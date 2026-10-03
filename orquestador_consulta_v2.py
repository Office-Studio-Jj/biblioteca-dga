"""
ORQUESTADOR DE CONSULTA ARANCELARIA v2
=======================================
Conecta los modulos R1-R7 al flujo de respuesta.
ARCHIVO NUEVO — no modifica ningun archivo existente.

Creado por orden directa del CEO — 4 mayo 2026.

Flujo:
    consulta → [R3 clasificador_rgi] → [R4 fallback] →
    [R1 validador_son] → SQLite gravamenes → [R7 permisos] →
    [R6 validador_pre_respuesta] → resultado

Base legal: Ley 168-21, Decreto 755-22, Decreto 36-22, Ley 11-92
"""

import json
import os
import re
import sqlite3
import sys
import unicodedata
from decimal import Decimal, InvalidOperation

_HERE = os.path.dirname(os.path.abspath(__file__))
_DB   = os.path.join(_HERE, "capa1_sqlite", "arancel_rd.db")

# Asegurar paths para importar sub-modulos
for _p in [
    _HERE,
    os.path.join(_HERE, "capa1_sqlite"),
    os.path.join(_HERE, "sub_agentes"),
    os.path.join(_HERE, "notebooklm_skill", "scripts"),
]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Seccion SA por capitulo (7ma Enmienda)
_SECCIONES = {
    range(1, 6): "I", range(6, 15): "II", range(15, 16): "III",
    range(16, 25): "IV", range(25, 28): "V", range(28, 39): "VI",
    range(39, 41): "VII", range(41, 44): "VIII", range(44, 47): "IX",
    range(47, 50): "X", range(50, 64): "XI", range(64, 68): "XII",
    range(68, 71): "XIII", range(71, 72): "XIV", range(72, 84): "XV",
    range(84, 86): "XVI", range(86, 90): "XVII", range(90, 93): "XVIII",
    range(93, 94): "XIX", range(94, 97): "XX", range(97, 98): "XXI",
}


def _seccion(cap_str: str) -> str:
    try:
        n = int(cap_str)
        for rango, sec in _SECCIONES.items():
            if n in rango:
                return sec
    except (ValueError, TypeError):
        pass
    return "DESCONOCIDA"


# Tasas DAI oficiales (Ley 146-00). Cualquier valor fuera de este set requiere
# verificacion manual — puede indicar error en la fuente de datos.
_TASAS_DAI_OFICIALES = {0, 3, 8, 14, 20, 25, 40}


# ── Helpers SQLite directos ─────────────────────────────────────────────────

# Columnas reales de la tabla codigos (arancel_rd.db). tests/test_orquestador_v2.py
# falla si alguna deja de existir en la base.
_COLUMNAS_CODIGOS = ("son", "descripcion", "gravamen", "itbis", "isc", "fuente")


def _tasa(valor) -> Decimal | None:
    """'20' o '20%' -> Decimal('20'). Texto como 'EXENTO' o 'NO APLICA' -> None."""
    texto = str(valor or "").strip().rstrip("%").strip()
    try:
        return Decimal(texto) if texto else None
    except InvalidOperation:
        return None


def _son_exacto_db(son: str) -> dict | None:
    """Lee un SON desde capa1_sqlite/arancel_rd.db.

    dai_pct, itbis_pct e isc_pct se derivan de gravamen, itbis e isc (la base no
    tiene columnas con esos nombres). permisos y notas_legales no estan en la base:
    los permisos salen de permisos_por_capitulo.json (PASO 7) y las notas del lector
    de notas.
    """
    if not son:
        return None
    try:
        con = sqlite3.connect(_DB)
        con.row_factory = sqlite3.Row
        row = con.execute(
            f"SELECT {', '.join(_COLUMNAS_CODIGOS)} FROM codigos WHERE son=?", (son,)
        ).fetchone()
        con.close()
    except sqlite3.Error as e:
        print(f"[ORQUESTADOR_V2] _son_exacto_db({son}): {e}", file=sys.stderr)
        return None
    if not row:
        return None
    datos = dict(row)
    datos["dai_pct"] = _tasa(datos.get("gravamen"))
    datos["itbis_pct"] = _tasa(datos.get("itbis"))
    datos["isc_pct"] = _tasa(datos.get("isc"))
    return datos


_SON_EN_TEXTO = re.compile(r"(?<![\d.])\d{4}\.\d{2}\.\d{2}(?:\.\d{2})?(?![\d.]*\d)")


