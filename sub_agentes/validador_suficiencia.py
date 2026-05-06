"""
PASO 6.5 — VALIDADOR DE SUFICIENCIA DE DATOS
=============================================
Dictamen CEO: el sistema clasifica o pide ficha tecnica. Nunca adivina.

Logica:
  - RGI 1 con match directo (sinonimo, navegador, FTS5 unico) → VERDE → clasificar
  - RGI 1 con multiples candidatas resueltas por RGI 3a → VERDE → clasificar
  - RGI 2/3b/3c/4 necesarias Y datos insuficientes → AMARILLO/ROJO → pedir ficha
  - Sin candidatas → ROJO → pedir ficha

Datos que pide segun el tipo de ambiguedad:
  - RGI 3b (caracter esencial): composicion %, material principal, peso por componente
  - RGI 2a (incompleto): funcion del articulo, si tiene caracteristicas del terminado
  - RGI 4 (analogia): especificaciones tecnicas, uso previsto, material constitutivo
  - Multiples capitulos: funcion principal declarada por fabricante, uso final

Base legal: Ley 168-21 Art. 76, Decreto 755-22 Arts. 62-77
"""

_DATOS_POR_TIPO = {
    "composicion": "Composicion exacta en porcentajes (ej: 60% algodon, 40% poliester)",
    "material": "Material constitutivo principal y secundarios",
    "funcion": "Funcion principal declarada por el fabricante",
    "uso": "Uso previsto y uso final del producto",
    "peso": "Peso por componente o material (en gramos o kg)",
    "dimensiones": "Dimensiones fisicas (largo x ancho x alto)",
    "propulsion": "Tipo de propulsion o energia (electrico, combustion, manual)",
    "potencia": "Potencia del motor o capacidad (kW, HP, cc)",
    "acabado": "Estado del producto (terminado, semielaborado, en bruto, desmontado)",
    "marca_modelo": "Marca y modelo del fabricante (para buscar ficha tecnica)",
}

_DATOS_POR_RGI = {
    "RGI 2": ["funcion", "acabado", "material"],
    "RGI 3b": ["composicion", "peso", "material", "funcion"],
    "RGI 3c": ["composicion", "material", "funcion", "uso"],
    "RGI 4": ["material", "funcion", "uso", "dimensiones", "marca_modelo"],
    "CONFLICTO": ["material", "funcion", "uso", "composicion", "marca_modelo"],
    "NINGUNA": ["material", "funcion", "uso", "composicion", "marca_modelo"],
}

_DATOS_POR_CAPITULO = {
    "39": ["material", "composicion"],
    "54": ["composicion", "peso"],
    "55": ["composicion", "peso"],
    "61": ["composicion", "peso"],
    "62": ["composicion", "peso"],
    "63": ["composicion", "peso"],
    "72": ["material", "composicion", "dimensiones"],
    "73": ["material", "dimensiones", "funcion"],
    "84": ["funcion", "potencia", "uso"],
    "85": ["funcion", "potencia", "propulsion"],
    "87": ["propulsion", "potencia", "funcion", "uso"],
    "90": ["funcion", "uso", "marca_modelo"],
}

_INDICADORES_DATO_PRESENTE = {
    "composicion": ["%", "porcentaje", "compuesto de", "mezcla de", "aleacion"],
    "material": ["acero", "aluminio", "cobre", "plastico", "madera", "vidrio",
                 "cuero", "algodon", "poliester", "nylon", "caucho", "hierro",
                 "titanio", "ceramica", "latex", "silicona", "fibra"],
    "funcion": ["para ", "sirve para", "se usa para", "funcion", "destinado a"],
    "uso": ["uso ", "utilizar", "aplicacion", "sector", "industria"],
    "peso": [" kg", " g ", "gramos", "kilos", "libras", " lb"],
    "dimensiones": [" cm", " mm", " m ", "pulgadas", "largo", "ancho", "alto"],
    "propulsion": ["electrico", "gasolina", "diesel", "manual", "solar",
                   "bateria", "motor", "combustion", "hidraulico"],
    "potencia": ["kw", "hp", "watts", "voltios", "amperios", " cc", "caballos"],
    "acabado": ["terminado", "sin terminar", "semielaborado", "bruto",
                "desmontado", "ensamblado", "sin ensamblar"],
    "marca_modelo": [],
}


