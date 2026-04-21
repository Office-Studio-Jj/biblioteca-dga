#!/usr/bin/env python3
"""
REPARADOR DE CACHE — Extraccion por tabla con matching posicional
=================================================================
Usa pdfplumber table extraction para emparejar CODIGO <-> GRAV
por posicion en las columnas del PDF. Corrige los ~1,005 codigos
sin gravamen que el extractor linea-por-linea no pudo resolver.

El PDF tiene 4 columnas: CODIGO | DESIGNACION | GRAV | EX.ITBIS
398 de 431 paginas tienen caracteres duplicados (artefacto PDF).

Estrategia:
  1. Extraer tabla por pagina (pdfplumber usa vectores del PDF)
  2. Detectar y de-duplicar caracteres por pagina
  3. Separar codigos y gravamenes por \\n dentro de cada celda
  4. Match posicional: subpartidas (XXXX.XX.XX) consumen gravamen,
     headings (XX.XX, XXXX.XX) no consumen gravamen
  5. Herencia: codigos sin gravamen heredan de subpartida padre
  6. Blacklist: NUNCA sobreescribir correcciones manuales

Uso:
  python reparar_cache_tabla.py                  # Reparar cache
  python reparar_cache_tabla.py --dry-run        # Solo mostrar que cambiaria
  python reparar_cache_tabla.py --full-extract   # Re-extraer todo desde cero
"""

import json
import os
import re
import sys
import time
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data", "fuentes_nomenclatura")
PDF_PATH = os.path.join(DATA_DIR, "Arancel 7ma enmienda de la republica dominicana.pdf")
CACHE_PATH = os.path.join(DATA_DIR, "arancel_cache.json")
BLACKLIST_PATH = os.path.join(DATA_DIR, "correcciones_manuales.json")

PATRON_SUBPARTIDA = re.compile(r'^\d{4}\.\d{2}\.\d{2}$')
PATRON_HEADING = re.compile(r'^\d{2}\.\d{2}$|^\d{4}\.\d{2}$')
PATRON_DOUBLED = re.compile(r'\d\d\d\d\d\d\d\d\.\.')  # 8 digitos + doble punto


def cargar_blacklist():
    if os.path.isfile(BLACKLIST_PATH):
        with open(BLACKLIST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"correcciones": {}, "historial": []}


def cargar_cache():
    from cache_utils import cargar_codigos
    return {"codigos": cargar_codigos()}


def guardar_cache(cache):
    from cache_utils import guardar_cache as _guardar
    _guardar(cache.get("codigos", {}), meta_extra={
        k: v for k, v in cache.items() if k != "codigos"
    })


def dedup_text(text):
    """De-duplica caracteres en texto con artefacto de duplicacion.
    Toma cada par de caracteres identicos adyacentes y colapsa a uno."""
    if not text:
        return text
    result = []
    i = 0
    while i < len(text):
        if i + 1 < len(text) and text[i] == text[i + 1] and text[i] not in ('\n', ' '):
            result.append(text[i])
            i += 2
        else:
            result.append(text[i])
            i += 1
    return ''.join(result)


def es_pagina_duplicada(text):
    """Detecta si una pagina tiene el artefacto de caracteres duplicados."""
    return bool(PATRON_DOUBLED.search(text or ""))


def extraer_tabla_pagina(page):
    """Extrae pares (codigo, gravamen) de una pagina usando tabla.

    Retorna dict {codigo: gravamen_str} para subpartidas encontradas.
    Tambien retorna dict {codigo: descripcion} para las descripciones.
    """
    gravamenes = {}
    descripciones = {}

    tables = page.extract_tables()
    if not tables:
        return gravamenes, descripciones

    for table in tables:
        if not table or len(table) == 0:
            continue

        for row in table:
            if not row or len(row) < 3:
                continue

            # Columnas: [CODIGO, DESIGNACION, GRAV, EX.ITBIS?]
            col_codigo = str(row[0] or "").strip()
            col_desc = str(row[1] or "").strip()
            col_grav = str(row[2] or "").strip() if len(row) > 2 else ""

            # Detectar duplicacion en esta fila
            if es_pagina_duplicada(col_codigo):
                col_codigo = dedup_text(col_codigo)
                col_desc = dedup_text(col_desc)
                col_grav = dedup_text(col_grav)

            # pdfplumber mega-row: multiples entries separadas por \n
            codigos_lines = col_codigo.split('\n')
            desc_lines = col_desc.split('\n') if col_desc else []
            grav_lines = col_grav.split('\n') if col_grav else []

            # Matching posicional: solo subpartidas consumen gravamen
            grav_idx = 0
            desc_idx = 0

            for code_line in codigos_lines:
                code_line = code_line.strip()
                if not code_line:
                    continue

                # Limpiar posibles artefactos residuales
                code_line = re.sub(r'\s+', '', code_line)

                if PATRON_SUBPARTIDA.match(code_line):
                    # Es subpartida -> consume un gravamen
                    grav_val = ""
                    if grav_idx < len(grav_lines):
                        grav_val = grav_lines[grav_idx].strip()
                        grav_idx += 1

                    # Obtener descripcion correspondiente
                    desc_val = ""
                    if desc_idx < len(desc_lines):
                        desc_val = desc_lines[desc_idx].strip()
                        desc_idx += 1

                    # Validar gravamen (debe ser numero entero)
                    if grav_val and re.match(r'^\d+$', grav_val):
                        gravamenes[code_line] = grav_val

                    if desc_val:
                        descripciones[code_line] = desc_val

                elif PATRON_HEADING.match(code_line):
                    # Es heading -> NO consume gravamen pero si descripcion
                    if desc_idx < len(desc_lines):
                        desc_idx += 1
                else:
                    # Otro texto (notas, etc) -> avanzar desc si hay
                    if desc_idx < len(desc_lines):
                        desc_idx += 1

    return gravamenes, descripciones


