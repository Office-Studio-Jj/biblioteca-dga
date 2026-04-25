#!/usr/bin/env python3
"""
LightRAG Engine para Biblioteca DGA
Grafo de conocimiento con recuperacion dual (entidades + relaciones)
sobre documentos PDF arancelarios usando Gemini como LLM backend.
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

try:
    from lightrag import LightRAG, QueryParam
except ImportError:
    print("[LIGHTRAG] ERROR: lightrag-hku no instalado. Ejecuta: pip install lightrag-hku")
    sys.exit(1)

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

from config import DATA_DIR, SKILL_DIR

logger = logging.getLogger(__name__)

# Directorio donde LightRAG almacena su grafo y vectores
LIGHTRAG_DIR = DATA_DIR / "lightrag_store"
LIGHTRAG_DIR.mkdir(parents=True, exist_ok=True)

# PDFs disponibles para indexar
PDF_SOURCES = [
    DATA_DIR / "arancel_7ma_enmienda.pdf",
]

# Agregar fuentes de nomenclatura si existen
FUENTES_DIR = DATA_DIR / "fuentes_nomenclatura"
if FUENTES_DIR.exists():
    PDF_SOURCES.extend(sorted(FUENTES_DIR.glob("*.pdf")))


def _extraer_texto_pdf(pdf_path: Path) -> str:
    """Extrae texto de un PDF usando pdfplumber (0% IA)."""
    if pdfplumber is None:
        logger.warning("pdfplumber no disponible, saltando %s", pdf_path.name)
        return ""
    texto_paginas = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for pagina in pdf.pages:
                texto = pagina.extract_text()
                if texto:
                    texto_paginas.append(texto)
    except Exception as e:
        logger.error("Error extrayendo %s: %s", pdf_path.name, e)
        return ""
    return "\n\n".join(texto_paginas)


def _get_gemini_model():
    """Determina el modelo Gemini disponible."""
    return os.environ.get("LIGHTRAG_MODEL", "gemini-2.5-flash")


def _get_embedding_model():
    """Modelo de embeddings para LightRAG."""
    return os.environ.get("LIGHTRAG_EMBEDDING", "text-embedding-004")


def crear_instancia_rag() -> LightRAG:
    """Crea y retorna una instancia configurada de LightRAG con Gemini."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Se requiere GEMINI_API_KEY o GOOGLE_API_KEY para LightRAG")

    rag = LightRAG(
        working_dir=str(LIGHTRAG_DIR),
        llm_model_name=_get_gemini_model(),
        llm_model_max_async=4,
        llm_model_max_token_size=32768,
        embedding_model_name=_get_embedding_model(),
    )
    return rag


async def indexar_documentos(rag: LightRAG = None, forzar: bool = False) -> dict:
    """
    Indexa todos los PDFs disponibles en el grafo de conocimiento LightRAG.

    Args:
        rag: Instancia LightRAG (se crea una si no se pasa).
        forzar: Si True, re-indexa aunque ya exista el grafo.

    Returns:
        dict con estadisticas de indexacion.
    """
    if rag is None:
        rag = crear_instancia_rag()

    # Verificar si ya hay datos indexados
    marcador = LIGHTRAG_DIR / ".indexed"
    if marcador.exists() and not forzar:
        logger.info("Grafo ya indexado. Usa forzar=True para re-indexar.")
        return {"status": "ya_indexado", "documentos": 0}

    stats = {"documentos": 0, "paginas_texto": 0, "errores": []}

    for pdf_path in PDF_SOURCES:
        if not pdf_path.exists():
            stats["errores"].append(f"No encontrado: {pdf_path.name}")
            continue

        logger.info("Indexando: %s", pdf_path.name)
        texto = _extraer_texto_pdf(pdf_path)
        if not texto:
            stats["errores"].append(f"Sin texto extraible: {pdf_path.name}")
            continue

        try:
            await rag.ainsert(texto)
            stats["documentos"] += 1
            stats["paginas_texto"] += texto.count("\n\n") + 1
            logger.info("Indexado OK: %s", pdf_path.name)
        except Exception as e:
            stats["errores"].append(f"Error indexando {pdf_path.name}: {e}")
            logger.error("Error indexando %s: %s", pdf_path.name, e)

    # Marcar como indexado
    if stats["documentos"] > 0:
        marcador.write_text(f"indexado: {stats['documentos']} documentos")

    stats["status"] = "completado"
    return stats


async def consultar(pregunta: str, modo: str = "hybrid", rag: LightRAG = None) -> str:
    """
    Consulta el grafo de conocimiento LightRAG.

    Args:
        pregunta: La consulta del usuario.
        modo: Modo de busqueda - "naive", "local", "global", "hybrid", "mix".
        rag: Instancia LightRAG (se crea una si no se pasa).

    Returns:
        Respuesta generada por LightRAG.
    """
    if rag is None:
        rag = crear_instancia_rag()

    resultado = await rag.aquery(
        pregunta,
        param=QueryParam(mode=modo)
    )
    return resultado


def consultar_sync(pregunta: str, modo: str = "hybrid") -> str:
    """Version sincrona de consultar() para uso desde Flask."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(consultar(pregunta, modo))
    finally:
        loop.close()


def indexar_sync(forzar: bool = False) -> dict:
    """Version sincrona de indexar_documentos() para uso desde Flask."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(indexar_documentos(forzar=forzar))
    finally:
        loop.close()


# CLI para pruebas directas
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="LightRAG Engine - Biblioteca DGA")
    sub = parser.add_subparsers(dest="comando")

    sub.add_parser("indexar", help="Indexar PDFs en el grafo de conocimiento")
    sub.add_parser("reindexar", help="Re-indexar forzando rebuild del grafo")

    q_parser = sub.add_parser("consultar", help="Consultar el grafo")
    q_parser.add_argument("pregunta", help="Pregunta a consultar")
    q_parser.add_argument("--modo", default="hybrid",
                          choices=["naive", "local", "global", "hybrid", "mix"])

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    if args.comando == "indexar":
        resultado = indexar_sync(forzar=False)
        print(f"Resultado: {resultado}")
    elif args.comando == "reindexar":
        resultado = indexar_sync(forzar=True)
        print(f"Resultado: {resultado}")
    elif args.comando == "consultar":
        respuesta = consultar_sync(args.pregunta, args.modo)
        print(f"\nRespuesta:\n{respuesta}")
    else:
        parser.print_help()
