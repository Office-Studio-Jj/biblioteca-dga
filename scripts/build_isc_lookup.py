"""Genera notebooklm_skill/data/fuentes_nomenclatura/isc_lookup.json desde la ley (0% IA).

Fuente: Art. 375 del Codigo Tributario (Ley 11-92, modificado por Ley 253-12), transcrito de la
tabla oficial; alcohol y tabaco segun sus Parrafos I-VIII; combustibles segun Ley 112-00 y
Art. 23 Ley 557-05 (mod. Art. 30 Ley 495-06) y Art. 31 Ley 495-06.
Los codigos de la ley vienen de una nomenclatura anterior: se expanden contra los SON vigentes de
capa1_sqlite/arancel_rd.db (7ma Enmienda, Decreto 36-22). Si no hay correspondencia clara, el codigo
queda en "pendientes_correlacion" y la tasa se marca VERIFICAR.

Uso: python scripts/build_isc_lookup.py
"""

import json
import os
import sqlite3
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_RAIZ, "capa1_sqlite", "arancel_rd.db")
_SALIDA = os.path.join(_RAIZ, "notebooklm_skill", "data", "fuentes_nomenclatura", "isc_lookup.json")

ART375 = "Ley 11-92 Art. 375 (mod. Ley 253-12)"

# (prefijo SON vigente, tasa ad valorem %, descripcion en la ley). Prefijo de 4 digitos = partida completa.
BIENES_AD_VALOREM = [
    ("1604.31.00", 20, "Caviar"), ("1604.32.00", 20, "Sucedaneos del caviar"),
    ("2403.11.00", 130, "Tabaco para pipa de agua"), ("2403.19.00", 130, "Los demas (tabaco para fumar)"),
    ("2403.99.90", 130, "Los demas (tabaco)"),
    ("3303", 20, "Perfumes y aguas de tocador"),
    ("3922.10.11", 20, "Banera tipo jacuzzi, de plastico reforzado con fibra de vidrio"),
    ("7324.21.10", 20, "Banera tipo jacuzzi, de fundicion"),
    ("7418.20.11", 20, "Banera tipo jacuzzi, de cobre (ley: 7418.20.00)"),
    ("7615.20.11", 20, "Banera tipo jacuzzi, de aluminio (ley: 7615.20.00)"),
    ("9019.10.12", 20, "Banera tipo jacuzzi con bombas e hidromasaje"),
    ("5701", 20, "Alfombras de nudo"), ("5702", 20, "Alfombras tejidas"), ("5703", 20, "Alfombras con mechon insertado"),
    ("5805", 20, "Tapiceria tejida a mano"),
    ("7113", 20, "Articulos de joyeria"), ("7114", 20, "Articulos de orfebreria"),
    ("7116", 20, "Manufacturas de perlas o piedras preciosas"), ("7117", 20, "Bisuteria"),
    ("8415", 20, "Maquinas y aparatos de aire acondicionado y sus partes"),
    ("8479.60.00", 20, "Aparatos de evaporacion para refrigerar el aire"),
    ("8508.11.00", 20, "Aspiradoras"), ("8508.19.00", 20, "Aspiradoras, las demas"), ("8508.60.00", 20, "Las demas aspiradoras"),
    ("8509.40.90", 20, "Trituradoras y mezcladoras de alimentos, los demas"),
    ("8509.80.10", 20, "Enceradoras de pisos"), ("8509.80.20", 20, "Trituradores de desperdicios de cocina"),
    ("8509.80.90", 20, "Los demas aparatos electromecanicos domesticos"),
    ("8516.10.00", 20, "Calentadores electricos de agua"), ("8516.50.00", 20, "Hornos de microondas"),
    ("8516.60.10", 20, "Hornos"), ("8516.60.30", 20, "Calentadores, parrillas y asadores"),
    ("8516.71.00", 20, "Aparatos para preparar cafe o te"), ("8516.72.00", 20, "Tostadoras de pan"),
    ("8516.79", 20, "Los demas aparatos electrotermicos (ley: 8516.79.00)"),
    ("8517.69.20", 20, "Videofonos"), ("8519.20.00", 20, "Tocadiscos de ficha o moneda"), ("8519.30.00", 20, "Giradiscos"),
    ("8521", 20, "Aparatos de grabacion o reproduccion de video"),
    ("8527.13.10", 20, "Aparatos combinados con reproductor optico"),
    ("8527.21.10", 20, "Receptores combinados con reproductor optico"),
    ("8527.91.10", 20, "Los demas receptores combinados con reproductor optico"),
    ("8528.72.00", 10, "Receptores de television en colores"), ("8528.59.10", 10, "Videomonitores en colores"),
    ("8529.10.10", 10, "Antenas exteriores para TV o radiodifusion"),
    ("8529.10.20", 10, "Antenas parabolicas"),
    ("8529", 20, "Partes de los aparatos de las partidas 85.25 a 85.28"),
    ("8801", 20, "Globos, dirigibles y planeadores"),
    ("8903.31.11", 20, "Yates (ley: 8903.91.10)"), ("8903.32.11", 20, "Yates (ley: 8903.91.10)"),
    ("8903.33.11", 20, "Yates (ley: 8903.91.10)"), ("8903.99.20", 20, "Motocicletas acuaticas (jet ski)"),
    ("9101", 20, "Relojes con caja de metal precioso"), ("9111.10.00", 20, "Cajas de metal precioso"),
    ("9113.10.00", 20, "Pulseras de metal precioso"),
    ("9302", 78, "Revolveres y pistolas"),
]

