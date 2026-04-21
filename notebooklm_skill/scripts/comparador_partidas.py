"""
COMPARADOR DE PARTIDAS ARANCELARIAS
Confronta dos codigos arancelarios y emite un analisis paso a paso.
Usa Claude Haiku para el razonamiento juridico-arancelario.
"""
import os
import re


def comparar_partidas(query: str, codigo_a: str, desc_a: str,
                      codigo_b: str, desc_b: str) -> dict:
    """
    Compara dos codigos arancelarios para una consulta dada.

    Returns:
        {
          "ok": bool,
          "veredicto": "A" | "B" | "EMPATE",
          "codigo_correcto": str,
          "pasos": [{"titulo": str, "contenido": str}, ...],
          "referencias": [str, ...],
          "conclusion": str,
          "error": str | None
        }
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"ok": False, "error": "ANTHROPIC_API_KEY no configurada"}

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        prompt = f"""Eres un clasificador arancelario experto del Arancel de Aduanas de la Republica Dominicana (7ma Enmienda, Sistema Armonizado).

CONSULTA DEL USUARIO: {query}

CODIGO A (recomendado por Biblioteca-Consultor): {codigo_a}
DESCRIPCION OFICIAL A: {desc_a or "(no disponible)"}

CODIGO B (seleccionado por el usuario como alternativa): {codigo_b}
DESCRIPCION OFICIAL B: {desc_b or "(no disponible)"}

Realiza un analisis comparativo paso a paso y determina cual codigo es mas correcto para esta consulta. Sé imparcial: puede ser correcto el A, el B, o ambos validos.

Responde EXACTAMENTE en este formato (no agregues nada fuera de este formato):

PASO_1_TITULO: Identificacion de la mercancia
PASO_1: (analiza que tipo de producto es segun la consulta, sus caracteristicas principales)

PASO_2_TITULO: Analisis del Codigo A ({codigo_a})
PASO_2: (explica si este codigo corresponde o no a la mercancia, por que si o por que no, basado en la descripcion oficial)

PASO_3_TITULO: Analisis del Codigo B ({codigo_b})
PASO_3: (explica si este codigo corresponde o no a la mercancia, por que si o por que no, basado en la descripcion oficial)

PASO_4_TITULO: Comparacion y criterios de clasificacion
PASO_4: (aplica las Reglas Generales de Interpretacion del SA — indica cual RGI aplica y por que uno es mas especifico que el otro)

PASO_5_TITULO: Conclusion y recomendacion
PASO_5: (conclusion definitiva, codigo recomendado y razon principal)

VEREDICTO: A o B o EMPATE
REFERENCIAS: (lista separada por comas: ej. RGI 1, RGI 3, Nota Legal Capitulo XX, Nota Explicativa SA)
CONCLUSION_BREVE: (una sola oracion con el codigo correcto y razon principal)"""

        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}]
        )
        texto = msg.content[0].text.strip()

        pasos = []
        for i in range(1, 6):
            m_titulo = re.search(rf'PASO_{i}_TITULO:\s*(.+)', texto)
            m_cont   = re.search(rf'PASO_{i}:\s*(.+?)(?=PASO_{i+1}_TITULO:|VEREDICTO:|$)', texto, re.DOTALL)
            titulo   = m_titulo.group(1).strip() if m_titulo else f"Paso {i}"
            contenido = m_cont.group(1).strip()  if m_cont   else ""
            pasos.append({"titulo": titulo, "contenido": contenido})

        m_veredicto  = re.search(r'VEREDICTO:\s*(A|B|EMPATE)', texto, re.IGNORECASE)
        m_refs       = re.search(r'REFERENCIAS:\s*(.+)', texto)
        m_conclusion = re.search(r'CONCLUSION_BREVE:\s*(.+)', texto)

        veredicto      = (m_veredicto.group(1).upper()  if m_veredicto  else "B")
        referencias    = [r.strip() for r in m_refs.group(1).split(',')]  if m_refs  else []
        conclusion     = m_conclusion.group(1).strip()  if m_conclusion else ""
        codigo_correcto = codigo_a if veredicto == "A" else (codigo_b if veredicto == "B" else codigo_a)

        return {
            "ok": True,
            "veredicto": veredicto,
            "codigo_correcto": codigo_correcto,
            "pasos": pasos,
            "referencias": referencias,
            "conclusion": conclusion,
            "error": None
        }

    except ImportError:
        return {"ok": False, "error": "SDK anthropic no instalado"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}
