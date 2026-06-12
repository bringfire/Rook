$ErrorActionPreference = 'Stop'

$TestRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestRoot)
$Helper = Join-Path $RepoRoot 'installer\rook_process_preflight.ps1'

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Assert-Equals {
    param($Actual, $Expected, [string]$Message)
    if ($Actual -ne $Expected) { throw "$Message Expected [$Expected], got [$Actual]." }
}

function New-TestRoot {
    $root = Join-Path $env:TEMP ("rook-preflight-test-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $root -Force | Out-Null
    return $root
}

function Remove-TestRoot {
    param([string]$Root)
    if (-not [string]::IsNullOrWhiteSpace($Root)) {
        Remove-Item -LiteralPath $Root -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-Helper {
    param(
        [string]$Mode,
        [string]$RookRoot,
        [string]$LogRoot,
        [string[]]$ExtraArgs = @(),
        [switch]$UseDefaultOutputPaths
    )
    $helperArgs = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $Helper,
        '-Mode', $Mode,
        '-RookRoot', $RookRoot,
        '-LogRoot', $LogRoot,
        '-SetupVersion', 'test'
    )
    if (-not $UseDefaultOutputPaths) {
        $summary = Join-Path $LogRoot 'post_install_summary.json'
        $innoSummary = Join-Path $LogRoot 'preflight-summary.txt'
        $log = Join-Path $LogRoot 'post_install.log'
        $helperArgs += @(
            '-SummaryPath', $summary,
            '-InnoSummaryPath', $innoSummary,
            '-LogPath', $log
        )
    }
    if ($ExtraArgs) {
        $helperArgs += $ExtraArgs
    }
    & powershell.exe @helperArgs
    return $LASTEXITCODE
}

function Import-HelperFunctionsForUnitTest {
    Clear-TestCommandMocks

    $tokens = $null
    $parseErrors = $null
    $source = Get-Content -Path $Helper -Raw
    $ast = [System.Management.Automation.Language.Parser]::ParseInput($source, [ref]$tokens, [ref]$parseErrors)
    Assert-Equals @($parseErrors).Count 0 'Helper script must parse for unit harness import.'

    $functions = $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)
    foreach ($functionAst in $functions) {
        $body = $functionAst.Body.Extent.Text
        $body = $body.Substring(1, $body.Length - 2)
        if (@($functionAst.Parameters).Count -gt 0) {
            $parameters = @($functionAst.Parameters | ForEach-Object { $_.Extent.Text }) -join ', '
            $body = ("param({0})`r`n{1}" -f $parameters, $body)
        }
        Set-Item -Path ("function:script:{0}" -f $functionAst.Name) -Value ([scriptblock]::Create($body))
    }
}

function Clear-TestCommandMocks {
    foreach ($mockName in @('Get-CimInstance', 'Stop-Process', 'Get-Process', 'Start-Sleep')) {
        Remove-Item -Path ("function:script:{0}" -f $mockName) -ErrorAction SilentlyContinue
    }
}

function Test-EnumerateNoConflictsSeedsSummaryAndLog {
    $root = New-TestRoot
    try {
        $logs = Join-Path $root 'logs'
        New-Item -ItemType Directory -Path $logs -Force | Out-Null

        $code = Invoke-Helper -Mode enumerate -RookRoot $root -LogRoot $logs

        Assert-Equals $code 0 'Enumeration with no matching processes must exit 0.'
        $summaryPath = Join-Path $logs 'post_install_summary.json'
        $innoSummaryPath = Join-Path $logs 'preflight-summary.txt'
        $logPath = Join-Path $logs 'post_install.log'
        Assert-True (Test-Path $summaryPath) 'Enumeration must seed post_install_summary.json.'
        Assert-True (Test-Path $innoSummaryPath) 'Enumeration must write the terse Inno summary file.'
        Assert-True (Test-Path $logPath) 'Enumeration must create post_install.log.'
        $summary = Get-Content -Path $summaryPath -Raw | ConvertFrom-Json
        Assert-Equals $summary.schema_version 1 'Summary schema version must be pinned.'
        Assert-Equals $summary.preflight.server_count 0 'No-conflict enumeration must record zero server roots.'
        Assert-Equals $summary.preflight.conflicts_found $false 'No-conflict enumeration must record conflicts_found=false.'
        $innoSummary = Get-Content -Path $innoSummaryPath -Raw
        Assert-True ($innoSummary.Contains('conflicts_found=false')) 'Inno summary must expose conflicts_found as key=value.'
        Assert-True ($innoSummary.Contains('message=')) 'Inno summary must include the exact dialog/status message.'
        $bytes = [IO.File]::ReadAllBytes($logPath)
        Assert-True ($bytes.Length -gt 0) 'Log must not be empty.'
        Assert-True (-not ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)) 'Log must be UTF-8 without a BOM.'
    }
    finally {
        Remove-TestRoot $root
    }
}

function Test-EnumerateRotatesExistingPostInstallLog {
    $root = New-TestRoot
    try {
        $logs = Join-Path $root 'logs'
        New-Item -ItemType Directory -Path $logs -Force | Out-Null
        $logPath = Join-Path $logs 'post_install.log'
        $previousLogPath = Join-Path $logs 'post_install.prev.log'
        $priorContent = "prior run content`r`n"
        $encoding = New-Object System.Text.UTF8Encoding($false)
        [IO.File]::WriteAllText($logPath, $priorContent, $encoding)

        $code = Invoke-Helper -Mode enumerate -RookRoot $root -LogRoot $logs

        Assert-Equals $code 0 'Enumeration with no matching processes must exit 0 while rotating an existing log.'
        Assert-True (Test-Path $previousLogPath) 'Existing post_install.log must rotate to post_install.prev.log.'
        Assert-Equals ([IO.File]::ReadAllText($previousLogPath)) $priorContent 'Rotated post_install.prev.log must retain the prior log content exactly.'
        $newLog = Get-Content -Path $logPath -Raw
        Assert-True ($newLog.Contains('mode=enumerate setup_version=test')) 'New post_install.log must contain the current enumerate run header.'
        Assert-True ($newLog.Contains('enumeration_complete')) 'New post_install.log must contain current enumerate completion content.'
        Assert-True (-not $newLog.Contains($priorContent.Trim())) 'New post_install.log must not retain prior-run content after rotation.'
    }
    finally {
        Remove-TestRoot $root
    }
}

function Test-EnumerateUsesDefaultOutputPathsUnderLogRoot {
    $root = New-TestRoot
    try {
        $logs = Join-Path $root 'logs'

        $code = Invoke-Helper -Mode enumerate -RookRoot $root -LogRoot $logs -UseDefaultOutputPaths

        Assert-Equals $code 0 'Enumeration with default output paths and no matching processes must exit 0.'
        $summaryPath = Join-Path $logs 'post_install_summary.json'
        $innoSummaryPath = Join-Path $logs 'preflight-summary.txt'
        $logPath = Join-Path $logs 'post_install.log'
        Assert-True (Test-Path $summaryPath) 'Default SummaryPath must resolve to post_install_summary.json under LogRoot.'
        Assert-True (Test-Path $innoSummaryPath) 'Default InnoSummaryPath must resolve to preflight-summary.txt under LogRoot.'
        Assert-True (Test-Path $logPath) 'Default LogPath must resolve to post_install.log under LogRoot.'
        $summary = Get-Content -Path $summaryPath -Raw | ConvertFrom-Json
        Assert-Equals $summary.setup_version 'test' 'Default output path invocation must still pass setup version through to the summary.'
    }
    finally {
        Remove-TestRoot $root
    }
}

function Test-InvalidModeReturnsHelperMisuseExitCode {
    $root = New-TestRoot
    try {
        $logs = Join-Path $root 'logs'
        New-Item -ItemType Directory -Path $logs -Force | Out-Null

        $code = Invoke-Helper -Mode invalid -RookRoot $root -LogRoot $logs

        Assert-Equals $code 40 'Invalid helper mode must be classified as helper misuse.'
    }
    finally {
        Remove-TestRoot $root
    }
}

