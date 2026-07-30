<#
.SYNOPSIS
    Create/update venv\ and launch the discovery GUI on Windows (PowerShell port
    of start-mu2edaq-discover-gui.sh). All arguments pass through to the GUI.
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$GuiArgs
)

$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Here

$Python = $env:PYTHON
if (-not $Python) {
    if (Get-Command python -ErrorAction SilentlyContinue) { $Python = 'python' }
    elseif (Get-Command py -ErrorAction SilentlyContinue) { $Python = 'py' }
    else { Write-Error 'Python 3.9+ not found on PATH.'; exit 1 }
}
if (-not (Test-Path 'venv')) { & $Python -m venv venv }

$VenvPy = Join-Path $Here 'venv\Scripts\python.exe'
& $VenvPy -m pip install --quiet --upgrade pip
& $VenvPy -m pip install --quiet -e '.[gui]'

& $VenvPy -m mu2edaq_discovery.gui @GuiArgs
exit $LASTEXITCODE
