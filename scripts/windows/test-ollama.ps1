$ErrorActionPreference = 'Stop'
try { $tags = Invoke-RestMethod 'http://localhost:11434/api/tags' -TimeoutSec 15 }
catch { Write-Host "FAIL native Ollama: $($_.Exception.Message). See docs/windows-setup.md"; exit 1 }
Write-Host 'PASS native Ollama API'
$missing = $false
foreach ($model in @('qwen3.5:4b', 'qwen3.5:9b')) {
    if ($tags.models.name -contains $model) { Write-Host "PASS $model installed" }
    else { Write-Host "FAIL $model missing; run: ollama pull $model"; $missing = $true }
}
Write-Host 'Model installation does not verify GPU use or structured inference.'
if ($missing) { exit 1 }

exit 0
