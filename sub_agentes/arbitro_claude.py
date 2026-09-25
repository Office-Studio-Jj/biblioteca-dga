"""Claude como árbitro legal de clasificación (Arquitectura Opción B, CEO 03-MAY-2026)."""

import json
import os
import re

MODELO = os.environ.get("ARBITRO_CLAUDE_MODEL", "claude-opus-5")

_client = None


def _cliente():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(timeout=45.0, max_retries=1)
    return _client


def llamar_claude(system, prompt, max_tokens=4000, effort="medium", timeout=45.0):
    """Texto de la respuesta de Claude, o None si no hay clave, hay error o hubo rechazo."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[ARBITRO] ANTHROPIC_API_KEY no configurada")
        return None
    try:
        resp = _cliente().with_options(timeout=timeout).beta.messages.create(
            model=MODELO,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": effort},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except Exception as e:
        print(f"[ARBITRO] Error Claude: {type(e).__name__}: {e}")
        return None
    if resp.stop_reason == "refusal":
        print("[ARBITRO] Claude declinó la solicitud")
        return None
    return "".join(b.text for b in resp.content if b.type == "text") or None


def llamar_claude_json(system, prompt, max_tokens=4000, effort="medium"):
    texto = llamar_claude(system, prompt, max_tokens=max_tokens, effort=effort)
    if not texto:
        return None
    m = re.search(r"\{[\s\S]*\}", texto)
    try:
        return json.loads(m.group(0)) if m else None
    except ValueError:
        return None


_SYSTEM_CAPITULO = (
    "Eres el árbitro legal de clasificación arancelaria de la República Dominicana "
    "(Arancel 7ma Enmienda, Decreto 36-22; RGI según Decreto 755-22). Eliges el capítulo "
    "aplicando la RGI 1: textos de las partidas y Notas de Sección y de Capítulo. "
    "La ficha merceológica describe el producto; no es una clasificación. Responde solo con JSON."
)


def elegir_capitulo(consulta, ficha, candidatos):
    """Capítulo entre los candidatos de la biblioteca-dga, con fundamento. None si no decide."""
    if not candidatos:
        return None
    lista = "\n".join(
        f"- Cap. {c['capitulo']} (coincidencias: {c['votos']}): " + " | ".join(c["ejemplos"])
        for c in candidatos)
    ficha_txt = json.dumps({k: v for k, v in ficha.items() if k != "fuente"}, ensure_ascii=False)
    prompt = (
        f"Consulta: {consulta}\n\nFicha merceológica:\n{ficha_txt}\n\n"
        f"Capítulos candidatos encontrados en la biblioteca-dga (arancel_rd.db):\n{lista}\n\n"
        "Si la RGI 1 o una Nota Legal excluye a todos los candidatos, indícalo con "
        "\"capitulo_fuera_de_lista\" y el capítulo correcto; si no, elige uno de la lista.\n"
        'JSON: {"capitulo": "NN", "capitulo_fuera_de_lista": false, '
        '"alternativos": ["NN"], "fundamento": "RGI y nota legal aplicada, 1-2 frases"}'
    )
    r = llamar_claude_json(_SYSTEM_CAPITULO, prompt, max_tokens=2000, effort="medium")
    if not r:
        return None
    cap = str(r.get("capitulo", "")).strip().zfill(2)
    if not re.fullmatch(r"\d{2}", cap):
        return None
    validos = {c["capitulo"] for c in candidatos}
    if cap not in validos and not r.get("capitulo_fuera_de_lista"):
        return None
    r["capitulo"] = cap
    return r
