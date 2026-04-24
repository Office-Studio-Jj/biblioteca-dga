"""
Capa 2 — Notion CMS Sync (Two-Brain System RD)
Lee jurisprudencia, SOPs y fichas merceológicas desde Notion y los escribe
en SQLite para disponibilidad offline y búsqueda FTS5.

Uso:
  python notion_service/sync_notion_to_sqlite.py          # sync completo
  python notion_service/sync_notion_to_sqlite.py --dry-run # solo reporta

Requiere: NOTION_API_KEY en env + notion-client (pip install notion-client)
"""
import json
import os
import sqlite3
import sys
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

DB_PATH = os.path.join(_ROOT, "capa1_sqlite", "arancel_rd.db")

# IDs de bases de datos Notion — rellenar cuando estén disponibles
NOTION_DB_IDS: dict[str, str] = {
    "jurisprudencia":       os.environ.get("NOTION_DB_JURISPRUDENCIA", ""),
    "sops":                 os.environ.get("NOTION_DB_SOPS", ""),
    "fichas_merceologicas": os.environ.get("NOTION_DB_MERCEOLOGIA", ""),
}


# ── Schema Capa 2 ────────────────────────────────────────────────────────────

_SCHEMA_CAPA2 = """
CREATE TABLE IF NOT EXISTS notion_jurisprudencia (
    notion_id   TEXT PRIMARY KEY,
    titulo      TEXT,
    fecha       TEXT,
    tipo        TEXT,
    son         TEXT,
    resumen     TEXT,
    url_notion  TEXT,
    synced_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notion_sops (
    notion_id   TEXT PRIMARY KEY,
    titulo      TEXT,
    version     TEXT,
    area        TEXT,
    contenido   TEXT,
    url_notion  TEXT,
    synced_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notion_fichas_merceologicas (
    notion_id   TEXT PRIMARY KEY,
    producto    TEXT,
    son_sugerido TEXT,
    materia     TEXT,
    funcion     TEXT,
    uso         TEXT,
    clasificacion TEXT,
    url_notion  TEXT,
    synced_at   TEXT DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS notion_fts USING fts5(
    tipo,
    titulo,
    contenido,
    tokenize='unicode61 remove_diacritics 1'
);
"""


def _get_notion_client():
    api_key = os.environ.get("NOTION_API_KEY", "")
    if not api_key:
        raise EnvironmentError("NOTION_API_KEY no configurada en entorno.")
    try:
        from notion_client import Client
        return Client(auth=api_key)
    except ImportError:
        raise ImportError(
            "notion-client no instalado. Agrega 'notion-client>=2.2.1' a requirements.txt"
        )


def _ensure_schema(con: sqlite3.Connection):
    con.executescript(_SCHEMA_CAPA2)
    con.commit()


def _extract_text(rich_text: list) -> str:
    return "".join(t.get("plain_text", "") for t in (rich_text or []))


def _extract_date(date_prop) -> str:
    if date_prop and date_prop.get("start"):
        return date_prop["start"]
    return ""


def _extract_select(select_prop) -> str:
    if select_prop and select_prop.get("name"):
        return select_prop["name"]
    return ""


def _resolver_data_source(notion, db_id: str) -> str:
    """
    Notion API 2025-09-03+: los databases tienen data_sources dentro.
    Retrieve database para obtener el data_source_id (usado por .query()).
    """
    try:
        db = notion.databases.retrieve(database_id=db_id)
        ds_list = db.get("data_sources", [])
        if ds_list:
            return ds_list[0]["id"]
    except Exception as e:
        print(f"[NOTION-SYNC] retrieve {db_id[:8]} fallo: {e}")
    # Fallback: en APIs antiguas el propio database_id funciona como data_source
    return db_id


