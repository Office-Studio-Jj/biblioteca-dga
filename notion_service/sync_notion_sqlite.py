"""
Sincronizador Notion (Capa 2) -> SQLite (Capa 1) via API REST.

Alternativa ligera a sync_notion_to_sqlite.py que usa requests directo
en vez de notion-client. Maneja paginacion, creacion dinamica de tablas
y registro de metadatos de sincronizacion.

Uso:
    from notion_service.sync_notion_sqlite import sincronizar_todo
    resultado = sincronizar_todo()
"""

import json
import os
import sqlite3
from datetime import datetime, timezone

import requests

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
_DEFAULT_DB_PATH = os.path.join(_ROOT, "capa1_sqlite", "arancel_rd.db")

# IDs de database_ids.json. Reemplazar con UUIDs reales si no estan en env.
_IDS_FILE = os.path.join(_HERE, "database_ids.json")


def _cargar_ids() -> dict:
    """Carga IDs desde env o desde database_ids.json como fallback."""
    ids = {}
    if os.path.exists(_IDS_FILE):
        with open(_IDS_FILE, "r", encoding="utf-8") as f:
            ids = json.load(f)
    return ids


# Configuracion de las 7 BDs: nombre interno -> {notion_env, tabla_sqlite, mapeo_campos}
# mapeo_campos: {columna_sqlite: (nombre_propiedad_notion, tipo_notion)}
_DATABASES_CONFIG = {
    "Jurisprudencia DGA": {
        "notion_env": "NOTION_DB_JURISPRUDENCIA",
        "tabla_sqlite": "notion_jurisprudencia",
        "mapeo_campos": {
            "titulo":     ("Titulo", "title"),
            "fecha":      ("Fecha", "date"),
            "tipo":       ("Tipo", "select"),
            "son":        ("SON", "rich_text"),
            "resumen":    ("Resumen", "rich_text"),
        },
    },
    "SOPs Aduanas": {
        "notion_env": "NOTION_DB_SOPS",
        "tabla_sqlite": "notion_sops",
        "mapeo_campos": {
            "titulo":     ("Titulo", "title"),
            "version":    ("Version", "rich_text"),
            "area":       ("Area", "select"),
            "base_legal": ("Base Legal", "rich_text"),
            "contenido":  ("Contenido", "rich_text"),
        },
    },
    "Fichas Merceologicas": {
        "notion_env": "NOTION_DB_MERCEOLOGIA",
        "tabla_sqlite": "notion_fichas_merceologicas",
        "mapeo_campos": {
            "producto":      ("Producto", "title"),
            "son_sugerido":  ("SON Sugerido", "rich_text"),
            "materia":       ("Materia", "rich_text"),
            "funcion":       ("Funcion", "rich_text"),
            "uso":           ("Uso", "rich_text"),
            "clasificacion": ("Clasificacion", "rich_text"),
            "dai_pct":       ("DAI%", "number"),
            "itbis_pct":     ("ITBIS%", "number"),
            "rgi":           ("RGI Aplicable", "select"),
            "capitulo_sa":   ("Capitulo SA", "rich_text"),
            "seccion_sa":    ("Seccion SA", "rich_text"),
            "notas_legales": ("Notas Legales", "rich_text"),
            "base_legal":    ("Base Legal", "rich_text"),
            "estado":        ("Estado", "select"),
            "fecha":         ("Fecha", "date"),
        },
    },
    "BD-Valoracion": {
        "notion_env": "NOTION_DB_VALORACION",
        "tabla_sqlite": "notion_valoracion",
        "mapeo_campos": {
            "titulo":      ("Titulo", "title"),
            "metodo_omc":  ("Metodo OMC", "select"),
            "base_legal":  ("Base Legal", "rich_text"),
            "descripcion": ("Descripcion", "rich_text"),
            "ejemplo":     ("Ejemplo", "rich_text"),
            "fecha":       ("Fecha", "date"),
        },
    },
    "BD-Regimenes": {
        "notion_env": "NOTION_DB_REGIMENES",
        "tabla_sqlite": "notion_regimenes",
        "mapeo_campos": {
            "titulo":       ("Titulo", "title"),
            "regimen":      ("Regimen", "select"),
            "arts_ley168":  ("Arts. Ley 168-21", "rich_text"),
            "trato_dai":    ("Tratamiento DAI", "rich_text"),
            "trato_itbis":  ("Tratamiento ITBIS", "rich_text"),
            "trato_isc":    ("Tratamiento ISC", "rich_text"),
            "descripcion":  ("Descripcion", "rich_text"),
            "fecha":        ("Fecha", "date"),
        },
    },
    "BD-VUCERD": {
        "notion_env": "NOTION_DB_VUCERD",
        "tabla_sqlite": "notion_vucerd",
        "mapeo_campos": {
            "titulo":       ("Titulo", "title"),
            "tipo_tramite": ("Tipo Tramite", "select"),
            "base_legal":   ("Base Legal", "rich_text"),
            "requisitos":   ("Requisitos", "rich_text"),
            "plazo_dias":   ("Plazo (dias)", "number"),
            "estado":       ("Estado", "select"),
            "fecha":        ("Fecha", "date"),
        },
    },
    "BD-Origen": {
        "notion_env": "NOTION_DB_ORIGEN",
        "tabla_sqlite": "notion_origen",
        "mapeo_campos": {
            "titulo":         ("Titulo", "title"),
            "tratado":        ("Tratado", "select"),
            "son":            ("SON", "rich_text"),
            "regla_origen":   ("Regla de Origen", "rich_text"),
            "preferencia_dai": ("Preferencia DAI", "rich_text"),
            "base_legal":     ("Base Legal", "rich_text"),
            "certificado":    ("Certificado", "rich_text"),
            "fecha":          ("Fecha", "date"),
        },
    },
}

