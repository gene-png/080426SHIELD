# SHIELD dev stack startup — brings up Docker, the full stack, seeds the demo
# accounts, and prints the web address + login credentials.
# Auto-run by .vscode/tasks.json on folder open; also runnable manually:
#   powershell -ExecutionPolicy Bypass -File scripts/dev-up.ps1

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

function Write-Step($m) { Write-Host "`n>> $m" -ForegroundColor Cyan }
function Test-DockerUp {
  docker info 1>$null 2>$null
  return ($LASTEXITCODE -eq 0)
}

Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host "  SHIELD by Kentro - starting the development stack" -ForegroundColor DarkCyan
Write-Host "============================================================" -ForegroundColor DarkCyan

# 1) Make sure the Docker daemon is running (launch Docker Desktop if needed).
if (-not (Test-DockerUp)) {
  Write-Step "Docker daemon not running - launching Docker Desktop..."
  $dd = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
  if (Test-Path $dd) { Start-Process $dd } else { Write-Host "  (Docker Desktop not found; start it manually)" -ForegroundColor Yellow }
  $waited = 0
  while (-not (Test-DockerUp) -and $waited -lt 180) {
    Start-Sleep -Seconds 5; $waited += 5
    Write-Host "  waiting for Docker to be ready... ${waited}s" -ForegroundColor DarkGray
  }
  if (-not (Test-DockerUp)) {
    Write-Host "Docker still not available. Start Docker Desktop, then re-run this task." -ForegroundColor Red
    exit 1
  }
}
Write-Host "Docker is running." -ForegroundColor Green

# 2) Build + start the full stack (first run can take a few minutes).
Write-Step "Building + starting containers (docker compose up -d --build)..."
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { Write-Host "docker compose up failed - see output above." -ForegroundColor Red; exit 1 }

# 3) Wait for the API to pass its health check.
Write-Step "Waiting for the API to become healthy..."
$apiOk = $false
for ($i = 0; $i -lt 60; $i++) {
  try {
    $r = Invoke-WebRequest -UseBasicParsing "http://localhost:8000/health" -TimeoutSec 3
    if ($r.StatusCode -eq 200) { $apiOk = $true; break }
  } catch {}
  Start-Sleep -Seconds 3
}
if (-not $apiOk) {
  Write-Host "API did not become healthy in time. Check: docker compose logs api" -ForegroundColor Red
  exit 1
}
Write-Host "API is healthy." -ForegroundColor Green

# 4) Seed the demo accounts (idempotent - safe to run every start).
Write-Step "Seeding demo accounts..."
docker compose exec -T api python scripts/seed_demo.py 1>$null 2>$null

# 5) Give the web app a moment (first build is slow; non-fatal if not ready yet).
Write-Step "Waiting for the web app..."
for ($i = 0; $i -lt 40; $i++) {
  try {
    $r = Invoke-WebRequest -UseBasicParsing "http://localhost:3000" -TimeoutSec 3
    if ($r.StatusCode -lt 500) { break }
  } catch {}
  Start-Sleep -Seconds 3
}

# 6) Print the banner with everything you need.
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  SHIELD by Kentro - the dev stack is UP" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Web app:     " -NoNewline; Write-Host "http://localhost:3000" -ForegroundColor White
Write-Host "  API + docs:  " -NoNewline; Write-Host "http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "  ADMIN  login: " -NoNewline -ForegroundColor Cyan
Write-Host "admin@kentro.example   /  DemoPass!2026" -ForegroundColor White
Write-Host "  CLIENT login: " -NoNewline -ForegroundColor Cyan
Write-Host "client@atlas.example   /  DemoPass!2026" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Stop the stack:   docker compose down" -ForegroundColor DarkGray
Write-Host "  Live AI (optional): put ANTHROPIC_API_KEY in .env, then re-run." -ForegroundColor DarkGray
Write-Host ""
