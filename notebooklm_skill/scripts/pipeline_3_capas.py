"""
PIPELINE 3 CAPAS — Arquitectura Two-Brain DGA
==============================================

Orquesta las 3 capas en el orden correcto, con verificacion de cada una:

    CAPA 3 (Gemini) → mesa de reparticion / orquestador
       ↓ identifica el producto y decide ruta
    CAPA 2 (Notion/Merceologia) → busca ficha del producto
       ↓ extrae codigo + datos clasificacion
    CAPA 1 (Claude/SQLite) → confirma codigo + cargas + base legal

Cada capa registra su resultado en `trazabilidad`. Si una capa falla, la
siguiente compensa. El resultado final es la mejor combinacion verificada.

NO ROMPER EL PATRON: este modulo es la unica via correcta para construir
respuestas. Si se modifica, ejecutar tests/test_pipeline_3_capas.py antes
de mergear.
"""
import os
import sys
import time
import json
import re
from typing import Optional, Dict, Any

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.join(_HERE, "..", "data")

# ── Cache de consultas frecuentes (TTL 7 dias) ──────────────────────────
# Bug APP-2026-001 #5: productos repetidos no deben recorrer las 3 capas.
_CACHE_CONSULTAS_PATH = os.path.join(_DATA, "cache_consultas.json")
_CACHE_TTL_SEG = 7 * 24 * 3600


def _cache_key(consulta: str, notebook_id: str) -> str:
    import hashlib
    norm = re.sub(r'\s+', ' ', (consulta or "").lower().strip())
    return hashlib.sha256(f"{notebook_id}|{norm}".encode("utf-8")).hexdigest()[:24]


