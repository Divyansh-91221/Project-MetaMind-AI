# Developer helper commands for Windows (PowerShell).
# Mirrors the Makefile targets for developers without GNU Make.
#
#   ./scripts/dev.ps1 up
#   ./scripts/dev.ps1 migrate
#   ./scripts/dev.ps1 seed

param(
    [Parameter(Position = 0)]
    [ValidateSet('install', 'up', 'down', 'logs', 'migrate', 'seed', 'demo', 'run', 'frontend', 'test', 'lint', 'format', 'typecheck')]
    [string]$Command = 'help'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

switch ($Command) {
    'install' {
        python -m pip install --upgrade pip
        python -m pip install -r "$root/backend/requirements.txt"
        pre-commit install
    }
    'up' { docker compose -f "$root/docker-compose.yml" up -d --build }
    'down' { docker compose -f "$root/docker-compose.yml" down }
    'logs' { docker compose -f "$root/docker-compose.yml" logs -f --tail=100 }
    'migrate' { Push-Location "$root/backend"; alembic upgrade head; Pop-Location }
    'seed' { python "$root/scripts/seed_demo_data.py" }
    'demo' {
        docker compose -f "$root/docker-compose.yml" up -d --build
        docker compose -f "$root/docker-compose.yml" exec backend alembic -c alembic.ini upgrade head
        docker compose -f "$root/docker-compose.yml" exec backend python /app/scripts/seed_demo_data.py
    }
    'run' { uvicorn app.main:app --app-dir "$root/backend" --reload --port 8000 }
    'frontend' { Push-Location "$root/frontend"; npm run dev; Pop-Location }
    'test' { Push-Location $root; pytest; Pop-Location }
    'lint' { Push-Location $root; ruff check backend scripts tests; Pop-Location }
    'format' { Push-Location $root; black backend scripts tests; ruff check --fix backend scripts tests; Pop-Location }
    'typecheck' { Push-Location $root; mypy backend/app; Pop-Location }
    default {
        Write-Host 'Usage: ./scripts/dev.ps1 <install|up|down|logs|migrate|seed|demo|run|frontend|test|lint|format|typecheck>'
    }
}
