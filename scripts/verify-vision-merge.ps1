[CmdletBinding()]
param(
    [string]$Python = 'python',
    [ValidateRange(3, 10)][int]$FullRuns = 3,
    [switch]$PortableOnly,
    [switch]$PublishStatus
)
$ErrorActionPreference = 'Stop'
$taskRepo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskRun = Join-Path $taskRepo ('artifacts/vision-merge-verification/' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8))
New-Item -ItemType Directory -Path $taskRun -Force | Out-Null
$taskChecks = [Collections.Generic.List[object]]::new()
$taskContext = if ($PortableOnly) { 'Windows portable verification' } else { 'Windows managed verification (Rhino 8)' }
$taskCommit = $null
$taskRepository = $null
$taskFailure = $null
function Invoke-Recorded([string]$Name, [string]$Executable, [string[]]$Arguments) {
    $taskLog = Join-Path $taskRun ($Name + '.log')
    $taskStart = [DateTime]::UtcNow
    Write-Host "Running $Name"
    & $Executable @Arguments *> $taskLog
    $taskExit = $LASTEXITCODE
    $taskChecks.Add([ordered]@{ name = $Name; executable = $Executable; arguments = $Arguments; exit_code = $taskExit; started_utc = $taskStart.ToString('O'); seconds = ([DateTime]::UtcNow - $taskStart).TotalSeconds; log = $taskLog })
    if ($taskExit -ne 0) { throw "$Name failed (exit $taskExit); see $taskLog" }
}
function Publish-Verification([string]$State, [string]$Description) {
    if (!$PublishStatus) { return }
    & gh api --method POST "repos/$taskRepository/statuses/$taskCommit" -f "state=$State" -f "context=$taskContext" -f "description=$Description" --silent
    if ($LASTEXITCODE) { throw 'Publishing the verification status failed.' }
}
Push-Location $taskRepo
try {
    $taskCommit = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -or $taskCommit -notmatch '^[a-f0-9]{40}$') { throw 'Cannot identify the source commit.' }
    $taskInitialDirty = @(& git status --porcelain)
    if ($PublishStatus) {
        if ($taskInitialDirty.Count) { throw 'A published verification requires a clean committed tree.' }
        $taskRepository = (& gh repo view --json nameWithOwner --jq .nameWithOwner).Trim()
        if ($LASTEXITCODE -or $taskRepository -ne 'bringfire/Rook') { throw 'Cannot identify the expected repository.' }
        Publish-Verification 'pending' 'Running exact-commit Windows verification'
    }
    if (!$PortableOnly) {
        $taskRhino = Join-Path $env:ProgramFiles 'Rhino 8/System'
        foreach ($taskRequired in @('RhinoCommon.dll','Eto.dll','Eto.Wpf.dll')) {
            if (!(Test-Path -LiteralPath (Join-Path $taskRhino $taskRequired))) { throw "Managed verification requires the installed Rhino 8 dependency $taskRequired." }
        }
        Invoke-Recorded 'dotnet-environment' 'dotnet' @('--info')
        Invoke-Recorded 'companion-release-build' 'dotnet' @('build','src/Rook/Rook.csproj','-c','Release','-p:RhinoPluginDir=')
        Invoke-Recorded 'test-release-build' 'dotnet' @('build','src/Rook.Tests/Rook.Tests.csproj','-c','Release','-p:RhinoPluginDir=')
        Invoke-Recorded 'qualification-release-build' 'dotnet' @('build','src/Rook.Framing.Qualification/Rook.Framing.Qualification.csproj','-c','Release','-f','net48','-p:RhinoPluginDir=')
        $taskFilter = 'FullyQualifiedName!~LiveSmoke&FullyQualifiedName!~SupersededSolverRaceSpec_LinksToTheNormativeLifecycleDesign&FullyQualifiedName!~Task7_original_producer_values_survive_managed_http_parser'
        $taskTotal = $null
        for ($taskIndex = 1; $taskIndex -le $FullRuns; $taskIndex++) {
            Invoke-Recorded "managed-$taskIndex" 'dotnet' @('test','src/Rook.Tests/Rook.Tests.csproj','-c','Release','--no-build','-p:RhinoPluginDir=','--filter',$taskFilter,'--logger',"trx;LogFileName=managed-$taskIndex.trx",'--results-directory',$taskRun)
            [xml]$taskTrx = Get-Content -LiteralPath (Join-Path $taskRun "managed-$taskIndex.trx") -Raw
            $taskCounts = $taskTrx.TestRun.ResultSummary.Counters
            if ([int]$taskCounts.failed -ne 0 -or [int]$taskCounts.passed -le 0 -or [int]$taskCounts.notExecuted -ne 0 -or [int]$taskCounts.passed -ne [int]$taskCounts.total) { throw 'The full managed suite did not complete without failures/skips.' }
            if ($null -ne $taskTotal -and $taskTotal -ne [int]$taskCounts.total) { throw 'Managed test selection changed between runs.' }
            $taskTotal = [int]$taskCounts.total
        }
        $taskCompiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        $taskProbe = Join-Path $taskRun 'WaiterStarvationProbe.exe'
        Invoke-Recorded 'compile-waiter-probe' $taskCompiler @('/nologo',"/out:$taskProbe",('/reference:' + (Join-Path $taskRepo 'src/Rook.Tests/bin/Release/net48/xunit.abstractions.dll')),(Join-Path $taskRepo 'scripts/verification/WaiterStarvationProbe.cs'))
        Invoke-Recorded 'occupied-pool-waiter-stress' $taskProbe @((Join-Path $taskRepo 'src/Rook.Tests/bin/Release/net48/Rook.Tests.dll'))
        Invoke-Recorded 'delayed-pool-shutdown-drain' $taskProbe @((Join-Path $taskRepo 'src/Rook.Tests/bin/Release/net48/Rook.Tests.dll'),'--close-drain')
        Invoke-Recorded 'unrelated-renderer-contention' $taskProbe @((Join-Path $taskRepo 'src/Rook.Tests/bin/Release/net48/Rook.Tests.dll'),'--renderer-contention')
    }
    Invoke-Recorded 'vision-ui' 'node' @('--test','src/Rook.Tests/UI/Vision/image-fallback.test.cjs','src/Rook.Tests/UI/Vision/video-fallback.test.cjs','src/Rook.Tests/UI/Vision/video-framing.test.cjs')
    Invoke-Recorded 'video-python' $Python @('-m','pytest','mcp_server/tests/test_video_mcp_tools.py','mcp_server/tests/test_server_tool_profiles.py','-q','--junitxml',(Join-Path $taskRun 'python.xml'))
    Invoke-Recorded 'ffmpeg-payload' 'powershell' @('-NoProfile','-ExecutionPolicy','Bypass','-File','scripts/validate-ffmpeg-bundle.ps1','-SourceBundleManifestPath','third_party/ffmpeg/source/source-bundle-manifest.json')
    Invoke-Recorded 'ffmpeg-policy-tests' 'powershell' @('-NoProfile','-ExecutionPolicy','Bypass','-File','scripts/tests/ffmpeg-bundle-validation.tests.ps1')
    if ((& git rev-parse HEAD).Trim() -ne $taskCommit) { throw 'The source commit changed during verification.' }
    if ($PublishStatus -and @(& git status --porcelain).Count) { throw 'The source tree changed during verification.' }
    Publish-Verification 'success' $(if ($PortableOnly) { 'UI, Python and FFmpeg policy checks passed' } else { "$FullRuns full Release passes, waiter stress and portable checks passed" })
} catch {
    $taskFailure = $_.Exception.Message
    if ($taskRepository) { Publish-Verification 'failure' 'Verification failed; inspect recorded logs' }
    throw
} finally {
    [ordered]@{ commit = $taskCommit; initial_dirty = @($taskInitialDirty); portable_only = [bool]$PortableOnly; full_runs_required = $FullRuns; managed_tests_per_run = $taskTotal; machine = $env:COMPUTERNAME; logical_processors = [Environment]::ProcessorCount; os = [Environment]::OSVersion.VersionString; checks = @($taskChecks.ToArray()); failure = $taskFailure; finished_utc = [DateTime]::UtcNow.ToString('O') } | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $taskRun 'verification.json') -Encoding utf8
    Pop-Location
    Write-Host "Verification evidence: $taskRun"
}
