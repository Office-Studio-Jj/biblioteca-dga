"""
NAVEGADOR JERARQUICO DEL SISTEMA ARMONIZADO
============================================
Sigue la jerarquia real del Arancel de Aduanas RD (Decreto 36-22, 7ma Enmienda SA):

  Capitulo (2 dig)
    └─ Partida (4 dig + descripcion sin guion)
         └─ Subpartida SA (6 dig + 1 guion)
              └─ SON Nacional RD (8 dig + 3 guiones)

Cada nivel se evalua de forma independiente contra sus propias keywords.
Nunca salta niveles: primero identifica la partida correcta, luego subpartida, luego SON.

Ejemplo verificado con arancel fisico:
  "patineta electrica" →
    Cap 87 (vehiculos) →
    8711 (motocicletas / ciclomotores / velocipedos) — NO 8701 (tractores) →
    8711.60 (propulsados con motor electrico) →
    8711.60.14 (ciclomotores / scooters) ✓

Base legal: RGI 1, RGI 3a, RGI 6 — Ley 168-21 Art.75, Decreto 755-22 Art.63
"""

import os
import re
import sqlite3
import unicodedata

_HERE = os.path.dirname(os.path.abspath(__file__))
_DB   = os.path.join(_HERE, "capa1_sqlite", "arancel_rd.db")

_STOPWORDS = {
    "de", "del", "la", "el", "los", "las", "un", "una", "con", "para",
    "en", "y", "o", "a", "al", "se", "su", "que", "por", "es", "son",
}

# ═══════════════════════════════════════════════════════════════════════════════
# ARBOL JERARQUICO SA — nivel 1: Capitulo
# ═══════════════════════════════════════════════════════════════════════════════

_CAP_KEYWORDS = {
    87: ["vehiculo", "carro", "auto", "moto", "bicicleta", "patineta",
         "scooter", "tractor", "remolque", "camion", "autobus", "monopatin",
         "hoverboard", "hover board", "segway", "velocipedo", "ciclomotor"],
    85: ["electrico", "electronico", "pantalla", "display", "telefono", "celular",
         "bateria", "cargador", "auricular", "led", "cable usb", "power bank",
         "televisor", "monitor", "panel solar", "smartphone"],
    84: ["maquina", "motor combustion", "bomba", "compresor", "computadora",
         "refrigerador", "lavadora", "impresora", "turbina", "laptop"],
    90: ["lente", "microscopio", "telescopio", "camara fotografica", "gafas", "anteojos"],
    61: ["camisa", "pantalon", "vestido", "ropa tejido punto"],
    62: ["chaqueta", "abrigo", "traje", "prenda tela"],
    64: ["zapato", "bota", "sandalia", "calzado", "zapatilla"],
}

# ═══════════════════════════════════════════════════════════════════════════════
# ARBOL JERARQUICO SA — nivel 2: Partida dentro de cada Capitulo
# ═══════════════════════════════════════════════════════════════════════════════

