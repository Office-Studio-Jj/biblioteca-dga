"""
subir_registros_notion.py
Lee los CSVs generados por los scripts 1 y 2, y sube cada fila como
una página de Notion a la BD correspondiente (Capa 2).

Requiere: NOTION_API_KEY en variables de entorno.
Si no está configurada, imprime instrucciones y termina sin errores.

Base legal: Ley 168-21 Art. 10 (confidencialidad aduanera),
            Ley 172-13 (protección de datos personales).

Organización: AMGECO Automatización y Gestión SRL
"""

import csv
import io
import json
import os
import sys
import urllib.request
import urllib.error

# Forzar UTF-8 en stdout (Windows cp1252 no soporta algunos caracteres)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ── Config local ─────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_DIR  = os.path.join(BASE_DIR, "csv")

# Importar IDs de BDs desde config_db.py
try:
    sys.path.insert(0, BASE_DIR)
    from config_db import NOTION_DB_IDS
except ImportError:
    print("[ERROR] No se pudo importar config_db.py. Verificar ruta del proyecto.")
    sys.exit(1)

# ── Mapeo CSV -> BD Notion ─────────────────────────────────────────────────────
CSV_A_NOTION = {
    "cuaderno_1_aforo_registros.csv":         "sops_aduanas",
    "cuaderno_2_legal_registros.csv":         "jurisprudencia_dga",
    "cuaderno_3_regimenes_registros.csv":     "bd_regimenes",
    "cuaderno_4_nomenclaturas_registros.csv": "fichas_merceologicas",
    "cuaderno_5_origen_registros.csv":        "bd_origen_drcafta",
    "cuaderno_6_vucerd_registros.csv":        "bd_vucerd",
    "cuaderno_7_valoracion_registros.csv":    "bd_valoracion",
    "fichas_merceologicas_5_productos.csv":   "fichas_merceologicas",
}

NOTION_API_URL = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2022-06-28"


# ── Conversión fila CSV -> propiedades Notion ──────────────────────────────────
def _csv_a_notion_props(row_dict: dict, columnas_bd: list) -> dict:
    """
    Convierte un dict de fila CSV a formato de propiedades Notion.
    Usa tipo 'rich_text' para todos los campos salvo 'titulo'/'Producto'
    que se mapea al título de la página.

    Parámetros:
        row_dict   — fila leída del CSV (dict columna->valor)
        columnas_bd — lista de columnas disponibles (para filtrar)

    Retorna dict con estructura Notion properties.
    """
    props = {}
    campos_titulo = {"titulo", "Producto"}

    for col, val in row_dict.items():
        if col not in columnas_bd:
            continue
        valor_str = str(val).strip() if val else ""

        if col in campos_titulo:
            # Propiedad especial Name/title de Notion
            props["Name"] = {
                "title": [{"type": "text", "text": {"content": valor_str[:2000]}}]
            }
        else:
            props[col] = {
                "rich_text": [{"type": "text", "text": {"content": valor_str[:2000]}}]
            }

    # Si no hubo campo título, usar primer valor disponible
    if "Name" not in props and row_dict:
        primer_val = str(list(row_dict.values())[0])[:2000]
        props["Name"] = {
            "title": [{"type": "text", "text": {"content": primer_val}}]
        }

    return props


# ── Crear una página en Notion ────────────────────────────────────────────────
def _crear_pagina_notion(db_id: str, row_dict: dict, token: str) -> bool:
    """
    Crea una página en la BD Notion indicada con los datos del row_dict.

    Parámetros:
        db_id    — ID de la base de datos Notion destino
        row_dict — dict con columna->valor de la fila CSV
        token    — Notion API token (Bearer)

    Retorna True si la página se creó correctamente, False en caso de error.
    """
    columnas_bd = list(row_dict.keys())
    props       = _csv_a_notion_props(row_dict, columnas_bd)

    payload = json.dumps({
        "parent":     {"database_id": db_id},
        "properties": props,
    }).encode("utf-8")

    req = urllib.request.Request(
        NOTION_API_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization":   f"Bearer {token}",
            "Notion-Version":  NOTION_VERSION,
            "Content-Type":    "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as exc:
        cuerpo = exc.read().decode("utf-8", errors="replace")[:300]
        print(f"    [HTTP {exc.code}] {cuerpo}")
        return False
    except Exception as exc:
        print(f"    [ERROR red] {exc}")
        return False


# ── Función principal ─────────────────────────────────────────────────────────
def subir_todo(notion_token: str = None) -> dict:
    """
    Recorre todos los CSVs en CSV_DIR que estén en CSV_A_NOTION y sube
    cada fila a la BD Notion correspondiente.

    Parámetros:
        notion_token — token de la API de Notion; si None, lo lee de NOTION_API_KEY

    Retorna dict con resultados por CSV: {csv: {creadas, errores}}.
    """
    token = notion_token or os.environ.get("NOTION_API_KEY", "").strip()

    if not token:
        print("NOTION_API_KEY no configurada.")
        print("Para subir los registros, ejecutar:")
        print("  NOTION_API_KEY=secret_xxxx python subir_registros_notion.py")
        print()
        print("CSVs disponibles en:", CSV_DIR)
        for nombre_csv in sorted(CSV_A_NOTION.keys()):
            ruta = os.path.join(CSV_DIR, nombre_csv)
            if os.path.exists(ruta):
                print(f"  [OK] {nombre_csv}")
            else:
                print(f"  [X] {nombre_csv} (no generado aún)")
        return {}

    resultados = {}
    total_creadas = 0
    total_errores = 0

    for nombre_csv, bd_key in CSV_A_NOTION.items():
        ruta_csv = os.path.join(CSV_DIR, nombre_csv)

        if not os.path.exists(ruta_csv):
            print(f"[OMITIDO] {nombre_csv} — archivo no encontrado")
            continue

        db_id = NOTION_DB_IDS.get(bd_key)
        if not db_id:
            print(f"[OMITIDO] {nombre_csv} — BD '{bd_key}' no tiene ID en config_db.py")
            continue

        print(f"\nSubiendo {nombre_csv} -> {bd_key} ({db_id[:8]}...)")

        creadas = 0
        errores = 0

        with open(ruta_csv, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, fila in enumerate(reader, 1):
                ok = _crear_pagina_notion(db_id, fila, token)
                if ok:
                    creadas += 1
                    print(f"  [{i}] OK")
                else:
                    errores += 1
                    print(f"  [{i}] ERROR — fila: {str(fila)[:80]}")

        resultados[nombre_csv] = {"creadas": creadas, "errores": errores}
        total_creadas += creadas
        total_errores += errores
        print(f"  Resultado: {creadas} creadas, {errores} errores")

    print(f"\nTotal páginas creadas: {total_creadas} | Errores: {total_errores}")
    return resultados


if __name__ == "__main__":
    subir_todo()
