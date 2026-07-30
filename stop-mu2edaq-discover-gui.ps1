<#
.SYNOPSIS
    Stop the discovery GUI cleanly on Windows (PowerShell port of
    stop-mu2edaq-discover-gui.sh): graceful close, then a forced kill if it is
    still up. Matches the process by command line via CIM (= `pgrep -f`).
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

function Get-MatchingPids([string]$Pattern) {
    Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match $Pattern -and $_.ProcessId -ne $PID } |
        ForEach-Object { $_.ProcessId }
}

$pattern = 'mu2edaq_discovery\.gui|mu2edaq-discover-gui'
$procs = @(Get-MatchingPids $pattern)
if ($procs.Count -eq 0) {
    Write-Host 'mu2edaq-discover-gui is not running.'
    exit 0
}

Write-Host "Stopping mu2edaq-discover-gui (pids: $($procs -join ' '))"
foreach ($p in $procs) {
    $proc = Get-Process -Id $p -ErrorAction SilentlyContinue
    if ($proc) { $proc.CloseMainWindow() | Out-Null }
}
for ($i = 0; $i -lt 5; $i++) {
    Start-Sleep -Seconds 1
    if (@(Get-MatchingPids $pattern).Count -eq 0) { Write-Host 'Stopped.'; exit 0 }
}

$procs = @(Get-MatchingPids $pattern)
Write-Host "Still running; forcing: $($procs -join ' ')"
foreach ($p in $procs) { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue }
Write-Host 'Stopped.'
