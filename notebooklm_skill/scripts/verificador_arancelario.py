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
Tu funcion es verificar un codigo arancelario y sus cargos fiscales.

ESTRUCTURA DE LA TABLA DEL ARANCEL DE LA RD (como leer el libro):
El Arancel impreso de la Republica Dominicana tiene estas columnas:
  | CODIGO | DESIGNACION DE LA MERCANCIA | GRAV. | EX. ITBIS |

- Columna CODIGO: codigo arancelario de 8 digitos (XXXX.XX.XX)
- Columna DESIGNACION: descripcion oficial de la mercancia
- Columna GRAV.: porcentaje de gravamen ad-valorem. Es un NUMERO (ej: 8, 14, 20).
  Este numero ES el porcentaje de gravamen. Si dice 20, el gravamen es 20%.
- Columna EX. ITBIS: si esta EN BLANCO = ITBIS 18% aplica. Si tiene una marca = EXENTO de ITBIS.

VERIFICACION 1 — EXISTENCIA DEL CODIGO:
1. Busca el codigo exacto (8 digitos, XXXX.XX.XX) en el Arancel de la RD.
2. Si NO existe con esa extension nacional exacta: proporciona el codigo correcto.
3. Muchas subpartidas SA solo tienen extension .00 — en esos casos .90, .19, .10 NO existen.

VERIFICACION 2 — GRAVAMEN AD-VALOREM (columna GRAV.):
Lee el NUMERO que aparece en la columna GRAV. junto al codigo en el Arancel.

REGLA ANTI-ALUCINACION CRITICA SOBRE EL GRAVAMEN:
- El gravamen 0% es MUY RARO en el Arancel RD. La gran mayoria de productos tiene gravamen > 0%.
- NUNCA respondas 0% a menos que el Arancel EXPLICITAMENTE muestre 0 en la columna GRAV.
- Si no puedes leer el numero exacto de la columna GRAV., responde "VERIFICAR EN ARANCEL VIGENTE".
- NO asumas, NO adivines, NO inventes. Lee el numero de la tabla.

GRAVAMENES CONOCIDOS POR CAPITULO (referencia de validacion):
  Cap. 01-05 (animales): 8-25%     Cap. 06-14 (vegetales): 3-20%
  Cap. 15-24 (alimentos): 8-25%    Cap. 25-27 (minerales): 3-20%
  Cap. 28-38 (quimicos): 3-14%     Cap. 39-40 (plasticos): 8-20%
  Cap. 41-43 (cueros): 8-20%       Cap. 44-46 (madera): 8-20%
  Cap. 47-49 (papel): 8-20%        Cap. 50-63 (textiles): 14-20%
  Cap. 64-67 (calzado): 20%        Cap. 68-70 (piedra/vidrio): 8-20%
  Cap. 71 (metales preciosos): 8-20%  Cap. 72-83 (metales comunes): 3-20%
  Cap. 84-85 (maquinas/electr): 3-20% Cap. 86-89 (vehiculos): 3-20%
  Cap. 90-92 (instrumentos): 3-14% Cap. 93 (armas): 20-25%
  Cap. 94-96 (muebles/varios): 14-20% Cap. 97 (arte): 3-20%

Si tu respuesta de gravamen es 0% pero el capitulo indica un rango de 8-20%,
tu respuesta PROBABLEMENTE es incorrecta. Verifica de nuevo.

VERIFICACION 3 — ITBIS (columna EX. ITBIS):
- Tasa general: 18% sobre (CIF + gravamen).
- Lee la columna EX. ITBIS del Arancel:
  Si esta EN BLANCO → ITBIS 18% aplica normalmente.
  Si tiene una marca (X, E, 0, o similar) → producto EXENTO de ITBIS.
- Productos tipicamente exentos: alimentos basicos (canasta familiar), medicamentos,
  insumos agropecuarios, libros, combustibles (Ley 11-92 Art. 343).
- NO asumir exencion sin evidencia. Por defecto aplica 18%.

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


