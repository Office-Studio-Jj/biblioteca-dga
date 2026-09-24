#!/bin/bash

# Backup Completo - Biblioteca DGA
# Sincroniza entre PC y Laptop
# Uso: ./scripts/backup_completo.sh

set -e

PROJECT_DIR="/home/user/biblioteca-dga"
BACKUP_DIR="$PROJECT_DIR/backups"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_FILE="$BACKUP_DIR/backup_$TIMESTAMP.tar.gz"
BACKUP_ENV="$BACKUP_DIR/env_$TIMESTAMP.tar.gz"

echo "🔄 Iniciando Backup Completo..."
echo "📅 Timestamp: $TIMESTAMP"
echo ""

# 1. Crear directorio de backups
mkdir -p "$BACKUP_DIR"

# 2. Backup de archivo .env (credenciales)
echo "📝 Respaldando archivo .env..."
if [ -f "$PROJECT_DIR/.env" ]; then
    tar -czf "$BACKUP_ENV" -C "$PROJECT_DIR" .env 2>/dev/null
    echo "   ✅ Archivo .env respaldado"
    chmod 600 "$BACKUP_ENV"
    echo "   🔒 Permisos restrictivos establecidos"
else
    echo "   ⚠️ Archivo .env no encontrado"
fi

# 3. Backup del proyecto completo (excluyendo ciertos directorios)
echo ""
echo "📦 Respaldando proyecto completo..."
tar -czf "$BACKUP_FILE" \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.pytest_cache' \
    --exclude='node_modules' \
    --exclude='backups' \
    --exclude='.env' \
    -C "$PROJECT_DIR/.." biblioteca-dga

if [ -f "$BACKUP_FILE" ]; then
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "   ✅ Proyecto respaldado: $SIZE"
    chmod 600 "$BACKUP_FILE"
fi

# 4. Backup de base de datos SQLite
echo ""
echo "🗄️ Respaldando base de datos..."
if [ -f "$PROJECT_DIR/capa1_sqlite/arancel_rd.db" ]; then
    DB_BACKUP="$BACKUP_DIR/database_$TIMESTAMP.db.gz"
    gzip -c "$PROJECT_DIR/capa1_sqlite/arancel_rd.db" > "$DB_BACKUP"
    echo "   ✅ Base de datos respaldada"
else
    echo "   ⚠️ Base de datos no encontrada"
fi

# 5. Git commit automático
echo ""
echo "📋 Commiteando cambios a git..."
cd "$PROJECT_DIR"
if [ -n "$(git status --porcelain)" ]; then
    git add -A
    git commit -m "backup: snapshot automático $TIMESTAMP" || true
    echo "   ✅ Cambios commiteados"
else
    echo "   ℹ️ No hay cambios para commitar"
fi

# 6. Git push
echo ""
echo "🚀 Pusheando a GitHub..."
git push -u origin $(git rev-parse --abbrev-ref HEAD) || echo "   ⚠️ Push fallido (verificar conexión)"

# 7. Información de sincronización
echo ""
echo "📊 Resumen de Backups:"
echo "   Proyecto: $BACKUP_FILE"
echo "   Credenciales: $BACKUP_ENV"
if [ -f "$DB_BACKUP" ]; then
    echo "   Base de datos: $DB_BACKUP"
fi
echo ""
echo "🔄 Para sincronizar en otra máquina:"
echo "   1. Clone el repositorio:"
echo "      git clone https://github.com/Office-Studio-Jj/biblioteca-dga.git"
echo "   2. Restaure el .env:"
echo "      tar -xzf env_$TIMESTAMP.tar.gz"
echo "   3. Restaure la base de datos:"
echo "      gunzip -c database_$TIMESTAMP.db.gz > capa1_sqlite/arancel_rd.db"
echo ""
echo "✅ Backup Completo Finalizado"
