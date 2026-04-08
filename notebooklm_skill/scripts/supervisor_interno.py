#!/usr/bin/env python3
"""
SUPERVISOR GENERAL INTERNO — Controlador Maestro de Calidad
============================================================
100% Python. 0% dependencia de IA.

Gemini es un subordinado: genera borradores de respuesta.
Este modulo los VERIFICA, CORRIGE o RECHAZA antes de entregar al usuario.

PRINCIPIO FUNDAMENTAL:
  Toda respuesta de TODOS los cuadernos pasa por aqui.
  Si Python no puede verificar algo, lo marca como NO VERIFICADO.
  Python es la autoridad final. Gemini obedece.

ARQUITECTURA:
  Usuario → server.py → ask_gemini.py (borrador) → supervisor_interno.py → Usuario
"""

import re
from typing import Dict, List, Tuple, Optional


# ══════════════════════════════════════════════════════════════════════════
# SECCION 1: BASES DE DATOS DE REFERENCIA
# Fuente de verdad del sistema. Solo datos verificados fisicamente.
# Para ampliar cobertura: agregar entradas a estos diccionarios.
# ══════════════════════════════════════════════════════════════════════════

# ── Codigos arancelarios verificados en el Arancel impreso de la RD ──────
# Cada clave = subpartida SA (6 digitos XXXX.XX)
# Cada valor = dict de extension_nacional (2 digitos) → descripcion oficial
CODIGOS_VERIFICADOS_RD = {
    "9018.90": {
        "11": "Para medida de la presion arterial",
        "12": "Endoscopios",
        "13": "De diatermia",
        "14": "De transfusion",
        "15": "De anestesia",
        "16": "Instrumentos de cirugia (bisturis, cizallas, tijeras, y similares)",
        "17": "Incubadoras",
        "18": "Grapas quirurgicas",
        "19": "Los demas",
    },
    "9619.00": {
        "10": "Compresas",
        "20": "Tampones",
        "30": "Panales",
        "40": "Toallas sanitarias",
        "50": "Panitos humedos",
        "90": "Los demas",
    },
    "8543.10": {"00": "Aceleradores de particulas"},
    "8543.20": {"00": "Generadores de senales"},
    "8543.30": {"00": "Maquinas y aparatos de galvanoplastia, electrolisis o electroforesis"},
    "8543.40": {
        "11": "Cigarrillos electronicos personales",
        "12": "Dispositivos de vaporizacion electricos personales",
    },
    "8543.70": {"00": "Las demas maquinas y aparatos"},
    "8543.90": {"00": "Partes"},
}


# ── Leyes y normativas verificadas de la Republica Dominicana ────────────
LEYES_RD = {
    "168-21":  {"nombre": "Orgánica de Aduanas de la RD", "vigente": True},
    "11-92":   {"nombre": "Código Tributario", "vigente": True},
    "14-93":   {"nombre": "Arancel de Aduanas", "vigente": True},
    "755-22":  {"nombre": "Reglamento de Origen de Mercancías", "vigente": True},
    "42-01":   {"nombre": "General de Salud / DIGEMAPS", "vigente": True},
    "41-08":   {"nombre": "Función Pública", "vigente": True},
    "6097":    {"nombre": "Telecomunicaciones / INDOTEL", "vigente": True},
    "8-90":    {"nombre": "Zonas Francas", "vigente": True},
    "56-07":   {"nombre": "Cadena Textil y Calzado", "vigente": True},
    "165-14":  {"nombre": "Crea la VUCERD", "vigente": True},
    "11-23":   {"nombre": "Reforma Aduanas y Comercio Exterior", "vigente": True},
    "253-12":  {"nombre": "Fortalecimiento Capacidad Recaudatoria", "vigente": True},
    "3489":    {"nombre": "Régimen de Aduanas (DEROGADA por 168-21)", "vigente": False},
    "226-06":  {"nombre": "Autonomía DGA", "vigente": True},
    "147-00":  {"nombre": "Reforma Arancelaria", "vigente": True},
    "84-99":   {"nombre": "Reactivación Económica", "vigente": True},
    "392-07":  {"nombre": "Competitividad e Innovación Industrial", "vigente": True},
}


