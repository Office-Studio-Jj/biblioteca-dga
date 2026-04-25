#!/usr/bin/env python3
"""
MERCEOLOGIA AGENT — Sub-agente cache-first para consultas arancelarias
======================================================================
Intercepta consultas antes de Gemini. Si hay ficha merceologica previa
que matchea la descripcion del producto, devuelve respuesta instantanea
con el codigo arancelario ya validado (0% Gemini, 100% cache-first).

Ganancia: consultas con match retornan en <500ms (vs 8-10s con Gemini).

Integracion: llamado desde server.py /consultar antes de ask_notebooklm.
"""

import os
import re
import json
import time
import unicodedata
from pathlib import Path
from typing import Optional, Tuple, List, Dict


_MERCEO_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "data", "merceologia"
)

# Cache en memoria: {slug: {"contenido": str, "keywords": set, "codigo": str, "mtime": float}}
_FICHAS_CACHE: Dict[str, dict] = {}
_CACHE_MTIME = 0.0


def _normalizar(s: str) -> str:
    """Normaliza texto para matching: minusculas, sin acentos, sin signos."""
    s = (s or "").strip().lower()
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = s.replace('ñ', 'n')
    return s


def _extraer_keywords(texto: str) -> set:
    """Extrae keywords significativas (len >= 4, no stopwords)."""
    stopwords = {
        'para', 'cual', 'como', 'donde', 'este', 'esta', 'estas', 'estos',
        'pueda', 'tiene', 'tienen', 'puede', 'pueden', 'favor', 'quiero',
        'necesito', 'consulta', 'clasificar', 'producto', 'producto',
        'con', 'sin', 'por', 'entre', 'sobre', 'bajo', 'desde', 'hacia',
        'segun', 'durante', 'mediante', 'hasta', 'contra', 'uso', 'usa',
        'usan', 'usar', 'los', 'las', 'del', 'una', 'uno', 'unas', 'unos',
    }
    texto_norm = _normalizar(texto)
    palabras = re.findall(r'\b[a-z0-9]{4,}\b', texto_norm)
    return {p for p in palabras if p not in stopwords}


def _extraer_codigo_de_ficha(contenido_md: str) -> Optional[str]:
    """Extrae el codigo arancelario RD (8 dig) de la pregunta 7."""
    m = re.search(
        r'(?:[Cc]odigo\s+nacional\s+RD|c[oó]digo\s+(?:arancelario\s+)?(?:RD)?)[^:]*:\s*'
        r'[_\*\[]*\s*(\d{4}\.\d{2}\.\d{2})',
        contenido_md
    )
    if m:
        return m.group(1)
    # Fallback: cualquier XXXX.XX.XX en la seccion 7
    m_sec7 = re.search(r'##\s*7\..*?(?=##|\Z)', contenido_md, re.DOTALL)
    if m_sec7:
        m_code = re.search(r'\b(\d{4}\.\d{2}\.\d{2})\b', m_sec7.group(0))
        if m_code:
            return m_code.group(1)
    return None


def _extraer_denominacion(contenido_md: str) -> str:
    """Extrae la denominacion tecnica y comercial de la pregunta 1."""
    m = re.search(r'##\s*1\..*?(?=##|\Z)', contenido_md, re.DOTALL)
    if not m:
        return ""
    seccion = m.group(0)
    tecnica = re.search(r'[Dd]enominaci[oó]n\s+t[eé]cnica[^:]*:\s*([^\n_*]+)', seccion)
    comercial = re.search(r'[Dd]enominaci[oó]n\s+comercial[^:]*:\s*([^\n_*]+)', seccion)
    partes = []
    if tecnica:
        partes.append(tecnica.group(1).strip())
    if comercial:
        partes.append(comercial.group(1).strip())
    return " | ".join(partes)


def _extraer_campo_ficha(contenido_md: str, seccion_num: int, patron: str, default: str = "") -> str:
    """Extrae un campo especifico dentro de una seccion numerada de la ficha."""
    m_sec = re.search(rf'##\s*{seccion_num}\..*?(?=##|\Z)', contenido_md, re.DOTALL)
    if not m_sec:
        return default
    m_val = re.search(patron, m_sec.group(0))
    if m_val:
        val = m_val.group(1).strip()
        # Limpiar asteriscos/underscores/backticks de markdown
        val = re.sub(r'[*_`]', '', val)
        return val.strip()
    return default


