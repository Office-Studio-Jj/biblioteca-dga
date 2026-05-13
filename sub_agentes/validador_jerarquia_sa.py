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

Procedimiento normativo (CEO 12-May-2026):
  1. LEER Notas Legales de Seccion y Capitulo (RGI 1)
  2. RECORRER todas las hermanas de la subpartida
  3. DESCARTAR hermanas cuya descripcion NO describe el producto
  4. SELECCIONAR la hermana mas especifica que SI aplica
  5. CONSTRUIR razonamiento legal citando RGI + Notas

Base legal: RGI 1-6 — Ley 168-21, Decreto 755-22 Art. 63
"""
import json
import os
import re
from typing import Optional, Dict, Any, List, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_DATA = os.path.join(_ROOT, "notebooklm_skill", "data")
_CACHE_PATH = os.path.join(_DATA, "fuentes_nomenclatura", "arancel_cache.json")
_NOTAS_CACHE_PATH = os.path.join(_DATA, "fuentes_nomenclatura", "notas_capitulos_cache.json")

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

# ── BLACKLIST GLOBAL: SON que NUNCA deben asignarse sin match semantico perfecto ──
_BLACKLIST_COHERENCIA = {
    "8501.10.10": {"juguete", "juguetes", "toy", "toys"},
    "8528.59.90": {"monitor", "pantalla", "display"},
    "8517.11.00": {"telefono", "telefonos", "linea fija"},
}

_EXCLUSION_SEMANTICA = {
    "8501.10.10": {"dron", "drone", "agricola", "industrial", "vehiculo",
                   "automotriz", "bicicleta", "scooter", "bomba", "compresor",
                   "ventilador", "herramienta", "robot", "aeronave", "motor brushless"},
}

# ── Cache interno ──
_cache_codigos: dict = {}
_cache_notas: dict = {}


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


def _cargar_notas_cache() -> dict:
    global _cache_notas
    if _cache_notas:
        return _cache_notas
    try:
        with open(_NOTAS_CACHE_PATH, "r", encoding="utf-8") as f:
            _cache_notas = json.load(f)
    except Exception:
        _cache_notas = {}
    return _cache_notas


def _obtener_notas_capitulo(capitulo: str) -> Dict[str, Any]:
    """Lee TODAS las Notas del capitulo + seccion desde el cache v3.0.

    Tipos de notas (Arancel 7ma Enmienda RD):
      - Notas Legales de Seccion (RGI 1: misma jerarquia que notas de Capitulo)
      - Notas Legales de Capitulo (determinan clasificacion, RGI 1)
      - Notas de Subpartida (determinan clasificacion dentro de partida, RGI 6)
      - Notas Adicionales (requisitos RD: permisos, certificados, prohibiciones)
      - Notas Explicativas SA (OMA — auxiliares, sin fuerza legal vinculante)
    """
    cache = _cargar_notas_cache()
    cap = str(capitulo).zfill(2)
    caps = cache.get("capitulos", {})
    secs = cache.get("secciones", {})
    info_cap = caps.get(cap, {})

    # Preferir notas completas si existen, sino las resumidas
    notas_cap = (info_cap.get("notas_legales_completas") or
                 info_cap.get("notas_legales", []))

    # Buscar seccion padre
    info_sec = {}
    for sec_id, sec_data in secs.items():
        rango = sec_data.get("capitulos", "")
        if "-" in str(rango):
            parts = str(rango).split("-")
            try:
                if int(parts[0]) <= int(cap) <= int(parts[1]):
                    info_sec = dict(sec_data)
                    info_sec["seccion_id"] = sec_id
                    break
            except ValueError:
                continue
        elif str(rango) == cap:
            info_sec = dict(sec_data)
            info_sec["seccion_id"] = sec_id
            break

    notas_sec = (info_sec.get("notas_legales_completas") or
                 info_sec.get("notas_legales", []))

    return {
        "capitulo": cap,
        "titulo_cap": info_cap.get("titulo", ""),
        "notas_legales_cap": notas_cap,
        "notas_subpartida_cap": info_cap.get("notas_subpartida", []),
        "notas_adicionales_cap": info_cap.get("notas_adicionales", []),
        "notas_explicativas": info_cap.get("notas_explicativas_clave", []),
        "seccion": info_sec.get("seccion_id", ""),
        "titulo_sec": info_sec.get("titulo", ""),
        "notas_legales_sec": notas_sec,
        "exclusiones_sec": info_sec.get("exclusiones", []),
        "rgi_completas": cache.get("rgi_completas", ""),
    }


def _palabras_clave(texto: str) -> List[str]:
    raw = re.findall(r'\b[a-záéíóúüñ]{4,}\b', texto.lower())
    return [w for w in raw if w not in _STOPWORDS]


def _es_las_demas(descripcion: str) -> bool:
    return bool(_DEMAS_RE.search(descripcion))


def _es_subpartida_residual(descripcion: str) -> bool:
    """Detecta SON residuales: 'Los/Las demas' O subpartidas de segundo nivel
    (prefijo '- -' o '--' en el Arancel = apertura dentro de 'Las demas')."""
    if _es_las_demas(descripcion):
        return True
    desc_strip = descripcion.strip()
    if desc_strip.startswith("- -") or desc_strip.startswith("--"):
        return True
    return False


# Palabras que aparecen en el titulo de la partida y por tanto no diferencian
# entre subpartidas. No cuentan como "match especifico".
_PALABRAS_PARTIDA_GENERICAS = {
    "motores", "motor", "electrico", "electricos", "electrica",
    "maquinas", "aparatos", "partes", "accesorios",
}


def _score_coherencia_semantica(consulta: str, son: str, desc_son: str) -> int:
    """Score 0-100. Excluye palabras que pertenecen al titulo de la partida
    padre (ej: 'motores' no diferencia entre subpartidas de 8501)."""
    consulta_l = consulta.lower()
    desc_l = desc_son.lower()
    palabras_consulta = set(re.findall(r'\b[a-záéíóúüñ]{3,}\b', consulta_l))
    palabras_desc = set(re.findall(r'\b[a-záéíóúüñ]{3,}\b', desc_l))
    if not palabras_desc:
        return 50
    # Excluir stopwords Y palabras genericas de la partida
    excluir = _STOPWORDS | _PALABRAS_PARTIDA_GENERICAS
    interseccion = (palabras_consulta & palabras_desc) - excluir
    if not interseccion:
        return 0
    return int(100 * len(interseccion) / max(len(palabras_desc - excluir), 1))


def _verificar_blacklist(consulta: str, son: str) -> Optional[str]:
    if son not in _BLACKLIST_COHERENCIA:
        return None
    consulta_l = consulta.lower()
    keywords_req = _BLACKLIST_COHERENCIA[son]
    if any(kw in consulta_l for kw in keywords_req):
        return None
    exclusiones = _EXCLUSION_SEMANTICA.get(son, set())
    if any(ex in consulta_l for ex in exclusiones):
        return (f"SON {son} BLOQUEADO: producto contiene terminos de exclusion "
                f"semantica. Descripcion oficial NO coincide con el producto.")
    return (f"SON {son} en blacklist de coherencia: consulta no contiene "
            f"ninguna keyword requerida {keywords_req}. "
            f"Descripcion oficial NO coincide con el producto.")


def obtener_hermanas(son: str) -> List[Tuple[str, str]]:
    codigos = _cargar_cache()
    if not son or len(son) < 7:
        return []
    prefijo_6 = son[:7]
    return sorted([
        (cod, str(desc))
        for cod, desc in codigos.items()
        if cod.startswith(prefijo_6)
    ])


def obtener_hermanas_partida(son: str) -> List[Tuple[str, str]]:
    codigos = _cargar_cache()
    if not son or len(son) < 4:
        return []
    prefijo_4 = son[:4]
    return sorted([
        (cod, str(desc))
        for cod, desc in codigos.items()
        if cod.startswith(prefijo_4)
    ])


def _analizar_hermanas_con_notas(
    consulta: str, son_rechazado: str, notas: Dict[str, Any]
) -> Tuple[Optional[str], str]:
    """
    Analiza TODAS las hermanas de la subpartida aplicando RGI 1 y RGI 6:

    RGI 1: La clasificacion esta determinada por los textos de las partidas
           y las Notas de Seccion o de Capitulo.
    RGI 6: La clasificacion en las subpartidas de una misma partida esta
           determinada por los textos de estas subpartidas y las Notas de
           subpartida, asi como por las RGI 1-5 aplicadas mutatis mutandis.

    Procedimiento:
      1. Listar TODAS las hermanas con su descripcion oficial
      2. DESCARTAR las que claramente NO aplican (su descripcion excluye el producto)
      3. Entre las restantes, preferir la MAS ESPECIFICA
      4. Si ninguna especifica aplica, usar la residual ("Los/Las demas")
      5. Construir razonamiento legal

    Retorna: (son_elegido, razonamiento_legal)
    """
    hermanas = obtener_hermanas(son_rechazado)
    if len(hermanas) <= 1:
        return None, "subpartida con un solo codigo"

    consulta_l = consulta.lower()
    codigos = _cargar_cache()

    # Clasificar cada hermana
    candidatas_especificas = []  # SON cuya descripcion describe algo concreto
    candidatas_residuales = []   # SON con "Los/Las demas"
    descartadas = []             # SON cuya descripcion NO aplica al producto

    for cod, desc in hermanas:
        if cod == son_rechazado:
            descartadas.append((cod, desc, "rechazado por blacklist/coherencia"))
            continue

        # No proponer otra SON que tambien este en blacklist
        bl = _verificar_blacklist(consulta, cod)
        if bl:
            descartadas.append((cod, desc, bl))
            continue

        desc_l = desc.lower()
        es_residual = _es_subpartida_residual(desc)

        if es_residual:
            candidatas_residuales.append((cod, desc))
        else:
            # Evaluar si la descripcion especifica aplica al producto
            score = _score_coherencia_semantica(consulta, cod, desc_l)
            candidatas_especificas.append((cod, desc, score))

    # Construir razonamiento legal con TODAS las notas aplicables
    cap = son_rechazado[:2] if len(son_rechazado) >= 2 else ""
    partida = son_rechazado[:4] if len(son_rechazado) >= 4 else ""
    notas_str = ""

    # Buscar notas relevantes a la partida en notas de capitulo
    for n in notas.get("notas_legales_cap", []):
        if partida in n or son_rechazado[:7] in n:
            notas_str += f" Nota Legal Cap.{cap}: {n[:150]}."
            break

    # Buscar notas de subpartida relevantes (RGI 6)
    for n in notas.get("notas_subpartida_cap", []):
        if partida in n or son_rechazado[:7] in n:
            notas_str += f" Nota Subpartida: {n[:150]}."
            break

    # Notas de seccion (RGI 1: misma jerarquia)
    for n in notas.get("notas_legales_sec", []):
        if "motor" in n.lower() or partida in n:
            notas_str += f" Nota Sec.{notas.get('seccion','')}: {n[:120]}."
            break

    # RGI 1 + RGI 6: preferir la mas especifica que aplique
    candidatas_especificas.sort(key=lambda x: x[2], reverse=True)

    # Si hay especifica con score > 0, usarla
    for cod, desc, score in candidatas_especificas:
        if score > 0:
            razon = (
                f"RGI 1 + RGI 6 (Decreto 755-22 Art. 63): Se evaluaron "
                f"{len(hermanas)} SON hermanas de la subpartida {son_rechazado[:7]}. "
                f"Descartado {son_rechazado} porque su descripcion oficial no "
                f"coincide con el producto consultado. "
                f"SON {cod} ({desc[:60]}) es la mas especifica que aplica "
                f"(score coherencia={score}).{notas_str}"
            )
            return cod, razon

    # Ninguna especifica matchea -> usar residual
    # En las residuales, aplicar criterio de subpartida desde las descripciones
    if candidatas_residuales:
        # Si hay multiples residuales (ej: .91 DC, .92 AC), analizar cual aplica
        if len(candidatas_residuales) > 1:
            elegida, criterio = _decidir_entre_residuales(
                consulta, candidatas_residuales, notas)
            if elegida:
                razon = (
                    f"RGI 1 + RGI 6: Ninguna SON especifica de {son_rechazado[:7]} "
                    f"describe el producto. Se evaluaron las residuales ('Los demas'). "
                    f"{criterio}{notas_str}"
                )
                return elegida, razon

        # Una sola residual o no se pudo decidir: tomar la primera
        cod_res, desc_res = candidatas_residuales[0]
        razon = (
            f"RGI 1 + RGI 6: Ninguna SON especifica de {son_rechazado[:7]} "
            f"describe el producto. Clasificacion en residual {cod_res} "
            f"({desc_res[:60]}) por descarte jerarquico.{notas_str}"
        )
        return cod_res, razon

    return None, "No se encontro hermana alternativa viable"


def _decidir_entre_residuales(
    consulta: str,
    residuales: List[Tuple[str, str]],
    notas: Dict[str, Any],
) -> Tuple[Optional[str], str]:
    """
    Cuando hay multiples residuales (ej: 8501.10.91 'DC' y 8501.10.92 'AC'),
    lee las descripciones y las notas legales para decidir cual aplica.

    Analiza el texto de cada residual buscando criterios tecnicos que matcheen
    con la consulta del usuario. Si no hay match claro, retorna la ultima
    (RGI 6: la ultima subpartida en el orden numeral del Arancel).
    """
    consulta_l = consulta.lower()

    # Extraer descriptores tecnicos de cada residual
    evaluaciones = []
    for cod, desc in residuales:
        desc_l = desc.lower()
        # Limpiar prefijos de guion
        desc_limpia = re.sub(r'^[\s\-]+', '', desc_l)
        # Extraer palabras tecnicas de la descripcion
        palabras_desc = set(re.findall(r'\b[a-záéíóúüñ]{3,}\b', desc_limpia))
        palabras_desc -= _STOPWORDS
        # Buscar match con la consulta
        match_palabras = palabras_desc & set(re.findall(r'\b[a-záéíóúüñ]{3,}\b', consulta_l))
        evaluaciones.append({
            "cod": cod,
            "desc": desc,
            "desc_limpia": desc_limpia,
            "palabras_tecnicas": palabras_desc,
            "match": match_palabras,
            "score": len(match_palabras),
        })

    # Ordenar por score
    evaluaciones.sort(key=lambda x: x["score"], reverse=True)

    # Si hay un ganador claro
    if evaluaciones and evaluaciones[0]["score"] > 0:
        mejor = evaluaciones[0]
        criterio = (
            f"Residual {mejor['cod']} ({mejor['desc'][:60]}) seleccionada "
            f"por coincidencia tecnica con la consulta: "
            f"{mejor['match']}."
        )
        return mejor["cod"], criterio

    # Sin match directo: buscar pistas tecnicas en la consulta para
    # mapear contra las descripciones de las residuales
    # Ej: "dron agricola" -> motor sin escobillas -> corriente continua
    pistas = _extraer_pistas_tecnicas(consulta_l)
    if pistas:
        for ev in evaluaciones:
            for pista_key, pista_desc in pistas:
                if any(p in ev["desc_limpia"] for p in pista_key.split("|")):
                    criterio = (
                        f"Residual {ev['cod']} ({ev['desc'][:60]}) seleccionada "
                        f"por inferencia tecnica: {pista_desc}."
                    )
                    return ev["cod"], criterio

    # RGI 6: ultima subpartida en orden numeral del Arancel
    ultima = residuales[-1]
    criterio = (
        f"RGI 6: Sin criterio tecnico diferenciador, se asigna la "
        f"ultima subpartida en orden numeral: {ultima[0]} ({ultima[1][:60]})."
    )
    return ultima[0], criterio


def _extraer_pistas_tecnicas(consulta: str) -> List[Tuple[str, str]]:
    """
    Extrae pistas tecnicas de la consulta que ayudan a diferenciar
    entre subpartidas residuales. NO hardcodea la respuesta — genera
    mapeos genericos 'pista_en_consulta -> descriptor_en_arancel'.

    Retorna lista de (patron_a_buscar_en_descripcion, explicacion).
    """
    pistas = []

    # Tipo de corriente electrica
    if any(t in consulta for t in ["continua", " dc ", "brushless", "bldc",
                                    "sin escobillas", "bateria"]):
        pistas.append(("continua", "producto opera con corriente continua (DC)"))
    if any(t in consulta for t in ["alterna", " ac ", "monofasico", "trifasico",
                                    "110v", "220v", "60hz", "50hz"]):
        pistas.append(("alterna", "producto opera con corriente alterna (AC)"))

    # Inferencias por tipo de uso (no hardcodeado al codigo, sino al descriptor)
    # Para drones/aeronaves: NO forzar DC ni AC — dejar que RGI 6 decida
    # (ultima subpartida en orden numeral del Arancel)
    if ("vehiculo" in consulta and "electrico" in consulta) or "automotriz" in consulta:
        pistas.append(("continua",
                       "motores para vehiculos electricos tipicamente DC"))
    if any(t in consulta for t in ["bomba", "compresor", "ventilador"]):
        pistas.append(("alterna",
                       "motores para maquinaria industrial tipicamente AC"))

    return pistas


def validar_jerarquia(consulta: str, son_propuesto: str) -> Dict[str, Any]:
    """
    Valida que el SON propuesto respeta la jerarquia SA.

    Procedimiento normativo:
      1. Verificar existencia del codigo
      2. Obtener TODAS las hermanas de la subpartida
      3. Comparar descripcion de cada hermana contra la consulta
      4. Si el propuesto es "Las demas" pero hay hermana especifica
         que matchea -> proponer correccion
      5. Si el propuesto es especifico -> confirmar coherencia
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

    desc_propuesto = codigos.get(son_propuesto, "")
    if not desc_propuesto:
        resultado["razon"] = f"codigo {son_propuesto} no existe en el Arancel RD"
        return resultado

    desc_propuesto_str = str(desc_propuesto).lower()
    hermanas = obtener_hermanas(son_propuesto)
    resultado["hermanas_evaluadas"] = len(hermanas)

    if len(hermanas) <= 1:
        resultado["valido"] = True
        resultado["jerarquia_respetada"] = True
        resultado["nivel"] = "unica"
        resultado["razon"] = "codigo unico en su subpartida — no hay alternativas"
        return resultado

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

    especificas = [s for s in scores if not s["es_demas"] and s["hits"] > 0]
    especificas.sort(key=lambda x: x["hits"], reverse=True)

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
                f"con {mejor['hits']} coincidencias. RGI 1: evaluar "
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
    Aplica 3 capas de defensa con fundamento normativo:

      CAPA 1: Blacklist de coherencia semantica
              (SON conocidos como problematicos — defensa rapida)
      CAPA 2: Score de coherencia semantica
              (descripcion oficial vs consulta — sin match = rechazar)
      CAPA 3: Validacion jerarquica SA completa
              (Las demas vs especifica — RGI 1 + RGI 6)

    Cuando rechaza, lee Notas Legales del Capitulo y Seccion (RGI 1),
    recorre las hermanas con analisis normativo, y construye razonamiento
    legal citando las reglas aplicadas.
    """
    # Obtener notas legales del capitulo para fundamentar decisiones
    cap = son_propuesto[:2] if len(son_propuesto) >= 2 else ""
    notas = _obtener_notas_capitulo(cap) if cap else {}

    # ── CAPA 1: Blacklist de coherencia ──
    bl_razon = _verificar_blacklist(consulta, son_propuesto)
    if bl_razon:
        mejor, razonamiento = _analizar_hermanas_con_notas(
            consulta, son_propuesto, notas)
        informe = {
            "valido": False,
            "son_propuesto": son_propuesto,
            "son_corregido": mejor,
            "razon": bl_razon,
            "razonamiento_legal": razonamiento,
            "notas_consultadas": {
                "capitulo": cap,
                "notas_cap": notas.get("notas_legales_cap", [])[:3],
                "notas_subpartida": notas.get("notas_subpartida_cap", [])[:2],
                "notas_adicionales": notas.get("notas_adicionales_cap", [])[:1],
                "seccion": notas.get("seccion", ""),
                "notas_sec": notas.get("notas_legales_sec", [])[:2],
                "tiene_rgi": bool(notas.get("rgi_completas")),
            },
            "hermanas_evaluadas": len(obtener_hermanas(son_propuesto)),
            "jerarquia_respetada": False,
            "nivel": "blacklist_coherencia",
            "defensa": "blacklist",
        }
        if mejor:
            desc_mejor = str(_cargar_cache().get(mejor, ""))
            print(
                f"[JERARQUIA-SA] BLACKLIST+NOTAS: {son_propuesto} -> {mejor} "
                f"({desc_mejor[:60]}). {razonamiento[:120]}"
            )
            return mejor, informe
        print(f"[JERARQUIA-SA] BLACKLIST: {son_propuesto} rechazado, sin alternativa")
        return son_propuesto, informe

    # ── CAPA 2: Score de coherencia semantica ──
    codigos = _cargar_cache()
    desc_propuesto = str(codigos.get(son_propuesto, ""))
    score = _score_coherencia_semantica(consulta, son_propuesto, desc_propuesto)
    if score < 15 and desc_propuesto:
        mejor, razonamiento = _analizar_hermanas_con_notas(
            consulta, son_propuesto, notas)
        if mejor and mejor != son_propuesto:
            desc_mejor = str(codigos.get(mejor, ""))
            score_mejor = _score_coherencia_semantica(consulta, mejor, desc_mejor)
            informe = {
                "valido": False,
                "son_propuesto": son_propuesto,
                "son_corregido": mejor,
                "razon": (f"Coherencia semantica {son_propuesto} "
                          f"({desc_propuesto[:50]}) score={score} < 15."),
                "razonamiento_legal": razonamiento,
                "notas_consultadas": {
                    "capitulo": cap,
                    "notas_cap": notas.get("notas_legales_cap", [])[:3],
                    "seccion": notas.get("seccion", ""),
                },
                "hermanas_evaluadas": len(obtener_hermanas(son_propuesto)),
                "jerarquia_respetada": False,
                "nivel": "coherencia_baja",
                "defensa": "coherencia_semantica",
                "score_original": score,
                "score_corregido": score_mejor,
            }
            print(
                f"[JERARQUIA-SA] COHERENCIA+NOTAS: {son_propuesto} (score={score}) "
                f"-> {mejor}. {razonamiento[:120]}"
            )
            return mejor, informe

    # ── CAPA 3: Validacion jerarquica SA (original) ──
    informe = validar_jerarquia(consulta, son_propuesto)
    mapa_info = _enriquecer_con_mapa_rgi(consulta, son_propuesto)
    if mapa_info:
        informe["mapa_rgi"] = mapa_info
    informe["score_coherencia"] = score

    if informe["valido"]:
        return son_propuesto, informe

    corregido = informe.get("son_corregido")
    if corregido:
        bl_corr = _verificar_blacklist(consulta, corregido)
        if bl_corr:
            mejor, razonamiento = _analizar_hermanas_con_notas(
                consulta, son_propuesto, notas)
            if mejor:
                corregido = mejor
                informe["son_corregido"] = mejor
                informe["razonamiento_legal"] = razonamiento
        print(
            f"[JERARQUIA-SA] Correccion: {son_propuesto} -> {corregido} "
            f"({informe['razon'][:100]})"
        )
        return corregido, informe

    return son_propuesto, informe
