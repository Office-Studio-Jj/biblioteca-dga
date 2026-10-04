"""Orquestador v2: lee columnas que existen en arancel_rd.db y responde la subpartida exacta.

Antes pedia dai_pct, itbis_pct, isc_pct, permisos y notas_legales, que la tabla codigos no
tiene: la consulta fallaba en silencio, ningun SON se verificaba y todo caia al pipeline.
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import orquestador_consulta_v2 as v2  # noqa: E402


def test_columnas_pedidas_existen_en_la_base():
    con = sqlite3.connect(v2._DB)
    reales = {fila[1] for fila in con.execute("PRAGMA table_info(codigos)")}
    con.close()
    faltan = set(v2._COLUMNAS_CODIGOS) - reales
    assert not faltan, f"columnas que codigos no tiene: {sorted(faltan)}"


def test_son_exacto_db_lee_tasas():
    carne = v2._son_exacto_db("0201.10.00")
    assert carne["gravamen"] == "40" and carne["dai_pct"] == 40
    assert carne["itbis"] == "EXENTO" and carne["itbis_pct"] is None

    cigarrillos = v2._son_exacto_db("2402.20.10")
    assert cigarrillos["itbis_pct"] == 18
    assert cigarrillos["isc"].startswith("RD$") and cigarrillos["isc_pct"] is None

    assert v2._son_exacto_db("9999.99.99") is None


def test_son_en_texto():
    assert v2._son_en_texto("8471.30.00") == "8471.30.00"
    assert v2._son_en_texto("¿Qué paga la 8471.30.00?") == "8471.30.00"
    assert v2._son_en_texto("laptop") is None
    assert v2._son_en_texto("8471.30.00 o 8471.41.00") is None  # comparar: lo decide el pipeline


def test_subpartida_exacta_se_resuelve_en_v2():
    r = v2.procesar_consulta("8471.30.00", solo_son_exacto=True)
    assert r["codigo_son"] == "8471.30.00"
    assert r["son_exacto"] and r["dai_pct"] == 0 and r["itbis_pct"] == 18
    informe = v2.formatear_informe(r)
    assert "8471.30.00" in informe and "DAI (Arancel): 0%" in informe and "ITBIS: 18%" in informe


def test_texto_libre_queda_para_el_pipeline():
    r = v2.procesar_consulta("zapatos de cuero para hombre", solo_son_exacto=True)
    assert r["codigo_son"] is None and r["limitado_son_exacto"]


def test_consultar_subpartida_exacta_no_cae_al_pipeline(monkeypatch):
    import server
    from notion_service import buscar_notion

    monkeypatch.setattr(server, "_get_cached", lambda *a: None)
    monkeypatch.setattr(server, "_set_cached", lambda *a: None)
    monkeypatch.setattr(buscar_notion, "buscar", lambda *a, **k: [])

    cliente = server.app.test_client()
    with cliente.session_transaction() as s:
        s["logged_in"] = True
    resp = cliente.post("/consultar", json={"question": "8471.30.00",
                                            "notebook_id": "biblioteca-de-nomenclaturas"})
    datos = resp.get_json()
    assert resp.status_code == 200, datos
    assert datos["cache_via"] == "orquestador_v2"
    assert datos["meta"]["codigo"] == "8471.30.00"


def _sons(consulta):
    return [s.get("son_destino") or s.get("partida_sugerida") for s in v2._buscar_sinonimos_v2(consulta)]


def test_sinonimos_no_coinciden_por_palabras_sueltas():
    # "para" llevaba estas consultas a "pantalla para celular" (8517.79.00)
    for consulta in ("zapatos para correr", "camisa para hombre", "zapatos de cuero para hombre"):
        assert _sons(consulta) == [], consulta


def test_sinonimos_respetan_el_nucleo_de_la_frase():
    # el producto es la funda, el cargador o la pantalla, no la tablet ni la laptop
    for consulta in ("funda para tablet", "cargador para laptop", "pantalla de laptop",
                     "mesa para computadora portatil"):
        assert _sons(consulta) == [], consulta


def test_sinonimos_validos_siguen_respondiendo():
    exacto = v2._buscar_sinonimos_v2("Patineta Eléctrica")
    assert exacto[0]["son_destino"] == "8711.60.14" and exacto[0]["coincidencia"] == "exacta"
    assert _sons("pantalla para celular") == ["8517.79.00"]
    inicio = v2._buscar_sinonimos_v2("bocina bluetooth")
    assert inicio[0]["partida_sugerida"] == "8518" and inicio[0]["coincidencia"] == "inicio"


def test_capa3_sinonimos_usa_el_mismo_criterio():
    # capa1_sqlite.orquestador_capa3.buscar_sinonimos (RGI 1 y agente guardian) usaba LIKE '%termino%'
    from capa1_sqlite import orquestador_capa3 as c3
    sons = lambda q: [s.get("son_destino") or s.get("partida_sugerida") for s in c3.buscar_sinonimos(q)]
    for consulta in ("para", "zapatos para correr", "funda para tablet", "pantalla de laptop"):
        assert sons(consulta) == [], consulta
    exacto = c3.buscar_sinonimos("Patineta Eléctrica")
    assert exacto and exacto[0]["son_destino"] == "8711.60.14" and exacto[0]["coincidencia"] == "exacta"
    assert "8517.79.00" in sons("pantalla para celular")
