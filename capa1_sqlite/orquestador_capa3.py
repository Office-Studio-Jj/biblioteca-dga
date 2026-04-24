"""
Capa 1 — Orquestador SQLite (Two-Brain System RD)
Fuente de verdad única para DAI/ITBIS/ISC/SON. Sin IA, sin inventar valores.
"""
import os
import sqlite3
import threading
from decimal import Decimal, InvalidOperation

_HERE   = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_HERE, "arancel_rd.db")

# Conexion thread-local (SQLite no es thread-safe con una conexion compartida)
_local = threading.local()


def _con() -> sqlite3.Connection:
    if not hasattr(_local, "con") or _local.con is None:
        if not os.path.exists(DB_PATH):
            raise FileNotFoundError(
                f"arancel_rd.db no encontrado en {DB_PATH}. "
                "Ejecuta: python capa1_sqlite/build_arancel_db.py"
            )
        con = sqlite3.connect(DB_PATH, check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA query_only=ON")
        _local.con = con
    return _local.con


# ── API pública ──────────────────────────────────────────────────────────

def consultar_son_exacto(son: str) -> dict | None:
    """
    Lookup exacto por SON (subpartida nacional).
    Devuelve {son, descripcion, gravamen, itbis, isc} o None si no existe.
    Latencia objetivo: < 5 ms.
    """
    if not son:
        return None
    son = son.strip()
    try:
        row = _con().execute(
            "SELECT son, descripcion, gravamen, itbis, isc, fuente FROM codigos WHERE son=?",
            (son,)
        ).fetchone()
    except Exception as e:
        print(f"[CAPA1] Error lookup {son}: {e}")
        return None
    if row is None:
        return None
    return dict(row)


def buscar_clasificacion_sugerida(termino: str, limit: int = 10) -> list[dict]:
    """
    Búsqueda FTS5 en descripcion. Devuelve lista de {son, descripcion, gravamen, rank}.
    Latencia objetivo: < 20 ms para el índice completo.
    """
    if not termino or not termino.strip():
        return []
    # FTS5 quita caracteres especiales — sanitizar
    term_safe = " ".join(
        w + "*" for w in termino.strip().split()
        if len(w) >= 2 and w.isalnum()
    )
    if not term_safe:
        return []
    try:
        rows = _con().execute(
            """
            SELECT c.son, c.descripcion, c.gravamen, bm25(codigos_fts) AS rank
            FROM codigos_fts
            JOIN codigos c ON c.rowid = codigos_fts.rowid
            WHERE codigos_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (term_safe, limit)
        ).fetchall()
    except Exception as e:
        print(f"[CAPA1] Error FTS '{termino}': {e}")
        return []
    return [dict(r) for r in rows]


def calcular_tributos(son: str, cif: Decimal) -> dict:
    """
    Cálculo tributario exacto usando Decimal. Nunca float.
    DAI  = CIF × gravamen/100
    ITBIS= (CIF + DAI) × 0.18   (si aplica)
    ISC  = según ley (este cálculo es estimativo; ISC mixto no se calcula aquí)
    """
    result = consultar_son_exacto(son)
    if result is None:
        return {"error": f"SON {son} no encontrado en Arancel 7ma Enmienda"}

    try:
        grav_pct = Decimal(result["gravamen"] or "0")
    except InvalidOperation:
        grav_pct = Decimal("0")

    dai = (cif * grav_pct / Decimal("100")).quantize(Decimal("0.01"))
    base_itbis = cif + dai

    itbis_flag = result.get("itbis", "18")
    if itbis_flag == "EXENTO":
        itbis = Decimal("0")
        itbis_nota = "EXENTO"
    else:
        try:
            itbis_pct = Decimal(itbis_flag)
        except InvalidOperation:
            itbis_pct = Decimal("18")
        itbis = (base_itbis * itbis_pct / Decimal("100")).quantize(Decimal("0.01"))
        itbis_nota = f"{itbis_pct}%"

    total = (cif + dai + itbis).quantize(Decimal("0.01"))

    return {
        "son":         son,
        "descripcion": result["descripcion"],
        "cif":         str(cif),
        "gravamen_pct": str(grav_pct),
        "dai":         str(dai),
        "itbis_nota":  itbis_nota,
        "itbis":       str(itbis),
        "isc_nota":    result.get("isc", "NO APLICA"),
        "total_cif_dai_itbis": str(total),
        "fuente":      "arancel_rd.db (pdfplumber 0% IA)",
        "base_legal":  "Ley 168-21, Decreto 36-22, Ley 253-12",
    }


def consultar_rgi(numero: int) -> str:
    """Devuelve el texto de la Regla General de Interpretación 1–6."""
    try:
        row = _con().execute("SELECT texto FROM rgi WHERE numero=?", (numero,)).fetchone()
    except Exception:
        return f"RGI {numero} no disponible."
    return row["texto"] if row else f"RGI {numero} no encontrada."


def consultar_base_legal(id_ley: str) -> dict | None:
    """Devuelve {id, titulo, texto} de la base legal."""
    try:
        row = _con().execute(
            "SELECT id, titulo, texto FROM base_legal WHERE id=?", (id_ley,)
        ).fetchone()
    except Exception:
        return None
    return dict(row) if row else None


def registrar_clasificacion(son: str, pregunta: str, resultado: str, usuario: str = "sistema"):
    """Auditoría: registra cada clasificación realizada."""
    # Conexion separada con write (la thread-local es read-only)
    try:
        con_w = sqlite3.connect(DB_PATH)
        con_w.execute(
            "INSERT INTO clasificaciones(son,pregunta,resultado,usuario) VALUES(?,?,?,?)",
            (son, pregunta[:500], resultado[:2000], usuario)
        )
        con_w.commit()
        con_w.close()
    except Exception as e:
        print(f"[CAPA1] Error registrar_clasificacion: {e}")


def estadisticas() -> dict:
    """Metadatos de la DB para diagnóstico."""
    try:
        con = _con()
        total = con.execute("SELECT COUNT(*) FROM codigos").fetchone()[0]
        caps  = con.execute("SELECT COUNT(DISTINCT substr(son,1,2)) FROM codigos").fetchone()[0]
        meta  = {r[0]: r[1] for r in con.execute("SELECT key, value FROM build_meta").fetchall()}
        return {"total_codigos": total, "capitulos": caps, **meta}
    except Exception as e:
        return {"error": str(e)}
