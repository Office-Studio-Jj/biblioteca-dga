#!/usr/bin/env python3
"""
ORDEN 3 — Poblar columnas dai_pct / itbis_pct / isc_pct en tabla codigos.
Migra los datos ya existentes en columnas gravamen/itbis/isc (TEXT) a las
nuevas columnas tipadas REAL.
Fuente primaria: datos extraidos por pdfplumber del Arancel 7ma Enmienda.
Base legal: Decreto 36-22, Ley 11-92 Titulo IV, Ley 146-00.
Uso: python poblar_gravamenes.py [--dry-run] [--capitulos 84,85,87,90]
"""
import os
import re
import sqlite3
import sys
from decimal import Decimal, InvalidOperation
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_HERE, "capa1_sqlite", "arancel_rd.db")

# ISC conocido por capitulo (Ley 11-92 Arts. 361-382, Ley 253-12)
_ISC_POR_CAPITULO = {
    "22": 10.0,  # Bebidas alcoholicas (tasa estimada, varia por producto)
    "24": 20.0,  # Tabaco y cigarrillos
    "27": 5.0,   # Combustibles (tasa aproximada — ver Ley 112-00)
}

# Permisos conocidos por capitulo (catalogo basico)
_PERMISOS_CAPITULO = {
    "01": "Ministerio de Agricultura (Ley 4030-55)",
    "02": "DIGEGA + MSP (Ley 42-01)",
    "03": "CODOPESCA (Ley 307-04)",
    "06": "Sanidad Vegetal AGRICULTURA (Ley 4030-55)",
    "27": "MIC - Hidrocarburos (Ley 112-00)",
    "30": "MSP/DIGEMAPS (Ley 42-01)",
    "36": "Ministerio Defensa (Ley 631)",
    "84": "DGNM si aplica (Ley 166-12)",
    "85": "INDOTEL (Ley 153-98), DGNM (Ley 166-12)",
    "87": "DGTT (Ley 63-17), DGNM",
    "88": "IDAC (Ley 491-06)",
    "89": "ANAMAR (Ley 5-23)",
    "90": "MSP/DIGEMAPS (Ley 42-01)",
    "93": "Ministerio Defensa (Ley 631)",
}


def _parse_decimal(valor: str, default: float = 0.0) -> float:
    if not valor:
        return default
    try:
        return float(Decimal(valor.strip()))
    except (InvalidOperation, AttributeError):
        return default


def _parse_isc(valor: str, son: str) -> float:
    if not valor or valor.strip().upper() in ("NO APLICA", "EXENTO", "", "0"):
        cap = son[:2]
        return _ISC_POR_CAPITULO.get(cap, 0.0)
    try:
        return float(Decimal(str(valor).replace("%", "").strip()))
    except (InvalidOperation, AttributeError):
        return 0.0


def poblar(dry_run: bool = False, capitulos_filtro: list = None) -> dict:
    """Migra gravamen/itbis/isc (TEXT) a dai_pct/itbis_pct/isc_pct (REAL)."""
    con = sqlite3.connect(DB_PATH)

    if capitulos_filtro:
        caps_sql = ",".join(f"'{c.zfill(2)}'" for c in capitulos_filtro)
        where = f"WHERE substr(son,1,2) IN ({caps_sql})"
        total_scope = con.execute(
            f"SELECT COUNT(*) FROM codigos {where}"
        ).fetchone()[0]
    else:
        where = ""
        total_scope = con.execute("SELECT COUNT(*) FROM codigos").fetchone()[0]

    rows = con.execute(
        f"SELECT son, gravamen, itbis, isc FROM codigos {where}"
    ).fetchall()

    actualizadas = 0
    errores = []
    log_caps = {}

    for son, gravamen_raw, itbis_raw, isc_raw in rows:
        cap = son[:2] if son else "00"
        try:
            dai = _parse_decimal(gravamen_raw, 0.0)
            # ITBIS: si la columna dice EXENTO, poner 0; si dice 18 o valor, usar ese
            if str(itbis_raw).upper() == "EXENTO":
                itbis = 0.0
            else:
                itbis = _parse_decimal(itbis_raw, 18.0)
            isc = _parse_isc(isc_raw, son)
            permisos = _PERMISOS_CAPITULO.get(cap, "")

            if not dry_run:
                con.execute(
                    """UPDATE codigos
                       SET dai_pct=?, itbis_pct=?, isc_pct=?, permisos=?
                       WHERE son=?""",
                    (dai, itbis, isc, permisos, son)
                )
            actualizadas += 1
            log_caps[cap] = log_caps.get(cap, 0) + 1
        except Exception as e:
            errores.append(f"{son}: {e}")

    if not dry_run:
        con.commit()

    con.close()

    resultado = {
        "fecha": datetime.now().isoformat(),
        "dry_run": dry_run,
        "scope": total_scope,
        "actualizadas": actualizadas,
        "errores": len(errores),
        "detalle_errores": errores[:10],
        "caps_actualizados": len(log_caps),
    }
    return resultado


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    caps_arg = next((a for a in sys.argv if a.startswith("--capitulos=")), None)
    capitulos = caps_arg.replace("--capitulos=", "").split(",") if caps_arg else None

    print(f"\n{'='*60}")
    print(f"  POBLAR GRAVAMENES — {'DRY RUN' if dry_run else 'EJECUCION REAL'}")
    if capitulos:
        print(f"  Capitulos filtro: {capitulos}")
    print(f"{'='*60}")

    res = poblar(dry_run=dry_run, capitulos_filtro=capitulos)

    print(f"  Scope:         {res['scope']:,} SON")
    print(f"  Actualizadas:  {res['actualizadas']:,}")
    print(f"  Errores:       {res['errores']}")
    print(f"  Caps poblados: {res['caps_actualizados']}")

    if res["detalle_errores"]:
        print("\n  Errores detalle:")
        for e in res["detalle_errores"]:
            print(f"    - {e}")

    print(f"\n  Base legal aplicada:")
    print(f"    DAI: Decreto 36-22 (Arancel 7ma Enmienda)")
    print(f"    ITBIS: Ley 11-92 Art. 335 (18% general)")
    print(f"    ISC: Ley 11-92 Arts. 361-382, Ley 112-00")
    print(f"{'='*60}\n")
    sys.exit(0 if res["errores"] == 0 else 1)
