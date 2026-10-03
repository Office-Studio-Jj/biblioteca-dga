"""Contenido editable de /clopas: solo el master edita, se valida y se puede deshacer."""

import copy
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import clopas_contenido  # noqa: E402
import server  # noqa: E402


@pytest.fixture
def datos(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_DATA_DIR", tmp_path)
    return tmp_path


def _cliente(rol=None):
    c = server.app.test_client()
    if rol:
        with c.session_transaction() as s:
            s["logged_in"] = True
            s["role"] = rol
    return c


def _base():
    with open(clopas_contenido.DEFAULT_FILE, encoding="utf-8") as f:
        return json.load(f)


def test_contenido_por_defecto_es_valido():
    clopas_contenido.validar(_base())


def test_json_publico(datos):
    r = _cliente().get("/clopas/contenido.json")
    assert r.status_code == 200 and r.get_json()["portada"]["titulo"]


def test_solo_master_edita(datos):
    for rol in (None, "invitado", "operativo"):
        c = _cliente(rol)
        assert c.post("/clopas/contenido", json=_base()).status_code == 403
        assert c.post("/clopas/contenido/restaurar", json={}).status_code == 403
    assert _cliente().get("/clopas/editar").status_code == 302
    assert 'Editar esta página' not in _cliente("operativo").get("/clopas").get_data(as_text=True)


def test_master_guarda_y_deshace(datos):
    c = _cliente("master")
    assert c.get("/clopas/editar").status_code == 200
    assert "Editar esta página" in c.get("/clopas").get_data(as_text=True)
    nuevo = _base()
    nuevo["portada"]["titulo"] = "Titulo de prueba"
    nuevo["isc"]["filas"].append({"producto": "Producto nuevo", "monto": "RD$1.00"})
    r = c.post("/clopas/contenido", json=nuevo)
    assert r.status_code == 200
    v = r.get_json()["version"]
    assert v == _base()["version"] + 1
    html = _cliente().get("/clopas").get_data(as_text=True)
    assert "Titulo de prueba" in html and "Producto nuevo" in html
    assert c.post("/clopas/contenido/restaurar", json={}).status_code == 200
    html = _cliente().get("/clopas").get_data(as_text=True)
    assert "Titulo de prueba" not in html and _base()["portada"]["titulo"] in html


def test_rechaza_contenido_invalido_y_formularios(datos):
    c = _cliente("master")
    malo = _base()
    malo["portada"]["titulo"] = "   "
    r = c.post("/clopas/contenido", json=malo)
    assert r.status_code == 400 and "portada.titulo" in r.get_json()["error"]
    malo = _base()
    malo["funciones"][0]["accion"] = "javascript:alert(1)"
    assert c.post("/clopas/contenido", json=malo).status_code == 400
    malo["funciones"][0]["accion"] = "//evil.com"
    assert c.post("/clopas/contenido", json=malo).status_code == 400
    # Un formulario de otro sitio no puede enviar JSON.
    assert c.post("/clopas/contenido", data={"x": "1"}).status_code == 415


def test_escapa_html_y_permite_formato_limitado(datos):
    c = _cliente("master")
    nuevo = _base()
    nuevo["portada"]["entrada"] = '<script>alert(1)</script> **clave** [DGA](https://www.aduanas.gob.do) [x](javascript:alert(1))'
    assert c.post("/clopas/contenido", json=nuevo).status_code == 200
    html = _cliente().get("/clopas").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "<strong>clave</strong>" in html
    assert 'href="https://www.aduanas.gob.do"' in html
    assert 'href="javascript:' not in html


def test_version_del_repo_mayor_gana(datos, monkeypatch, tmp_path_factory):
    c = _cliente("master")
    nuevo = _base()
    nuevo["cierre"] = "Cierre editado en la web"
    assert c.post("/clopas/contenido", json=nuevo).status_code == 200
    # Un cambio publicado desde PowerShell con version mas alta reemplaza lo de la web.
    repo = copy.deepcopy(_base())
    repo["version"] = 99
    repo["cierre"] = "Cierre publicado desde el repo"
    f = tmp_path_factory.mktemp("repo") / "clopas.json"
    f.write_text(json.dumps(repo), encoding="utf-8")
    monkeypatch.setattr(clopas_contenido, "DEFAULT_FILE", f)
    assert "Cierre publicado desde el repo" in _cliente().get("/clopas").get_data(as_text=True)