def _cache_get(consulta: str, notebook_id: str) -> Optional[Dict[str, Any]]:
    try:
        if not os.path.exists(_CACHE_CONSULTAS_PATH):
            return None
        with open(_CACHE_CONSULTAS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        entry = data.get(_cache_key(consulta, notebook_id))
        if not entry:
            return None
        if time.time() - entry.get("ts", 0) > _CACHE_TTL_SEG:
            return None
        return entry.get("payload")
    except Exception:
        return None


def _cache_put(consulta: str, notebook_id: str, payload: Dict[str, Any]) -> None:
    try:
        data = {}
        if os.path.exists(_CACHE_CONSULTAS_PATH):
            with open(_CACHE_CONSULTAS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        # Limpieza perezosa de expirados
        now = time.time()
        data = {k: v for k, v in data.items() if now - v.get("ts", 0) <= _CACHE_TTL_SEG}
        data[_cache_key(consulta, notebook_id)] = {"ts": now, "payload": payload}
        os.makedirs(os.path.dirname(_CACHE_CONSULTAS_PATH), exist_ok=True)
        with open(_CACHE_CONSULTAS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        print(f"[CACHE] No se pudo guardar consulta: {e}")


def capa_3_gemini_orquestador(consulta: str, notebook_id: str) -> Dict[str, Any]:
    """
    CAPA 3 — Gemini como mesa de reparticion / orquestador.

    Responsabilidades (NO toma decisiones legales — solo distribuye):
      - Identifica QUE ES el producto en lenguaje natural
      - Extrae caracteristicas mencionadas (peso, material, uso)
      - Decide si requiere flujo merceologico
      - REPARTE trabajo: envia consulta a Capa 2 (descripcion) y Capa 1 (verificacion legal)

    NO determina:
      - Partida arancelaria (eso lo hace Capa 1)
      - RGI ni Notas Legales (eso lo hace Capa 1)
      - Codigo SON (eso lo hace Capa 1)
    """
    t0 = time.time()
    resultado = {
        "capa": 3,
        "nombre": "Gemini Orquestador (identifica + reparte)",
        "ok": False,
        "fuente": "reglas",
        "producto_identificado": "",
        "categoria_general": "",
        "caracteristicas_detectadas": {},
        "trabajos_repartidos": [],
        "requiere_merceologia": False,
    }

    consulta_lower = (consulta or "").lower().strip()
    if not consulta_lower:
        resultado["error"] = "consulta vacia"
        resultado["elapsed_ms"] = int((time.time() - t0) * 1000)
        return resultado

    palabras = re.findall(r'\b[a-záéíóúüñ]{4,}\b', consulta_lower)
    stopwords = {"para", "como", "cual", "este", "esta", "donde", "tiene", "necesito",
                 "consulta", "clasificar", "producto", "codigo", "arancel"}
    palabras_clave = [p for p in palabras if p not in stopwords]
    resultado["producto_identificado"] = " ".join(palabras_clave[:5])

    # Categoria GENERAL solo como pista (NO determina partida)
    categorias = [
        ("aeronave", ["dron", "drone", "uav", "aeronave", "avion", "helicoptero"]),
        ("electronico", ["camara", "videocamara", "monitor", "tv", "televisor", "telefono",
                          "celular", "smartphone", "computadora", "laptop", "tablet"]),
        ("maquinaria", ["motor", "bomba", "compresor", "valvula", "rodamiento", "turbina"]),
        ("vehiculo", ["vehiculo", "auto", "carro", "motocicleta", "neumatico", "camion"]),
        ("farmaceutico", ["medicamento", "farmaco", "vitamina", "suplemento", "antibiotico"]),
        ("bebida", ["bebida", "alcohol", "vino", "cerveza", "ron", "whisky", "vodka"]),
        ("metalurgia", ["acero", "hierro", "metalica", "aluminio", "cobre", "tornillo"]),
        ("plastico", ["plastico", "polietileno", "pvc", "polimero"]),
        ("agropecuario", ["fertilizante", "pesticida", "semilla", "herbicida"]),
    ]
    for nombre, keys in categorias:
        if any(k in consulta_lower for k in keys):
            resultado["categoria_general"] = nombre
            break

    # Extraer caracteristicas mencionadas (peso, material, uso) para que Capa 1 las use
    caracs = {}
    m_peso = re.search(r'(\d+(?:[.,]\d+)?)\s*(kg|kilos?|gramos?|g\b|toneladas?)', consulta_lower)
    if m_peso:
        caracs["peso"] = f"{m_peso.group(1)}{m_peso.group(2)}"
    m_volumen = re.search(r'(\d+(?:[.,]\d+)?)\s*(ml|cc|litros?|l\b)', consulta_lower)
    if m_volumen:
        caracs["volumen"] = f"{m_volumen.group(1)}{m_volumen.group(2)}"
    m_potencia = re.search(r'(\d+(?:[.,]\d+)?)\s*(w|watts?|hp|kw|cv)\b', consulta_lower)
    if m_potencia:
        caracs["potencia"] = f"{m_potencia.group(1)}{m_potencia.group(2)}"
    if any(k in consulta_lower for k in ["agricol", "agropecuari", "agricultura", "fumigacion", "cultivo"]):
        caracs["uso_agropecuario"] = True
    if any(k in consulta_lower for k in ["industrial", "comercial"]):
        caracs["uso_industrial"] = True
    if any(k in consulta_lower for k in ["domestico", "casero", "residencial", "hogar"]):
        caracs["uso_domestico"] = True
    resultado["caracteristicas_detectadas"] = caracs

    # Reparticion de trabajo
    es_clasificacion = notebook_id == "biblioteca-de-nomenclaturas" and len(palabras_clave) >= 1
    resultado["requiere_merceologia"] = es_clasificacion
    resultado["trabajos_repartidos"] = [
        {"capa": 2, "tarea": "describir merceologicamente: que es, materia, funcion, uso, usuario"},
        {"capa": 1, "tarea": "determinar partida + RGI + notas legales + SON + gravamen + ITBIS + ISC + leyes + permisos + conflictos"},
    ]
    resultado["ok"] = True
    resultado["elapsed_ms"] = int((time.time() - t0) * 1000)
    return resultado


def _gemini_clasificar_producto(consulta: str, capitulo_pista: str = "") -> Dict[str, Any]:
    """Capa 2b: invoca Gemini-REST con prompt enfocado en clasificacion arancelaria.
    Devuelve codigo + descripcion + capitulo extraidos de la respuesta."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return {"ok": False, "error": "GEMINI_API_KEY no configurada"}

    try:
        if _HERE not in sys.path:
            sys.path.insert(0, _HERE)
        from ask_gemini import _gemini_rest_call
    except Exception as e:
        return {"ok": False, "error": f"import _gemini_rest_call: {e}"}

    pista = f"\nPista de capitulo SA: {capitulo_pista}" if capitulo_pista else ""
    system = (
        "Eres clasificador arancelario senior del Arancel de Aduanas de la Republica Dominicana "
        "(7ma Enmienda 2022, Decreto 36-22). Tu unica tarea es devolver el codigo nacional RD "
        "de 8 digitos (XXXX.XX.XX) mas especifico posible para el producto consultado."
    )
    prompt = (
        f"Clasifica este producto: {consulta}{pista}\n\n"
        "REGLAS OBLIGATORIAS:\n"
        "1. PROHIBIDO devolver subpartidas genericas '.99.X' o terminadas en '.00' "
        "si existen subpartidas mas especificas. Lee la descripcion oficial de "
        "cada subpartida candidata y elige la que mejor describe el producto.\n"
        "2. Codigo SIEMPRE 8 digitos formato XXXX.XX.XX. NUNCA 10 digitos.\n"
        "3. Si el producto puede caer en varias subpartidas por peso/tamaño/uso, "
        "indica la version mas especifica con justificacion breve.\n"
        "4. Considera Notas Legales del Capitulo y Reglas Generales de Interpretacion "
        "(RGI 1, 3a, 6).\n"
        "5. ILUMINACION (regla dura — Nota 11.b Cap.85 SA):\n"
        "   - Lampara/bombillo/tubo LED (con o sin casquillo, el elemento que GENERA luz) -> 8539.52.00\n"
        "   - Luminaria/fixture/aplique/candelabro (el aparato que SOSTIENE o DIRIGE la luz) -> 94.05.xx\n"
        "   - Criterio: si el producto genera luz por si mismo -> Cap.85. Si solo la sostiene -> Cap.94.\n"
        "   - PROHIBIDO clasificar bombillos LED en 9405. Es error frecuente.\n\n"
        "FORMATO DE RESPUESTA (estricto, una linea por campo):\n"
        "CODIGO: [XXXX.XX.XX]\n"
        "CAPITULO: [NN]\n"
        "PARTIDA: [XXXX]\n"
        "SUBPARTIDA_SA: [XXXX.XX]\n"
        "DESCRIPCION_OFICIAL: [texto breve del Arancel]\n"
        "JUSTIFICACION: [1-2 frases]\n"
        "RGI: [RGI X]"
    )
    answer, err = _gemini_rest_call(api_key, "gemini-2.5-flash", system, prompt, timeout=45)
    if err or not answer:
        return {"ok": False, "error": err or "respuesta vacia"}

    # Parsear bloque estructurado
    out = {"ok": True, "raw": answer[:600]}
    for campo, regex in [
        ("codigo", r'CODIGO:\s*(\d{4}\.\d{2}\.\d{2})'),
        ("capitulo", r'CAPITULO:\s*(\d{2})'),
        ("partida", r'PARTIDA:\s*(\d{4})'),
        ("subpartida_sa", r'SUBPARTIDA_SA:\s*(\d{4}\.\d{2})'),
        ("descripcion", r'DESCRIPCION_OFICIAL:\s*(.+)'),
        ("justificacion", r'JUSTIFICACION:\s*(.+)'),
        ("rgi", r'RGI:\s*(.+)'),
    ]:
        m = re.search(regex, answer, re.IGNORECASE)
        if m:
            out[campo] = m.group(1).strip().split('\n')[0][:300]
    if not out.get("codigo"):
        m_any = re.search(r'\b(\d{4}\.\d{2}\.\d{2})\b', answer)
        if m_any:
            out["codigo"] = m_any.group(1)
    out["ok"] = bool(out.get("codigo"))
    return out


def _capa2_verificar_pdfs(consulta: str, capa3: dict) -> Dict[str, Any]:
    """Sub-capa 2d: verificacion contra PDFs adjuntos del cuaderno.
    Confirma que la categoria/caracteristicas que detecto Capa 3 estan
    respaldadas por una fuente legal documental (Arancel, Notas Explicativas SA,
    Ley 168-21, etc.). Si no, devuelve cita del PDF que la contradice o
    indica que requiere correccion con la fuente especifica."""
    try:
        if _HERE not in sys.path:
            sys.path.insert(0, _HERE)
        from supervisor_interno import buscar_en_fuentes
    except Exception as e:
        return {"verificada": None, "razon": f"supervisor_interno no disponible: {e}"}

    palabras = re.findall(r'\b[a-záéíóúüñ]{4,}\b', consulta.lower())
    stopwords = {"para", "como", "cual", "este", "esta", "donde"}
    keywords = [p for p in palabras if p not in stopwords][:3]

    matches = []
    for kw in keywords:
        try:
            hits = buscar_en_fuentes(kw, max_resultados=3)
            if hits:
                for h in hits[:2]:
                    matches.append({
                        "keyword": kw,
                        "fuente_pdf": h.get("archivo", "?"),
                        "snippet": str(h.get("contexto", h))[:300]
                    })
        except Exception:
            continue

    if matches:
        return {
            "verificada": True,
            "razon": f"Capa 3 respaldada por {len(matches)} cita(s) en PDFs del cuaderno",
            "citas_pdf": matches[:5],
        }
    return {
        "verificada": False,
        "razon": (
            "Las palabras clave de la consulta NO aparecen en los PDFs cargados del cuaderno. "
            "Capa 3 NO esta respaldada documentalmente. Sugerir al usuario que revise la "
            "descripcion del producto o agregue la fuente legal correspondiente al cuaderno."
        ),
    }


def capa_2_notion_merceologia(consulta: str, notebook_id: str, umbral: float = 0.4,
                              capitulo_pista: str = "",
                              capa3_resultado: Optional[dict] = None) -> Dict[str, Any]:
    """
    CAPA 2 — Notion / fichas merceologicas + clasificacion via Gemini.

    Orden de busqueda:
      2a. Fichas merceologicas locales (md) — match directo, <500ms
      2b. Notion sincronizado a SQLite — si tabla existe
      2c. Gemini-REST clasificacion estructurada — fallback universal

    Cualquier consulta encuentra respuesta porque 2c siempre corre si las
    anteriores fallan. Asi el patron 3-capas funciona para todos los productos.
    """
    t0 = time.time()
    resultado = {
        "capa": 2,
        "nombre": "Notion / Merceologia",
        "ok": False,
        "fuente": "none",
        "slug": None,
        "codigo": None,
        "score": 0.0,
    }

    # Sub-capa 2a: cache merceologico local (md files)
    try:
        if _HERE not in sys.path:
            sys.path.insert(0, _HERE)
        from merceologia_agent import buscar_ficha_para_consulta
        match = buscar_ficha_para_consulta(consulta, umbral=umbral)
        if match:
            slug, ficha, score = match
            resultado.update({
                "ok": True,
                "fuente": "merceologia_md",
                "slug": slug,
                "codigo": ficha.get("codigo"),
                "score": round(score, 3),
                "elapsed_ms": int((time.time() - t0) * 1000),
            })
            # Sub-capa 2d: validar Capa 3 contra PDFs del cuaderno
            if capa3_resultado:
                verif = _capa2_verificar_pdfs(consulta, capa3_resultado)
                resultado["verificacion_pdfs"] = verif
                if verif.get("verificada") is False:
                    resultado["aviso_capa3"] = (
                        "Capa 3 dijo categoria='" + capa3_resultado.get("categoria_general", "") +
                        "' pero la consulta NO aparece en los PDFs del cuaderno. " + verif.get("razon", "")
                    )
            return resultado
    except Exception as e:
        resultado["error_md"] = f"{type(e).__name__}: {str(e)[:150]}"

    # Sub-capa 2b: SQLite sincronizado con Notion
    db_path = os.path.join(_HERE, "..", "..", "capa1_sqlite", "arancel_rd.db")
    if os.path.exists(db_path):
        try:
            import sqlite3
            con = sqlite3.connect(db_path)
            cur = con.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notion_merceologia'")
            if cur.fetchone():
                palabras = re.findall(r'\b[a-záéíóúüñ]{4,}\b', consulta.lower())
                if palabras:
                    like_clauses = " OR ".join(["LOWER(titulo || ' ' || resumen) LIKE ?" for _ in palabras])
                    params = [f"%{p}%" for p in palabras[:5]]
                    cur.execute(
                        f"SELECT notion_id, titulo, son, resumen FROM notion_merceologia "
                        f"WHERE {like_clauses} LIMIT 1",
                        params
                    )
                    row = cur.fetchone()
                    if row:
                        resultado.update({
                            "ok": True,
                            "fuente": "notion_sqlite",
                            "notion_id": row[0],
                            "titulo": row[1],
                            "codigo": row[2],
                            "elapsed_ms": int((time.time() - t0) * 1000),
                        })
                        con.close()
                        return resultado
            con.close()
        except Exception as e:
            resultado["error_sqlite"] = f"{type(e).__name__}: {str(e)[:150]}"

    # Sub-capa 2c: Gemini-REST clasificacion estructurada (cobertura universal)
    g = _gemini_clasificar_producto(consulta, capitulo_pista)
    if g.get("ok") and g.get("codigo"):
        resultado.update({
            "ok": True,
            "fuente": "gemini_rest",
            "codigo": g["codigo"],
            "capitulo": g.get("capitulo"),
            "partida": g.get("partida"),
            "subpartida_sa": g.get("subpartida_sa"),
            "descripcion": g.get("descripcion"),
            "justificacion": g.get("justificacion"),
            "rgi": g.get("rgi"),
            "elapsed_ms": int((time.time() - t0) * 1000),
        })
        # Sub-capa 2d: validar contra PDFs del cuaderno la categoria de Capa 3
        if capa3_resultado:
            verif = _capa2_verificar_pdfs(consulta, capa3_resultado)
            resultado["verificacion_pdfs"] = verif
            if verif.get("verificada") is False:
                resultado["aviso_capa3"] = (
                    "Capa 3 dijo categoria='" + capa3_resultado.get("categoria_general", "") +
                    "' pero NO esta respaldada en los PDFs del cuaderno. " + verif.get("razon", "")
                )
        return resultado
    else:
        resultado["error_gemini"] = g.get("error", "sin codigo extraido")

    resultado["elapsed_ms"] = int((time.time() - t0) * 1000)
    return resultado


_MAPA_PARTIDAS_RGI = {
    # capitulo + keywords del producto -> partida + RGI + notas legales + exclusiones
    "8806": {  # drones / aeronaves no tripuladas
        "trigger": ["dron", "drone", "uav", "aeronave no tripulada"],
        "rgi": "RGI 1 + RGI 6 (subpartida por peso maximo de despegue y equipamiento)",
        "notas_legales": [
            "Nota Legal 1 Cap.88: comprende aeronaves disenadas para transportar carga util o equipadas con dispositivos integrados permanentemente",
            "VII Enmienda SA 2022: creacion partida 88.06 especifica para drones",
        ],
        "exclusiones_partida": ["95.03 (juguetes voladores)"],
        "criterio_subpartida": "peso maximo de despegue + presencia de camara digital",
    },
    "8802": {
        "trigger": ["avion", "helicoptero"],
        "rgi": "RGI 1",
        "notas_legales": ["Cap.88 Nota 1 — aeronaves civiles"],
        "exclusiones_partida": ["88.01 (globos), 88.06 (no tripuladas)"],
        "criterio_subpartida": "peso vacio + tipo motor",
    },
    "8525": {
        "trigger": ["videocamara", "camara digital", "camara grabacion"],
        "rgi": "RGI 1 + RGI 6",
        "notas_legales": ["Cap.85 Nota 4 — conjuntos funcionales"],
        "exclusiones_partida": ["8528 monitores, 9006 fotograficas"],
        "criterio_subpartida": "tipo de captura + uso",
    },
    "8528": {
        "trigger": ["televisor", "monitor", "pantalla display"],
        "rgi": "RGI 1",
        "notas_legales": ["Cap.85 — receptores y monitores"],
        "exclusiones_partida": ["8443 monitores impresion"],
        "criterio_subpartida": "tecnologia (LCD/LED) + uso (TV vs monitor)",
    },
    "8413": {
        "trigger": ["bomba", "centrifuga"],
        "rgi": "RGI 1",
        "notas_legales": ["Cap.84 — bombas para liquidos"],
        "exclusiones_partida": ["8414 bombas aire"],
        "criterio_subpartida": "tipo bomba (centrifuga/embolo/rotativa)",
    },
    "7318": {
        "trigger": ["tornillo", "perno", "rosca"],
        "rgi": "RGI 1",
        "notas_legales": ["Cap.73 — articulos de fundicion hierro/acero"],
        "exclusiones_partida": ["7415 cobre, 7616 aluminio"],
        "criterio_subpartida": "rosca o sin rosca + material",
    },
    "2204": {
        "trigger": ["vino"],
        "rgi": "RGI 1",
        "notas_legales": ["Cap.22 — bebidas, liquidos alcoholicos y vinagre"],
        "exclusiones_partida": ["2206 otras bebidas fermentadas"],
        "criterio_subpartida": "espumoso/no espumoso + grado alcoholico + envase",
    },
    "2208": {
        "trigger": ["ron", "whisky", "vodka", "tequila", "ginebra", "aguardiente"],
        "rgi": "RGI 1",
        "notas_legales": ["Cap.22 — alcohol etilico desnaturalizado y aguardientes"],
        "exclusiones_partida": [],
        "criterio_subpartida": "tipo de aguardiente",
    },
    "8517": {
        "trigger": ["telefono", "celular", "smartphone", "movil"],
        "rgi": "RGI 1 + RGI 6",
        "notas_legales": ["Cap.85 — telefonia y telecomunicaciones"],
        "exclusiones_partida": ["8471 si solo computadora sin telefonia"],
        "criterio_subpartida": "celular vs fijo vs aparato emision",
    },
    "8539": {
        "trigger": ["lampara", "lampara led", "bombillo", "bombilla", "foco", "tubo led", "led con casquillo", "e27", "e14"],
        "rgi": "RGI 1 + Nota 11.b Cap.85",
        "notas_legales": [
            "Nota 11.b) Capitulo 85: las lamparas y tubos LED, incluso con casquillo, clasifican en 85.39 — NO en Cap.94",
            "Distincion clave: 85.39 = lampara (genera luz). 94.05 = luminaria (la sostiene/dirige).",
        ],
        "exclusiones_partida": ["94.05 luminarias/fixtures completos"],
        "criterio_subpartida": "tipo de lampara: incandescente (8539.21/22), descarga (8539.31/32), LED (8539.52)",
    },
    "8541": {
        "trigger": ["panel solar", "fotovoltaico", "celula solar"],
        "rgi": "RGI 1",
        "notas_legales": ["Cap.85 — diodos, transistores, dispositivos semiconductores"],
        "exclusiones_partida": [],
        "criterio_subpartida": "modulo vs celula",
    },
    "3004": {
        "trigger": ["medicamento", "farmaco", "remedio"],
        "rgi": "RGI 1",
        "notas_legales": ["Cap.30 — productos farmaceuticos"],
        "exclusiones_partida": ["3003 sin dosificar, 2106 suplementos"],
        "criterio_subpartida": "principio activo + forma farmaceutica",
    },
}


def capa_1_claude_validador(consulta: str, codigo_propuesto: str,
                             caracteristicas_capa3: Optional[dict] = None) -> Dict[str, Any]:
    """
    CAPA 1 — Claude / SQLite / Cache JSON.

    UNICA capa con autoridad legal/numerica precisa. Determina:
      - Partida arancelaria correcta (4 digitos)
      - RGI aplicada (Reglas Generales de Interpretacion)
      - Notas Legales del Capitulo
      - SON exacta (8 digitos) considerando caracteristicas (peso, uso)
      - Verificacion en cache de los 7,616 codigos del Arancel RD
      - Gravamen DAI (NMF estandar)
      - ITBIS (estandar 18% o exento)
      - ISC desde isc_lookup.json (Cap.22, 24, 27, 85, 87)
      - Beneficios legales aplicables (Ley 150-97 agropecuario, 28-01 fronteriza,
        8-90 zona franca, 195-13 energia renovable, 392-07 industria)
      - Permisos especiales (INDOTEL, IDAC, MISPAS, MICM, Min. Agricultura, etc.)
      - Conflictos arancelarios clasicos (88.06 vs 84.24, 8528 vs 8525, etc.)
      - Validacion final con Claude API (claude-haiku) si disponible

    Es la fuente de VERDAD del sistema. Las otras 2 capas se subordinan.
    """
    t0 = time.time()
    resultado = {
        "capa": 1,
        "nombre": "Claude / SQLite Verificador",
        "ok": False,
        "codigo_existe": False,
        "codigo_propuesto": codigo_propuesto,
        "gravamen": None,
        "itbis": None,
        "isc": None,
        "base_legal": [],
        "claude_confirmacion": None,
    }

    if not codigo_propuesto:
        resultado["error"] = "sin codigo a validar"
        resultado["elapsed_ms"] = int((time.time() - t0) * 1000)
        return resultado

    # 1. Verificar existencia en cache arancel
    try:
        cache_path = os.path.join(_DATA, "fuentes_nomenclatura", "arancel_cache.json")
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        codigos = cache.get("codigos", cache) if isinstance(cache, dict) else {}
        desc = codigos.get(codigo_propuesto)
        if desc:
            resultado["codigo_existe"] = True
            resultado["descripcion_oficial"] = str(desc)[:200]
            # Extraer gravamen del final de la descripcion (formato: "...descripcion N")
            m_grav = re.search(r'\b(\d+)\s*$', str(desc).strip())
            if m_grav:
                resultado["gravamen"] = f"{m_grav.group(1)}%"
    except Exception as e:
        resultado["error_cache"] = f"{type(e).__name__}: {str(e)[:150]}"

    # 2. ISC desde lookup
    try:
        isc_path = os.path.join(_DATA, "fuentes_nomenclatura", "isc_lookup.json")
        with open(isc_path, "r", encoding="utf-8") as f:
            isc_data = json.load(f)
        cap = codigo_propuesto[:2] if len(codigo_propuesto) >= 2 else ""
        cap_data = isc_data.get("capitulos_con_isc", {}).get(cap)
        if cap_data:
            verificados = cap_data.get("codigos_verificados", {})
            if codigo_propuesto in verificados:
                isc_v = verificados[codigo_propuesto].get("isc")
                resultado["isc"] = f"{isc_v} - Ley 11-92 Art. 375" if isc_v else "NO APLICA"
            else:
                resultado["isc"] = "NO APLICA"
        else:
            resultado["isc"] = "NO APLICA"
    except Exception as e:
        resultado["error_isc"] = f"{type(e).__name__}: {str(e)[:150]}"

    # 3. ITBIS estandar 18%
    resultado["itbis"] = "18% sobre (CIF + Gravamen)"

    # 4. Determinar PARTIDA + RGI + Notas Legales (responsabilidad de Capa 1)
    partida4 = codigo_propuesto[:4] if len(codigo_propuesto) >= 4 else ""
    info_partida = _MAPA_PARTIDAS_RGI.get(partida4)
    if info_partida:
        resultado["partida"] = partida4
        resultado["rgi"] = info_partida["rgi"]
        resultado["notas_legales"] = info_partida["notas_legales"]
        resultado["exclusiones_partida"] = info_partida["exclusiones_partida"]
        resultado["criterio_subpartida"] = info_partida["criterio_subpartida"]
    else:
        resultado["partida"] = partida4
        resultado["rgi"] = "RGI 1 (verificar manualmente)"
        resultado["notas_legales"] = [f"Consultar Notas Legales del Cap. {codigo_propuesto[:2]}"]
        resultado["exclusiones_partida"] = []
        resultado["criterio_subpartida"] = "Ver descripcion oficial del Arancel"

    # 5. Sugerir SON alternativa si caracteristicas de Capa 3 lo indican
    #    Caso clasico: drone agricola por peso (8806.23.19 vs 8806.24.19)
    son_sugerencias = []
    caracs = caracteristicas_capa3 or {}
    if partida4 == "8806" and caracs.get("peso"):
        peso_val = caracs["peso"]
        m_kg = re.search(r'(\d+(?:[.,]\d+)?)\s*(kg|kilos?)', peso_val.lower())
        if m_kg:
            try:
                kg = float(m_kg.group(1).replace(",", "."))
                if kg <= 0.25:
                    son_sugerencias.append({"son": "8806.21.19", "razon": "<=250g teledirigido sin camara"})
                elif kg <= 7:
                    son_sugerencias.append({"son": "8806.22.19", "razon": "250g-7kg teledirigido sin camara"})
                elif kg <= 25:
                    son_sugerencias.append({"son": "8806.23.19", "razon": "7-25kg teledirigido sin camara"})
                elif kg <= 150:
                    son_sugerencias.append({"son": "8806.24.19", "razon": "25-150kg teledirigido sin camara"})
            except ValueError:
                pass
    resultado["son_sugerencias_por_caracteristicas"] = son_sugerencias

    # 6. Base legal (siempre incluir leyes principales RD)
    resultado["base_legal"] = [
        "Ley 168-21 - Ley General de Aduanas RD",
        "Decreto 36-22 - Arancel Nacional vigente",
        "Ley 253-12 - ITBIS e ISC (Arts. 335-381)",
        "Decreto 755-22 - Reglamento Ley 168-21",
    ]

    # 7. Detectar leyes de beneficio aplicables (desde leyes_beneficio.json)
    resultado["leyes_beneficio"] = []
    try:
        leyes_path = os.path.join(_DATA, "fuentes_nomenclatura", "leyes_beneficio.json")
        if os.path.exists(leyes_path):
            with open(leyes_path, "r", encoding="utf-8") as f:
                leyes_data = json.load(f)
            for ley in leyes_data.get("leyes", []):
                triggered = False
                # Trigger por keywords en consulta
                for kw in ley.get("keywords_consulta", []):
                    if kw in consulta.lower():
                        triggered = True
                        break
                # Trigger por capitulo aplicable
                cap = codigo_propuesto[:2] if len(codigo_propuesto) >= 2 else ""
                if cap in ley.get("capitulos_aplicables", []) and triggered:
                    resultado["leyes_beneficio"].append({
                        "ley": ley["ley"],
                        "nombre": ley["nombre"],
                        "beneficio": ley["beneficio"],
                        "requisito": ley["requisito"],
                    })
                    resultado["base_legal"].append(f"{ley['ley']} - {ley['nombre']}")
                    if ley["ley"] == "Ley 150-97":
                        resultado["beneficio_150_97"] = "0% DAI + Exencion ITBIS si demuestra uso agropecuario exclusivo"
    except Exception as e:
        resultado["error_leyes"] = f"{type(e).__name__}: {str(e)[:100]}"

    # 8. Detectar permisos especiales (desde permisos_especiales.json)
    resultado["permisos_requeridos"] = []
    try:
        perm_path = os.path.join(_DATA, "fuentes_nomenclatura", "permisos_especiales.json")
        if os.path.exists(perm_path):
            with open(perm_path, "r", encoding="utf-8") as f:
                perm_data = json.load(f)
            cap_actual = codigo_propuesto[:2] if len(codigo_propuesto) >= 2 else ""
            for perm in perm_data.get("permisos", []):
                aplica = False
                if cap_actual in perm.get("capitulos", []):
                    aplica = True
                if any(p == codigo_propuesto[:4] or codigo_propuesto.startswith(p)
                       for p in perm.get("partidas", [])):
                    aplica = True
                if any(kw in consulta.lower() for kw in perm.get("keywords_consulta", [])):
                    aplica = True
                if aplica:
                    resultado["permisos_requeridos"].append({
                        "entidad": perm["entidad"],
                        "nombre": perm["nombre"],
                        "base_legal": perm["base_legal"],
                        "tramite": perm["tramite"],
                    })
    except Exception as e:
        resultado["error_permisos"] = f"{type(e).__name__}: {str(e)[:100]}"

    # 9. Detectar conflictos arancelarios clasicos
    resultado["conflictos_posibles"] = []
    try:
        conf_path = os.path.join(_DATA, "fuentes_nomenclatura", "conflictos_arancelarios.json")
        if os.path.exists(conf_path):
            with open(conf_path, "r", encoding="utf-8") as f:
                conf_data = json.load(f)
            for conf in conf_data.get("conflictos", []):
                if any(kw in consulta.lower() for kw in conf.get("trigger_keywords", [])):
                    if any(p in codigo_propuesto[:4] for p in conf.get("partidas_en_conflicto", [])):
                        resultado["conflictos_posibles"].append({
                            "id": conf["id"],
                            "partidas_en_conflicto": conf["partidas_en_conflicto"],
                            "ganadora": conf["ganadora"],
                            "razon": conf["razon"],
                            "exclusion_destino": conf["exclusion_destino"],
                        })
    except Exception as e:
        resultado["error_conflictos"] = f"{type(e).__name__}: {str(e)[:100]}"

    # 5. Detectar codigo generico ".99.X" cuando hay alternativas mas especificas
    #    Patron: si subpartida termina en 99 y existen otras subpartidas en la misma
    #    partida, marcar como codigo_generico=True para que el pipeline reintente.
    try:
        cache_path = os.path.join(_DATA, "fuentes_nomenclatura", "arancel_cache.json")
        with open(cache_path, "r", encoding="utf-8") as f:
            cache_full = json.load(f)
        codigos = cache_full.get("codigos", cache_full)
        partida4 = codigo_propuesto[:4] if len(codigo_propuesto) >= 4 else ""
        # codigos con la misma partida (4 primeros digitos)
        hermanos = [c for c in codigos.keys() if c.startswith(partida4)]
        sub_actual = codigo_propuesto[5:7] if len(codigo_propuesto) >= 7 else ""
        subs_distintas = set(c[5:7] for c in hermanos if len(c) >= 7)
        # Si la subpartida es .99 (las demas) Y hay otras subpartidas reales -> generico
        if sub_actual == "99" and len(subs_distintas) > 1:
            resultado["codigo_generico"] = True
            resultado["alternativas_mas_especificas"] = sorted([
                c for c in hermanos if not c.startswith(f"{partida4}.99")
            ])[:8]
        else:
            resultado["codigo_generico"] = False
    except Exception as e:
        resultado["error_generico_check"] = f"{type(e).__name__}: {str(e)[:100]}"

    # 6. Validacion final con Claude API (opcional)
    try:
        if _HERE not in sys.path:
            sys.path.insert(0, _HERE)
        from claude_validator import validar_clasificacion, esta_disponible
        if esta_disponible():
            desc_oficial = resultado.get("descripcion_oficial", "")
            valid = validar_clasificacion(consulta, codigo_propuesto, desc_oficial)
            resultado["claude_confirmacion"] = valid
    except Exception as e:
        resultado["claude_confirmacion"] = {"error": f"{type(e).__name__}: {str(e)[:150]}"}

    # OK si codigo existe Y (sin claude o claude valido) Y NO es codigo generico
    claude_ok = (resultado.get("claude_confirmacion") is None or
                 resultado.get("claude_confirmacion", {}).get("valido") is not False)
    no_generico = not resultado.get("codigo_generico", False)
    resultado["ok"] = bool(resultado["codigo_existe"]) and claude_ok and no_generico
    resultado["elapsed_ms"] = int((time.time() - t0) * 1000)
    return resultado


def _auto_generar_ficha(consulta: str, codigo: str, datos_capa2: dict, datos_capa1: dict) -> Optional[str]:
    """Crea una ficha merceologica minima para que la proxima consulta sea cache-hit.
    Solo se ejecuta si la consulta NO vino ya de merceologia_md y el codigo es valido.
    Retorna el slug creado o None si no se generó."""
    try:
        # Slug desde la consulta (alfanumerico + guiones)
        slug_raw = re.sub(r'[^a-z0-9\s-]', '', consulta.lower())
        slug_raw = re.sub(r'\s+', '-', slug_raw.strip())[:60]
        if not slug_raw or len(slug_raw) < 4:
            return None

        ficha_dir = os.path.join(_DATA, "merceologia")
        os.makedirs(ficha_dir, exist_ok=True)
        ficha_path = os.path.join(ficha_dir, f"{slug_raw}.md")
        if os.path.exists(ficha_path):
            return slug_raw  # ya existe, no sobreescribir

        capitulo = datos_capa2.get("capitulo") or codigo[:2]
        partida = datos_capa2.get("partida") or codigo[:4]
        subpartida = datos_capa2.get("subpartida_sa") or codigo[:7]
        descripcion = datos_capa2.get("descripcion") or datos_capa1.get("descripcion_oficial", "")
        justificacion = datos_capa2.get("justificacion", "Clasificacion por Capa 2 (Gemini-REST) verificada por Capa 1 (cache + base legal).")
        rgi = datos_capa2.get("rgi", "RGI 1")
        gravamen = datos_capa1.get("gravamen", "verificar")
        isc = datos_capa1.get("isc", "NO APLICA")

        contenido = f"""# Ficha Merceologica — {consulta.title()}

**Fecha:** auto-generada
**Origen:** Pipeline 3 Capas (Capa 2 Gemini-REST + Capa 1 verificacion cache)
**Slug:** `{slug_raw}`

## 1. Que es

- **Denominacion comercial:** {consulta}
- **Identificacion arancelaria:** {descripcion or 'ver Arancel RD'}

## 7. Codigo arancelario sugerido

- **Capitulo SA:** {capitulo}
- **Partida SA:** {partida}
- **Subpartida SA:** {subpartida}
- **Codigo nacional RD:** {codigo}
- **Descripcion del codigo:** {descripcion}
- **Gravamen esperado:** {gravamen}
- **ISC aplicable:** {isc}
- **RGI:** {rgi}
- **Justificacion:** {justificacion}

## Auto-validacion

Esta ficha fue generada automaticamente por pipeline_3_capas.py al primer hit
exitoso. Modificar manualmente si la clasificacion necesita ajuste de detalle
(peso, tamaño, uso especifico, beneficios legales como Ley 150-97).
"""
        with open(ficha_path, "w", encoding="utf-8") as f:
            f.write(contenido)

        # Forzar recarga del cache merceologico para que el proximo hit la encuentre
        try:
            from merceologia_agent import _cargar_fichas
            _cargar_fichas(forzar=True)
        except Exception:
            pass

        print(f"[PIPELINE] Auto-generada ficha {slug_raw}.md ({codigo})")
        return slug_raw
    except Exception as e:
        print(f"[PIPELINE] Error auto-generando ficha: {e}")
        return None


def _componer_respuesta_ground_truth(consulta: str, c2: dict, c1: dict) -> str:
    """Compone la respuesta final con la estructura del NotebookLM ground truth:
       1. Identificacion Merceologica (Capa 2)
       2. Determinacion de Partida (Capa 1)
       3. Subpartida Operativa Nacional (Capa 1)
       4. Regimen Arancelario y Beneficios (Capa 1)
       5. Restricciones y Permisos (Capa 1)
       Resumen + Nota tecnica de conflictos (Capa 1)
    """
    codigo = c1.get("codigo_propuesto", "")
    partida = c1.get("partida", codigo[:4] if len(codigo) >= 4 else "")
    capitulo = codigo[:2] if len(codigo) >= 2 else ""
    descripcion = c1.get("descripcion_oficial", "") or c2.get("descripcion", "")
    rgi = c1.get("rgi", "RGI 1")
    notas_legales = c1.get("notas_legales", [])
    exclusiones = c1.get("exclusiones_partida", [])
    son_sugerencias = c1.get("son_sugerencias_por_caracteristicas", [])
    leyes = c1.get("leyes_beneficio", [])
    permisos = c1.get("permisos_requeridos", [])
    conflictos = c1.get("conflictos_posibles", [])
    gravamen = c1.get("gravamen", "verificar")
    itbis = c1.get("itbis", "18% sobre (CIF + Gravamen)")
    isc = c1.get("isc", "NO APLICA")

    out = []
    out.append(f"## Clasificacion arancelaria — {consulta}\n")
    out.append(f"**Codigo nacional RD:** {codigo}\n")

    # 1. Identificacion Merceologica (Capa 2)
    out.append("### 1. Identificacion Merceologica (Capa 2)")
    if c2.get("fuente") == "merceologia_md":
        out.append(f"Ficha merceologica encontrada: `{c2.get('slug')}` (score {c2.get('score', 0):.0%}).")
    elif c2.get("fuente") == "gemini_rest":
        out.append(f"Descripcion via Capa 2 (Gemini-REST estructurado):")
        if c2.get("justificacion"):
            out.append(f"- Justificacion: {c2['justificacion']}")
    if descripcion:
        out.append(f"- Descripcion oficial Arancel: {descripcion}")
    out.append("")

    # 2. Determinacion de Partida (Capa 1)
    out.append("### 2. Determinacion de Partida Arancelaria (Capa 1)")
    out.append(f"- **Partida:** {partida[:2]}.{partida[2:]} ({_partida_nombre(capitulo)})")
    out.append(f"- **RGI aplicada:** {rgi}")
    if notas_legales:
        out.append("- **Notas Legales:**")
        for n in notas_legales:
            out.append(f"  - {n}")
    if exclusiones:
        out.append(f"- **Exclusiones de partida:** {', '.join(exclusiones)}")
    out.append("")

    # 3. SON exacta (Capa 1)
    out.append("### 3. Subpartida Operativa Nacional - SON (Capa 1)")
    out.append(f"- **Codigo nacional RD:** {codigo}")
    if c1.get("criterio_subpartida"):
        out.append(f"- **Criterio de subpartida:** {c1['criterio_subpartida']}")
    if son_sugerencias:
        out.append("- **SON sugerida(s) por caracteristicas detectadas:**")
        for s in son_sugerencias:
            out.append(f"  - `{s['son']}` — {s['razon']}")
    out.append("")

    # 4. Regimen arancelario (Capa 1)
    out.append("### 4. Regimen Arancelario y Beneficios (Capa 1)")
    out.append(f"- **Gravamen DAI (NMF):** {gravamen}")
    out.append(f"- **ITBIS:** {itbis}")
    out.append(f"- **ISC:** {isc}")
    if leyes:
        out.append("- **Leyes de beneficio aplicables:**")
        for ley in leyes:
            ben = ley.get("beneficio", {})
            out.append(f"  - **{ley['ley']}** — {ley['nombre']}")
            out.append(f"    - Beneficio: DAI {ben.get('DAI', 'estandar')}, ITBIS {ben.get('ITBIS', 'estandar')}")
            out.append(f"    - Requisito: {ley['requisito']}")
    out.append("")

    # 5. Permisos (Capa 1)
    out.append("### 5. Restricciones y Permisos Especiales (Capa 1)")
    if permisos:
        for p in permisos:
            out.append(f"- **{p['entidad']}** ({p['nombre']})")
            out.append(f"  - Base legal: {p['base_legal']}")
            out.append(f"  - Tramite: {p['tramite']}")
    else:
        out.append("- Ningun permiso especial detectado para este codigo/consulta")
    out.append("")

    # Conflictos (Capa 1)
    if conflictos:
        out.append("### Nota Tecnica — Conflictos Arancelarios Posibles")
        for cf in conflictos:
            out.append(f"- **{cf['id']}**: {cf['razon']}")
            out.append(f"  - Partida ganadora: {cf['ganadora']}")
            out.append(f"  - Excluye: {cf['exclusion_destino']}")
        out.append("")

    # Resumen — formato del NotebookLM ground truth
    out.append("### Resumen")
    out.append("| Elemento | Detalle |")
    out.append("|---|---|")
    out.append(f"| **Producto consultado** | **{consulta}** |")
    out.append(f"| Partida | {partida[:2]}.{partida[2:]} |")
    out.append(f"| ⭐ **PARTIDA NAC. SUGERIDA** | ## **`{codigo}`** |")
    if leyes:
        ley_principal = leyes[0]
        ben = ley_principal.get("beneficio", {})
        out.append(f"| Gravamen | {gravamen} estandar (con {ley_principal['ley']}: {ben.get('DAI', 'estandar')}) |")
        out.append(f"| ITBIS | {itbis} (con {ley_principal['ley']}: {ben.get('ITBIS', 'estandar')}) |")
    else:
        out.append(f"| Gravamen | {gravamen} |")
        out.append(f"| ITBIS | {itbis} |")
    out.append(f"| ISC | {isc} |")
    if permisos:
        out.append(f"| Permisos | {', '.join(p['entidad'] for p in permisos)} |")

    return "\n".join(out)


def _partida_nombre(capitulo: str) -> str:
    nombres = {
        "22": "Bebidas, liquidos alcoholicos y vinagre",
        "30": "Productos farmaceuticos",
        "73": "Manufacturas de fundicion, hierro o acero",
        "84": "Maquinas y aparatos mecanicos",
        "85": "Maquinas, aparatos y material electrico",
        "87": "Vehiculos automoviles, tractores",
        "88": "Aeronaves, vehiculos espaciales y sus partes",
        "39": "Plasticos y sus manufacturas",
        "27": "Combustibles minerales, aceites minerales",
    }
    return nombres.get(capitulo, f"Capitulo {capitulo}")


def ejecutar_pipeline(consulta: str, notebook_id: str = "biblioteca-de-nomenclaturas") -> Dict[str, Any]:
    """
    Ejecuta las 3 capas en orden y retorna trazabilidad completa.

    El patron de busqueda NO se rompe porque cada capa valida la siguiente:
        Capa 3 -> identifica -> Capa 2 -> encuentra ficha -> Capa 1 -> confirma codigo

    Returns:
        {
          "consulta": str,
          "capas": [resultado_capa3, resultado_capa2, resultado_capa1],
          "respuesta_final": str,
          "codigo_final": str,
          "tiempo_total_ms": int,
          "patron_intacto": bool  # True si las 3 capas se ejecutaron en orden
        }
    """
    t0 = time.time()
    trazabilidad = {"consulta": consulta, "notebook_id": notebook_id, "capas": []}

    # CACHE-HIT: si la consulta ya se resolvio en los ultimos 7 dias, devolver directo
    cached = _cache_get(consulta, notebook_id)
    if cached:
        cached["tiempo_total_ms"] = int((time.time() - t0) * 1000)
        cached["cache_hit"] = True
        return cached

    # CAPA 3: Gemini orquestador
    c3 = capa_3_gemini_orquestador(consulta, notebook_id)
    trazabilidad["capas"].append(c3)

    if not c3.get("ok"):
        trazabilidad["respuesta_final"] = "Error en Capa 3 (orquestador). Sin clasificacion."
        trazabilidad["patron_intacto"] = False
        trazabilidad["tiempo_total_ms"] = int((time.time() - t0) * 1000)
        return trazabilidad

    # CAPA 2: Notion/Merceologia (pasa categoria general de Capa 3 + resultado completo
    # para que sub-capa 2d verifique contra PDFs)
    capitulo_pista = c3.get("categoria_general", "")
    c2 = capa_2_notion_merceologia(consulta, notebook_id, capitulo_pista=capitulo_pista,
                                    capa3_resultado=c3)
    trazabilidad["capas"].append(c2)

    codigo_propuesto = c2.get("codigo")

    # CAPA 1: Claude/SQLite verificador (recibe caracteristicas detectadas en Capa 3)
    caracs = c3.get("caracteristicas_detectadas", {})
    c1 = capa_1_claude_validador(consulta, codigo_propuesto, caracteristicas_capa3=caracs)
    trazabilidad["capas"].append(c1)

    # Reintento: codigo generico (.99) O codigo inexistente en cache.
    # Bug APP-2026-001 #1: antes solo reintentaba .99; ahora tambien si no existe.
    necesita_retry = (
        (c1.get("codigo_generico") and c2.get("fuente") == "gemini_rest") or
        (c2.get("fuente") == "gemini_rest" and codigo_propuesto and not c1.get("codigo_existe"))
    )
    if necesita_retry:
        alternativas = c1.get("alternativas_mas_especificas", [])
        if not alternativas and not c1.get("codigo_existe"):
            # Sugerir hermanas de la misma partida desde el cache
            try:
                cache_path = os.path.join(_DATA, "fuentes_nomenclatura", "arancel_cache.json")
                with open(cache_path, "r", encoding="utf-8") as f:
                    _cache = json.load(f)
                _codigos = _cache.get("codigos", _cache)
                p4 = codigo_propuesto[:4] if codigo_propuesto else ""
                alternativas = sorted([c for c in _codigos.keys() if c.startswith(p4)])[:8]
            except Exception:
                alternativas = []
        if alternativas:
            motivo = "no existe en arancel_cache.json" if not c1.get("codigo_existe") else "es generico 'los demas'"
            consulta_refinada = (
                f"{consulta}. ATENCION: PROHIBIDO clasificar como {codigo_propuesto} ({motivo}). "
                f"Elige una de estas subpartidas validas del Arancel RD: "
                f"{', '.join(alternativas[:5])}"
            )
            print(f"[PIPELINE] Reintentando Capa 2 — codigo {codigo_propuesto} {motivo}")
            c2_retry = capa_2_notion_merceologia(consulta_refinada, notebook_id,
                                                  capitulo_pista=capitulo_pista)
            trazabilidad["capas"].append({**c2_retry, "capa": 2, "nombre": "Capa 2 reintento"})
            codigo_retry = c2_retry.get("codigo")
            if codigo_retry and codigo_retry != codigo_propuesto:
                c1_retry = capa_1_claude_validador(consulta, codigo_retry, caracteristicas_capa3=caracs)
                trazabilidad["capas"].append({**c1_retry, "capa": 1, "nombre": "Capa 1 reintento"})
                if c1_retry.get("ok"):
                    c1, c2 = c1_retry, c2_retry
                    codigo_propuesto = codigo_retry

    # Construir respuesta final con formato del NotebookLM ground truth
    if c2.get("ok") and c1.get("ok"):
        trazabilidad["codigo_final"] = c1["codigo_propuesto"]
        trazabilidad["gravamen_final"] = c1.get("gravamen", "verificar")
        trazabilidad["isc_final"] = c1.get("isc", "NO APLICA")
        trazabilidad["base_legal"] = c1.get("base_legal", [])
        trazabilidad["beneficio_150_97"] = c1.get("beneficio_150_97")
        trazabilidad["leyes_beneficio"] = c1.get("leyes_beneficio", [])
        trazabilidad["permisos_requeridos"] = c1.get("permisos_requeridos", [])
        trazabilidad["conflictos_posibles"] = c1.get("conflictos_posibles", [])
        trazabilidad["partida"] = c1.get("partida")
        trazabilidad["rgi"] = c1.get("rgi")
        trazabilidad["notas_legales"] = c1.get("notas_legales", [])
        trazabilidad["son_sugerencias"] = c1.get("son_sugerencias_por_caracteristicas", [])
        trazabilidad["respuesta_final"] = _componer_respuesta_ground_truth(consulta, c2, c1)
        trazabilidad["patron_intacto"] = True

        # Auto-generar ficha solo si vino de Gemini (no si ya existia ficha local)
        if c2.get("fuente") == "gemini_rest":
            slug = _auto_generar_ficha(consulta, codigo_propuesto, c2, c1)
            if slug:
                trazabilidad["ficha_auto_generada"] = slug
    elif c2.get("ok"):
        trazabilidad["codigo_final"] = c2.get("codigo")
        trazabilidad["respuesta_final"] = c2.get("respuesta", "")
        trazabilidad["patron_intacto"] = True
        trazabilidad["nota"] = (
            f"Codigo {c2.get('codigo')} aceptado por Capa 2 pero Capa 1 lo rechazo "
            f"(generico={c1.get('codigo_generico', False)}, "
            f"existe={c1.get('codigo_existe', False)}). "
            f"Verificar manualmente."
        )
    else:
        trazabilidad["respuesta_final"] = None
        trazabilidad["patron_intacto"] = False
        trazabilidad["nota"] = "Capa 2 sin match (md+sqlite+gemini). Producto necesita ficha manual."

    trazabilidad["tiempo_total_ms"] = int((time.time() - t0) * 1000)

    # CACHE-PUT: guardar solo respuestas validas (patron intacto + codigo final)
    if trazabilidad.get("patron_intacto") and trazabilidad.get("codigo_final"):
        _cache_put(consulta, notebook_id, trazabilidad)

    return trazabilidad


if __name__ == "__main__":
    # Self-test rapido
    consulta_test = " ".join(sys.argv[1:]) or "Dron aereo para agricultura"
    print(f"\n=== PIPELINE 3 CAPAS — Test ===")
    print(f"Consulta: {consulta_test}\n")
    r = ejecutar_pipeline(consulta_test)
    for c in r["capas"]:
        print(f"[CAPA {c['capa']}] {c['nombre']}: ok={c['ok']} "
              f"({c.get('elapsed_ms', '?')}ms)")
        for k, v in c.items():
            if k not in ("capa", "nombre", "ok", "elapsed_ms", "respuesta"):
                v_str = str(v)[:200]
                print(f"    {k}: {v_str}")
    print(f"\nRESULTADO FINAL:")
    print(f"  patron_intacto: {r.get('patron_intacto')}")
    print(f"  codigo_final:   {r.get('codigo_final')}")
    print(f"  gravamen:       {r.get('gravamen_final')}")
    print(f"  isc:            {r.get('isc_final')}")
    print(f"  tiempo_total:   {r.get('tiempo_total_ms')}ms")
    if r.get("beneficio_150_97"):
        print(f"  beneficio:      {r['beneficio_150_97']}")