def extraer_todo_pdf():
    """Extrae TODOS los gravamenes del PDF usando tabla extraction."""
    import pdfplumber

    if not os.path.isfile(PDF_PATH):
        print(f"[ERROR] PDF no encontrado: {PDF_PATH}")
        return {}, {}

    todos_grav = {}
    todas_desc = {}
    t0 = time.time()

    with pdfplumber.open(PDF_PATH) as pdf:
        total = len(pdf.pages)
        print(f"[PDF] {total} paginas")

        for i, page in enumerate(pdf.pages):
            if (i + 1) % 50 == 0:
                print(f"  Pagina {i+1}/{total}... ({len(todos_grav)} gravamenes)")

            grav, desc = extraer_tabla_pagina(page)
            todos_grav.update(grav)
            todas_desc.update(desc)

    t1 = time.time()
    print(f"[PDF] Extraidos {len(todos_grav)} gravamenes en {t1-t0:.1f}s")
    return todos_grav, todas_desc


def herencia_subpartida(codigos_cache, gravamenes_pdf):
    """Para codigos sin gravamen, hereda de la subpartida padre mas cercana.

    Jerarquia: XXXX.XX.00 -> XXXX.00.00 -> promedio de hermanos
    """
    heredados = {}

    for codigo in codigos_cache:
        if not PATRON_SUBPARTIDA.match(codigo):
            continue
        # Ya tiene gravamen en PDF?
        if codigo in gravamenes_pdf:
            continue

        # Intentar herencia de subpartida padre (.00)
        base6 = codigo[:7]  # XXXX.XX
        padre_00 = base6 + ".00"
        if padre_00 != codigo and padre_00 in gravamenes_pdf:
            heredados[codigo] = {
                "gravamen": gravamenes_pdf[padre_00],
                "fuente": f"herencia:{padre_00}"
            }
            continue

        # Intentar herencia de partida (.00.00)
        base4 = codigo[:4]  # XXXX
        padre_0000 = base4 + ".00.00"
        if padre_0000 != codigo and padre_0000 in gravamenes_pdf:
            heredados[codigo] = {
                "gravamen": gravamenes_pdf[padre_0000],
                "fuente": f"herencia:{padre_0000}"
            }
            continue

        # Buscar hermanos (mismo XXXX.XX.xx) que tengan gravamen
        hermanos_grav = []
        for c, g in gravamenes_pdf.items():
            if c[:7] == base6 and c != codigo:
                hermanos_grav.append(int(g))

        if hermanos_grav:
            # Usar el gravamen mas comun entre hermanos
            from collections import Counter
            grav_comun = Counter(hermanos_grav).most_common(1)[0][0]
            heredados[codigo] = {
                "gravamen": str(grav_comun),
                "fuente": f"hermanos:{base6}"
            }

    return heredados


def extraer_gravamen_de_desc(desc):
    """Extrae gravamen del final de una descripcion del cache."""
    m = re.search(r'\s+(\d+)\s*$', desc.strip())
    return m.group(1) if m else None


