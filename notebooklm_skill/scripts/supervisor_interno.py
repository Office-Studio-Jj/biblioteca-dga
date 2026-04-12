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
import hashlib
import hmac
import json
import os
import time
from typing import Dict, List, Tuple, Optional

try:
    import pdfplumber
    _PDFPLUMBER_DISPONIBLE = True
except ImportError:
    _PDFPLUMBER_DISPONIBLE = False
    print("[SUPERVISOR_INTERNO] pdfplumber no disponible — fuentes PDF deshabilitadas")


# ══════════════════════════════════════════════════════════════════════════
# SECCION -1: CARGA DE FUENTES PDF LOCALES
# Los documentos del cuaderno nomenclatura se extraen UNA VEZ al iniciar.
# El supervisor consulta estos textos directamente — 0% IA.
# ══════════════════════════════════════════════════════════════════════════

_FUENTES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "fuentes_nomenclatura")

# Cache global: {nombre_archivo: texto_completo}
_FUENTES_TEXTO: Dict[str, str] = {}

# Indice de codigos encontrados en PDFs: {codigo_8dig: descripcion}
_CODIGOS_PDF: Dict[str, str] = {}

# Indice de reglas RGI encontradas en PDFs
_REGLAS_RGI: List[str] = []


_FUENTES_CARGADAS = False

# Cache pre-extraido del Arancel (JSON ligero en vez de parsear 633 pags cada vez)
_ARANCEL_CACHE = os.path.join(_FUENTES_DIR, "arancel_cache.json")


def _cargar_fuentes_pdf():
    """
    Carga fuentes del cuaderno nomenclatura:
    1. Arancel 7ma enmienda: desde cache JSON pre-extraido (0.05s vs 100s del PDF)
    2. Demas PDFs: extraccion directa con pdfplumber (11 PDFs ligeros, ~5s)

    Se ejecuta LAZY — solo cuando se necesita, no al importar.
    """
    global _FUENTES_TEXTO, _CODIGOS_PDF, _REGLAS_RGI, _FUENTES_CARGADAS

    if _FUENTES_CARGADAS:
        return

    _FUENTES_CARGADAS = True

    # ── PASO 1: Cargar Arancel desde cache JSON (instantaneo) ──
    if os.path.isfile(_ARANCEL_CACHE):
        try:
            with open(_ARANCEL_CACHE, "r", encoding="utf-8") as f:
                cache = json.load(f)
            codigos_arancel = cache.get("codigos", {})
            _CODIGOS_PDF.update(codigos_arancel)
            print(f"[SUPERVISOR_INTERNO] Arancel cache: {len(codigos_arancel)} codigos "
                  f"({cache.get('paginas', '?')} pags pre-extraidas)")
        except Exception as e:
            print(f"[SUPERVISOR_INTERNO] Error cargando cache Arancel: {e}")
    else:
        print(f"[SUPERVISOR_INTERNO] Cache Arancel no encontrado: {_ARANCEL_CACHE}")

    # ── PASO 2: Cargar demas PDFs con pdfplumber ──
    if not _PDFPLUMBER_DISPONIBLE:
        print("[SUPERVISOR_INTERNO] Sin pdfplumber — fuentes PDF adicionales no cargadas")
        return

    if not os.path.isdir(_FUENTES_DIR):
        return

    # Cargar todos los PDFs EXCEPTO el Arancel grande (ya cargado desde cache)
    archivos = [f for f in os.listdir(_FUENTES_DIR)
                if f.lower().endswith('.pdf')
                and 'arancel 7ma' not in f.lower()]
    if not archivos:
        return

    print(f"[SUPERVISOR_INTERNO] Cargando {len(archivos)} fuentes PDF complementarias...")
    total_paginas = 0

    for archivo in archivos:
        ruta = os.path.join(_FUENTES_DIR, archivo)
        try:
            with pdfplumber.open(ruta) as pdf:
                textos_pagina = []
                for pagina in pdf.pages:
                    try:
                        texto = pagina.extract_text()
                        if texto:
                            textos_pagina.append(texto)
                    except Exception:
                        pass
                texto_completo = "\n".join(textos_pagina)
                _FUENTES_TEXTO[archivo] = texto_completo
                total_paginas += len(pdf.pages)
        except Exception as e:
            print(f"  [ERROR] {archivo}: {e}")

    print(f"[SUPERVISOR_INTERNO] {len(_FUENTES_TEXTO)} PDFs + Arancel cache cargados "
          f"({total_paginas} pags directas + {len(_CODIGOS_PDF)} codigos Arancel)")

    # Indexar codigos adicionales de los PDFs complementarios
    _indexar_codigos_desde_pdfs()
    # Indexar reglas RGI
    _indexar_reglas_rgi()