def _extraer_datos_merceologicos(contenido_md: str) -> dict:
    """Extrae los 7 campos clave de la ficha para el bloque DATOS_CLASIFICACION."""
    datos = {}
    datos["identificacion"] = _extraer_campo_ficha(
        contenido_md, 1, r'[Dd]enominaci[oó]n\s+t[eé]cnica[^:]*:\s*([^\n]+)'
    )
    datos["materia"] = _extraer_campo_ficha(
        contenido_md, 2, r'[Mm]aterial\s+principal[^:]*:\s*([^\n]+)'
    )
    datos["funcion"] = _extraer_campo_ficha(
        contenido_md, 3, r'[Ff]unci[oó]n\s+principal[^:]*:\s*([^\n]+)'
    )
    datos["criterio"] = _extraer_campo_ficha(
        contenido_md, 6, r'[Cc]riterio\s+dominante[^:]*:\s*([^\n]+)'
    )
    datos["rgi"] = _extraer_campo_ficha(
        contenido_md, 6, r'RGI\s+(\d[^\n\(]*)', default="RGI 1"
    )
    datos["restricciones"] = _extraer_campo_ficha(
        contenido_md, 5, r'[Rr]estricciones\s+regulatorias[^:]*:\s*([^\n]+)', default="NINGUNA"
    )
    datos["partida"] = _extraer_campo_ficha(
        contenido_md, 7, r'[Pp]artida\s+SA[^:]*:\s*(\d{4})'
    )
    datos["subpartida"] = _extraer_campo_ficha(
        contenido_md, 7, r'[Ss]ubpartida\s+SA[^:]*:\s*(\d{4}\.\d{2})'
    )
    datos["capitulo"] = _extraer_campo_ficha(
        contenido_md, 7, r'[Cc]ap[ií]tulo\s+SA[^:]*:\s*(\d{2})'
    )
    datos["descripcion_cod"] = _extraer_campo_ficha(
        contenido_md, 7, r'[Dd]escripci[oó]n\s+del\s+c[oó]digo[^:]*:\s*([^\n]+)'
    )
    datos["gravamen_ficha"] = _extraer_campo_ficha(
        contenido_md, 7, r'[Gg]ravamen\s+esperado[^:]*:\s*(\d+)'
    )
    datos["isc_ficha"] = _extraer_campo_ficha(
        contenido_md, 7, r'ISC\s+aplicable[^:]*:\s*([^\n]+)'
    )
    return datos


_SECCIONES_SA = [
    ("I",     range(1, 6),   "Animales vivos y productos del reino animal"),
    ("II",    range(6, 15),  "Productos del reino vegetal"),
    ("III",   range(15, 16), "Grasas y aceites animales o vegetales"),
    ("IV",    range(16, 25), "Productos alimenticios; bebidas; tabaco"),
    ("V",     range(25, 28), "Productos minerales"),
    ("VI",    range(28, 39), "Productos de las industrias quimicas"),
    ("VII",   range(39, 41), "Plasticos y caucho"),
    ("VIII",  range(41, 44), "Pieles, cueros, peleteria"),
    ("IX",    range(44, 47), "Madera, carbon vegetal, corcho"),
    ("X",     range(47, 50), "Pasta de madera, papel y carton"),
    ("XI",    range(50, 64), "Materias textiles y sus manufacturas"),
    ("XII",   range(64, 68), "Calzado, sombrereria, paraguas"),
    ("XIII",  range(68, 71), "Manufacturas de piedra, yeso, vidrio, ceramica"),
    ("XIV",   range(71, 72), "Perlas finas, piedras y metales preciosos"),
    ("XV",    range(72, 84), "Metales comunes y sus manufacturas"),
    ("XVI",   range(84, 86), "Maquinas y aparatos, material electrico"),
    ("XVII",  range(86, 90), "Material de transporte"),
    ("XVIII", range(90, 93), "Instrumentos de optica, fotografia, medico"),
    ("XIX",   range(93, 94), "Armas, municiones y sus partes"),
    ("XX",    range(94, 97), "Mercancias y productos diversos"),
    ("XXI",   range(97, 98), "Objetos de arte, antiguedades"),
]

