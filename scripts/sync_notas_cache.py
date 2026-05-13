"""
Sincroniza notas_capitulos_cache.json con notas_legales_completas.json
Mantiene datos ISC existentes y agrega TODAS las notas legales,
notas de subpartida, notas adicionales y RGI del archivo completo.
"""
import json
import os

_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "notebooklm_skill", "data", "fuentes_nomenclatura")
_CACHE = os.path.join(_DATA, "notas_capitulos_cache.json")
_COMPLETAS = os.path.join(_DATA, "notas_legales_completas.json")
_BACKUP = os.path.join(_DATA, "notas_capitulos_cache.v2.backup.json")

# 1. Leer ambos archivos
with open(_CACHE, "r", encoding="utf-8") as f:
    cache = json.load(f)
with open(_COMPLETAS, "r", encoding="utf-8") as f:
    completas = json.load(f)

# 2. Backup del cache actual
with open(_BACKUP, "w", encoding="utf-8") as f:
    json.dump(cache, f, ensure_ascii=False, indent=2)
print(f"Backup guardado en: {_BACKUP}")

# 3. Estadisticas antes
caps_antes = len(cache.get("capitulos", {}))
secs_antes = len(cache.get("secciones", {}))

# 4. Agregar RGI completas al cache
rgi_text = completas.get("rgi", "")
if rgi_text:
    # Parsear las 6 RGI individuales
    cache["rgi_completas"] = rgi_text
    print(f"RGI completas agregadas ({len(rgi_text)} chars)")

# 5. Sincronizar capitulos
caps_completas = completas.get("capitulos", {})
caps_cache = cache.get("capitulos", {})

for cap_id, cap_data in caps_completas.items():
    if cap_id in caps_cache:
        # Capitulo ya existe en cache: ENRIQUECER sin perder datos ISC
        existente = caps_cache[cap_id]
        # Agregar/actualizar notas legales completas
        notas_completas = cap_data.get("notas_legales", [])
        if notas_completas:
            # Si las notas completas son mas extensas, reemplazar
            notas_existentes = existente.get("notas_legales", [])
            total_chars_existentes = sum(len(n) for n in notas_existentes)
            total_chars_completas = sum(len(n) for n in notas_completas)
            if total_chars_completas > total_chars_existentes:
                existente["notas_legales_completas"] = notas_completas
                print(f"  Cap {cap_id}: notas legales enriquecidas "
                      f"({total_chars_existentes} -> {total_chars_completas} chars)")
        # Agregar notas subpartida si existen
        ns = cap_data.get("notas_subpartida", [])
        if ns:
            existente["notas_subpartida"] = ns
            print(f"  Cap {cap_id}: {len(ns)} notas de subpartida agregadas")
        # Agregar notas adicionales si existen
        na = cap_data.get("notas_adicionales", [])
        if na:
            existente["notas_adicionales"] = na
            print(f"  Cap {cap_id}: {len(na)} notas adicionales agregadas")
    else:
        # Capitulo nuevo: crear entrada basica
        nueva_entrada = {
            "titulo": cap_data.get("titulo", ""),
            "notas_legales": cap_data.get("notas_legales", []),
            "aplica_isc": False,
        }
        ns = cap_data.get("notas_subpartida", [])
        if ns:
            nueva_entrada["notas_subpartida"] = ns
        na = cap_data.get("notas_adicionales", [])
        if na:
            nueva_entrada["notas_adicionales"] = na
        caps_cache[cap_id] = nueva_entrada

cache["capitulos"] = caps_cache

# 6. Sincronizar secciones
secs_completas = completas.get("secciones", {})
secs_cache = cache.get("secciones", {})

for sec_id, sec_data in secs_completas.items():
    if sec_id in secs_cache:
        existente = secs_cache[sec_id]
        notas_completas = sec_data.get("notas_legales", [])
        if notas_completas:
            total_existentes = sum(len(n) for n in existente.get("notas_legales", []))
            total_completas = sum(len(n) for n in notas_completas)
            if total_completas > total_existentes:
                existente["notas_legales_completas"] = notas_completas
                print(f"  Sec {sec_id}: notas legales enriquecidas "
                      f"({total_existentes} -> {total_completas} chars)")
        na = sec_data.get("notas_adicionales", [])
        if na:
            existente["notas_adicionales"] = na
    else:
        secs_cache[sec_id] = {
            "titulo": sec_data.get("titulo", ""),
            "capitulos": sec_data.get("capitulos", ""),
            "notas_legales": sec_data.get("notas_legales", []),
            "exclusiones": sec_data.get("exclusiones", []),
        }
        na = sec_data.get("notas_adicionales", [])
        if na:
            secs_cache[sec_id]["notas_adicionales"] = na

cache["secciones"] = secs_cache

# 7. Actualizar meta
cache["_meta"]["version"] = "3.0"
cache["_meta"]["ultima_actualizacion"] = "2026-05-12"
cache["_meta"]["descripcion"] = (
    "Cache COMPLETO de Notas Legales, Notas de Subpartida, Notas Adicionales "
    "y RGI del Arancel RD 7ma Enmienda. v3.0: sincronizado con "
    "notas_legales_completas.json (97 capitulos, 21 secciones). "
    "Usado por validador_jerarquia_sa.py, consultor_notas_arancel.py y pipeline_3_capas.py."
)
cache["_meta"]["total_capitulos"] = len(caps_cache)
cache["_meta"]["total_secciones"] = len(secs_cache)
cache["_meta"]["capitulos_con_notas"] = sum(
    1 for c in caps_cache.values()
    if c.get("notas_legales") or c.get("notas_legales_completas"))
cache["_meta"]["capitulos_con_notas_subpartida"] = sum(
    1 for c in caps_cache.values() if c.get("notas_subpartida"))

# 8. Guardar cache actualizado
with open(_CACHE, "w", encoding="utf-8") as f:
    json.dump(cache, f, ensure_ascii=False, indent=2)

caps_despues = len(cache.get("capitulos", {}))
secs_despues = len(cache.get("secciones", {}))

print()
print("=== SINCRONIZACION COMPLETADA ===")
print(f"Capitulos: {caps_antes} -> {caps_despues}")
print(f"Secciones: {secs_antes} -> {secs_despues}")
print(f"RGI: {'SI' if cache.get('rgi_completas') else 'NO'}")
print(f"Archivo: {_CACHE}")
