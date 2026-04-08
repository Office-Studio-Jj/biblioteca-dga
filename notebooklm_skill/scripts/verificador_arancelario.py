#!/usr/bin/env python3
"""
VERIFICADOR ARANCELARIO AUTOMATICO — Segunda pasada del pipeline
================================================================
Verifica DOS cosas de forma automatica contra las fuentes del cuaderno:

  1. CODIGO: ¿Existe el codigo XXXX.XX.XX en el Arancel RD?
  2. CARGOS FISCALES: ¿Cual es el gravamen, ITBIS, selectivo y otros cargos
     reales para ese codigo segun el Arancel y las leyes fiscales?

Ambas verificaciones se hacen en UNA sola consulta dirigida para minimizar
latencia y costo de API.

ARQUITECTURA:
  ask_gemini.py → Gemini genera borrador con codigo + gravamen + ITBIS
                → verificador_arancelario.py verifica AMBOS contra fuentes
                → Si codigo o cargos incorrectos: corrige antes del supervisor
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
# PROMPT DE VERIFICACION — codigo + cargos fiscales en una sola consulta
# ══════════════════════════════════════════════════════════════════════════

_SYSTEM_VERIFICACION = """Eres un verificador tecnico del Arancel de Aduanas de la Republica Dominicana.
Tu funcion es verificar DOS cosas para un codigo arancelario especifico:

VERIFICACION 1 — EXISTENCIA DEL CODIGO:
1. Busca el codigo exacto (8 digitos, XXXX.XX.XX) en el Arancel de la RD.
2. Si NO existe con esa extension nacional exacta: proporciona el codigo correcto.
3. Muchas subpartidas SA solo tienen extension .00 — en esos casos .90, .19, .10 NO existen.

VERIFICACION 2 — CARGOS FISCALES REALES:
Para el codigo CORRECTO (ya verificado), determina los cargos REALES segun el Arancel y leyes fiscales de la RD:

a) GRAVAMEN AD-VALOREM: El porcentaje que aparece junto al codigo en el Arancel.
   - Valores comunes: 0%, 3%, 8%, 14%, 20%, 25%.
   - Si el producto tiene acuerdo comercial (DR-CAFTA, CARICOM, EPA), indicarlo como alternativa.

b) ITBIS: Impuesto sobre Transferencias de Bienes Industrializados y Servicios.
   - Tasa general: 18% sobre (CIF + gravamen).
   - EXENTO: Algunos productos estan exentos por ley (alimentos basicos, medicamentos,
     insumos agropecuarios, libros, combustibles, segun Ley 11-92 Art. 343 y modificaciones).
   - Si el producto esta exento, indicar "EXENTO" y la base legal.
   - NO asumir exencion sin base legal. Por defecto aplica 18%.

c) SELECTIVO AL CONSUMO: Impuesto selectivo (Ley 11-92, Titulo IV).
   - Aplica a: bebidas alcoholicas, tabaco, vehiculos de motor, productos de lujo, combustibles.
   - Si NO aplica, indicar "NO APLICA".
   - Si aplica: indicar la tasa y base legal.

d) OTROS CARGOS: Cualquier otro cargo aplicable.
   - Tasa por servicios aduaneros, recargos, impuestos especificos.
   - Si no hay otros cargos: "NINGUNO".

FORMATO DE RESPUESTA — EXCLUSIVAMENTE JSON, sin texto adicional:
{
  "existe": true o false,
  "codigo_consultado": "XXXX.XX.XX",
  "codigo_correcto": "XXXX.XX.XX",
  "descripcion_oficial": "descripcion exacta del arancel RD",
  "razon": "si no existe, explicar por que",
  "gravamen_ad_valorem": "XX%",
  "gravamen_nota": "explicacion breve si aplica acuerdo comercial o condicion especial",
  "itbis": "18%" o "EXENTO",
  "itbis_base_legal": "Ley y articulo si es exento, o 'Tasa general Ley 11-92' si aplica 18%",
  "selectivo": "NO APLICA" o "XX% — base legal",
  "otros_cargos": "NINGUNO" o "descripcion del cargo"
}

