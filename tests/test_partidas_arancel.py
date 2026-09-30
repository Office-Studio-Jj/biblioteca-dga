"""Integridad de partidas_arancel.json (Arancel 7ma Enmienda, Decreto 36-22; extraído con pdfplumber)."""

import json
import os
import re

_JSON = os.path.join(os.path.dirname(__file__), "..", "notebooklm_skill", "data",
                     "fuentes_nomenclatura", "partidas_arancel.json")

with open(_JSON, encoding="utf-8") as f:
    _PARTIDAS = json.load(f)["partidas"]


def test_todas_las_partidas_sa_2022():
    assert len(_PARTIDAS) == 1228
    capitulos = {k[:2] for k in _PARTIDAS}
    assert capitulos == {f"{c:02d}" for c in range(1, 98)} - {"77"}  # Cap. 77 reservado en el SA


def test_sin_tasa_ni_titulos_pegados():
    for codigo, texto in _PARTIDAS.items():
        assert not re.search(r"\s\d{1,2}(\s+\[\d{2}\.\d{2}\]|\s+[IVXL]+\.-)", texto), codigo
        assert not re.search(r"\s\d{1,2}$", texto), codigo


def test_textos_que_continuan_con_codigos_o_notas():
    assert _PARTIDAS["87.08"].endswith("de las partidas 87.01 a 87.05.")
    assert _PARTIDAS["90.29"].endswith("90.14 o 90.15; estroboscopios.")
    assert _PARTIDAS["85.17"].endswith("84.43, 85.25, 85.27 u 85.28.")
    assert _PARTIDAS["30.06"].endswith("la Nota 4 de este Capítulo.")
    assert _PARTIDAS["15.03"].endswith("mezclar ni preparar de otro modo.")
    assert _PARTIDAS["85.24"].startswith("Módulos de visualización")
