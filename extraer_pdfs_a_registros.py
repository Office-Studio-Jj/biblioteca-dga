"""
extraer_pdfs_a_registros.py
Lee PDFs (y .docx si está disponible) de notebooklm_skill/data/fuentes_nomenclatura/
y genera 7 CSVs clasificados por cuaderno DGA.

Extracción 0% IA — texto literal de pdfplumber sin inferencias.
Base legal: Decreto 755-22 Art. 5 (sistema informático DGA).

Organización: AMGECO Automatización y Gestión SRL
"""

import csv
import os
from datetime import datetime

try:
    import pdfplumber
    PDF_OK = True
except ImportError:
    PDF_OK = False
    print("[AVISO] pdfplumber no instalado. Instalar: pip install pdfplumber")

try:
    from docx import Document as DocxDocument
    DOCX_OK = True
except ImportError:
    DOCX_OK = False

# ── Rutas ────────────────────────────────────────────────────────────────────
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
PDF_DIR   = os.path.join(BASE_DIR, "notebooklm_skill", "data", "fuentes_nomenclatura")
CSV_DIR   = os.path.join(BASE_DIR, "csv")

# ── Definición de cuadernos ───────────────────────────────────────────────────
# Cada cuaderno: (nombre_csv, bd_notion, patrones_en_nombre_archivo, tipo_doc, base_legal)
CUADERNOS = [
    {
        "id":          "cuaderno_1_aforo",
        "csv":         "cuaderno_1_aforo_registros.csv",
        "bd_notion":   "SOPs Aduanas",
        "patrones":    ["aforo", "kioto", "incoterm", "despacho", "convenio", "declaracion", "levante"],
        "tipo":        "SOP Aduanero",
        "base_legal":  "Ley 168-21 Cap. VII (Aforo), Decreto 755-22",
    },
    {
        "id":          "cuaderno_2_legal",
        "csv":         "cuaderno_2_legal_registros.csv",
        "bd_notion":   "Jurisprudencia DGA",
        "patrones":    ["ley_168", "decreto_755", "codigo_tributario", "ilicitos", "recurso", "sancion", "liquidacion"],
        "tipo":        "Marco Legal",
        "base_legal":  "Ley 168-21, Decreto 755-22, Ley 11-92",
    },
    {
        "id":          "cuaderno_3_regimenes",
        "csv":         "cuaderno_3_regimenes_registros.csv",
        "bd_notion":   "BD-Regímenes",
        "patrones":    ["regimen"],
        "tipo":        "Régimen Aduanero",
        "base_legal":  "Ley 168-21 Cap. V Arts. 118-180, Ley 8-90",
    },
    {
        "id":          "cuaderno_4_nomenclaturas",
        "csv":         "cuaderno_4_nomenclaturas_registros.csv",
        "bd_notion":   "Fichas Merceológicas",
        "patrones":    ["arancel", "clasificacion", "nomenclatura", "rgi", "partida", "sa"],
        "tipo":        "Nomenclatura SA",
        "base_legal":  "Decreto 755-22, Decreto 36-22, SA 7ma Enmienda OMA 2022",
    },
    {
        "id":          "cuaderno_5_origen",
        "csv":         "cuaderno_5_origen_registros.csv",
        "bd_notion":   "BD-Origen DR-CAFTA",
        "patrones":    ["origen", "cafta", "integracion"],
        "tipo":        "Certificado de Origen",
        "base_legal":  "Ley 424-06, Resolución DGA 357-05",
    },
    {
        "id":          "cuaderno_6_vucerd",
        "csv":         "cuaderno_6_vucerd_registros.csv",
        "bd_notion":   "BD-VUCERD",
        "patrones":    ["vucerd"],
        "tipo":        "Trámite VUCERD",
        "base_legal":  "Ley 126-02, Ley 168-21 Arts. 15-17",
    },
    {
        "id":          "cuaderno_7_valoracion",
        "csv":         "cuaderno_7_valoracion_registros.csv",
        "bd_notion":   "BD-Valoración",
        "patrones":    ["valora"],
        "tipo":        "Valoración Aduanera",
        "base_legal":  "Ley 168-21 Cap. VI, Acuerdo OMC Art. VII",
    },
]

# Índice cuaderno por defecto (cuaderno 4 — nomenclaturas)
CUADERNO_DEFAULT_IDX = 3