_NOMBRES_CAPITULO = {
    "01": "Animales vivos", "02": "Carnes y despojos", "03": "Pescados y crustaceos",
    "04": "Lacteos, huevos, miel", "05": "Productos de origen animal",
    "06": "Plantas vivas y floricultura", "07": "Hortalizas", "08": "Frutas",
    "09": "Cafe, te, especias", "10": "Cereales", "11": "Productos molineria",
    "12": "Semillas y frutos oleaginosos", "13": "Gomas y resinas", "14": "Materias trenzables",
    "15": "Grasas y aceites", "16": "Preparaciones de carne, pescado",
    "17": "Azucares y articulos confiteria", "18": "Cacao y preparaciones",
    "19": "Preparaciones cereal/harina", "20": "Preparaciones hortalizas, frutas",
    "21": "Preparaciones alimenticias diversas", "22": "Bebidas, liquidos alcoholicos, vinagre",
    "23": "Residuos industria alimentaria", "24": "Tabaco", "25": "Sal, azufre, tierras",
    "26": "Minerales metaliferos", "27": "Combustibles minerales, aceites",
    "28": "Productos quimicos inorganicos", "29": "Productos quimicos organicos",
    "30": "Productos farmaceuticos", "31": "Abonos", "32": "Extractos curtientes",
    "33": "Aceites esenciales, perfumeria, cosmetica", "34": "Jabones, detergentes",
    "35": "Materias albuminoideas", "36": "Polvoras, explosivos",
    "37": "Productos fotograficos/cinematograficos", "38": "Productos quimicos diversos",
    "39": "Plasticos y sus manufacturas", "40": "Caucho y sus manufacturas",
    "41": "Pieles y cueros", "42": "Manufacturas de cuero", "43": "Peleteria",
    "44": "Madera", "45": "Corcho", "46": "Manufacturas esparteria/cesteria",
    "47": "Pasta de madera/celulosa", "48": "Papel y carton",
    "49": "Productos editoriales", "50": "Seda", "51": "Lana, pelos finos",
    "52": "Algodon", "53": "Demas fibras textiles vegetales",
    "54": "Filamentos sinteticos/artificiales", "55": "Fibras sinteticas/artificiales discontinuas",
    "56": "Guata, fieltro, cordeleria", "57": "Alfombras",
    "58": "Tejidos especiales", "59": "Tejidos impregnados/recubiertos",
    "60": "Tejidos de punto", "61": "Prendas vestir punto",
    "62": "Prendas vestir excepto punto", "63": "Demas articulos textiles confeccionados",
    "64": "Calzado", "65": "Sombrereria", "66": "Paraguas, bastones",
    "67": "Plumas, flores artificiales", "68": "Manufacturas piedra/yeso/cemento",
    "69": "Productos ceramicos", "70": "Vidrio y sus manufacturas",
    "71": "Perlas, piedras y metales preciosos", "72": "Fundicion, hierro y acero",
    "73": "Manufacturas de fundicion, hierro o acero", "74": "Cobre",
    "75": "Niquel", "76": "Aluminio", "78": "Plomo", "79": "Zinc",
    "80": "Estano", "81": "Demas metales comunes",
    "82": "Herramientas, utiles, articulos cuchilleria",
    "83": "Manufacturas diversas metales comunes",
    "84": "Maquinas y aparatos mecanicos",
    "85": "Maquinas, aparatos y material electrico, sus partes",
    "86": "Vehiculos y material para vias ferreas",
    "87": "Vehiculos automoviles, tractores",
    "88": "Aeronaves, vehiculos espaciales y sus partes",
    "89": "Barcos y demas artefactos flotantes",
    "90": "Instrumentos de optica, fotografia, medico-quirurgicos",
    "91": "Relojeria", "92": "Instrumentos musicales",
    "93": "Armas, municiones y sus partes", "94": "Muebles, aparatos de alumbrado",
    "95": "Juguetes, juegos, articulos para deporte", "96": "Manufacturas diversas",
    "97": "Objetos de arte, antiguedades",
}