def _indexar_codigos_desde_pdfs():
    """
    Busca patrones de codigos arancelarios (XXXX.XX.XX o XXXX.XX) en los textos
    y construye un indice rapido para verificacion.
    """
    global _CODIGOS_PDF
    patron_8dig = re.compile(r'(\d{4}\.\d{2}\.\d{2})\s+(.{5,80})')
    patron_6dig = re.compile(r'(\d{4}\.\d{2})\s+(.{5,80})')

    for archivo, texto in _FUENTES_TEXTO.items():
        # Priorizar el Arancel 7ma enmienda (fuente principal de codigos)
        for m in patron_8dig.finditer(texto):
            codigo = m.group(1)
            desc = m.group(2).strip()
            # Limpiar descripcion: quitar numeros sueltos al final (gravamen, etc)
            desc = re.sub(r'\s+\d{1,3}\s*$', '', desc).strip()
            if codigo not in _CODIGOS_PDF:
                _CODIGOS_PDF[codigo] = desc

    print(f"[SUPERVISOR_INTERNO] {len(_CODIGOS_PDF)} codigos arancelarios indexados desde PDFs")


def _indexar_reglas_rgi():
    """Extrae referencias a Reglas Generales de Interpretacion de los PDFs."""
    global _REGLAS_RGI
    patron_rgi = re.compile(r'(?:Regla\s+(?:General\s+)?(?:de\s+Interpretaci[oó]n\s+)?(?:No?\.?\s*)?(\d+[a-z]?))', re.IGNORECASE)

    for archivo, texto in _FUENTES_TEXTO.items():
        if 'regla' in archivo.lower() or 'interpretacion' in archivo.lower():
            for m in patron_rgi.finditer(texto):
                regla = f"RGI {m.group(1)}"
                if regla not in _REGLAS_RGI:
                    _REGLAS_RGI.append(regla)

    if _REGLAS_RGI:
        print(f"[SUPERVISOR_INTERNO] {len(_REGLAS_RGI)} reglas RGI indexadas")


def buscar_en_fuentes(termino: str, max_resultados: int = 5) -> List[Dict[str, str]]:
    """
    Busca un termino en TODAS las fuentes PDF cargadas.
    Retorna lista de coincidencias con contexto.
    """
    _cargar_fuentes_pdf()  # Lazy load
    resultados = []
    termino_lower = termino.lower()

    for archivo, texto in _FUENTES_TEXTO.items():
        texto_lower = texto.lower()
        pos = 0
        while len(resultados) < max_resultados:
            idx = texto_lower.find(termino_lower, pos)
            if idx == -1:
                break
            # Extraer contexto: 100 chars antes y despues
            inicio = max(0, idx - 100)
            fin = min(len(texto), idx + len(termino) + 100)
            contexto = texto[inicio:fin].replace('\n', ' ').strip()
            resultados.append({"fuente": archivo, "contexto": contexto})
            pos = idx + len(termino)

    return resultados[:max_resultados]


