#!/usr/bin/env python3
"""
Construye arancel_rd.db (SQLite FTS5) desde:
  1. arancel_cache.json  — 7,616 codigos pdfplumber (fuente primaria)
  2. isc_lookup.json     — flags ISC por capitulo
  3. PDF opcional        — re-extraccion para codigos faltantes

Uso: python build_arancel_db.py [--pdf]
"""
import json, os, re, sqlite3, sys
from decimal import Decimal, InvalidOperation
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_DATA = os.path.join(_ROOT, "notebooklm_skill", "data", "fuentes_nomenclatura")

DB_PATH     = os.path.join(_HERE, "arancel_rd.db")
CACHE_PATH  = os.path.join(_DATA, "arancel_cache.json")
ISC_PATH    = os.path.join(_DATA, "isc_lookup.json")
PDF_PATH    = os.path.join(_DATA, "Arancel 7ma enmienda de la republica dominicana.pdf")
MANUAL_PATH = os.path.join(_DATA, "correcciones_manuales.json")

# ITBIS estándar RD: 18% sobre la mayoría de bienes (Ley 253-12 Art. 335)
# Exenciones por capítulo (lista no exhaustiva — los más comunes)
_ITBIS_EXENTO_CAPS = {
    "01","02","03","04","07","08","09","10","11","12",  # alimentos crudos
    "25","27",  # minerales e hidrocarburos (ISC especial)
    "30",       # medicamentos (Ley 253-12 Art. 344 num 7)
    "49",       # libros/impresos
    "88","89",  # aeronaves y barcos (regímenes especiales)
}

_GRAV_RE = re.compile(r'\s+(\d+(?:\.\d+)?)\s*$')


def _parse_grav(desc: str):
    m = _GRAV_RE.search(desc.strip() if desc else "")
    if m:
        try:
            return Decimal(m.group(1))
        except InvalidOperation:
            pass
    return None


def _itbis_para(son: str, desc: str) -> str:
    cap = son[:2]
    if cap in _ITBIS_EXENTO_CAPS:
        return "EXENTO"
    desc_lower = (desc or "").lower()
    if any(w in desc_lower for w in ("medicamento", "vacuna", "insulina", "reactivo diagnos")):
        return "EXENTO"
    return "18"


def _isc_para(son: str, isc_data: dict) -> str:
    cap = son[:2]
    caps_isc = isc_data.get("capitulos_con_isc", {})
    if cap not in caps_isc:
        return "NO APLICA"
    entry = caps_isc[cap]
    # Buscar codigo especifico verificado dentro del capitulo
    codigos_ver = entry.get("codigos_verificados", {})
    if son in codigos_ver:
        tasa = codigos_ver[son]
        return str(tasa.get("tasa", "VERIFICAR")) if isinstance(tasa, dict) else str(tasa)
    partidas = entry.get("partidas_afectadas", [])
    partida = son[:7]  # XXXX.XX
    if any(p.startswith(partida) or partida.startswith(p[:7]) for p in partidas):
        tasas = entry.get("tasas", {})
        return str(list(tasas.values())[0]) if tasas else "VERIFICAR"
    return "NO APLICA"


def _crear_schema(con: sqlite3.Connection):
    con.executescript("""
        CREATE TABLE IF NOT EXISTS codigos (
            son         TEXT PRIMARY KEY,
            descripcion TEXT,
            gravamen    TEXT,
            itbis       TEXT,
            isc         TEXT,
            fuente      TEXT DEFAULT 'pdfplumber'
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS codigos_fts USING fts5(
            son,
            descripcion,
            content='codigos',
            content_rowid='rowid',
            tokenize='unicode61 remove_diacritics 1'
        );

        CREATE TRIGGER IF NOT EXISTS codigos_ai AFTER INSERT ON codigos BEGIN
            INSERT INTO codigos_fts(rowid, son, descripcion)
            VALUES (new.rowid, new.son, new.descripcion);
        END;
        CREATE TRIGGER IF NOT EXISTS codigos_au AFTER UPDATE ON codigos BEGIN
            INSERT INTO codigos_fts(codigos_fts, rowid, son, descripcion)
            VALUES ('delete', old.rowid, old.son, old.descripcion);
            INSERT INTO codigos_fts(rowid, son, descripcion)
            VALUES (new.rowid, new.son, new.descripcion);
        END;
        CREATE TRIGGER IF NOT EXISTS codigos_ad AFTER DELETE ON codigos BEGIN
            INSERT INTO codigos_fts(codigos_fts, rowid, son, descripcion)
            VALUES ('delete', old.rowid, old.son, old.descripcion);
        END;

        CREATE TABLE IF NOT EXISTS clasificaciones (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            son      TEXT,
            pregunta TEXT,
            resultado TEXT,
            usuario  TEXT DEFAULT 'sistema',
            ts       TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS rgi (
            numero INTEGER PRIMARY KEY,
            texto  TEXT
        );

        CREATE TABLE IF NOT EXISTS base_legal (
            id     TEXT PRIMARY KEY,
            titulo TEXT,
            texto  TEXT
        );

        CREATE TABLE IF NOT EXISTS build_meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
    """)


