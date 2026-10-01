# Migra railway.toml (Config as Code, deja de funcionar el 01-12-2026) a Infrastructure as Code
# (.railway/railway.ts) con la herramienta oficial de Railway. Solo hace la vista previa: deja
# en el portapapeles el railway.ts propuesto y los volumenes, para que Claude lo revise.
# Uso (PowerShell, dentro de la carpeta biblioteca-dga):  .\migrar_railway.ps1

Write-Host "=== Migrar configuracion de Railway ===" -ForegroundColor Cyan

if (-not (Test-Path railway.toml)) {
    Write-Host "ERROR: no encuentro railway.toml. Ejecuta el script dentro de la carpeta biblioteca-dga." -ForegroundColor Red
    exit 1
}
if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: no hay Railway CLI. Ejecuta primero .\configurar_railway.ps1" -ForegroundColor Red
    exit 1
}

Write-Host "[1/3] Guardando copia de railway.toml..." -ForegroundColor Yellow
Copy-Item railway.toml railway.toml.respaldo -Force
Write-Host "OK: copia en railway.toml.respaldo" -ForegroundColor Green

Write-Host "[2/3] Vista previa: railway config migrate (no cambia nada)..." -ForegroundColor Yellow
# Sin --apply la CLI solo muestra el railway.ts propuesto; no escribe archivos ni toca Railway.
$vista = railway config migrate 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {
    Write-Host $vista
    Write-Host "ERROR: la vista previa fallo. Mandale a Claude una captura de esta ventana." -ForegroundColor Red
    exit 1
}

Write-Host "[3/3] Leyendo el volumen y la configuracion actual del servicio..." -ForegroundColor Yellow
$volumen = railway volume list 2>&1 | Out-String

$texto = "===== VISTA PREVIA railway.ts =====`r`n" + $vista + "`r`n===== VOLUMENES =====`r`n" + $volumen +
         "`r`n===== railway.toml actual =====`r`n" + (Get-Content railway.toml -Raw)
Set-Clipboard -Value $texto
Write-Host $texto
Write-Host "=== Listo. El contenido ya esta copiado: pegalo en el chat de Claude (Ctrl+V). ===" -ForegroundColor Green
Write-Host "NO ejecutes 'railway config migrate --apply' hasta que Claude confirme que el volumen /data queda protegido." -ForegroundColor Green
