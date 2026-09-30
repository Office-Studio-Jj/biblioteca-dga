# Migra railway.toml (Config as Code, deja de funcionar el 01-12-2026) a Infrastructure as Code
# (.railway/railway.ts) con la herramienta oficial de Railway. No publica nada: deja el archivo
# nuevo copiado en el portapapeles para pegarselo a Claude, que lo revisa antes de subirlo.
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

Write-Host "[2/3] Ejecutando railway config migrate..." -ForegroundColor Yellow
railway config migrate
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: la migracion fallo. Mandale a Claude una captura de esta ventana." -ForegroundColor Red
    exit 1
}

Write-Host "[3/3] Buscando el archivo nuevo..." -ForegroundColor Yellow
$nuevos = Get-ChildItem -Path .railway -Recurse -File -ErrorAction SilentlyContinue
if (-not $nuevos) {
    Write-Host "No se creo la carpeta .railway. Mandale a Claude una captura de esta ventana." -ForegroundColor Red
    exit 1
}
$texto = ""
foreach ($f in $nuevos) {
    $ruta = $f.FullName.Substring((Get-Location).Path.Length + 1)
    $texto += "===== " + $ruta + " =====`r`n" + (Get-Content $f.FullName -Raw) + "`r`n"
}
if (Test-Path railway.toml) { $texto += "(railway.toml sigue existiendo)`r`n" } else { $texto += "(railway.toml fue eliminado por la migracion)`r`n" }
Set-Clipboard -Value $texto
Write-Host $texto
Write-Host "=== Listo. El contenido ya esta copiado: pegalo en el chat de Claude (Ctrl+V). ===" -ForegroundColor Green
Write-Host "No hagas git commit ni git push: Claude lo revisa y lo publica." -ForegroundColor Green