def reparar_cache(dry_run=False, full_extract=False):
    """Proceso principal de reparacion."""
    print("=" * 60)
    print("REPARADOR DE CACHE — Extraccion por tabla posicional")
    print("=" * 60)

    # Cargar datos
    cache = cargar_cache()
    codigos_cache = cache.get("codigos", {})
    bl = cargar_blacklist()
    protegidos = set(bl.get("correcciones", {}).keys())

    print(f"\nCache actual: {len(codigos_cache)} codigos")
    print(f"Protegidos (blacklist): {len(protegidos)}")

    # Identificar codigos sin gravamen
    sin_grav = []
    con_grav = []
    for codigo, desc in codigos_cache.items():
        if extraer_gravamen_de_desc(desc) is None:
            sin_grav.append(codigo)
        else:
            con_grav.append(codigo)

    print(f"Con gravamen: {len(con_grav)}")
    print(f"Sin gravamen: {len(sin_grav)}")

    if not sin_grav and not full_extract:
        print("\nTodos los codigos tienen gravamen. Nada que reparar.")
        return 0

    # Extraer gravamenes del PDF por tabla
    print(f"\n--- Extrayendo del PDF por tabla ---")
    gravamenes_pdf, descripciones_pdf = extraer_todo_pdf()

    # Calcular herencia para codigos huerfanos
    print(f"\n--- Calculando herencia de subpartidas ---")
    heredados = herencia_subpartida(codigos_cache, gravamenes_pdf)
    print(f"Herencia calculada para {len(heredados)} codigos")

    # Aplicar reparaciones
    reparados = 0
    reparaciones_log = []

    for codigo in sin_grav:
        if codigo in protegidos:
            continue

        gravamen = None
        fuente = ""

        # Prioridad 1: gravamen directo del PDF tabla
        if codigo in gravamenes_pdf:
            gravamen = gravamenes_pdf[codigo]
            fuente = "tabla-pdf"

        # Prioridad 2: herencia de subpartida
        elif codigo in heredados:
            gravamen = heredados[codigo]["gravamen"]
            fuente = heredados[codigo]["fuente"]

        if gravamen is not None:
            desc_actual = codigos_cache[codigo]
            desc_nueva = f"{desc_actual.strip()} {gravamen}"

            reparaciones_log.append({
                "codigo": codigo,
                "gravamen": gravamen,
                "fuente": fuente,
                "desc_antes": desc_actual[:60],
                "desc_despues": desc_nueva[:60]
            })

            if not dry_run:
                codigos_cache[codigo] = desc_nueva

            reparados += 1

    # Full extract: tambien actualizar descripciones incompletas
    desc_mejoradas = 0
    if full_extract:
        for codigo, desc_pdf in descripciones_pdf.items():
            if codigo in protegidos or codigo not in codigos_cache:
                continue
            desc_actual = codigos_cache[codigo]
            # Si la descripcion del PDF es mas completa, usar esa
            if len(desc_pdf) > len(desc_actual) + 10:
                grav = gravamenes_pdf.get(codigo, extraer_gravamen_de_desc(desc_actual))
                if grav:
                    desc_limpia = re.sub(r'\s+', ' ', desc_pdf).strip()
                    desc_limpia = re.sub(r'[^\x20-\x7E\xC0-\xFF\u00A0-\u024F]', '', desc_limpia)
                    if desc_limpia and not dry_run:
                        codigos_cache[codigo] = f"{desc_limpia} {grav}"
                        desc_mejoradas += 1

    # Guardar
    if not dry_run and reparados > 0:
        cache["codigos"] = codigos_cache
        cache["ultima_reparacion_tabla"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        cache["reparaciones_tabla"] = cache.get("reparaciones_tabla", 0) + reparados
        cache["metodo"] = "pdfplumber tabla-posicional + herencia + text (0% IA)"
        guardar_cache(cache)

    # Reporte
    print(f"\n{'='*60}")
    print(f"RESULTADO {'(DRY RUN)' if dry_run else ''}")
    print(f"{'='*60}")
    print(f"Reparados con gravamen: {reparados}")
    if full_extract:
        print(f"Descripciones mejoradas: {desc_mejoradas}")
    print(f"Sin resolver: {len(sin_grav) - reparados}")
    print(f"Protegidos (intocados): {len(protegidos)}")

    # Distribucion de fuentes
    fuentes = {}
    for r in reparaciones_log:
        f = r["fuente"].split(":")[0]
        fuentes[f] = fuentes.get(f, 0) + 1
    if fuentes:
        print(f"\nFuente de gravamenes:")
        for f, c in sorted(fuentes.items(), key=lambda x: -x[1]):
            print(f"  {f}: {c}")

    # Muestra de reparaciones
    if reparaciones_log:
        print(f"\nMuestra de reparaciones (primeros 15):")
        for r in reparaciones_log[:15]:
            print(f"  {r['codigo']} -> {r['gravamen']}% ({r['fuente']})")

    # Re-auditar
    sin_grav_final = sum(
        1 for c, d in codigos_cache.items()
        if extraer_gravamen_de_desc(d) is None
    )
    print(f"\nSalud post-reparacion:")
    print(f"  Total codigos: {len(codigos_cache)}")
    print(f"  Sin gravamen: {sin_grav_final}")
    print(f"  Cobertura: {100*(1 - sin_grav_final/len(codigos_cache)):.1f}%")
    print(f"{'='*60}")

    return reparados


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Reparador Cache Arancel - Tabla Posicional")
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar que cambiaria")
    parser.add_argument("--full-extract", action="store_true", help="Re-extraer descripciones tambien")
    args = parser.parse_args()

    reparar_cache(dry_run=args.dry_run, full_extract=args.full_extract)


if __name__ == "__main__":
    main()
