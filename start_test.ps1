param(
    [switch]$Restart,
    [switch]$RunMigrations,
    [switch]$SkipMigrations
)

$ErrorActionPreference = "Stop"
if ($RunMigrations -and $SkipMigrations) {
    throw "Use either -RunMigrations or -SkipMigrations, not both."
}
$serviceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$apiExe = Join-Path $serviceRoot ".venv\Scripts\welding-business-api.exe"
$alembicExe = Join-Path $serviceRoot ".venv\Scripts\alembic.exe"
$runtimeDir = Join-Path $serviceRoot ".runtime-tmp"
$stdoutLog = Join-Path $runtimeDir "test-api.stdout.log"
$stderrLog = Join-Path $runtimeDir "test-api.stderr.log"
$port = 8016

if (!(Test-Path -LiteralPath $apiExe)) {
    throw "API executable not found: $apiExe"
}

New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
$existing = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    $owner = Get-Process -Id $existing[0].OwningProcess -ErrorAction SilentlyContinue
    if (!$Restart) {
        throw "Port $port is already in use by PID=$($existing[0].OwningProcess) $($owner.ProcessName). Use -Restart only when it is this service."
    }

    $serviceProcesses = Get-CimInstance Win32_Process | Where-Object {
        (($_.Name -eq "welding-business-api.exe") -and ($_.ExecutablePath -like "$serviceRoot\\.venv\\Scripts\\*")) -or
        (($_.Name -eq "python.exe") -and ($_.CommandLine -like "*$serviceRoot*.venv*welding-business-api.exe*"))
    }
    foreach ($process in $serviceProcesses) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
}

if ($RunMigrations) {
    if (!(Test-Path -LiteralPath $alembicExe)) {
        throw "Alembic executable not found: $alembicExe"
    }
    Write-Host "Running database migrations..."
    & $alembicExe upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "Database migration failed with exit code $LASTEXITCODE"
    }
}

Remove-Item -LiteralPath $stdoutLog, $stderrLog -Force -ErrorAction SilentlyContinue
$env:SERVICE_HOST = "0.0.0.0"
$env:SERVICE_PORT = "$port"
$process = Start-Process `
    -FilePath $apiExe `
    -WorkingDirectory $serviceRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

Write-Host "API started. PID=$($process.Id)"
Write-Host "URL: http://127.0.0.1:$port"
Write-Host "Error log: $stderrLog"

$deadline = (Get-Date).AddSeconds(15)
$listener = $null
do {
    Start-Sleep -Milliseconds 500
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($listener) { break }
} while ((Get-Date) -lt $deadline)

if (!$listener) {
    Write-Host "API failed to start. Recent error log:" -ForegroundColor Red
    if (Test-Path -LiteralPath $stderrLog) {
        Get-Content -LiteralPath $stderrLog -Tail 40
    }
    exit 1
}

try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/v1/health" -TimeoutSec 5
    Write-Host "Health check passed: $($health | ConvertTo-Json -Compress)" -ForegroundColor Green
} catch {
    Write-Warning "Port is listening, but health check failed: $($_.Exception.Message)"
}

Write-Host "Welding MCP command: $serviceRoot\.venv\Scripts\hermes-welding-mcp-welding.exe"
Write-Host "Painting MCP command: $serviceRoot\.venv\Scripts\hermes-welding-mcp-painting.exe"
Write-Host "Stop API: Stop-Process -Id $($process.Id)"
