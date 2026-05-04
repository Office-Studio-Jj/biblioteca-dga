"""
Sub-agente [MAESTRO] — CLASIFICADOR MERCEOLOGICO AUTO (5 Agentes + 7 Pasos)
CEO Informe 04-MAY-2026: Protocolo de Resolución de Conflictos entre Partidas

Pipeline de 5 Agentes:
  [1] GUARDIAN DE ENTRADA   → Identifica funcion/materia/tipo, detecta partes
  [2] CAZADOR DE CANDIDATAS → Busqueda exhaustiva multi-nivel + sinonimos
  [3] FISCAL MERCEOLOGICO   → Matriz comparativa + score coherencia + Notas Legales
  [4] JUEZ DE RGI           → Aplicacion secuencial obligatoria RGI 1→2a→2b→3a→3b→3c→6
  [5] DICTAMINADOR FINAL    → Validacion final + gravamen + dictamen documentado

Regla CEO: NUNCA retornar resultado sin que los 5 agentes hayan ejecutado.

API:
    clasificar_producto(descripcion: str, publicar_notion: bool = False) -> dict
"""
import json
import os
import re
import sys
import time
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sub_agentes.lector_notas_arancel import (
    leer_notas_capitulo,
    formatear_notas_gemini,
)
from sub_agentes.investigador_biblioteca import (
    investigar,
    formatear_contexto_gemini,
)
from capa1_sqlite.orquestador_capa3 import (
    consultar_son_exacto,
    buscar_clasificacion_sugerida,
    buscar_sinonimos,
    buscar_partes_producto,
    registrar_conflicto,
)

_SON_RE = re.compile(r'\b(\d{4}\.\d{2}\.\d{2}(?:\.\d{2})?)\b')

# ── Datos de exclusion entre capitulos (BUG-003/BUG-004) ──────────────────
_NOTAS_EXCLUSION_PATH = os.path.join(
    _HERE, "..", "notebooklm_skill", "data", "fuentes_nomenclatura", "notas_exclusion.json"
)
_EXCLUSIONES_CACHE: list | None = None


