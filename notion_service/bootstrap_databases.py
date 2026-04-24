"""
Bootstrap Capa 2 — Crea las 3 bases de datos en Notion bajo la pagina padre.
Se ejecuta UNA SOLA VEZ. Retorna los IDs para configurar en Railway.
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
            "Título":    {"title": {}},
            "Versión":   {"rich_text": {}},
            "Área":      {"select": {"options": [
                {"name": "Clasificación",     "color": "blue"},
                {"name": "Valoración",        "color": "green"},
                {"name": "Régimen suspensivo","color": "yellow"},
                {"name": "Origen",            "color": "purple"},
                {"name": "Despacho",          "color": "red"},
            ]}},
            "Contenido": {"rich_text": {}},
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
