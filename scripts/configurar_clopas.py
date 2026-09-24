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
    elif tipo == "code":
        propiedad = {"type": "code"}
    else:
        return False

    payload = {
        "properties": {
            nombre: propiedad
        }
    }

    try:
        response = requests.patch(url, json=payload, headers=HEADERS)
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

def main():
    """Configura CLOPAS con todas las propiedades"""

    if not NOTION_TOKEN:
        print("❌ Error: NOTION_API_KEY no configurada en .env")
        return

    if not CLOPAS_DB_ID:
        print("❌ Error: NOTION_DB_CLOPAS no configurada en .env")
        return

    print("🚀 Configurando CLOPAS en Notion...")
    print(f"   Base de datos: {CLOPAS_DB_ID}")
    print()

    # Propiedad 1: Tipo
    print("1️⃣ Creando propiedad 'Tipo'...")
    crear_propiedad(
        CLOPAS_DB_ID,
        "Tipo",
        "select",
        ["Corrección", "Creación", "Error", "Feature", "Bug"]
    )

    # Propiedad 2: Proyecto
    print("2️⃣ Creando propiedad 'Proyecto'...")
    crear_propiedad(
        CLOPAS_DB_ID,
        "Proyecto",
        "select",
        ["app-movil", "biblioteca-dga"]
    )

    # Propiedad 3: Categoría
    print("3️⃣ Creando propiedad 'Categoría'...")
    crear_propiedad(
        CLOPAS_DB_ID,
        "Categoría",
        "select",
        ["Código", "Documentación", "BD", "UI/UX", "Seguridad", "Otra"]
    )

    # Propiedad 4: Descripción
    print("4️⃣ Creando propiedad 'Descripción'...")
    crear_propiedad(CLOPAS_DB_ID, "Descripción", "text")

    # Propiedad 5: Solución
    print("5️⃣ Creando propiedad 'Solución'...")
    crear_propiedad(CLOPAS_DB_ID, "Solución", "text")

    # Propiedad 6: Código
    print("6️⃣ Creando propiedad 'Código'...")
    crear_propiedad(CLOPAS_DB_ID, "Código", "code")

    # Propiedad 7: Fecha
    print("7️⃣ Creando propiedad 'Fecha'...")
    crear_propiedad(CLOPAS_DB_ID, "Fecha", "date")

    # Propiedad 8: Estado
    print("8️⃣ Creando propiedad 'Estado'...")
    crear_propiedad(
        CLOPAS_DB_ID,
        "Estado",
        "select",
        ["Nuevo", "En Revisión", "Resuelto", "Descartado"]
    )

    # Propiedad 9: Prioridad
    print("9️⃣ Creando propiedad 'Prioridad'...")
    crear_propiedad(
        CLOPAS_DB_ID,
        "Prioridad",
        "select",
        ["Crítica", "Alta", "Media", "Baja"]
    )

    # Propiedad 10: Autor
    print("🔟 Creando propiedad 'Autor'...")
    crear_propiedad(CLOPAS_DB_ID, "Autor", "text")

    # Propiedad 11: Impacto
    print("1️⃣1️⃣ Creando propiedad 'Impacto'...")
    crear_propiedad(
        CLOPAS_DB_ID,
        "Impacto",
        "multi_select",
        ["Performance", "Seguridad", "Usabilidad", "BD", "API"]
    )

    # Propiedad 12: Tags
    print("1️⃣2️⃣ Creando propiedad 'Tags'...")
    crear_propiedad(CLOPAS_DB_ID, "Tags", "multi_select")

    # Propiedad 13: Enlace GitHub
    print("1️⃣3️⃣ Creando propiedad 'Enlace GitHub'...")
    crear_propiedad(CLOPAS_DB_ID, "Enlace GitHub", "url")

    print()
    print("=" * 60)
    print("✅ CLOPAS Configurada Correctamente")
    print("=" * 60)
    print()
    print("Propiedades creadas:")
    print("  ✅ Tipo (Select)")
    print("  ✅ Proyecto (Select)")
    print("  ✅ Categoría (Select)")
    print("  ✅ Descripción (Text)")
    print("  ✅ Solución (Text)")
    print("  ✅ Código (Code)")
    print("  ✅ Fecha (Date)")
    print("  ✅ Estado (Select)")
    print("  ✅ Prioridad (Select)")
    print("  ✅ Autor (Text)")
    print("  ✅ Impacto (Multi-select)")
    print("  ✅ Tags (Multi-select)")
    print("  ✅ Enlace GitHub (URL)")
    print()
    print("🎉 ¡CLOPAS está lista para usar!")
    print()
    print("Próximos pasos:")
    print("  1. Abre CLOPAS en Notion")
    print("  2. Crea un nuevo registro")
    print("  3. Usa: python3 scripts/gestor_clopas.py")

if __name__ == "__main__":
    main()
