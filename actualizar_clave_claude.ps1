# Pega la clave REAL de Anthropic, la prueba y la guarda en el .env y en Railway.
# Uso (PowerShell, dentro de la carpeta biblioteca-dga):  .\actualizar_clave_claude.ps1
# La clave no se muestra en pantalla ni queda en el historial.

Write-Host "=== Actualizar clave de Claude (Anthropic) ===" -ForegroundColor Cyan
Write-Host "1. Abre console.anthropic.com > API Keys > Create Key"
Write-Host "2. Pulsa el boton Copy (NO copies la clave de la lista: ahi sale con puntos)"
Write-Host "3. Vuelve aqui, pega con clic derecho (o Ctrl+V) y pulsa Enter"
Write-Host ""

$segura = Read-Host "Pega la clave (no se vera al pegar)" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($segura)
$clave = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr).Trim().Trim('"').Trim("'")
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)

if (-not $clave.StartsWith("sk-ant-") -or $clave.Length -lt 50) {
    Write-Host "ERROR: eso no parece una clave de Anthropic (debe empezar por sk-ant-)." -ForegroundColor Red
    exit 1
}
if ($clave -match '[^\x21-\x7E]') {
    Write-Host "ERROR: la clave esta ENMASCARADA (tiene puntos). Usa el boton Copy al crearla." -ForegroundColor Red
    exit 1
}
Write-Host ("OK: clave de " + $clave.Length + " caracteres, termina en ..." + $clave.Substring($clave.Length - 4)) -ForegroundColor Green

Write-Host "[1/3] Probando la clave con Anthropic..." -ForegroundColor Yellow
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
try {
    Invoke-RestMethod -Uri "https://api.anthropic.com/v1/models?limit=1" -Headers @{
        "x-api-key" = $clave; "anthropic-version" = "2023-06-01" } | Out-Null
    Write-Host "OK: Anthropic acepta la clave." -ForegroundColor Green
} catch {
    Write-Host ("ERROR: Anthropic rechaza la clave (" + $_.Exception.Message + "). No se guardo nada.") -ForegroundColor Red
    exit 1
}

Write-Host "[2/3] Guardando en el .env..." -ForegroundColor Yellow
$ruta = Join-Path (Get-Location) ".env"
$utf8 = New-Object System.Text.UTF8Encoding($false)
$lineas = @()
if (Test-Path $ruta) { $lineas = [IO.File]::ReadAllLines($ruta, $utf8) }
$nueva = "ANTHROPIC_API_KEY=" + $clave
$hay = $false
$lineas = $lineas | ForEach-Object {
    if ($_ -match '^\s*ANTHROPIC_API_KEY\s*=') { $hay = $true; $nueva } else { $_ }
}
if (-not $hay) { $lineas = @($lineas) + $nueva }
[IO.File]::WriteAllLines($ruta, [string[]]$lineas, $utf8)
Write-Host "OK: .env actualizado." -ForegroundColor Green

Write-Host "[3/3] Guardando en Railway..." -ForegroundColor Yellow
if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
    Write-Host "No hay Railway CLI. Ejecuta primero .\configurar_railway.ps1 o pega la clave en railway.com > Variables." -ForegroundColor Red
    exit 1
}
railway status 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Vinculando el proyecto (elige invigorating-optimism > production > biblioteca-dga)..."
    railway link
    if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: no se pudo vincular." -ForegroundColor Red; exit 1 }
}
railway variables --set "ANTHROPIC_API_KEY=$clave" | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Railway no guardo la variable. Prueba: railway login y vuelve a ejecutar." -ForegroundColor Red
    exit 1
}
$clave = $null
Write-Host "=== Listo. Railway redespliega en 2-3 minutos. Avisale a Claude para verificar. ===" -ForegroundColor Green
