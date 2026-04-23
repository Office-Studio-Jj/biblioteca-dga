#!/usr/bin/env python3
"""
consultor_notas_arancel.py — Sub-agente paralelo de Notas Legales/Explicativas
================================================================================

Trabaja EN PARALELO con Gemini durante la clasificacion arancelaria. Mientras
Gemini consulta el Arancel 7ma Enmienda, este modulo lee notas_capitulos_cache.json
para validar (o corregir) la aplicabilidad de ISC, gravamen y otras disposiciones
segun las Notas Legales del capitulo y las Notas Explicativas del SA.

Motivacion:
  - El Capitulo 85 no es homogeneo para ISC: solo 8521/8525/8527/8528 son
    bienes suntuarios. Partidas como 8543.70.00 (Las demas maquinas y aparatos)
    NO son suntuarios aunque esten en el cap.85.
  - Sin este consultor paralelo, Gemini a veces extiende el ISC 10% a TODO el
    capitulo, produciendo cargas impositivas falsamente calculadas.

Arquitectura:
  - Cache JSON offline con Notas Legales, partidas_con_isc, advertencias y
    capitulos_sin_isc_general.
  - API sincrona: analizar_codigo(codigo) -> dict con veredicto.
  - API asincrona: analizar_codigo_async(codigo) -> threading.Thread.
  - Integracion: ask_gemini.py lanza analizar_codigo_async antes de llamar al
    modelo y consolida el resultado al final (antes de _corregir_isc_con_lookup).

Uso standalone:
  python consultor_notas_arancel.py --codigo 8543.70.00
"""

from __future__ import annotations

import json
import os
import re
import threading
from typing import Optional

_BASE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.join(_BASE, "..", "data", "fuentes_nomenclatura")
_NOTAS_CACHE = os.path.join(_DATA, "notas_capitulos_cache.json")
_ISC_LOOKUP = os.path.join(_DATA, "isc_lookup.json")

_CACHE_LOCK = threading.Lock()
_CACHE_DATA: Optional[dict] = None


def _cargar_cache() -> dict:
    global _CACHE_DATA
    with _CACHE_LOCK:
        if _CACHE_DATA is not None:
            return _CACHE_DATA
        try:
            with open(_NOTAS_CACHE, "r", encoding="utf-8") as f:
                _CACHE_DATA = json.load(f)
        except Exception as e:
            print(f"[NOTAS-ARANCEL] Error cargando cache: {e}")
            _CACHE_DATA = {"capitulos": {}, "regla_general_isc_rd": {}}
    return _CACHE_DATA


