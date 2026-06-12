param(
    [string]$Mode,

    [string]$RookRoot,

    [string]$LogRoot,

    [string]$SummaryPath,
    [string]$InnoSummaryPath,
    [string]$LogPath,
    [string]$SetupVersion = 'unknown',
    [string]$Outcome = ''
)

$ExitQuiet = 0
$ExitNotQuiet = 10
$ExitEnumerationFailure = 20
$ExitCloseFailure = 30
$ExitHelperError = 40

function Normalize-PathPrefix([string]$Path) {
    return ([IO.Path]::GetFullPath($Path).TrimEnd('\') + '\').ToLowerInvariant()
}

function Append-Utf8([string]$Path, [string]$Text) {
    $parent = Split-Path -Parent $Path
    if ($parent) { [IO.Directory]::CreateDirectory($parent) | Out-Null }
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::AppendAllText($Path, $Text, $encoding)
}

function Write-Utf8([string]$Path, [string]$Text) {
    $parent = Split-Path -Parent $Path
    if ($parent) { [IO.Directory]::CreateDirectory($parent) | Out-Null }
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($Path, $Text, $encoding)
}

function Log-Line([string]$Message) {
    Append-Utf8 -Path $script:LogPathResolved -Text ("{0} {1}`r`n" -f ([DateTime]::UtcNow.ToString("o")), $Message)
}

function Resolve-OutputPath([string]$Path, [string]$DefaultName) {
    if ([string]::IsNullOrWhiteSpace($Path)) {
        return (Join-Path $LogRoot $DefaultName)
    }
    return $Path
}

function Format-UtcTimestamp([DateTime]$Date) {
    return $Date.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
}

function Convert-CimDate([object]$Value) {
    if ($null -eq $Value) {
        return $null
    }
    if ($Value -is [DateTime]) {
        return ([DateTime]$Value).ToUniversalTime()
    }
    try {
        return ([System.Management.ManagementDateTimeConverter]::ToDateTime([string]$Value)).ToUniversalTime()
    }
    catch {
        return $null
    }
}

function Test-UnderRookRoot([string]$ExecutablePath) {
    if ([string]::IsNullOrWhiteSpace($ExecutablePath)) {
        return $false
    }
    try {
        $fullPath = [IO.Path]::GetFullPath($ExecutablePath).ToLowerInvariant()
        return $fullPath.StartsWith($script:RookRootPrefix)
    }
    catch {
        return $false
    }
}

function Test-ParentCreationTimeValid([object]$Child, [object]$Parent) {
    if ($null -eq $Child -or $null -eq $Parent) {
        return $false
    }
    if ($null -eq $Child.CreationDateUtc -or $null -eq $Parent.CreationDateUtc) {
        return $false
    }
    return ([DateTime]$Parent.CreationDateUtc -le [DateTime]$Child.CreationDateUtc)
}

function Get-ProcessSnapshot {
    try {
        $rawProcesses = Get-CimInstance Win32_Process -ErrorAction Stop |
            Select-Object ProcessId, ParentProcessId, ExecutablePath, CommandLine, CreationDate
    }
    catch {
        throw ("Failed to enumerate Win32_Process: {0}" -f $_.Exception.Message)
    }

    $snapshot = @()
    foreach ($process in $rawProcesses) {
        $creationDate = Convert-CimDate $process.CreationDate
        $creationText = ''
        if ($null -ne $creationDate) {
            $creationText = Format-UtcTimestamp $creationDate
        }

        $executablePath = ''
        if ($null -ne $process.ExecutablePath) {
            $executablePath = [string]$process.ExecutablePath
        }

        $commandLine = ''
        if ($null -ne $process.CommandLine) {
            $commandLine = [string]$process.CommandLine
        }

        $snapshot += [pscustomobject]@{
            ProcessId = [int]$process.ProcessId
            ParentProcessId = [int]$process.ParentProcessId
            ExecutablePath = $executablePath
            CommandLine = $commandLine
            CreationDateUtc = $creationDate
            CreationDateText = $creationText
            IsMatched = (Test-UnderRookRoot $executablePath)
        }
    }
    return $snapshot
}

function New-ProcessIndexes([object[]]$Processes) {
    $byPid = @{}
    $byParentPid = @{}
    foreach ($process in $Processes) {
        $byPid[[int]$process.ProcessId] = $process
        $parentPid = [int]$process.ParentProcessId
        if (-not $byParentPid.ContainsKey($parentPid)) {
            $byParentPid[$parentPid] = @()
        }
        $byParentPid[$parentPid] += $process
    }
    return [pscustomobject]@{
        ByPid = $byPid
        ByParentPid = $byParentPid
    }
}

function Get-LogicalServerRoots([object[]]$Processes, [hashtable]$ByPid) {
    $roots = @()
    foreach ($process in ($Processes | Where-Object { $_.IsMatched })) {
        $parent = $null
        if ($ByPid.ContainsKey([int]$process.ParentProcessId)) {
            $parent = $ByPid[[int]$process.ParentProcessId]
        }
        if ($null -ne $parent -and $parent.IsMatched -and (Test-ParentCreationTimeValid $process $parent)) {
            continue
        }
        $roots += $process
    }
    return $roots
}

function Get-OwnerName([object]$Root, [hashtable]$ByPid) {
    $parent = $null
    if ($ByPid.ContainsKey([int]$Root.ParentProcessId)) {
        $parent = $ByPid[[int]$Root.ParentProcessId]
    }
    if ($null -eq $parent -or -not (Test-ParentCreationTimeValid $Root $parent)) {
        return 'Unknown'
    }

    $basename = [IO.Path]::GetFileName($parent.ExecutablePath)
    if ([string]::IsNullOrWhiteSpace($basename)) {
        return 'Unknown'
    }

    switch ($basename.ToLowerInvariant()) {
        'claude.exe' { return 'Claude' }
        'codex.exe' { return 'Codex' }
        default { return $basename }
    }
}

function Format-OwnerPhrase([object[]]$Owners) {
    if ($Owners.Count -eq 0) {
        return 'unknown tools'
    }
    if ($Owners.Count -eq 1) {
        return [string]$Owners[0]
    }
    if ($Owners.Count -eq 2) {
        return ("{0} and {1}" -f $Owners[0], $Owners[1])
    }
    $leading = $Owners[0..($Owners.Count - 2)] -join ', '
    return ("{0}, and {1}" -f $leading, $Owners[$Owners.Count - 1])
}

function New-PreflightMessage([int]$ServerCount, [object[]]$Owners) {
    if ($ServerCount -eq 0) {
        return 'Rook Setup found no running Rook agent server(s).'
    }

    $ownerPhrase = Format-OwnerPhrase $Owners
    return ("Rook Setup found {0} running Rook agent server(s) started by {1}.`r`n`r`nSetup will close them now so Rook can be updated. Your AI tools will reconnect after installation." -f $ServerCount, $ownerPhrase)
}

function New-ProcessSummary([object]$Root, [string]$Owner) {
    return [pscustomobject]@{
        process_id = [int]$Root.ProcessId
        parent_process_id = [int]$Root.ParentProcessId
        executable_path = [string]$Root.ExecutablePath
        command_line = [string]$Root.CommandLine
        creation_date_utc = [string]$Root.CreationDateText
        owner = $Owner
    }
}

function New-PreflightSummary([object[]]$Roots, [hashtable]$ByPid) {
    $rootRecords = @()
    foreach ($root in $Roots) {
        $owner = Get-OwnerName -Root $root -ByPid $ByPid
        $rootRecords += [pscustomobject]@{
            Root = $root
            Owner = $owner
        }
    }

    $owners = @()
    foreach ($record in $rootRecords) {
        if ($owners -notcontains $record.Owner) {
            $owners += $record.Owner
        }
    }
    $owners = @($owners | Sort-Object)
    $serverCount = @($rootRecords).Count
    $message = New-PreflightMessage -ServerCount $serverCount -Owners $owners

    $processes = @()
    foreach ($record in $rootRecords) {
        $processes += (New-ProcessSummary -Root $record.Root -Owner $record.Owner)
    }

    return [pscustomobject]@{
        conflicts_found = ($serverCount -gt 0)
        server_count = $serverCount
        owners = $owners
        processes = $processes
        message = $message
    }
}

function New-EmptyPreflightSummary {
    return [pscustomobject]@{
        conflicts_found = $false
        server_count = 0
        owners = @()
        processes = @()
        message = (New-PreflightMessage -ServerCount 0 -Owners @())
    }
}

function New-RunSummary([object]$Preflight, [int]$ClosedProcessCount, [string]$RunOutcome) {
    return [pscustomobject]@{
        schema_version = 1
        setup_version = $SetupVersion
        run_start_utc = $script:RunStartUtc
        phase_reached = 'preflight'
        preflight = $Preflight
        closed_process_count = $ClosedProcessCount
        outcome = $RunOutcome
    }
}

function Save-Summary([object]$Summary) {
    $json = $Summary | ConvertTo-Json -Depth 8
    Write-Utf8 -Path $script:SummaryPathResolved -Text ($json + "`r`n")
}

function Read-SummaryOrDefault {
    if (Test-Path $script:SummaryPathResolved) {
        try {
            return (Get-Content -Path $script:SummaryPathResolved -Raw | ConvertFrom-Json)
        }
        catch {
            Log-Line ("summary_read_failed path={0} error={1}" -f $script:SummaryPathResolved, $_.Exception.Message)
        }
    }
    return (New-RunSummary -Preflight (New-EmptyPreflightSummary) -ClosedProcessCount 0 -RunOutcome 'preflight-not-run')
}

function Write-InnoSummary([object]$Preflight) {
    $conflicts = 'false'
    if ($Preflight.conflicts_found) {
        $conflicts = 'true'
    }

    $message = [string]$Preflight.message
    $message = $message -replace "`r`n", '\r\n'
    $lines = @(
        ("conflicts_found={0}" -f $conflicts),
        ("server_count={0}" -f $Preflight.server_count),
        ("owners={0}" -f (@($Preflight.owners) -join ', ')),
        ("message={0}" -f $message)
    )
    Write-Utf8 -Path $script:InnoSummaryPathResolved -Text (($lines -join "`r`n") + "`r`n")
}

function Invoke-EnumerateMode {
    $previousLog = Join-Path $LogRoot 'post_install.prev.log'
    if (Test-Path $script:LogPathResolved) {
        Move-Item -Path $script:LogPathResolved -Destination $previousLog -Force
    }

    Log-Line ("mode=enumerate setup_version={0} rook_root={1}" -f $SetupVersion, $RookRoot)

    try {
        $processes = @(Get-ProcessSnapshot)
    }
    catch {
        Log-Line ("enumeration_failed error={0}" -f $_.Exception.Message)
        return $ExitEnumerationFailure
    }

    $indexes = New-ProcessIndexes $processes
    $roots = @(Get-LogicalServerRoots -Processes $processes -ByPid $indexes.ByPid)
    $preflight = New-PreflightSummary -Roots $roots -ByPid $indexes.ByPid
    $summary = New-RunSummary -Preflight $preflight -ClosedProcessCount 0 -RunOutcome 'preflight-enumerated'

    Save-Summary $summary
    Write-InnoSummary $preflight
    Log-Line ("enumeration_complete conflicts_found={0} server_count={1}" -f $preflight.conflicts_found.ToString().ToLowerInvariant(), $preflight.server_count)

    if ($preflight.conflicts_found) {
        return $ExitNotQuiet
    }
    return $ExitQuiet
}

function Get-DescendantClosure([object[]]$Roots, [hashtable]$ByParentPid) {
    $stack = New-Object System.Collections.ArrayList
    foreach ($root in $Roots) {
        [void]$stack.Add([pscustomobject]@{
            Process = $root
            Depth = 0
        })
    }

    $seen = @{}
    $targets = @{}
    while ($stack.Count -gt 0) {
        $index = $stack.Count - 1
        $node = $stack[$index]
        $stack.RemoveAt($index)

        $process = $node.Process
        $processId = [int]$process.ProcessId
        if ($seen.ContainsKey($processId)) {
            continue
        }
        $seen[$processId] = $true
        $targets[$processId] = $node

        if (-not $ByParentPid.ContainsKey($processId)) {
            continue
        }

        foreach ($child in $ByParentPid[$processId]) {
            if (Test-ParentCreationTimeValid -Child $child -Parent $process) {
                [void]$stack.Add([pscustomobject]@{
                    Process = $child
                    Depth = ([int]$node.Depth + 1)
                })
            }
        }
    }

    return @($targets.Values | Sort-Object -Property @{ Expression = { $_.Depth }; Descending = $true }, @{ Expression = { $_.Process.ProcessId }; Descending = $true })
}

function Get-ProcessIdentityKey([object]$Process) {
    $creationText = ''
    if ($null -ne $Process.CreationDateText) {
        $creationText = [string]$Process.CreationDateText
    }
    return ("{0}|{1}" -f ([int]$Process.ProcessId), $creationText)
}

function New-FailedCloseRecord([object]$Process) {
    return [pscustomobject]@{
        ProcessId = [int]$Process.ProcessId
        CreationDateUtc = $Process.CreationDateUtc
        CreationDateText = [string]$Process.CreationDateText
    }
}

function Test-LiveProcessIdentityMatches([object]$Process) {
    $processId = [int]$Process.ProcessId

    if ($null -eq $Process.CreationDateUtc) {
        return ($null -ne (Get-Process -Id $processId -ErrorAction SilentlyContinue))
    }

    $liveProcess = Get-CimInstance Win32_Process -Filter ("ProcessId = {0}" -f $processId) -ErrorAction Stop |
        Select-Object -First 1
    if ($null -eq $liveProcess) {
        return $false
    }

    $liveCreationDate = Convert-CimDate $liveProcess.CreationDate
    if ($null -eq $liveCreationDate) {
        return $false
    }

    $creationDelta = ([DateTime]$liveCreationDate) - ([DateTime]$Process.CreationDateUtc)
    return ([Math]::Abs($creationDelta.TotalMilliseconds) -le 1)
}

function Add-FailedCloseRecord([hashtable]$FailedCloseRecords, [object]$Process) {
    $record = New-FailedCloseRecord $Process
    $FailedCloseRecords[(Get-ProcessIdentityKey $record)] = $record
}

function Get-LiveFailedCloseRecords([hashtable]$FailedCloseRecords) {
    $liveRecords = @()
    foreach ($record in $FailedCloseRecords.Values) {
        try {
            if (Test-LiveProcessIdentityMatches $record) {
                $liveRecords += $record
            }
        }
        catch {
            $liveRecords += $record
            Log-Line ("identity_recheck_failed pid={0} creation_date_utc={1} error={2}" -f $record.ProcessId, $record.CreationDateText, $_.Exception.Message)
        }
    }
    return @($liveRecords | Sort-Object -Property ProcessId, CreationDateText)
}

function Format-ProcessIdentities([object[]]$Records) {
    $items = @()
    foreach ($record in $Records) {
        if ([string]::IsNullOrWhiteSpace($record.CreationDateText)) {
            $items += [string]$record.ProcessId
        }
        else {
            $items += ("{0}@{1}" -f $record.ProcessId, $record.CreationDateText)
        }
    }
    return ($items -join ',')
}

function Invoke-CloseMode {
    Log-Line ("mode=close setup_version={0} rook_root={1}" -f $SetupVersion, $RookRoot)

    $attemptsByIdentity = @{}
    $failedCloseRecords = @{}
    $closedProcessCount = 0
    $closeFailed = $false
    $lastPreflight = New-EmptyPreflightSummary

    for ($round = 1; $round -le 3; $round++) {
        try {
            $processes = @(Get-ProcessSnapshot)
        }
        catch {
            Log-Line ("enumeration_failed round={0} error={1}" -f $round, $_.Exception.Message)
            return $ExitEnumerationFailure
        }

        $indexes = New-ProcessIndexes $processes
        $roots = @(Get-LogicalServerRoots -Processes $processes -ByPid $indexes.ByPid)
        $lastPreflight = New-PreflightSummary -Roots $roots -ByPid $indexes.ByPid
        if ($roots.Count -eq 0) {
            $liveFailedCloseRecords = @(Get-LiveFailedCloseRecords -FailedCloseRecords $failedCloseRecords)
            if ($liveFailedCloseRecords.Count -gt 0) {
                $summary = New-RunSummary -Preflight $lastPreflight -ClosedProcessCount $closedProcessCount -RunOutcome 'preflight-close-failed'
                Save-Summary $summary
                Write-InnoSummary $lastPreflight
                Log-Line ("close_failed remaining_failed_processes={0} closed_process_count={1}" -f (Format-ProcessIdentities $liveFailedCloseRecords), $closedProcessCount)
                return $ExitCloseFailure
            }
            $summary = New-RunSummary -Preflight $lastPreflight -ClosedProcessCount $closedProcessCount -RunOutcome 'preflight-closed'
            Save-Summary $summary
            Write-InnoSummary $lastPreflight
            Log-Line ("close_complete closed_process_count={0}" -f $closedProcessCount)
            return $ExitQuiet
        }

        $targets = @(Get-DescendantClosure -Roots $roots -ByParentPid $indexes.ByParentPid)
        foreach ($target in $targets) {
            $processId = [int]$target.Process.ProcessId
            $identityKey = Get-ProcessIdentityKey $target.Process
            if (-not $attemptsByIdentity.ContainsKey($identityKey)) {
                $attemptsByIdentity[$identityKey] = 0
            }
            if ([int]$attemptsByIdentity[$identityKey] -ge 3) {
                continue
            }

            $attemptsByIdentity[$identityKey] = [int]$attemptsByIdentity[$identityKey] + 1
            try {
                if (-not (Test-LiveProcessIdentityMatches $target.Process)) {
                    Log-Line ("skip_stop_identity_changed pid={0} creation_date_utc={1} attempt={2}" -f $processId, $target.Process.CreationDateText, $attemptsByIdentity[$identityKey])
                    continue
                }
            }
            catch {
                Log-Line ("skip_stop_identity_recheck_failed pid={0} creation_date_utc={1} attempt={2} error={3}" -f $processId, $target.Process.CreationDateText, $attemptsByIdentity[$identityKey], $_.Exception.Message)
                continue
            }

            try {
                Stop-Process -Id $processId -Force -ErrorAction Stop
                $closedProcessCount++
                Log-Line ("stop_process pid={0} creation_date_utc={1} attempt={2} depth={3}" -f $processId, $target.Process.CreationDateText, $attemptsByIdentity[$identityKey], $target.Depth)
            }
            catch {
                Start-Sleep -Milliseconds 50
                try {
                    $stillSameProcess = Test-LiveProcessIdentityMatches $target.Process
                }
                catch {
                    $stillSameProcess = $true
                    Log-Line ("identity_recheck_failed pid={0} creation_date_utc={1} error={2}" -f $processId, $target.Process.CreationDateText, $_.Exception.Message)
                }

                if ($stillSameProcess) {
                    $closeFailed = $true
                    Add-FailedCloseRecord -FailedCloseRecords $failedCloseRecords -Process $target.Process
                    Log-Line ("stop_process_failed pid={0} creation_date_utc={1} attempt={2} error={3}" -f $processId, $target.Process.CreationDateText, $attemptsByIdentity[$identityKey], $_.Exception.Message)
                }
                else {
                    Log-Line ("stop_process_already_exited pid={0} creation_date_utc={1} attempt={2}" -f $processId, $target.Process.CreationDateText, $attemptsByIdentity[$identityKey])
                }
            }
        }

        Start-Sleep -Milliseconds 250
    }

    try {
        $processes = @(Get-ProcessSnapshot)
    }
    catch {
        Log-Line ("enumeration_failed final_check error={0}" -f $_.Exception.Message)
        return $ExitEnumerationFailure
    }

    $indexes = New-ProcessIndexes $processes
    $roots = @(Get-LogicalServerRoots -Processes $processes -ByPid $indexes.ByPid)
    $lastPreflight = New-PreflightSummary -Roots $roots -ByPid $indexes.ByPid
    if ($roots.Count -gt 0) {
        $remainingTargets = @(Get-DescendantClosure -Roots $roots -ByParentPid $indexes.ByParentPid)
        foreach ($target in $remainingTargets) {
            $identityKey = Get-ProcessIdentityKey $target.Process
            if ($attemptsByIdentity.ContainsKey($identityKey) -and [int]$attemptsByIdentity[$identityKey] -ge 3 -and -not $failedCloseRecords.ContainsKey($identityKey)) {
                Add-FailedCloseRecord -FailedCloseRecords $failedCloseRecords -Process $target.Process
                Log-Line ("stop_process_still_alive pid={0} creation_date_utc={1} attempts={2} depth={3}" -f ([int]$target.Process.ProcessId), $target.Process.CreationDateText, $attemptsByIdentity[$identityKey], $target.Depth)
            }
        }
    }
    $liveFailedCloseRecords = @(Get-LiveFailedCloseRecords -FailedCloseRecords $failedCloseRecords)
    $closeFailed = $closeFailed -or ($liveFailedCloseRecords.Count -gt 0)
    $runOutcome = 'preflight-not-quiet'
    if ($closeFailed) {
        $runOutcome = 'preflight-close-failed'
    }
    elseif ($roots.Count -eq 0) {
        $runOutcome = 'preflight-closed'
    }
    $summary = New-RunSummary -Preflight $lastPreflight -ClosedProcessCount $closedProcessCount -RunOutcome $runOutcome
    Save-Summary $summary
    Write-InnoSummary $lastPreflight

    if ($roots.Count -eq 0) {
        if ($liveFailedCloseRecords.Count -gt 0) {
            Log-Line ("close_failed remaining_failed_processes={0} closed_process_count={1}" -f (Format-ProcessIdentities $liveFailedCloseRecords), $closedProcessCount)
            return $ExitCloseFailure
        }
        Log-Line ("close_complete closed_process_count={0}" -f $closedProcessCount)
        return $ExitQuiet
    }

    if ($liveFailedCloseRecords.Count -gt 0) {
        Log-Line ("close_failed remaining_failed_processes={0} remaining_server_count={1} closed_process_count={2}" -f (Format-ProcessIdentities $liveFailedCloseRecords), $roots.Count, $closedProcessCount)
        return $ExitCloseFailure
    }
    if ($closeFailed) {
        Log-Line ("close_failed remaining_server_count={0} closed_process_count={1}" -f $roots.Count, $closedProcessCount)
        return $ExitCloseFailure
    }
    Log-Line ("close_not_quiet remaining_server_count={0} close_failed=false" -f $roots.Count)
    return $ExitNotQuiet
}

function Invoke-RecordOutcomeMode {
    $summary = Read-SummaryOrDefault
    if ([string]::IsNullOrWhiteSpace($Outcome)) {
        $summary.outcome = 'unknown'
        Log-Line 'outcome=unknown'
    }
    else {
        $summary.outcome = $Outcome
        Log-Line ("outcome={0}" -f $Outcome)
    }
    Save-Summary $summary
    return $ExitQuiet
}

try {
    $validModes = @('enumerate', 'close', 'record-outcome')
    if ([string]::IsNullOrWhiteSpace($LogRoot)) {
        throw 'LogRoot is required.'
    }
    [IO.Directory]::CreateDirectory($LogRoot) | Out-Null
    $script:SummaryPathResolved = Resolve-OutputPath -Path $SummaryPath -DefaultName 'post_install_summary.json'
    $script:InnoSummaryPathResolved = Resolve-OutputPath -Path $InnoSummaryPath -DefaultName 'preflight-summary.txt'
    $script:LogPathResolved = Resolve-OutputPath -Path $LogPath -DefaultName 'post_install.log'
    if ([string]::IsNullOrWhiteSpace($Mode)) {
        throw 'Mode is required.'
    }
    if ($validModes -notcontains $Mode) {
        throw ("Invalid mode: {0}" -f $Mode)
    }
    if ([string]::IsNullOrWhiteSpace($RookRoot)) {
        throw 'RookRoot is required.'
    }
    $script:RookRootPrefix = Normalize-PathPrefix $RookRoot
    $script:RunStartUtc = Format-UtcTimestamp ([DateTime]::UtcNow)

    switch ($Mode) {
        'enumerate' { exit (Invoke-EnumerateMode) }
        'close' { exit (Invoke-CloseMode) }
        'record-outcome' { exit (Invoke-RecordOutcomeMode) }
    }
}
catch {
    try {
        if (-not [string]::IsNullOrWhiteSpace($script:LogPathResolved)) {
            Log-Line ("helper_error error={0}" -f $_.Exception.Message)
        }
    }
    catch {
    }
    exit $ExitHelperError
}