# Codigos de la ley sin correspondencia clara en la 7ma Enmienda: no se aplican solos.
PENDIENTES = {
    "8525.80.20": ("Camaras digitales", 20, ["8525.81", "8525.83", "8525.89"]),
    "8525.80.30": ("Videocamaras", 20, ["8525.81", "8525.83", "8525.89"]),
    "8519.81.91": ("Reproductores de casetes de bolsillo", 20, ["8519.81"]),
    "8529.10.91": ("Antenas para telefonia celular y buscapersonas", 10, ["8529.10.90"]),
}

# Alcohol y tabaco: montos especificos con vigencia en isc_montos_especificos.json (Res. DGII por
# periodo; Ley 11-92 Art. 375 Parr. I, III, V y VIII). El texto es el del periodo vigente al generar;
# en consulta, capa1_sqlite/isc_especifico.py lo recalcula segun la fecha.
sys.path.insert(0, os.path.join(_RAIZ, "capa1_sqlite"))
from isc_especifico import isc_especifico  # noqa: E402

# 2402 sin monto en la resolucion (puros, cigarritos): solo consta el ad valorem del Parr. VIII.
TABACO_SIN_MONTO = ("20% ad valorem sobre el precio de venta al por menor (Art. 375 Parr. VIII); la resolucion "
                    "DGII de montos especificos no lista este codigo: verificar monto especifico con la DGII")


def isc_tabaco_alcohol(son):
    esp = isc_especifico(son)
    return esp["texto"] if esp else TABACO_SIN_MONTO

COMBUSTIBLE = ("Monto especifico por galon de la Ley 112-00 (ajustado periodicamente: verificar monto vigente "
               "MICM/DGII) + 16% ad valorem (Art. 23 Ley 557-05, mod. Art. 30 Ley 495-06)")
COMBUSTIBLES = {
    "2710.12.11": "", "2710.12.13": "", "2710.12.20": "", "2710.12.41": "", "2710.12.60": "",
    "2710.12.14": " + RD$5.00/galon gasolina regular (Art. 31 Ley 495-06)",
    "2710.12.51": " + RD$3.00/galon gasoil (Art. 31 Ley 495-06)",
    "2710.12.52": " + RD$3.00/galon gasoil (Art. 31 Ley 495-06)",
}


