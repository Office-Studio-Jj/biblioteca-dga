"""Monto especifico del ISC (cigarrillos y alcoholes) segun la fecha, con su resolucion.

Fuente unica de los montos: notebooklm_skill/data/fuentes_nomenclatura/isc_montos_especificos.json
(tambien la usa scripts/build_isc_lookup.py). Nunca devuelve un monto fuera de su vigencia: si no
hay periodo cargado para la fecha, responde "monto por verificar" con el enlace a la DGII.
"""

import json
import os
from datetime import date, datetime, timedelta, timezone

_JSON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "notebooklm_skill", "data", "fuentes_nomenclatura", "isc_montos_especificos.json")
_RD = timezone(timedelta(hours=-4))  # Republica Dominicana, sin horario de verano
_datos = None


def _cargar():
    global _datos
    if _datos is None:
        with open(_JSON, encoding="utf-8") as f:
            _datos = json.load(f)
    return _datos


def hoy_rd():
    return datetime.now(_RD).date()


def _grupos_de(son, grupos):
    partida = son.replace(".", "")[:4]
    return [g for g, d in grupos.items()
            if son in d.get("codigos", []) or partida in d.get("partidas", [])]


def _ddmmaaaa(iso):
    return date.fromisoformat(iso).strftime("%d-%m-%Y")


def periodo_de(fecha):
    """Periodo de montos cuya vigencia incluye `fecha`, o None."""
    return next((p for p in _cargar()["periodos"]
                 if date.fromisoformat(p["vigente_desde"]) <= fecha <= date.fromisoformat(p["vigente_hasta"])),
                None)


def isc_especifico(son, fecha=None):
    """None si el SON no tiene monto especifico; si lo tiene, dict con estado, montos, texto y fuente.

    estado: "vigente" | "historico" | "por_verificar". `fecha` (date o "AAAA-MM-DD") es la
    fecha de referencia (Ley 168-21 Art. 82: aceptacion de la declaracion); por defecto, hoy en RD.
    """
    if not son:
        return None
    datos = _cargar()
    grupos = _grupos_de(son.strip(), datos["grupos"])
    if not grupos:
        return None
    if fecha is None:
        fecha = hoy_rd()
    elif isinstance(fecha, str):
        fecha = date.fromisoformat(fecha)

    periodo = periodo_de(fecha)
    if periodo is None:
        url = datos["_meta"]["por_verificar"]
        return {"estado": "por_verificar", "montos": [], "fuente": url,
                "texto": (f"Monto especifico por verificar: no hay resolucion cargada para el "
                          f"{fecha.strftime('%d-%m-%Y')}. Consultar la DGII: {url}")}

    estado = "historico" if date.fromisoformat(periodo["vigente_hasta"]) < hoy_rd() else "vigente"
    g = [datos["grupos"][k] for k in grupos]
    montos = [{"producto": d["producto"], "monto": periodo["montos"][k], "unidad": d["unidad"],
               "base_legal": d["base_legal"]} for k, d in zip(grupos, g)]
    detalle = " / ".join(f"RD${m['monto']} {m['unidad']}" for m in montos)
    vigencia = f"{_ddmmaaaa(periodo['vigente_desde'])} a {_ddmmaaaa(periodo['vigente_hasta'])}"
    etiqueta = "HISTORICO, no vigente: " if estado == "historico" else ""
    palabra = "vigencia" if estado == "historico" else "vigente"
    texto = (f"{etiqueta}{detalle} ({palabra} {vigencia}, Res. DGII {periodo['codigo_resolucion']}) "
             f"+ {g[0]['ad_valorem']}")
    return {"estado": estado, "montos": montos, "vigente_desde": periodo["vigente_desde"],
            "vigente_hasta": periodo["vigente_hasta"], "resolucion": periodo["resolucion"],
            "fuente": periodo["enlace"], "texto": texto}


def resumen_isc(son, isc_actual=None, fecha=None):
    """Version corta para listados: 'RD$65.02 por cajetilla de 20 + 20% (Res. ...)'."""
    r = isc_especifico(son, fecha)
    if not r:
        return isc_actual
    if r["estado"] == "por_verificar":
        return "monto especifico por verificar (DGII)"
    return r["texto"].split(" (")[0] + f" + ad valorem ({r['resolucion'].split(' (')[0]})"


def texto_isc(son, isc_actual=None, fecha=None):
    """Texto de ISC para mostrar: el monto especifico si el SON lo tiene; si no, isc_actual."""
    r = isc_especifico(son, fecha)
    return r["texto"] if r else isc_actual