# ── Dominios tematicos por cuaderno ──────────────────────────────────────
DOMINIOS = {
    "biblioteca-de-nomenclaturas": {
        "nombre": "Nomenclatura Arancelaria",
        "palabras_clave": [
            "partida", "subpartida", "codigo arancelario", "arancel", "clasificacion",
            "nomenclatura", "RGI", "sistema armonizado", "merceolog", "NESA",
            "seccion", "capitulo", "gravamen", "ad valorem", "ITBIS",
        ],
    },
    "biblioteca-legal-y-procedimiento-dga": {
        "nombre": "Legal y Procedimiento DGA",
        "palabras_clave": [
            "ley", "procedimiento", "infraccion", "sancion", "recurso", "decomiso",
            "abandono", "OEA", "fiscalizacion", "reglamento", "articulo", "tribunal",
        ],
    },
    "biblioteca-para-valoracion-dga": {
        "nombre": "Valoración Aduanera",
        "palabras_clave": [
            "valoracion", "valor de transaccion", "incoterm", "CIF", "FOB", "flete",
            "seguro", "DVA", "metodo", "AVA", "OMC", "GATT", "precio",
        ],
    },
    "biblioteca-guia-integral-de-regimenes-y-subastas": {
        "nombre": "Regímenes y Subastas",
        "palabras_clave": [
            "regimen", "importacion", "exportacion", "transito", "zona franca",
            "subasta", "abandono", "levante", "DUA", "deposito", "temporal",
        ],
    },
    "biblioteca-para-aforo-dga": {
        "nombre": "Aforo DGA",
        "palabras_clave": [
            "aforo", "levante", "canal", "rojo", "verde", "amarillo", "inspeccion",
            "reconocimiento", "contenedor", "despacho", "SIGA", "fisico",
        ],
    },
    "biblioteca-procedimiento-vucerd": {
        "nombre": "Procedimiento VUCERD",
        "palabras_clave": [
            "VUCERD", "ventanilla", "DIGEMAPS", "agricultura", "INDOCAL",
            "permiso", "certificado", "sanitario", "fitosanitario", "registro",
        ],
    },
    "biblioteca-de-normas-y-origen-dga": {
        "nombre": "Normas y Origen",
        "palabras_clave": [
            "origen", "certificado de origen", "DR-CAFTA", "CARICOM", "preferencia",
            "transformacion", "acumulacion", "regla de origen", "EPA",
        ],
    },
    "guia-maestra-comercio-exterior": {
        "nombre": "Guía Maestra Comercio Exterior",
        "palabras_clave": [
            "comercio exterior", "importar", "exportar", "DGA", "requisito",
            "documento", "tramite", "pagina", "portal", "enlace",
        ],
    },
}


# ── Incoherencias producto-capitulo confirmadas en campo ─────────────────
INCOHERENCIAS_CONOCIDAS = [
    {
        "productos": ["vaper", "vaporizador", "cigarrillo electronico",
                      "e-cigarette", "vape", "pod", "vapeador", "cigarro electronico"],
        "capitulos_incorrectos": ["9619", "2402", "2403", "2404"],
        "capitulo_correcto": "8543.40 (.11 o .12)",
        "mensaje": "Vapers/cigarrillos electronicos → 8543.40.11 o 8543.40.12. "
                   "NUNCA 9619 (higienicos), NUNCA Cap. 24 (tabaco)",
    },
    {
        "productos": ["compresa", "tampon", "pañal", "toalla sanitaria",
                      "panito humedo", "toallita"],
        "capitulos_incorrectos": ["8543", "8501", "3926"],
        "capitulo_correcto": "9619.00",
        "mensaje": "Productos higienicos → 9619.00.xx",
    },
]


# ══════════════════════════════════════════════════════════════════════════
# SECCION 2: FUNCIONES DE VALIDACION
# Cada funcion retorna (estado, mensaje).
# Estados posibles: "OK", "OBSERVACION", "ERROR"
# ══════════════════════════════════════════════════════════════════════════

