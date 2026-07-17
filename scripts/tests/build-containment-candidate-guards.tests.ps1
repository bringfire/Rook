Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$TestRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$GuardPath = $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestRoot)
$BuilderPath = Join-Path $RepoRoot 'scripts\build-containment-candidate.ps1'
$WindowsPowerShell = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
$CmdPath = 'C:\Windows\System32\cmd.exe'
$FixturePythonRoot = 'C:\Users\aryan\source\repos\Rook\installer\runtime\python\cpython-3.11.9'
$script:TestsPassed = 0

if (-not (Test-Path -LiteralPath $BuilderPath -PathType Leaf)) {
    throw 'EXPECTED_RED:T9:BUILDER_MISSING'
}

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Assert-Equal {
    param([object]$Actual, [object]$Expected, [string]$Message)
    if ([string]$Actual -cne [string]$Expected) {
        throw "$Message Expected=[$Expected] Actual=[$Actual]"
    }
}

function Assert-Contains {
    param([string]$Text, [string]$Expected, [string]$Message)
    Assert-True -Condition $Text.Contains($Expected) -Message "$Message Missing=[$Expected]"
}

function Assert-NotContains {
    param([string]$Text, [string]$Unexpected, [string]$Message)
    Assert-True -Condition (-not $Text.Contains($Unexpected)) -Message "$Message Unexpected=[$Unexpected]"
}

function Assert-StringSequenceEqual {
    param([object[]]$Actual, [object[]]$Expected, [string]$Message)
    $actualValues = @($Actual | ForEach-Object { [string]$_ })
    $expectedValues = @($Expected | ForEach-Object { [string]$_ })
    Assert-Equal -Actual $actualValues.Count -Expected $expectedValues.Count -Message "$Message Count mismatch."
    for ($index = 0; $index -lt $expectedValues.Count; $index++) {
        Assert-True -Condition ([string]::Equals($actualValues[$index],$expectedValues[$index],[StringComparison]::Ordinal)) -Message "$Message Index=${index} Expected=[$($expectedValues[$index])] Actual=[$($actualValues[$index])]"
    }
}

function Get-GuardOrdinalSortedStrings {
    param([AllowEmptyCollection()][string[]]$Values)
    [string[]]$sorted = @($Values)
    [System.Array]::Sort($sorted, [StringComparer]::Ordinal)
    return $sorted
}

function Assert-FileIdentityMatchesDisk {
    param([object]$Identity, [string]$ExpectedPath, [string]$Label)
    $canonical = (Resolve-Path -LiteralPath $ExpectedPath).Path
    Assert-Equal -Actual ([string]$Identity.path) -Expected $canonical -Message "$Label path mismatch."
    $item = Get-Item -LiteralPath $canonical -Force
    Assert-Equal -Actual ([long]$Identity.size) -Expected ([long]$item.Length) -Message "$Label size mismatch."
    Assert-Equal -Actual ([string]$Identity.sha256) -Expected ((Get-FileHash -LiteralPath $canonical -Algorithm SHA256).Hash.ToLowerInvariant()) -Message "$Label SHA-256 mismatch."
    $version = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($canonical)
    Assert-Equal -Actual ([string]$Identity.file_version) -Expected ([string]$version.FileVersion) -Message "$Label file-version mismatch."
    Assert-Equal -Actual ([string]$Identity.product_version) -Expected ([string]$version.ProductVersion) -Message "$Label product-version mismatch."
}

function Assert-HashMatchesFile {
    param([string]$ActualHash, [string]$Path, [string]$Label)
    Assert-Equal -Actual $ActualHash -Expected ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()) -Message "$Label SHA-256 mismatch."
}

function Write-Utf8NoBom {
    param([string]$Path, [string]$Text)
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path -LiteralPath $parent -PathType Container)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    [System.IO.File]::WriteAllText($Path, $Text, [System.Text.UTF8Encoding]::new($false))
}

function Get-GuardStringSha256 {
    param([string]$Text)
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($Text)
        $hash = $algorithm.ComputeHash($bytes)
        return ([System.BitConverter]::ToString($hash) -replace '-', '').ToLowerInvariant()
    } finally { $algorithm.Dispose() }
}

function ConvertTo-GuardCanonicalJson {
    param([AllowNull()][object]$Value)
    if ($null -eq $Value) { return 'null' }
    if ($Value -is [bool]) { if ($Value) { return 'true' } else { return 'false' } }
    if ($Value -is [string] -or $Value -is [char]) { return ConvertTo-Json -InputObject ([string]$Value) -Compress }
    if ($Value -is [System.Collections.IDictionary]) {
        [string[]]$keys = @($Value.Keys | ForEach-Object { [string]$_ })
        [System.Array]::Sort($keys, [StringComparer]::Ordinal)
        $parts = foreach ($key in $keys) { (ConvertTo-Json -InputObject $key -Compress) + ':' + (ConvertTo-GuardCanonicalJson -Value $Value[$key]) }
        return '{' + ($parts -join ',') + '}'
    }
    if ($Value -is [pscustomobject]) {
        $dictionary = [ordered]@{}
        foreach ($property in $Value.PSObject.Properties) { $dictionary[$property.Name] = $property.Value }
        return ConvertTo-GuardCanonicalJson -Value $dictionary
    }
    if ($Value -is [System.Collections.IEnumerable]) {
        $items = foreach ($item in $Value) { ConvertTo-GuardCanonicalJson -Value $item }
        return '[' + ($items -join ',') + ']'
    }
    if ($Value -is [byte] -or $Value -is [sbyte] -or $Value -is [int16] -or $Value -is [uint16] -or
        $Value -is [int32] -or $Value -is [uint32] -or $Value -is [int64] -or $Value -is [uint64] -or
        $Value -is [single] -or $Value -is [double] -or $Value -is [decimal]) {
        return [System.Convert]::ToString($Value, [System.Globalization.CultureInfo]::InvariantCulture)
    }
    return ConvertTo-Json -InputObject ([string]$Value) -Compress
}

