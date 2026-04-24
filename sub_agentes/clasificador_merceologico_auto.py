"""
Sub-agente [MAESTRO] — CLASIFICADOR MERCEOLOGICO AUTO (7 etapas)

Pipeline:
  [1] FICHA MERCEOLOGICA (Gemini)       → 7 preguntas obligatorias
  [2] IDENTIFICADOR DE CAPITULO         → top-3 candidatos (FTS + keywords)
  [3] LECTOR NOTAS CAPITULO             → notas_capitulos_cache + PDF fallback
  [3.5] INVESTIGADOR BIBLIOTECA         → RAG sobre 11 PDFs (FTS5)
  [4] REFINADOR SON (Gemini)            → ficha + notas + biblioteca → SON
  [5] VALIDADOR CAPA 1 (SQLite)         → consultar_son_exacto + alternativas
  [6] PUBLICADOR NOTION                 → escribe en DB "Fichas Merceologicas"

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
)

_SON_RE = re.compile(r'\b(\d{4}\.\d{2}\.\d{2}(?:\.\d{2})?)\b')


# ── Etapa 1: Ficha merceologica (Gemini) ─────────────────────────────────

_PROMPT_FICHA = """Eres un analista aduanero RD. Devuelve SOLO JSON valido con esta estructura exacta:

{{
  "que_es":          "<descripcion breve, 1 frase>",
  "materia":         "<material principal de fabricacion>",
  "funcion":         "<funcion tecnica principal>",
  "uso":             "<uso tipico/aplicacion>",
  "usuarios":        "<quienes lo utilizan>",
  "clasificacion":   "<uso | naturaleza | funcion>",
  "son_sugerido":    "<formato XXXX.XX.XX si hay suficiente certeza, vacio si no>",
  "keywords":        ["kw1","kw2","kw3","kw4","kw5"],
  "capitulos_probables": ["85","84"]
}}

Producto: {producto}

Responde SOLO con el JSON, sin markdown, sin explicacion.
"""


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
    # Quitar markdown fences si vienen
    m = re.search(r'\{[\s\S]*\}', texto)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        try:
            # Intento repair basico
            limpio = m.group(0).replace("'", '"')
            return json.loads(limpio)
        except Exception as e:
            print(f"[CLASIF-AUTO] JSON parse fail: {e}")
            return None


def generar_ficha_merceologica(descripcion: str) -> dict:
    """Etapa 1 — 7 preguntas merceologicas + keywords + capitulos probables."""
    t0 = time.time()
    prompt = _PROMPT_FICHA.format(producto=descripcion[:500])
    raw = _llamar_gemini(prompt)
    ficha = _parsear_json_gemini(raw) or {}

    # Normalizar campos obligatorios
    for k in ["que_es", "materia", "funcion", "uso", "usuarios", "clasificacion", "son_sugerido"]:
        ficha.setdefault(k, "")
    ficha.setdefault("keywords", [])
    ficha.setdefault("capitulos_probables", [])

    ficha["_latencia_ms"] = round((time.time() - t0) * 1000, 1)
    return ficha


# ── Etapa 2: Identificador de capitulo ───────────────────────────────────

def identificar_capitulos_candidatos(ficha: dict, limit: int = 3) -> list[str]:
    """
    Etapa 2. Combina:
      - capitulos_probables de la ficha (Gemini)
      - capitulos extraidos de los top-N FTS matches sobre 'codigos'
    """
    caps = []
    # 1. De la ficha
    for c in ficha.get("capitulos_probables", []):
        c = str(c).strip().zfill(2)
        if c.isdigit() and 1 <= int(c) <= 97 and c not in caps:
            caps.append(c)

    # 2. De FTS sobre 'codigos' con descripcion + keywords
    termino = " ".join([
        ficha.get("que_es", ""),
        ficha.get("funcion", ""),
        " ".join(ficha.get("keywords", [])[:5]),
    ]).strip()
    if termino:
        matches = buscar_clasificacion_sugerida(termino, limit=10)
        for m in matches:
            son = m.get("son", "")
            if len(son) >= 2:
                cap = son[:2]
                if cap not in caps:
                    caps.append(cap)
    return caps[:limit]


# ── Etapa 4: Refinador SON ───────────────────────────────────────────────

_PROMPT_REFINAR = """Eres experto clasificador arancelario RD (Arancel 7ma, SA 2022).

FICHA MERCEOLOGICA:
{ficha}

NOTAS LEGALES DEL CAPITULO CANDIDATO:
{notas}

DOCTRINA Y EJEMPLOS (biblioteca-nomenclatura RD):
{biblioteca}

Devuelve SOLO JSON:
{{
  "son_final":      "XXXX.XX.XX",
  "justificacion":  "<3-5 lineas citando RGI aplicada y nota legal>",
  "rgi_aplicada":   "RGI 1 | RGI 3a | RGI 3b | RGI 3c | RGI 6",
  "confianza":      "alta | media | baja",
  "alternativas":   ["XXXX.XX.XX","XXXX.XX.XX"]
}}

