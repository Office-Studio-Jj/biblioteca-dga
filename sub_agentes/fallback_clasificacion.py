"""
fallback_clasificacion.py — Clasificador de respaldo arancelario RD.

Garantiza que el usuario NUNCA reciba un error vacío ni un código inventado
cuando el clasificador principal (Capa 3) falla.

Base legal:
- Decreto 755-22 Art. 67 (clasificación por analogía)
- RGI 4 (mercancía sin posición específica → partida más análoga)
- Ley 168-21 Art. 76 (derecho a consulta vinculante al aforador DGA)

Autor: AMGECO Automatización y Gestión SRL
"""

import os
import sys
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from capa1_sqlite.orquestador_capa3 import (
    buscar_clasificacion_sugerida,
    consultar_rgi,
)

# ---------------------------------------------------------------------------
# Mapeo Capítulo SA → Sección (7ma Enmienda, 21 Secciones, 96 Capítulos)
# ---------------------------------------------------------------------------
_CAPITULO_A_SECCION: dict[str, str] = {}

_RANGOS_SECCION = [
    ("I",     1,  5),
    ("II",    6, 14),
    ("III",  15, 15),
    ("IV",   16, 24),
    ("V",    25, 27),
    ("VI",   28, 38),
    ("VII",  39, 40),
    ("VIII", 41, 43),
    ("IX",   44, 46),
    ("X",    47, 49),
    ("XI",   50, 63),
    ("XII",  64, 67),
    ("XIII", 68, 70),
    ("XIV",  71, 71),
    ("XV",   72, 83),
    ("XVI",  84, 85),
    ("XVII", 86, 89),
    ("XVIII", 90, 92),
    ("XIX",  93, 93),
    ("XX",   94, 96),
    ("XXI",  97, 97),
]

for _sec, _ini, _fin in _RANGOS_SECCION:
    for _cap in range(_ini, _fin + 1):
        _CAPITULO_A_SECCION[str(_cap).zfill(2)] = _sec


def _extraer_capitulo(son: str) -> str:
    """Extrae los 2 primeros dígitos de un código SON (ej. '8543.70.00' → '85')."""
    digitos = re.sub(r"[^0-9]", "", son)
    return digitos[:2] if len(digitos) >= 2 else "00"


# ---------------------------------------------------------------------------
# Expansión de términos para búsqueda flexible
# ---------------------------------------------------------------------------

def _expandir_terminos(descripcion: str) -> list[str]:
    """
    Genera variantes de búsqueda a partir de la descripción del usuario.

    Retorna lista ordenada por probabilidad de acierto:
    1. Descripción original completa
    2. Palabras individuales (>= 3 caracteres)
    3. Bigramas consecutivos
    """
    descripcion = descripcion.strip()
    if not descripcion:
        return []

    variantes: list[str] = [descripcion]

    palabras = [
        p for p in re.split(r"\s+", descripcion.lower())
        if len(p) >= 3 and p.isalnum()
    ]

    # Palabras individuales
    for p in palabras:
        if p not in variantes:
            variantes.append(p)

    # Bigramas
    for i in range(len(palabras) - 1):
        bigrama = f"{palabras[i]} {palabras[i + 1]}"
        if bigrama not in variantes:
            variantes.append(bigrama)

    return variantes


# ---------------------------------------------------------------------------
# Clasificador de respaldo
# ---------------------------------------------------------------------------

def fallback_clasificar(descripcion: str, capitulo_candidato: str = None) -> dict:
    """
    Clasificador de respaldo cuando la Capa 3 falla.

    Busca candidatas en SQLite vía FTS5 con expansión de términos.
    NUNCA retorna vacío. NUNCA inventa un código.

    Args:
        descripcion: texto libre del usuario describiendo la mercancía.
        capitulo_candidato: capítulo SA de 2 dígitos (opcional, del pre-filtro Gemini).

    Returns:
        dict con claves: tipo, capitulo_probable, seccion_probable,
        candidatas, notas_relevantes, mensaje, recomendacion.
    """
    if not descripcion or not descripcion.strip():
        return _respuesta_manual(
            descripcion="(vacía)",
            motivo="No se proporcionó descripción de la mercancía.",
        )

    # Intentar búsqueda con cada variante hasta obtener resultados
    todas_candidatas: list[dict] = []
    terminos = _expandir_terminos(descripcion)

    for termino in terminos:
        resultados = buscar_clasificacion_sugerida(termino, limit=10)
        for r in resultados:
            son = r.get("son", "")
            # Evitar duplicados
            if not any(c["son"] == son for c in todas_candidatas):
                todas_candidatas.append(r)
        if len(todas_candidatas) >= 3:
            break

    # Si hay capítulo candidato, priorizar resultados de ese capítulo
    if capitulo_candidato and todas_candidatas:
        cap = capitulo_candidato.zfill(2)
        del_capitulo = [
            c for c in todas_candidatas
            if _extraer_capitulo(c.get("son", "")) == cap
        ]
        resto = [
            c for c in todas_candidatas
            if _extraer_capitulo(c.get("son", "")) != cap
        ]
        todas_candidatas = del_capitulo + resto

    # Tomar top 3
    top3 = todas_candidatas[:3]

    if not top3:
        return _respuesta_manual(
            descripcion=descripcion,
            motivo="No se encontraron coincidencias en el Arancel Nacional (7,616 SON).",
        )

    # Construir respuesta parcial
    candidatas_formato = []
    for c in top3:
        son = c.get("son", "")
        candidatas_formato.append({
            "son": son,
            "descripcion": c.get("descripcion", ""),
            "score": round(abs(c.get("rank", 0)), 4),
        })

    cap_principal = _extraer_capitulo(top3[0].get("son", ""))
    seccion = _CAPITULO_A_SECCION.get(cap_principal, "—")

    # Obtener RGI 4 (clasificación por analogía)
    rgi4_texto = consultar_rgi(4)

    return {
        "tipo": "PARCIAL",
        "capitulo_probable": cap_principal,
        "seccion_probable": seccion,
        "candidatas": candidatas_formato,
        "notas_relevantes": (
            f"RGI 4: {rgi4_texto}\n"
            f"Decreto 755-22 Art. 67: clasificación por analogía funcional."
        ),
        "mensaje": (
            f"El clasificador principal no pudo resolver la consulta. "
            f"Se encontraron {len(candidatas_formato)} candidata(s) por similitud textual "
            f"en el Capítulo {cap_principal} (Sección {seccion}). "
            f"Estas sugerencias NO son vinculantes."
        ),
        "recomendacion": (
            "1. Verificar en https://aduanas.gob.do (Arancel en línea)\n"
            "2. Consultar aforador DGA (Ley 168-21 Art. 76)\n"
            "3. Solicitar clasificación vinculante (Decreto 755-22 Art. 67)"
        ),
    }


def _respuesta_manual(descripcion: str, motivo: str) -> dict:
    """Genera respuesta tipo MANUAL cuando no hay resultados posibles."""
    return {
        "tipo": "MANUAL",
        "capitulo_probable": "—",
        "seccion_probable": "—",
        "candidatas": [],
        "notas_relevantes": consultar_rgi(4),
        "mensaje": (
            f"{motivo} Se requiere clasificación manual. "
            f"Proporcione: nombre comercial, función, material constitutivo y uso."
        ),
        "recomendacion": (
            "1. Verificar en https://aduanas.gob.do (Arancel en línea)\n"
            "2. Consultar aforador DGA (Ley 168-21 Art. 76)\n"
            "3. Solicitar clasificación vinculante (Decreto 755-22 Art. 67)"
        ),
    }
