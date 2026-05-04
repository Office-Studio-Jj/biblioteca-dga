"""
Validador de códigos SON (Subpartida Nacional) — República Dominicana.

Valida formato regex, existencia en Capa 1 SQLite (arancel_rd.db),
y propone alternativas del mismo capítulo si el código no existe.

Base legal: Ley 14-93 Art. 1, Decreto 36-22, Ley 168-21 Art. 75.
Formato SON DGA: ####.##.## (8 dígitos) o ####.##.##.## (con apertura nacional).
"""
import os
import re
import sqlite3
import threading

_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_HERE, "arancel_rd.db")

_local = threading.local()
_SON_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}(\.\d{2})?$")

_SECCIONES = {
    range(1, 6): "I", range(6, 15): "II", range(15, 16): "III",
    range(16, 25): "IV", range(25, 28): "V", range(28, 39): "VI",
    range(39, 41): "VII", range(41, 44): "VIII", range(44, 47): "IX",
    range(47, 50): "X", range(50, 64): "XI", range(64, 68): "XII",
    range(68, 71): "XIII", range(71, 72): "XIV", range(72, 84): "XV",
    range(84, 86): "XVI", range(86, 90): "XVII", range(90, 93): "XVIII",
    range(93, 94): "XIX", range(94, 97): "XX", range(97, 98): "XXI",
}


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


def _capitulo_a_seccion(capitulo: int) -> str:
    """Mapea número de capítulo SA (1-97) a sección romana (I-XXI)."""
    for rango, seccion in _SECCIONES.items():
        if capitulo in rango:
            return seccion
    return "DESCONOCIDA"


def existe_en_arancel(codigo: str) -> bool:
    """
    Verificación rápida de existencia de un código SON en arancel_rd.db.

    Base legal: Decreto 36-22 (Arancel Nacional vigente, 7ma Enmienda SA).
    """
    if not codigo or not _SON_RE.match(codigo.strip()):
        return False
    row = _con().execute(
        "SELECT 1 FROM codigos WHERE son=?", (codigo.strip(),)
    ).fetchone()
    return row is not None


def buscar_alternativas_capitulo(capitulo: str, limit: int = 10) -> list[dict]:
    """
    Busca códigos SON dentro del mismo capítulo (primeros 2 dígitos).
    Útil para sugerir alternativas cuando un código no existe.

    Args:
        capitulo: Capítulo SA en formato '01'-'97'.
        limit: Máximo de resultados (default 10).

    Returns:
        Lista de dicts con son, descripcion, gravamen, itbis, isc.

    Base legal: Ley 168-21 Art. 75, Decreto 755-22 (RGI 1-6).
    """
    if not capitulo or not capitulo.strip().isdigit():
        return []
    cap = capitulo.strip().zfill(2)
    rows = _con().execute(
        "SELECT son, descripcion, gravamen, itbis, isc FROM codigos "
        "WHERE son LIKE ? ORDER BY son LIMIT ?",
        (f"{cap}%", limit)
    ).fetchall()
    return [dict(r) for r in rows]


def validar_son(codigo: str) -> dict:
    """
    Validador principal de códigos SON (Subpartida Nacional DGA).

    1. Valida formato regex (####.##.## o ####.##.##.##).
    2. Consulta existencia en SQLite Capa 1.
    3. Si existe: retorna código + descripción + capítulo + sección + tributos.
    4. Si no existe: retorna alternativas del mismo capítulo.

    Args:
        codigo: Código SON a validar.

    Returns:
        dict con {valido, codigo_son, descripcion, capitulo, seccion,
        gravamen, itbis, isc} si válido, o {valido: False, error,
        alternativas} si inválido.

    Base legal: Ley 14-93 Art. 1, Decreto 36-22, Ley 168-21 Art. 75.
    """
    if not codigo or not codigo.strip():
        return {"valido": False, "error": "Código vacío", "alternativas": []}

    codigo = codigo.strip()

    if not _SON_RE.match(codigo):
        return {
            "valido": False,
            "error": (
                f"Formato inválido: '{codigo}'. "
                "Formato DGA: ####.##.## o ####.##.##.##"
            ),
            "alternativas": [],
        }

    row = _con().execute(
        "SELECT son, descripcion, gravamen, itbis, isc FROM codigos WHERE son=?",
        (codigo,)
    ).fetchone()

    if row is None:
        cap = codigo[:2]
        return {
            "valido": False,
            "error": f"Código {codigo} no existe en Arancel 7ma Enmienda (Decreto 36-22)",
            "alternativas": buscar_alternativas_capitulo(cap),
        }

    cap_num = int(codigo[:2])
    return {
        "valido": True,
        "codigo_son": row["son"],
        "descripcion": row["descripcion"],
        "capitulo": codigo[:2],
        "seccion": _capitulo_a_seccion(cap_num),
        "gravamen": row["gravamen"],
        "itbis": row["itbis"],
        "isc": row["isc"],
    }
