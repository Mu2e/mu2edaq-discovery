<#
.SYNOPSIS
    Bootstrap mu2edaq-discovery on Windows (PowerShell port of bootstrap.sh):
    create venv, install the package + dev deps.

.PARAMETER Gui
    Also install the Qt binding needed by mu2edaq-discover-gui.
#>
[CmdletBinding()]
param(
    [switch]$Gui
)

$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Here

$extras = 'dev,yaml'
if ($Gui) { $extras += ',gui' }

# Prefer 'python'; fall back to the py launcher ('python3' on Windows is the
# Microsoft Store alias stub, so it is not used here).
$Python = $env:PYTHON
if (-not $Python) {
    if (Get-Command python -ErrorAction SilentlyContinue) { $Python = 'python' }
    elseif (Get-Command py -ErrorAction SilentlyContinue) { $Python = 'py' }
    else { Write-Error 'Python 3.9+ not found on PATH. Install it first.'; exit 1 }
}

if (-not (Test-Path 'venv')) { & $Python -m venv venv }
$VenvPy = Join-Path $Here 'venv\Scripts\python.exe'
& $VenvPy -m pip install --upgrade pip | Out-Null
& $VenvPy -m pip install -e ".[$extras]"

Write-Host 'Done.'
Write-Host '  Run tests with:   venv\Scripts\pytest.exe'
Write-Host '  Run the GUI with: .\start-mu2edaq-discover-gui.ps1'
