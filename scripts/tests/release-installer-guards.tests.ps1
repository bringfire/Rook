$ErrorActionPreference = 'Stop'

$TestRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestRoot)
$InstallerScript = Join-Path $RepoRoot 'installer\RookSetup.iss'
$BuildReleaseSkill = Join-Path $RepoRoot '.agents\skills\build-release\SKILL.md'
$IssSourcePaths = Join-Path $RepoRoot '.agents\skills\build-release\references\iss-source-paths.md'
$ClaudeBuildReleaseSkill = Join-Path $RepoRoot '.claude\skills\build-release\SKILL.md'
$ClaudeIssSourcePaths = Join-Path $RepoRoot '.claude\skills\build-release\references\iss-source-paths.md'
$VersionLocations = Join-Path $RepoRoot '.agents\skills\build-release\references\version-locations.md'
$BuildingDoc = Join-Path $RepoRoot 'BUILDING.md'
$CompanionRuntimeConfig = Join-Path $RepoRoot 'src\Rook\bin\Release\net7.0\Rook.runtimeconfig.json'
$FfmpegValidationScript = Join-Path $RepoRoot 'scripts\validate-ffmpeg-bundle.ps1'
$ReleaseWorkflow = Join-Path $RepoRoot '.github\workflows\release.yml'

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Assert-Contains {
    param(
        [string]$Text,
        [string]$Expected,
        [string]$Message
    )

    Assert-True -Condition $Text.Contains($Expected) -Message $Message
}

function Assert-NotContains {
    param(
        [string]$Text,
        [string]$Unexpected,
        [string]$Message
    )

    Assert-True -Condition (-not $Text.Contains($Unexpected)) -Message $Message
}