def verificar_codigo_en_fuentes(codigo: str) -> Tuple[bool, str]:
    """
    Verifica si un codigo arancelario existe en las fuentes PDF locales.
    100% Python, 0% IA.
    """
    _cargar_fuentes_pdf()  # Lazy load
    # Buscar codigo exacto en el indice
    if codigo in _CODIGOS_PDF:
        return True, f"{codigo} ENCONTRADO en fuentes: {_CODIGOS_PDF[codigo]}"

    # Buscar la subpartida SA (6 digitos)
    partes = codigo.split(".")
    if len(partes) == 3:
        sub_sa = f"{partes[0]}.{partes[1]}"
        # Buscar cualquier extension de esta subpartida
        extensiones = {c: d for c, d in _CODIGOS_PDF.items() if c.startswith(sub_sa)}
        if extensiones:
            ext_list = "; ".join(f"{c} = {d}" for c, d in list(extensiones.items())[:5])
            return False, (f"{codigo} NO encontrado en fuentes PDF. "
                          f"Subpartida {sub_sa} tiene estas extensiones: {ext_list}")

    # Buscar directamente en texto de PDFs (por si el indice no lo capturo)
    hits = buscar_en_fuentes(codigo, max_resultados=2)
    if hits:
        ctx = hits[0]["contexto"][:80]
        return True, f"{codigo} encontrado en {hits[0]['fuente']}: {ctx}"

    return False, f"{codigo} NO encontrado en ninguna fuente PDF local"


# ══════════════════════════════════════════════════════════════════════════
# SECCION 0: SEGURIDAD — CANDADO CRIPTOGRAFICO DEL SUPERVISOR
# Ningún agente externo (Gemini, otro LLM, inyección) puede:
#   - Generar bloques SUPERVISION validos (requiere firma HMAC)
#   - Inyectar bloques falsos (se sanitizan antes de procesar)
#   - Modificar los datos de referencia (hash de integridad)
#   - Suplantar la identidad del supervisor (firma unica por instancia)
# ══════════════════════════════════════════════════════════════════════════

# Clave secreta de firma — configurar en Railway como SUPERVISOR_SECRET
_SECRET_SEED = os.environ.get("SUPERVISOR_SECRET", "DGA_SGI_2026_CANDADO_MAESTRO")
_SIGNING_KEY = hashlib.sha256((_SECRET_SEED + "_hmac_key").encode()).digest()

# Hash de integridad — se calcula al cargar el modulo
_INTEGRITY_HASH_AT_LOAD = None


