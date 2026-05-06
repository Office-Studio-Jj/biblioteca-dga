"""
Sub-agente [3] — LECTOR DE NOTAS DEL CAPÍTULO (Arancel 7ma RD)
Retorna las Notas Legales de un capítulo + doctrina aplicable local.

Fuentes en orden de prioridad:
  1. notas_capitulos_cache.json (Cap 22, 24, 27, 85, 87 ya cacheados)
  2. Arancel 7ma pdfplumber on-demand (para capitulos no cacheados)
  3. Estructura basica del SA (fallback)

API:
    leer_notas_capitulo(capitulo: str) -> dict
"""
import json
import os
import re
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_CACHE_NOTAS = os.path.join(
    _ROOT, "notebooklm_skill", "data", "fuentes_nomenclatura",
    "notas_capitulos_cache.json"
)
_NOTAS_COMPLETAS = os.path.join(
    _ROOT, "notebooklm_skill", "data", "fuentes_nomenclatura",
    "notas_legales_completas.json"
)
_ARANCEL_PDF = os.path.join(
    _ROOT, "notebooklm_skill", "data", "fuentes_nomenclatura",
    "Arancel 7ma enmienda de la republica dominicana.pdf"
)

# Secciones del Sistema Armonizado (indicativo, NO vinculante — RGI 1)
_SECCIONES = {
    "I":     ("01-05", "Animales vivos y productos del reino animal"),
    "II":    ("06-14", "Productos del reino vegetal"),
    "III":   ("15",    "Grasas y aceites animales, vegetales o microbianos"),
    "IV":    ("16-24", "Productos de las industrias alimentarias; bebidas, tabaco"),
    "V":     ("25-27", "Productos minerales"),
    "VI":    ("28-38", "Productos de las industrias químicas"),
    "VII":   ("39-40", "Plástico y caucho y sus manufacturas"),
    "VIII":  ("41-43", "Pieles, cueros, peletería y manufacturas"),
    "IX":    ("44-46", "Madera, carbón vegetal, corcho, manufacturas de espartería"),
    "X":     ("47-49", "Pasta de madera, papel, cartón, productos editoriales"),
    "XI":    ("50-63", "Materias textiles y sus manufacturas"),
    "XII":   ("64-67", "Calzado, sombreros, paraguas, plumas, flores artificiales"),
    "XIII":  ("68-70", "Manufacturas de piedra, yeso, cerámica, vidrio"),
    "XIV":   ("71",    "Perlas, piedras preciosas, metales preciosos, bisutería"),
    "XV":    ("72-83", "Metales comunes y sus manufacturas"),
    "XVI":   ("84-85", "Máquinas, aparatos, material eléctrico"),
    "XVII":  ("86-89", "Material de transporte"),
    "XVIII": ("90-92", "Instrumentos y aparatos de óptica, relojería, música"),
    "XIX":   ("93",    "Armas, municiones y sus partes"),
    "XX":    ("94-96", "Mercancías y productos diversos"),
    "XXI":   ("97",    "Objetos de arte y antigüedades"),
}


def _seccion_de_capitulo(cap: str) -> tuple[str, str]:
    cap_num = int(cap)
    for sec, (rango, nombre) in _SECCIONES.items():
        if "-" in rango:
            ini, fin = rango.split("-")
            if int(ini) <= cap_num <= int(fin):
                return sec, nombre
        else:
            if cap_num == int(rango):
                return sec, nombre
    return "?", "(desconocida)"


