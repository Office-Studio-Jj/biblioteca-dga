"""
Bootstrap Capa 2 — Crea las 7 bases de datos en Notion bajo la pagina padre.
Se ejecuta UNA SOLA VEZ por BD nueva. Retorna los IDs para configurar en Railway.

BDs originales (2026-04-23): Jurisprudencia DGA, SOPs Aduanas, Fichas Merceologicas
BDs agregadas (2026-05-04, Informe CEO Diagnostico): BD-Valoracion, BD-Regimenes,
    BD-VUCERD, BD-Origen
Schema Fichas Merceologicas ampliado con 8 campos (DAI%, ITBIS%, RGI, Cap SA, Sec SA,
    Notas Legales, Base Legal, Estado, Fecha).
"""
import json
import os
import sys
import urllib.request

NOTION_API = "https://api.notion.com/v1/databases"
NOTION_VERSION = "2022-06-28"
PARENT_PAGE_ID = "34c35f1c-d8ea-80ed-97d8-f3943240e7b7"
TOKEN = os.environ.get("NOTION_API_KEY", "")

DATABASES = [
    {
        "env": "NOTION_DB_JURISPRUDENCIA",
        "title": "Jurisprudencia DGA",
        "icon": "⚖️",
        "properties": {
            "Título":   {"title": {}},
            "Fecha":    {"date": {}},
            "Tipo":     {"select": {"options": [
                {"name": "Resolución DGA", "color": "blue"},
                {"name": "Sentencia TC",    "color": "purple"},
                {"name": "Consulta vinculante", "color": "green"},
                {"name": "Dictamen",        "color": "orange"},
            ]}},
            "SON":      {"rich_text": {}},
            "Resumen":  {"rich_text": {}},
        },
    },
    {
        "env": "NOTION_DB_SOPS",
        "title": "SOPs Aduanas",
        "icon": "📋",
        "properties": {
            "Título":      {"title": {}},
            "Versión":     {"rich_text": {}},
            "Área":        {"select": {"options": [
                {"name": "Clasificación",     "color": "blue"},
                {"name": "Valoración",        "color": "green"},
                {"name": "Régimen suspensivo","color": "yellow"},
                {"name": "Origen",            "color": "purple"},
                {"name": "Despacho",          "color": "red"},
            ]}},
            "Base Legal":  {"rich_text": {}},
            "Contenido":   {"rich_text": {}},
        },
    },
    {
        "env": "NOTION_DB_MERCEOLOGIA",
        "title": "Fichas Merceológicas",
        "icon": "🏷️",
        "properties": {
            "Producto":       {"title": {}},
            "SON Sugerido":   {"rich_text": {}},
            "Materia":        {"rich_text": {}},
            "Función":        {"rich_text": {}},
            "Uso":            {"rich_text": {}},
            "Clasificación":  {"rich_text": {}},
            # Campos adicionales requeridos (Informe CEO Diagnóstico 04-05-2026)
            "DAI%":           {"number": {"format": "percent"}},
            "ITBIS%":         {"number": {"format": "percent"}},
            "RGI Aplicable":  {"select": {"options": [
                {"name": "RGI 1", "color": "blue"},
                {"name": "RGI 2", "color": "green"},
                {"name": "RGI 3", "color": "yellow"},
                {"name": "RGI 4", "color": "orange"},
                {"name": "RGI 5", "color": "pink"},
                {"name": "RGI 6", "color": "purple"},
            ]}},
            "Capítulo SA":    {"rich_text": {}},
            "Sección SA":     {"rich_text": {}},
            "Notas Legales":  {"rich_text": {}},
            "Base Legal":     {"rich_text": {}},
            "Estado":         {"select": {"options": [
                {"name": "Borrador",  "color": "gray"},
                {"name": "Revisado",  "color": "yellow"},
                {"name": "Publicado", "color": "green"},
            ]}},
            "Fecha":          {"date": {}},
        },
    },
    # ── 4 BDs faltantes (Informe CEO Diagnóstico 04-05-2026) ────────────
    {
        "env": "NOTION_DB_VALORACION",
        "title": "BD-Valoración Aduanera",
        "icon": "💰",
        "properties": {
            "Título":          {"title": {}},
            "Método OMC":      {"select": {"options": [
                {"name": "Método 1 — Valor de transacción",       "color": "blue"},
                {"name": "Método 2 — Mercancías idénticas",        "color": "green"},
                {"name": "Método 3 — Mercancías similares",        "color": "yellow"},
                {"name": "Método 4 — Precio unitario de venta",    "color": "orange"},
                {"name": "Método 5 — Valor reconstruido",          "color": "pink"},
                {"name": "Método 6 — Último recurso",              "color": "red"},
            ]}},
            "Base Legal":      {"rich_text": {}},
            "Descripción":     {"rich_text": {}},
            "Ejemplo":         {"rich_text": {}},
            "Fecha":           {"date": {}},
        },
    },
    {
        "env": "NOTION_DB_REGIMENES",
        "title": "BD-Regímenes Aduaneros",
        "icon": "🔄",
        "properties": {
            "Título":          {"title": {}},
            "Régimen":         {"select": {"options": [
                {"name": "Importación definitiva",  "color": "blue"},
                {"name": "Admisión temporal",        "color": "green"},
                {"name": "Reimportación",            "color": "yellow"},
                {"name": "Tránsito aduanero",        "color": "orange"},
                {"name": "Zona franca",              "color": "purple"},
                {"name": "Drawback",                 "color": "pink"},
                {"name": "Exportación definitiva",   "color": "red"},
                {"name": "DR-CAFTA preferencial",    "color": "gray"},
            ]}},
            "Arts. Ley 168-21": {"rich_text": {}},
            "Tratamiento DAI":  {"rich_text": {}},
            "Tratamiento ITBIS":{"rich_text": {}},
            "Tratamiento ISC":  {"rich_text": {}},
            "Descripción":      {"rich_text": {}},
            "Fecha":            {"date": {}},
        },
    },
    {
        "env": "NOTION_DB_VUCERD",
        "title": "BD-VUCERD Trámites Electrónicos",
        "icon": "💻",
        "properties": {
            "Título":          {"title": {}},
            "Tipo Trámite":    {"select": {"options": [
                {"name": "Importación",   "color": "blue"},
                {"name": "Exportación",   "color": "green"},
                {"name": "Tránsito",      "color": "yellow"},
                {"name": "Zona Franca",   "color": "purple"},
                {"name": "Consulta",      "color": "gray"},
            ]}},
            "Base Legal":      {"rich_text": {}},
            "Requisitos":      {"rich_text": {}},
            "Plazo (días)":    {"number": {"format": "number"}},
            "Estado":          {"select": {"options": [
                {"name": "Activo",     "color": "green"},
                {"name": "Suspendido", "color": "red"},
                {"name": "En revisión","color": "yellow"},
            ]}},
            "Fecha":           {"date": {}},
        },
    },
    {
        "env": "NOTION_DB_ORIGEN",
        "title": "BD-Normas y Origen DR-CAFTA",
        "icon": "🌎",
        "properties": {
            "Título":          {"title": {}},
            "Tratado":         {"select": {"options": [
                {"name": "DR-CAFTA",    "color": "blue"},
                {"name": "CARICOM",     "color": "green"},
                {"name": "SGP",         "color": "yellow"},
                {"name": "General",     "color": "gray"},
            ]}},
            "SON":             {"rich_text": {}},
            "Regla de Origen": {"rich_text": {}},
            "Preferencia DAI": {"rich_text": {}},
            "Base Legal":      {"rich_text": {}},
            "Certificado":     {"rich_text": {}},
            "Fecha":           {"date": {}},
        },
    },
]