# Mapeo tipo Notion -> tipo SQLite
_TIPO_SQL = {
    "title": "TEXT",
    "rich_text": "TEXT",
    "number": "REAL",
    "select": "TEXT",
    "multi_select": "TEXT",
    "date": "TEXT",
    "url": "TEXT",
}


def _extraer_valor_notion(prop: dict) -> str:
    """Extrae valor plano de una propiedad Notion. Maneja todos los tipos comunes."""
    tipo = prop.get("type", "")

    if tipo == "title":
        partes = prop.get("title", [])
        return "".join(p.get("plain_text", "") for p in partes)

    if tipo == "rich_text":
        partes = prop.get("rich_text", [])
        return "".join(p.get("plain_text", "") for p in partes)

    if tipo == "number":
        val = prop.get("number")
        return val  # puede ser None, int o float

    if tipo == "select":
        sel = prop.get("select")
        return sel["name"] if sel else ""

    if tipo == "multi_select":
        opciones = prop.get("multi_select", [])
        return ", ".join(o.get("name", "") for o in opciones)

    if tipo == "date":
        d = prop.get("date")
        return d["start"] if d else ""

    if tipo == "url":
        return prop.get("url") or ""

    # Tipo desconocido: devolver string vacio
    return ""


def _obtener_registros_notion(notion_db_id: str, token: str) -> list[dict]:
    """Obtiene todas las paginas de una BD Notion con paginacion."""
    url = f"{NOTION_API_BASE}/databases/{notion_db_id}/query"
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    registros = []
    cursor = None

    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor

        resp = requests.post(url, headers=headers, json=body, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for page in data.get("results", []):
            fila = {"_notion_id": page["id"], "_url": page.get("url", "")}
            for nombre_prop, prop_data in page.get("properties", {}).items():
                fila[nombre_prop] = _extraer_valor_notion(prop_data)
            registros.append(fila)

        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")

    return registros


def _sincronizar_bd(
    nombre: str,
    notion_db_id: str,
    tabla_sqlite: str,
    mapeo_campos: dict,
    con: sqlite3.Connection,
    token: str,
) -> dict:
    """Sincroniza una BD Notion a una tabla SQLite. Crea la tabla si no existe."""
    resultado = {"nombre": nombre, "tabla": tabla_sqlite, "registros": 0, "error": None}

    # Crear tabla dinamicamente
    columnas = ["notion_id TEXT PRIMARY KEY"]
    for col_sqlite, (_, tipo_notion) in mapeo_campos.items():
        tipo_sql = _TIPO_SQL.get(tipo_notion, "TEXT")
        columnas.append(f"{col_sqlite} {tipo_sql}")
    columnas.append("url_notion TEXT")
    columnas.append("synced_at TEXT DEFAULT (datetime('now'))")

    ddl = f"CREATE TABLE IF NOT EXISTS {tabla_sqlite} ({', '.join(columnas)})"
    con.execute(ddl)

    # Obtener registros de Notion
    registros = _obtener_registros_notion(notion_db_id, token)

    # Insertar en SQLite
    cols_insert = ["notion_id"] + list(mapeo_campos.keys()) + ["url_notion", "synced_at"]
    placeholders = ", ".join(["?"] * len(cols_insert))
    sql = f"INSERT OR REPLACE INTO {tabla_sqlite} ({', '.join(cols_insert)}) VALUES ({placeholders})"

    ahora = datetime.now(timezone.utc).isoformat()
    for reg in registros:
        valores = [reg["_notion_id"]]
        for col_sqlite, (nombre_notion, _) in mapeo_campos.items():
            valores.append(reg.get(nombre_notion, ""))
        valores.append(reg.get("_url", ""))
        valores.append(ahora)
        con.execute(sql, valores)

    con.commit()
    resultado["registros"] = len(registros)
    return resultado


def _resolver_notion_id(nombre_env: str, ids_json: dict) -> str:
    """Busca el ID de la BD primero en env, luego en database_ids.json."""
    valor = os.environ.get(nombre_env, "")
    if valor:
        return valor
    return ids_json.get(nombre_env, "")


def sincronizar_todo(notion_token: str = None, db_path: str = None) -> dict:
    """
    Punto de entrada principal. Sincroniza las 7 BDs Notion a SQLite.

    Args:
        notion_token: Token API Notion. Si None, lee NOTION_API_KEY del env.
        db_path: Ruta a arancel_rd.db. Si None, usa capa1_sqlite/arancel_rd.db.

    Returns:
        {tablas_sincronizadas, registros_totales, errores, log}
    """
    token = notion_token or os.environ.get("NOTION_API_KEY", "")
    if not token:
        return {
            "tablas_sincronizadas": 0,
            "registros_totales": 0,
            "errores": ["NOTION_API_KEY no configurada"],
            "log": [],
        }

    db = db_path or _DEFAULT_DB_PATH
    ids_json = _cargar_ids()
    con = sqlite3.connect(db)
    con.execute("PRAGMA journal_mode=WAL")

    # Tabla de metadatos de sync
    con.execute("""
        CREATE TABLE IF NOT EXISTS notion_sync_meta (
            bd_nombre TEXT PRIMARY KEY,
            ultimo_sync TEXT,
            registros INTEGER,
            estado TEXT
        )
    """)

    resultado = {
        "tablas_sincronizadas": 0,
        "registros_totales": 0,
        "errores": [],
        "log": [],
    }
    ahora = datetime.now(timezone.utc).isoformat()

    for nombre, config in _DATABASES_CONFIG.items():
        notion_db_id = _resolver_notion_id(config["notion_env"], ids_json)
        ts = datetime.now().strftime("%H:%M:%S")

        if not notion_db_id:
            msg = f"[{ts}] {nombre}: sin ID configurado, saltando"
            resultado["log"].append(msg)
            continue

        try:
            r = _sincronizar_bd(
                nombre=nombre,
                notion_db_id=notion_db_id,
                tabla_sqlite=config["tabla_sqlite"],
                mapeo_campos=config["mapeo_campos"],
                con=con,
                token=token,
            )
            resultado["tablas_sincronizadas"] += 1
            resultado["registros_totales"] += r["registros"]
            msg = f"[{ts}] {nombre}: {r['registros']} registros sincronizados"
            resultado["log"].append(msg)

            # Registrar en meta
            con.execute(
                "INSERT OR REPLACE INTO notion_sync_meta VALUES (?,?,?,?)",
                (nombre, ahora, r["registros"], "ok"),
            )
            con.commit()

        except requests.exceptions.HTTPError as e:
            # BD no existe en Notion o sin permisos: skip
            status = e.response.status_code if e.response is not None else 0
            msg = f"[{ts}] {nombre}: HTTP {status} — BD no accesible, saltando"
            resultado["log"].append(msg)
            resultado["errores"].append(f"{nombre}: HTTP {status}")
            con.execute(
                "INSERT OR REPLACE INTO notion_sync_meta VALUES (?,?,?,?)",
                (nombre, ahora, 0, f"error_http_{status}"),
            )
            con.commit()

        except Exception as e:
            msg = f"[{ts}] {nombre}: error — {e}"
            resultado["log"].append(msg)
            resultado["errores"].append(f"{nombre}: {e}")
            con.execute(
                "INSERT OR REPLACE INTO notion_sync_meta VALUES (?,?,?,?)",
                (nombre, ahora, 0, f"error: {str(e)[:100]}"),
            )
            con.commit()

    con.close()
    return resultado


if __name__ == "__main__":
    r = sincronizar_todo()
    print(json.dumps(r, indent=2, ensure_ascii=False))
