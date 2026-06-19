# rook-mcp-processes.ps1
#
# Lists Rook MCP python processes by default. Stops only exact python -m rook
# processes when -Stop is supplied.

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [switch]$Stop
)

$ErrorActionPreference = 'Stop'

function Get-RookMcpProcess {
    $previousWhatIfPreference = $WhatIfPreference
    try {
        $WhatIfPreference = $false
        return Get-CimInstance Win32_Process |
            Where-Object {
                $_.Name -match '^pythonw?\.exe$' -and
                $_.CommandLine -match '(^|\s)-m\s+rook(\s|$)'
            } |
            Sort-Object ProcessId
    } finally {
        $WhatIfPreference = $previousWhatIfPreference
    }
}

$processes = @(Get-RookMcpProcess)

if ($processes.Count -eq 0) {
    Write-Host 'No python -m rook processes found.'
    exit 0
}

$processes |
    Select-Object ProcessId, ParentProcessId, Name, ExecutablePath, CommandLine |
    Format-Table -Wrap |
    Out-String |
    Write-Host

if (-not $Stop) {
    Write-Host 'Rerun with -Stop to stop only the listed python -m rook processes.'
    exit 0
}

foreach ($process in $processes) {
    $target = "PID $($process.ProcessId): $($process.CommandLine)"
    if ($PSCmdlet.ShouldProcess($target, 'Stop python -m rook process')) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
    }
}

if ($WhatIfPreference) {
    Write-Host 'WhatIf mode: no python -m rook processes were stopped.'
    exit 0
}

$remaining = @(Get-RookMcpProcess)
if ($remaining.Count -gt 0) {
    $ids = ($remaining | Select-Object -ExpandProperty ProcessId) -join ', '
    throw "Some python -m rook processes are still running: $ids"
}

Write-Host "Stopped $($processes.Count) python -m rook process(es)."