def _vucerd_para_capitulo(cap: str) -> str:
    """ERR-026 fondo: VUCERD no es 'NO REQUIERE' siempre. Detectar segun capitulo."""
    cap_str = str(cap).zfill(2)
    requiere = {
        "01": "SI - sanitario animal", "02": "SI - sanitario carnes", "03": "SI - sanitario pesca",
        "04": "SI - sanitario lacteos", "06": "SI - fitosanitario plantas",
        "07": "SI - fitosanitario hortalizas", "08": "SI - fitosanitario frutas",
        "10": "SI - fitosanitario cereales", "12": "SI - fitosanitario semillas",
        "30": "SI - registro DIGEMAPS para farmaceuticos", "33": "SI - registro DIGEMAPS cosmeticos",
        "31": "SI - Ministerio Agricultura para abonos",
        "38": "SI - registro fitosanitario para pesticidas",
        "85": "SI si telecomunicaciones - homologacion INDOTEL",
        "86": "SI si maquina vias ferreas - certificacion",
        "87": "SI - registro vehicular DGII", "88": "SI - INDOTEL + IDAC si >25kg",
        "89": "SI - DGII registro embarcaciones", "93": "SI - licencia MICM/Defensa armas",
        "97": "SI - permiso Min. Cultura objetos arte/antiguedad",
    }
    return requiere.get(cap_str, "Verificar segun mercancia (algunos capitulos requieren VUCERD)")


def _permisos_para_consulta_y_capitulo(consulta: str, cap: str) -> str:
    """Devuelve lista de entidades emisoras de permisos requeridos (INDOTEL, IDAC, MISPAS, etc.)"""
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "data", "fuentes_nomenclatura", "permisos_especiales.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cap_str = str(cap).zfill(2)
        consulta_lower = (consulta or "").lower()
        entidades = []
        for perm in data.get("permisos", []):
            aplica = False
            if cap_str in perm.get("capitulos", []):
                aplica = True
            if any(kw in consulta_lower for kw in perm.get("keywords_consulta", [])):
                aplica = True
            if aplica:
                entidades.append(perm["entidad"])
        return ", ".join(entidades) if entidades else "NINGUNO"
    except Exception:
        return "Verificar manualmente"


def _leyes_para_consulta_y_capitulo(consulta: str, cap: str) -> str:
    """Devuelve leyes de beneficio aplicables (150-97, 28-01, 8-90, 195-13, etc.)"""
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "data", "fuentes_nomenclatura", "leyes_beneficio.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cap_str = str(cap).zfill(2)
        consulta_lower = (consulta or "").lower()
        leyes = []
        for ley in data.get("leyes", []):
            triggered_kw = any(kw in consulta_lower for kw in ley.get("keywords_consulta", []))
            triggered_cap = cap_str in ley.get("capitulos_aplicables", [])
            if triggered_kw and (triggered_cap or not ley.get("capitulos_aplicables")):
                ben = ley.get("beneficio", {})
                leyes.append(f"{ley['ley']} (DAI: {ben.get('DAI', '?')}, ITBIS: {ben.get('ITBIS', '?')})")
        return " | ".join(leyes) if leyes else "Tarifa NMF estandar (sin ley de beneficio detectada)"
    except Exception:
        return "Verificar manualmente"


def _conflictos_para_consulta_y_partida(consulta: str, partida: str) -> str:
    """Devuelve conflictos arancelarios clasicos relevantes"""
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "data", "fuentes_nomenclatura", "conflictos_arancelarios.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        consulta_lower = (consulta or "").lower()
        partida_str = str(partida)
        conflictos = []
        for conf in data.get("conflictos", []):
            kw_match = any(kw in consulta_lower for kw in conf.get("trigger_keywords", []))
            partida_match = any(p in partida_str[:4] for p in conf.get("partidas_en_conflicto", []))
            if kw_match and partida_match:
                conflictos.append(f"{conf['id']}: ganadora {conf['ganadora']} ({conf.get('exclusion_destino', '')})")
        return " | ".join(conflictos) if conflictos else "NINGUNO"
    except Exception:
        return "Verificar manualmente"


def _seccion_para_capitulo(cap: str) -> tuple:
    """Devuelve (numero_romano, nombre_seccion) para un numero de capitulo str."""
    try:
        cap_n = int(cap)
    except (ValueError, TypeError):
        return ("?", "Verificar Arancel")
    for romano, rng, nombre in _SECCIONES_SA:
        if cap_n in rng:
            return (romano, nombre)
    return ("?", "Verificar Arancel")