_PARTIDAS = {
    # ── CAP 87 ──────────────────────────────────────────────────────────────
    87: {
        # 8711: Motocicletas (incluidos los ciclomotores) y velocipedos con motor auxiliar
        # RGI 1: La nota de la partida incluye expresamente ciclomotores, velocipedos,
        #        scooters, e-scooters, patinetas electricas (propulsados por motor)
        "8711": ["motocicleta", "moto", "ciclomotor", "velocipedo",
                 "scooter", "e-scooter", "escooter", "patineta",
                 "monopatin", "hoverboard", "hover board", "segway",
                 "bicicleta electrica", "ebike", "e-bike",
                 "motor auxiliar", "propulsion electrica personal"],

        "8701": ["tractor", "motocultor", "arado", "agricola", "orugas tractor",
                 "tractor ruedas", "tractor agricola"],
        "8702": ["autobus", "autocar", "omnibus", "microbus", "bus pasajeros",
                 "transporte colectivo"],
        "8703": ["automovil", "sedan", "suv", "pickup personal", "turismo",
                 "coupe", "convertible", "station wagon"],
        "8704": ["camion carga", "furgon", "furgoneta carga", "volquete",
                 "camion volquete"],
        "8705": ["grua", "camion bomberos", "barredera", "hormigonera",
                 "vehiculo especial obra"],
        "8709": ["carretilla autopropulsada", "carretilla industrial",
                 "carretilla almacen", "montacargas electrico", "transpaleta",
                 "apilador electrico"],
        "8712": ["bicicleta", "cicla", "bici"],
        "8716": ["remolque", "semirremolque", "trailer", "acoplado"],
    },

    # ── CAP 85 ──────────────────────────────────────────────────────────────
    85: {
        "8517": ["telefono celular", "celular", "smartphone", "movil",
                 "telefono inteligente"],
        "8518": ["auricular", "audifonos", "headset", "airpods", "earbuds",
                 "headphones", "altavoz", "bocina"],
        "8504": ["cargador usb", "cargador celular", "adaptador corriente",
                 "convertidor ca cc", "transformador"],
        "8507": ["power bank", "bateria portatil", "acumulador portatil",
                 "bateria externa", "acumulador electrico"],
        "8528": ["pantalla", "monitor", "display", "televisor", "pantalla lcd",
                 "pantalla oled", "pantalla amoled", "pantalla celular",
                 "pantalla tactil", "touchscreen"],
    },

    # ── CAP 84 ──────────────────────────────────────────────────────────────
    84: {
        "8471": ["computadora", "ordenador", "laptop", "notebook", "pc"],
        "8418": ["refrigerador", "nevera", "frigorifico", "congelador"],
        "8450": ["lavadora", "lavarropa", "lavarropas"],
        "8443": ["impresora"],
    },

    # ── CAP 90 ──────────────────────────────────────────────────────────────
    90: {
        "9001": ["lente gafas", "lente oftalmico", "gafas", "anteojos", "lente optico"],
        "9006": ["camara fotografica", "camara digital", "camara foto"],
    },
}

# ═══════════════════════════════════════════════════════════════════════════════
# ARBOL JERARQUICO SA — nivel 3: Subpartida dentro de cada Partida
# ═══════════════════════════════════════════════════════════════════════════════

_SUBPARTIDAS = {
    # ── PARTIDA 8711 ────────────────────────────────────────────────────────
    "8711": {
        # 8711.60: Propulsados con motor electrico (1 guion = subpartida SA)
        # Esta es la subpartida para TODO vehiculo de 2 ruedas con motor electrico.
        # Patineta/scooter/hoverboard/segway son SIEMPRE electricos en la practica.
        "8711.60": ["electrico", "electrica", "motor electrico", "bateria litio",
                    "propulsion electrica", "electric",
                    "patineta", "scooter", "e-scooter", "escooter",
                    "monopatin", "hoverboard", "hover board", "segway",
                    "ebike", "e-bike", "bicicleta electrica"],

        # Subpartidas por cilindraje (motor de combustion)
        "8711.10": ["50 cm", "50cc", "cilindraje 50", "inferior 50"],
        "8711.20": ["125cc", "150cc", "200cc", "51 cm", "50 250", "cilindraje 125"],
        "8711.30": ["250cc", "300cc", "400cc", "250 500"],
        "8711.40": ["500cc", "600cc", "700cc", "500 800"],
        "8711.50": ["800cc", "1000cc", "superior 800"],
        "8711.90": ["velocipedo motor auxiliar", "auxiliar"],
    },

    # ── PARTIDA 8701 ────────────────────────────────────────────────────────
    "8701": {
        "8701.10": ["motocultor"],
        "8701.21": ["diesel encendido compresion inferior 130 kw"],
        "8701.24": ["electrico", "electrica", "motor electrico"],
        "8701.91": ["potencia inferior 18", "inferior 37"],
        "8701.92": ["18 37 kw"],
        "8701.93": ["37 75 kw"],
        "8701.94": ["75 130 kw"],
        "8701.95": ["superior 130 kw"],
    },

    # ── PARTIDA 8528 ────────────────────────────────────────────────────────
    "8528": {
        "8528.59": ["pantalla celular", "pantalla movil", "display celular",
                    "pantalla tactil movil", "pantalla smartphone",
                    "celular pantalla", "pantalla para celular",
                    "celular", "movil"],
        "8528.49": ["monitor", "pantalla monitor", "monitor pc"],
        "8528.71": ["televisor", "tv", "television", "pantalla televisor"],
    },

    # ── PARTIDA 8504 ────────────────────────────────────────────────────────
    "8504": {
        "8504.40": ["cargador", "adaptador corriente", "fuente alimentacion",
                    "convertidor", "cargador usb"],
    },
}

