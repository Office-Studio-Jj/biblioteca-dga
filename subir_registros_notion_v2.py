#!/usr/bin/env python3
"""
subir_registros_notion_v2.py
Sube los CSVs generados a las 7 BDs de Notion usando el schema real verificado.
Token: NOTION_API_KEY en .env o variable de entorno.
"""
import csv
import json
import os
import urllib.request
import urllib.error
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
CSV_DIR = os.path.join(_HERE, "csv")

TOKEN = os.getenv("NOTION_API_KEY", "")

# IDs reales verificados via API
DB_IDS = {
    "fichas_merceologicas": "34c35f1c-d8ea-8190-9772-e0e3fefd8513",
    "jurisprudencia_dga":   "34c35f1c-d8ea-81d1-a487-d2d46d65d9b0",
    "sops_aduanas":         "34c35f1c-d8ea-81da-8666-df9b5403bc66",
    "bd_valoracion":        "a29f968b-8976-4d39-86c3-55041130969d",
    "bd_regimenes":         "6f5a3d75-f636-42cd-8639-b44d565cdff8",
    "bd_vucerd":            "4857355c-e95c-4b14-abe3-9e6f0efaad34",
    "bd_origen_drcafta":    "df5f1b0b-3cda-420d-8f54-8bf86ffc166d",
}


def _rt(texto: str) -> dict:
    """Crea propiedad rich_text para Notion (max 2000 chars)."""
    return {"rich_text": [{"text": {"content": str(texto)[:2000]}}]}


def _title(texto: str) -> dict:
    return {"title": [{"text": {"content": str(texto)[:255]}}]}


def _select(valor: str) -> dict:
    return {"select": {"name": str(valor)[:100]}} if valor else {"select": None}


def _date(valor: str) -> dict:
    try:
        d = valor[:10] if valor else None
        return {"date": {"start": d}} if d else {"date": None}
    except Exception:
        return {"date": None}


def _url(valor: str) -> dict:
    """Propiedad URL de Notion. Si esta vacio devuelve None (omitir la prop)."""
    v = str(valor).strip() if valor else ""
    return {"url": v} if v and v.startswith("http") else {"url": None}


def _inject_url(props: dict, row: dict) -> dict:
    """Inyecta campo URL en props si el CSV tiene columna 'url' con valor valido."""
    url_val = row.get("url", row.get("URL", row.get("enlace", ""))).strip()
    if url_val and url_val.startswith("http"):
        props["URL"] = _url(url_val)
    return props


def _crear_pagina(db_id: str, props: dict) -> bool:
    """POST a /v1/pages. Devuelve True si tuvo exito."""
    body = json.dumps({"parent": {"database_id": db_id}, "properties": props}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.notion.com/v1/pages",
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=20)
        return True
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", errors="replace")[:200]
        print(f"    HTTP {e.code}: {msg}")
        return False


def subir_fichas_merceologicas():
    """fichas_merceologicas_5_productos.csv → BD Fichas Merceológicas."""
    path = os.path.join(CSV_DIR, "fichas_merceologicas_5_productos.csv")
    if not os.path.exists(path):
        print("  SKIP: fichas_merceologicas_5_productos.csv no encontrado")
        return 0, 0
    ok = err = 0
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            props = _inject_url({
                "Producto":      _title(row.get("Producto", "")),
                "Clasificación": _rt(row.get("Clasificacion", "")),
                "SON Sugerido":  _rt(row.get("SON_Sugerido", "")),
                "Materia":       _rt(row.get("Materia", "")),
                "Función":       _rt(row.get("Funcion", "")),
                "Uso":           _rt(row.get("Uso", "")),
            }, row)
            if _crear_pagina(DB_IDS["fichas_merceologicas"], props):
                ok += 1
            else:
                err += 1
    return ok, err


def subir_sops_aduanas():
    """cuaderno_1_aforo_registros.csv → BD SOPs Aduanas."""
    path = os.path.join(CSV_DIR, "cuaderno_1_aforo_registros.csv")
    if not os.path.exists(path):
        return 0, 0
    ok = err = 0
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            props = _inject_url({
                "Título":    _title(row.get("titulo", row.get("Título", ""))),
                "Contenido": _rt(row.get("contenido_resumen", "")),
                "Versión":   _rt(row.get("fecha_procesamiento", "")[:10]),
            }, row)
            if _crear_pagina(DB_IDS["sops_aduanas"], props):
                ok += 1
            else:
                err += 1
    return ok, err


def subir_jurisprudencia():
    """cuaderno_2_legal_registros.csv → BD Jurisprudencia DGA."""
    path = os.path.join(CSV_DIR, "cuaderno_2_legal_registros.csv")
    if not os.path.exists(path):
        return 0, 0
    ok = err = 0
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            props = _inject_url({
                "Título":  _title(row.get("titulo", "")),
                "Resumen": _rt(row.get("contenido_resumen", "")),
                "Fecha":   _date(row.get("fecha_procesamiento", "")),
            }, row)
            if _crear_pagina(DB_IDS["jurisprudencia_dga"], props):
                ok += 1
            else:
                err += 1
    return ok, err


