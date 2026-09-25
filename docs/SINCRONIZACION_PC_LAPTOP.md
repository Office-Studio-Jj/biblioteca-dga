# Sincronización PC y Laptop - Biblioteca DGA

**Objetivo:** Mantener ambas máquinas sincronizadas para trabajar indistintamente

---

## 📋 Tabla de Contenidos

1. [Setup Inicial](#setup-inicial)
2. [Backup y Restauración](#backup-y-restauración)
3. [Sincronización Diaria](#sincronización-diaria)
4. [Procedimientos de Emergencia](#procedimientos-de-emergencia)

---

## 🚀 Setup Inicial

### En la Laptop (Primera vez)

```bash
# 1. Clonar el repositorio
cd ~/Documentos  # o donde quieras
git clone https://github.com/Office-Studio-Jj/biblioteca-dga.git
cd biblioteca-dga

# 2. Crear archivo .env con tus credenciales
# (Pedir al PC: cat /home/user/biblioteca-dga/.env)
nano .env
# Pega las siguientes variables:
# GEMINI_API_KEY=...
# ANTHROPIC_API_KEY=...
# NOTION_API_KEY=...

# 3. Instalar dependencias (si es necesario)
pip install -r requirements.txt

# 4. Verificar que funciona
python3 -c "import os; print('✅ Setup completado')"
```

### En la PC (Ya configurada)

La PC ya tiene todo configurado. Solo necesita hacer backups.

---

## 📦 Backup y Restauración

### Crear Backup en la PC

```bash
cd /home/user/biblioteca-dga

# Opción 1: Script automático
bash scripts/backup_completo.sh

# Esto genera:
# - backups/backup_YYYY-MM-DD_HH-MM-SS.tar.gz
# - backups/env_YYYY-MM-DD_HH-MM-SS.tar.gz
# - backups/database_YYYY-MM-DD_HH-MM-SS.db.gz
```

### Transferir Backup a Laptop

**Opción A: Por USB/Drive**
```bash
# En PC:
cp -r /home/user/biblioteca-dga/backups ~/backup_biblioteca_dga

# Copiar a USB o compartir en Drive

# En Laptop:
cp -r ~/Descargas/backup_biblioteca_dga/backups ~/biblioteca-dga/
```

**Opción B: Por SSH (si está disponible)**
```bash
# En Laptop:
scp -r usuario@ip_pc:/home/user/biblioteca-dga/backups ~/biblioteca-dga/
```

**Opción C: Por GitHub Releases**
```bash
# En PC:
cd /home/user/biblioteca-dga/backups
zip -r backup_completo.zip backup_* env_* database_*

# Subir a GitHub Releases manualmente
# Descargar en Laptop desde GitHub
```

### Restaurar Backup en Laptop

```bash
cd ~/biblioteca-dga

# Script de restauración
bash scripts/restaurar_backup.sh \
  backups/backup_YYYY-MM-DD_HH-MM-SS.tar.gz \
  backups/env_YYYY-MM-DD_HH-MM-SS.tar.gz \
  backups/database_YYYY-MM-DD_HH-MM-SS.db.gz

# Verificar
git log --oneline | head -5
```

---

## 🔄 Sincronización Diaria

### Flujo de Trabajo Recomendado

#### Trabajar en PC

```bash
cd /home/user/biblioteca-dga

# 1. Hacer cambios en el código
# (editar archivos, etc.)

# 2. Commitar cambios
git add .
git commit -m "feat: descripción del cambio"

# 3. Hacer backup automático
bash scripts/backup_completo.sh

# 4. Pushear a GitHub
git push origin main
```

#### Trabajar en Laptop

```bash
cd ~/biblioteca-dga

# 1. Descargar cambios más recientes
git pull origin main

# 2. Hacer cambios en el código
# (editar archivos, etc.)

# 3. Commitar y pushear
git add .
git commit -m "feat: descripción del cambio"
git push origin main

# 4. Antes de terminar: hacer backup local
bash scripts/backup_completo.sh
```

### Sincronización de Base de Datos

```bash
# Si cambió la base de datos en la PC:
# 1. PC crea backup: bash scripts/backup_completo.sh
# 2. Laptop descarga el backup
# 3. Laptop restaura: bash scripts/restaurar_backup.sh backups/database_*.db.gz
```

---

## 🔒 Manejo de Credenciales

### Nunca versionear .env

```bash
# ✅ CORRECTO: .env en .gitignore (ya está)
git status  # No debe listar .env

# ❌ INCORRECTO: No hagas esto
git add .env
git commit -m "add env"  # NO
```

### Sincronizar .env entre máquinas

```bash
# PC: Hacer disponible el .env (SIN commitar)
# Opción 1: Por USB
cp /home/user/biblioteca-dga/.env ~/usb/.env.backup

# Opción 2: Enviar de forma segura
# (guardar en gestor de claves, 1Password, etc.)

# Laptop: Crear .env desde backup seguro
# (NO de GitHub, solo de fuente segura)
nano ~/.env
# Pega el contenido
cp ~/.env ~/biblioteca-dga/.env
chmod 600 ~/biblioteca-dga/.env
```

---

## 🆘 Procedimientos de Emergencia

### Si la Laptop está desincronizada

```bash
# OPCIÓN 1: Reset hard (perder cambios locales)
cd ~/biblioteca-dga
git reset --hard origin/main
git pull origin main

# OPCIÓN 2: Crear rama de recuperación
git stash  # Guardar cambios locales
git pull origin main
# Recuperar cambios: git stash pop
```

### Si se corrompe la base de datos

```bash
# Laptop: Restaurar desde backup más reciente
cd ~/biblioteca-dga
bash scripts/restaurar_backup.sh \
  backups/database_YYYY-MM-DD_HH-MM-SS.db.gz
```

### Si el .env se pierde

```bash
# PC a Laptop (OPCIÓN SEGURA SOLAMENTE)
# 1. Verificar que sea el archivo correcto
# 2. Transferir por: USB, Drive privado, o gestor de claves
# 3. NUNCA por email, chat, o repositorio público

# En Laptop:
cp ~/backup_seguro/.env ~/biblioteca-dga/.env
chmod 600 ~/biblioteca-dga/.env
```

---

## 📊 Checklist de Sincronización

Antes de cambiar de máquina, verifica:

- [ ] **PC**: Cambios commiteados y pusheados
- [ ] **PC**: Backup creado (bash scripts/backup_completo.sh)
- [ ] **Laptop**: Git pull completado
- [ ] **Laptop**: .env sincronizado
- [ ] **Laptop**: Base de datos sincronizada (si cambió)
- [ ] **Ambas**: Misma rama de trabajo (main o feature)

---

## 🕐 Horarios de Sincronización Recomendados

- **Mañana (PC)**: Revisar pull requests de Laptop
- **Mediodía (Laptop)**: Sincronizar con cambios de PC
- **Tarde (PC)**: Hacer cambios principales
- **Noche (Laptop)**: Revisar y hacer pequeños cambios
- **Domingo (Ambas)**: Backup completo + sincronización

---

## 🔗 Comandos Rápidos

```bash
# PC: Backup rápido
bash /home/user/biblioteca-dga/scripts/backup_completo.sh

# Laptop: Sincronizar
cd ~/biblioteca-dga && git pull origin main

# Ambas: Ver status
git status
git log --oneline | head -5

# PC: Ver últimos backups
ls -lh /home/user/biblioteca-dga/backups/

# Laptop: Restaurar backup
bash ~/biblioteca-dga/scripts/restaurar_backup.sh \
  ~/biblioteca-dga/backups/backup_*.tar.gz
```

---

## 📱 Backup en Cloud (Opcional)

Si quieres backup adicional en cloud:

```bash
# Google Drive, Dropbox, OneDrive, etc.
cp -r /home/user/biblioteca-dga/backups ~/Drive/

# O automático con:
rclone sync /home/user/biblioteca-dga/backups gdrive:biblioteca-dga/backups
```

---

## ✅ Verificación

Después de sincronizar, verifica:

```bash
# En Laptop:
git status          # Debe estar limpio
git log | head -1   # Mismos commits que PC
ls .env             # Debe existir
ls capa1_sqlite/    # Debe tener arancel_rd.db

# Si todo es ✅, ¡listo para trabajar!
```

---

**Última actualización:** 24 de septiembre de 2026  
**Estado:** ✅ Operativo en PC, Listo para Laptop
