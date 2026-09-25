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


# Solo instituciones oficiales de la República Dominicana (subdominios incluidos).
DOMINIOS_OFICIALES_RD = [
    "aduanas.gob.do", "vucerd.gob.do", "dgii.gov.do", "hacienda.gob.do", "consultoria.gov.do",
    "camaradediputados.gob.do", "senadord.gob.do", "tc.gob.do", "poderjudicial.gob.do",
    "msp.gob.do", "agricultura.gob.do", "indotel.gob.do", "micm.gob.do", "cnzfe.gob.do",
    "proindustria.gob.do", "ambiente.gob.do", "indocal.gob.do", "prodominicana.gob.do", "mirex.gob.do",
]

INSTRUCCION_WEB = (
    "\n\nBÚSQUEDA WEB: úsala solo si la biblioteca-dga incluida no contiene el dato que necesitas. "
    "Solo tienes acceso a sitios oficiales de instituciones dominicanas. Lo encontrado en la web "
    "complementa, nunca contradice, a la biblioteca-dga; cita la URL de cada dato obtenido así."
)


def _herramientas_web():
    return [
        {"type": "web_search_20260209", "name": "web_search", "max_uses": 2,
         "allowed_domains": DOMINIOS_OFICIALES_RD},
        {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 2,
         "allowed_domains": DOMINIOS_OFICIALES_RD},
    ]


def llamar_claude(system, prompt, max_tokens=4000, effort="medium", timeout=45.0, web=False):
    """Texto de la respuesta de Claude, o None si no hay clave, hay error o hubo rechazo.

    web=True habilita búsqueda/lectura web solo en DOMINIOS_OFICIALES_RD, como complemento.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[ARBITRO] ANTHROPIC_API_KEY no configurada")
        return None
    extra = {"tools": _herramientas_web()} if web else {}
    mensajes = [{"role": "user", "content": prompt}]
    try:
        for _ in range(3):
            resp = _cliente().with_options(timeout=timeout).beta.messages.create(
                model=MODELO,
                max_tokens=max_tokens,
                system=system + (INSTRUCCION_WEB if web else ""),
                messages=mensajes,
                output_config={"effort": effort},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                **extra,
            )
            if resp.stop_reason != "pause_turn":
                break
            # El servidor pausó la búsqueda web: reenviar el turno para que continúe.
            mensajes = [mensajes[0], {"role": "assistant", "content": resp.content}]
    except Exception as e:
        print(f"[ARBITRO] Error Claude: {type(e).__name__}: {e}")
        return None
    if resp.stop_reason == "refusal":
        print("[ARBITRO] Claude declinó la solicitud")
        return None
    usos_web = sum(1 for b in resp.content if b.type == "server_tool_use")
    if usos_web:
        print(f"[ARBITRO] Claude consultó web oficial ({usos_web} uso(s))")
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


SYSTEM_LEGAL = (
    "Eres el árbitro legal de clasificación arancelaria de la República Dominicana. Clasificas "
    "solo con el Arancel de Aduanas 7ma Enmienda (Decreto 36-22), la Ley 168-21 y las RGI "
    "(Decreto 755-22), usando el contexto de la biblioteca-dga que se te entrega. Orden obligatorio: "
    "RGI 1 (texto de las partidas y Notas de Sección y de Capítulo, incluidas sus exclusiones), luego "
    "RGI 2 a 5 solo si la RGI 1 no resuelve, y RGI 6 para subpartidas; la apertura nacional debe tener "
    "exactamente 8 dígitos (XXXX.XX.XX) y existir en la biblioteca. Las Notas Explicativas del SA son "
    "auxiliares, sin fuerza vinculante en RD (Art. 4, Ley 146-00). La ficha merceológica describe el "
    "producto; no es una clasificación. Si un dato no está en el contexto, dilo: no lo supongas."
)


def elegir_capitulo(consulta, ficha, candidatos):
    """Capítulo (y partida) entre los candidatos de la biblioteca-dga, con fundamento. None si no decide."""
    if not candidatos:
        return None
    from sub_agentes.contexto_legal import construir, partidas_por_texto
    from sub_agentes.merceologia_gemini import terminos_de_ficha
    caps = [c["capitulo"] for c in candidatos[:4]]
    destacadas = [p for p, _ in partidas_por_texto(terminos_de_ficha(ficha, consulta))]
    ficha_txt = json.dumps({k: v for k, v in ficha.items() if k != "fuente"}, ensure_ascii=False)
    prompt = (
        f"Consulta: {consulta}\n\nFicha merceológica (informativa):\n{ficha_txt or '(no disponible)'}\n\n"
        f"Capítulos candidatos de la biblioteca-dga: {', '.join(caps)}\n\n"
        f"{construir(caps, destacadas)}\n\n"
        "Elige capítulo y partida aplicando las RGI en orden. Si las Notas excluyen a todos los "
        "candidatos, usa \"capitulo_fuera_de_lista\": true e indica el capítulo correcto.\n"
        'JSON: {"capitulo": "NN", "partida": "NN.NN", "capitulo_fuera_de_lista": false, '
        '"alternativos": ["NN"], "fundamento": "RGI y Nota aplicada, con su número, 1-3 frases"}'
    )
    r = llamar_claude_json(SYSTEM_LEGAL, prompt, max_tokens=3000, effort="medium")
    if not r:
        return None
    cap = str(r.get("capitulo", "")).strip().zfill(2)
    if not re.fullmatch(r"\d{2}", cap):
        return None
    validos = {c["capitulo"] for c in candidatos}
    if cap not in validos and not r.get("capitulo_fuera_de_lista"):
        return None
    r["capitulo"] = cap
    partida = str(r.get("partida", "")).strip()
    if not (re.fullmatch(r"\d{2}\.\d{2}", partida) and partida.startswith(cap)
            and _partida_en_biblioteca(partida)):
        r["partida"] = ""
    return r


def _partida_en_biblioteca(partida):
    from sub_agentes.contexto_legal import partidas
    from sub_agentes.merceologia_gemini import _DB
    if partida in partidas():
        return True
    import sqlite3
    try:
        con = sqlite3.connect(_DB)
        fila = con.execute("SELECT 1 FROM codigos WHERE REPLACE(son,'.','') LIKE ? LIMIT 1",
                           (partida.replace(".", "") + "%",)).fetchone()
        con.close()
        return fila is not None
    except sqlite3.Error:
        return False
