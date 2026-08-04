# SHIELD one-command demo reset (Sprint 6 T8; -Demo overlay added Sprint 9 T8).
#
# Tears the stack down INCLUDING volumes (a clean slate), rebuilds, waits for the
# full-matrix /ready probe (T3) to go all-green, reseeds the coherent Atlas demo
# story (4 services + a synthesized Risk Register, all released + downloadable),
# waits for the web app to answer, and prints the URLs + logins.
#
#   powershell -ExecutionPolicy Bypass -File scripts/demo-reset.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/demo-reset.ps1 -Demo
#
# -Demo overlays docker-compose.demo.yml on EVERY compose call, so the web
# service is the production Next.js standalone image (shield-web:demo) rather than
# the dev server — the same stack the hosted-demo CI job and the demo-journey e2e
# spec (SHIELD_DEMO_SMOKE=1) assert against. Plain invocation drives the base
# compose only.
#
# WARNING: `docker compose down -v` DELETES all demo data (Postgres, MinIO,
# Redis, Keycloak). That is the point of a reset — do not run this against
# anything you want to keep. Live AI is optional: put ANTHROPIC_API_KEY in .env.
param(
  [switch]$Demo
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

# Compose file selection. Base uses docker-compose.yml only — identical to the
# bare `docker compose` default (there is no override file in this repo); -Demo
# appends the hosted-demo override so every call targets the production web image.
$composeArgs = @("-f", "docker-compose.yml")
if ($Demo) { $composeArgs += @("-f", "docker-compose.demo.yml") }
function Invoke-Compose { docker compose @composeArgs @args }

# Resolve the web host port (WEB_PORT env > repo-root .env > 3000) so the web
# readiness wait probes the port the stack actually publishes on — the same
# resolution order e2e/helpers/baseUrl.ts uses. The api mapping is fixed at 8000.
$webPort = $env:WEB_PORT
if ((-not $webPort) -and (Test-Path ".env")) {
  $m = Select-String -Path ".env" -Pattern '^\s*WEB_PORT\s*=\s*(\d+)\s*$' | Select-Object -First 1
  if ($m) { $webPort = $m.Matches[0].Groups[1].Value }
}
if (-not $webPort) { $webPort = "3000" }

function Write-Step($m) { Write-Host "`n>> $m" -ForegroundColor Cyan }
function Test-DockerUp {
  docker info 1>$null 2>$null
  return ($LASTEXITCODE -eq 0)
}

$mode = "base compose (web: next dev)"
if ($Demo) { $mode = "hosted-demo overlay (web: production standalone build)" }

Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host "  SHIELD by Kentro - resetting the demo stack (down -v)" -ForegroundColor DarkCyan
Write-Host "  Mode: $mode" -ForegroundColor DarkCyan
Write-Host "============================================================" -ForegroundColor DarkCyan

if (-not (Test-DockerUp)) {
  Write-Host "Docker daemon not running. Start Docker Desktop, then re-run." -ForegroundColor Red
  exit 1
}

# 1) Full teardown INCLUDING volumes (clean slate).
Write-Step "Tearing down (docker compose down -v)..."
Invoke-Compose down -v
if ($LASTEXITCODE -ne 0) { Write-Host "docker compose down -v failed." -ForegroundColor Red; exit 1 }

# 2) Rebuild + start the full stack.
Write-Step "Building + starting containers (docker compose up -d --build)..."
Invoke-Compose up -d --build
if ($LASTEXITCODE -ne 0) { Write-Host "docker compose up failed - see output above." -ForegroundColor Red; exit 1 }

# 3) Wait for the FULL-MATRIX readiness probe to go all-green (T3): every
#    required dependency (db, redis, minio) must report ok.
Write-Step "Waiting for /ready (full dependency matrix) to be all-green..."
$ready = $false
$offenders = ""
for ($i = 0; $i -lt 80; $i++) {
  try {
    $r = Invoke-WebRequest -UseBasicParsing "http://localhost:8000/ready" -TimeoutSec 3
    $body = $r.Content | ConvertFrom-Json
    if ($body.ready -eq $true) { $ready = $true; break }
    $offenders = ($body.offenders -join ", ")
  } catch {}
  Start-Sleep -Seconds 3
}
if (-not $ready) {
  Write-Host "Stack not ready in time. Offenders: $offenders" -ForegroundColor Red
  Write-Host "---- docker compose logs api ----" -ForegroundColor Yellow
  Invoke-Compose logs api
  exit 1
}
Write-Host "All dependencies ready." -ForegroundColor Green

# 4) Seed the coherent Atlas demo (idempotent, but the DB is fresh here).
Write-Step "Seeding the Atlas demo story..."
Invoke-Compose exec -T api python scripts/seed_demo.py
if ($LASTEXITCODE -ne 0) { Write-Host "Seed failed - see output above." -ForegroundColor Red; exit 1 }

# 5) Wait for the web app to answer — FAIL LOUDLY on timeout (Sprint 9 T8, Codex
#    finding): the old poll gave up after 120s and printed the success banner
#    anyway, so a failed prod-image build looked like a clean reset until
#    Playwright died opaquely. A non-zero exit + a web log dump surfaces it here.
Write-Step "Waiting for the web app on http://localhost:$webPort ..."
$webReady = $false
for ($i = 0; $i -lt 40; $i++) {
  try {
    $r = Invoke-WebRequest -UseBasicParsing "http://localhost:$webPort" -TimeoutSec 3
    if ($r.StatusCode -lt 500) { $webReady = $true; break }
  } catch {}
  Start-Sleep -Seconds 3
}
if (-not $webReady) {
  Write-Host "Web app never became reachable on http://localhost:$webPort within 120s." -ForegroundColor Red
  Write-Host "A failed web build/start would otherwise masquerade as a successful reset." -ForegroundColor Yellow
  Write-Host "---- docker compose logs web ----" -ForegroundColor Yellow
  Invoke-Compose logs web
  exit 1
}
Write-Host "Web app reachable." -ForegroundColor Green

# 6) Print the banner.
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  SHIELD by Kentro - demo reset complete" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Web app:     " -NoNewline; Write-Host "http://localhost:$webPort" -ForegroundColor White
Write-Host "  API + docs:  " -NoNewline; Write-Host "http://localhost:8000/docs" -ForegroundColor White
Write-Host "  Readiness:   " -NoNewline; Write-Host "http://localhost:8000/ready" -ForegroundColor White
Write-Host "  MailHog:     " -NoNewline; Write-Host "http://localhost:8025" -ForegroundColor White
Write-Host ""
Write-Host "  ADMIN  login: " -NoNewline -ForegroundColor Cyan
Write-Host "admin@kentro.example   /  DemoPass!2026" -ForegroundColor White
Write-Host "  CLIENT login: " -NoNewline -ForegroundColor Cyan
Write-Host "client@atlas.example   /  DemoPass!2026" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Demo story: 4 services + Risk Register, released + downloadable" -ForegroundColor DarkGray
Write-Host "  See it on:  /home and /documents (client) - reports download" -ForegroundColor DarkGray
Write-Host "  Live AI (optional): put ANTHROPIC_API_KEY in .env, then re-run." -ForegroundColor DarkGray
Write-Host ""
