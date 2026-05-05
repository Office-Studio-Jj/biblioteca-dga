# PROPUESTA: Integración Pasos Bloqueantes en orquestador_capa3.py

**Para aprobación CEO — 05-05-2026**  
**Estado:** PENDIENTE DE AUTORIZACIÓN

---

## Cambios Propuestos

### 1. PASO 5 — Lectura Notas Legales (BLOQUEANTE)

**Qué:** Agregar función `consultar_notas_legales(capitulo: int)` que lee de `notas_capitulos_cache.json`.

**Comportamiento bloqueante:**
- Si el JSON no existe → ERROR: sistema se detiene, no clasifica
- Si el capítulo solicitado no tiene notas → ERROR: detener con mensaje "Notas Legales no disponibles para Capítulo X"
- Si el JSON responde → continuar con las notas como contexto obligatorio

**Código propuesto:**
```python
def consultar_notas_legales(capitulo: int) -> dict:
    """Paso 5 BLOQUEANTE: Lee Notas Legales del JSON guardián."""
    json_path = os.path.join(_HERE, "..", "notebooklm_skill", "data", 
                             "fuentes_nomenclatura", "notas_capitulos_cache.json")
    if not os.path.exists(json_path):
        return {"error": "BLOQUEANTE: notas_capitulos_cache.json no encontrado. Clasificación detenida.",
                "bloquea": True}
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    cap_key = str(capitulo)
    if cap_key not in data.get("capitulos", {}):
        return {"error": f"BLOQUEANTE: Sin Notas Legales para Capítulo {capitulo}. Clasificación detenida.",
                "bloquea": True}
    return {"notas": data["capitulos"][cap_key], "bloquea": False}
```

---

### 2. PASO 6.5 — Solicitud de Ficha Técnica

**Qué:** Cuando datos insuficientes para aplicar RGI con certeza → NO clasificar, pedir ficha.

**Mensaje estandarizado:**
```
"CLASIFICACIÓN DETENIDA — Se requiere ficha técnica del producto.
Información insuficiente para aplicar las Reglas Generales de Interpretación con certeza.
Proporcione: composición, función principal, uso previsto, especificaciones técnicas.
Base legal: Decreto 755-22, RGI 1-6 (Convenio SA Art. 3)."
```

**Código propuesto:**
```python
def solicitar_ficha_tecnica(motivo: str) -> dict:
    """Paso 6.5: Detiene clasificación y solicita ficha técnica."""
    return {
        "estado": "ficha_requerida",
        "mensaje": (
            "CLASIFICACIÓN DETENIDA — Se requiere ficha técnica del producto. "
            f"Motivo: {motivo}. "
            "Proporcione: composición, función principal, uso previsto, especificaciones técnicas. "
            "Base legal: Decreto 755-22, RGI 1-6 (Convenio SA Art. 3)."
        ),
        "bloquea": True,
    }
```

---

### 3. PASO 8.5 — Cruce contra tabla_decretos

**Qué:** Después de clasificación técnica, cruzar contra decretos vigentes que puedan modificar DAI/ITBIS/ISC.

**Ya implementado en:** `capa1_sqlite/consultar_decretos.py` → función `paso_8_5_cruce_decretos()`

**Comportamiento:**
- Tabla vacía → advertencia (no bloquea, pero informa)
- Decretos encontrados → informar cuáles aplican
- Conflicto irreconciliable → DETENER, escalar a humano

---

## Integración Propuesta

Agregar al final de `orquestador_capa3.py`:

```python
from capa1_sqlite.paso_0_5_regimen import verificar_regimen
from capa1_sqlite.consultar_decretos import paso_8_5_cruce_decretos
```

Y crear función wrapper `clasificar_completo()` que ejecuta:
1. Paso 0.5 (régimen)
2. Pasos 1-4 (existentes)
3. Paso 5 (notas legales — BLOQUEANTE)
4. Paso 6 (RGI)
5. Paso 6.5 (ficha técnica si insuficiente)
6. Pasos 7-8 (existentes)
7. Paso 8.5 (cruce decretos)
8. Pasos 9-10 (existentes)

---

## Riesgo

- BAJO: los archivos nuevos ya están creados y testeables
- El orquestador actual NO se toca hasta autorización
- Rollback: simplemente no importar los nuevos módulos

---

**ESPERANDO AUTORIZACIÓN CEO PARA MODIFICAR `orquestador_capa3.py`**
