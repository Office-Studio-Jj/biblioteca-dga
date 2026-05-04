#!/usr/bin/env python3
"""
ORDEN 8 — Watcher de nuevos PDFs para autoalimentación futura.
Detecta PDFs adjuntados a Cuadernos en Notion y los procesa automáticamente.

IMPORTANTE: No activar hasta que Órdenes 1-6 estén completadas y verificadas.
Este script es la estructura lista para activar. Ver pipeline_v2.md.

Uso (cuando el CEO lo autorice):
    python watcher_nuevos_pdfs.py --test     # valida conexion sin procesar
    python watcher_nuevos_pdfs.py --run      # modo activo (polling cada 5 min)
"""
import json
import os
import sys
import time
from datetime import datetime

try:
    import requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

try:
    import pdfplumber
    _PDF_OK = True
except ImportError:
    _PDF_OK = False

_HERE = os.path.dirname(os.path.abspath(__file__))
_ESTADO_PATH = os.path.join(_HERE, "csv", "watcher_estado.json")

# IDs de las 7 BDs Notion (de config_db.py)
try:
    from config_db import NOTION_DB_IDS
except ImportError:
    NOTION_DB_IDS = {}

_POLL_INTERVAL_SEG = 300  # 5 minutos


def _cargar_estado() -> dict:
    """Carga estado de archivos ya procesados."""
    if os.path.exists(_ESTADO_PATH):
        with open(_ESTADO_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"procesados": [], "ultima_revision": None}


def _guardar_estado(estado: dict):
    os.makedirs(os.path.dirname(_ESTADO_PATH), exist_ok=True)
    with open(_ESTADO_PATH, "w", encoding="utf-8") as f:
        json.dump(estado, f, indent=2, ensure_ascii=False)


def _obtener_paginas_nuevas(db_id: str, token: str, ya_procesados: list) -> list:
    """Consulta Notion y devuelve páginas con adjuntos no procesadas."""
    if not _REQUESTS_OK:
        return []
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(
            f"https://api.notion.com/v1/databases/{db_id}/query",
            headers=headers,
            json={"filter": {"property": "Estado", "select": {"equals": "RECIBIDO"}}},
            timeout=15,
        )
        if resp.status_code != 200:
            return []
        pages = resp.json().get("results", [])
        return [p for p in pages if p["id"] not in ya_procesados]
    except Exception:
        return []


def _extraer_texto_pdf(ruta: str) -> str:
    """Extrae texto de un PDF local."""
    if not _PDF_OK:
        return ""
    try:
        texto = []
        with pdfplumber.open(ruta) as pdf:
            for page in pdf.pages[:10]:  # max 10 páginas
                t = page.extract_text()
                if t:
                    texto.append(t)
        return "\n".join(texto)[:3000]
    except Exception:
        return ""


def _actualizar_estado_notion(page_id: str, nuevo_estado: str, token: str):
    """Actualiza el estado de una página en Notion."""
    if not _REQUESTS_OK:
        return
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    try:
        requests.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=headers,
            json={"properties": {"Estado": {"select": {"name": nuevo_estado}}}},
            timeout=15,
        )
    except Exception:
        pass


def procesar_nuevos(token: str, test_mode: bool = False) -> dict:
    """
    Ciclo principal: detecta PDFs nuevos en Notion y los procesa.
    En test_mode solo valida conexión sin escribir nada.
    """
    estado = _cargar_estado()
    ya_procesados = estado.get("procesados", [])
    log = []
    total_nuevos = 0

    for nombre_bd, db_id in NOTION_DB_IDS.items():
        nuevas = _obtener_paginas_nuevas(db_id, token, ya_procesados)
        if not nuevas:
            continue
        total_nuevos += len(nuevas)
        for pagina in nuevas:
            page_id = pagina["id"]
            titulo = ""
            props = pagina.get("properties", {})
            for k, v in props.items():
                if v.get("type") == "title":
                    partes = v.get("title", [])
                    titulo = "".join(p.get("plain_text", "") for p in partes)
                    break

            if not test_mode:
                _actualizar_estado_notion(page_id, "EN PROCESAMIENTO", token)
                ya_procesados.append(page_id)

            log.append({
                "bd": nombre_bd,
                "page_id": page_id,
                "titulo": titulo,
                "procesado": not test_mode,
                "ts": datetime.now().isoformat(),
            })

    if not test_mode and log:
        estado["procesados"] = ya_procesados
        estado["ultima_revision"] = datetime.now().isoformat()
        _guardar_estado(estado)

    return {"total_nuevos": total_nuevos, "test_mode": test_mode, "log": log}


if __name__ == "__main__":
    # Verificar dependencias
    if not _REQUESTS_OK:
        print("ERROR: pip install requests")
        sys.exit(1)

    token = os.getenv("NOTION_API_KEY", "")
    if not token:
        print("WATCHER: No está activo.")
        print("Para activar: NOTION_API_KEY=tu_key python watcher_nuevos_pdfs.py --run")
        print("Para probar:  NOTION_API_KEY=tu_key python watcher_nuevos_pdfs.py --test")
        sys.exit(0)

    test_mode = "--test" in sys.argv
    run_mode = "--run" in sys.argv

    if test_mode:
        print("Modo TEST — verificando conexion...")
        r = procesar_nuevos(token, test_mode=True)
        print(f"BDs accesibles: {len(NOTION_DB_IDS)}")
        print(f"Páginas RECIBIDO encontradas: {r['total_nuevos']}")
        sys.exit(0)

    if run_mode:
        print(f"[WATCHER] Iniciando. Poll cada {_POLL_INTERVAL_SEG//60} min.")
        print("Ctrl+C para detener.")
        while True:
            r = procesar_nuevos(token)
            if r["total_nuevos"]:
                print(f"[{datetime.now().isoformat()}] Procesados: {r['total_nuevos']}")
            time.sleep(_POLL_INTERVAL_SEG)

    print("Usar --test o --run")