def evaluar_suficiencia(
    texto_usuario: str,
    rgi_aplicada: str,
    confianza: str,
    capitulo: str = "",
    candidatas_count: int = 1,
) -> dict:
    """
    Evalua si los datos del usuario son suficientes para la RGI que se necesita.

    Returns:
        {
            "suficiente": bool,
            "nivel": "VERDE" | "AMARILLO" | "ROJO",
            "datos_faltantes": [str],
            "mensaje_usuario": str | None,
            "rgi_bloqueante": str | None,
        }
    """
    texto_lower = texto_usuario.lower()

    if confianza == "ALTA":
        return {"suficiente": True, "nivel": "VERDE", "datos_faltantes": [],
                "mensaje_usuario": None, "rgi_bloqueante": None}

    rgi_norm = _normalizar_rgi(rgi_aplicada)

    if rgi_norm == "RGI 1" and confianza in ("ALTA", "MEDIA") and candidatas_count <= 1:
        return {"suficiente": True, "nivel": "VERDE", "datos_faltantes": [],
                "mensaje_usuario": None, "rgi_bloqueante": None}

    if rgi_norm == "RGI 3a" and confianza == "MEDIA":
        return {"suficiente": True, "nivel": "VERDE", "datos_faltantes": [],
                "mensaje_usuario": None, "rgi_bloqueante": None}

    datos_requeridos = set()
    if rgi_norm in _DATOS_POR_RGI:
        datos_requeridos.update(_DATOS_POR_RGI[rgi_norm])
    if capitulo and capitulo[:2] in _DATOS_POR_CAPITULO:
        datos_requeridos.update(_DATOS_POR_CAPITULO[capitulo[:2]])

    if not datos_requeridos:
        datos_requeridos = {"material", "funcion", "uso"}

    datos_presentes = set()
    for dato, indicadores in _INDICADORES_DATO_PRESENTE.items():
        if dato not in datos_requeridos:
            continue
        if any(ind in texto_lower for ind in indicadores):
            datos_presentes.add(dato)

    datos_faltantes = sorted(datos_requeridos - datos_presentes)
    cobertura = len(datos_presentes) / max(len(datos_requeridos), 1)

    if cobertura >= 0.7:
        return {"suficiente": True, "nivel": "VERDE", "datos_faltantes": datos_faltantes,
                "mensaje_usuario": None, "rgi_bloqueante": None}

    if confianza == "BAJA" or rgi_norm in ("RGI 4", "CONFLICTO", "NINGUNA"):
        nivel = "ROJO"
    elif confianza == "REQUIERE_REVISION":
        nivel = "ROJO"
    else:
        nivel = "AMARILLO"

    mensaje = _construir_mensaje(datos_faltantes, rgi_norm, nivel)

    return {
        "suficiente": False,
        "nivel": nivel,
        "datos_faltantes": datos_faltantes,
        "datos_faltantes_detalle": [_DATOS_POR_TIPO.get(d, d) for d in datos_faltantes],
        "mensaje_usuario": mensaje,
        "rgi_bloqueante": rgi_norm,
        "cobertura_datos": round(cobertura, 2),
    }


def _normalizar_rgi(rgi: str) -> str:
    if not rgi:
        return ""
    rgi_upper = rgi.upper()
    for r in ("RGI 1", "RGI 2", "RGI 3A", "RGI 3B", "RGI 3C", "RGI 4", "RGI 5", "RGI 6"):
        if r in rgi_upper:
            return r
    if "CONFLICTO" in rgi_upper:
        return "CONFLICTO"
    if "NINGUNA" in rgi_upper:
        return "NINGUNA"
    if "ANALOGIA" in rgi_upper:
        return "RGI 4"
    if "FTS5" in rgi_upper:
        return "RGI 1"
    if "SINONIMO" in rgi_upper:
        return "RGI 1"
    if "NAVEGADOR" in rgi_upper:
        return "RGI 1"
    return rgi_upper[:6]


def _construir_mensaje(datos_faltantes: list, rgi: str, nivel: str) -> str:
    if nivel == "ROJO":
        intro = (
            "Para clasificar esta mercancia necesito la ficha tecnica del fabricante. "
            "Sin estos datos, el sistema no puede garantizar precision "
            "(Ley 168-21 Art. 76, Decreto 755-22)."
        )
    else:
        intro = (
            "La clasificacion actual tiene incertidumbre. "
            "Con la ficha tecnica del fabricante puedo confirmarla al 100%."
        )

    items = []
    for d in datos_faltantes[:5]:
        detalle = _DATOS_POR_TIPO.get(d, d)
        items.append(f"  - {detalle}")

    partes = [intro, "", "Datos especificos que necesito:"]
    partes.extend(items)

    if rgi in ("RGI 3B", "RGI 3C"):
        partes.append("")
        partes.append(
            "Motivo: hay multiples partidas posibles y necesito determinar "
            "el caracter esencial del producto (RGI 3b, Decreto 755-22 Art. 68)."
        )
    elif rgi == "RGI 2":
        partes.append("")
        partes.append(
            "Motivo: el producto parece incompleto o sin terminar. "
            "Necesito confirmar si tiene las caracteristicas esenciales del articulo "
            "completo (RGI 2a, Decreto 755-22 Art. 65)."
        )
    elif rgi == "RGI 4":
        partes.append("")
        partes.append(
            "Motivo: no hay partida exacta para este producto. "
            "Con datos tecnicos puedo comparar contra mercancias analogas "
            "(RGI 4, Decreto 755-22 Art. 71)."
        )

    return "\n".join(partes)
