"""Extrae el texto de las partidas (4 dígitos, NN.NN) del Arancel 7ma Enmienda (pdfplumber, 0% IA).

Salida: notebooklm_skill/data/fuentes_nomenclatura/partidas_arancel.json
    {"_meta": {...}, "partidas": {"83.06": "Campanas, campanillas, gongs ...", ...}}
Uso: python capa1_sqlite/build_partidas.py
"""

import json
import os
import re

import pdfplumber

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PDF = os.path.join(_RAIZ, "notebooklm_skill", "data", "fuentes_nomenclatura",
                    "Arancel 7ma enmienda de la republica dominicana.pdf")
_SALIDA = os.path.join(_RAIZ, "notebooklm_skill", "data", "fuentes_nomenclatura", "partidas_arancel.json")

_PARTIDA = re.compile(r"^(\d{2}\.\d{2})\.?\s+(\S.*)$")  # "10.03. Cebada." lleva punto
_PARTIDA_UNICA = re.compile(r"^(\d{2})(\d{2})\.00(?:\.00)?\s+(\S.*)$")  # NNNN.00.00 o NNNN.00 (sin subpartidas SA)
_CORTE = re.compile(r"^(\d{4}\.\d{2}(\.\d{2})?\s|-|CÓDIGO|ARANCEL DE ADUANAS|GRAV\.|ITBIS|\d{1,3}$|Notas?\b|Capítulo \d)")


def _es_inicio_texto(texto):
    """Texto de partida: empieza en mayúscula o entre comillas («Tall oil», «T-shirts»)."""
    return texto[0].isupper() or (texto[0] == "«" and texto[1:2].isalpha())


def _deshacer_duplicado(linea):
    """Algunas páginas repiten cada carácter ("8855..0011" = "85.01")."""
    c = linea.replace(" ", "")
    if len(c) > 3 and sum(c[k] == c[k + 1] for k in range(0, len(c) - 1, 2)) / max(1, len(c) // 2) > 0.8:
        out, k = "", 0
        while k < len(linea):
            out += linea[k]
            k += 2 if k + 1 < len(linea) and linea[k + 1] == linea[k] else 1
        return out
    # Solo el código inicial duplicado: "8855..3399 Lámparas..." -> "85.39 Lámparas..."
    return re.sub(r"^(\d)\1(\d)\2\.\.(\d)\3(\d)\4(?=\s)", r"\1\2.\3\4", linea)


def main():
    partidas = {}
    with pdfplumber.open(_PDF) as pdf:
        for pagina in pdf.pages:
            lineas = [_deshacer_duplicado(l.strip()) for l in (pagina.extract_text() or "").splitlines()]
            i = 0
            while i < len(lineas):
                m = _PARTIDA.match(lineas[i])
                u = None if m else _PARTIDA_UNICA.match(re.sub(r"^(\d)\1(\d)\2(\d)\3(\d)\4\.\.0000\.\.0000",
                                                             r"\1\2\3\4.00.00", lineas[i]))
                if u and _es_inicio_texto(u.group(3)):
                    # Partida sin subdivisión: el texto está en la línea NNNN.00.00
                    codigo, texto = f"{u.group(1)}.{u.group(2)}", [u.group(3)]
                elif not m or not _es_inicio_texto(m.group(2)):
                    i += 1
                    continue
                else:
                    codigo, texto = m.group(1), [m.group(2)]
                i += 1
                while i < len(lineas) and not _CORTE.match(lineas[i]) and not _PARTIDA.match(lineas[i]) \
                        and not texto[-1].rstrip().endswith("."):
                    texto.append(lineas[i])
                    i += 1
                limpio = " ".join(" ".join(texto).split())
                limpio = re.sub(r"(\s+\d{1,2})+$", "", limpio)
                if u and codigo in partidas:
                    continue
                if codigo not in partidas or len(limpio) > len(partidas[codigo]):
                    partidas[codigo] = limpio
    datos = {"_meta": {"fuente": os.path.basename(_PDF), "metodo": "pdfplumber (0% IA)",
                       "total_partidas": len(partidas)},
             "partidas": dict(sorted(partidas.items()))}
    with open(_SALIDA, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
    print(f"{len(partidas)} partidas -> {_SALIDA}")


if __name__ == "__main__":
    main()
