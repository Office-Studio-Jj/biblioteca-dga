"""Tasas de un SON desde arancel_rd.db (DAI y ITBIS por columna del Arancel, Decreto 36-22).

No leer el DAI del texto de arancel_cache.json: termina en "40 0" (GRAV. y EX. ITBIS) y el
último número es la marca de ITBIS, no el DAI.
"""

import os
import sqlite3

_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arancel_rd.db")


def tasas_son(son):
    """{"dai": "40", "itbis": "EXENTO"|"18", "descripcion": ..., "fuente": ...} o None."""
    if not son:
        return None
    try:
        con = sqlite3.connect(_DB)
        fila = con.execute("SELECT gravamen, itbis, descripcion, fuente FROM codigos WHERE son=?",
                           (son.strip(),)).fetchone()
        con.close()
    except sqlite3.Error:
        return None
    if not fila:
        return None
    return {"dai": fila[0], "itbis": fila[1], "descripcion": fila[2], "fuente": fila[3]}
