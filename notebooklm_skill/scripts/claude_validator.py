"""
CLAUDE VALIDATOR — Segunda opinion de clasificacion arancelaria.
Se activa cuando Gemini retorna un codigo sospechoso o ambiguo.
Usa claude-haiku-4-5 (rapido, economico ~$0.001/consulta).
"""
import os
import re

def validar_clasificacion(query: str, codigo_gemini: str, desc_cache: str) -> dict:
    """
    Valida si el codigo retornado por Gemini es correcto para la consulta.

    Returns:
        {
          "valido": bool,
          "codigo_confirmado": str,
          "confianza": "ALTA"|"MEDIA"|"BAJA",
          "razon": str
        }
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"valido": None, "razon": "ANTHROPIC_API_KEY no configurada"}

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        prompt = f"""Eres un experto en clasificacion arancelaria del Arancel de Aduanas de la Republica Dominicana (7ma Enmienda, Sistema Armonizado).

CONSULTA DEL USUARIO: {query}

CODIGO PROPUESTO: {codigo_gemini}
DESCRIPCION OFICIAL DEL CODIGO: {desc_cache or "(no disponible en cache)"}

Determina si este codigo es correcto para la consulta.

Responde SOLO en este formato exacto:
VALIDO: SI o NO
CONFIANZA: ALTA, MEDIA o BAJA
RAZON: (una sola linea explicando por que es correcto o incorrecto)"""

        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}]
        )
        texto = msg.content[0].text.strip()

        valido = "VALIDO: SI" in texto.upper()
        m_conf = re.search(r'CONFIANZA:\s*(ALTA|MEDIA|BAJA)', texto, re.IGNORECASE)
        m_razon = re.search(r'RAZON:\s*(.+)', texto, re.IGNORECASE)

        return {
            "valido": valido,
            "codigo_confirmado": codigo_gemini if valido else None,
            "confianza": m_conf.group(1).upper() if m_conf else "MEDIA",
            "razon": m_razon.group(1).strip() if m_razon else texto[:100]
        }
    except ImportError:
        return {"valido": None, "razon": "SDK anthropic no instalado"}
    except Exception as e:
        return {"valido": None, "razon": str(e)[:100]}


def esta_disponible() -> bool:
    """Verifica si Claude validator esta listo para usar."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa
        return True
    except ImportError:
        return False
