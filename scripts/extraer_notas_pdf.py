#!/usr/bin/env python3
"""
Extrae notas legales de secciones y capitulos del PDF
'notas legales arancel rd.pdf' (7ma Enmienda SA, 133 paginas).

El PDF contiene un unico objeto JSON distribuido en multiples paginas.
Este script lo reconstruye, parsea y genera un archivo limpio con
la estructura de secciones y capitulos separada.

Salida: notebooklm_skill/data/fuentes_nomenclatura/notas_legales_completas.json
"""

import json
import re
import sys
import os

try:
    import pdfplumber
except ImportError:
    print("ERROR: pdfplumber no instalado. Ejecutar: pip install pdfplumber")
    sys.exit(1)

# Rutas
PDF_PATH = r"C:\Users\Usuario\Desktop\INFORME CHATS-CLAUDE\notas legales arancel rd.pdf"
OUTPUT_DIR = r"C:\Users\Usuario\Desktop\conectar a claude\biblioteca-dga\notebooklm_skill\data\fuentes_nomenclatura"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "notas_legales_completas.json")


def extraer_texto_completo(pdf_path: str) -> str:
    """Extrae texto de todas las paginas del PDF y lo concatena."""
    print(f"Abriendo PDF: {pdf_path}")
    texto_completo = []
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        print(f"Total paginas: {total}")
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text:
                texto_completo.append(text)
            if (i + 1) % 20 == 0:
                print(f"  Procesadas {i + 1}/{total} paginas...")
    print(f"Extraccion completa. Caracteres totales: {sum(len(t) for t in texto_completo)}")
    return "\n".join(texto_completo)


def limpiar_texto_json(texto: str) -> str:
    """Limpia texto pdfplumber para producir JSON valido en un solo paso.

    Problemas que resuelve:
    - Form feeds y numeros de pagina sueltos
    - Newlines/tabs literales dentro de strings JSON
    - Backslashes sueltos (no seguidos de un escape JSON valido)
    """
    texto = texto.replace("\f", "")
    texto = re.sub(r'\n\d{1,3}\n', '\n', texto)

    _VALID_AFTER_BACKSLASH = set('"\\bfnrtu/')
    result = []
    in_string = False
    i = 0
    length = len(texto)

    while i < length:
        ch = texto[i]

        if not in_string:
            if ch == '"':
                in_string = True
            result.append(ch)
            i += 1
            continue

        # Dentro de un string JSON
        if ch == '"':
            in_string = False
            result.append(ch)
            i += 1
            continue

        if ch == '\\':
            if i + 1 < length:
                next_ch = texto[i + 1]
                if next_ch in _VALID_AFTER_BACKSLASH:
                    result.append('\\')
                    result.append(next_ch)
                    i += 2
                    continue
                elif next_ch == '\n':
                    result.append('\\n')
                    i += 2
                    continue
                elif next_ch == '\r':
                    i += 2
                    continue
                else:
                    result.append('\\\\')
                    i += 1
                    continue
            else:
                result.append('\\\\')
                i += 1
                continue

        if ch == '\n':
            result.append('\\n')
            i += 1
            continue
        if ch == '\r':
            i += 1
            continue
        if ch == '\t':
            result.append('\\t')
            i += 1
            continue
        if ord(ch) < 32:
            i += 1
            continue

        result.append(ch)
        i += 1

    return "".join(result)


def parsear_json_robusto(texto: str) -> dict:
    """Parsea el JSON ya limpiado por limpiar_texto_json."""
    inicio = texto.find('{"metadata"')
    if inicio == -1:
        inicio = texto.find('{')
    if inicio == -1:
        raise ValueError("No se encontro inicio de JSON en el texto")

    texto_json = texto[inicio:]

    try:
        return json.loads(texto_json)
    except json.JSONDecodeError as e:
        print(f"Parse fallo en posicion {e.pos}: {e.msg}")
        start = max(0, e.pos - 80)
        end = min(len(texto_json), e.pos + 80)
        print(f"Contexto: ...{repr(texto_json[start:end])}...")
        raise ValueError(
            f"No se pudo parsear JSON. Error: {e.msg} en posicion {e.pos}"
        )


def clasificar_notas(notas_lista: list) -> dict:
    """Clasifica las notas por tipo (legales, adicionales, subpartida).

    Elimina duplicados exactos que el PDF a veces genera.
    """
    notas_legales = []
    notas_adicionales = []
    notas_subpartida = []

    vistos = set()  # para deduplicar

    for nota in notas_lista:
        tipo = nota.get("tipo", "").lower()
        texto = nota.get("texto", "").strip()

        if not texto:
            continue

        # Deduplicar por hash del texto
        hash_texto = hash(texto)
        if hash_texto in vistos:
            continue
        vistos.add(hash_texto)

        if "subpartida" in tipo:
            notas_subpartida.append(texto)
        elif "adicional" in tipo:
            notas_adicionales.append(texto)
        else:
            # Notas de Seccion, Notas de Capitulo, etc.
            notas_legales.append(texto)

    return {
        "notas_legales": notas_legales,
        "notas_adicionales": notas_adicionales,
        "notas_subpartida": notas_subpartida,
    }


