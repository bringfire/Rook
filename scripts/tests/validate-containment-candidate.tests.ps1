param(
    [Parameter(Mandatory = $true)]
    [string]$PrivatePythonPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$TestRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestRoot)
$ValidatorPath = Join-Path $RepoRoot 'scripts\validate-containment-candidate.ps1'
$WindowsPowerShell = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
$script:TestsPassed = 0

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Assert-False {
    param([bool]$Condition, [string]$Message)
    if ($Condition) { throw $Message }
}

function Assert-Equal {
    param([AllowNull()][object]$Actual, [AllowNull()][object]$Expected, [string]$Message)
    if ($null -eq $Actual -and $null -eq $Expected) { return }
    if ($null -eq $Actual -or $null -eq $Expected -or [string]$Actual -cne [string]$Expected) {
        throw "$Message Expected=[$Expected] Actual=[$Actual]"
    }
}

function Assert-SequenceEqual {
    param([object[]]$Actual, [object[]]$Expected, [string]$Message)
    Assert-Equal -Actual $Actual.Count -Expected $Expected.Count -Message "$Message count"
    for ($index = 0; $index -lt $Expected.Count; $index++) {
        Assert-Equal -Actual $Actual[$index] -Expected $Expected[$index] -Message "$Message index=$index"
    }
}

function Assert-Contains {
    param([string]$Text, [string]$Expected, [string]$Message)
    Assert-True -Condition $Text.Contains($Expected) -Message "$Message Missing=[$Expected]"
}

function Assert-ThrowsLike {
    param([scriptblock]$Body, [string]$Pattern, [string]$Message)
    $threw = $false
    try { & $Body } catch {
        $threw = $true
        if ([string]$_.Exception.Message -notmatch $Pattern) {
            throw "$Message Wrong error: $($_.Exception.Message)"
        }
    }
    if (-not $threw) { throw "$Message Expected an exception matching [$Pattern]." }
}

function Write-TestUtf8NoBom {
    param([string]$Path, [string]$Text)
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path -LiteralPath $parent -PathType Container)) {
        [IO.Directory]::CreateDirectory($parent) | Out-Null
    }
    [IO.File]::WriteAllText($Path, $Text, [Text.UTF8Encoding]::new($false))
}

function Write-TestAscii {
    param([string]$Path, [string]$Text)
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path -LiteralPath $parent -PathType Container)) {
        [IO.Directory]::CreateDirectory($parent) | Out-Null
    }
    [IO.File]::WriteAllText($Path, $Text, [Text.Encoding]::ASCII)
}

function Get-TestSha256 {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function New-TestFaultingCreateNewStream {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [ValidateSet('write','flush','dispose')][string]$FaultStage,
        [AllowNull()][scriptblock]$AfterDispose
    )

    $inner = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    $wrapper = [pscustomobject]@{
        Inner=$inner
        FaultStage=$FaultStage
        AfterDispose=$AfterDispose
        SafeFileHandle=$inner.SafeFileHandle
    }
    Add-Member -InputObject $wrapper -MemberType ScriptMethod -Name Write -Value {
        param([byte[]]$Buffer,[int]$Offset,[int]$Count)
        if ($this.FaultStage -ceq 'write') {
            $partial = [Math]::Min(1, $Count)
            if ($partial -gt 0) { $this.Inner.Write($Buffer, $Offset, $partial) }
            throw [IO.IOException]::new('injected create-new mid-write failure')
        }
        $this.Inner.Write($Buffer, $Offset, $Count)
    }
    Add-Member -InputObject $wrapper -MemberType ScriptMethod -Name Flush -Value {
        param([bool]$FlushToDisk)
        $this.Inner.Flush($FlushToDisk)
        if ($this.FaultStage -ceq 'flush') {
            throw [IO.IOException]::new('injected create-new durable-flush failure')
        }
    }
    Add-Member -InputObject $wrapper -MemberType ScriptMethod -Name Dispose -Value {
        $this.Inner.Dispose()
        if ($null -ne $this.AfterDispose) { & $this.AfterDispose }
        if ($this.FaultStage -ceq 'dispose') {
            throw [IO.IOException]::new('injected create-new dispose failure')
        }
    }
    return $wrapper
}

function New-TestDirectory {
    param([string]$Parent, [string]$Name)
    $path = Join-Path $Parent $Name
    [IO.Directory]::CreateDirectory($path) | Out-Null
    return (Resolve-Path -LiteralPath $path).Path
}

function Remove-TestTree {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $full = [IO.Path]::GetFullPath($Path)
    $temp = [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\'
    if (-not $full.StartsWith($temp, [StringComparison]::OrdinalIgnoreCase)) {
        throw "refusing to remove non-temporary test path: $full"
    }
    Remove-Item -LiteralPath $full -Recurse -Force
}

function ConvertTo-TestCanonicalJson {
    param([AllowNull()][object]$Value)
    if ($null -eq $Value) { return 'null' }
    if ($Value -is [bool]) { if ($Value) { return 'true' } else { return 'false' } }
    if ($Value -is [string] -or $Value -is [char]) { return ConvertTo-Json -InputObject ([string]$Value) -Compress }
    if ($Value -is [byte] -or $Value -is [sbyte] -or $Value -is [int16] -or $Value -is [uint16] -or
        $Value -is [int32] -or $Value -is [uint32] -or $Value -is [int64] -or $Value -is [uint64] -or
        $Value -is [single] -or $Value -is [double] -or $Value -is [decimal]) {
        return [Convert]::ToString($Value, [Globalization.CultureInfo]::InvariantCulture)
    }
    if ($Value -is [Collections.IDictionary]) {
        [string[]]$keys = @($Value.Keys | ForEach-Object { [string]$_ })
        [Array]::Sort($keys, [StringComparer]::Ordinal)
        $parts = foreach ($key in $keys) {
            (ConvertTo-Json -InputObject $key -Compress) + ':' + (ConvertTo-TestCanonicalJson -Value ($Value[$key]))
        }
        return '{' + ($parts -join ',') + '}'
    }
    if ($Value -is [pscustomobject]) {
        $mapping = [ordered]@{}
        foreach ($property in $Value.PSObject.Properties) { $mapping[$property.Name] = $property.Value }
        return ConvertTo-TestCanonicalJson -Value $mapping
    }
    if ($Value -is [Collections.IEnumerable]) {
        $items = foreach ($item in $Value) { ConvertTo-TestCanonicalJson -Value $item }
        return '[' + ($items -join ',') + ']'
    }
    throw "unsupported canonical JSON test value: $($Value.GetType().FullName)"
}

function Get-TestValueSha256 {
    param([AllowNull()][object]$Value)
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes((ConvertTo-TestCanonicalJson -Value $Value))
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($algorithm.ComputeHash($bytes)) -replace '-', '').ToLowerInvariant() }
    finally { $algorithm.Dispose() }
}

function Invoke-TestNative {
    param([string]$Executable, [string[]]$Arguments)
    $output = @(& $Executable @Arguments 2>&1)
    $exitCode = $LASTEXITCODE
    return [pscustomobject]@{ ExitCode = $exitCode; Output = $output; Text = ($output -join "`n") }
}