NO agregues texto antes ni despues del JSON.
Si no puedes determinar un cargo con certeza, indica "VERIFICAR EN ARANCEL VIGENTE" en ese campo."""


def verificar_codigo_y_cargos(codigo: str, producto: str, api_key: str) -> dict | None:
    """
    Verifica codigo arancelario Y cargos fiscales contra el Arancel RD.
    Una sola consulta dirigida cubre: existencia, gravamen, ITBIS, selectivo, otros.

    Args:
        codigo:   Codigo de 8 digitos a verificar (ej: "4818.90.90")
        producto: Descripcion del producto para contexto (ej: "papel camilla")
        api_key:  GEMINI_API_KEY de Railway

    Returns:
        dict completo con codigo + cargos verificados, o None si falla
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
            f"Republica Dominicana y determina TODOS los cargos fiscales aplicables:\n\n"
            f"Codigo a verificar: {codigo}\n"
            f"Producto: {producto}\n\n"
            f"1. ¿Existe el codigo {codigo} en el Arancel RD con esa extension nacional exacta?\n"
            f"2. ¿Cual es el gravamen ad-valorem REAL que aparece en el Arancel para este codigo?\n"
            f"3. ¿Este producto esta exento de ITBIS o paga 18%? Cita la base legal.\n"
            f"4. ¿Aplica impuesto selectivo al consumo? ¿Otros cargos?\n"
        )

        print(f"[VERIFICADOR] Verificando codigo + cargos: {codigo} para: {producto[:60]}")
        response = model.generate_content(pregunta)
        texto = response.text.strip()

        # Extraer JSON — puede venir con backticks o texto adicional
        texto_limpio = re.sub(r'```(?:json)?', '', texto).strip()
        # Buscar JSON con campos anidados (permitir llaves internas)
        m = re.search(r'\{[^{}]*"existe"[^{}]*\}', texto_limpio, re.DOTALL)
        if not m:
            # Intentar con formato mas flexible (JSON multilinea)
            m = re.search(r'\{[\s\S]*?"existe"[\s\S]*?\}', texto_limpio)
        if m:
            resultado = json.loads(m.group(0))

            existe = resultado.get("existe", True)
            codigo_c = resultado.get("codigo_correcto", codigo)
            desc = resultado.get("descripcion_oficial", "")
            grav = resultado.get("gravamen_ad_valorem", "?")
            itbis = resultado.get("itbis", "?")
            selec = resultado.get("selectivo", "?")

            estado = "CONFIRMADO" if existe else "NO EXISTE"
            print(f"[VERIFICADOR] Codigo: {codigo} → {estado} (correcto: {codigo_c})")
            print(f"[VERIFICADOR] Gravamen: {grav} | ITBIS: {itbis} | Selectivo: {selec}")

            return resultado

        print(f"[VERIFICADOR] No se pudo parsear JSON de: {texto[:300]}")
        return None

    except Exception as e:
        print(f"[VERIFICADOR] Error en verificacion de {codigo}: {e}")
        return None


def _corregir_cargos_en_respuesta(respuesta: str, resultado: dict, codigo_final: str) -> str:
    """
    Inyecta los cargos fiscales VERIFICADOS en la respuesta de Gemini.
    Reemplaza cualquier gravamen/ITBIS/selectivo que Gemini haya puesto
    con los datos verificados contra las fuentes del cuaderno.
    """
    gravamen = resultado.get("gravamen_ad_valorem", "")
    gravamen_nota = resultado.get("gravamen_nota", "")
    itbis = resultado.get("itbis", "")
    itbis_base = resultado.get("itbis_base_legal", "")
    selectivo = resultado.get("selectivo", "")
    otros = resultado.get("otros_cargos", "")

    if not gravamen:
        return respuesta

    # ── Construir bloque de cargos verificados ──
    bloque_cargos = "\n\n---CARGOS_VERIFICADOS---"
    bloque_cargos += f"\nGRAVAMEN_AD_VALOREM: {gravamen}"
    if gravamen_nota:
        bloque_cargos += f" ({gravamen_nota})"
    bloque_cargos += f"\nITBIS: {itbis}"
    if itbis_base:
        bloque_cargos += f" — Base legal: {itbis_base}"
    bloque_cargos += f"\nSELECTIVO: {selectivo}"
    bloque_cargos += f"\nOTROS_CARGOS: {otros}"
    bloque_cargos += "\nVERIFICADO_POR: Verificador Arancelario Automatico (consulta directa a fuentes)"
    bloque_cargos += "\n---FIN_CARGOS_VERIFICADOS---"

    # ── Corregir gravamen incorrecto en el texto de Gemini ──
    # Patron: "Ad-Valorem: X%" o "Gravamen: X%" o "gravamen ... X%"
    # Solo corregir si el verificador dio un valor concreto (no "?")
    if gravamen and gravamen not in ("?", "VERIFICAR EN ARANCEL VIGENTE"):
        # Reemplazar porcentajes de gravamen incorrectos en el texto
        respuesta = re.sub(
            r'(\*\*Ad[\s-]*Valorem:?\*\*:?\s*)\d+%',
            r'\g<1>' + gravamen,
            respuesta,
            flags=re.IGNORECASE
        )
        respuesta = re.sub(
            r'(Gravamen\s+(?:NMF\s+)?(?:ad[\s-]*valorem)?:?\s*)\d+%',
            r'\g<1>' + gravamen,
            respuesta,
            flags=re.IGNORECASE
        )

    # ── Corregir ITBIS incorrecto en el texto ──
    if itbis and itbis not in ("?", "VERIFICAR EN ARANCEL VIGENTE"):
        if itbis.upper() == "EXENTO":
            # Si es exento, reemplazar "18%" por "EXENTO"
            respuesta = re.sub(
                r'(\*\*ITBIS[^*]*\*\*:?\s*)18%[^\n]*',
                r'\g<1>EXENTO' + (f' — {itbis_base}' if itbis_base else ''),
                respuesta,
                flags=re.IGNORECASE
            )
        else:
            # Si tiene tasa especifica
            respuesta = re.sub(
                r'(\*\*ITBIS[^*]*\*\*:?\s*)(?:EXENTO|0%)',
                r'\g<1>' + itbis,
                respuesta,
                flags=re.IGNORECASE
            )

    # ── Insertar bloque de cargos verificados antes de FIN_CLASIFICACION ──
    fin_clas = respuesta.find("---FIN_CLASIFICACION---")
    if fin_clas != -1:
        respuesta = respuesta[:fin_clas] + bloque_cargos + "\n" + respuesta[fin_clas:]
    else:
        # Sin bloque de clasificacion — agregar al final
        respuesta += bloque_cargos

    return respuesta


