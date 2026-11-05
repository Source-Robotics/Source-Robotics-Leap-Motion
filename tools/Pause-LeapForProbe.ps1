param(
    [Parameter(Mandatory=$true)][string]$ControlDirectory
)

$ErrorActionPreference = 'Stop'
$controlPath = (Resolve-Path -LiteralPath $ControlDirectory).Path
$readyPath = Join-Path $controlPath 'ready.json'
$donePath = Join-Path $controlPath 'done'
$resultPath = Join-Path $controlPath 'restored.json'
$result = @{ restored = $false; stopped_by_helper = $false; stop_requested = $false }
$service = Get-Service -Name LeapService
$wasRunning = $service.Status -eq 'Running'
$result.was_running = $wasRunning
try {
    if ($wasRunning) {
        $result.stop_requested = $true
        Stop-Service -Name LeapService -NoWait
        $result.stopped_by_helper = $true
        $service.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(10))
    }
    @{ service = 'Stopped'; maximum_pause_seconds = 60 } |
        ConvertTo-Json | Set-Content -LiteralPath $readyPath -Encoding UTF8
    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    while (-not (Test-Path -LiteralPath $donePath) -and [DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 100
    }
} catch {
    $result.error = $_.Exception.Message
} finally {
    try {
        # A stop request can time out and still take effect afterward. Restore the
        # original running state even when Stop-Service or WaitForStatus threw.
        if ($wasRunning) {
            $service.Refresh()
            if ($service.Status -eq 'StopPending') {
                $service.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(30))
            }
            # Give USB teardown a brief settling interval before reopening the camera.
            if ($service.Status -eq 'Stopped') {
                Start-Sleep -Milliseconds 1000
                $service.Start()
            }
            $service.WaitForStatus('Running', [TimeSpan]::FromSeconds(10))
        }
        $service.Refresh()
        $result.final_status = $service.Status.ToString()
        $result.restored = (-not $wasRunning) -or $service.Status -eq 'Running'
    } catch {
        $result.restore_error = $_.Exception.Message
    }
    $result | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
}
