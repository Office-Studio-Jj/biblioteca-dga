"""Montos especificos del ISC con vigencia (BR-20261002-2205, Res. DGII DDG-AR1-2026-00068)."""

import json
import os
import sys
from datetime import date
from unittest import mock

_RAIZ = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _RAIZ)
sys.path.insert(0, os.path.join(_RAIZ, "capa1_sqlite"))
sys.path.insert(0, os.path.join(_RAIZ, "notebooklm_skill", "scripts"))

import isc_especifico as ie  # noqa: E402

_HOY = date(2026, 10, 15)


def _con_hoy(fn):
    def envuelto():
        with mock.patch.object(ie, "hoy_rd", return_value=_HOY):
            fn()
    envuelto.__name__ = fn.__name__
    return envuelto


@_con_hoy
def test_oct_dic_2026_devuelve_montos_nuevos():
    r = ie.isc_especifico("2402.20.10")
    assert r["estado"] == "vigente" and r["montos"][0]["monto"] == "65.02"
    assert "DDG-AR1-2026-00068" in r["texto"] and r["fuente"].startswith("https://www.aduanas.gob.do/")
    assert ie.isc_especifico("2402.20.30")["montos"][0]["monto"] == "32.51"
    alcohol = ie.isc_especifico("2208.40.11")
    assert "RD$768.65 por litro de alcohol absoluto" in alcohol["texto"]
    assert ie.isc_especifico("2203.00.00")["montos"][0]["monto"] == "768.65"


@_con_hoy
def test_2402_90_00_lleva_ambas_presentaciones():
    texto = ie.texto_isc("2402.90.00")
    assert "RD$65.02 por cajetilla de 20" in texto and "RD$32.51 por cajetilla de 10" in texto


@_con_hoy
def test_jul_sep_2026_es_historico_y_nunca_vigente():
    r = ie.isc_especifico("2402.20.10", "2026-08-15")
    assert r["estado"] == "historico" and r["montos"][0]["monto"] == "64.65"
    assert r["texto"].startswith("HISTORICO, no vigente")
    assert ie.isc_especifico("2208.40.11", "2026-09-30")["montos"][0]["monto"] == "764.29"
    # Hoy (oct-2026) jamas se muestra un monto de jul-sep
    assert "64.65" not in ie.texto_isc("2402.20.10") and "764.29" not in ie.texto_isc("2208.40.11")


def test_despues_del_31_12_2026_dice_por_verificar():
    with mock.patch.object(ie, "hoy_rd", return_value=date(2027, 1, 5)):
        r = ie.isc_especifico("2402.20.10")
    assert r["estado"] == "por_verificar" and r["montos"] == []
    assert "por verificar" in r["texto"] and "dgii.gov.do" in r["texto"]
    assert "65.02" not in r["texto"]


def test_codigos_sin_monto_especifico():
    assert ie.isc_especifico("8415.10.00") is None
    assert ie.isc_especifico("2402.10.11") is None  # puros: la resolucion no los lista
    assert ie.texto_isc("8528.72.00", "10%") == "10%"


@_con_hoy
def test_pipeline_capa1_muestra_monto_y_enlace():
    import pipeline_3_capas as p
    with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
        c1 = p.capa_1_claude_validador("cigarrillos de tabaco negro, cajetilla de 20", "2402.20.10")
    assert "RD$65.02 por cajetilla de 20" in c1["isc"] and "aduanas.gob.do" in c1["isc"]


@_con_hoy
def test_consultor_isc_y_lookup_coinciden_con_la_resolucion():
    import consultor_isc
    r = consultor_isc.consultar_isc("2208.40.11")
    assert "RD$768.65" in r["isc"] and r["certeza"] == "ALTA"
    lookup = json.load(open(os.path.join(_RAIZ, "notebooklm_skill", "data", "fuentes_nomenclatura",
                                         "isc_lookup.json"), encoding="utf-8-sig"))
    assert lookup["capitulos_con_isc"]["24"]["codigos_verificados"]["2402.20.30"]["isc"] == ie.texto_isc("2402.20.30")
