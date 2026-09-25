"""Consulta SIREVUCE (sirevuce.aduanas.gob.do) para saber si un SON requiere formulario VUCE.

Fuente oficial DGA. Si el portal no responde, el resultado es NO_VERIFICADO: nunca se
infiere "no requiere" sin respuesta del portal.
"""

import html
import re
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser

BASE_URL = "https://sirevuce.aduanas.gob.do"
TRAMITES = {"importacion": "1"}
_TIMEOUT = 15
_CACHE_TTL = 24 * 3600
_cache = {}

_BLOCK_TAGS = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6",
               "table", "section", "button", "span", "label", "strong", "b", "td", "th"}

_ETIQUETAS_FORM = [
    "Tipo de Trámite", "Organismos externos", "Uso", "Formulario",
    "Certificado Fitosanitario", "Costo", "Concepto Costo", "Documentos",
    "Última fecha de revisión",
]


class _Lector(HTMLParser):
    """Convierte HTML en líneas de texto y extrae filas de tabla con sus enlaces."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lineas, self._buf = [], []
        self.filas, self._fila, self._celda, self._en_celda = [], None, [], False
        self._links_fila = []
        self._href = None

    def _cortar(self):
        t = " ".join("".join(self._buf).split())
        if t:
            self.lineas.append(t)
        self._buf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in _BLOCK_TAGS:
            self._cortar()
        if tag == "tr":
            self._fila, self._links_fila = [], []
        elif tag in ("td", "th") and self._fila is not None:
            self._en_celda, self._celda = True, []
        elif tag == "a":
            self._href = a.get("href")

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            if self._fila is not None:
                self._links_fila.append(self._href)
            self._href = None
        if tag in ("td", "th") and self._fila is not None and self._en_celda:
            self._fila.append(" ".join("".join(self._celda).split()))
            self._en_celda = False
        if tag == "tr" and self._fila is not None:
            if any(self._fila):
                self.filas.append({"celdas": self._fila, "links": self._links_fila})
            self._fila = None
        if tag in _BLOCK_TAGS:
            self._cortar()

    def handle_data(self, data):
        self._buf.append(data)
        if self._en_celda:
            self._celda.append(data)

    def close(self):
        super().close()
        self._cortar()


def _leer(html_txt):
    p = _Lector()
    p.feed(html_txt)
    p.close()
    return p


def _get(path_o_url, params=None):
    url = path_o_url if path_o_url.startswith("http") else urllib.parse.urljoin(BASE_URL + "/", path_o_url.lstrip("/"))
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (biblioteca-dga; consulta SIREVUCE)",
        "Accept": "text/html",
        "Accept-Language": "es-DO,es;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace"), url


def normalizar_son(texto):
    """Devuelve el SON XXXX.XX.XX si el texto contiene exactamente 8 dígitos de código."""
    m = re.search(r"(?<!\d)(\d{4})[.\-\s]?(\d{2})[.\-\s]?(\d{2})(?![\d.])", texto or "")
    return f"{m.group(1)}.{m.group(2)}.{m.group(3)}" if m else None


def parsear_reporte(html_txt):
    """Filas del 'Reporte de Aranceles': código, categoría, descripción y enlace 'Ver'."""
    out = []
    for f in _leer(html_txt).filas:
        c = f["celdas"]
        codigo = next((normalizar_son(x) for x in c if normalizar_son(x)), None)
        if not codigo:
            continue
        ver = next((h for h in f["links"] if h and "Report" not in h), None) or (f["links"][-1] if f["links"] else None)
        out.append({
            "son": codigo,
            "categoria": c[1] if len(c) > 1 else "",
            "descripcion": c[2] if len(c) > 2 else "",
            "detalle_href": html.unescape(ver) if ver else None,
        })
    return out


def _valor(lineas, etiqueta):
    pat = re.compile(rf"^{re.escape(etiqueta)}\s*:?\s*(.*)$", re.I)
    for i, l in enumerate(lineas):
        m = pat.match(l)
        if m:
            v = m.group(1).strip()
            if not v and i + 1 < len(lineas):
                v = lineas[i + 1]
            return v
    return ""


def parsear_detalle(html_txt):
    """Información general + formularios VUCE del detalle de un código."""
    lineas = _leer(html_txt).lineas
    info = {
        "son": normalizar_son(_valor(lineas, "Código")),
        "descripcion": _valor(lineas, "Descripción"),
        "categoria": _valor(lineas, "Categoría"),
        "gravamen": _valor(lineas, "Gravamen"),
        "itbis": _valor(lineas, "ITBIS"),
        "selectivo_especifico": _valor(lineas, "Selectivo Específico"),
        "selectivo_ad_valorem": _valor(lineas, "Selectivo Ad Valorem"),
    }

    idx = next((i for i, l in enumerate(lineas) if l.lower().startswith("formularios vuce")), None)
    info["seccion_vuce_presente"] = idx is not None
    formularios = []
    if idx is not None:
        fin = next((i for i in range(idx + 1, len(lineas)) if lineas[i].lower().startswith("nota")), len(lineas))
        bloque = lineas[idx + 1:fin]
        actual, etiqueta, previa = None, None, ""
        for l in bloque:
            if "dar clic para ver requisitos" in l.lower():
                nombre = re.sub(r"\(?dar clic para ver requisitos\)?", "", l, flags=re.I).strip(" ▼▲▾▴")
                if not nombre and previa:
                    nombre = previa
                    if actual is not None and etiqueta and actual["campos"][etiqueta][-1:] == [previa]:
                        actual["campos"][etiqueta].pop()
                actual = {"nombre": nombre, "campos": {}}
                formularios.append(actual)
                etiqueta, previa = None, ""
                continue
            if l.strip(" ▼▲▾▴"):
                previa = l.strip(" ▼▲▾▴")
            if actual is None:
                continue
            limpio = l.lstrip(" —–-")
            etq = next((e for e in _ETIQUETAS_FORM if limpio.lower().startswith(e.lower())), None)
            if etq:
                etiqueta = etq
                resto = limpio[len(etq):].lstrip(" :—-").strip()
                actual["campos"].setdefault(etiqueta, [])
                if resto:
                    actual["campos"][etiqueta].append(resto)
            elif etiqueta and l not in ("Solicitar servicio",):
                actual["campos"][etiqueta].append(l)
        for f in formularios:
            if not f["nombre"]:
                f["nombre"] = " ".join(f["campos"].get("Formulario", [])) or "Formulario VUCE"
    info["formularios"] = formularios
    return info


def _buscar(q, tramite):
    trades = TRAMITES[tramite]
    son = normalizar_son(q)
    intentos = []
    if son:
        digitos = son.replace(".", "")
        intentos += [{"TagIdSelect": digitos, "Trades": trades}, {"TagIdSelect2": digitos, "Trades": trades}]
    intentos.append({"TagIdSelect2": q, "Trades": trades})
    ultimo_url = None
    for params in intentos:
        html_txt, url = _get("/Home/Report", params)
        ultimo_url = url
        filas = parsear_reporte(html_txt)
        if son:
            filas = [f for f in filas if f["son"] == son] or filas
        if filas:
            return filas, html_txt, url
        if son and "Formularios VUCE" in html_txt:
            return [{"son": son, "detalle_href": None}], html_txt, url
    return [], None, ultimo_url


_VACIAS = set("""
a al algun alguna como con cual cuales de del donde el ella en es esa ese esta este estos hay la las lleva
llevan lo los me mi mis necesita necesitan necesito no o para por que quiero requiere requieren se si sin su
sus tiene tienen un una uno y ya debo puedo importar importo importacion importación exportar permiso permisos
vuce vucerd sirevuce formulario formularios partida codigo código arancel arancelario tramite trámite saber
consulta consultar producto productos mercancia mercancía favor
""".split())


def terminos_busqueda(pregunta):
    """SON si la pregunta trae uno; si no, las palabras clave del producto (máx. 3)."""
    son = normalizar_son(pregunta)
    if son:
        return son
    palabras = re.findall(r"[a-záéíóúñü0-9]+", (pregunta or "").lower())
    utiles = [p for p in palabras if p not in _VACIAS and len(p) > 2]
    return " ".join(utiles[:3])


def consultar_pregunta(pregunta, tramite="importacion"):
    """Consulta a partir de una pregunta libre; si la frase no da resultados, prueba la primera palabra clave."""
    termino = terminos_busqueda(pregunta)
    if not termino:
        return {"estado": "SIN_RESULTADOS", "consulta": pregunta, "resultados": []}
    res = consultar_sirevuce(termino, tramite)
    if res["estado"] == "SIN_RESULTADOS" and " " in termino:
        res = consultar_sirevuce(termino.split()[0], tramite)
    return res


def consultar_sirevuce(consulta, tramite="importacion", max_detalles=3):
    """Consulta SIREVUCE por SON (XXXX.XX.XX) o por descripción.

    Devuelve {"estado": VERIFICADO|SIN_RESULTADOS|NO_VERIFICADO, "resultados": [...], ...}.
    Cada resultado: son, descripcion, gravamen, itbis, requiere_vuce (bool), formularios.
    """
    q = (consulta or "").strip()
    if not q:
        return {"estado": "SIN_RESULTADOS", "consulta": q, "resultados": []}
    clave = (q.lower(), tramite)
    hit = _cache.get(clave)
    if hit and time.time() - hit[0] < _CACHE_TTL:
        return hit[1]

    try:
        filas, html_reporte, url_reporte = _buscar(q, tramite)
        resultados = []
        for f in filas[:max_detalles]:
            if f.get("detalle_href"):
                det_html, url_det = _get(f["detalle_href"])
            else:
                det_html, url_det = html_reporte, url_reporte
            det = parsear_detalle(det_html)
            det["son"] = det["son"] or f["son"]
            det["descripcion"] = det["descripcion"] or f.get("descripcion", "")
            det["categoria"] = det["categoria"] or f.get("categoria", "")
            det["requiere_vuce"] = bool(det["formularios"])
            det["url"] = url_det
            resultados.append(det)
        out = {
            "estado": "VERIFICADO" if resultados else "SIN_RESULTADOS",
            "consulta": q,
            "tramite": tramite,
            "fuente": BASE_URL,
            "url_busqueda": url_reporte,
            "total_coincidencias": len(filas),
            "resultados": resultados,
            "consultado": time.strftime("%Y-%m-%d %H:%M"),
        }
    except Exception as e:
        return {"estado": "NO_VERIFICADO", "consulta": q, "tramite": tramite,
                "fuente": BASE_URL, "error": f"{type(e).__name__}: {e}", "resultados": []}

    _cache[clave] = (time.time(), out)
    return out


def formatear_bloque(res):
    """Bloque markdown para anteponer a la respuesta del Cuaderno 6 (VUCERD)."""
    cab = "### Verificación oficial SIREVUCE (DGA)\n"
    if res["estado"] == "NO_VERIFICADO":
        return (cab + "**NO VERIFICADO**: no se obtuvo respuesta de sirevuce.aduanas.gob.do. "
                "No se afirma si requiere o no VUCE; confirme en " + BASE_URL + " antes de declarar.\n")
    if res["estado"] == "SIN_RESULTADOS":
        return (cab + f"Sin coincidencias en SIREVUCE para «{res['consulta']}». "
                "Indique el código SON de 8 dígitos (XXXX.XX.XX) para una verificación exacta.\n")
    partes = [cab]
    for r in res["resultados"]:
        veredicto = "**SÍ requiere VUCE**" if r["requiere_vuce"] else "**NO requiere formulario VUCE**"
        partes.append(f"\n**{r['son']}** — {r['descripcion']}\n")
        partes.append(f"- Resultado: {veredicto} (trámite: {res['tramite']})\n")
        if r.get("gravamen") or r.get("itbis"):
            partes.append(f"- Gravamen: {r.get('gravamen') or '—'} · ITBIS: {r.get('itbis') or '—'}"
                          f" · Selectivo ad valorem: {r.get('selectivo_ad_valorem') or '—'}\n")
        for f in r["formularios"]:
            c = f["campos"]
            j = lambda k: "; ".join(c.get(k, [])) or "—"
            partes.append(f"- Formulario: **{f['nombre']}**\n"
                          f"  - Organismo: {j('Organismos externos')}\n"
                          f"  - Uso: {j('Uso')} · Costo: {j('Costo')}\n"
                          f"  - Documentos: {j('Documentos')}\n"
                          f"  - Certificado fitosanitario: {j('Certificado Fitosanitario')}\n"
                          f"  - Última revisión SIREVUCE: {j('Última fecha de revisión')}\n")
    if res["total_coincidencias"] > len(res["resultados"]):
        partes.append(f"\n_{res['total_coincidencias']} coincidencias; se muestran {len(res['resultados'])}. "
                      "Use el código SON exacto para precisar._\n")
    partes.append(f"\nFuente: {res['url_busqueda']} (consultado {res['consultado']}). SIREVUCE indica que su "
                  "respuesta es informativa y no constituye una decisión definitiva de la DGA.\n")
    return "".join(partes)
