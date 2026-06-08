param(
    [Parameter(Mandatory = $true)]
    [string]$Version,

    [string]$RepoRoot = '',
    [string]$GitSha = '',
    [string]$InstallerPath = '',
    [string]$FfmpegSourceBundleManifestPath = '',
    [Parameter(Mandatory = $true)]
    [string]$SmokeManifestPath,
    [string]$OutputManifestPath = '',
    [long]$MinInstallerBytes = 5242880,
    [string]$BuildStartedAt = ''
)

$ErrorActionPreference = 'Stop'

function Fail {
    param([string]$Message)
    throw "Release artifact validation failed: $Message"
}

function Require-File {
    param([string]$Path, [string]$Label)
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Fail "$Label is missing: $Path"
    }
    return (Resolve-Path -LiteralPath $Path).Path
}

function Require-Directory {
    param([string]$Path, [string]$Label)
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path -PathType Container)) {
        Fail "$Label is missing: $Path"
    }
    return (Resolve-Path -LiteralPath $Path).Path
}

function Require-JsonField {
    param([object]$Json, [string]$Field, [string]$Label)
    $property = $Json.PSObject.Properties[$Field]
    if ($null -eq $property -or $null -eq $property.Value) {
        Fail "$Label field '$Field' is missing"
    }
    if ($property.Value -is [string] -and [string]::IsNullOrWhiteSpace($property.Value)) {
        Fail "$Label field '$Field' is empty"
    }
    return $property.Value
}

function Get-Sha256 {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

function Assert-FileNewerThanBuildStart {
    param([string]$Path, [Nullable[DateTimeOffset]]$StartedAt)
    if ($null -eq $StartedAt) {
        return
    }
    $item = Get-Item -LiteralPath $Path
    if ([DateTimeOffset]$item.LastWriteTime -lt $StartedAt) {
        Fail "$Path is older than the recorded build start time $($StartedAt.ToString('o'))"
    }
}

function Assert-ManagedAssemblyVersion {
    param([string]$Path, [string]$Expected)
    try {
        $assemblyName = [System.Reflection.AssemblyName]::GetAssemblyName($Path)
    } catch {
        Fail "managed assembly version could not be read from $Path`: $($_.Exception.Message)"
    }
    $actual = $assemblyName.Version.ToString()
    if ($actual -ne $Expected) {
        Fail "managed assembly version mismatch for $Path. Expected $Expected, actual $actual"
    }
}

function Assert-NativeFileVersion {
    param([string]$Path, [string]$Expected)
    $versionInfo = (Get-Item -LiteralPath $Path).VersionInfo
    if ($versionInfo.FileVersion -ne $Expected) {
        Fail "native FileVersion mismatch for $Path. Expected $Expected, actual $($versionInfo.FileVersion)"
    }
    if ($versionInfo.ProductVersion -ne $Expected) {
        Fail "native ProductVersion mismatch for $Path. Expected $Expected, actual $($versionInfo.ProductVersion)"
    }
}

function Assert-RuntimeConfigTfm {
    param([string]$Path, [string]$ExpectedTfm)
    $runtimeConfig = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    $actual = $runtimeConfig.runtimeOptions.tfm
    if ($actual -ne $ExpectedTfm) {
        Fail "$Path must declare runtimeOptions.tfm == $ExpectedTfm; actual value: $actual"
    }
}

function Resolve-GitHead {
    param([string]$Root)
    $head = ((& git -C $Root rev-parse HEAD 2>$null) -join '').Trim()
    if ($LASTEXITCODE -ne 0 -or $head -notmatch '^[0-9a-fA-F]{40}$') {
        Fail 'could not resolve checked-out git HEAD'
    }
    return $head.ToLowerInvariant()
}

function Assert-GitCommitExists {
    param([string]$Root, [string]$CommitSha)
    $null = & git -C $Root cat-file -e "$CommitSha^{commit}" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Fail "GitSha is not a valid git commit: $CommitSha"
    }
}

