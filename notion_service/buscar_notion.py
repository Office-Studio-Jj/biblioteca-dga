"""
buscar_notion.py
Segunda fuente automática: busca en Notion DBs relevantes al notebook_id.
Se llama en paralelo a la consulta principal — timeout 5s, nunca bloquea.
"""
import json
import os
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

TOKEN = os.getenv("NOTION_API_KEY", "")

# notebook_id → BD(s) a consultar
_NB_TO_DBS = {
    "biblioteca-de-nomenclaturas":                       ["fichas_merceologicas"],
    "biblioteca-legal-y-procedimiento-dga":              ["jurisprudencia_dga"],
    "biblioteca-para-valoracion-dga":                    ["bd_valoracion"],
    "biblioteca-guia-integral-de-regimenes-y-subastas":  ["bd_regimenes"],
    "biblioteca-para-aforo-dga":                         ["sops_aduanas"],
    "biblioteca-procedimiento-vucerd":                   ["bd_vucerd"],
    "biblioteca-de-normas-y-origen-dga":                 ["bd_origen_drcafta"],
    "guia-maestra-comercio-exterior":                    [
        "fichas_merceologicas", "jurisprudencia_dga", "sops_aduanas"
    ],
}

_DB_IDS = {
    "fichas_merceologicas": "34c35f1c-d8ea-8190-9772-e0e3fefd8513",
    "jurisprudencia_dga":   "34c35f1c-d8ea-81d1-a487-d2d46d65d9b0",
    "sops_aduanas":         "34c35f1c-d8ea-81da-8666-df9b5403bc66",
    "bd_valoracion":        "a29f968b-8976-4d39-86c3-55041130969d",
    "bd_regimenes":         "6f5a3d75-f636-42cd-8639-b44d565cdff8",
    "bd_vucerd":            "4857355c-e95c-4b14-abe3-9e6f0efaad34",
    "bd_origen_drcafta":    "df5f1b0b-3cda-420d-8f54-8bf86ffc166d",
}

_DB_LABELS = {
    "fichas_merceologicas": "Fichas Merceológicas",
    "jurisprudencia_dga":   "Jurisprudencia DGA",
    "sops_aduanas":         "SOPs Aduanas",
    "bd_valoracion":        "Valoración Aduanera",
    "bd_regimenes":         "Regímenes Aduaneros",
    "bd_vucerd":            "VUCERD",
    "bd_origen_drcafta":    "Normas y Origen DR-CAFTA",
}


def _query_db(db_id: str, db_key: str, query: str, max_results: int = 3) -> list:
    """Busca en una BD de Notion. Devuelve lista de dicts con titulo/resumen/url/bd."""
    if not TOKEN:
        return []
    body = json.dumps({
        "query": query,
        "filter": {"value": "page", "property": "object"},
        "page_size": max_results,
    }).encode()
    req = urllib.request.Request(
        "https://api.notion.com/v1/search",
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
    except Exception:
        return []

    results = []
    for page in data.get("results", []):
        props = page.get("properties", {})

        # Extraer título
        titulo = ""
        for pv in props.values():
            if pv.get("type") == "title":
                titulo = "".join(
                    t.get("text", {}).get("content", "")
                    for t in pv.get("title", [])
                )
                break
        if not titulo:
            continue

        # Extraer primer resumen disponible
        resumen = ""
        for pn, pv in props.items():
            if pv.get("type") == "rich_text":
                resumen = "".join(
                    t.get("text", {}).get("content", "")
                    for t in pv.get("rich_text", [])
                )[:250]
                if resumen:
                    break

        # Extraer URL real si la página tiene propiedad URL (ej: VUCERD)
        url_real = ""
        for pv in props.values():
            if pv.get("type") == "url" and pv.get("url"):
                url_real = pv["url"]
                break

        results.append({
            "titulo":  titulo,
            "resumen": resumen,
            "url":     url_real or f"https://notion.so/{page['id'].replace('-', '')}",
            "url_externa": url_real,
            "bd":      _DB_LABELS.get(db_key, db_key),
        })
    return results


def buscar(query: str, notebook_id: str, timeout: float = 5.0) -> list:
    """
    Punto de entrada. Busca en Notion las BDs relevantes al notebook_id.
    Devuelve lista de fuentes (máx 5). Nunca lanza excepción.
    Si el token no está configurado o tarda más de `timeout` segundos, devuelve [].
    """
    if not TOKEN or not query:
        return []

    dbs = _NB_TO_DBS.get(notebook_id, [])
    if not dbs:
        # fallback: buscar en todas
        dbs = list(_DB_IDS.keys())

    def _run():
        todos = []
        for db_key in dbs:
            db_id = _DB_IDS.get(db_key)
            if db_id:
                todos.extend(_query_db(db_id, db_key, query, max_results=3))
        # deduplicar por url, limitar a 5
        seen = set()
        uniq = []
        for r in todos:
            if r["url"] not in seen:
                seen.add(r["url"])
                uniq.append(r)
            if len(uniq) >= 5:
                break
        return uniq

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_run)
            return fut.result(timeout=timeout)
    except (FutureTimeout, Exception):
        return []
