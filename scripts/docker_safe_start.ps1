# Start Docker Desktop safely on Windows.
# Docker Desktop can crash at startup ("listening on unix://...: remove ...: The file cannot be accessed by the system")
# when an unclean exit left stale AF_UNIX socket files behind (Model Runner: Docker\run\dockerInference,
# Secrets Engine: docker-secrets-engine\engine.sock). With Docker Desktop stopped, this script removes those files
# (renaming the folder if Windows refuses the delete), keeps Model Runner disabled, then starts Docker and waits.
# Usage (PowerShell):  powershell -ExecutionPolicy Bypass -File scripts\docker_safe_start.ps1

$ErrorActionPreference = "Continue"
$local = $env:LOCALAPPDATA
$stale = @(
    (Join-Path $local "Docker\run\dockerInference"),
    (Join-Path $local "Docker\run\userAnalyticsOtlpHttp.sock"),
    (Join-Path $local "docker-secrets-engine\engine.sock")
)

# True when the Docker engine answers.
function Test-Engine { docker info --format "{{.ServerVersion}}" 2>$null | Out-Null; return $LASTEXITCODE -eq 0 }

if (Test-Engine) { Write-Host "Docker engine is already running; nothing to clean."; exit 0 }

foreach ($path in $stale) {
    if (-not (Test-Path -LiteralPath $path)) { continue }
    try {
        Remove-Item -LiteralPath $path -Force -ErrorAction Stop
        Write-Host "removed stale socket $path"
    } catch {
        # Windows sometimes cannot delete a dead AF_UNIX socket; moving its folder aside lets Docker recreate it.
        $folder = Split-Path $path -Parent
        $aside = "$folder.stale-$(Get-Date -Format yyyyMMddHHmmss)"
        try { Rename-Item -LiteralPath $folder -NewName (Split-Path $aside -Leaf) -ErrorAction Stop; Write-Host "moved $folder aside" }
        catch { Write-Warning "could not clean $path : $($_.Exception.Message)" }
    }
}

Write-Host "starting Docker Desktop..."
docker desktop start 2>$null
if ($LASTEXITCODE -ne 0) { Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe" }
for ($i = 0; $i -lt 60; $i++) {
    if (Test-Engine) { break }
    Start-Sleep -Seconds 5
}
if (-not (Test-Engine)) { Write-Error "Docker engine did not start within 5 minutes"; exit 1 }
docker desktop disable model-runner 2>$null | Out-Null   # keep Model Runner off (we use Ollama)
Write-Host "Docker engine is up: $(docker info --format '{{.ServerVersion}}')"
