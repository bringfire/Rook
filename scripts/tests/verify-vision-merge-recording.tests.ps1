$ErrorActionPreference='Stop'
$scriptPath=Join-Path $PSScriptRoot '../verify-vision-merge.ps1'
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($scriptPath,[ref]$tokens,[ref]$errors)
$definition=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Invoke-Recorded'},$true)
Invoke-Expression $definition.Extent.Text
$taskRun=Join-Path ([IO.Path]::GetTempPath()) ('rook-record-test-'+[Guid]::NewGuid().ToString('N'));New-Item -ItemType Directory -Path $taskRun | Out-Null
$taskChecks=[Collections.Generic.List[object]]::new()
try {
    $failed=$false
    try { Invoke-Recorded 'stderr-exit' $env:ComSpec @('/d','/c','echo diagnostic-on-stderr 1>&2 & exit /b 7') } catch { $failed=$true }
    if (!$failed -or $taskChecks.Count -ne 1 -or $taskChecks[0].exit_code -ne 7 -or !(Get-Content (Join-Path $taskRun 'stderr-exit.log') -Raw).Contains('diagnostic-on-stderr')) { throw 'Recorder must preserve stderr and exit=7 before failing.' }
    if ($ErrorActionPreference -ne 'Stop') { throw 'Recorder did not restore caller error policy.' }
    Write-Host 'PASS: native stderr is retained with the real exit code.'
} finally {
    $resolved=[IO.Path]::GetFullPath($taskRun)
    if (!$resolved.StartsWith([IO.Path]::GetFullPath([IO.Path]::GetTempPath()),[StringComparison]::OrdinalIgnoreCase) -or ![IO.Path]::GetFileName($resolved).StartsWith('rook-record-test-')) { throw 'Unsafe test cleanup.' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