function Assert-InventoryMatchesDisk {
    param(
        [object]$Inventory,
        [string]$Root,
        [string]$Label,
        [string[]]$ExcludedRelativePaths = @()
    )
    $files = @($Inventory.files)
    $canonicalFiles = ConvertTo-GuardCanonicalJson -Value $files
    Assert-Equal -Actual ([string]$Inventory.digest) -Expected (Get-GuardStringSha256 -Text $canonicalFiles) -Message "$Label digest does not bind its canonical file projection."
    $canonicalRoot = [System.IO.Path]::GetFullPath($Root).TrimEnd('\')
    $excluded = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($relative in $ExcludedRelativePaths) { [void]$excluded.Add($relative.Replace('\','/')) }
    $recordedPaths = @($files | ForEach-Object { [string]$_.relative_path })
    $diskPaths = @(Get-GuardOrdinalSortedStrings -Values @(Get-ChildItem -LiteralPath $canonicalRoot -Recurse -File -Force | ForEach-Object {
        $relative = $_.FullName.Substring($canonicalRoot.Length).TrimStart('\').Replace('\','/')
        if ($relative -notmatch '(?i)(^|/)\.git(/|$)' -and -not $excluded.Contains($relative)) { $relative }
    }))
    Assert-Equal -Actual $recordedPaths.Count -Expected $diskPaths.Count -Message "$Label does not cover the exact disk file set."
    for ($index = 0; $index -lt $recordedPaths.Count; $index++) {
        Assert-True -Condition ([string]::Equals($recordedPaths[$index],$diskPaths[$index],[StringComparison]::Ordinal)) -Message "$Label disk file-set mismatch at index ${index}: recorded=$($recordedPaths[$index]) disk=$($diskPaths[$index])"
    }
    foreach ($file in $files) {
        $relative = [string]$file.relative_path
        Assert-True -Condition (-not [System.IO.Path]::IsPathRooted($relative) -and $relative -notmatch '(^|/)\.\.(/|$)') -Message "$Label contains an unsafe relative path: $relative"
        Assert-True -Condition ($relative -notmatch '(?i)(^|/)\.git(/|$)') -Message "$Label includes Git internals: $relative"
        $path = [System.IO.Path]::GetFullPath((Join-Path $canonicalRoot $relative.Replace('/','\')))
        Assert-True -Condition ($path.StartsWith($canonicalRoot + '\',[StringComparison]::OrdinalIgnoreCase)) -Message "$Label path escaped its root: $relative"
        Assert-True -Condition (Test-Path -LiteralPath $path -PathType Leaf) -Message "$Label recorded file is missing: $relative"
        $item = Get-Item -LiteralPath $path
        Assert-Equal -Actual ([long]$file.size) -Expected ([long]$item.Length) -Message "$Label size mismatch for $relative."
        Assert-Equal -Actual ([string]$file.sha256) -Expected ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()) -Message "$Label SHA-256 mismatch for $relative."
    }
}

function Assert-SelectedProjectionMatchesDisk {
    param(
        [object]$Projection,
        [string]$Root,
        [string[]]$ExpectedRelativePaths,
        [string]$Label
    )
    $files = @($Projection.files)
    Assert-Equal -Actual ([string]$Projection.digest) -Expected (Get-GuardStringSha256 -Text (ConvertTo-GuardCanonicalJson -Value $files)) -Message "$Label digest does not bind its canonical file projection."
    $expected = @(Get-GuardOrdinalSortedStrings -Values @($ExpectedRelativePaths | ForEach-Object { $_.Replace('\','/') }))
    $actual = @($files | ForEach-Object { [string]$_.relative_path })
    Assert-StringSequenceEqual -Actual $actual -Expected $expected -Message "$Label relative-path set is not exact."
    $canonicalRoot = [System.IO.Path]::GetFullPath($Root).TrimEnd('\')
    foreach ($file in $files) {
        $relative = [string]$file.relative_path
        Assert-True -Condition (-not [System.IO.Path]::IsPathRooted($relative) -and $relative -notmatch '(^|/)\.\.(/|$)') -Message "$Label contains an unsafe relative path: $relative"
        $path = [System.IO.Path]::GetFullPath((Join-Path $canonicalRoot $relative.Replace('/','\')))
        Assert-True -Condition ($path.StartsWith($canonicalRoot + '\',[StringComparison]::OrdinalIgnoreCase)) -Message "$Label path escaped its root: $relative"
        $item = Get-Item -LiteralPath $path -Force
        Assert-Equal -Actual ([long]$file.size) -Expected ([long]$item.Length) -Message "$Label size mismatch for $relative."
        Assert-Equal -Actual ([string]$file.sha256) -Expected ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()) -Message "$Label SHA-256 mismatch for $relative."
    }
}

function ConvertTo-ProcessArgument {
    param([AllowNull()][AllowEmptyString()][string]$Value)
    if ($null -eq $Value -or $Value.Length -eq 0) { return '""' }
    if ($Value -notmatch '[\s"]') { return $Value }
    $escaped = $Value -replace '(\\*)"', '$1$1\"'
    $escaped = $escaped -replace '(\\+)$', '$1$1'
    return '"' + $escaped + '"'
}

function Wait-GuardTaskBounded {
    param([System.Threading.Tasks.Task]$Task, [string]$Label)
    if (-not $Task.Wait(10000)) { throw "$Label did not drain within 10000 milliseconds" }
    return $Task.GetAwaiter().GetResult()
}

function Invoke-Process {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory,
        [hashtable]$Environment = @{}
    )
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = (@($Arguments) | ForEach-Object { ConvertTo-ProcessArgument $_ }) -join ' '
    $psi.WorkingDirectory = $WorkingDirectory
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    foreach ($entry in $Environment.GetEnumerator()) {
        $psi.EnvironmentVariables[[string]$entry.Key] = [string]$entry.Value
    }
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    try {
        if (-not $process.Start()) { throw "Failed to start $FilePath" }
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(120000)) {
            try { $process.Kill() } catch {}
            try { [void]$process.WaitForExit(10000) } catch {}
            throw "Process timed out: $FilePath"
        }
        $stdout = Wait-GuardTaskBounded -Task $stdoutTask -Label "$FilePath stdout"
        $stderr = Wait-GuardTaskBounded -Task $stderrTask -Label "$FilePath stderr"
        $exitCode = $process.ExitCode
    } finally {
        $process.Dispose()
    }
    [pscustomobject]@{
        ExitCode = $exitCode
        Stdout = $stdout
        Stderr = $stderr
        Output = ($stdout + "`n" + $stderr)
    }
}

function Invoke-Git {
    param([string]$GitPath, [string]$WorkingDirectory, [string[]]$Arguments)
    $result = Invoke-Process -FilePath $GitPath -Arguments $Arguments -WorkingDirectory $WorkingDirectory
    if ($result.ExitCode -ne 0) {
        throw "Git fixture command failed ($($Arguments -join ' ')): $($result.Output)"
    }
    return $result.Stdout.Trim()
}

function New-Directory {
    param([string]$Path)
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
    return (Resolve-Path -LiteralPath $Path).Path
}

function New-FakeRookRepository {
    param([string]$Root, [string]$GitPath)
    New-Directory -Path $Root | Out-Null

    $fixtureSource = Join-Path $RepoRoot 'mcp_server\src\rook\resources\containment_empty.ghx'
    Assert-True -Condition (Test-Path -LiteralPath $fixtureSource -PathType Leaf) -Message 'The reviewed containment_empty.ghx fixture is missing.'
    New-Directory -Path (Join-Path $Root 'mcp_server\src\rook\resources') | Out-Null
    Copy-Item -LiteralPath $fixtureSource -Destination (Join-Path $Root 'mcp_server\src\rook\resources\containment_empty.ghx')
    Write-Utf8NoBom -Path (Join-Path $Root 'mcp_server\pyproject.toml') -Text @'
[project]
name = "rook"
version = "9.8.7"
'@
    Write-Utf8NoBom -Path (Join-Path $Root 'src\Rook\Rook.csproj') -Text "<Project><PropertyGroup><Version>9.8.7</Version></PropertyGroup></Project>`n"
    Write-Utf8NoBom -Path (Join-Path $Root 'src\RookBim\RookBim.csproj') -Text "<Project><PropertyGroup><Version>9.8.7</Version></PropertyGroup></Project>`n"
    Write-Utf8NoBom -Path (Join-Path $Root 'third_party\ffmpeg\ffmpeg.exe') -Text "reviewed ffmpeg pointer fixture`n"
    Write-Utf8NoBom -Path (Join-Path $Root 'third_party\ffmpeg\ffmpeg-provenance.json') -Text "{`"reviewed`":true}`n"
    Write-Utf8NoBom -Path (Join-Path $Root 'src\RookNative\RookNative.vcxproj') -Text @'
<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <ImportGroup Label="PropertySheets">
    <Import Project="$([MSBuild]::GetRegistryValueFromView('HKEY_LOCAL_MACHINE\SOFTWARE\McNeel\Rhinoceros\SDK\8.0', 'InstallPath', '', RegistryView.Registry64))PropertySheets\Rhino.Cpp.PlugIn.props" />
  </ImportGroup>
</Project>
'@
    $occtDlls = @('TKernel.dll','TKMath.dll','TKG2d.dll','TKG3d.dll','TKGeomBase.dll','TKGeomAlgo.dll','TKBRep.dll','TKTopAlgo.dll','TKPrim.dll','TKBO.dll','TKShHealing.dll')
    $installerLines = @(
        '; fake reviewed installer',
        '#ifndef MyAppVersion',
        '#define MyAppVersion "9.8.7"',
        '#endif',
        '#define RepoRoot ".."',
        '#define ChirpDir RepoRoot + "\..\Chirp"',
        '#ifndef VcRedistRoot',
        '#define VcRedistRoot "unused"',
        '#endif',
        '#ifndef OcctRuntimeRoot',
        '#define OcctRuntimeRoot "unused"',
        '#endif',
        '[Setup]',
        'OutputBaseFilename=Rook-Setup-{#MyAppVersion}',
        'OutputDir=output',
        '[Files]'
    )
    foreach ($dll in $occtDlls) {
        $installerLines += "Source: `"{#OcctRuntimeRoot}\$dll`"; DestDir: `"{app}`"; Flags: ignoreversion"
    }
    Write-Utf8NoBom -Path (Join-Path $Root 'installer\RookSetup.iss') -Text (($installerLines -join "`n") + "`n")

    Write-Utf8NoBom -Path (Join-Path $Root 'scripts\python-runtime\stage-rook-python-runtime.ps1') -Text @'
param([Parameter(Mandatory = $true)][string]$RepoRoot)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($env:T9_WRITE_ERROR -eq '1') { Write-Error 'T9 injected normally nonterminating cmdlet error' }
$runtime = Join-Path $RepoRoot 'installer\runtime\python\cpython-3.11.9'
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
foreach ($name in @('python.exe','python311.dll','vcruntime140.dll','vcruntime140_1.dll')) {
    Copy-Item -LiteralPath (Join-Path $env:T9_FIXTURE_PYTHON_ROOT $name) -Destination (Join-Path $runtime $name)
}
if ($env:T9_MUTATE_SOURCE_FILE) { [System.IO.File]::WriteAllText($env:T9_MUTATE_SOURCE_FILE, 'source changed') }
if ($env:T9_MUTATE_STAGED_SOURCE -eq '1') { [System.IO.File]::AppendAllText((Join-Path $RepoRoot 'src\RookNative\RookNative.vcxproj'), "`n<!-- staged drift -->`n") }
if ($env:T9_MUTATE_ALLOWED_EARLY -eq '1') { [System.IO.File]::AppendAllText((Join-Path $RepoRoot 'third_party\ffmpeg\ffmpeg.exe'), "early drift`n") }
[System.IO.File]::WriteAllText((Join-Path $RepoRoot 'stage-runtime.args.txt'), ($PSBoundParameters.Keys | Sort-Object | ForEach-Object { "$_=$($PSBoundParameters[$_])" }) -join "`n")
'@
    Write-Utf8NoBom -Path (Join-Path $Root 'scripts\python-runtime\build-rook-python-wheelhouse.ps1') -Text @'
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][string]$RepoRoot,
    [Parameter(Mandatory = $true)][string]$ChirpRoot
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$outDir = Join-Path $RepoRoot 'installer\runtime\python-wheelhouse'
New-Item -ItemType Directory -Path $outDir -Force | Out-Null
$wheel = Join-Path $outDir "rook-$Version-py3-none-any.whl"
$archive = [System.IO.Compression.ZipFile]::Open($wheel, [System.IO.Compression.ZipArchiveMode]::Create)
try {
    $entry = $archive.CreateEntry('rook/resources/containment_empty.ghx')
    $stream = $entry.Open()
    try {
        $bytes = [System.IO.File]::ReadAllBytes((Join-Path $RepoRoot 'mcp_server\src\rook\resources\containment_empty.ghx'))
        $stream.Write($bytes, 0, $bytes.Length)
    } finally { $stream.Dispose() }
} finally { $archive.Dispose() }
[System.IO.File]::WriteAllText((Join-Path $RepoRoot 'wheelhouse.args.txt'), "Version=$Version`nRepoRoot=$RepoRoot`nChirpRoot=$ChirpRoot")
if ($env:T9_MUTATE_WHEEL_VALIDATOR -eq '1') { [System.IO.File]::AppendAllText((Join-Path $RepoRoot 'scripts\validate-python-wheelhouse.ps1'), "`n# mutated by wheel build`n") }
'@
    Write-Utf8NoBom -Path (Join-Path $Root 'scripts\validate-python-wheelhouse.ps1') -Text @'
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][string]$RepoRoot
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[System.IO.File]::WriteAllText((Join-Path $RepoRoot 'validate-wheelhouse.args.txt'), "Version=$Version`nRepoRoot=$RepoRoot")
'@
    Write-Utf8NoBom -Path (Join-Path $Root 'scripts\ffmpeg\rook-ffmpeg-source.json') -Text "{`"version`":`"7.1.1`"}`n"
    Write-Utf8NoBom -Path (Join-Path $Root 'scripts\ffmpeg\build-rook-ffmpeg.ps1') -Text @'
param(
    [Parameter(Mandatory = $true)][string]$RepoRoot,
    [Parameter(Mandatory = $true)][string]$Msys2Bash,
    [switch]$InstallPayload
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$stage = Join-Path $RepoRoot 'artifacts\ffmpeg\ffmpeg-7.1.1-rook-minimal'
New-Item -ItemType Directory -Path $stage -Force | Out-Null
[System.IO.File]::WriteAllText((Join-Path $stage 'rook-ffmpeg-source-bundle-manifest.json'), '{"version":"7.1.1"}')
$payload = Join-Path $RepoRoot 'third_party\ffmpeg'
New-Item -ItemType Directory -Path $payload -Force | Out-Null
[System.IO.File]::WriteAllText((Join-Path $payload 'ffmpeg.exe'), 'fake ffmpeg')
[System.IO.File]::WriteAllText((Join-Path $payload 'ffmpeg-provenance.json'), '{"built":true}')
[System.IO.File]::WriteAllText((Join-Path $RepoRoot 'ffmpeg-build.args.txt'), "RepoRoot=$RepoRoot`nMsys2Bash=$Msys2Bash`nInstallPayload=$InstallPayload")
if ($env:T9_MUTATE_FFMPEG_VALIDATOR -eq '1') { [System.IO.File]::AppendAllText((Join-Path $RepoRoot 'scripts\validate-ffmpeg-bundle.ps1'), "`n# mutated by FFmpeg build`n") }
'@
    Write-Utf8NoBom -Path (Join-Path $Root 'scripts\validate-ffmpeg-bundle.ps1') -Text @'
param(
    [Parameter(Mandatory = $true)][string]$RepoRoot,
    [Parameter(Mandatory = $true)][string]$SourceBundleManifestPath
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $SourceBundleManifestPath -PathType Leaf)) { throw 'missing generated FFmpeg manifest' }
if ($env:T9_MUTATE_THIRD_TRACKED -eq '1') { [System.IO.File]::AppendAllText((Join-Path $RepoRoot 'src\RookNative\RookNative.vcxproj'), "`n<!-- late staged drift -->`n") }
[System.IO.File]::WriteAllText((Join-Path $RepoRoot 'ffmpeg-validate.args.txt'), "RepoRoot=$RepoRoot`nSourceBundleManifestPath=$SourceBundleManifestPath")
'@

    Invoke-Git -GitPath $GitPath -WorkingDirectory $Root -Arguments @('init', '-b', 'codex/gh-execute-intent-root-fix') | Out-Null
    Invoke-Git -GitPath $GitPath -WorkingDirectory $Root -Arguments @('config', 'user.name', 'Task Nine Guard') | Out-Null
    Invoke-Git -GitPath $GitPath -WorkingDirectory $Root -Arguments @('config', 'user.email', 'task9@example.invalid') | Out-Null
    Invoke-Git -GitPath $GitPath -WorkingDirectory $Root -Arguments @('add', '.') | Out-Null
    Invoke-Git -GitPath $GitPath -WorkingDirectory $Root -Arguments @('commit', '-m', 'fake rook source') | Out-Null
    return (Invoke-Git -GitPath $GitPath -WorkingDirectory $Root -Arguments @('rev-parse', 'HEAD'))
}

function New-FakeChirpRepository {
    param([string]$Root, [string]$GitPath)
    New-Directory -Path $Root | Out-Null
    Write-Utf8NoBom -Path (Join-Path $Root 'pyproject.toml') -Text @'
[project]
name = "chirp"
version = "9.8.7"
'@
    Write-Utf8NoBom -Path (Join-Path $Root 'src\chirp\__init__.py') -Text "__version__ = '9.8.7'`n"
    Invoke-Git -GitPath $GitPath -WorkingDirectory $Root -Arguments @('init', '-b', 'main') | Out-Null
    Invoke-Git -GitPath $GitPath -WorkingDirectory $Root -Arguments @('config', 'user.name', 'Task Nine Guard') | Out-Null
    Invoke-Git -GitPath $GitPath -WorkingDirectory $Root -Arguments @('config', 'user.email', 'task9@example.invalid') | Out-Null
    Invoke-Git -GitPath $GitPath -WorkingDirectory $Root -Arguments @('add', '.') | Out-Null
    Invoke-Git -GitPath $GitPath -WorkingDirectory $Root -Arguments @('commit', '-m', 'fake chirp source') | Out-Null
    return (Invoke-Git -GitPath $GitPath -WorkingDirectory $Root -Arguments @('rev-parse', 'HEAD'))
}

function New-FakeToolchain {
    param([string]$Root)
    $vsRoot = New-Directory -Path (Join-Path $Root 'FakeVS')
    $vcvars = Join-Path $vsRoot 'VC\Auxiliary\Build\vcvarsall.bat'
    $msbuild = Join-Path $vsRoot 'MSBuild\Current\Bin\MSBuild.cmd'
    $vcTools = New-Directory -Path (Join-Path $vsRoot 'VC\Tools\MSVC\14.44.35207')
    $vcTargets = New-Directory -Path (Join-Path $vsRoot 'MSBuild\Microsoft\VC\v170')
    $msbuildRoot = New-Directory -Path (Join-Path $vsRoot 'MSBuild')
    $msbuildBin = New-Directory -Path (Join-Path $msbuildRoot 'Current\Bin')
    $msbuildSdks = New-Directory -Path (Join-Path $msbuildRoot 'Sdks')
    $sdkRoot = 'C:\Program Files (x86)\Windows Kits\10'
    $netFxSdkRoot = 'C:\Program Files (x86)\Windows Kits\NETFXSDK\4.8'
    $netFxToolsRoot = 'C:\Program Files (x86)\Microsoft SDKs\Windows\v10.0A\bin\NETFX 4.8 Tools\x64'
    $htmlHelpRoot = 'C:\Program Files (x86)\HTML Help Workshop'
    Assert-True -Condition (Test-Path -LiteralPath $sdkRoot -PathType Container) -Message 'Windows SDK guard root is missing.'
    Assert-True -Condition (Test-Path -LiteralPath (Join-Path $netFxSdkRoot 'include\um') -PathType Container) -Message 'NETFX SDK guard include root is missing.'
    Assert-True -Condition (Test-Path -LiteralPath $netFxToolsRoot -PathType Container) -Message 'NETFX tools guard root is missing.'
    Assert-True -Condition (Test-Path -LiteralPath $htmlHelpRoot -PathType Container) -Message 'HTML Help guard root is missing.'
    foreach ($path in @(
        (Join-Path $vcTools 'include'), (Join-Path $vcTools 'lib\x64'),
        (Join-Path $vcTools 'bin\Hostx64\x64'), $vcTargets
    )) { New-Directory -Path $path | Out-Null }
    $trustedCompiler = Join-Path $vcTools 'bin\Hostx64\x64\cl.exe'
    $trustedLinker = Join-Path $vcTools 'bin\Hostx64\x64\link.exe'
    Write-Utf8NoBom -Path $trustedCompiler -Text "trusted fake compiler`n"
    Write-Utf8NoBom -Path $trustedLinker -Text "trusted fake linker`n"

    Write-Utf8NoBom -Path $vcvars -Text (@"
@echo off
set "VCToolsInstallDir=$vcTools\"
set "VCTargetsPath=$vcTargets\"
set "VCTargetsPath10=$vcTargets\"
set "VCTargetsPath11=$vcTargets\"
set "VCTargetsPath12=$vcTargets\"
set "VCTargetsPath14=$vcTargets\"
set "VCTargetsPath15=$vcTargets\"
set "VCTargetsPath16=$vcTargets\"
set "VCTargetsPath17=$vcTargets\"
set "MSBUILD_EXE_PATH=$msbuild"
set "MSBuildExtensionsPath=$msbuildRoot\"
set "MSBuildExtensionsPath32=$msbuildRoot\"
set "MSBuildExtensionsPath64=$msbuildRoot\"
set "MSBuildSDKsPath=$msbuildSdks\"
set "MSBuildToolsPath=$msbuildBin\"
set "MSBuildToolsPath32=$msbuildBin\"
set "MSBuildToolsPath64=$msbuildBin\"
set "MSBuildToolsRoot=$msbuildRoot\"
set "WindowsSdkDir=$sdkRoot\"
set "UniversalCRTSdkDir=$sdkRoot\"
set "UCRTContentRoot=$sdkRoot\"
set "NETFXSDKDir=$netFxSdkRoot\"
set "INCLUDE=$vcTools\include;$sdkRoot\Include;$netFxSdkRoot\include\um"
set "LIB=$vcTools\lib\x64;$sdkRoot\Lib"
set "LIBPATH=$vcTools\lib\x64;$sdkRoot\Lib"
set "PATH=$vcTools\bin\Hostx64\x64;$sdkRoot\bin;$netFxToolsRoot;$htmlHelpRoot;%PATH%"
exit /b 0
"@ -replace "`n", "`r`n")

    Write-Utf8NoBom -Path $msbuild -Text (@'
@echo off
setlocal
set "project=%~1"
for %%P in ("%project%") do set "projectDir=%%~dpP"
> "%projectDir%native-msbuild.args.txt" echo %*
set > "%projectDir%native-msbuild.env.txt"
if defined CL exit /b 81
if defined _CL_ exit /b 82
if defined LINK exit /b 83
if defined _LINK_ exit /b 84
if not "%OCCT_ROOT%"=="" exit /b 85
mkdir "%projectDir%bin\Release\x64" 2>nul
> "%projectDir%bin\Release\x64\RookNative.rhp" echo fake native
> "%projectDir%bin\Release\x64\RookNative.pdb" echo fake pdb
exit /b 0
'@ -replace "`n", "`r`n")

    $dotnet = Join-Path $Root 'tools\dotnet.cmd'
    Write-Utf8NoBom -Path $dotnet -Text (@'
@echo off
setlocal EnableDelayedExpansion
if "%~1"=="--version" (
  echo 8.0.100
  exit /b 0
)
> "%T9_STUB_LOG%\dotnet-%RANDOM%.args.txt" echo %*
if not "%T9_MUTATE_EXTERNAL_FILE%"=="" if not exist "%T9_STUB_LOG%\external-mutated.marker" (
  >> "%T9_MUTATE_EXTERNAL_FILE%" echo drift
  > "%T9_STUB_LOG%\external-mutated.marker" echo mutated
)
set "pluginDir="
for %%A in (%*) do (
  set "arg=%%~A"
  if /I "!arg:~0,18!"=="-p:RhinoPluginDir=" set "pluginDir=!arg:~18!"
)
if defined pluginDir if exist "!pluginDir!" exit /b 91
if "%T9_CREATE_INERT%"=="1" if defined pluginDir mkdir "!pluginDir!"
if "%T9_MUTATE_LIVE%"=="1" > "%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\mutated.txt" echo changed
if /I "%~1"=="build" if "%T9_MUTATE_ALLOWED_LATE%"=="1" >> "%~dp2..\..\third_party\ffmpeg\ffmpeg.exe" echo late drift
if /I "%~1"=="build" if "%T9_MUTATE_WHEEL_LATE%"=="1" >> "%~dp2..\..\installer\runtime\python-wheelhouse\rook-9.8.7-py3-none-any.whl" echo late wheel drift
if /I "%~1"=="build" if "%T9_MUTATE_MANIFEST_LATE%"=="1" >> "%~dp2..\..\artifacts\ffmpeg\ffmpeg-7.1.1-rook-minimal\rook-ffmpeg-source-bundle-manifest.json" echo late manifest drift
set "project=%~2"
if /I "%~nx2"=="RookBim.csproj" (
  for %%P in ("%project%") do set "projectDir=%%~dpP"
  mkdir "!projectDir!bin\Release\net48" 2>nul
  > "!projectDir!bin\Release\net48\RookBim.dll" echo fake bim
) else (
  for %%P in ("%project%") do set "projectDir=%%~dpP"
  mkdir "!projectDir!bin\Release\net8.0" 2>nul
  mkdir "!projectDir!bin\Release\net7.0" 2>nul
  mkdir "!projectDir!bin\Release\net48" 2>nul
  > "!projectDir!bin\Release\net8.0\Rook.rhp" echo fake rook
  > "!projectDir!bin\Release\net7.0\Rook.rhp" echo fake rook
  > "!projectDir!bin\Release\net48\Rook.rhp" echo fake rook
)
exit /b 0
'@ -replace "`n", "`r`n")

    $iscc = Join-Path $Root 'tools\ISCC.cmd'
    Write-Utf8NoBom -Path $iscc -Text (@'
@echo off
setlocal EnableDelayedExpansion
> "%T9_STUB_LOG%\iscc.args.txt" echo %*
set "iss="
for %%A in (%*) do set "iss=%%~A"
for %%P in ("!iss!") do set "installerDir=%%~dpP"
mkdir "!installerDir!output" 2>nul
> "!installerDir!output\Rook-Setup-9.8.7.exe" echo fake installer
if "%T9_MUTATE_WHEEL_IN_ISCC%"=="1" >> "!installerDir!runtime\python-wheelhouse\rook-9.8.7-py3-none-any.whl" echo post-package wheel drift
exit /b 0
'@ -replace "`n", "`r`n")

    $bash = Join-Path $Root 'tools\bash.cmd'
    Write-Utf8NoBom -Path $bash -Text "@echo off`r`nexit /b 0`r`n"

    [pscustomobject]@{
        VsRoot = $vsRoot
        VcvarsallPath = (Resolve-Path -LiteralPath $vcvars).Path
        MsbuildPath = (Resolve-Path -LiteralPath $msbuild).Path
        DotnetPath = (Resolve-Path -LiteralPath $dotnet).Path
        IsccPath = (Resolve-Path -LiteralPath $iscc).Path
        Msys2Bash = (Resolve-Path -LiteralPath $bash).Path
        VcToolsRoot = $vcTools
        VcTargetsRoot = $vcTargets
        MsbuildRoot = $msbuildRoot
        MsbuildBin = $msbuildBin
        MsbuildSdks = $msbuildSdks
        WindowsSdkRoot = $sdkRoot
        NetFxSdkRoot = $netFxSdkRoot
        NetFxToolsRoot = $netFxToolsRoot
        HtmlHelpRoot = $htmlHelpRoot
        TrustedCompiler = $trustedCompiler
        TrustedLinker = $trustedLinker
    }
}

function New-Task9Fixture {
    $root = Join-Path ([System.IO.Path]::GetTempPath()) ('rook-task9-guards-' + [guid]::NewGuid().ToString('N'))
    New-Directory -Path $root | Out-Null
    $gitPath = (Get-Command git.exe -ErrorAction Stop).Source
    $rookRoot = Join-Path $root 'source\Rook'
    $chirpRoot = Join-Path $root 'source\Chirp'
    $rookSha = New-FakeRookRepository -Root $rookRoot -GitPath $gitPath
    $chirpSha = New-FakeChirpRepository -Root $chirpRoot -GitPath $gitPath
    $toolchain = New-FakeToolchain -Root $root

    $occtRoot = New-Directory -Path (Join-Path $root 'external\OCCT')
    Write-Utf8NoBom -Path (Join-Path $occtRoot 'inc\Standard.hxx') -Text "// fake Standard.hxx`n"
    $occtLibraries = @('TKernel.lib','TKMath.lib','TKG2d.lib','TKG3d.lib','TKGeomBase.lib','TKGeomAlgo.lib','TKBRep.lib','TKTopAlgo.lib','TKPrim.lib','TKBO.lib','TKBool.lib','TKShHealing.lib','TKMesh.lib')
    foreach ($name in $occtLibraries) { Write-Utf8NoBom -Path (Join-Path $occtRoot "win64\vc14\lib\$name") -Text "fake $name`n" }
    $occtRuntimeRoot = New-Directory -Path (Join-Path $occtRoot 'win64\vc14\bin')
    foreach ($name in @('TKernel.dll','TKMath.dll','TKG2d.dll','TKG3d.dll','TKGeomBase.dll','TKGeomAlgo.dll','TKBRep.dll','TKTopAlgo.dll','TKPrim.dll','TKBO.dll','TKShHealing.dll')) {
        Write-Utf8NoBom -Path (Join-Path $occtRuntimeRoot $name) -Text "fake $name`n"
    }

    $rhinoSystem = New-Directory -Path (Join-Path $root 'external\Rhino8\System')
    foreach ($rel in @('netcore\RhinoCommon.dll','netcore\Rhino.UI.dll','Eto.dll','RhinoCommon.dll')) {
        Write-Utf8NoBom -Path (Join-Path $rhinoSystem $rel) -Text "fake $rel`n"
    }
    $revitInstall = New-Directory -Path (Join-Path $root 'external\Revit2024')
    foreach ($name in @('RevitAPI.dll','RevitAPIUI.dll')) { Write-Utf8NoBom -Path (Join-Path $revitInstall $name) -Text "fake $name`n" }
    $vcRedist = New-Directory -Path (Join-Path $root 'external\VcRedist')
    foreach ($rel in @('Microsoft.VC143.CRT\concrt140.dll','Microsoft.VC143.CRT\msvcp140.dll','Microsoft.VC143.CRT\vcruntime140.dll','Microsoft.VC143.CRT\vcruntime140_1.dll','Microsoft.VC143.MFC\mfc140.dll','Microsoft.VC143.MFC\mfc140u.dll')) {
        Write-Utf8NoBom -Path (Join-Path $vcRedist $rel) -Text "fake $rel`n"
    }
    $rhinoSdk = New-Directory -Path (Join-Path $root 'external\RhinoSdk')
    Write-Utf8NoBom -Path (Join-Path $rhinoSdk 'PropertySheets\Rhino.Cpp.PlugIn.props') -Text "<Project />`n"
    $rhinoSdkDrift = New-Directory -Path (Join-Path $root 'external\RhinoSdkDrift')
    Write-Utf8NoBom -Path (Join-Path $rhinoSdkDrift 'PropertySheets\Rhino.Cpp.PlugIn.props') -Text "<Project><PropertyGroup><Drift>true</Drift></PropertyGroup></Project>`n"
    $appData = New-Directory -Path (Join-Path $root 'appdata')
    $livePlugin = New-Directory -Path (Join-Path $appData 'McNeel\Rhinoceros\8.0\Plug-ins\RookNative')
    Write-Utf8NoBom -Path (Join-Path $livePlugin 'sentinel\keep.bin') -Text 'live sentinel'
    $stubLog = New-Directory -Path (Join-Path $root 'stub-log')
    $decoy = New-Directory -Path (Join-Path $root 'decoy-path')
    $decoyOcct = New-Directory -Path (Join-Path $root 'decoy-occt')
    $tripRoot = New-Directory -Path (Join-Path $root 'trip-imports')
    $reparseTarget = New-Directory -Path (Join-Path $root 'external\ReparseEscape')
    $reparseLink = Join-Path $toolchain.VcToolsRoot 'include-junction'
    New-Item -ItemType Junction -Path $reparseLink -Target $reparseTarget | Out-Null
    foreach ($name in @('cl.cmd','link.cmd','MSBuild.cmd')) {
        $hitPath = Join-Path $tripRoot "$name.tool.hit"
        Write-Utf8NoBom -Path (Join-Path $decoy $name) -Text "@echo off`r`n> `"$hitPath`" echo reached`r`nexit /b 97`r`n"
    }
    foreach ($name in Get-DirectHookNames) {
        $hitPath = Join-Path $tripRoot "$name.hit"
        $tripText = "<Project><Target Name=`"Trip$name`" BeforeTargets=`"PrepareForBuild`"><WriteLinesToFile File=`"$hitPath`" Lines=`"trip`" /></Target></Project>"
        Write-Utf8NoBom -Path (Join-Path $tripRoot "$name.props") -Text $tripText
    }

    $wrapper = Join-Path $root 'invoke-builder.ps1'
    Write-Utf8NoBom -Path $wrapper -Text @'
param(
    [Parameter(Mandatory = $true)][string]$BuilderPath,
    [Parameter(Mandatory = $true)][string]$FakeRhinoSdkPath,
    [Parameter(Mandatory = $true)][string]$RookRoot,
    [Parameter(Mandatory = $true)][string]$ExpectedBranch,
    [Parameter(Mandatory = $true)][string]$ExpectedRookSha,
    [Parameter(Mandatory = $true)][string]$ChirpRoot,
    [Parameter(Mandatory = $true)][string]$ExpectedChirpSha,
    [Parameter(Mandatory = $true)][string]$ArtifactDirectory,
    [Parameter(Mandatory = $true)][string]$GitPath,
    [Parameter(Mandatory = $true)][string]$PowerShellPath,
    [Parameter(Mandatory = $true)][string]$CmdPath,
    [Parameter(Mandatory = $true)][string]$Msys2Bash,
    [Parameter(Mandatory = $true)][string]$VcvarsallPath,
    [Parameter(Mandatory = $true)][string]$MsbuildPath,
    [Parameter(Mandatory = $true)][string]$DotnetPath,
    [Parameter(Mandatory = $true)][string]$RhinoSystemDir,
    [Parameter(Mandatory = $true)][string]$RevitInstallDir,
    [Parameter(Mandatory = $true)][string]$VcRedistRoot,
    [Parameter(Mandatory = $true)][string]$OcctRoot,
    [Parameter(Mandatory = $true)][string]$OcctRuntimeRoot,
    [Parameter(Mandatory = $true)][string]$IsccPath
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$global:T9RhinoSdkQueryCount = 0
function Get-ItemProperty {
    param([string]$LiteralPath, [string]$Name, [object]$ErrorAction)
    if ($LiteralPath -eq 'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\McNeel\Rhinoceros\SDK\8.0' -and $Name -eq 'InstallPath') {
        $global:T9RhinoSdkQueryCount++
        $installPath = $FakeRhinoSdkPath
        if ($env:T9_FAKE_RHINO_SDK_PATH) { $installPath = $env:T9_FAKE_RHINO_SDK_PATH }
        if ($env:T9_RHINO_SDK_DRIFT_PATH -and $global:T9RhinoSdkQueryCount -ge 2) { $installPath = $env:T9_RHINO_SDK_DRIFT_PATH }
        return [pscustomobject]@{ InstallPath = $installPath }
    }
    throw "Unexpected registry query: $LiteralPath / $Name"
}
& $BuilderPath `
    -RookRoot $RookRoot -ExpectedBranch $ExpectedBranch -ExpectedRookSha $ExpectedRookSha `
    -ChirpRoot $ChirpRoot -ExpectedChirpSha $ExpectedChirpSha -ArtifactDirectory $ArtifactDirectory `
    -GitPath $GitPath -PowerShellPath $PowerShellPath -CmdPath $CmdPath -Msys2Bash $Msys2Bash `
    -VcvarsallPath $VcvarsallPath -MsbuildPath $MsbuildPath -DotnetPath $DotnetPath `
    -RhinoSystemDir $RhinoSystemDir -RevitInstallDir $RevitInstallDir -VcRedistRoot $VcRedistRoot `
    -OcctRoot $OcctRoot -OcctRuntimeRoot $OcctRuntimeRoot -IsccPath $IsccPath
'@

    [pscustomobject]@{
        Root = (Resolve-Path -LiteralPath $root).Path
        GitPath = $gitPath
        RookRoot = (Resolve-Path -LiteralPath $rookRoot).Path
        ChirpRoot = (Resolve-Path -LiteralPath $chirpRoot).Path
        RookSha = $rookSha
        ChirpSha = $chirpSha
        Toolchain = $toolchain
        OcctRoot = $occtRoot
        OcctRuntimeRoot = $occtRuntimeRoot
        RhinoSystemDir = $rhinoSystem
        RevitInstallDir = $revitInstall
        VcRedistRoot = $vcRedist
        RhinoSdkRoot = $rhinoSdk
        RhinoSdkDriftRoot = $rhinoSdkDrift
        AppData = $appData
        LivePlugin = $livePlugin
        StubLog = $stubLog
        DecoyPath = $decoy
        DecoyOcct = $decoyOcct
        TripRoot = $tripRoot
        ReparseLink = $reparseLink
        Wrapper = $wrapper
        NextRun = 0
    }
}

function Get-ScrubNames {
    @(
        'CL','_CL_','LINK','_LINK_','INCLUDE','LIB','LIBPATH',
        'VCTargetsPath','VCTargetsPath10','VCTargetsPath11','VCTargetsPath12','VCTargetsPath14','VCTargetsPath15','VCTargetsPath16','VCTargetsPath17',
        'MSBUILD_EXE_PATH','MSBuildExtensionsPath','MSBuildExtensionsPath32','MSBuildExtensionsPath64','MSBuildSDKsPath','MSBuildToolsPath','MSBuildToolsPath32','MSBuildToolsPath64','MSBuildToolsRoot','MSBuildUserExtensionsPath','MSBuildProjectExtensionsPath','MSBUILDLEGACYEXTENSIONSPATH',
        'DirectoryBuildPropsPath','DirectoryBuildTargetsPath','AlternateCommonProps','CustomBeforeMicrosoftCommonProps','CustomAfterMicrosoftCommonProps','CustomBeforeMicrosoftCommonTargets','CustomAfterMicrosoftCommonTargets','CustomBeforeDirectoryBuildProps','CustomAfterDirectoryBuildProps','CustomBeforeDirectoryBuildTargets','CustomAfterDirectoryBuildTargets','ForceImportAfterCppDefaultProps','ForceImportBeforeCppProps','ForceImportAfterCppProps','ForceImportBeforeCppTargets','ForceImportAfterCppTargets','BaseIntermediateOutputPath','ProjectExtensionsPathForSpecifiedProject','ProjectToOverrideProjectExtensionsPath','NuGetPropsFile','NuGetRestoreTargets','AdditionalVCTargetsPath','DisableInstalledVCTargetsUse','DisableInstalledVCTargetsDefaultsUse','VcpkgInstalledVCTargets','VcpkgManifestDirectory','ImportBeforeCppProps','ImportAfterCppProps','ImportBeforeCppTargets','ImportAfterCppTargets','ImportDirectoryBuildProps','ImportDirectoryBuildTargets','ImportProjectExtensionProps','ImportProjectExtensionTargets','ImportUserLocationsByWildcardBeforeMicrosoftCommonProps','ImportUserLocationsByWildcardAfterMicrosoftCommonProps','ImportUserLocationsByWildcardBeforeMicrosoftCommonTargets','ImportUserLocationsByWildcardAfterMicrosoftCommonTargets'
    )
}

function Get-DirectHookNames {
    @(
        'DirectoryBuildPropsPath','DirectoryBuildTargetsPath','AlternateCommonProps','CustomBeforeMicrosoftCommonProps','CustomAfterMicrosoftCommonProps','CustomBeforeMicrosoftCommonTargets','CustomAfterMicrosoftCommonTargets','CustomBeforeDirectoryBuildProps','CustomAfterDirectoryBuildProps','CustomBeforeDirectoryBuildTargets','CustomAfterDirectoryBuildTargets','ForceImportAfterCppDefaultProps','ForceImportBeforeCppProps','ForceImportAfterCppProps','ForceImportBeforeCppTargets','ForceImportAfterCppTargets','BaseIntermediateOutputPath','ProjectExtensionsPathForSpecifiedProject','ProjectToOverrideProjectExtensionsPath','NuGetPropsFile','NuGetRestoreTargets','AdditionalVCTargetsPath','DisableInstalledVCTargetsUse','DisableInstalledVCTargetsDefaultsUse','VcpkgInstalledVCTargets','VcpkgManifestDirectory','ImportBeforeCppProps','ImportAfterCppProps','ImportBeforeCppTargets','ImportAfterCppTargets','ImportDirectoryBuildProps','ImportDirectoryBuildTargets','ImportProjectExtensionProps','ImportProjectExtensionTargets','ImportUserLocationsByWildcardBeforeMicrosoftCommonProps','ImportUserLocationsByWildcardAfterMicrosoftCommonProps','ImportUserLocationsByWildcardBeforeMicrosoftCommonTargets','ImportUserLocationsByWildcardAfterMicrosoftCommonTargets'
    )
}

function Get-BuilderArguments {
    param(
        [object]$Fixture,
        [string]$ArtifactDirectory,
        [hashtable]$Overrides = @{}
    )
    $values = [ordered]@{
        RookRoot = $Fixture.RookRoot
        ExpectedBranch = 'codex/gh-execute-intent-root-fix'
        ExpectedRookSha = $Fixture.RookSha
        ChirpRoot = $Fixture.ChirpRoot
        ExpectedChirpSha = $Fixture.ChirpSha
        ArtifactDirectory = $ArtifactDirectory
        GitPath = $Fixture.GitPath
        PowerShellPath = $WindowsPowerShell
        CmdPath = $CmdPath
        Msys2Bash = $Fixture.Toolchain.Msys2Bash
        VcvarsallPath = $Fixture.Toolchain.VcvarsallPath
        MsbuildPath = $Fixture.Toolchain.MsbuildPath
        DotnetPath = $Fixture.Toolchain.DotnetPath
        RhinoSystemDir = $Fixture.RhinoSystemDir
        RevitInstallDir = $Fixture.RevitInstallDir
        VcRedistRoot = $Fixture.VcRedistRoot
        OcctRoot = $Fixture.OcctRoot
        OcctRuntimeRoot = $Fixture.OcctRuntimeRoot
        IsccPath = $Fixture.Toolchain.IsccPath
    }
    foreach ($key in $Overrides.Keys) { $values[$key] = $Overrides[$key] }
    $arguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$Fixture.Wrapper,'-BuilderPath',$BuilderPath,'-FakeRhinoSdkPath',$Fixture.RhinoSdkRoot)
    foreach ($entry in $values.GetEnumerator()) { $arguments += @("-$($entry.Key)", [string]$entry.Value) }
    return ,$arguments
}

function Invoke-BuilderFixture {
    param(
        [object]$Fixture,
        [hashtable]$Overrides = @{},
        [hashtable]$AdditionalEnvironment = @{},
        [switch]$PrecreateNonemptyArtifact
    )
    $Fixture.NextRun = [int]$Fixture.NextRun + 1
    $artifact = Join-Path $Fixture.Root ("artifacts\run-{0:D3}" -f $Fixture.NextRun)
    if ($PrecreateNonemptyArtifact) {
        New-Directory -Path $artifact | Out-Null
        Write-Utf8NoBom -Path (Join-Path $artifact 'stale.txt') -Text 'stale'
    }
    if ($Overrides.ContainsKey('ArtifactDirectory')) { $artifact = [string]$Overrides['ArtifactDirectory'] }

    $environment = @{
        APPDATA = $Fixture.AppData
        T9_FIXTURE_PYTHON_ROOT = $FixturePythonRoot
        T9_STUB_LOG = $Fixture.StubLog
        T9_CREATE_INERT = '0'
        T9_MUTATE_LIVE = '0'
        T9_WRITE_ERROR = '0'
        T9_MUTATE_SOURCE_FILE = ''
        T9_MUTATE_EXTERNAL_FILE = ''
        T9_MUTATE_STAGED_SOURCE = '0'
        T9_MUTATE_ALLOWED_EARLY = '0'
        T9_MUTATE_THIRD_TRACKED = '0'
        T9_MUTATE_WHEEL_VALIDATOR = '0'
        T9_MUTATE_FFMPEG_VALIDATOR = '0'
        T9_FAKE_RHINO_SDK_PATH = ''
        T9_RHINO_SDK_DRIFT_PATH = ''
        T9_MUTATE_ALLOWED_LATE = '0'
        T9_MUTATE_WHEEL_LATE = '0'
        T9_MUTATE_MANIFEST_LATE = '0'
        T9_MUTATE_WHEEL_IN_ISCC = '0'
        OCCT_ROOT = $Fixture.DecoyOcct
        PATH = $Fixture.DecoyPath
    }
    foreach ($name in Get-ScrubNames) { $environment[$name] = "T9_TRIP_$name" }
    foreach ($name in Get-DirectHookNames) { $environment[$name] = Join-Path $Fixture.TripRoot "$name.props" }
    $environment['MSBUILD_EXE_PATH'] = Join-Path $Fixture.DecoyPath 'MSBuild.cmd'
    foreach ($key in $AdditionalEnvironment.Keys) { $environment[$key] = [string]$AdditionalEnvironment[$key] }
    $args = Get-BuilderArguments -Fixture $Fixture -ArtifactDirectory $artifact -Overrides $Overrides
    $result = Invoke-Process -FilePath $WindowsPowerShell -Arguments $args -WorkingDirectory $Fixture.Root -Environment $environment
    Add-Member -InputObject $result -NotePropertyName ArtifactDirectory -NotePropertyValue $artifact
    return $result
}

function Invoke-Test {
    param([string]$Name, [scriptblock]$Body)
    & $Body
    $script:TestsPassed++
    Write-Host "PASS $Name"
}

function Assert-FailedWith {
    param([object]$Result, [string]$Marker, [string]$Message)
    Assert-True -Condition ($Result.ExitCode -ne 0) -Message "$Message Builder unexpectedly succeeded."
    Assert-Contains -Text $Result.Output -Expected $Marker -Message "$Message Output: $($Result.Output)"
    Assert-NotContains -Text $Result.Output -Unexpected 'ParserError' -Message "$Message was a parser failure."
    Assert-NotContains -Text $Result.Output -Unexpected 'CommandNotFoundException' -Message "$Message was an infrastructure failure."
}

function Test-StaticContract {
    $builder = Get-Content -LiteralPath $BuilderPath -Raw
    $builderTokens = $null
    $builderErrors = $null
    $builderAst = [System.Management.Automation.Language.Parser]::ParseFile($BuilderPath, [ref]$builderTokens, [ref]$builderErrors)
    Assert-True -Condition ($builderErrors.Count -eq 0) -Message "Builder parser errors: $($builderErrors | Out-String)"
    $testTokens = $null
    $testErrors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($GuardPath, [ref]$testTokens, [ref]$testErrors)
    Assert-True -Condition ($testErrors.Count -eq 0) -Message "Guard parser errors: $($testErrors | Out-String)"

    $requiredParameters = @('RookRoot','ExpectedBranch','ExpectedRookSha','ChirpRoot','ExpectedChirpSha','ArtifactDirectory','GitPath','PowerShellPath','CmdPath','Msys2Bash','VcvarsallPath','MsbuildPath','DotnetPath','RhinoSystemDir','RevitInstallDir','VcRedistRoot','OcctRoot','OcctRuntimeRoot','IsccPath') | Sort-Object
    $actualParameters = @($builderAst.ParamBlock.Parameters | ForEach-Object { $_.Name.VariablePath.UserPath }) | Sort-Object
    Assert-True -Condition (@(Compare-Object $requiredParameters $actualParameters).Count -eq 0) -Message "Builder parameter set mismatch: $(@(Compare-Object $requiredParameters $actualParameters) | Out-String)"

    $lines = @(Get-Content -LiteralPath $BuilderPath)
    $firstAfterParam = $builderAst.ParamBlock.Extent.EndLineNumber
    $executable = @()
    for ($index = $firstAfterParam; $index -lt $lines.Count -and $executable.Count -lt 2; $index++) {
        $trimmed = $lines[$index].Trim()
        if ($trimmed -and -not $trimmed.StartsWith('#')) { $executable += $trimmed }
    }
    Assert-Equal -Actual $executable[0] -Expected 'Set-StrictMode -Version Latest' -Message 'Builder first executable line must enable strict mode.'
    Assert-Equal -Actual $executable[1] -Expected '$ErrorActionPreference = ''Stop''' -Message 'Builder second executable line must enable fail-fast behavior.'
    $guardLines = @(Get-Content -LiteralPath $GuardPath | Where-Object { $_.Trim() -and -not $_.Trim().StartsWith('#') } | Select-Object -First 2)
    Assert-Equal -Actual $guardLines[0].Trim() -Expected 'Set-StrictMode -Version Latest' -Message 'Guard first executable line must enable strict mode.'
    Assert-Equal -Actual $guardLines[1].Trim() -Expected '$ErrorActionPreference = ''Stop''' -Message 'Guard second executable line must enable fail-fast behavior.'

    foreach ($name in Get-ScrubNames) { Assert-Contains -Text $builder -Expected "'$name'" -Message "Builder does not pin scrub name $name." }
    foreach ($argument in @(
        '/p:ImportDirectoryBuildProps=false','/p:ImportDirectoryBuildTargets=false','/p:ImportProjectExtensionProps=false','/p:ImportProjectExtensionTargets=false',
        '/p:ImportUserLocationsByWildcardBeforeMicrosoftCommonProps=false','/p:ImportUserLocationsByWildcardAfterMicrosoftCommonProps=false',
        '/p:ImportUserLocationsByWildcardBeforeMicrosoftCommonTargets=false','/p:ImportUserLocationsByWildcardAfterMicrosoftCommonTargets=false'
    )) { Assert-Contains -Text $builder -Expected "'$argument'" -Message "Builder does not pin native import-disable argument $argument." }
    foreach ($lib in @('TKernel.lib','TKMath.lib','TKG2d.lib','TKG3d.lib','TKGeomBase.lib','TKGeomAlgo.lib','TKBRep.lib','TKTopAlgo.lib','TKPrim.lib','TKBO.lib','TKBool.lib','TKShHealing.lib','TKMesh.lib')) {
        Assert-Contains -Text $builder -Expected "'$lib'" -Message "Builder does not pin OCCT import library $lib."
    }
    foreach ($required in @('non_publishable','containment-candidate.json','containment-candidate.sha256','private_python','pth_files','source_inventory','build_inventory','output_inventory','RhinoPluginDir','3.11.9','2def4c0009b3b41de681fe23880f741189c0119820260a35a48f048d2b8830df')) {
        Assert-Contains -Text $builder -Expected $required -Message "Builder omits required identity/build contract $required."
    }
    Assert-NotContains -Text $builder.ToLowerInvariant() -Unexpected 'git fetch' -Message 'Builder may not fetch from a remote.'
    Assert-NotContains -Text $builder -Unexpected 'validate-release-artifacts.ps1' -Message 'Builder may not invoke normal release validation.'
    Assert-NotContains -Text $builder -Unexpected 'build-release' -Message 'Builder may not invoke either build-release skill.'
    Assert-NotContains -Text $builder.ToLowerInvariant() -Unexpected 'dotnet publish' -Message 'Builder may not publish managed projects.'
    Assert-NotContains -Text $builder -Unexpected '$env:OCCT_ROOT' -Message 'Builder may not resolve OCCT from ambient OCCT_ROOT.'
    Assert-NotContains -Text $builder -Unexpected '$process.WaitForExit()' -Message 'Subprocess completion may not use an unbounded WaitForExit call.'
    Assert-NotContains -Text $builder -Unexpected '$copyTask.Wait()' -Message 'Binary subprocess output drain may not wait without a timeout.'
    Assert-NotContains -Text $builder -Unexpected '$stdoutTask.Result' -Message 'Text subprocess stdout may not be read through an unbounded task result.'
    Assert-NotContains -Text $builder -Unexpected '$stderrTask.Result' -Message 'Subprocess stderr may not be read through an unbounded task result.'
    Assert-Contains -Text $builder -Expected 'StreamDrainTimeoutMilliseconds' -Message 'Builder does not pin a bounded redirected-stream drain.'
}

function Test-PreflightGuards {
    param([object]$Fixture)

    $result = Invoke-BuilderFixture -Fixture $Fixture -Overrides @{ ExpectedBranch = 'wrong/branch' }
    Assert-FailedWith -Result $result -Marker 'Rook branch mismatch' -Message 'Wrong Rook branch was not rejected.'

    $result = Invoke-BuilderFixture -Fixture $Fixture -Overrides @{ ExpectedRookSha = ('0' * 40) }
    Assert-FailedWith -Result $result -Marker 'Rook HEAD mismatch' -Message 'Rook SHA drift was not rejected.'

    $result = Invoke-BuilderFixture -Fixture $Fixture -Overrides @{ ExpectedChirpSha = ('1' * 40) }
    Assert-FailedWith -Result $result -Marker 'Chirp HEAD mismatch' -Message 'Chirp SHA drift was not rejected.'

    $result = Invoke-BuilderFixture -Fixture $Fixture -Overrides @{ RookRoot = (Join-Path $Fixture.RookRoot 'mcp_server') }
    Assert-FailedWith -Result $result -Marker 'RookRoot is not the Git top-level' -Message 'Wrong Rook root was not rejected.'

    $dirtyRook = Join-Path $Fixture.RookRoot 'dirty-untracked.txt'
    try {
        Write-Utf8NoBom -Path $dirtyRook -Text 'dirty'
        $result = Invoke-BuilderFixture -Fixture $Fixture
        Assert-FailedWith -Result $result -Marker 'Rook source is not clean' -Message 'Dirty Rook input was not rejected.'
    } finally { Remove-Item -LiteralPath $dirtyRook -Force -ErrorAction SilentlyContinue }

    $dirtyChirp = Join-Path $Fixture.ChirpRoot 'dirty-untracked.txt'
    try {
        Write-Utf8NoBom -Path $dirtyChirp -Text 'dirty'
        $result = Invoke-BuilderFixture -Fixture $Fixture
        Assert-FailedWith -Result $result -Marker 'Chirp source is not clean' -Message 'Dirty Chirp input was not rejected.'
    } finally { Remove-Item -LiteralPath $dirtyChirp -Force -ErrorAction SilentlyContinue }

    $result = Invoke-BuilderFixture -Fixture $Fixture -PrecreateNonemptyArtifact
    Assert-FailedWith -Result $result -Marker 'ArtifactDirectory must be empty' -Message 'Stale output was not rejected.'

    $missingTool = Join-Path $Fixture.Root 'missing\bash.exe'
    $result = Invoke-BuilderFixture -Fixture $Fixture -Overrides @{ Msys2Bash = $missingTool }
    Assert-FailedWith -Result $result -Marker 'Msys2Bash is missing' -Message 'Missing external executable was not rejected.'

    $missingRoot = Join-Path $Fixture.Root 'missing\Revit'
    $result = Invoke-BuilderFixture -Fixture $Fixture -Overrides @{ RevitInstallDir = $missingRoot }
    Assert-FailedWith -Result $result -Marker 'RevitInstallDir is missing' -Message 'Missing external root was not rejected.'

    $overlapArtifact = Join-Path $Fixture.RookRoot '_artifact_must_not_be_created'
    $result = Invoke-BuilderFixture -Fixture $Fixture -Overrides @{ ArtifactDirectory = $overlapArtifact }
    Assert-FailedWith -Result $result -Marker 'ArtifactDirectory overlaps a source root' -Message 'Overlapping artifact/source roots were not rejected.'
    Assert-True -Condition (-not (Test-Path -LiteralPath $overlapArtifact)) -Message 'Overlap rejection must occur before artifact creation.'

    $result = Invoke-BuilderFixture -Fixture $Fixture -Overrides @{ RevitInstallDir = $Fixture.RhinoSystemDir }
    Assert-FailedWith -Result $result -Marker 'External input roots overlap' -Message 'Overlapping external input roots were not rejected.'

    $result = Invoke-BuilderFixture -Fixture $Fixture -AdditionalEnvironment @{ T9_FAKE_RHINO_SDK_PATH = $Fixture.RhinoSystemDir }
    Assert-FailedWith -Result $result -Marker 'External input roots overlap' -Message 'Overlapping registry-resolved Rhino SDK authority was not rejected.'

    $liveArtifact = Join-Path $Fixture.LivePlugin '_candidate_must_not_be_created'
    $result = Invoke-BuilderFixture -Fixture $Fixture -Overrides @{ ArtifactDirectory = $liveArtifact }
    Assert-FailedWith -Result $result -Marker 'ArtifactDirectory overlaps the live RookNative plug-in directory' -Message 'Artifact/live plug-in overlap was not rejected.'
    Assert-True -Condition (-not (Test-Path -LiteralPath $liveArtifact)) -Message 'Artifact/live overlap rejection occurred after artifact mutation.'

    $malformedOcct = New-Directory -Path (Join-Path $Fixture.Root 'external\MalformedOcct')
    $malformedRuntime = New-Directory -Path (Join-Path $malformedOcct 'win64\vc14\bin')
    $result = Invoke-BuilderFixture -Fixture $Fixture -Overrides @{ OcctRoot = $malformedOcct; OcctRuntimeRoot = $malformedRuntime }
    Assert-FailedWith -Result $result -Marker 'OCCT header is missing' -Message 'Malformed OCCT root was not rejected.'

    $disagreedRuntime = New-Directory -Path (Join-Path $Fixture.Root 'external\OtherOcctRuntime')
    $result = Invoke-BuilderFixture -Fixture $Fixture -Overrides @{ OcctRuntimeRoot = $disagreedRuntime }
    Assert-FailedWith -Result $result -Marker 'OcctRuntimeRoot must equal' -Message 'OCCT build/runtime root disagreement was not rejected.'

    $runtimeDll = Join-Path $Fixture.OcctRuntimeRoot 'TKernel.dll'
    $savedRuntimeDll = "$runtimeDll.saved"
    try {
        Move-Item -LiteralPath $runtimeDll -Destination $savedRuntimeDll
        $result = Invoke-BuilderFixture -Fixture $Fixture
        Assert-FailedWith -Result $result -Marker 'OCCT runtime DLL is missing' -Message 'Missing installer-consumed OCCT DLL was not rejected.'
    } finally {
        if (Test-Path -LiteralPath $savedRuntimeDll -PathType Leaf) { Move-Item -LiteralPath $savedRuntimeDll -Destination $runtimeDll }
    }
}

function Test-InjectedNonterminatingErrorStopsNextStage {
    param([object]$Fixture)
    $result = Invoke-BuilderFixture -Fixture $Fixture -AdditionalEnvironment @{ T9_WRITE_ERROR = '1' }
    Assert-FailedWith -Result $result -Marker 'stage-python-runtime failed with exit code' -Message 'Normally nonterminating stage error did not fail fast.'
    $nextStageMarker = Join-Path $result.ArtifactDirectory 'stage\Rook\wheelhouse.args.txt'
    Assert-True -Condition (-not (Test-Path -LiteralPath $nextStageMarker)) -Message 'Builder reached the next stage after the injected Write-Error.'
}

function Test-IdentityDriftFailsBeforeMsbuild {
    param([object]$Fixture)
    $vcvars = $Fixture.Toolchain.VcvarsallPath
    $originalVcvars = Get-Content -LiteralPath $vcvars -Raw
    $header = Join-Path $Fixture.OcctRoot 'inc\Standard.hxx'
    $originalHeader = Get-Content -LiteralPath $header -Raw
    try {
        $mutation = ">> `"$header`" echo drift"
        $mutatingVcvars = $originalVcvars -replace '(?im)^exit /b 0\s*$', ($mutation + "`r`nexit /b 0")
        Write-Utf8NoBom -Path $vcvars -Text $mutatingVcvars
        $result = Invoke-BuilderFixture -Fixture $Fixture
        if (-not $result.Output.Contains('OCCT input identity drift')) {
            $nativeLogs = @(Get-ChildItem -LiteralPath (Join-Path $result.ArtifactDirectory 'logs') -Filter '*-native-environment.*.log' -File -ErrorAction SilentlyContinue | ForEach-Object { "[$($_.Name)]`n$(Get-Content -LiteralPath $_.FullName -Raw)" }) -join "`n"
            $probePath = Join-Path $result.ArtifactDirectory 'native-environment\probe-vcvars.cmd'
            $probeText = if (Test-Path -LiteralPath $probePath -PathType Leaf) { Get-Content -LiteralPath $probePath -Raw } else { '<missing>' }
            $result.Output = $result.Output + "`nNATIVE LOGS:`n" + $nativeLogs + "`nPROBE BATCH:`n" + $probeText + "`nVCVARS STUB:`n" + (Get-Content -LiteralPath $vcvars -Raw)
        }
        Assert-FailedWith -Result $result -Marker 'OCCT input identity drift' -Message 'OCCT identity drift was not rejected before native build.'
        $msbuildMarker = Join-Path $result.ArtifactDirectory 'stage\Rook\src\RookNative\native-msbuild.args.txt'
        Assert-True -Condition (-not (Test-Path -LiteralPath $msbuildMarker)) -Message 'MSBuild ran after OCCT identity drift.'
    } finally {
        Write-Utf8NoBom -Path $vcvars -Text $originalVcvars
        Write-Utf8NoBom -Path $header -Text $originalHeader
    }

    $rhinoReference = Join-Path $Fixture.RhinoSystemDir 'RhinoCommon.dll'
    $originalRhinoReference = Get-Content -LiteralPath $rhinoReference -Raw
    $mutationMarker = Join-Path $Fixture.StubLog 'external-mutated.marker'
    try {
        Remove-Item -LiteralPath $mutationMarker -Force -ErrorAction SilentlyContinue
        $result = Invoke-BuilderFixture -Fixture $Fixture -AdditionalEnvironment @{ T9_MUTATE_EXTERNAL_FILE = $rhinoReference }
        Assert-FailedWith -Result $result -Marker 'Rhino managed reference identity drift' -Message 'Managed-reference identity drift was not rejected.'
        $installer = Join-Path $result.ArtifactDirectory 'stage\Rook\installer\output\Rook-Setup-9.8.7.exe'
        Assert-True -Condition (-not (Test-Path -LiteralPath $installer)) -Message 'Installer ran after managed-reference identity drift.'
    } finally {
        Write-Utf8NoBom -Path $rhinoReference -Text $originalRhinoReference
        Remove-Item -LiteralPath $mutationMarker -Force -ErrorAction SilentlyContinue
    }

    $originalVcvars = Get-Content -LiteralPath $vcvars -Raw
    try {
        $forbiddenHook = Join-Path $Fixture.TripRoot 'MSBuildUserExtensionsPath.props'
        $forbiddenVcvars = $originalVcvars -replace '(?im)^exit /b 0\s*$', ("set `"MSBuildUserExtensionsPath=$forbiddenHook`"`r`nexit /b 0")
        Write-Utf8NoBom -Path $vcvars -Text $forbiddenVcvars
        $result = Invoke-BuilderFixture -Fixture $Fixture
        Assert-FailedWith -Result $result -Marker 'Captured native environment retained forbidden authority MSBuildUserExtensionsPath' -Message 'Post-vcvars user-extension authority was not rejected.'
        $msbuildMarker = Join-Path $result.ArtifactDirectory 'stage\Rook\src\RookNative\native-msbuild.args.txt'
        Assert-True -Condition (-not (Test-Path -LiteralPath $msbuildMarker)) -Message 'MSBuild ran after forbidden post-vcvars authority was captured.'
    } finally {
        Write-Utf8NoBom -Path $vcvars -Text $originalVcvars
    }

    $originalVcvars = Get-Content -LiteralPath $vcvars -Raw
    try {
        $outsideVcvars = $originalVcvars -replace '(?im)^set "MSBuildSDKsPath=.*"\r?$', ("set `"MSBuildSDKsPath=$($Fixture.TripRoot)`"")
        Write-Utf8NoBom -Path $vcvars -Text $outsideVcvars
        $result = Invoke-BuilderFixture -Fixture $Fixture
        Assert-FailedWith -Result $result -Marker 'MSBuildSDKsPath is outside the explicit VS/SDK/SystemRoot authority' -Message 'An outside-root post-vcvars MSBuild path was not rejected.'
        $msbuildMarker = Join-Path $result.ArtifactDirectory 'stage\Rook\src\RookNative\native-msbuild.args.txt'
        Assert-True -Condition (-not (Test-Path -LiteralPath $msbuildMarker)) -Message 'MSBuild ran after an outside-root post-vcvars path was captured.'
    } finally {
        Write-Utf8NoBom -Path $vcvars -Text $originalVcvars
    }

    $originalVcvars = Get-Content -LiteralPath $vcvars -Raw
    try {
        $reparseVcvars = $originalVcvars -replace '(?im)^set "INCLUDE=.*"\r?$', ("set `"INCLUDE=$($Fixture.ReparseLink)`"")
        Write-Utf8NoBom -Path $vcvars -Text $reparseVcvars
        $result = Invoke-BuilderFixture -Fixture $Fixture
        Assert-FailedWith -Result $result -Marker 'INCLUDE must not contain a reparse-point path component' -Message 'A post-vcvars path beneath a junction was not rejected.'
        $msbuildMarker = Join-Path $result.ArtifactDirectory 'stage\Rook\src\RookNative\native-msbuild.args.txt'
        Assert-True -Condition (-not (Test-Path -LiteralPath $msbuildMarker)) -Message 'MSBuild ran after a reparse-point native path was captured.'
    } finally {
        Write-Utf8NoBom -Path $vcvars -Text $originalVcvars
    }

    $result = Invoke-BuilderFixture -Fixture $Fixture -AdditionalEnvironment @{ T9_RHINO_SDK_DRIFT_PATH = $Fixture.RhinoSdkDriftRoot }
    Assert-FailedWith -Result $result -Marker 'Registry-resolved Rhino SDK authority changed' -Message 'Registry-resolved Rhino SDK drift was not rejected before MSBuild.'
    $msbuildMarker = Join-Path $result.ArtifactDirectory 'stage\Rook\src\RookNative\native-msbuild.args.txt'
    Assert-True -Condition (-not (Test-Path -LiteralPath $msbuildMarker)) -Message 'MSBuild ran after registry-resolved Rhino SDK drift.'
}

function Test-OriginalSourceChangeIsRejected {
    param([object]$Fixture)
    $mutation = Join-Path $Fixture.RookRoot 'source-changed-during-build.txt'
    try {
        $result = Invoke-BuilderFixture -Fixture $Fixture -AdditionalEnvironment @{ T9_MUTATE_SOURCE_FILE = $mutation }
        if (-not $result.Output.Contains('Rook source changed during candidate construction')) {
            $managedLogs = @(Get-ChildItem -LiteralPath (Join-Path $result.ArtifactDirectory 'logs') -Filter '*-build-rook-managed*' -File -ErrorAction SilentlyContinue | ForEach-Object { "[$($_.Name)]`n$(Get-Content -LiteralPath $_.FullName -Raw)" }) -join "`n"
            $result.Output = $result.Output + "`nMANAGED LOGS:`n" + $managedLogs + "`nDOTNET STUB:`n" + (Get-Content -LiteralPath $Fixture.Toolchain.DotnetPath -Raw)
        }
        Assert-FailedWith -Result $result -Marker 'Rook source changed during candidate construction' -Message 'Original source mutation was not rejected.'
        Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $result.ArtifactDirectory 'containment-candidate.json'))) -Message 'Identity was written after source mutation.'
    } finally { Remove-Item -LiteralPath $mutation -Force -ErrorAction SilentlyContinue }
}

function Test-StagedSourceChangeIsRejected {
    param([object]$Fixture)
    $result = Invoke-BuilderFixture -Fixture $Fixture -AdditionalEnvironment @{ T9_MUTATE_STAGED_SOURCE = '1' }
    Assert-FailedWith -Result $result -Marker 'StagedRook tracked source changed during candidate construction' -Message 'Tracked staged-source mutation was not rejected.'
    $msbuildMarker = Join-Path $result.ArtifactDirectory 'stage\Rook\src\RookNative\native-msbuild.args.txt'
    Assert-True -Condition (-not (Test-Path -LiteralPath $msbuildMarker)) -Message 'MSBuild ran after tracked staged-source mutation.'

    $result = Invoke-BuilderFixture -Fixture $Fixture -AdditionalEnvironment @{ T9_MUTATE_ALLOWED_EARLY = '1' }
    Assert-FailedWith -Result $result -Marker 'StagedRook tracked source changed during candidate construction' -Message 'Tracked FFmpeg output changed before its build stage was not rejected.'
    $wheelMarker = Join-Path $result.ArtifactDirectory 'stage\Rook\wheelhouse.args.txt'
    Assert-True -Condition (-not (Test-Path -LiteralPath $wheelMarker)) -Message 'Wheelhouse build ran after premature tracked-output mutation.'

    $result = Invoke-BuilderFixture -Fixture $Fixture -AdditionalEnvironment @{ T9_MUTATE_THIRD_TRACKED = '1' }
    Assert-FailedWith -Result $result -Marker 'StagedRook tracked source changed during candidate construction' -Message 'A third tracked delta after the FFmpeg stage was not rejected.'
    $msbuildMarker = Join-Path $result.ArtifactDirectory 'stage\Rook\src\RookNative\native-msbuild.args.txt'
    Assert-True -Condition (-not (Test-Path -LiteralPath $msbuildMarker)) -Message 'MSBuild ran after a third post-FFmpeg tracked delta.'

    $result = Invoke-BuilderFixture -Fixture $Fixture -AdditionalEnvironment @{ T9_MUTATE_WHEEL_VALIDATOR = '1' }
    Assert-FailedWith -Result $result -Marker 'StagedRook tracked source changed during candidate construction' -Message 'A wheel build mutation of its validator was not rejected.'
    $validatorMarker = Join-Path $result.ArtifactDirectory 'stage\Rook\validate-wheelhouse.args.txt'
    Assert-True -Condition (-not (Test-Path -LiteralPath $validatorMarker)) -Message 'Wheelhouse validator ran after its tracked script was mutated.'

    $result = Invoke-BuilderFixture -Fixture $Fixture -AdditionalEnvironment @{ T9_MUTATE_FFMPEG_VALIDATOR = '1' }
    Assert-FailedWith -Result $result -Marker 'StagedRook tracked source changed during candidate construction' -Message 'An FFmpeg build mutation of its validator was not rejected.'
    $validatorMarker = Join-Path $result.ArtifactDirectory 'stage\Rook\ffmpeg-validate.args.txt'
    Assert-True -Condition (-not (Test-Path -LiteralPath $validatorMarker)) -Message 'FFmpeg validator ran after its tracked script was mutated.'
}

function Test-TrackedBuildOutputAllowance {
    param([object]$Fixture)
    $result = Invoke-BuilderFixture -Fixture $Fixture
    Assert-True -Condition ($result.ExitCode -eq 0) -Message "Exact post-FFmpeg tracked build outputs were not allowed. Output: $($result.Output)"
    $stagedRook = Join-Path $result.ArtifactDirectory 'stage\Rook'
    $changed = @(Invoke-Git -GitPath $Fixture.GitPath -WorkingDirectory $stagedRook -Arguments @('diff','--name-only','HEAD','--') -ErrorAction Stop) -split "`r?`n" | Where-Object { $_ }
    $expected = @('third_party/ffmpeg/ffmpeg-provenance.json','third_party/ffmpeg/ffmpeg.exe')
    Assert-True -Condition (@(Compare-Object $expected $changed -SyncWindow 0).Count -eq 0) -Message "Tracked build-output delta mismatch: $($changed -join ', ')"
    $identity = Get-Content -LiteralPath (Join-Path $result.ArtifactDirectory 'containment-candidate.json') -Raw | ConvertFrom-Json
    Assert-True -Condition (@(Compare-Object $expected @($identity.sources.rook.tracked_build_output_paths) -SyncWindow 0).Count -eq 0) -Message 'Candidate identity did not bind the exact tracked build-output allowance.'
    $inventoryPaths = @($identity.inventories.build_inventory.files | ForEach-Object { [string]$_.relative_path })
    foreach ($path in $expected) {
        Assert-True -Condition ($inventoryPaths -contains "Rook/$path") -Message "Build inventory omitted allowed tracked output $path."
    }
    $trackedProjectionPaths = @($identity.inputs.ffmpeg.tracked_build_outputs.files | ForEach-Object { [string]$_.relative_path })
    Assert-StringSequenceEqual -Actual $trackedProjectionPaths -Expected @(Get-GuardOrdinalSortedStrings -Values $expected) -Message 'FFmpeg identity did not freeze the exact tracked-output projection.'
    $commands = @{}
    foreach ($command in $identity.commands) { $commands[[string]$command.name] = $command }
    $expectedRookClone = @('-c','core.autocrlf=false','clone','--local','--no-hardlinks','--no-checkout','--',$Fixture.RookRoot,$stagedRook)
    $expectedChirpClone = @('-c','core.autocrlf=false','clone','--local','--no-hardlinks','--no-checkout','--',$Fixture.ChirpRoot,(Join-Path $result.ArtifactDirectory 'stage\Chirp'))
    Assert-True -Condition (@(Compare-Object $expectedRookClone @($commands['clone-rook'].arguments) -SyncWindow 0).Count -eq 0) -Message 'Rook staging clone was not exact and local-only.'
    Assert-True -Condition (@(Compare-Object $expectedChirpClone @($commands['clone-chirp'].arguments) -SyncWindow 0).Count -eq 0) -Message 'Chirp staging clone was not exact and local-only.'
    $lfsDisabledCheckout = @('-c','filter.lfs.process=','-c','filter.lfs.smudge=','-c','filter.lfs.required=false','checkout','--detach')
    $expectedRookCheckout = @('-C',$stagedRook) + $lfsDisabledCheckout + @($Fixture.RookSha)
    $expectedChirpCheckout = @('-C',(Join-Path $result.ArtifactDirectory 'stage\Chirp')) + $lfsDisabledCheckout + @($Fixture.ChirpSha)
    Assert-True -Condition (@(Compare-Object $expectedRookCheckout @($commands['checkout-rook'].arguments) -SyncWindow 0).Count -eq 0) -Message 'Rook checkout did not disable LFS process/smudge network authority.'
    Assert-True -Condition (@(Compare-Object $expectedChirpCheckout @($commands['checkout-chirp'].arguments) -SyncWindow 0).Count -eq 0) -Message 'Chirp checkout did not disable LFS process/smudge network authority.'
    foreach ($stage in @($stagedRook,(Join-Path $result.ArtifactDirectory 'stage\Chirp'))) {
        foreach ($key in @('filter.lfs.process','filter.lfs.smudge','filter.lfs.clean')) {
            Assert-Equal -Actual (Invoke-Git -GitPath $Fixture.GitPath -WorkingDirectory $stage -Arguments @('config','--local','--get',$key)) -Expected '' -Message "$key was not persistently disabled in $stage."
        }
        Assert-Equal -Actual (Invoke-Git -GitPath $Fixture.GitPath -WorkingDirectory $stage -Arguments @('config','--local','--get','filter.lfs.required')) -Expected 'false' -Message "filter.lfs.required was not disabled in $stage."
    }
    foreach ($command in $identity.commands) {
        Assert-True -Condition (@($command.arguments | Where-Object { [string]$_ -match '(?i)(^|\W)fetch(\W|$)|^https?://' }).Count -eq 0) -Message "Candidate command $($command.name) retained network fetch authority."
    }
}

function Test-ValidatedNativeEnvironmentIsReused {
    param([object]$Fixture)
    $vcvars = $Fixture.Toolchain.VcvarsallPath
    $originalVcvars = Get-Content -LiteralPath $vcvars -Raw
    try {
        $statefulTrip = @'
if exist "%TEMP%\t9-vcvars-first.marker" (
  > "%TEMP%\t9-vcvars-second.hit" echo second
  set "CL=T9_SECOND_VCVARS_TRIP"
) else (
  > "%TEMP%\t9-vcvars-first.marker" echo first
)
exit /b 0
'@ -replace "`n", "`r`n"
        $statefulVcvars = $originalVcvars -replace '(?im)^exit /b 0\s*$', $statefulTrip
        Write-Utf8NoBom -Path $vcvars -Text $statefulVcvars
        $result = Invoke-BuilderFixture -Fixture $Fixture
        Assert-True -Condition ($result.ExitCode -eq 0) -Message "Validated native environment was not reused for MSBuild. Output: $($result.Output)"
        $secondHit = Join-Path $result.ArtifactDirectory '_native_environment\TEMP\t9-vcvars-second.hit'
        Assert-True -Condition (-not (Test-Path -LiteralPath $secondHit)) -Message 'vcvarsall ran a second time after native-environment validation.'
    } finally {
        Write-Utf8NoBom -Path $vcvars -Text $originalVcvars
    }
}

function Test-ManagedDeploymentGuards {
    param([object]$Fixture)
    $result = Invoke-BuilderFixture -Fixture $Fixture -AdditionalEnvironment @{ T9_CREATE_INERT = '1' }
    Assert-FailedWith -Result $result -Marker 'inert RhinoPluginDir was created' -Message 'Managed build inert deployment path creation was not rejected.'
    $dotnetLogs = @(Get-ChildItem -LiteralPath $Fixture.StubLog -Filter 'dotnet-*.args.txt' -File)
    Assert-True -Condition ($dotnetLogs.Count -ge 1) -Message 'Managed build stub was not reached in inert-path guard.'

    $mutatedLive = Join-Path $Fixture.LivePlugin 'mutated.txt'
    try {
        $result = Invoke-BuilderFixture -Fixture $Fixture -AdditionalEnvironment @{ T9_MUTATE_LIVE = '1' }
        Assert-FailedWith -Result $result -Marker 'live RookNative plug-in projection changed' -Message 'Live APPDATA projection mutation was not rejected.'
        Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $result.ArtifactDirectory 'containment-candidate.json'))) -Message 'Identity was written after live projection mutation.'
    } finally { Remove-Item -LiteralPath $mutatedLive -Force -ErrorAction SilentlyContinue }

    $result = Invoke-BuilderFixture -Fixture $Fixture -AdditionalEnvironment @{ T9_MUTATE_ALLOWED_LATE = '1' }
    Assert-FailedWith -Result $result -Marker 'Tracked FFmpeg build output identity drift' -Message 'A later managed-stage mutation of an allowed FFmpeg output was not rejected.'
    $bimOutput = Join-Path $result.ArtifactDirectory 'stage\Rook\src\RookBim\bin\Release\net48\RookBim.dll'
    Assert-True -Condition (-not (Test-Path -LiteralPath $bimOutput)) -Message 'RookBim ran after tracked FFmpeg output identity drift.'

    $result = Invoke-BuilderFixture -Fixture $Fixture -AdditionalEnvironment @{ T9_MUTATE_WHEEL_LATE = '1' }
    Assert-FailedWith -Result $result -Marker 'Validated Python wheelhouse identity drift' -Message 'A post-validation wheelhouse mutation was not rejected before packaging.'
    Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $result.ArtifactDirectory 'stage\Rook\installer\output\Rook-Setup-9.8.7.exe'))) -Message 'Installer ran after a validated wheelhouse mutation.'

    $result = Invoke-BuilderFixture -Fixture $Fixture -AdditionalEnvironment @{ T9_MUTATE_MANIFEST_LATE = '1' }
    Assert-FailedWith -Result $result -Marker 'Validated FFmpeg manifest identity drift' -Message 'A post-validation FFmpeg manifest mutation was not rejected before packaging.'
    Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $result.ArtifactDirectory 'stage\Rook\installer\output\Rook-Setup-9.8.7.exe'))) -Message 'Installer ran after a validated FFmpeg manifest mutation.'

    $result = Invoke-BuilderFixture -Fixture $Fixture -AdditionalEnvironment @{ T9_MUTATE_WHEEL_IN_ISCC = '1' }
    Assert-FailedWith -Result $result -Marker 'Validated Python wheelhouse identity drift' -Message 'An installer-stage wheelhouse mutation was not rejected after packaging.'
    Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $result.ArtifactDirectory 'containment-candidate.json'))) -Message 'Identity was written after an installer-stage wheelhouse mutation.'
}

function Assert-SortedProjection {
    param([object[]]$Files, [string]$Label)
    $actual = @($Files | ForEach-Object { [string]$_.relative_path })
    $expected = @(Get-GuardOrdinalSortedStrings -Values $actual)
    Assert-True -Condition (@(Compare-Object $expected $actual -SyncWindow 0).Count -eq 0) -Message "$Label is not sorted by relative_path."
    foreach ($file in $Files) {
        Assert-True -Condition ([string]$file.sha256 -match '^[0-9a-f]{64}$') -Message "$Label contains a non-SHA256 digest."
        Assert-True -Condition ([long]$file.size -ge 0) -Message "$Label contains a negative size."
    }
}

function Test-FakeCandidateBuild {
    param([object]$Fixture)
    $beforeLiveHash = (Get-FileHash -LiteralPath (Join-Path $Fixture.LivePlugin 'sentinel\keep.bin') -Algorithm SHA256).Hash
    $result = Invoke-BuilderFixture -Fixture $Fixture
    Assert-True -Condition ($result.ExitCode -eq 0) -Message "Fake-only candidate build failed: $($result.Output)"
    $identityPath = Join-Path $result.ArtifactDirectory 'containment-candidate.json'
    $sidecarPath = Join-Path $result.ArtifactDirectory 'containment-candidate.sha256'
    Assert-True -Condition (Test-Path -LiteralPath $identityPath -PathType Leaf) -Message 'Candidate identity was not written.'
    Assert-True -Condition (Test-Path -LiteralPath $sidecarPath -PathType Leaf) -Message 'Candidate identity sidecar was not written.'
    $identityText = [System.IO.File]::ReadAllText($identityPath, [System.Text.Encoding]::UTF8)
    Assert-True -Condition (-not $identityText.Contains("`r")) -Message 'Canonical identity must use LF-only bytes.'
    $identityBytes = [System.IO.File]::ReadAllBytes($identityPath)
    Assert-True -Condition (-not ($identityBytes.Length -ge 3 -and $identityBytes[0] -eq 0xEF -and $identityBytes[1] -eq 0xBB -and $identityBytes[2] -eq 0xBF)) -Message 'Canonical identity must be UTF-8 without BOM.'
    $identity = $identityText | ConvertFrom-Json
    Assert-Equal -Actual $identityText -Expected (ConvertTo-GuardCanonicalJson -Value $identity) -Message 'Candidate identity bytes are not independently canonical.'
    Assert-Equal -Actual $identity.schema_version -Expected 1 -Message 'Candidate schema version mismatch.'
    Assert-True -Condition ([bool]$identity.non_publishable) -Message 'Candidate must be non-publishable.'
    Assert-Equal -Actual $identity.product_version -Expected '9.8.7' -Message 'Candidate version mismatch.'
    Assert-Equal -Actual $identity.sources.rook.sha -Expected $Fixture.RookSha -Message 'Rook source SHA binding mismatch.'
    Assert-Equal -Actual $identity.sources.chirp.sha -Expected $Fixture.ChirpSha -Message 'Chirp source SHA binding mismatch.'
    Assert-Equal -Actual $identity.sources.rook.branch -Expected 'codex/gh-execute-intent-root-fix' -Message 'Rook branch binding mismatch.'
    Assert-True -Condition ([bool]$identity.sources.rook.clean -and [bool]$identity.sources.chirp.clean) -Message 'Candidate did not record clean source proofs.'
    Assert-Equal -Actual $identity.sources.rook.stage_path -Expected (Join-Path $result.ArtifactDirectory 'stage\Rook') -Message 'Rook stage layout mismatch.'
    Assert-Equal -Actual $identity.sources.chirp.stage_path -Expected (Join-Path $result.ArtifactDirectory 'stage\Chirp') -Message 'Chirp stage layout mismatch.'
    Assert-Equal -Actual $identity.sources.rook.local_source_clone_path -Expected $identity.sources.rook.stage_path -Message 'Rook local source-clone identity does not bind the detached stage.'
    Assert-Equal -Actual $identity.sources.chirp.local_source_clone_path -Expected $identity.sources.chirp.stage_path -Message 'Chirp local source-clone identity does not bind the detached stage.'
    Assert-HashMatchesFile -ActualHash ([string]$identity.sources.rook.source_archive_sha256) -Path (Join-Path $result.ArtifactDirectory 'source-evidence\Rook.tar') -Label 'Rook source archive'
    Assert-HashMatchesFile -ActualHash ([string]$identity.sources.chirp.source_archive_sha256) -Path (Join-Path $result.ArtifactDirectory 'source-evidence\Chirp.tar') -Label 'Chirp source archive'
    Assert-Equal -Actual $identity.sources.rook.source_tree_digest -Expected $identity.inventories.source_inventory.rook.digest -Message 'Rook source-tree singleton digest mismatch.'
    Assert-Equal -Actual $identity.sources.chirp.source_tree_digest -Expected $identity.inventories.source_inventory.chirp.digest -Message 'Chirp source-tree singleton digest mismatch.'

    $stagedRook = [string]$identity.sources.rook.stage_path
    $stagedChirp = [string]$identity.sources.chirp.stage_path
    Assert-Equal -Actual (Invoke-Git -GitPath $Fixture.GitPath -WorkingDirectory $stagedRook -Arguments @('rev-parse','--abbrev-ref','HEAD')) -Expected 'HEAD' -Message 'Staged Rook clone is not detached.'
    Assert-Equal -Actual (Invoke-Git -GitPath $Fixture.GitPath -WorkingDirectory $stagedChirp -Arguments @('rev-parse','--abbrev-ref','HEAD')) -Expected 'HEAD' -Message 'Staged Chirp clone is not detached.'
    Assert-Equal -Actual (Invoke-Git -GitPath $Fixture.GitPath -WorkingDirectory $stagedRook -Arguments @('rev-parse','HEAD')) -Expected $Fixture.RookSha -Message 'Staged Rook SHA mismatch.'
    Assert-Equal -Actual (Invoke-Git -GitPath $Fixture.GitPath -WorkingDirectory $stagedChirp -Arguments @('rev-parse','HEAD')) -Expected $Fixture.ChirpSha -Message 'Staged Chirp SHA mismatch.'
    Assert-Equal -Actual (Invoke-Git -GitPath $Fixture.GitPath -WorkingDirectory $stagedRook -Arguments @('remote')) -Expected '' -Message 'Staged Rook clone retained a remote.'
    Assert-Equal -Actual (Invoke-Git -GitPath $Fixture.GitPath -WorkingDirectory $stagedChirp -Arguments @('remote')) -Expected '' -Message 'Staged Chirp clone retained a remote.'

    $expectedToolPaths = [ordered]@{
        GitPath = $Fixture.GitPath
        PowerShellPath = $WindowsPowerShell
        CmdPath = $CmdPath
        Msys2Bash = $Fixture.Toolchain.Msys2Bash
        VcvarsallPath = $Fixture.Toolchain.VcvarsallPath
        MsbuildPath = $Fixture.Toolchain.MsbuildPath
        DotnetPath = $Fixture.Toolchain.DotnetPath
        IsccPath = $Fixture.Toolchain.IsccPath
    }
    Assert-StringSequenceEqual -Actual @(Get-GuardOrdinalSortedStrings -Values @($identity.tools.PSObject.Properties.Name)) -Expected @(Get-GuardOrdinalSortedStrings -Values @($expectedToolPaths.Keys)) -Message 'Tool identity key set is not exact.'
    foreach ($name in $expectedToolPaths.Keys) {
        Assert-FileIdentityMatchesDisk -Identity $identity.tools.PSObject.Properties[$name].Value -ExpectedPath $expectedToolPaths[$name] -Label "Tool identity $name"
    }
    Assert-Equal -Actual $identity.inputs.native_rhino_sdk.registry_key -Expected 'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\McNeel\Rhinoceros\SDK\8.0' -Message 'Rhino SDK registry authority mismatch.'
    Assert-Equal -Actual $identity.inputs.native_rhino_sdk.install_path -Expected $Fixture.RhinoSdkRoot -Message 'Rhino SDK install-root identity mismatch.'
    Assert-FileIdentityMatchesDisk -Identity $identity.inputs.native_rhino_sdk.property_sheet -ExpectedPath (Join-Path $Fixture.RhinoSdkRoot 'PropertySheets\Rhino.Cpp.PlugIn.props') -Label 'Rhino SDK property sheet'
    Assert-FileIdentityMatchesDisk -Identity $identity.inputs.native_msvc.compiler -ExpectedPath $Fixture.Toolchain.TrustedCompiler -Label 'Selected native compiler'
    Assert-FileIdentityMatchesDisk -Identity $identity.inputs.native_msvc.linker -ExpectedPath $Fixture.Toolchain.TrustedLinker -Label 'Selected native linker'
    Assert-Equal -Actual $identity.inputs.native_msvc.vcvars_selector -Expected '14.44' -Message 'Native vcvars selector mismatch.'
    Assert-Equal -Actual $identity.inputs.native_msvc.vc_tools_version -Expected '14.44.35207' -Message 'Native toolset version mismatch.'
    Assert-Equal -Actual $identity.inputs.native_msvc.visual_studio_root -Expected $Fixture.Toolchain.VsRoot -Message 'Visual Studio root identity mismatch.'
    Assert-Equal -Actual $identity.inputs.dotnet.version -Expected '8.0.100' -Message '.NET SDK version identity mismatch.'
    Assert-Equal -Actual (ConvertTo-GuardCanonicalJson -Value $identity.inputs.dotnet.executable) -Expected (ConvertTo-GuardCanonicalJson -Value $identity.tools.DotnetPath) -Message '.NET executable identity does not equal the DotnetPath tool identity.'
    Assert-Equal -Actual $identity.inputs.ffmpeg.version -Expected '7.1.1' -Message 'FFmpeg version identity mismatch.'
    $occtImportPaths = @('inc\Standard.hxx') + @('TKernel.lib','TKMath.lib','TKG2d.lib','TKG3d.lib','TKGeomBase.lib','TKGeomAlgo.lib','TKBRep.lib','TKTopAlgo.lib','TKPrim.lib','TKBO.lib','TKBool.lib','TKShHealing.lib','TKMesh.lib' | ForEach-Object { "win64\vc14\lib\$_" })
    $occtRuntimePaths = @('TKernel.dll','TKMath.dll','TKG2d.dll','TKG3d.dll','TKGeomBase.dll','TKGeomAlgo.dll','TKBRep.dll','TKTopAlgo.dll','TKPrim.dll','TKBO.dll','TKShHealing.dll')
    $rhinoReferencePaths = @('Eto.dll','RhinoCommon.dll','netcore\Rhino.UI.dll','netcore\RhinoCommon.dll')
    $revitReferencePaths = @('RevitAPI.dll','RevitAPIUI.dll')
    $vcRedistPaths = @('Microsoft.VC143.CRT\concrt140.dll','Microsoft.VC143.CRT\msvcp140.dll','Microsoft.VC143.CRT\vcruntime140.dll','Microsoft.VC143.CRT\vcruntime140_1.dll','Microsoft.VC143.MFC\mfc140.dll','Microsoft.VC143.MFC\mfc140u.dll')
    Assert-Equal -Actual $identity.inputs.occt.build_root -Expected $Fixture.OcctRoot -Message 'OCCT build root identity mismatch.'
    Assert-Equal -Actual $identity.inputs.occt.runtime_root -Expected $Fixture.OcctRuntimeRoot -Message 'OCCT runtime root identity mismatch.'
    Assert-Equal -Actual $identity.inputs.occt.msbuild_property -Expected "/p:OcctRoot=$($Fixture.OcctRoot)" -Message 'OCCT MSBuild property identity mismatch.'
    Assert-Equal -Actual $identity.inputs.rhino_managed_references.root -Expected $Fixture.RhinoSystemDir -Message 'Rhino managed-reference root identity mismatch.'
    Assert-Equal -Actual $identity.inputs.revit_references.root -Expected $Fixture.RevitInstallDir -Message 'Revit reference root identity mismatch.'
    Assert-Equal -Actual $identity.inputs.vc_redist.root -Expected $Fixture.VcRedistRoot -Message 'VC redistributable root identity mismatch.'
    Assert-SelectedProjectionMatchesDisk -Projection $identity.inputs.occt.consumed_header_and_import_libraries -Root $Fixture.OcctRoot -ExpectedRelativePaths $occtImportPaths -Label 'OCCT build-input projection'
    Assert-SelectedProjectionMatchesDisk -Projection $identity.inputs.occt.consumed_runtime_dlls -Root $Fixture.OcctRuntimeRoot -ExpectedRelativePaths $occtRuntimePaths -Label 'OCCT runtime-input projection'
    Assert-SelectedProjectionMatchesDisk -Projection $identity.inputs.rhino_managed_references.projection -Root $Fixture.RhinoSystemDir -ExpectedRelativePaths $rhinoReferencePaths -Label 'Rhino managed-reference projection'
    Assert-SelectedProjectionMatchesDisk -Projection $identity.inputs.revit_references.projection -Root $Fixture.RevitInstallDir -ExpectedRelativePaths $revitReferencePaths -Label 'Revit reference projection'
    Assert-SelectedProjectionMatchesDisk -Projection $identity.inputs.vc_redist.projection -Root $Fixture.VcRedistRoot -ExpectedRelativePaths $vcRedistPaths -Label 'VC redistributable projection'

    Assert-Equal -Actual $identity.private_python.relative_path -Expected 'stage/Rook/installer/runtime/python/cpython-3.11.9/python.exe' -Message 'Private Python relative path mismatch.'
    Assert-Equal -Actual $identity.private_python.version -Expected '3.11.9' -Message 'Private Python version mismatch.'
    $privatePythonPath = Join-Path $result.ArtifactDirectory ([string]$identity.private_python.relative_path).Replace('/','\')
    Assert-HashMatchesFile -ActualHash ([string]$identity.private_python.sha256) -Path $privatePythonPath -Label 'Private Python executable'
    Assert-Equal -Actual @($identity.private_python.pth_files).Count -Expected 0 -Message 'Full private runtime must have an empty sorted *._pth projection.'
    Assert-Equal -Actual $identity.inputs.python_wheelhouse.relative_path -Expected 'stage/Rook/installer/runtime/python-wheelhouse' -Message 'Validated wheelhouse relative path mismatch.'
    Assert-InventoryMatchesDisk -Inventory $identity.inputs.python_wheelhouse.validated_payload -Root (Join-Path $stagedRook 'installer\runtime\python-wheelhouse') -Label 'Validated Python wheelhouse'

    $allowlist = @(Get-GuardOrdinalSortedStrings -Values @('SystemRoot','windir','TEMP','TMP','ComSpec','PATHEXT','PROCESSOR_ARCHITECTURE','ProgramFiles','ProgramFiles(x86)','ProgramData','SystemDrive','NUMBER_OF_PROCESSORS','OS','PATH'))
    Assert-Equal -Actual $identity.native_environment.contract_version -Expected 1 -Message 'Native environment contract version mismatch.'
    Assert-StringSequenceEqual -Actual @($identity.native_environment.input_allowlist) -Expected $allowlist -Message 'Native environment allowlist mismatch.'
    Assert-StringSequenceEqual -Actual @($identity.native_environment.scrub_names) -Expected @(Get-GuardOrdinalSortedStrings -Values @(Get-ScrubNames)) -Message 'Native environment scrub-name set mismatch.'
    $preEnv = @{}
    foreach ($entry in $identity.native_environment.pre_vcvars) { $preEnv[[string]$entry.name] = [string]$entry.value }
    Assert-Equal -Actual $preEnv['PATH'] -Expected 'C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem' -Message 'Native baseline PATH was not code-owned.'
    foreach ($name in Get-ScrubNames) { Assert-True -Condition (-not $preEnv.ContainsKey($name)) -Message "Native pre-vcvars environment leaked $name." }
    $preEnvText = ($identity.native_environment.pre_vcvars | ConvertTo-Json -Depth 4 -Compress)
    Assert-NotContains -Text $preEnvText -Unexpected 'T9_TRIP_' -Message 'Native pre-vcvars projection retained a trip value.'
    Assert-NotContains -Text $preEnvText -Unexpected $Fixture.DecoyPath -Message 'Native pre-vcvars projection retained ambient PATH.'
    Assert-NotContains -Text $preEnvText -Unexpected $Fixture.DecoyOcct -Message 'Native pre-vcvars projection retained ambient OCCT_ROOT.'
    $capturedExpected = [ordered]@{
        VCToolsInstallDir = $Fixture.Toolchain.VcToolsRoot + '\'
        VCTargetsPath = $Fixture.Toolchain.VcTargetsRoot + '\'
        VCTargetsPath10 = $Fixture.Toolchain.VcTargetsRoot + '\'
        VCTargetsPath11 = $Fixture.Toolchain.VcTargetsRoot + '\'
        VCTargetsPath12 = $Fixture.Toolchain.VcTargetsRoot + '\'
        VCTargetsPath14 = $Fixture.Toolchain.VcTargetsRoot + '\'
        VCTargetsPath15 = $Fixture.Toolchain.VcTargetsRoot + '\'
        VCTargetsPath16 = $Fixture.Toolchain.VcTargetsRoot + '\'
        VCTargetsPath17 = $Fixture.Toolchain.VcTargetsRoot + '\'
        MSBUILD_EXE_PATH = $Fixture.Toolchain.MsbuildPath
        MSBuildExtensionsPath = $Fixture.Toolchain.MsbuildRoot + '\'
        MSBuildExtensionsPath32 = $Fixture.Toolchain.MsbuildRoot + '\'
        MSBuildExtensionsPath64 = $Fixture.Toolchain.MsbuildRoot + '\'
        MSBuildSDKsPath = $Fixture.Toolchain.MsbuildSdks + '\'
        MSBuildToolsPath = $Fixture.Toolchain.MsbuildBin + '\'
        MSBuildToolsPath32 = $Fixture.Toolchain.MsbuildBin + '\'
        MSBuildToolsPath64 = $Fixture.Toolchain.MsbuildBin + '\'
        MSBuildToolsRoot = $Fixture.Toolchain.MsbuildRoot + '\'
        WindowsSdkDir = $Fixture.Toolchain.WindowsSdkRoot + '\'
        UniversalCRTSdkDir = $Fixture.Toolchain.WindowsSdkRoot + '\'
        UCRTContentRoot = $Fixture.Toolchain.WindowsSdkRoot + '\'
        NETFXSDKDir = $Fixture.Toolchain.NetFxSdkRoot + '\'
        INCLUDE = "$($Fixture.Toolchain.VcToolsRoot)\include;$($Fixture.Toolchain.WindowsSdkRoot)\Include;$($Fixture.Toolchain.NetFxSdkRoot)\include\um"
        LIB = "$($Fixture.Toolchain.VcToolsRoot)\lib\x64;$($Fixture.Toolchain.WindowsSdkRoot)\Lib"
        LIBPATH = "$($Fixture.Toolchain.VcToolsRoot)\lib\x64;$($Fixture.Toolchain.WindowsSdkRoot)\Lib"
        PATH = "$($Fixture.Toolchain.VcToolsRoot)\bin\Hostx64\x64;$($Fixture.Toolchain.WindowsSdkRoot)\bin;$($Fixture.Toolchain.NetFxToolsRoot);$($Fixture.Toolchain.HtmlHelpRoot);C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem"
    }
    Assert-StringSequenceEqual -Actual @(Get-GuardOrdinalSortedStrings -Values @($identity.native_environment.captured.PSObject.Properties.Name)) -Expected @(Get-GuardOrdinalSortedStrings -Values @($capturedExpected.Keys)) -Message 'Captured native path projection key set is not exact.'
    foreach ($name in $capturedExpected.Keys) {
        Assert-Equal -Actual $identity.native_environment.captured.PSObject.Properties[$name].Value -Expected $capturedExpected[$name] -Message "Captured native path projection mismatch for $name."
    }
    Assert-Equal -Actual $identity.native_environment.msbuild_occt_root -Expected $Fixture.OcctRoot -Message 'Explicit MSBuild OcctRoot binding mismatch.'
    Assert-Equal -Actual $identity.inputs.native_msvc.compiler.path -Expected $Fixture.Toolchain.TrustedCompiler -Message 'Trusted compiler identity path mismatch.'
    Assert-Equal -Actual $identity.inputs.native_msvc.linker.path -Expected $Fixture.Toolchain.TrustedLinker -Message 'Trusted linker identity path mismatch.'
    Assert-True -Condition ([string]$identity.inputs.native_msvc.compiler.sha256 -match '^[0-9a-f]{64}$') -Message 'Trusted compiler SHA-256 is missing.'
    Assert-True -Condition ([string]$identity.inputs.native_msvc.linker.sha256 -match '^[0-9a-f]{64}$') -Message 'Trusted linker SHA-256 is missing.'

    $commands = @{}
    foreach ($command in $identity.commands) { $commands[[string]$command.name] = $command }
    foreach ($name in @('stage-python-runtime','build-python-wheelhouse','validate-python-wheelhouse','build-ffmpeg','validate-ffmpeg','native-environment','native-build','dotnet-version','build-rook-managed','build-rookbim-managed','build-installer','private-python-version')) {
        Assert-True -Condition $commands.ContainsKey($name) -Message "Candidate omitted command record $name."
        Assert-Equal -Actual $commands[$name].exit_code -Expected 0 -Message "Command $name did not record exit zero."
    }
    foreach ($name in @('stage-python-runtime','build-python-wheelhouse','validate-python-wheelhouse','build-ffmpeg','validate-ffmpeg')) {
        Assert-Equal -Actual $commands[$name].executable -Expected $WindowsPowerShell -Message "Command $name did not use the explicit PowerShellPath."
    }
    foreach ($name in @('dotnet-version','build-rook-managed','build-rookbim-managed')) {
        Assert-Equal -Actual $commands[$name].executable -Expected $Fixture.Toolchain.DotnetPath -Message "Command $name did not use the explicit DotnetPath."
    }
    Assert-Equal -Actual $commands['native-environment'].executable -Expected $CmdPath -Message 'Native environment probe did not use the explicit CmdPath.'
    Assert-Equal -Actual $commands['native-build'].executable -Expected $Fixture.Toolchain.MsbuildPath -Message 'Native build did not use the explicit MsbuildPath.'
    Assert-Equal -Actual $commands['build-installer'].executable -Expected $Fixture.Toolchain.IsccPath -Message 'Installer build did not use the explicit IsccPath.'
    Assert-Equal -Actual $commands['private-python-version'].executable -Expected $privatePythonPath -Message 'Private Python version probe did not use the staged private interpreter.'
    Assert-Equal -Actual $commands['extract-reviewed-installer'].executable -Expected $Fixture.GitPath -Message 'Reviewed-installer extraction did not use the explicit GitPath.'
    foreach ($command in $identity.commands) {
        $name = [string]$command.name
        if ($name -match '^git-' -or $name -match '^(clone|configure|checkout|remove|archive)-(rook|chirp)') {
            Assert-Equal -Actual $command.executable -Expected $Fixture.GitPath -Message "Git command $name did not use the explicit GitPath."
        }
    }
    $stageRuntimeArgs = @($commands['stage-python-runtime'].arguments)
    $expectedStageRuntimeArgs = @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $stagedRook 'scripts\python-runtime\stage-rook-python-runtime.ps1'),'-RepoRoot',$stagedRook)
    Assert-True -Condition (@(Compare-Object $expectedStageRuntimeArgs $stageRuntimeArgs -SyncWindow 0).Count -eq 0) -Message 'Python runtime staging arguments are not exact.'
    $buildWheelArgs = @($commands['build-python-wheelhouse'].arguments)
    $expectedBuildWheelArgs = @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $stagedRook 'scripts\python-runtime\build-rook-python-wheelhouse.ps1'),'-Version','9.8.7','-RepoRoot',$stagedRook,'-ChirpRoot',$stagedChirp)
    Assert-True -Condition (@(Compare-Object $expectedBuildWheelArgs $buildWheelArgs -SyncWindow 0).Count -eq 0) -Message 'Wheelhouse build arguments are not exact.'
    $validateWheelArgs = @($commands['validate-python-wheelhouse'].arguments)
    $expectedValidateWheelArgs = @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $stagedRook 'scripts\validate-python-wheelhouse.ps1'),'-Version','9.8.7','-RepoRoot',$stagedRook)
    Assert-True -Condition (@(Compare-Object $expectedValidateWheelArgs $validateWheelArgs -SyncWindow 0).Count -eq 0) -Message 'Wheelhouse validator arguments are not exact.'
    $expectedFfmpegManifest = Join-Path $stagedRook 'artifacts\ffmpeg\ffmpeg-7.1.1-rook-minimal\rook-ffmpeg-source-bundle-manifest.json'
    Assert-FileIdentityMatchesDisk -Identity $identity.inputs.ffmpeg.source_identity -ExpectedPath (Join-Path $stagedRook 'scripts\ffmpeg\rook-ffmpeg-source.json') -Label 'FFmpeg source pin'
    Assert-FileIdentityMatchesDisk -Identity $identity.inputs.ffmpeg.source_bundle_manifest -ExpectedPath $expectedFfmpegManifest -Label 'FFmpeg source-bundle manifest'
    $ffmpegPayloadRoot = Join-Path $stagedRook 'third_party\ffmpeg'
    $ffmpegTrackedPaths = @('third_party/ffmpeg/ffmpeg-provenance.json','third_party/ffmpeg/ffmpeg.exe')
    Assert-InventoryMatchesDisk -Inventory $identity.inputs.ffmpeg.installed_payload -Root $ffmpegPayloadRoot -Label 'Installed FFmpeg payload'
    Assert-SelectedProjectionMatchesDisk -Projection $identity.inputs.ffmpeg.tracked_build_outputs -Root $stagedRook -ExpectedRelativePaths $ffmpegTrackedPaths -Label 'Tracked FFmpeg output projection'
    $buildFfmpegArgs = @($commands['build-ffmpeg'].arguments)
    $expectedBuildFfmpegArgs = @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $stagedRook 'scripts\ffmpeg\build-rook-ffmpeg.ps1'),'-RepoRoot',$stagedRook,'-Msys2Bash',$Fixture.Toolchain.Msys2Bash,'-InstallPayload')
    Assert-True -Condition (@(Compare-Object $expectedBuildFfmpegArgs $buildFfmpegArgs -SyncWindow 0).Count -eq 0) -Message 'FFmpeg build arguments are not exact.'
    $validateFfmpegArgs = @($commands['validate-ffmpeg'].arguments)
    $expectedValidateFfmpegArgs = @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $stagedRook 'scripts\validate-ffmpeg-bundle.ps1'),'-RepoRoot',$stagedRook,'-SourceBundleManifestPath',$expectedFfmpegManifest)
    Assert-True -Condition (@(Compare-Object $expectedValidateFfmpegArgs $validateFfmpegArgs -SyncWindow 0).Count -eq 0) -Message 'FFmpeg validator arguments are not exact.'

    $expectedImportDisableArguments = @(
        '/p:ImportDirectoryBuildProps=false','/p:ImportDirectoryBuildTargets=false',
        '/p:ImportProjectExtensionProps=false','/p:ImportProjectExtensionTargets=false',
        '/p:ImportUserLocationsByWildcardBeforeMicrosoftCommonProps=false',
        '/p:ImportUserLocationsByWildcardAfterMicrosoftCommonProps=false',
        '/p:ImportUserLocationsByWildcardBeforeMicrosoftCommonTargets=false',
        '/p:ImportUserLocationsByWildcardAfterMicrosoftCommonTargets=false'
    )
    $expectedNativeArguments = @(
        (Join-Path $stagedRook 'src\RookNative\RookNative.vcxproj'),'/t:Build','/p:Configuration=Release','/p:Platform=x64',
        '/p:VCToolsVersion=14.44.35207',"/p:OcctRoot=$($Fixture.OcctRoot)"
    ) + $expectedImportDisableArguments
    Assert-Equal -Actual $commands['native-build'].executable -Expected $Fixture.Toolchain.MsbuildPath -Message 'Native build did not invoke the explicit MSBuild executable.'
    Assert-StringSequenceEqual -Actual @($commands['native-build'].arguments) -Expected $expectedNativeArguments -Message 'Executed native MSBuild argument vector is not exact.'
    Assert-StringSequenceEqual -Actual @($identity.native_environment.msbuild_arguments) -Expected $expectedNativeArguments -Message 'Identity native MSBuild argument vector is not exact.'
    Assert-StringSequenceEqual -Actual @($identity.native_environment.import_disable_arguments) -Expected $expectedImportDisableArguments -Message 'Native import-disable property vector is not exact.'
    $nativeMsbuildEnvironmentPath = Join-Path $stagedRook 'src\RookNative\native-msbuild.env.txt'
    Assert-True -Condition (Test-Path -LiteralPath $nativeMsbuildEnvironmentPath -PathType Leaf) -Message 'Explicit fake MSBuild was not reached.'
    $nativeMsbuildEnvironment = Get-Content -LiteralPath $nativeMsbuildEnvironmentPath -Raw
    foreach ($name in Get-DirectHookNames) {
        Assert-True -Condition (-not [regex]::IsMatch($nativeMsbuildEnvironment,"(?im)^$([regex]::Escape($name))=")) -Message "Native MSBuild environment retained direct import authority $name."
    }
    Assert-Equal -Actual @(Get-ChildItem -LiteralPath $Fixture.TripRoot -Filter '*.hit' -File).Count -Expected 0 -Message 'A seeded MSBuild import trip file executed.'

    $rookManaged = @($commands['build-rook-managed'].arguments)
    $bimManaged = @($commands['build-rookbim-managed'].arguments)
    $inert = [string]$identity.managed.inert_rhino_plugin_dir
    $expectedRookManaged = @('build',(Join-Path $stagedRook 'src\Rook\Rook.csproj'),'-c','Release',"-p:RhinoPluginDir=$inert","-p:RhinoSystemDir=$($Fixture.RhinoSystemDir)")
    $expectedBimManaged = @('build',(Join-Path $stagedRook 'src\RookBim\RookBim.csproj'),'-c','Release',"-p:RhinoPluginDir=$inert","-p:RhinoSystemDir=$($Fixture.RhinoSystemDir)","-p:RevitInstallDir=$($Fixture.RevitInstallDir)")
    Assert-StringSequenceEqual -Actual $rookManaged -Expected $expectedRookManaged -Message 'Executed Rook managed argument vector is not exact.'
    Assert-StringSequenceEqual -Actual $bimManaged -Expected $expectedBimManaged -Message 'Executed RookBim managed argument vector is not exact.'
    Assert-StringSequenceEqual -Actual @($identity.managed.rook_arguments) -Expected $expectedRookManaged -Message 'Identity Rook managed argument vector is not exact.'
    Assert-StringSequenceEqual -Actual @($identity.managed.rookbim_arguments) -Expected $expectedBimManaged -Message 'Identity RookBim managed argument vector is not exact.'
    Assert-True -Condition (-not (Test-Path -LiteralPath $inert)) -Message 'Inert RhinoPluginDir exists after candidate construction.'
    $liveProjection = $identity.managed.live_plugin.projection
    Assert-True -Condition ([bool]$liveProjection.exists) -Message 'Live plug-in projection did not record the existing fixture.'
    Assert-Equal -Actual $liveProjection.path -Expected $Fixture.LivePlugin -Message 'Live plug-in projection path mismatch.'
    $liveProjectionHash = Get-GuardStringSha256 -Text (ConvertTo-GuardCanonicalJson -Value $liveProjection)
    Assert-Equal -Actual $identity.managed.live_plugin.before_sha256 -Expected $liveProjectionHash -Message 'Live plug-in before hash does not bind its canonical projection.'
    Assert-Equal -Actual $identity.managed.live_plugin.after_sha256 -Expected $liveProjectionHash -Message 'Live plug-in after hash does not bind the unchanged canonical projection.'
    $liveFiles = @($liveProjection.files)
    $liveInventory = [pscustomobject]@{ files = $liveFiles; digest = Get-GuardStringSha256 -Text (ConvertTo-GuardCanonicalJson -Value $liveFiles) }
    Assert-InventoryMatchesDisk -Inventory $liveInventory -Root $Fixture.LivePlugin -Label 'Live plug-in projection'
    Assert-Equal -Actual (Get-FileHash -LiteralPath (Join-Path $Fixture.LivePlugin 'sentinel\keep.bin') -Algorithm SHA256).Hash -Expected $beforeLiveHash -Message 'Live plug-in sentinel changed.'

    $isccArgs = @($commands['build-installer'].arguments)
    $expectedIsccArgs = @('/DMyAppVersion=9.8.7',"/DVcRedistRoot=$($Fixture.VcRedistRoot)","/DOcctRuntimeRoot=$($Fixture.OcctRuntimeRoot)",(Join-Path $stagedRook 'installer\RookSetup.iss'))
    Assert-True -Condition (@(Compare-Object $expectedIsccArgs $isccArgs -SyncWindow 0).Count -eq 0) -Message 'ISCC arguments are not exact.'
    $defines = @($isccArgs | Where-Object { $_ -like '/D*' })
    Assert-Equal -Actual $defines.Count -Expected 3 -Message 'ISCC must receive exactly three defines.'
    Assert-True -Condition (@($defines | Where-Object { $_ -notmatch '^/D(MyAppVersion|VcRedistRoot|OcctRuntimeRoot)=' }).Count -eq 0) -Message 'ISCC received an unapproved define.'
    $builtInstaller = Join-Path $result.ArtifactDirectory ([string]$identity.installer.relative_path).Replace('/','\')
    $reviewedInstaller = Join-Path $result.ArtifactDirectory 'source-evidence\RookSetup.reviewed.iss'
    $stagedInstaller = Join-Path $stagedRook 'installer\RookSetup.iss'
    Assert-HashMatchesFile -ActualHash ([string]$identity.installer.sha256) -Path $builtInstaller -Label 'Built installer'
    Assert-HashMatchesFile -ActualHash ([string]$identity.installer.source_sha256) -Path $reviewedInstaller -Label 'Reviewed installer source'
    Assert-HashMatchesFile -ActualHash ([string]$identity.installer.staged_sha256) -Path $stagedInstaller -Label 'Staged installer source'
    Assert-Equal -Actual ([long]$identity.installer.source_size) -Expected ([long](Get-Item -LiteralPath $reviewedInstaller).Length) -Message 'Reviewed installer source size mismatch.'
    Assert-Equal -Actual ([long]$identity.installer.staged_size) -Expected ([long](Get-Item -LiteralPath $stagedInstaller).Length) -Message 'Staged installer source size mismatch.'

    Assert-SortedProjection -Files @($identity.inventories.source_inventory.rook.files) -Label 'Rook source inventory'
    Assert-SortedProjection -Files @($identity.inventories.source_inventory.chirp.files) -Label 'Chirp source inventory'
    Assert-SortedProjection -Files @($identity.inventories.build_inventory.files) -Label 'Build inventory'
    Assert-SortedProjection -Files @($identity.inventories.output_inventory.files) -Label 'Output inventory'
    Assert-InventoryMatchesDisk -Inventory $identity.inventories.source_inventory.rook -Root $Fixture.RookRoot -Label 'Rook source inventory'
    Assert-InventoryMatchesDisk -Inventory $identity.inventories.source_inventory.chirp -Root $Fixture.ChirpRoot -Label 'Chirp source inventory'
    Assert-InventoryMatchesDisk -Inventory $identity.inventories.build_inventory -Root (Join-Path $result.ArtifactDirectory 'stage') -Label 'Build inventory'
    Assert-InventoryMatchesDisk -Inventory $identity.inventories.output_inventory -Root $result.ArtifactDirectory -Label 'Output inventory' -ExcludedRelativePaths @('containment-candidate.json','containment-candidate.sha256')
    Assert-True -Condition (-not $identityText.Contains('self_digest')) -Message 'Canonical identity must not contain a self digest.'
    $actualIdentityHash = (Get-FileHash -LiteralPath $identityPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $sidecar = ([System.IO.File]::ReadAllText($sidecarPath, [System.Text.Encoding]::ASCII) -split '\s+')[0].ToLowerInvariant()
    Assert-Equal -Actual $sidecar -Expected $actualIdentityHash -Message 'Identity sidecar does not hash exact canonical bytes.'
}

$fixture = $null
try {
    Assert-True -Condition (Test-Path -LiteralPath $WindowsPowerShell -PathType Leaf) -Message 'Windows PowerShell 5.1 is missing.'
    Assert-True -Condition (Test-Path -LiteralPath $CmdPath -PathType Leaf) -Message 'Canonical cmd.exe is missing.'
    foreach ($name in @('python.exe','python311.dll','vcruntime140.dll','vcruntime140_1.dll')) {
        Assert-True -Condition (Test-Path -LiteralPath (Join-Path $FixturePythonRoot $name) -PathType Leaf) -Message "Local Python 3.11.9 guard fixture is missing $name."
    }
    Invoke-Test -Name 'static builder contract' -Body { Test-StaticContract }
    $fixture = New-Task9Fixture
    Invoke-Test -Name 'source, root, tool, OCCT, and stale-output preflight guards' -Body { Test-PreflightGuards -Fixture $fixture }
    Invoke-Test -Name 'normally nonterminating cmdlet error stops next stage' -Body { Test-InjectedNonterminatingErrorStopsNextStage -Fixture $fixture }
    Invoke-Test -Name 'identity drift fails before MSBuild' -Body { Test-IdentityDriftFailsBeforeMsbuild -Fixture $fixture }
    Invoke-Test -Name 'tracked staged-source mutation is rejected' -Body { Test-StagedSourceChangeIsRejected -Fixture $fixture }
    Invoke-Test -Name 'exact post-FFmpeg tracked build outputs are allowed and inventoried' -Body { Test-TrackedBuildOutputAllowance -Fixture $fixture }
    Invoke-Test -Name 'validated native environment is reused for MSBuild' -Body { Test-ValidatedNativeEnvironmentIsReused -Fixture $fixture }
    Invoke-Test -Name 'original source change during build is rejected' -Body { Test-OriginalSourceChangeIsRejected -Fixture $fixture }
    Invoke-Test -Name 'managed inert and live deployment guards' -Body { Test-ManagedDeploymentGuards -Fixture $fixture }
    Invoke-Test -Name 'fake-only standalone candidate build and identity contract' -Body { Test-FakeCandidateBuild -Fixture $fixture }
    Write-Host "Task 9 containment candidate guard tests passed: $script:TestsPassed tests."
} finally {
    if ($null -ne $fixture -and (Test-Path -LiteralPath $fixture.Root -PathType Container)) {
        $resolvedFixture = (Resolve-Path -LiteralPath $fixture.Root).Path
        $resolvedTemp = (Resolve-Path -LiteralPath ([System.IO.Path]::GetTempPath())).Path.TrimEnd('\')
        if (-not $resolvedFixture.StartsWith($resolvedTemp + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to remove fixture outside temp: $resolvedFixture"
        }
        Remove-Item -LiteralPath $resolvedFixture -Recurse -Force -ErrorAction SilentlyContinue
    }
}