function Test-RecordOutcomeCancelledUsesStableSummary {
    $root = New-TestRoot
    try {
        $logs = Join-Path $root 'logs'
        New-Item -ItemType Directory -Path $logs -Force | Out-Null
        $null = Invoke-Helper -Mode enumerate -RookRoot $root -LogRoot $logs

        $code = Invoke-Helper -Mode record-outcome -RookRoot $root -LogRoot $logs -ExtraArgs @('-Outcome', 'cancelled')

        Assert-Equals $code 0 'record-outcome cancelled must exit 0.'
        $summary = Get-Content -Path (Join-Path $logs 'post_install_summary.json') -Raw | ConvertFrom-Json
        Assert-Equals $summary.outcome 'cancelled' 'Summary must persist cancelled outcome.'
        $log = Get-Content -Path (Join-Path $logs 'post_install.log') -Raw
        Assert-True ($log.Contains('outcome=cancelled')) 'Log must describe consent cancellation.'
    }
    finally {
        Remove-TestRoot $root
    }
}

function Test-RecordOutcomePreservesSummaryUnderBracketedLogRoot {
    $root = New-TestRoot
    try {
        $logs = Join-Path $root 'logs-[literal]'
        [IO.Directory]::CreateDirectory($logs) | Out-Null
        $summaryPath = Join-Path $logs 'post_install_summary.json'
        $encoding = New-Object System.Text.UTF8Encoding($false)

        $enumerateCode = Invoke-Helper -Mode enumerate -RookRoot $root -LogRoot $logs
        Assert-Equals $enumerateCode 0 'Enumeration must seed the summary under a bracketed LogRoot.'

        $summary = [IO.File]::ReadAllText($summaryPath) | ConvertFrom-Json
        $summary | Add-Member -NotePropertyName literal_path_marker -NotePropertyValue 'preserve-me'
        [IO.File]::WriteAllText($summaryPath, (($summary | ConvertTo-Json -Depth 8) + "`r`n"), $encoding)

        $recordCode = Invoke-Helper -Mode record-outcome -RookRoot $root -LogRoot $logs -ExtraArgs @('-Outcome', 'installed')

        Assert-Equals $recordCode 0 'record-outcome must exit 0 under a bracketed LogRoot.'
        $updated = [IO.File]::ReadAllText($summaryPath) | ConvertFrom-Json
        Assert-Equals $updated.literal_path_marker 'preserve-me' 'record-outcome must preserve the existing summary when LogRoot contains brackets.'
        Assert-Equals $updated.outcome 'installed' 'record-outcome must update the outcome in the existing summary.'
    }
    finally {
        Remove-TestRoot $root
    }
}

function Test-CloseModeFailsQuietlyWhenNothingMatches {
    $root = New-TestRoot
    try {
        $logs = Join-Path $root 'logs'
        New-Item -ItemType Directory -Path $logs -Force | Out-Null

        $code = Invoke-Helper -Mode close -RookRoot $root -LogRoot $logs

        Assert-Equals $code 0 'Close mode with no matches must exit 0.'
    }
    finally {
        Remove-TestRoot $root
    }
}

function Test-CloseModePreservesEnumeratedPreflightOnSuccessfulClose {
    Import-HelperFunctionsForUnitTest

    $root = New-TestRoot
    try {
        $logs = Join-Path $root 'logs'
        $summaryPath = Join-Path $logs 'post_install_summary.json'
        $innoSummaryPath = Join-Path $logs 'preflight-summary.txt'
        $logPath = Join-Path $logs 'post_install.log'
        $parentPid = 49000
        $rootPid = 49001
        $parentCreated = [DateTime]::new(2026, 1, 1, 12, 0, 0, 100, [DateTimeKind]::Utc)
        $rootCreated = [DateTime]::new(2026, 1, 1, 12, 0, 0, 200, [DateTimeKind]::Utc)
        $parentProcess = [pscustomobject]@{
            ProcessId = $parentPid
            ParentProcessId = 4
            ExecutablePath = 'C:\Tools\claude.exe'
            CommandLine = ''
            CreationDateUtc = $parentCreated
            CreationDateText = Format-UtcTimestamp $parentCreated
            IsMatched = $false
        }
        $rootProcess = [pscustomobject]@{
            ProcessId = $rootPid
            ParentProcessId = $parentPid
            ExecutablePath = (Join-Path $root 'rook-agent.exe')
            CommandLine = '--port 9876'
            CreationDateUtc = $rootCreated
            CreationDateText = Format-UtcTimestamp $rootCreated
            IsMatched = $true
        }
        $indexes = New-ProcessIndexes @($parentProcess, $rootProcess)
        $originalPreflight = New-PreflightSummary -Roots @($rootProcess) -ByPid $indexes.ByPid
        $originalSummary = New-RunSummary -Preflight $originalPreflight -ClosedProcessCount 0 -RunOutcome 'preflight-enumerated'

        $script:SummaryPathResolved = $summaryPath
        $script:InnoSummaryPathResolved = $innoSummaryPath
        $script:LogPathResolved = $logPath
        $script:RookRootPrefix = Normalize-PathPrefix $root
        $script:RunStartUtc = Format-UtcTimestamp ([DateTime]::UtcNow)
        $script:SetupVersion = 'test'
        $script:ExitQuiet = 0
        $script:ExitNotQuiet = 10
        $script:ExitEnumerationFailure = 20
        $script:ExitCloseFailure = 30
        $script:ExitHelperError = 40
        $script:PreserveSnapshotCallCount = 0
        $script:PreserveRootProcess = $rootProcess
        $script:PreserveRootPid = $rootPid
        $script:PreserveRootCreated = $rootCreated
        $script:PreserveRootLive = $true
        Save-Summary $originalSummary

        function script:Get-ProcessSnapshot {
            $script:PreserveSnapshotCallCount++
            if ($script:PreserveSnapshotCallCount -eq 1) {
                return @($script:PreserveRootProcess)
            }
            return @()
        }

        function script:Get-CimInstance {
            param($ClassName, [string]$Filter, $ErrorAction)
            if (-not $script:PreserveRootLive) {
                return $null
            }
            return [pscustomobject]@{
                ProcessId = $script:PreserveRootPid
                CreationDate = [System.Management.ManagementDateTimeConverter]::ToDmtfDateTime($script:PreserveRootCreated)
            }
        }

        function script:Stop-Process {
            param([int]$Id, [switch]$Force, $ErrorAction)
            $script:PreserveRootLive = $false
        }

        function script:Start-Sleep {
            param([int]$Milliseconds)
        }

        $code = Invoke-CloseMode

        Assert-Equals $code 0 'Close mode must return quiet after closing the matched root.'
        $updated = Get-Content -Path $summaryPath -Raw | ConvertFrom-Json
        Assert-Equals $updated.outcome 'preflight-closed' 'Successful close must update the saved outcome.'
        Assert-Equals $updated.closed_process_count 1 'Successful close must update the closed process count.'
        Assert-Equals $updated.preflight.server_count 1 'Successful close must preserve the original enumerated server count.'
        Assert-Equals (@($updated.preflight.owners) -join ',') 'Claude' 'Successful close must preserve original owner evidence.'
        Assert-True ([string]$updated.preflight.message).Contains('started by Claude') 'Successful close must preserve the original conflict message.'
        Assert-Equals $updated.preflight.processes[0].process_id $rootPid 'Successful close must preserve the original process table.'
        Assert-Equals $updated.preflight.processes[0].owner 'Claude' 'Successful close must preserve original per-process owner evidence.'
    }
    finally {
        Remove-TestRoot $root
    }
}