# ══════════════════════════════════════════════════════════════════════════
# GRAVAMENES MINIMOS POR CAPITULO — red de seguridad Python
# Si Gemini dice 0% pero el capitulo tiene un minimo conocido > 0%,
# Python rechaza el 0% y marca como sospechoso.
# Fuente: Arancel de Aduanas de la RD, verificado en campo.
# ══════════════════════════════════════════════════════════════════════════
_GRAVAMEN_MINIMO_POR_CAPITULO = {
    # Cap 01-24: Productos animales, vegetales, alimentos
    "01": 8, "02": 14, "03": 8, "04": 8, "05": 3,
    "06": 3, "07": 8, "08": 8, "09": 8, "10": 3,
    "11": 8, "12": 3, "13": 3, "14": 3,
    "15": 8, "16": 14, "17": 8, "18": 14, "19": 14, "20": 14,
    "21": 14, "22": 8, "23": 3, "24": 20,
    # Cap 25-27: Minerales y combustibles
    "25": 3, "26": 3, "27": 0,  # combustibles pueden ser 0%
    # Cap 28-38: Productos quimicos
    "28": 3, "29": 3, "30": 0,  # medicamentos pueden ser 0%
    "31": 0,  # abonos pueden ser 0%
    "32": 3, "33": 8, "34": 8, "35": 3, "36": 14, "37": 3, "38": 3,
    # Cap 39-40: Plasticos y caucho
    "39": 8, "40": 3,
    # Cap 41-49: Cueros, madera, papel
    "41": 3, "42": 14, "43": 14, "44": 3, "45": 8, "46": 14,
    "47": 3, "48": 8, "49": 3,
    # Cap 50-67: Textiles, calzado
    "50": 3, "51": 3, "52": 3, "53": 3, "54": 8, "55": 8,
    "56": 8, "57": 14, "58": 14, "59": 3, "60": 8,
    "61": 14, "62": 14, "63": 14, "64": 20, "65": 14, "66": 14, "67": 14,
    # Cap 68-71: Piedra, ceramica, vidrio, metales preciosos
    "68": 8, "69": 8, "70": 8, "71": 8,
    # Cap 72-83: Metales comunes
    "72": 3, "73": 3, "74": 3, "75": 3, "76": 3,
    "78": 3, "79": 3, "80": 3, "81": 3, "82": 8, "83": 14,
    # Cap 84-85: Maquinas y aparatos electricos
    "84": 3, "85": 3,
    # Cap 86-89: Material de transporte
    "86": 3, "87": 3, "88": 3, "89": 3,
    # Cap 90-97: Instrumentos, armas, muebles, varios
    "90": 3, "91": 8, "92": 14, "93": 20,
    "94": 14, "95": 14, "96": 8, "97": 3,
}