function Assert-FullCpythonFixtureAndControl {
    param([string]$PythonPath)
    Assert-True -Condition ([IO.Path]::IsPathRooted($PythonPath)) -Message 'PrivatePythonPath must be absolute.'
    Assert-True -Condition (Test-Path -LiteralPath $PythonPath -PathType Leaf) -Message "PrivatePythonPath is missing: $PythonPath"
    $canonical = (Resolve-Path -LiteralPath $PythonPath).Path
    $probeCode = @'
import json, os, site, sys
print(json.dumps({
    "base_executable": os.path.realpath(getattr(sys, "_base_executable", sys.executable)),
    "base_prefix": os.path.realpath(sys.base_prefix),
    "executable": os.path.realpath(sys.executable),
    "prefix": os.path.realpath(sys.prefix),
    "user_site": os.path.realpath(site.getusersitepackages()),
    "version": list(sys.version_info[:3]),
}, sort_keys=True, separators=(",", ":")))
'@
    $probePath = Join-Path $env:TEMP ("rook-t10-fixture-probe-" + [guid]::NewGuid().ToString('N') + '.py')
    try {
        Write-TestUtf8NoBom -Path $probePath -Text $probeCode
        $probe = Invoke-TestNative -Executable $canonical -Arguments @($probePath)
        Assert-Equal -Actual $probe.ExitCode -Expected 0 -Message 'Full-CPython fixture probe failed.'
        $record = $probe.Text | ConvertFrom-Json
    } finally {
        if (Test-Path -LiteralPath $probePath -PathType Leaf) { Remove-Item -LiteralPath $probePath -Force }
    }
    Assert-Equal -Actual ((Resolve-Path -LiteralPath ([string]$record.executable)).Path) -Expected $canonical -Message 'Fixture executable identity drifted.'
    Assert-Equal -Actual ([string]$record.prefix) -Expected ([string]$record.base_prefix) -Message 'Fixture is a virtual environment.'
    Assert-Equal -Actual ([string]$record.base_executable) -Expected ([string]$record.executable) -Message 'Fixture base executable differs from executable.'
    Assert-True -Condition ([int]$record.version[0] -eq 3 -and [int]$record.version[1] -ge 10) -Message 'Fixture Python version is unsupported.'
    $fixtureRoot = Split-Path -Parent $canonical
    Assert-False -Condition (Test-Path -LiteralPath (Join-Path $fixtureRoot 'pyvenv.cfg')) -Message 'Fixture root contains pyvenv.cfg.'
    $pthFiles = @(Get-ChildItem -LiteralPath $fixtureRoot -Filter '*._pth' -File -ErrorAction Stop)
    Assert-Equal -Actual $pthFiles.Count -Expected 0 -Message 'Fixture is ._pth-isolated.'

    $controlRoot = Join-Path $env:TEMP ("rook-t10-fixture-control-" + [guid]::NewGuid().ToString('N'))
    [IO.Directory]::CreateDirectory($controlRoot) | Out-Null
    $saved = @{}
    foreach ($name in @('PYTHONPATH','PYTHONHOME','PYTHONUSERBASE','PYTHONNOUSERSITE','DSPY_MODEL','DSPY_CACHEDIR','CHIRP_HOME')) {
        $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
    $rookSaved = @{}
    foreach ($entry in [Environment]::GetEnvironmentVariables('Process').GetEnumerator()) {
        if ([string]$entry.Key -match '^(?i:ROOK_)') {
            $rookSaved[[string]$entry.Key] = [string]$entry.Value
            [Environment]::SetEnvironmentVariable([string]$entry.Key, $null, 'Process')
        }
    }
    try {
        $ownedBase = New-TestDirectory -Parent $controlRoot -Name 'owned-user-base'
        [Environment]::SetEnvironmentVariable('PYTHONUSERBASE', $ownedBase, 'Process')
        $siteProbe = Invoke-TestNative -Executable $canonical -Arguments @('-S','-c','import site; print(site.getusersitepackages())')
        Assert-Equal -Actual $siteProbe.ExitCode -Expected 0 -Message 'Fixture user-site derivation failed.'
        $userSite = $siteProbe.Text.Trim()
        Assert-True -Condition ([IO.Path]::IsPathRooted($userSite)) -Message 'Derived user site is not absolute.'
        [IO.Directory]::CreateDirectory($userSite) | Out-Null
        $tripwire = "from pathlib import Path; Path(__file__).with_suffix('.hit').write_text('executed', encoding='ascii')`n"
        Write-TestUtf8NoBom -Path (Join-Path $userSite 'sitecustomize.py') -Text $tripwire
        Write-TestUtf8NoBom -Path (Join-Path $userSite 'usercustomize.py') -Text $tripwire
        $controlProbePath = Join-Path $controlRoot 'control-probe.py'
        Write-TestUtf8NoBom -Path $controlProbePath -Text "import json, site, sys`nprint(json.dumps({'enable': site.ENABLE_USER_SITE, 'no_user_site': sys.flags.no_user_site, 'site': site.getusersitepackages()}, sort_keys=True, separators=(',', ':')))`n"
        $control = Invoke-TestNative -Executable $canonical -Arguments @($controlProbePath)
        Assert-Equal -Actual $control.ExitCode -Expected 0 -Message 'Unsanitized fixture-validity control failed.'
        $controlRecord = $control.Text | ConvertFrom-Json
        Assert-True -Condition ([bool]$controlRecord.enable) -Message 'Unsanitized fixture control did not enable user site.'
        Assert-Equal -Actual ([int]$controlRecord.no_user_site) -Expected 0 -Message 'Unsanitized fixture unexpectedly disabled user site.'
        Assert-True -Condition (Test-Path -LiteralPath (Join-Path $userSite 'sitecustomize.hit') -PathType Leaf) -Message 'sitecustomize unsanitized control did not fire.'
        Assert-True -Condition (Test-Path -LiteralPath (Join-Path $userSite 'usercustomize.hit') -PathType Leaf) -Message 'usercustomize unsanitized control did not fire.'
    } finally {
        foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
        foreach ($name in $rookSaved.Keys) { [Environment]::SetEnvironmentVariable($name, $rookSaved[$name], 'Process') }
        Remove-TestTree -Path $controlRoot
    }
    return $canonical
}

$PrivatePythonPath = Assert-FullCpythonFixtureAndControl -PythonPath $PrivatePythonPath

if (-not (Test-Path -LiteralPath $ValidatorPath -PathType Leaf)) {
    throw 'EXPECTED_RED:T10:VALIDATOR_MISSING'
}

. $ValidatorPath

function Invoke-Test {
    param([string]$Name, [scriptblock]$Body)
    & $Body
    $script:TestsPassed++
    Write-Host "PASS: $Name"
}

function New-ChildScript {
    param([string]$Root, [string]$Name, [string]$Body)
    $path = Join-Path $Root $Name
    Write-TestUtf8NoBom -Path $path -Text $Body
    return $path
}

function New-FakeFileIdentity {
    param([string]$Path)
    $item = Get-Item -LiteralPath $Path -Force
    $version = [Diagnostics.FileVersionInfo]::GetVersionInfo($item.FullName)
    return [ordered]@{
        path = $item.FullName
        size = [long]$item.Length
        sha256 = Get-TestSha256 -Path $item.FullName
        file_version = [string]$version.FileVersion
        product_version = [string]$version.ProductVersion
    }
}

function New-TestProjection {
    param([string]$Root, [string[]]$RelativePaths)
    [string[]]$sortedRelativePaths = @($RelativePaths)
    [Array]::Sort($sortedRelativePaths, [StringComparer]::Ordinal)
    $files = foreach ($relative in $sortedRelativePaths) {
        $path = Join-Path $Root $relative
        $item = Get-Item -LiteralPath $path -Force
        [ordered]@{ relative_path = $relative.Replace('\','/'); sha256 = Get-TestSha256 -Path $path; size = [long]$item.Length }
    }
    $json = ConvertTo-TestCanonicalJson -Value @($files)
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($json)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { $digest = ([BitConverter]::ToString($algorithm.ComputeHash($bytes)) -replace '-', '').ToLowerInvariant() } finally { $algorithm.Dispose() }
    return [ordered]@{ digest = $digest; files = @($files) }
}

function New-MinimalCandidateFixture {
    param([string]$Root)
    $artifact = New-TestDirectory -Parent $Root -Name 'candidate'
    $stageRook = New-TestDirectory -Parent (New-TestDirectory -Parent $artifact -Name 'stage') -Name 'Rook'
    $stageChirp = New-TestDirectory -Parent (Join-Path $artifact 'stage') -Name 'Chirp'
    $installerSourceDir = New-TestDirectory -Parent $stageRook -Name 'installer'
    $wheelhouse = New-TestDirectory -Parent (New-TestDirectory -Parent $installerSourceDir -Name 'runtime') -Name 'python-wheelhouse'
    Write-TestAscii -Path (Join-Path $wheelhouse 'fixture.whl') -Text 'wheel-bytes'
    $runtimeDir = New-TestDirectory -Parent (New-TestDirectory -Parent (New-TestDirectory -Parent (Join-Path $installerSourceDir 'runtime') -Name 'python') -Name 'cpython-3.11.9') -Name 'payload'
    $privatePythonDir = Split-Path -Parent $runtimeDir
    $privatePython = Join-Path $privatePythonDir 'python.exe'
    Copy-Item -LiteralPath $WindowsPowerShell -Destination $privatePython
    Write-TestUtf8NoBom -Path (Join-Path $installerSourceDir 'RookSetup.iss') -Text "fake reviewed installer`n"
    $outputDir = New-TestDirectory -Parent $artifact -Name 'output'
    $installer = Join-Path $outputDir 'Rook-Setup-fake.exe'
    Copy-Item -LiteralPath $WindowsPowerShell -Destination $installer
    $sourceEvidence = New-TestDirectory -Parent $artifact -Name 'source-evidence'
    Write-TestAscii -Path (Join-Path $sourceEvidence 'Rook.tar') -Text 'rook-source'
    Write-TestAscii -Path (Join-Path $sourceEvidence 'Chirp.tar') -Text 'chirp-source'
    Write-TestAscii -Path (Join-Path $stageRook 'rook.txt') -Text 'rook'
    Write-TestAscii -Path (Join-Path $stageChirp 'chirp.txt') -Text 'chirp'
    $stagedFfmpeg = New-TestDirectory -Parent (New-TestDirectory -Parent $stageRook -Name 'third_party') -Name 'ffmpeg'
    Write-TestAscii -Path (Join-Path $stagedFfmpeg 'ffmpeg.exe') -Text 'installed-ffmpeg'
    $externalRoot = New-TestDirectory -Parent $Root -Name 'external-inputs'
    foreach ($name in @('header.hxx','import.lib','runtime.dll','rhino.dll','revit.dll','redist.dll','ffmpeg.exe','ffmpeg-manifest.json')) {
        Write-TestAscii -Path (Join-Path $externalRoot $name) -Text $name
    }
    $toolIdentity = New-FakeFileIdentity -Path $WindowsPowerShell
    $gitPath = (Get-Command git.exe -ErrorAction Stop).Source
    $gitIdentity = New-FakeFileIdentity -Path $gitPath
    $tools = [ordered]@{}
    foreach ($name in @('GitPath','PowerShellPath','CmdPath','Msys2Bash','VcvarsallPath','MsbuildPath','DotnetPath','IsccPath')) { $tools[$name] = $toolIdentity }
    $tools.GitPath = $gitIdentity
    $stagedInstaller = Join-Path $installerSourceDir 'RookSetup.iss'
    foreach ($repo in @($stageRook,$stageChirp)) {
        & $gitPath -C $repo init -q
        if ($LASTEXITCODE -ne 0) { throw "git init failed for $repo" }
        & $gitPath -C $repo config user.email 'containment-test@example.invalid'
        & $gitPath -C $repo config user.name 'Containment Test'
        & $gitPath -C $repo add --all
        & $gitPath -C $repo commit -q -m fixture
        if ($LASTEXITCODE -ne 0) { throw "git commit failed for $repo" }
    }
    $rookBranch = (& $gitPath -C $stageRook branch --show-current).Trim()
    $chirpBranch = (& $gitPath -C $stageChirp branch --show-current).Trim()
    $rookSha = (& $gitPath -C $stageRook rev-parse HEAD).Trim()
    $chirpSha = (& $gitPath -C $stageChirp rev-parse HEAD).Trim()
    $rookSourceProjection = New-TestProjection $stageRook @(
        'installer/RookSetup.iss',
        'installer/runtime/python-wheelhouse/fixture.whl',
        'installer/runtime/python/cpython-3.11.9/python.exe',
        'rook.txt',
        'third_party/ffmpeg/ffmpeg.exe'
    )
    $chirpSourceProjection = New-TestProjection $stageChirp @('chirp.txt')
    $candidate = [ordered]@{
        schema_version = 1
        non_publishable = $true
        product_version = '0.0.fake'
        build = [ordered]@{ started_utc = '2026-07-17T00:00:00.0000000Z'; completed_utc = '2026-07-17T00:00:01.0000000Z' }
        sources = [ordered]@{
            rook = [ordered]@{ root=$stageRook; branch=$rookBranch; sha=$rookSha; clean=$true; local_source_clone_path=$stageRook; stage_path=$stageRook; tracked_build_output_paths=@('third_party/ffmpeg/ffmpeg.exe'); source_archive_sha256=(Get-TestSha256 (Join-Path $sourceEvidence 'Rook.tar')); source_tree_digest=$rookSourceProjection.digest }
            chirp = [ordered]@{ root=$stageChirp; branch=$chirpBranch; sha=$chirpSha; clean=$true; local_source_clone_path=$stageChirp; stage_path=$stageChirp; source_archive_sha256=(Get-TestSha256 (Join-Path $sourceEvidence 'Chirp.tar')); source_tree_digest=$chirpSourceProjection.digest }
        }
        tools = $tools
        inputs = [ordered]@{
            python_wheelhouse = [ordered]@{ relative_path='stage/Rook/installer/runtime/python-wheelhouse'; validated_payload=(New-TestProjection -Root $wheelhouse -RelativePaths @('fixture.whl')) }
            native_msvc = [ordered]@{ vcvars_selector='14.44'; vc_tools_version='14.44.35207'; visual_studio_root=$externalRoot; compiler=$toolIdentity; linker=$toolIdentity }
            native_rhino_sdk = [ordered]@{ registry_key='fake'; install_path=$externalRoot; property_sheet=(New-FakeFileIdentity (Join-Path $externalRoot 'rhino.dll')) }
            dotnet = [ordered]@{ version='8.0.fake'; executable=$toolIdentity }
            rhino_managed_references = [ordered]@{ root=$externalRoot; projection=(New-TestProjection $externalRoot @('rhino.dll')) }
            revit_references = [ordered]@{ root=$externalRoot; projection=(New-TestProjection $externalRoot @('revit.dll')) }
            vc_redist = [ordered]@{ root=$externalRoot; projection=(New-TestProjection $externalRoot @('redist.dll')) }
            occt = [ordered]@{ build_root=$externalRoot; runtime_root=$externalRoot; msbuild_property="/p:OcctRoot=$externalRoot"; consumed_header_and_import_libraries=(New-TestProjection $externalRoot @('header.hxx','import.lib')); consumed_runtime_dlls=(New-TestProjection $externalRoot @('runtime.dll')) }
            ffmpeg = [ordered]@{ version='fake'; source_identity=(New-FakeFileIdentity (Join-Path $externalRoot 'ffmpeg.exe')); source_bundle_manifest=(New-FakeFileIdentity (Join-Path $externalRoot 'ffmpeg-manifest.json')); installed_payload=(New-TestProjection $stagedFfmpeg @('ffmpeg.exe')); tracked_build_outputs=(New-TestProjection $stageRook @('third_party/ffmpeg/ffmpeg.exe')) }
        }
        native_environment = [ordered]@{ contract_version=1; input_allowlist=@(); scrub_names=@(); pre_vcvars=[ordered]@{}; captured=[ordered]@{}; import_disable_arguments=@(); msbuild_executable=$WindowsPowerShell; msbuild_arguments=@(); msbuild_occt_root=$externalRoot }
        private_python = [ordered]@{ relative_path='stage/Rook/installer/runtime/python/cpython-3.11.9/python.exe'; version='3.11.9'; sha256=(Get-TestSha256 $privatePython); pth_files=@() }
        managed = [ordered]@{ inert_rhino_plugin_dir=(Join-Path $artifact '_no_rhino_deploy_fake'); rook_arguments=@(); rookbim_arguments=@(); live_plugin=[ordered]@{ path=(Join-Path $Root 'live-plugin'); before_sha256='0'*64; after_sha256='0'*64; projection=@() } }
        installer = [ordered]@{ relative_path='output/Rook-Setup-fake.exe'; sha256=(Get-TestSha256 $installer); source_sha256=(Get-TestSha256 $stagedInstaller); staged_sha256=(Get-TestSha256 $stagedInstaller); source_size=(Get-Item $stagedInstaller).Length; staged_size=(Get-Item $stagedInstaller).Length }
        commands = @()
        inventories = [ordered]@{ source_inventory=[ordered]@{ rook=$rookSourceProjection; chirp=$chirpSourceProjection }; build_inventory=(New-TestProjection (Join-Path $artifact 'stage') @('Chirp/chirp.txt','Rook/installer/RookSetup.iss','Rook/installer/runtime/python-wheelhouse/fixture.whl','Rook/installer/runtime/python/cpython-3.11.9/python.exe','Rook/rook.txt','Rook/third_party/ffmpeg/ffmpeg.exe')); output_inventory=(New-TestProjection $artifact @('output/Rook-Setup-fake.exe','source-evidence/Chirp.tar','source-evidence/Rook.tar','stage/Chirp/chirp.txt','stage/Rook/installer/RookSetup.iss','stage/Rook/installer/runtime/python-wheelhouse/fixture.whl','stage/Rook/installer/runtime/python/cpython-3.11.9/python.exe','stage/Rook/rook.txt','stage/Rook/third_party/ffmpeg/ffmpeg.exe')) }
    }
    $identityPath = Join-Path $artifact 'containment-candidate.json'
    Write-TestUtf8NoBom -Path $identityPath -Text (ConvertTo-TestCanonicalJson -Value $candidate)
    $identityHash = Get-TestSha256 -Path $identityPath
    $sidecarPath = Join-Path $artifact 'containment-candidate.sha256'
    Write-TestAscii -Path $sidecarPath -Text "$identityHash  containment-candidate.json`n"
    return [pscustomobject]@{ Artifact=$artifact; IdentityPath=$identityPath; SidecarPath=$sidecarPath; Installer=$installer; Identity=$candidate; ExternalRoot=$externalRoot }
}

function New-FakeScenarioEvidence {
    param([string]$Directory, [ValidateSet('rhino','grasshopper')][string]$Scenario, [switch]$FailRestoration, [switch]$TelemetryChanged)
    [IO.Directory]::CreateDirectory($Directory) | Out-Null
    $runId = 'a' * 32
    $nonce = 'd' * 32
    $processToken = 'b' * 32
    $scratchPath = Join-Path $Directory "$Scenario-scratch"
    $ownershipPath = Join-Path $Directory '.rook-containment-owner.json'
    Write-TestUtf8NoBom $ownershipPath (ConvertTo-TestCanonicalJson ([ordered]@{process_id=123;run_id=$runId;schema_version=1}))
    $operationDir = New-TestDirectory -Parent $Directory -Name 'operations'
    $challenge = New-AuthorizationRecord -Scenario $Scenario -RunId $runId -Nonce $nonce -ProcessId 123 -ScratchPath $scratchPath
    $hostProjection = if ($Scenario -eq 'rhino') {
        [ordered]@{prior_active_document_runtime_serial=321;prior_path='';prior_modified=$false}
    } else {
        [ordered]@{has_active_canvas=$false;document_id=$null}
    }
    $scratchProjection = if ($Scenario -eq 'rhino') {
        [ordered]@{runtime_serial=321;path=$scratchPath;modified=$false;object_count=0;object_ids=@()}
    } else {
        [ordered]@{
            document_id='fake-document';has_active_canvas=$true
            gate_canvas_token=(Get-TestValueSha256 -Value @(123,$processToken,9878,$true,'fake-document'))
            path=$scratchPath;object_count=0;component_ids=@();wires=@();errors=0;warnings=0
        }
    }
    $sphereId = '11111111-1111-4111-8111-111111111111'
    $pointId = '22222222-2222-4222-8222-222222222222'
    $sphereProjection = [ordered]@{
        id=$sphereId;name="RookContainmentSphere-$runId";type='Brep';center=@(0.0,0.0,0.0);radius=4.0
        bbox=[ordered]@{min=@(-4,-4,-4);max=@(4,4,4)}
        face_count=1;edge_count=1;vertex_count=2;is_solid=$true;is_manifold=$true;area=201.0619;volume=268.0826
    }
    $pointProjection = [ordered]@{id=$pointId;name="RookContainmentPoint-$runId";type='Point';location=@(10,0,0)}
    $ghComponents = @(
        [ordered]@{id='C1';type='NumberSlider';nick="RookContainmentRadius-$runId";pos=@(100,100);is_param=$true;value=[ordered]@{type='slider';val=4;min=1;max=9}},
        [ordered]@{id='C2';type='Component';name='Sphere';componentGuid='dabc854d-f50e-408a-b001-d043c7de151d';pos=@(400,100);inputs=@([ordered]@{idx=0;name='Base'},[ordered]@{idx=1;name='Radius';sources=1});outputs=@([ordered]@{idx=0;name='Sphere';type='Sphere';data=[ordered]@{structure='single';count=1;preview=@('Sphere')}})}
    )
    $ghDiagnostics = [ordered]@{total=2;errors=0;warnings=0;error_ids=$null;warning_ids=$null}
    $ghEditSolve = [ordered]@{solve_scheduled=$true;solver_locked=$false;solver_state_known=$true;verification_deferred=$true}
    $ghSolvedStatus = [ordered]@{
        available=$true;has_active_canvas=$true;has_active_document=$true
        document_id='fake-document';document_path=$scratchPath;object_count=2;ready_for_edit=$true
        solver_enabled=$true;solver_state_known=$true;solution_state='PostProcess'
    }
    $verificationProjection = if ($Scenario -eq 'rhino') {
        [ordered]@{
            document=[ordered]@{path=$scratchPath;object_count=2;modified=$true}
            objects=[ordered]@{sphere=$sphereProjection;point=$pointProjection}
            object_ids=@($pointId,$sphereId)
        }
    } else {
        [ordered]@{
            components=$ghComponents;flows=@('C1.O0>C2.I1');diagnostics=$ghDiagnostics
            solve=[ordered]@{edit=$ghEditSolve;status=$ghSolvedStatus}
        }
    }
    $operationNames = if ($Scenario -eq 'rhino') {
        @(
            'rhino_ping','rhino_execute','rhino_document','rhino_objects',
            'rhino_ping','rhino_execute','rhino_document','rhino_objects',
            'rhino_document_ops','rhino_execute','rhino_document','rhino_objects',
            'rhino_create','rhino_execute','rhino_objects','rhino_geometry','rhino_geometry','rhino_document',
            'rhino_execute','rhino_document','rhino_objects','rhino_delete',
            'rhino_execute','rhino_document','rhino_objects','rhino_document_ops',
            'rhino_execute','rhino_document','rhino_objects'
        )
    } else {
        @(
            'rhino_ping','rhino_document','gh_status','rhino_ping','rhino_document','gh_status',
            'rhino_command','gh_status','gh_document_open','gh_status','gh_snapshot','gh_errors',
            'gh_library','gh_snapshot','gh_edit',
            'gh_snapshot','gh_errors','gh_status','gh_snapshot','gh_errors','gh_status',
            'gh_undo','gh_snapshot','gh_errors','gh_status'
        )
    }
    $operationRecords = New-Object Collections.Generic.List[object]
    $artifactRecords = New-Object Collections.Generic.List[object]
    $artifactRecords.Add([ordered]@{kind='ownership_marker';relative_path='.rook-containment-owner.json';sha256=(Get-TestSha256 $ownershipPath);size=(Get-Item $ownershipPath).Length})
    $executeCount = 0
    $geometryCount = 0
    for ($operationIndex = 1; $operationIndex -le $operationNames.Count; $operationIndex++) {
        $name = [string]$operationNames[$operationIndex - 1]
        $arguments = [ordered]@{}
        if ($name -eq 'rhino_objects') { $arguments = [ordered]@{limit=500;offset=0} }
        elseif ($name -eq 'rhino_document_ops') { $arguments = [ordered]@{action='save';path=$scratchPath} }
        elseif ($name -eq 'rhino_create') { $arguments = [ordered]@{type='SPHERE';center=@(0,0,0);radius=4;name="RookContainmentSphere-$runId"} }
        elseif ($name -eq 'rhino_execute') {
            $executeCount++
            $code = if ($executeCount -eq 4) {
                Get-ContainmentRhinoPointScript -RunId $runId
            } else {
                "import Rhino`nprint('ROOK_DOC_RUNTIME_SERIAL={0}'.format(Rhino.RhinoDoc.ActiveDoc.RuntimeSerialNumber))"
            }
            $arguments = [ordered]@{code=$code}
        }
        elseif ($name -eq 'rhino_geometry') {
            $geometryCount++
            $arguments = [ordered]@{id=$(if($geometryCount -eq 1){$sphereId}else{$pointId})}
        }
        elseif ($name -eq 'rhino_delete') { $arguments = [ordered]@{ids=@($pointId,$sphereId)} }
        elseif ($name -eq 'rhino_command') { $arguments = [ordered]@{command='_Grasshopper';echo=$false} }
        elseif ($name -eq 'gh_document_open') { $arguments = [ordered]@{path=$scratchPath} }
        elseif ($name -eq 'gh_library') { $arguments = [ordered]@{search='Sphere';exact=$true} }
        elseif ($name -eq 'gh_edit') {
            $arguments = [ordered]@{
                epoch=7
                create=@(
                    [ordered]@{temp_id='T1';type='slider';nick="RookContainmentRadius-$runId";min=1;max=9;value=4;pos=@(100,100)},
                    [ordered]@{temp_id='T2';guid='dabc854d-f50e-408a-b001-d043c7de151d';pos=@(400,100)}
                )
                connect=@('T1.O0>T2.I1')
            }
        }
        $resultData = [ordered]@{}
        if ($name -eq 'rhino_ping') { $resultData = [ordered]@{pong=$true} }
        elseif ($name -eq 'rhino_document') {
            if ($Scenario -eq 'grasshopper' -or $operationIndex -in @(3,7)) {
                $resultData = [ordered]@{name='fixture';path='';objectCount=0;modified=$false}
            }
            elseif ($operationIndex -in @(11,28)) {
                $resultData = [ordered]@{name='fixture';path=$scratchPath;objectCount=0;modified=$false}
            }
            elseif ($operationIndex -in @(18,20)) {
                $resultData = [ordered]@{name='fixture';path=$scratchPath;objectCount=2;modified=$true}
            }
            elseif ($operationIndex -eq 24) {
                $resultData = [ordered]@{name='fixture';path=$scratchPath;objectCount=0;modified=$true}
            }
        }
        elseif ($name -eq 'rhino_objects') {
            if ($operationIndex -in @(15,21)) {
                $resultData = [ordered]@{objects=@($sphereProjection,$pointProjection);count=2}
            } else {
                $resultData = [ordered]@{objects=@();count=0}
            }
        }
        elseif ($name -eq 'rhino_document_ops') { $resultData = [ordered]@{saved=$true;path=$scratchPath} }
        elseif ($name -eq 'rhino_create') { $resultData = [ordered]@{id=$sphereId} }
        elseif ($name -eq 'rhino_execute') {
            $resultData = if ($executeCount -eq 4) {
                [ordered]@{output="ROOK_POINT_ID=$pointId`n"}
            } else {
                [ordered]@{output="ROOK_DOC_RUNTIME_SERIAL=321`n"}
            }
        }
        elseif ($name -eq 'rhino_geometry') {
            $resultData = if ($geometryCount -eq 1) {
                [ordered]@{
                    id=$sphereId;name=$sphereProjection.name;type='Brep';bbox=$sphereProjection.bbox
                    geometry=[ordered]@{type='Brep';faceCount=1;edgeCount=1;vertexCount=2;isSolid=$true;isManifold=$true;area=201.0619;volume=268.0826}
                }
            } else {
                [ordered]@{id=$pointId;name=$pointProjection.name;type='Point';bbox=[ordered]@{min=@(10,0,0);max=@(10,0,0)};geometry=[ordered]@{type='Point';location=@(10,0,0)}}
            }
        }
        elseif ($name -eq 'rhino_delete') { $resultData = [ordered]@{deleted=2} }
        elseif ($name -eq 'rhino_command') { $resultData = [ordered]@{executed=$true} }
        elseif ($name -eq 'gh_status') {
            if ($operationIndex -in @(3,6)) {
                $resultData = [ordered]@{
                    available=$false;has_active_canvas=$false;has_active_document=$false
                    document_id=$null;document_path='';object_count=0;ready_for_edit=$false
                    solver_enabled=$null;solver_state_known=$true;solution_state=$null
                }
            }
            elseif ($operationIndex -eq 8) {
                $resultData = [ordered]@{
                    available=$true;has_active_canvas=$true;has_active_document=$true
                    document_id='bootstrap-document';document_path='';object_count=0;ready_for_edit=$true
                    solver_enabled=$true;solver_state_known=$true;solution_state='PostProcess'
                }
            }
            elseif ($operationIndex -in @(18,21)) { $resultData = $ghSolvedStatus }
            else {
                $resultData = [ordered]@{
                    available=$true;has_active_canvas=$true;has_active_document=$true
                    document_id='fake-document';document_path=$scratchPath;object_count=0;ready_for_edit=$true
                    solver_enabled=$true;solver_state_known=$true;solution_state='PostProcess'
                }
            }
        }
        elseif ($name -eq 'gh_document_open') { $resultData = [ordered]@{opened=$true;path=$scratchPath;fileName='fixture.ghx';objectCount=0} }
        elseif ($name -eq 'gh_snapshot') {
            if ($operationIndex -in @(16,19)) {
                $resultData = [ordered]@{epoch=8;components=$ghComponents;flows=@('C1.O0>C2.I1');diagnostics=$ghDiagnostics}
            } else {
                $snapshotEpoch = if ($operationIndex -eq 23) { 9 } else { 7 }
                $resultData = [ordered]@{epoch=$snapshotEpoch;components=@();flows=@();diagnostics=[ordered]@{total=0;errors=0;warnings=0}}
            }
        }
        elseif ($name -eq 'gh_errors') {
            $componentCount = if ($operationIndex -in @(17,20)) { 2 } else { 0 }
            $resultData = [ordered]@{totalComponents=$componentCount;errorCount=0;warningCount=0;errors=@();warnings=@()}
        }
        elseif ($name -eq 'gh_library') { $resultData = [ordered]@{count=1;components=@([ordered]@{name='Sphere';guid='dabc854d-f50e-408a-b001-d043c7de151d'})} }
        elseif ($name -eq 'gh_edit') {
            $resultData = [ordered]@{
                epoch=8;components=$ghComponents;flows=@('C1.O0>C2.I1');diagnostics=$ghDiagnostics
                edit_summary=[ordered]@{created=2;connected=1;solve_scheduled=$true;solver_locked=$false;solver_state_known=$true;verification_deferred=$true;errors=$null}
            }
        }
        elseif ($name -eq 'gh_undo') { $resultData = [ordered]@{message='Undo successful';epoch=9;snapshot=[ordered]@{components=@();flows=@()}} }
        $stem = '{0:D3}-{1}' -f $operationIndex,$name
        $argumentsRelative = "operations/$stem-arguments.json"
        $resultRelative = "operations/$stem-result.json"
        $argumentsPath = Join-Path $Directory $argumentsRelative
        $resultPath = Join-Path $Directory $resultRelative
        Write-TestUtf8NoBom $argumentsPath (ConvertTo-TestCanonicalJson $arguments)
        Write-TestUtf8NoBom $resultPath (ConvertTo-TestCanonicalJson ([ordered]@{data=$resultData;success=$true}))
        $operationRecords.Add([ordered]@{
            index=$operationIndex;name=$name
            arguments_path=$argumentsRelative;arguments_sha256=(Get-TestSha256 $argumentsPath)
            result_path=$resultRelative;result_sha256=(Get-TestSha256 $resultPath);success=$true
        })
        $artifactRecords.Add([ordered]@{kind='operation_arguments';relative_path=$argumentsRelative;sha256=(Get-TestSha256 $argumentsPath);size=(Get-Item $argumentsPath).Length})
        $artifactRecords.Add([ordered]@{kind='operation_result';relative_path=$resultRelative;sha256=(Get-TestSha256 $resultPath);size=(Get-Item $resultPath).Length})
    }
    [object[]]$telemetryEvents = @()
    [int]$telemetryDelta = 0
    if ($TelemetryChanged) {
        $telemetryEvents = @([ordered]@{tool='gh_execute_intent'})
        $telemetryDelta = 1
    }
    $preflightProjection = if ($Scenario -eq 'rhino') {
        [ordered]@{runtime_serial=321;path='';object_count=0;modified=$false;object_ids=@()}
    } else {
        [ordered]@{
            rhino=[ordered]@{path='';object_count=0;modified=$false}
            grasshopper=[ordered]@{
                available=$false;has_active_canvas=$false;has_active_document=$false
                document_id=$null;document_path='';object_count=0;ready_for_edit=$false
                solver_enabled=$null;solver_state_known=$true;solution_state=$null
            }
        }
    }
    $preflightHash = Get-TestValueSha256 $preflightProjection
    $record = [ordered]@{
        schema_version=1; scenario=$Scenario; success=$true; failure_label=$null; run_id=$runId
        started_at='2026-07-17T00:00:00.000000Z'; ended_at='2026-07-17T00:00:01.000000Z'
        runtime=[ordered]@{ python_executable=$WindowsPowerShell; installed_root=$Directory; cwd=$Directory; sys_path=@($Directory); rook_origins=[ordered]@{ rook=(Join-Path $Directory 'rook.py') } }
        target=[ordered]@{ process_id=123; port=9878; process_start_token=$processToken; discovery_record_sha256=('c'*64); scratch_path=$scratchPath; ownership_certain=$true }
        authorization=[ordered]@{ nonce=$nonce; challenge_sha256=(Get-TestValueSha256 $challenge); authorized_at='2026-07-17T00:00:00.500000Z'; preflight_sha256=$preflightHash; pre_mutation_sha256=$preflightHash; state_unchanged=$true }
        pre_state=[ordered]@{ host_projection=$hostProjection; host_sha256=(Get-TestValueSha256 $hostProjection); scratch_projection=$scratchProjection; scratch_sha256=(Get-TestValueSha256 $scratchProjection) }
        operations=@($operationRecords.ToArray())
        verification=[ordered]@{ passed=$true; projection=$verificationProjection; projection_sha256=(Get-TestValueSha256 $verificationProjection); errors=@(); warnings=@() }
        restoration=[ordered]@{ ownership_certain=$true; attempted=$true; verified=(-not $FailRestoration); in_process_projection_matches_declared=$true; prior_identity_or_absence_restored=$true; scratch_disposed=$true; discovery_removed=$true }
        telemetry=[ordered]@{ process_id=123; process_start_token=$processToken; before_sha256=('4'*64); after_sha256=('5'*64); delta_count=$telemetryDelta; events_added=$telemetryEvents }
        artifacts=@($artifactRecords.ToArray())
        diagnostics=@()
    }
    $path = Join-Path $Directory "$Scenario-scenario.json"
    Write-TestUtf8NoBom $path (ConvertTo-TestCanonicalJson $record)
    $hash = Get-TestSha256 $path
    $sidecar = Join-Path $Directory "$Scenario-scenario.sha256"
    Write-TestAscii $sidecar "$hash`n"
    return [pscustomobject]@{ Path=$path; Sidecar=$sidecar; Hash=$hash; Record=$record }
}

function Set-FakeScenarioOperationResult {
    param(
        [Parameter(Mandatory = $true)][object]$Fixture,
        [Parameter(Mandatory = $true)][string]$Name,
        [ValidateRange(1,100)][int]$Occurrence = 1,
        [Parameter(Mandatory = $true)][object]$Data
    )
    $matches = @($Fixture.Record.operations | Where-Object { [string]$_.name -ceq $Name })
    if ($matches.Count -lt $Occurrence) { throw "Fake scenario has no $Name occurrence $Occurrence" }
    $operation = $matches[$Occurrence - 1]
    $root = Split-Path -Parent $Fixture.Path
    $resultPath = Join-Path $root ([string]$operation.result_path)
    Write-TestUtf8NoBom $resultPath (ConvertTo-TestCanonicalJson ([ordered]@{data=$Data;success=$true}))
    $resultHash = Get-TestSha256 $resultPath
    $operation.result_sha256 = $resultHash
    $artifact = @($Fixture.Record.artifacts | Where-Object { [string]$_.relative_path -ceq [string]$operation.result_path })
    Assert-Equal $artifact.Count 1 'Fake scenario result artifact lookup drifted.'
    $artifact[0].sha256 = $resultHash
    $artifact[0].size = (Get-Item -LiteralPath $resultPath).Length
    Write-TestUtf8NoBom $Fixture.Path (ConvertTo-TestCanonicalJson $Fixture.Record)
    $fixtureHash = Get-TestSha256 $Fixture.Path
    Write-TestAscii $Fixture.Sidecar "$fixtureHash`n"
    $Fixture.Hash = $fixtureHash
}

function Save-FakeScenarioEvidence {
    param([Parameter(Mandatory = $true)][object]$Fixture)

    Write-TestUtf8NoBom $Fixture.Path (ConvertTo-TestCanonicalJson $Fixture.Record)
    $fixtureHash = Get-TestSha256 $Fixture.Path
    Write-TestAscii $Fixture.Sidecar "$fixtureHash`n"
    $Fixture.Hash = $fixtureHash
}

function New-AuthorizationRecord {
    param(
        [ValidateSet('rhino','grasshopper')][string]$Scenario,
        [string]$RunId = ('1' * 32),
        [string]$Nonce = ('2' * 32),
        [int]$ProcessId = 123,
        [string]$ScratchPath = "C:\Temp\$Scenario scratch"
    )
    $run = $RunId
    $nonce = $Nonce
    $target = [ordered]@{label=$(if($Scenario -eq 'rhino'){'Rook containment Rhino scratch document'}else{'Rook containment Grasshopper scratch definition'});process_id=$ProcessId;port=9878;scratch_path=$ScratchPath}
    $descriptions = if ($Scenario -eq 'rhino') {
        [ordered]@{
            mutation='Save the fresh owned Rhino document, create one radius-4 sphere and one marked point using admitted typed and scripted tools.'
            verification='Verify exact object identities, names, types, coordinates, sphere radius and bounds, and clean document state.'
            restoration='Delete only the two gate-owned objects, save the empty scratch document, close the owned process gracefully, and remove the scratch file and discovery record.'
        }
    } else {
        [ordered]@{
            mutation='Bootstrap Grasshopper in the fresh owned Rhino process, open the packaged empty scratch definition, and create one configured radius slider wired to one built-in Sphere.'
            verification='Verify exact component identities, slider settings, wire topology, solved sphere output, and zero Grasshopper errors or warnings.'
            restoration='Undo only the gate-owned edit to the declared empty projection, close the owned process, and remove the scratch definition and discovery record.'
        }
    }
    $targetHash = Get-TestValueSha256 $target
    $mutationHash = Get-TestValueSha256 $descriptions.mutation
    $verifyHash = Get-TestValueSha256 $descriptions.verification
    $restoreHash = Get-TestValueSha256 $descriptions.restoration
    $response = "AUTHORIZE scenario=$Scenario run=$run nonce=$nonce target=$targetHash mutation=$mutationHash verify=$verifyHash restore=$restoreHash"
    return [ordered]@{
        type='authorization_required'; schema_version=1; scenario=$Scenario; run_id=$run; nonce=$nonce
        target=$target
        target_sha256=$targetHash; mutation=$descriptions.mutation; mutation_sha256=$mutationHash
        verification=$descriptions.verification; verification_sha256=$verifyHash
        restoration=$descriptions.restoration; restoration_sha256=$restoreHash; required_response=$response
    }
}

function New-FakeTask7ProcessEvidence {
    param(
        [string]$PythonPath,
        [string]$InstallRoot,
        [string]$DataRoot,
        [string]$DspyCache,
        [AllowNull()][string]$Profile,
        [int]$ProcessId = 101,
        [string]$ProcessToken = ('1'*32)
    )
    $environment = Get-ContainmentExpectedProcessEnvironment -InstallRoot $InstallRoot -DataRoot $DataRoot -DspyCache $DspyCache -ChirpHome $null -Profile $Profile
    return [ordered]@{
        executable=$PythonPath;installed_root=$InstallRoot;cwd=$InstallRoot
        environment=$environment;sys_path=@($InstallRoot)
        rook_origins=[ordered]@{
            rook=(Join-Path $InstallRoot 'rook\__init__.py')
            'rook.containment_acceptance'=(Join-Path $InstallRoot 'rook\containment_acceptance.py')
            'rook.server'=(Join-Path $InstallRoot 'rook\server.py')
        }
        process_id=$ProcessId;process_start_token=$ProcessToken
    }
}

function New-FakeTask7Models {
    return [ordered]@{
        rook_agent=[ordered]@{count=2;names=@('rhino_ping','gh_status')}
        rook_chat=[ordered]@{count=2;names=@('rhino_ping','gh_status')}
    }
}

function New-FakeTask7Denial {
    param([string]$Tool)
    $lifecycle = $script:ContainmentLifecycle[$Tool]
    return [ordered]@{
        success=$false
        data=[ordered]@{
            code='legacy_semantic_tool_contained';tool=$Tool;disposition=$lifecycle.disposition
            retryable=$false;verified=$false;recovery=$lifecycle.recovery
        }
    }
}

function New-FakeTask7Stages {
    param([int]$FormatResult)
    $stages = [ordered]@{}
    foreach ($name in $script:ContainmentStageNames) {
        $stages[$name] = if ($name -eq 'recording_attempt') { 1 } elseif ($name -eq 'format_result') { $FormatResult } else { 0 }
    }
    return $stages
}

function New-FakeTask7TelemetryPair {
    param([int]$ProcessId,[string]$ProcessToken,[string]$Tool,[string]$Origin)
    $event = [ordered]@{tool=$Tool;disposition=$script:ContainmentLifecycle[$Tool].disposition;origin=$Origin;timestamp='2026-07-17T00:00:00.000000Z'}
    return [ordered]@{
        before=[ordered]@{process_id=$ProcessId;process_start_token=$ProcessToken;events=@()}
        after=[ordered]@{process_id=$ProcessId;process_start_token=$ProcessToken;events=@($event)}
    }
}

function Write-FakeTask7JsonLf {
    param([string]$Path,[AllowNull()][object]$Value)
    Write-TestUtf8NoBom -Path $Path -Text ((ConvertTo-TestCanonicalJson $Value) + "`n")
}

function Test-Task7ArtifactValidators {
    param([string]$Root)
    $installRoot = New-TestDirectory $Root 'installed-root'
    $dataRoot = New-TestDirectory $Root 'data-root'
    $dspy = New-TestDirectory $dataRoot 'dspy-cache'
    $python = $WindowsPowerShell
    $runId = '2' * 32
    $childId = 202
    $childToken = '3' * 32
    $patchpoints = [ordered]@{}
    foreach ($name in $script:ContainmentPatchpointNames) { $patchpoints[$name]=$true }
    $wrapperFactory = [ordered]@{sync_scoped_trip=$true;sync_unscoped_passthrough=$true;async_scoped_trip=$true;async_unscoped_passthrough=$true}

    $transportRoot = New-TestDirectory $Root 'transport-full'
    $transportProbes = New-Object Collections.Generic.List[object]
    for ($index=0; $index -lt 12; $index++) {
        $tool = [string]$script:ContainmentContainedNames[$index % 6]
        $adapter = if($index -lt 6){'direct'}else{'progressive'}
        $origin = if($index -lt 6){'public_mcp'}else{'progressive_meta'}
        $telemetry = New-FakeTask7TelemetryPair -ProcessId $childId -ProcessToken $childToken -Tool $tool -Origin $origin
        $spy = [ordered]@{
            schema_version=1;run_id=$runId;process_id=$childId;process_start_token=$childToken
            self_test=[ordered]@{patchpoints=$patchpoints;wrapper_factory=$wrapperFactory}
            probe=[ordered]@{index=$index;adapter=$adapter;tool=$tool;origin=$origin;telemetry_before=$telemetry.before;telemetry_after=$telemetry.after;stages=(New-FakeTask7Stages 1)}
        }
        $transportProbes.Add([ordered]@{
            index=$index;adapter=$adapter;tool=$tool;origin=$origin
            result=(New-FakeTask7Denial $tool);transport=[ordered]@{content_count=1;content_types=@('text');is_error=$false};spy=$spy
        })
    }
    $finalSpy = $transportProbes[11].spy
    $finalSpyPath = Join-Path $transportRoot 'final-spy.json'
    Write-FakeTask7JsonLf $finalSpyPath $finalSpy
    $transport = [ordered]@{
        schema_version=1;command='transport-profile';profile='full';run_id=$runId
        process=(New-FakeTask7ProcessEvidence -PythonPath $python -InstallRoot $installRoot -DataRoot $dataRoot -DspyCache $dspy -Profile 'full')
        child_environment=(Get-ContainmentExpectedProcessEnvironment -InstallRoot $installRoot -DataRoot $dataRoot -DspyCache $dspy -ChirpHome $null -Profile 'full')
        catalog=[ordered]@{count=2;tools=@([ordered]@{name='rhino_ping'},[ordered]@{name='gh_status'})}
        model_projections=(New-FakeTask7Models);probes=@($transportProbes.ToArray())
        child_process_id=$childId;child_process_start_token=$childToken
        final_spy_path=$finalSpyPath;final_spy_sha256=(Get-TestSha256 $finalSpyPath);final_spy=$finalSpy
    }
    $transportPath = Join-Path $transportRoot 'transport-full.json'
    Write-FakeTask7JsonLf $transportPath $transport
    $validatedTransport = Read-AndValidateContainmentTransportArtifact -Path $transportPath -ArtifactRoot $transportRoot -Profile full -ExpectedCount 2 -InstalledPython $python -InstallRoot $installRoot -DataRoot $dataRoot -DspyCache $dspy -ChirpHome $null -ForbiddenSourceRoots @()
    Assert-Equal @($validatedTransport.records).Count 12 'Task 7 transport validator did not retain all probes.'
    $transportTypeDrift = [IO.File]::ReadAllText($transportPath) | ConvertFrom-Json
    $transportTypeDrift.probes[0].spy.schema_version = '1'
    $transportTypeDriftPath = Join-Path $transportRoot 'transport-full-type-drift.json'
    Write-FakeTask7JsonLf $transportTypeDriftPath $transportTypeDrift
    Assert-ThrowsLike {
        Read-AndValidateContainmentTransportArtifact -Path $transportTypeDriftPath -ArtifactRoot $transportRoot -Profile full -ExpectedCount 2 -InstalledPython $python -InstallRoot $installRoot -DataRoot $dataRoot -DspyCache $dspy -ChirpHome $null -ForbiddenSourceRoots @()
    } 'type|identity|schema' 'Task 7 transport validator accepted a string-coercible spy schema version.'

    $discoveryRoot = New-TestDirectory $Root 'discovery-default'
    $emptyTelemetry = [ordered]@{process_id=101;process_start_token=('1'*32);events=@()}
    $discovery = [ordered]@{
        schema_version=1;command='discovery-default'
        process=(New-FakeTask7ProcessEvidence -PythonPath $python -InstallRoot $installRoot -DataRoot $dataRoot -DspyCache $dspy -Profile $null)
        profile_env_present=$false;interactive_env_present=$false
        catalog=[ordered]@{count=2;tools=@([ordered]@{name='rhino_ping'},[ordered]@{name='gh_status'})}
        telemetry_before=$emptyTelemetry;telemetry_after=$emptyTelemetry;model_projections=(New-FakeTask7Models)
    }
    $discoveryPath = Join-Path $discoveryRoot 'discovery-default.json'
    Write-FakeTask7JsonLf $discoveryPath $discovery
    $validatedDiscovery = Read-AndValidateContainmentDiscoveryArtifact -Path $discoveryPath -Command discovery-default -ExpectedCount 2 -InstalledPython $python -InstallRoot $installRoot -DataRoot $dataRoot -DspyCache $dspy -ChirpHome $null -ForbiddenSourceRoots @()
    Assert-Equal $validatedDiscovery.catalog.count 2 'Task 7 discovery validator rejected valid source-free evidence.'
    $discoveryTypeDrift = [IO.File]::ReadAllText($discoveryPath) | ConvertFrom-Json
    $discoveryTypeDrift.profile_env_present = ''
    $discoveryTypeDriftPath = Join-Path $discoveryRoot 'discovery-default-type-drift.json'
    Write-FakeTask7JsonLf $discoveryTypeDriftPath $discoveryTypeDrift
    Assert-ThrowsLike {
        Read-AndValidateContainmentDiscoveryArtifact -Path $discoveryTypeDriftPath -Command discovery-default -ExpectedCount 2 -InstalledPython $python -InstallRoot $installRoot -DataRoot $dataRoot -DspyCache $dspy -ChirpHome $null -ForbiddenSourceRoots @()
    } 'type|identity|environment' 'Task 7 discovery validator accepted a string-coercible environment-presence boolean.'

    $internalRoot = New-TestDirectory $Root 'internal-matrix'
    $pairs = @(Get-ContainmentExpectedInternalPairs)
    $internalProbes = New-Object Collections.Generic.List[object]
    for ($index=0; $index -lt $pairs.Count; $index++) {
        $pair = $pairs[$index]
        $telemetry = New-FakeTask7TelemetryPair -ProcessId 101 -ProcessToken ('1'*32) -Tool ([string]$pair.tool) -Origin ([string]$pair.origin)
        $modelCalls = if(@('RookAgent._run_loop','ChatRunner.run_turn') -ccontains [string]$pair.seam){2}else{0}
        $internalProbes.Add([ordered]@{
            index=$index;seam=$pair.seam;adapter=$pair.adapter;tool=$pair.tool;origin=$pair.origin
            result=(New-FakeTask7Denial ([string]$pair.tool));telemetry_before=$telemetry.before;telemetry_after=$telemetry.after
            stages=(New-FakeTask7Stages 0);primary_model_calls=$modelCalls
        })
    }
    $internal = [ordered]@{
        schema_version=1;command='internal-matrix'
        process=(New-FakeTask7ProcessEvidence -PythonPath $python -InstallRoot $installRoot -DataRoot $dataRoot -DspyCache $dspy -Profile $null)
        expected_pairs=$pairs;probes=@($internalProbes.ToArray());model_projections=(New-FakeTask7Models)
    }
    $internalPath = Join-Path $internalRoot 'internal-matrix.json'
    Write-FakeTask7JsonLf $internalPath $internal
    $validatedInternal = Read-AndValidateContainmentInternalArtifact -Path $internalPath -InstalledPython $python -InstallRoot $installRoot -DataRoot $dataRoot -DspyCache $dspy -ChirpHome $null -ForbiddenSourceRoots @()
    Assert-Equal @($validatedInternal.records).Count 164 'Task 7 internal validator did not retain all probes.'
    $internalTypeDrift = [IO.File]::ReadAllText($internalPath) | ConvertFrom-Json
    $internalTypeDrift.probes[0].index = '0'
    $internalTypeDriftPath = Join-Path $internalRoot 'internal-matrix-type-drift.json'
    Write-FakeTask7JsonLf $internalTypeDriftPath $internalTypeDrift
    Assert-ThrowsLike {
        Read-AndValidateContainmentInternalArtifact -Path $internalTypeDriftPath -InstalledPython $python -InstallRoot $installRoot -DataRoot $dataRoot -DspyCache $dspy -ChirpHome $null -ForbiddenSourceRoots @()
    } 'type|order|identity|index' 'Task 7 internal validator accepted a string-coercible probe index.'
    $internal.probes[0].tool = 'tampered_tool'
    $tamperedPath = Join-Path $internalRoot 'internal-matrix-tampered.json'
    Write-FakeTask7JsonLf $tamperedPath $internal
    Assert-ThrowsLike {
        Read-AndValidateContainmentInternalArtifact -Path $tamperedPath -InstalledPython $python -InstallRoot $installRoot -DataRoot $dataRoot -DspyCache $dspy -ChirpHome $null -ForbiddenSourceRoots @()
    } 'order|identity|tool' 'Task 7 internal validator accepted a tampered pair.'
}

function Test-StaticContract {
    $source = Get-Content -LiteralPath $ValidatorPath -Raw
    [Management.Automation.Language.Token[]]$tokens = $null
    [Management.Automation.Language.ParseError[]]$errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile($ValidatorPath, [ref]$tokens, [ref]$errors)
    Assert-Equal $errors.Count 0 'Validator has PowerShell parse errors.'
    $lines = @(Get-Content -LiteralPath $ValidatorPath)
    $paramEnd = 0
    if ($lines[0] -match '^param\(') {
        for ($index=0; $index -lt $lines.Count; $index++) { if ($lines[$index] -eq ')') { $paramEnd=$index; break } }
    }
    $executables = @($lines[($paramEnd+1)..($lines.Count-1)] | Where-Object { $_.Trim() -and -not $_.Trim().StartsWith('#') })
    Assert-Equal $executables[0].Trim() 'Set-StrictMode -Version Latest' 'Validator first executable line drifted.'
    Assert-Equal $executables[1].Trim() '$ErrorActionPreference = ''Stop''' 'Validator second executable line drifted.'
    foreach ($forbidden in @('Start-Process','ArgumentList','Invoke-Expression','-Environment')) { Assert-False $source.Contains($forbidden) "Validator uses forbidden process API: $forbidden" }
    Assert-False $source.Contains('WaitForExit(60000)') 'Live-gate restoration uses a secondary fixed timeout instead of the original overall deadline.'
    foreach ($parameter in @('ArtifactDirectory','CandidateIdentityPath','CandidateSidecarPath','EvidenceDirectory','RhinoExe','VerifyEvidenceOnly')) { Assert-Contains $source $parameter "Validator parameter is missing." }
    foreach ($required in @('ConvertTo-ProcessArgument','BeginOutputReadLine','PYTHONNOUSERSITE','authorization_required','containment-failure.json','containment-acceptance.json','containment-hold.json')) { Assert-Contains $source $required "Validator required contract is missing." }
}

function Test-CreateNewPublicationFailureCleanup {
    param([string]$Root)

    $savedFactory = (Get-Item -LiteralPath Function:\New-ContainmentCreateNewStream).ScriptBlock
    $savedIdentityRemover = (Get-Item -LiteralPath Function:\Remove-ContainmentOwnedFileByIdentity).ScriptBlock
    $savedEvidenceDirectoryCreator = (Get-Item -LiteralPath Function:\New-ContainmentEvidenceDirectoryExclusive).ScriptBlock
    $savedClaimStagingPathFactory = (Get-Item -LiteralPath Function:\New-ContainmentClaimStagingPath).ScriptBlock
    $payload = [Text.Encoding]::ASCII.GetBytes('publisher-payload')
    try {
        foreach ($stage in @('write','flush','dispose')) {
            $path = Join-Path $Root "low-level-$stage.bin"
            $faultPath = $path
            $faultStage = $stage
            Set-Item Function:\New-ContainmentCreateNewStream -Value ({
                param([string]$Path)
                if ([string]::Equals([IO.Path]::GetFullPath($Path),[IO.Path]::GetFullPath($faultPath),[StringComparison]::OrdinalIgnoreCase)) {
                    return New-TestFaultingCreateNewStream -Path $Path -FaultStage $faultStage
                }
                return & $savedFactory -Path $Path
            }.GetNewClosure())
            Assert-ThrowsLike {
                Write-ContainmentCreateNewBytes -Path $path -Bytes $payload
            } 'injected create-new' "Low-level CreateNew $stage fault did not propagate."
            Assert-False (Test-Path -LiteralPath $path) "Low-level CreateNew $stage fault stranded its owned destination."
        }

        $foreignPath = Join-Path $Root 'foreign-low-level.bin'
        Write-TestAscii $foreignPath 'foreign-owned-low-level'
        Assert-ThrowsLike {
            Write-ContainmentCreateNewBytes -Path $foreignPath -Bytes $payload
        } 'exist|used|access|create' 'Low-level CreateNew accepted a foreign pre-existing path.'
        Assert-Equal ([IO.File]::ReadAllText($foreignPath)) 'foreign-owned-low-level' 'Low-level CreateNew changed or removed a foreign pre-existing path.'

        foreach ($stage in @('write','flush','dispose')) {
            foreach ($member in @('json','sidecar')) {
                $pairRoot = New-TestDirectory $Root "pair-$member-$stage"
                $jsonPath = Join-Path $pairRoot 'final.json'
                $sidecarPath = Join-Path $pairRoot 'final.sha256'
                $faultPath = if ($member -ceq 'json') { $jsonPath } else { $sidecarPath }
                $faultStage = $stage
                Set-Item Function:\New-ContainmentCreateNewStream -Value ({
                    param([string]$Path)
                    if ([string]::Equals([IO.Path]::GetFullPath($Path),[IO.Path]::GetFullPath($faultPath),[StringComparison]::OrdinalIgnoreCase)) {
                        return New-TestFaultingCreateNewStream -Path $Path -FaultStage $faultStage
                    }
                    return & $savedFactory -Path $Path
                }.GetNewClosure())
                Assert-ThrowsLike {
                    Write-CanonicalJsonPair -Path $jsonPath -SidecarPath $sidecarPath -Value ([ordered]@{schema_version=1;success=$true})
                } 'injected create-new' "Final pair $member $stage fault did not propagate."
                Assert-False (Test-Path -LiteralPath $jsonPath) "Final pair $member $stage fault stranded JSON."
                Assert-False (Test-Path -LiteralPath $sidecarPath) "Final pair $member $stage fault stranded sidecar."
            }
        }

        $foreignPairRoot = New-TestDirectory $Root 'foreign-pair'
        $foreignJson = Join-Path $foreignPairRoot 'final.json'
        $foreignSidecar = Join-Path $foreignPairRoot 'final.sha256'
        Write-TestAscii $foreignJson 'foreign-json'
        Write-TestAscii $foreignSidecar 'foreign-sidecar'
        Assert-ThrowsLike {
            Write-CanonicalJsonPair -Path $foreignJson -SidecarPath $foreignSidecar -Value ([ordered]@{success=$true})
        } 'already exists' 'Final pair accepted foreign pre-existing members.'
        Assert-Equal ([IO.File]::ReadAllText($foreignJson)) 'foreign-json' 'Final pair changed or removed foreign JSON.'
        Assert-Equal ([IO.File]::ReadAllText($foreignSidecar)) 'foreign-sidecar' 'Final pair changed or removed foreign sidecar.'

        $cleanupFaultRoot = New-TestDirectory $Root 'pair-cleanup-fault'
        $cleanupFaultJson = Join-Path $cleanupFaultRoot 'final.json'
        $cleanupFaultSidecar = Join-Path $cleanupFaultRoot 'final.sha256'
        $faultPath = $cleanupFaultSidecar
        $faultStage = 'write'
        Set-Item Function:\New-ContainmentCreateNewStream -Value ({
            param([string]$Path)
            if ([string]::Equals([IO.Path]::GetFullPath($Path),[IO.Path]::GetFullPath($faultPath),[StringComparison]::OrdinalIgnoreCase)) {
                return New-TestFaultingCreateNewStream -Path $Path -FaultStage $faultStage
            }
            return & $savedFactory -Path $Path
        }.GetNewClosure())
        $removeFaultPath = $cleanupFaultJson
        Set-Item Function:\Remove-ContainmentOwnedFileByIdentity -Value ({
            param([object]$Ownership)
            if ([string]::Equals([IO.Path]::GetFullPath([string]$Ownership.Path),[IO.Path]::GetFullPath($removeFaultPath),[StringComparison]::OrdinalIgnoreCase)) {
                throw [IO.IOException]::new('injected final-pair rollback deletion failure')
            }
            return & $savedIdentityRemover -Ownership $Ownership
        }.GetNewClosure())
        try {
            Assert-ThrowsLike {
                Write-CanonicalJsonPair -Path $cleanupFaultJson -SidecarPath $cleanupFaultSidecar -Value ([ordered]@{success=$true})
            } 'cleanup.*incomplete|cleanup.*failed|rollback deletion failure' 'Final-pair rollback deletion failure was hidden behind its publication error.'
            Assert-True (Test-Path -LiteralPath $cleanupFaultJson -PathType Leaf) 'Final-pair rollback deletion fault fixture did not retain the JSON member it refused to remove.'
            Assert-False (Test-Path -LiteralPath $cleanupFaultSidecar) 'Final-pair rollback deletion fault stranded the failed sidecar publication.'
        }
        finally {
            Set-Item Function:\Remove-ContainmentOwnedFileByIdentity -Value $savedIdentityRemover
            if (Test-Path -LiteralPath $cleanupFaultJson -PathType Leaf) {
                Remove-Item -LiteralPath $cleanupFaultJson -Force -ErrorAction Stop
            }
        }

        $foreignStaging = New-TestDirectory $Root '.containment-claim-staging-foreign'
        $foreignStagingSentinel = Join-Path $foreignStaging 'foreign-staging-sentinel.txt'
        Write-TestAscii $foreignStagingSentinel 'foreign-staging-owner'
        $retryStaging = Join-Path $Root '.containment-claim-staging-retry'
        $stagingRetryClaim = Join-Path $Root 'staging-retry-claim'
        $stagingRetryMarker = Join-Path $stagingRetryClaim '.containment-run-owner.json'
        $stagingPathState = [pscustomobject]@{ Count = 0 }
        Set-Item Function:\New-ContainmentClaimStagingPath -Value ({
            param([string]$Parent)
            $stagingPathState.Count++
            if ($stagingPathState.Count -eq 1) { return $foreignStaging }
            return $retryStaging
        }.GetNewClosure())
        try {
            $stagingRetryResult = New-EvidenceDirectoryClaim -EvidenceDirectory $stagingRetryClaim -RunId ('e'*32)
            Assert-Equal ([string]$stagingRetryResult.MarkerPath) $stagingRetryMarker 'Staging collision retry returned the wrong owner marker.'
            Assert-True (Test-Path -LiteralPath $foreignStaging -PathType Container) 'Staging collision moved or removed the foreign staging directory.'
            Assert-Equal ([IO.File]::ReadAllText($foreignStagingSentinel)) 'foreign-staging-owner' 'Staging collision changed or removed the foreign sentinel.'
            Assert-False (Test-Path -LiteralPath (Join-Path $stagingRetryClaim 'foreign-staging-sentinel.txt')) 'Staging collision moved the foreign sentinel into the claimed directory.'
            Assert-False (Test-Path -LiteralPath $retryStaging) 'Successful staging retry left its staging directory behind.'
            Assert-True ($stagingPathState.Count -ge 2) 'Exclusive staging creation did not retry after the forced collision.'
        }
        finally {
            Set-Item Function:\New-ContainmentClaimStagingPath -Value $savedClaimStagingPathFactory
            foreach ($file in @($stagingRetryMarker,(Join-Path $stagingRetryClaim 'foreign-staging-sentinel.txt'),$foreignStagingSentinel)) {
                if (Test-Path -LiteralPath $file -PathType Leaf) { Remove-Item -LiteralPath $file -Force -ErrorAction Stop }
            }
            foreach ($directory in @($stagingRetryClaim,$foreignStaging,$retryStaging)) {
                if ((Test-Path -LiteralPath $directory -PathType Container) -and @(Get-ChildItem -LiteralPath $directory -Force).Count -eq 0) {
                    [IO.Directory]::Delete($directory, $false)
                }
            }
        }

        $racingClaim = Join-Path $Root 'racing-foreign-claim'
        $racingSentinel = Join-Path $racingClaim 'foreign-sentinel.txt'
        $racingMarker = Join-Path $racingClaim '.containment-run-owner.json'
        Set-Item Function:\New-ContainmentEvidenceDirectoryExclusive -Value ({
            param([string]$Path,[byte[]]$MarkerBytes)
            [IO.Directory]::CreateDirectory($Path) | Out-Null
            Write-TestAscii -Path $racingSentinel -Text 'foreign-race-owner'
            return & $savedEvidenceDirectoryCreator -Path $Path -MarkerBytes $MarkerBytes
        }.GetNewClosure())
        try {
            Assert-ThrowsLike {
                New-EvidenceDirectoryClaim -EvidenceDirectory $racingClaim -RunId ('d'*32)
            } 'exist|collision|ownership|race' 'Claim accepted a foreign directory created after its initial absence check.'
            Assert-Equal ([IO.File]::ReadAllText($racingSentinel)) 'foreign-race-owner' 'Lost directory-creation race changed or removed the foreign sentinel.'
            Assert-False (Test-Path -LiteralPath $racingMarker) 'Lost directory-creation race published an owner marker into the foreign directory.'
            Assert-Equal @(Get-ChildItem -LiteralPath $Root -Force -Filter '.containment-claim-staging-*').Count 0 'Lost directory-creation race stranded an owned staging directory.'
        }
        finally {
            Set-Item Function:\New-ContainmentEvidenceDirectoryExclusive -Value $savedEvidenceDirectoryCreator
            if (Test-Path -LiteralPath $racingMarker -PathType Leaf) { Remove-Item -LiteralPath $racingMarker -Force -ErrorAction Stop }
            if (Test-Path -LiteralPath $racingSentinel -PathType Leaf) { Remove-Item -LiteralPath $racingSentinel -Force -ErrorAction Stop }
            if (Test-Path -LiteralPath $racingClaim -PathType Container) { [IO.Directory]::Delete($racingClaim, $false) }
        }

        foreach ($stage in @('write','flush','dispose')) {
            $newClaim = Join-Path $Root "new-claim-$stage"
            $faultPath = Join-Path $newClaim '.containment-run-owner.json'
            $faultStage = $stage
            Set-Item Function:\New-ContainmentCreateNewStream -Value ({
                param([string]$Path)
                $isStagedOwnerMarker = ([IO.Path]::GetFileName($Path) -ceq '.containment-run-owner.json' -and
                    [IO.Path]::GetFileName((Split-Path -Parent $Path)).StartsWith('.containment-claim-staging-', [StringComparison]::Ordinal))
                if ($isStagedOwnerMarker) {
                    return New-TestFaultingCreateNewStream -Path $Path -FaultStage $faultStage
                }
                return & $savedFactory -Path $Path
            }.GetNewClosure())
            Assert-ThrowsLike {
                New-EvidenceDirectoryClaim -EvidenceDirectory $newClaim -RunId ('a'*32)
            } 'injected create-new' "New-directory owner marker $stage fault did not propagate."
            Assert-False (Test-Path -LiteralPath $faultPath) "Owner marker $stage fault stranded its marker."
            Assert-False (Test-Path -LiteralPath $newClaim) "Owner marker $stage fault stranded its newly created evidence directory."

            $existingClaim = New-TestDirectory $Root "existing-claim-$stage"
            $faultPath = Join-Path $existingClaim '.containment-run-owner.json'
            Set-Item Function:\New-ContainmentCreateNewStream -Value ({
                param([string]$Path)
                if ([string]::Equals([IO.Path]::GetFullPath($Path),[IO.Path]::GetFullPath($faultPath),[StringComparison]::OrdinalIgnoreCase)) {
                    return New-TestFaultingCreateNewStream -Path $Path -FaultStage $faultStage
                }
                return & $savedFactory -Path $Path
            }.GetNewClosure())
            Assert-ThrowsLike {
                New-EvidenceDirectoryClaim -EvidenceDirectory $existingClaim -RunId ('b'*32)
            } 'injected create-new' "Existing-directory owner marker $stage fault did not propagate."
            Assert-True (Test-Path -LiteralPath $existingClaim -PathType Container) "Owner marker $stage fault removed a pre-existing empty evidence directory."
            Assert-Equal @(Get-ChildItem -LiteralPath $existingClaim -Force).Count 0 "Owner marker $stage fault stranded content in a pre-existing evidence directory."
        }

        $foreignClaim = New-TestDirectory $Root 'foreign-claim'
        $foreignMarker = Join-Path $foreignClaim '.containment-run-owner.json'
        Write-TestAscii $foreignMarker 'foreign-owner-marker'
        Assert-ThrowsLike {
            New-EvidenceDirectoryClaim -EvidenceDirectory $foreignClaim -RunId ('c'*32)
        } 'empty|nonempty' 'Claim accepted a foreign pre-existing owner marker.'
        Assert-Equal ([IO.File]::ReadAllText($foreignMarker)) 'foreign-owner-marker' 'Claim changed or removed a foreign pre-existing marker.'
    }
    finally {
        Set-Item Function:\New-ContainmentCreateNewStream -Value $savedFactory
        Set-Item Function:\Remove-ContainmentOwnedFileByIdentity -Value $savedIdentityRemover
        Set-Item Function:\New-ContainmentEvidenceDirectoryExclusive -Value $savedEvidenceDirectoryCreator
        Set-Item Function:\New-ContainmentClaimStagingPath -Value $savedClaimStagingPathFactory
    }
}

function Test-LowLevelIdentityBoundReplacementCleanup {
    param([string]$Root)

    $savedFactory = (Get-Item -LiteralPath Function:\New-ContainmentCreateNewStream).ScriptBlock
    $path = Join-Path $Root 'rebound-low-level.bin'
    $ownedAway = Join-Path $Root 'rebound-low-level-owned-away.bin'
    $payload = [Text.Encoding]::ASCII.GetBytes('owned-low-level-payload')
    $afterDispose = {
        Move-Item -LiteralPath $path -Destination $ownedAway -ErrorAction Stop
        Write-TestAscii -Path $path -Text 'foreign-low-level-replacement'
    }.GetNewClosure()
    try {
        Set-Item Function:\New-ContainmentCreateNewStream -Value ({
            param([string]$Path)
            if ([string]::Equals([IO.Path]::GetFullPath($Path),[IO.Path]::GetFullPath($path),[StringComparison]::OrdinalIgnoreCase)) {
                return New-TestFaultingCreateNewStream -Path $Path -FaultStage write -AfterDispose $afterDispose
            }
            return & $savedFactory -Path $Path
        }.GetNewClosure())
        Assert-ThrowsLike {
            Write-ContainmentCreateNewBytes -Path $path -Bytes $payload
        } 'identity|replacement|refus|cleanup.*incomplete' 'Low-level failed-write cleanup did not reject a foreign pathname replacement.'
        Assert-Equal ([IO.File]::ReadAllText($path)) 'foreign-low-level-replacement' 'Low-level failed-write cleanup changed or removed the foreign replacement.'
        Assert-True (Test-Path -LiteralPath $ownedAway -PathType Leaf) 'Low-level replacement fixture lost the original helper-created file.'
    }
    finally {
        Set-Item Function:\New-ContainmentCreateNewStream -Value $savedFactory
    }
}

function Test-PairIdentityBoundReplacementCleanup {
    param([string]$Root)

    $savedFactory = (Get-Item -LiteralPath Function:\New-ContainmentCreateNewStream).ScriptBlock
    $savedHash = (Get-Item -LiteralPath Function:\Get-ContainmentSha256).ScriptBlock
    $jsonPath = Join-Path $Root 'rebound-pair.json'
    $sidecarPath = Join-Path $Root 'rebound-pair.sha256'
    $ownedAway = Join-Path $Root 'rebound-pair-owned-away.json'
    $hashState = [pscustomobject]@{ Replaced = $false }
    try {
        Set-Item Function:\New-ContainmentCreateNewStream -Value ({
            param([string]$Path)
            if ([string]::Equals([IO.Path]::GetFullPath($Path),[IO.Path]::GetFullPath($sidecarPath),[StringComparison]::OrdinalIgnoreCase)) {
                return New-TestFaultingCreateNewStream -Path $Path -FaultStage write
            }
            return & $savedFactory -Path $Path
        }.GetNewClosure())
        Set-Item Function:\Get-ContainmentSha256 -Value ({
            param([string]$Path)
            if (-not $hashState.Replaced -and
                [string]::Equals([IO.Path]::GetFullPath($Path),[IO.Path]::GetFullPath($jsonPath),[StringComparison]::OrdinalIgnoreCase)) {
                $hashState.Replaced = $true
                Move-Item -LiteralPath $jsonPath -Destination $ownedAway -ErrorAction Stop
                Write-TestAscii -Path $jsonPath -Text 'foreign-pair-replacement'
            }
            return & $savedHash -Path $Path
        }.GetNewClosure())
        Assert-ThrowsLike {
            Write-CanonicalJsonPair -Path $jsonPath -SidecarPath $sidecarPath -Value ([ordered]@{schema_version=1;success=$true})
        } 'identity|replacement|refus|cleanup.*incomplete' 'Final-pair rollback did not reject a foreign JSON pathname replacement.'
        Assert-Equal ([IO.File]::ReadAllText($jsonPath)) 'foreign-pair-replacement' 'Final-pair rollback changed or removed the foreign JSON replacement.'
        Assert-False (Test-Path -LiteralPath $sidecarPath) 'Final-pair replacement fault stranded the failed sidecar publication.'
        Assert-True (Test-Path -LiteralPath $ownedAway -PathType Leaf) 'Final-pair replacement fixture lost the original helper-created JSON.'
    }
    finally {
        Set-Item Function:\New-ContainmentCreateNewStream -Value $savedFactory
        Set-Item Function:\Get-ContainmentSha256 -Value $savedHash
    }
}

function Test-NewEvidenceClaimForeignChildGap {
    param([string]$Root)

    $savedPathAssert = (Get-Item -LiteralPath Function:\Assert-ContainmentPathNotReparse).ScriptBlock
    $claimPath = Join-Path $Root 'new-claim-foreign-child-gap'
    $markerPath = Join-Path $claimPath '.containment-run-owner.json'
    $foreignChild = Join-Path $claimPath 'foreign-gap-child.txt'
    $state = [pscustomobject]@{ Injected = $false }
    try {
        Set-Item Function:\Assert-ContainmentPathNotReparse -Value ({
            param([string]$Path,[string]$Label)
            $result = & $savedPathAssert -Path $Path -Label $Label
            if (-not $state.Injected -and
                [string]::Equals([IO.Path]::GetFullPath($Path),[IO.Path]::GetFullPath($claimPath),[StringComparison]::OrdinalIgnoreCase) -and
                (Test-Path -LiteralPath $claimPath -PathType Container)) {
                $state.Injected = $true
                Write-TestAscii -Path $foreignChild -Text 'foreign-post-publication-child'
            }
            return $result
        }.GetNewClosure())
        Assert-ThrowsLike {
            New-EvidenceDirectoryClaim -EvidenceDirectory $claimPath -RunId ('f'*32)
        } 'exact|child|nonempty|claim.*incomplete|ownership' 'New evidence claim accepted a foreign child injected after directory publication.'
        Assert-Equal ([IO.File]::ReadAllText($foreignChild)) 'foreign-post-publication-child' 'Failed new evidence claim changed or removed the injected foreign child.'
        Assert-False (Test-Path -LiteralPath $markerPath) 'Failed new evidence claim stranded its owned marker beside the foreign child.'
        Assert-True (Test-Path -LiteralPath $claimPath -PathType Container) 'Failed new evidence claim removed the directory containing a foreign child.'
    }
    finally {
        Set-Item Function:\Assert-ContainmentPathNotReparse -Value $savedPathAssert
    }
}

function Test-NewEvidenceClaimEmptyDirectoryReplacement {
    param([string]$Root)

    $savedPathAssert = (Get-Item -LiteralPath Function:\Assert-ContainmentPathNotReparse).ScriptBlock
    $claimPath = Join-Path $Root 'new-claim-empty-directory-replacement'
    $ownedAway = Join-Path $Root 'new-claim-owned-directory-away'
    $state = [pscustomobject]@{ Replaced = $false }
    try {
        Set-Item Function:\Assert-ContainmentPathNotReparse -Value ({
            param([string]$Path,[string]$Label)
            $result = & $savedPathAssert -Path $Path -Label $Label
            if (-not $state.Replaced -and
                [string]::Equals([IO.Path]::GetFullPath($Path),[IO.Path]::GetFullPath($claimPath),[StringComparison]::OrdinalIgnoreCase) -and
                (Test-Path -LiteralPath $claimPath -PathType Container)) {
                $state.Replaced = $true
                Move-Item -LiteralPath $claimPath -Destination $ownedAway -ErrorAction Stop
                [IO.Directory]::CreateDirectory($claimPath) | Out-Null
            }
            return $result
        }.GetNewClosure())
        Assert-ThrowsLike {
            New-EvidenceDirectoryClaim -EvidenceDirectory $claimPath -RunId ('e'*32)
        } 'identity|replacement|refus|claim.*incomplete|ownership' 'New evidence claim cleanup accepted or removed an empty foreign directory replacement.'
        Assert-True (Test-Path -LiteralPath $claimPath -PathType Container) 'Failed new evidence claim removed the empty foreign directory replacement.'
        Assert-Equal @(Get-ChildItem -LiteralPath $claimPath -Force).Count 0 'Foreign replacement directory did not remain empty.'
        Assert-True (Test-Path -LiteralPath $ownedAway -PathType Container) 'Whole-directory replacement fixture lost the original helper-created directory.'
        Assert-True (Test-Path -LiteralPath (Join-Path $ownedAway '.containment-run-owner.json') -PathType Leaf) 'Whole-directory replacement fixture lost the original owned marker.'
    }
    finally {
        Set-Item Function:\Assert-ContainmentPathNotReparse -Value $savedPathAssert
    }
}

function Test-ExistingEvidenceClaimMarkerReplacement {
    param([string]$Root)

    $savedWriter = (Get-Item -LiteralPath Function:\Write-ContainmentCreateNewBytes).ScriptBlock
    $claimPath = New-TestDirectory $Root 'existing-claim-marker-replacement'
    $markerPath = Join-Path $claimPath '.containment-run-owner.json'
    $ownedAway = Join-Path $Root 'existing-claim-owned-marker-away.json'
    $state = [pscustomobject]@{ Replaced = $false }
    try {
        Set-Item Function:\Write-ContainmentCreateNewBytes -Value ({
            param([string]$Path,[byte[]]$Bytes)
            $ownership = & $savedWriter -Path $Path -Bytes $Bytes
            if (-not $state.Replaced -and
                [string]::Equals([IO.Path]::GetFullPath($Path),[IO.Path]::GetFullPath($markerPath),[StringComparison]::OrdinalIgnoreCase)) {
                $state.Replaced = $true
                Move-Item -LiteralPath $markerPath -Destination $ownedAway -ErrorAction Stop
                Write-TestAscii -Path $markerPath -Text 'foreign-owner-marker-replacement'
            }
            return $ownership
        }.GetNewClosure())
        Assert-ThrowsLike {
            New-EvidenceDirectoryClaim -EvidenceDirectory $claimPath -RunId ('1'*32)
        } 'identity|replacement|refus|claim.*incomplete|ownership' 'Existing evidence claim accepted a foreign owner-marker replacement.'
        Assert-Equal ([IO.File]::ReadAllText($markerPath)) 'foreign-owner-marker-replacement' 'Existing claim cleanup changed or removed the foreign marker replacement.'
        Assert-True (Test-Path -LiteralPath $ownedAway -PathType Leaf) 'Existing claim replacement fixture lost the original owned marker.'
        Assert-True (Test-Path -LiteralPath $claimPath -PathType Container) 'Existing claim failure removed the pre-existing directory.'
    }
    finally {
        Set-Item Function:\Write-ContainmentCreateNewBytes -Value $savedWriter
    }
}

function Test-ProcessQuotingAndWorkingDirectory {
    param([string]$Root)
    Assert-Equal (ConvertTo-ProcessArgument '') '""' 'Empty process argument was not preserved.'
    Assert-Equal (ConvertTo-ProcessArgument $null) '""' 'Null process argument was not preserved.'
    $scriptPath = New-ChildScript $Root 'echo-args.ps1' @'
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::Out.WriteLine((ConvertTo-Json -InputObject @($args) -Compress))
[Console]::Out.WriteLine((Get-Location).ProviderPath)
'@
    $sentinels = @('left','','right','with spaces','quote"inside','C:\path with space\trail\')
    $result = Invoke-ContainmentChildProcess -Executable $WindowsPowerShell -Arguments (@('-NoProfile','-ExecutionPolicy','Bypass','-File',$scriptPath) + $sentinels) -DiagnosticDirectory $Root -TimeoutSeconds 10
    Assert-Equal $result.ExitCode 0 'Quoted child failed.'
    $lines = @(Get-Content -LiteralPath $result.StdoutPath)
    $roundTrip = @(($lines[0] | ConvertFrom-Json))
    Assert-SequenceEqual $roundTrip $sentinels 'Windows argument round-trip drifted.'
    Assert-True ([IO.Path]::IsPathRooted($lines[1])) 'Child working directory was not absolute.'
    Assert-False ([string]::Equals($lines[1],$RepoRoot,[StringComparison]::OrdinalIgnoreCase)) 'Child inherited repository cwd.'
}

function Test-ConcurrentStreamsAndTimeout {
    param([string]$Root)
    $flood = New-ChildScript $Root 'flood.ps1' @'
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$out = 'O' * 196608
$err = 'E' * 196608
[Console]::Out.Write($out)
[Console]::Error.Write($err)
'@
    $result = Invoke-ContainmentChildProcess -Executable $WindowsPowerShell -Arguments @('-NoProfile','-ExecutionPolicy','Bypass','-File',$flood) -DiagnosticDirectory $Root -TimeoutSeconds 10
    Assert-Equal $result.ExitCode 0 'Dual-stream child failed.'
    Assert-Equal (Get-Item $result.StdoutPath).Length 196608 'stdout was not fully drained.'
    Assert-Equal (Get-Item $result.StderrPath).Length 196608 'stderr was not fully drained.'
    Assert-True ([string]$result.StdoutSummary).Length -le 8192 'stdout summary is unbounded.'
    Assert-True ([string]$result.StderrSummary).Length -le 8192 'stderr summary is unbounded.'

    $timeout = New-ChildScript $Root 'timeout.ps1' @'
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::Out.WriteLine("PID=$PID")
[Console]::Out.Flush()
Start-Sleep -Seconds 30
'@
    $caught = $null
    try { [void](Invoke-ContainmentChildProcess -Executable $WindowsPowerShell -Arguments @('-NoProfile','-File',$timeout) -DiagnosticDirectory $Root -TimeoutSeconds 1) } catch { $caught = $_ }
    Assert-True ($null -ne $caught) 'Timeout child did not fail.'
    Assert-Contains ([string]$caught.Exception.Message) 'timed out' 'Timeout error was not explicit.'
    $pidValue = [int]$caught.Exception.Data['ProcessId']
    Assert-True ($pidValue -gt 0) 'Timeout error did not retain child PID.'
    Start-Sleep -Milliseconds 200
    Assert-False ($null -ne (Get-Process -Id $pidValue -ErrorAction SilentlyContinue)) 'Timed-out child remained alive.'

    $grandchildPidPath = Join-Path $Root 'timeout-grandchild.pid'
    $lateMarkerPath = Join-Path $Root 'timeout-grandchild-late.txt'
    $grandchild = New-ChildScript $Root 'timeout-grandchild.ps1' @'
param([string]$PidPath,[string]$LateMarkerPath)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[IO.File]::WriteAllText($PidPath,[string]$PID,[Text.UTF8Encoding]::new($false))
Start-Sleep -Seconds 3
[IO.File]::WriteAllText($LateMarkerPath,'late',[Text.UTF8Encoding]::new($false))
Start-Sleep -Seconds 30
'@
    $parent = New-ChildScript $Root 'timeout-parent.ps1' @'
param([string]$PowerShellPath,[string]$GrandchildScript,[string]$GrandchildPidPath,[string]$LateMarkerPath)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$info = [Diagnostics.ProcessStartInfo]::new()
$info.FileName = $PowerShellPath
$info.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $GrandchildScript + '" -PidPath "' + $GrandchildPidPath + '" -LateMarkerPath "' + $LateMarkerPath + '"'
$info.UseShellExecute = $false
$info.CreateNoWindow = $true
$info.RedirectStandardOutput = $true
$info.RedirectStandardError = $true
$child = [Diagnostics.Process]::Start($info)
[Console]::Out.WriteLine("GRANDCHILD_PID=$($child.Id)")
[Console]::Out.Flush()
Start-Sleep -Seconds 30
'@
    $treeCaught = $null
    try {
        [void](Invoke-ContainmentChildProcess `
            -Executable $WindowsPowerShell `
            -Arguments @('-NoProfile','-File',$parent,$WindowsPowerShell,$grandchild,$grandchildPidPath,$lateMarkerPath) `
            -DiagnosticDirectory $Root -TimeoutSeconds 1)
    }
    catch { $treeCaught = $_ }
    Assert-True ($null -ne $treeCaught) 'Timeout process tree did not fail.'
    Assert-Contains ([string]$treeCaught.Exception.Message) 'timed out' 'Process-tree timeout error was not explicit.'
    $treeParentPid = [int]$treeCaught.Exception.Data['ProcessId']
    Assert-True ($treeParentPid -gt 0) 'Timed-out process tree did not retain its parent PID.'
    $grandchildPid = 0
    for ($attempt = 0; $attempt -lt 20 -and $grandchildPid -le 0; $attempt++) {
        if (Test-Path -LiteralPath $grandchildPidPath -PathType Leaf) {
            $grandchildPid = [int]([IO.File]::ReadAllText($grandchildPidPath))
        }
        else { Start-Sleep -Milliseconds 50 }
    }
    Assert-True ($grandchildPid -gt 0) 'Timed-out process tree did not expose the grandchild PID.'
    try {
        Start-Sleep -Milliseconds 2500
        Assert-False ($null -ne (Get-Process -Id $treeParentPid -ErrorAction SilentlyContinue)) 'Timed-out process-tree parent remained alive.'
        Assert-False ($null -ne (Get-Process -Id $grandchildPid -ErrorAction SilentlyContinue)) 'Timed-out grandchild remained alive.'
        Assert-False (Test-Path -LiteralPath $lateMarkerPath -PathType Leaf) 'Timed-out grandchild continued mutating after cleanup.'
    }
    finally {
        $parentSurvivor = Get-Process -Id $treeParentPid -ErrorAction SilentlyContinue
        if ($null -ne $parentSurvivor) { Stop-Process -Id $treeParentPid -Force -ErrorAction SilentlyContinue }
        $survivor = Get-Process -Id $grandchildPid -ErrorAction SilentlyContinue
        if ($null -ne $survivor) { Stop-Process -Id $grandchildPid -Force -ErrorAction SilentlyContinue }
    }
}

function Test-InstalledAndInstallerEnvironmentPolicies {
    param([string]$Root)
    $report = New-ChildScript $Root 'report-env.ps1' @'
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$controlled = [ordered]@{}
foreach ($entry in [Environment]::GetEnvironmentVariables('Process').GetEnumerator()) {
    $name = [string]$entry.Key
    if ($name -match '^(?i:PYTHONPATH|PYTHONHOME|PYTHONUSERBASE|PYTHONNOUSERSITE|DSPY_MODEL|DSPY_CACHEDIR|CHIRP_HOME|ROOK_.*)$') { $controlled[$name] = [string]$entry.Value }
}
$controlled | ConvertTo-Json -Compress
'@
    $names = @('PYTHONPATH','PYTHONHOME','pYtHoNuSeRbAsE','PyThOnNoUsErSiTe','DSPY_MODEL','DSPY_CACHEDIR','cHiRp_HoMe','ROOK_MCP_TOOL_PROFILE','rook_target_port','ROOK_MODEL_OVERRIDE','ROOK_BRIDGE_TOKEN')
    $saved = @{}
    foreach ($name in $names) { $saved[$name]=[Environment]::GetEnvironmentVariable($name,'Process'); [Environment]::SetEnvironmentVariable($name,"hostile-$name",'Process') }
    try {
        $installRoot = New-TestDirectory $Root 'installed-app'
        $dataRoot = New-TestDirectory $Root 'installed-data'
        $dspy = New-TestDirectory $dataRoot 'dspy-cache'
        $chirp = New-TestDirectory $installRoot 'chirp'
        $policies = @(
            @{Kind='transport-full';Profile='full';Interactive=$false;Chirp=$chirp},
            @{Kind='transport-lean';Profile='lean';Interactive=$false;Chirp=$chirp},
            @{Kind='transport-readonly';Profile='readonly';Interactive=$false;Chirp=$chirp},
            @{Kind='discovery-default';Profile=$null;Interactive=$false;Chirp=$chirp},
            @{Kind='discovery-interactive';Profile='full';Interactive=$true;Chirp=$chirp},
            @{Kind='internal-matrix';Profile=$null;Interactive=$false;Chirp=$chirp},
            @{Kind='live-rhino';Profile=$null;Interactive=$false;Chirp=$null},
            @{Kind='live-grasshopper';Profile=$null;Interactive=$false;Chirp=$null}
        )
        foreach ($policy in $policies) {
            $result = Invoke-InstalledPythonProcess -PythonPath $WindowsPowerShell -Arguments @('-NoProfile','-File',$report) -DiagnosticDirectory $Root -TimeoutSeconds 10 -InstallRoot $installRoot -DataRoot $dataRoot -DspyCache $dspy -ChirpHome $policy.Chirp -Profile $policy.Profile -Interactive:$policy.Interactive
            $record = (Get-Content -LiteralPath $result.StdoutPath -Raw).Trim() | ConvertFrom-Json
            $folded = @{}
            foreach ($property in $record.PSObject.Properties) { $folded[$property.Name.ToLowerInvariant()] = [string]$property.Value }
            Assert-False $folded.ContainsKey('pythonpath') "$($policy.Kind) retained PYTHONPATH."
            Assert-False $folded.ContainsKey('pythonhome') "$($policy.Kind) retained PYTHONHOME."
            Assert-False $folded.ContainsKey('pythonuserbase') "$($policy.Kind) retained PYTHONUSERBASE."
            Assert-False $folded.ContainsKey('dspy_model') "$($policy.Kind) retained DSPY_MODEL."
            Assert-Equal $folded['pythonnousersite'] '1' "$($policy.Kind) PYTHONNOUSERSITE drifted."
            Assert-Equal $folded['dspy_cachedir'] $dspy "$($policy.Kind) DSPY_CACHEDIR drifted."
            Assert-Equal $folded['rook_install_root'] $installRoot "$($policy.Kind) install root drifted."
            Assert-Equal $folded['rook_data_dir'] $dataRoot "$($policy.Kind) data root drifted."
            Assert-Equal $folded['rook_mode'] 'release' "$($policy.Kind) mode drifted."
            Assert-Equal $folded['rook_dspy_restrict_pickle'] '1' "$($policy.Kind) pickle restriction drifted."
            if ($null -eq $policy.Chirp) { Assert-False $folded.ContainsKey('chirp_home') "$($policy.Kind) unexpectedly retained CHIRP_HOME." } else { Assert-Equal $folded['chirp_home'] $chirp "$($policy.Kind) CHIRP_HOME drifted." }
            if ($null -eq $policy.Profile) { Assert-False $folded.ContainsKey('rook_mcp_tool_profile') "$($policy.Kind) unexpectedly set profile." } else { Assert-Equal $folded['rook_mcp_tool_profile'] $policy.Profile "$($policy.Kind) profile drifted." }
            if ($policy.Interactive) { Assert-Equal $folded['rook_enable_interactive_command_learning'] '1' 'Interactive opt-in drifted.' } else { Assert-False $folded.ContainsKey('rook_enable_interactive_command_learning') "$($policy.Kind) unexpectedly enabled interactive mode." }
            Assert-True @($result.RemovedEnvironmentNames).Count -ge 8 "$($policy.Kind) did not record removed names."
            Assert-False ((ConvertTo-Json $result -Depth 8).Contains('hostile-')) "$($policy.Kind) leaked controlled values into diagnostics."
        }

        $installerStart = [pscustomobject]@{count=0;process_id=0}
        $installerStartedAction = { param([int]$ProcessId); $installerStart.count++; $installerStart.process_id=$ProcessId }.GetNewClosure()
        $installer = Invoke-CandidateInstallerProcess -InstallerPath $WindowsPowerShell -InstallerArguments @('-NoProfile','-File',$report) -DiagnosticDirectory $Root -TimeoutSeconds 10 -OnProcessStarted $installerStartedAction
        Assert-Equal $installerStart.count 1 'Installer start signal did not occur exactly after one successful Process.Start.'
        Assert-Equal $installerStart.process_id $installer.ProcessId 'Installer start signal retained the wrong process identity.'
        $installerRecord = (Get-Content -LiteralPath $installer.StdoutPath -Raw).Trim() | ConvertFrom-Json
        $installerFolded = @{}
        foreach ($property in $installerRecord.PSObject.Properties) { $installerFolded[$property.Name.ToLowerInvariant()] = [string]$property.Value }
        Assert-SequenceEqual @($installerFolded.Keys | Sort-Object) @('pythonnousersite') 'Installer controlled environment was not closed.'
        Assert-Equal $installerFolded['pythonnousersite'] '1' 'Installer PYTHONNOUSERSITE drifted.'
        Assert-False ((ConvertTo-Json $installer -Depth 8).Contains('hostile-')) 'Installer diagnostics leaked controlled values.'
        $postInstall = New-ChildScript $Root 'fake-post-install.ps1' @'
param([string]$ShellPath,[string]$EnvironmentReportPath)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
& $ShellPath -NoProfile -ExecutionPolicy Bypass -File $EnvironmentReportPath
if ($LASTEXITCODE -ne 0) { throw "fake post-install child failed with exit code $LASTEXITCODE" }
'@
        $inherited = Invoke-CandidateInstallerProcess -InstallerPath $WindowsPowerShell -InstallerArguments @('-NoProfile','-File',$postInstall,'-ShellPath',$WindowsPowerShell,'-EnvironmentReportPath',$report) -DiagnosticDirectory $Root -TimeoutSeconds 10
        $inheritedRecord = (Get-Content -LiteralPath $inherited.StdoutPath -Raw).Trim() | ConvertFrom-Json
        $inheritedFolded = @{}
        foreach ($property in $inheritedRecord.PSObject.Properties) { $inheritedFolded[$property.Name.ToLowerInvariant()] = [string]$property.Value }
        Assert-SequenceEqual @($inheritedFolded.Keys | Sort-Object) @('pythonnousersite') 'Fake post-install grandchild did not inherit the closed installer environment.'
        Assert-Equal $inheritedFolded['pythonnousersite'] '1' 'Fake post-install grandchild PYTHONNOUSERSITE drifted.'
        $prelaunch = [pscustomobject]@{started=$false}
        $prelaunchAction = { $prelaunch.started=$true }.GetNewClosure()
        Assert-ThrowsLike {
            [void](Invoke-CandidateInstallerProcess -InstallerPath (Join-Path $Root 'missing-installer.exe') -InstallerArguments @() -DiagnosticDirectory $Root -TimeoutSeconds 10 -OnProcessStarted $prelaunchAction)
        } 'missing|executable' 'Missing installer did not fail before launch.'
        Assert-False $prelaunch.started 'Prelaunch installer failure emitted an actual-start signal.'
    } finally {
        foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name,$saved[$name],'Process') }
    }
}

function Test-ProductionStartupIsolation {
    param([string]$Root)
    $identity = Assert-FullCpythonRuntime -PythonPath $PrivatePythonPath -DiagnosticDirectory (New-TestDirectory $Root 'installed-identity') -EnforceNoUserSite
    Assert-SequenceEqual @($identity.final_controlled_environment_names) @('PYTHONNOUSERSITE') 'Installed private-Python identity probe omitted PYTHONNOUSERSITE=1 policy.'
    $result = Test-PythonStartupIsolation -PythonPath $PrivatePythonPath -EvidenceRoot (New-TestDirectory $Root 'startup-isolation') -InstallRoot (New-TestDirectory $Root 'startup-app') -DataRoot (New-TestDirectory $Root 'startup-data')
    Assert-True ([bool]$result.control_fired) 'Production startup isolation did not prove the unsanitized control.'
    Assert-True ([bool]$result.sanitized) 'Production startup isolation did not prove sanitization.'
    Assert-True ([bool]$result.sitecustomize_control_hit -and [bool]$result.usercustomize_control_hit) 'Both startup controls did not fire.'
    Assert-False ([bool]$result.sitecustomize_sanitized_hit -or [bool]$result.usercustomize_sanitized_hit) 'A startup hook fired under sanitized policy.'
    Assert-Equal ([string]$result.sanitized_environment.PYTHONNOUSERSITE) '1' 'Sanitized startup environment drifted.'
    Assert-False $result.sanitized_environment.ContainsKey('PYTHONUSERBASE') 'Sanitized startup retained PYTHONUSERBASE.'
    $venvPython = Join-Path $RepoRoot 'mcp_server\.venv\Scripts\python.exe'
    Assert-ThrowsLike { Test-PythonStartupIsolation -PythonPath $venvPython -EvidenceRoot (New-TestDirectory $Root 'venv-reject') -InstallRoot (New-TestDirectory $Root 'venv-app') -DataRoot (New-TestDirectory $Root 'venv-data') } 'full CPython|virtual environment|base executable' 'Venv fixture was not rejected.'
    $isolated = New-TestDirectory $Root 'pth-isolated'
    Copy-Item $PrivatePythonPath (Join-Path $isolated 'python.exe')
    Write-TestAscii (Join-Path $isolated 'python._pth') "python311.zip`n"
    Assert-ThrowsLike { Assert-FullCpythonRuntime -PythonPath (Join-Path $isolated 'python.exe') -ExpectedVersion $null } '_pth|isolated' '._pth-isolated runtime was not rejected.'
}

function Test-CandidateIdentityAndEvidencePathGuards {
    param([string]$Root)
    $fixture = New-MinimalCandidateFixture -Root $Root
    $identity = Read-AndValidateCandidateIdentity -ArtifactDirectory $fixture.Artifact -CandidateIdentityPath $fixture.IdentityPath -CandidateSidecarPath $fixture.SidecarPath -ValidateSourceRepositories:$false
    Assert-Equal $identity.identity_sha256 (Get-TestSha256 $fixture.IdentityPath) 'Candidate identity hash drifted.'
    Assert-Equal $identity.installer_sha256 (Get-TestSha256 $fixture.Installer) 'Candidate installer hash drifted.'
    $snapshot = Get-CandidateArtifactSnapshot -Candidate $identity
    Assert-CandidateArtifactSnapshot -Snapshot $snapshot

    $original = [IO.File]::ReadAllText($fixture.IdentityPath)
    [IO.File]::WriteAllText($fixture.IdentityPath, $original + ' ', [Text.UTF8Encoding]::new($false))
    Assert-ThrowsLike { Read-AndValidateCandidateIdentity -ArtifactDirectory $fixture.Artifact -CandidateIdentityPath $fixture.IdentityPath -CandidateSidecarPath $fixture.SidecarPath -ValidateSourceRepositories:$false } 'canonical|sidecar|hash' 'Noncanonical/corrupt identity was accepted.'
    [IO.File]::WriteAllText($fixture.IdentityPath, $original, [Text.UTF8Encoding]::new($false))
    $identityHash = Get-TestSha256 $fixture.IdentityPath
    Write-TestAscii $fixture.SidecarPath "$identityHash  containment-candidate.json`n"
    Write-TestAscii $fixture.Installer 'drift'
    Assert-ThrowsLike { Read-AndValidateCandidateIdentity -ArtifactDirectory $fixture.Artifact -CandidateIdentityPath $fixture.IdentityPath -CandidateSidecarPath $fixture.SidecarPath -ValidateSourceRepositories:$false } 'installer.*hash|hash.*installer' 'Installer drift was accepted.'
    Copy-Item $WindowsPowerShell $fixture.Installer -Force

    $identityTypeCases = @(
        [ordered]@{label='schema_version';mutate={param($value) $value.schema_version = '1'}},
        [ordered]@{label='non_publishable';mutate={param($value) $value.non_publishable = 'false'}}
    )
    foreach ($case in $identityTypeCases) {
        $typedIdentity = $original | ConvertFrom-Json
        $mutate = $case.mutate
        & $mutate $typedIdentity
        Write-TestUtf8NoBom $fixture.IdentityPath (ConvertTo-TestCanonicalJson $typedIdentity)
        $typedIdentityHash = Get-TestSha256 $fixture.IdentityPath
        Write-TestAscii $fixture.SidecarPath "$typedIdentityHash  containment-candidate.json`n"
        Assert-ThrowsLike {
            Read-AndValidateCandidateIdentity -ArtifactDirectory $fixture.Artifact -CandidateIdentityPath $fixture.IdentityPath -CandidateSidecarPath $fixture.SidecarPath -ValidateSourceRepositories:$false
        } 'schema|non-publishable|type' "String-coercible candidate identity $($case.label) was accepted."
    }

    $badIdentity = $original | ConvertFrom-Json
    $badIdentity.sources.rook.sha = '9' * 40
    Write-TestUtf8NoBom $fixture.IdentityPath (ConvertTo-TestCanonicalJson $badIdentity)
    $badHash = Get-TestSha256 $fixture.IdentityPath
    Write-TestAscii $fixture.SidecarPath "$badHash  containment-candidate.json`n"
    Assert-ThrowsLike { Read-AndValidateCandidateIdentity -ArtifactDirectory $fixture.Artifact -CandidateIdentityPath $fixture.IdentityPath -CandidateSidecarPath $fixture.SidecarPath -ValidateSourceRepositories:$true } 'source|inventory|identity|SHA' 'Source SHA mismatch was accepted.'

    $empty = Join-Path $Root 'new-evidence'
    $claim = New-EvidenceDirectoryClaim -EvidenceDirectory $empty -RunId ('a'*32)
    Assert-True (Test-Path $claim.MarkerPath -PathType Leaf) 'Evidence ownership marker was not written.'
    Assert-ThrowsLike { New-EvidenceDirectoryClaim -EvidenceDirectory $empty -RunId ('b'*32) } 'empty|owned|nonempty' 'Owned evidence directory was reclaimed.'
    $nonempty = New-TestDirectory $Root 'nonempty-evidence'
    Write-TestAscii (Join-Path $nonempty 'sentinel.txt') 'sentinel'
    $before = @(Get-ChildItem $nonempty -Force | Select-Object Name,Length | ConvertTo-Json -Compress)
    Assert-ThrowsLike { New-EvidenceDirectoryClaim -EvidenceDirectory $nonempty -RunId ('c'*32) } 'empty|nonempty' 'Nonempty evidence directory was accepted.'
    $after = @(Get-ChildItem $nonempty -Force | Select-Object Name,Length | ConvertTo-Json -Compress)
    Assert-SequenceEqual $after $before 'Preownership rejection wrote evidence.'

    $target = New-TestDirectory $Root 'junction-target'
    $junction = Join-Path $Root 'junction-evidence'
    New-Item -ItemType Junction -Path $junction -Target $target | Out-Null
    Assert-ThrowsLike { New-EvidenceDirectoryClaim -EvidenceDirectory $junction -RunId ('d'*32) } 'reparse' 'Reparse evidence directory was accepted.'
    Assert-Equal @(Get-ChildItem $target -Force).Count 0 'Reparse rejection wrote through the junction.'
}

function Test-AuthorizationProtocolAndScenarioValidation {
    param([string]$Root)
    $challenge = New-AuthorizationRecord -Scenario rhino
    $line = ConvertTo-TestCanonicalJson $challenge
    $parsed = ConvertFrom-CanonicalJsonLine -Line $line -ExpectedType 'authorization_required'
    Assert-Equal $parsed.required_response $challenge.required_response 'Authorization response drifted.'
    $bad = $line.Replace('"schema_version":1','"schema_version":2')
    Assert-ThrowsLike { ConvertFrom-CanonicalJsonLine -Line $bad -ExpectedType 'authorization_required' } 'schema|canonical' 'Wrong challenge schema was accepted.'
    Assert-ThrowsLike { ConvertFrom-CanonicalJsonLine -Line ($line + ' ') -ExpectedType 'authorization_required' } 'canonical' 'Noncanonical challenge was accepted.'
    $authorizationTypeCases = @(
        [ordered]@{label='schema_version';mutate={param($value) $value.schema_version = '1'}},
        [ordered]@{label='target.process_id';mutate={param($value) $value.target.process_id = '123'}},
        [ordered]@{label='target.port';mutate={param($value) $value.target.port = '9878'}}
    )
    foreach ($case in $authorizationTypeCases) {
        $typedChallenge = $challenge | ConvertTo-Json -Depth 20 | ConvertFrom-Json
        $mutate = $case.mutate
        & $mutate $typedChallenge
        $typedChallenge.target_sha256 = Get-TestValueSha256 $typedChallenge.target
        $typedChallenge.required_response = "AUTHORIZE scenario=$($typedChallenge.scenario) run=$($typedChallenge.run_id) nonce=$($typedChallenge.nonce) target=$($typedChallenge.target_sha256) mutation=$($typedChallenge.mutation_sha256) verify=$($typedChallenge.verification_sha256) restore=$($typedChallenge.restoration_sha256)"
        Assert-ThrowsLike {
            ConvertFrom-CanonicalJsonLine -Line (ConvertTo-TestCanonicalJson $typedChallenge) -ExpectedType 'authorization_required'
        } 'schema|target|type' "String-coercible authorization JSONL $($case.label) was accepted."
    }

    $child = New-ChildScript $Root 'gate-child.ps1' @'
param([string]$ChallengePath,[string]$ResultPath,[string]$Mode,[string]$RestorationMarkerPath)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$challenge = Get-Content -Raw -LiteralPath $ChallengePath
if ($Mode -eq 'oversized-challenge') {
    [Console]::Out.Write('X' * 131072)
    [Console]::Out.Flush()
    Start-Sleep -Seconds 30
    exit 3
}
[Console]::Out.WriteLine($challenge)
[Console]::Out.Flush()
if ($Mode -eq 'eof') { exit 3 }
$response = [Console]::In.ReadLine()
if ($Mode -eq 'replay') { [Console]::Out.WriteLine($challenge); [Console]::Out.Flush(); exit 3 }
if ($Mode -eq 'wrong-result') { [Console]::Out.WriteLine('{"type":"unexpected"}'); [Console]::Out.Flush(); exit 3 }
$record = $challenge | ConvertFrom-Json
if ($response -cne [string]$record.required_response) { exit 3 }
if ($Mode -eq 'oversized-result') {
    [Console]::Out.Write('X' * 131072)
    [Console]::Out.Flush()
    Start-Sleep -Milliseconds 500
    [IO.File]::WriteAllText($RestorationMarkerPath,'restored-after-oversized-result')
    exit 3
}
if ($Mode -eq 'restore-after-malformed') {
    [Console]::Out.WriteLine('{"type":"unexpected"}')
    [Console]::Out.Flush()
    Start-Sleep -Milliseconds 500
    [IO.File]::WriteAllText($RestorationMarkerPath,'restored')
    exit 3
}
if ($Mode -eq 'restore-past-original-deadline') {
    Start-Sleep -Milliseconds 1000
    [Console]::Out.WriteLine('{"type":"unexpected"}')
    [Console]::Out.Flush()
    Start-Sleep -Milliseconds 2500
    [IO.File]::WriteAllText($RestorationMarkerPath,'late-restoration')
    exit 3
}
[Console]::Out.WriteLine((Get-Content -Raw -LiteralPath $ResultPath))
[Console]::Out.Flush()
if ($Mode -eq 'failed-result') { exit 3 }
if ($Mode -eq 'oversized-extra') {
    [Console]::Out.Write('X' * 131072)
    [Console]::Out.Flush()
    Start-Sleep -Milliseconds 500
    [IO.File]::WriteAllText($RestorationMarkerPath,'restored-after-oversized-extra')
    exit 3
}
'@
    $challengePath = Join-Path $Root 'challenge.json'
    Write-TestUtf8NoBom $challengePath $line
    $resultRecord = [ordered]@{ type='scenario_result';schema_version=1;scenario='rhino';run_id=('1'*32);success=$true;failure_label=$null;evidence_path='rhino-scenario.json';evidence_sha256=('7'*64) }
    $typedResultRecord = $resultRecord | ConvertTo-Json -Depth 10 | ConvertFrom-Json
    $typedResultRecord.success = 'false'
    Assert-ThrowsLike {
        ConvertFrom-CanonicalJsonLine -Line (ConvertTo-TestCanonicalJson $typedResultRecord) -ExpectedType 'scenario_result'
    } 'success|type|schema' 'String scenario_result success was accepted as a boolean.'
    $resultPath = Join-Path $Root 'result.json'
    Write-TestUtf8NoBom $resultPath (ConvertTo-TestCanonicalJson $resultRecord)
    $script:ExpectedReadHost = [string]$challenge.required_response
    function global:Read-Host { param([string]$Prompt); return $script:ExpectedReadHost }
    try {
        $gate = Invoke-LiveGateProcess -PythonPath $WindowsPowerShell -Arguments @('-NoProfile','-File',$child,'-ChallengePath',$challengePath,'-ResultPath',$resultPath,'-Mode','success') -DiagnosticDirectory $Root -TimeoutSeconds 10 -ExpectedScenario rhino
        Assert-Equal $gate.ExitCode 0 'Fake live gate failed.'
        Assert-Equal $gate.Authorization.required_response $challenge.required_response 'Gate relayed wrong challenge.'
        Assert-Equal $gate.Result.type 'scenario_result' 'Gate final record drifted.'
        foreach ($mode in @('eof','replay','wrong-result')) {
            Assert-ThrowsLike { Invoke-LiveGateProcess -PythonPath $WindowsPowerShell -Arguments @('-NoProfile','-File',$child,'-ChallengePath',$challengePath,'-ResultPath',$resultPath,'-Mode',$mode) -DiagnosticDirectory $Root -TimeoutSeconds 10 -ExpectedScenario rhino } 'authorization|challenge|JSONL|scenario_result|exit' "Gate mode $mode did not fail closed."
        }
        Assert-ThrowsLike {
            Invoke-LiveGateProcess -PythonPath $WindowsPowerShell -Arguments @('-NoProfile','-File',$child,'-ChallengePath',$challengePath,'-ResultPath',$resultPath,'-Mode','oversized-challenge') -DiagnosticDirectory $Root -TimeoutSeconds 2 -ExpectedScenario rhino
        } 'length|limit|large|bounded' 'Oversized unterminated authorization challenge was not rejected by the line bound.'
        foreach ($mode in @('oversized-result','oversized-extra')) {
            $oversizedRestoration = Join-Path $Root "$mode-restoration.txt"
            Assert-ThrowsLike {
                Invoke-LiveGateProcess -PythonPath $WindowsPowerShell -Arguments @('-NoProfile','-File',$child,'-ChallengePath',$challengePath,'-ResultPath',$resultPath,'-Mode',$mode,'-RestorationMarkerPath',$oversizedRestoration) -DiagnosticDirectory $Root -TimeoutSeconds 10 -ExpectedScenario rhino
            } 'length|limit|large|bounded' "Gate mode $mode was not rejected by the line bound."
            Assert-True (Test-Path -LiteralPath $oversizedRestoration -PathType Leaf) "Gate mode $mode was killed before restoration completed."
        }
        foreach ($failureLabel in @('ownership_ambiguous','restoration_failed','cleanup_failed')) {
            $failedResultPath = Join-Path $Root "result-$failureLabel.json"
            $failedResult = [ordered]@{ type='scenario_result';schema_version=1;scenario='rhino';run_id=('1'*32);success=$false;failure_label=$failureLabel;evidence_path='rhino-scenario.json';evidence_sha256=('7'*64) }
            Write-TestUtf8NoBom $failedResultPath (ConvertTo-TestCanonicalJson $failedResult)
            $failedGate = $null
            try {
                Invoke-LiveGateProcess -PythonPath $WindowsPowerShell -Arguments @('-NoProfile','-File',$child,'-ChallengePath',$challengePath,'-ResultPath',$failedResultPath,'-Mode','failed-result') -DiagnosticDirectory $Root -TimeoutSeconds 10 -ExpectedScenario rhino
            }
            catch { $failedGate = $_ }
            Assert-True ($null -ne $failedGate) "Gate failure label $failureLabel unexpectedly succeeded."
            Assert-Equal ([string]$failedGate.Exception.Data['ContainmentFailureLabel']) $failureLabel "Gate failure label $failureLabel was lost behind the child exit code."
        }
        $restorationMarker = Join-Path $Root 'authorized-restoration-completed.txt'
        Assert-ThrowsLike {
            Invoke-LiveGateProcess -PythonPath $WindowsPowerShell -Arguments @('-NoProfile','-File',$child,'-ChallengePath',$challengePath,'-ResultPath',$resultPath,'-Mode','restore-after-malformed','-RestorationMarkerPath',$restorationMarker) -DiagnosticDirectory $Root -TimeoutSeconds 10 -ExpectedScenario rhino
        } 'JSONL|scenario_result|exit' 'Malformed post-authorization output did not fail closed.'
        Assert-True (Test-Path -LiteralPath $restorationMarker -PathType Leaf) 'Authorized child was killed before its restoration/finally window completed.'
        Assert-Equal (Get-Content -LiteralPath $restorationMarker -Raw) 'restored' 'Authorized child restoration marker drifted.'
        $lateRestorationMarker = Join-Path $Root 'authorized-restoration-past-deadline.txt'
        $deadlineTimer = [Diagnostics.Stopwatch]::StartNew()
        Assert-ThrowsLike {
            Invoke-LiveGateProcess -PythonPath $WindowsPowerShell -Arguments @('-NoProfile','-File',$child,'-ChallengePath',$challengePath,'-ResultPath',$resultPath,'-Mode','restore-past-original-deadline','-RestorationMarkerPath',$lateRestorationMarker) -DiagnosticDirectory $Root -TimeoutSeconds 3 -ExpectedScenario rhino
        } 'JSONL|scenario_result|exit|timed out' 'Authorized failure reset the original live-gate deadline.'
        $deadlineTimer.Stop()
        Assert-False (Test-Path -LiteralPath $lateRestorationMarker) 'Authorized failure received a fresh restoration timeout after the original deadline.'
        Assert-True ($deadlineTimer.Elapsed.TotalSeconds -lt 5.5) 'Authorized failure exceeded the bounded original deadline window.'
    } finally { Remove-Item Function:\global:Read-Host -ErrorAction SilentlyContinue }

    $scenarioDir = New-TestDirectory $Root 'scenario-good'
    $scenario = New-FakeScenarioEvidence -Directory $scenarioDir -Scenario rhino
    $validated = Read-AndValidateScenarioEvidence -Scenario rhino -ScenarioPath $scenario.Path -ScenarioSidecarPath $scenario.Sidecar -ExpectedInstalledRoot $scenarioDir
    Assert-True $validated.restoration.verified 'Valid scenario restoration was not retained.'
    $rhinoNames = @($scenario.Record.operations | ForEach-Object { [string]$_.name })
    Assert-ContainmentScenarioOperationSequence -Scenario rhino -Names $rhinoNames
    Assert-ThrowsLike {
        Assert-ContainmentScenarioOperationSequence -Scenario rhino -Names @($rhinoNames[0..($rhinoNames.Count - 2)])
    } 'sequence|count' 'Truncated Rhino operation sequence was accepted.'
    Write-TestAscii $scenario.Sidecar "$('0'*64)  rhino-scenario.json`n"
    Assert-ThrowsLike { Read-AndValidateScenarioEvidence -Scenario rhino -ScenarioPath $scenario.Path -ScenarioSidecarPath $scenario.Sidecar -ExpectedInstalledRoot $scenarioDir } 'sidecar|hash' 'Tampered scenario sidecar was accepted.'
    $badRestoration = New-FakeScenarioEvidence -Directory (New-TestDirectory $Root 'scenario-restoration') -Scenario rhino -FailRestoration
    $restorationEvidenceFailure = $null
    try { Read-AndValidateScenarioEvidence -Scenario rhino -ScenarioPath $badRestoration.Path -ScenarioSidecarPath $badRestoration.Sidecar -ExpectedInstalledRoot (Split-Path -Parent $badRestoration.Path) }
    catch { $restorationEvidenceFailure = $_ }
    Assert-True ($null -ne $restorationEvidenceFailure) 'Unverified restoration was accepted.'
    Assert-Equal ([string]$restorationEvidenceFailure.Exception.Data['ContainmentFailureLabel']) 'restoration_failed' 'Unverified restoration lost its typed failure label.'
    $ambiguousOwnership = New-FakeScenarioEvidence -Directory (New-TestDirectory $Root 'scenario-ownership') -Scenario rhino
    $ambiguousOwnership.Record.target.ownership_certain = $false
    Save-FakeScenarioEvidence -Fixture $ambiguousOwnership
    $ownershipEvidenceFailure = $null
    try { Read-AndValidateScenarioEvidence -Scenario rhino -ScenarioPath $ambiguousOwnership.Path -ScenarioSidecarPath $ambiguousOwnership.Sidecar -ExpectedInstalledRoot (Split-Path -Parent $ambiguousOwnership.Path) }
    catch { $ownershipEvidenceFailure = $_ }
    Assert-True ($null -ne $ownershipEvidenceFailure) 'Ambiguous ownership evidence was accepted.'
    Assert-Equal ([string]$ownershipEvidenceFailure.Exception.Data['ContainmentFailureLabel']) 'ownership_ambiguous' 'Ambiguous ownership evidence lost its typed failure label.'
    $cleanupFailureFixture = New-FakeScenarioEvidence -Directory (New-TestDirectory $Root 'scenario-cleanup') -Scenario rhino
    $cleanupFailureFixture.Record.restoration.scratch_disposed = $false
    Save-FakeScenarioEvidence -Fixture $cleanupFailureFixture
    $cleanupEvidenceFailure = $null
    try { Read-AndValidateScenarioEvidence -Scenario rhino -ScenarioPath $cleanupFailureFixture.Path -ScenarioSidecarPath $cleanupFailureFixture.Sidecar -ExpectedInstalledRoot (Split-Path -Parent $cleanupFailureFixture.Path) }
    catch { $cleanupEvidenceFailure = $_ }
    Assert-True ($null -ne $cleanupEvidenceFailure) 'Cleanup-failure evidence was accepted.'
    Assert-Equal ([string]$cleanupEvidenceFailure.Exception.Data['ContainmentFailureLabel']) 'cleanup_failed' 'Cleanup-failure evidence lost its typed failure label.'
    $badTelemetry = New-FakeScenarioEvidence -Directory (New-TestDirectory $Root 'scenario-telemetry') -Scenario grasshopper -TelemetryChanged
    $grasshopperNames = @($badTelemetry.Record.operations | ForEach-Object { [string]$_.name })
    Assert-ContainmentScenarioOperationSequence -Scenario grasshopper -Names $grasshopperNames
    $grasshopperNames[7] = 'gh_snapshot'
    Assert-ThrowsLike {
        Assert-ContainmentScenarioOperationSequence -Scenario grasshopper -Names $grasshopperNames
    } 'sequence|readiness|forward' 'Reordered Grasshopper operation sequence was accepted.'
    Assert-ThrowsLike { Read-AndValidateScenarioEvidence -Scenario grasshopper -ScenarioPath $badTelemetry.Path -ScenarioSidecarPath $badTelemetry.Sidecar -ExpectedInstalledRoot (Split-Path -Parent $badTelemetry.Path) } 'telemetry|containment' 'Supported-path containment activity was accepted.'

    $emptyEdit = New-FakeScenarioEvidence -Directory (New-TestDirectory $Root 'scenario-empty-edit') -Scenario grasshopper
    Set-FakeScenarioOperationResult -Fixture $emptyEdit -Name 'gh_edit' -Data ([ordered]@{
        epoch=8;components=@();flows=@();diagnostics=[ordered]@{total=0;errors=0;warnings=0}
        edit_summary=[ordered]@{created=2;connected=1;solve_scheduled=$true;solver_locked=$false;solver_state_known=$true;verification_deferred=$true;errors=$null}
    })
    Assert-ThrowsLike {
        Read-AndValidateScenarioEvidence -Scenario grasshopper -ScenarioPath $emptyEdit.Path -ScenarioSidecarPath $emptyEdit.Sidecar -ExpectedInstalledRoot (Split-Path -Parent $emptyEdit.Path)
    } 'edit|stage|projection|snapshot' 'Empty gh_edit result was accepted against a two-component final projection.'

    $wrongRhinoDocument = New-FakeScenarioEvidence -Directory (New-TestDirectory $Root 'scenario-wrong-rhino-document') -Scenario rhino
    Set-FakeScenarioOperationResult -Fixture $wrongRhinoDocument -Name 'rhino_document' -Occurrence 1 -Data ([ordered]@{name='fixture';path=$wrongRhinoDocument.Record.target.scratch_path;objectCount=2;modified=$true})
    Assert-ThrowsLike {
        Read-AndValidateScenarioEvidence -Scenario rhino -ScenarioPath $wrongRhinoDocument.Path -ScenarioSidecarPath $wrongRhinoDocument.Sidecar -ExpectedInstalledRoot (Split-Path -Parent $wrongRhinoDocument.Path)
    } 'document|stage|preflight|projection' 'Mutated Rhino document result was accepted in the preflight stage.'

    $wrongRhinoObjects = New-FakeScenarioEvidence -Directory (New-TestDirectory $Root 'scenario-wrong-rhino-objects') -Scenario rhino
    $finalObjects = @($wrongRhinoObjects.Record.verification.projection.objects.sphere,$wrongRhinoObjects.Record.verification.projection.objects.point)
    Set-FakeScenarioOperationResult -Fixture $wrongRhinoObjects -Name 'rhino_objects' -Occurrence 1 -Data ([ordered]@{objects=$finalObjects;count=2})
    Assert-ThrowsLike {
        Read-AndValidateScenarioEvidence -Scenario rhino -ScenarioPath $wrongRhinoObjects.Path -ScenarioSidecarPath $wrongRhinoObjects.Sidecar -ExpectedInstalledRoot (Split-Path -Parent $wrongRhinoObjects.Path)
    } 'object|stage|preflight|projection' 'Mutated Rhino object set was accepted in the preflight stage.'

    $wrongGhStatus = New-FakeScenarioEvidence -Directory (New-TestDirectory $Root 'scenario-wrong-gh-status') -Scenario grasshopper
    Set-FakeScenarioOperationResult -Fixture $wrongGhStatus -Name 'gh_status' -Occurrence 1 -Data ([ordered]@{available=$true;has_active_canvas=$true;has_active_document=$true;object_count=2;ready_for_edit=$true})
    Assert-ThrowsLike {
        Read-AndValidateScenarioEvidence -Scenario grasshopper -ScenarioPath $wrongGhStatus.Path -ScenarioSidecarPath $wrongGhStatus.Sidecar -ExpectedInstalledRoot (Split-Path -Parent $wrongGhStatus.Path)
    } 'status|stage|preflight|projection' 'Ready mutated Grasshopper status was accepted in the absent preflight stage.'

    $wrongRestoredSnapshot = New-FakeScenarioEvidence -Directory (New-TestDirectory $Root 'scenario-wrong-restored-snapshot') -Scenario grasshopper
    $solved = $wrongRestoredSnapshot.Record.verification.projection
    Set-FakeScenarioOperationResult -Fixture $wrongRestoredSnapshot -Name 'gh_snapshot' -Occurrence 5 -Data ([ordered]@{epoch=9;components=$solved.components;flows=$solved.flows;diagnostics=$solved.diagnostics})
    Assert-ThrowsLike {
        Read-AndValidateScenarioEvidence -Scenario grasshopper -ScenarioPath $wrongRestoredSnapshot.Path -ScenarioSidecarPath $wrongRestoredSnapshot.Sidecar -ExpectedInstalledRoot (Split-Path -Parent $wrongRestoredSnapshot.Path)
    } 'snapshot|stage|restor|projection' 'Mutated Grasshopper snapshot was accepted after the final undo.'

    $coordinatedRhino = New-FakeScenarioEvidence -Directory (New-TestDirectory $Root 'scenario-coordinated-rhino-projection') -Scenario rhino
    $driftedRhinoBbox = [ordered]@{min=@(-5,-5,-5);max=@(5,5,5)}
    $coordinatedRhino.Record.verification.projection.objects.sphere.bbox = $driftedRhinoBbox
    $coordinatedRhino.Record.verification.projection_sha256 = Get-TestValueSha256 $coordinatedRhino.Record.verification.projection
    $sphere = $coordinatedRhino.Record.verification.projection.objects.sphere
    Set-FakeScenarioOperationResult -Fixture $coordinatedRhino -Name 'rhino_geometry' -Occurrence 1 -Data ([ordered]@{
        id=$sphere.id;name=$sphere.name;type='Brep';bbox=$driftedRhinoBbox
        geometry=[ordered]@{type='Brep';faceCount=1;edgeCount=1;vertexCount=2;isSolid=$true;isManifold=$true;area=201.0619;volume=268.0826}
    })
    Save-FakeScenarioEvidence -Fixture $coordinatedRhino
    Assert-ThrowsLike {
        Read-AndValidateScenarioEvidence -Scenario rhino -ScenarioPath $coordinatedRhino.Path -ScenarioSidecarPath $coordinatedRhino.Sidecar -ExpectedInstalledRoot (Split-Path -Parent $coordinatedRhino.Path)
    } 'Rhino|sphere|bbox|bound|projection' 'Coordinated Rhino bbox drift was accepted as self-consistent evidence.'

    $coordinatedGh = New-FakeScenarioEvidence -Directory (New-TestDirectory $Root 'scenario-coordinated-gh-projection') -Scenario grasshopper
    $driftedComponents = @(
        [ordered]@{id='X1';type='DriftedSlider';nick='Drifted';pos=@(101,101);is_param=$false;value=[ordered]@{type='slider';val=5;min=0;max=10}},
        [ordered]@{id='X2';type='DriftedComponent';name='Drifted Sphere';componentGuid='ffffffff-ffff-4fff-8fff-ffffffffffff';pos=@(401,101);inputs=@([ordered]@{idx=1;name='Radius';sources=2});outputs=@([ordered]@{idx=0;name='Drifted';type='Other';data=[ordered]@{structure='single';count=2}})}
    )
    $coordinatedGh.Record.verification.projection.components = $driftedComponents
    $coordinatedGh.Record.verification.projection_sha256 = Get-TestValueSha256 $coordinatedGh.Record.verification.projection
    $ghDiagnostics = $coordinatedGh.Record.verification.projection.diagnostics
    Set-FakeScenarioOperationResult -Fixture $coordinatedGh -Name 'gh_edit' -Data ([ordered]@{
        epoch=8;components=$driftedComponents;flows=@('C1.O0>C2.I1');diagnostics=$ghDiagnostics
        edit_summary=[ordered]@{created=2;connected=1;solve_scheduled=$true;solver_locked=$false;solver_state_known=$true;verification_deferred=$true;errors=$null}
    })
    foreach ($occurrence in @(3,4)) {
        Set-FakeScenarioOperationResult -Fixture $coordinatedGh -Name 'gh_snapshot' -Occurrence $occurrence -Data ([ordered]@{epoch=8;components=$driftedComponents;flows=@('C1.O0>C2.I1');diagnostics=$ghDiagnostics})
    }
    Save-FakeScenarioEvidence -Fixture $coordinatedGh
    Assert-ThrowsLike {
        Read-AndValidateScenarioEvidence -Scenario grasshopper -ScenarioPath $coordinatedGh.Path -ScenarioSidecarPath $coordinatedGh.Sidecar -ExpectedInstalledRoot (Split-Path -Parent $coordinatedGh.Path)
    } 'Grasshopper|component|slider|Sphere|projection' 'Coordinated Grasshopper component drift was accepted as self-consistent evidence.'

    $typedRhino = New-FakeScenarioEvidence -Directory (New-TestDirectory $Root 'scenario-rhino-type-drift') -Scenario rhino
    $typedRhino.Record.verification.projection.document.object_count = '2'
    $typedRhino.Record.verification.projection.document.modified = 'true'
    $typedRhino.Record.verification.projection.objects.sphere.radius = '4'
    $typedRhino.Record.verification.projection.objects.sphere.face_count = '1'
    $typedRhino.Record.verification.projection.objects.sphere.edge_count = '1'
    $typedRhino.Record.verification.projection.objects.sphere.vertex_count = '2'
    $typedRhino.Record.verification.projection.objects.sphere.is_solid = 'true'
    $typedRhino.Record.verification.projection.objects.sphere.is_manifold = 'true'
    $typedRhino.Record.verification.projection.objects.sphere.area = '201.0619'
    $typedRhino.Record.verification.projection.objects.sphere.volume = '268.0826'
    $typedRhino.Record.verification.projection_sha256 = Get-TestValueSha256 $typedRhino.Record.verification.projection
    Save-FakeScenarioEvidence -Fixture $typedRhino
    Assert-ThrowsLike {
        Read-AndValidateScenarioEvidence -Scenario rhino -ScenarioPath $typedRhino.Path -ScenarioSidecarPath $typedRhino.Sidecar -ExpectedInstalledRoot (Split-Path -Parent $typedRhino.Path)
    } 'type|Rhino|projection' 'String-coercible Rhino verification fields were accepted.'

    $typedGh = New-FakeScenarioEvidence -Directory (New-TestDirectory $Root 'scenario-gh-type-drift') -Scenario grasshopper
    $typedComponents = $typedGh.Record.verification.projection.components
    $typedComponents[0].is_param = 'true'
    $typedComponents[0].value.val = '4'
    $typedComponents[0].value.min = '1'
    $typedComponents[0].value.max = '9'
    $typedComponents[1].inputs[1].sources = '1'
    $typedComponents[1].outputs[0].idx = '0'
    $typedComponents[1].outputs[0].data.count = '1'
    $typedGh.Record.verification.projection.solve.edit.solve_scheduled = 'true'
    $typedGh.Record.verification.projection.solve.edit.solver_locked = ''
    $typedGh.Record.verification.projection.solve.edit.solver_state_known = 'true'
    $typedGh.Record.verification.projection.solve.edit.verification_deferred = 'true'
    $typedGh.Record.verification.projection_sha256 = Get-TestValueSha256 $typedGh.Record.verification.projection
    $typedDiagnostics = $typedGh.Record.verification.projection.diagnostics
    Set-FakeScenarioOperationResult -Fixture $typedGh -Name 'gh_edit' -Data ([ordered]@{
        epoch=8;components=$typedComponents;flows=@('C1.O0>C2.I1');diagnostics=$typedDiagnostics
        edit_summary=[ordered]@{created=2;connected=1;solve_scheduled=$true;solver_locked=$false;solver_state_known=$true;verification_deferred=$true;errors=$null}
    })
    foreach ($occurrence in @(3,4)) {
        Set-FakeScenarioOperationResult -Fixture $typedGh -Name 'gh_snapshot' -Occurrence $occurrence -Data ([ordered]@{epoch=8;components=$typedComponents;flows=@('C1.O0>C2.I1');diagnostics=$typedDiagnostics})
    }
    Save-FakeScenarioEvidence -Fixture $typedGh
    Assert-ThrowsLike {
        Read-AndValidateScenarioEvidence -Scenario grasshopper -ScenarioPath $typedGh.Path -ScenarioSidecarPath $typedGh.Sidecar -ExpectedInstalledRoot (Split-Path -Parent $typedGh.Path)
    } 'type|Grasshopper|projection' 'String-coercible Grasshopper verification fields were accepted.'

    $typedEnvelope = New-FakeScenarioEvidence -Directory (New-TestDirectory $Root 'scenario-envelope-type-drift') -Scenario rhino
    $typedEnvelope.Record.schema_version = '1'
    $typedEnvelope.Record.success = 'true'
    $typedEnvelope.Record.target.process_id = '123'
    $typedEnvelope.Record.target.port = '9878'
    $typedEnvelope.Record.target.ownership_certain = 'true'
    $typedEnvelope.Record.authorization.state_unchanged = 'true'
    $typedEnvelope.Record.verification.passed = 'true'
    $typedEnvelope.Record.operations[0].index = '1'
    $typedEnvelope.Record.operations[0].success = 'true'
    $typedEnvelope.Record.artifacts[0].size = [string]$typedEnvelope.Record.artifacts[0].size
    $typedEnvelope.Record.telemetry.process_id = '123'
    $typedEnvelope.Record.telemetry.delta_count = '0'
    Save-FakeScenarioEvidence -Fixture $typedEnvelope
    Assert-ThrowsLike {
        Read-AndValidateScenarioEvidence -Scenario rhino -ScenarioPath $typedEnvelope.Path -ScenarioSidecarPath $typedEnvelope.Sidecar -ExpectedInstalledRoot (Split-Path -Parent $typedEnvelope.Path)
    } 'type|schema|envelope|target|operation|telemetry|artifact' 'String-coercible scenario envelope fields were accepted.'

    $wrongPreflightDigest = New-FakeScenarioEvidence -Directory (New-TestDirectory $Root 'scenario-wrong-preflight-digest') -Scenario rhino
    $wrongPreflightDigest.Record.authorization.preflight_sha256 = 'e' * 64
    $wrongPreflightDigest.Record.authorization.pre_mutation_sha256 = 'e' * 64
    Save-FakeScenarioEvidence -Fixture $wrongPreflightDigest
    Assert-ThrowsLike {
        Read-AndValidateScenarioEvidence -Scenario rhino -ScenarioPath $wrongPreflightDigest.Path -ScenarioSidecarPath $wrongPreflightDigest.Sidecar -ExpectedInstalledRoot (Split-Path -Parent $wrongPreflightDigest.Path)
    } 'preflight|pre-mutation|digest|hash' 'Self-consistent but uncomputed authorization preflight digests were accepted.'

    $coordinatedPreflight = New-FakeScenarioEvidence -Directory (New-TestDirectory $Root 'scenario-coordinated-preflight') -Scenario rhino
    $coordinatedPreflight.Record.pre_state.host_projection.prior_path = 'C:\drifted-host.3dm'
    $coordinatedPreflight.Record.pre_state.host_projection.prior_modified = $true
    $coordinatedPreflight.Record.pre_state.host_sha256 = Get-TestValueSha256 $coordinatedPreflight.Record.pre_state.host_projection
    $coordinatedPreflight.Record.pre_state.scratch_projection.modified = $true
    $coordinatedPreflight.Record.pre_state.scratch_sha256 = Get-TestValueSha256 $coordinatedPreflight.Record.pre_state.scratch_projection
    foreach ($occurrence in @(1,2)) {
        Set-FakeScenarioOperationResult -Fixture $coordinatedPreflight -Name 'rhino_document' -Occurrence $occurrence -Data ([ordered]@{name='fixture';path='C:\drifted-host.3dm';objectCount=0;modified=$true})
    }
    foreach ($occurrence in @(3,7)) {
        Set-FakeScenarioOperationResult -Fixture $coordinatedPreflight -Name 'rhino_document' -Occurrence $occurrence -Data ([ordered]@{name='fixture';path=$coordinatedPreflight.Record.target.scratch_path;objectCount=0;modified=$true})
    }
    $driftedPreflightProjection = [ordered]@{runtime_serial=321;path='C:\drifted-host.3dm';object_count=0;modified=$true;object_ids=@()}
    $driftedPreflightHash = Get-TestValueSha256 $driftedPreflightProjection
    $coordinatedPreflight.Record.authorization.preflight_sha256 = $driftedPreflightHash
    $coordinatedPreflight.Record.authorization.pre_mutation_sha256 = $driftedPreflightHash
    Save-FakeScenarioEvidence -Fixture $coordinatedPreflight
    Assert-ThrowsLike {
        Read-AndValidateScenarioEvidence -Scenario rhino -ScenarioPath $coordinatedPreflight.Path -ScenarioSidecarPath $coordinatedPreflight.Sidecar -ExpectedInstalledRoot (Split-Path -Parent $coordinatedPreflight.Path)
    } 'preflight|host|scratch|empty|clean|projection' 'Coordinated nonempty/dirty Rhino preflight projections were accepted.'

    $retainedFixture = New-FakeScenarioEvidence -Directory (New-TestDirectory $Root 'scenario-retained-binding') -Scenario rhino
    $retainedEvidence = Read-AndValidateScenarioEvidence -Scenario rhino -ScenarioPath $retainedFixture.Path -ScenarioSidecarPath $retainedFixture.Sidecar -ExpectedInstalledRoot (Split-Path -Parent $retainedFixture.Path)
    $retainedChallenge = New-ContainmentAuthorizationChallenge -Scenario rhino -RunId ([string]$retainedEvidence.run_id) -Nonce ([string]$retainedEvidence.authorization.nonce) -Target $retainedEvidence.target
    $acceptedScenario = [ordered]@{
        success=$true;restoration_verified=$true;telemetry_delta=0
        evidence_path=$retainedFixture.Path;evidence_sha256=(Get-TestSha256 $retainedFixture.Path)
        sidecar_path=$retainedFixture.Sidecar;sidecar_sha256=(Get-TestSha256 $retainedFixture.Sidecar)
        authorization=$retainedChallenge;operations=@($retainedEvidence.operations)
        verification=$retainedEvidence.verification;restoration=$retainedEvidence.restoration
        target=$retainedEvidence.target;runtime=$retainedEvidence.runtime;telemetry=$retainedEvidence.telemetry
        gate_process_id=456
    }
    [void](Assert-ContainmentRetainedScenarioBinding -Scenario rhino -Accepted $acceptedScenario -ScenarioEvidence $retainedEvidence -EvidencePath $retainedFixture.Path -SidecarPath $retainedFixture.Sidecar)
    $relocatedEvidence = Join-Path (Split-Path -Parent $retainedFixture.Path) 'relocated-scenario.json'
    Copy-Item -LiteralPath $retainedFixture.Path -Destination $relocatedEvidence
    $badAccepted = $acceptedScenario | ConvertTo-Json -Depth 100 | ConvertFrom-Json
    $badAccepted.evidence_path = $relocatedEvidence
    Assert-ThrowsLike {
        Assert-ContainmentRetainedScenarioBinding -Scenario rhino -Accepted $badAccepted -ScenarioEvidence $retainedEvidence -EvidencePath $retainedFixture.Path -SidecarPath $retainedFixture.Sidecar
    } 'fixed|path|scenario' 'Relocated retained scenario evidence was accepted.'
    foreach ($case in @(
        [ordered]@{label='sidecar';mutate={param($value);$value.sidecar_sha256='0'*64}},
        [ordered]@{label='authorization';mutate={param($value);$value.authorization.nonce='0'*32}},
        [ordered]@{label='target';mutate={param($value);$value.target.port=9999}},
        [ordered]@{label='runtime';mutate={param($value);$value.runtime.cwd='C:\drifted'}},
        [ordered]@{label='gate process';mutate={param($value);$value.gate_process_id=0}}
    )) {
        $badAccepted = $acceptedScenario | ConvertTo-Json -Depth 100 | ConvertFrom-Json
        & $case.mutate $badAccepted
        Assert-ThrowsLike {
            Assert-ContainmentRetainedScenarioBinding -Scenario rhino -Accepted $badAccepted -ScenarioEvidence $retainedEvidence -EvidencePath $retainedFixture.Path -SidecarPath $retainedFixture.Sidecar
        } ([string]$case.label + '|binding|drift') "Retained scenario $($case.label) drift was accepted."
    }
}

function Test-StartupSurfaceAndDurableHold {
    param([string]$Root)
    $local = New-TestDirectory $Root 'localappdata'
    $appdata = New-TestDirectory $Root 'appdata'
    $homeRoot = New-TestDirectory $Root 'home'
    $runtime = New-TestDirectory $local 'Rook'
    $venv = New-TestDirectory $runtime 'venv'
    Write-TestAscii (Join-Path $venv 'runtime.bin') 'venv-bytes'
    $plugin = New-TestDirectory (New-TestDirectory (New-TestDirectory (New-TestDirectory $appdata 'McNeel') 'Rhinoceros') '8.0') 'Plug-ins'
    $plugin = New-TestDirectory $plugin 'RookNative'
    foreach ($tfm in @('net8.0','net7.0','net48')) {
        $dir = New-TestDirectory $plugin $tfm
        Write-TestAscii (Join-Path $dir 'Rook.rhp') "assembly-$tfm"
        $manifest = [ordered]@{pythonPath=(Join-Path $venv 'Scripts\python.exe');workingDirectory=(Join-Path $runtime 'app\mcp_server');module='rook.agent.chat.service_main';owner='rhino-panel';pythonPathEntries=@();environment=[ordered]@{}}
        Write-TestUtf8NoBom (Join-Path $dir 'RookChatService.json') (ConvertTo-TestCanonicalJson $manifest)
    }
    $claude = [ordered]@{mcpServers=[ordered]@{rook=[ordered]@{command=(Join-Path $venv 'Scripts\python.exe');args=@('-m','rook')}}}
    Write-TestUtf8NoBom (Join-Path $homeRoot '.claude.json') (ConvertTo-TestCanonicalJson $claude)
    $codex = New-TestDirectory $homeRoot '.codex'
    Write-TestUtf8NoBom (Join-Path $codex 'config.toml') "[mcp_servers.rook]`ncommand = '$(Join-Path $venv 'Scripts\python.exe')'`n"
    $projection = Get-ContainmentStartupSurfaceProjection -LocalAppDataRoot $local -AppDataRoot $appdata -HomeRoot $homeRoot -RegistryFileName (Join-Path $plugin 'net8.0\Rook.rhp')
    Assert-True $projection.valid 'Valid startup projection was rejected.'
    $identityHash = 'a' * 64
    $runId = 'b' * 32
    $postDisableState = [pscustomobject]@{count=0}
    $postDisableAction = { $postDisableState.count++; return [ordered]@{quiet=$true;sha256=('d'*64)} }.GetNewClosure()
    $hold = Enter-ContainmentDurableHold -CandidateIdentitySha256 $identityHash -RunId $runId -LocalAppDataRoot $local -AppDataRoot $appdata -HomeRoot $homeRoot -StartupProjection $projection -FinalQuietResweep ([ordered]@{quiet=$true;sha256=('c'*64)}) -FinalQuietResweepAction $postDisableAction
    Assert-True $hold.success 'Durable hold did not succeed.'
    Assert-Equal $postDisableState.count 1 'Durable hold did not run exactly one post-disable quiet resweep.'
    Assert-Equal $hold.pre_disable_quiet_resweep.sha256 ('c'*64) 'Durable hold lost pre-disable quiet evidence.'
    Assert-Equal $hold.post_disable_quiet_resweep.sha256 ('d'*64) 'Durable hold lost post-disable quiet evidence.'
    Assert-Equal $hold.sidecar_sha256 (Get-TestSha256 $hold.receipt_sidecar_path) 'Durable hold did not bind the receipt sidecar hash.'
    Assert-False (Test-Path $venv) 'Durable hold left original venv active.'
    Assert-True (Test-Path $hold.venv.held_path -PathType Container) 'Durable hold did not retain venv.'
    foreach ($assembly in @($hold.assemblies)) {
        if ($assembly.source_present) {
            Assert-False (Test-Path $assembly.original_path) 'Durable hold left an original Rook.rhp active.'
            Assert-True (Test-Path $assembly.held_path -PathType Leaf) 'Durable hold lost a held assembly.'
            Assert-False $assembly.held_path.EndsWith('.rhp',[StringComparison]::OrdinalIgnoreCase) 'Held assembly still ends in .rhp.'
        }
    }
    Assert-True (Test-Path $hold.receipt_path -PathType Leaf) 'Durable hold receipt is missing.'
    Assert-True (Test-Path $hold.receipt_sidecar_path -PathType Leaf) 'Durable hold sidecar is missing.'
    $receiptWrite = (Get-Item $hold.receipt_path).LastWriteTimeUtc
    $verified = Test-ContainmentDurableHold -ReceiptPath $hold.receipt_path -SidecarPath $hold.receipt_sidecar_path
    Assert-True $verified.success 'Idempotent hold verification failed.'
    Assert-Equal (Get-Item $hold.receipt_path).LastWriteTimeUtc $receiptWrite 'Idempotent hold verification mutated receipt.'
    Assert-ThrowsLike { & (Join-Path $venv 'Scripts\python.exe') } 'not recognized|does not exist|cannot find|term' 'Configured MCP path respawned after hold.'

    $collisionLocal = New-TestDirectory $Root 'collision-local'
    $collisionRuntime = New-TestDirectory $collisionLocal 'Rook'
    [void](New-TestDirectory $collisionRuntime 'venv')
    $collisionHold = Join-Path $collisionRuntime "containment-hold\$identityHash\$runId"
    [IO.Directory]::CreateDirectory($collisionHold) | Out-Null
    Assert-ThrowsLike { Enter-ContainmentDurableHold -CandidateIdentitySha256 $identityHash -RunId $runId -LocalAppDataRoot $collisionLocal -AppDataRoot $appdata -HomeRoot $homeRoot -StartupProjection $projection -FinalQuietResweep ([ordered]@{quiet=$true}) -FinalQuietResweepAction { [ordered]@{quiet=$true} } } 'collision|exists|fresh' 'Hold collision was accepted.'

    $alternate = $projection | ConvertTo-Json -Depth 20 | ConvertFrom-Json
    $alternate.records[0].resolved_path = Join-Path $Root 'alternate.exe'
    $alternate.valid = $false
    Assert-ThrowsLike { Assert-ContainmentStartupProjection -Projection $alternate -ExpectedVenvPath $venv -ExpectedPluginRoot $plugin } 'alternate|startup|projection' 'Alternate startup authority was accepted.'

    $partialLocal = New-TestDirectory $Root 'partial-local'
    $partialAppData = New-TestDirectory $Root 'partial-appdata'
    $partialHome = New-TestDirectory $Root 'partial-home'
    $partialRuntime = New-TestDirectory $partialLocal 'Rook'
    $partialVenv = New-TestDirectory $partialRuntime 'venv'
    Write-TestAscii (Join-Path $partialVenv 'runtime.bin') 'partial-venv'
    $partialPlugin = New-TestDirectory (New-TestDirectory (New-TestDirectory (New-TestDirectory $partialAppData 'McNeel') 'Rhinoceros') '8.0') 'Plug-ins'
    $partialPlugin = New-TestDirectory $partialPlugin 'RookNative'
    foreach ($tfm in @('net8.0','net7.0','net48')) {
        $dir = New-TestDirectory $partialPlugin $tfm
        Write-TestAscii (Join-Path $dir 'Rook.rhp') "partial-$tfm"
    }
    $partialProjection = Get-ContainmentStartupSurfaceProjection -LocalAppDataRoot $partialLocal -AppDataRoot $partialAppData -HomeRoot $partialHome -RegistryFileName (Join-Path $partialPlugin 'net8.0\Rook.rhp')
    $partialIdentity = 'e' * 64
    $partialRun = 'f' * 32
    $collisionAssembly = (Join-Path $partialPlugin 'net7.0\Rook.rhp') + ".contained.$partialIdentity.$partialRun"
    Write-TestAscii $collisionAssembly 'preexisting-collision'
    $partialFailure = $null
    try {
        [void](Enter-ContainmentDurableHold -CandidateIdentitySha256 $partialIdentity -RunId $partialRun -LocalAppDataRoot $partialLocal -AppDataRoot $partialAppData -HomeRoot $partialHome -StartupProjection $partialProjection -FinalQuietResweep ([ordered]@{quiet=$true}) -FinalQuietResweepAction { [ordered]@{quiet=$true} })
    } catch { $partialFailure = $_ }
    Assert-True ($null -ne $partialFailure) 'Partial durable hold failure did not fail closed.'
    $retainedHoldPath = [string]$partialFailure.Exception.Data['ContainmentHoldPath']
    Assert-True ([IO.Path]::IsPathRooted($retainedHoldPath)) 'Partial hold failure omitted its deterministic hold path.'
    Assert-True (Test-Path -LiteralPath $retainedHoldPath -PathType Container) 'Partial hold path does not retain held bytes.'
    Assert-False (Test-Path -LiteralPath $partialVenv) 'Partial hold failure restored or retained the active venv path.'
    Assert-True (Test-Path -LiteralPath (Join-Path $retainedHoldPath 'venv') -PathType Container) 'Partial hold failure lost the held venv.'
    $retainedProjection = $partialFailure.Exception.Data['ContainmentHoldProjection']
    $retainedProjectionSha = [string]$partialFailure.Exception.Data['ContainmentHoldProjectionSha256']
    Assert-True ($null -ne $retainedProjection) 'Partial hold failure omitted its canonical retained-state projection.'
    Assert-Equal $retainedProjectionSha (Get-TestValueSha256 $retainedProjection) 'Partial hold projection digest was not independently bound.'
    Assert-Equal @($retainedProjection.assemblies).Count 3 'Partial hold projection omitted an assembly path pair.'
    Assert-Equal ([string]$retainedProjection.venv.original.path) ([IO.Path]::GetFullPath($partialVenv)) 'Partial hold projection original venv path drifted.'
    Assert-False ([bool]$retainedProjection.venv.original.present) 'Partial hold projection reported the moved original venv as present.'
    Assert-True ($null -eq $retainedProjection.venv.original.sha256) 'Partial hold projection hashed an absent original venv.'
    Assert-Equal ([string]$retainedProjection.venv.held.path) ([IO.Path]::GetFullPath((Join-Path $retainedHoldPath 'venv'))) 'Partial hold projection held venv path drifted.'
    Assert-True ([bool]$retainedProjection.venv.held.present) 'Partial hold projection omitted the held venv.'
    Assert-Equal ([string]$retainedProjection.venv.held.sha256) (Get-TestValueSha256 @($retainedProjection.venv.held.files)) 'Partial hold projection held venv tree digest drifted.'
    foreach ($file in @($retainedProjection.venv.held.files)) {
        $heldFilePath = Join-Path ([string]$retainedProjection.venv.held.path) ([string]$file.relative_path)
        Assert-Equal ([string]$file.sha256) (Get-TestSha256 $heldFilePath) 'Partial hold projection held venv file hash drifted.'
        Assert-Equal ([long]$file.size) ([long](Get-Item -LiteralPath $heldFilePath).Length) 'Partial hold projection held venv file size drifted.'
    }
    foreach ($assembly in @($retainedProjection.assemblies)) {
        $expectedOriginal = [IO.Path]::GetFullPath((Join-Path $partialPlugin "$($assembly.tfm)\Rook.rhp"))
        $expectedHeld = "$expectedOriginal.contained.$partialIdentity.$partialRun"
        Assert-Equal ([string]$assembly.original.path) $expectedOriginal "Partial hold $($assembly.tfm) original assembly path drifted."
        Assert-Equal ([string]$assembly.held.path) $expectedHeld "Partial hold $($assembly.tfm) held assembly path drifted."
        foreach ($stateCase in @([ordered]@{record=$assembly.original;path=$expectedOriginal},[ordered]@{record=$assembly.held;path=$expectedHeld})) {
            $present = Test-Path -LiteralPath $stateCase.path -PathType Leaf
            Assert-Equal ([bool]$stateCase.record.present) $present "Partial hold $($assembly.tfm) assembly presence drifted."
            Assert-Equal @($stateCase.record.files).Count 0 "Partial hold $($assembly.tfm) file state retained a directory inventory."
            if ($present) {
                Assert-Equal ([string]$stateCase.record.sha256) (Get-TestSha256 $stateCase.path) "Partial hold $($assembly.tfm) assembly hash drifted."
                Assert-Equal ([long]$stateCase.record.size) ([long](Get-Item -LiteralPath $stateCase.path).Length) "Partial hold $($assembly.tfm) assembly size drifted."
            }
            else {
                Assert-True ($null -eq $stateCase.record.sha256 -and $null -eq $stateCase.record.size) "Partial hold $($assembly.tfm) absent assembly retained hash/size."
            }
        }
    }
    $net8HeldPath = (Join-Path $partialPlugin 'net8.0\Rook.rhp') + ".contained.$partialIdentity.$partialRun"
    $freshProjection = Get-ContainmentPartialHoldProjection -CandidateIdentitySha256 $partialIdentity -RunId $partialRun -HoldRoot $retainedHoldPath -VenvPath $partialVenv -PluginRoot $partialPlugin
    Assert-Equal (Get-TestValueSha256 $freshProjection) $retainedProjectionSha 'Partial hold projection did not match retained disk state.'
    [IO.File]::AppendAllText($net8HeldPath,'tampered-after-projection',[Text.UTF8Encoding]::new($false))
    $tamperedProjection = Get-ContainmentPartialHoldProjection -CandidateIdentitySha256 $partialIdentity -RunId $partialRun -HoldRoot $retainedHoldPath -VenvPath $partialVenv -PluginRoot $partialPlugin
    Assert-False ((Get-TestValueSha256 $tamperedProjection) -ceq $retainedProjectionSha) 'Partial hold projection digest did not bind retained-byte tampering.'

    $receiptLocal = New-TestDirectory $Root 'receipt-local'
    $receiptAppData = New-TestDirectory $Root 'receipt-appdata'
    $receiptHome = New-TestDirectory $Root 'receipt-home'
    $receiptRuntime = New-TestDirectory $receiptLocal 'Rook'
    $receiptVenv = New-TestDirectory $receiptRuntime 'venv'
    Write-TestAscii (Join-Path $receiptVenv 'runtime.bin') 'receipt-venv'
    $receiptPlugin = New-TestDirectory (New-TestDirectory (New-TestDirectory (New-TestDirectory $receiptAppData 'McNeel') 'Rhinoceros') '8.0') 'Plug-ins'
    $receiptPlugin = New-TestDirectory $receiptPlugin 'RookNative'
    foreach ($tfm in @('net8.0','net7.0','net48')) {
        $dir = New-TestDirectory $receiptPlugin $tfm
        Write-TestAscii (Join-Path $dir 'Rook.rhp') "receipt-$tfm"
    }
    $receiptProjection = Get-ContainmentStartupSurfaceProjection -LocalAppDataRoot $receiptLocal -AppDataRoot $receiptAppData -HomeRoot $receiptHome -RegistryFileName (Join-Path $receiptPlugin 'net8.0\Rook.rhp')
    $savedHoldVerifier = (Get-Item -LiteralPath Function:\Test-ContainmentDurableHold).ScriptBlock
    $receiptFailure = $null
    try {
        Set-Item Function:\Test-ContainmentDurableHold -Value { param($ReceiptPath,$SidecarPath); return [ordered]@{success=$false} }
        try {
            [void](Enter-ContainmentDurableHold -CandidateIdentitySha256 ('6'*64) -RunId ('7'*32) -LocalAppDataRoot $receiptLocal -AppDataRoot $receiptAppData -HomeRoot $receiptHome -StartupProjection $receiptProjection -FinalQuietResweep ([ordered]@{quiet=$true}) -FinalQuietResweepAction { [ordered]@{quiet=$true} })
        }
        catch { $receiptFailure = $_ }
    }
    finally { Set-Item Function:\Test-ContainmentDurableHold -Value $savedHoldVerifier }
    Assert-True ($null -ne $receiptFailure) 'Forced receipt-verification failure unexpectedly succeeded.'
    $publishedReceiptPath = [string]$receiptFailure.Exception.Data['ContainmentHoldReceiptPath']
    $publishedSidecarPath = [string]$receiptFailure.Exception.Data['ContainmentHoldReceiptSidecarPath']
    Assert-True (Test-Path -LiteralPath $publishedReceiptPath -PathType Leaf) 'Receipt-verification failure lost the published receipt.'
    Assert-True (Test-Path -LiteralPath $publishedSidecarPath -PathType Leaf) 'Receipt-verification failure lost the published sidecar.'
    Assert-Equal ([string]$receiptFailure.Exception.Data['ContainmentHoldReceiptSha256']) (Get-TestSha256 $publishedReceiptPath) 'Receipt-verification failure did not preserve the actual receipt hash.'
    Assert-Equal ([string]$receiptFailure.Exception.Data['ContainmentHoldReceiptSidecarSha256']) (Get-TestSha256 $publishedSidecarPath) 'Receipt-verification failure did not preserve the actual sidecar hash.'
    Assert-Equal ([string]$receiptFailure.Exception.Data['ContainmentHoldProjectionSha256']) (Get-TestValueSha256 $receiptFailure.Exception.Data['ContainmentHoldProjection']) 'Receipt-verification failure did not bind its retained-state projection.'
}

function Test-AcceptanceFailureAndReadOnlyVerification {
    param([string]$Root)
    $evidence = New-TestDirectory $Root 'acceptance-evidence'
    $marker = Join-Path $evidence '.containment-run-owner.json'
    Write-TestUtf8NoBom $marker (ConvertTo-TestCanonicalJson ([ordered]@{schema_version=1;run_id=('a'*32)}))
    $diagnostic = Join-Path $evidence 'diagnostic.txt'
    Write-TestAscii $diagnostic 'diagnostic'
    $candidateRoot = New-TestDirectory $Root 'acceptance-candidate'
    $installerPath = Join-Path $candidateRoot 'installer.exe'
    Write-TestAscii $installerPath 'immutable-installer'
    $identityPath = Join-Path $candidateRoot 'containment-candidate.json'
    Write-TestUtf8NoBom $identityPath (ConvertTo-TestCanonicalJson ([ordered]@{schema_version=1;non_publishable=$true}))
    $identityHash = Get-TestSha256 $identityPath
    $identitySidecar = Join-Path $candidateRoot 'containment-candidate.sha256'
    Write-TestAscii $identitySidecar "$identityHash  containment-candidate.json`n"
    $pythonPath = Join-Path $candidateRoot 'python.exe'
    Copy-Item -LiteralPath $WindowsPowerShell -Destination $pythonPath
    $candidate = [ordered]@{
        identity_path=$identityPath;identity_sha256=$identityHash
        sidecar_path=$identitySidecar;sidecar_sha256=(Get-TestSha256 $identitySidecar)
        installer_path=$installerPath;installer_sha256=(Get-TestSha256 $installerPath)
        rook_sha=('4'*40);chirp_sha=('5'*40)
    }
    $runtime = [ordered]@{python_executable=$pythonPath;python_sha256=(Get-TestSha256 $pythonPath);install_root='C:\Rook\app';processes=@()}
    $record = New-ContainmentAcceptanceRecord -RunId ('a'*32) -StartedUtc '2026-07-17T00:00:00.000000Z' -Candidate $candidate -InstalledRuntime $runtime -Quiescence ([ordered]@{preflight_quiet=$true;final_quiet=$true;records=@()}) -StartupIsolation ([ordered]@{control_fired=$true;installed_sanitized=$true;installer_sanitized=$true;external_hits_absent=$true;PYTHONUSERBASE_absent=$true;PYTHONNOUSERSITE='1';probe_hashes=@()}) -Discovery ([ordered]@{default=422;full=422;lean=20;readonly=148;interactive_full=425;contained_names_absent=$true}) -TransportRecords (0..35 | ForEach-Object { [ordered]@{index=$_;valid=$true} }) -InternalRecords (0..163 | ForEach-Object { [ordered]@{index=$_;valid=$true} }) -Scenarios ([ordered]@{rhino=[ordered]@{success=$true;restoration_verified=$true;telemetry_delta=0};grasshopper=[ordered]@{success=$true;restoration_verified=$true;telemetry_delta=0}}) -Diagnostics @([ordered]@{relative_path='diagnostic.txt';sha256=(Get-TestSha256 $diagnostic);size=(Get-Item $diagnostic).Length}) -PostRunArtifactSnapshot ([ordered]@{verified=$true;sha256=('7'*64)})
    $acceptancePath = Join-Path $evidence 'containment-acceptance.json'
    $sidecarPath = Join-Path $evidence 'containment-acceptance.sha256'
    $beforeInMemoryProof = Get-TreeIdentity -Root $evidence
    $inMemory = Read-AndValidateContainmentAcceptance -EvidenceDirectory $evidence -Record $record
    Assert-True $inMemory.success 'In-memory pre-publication acceptance proof rejected a valid record.'
    Assert-False (Test-Path $acceptancePath) 'In-memory pre-publication proof wrote acceptance JSON.'
    Assert-False (Test-Path $sidecarPath) 'In-memory pre-publication proof wrote an acceptance sidecar.'
    Assert-Equal (Get-TreeIdentity -Root $evidence).sha256 $beforeInMemoryProof.sha256 'In-memory pre-publication proof mutated evidence.'
    $acceptanceTypeCases = @(
        [ordered]@{label='schema_version';mutate={param($value) $value.schema_version = '1'}},
        [ordered]@{label='success';mutate={param($value) $value.success = 'false'}},
        [ordered]@{label='validator_result.success';mutate={param($value) $value.validator_result.success = 'false'}},
        [ordered]@{label='containment_hold.activated';mutate={param($value) $value.containment_hold.activated = 0}},
        [ordered]@{label='restoration_verified';mutate={param($value) $value.restoration_verified = 'false'}},
        [ordered]@{label='quiescence.preflight_quiet';mutate={param($value) $value.quiescence.preflight_quiet = 'false'}},
        [ordered]@{label='quiescence.final_quiet';mutate={param($value) $value.quiescence.final_quiet = 'false'}},
        [ordered]@{label='startup_isolation.control_fired';mutate={param($value) $value.startup_isolation.control_fired = 'false'}},
        [ordered]@{label='startup_isolation.installed_sanitized';mutate={param($value) $value.startup_isolation.installed_sanitized = 'false'}},
        [ordered]@{label='startup_isolation.installer_sanitized';mutate={param($value) $value.startup_isolation.installer_sanitized = 'false'}},
        [ordered]@{label='startup_isolation.external_hits_absent';mutate={param($value) $value.startup_isolation.external_hits_absent = 'false'}},
        [ordered]@{label='startup_isolation.PYTHONUSERBASE_absent';mutate={param($value) $value.startup_isolation.PYTHONUSERBASE_absent = 'false'}},
        [ordered]@{label='startup_isolation.PYTHONNOUSERSITE';mutate={param($value) $value.startup_isolation.PYTHONNOUSERSITE = 1}},
        [ordered]@{label='discovery.default';mutate={param($value) $value.discovery.default = '422'}},
        [ordered]@{label='discovery.contained_names_absent';mutate={param($value) $value.discovery.contained_names_absent = 'false'}},
        [ordered]@{label='transport.count';mutate={param($value) $value.transport.count = '36'}},
        [ordered]@{label='internal.count';mutate={param($value) $value.internal.count = '164'}},
        [ordered]@{label='scenarios.rhino.success';mutate={param($value) $value.scenarios.rhino.success = 'false'}},
        [ordered]@{label='scenarios.grasshopper.restoration_verified';mutate={param($value) $value.scenarios.grasshopper.restoration_verified = 'false'}},
        [ordered]@{label='scenarios.rhino.telemetry_delta';mutate={param($value) $value.scenarios.rhino.telemetry_delta = '0'}},
        [ordered]@{label='post_run_artifact_snapshot.verified';mutate={param($value) $value.post_run_artifact_snapshot.verified = 'false'}},
        [ordered]@{label='diagnostics[0].size';mutate={param($value) $value.diagnostics[0].size = [string]$value.diagnostics[0].size}}
    )
    foreach ($case in $acceptanceTypeCases) {
        $typedAcceptance = $record | ConvertTo-Json -Depth 100 | ConvertFrom-Json
        $mutate = $case.mutate
        & $mutate $typedAcceptance
        $null = Write-CanonicalJsonPair -Path $acceptancePath -SidecarPath $sidecarPath -Value $typedAcceptance
        try {
            Assert-ThrowsLike {
                Read-AndValidateContainmentAcceptance -EvidenceDirectory $evidence
            } 'acceptance|success|restoration|quiescence|type|scenario|count|environment|discovery|snapshot|hold|diagnostic' "String-coercible retained acceptance $($case.label) was accepted."
        }
        finally {
            Remove-Item -LiteralPath $acceptancePath,$sidecarPath -Force -ErrorAction SilentlyContinue
        }
    }
    Write-CanonicalJsonPair -Path $acceptancePath -SidecarPath $sidecarPath -Value $record
    $before = Get-TreeIdentity -Root $evidence
    $verified = Read-AndValidateContainmentAcceptance -EvidenceDirectory $evidence
    Assert-True $verified.success 'Read-only evidence verification rejected a valid record.'
    $after = Get-TreeIdentity -Root $evidence
    Assert-Equal $after.sha256 $before.sha256 'Read-only evidence verification mutated evidence.'
    Assert-ThrowsLike {
        Read-AndValidateContainmentAcceptance -EvidenceDirectory $evidence -RequireNormalEvidence
    } 'normal|snapshot' 'Strict normal-evidence verification accepted shallow unit evidence.'
    $savedMode = [ordered]@{
        ArtifactDirectory=$ArtifactDirectory;CandidateIdentityPath=$CandidateIdentityPath
        CandidateSidecarPath=$CandidateSidecarPath;EvidenceDirectory=$EvidenceDirectory
        RhinoExe=$RhinoExe;VerifyEvidenceOnly=$VerifyEvidenceOnly
    }
    try {
        $ArtifactDirectory=$null; $CandidateIdentityPath=$null; $CandidateSidecarPath=$null
        $RhinoExe=$null; $EvidenceDirectory=$evidence; $VerifyEvidenceOnly=$true
        $beforeMode = Get-TreeIdentity -Root $evidence
        Assert-ThrowsLike { Invoke-ContainmentCandidateValidator } 'normal|snapshot' 'VerifyEvidenceOnly accepted shallow unit evidence.'
        Assert-Equal (Get-TreeIdentity -Root $evidence).sha256 $beforeMode.sha256 'VerifyEvidenceOnly mutated retained evidence.'
    }
    finally {
        $ArtifactDirectory=$savedMode.ArtifactDirectory; $CandidateIdentityPath=$savedMode.CandidateIdentityPath
        $CandidateSidecarPath=$savedMode.CandidateSidecarPath; $EvidenceDirectory=$savedMode.EvidenceDirectory
        $RhinoExe=$savedMode.RhinoExe; $VerifyEvidenceOnly=$savedMode.VerifyEvidenceOnly
    }
    Write-TestAscii $diagnostic 'drift'
    Assert-ThrowsLike { Read-AndValidateContainmentAcceptance -EvidenceDirectory $evidence } 'diagnostic|artifact|hash' 'Mutable acceptance evidence was accepted.'

    $failureEvidence = New-TestDirectory $Root 'failure-evidence'
    Write-ContainmentFailureEvidence -EvidenceDirectory $failureEvidence -RunId ('b'*32) -StartedUtc '2026-07-17T00:00:00.000000Z' -FailureStage 'installed-certification' -Message 'fake failure' -InstallerStarted -DurableHold ([ordered]@{success=$true;path='C:\hold';sha256=('8'*64)}) -Diagnostics @()
    Assert-True (Test-Path (Join-Path $failureEvidence 'containment-failure.json')) 'Failure evidence was not written.'
    Assert-False (Test-Path (Join-Path $failureEvidence 'containment-acceptance.json')) 'Failure path wrote acceptance.'
    Assert-ThrowsLike { Read-AndValidateContainmentAcceptance -EvidenceDirectory $failureEvidence } 'failure|acceptance|success' 'Failure diagnostic was accepted as success.'

    $partialRoot = New-TestDirectory $Root 'partial-pair'
    $partialJson = Join-Path $partialRoot 'pair.json'
    $missingSidecarParent = Join-Path $partialRoot 'missing\pair.sha256'
    Assert-ThrowsLike {
        Write-CanonicalJsonPair -Path $partialJson -SidecarPath $missingSidecarParent -Value ([ordered]@{success=$true})
    } 'missing|path|directory|part' 'Partial evidence-pair write unexpectedly succeeded.'
    Assert-False (Test-Path $partialJson) 'Failed evidence-pair publication left success JSON behind.'

    $foreignJson = Join-Path $partialRoot 'preexisting.json'
    Write-TestAscii $foreignJson 'foreign-owned-bytes'
    Assert-ThrowsLike {
        Write-CanonicalJsonPair -Path $foreignJson -SidecarPath (Join-Path $partialRoot 'preexisting.sha256') -Value ([ordered]@{success=$true})
    } 'already exists' 'Pre-existing evidence path was accepted.'
    Assert-Equal (Get-Content -LiteralPath $foreignJson -Raw) 'foreign-owned-bytes' 'Collision cleanup removed or changed a path the writer did not create.'
}

function Invoke-FakeNormalModeCase {
    param(
        [string]$Root,
        [ValidateSet(
            'success','failed-preflight','failed-preflight-cleanup-nonquiet','failed-install','wrong-installed-origin',
            'task7-discovery-leak','task7-denial-mismatch','task7-telemetry-mismatch','task7-child-replacement',
            'live-target-state-drift','live-failure','live-uncertain-ownership','live-unverified-restoration','live-cleanup-failure',
            'cleanup-failure','hold-receipt-failure','post-run-drift','acceptance-self-check','acceptance-self-check-replacement'
        )][string]$Fault
    )

    $caseRoot = New-TestDirectory $Root $Fault
    $artifact = New-TestDirectory $caseRoot 'artifact'
    $identityPath = Join-Path $artifact 'containment-candidate.json'
    $identitySidecar = Join-Path $artifact 'containment-candidate.sha256'
    $installerPath = Join-Path $artifact 'candidate-installer.exe'
    $privatePython = Join-Path $artifact 'private-python.exe'
    $preflightPath = Join-Path $artifact 'rook_process_preflight.ps1'
    foreach ($entry in @(
        [ordered]@{path=$identityPath;text='identity'},
        [ordered]@{path=$identitySidecar;text='sidecar'},
        [ordered]@{path=$installerPath;text='installer'},
        [ordered]@{path=$privatePython;text='python'},
        [ordered]@{path=$preflightPath;text='preflight'}
    )) { Write-TestAscii $entry.path $entry.text }
    $rookRoot = New-TestDirectory $caseRoot 'rook-source'
    $chirpRoot = New-TestDirectory $caseRoot 'chirp-source'
    $pluginRoot = New-TestDirectory $caseRoot 'plugin-root'
    $installRoot = New-TestDirectory $caseRoot 'installed-app'
    $dataRoot = New-TestDirectory $caseRoot 'installed-data'
    $dspyCache = New-TestDirectory $dataRoot 'dspy-cache'
    $candidate = [ordered]@{
        artifact_directory=$artifact
        identity_path=$identityPath;identity_sha256=('1'*64)
        sidecar_path=$identitySidecar;sidecar_sha256=('2'*64)
        installer_path=$installerPath;installer_sha256=('3'*64)
        private_python_path=$privatePython;private_python_sha256=(Get-TestSha256 $privatePython)
        record=[ordered]@{
            private_python=[ordered]@{sha256=(Get-TestSha256 $privatePython)}
            sources=[ordered]@{
                rook=[ordered]@{sha=('4'*40);root=$rookRoot;stage_path=$rookRoot}
                chirp=[ordered]@{sha=('5'*40);root=$chirpRoot;stage_path=$chirpRoot}
            }
        }
    }
    $postCandidate = [ordered]@{}
    foreach ($key in $candidate.Keys) { $postCandidate[$key] = $candidate[$key] }
    if ($Fault -eq 'post-run-drift') { $postCandidate.identity_sha256 = '9' * 64 }
    $installed = [ordered]@{
        python_executable=$privatePython;python_sha256=(Get-TestSha256 $privatePython)
        install_root=$installRoot;data_root=$dataRoot;dspy_cache=$dspyCache;chirp_home=$null
        plugin_root=$pluginRoot;processes=@()
    }
    $state = [pscustomobject]@{
        fault=$Fault;candidate_reads=0;installer_started=$false
        preflight_labels=(New-Object Collections.Generic.List[string])
        task7_reached=$false;live_reached=$false;acceptance_written=$false
        failure_written=$false;failure_stage=$null;hold_attempted=$false;hold_record=$null
        final_cleanup_fault_fired=$false;acceptance_pair=$null
    }
    $savedFunctions = @{}
    $functionNames = @(
        'Read-AndValidateCandidateIdentity','Get-CandidateArtifactSnapshot','Test-PythonStartupIsolation',
        'Get-ContainmentCompanionRegistryFileName','Get-ContainmentStartupSurfaceProjection','Assert-ContainmentStartupProjection',
        'Resolve-ContainmentOwnedRelativePath','Invoke-ContainmentProcessPreflight','New-ContainmentInstallerTripwire',
        'Invoke-ContainmentCandidateInstallation','Assert-ContainmentInstalledRuntime','Invoke-ContainmentTask7Certification',
        'Invoke-ContainmentLiveScenarios','Get-ContainmentDiagnosticProjection','New-ContainmentAcceptanceRecord',
        'Read-AndValidateContainmentAcceptance','Write-CanonicalJsonPair','Enter-ContainmentDurableHold',
        'Write-ContainmentFailureEvidence'
    )
    foreach ($name in $functionNames) { $savedFunctions[$name] = (Get-Item -LiteralPath "Function:\$name").ScriptBlock }

    $savedEnvironment = [ordered]@{
        LOCALAPPDATA=$env:LOCALAPPDATA;APPDATA=$env:APPDATA;USERPROFILE=$env:USERPROFILE
    }
    $localRoot = New-TestDirectory $caseRoot 'localappdata'
    $appDataRoot = New-TestDirectory $caseRoot 'appdata'
    $homeRoot = New-TestDirectory $caseRoot 'home'
    [void](New-TestDirectory $localRoot 'Rook')
    $evidenceParent = New-TestDirectory $caseRoot 'evidence-parent'
    $evidencePath = Join-Path $evidenceParent 'run'

    try {
        $env:LOCALAPPDATA=$localRoot; $env:APPDATA=$appDataRoot; $env:USERPROFILE=$homeRoot

        Set-Item Function:\Read-AndValidateCandidateIdentity -Value ({
            param($ArtifactDirectory,$CandidateIdentityPath,$CandidateSidecarPath,[switch]$ValidateSourceRepositories)
            $state.candidate_reads++
            if ($state.candidate_reads -ge 2) { return $postCandidate }
            return $candidate
        }.GetNewClosure())
        Set-Item Function:\Get-CandidateArtifactSnapshot -Value ({
            param($Candidate)
            return [ordered]@{sha256=[string]$Candidate.identity_sha256;installer_sha256=[string]$Candidate.installer_sha256}
        }.GetNewClosure())
        Set-Item Function:\Test-PythonStartupIsolation -Value ({
            param($PythonPath,$EvidenceRoot,$InstallRoot,$DataRoot,$ExpectedVersion)
            return [ordered]@{control_fired=$true;sanitized=$true;probe_hashes=@('a'*64)}
        }.GetNewClosure())
        Set-Item Function:\Get-ContainmentCompanionRegistryFileName -Value ({ param($AppDataRoot); return (Join-Path $pluginRoot 'net8.0\Rook.rhp') }.GetNewClosure())
        Set-Item Function:\Get-ContainmentStartupSurfaceProjection -Value ({
            param($LocalAppDataRoot,$AppDataRoot,$HomeRoot,$RegistryFileName)
            return [ordered]@{plugin_root=$pluginRoot;valid=$true;records=@()}
        }.GetNewClosure())
        Set-Item Function:\Assert-ContainmentStartupProjection -Value ({ param($Projection,$ExpectedVenvPath,$ExpectedPluginRoot); return $true }.GetNewClosure())
        Set-Item Function:\Resolve-ContainmentOwnedRelativePath -Value ({ param($Root,$RelativePath,$Kind,$Label); return $preflightPath }.GetNewClosure())
        Set-Item Function:\Invoke-ContainmentProcessPreflight -Value ({
            param($Mode,$PreflightScript,$RookRoot,$EvidenceDirectory,$Label)
            $state.preflight_labels.Add([string]$Label)
            if ($state.fault -eq 'cleanup-failure' -and $Label -ceq 'final close' -and -not $state.final_cleanup_fault_fired) {
                $state.final_cleanup_fault_fired=$true
                throw 'injected cleanup failure after green checks'
            }
            if ($state.fault -in @('failed-preflight','failed-preflight-cleanup-nonquiet') -and $Label -ceq 'preinstall quiet resweep') {
                return [ordered]@{quiet=$false;records=@([ordered]@{process_id=99})}
            }
            if ($state.fault -eq 'failed-preflight-cleanup-nonquiet' -and $Label -ceq 'failed-run quiet resweep') {
                return [ordered]@{quiet=$false;records=@([ordered]@{process_id=100})}
            }
            $stale = if ($Label -ceq 'preinstall close') { @([ordered]@{process_id=77;owned=$true;stopped=$true}) } else { @() }
            return [ordered]@{quiet=$true;records=$stale}
        }.GetNewClosure())
        Set-Item Function:\New-ContainmentInstallerTripwire -Value ({ param($PythonPath,$EvidenceDirectory); return [ordered]@{path=(Join-Path $EvidenceDirectory 'tripwire')} }.GetNewClosure())
        Set-Item Function:\Invoke-ContainmentCandidateInstallation -Value ({
            param($Candidate,$Tripwire,$DiagnosticDirectory,$StartedUtc,$OnInstallerStarted)
            & $OnInstallerStarted 4242
            $state.installer_started=$true
            if ($state.fault -eq 'failed-install') { throw 'injected failed install' }
            return [ordered]@{external_hits_absent=$true;installer_process_id=4242}
        }.GetNewClosure())
        Set-Item Function:\Assert-ContainmentInstalledRuntime -Value ({
            param($Candidate,$LocalAppDataRoot,$AppDataRoot,$InstallStartedUtc,$DiagnosticDirectory)
            if ($state.fault -eq 'wrong-installed-origin') { throw 'injected wrong installed origin' }
            return $installed
        }.GetNewClosure())
        Set-Item Function:\Invoke-ContainmentTask7Certification -Value ({
            param($EvidenceDirectory,$InstalledPython,$InstallRoot,$DataRoot,$DspyCache,$ChirpHome,$ForbiddenSourceRoots)
            $state.task7_reached=$true
            $messages = @{
                'task7-discovery-leak'='injected discovery leak'
                'task7-denial-mismatch'='injected denial mismatch'
                'task7-telemetry-mismatch'='injected telemetry mismatch'
                'task7-child-replacement'='injected child-process replacement'
            }
            if ($messages.ContainsKey($state.fault)) { throw $messages[$state.fault] }
            if ($state.fault -eq 'hold-receipt-failure') { throw 'injected primary failure before hold receipt verification' }
            return [ordered]@{discovery=[ordered]@{valid=$true};transport_records=@();internal_records=@()}
        }.GetNewClosure())
        Set-Item Function:\Invoke-ContainmentLiveScenarios -Value ({
            param($EvidenceDirectory,$InstalledPython,$InstallRoot,$DataRoot,$DspyCache,$ChirpHome,$RhinoExe)
            $state.live_reached=$true
            $messages = @{
                'live-target-state-drift'='injected target/state drift'
                'live-failure'='injected live failure'
                'live-uncertain-ownership'='injected uncertain ownership'
                'live-unverified-restoration'='injected unverified restoration'
                'live-cleanup-failure'='injected live cleanup failure'
            }
            if ($messages.ContainsKey($state.fault)) {
                $exception = [InvalidOperationException]::new([string]$messages[$state.fault])
                $labels = @{
                    'live-target-state-drift'='state_drift'
                    'live-failure'='verification_failed'
                    'live-uncertain-ownership'='ownership_ambiguous'
                    'live-unverified-restoration'='restoration_failed'
                    'live-cleanup-failure'='cleanup_failed'
                }
                $exception.Data['ContainmentFailureLabel'] = [string]$labels[$state.fault]
                throw $exception
            }
            return [ordered]@{rhino=[ordered]@{success=$true};grasshopper=[ordered]@{success=$true}}
        }.GetNewClosure())
        Set-Item Function:\Get-ContainmentDiagnosticProjection -Value ({ param($EvidenceDirectory); return @() }.GetNewClosure())
        Set-Item Function:\New-ContainmentAcceptanceRecord -Value ({
            param($RunId,$StartedUtc,$Candidate,$InstalledRuntime,$Quiescence,$StartupIsolation,$Discovery,$TransportRecords,$InternalRecords,$Scenarios,$Diagnostics,$PostRunArtifactSnapshot)
            return [ordered]@{schema_version=1;success=$true;run_id=$RunId;candidate=$Candidate}
        }.GetNewClosure())
        Set-Item Function:\Read-AndValidateContainmentAcceptance -Value ({
            param($EvidenceDirectory,[switch]$RequireNormalEvidence,[AllowNull()][object]$Record)
            if ($null -ne $Record) { return $Record }
            if ($state.fault -in @('acceptance-self-check','acceptance-self-check-replacement')) {
                if ($state.fault -eq 'acceptance-self-check-replacement') {
                    $acceptancePath = Join-Path $EvidenceDirectory 'containment-acceptance.json'
                    $ownedAway = Join-Path $caseRoot 'acceptance-owned-away.json'
                    Move-Item -LiteralPath $acceptancePath -Destination $ownedAway -ErrorAction Stop
                    Write-TestAscii -Path $acceptancePath -Text 'foreign-acceptance-replacement'
                }
                throw 'injected acceptance self-check failure'
            }
            return [ordered]@{schema_version=1;success=$true;evidence_directory=$EvidenceDirectory}
        }.GetNewClosure())
        Set-Item Function:\Write-CanonicalJsonPair -Value ({
            param($Path,$SidecarPath,$Value)
            $state.acceptance_written=$true
            if ($state.fault -in @('acceptance-self-check','acceptance-self-check-replacement')) {
                $state.acceptance_pair = & $savedFunctions['Write-CanonicalJsonPair'] -Path $Path -SidecarPath $SidecarPath -Value $Value
                return $state.acceptance_pair
            }
            return [pscustomobject]@{Path=$Path;SidecarPath=$SidecarPath;Sha256=('a'*64);SidecarSha256=('b'*64)}
        }.GetNewClosure())
        Set-Item Function:\Enter-ContainmentDurableHold -Value ({
            param($CandidateIdentitySha256,$RunId,$LocalAppDataRoot,$AppDataRoot,$HomeRoot,$StartupProjection,$FinalQuietResweep,$FinalQuietResweepAction)
            $state.hold_attempted=$true
            if ($state.fault -eq 'hold-receipt-failure') {
                $exception = [InvalidOperationException]::new('injected durable hold receipt failure')
                $holdPath = Join-Path $LocalAppDataRoot "Rook\containment-hold\$CandidateIdentitySha256\$RunId"
                [IO.Directory]::CreateDirectory($holdPath) | Out-Null
                $receiptPath = Join-Path $holdPath 'containment-hold.json'
                $sidecarPath = Join-Path $holdPath 'containment-hold.sha256'
                Write-TestAscii $receiptPath 'partial-receipt'
                Write-TestAscii $sidecarPath 'partial-sidecar'
                $projection = [ordered]@{schema_version=1;candidate_identity_sha256=$CandidateIdentitySha256;run_id=$RunId;hold_path=$holdPath;venv=[ordered]@{original=[ordered]@{present=$false};held=[ordered]@{present=$true}};assemblies=@()}
                $exception.Data['ContainmentHoldPath'] = $holdPath
                $exception.Data['ContainmentHoldProjection'] = $projection
                $exception.Data['ContainmentHoldProjectionSha256'] = Get-TestValueSha256 $projection
                $exception.Data['ContainmentHoldReceiptPath'] = $receiptPath
                $exception.Data['ContainmentHoldReceiptSha256'] = Get-TestSha256 $receiptPath
                $exception.Data['ContainmentHoldReceiptSidecarPath'] = $sidecarPath
                $exception.Data['ContainmentHoldReceiptSidecarSha256'] = Get-TestSha256 $sidecarPath
                throw $exception
            }
            return [ordered]@{success=$true;path=(Join-Path $LocalAppDataRoot 'held');sha256=('c'*64);sidecar_sha256=('d'*64)}
        }.GetNewClosure())
        Set-Item Function:\Write-ContainmentFailureEvidence -Value ({
            param($EvidenceDirectory,$RunId,$StartedUtc,$FailureStage,$Message,[switch]$InstallerStarted,$DurableHold,$Diagnostics)
            $state.failure_written=$true
            $state.failure_stage=[string]$FailureStage
            $state.hold_record=$DurableHold
            return [ordered]@{success=$false;failure_stage=$FailureStage}
        }.GetNewClosure())

        $ArtifactDirectory=$artifact
        $CandidateIdentityPath=$identityPath
        $CandidateSidecarPath=$identitySidecar
        $EvidenceDirectory=$evidencePath
        $RhinoExe=$WindowsPowerShell
        $VerifyEvidenceOnly=$false
        $caught=$null
        $result=$null
        try { $result = Invoke-ContainmentCandidateValidator } catch { $caught=$_ }
        if ($Fault -eq 'success') {
            $caughtMessage = if ($null -eq $caught) { '<none>' } else { [string]$caught.Exception.Message }
            Assert-True ($null -eq $caught) "Fake normal-mode success failed: $caughtMessage"
            Assert-True ([bool]$result.success) 'Fake normal-mode success did not return verified acceptance.'
            Assert-True $state.acceptance_written 'Fake normal-mode success did not publish acceptance.'
            Assert-False $state.failure_written 'Fake normal-mode success wrote failure evidence.'
            Assert-False $state.hold_attempted 'Fake normal-mode success activated a durable hold.'
            Assert-True (@($state.preflight_labels) -ccontains 'preinstall close') 'Fake normal-mode success did not exercise stale-process close.'
            Assert-True (@($state.preflight_labels) -ccontains 'preinstall quiet resweep') 'Fake normal-mode success omitted the preinstall quiet resweep.'
        }
        else {
            Assert-True ($null -ne $caught) "Fake normal-mode fault $Fault unexpectedly succeeded."
            $postPublicationFault = $Fault -in @('acceptance-self-check','acceptance-self-check-replacement')
            Assert-Equal ([bool]$state.acceptance_written) $postPublicationFault "Fake normal-mode fault $Fault acceptance-publication reachability drifted."
            $expectedFailureEvidence = $Fault -ne 'acceptance-self-check-replacement'
            Assert-Equal ([bool]$state.failure_written) $expectedFailureEvidence "Fake normal-mode fault $Fault failure-evidence disposition drifted."
            $expectation = switch -Exact ($Fault) {
                'failed-preflight' { [ordered]@{message='preinstall process boundary is not quiet';stage='preinstall-quiescence';task7=$false;live=$false;installer=$false} }
                'failed-preflight-cleanup-nonquiet' { [ordered]@{message='preinstall process boundary is not quiet';stage='emergency-quiescence';task7=$false;live=$false;installer=$false} }
                'failed-install' { [ordered]@{message='injected failed install';stage='installer-startup-isolation';task7=$false;live=$false;installer=$true} }
                'wrong-installed-origin' { [ordered]@{message='injected wrong installed origin';stage='installed-runtime-certification';task7=$false;live=$false;installer=$true} }
                'task7-discovery-leak' { [ordered]@{message='injected discovery leak';stage='installed-containment-certification';task7=$true;live=$false;installer=$true} }
                'task7-denial-mismatch' { [ordered]@{message='injected denial mismatch';stage='installed-containment-certification';task7=$true;live=$false;installer=$true} }
                'task7-telemetry-mismatch' { [ordered]@{message='injected telemetry mismatch';stage='installed-containment-certification';task7=$true;live=$false;installer=$true} }
                'task7-child-replacement' { [ordered]@{message='injected child-process replacement';stage='installed-containment-certification';task7=$true;live=$false;installer=$true} }
                'live-target-state-drift' { [ordered]@{message='injected target/state drift';stage='authorized-live-scenarios';task7=$true;live=$true;installer=$true} }
                'live-failure' { [ordered]@{message='injected live failure';stage='authorized-live-scenarios';task7=$true;live=$true;installer=$true} }
                'live-uncertain-ownership' { [ordered]@{message='injected uncertain ownership';stage='emergency-quiescence';task7=$true;live=$true;installer=$true} }
                'live-unverified-restoration' { [ordered]@{message='injected unverified restoration';stage='emergency-quiescence';task7=$true;live=$true;installer=$true} }
                'live-cleanup-failure' { [ordered]@{message='injected live cleanup failure';stage='emergency-quiescence';task7=$true;live=$true;installer=$true} }
                'cleanup-failure' { [ordered]@{message='injected cleanup failure after green checks';stage='emergency-quiescence';task7=$true;live=$true;installer=$true} }
                'hold-receipt-failure' { [ordered]@{message='injected primary failure before hold receipt verification';stage='emergency-quiescence';task7=$true;live=$false;installer=$true} }
                'post-run-drift' { [ordered]@{message='candidate artifact drifted during installed/live acceptance';stage='post-run-candidate-rehash';task7=$true;live=$true;installer=$true} }
                'acceptance-self-check' { [ordered]@{message='injected acceptance self-check failure';stage='acceptance-write';task7=$true;live=$true;installer=$true} }
                'acceptance-self-check-replacement' { [ordered]@{message='injected acceptance self-check failure';stage='acceptance-write';task7=$true;live=$true;installer=$true} }
                default { throw "Missing fake normal-mode expectation for $Fault" }
            }
            Assert-Contains ([string]$caught.Exception.Message) ([string]$expectation.message) "Fake normal-mode fault $Fault failed for the wrong reason."
            if ($expectedFailureEvidence) {
                Assert-Equal ([string]$state.failure_stage) ([string]$expectation.stage) "Fake normal-mode fault $Fault recorded the wrong failure stage."
            }
            else {
                Assert-Equal ([string]$state.failure_stage) '' "Fake normal-mode fault $Fault recorded contradictory failure evidence."
                Assert-Contains ([string]$caught.Exception.Message) ([string]$expectation.stage) "Fake normal-mode fault $Fault lost its failure-stage context."
            }
            Assert-Equal ([bool]$state.task7_reached) ([bool]$expectation.task7) "Fake normal-mode fault $Fault Task 7 reachability drifted."
            Assert-Equal ([bool]$state.live_reached) ([bool]$expectation.live) "Fake normal-mode fault $Fault live reachability drifted."
            Assert-Equal ([bool]$state.installer_started) ([bool]$expectation.installer) "Fake normal-mode fault $Fault installer reachability drifted."
            $expectedHold = [bool]$expectation.installer
            Assert-Equal $state.hold_attempted $expectedHold "Fake normal-mode fault $Fault durable-hold dispatch drifted."
            if ($Fault -eq 'hold-receipt-failure') {
                Assert-False ([bool]$state.hold_record.success) 'Hold receipt failure was recorded as a successful hold.'
                Assert-True ([IO.Path]::IsPathRooted([string]$state.hold_record.path)) 'Hold receipt failure lost its deterministic partial hold path.'
                Assert-Equal ([string]$state.hold_record.projection_sha256) (Get-TestValueSha256 $state.hold_record.projection) 'Hold receipt failure did not bind its retained-state projection.'
                Assert-Equal ([string]$state.hold_record.sha256) (Get-TestSha256 $state.hold_record.receipt_path) 'Hold receipt failure lost the existing receipt hash.'
                Assert-Equal ([string]$state.hold_record.sidecar_sha256) (Get-TestSha256 $state.hold_record.receipt_sidecar_path) 'Hold receipt failure lost the existing sidecar hash.'
            }
            if ($Fault -eq 'acceptance-self-check') {
                Assert-False (Test-Path -LiteralPath (Join-Path $evidencePath 'containment-acceptance.json')) 'Acceptance self-check rollback left JSON behind.'
                Assert-False (Test-Path -LiteralPath (Join-Path $evidencePath 'containment-acceptance.sha256')) 'Acceptance self-check rollback left sidecar behind.'
            }
            if ($Fault -eq 'acceptance-self-check-replacement') {
                $foreignAcceptance = Join-Path $evidencePath 'containment-acceptance.json'
                Assert-Equal ([IO.File]::ReadAllText($foreignAcceptance)) 'foreign-acceptance-replacement' 'Acceptance self-check rollback changed or removed the foreign JSON replacement.'
                Assert-False (Test-Path -LiteralPath (Join-Path $evidencePath 'containment-acceptance.sha256')) 'Acceptance replacement rollback left its owned sidecar behind.'
                Assert-True (Test-Path -LiteralPath (Join-Path $caseRoot 'acceptance-owned-away.json') -PathType Leaf) 'Acceptance replacement fixture lost the originally published JSON.'
                Assert-Contains ([string]$caught.Exception.Message) 'cleanup' 'Acceptance replacement failure did not surface incomplete cleanup.'
            }
        }
        return $state
    }
    finally {
        foreach ($name in $functionNames) { Set-Item -LiteralPath "Function:\$name" -Value $savedFunctions[$name] }
        $env:LOCALAPPDATA=$savedEnvironment.LOCALAPPDATA
        $env:APPDATA=$savedEnvironment.APPDATA
        $env:USERPROFILE=$savedEnvironment.USERPROFILE
    }
}

function Test-FakeNormalModeOrchestrationMatrix {
    param([string]$Root)

    $faults = @(
        'success','failed-preflight','failed-preflight-cleanup-nonquiet','failed-install','wrong-installed-origin',
        'task7-discovery-leak','task7-denial-mismatch','task7-telemetry-mismatch','task7-child-replacement',
        'live-target-state-drift','live-failure','live-uncertain-ownership','live-unverified-restoration','live-cleanup-failure',
        'cleanup-failure','hold-receipt-failure','post-run-drift'
        ,'acceptance-self-check','acceptance-self-check-replacement'
    )
    foreach ($fault in $faults) {
        [void](Invoke-FakeNormalModeCase -Root $Root -Fault $fault)
    }
}

function Test-FailFastStageAndFrozenWiring {
    param([string]$Root)
    $reached = Join-Path $Root 'next-stage.txt'
    Assert-ThrowsLike {
        Invoke-ContainmentStageSequence -Stages @(
            [ordered]@{name='injected-error';body={ Write-Error 'injected normally nonterminating cmdlet error' }},
            [ordered]@{name='must-not-run';body={ Write-TestAscii $reached 'reached' }}
        )
    } 'injected normally nonterminating' 'Normally nonterminating error did not stop the validator.'
    Assert-False (Test-Path $reached) 'Validator reached a stage after Write-Error.'
    $installer = Get-Content -LiteralPath (Join-Path $RepoRoot 'installer\RookSetup.iss') -Raw
    $postInstall = Get-Content -LiteralPath (Join-Path $RepoRoot 'installer\post_install.py') -Raw
    foreach ($needle in @('{localappdata}\Rook\venv','{#CompanionNet8Dir}\Rook.rhp','{#CompanionNet7Dir}\Rook.rhp','{#CompanionNet48Dir}\Rook.rhp','RookChatService.json')) { Assert-Contains $installer $needle 'Installer startup/hold wiring drifted.' }
    foreach ($needle in @('runtime_root / "venv"','RookChatService.json','MANAGED_COMPANION_RUNTIMES')) { Assert-Contains $postInstall $needle 'Post-install startup/hold wiring drifted.' }
}

$runRoot = Join-Path $env:TEMP ("rook-t10-validator-tests-" + [guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($runRoot) | Out-Null
$started = [Diagnostics.Stopwatch]::StartNew()
try {
    Invoke-Test 'static PS5.1, parameter, and process-boundary contract' { Test-StaticContract }
    Invoke-Test 'CreateNew publication and claim failure cleanup' { Test-CreateNewPublicationFailureCleanup -Root (New-TestDirectory $runRoot 'publication-cleanup') }
    Invoke-Test 'low-level cleanup rejects a foreign pathname replacement' { Test-LowLevelIdentityBoundReplacementCleanup -Root (New-TestDirectory $runRoot 'low-level-replacement') }
    Invoke-Test 'final-pair rollback rejects a foreign pathname replacement' { Test-PairIdentityBoundReplacementCleanup -Root (New-TestDirectory $runRoot 'pair-replacement') }
    Invoke-Test 'new evidence claim rejects a post-publication foreign child' { Test-NewEvidenceClaimForeignChildGap -Root (New-TestDirectory $runRoot 'new-claim-gap') }
    Invoke-Test 'new evidence claim preserves an empty foreign directory replacement' { Test-NewEvidenceClaimEmptyDirectoryReplacement -Root (New-TestDirectory $runRoot 'new-claim-directory-replacement') }
    Invoke-Test 'existing evidence claim rejects an owner-marker replacement' { Test-ExistingEvidenceClaimMarkerReplacement -Root (New-TestDirectory $runRoot 'existing-claim-replacement') }
    Invoke-Test 'Windows quoting and unique working directory' { Test-ProcessQuotingAndWorkingDirectory -Root (New-TestDirectory $runRoot 'quoting') }
    Invoke-Test 'concurrent stdout/stderr drain and timeout termination' { Test-ConcurrentStreamsAndTimeout -Root (New-TestDirectory $runRoot 'streams') }
    Invoke-Test 'installed-child and installer environment sanitization matrix' { Test-InstalledAndInstallerEnvironmentPolicies -Root (New-TestDirectory $runRoot 'environment') }
    Invoke-Test 'full-CPython parent-observed startup isolation' { Test-ProductionStartupIsolation -Root (New-TestDirectory $runRoot 'python') }
    Invoke-Test 'candidate identity, sidecar, installer, source, snapshot, and evidence path guards' { Test-CandidateIdentityAndEvidencePathGuards -Root (New-TestDirectory $runRoot 'candidate') }
    Invoke-Test 'Task 7 transport, discovery, and internal evidence validators' { Test-Task7ArtifactValidators -Root (New-TestDirectory $runRoot 'task7') }
    Invoke-Test 'canonical JSONL authorization and scenario evidence validation' { Test-AuthorizationProtocolAndScenarioValidation -Root (New-TestDirectory $runRoot 'gate') }
    Invoke-Test 'startup-surface projection and durable containment hold' { Test-StartupSurfaceAndDurableHold -Root (New-TestDirectory $runRoot 'hold') }
    Invoke-Test 'acceptance, failure, post-drift, and read-only evidence contracts' { Test-AcceptanceFailureAndReadOnlyVerification -Root (New-TestDirectory $runRoot 'evidence') }
    Invoke-Test 'fake normal-mode success and fail-closed orchestration matrix' { Test-FakeNormalModeOrchestrationMatrix -Root (New-TestDirectory $runRoot 'normal-mode') }
    Invoke-Test 'normally nonterminating error fail-fast and frozen installer wiring' { Test-FailFastStageAndFrozenWiring -Root (New-TestDirectory $runRoot 'fail-fast') }
    $started.Stop()
    Write-Host ("Task 10 validator tests passed: {0} tests in {1:N2}s." -f $script:TestsPassed,$started.Elapsed.TotalSeconds)
} finally {
    if ($started.IsRunning) { $started.Stop() }
    Remove-TestTree -Path $runRoot
}
