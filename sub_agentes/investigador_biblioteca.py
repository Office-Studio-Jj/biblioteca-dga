"""
Sub-agente [3.5] — INVESTIGADOR BIBLIOTECA-NOMENCLATURA
Busca doctrina, jurisprudencia y ejemplos en los 11 PDFs indexados en FTS5.

API:
    investigar(keywords: list[str], capitulo: str = None, limit=5) -> list[dict]

Latencia objetivo: <50 ms por consulta.
"""
import os
import re
import sqlite3
from typing import Optional

_HERE    = os.path.dirname(os.path.abspath(__file__))
_ROOT    = os.path.dirname(_HERE)
_DB_PATH = os.path.join(_ROOT, "capa1_sqlite", "arancel_rd.db")


def _con() -> sqlite3.Connection:
    con = sqlite3.connect(_DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def _limpiar_keyword(k: str) -> str:
    """Solo alnum >= 3 chars (evita inyeccion FTS5)."""
    k = re.sub(r'[^\w]', ' ', k).strip()
    return k if len(k) >= 3 and k.isalnum() else ""


def investigar(
    keywords: list[str],
    capitulo: Optional[str] = None,
    limit: int = 5
) -> list[dict]:
    """
    Busca snippets relevantes en los 11 PDFs de biblioteca-nomenclatura.

    Args:
        keywords: palabras clave extraidas de la ficha merceologica
        capitulo: si se indica (ej "85"), da boost 2x a snippets que lo mencionen
        limit: cantidad de snippets a retornar

    Returns:
        [
            {
                "pdf_nombre": "Guía Estrategias...",
                "pagina":     47,
                "capitulos":  "85,87",
                "codigos_son": "8543.70.90",
                "texto":      "<snippet de hasta 1500 chars>",
                "rank":       -8.42,
                "boost_capitulo": True
            },
            ...
        ]
    """
    terms = [_limpiar_keyword(k) for k in keywords]
    terms = [t for t in terms if t]
    if not terms:
        return []

    # Query FTS5 con OR entre keywords, prefijo *
    fts_query = " OR ".join(f"{t}*" for t in terms)

    try:
        con = _con()
        if capitulo:
            # Dos queries: una con boost (menciona capitulo), otra general
            rows_boost = con.execute("""
                SELECT b.id, b.pdf_nombre, b.pagina, b.capitulos, b.codigos_son,
                       b.texto, bm25(biblioteca_fts) AS rank
                FROM biblioteca_fts
                JOIN biblioteca b ON b.id = biblioteca_fts.rowid
                WHERE biblioteca_fts MATCH ?
                  AND (',' || b.capitulos || ',') LIKE ?
                ORDER BY rank
                LIMIT ?
            """, (fts_query, f"%,{capitulo},%", limit)).fetchall()

            ids_boost = {r["id"] for r in rows_boost}
            rows_resto = con.execute("""
                SELECT b.id, b.pdf_nombre, b.pagina, b.capitulos, b.codigos_son,
                       b.texto, bm25(biblioteca_fts) AS rank
                FROM biblioteca_fts
                JOIN biblioteca b ON b.id = biblioteca_fts.rowid
                WHERE biblioteca_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (fts_query, limit * 2)).fetchall()
            rows_resto = [r for r in rows_resto if r["id"] not in ids_boost][:limit]

            resultados = []
            for r in rows_boost:
                resultados.append({**dict(r), "boost_capitulo": True})
            for r in rows_resto:
                resultados.append({**dict(r), "boost_capitulo": False})
            resultados = resultados[:limit]
        else:
            rows = con.execute("""
                SELECT b.id, b.pdf_nombre, b.pagina, b.capitulos, b.codigos_son,
                       b.texto, bm25(biblioteca_fts) AS rank
                FROM biblioteca_fts
                JOIN biblioteca b ON b.id = biblioteca_fts.rowid
                WHERE biblioteca_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (fts_query, limit)).fetchall()
            resultados = [{**dict(r), "boost_capitulo": False} for r in rows]

        con.close()

        # Truncar texto a 1500 chars para no saturar contexto Gemini
        for r in resultados:
            if len(r["texto"]) > 1500:
                r["texto"] = r["texto"][:1500] + "..."
            # Limpiar campos innecesarios
            r.pop("id", None)
        return resultados

    except Exception as e:
        print(f"[INVESTIGADOR] Error: {e}")
        return []


def formatear_contexto_gemini(snippets: list[dict]) -> str:
    """
    Formatea snippets para inyectar en el prompt de Gemini.
    """
    if not snippets:
        return "(Sin resultados en biblioteca-nomenclatura)"
    partes = []
    for i, s in enumerate(snippets, 1):
        boost = " ★" if s.get("boost_capitulo") else ""
        partes.append(
            f"[{i}] {s['pdf_nombre']} (p.{s['pagina']}){boost}\n"
            f"    Capitulos mencionados: {s.get('capitulos') or '-'}\n"
            f"    SON mencionados: {s.get('codigos_son') or '-'}\n"
            f"    \"{s['texto']}\""
        )
    return "\n\n".join(partes)


if __name__ == "__main__":
    # Test
    r = investigar(["videoconferencia", "camara", "aparato"], capitulo="85", limit=3)
    print(f"Resultados: {len(r)}")
    print(formatear_contexto_gemini(r)[:800])