def _check_codigo_arancelario(respuesta: str) -> Tuple[str, str, str]:
    """
    Valida codigo arancelario contra CODIGOS_VERIFICADOS_RD.
    Solo aplica si hay bloque DATOS_CLASIFICACION en la respuesta.

    Returns:
        (respuesta_modificada, estado, mensaje)
    """
    start_tag = "---DATOS_CLASIFICACION---"
    end_tag = "---FIN_CLASIFICACION---"
    si = respuesta.find(start_tag)
    if si == -1:
        return respuesta, "OK", "Sin bloque de clasificacion"
    ei = respuesta.find(end_tag)
    if ei == -1:
        return respuesta, "OBSERVACION", "Bloque DATOS_CLASIFICACION incompleto"

    block = respuesta[si + len(start_tag):ei]

    m = re.search(r'SUBPARTIDA_NAC:\s*(\d{4}\.\d{2}\.\d{2})', block)
    if not m:
        return respuesta, "OK", "Sin codigo de 8 digitos para validar"

    codigo = m.group(1)
    partes = codigo.split(".")
    sub_sa = f"{partes[0]}.{partes[1]}"
    ext_nac = partes[2]

    # Si la subpartida SA no esta en nuestra base, no podemos validar
    if sub_sa not in CODIGOS_VERIFICADOS_RD:
        return (respuesta, "OBSERVACION",
                f"{codigo}: subpartida {sub_sa} no esta en base verificada "
                f"— requiere verificacion manual en Arancel impreso")

    validas = CODIGOS_VERIFICADOS_RD[sub_sa]

    # Codigo existe — VERIFICADO
    if ext_nac in validas:
        desc = validas[ext_nac]
        return respuesta, "OK", f"{codigo} VERIFICADO — {desc}"

    # ── CODIGO INVALIDO — CORRECCION AUTOMATICA ──
    ext_fallback = None
    for e, d in validas.items():
        if "los demas" in d.lower() or "las demas" in d.lower():
            ext_fallback = e
            break

    disponibles = "; ".join(f"{sub_sa}.{e} = {d}" for e, d in validas.items())

    if ext_fallback:
        nuevo = f"{sub_sa}.{ext_fallback}"
        desc_nuevo = validas[ext_fallback]
        nota = (f"{nuevo} — {desc_nuevo} "
                f"[CORREGIDO: {codigo} NO EXISTE en Arancel RD. "
                f"Validos bajo {sub_sa}: {disponibles}]")
    else:
        nota = (f"{sub_sa}.[verificar en Arancel RD] "
                f"[CORREGIDO: {codigo} NO EXISTE. "
                f"Validos bajo {sub_sa}: {disponibles}]")

    # Reemplazar linea SUBPARTIDA_NAC en la respuesta
    old_line_match = re.search(r'SUBPARTIDA_NAC:.*', block)
    if old_line_match:
        respuesta = respuesta.replace(old_line_match.group(0),
                                       f"SUBPARTIDA_NAC: {nota}")
    # Degradar auditoria
    respuesta = re.sub(
        r'AUDITORIA:\s*APROBADA\b',
        'AUDITORIA: CONDICIONADA — codigo corregido por Supervisor Interno',
        respuesta
    )

    return (respuesta, "ERROR",
            f"{codigo} NO EXISTE bajo {sub_sa} — corregido. "
            f"Validos: {disponibles}")


def _check_incoherencia_producto(respuesta: str, pregunta: str) -> Tuple[str, str]:
    """
    Detecta incoherencias producto-capitulo usando reglas confirmadas en campo.
    Ejemplo: vaper clasificado en 9619 (higienicos) → ERROR.
    """
    pregunta_lower = pregunta.lower()
    resp_lower = respuesta.lower()

    for regla in INCOHERENCIAS_CONOCIDAS:
        producto_en_pregunta = any(p in pregunta_lower for p in regla["productos"])
        if not producto_en_pregunta:
            continue

        for cap_inc in regla["capitulos_incorrectos"]:
            # Buscar el capitulo incorrecto en un contexto de codigo arancelario
            patron = re.compile(rf'\b{re.escape(cap_inc)}[\.\d]*\b')
            if patron.search(respuesta):
                return "ERROR", regla["mensaje"]

    return "OK", "Sin incoherencias producto-capitulo"


def _check_dominio(respuesta: str, notebook_id: str) -> Tuple[str, str]:
    """
    Verifica que la respuesta este dentro del dominio tematico del cuaderno.
    """
    dominio = DOMINIOS.get(notebook_id)
    if not dominio:
        return "OK", "Cuaderno sin dominio definido"

    resp_lower = respuesta.lower()
    hits = sum(1 for kw in dominio["palabras_clave"] if kw.lower() in resp_lower)
    total = len(dominio["palabras_clave"])
    pct = hits / total if total > 0 else 0

    if pct >= 0.15:
        return "OK", f"{dominio['nombre']} ({hits}/{total} indicadores)"
    elif pct >= 0.05:
        return ("OBSERVACION",
                f"Baja presencia de indicadores de {dominio['nombre']} "
                f"({hits}/{total}) — verificar contenido")
    else:
        return ("ERROR",
                f"Respuesta posiblemente fuera del dominio de {dominio['nombre']} "
                f"({hits}/{total} indicadores)")


