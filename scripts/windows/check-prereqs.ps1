$ErrorActionPreference = 'Stop'
$failed = $false
if ($env:OS -ne 'Windows_NT') { Write-Host 'FAIL Windows: this helper targets Windows 11'; exit 1 }
$build = [Environment]::OSVersion.Version.Build
if ($build -ge 22000) { Write-Host "PASS Windows build $build" } else { Write-Host "FAIL Windows build $build (Windows 11 required)"; $failed = $true }
foreach ($tool in @('docker', 'ollama', 'git')) {
    if (Get-Command $tool -ErrorAction SilentlyContinue) { Write-Host "PASS $tool command" }
    else { Write-Host "FAIL $tool missing; see SETUP_INSTRUCTIONS.md"; $failed = $true }
}
if (Get-Command tailscale -ErrorAction SilentlyContinue) { Write-Host 'PASS tailscale command (optional private remote access)' }
else { Write-Host 'NOT AVAILABLE tailscale (optional; needed only for private remote access)' }
if (Get-Command docker -ErrorAction SilentlyContinue) {
    $dockerOsType = docker info --format '{{.OSType}}'
    if ($LASTEXITCODE -eq 0 -and $dockerOsType -eq 'linux') { Write-Host 'PASS Docker daemon (Linux containers)' }
    elseif ($LASTEXITCODE -eq 0) { Write-Host "FAIL Docker engine type $dockerOsType; switch Docker Desktop to Linux containers"; $failed = $true }
    else { Write-Host 'FAIL Docker daemon; start Docker Desktop with Linux containers / WSL2'; $failed = $true }
}
if (Get-Command python -ErrorAction SilentlyContinue) { python --version; Write-Host 'Python is optional for host checks; worker includes Python.' }
else { Write-Host 'NOT AVAILABLE host Python (optional; run checks in worker)' }
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) { nvidia-smi; if ($LASTEXITCODE -ne 0) { $failed = $true } }
else { Write-Host 'NOT AVAILABLE nvidia-smi; update NVIDIA driver and verify GPU before inference' }
if ($failed) { exit 1 }

exit 0
