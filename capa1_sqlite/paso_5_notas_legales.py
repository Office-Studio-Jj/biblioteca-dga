"""
Paso 5 — Lectura de Notas Legales desde JSON guardián (BLOQUEANTE)
CEO 05-05-2026: Si el JSON no responde o no tiene la nota, el sistema se detiene.
"""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_JSON_PATH = os.path.join(
    _HERE, "..", "notebooklm_skill", "data",
    "fuentes_nomenclatura", "notas_capitulos_cache.json"
)


def consultar_notas_legales(capitulo: int) -> dict:
    """
    Paso 5 BLOQUEANTE: Lee Notas Legales del capítulo desde el JSON guardián.
    Si falla → clasificación detenida.
    """
    if not os.path.exists(_JSON_PATH):
        return {
            "error": "BLOQUEANTE: notas_capitulos_cache.json no encontrado. Clasificación detenida.",
            "bloquea": True,
            "notas": None,
        }

    try:
        with open(_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return {
            "error": f"BLOQUEANTE: Error leyendo JSON guardián: {e}. Clasificación detenida.",
            "bloquea": True,
            "notas": None,
        }

    capitulos = data.get("capitulos", {})
    cap_key = str(capitulo)

    if cap_key not in capitulos:
        return {
            "error": f"BLOQUEANTE: Sin Notas Legales para Capítulo {capitulo}. Clasificación detenida.",
            "bloquea": True,
            "notas": None,
        }

    cap_data = capitulos[cap_key]
    return {
        "error": None,
        "bloquea": False,
        "notas": cap_data.get("notas_legales", []),
        "titulo": cap_data.get("titulo", ""),
        "aplica_isc": cap_data.get("aplica_isc", False),
        "partidas_con_isc": cap_data.get("partidas_con_isc", []),
        "version_json": data.get("_meta", {}).get("version", "desconocida"),
    }


def solicitar_ficha_tecnica(motivo: str) -> dict:
    """
    Paso 6.5: Detiene clasificación y solicita ficha técnica.
    Se activa cuando datos insuficientes para aplicar RGI con certeza.
    """
    return {
        "estado": "ficha_requerida",
        "mensaje": (
            "CLASIFICACIÓN DETENIDA — Se requiere ficha técnica del producto. "
            f"Motivo: {motivo}. "
            "Proporcione: composición, función principal, uso previsto, especificaciones técnicas. "
            "Base legal: Decreto 755-22, RGI 1-6 (Convenio SA Art. 3)."
        ),
        "bloquea": True,
    }
