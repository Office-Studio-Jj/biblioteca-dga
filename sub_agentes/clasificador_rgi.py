"""
Clasificador RGI — Reglas Generales de Interpretacion del Sistema Armonizado.
Aplica RGI 1→6 secuencialmente segun Ley 168-21 Arts. 75-78, Decreto 755-22 Arts. 62-77.
Trabaja sobre Capa 1 (SQLite) para datos exactos de SON/DAI/ITBIS/ISC.
"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from capa1_sqlite.orquestador_capa3 import (
    buscar_clasificacion_sugerida,
    buscar_partes_producto,
    buscar_sinonimos,
    consultar_rgi,
    consultar_son_exacto,
    registrar_conflicto,
)

_SON_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}(\.\d{2})?$")

# Palabras clave que sugieren producto incompleto/sin terminar (RGI 2)
_INDICADORES_INCOMPLETO = {
    "sin terminar", "incompleto", "sin ensamblar", "desmontado",
    "en partes", "sin acabar", "parcial", "semielaborado",
    "preforma", "en bruto", "sin pulir", "desarmado",
}

# Palabras clave para envases/contenedores (RGI 5)
_INDICADORES_ENVASE = {
    "estuche", "caja", "envase", "contenedor", "funda", "bolsa",
    "empaque", "embalaje", "botella", "frasco", "lata", "recipiente",
}


def clasificar_por_rgi(
    descripcion_producto: str,
    capitulo_candidato: str = None,
) -> dict:
    """
    Punto de entrada principal. Aplica RGI 1→2→3→4→5→6 secuencialmente.

    Args:
        descripcion_producto: Descripcion del producto en lenguaje natural.
        capitulo_candidato: Capitulo SA de 2 digitos (ej. '85'). Opcional.

    Returns:
        {son_final, descripcion, rgi_aplicada, justificacion,
         candidatas_evaluadas, confianza}
    """
    if not descripcion_producto or not descripcion_producto.strip():
        return _resultado_vacio("Descripcion vacia")

    termino = descripcion_producto.strip()
    capitulo = (capitulo_candidato or "").strip().zfill(2) if capitulo_candidato else None

    # === RGI ESTRICTAMENTE SECUENCIAL: 1→2→3→4→5→6 (Guia DGA, Art. 4 Ley 146-00) ===
    # NUNCA saltar ni aplicar fuera de orden.

    # RGI 1: Texto de partidas y notas de seccion/capitulo
    candidatas = _aplicar_rgi1(termino, capitulo)

    if len(candidatas) == 1:
        return _construir_resultado(
            candidatas[0], "RGI 1",
            "Clasificacion directa por texto de partida. Decreto 755-22 Art. 62.",
            candidatas, "ALTA",
        )

    # RGI 2: Articulos incompletos, desmontados o mezclas
    if len(candidatas) == 0 or _es_incompleto(termino):
        candidatas_rgi2 = _intentar_rgi2(termino, capitulo)
        if candidatas_rgi2:
            candidatas = candidatas_rgi2
            if len(candidatas) == 1:
                return _construir_resultado(
                    candidatas[0], "RGI 2",
                    "Articulo incompleto/desmontado con caracteristicas esenciales "
                    "del terminado. Decreto 755-22 Art. 65.",
                    candidatas, "ALTA",
                )

    # RGI 3: Multiples candidatas — resolver conflicto (3a→3b→3c en orden)
    if len(candidatas) >= 2:
        resultado_rgi3 = _aplicar_rgi3(candidatas)
        if resultado_rgi3:
            return _construir_resultado(
                resultado_rgi3["ganadora"],
                resultado_rgi3["sub_regla"],
                resultado_rgi3["justificacion"],
                candidatas,
                resultado_rgi3.get("confianza", "MEDIA"),
            )

    # RGI 4: Analogia — solo si RGI 1-3 no resolvieron
    if len(candidatas) == 0:
        resultado_rgi4 = _aplicar_rgi4(termino)
        if resultado_rgi4:
            return resultado_rgi4
        return _resultado_vacio(f"Sin candidatas para '{termino}'")

    # RGI 5: Envases y contenedores
    if _es_envase(termino):
        return _construir_resultado(
            candidatas[0], "RGI 5",
            "Envase/contenedor: se clasifica con la mercancia que contiene. "
            "Decreto 755-22 Art. 73.",
            candidatas, "MEDIA",
        )

    # RGI 6: Subpartidas al mismo nivel de guiones
    resultado_rgi6 = _aplicar_rgi6(candidatas)
    if resultado_rgi6:
        return _construir_resultado(
            resultado_rgi6, "RGI 6",
            "Clasificacion por comparacion de subpartidas al mismo nivel. "
            "Decreto 755-22 Art. 77.",
            candidatas, "MEDIA",
        )

    # Sin resolucion por RGI 1-6 → registrar para revision humana
    return _resolver_conflicto(candidatas, termino)


def _aplicar_rgi1(termino: str, capitulo: str = None) -> list[dict]:
    """
    RGI 1: Busca por texto de partidas. Filtra por capitulo si se indica.
    Tambien busca sinonimos arancelarios para ampliar resultados.
    """
    candidatas = buscar_clasificacion_sugerida(termino, limit=20)

    # Ampliar con sinonimos
    sinonimos = buscar_sinonimos(termino)
    for sin in sinonimos:
        son_target = sin.get("son_destino") or sin.get("son")
        if son_target:
            datos = consultar_son_exacto(son_target)
            if datos and not any(c["son"] == datos["son"] for c in candidatas):
                candidatas.append(datos)

    # Filtrar por capitulo si se proporciono
    if capitulo and len(capitulo) >= 2:
        filtradas = [c for c in candidatas if c["son"][:2] == capitulo[:2]]
        if filtradas:
            candidatas = filtradas

    # Eliminar duplicados por SON
    vistos = set()
    unicas = []
    for c in candidatas:
        if c["son"] not in vistos:
            vistos.add(c["son"])
            unicas.append(c)
    return unicas


def _intentar_rgi2(termino: str, capitulo: str = None) -> list[dict]:
    """
    RGI 2: Productos incompletos, sin terminar o desmontados
    se clasifican como el articulo completo.
    Busca tambien partes de productos.
    """
    # Buscar si es parte de un producto conocido
    partes = buscar_partes_producto(termino)
    candidatas = []
    for p in partes:
        son_padre = p.get("son_producto_completo") or p.get("son")
        if son_padre:
            datos = consultar_son_exacto(son_padre)
            if datos:
                candidatas.append(datos)

    if not candidatas:
        # Intentar busqueda sin indicadores de incompletitud
        termino_limpio = termino
        for ind in _INDICADORES_INCOMPLETO:
            termino_limpio = termino_limpio.replace(ind, "").strip()
        if termino_limpio != termino and termino_limpio:
            candidatas = _aplicar_rgi1(termino_limpio, capitulo)

    return candidatas


def _aplicar_rgi3(candidatas: list[dict]) -> dict | None:
    """
    RGI 3: Cuando un producto puede clasificarse en 2+ partidas.
    3a: La mas especifica prevalece.
    3b: Caracter esencial (mezclas, surtidos, juegos).
    3c: Ultima en orden numerico.

    Retorna {ganadora, sub_regla, justificacion} o None.
    """
    if len(candidatas) < 2:
        return None

    # RGI 3a: La partida mas especifica prevalece sobre la generica
    candidatas_ord = sorted(candidatas, key=lambda c: len(c.get("descripcion", "")), reverse=True)
    top = candidatas_ord[0]
    segunda = candidatas_ord[1]
    diff_len = len(top.get("descripcion", "")) - len(segunda.get("descripcion", ""))

    if diff_len > 20:
        return {
            "ganadora": top,
            "sub_regla": "RGI 3a",
            "confianza": "MEDIA",
            "justificacion": (
                f"Partida {top['son']} es mas especifica que {segunda['son']}. "
                "Decreto 755-22 Art. 67."
            ),
        }

    # RGI 3b: Caracter esencial (mezclas, surtidos, juegos para venta al detalle)
    # Se determina por naturaleza, volumen, peso, valor o papel funcional.
    # SIN datos del fabricante → no se puede calcular → marcar como PROVISIONAL.
    return {
        "ganadora": top,
        "sub_regla": "RGI 3b",
        "confianza": "BAJA",
        "justificacion": (
            f"Multiples partidas posibles ({', '.join(c['son'] for c in candidatas[:3])}). "
            "RGI 3b requiere determinar caracter esencial por composicion/peso/valor. "
            "Ficha tecnica del fabricante necesaria para certeza. "
            "Decreto 755-22 Art. 68."
        ),
    }


def _aplicar_rgi4(termino: str) -> dict | None:
    """
    RGI 4: Mercancias sin partida especifica se clasifican
    en la partida de articulos mas analogos.
    """
    # Busqueda mas amplia: cada palabra individual
    palabras = [p for p in termino.split() if len(p) >= 3]
    todas = []
    for palabra in palabras[:5]:
        resultados = buscar_clasificacion_sugerida(palabra, limit=5)
        todas.extend(resultados)

    if not todas:
        return None

    # Deduplicar
    vistos = set()
    unicas = []
    for c in todas:
        if c["son"] not in vistos:
            vistos.add(c["son"])
            unicas.append(c)

    if not unicas:
        return None

    # Seleccionar la mas frecuente (aparece en mas busquedas parciales)
    conteo = {}
    for c in todas:
        conteo[c["son"]] = conteo.get(c["son"], 0) + 1
    mejor_son = max(conteo, key=conteo.get)
    mejor = next(c for c in unicas if c["son"] == mejor_son)

    return _construir_resultado(
        mejor, "RGI 4",
        f"Sin partida exacta. Clasificacion por analogia con {mejor['son']}. "
        "Decreto 755-22 Art. 71.",
        unicas, "BAJA",
    )


def _aplicar_rgi6(candidatas: list[dict]) -> dict | None:
    """
    RGI 6: Comparar subpartidas al mismo nivel de guiones.
    Solo aplica entre subpartidas del mismo nivel jerarquico.
    """
    if len(candidatas) < 2:
        return None

    # Agrupar por partida (4 digitos)
    por_partida = {}
    for c in candidatas:
        partida = c["son"][:4]
        por_partida.setdefault(partida, []).append(c)

    # Si hay un grupo mayoritario, comparar dentro de ese grupo
    grupo_mayor = max(por_partida.values(), key=len)
    if len(grupo_mayor) >= 2:
        # Aplicar RGI 1-5 mutatis mutandis a nivel de subpartida
        # Heuristica: la mas especifica (descripcion mas larga)
        return sorted(grupo_mayor, key=lambda c: len(c.get("descripcion", "")), reverse=True)[0]

    return None


def _resolver_conflicto(candidatas: list[dict], consulta: str) -> dict:
    """
    Ultimo recurso: registra el conflicto y devuelve la mejor estimacion.
    """
    if not candidatas:
        return _resultado_vacio(f"Sin candidatas para '{consulta}'")

    # Tomar la primera por orden numerico como fallback
    candidatas_ord = sorted(candidatas, key=lambda c: c["son"])
    ganadora = candidatas_ord[0]

    # Registrar conflicto para revision humana
    registrar_conflicto(
        consulta=consulta,
        candidatas=[c["son"] for c in candidatas],
        ganadora=ganadora["son"],
        rgi="CONFLICTO",
        justificacion="Requiere revision humana. Ninguna RGI resolvio el conflicto.",
        resuelto_por="clasificador_rgi_auto",
    )

    return _construir_resultado(
        ganadora, "NINGUNA",
        "No se pudo resolver con RGI 1-6. Registrado para revision. "
        "Verificar en aduanas.gob.do",
        candidatas, "REQUIERE_REVISION",
    )


def _es_incompleto(termino: str) -> bool:
    """Detecta si la descripcion indica producto incompleto/sin terminar."""
    t = termino.lower()
    return any(ind in t for ind in _INDICADORES_INCOMPLETO)


def _es_envase(termino: str) -> bool:
    """Detecta si la descripcion indica un envase o contenedor."""
    t = termino.lower()
    return any(ind in t for ind in _INDICADORES_ENVASE)


def _construir_resultado(
    candidata: dict,
    rgi_aplicada: str,
    justificacion: str,
    todas: list[dict],
    confianza: str,
) -> dict:
    """Arma el dict de respuesta estandar."""
    return {
        "son_final": candidata["son"],
        "descripcion": candidata.get("descripcion", ""),
        "rgi_aplicada": rgi_aplicada,
        "justificacion": justificacion,
        "candidatas_evaluadas": [
            {"son": c["son"], "descripcion": c.get("descripcion", "")}
            for c in todas[:10]
        ],
        "confianza": confianza,
        "gravamen": candidata.get("gravamen"),
        "itbis": candidata.get("itbis"),
        "isc": candidata.get("isc"),
    }


def _resultado_vacio(motivo: str) -> dict:
    """Retorna resultado cuando no hay candidatas."""
    return {
        "son_final": None,
        "descripcion": None,
        "rgi_aplicada": "NINGUNA",
        "justificacion": motivo,
        "candidatas_evaluadas": [],
        "confianza": "REQUIERE_REVISION",
        "gravamen": None,
        "itbis": None,
        "isc": None,
    }
