"""Extrae de cada SON (XXXX.XX.XX) la tasa GRAV. (DAI, Ley 146-00) y la marca EX. ITBIS del
Arancel 7ma Enmienda (Decreto 36-22) leyendo la POSICIÓN de las columnas (pdfplumber, 0% IA).

Por qué por posición: el texto plano pone "40 0" al final de la descripción (GRAV. y EX. ITBIS)
y los lectores que tomaban el último número guardaban 0 como DAI (carne bovina 0201.10.00:
40% en el PDF, 0% en la base). En filas de varias líneas la tasa va en la última línea, así que
se asigna al último SON abierto. Algunas páginas imprimen cada carácter dos veces ("1144" = 14):
se limpian con dedupe_chars.

Salida: notebooklm_skill/data/fuentes_nomenclatura/tasas_arancel_pdf.json
    {"_meta": {...}, "tasas": {"0201.10.00": {"dai": "40", "ex_itbis": true, "pag": 37,
                                              "descripcion": "- En canales o medias canales"}}}
Uso: python capa1_sqlite/extraer_tasas_pdf.py   (tarda unos minutos)
"""

import json
import os
import re
import sys

import pdfplumber

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_partidas import _PDF, _deshacer_duplicado  # noqa: E402

_SALIDA = os.path.join(os.path.dirname(_PDF), "tasas_arancel_pdf.json")
DAI_OFICIALES = {"0", "3", "8", "14", "20", "25", "40"}  # Ley 146-00

_SON = re.compile(r"^\d{4}\.\d{2}\.\d{2}$")
_CODIGO = re.compile(r"^(\d{4}\.\d{2}(\.\d{2})?|\d{2}\.\d{2}\.?)$")  # SON, subpartida o partida
_NUM = re.compile(r"^\d{1,3}$")
_LINEA_SON = re.compile(r"^(\d{4}\.\d{2}\.\d{2})\s+(.*)$")
_FIN_BLOQUE = re.compile(r"^(\d{4}\.\d{2}(\.\d{2})?\s|\d{2}\.\d{2}\.?\s|CÓDIGO|ARANCEL DE|GRAV\.|ITBIS|"
                         r"Notas?(\.|\s*$)|Capítulo \d+\s*$|Sección|SECCIÓN)")


def _tasas_pagina(pagina, abierto=None):
    """({son: {"dai", "itbis"}}, son abierto al final). Según la columna de cada número.

    `abierto` es el SON cuya descripción siguió en esta página sin tasa todavía
    (8524.92.11 empieza en la pág. 537 y su "0" está arriba de la 538)."""
    pagina = pagina.dedupe_chars(tolerance=1)
    palabras = pagina.extract_words()
    cab = [w for w in palabras if w["text"].upper().startswith("GRAV")]
    if not cab:
        return {}, None
    gx0, gx1 = cab[0]["x0"] - 6, cab[0]["x1"] + 8
    itb = [w for w in palabras if "ITBIS" in w["text"].upper()]
    ix0 = itb[0]["x0"] - 6 if itb else gx1
    if itb:  # en algunas páginas el título "GRAV." está corrido; la columna va pegada a EX. ITBIS
        gx0, gx1 = max(gx0, itb[0]["x0"] - 45), ix0
    izquierda = pagina.width * 0.25
    fichas = []
    for w in palabras:
        t = w["text"]
        if w["x0"] < izquierda and _CODIGO.match(t):
            fichas.append((round(w["top"]), 0, "codigo", t))
        elif _NUM.match(t) and w["x0"] >= gx0 and w["x1"] <= gx1:
            fichas.append((round(w["top"]), 1, "dai", t))
        elif _NUM.match(t) and w["x0"] >= ix0:
            fichas.append((round(w["top"]), 1, "itbis", t))
    fichas.sort()
    filas, actual = {}, abierto
    if abierto:
        filas[abierto] = {"dai": None, "itbis": None}
    for _, _, tipo, t in fichas:
        if tipo == "codigo":
            actual = t if _SON.match(t) else None  # partida o subpartida cierra la fila anterior
            if actual:
                filas.setdefault(actual, {"dai": None, "itbis": None})
        elif actual:
            if filas[actual][tipo] is None:
                filas[actual][tipo] = t
    if abierto and filas[abierto]["dai"] is None:
        del filas[abierto]
    sigue = actual if actual and filas.get(actual, {}).get("dai") is None else None
    return filas, sigue


def _descripciones_pagina(pagina):
    """Texto de cada SON (varias líneas unidas), sin las tasas del final."""
    lineas = [_deshacer_duplicado(l.strip()) for l in (pagina.extract_text() or "").splitlines()]
    out, i = {}, 0
    while i < len(lineas):
        m = _LINEA_SON.match(lineas[i])
        if not m:
            i += 1
            continue
        son, texto = m.group(1), [m.group(2)]
        i += 1
        while (i < len(lineas) and not _FIN_BLOQUE.match(lineas[i]) and not lineas[i].startswith("-")
               and not re.search(r"\s\d{1,2}(\s+\d{1,2})?$", texto[-1])):
            texto.append(lineas[i])
            i += 1
        out.setdefault(son, " ".join(" ".join(texto).split()))
    return out


def main():
    tasas, abierto = {}, None
    with pdfplumber.open(_PDF) as pdf:
        for n, pagina in enumerate(pdf.pages, start=1):
            descs = _descripciones_pagina(pagina)
            filas, sigue = _tasas_pagina(pagina, abierto)
            for son, v in filas.items():
                dai, ex_itbis = v["dai"], v["itbis"] is not None
                if son in tasas and tasas[son]["dai"] is not None:
                    continue
                if son in tasas:  # fila que siguió desde la página anterior
                    tasas[son].update({"dai": dai, "ex_itbis": ex_itbis})
                    continue
                desc = descs.get(son, "")
                if dai is not None:  # quitar "40 0" / "20" del final de la descripción
                    desc = re.sub(rf"\s{dai}(\s+\d{{1,2}})?$", "", desc)
                else:  # quitar el número de página que cierra la columna
                    desc = re.sub(r"\s\d{1,3}$", "", desc)
                tasas[son] = {"dai": dai, "ex_itbis": ex_itbis, "pag": n, "descripcion": desc}
            abierto = sigue
    revisar = sorted(s for s, v in tasas.items() if v["dai"] not in DAI_OFICIALES)
    datos = {"_meta": {"fuente": os.path.basename(_PDF), "norma": "Decreto 36-22 (Arancel 7ma Enmienda)",
                       "metodo": "pdfplumber, posición de columnas GRAV. y EX. ITBIS (0% IA)",
                       "total": len(tasas), "dai_no_oficial_o_ausente": revisar},
             "tasas": dict(sorted(tasas.items()))}
    with open(_SALIDA, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
    print(f"{len(tasas)} SON -> {_SALIDA} ({len(revisar)} a revisión humana)")


if __name__ == "__main__":
    main()
