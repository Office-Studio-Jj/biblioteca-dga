"""
auditoria_decretos.py — Verifica si la auditoría trimestral está vencida.
CEO 05-05-2026: Sin auditoría, el Paso 8.5 es una promesa vacía.
"""
import os
import sqlite3
from datetime import datetime, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_HERE, "arancel_rd.db")


def verificar_auditoria_vencida() -> dict:
    """
    Verifica si algún decreto tiene más de 90 días sin auditoría.
    Retorna alerta si hay decretos vencidos.
    """
    if not os.path.exists(DB_PATH):
        return {"alerta": False, "mensaje": "BD no disponible"}

    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row

    try:
        count = con.execute("SELECT COUNT(*) FROM tabla_decretos").fetchone()[0]
    except Exception:
        con.close()
        return {"alerta": False, "mensaje": "tabla_decretos no existe aún"}

    if count == 0:
        con.close()
        return {
            "alerta": True,
            "mensaje": "ALERTA: tabla_decretos está vacía. Paso 8.5 no puede operar.",
            "decretos_vencidos": 0,
        }

    limite = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    vencidos = con.execute("""
        SELECT COUNT(*) FROM tabla_decretos
        WHERE estado='vigente' AND (fecha_ultima_auditoria IS NULL OR fecha_ultima_auditoria < ?)
    """, (limite,)).fetchone()[0]
    con.close()

    if vencidos > 0:
        return {
            "alerta": True,
            "mensaje": (
                f"ALERTA: Auditoría de decretos vencida. {vencidos} decreto(s) con más de 90 días "
                "sin verificar. El Paso 8.5 puede operar con información desactualizada."
            ),
            "decretos_vencidos": vencidos,
        }

    return {
        "alerta": False,
        "mensaje": "Auditoría trimestral al día.",
        "decretos_vencidos": 0,
    }


if __name__ == "__main__":
    result = verificar_auditoria_vencida()
    print(result["mensaje"])