function Test-ProcessEnumerationUsesTerminatingCimErrors {
    $source = Get-Content -Path $Helper -Raw
    Assert-True ($source -match 'Get-CimInstance\s+Win32_Process\s+-ErrorAction\s+Stop') 'Get-ProcessSnapshot must use -ErrorAction Stop so Win32_Process enumeration failures are terminating.'
}

function Test-EnumerateModeReturnsNotQuietExitCodeWhenConflictFound {
    Import-HelperFunctionsForUnitTest

    $root = New-TestRoot
    try {
        $logs = Join-Path $root 'logs'
        $created = [DateTime]::new(2026, 1, 1, 12, 0, 0, 123, [DateTimeKind]::Utc)
        $conflictProcess = [pscustomobject]@{
            ProcessId = 47000
            ParentProcessId = 4
            ExecutablePath = (Join-Path $root 'rook-agent.exe')
            CommandLine = ''
            CreationDateUtc = $created
            CreationDateText = Format-UtcTimestamp $created
            IsMatched = $true
        }

        $script:LogRoot = $logs
        $script:LogPathResolved = Join-Path $logs 'post_install.log'
        $script:RookRootPrefix = Normalize-PathPrefix $root
        $script:RunStartUtc = Format-UtcTimestamp ([DateTime]::UtcNow)
        $script:SetupVersion = 'test'
        $script:ExitQuiet = 0
        $script:ExitNotQuiet = 10
        $script:ExitEnumerationFailure = 20
        $script:ExitCloseFailure = 30
        $script:ExitHelperError = 40
        $script:NotQuietProcess = $conflictProcess
        $script:SavedSummary = $null

        function script:Get-ProcessSnapshot {
            return @($script:NotQuietProcess)
        }

        function script:Save-Summary {
            param([object]$Summary)
            $script:SavedSummary = $Summary
        }

        function script:Write-InnoSummary {
            param([object]$Preflight)
        }

        function script:Log-Line {
            param([string]$Message)
        }

        $code = Invoke-EnumerateMode

        Assert-Equals $code 10 'Enumerate mode must return the not-quiet exit code when a matching Rook process is found.'
        Assert-Equals $script:SavedSummary.preflight.conflicts_found $true 'Not-quiet enumeration must summarize conflicts_found=true.'
        Assert-Equals $script:SavedSummary.preflight.server_count 1 'Not-quiet enumeration must record the matched server root.'
    }
    finally {
        Remove-TestRoot $root
    }
}

function Test-PreflightSummaryCollapsesMatchedChildrenAndReportsOwners {
    Import-HelperFunctionsForUnitTest

    $root = New-TestRoot
    try {
        $logs = Join-Path $root 'logs'
        $script:InnoSummaryPathResolved = Join-Path $logs 'preflight-summary.txt'
        $parentCreated = [DateTime]::UtcNow.AddSeconds(-20)
        $rootCreated = [DateTime]::UtcNow.AddSeconds(-10)
        $childCreated = [DateTime]::UtcNow.AddSeconds(-5)
        $processes = @(
            [pscustomobject]@{
                ProcessId = 51000
                ParentProcessId = 4
                ExecutablePath = 'C:\Tools\claude.exe'
                CommandLine = ''
                CreationDateUtc = $parentCreated
                CreationDateText = Format-UtcTimestamp $parentCreated
                IsMatched = $false
            },
            [pscustomobject]@{
                ProcessId = 51001
                ParentProcessId = 51000
                ExecutablePath = (Join-Path $root 'server-a\rook-agent.exe')
                CommandLine = ''
                CreationDateUtc = $rootCreated
                CreationDateText = Format-UtcTimestamp $rootCreated
                IsMatched = $true
            },
            [pscustomobject]@{
                ProcessId = 51002
                ParentProcessId = 51001
                ExecutablePath = (Join-Path $root 'server-a\rook-worker.exe')
                CommandLine = ''
                CreationDateUtc = $childCreated
                CreationDateText = Format-UtcTimestamp $childCreated
                IsMatched = $true
            },
            [pscustomobject]@{
                ProcessId = 52000
                ParentProcessId = 4
                ExecutablePath = 'C:\Tools\codex.exe'
                CommandLine = ''
                CreationDateUtc = $parentCreated
                CreationDateText = Format-UtcTimestamp $parentCreated
                IsMatched = $false
            },
            [pscustomobject]@{
                ProcessId = 52001
                ParentProcessId = 52000
                ExecutablePath = (Join-Path $root 'server-b\rook-agent.exe')
                CommandLine = ''
                CreationDateUtc = $rootCreated
                CreationDateText = Format-UtcTimestamp $rootCreated
                IsMatched = $true
            },
            [pscustomobject]@{
                ProcessId = 53000
                ParentProcessId = 4
                ExecutablePath = 'C:\Tools\OtherCli.exe'
                CommandLine = ''
                CreationDateUtc = $parentCreated
                CreationDateText = Format-UtcTimestamp $parentCreated
                IsMatched = $false
            },
            [pscustomobject]@{
                ProcessId = 53001
                ParentProcessId = 53000
                ExecutablePath = (Join-Path $root 'server-c\rook-agent.exe')
                CommandLine = ''
                CreationDateUtc = $rootCreated
                CreationDateText = Format-UtcTimestamp $rootCreated
                IsMatched = $true
            }
        )
        $indexes = New-ProcessIndexes $processes

        $roots = @(Get-LogicalServerRoots -Processes $processes -ByPid $indexes.ByPid)
        $preflight = New-PreflightSummary -Roots $roots -ByPid $indexes.ByPid
        Write-InnoSummary $preflight

        Assert-Equals $roots.Count 3 'Matched child processes must collapse under their logical matched root.'
        Assert-True (-not (@($preflight.processes | ForEach-Object { [int]$_.process_id }) -contains 51002)) 'Matched child process must not be reported as a separate server root.'
        Assert-Equals $preflight.server_count 3 'Preflight summary must count only logical server roots.'
        Assert-Equals (@($preflight.owners) -join ',') 'Claude,Codex,OtherCli.exe' 'Owners must include friendly Claude/Codex mappings and raw basename fallback.'
        Assert-Equals (@($preflight.processes | ForEach-Object { $_.owner }) -join ',') 'Claude,Codex,OtherCli.exe' 'Each process summary must retain owner attribution.'
        $innoSummary = Get-Content -Path $script:InnoSummaryPathResolved -Raw
        Assert-True ($innoSummary.Contains('server_count=3')) 'Inno summary must expose the logical root server count.'
        Assert-True ($innoSummary.Contains('owners=Claude, Codex, OtherCli.exe')) 'Inno summary must expose owner attribution.'
        Assert-True ($innoSummary.Contains('started by Claude, Codex, and OtherCli.exe')) 'Inno summary message must include the owner phrase.'
    }
    finally {
        Remove-TestRoot $root
    }
}

function Test-EnumerateModeReturnsEnumerationFailureExitCodeWhenCimEnumerationFails {
    Import-HelperFunctionsForUnitTest

    $root = New-TestRoot
    try {
        $logs = Join-Path $root 'logs'

        $script:LogRoot = $logs
        $script:LogPathResolved = Join-Path $logs 'post_install.log'
        $script:RookRootPrefix = Normalize-PathPrefix $root
        $script:RunStartUtc = Format-UtcTimestamp ([DateTime]::UtcNow)
        $script:SetupVersion = 'test'
        $script:ExitQuiet = 0
        $script:ExitNotQuiet = 10
        $script:ExitEnumerationFailure = 20
        $script:ExitCloseFailure = 30
        $script:ExitHelperError = 40
        $script:CimErrorAction = $null

        function script:Get-CimInstance {
            param([string]$ClassName, $ErrorAction)
            $script:CimErrorAction = $ErrorAction
            throw 'simulated Win32_Process enumeration failure'
        }

        function script:Log-Line {
            param([string]$Message)
        }

        $code = Invoke-EnumerateMode

        Assert-Equals $code 20 'Enumerate mode must return the enumeration failure exit code when Win32_Process enumeration fails.'
        Assert-Equals ([string]$script:CimErrorAction) 'Stop' 'Win32_Process enumeration must request terminating CIM errors.'
    }
    finally {
        Remove-TestRoot $root
    }
}

