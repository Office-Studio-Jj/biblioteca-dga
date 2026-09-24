# Paso 7: Auditoría y Limpieza de Seguridad - Instrucciones Específicas

**Fecha:** 24 de septiembre de 2026  
**Estado:** En progreso

---

## ✅ Completado (Automatizado)

- ✅ Git history: LIMPIO (sin claves reales)
- ✅ Archivos Python: Sin claves hardcodeadas
- ✅ `.env` local: Protegido en `.gitignore`
- ✅ `.env.example`: Solo contiene placeholders (XXX)
- ✅ Railway: Actualizado con claves nuevas
- ✅ Desarrollo local: `.env` con claves nuevas

---

## ❌ Por Completar (Manual)

### **Paso 7.1: Borrar foto del teléfono**

**¿Qué fue?** 
- Captura de pantalla que mostraba las claves de Gemini, Anthropic y Notion en el VS Code/terminal

**¿Cómo borrarlo?**

**En iPhone:**
1. Abre la app "Fotos"
2. Ve a "Recientes"
3. Busca la foto con la ventana de código/terminal
4. Toca la foto → "Eliminar" → "Eliminar Foto"
5. Ve a "Álbumes" → "Eliminadas Recientemente" → "Editar" → "Eliminar todo"

**En Android:**
1. Abre Google Fotos
2. Busca la foto (buscar por fecha reciente)
3. Toca la foto → 3 puntos (⋮) → "Eliminar"
4. Ve a "Papelera" → "Vaciar papelera"

**En Windows:**
1. Abre "Galería" o "Fotos"
2. Busca la imagen
3. Clic derecho → "Eliminar" → "Eliminar de forma permanente"

---

### **Paso 7.2: Borrar mensajes de WhatsApp**

**¿Qué fue?**
- Conversación en WhatsApp donde pasaste las claves (texto copiado-pegado)

**¿Cómo borrarlo?**

**En iPhone:**
1. Abre WhatsApp
2. Busca el chat donde enviaste las claves
3. Desliza sobre el chat → "Más" (⋯) → "Eliminar chat"
   - O: Mantén presionado el chat → "Eliminar" → "Eliminar chat y multimedia"

**En Android:**
1. Abre WhatsApp
2. Mantén presionado el chat
3. Toca 🗑️ (basura)

**Mejor: Elimina solo los mensajes:**
1. Abre el chat
2. Mantén presionado el mensaje con la clave
3. Toca 🗑️ (basura) → "Eliminar para mí"
   - Nota: Si lo enviaste a otra persona, también pídele que lo elimine de su lado

---

### **Paso 7.3: Borrar este chat de Claude**

**¿Qué es?**
- Esta conversación actual donde mostramos las claves

**¿Cómo borrarlo?**

**En claude.ai (Web):**
1. Ve a la lista de conversaciones a la izquierda
2. Busca "cambiar las claves" o la fecha de hoy
3. Hover sobre la conversación → clic en los 3 puntos (⋮)
4. Selecciona "Eliminar" o "Archivar"

**En Claude Desktop App:**
1. Abre el menú de conversaciones (izquierda)
2. Busca esta conversación
3. Clic derecho → "Eliminar"

**Alternativa: Archivar en lugar de eliminar**
- Si prefieres mantener referencia, puedes "Archivar" en lugar de eliminar
- Esto la oculta pero se puede recuperar si la necesitas

---

## ✅ Checklist Final

- [ ] Foto del teléfono: ELIMINADA
- [ ] Mensajes WhatsApp: ELIMINADOS
- [ ] Chat de Claude: ELIMINADO o ARCHIVADO
- [ ] Git history: LIMPIO (✅ ya verificado)

---

## 🔒 Confirmación

Cuando hayas completado los 3 pasos manuales (foto, WhatsApp, Claude), **dile a Claude:**

```
Paso 7 completado, seguridad limpia
```

Entonces marcaremos como finalizado el proceso completo de cambio de claves. 🎉

---

## ⚠️ Importante

- **Nunca más** envíes claves por WhatsApp, SMS, o chat no encriptado
- **Usa** un gestor de claves (1Password, LastPass, Bitwarden)
- **Rota** claves cada 3 meses
- **Si sospechas** otra exposición, regenera claves inmediatamente

---

**Documento creado el:** 24 de septiembre de 2026  
**Generado por:** Claude Haiku 4.5
