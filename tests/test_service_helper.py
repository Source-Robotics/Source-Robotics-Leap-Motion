import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(
    sys.platform != "win32" or shutil.which("powershell.exe") is None,
    reason="Windows PowerShell helper regression test",
)
@pytest.mark.parametrize("delayed_stop", [False, True])
def test_service_helper_restores_original_running_state_even_after_stop_error(
    tmp_path, delayed_stop
):
    # Shadow service commands in a separate PowerShell process. No real service or UAC.
    helper = Path(__file__).resolve().parents[1] / "tools" / "Pause-LeapForProbe.ps1"
    (tmp_path / "done").touch()
    harness = tmp_path / "mock-service.ps1"
    mock_output = tmp_path / "mock-result.json"

    def quote(path):
        return "'" + str(path).replace("'", "''") + "'"

    harness.write_text(
        """
$ErrorActionPreference = 'Stop'
$global:fakeService = [pscustomobject]@{ Status = 'Running'; Starts = 0; NoWait = $false }
$global:fakeService | Add-Member -MemberType ScriptMethod -Name Refresh -Value {}
$global:fakeService | Add-Member -MemberType ScriptMethod -Name Start -Value {
    $this.Starts += 1
    $this.Status = 'Running'
}
$global:fakeService | Add-Member -MemberType ScriptMethod -Name WaitForStatus -Value {
    param($wanted, $timeout)
    if ($wanted -eq 'Stopped' -and $this.Status -eq 'StopPending') {
        $this.Status = 'Stopped'
    }
    if ($this.Status -ne $wanted) { throw 'Unexpected fake service state' }
}
function Get-Service { param($Name); return $global:fakeService }
function Stop-Service {
    param($Name, [switch]$NoWait)
    $global:fakeService.NoWait = $NoWait.IsPresent
    if (DELAYED_STOP) {
        $global:fakeService.Status = 'StopPending'
        throw 'Simulated delayed Windows stop error'
    }
    $global:fakeService.Status = 'Stopped'
}
function Start-Sleep { param($Milliseconds) }
""".replace("DELAYED_STOP", "$true" if delayed_stop else "$false")
        + "\n& "
        + quote(helper)
        + " -ControlDirectory "
        + quote(tmp_path)
        + "\n$global:fakeService | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath "
        + quote(mock_output),
        encoding="utf-8-sig",
    )
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    service = json.loads(mock_output.read_text(encoding="utf-8-sig"))
    restored = json.loads((tmp_path / "restored.json").read_text(encoding="utf-8-sig"))
    assert service["Starts"] == 1
    assert service["NoWait"]
    assert restored["was_running"]
    assert restored["stop_requested"]
    assert restored["restored"]
    assert restored["final_status"] == "Running"
    assert bool(restored.get("error")) == delayed_stop