function Test-ProcessIdentityKeyDistinguishesSamePidWithinSameSecond {
    Import-HelperFunctionsForUnitTest

    $targetPid = 41000
    $firstCreated = [DateTime]::new(2026, 1, 1, 12, 0, 0, 123, [DateTimeKind]::Utc)
    $secondCreated = $firstCreated.AddMilliseconds(456)
    $firstProcess = [pscustomobject]@{
        ProcessId = $targetPid
        CreationDateUtc = $firstCreated
        CreationDateText = Format-UtcTimestamp $firstCreated
    }
    $secondProcess = [pscustomobject]@{
        ProcessId = $targetPid
        CreationDateUtc = $secondCreated
        CreationDateText = Format-UtcTimestamp $secondCreated
    }

    Assert-Equals $firstProcess.CreationDateText $secondProcess.CreationDateText 'Test setup must use the same whole-second display timestamp.'
    Assert-True ((Get-ProcessIdentityKey $firstProcess) -ne (Get-ProcessIdentityKey $secondProcess)) 'Internal identity keys must preserve sub-second CreationDateUtc precision.'
}

function Test-LiveProcessIdentityRejectsSamePidWithinSameSecondDifferentFileTime {
    Import-HelperFunctionsForUnitTest

    $targetPid = 41010
    $snapshotCreated = [DateTime]::new(2026, 1, 1, 12, 0, 0, 123, [DateTimeKind]::Utc)
    $liveCreated = $snapshotCreated.AddTicks(5000)
    $snapshotProcess = [pscustomobject]@{
        ProcessId = $targetPid
        CreationDateUtc = $snapshotCreated
        CreationDateText = Format-UtcTimestamp $snapshotCreated
    }
    $liveProcess = [pscustomobject]@{
        ProcessId = $targetPid
        CreationDateUtc = $liveCreated
        CreationDateText = Format-UtcTimestamp $liveCreated
    }
    $script:LiveIdentityPid = $targetPid
    $script:LiveIdentityCreated = $liveCreated

    function script:Get-CimInstance {
        param($ClassName, [string]$Filter, $ErrorAction)
        return [pscustomobject]@{
            ProcessId = $script:LiveIdentityPid
            CreationDate = $script:LiveIdentityCreated
        }
    }

    Assert-Equals $snapshotProcess.CreationDateText $liveProcess.CreationDateText 'Test setup must use the same whole-second display timestamp.'
    Assert-True ((Get-ProcessIdentityKey $snapshotProcess) -ne (Get-ProcessIdentityKey $liveProcess)) 'Internal identity keys must not collide when only sub-millisecond creation time differs.'
    Assert-Equals (Test-LiveProcessIdentityMatches $snapshotProcess) $false 'Live identity revalidation must reject same PID with a different full-precision creation time.'
}

function Test-LiveProcessIdentityRejectsMissingCreationDateWithoutPidFallback {
    Import-HelperFunctionsForUnitTest

    $targetPid = 41020
    $snapshotProcess = [pscustomobject]@{
        ProcessId = $targetPid
        CreationDateUtc = $null
        CreationDateText = ''
    }
    $script:GetProcessWasCalled = $false

    function script:Get-Process {
        param([int]$Id, $ErrorAction)
        $script:GetProcessWasCalled = $true
        return [pscustomobject]@{
            Id = $Id
        }
    }

    function script:Get-CimInstance {
        throw 'Missing snapshot creation identity must not be revalidated against live process state.'
    }

    Assert-Equals (Test-LiveProcessIdentityMatches $snapshotProcess) $false 'Live identity revalidation must reject snapshots without a full creation-time identity.'
    Assert-Equals $script:GetProcessWasCalled $false 'Live identity revalidation must not fall back to PID-only Get-Process matching.'
}

function Test-CloseModeSkipsStopWhenPidIdentityChangesBeforeStop {
    Import-HelperFunctionsForUnitTest

    $root = New-TestRoot
    try {
        $targetPid = 43000
        $created = [DateTime]::new(2026, 1, 1, 12, 0, 0, 123, [DateTimeKind]::Utc)
        $replacementCreated = $created.AddSeconds(5)
        $rootProcess = [pscustomobject]@{
            ProcessId = $targetPid
            ParentProcessId = 4
            ExecutablePath = (Join-Path $root 'rook-agent.exe')
            CommandLine = ''
            CreationDateUtc = $created
            CreationDateText = Format-UtcTimestamp $created
            IsMatched = $true
        }

        $script:RookRootPrefix = Normalize-PathPrefix $root
        $script:RunStartUtc = Format-UtcTimestamp ([DateTime]::UtcNow)
        $script:SetupVersion = 'test'
        $script:ExitQuiet = 0
        $script:ExitNotQuiet = 10
        $script:ExitEnumerationFailure = 20
        $script:ExitCloseFailure = 30
        $script:ExitHelperError = 40
        $script:SnapshotCallCount = 0
        $script:StopCalled = $false
        $script:IdentityRootProcess = $rootProcess
        $script:IdentityReplacementCreated = $replacementCreated
        $script:IdentityTargetPid = $targetPid

        function script:Get-ProcessSnapshot {
            $script:SnapshotCallCount++
            if ($script:SnapshotCallCount -eq 1) {
                return @($script:IdentityRootProcess)
            }
            return @()
        }

        function script:Get-CimInstance {
            param($ClassName, [string]$Filter, $ErrorAction)
            return [pscustomobject]@{
                ProcessId = $script:IdentityTargetPid
                CreationDate = [System.Management.ManagementDateTimeConverter]::ToDmtfDateTime($script:IdentityReplacementCreated)
            }
        }

        function script:Stop-Process {
            param([int]$Id, [switch]$Force, $ErrorAction)
            $script:StopCalled = $true
        }

        function script:Get-Process {
            param([int]$Id, $ErrorAction)
            return $null
        }

        function script:Start-Sleep {
            param([int]$Milliseconds)
        }

        function script:Save-Summary {
            param([object]$Summary)
        }

        function script:Write-InnoSummary {
            param([object]$Preflight)
        }

        function script:Log-Line {
            param([string]$Message)
        }

        $code = Invoke-CloseMode

        Assert-Equals $code 0 'Close mode must reach quiet when the original process is gone.'
        Assert-Equals $script:StopCalled $false 'Close mode must not stop a PID whose CreationDate no longer matches the snapshot target.'
    }
    finally {
        Remove-TestRoot $root
    }
}

