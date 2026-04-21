#!/usr/bin/env python3
"""
AUTO-HEAL CACHE — Reparacion automatica preventiva
===================================================
Modulo ligero que se ejecuta al cargar el cache del Arancel.
Detecta y corrige codigos sin gravamen ANTES de cualquier consulta.

No re-parsea el PDF (eso toma ~90s). Usa un lookup pre-extraido
(gravamenes_lookup.json) que se genera una vez con reparar_cache_tabla.py.

Flujo:
  1. verificador_arancelario.py llama _cargar_cache_arancel()
  2. Despues de cargar, llama auto_heal() de este modulo
  3. auto_heal() verifica integridad en <100ms
  4. Si hay codigos sin gravamen, los repara del lookup instantaneamente
  5. Respeta blacklist (nunca toca correcciones manuales)

Uso directo:
  python auto_heal_cache.py              # Reparar + generar lookup si no existe
  python auto_heal_cache.py --generar    # Solo generar lookup desde PDF
  python auto_heal_cache.py --status     # Solo mostrar estado del cache
"""

import json
import os
import re
import sys
import time
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data", "fuentes_nomenclatura")
CACHE_PATH = os.path.join(DATA_DIR, "arancel_cache.json")
LOOKUP_PATH = os.path.join(DATA_DIR, "gravamenes_lookup.json")
BLACKLIST_PATH = os.path.join(DATA_DIR, "correcciones_manuales.json")
HERENCIA_PATH = os.path.join(DATA_DIR, "herencia_gravamenes.json")

PATRON_SUBPARTIDA = re.compile(r'^\d{4}\.\d{2}\.\d{2}$')


def _extraer_grav(desc):
    """Extrae gravamen del final de una descripcion."""
    m = re.search(r'\s+(\d+)\s*$', (desc or "").strip())
    return m.group(1) if m else None


def _cargar_json(path):
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _guardar_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def generar_lookup():
    """Genera gravamenes_lookup.json extrayendo del PDF por tabla.
    Se ejecuta UNA VEZ (o cuando el PDF cambie)."""
    try:
        from reparar_cache_tabla import extraer_todo_pdf, herencia_subpartida
    except ImportError:
        sys.path.insert(0, SCRIPT_DIR)
        from reparar_cache_tabla import extraer_todo_pdf, herencia_subpartida

    print("[AUTO-HEAL] Generando lookup de gravamenes desde PDF...")
    gravamenes_pdf, descripciones_pdf = extraer_todo_pdf()

    # Calcular herencia para cubrir codigos huerfanos
    cache = _cargar_json(CACHE_PATH)
    codigos_cache = cache.get("codigos", {})
    heredados = herencia_subpartida(codigos_cache, gravamenes_pdf)

    # Combinar: PDF directo + herencia
    lookup = {}
    for codigo, grav in gravamenes_pdf.items():
        lookup[codigo] = {"g": grav, "f": "pdf"}

    for codigo, info in heredados.items():
        if codigo not in lookup:
            lookup[codigo] = {"g": info["gravamen"], "f": info["fuente"]}

    # Guardar
    meta = {
        "generado": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_pdf": len(gravamenes_pdf),
        "total_herencia": len(heredados),
        "total": len(lookup),
        "gravamenes": lookup
    }
    _guardar_json(LOOKUP_PATH, meta)
    print(f"[AUTO-HEAL] Lookup guardado: {len(lookup)} gravamenes -> {LOOKUP_PATH}")
    return lookup


def auto_heal(codigos_cache: dict, silent=False) -> int:
    """Repara codigos sin gravamen usando el lookup pre-extraido.

    Args:
        codigos_cache: dict {codigo: descripcion} — se modifica IN-PLACE
        silent: si True, no imprime nada (para uso en servidor)

    Returns:
        Cantidad de codigos reparados
    """
    # Cargar lookup
    lookup_data = _cargar_json(LOOKUP_PATH)
    lookup = lookup_data.get("gravamenes", {})

    if not lookup:
        if not silent:
            print("[AUTO-HEAL] Lookup no encontrado — ejecute: python auto_heal_cache.py --generar")
        return 0

    # Cargar blacklist
    bl = _cargar_json(BLACKLIST_PATH)
    protegidos = set(bl.get("correcciones", {}).keys())

    # Identificar codigos sin gravamen
    sin_grav = []
    for codigo, desc in codigos_cache.items():
        if _extraer_grav(desc) is None and codigo not in protegidos:
            sin_grav.append(codigo)

    if not sin_grav:
        if not silent:
            print("[AUTO-HEAL] Cache sano — todos los codigos tienen gravamen")
        return 0

    # Reparar
    reparados = 0
    for codigo in sin_grav:
        if codigo in lookup:
            grav = lookup[codigo]["g"]
            desc_actual = codigos_cache[codigo]
            codigos_cache[codigo] = f"{desc_actual.strip()} {grav}"
            reparados += 1

    if reparados > 0 and not silent:
        print(f"[AUTO-HEAL] {reparados} codigos reparados de {len(sin_grav)} sin gravamen")

    return reparados


def auto_heal_y_guardar():
    """Carga cache, repara, guarda. Para uso standalone."""
    from cache_utils import cargar_codigos, guardar_cache
    codigos = cargar_codigos()

    reparados = auto_heal(codigos)

    if reparados > 0:
        guardar_cache(codigos, meta_extra={
            "auto_heal_ultima": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        print(f"[AUTO-HEAL] Cache guardado con {reparados} reparaciones")

    return reparados


def status():
    """Muestra estado rapido del cache."""
    cache = _cargar_json(CACHE_PATH)
    codigos = cache.get("codigos", {})
    total = len(codigos)

    sin_grav = sum(1 for d in codigos.values() if _extraer_grav(d) is None)
    con_grav = total - sin_grav

    lookup_data = _cargar_json(LOOKUP_PATH)
    lookup_size = len(lookup_data.get("gravamenes", {}))
    lookup_fecha = lookup_data.get("generado", "no generado")

    bl = _cargar_json(BLACKLIST_PATH)
    protegidos = len(bl.get("correcciones", {}))

    print(f"Cache: {total} codigos ({con_grav} con gravamen, {sin_grav} sin)")
    print(f"Cobertura: {100*con_grav/total:.1f}%")
    print(f"Lookup: {lookup_size} gravamenes (generado: {lookup_fecha})")
    print(f"Blacklist: {protegidos} protegidos")
    print(f"Salud: {'OPTIMO' if sin_grav < 20 else 'DEGRADADO' if sin_grav < 200 else 'CRITICO'}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Auto-Heal Cache Arancel")
    parser.add_argument("--generar", action="store_true", help="Generar lookup desde PDF")
    parser.add_argument("--status", action="store_true", help="Mostrar estado del cache")
    args = parser.parse_args()

    if args.status:
        status()
        return

    if args.generar:
        generar_lookup()
        return

    # Default: generar lookup si no existe, luego reparar
    if not os.path.isfile(LOOKUP_PATH):
        print("[AUTO-HEAL] Lookup no existe — generando...")
        generar_lookup()

    reparados = auto_heal_y_guardar()
    if reparados == 0:
        print("[AUTO-HEAL] Cache ya esta sano")

    status()


if __name__ == "__main__":
    main()