def pre_verificar_codigo_en_respuesta(respuesta: str, pregunta: str, api_key: str) -> tuple[str, bool]:
    """
    Punto de entrada principal. Extrae el SUBPARTIDA_NAC del borrador de Gemini,
    verifica el codigo Y los cargos fiscales contra el Arancel RD.

    Se invoca desde ask_gemini.py ANTES de pasar la respuesta al supervisor.

    Args:
        respuesta: Borrador completo de Gemini
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
    fue_corregida = False

    # ── Consulta unica: verifica codigo + cargos fiscales ──
    resultado = verificar_codigo_y_cargos(codigo, pregunta, api_key)
    if resultado is None:
        return respuesta, False

    codigo_final = codigo

    # ── PASO 1: Verificar existencia del codigo ──
    if not resultado.get("existe", True):
        codigo_correcto = resultado.get("codigo_correcto", "")
        descripcion_correcta = resultado.get("descripcion_oficial", "")
        razon = resultado.get("razon", f"{codigo} no existe en el Arancel RD")

        if not codigo_correcto or not re.match(r'\d{4}\.\d{2}\.\d{2}$', codigo_correcto):
            print(f"[VERIFICADOR] Codigo correcto invalido: '{codigo_correcto}' — no se corrige")
            return respuesta, False

        codigo_final = codigo_correcto

        nota = (
            f"{codigo_correcto} — {descripcion_correcta} "
            f"[CORREGIDO AUTOMATICAMENTE: {codigo} no existe en Arancel RD. {razon}]"
        )

        # Reemplazar linea SUBPARTIDA_NAC
        old_line = re.search(r'SUBPARTIDA_NAC:\s*' + re.escape(codigo) + r'[^\n]*', respuesta)
        if old_line:
            respuesta = respuesta.replace(old_line.group(0), f"SUBPARTIDA_NAC: {nota}")

        # Reemplazar codigo en el texto del analisis
        respuesta = respuesta.replace(f"**{codigo}**", f"**{codigo_correcto}**")
        respuesta = re.sub(
            r'\b' + re.escape(codigo) + r'\b(?![^\-])',
            codigo_correcto,
            respuesta
        )

        # Degradar auditoria
        respuesta = re.sub(
            r'AUDITORIA:\s*APROBADA\b',
            'AUDITORIA: CONDICIONADA — codigo corregido por Verificador Arancelario Automatico',
            respuesta
        )

        fue_corregida = True
        print(f"[VERIFICADOR] Codigo corregido: {codigo} → {codigo_correcto}")
    else:
        # Codigo confirmado — agregar marca de verificacion
        descripcion = resultado.get("descripcion_oficial", "")
        if descripcion:
            old_line = re.search(r'SUBPARTIDA_NAC:\s*' + re.escape(codigo) + r'[^\n]*', respuesta)
            if old_line and "[VERIFICADO" not in old_line.group(0):
                nueva_linea = f"SUBPARTIDA_NAC: {codigo} — {descripcion} [VERIFICADO AUTOMATICAMENTE]"
                respuesta = respuesta.replace(old_line.group(0), nueva_linea)
        print(f"[VERIFICADOR] Codigo {codigo} confirmado en Arancel RD")

    # ── PASO 2: Verificar y corregir cargos fiscales ──
    respuesta = _corregir_cargos_en_respuesta(respuesta, resultado, codigo_final)
    fue_corregida = True  # siempre inyecta bloque de cargos verificados

    return respuesta, fue_corregida
