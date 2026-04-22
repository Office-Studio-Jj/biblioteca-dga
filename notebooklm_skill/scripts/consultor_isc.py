"""
consultor_isc.py — Sub-agente ISC para Biblioteca DGA
======================================================
Dado un codigo arancelario RD, determina si lleva ISC y otros impuestos
siguiendo el flujo de 3 capas:

  CAPA 1: isc_lookup.json  (cache local, respuesta instantanea)
  CAPA 2: Gemini + cuaderno biblioteca-legal-y-procedimiento-dga
  CAPA 3: Fetch DGII dgii.gov.do  (fuente oficial, web scraping)

El resultado se guarda en cache (Capa 1) para futuras consultas.
"""

import os
import json
import re
import time
import urllib.request
import urllib.error

_BASE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.join(_BASE, "..", "data", "fuentes_nomenclatura")
_ISC_LOOKUP = os.path.join(_DATA, "isc_lookup.json")

# ── Capa 1: cache local ────────────────────────────────────────────────────

def _cargar_cache() -> dict:
    try:
        with open(_ISC_LOOKUP, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"_meta": {}, "capitulos_con_isc": {}, "cache_consultas": {}}


def _guardar_cache(data: dict) -> None:
    try:
        with open(_ISC_LOOKUP, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ISC] Error guardando cache: {e}")


def _buscar_en_cache(codigo: str, cache: dict) -> dict | None:
    # 1. Lookup directo por codigo especifico
    cap = codigo[:2]
    cap_data = cache.get("capitulos_con_isc", {}).get(cap)
    if cap_data:
        verificados = cap_data.get("codigos_verificados", {})
        if codigo in verificados:
            entry = verificados[codigo]
            return {
                "isc": entry.get("isc", "NO APLICA"),
                "base_legal": f"Ley 11-92 Art. 375, bienes suntuarios ({cap_data.get('descripcion','')})",
                "fuente": "isc_lookup.json (cache verificado)",
                "certeza": "ALTA",
                "otros_cargos": "NINGUNO",
                "capitulo": cap,
                "descripcion_codigo": entry.get("descripcion", "")
            }
        # Verificar si la partida base esta en las afectadas del capitulo
        partidas_afectadas = cap_data.get("partidas_afectadas", [])
        if any(codigo.startswith(p) for p in partidas_afectadas):
            tasa = cap_data.get("tasas", {}).get("default", "NO APLICA")
            if tasa != "NO APLICA":
                return {
                    "isc": tasa,
                    "base_legal": f"Ley 11-92 Art. 375, {cap_data.get('descripcion','')}",
                    "fuente": "isc_lookup.json (partida afectada, cap. verificado)",
                    "certeza": "MEDIA",
                    "otros_cargos": "NINGUNO",
                    "capitulo": cap
                }

    # 2. Cache de consultas previas
    cache_consultas = cache.get("cache_consultas", {})
    if codigo in cache_consultas:
        entrada = cache_consultas[codigo]
        entrada["fuente"] += " (cache consulta previa)"
        return entrada

    return None


# ── Capa 2: Gemini + cuaderno legal ────────────────────────────────────────

