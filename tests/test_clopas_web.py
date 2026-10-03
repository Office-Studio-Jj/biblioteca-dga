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
    # Ad valorem: 10 % alcohol (DGII) y 20 % tabaco (Ley 30-26, Art. 42). El 7.5 % no tenia sustento.
    assert "10&nbsp;% para el alcohol y 20&nbsp;% para el tabaco" in seccion
    assert "Gaceta Oficial" in seccion
    assert "7.5 %" not in seccion and "7,5 %" not in seccion


def test_instalar_marca_y_aviso_legal():
    resp = server.app.test_client().get("/instalar")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    titulo = "Instalar CLOPAS — Consultoría Logística de Puertos y Aduanas"
    assert f"<title>{titulo}</title>" in html and titulo in html.split("<h1", 1)[1]
    assert "Distribuido oficialmente por" not in html
    assert "consultoria.puertos.aduanas@gmail.com" in html
    assert ("CLOPAS es una consultoría privada y no es una entidad del Estado. Sus respuestas orientan; "
            "la clasificación oficial de una mercancía la determina la Dirección General de Aduanas.") in html
    assert 'id="btnAbrirApp"' in html and "getElementById('btnAbrirApp').href" in html


def test_instalar_master_ve_opciones_de_admin():
    client = server.app.test_client()
    html = client.get("/instalar").get_data(as_text=True)
    assert 'id="btnWa"' not in html and 'id="urlBox"' not in html
    with client.session_transaction() as s:
        s["logged_in"] = True
        s["role"] = "master"
    html = client.get("/instalar").get_data(as_text=True)
    assert 'id="btnWa"' in html and 'id="urlBox"' in html and 'id="btnEmail"' in html