COLUMNAS_CSV = [
    "titulo", "contenido_resumen", "tipo_documento",
    "base_legal", "cuaderno", "fecha_procesamiento",
]


def _normalizar(nombre: str) -> str:
    """Convierte nombre de archivo a minúsculas sin tildes para comparación."""
    reemplazos = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n"}
    n = nombre.lower()
    for orig, rep in reemplazos.items():
        n = n.replace(orig, rep)
    return n


def _detectar_cuaderno(nombre_archivo: str) -> dict:
    """Devuelve el cuaderno al que pertenece el archivo según su nombre."""
    norm = _normalizar(nombre_archivo)
    for cuaderno in CUADERNOS:
        for patron in cuaderno["patrones"]:
            if patron in norm:
                return cuaderno
    return CUADERNOS[CUADERNO_DEFAULT_IDX]


def _extraer_texto_pdf(ruta: str) -> str:
    """Extrae texto plano de un PDF con pdfplumber. Retorna '' si falla."""
    if not PDF_OK:
        return ""
    try:
        texto_paginas = []
        with pdfplumber.open(ruta) as pdf:
            for pagina in pdf.pages:
                t = pagina.extract_text()
                if t:
                    texto_paginas.append(t)
        return "\n".join(texto_paginas)
    except Exception as exc:
        print(f"  [ERROR PDF] {os.path.basename(ruta)}: {exc}")
        return ""


def _extraer_texto_docx(ruta: str) -> str:
    """Extrae texto de un .docx. Retorna '' si python-docx no está disponible."""
    if not DOCX_OK:
        return ""
    try:
        doc = DocxDocument(ruta)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as exc:
        print(f"  [ERROR DOCX] {os.path.basename(ruta)}: {exc}")
        return ""


def _procesar_archivo(ruta: str) -> str:
    """Despacha la extracción según extensión del archivo."""
    ext = os.path.splitext(ruta)[1].lower()
    if ext == ".pdf":
        return _extraer_texto_pdf(ruta)
    if ext == ".docx":
        return _extraer_texto_docx(ruta)
    return ""


def extraer_todo() -> dict:
    """
    Recorre PDF_DIR, clasifica cada archivo en su cuaderno y escribe los CSVs.
    Retorna dict con estadísticas por cuaderno.
    """
    os.makedirs(CSV_DIR, exist_ok=True)

    # Acumuladores: {cuaderno_id: [filas]}
    acumulador: dict[str, list] = {c["id"]: [] for c in CUADERNOS}

    archivos = [
        f for f in os.listdir(PDF_DIR)
        if os.path.splitext(f)[1].lower() in (".pdf", ".docx")
    ]

    if not archivos:
        print(f"No se encontraron PDF/DOCX en {PDF_DIR}")
        return {}

    print(f"Archivos encontrados: {len(archivos)}")

    for nombre in sorted(archivos):
        ruta    = os.path.join(PDF_DIR, nombre)
        cuad    = _detectar_cuaderno(nombre)
        texto   = _procesar_archivo(ruta)
        resumen = texto[:500].replace("\n", " ").strip() if texto else "(sin texto extraído)"

        fila = {
            "titulo":              os.path.splitext(nombre)[0],
            "contenido_resumen":   resumen,
            "tipo_documento":      cuad["tipo"],
            "base_legal":          cuad["base_legal"],
            "cuaderno":            cuad["bd_notion"],
            "fecha_procesamiento": datetime.now().isoformat(timespec="seconds"),
        }
        acumulador[cuad["id"]].append(fila)
        print(f"  [{cuad['id']}] {nombre}")

    # ── Escribir CSVs ────────────────────────────────────────────────────────
    estadisticas = {}
    total_filas  = 0

    for cuad in CUADERNOS:
        filas   = acumulador[cuad["id"]]
        ruta_csv = os.path.join(CSV_DIR, cuad["csv"])

        with open(ruta_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNAS_CSV)
            writer.writeheader()
            writer.writerows(filas)

        estadisticas[cuad["id"]] = {
            "archivos": len(filas),
            "csv":      ruta_csv,
        }
        total_filas += len(filas)
        print(f"\n{cuad['id']}: {len(filas)} archivo(s) -> {ruta_csv}")

    print(f"\nTotal filas escritas: {total_filas}")
    return estadisticas


if __name__ == "__main__":
    extraer_todo()
