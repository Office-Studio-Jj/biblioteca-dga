"""Pruebas del lector SIREVUCE con HTML sintético basado en capturas del portal (25-09-2026)."""

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sub_agentes import consultor_sirevuce as cs  # noqa: E402

REPORTE = """
<table class="table"><thead><tr><th>Código</th><th>Categoria</th><th>Descripción</th><th>Acción</th></tr></thead>
<tbody>
<tr><td><a href="/Home/Details?id=90229010&amp;Trades=1">90229010</a></td>
<td>Aparatos de rayos X y aparatos que utilicen radiaciones alfa, beta o gamma, incl</td>
<td>- - Pantallas radiológicas, incluidas las que incorporan antidifusantes</td>
<td><a class="btn" href="/Home/Details?id=90229010&amp;Trades=1">Ver</a></td></tr>
<tr><td><a href="/Home/Details?id=90106000&amp;Trades=1">90106000</a></td>
<td>Aparatos y material para laboratorios fotográfico o cinematográfico, no expresad</td>
<td>- Pantallas de proyección</td>
<td><a class="btn" href="/Home/Details?id=90106000&amp;Trades=1">Ver</a></td></tr>
</tbody></table>
"""

DETALLE_CON_VUCE = """
<div class="card"><div class="card-header">Información General (despacho a consumo)</div>
<div class="card-body">
<p><b>Código:</b> 90229010</p>
<p><b>Descripción:</b> - - Pantallas radiológicas, incluidas las que incorporan antidifusantes</p>
<p><b>Categoría:</b> Aparatos de rayos X y aparatos que utilicen radiaciones alfa, beta o gamma, incl</p>
<p><b>Gravamen:</b> 0%</p><p><b>ITBIS :</b> 18%</p>
<p><b>Selectivo Específico:</b> 0</p><p><b>Selectivo Ad Valorem:</b> 0%</p>
</div></div>
<div class="card"><div class="card-header">Formularios VUCE (Seleccionar de acuerdo con el uso)</div>
<div class="card-body">
<button class="accordion"><span>Importación de Productos Sanitarios y Equipos Médicos</span>
<span>&#9660;</span><span>(Dar clic para ver requisitos)</span></button>
<div class="panel"><div class="row"><div class="col">
<h5>Tipo de Trámite</h5><p>Importación</p>
<h5>Organismos externos</h5><p>MINISTERIO DE SALUD PUBLICA Y ASISTENCIA SOCIAL</p>
<h5>Uso</h5><p>Comercializar</p>
<h5>Formulario</h5><p>Importación de Productos Sanitarios y Equipos Médicos</p>
<h5>Certificado Fitosanitario</h5><span class="badge">No requiere certificado</span>
</div><div class="col">
<h5>Costo</h5><p>DOP 1,000.00</p>
<h5>Concepto Costo</h5><ul><li>1 - Tarifa Servicios DIGEMAPS DOP 1,000.00</li></ul>
<h5>Documentos</h5><ul><li>Factura Comercial</li><li>Ficha Técnica del Producto</li>
<li>Registro Sanitario.</li><li>Guía Aérea/ Documento de embarque</li><li></li></ul>
</div></div>
<p>— Última fecha de revisión: <i>18/03/2026 8:58:23</i></p>
<a class="btn">Solicitar servicio</a></div>
</div></div>
<p><b>Nota:</b> La presente respuesta se emite con fines meramente informativos.</p>
"""

DETALLE_SIN_VUCE = DETALLE_CON_VUCE.split('<div class="card"><div class="card-header">Formularios')[0] + \
    '<div class="card"><div class="card-header">Formularios VUCE (Seleccionar de acuerdo con el uso)</div>' \
    '<div class="card-body"></div></div><p><b>Nota:</b> informativo.</p>'


def test_normalizar_son():
    assert cs.normalizar_son("90229010") == "9022.90.10"
    assert cs.normalizar_son("partida 8524.91.11 lcd") == "8524.91.11"
    assert cs.normalizar_son("8524.91.11.00") is None
    assert cs.normalizar_son("pantalla") is None


def test_parsear_reporte():
    filas = cs.parsear_reporte(REPORTE)
    assert [f["son"] for f in filas] == ["9022.90.10", "9010.60.00"]
    assert filas[0]["detalle_href"] == "/Home/Details?id=90229010&Trades=1"
    assert filas[1]["descripcion"] == "- Pantallas de proyección"


