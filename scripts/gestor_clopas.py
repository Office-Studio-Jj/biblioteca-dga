#!/usr/bin/env python3
"""
Gestor CLOPAS - Sistema Central de Control de Cambios
Gestiona correcciones, creaciones y errores en Notion
"""

import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
from typing import Dict, List, Optional

load_dotenv()

class GestorCLOPAS:
    """Gestor de CLOPAS en Notion"""

    def __init__(self):
        self.notion_token = os.getenv("NOTION_API_KEY", "")
        self.clopas_db_id = os.getenv("NOTION_DB_CLOPAS", "")
        self.base_url = "https://api.notion.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }

        if not self.notion_token or not self.clopas_db_id:
            print("⚠️ NOTION_API_KEY o NOTION_DB_CLOPAS no configurados")
            print("   Agregar al .env:")
            print("   NOTION_DB_CLOPAS=xxxxxxxxxxxxxxxxxxxxxxxxxxxxx")

    def crear_registro_correccion(
        self,
        titulo: str,
        proyecto: str,
        categoria: str,
        descripcion: str,
        solucion: str = "",
        codigo: str = "",
        prioridad: str = "Media",
        impacto: List[str] = None
    ) -> bool:
        """Crea un registro de corrección en CLOPAS"""

        if impacto is None:
            impacto = []

        payload = {
            "parent": {"database_id": self.clopas_db_id},
            "properties": {
                "Title": {"title": [{"text": {"content": titulo}}]},
                "Tipo": {"select": {"name": "Corrección"}},
                "Proyecto": {"select": {"name": proyecto}},
                "Categoría": {"select": {"name": categoria}},
                "Descripción": {"rich_text": [{"text": {"content": descripcion}}]},
                "Solución": {"rich_text": [{"text": {"content": solucion}}]},
                "Código": {"rich_text": [{"text": {"content": codigo}}]},
                "Fecha": {"date": {"start": datetime.now().isoformat()}},
                "Estado": {"select": {"name": "Nuevo"}},
                "Prioridad": {"select": {"name": prioridad}},
                "Autor": {"rich_text": [{"text": {"content": os.getenv("USER", "Sistema")}}]},
                "Impacto": {"multi_select": [{"name": imp} for imp in impacto]},
            }
        }

        return self._enviar_request("POST", "/pages", payload)

    def crear_registro_error(
        self,
        titulo: str,
        proyecto: str,
        descripcion: str,
        solucion: str = "",
        codigo: str = "",
        prioridad: str = "Alta",
        stack_trace: str = ""
    ) -> bool:
        """Crea un registro de error en CLOPAS"""

        payload = {
            "parent": {"database_id": self.clopas_db_id},
            "properties": {
                "Title": {"title": [{"text": {"content": titulo}}]},
                "Tipo": {"select": {"name": "Error"}},
                "Proyecto": {"select": {"name": proyecto}},
                "Categoría": {"select": {"name": "Bug"}},
                "Descripción": {"rich_text": [{"text": {"content": descripcion}}]},
                "Solución": {"rich_text": [{"text": {"content": solucion}}]},
                "Código": {"rich_text": [{"text": {"content": stack_trace or codigo}}]},
                "Fecha": {"date": {"start": datetime.now().isoformat()}},
                "Estado": {"select": {"name": "Nuevo"}},
                "Prioridad": {"select": {"name": prioridad}},
                "Autor": {"rich_text": [{"text": {"content": os.getenv("USER", "Sistema")}}]},
            }
        }

        return self._enviar_request("POST", "/pages", payload)

    def crear_registro_creacion(
        self,
        titulo: str,
        proyecto: str,
        categoria: str,
        contenido: str,
        tecnologia: str = "",
        tags: List[str] = None
    ) -> bool:
        """Crea un registro de creación de contenido en CLOPAS"""

        if tags is None:
            tags = []

        payload = {
            "parent": {"database_id": self.clopas_db_id},
            "properties": {
                "Title": {"title": [{"text": {"content": titulo}}]},
                "Tipo": {"select": {"name": "Creación"}},
                "Proyecto": {"select": {"name": proyecto}},
                "Categoría": {"select": {"name": categoria}},
                "Descripción": {"rich_text": [{"text": {"content": contenido}}]},
                "Fecha": {"date": {"start": datetime.now().isoformat()}},
                "Estado": {"select": {"name": "Nuevo"}},
                "Prioridad": {"select": {"name": "Media"}},
                "Autor": {"rich_text": [{"text": {"content": os.getenv("USER", "Sistema")}}]},
                "Tags": {"multi_select": [{"name": tag} for tag in tags + ([tecnologia] if tecnologia else [])]},
            }
        }

        return self._enviar_request("POST", "/pages", payload)

    def listar_errores(self, proyecto: str = None, estado: str = "Nuevo") -> List[Dict]:
        """Lista todos los errores en CLOPAS"""

        filter_query = {
            "filter": {
                "and": [
                    {"property": "Tipo", "select": {"equals": "Error"}},
                    {"property": "Estado", "select": {"equals": estado}}
                ]
            }
        }

        if proyecto:
            filter_query["filter"]["and"].append(
                {"property": "Proyecto", "select": {"equals": proyecto}}
            )

        return self._enviar_request("POST", f"/databases/{self.clopas_db_id}/query", filter_query)

    def listar_correcciones(self, proyecto: str = None) -> List[Dict]:
        """Lista todas las correcciones en CLOPAS"""

        filter_query = {
            "filter": {
                "property": "Tipo",
                "select": {"equals": "Corrección"}
            }
        }

        if proyecto:
            filter_query["filter"] = {
                "and": [
                    filter_query["filter"],
                    {"property": "Proyecto", "select": {"equals": proyecto}}
                ]
            }

        return self._enviar_request("POST", f"/databases/{self.clopas_db_id}/query", filter_query)

    def actualizar_estado(self, page_id: str, nuevo_estado: str) -> bool:
        """Actualiza el estado de un registro en CLOPAS"""

        payload = {
            "properties": {
                "Estado": {"select": {"name": nuevo_estado}}
            }
        }

        return self._enviar_request("PATCH", f"/pages/{page_id}", payload)

    def _enviar_request(self, metodo: str, endpoint: str, datos: Dict = None) -> bool:
        """Envía request a Notion API"""

        try:
            url = f"{self.base_url}{endpoint}"

            if metodo == "POST":
                response = requests.post(url, json=datos, headers=self.headers)
            elif metodo == "PATCH":
                response = requests.patch(url, json=datos, headers=self.headers)
            elif metodo == "GET":
                response = requests.get(url, headers=self.headers)
            else:
                return False

            if response.status_code in [200, 201]:
                print(f"✅ {metodo} exitoso: {endpoint}")
                return True
            else:
                print(f"❌ Error {response.status_code}: {response.text}")
                return False

        except Exception as e:
            print(f"❌ Error de conexión: {e}")
            return False

    def generar_reporte(self) -> Dict:
        """Genera un reporte de CLOPAS"""

        reporte = {
            "fecha_generacion": datetime.now().isoformat(),
            "total_errores": len(self.listar_errores()),
            "errores_por_proyecto": {},
            "correcciones_recientes": [],
            "estado_general": "OK"
        }

        return reporte