# ═══════════════════════════════════════════════════════════════════════════════
# ARBOL JERARQUICO SA — nivel 4: SON dentro de cada Subpartida
# ═══════════════════════════════════════════════════════════════════════════════

_SONS = {
    # ── SUBPARTIDA 8711.60 ──────────────────────────────────────────────────
    "8711.60": {
        # 8711.60.14: Ciclomotores («scooters»)
        # Verificado con imagen del arancel fisico RD
        # Patineta electrica, e-scooter, hoverboard, segway → ciclomotor
        "8711.60.14": ["ciclomotor", "scooter", "e-scooter", "escooter",
                       "patineta", "monopatin", "hoverboard", "hover board",
                       "segway"],

        # 8711.60.11: Motocicletas
        "8711.60.11": ["motocicleta", "moto electrica", "motorcycle"],

        # 8711.60.12: Bicicletas
        "8711.60.12": ["bicicleta", "ebike", "e-bike", "bici electrica"],

        # 8711.60.13: Velocipedos
        "8711.60.13": ["velocipedo"],

        # 8711.60.19: Los demas
        "8711.60.19": ["otro vehiculo electrico", "vehiculo autoequilibrio",
                       "movilidad personal electrica"],
    },

    # ── SUBPARTIDA 8528.59 ──────────────────────────────────────────────────
    "8528.59": {
        "8528.59.90": ["pantalla celular", "display movil", "pantalla smartphone",
                       "pantalla tactil movil", "pantalla lcd celular",
                       "celular", "movil", "display celular"],
    },

    # ── SUBPARTIDA 8528.49 ──────────────────────────────────────────────────
    "8528.49": {
        "8528.49.00": ["monitor", "pantalla monitor", "display pc"],
    },

    # ── SUBPARTIDA 8504.40 ──────────────────────────────────────────────────
    "8504.40": {
        "8504.40.00": ["cargador", "adaptador"],
    },
}


# ─── UTILIDADES ────────────────────────────────────────────────────────────────

def _norm(texto: str) -> str:
    s = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", " ", s.lower()).strip()


def _tokens(texto: str) -> set:
    return {w for w in _norm(texto).split() if len(w) >= 3 and w not in _STOPWORDS}


def _score_kws(texto_norm: str, keywords: list) -> float:
    """
    Puntua cuantos keywords del catalogo aparecen en el texto.
    - Keyword de 1 palabra: debe ser token exacto (evita 'bici' dentro de 'bicicleta')
    - Keyword de N palabras: frase completa (substring) + peso N (RGI 3a: mas especifico gana)
    """
    tokens_texto = set(texto_norm.split())
    score = 0.0
    for kw in keywords:
        kw_norm = _norm(kw)
        partes = kw_norm.split()
        if len(partes) == 1:
            # Token exacto — evita falsos positivos por substring
            if kw_norm in tokens_texto:
                score += 1.0
        else:
            # Frase completa en el texto
            if kw_norm in texto_norm:
                score += float(len(partes))
    return score


# ─── NIVEL 1: CAPITULO ─────────────────────────────────────────────────────────

def _detectar_capitulo(texto: str) -> int | None:
    tn = _norm(texto)
    mejor = (0, None)
    for cap, kws in _CAP_KEYWORDS.items():
        score = _score_kws(tn, kws)
        if score > mejor[0]:
            mejor = (score, cap)
    return mejor[1] if mejor[0] > 0 else None


# ─── NIVEL 2: PARTIDA ──────────────────────────────────────────────────────────

def _detectar_partida(texto: str, capitulo: int) -> str | None:
    tn = _norm(texto)
    mapa = _PARTIDAS.get(capitulo, {})
    if not mapa:
        return None

    candidatos = []
    for partida, kws in mapa.items():
        score = _score_kws(tn, kws)
        if score > 0:
            candidatos.append((score, partida))

    if not candidatos:
        return None

    candidatos.sort(reverse=True)
    return candidatos[0][1]