def _son_en_texto(texto: str) -> str | None:
    """La unica subpartida (formato XXXX.XX.XX) escrita en el texto; None si hay 0 o varias."""
    encontrados = set(_SON_EN_TEXTO.findall(texto or ""))
    return encontrados.pop() if len(encontrados) == 1 else None


def _primer_son_de_partida(partida4: str) -> str | None:
    """Devuelve el SON mas especifico (no .00/.90/.99) dentro de una partida."""
    if not partida4 or len(partida4) < 4:
        return None
    p = partida4.replace(".", "")[:4]
    try:
        con = sqlite3.connect(_DB)
        rows = con.execute(
            "SELECT son FROM codigos WHERE REPLACE(son,'.','') LIKE ? ORDER BY son",
            (p + "%",)
        ).fetchall()
        con.close()
        if not rows:
            return None
        # Preferir subpartidas especificas sobre .00 / .90 / .99
        especificas = [r[0] for r in rows
                       if not r[0].endswith(".00") and not r[0].endswith(".90") and not r[0].endswith(".99")]
        return especificas[0] if especificas else rows[0][0]
    except Exception:
        return None


def _buscar_fts(termino: str, capitulo: str = "", limit: int = 5) -> list[dict]:
    """Busqueda FTS5 directa en arancel_rd.db."""
    if not termino:
        return []
    term_safe = " ".join(w + "*" for w in termino.split() if len(w) >= 3 and w.isalpha())
    if not term_safe:
        return []
    try:
        con = sqlite3.connect(_DB)
        rows = con.execute(
            "SELECT c.son, c.descripcion, c.gravamen, bm25(codigos_fts) AS rank "
            "FROM codigos_fts JOIN codigos c ON c.rowid=codigos_fts.rowid "
            "WHERE codigos_fts MATCH ? ORDER BY rank LIMIT ?",
            (term_safe, limit)
        ).fetchall()
        con.close()
        results = [{"son": r[0], "descripcion": r[1], "rank": r[3]} for r in rows]
        if capitulo and len(capitulo) >= 2:
            filtradas = [r for r in results if r["son"][:2] == capitulo[:2]]
            if filtradas:
                return filtradas
        return results
    except Exception:
        return []


_VACIAS = {
    "a", "al", "de", "del", "el", "la", "las", "lo", "los", "un", "una", "unos", "unas",
    "para", "por", "con", "sin", "en", "y", "o", "e", "u", "que", "tipo",
}


def _palabras(texto: str) -> list[str]:
    """Palabras en minuscula y sin acentos ("Patineta Eléctrica" → ["patineta", "electrica"])."""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", (texto or "").lower())
        if unicodedata.category(c) != "Mn"
    )
    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", sin_acentos)


def _buscar_sinonimos_v2(termino: str) -> list[dict]:
    """
    Sinonimos arancelarios que nombran el producto de la consulta, por palabras completas.

    El sinonimo tiene que coincidir con la consulta entera ("exacta") o con su comienzo
    ("inicio"): en espanol el nucleo va primero, asi "funda para tablet" no es una tablet
    ni "pantalla de laptop" una laptop. Se ignoran los sinonimos hechos solo de palabras
    vacias. Antes se comparaban pedazos de texto y "para" llevaba "zapatos para correr"
    a 8517.79.00 ("pantalla para celular").
    Cada resultado trae "coincidencia": "exacta" o "inicio". Los mas largos van primero.
    """
    consulta = _palabras(termino)
    if not consulta:
        return []
    cols = ["termino_busqueda", "termino_oficial", "capitulo_sugerido",
            "partida_sugerida", "tipo", "son_destino"]
    try:
        con = sqlite3.connect(_DB)
        rows = con.execute(
            "SELECT termino_busqueda, termino_oficial, capitulo_sugerido, "
            "partida_sugerida, tipo, son_destino FROM sinonimos_arancelarios"
        ).fetchall()
        con.close()
    except Exception:
        return []

    candidatos = []
    for r in rows:
        d = dict(zip(cols, r))
        sin = _palabras(d["termino_busqueda"])
        if not sin or all(p in _VACIAS for p in sin):
            continue
        if consulta == sin:
            d["coincidencia"] = "exacta"
        elif consulta[:len(sin)] == sin:
            d["coincidencia"] = "inicio"
        else:
            continue
        candidatos.append((len(sin), d))
    candidatos.sort(key=lambda c: -c[0])

    vistos, resultados = set(), []
    for _, d in candidatos:
        k = d.get("son_destino") or d.get("partida_sugerida", "")
        if k and k not in vistos:
            vistos.add(k)
            resultados.append(d)
    return resultados


