#!/bin/bash

# Restaurar Backup - Biblioteca DGA
# Uso: ./scripts/restaurar_backup.sh <archivo_backup> <archivo_env> <archivo_db>

set -e

if [ $# -lt 1 ]; then
    echo "❌ Uso: $0 <archivo_backup.tar.gz> [archivo_env.tar.gz] [archivo_db.db.gz]"
    echo ""
    echo "Ejemplo:"
    echo "  $0 backup_2026-09-24_10-30-45.tar.gz env_2026-09-24_10-30-45.tar.gz database_2026-09-24_10-30-45.db.gz"
    exit 1
fi

BACKUP_FILE="$1"
ENV_FILE="${2:-}"
DB_FILE="${3:-}"

echo "🔄 Iniciando Restauración de Backup..."
echo ""

# 1. Verificar que el archivo de backup existe
if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Error: Archivo de backup no encontrado: $BACKUP_FILE"
    exit 1
fi

echo "✅ Archivo de backup encontrado"

# 2. Crear directorio temporal
RESTORE_DIR=$(mktemp -d)
echo "📂 Directorio temporal: $RESTORE_DIR"

# 3. Extraer backup
echo ""
echo "📦 Extrayendo backup..."
tar -xzf "$BACKUP_FILE" -C "$RESTORE_DIR"
echo "   ✅ Backup extraído"

# 4. Copiar archivos
echo ""
echo "📋 Copiando archivos al directorio del proyecto..."
cp -r "$RESTORE_DIR/biblioteca-dga"/* /home/user/biblioteca-dga/ || true
echo "   ✅ Archivos copiados"

# 5. Restaurar .env si se proporciona
if [ -n "$ENV_FILE" ] && [ -f "$ENV_FILE" ]; then
    echo ""
    echo "📝 Restaurando archivo .env..."
    tar -xzf "$ENV_FILE" -C /home/user/biblioteca-dga
    chmod 600 /home/user/biblioteca-dga/.env
    echo "   ✅ Archivo .env restaurado"
    echo "   🔒 Permisos restrictivos establecidos"
else
    echo ""
    echo "⚠️ Archivo .env no proporcionado o no encontrado"
    echo "   Crear manualmente: /home/user/biblioteca-dga/.env"
fi

# 6. Restaurar base de datos si se proporciona
if [ -n "$DB_FILE" ] && [ -f "$DB_FILE" ]; then
    echo ""
    echo "🗄️ Restaurando base de datos..."
    mkdir -p /home/user/biblioteca-dga/capa1_sqlite
    gunzip -c "$DB_FILE" > /home/user/biblioteca-dga/capa1_sqlite/arancel_rd.db
    echo "   ✅ Base de datos restaurada"
else
    echo ""
    echo "ℹ️ Base de datos no proporcionada"
    echo "   Asegúrate de que exista: capa1_sqlite/arancel_rd.db"
fi

# 7. Limpiar directorio temporal
rm -rf "$RESTORE_DIR"

# 8. Verificación final
echo ""
echo "🔍 Verificación final..."
cd /home/user/biblioteca-dga

if [ -f ".env" ]; then
    echo "   ✅ Archivo .env presente"
else
    echo "   ⚠️ Archivo .env faltante"
fi

if [ -f "capa1_sqlite/arancel_rd.db" ]; then
    SIZE=$(du -h capa1_sqlite/arancel_rd.db | cut -f1)
    echo "   ✅ Base de datos presente ($SIZE)"
else
    echo "   ⚠️ Base de datos faltante"
fi

if [ -d ".git" ]; then
    echo "   ✅ Repositorio git presente"
else
    echo "   ⚠️ Repositorio git faltante"
fi

# 9. Información de próximos pasos
echo ""
echo "✅ Restauración Completada"
echo ""
echo "📋 Próximos pasos:"
echo "   1. Verifica el archivo .env: nano /home/user/biblioteca-dga/.env"
echo "   2. Instala dependencias: pip install -r requirements.txt (si existe)"
echo "   3. Sincroniza con git: git pull origin main"
echo "   4. ¡Listo para trabajar!"