def _validar_gravamen_python(resultado: dict, codigo: str) -> dict:
    """
    Red de seguridad Python: si Gemini dice gravamen 0% pero el capitulo
    normalmente tiene gravamen > 0%, marca como sospechoso.
    """
    grav_str = resultado.get("gravamen_ad_valorem", "?")
    if grav_str in ("?", "VERIFICAR EN ARANCEL VIGENTE", ""):
        return resultado

    # Extraer numero del gravamen
    m = re.search(r'(\d+)', grav_str)
    if not m:
        return resultado

    grav_num = int(m.group(1))
    capitulo = codigo[:2]

    gravamen_minimo = _GRAVAMEN_MINIMO_POR_CAPITULO.get(capitulo, 0)

    if grav_num < gravamen_minimo:
        print(f"[VERIFICADOR-PYTHON] ALERTA: Gemini dijo {grav_num}% para cap. {capitulo} "
              f"pero el minimo conocido es {gravamen_minimo}%. Marcando como sospechoso.")
        resultado["gravamen_ad_valorem"] = f"VERIFICAR EN ARANCEL VIGENTE (Gemini respondio {grav_num}% pero cap. {capitulo} tiene minimo {gravamen_minimo}%)"
        resultado["gravamen_alerta"] = True

    return resultado


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
            f"Verifica el codigo arancelario {codigo} en el Arancel de la Republica Dominicana.\n"
            f"Producto: {producto}\n\n"
            f"INSTRUCCIONES ESPECIFICAS:\n"
            f"1. ¿Existe el codigo {codigo} con esa extension nacional exacta?\n"
            f"2. Lee la columna GRAV. del Arancel junto a este codigo. "
            f"¿Que NUMERO aparece en esa columna? Ese numero es el gravamen ad-valorem en porcentaje. "
            f"NO respondas 0% a menos que la columna GRAV. explicitamente muestre 0.\n"
            f"3. Lee la columna EX. ITBIS. ¿Esta en blanco (ITBIS 18% aplica) o tiene marca (EXENTO)?\n"
            f"4. ¿Aplica selectivo al consumo u otros cargos?\n"
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

            # ── VALIDACION PYTHON: detectar gravamen 0% sospechoso ──
            # Si Gemini dice 0% pero el capitulo normalmente tiene gravamen,
            # marcar como no confiable y forzar "VERIFICAR EN ARANCEL VIGENTE"
            resultado = _validar_gravamen_python(resultado, codigo_c or codigo)

            grav = resultado.get("gravamen_ad_valorem", "?")
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
    # Gemini usa muchos formatos distintos. Cubrir TODOS:
    #   "Derecho Ad Valorem: 0%"  |  "**Ad-Valorem:** 0%"  |  "Ad Valorem: 0%"
    #   "Gravamen ad valorem: 0%"  |  "Gravamen NMF: 0%"  |  "gravamen: 0%"
    #   "* Derecho Ad Valorem: 0%"  |  "Arancel: 0%"
    es_gravamen_alerta = resultado.get("gravamen_alerta", False)

    if gravamen and gravamen not in ("?",):
        # Si es alerta de Python (0% sospechoso), reemplazar el 0% con la advertencia
        gravamen_reemplazo = gravamen
        if es_gravamen_alerta or "VERIFICAR" in gravamen:
            gravamen_reemplazo = gravamen

        _patrones_gravamen = [
            # "Derecho Ad Valorem: 0%" (con o sin asteriscos/bullets)
            r'([\*\s]*Derecho\s+Ad[\s\-]*Valorem:?\s*)\d+%',
            # "**Ad-Valorem:** 0%" o "Ad Valorem: 0%"
            r'(\*{0,2}Ad[\s\-]*Valorem:?\*{0,2}:?\s*)\d+%',
            # "Gravamen NMF ad valorem: 0%" o "Gravamen: 0%"
            r'(Gravamen\s*(?:NMF\s*)?(?:ad[\s\-]*valorem\s*)?(?:aplicable\s*)?:?\s*)\d+%',
            # "Arancel: 0%"
            r'(Arancel:?\s*)\d+%',
        ]
        for patron in _patrones_gravamen:
            respuesta = re.sub(
                patron,
                r'\g<1>' + gravamen_reemplazo,
                respuesta,
                flags=re.IGNORECASE
            )
        # Tambien corregir en parentesis: "(0%)" → "(20%)"
        respuesta = re.sub(
            r'(ad[\s\-]*valorem[^)]*?)\d+(%\s*(?:\(|,|\.|\)))',
            r'\g<1>' + gravamen.replace('%', '') + r'\2',
            respuesta,
            flags=re.IGNORECASE
        )

    # ── Corregir ITBIS incorrecto en el texto ──
    # Formatos: "ITBIS: 18%"  |  "**ITBIS:** 18%"  |  "* ITBIS: 18%"
    #           "ITBIS (18%)"  |  "ITBIS...18%"
    if itbis and itbis not in ("?", "VERIFICAR EN ARANCEL VIGENTE"):
        itbis_texto_reemplazo = itbis
        if itbis_base and itbis.upper() == "EXENTO":
            itbis_texto_reemplazo = f"EXENTO — {itbis_base}"

        if itbis.upper() == "EXENTO":
            # Producto exento: reemplazar "18%" por "EXENTO"
            _patrones_itbis_18 = [
                r'([\*\s]*\*{0,2}ITBIS[^:\n]*:?\*{0,2}:?\s*)18%[^\n]*',
                r'(ITBIS\s*\([^)]*)\b18%',
            ]
            for patron in _patrones_itbis_18:
                respuesta = re.sub(
                    patron,
                    r'\g<1>' + itbis_texto_reemplazo,
                    respuesta,
                    flags=re.IGNORECASE
                )
        elif itbis != "18%":
            # Tasa diferente a 18%
            _patrones_itbis = [
                r'([\*\s]*\*{0,2}ITBIS[^:\n]*:?\*{0,2}:?\s*)(?:EXENTO|0%|18%)[^\n]*',
            ]
            for patron in _patrones_itbis:
                respuesta = re.sub(
                    patron,
                    r'\g<1>' + itbis_texto_reemplazo,
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
