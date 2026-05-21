$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$logs = Join-Path $root "logs"

New-Item -ItemType Directory -Force -Path $logs | Out-Null

function Test-PortInUse {
  param([int]$Port)
  $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  return $null -ne $connection
}

if (!(Test-Path (Join-Path $backend ".venv"))) {
  Push-Location $backend
  python -m venv .venv
  .\.venv\Scripts\python -m pip install --upgrade pip
  Pop-Location
}

Push-Location $backend
.\.venv\Scripts\pip install -r requirements.txt
Pop-Location

if (!(Test-Path (Join-Path $backend ".env"))) {
  Copy-Item (Join-Path $backend ".env.example") (Join-Path $backend ".env")
}

if (!(Test-Path (Join-Path $frontend "node_modules"))) {
  Push-Location $frontend
  npm install
  Pop-Location
}

if (Test-PortInUse 8000) {
  Write-Host "Backend is already running on http://127.0.0.1:8000"
} else {
  Write-Host "Starting backend on http://127.0.0.1:8000"
  Start-Process -FilePath (Join-Path $backend ".venv\Scripts\python.exe") `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload") `
    -WorkingDirectory $backend `
    -RedirectStandardOutput (Join-Path $logs "backend.log") `
    -RedirectStandardError (Join-Path $logs "backend-error.log") `
    -WindowStyle Hidden
}

Start-Sleep -Seconds 2

if (Test-PortInUse 3000) {
  Write-Host "Frontend is already running on http://127.0.0.1:3000"
} else {
  Write-Host "Starting frontend on http://127.0.0.1:3000"
  Start-Process -FilePath "npm.cmd" `
    -ArgumentList @("run", "dev", "--", "--hostname", "127.0.0.1", "--port", "3000") `
    -WorkingDirectory $frontend `
    -RedirectStandardOutput (Join-Path $logs "frontend.log") `
    -RedirectStandardError (Join-Path $logs "frontend-error.log") `
    -WindowStyle Hidden
}

Write-Host "Open http://127.0.0.1:3000"
Write-Host "Logs are in $logs"