# ─── NIVEL 3: SUBPARTIDA ───────────────────────────────────────────────────────

def _detectar_subpartida(texto: str, partida: str) -> str | None:
    tn = _norm(texto)
    mapa = _SUBPARTIDAS.get(partida, {})
    if not mapa:
        return None

    candidatos = []
    for subpartida, kws in mapa.items():
        score = _score_kws(tn, kws)
        if score > 0:
            candidatos.append((score, subpartida))

    if not candidatos:
        return None

    candidatos.sort(reverse=True)
    return candidatos[0][1]


# ─── NIVEL 4: SON ──────────────────────────────────────────────────────────────

def _detectar_son_en_subpartida(texto: str, subpartida: str) -> str | None:
    tn = _norm(texto)
    mapa = _SONS.get(subpartida, {})
    if not mapa:
        return None

    candidatos = []
    for son, kws in mapa.items():
        score = _score_kws(tn, kws)
        if score > 0:
            candidatos.append((score, son))

    if not candidatos:
        return None

    candidatos.sort(reverse=True)
    return candidatos[0][1]


# ─── VERIFICACION EN DB ────────────────────────────────────────────────────────

def _verificar_en_db(son: str) -> str | None:
    try:
        with sqlite3.connect(_DB) as conn:
            r = conn.execute("SELECT son FROM codigos WHERE son = ?", (son,)).fetchone()
            return r[0] if r else None
    except Exception:
        return None


def _elegir_son_db(tokens: set, prefijo: str) -> str | None:
    """Si no hay match en _SONS, elige el mejor SON de la DB bajo ese prefijo."""
    residuales = (".00", ".90", ".99", ".19", ".29", ".09", ".49")
    try:
        with sqlite3.connect(_DB) as conn:
            prefijo_clean = prefijo.replace(".", "")
            rows = conn.execute(
                "SELECT son, descripcion FROM codigos "
                "WHERE replace(son,'.','') LIKE ? ORDER BY son",
                (prefijo_clean + "%",)
            ).fetchall()
        if not rows:
            return None

        puntuados = []
        for son, desc in rows:
            score = sum(1 for t in tokens if t in _norm(desc or ""))
            es_residual = son.endswith(residuales)
            puntuados.append((score, not es_residual, son))

        puntuados.sort(reverse=True)

        for score, _, son in puntuados:
            if score > 0:
                return son

        for _, no_res, son in puntuados:
            if no_res:
                return son

        return puntuados[0][2] if puntuados else None

    except Exception:
        return None


# ─── PUNTO DE ENTRADA ──────────────────────────────────────────────────────────

def navegar_jerarquia(texto_usuario: str) -> str | None:
    """
    Navega el arbol SA siguiendo la jerarquia real del Arancel RD.

    Orden estricto:
      1. Detectar Capitulo (2 dig)
      2. Identificar Partida correcta dentro del Capitulo (4 dig)
      3. Identificar Subpartida dentro de la Partida (6 dig)
      4. Identificar SON dentro de la Subpartida (8 dig)

    Retorna el SON mas especifico o None si no puede determinar.
    """
    if not texto_usuario or not texto_usuario.strip():
        return None

    tokens = _tokens(texto_usuario)
    if not tokens:
        return None

    # PASO 1: Capitulo
    capitulo = _detectar_capitulo(texto_usuario)
    if not capitulo:
        return None

    # PASO 2: Partida (RGI 1 — texto de las partidas del capitulo)
    partida = _detectar_partida(texto_usuario, capitulo)
    if not partida:
        return None

    # PASO 3: Subpartida (RGI 6 — comparacion al mismo nivel)
    subpartida = _detectar_subpartida(texto_usuario, partida)
    if not subpartida:
        # Sin subpartida en el arbol local → buscar en DB
        son_db = _elegir_son_db(tokens, partida)
        return son_db

    # PASO 4: SON (RGI 6 — nivel subpartida nacional)
    son = _detectar_son_en_subpartida(texto_usuario, subpartida)
    if son:
        verificado = _verificar_en_db(son)
        if verificado:
            return verificado

    # Fallback: buscar en DB bajo la subpartida
    return _elegir_son_db(tokens, subpartida)