def _query_paginado(notion, ds_id: str):
    """Yield paginas consultando un data_source."""
    cursor = None
    while True:
        kwargs = {"data_source_id": ds_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        response = notion.data_sources.query(**kwargs)
        for page in response.get("results", []):
            yield page
        if not response.get("has_more"):
            return
        cursor = response.get("next_cursor")


# ── Sincronizadores por tipo ─────────────────────────────────────────────────

def _sync_jurisprudencia(notion, con: sqlite3.Connection, db_id: str, dry_run=False) -> int:
    if not db_id:
        print("[NOTION-SYNC] NOTION_DB_JURISPRUDENCIA no configurada — skip")
        return 0
    count = 0
    ds_id = _resolver_data_source(notion, db_id)
    for page in _query_paginado(notion, ds_id):
        props = page.get("properties", {})
        notion_id   = page["id"]
        titulo      = _extract_text(props.get("Título", {}).get("title", []))
        fecha       = _extract_date(props.get("Fecha", {}).get("date", {}))
        tipo        = _extract_select(props.get("Tipo", {}).get("select", {}))
        son         = _extract_text(props.get("SON", {}).get("rich_text", []))
        resumen     = _extract_text(props.get("Resumen", {}).get("rich_text", []))
        url_notion  = f"https://notion.so/{notion_id.replace('-', '')}"
        if not dry_run:
            con.execute(
                """INSERT OR REPLACE INTO notion_jurisprudencia
                   (notion_id, titulo, fecha, tipo, son, resumen, url_notion, synced_at)
                   VALUES (?,?,?,?,?,?,?,datetime('now'))""",
                (notion_id, titulo, fecha, tipo, son, resumen, url_notion)
            )
            con.execute(
                "INSERT INTO notion_fts(tipo, titulo, contenido) VALUES (?,?,?)",
                ("jurisprudencia", titulo, resumen)
            )
        count += 1
    return count


def _sync_sops(notion, con: sqlite3.Connection, db_id: str, dry_run=False) -> int:
    if not db_id:
        print("[NOTION-SYNC] NOTION_DB_SOPS no configurada — skip")
        return 0
    count = 0
    ds_id = _resolver_data_source(notion, db_id)
    for page in _query_paginado(notion, ds_id):
        props = page.get("properties", {})
        notion_id  = page["id"]
        titulo     = _extract_text(props.get("Título", {}).get("title", []))
        version    = _extract_text(props.get("Versión", {}).get("rich_text", []))
        area       = _extract_select(props.get("Área", {}).get("select", {}))
        contenido  = _extract_text(props.get("Contenido", {}).get("rich_text", []))
        url_notion = f"https://notion.so/{notion_id.replace('-', '')}"
        if not dry_run:
            con.execute(
                """INSERT OR REPLACE INTO notion_sops
                   (notion_id, titulo, version, area, contenido, url_notion, synced_at)
                   VALUES (?,?,?,?,?,?,datetime('now'))""",
                (notion_id, titulo, version, area, contenido, url_notion)
            )
            con.execute(
                "INSERT INTO notion_fts(tipo, titulo, contenido) VALUES (?,?,?)",
                ("sop", titulo, contenido)
            )
        count += 1
    return count


def _sync_fichas(notion, con: sqlite3.Connection, db_id: str, dry_run=False) -> int:
    if not db_id:
        print("[NOTION-SYNC] NOTION_DB_MERCEOLOGIA no configurada — skip")
        return 0
    count = 0
    ds_id = _resolver_data_source(notion, db_id)
    for page in _query_paginado(notion, ds_id):
        props = page.get("properties", {})
        notion_id    = page["id"]
        producto     = _extract_text(props.get("Producto", {}).get("title", []))
        son_sugerido = _extract_text(props.get("SON Sugerido", {}).get("rich_text", []))
        materia      = _extract_text(props.get("Materia", {}).get("rich_text", []))
        funcion      = _extract_text(props.get("Función", {}).get("rich_text", []))
        uso          = _extract_text(props.get("Uso", {}).get("rich_text", []))
        clasificacion = _extract_text(props.get("Clasificación", {}).get("rich_text", []))
        url_notion   = f"https://notion.so/{notion_id.replace('-', '')}"
        if not dry_run:
            con.execute(
                """INSERT OR REPLACE INTO notion_fichas_merceologicas
                   (notion_id, producto, son_sugerido, materia, funcion, uso, clasificacion, url_notion, synced_at)
                   VALUES (?,?,?,?,?,?,?,?,datetime('now'))""",
                (notion_id, producto, son_sugerido, materia, funcion, uso, clasificacion, url_notion)
            )
            con.execute(
                "INSERT INTO notion_fts(tipo, titulo, contenido) VALUES (?,?,?)",
                ("merceologia", producto, f"{materia} {funcion} {uso}")
            )
        count += 1
    return count


# ── Punto de entrada ─────────────────────────────────────────────────────────

def sync(dry_run=False) -> dict:
    t0 = __import__("time").time()
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(
            f"arancel_rd.db no encontrado en {DB_PATH}. "
            "Ejecuta: python capa1_sqlite/build_arancel_db.py"
        )

    notion = _get_notion_client()
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode=WAL")
    _ensure_schema(con)

    # Limpiar FTS antes de re-indexar (evita duplicados)
    if not dry_run:
        con.execute("DELETE FROM notion_fts")

    n_juri  = _sync_jurisprudencia(notion, con, NOTION_DB_IDS["jurisprudencia"],  dry_run)
    n_sops  = _sync_sops(notion,           con, NOTION_DB_IDS["sops"],            dry_run)
    n_fichas = _sync_fichas(notion,         con, NOTION_DB_IDS["fichas_merceologicas"], dry_run)

    if not dry_run:
        con.execute(
            "INSERT OR REPLACE INTO build_meta VALUES('notion_sync_ts',?)",
            (datetime.now().isoformat(),)
        )
        con.commit()
    con.close()

    elapsed = __import__("time").time() - t0
    return {
        "dry_run":           dry_run,
        "jurisprudencia":    n_juri,
        "sops":              n_sops,
        "fichas":            n_fichas,
        "total":             n_juri + n_sops + n_fichas,
        "elapsed_s":         round(elapsed, 2),
        "synced_at":         datetime.now().isoformat(),
    }


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    try:
        result = sync(dry_run=dry)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except EnvironmentError as e:
        print(f"[NOTION-SYNC] {e}")
        print("[NOTION-SYNC] Sin NOTION_API_KEY — Capa 2 offline. Capa 1 SQLite activa.")
        sys.exit(0)
    except ImportError as e:
        print(f"[NOTION-SYNC] {e}")
        sys.exit(1)