def _normalizar_numero_ley(ref: str) -> str:
    """Extrae el patron numerico de una referencia legal (ej: 'Ley 168-21' → '168-21')."""
    m = re.search(r'(\d+[\-/]\d+|\d{4,})', ref)
    if m:
        return m.group(1).replace("/", "-")
    return ref.strip()


def _check_leyes_citadas(respuesta: str, notebook_id: str) -> Tuple[str, str]:
    """
    Extrae referencias a leyes/decretos del texto y verifica que sean validas.
    """
    patrones = [
        r'Ley\s+(?:No?\.?\s*)?(\d+[\-/]\d+)',
        r'Dec(?:reto)?\.?\s+(?:No?\.?\s*)?(\d+[\-/]\d+)',
        r'Ley\s+(\d{4,})',
    ]
    numeros_encontrados = set()
    for patron in patrones:
        for match in re.finditer(patron, respuesta, re.IGNORECASE):
            num = match.group(1).replace("/", "-")
            numeros_encontrados.add(num)

    if not numeros_encontrados:
        return "OK", "Sin referencias legales explicitas"

    verificadas = []
    derogadas = []
    no_verificadas = []

    for num in numeros_encontrados:
        if num in LEYES_RD:
            info = LEYES_RD[num]
            if info["vigente"]:
                verificadas.append(num)
            else:
                derogadas.append(f"{num} ({info['nombre']})")
        else:
            no_verificadas.append(num)

    partes = []
    if verificadas:
        partes.append(f"Verificadas: {', '.join(sorted(verificadas))}")
    if derogadas:
        partes.append(f"DEROGADAS: {', '.join(derogadas)}")
    if no_verificadas:
        partes.append(f"No en base: {', '.join(sorted(no_verificadas))}")

    mensaje = "; ".join(partes)

    if derogadas:
        return "ERROR", mensaje
    elif no_verificadas:
        return "OBSERVACION", mensaje
    else:
        return "OK", mensaje


def _check_coherencia(respuesta: str, pregunta: str) -> Tuple[str, str]:
    """
    Verifica coherencia basica: longitud, indicadores de incertidumbre.
    """
    if len(respuesta.strip()) < 50:
        return "ERROR", "Respuesta demasiado corta — posiblemente incompleta"

    frases_incertidumbre = [
        "no tengo acceso", "no puedo verificar", "como modelo de lenguaje",
        "no tengo información suficiente", "no dispongo de datos",
        "i don't have", "i cannot",
    ]
    resp_lower = respuesta.lower()
    for frase in frases_incertidumbre:
        if frase in resp_lower:
            return "OBSERVACION", f"Indicador de incertidumbre detectado: '{frase}'"

    return "OK", "Longitud y estructura adecuadas"


def _check_fuente(respuesta: str, notebook_id: str) -> Tuple[str, str]:
    """
    Verifica indicadores de que la información esta contextualizada en RD.
    """
    indicadores = [
        "republica dominicana", "dominicana", "DGA", "arancel",
        "aduana", "ley 168", "comercio exterior",
    ]
    resp_lower = respuesta.lower()
    hits = sum(1 for ind in indicadores if ind.lower() in resp_lower)

    if hits >= 2:
        return "OK", f"Contexto dominicano confirmado ({hits} referencias)"
    elif hits >= 1:
        return ("OBSERVACION",
                "Pocas referencias a contexto dominicano — "
                "verificar que no sea informacion generica")
    else:
        return ("OBSERVACION",
                "Sin referencias a contexto dominicano — "
                "la respuesta podria ser generica internacional")


# ══════════════════════════════════════════════════════════════════════════
# SECCION 3: MOTOR PRINCIPAL — PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════════════════

