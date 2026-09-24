# Script para configurar CLOPAS automáticamente en Windows PowerShell
# Uso: .\ejecutar_clopas.ps1
# Requisito: Debe existir un archivo .env en el directorio actual

Write-Host "🚀 Iniciando configuración de CLOPAS..." -ForegroundColor Cyan
Write-Host "════════════════════════════════════════" -ForegroundColor Cyan

# 1. Verificar Python
Write-Host "`n1️⃣ Verificando Python..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ $pythonVersion encontrado" -ForegroundColor Green
} catch {
    Write-Host "❌ Python no encontrado. Instálalo desde python.org" -ForegroundColor Red
    exit 1
}

# 2. Verificar que .env existe
Write-Host "`n2️⃣ Verificando archivo .env..." -ForegroundColor Yellow
if (-not (Test-Path .env)) {
    Write-Host "`n❌ Archivo .env no encontrado" -ForegroundColor Red
    Write-Host "`n📋 Solución:" -ForegroundColor Yellow
    Write-Host "  1. Copia tu .env desde tu PC a esta carpeta"
    Write-Host "  2. O lee la guía: docs/EJECUTAR_CLOPAS_LOCALMENTE.md"
    Write-Host ""
    exit 1
}
Write-Host "✅ Archivo .env encontrado" -ForegroundColor Green

# 3. Verificar contenido del .env
Write-Host "`n3️⃣ Verificando credenciales en .env:" -ForegroundColor Yellow
Write-Host "────────────────────────────────────────"
cat .env
Write-Host "────────────────────────────────────────"

# 4. Ejecutar configuración
Write-Host "`n4️⃣ Ejecutando configuración de CLOPAS en Notion..." -ForegroundColor Yellow
Write-Host "⏳ Esto puede tomar unos segundos..." -ForegroundColor Cyan

try {
    python scripts/configurar_clopas.py
    Write-Host "`n✅ ¡Configuración completada!" -ForegroundColor Green
} catch {
    Write-Host "`n❌ Error al ejecutar configuración:" -ForegroundColor Red
    Write-Host $_.Exception.Message
    exit 1
}

Write-Host "`n════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "🎉 ¡CLOPAS está lista para usar!" -ForegroundColor Green
Write-Host "════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "`n📋 Próximos pasos:" -ForegroundColor Cyan
Write-Host "  1. Abre Notion y verifica que CLOPAS tiene 13 propiedades ✅"
Write-Host "  2. Crea tu primer registro de prueba"
Write-Host "  3. Usa: python scripts/gestor_clopas.py para agregar cambios"
Write-Host "`n💡 Documentación: docs/BIBLIOTECA_ERRORES_CLOPAS.md"
Write-Host "📖 Guía completa: docs/EJECUTAR_CLOPAS_LOCALMENTE.md"
Write-Host ""
