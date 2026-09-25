"""Registro automático en CLOPAS (Notion) de las verificaciones VUCERD/SIREVUCE.

Solo guarda datos oficiales de SIREVUCE (SON, formularios, organismo, costo). Nunca el texto
de la pregunta ni la identidad del usuario (Ley 172-13, protección de datos personales).
"""

import hashlib
import json
import os
import threading
import time
import urllib.request

_NOTION = "https://api.notion.com/v1"
_DB_POR_DEFECTO = "e95803c0833045848ac4dc6fa7509bc0"
_vistos = set()
_lock = threading.Lock()


def _activo():
    return os.environ.get("CLOPAS_AUTO", "1") != "0" and bool(os.environ.get("NOTION_API_KEY"))


def _db():
    return os.environ.get("NOTION_DB_CLOPAS") or _DB_POR_DEFECTO


def _notion(ruta, cuerpo):
    req = urllib.request.Request(
        f"{_NOTION}{ruta}", data=json.dumps(cuerpo).encode(), method="POST",
        headers={"Authorization": f"Bearer {os.environ['NOTION_API_KEY']}",
                 "Notion-Version": "2022-06-28", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def _txt(v):
    return {"rich_text": [{"text": {"content": str(v)[:1990]}}]} if v else {"rich_text": []}


def _buscar_por_titulo(titulo):
    r = _notion(f"/databases/{_db()}/query",
                {"filter": {"property": "Title", "title": {"equals": titulo}}, "page_size": 1})
    return (r.get("results") or [None])[0]


def _crear(titulo, tipo, categoria, estado, prioridad, descripcion, solucion="", codigo="",
           tags=(), impacto=(), enlace=None):
    props = {
        "Title": {"title": [{"text": {"content": titulo[:200]}}]},
        "Tipo": {"select": {"name": tipo}},
        "Proyecto": {"select": {"name": "biblioteca-dga"}},
        "Categoría": {"select": {"name": categoria}},
        "Estado": {"select": {"name": estado}},
        "Prioridad": {"select": {"name": prioridad}},
        "Descripción": _txt(descripcion),
        "Solución": _txt(solucion),
        "Código": _txt(codigo),
        "Autor": _txt("CLOPAS automático (Cuaderno 6 VUCERD)"),
        "Fecha": {"date": {"start": time.strftime("%Y-%m-%d")}},
        "Tags": {"multi_select": [{"name": t} for t in tags]},
        "Impacto": {"multi_select": [{"name": i} for i in impacto]},
    }
    if enlace:
        props["Enlace GitHub"] = {"url": enlace}
    return _notion("/pages", {"parent": {"database_id": _db()}, "properties": props})


def _huella(r):
    """Resumen estable del resultado oficial, para detectar cambios en SIREVUCE."""
    base = {"vuce": r["requiere_vuce"], "grav": r.get("gravamen"), "itbis": r.get("itbis"),
            "formularios": sorted(
                (f["nombre"], "; ".join(f["campos"].get("Organismos externos", [])),
                 "; ".join(f["campos"].get("Costo", []))) for f in r.get("formularios", []))}
    return hashlib.sha256(json.dumps(base, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def _describir(r):
    lineas = [("SÍ requiere VUCE" if r["requiere_vuce"] else "NO requiere formulario VUCE")
              + f" (SIREVUCE, importación). Gravamen {r.get('gravamen') or '—'}, ITBIS {r.get('itbis') or '—'}."]
    for f in r.get("formularios", []):
        c = f["campos"]
        j = lambda k: "; ".join(c.get(k, [])) or "—"
        lineas.append(f"Formulario: {f['nombre']} | Organismo: {j('Organismos externos')} | "
                      f"Costo: {j('Costo')} | Documentos: {j('Documentos')} | "
                      f"Revisión SIREVUCE: {j('Última fecha de revisión')}")
    return "\n".join(lineas)


def _registrar_resultado(r):
    son = r.get("son")
    if not son:
        return
    huella = _huella(r)
    with _lock:
        if (son, huella) in _vistos:
            return
        _vistos.add((son, huella))
    titulo = f"[VUCE] {son} — {(r.get('descripcion') or '').strip(' -')[:120]}"
    existente = _buscar_por_titulo(titulo)
    if existente is None:
        _crear(titulo, "Creación", "BD", "Resuelto", "Baja", _describir(r),
               solucion=f"Fuente oficial: {r.get('url', '')}", codigo=f"huella={huella}",
               tags=("VUCERD", "SIREVUCE", "Requiere VUCE" if r["requiere_vuce"] else "Sin VUCE"))
        print(f"[CLOPAS-AUTO] Registrado {son}")
        return
    codigo = "".join(t.get("plain_text", "") for t in existente["properties"].get("Código", {}).get("rich_text", []))
    if f"huella={huella}" not in codigo:
        _crear(f"[VUCE] {son} cambió en SIREVUCE ({time.strftime('%Y-%m-%d')})", "Corrección", "BD",
               "En Revisión", "Alta",
               "El resultado oficial de SIREVUCE difiere del registrado.\nAhora: " + _describir(r),
               solucion=f"Revisar y actualizar el registro original: {existente.get('url', '')}",
               codigo=f"huella={huella}", tags=("VUCERD", "SIREVUCE", "Cambio oficial"), impacto=("BD",))
        print(f"[CLOPAS-AUTO] Cambio detectado en {son}")


def _registrar_error_diario(titulo_base, prioridad, descripcion):
    titulo = f"{titulo_base} {time.strftime('%Y-%m-%d')}"
    with _lock:
        if titulo in _vistos:
            return
        _vistos.add(titulo)
    if _buscar_por_titulo(titulo) is None:
        _crear(titulo, "Error", "Código", "Nuevo", prioridad, descripcion,
               solucion="Revisar /health/sirevuce en producción.",
               tags=("VUCERD", "SIREVUCE"), impacto=("API",))
        print(f"[CLOPAS-AUTO] Error registrado: {titulo}")


def _en_segundo_plano(fn, *args):
    def _run():
        try:
            fn(*args)
        except Exception as e:
            print(f"[CLOPAS-AUTO] No se pudo registrar en CLOPAS: {type(e).__name__}: {e}")
    threading.Thread(target=_run, daemon=True).start()


def registrar_consulta_vucerd(res):
    """Registra en CLOPAS el resultado de consultor_sirevuce (no bloquea)."""
    if not _activo() or not res:
        return
    if res.get("estado") == "VERIFICADO":
        for r in res.get("resultados", []):
            _en_segundo_plano(_registrar_resultado, r)
    elif res.get("estado") == "NO_VERIFICADO":
        _en_segundo_plano(_registrar_error_diario, "[VUCERD] SIREVUCE sin respuesta", "Alta",
                          f"sirevuce.aduanas.gob.do no respondió: {res.get('error', '')}. "
                          "El Cuaderno 6 respondió NO VERIFICADO.")


def registrar_salud_sirevuce(status, detalle):
    """Registra fallas del chequeo /health/sirevuce (una por día y tipo)."""
    if not _activo() or status == "OK":
        return
    if status == "REVISAR_PARSER":
        _en_segundo_plano(_registrar_error_diario, "[VUCERD] Lector SIREVUCE no reconoce el HTML", "Crítica",
                          "SIREVUCE respondió pero el lector no extrajo el resultado esperado para 9022.90.10. "
                          f"Detalle: {json.dumps(detalle, ensure_ascii=False)[:1500]}")
    else:
        _en_segundo_plano(_registrar_error_diario, "[VUCERD] SIREVUCE sin respuesta", "Alta",
                          f"Chequeo /health/sirevuce sin conexión: {detalle}")
