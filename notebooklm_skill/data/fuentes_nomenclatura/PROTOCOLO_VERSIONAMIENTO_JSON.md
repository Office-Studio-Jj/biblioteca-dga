# Protocolo de Versionamiento — JSON Guardián (Notas Legales)

**Orden CEO 05-05-2026 — Sección 2.5**  
**Archivo controlado:** `notas_capitulos_cache.json`

---

## 1. Formato de Versión

```
notas_legales_arancel_rd_v[X.Y].json
```

- **X** = Enmienda SA (actualmente 7)
- **Y** = Revisión interna (incrementa con cada actualización)

Ejemplo: `notas_legales_arancel_rd_v7.3.json`

El archivo activo siempre se llama `notas_capitulos_cache.json` (symlink lógico). Las versiones anteriores se archivan con nombre completo.

## 2. Reglas de Actualización

1. Toda actualización requiere **doble validación**:
   - Extracción automática (pdfplumber/script)
   - Revisión humana (consultor legal)

2. Solo se actualiza cuando:
   - DGA emite resolución que modifica una Nota Legal
   - Se publica nueva enmienda SA (OMA/WCO)
   - Se detecta error de tipeo verificado contra PDF oficial

3. **NUNCA** se elimina una versión anterior. Se archiva en `./versiones_anteriores/`.

## 3. Log de Cambios Obligatorio

Cada actualización agrega entrada al campo `_meta.changelog`:

```json
{
  "version": "7.Y",
  "fecha": "2026-XX-XX",
  "autor": "nombre del consultor",
  "fundamento_legal": "Resolución DGA XXX-XX / Gaceta Oficial #XXXXX",
  "cambios": ["Nota X del Cap. Y modificada: ..."],
  "validado_por": "nombre del revisor humano"
}
```

## 4. Procedimiento

```
1. Detectar necesidad de cambio (Resolución DGA, Gaceta Oficial, error reportado)
2. Crear copia: notas_legales_arancel_rd_v7.[Y-1].json → versiones_anteriores/
3. Aplicar cambio en notas_capitulos_cache.json
4. Agregar entrada a _meta.changelog
5. Incrementar _meta.version
6. Validación humana: consultor firma con nombre en changelog
7. Commit con mensaje: "chore(notas): vX.Y — [fundamento legal]"
8. Deploy
```

## 5. Detección de Errores

Si se sospecha error de tipeo en el JSON:
1. Comparar contra PDF oficial del Arancel 7ma Enmienda
2. Si confirma error: corregir + log
3. Si no confirma: NO tocar. El PDF es verdad absoluta.

## 6. Responsables

| Rol | Responsabilidad |
|-----|----------------|
| Script automático | Extracción inicial desde PDF |
| Consultor legal | Validación de contenido, firma en changelog |
| Sistema | Versionamiento automático, archivado |
| CEO | Autorización de cambios estructurales (nuevas secciones/capítulos) |

---

**Sin este protocolo, el Paso 5 del flujo de clasificación es una promesa vacía.**