function Test-CloseModeReturnsCloseFailureWhenSuccessfulStopLeavesSameProcessAlive {
    Import-HelperFunctionsForUnitTest

    $root = New-TestRoot
    try {
        $targetPid = 44000
        $created = [DateTime]::new(2026, 1, 1, 12, 0, 0, 123, [DateTimeKind]::Utc)
        $rootProcess = [pscustomobject]@{
            ProcessId = $targetPid
            ParentProcessId = 4
            ExecutablePath = (Join-Path $root 'rook-agent.exe')
            CommandLine = ''
            CreationDateUtc = $created
            CreationDateText = Format-UtcTimestamp $created
            IsMatched = $true
        }

        $script:RookRootPrefix = Normalize-PathPrefix $root
        $script:RunStartUtc = Format-UtcTimestamp ([DateTime]::UtcNow)
        $script:SetupVersion = 'test'
        $script:ExitQuiet = 0
        $script:ExitNotQuiet = 10
        $script:ExitEnumerationFailure = 20
        $script:ExitCloseFailure = 30
        $script:ExitHelperError = 40
        $script:SavedSummary = $null
        $script:CloseFailureLogMessages = @()
        $script:StopCallCount = 0
        $script:PersistentRootProcess = $rootProcess
        $script:PersistentRootPid = $targetPid
        $script:PersistentRootCreated = $created

        function script:Get-ProcessSnapshot {
            return @($script:PersistentRootProcess)
        }

        function script:Get-CimInstance {
            param($ClassName, [string]$Filter, $ErrorAction)
            return [pscustomobject]@{
                ProcessId = $script:PersistentRootPid
                CreationDate = [System.Management.ManagementDateTimeConverter]::ToDmtfDateTime($script:PersistentRootCreated)
            }
        }

        function script:Stop-Process {
            param([int]$Id, [switch]$Force, $ErrorAction)
            $script:StopCallCount++
        }

        function script:Get-Process {
            param([int]$Id, $ErrorAction)
            return [pscustomobject]@{ Id = $script:PersistentRootPid }
        }

        function script:Start-Sleep {
            param([int]$Milliseconds)
        }

        function script:Save-Summary {
            param([object]$Summary)
            $script:SavedSummary = $Summary
        }

        function script:Write-InnoSummary {
            param([object]$Preflight)
        }

        function script:Log-Line {
            param([string]$Message)
            $script:CloseFailureLogMessages += $Message
        }

        $code = Invoke-CloseMode

        Assert-Equals $code 30 ("Close mode must return close failure when successful Stop-Process calls leave the same process alive. Logs: {0}" -f ($script:CloseFailureLogMessages -join '; '))
        Assert-Equals $script:SavedSummary.outcome 'preflight-close-failed' 'Persistent processes after successful stop attempts must be summarized as close failures.'
        Assert-Equals $script:SavedSummary.closed_process_count 0 'Repeated successful Stop-Process calls must not inflate closed_process_count while the same identity remains live.'
        Assert-Equals $script:StopCallCount 3 'Close mode must bound successful stop attempts before classifying a persistent process as failed.'
    }
    finally {
        Remove-TestRoot $root
    }
}

function Test-CloseModeStopsDescendantsBeforeAncestors {
    Import-HelperFunctionsForUnitTest

    $root = New-TestRoot
    try {
        $rootPid = 48000
        $childPid = 48001
        $grandchildPid = 48002
        $rootCreated = [DateTime]::new(2026, 1, 1, 12, 0, 0, 100, [DateTimeKind]::Utc)
        $childCreated = [DateTime]::new(2026, 1, 1, 12, 0, 0, 200, [DateTimeKind]::Utc)
        $grandchildCreated = [DateTime]::new(2026, 1, 1, 12, 0, 0, 300, [DateTimeKind]::Utc)
        $rootProcess = [pscustomobject]@{
            ProcessId = $rootPid
            ParentProcessId = 4
            ExecutablePath = (Join-Path $root 'rook-agent.exe')
            CommandLine = ''
            CreationDateUtc = $rootCreated
            CreationDateText = Format-UtcTimestamp $rootCreated
            IsMatched = $true
        }
        $childProcess = [pscustomobject]@{
            ProcessId = $childPid
            ParentProcessId = $rootPid
            ExecutablePath = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
            CommandLine = ''
            CreationDateUtc = $childCreated
            CreationDateText = Format-UtcTimestamp $childCreated
            IsMatched = $false
        }
        $grandchildProcess = [pscustomobject]@{
            ProcessId = $grandchildPid
            ParentProcessId = $childPid
            ExecutablePath = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
            CommandLine = ''
            CreationDateUtc = $grandchildCreated
            CreationDateText = Format-UtcTimestamp $grandchildCreated
            IsMatched = $false
        }

        $script:RookRootPrefix = Normalize-PathPrefix $root
        $script:RunStartUtc = Format-UtcTimestamp ([DateTime]::UtcNow)
        $script:SetupVersion = 'test'
        $script:ExitQuiet = 0
        $script:ExitNotQuiet = 10
        $script:ExitEnumerationFailure = 20
        $script:ExitCloseFailure = 30
        $script:ExitHelperError = 40
        $script:StopOrderSnapshotCallCount = 0
        $script:StopOrderProcesses = @($rootProcess, $childProcess, $grandchildProcess)
        $script:StopOrderLiveByPid = @{}
        $script:StopOrderCreationByPid = @{}
        $script:StopCallIds = @()
        foreach ($process in $script:StopOrderProcesses) {
            $processId = [int]$process.ProcessId
            $script:StopOrderLiveByPid[$processId] = $true
            $script:StopOrderCreationByPid[$processId] = $process.CreationDateUtc
        }

        function script:Get-ProcessSnapshot {
            $script:StopOrderSnapshotCallCount++
            if ($script:StopOrderSnapshotCallCount -eq 1) {
                return $script:StopOrderProcesses
            }
            return @()
        }

        function script:Get-CimInstance {
            param($ClassName, [string]$Filter, $ErrorAction)
            if ($Filter -notmatch 'ProcessId\s*=\s*(\d+)') {
                return $null
            }
            $processId = [int]$Matches[1]
            if (-not $script:StopOrderLiveByPid.ContainsKey($processId)) {
                return $null
            }
            return [pscustomobject]@{
                ProcessId = $processId
                CreationDate = [System.Management.ManagementDateTimeConverter]::ToDmtfDateTime($script:StopOrderCreationByPid[$processId])
            }
        }

        function script:Stop-Process {
            param([int]$Id, [switch]$Force, $ErrorAction)
            $script:StopCallIds += $Id
            $script:StopOrderLiveByPid.Remove($Id)
        }

        function script:Get-Process {
            param([int]$Id, $ErrorAction)
            if ($script:StopOrderLiveByPid.ContainsKey($Id)) {
                return [pscustomobject]@{ Id = $Id }
            }
            return $null
        }

        function script:Start-Sleep {
            param([int]$Milliseconds)
        }

        function script:Save-Summary {
            param([object]$Summary)
        }

        function script:Write-InnoSummary {
            param([object]$Preflight)
        }

        function script:Log-Line {
            param([string]$Message)
        }

        $code = Invoke-CloseMode

        Assert-Equals $code 0 'Close mode must reach quiet after mocked descendant and ancestor stops complete.'
        Assert-Equals ($script:StopCallIds -join ',') ("{0},{1},{2}" -f $grandchildPid, $childPid, $rootPid) 'Close mode must stop descendants before their ancestors.'
    }
    finally {
        Remove-TestRoot $root
    }
}

