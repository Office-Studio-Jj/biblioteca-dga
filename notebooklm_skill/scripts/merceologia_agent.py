#!/usr/bin/env python3
"""
MERCEOLOGIA AGENT — Sub-agente cache-first para consultas arancelarias
======================================================================
Intercepta consultas antes de Gemini. Si hay ficha merceologica previa
que matchea la descripcion del producto, devuelve respuesta instantanea
con el codigo arancelario ya validado (0% Gemini, 100% cache-first).

Ganancia: consultas con match retornan en <500ms (vs 8-10s con Gemini).

Integracion: llamado desde server.py /consultar antes de ask_notebooklm.
"""

import os
import re
import json
import time
import unicodedata
from pathlib import Path
from typing import Optional, Tuple, List, Dict


_MERCEO_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "data", "merceologia"
)

# Cache en memoria: {slug: {"contenido": str, "keywords": set, "codigo": str, "mtime": float}}
_FICHAS_CACHE: Dict[str, dict] = {}
_CACHE_MTIME = 0.0


def _normalizar(s: str) -> str:
    """Normaliza texto para matching: minusculas, sin acentos, sin signos."""
    s = (s or "").strip().lower()
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = s.replace('ñ', 'n')
    return s


def _extraer_keywords(texto: str) -> set:
    """Extrae keywords significativas (len >= 4, no stopwords)."""
    stopwords = {
        'para', 'cual', 'como', 'donde', 'este', 'esta', 'estas', 'estos',
        'pueda', 'tiene', 'tienen', 'puede', 'pueden', 'favor', 'quiero',
        'necesito', 'consulta', 'clasificar', 'producto', 'producto',
        'con', 'sin', 'por', 'entre', 'sobre', 'bajo', 'desde', 'hacia',
        'segun', 'durante', 'mediante', 'hasta', 'contra', 'uso', 'usa',
        'usan', 'usar', 'los', 'las', 'del', 'una', 'uno', 'unas', 'unos',
    }
    texto_norm = _normalizar(texto)
    palabras = re.findall(r'\b[a-z0-9]{4,}\b', texto_norm)
    return {p for p in palabras if p not in stopwords}


def _extraer_codigo_de_ficha(contenido_md: str) -> Optional[str]:
    """Extrae el codigo arancelario RD (8 dig) de la pregunta 7."""
    m = re.search(
        r'(?:[Cc]odigo\s+nacional\s+RD|c[oó]digo\s+(?:arancelario\s+)?(?:RD)?)[^:]*:\s*'
        r'[_\*\[]*\s*(\d{4}\.\d{2}\.\d{2})',
        contenido_md
    )
    if m:
        return m.group(1)
    # Fallback: cualquier XXXX.XX.XX en la seccion 7
    m_sec7 = re.search(r'##\s*7\..*?(?=##|\Z)', contenido_md, re.DOTALL)
    if m_sec7:
        m_code = re.search(r'\b(\d{4}\.\d{2}\.\d{2})\b', m_sec7.group(0))
        if m_code:
            return m_code.group(1)
    return None


def _extraer_denominacion(contenido_md: str) -> str:
    """Extrae la denominacion tecnica y comercial de la pregunta 1."""
    m = re.search(r'##\s*1\..*?(?=##|\Z)', contenido_md, re.DOTALL)
    if not m:
        return ""
    seccion = m.group(0)
    tecnica = re.search(r'[Dd]enominaci[oó]n\s+t[eé]cnica[^:]*:\s*([^\n_*]+)', seccion)
    comercial = re.search(r'[Dd]enominaci[oó]n\s+comercial[^:]*:\s*([^\n_*]+)', seccion)
    partes = []
    if tecnica:
        partes.append(tecnica.group(1).strip())
    if comercial:
        partes.append(comercial.group(1).strip())
    return " | ".join(partes)


def _cargar_fichas(forzar: bool = False) -> None:
    """Carga/recarga las fichas del directorio. Lazy + mtime-aware."""
    global _FICHAS_CACHE, _CACHE_MTIME

    if not os.path.isdir(_MERCEO_DIR):
        return

    # Detectar si el directorio cambio
    try:
        dir_mtime = os.path.getmtime(_MERCEO_DIR)
    except OSError:
        return

    if not forzar and _FICHAS_CACHE and dir_mtime == _CACHE_MTIME:
        return

    _FICHAS_CACHE.clear()
    for fname in os.listdir(_MERCEO_DIR):
        if not fname.endswith(".md"):
            continue
        ruta = os.path.join(_MERCEO_DIR, fname)
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                contenido = f.read()
        except Exception:
            continue
        slug = fname[:-3]
        # Keywords = slug (nombre del producto) + contenido del MD
        texto_indexable = slug.replace("-", " ") + " " + _extraer_denominacion(contenido)
        _FICHAS_CACHE[slug] = {
            "contenido": contenido,
            "keywords": _extraer_keywords(texto_indexable),
            "codigo": _extraer_codigo_de_ficha(contenido),
            "mtime": os.path.getmtime(ruta),
        }

    _CACHE_MTIME = dir_mtime