function Assert-FfmpegInstallerLine {
    param(
        [string]$FileName
    )

    $sourcePrefix = "Source: `"{#FfmpegDir}\$FileName`""
    $matchingLines = @(Get-Content -Path $InstallerScript | Where-Object { $_ -like "$sourcePrefix*" })

    Assert-True -Condition ($matchingLines.Count -eq 1) -Message "Installer must include exactly one bundled FFmpeg source line for $FileName; found $($matchingLines.Count)."

    $line = $matchingLines[0]
    Assert-Contains -Text $line -Expected $sourcePrefix -Message "Installer FFmpeg line must use the bundled source path for $FileName."
    Assert-Contains -Text $line -Expected 'DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\ffmpeg"' -Message "Installer FFmpeg line must install $FileName under the RookNative ffmpeg directory."
    Assert-Contains -Text $line -Expected 'Components: plugins' -Message "Installer FFmpeg line must be gated by the plugins component for $FileName."
    Assert-Contains -Text $line -Expected 'Flags: ignoreversion' -Message "Installer FFmpeg line must use ignoreversion for $FileName."
    Assert-NotContains -Text $line -Unexpected 'skipifsourcedoesntexist' -Message "Release installer must fail packaging when bundled FFmpeg payload file is missing: $FileName."
}

function Test-InstallerPackagesNet7CompanionRuntime {
    $content = Get-Content -Path $InstallerScript -Raw

    Assert-Contains -Text $content -Expected '#define CompanionDir RepoRoot + "\src\Rook\bin\Release\net7.0"' -Message 'Installer must package the net7.0 companion output.'
    Assert-NotContains -Text $content -Unexpected 'net48' -Message 'Installer must not reference net48 companion artifacts.'
    Assert-Contains -Text $content -Expected '{#CompanionDir}\Rook.rhp' -Message 'Installer must package Rook.rhp from the companion output.'
    Assert-Contains -Text $content -Expected '{#CompanionDir}\Rook.deps.json' -Message 'Installer must package Rook.deps.json for the net7.0 companion.'
    Assert-Contains -Text $content -Expected '{#CompanionDir}\Rook.runtimeconfig.json' -Message 'Installer must package Rook.runtimeconfig.json for the net7.0 companion.'
    Assert-Contains -Text $content -Expected '{#CompanionDir}\runtimes\*' -Message 'Installer must package companion runtime assets.'
}

function Test-BuiltCompanionRuntimeConfigDeclaresNet7 {
    Assert-True -Condition (Test-Path $CompanionRuntimeConfig) -Message "Built companion runtimeconfig is missing: $CompanionRuntimeConfig"

    try {
        $runtimeConfig = Get-Content -Path $CompanionRuntimeConfig -Raw | ConvertFrom-Json
    } catch {
        throw "Built companion runtimeconfig is malformed JSON: $CompanionRuntimeConfig"
    }

    $tfm = $runtimeConfig.runtimeOptions.tfm
    Assert-True -Condition ($tfm -eq 'net7.0') -Message "Built companion runtimeconfig must declare runtimeOptions.tfm == net7.0; actual value: $tfm"
}

function Test-InstallerPackagesBundledFfmpegPayload {
    $content = Get-Content -Path $InstallerScript -Raw

    Assert-Contains -Text $content -Expected '#define FfmpegDir   RepoRoot + "\third_party\ffmpeg"' -Message 'Installer must define the bundled FFmpeg payload directory.'
    foreach ($fileName in @(
        'ffmpeg.exe',
        'ffmpeg-provenance.json',
        'ffmpeg-dependencies.json',
        'LICENSE.FFmpeg.txt',
        'NOTICE.FFmpeg.txt',
        'SOURCE.FFmpeg.txt',
        'DEPENDENCIES.FFmpeg.txt',
        'README.md'
    )) {
        Assert-FfmpegInstallerLine -FileName $fileName
    }
}

function Test-FfmpegBundleValidationPasses {
    Assert-True -Condition (Test-Path $FfmpegValidationScript) -Message "FFmpeg validation script is missing: $FfmpegValidationScript"
    & powershell -NoProfile -ExecutionPolicy Bypass -File $FfmpegValidationScript
    if ($LASTEXITCODE -ne 0) {
        throw "FFmpeg bundle validation failed with exit code $LASTEXITCODE"
    }
}

function Test-InstallerRequiresNativePluginBuildOutput {
    $nativeLine = (Get-Content -Path $InstallerScript | Where-Object { $_ -like 'Source: "{#NativePlugin}"*' }) -join "`n"

    Assert-Contains -Text $nativeLine -Expected 'Source: "{#NativePlugin}"' -Message 'Installer must include the native plugin source line.'
    Assert-NotContains -Text $nativeLine -Unexpected 'skipifsourcedoesntexist' -Message 'Release installer must fail packaging when RookNative.rhp is missing.'
}

function Test-InstallerRegistersRhinoPluginFileNamesUnderPluginSubkey {
    $content = Get-Content -Path $InstallerScript -Raw

    Assert-Contains -Text $content -Expected 'Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906\PlugIn"; ValueType: string; ValueName: "FileName"' -Message 'Native plugin FileName must be written under the Rhino PlugIn subkey.'
    Assert-Contains -Text $content -Expected 'Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B\PlugIn"; ValueType: string; ValueName: "FileName"' -Message 'Companion FileName must be written under the Rhino PlugIn subkey.'

    $fileNameLines = Get-Content -Path $InstallerScript | Where-Object { $_ -like 'Root: HKCU; Subkey:*ValueName: "FileName"*' }
    foreach ($line in $fileNameLines) {
        Assert-Contains -Text $line -Expected '\PlugIn";' -Message "Installer registry FileName line is not under the PlugIn subkey: $line"
    }
}

function Test-ReleaseWorkflowDocsUseNet7CompanionOutput {
    $combined = @(
        Get-Content -Path $BuildReleaseSkill -Raw
        Get-Content -Path $IssSourcePaths -Raw
        Get-Content -Path $ClaudeBuildReleaseSkill -Raw
        Get-Content -Path $ClaudeIssSourcePaths -Raw
        Get-Content -Path $VersionLocations -Raw
        Get-Content -Path $BuildingDoc -Raw
    ) -join "`n"

    $forbidden = @(
        '-p:TargetFramework=net48',
        'TargetFramework=net48',
        'src\Rook\bin\x64\Release\net48',
        'src/Rook/bin/x64/Release/net48',
        'src\Rook\bin\Release\net48',
        'src/Rook/bin/Release/net48'
    )

    foreach ($pattern in $forbidden) {
        Assert-NotContains -Text $combined -Unexpected $pattern -Message "Release workflow docs still reference unsupported net48 companion release path or build flag: $pattern"
    }

    Assert-Contains -Text $combined -Expected 'dotnet build src\Rook\Rook.csproj -f net7.0 -c Release' -Message 'Release workflow docs must use the canonical net7.0 companion build command.'
    Assert-Contains -Text $combined -Expected 'src\Rook\bin\Release\net7.0\Rook.rhp' -Message 'Release workflow docs must reference the net7.0 companion output.'
    Assert-Contains -Text $combined -Expected 'src\Rook\bin\Release\net7.0\Rook.runtimeconfig.json' -Message 'Release workflow docs must mention the net7.0 runtimeconfig output.'
}

function Test-BuildReleaseWorkflowUsesWindowsPowerShellCommands {
    $combined = @(
        Get-Content -Path $BuildReleaseSkill -Raw
        Get-Content -Path $IssSourcePaths -Raw
        Get-Content -Path $ClaudeBuildReleaseSkill -Raw
        Get-Content -Path $ClaudeIssSourcePaths -Raw
        Get-Content -Path $VersionLocations -Raw
        Get-Content -Path $BuildingDoc -Raw
    ) -join "`n"

    $forbidden = @(
        'grep -',
        'ls -la',
        'cat > /tmp',
        '/tmp/rook_build.bat',
        'rm -f',
        'wc -l'
    )

    foreach ($pattern in $forbidden) {
        Assert-NotContains -Text $combined -Unexpected $pattern -Message "Release workflow docs still contain bash-only command text: $pattern"
    }

    Assert-Contains -Text $combined -Expected 'Test-Path' -Message 'Release workflow docs must use PowerShell path checks.'
    Assert-Contains -Text $combined -Expected 'Select-String' -Message 'Release workflow docs must use PowerShell text checks.'
    Assert-Contains -Text $combined -Expected '$env:TEMP' -Message 'Release workflow docs must create temporary build scripts using Windows temp paths.'
}

function Test-BuildReleaseDocsRequireFfmpegValidation {
    $combined = @(
        Get-Content -Path $BuildReleaseSkill -Raw
        Get-Content -Path $IssSourcePaths -Raw
        Get-Content -Path $ClaudeBuildReleaseSkill -Raw
        Get-Content -Path $ClaudeIssSourcePaths -Raw
        Get-Content -Path $BuildingDoc -Raw
    ) -join "`n"

    Assert-Contains -Text $combined -Expected 'scripts\validate-ffmpeg-bundle.ps1' -Message 'Release docs must require the FFmpeg bundle validation guard.'
    Assert-Contains -Text $combined -Expected 'third_party\ffmpeg\ffmpeg-dependencies.json' -Message 'Release docs must include the FFmpeg dependency manifest in path checks.'
    Assert-Contains -Text $combined -Expected 'third_party\ffmpeg\README.md' -Message 'Release docs must include the installed FFmpeg README in path checks.'
}

function Test-LegacyGitHubReleaseWorkflowIsDisabled {
    Assert-True -Condition (Test-Path $ReleaseWorkflow) -Message "Release workflow file is missing: $ReleaseWorkflow"
    $content = Get-Content -Path $ReleaseWorkflow -Raw

    Assert-Contains -Text $content -Expected 'Legacy Build and Release Disabled' -Message 'Legacy GitHub release workflow must be explicitly disabled.'
    Assert-Contains -Text $content -Expected 'scripts\validate-ffmpeg-bundle.ps1' -Message 'Disabled workflow must point release owners at the FFmpeg-validating release path.'
    Assert-Contains -Text $content -Expected 'throw "This ZIP-based release workflow is retired.' -Message 'Legacy GitHub release workflow must fail before producing artifacts.'
    Assert-NotContains -Text $content -Unexpected 'softprops/action-gh-release' -Message 'Legacy GitHub release workflow must not create releases.'
    Assert-NotContains -Text $content -Unexpected 'actions/upload-artifact' -Message 'Legacy GitHub release workflow must not upload bypass artifacts.'
    Assert-NotContains -Text $content -Unexpected 'Compress-Archive' -Message 'Legacy GitHub release workflow must not package the old ZIP release.'
}

Test-InstallerPackagesNet7CompanionRuntime
Test-BuiltCompanionRuntimeConfigDeclaresNet7
Test-InstallerPackagesBundledFfmpegPayload
Test-FfmpegBundleValidationPasses
Test-InstallerRequiresNativePluginBuildOutput
Test-InstallerRegistersRhinoPluginFileNamesUnderPluginSubkey
Test-ReleaseWorkflowDocsUseNet7CompanionOutput
Test-BuildReleaseWorkflowUsesWindowsPowerShellCommands
Test-BuildReleaseDocsRequireFfmpegValidation
Test-LegacyGitHubReleaseWorkflowIsDisabled

Write-Host 'Release installer guard tests passed.'