function Test-CloseModeSavesClosedOutcomeWhenFailedStopIdentityGoneAtFinalCheck {
    Import-HelperFunctionsForUnitTest

    $root = New-TestRoot
    try {
        $targetPid = 46000
        $created = [DateTime]::new(2026, 1, 1, 12, 0, 0, 123, [DateTimeKind]::Utc)
        $rootProcess = [pscustomobject]@{
            ProcessId = $targetPid
            ParentProcessId = 4
            ExecutablePath = (Join-Path $root 'rook-agent.exe')
            CommandLine = ''
            CreationDateUtc = $created
            CreationDateText = Format-UtcTimestamp $created
            IsMatched = $true
        }

        $script:RookRootPrefix = Normalize-PathPrefix $root
        $script:RunStartUtc = Format-UtcTimestamp ([DateTime]::UtcNow)
        $script:SetupVersion = 'test'
        $script:ExitQuiet = 0
        $script:ExitNotQuiet = 10
        $script:ExitEnumerationFailure = 20
        $script:ExitCloseFailure = 30
        $script:ExitHelperError = 40
        $script:MismatchSnapshotCallCount = 0
        $script:MismatchFinalCheckReached = $false
        $script:MismatchStopCallCount = 0
        $script:MismatchRootProcess = $rootProcess
        $script:MismatchRootPid = $targetPid
        $script:MismatchRootCreated = $created
        $script:SavedSummary = $null
        $script:MismatchLogMessages = @()

        function script:Get-ProcessSnapshot {
            $script:MismatchSnapshotCallCount++
            if ($script:MismatchSnapshotCallCount -le 3) {
                return @($script:MismatchRootProcess)
            }
            $script:MismatchFinalCheckReached = $true
            return @()
        }

        function script:Get-CimInstance {
            param($ClassName, [string]$Filter, $ErrorAction)
            if ($script:MismatchFinalCheckReached) {
                return $null
            }
            return [pscustomobject]@{
                ProcessId = $script:MismatchRootPid
                CreationDate = [System.Management.ManagementDateTimeConverter]::ToDmtfDateTime($script:MismatchRootCreated)
            }
        }

        function script:Stop-Process {
            param([int]$Id, [switch]$Force, $ErrorAction)
            $script:MismatchStopCallCount++
            throw 'simulated close failure before final exit'
        }

        function script:Get-Process {
            param([int]$Id, $ErrorAction)
            return $null
        }

        function script:Start-Sleep {
            param([int]$Milliseconds)
        }

        function script:Save-Summary {
            param([object]$Summary)
            $script:SavedSummary = $Summary
        }

        function script:Write-InnoSummary {
            param([object]$Preflight)
        }

        function script:Log-Line {
            param([string]$Message)
            $script:MismatchLogMessages += $Message
        }

        $code = Invoke-CloseMode

        Assert-Equals $code 0 ("Close mode must return quiet when failed stop identities are gone at final check. Logs: {0}" -f ($script:MismatchLogMessages -join '; '))
        Assert-Equals $script:SavedSummary.outcome 'preflight-closed' 'Saved summary outcome must match the quiet close return path.'
        Assert-Equals $script:MismatchStopCallCount 3 'Test setup must exhaust the stop attempts before the final quiet check.'
    }
    finally {
        Remove-TestRoot $root
    }
}

function Test-CloseModeReturnsCloseFailureWhenSuccessfulDescendantStopLeavesSameProcessAliveAfterRootGone {
    Import-HelperFunctionsForUnitTest

    $root = New-TestRoot
    try {
        $childPid = 45001
        $rootPid = 45000
        $rootCreated = [DateTime]::new(2026, 1, 1, 12, 0, 0, 100, [DateTimeKind]::Utc)
        $childCreated = [DateTime]::new(2026, 1, 1, 12, 0, 0, 200, [DateTimeKind]::Utc)
        $rootProcess = [pscustomobject]@{
            ProcessId = $rootPid
            ParentProcessId = 4
            ExecutablePath = (Join-Path $root 'rook-agent.exe')
            CommandLine = ''
            CreationDateUtc = $rootCreated
            CreationDateText = Format-UtcTimestamp $rootCreated
            IsMatched = $true
        }
        $childProcess = [pscustomobject]@{
            ProcessId = $childPid
            ParentProcessId = $rootPid
            ExecutablePath = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
            CommandLine = ''
            CreationDateUtc = $childCreated
            CreationDateText = Format-UtcTimestamp $childCreated
            IsMatched = $false
        }

        $script:RookRootPrefix = Normalize-PathPrefix $root
        $script:RunStartUtc = Format-UtcTimestamp ([DateTime]::UtcNow)
        $script:SetupVersion = 'test'
        $script:ExitQuiet = 0
        $script:ExitNotQuiet = 10
        $script:ExitEnumerationFailure = 20
        $script:ExitCloseFailure = 30
        $script:ExitHelperError = 40
        $script:SnapshotCallCount = 0
        $script:SavedSummary = $null
        $script:CloseFailureLogMessages = @()
        $script:NoOpRootProcess = $rootProcess
        $script:NoOpChildProcess = $childProcess
        $script:NoOpRootPid = $rootPid
        $script:NoOpChildPid = $childPid
        $script:NoOpRootCreated = $rootCreated
        $script:NoOpChildCreated = $childCreated
        $script:NoOpRootGone = $false
        $script:NoOpStopCallIds = @()

        function script:Get-ProcessSnapshot {
            $script:SnapshotCallCount++
            if ($script:SnapshotCallCount -eq 1) {
                return @($script:NoOpRootProcess, $script:NoOpChildProcess)
            }
            return @($script:NoOpChildProcess)
        }

        function script:Get-CimInstance {
            param($ClassName, [string]$Filter, $ErrorAction)
            if ($Filter -match ("ProcessId\s*=\s*{0}" -f $script:NoOpRootPid)) {
                if ($script:NoOpRootGone) {
                    return $null
                }
                return [pscustomobject]@{
                    ProcessId = $script:NoOpRootPid
                    CreationDate = [System.Management.ManagementDateTimeConverter]::ToDmtfDateTime($script:NoOpRootCreated)
                }
            }
            return [pscustomobject]@{
                ProcessId = $script:NoOpChildPid
                CreationDate = [System.Management.ManagementDateTimeConverter]::ToDmtfDateTime($script:NoOpChildCreated)
            }
        }

        function script:Stop-Process {
            param([int]$Id, [switch]$Force, $ErrorAction)
            $script:NoOpStopCallIds += $Id
            if ($Id -eq $script:NoOpRootPid) {
                $script:NoOpRootGone = $true
            }
        }

        function script:Get-Process {
            param([int]$Id, $ErrorAction)
            if ($Id -eq $script:NoOpChildPid) {
                return [pscustomobject]@{ Id = $script:NoOpChildPid }
            }
            return $null
        }

        function script:Start-Sleep {
            param([int]$Milliseconds)
        }

        function script:Save-Summary {
            param([object]$Summary)
            $script:SavedSummary = $Summary
        }

        function script:Write-InnoSummary {
            param([object]$Preflight)
        }

        function script:Log-Line {
            param([string]$Message)
            $script:CloseFailureLogMessages += $Message
        }

        $code = Invoke-CloseMode

        Assert-Equals $code 30 ("Close mode must return close failure when a successful out-of-boundary descendant stop leaves the same process alive after matched roots are gone. Logs: {0}" -f ($script:CloseFailureLogMessages -join '; '))
        Assert-Equals $script:SavedSummary.outcome 'preflight-close-failed' 'Attempted descendant identities that remain alive must be summarized as close failures even after matched roots disappear.'
        Assert-True ($script:NoOpStopCallIds -contains $script:NoOpChildPid) 'Test setup must attempt to close the out-of-boundary descendant.'
    }
    finally {
        Remove-TestRoot $root
    }
}