def _nombre_capitulo(cap: str) -> str:
    return _NOMBRES_CAPITULO.get(str(cap).zfill(2), "Verificar descripcion oficial Arancel")


def _gravamen_desde_cache(codigo: str) -> tuple:
    """Consulta arancel_cache para obtener gravamen real. Returns (valor, fuente)."""
    try:
        cache_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "data", "fuentes_nomenclatura", "arancel_cache.json"
        )
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        codigos = data.get("codigos", data) if isinstance(data, dict) else {}
        desc = codigos.get(codigo, "") if isinstance(codigos, dict) else ""
        m = re.search(r'\s+(\d+)\s*$', (desc or "").strip())
        if m:
            return int(m.group(1)), "arancel_cache.json"
    except Exception:
        pass
    return None, ""


def _isc_desde_lookup(codigo: str) -> str:
    """Consulta isc_lookup para ISC real. Returns texto formateado o 'NO APLICA'."""
    try:
        isc_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "data", "fuentes_nomenclatura", "isc_lookup.json"
        )
        with open(isc_path, "r", encoding="utf-8") as f:
            isc_data = json.load(f)
        cap = codigo[:2]
        cap_data = isc_data.get("capitulos_con_isc", {}).get(cap)
        if not cap_data:
            return "NO APLICA"
        verificados = cap_data.get("codigos_verificados", {})
        if codigo in verificados:
            isc_val = verificados[codigo].get("isc")
            if isc_val:
                return f"{isc_val} — Ley 11-92 Art. 375, bienes suntuarios electronicos"
        partidas_af = cap_data.get("partidas_afectadas", [])
        if any(codigo.startswith(p) for p in partidas_af):
            default = cap_data.get("tasas", {}).get("default")
            if default:
                return f"{default} — Ley 11-92 Art. 375, bienes suntuarios electronicos"
    except Exception:
        pass
    return "NO APLICA"


def _renderizar_ficha_visible(contenido_md: str, slug: str) -> str:
    """Extrae las 7 secciones completas de la ficha MD para mostrar al usuario."""
    secciones = []
    for i in range(1, 8):
        m = re.search(rf'##\s*{i}\..*?(?=##\s*\d|\Z)', contenido_md, re.DOTALL)
        if m:
            texto = m.group(0).strip()
            secciones.append(texto)
    if not secciones:
        return ""
    return "\n\n".join(secciones)


def _cargar_fichas(forzar: bool = False) -> None:
    """Carga/recarga las fichas del directorio. Lazy + mtime-aware."""
    global _FICHAS_CACHE, _CACHE_MTIME

    if not os.path.isdir(_MERCEO_DIR):
        return

    # Detectar si el directorio cambio
    try:
        dir_mtime = os.path.getmtime(_MERCEO_DIR)
    except OSError:
        return

    if not forzar and _FICHAS_CACHE and dir_mtime == _CACHE_MTIME:
        return

    _FICHAS_CACHE.clear()
    for fname in os.listdir(_MERCEO_DIR):
        if not fname.endswith(".md"):
            continue
        ruta = os.path.join(_MERCEO_DIR, fname)
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                contenido = f.read()
        except Exception:
            continue
        slug = fname[:-3]
        # Keywords = slug (nombre del producto) + contenido del MD
        texto_indexable = slug.replace("-", " ") + " " + _extraer_denominacion(contenido)
        _FICHAS_CACHE[slug] = {
            "contenido": contenido,
            "keywords": _extraer_keywords(texto_indexable),
            "codigo": _extraer_codigo_de_ficha(contenido),
            "mtime": os.path.getmtime(ruta),
        }

    _CACHE_MTIME = dir_mtime


