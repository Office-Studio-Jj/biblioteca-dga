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


def capa_3_gemini_orquestador(consulta: str, notebook_id: str) -> Dict[str, Any]:
    """
    CAPA 3 — Gemini como mesa de reparticion.
    Identifica el producto, normaliza la consulta, decide si requiere
    merceologia o respuesta directa.

    Returns:
        {"producto_identificado": str, "categoria": str, "requiere_merceologia": bool,
         "elapsed_ms": int, "fuente": "gemini"|"reglas", "ok": bool}
    """
    t0 = time.time()
    resultado = {
        "capa": 3,
        "nombre": "Gemini Orquestador",
        "ok": False,
        "fuente": "reglas",
        "producto_identificado": "",
        "categoria": "",
        "requiere_merceologia": False,
    }

    consulta_lower = (consulta or "").lower().strip()
    if not consulta_lower:
        resultado["error"] = "consulta vacia"
        resultado["elapsed_ms"] = int((time.time() - t0) * 1000)
        return resultado

    # Normalizar producto sin Gemini (rapido). Gemini se invoca solo si capa 2 no resuelve.
    palabras = re.findall(r'\b[a-záéíóúüñ]{4,}\b', consulta_lower)
    stopwords = {"para", "como", "cual", "este", "esta", "donde", "tiene", "necesito",
                 "consulta", "clasificar", "producto", "codigo", "arancel"}
    palabras_clave = [p for p in palabras if p not in stopwords]
    resultado["producto_identificado"] = " ".join(palabras_clave[:5])

    # Inferir categoria por capitulo aproximado (heuristica para enrutamiento)
    keywords_cap = {
        "88": ["dron", "drone", "aeronave", "uav", "vehiculo aereo", "fumigacion aerea"],
        "85": ["camara", "videocamara", "monitor", "tv", "televisor", "telefono", "movil",
               "computadora", "tablet"],
        "84": ["motor", "bomba", "compresor", "valvula", "rodamiento"],
        "87": ["vehiculo", "auto", "carro", "motocicleta", "neumatico"],
        "30": ["medicamento", "farmaco", "vitamina", "suplemento"],
        "22": ["bebida", "alcohol", "vino", "cerveza", "ron"],
        "27": ["combustible", "gasolina", "diesel", "petroleo"],
        "73": ["acero", "hierro", "metalica"],
        "39": ["plastico", "polietileno", "pvc", "polimero"],
    }
    for cap, keys in keywords_cap.items():
        if any(k in consulta_lower for k in keys):
            resultado["categoria"] = f"Capitulo {cap}"
            break

    # Si la consulta es de nomenclaturas y describe un producto fisico -> requiere merceologia
    es_clasificacion = notebook_id == "biblioteca-de-nomenclaturas" and len(palabras_clave) >= 1
    resultado["requiere_merceologia"] = es_clasificacion

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
        "(RGI 1, 3a, 6).\n\n"
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


def capa_2_notion_merceologia(consulta: str, notebook_id: str, umbral: float = 0.4,
                              capitulo_pista: str = "") -> Dict[str, Any]:
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
        return resultado
    else:
        resultado["error_gemini"] = g.get("error", "sin codigo extraido")

    resultado["elapsed_ms"] = int((time.time() - t0) * 1000)
    return resultado