def _leer_cache_notas() -> dict:
    try:
        with open(_CACHE_NOTAS, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _leer_notas_completas() -> dict:
    """Lee el archivo de notas legales completas (todos los capitulos/secciones)."""
    try:
        with open(_NOTAS_COMPLETAS, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _extraer_notas_pdf(capitulo: str) -> Optional[dict]:
    """Extrae Notas Legales de un capitulo desde el Arancel 7ma (on-demand)."""
    if not os.path.exists(_ARANCEL_PDF):
        return None
    try:
        import pdfplumber
        cap_num = int(capitulo)
        # Buscar paginas con "Capitulo XX" al inicio
        notas_texto = []
        con_pdf = pdfplumber.open(_ARANCEL_PDF)
        try:
            # Heuristica: las notas estan en las primeras 1-3 paginas del capitulo
            for i, page in enumerate(con_pdf.pages):
                txt = page.extract_text() or ""
                # Match: "Capitulo 85" o "CAPITULO 85" al inicio de pagina
                if re.search(
                    rf'(?:^|\n)\s*(?:CAP(?:I|Í)TULO|Cap(?:í|i)tulo)\s+{cap_num}\b',
                    txt[:500]
                ):
                    # Este es el inicio del capitulo. Tomar esta pagina + siguientes
                    # hasta encontrar el primer codigo XXXX.XX.XX
                    bloque = []
                    for j in range(i, min(i + 4, len(con_pdf.pages))):
                        t = con_pdf.pages[j].extract_text() or ""
                        bloque.append(t)
                        # Detectar fin de notas: aparece un codigo SON concreto
                        if re.search(r'\d{4}\.\d{2}\.\d{2}', t):
                            break
                    notas_texto = "\n".join(bloque)
                    # Extraer solo hasta el primer SON
                    m = re.search(r'\d{4}\.\d{2}\.\d{2}', notas_texto)
                    if m:
                        notas_texto = notas_texto[:m.start()]
                    break
        finally:
            con_pdf.close()

        if not notas_texto:
            return None

        return {
            "texto_completo": notas_texto.strip()[:5000],  # max 5K chars
            "fuente":         "Arancel 7ma pdfplumber on-demand",
            "capitulo":       capitulo,
        }
    except Exception as e:
        print(f"[LECTOR-NOTAS] Error extrayendo cap {capitulo}: {e}")
        return None


def _leer_notas_seccion(seccion: str, cache: dict) -> dict:
    """
    Retorna las notas de la Seccion SA desde el cache.
    Conforme RGI 1: las notas de Seccion tienen igual jerarquia legal que las de Capitulo.
    """
    secs_cached = cache.get("secciones", {})
    if seccion not in secs_cached:
        return {}
    info = secs_cached[seccion]
    return {
        "seccion":        seccion,
        "titulo":         info.get("titulo", ""),
        "capitulos":      info.get("capitulos", ""),
        "notas_legales":  info.get("notas_legales", []),
        "exclusiones":    info.get("exclusiones", []),
    }


def leer_notas_capitulo(capitulo: str) -> dict:
    """
    Retorna notas del Capitulo Y de su Seccion padre en formato uniforme.

    Conforme RGI 1 (Decreto 755-22 Art. 63): la clasificacion esta determinada
    por el texto de las partidas Y las Notas de Seccion o de Capitulo — ambas.

    Estructura retornada:
    {
        "capitulo":           "87",
        "seccion":            "XVII",
        "seccion_titulo":     "Material de transporte",
        "titulo_cap":         "Vehiculos automoviles, tractores...",
        "notas_legales":      [...],    # Notas del Capitulo
        "alcance":            "...",    # Que NO comprende el capitulo
        "isc_aplicable":      "...",    # ISC si aplica
        "notas_seccion":      {         # NUEVO: Notas de la Seccion padre
            "seccion":        "XVII",
            "titulo":         "...",
            "notas_legales":  [...],
            "exclusiones":    [...],
        },
        "fuente":             "cache" | "pdf" | "fallback"
    }
    """
    cap = str(capitulo).zfill(2)
    sec, sec_nombre = _seccion_de_capitulo(cap)

    result = {
        "capitulo":       cap,
        "seccion":        sec,
        "seccion_titulo": sec_nombre,
        "titulo_cap":     "",
        "notas_legales":  [],
        "alcance":        "",
        "isc_aplicable":  "",
        "notas_seccion":  {},
        "fuente":         "fallback",
    }

    cache = _leer_cache_notas()

    # 1. Notas de Seccion (RGI 1 — misma jerarquia que notas de capitulo)
    result["notas_seccion"] = _leer_notas_seccion(sec, cache)

    # 2. Cache JSON principal (si existe para el capitulo)
    caps_cached = cache.get("capitulos", {})
    if cap in caps_cached:
        info = caps_cached[cap]
        result["titulo_cap"]    = info.get("titulo", "")
        result["notas_legales"] = info.get("notas_legales", [])
        result["alcance"]       = info.get("no_comprende",
                                           info.get("alcance", ""))
        result["isc_aplicable"] = info.get("isc_rd", info.get("isc", ""))
        result["fuente"]        = "cache"
        return result

    # 2b. Notas legales completas (archivo con TODOS los capitulos)
    completas = _leer_notas_completas()
    caps_completas = completas.get("capitulos", {})
    if cap in caps_completas:
        info = caps_completas[cap]
        result["titulo_cap"]    = info.get("titulo", "")
        result["notas_legales"] = info.get("notas_legales", [])
        result["alcance"]       = info.get("no_comprende",
                                           info.get("alcance", ""))
        result["fuente"]        = "notas_legales_completas"
        return result

    # 2c. Notas de seccion del archivo completo (si no estaban en cache principal)
    secs_completas = completas.get("secciones", {})
    if sec in secs_completas and not result["notas_seccion"]:
        result["notas_seccion"] = {
            "seccion":       sec,
            "titulo":        secs_completas[sec].get("titulo", ""),
            "capitulos":     secs_completas[sec].get("capitulos", ""),
            "notas_legales": secs_completas[sec].get("notas_legales", []),
            "exclusiones":   secs_completas[sec].get("exclusiones", []),
        }

    # 3. PDF on-demand
    pdf_notas = _extraer_notas_pdf(cap)
    if pdf_notas:
        texto = pdf_notas["texto_completo"]
        result["titulo_cap"]    = texto[:200].split("\n")[0]
        result["notas_legales"] = [texto]
        result["fuente"]        = "pdf"
        return result

    # 4. Fallback — seccion disponible, capitulo sin notas
    result["titulo_cap"] = f"Capitulo {cap} - sin notas cacheadas"
    return result


def formatear_notas_gemini(notas: dict) -> str:
    """
    Formatea Notas de Seccion + Notas de Capitulo para inyectar en prompt Gemini.
    Conforme RGI 1: primero Seccion, luego Capitulo.
    """
    partes = []

    # Notas de Seccion (RGI 1 — primer nivel jerarquico)
    ns = notas.get("notas_seccion", {})
    if ns and ns.get("notas_legales"):
        partes.append(
            f"SECCION {ns['seccion']}: {ns.get('titulo', '')} (Cap. {ns.get('capitulos', '')})"
        )
        partes.append("NOTAS DE SECCION:")
        for i, n in enumerate(ns["notas_legales"], 1):
            partes.append(f"  {i}. {str(n)[:400]}")
        for excl in (ns.get("exclusiones") or []):
            partes.append(f"  EXCLUYE: {str(excl)[:300]}")

    # Notas de Capitulo
    partes.append(
        f"\nCAPITULO {notas['capitulo']} - Seccion {notas['seccion']}: {notas['seccion_titulo']}"
    )
    if notas.get("titulo_cap"):
        partes.append(f"Titulo: {notas['titulo_cap']}")
    if notas.get("notas_legales"):
        partes.append("NOTAS DE CAPITULO:")
        for i, n in enumerate(notas["notas_legales"], 1):
            if isinstance(n, dict):
                n = n.get("texto", str(n))
            partes.append(f"  {i}. {str(n)[:600]}")
    if notas.get("alcance"):
        partes.append(f"ALCANCE/EXCLUSIONES:\n  {str(notas['alcance'])[:500]}")
    if notas.get("isc_aplicable"):
        partes.append(f"ISC APLICABLE EN RD:\n  {str(notas['isc_aplicable'])[:400]}")

    partes.append(f"[Fuente: {notas.get('fuente', 'fallback')}]")
    return "\n".join(partes)


if __name__ == "__main__":
    for cap in ["85", "22", "77", "84"]:
        print(f"\n===== Capitulo {cap} =====")
        n = leer_notas_capitulo(cap)
        print(formatear_notas_gemini(n)[:500])