def buscar_ficha_para_consulta(consulta: str, umbral: float = 0.5) -> Optional[Tuple[str, dict, float]]:
    """
    Busca la ficha que mejor matchea la consulta.

    Args:
        consulta: texto de la pregunta del usuario
        umbral: score minimo (0.0-1.0) para considerar match. Default 0.5.

    Returns:
        (slug, ficha_dict, score) si match >= umbral, else None.
        score = |interseccion| / |keywords_consulta|
    """
    _cargar_fichas()
    if not _FICHAS_CACHE:
        return None

    kw_consulta = _extraer_keywords(consulta)
    if not kw_consulta:
        return None

    mejor_slug = None
    mejor_ficha = None
    mejor_score = 0.0

    for slug, ficha in _FICHAS_CACHE.items():
        kw_ficha = ficha["keywords"]
        if not kw_ficha:
            continue
        interseccion = kw_consulta & kw_ficha
        if not interseccion:
            continue
        # Score = cobertura de la consulta por la ficha
        score = len(interseccion) / max(len(kw_consulta), 1)
        if score > mejor_score:
            mejor_score = score
            mejor_slug = slug
            mejor_ficha = ficha

    if mejor_ficha and mejor_score >= umbral:
        return mejor_slug, mejor_ficha, mejor_score
    return None


def construir_respuesta_desde_ficha(
    slug: str,
    ficha: dict,
    score: float,
    consulta_original: str
) -> Optional[str]:
    """
    Construye respuesta final (texto al usuario) desde una ficha merceologica.
    Retorna None si la ficha no tiene codigo arancelario valido.

    El formato replica la estructura que produce ask_gemini.py para que el
    supervisor_interno pueda validarla de forma consistente.
    """
    codigo = ficha.get("codigo")
    if not codigo:
        return None

    # Verificar que el codigo existe en el arancel antes de devolverlo
    # (defensa extra contra fichas con codigos obsoletos)
    try:
        from supervisor_interno import verificar_codigo_en_fuentes
        existe, _msg = verificar_codigo_en_fuentes(codigo)
        if not existe:
            # Codigo en ficha es invalido — no usar
            return None
    except ImportError:
        pass  # Sin supervisor, proceder con cuidado

    contenido = ficha["contenido"]
    denominacion = _extraer_denominacion(contenido)
    nombre_producto = slug.replace("-", " ").title()
    datos_m = _extraer_datos_merceologicos(contenido)

    # Gravamen real: prioriza arancel_cache sobre la ficha
    grav_cache, fuente_grav = _gravamen_desde_cache(codigo)
    if grav_cache is not None:
        gravamen_final = f"{grav_cache}% — NMF estandar (verificado {fuente_grav})"
    elif datos_m.get("gravamen_ficha"):
        gravamen_final = f"{datos_m['gravamen_ficha']}% — NMF estandar (ficha merceologica)"
    else:
        gravamen_final = "VERIFICAR EN ARANCEL VIGENTE"

    # ISC real: consultar isc_lookup
    isc_final = _isc_desde_lookup(codigo)

    # Ficha visible completa (7 secciones)
    ficha_visible = _renderizar_ficha_visible(contenido, slug)

    # Campos para bloque DATOS_CLASIFICACION
    capitulo = datos_m.get("capitulo") or codigo[:2]
    partida = datos_m.get("partida") or codigo[:4]
    subpartida = datos_m.get("subpartida") or codigo[:7]
    desc_cod = datos_m.get("descripcion_cod") or denominacion or nombre_producto
    identificacion = datos_m.get("identificacion") or denominacion or nombre_producto
    materia = datos_m.get("materia") or "Ver ficha merceologica"
    funcion = datos_m.get("funcion") or "Ver ficha merceologica"
    criterio = datos_m.get("criterio") or "FUNCION"
    rgi = datos_m.get("rgi") or "RGI 1"
    restricciones = datos_m.get("restricciones") or "NINGUNA"

    # FIX ERR-026: nombres correctos por capitulo, no hardcoded a Cap.85
    seccion_romana, seccion_nombre = _seccion_para_capitulo(capitulo)
    capitulo_nombre = _nombre_capitulo(capitulo)

    respuesta = f"""# {codigo} — {identificacion}

**Respuesta desde cache merceologico** (score={score:.0%}, ficha `{slug}`)

Esta clasificacion se basa en la ficha merceologica previa del producto. Compara las 7 preguntas abajo con tu consulta para confirmar que es el mismo producto.

---

## Ficha Merceologica de Referencia

{ficha_visible}

---

---DATOS_CLASIFICACION---
FUENTE_NLKM: ARANCEL DE ADUANAS DE LA REPUBLICA DOMINICANA
ARTICULO: N/A
SECCION: {seccion_romana} — {seccion_nombre}
NOTA_SECCION: N/A
CAPITULO: {capitulo} — {capitulo_nombre}
NOTA_CAPITULO: N/A
PARTIDA: {partida} — {desc_cod}
SUBPARTIDA: {subpartida} — {desc_cod}
SUBPARTIDA_NAC: {codigo} — {desc_cod}
AUDITORIA: CONDICIONADA — respuesta desde cache merceologico, confirmar con supervisor DGA
IDENTIFICACION: {identificacion}
MATERIA: {materia}
FUNCION: {funcion}
CRITERIO_CLASIFICACION: {criterio} — justificado en la ficha merceologica
RGI: {rgi}
RESTRICCIONES: {restricciones}
GRAVAMEN: {gravamen_final}
ITBIS: 18% sobre (CIF + Gravamen)
ISC: {isc_final}
VUCERD: {_vucerd_para_capitulo(capitulo)}
OTROS_PERMISOS: {_permisos_para_consulta_y_capitulo(consulta_original, capitulo)}
LEYES_BENEFICIO: {_leyes_para_consulta_y_capitulo(consulta_original, capitulo)}
CONFLICTOS_POSIBLES: {_conflictos_para_consulta_y_partida(consulta_original, partida)}
---FIN_CLASIFICACION---

> Cache-hit en {slug}. Tiempo <5ms vs 8-10s con Gemini. Si el producto consultado NO coincide con la ficha anterior, regenera la consulta con mas detalle o usa `/merceologia <producto>` para crear una ficha nueva.
"""
    return respuesta