def supervisar(pregunta: str, notebook_id: str, respuesta_gemini: str) -> Tuple[str, str]:
    """
    PUNTO DE ENTRADA PRINCIPAL del Supervisor General Interno.

    Recibe el borrador de Gemini y ejecuta la bateria completa de validaciones.
    TODAS las respuestas de TODOS los cuadernos pasan por aqui.

    Args:
        pregunta:         Consulta original del usuario
        notebook_id:      ID del cuaderno consultado
        respuesta_gemini: Respuesta bruta generada por Gemini (borrador)

    Returns:
        Tupla (respuesta_corregida, bloque_supervision)
        - respuesta_corregida: texto con correcciones aplicadas
        - bloque_supervision:  bloque ---SUPERVISION---...---FIN_SUPERVISION---
    """
    print(f"[SUPERVISOR_INTERNO] Validando respuesta para: {notebook_id}")

    checks: List[Tuple[str, str, str]] = []  # (nombre, estado, mensaje)
    respuesta = respuesta_gemini

    # ── Check 1: Codigo arancelario (si hay bloque DATOS_CLASIFICACION) ──
    respuesta, st_cod, msg_cod = _check_codigo_arancelario(respuesta)
    checks.append(("Codigo", st_cod, msg_cod))

    # ── Check 2: Incoherencia producto-capitulo ──────────────────────────
    st_inc, msg_inc = _check_incoherencia_producto(respuesta, pregunta)
    checks.append(("Capitulo", st_inc, msg_inc))

    # ── Check 3: Dominio tematico del cuaderno ───────────────────────────
    st_dom, msg_dom = _check_dominio(respuesta, notebook_id)
    checks.append(("Dominio", st_dom, msg_dom))

    # ── Check 4: Leyes y normativas citadas ──────────────────────────────
    st_ley, msg_ley = _check_leyes_citadas(respuesta, notebook_id)
    checks.append(("Leyes", st_ley, msg_ley))

    # ── Check 5: Coherencia general ──────────────────────────────────────
    st_coh, msg_coh = _check_coherencia(respuesta, pregunta)
    checks.append(("Coherencia", st_coh, msg_coh))

    # ── Check 6: Fuente / contexto dominicano ────────────────────────────
    st_fue, msg_fue = _check_fuente(respuesta, notebook_id)
    checks.append(("Fuente", st_fue, msg_fue))

    # ── Determinar resultado general ─────────────────────────────────────
    errores = [c for c in checks if c[1] == "ERROR"]
    observaciones = [c for c in checks if c[1] == "OBSERVACION"]

    hay_correccion_codigo = any(c[0] == "Codigo" and c[1] == "ERROR" for c in checks)

    if errores:
        if hay_correccion_codigo:
            resultado = "CORREGIDA"
        else:
            resultado = "CONDICIONADA"
    elif observaciones:
        resultado = "APROBADA CON OBSERVACIONES"
    else:
        resultado = "APROBADA"

    # ── Extraer codigo verificado (si aplica) ────────────────────────────
    codigo_verificado = "N/A"
    descripcion_verificada = "N/A"

    tag_start = "---DATOS_CLASIFICACION---"
    tag_end = "---FIN_CLASIFICACION---"
    si = respuesta.find(tag_start)
    ei = respuesta.find(tag_end)
    if si != -1 and ei != -1:
        block = respuesta[si + len(tag_start):ei]
        m_code = re.search(r'SUBPARTIDA_NAC:\s*(\S+)', block)
        if m_code:
            codigo_verificado = m_code.group(1)
        m_desc = re.search(r'SUBPARTIDA_NAC:\s*\S+\s*[—\-]+\s*([^\[\n]+)', block)
        if m_desc:
            descripcion_verificada = m_desc.group(1).strip()

    # ── Construir texto de correcciones ───────────────────────────────────
    correcciones = [c[2] for c in checks if c[1] == "ERROR"]
    correccion_text = "; ".join(correcciones) if correcciones else "NINGUNA"

    # ── Generar bloque SUPERVISION ────────────────────────────────────────
    check_lines = []
    for nombre, estado, mensaje in checks:
        tag = f"CHECK_{nombre.upper()}"
        if estado == "OK":
            check_lines.append(f"{tag}: OK")
        else:
            check_lines.append(f"{tag}: {estado}: {mensaje}")

    dominio = DOMINIOS.get(notebook_id, {})
    nombre_cuaderno = dominio.get("nombre", notebook_id)

    bloque = (
        "---SUPERVISION---\n"
        f"RESULTADO: {resultado}\n"
        f"VERIFICADO_POR: Supervisor General Interno v1.0 (Python — deterministico)\n"
        f"CUADERNO: {nombre_cuaderno}\n"
        f"CODIGO_VERIFICADO: {codigo_verificado}\n"
        f"DESCRIPCION_VERIFICADA: {descripcion_verificada}\n"
        + "\n".join(check_lines) + "\n"
        f"CORRECCION: {correccion_text}\n"
        "---FIN_SUPERVISION---"
    )

    print(f"[SUPERVISOR_INTERNO] Resultado: {resultado} "
          f"({len(errores)} errores, {len(observaciones)} observaciones)")

    return respuesta, bloque
