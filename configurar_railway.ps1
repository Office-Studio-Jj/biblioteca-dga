# Actualiza ANTHROPIC_API_KEY (y NOTION_DB_CLOPAS) en Railway tomando los valores del .env local.
# Uso (PowerShell, dentro de la carpeta biblioteca-dga):  .\configurar_railway.ps1
# La clave nunca se muestra en pantalla. Railway redespliega solo al cambiar la variable.

Write-Host "=== Actualizar variables en Railway ===" -ForegroundColor Cyan

if (-not (Test-Path .env)) {
    Write-Host "ERROR: no hay archivo .env en esta carpeta." -ForegroundColor Red
    exit 1
}

function Leer-Env($nombre) {
    $linea = Get-Content .env | Where-Object { $_ -match "^\s*$nombre\s*=" } | Select-Object -First 1
    if (-not $linea) { return "" }
    return ($linea -replace "^\s*$nombre\s*=\s*", "").Trim().Trim('"').Trim("'")
}

$clave = Leer-Env "ANTHROPIC_API_KEY"
$clopas = Leer-Env "NOTION_DB_CLOPAS"
if ($clave.Length -lt 50 -or -not $clave.StartsWith("sk-ant-")) {
    Write-Host "ERROR: ANTHROPIC_API_KEY del .env no parece valida." -ForegroundColor Red
    exit 1
}
Write-Host ("OK: clave leida del .env (" + $clave.Length + " caracteres)") -ForegroundColor Green

Write-Host "[1/4] Verificando Railway CLI..." -ForegroundColor Yellow
if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        npm install -g @railway/cli
    } else {
        Write-Host "No hay Railway CLI ni Node.js (npm)." -ForegroundColor Red
        Write-Host "Opcion manual: railway.com > proyecto biblioteca-dga > servicio > Variables >"
        Write-Host "ANTHROPIC_API_KEY > pegar el valor de ANTHROPIC_API_KEY del .env (sin comillas ni espacios)."
        exit 1
    }
}

Write-Host "[2/4] Iniciando sesion (se abre el navegador)..." -ForegroundColor Yellow
railway login
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: no se pudo iniciar sesion." -ForegroundColor Red; exit 1 }

Write-Host "[3/4] Vinculando el proyecto (elige biblioteca-dga y su servicio)..." -ForegroundColor Yellow
railway link
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: no se pudo vincular el proyecto." -ForegroundColor Red; exit 1 }

Write-Host "[4/4] Guardando variables..." -ForegroundColor Yellow
railway variables --set "ANTHROPIC_API_KEY=$clave" | Out-Null
if ($clopas) { railway variables --set "NOTION_DB_CLOPAS=$clopas" | Out-Null }
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: no se pudieron guardar las variables." -ForegroundColor Red; exit 1 }

Write-Host "=== Listo. Railway redespliega en 2-3 minutos. ===" -ForegroundColor Green
