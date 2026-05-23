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

function Invoke-Validator {
    param([string[]]$Arguments)

    $output = @(& powershell -NoProfile -ExecutionPolicy Bypass @Arguments 2>&1 | ForEach-Object { $_.ToString() })
    return [pscustomobject]@{
        ExitCode = $LASTEXITCODE
        Output = ($output -join "`n")
    }
}

function Test-ValidatorWritesExactArtifactManifest {
    Assert-True -Condition (Test-Path $Validator) -Message "Validator script is missing: $Validator"

    $version = '1.5.6'
    $gitSha = ((& git -C $RepoRoot rev-parse HEAD) -join '').Trim()
    Assert-True -Condition ($LASTEXITCODE -eq 0 -and $gitSha) -Message 'Could not resolve git SHA for validator test.'

    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("rook-release-artifact-test-" + [System.Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null

    try {
        $installerPath = Join-Path $tempRoot "Rook-Setup-$version.exe"
        Set-Content -LiteralPath $installerPath -Value 'fake installer bytes' -Encoding ASCII
        $installerSha = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash

        $smokeManifestPath = Join-Path $tempRoot "smoke-$version.json"
        [ordered]@{
            git_sha = $gitSha
            installer_sha256 = $installerSha
            rhino_version = '8.test'
            revit_version = '2025.test'
            rhino_inside_version = 'test'
            rook_version = $version
            native_port = 9876
            ping_result = 'pong'
            loaded_native_path = 'C:/Users/test/AppData/Roaming/McNeel/Rhinoceros/8.0/Plug-ins/RookNative/RookNative.rhp'
            loaded_companion_path = 'C:/Users/test/AppData/Roaming/McNeel/Rhinoceros/8.0/Plug-ins/RookNative/net7.0/Rook.rhp'
        } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $smokeManifestPath -Encoding UTF8

        $outputManifestPath = Join-Path $tempRoot "release-manifest-$version.json"
        $sourceBundleManifestPath = Join-Path $RepoRoot 'artifacts\ffmpeg\ffmpeg-8.1.1-rook-minimal\rook-ffmpeg-source-bundle-manifest.json'

        $result = Invoke-Validator -Arguments @(
            '-File', $Validator,
            '-Version', $version,
            '-RepoRoot', $RepoRoot,
            '-GitSha', $gitSha,
            '-InstallerPath', $installerPath,
            '-FfmpegSourceBundleManifestPath', $sourceBundleManifestPath,
            '-SmokeManifestPath', $smokeManifestPath,
            '-OutputManifestPath', $outputManifestPath,
            '-MinInstallerBytes', '1'
        )

        Assert-True -Condition ($result.ExitCode -eq 0) -Message "Validator failed unexpectedly. Output: $($result.Output)"
        Assert-True -Condition (Test-Path $outputManifestPath) -Message 'Validator did not write the release manifest.'

        $manifestText = Get-Content -LiteralPath $outputManifestPath -Raw
        Assert-Contains -Text $manifestText -Expected '"git_sha"' -Message 'Release manifest must contain git_sha.'
        Assert-Contains -Text $manifestText -Expected '"installer_sha256"' -Message 'Release manifest must contain installer_sha256.'
        Assert-Contains -Text $manifestText -Expected '"ffmpeg_source_bundle_sha256"' -Message 'Release manifest must contain ffmpeg_source_bundle_sha256.'
    } finally {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Test-ValidatorWritesExactArtifactManifest

Write-Host 'Release artifact validator tests passed.'