def intentar_respuesta_cache(
    consulta: str,
    notebook_id: str,
    umbral: float = 0.5
) -> Optional[Tuple[str, dict]]:
    """
    Punto de entrada principal para el server.
    Intenta responder desde cache merceologico antes de llamar a Gemini.

    Returns:
        (respuesta_texto, metadata) si hay hit, else None.
        metadata = {"slug", "score", "codigo", "via": "merceologia_cache"}
    """
    # Solo para cuaderno de nomenclaturas (clasificacion arancelaria)
    if notebook_id != "biblioteca-de-nomenclaturas":
        return None

    if not consulta or len(consulta) < 10:
        return None

    t0 = time.time()
    match = buscar_ficha_para_consulta(consulta, umbral=umbral)
    if not match:
        return None

    slug, ficha, score = match
    respuesta = construir_respuesta_desde_ficha(slug, ficha, score, consulta)
    if not respuesta:
        return None

    elapsed_ms = int((time.time() - t0) * 1000)
    metadata = {
        "slug": slug,
        "score": round(score, 2),
        "codigo": ficha.get("codigo"),
        "via": "merceologia_cache",
        "elapsed_ms": elapsed_ms,
    }
    print(f"[MERCEOLOGIA_AGENT] HIT {slug} (score={score:.0%}, {elapsed_ms}ms) -> {ficha.get('codigo')}")
    return respuesta, metadata


def stats() -> dict:
    """Estadisticas del cache para debug/admin."""
    _cargar_fichas()
    return {
        "fichas_cargadas": len(_FICHAS_CACHE),
        "fichas_con_codigo": sum(1 for f in _FICHAS_CACHE.values() if f.get("codigo")),
        "directorio": _MERCEO_DIR,
        "directorio_existe": os.path.isdir(_MERCEO_DIR),
    }


if __name__ == "__main__":
    import sys
    _cargar_fichas()
    print(f"[MERCEOLOGIA_AGENT] {len(_FICHAS_CACHE)} fichas cargadas desde {_MERCEO_DIR}")
    for slug, ficha in _FICHAS_CACHE.items():
        print(f"  - {slug}: codigo={ficha.get('codigo')} keywords={len(ficha['keywords'])}")

    if len(sys.argv) > 1:
        consulta = " ".join(sys.argv[1:])
        print(f"\nConsulta test: {consulta!r}")
        resultado = intentar_respuesta_cache(consulta, "biblioteca-de-nomenclaturas")
        if resultado:
            respuesta, meta = resultado
            print(f"\nMETA: {meta}")
            print(f"\n{respuesta}")
        else:
            print("Sin match — Gemini procesaria esta consulta.")
