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

    $smokeManifestPath = Join-Path $tempRoot "smoke-$Version.json"
    $pythonRuntimeManifestPath = Join-Path $tempRoot 'python-runtime-manifest.json'
    $installStatePath = Join-Path $tempRoot 'install-state.json'
    $privatePythonPath = 'C:/Users/test/AppData/Local/Rook/python/cpython-3.11.9/python.exe'
    $rookVenvPath = 'C:/Users/test/AppData/Local/Rook/venv'
    $chirpVenvPath = 'C:/Users/test/AppData/Local/Rook/app/chirp/.venv'
    $rookImportFile = 'C:/Users/test/AppData/Local/Rook/venv/Lib/site-packages/rook/__init__.py'
    $chirpImportFile = 'C:/Users/test/AppData/Local/Rook/app/chirp/.venv/Lib/site-packages/chirp/__init__.py'
    $chirpSourceArchiveSha = '1111111111111111111111111111111111111111111111111111111111111111'

    [ordered]@{
        schema_version = 1
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
                    license = 'Proprietary'
                }
            )
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

    [ordered]@{
        schema_version = 1
        python = [ordered]@{
            path = $privatePythonPath
            version = '3.11.9'
        }
        rook = [ordered]@{
            venv_path = $rookVenvPath
        }
        chirp = [ordered]@{
            venv_path = $chirpVenvPath
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
            license_provenance = [ordered]@{
                manifest_path = $pythonRuntimeManifestPath
            }
            config_identity = [ordered]@{
                chat_service_python_path = $privatePythonPath
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
    Assert-Contains -Text $validator -Expected 'license_provenance' -Message 'Release validator must require runtime and wheel license/provenance evidence.'
    Assert-Contains -Text $validator -Expected 'security_mitigations' -Message 'Release validator must require runtime security mitigation evidence.'
    Assert-Contains -Text $validator -Expected 'diskcache_cve_2025_69872' -Message 'Release validator must require the DiskCache CVE mitigation evidence.'
    Assert-Contains -Text $validator -Expected 'restrict_pickle' -Message 'Release validator must require DSPy restricted pickle evidence.'
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
        Assert-Contains -Text $manifestText -Expected '"rook_bim"' -Message 'Release manifest must contain RookBIM artifact identity.'
        Assert-Contains -Text $manifestText -Expected '"runtime":  "net48"' -Message 'Release manifest must identify RookBIM as a net48 artifact.'
        Assert-Contains -Text $manifestText -Expected '"assembly_version"' -Message 'Release manifest must record RookBIM assembly version.'
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

Test-ReleaseValidatorRequiresPythonRuntimeEvidence
Test-ValidatorWritesExactArtifactManifest
Test-DocumentedValidatorCommandDefaultsRepoRoot
Test-ValidatorRejectsGitShaThatDoesNotMatchCheckout
Test-ValidatorRejectsFailedSmokeEvidence
Test-ValidatorRejectsMissingPluginManagerEvidence
Test-ValidatorRejectsMissingChatServiceEvidence
Test-ValidatorRejectsLegacySingleHostSmokeManifest
Test-ValidatorUsesCompanionSelfReportAsAuthoritativePath
Test-ValidatorRejectsIncompleteCompanionSelfReport
Test-ValidatorRejectsStaleCompanionSelfReport

Write-Host 'Release artifact validator tests passed.'
