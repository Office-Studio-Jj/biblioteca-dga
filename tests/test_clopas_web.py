"""/clopas: pagina publica de presentacion. Debe abrir sin sesion y respetar la marca."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import server  # noqa: E402


def _html():
    resp = server.app.test_client().get("/clopas")
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def test_abre_sin_sesion_y_enlaza_la_app():
    html = _html()
    assert "CLOPAS" in html
    assert 'href="/instalar"' in html and 'href="/login"' in html
    assert "/static/web/clopas.css" in html


def test_marca_y_aviso_legal():
    html = _html()
    # Rebranding: la app es de CLOPAS, no de la DGA, y no lleva escudo.
    assert "escudo" not in html.lower()
    assert "no es una entidad del Estado" in html
    assert "Ley 168-21" in html and "Decreto 755-22" in html


def test_css_publico():
    resp = server.app.test_client().get("/static/web/clopas.css")
    assert resp.status_code == 200


def test_seccion_calcula_y_clasifica():
    import re

    html = _html()
    texto = re.sub(r"<[^>]+>", "", html)
    assert 'id="calcula"' in html
    assert "Calcula y clasifica con respaldo" in texto
    assert (
        "Primero se clasifica y después se calcula: el cálculo solo sirve "
        "si la subpartida es la correcta." in texto
    )
    enlace = re.search(r'<a[^>]+href="https://siga\.aduanas\.gob\.do/Default\.aspx"[^>]*>', html)
    assert enlace, "falta el enlace al portal SIGA"
    rel = re.search(r'rel="([^"]*)"', enlace.group(0))
    assert rel and "noopener" in rel.group(1)
    assert "La Ley 3489 de 1953 fue derogada por la Ley 168-21." in texto
    assert "gratis" not in html.lower()
    assert "<form" not in html.lower()


def test_seccion_montos_isc_oct_dic_2026():
    # BR-20261002-2205: texto del brief, entre "Base legal" y "Para quien es", con enlace oficial.
    html = _html()
    i_legal, i_isc, i_quien = (html.index('id="titulo-legal"'), html.index('id="titulo-isc"'),
                               html.index('id="titulo-quien"'))
    assert i_legal < i_isc < i_quien
    seccion = html[i_isc:i_quien]
    assert "Montos del ISC, octubre-diciembre 2026" in seccion
    assert "Resolución DDG-AR1-2026-00068" in seccion
    for monto in ("RD$65.02 por cajetilla", "RD$32.51 por cajetilla", "RD$768.65 por litro de alcohol absoluto"):
        assert monto in seccion
    assert "Ley 11-92, Código Tributario, Art. 375, Párrafos I, III y IX." in seccion
    assert 'href="https://www.aduanas.gob.do/media/lu4c1bpi/' in seccion and "Ver la resolución oficial (PDF)" in seccion
    assert "La liquidación final la determina la Dirección General de Aduanas." in seccion
    # La app muestra los montos pero no calcula el ISC: no se promete un calculo.
    assert "aplica estos montos en el cálculo" not in seccion
