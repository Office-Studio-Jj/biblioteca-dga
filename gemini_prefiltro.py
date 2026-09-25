"""
GEMINI PRE-FILTRO MERCEOLOGICO
================================
Gemini investiga solo la merceologia del producto (sub_agentes/merceologia_gemini.py)
y con ella enriquece la busqueda en la biblioteca-dga. Se ejecuta ANTES del orquestador_v2.

Regla de oro:
  - Gemini no clasifica: no emite capitulo, partida, SON, tasas ni leyes.
  - Si Gemini falla o no esta disponible, devuelve texto_original sin cambio.
  - El patron R1-R7 sigue IDENTICO despues de esta capa.

Creado por Orden 10 del CEO — 4 mayo 2026
Base legal: Convenio SA (OMA) RGI 1, Decreto 755-22 Art. 64, Ley 168-21 Art. 75
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def traducir_consulta(texto_usuario: str, timeout: float = 15.0) -> dict:
    """Ficha merceologica de Gemini en el formato que espera el orquestador.
    Si falla, devuelve consulta_traducida = texto_usuario (sin cambio)."""
    fallback = {
        "consulta_original":    texto_usuario,
        "consulta_traducida":   texto_usuario,
        "sinonimos":            [],
        "identidad":            "",
        "parentesco_sa":        "",
        "capitulo_probable":    "",
        "terminos_arancelarios": [],
    }

    if not texto_usuario or not texto_usuario.strip():
        return fallback
    from sub_agentes.merceologia_gemini import investigar_merceologia
    ficha = investigar_merceologia(texto_usuario, timeout=timeout)
    if not ficha:
        return fallback
    return {
        "consulta_original":     texto_usuario,
        "consulta_traducida":    ficha.get("nombre_tecnico") or texto_usuario,
        "sinonimos":             ficha.get("sinonimos", []),
        "identidad":             ficha.get("que_es", ""),
        "parentesco_sa":         "",
        "capitulo_probable":     "",
        "terminos_arancelarios": ficha.get("terminos_busqueda", []),
        "ficha_merceologica":    ficha,
    }


def enriquecer_consulta(texto_usuario: str, timeout: float = 15.0) -> str:
    """
    Funcion simplificada para orquestador_v2.
    Devuelve texto enriquecido = traduccion + terminos arancelarios.
    Si Gemini falla → devuelve texto_usuario original (el flujo no se rompe).

    Ejemplo:
      "hover board" → "vehiculo de autoequilibrio con motor electrico |
                        hover board | velocipedo | propulsion electrica"
    """
    try:
        t = traducir_consulta(texto_usuario, timeout=timeout)

        traducida   = (t.get("consulta_traducida") or "").strip()
        sinonimos   = [s for s in t.get("sinonimos", []) if s and s != texto_usuario]
        terminos    = [s for s in t.get("terminos_arancelarios", []) if s]

        # Si Gemini devolvio lo mismo que entrada, no agregar ruido
        if not traducida or traducida.lower() == texto_usuario.lower():
            return texto_usuario

        partes = [traducida]
        partes += sinonimos[:2]   # max 2 sinonimos para no contaminar FTS
        partes += terminos[:3]    # max 3 terminos arancelarios

        return " | ".join(p for p in partes if p)

    except Exception:
        # Nunca romper el flujo por culpa de Gemini
        return texto_usuario
