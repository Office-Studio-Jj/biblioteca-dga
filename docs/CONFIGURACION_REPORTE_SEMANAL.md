# Configuración Reporte Semanal - Notion

**Fecha de configuración:** 24 de septiembre de 2026  
**Ejecuta:** Cada domingo a las 21:00 (9 PM)  
**Destino:** Notion (biblioteca-dga)  
**Nota:** NotebookLM completamente removido del pipeline

---

## 📋 Qué incluye el Reporte Semanal

✅ **Commits de la semana** - Todos los cambios en el código  
✅ **Logs de Railway** - Estado de deployments y errores  
✅ **Métricas de performance** - Información de la aplicación  
✅ **Info de Notion** - Datos de las pestañas de biblioteca-dga  
✅ **Investigaciones documentales** - Nuevas fuentes y análisis  
❌ **NotebookLM** - Eliminado por completo

---

## 🔧 Configuración Requerida

Agregar estas variables al `.env`:

```env
# Base de datos de Notion para reportes semanales
NOTION_DB_REPORTES=xxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Token de Railway (opcional, para logs)
RAILWAY_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

## 📊 Estructura del Reporte

Cada domingo a las 21:00 se crea una página en Notion con:

### Sección 1: Estadísticas
- Total de commits de la semana
- Número de deployments
- Errores detectados
- Cambios en el código

### Sección 2: Cambios de Código
- Lista de commits (hash, autor, mensaje, fecha)
- Ramas modificadas
- Archivos cambiados

### Sección 3: Deployments
- Estado de cada deployment
- Hora del deployment
- Changelog del release

### Sección 4: Investigaciones
- Nuevos documentos añadidos
- Actualizaciones en fichas merceológicas
- Cambios en la clasificación de aranceles
- Nuevas fuentes normativas

---

## 🚀 Ejecutar Manualmente

Si necesitas generar un reporte fuera del horario:

```bash
cd /home/user/biblioteca-dga
python3 scripts/reporte_semanal_notion.py
```

---

## 🔄 Desactivar NotebookLM

✅ **Ya hecho:** El pipeline NO incluye NotebookLM

Verificar que no hay referencias:
```bash
grep -r "notebooklm\|notebook" --include="*.py" /home/user/biblioteca-dga/
```

---

## 📅 Horario

- **Día:** Domingo
- **Hora:** 21:00 (9 PM)
- **Frecuencia:** Una vez por semana
- **Zona horaria:** Local (tu zona horaria)
- **Auto-expira:** Si Claude se desconecta, el cron se detiene (reagendar si es necesario)

---

## ⚙️ Ajustar Horario

Si quieres cambiar el horario del reporte:

```
Cron format: "M H DoM Mon DoW"
- M = minutos (0-59)
- H = hora (0-23)
- DoM = día del mes (1-31)
- Mon = mes (1-12)
- DoW = día de la semana (0=domingo, 1=lunes, ..., 6=sábado)

Ejemplos:
- Domingo 21:00: "0 21 * * 0"
- Jueves 18:00: "0 18 * * 4"
- Cada día 08:00: "0 8 * * *"
```

---

## 🔒 Seguridad

- ✅ `.env` protegido en `.gitignore`
- ✅ Tokens de Notion y Railway en variables de entorno
- ✅ Sin credenciales en el repositorio
- ✅ Script ejecutable solo desde este usuario

---

## 📞 Soporte

Si el reporte no se ejecuta:

1. Verificar que las variables de entorno están cargadas: `echo $NOTION_API_KEY`
2. Revisar que la conexión a Notion está activa
3. Confirmar que Railway token es válido (si se usa)
4. Revisar logs: `cat /home/user/biblioteca-dga/logs/reporte_semanal.log`

---

**Configuración completada:** ✅