function Test-CloseModeReturnsCloseFailureWhenFailedDescendantRemainsAfterRootGone {
    Import-HelperFunctionsForUnitTest

    $root = New-TestRoot
    try {
        $childPid = 42001
        $rootPid = 42000
        $rootCreated = [DateTime]::new(2026, 1, 1, 12, 0, 0, 100, [DateTimeKind]::Utc)
        $childCreated = [DateTime]::new(2026, 1, 1, 12, 0, 0, 200, [DateTimeKind]::Utc)
        $rootProcess = [pscustomobject]@{
            ProcessId = $rootPid
            ParentProcessId = 4
            ExecutablePath = (Join-Path $root 'rook-agent.exe')
            CommandLine = ''
            CreationDateUtc = $rootCreated
            CreationDateText = Format-UtcTimestamp $rootCreated
            IsMatched = $true
        }
        $childProcess = [pscustomobject]@{
            ProcessId = $childPid
            ParentProcessId = $rootPid
            ExecutablePath = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
            CommandLine = ''
            CreationDateUtc = $childCreated
            CreationDateText = Format-UtcTimestamp $childCreated
            IsMatched = $false
        }

        $script:RookRootPrefix = Normalize-PathPrefix $root
        $script:RunStartUtc = Format-UtcTimestamp ([DateTime]::UtcNow)
        $script:SetupVersion = 'test'
        $script:ExitQuiet = 0
        $script:ExitNotQuiet = 10
        $script:ExitEnumerationFailure = 20
        $script:ExitCloseFailure = 30
        $script:ExitHelperError = 40
        $script:SnapshotCallCount = 0
        $script:SavedSummary = $null
        $script:CloseFailureLogMessages = @()
        $script:FailedRootProcess = $rootProcess
        $script:FailedChildProcess = $childProcess
        $script:FailedRootPid = $rootPid
        $script:FailedChildPid = $childPid
        $script:FailedRootCreated = $rootCreated
        $script:FailedChildCreated = $childCreated

        function script:Get-ProcessSnapshot {
            $script:SnapshotCallCount++
            if ($script:SnapshotCallCount -eq 1) {
                return @($script:FailedRootProcess, $script:FailedChildProcess)
            }
            return @($script:FailedChildProcess)
        }

        function script:Get-CimInstance {
            param($ClassName, [string]$Filter, $ErrorAction)
            if ($Filter -match [string]$script:FailedRootPid) {
                return [pscustomobject]@{
                    ProcessId = $script:FailedRootPid
                    CreationDate = [System.Management.ManagementDateTimeConverter]::ToDmtfDateTime($script:FailedRootCreated)
                }
            }
            return [pscustomobject]@{
                ProcessId = $script:FailedChildPid
                CreationDate = [System.Management.ManagementDateTimeConverter]::ToDmtfDateTime($script:FailedChildCreated)
            }
        }

        function script:Stop-Process {
            param([int]$Id, [switch]$Force, $ErrorAction)
            if ($Id -eq $script:FailedChildPid) {
                throw 'simulated descendant close failure'
            }
        }

        function script:Get-Process {
            param([int]$Id, $ErrorAction)
            if ($Id -eq $script:FailedChildPid) {
                return [pscustomobject]@{ Id = $script:FailedChildPid }
            }
            return $null
        }

        function script:Start-Sleep {
            param([int]$Milliseconds)
        }

        function script:Save-Summary {
            param([object]$Summary)
            $script:SavedSummary = $Summary
        }

        function script:Write-InnoSummary {
            param([object]$Preflight)
        }

        function script:Log-Line {
            param([string]$Message)
            $script:CloseFailureLogMessages += $Message
        }

        $code = Invoke-CloseMode

        Assert-Equals $code 30 ("Close mode must return close failure when a failed out-of-boundary descendant remains alive after matched roots are gone. Logs: {0}" -f ($script:CloseFailureLogMessages -join '; '))
        Assert-Equals $script:SavedSummary.outcome 'preflight-close-failed' 'Close failure summaries must not report preflight-closed before failed descendants are evaluated.'
    }
    finally {
        Remove-TestRoot $root
    }
}

function Test-CloseModePreservesEnumeratedPreflightOnDescendantOnlyCloseFailure {
    Import-HelperFunctionsForUnitTest

    $root = New-TestRoot
    try {
        $logs = Join-Path $root 'logs'
        $summaryPath = Join-Path $logs 'post_install_summary.json'
        $innoSummaryPath = Join-Path $logs 'preflight-summary.txt'
        $logPath = Join-Path $logs 'post_install.log'
        $parentPid = 42100
        $rootPid = 42101
        $childPid = 42102
        $parentCreated = [DateTime]::new(2026, 1, 1, 12, 0, 0, 50, [DateTimeKind]::Utc)
        $rootCreated = [DateTime]::new(2026, 1, 1, 12, 0, 0, 100, [DateTimeKind]::Utc)
        $childCreated = [DateTime]::new(2026, 1, 1, 12, 0, 0, 200, [DateTimeKind]::Utc)
        $parentProcess = [pscustomobject]@{
            ProcessId = $parentPid
            ParentProcessId = 4
            ExecutablePath = 'C:\Tools\codex.exe'
            CommandLine = ''
            CreationDateUtc = $parentCreated
            CreationDateText = Format-UtcTimestamp $parentCreated
            IsMatched = $false
        }
        $rootProcess = [pscustomobject]@{
            ProcessId = $rootPid
            ParentProcessId = $parentPid
            ExecutablePath = (Join-Path $root 'rook-agent.exe')
            CommandLine = '--port 9876'
            CreationDateUtc = $rootCreated
            CreationDateText = Format-UtcTimestamp $rootCreated
            IsMatched = $true
        }
        $childProcess = [pscustomobject]@{
            ProcessId = $childPid
            ParentProcessId = $rootPid
            ExecutablePath = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
            CommandLine = ''
            CreationDateUtc = $childCreated
            CreationDateText = Format-UtcTimestamp $childCreated
            IsMatched = $false
        }
        $indexes = New-ProcessIndexes @($parentProcess, $rootProcess, $childProcess)
        $originalPreflight = New-PreflightSummary -Roots @($rootProcess) -ByPid $indexes.ByPid
        $originalSummary = New-RunSummary -Preflight $originalPreflight -ClosedProcessCount 0 -RunOutcome 'preflight-enumerated'

        $script:SummaryPathResolved = $summaryPath
        $script:InnoSummaryPathResolved = $innoSummaryPath
        $script:LogPathResolved = $logPath
        $script:RookRootPrefix = Normalize-PathPrefix $root
        $script:RunStartUtc = Format-UtcTimestamp ([DateTime]::UtcNow)
        $script:SetupVersion = 'test'
        $script:ExitQuiet = 0
        $script:ExitNotQuiet = 10
        $script:ExitEnumerationFailure = 20
        $script:ExitCloseFailure = 30
        $script:ExitHelperError = 40
        $script:DescendantOnlySnapshotCallCount = 0
        $script:DescendantOnlyRootProcess = $rootProcess
        $script:DescendantOnlyChildProcess = $childProcess
        $script:DescendantOnlyRootPid = $rootPid
        $script:DescendantOnlyChildPid = $childPid
        $script:DescendantOnlyRootCreated = $rootCreated
        $script:DescendantOnlyChildCreated = $childCreated
        $script:DescendantOnlyRootLive = $true
        Save-Summary $originalSummary

        function script:Get-ProcessSnapshot {
            $script:DescendantOnlySnapshotCallCount++
            if ($script:DescendantOnlySnapshotCallCount -eq 1) {
                return @($script:DescendantOnlyRootProcess, $script:DescendantOnlyChildProcess)
            }
            return @($script:DescendantOnlyChildProcess)
        }

        function script:Get-CimInstance {
            param($ClassName, [string]$Filter, $ErrorAction)
            if ($Filter -match ("ProcessId\s*=\s*{0}" -f $script:DescendantOnlyRootPid)) {
                if (-not $script:DescendantOnlyRootLive) {
                    return $null
                }
                return [pscustomobject]@{
                    ProcessId = $script:DescendantOnlyRootPid
                    CreationDate = [System.Management.ManagementDateTimeConverter]::ToDmtfDateTime($script:DescendantOnlyRootCreated)
                }
            }
            return [pscustomobject]@{
                ProcessId = $script:DescendantOnlyChildPid
                CreationDate = [System.Management.ManagementDateTimeConverter]::ToDmtfDateTime($script:DescendantOnlyChildCreated)
            }
        }

        function script:Stop-Process {
            param([int]$Id, [switch]$Force, $ErrorAction)
            if ($Id -eq $script:DescendantOnlyRootPid) {
                $script:DescendantOnlyRootLive = $false
            }
        }

        function script:Start-Sleep {
            param([int]$Milliseconds)
        }

        $code = Invoke-CloseMode

        Assert-Equals $code 30 'Close mode must return close failure when only a stopped descendant remains live.'
        $updated = Get-Content -Path $summaryPath -Raw | ConvertFrom-Json
        Assert-Equals $updated.outcome 'preflight-close-failed' 'Descendant-only close failure must save a close-failed outcome.'
        Assert-Equals $updated.preflight.conflicts_found $true 'Descendant-only close failure must preserve conflicts_found=true from enumerate.'
        Assert-Equals $updated.preflight.server_count 1 'Descendant-only close failure must preserve the original enumerated server count.'
        Assert-Equals (@($updated.preflight.owners) -join ',') 'Codex' 'Descendant-only close failure must preserve original owner evidence.'
        Assert-Equals $updated.preflight.processes[0].process_id $rootPid 'Descendant-only close failure must preserve the original root process table.'
        $innoSummary = Get-Content -Path $innoSummaryPath -Raw
        Assert-True ($innoSummary.Contains('conflicts_found=true')) 'Inno summary must preserve conflicts_found=true on descendant-only close failure.'
        Assert-True ($innoSummary.Contains('server_count=1')) 'Inno summary must preserve the original server count on descendant-only close failure.'
        Assert-True ($innoSummary.Contains('owners=Codex')) 'Inno summary must preserve original owner evidence on descendant-only close failure.'
    }
    finally {
        Remove-TestRoot $root
    }
}

