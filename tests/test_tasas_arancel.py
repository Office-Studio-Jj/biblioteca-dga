"""DAI e ITBIS de Capa 1 contra valores leídos a ojo en el PDF del Arancel (Decreto 36-22).

Págs. 37-38 (carnes), 67 (tomates), 537-538 (módulos de pantalla 85.24). Antes la base tomaba
la marca EX. ITBIS ("0") como DAI y corría tasas en filas de varias líneas.
"""

import json
import os
import sys

_RAIZ = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(_RAIZ, "capa1_sqlite"))
sys.path.insert(0, os.path.join(_RAIZ, "notebooklm_skill", "scripts"))

from tasas import tasas_son  # noqa: E402

# (DAI, ITBIS) según la imagen de cada página
_VISTO_EN_PDF = {
    "0201.10.00": ("40", "EXENTO"),  # carne bovina, pág. 37
    "0202.30.10": ("25", "EXENTO"),  # pág. 38
    "0204.10.00": ("20", "18"),      # cordero: EX. ITBIS vacío, pág. 38
    "0702.00.11": ("20", "EXENTO"),  # tomates, pág. 67
    "8524.91.11": ("0", "18"),       # pantallas LCD con controladores, pág. 537
    "8524.91.15": ("3", "18"),
    "8524.91.17": ("20", "18"),
    "8524.92.11": ("0", "18"),       # tasa en la pág. 538 (fila que cruza de página)
    "8524.92.15": ("3", "18"),       # pág. 538
    "8524.92.16": ("8", "18"),
    "8524.99.11": ("0", "18"),
    "8524.99.17": ("20", "18"),
}


def test_tasas_vistas_en_el_pdf():
    for son, (dai, itbis) in _VISTO_EN_PDF.items():
        t = tasas_son(son)
        assert t, son
        assert (t["dai"], t["itbis"]) == (dai, itbis), son


def test_dai_solo_tasas_oficiales_ley_146_00():
    with open(os.path.join(_RAIZ, "notebooklm_skill", "data", "fuentes_nomenclatura",
                           "tasas_arancel_pdf.json"), encoding="utf-8") as f:
        datos = json.load(f)
    tasas = datos["tasas"]
    assert len(tasas) >= 7690
    raros = {s for s, v in tasas.items() if v["dai"] not in {"0", "3", "8", "14", "20", "25", "40"}}
    assert raros == set(datos["_meta"]["dai_no_oficial_o_ausente"])
    assert len(raros) <= 11  # quedan a revisión humana, no se cargan a la base


def test_correccion_manual_prevalece():
    t = tasas_son("8543.70.00")
    assert t["dai"] == "0" and t["fuente"] == "manual"


def test_capa1_del_pipeline_usa_sqlite():
    import pipeline_3_capas as p
    r = p.capa_1_claude_validador("carne bovina en canales", "0201.10.00")
    assert r["gravamen"] == "40%" and r["itbis"].startswith("EXENTO")
    r = p.capa_1_claude_validador("pantalla lcd para celular", "8524.91.11")
    assert r["codigo_existe"] and r["gravamen"] == "0%" and r["itbis"].startswith("18%")


def test_lectura_del_texto_del_cache():
    from verificador_arancelario import _extraer_gravamen_de_cache as g
    assert g("-En canales o medias canales 40 0") == 40
    assert g("- Teléfonos inteligentes 20") == 20
    assert g("-Para siembra 0 0") == 0
