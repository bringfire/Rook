param(
    [string]$ArtifactDirectory,
    [string]$CandidateIdentityPath,
    [string]$CandidateSidecarPath,
    [string]$EvidenceDirectory,
    [string]$RhinoExe,
    [switch]$VerifyEvidenceOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:ContainmentValidatorPath = $MyInvocation.MyCommand.Path
$script:ContainmentControlledExactNames = @(
    'PYTHONPATH',
    'PYTHONHOME',
    'PYTHONUSERBASE',
    'PYTHONNOUSERSITE',
    'DSPY_MODEL',
    'DSPY_CACHEDIR',
    'CHIRP_HOME'
)
$script:ContainmentProfiles = @('full', 'lean', 'readonly')
$script:ContainmentAcceptanceFileName = 'containment-acceptance.json'
$script:ContainmentFailureFileName = 'containment-failure.json'
$script:ContainmentHoldFileName = 'containment-hold.json'
$script:ContainmentContainedNames = @(
    'gh_execute_intent',
    'rhino_execute_intent',
    'plan_and_execute',
    'spawn_agent',
    'gh_explore_workflow',
    'gh_replay_recipe'
)
$script:ContainmentStageNames = @(
    'recording_attempt', 'format_result', 'argument_access', 'profile',
    'capability', 'knowledge', 'model', 'target', 'http', 'host',
    'observation', 'adaptation', 'receipt'
)
$script:ContainmentPatchpointNames = @(
    'rook.tool_lifecycle_runtime._record_containment_denial',
    'rook.server._format_tool_result',
    'rook.server.validate_arguments',
    'mcp.server.lowlevel.server.Server._get_cached_tool_definition',
    'mcp.server.lowlevel.server.jsonschema.validate',
    'rook.server.tool_blocked',
    'rook.server._get_capability_index',
    'rook.server.inject_knowledge',
    'rook.agent.base_agent.RookAgent._call_model',
    'rook.server.targeting.policy_for_tool',
    'httpx.AsyncClient.get',
    'httpx.AsyncClient.post',
    'httpx.AsyncClient.request',
    'rook.bootstrap.executor.urllib.request.urlopen',
    'rook.server.call_rhino',
    'rook.server._record_observation',
    'rook.server.get_phase_tracker',
    'rook.server.build_script_receipt'
)
$script:ContainmentInternalSeams = @(
    'server._call_tool_dispatch',
    'server._mcp_tool_executor',
    'ToolDispatcher.dispatch',
    'ToolDispatcher._dispatch_inner',
    'ToolDispatcher._call_local',
    'ToolDispatcher._dispatch_with_knowledge',
    'RookAgent._run_loop',
    'RookAgent._execute_tool',
    'RookAgent._execute_local_tool',
    'ChatRunner.run_turn',
    'rook.agent.plan_graph_live.apply_live_producer_node',
    'BootstrapRunner.run_test',
    'BootstrapRunner._mock_executor',
    'bootstrap.HttpExecutor.execute',
    'bootstrap.create_mock_executor.callable',
    'learning.create_tool_executor.callable',
    'Investigator.investigate_tool',
    'Investigator.investigate_gap',
    'Investigator.investigate_workflow',
    'Investigator._run_experiment',
    'HybridInvestigator.investigate_tool',
    'HybridInvestigator.investigate_gap',
    'LearningSession.run_investigation_cycle.tool_target',
    'explorer.HttpExecutor.execute',
    'explorer.HttpExecutor.execute_sync',
    'explorer.MockExecutor.execute',
    'explorer.MockExecutor.execute_sync'
)
$script:ContainmentLifecycle = [ordered]@{
    gh_execute_intent = [ordered]@{
        disposition = 'retired'
        recovery = 'Rediscover the current Grasshopper surface; inspect state and components, then use explicit gh_edit or supported script tools and verify solve state, outputs, and errors.'
    }
    rhino_execute_intent = [ordered]@{
        disposition = 'retired'
        recovery = 'Rediscover the current Rhino surface; use explicit typed Rhino tools, rhino_execute, or a sanctioned preflighted rhino_command, then verify the host result.'
    }
    plan_and_execute = [ordered]@{
        disposition = 'suspended'
        recovery = 'Rediscover the current surface and perform bounded steps through explicit admitted tools; autonomous plan execution is suspended.'
    }
    spawn_agent = [ordered]@{
        disposition = 'suspended'
        recovery = 'Rediscover the current surface and use the connected model to call explicit admitted tools directly; autonomous agent spawning is suspended.'
    }
    gh_explore_workflow = [ordered]@{
        disposition = 'suspended'
        recovery = 'Rediscover the current Grasshopper inspection surface and use explicit snapshot, component, or knowledge tools; semantic workflow exploration is suspended.'
    }
    gh_replay_recipe = [ordered]@{
        disposition = 'suspended'
        recovery = 'Rediscover the current Grasshopper surface and apply reviewed explicit gh_edit operations; recipe replay is suspended.'
    }
}
$script:ContainmentScenarioFailureLabels = @(
    'runtime_origin_invalid',
    'launch_failed',
    'readiness_failed',
    'fixture_invalid',
    'preflight_blocked',
    'authorization_rejected',
    'state_drift',
    'mutation_failed',
    'verification_failed',
    'ownership_ambiguous',
    'restoration_failed',
    'telemetry_changed',
    'cleanup_failed'
)
$script:ContainmentScenarioTools = [ordered]@{
    rhino = @(
        'rhino_ping', 'rhino_document', 'rhino_objects', 'rhino_geometry',
        'rhino_document_ops', 'rhino_create', 'rhino_execute', 'rhino_delete'
    )
    grasshopper = @(
        'rhino_ping', 'rhino_document', 'rhino_command', 'gh_status',
        'gh_document_open', 'gh_library', 'gh_snapshot', 'gh_edit',
        'gh_errors', 'gh_undo'
    )
}
$script:ContainmentAuthorizationLabels = [ordered]@{
    rhino = 'Rook containment Rhino scratch document'
    grasshopper = 'Rook containment Grasshopper scratch definition'
}
$script:ContainmentAuthorizationDescriptions = [ordered]@{
    rhino = [ordered]@{
        mutation = 'Save the fresh owned Rhino document, create one radius-4 sphere and one marked point using admitted typed and scripted tools.'
        verification = 'Verify exact object identities, names, types, coordinates, sphere radius and bounds, and clean document state.'
        restoration = 'Delete only the two gate-owned objects, save the empty scratch document, close the owned process gracefully, and remove the scratch file and discovery record.'
    }
    grasshopper = [ordered]@{
        mutation = 'Bootstrap Grasshopper in the fresh owned Rhino process, open the packaged empty scratch definition, and create one configured radius slider wired to one built-in Sphere.'
        verification = 'Verify exact component identities, slider settings, wire topology, solved sphere output, and zero Grasshopper errors or warnings.'
        restoration = 'Undo only the gate-owned edit to the declared empty projection, close the owned process, and remove the scratch definition and discovery record.'
    }
}

function ConvertTo-ContainmentCanonicalJson {
    param([AllowNull()][object]$Value)

    if ($null -eq $Value) { return 'null' }
    if ($Value -is [bool]) {
        if ($Value) { return 'true' }
        return 'false'
    }
    if ($Value -is [string] -or $Value -is [char]) {
        return ConvertTo-Json -InputObject ([string]$Value) -Compress
    }
    # Test and pipeline integers can carry a PSObject wrapper in Windows
    # PowerShell, so primitive numbers must precede the custom-object branch.
    if ($Value -is [byte] -or $Value -is [sbyte] -or
        $Value -is [int16] -or $Value -is [uint16] -or
        $Value -is [int32] -or $Value -is [uint32] -or
        $Value -is [int64] -or $Value -is [uint64] -or
        $Value -is [single] -or $Value -is [double] -or
        $Value -is [decimal]) {
        $text = [Convert]::ToString(
            $Value,
            [Globalization.CultureInfo]::InvariantCulture
        )
        if ($text -match 'NaN|Infinity') {
            throw 'non-finite numbers are not canonical JSON'
        }
        return $text
    }
    if ($Value -is [Collections.IDictionary]) {
        [string[]]$keys = @($Value.Keys | ForEach-Object { [string]$_ })
        [Array]::Sort($keys, [StringComparer]::Ordinal)
        $parts = foreach ($key in $keys) {
            (ConvertTo-Json -InputObject $key -Compress) + ':' +
                (ConvertTo-ContainmentCanonicalJson -Value ($Value[$key]))
        }
        return '{' + ($parts -join ',') + '}'
    }
    if ($Value -is [pscustomobject]) {
        $mapping = [ordered]@{}
        foreach ($property in $Value.PSObject.Properties) {
            $mapping[$property.Name] = $property.Value
        }
        return ConvertTo-ContainmentCanonicalJson -Value $mapping
    }
    if ($Value -is [Collections.IEnumerable]) {
        $items = foreach ($item in $Value) {
            ConvertTo-ContainmentCanonicalJson -Value $item
        }
        return '[' + ($items -join ',') + ']'
    }
    throw "unsupported canonical JSON value: $($Value.GetType().FullName)"
}

function Get-ContainmentSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "required file is missing: $Path"
    }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-ContainmentValueSha256 {
    param([AllowNull()][object]$Value)

    $json = ConvertTo-ContainmentCanonicalJson -Value $Value
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($json)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($algorithm.ComputeHash($bytes)) -replace '-', '').ToLowerInvariant()
    }
    finally {
        $algorithm.Dispose()
    }
}

function Test-ContainmentJsonNumber {
    param([AllowNull()][object]$Value)

    return ($Value -is [byte] -or $Value -is [sbyte] -or
        $Value -is [int16] -or $Value -is [uint16] -or
        $Value -is [int32] -or $Value -is [uint32] -or
        $Value -is [int64] -or $Value -is [uint64] -or
        $Value -is [single] -or $Value -is [double] -or $Value -is [decimal])
}

function Test-ContainmentJsonInteger {
    param([AllowNull()][object]$Value)

    return ($Value -is [byte] -or $Value -is [sbyte] -or
        $Value -is [int16] -or $Value -is [uint16] -or
        $Value -is [int32] -or $Value -is [uint32] -or
        $Value -is [int64] -or $Value -is [uint64])
}

function Assert-ContainmentHex {
    param(
        [AllowNull()][object]$Value,
        [int]$Length,
        [string]$Label
    )

    if ($Value -isnot [string]) { throw "$Label must be a string" }
    $text = [string]$Value
    if ($text -cnotmatch "^[0-9a-f]{$Length}$") {
        throw "$Label must be lowercase $Length-hex"
    }
    return $text
}

function Assert-ContainmentExactProperties {
    param(
        [AllowNull()][object]$Value,
        [string[]]$Expected,
        [string]$Label
    )

    if ($null -eq $Value) { throw "$Label is null" }
    [string[]]$actual = if ($Value -is [Collections.IDictionary]) {
        @($Value.Keys | ForEach-Object { [string]$_ })
    }
    else {
        @($Value.PSObject.Properties.Name)
    }
    [Array]::Sort($actual, [StringComparer]::Ordinal)
    [string[]]$wanted = @($Expected)
    [Array]::Sort($wanted, [StringComparer]::Ordinal)
    if ($actual.Count -ne $wanted.Count) {
        throw "$Label property count drift"
    }
    for ($index = 0; $index -lt $wanted.Count; $index++) {
        if ($actual[$index] -cne $wanted[$index]) {
            throw "$Label properties drift"
        }
    }
}

function Assert-ContainmentPathNotReparse {
    param([Parameter(Mandatory = $true)][string]$Path, [string]$Label)

    $full = [IO.Path]::GetFullPath($Path)
    $cursor = $full
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "$Label is reparse-backed: $cursor"
            }
        }
        $parent = Split-Path -Parent $cursor
        if (-not $parent -or $parent -eq $cursor) { break }
        $cursor = $parent
    }
    return $full
}

function Get-ContainmentCanonicalPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [ValidateSet('Leaf', 'Container')][string]$Kind,
        [string]$Label
    )

    if (-not [IO.Path]::IsPathRooted($Path)) {
        throw "$Label must be absolute"
    }
    if (-not (Test-Path -LiteralPath $Path -PathType $Kind)) {
        throw "$Label is missing: $Path"
    }
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    [void](Assert-ContainmentPathNotReparse -Path $resolved -Label $Label)
    return $resolved
}

function Test-ContainmentSamePath {
    param([string]$Left, [string]$Right)

    return [string]::Equals(
        [IO.Path]::GetFullPath($Left),
        [IO.Path]::GetFullPath($Right),
        [StringComparison]::OrdinalIgnoreCase
    )
}

function Resolve-ContainmentOwnedRelativePath {
    param(
        [string]$Root,
        [AllowNull()][object]$RelativePath,
        [ValidateSet('Leaf', 'Container', 'Any')][string]$Kind = 'Any',
        [string]$Label
    )

    $relative = [string]$RelativePath
    if ([string]::IsNullOrWhiteSpace($relative) -or
        [IO.Path]::IsPathRooted($relative) -or
        $relative -match '(^|[\\/])\.\.([\\/]|$)') {
        throw "$Label has an unsafe relative path"
    }
    $rootFull = [IO.Path]::GetFullPath($Root)
    $prefix = $rootFull.TrimEnd('\') + '\'
    $candidate = [IO.Path]::GetFullPath((Join-Path $rootFull $relative))
    if (-not $candidate.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "$Label escapes its owned root"
    }
    [void](Assert-ContainmentPathNotReparse -Path $candidate -Label $Label)
    if ($Kind -eq 'Leaf' -and -not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw "$Label file is missing: $candidate"
    }
    if ($Kind -eq 'Container' -and -not (Test-Path -LiteralPath $candidate -PathType Container)) {
        throw "$Label directory is missing: $candidate"
    }
    return $candidate
}

function Read-ContainmentCanonicalJsonFile {
    param([string]$Path, [string]$Label)

    $canonicalPath = Get-ContainmentCanonicalPath -Path $Path -Kind Leaf -Label $Label
    $bytes = [IO.File]::ReadAllBytes($canonicalPath)
    if ($bytes.Length -ge 3 -and
        $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        throw "$Label contains a UTF-8 BOM"
    }
    try {
        $text = [Text.UTF8Encoding]::new($false, $true).GetString($bytes)
        $record = $text | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        throw "$Label is malformed JSON: $($_.Exception.Message)"
    }
    if ($text -cne (ConvertTo-ContainmentCanonicalJson -Value $record)) {
        throw "$Label is not canonical JSON"
    }
    return $record
}

function Read-ContainmentCanonicalJsonLfFile {
    param([string]$Path, [string]$Label)

    $canonicalPath = Get-ContainmentCanonicalPath -Path $Path -Kind Leaf -Label $Label
    $bytes = [IO.File]::ReadAllBytes($canonicalPath)
    if ($bytes.Length -lt 2 -or $bytes[$bytes.Length - 1] -ne 0x0A -or
        ($bytes.Length -ge 2 -and $bytes[$bytes.Length - 2] -eq 0x0D) -or
        ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)) {
        throw "$Label must be canonical UTF-8 JSON with one final LF"
    }
    try {
        $text = [Text.UTF8Encoding]::new($false, $true).GetString($bytes)
        $body = $text.Substring(0, $text.Length - 1)
        if ($body.Contains("`r") -or $body.Contains("`n")) {
            throw "$Label must contain one compact JSON record"
        }
        $record = $body | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        throw "$Label is malformed JSON: $($_.Exception.Message)"
    }
    if ($body -cne (ConvertTo-ContainmentCanonicalJson -Value $record)) {
        throw "$Label is not canonical JSON"
    }
    return $record
}

function Test-ContainmentCanonicalEqual {
    param([AllowNull()][object]$Left, [AllowNull()][object]$Right)
    return ((ConvertTo-ContainmentCanonicalJson -Value $Left) -ceq
        (ConvertTo-ContainmentCanonicalJson -Value $Right))
}

function Write-ContainmentCreateNewBytes {
    param([string]$Path, [byte[]]$Bytes)

    $parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        throw "owned output parent is missing: $parent"
    }
    $stream = [IO.File]::Open(
        $Path,
        [IO.FileMode]::CreateNew,
        [IO.FileAccess]::Write,
        [IO.FileShare]::None
    )
    try {
        $stream.Write($Bytes, 0, $Bytes.Length)
        $stream.Flush($true)
    }
    finally {
        $stream.Dispose()
    }
}

function Write-CanonicalJsonPair {
    param(
        [string]$Path,
        [string]$SidecarPath,
        [AllowNull()][object]$Value
    )

    if ((Test-Path -LiteralPath $Path) -or (Test-Path -LiteralPath $SidecarPath)) {
        throw 'canonical JSON evidence pair path already exists'
    }
    $pathCreated = $false
    $sidecarCreated = $false
    try {
        $json = ConvertTo-ContainmentCanonicalJson -Value $Value
        Write-ContainmentCreateNewBytes -Path $Path -Bytes ([Text.UTF8Encoding]::new($false).GetBytes($json))
        $pathCreated = $true
        $digest = Get-ContainmentSha256 -Path $Path
        $sidecar = "$digest  $([IO.Path]::GetFileName($Path))`n"
        Write-ContainmentCreateNewBytes -Path $SidecarPath -Bytes ([Text.Encoding]::ASCII.GetBytes($sidecar))
        $sidecarCreated = $true
        return [pscustomobject]@{
            Path = $Path
            Sha256 = $digest
            SidecarPath = $SidecarPath
            SidecarSha256 = Get-ContainmentSha256 -Path $SidecarPath
        }
    }
    catch {
        if ($sidecarCreated -and (Test-Path -LiteralPath $SidecarPath -PathType Leaf)) {
            Remove-Item -LiteralPath $SidecarPath -Force -ErrorAction SilentlyContinue
        }
        if ($pathCreated -and (Test-Path -LiteralPath $Path -PathType Leaf)) {
            Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
        }
        throw
    }
}

function Assert-ContainmentSidecar {
    param(
        [string]$SidecarPath,
        [string]$TargetPath,
        [switch]$DigestOnly,
        [string]$Label
    )

    $sidecar = Get-ContainmentCanonicalPath -Path $SidecarPath -Kind Leaf -Label "$Label sidecar"
    $target = Get-ContainmentCanonicalPath -Path $TargetPath -Kind Leaf -Label $Label
    $digest = Get-ContainmentSha256 -Path $target
    $expected = "$digest`n"
    if (-not $DigestOnly) {
        $expected = "$digest  $([IO.Path]::GetFileName($target))`n"
    }
    $actual = [Text.Encoding]::ASCII.GetString([IO.File]::ReadAllBytes($sidecar))
    if ($actual -cne $expected) {
        throw "$Label sidecar hash mismatch"
    }
    return [pscustomobject]@{
        TargetSha256 = $digest
        SidecarSha256 = Get-ContainmentSha256 -Path $sidecar
    }
}

function ConvertTo-ProcessArgument {
    param([AllowNull()][AllowEmptyString()][string]$Value)

    if ($null -eq $Value -or $Value.Length -eq 0) {
        return '""'
    }
    if ($Value -notmatch '[\s"]') {
        return $Value
    }
    $escaped = $Value -replace '(\\*)"', '$1$1\"'
    $escaped = $escaped -replace '(\\+)$', '$1$1'
    return '"' + $escaped + '"'
}

function Test-ContainmentControlledName {
    param([string]$Name)

    foreach ($exact in $script:ContainmentControlledExactNames) {
        if ([string]::Equals($Name, $exact, [StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }
    return $Name.StartsWith('ROOK_', [StringComparison]::OrdinalIgnoreCase)
}

function Set-ContainmentProcessPolicy {
    param(
        [Diagnostics.ProcessStartInfo]$ProcessInfo,
        [AllowNull()][Collections.IDictionary]$Policy
    )

    $removed = New-Object Collections.Generic.List[string]
    $final = New-Object Collections.Generic.List[string]
    if ($null -eq $Policy -or [string]$Policy.Mode -eq 'raw') {
        return [pscustomobject]@{ Removed = @(); Final = @() }
    }

    foreach ($keyObject in @($ProcessInfo.EnvironmentVariables.Keys)) {
        $key = [string]$keyObject
        if (Test-ContainmentControlledName -Name $key) {
            $ProcessInfo.EnvironmentVariables.Remove($key)
            $removed.Add($key)
        }
    }

    $values = [ordered]@{}
    if ($Policy.Contains('Values') -and $null -ne $Policy.Values) {
        foreach ($key in $Policy.Values.Keys) {
            $name = [string]$key
            if (-not (Test-ContainmentControlledName -Name $name)) {
                throw "process policy attempted to add an uncontrolled name: $name"
            }
            $values[$name] = [string]$Policy.Values[$key]
        }
    }
    foreach ($name in $values.Keys) {
        if ([string]::IsNullOrEmpty([string]$values[$name])) {
            throw "process policy value may not be empty: $name"
        }
        $ProcessInfo.EnvironmentVariables[[string]$name] = [string]$values[$name]
    }
    foreach ($keyObject in @($ProcessInfo.EnvironmentVariables.Keys)) {
        $key = [string]$keyObject
        if (Test-ContainmentControlledName -Name $key) {
            $final.Add($key)
        }
    }
    [string[]]$removedSorted = @($removed | Sort-Object -CaseSensitive -Unique)
    [string[]]$finalSorted = @($final | Sort-Object -CaseSensitive -Unique)
    return [pscustomobject]@{ Removed = $removedSorted; Final = $finalSorted }
}

function New-ContainmentProcessStartInfo {
    param(
        [string]$Executable,
        [string[]]$Arguments,
        [string]$DiagnosticDirectory,
        [AllowNull()][Collections.IDictionary]$Policy,
        [switch]$InteractiveInput
    )

    $executablePath = Get-ContainmentCanonicalPath -Path $Executable -Kind Leaf -Label 'child executable'
    $diagnostics = Get-ContainmentCanonicalPath -Path $DiagnosticDirectory -Kind Container -Label 'diagnostic directory'
    $id = [guid]::NewGuid().ToString('N')
    $workingDirectory = Join-Path $env:TEMP "rook-containment-child-$id"
    [IO.Directory]::CreateDirectory($workingDirectory) | Out-Null
    [void](Assert-ContainmentPathNotReparse -Path $workingDirectory -Label 'child working directory')

    $processInfo = [Diagnostics.ProcessStartInfo]::new()
    $processInfo.FileName = $executablePath
    $processInfo.Arguments = (@($Arguments) | ForEach-Object { ConvertTo-ProcessArgument -Value $_ }) -join ' '
    $processInfo.UseShellExecute = $false
    $processInfo.CreateNoWindow = $true
    $processInfo.RedirectStandardOutput = $true
    $processInfo.RedirectStandardError = $true
    $processInfo.RedirectStandardInput = $true
    $processInfo.WorkingDirectory = $workingDirectory
    $policyProjection = Set-ContainmentProcessPolicy -ProcessInfo $processInfo -Policy $Policy
    return [pscustomobject]@{
        ProcessInfo = $processInfo
        WorkingDirectory = $workingDirectory
        StdoutPath = Join-Path $diagnostics "child-$id.stdout.log"
        StderrPath = Join-Path $diagnostics "child-$id.stderr.log"
        Removed = $policyProjection.Removed
        Final = $policyProjection.Final
        Interactive = [bool]$InteractiveInput
    }
}

function Get-ContainmentBoundedFileText {
    param([string]$Path, [int]$MaximumBytes = 8192)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return '' }
    $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try {
        $count = [Math]::Min([long]$MaximumBytes, $stream.Length)
        $buffer = New-Object byte[] ([int]$count)
        $read = $stream.Read($buffer, 0, $buffer.Length)
        return [Text.UTF8Encoding]::new($false, $false).GetString($buffer, 0, $read)
    }
    finally {
        $stream.Dispose()
    }
}

function Stop-ContainmentProcessTree {
    param(
        [Parameter(Mandatory = $true)][Diagnostics.Process]$Process,
        [ValidateRange(1,60000)][int]$TimeoutMilliseconds = 10000
    )

    try { if ($Process.HasExited) { return $true } } catch { return $true }
    $processId = $Process.Id
    $treeTerminationAttempted = $false
    $taskkill = $null
    try {
        if (-not [string]::IsNullOrWhiteSpace($env:SystemRoot)) {
            $expectedTaskkill = [IO.Path]::GetFullPath((Join-Path $env:SystemRoot 'System32\taskkill.exe'))
            $taskkill = Get-ContainmentCanonicalPath -Path $expectedTaskkill -Kind Leaf -Label 'taskkill executable'
            if (-not (Test-ContainmentSamePath -Left $taskkill -Right $expectedTaskkill)) {
                throw 'taskkill executable did not resolve to the fixed System32 path'
            }
        }
        if ($taskkill) {
            $treeTerminationAttempted = $true
            $info = [Diagnostics.ProcessStartInfo]::new()
            $info.FileName = $taskkill
            $info.Arguments = "/PID $processId /T /F"
            $info.UseShellExecute = $false
            $info.CreateNoWindow = $true
            $info.RedirectStandardOutput = $true
            $info.RedirectStandardError = $true
            $killer = [Diagnostics.Process]::new()
            try {
                $killer.StartInfo = $info
                if ($killer.Start()) {
                    $stdoutTask = $killer.StandardOutput.ReadToEndAsync()
                    $stderrTask = $killer.StandardError.ReadToEndAsync()
                    if (-not $killer.WaitForExit($TimeoutMilliseconds)) {
                        try { $killer.Kill() } catch { }
                        [void]$killer.WaitForExit($TimeoutMilliseconds)
                    }
                    [void]$stdoutTask.Wait($TimeoutMilliseconds)
                    [void]$stderrTask.Wait($TimeoutMilliseconds)
                }
            }
            finally { $killer.Dispose() }
        }
    }
    catch { }

    try { $Process.Refresh() } catch { }
    try {
        if (-not $Process.HasExited) {
            try { $Process.Kill() } catch { }
            [void]$Process.WaitForExit($TimeoutMilliseconds)
        }
        $Process.Refresh()
        return $Process.HasExited
    }
    catch {
        if (-not $treeTerminationAttempted) { return $false }
        return $false
    }
}

function Invoke-ContainmentChildProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [AllowEmptyCollection()][string[]]$Arguments = @(),
        [Parameter(Mandatory = $true)][string]$DiagnosticDirectory,
        [ValidateRange(1, 86400)][int]$TimeoutSeconds = 120,
        [AllowNull()][Collections.IDictionary]$Policy,
        [AllowNull()][scriptblock]$OnProcessStarted
    )

    $launch = New-ContainmentProcessStartInfo `
        -Executable $Executable `
        -Arguments $Arguments `
        -DiagnosticDirectory $DiagnosticDirectory `
        -Policy $Policy
    $stdout = $null
    $stderr = $null
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $launch.ProcessInfo
    $started = $false
    try {
        $stdout = [IO.FileStream]::new(
            $launch.StdoutPath,
            [IO.FileMode]::CreateNew,
            [IO.FileAccess]::Write,
            [IO.FileShare]::Read,
            65536,
            [IO.FileOptions]::Asynchronous
        )
        $stderr = [IO.FileStream]::new(
            $launch.StderrPath,
            [IO.FileMode]::CreateNew,
            [IO.FileAccess]::Write,
            [IO.FileShare]::Read,
            65536,
            [IO.FileOptions]::Asynchronous
        )
        if (-not $process.Start()) {
            throw "child process did not start: $Executable"
        }
        $started = $true
        $processId = $process.Id
        if ($null -ne $OnProcessStarted) { & $OnProcessStarted $processId }
        $process.StandardInput.Close()
        # BeginOutputReadLine-equivalent independent asynchronous stream drains.
        $stdoutDrain = $process.StandardOutput.BaseStream.CopyToAsync($stdout)
        $stderrDrain = $process.StandardError.BaseStream.CopyToAsync($stderr)
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            [void](Stop-ContainmentProcessTree -Process $process -TimeoutMilliseconds 10000)
            [void]$stdoutDrain.Wait(10000)
            [void]$stderrDrain.Wait(10000)
            $timeout = [TimeoutException]::new("child process timed out after $TimeoutSeconds seconds")
            $timeout.Data['ProcessId'] = $processId
            $timeout.Data['StdoutPath'] = $launch.StdoutPath
            $timeout.Data['StderrPath'] = $launch.StderrPath
            throw $timeout
        }
        if (-not $stdoutDrain.Wait(10000) -or -not $stderrDrain.Wait(10000)) {
            $drainError = [TimeoutException]::new('child process output drain timed out')
            $drainError.Data['ProcessId'] = $processId
            throw $drainError
        }
        $stdout.Flush($true)
        $stderr.Flush($true)
        $exitCode = $process.ExitCode
    }
    finally {
        if ($null -ne $stdout) { $stdout.Dispose() }
        if ($null -ne $stderr) { $stderr.Dispose() }
        if ($started -and -not $process.HasExited) {
            [void](Stop-ContainmentProcessTree -Process $process -TimeoutMilliseconds 10000)
        }
        $process.Dispose()
        if (Test-Path -LiteralPath $launch.WorkingDirectory -PathType Container) {
            try { [IO.Directory]::Delete($launch.WorkingDirectory, $true) } catch { }
        }
    }
    return [pscustomobject]@{
        ExitCode = $exitCode
        ProcessId = $processId
        StdoutPath = $launch.StdoutPath
        StderrPath = $launch.StderrPath
        StdoutSummary = Get-ContainmentBoundedFileText -Path $launch.StdoutPath
        StderrSummary = Get-ContainmentBoundedFileText -Path $launch.StderrPath
        WorkingDirectory = $launch.WorkingDirectory
        RemovedEnvironmentNames = @($launch.Removed)
        FinalControlledEnvironmentNames = @($launch.Final)
    }
}

function New-InstalledProcessPolicy {
    param(
        [string]$InstallRoot,
        [string]$DataRoot,
        [string]$DspyCache,
        [AllowNull()][string]$ChirpHome,
        [AllowNull()][string]$Profile,
        [switch]$Interactive
    )

    $install = Get-ContainmentCanonicalPath -Path $InstallRoot -Kind Container -Label 'installed root'
    $data = Get-ContainmentCanonicalPath -Path $DataRoot -Kind Container -Label 'installed data root'
    $dspy = Get-ContainmentCanonicalPath -Path $DspyCache -Kind Container -Label 'DSPy cache'
    if ($Profile -and $script:ContainmentProfiles -notcontains $Profile) {
        throw "invalid installed child profile: $Profile"
    }
    if ($Interactive -and $Profile -cne 'full') {
        throw 'interactive discovery requires profile full'
    }
    $values = [ordered]@{
        PYTHONNOUSERSITE = '1'
        ROOK_INSTALL_ROOT = $install
        ROOK_DATA_DIR = $data
        ROOK_MODE = 'release'
        ROOK_DSPY_RESTRICT_PICKLE = '1'
        DSPY_CACHEDIR = $dspy
    }
    if ($ChirpHome) {
        $values.CHIRP_HOME = Get-ContainmentCanonicalPath -Path $ChirpHome -Kind Container -Label 'installed Chirp home'
    }
    if ($Profile) { $values.ROOK_MCP_TOOL_PROFILE = $Profile }
    if ($Interactive) { $values.ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING = '1' }
    return [ordered]@{ Mode = 'installed'; Values = $values }
}

function Invoke-InstalledPythonProcess {
    param(
        [string]$PythonPath,
        [string[]]$Arguments,
        [string]$DiagnosticDirectory,
        [int]$TimeoutSeconds,
        [string]$InstallRoot,
        [string]$DataRoot,
        [string]$DspyCache,
        [AllowNull()][string]$ChirpHome,
        [AllowNull()][string]$Profile,
        [switch]$Interactive
    )

    $policy = New-InstalledProcessPolicy `
        -InstallRoot $InstallRoot `
        -DataRoot $DataRoot `
        -DspyCache $DspyCache `
        -ChirpHome $ChirpHome `
        -Profile $Profile `
        -Interactive:$Interactive
    return Invoke-ContainmentChildProcess `
        -Executable $PythonPath `
        -Arguments $Arguments `
        -DiagnosticDirectory $DiagnosticDirectory `
        -TimeoutSeconds $TimeoutSeconds `
        -Policy $policy
}

function Invoke-CandidateInstallerProcess {
    param(
        [string]$InstallerPath,
        [string[]]$InstallerArguments,
        [string]$DiagnosticDirectory,
        [int]$TimeoutSeconds,
        [AllowNull()][scriptblock]$OnProcessStarted
    )

    $policy = [ordered]@{
        Mode = 'installer'
        Values = [ordered]@{ PYTHONNOUSERSITE = '1' }
    }
    return Invoke-ContainmentChildProcess `
        -Executable $InstallerPath `
        -Arguments $InstallerArguments `
        -DiagnosticDirectory $DiagnosticDirectory `
        -TimeoutSeconds $TimeoutSeconds `
        -Policy $policy `
        -OnProcessStarted $OnProcessStarted
}

function Read-ContainmentSingleCanonicalRecord {
    param([string]$Path, [string]$Label)

    $text = [Text.UTF8Encoding]::new($false, $true).GetString(
        [IO.File]::ReadAllBytes((Get-ContainmentCanonicalPath -Path $Path -Kind Leaf -Label $Label))
    )
    $line = $text.TrimEnd("`r", "`n")
    if ([string]::IsNullOrEmpty($line) -or $line.Contains("`r") -or $line.Contains("`n")) {
        throw "$Label must contain exactly one JSONL record"
    }
    try { $record = $line | ConvertFrom-Json -ErrorAction Stop }
    catch { throw "$Label is malformed JSON: $($_.Exception.Message)" }
    if ($line -cne (ConvertTo-ContainmentCanonicalJson -Value $record)) {
        throw "$Label is not canonical JSON"
    }
    return $record
}

function Assert-FullCpythonRuntime {
    param(
        [Parameter(Mandatory = $true)][string]$PythonPath,
        [AllowNull()][string]$ExpectedVersion,
        [AllowNull()][string]$DiagnosticDirectory,
        [switch]$EnforceNoUserSite
    )

    $python = Get-ContainmentCanonicalPath -Path $PythonPath -Kind Leaf -Label 'full CPython executable'
    $pythonRoot = Split-Path -Parent $python
    if (Test-Path -LiteralPath (Join-Path $pythonRoot 'pyvenv.cfg') -PathType Leaf) {
        throw 'full CPython runtime may not be a virtual environment'
    }
    $pthFiles = @(Get-ChildItem -LiteralPath $pythonRoot -Filter '*._pth' -File -ErrorAction Stop)
    if ($pthFiles.Count -ne 0) {
        throw 'full CPython runtime may not be _pth isolated'
    }

    $ownedDiagnostics = $false
    if (-not $DiagnosticDirectory) {
        $DiagnosticDirectory = Join-Path $env:TEMP ('rook-containment-python-identity-' + [guid]::NewGuid().ToString('N'))
        [IO.Directory]::CreateDirectory($DiagnosticDirectory) | Out-Null
        $ownedDiagnostics = $true
    }
    else {
        [void](Get-ContainmentCanonicalPath -Path $DiagnosticDirectory -Kind Container -Label 'Python identity diagnostics')
    }

    try {
        $code = "import json,os,sys;print(json.dumps({'base_executable':os.path.realpath(getattr(sys,'_base_executable',sys.executable)),'base_prefix':os.path.realpath(sys.base_prefix),'executable':os.path.realpath(sys.executable),'prefix':os.path.realpath(sys.prefix),'version':'.'.join(map(str,sys.version_info[:3]))},sort_keys=True,separators=(',',':')))"
        $identityValues = [ordered]@{}
        if ($EnforceNoUserSite) { $identityValues.PYTHONNOUSERSITE = '1' }
        $result = Invoke-ContainmentChildProcess `
            -Executable $python `
            -Arguments @('-S', '-c', $code) `
            -DiagnosticDirectory $DiagnosticDirectory `
            -TimeoutSeconds 30 `
            -Policy ([ordered]@{ Mode = 'identity'; Values = $identityValues })
        if ($result.ExitCode -ne 0) {
            throw "full CPython identity probe failed with exit code $($result.ExitCode)"
        }
        if ($EnforceNoUserSite) {
            [string[]]$finalControlled = @($result.FinalControlledEnvironmentNames)
            if ($finalControlled.Count -ne 1 -or
                -not [string]::Equals($finalControlled[0], 'PYTHONNOUSERSITE', [StringComparison]::OrdinalIgnoreCase)) {
                throw 'installed full CPython identity probe environment drift'
            }
        }
        $record = Read-ContainmentSingleCanonicalRecord -Path $result.StdoutPath -Label 'full CPython identity probe'
        foreach ($name in @('base_executable', 'base_prefix', 'executable', 'prefix', 'version')) {
            if ($record.PSObject.Properties.Name -notcontains $name) {
                throw "full CPython identity probe omitted $name"
            }
        }
        $reportedExecutable = (Resolve-Path -LiteralPath ([string]$record.executable)).Path
        $baseExecutable = (Resolve-Path -LiteralPath ([string]$record.base_executable)).Path
        if (-not (Test-ContainmentSamePath -Left $reportedExecutable -Right $python)) {
            throw 'full CPython executable identity drift'
        }
        if (-not (Test-ContainmentSamePath -Left $baseExecutable -Right $reportedExecutable)) {
            throw 'full CPython base executable differs from executable'
        }
        if (-not (Test-ContainmentSamePath -Left ([string]$record.prefix) -Right ([string]$record.base_prefix))) {
            throw 'full CPython runtime is a virtual environment'
        }
        if ($ExpectedVersion -and [string]$record.version -cne $ExpectedVersion) {
            throw "full CPython version mismatch: expected $ExpectedVersion, found $($record.version)"
        }
        return [pscustomobject]@{
            executable = $reportedExecutable
            base_executable = $baseExecutable
            prefix = [IO.Path]::GetFullPath([string]$record.prefix)
            base_prefix = [IO.Path]::GetFullPath([string]$record.base_prefix)
            version = [string]$record.version
            sha256 = Get-ContainmentSha256 -Path $python
            pth_files = @()
            diagnostic_stdout = $result.StdoutPath
            diagnostic_stderr = $result.StderrPath
            removed_environment_names = @($result.RemovedEnvironmentNames)
            final_controlled_environment_names = @($result.FinalControlledEnvironmentNames)
        }
    }
    finally {
        if ($ownedDiagnostics -and (Test-Path -LiteralPath $DiagnosticDirectory -PathType Container)) {
            [IO.Directory]::Delete($DiagnosticDirectory, $true)
        }
    }
}

