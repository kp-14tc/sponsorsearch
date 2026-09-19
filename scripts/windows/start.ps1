$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot '../..')
try {
    if (-not (Test-Path '.env')) { throw 'Copy .env.example to .env and fill in secrets first. See SETUP_INSTRUCTIONS.md.' }
    & (Join-Path $PSScriptRoot 'check-prereqs.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Prerequisite check failed.' }
    & (Join-Path $PSScriptRoot 'test-ollama.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Native Ollama check failed.' }
    docker compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Compose configuration failed.' }
    docker compose up -d --build --wait --wait-timeout 180
    if ($LASTEXITCODE -ne 0) { throw 'Stack startup failed. Inspect: docker compose logs --tail 100' }
    docker compose exec -T worker python scripts/healthcheck.py --inside
    if ($LASTEXITCODE -ne 0) { throw 'Health checks failed; see docs/windows-setup.md.' }
    Write-Host 'Open http://localhost:5678 and create the n8n owner account. See docs/workflows.md.'
} finally { Pop-Location }
