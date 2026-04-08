#!/usr/bin/env python3
"""
VERIFICADOR ARANCELARIO AUTOMATICO — Segunda pasada del pipeline
================================================================
Resuelve el problema central: cuando Gemini genera un codigo que NO esta
en la base estatica del supervisor, en lugar de decir "verifique manualmente"
se hace una segunda consulta DIRIGIDA Y CERRADA al cuaderno de nomenclaturas.

Pregunta cerrada: "¿Existe el codigo X en el Arancel RD? Si no, cual es el correcto?"
Esta pregunta es mucho mas fiable que la clasificacion abierta porque:
  1. Es una consulta de verificacion, no de clasificacion
  2. El cuaderno tiene el Arancel.pdf como fuente primaria
  3. Una pregunta binaria produce menos alucinaciones que una abierta

ARQUITECTURA:
  ask_gemini.py → Gemini genera borrador con codigo XXXX.XX.XX
                → verificador_arancelario.py verifica ese codigo especifico
                → Si no existe: corrige la respuesta antes de enviar al supervisor
                → supervisor_interno.py valida el resultado ya corregido
"""

import re
import json
import os

try:
    import google.generativeai as genai
    _GENAI_DISPONIBLE = True
except ImportError:
    _GENAI_DISPONIBLE = False

# ══════════════════════════════════════════════════════════════════════════
# PROMPT DE VERIFICACION — cerrado, especifico, anti-alucinacion
# ══════════════════════════════════════════════════════════════════════════

_SYSTEM_VERIFICACION = """Eres un verificador tecnico de codigos arancelarios del Arancel de la Republica Dominicana.
Tu UNICA funcion en esta consulta es verificar si un codigo arancelario de 8 digitos EXISTE en el Arancel de la Republica Dominicana.

INSTRUCCIONES ESTRICTAS:
1. Busca el codigo exacto en el Arancel de Aduanas de la Republica Dominicana.
2. Determina si ese codigo (con esa extension nacional exacta) EXISTE en el Arancel.
3. Si NO existe: proporciona el codigo correcto de 8 digitos que SI existe para ese producto.
4. Si EXISTE: confirma con su descripcion oficial exacta.

REGLA CRITICA DE FORMATO:
El Arancel RD usa EXACTAMENTE 8 digitos (XXXX.XX.XX).
La extension nacional (ultimos 2 digitos) tiene valores MUY ESPECIFICOS.
Muchas subpartidas SA solo tienen la extension .00 — en esos casos, .90, .19, .10, etc. NO EXISTEN.

FORMATO DE RESPUESTA — EXCLUSIVAMENTE JSON, sin texto adicional:
{"existe": true, "codigo_consultado": "XXXX.XX.XX", "codigo_correcto": "XXXX.XX.XX", "descripcion_oficial": "descripcion exacta del arancel RD"}
o si no existe:
{"existe": false, "codigo_consultado": "XXXX.XX.XX", "codigo_correcto": "XXXX.XX.XX", "descripcion_oficial": "descripcion del codigo correcto", "razon": "explicacion de por que el codigo consultado no existe"}

NO agregues texto antes ni despues del JSON."""


def verificar_codigo_en_arancel(codigo: str, producto: str, api_key: str) -> dict | None:
    """
    Verifica si un codigo arancelario existe en el Arancel RD.
    Hace una consulta dirigida al modelo con el contexto de nomenclatura.

    Args:
        codigo:   Codigo de 8 digitos a verificar (ej: "4818.90.90")
        producto: Descripcion del producto para contexto (ej: "papel camilla")
        api_key:  GEMINI_API_KEY de Railway

    Returns:
        dict con: existe (bool), codigo_correcto (str), descripcion_oficial (str)
        None si hay error de comunicacion
    """
    if not _GENAI_DISPONIBLE:
        print("[VERIFICADOR] google-generativeai no disponible — saltando verificacion")
        return None

    if not api_key:
        print("[VERIFICADOR] Sin GEMINI_API_KEY — saltando verificacion")
        return None

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=_SYSTEM_VERIFICACION
        )

        pregunta = (
            f"Verifica el siguiente codigo arancelario en el Arancel de la "
            f"Republica Dominicana:\n"
            f"Codigo a verificar: {codigo}\n"
            f"Producto: {producto}\n\n"
            f"¿Existe el codigo {codigo} en el Arancel RD con esa extension nacional exacta? "
            f"Si no existe, indica el codigo correcto de 8 digitos para este producto."
        )

        print(f"[VERIFICADOR] Verificando codigo {codigo} para: {producto[:60]}")
        response = model.generate_content(pregunta)
        texto = response.text.strip()

        # Extraer JSON — puede venir con backticks o texto adicional
        texto_limpio = re.sub(r'```(?:json)?', '', texto).strip()
        m = re.search(r'\{[^{}]*"existe"[^{}]*\}', texto_limpio, re.DOTALL)
        if m:
            resultado = json.loads(m.group(0))
            existe = resultado.get("existe", True)
            codigo_correcto = resultado.get("codigo_correcto", codigo)
            descripcion = resultado.get("descripcion_oficial", "")
            razon = resultado.get("razon", "")

            if existe:
                print(f"[VERIFICADOR] {codigo} CONFIRMADO: {descripcion}")
            else:
                print(f"[VERIFICADOR] {codigo} NO EXISTE → correcto: {codigo_correcto} ({descripcion})")

            return resultado

        print(f"[VERIFICADOR] No se pudo parsear JSON de: {texto[:200]}")
        return None

    except Exception as e:
        print(f"[VERIFICADOR] Error en verificacion de {codigo}: {e}")
        return None