def estructurar_salida(data: dict) -> dict:
    """Convierte el JSON crudo del PDF al formato de salida deseado."""
    resultado = {
        "_meta": {
            "fuente": "Arancel de Aduanas de la Republica Dominicana - 7ma Enmienda SA (2022)",
            "base_legal": "Ley 14-93, modificada por Ley 146-00, Art. 4",
            "extraido_de": "notas legales arancel rd.pdf (133 paginas, 784KB)",
            "script": "scripts/extraer_notas_pdf.py",
            "total_secciones": 0,
            "total_capitulos": 0,
            "secciones_con_notas": 0,
            "capitulos_con_notas": 0,
        },
        "rgi": data.get("rgi", ""),
        "secciones": {},
        "capitulos": {},
    }

    # Procesar secciones
    secciones_raw = data.get("secciones", {})
    for num_seccion, sec_data in secciones_raw.items():
        titulo = sec_data.get("titulo", "").strip()
        notas_raw = sec_data.get("notas", [])

        clasificadas = clasificar_notas(notas_raw)

        entrada = {
            "titulo": titulo,
            **clasificadas,
        }

        # Quitar claves vacias
        entrada = {k: v for k, v in entrada.items() if v}
        if "titulo" not in entrada:
            entrada["titulo"] = ""

        resultado["secciones"][num_seccion] = entrada

    # Procesar capitulos
    capitulos_raw = data.get("capitulos", {})
    for num_cap, cap_data in capitulos_raw.items():
        titulo = cap_data.get("titulo", "").strip()
        notas_raw = cap_data.get("notas", [])

        clasificadas = clasificar_notas(notas_raw)

        entrada = {
            "titulo": titulo,
            **clasificadas,
        }

        # Quitar claves vacias
        entrada = {k: v for k, v in entrada.items() if v}
        if "titulo" not in entrada:
            entrada["titulo"] = ""

        resultado["capitulos"][num_cap] = entrada

    # Estadisticas
    resultado["_meta"]["total_secciones"] = len(resultado["secciones"])
    resultado["_meta"]["total_capitulos"] = len(resultado["capitulos"])
    resultado["_meta"]["secciones_con_notas"] = sum(
        1 for s in resultado["secciones"].values()
        if s.get("notas_legales") or s.get("notas_adicionales")
    )
    resultado["_meta"]["capitulos_con_notas"] = sum(
        1 for c in resultado["capitulos"].values()
        if c.get("notas_legales") or c.get("notas_adicionales") or c.get("notas_subpartida")
    )

    return resultado


def main():
    # Verificar que el PDF existe
    if not os.path.exists(PDF_PATH):
        print(f"ERROR: No se encuentra el PDF en: {PDF_PATH}")
        sys.exit(1)

    # Verificar directorio de salida
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Paso 1: Extraer texto
    texto = extraer_texto_completo(PDF_PATH)

    # Paso 2: Limpiar
    texto = limpiar_texto_json(texto)

    # Paso 3: Parsear JSON
    print("\nParseando JSON...")
    data = parsear_json_robusto(texto)
    print("JSON parseado correctamente.")

    # Paso 4: Estructurar salida
    print("\nEstructurando salida...")
    resultado = estructurar_salida(data)

    # Paso 5: Guardar
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    # Resumen
    meta = resultado["_meta"]
    print(f"\n{'='*60}")
    print(f"EXTRACCION COMPLETADA")
    print(f"{'='*60}")
    print(f"Archivo: {OUTPUT_FILE}")
    print(f"Secciones: {meta['total_secciones']} ({meta['secciones_con_notas']} con notas)")
    print(f"Capitulos: {meta['total_capitulos']} ({meta['capitulos_con_notas']} con notas)")
    print(f"Tamano: {os.path.getsize(OUTPUT_FILE) / 1024:.1f} KB")

    # Listar secciones
    print(f"\nSecciones encontradas:")
    for num, sec in sorted(resultado["secciones"].items(), key=lambda x: x[0]):
        n_notas = len(sec.get("notas_legales", [])) + len(sec.get("notas_adicionales", []))
        titulo = sec.get("titulo", "")[:60]
        print(f"  {num:>4}: {titulo} ({n_notas} notas)")

    # Listar capitulos
    print(f"\nCapitulos encontrados:")
    for num, cap in sorted(resultado["capitulos"].items(), key=lambda x: x[0]):
        n_notas = (
            len(cap.get("notas_legales", []))
            + len(cap.get("notas_adicionales", []))
            + len(cap.get("notas_subpartida", []))
        )
        titulo = cap.get("titulo", "")[:60]
        print(f"  {num:>4}: {titulo} ({n_notas} notas)")


if __name__ == "__main__":
    main()
