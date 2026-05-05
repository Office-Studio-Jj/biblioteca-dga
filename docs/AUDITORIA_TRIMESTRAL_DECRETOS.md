# Auditoría Trimestral — tabla_decretos

**Orden CEO 05-05-2026 — Sección 3.2**  
**Frecuencia:** Cada 90 días  
**Sin auditoría, el Paso 8.5 es una promesa vacía.**

---

## Procedimiento Obligatorio

Cada 90 días, el consultor debe:

### 1. Verificar Gaceta Oficial

- Consultar Gaceta Oficial RD (consultoria.gob.do) para nuevos decretos que afecten clasificación arancelaria
- Buscar: decretos que modifiquen DAI, ITBIS, ISC o exenciones
- Periodo: últimos 90 días desde última auditoría

### 2. Verificar Resoluciones DGA

- Consultar aduanas.gob.do → Resoluciones
- Buscar: resoluciones sobre clasificación anticipada (Art. 75 Ley 168-21)
- Buscar: resoluciones que modifiquen aplicación de Notas Legales

### 3. Verificar Derogaciones

- Confirmar que cada decreto en tabla_decretos con estado='vigente' sigue vigente
- Si fue derogado o modificado: actualizar estado + registrar en changelog
- Registrar referencia al instrumento que lo deroga

### 4. Actualizar Estados

```sql
-- Ejemplo de actualización
UPDATE tabla_decretos SET estado='derogado', derogado_por='Decreto XXX-XX', 
  fecha_derogacion='2026-XX-XX', updated_at=datetime('now')
WHERE id = ?;

-- Registrar en changelog
INSERT INTO decretos_changelog(decreto_id, accion, campo_modificado, 
  valor_anterior, valor_nuevo, fundamento_legal, autor)
VALUES(?, 'derogar', 'estado', 'vigente', 'derogado', 'Gaceta #XXXXX', 'nombre');
```

### 5. Registrar Fecha de Auditoría

```sql
UPDATE tabla_decretos SET fecha_ultima_auditoria=date('now'), auditor='nombre'
WHERE estado='vigente';
```

---

## Calendario

| Trimestre | Fecha límite | Responsable |
|-----------|-------------|-------------|
| Q1 2026 | 2026-03-31 | Consultor legal |
| Q2 2026 | 2026-06-30 | Consultor legal |
| Q3 2026 | 2026-09-30 | Consultor legal |
| Q4 2026 | 2026-12-31 | Consultor legal |

---

## Checklist de Auditoría

- [ ] Gaceta Oficial revisada (últimos 90 días)
- [ ] aduanas.gob.do revisado (resoluciones)
- [ ] Todos los decretos vigentes confirmados
- [ ] Decretos derogados/modificados actualizados
- [ ] Changelog actualizado con fundamento legal
- [ ] fecha_ultima_auditoria actualizada en BD
- [ ] Informe breve al CEO con hallazgos

---

## Alerta Automática

El sistema debe emitir alerta cuando:
- `fecha_ultima_auditoria` de cualquier decreto supere 90 días
- Mensaje: "ALERTA: Auditoría de decretos vencida. Última revisión: [fecha]. El Paso 8.5 puede operar con información desactualizada."

---

**Base legal:** Art. 75 Ley 168-21 (clasificación anticipada), Decreto 755-22 Arts. 3-5.
