#!/usr/bin/env python3
"""
Construye indice FTS5 sobre los 11 PDFs de biblioteca-nomenclatura
(excluye el Arancel 7ma, que ya esta en tabla 'codigos').

Salida: tablas `biblioteca` + `biblioteca_fts` en arancel_rd.db
Uso: python capa1_sqlite/build_biblioteca_fts.py
"""
import json
import os
import re
import sqlite3
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_PDF_DIR = os.path.join(_ROOT, "notebooklm_skill", "data", "fuentes_nomenclatura")
DB_PATH = os.path.join(_HERE, "arancel_rd.db")

# PDFs a indexar — el Arancel principal se excluye (ya esta en tabla codigos)
PDFS_BIBLIOTECA = [
    "21115-18311 - 01171 (Ley 14-93 sobre Arancel de Aduanas).pdf",
    "146-00_de_reforma_arancelaria.pdf",
    "2da parte de clasificacion arancelaria de las mercancias.pdf",
    "CLASIFICACION ARANCELARIA DE LAS MERCANCIAS.pdf",
    "ESPECIFICACIONES TÉCNICAS PARA IDENTIFICAR CARGAS DE IMPUESTOS.pdf",
    "Guía Estrategias Clasificar Mercancías.pdf",
    "Partidas y subpartidas de tipo obligatorio con ejemplos.pdf",
    "estructura de codificacion del sistema armonizado.pdf",
    "procedimiento para aplicar las reglas generales de interpretacion del sistema armonizado de la nomenclatura.pdf",
    "reglas generals de interpretacion del sistema armonizado de designacion y codificacion de mercancias con ejemplos.pdf",
    "PROTOCOLO_MERCEOLOGICO_NOMENCLATURA-uso intrno como codigo.pdf",
]

# Chunks: ~800 palabras con 150 de overlap
CHUNK_WORDS = 800
OVERLAP_WORDS = 150

# Detector de capitulos mencionados en el chunk
_CAP_RE = re.compile(r'\b(?:cap(?:i|í)tulo|cap\.?)\s*(\d{1,2})\b', re.IGNORECASE)
_SON_RE = re.compile(r'\b(\d{4}\.\d{2}\.\d{2}(?:\.\d{2})?)\b')


def _crear_schema(con: sqlite3.Connection):
    con.executescript("""
        CREATE TABLE IF NOT EXISTS biblioteca (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            pdf_nombre  TEXT,
            pagina      INTEGER,
            chunk_idx   INTEGER,
            texto       TEXT,
            capitulos   TEXT,     -- capitulos mencionados: "85,87"
            codigos_son TEXT      -- codigos SON mencionados: "8543.70.90"
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS biblioteca_fts USING fts5(
            texto,
            pdf_nombre,
            capitulos,
            codigos_son,
            content='biblioteca',
            content_rowid='id',
            tokenize='unicode61 remove_diacritics 1'
        );

        CREATE TRIGGER IF NOT EXISTS biblioteca_ai AFTER INSERT ON biblioteca BEGIN
            INSERT INTO biblioteca_fts(rowid, texto, pdf_nombre, capitulos, codigos_son)
            VALUES (new.id, new.texto, new.pdf_nombre, new.capitulos, new.codigos_son);
        END;
    """)


def _chunk_texto(texto: str, chunk_words=CHUNK_WORDS, overlap=OVERLAP_WORDS):
    """Divide texto en chunks con overlap. Yields (chunk_idx, chunk_text)."""
    words = texto.split()
    if len(words) <= chunk_words:
        yield 0, " ".join(words)
        return
    step = chunk_words - overlap
    idx = 0
    for start in range(0, len(words), step):
        chunk = words[start:start + chunk_words]
        if len(chunk) < 100:  # Skip chunks muy chicos al final
            break
        yield idx, " ".join(chunk)
        idx += 1


def _extraer_metadatos(texto: str):
    """Extrae capitulos y codigos SON mencionados."""
    caps = sorted(set(m.group(1).zfill(2) for m in _CAP_RE.finditer(texto)))
    sones = sorted(set(_SON_RE.findall(texto)))
    return ",".join(caps), ",".join(sones[:10])  # max 10 SON por chunk