function Test-PythonStartupIsolation {
    param(
        [Parameter(Mandatory = $true)][string]$PythonPath,
        [Parameter(Mandatory = $true)][string]$EvidenceRoot,
        [Parameter(Mandatory = $true)][string]$InstallRoot,
        [Parameter(Mandatory = $true)][string]$DataRoot,
        [AllowNull()][string]$ExpectedVersion
    )

    $evidence = Get-ContainmentCanonicalPath -Path $EvidenceRoot -Kind Container -Label 'startup-isolation evidence root'
    [void](Assert-ContainmentPathNotReparse -Path $evidence -Label 'startup-isolation evidence root')
    $runtime = Assert-FullCpythonRuntime -PythonPath $PythonPath -ExpectedVersion $ExpectedVersion -DiagnosticDirectory $evidence
    $install = Get-ContainmentCanonicalPath -Path $InstallRoot -Kind Container -Label 'startup-isolation install root'
    $data = Get-ContainmentCanonicalPath -Path $DataRoot -Kind Container -Label 'startup-isolation data root'
    $dspy = Join-Path $evidence 'dspy-cache'
    $ownedBase = Join-Path $evidence 'owned-user-base'
    [IO.Directory]::CreateDirectory($dspy) | Out-Null
    [IO.Directory]::CreateDirectory($ownedBase) | Out-Null

    $controlPolicy = [ordered]@{
        Mode = 'startup-control'
        Values = [ordered]@{ PYTHONUSERBASE = $ownedBase }
    }
    $siteCode = "import site;print(site.getusersitepackages())"
    $siteResult = Invoke-ContainmentChildProcess `
        -Executable $runtime.executable `
        -Arguments @('-S', '-c', $siteCode) `
        -DiagnosticDirectory $evidence `
        -TimeoutSeconds 30 `
        -Policy $controlPolicy
    if ($siteResult.ExitCode -ne 0) { throw 'startup-isolation user-site derivation failed' }
    $userSite = ([IO.File]::ReadAllText($siteResult.StdoutPath)).TrimEnd("`r", "`n")
    if (-not [IO.Path]::IsPathRooted($userSite)) { throw 'derived startup-isolation user site is not absolute' }
    $ownedPrefix = [IO.Path]::GetFullPath($ownedBase).TrimEnd('\') + '\'
    $userSite = [IO.Path]::GetFullPath($userSite)
    if (-not $userSite.StartsWith($ownedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'derived startup-isolation user site escaped the owned base'
    }
    [IO.Directory]::CreateDirectory($userSite) | Out-Null
    $tripwire = "from pathlib import Path; Path(__file__).with_suffix('.hit').write_text('executed', encoding='ascii')`n"
    $siteScript = Join-Path $userSite 'sitecustomize.py'
    $userScript = Join-Path $userSite 'usercustomize.py'
    [IO.File]::WriteAllText($siteScript, $tripwire, [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($userScript, $tripwire, [Text.UTF8Encoding]::new($false))
    $siteHit = Join-Path $userSite 'sitecustomize.hit'
    $userHit = Join-Path $userSite 'usercustomize.hit'

    $probePath = Join-Path $evidence 'startup-isolation-probe.py'
    $probeCode = @'
import json, os, site, sys
def origin(name):
    module = sys.modules.get(name)
    return None if module is None else os.path.realpath(getattr(module, "__file__", ""))
controlled = {}
for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE", "PYTHONNOUSERSITE", "DSPY_MODEL", "DSPY_CACHEDIR", "CHIRP_HOME"):
    if name in os.environ:
        controlled[name] = os.environ[name]
for name in sorted(k for k in os.environ if k.upper().startswith("ROOK_")):
    controlled[name] = os.environ[name]
print(json.dumps({
    "controlled_environment": controlled,
    "enable_user_site": site.ENABLE_USER_SITE,
    "executable": os.path.realpath(sys.executable),
    "no_user_site": sys.flags.no_user_site,
    "sitecustomize_origin": origin("sitecustomize"),
    "sys_path": [os.path.realpath(p) for p in sys.path if p],
    "user_site": os.path.realpath(site.getusersitepackages()),
    "usercustomize_origin": origin("usercustomize"),
    "version": ".".join(map(str, sys.version_info[:3])),
}, sort_keys=True, separators=(",", ":")))
'@
    [IO.File]::WriteAllText($probePath, $probeCode, [Text.UTF8Encoding]::new($false))

    $control = Invoke-ContainmentChildProcess `
        -Executable $runtime.executable `
        -Arguments @($probePath) `
        -DiagnosticDirectory $evidence `
        -TimeoutSeconds 30 `
        -Policy $controlPolicy
    if ($control.ExitCode -ne 0) { throw 'unsanitized startup-isolation control failed' }
    $controlRecord = Read-ContainmentSingleCanonicalRecord -Path $control.StdoutPath -Label 'unsanitized startup-isolation control'
    $siteControlHit = Test-Path -LiteralPath $siteHit -PathType Leaf
    $userControlHit = Test-Path -LiteralPath $userHit -PathType Leaf
    if (-not $siteControlHit -or -not $userControlHit -or
        [int]$controlRecord.no_user_site -ne 0 -or
        -not [bool]$controlRecord.enable_user_site) {
        throw 'unsanitized startup-isolation control did not prove both customization hooks'
    }
    if (-not (Test-ContainmentSamePath -Left ([string]$controlRecord.user_site) -Right $userSite)) {
        throw 'unsanitized startup-isolation control reported a different user site'
    }
    foreach ($origin in @([string]$controlRecord.sitecustomize_origin, [string]$controlRecord.usercustomize_origin)) {
        if (-not $origin.StartsWith($userSite.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'unsanitized startup-isolation hook origin escaped the owned user site'
        }
    }
    [IO.File]::Delete($siteHit)
    [IO.File]::Delete($userHit)

    $sanitized = Invoke-InstalledPythonProcess `
        -PythonPath $runtime.executable `
        -Arguments @($probePath) `
        -DiagnosticDirectory $evidence `
        -TimeoutSeconds 30 `
        -InstallRoot $install `
        -DataRoot $data `
        -DspyCache $dspy
    if ($sanitized.ExitCode -ne 0) { throw 'sanitized startup-isolation probe failed' }
    $sanitizedRecord = Read-ContainmentSingleCanonicalRecord -Path $sanitized.StdoutPath -Label 'sanitized startup-isolation probe'
    $siteSanitizedHit = Test-Path -LiteralPath $siteHit -PathType Leaf
    $userSanitizedHit = Test-Path -LiteralPath $userHit -PathType Leaf
    $environment = @{}
    foreach ($property in $sanitizedRecord.controlled_environment.PSObject.Properties) {
        $environment[$property.Name] = [string]$property.Value
    }
    if ($siteSanitizedHit -or $userSanitizedHit -or
        [int]$sanitizedRecord.no_user_site -ne 1 -or
        [bool]$sanitizedRecord.enable_user_site -or
        $environment.Contains('PYTHONUSERBASE') -or
        -not $environment.Contains('PYTHONNOUSERSITE') -or
        [string]$environment['PYTHONNOUSERSITE'] -cne '1') {
        throw 'sanitized startup-isolation policy failed closed'
    }
    foreach ($pathEntry in @($sanitizedRecord.sys_path)) {
        if (Test-ContainmentSamePath -Left ([string]$pathEntry) -Right $userSite) {
            throw 'sanitized startup-isolation sys.path retained the hostile user site'
        }
    }
    foreach ($origin in @($sanitizedRecord.sitecustomize_origin, $sanitizedRecord.usercustomize_origin)) {
        if ($null -ne $origin -and [string]$origin -and
            ([string]$origin).StartsWith($userSite.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'sanitized startup-isolation resolved an owned customization module'
        }
    }

    return [ordered]@{
        control_fired = $true
        sanitized = $true
        sitecustomize_control_hit = $siteControlHit
        usercustomize_control_hit = $userControlHit
        sitecustomize_sanitized_hit = $siteSanitizedHit
        usercustomize_sanitized_hit = $userSanitizedHit
        runtime = $runtime
        hostile_user_site = $userSite
        control_record = $controlRecord
        sanitized_record = $sanitizedRecord
        sanitized_environment = $environment
        probe_hashes = @(
            [ordered]@{ relative_path = 'startup-isolation-probe.py'; sha256 = Get-ContainmentSha256 $probePath },
            [ordered]@{ relative_path = 'sitecustomize.py'; sha256 = Get-ContainmentSha256 $siteScript },
            [ordered]@{ relative_path = 'usercustomize.py'; sha256 = Get-ContainmentSha256 $userScript }
        )
    }
}

function Get-ContainmentTreeProjection {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [string[]]$ExcludedRelativePaths = @(),
        [switch]$ExcludeGit
    )

    $rootPath = Get-ContainmentCanonicalPath -Path $Root -Kind Container -Label 'inventory root'
    $excluded = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($relative in $ExcludedRelativePaths) {
        [void]$excluded.Add($relative.Replace('\', '/').TrimStart('/'))
    }
    $records = [Collections.Generic.SortedDictionary[string,object]]::new([StringComparer]::Ordinal)
    $pending = New-Object Collections.Generic.Stack[string]
    $pending.Push($rootPath)
    while ($pending.Count -ne 0) {
        $directory = $pending.Pop()
        foreach ($item in @(Get-ChildItem -LiteralPath $directory -Force -ErrorAction Stop)) {
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "inventory contains a reparse point: $($item.FullName)"
            }
            $relative = $item.FullName.Substring($rootPath.TrimEnd('\').Length).TrimStart('\').Replace('\', '/')
            if ($ExcludeGit -and $relative -match '(?i)(^|/)\.git(/|$)') {
                continue
            }
            if ($excluded.Contains($relative)) { continue }
            if ($item.PSIsContainer) {
                $pending.Push($item.FullName)
                continue
            }
            if (-not ($item -is [IO.FileInfo])) { throw "inventory contains an unsupported object: $($item.FullName)" }
            $records.Add($relative, [ordered]@{
                relative_path = $relative
                sha256 = Get-ContainmentSha256 -Path $item.FullName
                size = [long]$item.Length
            })
        }
    }
    $files = @($records.Values)
    return [ordered]@{
        digest = Get-ContainmentValueSha256 -Value $files
        files = $files
    }
}

function Assert-ContainmentProjectionMatchesDisk {
    param(
        [AllowNull()][object]$Projection,
        [string]$Root,
        [string]$Label,
        [string[]]$ExcludedRelativePaths = @(),
        [switch]$ExcludeGit
    )

    Assert-ContainmentExactProperties -Value $Projection -Expected @('digest', 'files') -Label $Label
    [void](Assert-ContainmentHex -Value $Projection.digest -Length 64 -Label "$Label digest")
    $last = $null
    foreach ($record in @($Projection.files)) {
        Assert-ContainmentExactProperties -Value $record -Expected @('relative_path', 'sha256', 'size') -Label "$Label file"
        $relative = [string]$record.relative_path
        if ($null -ne $last -and [StringComparer]::Ordinal.Compare($last, $relative) -ge 0) {
            throw "$Label file projection is not strictly ordinal-sorted"
        }
        $last = $relative
        [void](Resolve-ContainmentOwnedRelativePath -Root $Root -RelativePath $relative -Kind Leaf -Label "$Label file")
        [void](Assert-ContainmentHex -Value $record.sha256 -Length 64 -Label "$Label file hash")
        if (-not (Test-ContainmentJsonInteger $record.size) -or [long]$record.size -lt 0) {
            throw "$Label file size is invalid"
        }
    }
    $actual = Get-ContainmentTreeProjection -Root $Root -ExcludedRelativePaths $ExcludedRelativePaths -ExcludeGit:$ExcludeGit
    if ((ConvertTo-ContainmentCanonicalJson -Value $actual) -cne
        (ConvertTo-ContainmentCanonicalJson -Value $Projection)) {
        throw "$Label inventory does not match disk"
    }
    return $actual
}

function Assert-ContainmentSelectedProjectionMatchesDisk {
    param([AllowNull()][object]$Projection, [string]$Root, [string]$Label)

    Assert-ContainmentExactProperties -Value $Projection -Expected @('digest','files') -Label $Label
    $rootPath = Get-ContainmentCanonicalPath -Path $Root -Kind Container -Label "$Label root"
    $last = $null
    $actualFiles = foreach ($record in @($Projection.files)) {
        Assert-ContainmentExactProperties -Value $record -Expected @('relative_path','sha256','size') -Label "$Label file"
        $relative = [string]$record.relative_path
        if ($null -ne $last -and [StringComparer]::Ordinal.Compare($last, $relative) -ge 0) {
            throw "$Label selected projection is not strictly ordinal-sorted"
        }
        $last = $relative
        $path = Resolve-ContainmentOwnedRelativePath -Root $rootPath -RelativePath $relative -Kind Leaf -Label "$Label file"
        $item = Get-Item -LiteralPath $path -Force
        [ordered]@{ relative_path=$relative; sha256=(Get-ContainmentSha256 $path); size=[long]$item.Length }
    }
    $actual = [ordered]@{ digest=(Get-ContainmentValueSha256 -Value @($actualFiles)); files=@($actualFiles) }
    if ((ConvertTo-ContainmentCanonicalJson $actual) -cne (ConvertTo-ContainmentCanonicalJson $Projection)) {
        throw "$Label selected projection hash/size mismatch"
    }
    return $actual
}

function Assert-ContainmentFileIdentity {
    param([AllowNull()][object]$Identity, [string]$Label)

    Assert-ContainmentExactProperties `
        -Value $Identity `
        -Expected @('path', 'size', 'sha256', 'file_version', 'product_version') `
        -Label $Label
    $path = Get-ContainmentCanonicalPath -Path ([string]$Identity.path) -Kind Leaf -Label $Label
    $item = Get-Item -LiteralPath $path -Force
    [void](Assert-ContainmentHex -Value $Identity.sha256 -Length 64 -Label "$Label hash")
    if (-not (Test-ContainmentJsonInteger $Identity.size) -or
        [long]$Identity.size -ne [long]$item.Length -or
        [string]$Identity.sha256 -cne (Get-ContainmentSha256 -Path $path)) {
        throw "$Label file identity hash/size drift"
    }
    $version = [Diagnostics.FileVersionInfo]::GetVersionInfo($path)
    if ([string]$Identity.file_version -cne [string]$version.FileVersion -or
        [string]$Identity.product_version -cne [string]$version.ProductVersion) {
        throw "$Label version identity drift"
    }
    return $path
}

function Invoke-ContainmentGitText {
    param([string]$GitPath, [string]$Root, [string[]]$Arguments, [string]$Label)

    $git = Get-ContainmentCanonicalPath -Path $GitPath -Kind Leaf -Label "$Label Git executable"
    $rootPath = Get-ContainmentCanonicalPath -Path $Root -Kind Container -Label "$Label Git root"
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $git
    $info.Arguments = (@('-C', $rootPath) + @($Arguments) | ForEach-Object { ConvertTo-ProcessArgument $_ }) -join ' '
    $info.WorkingDirectory = $rootPath
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $info
    $started = $false
    try {
        if (-not $process.Start()) { throw "$Label Git probe did not start" }
        $started = $true
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(30000)) {
            try { $process.Kill() } catch { }
            [void]$process.WaitForExit(10000)
            throw "$Label Git probe timed out"
        }
        if (-not $stdoutTask.Wait(10000) -or -not $stderrTask.Wait(10000)) {
            throw "$Label Git probe output drain timed out"
        }
        $stdout = [string]$stdoutTask.Result
        $stderr = [string]$stderrTask.Result
        if ($process.ExitCode -ne 0) {
            $summary = $stderr
            if ($summary.Length -gt 4096) { $summary = $summary.Substring(0, 4096) }
            throw "$Label Git probe failed with exit code $($process.ExitCode)`: $summary"
        }
    }
    finally {
        if ($started -and -not $process.HasExited) {
            try { $process.Kill() } catch { }
            [void]$process.WaitForExit(10000)
        }
        $process.Dispose()
    }
    return $stdout.Trim()
}

function Assert-ContainmentSourceRepository {
    param([string]$Label, [AllowNull()][object]$Source, [string]$GitPath)

    $root = Get-ContainmentCanonicalPath -Path ([string]$Source.root) -Kind Container -Label "$Label source root"
    $reported = Invoke-ContainmentGitText -GitPath $GitPath -Root $root -Arguments @('rev-parse', '--show-toplevel') -Label $Label
    if (-not (Test-ContainmentSamePath -Left $root -Right $reported)) {
        throw "$Label source root is not the Git top-level"
    }
    $head = Invoke-ContainmentGitText -GitPath $GitPath -Root $root -Arguments @('rev-parse', 'HEAD') -Label $Label
    $branch = Invoke-ContainmentGitText -GitPath $GitPath -Root $root -Arguments @('branch', '--show-current') -Label $Label
    $status = Invoke-ContainmentGitText -GitPath $GitPath -Root $root -Arguments @('status', '--porcelain=v1', '--untracked-files=all') -Label $Label
    if ($Source.clean -isnot [bool] -or
        [string]$Source.sha -cne $head -or [string]$Source.branch -cne $branch -or
        -not $Source.clean -or -not [string]::IsNullOrEmpty($status)) {
        throw "$Label source SHA, branch, or clean-state mismatch"
    }
}

function Read-AndValidateCandidateIdentity {
    param(
        [Parameter(Mandatory = $true)][string]$ArtifactDirectory,
        [Parameter(Mandatory = $true)][string]$CandidateIdentityPath,
        [Parameter(Mandatory = $true)][string]$CandidateSidecarPath,
        [switch]$ValidateSourceRepositories = $true
    )

    $artifact = Get-ContainmentCanonicalPath -Path $ArtifactDirectory -Kind Container -Label 'candidate artifact directory'
    $identityPath = Get-ContainmentCanonicalPath -Path $CandidateIdentityPath -Kind Leaf -Label 'candidate identity'
    $sidecarPath = Get-ContainmentCanonicalPath -Path $CandidateSidecarPath -Kind Leaf -Label 'candidate identity sidecar'
    if (-not (Test-ContainmentSamePath -Left $identityPath -Right (Join-Path $artifact 'containment-candidate.json')) -or
        -not (Test-ContainmentSamePath -Left $sidecarPath -Right (Join-Path $artifact 'containment-candidate.sha256'))) {
        throw 'candidate identity and sidecar must use their canonical artifact paths'
    }
    $record = Read-ContainmentCanonicalJsonFile -Path $identityPath -Label 'candidate identity'
    $pair = Assert-ContainmentSidecar -SidecarPath $sidecarPath -TargetPath $identityPath -Label 'candidate identity'
    Assert-ContainmentExactProperties `
        -Value $record `
        -Expected @('schema_version','non_publishable','product_version','build','sources','tools','inputs','native_environment','private_python','managed','installer','commands','inventories') `
        -Label 'candidate identity'
    if ($record.schema_version -isnot [int] -or $record.schema_version -ne 1 -or
        $record.non_publishable -isnot [bool] -or -not $record.non_publishable) {
        throw 'candidate identity schema/non-publishable marker is invalid'
    }

    foreach ($name in @('rook', 'chirp')) {
        $source = $record.sources.$name
        [void](Assert-ContainmentHex -Value $source.sha -Length 40 -Label "$name source SHA")
        [void](Assert-ContainmentHex -Value $source.source_archive_sha256 -Length 64 -Label "$name source archive hash")
        [void](Assert-ContainmentHex -Value $source.source_tree_digest -Length 64 -Label "$name source tree digest")
        $stageExpected = Join-Path $artifact ("stage\" + (Get-Culture).TextInfo.ToTitleCase($name))
        $stagePath = Get-ContainmentCanonicalPath -Path ([string]$source.stage_path) -Kind Container -Label "$name staged source"
        if (-not (Test-ContainmentSamePath -Left $stagePath -Right $stageExpected) -or
            -not (Test-ContainmentSamePath -Left ([string]$source.local_source_clone_path) -Right $stagePath)) {
            throw "$name staged source path identity mismatch"
        }
        $inventory = $record.inventories.source_inventory.$name
        if ([string]$source.source_tree_digest -cne [string]$inventory.digest) {
            throw "$name source inventory digest binding mismatch"
        }
        [void](Assert-ContainmentProjectionMatchesDisk -Projection $inventory -Root $stagePath -Label "$name source inventory" -ExcludeGit)
        $archivePath = Join-Path $artifact ("source-evidence\" + (Get-Culture).TextInfo.ToTitleCase($name) + '.tar')
        if ([string]$source.source_archive_sha256 -cne (Get-ContainmentSha256 -Path $archivePath)) {
            throw "$name source archive hash mismatch"
        }
    }

    $privateRelative = [string]$record.private_python.relative_path
    if ($privateRelative -cne 'stage/Rook/installer/runtime/python/cpython-3.11.9/python.exe' -or
        [string]$record.private_python.version -cne '3.11.9' -or
        @($record.private_python.pth_files).Count -ne 0) {
        throw 'candidate private Python identity is not the full CPython 3.11.9 runtime'
    }
    $privatePython = Resolve-ContainmentOwnedRelativePath -Root $artifact -RelativePath $privateRelative -Kind Leaf -Label 'candidate private Python'
    if ([string]$record.private_python.sha256 -cne (Get-ContainmentSha256 -Path $privatePython)) {
        throw 'candidate private Python hash mismatch'
    }
    if (@(Get-ChildItem -LiteralPath (Split-Path -Parent $privatePython) -Filter '*._pth' -File).Count -ne 0) {
        throw 'candidate private Python is _pth isolated'
    }

    $wheelhouseRelative = [string]$record.inputs.python_wheelhouse.relative_path
    if ($wheelhouseRelative -cne 'stage/Rook/installer/runtime/python-wheelhouse') {
        throw 'candidate Python wheelhouse relative path mismatch'
    }
    $wheelhouse = Resolve-ContainmentOwnedRelativePath -Root $artifact -RelativePath $wheelhouseRelative -Kind Container -Label 'candidate Python wheelhouse'
    [void](Assert-ContainmentProjectionMatchesDisk -Projection $record.inputs.python_wheelhouse.validated_payload -Root $wheelhouse -Label 'candidate Python wheelhouse')

    foreach ($property in $record.tools.PSObject.Properties) {
        [void](Assert-ContainmentFileIdentity -Identity $property.Value -Label "candidate tool $($property.Name)")
    }
    [void](Assert-ContainmentFileIdentity -Identity $record.inputs.native_msvc.compiler -Label 'candidate MSVC compiler')
    [void](Assert-ContainmentFileIdentity -Identity $record.inputs.native_msvc.linker -Label 'candidate MSVC linker')
    [void](Assert-ContainmentFileIdentity -Identity $record.inputs.native_rhino_sdk.property_sheet -Label 'candidate Rhino SDK property sheet')
    [void](Assert-ContainmentFileIdentity -Identity $record.inputs.dotnet.executable -Label 'candidate dotnet executable')
    [void](Assert-ContainmentFileIdentity -Identity $record.inputs.ffmpeg.source_identity -Label 'candidate FFmpeg source')
    [void](Assert-ContainmentFileIdentity -Identity $record.inputs.ffmpeg.source_bundle_manifest -Label 'candidate FFmpeg manifest')
    [void](Assert-ContainmentSelectedProjectionMatchesDisk -Projection $record.inputs.rhino_managed_references.projection -Root ([string]$record.inputs.rhino_managed_references.root) -Label 'Rhino managed references')
    [void](Assert-ContainmentSelectedProjectionMatchesDisk -Projection $record.inputs.revit_references.projection -Root ([string]$record.inputs.revit_references.root) -Label 'Revit references')
    [void](Assert-ContainmentSelectedProjectionMatchesDisk -Projection $record.inputs.vc_redist.projection -Root ([string]$record.inputs.vc_redist.root) -Label 'VC redistributable inputs')
    [void](Assert-ContainmentSelectedProjectionMatchesDisk -Projection $record.inputs.occt.consumed_header_and_import_libraries -Root ([string]$record.inputs.occt.build_root) -Label 'OCCT build inputs')
    [void](Assert-ContainmentSelectedProjectionMatchesDisk -Projection $record.inputs.occt.consumed_runtime_dlls -Root ([string]$record.inputs.occt.runtime_root) -Label 'OCCT runtime inputs')
    $stageRook = Join-Path $artifact 'stage\Rook'
    [void](Assert-ContainmentProjectionMatchesDisk -Projection $record.inputs.ffmpeg.installed_payload -Root (Join-Path $stageRook 'third_party\ffmpeg') -Label 'FFmpeg installed payload')
    $trackedProjection = $record.inputs.ffmpeg.tracked_build_outputs
    foreach ($tracked in @($trackedProjection.files)) {
        [void](Resolve-ContainmentOwnedRelativePath -Root $stageRook -RelativePath $tracked.relative_path -Kind Leaf -Label 'tracked FFmpeg output')
        $trackedPath = Resolve-ContainmentOwnedRelativePath -Root $stageRook -RelativePath $tracked.relative_path -Kind Leaf -Label 'tracked FFmpeg output'
        if (-not (Test-ContainmentJsonInteger $tracked.size) -or
            [string]$tracked.sha256 -cne (Get-ContainmentSha256 $trackedPath) -or
            [long]$tracked.size -ne (Get-Item $trackedPath).Length) {
            throw 'tracked FFmpeg output projection mismatch'
        }
    }
    if ([string]$trackedProjection.digest -cne (Get-ContainmentValueSha256 -Value @($trackedProjection.files))) {
        throw 'tracked FFmpeg output digest mismatch'
    }

    $installer = Resolve-ContainmentOwnedRelativePath -Root $artifact -RelativePath $record.installer.relative_path -Kind Leaf -Label 'candidate installer'
    $stagedInstaller = Resolve-ContainmentOwnedRelativePath -Root $artifact -RelativePath 'stage/Rook/installer/RookSetup.iss' -Kind Leaf -Label 'staged installer source'
    $sourceInstaller = Join-Path ([string]$record.sources.rook.root) 'installer\RookSetup.iss'
    $sourceInstaller = Get-ContainmentCanonicalPath -Path $sourceInstaller -Kind Leaf -Label 'reviewed installer source'
    if (-not (Test-ContainmentJsonInteger $record.installer.staged_size) -or
        -not (Test-ContainmentJsonInteger $record.installer.source_size) -or
        [string]$record.installer.sha256 -cne (Get-ContainmentSha256 $installer) -or
        [string]$record.installer.staged_sha256 -cne (Get-ContainmentSha256 $stagedInstaller) -or
        [string]$record.installer.source_sha256 -cne (Get-ContainmentSha256 $sourceInstaller) -or
        [long]$record.installer.staged_size -ne (Get-Item $stagedInstaller).Length -or
        [long]$record.installer.source_size -ne (Get-Item $sourceInstaller).Length -or
        [string]$record.installer.source_sha256 -cne [string]$record.installer.staged_sha256 -or
        [long]$record.installer.source_size -ne [long]$record.installer.staged_size) {
        throw 'candidate installer source/staged/output hash identity mismatch'
    }

    [void](Assert-ContainmentProjectionMatchesDisk -Projection $record.inventories.build_inventory -Root (Join-Path $artifact 'stage') -Label 'candidate build inventory' -ExcludeGit)
    [void](Assert-ContainmentProjectionMatchesDisk -Projection $record.inventories.output_inventory -Root $artifact -Label 'candidate output inventory' -ExcludedRelativePaths @('containment-candidate.json','containment-candidate.sha256') -ExcludeGit)

    if ($ValidateSourceRepositories) {
        $gitIdentity = $record.tools.GitPath
        $gitPath = Assert-ContainmentFileIdentity -Identity $gitIdentity -Label 'candidate Git tool'
        Assert-ContainmentSourceRepository -Label 'Rook' -Source $record.sources.rook -GitPath $gitPath
        Assert-ContainmentSourceRepository -Label 'Chirp' -Source $record.sources.chirp -GitPath $gitPath
    }

    return [ordered]@{
        artifact_directory = $artifact
        identity_path = $identityPath
        identity_sha256 = $pair.TargetSha256
        sidecar_path = $sidecarPath
        sidecar_sha256 = $pair.SidecarSha256
        installer_path = $installer
        installer_sha256 = Get-ContainmentSha256 $installer
        private_python_path = $privatePython
        private_python_sha256 = Get-ContainmentSha256 $privatePython
        record = $record
    }
}

function Get-CandidateArtifactSnapshot {
    param(
        [AllowNull()][object]$Candidate,
        [AllowNull()][string]$ArtifactDirectory
    )

    if ($null -ne $Candidate) { $ArtifactDirectory = [string]$Candidate.artifact_directory }
    if (-not $ArtifactDirectory) { throw 'candidate artifact snapshot requires a validated candidate or artifact directory' }
    $artifact = Get-ContainmentCanonicalPath -Path $ArtifactDirectory -Kind Container -Label 'candidate artifact snapshot root'
    $projection = Get-ContainmentTreeProjection -Root $artifact -ExcludeGit
    return [ordered]@{
        root = $artifact
        sha256 = $projection.digest
        files = @($projection.files)
    }
}

function Assert-CandidateArtifactSnapshot {
    param([AllowNull()][object]$Snapshot)

    Assert-ContainmentExactProperties -Value $Snapshot -Expected @('root','sha256','files') -Label 'candidate artifact snapshot'
    $actual = Get-CandidateArtifactSnapshot -ArtifactDirectory ([string]$Snapshot.root)
    if ((ConvertTo-ContainmentCanonicalJson $actual) -cne (ConvertTo-ContainmentCanonicalJson $Snapshot)) {
        throw 'candidate artifact snapshot hash drift'
    }
}

function New-EvidenceDirectoryClaim {
    param(
        [Parameter(Mandatory = $true)][string]$EvidenceDirectory,
        [Parameter(Mandatory = $true)][string]$RunId
    )

    [void](Assert-ContainmentHex -Value $RunId -Length 32 -Label 'run id')
    if (-not [IO.Path]::IsPathRooted($EvidenceDirectory)) {
        throw 'evidence directory must be absolute'
    }
    $full = [IO.Path]::GetFullPath($EvidenceDirectory)
    [void](Assert-ContainmentPathNotReparse -Path $full -Label 'evidence directory')
    if (Test-Path -LiteralPath $full) {
        $item = Get-Item -LiteralPath $full -Force
        if (-not $item.PSIsContainer) { throw 'evidence path must be an empty directory' }
        if (@(Get-ChildItem -LiteralPath $full -Force).Count -ne 0) {
            throw 'evidence directory must be empty before ownership is claimed'
        }
    }
    else {
        $parent = Split-Path -Parent $full
        if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
            throw 'evidence directory parent must already exist'
        }
        [IO.Directory]::CreateDirectory($full) | Out-Null
    }
    [void](Assert-ContainmentPathNotReparse -Path $full -Label 'evidence directory')
    $markerPath = Join-Path $full '.containment-run-owner.json'
    $marker = [ordered]@{ schema_version = 1; run_id = $RunId }
    Write-ContainmentCreateNewBytes -Path $markerPath -Bytes ([Text.UTF8Encoding]::new($false).GetBytes((ConvertTo-ContainmentCanonicalJson $marker)))
    return [pscustomobject]@{ EvidenceDirectory = $full; MarkerPath = $markerPath; RunId = $RunId }
}

function ConvertFrom-CanonicalJsonLine {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Line,
        [ValidateSet('authorization_required', 'scenario_result')][string]$ExpectedType
    )

    if ([string]::IsNullOrEmpty($Line) -or $Line.Contains("`r") -or $Line.Contains("`n") -or $Line -ne $Line.Trim()) {
        throw "$ExpectedType JSONL record is not one canonical line"
    }
    try { $record = $Line | ConvertFrom-Json -ErrorAction Stop }
    catch { throw "$ExpectedType JSONL record is malformed: $($_.Exception.Message)" }
    if ($Line -cne (ConvertTo-ContainmentCanonicalJson -Value $record)) {
        throw "$ExpectedType JSONL record is not canonical"
    }
    if ($record.type -isnot [string] -or $record.type -cne $ExpectedType -or
        $record.schema_version -isnot [int] -or $record.schema_version -ne 1) {
        throw "$ExpectedType JSONL record type/schema mismatch"
    }

    if ($ExpectedType -eq 'authorization_required') {
        Assert-ContainmentExactProperties `
            -Value $record `
            -Expected @('type','schema_version','scenario','run_id','nonce','target','target_sha256','mutation','mutation_sha256','verification','verification_sha256','restoration','restoration_sha256','required_response') `
            -Label 'authorization_required'
        if ($record.scenario -isnot [string] -or $record.run_id -isnot [string] -or
            $record.nonce -isnot [string] -or $record.target_sha256 -isnot [string] -or
            $record.mutation -isnot [string] -or $record.mutation_sha256 -isnot [string] -or
            $record.verification -isnot [string] -or $record.verification_sha256 -isnot [string] -or
            $record.restoration -isnot [string] -or $record.restoration_sha256 -isnot [string] -or
            $record.required_response -isnot [string]) {
            throw 'authorization_required field type mismatch'
        }
        if (@('rhino','grasshopper') -cnotcontains $record.scenario) {
            throw 'authorization_required scenario is invalid'
        }
        [void](Assert-ContainmentHex -Value $record.run_id -Length 32 -Label 'authorization run id')
        [void](Assert-ContainmentHex -Value $record.nonce -Length 32 -Label 'authorization nonce')
        Assert-ContainmentExactProperties -Value $record.target -Expected @('label','process_id','port','scratch_path') -Label 'authorization target'
        if ($record.target.label -isnot [string] -or $record.target.process_id -isnot [int] -or
            $record.target.port -isnot [int] -or $record.target.scratch_path -isnot [string] -or
            $record.target.process_id -le 0 -or $record.target.port -ne 9878 -or
            -not [IO.Path]::IsPathRooted($record.target.scratch_path)) {
            throw 'authorization_required target identity is invalid'
        }
        $scenario = $record.scenario
        if ($record.target.label -cne [string]$script:ContainmentAuthorizationLabels[$scenario]) {
            throw 'authorization_required target label mismatch'
        }
        foreach ($field in @('mutation','verification','restoration')) {
            if ([string]$record.$field -cne [string]$script:ContainmentAuthorizationDescriptions[$scenario][$field]) {
                throw "authorization_required $field description mismatch"
            }
            $hashName = $field + '_sha256'
            $expectedHash = Get-ContainmentValueSha256 -Value ([string]$record.$field)
            if ([string]$record.$hashName -cne $expectedHash) {
                throw "authorization_required $field hash mismatch"
            }
        }
        $targetHash = Get-ContainmentValueSha256 -Value $record.target
        if ([string]$record.target_sha256 -cne $targetHash) {
            throw 'authorization_required target hash mismatch'
        }
        $expectedResponse = "AUTHORIZE scenario=$scenario run=$($record.run_id) nonce=$($record.nonce) target=$targetHash mutation=$($record.mutation_sha256) verify=$($record.verification_sha256) restore=$($record.restoration_sha256)"
        if ([string]$record.required_response -cne $expectedResponse) {
            throw 'authorization_required required response mismatch'
        }
    }
    else {
        Assert-ContainmentExactProperties `
            -Value $record `
            -Expected @('type','schema_version','scenario','run_id','success','failure_label','evidence_path','evidence_sha256') `
            -Label 'scenario_result'
        if ($record.scenario -isnot [string] -or $record.run_id -isnot [string] -or
            $record.success -isnot [bool] -or
            ($null -ne $record.failure_label -and $record.failure_label -isnot [string]) -or
            $record.evidence_path -isnot [string] -or $record.evidence_sha256 -isnot [string]) {
            throw 'scenario_result field type mismatch'
        }
        if (@('rhino','grasshopper') -cnotcontains $record.scenario) {
            throw 'scenario_result scenario is invalid'
        }
        [void](Assert-ContainmentHex -Value $record.run_id -Length 32 -Label 'scenario result run id')
        [void](Assert-ContainmentHex -Value $record.evidence_sha256 -Length 64 -Label 'scenario result evidence hash')
        if ([IO.Path]::IsPathRooted($record.evidence_path) -or $record.evidence_path -match '(^|[\/])\.\.([\/]|$)') {
            throw 'scenario_result evidence path is unsafe'
        }
        if ($record.success) {
            if ($null -ne $record.failure_label) { throw 'successful scenario_result retained a failure label' }
        }
        elseif ($script:ContainmentScenarioFailureLabels -cnotcontains [string]$record.failure_label) {
            throw 'scenario_result failure label is invalid'
        }
    }
    return $record
}

function Read-ContainmentBoundedJsonLine {
    param(
        [Parameter(Mandatory = $true)][IO.Stream]$Stream,
        [Parameter(Mandatory = $true)][Collections.IDictionary]$State,
        [Parameter(Mandatory = $true)][DateTime]$Deadline,
        [Parameter(Mandatory = $true)][string]$Label,
        [ValidateRange(1, 1048576)][int]$MaximumBytes = 65536,
        [switch]$AllowCleanEof,
        [Parameter(Mandatory = $true)][ref]$ReadPending
    )

    $bytes = New-Object Collections.Generic.List[byte]
    if ($State.buffer -isnot [byte[]] -or $State.buffer.Length -lt 1 -or
        $State.offset -isnot [int] -or $State.count -isnot [int]) {
        throw "$Label reader state is invalid"
    }
    $ReadPending.Value = $false
    while ($true) {
        $remaining = [int]($Deadline - [DateTime]::UtcNow).TotalMilliseconds
        if ($remaining -le 0) { throw "$Label timed out" }
        if ([int]$State.offset -ge [int]$State.count) {
            $State.offset = 0
            $State.count = 0
            $ReadPending.Value = $true
            $readTask = $Stream.ReadAsync($State.buffer, 0, $State.buffer.Length)
            if (-not $readTask.Wait($remaining)) { throw "$Label timed out" }
            $ReadPending.Value = $false
            $read = $readTask.Result
            if ($read -eq 0) {
                if ($AllowCleanEof -and $bytes.Count -eq 0) { return $null }
                throw "$Label ended at EOF before its JSONL newline"
            }
            $State.count = [int]$read
        }
        $current = [byte]$State.buffer[[int]$State.offset]
        $State.offset = [int]$State.offset + 1
        if ($current -eq 10) {
            $length = $bytes.Count
            if ($length -gt 0 -and $bytes[$length - 1] -eq 13) { $length-- }
            try {
                return [Text.UTF8Encoding]::new($false, $true).GetString($bytes.ToArray(), 0, $length)
            }
            catch { throw "$Label is not strict UTF-8" }
        }
        if ($bytes.Count -ge $MaximumBytes) {
            throw "$Label exceeded the bounded $MaximumBytes-byte line limit"
        }
        $bytes.Add($current)
    }
}

function Invoke-LiveGateProcess {
    param(
        [Parameter(Mandatory = $true)][string]$PythonPath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$DiagnosticDirectory,
        [ValidateRange(1, 86400)][int]$TimeoutSeconds,
        [ValidateSet('rhino','grasshopper')][string]$ExpectedScenario,
        [AllowNull()][string]$InstallRoot,
        [AllowNull()][string]$DataRoot,
        [AllowNull()][string]$DspyCache,
        [AllowNull()][string]$ChirpHome
    )

    $policy = [ordered]@{ Mode = 'raw'; Values = [ordered]@{} }
    if ($InstallRoot -or $DataRoot -or $DspyCache -or $ChirpHome) {
        if (-not $InstallRoot -or -not $DataRoot -or -not $DspyCache) {
            throw 'installed live gate requires install, data, and DSPy roots'
        }
        $policy = New-InstalledProcessPolicy -InstallRoot $InstallRoot -DataRoot $DataRoot -DspyCache $DspyCache -ChirpHome $ChirpHome
    }
    $launch = New-ContainmentProcessStartInfo `
        -Executable $PythonPath `
        -Arguments $Arguments `
        -DiagnosticDirectory $DiagnosticDirectory `
        -Policy $policy `
        -InteractiveInput
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $launch.ProcessInfo
    $stdout = $null
    $stderr = $null
    $stderrDrain = $null
    $stdoutWriter = $null
    $started = $false
    $authorizedResponseMatched = $false
    $stdoutReadPending = $false
    $stdoutLineState = [ordered]@{buffer=(New-Object byte[] 4096);offset=0;count=0}
    $authorizedStdoutDrain = $null
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    try {
        $stdout = [IO.File]::Open($launch.StdoutPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
        $stderr = [IO.FileStream]::new($launch.StderrPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read, 65536, [IO.FileOptions]::Asynchronous)
        $stdoutWriter = [IO.StreamWriter]::new($stdout, [Text.UTF8Encoding]::new($false), 4096, $true)
        $stdoutWriter.NewLine = "`n"
        if (-not $process.Start()) { throw 'live gate child did not start' }
        $started = $true
        $processId = $process.Id
        $stderrDrain = $process.StandardError.BaseStream.CopyToAsync($stderr)

        $firstLine = Read-ContainmentBoundedJsonLine `
            -Stream $process.StandardOutput.BaseStream `
            -State $stdoutLineState `
            -Deadline $deadline `
            -Label 'live gate authorization challenge' `
            -ReadPending ([ref]$stdoutReadPending)
        $stdoutWriter.WriteLine($firstLine)
        $stdoutWriter.Flush()
        $authorization = ConvertFrom-CanonicalJsonLine -Line $firstLine -ExpectedType 'authorization_required'
        if ([string]$authorization.scenario -cne $ExpectedScenario) {
            throw 'live gate authorization challenge scenario mismatch'
        }

        Write-Host "authorization_required scenario=$($authorization.scenario) run=$($authorization.run_id) nonce=$($authorization.nonce)"
        Write-Host "target: $($authorization.target.label) pid=$($authorization.target.process_id) port=$($authorization.target.port) scratch=$($authorization.target.scratch_path)"
        Write-Host "mutation: $($authorization.mutation)"
        Write-Host "verification: $($authorization.verification)"
        Write-Host "restoration: $($authorization.restoration)"
        Write-Host "required_response: $($authorization.required_response)"
        $response = Read-Host -Prompt "Authorize $ExpectedScenario exactly as displayed"
        $authorizedResponseMatched = [string]::Equals(
            [string]$response,
            [string]$authorization.required_response,
            [StringComparison]::Ordinal
        )
        $process.StandardInput.Write($response)
        $process.StandardInput.Write("`n")
        $process.StandardInput.Flush()
        $process.StandardInput.Close()
        $response = $null

        $secondLine = Read-ContainmentBoundedJsonLine `
            -Stream $process.StandardOutput.BaseStream `
            -State $stdoutLineState `
            -Deadline $deadline `
            -Label 'live gate scenario_result' `
            -ReadPending ([ref]$stdoutReadPending)
        $stdoutWriter.WriteLine($secondLine)
        $stdoutWriter.Flush()
        $result = ConvertFrom-CanonicalJsonLine -Line $secondLine -ExpectedType 'scenario_result'
        if ([string]$result.scenario -cne $ExpectedScenario) {
            throw 'live gate scenario_result scenario mismatch'
        }
        $extraLine = Read-ContainmentBoundedJsonLine `
            -Stream $process.StandardOutput.BaseStream `
            -State $stdoutLineState `
            -Deadline $deadline `
            -Label 'live gate extra JSONL record' `
            -AllowCleanEof `
            -ReadPending ([ref]$stdoutReadPending)
        if ($null -ne $extraLine) {
            $stdoutWriter.WriteLine($extraLine)
            $stdoutWriter.Flush()
            throw 'live gate emitted an extra JSONL record'
        }
        $remaining = [Math]::Max(1, [int]($deadline - [DateTime]::UtcNow).TotalMilliseconds)
        if (-not $process.WaitForExit($remaining)) { throw 'live gate child timed out after scenario_result' }
        if (-not $stderrDrain.Wait(10000)) { throw 'live gate stderr drain timed out' }
        $stderr.Flush($true)
        if (-not [bool]$result.success) {
            $scenarioFailure = [InvalidOperationException]::new("live gate scenario_result reported failure: $($result.failure_label)")
            if ($script:ContainmentScenarioFailureLabels -ccontains [string]$result.failure_label) {
                $scenarioFailure.Data['ContainmentFailureLabel'] = [string]$result.failure_label
            }
            throw $scenarioFailure
        }
        if ($process.ExitCode -ne 0) { throw "live gate child exit code was $($process.ExitCode)" }
        return [pscustomobject]@{
            ExitCode = $process.ExitCode
            ProcessId = $processId
            Authorization = $authorization
            Result = $result
            StdoutPath = $launch.StdoutPath
            StderrPath = $launch.StderrPath
            RemovedEnvironmentNames = @($launch.Removed)
            FinalControlledEnvironmentNames = @($launch.Final)
        }
    }
    catch {
        $failure = $_
        if ($started -and -not $process.HasExited) {
            try { $process.StandardInput.Close() } catch { }
            if ($authorizedResponseMatched) {
                # A matching authorization may already have begun mutation. Continue draining
                # and give the gate's own finally/restoration path all time remaining under the
                # original live-gate deadline. There is no shorter post-authorization kill cap.
                if (-not $stdoutReadPending) {
                    try {
                        $stdoutWriter.Flush()
                        $process.StandardOutput.DiscardBufferedData()
                        $authorizedStdoutDrain = $process.StandardOutput.BaseStream.CopyToAsync($stdout)
                    }
                    catch { $authorizedStdoutDrain = $null }
                }
                $remaining = [Math]::Max(0, [int]($deadline - [DateTime]::UtcNow).TotalMilliseconds)
                if ($remaining -gt 0) { [void]$process.WaitForExit($remaining) }
            }
            if (-not $process.HasExited) {
                [void](Stop-ContainmentProcessTree -Process $process -TimeoutMilliseconds 10000)
            }
            if ($null -ne $authorizedStdoutDrain) { [void]$authorizedStdoutDrain.Wait(10000) }
            if ($null -ne $stderrDrain) { [void]$stderrDrain.Wait(10000) }
        }
        throw $failure
    }
    finally {
        if ($null -ne $stdoutWriter) { $stdoutWriter.Dispose() }
        if ($null -ne $stdout) { $stdout.Dispose() }
        if ($null -ne $stderr) { $stderr.Dispose() }
        $process.Dispose()
        if (Test-Path -LiteralPath $launch.WorkingDirectory -PathType Container) {
            try { [IO.Directory]::Delete($launch.WorkingDirectory, $true) } catch { }
        }
    }
}

function Test-ContainmentUtcTimestamp {
    param([AllowNull()][object]$Value)
    return ([string]$Value -cmatch '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{1,6}Z$')
}

function New-ContainmentAuthorizationChallenge {
    param(
        [ValidateSet('rhino','grasshopper')][string]$Scenario,
        [string]$RunId,
        [string]$Nonce,
        [AllowNull()][object]$Target
    )

    $challengeTarget = [ordered]@{
        label = [string]$script:ContainmentAuthorizationLabels[$Scenario]
        process_id = [int]$Target.process_id
        port = [int]$Target.port
        scratch_path = [string]$Target.scratch_path
    }
    $descriptions = $script:ContainmentAuthorizationDescriptions[$Scenario]
    $targetHash = Get-ContainmentValueSha256 $challengeTarget
    $mutationHash = Get-ContainmentValueSha256 ([string]$descriptions.mutation)
    $verificationHash = Get-ContainmentValueSha256 ([string]$descriptions.verification)
    $restorationHash = Get-ContainmentValueSha256 ([string]$descriptions.restoration)
    $required = "AUTHORIZE scenario=$Scenario run=$RunId nonce=$Nonce target=$targetHash mutation=$mutationHash verify=$verificationHash restore=$restorationHash"
    return [ordered]@{
        type = 'authorization_required'
        schema_version = 1
        scenario = $Scenario
        run_id = $RunId
        nonce = $Nonce
        target = $challengeTarget
        target_sha256 = $targetHash
        mutation = [string]$descriptions.mutation
        mutation_sha256 = $mutationHash
        verification = [string]$descriptions.verification
        verification_sha256 = $verificationHash
        restoration = [string]$descriptions.restoration
        restoration_sha256 = $restorationHash
        required_response = $required
    }
}

function Assert-ContainmentScenarioProjection {
    param([AllowNull()][object]$Projection, [ValidateSet('rhino','grasshopper')][string]$Scenario, [string]$Label)

    if ($Scenario -eq 'rhino') {
        Assert-ContainmentExactProperties -Value $Projection -Expected @('prior_active_document_runtime_serial','prior_path','prior_modified') -Label $Label
        if ($Projection.prior_active_document_runtime_serial -isnot [int] -or
            [int]$Projection.prior_active_document_runtime_serial -le 0 -or
            $Projection.prior_path -isnot [string] -or [string]$Projection.prior_path -cne '' -or
            $Projection.prior_modified -isnot [bool] -or [bool]$Projection.prior_modified) {
            throw "$Label type drift"
        }
    }
    else {
        Assert-ContainmentExactProperties -Value $Projection -Expected @('has_active_canvas','document_id') -Label $Label
        if ($Projection.has_active_canvas -isnot [bool] -or [bool]$Projection.has_active_canvas -or $null -ne $Projection.document_id) {
            throw "$Label type drift"
        }
    }
}

function Assert-ContainmentScratchProjection {
    param(
        [AllowNull()][object]$Projection,
        [ValidateSet('rhino','grasshopper')][string]$Scenario,
        [string]$ScratchPath,
        [AllowNull()][object]$Target,
        [string]$Label
    )

    if ($Scenario -eq 'rhino') {
        Assert-ContainmentExactProperties -Value $Projection -Expected @('runtime_serial','path','modified','object_count','object_ids') -Label $Label
        if ($Projection.runtime_serial -isnot [int] -or [int]$Projection.runtime_serial -le 0 -or
            $Projection.path -isnot [string] -or [string]$Projection.path -cne $ScratchPath -or
            $Projection.modified -isnot [bool] -or [bool]$Projection.modified -or
            $Projection.object_count -isnot [int] -or [int]$Projection.object_count -ne 0 -or
            @($Projection.object_ids).Count -ne 0) {
            throw "$Label type drift"
        }
        foreach ($id in @($Projection.object_ids)) {
            if ([string]$id -cnotmatch '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$') {
                throw "$Label object identity drift"
            }
        }
    }
    else {
        Assert-ContainmentExactProperties -Value $Projection -Expected @('document_id','has_active_canvas','gate_canvas_token','path','object_count','component_ids','wires','errors','warnings') -Label $Label
        [void](Assert-ContainmentHex $Projection.gate_canvas_token 64 "$Label canvas token")
        $expectedCanvasToken = Get-ContainmentValueSha256 -Value @(
            [int]$Target.process_id,[string]$Target.process_start_token,[int]$Target.port,
            $true,[string]$Projection.document_id
        )
        if ($Projection.has_active_canvas -isnot [bool] -or -not [bool]$Projection.has_active_canvas -or
            $Projection.document_id -isnot [string] -or [string]::IsNullOrWhiteSpace([string]$Projection.document_id) -or
            [string]$Projection.gate_canvas_token -cne $expectedCanvasToken -or
            $Projection.path -isnot [string] -or [string]$Projection.path -cne $ScratchPath -or
            $Projection.object_count -isnot [int] -or [int]$Projection.object_count -ne 0 -or
            @($Projection.component_ids).Count -ne 0 -or @($Projection.wires).Count -ne 0 -or
            $Projection.errors -isnot [int] -or [int]$Projection.errors -ne 0 -or
            $Projection.warnings -isnot [int] -or [int]$Projection.warnings -ne 0) {
            throw "$Label type drift"
        }
    }
}

function Get-ContainmentRhinoPointScript {
    param([string]$RunId)
    [void](Assert-ContainmentHex $RunId 32 'Rhino point run id')
    return "import Rhino`nimport scriptcontext as sc`npoint = Rhino.Geometry.Point3d(10.0, 0.0, 0.0)`nattributes = Rhino.DocObjects.ObjectAttributes()`nattributes.Name = `"RookContainmentPoint-$RunId`"`nobject_id = sc.doc.Objects.AddPoint(point, attributes)`nsc.doc.Views.Redraw()`nprint(`"ROOK_POINT_ID={0}`".format(object_id))"
}

function Assert-ContainmentScenarioOperationSequence {
    param(
        [ValidateSet('rhino','grasshopper')][string]$Scenario,
        [string[]]$Names
    )

    if ($Scenario -eq 'rhino') {
        $expected = @(
            'rhino_ping','rhino_execute','rhino_document','rhino_objects',
            'rhino_ping','rhino_execute','rhino_document','rhino_objects',
            'rhino_document_ops','rhino_execute','rhino_document','rhino_objects',
            'rhino_create','rhino_execute','rhino_objects','rhino_geometry','rhino_geometry','rhino_document',
            'rhino_execute','rhino_document','rhino_objects','rhino_delete',
            'rhino_execute','rhino_document','rhino_objects','rhino_document_ops',
            'rhino_execute','rhino_document','rhino_objects'
        )
        if (-not (Test-ContainmentCanonicalEqual -Left @($Names) -Right $expected)) {
            throw 'Rhino scenario operation sequence/count drift'
        }
        return
    }

    $cursor = 0
    $prefix = @(
        'rhino_ping','rhino_document','gh_status',
        'rhino_ping','rhino_document','gh_status',
        'rhino_command'
    )
    foreach ($expectedName in $prefix) {
        if ($cursor -ge $Names.Count -or $Names[$cursor] -cne $expectedName) {
            throw 'Grasshopper scenario operation prefix drift'
        }
        $cursor++
    }
    $readyPolls = 0
    while ($cursor -lt $Names.Count -and $Names[$cursor] -ceq 'gh_status' -and $readyPolls -lt 20) {
        $readyPolls++
        $cursor++
    }
    if ($readyPolls -lt 1) { throw 'Grasshopper readiness operation sequence is empty' }

    $forward = @('gh_document_open','gh_status','gh_snapshot','gh_errors','gh_library','gh_snapshot','gh_edit')
    foreach ($expectedName in $forward) {
        if ($cursor -ge $Names.Count -or $Names[$cursor] -cne $expectedName) {
            throw 'Grasshopper forward operation sequence drift'
        }
        $cursor++
    }

    $observationGroups = 0
    while ($cursor + 2 -lt $Names.Count -and
        $Names[$cursor] -ceq 'gh_snapshot' -and
        $Names[$cursor + 1] -ceq 'gh_errors' -and
        $Names[$cursor + 2] -ceq 'gh_status') {
        $observationGroups++
        $cursor += 3
    }
    if ($observationGroups -lt 2) {
        throw 'Grasshopper solve/restoration observation sequence is incomplete'
    }

    $undoCount = 0
    while ($cursor -lt $Names.Count) {
        if ($undoCount -ge 4 -or $Names[$cursor] -cne 'gh_undo' -or $cursor + 3 -ge $Names.Count -or
            $Names[$cursor + 1] -cne 'gh_snapshot' -or
            $Names[$cursor + 2] -cne 'gh_errors' -or
            $Names[$cursor + 3] -cne 'gh_status') {
            throw 'Grasshopper undo/restoration operation sequence drift'
        }
        $undoCount++
        $cursor += 4
    }
    if ($undoCount -lt 1 -or $cursor -ne $Names.Count) {
        throw 'Grasshopper operation sequence did not finish with verified undo restoration'
    }
}

function Get-ContainmentAliasedPropertyValue {
    param(
        [AllowNull()][object]$Value,
        [string[]]$Names,
        [string]$Label
    )

    if ($null -eq $Value) { throw "$Label parent value is null" }
    $matches = @($Value.PSObject.Properties | Where-Object {
        $propertyName = [string]$_.Name
        @($Names | Where-Object { [string]::Equals($_,$propertyName,[StringComparison]::OrdinalIgnoreCase) }).Count -ne 0
    })
    if ($matches.Count -ne 1) { throw "$Label property alias count drift" }
    return $matches[0].Value
}

function ConvertTo-ContainmentGhStatusProjection {
    param([AllowNull()][object]$Data, [string]$Label)

    $projection = [ordered]@{
        available = Get-ContainmentAliasedPropertyValue $Data @('available') "$Label available"
        has_active_canvas = Get-ContainmentAliasedPropertyValue $Data @('has_active_canvas','hasActiveCanvas') "$Label active canvas"
        has_active_document = Get-ContainmentAliasedPropertyValue $Data @('has_active_document','hasActiveDocument') "$Label active document"
        document_id = Get-ContainmentAliasedPropertyValue $Data @('document_id','documentId') "$Label document id"
        document_path = Get-ContainmentAliasedPropertyValue $Data @('document_path','documentPath') "$Label document path"
        object_count = Get-ContainmentAliasedPropertyValue $Data @('object_count','objectCount') "$Label object count"
        ready_for_edit = Get-ContainmentAliasedPropertyValue $Data @('ready_for_edit','readyForEdit') "$Label edit readiness"
        solver_enabled = Get-ContainmentAliasedPropertyValue $Data @('solver_enabled','solverEnabled') "$Label solver enabled"
        solver_state_known = Get-ContainmentAliasedPropertyValue $Data @('solver_state_known','solverStateKnown') "$Label solver state known"
        solution_state = Get-ContainmentAliasedPropertyValue $Data @('solution_state','solutionState') "$Label solution state"
    }
    if ($projection.available -isnot [bool] -or $projection.has_active_canvas -isnot [bool] -or
        $projection.has_active_document -isnot [bool] -or $projection.ready_for_edit -isnot [bool] -or
        $projection.solver_state_known -isnot [bool] -or
        ($null -ne $projection.solver_enabled -and $projection.solver_enabled -isnot [bool]) -or
        ($null -ne $projection.document_id -and $projection.document_id -isnot [string]) -or
        $projection.document_path -isnot [string] -or $projection.object_count -isnot [int] -or
        [int]$projection.object_count -lt 0 -or
        ($null -ne $projection.solution_state -and $projection.solution_state -isnot [string])) {
        throw "$Label Grasshopper status type drift"
    }
    return $projection
}

function Get-ContainmentGhStageLayout {
    param([string[]]$OperationNames)

    $openIndex = 0
    $editIndex = 0
    $firstUndoIndex = 0
    for ($position = 0; $position -lt $OperationNames.Count; $position++) {
        $oneBased = $position + 1
        if ($OperationNames[$position] -ceq 'gh_document_open') { $openIndex = $oneBased }
        if ($OperationNames[$position] -ceq 'gh_edit') { $editIndex = $oneBased }
        if ($firstUndoIndex -eq 0 -and $OperationNames[$position] -ceq 'gh_undo') { $firstUndoIndex = $oneBased }
    }
    if ($openIndex -le 0 -or $editIndex -le 0 -or $firstUndoIndex -le 0) {
        throw 'Grasshopper stage layout is incomplete'
    }
    return [pscustomobject]@{
        OpenIndex = $openIndex
        EditIndex = $editIndex
        FirstUndoIndex = $firstUndoIndex
        LastSettleSnapshotIndex = $firstUndoIndex - 6
        PreUndoSnapshotIndex = $firstUndoIndex - 3
        FinalUndoIndex = $OperationNames.Count - 3
        FinalSnapshotIndex = $OperationNames.Count - 2
        FinalErrorsIndex = $OperationNames.Count - 1
        FinalStatusIndex = $OperationNames.Count
    }
}

function Assert-ContainmentGhSnapshotState {
    param(
        [AllowNull()][object]$Data,
        [AllowNull()][object]$FinalProjection,
        [ValidateSet('empty','mutated','structural','bounded')][string]$ExpectedState,
        [string]$Label
    )

    foreach ($required in @('epoch','components','flows','diagnostics')) {
        if ($Data.PSObject.Properties.Name -cnotcontains $required) { throw "$Label snapshot omitted $required" }
    }
    if ($Data.epoch -isnot [int] -or $null -eq $Data.diagnostics -or
        $Data.diagnostics.PSObject.Properties.Name -cnotcontains 'errors' -or
        $Data.diagnostics.PSObject.Properties.Name -cnotcontains 'warnings' -or
        $Data.diagnostics.errors -isnot [int] -or $Data.diagnostics.warnings -isnot [int] -or
        [int]$Data.diagnostics.errors -ne 0 -or [int]$Data.diagnostics.warnings -ne 0) {
        throw "$Label snapshot epoch/diagnostics drift"
    }
    $components = @($Data.components)
    $flows = @($Data.flows)
    if ($ExpectedState -eq 'empty') {
        if ($components.Count -ne 0 -or $flows.Count -ne 0) { throw "$Label expected the restored empty projection" }
        return
    }
    if ($ExpectedState -eq 'mutated') {
        if (-not (Test-ContainmentCanonicalEqual -Left $components -Right @($FinalProjection.components)) -or
            -not (Test-ContainmentCanonicalEqual -Left $flows -Right @($FinalProjection.flows)) -or
            -not (Test-ContainmentCanonicalEqual -Left $Data.diagnostics -Right $FinalProjection.diagnostics)) {
            throw "$Label solved snapshot/final projection drift"
        }
        return
    }

    $expectedIds = @($FinalProjection.components | ForEach-Object { [string]$_.id })
    $actualIds = @($components | ForEach-Object { [string]$_.id })
    if ($actualIds.Count -gt 2 -or @($actualIds | Select-Object -Unique).Count -ne $actualIds.Count) {
        throw "$Label component identity count drift"
    }
    foreach ($id in $actualIds) {
        if ($expectedIds -cnotcontains $id) { throw "$Label contains an unknown component identity" }
    }
    foreach ($flow in $flows) {
        if (@($FinalProjection.flows) -cnotcontains [string]$flow) { throw "$Label contains an unknown wire" }
    }
    if ($ExpectedState -eq 'structural') {
        if ($actualIds.Count -ne 2 -or -not (Test-ContainmentCanonicalEqual -Left $flows -Right @($FinalProjection.flows))) {
            throw "$Label structural edit result is not the declared two-component mutation"
        }
        foreach ($expected in @($FinalProjection.components)) {
            $actual = @($components | Where-Object { [string]$_.id -ceq [string]$expected.id })
            if ($actual.Count -ne 1 -or [string]$actual[0].type -cne [string]$expected.type -or
                -not (Test-ContainmentCanonicalEqual -Left $actual[0].pos -Right $expected.pos)) {
                throw "$Label component structural identity drift"
            }
            if ([string]$expected.id -ceq 'C1' -and
                ([string]$actual[0].nick -cne [string]$expected.nick -or
                 -not (Test-ContainmentCanonicalEqual -Left $actual[0].value -Right $expected.value))) {
                throw "$Label slider structural settings drift"
            }
            if ([string]$expected.id -ceq 'C2' -and
                (([string]$actual[0].componentGuid).ToLowerInvariant() -cne ([string]$expected.componentGuid).ToLowerInvariant() -or
                 [string]$actual[0].name -cne [string]$expected.name -or
                 -not (Test-ContainmentCanonicalEqual -Left $actual[0].inputs -Right $expected.inputs))) {
                throw "$Label Sphere structural settings drift"
            }
        }
    }
}

function Assert-ContainmentScenarioFinalProjection {
    param(
        [ValidateSet('rhino','grasshopper')][string]$Scenario,
        [AllowNull()][object]$Verification,
        [AllowNull()][object]$PreState,
        [string]$ScratchPath,
        [string]$RunId
    )

    $projection = $Verification.projection
    if ($Scenario -eq 'rhino') {
        Assert-ContainmentExactProperties -Value $projection -Expected @('document','objects','object_ids') -Label 'Rhino final projection'
        Assert-ContainmentExactProperties -Value $projection.document -Expected @('path','object_count','modified') -Label 'Rhino final document projection'
        Assert-ContainmentExactProperties -Value $projection.objects -Expected @('sphere','point') -Label 'Rhino final objects projection'
        Assert-ContainmentExactProperties -Value $projection.objects.sphere -Expected @(
            'id','name','type','center','radius','bbox','face_count','edge_count','vertex_count',
            'is_solid','is_manifold','area','volume'
        ) -Label 'Rhino final sphere projection'
        Assert-ContainmentExactProperties -Value $projection.objects.sphere.bbox -Expected @('min','max') -Label 'Rhino final sphere bounds'
        Assert-ContainmentExactProperties -Value $projection.objects.point -Expected @('id','name','type','location') -Label 'Rhino final point projection'
        if ($projection.document.path -isnot [string] -or
            $projection.document.object_count -isnot [int] -or
            $projection.document.modified -isnot [bool] -or
            $projection.objects.sphere.id -isnot [string] -or
            $projection.objects.sphere.name -isnot [string] -or
            $projection.objects.sphere.type -isnot [string] -or
            -not (Test-ContainmentJsonNumber $projection.objects.sphere.radius) -or
            $projection.objects.sphere.face_count -isnot [int] -or
            $projection.objects.sphere.edge_count -isnot [int] -or
            $projection.objects.sphere.vertex_count -isnot [int] -or
            $projection.objects.sphere.is_solid -isnot [bool] -or
            $projection.objects.sphere.is_manifold -isnot [bool] -or
            -not (Test-ContainmentJsonNumber $projection.objects.sphere.area) -or
            -not (Test-ContainmentJsonNumber $projection.objects.sphere.volume) -or
            $projection.objects.point.id -isnot [string] -or
            $projection.objects.point.name -isnot [string] -or
            $projection.objects.point.type -isnot [string]) {
            throw 'Rhino final verification projection type drift'
        }
        if ([string]$projection.document.path -cne $ScratchPath -or [int]$projection.document.object_count -ne 2 -or
            -not [bool]$projection.document.modified -or @($projection.object_ids).Count -ne 2 -or
            [string]$projection.objects.sphere.id -cnotmatch '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$' -or
            [string]$projection.objects.point.id -cnotmatch '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$' -or
            [string]$projection.objects.sphere.id -ceq [string]$projection.objects.point.id -or
            [string]$projection.objects.sphere.name -cne "RookContainmentSphere-$RunId" -or
            [string]$projection.objects.point.name -cne "RookContainmentPoint-$RunId" -or
            [string]$projection.objects.sphere.type -cne 'Brep' -or [string]$projection.objects.point.type -cne 'Point' -or
            -not (Test-ContainmentCanonicalEqual -Left $projection.objects.sphere.center -Right @(0.0,0.0,0.0)) -or
            [double]$projection.objects.sphere.radius -ne 4.0 -or
            -not (Test-ContainmentCanonicalEqual -Left $projection.objects.sphere.bbox -Right ([ordered]@{min=@(-4,-4,-4);max=@(4,4,4)})) -or
            [int]$projection.objects.sphere.face_count -ne 1 -or
            [int]$projection.objects.sphere.edge_count -ne 1 -or
            [int]$projection.objects.sphere.vertex_count -ne 2 -or
            -not [bool]$projection.objects.sphere.is_solid -or
            -not [bool]$projection.objects.sphere.is_manifold -or
            [double]$projection.objects.sphere.area -ne 201.0619 -or
            [double]$projection.objects.sphere.volume -ne 268.0826 -or
            -not (Test-ContainmentCanonicalEqual -Left $projection.objects.point.location -Right @(10,0,0))) {
            throw 'Rhino final verification projection drift'
        }
        $expectedIds = @([string]$projection.objects.sphere.id,[string]$projection.objects.point.id) | Sort-Object
        $actualIds = @($projection.object_ids | ForEach-Object { [string]$_ }) | Sort-Object
        if (-not (Test-ContainmentCanonicalEqual -Left $actualIds -Right $expectedIds)) {
            throw 'Rhino final verification object identity drift'
        }
        return
    }

    Assert-ContainmentExactProperties -Value $projection -Expected @('components','flows','diagnostics','solve') -Label 'Grasshopper final projection'
    Assert-ContainmentExactProperties -Value $projection.solve -Expected @('edit','status') -Label 'Grasshopper final solve projection'
    Assert-ContainmentExactProperties -Value $projection.solve.edit -Expected @('solve_scheduled','solver_locked','solver_state_known','verification_deferred') -Label 'Grasshopper final edit solve projection'
    $status = ConvertTo-ContainmentGhStatusProjection -Data $projection.solve.status -Label 'Grasshopper final solve status'
    $components = @($projection.components)
    $slider = @($components | Where-Object { [string](Get-ContainmentAliasedPropertyValue $_ @('id') 'Grasshopper final component id') -ceq 'C1' })
    $sphere = @($components | Where-Object { [string](Get-ContainmentAliasedPropertyValue $_ @('id') 'Grasshopper final component id') -ceq 'C2' })
    if ($slider.Count -ne 1 -or $sphere.Count -ne 1) {
        throw 'Grasshopper final component identities drift'
    }
    $slider = $slider[0]
    $sphere = $sphere[0]
    $sliderValue = Get-ContainmentAliasedPropertyValue $slider @('value') 'Grasshopper final slider value'
    $sphereInputs = @(Get-ContainmentAliasedPropertyValue $sphere @('inputs') 'Grasshopper final Sphere inputs')
    $radiusInputs = @($sphereInputs | Where-Object {
        $candidateIndex = Get-ContainmentAliasedPropertyValue $_ @('idx') 'Grasshopper final Sphere input index'
        $candidateIndex -is [int] -and [int]$candidateIndex -eq 1
    })
    $sphereOutputs = @(Get-ContainmentAliasedPropertyValue $sphere @('outputs') 'Grasshopper final Sphere outputs')
    if ($radiusInputs.Count -ne 1 -or $sphereOutputs.Count -ne 1) {
        throw 'Grasshopper final Sphere input/output identity drift'
    }
    $radiusInput = $radiusInputs[0]
    $sphereOutput = $sphereOutputs[0]
    $sphereOutputData = Get-ContainmentAliasedPropertyValue $sphereOutput @('data') 'Grasshopper final Sphere output data'
    $sliderType = Get-ContainmentAliasedPropertyValue $slider @('type') 'Grasshopper final slider type'
    $sliderNick = Get-ContainmentAliasedPropertyValue $slider @('nick') 'Grasshopper final slider nickname'
    $sliderPosition = Get-ContainmentAliasedPropertyValue $slider @('pos') 'Grasshopper final slider position'
    $sliderIsParameter = Get-ContainmentAliasedPropertyValue $slider @('is_param','isParam') 'Grasshopper final slider parameter flag'
    $sliderValueType = Get-ContainmentAliasedPropertyValue $sliderValue @('type') 'Grasshopper final slider value type'
    $sliderValueValue = Get-ContainmentAliasedPropertyValue $sliderValue @('val') 'Grasshopper final slider value'
    $sliderMinimum = Get-ContainmentAliasedPropertyValue $sliderValue @('min') 'Grasshopper final slider minimum'
    $sliderMaximum = Get-ContainmentAliasedPropertyValue $sliderValue @('max') 'Grasshopper final slider maximum'
    $sphereType = Get-ContainmentAliasedPropertyValue $sphere @('type') 'Grasshopper final Sphere type'
    $sphereName = Get-ContainmentAliasedPropertyValue $sphere @('name') 'Grasshopper final Sphere name'
    $sphereGuid = Get-ContainmentAliasedPropertyValue $sphere @('componentGuid','component_guid') 'Grasshopper final Sphere GUID'
    $spherePosition = Get-ContainmentAliasedPropertyValue $sphere @('pos') 'Grasshopper final Sphere position'
    $radiusName = Get-ContainmentAliasedPropertyValue $radiusInput @('name') 'Grasshopper final radius input name'
    $radiusSources = Get-ContainmentAliasedPropertyValue $radiusInput @('sources') 'Grasshopper final radius source count'
    $outputIndex = Get-ContainmentAliasedPropertyValue $sphereOutput @('idx') 'Grasshopper final Sphere output index'
    $outputName = Get-ContainmentAliasedPropertyValue $sphereOutput @('name') 'Grasshopper final Sphere output name'
    $outputType = Get-ContainmentAliasedPropertyValue $sphereOutput @('type') 'Grasshopper final Sphere output type'
    $outputStructure = Get-ContainmentAliasedPropertyValue $sphereOutputData @('structure') 'Grasshopper final Sphere output structure'
    $outputCount = Get-ContainmentAliasedPropertyValue $sphereOutputData @('count') 'Grasshopper final Sphere output count'
    if ($projection.diagnostics.errors -isnot [int] -or $projection.diagnostics.warnings -isnot [int] -or
        $sliderType -isnot [string] -or $sliderNick -isnot [string] -or $sliderIsParameter -isnot [bool] -or
        $sliderValueType -isnot [string] -or $sliderValueValue -isnot [int] -or
        $sliderMinimum -isnot [int] -or $sliderMaximum -isnot [int] -or
        $sphereType -isnot [string] -or $sphereName -isnot [string] -or $sphereGuid -isnot [string] -or
        $radiusName -isnot [string] -or $radiusSources -isnot [int] -or
        $outputIndex -isnot [int] -or $outputName -isnot [string] -or $outputType -isnot [string] -or
        $outputStructure -isnot [string] -or $outputCount -isnot [int] -or
        $projection.solve.edit.solve_scheduled -isnot [bool] -or
        $projection.solve.edit.solver_locked -isnot [bool] -or
        $projection.solve.edit.solver_state_known -isnot [bool] -or
        $projection.solve.edit.verification_deferred -isnot [bool]) {
        throw 'Grasshopper final verification projection type drift'
    }
    if (@($projection.components).Count -ne 2 -or
        -not (Test-ContainmentCanonicalEqual -Left @($projection.flows) -Right @('C1.O0>C2.I1')) -or
        [int]$projection.diagnostics.errors -ne 0 -or [int]$projection.diagnostics.warnings -ne 0 -or
        [string]$sliderType -cne 'NumberSlider' -or [string]$sliderNick -cne "RookContainmentRadius-$RunId" -or
        -not (Test-ContainmentCanonicalEqual -Left $sliderPosition -Right @(100,100)) -or -not [bool]$sliderIsParameter -or
        [string]$sliderValueType -cne 'slider' -or [int]$sliderValueValue -ne 4 -or
        [int]$sliderMinimum -ne 1 -or [int]$sliderMaximum -ne 9 -or
        [string]$sphereType -cne 'Component' -or [string]$sphereName -cne 'Sphere' -or
        ([string]$sphereGuid).ToLowerInvariant() -cne 'dabc854d-f50e-408a-b001-d043c7de151d' -or
        -not (Test-ContainmentCanonicalEqual -Left $spherePosition -Right @(400,100)) -or
        [string]$radiusName -cne 'Radius' -or [int]$radiusSources -ne 1 -or
        [int]$outputIndex -ne 0 -or [string]$outputName -cne 'Sphere' -or [string]$outputType -cne 'Sphere' -or
        [string]$outputStructure -cne 'single' -or [int]$outputCount -ne 1 -or
        -not [bool]$projection.solve.edit.solve_scheduled -or [bool]$projection.solve.edit.solver_locked -or
        -not [bool]$projection.solve.edit.solver_state_known -or -not [bool]$projection.solve.edit.verification_deferred -or
        -not [bool]$status.available -or -not [bool]$status.has_active_canvas -or -not [bool]$status.has_active_document -or
        [string]$status.document_id -cne [string]$PreState.scratch_projection.document_id -or
        [string]$status.document_path -cne $ScratchPath -or [int]$status.object_count -ne 2 -or
        -not [bool]$status.ready_for_edit -or -not [bool]$status.solver_enabled -or
        -not [bool]$status.solver_state_known -or [string]$status.solution_state -cne 'PostProcess') {
        throw 'Grasshopper final verification projection drift'
    }
}

function Assert-ContainmentScenarioArguments {
    param(
        [ValidateSet('rhino','grasshopper')][string]$Scenario,
        [string]$Name,
        [AllowNull()][object]$Arguments,
        [string]$RunId,
        [string]$ScratchPath,
        [AllowNull()][object]$Verification,
        [ValidateRange(1,1000)][int]$OperationIndex,
        [string[]]$OperationNames,
        [AllowNull()][object]$PreviousResult,
        [string]$Label
    )

    $emptyNames = @('rhino_ping','rhino_document','gh_status','gh_snapshot','gh_errors','gh_undo')
    if ($emptyNames -ccontains $Name) {
        if (@($Arguments.PSObject.Properties).Count -ne 0) { throw "$Label arguments are not the exact empty mapping" }
        return
    }
    if ($Name -eq 'rhino_objects') {
        $expected = [ordered]@{limit=500;offset=0}
        if (-not (Test-ContainmentCanonicalEqual $Arguments $expected)) { throw "$Label arguments drift" }
        return
    }
    if ($Name -eq 'rhino_document_ops') {
        $expected = [ordered]@{action='save';path=$ScratchPath}
        if (-not (Test-ContainmentCanonicalEqual $Arguments $expected)) { throw "$Label arguments drift" }
        return
    }
    if ($Name -eq 'rhino_create') {
        $expected = [ordered]@{type='SPHERE';center=@(0,0,0);radius=4;name="RookContainmentSphere-$RunId"}
        if (-not (Test-ContainmentCanonicalEqual $Arguments $expected)) { throw "$Label arguments drift" }
        return
    }
    if ($Name -eq 'rhino_execute') {
        Assert-ContainmentExactProperties -Value $Arguments -Expected @('code') -Label "$Label arguments"
        $runtimeSerial = "import Rhino`nprint('ROOK_DOC_RUNTIME_SERIAL={0}'.format(Rhino.RhinoDoc.ActiveDoc.RuntimeSerialNumber))"
        $point = Get-ContainmentRhinoPointScript $RunId
        $expectedCode = if ($OperationIndex -eq 14) { $point } else { $runtimeSerial }
        if ([string]$Arguments.code -cne $expectedCode) { throw "$Label code/stage drift" }
        return
    }
    if ($Name -eq 'rhino_geometry') {
        Assert-ContainmentExactProperties -Value $Arguments -Expected @('id') -Label "$Label arguments"
        $expectedId = if ($OperationIndex -eq 16) {
            [string]$Verification.projection.objects.sphere.id
        } elseif ($OperationIndex -eq 17) {
            [string]$Verification.projection.objects.point.id
        } else { $null }
        if ($null -eq $expectedId -or ([string]$Arguments.id).ToLowerInvariant() -cne $expectedId.ToLowerInvariant()) {
            throw "$Label geometry identity/stage is not bound to final verification"
        }
        return
    }
    if ($Name -eq 'rhino_delete') {
        Assert-ContainmentExactProperties -Value $Arguments -Expected @('ids') -Label "$Label arguments"
        $expectedIds = @($Verification.projection.object_ids | Sort-Object)
        $actualIds = @($Arguments.ids | Sort-Object)
        if (-not (Test-ContainmentCanonicalEqual $actualIds $expectedIds)) { throw "$Label delete set drift" }
        return
    }
    if ($Name -eq 'rhino_command') {
        $expected = [ordered]@{command='_Grasshopper';echo=$false}
        if (-not (Test-ContainmentCanonicalEqual $Arguments $expected)) { throw "$Label arguments drift" }
        return
    }
    if ($Name -eq 'gh_document_open') {
        $expected = [ordered]@{path=$ScratchPath}
        if (-not (Test-ContainmentCanonicalEqual $Arguments $expected)) { throw "$Label arguments drift" }
        return
    }
    if ($Name -eq 'gh_library') {
        $expected = [ordered]@{search='Sphere';exact=$true}
        if (-not (Test-ContainmentCanonicalEqual $Arguments $expected)) { throw "$Label arguments drift" }
        return
    }
    if ($Name -eq 'gh_edit') {
        Assert-ContainmentExactProperties -Value $Arguments -Expected @('epoch','create','connect') -Label "$Label arguments"
        if ($Arguments.epoch -isnot [int] -or $null -eq $PreviousResult -or
            $PreviousResult.data.epoch -isnot [int] -or [int]$Arguments.epoch -ne [int]$PreviousResult.data.epoch) {
            throw "$Label epoch/edit-base snapshot drift"
        }
        $expected = [ordered]@{
            epoch=[int]$Arguments.epoch
            create=@(
                [ordered]@{temp_id='T1';type='slider';nick="RookContainmentRadius-$RunId";min=1;max=9;value=4;pos=@(100,100)},
                [ordered]@{temp_id='T2';guid='dabc854d-f50e-408a-b001-d043c7de151d';pos=@(400,100)}
            )
            connect=@('T1.O0>T2.I1')
        }
        if (-not (Test-ContainmentCanonicalEqual $Arguments $expected)) { throw "$Label edit arguments drift" }
        return
    }
    throw "$Label used an unrecognized code-owned argument contract"
}

function Assert-ContainmentScenarioResult {
    param(
        [ValidateSet('rhino','grasshopper')][string]$Scenario,
        [string]$Name,
        [AllowNull()][object]$Arguments,
        [AllowNull()][object]$Result,
        [AllowNull()][object]$Verification,
        [AllowNull()][object]$PreState,
        [string]$ScratchPath,
        [string]$RunId,
        [ValidateRange(1,1000)][int]$OperationIndex,
        [string[]]$OperationNames,
        [string]$Label
    )

    Assert-ContainmentExactProperties -Value $Result -Expected @('success','data') -Label "$Label result envelope"
    if ($Result.success -isnot [bool] -or -not [bool]$Result.success -or $null -eq $Result.data) {
        throw "$Label result envelope is not an exact success"
    }
    $data = $Result.data
    if ($Name -eq 'rhino_ping') {
        Assert-ContainmentExactProperties -Value $data -Expected @('pong') -Label "$Label data"
        if ($data.pong -isnot [bool] -or -not [bool]$data.pong) { throw "$Label ping result drift" }
        return
    }
    if ($Name -eq 'rhino_document') {
        foreach ($required in @('name','path','objectCount','modified')) {
            if ($data.PSObject.Properties.Name -cnotcontains $required) { throw "$Label document result omitted $required" }
        }
        $expectedDocument = $null
        if ($Scenario -eq 'grasshopper' -and $OperationIndex -in @(2,5)) {
            $expectedDocument = [ordered]@{path='';objectCount=0;modified=$false}
        }
        elseif ($Scenario -eq 'rhino') {
            if ($OperationIndex -in @(3,7)) {
                $expectedDocument = [ordered]@{
                    path=[string]$PreState.host_projection.prior_path;objectCount=0
                    modified=[bool]$PreState.host_projection.prior_modified
                }
            }
            elseif ($OperationIndex -in @(11,28)) {
                $expectedDocument = [ordered]@{
                    path=[string]$PreState.scratch_projection.path
                    objectCount=[int]$PreState.scratch_projection.object_count
                    modified=[bool]$PreState.scratch_projection.modified
                }
            }
            elseif ($OperationIndex -in @(18,20)) {
                $expectedDocument = [ordered]@{
                    path=[string]$Verification.projection.document.path
                    objectCount=[int]$Verification.projection.document.object_count
                    modified=[bool]$Verification.projection.document.modified
                }
            }
            elseif ($OperationIndex -eq 24) {
                $expectedDocument = [ordered]@{path=$ScratchPath;objectCount=0;modified=$true}
            }
        }
        if ($null -eq $expectedDocument -or $data.path -isnot [string] -or $data.objectCount -isnot [int] -or
            $data.modified -isnot [bool] -or [string]$data.path -cne [string]$expectedDocument.path -or
            [int]$data.objectCount -ne [int]$expectedDocument.objectCount -or
            [bool]$data.modified -ne [bool]$expectedDocument.modified) {
            throw "$Label document result/stage projection drift"
        }
        return
    }
    if ($Name -eq 'rhino_objects') {
        Assert-ContainmentExactProperties -Value $data -Expected @('objects','count') -Label "$Label data"
        if ($data.count -isnot [int] -or [int]$data.count -ne @($data.objects).Count) {
            throw "$Label object result count drift"
        }
        $expectedIds = @($Verification.projection.object_ids | ForEach-Object { ([string]$_).ToLowerInvariant() } | Sort-Object)
        $actualIds = @($data.objects | ForEach-Object { ([string]$_.id).ToLowerInvariant() } | Sort-Object)
        $expectsMutation = $OperationIndex -in @(15,21)
        if ($expectsMutation) {
            if (-not (Test-ContainmentCanonicalEqual -Left $actualIds -Right $expectedIds)) {
                throw "$Label object result does not match the mutated-stage identities"
            }
            foreach ($expectedObject in @($Verification.projection.objects.sphere,$Verification.projection.objects.point)) {
                $actualObject = @($data.objects | Where-Object { ([string]$_.id).ToLowerInvariant() -ceq ([string]$expectedObject.id).ToLowerInvariant() })
                if ($actualObject.Count -ne 1 -or [string]$actualObject[0].name -cne [string]$expectedObject.name -or
                    [string]$actualObject[0].type -cne [string]$expectedObject.type) {
                    throw "$Label object result/final projection identity drift"
                }
            }
        }
        elseif ($actualIds.Count -ne 0) {
            throw "$Label object result was not empty in a pre/restored stage"
        }
        return
    }
    if ($Name -eq 'rhino_document_ops') {
        Assert-ContainmentExactProperties -Value $data -Expected @('saved','path') -Label "$Label data"
        if (-not [bool]$data.saved -or [string]$data.path -cne $ScratchPath) { throw "$Label save result drift" }
        return
    }
    if ($Name -eq 'rhino_create') {
        Assert-ContainmentExactProperties -Value $data -Expected @('id') -Label "$Label data"
        if ([string]$data.id -cne [string]$Verification.projection.objects.sphere.id) { throw "$Label created sphere identity drift" }
        return
    }
    if ($Name -eq 'rhino_execute') {
        Assert-ContainmentExactProperties -Value $data -Expected @('output') -Label "$Label data"
        $pointScript = Get-ContainmentRhinoPointScript -RunId $RunId
        if ([string]$Arguments.code -ceq $pointScript) {
            if ([string]$data.output -cnotmatch '^ROOK_POINT_ID=([0-9a-fA-F-]{36})\r?\n$' -or
                $Matches[1].ToLowerInvariant() -cne [string]$Verification.projection.objects.point.id) {
                throw "$Label point result/final projection drift"
            }
        }
        elseif ([string]$data.output -cnotmatch '^ROOK_DOC_RUNTIME_SERIAL=([0-9]+)\r?\n$' -or
            [int]$Matches[1] -ne [int]$PreState.scratch_projection.runtime_serial -or
            [int]$Matches[1] -ne [int]$PreState.host_projection.prior_active_document_runtime_serial) {
            throw "$Label runtime-serial result/pre-state drift"
        }
        return
    }
    if ($Name -eq 'rhino_geometry') {
        $id = ([string]$data.id).ToLowerInvariant()
        $finalObject = if ($id -ceq [string]$Verification.projection.objects.sphere.id) {
            $Verification.projection.objects.sphere
        } elseif ($id -ceq [string]$Verification.projection.objects.point.id) {
            $Verification.projection.objects.point
        } else { $null }
        if ($null -eq $finalObject -or [string]$data.name -cne [string]$finalObject.name -or
            [string]$data.type -cne [string]$finalObject.type) { throw "$Label geometry result identity drift" }
        if ($id -ceq [string]$Verification.projection.objects.sphere.id) {
            if (-not (Test-ContainmentCanonicalEqual -Left $data.bbox -Right $finalObject.bbox) -or
                [string]$data.geometry.type -cne 'Brep' -or [int]$data.geometry.faceCount -ne [int]$finalObject.face_count -or
                [int]$data.geometry.edgeCount -ne [int]$finalObject.edge_count -or [int]$data.geometry.vertexCount -ne [int]$finalObject.vertex_count -or
                [bool]$data.geometry.isSolid -ne [bool]$finalObject.is_solid -or [bool]$data.geometry.isManifold -ne [bool]$finalObject.is_manifold -or
                [double]$data.geometry.area -ne [double]$finalObject.area -or [double]$data.geometry.volume -ne [double]$finalObject.volume) {
                throw "$Label sphere geometry result/final projection drift"
            }
        }
        elseif (-not (Test-ContainmentCanonicalEqual -Left $data.geometry.location -Right $finalObject.location) -or
            -not (Test-ContainmentCanonicalEqual -Left $data.bbox -Right ([ordered]@{min=@(10,0,0);max=@(10,0,0)}))) {
            throw "$Label point geometry result/final projection drift"
        }
        return
    }
    if ($Name -eq 'rhino_delete') {
        Assert-ContainmentExactProperties -Value $data -Expected @('deleted') -Label "$Label data"
        if ([int]$data.deleted -ne @($Arguments.ids).Count -or [int]$data.deleted -ne 2) { throw "$Label delete result drift" }
        return
    }
    if ($Name -eq 'rhino_command') {
        Assert-ContainmentExactProperties -Value $data -Expected @('executed') -Label "$Label data"
        if (-not [bool]$data.executed) { throw "$Label Grasshopper bootstrap result drift" }
        return
    }
    if ($Name -eq 'gh_document_open') {
        foreach ($required in @('opened','path','objectCount')) {
            if ($data.PSObject.Properties.Name -cnotcontains $required) { throw "$Label open result omitted $required" }
        }
        if (-not [bool]$data.opened -or [string]$data.path -cne $ScratchPath -or [int]$data.objectCount -ne 0) {
            throw "$Label Grasshopper open result drift"
        }
        return
    }
    if ($Name -eq 'gh_library') {
        Assert-ContainmentExactProperties -Value $data -Expected @('count','components') -Label "$Label data"
        if ([int]$data.count -ne 1 -or @($data.components).Count -ne 1 -or
            ([string]$data.components[0].guid).ToLowerInvariant() -cne 'dabc854d-f50e-408a-b001-d043c7de151d') {
            throw "$Label Grasshopper library result drift"
        }
        return
    }
    if ($Name -eq 'gh_errors') {
        foreach ($required in @('totalComponents','errorCount','warningCount','errors','warnings')) {
            if ($data.PSObject.Properties.Name -cnotcontains $required) { throw "$Label error result omitted $required" }
        }
        $layout = Get-ContainmentGhStageLayout -OperationNames $OperationNames
        $expectedCount = $null
        if ($OperationIndex -lt $layout.EditIndex) { $expectedCount = 0 }
        if ($OperationIndex -in @(([int]$layout.LastSettleSnapshotIndex + 1),([int]$layout.PreUndoSnapshotIndex + 1))) { $expectedCount = 2 }
        if ($OperationIndex -eq $layout.FinalErrorsIndex) { $expectedCount = 0 }
        if ($data.totalComponents -isnot [int] -or [int]$data.totalComponents -notin @(0,2) -or
            ($null -ne $expectedCount -and [int]$data.totalComponents -ne [int]$expectedCount) -or
            [int]$data.errorCount -ne @($data.errors).Count -or [int]$data.warningCount -ne @($data.warnings).Count -or
            [int]$data.errorCount -ne 0 -or [int]$data.warningCount -ne 0) { throw "$Label Grasshopper error result/stage drift" }
        return
    }
    if ($Name -eq 'gh_snapshot') {
        $layout = Get-ContainmentGhStageLayout -OperationNames $OperationNames
        $expectedState = 'bounded'
        if ($OperationIndex -in @(([int]$layout.OpenIndex + 2),([int]$layout.EditIndex - 1),[int]$layout.FinalSnapshotIndex)) { $expectedState = 'empty' }
        if ($OperationIndex -in @($layout.LastSettleSnapshotIndex,$layout.PreUndoSnapshotIndex)) { $expectedState = 'mutated' }
        Assert-ContainmentGhSnapshotState -Data $data -FinalProjection $Verification.projection -ExpectedState $expectedState -Label $Label
        return
    }
    if ($Name -eq 'gh_edit') {
        $layout = Get-ContainmentGhStageLayout -OperationNames $OperationNames
        if ($OperationIndex -ne $layout.EditIndex -or $data.PSObject.Properties.Name -cnotcontains 'edit_summary') {
            throw "$Label edit operation/stage drift"
        }
        Assert-ContainmentGhSnapshotState -Data $data -FinalProjection $Verification.projection -ExpectedState structural -Label $Label
        $summary = $data.edit_summary
        foreach ($required in @('created','connected','solve_scheduled','solver_locked','solver_state_known','verification_deferred','errors')) {
            if ($summary.PSObject.Properties.Name -cnotcontains $required) { throw "$Label edit summary omitted $required" }
        }
        if ([int]$data.epoch -le [int]$Arguments.epoch -or [int]$summary.created -ne 2 -or [int]$summary.connected -ne 1 -or
            $null -ne $summary.errors -or
            [bool]$summary.solve_scheduled -ne [bool]$Verification.projection.solve.edit.solve_scheduled -or
            [bool]$summary.solver_locked -ne [bool]$Verification.projection.solve.edit.solver_locked -or
            [bool]$summary.solver_state_known -ne [bool]$Verification.projection.solve.edit.solver_state_known -or
            [bool]$summary.verification_deferred -ne [bool]$Verification.projection.solve.edit.verification_deferred) {
            throw "$Label edit result/final projection drift"
        }
        return
    }
    if ($Name -eq 'gh_status') {
        $status = ConvertTo-ContainmentGhStatusProjection -Data $data -Label $Label
        $layout = Get-ContainmentGhStageLayout -OperationNames $OperationNames
        if ($OperationIndex -in @(3,6)) {
            if ([bool]$status.available -or [bool]$status.has_active_canvas -or [bool]$status.has_active_document -or
                $null -ne $status.document_id -or [string]$status.document_path -cne '' -or
                [int]$status.object_count -ne 0 -or [bool]$status.ready_for_edit) {
                throw "$Label Grasshopper preflight status/stage drift"
            }
            return
        }
        if ($OperationIndex -ge 8 -and $OperationIndex -lt $layout.OpenIndex) {
            if ([int]$status.object_count -ne 0 -or [string]$status.document_path -cne '') {
                throw "$Label Grasshopper readiness status mutated scratch state"
            }
            if ($OperationIndex -eq ($layout.OpenIndex - 1) -and
                (-not [bool]$status.available -or -not [bool]$status.has_active_canvas -or
                 -not [bool]$status.has_active_document -or -not [bool]$status.ready_for_edit -or
                 [string]::IsNullOrWhiteSpace([string]$status.document_id) -or
                 [string]$status.document_id -ceq [string]$PreState.scratch_projection.document_id)) {
                throw "$Label Grasshopper final readiness status drift"
            }
            return
        }
        if ($OperationIndex -eq ($layout.OpenIndex + 1)) {
            if (-not [bool]$status.available -or -not [bool]$status.has_active_canvas -or -not [bool]$status.has_active_document -or
                [string]$status.document_id -cne [string]$PreState.scratch_projection.document_id -or
                [string]$status.document_path -cne $ScratchPath -or [int]$status.object_count -ne 0 -or
                -not [bool]$status.ready_for_edit) {
                throw "$Label Grasshopper opened-scratch status drift"
            }
            return
        }
        if ($OperationIndex -in @(([int]$layout.LastSettleSnapshotIndex + 2),([int]$layout.PreUndoSnapshotIndex + 2))) {
            if (-not (Test-ContainmentCanonicalEqual -Left $status -Right $Verification.projection.solve.status)) {
                throw "$Label Grasshopper mutated status/final projection drift"
            }
            return
        }
        if ($OperationIndex -eq $layout.FinalStatusIndex) {
            if (-not [bool]$status.available -or -not [bool]$status.has_active_canvas -or -not [bool]$status.has_active_document -or
                [string]$status.document_id -cne [string]$PreState.scratch_projection.document_id -or
                [string]$status.document_path -cne $ScratchPath -or [int]$status.object_count -ne 0 -or
                -not [bool]$status.ready_for_edit) {
                throw "$Label Grasshopper restored status/pre-state drift"
            }
            return
        }
        if ([string]$status.document_id -cne [string]$PreState.scratch_projection.document_id -or
            [string]$status.document_path -cne $ScratchPath -or [int]$status.object_count -notin @(0,2)) {
            throw "$Label Grasshopper bounded observation status drift"
        }
        return
    }
    if ($Name -eq 'gh_undo') {
        foreach ($required in @('message','epoch','snapshot')) {
            if ($data.PSObject.Properties.Name -cnotcontains $required) { throw "$Label undo result omitted $required" }
        }
        $layout = Get-ContainmentGhStageLayout -OperationNames $OperationNames
        if ([string]$data.message -cne 'Undo successful' -or $data.epoch -isnot [int] -or
            $null -eq $data.snapshot -or $data.snapshot.PSObject.Properties.Name -cnotcontains 'components' -or
            $data.snapshot.PSObject.Properties.Name -cnotcontains 'flows') { throw "$Label undo result schema drift" }
        if ($OperationIndex -eq $layout.FinalUndoIndex -and
            (@($data.snapshot.components).Count -ne 0 -or @($data.snapshot.flows).Count -ne 0)) {
            throw "$Label undo result/restored projection drift"
        }
        foreach ($component in @($data.snapshot.components)) {
            if (@($Verification.projection.components | ForEach-Object { [string]$_.id }) -cnotcontains [string]$component.id) {
                throw "$Label undo result contains an unknown component"
            }
        }
        foreach ($flow in @($data.snapshot.flows)) {
            if (@($Verification.projection.flows) -cnotcontains [string]$flow) { throw "$Label undo result contains an unknown wire" }
        }
        return
    }
    throw "$Label result used an unrecognized admitted tool"
}

function Get-ContainmentRhinoPreflightProjection {
    param([object[]]$OperationResults, [int]$Offset, [string]$Label)

    if ($Offset -lt 0 -or $Offset + 3 -ge $OperationResults.Count) {
        throw "$Label operation range is incomplete"
    }
    $serialOutput = [string]$OperationResults[$Offset + 1].data.output
    if ($serialOutput -cnotmatch '^ROOK_DOC_RUNTIME_SERIAL=([0-9]+)\r?\n$') {
        throw "$Label runtime serial output drift"
    }
    $runtimeSerial = [int]$Matches[1]
    $document = $OperationResults[$Offset + 2].data
    $objects = $OperationResults[$Offset + 3].data
    $objectIds = @($objects.objects | ForEach-Object { ([string]$_.id).ToLowerInvariant() } | Sort-Object)
    return [ordered]@{
        runtime_serial=$runtimeSerial
        path=[string]$document.path
        object_count=[int]$document.objectCount
        modified=[bool]$document.modified
        object_ids=$objectIds
    }
}

function Get-ContainmentGrasshopperPreflightProjection {
    param([object[]]$OperationResults, [int]$Offset, [string]$Label)

    if ($Offset -lt 0 -or $Offset + 2 -ge $OperationResults.Count) {
        throw "$Label operation range is incomplete"
    }
    $document = $OperationResults[$Offset + 1].data
    $status = ConvertTo-ContainmentGhStatusProjection -Data $OperationResults[$Offset + 2].data -Label "$Label Grasshopper status"
    return [ordered]@{
        rhino=[ordered]@{
            path=[string]$document.path
            object_count=[int]$document.objectCount
            modified=[bool]$document.modified
        }
        grasshopper=$status
    }
}

function Assert-ContainmentScenarioPreflightBinding {
    param(
        [ValidateSet('rhino','grasshopper')][string]$Scenario,
        [object[]]$OperationResults,
        [AllowNull()][object]$Authorization,
        [AllowNull()][object]$PreState
    )

    if ($Scenario -eq 'rhino') {
        $first = Get-ContainmentRhinoPreflightProjection -OperationResults $OperationResults -Offset 0 -Label 'initial Rhino preflight'
        $second = Get-ContainmentRhinoPreflightProjection -OperationResults $OperationResults -Offset 4 -Label 'post-authorization Rhino preflight'
        $expected = [ordered]@{
            runtime_serial=[int]$first.runtime_serial;path='';object_count=0;modified=$false;object_ids=@()
        }
        if (-not (Test-ContainmentCanonicalEqual -Left $first -Right $expected) -or
            -not (Test-ContainmentCanonicalEqual -Left $second -Right $expected) -or
            [int]$PreState.host_projection.prior_active_document_runtime_serial -ne [int]$first.runtime_serial -or
            [int]$PreState.scratch_projection.runtime_serial -ne [int]$first.runtime_serial) {
            throw 'Rhino preflight operation projections are not the fixed empty/clean state'
        }
    }
    else {
        $first = Get-ContainmentGrasshopperPreflightProjection -OperationResults $OperationResults -Offset 0 -Label 'initial Grasshopper preflight'
        $second = Get-ContainmentGrasshopperPreflightProjection -OperationResults $OperationResults -Offset 3 -Label 'post-authorization Grasshopper preflight'
        $expectedRhino = [ordered]@{path='';object_count=0;modified=$false}
        if (-not (Test-ContainmentCanonicalEqual -Left $first.rhino -Right $expectedRhino) -or
            -not (Test-ContainmentCanonicalEqual -Left $second.rhino -Right $expectedRhino) -or
            -not (Test-ContainmentCanonicalEqual -Left $first -Right $second) -or
            [bool]$first.grasshopper.available -or [bool]$first.grasshopper.has_active_canvas -or
            [bool]$first.grasshopper.has_active_document -or $null -ne $first.grasshopper.document_id -or
            [string]$first.grasshopper.document_path -cne '' -or [int]$first.grasshopper.object_count -ne 0 -or
            [bool]$first.grasshopper.ready_for_edit) {
            throw 'Grasshopper preflight operation projections are not the fixed absent/empty state'
        }
    }
    $firstHash = Get-ContainmentValueSha256 $first
    $secondHash = Get-ContainmentValueSha256 $second
    if ([string]$Authorization.preflight_sha256 -cne $firstHash -or
        [string]$Authorization.pre_mutation_sha256 -cne $secondHash -or
        $firstHash -cne $secondHash) {
        throw "$Scenario authorization preflight/pre-mutation digest binding drift"
    }
    return $true
}

function Read-AndValidateScenarioEvidence {
    param(
        [ValidateSet('rhino','grasshopper')][string]$Scenario,
        [Parameter(Mandatory = $true)][string]$ScenarioPath,
        [Parameter(Mandatory = $true)][string]$ScenarioSidecarPath,
        [Parameter(Mandatory = $true)][string]$ExpectedInstalledRoot
    )

    $root = Get-ContainmentCanonicalPath -Path (Split-Path -Parent $ScenarioPath) -Kind Container -Label "$Scenario scenario evidence root"
    $expectedRoot = Get-ContainmentCanonicalPath -Path $ExpectedInstalledRoot -Kind Container -Label 'expected installed root'
    if (-not (Test-ContainmentSamePath $ScenarioPath (Join-Path $root "$Scenario-scenario.json")) -or
        -not (Test-ContainmentSamePath $ScenarioSidecarPath (Join-Path $root "$Scenario-scenario.sha256"))) {
        throw "$Scenario scenario final evidence path mismatch"
    }
    $evidence = Read-ContainmentCanonicalJsonFile -Path $ScenarioPath -Label "$Scenario scenario evidence"
    [void](Assert-ContainmentSidecar -SidecarPath $ScenarioSidecarPath -TargetPath $ScenarioPath -DigestOnly -Label "$Scenario scenario evidence")
    Assert-ContainmentExactProperties `
        -Value $evidence `
        -Expected @('schema_version','scenario','success','failure_label','run_id','started_at','ended_at','runtime','target','authorization','pre_state','operations','verification','restoration','telemetry','artifacts','diagnostics') `
        -Label "$Scenario scenario evidence"
    if ($evidence.schema_version -isnot [int] -or [int]$evidence.schema_version -ne 1 -or
        $evidence.scenario -isnot [string] -or [string]$evidence.scenario -cne $Scenario -or
        $evidence.success -isnot [bool] -or
        $evidence.run_id -isnot [string] -or
        $evidence.started_at -isnot [string] -or $evidence.ended_at -isnot [string] -or
        $evidence.operations -isnot [array] -or $evidence.artifacts -isnot [array] -or
        $evidence.diagnostics -isnot [array]) {
        throw "$Scenario scenario evidence schema drift"
    }
    [void](Assert-ContainmentHex $evidence.run_id 32 "$Scenario scenario run id")
    if (-not (Test-ContainmentUtcTimestamp $evidence.started_at) -or
        -not (Test-ContainmentUtcTimestamp $evidence.ended_at) -or
        [string]$evidence.ended_at -clt [string]$evidence.started_at) {
        throw "$Scenario scenario timestamp drift"
    }
    if (-not [bool]$evidence.success -or $null -ne $evidence.failure_label) {
        throw "$Scenario scenario evidence is not successful"
    }

    $runtime = $evidence.runtime
    Assert-ContainmentExactProperties -Value $runtime -Expected @('python_executable','installed_root','cwd','sys_path','rook_origins') -Label 'scenario runtime'
    if ($runtime.python_executable -isnot [string] -or $runtime.installed_root -isnot [string] -or
        $runtime.cwd -isnot [string] -or $runtime.sys_path -isnot [array] -or
        $runtime.rook_origins -isnot [pscustomobject] -or
        -not [IO.Path]::IsPathRooted([string]$runtime.python_executable) -or
        -not [IO.Path]::IsPathRooted([string]$runtime.cwd) -or
        -not (Test-ContainmentSamePath ([string]$runtime.installed_root) $expectedRoot)) {
        throw 'scenario runtime installed origin mismatch'
    }
    $installedPrefix = $expectedRoot.TrimEnd('\') + '\'
    if (@($runtime.rook_origins.PSObject.Properties).Count -eq 0) { throw 'scenario runtime has no Rook origins' }
    foreach ($originProperty in $runtime.rook_origins.PSObject.Properties) {
        if ($originProperty.Value -isnot [string]) { throw 'scenario runtime Rook origin type drift' }
        $origin = [IO.Path]::GetFullPath([string]$originProperty.Value)
        if (-not $origin.StartsWith($installedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'scenario runtime Rook origin escaped the installed root'
        }
    }
    foreach ($pathEntry in @($runtime.sys_path)) {
        if ($pathEntry -isnot [string]) { throw 'scenario runtime sys.path type drift' }
        $normalized = ([string]$pathEntry).Replace('\','/').ToLowerInvariant()
        if ($normalized.Contains('/.worktrees/') -or $normalized.EndsWith('/mcp_server/src')) {
            throw 'scenario runtime sys.path retained a development source root'
        }
    }

    $target = $evidence.target
    Assert-ContainmentExactProperties -Value $target -Expected @('process_id','port','process_start_token','discovery_record_sha256','scratch_path','ownership_certain') -Label 'scenario target'
    if ($target.process_id -isnot [int] -or $target.port -isnot [int] -or
        $target.process_start_token -isnot [string] -or $target.discovery_record_sha256 -isnot [string] -or
        $target.scratch_path -isnot [string] -or $target.ownership_certain -isnot [bool]) {
        throw 'scenario target ownership identity type drift'
    }
    [void](Assert-ContainmentHex $target.process_start_token 32 'scenario process start token')
    [void](Assert-ContainmentHex $target.discovery_record_sha256 64 'scenario discovery hash')
    if (-not [bool]$target.ownership_certain) {
        $ownershipFailure = [InvalidOperationException]::new('scenario target ownership is ambiguous')
        $ownershipFailure.Data['ContainmentFailureLabel'] = 'ownership_ambiguous'
        throw $ownershipFailure
    }
    if ([int]$target.process_id -le 0 -or [int]$target.port -ne 9878 -or
        -not [IO.Path]::IsPathRooted([string]$target.scratch_path)) {
        throw 'scenario target ownership identity drift'
    }

    $authorization = $evidence.authorization
    Assert-ContainmentExactProperties -Value $authorization -Expected @('nonce','challenge_sha256','authorized_at','preflight_sha256','pre_mutation_sha256','state_unchanged') -Label 'scenario authorization'
    if ($authorization.nonce -isnot [string] -or $authorization.challenge_sha256 -isnot [string] -or
        $authorization.authorized_at -isnot [string] -or $authorization.preflight_sha256 -isnot [string] -or
        $authorization.pre_mutation_sha256 -isnot [string] -or $authorization.state_unchanged -isnot [bool]) {
        throw 'scenario authorization type drift'
    }
    [void](Assert-ContainmentHex $authorization.nonce 32 'scenario authorization nonce')
    [void](Assert-ContainmentHex $authorization.challenge_sha256 64 'scenario authorization challenge hash')
    [void](Assert-ContainmentHex $authorization.preflight_sha256 64 'scenario preflight hash')
    [void](Assert-ContainmentHex $authorization.pre_mutation_sha256 64 'scenario pre-mutation hash')
    if (-not (Test-ContainmentUtcTimestamp $authorization.authorized_at) -or
        -not [bool]$authorization.state_unchanged -or
        [string]$authorization.preflight_sha256 -cne [string]$authorization.pre_mutation_sha256) {
        throw 'scenario authorization state relationship drift'
    }
    $challenge = New-ContainmentAuthorizationChallenge -Scenario $Scenario -RunId ([string]$evidence.run_id) -Nonce ([string]$authorization.nonce) -Target $target
    if ([string]$authorization.challenge_sha256 -cne (Get-ContainmentValueSha256 $challenge)) {
        throw 'scenario authorization challenge hash mismatch'
    }

    $pre = $evidence.pre_state
    Assert-ContainmentExactProperties -Value $pre -Expected @('host_projection','host_sha256','scratch_projection','scratch_sha256') -Label 'scenario pre-state'
    if ($pre.host_sha256 -isnot [string] -or
        ($null -ne $pre.scratch_sha256 -and $pre.scratch_sha256 -isnot [string])) {
        throw 'scenario pre-state hash type drift'
    }
    Assert-ContainmentScenarioProjection -Projection $pre.host_projection -Scenario $Scenario -Label 'scenario host projection'
    if ([string]$pre.host_sha256 -cne (Get-ContainmentValueSha256 $pre.host_projection)) {
        throw 'scenario pre-state host projection hash mismatch'
    }
    if ($null -eq $pre.scratch_projection) {
        if ($null -ne $pre.scratch_sha256) { throw 'scenario pre-state scratch nullability drift' }
    }
    else {
        Assert-ContainmentScratchProjection `
            -Projection $pre.scratch_projection -Scenario $Scenario `
            -ScratchPath ([string]$target.scratch_path) -Target $target `
            -Label 'scenario scratch projection'
        if ([string]$pre.scratch_sha256 -cne (Get-ContainmentValueSha256 $pre.scratch_projection)) {
            throw 'scenario pre-state scratch projection hash mismatch'
        }
    }

    $inventory = @{}
    foreach ($artifact in @($evidence.artifacts)) {
        Assert-ContainmentExactProperties -Value $artifact -Expected @('kind','relative_path','sha256','size') -Label 'scenario artifact'
        if ($artifact.kind -isnot [string] -or $artifact.relative_path -isnot [string] -or
            $artifact.sha256 -isnot [string] -or -not (Test-ContainmentJsonInteger $artifact.size) -or
            [long]$artifact.size -lt 0) {
            throw 'scenario artifact type drift'
        }
        $relative = [string]$artifact.relative_path
        if ($inventory.ContainsKey($relative)) { throw 'scenario artifact inventory contains a duplicate path' }
        $path = Resolve-ContainmentOwnedRelativePath -Root $root -RelativePath $relative -Kind Leaf -Label 'scenario artifact'
        [void](Assert-ContainmentHex $artifact.sha256 64 'scenario artifact hash')
        if ([string]$artifact.sha256 -cne (Get-ContainmentSha256 $path) -or [long]$artifact.size -ne (Get-Item $path).Length) {
            throw 'scenario artifact hash/size mismatch'
        }
        $inventory[$relative] = $artifact
    }
    if (-not $inventory.ContainsKey('.rook-containment-owner.json') -or
        [string]$inventory['.rook-containment-owner.json'].kind -cne 'ownership_marker') {
        throw 'scenario ownership marker inventory binding mismatch'
    }
    $owner = Read-ContainmentCanonicalJsonFile -Path (Join-Path $root '.rook-containment-owner.json') -Label 'scenario ownership marker'
    Assert-ContainmentExactProperties -Value $owner -Expected @('process_id','run_id','schema_version') -Label 'scenario ownership marker'
    if ($owner.schema_version -isnot [int] -or $owner.process_id -isnot [int] -or $owner.run_id -isnot [string]) {
        throw 'scenario ownership marker type drift'
    }
    if ([int]$owner.schema_version -ne 1 -or [int]$owner.process_id -ne [int]$target.process_id -or
        [int]$owner.process_id -ne [int]$evidence.telemetry.process_id -or [string]$owner.run_id -cne [string]$evidence.run_id) {
        throw 'scenario ownership marker content binding mismatch'
    }

    $verification = $evidence.verification
    Assert-ContainmentExactProperties -Value $verification -Expected @('passed','projection','projection_sha256','errors','warnings') -Label 'scenario verification'
    if ($verification.passed -isnot [bool] -or $verification.projection_sha256 -isnot [string] -or
        $verification.errors -isnot [array] -or $verification.warnings -isnot [array] -or
        -not [bool]$verification.passed -or $null -eq $verification.projection -or
        [string]$verification.projection_sha256 -cne (Get-ContainmentValueSha256 $verification.projection) -or
        @($verification.errors).Count -ne 0 -or @($verification.warnings).Count -ne 0) {
        throw 'scenario verification proof mismatch'
    }
    Assert-ContainmentScenarioFinalProjection `
        -Scenario $Scenario -Verification $verification -PreState $pre `
        -ScratchPath ([string]$target.scratch_path) -RunId ([string]$evidence.run_id)

    [string[]]$operationNames = @($evidence.operations | ForEach-Object { [string]$_.name })
    Assert-ContainmentScenarioOperationSequence -Scenario $Scenario -Names $operationNames
    $index = 0
    $previousResult = $null
    $decodedOperationResults = New-Object Collections.Generic.List[object]
    foreach ($operation in @($evidence.operations)) {
        $index++
        Assert-ContainmentExactProperties -Value $operation -Expected @('index','name','arguments_path','arguments_sha256','result_path','result_sha256','success') -Label 'scenario operation'
        if ($operation.index -isnot [int] -or $operation.name -isnot [string] -or
            $operation.arguments_path -isnot [string] -or $operation.arguments_sha256 -isnot [string] -or
            $operation.result_path -isnot [string] -or $operation.result_sha256 -isnot [string] -or
            $operation.success -isnot [bool]) {
            throw 'scenario operation envelope type drift'
        }
        $name = [string]$operation.name
        if ([int]$operation.index -ne $index -or $script:ContainmentScenarioTools[$Scenario] -cnotcontains $name) {
            throw 'scenario operation schema/order/allowlist drift'
        }
        $stem = '{0:D3}-{1}' -f $index, $name
        if ([string]$operation.arguments_path -cne "operations/$stem-arguments.json" -or
            [string]$operation.result_path -cne "operations/$stem-result.json") {
            throw 'scenario operation path identity drift'
        }
        $decodedArguments = $null
        $decodedResult = $null
        foreach ($kind in @('arguments','result')) {
            $relative = [string]$operation.($kind + '_path')
            if (-not $inventory.ContainsKey($relative)) { throw 'scenario operation artifact is not enumerated' }
            $path = Resolve-ContainmentOwnedRelativePath -Root $root -RelativePath $relative -Kind Leaf -Label "scenario operation $kind"
            $decoded = Read-ContainmentCanonicalJsonFile -Path $path -Label "scenario operation $kind"
            if ([string]$operation.($kind + '_sha256') -cne (Get-ContainmentSha256 $path) -or
                [string]$inventory[$relative].sha256 -cne (Get-ContainmentSha256 $path)) {
                throw 'scenario operation artifact hash mismatch'
            }
            if ($kind -eq 'arguments') {
                $decodedArguments = $decoded
                Assert-ContainmentScenarioArguments `
                    -Scenario $Scenario -Name $name -Arguments $decoded -RunId ([string]$evidence.run_id) `
                    -ScratchPath ([string]$target.scratch_path) -Verification $evidence.verification `
                    -OperationIndex $index -OperationNames $operationNames -PreviousResult $previousResult `
                    -Label "scenario operation $index $name"
            }
            if ($kind -eq 'result') {
                $decodedResult = $decoded
                if ($decoded.PSObject.Properties.Name -notcontains 'success' -or
                    $decoded.success -isnot [bool] -or
                    [bool]$decoded.success -ne [bool]$operation.success) {
                    throw 'scenario operation result/success relationship drift'
                }
            }
        }
        Assert-ContainmentScenarioResult `
            -Scenario $Scenario -Name $name -Arguments $decodedArguments -Result $decodedResult `
            -Verification $evidence.verification -PreState $evidence.pre_state `
            -ScratchPath ([string]$target.scratch_path) -RunId ([string]$evidence.run_id) `
            -OperationIndex $index -OperationNames $operationNames `
            -Label "scenario operation $index $name"
        if (-not [bool]$operation.success) { throw 'scenario successful evidence contains a failed operation' }
        $decodedOperationResults.Add($decodedResult)
        $previousResult = $decodedResult
    }
    [void](Assert-ContainmentScenarioPreflightBinding `
        -Scenario $Scenario -OperationResults @($decodedOperationResults.ToArray()) `
        -Authorization $authorization -PreState $pre)
    $restoration = $evidence.restoration
    Assert-ContainmentExactProperties -Value $restoration -Expected @('ownership_certain','attempted','verified','in_process_projection_matches_declared','prior_identity_or_absence_restored','scratch_disposed','discovery_removed') -Label 'scenario restoration'
    foreach ($property in $restoration.PSObject.Properties) {
        if ($property.Value -isnot [bool] -or -not [bool]$property.Value) {
            $restorationFailure = [InvalidOperationException]::new('scenario restoration is not fully verified')
            $restorationFailure.Data['ContainmentFailureLabel'] = if ($property.Name -ceq 'ownership_certain') {
                'ownership_ambiguous'
            }
            elseif (@('scratch_disposed','discovery_removed') -ccontains $property.Name) {
                'cleanup_failed'
            }
            else { 'restoration_failed' }
            throw $restorationFailure
        }
    }
    $telemetry = $evidence.telemetry
    Assert-ContainmentExactProperties -Value $telemetry -Expected @('process_id','process_start_token','before_sha256','after_sha256','delta_count','events_added') -Label 'scenario telemetry'
    if ($telemetry.process_id -isnot [int] -or $telemetry.process_start_token -isnot [string] -or
        $telemetry.before_sha256 -isnot [string] -or $telemetry.after_sha256 -isnot [string] -or
        $telemetry.delta_count -isnot [int] -or $telemetry.events_added -isnot [array]) {
        throw 'scenario telemetry type drift'
    }
    [void](Assert-ContainmentHex $telemetry.before_sha256 64 'scenario telemetry before hash')
    [void](Assert-ContainmentHex $telemetry.after_sha256 64 'scenario telemetry after hash')
    if ([int]$telemetry.process_id -ne [int]$target.process_id -or
        [string]$telemetry.process_start_token -cne [string]$target.process_start_token -or
        [int]$telemetry.delta_count -ne 0 -or @($telemetry.events_added).Count -ne 0) {
        throw "scenario telemetry containment activity or process replacement detected: pid=$($telemetry.process_id)/$($target.process_id), token=$($telemetry.process_start_token)/$($target.process_start_token), delta=$($telemetry.delta_count), events=$(@($telemetry.events_added).Count)"
    }
    foreach ($diagnostic in @($evidence.diagnostics)) {
        Assert-ContainmentExactProperties -Value $diagnostic -Expected @('stage','label','relative_path','sha256') -Label 'scenario diagnostic'
        if ($diagnostic.stage -isnot [string] -or $diagnostic.label -isnot [string] -or
            $diagnostic.relative_path -isnot [string] -or $diagnostic.sha256 -isnot [string]) {
            throw 'scenario diagnostic type drift'
        }
        if (-not $inventory.ContainsKey([string]$diagnostic.relative_path) -or
            [string]$diagnostic.sha256 -cne [string]$inventory[[string]$diagnostic.relative_path].sha256) {
            throw 'scenario diagnostic artifact binding mismatch'
        }
    }

    $declared = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    [void]$declared.Add("$Scenario-scenario.json")
    [void]$declared.Add("$Scenario-scenario.sha256")
    foreach ($relative in $inventory.Keys) { [void]$declared.Add([string]$relative) }
    $actual = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($file in @(Get-ChildItem -LiteralPath $root -File -Recurse -Force)) {
        $relative = $file.FullName.Substring($root.TrimEnd('\').Length).TrimStart('\').Replace('\','/')
        [void]$actual.Add($relative)
    }
    if (-not $actual.SetEquals($declared)) { throw 'scenario artifact directory contains unenumerated files' }
    return $evidence
}

function Read-ContainmentLooseJsonFile {
    param([string]$Path, [string]$Label)
    try { return (Get-Content -LiteralPath $Path -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop) }
    catch { throw "$Label is not parseable JSON: $($_.Exception.Message)" }
}

function New-ContainmentStartupRecord {
    param(
        [string]$Surface,
        [string]$Path,
        [string]$Kind,
        [bool]$Present,
        [AllowNull()][string]$ResolvedPath,
        [AllowNull()][string]$ExpectedPath,
        [bool]$Valid
    )
    return [ordered]@{
        surface = $Surface
        path = [IO.Path]::GetFullPath($Path)
        kind = $Kind
        present = $Present
        resolved_path = $ResolvedPath
        expected_path = $ExpectedPath
        valid = $Valid
        sha256 = $(if ($Present -and (Test-Path -LiteralPath $Path -PathType Leaf)) { Get-ContainmentSha256 $Path } else { $null })
    }
}

function Get-ContainmentStartupSurfaceProjection {
    param(
        [Parameter(Mandatory = $true)][string]$LocalAppDataRoot,
        [Parameter(Mandatory = $true)][string]$AppDataRoot,
        [Parameter(Mandatory = $true)][string]$HomeRoot,
        [Parameter(Mandatory = $true)][string]$RegistryFileName
    )

    $local = Get-ContainmentCanonicalPath -Path $LocalAppDataRoot -Kind Container -Label 'LOCALAPPDATA startup root'
    $appdata = Get-ContainmentCanonicalPath -Path $AppDataRoot -Kind Container -Label 'APPDATA startup root'
    $homePath = Get-ContainmentCanonicalPath -Path $HomeRoot -Kind Container -Label 'home startup root'
    if (-not [IO.Path]::IsPathRooted($RegistryFileName)) { throw 'registry FileName must be absolute' }
    $registryFile = [IO.Path]::GetFullPath($RegistryFileName)
    $pluginRoot = [IO.Path]::GetFullPath((Join-Path $appdata 'McNeel\Rhinoceros\8.0\Plug-ins\RookNative'))
    $expectedVenv = [IO.Path]::GetFullPath((Join-Path $local 'Rook\venv'))
    $expectedPython = Join-Path $expectedVenv 'Scripts\python.exe'
    $expectedWorking = [IO.Path]::GetFullPath((Join-Path $local 'Rook\app\mcp_server'))
    $expectedRegistry = Join-Path $pluginRoot 'net8.0\Rook.rhp'
    $records = New-Object Collections.Generic.List[object]
    $valid = $true

    $jsonConfigs = @(
        [ordered]@{surface='claude-user';path=(Join-Path $homePath '.claude.json')},
        [ordered]@{surface='claude-project';path=(Join-Path $homePath '.claude\.mcp.json')},
        [ordered]@{surface='claude-desktop';path=(Join-Path $appdata 'Claude\claude_desktop_config.json')}
    )
    foreach ($config in $jsonConfigs) {
        $path = [string]$config.path
        $present = Test-Path -LiteralPath $path -PathType Leaf
        $resolved = $null
        $entryValid = $true
        if ($present) {
            [void](Assert-ContainmentPathNotReparse $path ([string]$config.surface))
            $json = Read-ContainmentLooseJsonFile -Path $path -Label ([string]$config.surface)
            if ($null -ne $json.mcpServers -and $null -ne $json.mcpServers.rook) {
                $resolved = [string]$json.mcpServers.rook.command
                $entryValid = [IO.Path]::IsPathRooted($resolved) -and (Test-ContainmentSamePath $resolved $expectedPython)
            }
        }
        if (-not $entryValid) { $valid = $false }
        $records.Add((New-ContainmentStartupRecord -Surface $config.surface -Path $path -Kind 'mcp-config' -Present $present -ResolvedPath $resolved -ExpectedPath $expectedPython -Valid $entryValid))
    }

    $codexPath = Join-Path $homePath '.codex\config.toml'
    $codexPresent = Test-Path -LiteralPath $codexPath -PathType Leaf
    $codexResolved = $null
    $codexValid = $true
    if ($codexPresent) {
        [void](Assert-ContainmentPathNotReparse $codexPath 'Codex startup config')
        $toml = Get-Content -LiteralPath $codexPath -Raw
        $section = [regex]::Match($toml, '(?ms)^\[mcp_servers\.rook\]\s*(.*?)(?=^\[|\z)')
        if ($section.Success) {
            $matches = [regex]::Matches($section.Groups[1].Value, '(?m)^\s*command\s*=\s*["'']([^"'']+)["'']\s*$')
            if ($matches.Count -ne 1) { $codexValid = $false }
            else {
                $codexResolved = $matches[0].Groups[1].Value
                $codexValid = [IO.Path]::IsPathRooted($codexResolved) -and (Test-ContainmentSamePath $codexResolved $expectedPython)
            }
        }
    }
    if (-not $codexValid) { $valid = $false }
    $records.Add((New-ContainmentStartupRecord -Surface 'codex-user' -Path $codexPath -Kind 'mcp-config' -Present $codexPresent -ResolvedPath $codexResolved -ExpectedPath $expectedPython -Valid $codexValid))

    foreach ($relative in @('RookChatService.json','net8.0\RookChatService.json','net7.0\RookChatService.json','net48\RookChatService.json')) {
        $manifestPath = Join-Path $pluginRoot $relative
        $present = Test-Path -LiteralPath $manifestPath -PathType Leaf
        $resolved = $null
        $entryValid = $true
        if ($present) {
            [void](Assert-ContainmentPathNotReparse $manifestPath 'RookChat startup manifest')
            $manifest = Read-ContainmentLooseJsonFile -Path $manifestPath -Label 'RookChat startup manifest'
            $resolved = [string]$manifest.pythonPath
            $entryValid = [IO.Path]::IsPathRooted($resolved) -and
                (Test-ContainmentSamePath $resolved $expectedPython) -and
                [string]$manifest.module -ceq 'rook.agent.chat.service_main' -and
                [IO.Path]::IsPathRooted([string]$manifest.workingDirectory) -and
                (Test-ContainmentSamePath ([string]$manifest.workingDirectory) $expectedWorking)
        }
        if (-not $entryValid) { $valid = $false }
        $records.Add((New-ContainmentStartupRecord -Surface ("rook-chat-manifest:" + $relative.Replace('\','/')) -Path $manifestPath -Kind 'chat-manifest' -Present $present -ResolvedPath $resolved -ExpectedPath $expectedPython -Valid $entryValid))
    }

    $registryPresent = Test-Path -LiteralPath $registryFile -PathType Leaf
    $registryValid = Test-ContainmentSamePath $registryFile $expectedRegistry
    if (-not $registryValid) { $valid = $false }
    $records.Add((New-ContainmentStartupRecord -Surface 'rhino-plugin-registry' -Path $registryFile -Kind 'plugin-registry' -Present $registryPresent -ResolvedPath $registryFile -ExpectedPath $expectedRegistry -Valid $registryValid))

    return [ordered]@{
        schema_version = 1
        valid = $valid
        expected_venv_path = $expectedVenv
        expected_python_path = $expectedPython
        expected_working_directory = $expectedWorking
        plugin_root = $pluginRoot
        registry_file_name = $registryFile
        records = @($records.ToArray())
    }
}

function Assert-ContainmentStartupProjection {
    param(
        [AllowNull()][object]$Projection,
        [Parameter(Mandatory = $true)][string]$ExpectedVenvPath,
        [Parameter(Mandatory = $true)][string]$ExpectedPluginRoot
    )

    if ([int]$Projection.schema_version -ne 1 -or -not [bool]$Projection.valid -or
        -not (Test-ContainmentSamePath ([string]$Projection.expected_venv_path) ([IO.Path]::GetFullPath($ExpectedVenvPath))) -or
        -not (Test-ContainmentSamePath ([string]$Projection.plugin_root) ([IO.Path]::GetFullPath($ExpectedPluginRoot)))) {
        throw 'startup projection contains an alternate authority'
    }
    $expectedPython = Join-Path ([IO.Path]::GetFullPath($ExpectedVenvPath)) 'Scripts\python.exe'
    foreach ($record in @($Projection.records)) {
        if (-not [bool]$record.valid) { throw "startup projection contains an alternate authority: $($record.surface)" }
        if ([bool]$record.present -and [string]$record.kind -ne 'plugin-registry' -and $null -ne $record.resolved_path -and
            -not (Test-ContainmentSamePath ([string]$record.resolved_path) $expectedPython)) {
            throw "startup projection contains an alternate executable: $($record.surface)"
        }
        if ([string]$record.kind -eq 'plugin-registry' -and
            -not (Test-ContainmentSamePath ([string]$record.resolved_path) (Join-Path ([IO.Path]::GetFullPath($ExpectedPluginRoot)) 'net8.0\Rook.rhp'))) {
            throw 'startup projection contains an alternate plug-in registration'
        }
    }
    return $true
}

function Get-ContainmentFileProjection {
    param([string]$Path)
    $item = Get-Item -LiteralPath $Path -Force
    return [ordered]@{ sha256=(Get-ContainmentSha256 $Path); size=[long]$item.Length }
}

function Get-ContainmentHoldPathProjection {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [ValidateSet('directory','file')][string]$Kind
    )

    $fullPath = [IO.Path]::GetFullPath($Path)
    $present = Test-Path -LiteralPath $fullPath
    if (-not $present) {
        return [ordered]@{path=$fullPath;present=$false;sha256=$null;size=$null;files=@()}
    }
    if ($Kind -eq 'directory') {
        if (-not (Test-Path -LiteralPath $fullPath -PathType Container)) {
            throw "partial hold path has the wrong type: $fullPath"
        }
        [void](Assert-ContainmentPathNotReparse $fullPath 'partial hold directory')
        $tree = Get-ContainmentTreeProjection -Root $fullPath
        return [ordered]@{path=$fullPath;present=$true;sha256=$tree.digest;size=$null;files=@($tree.files)}
    }
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        throw "partial hold path has the wrong type: $fullPath"
    }
    [void](Assert-ContainmentPathNotReparse $fullPath 'partial hold file')
    $file = Get-ContainmentFileProjection -Path $fullPath
    return [ordered]@{path=$fullPath;present=$true;sha256=$file.sha256;size=[long]$file.size;files=@()}
}

function Get-ContainmentPartialHoldProjection {
    param(
        [Parameter(Mandatory = $true)][string]$CandidateIdentitySha256,
        [Parameter(Mandatory = $true)][string]$RunId,
        [Parameter(Mandatory = $true)][string]$HoldRoot,
        [Parameter(Mandatory = $true)][string]$VenvPath,
        [Parameter(Mandatory = $true)][string]$PluginRoot
    )

    $identity = Assert-ContainmentHex $CandidateIdentitySha256 64 'partial hold candidate identity'
    $run = Assert-ContainmentHex $RunId 32 'partial hold run id'
    $hold = Get-ContainmentCanonicalPath -Path $HoldRoot -Kind Container -Label 'partial hold root'
    $venv = [IO.Path]::GetFullPath($VenvPath)
    $plugin = [IO.Path]::GetFullPath($PluginRoot)
    $assemblies = New-Object Collections.Generic.List[object]
    foreach ($tfm in @('net8.0','net7.0','net48')) {
        $original = Join-Path $plugin "$tfm\Rook.rhp"
        $held = "$original.contained.$identity.$run"
        $assemblies.Add([ordered]@{
            tfm=$tfm
            original=(Get-ContainmentHoldPathProjection -Path $original -Kind file)
            held=(Get-ContainmentHoldPathProjection -Path $held -Kind file)
        })
    }
    return [ordered]@{
        schema_version=1
        candidate_identity_sha256=$identity
        run_id=$run
        hold_path=$hold
        venv=[ordered]@{
            original=(Get-ContainmentHoldPathProjection -Path $venv -Kind directory)
            held=(Get-ContainmentHoldPathProjection -Path (Join-Path $hold 'venv') -Kind directory)
        }
        assemblies=@($assemblies.ToArray())
    }
}

function Enter-ContainmentDurableHold {
    param(
        [Parameter(Mandatory = $true)][string]$CandidateIdentitySha256,
        [Parameter(Mandatory = $true)][string]$RunId,
        [Parameter(Mandatory = $true)][string]$LocalAppDataRoot,
        [Parameter(Mandatory = $true)][string]$AppDataRoot,
        [Parameter(Mandatory = $true)][string]$HomeRoot,
        [AllowNull()][object]$StartupProjection,
        [AllowNull()][object]$FinalQuietResweep,
        [AllowNull()][scriptblock]$FinalQuietResweepAction
    )

    $identity = Assert-ContainmentHex $CandidateIdentitySha256 64 'candidate identity hash'
    $run = Assert-ContainmentHex $RunId 32 'run id'
    $local = Get-ContainmentCanonicalPath -Path $LocalAppDataRoot -Kind Container -Label 'durable hold LOCALAPPDATA root'
    [void](Get-ContainmentCanonicalPath -Path $AppDataRoot -Kind Container -Label 'durable hold APPDATA root')
    [void](Get-ContainmentCanonicalPath -Path $HomeRoot -Kind Container -Label 'durable hold home root')
    $runtimeRoot = Join-Path $local 'Rook'
    if (-not (Test-Path -LiteralPath $runtimeRoot -PathType Container)) { throw 'durable hold runtime root is missing' }
    [void](Assert-ContainmentPathNotReparse $runtimeRoot 'durable hold runtime root')
    $venvPath = Join-Path $runtimeRoot 'venv'
    $pluginRoot = [IO.Path]::GetFullPath([string]$StartupProjection.plugin_root)
    if ($null -eq $FinalQuietResweep -or -not [bool]$FinalQuietResweep.quiet) {
        throw 'durable hold requires a quiet final process resweep'
    }
    if ($null -eq $FinalQuietResweepAction) {
        throw 'durable hold requires a post-disable quiet resweep action'
    }
    $preDisableQuietResweep = $FinalQuietResweep

    $identityRoot = Join-Path $runtimeRoot ("containment-hold\" + $identity)
    if (-not (Test-Path -LiteralPath $identityRoot)) { [IO.Directory]::CreateDirectory($identityRoot) | Out-Null }
    [void](Assert-ContainmentPathNotReparse $identityRoot 'durable hold identity root')
    $holdRoot = Join-Path $identityRoot $run
    if (Test-Path -LiteralPath $holdRoot) { throw "durable hold collision: fresh leaf already exists: $holdRoot" }
    [void](Assert-ContainmentStartupProjection -Projection $StartupProjection -ExpectedVenvPath $venvPath -ExpectedPluginRoot $pluginRoot)
    [IO.Directory]::CreateDirectory($holdRoot) | Out-Null
    [void](Assert-ContainmentPathNotReparse $holdRoot 'durable hold root')

    try {
    $errors = New-Object Collections.Generic.List[string]
    $heldVenv = Join-Path $holdRoot 'venv'
    $venvRecord = [ordered]@{ source_present=$false; original_path=$venvPath; held_path=$heldVenv; sha256=$null; files=@() }
    if (Test-Path -LiteralPath $venvPath -PathType Container) {
        try {
            [void](Assert-ContainmentPathNotReparse $venvPath 'durable hold venv')
            $before = Get-ContainmentTreeProjection -Root $venvPath
            [IO.Directory]::Move($venvPath, $heldVenv)
            $after = Get-ContainmentTreeProjection -Root $heldVenv
            if ((ConvertTo-ContainmentCanonicalJson $before) -cne (ConvertTo-ContainmentCanonicalJson $after) -or (Test-Path -LiteralPath $venvPath)) {
                throw 'durable hold venv projection drift'
            }
            $venvRecord = [ordered]@{source_present=$true;original_path=$venvPath;held_path=$heldVenv;sha256=$after.digest;files=@($after.files)}
        }
        catch { $errors.Add("venv: $($_.Exception.Message)") }
    }

    $assemblies = New-Object Collections.Generic.List[object]
    foreach ($tfm in @('net8.0','net7.0','net48')) {
        $original = Join-Path $pluginRoot "$tfm\Rook.rhp"
        $held = "$original.contained.$identity.$run"
        $record = [ordered]@{tfm=$tfm;source_present=$false;original_path=$original;held_path=$held;sha256=$null;size=0}
        if (Test-Path -LiteralPath $original -PathType Leaf) {
            $record.source_present = $true
            try {
                [void](Assert-ContainmentPathNotReparse $original "durable hold $tfm assembly")
                if (Test-Path -LiteralPath $held) { throw "durable hold assembly destination exists: $held" }
                $before = Get-ContainmentFileProjection $original
                [IO.File]::Move($original, $held)
                $after = Get-ContainmentFileProjection $held
                if ([string]$before.sha256 -cne [string]$after.sha256 -or [long]$before.size -ne [long]$after.size -or
                    (Test-Path -LiteralPath $original) -or $held.EndsWith('.rhp', [StringComparison]::OrdinalIgnoreCase)) {
                    throw "durable hold $tfm assembly projection drift"
                }
                $record.sha256 = $after.sha256
                $record.size = $after.size
            }
            catch { $errors.Add("$tfm`: $($_.Exception.Message)") }
        }
        $assemblies.Add($record)
    }
    if ($errors.Count -ne 0) { throw "durable hold partial failure; held bytes were not restored: $($errors -join '; ')" }
    if (Test-Path -LiteralPath $venvPath) { throw 'durable hold left the original venv active' }
    foreach ($record in $assemblies) {
        if ([bool]$record.source_present -and ((Test-Path -LiteralPath $record.original_path) -or -not (Test-Path -LiteralPath $record.held_path -PathType Leaf))) {
            throw 'durable hold left an original Rook.rhp authority active'
        }
    }
    $postDisableQuietResweep = & $FinalQuietResweepAction
    if ($null -eq $postDisableQuietResweep -or -not [bool]$postDisableQuietResweep.quiet) {
        throw 'durable hold post-disable process resweep was not quiet'
    }

    $receipt = [ordered]@{
        schema_version = 1
        success = $true
        candidate_identity_sha256 = $identity
        run_id = $run
        held_at = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.ffffffZ')
        venv = $venvRecord
        assemblies = @($assemblies.ToArray())
        startup_projection = $StartupProjection
        pre_disable_quiet_resweep = $preDisableQuietResweep
        post_disable_quiet_resweep = $postDisableQuietResweep
    }
    $receiptPath = Join-Path $holdRoot $script:ContainmentHoldFileName
    $sidecarPath = Join-Path $holdRoot 'containment-hold.sha256'
    $pair = Write-CanonicalJsonPair -Path $receiptPath -SidecarPath $sidecarPath -Value $receipt
    $verified = Test-ContainmentDurableHold -ReceiptPath $receiptPath -SidecarPath $sidecarPath
    if (-not [bool]$verified.success) { throw 'durable hold receipt verification failed' }
    return [ordered]@{
        success = $true
        path = $holdRoot
        sha256 = $pair.Sha256
        sidecar_sha256 = $pair.SidecarSha256
        receipt_path = $receiptPath
        receipt_sidecar_path = $sidecarPath
        pre_disable_quiet_resweep = $preDisableQuietResweep
        post_disable_quiet_resweep = $postDisableQuietResweep
        venv = $venvRecord
        assemblies = @($assemblies.ToArray())
    }
    }
    catch {
        $primaryFailure = $_
        if (-not $primaryFailure.Exception.Data.Contains('ContainmentHoldPath')) {
            $primaryFailure.Exception.Data['ContainmentHoldPath'] = $holdRoot
        }
        try {
            $partialProjection = Get-ContainmentPartialHoldProjection `
                -CandidateIdentitySha256 $identity -RunId $run -HoldRoot $holdRoot `
                -VenvPath $venvPath -PluginRoot $pluginRoot
            $primaryFailure.Exception.Data['ContainmentHoldProjection'] = $partialProjection
            $primaryFailure.Exception.Data['ContainmentHoldProjectionSha256'] = Get-ContainmentValueSha256 $partialProjection
            $partialReceiptPath = Join-Path $holdRoot $script:ContainmentHoldFileName
            $partialSidecarPath = Join-Path $holdRoot 'containment-hold.sha256'
            if (Test-Path -LiteralPath $partialReceiptPath -PathType Leaf) {
                $primaryFailure.Exception.Data['ContainmentHoldReceiptPath'] = $partialReceiptPath
                $primaryFailure.Exception.Data['ContainmentHoldReceiptSha256'] = Get-ContainmentSha256 $partialReceiptPath
            }
            if (Test-Path -LiteralPath $partialSidecarPath -PathType Leaf) {
                $primaryFailure.Exception.Data['ContainmentHoldReceiptSidecarPath'] = $partialSidecarPath
                $primaryFailure.Exception.Data['ContainmentHoldReceiptSidecarSha256'] = Get-ContainmentSha256 $partialSidecarPath
            }
        }
        catch {
            $projectionFailure = [InvalidOperationException]::new(
                "durable hold failed and retained-state projection failed: $($_.Exception.Message)",
                $primaryFailure.Exception
            )
            $projectionFailure.Data['ContainmentHoldPath'] = $holdRoot
            throw $projectionFailure
        }
        throw
    }
}

function Test-ContainmentDurableHold {
    param([Parameter(Mandatory = $true)][string]$ReceiptPath, [Parameter(Mandatory = $true)][string]$SidecarPath)

    $receipt = Read-ContainmentCanonicalJsonFile -Path $ReceiptPath -Label 'durable hold receipt'
    [void](Assert-ContainmentSidecar -SidecarPath $SidecarPath -TargetPath $ReceiptPath -Label 'durable hold receipt')
    if ([int]$receipt.schema_version -ne 1 -or -not [bool]$receipt.success -or
        -not [bool]$receipt.pre_disable_quiet_resweep.quiet -or
        -not [bool]$receipt.post_disable_quiet_resweep.quiet) {
        throw 'durable hold receipt state is invalid'
    }
    [void](Assert-ContainmentHex $receipt.candidate_identity_sha256 64 'durable hold candidate identity')
    [void](Assert-ContainmentHex $receipt.run_id 32 'durable hold run id')
    if ([bool]$receipt.venv.source_present) {
        if ((Test-Path -LiteralPath $receipt.venv.original_path) -or -not (Test-Path -LiteralPath $receipt.venv.held_path -PathType Container)) {
            throw 'durable hold venv path state drift'
        }
        $projection = Get-ContainmentTreeProjection -Root ([string]$receipt.venv.held_path)
        if ([string]$projection.digest -cne [string]$receipt.venv.sha256 -or
            (ConvertTo-ContainmentCanonicalJson @($projection.files)) -cne (ConvertTo-ContainmentCanonicalJson @($receipt.venv.files))) {
            throw 'durable hold venv hash drift'
        }
    }
    foreach ($assembly in @($receipt.assemblies)) {
        if ([bool]$assembly.source_present) {
            if ((Test-Path -LiteralPath $assembly.original_path) -or -not (Test-Path -LiteralPath $assembly.held_path -PathType Leaf) -or
                [string]$assembly.sha256 -cne (Get-ContainmentSha256 $assembly.held_path) -or
                [long]$assembly.size -ne (Get-Item $assembly.held_path).Length -or
                ([string]$assembly.held_path).EndsWith('.rhp', [StringComparison]::OrdinalIgnoreCase)) {
                throw 'durable hold assembly hash/path drift'
            }
        }
    }
    return [ordered]@{success=$true;receipt=$receipt;sha256=(Get-ContainmentSha256 $ReceiptPath)}
}

function Get-ContainmentExpectedProcessEnvironment {
    param(
        [string]$InstallRoot,
        [string]$DataRoot,
        [string]$DspyCache,
        [AllowNull()][string]$ChirpHome,
        [AllowNull()][string]$Profile,
        [switch]$Interactive
    )

    $expected = [ordered]@{
        PYTHONNOUSERSITE = '1'
        DSPY_CACHEDIR = [IO.Path]::GetFullPath($DspyCache)
        ROOK_INSTALL_ROOT = [IO.Path]::GetFullPath($InstallRoot)
        ROOK_DATA_DIR = [IO.Path]::GetFullPath($DataRoot)
        ROOK_MODE = 'release'
        ROOK_DSPY_RESTRICT_PICKLE = '1'
    }
    if ($ChirpHome) { $expected.CHIRP_HOME = [IO.Path]::GetFullPath($ChirpHome) }
    if ($Profile) { $expected.ROOK_MCP_TOOL_PROFILE = $Profile }
    if ($Interactive) { $expected.ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING = '1' }
    return $expected
}

function Assert-ContainmentProcessEnvironment {
    param(
        [AllowNull()][object]$Projection,
        [string]$InstallRoot,
        [string]$DataRoot,
        [string]$DspyCache,
        [AllowNull()][string]$ChirpHome,
        [AllowNull()][string]$Profile,
        [switch]$Interactive,
        [string]$Label
    )

    if ($Profile -and $script:ContainmentProfiles -notcontains $Profile) { throw "$Label profile is invalid" }
    if ($Interactive -and $Profile -cne 'full') { throw "$Label interactive profile is not full" }
    $actual = [Collections.Generic.Dictionary[string,string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($property in @($Projection.PSObject.Properties)) {
        if ($property.Value -isnot [string] -or $actual.ContainsKey($property.Name)) {
            throw "$Label environment is malformed or case-duplicated"
        }
        $actual.Add($property.Name, [string]$property.Value)
    }
    $expected = Get-ContainmentExpectedProcessEnvironment `
        -InstallRoot $InstallRoot -DataRoot $DataRoot -DspyCache $DspyCache `
        -ChirpHome $ChirpHome -Profile $Profile -Interactive:$Interactive
    if ($actual.Count -ne $expected.Count) { throw "$Label environment closed allowlist count drift" }
    foreach ($name in $expected.Keys) {
        if (-not $actual.ContainsKey($name) -or [string]$actual[$name] -cne [string]$expected[$name]) {
            throw "$Label environment closed allowlist drift: $name"
        }
    }
}

function Assert-ContainmentInstalledProcessEvidence {
    param(
        [AllowNull()][object]$Evidence,
        [string]$InstalledPython,
        [string]$InstallRoot,
        [string]$DataRoot,
        [string]$DspyCache,
        [AllowNull()][string]$ChirpHome,
        [AllowNull()][string]$Profile,
        [switch]$Interactive,
        [string[]]$RequiredModules,
        [string[]]$ForbiddenSourceRoots = @(),
        [string]$Label
    )

    Assert-ContainmentExactProperties `
        -Value $Evidence `
        -Expected @('executable','installed_root','cwd','environment','sys_path','rook_origins','process_id','process_start_token') `
        -Label "$Label process"
    foreach ($name in @('executable','installed_root','cwd','process_start_token')) {
        if ($Evidence.$name -isnot [string]) { throw "$Label process $name type drift" }
    }
    if ($Evidence.process_id -isnot [int] -or $Evidence.sys_path -isnot [Array]) {
        throw "$Label installed process type drift"
    }
    if (-not (Test-ContainmentSamePath ([string]$Evidence.executable) $InstalledPython) -or
        -not (Test-ContainmentSamePath ([string]$Evidence.installed_root) $InstallRoot) -or
        -not [IO.Path]::IsPathRooted([string]$Evidence.cwd) -or [int]$Evidence.process_id -le 0) {
        throw "$Label installed process identity drift"
    }
    [void](Assert-ContainmentHex $Evidence.process_start_token 32 "$Label process start token")
    Assert-ContainmentProcessEnvironment `
        -Projection $Evidence.environment -InstallRoot $InstallRoot -DataRoot $DataRoot `
        -DspyCache $DspyCache -ChirpHome $ChirpHome -Profile $Profile `
        -Interactive:$Interactive -Label $Label

    $forbidden = @($ForbiddenSourceRoots | ForEach-Object { [IO.Path]::GetFullPath($_).TrimEnd('\') + '\' })
    foreach ($raw in @([string]$Evidence.cwd) + @($Evidence.sys_path)) {
        if ($raw -isnot [string] -or -not [IO.Path]::IsPathRooted([string]$raw)) {
            throw "$Label sys.path/cwd evidence is malformed"
        }
        $path = [IO.Path]::GetFullPath([string]$raw)
        $normalized = $path.Replace('\','/').ToLowerInvariant()
        if ($normalized.Contains('/.worktrees/') -or $normalized.EndsWith('/mcp_server/src') -or
            $normalized.Contains('/source/repos/rook/mcp_server/src/')) {
            throw "$Label retained a development source path"
        }
        foreach ($prefix in $forbidden) {
            if ($path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
                throw "$Label retained a forbidden source root"
            }
        }
    }
    $originProperties = @($Evidence.rook_origins.PSObject.Properties)
    if ($originProperties.Count -eq 0) { throw "$Label has no installed Rook origins" }
    foreach ($required in $RequiredModules) {
        if ($Evidence.rook_origins.PSObject.Properties.Name -cnotcontains $required) {
            throw "$Label omitted required Rook origin: $required"
        }
    }
    $installPrefix = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\') + '\'
    foreach ($property in $originProperties) {
        if ($property.Value -isnot [string] -or -not [IO.Path]::IsPathRooted([string]$property.Value) -or
            -not ([IO.Path]::GetFullPath([string]$property.Value)).StartsWith($installPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "$Label Rook origin escaped the installed root: $($property.Name)"
        }
    }
}

function Assert-ContainmentCatalog {
    param([AllowNull()][object]$Catalog, [int]$ExpectedCount, [string]$Label)

    Assert-ContainmentExactProperties -Value $Catalog -Expected @('count','tools') -Label "$Label catalog"
    if ($Catalog.count -isnot [int] -or $Catalog.tools -isnot [Array] -or
        [int]$Catalog.count -ne $ExpectedCount -or @($Catalog.tools).Count -ne $ExpectedCount) {
        throw "$Label discovery count drift"
    }
    $names = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($tool in @($Catalog.tools)) {
        if ($tool.PSObject.Properties.Name -cnotcontains 'name' -or $tool.name -isnot [string] -or
            -not $names.Add([string]$tool.name)) {
            throw "$Label discovery schema/name uniqueness drift"
        }
        if ($script:ContainmentContainedNames -ccontains [string]$tool.name) {
            throw "$Label leaked a contained name into discovery"
        }
    }
}

function Assert-ContainmentModelProjections {
    param([AllowNull()][object]$Projections, [string]$Label)

    Assert-ContainmentExactProperties -Value $Projections -Expected @('rook_agent','rook_chat') -Label "$Label model projections"
    foreach ($consumer in @('rook_agent','rook_chat')) {
        $projection = $Projections.$consumer
        Assert-ContainmentExactProperties -Value $projection -Expected @('count','names') -Label "$Label $consumer projection"
        if ($projection.count -isnot [int] -or $projection.names -isnot [Array] -or
            [int]$projection.count -ne @($projection.names).Count) { throw "$Label $consumer projection count/type drift" }
        foreach ($name in @($projection.names)) {
            if ($name -isnot [string] -or $script:ContainmentContainedNames -ccontains [string]$name) {
                throw "$Label contained name leaked into $consumer projection"
            }
        }
    }
}

function Assert-ContainmentTelemetrySnapshot {
    param([AllowNull()][object]$Snapshot, [string]$Label)

    Assert-ContainmentExactProperties -Value $Snapshot -Expected @('process_id','process_start_token','events') -Label $Label
    if ($Snapshot.process_id -isnot [int] -or $Snapshot.process_start_token -isnot [string] -or
        $Snapshot.events -isnot [Array] -or [int]$Snapshot.process_id -le 0 -or
        @($Snapshot.events).Count -gt 50) { throw "$Label shape/type drift" }
    [void](Assert-ContainmentHex $Snapshot.process_start_token 32 "$Label process start token")
}

function Assert-ContainmentTelemetryDelta {
    param(
        [AllowNull()][object]$Before,
        [AllowNull()][object]$After,
        [string]$ExpectedTool,
        [string]$ExpectedOrigin,
        [string]$Label
    )

    Assert-ContainmentTelemetrySnapshot -Snapshot $Before -Label "$Label before telemetry"
    Assert-ContainmentTelemetrySnapshot -Snapshot $After -Label "$Label after telemetry"
    if ([int]$Before.process_id -ne [int]$After.process_id -or
        [string]$Before.process_start_token -cne [string]$After.process_start_token) {
        throw "$Label telemetry process replacement"
    }
    [object[]]$beforeEvents = @($Before.events)
    [object[]]$afterEvents = @($After.events)
    if ($beforeEvents.Count -lt 50) {
        if ($afterEvents.Count -ne ($beforeEvents.Count + 1)) { throw "$Label telemetry append count drift" }
        for ($index = 0; $index -lt $beforeEvents.Count; $index++) {
            if (-not (Test-ContainmentCanonicalEqual $beforeEvents[$index] $afterEvents[$index])) {
                throw "$Label telemetry history drift"
            }
        }
    }
    else {
        if ($afterEvents.Count -ne 50) { throw "$Label telemetry ring size drift" }
        for ($index = 0; $index -lt 49; $index++) {
            if (-not (Test-ContainmentCanonicalEqual $beforeEvents[$index + 1] $afterEvents[$index])) {
                throw "$Label telemetry ring eviction drift"
            }
        }
    }
    $event = $afterEvents[$afterEvents.Count - 1]
    Assert-ContainmentExactProperties -Value $event -Expected @('tool','disposition','origin','timestamp') -Label "$Label telemetry event"
    $lifecycle = $script:ContainmentLifecycle[$ExpectedTool]
    if ($event.tool -isnot [string] -or $event.disposition -isnot [string] -or
        $event.origin -isnot [string] -or $event.timestamp -isnot [string] -or
        $null -eq $lifecycle -or [string]$event.tool -cne $ExpectedTool -or
        [string]$event.origin -cne $ExpectedOrigin -or
        [string]$event.disposition -cne [string]$lifecycle.disposition -or
        [string]$event.timestamp -cnotmatch '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$') {
        throw "$Label telemetry event identity drift"
    }
}

function Assert-ContainmentDenialEnvelope {
    param([AllowNull()][object]$Envelope, [string]$Tool, [string]$Label)

    $lifecycle = $script:ContainmentLifecycle[$Tool]
    if ($null -eq $lifecycle) { throw "$Label uses an unknown contained tool" }
    Assert-ContainmentExactProperties -Value $Envelope -Expected @('success','data') -Label "$Label envelope"
    Assert-ContainmentExactProperties `
        -Value $Envelope.data `
        -Expected @('code','tool','disposition','retryable','verified','recovery') `
        -Label "$Label payload"
    if ($Envelope.success -isnot [bool] -or [bool]$Envelope.success -or
        $Envelope.data.code -isnot [string] -or $Envelope.data.tool -isnot [string] -or
        $Envelope.data.disposition -isnot [string] -or $Envelope.data.recovery -isnot [string] -or
        [string]$Envelope.data.code -cne 'legacy_semantic_tool_contained' -or
        [string]$Envelope.data.tool -cne $Tool -or
        [string]$Envelope.data.disposition -cne [string]$lifecycle.disposition -or
        $Envelope.data.retryable -isnot [bool] -or [bool]$Envelope.data.retryable -or
        $Envelope.data.verified -isnot [bool] -or [bool]$Envelope.data.verified -or
        [string]$Envelope.data.recovery -cne [string]$lifecycle.recovery) {
        throw "$Label denial payload drift"
    }
}

function Assert-ContainmentStageCounts {
    param([AllowNull()][object]$Stages, [int]$FormatResult, [string]$Label)

    Assert-ContainmentExactProperties -Value $Stages -Expected $script:ContainmentStageNames -Label "$Label stages"
    foreach ($name in $script:ContainmentStageNames) {
        $expected = if ($name -eq 'recording_attempt') { 1 } elseif ($name -eq 'format_result') { $FormatResult } else { 0 }
        if ($Stages.$name -isnot [int] -or [int]$Stages.$name -ne $expected) {
            throw "$Label stage count drift: $name"
        }
    }
}

function Assert-ContainmentTransportSpy {
    param(
        [AllowNull()][object]$Spy,
        [string]$RunId,
        [int]$Index,
        [string]$Adapter,
        [string]$Tool,
        [string]$Origin,
        [int]$ProcessId,
        [string]$ProcessStartToken,
        [string]$Label
    )

    Assert-ContainmentExactProperties `
        -Value $Spy `
        -Expected @('schema_version','run_id','process_id','process_start_token','self_test','probe') `
        -Label "$Label spy"
    if ($Spy.schema_version -isnot [int] -or $Spy.run_id -isnot [string] -or
        $Spy.process_id -isnot [int] -or $Spy.process_start_token -isnot [string] -or
        [int]$Spy.schema_version -ne 1 -or [string]$Spy.run_id -cne $RunId -or
        [int]$Spy.process_id -ne $ProcessId -or [string]$Spy.process_start_token -cne $ProcessStartToken) {
        throw "$Label spy identity drift"
    }
    Assert-ContainmentExactProperties -Value $Spy.self_test -Expected @('patchpoints','wrapper_factory') -Label "$Label spy self-test"
    Assert-ContainmentExactProperties -Value $Spy.self_test.patchpoints -Expected $script:ContainmentPatchpointNames -Label "$Label patchpoint self-test"
    foreach ($name in $script:ContainmentPatchpointNames) {
        if ($Spy.self_test.patchpoints.$name -isnot [bool] -or -not [bool]$Spy.self_test.patchpoints.$name) {
            throw "$Label patchpoint self-test failed: $name"
        }
    }
    $factoryNames = @('sync_scoped_trip','sync_unscoped_passthrough','async_scoped_trip','async_unscoped_passthrough')
    Assert-ContainmentExactProperties -Value $Spy.self_test.wrapper_factory -Expected $factoryNames -Label "$Label wrapper self-test"
    foreach ($name in $factoryNames) {
        if ($Spy.self_test.wrapper_factory.$name -isnot [bool] -or -not [bool]$Spy.self_test.wrapper_factory.$name) {
            throw "$Label wrapper self-test failed: $name"
        }
    }
    Assert-ContainmentExactProperties `
        -Value $Spy.probe `
        -Expected @('index','adapter','tool','origin','telemetry_before','telemetry_after','stages') `
        -Label "$Label spy probe"
    if ($Spy.probe.index -isnot [int] -or $Spy.probe.adapter -isnot [string] -or
        $Spy.probe.tool -isnot [string] -or $Spy.probe.origin -isnot [string] -or
        [int]$Spy.probe.index -ne $Index -or [string]$Spy.probe.adapter -cne $Adapter -or
        [string]$Spy.probe.tool -cne $Tool -or [string]$Spy.probe.origin -cne $Origin) {
        throw "$Label spy probe order drift"
    }
    Assert-ContainmentStageCounts -Stages $Spy.probe.stages -FormatResult 1 -Label $Label
    Assert-ContainmentTelemetryDelta `
        -Before $Spy.probe.telemetry_before -After $Spy.probe.telemetry_after `
        -ExpectedTool $Tool -ExpectedOrigin $Origin -Label $Label
    if ([int]$Spy.probe.telemetry_before.process_id -ne $ProcessId -or
        [string]$Spy.probe.telemetry_before.process_start_token -cne $ProcessStartToken) {
        throw "$Label spy telemetry identity drift"
    }
}

function Read-AndValidateContainmentTransportArtifact {
    param(
        [string]$Path,
        [string]$ArtifactRoot,
        [ValidateSet('full','lean','readonly')][string]$Profile,
        [int]$ExpectedCount,
        [string]$InstalledPython,
        [string]$InstallRoot,
        [string]$DataRoot,
        [string]$DspyCache,
        [AllowNull()][string]$ChirpHome,
        [string[]]$ForbiddenSourceRoots
    )

    $artifact = Read-ContainmentCanonicalJsonLfFile -Path $Path -Label "$Profile transport artifact"
    Assert-ContainmentExactProperties `
        -Value $artifact `
        -Expected @('schema_version','command','profile','run_id','process','child_environment','catalog','model_projections','probes','child_process_id','child_process_start_token','final_spy_path','final_spy_sha256','final_spy') `
        -Label "$Profile transport artifact"
    if ($artifact.schema_version -isnot [int] -or $artifact.command -isnot [string] -or
        $artifact.profile -isnot [string] -or $artifact.run_id -isnot [string] -or
        $artifact.child_process_id -isnot [int] -or $artifact.child_process_start_token -isnot [string] -or
        $artifact.final_spy_path -isnot [string] -or $artifact.final_spy_sha256 -isnot [string] -or
        $artifact.probes -isnot [Array] -or [int]$artifact.schema_version -ne 1 -or
        [string]$artifact.command -cne 'transport-profile' -or
        [string]$artifact.profile -cne $Profile) { throw "$Profile transport artifact identity drift" }
    [void](Assert-ContainmentHex $artifact.run_id 32 "$Profile transport run id")
    Assert-ContainmentInstalledProcessEvidence `
        -Evidence $artifact.process -InstalledPython $InstalledPython -InstallRoot $InstallRoot `
        -DataRoot $DataRoot -DspyCache $DspyCache -ChirpHome $ChirpHome -Profile $Profile `
        -RequiredModules @('rook','rook.containment_acceptance','rook.server') `
        -ForbiddenSourceRoots $ForbiddenSourceRoots -Label "$Profile transport"
    Assert-ContainmentProcessEnvironment `
        -Projection $artifact.child_environment -InstallRoot $InstallRoot -DataRoot $DataRoot `
        -DspyCache $DspyCache -ChirpHome $ChirpHome -Profile $Profile -Label "$Profile transport child"
    Assert-ContainmentCatalog -Catalog $artifact.catalog -ExpectedCount $ExpectedCount -Label "$Profile transport"
    Assert-ContainmentModelProjections -Projections $artifact.model_projections -Label "$Profile transport"
    [void](Assert-ContainmentHex $artifact.child_process_start_token 32 "$Profile transport child token")
    if ([int]$artifact.child_process_id -le 0 -or @($artifact.probes).Count -ne 12) {
        throw "$Profile transport child/probe count drift"
    }

    $records = New-Object Collections.Generic.List[object]
    for ($index = 0; $index -lt 12; $index++) {
        $probe = $artifact.probes[$index]
        $toolIndex = $index % $script:ContainmentContainedNames.Count
        $adapter = if ($index -lt 6) { 'direct' } else { 'progressive' }
        $origin = if ($adapter -eq 'direct') { 'public_mcp' } else { 'progressive_meta' }
        $tool = [string]$script:ContainmentContainedNames[$toolIndex]
        Assert-ContainmentExactProperties `
            -Value $probe `
            -Expected @('index','adapter','tool','origin','result','transport','spy') `
            -Label "$Profile transport probe $index"
        if ($probe.index -isnot [int] -or $probe.adapter -isnot [string] -or
            $probe.tool -isnot [string] -or $probe.origin -isnot [string] -or
            [int]$probe.index -ne $index -or [string]$probe.adapter -cne $adapter -or
            [string]$probe.tool -cne $tool -or [string]$probe.origin -cne $origin) {
            throw "$Profile transport probe order drift at $index"
        }
        Assert-ContainmentDenialEnvelope -Envelope $probe.result -Tool $tool -Label "$Profile transport probe $index"
        $expectedTransport = [ordered]@{content_count=1;content_types=@('text');is_error=$false}
        if (-not (Test-ContainmentCanonicalEqual $probe.transport $expectedTransport)) {
            throw "$Profile transport wire contract drift at $index"
        }
        Assert-ContainmentTransportSpy `
            -Spy $probe.spy -RunId ([string]$artifact.run_id) -Index $index -Adapter $adapter `
            -Tool $tool -Origin $origin -ProcessId ([int]$artifact.child_process_id) `
            -ProcessStartToken ([string]$artifact.child_process_start_token) `
            -Label "$Profile transport probe $index"
        $records.Add([ordered]@{
            profile=$Profile;profile_index=$index;adapter=$adapter;tool=$tool;origin=$origin
            result=$probe.result;transport=$probe.transport;spy=$probe.spy;valid=$true
        })
    }
    if (-not (Test-ContainmentCanonicalEqual $artifact.final_spy $artifact.probes[11].spy)) {
        throw "$Profile transport final spy drift"
    }
    $finalPath = Get-ContainmentCanonicalPath -Path ([string]$artifact.final_spy_path) -Kind Leaf -Label "$Profile final spy"
    $rootPrefix = [IO.Path]::GetFullPath($ArtifactRoot).TrimEnd('\') + '\'
    if (-not $finalPath.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase) -or
        [string]$artifact.final_spy_sha256 -cne (Get-ContainmentSha256 $finalPath)) {
        throw "$Profile transport final spy path/hash drift"
    }
    $finalRecord = Read-ContainmentCanonicalJsonLfFile -Path $finalPath -Label "$Profile final spy"
    if (-not (Test-ContainmentCanonicalEqual $finalRecord $artifact.final_spy)) {
        throw "$Profile transport final spy content drift"
    }
    return [ordered]@{artifact=$artifact;records=@($records.ToArray())}
}

function Read-AndValidateContainmentDiscoveryArtifact {
    param(
        [string]$Path,
        [ValidateSet('discovery-default','discovery-interactive')][string]$Command,
        [int]$ExpectedCount,
        [string]$InstalledPython,
        [string]$InstallRoot,
        [string]$DataRoot,
        [string]$DspyCache,
        [AllowNull()][string]$ChirpHome,
        [string[]]$ForbiddenSourceRoots
    )

    $artifact = Read-ContainmentCanonicalJsonLfFile -Path $Path -Label "$Command artifact"
    Assert-ContainmentExactProperties `
        -Value $artifact `
        -Expected @('schema_version','command','process','profile_env_present','interactive_env_present','catalog','telemetry_before','telemetry_after','model_projections') `
        -Label "$Command artifact"
    if ($artifact.schema_version -isnot [int] -or $artifact.command -isnot [string] -or
        $artifact.profile_env_present -isnot [bool] -or $artifact.interactive_env_present -isnot [bool] -or
        [int]$artifact.schema_version -ne 1 -or [string]$artifact.command -cne $Command) {
        throw "$Command artifact identity drift"
    }
    $interactive = $Command -eq 'discovery-interactive'
    $profile = if ($interactive) { 'full' } else { $null }
    if (($interactive -and (-not [bool]$artifact.profile_env_present -or -not [bool]$artifact.interactive_env_present)) -or
        (-not $interactive -and ([bool]$artifact.profile_env_present -or [bool]$artifact.interactive_env_present))) {
        throw "$Command explicit environment presence drift"
    }
    Assert-ContainmentInstalledProcessEvidence `
        -Evidence $artifact.process -InstalledPython $InstalledPython -InstallRoot $InstallRoot `
        -DataRoot $DataRoot -DspyCache $DspyCache -ChirpHome $ChirpHome -Profile $profile `
        -Interactive:$interactive -RequiredModules @('rook','rook.containment_acceptance','rook.server') `
        -ForbiddenSourceRoots $ForbiddenSourceRoots -Label $Command
    Assert-ContainmentCatalog -Catalog $artifact.catalog -ExpectedCount $ExpectedCount -Label $Command
    Assert-ContainmentTelemetrySnapshot -Snapshot $artifact.telemetry_before -Label "$Command telemetry before"
    Assert-ContainmentTelemetrySnapshot -Snapshot $artifact.telemetry_after -Label "$Command telemetry after"
    if (-not (Test-ContainmentCanonicalEqual $artifact.telemetry_before $artifact.telemetry_after)) {
        throw "$Command changed containment telemetry"
    }
    Assert-ContainmentModelProjections -Projections $artifact.model_projections -Label $Command
    return $artifact
}

function Get-ContainmentInternalOrigin {
    param([string]$Seam)
    if ($Seam.StartsWith('server._call_tool_dispatch', [StringComparison]::Ordinal) -or
        $Seam.StartsWith('server._mcp_tool_executor', [StringComparison]::Ordinal)) { return 'server_dispatch' }
    if ($Seam.StartsWith('ToolDispatcher.', [StringComparison]::Ordinal)) { return 'tool_dispatcher' }
    if ($Seam.StartsWith('RookAgent.', [StringComparison]::Ordinal)) { return 'rook_agent' }
    if ($Seam -ceq 'ChatRunner.run_turn') { return 'rook_chat' }
    if ($Seam -ceq 'rook.agent.plan_graph_live.apply_live_producer_node') { return 'plan_graph' }
    return 'internal_handler'
}

function Get-ContainmentExpectedInternalPairs {
    $pairs = New-Object Collections.Generic.List[object]
    foreach ($seam in $script:ContainmentInternalSeams) {
        foreach ($tool in $script:ContainmentContainedNames) {
            $pairs.Add([ordered]@{seam=$seam;tool=$tool;origin=(Get-ContainmentInternalOrigin $seam);adapter=$seam})
        }
    }
    foreach ($constant in @(
        [ordered]@{seam='server._handle_spawn_agent';tool='spawn_agent'},
        [ordered]@{seam='server._handle_plan_and_execute';tool='plan_and_execute'}
    )) {
        $pairs.Add([ordered]@{seam=$constant.seam;tool=$constant.tool;origin='internal_handler';adapter=$constant.seam})
    }
    if ($pairs.Count -ne 164) { throw 'independent internal pair table count drift' }
    return @($pairs.ToArray())
}

function Read-AndValidateContainmentInternalArtifact {
    param(
        [string]$Path,
        [string]$InstalledPython,
        [string]$InstallRoot,
        [string]$DataRoot,
        [string]$DspyCache,
        [AllowNull()][string]$ChirpHome,
        [string[]]$ForbiddenSourceRoots
    )

    $artifact = Read-ContainmentCanonicalJsonLfFile -Path $Path -Label 'internal matrix artifact'
    Assert-ContainmentExactProperties `
        -Value $artifact `
        -Expected @('schema_version','command','process','expected_pairs','probes','model_projections') `
        -Label 'internal matrix artifact'
    if ($artifact.schema_version -isnot [int] -or $artifact.command -isnot [string] -or
        $artifact.expected_pairs -isnot [Array] -or $artifact.probes -isnot [Array] -or
        [int]$artifact.schema_version -ne 1 -or [string]$artifact.command -cne 'internal-matrix') {
        throw 'internal matrix artifact identity drift'
    }
    Assert-ContainmentInstalledProcessEvidence `
        -Evidence $artifact.process -InstalledPython $InstalledPython -InstallRoot $InstallRoot `
        -DataRoot $DataRoot -DspyCache $DspyCache -ChirpHome $ChirpHome `
        -RequiredModules @('rook','rook.containment_acceptance','rook.server') `
        -ForbiddenSourceRoots $ForbiddenSourceRoots -Label 'internal matrix'
    [object[]]$expectedPairs = @(Get-ContainmentExpectedInternalPairs)
    if (@($artifact.expected_pairs).Count -ne 164 -or @($artifact.probes).Count -ne 164 -or
        -not (Test-ContainmentCanonicalEqual -Left @($artifact.expected_pairs) -Right $expectedPairs)) {
        throw 'internal matrix expected-pair set/order drift'
    }
    $records = New-Object Collections.Generic.List[object]
    for ($index = 0; $index -lt 164; $index++) {
        $expected = $expectedPairs[$index]
        $probe = $artifact.probes[$index]
        Assert-ContainmentExactProperties `
            -Value $probe `
            -Expected @('index','seam','adapter','tool','origin','result','telemetry_before','telemetry_after','stages','primary_model_calls') `
            -Label "internal probe $index"
        if ($probe.index -isnot [int] -or $probe.seam -isnot [string] -or
            $probe.adapter -isnot [string] -or $probe.tool -isnot [string] -or $probe.origin -isnot [string] -or
            [int]$probe.index -ne $index -or [string]$probe.seam -cne [string]$expected.seam -or
            [string]$probe.adapter -cne [string]$expected.adapter -or [string]$probe.tool -cne [string]$expected.tool -or
            [string]$probe.origin -cne [string]$expected.origin) {
            throw "internal probe order/identity drift at $index"
        }
        Assert-ContainmentDenialEnvelope -Envelope $probe.result -Tool ([string]$expected.tool) -Label "internal probe $index"
        Assert-ContainmentTelemetryDelta `
            -Before $probe.telemetry_before -After $probe.telemetry_after `
            -ExpectedTool ([string]$expected.tool) -ExpectedOrigin ([string]$expected.origin) -Label "internal probe $index"
        Assert-ContainmentStageCounts -Stages $probe.stages -FormatResult 0 -Label "internal probe $index"
        $expectedCalls = if (@('RookAgent._run_loop','ChatRunner.run_turn') -ccontains [string]$expected.seam) { 2 } else { 0 }
        if ($probe.primary_model_calls -isnot [int] -or [int]$probe.primary_model_calls -ne $expectedCalls) {
            throw "internal probe primary model call drift at $index"
        }
        $records.Add([ordered]@{
            index=$index;seam=$expected.seam;adapter=$expected.adapter;tool=$expected.tool;origin=$expected.origin
            result=$probe.result;telemetry_before=$probe.telemetry_before;telemetry_after=$probe.telemetry_after
            stages=$probe.stages;primary_model_calls=[int]$probe.primary_model_calls;valid=$true
        })
    }
    Assert-ContainmentModelProjections -Projections $artifact.model_projections -Label 'internal matrix'
    return [ordered]@{artifact=$artifact;records=@($records.ToArray())}
}

function New-ContainmentOwnedSubdirectory {
    param([string]$Parent, [string]$Name, [string]$Label)

    $parentPath = Get-ContainmentCanonicalPath -Path $Parent -Kind Container -Label "$Label parent"
    $path = Join-Path $parentPath $Name
    if (Test-Path -LiteralPath $path) { throw "$Label path collision: $path" }
    [IO.Directory]::CreateDirectory($path) | Out-Null
    [void](Assert-ContainmentPathNotReparse -Path $path -Label $Label)
    return [IO.Path]::GetFullPath($path)
}

function Invoke-ContainmentTask7Certification {
    param(
        [string]$EvidenceDirectory,
        [string]$InstalledPython,
        [string]$InstallRoot,
        [string]$DataRoot,
        [string]$DspyCache,
        [AllowNull()][string]$ChirpHome,
        [string[]]$ForbiddenSourceRoots
    )

    $root = New-ContainmentOwnedSubdirectory -Parent $EvidenceDirectory -Name 'task7' -Label 'Task 7 evidence'
    $diagnostics = New-ContainmentOwnedSubdirectory -Parent $root -Name 'process-logs' -Label 'Task 7 process logs'
    $transportRecords = New-Object Collections.Generic.List[object]
    $profileCounts = [ordered]@{full=422;lean=20;readonly=148}
    $globalIndex = 0
    foreach ($profile in $script:ContainmentProfiles) {
        $artifactRoot = New-ContainmentOwnedSubdirectory -Parent $root -Name "transport-$profile" -Label "$profile transport evidence"
        $process = Invoke-InstalledPythonProcess `
            -PythonPath $InstalledPython `
            -Arguments @('-m','rook.containment_acceptance','transport-profile','--profile',$profile,'--artifact-dir',$artifactRoot) `
            -DiagnosticDirectory $diagnostics -TimeoutSeconds 1800 `
            -InstallRoot $InstallRoot -DataRoot $DataRoot -DspyCache $DspyCache `
            -ChirpHome $ChirpHome -Profile $profile
        if ($process.ExitCode -ne 0) {
            throw "Task 7 $profile transport child failed with exit code $($process.ExitCode): $($process.StderrSummary)"
        }
        $parsed = Read-AndValidateContainmentTransportArtifact `
            -Path (Join-Path $artifactRoot "transport-$profile.json") -ArtifactRoot $artifactRoot `
            -Profile $profile -ExpectedCount ([int]$profileCounts[$profile]) `
            -InstalledPython $InstalledPython -InstallRoot $InstallRoot -DataRoot $DataRoot `
            -DspyCache $DspyCache -ChirpHome $ChirpHome -ForbiddenSourceRoots $ForbiddenSourceRoots
        foreach ($record in @($parsed.records)) {
            $transportRecords.Add([ordered]@{
                index=$globalIndex;valid=$true;profile=$profile;profile_index=[int]$record.profile_index
                adapter=$record.adapter;tool=$record.tool;origin=$record.origin;result=$record.result
                transport=$record.transport;spy=$record.spy;parent_process_id=[int]$parsed.artifact.process.process_id
                child_process_id=[int]$parsed.artifact.child_process_id
                child_process_start_token=[string]$parsed.artifact.child_process_start_token
            })
            $globalIndex++
        }
    }
    if ($globalIndex -ne 36) { throw 'Task 7 transport record total drift' }

    $defaultRoot = New-ContainmentOwnedSubdirectory -Parent $root -Name 'discovery-default' -Label 'default discovery evidence'
    $defaultProcess = Invoke-InstalledPythonProcess `
        -PythonPath $InstalledPython `
        -Arguments @('-m','rook.containment_acceptance','discovery-default','--artifact-dir',$defaultRoot) `
        -DiagnosticDirectory $diagnostics -TimeoutSeconds 600 `
        -InstallRoot $InstallRoot -DataRoot $DataRoot -DspyCache $DspyCache -ChirpHome $ChirpHome
    if ($defaultProcess.ExitCode -ne 0) {
        throw "Task 7 default discovery failed with exit code $($defaultProcess.ExitCode): $($defaultProcess.StderrSummary)"
    }
    $default = Read-AndValidateContainmentDiscoveryArtifact `
        -Path (Join-Path $defaultRoot 'discovery-default.json') -Command 'discovery-default' -ExpectedCount 422 `
        -InstalledPython $InstalledPython -InstallRoot $InstallRoot -DataRoot $DataRoot -DspyCache $DspyCache `
        -ChirpHome $ChirpHome -ForbiddenSourceRoots $ForbiddenSourceRoots

    $interactiveRoot = New-ContainmentOwnedSubdirectory -Parent $root -Name 'discovery-interactive' -Label 'interactive discovery evidence'
    $interactiveProcess = Invoke-InstalledPythonProcess `
        -PythonPath $InstalledPython `
        -Arguments @('-m','rook.containment_acceptance','discovery-interactive','--artifact-dir',$interactiveRoot) `
        -DiagnosticDirectory $diagnostics -TimeoutSeconds 600 `
        -InstallRoot $InstallRoot -DataRoot $DataRoot -DspyCache $DspyCache -ChirpHome $ChirpHome `
        -Profile 'full' -Interactive
    if ($interactiveProcess.ExitCode -ne 0) {
        throw "Task 7 interactive discovery failed with exit code $($interactiveProcess.ExitCode): $($interactiveProcess.StderrSummary)"
    }
    $interactive = Read-AndValidateContainmentDiscoveryArtifact `
        -Path (Join-Path $interactiveRoot 'discovery-interactive.json') -Command 'discovery-interactive' -ExpectedCount 425 `
        -InstalledPython $InstalledPython -InstallRoot $InstallRoot -DataRoot $DataRoot -DspyCache $DspyCache `
        -ChirpHome $ChirpHome -ForbiddenSourceRoots $ForbiddenSourceRoots

    $internalRoot = New-ContainmentOwnedSubdirectory -Parent $root -Name 'internal-matrix' -Label 'internal matrix evidence'
    $internalProcess = Invoke-InstalledPythonProcess `
        -PythonPath $InstalledPython `
        -Arguments @('-m','rook.containment_acceptance','internal-matrix','--artifact-dir',$internalRoot) `
        -DiagnosticDirectory $diagnostics -TimeoutSeconds 3600 `
        -InstallRoot $InstallRoot -DataRoot $DataRoot -DspyCache $DspyCache -ChirpHome $ChirpHome
    if ($internalProcess.ExitCode -ne 0) {
        throw "Task 7 internal matrix failed with exit code $($internalProcess.ExitCode): $($internalProcess.StderrSummary)"
    }
    $internal = Read-AndValidateContainmentInternalArtifact `
        -Path (Join-Path $internalRoot 'internal-matrix.json') -InstalledPython $InstalledPython `
        -InstallRoot $InstallRoot -DataRoot $DataRoot -DspyCache $DspyCache `
        -ChirpHome $ChirpHome -ForbiddenSourceRoots $ForbiddenSourceRoots

    return [ordered]@{
        discovery = [ordered]@{
            default=[int]$default.catalog.count
            full=422
            lean=20
            readonly=148
            interactive_full=[int]$interactive.catalog.count
            contained_names_absent=$true
        }
        transport_records = @($transportRecords.ToArray())
        internal_records = @($internal.records)
        process_evidence = [ordered]@{
            transport_profiles=@($script:ContainmentProfiles)
            default=$default.process
            interactive=$interactive.process
            internal=$internal.artifact.process
        }
    }
}

function Invoke-ContainmentProcessPreflight {
    param(
        [ValidateSet('close','enumerate')][string]$Mode,
        [string]$PreflightScript,
        [string]$RookRoot,
        [string]$EvidenceDirectory,
        [string]$Label
    )

    $scriptPath = Get-ContainmentCanonicalPath -Path $PreflightScript -Kind Leaf -Label 'process preflight script'
    if (-not [IO.Path]::IsPathRooted($RookRoot)) { throw 'Rook runtime root must be absolute' }
    $runtimeRoot = [IO.Path]::GetFullPath($RookRoot)
    [void](Assert-ContainmentPathNotReparse -Path $runtimeRoot -Label 'Rook runtime root')
    $root = New-ContainmentOwnedSubdirectory `
        -Parent $EvidenceDirectory -Name ("preflight-" + $Mode + '-' + [guid]::NewGuid().ToString('N')) `
        -Label "$Label preflight evidence"
    $summaryPath = Join-Path $root 'summary.json'
    $innoPath = Join-Path $root 'summary.txt'
    $logPath = Join-Path $root 'preflight.log'
    $powershell = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
    $result = Invoke-ContainmentChildProcess `
        -Executable $powershell `
        -Arguments @(
            '-NoProfile','-ExecutionPolicy','Bypass','-File',$scriptPath,
            '-Mode',$Mode,'-RookRoot',$runtimeRoot,'-LogRoot',$root,
            '-SummaryPath',$summaryPath,'-InnoSummaryPath',$innoPath,'-LogPath',$logPath,
            '-SetupVersion','containment-candidate'
        ) `
        -DiagnosticDirectory $root -TimeoutSeconds 180 `
        -Policy ([ordered]@{Mode='preflight';Values=[ordered]@{}})
    if ($result.ExitCode -ne 0) {
        throw "$Label process preflight mode $Mode failed with exit code $($result.ExitCode): $($result.StderrSummary)"
    }
    $summary = Read-ContainmentLooseJsonFile -Path $summaryPath -Label "$Label process preflight summary"
    Assert-ContainmentExactProperties `
        -Value $summary `
        -Expected @('schema_version','setup_version','run_start_utc','phase_reached','preflight','closed_process_count','outcome') `
        -Label "$Label process preflight summary"
    Assert-ContainmentExactProperties `
        -Value $summary.preflight `
        -Expected @('conflicts_found','server_count','owners','processes','message') `
        -Label "$Label process preflight projection"
    if ([int]$summary.schema_version -ne 1 -or [string]$summary.phase_reached -cne 'preflight' -or
        [int]$summary.preflight.server_count -lt 0 -or [int]$summary.closed_process_count -lt 0) {
        throw "$Label process preflight summary drift"
    }
    $quiet = -not [bool]$summary.preflight.conflicts_found -and [int]$summary.preflight.server_count -eq 0
    if ($Mode -eq 'enumerate' -and -not $quiet) { throw "$Label process resweep is not quiet" }
    return [ordered]@{
        mode=$Mode;quiet=$quiet;exit_code=[int]$result.ExitCode;summary_path=$summaryPath
        summary_sha256=(Get-ContainmentSha256 $summaryPath);log_path=$logPath
        log_sha256=(Get-ContainmentSha256 $logPath);summary=$summary
    }
}

function Get-ContainmentCompanionRegistryFileName {
    param([string]$AppDataRoot)

    $appdata = Get-ContainmentCanonicalPath -Path $AppDataRoot -Kind Container -Label 'APPDATA root'
    $expected = Join-Path $appdata 'McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0\Rook.rhp'
    $key = 'HKCU:\Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B\PlugIn'
    if (Test-Path -LiteralPath $key) {
        $value = (Get-ItemProperty -LiteralPath $key -Name FileName -ErrorAction Stop).FileName
        if ($value -isnot [string] -or -not [IO.Path]::IsPathRooted([string]$value)) {
            throw 'companion registry FileName is missing or non-absolute'
        }
        return [IO.Path]::GetFullPath([string]$value)
    }
    return [IO.Path]::GetFullPath($expected)
}

function New-ContainmentInstallerTripwire {
    param([string]$PythonPath, [string]$EvidenceDirectory)

    $root = New-ContainmentOwnedSubdirectory -Parent $EvidenceDirectory -Name 'installer-startup-isolation' -Label 'installer startup isolation'
    $base = New-ContainmentOwnedSubdirectory -Parent $root -Name 'owned-user-base' -Label 'installer hostile user base'
    $logs = New-ContainmentOwnedSubdirectory -Parent $root -Name 'process-logs' -Label 'installer tripwire logs'
    $policy = [ordered]@{Mode='startup-control';Values=[ordered]@{PYTHONUSERBASE=$base}}
    $probe = Invoke-ContainmentChildProcess `
        -Executable $PythonPath -Arguments @('-S','-c','import site;print(site.getusersitepackages())') `
        -DiagnosticDirectory $logs -TimeoutSeconds 30 -Policy $policy
    if ($probe.ExitCode -ne 0) { throw 'installer hostile user-site derivation failed' }
    $site = ([IO.File]::ReadAllText($probe.StdoutPath)).TrimEnd("`r","`n")
    $basePrefix = [IO.Path]::GetFullPath($base).TrimEnd('\') + '\'
    if (-not [IO.Path]::IsPathRooted($site) -or
        -not ([IO.Path]::GetFullPath($site)).StartsWith($basePrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'installer hostile user site escaped its owned base'
    }
    [IO.Directory]::CreateDirectory($site) | Out-Null
    $code = "from pathlib import Path; Path(__file__).with_suffix('.hit').write_text('executed', encoding='ascii')`n"
    $siteScript = Join-Path $site 'sitecustomize.py'
    $userScript = Join-Path $site 'usercustomize.py'
    [IO.File]::WriteAllText($siteScript, $code, [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($userScript, $code, [Text.UTF8Encoding]::new($false))
    return [ordered]@{
        root=$root;user_base=$base;user_site=[IO.Path]::GetFullPath($site)
        sitecustomize_path=$siteScript;sitecustomize_sha256=(Get-ContainmentSha256 $siteScript)
        usercustomize_path=$userScript;usercustomize_sha256=(Get-ContainmentSha256 $userScript)
        sitecustomize_hit=(Join-Path $site 'sitecustomize.hit')
        usercustomize_hit=(Join-Path $site 'usercustomize.hit')
    }
}

function Invoke-ContainmentCandidateInstallation {
    param(
        [AllowNull()][object]$Candidate,
        [AllowNull()][object]$Tripwire,
        [string]$DiagnosticDirectory,
        [string]$StartedUtc,
        [AllowNull()][scriptblock]$OnInstallerStarted
    )

    if (-not (Test-ContainmentUtcTimestamp $StartedUtc)) { throw 'installer start timestamp is invalid' }
    $beforeInstallerHash = Get-ContainmentSha256 ([string]$Candidate.installer_path)
    if ($beforeInstallerHash -cne [string]$Candidate.installer_sha256) { throw 'installer drifted before launch' }
    $saved = [ordered]@{}
    foreach ($entry in [Environment]::GetEnvironmentVariables('Process').GetEnumerator()) {
        $name = [string]$entry.Key
        if (Test-ContainmentControlledName $name) {
            $saved[$name] = [string]$entry.Value
            [Environment]::SetEnvironmentVariable($name, $null, 'Process')
        }
    }
    try {
        [Environment]::SetEnvironmentVariable('PyThOnUsErBaSe', [string]$Tripwire.user_base, 'Process')
        [Environment]::SetEnvironmentVariable('pYtHoNnOuSeRsItE', '0', 'Process')
        [Environment]::SetEnvironmentVariable('PyThOnPaTh', 'C:\hostile\source', 'Process')
        [Environment]::SetEnvironmentVariable('RoOk_McP_ToOl_PrOfIlE', 'hostile', 'Process')
        $result = Invoke-CandidateInstallerProcess `
            -InstallerPath ([string]$Candidate.installer_path) `
            -InstallerArguments @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/TYPE=full') `
            -DiagnosticDirectory $DiagnosticDirectory -TimeoutSeconds 3600 `
            -OnProcessStarted $OnInstallerStarted
    }
    finally {
        foreach ($entry in [Environment]::GetEnvironmentVariables('Process').GetEnumerator()) {
            $name = [string]$entry.Key
            if (Test-ContainmentControlledName $name) {
                [Environment]::SetEnvironmentVariable($name, $null, 'Process')
            }
        }
        foreach ($name in $saved.Keys) {
            [Environment]::SetEnvironmentVariable([string]$name, [string]$saved[$name], 'Process')
        }
    }
    if ($result.ExitCode -ne 0) {
        throw "candidate installer failed with exit code $($result.ExitCode): $($result.StderrSummary)"
    }
    if ((Test-Path -LiteralPath ([string]$Tripwire.sitecustomize_hit)) -or
        (Test-Path -LiteralPath ([string]$Tripwire.usercustomize_hit))) {
        throw 'candidate installer or post-install descendant executed an external startup hook'
    }
    [string[]]$final = @($result.FinalControlledEnvironmentNames)
    if ($final.Count -ne 1 -or -not [string]::Equals($final[0], 'PYTHONNOUSERSITE', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'candidate installer controlled environment allowlist drift'
    }
    $removedFolded = @($result.RemovedEnvironmentNames | ForEach-Object { ([string]$_).ToUpperInvariant() })
    foreach ($required in @('PYTHONUSERBASE','PYTHONNOUSERSITE','PYTHONPATH','ROOK_MCP_TOOL_PROFILE')) {
        if ($removedFolded -notcontains $required) { throw "candidate installer did not remove seeded $required" }
    }
    if ((Get-ContainmentSha256 ([string]$Candidate.installer_path)) -cne $beforeInstallerHash) {
        throw 'installer bytes drifted during installation'
    }
    return [ordered]@{
        started_utc=$StartedUtc;ended_utc=[DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.ffffffZ')
        installer_sha256=$beforeInstallerHash;exit_code=[int]$result.ExitCode
        process_id=[int]$result.ProcessId;removed_environment_names=@($result.RemovedEnvironmentNames)
        final_controlled_environment_names=@($result.FinalControlledEnvironmentNames)
        external_hits_absent=$true;tripwire=$Tripwire
    }
}

function Assert-ContainmentInstalledRuntime {
    param(
        [AllowNull()][object]$Candidate,
        [string]$LocalAppDataRoot,
        [string]$AppDataRoot,
        [DateTime]$InstallStartedUtc,
        [string]$DiagnosticDirectory
    )

    $local = Get-ContainmentCanonicalPath -Path $LocalAppDataRoot -Kind Container -Label 'installed LOCALAPPDATA root'
    $appdata = Get-ContainmentCanonicalPath -Path $AppDataRoot -Kind Container -Label 'installed APPDATA root'
    $runtimeRoot = Get-ContainmentCanonicalPath -Path (Join-Path $local 'Rook') -Kind Container -Label 'installed Rook runtime root'
    $installRoot = Get-ContainmentCanonicalPath -Path (Join-Path $runtimeRoot 'app') -Kind Container -Label 'installed Rook app root'
    $dataRoot = Get-ContainmentCanonicalPath -Path (Join-Path $runtimeRoot 'data') -Kind Container -Label 'installed Rook data root'
    $venvPython = Get-ContainmentCanonicalPath -Path (Join-Path $runtimeRoot 'venv\Scripts\python.exe') -Kind Leaf -Label 'installed Rook venv Python'
    $privatePython = Get-ContainmentCanonicalPath -Path (Join-Path $runtimeRoot 'python\cpython-3.11.9\python.exe') -Kind Leaf -Label 'installed private Python'
    if ((Get-ContainmentSha256 $privatePython) -cne [string]$Candidate.private_python_sha256) {
        throw 'installed private Python does not match the identity-bound candidate runtime'
    }
    $privateIdentity = Assert-FullCpythonRuntime `
        -PythonPath $privatePython -ExpectedVersion '3.11.9' `
        -DiagnosticDirectory $DiagnosticDirectory -EnforceNoUserSite

    $candidateManifest = Resolve-ContainmentOwnedRelativePath `
        -Root ([string]$Candidate.artifact_directory) `
        -RelativePath 'stage/Rook/installer/runtime/python-runtime-manifest.json' `
        -Kind Leaf -Label 'candidate Python runtime manifest'
    $installedManifest = Get-ContainmentCanonicalPath `
        -Path (Join-Path $installRoot 'python-runtime-manifest.json') -Kind Leaf -Label 'installed Python runtime manifest'
    $manifestHash = Get-ContainmentSha256 $candidateManifest
    if ((Get-ContainmentSha256 $installedManifest) -cne $manifestHash) {
        throw 'installed Python runtime manifest does not match the candidate'
    }
    $installStatePath = Get-ContainmentCanonicalPath `
        -Path (Join-Path $dataRoot 'install-state.json') -Kind Leaf -Label 'installed Python state'
    $state = Read-ContainmentLooseJsonFile -Path $installStatePath -Label 'installed Python state'
    if ([int]$state.schema_version -ne 1 -or [string]$state.python.version -cne '3.11.9' -or
        -not (Test-ContainmentSamePath ([string]$state.python.path) $privatePython) -or
        -not (Test-ContainmentSamePath ([string]$state.python.runtime_manifest_path) $installedManifest) -or
        [string]$state.python.identity_hash -cne $manifestHash -or
        [string]$state.python.runtime_manifest_sha256 -cne $manifestHash) {
        throw 'installed Python state/manifest identity drift'
    }
    foreach ($runtimeName in @('rook','chirp')) {
        $entry = $state.$runtimeName
        if ($null -eq $entry -or [string]$entry.python_identity_hash -cne $manifestHash -or
            -not [IO.Path]::IsPathRooted([string]$entry.venv_path) -or
            -not [IO.Path]::IsPathRooted([string]$entry.python_path) -or
            -not (Test-ContainmentUtcTimestamp ([string]$entry.installed_utc))) {
            throw "installed $runtimeName runtime state drift"
        }
    }
    $minimumCreation = $InstallStartedUtc.AddSeconds(-5)
    foreach ($path in @($installedManifest,$installStatePath,$privatePython,$venvPython)) {
        if ((Get-Item -LiteralPath $path -Force).CreationTimeUtc -lt $minimumCreation) {
            throw "installed runtime artifact predates installer start: $path"
        }
    }

    $pluginRoot = Get-ContainmentCanonicalPath `
        -Path (Join-Path $appdata 'McNeel\Rhinoceros\8.0\Plug-ins\RookNative') `
        -Kind Container -Label 'installed Rook plug-in root'
    $fileBindings = @(
        [ordered]@{source='stage/Rook/src/RookNative/bin/Release/x64/RookNative.rhp';target='RookNative.rhp'},
        [ordered]@{source='stage/Rook/src/Rook/bin/Release/net8.0/Rook.rhp';target='net8.0/Rook.rhp'},
        [ordered]@{source='stage/Rook/src/Rook/bin/Release/net7.0/Rook.rhp';target='net7.0/Rook.rhp'},
        [ordered]@{source='stage/Rook/src/Rook/bin/Release/net48/Rook.rhp';target='net48/Rook.rhp'}
    )
    $pluginBindings = New-Object Collections.Generic.List[object]
    foreach ($binding in $fileBindings) {
        $source = Resolve-ContainmentOwnedRelativePath -Root ([string]$Candidate.artifact_directory) -RelativePath $binding.source -Kind Leaf -Label 'candidate installed plug-in binding'
        $target = Resolve-ContainmentOwnedRelativePath -Root $pluginRoot -RelativePath $binding.target -Kind Leaf -Label 'installed plug-in binding'
        $hash = Get-ContainmentSha256 $source
        if ((Get-ContainmentSha256 $target) -cne $hash) { throw "installed plug-in candidate hash drift: $($binding.target)" }
        $pluginBindings.Add([ordered]@{relative_path=$binding.target;sha256=$hash;size=[long](Get-Item $target).Length})
    }
    foreach ($relative in @(
        'mcp_server/src/rook/containment_acceptance.py',
        'mcp_server/src/rook/containment_live_gate.py',
        'mcp_server/src/rook/tool_lifecycle.py'
    )) {
        $source = Resolve-ContainmentOwnedRelativePath -Root (Join-Path ([string]$Candidate.artifact_directory) 'stage\Rook') -RelativePath $relative -Kind Leaf -Label 'candidate installed Python module'
        $target = Resolve-ContainmentOwnedRelativePath -Root $installRoot -RelativePath $relative -Kind Leaf -Label 'installed Python module'
        if ((Get-ContainmentSha256 $target) -cne (Get-ContainmentSha256 $source)) {
            throw "installed Python module does not match candidate: $relative"
        }
    }

    $dspyCache = Join-Path $dataRoot 'dspy-cache'
    if (-not (Test-Path -LiteralPath $dspyCache -PathType Container)) { [IO.Directory]::CreateDirectory($dspyCache) | Out-Null }
    [void](Assert-ContainmentPathNotReparse $dspyCache 'installed DSPy cache')
    $chirpHome = Join-Path $installRoot 'chirp'
    if (-not (Test-Path -LiteralPath $chirpHome -PathType Container)) { $chirpHome = $null }
    return [ordered]@{
        runtime_root=$runtimeRoot;install_root=$installRoot;data_root=$dataRoot
        dspy_cache=[IO.Path]::GetFullPath($dspyCache);chirp_home=$chirpHome
        python_executable=$venvPython;python_sha256=(Get-ContainmentSha256 $venvPython)
        private_python=$privateIdentity;runtime_manifest_path=$installedManifest
        runtime_manifest_sha256=$manifestHash;install_state_path=$installStatePath
        install_state_sha256=(Get-ContainmentSha256 $installStatePath);plugin_root=$pluginRoot
        plugin_bindings=@($pluginBindings.ToArray())
    }
}

function Get-ContainmentDiagnosticProjection {
    param([string]$EvidenceDirectory)

    $root = Get-ContainmentCanonicalPath -Path $EvidenceDirectory -Kind Container -Label 'diagnostic evidence root'
    $records = New-Object Collections.Generic.List[object]
    foreach ($file in @(Get-ChildItem -LiteralPath $root -File -Recurse -Force | Sort-Object FullName)) {
        if ((Test-ContainmentSamePath $file.DirectoryName $root) -and $file.Name -ceq '.containment-run-owner.json') {
            continue
        }
        if (@(
            $script:ContainmentAcceptanceFileName,'containment-acceptance.sha256',
            $script:ContainmentFailureFileName,'containment-failure.sha256'
        ) -contains $file.Name -and (Test-ContainmentSamePath $file.DirectoryName $root)) {
            continue
        }
        [void](Assert-ContainmentPathNotReparse $file.FullName 'diagnostic evidence artifact')
        $relative = $file.FullName.Substring($root.TrimEnd('\').Length).TrimStart('\').Replace('\','/')
        $records.Add([ordered]@{relative_path=$relative;sha256=(Get-ContainmentSha256 $file.FullName);size=[long]$file.Length})
    }
    return @($records.ToArray())
}

function Invoke-ContainmentLiveScenarios {
    param(
        [string]$EvidenceDirectory,
        [string]$InstalledPython,
        [string]$InstallRoot,
        [string]$DataRoot,
        [string]$DspyCache,
        [AllowNull()][string]$ChirpHome,
        [string]$RhinoExe
    )

    $root = New-ContainmentOwnedSubdirectory -Parent $EvidenceDirectory -Name 'scenarios' -Label 'live scenario evidence'
    $logs = New-ContainmentOwnedSubdirectory -Parent $root -Name 'process-logs' -Label 'live scenario process logs'
    $summary = [ordered]@{}
    foreach ($scenario in @('rhino','grasshopper')) {
        $scenarioRoot = New-ContainmentOwnedSubdirectory -Parent $root -Name $scenario -Label "$scenario scenario evidence"
        $process = Invoke-LiveGateProcess `
            -PythonPath $InstalledPython `
            -Arguments @('-m','rook.containment_live_gate','run','--scenario',$scenario,'--rhino-exe',$RhinoExe,'--artifact-dir',$scenarioRoot) `
            -DiagnosticDirectory $logs -TimeoutSeconds 1800 -ExpectedScenario $scenario `
            -InstallRoot $InstallRoot -DataRoot $DataRoot -DspyCache $DspyCache -ChirpHome $ChirpHome
        $evidencePath = Join-Path $scenarioRoot "$scenario-scenario.json"
        $sidecarPath = Join-Path $scenarioRoot "$scenario-scenario.sha256"
        if ([string]$process.Result.evidence_path -cne "$scenario-scenario.json" -or
            [string]$process.Result.evidence_sha256 -cne (Get-ContainmentSha256 $evidencePath)) {
            throw "$scenario scenario_result path/hash drift"
        }
        $evidence = Read-AndValidateScenarioEvidence `
            -Scenario $scenario -ScenarioPath $evidencePath -ScenarioSidecarPath $sidecarPath `
            -ExpectedInstalledRoot $InstallRoot
        if ([string]$process.Result.run_id -cne [string]$evidence.run_id -or
            [string]$process.Authorization.run_id -cne [string]$evidence.run_id -or
            [string]$evidence.authorization.challenge_sha256 -cne (Get-ContainmentValueSha256 $process.Authorization)) {
            throw "$scenario stdout/evidence authorization binding drift"
        }
        $summary[$scenario] = [ordered]@{
            success=$true;restoration_verified=[bool]$evidence.restoration.verified
            telemetry_delta=[int]$evidence.telemetry.delta_count
            evidence_path=$evidencePath;evidence_sha256=(Get-ContainmentSha256 $evidencePath)
            sidecar_path=$sidecarPath;sidecar_sha256=(Get-ContainmentSha256 $sidecarPath)
            authorization=$process.Authorization;operations=@($evidence.operations)
            verification=$evidence.verification;restoration=$evidence.restoration
            target=$evidence.target;runtime=$evidence.runtime;telemetry=$evidence.telemetry
            gate_process_id=[int]$process.ProcessId
        }
    }
    return $summary
}

function Assert-ContainmentRetainedScenarioBinding {
    param(
        [ValidateSet('rhino','grasshopper')][string]$Scenario,
        [AllowNull()][object]$Accepted,
        [AllowNull()][object]$ScenarioEvidence,
        [string]$EvidencePath,
        [string]$SidecarPath
    )

    Assert-ContainmentExactProperties -Value $Accepted -Expected @(
        'success','restoration_verified','telemetry_delta',
        'evidence_path','evidence_sha256','sidecar_path','sidecar_sha256',
        'authorization','operations','verification','restoration','target','runtime','telemetry',
        'gate_process_id'
    ) -Label "$Scenario retained acceptance scenario"
    $fixedEvidencePath = Get-ContainmentCanonicalPath -Path $EvidencePath -Kind Leaf -Label "$Scenario fixed scenario evidence"
    $fixedSidecarPath = Get-ContainmentCanonicalPath -Path $SidecarPath -Kind Leaf -Label "$Scenario fixed scenario sidecar"
    $acceptedEvidencePath = Get-ContainmentCanonicalPath -Path ([string]$Accepted.evidence_path) -Kind Leaf -Label "$Scenario retained evidence path"
    $acceptedSidecarPath = Get-ContainmentCanonicalPath -Path ([string]$Accepted.sidecar_path) -Kind Leaf -Label "$Scenario retained sidecar path"
    if (-not (Test-ContainmentSamePath $acceptedEvidencePath $fixedEvidencePath) -or
        -not (Test-ContainmentSamePath $acceptedSidecarPath $fixedSidecarPath)) {
        throw "$Scenario retained acceptance did not bind the fixed scenario evidence pair"
    }
    $pair = Assert-ContainmentSidecar -SidecarPath $fixedSidecarPath -TargetPath $fixedEvidencePath -DigestOnly -Label "$Scenario retained scenario evidence"
    if ($Accepted.success -isnot [bool] -or -not [bool]$Accepted.success -or
        $Accepted.restoration_verified -isnot [bool] -or -not [bool]$Accepted.restoration_verified -or
        $Accepted.telemetry_delta -isnot [int] -or [int]$Accepted.telemetry_delta -ne 0 -or
        [string]$Accepted.evidence_sha256 -cne [string]$pair.TargetSha256 -or
        [string]$Accepted.sidecar_sha256 -cne [string]$pair.SidecarSha256 -or
        $Accepted.gate_process_id -isnot [int] -or [int]$Accepted.gate_process_id -le 0) {
        throw "$Scenario retained acceptance fixed evidence/gate process binding drift"
    }
    $expectedChallenge = New-ContainmentAuthorizationChallenge `
        -Scenario $Scenario -RunId ([string]$ScenarioEvidence.run_id) `
        -Nonce ([string]$ScenarioEvidence.authorization.nonce) -Target $ScenarioEvidence.target
    if ([string]$ScenarioEvidence.authorization.challenge_sha256 -cne (Get-ContainmentValueSha256 $expectedChallenge) -or
        -not (Test-ContainmentCanonicalEqual -Left $Accepted.authorization -Right $expectedChallenge) -or
        -not (Test-ContainmentCanonicalEqual -Left @($Accepted.operations) -Right @($ScenarioEvidence.operations)) -or
        -not (Test-ContainmentCanonicalEqual -Left $Accepted.verification -Right $ScenarioEvidence.verification) -or
        -not (Test-ContainmentCanonicalEqual -Left $Accepted.restoration -Right $ScenarioEvidence.restoration) -or
        -not (Test-ContainmentCanonicalEqual -Left $Accepted.target -Right $ScenarioEvidence.target) -or
        -not (Test-ContainmentCanonicalEqual -Left $Accepted.runtime -Right $ScenarioEvidence.runtime) -or
        -not (Test-ContainmentCanonicalEqual -Left $Accepted.telemetry -Right $ScenarioEvidence.telemetry)) {
        throw "$Scenario retained acceptance/scenario evidence binding drift"
    }
    return $true
}

function Assert-ContainmentIndexedAcceptanceRecords {
    param([object[]]$Records, [int]$ExpectedCount, [string]$Label)
    if (@($Records).Count -ne $ExpectedCount) { throw "$Label record count must equal $ExpectedCount" }
    for ($index = 0; $index -lt $ExpectedCount; $index++) {
        $record = $Records[$index]
        if ($record -is [Collections.IDictionary]) {
            $recordIndex = $record['index']
            $recordValid = $record['valid']
        }
        else {
            $recordIndex = $record.index
            $recordValid = $record.valid
        }
        if ($recordIndex -isnot [int] -or [int]$recordIndex -ne $index -or
            $recordValid -isnot [bool] -or -not [bool]$recordValid) {
            throw "$Label record is incomplete or invalid at index $index"
        }
    }
}

function New-ContainmentAcceptanceRecord {
    param(
        [Parameter(Mandatory = $true)][string]$RunId,
        [Parameter(Mandatory = $true)][string]$StartedUtc,
        [Parameter(Mandatory = $true)][AllowNull()][object]$Candidate,
        [Parameter(Mandatory = $true)][AllowNull()][object]$InstalledRuntime,
        [Parameter(Mandatory = $true)][AllowNull()][object]$Quiescence,
        [Parameter(Mandatory = $true)][AllowNull()][object]$StartupIsolation,
        [Parameter(Mandatory = $true)][AllowNull()][object]$Discovery,
        [Parameter(Mandatory = $true)][object[]]$TransportRecords,
        [Parameter(Mandatory = $true)][object[]]$InternalRecords,
        [Parameter(Mandatory = $true)][AllowNull()][object]$Scenarios,
        [Parameter(Mandatory = $true)][object[]]$Diagnostics,
        [Parameter(Mandatory = $true)][AllowNull()][object]$PostRunArtifactSnapshot
    )

    [void](Assert-ContainmentHex $RunId 32 'acceptance run id')
    if (-not (Test-ContainmentUtcTimestamp $StartedUtc)) { throw 'acceptance start timestamp is invalid' }
    Assert-ContainmentIndexedAcceptanceRecords -Records $TransportRecords -ExpectedCount 36 -Label 'transport'
    Assert-ContainmentIndexedAcceptanceRecords -Records $InternalRecords -ExpectedCount 164 -Label 'internal'
    $expectedDiscovery = [ordered]@{default=422;full=422;lean=20;readonly=148;interactive_full=425}
    foreach ($name in $expectedDiscovery.Keys) {
        if ($Discovery.$name -isnot [int] -or $Discovery.$name -ne $expectedDiscovery[$name]) {
            throw "acceptance discovery count drift: $name"
        }
    }
    if ($Discovery.contained_names_absent -isnot [bool] -or -not $Discovery.contained_names_absent) {
        throw 'acceptance discovery retained contained identities'
    }
    if ($Quiescence.preflight_quiet -isnot [bool] -or -not $Quiescence.preflight_quiet -or
        $Quiescence.final_quiet -isnot [bool] -or -not $Quiescence.final_quiet) {
        throw 'acceptance quiescence is incomplete'
    }
    foreach ($name in @('control_fired','installed_sanitized','installer_sanitized','external_hits_absent','PYTHONUSERBASE_absent')) {
        if ($StartupIsolation.$name -isnot [bool] -or -not $StartupIsolation.$name) {
            throw "acceptance startup isolation is incomplete: $name"
        }
    }
    if ($StartupIsolation.PYTHONNOUSERSITE -isnot [string] -or $StartupIsolation.PYTHONNOUSERSITE -cne '1') {
        throw 'acceptance PYTHONNOUSERSITE projection drift'
    }
    foreach ($scenario in @('rhino','grasshopper')) {
        $entry = $Scenarios.$scenario
        if ($entry.success -isnot [bool] -or -not $entry.success -or
            $entry.restoration_verified -isnot [bool] -or -not $entry.restoration_verified -or
            $entry.telemetry_delta -isnot [int] -or $entry.telemetry_delta -ne 0) {
            throw "$scenario acceptance scenario is not safely restored"
        }
    }
    if ($PostRunArtifactSnapshot.verified -isnot [bool] -or -not $PostRunArtifactSnapshot.verified) {
        throw 'acceptance post-run candidate artifact snapshot is unverified'
    }
    if (@($Diagnostics).Count -eq 0) { throw 'acceptance requires retained diagnostic evidence'
    }
    $validatorPath = Get-ContainmentCanonicalPath -Path $script:ContainmentValidatorPath -Kind Leaf -Label 'validator script'
    return [ordered]@{
        schema_version = 1
        success = $true
        started_utc = $StartedUtc
        ended_utc = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.ffffffZ')
        validator = [ordered]@{sha256=(Get-ContainmentSha256 $validatorPath)}
        validator_result = [ordered]@{status='passed';success=$true}
        candidate = $Candidate
        installed_runtime = $InstalledRuntime
        quiescence = $Quiescence
        startup_isolation = $StartupIsolation
        discovery = $Discovery
        transport = [ordered]@{count=36;records=@($TransportRecords)}
        internal = [ordered]@{count=164;records=@($InternalRecords)}
        scenarios = $Scenarios
        diagnostics = @($Diagnostics)
        post_run_artifact_snapshot = $PostRunArtifactSnapshot
        restoration_verified = $true
        containment_hold = [ordered]@{activated=$false;receipt_path=$null;receipt_sha256=$null}
    }
}

function Get-TreeIdentity {
    param([Parameter(Mandatory = $true)][string]$Root)
    $projection = Get-ContainmentTreeProjection -Root $Root
    return [ordered]@{sha256=$projection.digest;files=@($projection.files)}
}

function Read-AndValidateContainmentAcceptance {
    param(
        [Parameter(Mandatory = $true)][string]$EvidenceDirectory,
        [switch]$RequireNormalEvidence,
        [AllowNull()][object]$Record
    )

    $evidenceRoot = Get-ContainmentCanonicalPath -Path $EvidenceDirectory -Kind Container -Label 'acceptance evidence directory'
    foreach ($failureName in @('containment-failure.json','containment-failure.sha256')) {
        if (Test-Path -LiteralPath (Join-Path $evidenceRoot $failureName) -PathType Leaf) {
            throw 'failure diagnostic is present beside acceptance'
        }
    }
    foreach ($holdName in @('containment-hold.json','containment-hold.sha256')) {
        if (Test-Path -LiteralPath (Join-Path $evidenceRoot $holdName) -PathType Leaf) {
            throw 'containment hold receipt is present beside acceptance'
        }
    }
    if ($PSBoundParameters.ContainsKey('Record')) {
        if ($null -eq $Record) { throw 'in-memory containment acceptance is null' }
        $record = $Record
    }
    else {
        $path = Join-Path $evidenceRoot $script:ContainmentAcceptanceFileName
        $sidecar = Join-Path $evidenceRoot 'containment-acceptance.sha256'
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or -not (Test-Path -LiteralPath $sidecar -PathType Leaf)) {
            throw 'successful acceptance evidence pair is missing'
        }
        $record = Read-ContainmentCanonicalJsonFile -Path $path -Label 'containment acceptance'
        [void](Assert-ContainmentSidecar -SidecarPath $sidecar -TargetPath $path -Label 'containment acceptance')
    }
    Assert-ContainmentExactProperties `
        -Value $record `
        -Expected @('schema_version','success','started_utc','ended_utc','validator','validator_result','candidate','installed_runtime','quiescence','startup_isolation','discovery','transport','internal','scenarios','diagnostics','post_run_artifact_snapshot','restoration_verified','containment_hold') `
        -Label 'containment acceptance'
    if ($record.schema_version -isnot [int] -or $record.schema_version -ne 1 -or
        $record.success -isnot [bool] -or -not $record.success -or
        $record.validator_result.success -isnot [bool] -or -not $record.validator_result.success -or
        $record.validator_result.status -isnot [string] -or $record.validator_result.status -cne 'passed') {
        throw 'containment acceptance does not contain fixed success'
    }
    if (-not (Test-ContainmentUtcTimestamp $record.started_utc) -or -not (Test-ContainmentUtcTimestamp $record.ended_utc) -or
        [string]$record.ended_utc -clt [string]$record.started_utc) { throw 'containment acceptance timestamp drift' }
    if ([string]$record.validator.sha256 -cne (Get-ContainmentSha256 $script:ContainmentValidatorPath)) {
        throw 'containment acceptance validator hash drift'
    }
    if ($record.containment_hold.activated -isnot [bool] -or $record.containment_hold.activated -or
        $null -ne $record.containment_hold.receipt_path -or
        $null -ne $record.containment_hold.receipt_sha256) { throw 'containment acceptance retained an activated hold' }
    if ($record.restoration_verified -isnot [bool] -or -not $record.restoration_verified -or
        $record.quiescence.preflight_quiet -isnot [bool] -or -not $record.quiescence.preflight_quiet -or
        $record.quiescence.final_quiet -isnot [bool] -or -not $record.quiescence.final_quiet) {
        throw 'containment acceptance restoration/quiescence is unverified'
    }
    foreach ($name in @('control_fired','installed_sanitized','installer_sanitized','external_hits_absent','PYTHONUSERBASE_absent')) {
        if ($record.startup_isolation.$name -isnot [bool] -or -not $record.startup_isolation.$name) {
            throw "containment acceptance startup isolation is incomplete: $name"
        }
    }
    if ($record.startup_isolation.PYTHONNOUSERSITE -isnot [string] -or
        $record.startup_isolation.PYTHONNOUSERSITE -cne '1') {
        throw 'containment acceptance startup environment drift'
    }
    $expectedDiscovery = [ordered]@{default=422;full=422;lean=20;readonly=148;interactive_full=425}
    foreach ($name in $expectedDiscovery.Keys) {
        if ($record.discovery.$name -isnot [int] -or $record.discovery.$name -ne $expectedDiscovery[$name]) {
            throw "containment acceptance discovery count drift: $name"
        }
    }
    if ($record.discovery.contained_names_absent -isnot [bool] -or -not $record.discovery.contained_names_absent) {
        throw 'containment acceptance discovery retained contained names'
    }
    Assert-ContainmentIndexedAcceptanceRecords -Records @($record.transport.records) -ExpectedCount 36 -Label 'transport'
    Assert-ContainmentIndexedAcceptanceRecords -Records @($record.internal.records) -ExpectedCount 164 -Label 'internal'
    if ($record.transport.count -isnot [int] -or $record.transport.count -ne 36 -or
        $record.internal.count -isnot [int] -or $record.internal.count -ne 164) {
        throw 'containment acceptance record container count drift'
    }
    foreach ($scenario in @('rhino','grasshopper')) {
        $entry = $record.scenarios.$scenario
        if ($entry.success -isnot [bool] -or -not $entry.success -or
            $entry.restoration_verified -isnot [bool] -or -not $entry.restoration_verified -or
            $entry.telemetry_delta -isnot [int] -or $entry.telemetry_delta -ne 0) {
            throw "$scenario acceptance scenario is not safely restored"
        }
    }
    if ($record.post_run_artifact_snapshot.verified -isnot [bool] -or
        -not $record.post_run_artifact_snapshot.verified) {
        throw 'post-run candidate artifact snapshot is unverified'
    }

    $candidate = $record.candidate
    $identityPath = Get-ContainmentCanonicalPath -Path ([string]$candidate.identity_path) -Kind Leaf -Label 'accepted candidate identity'
    $candidateSidecar = Get-ContainmentCanonicalPath -Path ([string]$candidate.sidecar_path) -Kind Leaf -Label 'accepted candidate sidecar'
    $installer = Get-ContainmentCanonicalPath -Path ([string]$candidate.installer_path) -Kind Leaf -Label 'accepted candidate installer'
    $identityPair = Assert-ContainmentSidecar -SidecarPath $candidateSidecar -TargetPath $identityPath -Label 'accepted candidate identity'
    if ([string]$candidate.identity_sha256 -cne $identityPair.TargetSha256 -or
        [string]$candidate.sidecar_sha256 -cne $identityPair.SidecarSha256 -or
        [string]$candidate.installer_sha256 -cne (Get-ContainmentSha256 $installer)) {
        throw 'accepted candidate identity/sidecar/installer hash drift'
    }
    [void](Assert-ContainmentHex $candidate.rook_sha 40 'accepted Rook source SHA')
    [void](Assert-ContainmentHex $candidate.chirp_sha 40 'accepted Chirp source SHA')
    $python = Get-ContainmentCanonicalPath -Path ([string]$record.installed_runtime.python_executable) -Kind Leaf -Label 'accepted installed Python'
    if ([string]$record.installed_runtime.python_sha256 -cne (Get-ContainmentSha256 $python)) { throw 'accepted installed Python hash drift' }

    if (@($record.diagnostics).Count -eq 0) { throw 'containment acceptance has no retained diagnostics' }
    $seen = @{}
    foreach ($diagnostic in @($record.diagnostics)) {
        Assert-ContainmentExactProperties -Value $diagnostic -Expected @('relative_path','sha256','size') -Label 'acceptance diagnostic'
        $relative = [string]$diagnostic.relative_path
        if ($seen.ContainsKey($relative)) { throw 'duplicate acceptance diagnostic path' }
        $seen[$relative] = $true
        $diagnosticPath = Resolve-ContainmentOwnedRelativePath -Root $evidenceRoot -RelativePath $relative -Kind Leaf -Label 'acceptance diagnostic artifact'
        if (-not (Test-ContainmentJsonInteger $diagnostic.size) -or
            [string]$diagnostic.sha256 -cne (Get-ContainmentSha256 $diagnosticPath) -or
            [long]$diagnostic.size -ne (Get-Item $diagnosticPath).Length) {
            throw 'acceptance diagnostic artifact hash/size drift'
        }
    }
    if ($RequireNormalEvidence) {
        if ($null -eq $record.post_run_artifact_snapshot.snapshot) {
            throw 'normal acceptance omitted the post-run candidate snapshot'
        }
        [void](Assert-CandidateArtifactSnapshot -Snapshot $record.post_run_artifact_snapshot.snapshot)
        if ([string]$record.post_run_artifact_snapshot.sha256 -cne
            [string]$record.post_run_artifact_snapshot.snapshot.sha256) {
            throw 'normal acceptance post-run snapshot digest drift'
        }

        $installed = $record.installed_runtime
        $privatePython = Get-ContainmentCanonicalPath -Path ([string]$installed.private_python.executable) -Kind Leaf -Label 'retained private Python'
        if ([string]$installed.private_python.sha256 -cne (Get-ContainmentSha256 $privatePython) -or
            [string]$installed.private_python.version -cne '3.11.9' -or @($installed.private_python.pth_files).Count -ne 0) {
            throw 'retained private Python identity drift'
        }
        [string[]]$privateFinalNames = @($installed.private_python.final_controlled_environment_names)
        if ($privateFinalNames.Count -ne 1 -or
            -not [string]::Equals($privateFinalNames[0], 'PYTHONNOUSERSITE', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'retained private Python identity environment drift'
        }
        foreach ($binding in @(
            [ordered]@{path=$installed.runtime_manifest_path;sha=$installed.runtime_manifest_sha256;label='runtime manifest'},
            [ordered]@{path=$installed.install_state_path;sha=$installed.install_state_sha256;label='install state'}
        )) {
            $boundPath = Get-ContainmentCanonicalPath -Path ([string]$binding.path) -Kind Leaf -Label ([string]$binding.label)
            if ([string]$binding.sha -cne (Get-ContainmentSha256 $boundPath)) { throw "retained $($binding.label) hash drift" }
        }
        foreach ($binding in @($installed.plugin_bindings)) {
            $pluginPath = Resolve-ContainmentOwnedRelativePath `
                -Root ([string]$installed.plugin_root) -RelativePath ([string]$binding.relative_path) `
                -Kind Leaf -Label 'retained installed plug-in'
            if (-not (Test-ContainmentJsonInteger $binding.size) -or
                [string]$binding.sha256 -cne (Get-ContainmentSha256 $pluginPath) -or
                [long]$binding.size -ne (Get-Item $pluginPath).Length) {
                throw 'retained installed plug-in hash/size drift'
            }
        }
        $installerTripwire = $record.startup_isolation.installer.tripwire
        foreach ($binding in @(
            [ordered]@{path=$installerTripwire.sitecustomize_path;sha=$installerTripwire.sitecustomize_sha256},
            [ordered]@{path=$installerTripwire.usercustomize_path;sha=$installerTripwire.usercustomize_sha256}
        )) {
            $tripwirePath = Get-ContainmentCanonicalPath -Path ([string]$binding.path) -Kind Leaf -Label 'installer startup tripwire'
            if ([string]$binding.sha -cne (Get-ContainmentSha256 $tripwirePath)) { throw 'installer startup tripwire hash drift' }
        }
        if ((Test-Path -LiteralPath ([string]$installerTripwire.sitecustomize_hit)) -or
            (Test-Path -LiteralPath ([string]$installerTripwire.usercustomize_hit))) {
            throw 'retained installer startup tripwire contains an execution hit'
        }

        $task7Root = Join-Path $evidenceRoot 'task7'
        $forbiddenSources = @(
            [string]$candidate.rook_root,
            [string]$candidate.chirp_root,
            [string]$candidate.rook_stage_path,
            [string]$candidate.chirp_stage_path
        )
        foreach ($forbiddenSource in $forbiddenSources) {
            if (-not [IO.Path]::IsPathRooted($forbiddenSource)) {
                throw 'retained candidate source exclusion is missing or non-absolute'
            }
        }
        $profileCounts = [ordered]@{full=422;lean=20;readonly=148}
        $globalIndex = 0
        foreach ($profile in $script:ContainmentProfiles) {
            $artifactRoot = Join-Path $task7Root "transport-$profile"
            $parsed = Read-AndValidateContainmentTransportArtifact `
                -Path (Join-Path $artifactRoot "transport-$profile.json") -ArtifactRoot $artifactRoot `
                -Profile $profile -ExpectedCount ([int]$profileCounts[$profile]) `
                -InstalledPython ([string]$installed.python_executable) -InstallRoot ([string]$installed.install_root) `
                -DataRoot ([string]$installed.data_root) -DspyCache ([string]$installed.dspy_cache) `
                -ChirpHome $installed.chirp_home -ForbiddenSourceRoots $forbiddenSources
            foreach ($probe in @($parsed.records)) {
                $accepted = $record.transport.records[$globalIndex]
                if ([int]$accepted.index -ne $globalIndex -or [string]$accepted.profile -cne $profile -or
                    $accepted.profile_index -isnot [int] -or
                    $accepted.profile_index -ne [int]$probe.profile_index -or
                    [string]$accepted.adapter -cne [string]$probe.adapter -or
                    [string]$accepted.tool -cne [string]$probe.tool -or
                    [string]$accepted.origin -cne [string]$probe.origin -or
                    -not (Test-ContainmentCanonicalEqual $accepted.result $probe.result) -or
                    -not (Test-ContainmentCanonicalEqual $accepted.transport $probe.transport) -or
                    -not (Test-ContainmentCanonicalEqual $accepted.spy $probe.spy)) {
                    throw "retained transport acceptance record drift at $globalIndex"
                }
                $globalIndex++
            }
        }
        if ($globalIndex -ne 36) { throw 'retained transport acceptance total drift' }
        $default = Read-AndValidateContainmentDiscoveryArtifact `
            -Path (Join-Path $task7Root 'discovery-default\discovery-default.json') `
            -Command 'discovery-default' -ExpectedCount 422 -InstalledPython ([string]$installed.python_executable) `
            -InstallRoot ([string]$installed.install_root) -DataRoot ([string]$installed.data_root) `
            -DspyCache ([string]$installed.dspy_cache) -ChirpHome $installed.chirp_home -ForbiddenSourceRoots $forbiddenSources
        $interactive = Read-AndValidateContainmentDiscoveryArtifact `
            -Path (Join-Path $task7Root 'discovery-interactive\discovery-interactive.json') `
            -Command 'discovery-interactive' -ExpectedCount 425 -InstalledPython ([string]$installed.python_executable) `
            -InstallRoot ([string]$installed.install_root) -DataRoot ([string]$installed.data_root) `
            -DspyCache ([string]$installed.dspy_cache) -ChirpHome $installed.chirp_home -ForbiddenSourceRoots $forbiddenSources
        if ([int]$default.catalog.count -ne [int]$record.discovery.default -or
            [int]$interactive.catalog.count -ne [int]$record.discovery.interactive_full) {
            throw 'retained discovery evidence/count binding drift'
        }
        $internal = Read-AndValidateContainmentInternalArtifact `
            -Path (Join-Path $task7Root 'internal-matrix\internal-matrix.json') `
            -InstalledPython ([string]$installed.python_executable) -InstallRoot ([string]$installed.install_root) `
            -DataRoot ([string]$installed.data_root) -DspyCache ([string]$installed.dspy_cache) `
            -ChirpHome $installed.chirp_home -ForbiddenSourceRoots $forbiddenSources
        if (-not (Test-ContainmentCanonicalEqual -Left @($record.internal.records) -Right @($internal.records))) {
            throw 'retained internal acceptance records drift'
        }

        foreach ($scenario in @('rhino','grasshopper')) {
            $scenarioRoot = Join-Path $evidenceRoot "scenarios\$scenario"
            $scenarioPath = Join-Path $scenarioRoot "$scenario-scenario.json"
            $scenarioSidecarPath = Join-Path $scenarioRoot "$scenario-scenario.sha256"
            $scenarioEvidence = Read-AndValidateScenarioEvidence `
                -Scenario $scenario -ScenarioPath $scenarioPath `
                -ScenarioSidecarPath $scenarioSidecarPath `
                -ExpectedInstalledRoot ([string]$installed.install_root)
            $accepted = $record.scenarios.$scenario
            [void](Assert-ContainmentRetainedScenarioBinding `
                -Scenario $scenario -Accepted $accepted -ScenarioEvidence $scenarioEvidence `
                -EvidencePath $scenarioPath -SidecarPath $scenarioSidecarPath)
        }
        $currentDiagnostics = @(Get-ContainmentDiagnosticProjection -EvidenceDirectory $evidenceRoot)
        if (-not (Test-ContainmentCanonicalEqual -Left @($record.diagnostics) -Right $currentDiagnostics)) {
            throw 'retained acceptance diagnostic file set drift'
        }
    }
    return $record
}

function Write-ContainmentFailureEvidence {
    param(
        [Parameter(Mandatory = $true)][string]$EvidenceDirectory,
        [Parameter(Mandatory = $true)][string]$RunId,
        [Parameter(Mandatory = $true)][string]$StartedUtc,
        [Parameter(Mandatory = $true)][string]$FailureStage,
        [Parameter(Mandatory = $true)][string]$Message,
        [switch]$InstallerStarted,
        [AllowNull()][object]$DurableHold,
        [object[]]$Diagnostics = @()
    )
    $root = Get-ContainmentCanonicalPath -Path $EvidenceDirectory -Kind Container -Label 'failure evidence directory'
    if (Test-Path -LiteralPath (Join-Path $root $script:ContainmentAcceptanceFileName)) { throw 'failure path may not coexist with successful acceptance' }
    [void](Assert-ContainmentHex $RunId 32 'failure run id')
    $bounded = if ($Message.Length -gt 4096) { $Message.Substring(0,4096) } else { $Message }
    $record = [ordered]@{
        schema_version=1
        success=$false
        run_id=$RunId
        started_utc=$StartedUtc
        ended_utc=[DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.ffffffZ')
        failure_stage=$FailureStage
        message=$bounded
        installer_started=[bool]$InstallerStarted
        durable_hold=$DurableHold
        diagnostics=@($Diagnostics)
    }
    return Write-CanonicalJsonPair -Path (Join-Path $root $script:ContainmentFailureFileName) -SidecarPath (Join-Path $root 'containment-failure.sha256') -Value $record
}

function Invoke-ContainmentStageSequence {
    param([Parameter(Mandatory = $true)][object[]]$Stages)
    foreach ($stage in $Stages) {
        try { & $stage.body }
        catch { throw "containment validation stage '$($stage.name)' failed: $($_.Exception.Message)" }
    }
}

function Invoke-ContainmentCandidateValidator {
    if ($VerifyEvidenceOnly) {
        if (-not $EvidenceDirectory -or $ArtifactDirectory -or $CandidateIdentityPath -or
            $CandidateSidecarPath -or $RhinoExe) {
            throw 'VerifyEvidenceOnly accepts only EvidenceDirectory'
        }
        $record = Read-AndValidateContainmentAcceptance -EvidenceDirectory $EvidenceDirectory -RequireNormalEvidence
        Write-Host "Containment acceptance evidence verified read-only: $EvidenceDirectory"
        return $record
    }
    foreach ($argument in @(
        [ordered]@{name='ArtifactDirectory';value=$ArtifactDirectory},
        [ordered]@{name='CandidateIdentityPath';value=$CandidateIdentityPath},
        [ordered]@{name='CandidateSidecarPath';value=$CandidateSidecarPath},
        [ordered]@{name='EvidenceDirectory';value=$EvidenceDirectory},
        [ordered]@{name='RhinoExe';value=$RhinoExe}
    )) {
        if ([string]::IsNullOrWhiteSpace([string]$argument.value)) { throw "normal mode requires $($argument.name)" }
    }
    $rhino = Get-ContainmentCanonicalPath -Path $RhinoExe -Kind Leaf -Label 'Rhino executable'
    $runId = [guid]::NewGuid().ToString('N')
    $startedUtc = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.ffffffZ')
    $failureStage = 'evidence-claim'
    $claimed = $false
    $installerStarted = $false
    $installerLaunchState = [pscustomobject]@{started=$false;process_id=$null}
    $acceptancePairStarted = $false
    $preflightEngaged = $false
    $candidate = $null
    $startupProjection = $null
    $preflightScript = $null
    $runtimeRoot = if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA 'Rook' } else { $null }
    $evidenceRoot = $null

    try {
        $claim = New-EvidenceDirectoryClaim -EvidenceDirectory $EvidenceDirectory -RunId $runId
        $evidenceRoot = [string]$claim.EvidenceDirectory
        $claimed = $true
        $diagnostics = New-ContainmentOwnedSubdirectory -Parent $evidenceRoot -Name 'diagnostics' -Label 'validator diagnostics'

        $failureStage = 'candidate-validation'
        $candidate = Read-AndValidateCandidateIdentity `
            -ArtifactDirectory $ArtifactDirectory -CandidateIdentityPath $CandidateIdentityPath `
            -CandidateSidecarPath $CandidateSidecarPath -ValidateSourceRepositories
        $candidateSnapshot = Get-CandidateArtifactSnapshot -Candidate $candidate
        if ([string]$candidate.private_python_sha256 -cne [string]$candidate.record.private_python.sha256) {
            throw 'candidate private Python return identity drift'
        }

        $failureStage = 'candidate-startup-isolation'
        $startupRoot = New-ContainmentOwnedSubdirectory -Parent $evidenceRoot -Name 'candidate-startup-isolation' -Label 'candidate startup isolation'
        $policyInstall = New-ContainmentOwnedSubdirectory -Parent $startupRoot -Name 'code-owned-install' -Label 'startup policy install root'
        $policyData = New-ContainmentOwnedSubdirectory -Parent $startupRoot -Name 'code-owned-data' -Label 'startup policy data root'
        $candidateStartup = Test-PythonStartupIsolation `
            -PythonPath ([string]$candidate.private_python_path) -EvidenceRoot $startupRoot `
            -InstallRoot $policyInstall -DataRoot $policyData -ExpectedVersion '3.11.9'
        if (-not [bool]$candidateStartup.control_fired -or -not [bool]$candidateStartup.sanitized) {
            throw 'candidate startup-isolation proof is incomplete'
        }

        $failureStage = 'startup-surface-inventory'
        if (-not $env:LOCALAPPDATA -or -not $env:APPDATA -or -not $env:USERPROFILE) {
            throw 'LOCALAPPDATA, APPDATA, and USERPROFILE are required'
        }
        $registryFile = Get-ContainmentCompanionRegistryFileName -AppDataRoot $env:APPDATA
        $startupProjection = Get-ContainmentStartupSurfaceProjection `
            -LocalAppDataRoot $env:LOCALAPPDATA -AppDataRoot $env:APPDATA `
            -HomeRoot $env:USERPROFILE -RegistryFileName $registryFile
        $expectedPluginRoot = Join-Path $env:APPDATA 'McNeel\Rhinoceros\8.0\Plug-ins\RookNative'
        [void](Assert-ContainmentStartupProjection `
            -Projection $startupProjection -ExpectedVenvPath (Join-Path $runtimeRoot 'venv') `
            -ExpectedPluginRoot $expectedPluginRoot)

        $preflightScript = Resolve-ContainmentOwnedRelativePath `
            -Root ([string]$candidate.artifact_directory) `
            -RelativePath 'stage/Rook/installer/rook_process_preflight.ps1' `
            -Kind Leaf -Label 'candidate process preflight script'
        $failureStage = 'preinstall-quiescence'
        $preflightEngaged = $true
        $preClose = Invoke-ContainmentProcessPreflight `
            -Mode close -PreflightScript $preflightScript -RookRoot $runtimeRoot `
            -EvidenceDirectory $diagnostics -Label 'preinstall close'
        $preQuiet = Invoke-ContainmentProcessPreflight `
            -Mode enumerate -PreflightScript $preflightScript -RookRoot $runtimeRoot `
            -EvidenceDirectory $diagnostics -Label 'preinstall quiet resweep'
        if (-not [bool]$preQuiet.quiet) { throw 'preinstall process boundary is not quiet' }

        $failureStage = 'installer-startup-isolation'
        $installerTripwire = New-ContainmentInstallerTripwire `
            -PythonPath ([string]$candidate.private_python_path) -EvidenceDirectory $evidenceRoot
        $installStartedDate = [DateTime]::UtcNow
        $installStartedText = $installStartedDate.ToString('yyyy-MM-ddTHH:mm:ss.ffffffZ')
        $onInstallerStarted = {
            param([int]$ProcessId)
            $installerLaunchState.started = $true
            $installerLaunchState.process_id = $ProcessId
        }.GetNewClosure()
        $installation = Invoke-ContainmentCandidateInstallation `
            -Candidate $candidate -Tripwire $installerTripwire `
            -DiagnosticDirectory $diagnostics -StartedUtc $installStartedText `
            -OnInstallerStarted $onInstallerStarted
        $installerStarted = [bool]$installerLaunchState.started

        $failureStage = 'installed-runtime-certification'
        $installed = Assert-ContainmentInstalledRuntime `
            -Candidate $candidate -LocalAppDataRoot $env:LOCALAPPDATA -AppDataRoot $env:APPDATA `
            -InstallStartedUtc $installStartedDate -DiagnosticDirectory $diagnostics
        $registryFile = Get-ContainmentCompanionRegistryFileName -AppDataRoot $env:APPDATA
        $startupProjection = Get-ContainmentStartupSurfaceProjection `
            -LocalAppDataRoot $env:LOCALAPPDATA -AppDataRoot $env:APPDATA `
            -HomeRoot $env:USERPROFILE -RegistryFileName $registryFile
        [void](Assert-ContainmentStartupProjection `
            -Projection $startupProjection -ExpectedVenvPath (Join-Path $runtimeRoot 'venv') `
            -ExpectedPluginRoot ([string]$installed.plugin_root))

        $failureStage = 'installed-containment-certification'
        $forbiddenSources = @(
            [string]$candidate.record.sources.rook.root,
            [string]$candidate.record.sources.chirp.root,
            [string]$candidate.record.sources.rook.stage_path,
            [string]$candidate.record.sources.chirp.stage_path
        )
        $task7 = Invoke-ContainmentTask7Certification `
            -EvidenceDirectory $evidenceRoot -InstalledPython ([string]$installed.python_executable) `
            -InstallRoot ([string]$installed.install_root) -DataRoot ([string]$installed.data_root) `
            -DspyCache ([string]$installed.dspy_cache) -ChirpHome $installed.chirp_home `
            -ForbiddenSourceRoots $forbiddenSources

        $failureStage = 'authorized-live-scenarios'
        $scenarios = Invoke-ContainmentLiveScenarios `
            -EvidenceDirectory $evidenceRoot -InstalledPython ([string]$installed.python_executable) `
            -InstallRoot ([string]$installed.install_root) -DataRoot ([string]$installed.data_root) `
            -DspyCache ([string]$installed.dspy_cache) -ChirpHome $installed.chirp_home -RhinoExe $rhino

        $failureStage = 'final-quiescence'
        $finalClose = Invoke-ContainmentProcessPreflight `
            -Mode close -PreflightScript $preflightScript -RookRoot $runtimeRoot `
            -EvidenceDirectory $diagnostics -Label 'final close'
        $finalQuiet = Invoke-ContainmentProcessPreflight `
            -Mode enumerate -PreflightScript $preflightScript -RookRoot $runtimeRoot `
            -EvidenceDirectory $diagnostics -Label 'final quiet resweep'
        if (-not [bool]$finalQuiet.quiet) { throw 'final process boundary is not quiet' }

        $failureStage = 'post-run-candidate-rehash'
        $postCandidate = Read-AndValidateCandidateIdentity `
            -ArtifactDirectory $ArtifactDirectory -CandidateIdentityPath $CandidateIdentityPath `
            -CandidateSidecarPath $CandidateSidecarPath -ValidateSourceRepositories
        $postSnapshot = Get-CandidateArtifactSnapshot -Candidate $postCandidate
        if (-not (Test-ContainmentCanonicalEqual $candidateSnapshot $postSnapshot) -or
            [string]$postCandidate.identity_sha256 -cne [string]$candidate.identity_sha256 -or
            [string]$postCandidate.installer_sha256 -cne [string]$candidate.installer_sha256) {
            throw 'candidate artifact drifted during installed/live acceptance'
        }

        $failureStage = 'acceptance-write'
        $acceptedCandidate = [ordered]@{
            artifact_directory=$candidate.artifact_directory
            identity_path=$candidate.identity_path;identity_sha256=$candidate.identity_sha256
            sidecar_path=$candidate.sidecar_path;sidecar_sha256=$candidate.sidecar_sha256
            installer_path=$candidate.installer_path;installer_sha256=$candidate.installer_sha256
            rook_sha=[string]$candidate.record.sources.rook.sha
            chirp_sha=[string]$candidate.record.sources.chirp.sha
            rook_root=[string]$candidate.record.sources.rook.root
            chirp_root=[string]$candidate.record.sources.chirp.root
            rook_stage_path=[string]$candidate.record.sources.rook.stage_path
            chirp_stage_path=[string]$candidate.record.sources.chirp.stage_path
        }
        $startupIsolation = [ordered]@{
            control_fired=$true;installed_sanitized=$true;installer_sanitized=$true
            external_hits_absent=[bool]$installation.external_hits_absent
            PYTHONUSERBASE_absent=$true;PYTHONNOUSERSITE='1'
            candidate_runtime=$candidateStartup;installer=$installation
            probe_hashes=@($candidateStartup.probe_hashes)
        }
        $quiescence = [ordered]@{
            preflight_quiet=[bool]$preQuiet.quiet;final_quiet=[bool]$finalQuiet.quiet
            pre_close=$preClose;pre_resweep=$preQuiet;final_close=$finalClose;final_resweep=$finalQuiet
        }
        $postRunSnapshot = [ordered]@{verified=$true;snapshot=$postSnapshot;sha256=$postSnapshot.sha256}
        $diagnosticProjection = @(Get-ContainmentDiagnosticProjection -EvidenceDirectory $evidenceRoot)
        $acceptance = New-ContainmentAcceptanceRecord `
            -RunId $runId -StartedUtc $startedUtc -Candidate $acceptedCandidate `
            -InstalledRuntime $installed -Quiescence $quiescence -StartupIsolation $startupIsolation `
            -Discovery $task7.discovery -TransportRecords @($task7.transport_records) `
            -InternalRecords @($task7.internal_records) -Scenarios $scenarios `
            -Diagnostics $diagnosticProjection -PostRunArtifactSnapshot $postRunSnapshot
        [void](Read-AndValidateContainmentAcceptance `
            -EvidenceDirectory $evidenceRoot -RequireNormalEvidence -Record $acceptance)
        [void](Write-CanonicalJsonPair `
            -Path (Join-Path $evidenceRoot $script:ContainmentAcceptanceFileName) `
            -SidecarPath (Join-Path $evidenceRoot 'containment-acceptance.sha256') -Value $acceptance)
        $acceptancePairStarted = $true
        $verified = Read-AndValidateContainmentAcceptance -EvidenceDirectory $evidenceRoot -RequireNormalEvidence
        $acceptancePairStarted = $false
        Write-Host "Containment candidate acceptance passed: $evidenceRoot"
        return $verified
    }
    catch {
        $caught = $_
        $emergencyFailureLabels = @('ownership_ambiguous','restoration_failed','cleanup_failed')
        $failureLabel = $null
        if ($caught.Exception.Data.Contains('ContainmentFailureLabel')) {
            $failureLabel = [string]$caught.Exception.Data['ContainmentFailureLabel']
        }
        $requiresEmergencyStage = ($failureStage -ceq 'final-quiescence' -or
            $emergencyFailureLabels -ccontains $failureLabel)
        $installerStarted = $installerStarted -or [bool]$installerLaunchState.started
        $durableHold = $null
        if ($claimed) {
            if ($acceptancePairStarted) {
                foreach ($partialAcceptance in @(
                    (Join-Path $evidenceRoot 'containment-acceptance.sha256'),
                    (Join-Path $evidenceRoot $script:ContainmentAcceptanceFileName)
                )) {
                    if (Test-Path -LiteralPath $partialAcceptance -PathType Leaf) {
                        Remove-Item -LiteralPath $partialAcceptance -Force -ErrorAction SilentlyContinue
                    }
                }
            }
            if ($installerStarted) {
                $holdMessage = $null
                try {
                    $failureStageBeforeHold = $failureStage
                    $cleanupClose = Invoke-ContainmentProcessPreflight `
                        -Mode close -PreflightScript $preflightScript -RookRoot $runtimeRoot `
                        -EvidenceDirectory (Join-Path $evidenceRoot 'diagnostics') -Label 'emergency close'
                    $cleanupQuiet = Invoke-ContainmentProcessPreflight `
                        -Mode enumerate -PreflightScript $preflightScript -RookRoot $runtimeRoot `
                        -EvidenceDirectory (Join-Path $evidenceRoot 'diagnostics') -Label 'emergency quiet resweep'
                    $registryFile = Get-ContainmentCompanionRegistryFileName -AppDataRoot $env:APPDATA
                    $startupProjection = Get-ContainmentStartupSurfaceProjection `
                        -LocalAppDataRoot $env:LOCALAPPDATA -AppDataRoot $env:APPDATA `
                        -HomeRoot $env:USERPROFILE -RegistryFileName $registryFile
                    [void](Assert-ContainmentStartupProjection `
                        -Projection $startupProjection -ExpectedVenvPath (Join-Path $runtimeRoot 'venv') `
                        -ExpectedPluginRoot (Join-Path $env:APPDATA 'McNeel\Rhinoceros\8.0\Plug-ins\RookNative'))
                    $holdResweepAction = {
                        Invoke-ContainmentProcessPreflight `
                            -Mode enumerate -PreflightScript $preflightScript -RookRoot $runtimeRoot `
                            -EvidenceDirectory (Join-Path $evidenceRoot 'diagnostics') -Label 'post-hold quiet resweep'
                    }.GetNewClosure()
                    $durableHold = Enter-ContainmentDurableHold `
                        -CandidateIdentitySha256 ([string]$candidate.identity_sha256) -RunId $runId `
                        -LocalAppDataRoot $env:LOCALAPPDATA -AppDataRoot $env:APPDATA -HomeRoot $env:USERPROFILE `
                        -StartupProjection $startupProjection -FinalQuietResweep $cleanupQuiet `
                        -FinalQuietResweepAction $holdResweepAction
                    $failureStage = if ($requiresEmergencyStage) { 'emergency-quiescence' } else { $failureStageBeforeHold }
                }
                catch {
                    $holdFailure = $_
                    $holdMessage = [string]$_.Exception.Message
                    if ($holdMessage.Length -gt 2048) { $holdMessage = $holdMessage.Substring(0,2048) }
                    $partialHoldPath = $null
                    if ($holdFailure.Exception.Data.Contains('ContainmentHoldPath')) {
                        $partialHoldPath = [string]$holdFailure.Exception.Data['ContainmentHoldPath']
                    }
                    $partialProjection = $null
                    $partialProjectionSha = $null
                    $partialReceiptPath = $null
                    $partialReceiptSha = $null
                    $partialSidecarPath = $null
                    $partialSidecarSha = $null
                    if ($holdFailure.Exception.Data.Contains('ContainmentHoldProjection')) {
                        $partialProjection = $holdFailure.Exception.Data['ContainmentHoldProjection']
                    }
                    if ($holdFailure.Exception.Data.Contains('ContainmentHoldProjectionSha256')) {
                        $partialProjectionSha = [string]$holdFailure.Exception.Data['ContainmentHoldProjectionSha256']
                    }
                    if ($holdFailure.Exception.Data.Contains('ContainmentHoldReceiptPath')) {
                        $partialReceiptPath = [string]$holdFailure.Exception.Data['ContainmentHoldReceiptPath']
                    }
                    if ($holdFailure.Exception.Data.Contains('ContainmentHoldReceiptSha256')) {
                        $partialReceiptSha = [string]$holdFailure.Exception.Data['ContainmentHoldReceiptSha256']
                    }
                    if ($holdFailure.Exception.Data.Contains('ContainmentHoldReceiptSidecarPath')) {
                        $partialSidecarPath = [string]$holdFailure.Exception.Data['ContainmentHoldReceiptSidecarPath']
                    }
                    if ($holdFailure.Exception.Data.Contains('ContainmentHoldReceiptSidecarSha256')) {
                        $partialSidecarSha = [string]$holdFailure.Exception.Data['ContainmentHoldReceiptSidecarSha256']
                    }
                    $durableHold = [ordered]@{
                        success=$false;path=$partialHoldPath
                        sha256=$(if ($partialReceiptSha) { $partialReceiptSha } else { $partialProjectionSha })
                        sidecar_sha256=$partialSidecarSha
                        receipt_path=$partialReceiptPath;receipt_sidecar_path=$partialSidecarPath
                        projection=$partialProjection;projection_sha256=$partialProjectionSha;error=$holdMessage
                    }
                    $failureStage = 'emergency-quiescence'
                }
            }
            elseif ($preflightEngaged -and $preflightScript -and $runtimeRoot) {
                try {
                    [void](Invoke-ContainmentProcessPreflight `
                        -Mode close -PreflightScript $preflightScript -RookRoot $runtimeRoot `
                        -EvidenceDirectory (Join-Path $evidenceRoot 'diagnostics') -Label 'failed-run close')
                    $failedRunQuiet = Invoke-ContainmentProcessPreflight `
                        -Mode enumerate -PreflightScript $preflightScript -RookRoot $runtimeRoot `
                        -EvidenceDirectory (Join-Path $evidenceRoot 'diagnostics') -Label 'failed-run quiet resweep'
                    if (-not [bool]$failedRunQuiet.quiet) {
                        throw 'failed-run process boundary is not quiet'
                    }
                }
                catch { $failureStage = 'emergency-quiescence' }
            }
            try {
                $diagnosticProjection = @(Get-ContainmentDiagnosticProjection -EvidenceDirectory $evidenceRoot)
                [void](Write-ContainmentFailureEvidence `
                    -EvidenceDirectory $evidenceRoot -RunId $runId -StartedUtc $startedUtc `
                    -FailureStage $failureStage -Message ([string]$caught.Exception.Message) `
                    -InstallerStarted:$installerStarted -DurableHold $durableHold -Diagnostics $diagnosticProjection)
            }
            catch {
                throw "containment validation failed at $failureStage and failure evidence could not be persisted: $($caught.Exception.Message); evidence error: $($_.Exception.Message)"
            }
        }
        throw "containment validation failed at $failureStage`: $($caught.Exception.Message)"
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    try {
        [void](Invoke-ContainmentCandidateValidator)
        exit 0
    }
    catch {
        $summary = [string]$_.Exception.Message
        if ($summary.Length -gt 4096) { $summary = $summary.Substring(0,4096) }
        [Console]::Error.WriteLine($summary)
        exit 1
    }
}
