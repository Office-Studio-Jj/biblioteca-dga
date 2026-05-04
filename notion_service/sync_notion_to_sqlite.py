"""
Capa 2 — Notion CMS Sync (Two-Brain System RD)
Lee las 7 BDs Notion y las escribe en SQLite para disponibilidad offline y FTS5.

BDs originales: Jurisprudencia DGA, SOPs Aduanas, Fichas Merceologicas
BDs nuevas (CEO 04-05-2026): BD-Valoracion, BD-Regimenes, BD-VUCERD, BD-Origen

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

# IDs de bases de datos Notion — originales + 4 nuevas (CEO 04-05-2026)
NOTION_DB_IDS: dict[str, str] = {
    "jurisprudencia":       os.environ.get("NOTION_DB_JURISPRUDENCIA", ""),
    "sops":                 os.environ.get("NOTION_DB_SOPS", ""),
    "fichas_merceologicas": os.environ.get("NOTION_DB_MERCEOLOGIA", ""),
    "notas_legales":        os.environ.get("NOTION_DB_NOTAS_LEGALES", ""),
    "mapa_exclusiones":     os.environ.get("NOTION_DB_MAPA_EXCLUSIONES", ""),
    # Nuevas 4 BDs (Informe CEO Diagnóstico 04-05-2026)
    "valoracion":           os.environ.get("NOTION_DB_VALORACION", ""),
    "regimenes":            os.environ.get("NOTION_DB_REGIMENES", ""),
    "vucerd":               os.environ.get("NOTION_DB_VUCERD", ""),
    "origen":               os.environ.get("NOTION_DB_ORIGEN", ""),
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
    notion_id    TEXT PRIMARY KEY,
    producto     TEXT,
    son_sugerido TEXT,
    materia      TEXT,
    funcion      TEXT,
    uso          TEXT,
    clasificacion TEXT,
    dai_pct      REAL,
    itbis_pct    REAL,
    rgi          TEXT,
    capitulo_sa  TEXT,
    seccion_sa   TEXT,
    notas_legales TEXT,
    base_legal   TEXT,
    estado       TEXT,
    fecha        TEXT,
    url_notion   TEXT,
    synced_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notion_valoracion (
    notion_id   TEXT PRIMARY KEY,
    titulo      TEXT,
    metodo_omc  TEXT,
    base_legal  TEXT,
    descripcion TEXT,
    ejemplo     TEXT,
    fecha       TEXT,
    url_notion  TEXT,
    synced_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notion_regimenes (
    notion_id      TEXT PRIMARY KEY,
    titulo         TEXT,
    regimen        TEXT,
    arts_ley168    TEXT,
    trato_dai      TEXT,
    trato_itbis    TEXT,
    trato_isc      TEXT,
    descripcion    TEXT,
    fecha          TEXT,
    url_notion     TEXT,
    synced_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notion_vucerd (
    notion_id   TEXT PRIMARY KEY,
    titulo      TEXT,
    tipo_tramite TEXT,
    base_legal  TEXT,
    requisitos  TEXT,
    plazo_dias  INTEGER,
    estado      TEXT,
    fecha       TEXT,
    url_notion  TEXT,
    synced_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notion_origen (
    notion_id     TEXT PRIMARY KEY,
    titulo        TEXT,
    tratado       TEXT,
    son           TEXT,
    regla_origen  TEXT,
    preferencia_dai TEXT,
    base_legal    TEXT,
    certificado   TEXT,
    fecha         TEXT,
    url_notion    TEXT,
    synced_at     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notion_notas_legales (
    notion_id       TEXT PRIMARY KEY,
    capitulo        TEXT,
    texto_completo  TEXT,
    fuente          TEXT DEFAULT 'Decreto 755-22',
    indexado_rag    INTEGER DEFAULT 1,
    url_notion      TEXT,
    synced_at       TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notion_mapa_exclusiones (
    notion_id           TEXT PRIMARY KEY,
    capitulo_excluye    TEXT,
    capitulo_incluye    TEXT,
    producto_patron     TEXT,
    texto_exclusion     TEXT,
    excepcion           TEXT,
    fuente              TEXT DEFAULT 'Decreto 755-22',
    url_notion          TEXT,
    synced_at           TEXT DEFAULT (datetime('now'))
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
        notion_id     = page["id"]
        producto      = _extract_text(props.get("Producto", {}).get("title", []))
        son_sugerido  = _extract_text(props.get("SON Sugerido", {}).get("rich_text", []))
        materia       = _extract_text(props.get("Materia", {}).get("rich_text", []))
        funcion       = _extract_text(props.get("Función", {}).get("rich_text", []))
        uso           = _extract_text(props.get("Uso", {}).get("rich_text", []))
        clasificacion = _extract_text(props.get("Clasificación", {}).get("rich_text", []))
        dai_pct       = props.get("DAI%", {}).get("number")
        itbis_pct     = props.get("ITBIS%", {}).get("number")
        rgi           = _extract_select(props.get("RGI Aplicable", {}).get("select", {}))
        capitulo_sa   = _extract_text(props.get("Capítulo SA", {}).get("rich_text", []))
        seccion_sa    = _extract_text(props.get("Sección SA", {}).get("rich_text", []))
        notas_legales = _extract_text(props.get("Notas Legales", {}).get("rich_text", []))
        base_legal    = _extract_text(props.get("Base Legal", {}).get("rich_text", []))
        estado        = _extract_select(props.get("Estado", {}).get("select", {}))
        fecha         = _extract_date(props.get("Fecha", {}).get("date", {}))
        url_notion    = f"https://notion.so/{notion_id.replace('-', '')}"
        if not dry_run:
            con.execute(
                """INSERT OR REPLACE INTO notion_fichas_merceologicas
                   (notion_id, producto, son_sugerido, materia, funcion, uso, clasificacion,
                    dai_pct, itbis_pct, rgi, capitulo_sa, seccion_sa, notas_legales,
                    base_legal, estado, fecha, url_notion, synced_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))""",
                (notion_id, producto, son_sugerido, materia, funcion, uso, clasificacion,
                 dai_pct, itbis_pct, rgi, capitulo_sa, seccion_sa, notas_legales,
                 base_legal, estado, fecha, url_notion)
            )
            con.execute(
                "INSERT INTO notion_fts(tipo, titulo, contenido) VALUES (?,?,?)",
                ("merceologia", producto, f"{materia} {funcion} {uso} {notas_legales}")
            )
        count += 1
    return count


def _sync_valoracion(notion, con: sqlite3.Connection, db_id: str, dry_run=False) -> int:
    if not db_id:
        print("[NOTION-SYNC] NOTION_DB_VALORACION no configurada — skip")
        return 0
    count = 0
    ds_id = _resolver_data_source(notion, db_id)
    for page in _query_paginado(notion, ds_id):
        props = page.get("properties", {})
        notion_id   = page["id"]
        titulo      = _extract_text(props.get("Título", {}).get("title", []))
        metodo_omc  = _extract_select(props.get("Método OMC", {}).get("select", {}))
        base_legal  = _extract_text(props.get("Base Legal", {}).get("rich_text", []))
        descripcion = _extract_text(props.get("Descripción", {}).get("rich_text", []))
        ejemplo     = _extract_text(props.get("Ejemplo", {}).get("rich_text", []))
        fecha       = _extract_date(props.get("Fecha", {}).get("date", {}))
        url_notion  = f"https://notion.so/{notion_id.replace('-', '')}"
        if not dry_run:
            con.execute(
                """INSERT OR REPLACE INTO notion_valoracion
                   (notion_id, titulo, metodo_omc, base_legal, descripcion, ejemplo, fecha, url_notion, synced_at)
                   VALUES (?,?,?,?,?,?,?,?,datetime('now'))""",
                (notion_id, titulo, metodo_omc, base_legal, descripcion, ejemplo, fecha, url_notion)
            )
            con.execute(
                "INSERT INTO notion_fts(tipo, titulo, contenido) VALUES (?,?,?)",
                ("valoracion", titulo, f"{metodo_omc} {descripcion}")
            )
        count += 1
    return count


def _sync_regimenes(notion, con: sqlite3.Connection, db_id: str, dry_run=False) -> int:
    if not db_id:
        print("[NOTION-SYNC] NOTION_DB_REGIMENES no configurada — skip")
        return 0
    count = 0
    ds_id = _resolver_data_source(notion, db_id)
    for page in _query_paginado(notion, ds_id):
        props = page.get("properties", {})
        notion_id   = page["id"]
        titulo      = _extract_text(props.get("Título", {}).get("title", []))
        regimen     = _extract_select(props.get("Régimen", {}).get("select", {}))
        arts_ley168 = _extract_text(props.get("Arts. Ley 168-21", {}).get("rich_text", []))
        trato_dai   = _extract_text(props.get("Tratamiento DAI", {}).get("rich_text", []))
        trato_itbis = _extract_text(props.get("Tratamiento ITBIS", {}).get("rich_text", []))
        trato_isc   = _extract_text(props.get("Tratamiento ISC", {}).get("rich_text", []))
        descripcion = _extract_text(props.get("Descripción", {}).get("rich_text", []))
        fecha       = _extract_date(props.get("Fecha", {}).get("date", {}))
        url_notion  = f"https://notion.so/{notion_id.replace('-', '')}"
        if not dry_run:
            con.execute(
                """INSERT OR REPLACE INTO notion_regimenes
                   (notion_id, titulo, regimen, arts_ley168, trato_dai, trato_itbis, trato_isc,
                    descripcion, fecha, url_notion, synced_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))""",
                (notion_id, titulo, regimen, arts_ley168, trato_dai, trato_itbis, trato_isc,
                 descripcion, fecha, url_notion)
            )
            con.execute(
                "INSERT INTO notion_fts(tipo, titulo, contenido) VALUES (?,?,?)",
                ("regimen", titulo, f"{regimen} {descripcion} Ley 168-21 Arts. {arts_ley168}")
            )
        count += 1
    return count


def _sync_vucerd(notion, con: sqlite3.Connection, db_id: str, dry_run=False) -> int:
    if not db_id:
        print("[NOTION-SYNC] NOTION_DB_VUCERD no configurada — skip")
        return 0
    count = 0
    ds_id = _resolver_data_source(notion, db_id)
    for page in _query_paginado(notion, ds_id):
        props = page.get("properties", {})
        notion_id    = page["id"]
        titulo       = _extract_text(props.get("Título", {}).get("title", []))
        tipo_tramite = _extract_select(props.get("Tipo Trámite", {}).get("select", {}))
        base_legal   = _extract_text(props.get("Base Legal", {}).get("rich_text", []))
        requisitos   = _extract_text(props.get("Requisitos", {}).get("rich_text", []))
        plazo        = props.get("Plazo (días)", {}).get("number")
        estado       = _extract_select(props.get("Estado", {}).get("select", {}))
        fecha        = _extract_date(props.get("Fecha", {}).get("date", {}))
        url_notion   = f"https://notion.so/{notion_id.replace('-', '')}"
        if not dry_run:
            con.execute(
                """INSERT OR REPLACE INTO notion_vucerd
                   (notion_id, titulo, tipo_tramite, base_legal, requisitos, plazo_dias,
                    estado, fecha, url_notion, synced_at)
                   VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))""",
                (notion_id, titulo, tipo_tramite, base_legal, requisitos, plazo,
                 estado, fecha, url_notion)
            )
            con.execute(
                "INSERT INTO notion_fts(tipo, titulo, contenido) VALUES (?,?,?)",
                ("vucerd", titulo, f"{tipo_tramite} {requisitos}")
            )
        count += 1
    return count


def _sync_origen(notion, con: sqlite3.Connection, db_id: str, dry_run=False) -> int:
    if not db_id:
        print("[NOTION-SYNC] NOTION_DB_ORIGEN no configurada — skip")
        return 0
    count = 0
    ds_id = _resolver_data_source(notion, db_id)
    for page in _query_paginado(notion, ds_id):
        props = page.get("properties", {})
        notion_id      = page["id"]
        titulo         = _extract_text(props.get("Título", {}).get("title", []))
        tratado        = _extract_select(props.get("Tratado", {}).get("select", {}))
        son            = _extract_text(props.get("SON", {}).get("rich_text", []))
        regla_origen   = _extract_text(props.get("Regla de Origen", {}).get("rich_text", []))
        preferencia    = _extract_text(props.get("Preferencia DAI", {}).get("rich_text", []))
        base_legal     = _extract_text(props.get("Base Legal", {}).get("rich_text", []))
        certificado    = _extract_text(props.get("Certificado", {}).get("rich_text", []))
        fecha          = _extract_date(props.get("Fecha", {}).get("date", {}))
        url_notion     = f"https://notion.so/{notion_id.replace('-', '')}"
        if not dry_run:
            con.execute(
                """INSERT OR REPLACE INTO notion_origen
                   (notion_id, titulo, tratado, son, regla_origen, preferencia_dai,
                    base_legal, certificado, fecha, url_notion, synced_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))""",
                (notion_id, titulo, tratado, son, regla_origen, preferencia,
                 base_legal, certificado, fecha, url_notion)
            )
            con.execute(
                "INSERT INTO notion_fts(tipo, titulo, contenido) VALUES (?,?,?)",
                ("origen", titulo, f"{tratado} SON {son} {regla_origen}")
            )
        count += 1
    return count


def _sync_notas_legales(notion, con: sqlite3.Connection, db_id: str, dry_run=False) -> int:
    """BUG-005 fix: sincroniza Notas Legales como TEXTO PLANO, no links/PDFs."""
    if not db_id:
        print("[NOTION-SYNC] NOTION_DB_NOTAS_LEGALES no configurada — skip")
        return 0
    count = 0
    ds_id = _resolver_data_source(notion, db_id)
    for page in _query_paginado(notion, ds_id):
        props = page.get("properties", {})
        notion_id      = page["id"]
        capitulo       = _extract_text(props.get("Capitulo", {}).get("rich_text", []))
        if not capitulo:
            capitulo   = _extract_text(props.get("Capitulo", {}).get("title", []))
        texto_completo = _extract_text(props.get("Texto_Completo", {}).get("rich_text", []))
        fuente         = _extract_text(props.get("Fuente", {}).get("rich_text", [])) or "Decreto 755-22"
        indexado       = props.get("Indexado_RAG", {}).get("checkbox", True)
        url_notion     = f"https://notion.so/{notion_id.replace('-', '')}"

        if not texto_completo or len(texto_completo) < 10:
            print(f"[NOTION-SYNC] AVISO: Cap. {capitulo} sin Texto_Completo — pagina solo tiene link/PDF. Saltar.")
            continue

        if not dry_run:
            con.execute(
                """INSERT OR REPLACE INTO notion_notas_legales
                   (notion_id, capitulo, texto_completo, fuente, indexado_rag, url_notion, synced_at)
                   VALUES (?,?,?,?,?,?,datetime('now'))""",
                (notion_id, capitulo, texto_completo, fuente, 1 if indexado else 0, url_notion)
            )
            con.execute(
                "INSERT INTO notion_fts(tipo, titulo, contenido) VALUES (?,?,?)",
                ("nota_legal", f"Cap. {capitulo}", texto_completo)
            )
        count += 1
    return count


def _sync_mapa_exclusiones(notion, con: sqlite3.Connection, db_id: str, dry_run=False) -> int:
    if not db_id:
        print("[NOTION-SYNC] NOTION_DB_MAPA_EXCLUSIONES no configurada — skip")
        return 0
    count = 0
    ds_id = _resolver_data_source(notion, db_id)
    for page in _query_paginado(notion, ds_id):
        props = page.get("properties", {})
        notion_id         = page["id"]
        cap_excluye       = _extract_text(props.get("Capitulo_Excluye", {}).get("rich_text", []))
        cap_incluye       = _extract_text(props.get("Capitulo_Incluye", {}).get("rich_text", []))
        producto_patron   = _extract_text(props.get("Producto_Patron", {}).get("rich_text", []))
        texto_exclusion   = _extract_text(props.get("Texto_Exclusion", {}).get("rich_text", []))
        excepcion         = _extract_text(props.get("Excepcion", {}).get("rich_text", []))
        fuente            = _extract_text(props.get("Fuente", {}).get("rich_text", [])) or "Decreto 755-22"
        url_notion        = f"https://notion.so/{notion_id.replace('-', '')}"
        if not dry_run:
            con.execute(
                """INSERT OR REPLACE INTO notion_mapa_exclusiones
                   (notion_id, capitulo_excluye, capitulo_incluye, producto_patron,
                    texto_exclusion, excepcion, fuente, url_notion, synced_at)
                   VALUES (?,?,?,?,?,?,?,?,datetime('now'))""",
                (notion_id, cap_excluye, cap_incluye, producto_patron,
                 texto_exclusion, excepcion, fuente, url_notion)
            )
        count += 1
    return count


def notion_rag_query(query: str) -> str:
    """
    BUG-005 fix: query RAG que retorna TEXTO PLANO, nunca URLs ni file objects.
    Busca en notion_notas_legales y notion_fts. Retorna texto o string vacio.
    """
    if not os.path.exists(DB_PATH):
        return ""
    try:
        con = sqlite3.connect(DB_PATH)
        # Buscar por capitulo exacto
        import re
        m_cap = re.search(r'(?:Cap\.?\s*|Capitulo\s*)(\d{1,2})', query, re.IGNORECASE)
        if m_cap:
            cap = m_cap.group(1).zfill(2)
            cur = con.execute(
                "SELECT texto_completo FROM notion_notas_legales WHERE capitulo = ? AND indexado_rag = 1",
                (cap,)
            )
            row = cur.fetchone()
            if row and row[0]:
                con.close()
                return row[0]

        # Fallback: FTS5 sobre notion_fts
        palabras = re.findall(r'\b[a-záéíóúñ]{3,}\b', query.lower())
        if palabras:
            fts_query = " OR ".join(palabras[:5])
            cur = con.execute(
                "SELECT contenido FROM notion_fts WHERE notion_fts MATCH ? LIMIT 3",
                (fts_query,)
            )
            rows = cur.fetchall()
            if rows:
                con.close()
                return "\n---\n".join(r[0] for r in rows if r[0])

        con.close()
    except Exception as e:
        print(f"[NOTION-RAG] Error en query: {e}")
    return ""


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

    n_juri   = _sync_jurisprudencia(notion, con, NOTION_DB_IDS["jurisprudencia"],       dry_run)
    n_sops   = _sync_sops(notion,           con, NOTION_DB_IDS["sops"],                 dry_run)
    n_fichas = _sync_fichas(notion,         con, NOTION_DB_IDS["fichas_merceologicas"], dry_run)
    n_notas  = _sync_notas_legales(notion,  con, NOTION_DB_IDS["notas_legales"],        dry_run)
    n_excl   = _sync_mapa_exclusiones(notion, con, NOTION_DB_IDS["mapa_exclusiones"],   dry_run)
    # BDs nuevas (CEO 04-05-2026)
    n_val    = _sync_valoracion(notion, con, NOTION_DB_IDS["valoracion"], dry_run)
    n_reg    = _sync_regimenes(notion,  con, NOTION_DB_IDS["regimenes"],  dry_run)
    n_vuc    = _sync_vucerd(notion,     con, NOTION_DB_IDS["vucerd"],     dry_run)
    n_orig   = _sync_origen(notion,     con, NOTION_DB_IDS["origen"],     dry_run)

    if not dry_run:
        con.execute(
            "INSERT OR REPLACE INTO build_meta VALUES('notion_sync_ts',?)",
            (datetime.now().isoformat(),)
        )
        con.commit()
    con.close()

    elapsed = __import__("time").time() - t0
    total = n_juri + n_sops + n_fichas + n_notas + n_excl + n_val + n_reg + n_vuc + n_orig
    return {
        "dry_run":           dry_run,
        "jurisprudencia":    n_juri,
        "sops":              n_sops,
        "fichas":            n_fichas,
        "notas_legales":     n_notas,
        "mapa_exclusiones":  n_excl,
        "valoracion":        n_val,
        "regimenes":         n_reg,
        "vucerd":            n_vuc,
        "origen":            n_orig,
        "total":             total,
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
