#!/usr/bin/env python3
"""
Configurar CLOPAS automáticamente en Notion
Crea todas las propiedades necesarias
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_API_KEY", "")
CLOPAS_DB_ID = os.getenv("NOTION_DB_CLOPAS", "")

BASE_URL = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def crear_propiedad(db_id, nombre, tipo, opciones=None):
    """Crea una propiedad en la base de datos"""

    url = f"{BASE_URL}/databases/{db_id}"

    # Preparar la propiedad según el tipo
    if tipo == "select":
        propiedad = {
            "type": "select",
            "select": {
                "options": [
                    {"name": opt, "color": "default"}
                    for opt in opciones
                ] if opciones else []
            }
        }
    elif tipo == "multi_select":
        propiedad = {
            "type": "multi_select",
            "multi_select": {
                "options": [
                    {"name": opt, "color": "default"}
                    for opt in opciones
                ] if opciones else []
            }
        }
    elif tipo == "text":
        propiedad = {"type": "rich_text"}
    elif tipo == "date":
        propiedad = {"type": "date"}
    elif tipo == "url":
        propiedad = {"type": "url"}
    else:
        return False

    payload = {
        "properties": {
            nombre: propiedad
        }
    }

    try:
        response = requests.patch(url, json=payload, headers=HEADERS, timeout=30)
        if response.status_code in [200, 201]:
            print(f"✅ Propiedad '{nombre}' creada")
            return True
        else:
            print(f"⚠️ Error en '{nombre}': {response.status_code}")
            print(f"   Respuesta: {response.text[:200]}")
            return False
    except Exception as e:
        print(f"❌ Error al crear '{nombre}': {e}")
        return False

def renombrar_titulo(db_id):
    """gestor_clopas.py escribe en 'Title'; una BD nueva trae 'Name' o 'Nombre'."""
    try:
        r = requests.get(f"{BASE_URL}/databases/{db_id}", headers=HEADERS, timeout=30)
        if r.status_code != 200:
            print(f"ERROR leyendo la BD: {r.status_code} {r.text[:200]}")
            return False
        actual = next(k for k, v in r.json()["properties"].items() if v["type"] == "title")
        if actual == "Title":
            return True
        r = requests.patch(f"{BASE_URL}/databases/{db_id}", headers=HEADERS, timeout=30,
                           json={"properties": {actual: {"name": "Title"}}})
        print(f"Columna de título '{actual}' -> 'Title': {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        print(f"ERROR renombrando título: {e}")
        return False


PROPIEDADES = [
    ("Tipo", "select", ["Corrección", "Creación", "Error", "Feature", "Bug"]),
    ("Proyecto", "select", ["app-movil", "biblioteca-dga"]),
    ("Categoría", "select", ["Código", "Documentación", "BD", "UI/UX", "Seguridad", "Otra"]),
    ("Descripción", "text", None),
    ("Solución", "text", None),
    ("Código", "text", None),
    ("Fecha", "date", None),
    ("Estado", "select", ["Nuevo", "En Revisión", "Resuelto", "Descartado"]),
    ("Prioridad", "select", ["Crítica", "Alta", "Media", "Baja"]),
    ("Autor", "text", None),
    ("Impacto", "multi_select", ["Performance", "Seguridad", "Usabilidad", "BD", "API"]),
    ("Tags", "multi_select", None),
    ("Enlace GitHub", "url", None),
]


def main():
    if not NOTION_TOKEN:
        print("ERROR: NOTION_API_KEY no configurada en .env")
        return 1
    if not CLOPAS_DB_ID:
        print("ERROR: NOTION_DB_CLOPAS no configurada en .env")
        return 1

    print(f"Configurando CLOPAS en Notion (BD {CLOPAS_DB_ID})...")
    fallidas = [] if renombrar_titulo(CLOPAS_DB_ID) else ["Title"]
    for n, (nombre, tipo, opciones) in enumerate(PROPIEDADES, 1):
        print(f"[{n}/{len(PROPIEDADES)}] {nombre}")
        if not crear_propiedad(CLOPAS_DB_ID, nombre, tipo, opciones):
            fallidas.append(nombre)

    print()
    if fallidas:
        print(f"ERROR: {len(fallidas)} propiedades no se crearon: {', '.join(fallidas)}")
        print("Verificar que la integración de Notion tenga acceso a la BD CLOPAS")
        print("(en Notion: ... > Conexiones > agregar la integración).")
        return 1

    print(f"OK: CLOPAS configurada con {len(PROPIEDADES)} propiedades.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
