# Configura CLOPAS en Notion desde Windows PowerShell.
# Uso: .\ejecutar_clopas.ps1  (requiere .env en esta carpeta)
# Archivo en ASCII puro: Windows PowerShell 5.1 no interpreta UTF-8 sin BOM.

Write-Host "=== Configuracion de CLOPAS ===" -ForegroundColor Cyan

Write-Host "[1/3] Verificando Python..." -ForegroundColor Yellow
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "ERROR: Python no encontrado. Instalar desde python.org" -ForegroundColor Red
    exit 1
}
python --version

Write-Host "[2/3] Verificando archivo .env..." -ForegroundColor Yellow
if (-not (Test-Path .env)) {
    Write-Host "ERROR: falta el archivo .env en esta carpeta." -ForegroundColor Red
    Write-Host "Ver docs/EJECUTAR_CLOPAS_LOCALMENTE.md"
    exit 1
}
Write-Host "OK: .env encontrado" -ForegroundColor Green

Write-Host "[3/3] Configurando CLOPAS en Notion..." -ForegroundColor Yellow
$env:PYTHONUTF8 = "1"
python -m pip install --quiet python-dotenv requests
python scripts/configurar_clopas.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: la configuracion fallo. Revisar mensajes arriba." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "=== Listo. Abrir CLOPAS en Notion y verificar las propiedades ===" -ForegroundColor Green