function Assert-SmokeHostSuccess {
    param(
        [object]$HostManifest,
        [string]$Label,
        [string[]]$RequiredVersionFields,
        [bool]$ExpectedRhinoInside,
        [DateTimeOffset]$SmokeStartedAt
    )

    foreach ($field in $RequiredVersionFields) {
        $null = Require-JsonField -Json $HostManifest -Field $field -Label $Label
    }

    $hostRuntime = ([string](Require-JsonField -Json $HostManifest -Field 'host_runtime' -Label $Label)).Trim()
    if ($hostRuntime -notin @('net8.0', 'net7.0', 'net48')) {
        Fail "$Label field 'host_runtime' must be net8.0, net7.0, or net48; actual value: $hostRuntime"
    }

    $pingResult = ([string](Require-JsonField -Json $HostManifest -Field 'ping_result' -Label $Label)).Trim()
    $successPingValues = @('pong', 'ok', 'success')
    if (-not ($successPingValues -contains $pingResult.ToLowerInvariant())) {
        Fail "$Label field 'ping_result' must be a success value (pong, ok, or success); actual value: $pingResult"
    }

    $pluginManagerListedValue = Require-JsonField -Json $HostManifest -Field 'plugin_manager_listed' -Label $Label
    $pluginManagerListed = $false
    if (-not [bool]::TryParse(([string]$pluginManagerListedValue), [ref]$pluginManagerListed) -or -not $pluginManagerListed) {
        Fail "$Label field 'plugin_manager_listed' must be true to prove Rhino enumerated RookNative; actual value: $pluginManagerListedValue"
    }

    $chatManifestPath = ([string](Require-JsonField -Json $HostManifest -Field 'chat_service_manifest_path' -Label $Label)).Replace('/', '\')
    if ($chatManifestPath -notmatch '(?i)\\RookNative\\RookChatService\.json$') {
        Fail "$Label field 'chat_service_manifest_path' must point to the installed RookNative\\RookChatService.json; actual value: $($HostManifest.chat_service_manifest_path)"
    }

    $chatServiceHealth = ([string](Require-JsonField -Json $HostManifest -Field 'chat_service_health' -Label $Label)).Trim()
    $successHealthValues = @('ok', 'healthy', 'success')
    if (-not ($successHealthValues -contains $chatServiceHealth.ToLowerInvariant())) {
        Fail "$Label field 'chat_service_health' must be a success value (ok, healthy, or success); actual value: $chatServiceHealth"
    }

    $nativePortValue = Require-JsonField -Json $HostManifest -Field 'native_port' -Label $Label
    $nativePort = 0
    if (-not [int]::TryParse(([string]$nativePortValue), [ref]$nativePort) -or $nativePort -lt 1 -or $nativePort -gt 65535) {
        Fail "$Label field 'native_port' must be between 1 and 65535; actual value: $nativePortValue"
    }

    $nativePath = ([string](Require-JsonField -Json $HostManifest -Field 'loaded_native_path' -Label $Label)).Replace('/', '\')
    if ($nativePath -notmatch '(?i)\\RookNative\\RookNative\.rhp$') {
        Fail "$Label field 'loaded_native_path' must point to the installed RookNative\\RookNative.rhp; actual value: $($HostManifest.loaded_native_path)"
    }

    Assert-CompanionSelfReport `
        -SelfReport (Require-JsonField -Json $HostManifest -Field 'companion_self_report' -Label $Label) `
        -Label "$Label companion_self_report" `
        -HostRuntime $hostRuntime `
        -ExpectedRhinoInside $ExpectedRhinoInside `
        -SmokeStartedAt $SmokeStartedAt
}

function Assert-BooleanField {
    param(
        [object]$Json,
        [string]$Field,
        [string]$Label,
        [bool]$Expected
    )

    $value = Require-JsonField -Json $Json -Field $Field -Label $Label
    $parsed = $false
    if (-not [bool]::TryParse(([string]$value), [ref]$parsed) -or $parsed -ne $Expected) {
        Fail "$Label.$Field must be $Expected; actual value: $value"
    }
}

function Require-TimestampField {
    param(
        [object]$Json,
        [string]$Field,
        [string]$Label
    )

    $rawValue = [string](Require-JsonField -Json $Json -Field $Field -Label $Label)
    $parsed = [DateTimeOffset]::MinValue
    if (-not [DateTimeOffset]::TryParse($rawValue, [ref]$parsed)) {
        Fail "$Label.$Field must be a valid timestamp; actual value: $rawValue"
    }

    return $parsed
}

function Assert-CompanionSelfReport {
    param(
        [object]$SelfReport,
        [string]$Label,
        [string]$HostRuntime,
        [bool]$ExpectedRhinoInside,
        [DateTimeOffset]$SmokeStartedAt
    )

    foreach ($field in @(
        'processId',
        'processName',
        'rhinoInside',
        'assemblyLocation',
        'runtimeChild',
        'targetFramework',
        'startupGateAttached',
        'deferredLocalStartupComplete',
        'startupComplete',
        'bridgeRegistered',
        'onLoadUtc',
        'startupCompleteUtc',
        'statusUpdatedUtc'
    )) {
        $null = Require-JsonField -Json $SelfReport -Field $field -Label $Label
    }

    Assert-BooleanField -Json $SelfReport -Field 'rhinoInside' -Label $Label -Expected $ExpectedRhinoInside
    Assert-BooleanField -Json $SelfReport -Field 'deferredLocalStartupComplete' -Label $Label -Expected $true
    Assert-BooleanField -Json $SelfReport -Field 'startupComplete' -Label $Label -Expected $true
    Assert-BooleanField -Json $SelfReport -Field 'bridgeRegistered' -Label $Label -Expected $true

    $runtimeChild = ([string](Require-JsonField -Json $SelfReport -Field 'runtimeChild' -Label $Label)).Trim()
    if ($runtimeChild -ne $HostRuntime) {
        Fail "$Label.runtimeChild must match host_runtime $HostRuntime; actual value: $runtimeChild"
    }

    $runtimePattern = [regex]::Escape($HostRuntime)
    $companionPattern = "(?i)\\RookNative\\$runtimePattern\\Rook\.rhp$"
    $assemblyLocation = ([string](Require-JsonField -Json $SelfReport -Field 'assemblyLocation' -Label $Label)).Replace('/', '\')
    if ($assemblyLocation -notmatch $companionPattern) {
        Fail "$Label.assemblyLocation must point to the self-reported runtime child RookNative\\$HostRuntime\\Rook.rhp; actual value: $($SelfReport.assemblyLocation)"
    }

    $statusUpdatedUtc = Require-TimestampField -Json $SelfReport -Field 'statusUpdatedUtc' -Label $Label
    if ($statusUpdatedUtc -lt $SmokeStartedAt) {
        Fail "$Label.statusUpdatedUtc must be at or after release smoke start $($SmokeStartedAt.ToString('o')); actual value: $($statusUpdatedUtc.ToString('o'))"
    }
}

function Assert-PythonRuntimeEvidence {
    param([object]$SmokeManifest)

    foreach ($field in @(
        'python_runtime_manifest',
        'install_state',
        'private_python_path',
        'private_python_version',
        'rook_venv_path',
        'chirp_venv_path',
        'rook_import_file',
        'chirp_import_file',
        'pip_check',
        'license_provenance',
        'config_identity',
        'no_index_install',
        'chirp_git_sha',
        'chirp_source_archive_sha256'
    )) {
        $null = Require-JsonField -Json $SmokeManifest -Field $field -Label 'release smoke manifest'
    }

    $pythonRuntimeManifestPath = Require-File -Path ([string]$SmokeManifest.python_runtime_manifest) -Label 'python_runtime_manifest'
    $installStatePath = Require-File -Path ([string]$SmokeManifest.install_state) -Label 'install_state'
    $pythonRuntimeManifest = Get-Content -LiteralPath $pythonRuntimeManifestPath -Raw | ConvertFrom-Json
    $installState = Get-Content -LiteralPath $installStatePath -Raw | ConvertFrom-Json

    $privatePythonPath = ([string]$SmokeManifest.private_python_path).Replace('/', '\')
    if ($privatePythonPath -notmatch '(?i)\\Rook\\python\\cpython-3\.11\.9\\python\.exe$') {
        Fail "release smoke manifest.private_python_path must point to Rook private CPython 3.11.9; actual value: $($SmokeManifest.private_python_path)"
    }
    if ([string]$SmokeManifest.private_python_version -ne '3.11.9') {
        Fail "release smoke manifest.private_python_version must be 3.11.9; actual value: $($SmokeManifest.private_python_version)"
    }

    $rookImportFile = ([string]$SmokeManifest.rook_import_file).Replace('/', '\')
    if ($rookImportFile -notmatch '(?i)\\Rook\\venv\\Lib\\site-packages\\rook\\') {
        Fail "release smoke manifest.rook_import_file must resolve from Rook venv site-packages; actual value: $($SmokeManifest.rook_import_file)"
    }

    $chirpImportFile = ([string]$SmokeManifest.chirp_import_file).Replace('/', '\')
    if ($chirpImportFile -notmatch '(?i)\\Rook\\app\\chirp\\.venv\\Lib\\site-packages\\chirp\\') {
        Fail "release smoke manifest.chirp_import_file must resolve from Chirp venv site-packages; actual value: $($SmokeManifest.chirp_import_file)"
    }

    Assert-BooleanField -Json $SmokeManifest -Field 'no_index_install' -Label 'release smoke manifest' -Expected $true
    $pipCheck = Require-JsonField -Json $SmokeManifest -Field 'pip_check' -Label 'release smoke manifest'
    Assert-BooleanField -Json (Require-JsonField -Json $pipCheck -Field 'rook' -Label 'release smoke manifest.pip_check') -Field 'ok' -Label 'release smoke manifest.pip_check.rook' -Expected $true
    Assert-BooleanField -Json (Require-JsonField -Json $pipCheck -Field 'chirp' -Label 'release smoke manifest.pip_check') -Field 'ok' -Label 'release smoke manifest.pip_check.chirp' -Expected $true

    $configIdentity = Require-JsonField -Json $SmokeManifest -Field 'config_identity' -Label 'release smoke manifest'
    $chatServicePythonPath = ([string](Require-JsonField -Json $configIdentity -Field 'chat_service_python_path' -Label 'release smoke manifest.config_identity')).Replace('/', '\')
    if ($chatServicePythonPath -ne $privatePythonPath) {
        Fail "release smoke manifest.config_identity.chat_service_python_path must match private_python_path"
    }
    $chirpHome = ([string](Require-JsonField -Json $configIdentity -Field 'chirp_home' -Label 'release smoke manifest.config_identity')).Replace('/', '\')
    if ($chirpHome -notmatch '(?i)\\Rook\\app\\chirp$') {
        Fail "release smoke manifest.config_identity.chirp_home must point to Rook app Chirp home; actual value: $($configIdentity.chirp_home)"
    }

    if ([int]$installState.schema_version -ne 1) {
        Fail 'install_state.schema_version must be 1'
    }

    $licenseProvenance = Require-JsonField -Json $pythonRuntimeManifest -Field 'license_provenance' -Label 'python_runtime_manifest'
    $pythonRuntimeLicense = Require-JsonField -Json $licenseProvenance -Field 'python_runtime' -Label 'python_runtime_manifest.license_provenance'
    if ([string]$pythonRuntimeLicense.package -ne 'python') {
        Fail "python_runtime_manifest.license_provenance.python_runtime.package must be python; actual value: $($pythonRuntimeLicense.package)"
    }
    $thirdPartyWheels = @(Require-JsonField -Json $licenseProvenance -Field 'third_party_wheels' -Label 'python_runtime_manifest.license_provenance')
    if ($thirdPartyWheels.Count -lt 1) {
        Fail 'python_runtime_manifest.license_provenance.third_party_wheels must contain at least one wheel entry'
    }

    $securityMitigations = Require-JsonField -Json $pythonRuntimeManifest -Field 'security_mitigations' -Label 'python_runtime_manifest'
    $diskcacheMitigation = Require-JsonField -Json $securityMitigations -Field 'diskcache_cve_2025_69872' -Label 'python_runtime_manifest.security_mitigations'
    if ([string]$diskcacheMitigation.id -ne 'CVE-2025-69872') {
        Fail "python_runtime_manifest.security_mitigations.diskcache_cve_2025_69872.id must be CVE-2025-69872; actual value: $($diskcacheMitigation.id)"
    }
    if ([string]$diskcacheMitigation.package -ne 'diskcache') {
        Fail "python_runtime_manifest.security_mitigations.diskcache_cve_2025_69872.package must be diskcache; actual value: $($diskcacheMitigation.package)"
    }
    foreach ($runtimeName in @('rook', 'chirp')) {
        $runtimeMitigation = Require-JsonField -Json $diskcacheMitigation -Field $runtimeName -Label 'python_runtime_manifest.security_mitigations.diskcache_cve_2025_69872'
        Assert-BooleanField -Json $runtimeMitigation -Field 'restrict_pickle' -Label "python_runtime_manifest.security_mitigations.diskcache_cve_2025_69872.$runtimeName" -Expected $true
        $cacheDir = [string](Require-JsonField -Json $runtimeMitigation -Field 'disk_cache_dir' -Label "python_runtime_manifest.security_mitigations.diskcache_cve_2025_69872.$runtimeName")
        if ($cacheDir -notmatch '(?i)dspy-cache') {
            Fail "python_runtime_manifest.security_mitigations.diskcache_cve_2025_69872.$runtimeName.disk_cache_dir must point to a Rook-owned DSPy cache; actual value: $cacheDir"
        }
    }

    $manifestChirpGitSha = [string](Require-JsonField -Json $pythonRuntimeManifest -Field 'chirp_git_sha' -Label 'python_runtime_manifest')
    if ([string]$SmokeManifest.chirp_git_sha -ne $manifestChirpGitSha) {
        Fail 'release smoke manifest chirp_git_sha must match python_runtime_manifest chirp_git_sha'
    }
    $manifestChirpSourceArchiveSha = [string](Require-JsonField -Json $pythonRuntimeManifest -Field 'chirp_source_archive_sha256' -Label 'python_runtime_manifest')
    if ([string]$SmokeManifest.chirp_source_archive_sha256 -ne $manifestChirpSourceArchiveSha) {
        Fail 'release smoke manifest chirp_source_archive_sha256 must match python_runtime_manifest chirp_source_archive_sha256'
    }

    return [ordered]@{
        python_runtime_manifest_path = $pythonRuntimeManifestPath
        install_state_path = $installStatePath
        private_python_path = [string]$SmokeManifest.private_python_path
        private_python_version = [string]$SmokeManifest.private_python_version
        rook_venv_path = [string]$SmokeManifest.rook_venv_path
        chirp_venv_path = [string]$SmokeManifest.chirp_venv_path
        rook_import_file = [string]$SmokeManifest.rook_import_file
        chirp_import_file = [string]$SmokeManifest.chirp_import_file
        no_index_install = $true
        pip_check = $pipCheck
        license_provenance = [ordered]@{
            python_runtime_package = [string]$pythonRuntimeLicense.package
            third_party_wheel_count = $thirdPartyWheels.Count
        }
        security_mitigations = [ordered]@{
            diskcache_cve_2025_69872 = [ordered]@{
                package = [string]$diskcacheMitigation.package
                rook_restrict_pickle = $true
                chirp_restrict_pickle = $true
            }
        }
        chirp_git_sha = [string]$SmokeManifest.chirp_git_sha
        chirp_source_archive_sha256 = [string]$SmokeManifest.chirp_source_archive_sha256
    }
}

if ($Version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+$') {
    Fail "version must be X.Y.Z; actual value: $Version"
}

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}
$RepoRoot = Require-Directory -Path $RepoRoot -Label 'RepoRoot'

$checkedOutHead = Resolve-GitHead -Root $RepoRoot
if ([string]::IsNullOrWhiteSpace($GitSha)) {
    $GitSha = $checkedOutHead
} else {
    $rawGitSha = $GitSha.Trim().ToLowerInvariant()
    if ($rawGitSha -notmatch '^[0-9a-f]{40}$') {
        Fail "GitSha must be a full 40-character commit SHA; actual value: $GitSha"
    }
    if ($rawGitSha -ne $checkedOutHead) {
        Fail "GitSha does not match checked-out HEAD. Expected $checkedOutHead, actual $rawGitSha"
    }
    Assert-GitCommitExists -Root $RepoRoot -CommitSha $rawGitSha
    $GitSha = $rawGitSha
}

if ([string]::IsNullOrWhiteSpace($InstallerPath)) {
    $InstallerPath = Join-Path $RepoRoot "installer\output\Rook-Setup-$Version.exe"
}
if ([string]::IsNullOrWhiteSpace($FfmpegSourceBundleManifestPath)) {
    $FfmpegSourceBundleManifestPath = Join-Path $RepoRoot 'artifacts\ffmpeg\ffmpeg-8.1.1-rook-minimal\rook-ffmpeg-source-bundle-manifest.json'
}
if ([string]::IsNullOrWhiteSpace($OutputManifestPath)) {
    $OutputManifestPath = Join-Path $RepoRoot "installer\output\release-manifest-$Version.json"
}

$buildStartedAtValue = $null
if (-not [string]::IsNullOrWhiteSpace($BuildStartedAt)) {
    $parsedBuildStart = [DateTimeOffset]::MinValue
    if (-not [DateTimeOffset]::TryParse($BuildStartedAt, [ref]$parsedBuildStart)) {
        Fail "BuildStartedAt is not a valid timestamp: $BuildStartedAt"
    }
    $buildStartedAtValue = $parsedBuildStart
}

$expectedFileVersion = "$Version.0"
$installerPathResolved = Require-File -Path $InstallerPath -Label 'installer'
$installerItem = Get-Item -LiteralPath $installerPathResolved
if ($installerItem.Name -ne "Rook-Setup-$Version.exe") {
    Fail "installer filename must be Rook-Setup-$Version.exe; actual value: $($installerItem.Name)"
}
if ($installerItem.Length -lt $MinInstallerBytes) {
    Fail "installer is smaller than expected: $($installerItem.Length) bytes"
}
Assert-FileNewerThanBuildStart -Path $installerPathResolved -StartedAt $buildStartedAtValue
$installerSha256 = Get-Sha256 -Path $installerPathResolved

$nativePath = Require-File -Path (Join-Path $RepoRoot 'src\RookNative\bin\Release\x64\RookNative.rhp') -Label 'native RHP'
Assert-NativeFileVersion -Path $nativePath -Expected $expectedFileVersion
Assert-FileNewerThanBuildStart -Path $nativePath -StartedAt $buildStartedAtValue

$managedArtifacts = @(
    @{ Runtime = 'net8.0'; Path = Join-Path $RepoRoot 'src\Rook\bin\Release\net8.0\Rook.rhp'; RuntimeConfig = Join-Path $RepoRoot 'src\Rook\bin\Release\net8.0\Rook.runtimeconfig.json' },
    @{ Runtime = 'net7.0'; Path = Join-Path $RepoRoot 'src\Rook\bin\Release\net7.0\Rook.rhp'; RuntimeConfig = Join-Path $RepoRoot 'src\Rook\bin\Release\net7.0\Rook.runtimeconfig.json' },
    @{ Runtime = 'net48'; Path = Join-Path $RepoRoot 'src\Rook\bin\Release\net48\Rook.rhp'; RuntimeConfig = $null }
)

foreach ($artifact in $managedArtifacts) {
    $managedPath = Require-File -Path $artifact.Path -Label "$($artifact.Runtime) managed RHP"
    Assert-ManagedAssemblyVersion -Path $managedPath -Expected $expectedFileVersion
    Assert-FileNewerThanBuildStart -Path $managedPath -StartedAt $buildStartedAtValue
    if ($artifact.RuntimeConfig) {
        $runtimeConfigPath = Require-File -Path $artifact.RuntimeConfig -Label "$($artifact.Runtime) runtimeconfig"
        Assert-RuntimeConfigTfm -Path $runtimeConfigPath -ExpectedTfm $artifact.Runtime
    }
}

$rookBimPath = Require-File -Path (Join-Path $RepoRoot 'src\Rook\bin\Release\net48\RookBim.dll') -Label 'RookBIM net48 module'
Assert-ManagedAssemblyVersion -Path $rookBimPath -Expected $expectedFileVersion
Assert-FileNewerThanBuildStart -Path $rookBimPath -StartedAt $buildStartedAtValue

$sourceBundleManifestPathResolved = Require-File -Path $FfmpegSourceBundleManifestPath -Label 'FFmpeg source-bundle manifest'
$sourceBundleManifest = Get-Content -LiteralPath $sourceBundleManifestPathResolved -Raw | ConvertFrom-Json
$sourceBundlePath = Require-File -Path (Require-JsonField -Json $sourceBundleManifest -Field 'bundle_path' -Label 'FFmpeg source-bundle manifest') -Label 'FFmpeg source bundle'
$sourceBundleSha256 = Get-Sha256 -Path $sourceBundlePath
$manifestSourceBundleSha = ([string](Require-JsonField -Json $sourceBundleManifest -Field 'bundle_sha256' -Label 'FFmpeg source-bundle manifest')).ToUpperInvariant()
if ($sourceBundleSha256 -ne $manifestSourceBundleSha) {
    Fail "FFmpeg source bundle checksum mismatch. Expected $manifestSourceBundleSha, actual $sourceBundleSha256"
}

$smokeManifestPathResolved = Require-File -Path $SmokeManifestPath -Label 'release smoke manifest'
$smokeManifest = Get-Content -LiteralPath $smokeManifestPathResolved -Raw | ConvertFrom-Json
foreach ($field in @(
    'git_sha',
    'installer_sha256',
    'rook_version',
    'smoke_started_utc',
    'standalone_rhino',
    'rhino_inside_revit'
)) {
    $null = Require-JsonField -Json $smokeManifest -Field $field -Label 'release smoke manifest'
}

$smokeStartedAt = Require-TimestampField -Json $smokeManifest -Field 'smoke_started_utc' -Label 'release smoke manifest'

if ([string]$smokeManifest.git_sha -ne $GitSha) {
    Fail "smoke manifest git_sha does not match release git SHA. Expected $GitSha, actual $($smokeManifest.git_sha)"
}
if (([string]$smokeManifest.installer_sha256).ToUpperInvariant() -ne $installerSha256) {
    Fail "smoke manifest installer_sha256 does not match installer hash"
}
if ([string]$smokeManifest.rook_version -ne $Version) {
    Fail "smoke manifest rook_version does not match release version. Expected $Version, actual $($smokeManifest.rook_version)"
}
Assert-SmokeHostSuccess -HostManifest $smokeManifest.standalone_rhino -Label 'release smoke manifest standalone_rhino' -RequiredVersionFields @('rhino_version') -ExpectedRhinoInside $false -SmokeStartedAt $smokeStartedAt
Assert-SmokeHostSuccess -HostManifest $smokeManifest.rhino_inside_revit -Label 'release smoke manifest rhino_inside_revit' -RequiredVersionFields @('rhino_version', 'revit_version', 'rhino_inside_version') -ExpectedRhinoInside $true -SmokeStartedAt $smokeStartedAt
$pythonRuntimeEvidence = Assert-PythonRuntimeEvidence -SmokeManifest $smokeManifest

$outputManifestParent = Split-Path -Parent $OutputManifestPath
if ($outputManifestParent) {
    New-Item -ItemType Directory -Path $outputManifestParent -Force | Out-Null
}

$releaseManifest = [ordered]@{
    schema_version = 1
    version = $Version
    git_sha = $GitSha
    generated_at = [DateTimeOffset]::UtcNow.ToString('o')
    installer_path = $installerPathResolved
    installer_sha256 = $installerSha256
    ffmpeg_source_bundle_path = $sourceBundlePath
    ffmpeg_source_bundle_sha256 = $sourceBundleSha256
    ffmpeg_source_bundle_manifest_path = $sourceBundleManifestPathResolved
    smoke_manifest_path = $smokeManifestPathResolved
    smoke = $smokeManifest
    python_runtime = $pythonRuntimeEvidence
    native = [ordered]@{
        path = $nativePath
        file_version = $expectedFileVersion
        sha256 = Get-Sha256 -Path $nativePath
    }
    managed = @($managedArtifacts | ForEach-Object {
        $path = (Resolve-Path -LiteralPath $_.Path).Path
        [ordered]@{
            runtime = $_.Runtime
            path = $path
            assembly_version = $expectedFileVersion
            sha256 = Get-Sha256 -Path $path
        }
    })
    rook_bim = [ordered]@{
        runtime = 'net48'
        path = $rookBimPath
        assembly_version = $expectedFileVersion
        sha256 = Get-Sha256 -Path $rookBimPath
    }
}

$releaseManifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $OutputManifestPath -Encoding UTF8

Write-Host "Release artifact validation passed: $Version $GitSha"
Write-Host "Release manifest: $OutputManifestPath"