def main():
    con = sqlite3.connect(_DB)
    sons = dict(con.execute("SELECT son, descripcion FROM codigos").fetchall())
    con.close()

    caps = {}

    def poner(son, isc, nota, cap_desc, base):
        cap = caps.setdefault(son[:2], {"descripcion": cap_desc, "base_legal": base, "tipo": "",
                                        "tasas": {}, "partidas_afectadas": [], "codigos_verificados": {}})
        cap["codigos_verificados"].setdefault(son, {"isc": isc, "descripcion": nota})

    # Bienes del Art. 375: el prefijo mas especifico manda (8529.10.10 al 10% antes que 8529 al 20%)
    for prefijo, tasa, nota in sorted(BIENES_AD_VALOREM, key=lambda x: -len(x[0])):
        hallados = [s for s in sons if s.startswith(prefijo)]
        if not hallados:
            raise SystemExit(f"Sin SON vigente para {prefijo} ({nota}): revisar correlacion")
        for son in hallados:
            poner(son, f"{tasa}%", nota, "Bienes gravados Art. 375", f"{ART375} - ad valorem sobre CIF + gravamen")
        if len(prefijo) == 4:
            caps[prefijo[:2]]["partidas_afectadas"].append(prefijo)

    for son in sorted(s for s in sons if s[:4] in ("2203", "2204", "2205", "2206", "2207", "2208")):
        poner(son, isc_especifico(son)["texto"], sons[son][:80], "Productos del alcohol (Art. 379)", f"{ART375} Parr. I-III")
    for son in sorted(s for s in sons if s.startswith("2402")):
        poner(son, isc_tabaco_alcohol(son), sons[son][:80], "Productos del tabaco (Art. 379)", f"{ART375} Parr. V, VII, VIII")
    for son, extra in COMBUSTIBLES.items():
        if son in sons:
            poner(son, COMBUSTIBLE + extra, sons[son][:80], "Combustibles fosiles",
                  "Ley 112-00; Art. 23 Ley 557-05 (mod. Art. 30 Ley 495-06); Art. 31 Ley 495-06")

    for ley, (nota, tasa, candidatos) in PENDIENTES.items():
        for son in (s for s in sons if any(s.startswith(c) for c in candidatos)):
            previo = caps.get(son[:2], {}).get("codigos_verificados", {}).pop(son, None)
            alternativa = f" o {previo['isc']} ({previo['descripcion']})" if previo else ""
            poner(son, f"VERIFICAR {tasa}%{alternativa} - Art. 375 grava '{nota}' (codigo de la ley {ley}); "
                       f"correlacion con la 7ma Enmienda pendiente de confirmar con DGA",
                  sons[son][:80], "Bienes gravados Art. 375", ART375)

    for cap in caps.values():
        cap["codigos_verificados"] = dict(sorted(cap["codigos_verificados"].items()))
        tasas = {v["isc"] for v in cap["codigos_verificados"].values()}
        cap["tipo"] = "ad_valorem" if all(t.endswith("%") for t in tasas) else "mixto"
        if len(tasas) == 1:
            cap["tasas"]["default"] = tasas.pop()
        cap["partidas_afectadas"] = sorted(set(cap["partidas_afectadas"]))

    datos = {
        "_meta": {
            "descripcion": "ISC (Impuesto Selectivo al Consumo) por SON del Arancel RD",
            "fuente_legal": ("Ley 11-92 Titulo IV, Art. 375 (mod. Ley 253-12) y Art. 379; Ley 112-00; "
                             "Art. 23 Ley 557-05 (mod. Art. 30 Ley 495-06); Art. 31 Ley 495-06"),
            "generado_por": "scripts/build_isc_lookup.py (0% IA)",
            "nota": ("Ad valorem del Art. 375: base CIF + gravamen en importacion. Alcohol y tabaco: monto "
                     "especifico ajustable por inflacion + ad valorem sobre precio al por menor. Vehiculos "
                     "(Cap. 87) NO pagan ISC: pagan impuesto por emision de CO2 (Ley 253-12; Norma General "
                     "DGII 06-2012) y 17% de primer registro (Art. 22 Ley 557-05), ambos en la DGII."),
            "pendientes_correlacion": {k: {"descripcion": v[0], "tasa_ley": f"{v[1]}%", "candidatos": v[2]}
                                       for k, v in PENDIENTES.items()},
        },
        "capitulos_con_isc": dict(sorted(caps.items())),
        "regla_general": f"ISC solo aplica a los SON listados aqui ({ART375} y leyes de combustibles). Resto: NO APLICA",
    }
    with open(_SALIDA, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
    total = sum(len(c["codigos_verificados"]) for c in caps.values())
    print(f"{total} SON con ISC en {len(caps)} capitulos -> {_SALIDA}")


if __name__ == "__main__":
    main()
