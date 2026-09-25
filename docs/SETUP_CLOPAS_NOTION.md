# CLOPAS - Sistema Central de Control de Cambios

**Fecha:** 24 de septiembre de 2026  
**Propósito:** Backup centralizado de correcciones, creaciones y errores  
**Proyectos:** app móvil + biblioteca-dga  
**Ubicación:** Notion

---

## 🎯 ¿Qué es CLOPAS?

**CLOPAS** = Control Logs + Operaciones + Arquitectura + Sistema

Sistema centralizado en Notion que contiene:
- ✅ Todas las correcciones realizadas
- ✅ Todas las creaciones de contenidos
- ✅ Biblioteca completa de errores (nuevos y viejos)
- ✅ Tracking de cambios automático
- ✅ Historia de revisiones

---

## 🚀 Crear CLOPAS en Notion (Paso a Paso)

### Paso 1: Crear Base de Datos

1. Abre Notion → biblioteca-dga
2. Haz clic en **"+ Add a database"**
3. Selecciona **"Database"**
4. Asigna el nombre: **"CLOPAS"**
5. Elige tipo: **"Table"**

### Paso 2: Configurar Propiedades

Agregar estas propiedades (campos) a la tabla CLOPAS:

| Propiedad | Tipo | Descripción |
|-----------|------|-------------|
| **Title** | Text | Título del cambio/error/creación |
| **Tipo** | Select | Corrección / Creación / Error / Feature / Bug |
| **Proyecto** | Select | app-movil / biblioteca-dga |
| **Categoría** | Select | Código / Documentación / BD / UI/UX / Seguridad / Otra |
| **Descripción** | Text | Descripción detallada |
| **Solución** | Text | Cómo se resolvió |
| **Código** | Code | Snippet de código (si aplica) |
| **Fecha** | Date | Fecha del cambio |
| **Estado** | Select | Nuevo / En Revisión / Resuelto / Descartado |
| **Prioridad** | Select | Crítica / Alta / Media / Baja |
| **Autor** | Text | Quien hizo el cambio |
| **Impacto** | Multi-select | Performance / Seguridad / Usabilidad / BD / API |
| **Tags** | Multi-select | Etiquetas personalizadas |
| **Enlace GitHub** | URL | Link a commit/PR |
| **Notas** | Text | Observaciones adicionales |

### Paso 3: Crear Vistas

Crea estas vistas para organizar:

**Vista 1: Por Estado**
- Filter: Estado = Nuevo
- Group By: Proyecto

**Vista 2: Por Prioridad**
- Filter: Estado = En Revisión o Nuevo
- Sort By: Prioridad (Crítica → Baja)

**Vista 3: Por Proyecto**
- Group By: Proyecto
- Filter: Estado ≠ Descartado

**Vista 4: Errors (Biblioteca de Errores)**
- Filter: Tipo = Error
- Sort By: Fecha (más reciente primero)

**Vista 5: Timeline**
- Timeline view (por Fecha)

---

## 🔑 Obtener ID de la Base de Datos

1. Abre la base de datos CLOPAS en Notion
2. La URL será algo como:
   ```
   https://www.notion.so/XXXXXXXXXXXXXXXXXXXXXXXXXXXXX?v=YYYYYYYYYYYYYYYYY
   ```
3. El ID es: `XXXXXXXXXXXXXXXXXXXXXXXXXXXXX`
4. Cópialo y guárdalo

---

## 📋 Estructura de un Registro en CLOPAS

### Ejemplo: Corrección

```
Title: Corregir validación de Email en login
Tipo: Corrección
Proyecto: app-movil
Categoría: Código
Descripción: 
  La validación de email no aceptaba algunos dominios válidos.
  Regex estaba muy restrictiva.
Solución:
  Actualizar regex a RFC 5322 completo
Código:
  // Antes
  const emailRegex = /^[a-z]+@[a-z]+\.[a-z]+$/
  
  // Después
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
Fecha: 2026-09-24
Estado: Resuelto
Prioridad: Alta
Autor: Tu Nombre
Impacto: Seguridad, Usabilidad
Tags: regex, validación, login
Enlace GitHub: https://github.com/.../commit/abc123
```

### Ejemplo: Error

```
Title: Database connection timeout en producción
Tipo: Error
Proyecto: biblioteca-dga
Categoría: BD
Descripción:
  Timeout de conexión a SQLite cada 30 minutos en Railway
Solución:
  Aumentar timeout de conexión a 60 segundos
  Agregar retry automático (3 intentos)
Código:
  connection_timeout = 60
  max_retries = 3
Fecha: 2026-09-20
Estado: Resuelto
Prioridad: Crítica
Autor: Tu Nombre
Impacto: Performance, Disponibilidad
Tags: database, timeout, production
Enlace GitHub: https://github.com/.../commit/def456
```

---

## 🔄 Usar CLOPAS desde Python

Ver archivo: `scripts/gestor_clopas.py`

---

## 📊 Estadísticas en CLOPAS

Crear una página con botones para:

```
[Total Errores] = FILTER(Tipo = "Error")
[Errores Resueltos] = FILTER(Tipo = "Error" AND Estado = "Resuelto")
[Pendientes] = FILTER(Estado = "Nuevo" OR "En Revisión")
[Por Proyecto] = GROUP BY Proyecto
```

---

## 🔐 Permisos

- Solo tú puedes editar CLOPAS
- Compartido en lectura con el equipo (opcional)
- Backups automáticos en GitHub

---

## ✅ Checklist Final

- [ ] CLOPAS creada en Notion
- [ ] Propiedades configuradas
- [ ] Vistas creadas
- [ ] ID de base de datos copiado
- [ ] URL guardada: https://www.notion.so/XXXXX
- [ ] Archivos trasladados

---

**Estado:** Listo para configurar  
**Próximo paso:** Compartir ID de base de datos
