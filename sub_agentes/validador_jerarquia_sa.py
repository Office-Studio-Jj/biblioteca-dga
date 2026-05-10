"""
VALIDADOR JERARQUICO SA — Gate post-clasificacion
===================================================
Garantiza que toda clasificacion arancelaria respeta la jerarquia
del Sistema Armonizado (7ma Enmienda, Decreto 36-22):

  Seccion (I-XXI)
    Capitulo (2 dig)
      Partida (4 dig)
        Subpartida SA (6 dig)
          SON Nacional RD (8 dig)

Reglas que valida:
  1. El codigo SON existe en el Arancel (arancel_cache.json / SQLite)
  2. Dentro de la subpartida, se verificaron TODAS las hermanas
     especificas antes de caer en "Las demas"
  3. La descripcion oficial de la SON coincide con el producto
  4. Si hay una SON mas especifica que aplica, la propone como correccion

Base legal: RGI 1, RGI 6 — Ley 168-21, Decreto 755-22 Art. 63
"""
import json
import os
import re
from typing import Optional, Dict, Any, List, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_DATA = os.path.join(_ROOT, "notebooklm_skill", "data")
_CACHE_PATH = os.path.join(_DATA, "fuentes_nomenclatura", "arancel_cache.json")

import sys
if os.path.join(_ROOT, "notebooklm_skill", "scripts") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "notebooklm_skill", "scripts"))

_MAPA_RGI: dict = {}
try:
    from pipeline_3_capas import _MAPA_PARTIDAS_RGI
    _MAPA_RGI = _MAPA_PARTIDAS_RGI
except Exception:
    pass

_DEMAS_RE = re.compile(r'\blos?\s+dem[aá]s\b|\blas?\s+dem[aá]s\b', re.IGNORECASE)
_STOPWORDS = {
    "para", "como", "cual", "este", "esta", "donde", "tiene", "tipo",
    "generica", "generico", "modelo", "marca", "uso", "nuevo", "nueva",
    "celular", "profesional", "industrial", "comercial", "domestico",
}

_cache_codigos: dict = {}