def analizar_codigo(codigo: str) -> dict:
    """
    Analiza un codigo arancelario contra Notas Legales / Explicativas.

    Args:
        codigo: XXXX.XX.XX (formato RD, 8 digitos)

    Returns:
        dict con:
          - codigo
          - capitulo
          - partida
          - aplica_isc: bool | "parcial" | None
          - tasa_isc: str | None
          - razon: str (explicacion citando notas/ley)
          - advertencia: str | None (si la clasificacion necesita confirmacion)
          - notas_legales: list[str]
          - fuente: str
          - veredicto: "APLICA_ISC" | "NO_APLICA_ISC" | "VERIFICAR" | "CAPITULO_NO_ISC"
    """
    if not re.match(r'^\d{4}\.\d{2}\.\d{2}$', codigo or ""):
        return {
            "codigo": codigo,
            "error": f"Formato invalido: {codigo}. Esperado XXXX.XX.XX",
            "veredicto": "ERROR",
            "fuente": "consultor_notas_arancel.py"
        }

    cache = _cargar_cache()
    capitulo = codigo[:2]
    partida = codigo[:4]

    capitulos_con_isc = cache.get("regla_general_isc_rd", {}).get("capitulos_con_isc", [])

    cap_data = cache.get("capitulos", {}).get(capitulo)

    # Capitulo sin ISC en RD (ni siquiera figura en la lista de capitulos_con_isc)
    if capitulo not in capitulos_con_isc:
        return {
            "codigo": codigo,
            "capitulo": capitulo,
            "partida": partida,
            "aplica_isc": False,
            "tasa_isc": None,
            "razon": (f"Capitulo {capitulo} no esta en la lista de capitulos afectados por ISC "
                      f"({capitulos_con_isc}). Ley 11-92 Titulo IV no aplica a esta mercancia."),
            "advertencia": None,
            "notas_legales": (cap_data or {}).get("notas_legales", []),
            "fuente": f"notas_capitulos_cache.json + Ley 11-92 Titulo IV (cap. {capitulo} sin ISC)",
            "veredicto": "CAPITULO_NO_ISC"
        }

    # Capitulo con ISC pero sin entrada detallada en cache
    if not cap_data:
        return {
            "codigo": codigo,
            "capitulo": capitulo,
            "partida": partida,
            "aplica_isc": "verificar",
            "tasa_isc": None,
            "razon": (f"Capitulo {capitulo} figura como afectado por ISC pero sin notas "
                      f"detalladas en cache. Consultar isc_lookup.json o PDF del Arancel."),
            "advertencia": f"Agregar entrada para cap. {capitulo} en notas_capitulos_cache.json",
            "notas_legales": [],
            "fuente": f"notas_capitulos_cache.json (cap. {capitulo} sin detalle)",
            "veredicto": "VERIFICAR"
        }

    aplica = cap_data.get("aplica_isc", False)
    partidas_con_isc = cap_data.get("partidas_con_isc", [])
    partidas_sin_isc = cap_data.get("partidas_sin_isc_explicito", [])
    tipo_isc = cap_data.get("tipo_isc", "")
    base_legal = cap_data.get("base_legal_isc", "")

    # Caso ISC total para el capitulo
    if aplica is True:
        aplica_a_esta_partida = not partidas_con_isc or any(
            partida == p for p in partidas_con_isc
        )
        if aplica_a_esta_partida:
            return {
                "codigo": codigo,
                "capitulo": capitulo,
                "partida": partida,
                "aplica_isc": True,
                "tasa_isc": tipo_isc,
                "razon": f"Partida {partida} afectada por ISC del capitulo {capitulo}",
                "advertencia": None,
                "notas_legales": cap_data.get("notas_legales", []),
                "base_legal": base_legal,
                "fuente": f"notas_capitulos_cache.json[cap.{capitulo}] (ISC total capitulo)",
                "veredicto": "APLICA_ISC"
            }
        return {
            "codigo": codigo,
            "capitulo": capitulo,
            "partida": partida,
            "aplica_isc": False,
            "tasa_isc": None,
            "razon": (f"Capitulo {capitulo} tiene ISC pero solo para partidas {partidas_con_isc}; "
                      f"{partida} no esta afectada."),
            "advertencia": None,
            "notas_legales": cap_data.get("notas_legales", []),
            "base_legal": base_legal,
            "fuente": f"notas_capitulos_cache.json[cap.{capitulo}]",
            "veredicto": "NO_APLICA_ISC"
        }

    # Caso parcial (cap. 85): solo aplica a partidas listadas
    if aplica == "parcial":
        if partida in partidas_con_isc:
            return {
                "codigo": codigo,
                "capitulo": capitulo,
                "partida": partida,
                "aplica_isc": True,
                "tasa_isc": tipo_isc,
                "razon": (f"Partida {partida} listada como bien suntuario electronico "
                          f"(cap.{capitulo}, Ley 11-92 Art. 375)"),
                "advertencia": None,
                "notas_legales": cap_data.get("notas_legales", []),
                "notas_explicativas": cap_data.get("notas_explicativas_clave", []),
                "base_legal": base_legal,
                "fuente": f"notas_capitulos_cache.json[cap.{capitulo}].partidas_con_isc",
                "veredicto": "APLICA_ISC"
            }
        if partida in partidas_sin_isc:
            return {
                "codigo": codigo,
                "capitulo": capitulo,
                "partida": partida,
                "aplica_isc": False,
                "tasa_isc": None,
                "razon": (f"Partida {partida} NO esta listada como bien suntuario del cap.{capitulo}. "
                          f"Solo {partidas_con_isc} aplican ISC 10% (Ley 11-92 Art. 375). "
                          f"{cap_data.get('advertencia_aplicacion', '')}"),
                "advertencia": ("El capitulo 85 no es homogeneo para ISC. "
                                "No extrapolar 10% a partidas fuera de la lista."),
                "notas_legales": cap_data.get("notas_legales", []),
                "notas_explicativas": cap_data.get("notas_explicativas_clave", []),
                "base_legal": base_legal,
                "fuente": f"notas_capitulos_cache.json[cap.{capitulo}].partidas_sin_isc_explicito",
                "veredicto": "NO_APLICA_ISC"
            }
        # Partida no catalogada — necesita verificacion manual
        return {
            "codigo": codigo,
            "capitulo": capitulo,
            "partida": partida,
            "aplica_isc": "verificar",
            "tasa_isc": None,
            "razon": (f"Partida {partida} no catalogada en cap.{capitulo}. "
                      f"Partidas con ISC: {partidas_con_isc}. "
                      f"Verificar manualmente contra Arancel PDF antes de aplicar 10%."),
            "advertencia": "Partida ambigua — NO aplicar ISC sin verificacion",
            "notas_legales": cap_data.get("notas_legales", []),
            "base_legal": base_legal,
            "fuente": f"notas_capitulos_cache.json[cap.{capitulo}] (partida no catalogada)",
            "veredicto": "VERIFICAR"
        }

    # Fallback general
    return {
        "codigo": codigo,
        "capitulo": capitulo,
        "partida": partida,
        "aplica_isc": False,
        "tasa_isc": None,
        "razon": f"Sin disposicion ISC para {codigo}",
        "advertencia": None,
        "notas_legales": (cap_data or {}).get("notas_legales", []),
        "base_legal": base_legal,
        "fuente": f"notas_capitulos_cache.json (caso no contemplado)",
        "veredicto": "NO_APLICA_ISC"
    }


