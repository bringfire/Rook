$ErrorActionPreference = 'Stop'

$TestRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestRoot)
$Validator = Join-Path $RepoRoot 'scripts\validate-release-artifacts.ps1'

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) {
        throw $Message
    }
}

function Assert-Contains {
    param([string]$Text, [string]$Expected, [string]$Message)
    Assert-True -Condition $Text.Contains($Expected) -Message $Message
}

function Get-RepoReleaseVersion {
    $pyprojectPath = Join-Path $RepoRoot 'mcp_server\pyproject.toml'
    $pyprojectText = Get-Content -LiteralPath $pyprojectPath -Raw
    if ($pyprojectText -notmatch '(?m)^version\s*=\s*"([^"]+)"') {
        throw "Could not resolve release version from $pyprojectPath"
    }
    return $Matches[1]
}

function Invoke-Validator {
    param([string[]]$Arguments)

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = @(& powershell -NoProfile -ExecutionPolicy Bypass @Arguments 2>&1 | ForEach-Object { $_.ToString() })
        return [pscustomobject]@{
            ExitCode = $LASTEXITCODE
            Output = ($output -join "`n")
        }
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
}

function New-ValidatorFixture {
    param(
        [string]$Version = (Get-RepoReleaseVersion),
        [string]$GitSha = '',
        [string]$PingResult = 'pong',
        [int]$NativePort = 9876,
        [object]$PluginManagerListed = $true,
        [string]$ChatServiceHealth = 'ok',
        [string]$ChatServiceManifestPath = 'C:/Users/test/AppData/Roaming/McNeel/Rhinoceros/8.0/Plug-ins/RookNative/RookChatService.json',
        [string]$LoadedNativePath = 'C:/Users/test/AppData/Roaming/McNeel/Rhinoceros/8.0/Plug-ins/RookNative/RookNative.rhp',
        [string]$LoadedCompanionPath = 'C:/Users/test/AppData/Roaming/McNeel/Rhinoceros/8.0/Plug-ins/RookNative/net7.0/Rook.rhp',
        [string]$SmokeStartedUtc = '2026-05-26T17:59:00.0000000Z',
        [string]$StandaloneCompanionAssemblyLocation = 'C:/Users/test/AppData/Roaming/McNeel/Rhinoceros/8.0/Plug-ins/RookNative/net7.0/Rook.rhp',
        [string]$StandaloneCompanionRuntimeChild = 'net7.0',
        [string]$RhinoInsideCompanionAssemblyLocation = 'C:/Users/test/AppData/Roaming/McNeel/Rhinoceros/8.0/Plug-ins/RookNative/net48/Rook.rhp',
        [string]$RhinoInsideCompanionRuntimeChild = 'net48',
        [bool]$CompanionStartupComplete = $true,
        [bool]$CompanionBridgeRegistered = $true,
        [string]$CompanionStatusUpdatedUtc = '2026-05-26T18:00:06.0000000Z',
        [switch]$LegacySingleHost
    )

    if ([string]::IsNullOrWhiteSpace($GitSha)) {
        $GitSha = ((& git -C $RepoRoot rev-parse HEAD) -join '').Trim()
        Assert-True -Condition ($LASTEXITCODE -eq 0 -and $GitSha) -Message 'Could not resolve git SHA for validator test.'
    }

    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("rook-release-artifact-test-" + [System.Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null

    $installerPath = Join-Path $tempRoot "Rook-Setup-$Version.exe"
    Set-Content -LiteralPath $installerPath -Value 'fake installer bytes' -Encoding ASCII
    $installerSha = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash

    $sourceBundlePath = Join-Path $tempRoot 'rook-ffmpeg-8.1.1-source-bundle.zip'
    Set-Content -LiteralPath $sourceBundlePath -Value 'fake ffmpeg source bundle bytes' -Encoding ASCII
    $sourceBundleSha = (Get-FileHash -LiteralPath $sourceBundlePath -Algorithm SHA256).Hash
    $sourceBundleManifestPath = Join-Path $tempRoot 'rook-ffmpeg-source-bundle-manifest.json'
    [ordered]@{
        bundle_path = $sourceBundlePath
        bundle_sha256 = $sourceBundleSha
    } | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $sourceBundleManifestPath -Encoding UTF8

    $occtProvenance = Get-Content -LiteralPath (Join-Path $RepoRoot 'third_party\occt\occt-provenance.json') -Raw | ConvertFrom-Json
    $occtBundlePath = Join-Path $tempRoot ([string]$occtProvenance.source_bundle_name)
    Set-Content -LiteralPath $occtBundlePath -Value 'fake occt source bundle bytes' -Encoding ASCII
    $occtManifestPath = Join-Path $tempRoot 'rook-occt-source-bundle-manifest.json'
    [ordered]@{
        bundle_path = $occtBundlePath
        bundle_sha256 = (Get-FileHash -LiteralPath $occtBundlePath -Algorithm SHA256).Hash
        source_commit = [string]$occtProvenance.source.commit
    } | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $occtManifestPath -Encoding UTF8

    $smokeManifestPath = Join-Path $tempRoot "smoke-$Version.json"
    $pythonRuntimeManifestPath = Join-Path $tempRoot 'python-runtime-manifest.json'
    $installStatePath = Join-Path $tempRoot 'install-state.json'
    $rookLockPath = Join-Path $tempRoot 'requirements-rook-lock.txt'
    $chirpLockPath = Join-Path $tempRoot 'requirements-chirp-lock.txt'
    $privatePythonPath = 'C:/Users/test/AppData/Local/Rook/python/cpython-3.11.9/python.exe'
    $rookVenvPath = 'C:/Users/test/AppData/Local/Rook/venv'
    $chirpVenvPath = 'C:/Users/test/AppData/Local/Rook/app/chirp/.venv'
    $rookImportFile = 'C:/Users/test/AppData/Local/Rook/venv/Lib/site-packages/rook/__init__.py'
    $chirpImportFile = 'C:/Users/test/AppData/Local/Rook/app/chirp/.venv/Lib/site-packages/chirp/__init__.py'
    $chirpSourceArchiveSha = '1111111111111111111111111111111111111111111111111111111111111111'
    Set-Content -LiteralPath $rookLockPath -Value 'rook-mcp==1.5.10 --hash=sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' -Encoding ASCII
    Set-Content -LiteralPath $chirpLockPath -Value 'chirp==0.1.0 --hash=sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' -Encoding ASCII
    $rookLockSha = (Get-FileHash -LiteralPath $rookLockPath -Algorithm SHA256).Hash.ToUpperInvariant()
    $chirpLockSha = (Get-FileHash -LiteralPath $chirpLockPath -Algorithm SHA256).Hash.ToUpperInvariant()

    [ordered]@{
        schema_version = 1
        release_version = $Version
        rook_git_sha = $GitSha
        rook_source_archive_sha256 = '2222222222222222222222222222222222222222222222222222222222222222'
        python_runtime = [ordered]@{
            package = 'python'
            version = '3.11.9'
            nuget_sha256 = '9283876D58C017E0E846F95B490DA3BCA0FC0A6EE1134B2870677CFB7EEC3C67'
        }
        license_provenance = [ordered]@{
            python_runtime = [ordered]@{
                package = 'python'
                version = '3.11.9'
            }
            third_party_wheels = @(
                [ordered]@{
                    name = 'rook-mcp'
                    version = $Version
                    license = 'MIT'
                }
            )
        }
        lockfiles = [ordered]@{
            rook = [ordered]@{
                path = $rookLockPath
                sha256 = $rookLockSha
            }
            chirp = [ordered]@{
                path = $chirpLockPath
                sha256 = $chirpLockSha
            }
        }
        security_mitigations = [ordered]@{
            diskcache_cve_2025_69872 = [ordered]@{
                id = 'CVE-2025-69872'
                package = 'diskcache'
                rook = [ordered]@{
                    restrict_pickle = $true
                    disk_cache_dir = 'C:/Users/test/AppData/Local/Rook/data/dspy-cache'
                }
                chirp = [ordered]@{
                    restrict_pickle = $true
                    disk_cache_dir = 'C:/Users/test/AppData/Local/Rook/app/chirp/data/dspy-cache'
                }
            }
        }
        chirp_git_sha = $GitSha
        chirp_source_archive_sha256 = $chirpSourceArchiveSha
    } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $pythonRuntimeManifestPath -Encoding UTF8
    $pythonRuntimeManifestSha = (Get-FileHash -LiteralPath $pythonRuntimeManifestPath -Algorithm SHA256).Hash.ToUpperInvariant()

    [ordered]@{
        schema_version = 1
        python = [ordered]@{
            path = $privatePythonPath
            version = '3.11.9'
            identity_hash = $pythonRuntimeManifestSha
            runtime_manifest_sha256 = $pythonRuntimeManifestSha
        }
        rook = [ordered]@{
            venv_path = $rookVenvPath
            python_path = "$rookVenvPath/Scripts/python.exe"
            python_identity_hash = $pythonRuntimeManifestSha
            lockfile_path = $rookLockPath
            lockfile_sha256 = $rookLockSha
            pip_check = 'No broken requirements found.'
        }
        chirp = [ordered]@{
            venv_path = $chirpVenvPath
            python_path = "$chirpVenvPath/Scripts/python.exe"
            python_identity_hash = $pythonRuntimeManifestSha
            lockfile_path = $chirpLockPath
            lockfile_sha256 = $chirpLockSha
            pip_check = 'No broken requirements found.'
        }
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $installStatePath -Encoding UTF8

    if ($LegacySingleHost) {
        [ordered]@{
            git_sha = $GitSha
            installer_sha256 = $installerSha
            rhino_version = '8.test'
            revit_version = '2025.test'
            rhino_inside_version = 'test'
            rook_version = $Version
            smoke_started_utc = $SmokeStartedUtc
            native_port = $NativePort
            ping_result = $PingResult
            loaded_native_path = $LoadedNativePath
            loaded_companion_path = $LoadedCompanionPath
        } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $smokeManifestPath -Encoding UTF8
    } else {
        [ordered]@{
            git_sha = $GitSha
            installer_sha256 = $installerSha
            rook_version = $Version
            smoke_started_utc = $SmokeStartedUtc
            python_runtime_manifest = $pythonRuntimeManifestPath
            install_state = $installStatePath
            private_python_path = $privatePythonPath
            private_python_version = '3.11.9'
            rook_venv_path = $rookVenvPath
            chirp_venv_path = $chirpVenvPath
            rook_import_file = $rookImportFile
            chirp_import_file = $chirpImportFile
            pip_check = [ordered]@{
                rook = [ordered]@{ ok = $true }
                chirp = [ordered]@{ ok = $true }
            }
            rook_dspy_cache = [ordered]@{
                restrict_pickle = $true
                disk_cache_dir = 'C:/Users/test/AppData/Local/Rook/data/dspy-cache'
            }
            chirp_dspy_cache = [ordered]@{
                restrict_pickle = $true
                disk_cache_dir = 'C:/Users/test/AppData/Local/Rook/app/chirp/data/dspy-cache'
            }
            license_provenance = [ordered]@{
                manifest_path = $pythonRuntimeManifestPath
            }
            config_identity = [ordered]@{
                chat_service_python_path = "$rookVenvPath/Scripts/python.exe"
                chirp_home = 'C:/Users/test/AppData/Local/Rook/app/chirp'
                release_pythonpath_entries = $false
            }
            no_index_install = $true
            chirp_git_sha = $GitSha
            chirp_source_archive_sha256 = $chirpSourceArchiveSha
            standalone_rhino = [ordered]@{
                rhino_version = '8.test'
                host_runtime = 'net7.0'
                native_port = $NativePort
                ping_result = $PingResult
                plugin_manager_listed = $PluginManagerListed
                chat_service_manifest_path = $ChatServiceManifestPath
                chat_service_health = $ChatServiceHealth
                loaded_native_path = $LoadedNativePath
                loaded_companion_path = $LoadedCompanionPath
                companion_self_report = [ordered]@{
                    processId = 1111
                    processName = 'Rhino'
                    rhinoInside = $false
                    assemblyLocation = $StandaloneCompanionAssemblyLocation
                    runtimeChild = $StandaloneCompanionRuntimeChild
                    targetFramework = '.NETCoreApp,Version=v7.0'
                    startupGateAttached = $false
                    deferredLocalStartupComplete = $true
                    startupComplete = $CompanionStartupComplete
                    bridgeRegistered = $CompanionBridgeRegistered
                    onLoadUtc = '2026-05-26T18:00:00.0000000Z'
                    startupCompleteUtc = '2026-05-26T18:00:05.0000000Z'
                    statusUpdatedUtc = $CompanionStatusUpdatedUtc
                }
            }
            rhino_inside_revit = [ordered]@{
                rhino_version = '8.test'
                revit_version = '2025.test'
                rhino_inside_version = 'test'
                host_runtime = $RhinoInsideCompanionRuntimeChild
                native_port = $NativePort
                ping_result = $PingResult
                plugin_manager_listed = $PluginManagerListed
                chat_service_manifest_path = $ChatServiceManifestPath
                chat_service_health = $ChatServiceHealth
                loaded_native_path = $LoadedNativePath
                loaded_companion_path = $LoadedCompanionPath
                companion_self_report = [ordered]@{
                    processId = 2222
                    processName = 'Revit'
                    rhinoInside = $true
                    assemblyLocation = $RhinoInsideCompanionAssemblyLocation
                    runtimeChild = $RhinoInsideCompanionRuntimeChild
                    targetFramework = '.NETFramework,Version=v4.8'
                    startupGateAttached = $false
                    deferredLocalStartupComplete = $true
                    startupComplete = $CompanionStartupComplete
                    bridgeRegistered = $CompanionBridgeRegistered
                    onLoadUtc = '2026-05-26T18:00:00.0000000Z'
                    startupCompleteUtc = '2026-05-26T18:00:05.0000000Z'
                    statusUpdatedUtc = $CompanionStatusUpdatedUtc
                }
            }
        } | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $smokeManifestPath -Encoding UTF8
    }

    return [pscustomobject]@{
        Version = $Version
        GitSha = $GitSha
        TempRoot = $tempRoot
        InstallerPath = $installerPath
        SmokeManifestPath = $smokeManifestPath
        OutputManifestPath = (Join-Path $tempRoot "release-manifest-$Version.json")
        SourceBundleManifestPath = $sourceBundleManifestPath
        OcctSourceBundleManifestPath = $occtManifestPath
        OcctBundlePath = $occtBundlePath
    }
}

function Test-ReleaseValidatorRequiresPythonRuntimeEvidence {
    $validator = Get-Content -Path $Validator -Raw
    Assert-Contains -Text $validator -Expected 'python_runtime_manifest' -Message 'Release validator must require python_runtime_manifest in smoke evidence.'
    Assert-Contains -Text $validator -Expected 'install_state' -Message 'Release validator must require install_state evidence.'
    Assert-Contains -Text $validator -Expected 'private_python_path' -Message 'Smoke manifest must record private Python path.'
    Assert-Contains -Text $validator -Expected 'private_python_version' -Message 'Smoke manifest must record private Python version.'
    Assert-Contains -Text $validator -Expected 'rook_import_file' -Message 'Smoke manifest must record rook.__file__.'
    Assert-Contains -Text $validator -Expected 'chirp_import_file' -Message 'Smoke manifest must record chirp.__file__.'
    Assert-Contains -Text $validator -Expected 'pip_check' -Message 'Smoke manifest must record pip check results.'
    Assert-Contains -Text $validator -Expected 'rook_dspy_cache' -Message 'Smoke manifest must record installed Rook DSPy cache mitigation evidence.'
    Assert-Contains -Text $validator -Expected 'chirp_dspy_cache' -Message 'Smoke manifest must record installed Chirp DSPy cache mitigation evidence.'
    Assert-Contains -Text $validator -Expected 'license_provenance' -Message 'Release validator must require runtime and wheel license/provenance evidence.'
    Assert-Contains -Text $validator -Expected 'security_mitigations' -Message 'Release validator must require runtime security mitigation evidence.'
    Assert-Contains -Text $validator -Expected 'diskcache_cve_2025_69872' -Message 'Release validator must require the DiskCache CVE mitigation evidence.'
    Assert-Contains -Text $validator -Expected 'restrict_pickle' -Message 'Release validator must require DSPy restricted pickle evidence.'
    Assert-Contains -Text $validator -Expected 'rook_git_sha' -Message 'Release validator must bind the Python payload to the Rook release git SHA.'
    Assert-Contains -Text $validator -Expected 'rook_source_archive_sha256' -Message 'Release validator must require Rook source archive provenance.'
    Assert-Contains -Text $validator -Expected 'release_version' -Message 'Release validator must bind the Python payload to the release version.'
    Assert-Contains -Text $validator -Expected 'chirp_git_sha' -Message 'Release validator must require Chirp source identity.'
}

function Test-ValidatorWritesExactArtifactManifest {
    Assert-True -Condition (Test-Path $Validator) -Message "Validator script is missing: $Validator"
    $version = Get-RepoReleaseVersion
    $fixture = New-ValidatorFixture -Version $version

    try {
        $result = Invoke-Validator -Arguments @(
            '-File', $Validator,
            '-Version', $version,
            '-RepoRoot', $RepoRoot,
            '-GitSha', $fixture.GitSha,
            '-InstallerPath', $fixture.InstallerPath,
            '-FfmpegSourceBundleManifestPath', $fixture.SourceBundleManifestPath,
            '-OcctSourceBundleManifestPath', $fixture.OcctSourceBundleManifestPath,
            '-SmokeManifestPath', $fixture.SmokeManifestPath,
            '-OutputManifestPath', $fixture.OutputManifestPath,
            '-MinInstallerBytes', '1'
        )

        Assert-True -Condition ($result.ExitCode -eq 0) -Message "Validator failed unexpectedly. Output: $($result.Output)"
        Assert-True -Condition (Test-Path $fixture.OutputManifestPath) -Message 'Validator did not write the release manifest.'

        $manifestText = Get-Content -LiteralPath $fixture.OutputManifestPath -Raw
        Assert-Contains -Text $manifestText -Expected '"git_sha"' -Message 'Release manifest must contain git_sha.'
        Assert-Contains -Text $manifestText -Expected '"installer_sha256"' -Message 'Release manifest must contain installer_sha256.'
        Assert-Contains -Text $manifestText -Expected '"ffmpeg_source_bundle_sha256"' -Message 'Release manifest must contain ffmpeg_source_bundle_sha256.'
        Assert-Contains -Text $manifestText -Expected '"occt_source_bundle_sha256"' -Message 'Release manifest must contain occt_source_bundle_sha256.'
        Assert-Contains -Text $manifestText -Expected '"occt_source_commit"' -Message 'Release manifest must contain occt_source_commit.'
        Assert-Contains -Text $manifestText -Expected '"rook_bim"' -Message 'Release manifest must contain RookBIM artifact identity.'
        Assert-Contains -Text $manifestText -Expected '"runtime":  "net48"' -Message 'Release manifest must identify RookBIM as a net48 artifact.'
        Assert-Contains -Text $manifestText -Expected '"assembly_version"' -Message 'Release manifest must record RookBIM assembly version.'
    } finally {
        Remove-Item -LiteralPath $fixture.TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-ValidatorAcceptsInstallerOlderThanInstallerScriptByDefault {
    $fixture = New-ValidatorFixture

    try {
        $installerScript = Get-Item -LiteralPath (Join-Path $RepoRoot 'installer\RookSetup.iss')
        (Get-Item -LiteralPath $fixture.InstallerPath).LastWriteTimeUtc = $installerScript.LastWriteTimeUtc.AddMinutes(-5)

        $result = Invoke-Validator -Arguments @(
            '-File', $Validator,
            '-Version', $fixture.Version,
            '-RepoRoot', $RepoRoot,
            '-GitSha', $fixture.GitSha,
            '-InstallerPath', $fixture.InstallerPath,
            '-FfmpegSourceBundleManifestPath', $fixture.SourceBundleManifestPath,
            '-OcctSourceBundleManifestPath', $fixture.OcctSourceBundleManifestPath,
            '-SmokeManifestPath', $fixture.SmokeManifestPath,
            '-OutputManifestPath', $fixture.OutputManifestPath,
            '-MinInstallerBytes', '1'
        )

        Assert-True -Condition ($result.ExitCode -eq 0) -Message "Validator treated working-tree mtimes as a portable artifact invariant. Output: $($result.Output)"
    } finally {
        Remove-Item -LiteralPath $fixture.TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-ValidatorRejectsInstallerOlderThanInstallerScriptWhenRequired {
    $fixture = New-ValidatorFixture

    try {
        $installerScript = Get-Item -LiteralPath (Join-Path $RepoRoot 'installer\RookSetup.iss')
        (Get-Item -LiteralPath $fixture.InstallerPath).LastWriteTimeUtc = $installerScript.LastWriteTimeUtc.AddMinutes(-5)

        $result = Invoke-Validator -Arguments @(
            '-File', $Validator,
            '-Version', $fixture.Version,
            '-RepoRoot', $RepoRoot,
            '-GitSha', $fixture.GitSha,
            '-InstallerPath', $fixture.InstallerPath,
            '-FfmpegSourceBundleManifestPath', $fixture.SourceBundleManifestPath,
            '-OcctSourceBundleManifestPath', $fixture.OcctSourceBundleManifestPath,
            '-SmokeManifestPath', $fixture.SmokeManifestPath,
            '-OutputManifestPath', $fixture.OutputManifestPath,
            '-MinInstallerBytes', '1',
            '-RequireInstallerNewerThanScript'
        )

        Assert-True -Condition ($result.ExitCode -ne 0) -Message 'Validator accepted an installer built before the current installer script.'
        Assert-Contains -Text $result.Output -Expected 'installer is stale' -Message "Validator stale-installer error was not specific. Output: $($result.Output)"
    } finally {
        Remove-Item -LiteralPath $fixture.TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-DocumentedValidatorCommandDefaultsRepoRoot {
    $fixture = New-ValidatorFixture

    try {
        Push-Location $RepoRoot
        try {
            $result = Invoke-Validator -Arguments @(
                '-File', 'scripts\validate-release-artifacts.ps1',
                '-Version', $fixture.Version,
                '-GitSha', $fixture.GitSha,
                '-InstallerPath', $fixture.InstallerPath,
                '-FfmpegSourceBundleManifestPath', $fixture.SourceBundleManifestPath,
                '-OcctSourceBundleManifestPath', $fixture.OcctSourceBundleManifestPath,
                '-SmokeManifestPath', $fixture.SmokeManifestPath,
                '-OutputManifestPath', $fixture.OutputManifestPath,
                '-MinInstallerBytes', '1'
            )
        } finally {
            Pop-Location
        }

        Assert-True -Condition ($result.ExitCode -eq 0) -Message "Documented validator invocation without -RepoRoot failed. Output: $($result.Output)"
    } finally {
        Remove-Item -LiteralPath $fixture.TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-ValidatorRejectsGitShaThatDoesNotMatchCheckout {
    $bogusSha = '0000000000000000000000000000000000000000'
    $fixture = New-ValidatorFixture -GitSha $bogusSha

    try {
        $result = Invoke-Validator -Arguments @(
            '-File', $Validator,
            '-Version', $fixture.Version,
            '-RepoRoot', $RepoRoot,
            '-GitSha', $bogusSha,
            '-InstallerPath', $fixture.InstallerPath,
            '-FfmpegSourceBundleManifestPath', $fixture.SourceBundleManifestPath,
            '-OcctSourceBundleManifestPath', $fixture.OcctSourceBundleManifestPath,
            '-SmokeManifestPath', $fixture.SmokeManifestPath,
            '-OutputManifestPath', $fixture.OutputManifestPath,
            '-MinInstallerBytes', '1'
        )

        Assert-True -Condition ($result.ExitCode -ne 0) -Message 'Validator must reject a release GitSha that does not match the checked-out HEAD.'
        Assert-Contains -Text $result.Output -Expected 'does not match checked-out HEAD' -Message "Validator mismatch error was not specific. Output: $($result.Output)"
    } finally {
        Remove-Item -LiteralPath $fixture.TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-ValidatorRejectsFailedSmokeEvidence {
    $fixture = New-ValidatorFixture -PingResult 'FAILED' -NativePort 0 -LoadedNativePath 'C:/bogus/RookNative.rhp' -LoadedCompanionPath 'C:/bogus/Rook.rhp'

    try {
        $result = Invoke-Validator -Arguments @(
            '-File', $Validator,
            '-Version', $fixture.Version,
            '-RepoRoot', $RepoRoot,
            '-GitSha', $fixture.GitSha,
            '-InstallerPath', $fixture.InstallerPath,
            '-FfmpegSourceBundleManifestPath', $fixture.SourceBundleManifestPath,
            '-OcctSourceBundleManifestPath', $fixture.OcctSourceBundleManifestPath,
            '-SmokeManifestPath', $fixture.SmokeManifestPath,
            '-OutputManifestPath', $fixture.OutputManifestPath,
            '-MinInstallerBytes', '1'
        )

        Assert-True -Condition ($result.ExitCode -ne 0) -Message 'Validator must reject smoke evidence that records a failed ping, invalid port, or implausible loaded paths.'
        Assert-Contains -Text $result.Output -Expected 'ping_result' -Message "Validator smoke error was not specific. Output: $($result.Output)"
    } finally {
        Remove-Item -LiteralPath $fixture.TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-ValidatorRejectsMissingPluginManagerEvidence {
    $fixture = New-ValidatorFixture -PluginManagerListed $false

    try {
        $result = Invoke-Validator -Arguments @(
            '-File', $Validator,
            '-Version', $fixture.Version,
            '-RepoRoot', $RepoRoot,
            '-GitSha', $fixture.GitSha,
            '-InstallerPath', $fixture.InstallerPath,
            '-FfmpegSourceBundleManifestPath', $fixture.SourceBundleManifestPath,
            '-OcctSourceBundleManifestPath', $fixture.OcctSourceBundleManifestPath,
            '-SmokeManifestPath', $fixture.SmokeManifestPath,
            '-OutputManifestPath', $fixture.OutputManifestPath,
            '-MinInstallerBytes', '1'
        )

        Assert-True -Condition ($result.ExitCode -ne 0) -Message 'Validator accepted smoke evidence without Plugin Manager enumeration.'
        Assert-Contains -Text $result.Output -Expected 'plugin_manager_listed' -Message "Validator Plugin Manager evidence error was not specific. Output: $($result.Output)"
    } finally {
        Remove-Item -LiteralPath $fixture.TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-ValidatorRejectsMissingChatServiceEvidence {
    $fixture = New-ValidatorFixture -ChatServiceHealth 'not_connected'

    try {
        $result = Invoke-Validator -Arguments @(
            '-File', $Validator,
            '-Version', $fixture.Version,
            '-RepoRoot', $RepoRoot,
            '-GitSha', $fixture.GitSha,
            '-InstallerPath', $fixture.InstallerPath,
            '-FfmpegSourceBundleManifestPath', $fixture.SourceBundleManifestPath,
            '-OcctSourceBundleManifestPath', $fixture.OcctSourceBundleManifestPath,
            '-SmokeManifestPath', $fixture.SmokeManifestPath,
            '-OutputManifestPath', $fixture.OutputManifestPath,
            '-MinInstallerBytes', '1'
        )

        Assert-True -Condition ($result.ExitCode -ne 0) -Message 'Validator accepted smoke evidence without successful chat service health.'
        Assert-Contains -Text $result.Output -Expected 'chat_service_health' -Message "Validator chat service evidence error was not specific. Output: $($result.Output)"
    } finally {
        Remove-Item -LiteralPath $fixture.TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-ValidatorRejectsLegacySingleHostSmokeManifest {
    $fixture = New-ValidatorFixture -LegacySingleHost

    try {
        $result = Invoke-Validator -Arguments @(
            '-File', $Validator,
            '-Version', $fixture.Version,
            '-RepoRoot', $RepoRoot,
            '-GitSha', $fixture.GitSha,
            '-InstallerPath', $fixture.InstallerPath,
            '-FfmpegSourceBundleManifestPath', $fixture.SourceBundleManifestPath,
            '-OcctSourceBundleManifestPath', $fixture.OcctSourceBundleManifestPath,
            '-SmokeManifestPath', $fixture.SmokeManifestPath,
            '-OutputManifestPath', $fixture.OutputManifestPath,
            '-MinInstallerBytes', '1'
        )

        Assert-True -Condition ($result.ExitCode -ne 0) -Message 'Validator must reject legacy single-host smoke manifests that do not prove standalone Rhino and Rhino.Inside.Revit were both tested.'
        Assert-Contains -Text $result.Output -Expected 'standalone_rhino' -Message "Validator host coverage error was not specific. Output: $($result.Output)"
    } finally {
        Remove-Item -LiteralPath $fixture.TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-ValidatorUsesCompanionSelfReportAsAuthoritativePath {
    $fixture = New-ValidatorFixture -LoadedCompanionPath 'C:/bogus/from-module-enumeration/Rook.rhp'

    try {
        $result = Invoke-Validator -Arguments @(
            '-File', $Validator,
            '-Version', $fixture.Version,
            '-RepoRoot', $RepoRoot,
            '-GitSha', $fixture.GitSha,
            '-InstallerPath', $fixture.InstallerPath,
            '-FfmpegSourceBundleManifestPath', $fixture.SourceBundleManifestPath,
            '-OcctSourceBundleManifestPath', $fixture.OcctSourceBundleManifestPath,
            '-SmokeManifestPath', $fixture.SmokeManifestPath,
            '-OutputManifestPath', $fixture.OutputManifestPath,
            '-MinInstallerBytes', '1'
        )

        Assert-True -Condition ($result.ExitCode -eq 0) -Message "Validator must accept companion self-report even when loaded_companion_path is unusable module evidence. Output: $($result.Output)"
    } finally {
        Remove-Item -LiteralPath $fixture.TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-ValidatorRejectsIncompleteCompanionSelfReport {
    $fixture = New-ValidatorFixture -CompanionStartupComplete $false

    try {
        $result = Invoke-Validator -Arguments @(
            '-File', $Validator,
            '-Version', $fixture.Version,
            '-RepoRoot', $RepoRoot,
            '-GitSha', $fixture.GitSha,
            '-InstallerPath', $fixture.InstallerPath,
            '-FfmpegSourceBundleManifestPath', $fixture.SourceBundleManifestPath,
            '-OcctSourceBundleManifestPath', $fixture.OcctSourceBundleManifestPath,
            '-SmokeManifestPath', $fixture.SmokeManifestPath,
            '-OutputManifestPath', $fixture.OutputManifestPath,
            '-MinInstallerBytes', '1'
        )

        Assert-True -Condition ($result.ExitCode -ne 0) -Message 'Validator accepted companion self-report without startup completion.'
        Assert-Contains -Text $result.Output -Expected 'companion_self_report.startupComplete' -Message "Validator companion self-report error was not specific. Output: $($result.Output)"
    } finally {
        Remove-Item -LiteralPath $fixture.TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-ValidatorRejectsStaleCompanionSelfReport {
    $fixture = New-ValidatorFixture `
        -SmokeStartedUtc '2026-05-26T18:00:00.0000000Z' `
        -CompanionStatusUpdatedUtc '2026-05-26T17:59:59.0000000Z'

    try {
        $result = Invoke-Validator -Arguments @(
            '-File', $Validator,
            '-Version', $fixture.Version,
            '-RepoRoot', $RepoRoot,
            '-GitSha', $fixture.GitSha,
            '-InstallerPath', $fixture.InstallerPath,
            '-FfmpegSourceBundleManifestPath', $fixture.SourceBundleManifestPath,
            '-OcctSourceBundleManifestPath', $fixture.OcctSourceBundleManifestPath,
            '-SmokeManifestPath', $fixture.SmokeManifestPath,
            '-OutputManifestPath', $fixture.OutputManifestPath,
            '-MinInstallerBytes', '1'
        )

        Assert-True -Condition ($result.ExitCode -ne 0) -Message 'Validator accepted a stale companion self-report.'
        Assert-Contains -Text $result.Output -Expected 'companion_self_report.statusUpdatedUtc' -Message "Validator stale self-report error was not specific. Output: $($result.Output)"
    } finally {
        Remove-Item -LiteralPath $fixture.TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-ValidatorRejectsStaleInstallStateHashes {
    $fixture = New-ValidatorFixture

    try {
        $installStatePath = Join-Path $fixture.TempRoot 'install-state.json'
        $installState = Get-Content -LiteralPath $installStatePath -Raw | ConvertFrom-Json
        $installState.rook.lockfile_sha256 = '0000000000000000000000000000000000000000000000000000000000000000'
        $installState | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $installStatePath -Encoding UTF8

        $result = Invoke-Validator -Arguments @(
            '-File', $Validator,
            '-Version', $fixture.Version,
            '-RepoRoot', $RepoRoot,
            '-GitSha', $fixture.GitSha,
            '-InstallerPath', $fixture.InstallerPath,
            '-FfmpegSourceBundleManifestPath', $fixture.SourceBundleManifestPath,
            '-OcctSourceBundleManifestPath', $fixture.OcctSourceBundleManifestPath,
            '-SmokeManifestPath', $fixture.SmokeManifestPath,
            '-OutputManifestPath', $fixture.OutputManifestPath,
            '-MinInstallerBytes', '1'
        )

        Assert-True -Condition ($result.ExitCode -ne 0) -Message 'Validator accepted stale Rook install-state lockfile hash.'
        Assert-Contains -Text $result.Output -Expected 'install_state.rook.lockfile_sha256' -Message "Validator install-state hash error was not specific. Output: $($result.Output)"
    } finally {
        Remove-Item -LiteralPath $fixture.TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-ValidatorRejectsStaleInstallStateLockfilePath {
    $fixture = New-ValidatorFixture

    try {
        $installStatePath = Join-Path $fixture.TempRoot 'install-state.json'
        $installState = Get-Content -LiteralPath $installStatePath -Raw | ConvertFrom-Json
        $installState.chirp.lockfile_path = (Join-Path $fixture.TempRoot 'missing-chirp-lock.txt')
        $installState | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $installStatePath -Encoding UTF8

        $result = Invoke-Validator -Arguments @(
            '-File', $Validator,
            '-Version', $fixture.Version,
            '-RepoRoot', $RepoRoot,
            '-GitSha', $fixture.GitSha,
            '-InstallerPath', $fixture.InstallerPath,
            '-FfmpegSourceBundleManifestPath', $fixture.SourceBundleManifestPath,
            '-OcctSourceBundleManifestPath', $fixture.OcctSourceBundleManifestPath,
            '-SmokeManifestPath', $fixture.SmokeManifestPath,
            '-OutputManifestPath', $fixture.OutputManifestPath,
            '-MinInstallerBytes', '1'
        )

        Assert-True -Condition ($result.ExitCode -ne 0) -Message 'Validator accepted missing Chirp install-state lockfile path.'
        Assert-Contains -Text $result.Output -Expected 'install_state.chirp.lockfile_path' -Message "Validator install-state lockfile path error was not specific. Output: $($result.Output)"
    } finally {
        Remove-Item -LiteralPath $fixture.TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-ValidatorRejectsStaleInstallStatePythonPath {
    $fixture = New-ValidatorFixture

    try {
        $installStatePath = Join-Path $fixture.TempRoot 'install-state.json'
        $installState = Get-Content -LiteralPath $installStatePath -Raw | ConvertFrom-Json
        $installState.rook.python_path = 'C:/Users/test/AppData/Local/Rook/old-venv/Scripts/python.exe'
        $installState | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $installStatePath -Encoding UTF8

        $result = Invoke-Validator -Arguments @(
            '-File', $Validator,
            '-Version', $fixture.Version,
            '-RepoRoot', $RepoRoot,
            '-GitSha', $fixture.GitSha,
            '-InstallerPath', $fixture.InstallerPath,
            '-FfmpegSourceBundleManifestPath', $fixture.SourceBundleManifestPath,
            '-OcctSourceBundleManifestPath', $fixture.OcctSourceBundleManifestPath,
            '-SmokeManifestPath', $fixture.SmokeManifestPath,
            '-OutputManifestPath', $fixture.OutputManifestPath,
            '-MinInstallerBytes', '1'
        )

        Assert-True -Condition ($result.ExitCode -ne 0) -Message 'Validator accepted stale Rook install-state python path.'
        Assert-Contains -Text $result.Output -Expected 'install_state.rook.python_path' -Message "Validator install-state python path error was not specific. Output: $($result.Output)"
    } finally {
        Remove-Item -LiteralPath $fixture.TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-ValidatorRejectsStaleInstallStateRuntimePythonIdentity {
    $fixture = New-ValidatorFixture

    try {
        $installStatePath = Join-Path $fixture.TempRoot 'install-state.json'
        $installState = Get-Content -LiteralPath $installStatePath -Raw | ConvertFrom-Json
        $installState.chirp.python_identity_hash = '0000000000000000000000000000000000000000000000000000000000000000'
        $installState | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $installStatePath -Encoding UTF8

        $result = Invoke-Validator -Arguments @(
            '-File', $Validator,
            '-Version', $fixture.Version,
            '-RepoRoot', $RepoRoot,
            '-GitSha', $fixture.GitSha,
            '-InstallerPath', $fixture.InstallerPath,
            '-FfmpegSourceBundleManifestPath', $fixture.SourceBundleManifestPath,
            '-OcctSourceBundleManifestPath', $fixture.OcctSourceBundleManifestPath,
            '-SmokeManifestPath', $fixture.SmokeManifestPath,
            '-OutputManifestPath', $fixture.OutputManifestPath,
            '-MinInstallerBytes', '1'
        )

        Assert-True -Condition ($result.ExitCode -ne 0) -Message 'Validator accepted stale Chirp install-state Python identity hash.'
        Assert-Contains -Text $result.Output -Expected 'install_state.chirp.python_identity_hash' -Message "Validator install-state Python identity error was not specific. Output: $($result.Output)"
    } finally {
        Remove-Item -LiteralPath $fixture.TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-ValidatorRejectsSuffixOnlyDspyCachePaths {
    $fixture = New-ValidatorFixture

    try {
        $smokeManifest = Get-Content -LiteralPath $fixture.SmokeManifestPath -Raw | ConvertFrom-Json
        $smokeManifest.rook_dspy_cache.disk_cache_dir = 'D:/shadow/Rook/data/dspy-cache'
        $smokeManifest.chirp_dspy_cache.disk_cache_dir = 'D:/shadow/Rook/app/chirp/data/dspy-cache'
        $smokeManifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $fixture.SmokeManifestPath -Encoding UTF8

        $result = Invoke-Validator -Arguments @(
            '-File', $Validator,
            '-Version', $fixture.Version,
            '-RepoRoot', $RepoRoot,
            '-GitSha', $fixture.GitSha,
            '-InstallerPath', $fixture.InstallerPath,
            '-FfmpegSourceBundleManifestPath', $fixture.SourceBundleManifestPath,
            '-OcctSourceBundleManifestPath', $fixture.OcctSourceBundleManifestPath,
            '-SmokeManifestPath', $fixture.SmokeManifestPath,
            '-OutputManifestPath', $fixture.OutputManifestPath,
            '-MinInstallerBytes', '1'
        )

        Assert-True -Condition ($result.ExitCode -ne 0) -Message 'Validator accepted suffix-only DSPy cache paths outside the installed Rook root.'
        Assert-Contains -Text $result.Output -Expected 'rook_dspy_cache.disk_cache_dir' -Message "Validator DSPy cache path error was not specific. Output: $($result.Output)"
    } finally {
        Remove-Item -LiteralPath $fixture.TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-ValidatorRejectsBaseRuntimeChatServicePython {
    $fixture = New-ValidatorFixture

    try {
        $smokeManifest = Get-Content -LiteralPath $fixture.SmokeManifestPath -Raw | ConvertFrom-Json
        $smokeManifest.config_identity.chat_service_python_path = $smokeManifest.private_python_path
        $smokeManifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $fixture.SmokeManifestPath -Encoding UTF8

        $result = Invoke-Validator -Arguments @(
            '-File', $Validator,
            '-Version', $fixture.Version,
            '-RepoRoot', $RepoRoot,
            '-GitSha', $fixture.GitSha,
            '-InstallerPath', $fixture.InstallerPath,
            '-FfmpegSourceBundleManifestPath', $fixture.SourceBundleManifestPath,
            '-OcctSourceBundleManifestPath', $fixture.OcctSourceBundleManifestPath,
            '-SmokeManifestPath', $fixture.SmokeManifestPath,
            '-OutputManifestPath', $fixture.OutputManifestPath,
            '-MinInstallerBytes', '1'
        )

        Assert-True -Condition ($result.ExitCode -ne 0) -Message 'Validator accepted a chat service path pointing at the base private CPython runtime.'
        Assert-Contains -Text $result.Output -Expected 'chat_service_python_path' -Message "Validator chat service Python path error was not specific. Output: $($result.Output)"
    } finally {
        Remove-Item -LiteralPath $fixture.TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-ValidatorRejectsSuffixOnlyImportOrigins {
    $fixture = New-ValidatorFixture

    try {
        $smokeManifest = Get-Content -LiteralPath $fixture.SmokeManifestPath -Raw | ConvertFrom-Json
        $smokeManifest.rook_import_file = 'D:/shadow/Rook/venv/Lib/site-packages/rook/__init__.py'
        $smokeManifest.chirp_import_file = 'D:/shadow/Rook/app/chirp/.venv/Lib/site-packages/chirp/__init__.py'
        $smokeManifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $fixture.SmokeManifestPath -Encoding UTF8

        $result = Invoke-Validator -Arguments @(
            '-File', $Validator,
            '-Version', $fixture.Version,
            '-RepoRoot', $RepoRoot,
            '-GitSha', $fixture.GitSha,
            '-InstallerPath', $fixture.InstallerPath,
            '-FfmpegSourceBundleManifestPath', $fixture.SourceBundleManifestPath,
            '-OcctSourceBundleManifestPath', $fixture.OcctSourceBundleManifestPath,
            '-SmokeManifestPath', $fixture.SmokeManifestPath,
            '-OutputManifestPath', $fixture.OutputManifestPath,
            '-MinInstallerBytes', '1'
        )

        Assert-True -Condition ($result.ExitCode -ne 0) -Message 'Validator accepted import origins from a shadow Rook root.'
        Assert-Contains -Text $result.Output -Expected 'rook_import_file' -Message "Validator import origin error was not specific. Output: $($result.Output)"
    } finally {
        Remove-Item -LiteralPath $fixture.TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-ValidatorRejectsStalePythonRuntimeRookGitSha {
    $fixture = New-ValidatorFixture

    try {
        $pythonRuntimeManifestPath = Join-Path $fixture.TempRoot 'python-runtime-manifest.json'
        $runtimeManifest = Get-Content -LiteralPath $pythonRuntimeManifestPath -Raw | ConvertFrom-Json
        $runtimeManifest.rook_git_sha = '0000000000000000000000000000000000000000'
        $runtimeManifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $pythonRuntimeManifestPath -Encoding UTF8
        $runtimeManifestSha = (Get-FileHash -LiteralPath $pythonRuntimeManifestPath -Algorithm SHA256).Hash.ToUpperInvariant()
        $installStatePath = Join-Path $fixture.TempRoot 'install-state.json'
        $installState = Get-Content -LiteralPath $installStatePath -Raw | ConvertFrom-Json
        $installState.python.identity_hash = $runtimeManifestSha
        $installState.python.runtime_manifest_sha256 = $runtimeManifestSha
        $installState.rook.python_identity_hash = $runtimeManifestSha
        $installState.chirp.python_identity_hash = $runtimeManifestSha
        $installState | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $installStatePath -Encoding UTF8

        $result = Invoke-Validator -Arguments @(
            '-File', $Validator,
            '-Version', $fixture.Version,
            '-RepoRoot', $RepoRoot,
            '-GitSha', $fixture.GitSha,
            '-InstallerPath', $fixture.InstallerPath,
            '-FfmpegSourceBundleManifestPath', $fixture.SourceBundleManifestPath,
            '-OcctSourceBundleManifestPath', $fixture.OcctSourceBundleManifestPath,
            '-SmokeManifestPath', $fixture.SmokeManifestPath,
            '-OutputManifestPath', $fixture.OutputManifestPath,
            '-MinInstallerBytes', '1'
        )

        Assert-True -Condition ($result.ExitCode -ne 0) -Message 'Validator accepted a Python runtime manifest built from a stale Rook git SHA.'
        Assert-Contains -Text $result.Output -Expected 'rook_git_sha' -Message "Validator Rook git SHA error was not specific. Output: $($result.Output)"
    } finally {
        Remove-Item -LiteralPath $fixture.TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-ValidatorRejectsPythonRuntimeReleaseVersionMismatch {
    $fixture = New-ValidatorFixture

    try {
        $pythonRuntimeManifestPath = Join-Path $fixture.TempRoot 'python-runtime-manifest.json'
        $runtimeManifest = Get-Content -LiteralPath $pythonRuntimeManifestPath -Raw | ConvertFrom-Json
        $runtimeManifest.release_version = '0.0.0'
        $runtimeManifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $pythonRuntimeManifestPath -Encoding UTF8
        $runtimeManifestSha = (Get-FileHash -LiteralPath $pythonRuntimeManifestPath -Algorithm SHA256).Hash.ToUpperInvariant()
        $installStatePath = Join-Path $fixture.TempRoot 'install-state.json'
        $installState = Get-Content -LiteralPath $installStatePath -Raw | ConvertFrom-Json
        $installState.python.identity_hash = $runtimeManifestSha
        $installState.python.runtime_manifest_sha256 = $runtimeManifestSha
        $installState.rook.python_identity_hash = $runtimeManifestSha
        $installState.chirp.python_identity_hash = $runtimeManifestSha
        $installState | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $installStatePath -Encoding UTF8

        $result = Invoke-Validator -Arguments @(
            '-File', $Validator,
            '-Version', $fixture.Version,
            '-RepoRoot', $RepoRoot,
            '-GitSha', $fixture.GitSha,
            '-InstallerPath', $fixture.InstallerPath,
            '-FfmpegSourceBundleManifestPath', $fixture.SourceBundleManifestPath,
            '-OcctSourceBundleManifestPath', $fixture.OcctSourceBundleManifestPath,
            '-SmokeManifestPath', $fixture.SmokeManifestPath,
            '-OutputManifestPath', $fixture.OutputManifestPath,
            '-MinInstallerBytes', '1'
        )

        Assert-True -Condition ($result.ExitCode -ne 0) -Message 'Validator accepted a Python runtime manifest built for a different release version.'
        Assert-Contains -Text $result.Output -Expected 'release_version' -Message "Validator release version error was not specific. Output: $($result.Output)"
    } finally {
        Remove-Item -LiteralPath $fixture.TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-ValidatorWithOcctDamage {
    param([string]$Damage)
    $fixture = New-ValidatorFixture
    try {
        if ($Damage -eq 'bundle-bytes') {
            Add-Content -LiteralPath $fixture.OcctBundlePath -Value 'tampered' -Encoding ASCII
        } else {
            $manifest = Get-Content -LiteralPath $fixture.OcctSourceBundleManifestPath -Raw | ConvertFrom-Json
            $manifest.source_commit = '0000000000000000000000000000000000000000'
            $manifest | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $fixture.OcctSourceBundleManifestPath -Encoding UTF8
        }
        return Invoke-Validator -Arguments @(
            '-File', $Validator,
            '-Version', $fixture.Version,
            '-RepoRoot', $RepoRoot,
            '-GitSha', $fixture.GitSha,
            '-InstallerPath', $fixture.InstallerPath,
            '-FfmpegSourceBundleManifestPath', $fixture.SourceBundleManifestPath,
            '-OcctSourceBundleManifestPath', $fixture.OcctSourceBundleManifestPath,
            '-SmokeManifestPath', $fixture.SmokeManifestPath,
            '-OutputManifestPath', $fixture.OutputManifestPath,
            '-MinInstallerBytes', '1'
        )
    } finally {
        Remove-Item -LiteralPath $fixture.TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-ValidatorRejectsChangedOcctSourceBundle {
    $result = Invoke-ValidatorWithOcctDamage -Damage 'bundle-bytes'
    Assert-True -Condition ($result.ExitCode -ne 0) -Message 'Validator must reject an OCCT source bundle whose bytes differ from its manifest.'
    Assert-Contains -Text $result.Output -Expected 'OCCT source bundle checksum mismatch' -Message "OCCT checksum error was not specific. Output: $($result.Output)"
}

function Test-ValidatorRejectsOcctSourceBundleForAnotherCommit {
    $result = Invoke-ValidatorWithOcctDamage -Damage 'commit'
    Assert-True -Condition ($result.ExitCode -ne 0) -Message 'Validator must reject an OCCT source bundle bound to a different commit.'
    Assert-Contains -Text $result.Output -Expected 'does not match the provenance commit' -Message "OCCT commit error was not specific. Output: $($result.Output)"
}

Test-ReleaseValidatorRequiresPythonRuntimeEvidence
Test-ValidatorWritesExactArtifactManifest
Test-ValidatorAcceptsInstallerOlderThanInstallerScriptByDefault
Test-ValidatorRejectsInstallerOlderThanInstallerScriptWhenRequired
Test-DocumentedValidatorCommandDefaultsRepoRoot
Test-ValidatorRejectsGitShaThatDoesNotMatchCheckout
Test-ValidatorRejectsFailedSmokeEvidence
Test-ValidatorRejectsMissingPluginManagerEvidence
Test-ValidatorRejectsMissingChatServiceEvidence
Test-ValidatorRejectsLegacySingleHostSmokeManifest
Test-ValidatorUsesCompanionSelfReportAsAuthoritativePath
Test-ValidatorRejectsIncompleteCompanionSelfReport
Test-ValidatorRejectsStaleCompanionSelfReport
Test-ValidatorRejectsStaleInstallStateHashes
Test-ValidatorRejectsStaleInstallStateLockfilePath
Test-ValidatorRejectsStaleInstallStatePythonPath
Test-ValidatorRejectsStaleInstallStateRuntimePythonIdentity
Test-ValidatorRejectsSuffixOnlyDspyCachePaths
Test-ValidatorRejectsBaseRuntimeChatServicePython
Test-ValidatorRejectsSuffixOnlyImportOrigins
Test-ValidatorRejectsStalePythonRuntimeRookGitSha
Test-ValidatorRejectsPythonRuntimeReleaseVersionMismatch
Test-ValidatorRejectsChangedOcctSourceBundle
Test-ValidatorRejectsOcctSourceBundleForAnotherCommit

Write-Host 'Release artifact validator tests passed.'