def _consultar_gemini_isc(codigo: str, descripcion: str = "") -> dict | None:
    """Pregunta al cuaderno biblioteca-legal-y-procedimiento-dga sobre ISC."""
    try:
        import subprocess, sys
        script = os.path.join(_BASE, "ask_gemini.py")
        if not os.path.exists(script):
            return None

        desc_txt = f" ({descripcion})" if descripcion else ""
        pregunta = (
            f"CONSULTA ISC: Para el codigo arancelario {codigo}{desc_txt} de la Republica Dominicana, "
            f"responde EXCLUSIVAMENTE: "
            f"1) ¿Aplica ISC (Impuesto Selectivo al Consumo)? Si/No y tasa. "
            f"2) Base legal (articulo y ley). "
            f"3) ¿Hay otros impuestos adicionales? "
            f"Responde en formato JSON: "
            f"{{\"isc\": \"X% o NO APLICA\", \"base_legal\": \"...\", \"otros_cargos\": \"...\", \"certeza\": \"ALTA/MEDIA/BAJA\"}}"
        )

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONPATH"] = os.path.dirname(_BASE)

        result = subprocess.run(
            [sys.executable, script,
             "--question", pregunta,
             "--notebook-id", "biblioteca-legal-y-procedimiento-dga"],
            cwd=_BASE, capture_output=True, text=True,
            encoding="utf-8", env=env, timeout=60
        )
        output = result.stdout.strip()
        if not output:
            return None

        # Intentar parsear JSON de la respuesta
        m = re.search(r'\{[^{}]*"isc"[^{}]*\}', output, re.DOTALL)
        if m:
            datos = json.loads(m.group(0))
            return {
                "isc": datos.get("isc", "NO APLICA"),
                "base_legal": datos.get("base_legal", "Consulta cuaderno legal"),
                "otros_cargos": datos.get("otros_cargos", "NINGUNO"),
                "certeza": datos.get("certeza", "MEDIA"),
                "fuente": "Gemini — biblioteca-legal-y-procedimiento-dga"
            }

        # Si no hay JSON estructurado, buscar keywords en texto libre
        isc_val = "NO APLICA"
        base = "Ley 11-92"
        m_tasa = re.search(r'(\d+)\s*%\s*(?:ISC|selectivo|ad.valorem)', output, re.IGNORECASE)
        if m_tasa:
            isc_val = f"{m_tasa.group(1)}%"
        m_art = re.search(r'(Art(?:iculo)?\.?\s*\d+[^\n.]{0,60})', output, re.IGNORECASE)
        if m_art:
            base = m_art.group(1).strip()

        return {
            "isc": isc_val,
            "base_legal": base,
            "otros_cargos": "NINGUNO",
            "certeza": "MEDIA",
            "fuente": "Gemini — biblioteca-legal-y-procedimiento-dga (texto libre)"
        }
    except Exception as e:
        print(f"[ISC] Error consultando Gemini: {e}")
        return None


# ── Capa 3: Fetch DGII ─────────────────────────────────────────────────────

_DGII_ISC_URLS = [
    "https://dgii.gov.do/cicloContribuyente/obligacionesTributarias/principalesImpuestos/Paginas/impuestoSelectivoConsumo.aspx",
    "https://dgii.gov.do/publicacionesOficiales/bibliotecaVirtual/contribuyentes/isc/Documents/BROCHURE%20IMPUESTO%20SELECTIVO%20AL%20CONSUMO%20(ISC).pdf",
]

# Tabla codificada de ISC conocidos — actualizar cuando DGII publique cambios
_DGII_ISC_TABLA = {
    # Capitulo 85 — bienes suntuarios electronicos (Ley 11-92 Art. 375)
    "85": {"isc": "10%", "base_legal": "Ley 11-92 Art. 375 — bienes suntuarios electronicos importados",
           "partidas": ["8521", "8525", "8527", "8528"]},
    # Capitulo 22 — bebidas alcoholicas
    "22": {"isc": "Mixto RD$/litro + Ad Valorem", "base_legal": "Ley 11-92 Art. 367-370",
           "partidas": []},
    # Capitulo 24 — tabaco
    "24": {"isc": "Mixto RD$/unidad + 20%", "base_legal": "Ley 11-92 Art. 371-374",
           "partidas": []},
    # Capitulo 27 — hidrocarburos
    "27": {"isc": "RD$/galon (monto especifico)", "base_legal": "Ley 112-00",
           "partidas": []},
    # Capitulo 87 — vehiculos
    "87": {"isc": "Escala progresiva CO2/cilindrada", "base_legal": "Ley 253-12",
           "partidas": []},
}


