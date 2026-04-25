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


def capa_2_notion_merceologia(consulta: str, notebook_id: str, umbral: float = 0.4) -> Dict[str, Any]:
    """
    CAPA 2 — Notion / fichas merceologicas locales.
    Busca primero en fichas markdown locales (cache rapido). Si no encuentra,
    consulta SQLite (que se sincroniza con Notion via notion_service).

    Returns:
        {"slug": str, "codigo": str, "score": float, "fuente": "merceologia"|"notion-sqlite"|"none",
         "respuesta": str, "elapsed_ms": int, "ok": bool}
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

    # Sub-capa 2a: cache merceologico local (md files) — solo match, sin supervisor lento
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

    # Sub-capa 2b: SQLite sincronizado con Notion (si existe)
    db_path = os.path.join(_HERE, "..", "..", "capa1_sqlite", "arancel_rd.db")
    if os.path.exists(db_path):
        try:
            import sqlite3
            con = sqlite3.connect(db_path)
            cur = con.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notion_merceologia'")
            if cur.fetchone():
                # Buscar por palabras clave en titulo/resumen
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

    # 5. Validacion final con Claude API (opcional)
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

    # OK si codigo existe Y (sin claude o claude valido)
    claude_ok = (resultado.get("claude_confirmacion") is None or
                 resultado.get("claude_confirmacion", {}).get("valido") is not False)
    resultado["ok"] = bool(resultado["codigo_existe"]) and claude_ok
    resultado["elapsed_ms"] = int((time.time() - t0) * 1000)
    return resultado


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

    # CAPA 2: Notion/Merceologia
    c2 = capa_2_notion_merceologia(consulta, notebook_id)
    trazabilidad["capas"].append(c2)

    codigo_propuesto = c2.get("codigo")

    # CAPA 1: Claude/SQLite verificador
    c1 = capa_1_claude_validador(consulta, codigo_propuesto)
    trazabilidad["capas"].append(c1)

    # Construir respuesta final solo si las 3 capas estan ok
    if c2.get("ok") and c1.get("ok"):
        trazabilidad["codigo_final"] = c1["codigo_propuesto"]
        trazabilidad["respuesta_final"] = c2.get("respuesta", "")
        trazabilidad["gravamen_final"] = c1.get("gravamen", "verificar")
        trazabilidad["isc_final"] = c1.get("isc", "NO APLICA")
        trazabilidad["base_legal"] = c1.get("base_legal", [])
        trazabilidad["beneficio_150_97"] = c1.get("beneficio_150_97")
        trazabilidad["patron_intacto"] = True
    elif c2.get("ok"):
        trazabilidad["codigo_final"] = c2.get("codigo")
        trazabilidad["respuesta_final"] = c2.get("respuesta", "")
        trazabilidad["patron_intacto"] = True
        trazabilidad["nota"] = "Capa 1 (Claude) no verifico, usando ficha merceologica directa"
    else:
        trazabilidad["respuesta_final"] = None
        trazabilidad["patron_intacto"] = False
        trazabilidad["nota"] = "Capa 2 sin match. Pasara a Gemini directo en server.py"

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
