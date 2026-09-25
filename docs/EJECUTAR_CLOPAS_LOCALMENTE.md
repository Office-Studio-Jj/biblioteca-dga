# Configurar CLOPAS - Instrucciones para tu PC

## ⚠️ Situación Actual

El entorno remoto de Claude Code tiene **restricciones de red** que impiden conectar a `api.notion.com`. Por eso necesitas ejecutar el script de configuración desde tu **PC local** (donde tienes acceso a internet sin restricciones).

---

## 🚀 Pasos para Ejecutar desde tu PC

### Paso 1: Clonar o Actualizar el Repositorio

Si aún no tienes el repo en tu PC:
```bash
git clone https://github.com/Office-Studio-Jj/biblioteca-dga.git
cd biblioteca-dga
```

Si ya lo tienes, actualiza:
```bash
git fetch origin
git checkout claude/abrir-powershell-fofq4h
git pull origin claude/abrir-powershell-fofq4h
```

### Paso 2: Instalar Dependencias

```bash
pip install python-dotenv requests
```

### Paso 3: Verificar tu .env

Asegúrate de que tu `.env` local contiene:
- `NOTION_API_KEY=ntn_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx` (tu token real)
- `NOTION_DB_CLOPAS=xxxxxxxxxxxxxxxxxxxxxxxxxxxxx` (tu DB ID real)

**⚠️ IMPORTANTE:** Nunca commitear el `.env` a Git (ya está en `.gitignore`)

### Paso 4: Ejecutar el Script

```bash
python3 scripts/configurar_clopas.py
```

**Esperado:** Verás mensajes como:
```
🚀 Configurando CLOPAS en Notion...
   Base de datos: e95803c0833045848ac4dc6fa7509bc0

1️⃣ Creando propiedad 'Tipo'...
✅ Propiedad 'Tipo' creada
```

Si todo funciona, al final dirá:
```
✅ CLOPAS Configurada Correctamente
🎉 ¡CLOPAS está lista para usar!
```

### Paso 5: Verificar en Notion

1. Abre Notion
2. Ve a tu workspace "biblioteca-dga"
3. Abre la BD "CLOPAS"
4. Verifica que aparecen estas propiedades:
   - ✅ Tipo
   - ✅ Proyecto
   - ✅ Categoría
   - ✅ Descripción
   - ✅ Solución
   - ✅ Código
   - ✅ Fecha
   - ✅ Estado
   - ✅ Prioridad
   - ✅ Autor
   - ✅ Impacto
   - ✅ Tags
   - ✅ Enlace GitHub

---

## ✅ Usa CLOPAS

Una vez configurada, puedes:

### Crear un Error
```python
from scripts.gestor_clopas import GestorCLOPAS

gestor = GestorCLOPAS()
gestor.crear_registro_error(
    titulo="Bug en login",
    proyecto="app-movil",
    descripcion="Email no valida correctamente",
    prioridad="Alta"
)
```

### Crear una Corrección
```python
gestor.crear_registro_correccion(
    titulo="Corregir validación de email",
    proyecto="biblioteca-dga",
    categoria="Código",
    descripcion="Regex más permisiva",
    solucion="RFC 5322",
    prioridad="Alta"
)
```

### Listar Errores
```python
errores = gestor.listar_errores(proyecto="biblioteca-dga")
for error in errores:
    print(f"- {error['title']}")
```

---

## 🔄 Sincronización con tu Laptop

Una vez CLOPAS esté configurada en tu PC:

1. **Backup de PC:**
   ```bash
   bash scripts/backup_completo.sh
   ```
   Guarda el archivo `backup_*.tar.gz` generado

2. **En tu Laptop:**
   ```bash
   # Clonar repo
   git clone https://github.com/Office-Studio-Jj/biblioteca-dga.git
   cd biblioteca-dga
   
   # Restaurar backup
   bash scripts/restaurar_backup.sh /ruta/a/backup_*.tar.gz
   ```

---

## 📝 Próximos Pasos

1. ✅ Ejecutar `configurar_clopas.py` desde tu PC
2. ✅ Verificar CLOPAS en Notion
3. ✅ Crear tu primer registro de prueba
4. ✅ Sincronizar con tu Laptop
5. ✅ Empezar a usar CLOPAS para todos los cambios

---

## 🆘 Problemas?

**Error: ModuleNotFoundError: No module named 'dotenv'**
```bash
pip install python-dotenv requests
```

**Error: NOTION_API_KEY no configurada**
- Verifica que tu `.env` existe en el directorio raíz
- Contiene: `NOTION_API_KEY=ntn_...`
- Contiene: `NOTION_DB_CLOPAS=e958...`

**Error: 403 Forbidden en Notion**
- Verifica que el token de Notion es correcto
- Verifica que la BD de CLOPAS existe en Notion
- Verifica que tienes permisos en esa BD

---

**Creado:** 24 de septiembre de 2026  
**Estado:** Listo para ejecutar en PC ✅
