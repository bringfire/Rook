$ErrorActionPreference = 'Stop'

$TestRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestRoot)
$InstallerScript = Join-Path $RepoRoot 'installer\RookSetup.iss'
$BuildReleaseSkill = Join-Path $RepoRoot '.agents\skills\build-release\SKILL.md'
$IssSourcePaths = Join-Path $RepoRoot '.agents\skills\build-release\references\iss-source-paths.md'
$VersionLocations = Join-Path $RepoRoot '.agents\skills\build-release\references\version-locations.md'
$BuildingDoc = Join-Path $RepoRoot 'BUILDING.md'
$CompanionRuntimeConfig = Join-Path $RepoRoot 'src\Rook\bin\Release\net7.0\Rook.runtimeconfig.json'

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

Test-InstallerPackagesNet7CompanionRuntime
Test-BuiltCompanionRuntimeConfigDeclaresNet7
Test-InstallerRequiresNativePluginBuildOutput
Test-InstallerRegistersRhinoPluginFileNamesUnderPluginSubkey
Test-ReleaseWorkflowDocsUseNet7CompanionOutput
Test-BuildReleaseWorkflowUsesWindowsPowerShellCommands

Write-Host 'Release installer guard tests passed.'