def capa_1_claude_validador(consulta: str, codigo_propuesto: str) -> Dict[str, Any]:
    """
    CAPA 1 — Claude API + cache local SQLite/JSON.
    Verifica:
      - Codigo arancelario existe en el cache 7,616 codigos del Arancel RD
      - Gravamen (DAI) correcto desde gravamenes_lookup.json
      - ITBIS aplica/no aplica
      - ISC aplica/no aplica desde isc_lookup.json
      - Base legal (Ley 168-21, Decreto 36-22, Ley 150-97 si aplica)
      - Confirma con claude-haiku via claude_validator.py si esta disponible

    Returns:
        {"codigo_existe": bool, "gravamen": str, "itbis": str, "isc": str,
         "base_legal": list, "claude_confirmacion": dict, "ok": bool, "elapsed_ms": int}
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

    # 4. Base legal (siempre incluir leyes principales RD)
    resultado["base_legal"] = [
        "Ley 168-21 - Ley General de Aduanas RD",
        "Decreto 36-22 - Arancel Nacional vigente",
        "Ley 253-12 - ITBIS e ISC (Arts. 335-381)",
        "Decreto 755-22 - Reglamento Ley 168-21",
    ]
    # Detectar si aplica Ley 150-97 (uso agropecuario)
    if "agricultura" in consulta.lower() or "agropecuari" in consulta.lower():
        resultado["base_legal"].append("Ley 150-97 - Tarifa cero sector agropecuario")
        resultado["beneficio_150_97"] = "0% DAI + Exencion ITBIS si demuestra uso agricola exclusivo"

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

    # CAPA 3: Gemini orquestador
    c3 = capa_3_gemini_orquestador(consulta, notebook_id)
    trazabilidad["capas"].append(c3)

    if not c3.get("ok"):
        trazabilidad["respuesta_final"] = "Error en Capa 3 (orquestador). Sin clasificacion."
        trazabilidad["patron_intacto"] = False
        trazabilidad["tiempo_total_ms"] = int((time.time() - t0) * 1000)
        return trazabilidad

    # CAPA 2: Notion/Merceologia (pasa pista de capitulo de Capa 3)
    capitulo_pista = c3.get("categoria", "")
    c2 = capa_2_notion_merceologia(consulta, notebook_id, capitulo_pista=capitulo_pista)
    trazabilidad["capas"].append(c2)

    codigo_propuesto = c2.get("codigo")

    # CAPA 1: Claude/SQLite verificador
    c1 = capa_1_claude_validador(consulta, codigo_propuesto)
    trazabilidad["capas"].append(c1)

    # Reintento: si Capa 1 marca codigo_generico, pedir a Gemini que afine
    if c1.get("codigo_generico") and c2.get("fuente") == "gemini_rest":
        alternativas = c1.get("alternativas_mas_especificas", [])
        if alternativas:
            consulta_refinada = (
                f"{consulta}. ATENCION: PROHIBIDO clasificar como {codigo_propuesto} (es generico 'los demas'). "
                f"Elige una de estas subpartidas mas especificas segun caracteristicas del producto: "
                f"{', '.join(alternativas[:5])}"
            )
            print(f"[PIPELINE] Reintentando Capa 2 — codigo {codigo_propuesto} es generico")
            c2_retry = capa_2_notion_merceologia(consulta_refinada, notebook_id,
                                                  capitulo_pista=capitulo_pista)
            trazabilidad["capas"].append({**c2_retry, "capa": 2, "nombre": "Capa 2 reintento"})
            codigo_retry = c2_retry.get("codigo")
            if codigo_retry and codigo_retry != codigo_propuesto:
                c1_retry = capa_1_claude_validador(consulta, codigo_retry)
                trazabilidad["capas"].append({**c1_retry, "capa": 1, "nombre": "Capa 1 reintento"})
                if c1_retry.get("ok"):
                    c1, c2 = c1_retry, c2_retry
                    codigo_propuesto = codigo_retry

    # Construir respuesta final
    if c2.get("ok") and c1.get("ok"):
        trazabilidad["codigo_final"] = c1["codigo_propuesto"]
        trazabilidad["respuesta_final"] = c2.get("respuesta", "")
        trazabilidad["gravamen_final"] = c1.get("gravamen", "verificar")
        trazabilidad["isc_final"] = c1.get("isc", "NO APLICA")
        trazabilidad["base_legal"] = c1.get("base_legal", [])
        trazabilidad["beneficio_150_97"] = c1.get("beneficio_150_97")
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
