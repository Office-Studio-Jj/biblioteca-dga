# Manual de Contingencia — Sistema Two-Brain RD

**Orden CEO 05-05-2026 — Sección 3.3**  
**Principio:** El protocolo legal existe antes de la tecnología y funciona sin ella.

---

## Escenarios de Falla y Protocolo

### FALLA LAYER 1 — SQLite (arancel_rd.db)

| Síntoma | Acción |
|---------|--------|
| DB corrupta o inaccesible | Clasificación manual con PDF del Arancel 7ma Enmienda |
| Código SON no encontrado | Verificar en aduanas.gob.do → clasificación manual |
| Gravamen incorrecto | Cruzar contra PDF oficial, reportar error en sistema |

**Procedimiento:**
1. Consultor abre PDF "Arancel 7ma Enmienda de la República Dominicana"
2. Localiza Sección → Capítulo → Partida → Subpartida manualmente
3. Lee Notas Legales directamente del PDF
4. Aplica RGI 1→6 según protocolo estándar
5. Registra clasificación en formato papel/Excel hasta restauración

---

### FALLA LAYER 2 — Notion (BDs conocimiento)

| Síntoma | Acción |
|---------|--------|
| Notion API caída | Clasificación sin precedentes (pierde eficiencia, NO precisión) |
| BD Fichas inaccesible | Clasificar desde cero sin consultar fichas anteriores |
| Timeout Notion | Reintentar x3 con backoff, luego continuar sin precedentes |

**Procedimiento:**
1. El sistema emite: "Capa 2 no disponible. Clasificación sin precedentes."
2. La clasificación procede normalmente siguiendo los 11 pasos
3. Se pierde contexto de fichas previas pero NO se pierde precisión legal
4. Al restaurarse Notion, registrar la nueva clasificación como ficha

---

### FALLA LAYER 3 — Claude API / Gemini

| Síntoma | Acción |
|---------|--------|
| Claude API no responde | Clasificación manual por consultor siguiendo 11 pasos en papel |
| Gemini timeout | Consultor identifica Capítulo manualmente (2 dígitos) |
| Rate limit excedido | Cola de espera + clasificación manual urgentes |
| Respuesta incoherente | Descartar respuesta, consultor clasifica manualmente |

**Procedimiento:**
1. El sistema emite: "Capa 3 no disponible. Activar protocolo manual."
2. Consultor toma control total del flujo de 11 pasos
3. Usa PDF del Arancel + Notas Legales impresas/PDF
4. Aplica RGI secuencialmente (mismo protocolo, sin automatización)
5. Documenta clasificación manualmente
6. Al restaurarse el servicio, alimentar la clasificación al sistema

---

### FALLA COMPLETA — Todas las capas

**El sistema NUNCA puede decir "no puedo clasificar porque la tecnología falló."**

Procedimiento de contingencia total:
1. Consultor activa protocolo 100% manual
2. Materiales requeridos (deben estar disponibles siempre):
   - PDF Arancel 7ma Enmienda (copia local)
   - PDF Decreto 755-22 (reglamento)
   - PDF Notas Explicativas SA (OMA)
   - Tabla de DAI/ITBIS/ISC impresa o en Excel
3. Flujo: los mismos 11 pasos del sistema, ejecutados por humano
4. Registro: Excel/formulario papel
5. Al restaurarse: migrar clasificaciones manuales al sistema

---

## Materiales de Contingencia Obligatorios

Estos archivos deben existir en copia local (no solo en cloud):

| Archivo | Ubicación backup | Actualización |
|---------|-----------------|---------------|
| Arancel 7ma Enmienda PDF | `./backup/arancel_7ma_enmienda.pdf` | Cada nueva enmienda |
| Decreto 755-22 PDF | `./backup/decreto_755_22.pdf` | Si se modifica |
| Notas Legales JSON | `./backup/notas_capitulos_cache_vX.Y.json` | Cada actualización |
| Tabla DAI/ITBIS Excel | `./backup/tabla_gravamenes.xlsx` | Trimestral |
| RGI 1-6 texto | `./backup/rgi_texto_completo.txt` | Estable |

---

## Tiempos Máximos de Indisponibilidad

| Capa | Tiempo máximo sin servicio | Escalación |
|------|---------------------------|-----------|
| Layer 1 (SQLite) | 1 hora | Restaurar desde backup, activar manual |
| Layer 2 (Notion) | 4 horas | Continuar sin precedentes |
| Layer 3 (APIs) | 2 horas | Activar protocolo manual completo |
| Total | 30 minutos | CEO notificado, protocolo manual inmediato |

---

## Responsables

| Rol | Acción en contingencia |
|-----|----------------------|
| Sistema | Detectar falla, emitir alerta, registrar timestamp |
| Consultor | Activar protocolo manual, clasificar sin tecnología |
| Administrador | Restaurar servicio, migrar datos manuales |
| CEO | Decisión sobre continuidad si falla > 24h |

---

**Base legal:** Ley 168-21 Art. 75 (clasificación anticipada), Decreto 755-22 Arts. 3-5 (sistema informático).  
El sistema informático es herramienta, no requisito. La clasificación procede con o sin él.
