#!/usr/bin/env python3
"""
Verificador de integridad del Arancel Nacional en SQLite (Capa 1).
Confirma que arancel_rd.db contiene los ~7,616 SON de la 7ma Enmienda,
con cobertura completa de los 97 capitulos del SA.

Base legal: Decreto 36-22 (Arancel Nacional vigente), Ley 168-21 Art. 75-78.

Uso:
    python capa1_sqlite/verificar_carga_arancel.py
    python capa1_sqlite/verificar_carga_arancel.py --detalle
    python capa1_sqlite/verificar_carga_arancel.py --rebuild (re-ejecuta build_arancel_db)
"""
import json
import os
import sqlite3
import sys
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_HERE, "arancel_rd.db")

_CAPITULOS_SA_ESPERADOS = 97
_SON_MINIMO_ESPERADO = 7000
_SECCIONES_SA = 21

_CAPITULOS_POR_SECCION = {
    "I": range(1, 6), "II": range(6, 15), "III": range(15, 16),
    "IV": range(16, 25), "V": range(25, 28), "VI": range(28, 39),
    "VII": range(39, 41), "VIII": range(41, 44), "IX": range(44, 47),
    "X": range(47, 50), "XI": range(50, 64), "XII": range(64, 68),
    "XIII": range(68, 71), "XIV": range(71, 72), "XV": range(72, 84),
    "XVI": range(84, 86), "XVII": range(86, 90), "XVIII": range(90, 93),
    "XIX": range(93, 94), "XX": range(94, 97), "XXI": range(97, 98),
}


def verificar_carga(detalle: bool = False) -> dict:
    """Verifica integridad completa de arancel_rd.db."""
    resultado = {
        "fecha": datetime.now().isoformat(),
        "db_existe": False,
        "total_codigos": 0,
        "capitulos_cubiertos": 0,
        "capitulos_faltantes": [],
        "tablas_presentes": [],
        "tablas_faltantes": [],
        "rgi_completas": False,
        "fts5_operativo": False,
        "integridad": "FALLO",
        "errores": [],
        "detalle_capitulos": {},
    }

    if not os.path.exists(DB_PATH):
        resultado["errores"].append(f"DB no encontrada: {DB_PATH}")
        return resultado

    resultado["db_existe"] = True
    con = sqlite3.connect(DB_PATH)

    tablas_requeridas = [
        "codigos", "codigos_fts", "clasificaciones", "rgi",
        "base_legal", "build_meta", "sinonimos_arancelarios",
        "partes_de_productos", "conflictos_registrados"
    ]
    tablas_existentes = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    resultado["tablas_presentes"] = sorted(tablas_existentes)
    resultado["tablas_faltantes"] = [t for t in tablas_requeridas if t not in tablas_existentes]

    total = con.execute("SELECT COUNT(*) FROM codigos").fetchone()[0]
    resultado["total_codigos"] = total

    caps = con.execute(
        "SELECT DISTINCT substr(son,1,2) as cap FROM codigos ORDER BY cap"
    ).fetchall()
    caps_presentes = {int(r[0]) for r in caps}
    caps_esperados = set(range(1, _CAPITULOS_SA_ESPERADOS + 1))
    resultado["capitulos_cubiertos"] = len(caps_presentes)
    resultado["capitulos_faltantes"] = sorted(caps_esperados - caps_presentes)

    if detalle:
        for cap_num in sorted(caps_presentes):
            cap_str = f"{cap_num:02d}"
            cnt = con.execute(
                "SELECT COUNT(*) FROM codigos WHERE substr(son,1,2)=?", (cap_str,)
            ).fetchone()[0]
            resultado["detalle_capitulos"][cap_str] = cnt

    rgi_count = con.execute("SELECT COUNT(*) FROM rgi").fetchone()[0]
    resultado["rgi_completas"] = rgi_count == 6

    try:
        fts_test = con.execute(
            "SELECT COUNT(*) FROM codigos_fts WHERE codigos_fts MATCH 'motor*'"
        ).fetchone()[0]
        resultado["fts5_operativo"] = fts_test >= 0
    except Exception as e:
        resultado["errores"].append(f"FTS5 fallo: {e}")

    if total < _SON_MINIMO_ESPERADO:
        resultado["errores"].append(
            f"Solo {total} SON cargadas (minimo esperado: {_SON_MINIMO_ESPERADO})"
        )
    if resultado["tablas_faltantes"]:
        resultado["errores"].append(f"Tablas faltantes: {resultado['tablas_faltantes']}")
    if resultado["capitulos_faltantes"]:
        resultado["errores"].append(
            f"Capitulos sin cobertura: {resultado['capitulos_faltantes']}"
        )
    if not resultado["rgi_completas"]:
        resultado["errores"].append(f"Solo {rgi_count}/6 RGI cargadas")

    if not resultado["errores"]:
        resultado["integridad"] = "OK"
    elif total >= _SON_MINIMO_ESPERADO and not resultado["tablas_faltantes"]:
        resultado["integridad"] = "PARCIAL"

    con.close()
    return resultado


def ejecutar_rebuild():
    """Re-ejecuta build_arancel_db.py para reconstruir la DB."""
    build_script = os.path.join(_HERE, "build_arancel_db.py")
    if not os.path.exists(build_script):
        print(f"ERROR: {build_script} no encontrado")
        return False
    print("[VERIFICADOR] Ejecutando rebuild de arancel_rd.db...")
    import subprocess
    r = subprocess.run([sys.executable, build_script], capture_output=True, text=True)
    print(r.stdout)
    if r.returncode != 0:
        print(f"ERROR: {r.stderr}")
        return False
    return True


if __name__ == "__main__":
    detalle = "--detalle" in sys.argv
    rebuild = "--rebuild" in sys.argv

    if rebuild:
        ejecutar_rebuild()

    res = verificar_carga(detalle=detalle)

    print(f"\n{'='*60}")
    print(f"  VERIFICACION ARANCEL RD — {res['fecha']}")
    print(f"{'='*60}")
    print(f"  DB existe:          {res['db_existe']}")
    print(f"  Total SON:          {res['total_codigos']}")
    print(f"  Capitulos:          {res['capitulos_cubiertos']}/{_CAPITULOS_SA_ESPERADOS}")
    print(f"  RGI completas:      {res['rgi_completas']}")
    print(f"  FTS5 operativo:     {res['fts5_operativo']}")
    print(f"  Tablas faltantes:   {res['tablas_faltantes'] or 'ninguna'}")
    print(f"  INTEGRIDAD:         {res['integridad']}")

    if res["errores"]:
        print(f"\n  ERRORES:")
        for e in res["errores"]:
            print(f"    - {e}")

    if detalle and res["detalle_capitulos"]:
        print(f"\n  DETALLE POR CAPITULO:")
        for cap, cnt in sorted(res["detalle_capitulos"].items()):
            print(f"    Cap {cap}: {cnt} SON")

    print(f"{'='*60}\n")
    sys.exit(0 if res["integridad"] == "OK" else 1)
