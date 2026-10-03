"""Contenido editable de la pagina publica /clopas.

- El contenido por defecto vive en el repo: contenido/clopas.json.
- Lo que el master edita desde la web se guarda en el volumen de datos
  (clopas_contenido.json) y la version anterior en clopas_contenido.prev.json.
- Gana el que tenga el "version" mas alto. Asi, un cambio publicado desde
  PowerShell (repo con version mayor) tambien llega a produccion.
- Los textos admiten **negrita** y [texto](https://enlace). Todo se escapa.
"""
import html
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

from markupsafe import Markup

DEFAULT_FILE = Path(__file__).resolve().parent / "contenido" / "clopas.json"
ICONOS = ("camara", "documento", "moneda", "lupa", "verificado", "candado")

_MAX_TEXTO = 2000
_MAX_ITEMS = 30


class ContenidoInvalido(ValueError):
    pass


def _rutas(data_dir):
    d = Path(data_dir)
    return d / "clopas_contenido.json", d / "clopas_contenido.prev.json"


def _leer(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def cargar(data_dir):
    """Devuelve el contenido vigente: el de mayor version entre repo y volumen."""
    base = _leer(DEFAULT_FILE) or {}
    actual, _ = _rutas(data_dir)
    guardado = _leer(actual)
    if guardado:
        try:
            guardado = validar(guardado)
            if guardado.get("version", 0) >= base.get("version", 0):
                return guardado
        except ContenidoInvalido:
            pass
    return base


def _texto(v, campo, requerido=True):
    if not isinstance(v, str):
        raise ContenidoInvalido(f"{campo}: debe ser texto")
    v = v.strip()
    if requerido and not v:
        raise ContenidoInvalido(f"{campo}: no puede quedar vacio")
    if len(v) > _MAX_TEXTO:
        raise ContenidoInvalido(f"{campo}: maximo {_MAX_TEXTO} caracteres")
    return v


def _lista(v, campo, minimo=1):
    if not isinstance(v, list) or not (minimo <= len(v) <= _MAX_ITEMS):
        raise ContenidoInvalido(f"{campo}: debe tener entre {minimo} y {_MAX_ITEMS} elementos")
    return v


def _accion(v, campo):
    v = _texto(v or "/", campo)
    # Solo rutas de la propia app o enlaces https.
    if not (re.fullmatch(r"/(?![/\\])[A-Za-z0-9_\-/#?=&.]*", v) or re.fullmatch(r"https://[^\s\"'<>]+", v)):
        raise ContenidoInvalido(f"{campo}: usa una ruta como / o un enlace https://")
    return v


def validar(c):
    """Valida y normaliza el contenido. Lanza ContenidoInvalido con el campo que falla."""
    if not isinstance(c, dict):
        raise ContenidoInvalido("el contenido debe ser un objeto JSON")
    try:
        p = c["portada"]
        out = {
            "version": int(c.get("version", 0)),
            "actualizado": str(c.get("actualizado", ""))[:40],
            "portada": {k: _texto(p[k], f"portada.{k}") for k in ("sobretitulo", "titulo", "entrada", "nota")},
            "funciones": [{
                "icono": f.get("icono") if f.get("icono") in ICONOS else "documento",
                "titulo": _texto(f["titulo"], f"funciones[{i}].titulo"),
                "texto": _texto(f["texto"], f"funciones[{i}].texto"),
                "accion": _accion(f.get("accion"), f"funciones[{i}].accion"),
            } for i, f in enumerate(_lista(c["funciones"], "funciones"))],
            "pasos": [{
                "titulo": _texto(s["titulo"], f"pasos[{i}].titulo"),
                "texto": _texto(s["texto"], f"pasos[{i}].texto"),
            } for i, s in enumerate(_lista(c["pasos"], "pasos"))],
            "calcula": {
                "intro": _texto(c["calcula"]["intro"], "calcula.intro"),
                "pasos": [{
                    "titulo": _texto(s["titulo"], f"calcula.pasos[{i}].titulo"),
                    "texto": _texto(s["texto"], f"calcula.pasos[{i}].texto"),
                } for i, s in enumerate(_lista(c["calcula"]["pasos"], "calcula.pasos"))],
                "requisitos": [_texto(r, f"calcula.requisitos[{i}]")
                               for i, r in enumerate(_lista(c["calcula"]["requisitos"], "calcula.requisitos"))],
            },
            "base_legal": {
                "intro": _texto(c["base_legal"]["intro"], "base_legal.intro"),
                "normas": [_texto(n, f"base_legal.normas[{i}]")
                           for i, n in enumerate(_lista(c["base_legal"]["normas"], "base_legal.normas"))],
            },
            "isc": {
                **{k: _texto(c["isc"][k], f"isc.{k}") for k in ("titulo", "intro", "nota", "base_legal", "enlace")},
                "filas": [{
                    "producto": _texto(r["producto"], f"isc.filas[{i}].producto"),
                    "monto": _texto(r["monto"], f"isc.filas[{i}].monto"),
                } for i, r in enumerate(_lista(c["isc"]["filas"], "isc.filas"))],
            },
            "publico": [_texto(x, f"publico[{i}]") for i, x in enumerate(_lista(c["publico"], "publico"))],
            "cierre": _texto(c["cierre"], "cierre"),
        }
    except (KeyError, TypeError, AttributeError) as e:
        raise ContenidoInvalido(f"falta el campo {e}") from e
    return out


def guardar(data_dir, nuevo):
    """Valida, sube la version y guarda. La version anterior queda como respaldo."""
    actual = cargar(data_dir)
    limpio = validar(nuevo)
    limpio["version"] = max(int(actual.get("version", 0)), limpio["version"]) + 1
    limpio["actualizado"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    ruta, prev = _rutas(data_dir)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(prev, "w", encoding="utf-8") as f:
        json.dump(actual, f, ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(dir=str(ruta.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(limpio, f, ensure_ascii=False, indent=2)
    os.replace(tmp, ruta)
    return limpio


def restaurar(data_dir):
    """Vuelve a la version anterior (deshacer el ultimo guardado)."""
    _, prev = _rutas(data_dir)
    anterior = _leer(prev)
    if not anterior:
        raise ContenidoInvalido("no hay una version anterior guardada")
    return guardar(data_dir, anterior)


_LINK = re.compile(r"\[([^\]\n]{1,200})\]\((https://[^\s)]{1,500})\)")
_BOLD = re.compile(r"\*\*([^*\n]{1,300})\*\*")


def formato(texto):
    """Texto seguro para la plantilla: escapa todo y solo permite **negrita** y enlaces https."""
    s = html.escape(texto or "", quote=True)
    s = _BOLD.sub(r"<strong>\1</strong>", s)
    s = _LINK.sub(r'<a href="\2" target="_blank" rel="noopener noreferrer">\1'
                  r'<span class="sr-only"> (se abre en otra pestaña)</span></a>', s)
    s = re.sub(r"(\d) %", r"\1&nbsp;%", s)
    return Markup(s)
