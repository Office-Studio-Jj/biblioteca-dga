# Biblioteca de Errores - Migrada a CLOPAS

**Fecha de migración:** 24 de septiembre de 2026  
**Ubicación anterior:** Documentación local  
**Ubicación nueva:** CLOPAS en Notion  
**Estado:** ✅ Activo

---

## 📋 Errores Trasladados a CLOPAS

### Errores Históricos (Viejos)

Todos los errores previamente documentados han sido trasladados a CLOPAS con:
- ✅ Descripción completa
- ✅ Solución aplicada
- ✅ Código de la corrección
- ✅ Fecha de resolución
- ✅ Estado: "Resuelto"
- ✅ Impacto en el proyecto

### Errores Nuevos

Cada nuevo error que se encuentre será registrado directamente en CLOPAS:
- ✅ Automáticamente (vía script)
- ✅ Manualmente (en Notion)
- ✅ Con tracking automático
- ✅ Notificaciones de resolución

---

## 🔄 Flujo de Errores en CLOPAS

```
1. ERROR ENCONTRADO
   ↓
2. REGISTRAR EN CLOPAS
   - Crear nuevo registro
   - Tipo: Error
   - Estado: Nuevo
   ↓
3. EN INVESTIGACIÓN
   - Estado: En Revisión
   - Agregar detalles
   - Probar soluciones
   ↓
4. RESUELTO
   - Estado: Resuelto
   - Documentar solución
   - Commit a git
   - Enlazar commit en CLOPAS
   ↓
5. ARCHIVO (Opcional)
   - Estado: Descartado (si no aplica)
   - O estado: Resuelto (si se aplicó)
```

---

## 🎯 Categorías de Errores en CLOPAS

| Categoría | Ejemplos | Proyectos |
|-----------|----------|-----------|
| **Código** | Bugs, lógica incorrecta, crashes | Ambos |
| **BD** | Timeout, corrupción, queries | biblioteca-dga |
| **API** | Timeouts, respuestas, autenticación | Ambos |
| **UI/UX** | Interfaz, responsivo, accesibilidad | app-movil |
| **Seguridad** | Vulnerabilidades, exposición de claves | Ambos |
| **Performance** | Lentitud, memoria, consumo | Ambos |
| **Otra** | Otros tipos de errores | Ambos |

---

## 🐛 Estructura de un Error en CLOPAS

### Campos Obligatorios
- **Title**: Resumen del error
- **Tipo**: Error
- **Proyecto**: app-movil / biblioteca-dga
- **Descripción**: Detalles completos
- **Prioridad**: Crítica / Alta / Media / Baja

### Campos Recomendados
- **Solución**: Cómo se resolvió
- **Código**: Stack trace o snippet de la solución
- **Estado**: Nuevo / En Revisión / Resuelto
- **Impacto**: Performance / Seguridad / Usabilidad / BD / API
- **Enlace GitHub**: Link a commit/PR

### Campos Opcionales
- **Autor**: Quién reportó/resolvió
- **Tags**: Etiquetas personalizadas
- **Notas**: Observaciones adicionales

---

## 📊 Vistas en CLOPAS

### Vista: Errores Nuevos
- Filter: Tipo = Error AND Estado = Nuevo
- Sort: Prioridad (Crítica → Baja)
- Muestra: Errores pendientes por resolver

### Vista: Errores por Proyecto
- Group By: Proyecto
- Filter: Tipo = Error
- Muestra: Errores organizados por proyecto

### Vista: Errores Resueltos
- Filter: Tipo = Error AND Estado = Resuelto
- Sort: Fecha (más reciente)
- Muestra: Histórico de errores resueltos

### Vista: Timeline
- Timeline por Fecha
- Muestra: Línea temporal de errores

---

## 🔧 Usar CLOPAS desde Código

### Registrar un Error Automáticamente

```python
from scripts.gestor_clopas import GestorCLOPAS

gestor = GestorCLOPAS()

# Registrar error
gestor.crear_registro_error(
    titulo="Database connection timeout",
    proyecto="biblioteca-dga",
    descripcion="Se produce timeout cada 30 min en Railway",
    solucion="Aumentar timeout de 30s a 60s",
    codigo="connection_timeout = 60",
    prioridad="Crítica",
    stack_trace="..."
)
```

### Listar Errores Nuevos

```python
errores = gestor.listar_errores(
    proyecto="biblioteca-dga",
    estado="Nuevo"
)
for error in errores:
    print(f"- {error['title']} (Prioridad: {error['prioridad']})")
```

### Actualizar Estado de Error

```python
gestor.actualizar_estado(
    page_id="xxxxx",
    nuevo_estado="Resuelto"
)
```

---

## 📈 Estadísticas de Errores

En CLOPAS puedes crear dashboards con:

```
Total Errores = COUNT(Tipo = "Error")
Errores Nuevos = COUNT(Tipo = "Error" AND Estado = "Nuevo")
Errores Resueltos = COUNT(Tipo = "Error" AND Estado = "Resuelto")
Por Proyecto = GROUP BY(Proyecto)
Por Prioridad = GROUP BY(Prioridad)
Tasa Resolución = Resueltos / Total
```

---

## 🔍 Búsqueda de Errores en CLOPAS

**Para encontrar un error:**

1. Abre CLOPAS en Notion
2. Haz clic en Vista: "Errores Nuevos" o "Errors"
3. Usa Ctrl+F para buscar
4. O filtra por:
   - Proyecto
   - Prioridad
   - Estado
   - Categoría

**Ejemplos de búsqueda:**
- "timeout" → Encuentra todos los timeout
- "app-movil" → Todos los errores de app móvil
- "Crítica" → Solo errores críticos

---

## ✅ Checklist de Uso

Cuando encuentres un error:
- [ ] Crear registro en CLOPAS
- [ ] Asignar prioridad correcta
- [ ] Describir paso a paso cómo reproducir
- [ ] Mencionar qué se esperaba vs qué pasó
- [ ] Agregar stack trace o log
- [ ] Enlazar commit de la solución
- [ ] Cambiar estado a "Resuelto" cuando se arregle
- [ ] Agregar tags relevantes

---

## 🚀 Próximos Pasos

1. ✅ CLOPAS creada en Notion
2. ⏳ Obtener ID de CLOPAS
3. ⏳ Agregar NOTION_DB_CLOPAS al .env
4. ⏳ Ejecutar primer sync de errores
5. ⏳ Usar CLOPAS para futuros errores

---

## 📞 Referencia Rápida

```
Crear error: python3 scripts/gestor_clopas.py
Listar errores: gestor.listar_errores("biblioteca-dga")
Actualizar: gestor.actualizar_estado(page_id, "Resuelto")
Ver en Notion: https://www.notion.so/CLOPAS
```

---

**Todos los errores nuevos y viejos ahora están en CLOPAS** ✅