def _calcular_hash_integridad():
    """Calcula SHA-256 de todas las bases de datos de referencia."""
    payload = json.dumps({
        "c": CODIGOS_VERIFICADOS_RD,
        "l": {k: v["vigente"] for k, v in LEYES_RD.items()},
        "d": list(DOMINIOS.keys()),
        "i": [r["capitulo_correcto"] for r in INCOHERENCIAS_CONOCIDAS],
    }, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _verificar_integridad():
    """Verifica que los datos de referencia no han sido manipulados en runtime."""
    global _INTEGRITY_HASH_AT_LOAD
    actual = _calcular_hash_integridad()
    if _INTEGRITY_HASH_AT_LOAD is None:
        _INTEGRITY_HASH_AT_LOAD = actual
        print(f"[SEGURIDAD] Hash de integridad registrado: {actual[:16]}...")
        return True
    if actual != _INTEGRITY_HASH_AT_LOAD:
        print(f"[SEGURIDAD] *** ALERTA: DATOS DE REFERENCIA MANIPULADOS ***")
        print(f"[SEGURIDAD] Esperado: {_INTEGRITY_HASH_AT_LOAD[:16]}...")
        print(f"[SEGURIDAD] Actual:   {actual[:16]}...")
        return False
    return True


def _firmar_bloque(contenido: str, ts: str) -> str:
    """Genera firma HMAC-SHA256 del bloque de supervision."""
    msg = (contenido + "|" + ts).encode("utf-8")
    return hmac.new(_SIGNING_KEY, msg, hashlib.sha256).hexdigest()[:24]


def verificar_firma_supervision(bloque_texto: str) -> bool:
    """
    Verifica que un bloque SUPERVISION fue generado por ESTE modulo.
    Uso: llamar desde ask_gemini.py o server.py para confirmar autenticidad.
    """
    m_firma = re.search(r'FIRMA:\s*([a-f0-9]+)', bloque_texto)
    m_ts = re.search(r'TIMESTAMP:\s*(\d+)', bloque_texto)
    if not m_firma or not m_ts:
        return False
    # Reconstruir contenido sin la linea FIRMA para verificar
    contenido_sin_firma = re.sub(r'\nFIRMA:[^\n]*', '', bloque_texto)
    esperada = _firmar_bloque(contenido_sin_firma, m_ts.group(1))
    return hmac.compare_digest(m_firma.group(1), esperada)


def _sanitizar_respuesta_gemini(respuesta: str) -> Tuple[str, List[str]]:
    """
    BARRERA DE SEGURIDAD #1: Limpia la respuesta de Gemini ANTES de procesarla.
    Elimina cualquier intento de inyeccion, suplantacion o manipulacion.

    Returns:
        (respuesta_limpia, alertas_de_seguridad)
    """
    alertas = []

    # 1. BLOQUEAR bloques ---SUPERVISION--- inyectados por Gemini
    count = respuesta.count('---SUPERVISION---')
    if count > 0:
        alertas.append(f"INYECCION BLOQUEADA: {count} bloque(s) SUPERVISION falso(s) eliminado(s)")
        while '---SUPERVISION---' in respuesta:
            si = respuesta.find('---SUPERVISION---')
            ei = respuesta.find('---FIN_SUPERVISION---')
            if ei != -1:
                respuesta = respuesta[:si].rstrip() + respuesta[ei + len('---FIN_SUPERVISION---'):]
            else:
                respuesta = respuesta[:si].rstrip()

    # 2. BLOQUEAR lineas FIRMA: (solo el supervisor puede firmar)
    if 'FIRMA:' in respuesta and '---DATOS_CLASIFICACION---' not in respuesta.split('FIRMA:')[0][-50:]:
        firmas = re.findall(r'FIRMA:\s*[a-f0-9]+', respuesta)
        if firmas:
            alertas.append(f"INYECCION BLOQUEADA: {len(firmas)} FIRMA(s) falsa(s) eliminada(s)")
            respuesta = re.sub(r'FIRMA:\s*[a-f0-9]+', '', respuesta)

    # 3. BLOQUEAR lineas VERIFICADO_POR: (suplantacion del supervisor)
    if 'VERIFICADO_POR:' in respuesta:
        alertas.append("SUPLANTACION BLOQUEADA: VERIFICADO_POR falso eliminado")
        respuesta = re.sub(r'VERIFICADO_POR:[^\n]*', '', respuesta)

    # 4. BLOQUEAR lineas TIMESTAMP: fuera de contexto
    ts_fuera = re.findall(r'TIMESTAMP:\s*\d+', respuesta)
    if ts_fuera:
        alertas.append(f"INYECCION BLOQUEADA: {len(ts_fuera)} TIMESTAMP(s) falso(s) eliminado(s)")
        respuesta = re.sub(r'TIMESTAMP:\s*\d+', '', respuesta)

    # 5. DETECTAR patrones de prompt injection / manipulacion
    patrones_hostiles = [
        (r'ignor(?:a|ar|e)\s+(?:el\s+)?supervisor', "intento de desactivar supervisor"),
        (r'override\s+validat', "intento de override de validacion"),
        (r'bypass\s+(?:the\s+)?check', "intento de bypass de checks"),
        (r'skip\s+(?:the\s+)?supervis', "intento de saltar supervisor"),
        (r'desactivar?\s+(?:el\s+)?supervisor', "intento de desactivar supervisor"),
        (r'deshabilitar?\s+(?:el\s+)?supervisor', "intento de deshabilitar supervisor"),
        (r'no\s+apliqu(?:e|es|ar)\s+(?:la\s+)?validaci[oó]n', "intento de evadir validacion"),
        (r'RESULTADO:\s*APROBADA', "intento de pre-aprobar resultado"),
    ]
    for patron, desc in patrones_hostiles:
        if re.search(patron, respuesta, re.IGNORECASE):
            alertas.append(f"PROMPT INJECTION: {desc}")

    return respuesta.strip(), alertas


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
    # ── Capitulo 48: Papel y carton — verificado en Arancel impreso RD ───
    # UNICA extension nacional valida para todas estas subpartidas: "00"
    # Error comun de Gemini: genera .90 o .19 en lugar de .00
    "4818.10": {"00": "Papel higienico"},
    "4818.20": {"00": "Panuelos, toallitas de desmaquillar, toallas, sabanas y articulos similares para uso domestico, higienico o de tocador"},
    "4818.30": {"00": "Manteles y servilletas"},
    "4818.50": {"00": "Prendas y complementos (accesorios), de vestir"},
    "4818.90": {"00": "Los demas"},  # papel camilla, papel sábana, etc.
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
    {
        "productos": ["papel camilla", "papel sabana", "papel medico", "rollo medico",
                      "papel examen", "papel camion", "sabana desechable"],
        "capitulos_incorrectos": ["9619", "4818.90.90", "4818.90.19", "4818.90.10"],
        "capitulo_correcto": "4818.90.00",
        "mensaje": "Papel camilla y papeles similares de uso medico/sanitario → "
                   "4818.90.00 (Los demas). "
                   "NUNCA 4818.90.90 ni 4818.90.19 — NO EXISTEN en el Arancel RD. "
                   "La unica extension valida bajo 4818.90 es .00",
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

    # Si la subpartida SA no esta en nuestra base hardcoded, intentar con PDFs
    if sub_sa not in CODIGOS_VERIFICADOS_RD:
        # Consultar fuentes PDF locales antes de rendirse
        if _CODIGOS_PDF:
            existe_pdf, msg_pdf = verificar_codigo_en_fuentes(codigo)
            if existe_pdf:
                return respuesta, "OK", f"{codigo} verificado via fuentes PDF: {msg_pdf}"
            else:
                return (respuesta, "OBSERVACION",
                        f"{msg_pdf} — requiere verificacion manual en Arancel impreso")
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


def _check_fuentes_pdf(respuesta: str, pregunta: str, notebook_id: str) -> Tuple[str, str]:
    """
    Valida la respuesta contra las fuentes PDF locales del cuaderno nomenclatura.
    Solo aplica al cuaderno de nomenclaturas.
    100% Python — busca coincidencias textuales en los PDFs extraidos.
    """
    if notebook_id != "biblioteca-de-nomenclaturas":
        return "OK", "Check PDF: solo aplica a nomenclaturas"

    _cargar_fuentes_pdf()  # Lazy load

    if not _FUENTES_TEXTO:
        return "OBSERVACION", "Fuentes PDF no cargadas — verificacion limitada"

    # Extraer codigo del bloque de clasificacion si existe
    si = respuesta.find("---DATOS_CLASIFICACION---")
    ei = respuesta.find("---FIN_CLASIFICACION---")
    if si != -1 and ei != -1:
        bloque = respuesta[si:ei]
        m_code = re.search(r'SUBPARTIDA_NAC:\s*(\d{4}\.\d{2}\.\d{2})', bloque)
        if m_code:
            codigo = m_code.group(1)
            existe, msg = verificar_codigo_en_fuentes(codigo)
            if existe:
                return "OK", f"Fuentes PDF: {msg}"
            else:
                return "OBSERVACION", f"Fuentes PDF: {msg}"

    # Verificar que la respuesta menciona conceptos presentes en las fuentes
    pregunta_lower = pregunta.lower()
    # Buscar terminos clave de la pregunta en las fuentes
    terminos = re.findall(r'\b[a-záéíóúñ]{4,}\b', pregunta_lower)
    terminos_relevantes = [t for t in terminos if t not in (
        "cual", "como", "donde", "para", "este", "esta", "puede", "tiene",
        "hola", "quiero", "necesito", "clasificar", "consultar", "favor",
    )]

    hits_fuente = 0
    for termino in terminos_relevantes[:5]:
        resultados = buscar_en_fuentes(termino, max_resultados=1)
        if resultados:
            hits_fuente += 1

    if hits_fuente > 0:
        return "OK", f"Fuentes PDF: {hits_fuente}/{min(len(terminos_relevantes), 5)} terminos encontrados en documentos locales"

    return "OK", "Fuentes PDF: sin terminos especificos para validar"


# ══════════════════════════════════════════════════════════════════════════
# SECCION 3: MOTOR PRINCIPAL — PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════════════════

def supervisar(pregunta: str, notebook_id: str, respuesta_gemini: str) -> Tuple[str, str]:
    """
    PUNTO DE ENTRADA PRINCIPAL del Supervisor General Interno.

    PROTOCOLO DE SEGURIDAD:
      1. Verificar integridad de datos de referencia (anti-tampering)
      2. Sanitizar respuesta de Gemini (anti-inyeccion)
      3. Ejecutar bateria de validaciones
      4. Firmar bloque de supervision con HMAC-SHA256 (anti-falsificacion)

    Args:
        pregunta:         Consulta original del usuario
        notebook_id:      ID del cuaderno consultado
        respuesta_gemini: Respuesta bruta generada por Gemini (borrador)

    Returns:
        Tupla (respuesta_corregida, bloque_supervision_firmado)
    """
    print(f"[SUPERVISOR_INTERNO] Validando respuesta para: {notebook_id}")

    # ══ SEGURIDAD PASO 1: Verificar integridad de datos de referencia ════
    if not _verificar_integridad():
        bloque_error = (
            "---SUPERVISION---\n"
            "RESULTADO: BLOQUEADO — INTEGRIDAD COMPROMETIDA\n"
            "VERIFICADO_POR: Supervisor General Interno v2.0 (ALERTA DE SEGURIDAD)\n"
            "CUADERNO: " + notebook_id + "\n"
            "CHECK_SEGURIDAD: ERROR: Datos de referencia manipulados en runtime\n"
            "CORRECCION: Reiniciar el servidor para restaurar integridad\n"
            "---FIN_SUPERVISION---"
        )
        print("[SEGURIDAD] *** OPERACION BLOQUEADA: integridad comprometida ***")
        return respuesta_gemini, bloque_error

    # ══ SEGURIDAD PASO 2: Sanitizar respuesta de Gemini ══════════════════
    respuesta, alertas_seguridad = _sanitizar_respuesta_gemini(respuesta_gemini)
    for alerta in alertas_seguridad:
        print(f"[SEGURIDAD] {alerta}")

    # ══ VALIDACION: Ejecutar bateria de checks ═══════════════════════════
    checks: List[Tuple[str, str, str]] = []

    # Check 1: Codigo arancelario
    respuesta, st_cod, msg_cod = _check_codigo_arancelario(respuesta)
    checks.append(("Codigo", st_cod, msg_cod))

    # Check 2: Incoherencia producto-capitulo
    st_inc, msg_inc = _check_incoherencia_producto(respuesta, pregunta)
    checks.append(("Capitulo", st_inc, msg_inc))

    # Check 3: Dominio tematico
    st_dom, msg_dom = _check_dominio(respuesta, notebook_id)
    checks.append(("Dominio", st_dom, msg_dom))

    # Check 4: Leyes citadas
    st_ley, msg_ley = _check_leyes_citadas(respuesta, notebook_id)
    checks.append(("Leyes", st_ley, msg_ley))

    # Check 5: Coherencia
    st_coh, msg_coh = _check_coherencia(respuesta, pregunta)
    checks.append(("Coherencia", st_coh, msg_coh))

    # Check 6: Fuente
    st_fue, msg_fue = _check_fuente(respuesta, notebook_id)
    checks.append(("Fuente", st_fue, msg_fue))

    # Check 7: Alertas de seguridad (si se detectaron inyecciones)
    if alertas_seguridad:
        checks.append(("Seguridad", "OBSERVACION",
                        f"{len(alertas_seguridad)} inyeccion(es) bloqueada(s)"))
    else:
        checks.append(("Seguridad", "OK", "Sin intentos de inyeccion"))

    # Check 8: Validacion contra fuentes PDF locales (nomenclatura)
    st_pdf, msg_pdf = _check_fuentes_pdf(respuesta, pregunta, notebook_id)
    checks.append(("FuentesPDF", st_pdf, msg_pdf))

    # ── Determinar resultado ─────────────────────────────────────────────
    errores = [c for c in checks if c[1] == "ERROR"]
    observaciones = [c for c in checks if c[1] == "OBSERVACION"]
    hay_correccion_codigo = any(c[0] == "Codigo" and c[1] == "ERROR" for c in checks)

    if errores:
        resultado = "CORREGIDA" if hay_correccion_codigo else "CONDICIONADA"
    elif observaciones:
        resultado = "APROBADA CON OBSERVACIONES"
    else:
        resultado = "APROBADA"

    # ── Extraer codigo verificado ────────────────────────────────────────
    codigo_verificado = "N/A"
    descripcion_verificada = "N/A"
    si = respuesta.find("---DATOS_CLASIFICACION---")
    ei = respuesta.find("---FIN_CLASIFICACION---")
    if si != -1 and ei != -1:
        block = respuesta[si + len("---DATOS_CLASIFICACION---"):ei]
        m_code = re.search(r'SUBPARTIDA_NAC:\s*(\S+)', block)
        if m_code:
            codigo_verificado = m_code.group(1)
        m_desc = re.search(r'SUBPARTIDA_NAC:\s*\S+\s*[—\-]+\s*([^\[\n]+)', block)
        if m_desc:
            descripcion_verificada = m_desc.group(1).strip()

    # ── Construir correcciones ───────────────────────────────────────────
    correcciones = [c[2] for c in checks if c[1] == "ERROR"]
    correccion_text = "; ".join(correcciones) if correcciones else "NINGUNA"

    # ── Construir check lines ────────────────────────────────────────────
    check_lines = []
    for nombre, estado, mensaje in checks:
        tag = f"CHECK_{nombre.upper()}"
        if estado == "OK":
            check_lines.append(f"{tag}: OK")
        else:
            check_lines.append(f"{tag}: {estado}: {mensaje}")

    dominio = DOMINIOS.get(notebook_id, {})
    nombre_cuaderno = dominio.get("nombre", notebook_id)
    ts = str(int(time.time()))

    # ══ SEGURIDAD PASO 3: Generar bloque firmado ═════════════════════════
    # El bloque se construye SIN firma, se firma, y se agrega la firma
    bloque_sin_firma = (
        "---SUPERVISION---\n"
        f"RESULTADO: {resultado}\n"
        f"VERIFICADO_POR: Supervisor General Interno v2.0 (Python — deterministico)\n"
        f"CUADERNO: {nombre_cuaderno}\n"
        f"CODIGO_VERIFICADO: {codigo_verificado}\n"
        f"DESCRIPCION_VERIFICADA: {descripcion_verificada}\n"
        + "\n".join(check_lines) + "\n"
        f"CORRECCION: {correccion_text}\n"
        f"TIMESTAMP: {ts}\n"
        "---FIN_SUPERVISION---"
    )

    firma = _firmar_bloque(bloque_sin_firma, ts)

    bloque_firmado = (
        "---SUPERVISION---\n"
        f"RESULTADO: {resultado}\n"
        f"VERIFICADO_POR: Supervisor General Interno v2.0 (Python — deterministico)\n"
        f"CUADERNO: {nombre_cuaderno}\n"
        f"CODIGO_VERIFICADO: {codigo_verificado}\n"
        f"DESCRIPCION_VERIFICADA: {descripcion_verificada}\n"
        + "\n".join(check_lines) + "\n"
        f"CORRECCION: {correccion_text}\n"
        f"TIMESTAMP: {ts}\n"
        f"FIRMA: {firma}\n"
        "---FIN_SUPERVISION---"
    )

    print(f"[SUPERVISOR_INTERNO] Resultado: {resultado} "
          f"({len(errores)} errores, {len(observaciones)} obs) "
          f"Firma: {firma[:8]}...")

    return respuesta, bloque_firmado


# ══════════════════════════════════════════════════════════════════════════
# SECCION 4: INICIALIZACION DE SEGURIDAD
# Se ejecuta al importar el modulo — registra el hash de integridad
# ══════════════════════════════════════════════════════════════════════════
_INTEGRITY_HASH_AT_LOAD = _calcular_hash_integridad()
print(f"[SUPERVISOR_INTERNO] Modulo cargado. Integridad: {_INTEGRITY_HASH_AT_LOAD[:16]}...")
# Fuentes PDF se cargan LAZY — solo cuando se necesitan (no al importar)
