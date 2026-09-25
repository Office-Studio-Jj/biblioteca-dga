# Cambio de Claves de API - Protocolo de Seguridad

**Fecha de este protocolo:** 24 de septiembre de 2026  
**Criticidad:** ALTA - Las claves anteriores fueron expuestas en comunicaciones de WhatsApp y chat

---

## 1. Generar nuevas claves en los servicios

### 1.1 Anthropic (Claude API)
1. Ir a: https://console.anthropic.com/api/keys
2. Crear una clave nueva
3. **Copiar la clave completa** (empieza con `sk-ant-api03-`)
4. Borrar la clave anterior que comienza con `sk-ant-api03-rrr0...`
5. Guardar la clave en lugar seguro

### 1.2 Google Gemini API
1. Ir a: https://aistudio.google.com/apikey
2. Crear una clave nueva
3. **Copiar la clave completa** (empieza con `AIzaSy`)
4. Borrar la clave anterior que comienza con `AIzaSyBeK...`
5. Guardar la clave en lugar seguro

### 1.3 Notion Integration Secret
1. Ir a: https://notion.so/profile/integrations
2. Seleccionar la integración de Biblioteca DGA
3. Hacer clic en "Refresh" del **Internal Integration Secret**
4. **Copiar el nuevo token** (empieza con `secret_`)
5. Guardar el token en lugar seguro

---

## 2. Actualizar Railway (PRODUCCIÓN)

**IMPORTANTE:** Las claves en Railway están mal formateadas. Tienen saltos de línea, símbolos `>`, comas y valores duplicados.

### Pasos:
1. Ir a: https://railway.app → Dashboard → Biblioteca DGA → Variables
2. Para cada variable (`GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `NOTION_API_KEY`):
   - Borrar **TODO EL CONTENIDO ANTERIOR**
   - Pegar **SOLO** la clave nueva
   - **Sin espacios, sin símbolos, sin saltos de línea**
   - Ejemplo correcto:
     ```
     AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
     ```
   - Ejemplo **INCORRECTO** (lo que había antes):
     ```
     AIzaSyBeK...
     > AIzaSyBeK...
     ,
     ```

3. Guardar los cambios
4. Railway auto-desplegará los cambios

---

## 3. Actualizar archivo `.env` local

### En la laptop (desarrollo):
```bash
cd /home/user/biblioteca-dga
cp .env.example .env
```

Luego editar `.env` y rellenar con las nuevas claves:
```
GEMINI_API_KEY=AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
ANTHROPIC_API_KEY=sk-ant-api03-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
NOTION_API_KEY=secret_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

### En esta PC (desarrollo remoto):
Mismo procedimiento que en la laptop.

---

## 4. Verificar funcionamiento

Después de actualizar Railway y el `.env` local, verificar que todo funcione:

```bash
# En la laptop o PC
python sub_agentes/clasificador_merceologico_auto.py --test
python gemini_prefiltro.py --test
python notebooklm_skill/scripts/ask_gemini.py --test
```

En Railway, ir al "Deploy Logs" y buscar que no haya errores de autenticación.

---

## 5. Auditoría y limpieza

- [ ] Borrar la foto del teléfono donde aparecen las claves
- [ ] Borrar los mensajes de WhatsApp donde se pasaron las claves
- [ ] Borrar el chat de esta sesión donde aparecen las claves
- [ ] Verificar en git que no hay commits con claves expuestas:
  ```bash
  git log -p | grep -i "api_key\|api.key" | head
  ```
  Si hay, contactar a administrador de seguridad de GitHub

---

## 6. Protocolo de no-exposición futuro

1. **NUNCA** enviar claves por:
   - WhatsApp
   - Chat de Slack
   - Telegram
   - Correos normales
   - Screenshots

2. **SIEMPRE** usar:
   - Gestor de claves (1Password, LastPass, etc.)
   - Variables de entorno
   - Secrets de CI/CD (GitHub Actions, Railway)
   - Sesiones seguras con encriptación E2E

3. **Rotar claves** cada 3 meses o si hay sospecha de exposición

---

## 7. Contacto en caso de problemas

- Errores de autenticación en Railway → Revisar variables en dashboard
- Errores en desarrollo local → Revisar archivo `.env`
- Claves expuestas nuevamente → Contactar al administrador de seguridad inmediatamente

---

**Este documento debe guardarse en lugar seguro y compartirse solo con personal autorizado.**
