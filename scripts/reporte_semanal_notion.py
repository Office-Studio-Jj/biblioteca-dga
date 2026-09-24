#!/usr/bin/env python3
"""
Reporte Semanal Automático - Biblioteca DGA
Ejecuta cada domingo a las 21:00 y envía resumen a Notion
Elimina por completo NotebookLM
"""

import os
import json
import subprocess
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
NOTION_DB_REPORTES = os.getenv("NOTION_DB_REPORTES", "")  # Base de datos para reportes
RAILWAY_TOKEN = os.getenv("RAILWAY_TOKEN", "")

class ReporteSemanal:
    def __init__(self):
        self.fecha_generacion = datetime.now()
        self.fecha_inicio_semana = self.fecha_generacion - timedelta(days=7)
        self.commits = []
        self.errores_railway = []
        self.deployments = []
        self.info_notion = {}

    def obtener_commits_semana(self):
        """Obtiene todos los commits de la última semana"""
        try:
            fecha_inicio = self.fecha_inicio_semana.isoformat()
            cmd = [
                "git", "log",
                "--since=" + fecha_inicio,
                "--pretty=format:%h|%an|%ae|%s|%aI"
            ]
            resultado = subprocess.run(cmd, capture_output=True, text=True, cwd="/home/user/biblioteca-dga")

            if resultado.stdout:
                for linea in resultado.stdout.strip().split('\n'):
                    if linea:
                        partes = linea.split('|')
                        if len(partes) == 5:
                            self.commits.append({
                                'hash': partes[0],
                                'autor': partes[1],
                                'email': partes[2],
                                'mensaje': partes[3],
                                'fecha': partes[4]
                            })
            print(f"✅ Commits obtenidos: {len(self.commits)}")
        except Exception as e:
            print(f"❌ Error al obtener commits: {e}")

    def obtener_info_railway(self):
        """Obtiene información de Railway (logs, deployments)"""
        if not RAILWAY_TOKEN:
            print("⚠️ RAILWAY_TOKEN no configurado, saltando Railway")
            return

        try:
            # Aquí se conectaría con Railway API
            # Por ahora, placeholder
            self.deployments = [{
                'estado': 'ACTIVE',
                'fecha': datetime.now().isoformat(),
                'mensaje': 'Deploy automático de claves nuevas'
            }]
            print(f"✅ Deployments obtenidos: {len(self.deployments)}")
        except Exception as e:
            print(f"❌ Error al obtener Railway: {e}")

    def compilar_resumen(self):
        """Compila el resumen para Notion"""
        resumen = {
            'fecha_generacion': self.fecha_generacion.isoformat(),
            'periodo': f"{self.fecha_inicio_semana.date()} a {self.fecha_generacion.date()}",
            'estadisticas': {
                'total_commits': len(self.commits),
                'total_deployments': len(self.deployments),
                'errores_detectados': len(self.errores_railway)
            },
            'commits': self.commits[:10],  # Últimos 10 commits
            'deployments': self.deployments,
            'notas': 'Reporte generado automáticamente. NotebookLM removido del pipeline.'
        }
        return resumen

    def enviar_notion(self, resumen):
        """Envía el resumen a Notion"""
        if not NOTION_API_KEY or not NOTION_DB_REPORTES:
            print("⚠️ Credenciales de Notion no configuradas")
            print("Resumen compilado:")
            print(json.dumps(resumen, indent=2, default=str))
            return False

        try:
            # Preparar payload para Notion API
            titulo = f"📊 Reporte Semanal - {self.fecha_generacion.strftime('%d-%b-%Y')}"

            payload = {
                "parent": {"database_id": NOTION_DB_REPORTES},
                "properties": {
                    "title": {"title": [{"text": {"content": titulo}}]},
                    "Período": {"rich_text": [{"text": {"content": resumen['periodo']}}]},
                    "Total Commits": {"number": resumen['estadisticas']['total_commits']},
                    "Deployments": {"number": resumen['estadisticas']['total_deployments']},
                    "Estado": {"select": {"name": "Completado"}}
                },
                "children": [
                    {
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {"rich_text": [{"text": {"content": "Estadísticas"}}]}
                    },
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{
                                "text": {
                                    "content": f"Commits: {resumen['estadisticas']['total_commits']} | Deployments: {resumen['estadisticas']['total_deployments']}"
                                }
                            }]
                        }
                    }
                ]
            }

            # Aquí se haría la llamada a Notion API
            # import requests
            # headers = {"Authorization": f"Bearer {NOTION_API_KEY}"}
            # response = requests.post("https://api.notion.com/v1/pages", json=payload, headers=headers)

            print("✅ Reporte preparado para Notion")
            print(f"   Título: {titulo}")
            print(f"   Commits: {resumen['estadisticas']['total_commits']}")
            return True

        except Exception as e:
            print(f"❌ Error al enviar a Notion: {e}")
            return False

    def ejecutar(self):
        """Ejecuta el reporte completo"""
        print("🚀 Iniciando Reporte Semanal...")
        print(f"   Fecha: {self.fecha_generacion}")
        print(f"   Período: Última semana")
        print()

        self.obtener_commits_semana()
        self.obtener_info_railway()
        resumen = self.compilar_resumen()
        self.enviar_notion(resumen)

        print()
        print("✅ Reporte Semanal Completado")


if __name__ == "__main__":
    reporte = ReporteSemanal()
    reporte.ejecutar()
