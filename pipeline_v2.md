# Pipeline v2 — Flujo sin NotebookLM
## Aprobado por CEO — 4 mayo 2026

---

## FLUJO ANTERIOR (obsoleto — archivo original conservado)
```
RECIBIDO → CLASIFICADO → EN NOTEBOOK (NotebookLM) → APROBADO → EN NOTION
```
NotebookLM procesaba consultas intermedias. Se elimina como paso de clasificación.

---

## FLUJO NUEVO (vigente)
```
RECIBIDO → CLASIFICADO → EN PROCESAMIENTO (Notion directo) → CURADO → PUBLICADO
```

### Roles actualizados

| Agente | Rol | Herramientas |
|--------|-----|--------------|
| **Gemini/NotebookLM** | Solo consulta académica de referencia. NO clasifica. NO procesa. | Cuadernos como biblioteca de estudio |
| **Notion (7 BDs)** | Fuente única de verdad. Recibe y almacena registros procesados. | Fichas Merceológicas, SOPs, Jurisprudencia, Regímenes, VUCERD, Valoración, Origen |
| **Claude/SQLite (Capa 1)** | Motor de clasificación arancelaria. 7,616 SON + 7 módulos. | arancel_rd.db, clasificador_rgi.py, validador_son.py, validador_pre_respuesta.py |
| **Pipeline 3 Capas** | Orquestador: Gemini prefiltro (Cap.) → Claude árbitro legal (SON final) | pipeline_3_capas.py |

---

## FLUJO DETALLADO

```
1. Usuario describe producto en lenguaje natural
   ↓
2. Gemini identifica Capítulo candidato (2 dígitos SOLAMENTE)
   - NO clasifica SON. Solo "huele" el capítulo.
   - Base: ask_gemini.py
   ↓
3. clasificador_rgi.py aplica RGI 1→2→3→4→5→6 secuencialmente
   - Fuente: SQLite arancel_rd.db (7,616 SON)
   - Consulta Notas Legales de Sección/Capítulo
   - Base legal: Ley 168-21 Art. 75, Decreto 755-22 Arts. 62-77
   ↓
4. validador_son.py verifica que la SON exista en el Arancel
   - Si no existe: rechaza + propone alternativas del mismo capítulo
   ↓
5. validador_pre_respuesta.py verifica todos los campos del informe
   - DAI/ITBIS/ISC contra SQLite — nunca datos inventados
   - Permisos contra permisos_por_capitulo.json
   ↓
6. Si confianza BAJA o REQUIERE_REVISION:
   - fallback_clasificacion.py devuelve capítulo + 3 candidatas + solicita ficha técnica
   - NUNCA devuelve error vacío
   ↓
7. Resultado verificado → Notion (BD correspondiente)
   - Estado: BORRADOR → CURADO → PUBLICADO
   - subir_registros_notion.py
   ↓
8. watcher_nuevos_pdfs.py (FUTURO — no activo aún)
   - Detecta PDFs nuevos en Cuadernos → procesa automático
```

---

## ESTADOS DE UN DOCUMENTO EN NOTION

| Estado | Significado |
|--------|-------------|
| RECIBIDO | Adjuntado a Cuaderno, pendiente de procesar |
| CLASIFICADO | Categorizado por tipo (legal, merceológico, SOP, etc.) |
| EN PROCESAMIENTO | Extracción en curso (extraer_pdfs_a_registros.py) |
| CURADO | Revisado por operativo o aforador |
| PUBLICADO | Disponible para consulta en la app |

---

## CAMBIOS RESPECTO AL FLUJO ANTERIOR

1. NotebookLM eliminado como paso de procesamiento (queda como referencia académica)
2. Notion es la fuente única de verdad — no hay paso intermedio
3. Validación doble antes de entregar respuesta (validador_son + validador_pre_respuesta)
4. Fallback garantizado — el sistema siempre responde algo verificado
5. 5 nuevos campos en tabla codigos: dai_pct, itbis_pct, isc_pct, permisos, notas_legales

---

*Documento: pipeline_v2.md | Creado: 04-05-2026 | CEO: José Rodolfo Santana C.*
*No modifica ni elimina pipeline_3_capas.py original.*