def _cargar_exclusiones() -> list:
    global _EXCLUSIONES_CACHE
    if _EXCLUSIONES_CACHE is not None:
        return _EXCLUSIONES_CACHE
    try:
        with open(_NOTAS_EXCLUSION_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        _EXCLUSIONES_CACHE = data.get("exclusiones", [])
    except Exception as e:
        print(f"[CLASIF-AUTO] Error cargando notas_exclusion.json: {e}")
        _EXCLUSIONES_CACHE = []
    return _EXCLUSIONES_CACHE


def validar_exclusion_capitulos(
    capitulo_propuesto: str,
    descripcion_producto: str,
    criterio_0: str = "",
    notas_context: dict | None = None,
) -> dict:
    exclusiones = _cargar_exclusiones()
    desc_lower = descripcion_producto.lower()
    cap = str(capitulo_propuesto).strip().zfill(2)

    for ex in exclusiones:
        if ex.get("capitulo_excluye") != cap:
            continue
        patrones = ex.get("producto_patron", [])
        match_patron = any(p.lower() in desc_lower for p in patrones)
        if not match_patron:
            continue
        excepcion = (ex.get("excepcion") or "").lower()
        if excepcion and excepcion in desc_lower:
            continue
        if criterio_0 and ex.get("criterio_0"):
            if criterio_0.upper() != ex["criterio_0"].upper():
                continue
        return {
            "aprobado": False, "excluido": True,
            "capitulo_propuesto": cap,
            "capitulo_final": ex["capitulo_incluye"],
            "partida_alternativa": ex.get("partida_incluye", ""),
            "norma_citada": ex.get("fuente", "Decreto 755-22"),
            "texto_nota": ex.get("texto_nota", ""),
            "rgi_aplicada": "RGI_1",
            "razon": f"Nota Legal excluye Cap. {cap} -> redirigir a Cap. {ex['capitulo_incluye']}",
        }
    return {
        "aprobado": True, "excluido": False,
        "capitulo_final": cap, "norma_citada": "",
        "rgi_aplicada": "RGI_1_VALIDADO",
        "razon": f"Cap. {cap} no excluido para '{descripcion_producto[:80]}'",
    }


# ── Diccionario de términos ambiguos ──────────────────────────────────────

_TERMINOS_AMBIGUOS: dict[str, dict] = {
    "scooter":      {"headings": ["87.11", "87.12", "87.03"],
                     "preguntas": "¿Tiene motor de combustión interna (sí/no)? ¿Velocidad máxima (km/h)? Adjunte ficha técnica."},
    "scooters":     {"headings": ["87.11", "87.12", "87.03"],
                     "preguntas": "¿Tiene motor de combustión interna (sí/no)? ¿Velocidad máxima (km/h)? Adjunte ficha técnica."},
    "motor":        {"headings": ["84.07", "84.08", "85.01"],
                     "preguntas": "¿Tipo de motor (combustión interna / eléctrico)? ¿Uso previsto? ¿Potencia (kW)?"},
    "motores":      {"headings": ["84.07", "84.08", "85.01"],
                     "preguntas": "¿Tipo de motor (combustión interna / eléctrico)? ¿Uso previsto? ¿Potencia (kW)?"},
    "batería":      {"headings": ["85.06", "85.07", "85.39"],
                     "preguntas": "¿Es recargable (sí/no)? ¿Química (Li-ion, plomo, alcalina)?"},
    "bateria":      {"headings": ["85.06", "85.07", "85.39"],
                     "preguntas": "¿Es recargable (sí/no)? ¿Química (Li-ion, plomo, alcalina)?"},
    "panel":        {"headings": ["85.41", "76.10", "94.06"],
                     "preguntas": "¿Material? ¿Función (solar, estructural, decorativo)?"},
    "paneles":      {"headings": ["85.41", "76.10", "94.06"],
                     "preguntas": "¿Material? ¿Función (solar, estructural, decorativo)?"},
    "cable":        {"headings": ["74.13", "76.05", "85.44"],
                     "preguntas": "¿Material (cobre, aluminio, acero)? ¿Uso eléctrico (sí/no)?"},
    "cables":       {"headings": ["74.13", "76.05", "85.44"],
                     "preguntas": "¿Material (cobre, aluminio, acero)? ¿Uso eléctrico (sí/no)?"},
    "equipo":       {"headings": ["Cap.84", "Cap.85", "Cap.90"],
                     "preguntas": "¿Función específica del equipo? ¿Sector de uso?"},
    "equipos":      {"headings": ["Cap.84", "Cap.85", "Cap.90"],
                     "preguntas": "¿Función específica del equipo? ¿Sector de uso?"},
    "dispositivo":  {"headings": ["Cap.84", "Cap.85", "Cap.90"],
                     "preguntas": "¿Función específica? ¿Sector de uso?"},
    "dispositivos": {"headings": ["Cap.84", "Cap.85", "Cap.90"],
                     "preguntas": "¿Función específica? ¿Sector de uso?"},
    "accesorio":    {"headings": ["múltiples capítulos"],
                     "preguntas": "¿Accesorio de qué producto principal?"},
    "accesorios":   {"headings": ["múltiples capítulos"],
                     "preguntas": "¿Accesorio de qué producto principal?"},
    "repuesto":     {"headings": ["múltiples capítulos"],
                     "preguntas": "¿Repuesto de qué máquina o sistema?"},
    "repuestos":    {"headings": ["múltiples capítulos"],
                     "preguntas": "¿Repuesto de qué máquina o sistema?"},
}

_TECH_QUALIFIERS = {
    "electrico", "electrica", "electricos", "electricas",
    "eléctrico", "eléctrica", "eléctricos", "eléctricas",
    "combustion", "combustión", "gasolina", "diesel", "diésel",
    "cilindro", "cilindros", "cc", "kw", "hp", "cv", "watts",
    "voltio", "voltios", "volt", "amperio", "amperios", "amp",
    "litio", "plomo", "alcalina", "niquel", "hidruro",
    "cobre", "aluminio", "acero", "hierro", "zinc", "bronce",
    "solar", "fotovoltaico", "monocristalino", "policristalino",
    "recargable", "primaria", "secundaria",
    "patineta", "ciclomotor", "vespa", "kick", "bicicleta",
    "sin motor", "con motor",
    "hdmi", "usb", "usb-c", "usb-a", "usb-b", "usb3", "usb4", "lightning",
    "ethernet", "rj45", "cat5", "cat6", "cat7", "cat8",
    "thunderbolt", "displayport", "vga", "dvi",
    "obd", "obd-ii", "obd2",
    "bluetooth", "wifi", "wi-fi", "zigbee", "lte", "nfc",
    "biometrico", "biométrico", "biometric",
    "celular", "telefono", "teléfono", "smartphone",
    "para celular", "de celular", "para telefono",
}


# ── Utilidades Gemini ─────────────────────────────────────────────────────

def _llamar_gemini(prompt: str, timeout: int = 25) -> Optional[str]:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("[CLASIF-AUTO] GEMINI_API_KEY no configurada")
        return None
    try:
        from google import genai
        client = genai.Client(api_key=api_key, http_options={"timeout": timeout})
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return getattr(resp, "text", None) or str(resp)
    except Exception as e:
        print(f"[CLASIF-AUTO] Error Gemini: {e}")
        return None


def _parsear_json_gemini(texto: str) -> Optional[dict]:
    if not texto:
        return None
    m = re.search(r'\{[\s\S]*\}', texto)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        try:
            limpio = m.group(0).replace("'", '"')
            return json.loads(limpio)
        except Exception as e:
            print(f"[CLASIF-AUTO] JSON parse fail: {e}")
            return None


# ── Gate de entrada (pre-agentes) ─────────────────────────────────────────

def validar_entrada(termino: str) -> dict:
    if not termino or not termino.strip():
        return {
            "ok": False, "tipo": "ENTRADA_INSUFICIENTE",
            "mensaje": "Describa el producto con función, material y propulsión. Adjunte ficha técnica.",
        }
    norm = termino.strip().lower()
    norm_tok = re.sub(r"[^\w\sáéíóúñü]", " ", norm, flags=re.UNICODE)
    tokens = norm_tok.split()
    token_set = set(tokens)

    token_ambiguo = None
    for tok in tokens:
        if tok in _TERMINOS_AMBIGUOS:
            token_ambiguo = tok
            break

    if token_ambiguo:
        tiene_qualifier = bool(token_set & _TECH_QUALIFIERS)
        if not tiene_qualifier:
            tiene_qualifier = "sin motor" in norm or "con motor" in norm
        # "para celular", "de celular" son calificadores contextuales
        if not tiene_qualifier:
            tiene_qualifier = any(f in norm for f in ["para celular", "de celular", "para telefono", "de telefono"])
        if not tiene_qualifier:
            info = _TERMINOS_AMBIGUOS[token_ambiguo]
            headings_str = ", ".join(info["headings"])
            return {
                "ok": False, "tipo": "AMBIGUO",
                "termino_ambiguo": token_ambiguo,
                "headings_posibles": info["headings"],
                "mensaje": (
                    f"El término '{token_ambiguo}' puede corresponder a: {headings_str}. "
                    f"Indique: {info['preguntas']}"
                ),
            }
    if len(norm) < 5:
        return {
            "ok": False, "tipo": "ENTRADA_POCO_ESPECIFICA",
            "mensaje": "Descripción insuficiente. Indique función principal, material, propulsión y uso previsto.",
        }
    return {"ok": True}


def validar_salida(son: str, rgi: str = "", fuente_db: dict | None = None) -> dict:
    digits_only = re.sub(r"[^0-9]", "", son or "")
    resultado: dict = {
        "son_validado": son, "nivel_valido": False, "advertencias": [],
        "fuente": "Arancel DGA (www.aduanas.gob.do)",
        "rgi_aplicada": rgi or "Indicar RGI aplicable (RGI 1–6 SA 2022)",
        "base_legal": "Ley 3489 del 14/02/1953 | Ley 168-21 | Decreto 36-22",
        "nota_verificacion": "Validar con aforador acreditado. Fuente definitiva: www.aduanas.gob.do",
    }
    if len(digits_only) < 8:
        resultado["advertencias"].append(
            f"Código '{son}' tiene {len(digits_only)} dígitos — se requieren 8 (XXXX.XX.XX)."
        )
        return resultado
    if not _SON_RE.match((son or "").strip()):
        resultado["advertencias"].append(f"Código '{son}' no cumple formato XXXX.XX.XX.")
        return resultado
    resultado["nivel_valido"] = True
    if fuente_db is not None and not fuente_db:
        resultado["advertencias"].append(f"Código {son} no encontrado en base local. Confirmar en www.aduanas.gob.do.")
    return resultado


# ══════════════════════════════════════════════════════════════════════════
# AGENTE 1 — GUARDIAN DE ENTRADA (Validación Pre-Búsqueda)
# CEO 04-MAY-2026: Entender QUÉ es el producto ANTES de buscar en la BD.
# ══════════════════════════════════════════════════════════════════════════

_PROMPT_GUARDIAN = """Eres el Guardian de Entrada del clasificador arancelario RD (Decreto 755-22).
Tu trabajo es analizar la consulta del usuario ANTES de buscar en la base de datos.

INSTRUCCIONES:
1. Identificar: FUNCION del producto, MATERIA principal, USO destinado
2. Determinar si es un producto completo o una PARTE de otro producto
3. Si es PARTE, identificar el producto principal (ej: pantalla -> parte de telefono celular = partida 8517)
4. Retornar los capitulos arancelarios mas probables (maximo 3)
5. Construir ficha merceologica basica con 8 atributos

REGLA CRITICA: Si el producto es una PARTE, buscar primero en subpartidas de PARTES
del producto principal (Nota Legal Seccion XVI, Nota 2).

Devuelve SOLO JSON:
{{
  "criterio_0": "A|B|C",
  "justificacion_0": "<1 frase>",
  "que_es": "<descripcion breve>",
  "materia": "<material principal>",
  "funcion": "<funcion tecnica principal>",
  "mecanismo_operativo": "<como opera>",
  "especificaciones": "<potencia, tamaño, etc si es relevante>",
  "uso": "<uso tipico>",
  "usuarios": "<quienes lo usan>",
  "caracteristicas_fisicas": "<forma, componentes visibles>",
  "presentacion": "<estado de importacion>",
  "clasificacion": "<uso | naturaleza | funcion>",
  "es_parte": true|false,
  "producto_principal": "<si es parte, de que producto>",
  "partida_producto_principal": "<si es parte, partida del producto principal>",
  "capitulos_probables": ["85","84"],
  "keywords": ["kw1","kw2","kw3","kw4","kw5"],
  "son_sugerido": "<formato XXXX.XX.XX si hay certeza, vacio si no>"
}}

CRITERIO 0 — IDENTIDAD FUNCIONAL:
  [A] adorno personal -> Cap. 71
  [B] distincion/trofeo -> Cap. 83
  [C] uso tecnico/comercial/domestico -> especificar

Producto: {producto}
Responde SOLO con el JSON.
"""


def agente_1_guardian(descripcion: str) -> dict:
    t0 = time.time()

    # Consultar tabla partes_de_productos ANTES de Gemini
    partes_info = buscar_partes_producto(descripcion)
    sinonimos_info = buscar_sinonimos(descripcion)

    prompt = _PROMPT_GUARDIAN.format(producto=descripcion[:500])
    if partes_info:
        prompt += f"\n\nINFO TABLA PARTES: {json.dumps(partes_info, ensure_ascii=False)}"
    if sinonimos_info:
        prompt += f"\n\nINFO SINONIMOS: {json.dumps(sinonimos_info, ensure_ascii=False)}"

    raw = _llamar_gemini(prompt)
    ficha = _parsear_json_gemini(raw) or {}

    for k in ["criterio_0", "justificacion_0", "que_es", "materia", "funcion",
              "mecanismo_operativo", "especificaciones", "uso", "usuarios",
              "caracteristicas_fisicas", "presentacion", "clasificacion", "son_sugerido"]:
        ficha.setdefault(k, "")
    ficha.setdefault("es_parte", False)
    ficha.setdefault("producto_principal", "")
    ficha.setdefault("partida_producto_principal", "")
    ficha.setdefault("keywords", [])
    ficha.setdefault("capitulos_probables", [])

    # Enriquecer con info de tablas SQLite
    if partes_info and not ficha.get("es_parte"):
        ficha["es_parte"] = True
        ficha["producto_principal"] = partes_info[0]["producto_principal"]
        ficha["partida_producto_principal"] = partes_info[0]["partida_principal"]
        if partes_info[0]["partida_principal"][:2] not in ficha["capitulos_probables"]:
            ficha["capitulos_probables"].insert(0, partes_info[0]["partida_principal"][:2])

    if sinonimos_info:
        for s in sinonimos_info:
            cap = s.get("capitulo_sugerido", "")
            if cap and cap not in ficha["capitulos_probables"]:
                ficha["capitulos_probables"].append(cap)

    ficha["_partes_db"] = partes_info
    ficha["_sinonimos_db"] = sinonimos_info
    ficha["_latencia_ms"] = round((time.time() - t0) * 1000, 1)
    ficha["_agente"] = "GUARDIAN"
    return ficha


# ══════════════════════════════════════════════════════════════════════════
# AGENTE 2 — CAZADOR DE CANDIDATAS (Búsqueda Exhaustiva)
# CEO 04-MAY-2026: TODAS las subpartidas SON candidatas. NUNCA solo una.
# ══════════════════════════════════════════════════════════════════════════

def agente_2_cazador(ficha: dict, descripcion: str) -> dict:
    t0 = time.time()
    candidatas = []
    candidatas_set = set()

    def _agregar(son, desc, origen):
        if son not in candidatas_set and _SON_RE.match(son):
            candidatas_set.add(son)
            candidatas.append({"son": son, "descripcion": desc, "origen": origen})

    # 1. Si es parte, buscar en partidas de partes del producto principal
    if ficha.get("es_parte") and ficha.get("partida_producto_principal"):
        partida_pp = ficha["partida_producto_principal"]
        # Buscar SON que empiecen con esa partida (partes)
        partes_db = ficha.get("_partes_db", [])
        for p in partes_db:
            partida_partes = p.get("partida_partes", "")
            if partida_partes and "/" not in partida_partes:
                matches = buscar_clasificacion_sugerida(partida_partes, limit=5)
                for m in matches:
                    _agregar(m["son"], m.get("descripcion", ""), f"partes_db:{p['parte']}")
            elif "/" in partida_partes:
                for pp in partida_partes.split("/"):
                    matches = buscar_clasificacion_sugerida(pp.strip(), limit=3)
                    for m in matches:
                        _agregar(m["son"], m.get("descripcion", ""), f"partes_db:{pp}")

    # 2. Buscar por sinónimos de la tabla
    for s in ficha.get("_sinonimos_db", []):
        termino_of = s.get("termino_oficial", "")
        if termino_of:
            matches = buscar_clasificacion_sugerida(termino_of, limit=5)
            for m in matches:
                _agregar(m["son"], m.get("descripcion", ""), f"sinonimo:{s['termino_busqueda']}")

    # 3. Buscar por descripcion directa + keywords (FTS)
    terminos_busqueda = [
        descripcion,
        ficha.get("que_es", ""),
        ficha.get("funcion", ""),
        ficha.get("materia", ""),
        " ".join(ficha.get("keywords", [])[:5]),
    ]
    for termino in terminos_busqueda:
        if not termino or not termino.strip():
            continue
        matches = buscar_clasificacion_sugerida(termino.strip(), limit=10)
        for m in matches:
            _agregar(m["son"], m.get("descripcion", ""), f"fts:{termino[:30]}")

    # 4. Buscar en capitulos probables del Guardian
    for cap in ficha.get("capitulos_probables", []):
        cap_z = str(cap).strip().zfill(2)
        matches = buscar_clasificacion_sugerida(cap_z, limit=5)
        for m in matches:
            if m["son"][:2] == cap_z:
                _agregar(m["son"], m.get("descripcion", ""), f"capitulo:{cap_z}")

    # 5. Si SON sugerido por Guardian, verificar que exista
    son_sug = ficha.get("son_sugerido", "").strip()
    if son_sug and _SON_RE.match(son_sug):
        exacto = consultar_son_exacto(son_sug)
        if exacto:
            _agregar(son_sug, exacto.get("descripcion", ""), "guardian_sugerido")

    conflicto = len(candidatas) > 1

    return {
        "candidatas": candidatas,
        "total_candidatas": len(candidatas),
        "conflicto_detectado": conflicto,
        "_latencia_ms": round((time.time() - t0) * 1000, 1),
        "_agente": "CAZADOR",
    }


# ══════════════════════════════════════════════════════════════════════════
# AGENTE 3 — FISCAL MERCEOLOGICO (Comparación y Filtrado)
# CEO 04-MAY-2026: Matriz comparativa + score coherencia + Notas Legales
# ══════════════════════════════════════════════════════════════════════════

_PROMPT_FISCAL = """Eres el Fiscal Merceologico del clasificador arancelario RD.
Tu trabajo es evaluar cada candidata contra la ficha merceologica del producto.

FICHA DEL PRODUCTO:
{ficha}

CANDIDATAS A EVALUAR:
{candidatas}

NOTAS LEGALES DEL CAPITULO PRINCIPAL:
{notas}

Para CADA candidata evalua:
1. Coherencia semantica: la descripcion de la SON DESCRIBE al producto? (0-100)
   - 80-100: texto exacto o muy especifico al producto
   - 50-79: texto parcialmente relacionado
   - 20-49: relacion debil o indirecta
   - 0-19: SIN relacion funcional (ej: motor vs pantalla)
2. Especificidad: Alta (texto exacto), Media (texto parcial), Baja (general/residual)
3. Exclusion por Nota Legal: Si alguna nota excluye la candidata, marcar excluida=true
4. RGI aplicable mas probable

ELIMINAR candidata si:
- Score coherencia < 40 (BUG-008 fix)
- Nota Legal la excluye expresamente
- Funcion descrita en la partida es INCOMPATIBLE con funcion del producto

Devuelve SOLO JSON:
{{
  "evaluaciones": [
    {{
      "son": "XXXX.XX.XX",
      "descripcion": "...",
      "score_coherencia": 85,
      "especificidad": "Alta|Media|Baja",
      "excluida": false,
      "razon_exclusion": "",
      "rgi_probable": "RGI 1|3a|6",
      "notas_relevantes": "..."
    }}
  ],
  "candidatas_supervivientes": ["XXXX.XX.XX"],
  "candidatas_descartadas": [
    {{"son": "XXXX.XX.XX", "razon": "Score coherencia 15 - sin relacion funcional"}}
  ]
}}
"""


def agente_3_fiscal(ficha: dict, cazador: dict, notas: dict, descripcion: str) -> dict:
    t0 = time.time()
    candidatas = cazador.get("candidatas", [])

    if not candidatas:
        return {
            "evaluaciones": [], "candidatas_supervivientes": [],
            "candidatas_descartadas": [], "conflicto_resuelto": False,
            "_latencia_ms": 0, "_agente": "FISCAL",
        }

    # Si solo hay 1 candidata, aun asi evaluarla por coherencia (BUG-008 fix)
    candidatas_texto = "\n".join(
        f"- {c['son']}: {c['descripcion'][:100]} (origen: {c['origen']})"
        for c in candidatas[:15]
    )

    prompt = _PROMPT_FISCAL.format(
        ficha=json.dumps({k: v for k, v in ficha.items() if not k.startswith("_")},
                         ensure_ascii=False, indent=2),
        candidatas=candidatas_texto,
        notas=formatear_notas_gemini(notas)[:2000],
    )
    raw = _llamar_gemini(prompt, timeout=30)
    resultado = _parsear_json_gemini(raw) or {}

    evaluaciones = resultado.get("evaluaciones", [])
    supervivientes = []
    descartadas = []

    for ev in evaluaciones:
        score = ev.get("score_coherencia", 0)
        excluida = ev.get("excluida", False)
        if score < 40 or excluida:
            descartadas.append({
                "son": ev.get("son", ""),
                "score": score,
                "razon": ev.get("razon_exclusion", "") or f"Score coherencia {score} < 40",
            })
        else:
            supervivientes.append(ev)

    # Fallback: si Gemini no devolvio evaluaciones, evaluar por texto
    if not evaluaciones and candidatas:
        desc_lower = descripcion.lower()
        for c in candidatas[:10]:
            c_desc = (c.get("descripcion") or "").lower()
            overlap = len(set(desc_lower.split()) & set(c_desc.split()))
            score = min(100, overlap * 20)
            if score >= 40:
                supervivientes.append({
                    "son": c["son"], "descripcion": c.get("descripcion", ""),
                    "score_coherencia": score, "especificidad": "Media",
                    "excluida": False, "rgi_probable": "RGI 1",
                })
            else:
                descartadas.append({"son": c["son"], "score": score, "razon": f"Score {score} < 40 (fallback)"})

    # Ordenar supervivientes por score descendente
    supervivientes.sort(key=lambda x: x.get("score_coherencia", 0), reverse=True)

    return {
        "evaluaciones": supervivientes,
        "candidatas_supervivientes": [s["son"] for s in supervivientes],
        "candidatas_descartadas": descartadas,
        "conflicto_resuelto": len(supervivientes) == 1,
        "_latencia_ms": round((time.time() - t0) * 1000, 1),
        "_agente": "FISCAL",
    }


# ══════════════════════════════════════════════════════════════════════════
# AGENTE 4 — JUEZ DE RGI (Aplicación de Reglas en orden estricto)
# CEO 04-MAY-2026: RGI 1→2a→2b→3a→3b→3c→6. Solo avanzar si anterior no resuelve.
# ══════════════════════════════════════════════════════════════════════════

_PROMPT_JUEZ = """Eres el Juez de RGI del clasificador arancelario RD.
Aplica las Reglas Generales de Interpretacion en ORDEN ESTRICTO para resolver
el conflicto entre las candidatas supervivientes.

PRODUCTO:
{producto}

FICHA MERCEOLOGICA:
{ficha}

CANDIDATAS SUPERVIVIENTES (con scores):
{candidatas}

NOTAS LEGALES:
{notas}

SECUENCIA OBLIGATORIA — solo pasar a la siguiente si la anterior NO resuelve:
1. RGI 1: Texto LITERAL de cada candidata + Notas Legales
2. RGI 2a: Producto incompleto -> clasificar como completo
3. RGI 2b: Mezcla -> caracter esencial
4. RGI 3a: PARTIDA MAS ESPECIFICA prevalece (la mas comun para conflictos)
5. RGI 3b: Caracter esencial para mixtos
6. RGI 3c: Ultima en orden numerico (ultimo recurso)
7. RGI 6: Subpartidas del mismo nivel de guiones

Devuelve SOLO JSON:
{{
  "candidata_ganadora": "XXXX.XX.XX",
  "rgi_aplicada": "RGI 3a",
  "rgi_secuencia": ["RGI 1: no resolvio porque...", "RGI 3a: resolvio porque..."],
  "justificacion": "<3-5 lineas citando RGI y nota legal>",
  "confianza": "alta|media|baja",
  "escalamiento_humano": false,
  "alternativas_ordenadas": ["XXXX.XX.XX", "XXXX.XX.XX"]
}}

Si NINGUNA RGI resuelve: escalamiento_humano = true.
"""


def agente_4_juez_rgi(ficha: dict, fiscal: dict, notas: dict, descripcion: str) -> dict:
    t0 = time.time()
    supervivientes = fiscal.get("evaluaciones", [])

    if not supervivientes:
        return {
            "candidata_ganadora": "", "rgi_aplicada": "",
            "justificacion": "Sin candidatas supervivientes",
            "confianza": "baja", "escalamiento_humano": True,
            "_latencia_ms": 0, "_agente": "JUEZ_RGI",
        }

    # Si solo queda 1, validar con RGI 1 y pasar directo
    if len(supervivientes) == 1:
        ganadora = supervivientes[0]
        return {
            "candidata_ganadora": ganadora.get("son", ""),
            "rgi_aplicada": "RGI 1",
            "rgi_secuencia": ["RGI 1: unica candidata superviviente, texto de partida compatible"],
            "justificacion": f"Unica candidata superviviente: {ganadora.get('son','')} con score {ganadora.get('score_coherencia',0)}",
            "confianza": "alta" if ganadora.get("score_coherencia", 0) >= 70 else "media",
            "escalamiento_humano": False,
            "alternativas_ordenadas": [],
            "_latencia_ms": round((time.time() - t0) * 1000, 1),
            "_agente": "JUEZ_RGI",
        }

    # Multiples candidatas: usar Gemini para aplicar RGI en secuencia
    candidatas_texto = "\n".join(
        f"- {s.get('son','')}: {s.get('descripcion','')[:80]} (score: {s.get('score_coherencia',0)}, especificidad: {s.get('especificidad','')})"
        for s in supervivientes[:8]
    )

    prompt = _PROMPT_JUEZ.format(
        producto=descripcion[:300],
        ficha=json.dumps({k: v for k, v in ficha.items() if not k.startswith("_")},
                         ensure_ascii=False, indent=2)[:2000],
        candidatas=candidatas_texto,
        notas=formatear_notas_gemini(notas)[:2000],
    )
    raw = _llamar_gemini(prompt, timeout=30)
    resultado = _parsear_json_gemini(raw) or {}

    for k in ["candidata_ganadora", "rgi_aplicada", "justificacion", "confianza"]:
        resultado.setdefault(k, "")
    resultado.setdefault("escalamiento_humano", False)
    resultado.setdefault("rgi_secuencia", [])
    resultado.setdefault("alternativas_ordenadas", [])

    # Validar que la ganadora exista en supervivientes
    ganadora_son = resultado.get("candidata_ganadora", "").strip()
    sons_validos = {s.get("son", "") for s in supervivientes}
    if ganadora_son not in sons_validos and supervivientes:
        resultado["candidata_ganadora"] = supervivientes[0].get("son", "")
        resultado["_warning"] = f"Ganadora '{ganadora_son}' no en supervivientes, usando top-score"

    resultado["_latencia_ms"] = round((time.time() - t0) * 1000, 1)
    resultado["_agente"] = "JUEZ_RGI"
    return resultado


# ══════════════════════════════════════════════════════════════════════════
# AGENTE 5 — DICTAMINADOR FINAL (Validación y Presentación)
# CEO 04-MAY-2026: Validar "tiene sentido?", calcular gravamen, dictamen.
# ══════════════════════════════════════════════════════════════════════════

def agente_5_dictaminador(ficha: dict, cazador: dict, fiscal: dict,
                          juez: dict, descripcion: str) -> dict:
    t0 = time.time()
    son_ganadora = juez.get("candidata_ganadora", "").strip()

    # Validacion CRITICA: el resultado tiene sentido?
    if not son_ganadora or not _SON_RE.match(son_ganadora):
        return {
            "son_final": "", "validado": False,
            "dictamen": "Sin candidata ganadora valida",
            "requiere_reintento": True,
            "_latencia_ms": round((time.time() - t0) * 1000, 1),
            "_agente": "DICTAMINADOR",
        }

    # Lookup en Capa 1
    exacto = consultar_son_exacto(son_ganadora)

    # Validacion de coherencia final (BUG-008 prevention)
    coherencia_ok = True
    if exacto:
        desc_son = (exacto.get("descripcion") or "").lower()
        desc_prod = descripcion.lower()
        # Check basico: al menos 1 palabra clave del producto en la descripcion SON
        palabras_prod = {w for w in desc_prod.split() if len(w) >= 4}
        palabras_son = {w for w in desc_son.split() if len(w) >= 4}
        overlap = palabras_prod & palabras_son
        # Si es parte, verificar que la partida corresponda al producto principal
        if ficha.get("es_parte"):
            partida_pp = ficha.get("partida_producto_principal", "")
            if partida_pp and son_ganadora[:4] == partida_pp[:4]:
                coherencia_ok = True
            elif overlap:
                coherencia_ok = True
            else:
                coherencia_ok = len(overlap) > 0 or juez.get("confianza") == "alta"
        else:
            if not overlap and juez.get("confianza") != "alta":
                coherencia_ok = False

    if not coherencia_ok:
        return {
            "son_final": son_ganadora, "validado": False,
            "dictamen": f"RECHAZADO por Dictaminador: la descripcion de {son_ganadora} no corresponde al producto '{descripcion[:80]}'. Requiere revision.",
            "requiere_reintento": True,
            "razon_rechazo": "Coherencia final fallida — sin overlap entre producto y SON",
            "_latencia_ms": round((time.time() - t0) * 1000, 1),
            "_agente": "DICTAMINADOR",
        }

    # Calcular gravamen
    gravamen_info = {}
    if exacto:
        gravamen_info = {
            "dai_pct": exacto.get("gravamen", ""),
            "itbis": exacto.get("itbis", "18"),
            "isc": exacto.get("isc", "NO APLICA"),
            "descripcion_oficial": exacto.get("descripcion", ""),
        }

    # Construir dictamen documentado (Paso 7 del protocolo)
    todas_candidatas = cazador.get("candidatas", [])
    descartadas = fiscal.get("candidatas_descartadas", [])

    dictamen = {
        "son_final": son_ganadora,
        "validado": bool(exacto),
        "gravamen": gravamen_info,
        "rgi_aplicada": juez.get("rgi_aplicada", ""),
        "justificacion_rgi": juez.get("justificacion", ""),
        "rgi_secuencia": juez.get("rgi_secuencia", []),
        "confianza": juez.get("confianza", ""),
        "candidatas_evaluadas": [c["son"] for c in todas_candidatas],
        "candidatas_descartadas": descartadas,
        "candidata_seleccionada_razon": juez.get("justificacion", ""),
        "es_parte": ficha.get("es_parte", False),
        "producto_principal": ficha.get("producto_principal", ""),
        "escalamiento_humano": juez.get("escalamiento_humano", False),
        "requiere_reintento": False,
        "nota_verificacion": "Validar con aforador acreditado DGA. Fuente: www.aduanas.gob.do",
        "_latencia_ms": round((time.time() - t0) * 1000, 1),
        "_agente": "DICTAMINADOR",
    }

    # Registrar conflicto si hubo multiples candidatas
    if cazador.get("conflicto_detectado"):
        try:
            registrar_conflicto(
                consulta=descripcion,
                candidatas=[c["son"] for c in todas_candidatas],
                ganadora=son_ganadora,
                rgi=juez.get("rgi_aplicada", ""),
                justificacion=juez.get("justificacion", "")[:500],
                resuelto_por="sistema",
            )
        except Exception as e:
            print(f"[DICTAMINADOR] Error registrando conflicto: {e}")

    return dictamen


# ══════════════════════════════════════════════════════════════════════════
# ORQUESTADOR PRINCIPAL — Pipeline 5 Agentes
# ══════════════════════════════════════════════════════════════════════════

def clasificar_producto(descripcion: str, publicar: bool = False) -> dict:
    """
    Pipeline 5 agentes CEO 04-MAY-2026.
    [GATE_IN] → [AG1: Guardian] → [AG2: Cazador] → [AG3: Fiscal]
             → [AG4: Juez RGI] → [AG5: Dictaminador] → [GATE_OUT]
    """
    t0 = time.time()
    resultado = {
        "descripcion": descripcion,
        "etapas": {},
        "son_final": "",
        "confianza": "",
        "validado": False,
        "protocolo": "CEO-04-MAY-2026-7PASOS",
    }

    # [GATE ENTRADA]
    gate_entrada = validar_entrada(descripcion)
    resultado["etapas"]["0_gate_entrada"] = gate_entrada
    if not gate_entrada["ok"]:
        resultado["error"] = gate_entrada["tipo"]
        resultado["mensaje_usuario"] = gate_entrada["mensaje"]
        resultado["latencia_total_ms"] = round((time.time() - t0) * 1000, 1)
        return resultado

    # [AGENTE 1: GUARDIAN DE ENTRADA]
    ficha = agente_1_guardian(descripcion)
    resultado["etapas"]["1_guardian"] = ficha

    # Identificar capitulos candidatos
    caps = []
    for c in ficha.get("capitulos_probables", []):
        c = str(c).strip().zfill(2)
        if c.isdigit() and 1 <= int(c) <= 97 and c not in caps:
            caps.append(c)
    resultado["etapas"]["1b_capitulos"] = caps
    cap_principal = caps[0] if caps else None

    # Notas legales del capitulo principal
    notas = {}
    if cap_principal:
        notas = leer_notas_capitulo(cap_principal)
    resultado["etapas"]["1c_notas"] = notas

    # RGI 1 exclusion check
    exclusion = validar_exclusion_capitulos(
        capitulo_propuesto=cap_principal or "",
        descripcion_producto=descripcion,
        criterio_0=ficha.get("criterio_0", ""),
        notas_context=notas,
    )
    resultado["etapas"]["1d_exclusion"] = exclusion
    if exclusion.get("excluido"):
        cap_principal = exclusion["capitulo_final"]
        if cap_principal not in caps:
            caps.insert(0, cap_principal)
        notas = leer_notas_capitulo(cap_principal)
        resultado["etapas"]["1c_notas_reclasificado"] = notas
        resultado["reclasificado_por_rgi1"] = True

    # Biblioteca RAG
    keywords = ficha.get("keywords", [])
    if not keywords:
        keywords = [ficha.get("que_es", ""), ficha.get("funcion", "")]
    snippets = investigar(keywords, capitulo=cap_principal, limit=5)
    resultado["etapas"]["1e_biblioteca"] = [
        {k: v for k, v in s.items() if k != "texto"} | {"texto_preview": s["texto"][:200]}
        for s in snippets
    ]

    # [AGENTE 2: CAZADOR DE CANDIDATAS]
    cazador = agente_2_cazador(ficha, descripcion)
    resultado["etapas"]["2_cazador"] = {
        "total_candidatas": cazador["total_candidatas"],
        "conflicto_detectado": cazador["conflicto_detectado"],
        "candidatas": cazador["candidatas"][:15],
        "_latencia_ms": cazador["_latencia_ms"],
    }

    if not cazador["candidatas"]:
        resultado["error"] = "SIN_CANDIDATAS"
        resultado["mensaje_usuario"] = "No se encontraron candidatas en el arancel. Reformule la consulta con mas detalle."
        resultado["latencia_total_ms"] = round((time.time() - t0) * 1000, 1)
        return resultado

    # [AGENTE 3: FISCAL MERCEOLOGICO]
    fiscal = agente_3_fiscal(ficha, cazador, notas, descripcion)
    resultado["etapas"]["3_fiscal"] = {
        "candidatas_supervivientes": fiscal["candidatas_supervivientes"],
        "candidatas_descartadas": fiscal["candidatas_descartadas"],
        "evaluaciones": fiscal["evaluaciones"][:10],
        "_latencia_ms": fiscal["_latencia_ms"],
    }

    if not fiscal["candidatas_supervivientes"]:
        resultado["error"] = "TODAS_DESCARTADAS"
        resultado["mensaje_usuario"] = "Todas las candidatas fueron descartadas por baja coherencia. Reformule con mas detalle tecnico."
        resultado["latencia_total_ms"] = round((time.time() - t0) * 1000, 1)
        return resultado

    # [AGENTE 4: JUEZ DE RGI]
    juez = agente_4_juez_rgi(ficha, fiscal, notas, descripcion)
    resultado["etapas"]["4_juez_rgi"] = juez

    # [AGENTE 5: DICTAMINADOR FINAL]
    dictamen = agente_5_dictaminador(ficha, cazador, fiscal, juez, descripcion)
    resultado["etapas"]["5_dictaminador"] = dictamen

    # Si el dictaminador rechaza, intentar con la segunda candidata
    if dictamen.get("requiere_reintento") and len(fiscal.get("evaluaciones", [])) > 1:
        segunda = fiscal["evaluaciones"][1]
        juez_retry = {
            "candidata_ganadora": segunda.get("son", ""),
            "rgi_aplicada": segunda.get("rgi_probable", "RGI 3a"),
            "justificacion": f"Reintento: primera candidata rechazada por Dictaminador. Segunda candidata: {segunda.get('son','')}",
            "confianza": "media",
            "escalamiento_humano": False,
        }
        dictamen_retry = agente_5_dictaminador(ficha, cazador, fiscal, juez_retry, descripcion)
        if not dictamen_retry.get("requiere_reintento"):
            dictamen = dictamen_retry
            resultado["etapas"]["5b_dictaminador_retry"] = dictamen_retry
            resultado["etapas"]["4b_juez_rgi_retry"] = juez_retry

    resultado["son_final"] = dictamen.get("son_final", "")
    resultado["confianza"] = dictamen.get("confianza", juez.get("confianza", ""))
    resultado["validado"] = dictamen.get("validado", False)
    resultado["conflicto_detectado"] = cazador.get("conflicto_detectado", False)
    resultado["candidatas_evaluadas"] = dictamen.get("candidatas_evaluadas", [])
    resultado["candidatas_descartadas"] = dictamen.get("candidatas_descartadas", [])
    resultado["rgi_aplicada"] = dictamen.get("rgi_aplicada", juez.get("rgi_aplicada", ""))
    resultado["justificacion_rgi"] = dictamen.get("justificacion_rgi", "")
    resultado["gravamen"] = dictamen.get("gravamen", {})
    resultado["es_parte"] = dictamen.get("es_parte", False)
    resultado["escalamiento_humano"] = dictamen.get("escalamiento_humano", False)

    # [GATE SALIDA]
    gate_salida = validar_salida(
        resultado["son_final"],
        rgi=resultado.get("rgi_aplicada", ""),
        fuente_db=dictamen.get("gravamen"),
    )
    resultado["etapas"]["6_gate_salida"] = gate_salida
    resultado["metadatos"] = {
        "fuente": gate_salida["fuente"],
        "rgi_aplicada": gate_salida["rgi_aplicada"],
        "base_legal": gate_salida["base_legal"],
        "nota_verificacion": gate_salida["nota_verificacion"],
    }
    if gate_salida["advertencias"]:
        resultado["advertencias"] = gate_salida["advertencias"]

    # Notion (opcional)
    if publicar:
        resultado["etapas"]["7_notion"] = _publicar_notion(descripcion, ficha, dictamen)

    resultado["latencia_total_ms"] = round((time.time() - t0) * 1000, 1)
    return resultado


# ── Publicador Notion ───────────────────────────────────────────────────

def _publicar_notion(descripcion: str, ficha: dict, dictamen: dict) -> dict:
    api_key = os.environ.get("NOTION_API_KEY", "")
    db_id = os.environ.get("NOTION_DB_MERCEOLOGIA", "")
    if not api_key or not db_id:
        return {"ok": False, "razon": "NOTION_API_KEY o NOTION_DB_MERCEOLOGIA no configurada"}
    try:
        from notion_client import Client
        notion = Client(auth=api_key)
        son_final = dictamen.get("son_final", "")
        grav = dictamen.get("gravamen", {})
        gravamen_txt = f"DAI {grav.get('dai_pct','?')}% | ITBIS {grav.get('itbis','?')}%"

        props = {
            "Producto":     {"title": [{"text": {"content": descripcion[:200]}}]},
            "SON Sugerido": {"rich_text": [{"text": {"content": son_final}}]},
            "Materia":      {"rich_text": [{"text": {"content": ficha.get("materia","")[:500]}}]},
            "Función":      {"rich_text": [{"text": {"content": ficha.get("funcion","")[:500]}}]},
            "Uso":          {"rich_text": [{"text": {"content": ficha.get("uso","")[:500]}}]},
            "Clasificación": {"rich_text": [{"text": {"content": dictamen.get("justificacion_rgi","")[:1800]}}]},
        }
        page = notion.pages.create(
            parent={"data_source_id": _resolver_ds_id(notion, db_id)},
            properties=props,
        )
        return {"ok": True, "page_id": page["id"], "url": page.get("url", "")}
    except Exception as e:
        return {"ok": False, "razon": str(e)}


def _resolver_ds_id(notion, db_id: str) -> str:
    try:
        db = notion.databases.retrieve(database_id=db_id)
        ds = db.get("data_sources", [])
        if ds:
            return ds[0]["id"]
    except Exception:
        pass
    return db_id


if __name__ == "__main__":
    desc = "Pantalla para celular Samsung Galaxy S24"
    r = clasificar_producto(desc, publicar=False)
    print(json.dumps(r, ensure_ascii=False, indent=2)[:5000])