REGLAS:
- SON obligatorio formato XXXX.XX.XX (8 digitos con puntos)
- Si dudas, elige el mas especifico
- Cita nota legal o partida explicativa en justificacion
- NO inventes codigos, solo candidatos coherentes con las notas
"""


def refinar_son(ficha: dict, notas: dict, snippets: list[dict]) -> dict:
    t0 = time.time()
    prompt = _PROMPT_REFINAR.format(
        ficha=json.dumps(ficha, ensure_ascii=False, indent=2),
        notas=formatear_notas_gemini(notas)[:3000],
        biblioteca=formatear_contexto_gemini(snippets)[:3000],
    )
    raw = _llamar_gemini(prompt, timeout=30)
    out = _parsear_json_gemini(raw) or {}
    for k in ["son_final", "justificacion", "rgi_aplicada", "confianza"]:
        out.setdefault(k, "")
    out.setdefault("alternativas", [])
    # Validar formato SON
    son = (out.get("son_final") or "").strip()
    if not _SON_RE.match(son):
        out["son_final"] = ""
        out["_warning"] = f"SON devuelto '{son}' no valido"
    out["_latencia_ms"] = round((time.time() - t0) * 1000, 1)
    return out


# ── Etapa 5: Validador Capa 1 ────────────────────────────────────────────

def validar_capa1(son: str, ficha: dict) -> dict:
    """Intenta lookup exacto; si no existe, devuelve top-3 alternativas FTS."""
    out = {"son_consultado": son, "exacto": None, "alternativas": []}
    if son:
        out["exacto"] = consultar_son_exacto(son)
    if not out["exacto"]:
        # Buscar alternativas por descripcion
        termino = " ".join([
            ficha.get("que_es", ""),
            ficha.get("funcion", ""),
            ficha.get("materia", ""),
        ]).strip()
        if termino:
            out["alternativas"] = buscar_clasificacion_sugerida(termino, limit=3)
    return out


# ── Etapa 6: Publicador Notion ───────────────────────────────────────────

def publicar_notion(descripcion: str, ficha: dict, refinado: dict,
                    capa1: dict) -> Optional[dict]:
    """Escribe la ficha a Notion DB 'Fichas Merceologicas' (si configurada)."""
    api_key = os.environ.get("NOTION_API_KEY", "")
    db_id = os.environ.get("NOTION_DB_MERCEOLOGIA", "")
    if not api_key or not db_id:
        return {"ok": False, "razon": "NOTION_API_KEY o NOTION_DB_MERCEOLOGIA no configurada"}
    try:
        from notion_client import Client
        notion = Client(auth=api_key)

        son_final = refinado.get("son_final", "")
        gravamen = ""
        if capa1.get("exacto"):
            gravamen = f"DAI {capa1['exacto'].get('gravamen','?')}% | ITBIS {capa1['exacto'].get('itbis','?')}%"

        props = {
            "Producto":     {"title": [{"text": {"content": descripcion[:200]}}]},
            "SON Sugerido": {"rich_text": [{"text": {"content": son_final}}]},
            "Materia":      {"rich_text": [{"text": {"content": ficha.get("materia","")[:500]}}]},
            "Función":      {"rich_text": [{"text": {"content": ficha.get("funcion","")[:500]}}]},
            "Uso":          {"rich_text": [{"text": {"content": ficha.get("uso","")[:500]}}]},
            "Clasificación": {"rich_text": [{"text": {"content": refinado.get("justificacion","")[:1800]}}]},
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


# ── Orquestador ──────────────────────────────────────────────────────────

def clasificar_producto(descripcion: str, publicar: bool = False) -> dict:
    """
    Pipeline completo de 7 etapas. Retorna dict con todas las etapas + SON final.
    """
    t0 = time.time()
    resultado = {
        "descripcion":  descripcion,
        "etapas":       {},
        "son_final":    "",
        "confianza":    "",
        "validado":     False,
    }

    # [1] Ficha
    ficha = generar_ficha_merceologica(descripcion)
    resultado["etapas"]["1_ficha"] = ficha

    # [2] Capitulos candidatos
    caps = identificar_capitulos_candidatos(ficha)
    resultado["etapas"]["2_capitulos"] = caps
    cap_principal = caps[0] if caps else None

    # [3] Notas capitulo principal
    notas = {}
    if cap_principal:
        notas = leer_notas_capitulo(cap_principal)
    resultado["etapas"]["3_notas"] = notas

    # [3.5] Biblioteca RAG
    keywords = ficha.get("keywords", [])
    if not keywords:
        keywords = [ficha.get("que_es",""), ficha.get("funcion","")]
    snippets = investigar(keywords, capitulo=cap_principal, limit=5)
    resultado["etapas"]["35_biblioteca"] = [
        {k: v for k, v in s.items() if k != "texto"} | {"texto_preview": s["texto"][:200]}
        for s in snippets
    ]

    # [4] Refinar SON
    refinado = refinar_son(ficha, notas, snippets)
    resultado["etapas"]["4_refinado"] = refinado
    resultado["son_final"] = refinado.get("son_final", "")
    resultado["confianza"] = refinado.get("confianza", "")

    # [5] Validar Capa 1
    capa1 = validar_capa1(resultado["son_final"], ficha)
    resultado["etapas"]["5_capa1"] = capa1
    resultado["validado"] = bool(capa1.get("exacto"))

    # [6] Notion (opcional)
    if publicar:
        pub = publicar_notion(descripcion, ficha, refinado, capa1)
        resultado["etapas"]["6_notion"] = pub
    else:
        resultado["etapas"]["6_notion"] = {"ok": False, "razon": "no solicitado"}

    resultado["latencia_total_ms"] = round((time.time() - t0) * 1000, 1)
    return resultado


if __name__ == "__main__":
    desc = "Camara de videoconferencia para sala de conferencias, 4K, microfono integrado, conexion USB-C"
    r = clasificar_producto(desc, publicar=False)
    print(json.dumps(r, ensure_ascii=False, indent=2)[:3000])
