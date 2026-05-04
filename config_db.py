"""
config_db.py — Mapeo de columnas reales en arancel_rd.db.
Generado post-Orden 1 (PRAGMA table_info) + Orden 2 (ALTER TABLE).
Los 7 modulos R1-R7 y cualquier script nuevo deben importar de aqui
en vez de hardcodear nombres de columna.
Base legal: Decreto 36-22, Ley 11-92 Titulo IV.
"""
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "capa1_sqlite", "arancel_rd.db")
TABLA_PRINCIPAL = "codigos"

# Mapeo: nombre logico → nombre real en la tabla
COLUMNAS = {
    "codigo_son":   "son",           # PK — codigo SON formato XXXX.XX.XX
    "descripcion":  "descripcion",   # descripcion oficial del arancel
    "capitulo":     None,            # derivado: substr(son,1,2)
    "seccion":      None,            # derivado por logica Python (ver validador_son.py)
    "dai_pct":      "dai_pct",       # DAI% — Decreto 36-22 (REAL, poblado por poblar_gravamenes.py)
    "itbis_pct":    "itbis_pct",     # ITBIS% — Ley 11-92 Art. 335 (REAL)
    "isc_pct":      "isc_pct",       # ISC% — Ley 11-92 Arts. 361-382 (REAL)
    "gravamen_txt": "gravamen",      # columna original TEXT — mantener para compatibilidad
    "itbis_txt":    "itbis",         # columna original TEXT (puede decir EXENTO)
    "isc_txt":      "isc",           # columna original TEXT (puede decir NO APLICA)
    "permisos":     "permisos",      # entidades reguladoras por capitulo
    "notas_legales":"notas_legales", # referencias a notas SA aplicables
    "fuente":       "fuente",        # origen del dato (pdfplumber)
}

# Columnas de gravamen tipadas disponibles (post ALTER TABLE Orden 2)
GRAVAMENES_TIPADOS = True

# IDs de las 7 BDs de Notion (Capa 2)
NOTION_DB_IDS = {
    "fichas_merceologicas": "34c35f1c-d8ea-8190-9772-e0e3fefd8513",
    "jurisprudencia_dga":   "34c35f1c-d8ea-81d1-a487-d2d46d65d9b0",
    "sops_aduanas":         "34c35f1c-d8ea-81da-8666-df9b5403bc66",
    "bd_valoracion":        "a29f968b-8976-4d39-86c3-55041130969d",
    "bd_regimenes":         "6f5a3d75-f636-42cd-8639-b44d565cdff8",
    "bd_vucerd":            "4857355c-e95c-4b14-abe3-9e6f0efaad34",
    "bd_origen_drcafta":    "df5f1b0b-3cda-420d-8f54-8bf86ffc166d",
}

# Directorio de PDFs locales por cuaderno
PDF_BASE = os.path.join(
    os.path.dirname(__file__), "notebooklm_skill", "data", "fuentes_nomenclatura"
)

# Directorio de CSVs generados
CSV_BASE = os.path.join(os.path.dirname(__file__), "csv")