def crear_db(db_spec: dict) -> dict:
    body = {
        "parent": {"type": "page_id", "page_id": PARENT_PAGE_ID},
        "icon":   {"type": "emoji", "emoji": db_spec["icon"]},
        "title":  [{"type": "text", "text": {"content": db_spec["title"]}}],
        "properties": db_spec["properties"],
    }
    req = urllib.request.Request(
        NOTION_API,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization":   f"Bearer {TOKEN}",
            "Notion-Version":  NOTION_VERSION,
            "Content-Type":    "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        return {"object": "error", "status": e.code, "body": err_body}


def main():
    if not TOKEN:
        print("ERROR: NOTION_API_KEY no configurada en env")
        sys.exit(1)
    print(f"Creando {len(DATABASES)} bases de datos bajo pagina {PARENT_PAGE_ID[:8]}...")
    ids = {}
    for spec in DATABASES:
        print(f"  → {spec['title']}...", end=" ", flush=True)
        r = crear_db(spec)
        if r.get("object") == "error":
            print(f"ERROR {r.get('status')}: {r.get('body', '')[:200]}")
            continue
        db_id = r.get("id", "")
        ids[spec["env"]] = db_id
        print(f"OK id={db_id}")
    print("\n" + "="*60)
    print("VARIABLES PARA RAILWAY:")
    print("="*60)
    for k, v in ids.items():
        print(f"{k}={v}")
    print("="*60)
    # Guardar para referencia
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database_ids.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(ids, f, indent=2)
    print(f"\nIDs guardados en: {out}")


if __name__ == "__main__":
    main()