def buscar_ficha_para_consulta(consulta: str, umbral: float = 0.5) -> Optional[Tuple[str, dict, float]]:
    """
    Busca la ficha que mejor matchea la consulta.

    Args:
        consulta: texto de la pregunta del usuario
        umbral: score minimo (0.0-1.0) para considerar match. Default 0.5.

    Returns:
        (slug, ficha_dict, score) si match >= umbral, else None.
        score = |interseccion| / |keywords_consulta|
    """
    _cargar_fichas()
    if not _FICHAS_CACHE:
        return None

    kw_consulta = _extraer_keywords(consulta)
    if not kw_consulta:
        return None

    mejor_slug = None
    mejor_ficha = None
    mejor_score = 0.0

    for slug, ficha in _FICHAS_CACHE.items():
        kw_ficha = ficha["keywords"]
        if not kw_ficha:
            continue
        interseccion = kw_consulta & kw_ficha
        if not interseccion:
            continue
        # Score = cobertura de la consulta por la ficha
        score = len(interseccion) / max(len(kw_consulta), 1)
        if score > mejor_score:
            mejor_score = score
            mejor_slug = slug
            mejor_ficha = ficha

    if mejor_ficha and mejor_score >= umbral:
        return mejor_slug, mejor_ficha, mejor_score
    return None


def construir_respuesta_desde_ficha(
    slug: str,
    ficha: dict,
    score: float,
    consulta_original: str
) -> Optional[str]:
    """
    Construye respuesta final (texto al usuario) desde una ficha merceologica.
    Retorna None si la ficha no tiene codigo arancelario valido.

    El formato replica la estructura que produce ask_gemini.py para que el
    supervisor_interno pueda validarla de forma consistente.
    """
    codigo = ficha.get("codigo")
    if not codigo:
        return None

    # Verificar que el codigo existe en el arancel antes de devolverlo
    # (defensa extra contra fichas con codigos obsoletos)
    try:
        from supervisor_interno import verificar_codigo_en_fuentes
        existe, _msg = verificar_codigo_en_fuentes(codigo)
        if not existe:
            # Codigo en ficha es invalido — no usar
            return None
    except ImportError:
        pass  # Sin supervisor, proceder con cuidado

    denominacion = _extraer_denominacion(ficha["contenido"])
    nombre_producto = slug.replace("-", " ").title()

    respuesta = f"""**{codigo} — {denominacion or nombre_producto}**

Esta clasificacion proviene de la ficha merceologica previa del producto, registrada en la Biblioteca DGA.

---DATOS_CLASIFICACION---
SUBPARTIDA_NAC: {codigo}
PRODUCTO: {nombre_producto}
FUENTE: Ficha merceologica (cache merceologia_agent, score={score:.0%})
AUDITORIA: CONDICIONADA — respuesta desde cache merceologico, confirmar con supervisor DGA
---FIN_CLASIFICACION---

> Respuesta instantanea desde cache merceologico. Para desglose merceologico completo, consultar ficha `/merceologia/{slug}`.
"""
    return respuesta


def intentar_respuesta_cache(
    consulta: str,
    notebook_id: str,
    umbral: float = 0.5
) -> Optional[Tuple[str, dict]]:
    """
    Punto de entrada principal para el server.
    Intenta responder desde cache merceologico antes de llamar a Gemini.

    Returns:
        (respuesta_texto, metadata) si hay hit, else None.
        metadata = {"slug", "score", "codigo", "via": "merceologia_cache"}
    """
    # Solo para cuaderno de nomenclaturas (clasificacion arancelaria)
    if notebook_id != "biblioteca-de-nomenclaturas":
        return None

    if not consulta or len(consulta) < 10:
        return None

    t0 = time.time()
    match = buscar_ficha_para_consulta(consulta, umbral=umbral)
    if not match:
        return None

    slug, ficha, score = match
    respuesta = construir_respuesta_desde_ficha(slug, ficha, score, consulta)
    if not respuesta:
        return None

    elapsed_ms = int((time.time() - t0) * 1000)
    metadata = {
        "slug": slug,
        "score": round(score, 2),
        "codigo": ficha.get("codigo"),
        "via": "merceologia_cache",
        "elapsed_ms": elapsed_ms,
    }
    print(f"[MERCEOLOGIA_AGENT] HIT {slug} (score={score:.0%}, {elapsed_ms}ms) -> {ficha.get('codigo')}")
    return respuesta, metadata


def stats() -> dict:
    """Estadisticas del cache para debug/admin."""
    _cargar_fichas()
    return {
        "fichas_cargadas": len(_FICHAS_CACHE),
        "fichas_con_codigo": sum(1 for f in _FICHAS_CACHE.values() if f.get("codigo")),
        "directorio": _MERCEO_DIR,
        "directorio_existe": os.path.isdir(_MERCEO_DIR),
    }


if __name__ == "__main__":
    import sys
    _cargar_fichas()
    print(f"[MERCEOLOGIA_AGENT] {len(_FICHAS_CACHE)} fichas cargadas desde {_MERCEO_DIR}")
    for slug, ficha in _FICHAS_CACHE.items():
        print(f"  - {slug}: codigo={ficha.get('codigo')} keywords={len(ficha['keywords'])}")

    if len(sys.argv) > 1:
        consulta = " ".join(sys.argv[1:])
        print(f"\nConsulta test: {consulta!r}")
        resultado = intentar_respuesta_cache(consulta, "biblioteca-de-nomenclaturas")
        if resultado:
            respuesta, meta = resultado
            print(f"\nMETA: {meta}")
            print(f"\n{respuesta}")
        else:
            print("Sin match — Gemini procesaria esta consulta.")