# ── Punto de entrada principal ───────────────────────────────────────────────

def procesar_consulta(texto_usuario: str, solo_son_exacto: bool = False) -> dict:
    """
    Flujo completo v2: texto → SON verificado → gravamenes exactos + permisos.

    solo_son_exacto=True (lo usa /consultar): solo responde cuando la consulta trae una
    subpartida exacta que existe en el Arancel; el texto libre vuelve sin codigo_son y con
    limitado_son_exacto=True. Los sinonimos dan falsos positivos (ej. "para" en
    "pantalla para celular" → zapatos en 8517.79.00) hasta que se depuren.

    Modulos activos:
      R3 — clasificador_rgi.py   (RGI 1-6 secuencial)
      R4 — fallback_clasificacion.py  (RGI 4 analogia)
      R1 — validador_son.py      (existencia en arancel_rd.db)
      SQLite — gravamenes exactos (columnas gravamen, itbis, isc)
      R7 — permisos_por_capitulo.json
      R6 — validador_pre_respuesta.py
    """
    resultado = {
        "consulta": texto_usuario,
        "codigo_son": None,
        "descripcion_oficial": None,
        "capitulo": None,
        "seccion": None,
        "dai_pct": None,
        "itbis_pct": None,
        "isc_pct": None,
        "gravamen": None,
        "itbis": None,
        "isc": None,
        "permisos": None,
        "rgi_aplicada": None,
        "confianza": None,
        "fuente": "orquestador_v2",
        "advertencias": [],
        "base_legal": [
            "Ley 168-21 - Ley General de Aduanas RD",
            "Decreto 36-22 - Arancel Nacional vigente (7ma Enmienda SA)",
            "Ley 11-92 - Codigo Tributario (ITBIS/ISC)",
            "Decreto 755-22 - Reglamento RGI 1-6 (Arts. 62-77)",
        ],
    }

    if not texto_usuario or not texto_usuario.strip():
        resultado["advertencias"].append("Consulta vacia")
        return resultado

    texto_original = texto_usuario.strip()

    # ── PASO 0: subpartida exacta escrita en la consulta ("8471.30.00") ──
    # Si existe en arancel_rd.db se responde con sus tasas, sin Gemini ni sinonimos.
    son_exacto = _son_en_texto(texto_original)
    if son_exacto and not _son_exacto_db(son_exacto):
        resultado["advertencias"].append(
            f"La subpartida {son_exacto} no existe en el Arancel RD (Decreto 36-22)."
        )
        son_exacto = None
    if solo_son_exacto and not son_exacto:
        # Texto libre: lo resuelve el pipeline de 3 capas (Claude arbitro legal).
        resultado["limitado_son_exacto"] = True
        return resultado

    # === PRE-FILTRO GEMINI (Orden 10 CEO 04-05-2026) ===
    # Traduce lenguaje comercial → lenguaje arancelario SA.
    # Si Gemini falla → texto_usuario queda sin cambio, flujo no se rompe.
    if not son_exacto:
        try:
            from gemini_prefiltro import enriquecer_consulta as _ge
            texto_usuario = _ge(texto_usuario)
            resultado["consulta_enriquecida"] = texto_usuario
        except Exception:
            pass
    # === FIN PRE-FILTRO GEMINI ===

    son_candidato = None
    rgi_usada = None
    confianza = None
    if son_exacto:
        son_candidato = son_exacto
        rgi_usada     = "Subpartida indicada en la consulta (verificada en el Arancel, Decreto 36-22)"
        confianza     = "ALTA"
        resultado["son_exacto"] = True
        resultado["advertencias"].append(
            "La subpartida la indico la consulta: CLOPAS verifico que existe y muestra sus "
            "tasas, pero no comprobo que corresponda al producto."
        )

    # === PASO LEGAL: LECTURA DE NOTAS DE SECCION Y CAPITULO (RGI 1) ===
    # Decreto 755-22 Arts. 62-77: "la clasificacion esta determinada por el
    # texto de las partidas Y las Notas de Seccion o de Capitulo."
    # Se ejecuta ANTES de cualquier clasificacion para saber que esta incluido
    # y excluido en el capitulo candidato — evita errores como clasificar en
    # Cap. 85 algo que la Nota 1 de ese capitulo excluye explicitamente.
    _notas_capitulo = {}
    try:
        from navegador_jerarquico_sa import _detectar_capitulo as _det_cap
        _cap_num = son_exacto[:2] if son_exacto else _det_cap(texto_usuario)
        if _cap_num:
            from sub_agentes.lector_notas_arancel import leer_notas_capitulo
            _notas_capitulo = leer_notas_capitulo(str(_cap_num).zfill(2))
            resultado["notas_capitulo"] = {
                "capitulo":      _notas_capitulo.get("capitulo"),
                "seccion":       _notas_capitulo.get("seccion"),
                "seccion_titulo": _notas_capitulo.get("seccion_titulo"),
                "titulo_cap":    _notas_capitulo.get("titulo_cap"),
                "notas_legales": _notas_capitulo.get("notas_legales", [])[:5],
                "isc_aplicable": _notas_capitulo.get("isc_aplicable"),
                "fuente":        _notas_capitulo.get("fuente"),
                # RGI 1: Notas de Seccion al mismo nivel jerarquico que notas de Capitulo
                "notas_seccion": _notas_capitulo.get("notas_seccion", {}),
            }
    except Exception as _en:
        resultado["advertencias"].append(f"lector_notas_capitulo: {_en}")
    # === FIN PASO LEGAL NOTAS ===

    # ── PASO 1: sinonimos arancelarios (prioridad maxima — mapeo explicito) ──
    # Los sinonimos son verdad explicita: "patineta electrica" = 8711.60.14.
    # Deben correr ANTES que el clasificador para evitar que el clasificador
    # pise un mapeo directo con un resultado fuzzy incorrecto.
    # BUG-CEO-001 FIX: buscar con texto ORIGINAL primero (Gemini puede borrar
    # las palabras que matchean con sinonimos al traducir).
    sinonimos = [] if son_candidato else _buscar_sinonimos_v2(texto_original)
    if not sinonimos and not son_candidato:
        sinonimos = _buscar_sinonimos_v2(texto_usuario)
    for sin in sinonimos:
        son_t = sin.get("son_destino")
        if not son_t:
            partida = sin.get("partida_sugerida", "")
            if partida:
                son_t = _primer_son_de_partida(partida)
        if son_t and _son_exacto_db(son_t):
            son_candidato = son_t
            rgi_usada     = "RGI 1 (via sinonimo arancelario)"
            # Solo el sinonimo que es la consulta entera da ALTA; "laptop dell" → MEDIA.
            confianza     = "ALTA" if sin.get("coincidencia") == "exacta" else "MEDIA"
            break

    # ── PASO 2: navegador_jerarquico_sa (RGI 1→3a — navega el arbol SA) ───
    # Si no hubo sinonimo directo, navegar jerarquia: capitulo→partida→subpartida→SON.
    # Nunca devuelve el primer codigo del capitulo — evalua TODAS las partidas.
    if not son_candidato:
        try:
            from navegador_jerarquico_sa import navegar_jerarquia
            son_nav = navegar_jerarquia(texto_original)
            if son_nav and _son_exacto_db(son_nav):
                son_candidato = son_nav
                rgi_usada     = "RGI 1 (navegador_jerarquico_sa)"
                confianza     = "MEDIA"
        except Exception as e:
            resultado["advertencias"].append(f"navegador_jerarquico: {e}")

    # ── PASO 3: clasificador_rgi.py (R3) — RGI 1→6 secuencial ─────────────
    if not son_candidato:
        try:
            from sub_agentes.clasificador_rgi import clasificar_por_rgi
            res_rgi = clasificar_por_rgi(texto_usuario)
            if res_rgi and res_rgi.get("son_final"):
                son_candidato = res_rgi["son_final"]
                rgi_usada     = res_rgi.get("rgi_aplicada", "RGI 1")
                confianza     = res_rgi.get("confianza", "MEDIA")
        except Exception as e:
            resultado["advertencias"].append(f"R3 clasificador_rgi: {e}")

    # ── PASO 4: busqueda FTS5 directa ────────────────────────────────────
    if not son_candidato:
        hits = _buscar_fts(texto_usuario, limit=5)
        if hits:
            son_candidato = hits[0]["son"]
            rgi_usada     = "RGI 1 (FTS5 — verificar descripcion)"
            confianza     = "BAJA"

    # ── PASO 5: fallback_clasificacion (R4) — analogia RGI 4 ─────────────
    if not son_candidato:
        try:
            from sub_agentes.fallback_clasificacion import clasificar_fallback
            res_fb = clasificar_fallback(texto_usuario)
            if res_fb and res_fb.get("son_final"):
                son_candidato = res_fb["son_final"]
                rgi_usada     = res_fb.get("rgi_aplicada", "RGI 4 (analogia)")
                confianza     = "BAJA"
                resultado["advertencias"].append(
                    "Clasificacion por analogia (RGI 4) — requiere validacion manual"
                )
        except Exception as e:
            resultado["advertencias"].append(f"R4 fallback: {e}")

    if not son_candidato:
        resultado["advertencias"].append(
            "Sin clasificacion automatica. Consultar aforador DGA (Ley 168-21 Art. 76)."
        )
        resultado["solicita_ficha_tecnica"] = True
        resultado["nivel_confianza"] = "ROJO"
        resultado["confianza"] = "INSUFICIENTE"
        resultado["mensaje_ficha"] = (
            "Para clasificar esta mercancia necesito la ficha tecnica del fabricante. "
            "Sin estos datos, el sistema no puede determinar la partida arancelaria "
            "(Ley 168-21 Art. 76, Decreto 755-22).\n\n"
            "Datos especificos que necesito:\n"
            "  - Material constitutivo principal y secundarios\n"
            "  - Funcion principal declarada por el fabricante\n"
            "  - Uso previsto y uso final del producto\n"
            "  - Marca y modelo del fabricante (para buscar ficha tecnica)"
        )
        return resultado

    # ── PASO 5: validar_son.py (R1) — existencia en arancel_rd.db ─────────
    existe = False
    try:
        from capa1_sqlite.validador_son import validar_codigo
        val = validar_codigo(son_candidato)
        existe = bool(val.get("existe"))
        if not existe:
            alts = val.get("alternativas", [])
            resultado["advertencias"].append(
                f"CODIGO {son_candidato} NO EXISTE en Arancel RD. "
                f"Alternativas sugeridas: {alts[:3]}"
            )
            # Intentar primera alternativa
            if alts:
                son_candidato = alts[0]
                existe = bool(_son_exacto_db(son_candidato))
    except Exception:
        # Fallback: verificacion directa en SQLite
        existe = bool(_son_exacto_db(son_candidato))

    if not existe:
        resultado["advertencias"].append(
            f"Codigo {son_candidato} no verificado. Consultar aduanas.gob.do"
        )
        return resultado

    # ── PASO 6: gravamenes exactos desde SQLite (Capa 1 verdad) ──────────
    datos = _son_exacto_db(son_candidato)
    if datos:
        resultado["codigo_son"]          = son_candidato
        resultado["descripcion_oficial"] = (datos.get("descripcion") or "")[:200]
        resultado["gravamen"]            = datos.get("gravamen")
        resultado["itbis"]               = datos.get("itbis")
        resultado["isc"]                 = datos.get("isc")
        resultado["dai_pct"]             = datos.get("dai_pct")
        resultado["itbis_pct"]           = datos.get("itbis_pct")
        resultado["isc_pct"]             = datos.get("isc_pct")
        resultado["capitulo"]            = son_candidato[:2]
        resultado["seccion"]             = _seccion(son_candidato[:2])
        resultado["rgi_aplicada"]        = rgi_usada
        resultado["confianza"]           = confianza
        resultado["fuente"]              = "arancel_rd.db — Decreto 36-22, 7ma Enmienda SA"

        # Validar DAI contra tasas oficiales Ley 146-00
        dai_val = datos.get("dai_pct")
        if dai_val is not None:
            try:
                dai_num = int(round(float(dai_val)))
                if dai_num not in _TASAS_DAI_OFICIALES:
                    resultado["advertencias"].append(
                        f"DAI {dai_num}% no esta en tasas oficiales Ley 146-00 "
                        f"({', '.join(str(t) + '%' for t in sorted(_TASAS_DAI_OFICIALES))}). "
                        "Verificar en aduanas.gob.do."
                    )
            except (ValueError, TypeError):
                pass

    # ── PASO 6.5: VALIDACION DE SUFICIENCIA DE DATOS (Dictamen CEO) ─────
    # El sistema clasifica o pide ficha tecnica. Nunca adivina.
    # Si la RGI aplicada es 2/3b/3c/4 y los datos del usuario no alcanzan
    # para determinar con certeza, se detiene y pide ficha del fabricante.
    try:
        from sub_agentes.validador_suficiencia import evaluar_suficiencia
        _suf = evaluar_suficiencia(
            texto_original,
            rgi_usada or "",
            confianza or "",
            capitulo=son_candidato[:2] if son_candidato else "",
        )
        resultado["suficiencia"] = _suf
        if not _suf["suficiente"]:
            resultado["solicita_ficha_tecnica"] = True
            resultado["nivel_confianza"] = _suf["nivel"]
            resultado["datos_faltantes"] = _suf.get("datos_faltantes", [])
            resultado["mensaje_ficha"] = _suf.get("mensaje_usuario", "")
            if _suf["nivel"] == "ROJO":
                resultado["advertencias"].append(
                    f"DATOS INSUFICIENTES para {_suf.get('rgi_bloqueante', 'clasificacion')}. "
                    "Adjunte ficha tecnica del fabricante para clasificacion definitiva."
                )
                resultado["confianza"] = "PROVISIONAL"
    except Exception as _esuf:
        resultado["advertencias"].append(f"validador_suficiencia: {_esuf}")
    # === FIN PASO 6.5 ===

    # ── PASO 7: permisos_por_capitulo.json (R7) ───────────────────────────
    if resultado.get("capitulo") and not resultado.get("permisos"):
        try:
            perm_path = os.path.join(
                _HERE, "notebooklm_skill", "data", "permisos_por_capitulo.json"
            )
            with open(perm_path, "r", encoding="utf-8") as f:
                pj = json.load(f)
            cap_key = f"cap_{resultado['capitulo']}"
            if cap_key in pj:
                resultado["permisos"] = pj[cap_key]
        except Exception:
            pass

    # ── PASO 8: validador_pre_respuesta (R6) — nunca enviar sin validar ───
    try:
        from sub_agentes.validador_pre_respuesta import validar_respuesta
        vf = validar_respuesta(resultado)
        if vf.get("datos_inventados"):
            resultado["advertencias"].append(
                "ALERTA: Campos sin respaldo detectados. Verificar manualmente."
            )
    except Exception:
        pass

    # ── APRENDIZAJE: si Gemini enriqueció Y se obtuvo SON válido → guardar sinonimo ──
    # BUG-FIX 06-05-2026: validar que la descripcion del SON tiene relacion con la
    # consulta ANTES de guardar. Sin esto, clasificaciones erroneas se guardan como
    # sinonimos y contaminan TODAS las busquedas futuras.
    consulta_original_raw = resultado.get("consulta", "")
    consulta_enriquecida  = resultado.get("consulta_enriquecida", "")
    son_final = resultado.get("codigo_son")
    desc_final = (resultado.get("descripcion_oficial") or "").lower()
    if (consulta_enriquecida
            and consulta_enriquecida.lower() != consulta_original_raw.lower()
            and son_final
            and confianza in ("ALTA", "MEDIA")):
        # Validar relevancia: al menos 1 palabra de 4+ chars de la consulta (no "para")
        # debe aparecer como palabra en la descripcion oficial del SON
        _palabras_consulta = [w for w in _palabras(consulta_original_raw)
                              if len(w) >= 4 and w not in _VACIAS]
        _relevante = bool(set(_palabras_consulta) & set(_palabras(desc_final)))
        if _relevante:
            try:
                with sqlite3.connect(_DB) as _conn:
                    _conn.execute(
                        "INSERT OR IGNORE INTO sinonimos_arancelarios "
                        "(termino_busqueda, termino_oficial, capitulo_sugerido, "
                        "partida_sugerida, tipo, son_destino) VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            consulta_original_raw.lower().strip(),
                            f"[auto-Gemini] {consulta_enriquecida[:120]}",
                            son_final[:2],
                            son_final[:4],
                            "sinonimo",
                            son_final,
                        ),
                    )
            except Exception:
                pass

    return resultado