_RGI = {
    1: ("Las nomenclaturas de secciones, capítulos y subcapítulos tienen valor indicativo. "
        "La clasificación se determina legalmente por el texto de las partidas y de las notas de sección "
        "o de capítulo, y si no son contrarias a estas partidas y notas."),
    2: ("Cualquier referencia a un artículo en una partida comprende ese artículo incompleto o sin acabar, "
        "siempre que éste presente las características esenciales del artículo completo o acabado. "
        "También comprende el artículo completo o acabado, o inclasificado como tal en virtud del presente "
        "texto, cuando se presente desmontado o sin montar todavía."),
    3: ("Cuando una mercancía pudiera clasificarse, en principio, en dos o más partidas, se clasificará: "
        "a) La partida con descripción más específica. "
        "b) Las mezclas y manufacturas: la materia que les confiera carácter esencial. "
        "c) La partida situada en último lugar en orden numérico (última en el arancel)."),
    4: ("Las mercancías que no puedan clasificarse aplicando las reglas anteriores se clasificarán "
        "en la partida que comprenda los artículos con los que tengan mayor analogía."),
    5: ("Además de las disposiciones anteriores, las reglas siguientes se aplicarán a las mercancías "
        "que en ellas se mencionan: a) Estuches para cámaras fotográficas, instrumentos musicales, etc. "
        "clasificados con la mercancía que contienen cuando sean del tipo normalmente vendido con ellas. "
        "b) Los envases que contienen mercancías se clasifican con ellas cuando sean del tipo normalmente "
        "utilizado para ese tipo de mercancías."),
    6: ("La clasificación de mercancías en las subpartidas de una misma partida está determinada "
        "legalmente por el texto de estas subpartidas y de las notas de subpartida, así como, "
        "con las adaptaciones necesarias, por las reglas anteriores, entendiéndose que solo pueden "
        "compararse subpartidas del mismo nivel. Las notas de sección y de capítulo son también "
        "aplicables salvo disposición contraria."),
}

_BASE_LEGAL = [
    ("168-21", "Ley General de Aduanas", "Deroga Ley 3489 de 1953. Marco legal aduanero vigente RD."),
    ("755-22", "Decreto Reglamento Ley 168-21", "Reglamento de aplicación de la Ley 168-21."),
    ("36-22",  "Decreto Arancel Nacional", "Arancel Nacional vigente — 7ma Enmienda SA."),
    ("253-12", "Ley ITBIS e ISC", "Arts. 335-337 ITBIS (18%), Arts. 361-400 ISC."),
    ("14-93",  "Código Arancelario", "Marco histórico arancelario."),
    ("112-00", "Ley Hidrocarburos", "ISC especial Cap. 27."),
    ("SA-7",   "SA 7ma Enmienda OMA/WCO 2022", "21 Secciones, 96 Capítulos, 1224 Partidas."),
    ("357-05", "Resolución DGA DR-CAFTA", "Reglas de Origen DR-CAFTA."),
]


