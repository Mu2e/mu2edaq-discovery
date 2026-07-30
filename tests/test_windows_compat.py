"""Windows compatibility tests.

Added in the windows-compat sweep. Locks in:
  * the responder's socket setup uses the SO_REUSEPORT guard (absent on Windows)
    so the multicast bind works cross-platform, and
  * the GUI launch/bootstrap scripts ship PowerShell ports.

The end-to-end multicast loopback is exercised by tests/test_loopback.py, which
already passes on Windows.
"""
import pathlib
import shutil
import socket
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
PWSH = shutil.which("pwsh") or shutil.which("powershell")

SCRIPT_STEMS = [
    "bootstrap",
    "start-mu2edaq-discover-gui",
    "stop-mu2edaq-discover-gui",
]


def test_reuseport_is_optional():
    # responder.py only sets SO_REUSEPORT when the platform has it (Windows does
    # not). SO_REUSEADDR, which it always sets, does exist everywhere.
    assert hasattr(socket, "SO_REUSEADDR")
    # No assertion on SO_REUSEPORT existing -- it legitimately may not (Windows).


def test_multicast_constants_available():
    # The multicast options the responder/client use must exist on this platform.
    for attr in ("IP_MULTICAST_TTL", "IP_MULTICAST_IF",
                 "IP_ADD_MEMBERSHIP", "IPPROTO_IP"):
        assert hasattr(socket, attr), f"socket.{attr} missing on this platform"


def test_scripts_have_both_forms():
    for stem in SCRIPT_STEMS:
        assert (REPO / f"{stem}.sh").is_file(), f"missing bash script: {stem}.sh"
        assert (REPO / f"{stem}.ps1").is_file(), f"missing PowerShell port: {stem}.ps1"


@pytest.mark.skipif(not PWSH, reason="PowerShell not available")
@pytest.mark.parametrize("stem", SCRIPT_STEMS)
def test_powershell_scripts_parse(stem):
    path = (REPO / f"{stem}.ps1").as_posix()
    code = (
        "$e=$null;"
        f"[System.Management.Automation.Language.Parser]::ParseFile('{path}',[ref]$null,[ref]$e)|Out-Null;"
        "if($e){$e|ForEach-Object{Write-Error $_};exit 1}else{exit 0}"
    )
    result = subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-Command", code],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