def _isc_v2(son, isc_pct, isc_texto=None):
    """Monto especifico vigente (cigarrillos, alcoholes), el ISC% o el texto de la columna isc."""
    try:
        from capa1_sqlite.isc_especifico import texto_isc
        esp = texto_isc(son)
        if esp:
            return esp
    except Exception:
        pass
    if isc_pct is not None:
        return f"{isc_pct}%"
    return isc_texto or "NO APLICA"


def formatear_informe(resultado: dict) -> str:
    """Convierte resultado dict a texto estructurado para respuesta al usuario."""
    son    = resultado.get("codigo_son", "No determinado")
    desc   = (resultado.get("descripcion_oficial") or "")[:100]
    cap    = resultado.get("capitulo", "?")
    sec    = resultado.get("seccion", "?")
    dai    = resultado.get("dai_pct")
    itbis  = resultado.get("itbis_pct")
    isc    = resultado.get("isc_pct")
    grav   = resultado.get("gravamen")
    rgi    = resultado.get("rgi_aplicada", "?")
    conf   = resultado.get("confianza", "?")
    perms  = resultado.get("permisos", "")
    warns  = resultado.get("advertencias", [])
    blegal = resultado.get("base_legal", [])

    lineas = [
        f"## Clasificacion arancelaria — {resultado.get('consulta', '')}",
        "",
        f"**Codigo SON:** {son}",
        f"**Descripcion:** {desc}",
        f"**Capitulo SA:** {cap} | **Seccion SA:** {sec}",
        f"**RGI aplicada:** {rgi} | **Confianza:** {conf}",
        "",
        "### Regimen Tributario (Decreto 36-22)",
        f"- DAI (Arancel): {dai}%" if dai is not None else f"- DAI: {grav or 'verificar'}",
        f"- ITBIS: {itbis}%" if itbis is not None else f"- ITBIS: {resultado.get('itbis') or 'verificar'}",
        f"- ISC: {_isc_v2(son, isc, resultado.get('isc'))}",
        "",
    ]

    # Notas Legales (RGI 1 — Decreto 755-22 Art. 63): Seccion primero, luego Capitulo
    notas = resultado.get("notas_capitulo", {})
    if notas:
        # Notas de Seccion (primer nivel jerarquico)
        ns = notas.get("notas_seccion", {})
        if ns and ns.get("notas_legales"):
            lineas += [
                f"### Notas de Seccion {ns.get('seccion')}: {ns.get('titulo', '')}",
            ]
            for nota in ns.get("notas_legales", []):
                lineas.append(f"  - {str(nota)[:300]}")
            for excl in (ns.get("exclusiones") or []):
                lineas.append(f"  - *Excluye:* {str(excl)[:250]}")
            lineas.append("")

        # Notas de Capitulo (segundo nivel jerarquico)
        if notas.get("titulo_cap"):
            lineas += [
                f"### Notas de Capitulo {notas.get('capitulo')} "
                f"(Sec. {notas.get('seccion')}: {notas.get('seccion_titulo', '')})",
                f"*{notas.get('titulo_cap', '')}*",
            ]
            for nota in (notas.get("notas_legales") or []):
                if isinstance(nota, dict):
                    nota = nota.get("texto", str(nota))
                lineas.append(f"  - {str(nota)[:300]}")
            if notas.get("isc_aplicable"):
                lineas.append(f"  - ISC RD: {notas['isc_aplicable']}")
            lineas.append("")

    # Paso 6.5: solicitud de ficha tecnica si datos insuficientes
    if resultado.get("solicita_ficha_tecnica"):
        suf = resultado.get("suficiencia", {})
        nivel = suf.get("nivel", "AMARILLO")
        if nivel == "ROJO":
            lineas += [
                "### ATENCION: Clasificacion PROVISIONAL",
                "",
                f"**Codigo SON {son} es provisional.** El sistema necesita la ficha "
                "tecnica del fabricante para confirmar con 100% de certeza.",
                "",
            ]
        else:
            lineas += [
                "### Ficha tecnica recomendada",
                "",
                "Para confirmar esta clasificacion al 100%, adjunte ficha tecnica.",
                "",
            ]
        msg = resultado.get("mensaje_ficha", "")
        if msg:
            for line in msg.split("\n"):
                lineas.append(line)
            lineas.append("")

    if perms:
        lineas += ["### Permisos y Restricciones", str(perms), ""]

    if blegal:
        lineas += ["### Base Legal", *[f"- {l}" for l in blegal], ""]

    if warns:
        lineas += ["### Advertencias", *[f"- {w}" for w in warns]]

    return "\n".join(lineas)
