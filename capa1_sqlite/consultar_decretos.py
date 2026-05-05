"""
consultar_decretos.py — Consulta tabla_decretos con regla de prelación CEO.
Detecta conflictos normativos y detiene clasificación si irreconciliable.
"""
import json
import os
import sqlite3

_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_HERE, "arancel_rd.db")


def _con():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def consultar_decretos_por_capitulo(capitulo: int) -> list[dict]:
    """Devuelve decretos vigentes que afectan un capítulo SA, ordenados por prelación."""
    con = _con()
    rows = con.execute("""
        SELECT * FROM v_decretos_por_prelacion
        WHERE capitulos_afectados LIKE ?
    """, (f'%{capitulo}%',)).fetchall()
    con.close()
    return [dict(r) for r in rows]


def consultar_decretos_por_partida(partida: str) -> list[dict]:
    """Devuelve decretos vigentes que afectan una partida específica."""
    con = _con()
    rows = con.execute("""
        SELECT * FROM v_decretos_por_prelacion
        WHERE partidas_afectadas LIKE ?
    """, (f'%"{partida}"%',)).fetchall()
    con.close()
    return [dict(r) for r in rows]


def detectar_conflicto(decretos: list[dict]) -> dict | None:
    """
    Regla de prelación CEO (Sección 2.7):
    1. Ley especial prevalece sobre ley general
    2. Norma posterior prevalece sobre anterior
    3. Conflicto irreconciliable → DETENER clasificación

    Retorna None si no hay conflicto, o dict con detalle si lo hay.
    """
    if len(decretos) < 2:
        return None

    vigentes_con_efecto = [d for d in decretos if d.get("estado") == "vigente"]
    if len(vigentes_con_efecto) < 2:
        return None

    # Detectar si hay decretos con efectos opuestos sobre la misma mercancía
    exime = [d for d in vigentes_con_efecto if d.get("exencion_total")]
    grava = [d for d in vigentes_con_efecto if d.get("modifica_dai") and not d.get("exencion_total")]

    if exime and grava:
        # Intentar resolver por prelación
        max_exime = max(exime, key=lambda x: x.get("score_prelacion", 0))
        max_grava = max(grava, key=lambda x: x.get("score_prelacion", 0))

        if max_exime["score_prelacion"] == max_grava["score_prelacion"]:
            return {
                "tipo": "irreconciliable",
                "mensaje": (
                    f"Conflicto normativo detectado entre [{max_exime['instrumento']}] "
                    f"y [{max_grava['instrumento']}]. Requiere criterio jurídico."
                ),
                "decreto_a": max_exime["instrumento"],
                "decreto_b": max_grava["instrumento"],
                "accion": "DETENER_CLASIFICACION",
            }
        # Resuelto por prelación
        ganador = max_exime if max_exime["score_prelacion"] > max_grava["score_prelacion"] else max_grava
        return {
            "tipo": "resuelto_prelacion",
            "mensaje": f"Prevalece {ganador['instrumento']} por prelación (especialidad/temporalidad).",
            "decreto_prevalente": ganador["instrumento"],
            "accion": "CONTINUAR",
        }

    return None


def paso_8_5_cruce_decretos(capitulo: int, partida: str = None) -> dict:
    """
    Paso 8.5 del flujo CEO: cruce contra tabla_decretos.
    Retorna resultado con advertencias o conflictos detectados.
    """
    con = _con()
    count = con.execute("SELECT COUNT(*) FROM tabla_decretos").fetchone()[0]
    con.close()

    if count == 0:
        return {
            "estado": "advertencia",
            "mensaje": (
                "AVISO: La tabla de decretos no está cargada. "
                "La clasificación técnica puede estar modificada por "
                "decretos vigentes no consultados."
            ),
            "decretos_aplicables": [],
            "conflicto": None,
        }

    decretos = consultar_decretos_por_capitulo(capitulo)
    if partida:
        decretos_partida = consultar_decretos_por_partida(partida)
        # Merge sin duplicados
        ids_vistos = {d["id"] for d in decretos}
        for dp in decretos_partida:
            if dp["id"] not in ids_vistos:
                decretos.append(dp)

    conflicto = detectar_conflicto(decretos)

    if conflicto and conflicto["accion"] == "DETENER_CLASIFICACION":
        return {
            "estado": "conflicto_irreconciliable",
            "mensaje": conflicto["mensaje"],
            "decretos_aplicables": decretos,
            "conflicto": conflicto,
            "bloquea": True,
        }

    return {
        "estado": "ok" if decretos else "sin_decretos",
        "mensaje": f"{len(decretos)} decreto(s) vigente(s) encontrado(s)." if decretos else "Sin decretos aplicables.",
        "decretos_aplicables": decretos,
        "conflicto": conflicto,
        "bloquea": False,
    }
