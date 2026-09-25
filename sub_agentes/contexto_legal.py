"""Contexto legal de la biblioteca-dga para el árbitro Claude.

Reúne, por capítulo candidato, lo que exige la RGI 1 (Decreto 755-22): texto de las partidas
y Notas de Sección y de Capítulo; más las RGI completas, las aperturas nacionales (SON de
8 dígitos con DAI/ITBIS/ISC) y la base legal registrada. Todo sale de fuentes locales
extraídas del Arancel 7ma Enmienda (Decreto 36-22) con pdfplumber.
"""

import json
import os
import re
import sqlite3
import unicodedata
from functools import lru_cache

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_RAIZ, "capa1_sqlite", "arancel_rd.db")
_PARTIDAS = os.path.join(_RAIZ, "notebooklm_skill", "data", "fuentes_nomenclatura", "partidas_arancel.json")


def _sin_acentos(t):
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


@lru_cache(maxsize=1)
def partidas():
    try:
        with open(_PARTIDAS, encoding="utf-8") as f:
            return json.load(f)["partidas"]
    except (OSError, ValueError, KeyError):
        return {}


@lru_cache(maxsize=1)
def rgi_texto():
    try:
        con = sqlite3.connect(_DB)
        filas = con.execute("SELECT numero, texto FROM rgi ORDER BY numero").fetchall()
        con.close()
    except sqlite3.Error:
        return ""
    return "\n".join(f"RGI {n}: {t}" for n, t in filas)


@lru_cache(maxsize=1)
def base_legal():
    try:
        con = sqlite3.connect(_DB)
        filas = con.execute("SELECT id, titulo FROM base_legal").fetchall()
        con.close()
    except sqlite3.Error:
        return ""
    return "; ".join(f"{i} ({t})" for i, t in filas)


def partidas_por_texto(terminos, maximo=8):
    """Partidas cuyo TEXTO oficial coincide con los términos (RGI 1). [(partida, puntaje)]."""
    raices = {_sin_acentos(w)[:5] for t in terminos for w in re.findall(r"[a-záéíóúñü]+", t.lower()) if len(w) >= 4}
    if not raices:
        return []
    puntajes = []
    for codigo, texto in partidas().items():
        palabras = {_sin_acentos(w)[:5] for w in re.findall(r"[a-záéíóúñü]+", texto.lower()) if len(w) >= 4}
        p = len(raices & palabras)
        if p:
            puntajes.append((codigo, p))
    return sorted(puntajes, key=lambda x: (-x[1], x[0]))[:maximo]


def _notas_capitulo(cap):
    try:
        from sub_agentes.lector_notas_arancel import leer_notas_capitulo, formatear_notas_gemini
        return formatear_notas_gemini(leer_notas_capitulo(cap))
    except Exception as e:
        return f"(Notas del Capítulo {cap} no disponibles: {e})"


def _aperturas(partida, limite=25):
    p4 = partida.replace(".", "")
    try:
        con = sqlite3.connect(_DB)
        filas = con.execute(
            "SELECT son, descripcion, gravamen, itbis, isc FROM codigos WHERE REPLACE(son,'.','') LIKE ? "
            "ORDER BY son LIMIT ?", (p4 + "%", limite)).fetchall()
        con.close()
    except sqlite3.Error:
        return []
    return [f"    {s} {d[:110]} | DAI {g}% ITBIS {i}% ISC {c}" for s, d, g, i, c in filas]


def construir(capitulos, partidas_destacadas=(), max_partidas_por_cap=60):
    """Bloque de texto con RGI, Notas, partidas y aperturas nacionales para los capítulos dados."""
    out = ["== REGLAS GENERALES DE INTERPRETACIÓN (RGI, Decreto 755-22) ==", rgi_texto(),
           f"== BASE LEGAL REGISTRADA EN LA BIBLIOTECA == {base_legal()}"]
    todas = partidas()
    for cap in capitulos:
        out.append(f"\n== CAPÍTULO {cap} ==")
        out.append(_notas_capitulo(cap))
        del_cap = [(k, v) for k, v in todas.items() if k.startswith(cap + ".")]
        out.append("Partidas (texto oficial):")
        out += [f"  {k} {v}" for k, v in del_cap[:max_partidas_por_cap]]
    destacadas = [p for p in partidas_destacadas if p[:2] in capitulos]
    if destacadas:
        out.append("\n== APERTURAS NACIONALES (SON 8 dígitos) DE LAS PARTIDAS MÁS PROBABLES ==")
        for p in destacadas[:4]:
            out.append(f"  {p} {todas.get(p, '')[:120]}")
            out += _aperturas(p)
    return "\n".join(out)