def subir_regimenes():
    """cuaderno_3_regimenes_registros.csv → BD-Regímenes Aduaneros."""
    path = os.path.join(CSV_DIR, "cuaderno_3_regimenes_registros.csv")
    if not os.path.exists(path):
        return 0, 0
    ok = err = 0
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            props = _inject_url({
                "Título":        _title(row.get("titulo", "")),
                "Descripción":   _rt(row.get("contenido_resumen", "")),
                "Arts. Ley 168-21": _rt(row.get("base_legal", "")),
                "Fecha":         _date(row.get("fecha_procesamiento", "")),
            }, row)
            if _crear_pagina(DB_IDS["bd_regimenes"], props):
                ok += 1
            else:
                err += 1
    return ok, err


def subir_nomenclaturas():
    """cuaderno_4_nomenclaturas_registros.csv → BD Fichas Merceológicas (documentos)."""
    path = os.path.join(CSV_DIR, "cuaderno_4_nomenclaturas_registros.csv")
    if not os.path.exists(path):
        return 0, 0
    ok = err = 0
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            props = _inject_url({
                "Producto":      _title(row.get("titulo", "")),
                "Clasificación": _rt(row.get("tipo_documento", "")),
                "SON Sugerido":  _rt("Ver documento"),
                "Uso":           _rt(row.get("base_legal", "")),
                "Función":       _rt(row.get("contenido_resumen", "")),
            }, row)
            if _crear_pagina(DB_IDS["fichas_merceologicas"], props):
                ok += 1
            else:
                err += 1
    return ok, err


def subir_origen():
    """cuaderno_5_origen_registros.csv → BD-Normas y Origen DR-CAFTA."""
    path = os.path.join(CSV_DIR, "cuaderno_5_origen_registros.csv")
    if not os.path.exists(path):
        return 0, 0
    ok = err = 0
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            props = _inject_url({
                "Título":         _title(row.get("titulo", "")),
                "Regla de Origen":_rt(row.get("contenido_resumen", "")),
                "Base Legal":     _rt(row.get("base_legal", "")),
                "Fecha":          _date(row.get("fecha_procesamiento", "")),
            }, row)
            if _crear_pagina(DB_IDS["bd_origen_drcafta"], props):
                ok += 1
            else:
                err += 1
    return ok, err


def subir_vucerd():
    """cuaderno_6_vucerd_registros.csv → BD-VUCERD."""
    path = os.path.join(CSV_DIR, "cuaderno_6_vucerd_registros.csv")
    if not os.path.exists(path):
        return 0, 0
    ok = err = 0
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            props = _inject_url({
                "Título":      _title(row.get("titulo", "")),
                "Requisitos":  _rt(row.get("contenido_resumen", "")),
                "Base Legal":  _rt(row.get("base_legal", "")),
                "Fecha":       _date(row.get("fecha_procesamiento", "")),
            }, row)
            if _crear_pagina(DB_IDS["bd_vucerd"], props):
                ok += 1
            else:
                err += 1
    return ok, err


def subir_valoracion():
    """cuaderno_7_valoracion_registros.csv → BD-Valoración Aduanera."""
    path = os.path.join(CSV_DIR, "cuaderno_7_valoracion_registros.csv")
    if not os.path.exists(path):
        return 0, 0
    ok = err = 0
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            props = _inject_url({
                "Título":      _title(row.get("titulo", "")),
                "Descripción": _rt(row.get("contenido_resumen", "")),
                "Base Legal":  _rt(row.get("base_legal", "")),
                "Fecha":       _date(row.get("fecha_procesamiento", "")),
            }, row)
            if _crear_pagina(DB_IDS["bd_valoracion"], props):
                ok += 1
            else:
                err += 1
    return ok, err


if __name__ == "__main__":
    if not TOKEN:
        print("ERROR: NOTION_API_KEY no configurada.")
        print("Ejecutar: NOTION_API_KEY=secret_xxx python subir_registros_notion_v2.py")
        raise SystemExit(1)

    print(f"\n{'='*60}")
    print(f"  SUBIR REGISTROS A NOTION — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    tareas = [
        ("5 Fichas Merceologicas", subir_fichas_merceologicas),
        ("Cuaderno 1 — SOPs Aduanas", subir_sops_aduanas),
        ("Cuaderno 2 — Jurisprudencia DGA", subir_jurisprudencia),
        ("Cuaderno 3 — Regimenes Aduaneros", subir_regimenes),
        ("Cuaderno 4 — Nomenclaturas (docs)", subir_nomenclaturas),
        ("Cuaderno 5 — Origen DR-CAFTA", subir_origen),
        ("Cuaderno 6 — VUCERD", subir_vucerd),
        ("Cuaderno 7 — Valoracion Aduanera", subir_valoracion),
    ]

    total_ok = total_err = 0
    for nombre, fn in tareas:
        print(f"Subiendo {nombre}...")
        ok, err = fn()
        print(f"  Resultado: {ok} creadas, {err} errores\n")
        total_ok += ok
        total_err += err

    print(f"{'='*60}")
    print(f"  TOTAL: {total_ok} paginas creadas | {total_err} errores")
    print(f"{'='*60}\n")
