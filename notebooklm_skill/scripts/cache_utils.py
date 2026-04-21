"""
Contrato único para leer y escribir arancel_cache.json.
Todos los scripts deben usar estas funciones — nunca json.load/dump directo.
"""
import json
import os
from datetime import datetime

_BASE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(_BASE, "..", "data", "fuentes_nomenclatura", "arancel_cache.json")


def cargar_codigos() -> dict:
    """Devuelve {codigo: descripcion} sin importar el formato del archivo."""
    if not os.path.isfile(CACHE_PATH):
        return {}
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Formato canónico: objeto con clave "codigos"
        if "codigos" in data and isinstance(data["codigos"], dict):
            return data["codigos"]
        # Formato plano legado: filtrar solo códigos arancelarios
        return {k: v for k, v in data.items() if isinstance(k, str) and len(k) >= 8 and "." in k}
    except Exception as e:
        print(f"[CACHE_UTILS] Error cargando cache: {e}")
        return {}


def guardar_cache(codigos: dict, meta_extra: dict = None):
    """Siempre guarda en formato canónico: {"codigos": {...}, metadatos...}"""
    # Preservar metadatos existentes
    existente = {}
    if os.path.isfile(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                existente = json.load(f)
            # Si era formato plano, limpiar claves que no son metadatos
            if "codigos" not in existente:
                existente = {}
        except Exception:
            existente = {}

    existente.setdefault("fuente", "Arancel 7ma enmienda de la republica dominicana.pdf")
    existente.setdefault("metodo", "pdfplumber (0% IA)")
    existente.setdefault("fecha_extraccion", datetime.now().strftime("%Y-%m-%d"))
    existente["codigos"] = codigos
    existente["codigos_extraidos"] = len(codigos)
    existente["ultima_escritura"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    if meta_extra:
        existente.update(meta_extra)

    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(existente, f, ensure_ascii=False, indent=2)