function Test-CloseModeReturnsInspectionFailureWhenIdentityRecheckCimThrows {
    Import-HelperFunctionsForUnitTest

    $root = New-TestRoot
    try {
        $rootPid = 43100
        $created = [DateTime]::new(2026, 1, 1, 12, 0, 0, 123, [DateTimeKind]::Utc)
        $rootProcess = [pscustomobject]@{
            ProcessId = $rootPid
            ParentProcessId = 4
            ExecutablePath = (Join-Path $root 'rook-agent.exe')
            CommandLine = ''
            CreationDateUtc = $created
            CreationDateText = Format-UtcTimestamp $created
            IsMatched = $true
        }

        $script:RookRootPrefix = Normalize-PathPrefix $root
        $script:RunStartUtc = Format-UtcTimestamp ([DateTime]::UtcNow)
        $script:SetupVersion = 'test'
        $script:ExitQuiet = 0
        $script:ExitNotQuiet = 10
        $script:ExitEnumerationFailure = 20
        $script:ExitCloseFailure = 30
        $script:ExitHelperError = 40
        $script:InspectionFailureRootProcess = $rootProcess
        $script:InspectionFailureStopCalled = $false

        function script:Get-ProcessSnapshot {
            return @($script:InspectionFailureRootProcess)
        }

        function script:Get-CimInstance {
            param($ClassName, [string]$Filter, $ErrorAction)
            throw 'simulated per-PID CIM identity recheck failure'
        }

        function script:Stop-Process {
            param([int]$Id, [switch]$Force, $ErrorAction)
            $script:InspectionFailureStopCalled = $true
        }

        function script:Start-Sleep {
            param([int]$Milliseconds)
        }

        function script:Save-Summary {
            param([object]$Summary)
        }

        function script:Write-InnoSummary {
            param([object]$Preflight)
        }

        function script:Log-Line {
            param([string]$Message)
        }

        $code = Invoke-CloseMode

        Assert-Equals $code 20 'Close mode must classify per-PID CIM identity recheck exceptions as process inspection failures.'
        Assert-Equals $script:InspectionFailureStopCalled $false 'Close mode must not stop a process after identity recheck inspection fails.'
    }
    finally {
        Remove-TestRoot $root
    }
}

function Test-PreBundledDescendantTreeCloseKillsOutOfBoundaryChild {
    Clear-TestCommandMocks

    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $python) {
        Write-Host 'SKIP: python.exe not on PATH for fabricated venv integration test.'
        return
    }

    $root = New-TestRoot
    try {
        $logs = Join-Path $root 'logs'
        New-Item -ItemType Directory -Path $logs -Force | Out-Null
        $venv = Join-Path $root 'venv'
        & $python -m venv $venv
        if ($LASTEXITCODE -ne 0) { throw 'Failed to create temp venv.' }

        $childPidFile = Join-Path $root 'child.pid'
        $script = Join-Path $root 'spawn_child.py'
        @'
import pathlib
import subprocess
import sys
import time

pid_file = pathlib.Path(sys.argv[1])
base = getattr(sys, "_base_executable", sys.executable)
child = subprocess.Popen([base, "-c", "import time; time.sleep(120)"])
pid_file.write_text(str(child.pid), encoding="utf-8")
try:
    time.sleep(120)
finally:
    child.terminate()
'@ | Set-Content -Path $script -Encoding UTF8

        $venvPython = Join-Path $venv 'Scripts\python.exe'
        $parentArgs = '"' + $script + '" "' + $childPidFile + '"'
        $parent = Start-Process -FilePath $venvPython -ArgumentList $parentArgs -PassThru -WindowStyle Hidden
        try {
            $deadline = (Get-Date).AddSeconds(20)
            while ((-not (Test-Path $childPidFile)) -and ((Get-Date) -lt $deadline)) {
                Microsoft.PowerShell.Utility\Start-Sleep -Milliseconds 100
            }
            Assert-True (Test-Path $childPidFile) 'Test child PID file was not written.'
            $childPid = [int](Get-Content -Path $childPidFile -Raw)

            $code = Invoke-Helper -Mode close -RookRoot $root -LogRoot $logs

            Assert-Equals $code 0 'Helper close mode must reach quiet.'
            Microsoft.PowerShell.Utility\Start-Sleep -Milliseconds 500
            Assert-True (-not (Microsoft.PowerShell.Management\Get-Process -Id $parent.Id -ErrorAction SilentlyContinue)) 'Matched venv root process must be closed.'
            Assert-True (-not (Microsoft.PowerShell.Management\Get-Process -Id $childPid -ErrorAction SilentlyContinue)) 'Out-of-boundary system-Python child must be closed.'
        }
        finally {
            Microsoft.PowerShell.Management\Stop-Process -Id $parent.Id -Force -ErrorAction SilentlyContinue
            if (Test-Path $childPidFile) {
                Microsoft.PowerShell.Management\Stop-Process -Id ([int](Get-Content -Path $childPidFile -Raw)) -Force -ErrorAction SilentlyContinue
            }
        }
    }
    finally {
        Remove-TestRoot $root
    }
}

Test-ProcessEnumerationUsesTerminatingCimErrors
Test-EnumerateNoConflictsSeedsSummaryAndLog
Test-EnumerateRotatesExistingPostInstallLog
Test-EnumerateUsesDefaultOutputPathsUnderLogRoot
Test-RecordOutcomeCancelledUsesStableSummary
Test-RecordOutcomePreservesSummaryUnderBracketedLogRoot
Test-CloseModeFailsQuietlyWhenNothingMatches
Test-CloseModePreservesEnumeratedPreflightOnSuccessfulClose
Test-PreBundledDescendantTreeCloseKillsOutOfBoundaryChild
Test-InvalidModeReturnsHelperMisuseExitCode
Test-EnumerateModeReturnsNotQuietExitCodeWhenConflictFound
Test-EnumerateModeReturnsEnumerationFailureExitCodeWhenCimEnumerationFails
Test-PreflightSummaryCollapsesMatchedChildrenAndReportsOwners
Test-ProcessIdentityKeyDistinguishesSamePidWithinSameSecond
Test-LiveProcessIdentityRejectsSamePidWithinSameSecondDifferentFileTime
Test-LiveProcessIdentityRejectsMissingCreationDateWithoutPidFallback
Test-CloseModeSkipsStopWhenPidIdentityChangesBeforeStop
Test-CloseModeReturnsCloseFailureWhenSuccessfulStopLeavesSameProcessAlive
Test-CloseModeStopsDescendantsBeforeAncestors
Test-CloseModeSavesClosedOutcomeWhenFailedStopIdentityGoneAtFinalCheck
Test-CloseModeReturnsCloseFailureWhenSuccessfulDescendantStopLeavesSameProcessAliveAfterRootGone
Test-CloseModeReturnsCloseFailureWhenFailedDescendantRemainsAfterRootGone
Test-CloseModePreservesEnumeratedPreflightOnDescendantOnlyCloseFailure
Test-CloseModeReturnsInspectionFailureWhenIdentityRecheckCimThrows
Write-Host 'rook-process-preflight.tests.ps1 PASS'