def analizar_codigo_async(codigo: str, resultado: dict) -> threading.Thread:
    """Lanza el analisis en un thread. El resultado se guarda en resultado['notas'].

    Uso:
        slot = {}
        t = analizar_codigo_async("8543.70.00", slot)
        # ...Gemini trabaja en paralelo...
        t.join(timeout=3)
        notas = slot.get("notas")
    """
    def _worker():
        try:
            resultado["notas"] = analizar_codigo(codigo)
        except Exception as e:
            resultado["notas"] = {"error": str(e), "veredicto": "ERROR"}

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return t


def formatear_para_respuesta(notas: dict) -> str:
    """Formatea el resultado del consultor en un bloque legible para anexar a la respuesta."""
    if not notas or notas.get("error"):
        return ""
    veredicto = notas.get("veredicto", "VERIFICAR")
    partes = [
        "---NOTAS_ARANCEL---",
        f"CODIGO: {notas.get('codigo')}",
        f"CAPITULO: {notas.get('capitulo')} — Partida: {notas.get('partida')}",
        f"VEREDICTO_ISC: {veredicto}",
        f"APLICA_ISC: {notas.get('aplica_isc')}",
        f"RAZON: {notas.get('razon', '')}",
    ]
    if notas.get("tasa_isc"):
        partes.append(f"TASA_ISC: {notas['tasa_isc']}")
    if notas.get("base_legal"):
        partes.append(f"BASE_LEGAL: {notas['base_legal']}")
    if notas.get("advertencia"):
        partes.append(f"ADVERTENCIA: {notas['advertencia']}")
    partes.append(f"FUENTE: {notas.get('fuente', '')}")
    partes.append("---FIN_NOTAS_ARANCEL---")
    return "\n".join(partes)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Consultor de Notas Arancel RD")
    parser.add_argument("--codigo", required=True)
    parser.add_argument("--json", action="store_true", help="Salida JSON pura")
    args = parser.parse_args()
    r = analizar_codigo(args.codigo)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(formatear_para_respuesta(r))
