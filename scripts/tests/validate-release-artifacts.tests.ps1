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

    $smokeManifestPath = Join-Path $tempRoot "smoke-$Version.json"
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
        SourceBundleManifestPath = (Join-Path $RepoRoot 'artifacts\ffmpeg\ffmpeg-8.1.1-rook-minimal\rook-ffmpeg-source-bundle-manifest.json')
    }
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
