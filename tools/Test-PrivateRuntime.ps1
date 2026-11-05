# Development-only: elevate the bounded service helper, never the tracking engine.
param(
    [string]$RuntimeDirectory = (Join-Path $PSScriptRoot '..\.tools\private-runtime-321'),
    [ValidateRange(1,15)][int]$CaptureSeconds = 5,
    [switch]$Lifecycle,
    [string]$PythonPath
)

$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this test from a normal terminal so that the engine remains non-administrator.'
}
$projectPath = Split-Path -Parent $PSScriptRoot
if (-not $PythonPath) { $PythonPath = Join-Path $projectPath '.venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'This checkout needs its .venv before running the development test.'
}
$runtimePath = (Resolve-Path -LiteralPath $RuntimeDirectory).Path
$controlPath = Join-Path $projectPath ('.tools\private-probes\' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $controlPath -Force | Out-Null
$helperPath = Join-Path $PSScriptRoot 'Pause-LeapForProbe.ps1'
$probePath = Join-Path $PSScriptRoot 'probe_private_runtime.py'
if ($Lifecycle) { $probePath = Join-Path $PSScriptRoot 'probe_runtime_lifecycle.py' }
$readyPath = Join-Path $controlPath 'ready.json'
$restoredPath = Join-Path $controlPath 'restored.json'
$helperStarted = $false
$exitCode = 2
try {
    $helperArguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -ControlDirectory "{1}"' -f $helperPath, $controlPath
    Write-Host 'Approve the Windows prompt to pause LeapService for this bounded test.'
    Start-Process -FilePath 'powershell.exe' -Verb RunAs -WindowStyle Hidden -ArgumentList $helperArguments | Out-Null
    $helperStarted = $true
    $deadline = [DateTime]::UtcNow.AddSeconds(20)
    while (-not (Test-Path -LiteralPath $readyPath)) {
        if (Test-Path -LiteralPath $restoredPath) {
            throw (Get-Content -LiteralPath $restoredPath -Raw)
        }
        if ([DateTime]::UtcNow -gt $deadline) {
            throw 'The service-pause helper did not become ready.'
        }
        Start-Sleep -Milliseconds 100
    }
    Write-Host 'Running the private engine with the normal user account...'
    if ($Lifecycle) {
        & $pythonPath $probePath $runtimePath --summary (Join-Path $controlPath 'summary.json')
    } else {
        & $pythonPath $probePath $runtimePath --duration $CaptureSeconds --summary (Join-Path $controlPath 'summary.json') --record (Join-Path $controlPath 'tracking.jsonl')
    }
    $exitCode = $LASTEXITCODE
} catch {
    Write-Host $_.Exception.Message
} finally {
    New-Item -ItemType File -Path (Join-Path $controlPath 'done') -Force | Out-Null
    if ($helperStarted) {
        $deadline = [DateTime]::UtcNow.AddSeconds(15)
        while (-not (Test-Path -LiteralPath $restoredPath) -and [DateTime]::UtcNow -lt $deadline) {
            Start-Sleep -Milliseconds 100
        }
        if (Test-Path -LiteralPath $restoredPath) {
            $restored = Get-Content -LiteralPath $restoredPath -Raw | ConvertFrom-Json
            Write-Host ('Installed service: ' + $restored.final_status)
            if (-not $restored.restored) {
                Write-Host ('Restoration failed. See ' + $restoredPath)
                $exitCode = 2
            } elseif ($restored.was_running) {
                Write-Host 'Verifying that the restored service sends camera frames...'
                & $pythonPath -m source_robotics_leap_motion doctor --probe --json --timeout 10
                if ($LASTEXITCODE -ne 0) {
                    Write-Host 'Service is running, but the restored camera stream check failed.'
                    $exitCode = 2
                }
            }
        } else {
            Write-Host 'No restoration result yet. The helper has a separate 60-second watchdog.'
            $exitCode = 2
        }
    }
    Write-Host ('Test results: ' + $controlPath)
}
exit $exitCode