def _consultar_dgii(codigo: str) -> dict | None:
    """Consulta la tabla DGII codificada y, si no coincide, intenta fetch web."""
    cap = codigo[:2]

    # 1. Tabla codificada (datos verificados de DGII)
    if cap in _DGII_ISC_TABLA:
        entrada = _DGII_ISC_TABLA[cap]
        partidas_cap = entrada.get("partidas", [])
        aplica = not partidas_cap or any(codigo.startswith(p) for p in partidas_cap)
        if aplica:
            return {
                "isc": entrada["isc"],
                "base_legal": entrada["base_legal"],
                "otros_cargos": "NINGUNO",
                "certeza": "ALTA",
                "fuente": "Tabla DGII codificada — dgii.gov.do (verificado 2026-04)"
            }
        else:
            return {
                "isc": "NO APLICA",
                "base_legal": f"Capitulo {cap} tiene ISC pero partida {codigo} no esta afectada",
                "otros_cargos": "NINGUNO",
                "certeza": "MEDIA",
                "fuente": "Tabla DGII codificada"
            }

    # 2. Fetch web DGII como fallback (solo si no esta en tabla)
    try:
        req = urllib.request.Request(
            _DGII_ISC_URLS[0],
            headers={"User-Agent": "Mozilla/5.0 (compatible; BibliotecaDGA/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # Buscar menciones del capitulo o codigo en el HTML
        cap_pattern = rf'(?:cap[ií]tulo|partida).*?{cap}\b[^\n]{{0,200}}'
        m = re.search(cap_pattern, html, re.IGNORECASE | re.DOTALL)
        if m:
            texto = re.sub(r'<[^>]+>', ' ', m.group(0))
            m_tasa = re.search(r'(\d+)\s*%', texto)
            tasa = f"{m_tasa.group(1)}%" if m_tasa else "VERIFICAR EN DGII"
            return {
                "isc": tasa,
                "base_legal": "dgii.gov.do — impuesto selectivo al consumo",
                "otros_cargos": "NINGUNO",
                "certeza": "MEDIA",
                "fuente": "Fetch DGII (web scraping)"
            }
    except Exception as e:
        print(f"[ISC] Fetch DGII fallido: {e}")

    return {
        "isc": "NO APLICA",
        "base_legal": "No encontrado en tabla DGII — verificar manualmente",
        "otros_cargos": "NINGUNO",
        "certeza": "BAJA",
        "fuente": "Ninguna fuente disponible"
    }


# ── Orquestador principal ──────────────────────────────────────────────────

def consultar_isc(codigo: str, descripcion: str = "", usar_gemini: bool = True) -> dict:
    """
    Consulta ISC para un codigo arancelario RD.

    Args:
        codigo: Formato XXXX.XX.XX
        descripcion: Descripcion del producto (mejora precision)
        usar_gemini: Si True, usa cuaderno legal como Capa 2

    Returns:
        dict con: isc, base_legal, fuente, certeza, otros_cargos, codigo
    """
    if not re.match(r'^\d{4}\.\d{2}\.\d{2}$', codigo):
        return {"error": f"Formato invalido: {codigo}", "isc": "NO APLICA", "certeza": "BAJA"}

    print(f"[ISC-AGENTE] Consultando {codigo} ({descripcion[:40] if descripcion else ''})")
    cache = _cargar_cache()

    # CAPA 1 — cache local (0ms)
    resultado = _buscar_en_cache(codigo, cache)
    if resultado:
        print(f"[ISC-AGENTE] Capa 1 (cache): {resultado['isc']}")
        resultado["codigo"] = codigo
        resultado["descripcion"] = descripcion
        return resultado

    # CAPA 2 — Gemini cuaderno legal (~30-60s)
    if usar_gemini:
        print(f"[ISC-AGENTE] Capa 2 (Gemini legal): consultando...")
        resultado = _consultar_gemini_isc(codigo, descripcion)
        if resultado and resultado.get("certeza") in ("ALTA", "MEDIA"):
            print(f"[ISC-AGENTE] Capa 2: {resultado['isc']} ({resultado['certeza']})")
            _guardar_en_cache(codigo, resultado, cache)
            resultado["codigo"] = codigo
            resultado["descripcion"] = descripcion
            return resultado

    # CAPA 3 — DGII tabla codificada / fetch web (~2-8s)
    print(f"[ISC-AGENTE] Capa 3 (DGII): consultando tabla codificada...")
    resultado = _consultar_dgii(codigo)
    if resultado:
        _guardar_en_cache(codigo, resultado, cache)
        resultado["codigo"] = codigo
        resultado["descripcion"] = descripcion
        return resultado

    return {
        "codigo": codigo,
        "descripcion": descripcion,
        "isc": "NO APLICA",
        "base_legal": "No determinado",
        "fuente": "Sin fuente disponible",
        "certeza": "BAJA",
        "otros_cargos": "NINGUNO"
    }


def _guardar_en_cache(codigo: str, resultado: dict, cache: dict) -> None:
    """Guarda resultado en cache_consultas para uso futuro."""
    if "cache_consultas" not in cache:
        cache["cache_consultas"] = {}
    entrada = {k: v for k, v in resultado.items() if k not in ("codigo", "descripcion")}
    entrada["fecha"] = time.strftime("%Y-%m-%d")
    cache["cache_consultas"][codigo] = entrada
    _guardar_cache(cache)
    print(f"[ISC-AGENTE] Guardado en cache: {codigo} → {resultado.get('isc')}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Consultor ISC para partidas arancelarias RD")
    parser.add_argument("--codigo", required=True, help="Codigo arancelario XXXX.XX.XX")
    parser.add_argument("--descripcion", default="", help="Descripcion del producto")
    parser.add_argument("--no-gemini", action="store_true", help="Omitir consulta Gemini")
    args = parser.parse_args()

    resultado = consultar_isc(args.codigo, args.descripcion, usar_gemini=not args.no_gemini)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