def _procesar_pdf(pdf_path: str):
    """Yields (pagina, chunk_idx, texto, capitulos, codigos_son)."""
    import pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        # Estrategia 1: agrupar por paginas, pero si una pagina es muy larga,
        # chunkearla internamente. Si es corta, combinarla con siguientes.
        buffer_texto = []
        buffer_inicio_pagina = 1
        buffer_paginas = []
        for i, page in enumerate(pdf.pages, start=1):
            try:
                t = page.extract_text() or ""
            except Exception:
                t = ""
            t = t.strip()
            if not t:
                continue
            buffer_texto.append(t)
            buffer_paginas.append(i)
            combined = " ".join(buffer_texto)
            words_count = len(combined.split())
            # Si el buffer alcanzo >= CHUNK_WORDS, flush
            if words_count >= CHUNK_WORDS:
                for cidx, chunk in _chunk_texto(combined):
                    caps, sones = _extraer_metadatos(chunk)
                    yield buffer_paginas[0], cidx, chunk, caps, sones
                buffer_texto = []
                buffer_paginas = []
        # Flush final
        if buffer_texto:
            combined = " ".join(buffer_texto)
            for cidx, chunk in _chunk_texto(combined):
                caps, sones = _extraer_metadatos(chunk)
                yield buffer_paginas[0], cidx, chunk, caps, sones


def main():
    if not os.path.exists(DB_PATH):
        print(f"[BIBLIOTECA] ERROR: arancel_rd.db no existe en {DB_PATH}")
        print(f"[BIBLIOTECA] Ejecuta primero: python capa1_sqlite/build_arancel_db.py")
        sys.exit(1)

    t0 = time.time()
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode=WAL")
    _crear_schema(con)

    # Limpiar si ya existe (rebuild idempotente)
    con.execute("DELETE FROM biblioteca")
    con.execute("INSERT INTO biblioteca_fts(biblioteca_fts) VALUES('delete-all')")
    con.commit()

    total_chunks = 0
    total_pdfs_ok = 0
    for pdf_nombre in PDFS_BIBLIOTECA:
        pdf_path = os.path.join(_PDF_DIR, pdf_nombre)
        if not os.path.exists(pdf_path):
            print(f"[BIBLIOTECA]   SKIP (no existe): {pdf_nombre}")
            continue
        print(f"[BIBLIOTECA]   Procesando: {pdf_nombre[:70]}...")
        chunks_pdf = 0
        try:
            for pagina, chunk_idx, texto, caps, sones in _procesar_pdf(pdf_path):
                con.execute(
                    """INSERT INTO biblioteca(pdf_nombre, pagina, chunk_idx, texto, capitulos, codigos_son)
                       VALUES (?,?,?,?,?,?)""",
                    (pdf_nombre, pagina, chunk_idx, texto, caps, sones)
                )
                chunks_pdf += 1
            print(f"[BIBLIOTECA]     -> {chunks_pdf} chunks")
            total_chunks += chunks_pdf
            total_pdfs_ok += 1
        except Exception as e:
            print(f"[BIBLIOTECA]     ERROR: {e}")

    con.commit()

    # Metadata
    con.execute(
        "INSERT OR REPLACE INTO build_meta VALUES('biblioteca_chunks',?)",
        (str(total_chunks),)
    )
    con.execute(
        "INSERT OR REPLACE INTO build_meta VALUES('biblioteca_pdfs',?)",
        (str(total_pdfs_ok),)
    )
    con.commit()
    con.close()

    elapsed = time.time() - t0
    size_kb = os.path.getsize(DB_PATH) / 1024
    print(f"\n{'='*60}")
    print(f"Biblioteca FTS5 indexada en {elapsed:.1f}s")
    print(f"  PDFs procesados : {total_pdfs_ok}/{len(PDFS_BIBLIOTECA)}")
    print(f"  Chunks totales  : {total_chunks}")
    print(f"  DB actual       : {size_kb:.0f} KB")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