def _cargar_cache() -> dict:
    global _cache_codigos
    if _cache_codigos:
        return _cache_codigos
    try:
        with open(_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        _cache_codigos = data.get("codigos", data)
    except Exception:
        _cache_codigos = {}
    return _cache_codigos


def _palabras_clave(texto: str) -> List[str]:
    raw = re.findall(r'\b[a-záéíóúüñ]{4,}\b', texto.lower())
    return [w for w in raw if w not in _STOPWORDS]


def _es_las_demas(descripcion: str) -> bool:
    return bool(_DEMAS_RE.search(descripcion))


def obtener_hermanas(son: str) -> List[Tuple[str, str]]:
    """Retorna todas las SON hermanas (misma subpartida SA de 6 digitos)."""
    codigos = _cargar_cache()
    if not son or len(son) < 7:
        return []
    prefijo_6 = son[:7]  # XXXX.XX
    return sorted([
        (cod, str(desc))
        for cod, desc in codigos.items()
        if cod.startswith(prefijo_6)
    ])


def obtener_hermanas_partida(son: str) -> List[Tuple[str, str]]:
    """Retorna todas las SON de la misma partida (4 digitos)."""
    codigos = _cargar_cache()
    if not son or len(son) < 4:
        return []
    prefijo_4 = son[:4]
    return sorted([
        (cod, str(desc))
        for cod, desc in codigos.items()
        if cod.startswith(prefijo_4)
    ])


def validar_jerarquia(consulta: str, son_propuesto: str) -> Dict[str, Any]:
    """
    Valida que el SON propuesto respeta la jerarquia SA.

    Procedimiento:
      1. Verificar existencia del codigo
      2. Obtener TODAS las hermanas de la subpartida
      3. Comparar descripcion de cada hermana contra la consulta
      4. Si el propuesto es "Las demas" pero hay hermana especifica
         que matchea -> proponer correccion
      5. Si el propuesto es especifico -> confirmar coherencia

    Returns:
        {
          "valido": bool,
          "son_propuesto": str,
          "son_corregido": str | None,
          "razon": str,
          "hermanas_evaluadas": int,
          "jerarquia_respetada": bool,
          "nivel": "especifica" | "las_demas" | "unica" | "inexistente"
        }
    """
    codigos = _cargar_cache()
    resultado = {
        "valido": False,
        "son_propuesto": son_propuesto,
        "son_corregido": None,
        "razon": "",
        "hermanas_evaluadas": 0,
        "jerarquia_respetada": False,
        "nivel": "inexistente",
    }

    if not son_propuesto:
        resultado["razon"] = "sin codigo propuesto"
        return resultado

    # 1. Existencia
    desc_propuesto = codigos.get(son_propuesto, "")
    if not desc_propuesto:
        resultado["razon"] = f"codigo {son_propuesto} no existe en el Arancel RD"
        return resultado

    desc_propuesto_str = str(desc_propuesto).lower()

    # 2. Obtener hermanas de la subpartida SA (6 digitos)
    hermanas = obtener_hermanas(son_propuesto)
    resultado["hermanas_evaluadas"] = len(hermanas)

    if len(hermanas) <= 1:
        resultado["valido"] = True
        resultado["jerarquia_respetada"] = True
        resultado["nivel"] = "unica"
        resultado["razon"] = "codigo unico en su subpartida — no hay alternativas"
        return resultado

    # 3. Evaluar cada hermana contra la consulta
    palabras = _palabras_clave(consulta)
    propuesto_es_demas = _es_las_demas(desc_propuesto_str)

    scores = []
    for cod, desc in hermanas:
        desc_lower = str(desc).lower()
        es_demas = _es_las_demas(desc_lower)
        hits = sum(1 for p in palabras if p in desc_lower)
        scores.append({
            "cod": cod,
            "desc": desc[:120],
            "hits": hits,
            "es_demas": es_demas,
            "es_propuesto": cod == son_propuesto,
        })

    # Ordenar: especificas primero (mayor score), "Las demas" al final
    especificas = [s for s in scores if not s["es_demas"] and s["hits"] > 0]
    especificas.sort(key=lambda x: x["hits"], reverse=True)

    # 4. Decision jerarquica
    if propuesto_es_demas:
        if especificas:
            mejor = especificas[0]
            resultado["valido"] = False
            resultado["son_corregido"] = mejor["cod"]
            resultado["jerarquia_respetada"] = False
            resultado["nivel"] = "las_demas"
            resultado["razon"] = (
                f"Propuesto {son_propuesto} es 'Las demas' pero existe "
                f"hermana especifica {mejor['cod']} ({mejor['desc'][:80]}) "
                f"con {mejor['hits']} coincidencias. Jerarquia exige evaluar "
                f"especificas antes de residual."
            )
            resultado["alternativas"] = [
                {"cod": s["cod"], "desc": s["desc"][:80], "score": s["hits"]}
                for s in especificas[:5]
            ]
        else:
            resultado["valido"] = True
            resultado["jerarquia_respetada"] = True
            resultado["nivel"] = "las_demas"
            resultado["razon"] = (
                f"Propuesto {son_propuesto} es 'Las demas' — ninguna hermana "
                f"especifica coincide con la consulta. Jerarquia respetada."
            )
    else:
        resultado["valido"] = True
        resultado["jerarquia_respetada"] = True
        resultado["nivel"] = "especifica"
        propuesto_score = next(
            (s["hits"] for s in scores if s["es_propuesto"]), 0
        )
        resultado["razon"] = (
            f"Propuesto {son_propuesto} es especifica "
            f"(score={propuesto_score}). Jerarquia respetada."
        )
        if especificas and especificas[0]["cod"] != son_propuesto:
            mejor = especificas[0]
            if mejor["hits"] > propuesto_score:
                resultado["sugerencia"] = (
                    f"Hermana {mejor['cod']} ({mejor['desc'][:80]}) tiene "
                    f"mayor coincidencia (score={mejor['hits']} vs {propuesto_score}). "
                    f"Verificar si aplica mejor."
                )

    return resultado


def _enriquecer_con_mapa_rgi(consulta: str, son: str) -> Dict[str, Any]:
    """Busca en _MAPA_PARTIDAS_RGI si la partida del SON tiene reglas
    definidas (notas legales, exclusiones, criterio de subpartida).
    Permite validar que el codigo no viola una exclusion conocida."""
    if not _MAPA_RGI or not son or len(son) < 4:
        return {}
    partida = son[:4]
    info = _MAPA_RGI.get(partida)
    if not info:
        return {}
    consulta_l = consulta.lower()
    trigger_match = any(t in consulta_l for t in info.get("trigger", []))
    exclusiones = info.get("exclusiones_partida", [])
    excluido = False
    for excl in exclusiones:
        excl_partida = re.search(r'(\d{4})', excl)
        if excl_partida and son.startswith(excl_partida.group(1)):
            excluido = True
            break
    return {
        "partida_en_mapa": partida,
        "rgi_aplicable": info.get("rgi", ""),
        "notas_legales": info.get("notas_legales", []),
        "exclusiones": exclusiones,
        "criterio_subpartida": info.get("criterio_subpartida", ""),
        "trigger_match": trigger_match,
        "excluido_por_mapa": excluido,
    }


def validar_y_corregir(consulta: str, son_propuesto: str) -> Tuple[str, Dict[str, Any]]:
    """
    Valida jerarquia y retorna (son_final, informe).
    Si la jerarquia NO se respeta y hay correccion, aplica la correccion.
    Si se respeta, retorna el propuesto sin cambio.
    Enriquece con notas legales del _MAPA_PARTIDAS_RGI si existen.
    """
    informe = validar_jerarquia(consulta, son_propuesto)
    mapa_info = _enriquecer_con_mapa_rgi(consulta, son_propuesto)
    if mapa_info:
        informe["mapa_rgi"] = mapa_info

    if informe["valido"]:
        return son_propuesto, informe

    corregido = informe.get("son_corregido")
    if corregido:
        print(
            f"[JERARQUIA-SA] Correccion: {son_propuesto} -> {corregido} "
            f"({informe['razon'][:100]})"
        )
        return corregido, informe

    return son_propuesto, informe
