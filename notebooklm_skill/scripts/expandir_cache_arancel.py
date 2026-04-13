#!/usr/bin/env python3
"""
Expande arancel_cache.json extrayendo TODOS los codigos arancelarios
del PDF Arancel 7ma Enmienda usando pdfplumber (0% IA).

El PDF tiene codificacion doble (cada caracter aparece 2 veces).
Este script detecta y corrige ese patron antes de parsear.

Formato esperado de codigos: XXXX.XX.XX (8 digitos, patron nacional RD)
Cada entrada: "XXXX.XX.XX": "Descripcion Gravamen%"

Uso: python expandir_cache_arancel.py
"""

import json
import os
import re
import sys
import time

# Rutas
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data", "fuentes_nomenclatura")
PDF_PATH = os.path.join(DATA_DIR, "Arancel 7ma enmienda de la republica dominicana.pdf")
CACHE_PATH = os.path.join(DATA_DIR, "arancel_cache.json")
BACKUP_PATH = os.path.join(DATA_DIR, "arancel_cache_backup_666.json")

# Patron para codigo arancelario nacional RD: XXXX.XX.XX
PATRON_CODIGO = re.compile(r'\b(\d{4}\.\d{2}\.\d{2})\b')


def dedup_text(text):
    """Corrige texto con codificacion doble donde cada caracter aparece 2 veces.
    Ejemplo: '00330066..1111..0000' -> '0306.11.00'
    Solo aplica si se detecta el patron duplicado."""
    if not text:
        return text

    # Detectar si el texto tiene duplicacion: buscar patron XXYY donde X==Y
    # Patron tipico del PDF: cada caracter se repite
    doubled_pattern = re.compile(r'(\d)\1(\d)\1(\d)\1(\d)\1\.\.(\d)\1(\d)\1\.\.(\d)\1(\d)\1')
    if doubled_pattern.search(text):
        # Texto tiene duplicacion - corregir tomando 1 de cada 2 caracteres
        result = []
        i = 0
        while i < len(text):
            if i + 1 < len(text) and text[i] == text[i + 1]:
                result.append(text[i])
                i += 2
            else:
                result.append(text[i])
                i += 1
        return ''.join(result)
    return text


def extraer_codigos_tabla(page):
    """Extrae codigos de tablas estructuradas en una pagina."""
    codigos = {}
    tables = page.extract_tables()
    if not tables:
        return codigos

    for table in tables:
        for row in table:
            if not row or not row[0]:
                continue
            celda = dedup_text(str(row[0]).strip())
            match = PATRON_CODIGO.search(celda)
            if match:
                codigo = match.group(1)
                desc_parts = []
                for c in row[1:]:
                    if c and str(c).strip():
                        desc_parts.append(dedup_text(str(c).strip()))
                desc = " ".join(desc_parts) if desc_parts else celda
                desc = re.sub(r'\s+', ' ', desc).strip()
                if desc and len(desc) > 2:
                    codigos[codigo] = desc
    return codigos


def extraer_codigos_texto(page):
    """Extrae codigos del texto plano, manejando la codificacion doble."""
    codigos = {}
    text = page.extract_text()
    if not text:
        return codigos

    # Primero intentar deduplicar todo el texto
    text_clean = dedup_text(text)

    lines = text_clean.split('\n')
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        # Buscar codigo en cualquier parte de la linea
        match = PATRON_CODIGO.search(line)
        if match:
            codigo = match.group(1)
            # El resto de la linea despues del codigo es la descripcion
            rest = line[match.end():].strip()
            # Tambien considerar texto antes del codigo si es un guion
            prefix = line[:match.start()].strip()

            # Separar descripcion del gravamen (numero al final)
            grav_match = re.search(r'\s+(\d+(?:\.\d+)?)\s*%?\s*$', rest)
            if grav_match:
                desc = rest[:grav_match.start()].strip()
                gravamen = grav_match.group(1)
                if desc:
                    codigos[codigo] = f"{desc} {gravamen}"
                elif prefix:
                    codigos[codigo] = f"{prefix} {gravamen}"
            elif rest:
                codigos[codigo] = rest
            elif prefix and len(prefix) > 3:
                codigos[codigo] = prefix
            else:
                # Descripcion podria estar en la linea siguiente
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line and not PATRON_CODIGO.search(next_line):
                        codigos[codigo] = dedup_text(next_line)

    return codigos


