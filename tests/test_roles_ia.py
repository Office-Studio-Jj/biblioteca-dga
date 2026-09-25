"""Reglas de roles: Gemini solo informa merceologia; Claude + biblioteca-dga deciden."""

import json
import os
import sys
from unittest import mock

_RAIZ = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _RAIZ)
sys.path.insert(0, os.path.join(_RAIZ, "notebooklm_skill", "scripts"))

from sub_agentes import arbitro_claude, clopas_auto, merceologia_gemini as mg  # noqa: E402


def test_ficha_merceologica_no_trae_codigos():
    t = mg._limpiar("Módulo de pantalla (partida 85.24, cap. 85, SON 8524.91.11) para teléfono")
    assert t == "Módulo de pantalla para teléfono"
    assert mg._limpiar(["capítulo 76", "aluminio"]) == ["aluminio"]


def test_biblioteca_solo_propone_candidatos():
    cands = mg.capitulos_desde_biblioteca(["bombillo led", "diodos emisores de luz"])
    assert cands and all(set(c) == {"capitulo", "votos", "ejemplos"} for c in cands)


def test_arbitro_rechaza_capitulo_fuera_de_lista_sin_justificar():
    cands = [{"capitulo": "85", "votos": 3, "ejemplos": []}, {"capitulo": "94", "votos": 1, "ejemplos": []}]
    with mock.patch.object(arbitro_claude, "llamar_claude_json", return_value={"capitulo": "71"}):
        assert arbitro_claude.elegir_capitulo("x", {}, cands) is None
    with mock.patch.object(arbitro_claude, "llamar_claude_json",
                           return_value={"capitulo": "83", "capitulo_fuera_de_lista": True}):
        assert arbitro_claude.elegir_capitulo("medalla", {}, cands)["capitulo"] == "83"
    with mock.patch.object(arbitro_claude, "llamar_claude_json", return_value=None):
        assert arbitro_claude.elegir_capitulo("x", {}, cands) is None


def test_sin_claude_no_hay_capitulo():
    import pipeline_3_capas as p3
    with mock.patch.object(mg, "investigar_merceologia", return_value={}), \
            mock.patch.object(arbitro_claude, "llamar_claude_json", return_value=None):
        r = p3._gemini_identificar_capitulo("bombillo led")
    assert r["ok"] is False and "capitulo" not in r


def test_verificador_solo_informa():
    import verificador_arancelario as v
    ok = v.verificar_codigo_y_cargos("9022.90.10", "x")
    assert ok["existe"] and ok["gravamen_ad_valorem"] == "0%" and ok["codigo_correcto"] == "9022.90.10"
    no = v.verificar_codigo_y_cargos("8517.70.00", "x")
    assert no["existe"] is False and no["codigo_correcto"] == ""


def test_supervisor_no_sustituye_codigo_inexistente():
    import supervisor_interno as si
    resp = ("---DATOS_CLASIFICACION---\nSUBPARTIDA_NAC: 8517.70.00 pantalla\nAUDITORIA: APROBADA\n"
            "---FIN_CLASIFICACION---")
    nueva, estado, _ = si._check_fuentes_pdf(resp, "pantalla celular", "biblioteca-de-nomenclaturas")
    linea = next(l for l in nueva.splitlines() if l.startswith("SUBPARTIDA_NAC"))
    assert linea.startswith("SUBPARTIDA_NAC: NO DETERMINADA") and estado == "ERROR"


def _resultado(requiere=True, costo="DOP 1,000.00"):
    return {"son": "9022.90.10", "descripcion": "- - Pantallas radiológicas", "gravamen": "0%",
            "itbis": "18%", "requiere_vuce": requiere, "url": "https://sirevuce.aduanas.gob.do/x",
            "formularios": [{"nombre": "Productos Sanitarios", "campos": {
                "Organismos externos": ["MISPAS"], "Costo": [costo]}}] if requiere else []}