def main(con_pdf=False):
    print(f"[BUILD] Iniciando construcción de arancel_rd.db...")
    t0 = __import__("time").time()

    # 1. Cargar datos fuente
    print(f"[BUILD] Cargando arancel_cache.json...")
    with open(CACHE_PATH, encoding="utf-8") as f:
        cache_data = json.load(f)
    codigos_json = cache_data.get("codigos", {})
    print(f"[BUILD]   {len(codigos_json)} codigos en cache JSON")

    print(f"[BUILD] Cargando isc_lookup.json...")
    with open(ISC_PATH, encoding="utf-8") as f:
        isc_data = json.load(f)

    correcciones = {}
    if os.path.exists(MANUAL_PATH):
        with open(MANUAL_PATH, encoding="utf-8") as f:
            correcciones = json.load(f)
        print(f"[BUILD]   {len(correcciones)} correcciones manuales")

    # 2. Extraccion adicional del PDF (opcional, lenta)
    extras_pdf = {}
    if con_pdf and os.path.exists(PDF_PATH):
        print(f"[BUILD] Re-extrayendo PDF (esto tarda ~2-4 min)...")
        sys.path.insert(0, os.path.join(_ROOT, "notebooklm_skill", "scripts"))
        from expandir_cache_arancel import extraer_codigos_tabla, extraer_codigos_texto, extraer_con_words, dedup_text
        import pdfplumber, re as _re
        PAT = _re.compile(r'\b(\d{4}\.\d{2}\.\d{2})\b')
        with pdfplumber.open(PDF_PATH) as pdf:
            for i, page in enumerate(pdf.pages):
                if (i+1) % 100 == 0:
                    print(f"  pagina {i+1}/{len(pdf.pages)}, codigos extra={len(extras_pdf)}")
                for extractor in [extraer_codigos_tabla, extraer_codigos_texto, extraer_con_words]:
                    for k, v in extractor(page).items():
                        if k not in codigos_json and PAT.match(k):
                            extras_pdf[k] = v
        print(f"[BUILD]   {len(extras_pdf)} codigos nuevos desde PDF")

    # 3. Construir filas para SQLite
    todos = {**codigos_json, **extras_pdf}
    filas = []
    for son in sorted(todos):
        if not re.match(r'^\d{4}\.\d{2}\.\d{2}$', son):
            continue
        desc_raw = todos[son] or ""
        grav_dec  = _parse_grav(desc_raw)
        # Correcciones manuales tienen máxima prioridad
        if son in correcciones:
            grav_dec = Decimal(str(correcciones[son].get("gravamen", grav_dec or 0)))
        gravamen  = str(int(grav_dec)) if grav_dec is not None and grav_dec == grav_dec.to_integral_value() \
                    else (format(grav_dec.normalize(), "f") if grav_dec is not None else "")
        itbis     = _itbis_para(son, desc_raw)
        isc       = _isc_para(son, isc_data)
        fuente    = "manual" if son in correcciones else "pdfplumber"
        # Descripcion sin el gravamen al final
        desc_limpia = _GRAV_RE.sub("", desc_raw).strip() if desc_raw else ""
        filas.append((son, desc_limpia or desc_raw, gravamen, itbis, isc, fuente))

    # 4. Escribir SQLite
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    _crear_schema(con)

    con.executemany(
        "INSERT OR REPLACE INTO codigos(son,descripcion,gravamen,itbis,isc,fuente) VALUES(?,?,?,?,?,?)",
        filas
    )

    # RGI
    for num, texto in _RGI.items():
        con.execute("INSERT OR REPLACE INTO rgi(numero,texto) VALUES(?,?)", (num, texto))

    # Base legal
    for fila in _BASE_LEGAL:
        con.execute("INSERT OR REPLACE INTO base_legal(id,titulo,texto) VALUES(?,?,?)", fila)

    # Metadata
    con.execute("INSERT OR REPLACE INTO build_meta VALUES('build_ts',?)", (datetime.now().isoformat(),))
    con.execute("INSERT OR REPLACE INTO build_meta VALUES('total_codigos',?)", (str(len(filas)),))
    con.execute("INSERT OR REPLACE INTO build_meta VALUES('fuente_json',?)", (CACHE_PATH,))
    con.commit()

    # FTS rebuild
    con.execute("INSERT INTO codigos_fts(codigos_fts) VALUES('rebuild')")
    con.commit()
    con.close()

    t1 = __import__("time").time()
    size_kb = os.path.getsize(DB_PATH) / 1024
    print(f"\n{'='*50}")
    print(f"arancel_rd.db construido en {t1-t0:.1f}s")
    print(f"  Codigos cargados : {len(filas)}")
    print(f"  Tamaño DB        : {size_kb:.0f} KB")
    print(f"  Ruta             : {DB_PATH}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main(con_pdf="--pdf" in sys.argv)