def extraer_con_words(page):
    """Extraccion avanzada usando coordenadas de palabras individuales.
    Reconstruye lineas agrupando palabras por posicion Y."""
    codigos = {}
    words = page.extract_words(keep_blank_chars=False, extra_attrs=["fontname", "size"])
    if not words:
        return codigos

    # Agrupar palabras por linea (misma coordenada Y, tolerancia 3px)
    lines_dict = {}
    for w in words:
        y_key = round(w['top'] / 3) * 3  # Agrupar por intervalos de 3px
        if y_key not in lines_dict:
            lines_dict[y_key] = []
        lines_dict[y_key].append(w)

    # Ordenar palabras dentro de cada linea por posicion X
    for y_key in lines_dict:
        lines_dict[y_key].sort(key=lambda w: w['x0'])

    # Reconstruir lineas de texto
    for y_key in sorted(lines_dict.keys()):
        words_in_line = lines_dict[y_key]
        line_text = ' '.join(w['text'] for w in words_in_line)
        line_text = dedup_text(line_text.strip())

        match = PATRON_CODIGO.search(line_text)
        if match:
            codigo = match.group(1)
            rest = line_text[match.end():].strip()
            prefix = line_text[:match.start()].strip()

            grav_match = re.search(r'\s+(\d+(?:\.\d+)?)\s*%?\s*$', rest)
            if grav_match:
                desc = rest[:grav_match.start()].strip()
                gravamen = grav_match.group(1)
                full_desc = f"{desc} {gravamen}" if desc else f"{prefix} {gravamen}"
                if full_desc.strip():
                    codigos[codigo] = full_desc
            elif rest and len(rest) > 2:
                codigos[codigo] = rest

    return codigos


def main():
    if not os.path.exists(PDF_PATH):
        print(f"ERROR: PDF no encontrado: {PDF_PATH}")
        sys.exit(1)

    # Backup del cache actual solo si no existe el backup de 666
    if os.path.exists(CACHE_PATH) and not os.path.exists(BACKUP_PATH):
        import shutil
        shutil.copy2(CACHE_PATH, BACKUP_PATH)
        print(f"Backup creado: {BACKUP_PATH}")

    # Cargar cache original de 666 codigos como base
    codigos_base = {}
    if os.path.exists(BACKUP_PATH):
        with open(BACKUP_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            codigos_base = data.get('codigos', {})
        print(f"Cache base cargado: {len(codigos_base)} codigos")

    print(f"Abriendo PDF: {os.path.basename(PDF_PATH)}")
    t0 = time.time()

    import pdfplumber

    todos_codigos = dict(codigos_base)  # Empezar con la base de 666
    total_paginas = 0

    with pdfplumber.open(PDF_PATH) as pdf:
        total_paginas = len(pdf.pages)
        print(f"Total paginas: {total_paginas}")

        for i, page in enumerate(pdf.pages):
            if (i + 1) % 50 == 0 or i == 0:
                print(f"  Procesando pagina {i+1}/{total_paginas}... "
                      f"({len(todos_codigos)} codigos hasta ahora)")

            # Metodo 1: Tablas
            codigos_tabla = extraer_codigos_tabla(page)
            for k, v in codigos_tabla.items():
                if k not in todos_codigos or len(v) > len(todos_codigos.get(k, '')):
                    todos_codigos[k] = v

            # Metodo 2: Texto plano con dedup
            codigos_texto = extraer_codigos_texto(page)
            for k, v in codigos_texto.items():
                if k not in todos_codigos or len(v) > len(todos_codigos.get(k, '')):
                    todos_codigos[k] = v

            # Metodo 3: Words-based (mas robusto para PDFs complejos)
            codigos_words = extraer_con_words(page)
            for k, v in codigos_words.items():
                if k not in todos_codigos or len(v) > len(todos_codigos.get(k, '')):
                    todos_codigos[k] = v

    t1 = time.time()

    # Limpiar codigos invalidos
    codigos_limpios = {}
    for codigo, desc in sorted(todos_codigos.items()):
        if re.match(r'^\d{4}\.\d{2}\.\d{2}$', codigo):
            cap = int(codigo[:2])
            if 1 <= cap <= 99:
                desc_limpia = re.sub(r'\s+', ' ', str(desc)).strip()
                # Eliminar artefactos de dedup parcial
                desc_limpia = re.sub(r'[^\x20-\x7E\xC0-\xFF\u00A0-\u024F]', '', desc_limpia)
                if desc_limpia and len(desc_limpia) > 1:
                    codigos_limpios[codigo] = desc_limpia

    # Guardar nuevo cache
    cache = {
        "fuente": "Arancel 7ma enmienda de la republica dominicana.pdf",
        "paginas": total_paginas,
        "codigos_extraidos": len(codigos_limpios),
        "metodo": "pdfplumber tables + text + words con dedup (0% IA)",
        "fecha_extraccion": time.strftime("%Y-%m-%d"),
        "codigos": codigos_limpios
    }

    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    # Resumen
    caps = set(c[:2] for c in codigos_limpios)
    nuevos = len(codigos_limpios) - len(codigos_base)
    print(f"\n{'='*50}")
    print(f"EXTRACCION COMPLETADA en {t1-t0:.1f}s")
    print(f"  Codigos base: {len(codigos_base)}")
    print(f"  Codigos nuevos: {nuevos}")
    print(f"  Total codigos: {len(codigos_limpios)}")
    print(f"  Capitulos cubiertos: {len(caps)}/99")
    print(f"  Cache guardado: {CACHE_PATH}")
    print(f"{'='*50}")

    # Estadisticas por capitulo
    caps_count = {}
    for c in codigos_limpios:
        cap = c[:2]
        caps_count[cap] = caps_count.get(cap, 0) + 1

    print(f"\nTop 15 capitulos con mas codigos:")
    for cap, count in sorted(caps_count.items(), key=lambda x: -x[1])[:15]:
        print(f"  Cap {cap}: {count} codigos")


if __name__ == "__main__":
    main()