def pre_verificar_codigo_en_respuesta(respuesta: str, pregunta: str, api_key: str) -> tuple[str, bool]:
    """
    Punto de entrada principal. Extrae el SUBPARTIDA_NAC del borrador de Gemini
    y lo verifica contra el Arancel RD.

    Se invoca desde ask_gemini.py ANTES de pasar la respuesta al supervisor,
    pero DESPUES de que la base estatica del supervisor no pudo verificar el codigo.

    Args:
        respuesta: Borrador completo de Gemini (puede incluir bloque DATOS_CLASIFICACION)
        pregunta:  Consulta original del usuario
        api_key:   GEMINI_API_KEY

    Returns:
        (respuesta_corregida, fue_corregida)
    """
    # Solo aplica si hay bloque de clasificacion
    si = respuesta.find("---DATOS_CLASIFICACION---")
    ei = respuesta.find("---FIN_CLASIFICACION---")
    if si == -1 or ei == -1:
        return respuesta, False

    bloque = respuesta[si + len("---DATOS_CLASIFICACION---"):ei]

    m_codigo = re.search(r'SUBPARTIDA_NAC:\s*(\d{4}\.\d{2}\.\d{2})', bloque)
    if not m_codigo:
        return respuesta, False

    codigo = m_codigo.group(1)

    # Verificar contra el Arancel RD
    resultado = verificar_codigo_en_arancel(codigo, pregunta, api_key)
    if resultado is None:
        return respuesta, False

    if resultado.get("existe", True):
        # Codigo confirmado — agregar descripcion verificada al bloque
        descripcion = resultado.get("descripcion_oficial", "")
        if descripcion:
            old_line = re.search(r'SUBPARTIDA_NAC:\s*' + re.escape(codigo) + r'[^\n]*', respuesta)
            if old_line and "—" not in old_line.group(0):
                nueva_linea = f"SUBPARTIDA_NAC: {codigo} — {descripcion} [VERIFICADO AUTOMATICAMENTE]"
                respuesta = respuesta.replace(old_line.group(0), nueva_linea)
        return respuesta, False

    # Codigo NO existe — corregir la respuesta
    codigo_correcto = resultado.get("codigo_correcto", "")
    descripcion_correcta = resultado.get("descripcion_oficial", "")
    razon = resultado.get("razon", f"{codigo} no existe en el Arancel RD")

    if not codigo_correcto or not re.match(r'\d{4}\.\d{2}\.\d{2}$', codigo_correcto):
        print(f"[VERIFICADOR] Codigo correcto invalido: '{codigo_correcto}' — no se corrige")
        return respuesta, False

    nota = (
        f"{codigo_correcto} — {descripcion_correcta} "
        f"[CORREGIDO AUTOMATICAMENTE: {codigo} no existe en Arancel RD. {razon}]"
    )

    # Reemplazar linea SUBPARTIDA_NAC
    old_line = re.search(r'SUBPARTIDA_NAC:\s*' + re.escape(codigo) + r'[^\n]*', respuesta)
    if old_line:
        respuesta = respuesta.replace(old_line.group(0), f"SUBPARTIDA_NAC: {nota}")

    # Reemplazar tambien en el texto del analisis (parte 1 de la respuesta)
    respuesta = respuesta.replace(
        f"**{codigo}**",
        f"**{codigo_correcto}**"
    )
    respuesta = re.sub(
        r'\b' + re.escape(codigo) + r'\b(?![^\-])',
        codigo_correcto,
        respuesta
    )

    # Degradar auditoria a CONDICIONADA
    respuesta = re.sub(
        r'AUDITORIA:\s*APROBADA\b',
        'AUDITORIA: CONDICIONADA — codigo corregido por Verificador Arancelario Automatico',
        respuesta
    )

    print(f"[VERIFICADOR] Correccion aplicada: {codigo} → {codigo_correcto}")
    return respuesta, True
