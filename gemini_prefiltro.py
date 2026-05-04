"""
GEMINI PRE-FILTRO DE SINONIMOS
================================
Traduce lenguaje comercial/coloquial → lenguaje arancelario SA.
Se ejecuta ANTES del orquestador_v2. No modifica el flujo posterior.

Regla de oro:
  - Gemini SOLO traduce. No clasifica. No asigna SON. No toca la DB.
  - Si Gemini falla o no esta disponible, devuelve texto_original sin cambio.
  - El patron R1-R7 sigue IDENTICO despues de esta capa.

Creado por Orden 10 del CEO — 4 mayo 2026
Base legal: Convenio SA (OMA) RGI 1, Decreto 755-22 Art. 64, Ley 168-21 Art. 75
"""

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.join(_HERE, "notebooklm_skill", "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

_SYSTEM = (
    "Eres un traductor de nomenclatura arancelaria del Sistema Armonizado (SA) de la OMA. "
    "Tu UNICA funcion es traducir el nombre comercial, marca o termino coloquial de un producto "
    "al lenguaje tecnico del SA. NO clasificas. NO asignas codigos SON. Solo traduces. "
    "Responde UNICAMENTE con el JSON solicitado, sin texto adicional, sin bloques de codigo."
)

_PROMPT_TPL = """Producto del usuario: "{consulta}"

Traduce al lenguaje tecnico del Sistema Armonizado (SA) de la OMA.

Responde SOLO con este JSON (sin bloques de codigo, sin comentarios):
{{
  "consulta_original": "{consulta}",
  "consulta_traducida": "[descripcion tecnica SA del producto]",
  "sinonimos": ["[sinonimo1]", "[sinonimo2]"],
  "identidad": "[que ES: su naturaleza tecnica en 1 frase]",
  "parentesco_sa": "[familia SA a la que pertenece]",
  "capitulo_probable": "[2 digitos, ej: 87]",
  "terminos_arancelarios": ["[termino SA 1]", "[termino SA 2]", "[termino SA 3]"]
}}"""


def traducir_consulta(texto_usuario: str, timeout: float = 8.0) -> dict:
    """
    Llama a Gemini para traducir texto_usuario al lenguaje del SA.
    Devuelve dict con consulta_traducida, sinonimos, terminos_arancelarios, etc.
    Si falla, devuelve dict con consulta_traducida = texto_usuario (sin cambio).
    """
    fallback = {
        "consulta_original":    texto_usuario,
        "consulta_traducida":   texto_usuario,
        "sinonimos":            [],
        "identidad":            "",
        "parentesco_sa":        "",
        "capitulo_probable":    "",
        "terminos_arancelarios": [],
    }

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or not texto_usuario or not texto_usuario.strip():
        return fallback

    try:
        from ask_gemini import _gemini_rest_call
    except Exception:
        return fallback

    prompt = _PROMPT_TPL.format(consulta=texto_usuario.replace('"', "'"))
    try:
        text, err = _gemini_rest_call(
            api_key,
            "gemini-2.5-flash",
            _SYSTEM,
            prompt,
            timeout=int(timeout),
        )
    except Exception:
        return fallback

    if err or not text:
        return fallback

    # Extraer JSON de la respuesta (puede venir con backticks o sin ellos)
    raw = text.strip()
    # Quitar bloques de codigo si los hay
    if "```" in raw:
        import re
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        raw = m.group(1) if m else raw.split("```")[1].lstrip("json").strip()

    try:
        resultado = json.loads(raw)
        # Asegurar que consulta_original siempre este presente
        resultado.setdefault("consulta_original", texto_usuario)
        resultado.setdefault("consulta_traducida", texto_usuario)
        resultado.setdefault("sinonimos", [])
        resultado.setdefault("terminos_arancelarios", [])
        return resultado
    except (json.JSONDecodeError, ValueError):
        return fallback


def enriquecer_consulta(texto_usuario: str, timeout: float = 8.0) -> str:
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