def test_parsear_detalle_con_formulario():
    d = cs.parsear_detalle(DETALLE_CON_VUCE)
    assert d["son"] == "9022.90.10"
    assert d["gravamen"] == "0%" and d["itbis"] == "18%"
    assert len(d["formularios"]) == 1
    f = d["formularios"][0]
    assert f["nombre"] == "Importación de Productos Sanitarios y Equipos Médicos"
    assert f["campos"]["Organismos externos"] == ["MINISTERIO DE SALUD PUBLICA Y ASISTENCIA SOCIAL"]
    assert f["campos"]["Costo"] == ["DOP 1,000.00"]
    assert "Registro Sanitario." in f["campos"]["Documentos"]
    assert f["campos"]["Certificado Fitosanitario"] == ["No requiere certificado"]
    assert f["campos"]["Última fecha de revisión"] == ["18/03/2026 8:58:23"]


def test_parsear_detalle_sin_formulario():
    d = cs.parsear_detalle(DETALLE_SIN_VUCE)
    assert d["seccion_vuce_presente"] and d["formularios"] == []


def _fake_get(paginas):
    def _g(path, params=None):
        if params:
            return paginas["reporte"], cs.BASE_URL + "/Home/Report?" + cs.urllib.parse.urlencode(params)
        return paginas[path], cs.BASE_URL + path
    return _g


def test_consultar_por_codigo_requiere_vuce():
    cs._cache.clear()
    pag = {"reporte": REPORTE, "/Home/Details?id=90229010&Trades=1": DETALLE_CON_VUCE}
    with mock.patch.object(cs, "_get", side_effect=_fake_get(pag)):
        r = cs.consultar_sirevuce("9022.90.10")
    assert r["estado"] == "VERIFICADO"
    assert len(r["resultados"]) == 1 and r["resultados"][0]["requiere_vuce"] is True
    bloque = cs.formatear_bloque(r)
    assert "SÍ requiere VUCE" in bloque and "DIGEMAPS" not in bloque.split("Organismo")[0]


def test_consultar_sin_formulario():
    cs._cache.clear()
    pag = {"reporte": REPORTE, "/Home/Details?id=90229010&Trades=1": DETALLE_SIN_VUCE}
    with mock.patch.object(cs, "_get", side_effect=_fake_get(pag)):
        r = cs.consultar_sirevuce("90229010")
    assert r["resultados"][0]["requiere_vuce"] is False
    assert "NO requiere formulario VUCE" in cs.formatear_bloque(r)


def test_portal_caido_no_verificado():
    cs._cache.clear()
    with mock.patch.object(cs, "_get", side_effect=OSError("403")):
        r = cs.consultar_sirevuce("9022.90.10")
    assert r["estado"] == "NO_VERIFICADO"
    assert "NO VERIFICADO" in cs.formatear_bloque(r)
    assert cs._cache == {}


_FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _html_real(nombre):
    with open(os.path.join(_FIX, nombre), encoding="utf-8") as f:
        return f.read()


def test_html_real_del_portal_por_codigo():
    """Páginas reales de sirevuce.aduanas.gob.do capturadas el 25-09-2026."""
    cs._cache.clear()
    pag = {"reporte": _html_real("sirevuce_reporte_90229010.html"),
           "/Home/Details/7268?Trades=1": _html_real("sirevuce_detalle_7268.html")}
    llamadas = []

    def _g(path, params=None):
        llamadas.append(params)
        return _fake_get(pag)(path, params)

    with mock.patch.object(cs, "_get", side_effect=_g):
        r = cs.consultar_sirevuce("9022.90.10")
    assert llamadas[0] == {"inputArancel": "90229010", "Trades": "1"}
    assert r["estado"] == "VERIFICADO"
    res = r["resultados"][0]
    assert res["son"] == "9022.90.10" and res["requiere_vuce"] is True
    assert res["gravamen"] == "0%" and res["itbis"] == "18%"
    f = res["formularios"][0]
    assert f["nombre"] == "Importación de Productos Sanitarios y Equipos Médicos"
    assert f["campos"]["Organismos externos"] == ["MINISTERIO DE SALUD PUBLICA Y ASISTENCIA SOCIAL"]
    assert f["campos"]["Costo"] == ["DOP 1,000.00"]
