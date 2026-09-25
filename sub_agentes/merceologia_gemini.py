"""Gemini restringido a investigación merceológica.

Gemini describe QUÉ ES el producto (origen, composición, función, uso, criterio que
prevalece). Nunca emite capítulos, partidas, SON, tasas ni leyes: todo dato arancelario
sale de la biblioteca-dga (capa1_sqlite/arancel_rd.db) y del árbitro legal (Claude).
"""

import json
import os
import re
import sqlite3
import sys
from collections import defaultdict

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_RAIZ, "capa1_sqlite", "arancel_rd.db")
_SCRIPTS = os.path.join(_RAIZ, "notebooklm_skill", "scripts")

CRITERIOS = ("materia", "funcion", "uso", "parte_accesorio", "conjunto_o_juego", "estado_presentacion")

_SYSTEM = (
    "Eres un perito merceólogo. Tu única tarea es describir la mercancía: su origen, "
    "composición, función, uso y presentación, y qué criterio merceológico la caracteriza. "
    "No clasificas: no menciones capítulos, partidas, subpartidas, códigos numéricos, "
    "aranceles, impuestos ni leyes. Si un dato no se puede saber con la descripción dada, "
    "déjalo vacío y agrégalo a datos_faltantes; no lo inventes. Responde solo con el JSON pedido."
)

_PROMPT = """Mercancía: "{producto}"

Devuelve este JSON:
{{
  "nombre_tecnico": "denominación técnica o comercial genérica",
  "que_es": "qué es la mercancía, en una frase",
  "origen": "animal | vegetal | mineral | sintetico | manufacturado | mixto",
  "composicion": "materiales o sustancias y su proporción si se conoce",
  "funcion": "función técnica principal",
  "mecanismo": "cómo opera o actúa",
  "uso": "uso o destino principal",
  "usuarios": "quién lo usa",
  "presentacion": "estado o forma en que se importa (a granel, envasado, desmontado, kit, repuesto...)",
  "es_parte_o_accesorio": false,
  "producto_al_que_pertenece": "si es parte o accesorio, de qué mercancía",
  "criterio_prevalente": "{criterios}",
  "justificacion_criterio": "por qué ese criterio caracteriza a la mercancía",
  "terminos_busqueda": ["3 a 6 términos descriptivos en español para buscar en un arancel"],
  "sinonimos": ["nombres alternativos"],
  "datos_faltantes": ["datos técnicos que harían falta para identificarla con certeza"]
}}"""

_PATRON_ARANCELARIO = re.compile(
    r"\b(?:cap[ií]tulos?|cap\.|partidas?|subpartidas?|sac|son|sa|hs)\s*n?[º°o.]?\s*:?\s*\d[\d.]*"
    r"|\b\d{2}\.\d{2}(?:\.\d{2}){0,2}\b|\b\d{6,10}\b",
    re.I)


def _limpiar(valor):
    """Quita cualquier referencia arancelaria que Gemini haya colado en un campo."""
    if isinstance(valor, str):
        t = _PATRON_ARANCELARIO.sub("", valor)
        t = re.sub(r"\(\s*[,;\s]*\)", "", t)
        return " ".join(re.sub(r"\s+([,.;)])", r"\1", t).split()).strip(" ,;")
    if isinstance(valor, list):
        return [v for v in (_limpiar(x) for x in valor) if v]
    return valor


def investigar_merceologia(producto, timeout=20):
    """Ficha merceológica del producto según Gemini. {} si Gemini no está disponible."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or not (producto or "").strip():
        return {}
    if _SCRIPTS not in sys.path:
        sys.path.insert(0, _SCRIPTS)
    try:
        from ask_gemini import _gemini_rest_call
        texto, err = _gemini_rest_call(
            api_key, "gemini-2.5-flash", _SYSTEM,
            _PROMPT.format(producto=producto.replace('"', "'")[:600], criterios=" | ".join(CRITERIOS)),
            timeout=int(timeout))
    except Exception as e:
        print(f"[MERCEOLOGIA] Gemini no disponible: {e}")
        return {}
    if err or not texto:
        print(f"[MERCEOLOGIA] Gemini sin respuesta: {err}")
        return {}
    m = re.search(r"\{[\s\S]*\}", texto)
    try:
        ficha = json.loads(m.group(0)) if m else {}
    except ValueError:
        return {}
    ficha = {k: _limpiar(v) for k, v in ficha.items()}
    if ficha.get("criterio_prevalente") not in CRITERIOS:
        ficha["criterio_prevalente"] = ""
    ficha["fuente"] = "gemini_merceologia"
    return ficha


def terminos_de_ficha(ficha, consulta=""):
    """Términos para buscar en la biblioteca: los del usuario primero, luego los de la ficha."""
    vistos, out = set(), []
    fuentes = [consulta, ficha.get("nombre_tecnico", "")] + list(ficha.get("terminos_busqueda", [])) \
        + list(ficha.get("sinonimos", []))
    if ficha.get("es_parte_o_accesorio"):
        fuentes.insert(1, ficha.get("producto_al_que_pertenece", ""))
    for t in fuentes:
        t = (t or "").strip()
        if t and t.lower() not in vistos:
            vistos.add(t.lower())
            out.append(t)
    return out


def _fts(termino, limite=15):
    palabras = [w for w in re.findall(r"[a-záéíóúñü]+", termino.lower()) if len(w) >= 3]
    if not palabras:
        return []
    try:
        con = sqlite3.connect(_DB)
        filas = con.execute(
            "SELECT c.son, c.descripcion, bm25(codigos_fts) FROM codigos_fts "
            "JOIN codigos c ON c.rowid = codigos_fts.rowid "
            "WHERE codigos_fts MATCH ? ORDER BY bm25(codigos_fts) LIMIT ?",
            (" OR ".join(w + "*" for w in palabras), limite)).fetchall()
        con.close()
        return filas
    except sqlite3.Error:
        return []


def capitulos_desde_biblioteca(terminos, maximo=3):
    """Capítulos candidatos por votación de coincidencias en arancel_rd.db (biblioteca-dga).

    Devuelve [{"capitulo": "85", "votos": 7.5, "ejemplos": ["8524.91.11 ...", ...]}].
    Los primeros términos (consulta del usuario, nombre técnico) pesan más.
    """
    votos, ejemplos = defaultdict(float), defaultdict(list)
    for i, termino in enumerate(terminos[:8]):
        peso = 1.0 / (1 + i * 0.5)
        for pos, (son, desc, _rank) in enumerate(_fts(termino)):
            cap = son[:2]
            votos[cap] += peso / (1 + pos * 0.2)
            if len(ejemplos[cap]) < 3 and not any(e.startswith(son) for e in ejemplos[cap]):
                ejemplos[cap].append(f"{son} {desc[:70]}")
    orden = sorted(votos.items(), key=lambda kv: kv[1], reverse=True)[:maximo]
    return [{"capitulo": c, "votos": round(v, 2), "ejemplos": ejemplos[c]} for c, v in orden]


def son_en_biblioteca(son):
    """Datos oficiales de un SON (XXXX.XX.XX) desde arancel_rd.db, o None si no existe."""
    try:
        con = sqlite3.connect(_DB)
        fila = con.execute(
            "SELECT son, descripcion, gravamen, itbis, isc FROM codigos WHERE son = ?", (son,)).fetchone()
        con.close()
    except sqlite3.Error:
        return None
    if not fila:
        return None
    return dict(zip(("son", "descripcion", "gravamen", "itbis", "isc"), fila))