def test_clopas_registra_una_vez_y_detecta_cambios():
    clopas_auto._vistos.clear()
    enviados, existente = [], {"v": None}

    def fake_notion(ruta, cuerpo):
        enviados.append((ruta, cuerpo))
        if ruta.endswith("/query"):
            return {"results": [existente["v"]] if existente["v"] else []}
        return {"id": "p"}

    with mock.patch.dict(os.environ, {"NOTION_API_KEY": "x"}), \
            mock.patch.object(clopas_auto, "_notion", side_effect=fake_notion), \
            mock.patch.object(clopas_auto, "_en_segundo_plano", side_effect=lambda f, *a: f(*a)):
        clopas_auto.registrar_consulta_vucerd({"estado": "VERIFICADO", "resultados": [_resultado()]})
        clopas_auto.registrar_consulta_vucerd({"estado": "VERIFICADO", "resultados": [_resultado()]})
        creados = [c for r, c in enviados if r == "/pages"]
        assert len(creados) == 1
        assert creados[0]["properties"]["Tipo"]["select"]["name"] == "Creación"

        huella = clopas_auto._huella(_resultado())
        existente["v"] = {"url": "u", "properties": {"Código": {"rich_text": [{"plain_text": f"huella={huella}"}]}}}
        clopas_auto.registrar_consulta_vucerd({"estado": "VERIFICADO", "resultados": [_resultado(costo="DOP 2,000.00")]})
        creados = [c for r, c in enviados if r == "/pages"]
        assert creados[-1]["properties"]["Tipo"]["select"]["name"] == "Corrección"

    assert "pantalla para celular" not in json.dumps(enviados, ensure_ascii=False)


def test_clopas_error_diario_sin_duplicar():
    clopas_auto._vistos.clear()
    enviados = []
    with mock.patch.dict(os.environ, {"NOTION_API_KEY": "x"}), \
            mock.patch.object(clopas_auto, "_notion",
                              side_effect=lambda r, c: enviados.append(r) or {"results": []}), \
            mock.patch.object(clopas_auto, "_en_segundo_plano", side_effect=lambda f, *a: f(*a)):
        for _ in range(3):
            clopas_auto.registrar_consulta_vucerd({"estado": "NO_VERIFICADO", "error": "403"})
    assert enviados.count("/pages") == 1


def test_clopas_inactivo_sin_clave():
    with mock.patch.dict(os.environ, {"NOTION_API_KEY": ""}), \
            mock.patch.object(clopas_auto, "_en_segundo_plano") as bg:
        clopas_auto.registrar_consulta_vucerd({"estado": "NO_VERIFICADO"})
    bg.assert_not_called()


class _Bloque:
    def __init__(self, tipo, texto=""):
        self.type, self.text = tipo, texto


class _Resp:
    def __init__(self, stop, bloques):
        self.stop_reason, self.content = stop, bloques


def _cliente_simulado(respuestas, llamadas):
    class _Msgs:
        def create(self, **kw):
            llamadas.append(kw)
            return respuestas.pop(0)

    class _Beta:
        messages = _Msgs()

    class _C:
        beta = _Beta()

        def with_options(self, **kw):
            return self
    return _C()


def test_web_solo_dominios_oficiales_y_reanuda_pausa():
    llamadas = []
    respuestas = [_Resp("pause_turn", [_Bloque("server_tool_use")]),
                  _Resp("end_turn", [_Bloque("server_tool_use"), _Bloque("text", "Respuesta con fuente")])]
    with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "x"}), \
            mock.patch.object(arbitro_claude, "_cliente", return_value=_cliente_simulado(respuestas, llamadas)):
        texto = arbitro_claude.llamar_claude("sys", "pregunta", web=True)
    assert texto == "Respuesta con fuente" and len(llamadas) == 2
    for h in llamadas[0]["tools"]:
        assert h["allowed_domains"] == arbitro_claude.DOMINIOS_OFICIALES_RD and h["max_uses"] <= 2
    assert all(d.endswith((".gob.do", ".gov.do")) for d in arbitro_claude.DOMINIOS_OFICIALES_RD)
    assert llamadas[1]["messages"][-1]["role"] == "assistant"


def test_sin_web_no_hay_herramientas():
    llamadas = []
    with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "x"}), \
            mock.patch.object(arbitro_claude, "_cliente",
                              return_value=_cliente_simulado([_Resp("end_turn", [_Bloque("text", "ok")])], llamadas)):
        assert arbitro_claude.llamar_claude("sys", "p") == "ok"
    assert "tools" not in llamadas[0]


def test_contexto_legal_incluye_rgi_notas_partidas_y_aperturas():
    from sub_agentes.contexto_legal import construir
    b = construir(["83"], ["83.06"])
    assert "RGI 1" in b and "CAPÍTULO 83" in b and "83.06 Campanas" in b and "8306.29.00" in b


def test_validador_jerarquia_advierte_sin_sustituir():
    from sub_agentes.validador_jerarquia_sa import validar_y_corregir
    for consulta, son in (("Dron aereo para agricultura", "8806.23.19"),
                          ("pantalla para celular", "8501.10.10")):
        final, informe = validar_y_corregir(consulta, son)
        assert final == son
        assert "son_corregido" not in informe
        if informe.get("valido") is False:
            assert informe.get("sustitucion", "").startswith("no aplicada")