def main():
    """Ejemplo de uso"""

    gestor = GestorCLOPAS()

    if not gestor.notion_token:
        print("❌ No hay credenciales de Notion configuradas")
        return

    print("🎯 Gestor CLOPAS - Sistema Central de Control")
    print()

    # Ejemplo: Crear error
    gestor.crear_registro_error(
        titulo="Timeout en conexión a base de datos",
        proyecto="biblioteca-dga",
        descripcion="Se produce timeout cada 30 minutos en producción",
        solucion="Aumentar timeout a 60 segundos",
        codigo="timeout = 60",
        prioridad="Crítica"
    )

    # Ejemplo: Crear corrección
    gestor.crear_registro_correccion(
        titulo="Corregir validación de email",
        proyecto="app-movil",
        categoria="Código",
        descripcion="Email regex muy restrictiva",
        solucion="Actualizar a RFC 5322",
        prioridad="Alta"
    )

    # Ejemplo: Crear creación
    gestor.crear_registro_creacion(
        titulo="Nueva función de clasificación",
        proyecto="biblioteca-dga",
        categoria="Código",
        contenido="Función que clasifica aranceles automáticamente",
        tags=["IA", "clasificación"]
    )

    print()
    print("✅ Ejemplos enviados a CLOPAS")


if __name__ == "__main__":
    main()
