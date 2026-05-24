$ErrorActionPreference = 'Stop'

$TestRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestRoot)
$InstallerScript = Join-Path $RepoRoot 'installer\RookSetup.iss'
$BuildReleaseSkill = Join-Path $RepoRoot '.agents\skills\build-release\SKILL.md'
$IssSourcePaths = Join-Path $RepoRoot '.agents\skills\build-release\references\iss-source-paths.md'
$ClaudeBuildReleaseSkill = Join-Path $RepoRoot '.claude\skills\build-release\SKILL.md'
$ClaudeIssSourcePaths = Join-Path $RepoRoot '.claude\skills\build-release\references\iss-source-paths.md'
$VersionLocations = Join-Path $RepoRoot '.agents\skills\build-release\references\version-locations.md'
$ClaudeVersionLocations = Join-Path $RepoRoot '.claude\skills\build-release\references\version-locations.md'
$BuildingDoc = Join-Path $RepoRoot 'BUILDING.md'
$PostInstallScript = Join-Path $RepoRoot 'installer\post_install.py'
$DoctorScript = Join-Path $RepoRoot 'mcp_server\src\rook\doctor.py'
$BuildNativeScript = Join-Path $RepoRoot 'build_native.ps1'
$ReleaseArtifactValidator = Join-Path $RepoRoot 'scripts\validate-release-artifacts.ps1'
$CompanionNet8RuntimeConfig = Join-Path $RepoRoot 'src\Rook\bin\Release\net8.0\Rook.runtimeconfig.json'
$CompanionNet7RuntimeConfig = Join-Path $RepoRoot 'src\Rook\bin\Release\net7.0\Rook.runtimeconfig.json'
$CompanionNet8Rhp = Join-Path $RepoRoot 'src\Rook\bin\Release\net8.0\Rook.rhp'
$CompanionNet7Rhp = Join-Path $RepoRoot 'src\Rook\bin\Release\net7.0\Rook.rhp'
$CompanionNet48Rhp = Join-Path $RepoRoot 'src\Rook\bin\Release\net48\Rook.rhp'
$CompanionNet48WebView2Core = Join-Path $RepoRoot 'src\Rook\bin\Release\net48\Microsoft.Web.WebView2.Core.dll'
$CompanionNet48WebView2Loader = Join-Path $RepoRoot 'src\Rook\bin\Release\net48\runtimes\win-x64\native\WebView2Loader.dll'
$FfmpegValidationScript = Join-Path $RepoRoot 'scripts\validate-ffmpeg-bundle.ps1'
$FfmpegBuildScript = Join-Path $RepoRoot 'scripts\ffmpeg\build-rook-ffmpeg.ps1'
$FfmpegConfigureRecipe = Join-Path $RepoRoot 'scripts\ffmpeg\rook-ffmpeg-configure.txt'
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

function Test-InstallerPackagesMultiRuntimeCompanionPayloads {
    $content = Get-Content -Path $InstallerScript -Raw

    Assert-Contains -Text $content -Expected '#define CompanionNet8Dir RepoRoot + "\src\Rook\bin\Release\net8.0"' -Message 'Installer must define the net8.0 companion output for Rhino.Inside/Revit .NET 8 hosts.'
    Assert-Contains -Text $content -Expected '#define CompanionNet7Dir RepoRoot + "\src\Rook\bin\Release\net7.0"' -Message 'Installer must define the net7.0 companion output.'
    Assert-Contains -Text $content -Expected '#define CompanionNet48Dir RepoRoot + "\src\Rook\bin\Release\net48"' -Message 'Installer must define the net48 companion output for Rhino.Inside/Revit .NET Framework hosts.'

    foreach ($runtime in @('net8.0', 'net7.0', 'net48')) {
        Assert-Contains -Text $content -Expected "DestDir: `"{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\$runtime`"" -Message "Installer must deploy the companion into the $runtime runtime subfolder."
        Assert-Contains -Text $content -Expected "RookNative\$runtime\Rook.rhp" -Message "Installer must reference the $runtime Rook.rhp payload."
    }

    Assert-Contains -Text $content -Expected '{#CompanionNet8Dir}\Rook.deps.json' -Message 'Installer must package Rook.deps.json for the net8.0 companion.'
    Assert-Contains -Text $content -Expected '{#CompanionNet8Dir}\Rook.runtimeconfig.json' -Message 'Installer must package Rook.runtimeconfig.json for the net8.0 companion.'
    Assert-Contains -Text $content -Expected '{#CompanionNet8Dir}\runtimes\*' -Message 'Installer must package net8.0 companion runtime assets.'
    Assert-Contains -Text $content -Expected '{#CompanionNet7Dir}\Rook.deps.json' -Message 'Installer must package Rook.deps.json for the net7.0 companion.'
    Assert-Contains -Text $content -Expected '{#CompanionNet7Dir}\Rook.runtimeconfig.json' -Message 'Installer must package Rook.runtimeconfig.json for the net7.0 companion.'
    Assert-Contains -Text $content -Expected '{#CompanionNet7Dir}\runtimes\*' -Message 'Installer must package net7.0 companion runtime assets.'
    Assert-Contains -Text $content -Expected '{#CompanionNet48Dir}\Rook.rhp' -Message 'Installer must package the net48 companion RHP.'
    Assert-Contains -Text $content -Expected '{#CompanionNet48Dir}\*.dll' -Message 'Installer must package net48 companion dependency DLLs.'
    Assert-Contains -Text $content -Expected '{#CompanionNet48Dir}\runtimes\*' -Message 'Installer must package net48 companion runtime assets.'
}

function Assert-RuntimeConfigDeclaresTfm {
    param(
        [string]$RuntimeConfigPath,
        [string]$ExpectedTfm
    )

    Assert-True -Condition (Test-Path $RuntimeConfigPath) -Message "Built companion runtimeconfig is missing: $RuntimeConfigPath"

    try {
        $runtimeConfig = Get-Content -Path $RuntimeConfigPath -Raw | ConvertFrom-Json
    } catch {
        throw "Built companion runtimeconfig is malformed JSON: $RuntimeConfigPath"
    }

    $tfm = $runtimeConfig.runtimeOptions.tfm
    Assert-True -Condition ($tfm -eq $ExpectedTfm) -Message "Built companion runtimeconfig must declare runtimeOptions.tfm == $ExpectedTfm; actual value: $tfm"
}

function Test-BuiltCompanionPayloadsExist {
    Assert-True -Condition (Test-Path $CompanionNet8Rhp) -Message "Built net8.0 companion payload is missing: $CompanionNet8Rhp"
    Assert-True -Condition (Test-Path $CompanionNet7Rhp) -Message "Built net7.0 registered-anchor companion payload is missing: $CompanionNet7Rhp"
    Assert-True -Condition (Test-Path $CompanionNet48Rhp) -Message "Built net48 companion payload is missing: $CompanionNet48Rhp"
    Assert-True -Condition (Test-Path $CompanionNet48WebView2Core) -Message "Built net48 WebView2 wrapper is missing: $CompanionNet48WebView2Core"
    Assert-True -Condition (Test-Path $CompanionNet48WebView2Loader) -Message "Built net48 WebView2 loader is missing: $CompanionNet48WebView2Loader"
    Assert-RuntimeConfigDeclaresTfm -RuntimeConfigPath $CompanionNet8RuntimeConfig -ExpectedTfm 'net8.0'
    Assert-RuntimeConfigDeclaresTfm -RuntimeConfigPath $CompanionNet7RuntimeConfig -ExpectedTfm 'net7.0'
}

function Test-InstallerPackagesBundledFfmpegPayload {
    $content = Get-Content -Path $InstallerScript -Raw

    Assert-Contains -Text $content -Expected '#define FfmpegDir   RepoRoot + "\third_party\ffmpeg"' -Message 'Installer must define the bundled FFmpeg payload directory.'
    foreach ($fileName in @(
        'ffmpeg.exe',
        'ffmpeg-provenance.json',
        'LICENSE.FFmpeg.txt',
        'NOTICE.FFmpeg.txt',
        'SOURCE.FFmpeg.txt',
        'README.md'
    )) {
        Assert-FfmpegInstallerLine -FileName $fileName
    }
}

function Test-FfmpegValidatorRequiresReleaseSourceBundleArgument {
    Assert-True -Condition (Test-Path $FfmpegValidationScript) -Message "FFmpeg validation script is missing: $FfmpegValidationScript"

    $script = Get-Content -Path $FfmpegValidationScript -Raw
    Assert-Contains -Text $script -Expected 'SourceBundleManifestPath' -Message 'FFmpeg validator must require a release source-bundle manifest path.'
    Assert-Contains -Text $script -Expected 'Assert-SourceBundleManifest' -Message 'FFmpeg validator must verify the staged release source bundle.'
}

function Test-FfmpegBuildScriptUsesAgentlessSignatureVerification {
    Assert-True -Condition (Test-Path $FfmpegBuildScript) -Message "FFmpeg build script is missing: $FfmpegBuildScript"

    $script = Get-Content -Path $FfmpegBuildScript -Raw
    Assert-Contains -Text $script -Expected 'gpg --batch --import-options show-only --import --with-colons' -Message 'FFmpeg build script must inspect the signing key fingerprint without importing it into a user keyring.'
    Assert-Contains -Text $script -Expected 'gpgv --keyring' -Message 'FFmpeg build script must verify the source signature through gpgv and an explicit trusted keyring.'
    Assert-NotContains -Text $script -Unexpected '--homedir' -Message 'FFmpeg build script must not depend on a private GPG homedir or gpg-agent startup.'
}

function Test-FfmpegBuildRecipeTargetsOnlyFfmpegProgram {
    Assert-True -Condition (Test-Path $FfmpegBuildScript) -Message "FFmpeg build script is missing: $FfmpegBuildScript"
    Assert-True -Condition (Test-Path $FfmpegConfigureRecipe) -Message "FFmpeg configure recipe is missing: $FfmpegConfigureRecipe"

    $script = Get-Content -Path $FfmpegBuildScript -Raw
    $configureRecipe = Get-Content -Path $FfmpegConfigureRecipe -Raw
    Assert-Contains -Text $configureRecipe -Expected '--disable-programs' -Message 'FFmpeg configure recipe must disable default programs before re-enabling ffmpeg.'
    Assert-Contains -Text $configureRecipe -Expected '--enable-ffmpeg' -Message 'FFmpeg configure recipe must explicitly re-enable the ffmpeg executable.'
    Assert-Contains -Text $script -Expected 'make -j`$(nproc) ffmpeg.exe' -Message 'FFmpeg build script must build the ffmpeg.exe target specifically.'
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

function Test-InstallerWritesRhinoPluginEnumerationMetadata {
    $content = Get-Content -Path $InstallerScript -Raw

    foreach ($guid in @(
        'A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906',
        'B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B'
    )) {
        Assert-Contains -Text $content -Expected "Plug-Ins\$guid`"; ValueType: string; ValueName: `"EnglishName`"" -Message "Installer must pre-populate EnglishName so Rhino can enumerate plugin $guid before first load."
        Assert-Contains -Text $content -Expected "Plug-Ins\$guid`"; ValueType: string; ValueName: `"Organization`"" -Message "Installer must pre-populate Organization so Rhino can enumerate plugin $guid before first load."
        Assert-Contains -Text $content -Expected "Plug-Ins\$guid`"; ValueType: string; ValueName: `"Description`"" -Message "Installer must pre-populate Description so Rhino can enumerate plugin $guid before first load."
        Assert-Contains -Text $content -Expected "Plug-Ins\$guid`"; ValueType: string; ValueName: `"RegPath`"" -Message "Installer must pre-populate RegPath so Rhino can enumerate plugin $guid before first load."
        Assert-Contains -Text $content -Expected "Plug-Ins\$guid`"; ValueType: dword; ValueName: `"AddToHelpMenu`"; ValueData: `"0`"" -Message "Installer must pre-populate AddToHelpMenu for plugin $guid."
        Assert-Contains -Text $content -Expected "Plug-Ins\$guid`"; ValueType: dword; ValueName: `"DirectoryInstall`"; ValueData: `"0`"" -Message "Installer must pre-populate DirectoryInstall for plugin $guid."
    }

    Assert-Contains -Text $content -Expected 'Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906\CommandList"; ValueType: string; ValueName: "AIGumball"; ValueData: "2;AIGumball"' -Message 'Installer must pre-populate the native command list entry that Rhino records after a successful load.'
    foreach ($command in @(
        'RestartRookChatService',
        'ShowRookChat',
        'ShowRookKnowledgeGraph',
        'ShowRookVision',
        'UVBoxMapping'
    )) {
        Assert-Contains -Text $content -Expected "Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B\CommandList`"; ValueType: string; ValueName: `"$command`"; ValueData: `"2;$command`"" -Message "Installer must pre-populate companion command list entry $command."
    }

    Assert-Contains -Text $content -Expected 'ValueName: "RuiFile"; ValueData: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net7.0\Rook.rui"' -Message 'Installer must pre-populate the companion RuiFile metadata for Rhino plugin enumeration.'
    Assert-Contains -Text $content -Expected 'RequiredStringValues: TArrayOfString;' -Message 'Installer post-install verification must check required plugin metadata, not only sparse load fields.'
    Assert-Contains -Text $content -Expected 'RequiredCommandValues: TArrayOfString;' -Message 'Installer post-install verification must check required command-list entries.'
}

function Test-InstallerBlocksWhenRhinoOrRevitAreRunning {
    $content = Get-Content -Path $InstallerScript -Raw

    Assert-Contains -Text $content -Expected 'function IsProcessRunning(const ImageName: String): Boolean;' -Message 'Installer must define a process-running check.'
    Assert-Contains -Text $content -Expected 'function IsRhinoHostRunning(): Boolean;' -Message 'Installer must define a Rhino/Revit host-running check.'
    Assert-Contains -Text $content -Expected "IsProcessRunning('Rhino.exe')" -Message 'Installer must block when Rhino.exe is running.'
    Assert-Contains -Text $content -Expected "IsProcessRunning('Rhinoceros.exe')" -Message 'Installer must block when Rhinoceros.exe is running.'
    Assert-Contains -Text $content -Expected "IsProcessRunning('Revit.exe')" -Message 'Installer must block when Revit.exe is running.'
    Assert-Contains -Text $content -Expected 'Close Rhino, Rhino.Inside.Revit, and Revit before installing Rook.' -Message 'Installer must tell users to close Rhino/Revit before install.'
    Assert-Contains -Text $content -Expected 'Result := False;' -Message 'Installer must abort setup when host applications are running.'
}

function Test-InstallerWarnsRegistrationIsPerWindowsUser {
    $installerContent = Get-Content -Path $InstallerScript -Raw
    $readmeContent = Get-Content -Path (Join-Path $RepoRoot 'installer\pre-install-readme.txt') -Raw

    Assert-Contains -Text $installerContent -Expected 'Rook installs Rhino plug-ins for the current Windows user only.' -Message 'Installer must warn that Rhino registration is per-user.'
    Assert-Contains -Text $installerContent -Expected 'If an administrator installs Rook for someone else, Rhino will not see the plug-ins in that user profile.' -Message 'Installer must warn against admin-for-another-user installs.'
    Assert-Contains -Text $readmeContent -Expected 'Run this installer as the same Windows user who runs Rhino/Revit.' -Message 'Pre-install readme must warn about per-user Rhino registration.'
}

function Test-InstallerVerifiesRhinoPluginRegistrationAfterInstall {
    $content = Get-Content -Path $InstallerScript -Raw

    Assert-Contains -Text $content -Expected 'function VerifyPluginRegistration(const Guid, FileName: String; IsDotNet: Cardinal; LoadMode: Cardinal): Boolean;' -Message 'Installer must define registry verification for Rhino plugins.'
    Assert-Contains -Text $content -Expected 'procedure VerifyRhinoPluginInstall();' -Message 'Installer must run post-install Rhino plugin verification.'
    Assert-Contains -Text $content -Expected 'VerifyPluginRegistration(''A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906''' -Message 'Installer must verify native Rhino registry registration.'
    Assert-Contains -Text $content -Expected 'VerifyPluginRegistration(''B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B''' -Message 'Installer must verify companion Rhino registry registration.'
    Assert-Contains -Text $content -Expected 'RookNative\net7.0\Rook.rhp' -Message 'Installer must register the current direct-registry runtime child RHP anchor.'
    Assert-Contains -Text $content -Expected 'Rook copied the plug-in files, but Rhino registration verification failed.' -Message 'Installer must surface a clear post-install registration failure.'
    Assert-Contains -Text $content -Expected 'Restart Rhino after installation.' -Message 'Installer must remind users to restart Rhino after installer-time registry writes.'
}

function Test-UninstallRemovesGeneratedRuntimeArtifacts {
    $installerContent = Get-Content -Path $InstallerScript -Raw
    $postInstallContent = Get-Content -Path $PostInstallScript -Raw

    foreach ($path in @(
        '{localappdata}\Rook\app',
        '{localappdata}\Rook\venv',
        '{localappdata}\Rook\data',
        '{localappdata}\Rook\logs',
        '{localappdata}\Rook\discovery',
        '{userappdata}\Rook',
        '{localappdata}\Temp\rook'
    )) {
        Assert-Contains -Text $installerContent -Expected "Type: filesandordirs; Name: `"$path`"" -Message "Uninstall must remove generated Rook artifact path: $path"
    }

    Assert-Contains -Text $postInstallContent -Expected 'Path(tempfile.gettempdir()) / "rook"' -Message 'Uninstall cleanup must remove the actual user temp Rook diagnostics directory.'
    Assert-Contains -Text $postInstallContent -Expected 'runtime_root / "venv"' -Message 'Uninstall cleanup must remove the managed Python venv created by post_install.py.'
    Assert-Contains -Text $postInstallContent -Expected 'runtime_root / "data"' -Message 'Uninstall cleanup must remove runtime data for a fresh reinstall surface.'
    Assert-Contains -Text $postInstallContent -Expected 'runtime_root / "discovery"' -Message 'Uninstall cleanup must remove shared Rook discovery metadata for a fresh reinstall surface.'
    Assert-Contains -Text $postInstallContent -Expected 'roaming_root' -Message 'Uninstall cleanup must remove user-level Rook roaming state.'
}

function Test-PostInstallValidationUsesMultiRuntimeCompanionLayout {
    $postInstall = Get-Content -Path $PostInstallScript -Raw
    $doctor = Get-Content -Path $DoctorScript -Raw
    $combined = @($postInstall, $doctor) -join "`n"

    Assert-Contains -Text $combined -Expected 'MANAGED_COMPANION_RUNTIMES = ("net8.0", "net7.0", "net48")' -Message 'Post-install validation must know the managed companion runtime folders.'
    Assert-Contains -Text $combined -Expected 'plugin_dir / runtime / "Rook.rhp"' -Message 'Post-install validation must check runtime-child companion RHP payloads.'
    Assert-Contains -Text $combined -Expected 'Rook.rhp {runtime} deployed' -Message 'Post-install validation must label runtime-child companion checks.'
    Assert-Contains -Text $postInstall -Expected '"--skip-handshake"' -Message 'Post-install validation must not fail installation on MCP handshake performance thresholds.'
    Assert-NotContains -Text $combined -Unexpected 'plugin_dir / "Rook.rhp"' -Message 'Post-install validation must not require a root-level Rook.rhp companion payload.'
}

function Test-ReleaseWorkflowDocsUseMultiRuntimeCompanionOutputs {
    $combined = @(
        Get-Content -Path $BuildReleaseSkill -Raw
        Get-Content -Path $IssSourcePaths -Raw
        Get-Content -Path $ClaudeBuildReleaseSkill -Raw
        Get-Content -Path $ClaudeIssSourcePaths -Raw
        Get-Content -Path $BuildingDoc -Raw
        Get-Content -Path $VersionLocations -Raw
    ) -join "`n"

    Assert-Contains -Text $combined -Expected 'dotnet build src\Rook\Rook.csproj -c Release' -Message 'Release workflow docs must build all companion target frameworks.'
    Assert-Contains -Text $combined -Expected 'src\Rook\bin\Release\net8.0\Rook.rhp' -Message 'Release workflow docs must reference the net8.0 companion output.'
    Assert-Contains -Text $combined -Expected 'src\Rook\bin\Release\net8.0\Rook.runtimeconfig.json' -Message 'Release workflow docs must mention the net8.0 runtimeconfig output.'
    Assert-Contains -Text $combined -Expected 'src\Rook\bin\Release\net7.0\Rook.rhp' -Message 'Release workflow docs must reference the net7.0 companion output.'
    Assert-Contains -Text $combined -Expected 'src\Rook\bin\Release\net7.0\Rook.runtimeconfig.json' -Message 'Release workflow docs must mention the net7.0 runtimeconfig output.'
    Assert-Contains -Text $combined -Expected 'src\Rook\bin\Release\net48\Rook.rhp' -Message 'Release workflow docs must reference the net48 companion output.'
    Assert-Contains -Text $combined -Expected 'src\Rook\bin\Release\net48\runtimes' -Message 'Release workflow docs must copy net48 runtime assets for WebView2 panels.'
    Assert-Contains -Text $combined -Expected 'Rhino.Inside.Revit' -Message 'Release workflow docs must require Rhino.Inside.Revit smoke coverage for release validation.'
    Assert-Contains -Text $combined -Expected 'direct-registry' -Message 'Release workflow docs must call out the direct-registry loader assumption.'
    Assert-Contains -Text $combined -Expected 'physical `Rook.rhp`' -Message 'Release workflow docs must require recording the physical Rook.rhp path loaded by Rhino.'
    Assert-Contains -Text $combined -Expected 'Do not cite Yak/package-manager layout docs as proof' -Message 'Release workflow docs must not treat Yak package layout docs as proof for the Inno installer.'
}

function Test-BuildReleaseWorkflowUsesWindowsPowerShellCommands {
    $combined = @(
        Get-Content -Path $BuildReleaseSkill -Raw
        Get-Content -Path $IssSourcePaths -Raw
        Get-Content -Path $ClaudeBuildReleaseSkill -Raw
        Get-Content -Path $ClaudeIssSourcePaths -Raw
        Get-Content -Path $VersionLocations -Raw
        Get-Content -Path $ClaudeVersionLocations -Raw
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

function Test-BuildReleaseReferencesStaySynchronized {
    $agentVersionLocations = (Get-Content -Path $VersionLocations -Raw) -replace "`r`n", "`n"
    $claudeVersionLocations = (Get-Content -Path $ClaudeVersionLocations -Raw) -replace "`r`n", "`n"

    Assert-True -Condition ($agentVersionLocations -eq $claudeVersionLocations) -Message 'Codex and Claude build-release version-location references must stay synchronized.'
}

function Test-BuildReleaseWorkflowUsesReleaseBranchAndExactArtifacts {
    $combined = @(
        Get-Content -Path $BuildReleaseSkill -Raw
        Get-Content -Path $ClaudeBuildReleaseSkill -Raw
    ) -join "`n"

    Assert-NotContains -Text $combined -Unexpected 'git push origin main' -Message 'Release workflow must not document direct pushes to main.'
    Assert-Contains -Text $combined -Expected 'git switch -c release/vX.Y.Z' -Message 'Release workflow must make the release branch explicit.'
    Assert-Contains -Text $combined -Expected 'validate-release-artifacts.ps1' -Message 'Release workflow must run executable release artifact validation.'
    Assert-Contains -Text $combined -Expected 'release-manifest-X.Y.Z.json' -Message 'Release workflow must produce a release manifest with exact artifact identity.'
    Assert-Contains -Text $combined -Expected 'git_sha' -Message 'Release manifest requirements must include the exact git SHA being released.'
    Assert-Contains -Text $combined -Expected 'installer_sha256' -Message 'Release manifest requirements must include the installer SHA-256.'
    Assert-Contains -Text $combined -Expected 'ffmpeg_source_bundle_sha256' -Message 'Release manifest requirements must include the FFmpeg source bundle SHA-256.'
}

function Test-BuildReleaseDocsRequirePerHostSmokeManifest {
    $combined = @(
        Get-Content -Path $BuildReleaseSkill -Raw
        Get-Content -Path $ClaudeBuildReleaseSkill -Raw
        Get-Content -Path $ReleaseArtifactValidator -Raw
    ) -join "`n"

    Assert-Contains -Text $combined -Expected 'standalone_rhino' -Message 'Release smoke manifest must require a standalone Rhino host entry.'
    Assert-Contains -Text $combined -Expected 'rhino_inside_revit' -Message 'Release smoke manifest must require a Rhino.Inside.Revit host entry.'
    Assert-Contains -Text $combined -Expected 'host_runtime' -Message 'Release smoke manifest must record the runtime tested for each host.'
    Assert-Contains -Text $combined -Expected 'plugin_manager_listed' -Message 'Release smoke manifest must record that Rhino Plugin Manager lists RookNative.'
    Assert-Contains -Text $combined -Expected 'chat_service_manifest_path' -Message 'Release smoke manifest must record the installed chat service manifest path.'
    Assert-Contains -Text $combined -Expected 'chat_service_health' -Message 'Release smoke manifest must record successful chat service health.'
    Assert-Contains -Text $combined -Expected 'release smoke manifest standalone_rhino' -Message 'Release artifact validator must validate standalone Rhino smoke evidence separately.'
    Assert-Contains -Text $combined -Expected 'release smoke manifest rhino_inside_revit' -Message 'Release artifact validator must validate Rhino.Inside.Revit smoke evidence separately.'
}

function Test-BuildReleaseWorkflowPublishesFfmpegSourceBundle {
    $combined = @(
        Get-Content -Path $BuildReleaseSkill -Raw
        Get-Content -Path $ClaudeBuildReleaseSkill -Raw
    ) -join "`n"

    Assert-Contains -Text $combined -Expected 'rook-ffmpeg-8.1.1-source-bundle.zip' -Message 'GitHub release command must attach the FFmpeg source bundle zip.'
    Assert-Contains -Text $combined -Expected 'rook-ffmpeg-source-bundle-manifest.json' -Message 'GitHub release command must attach the FFmpeg source bundle manifest.'
    Assert-Contains -Text $combined -Expected 'Rook-Setup-X.Y.Z.exe' -Message 'GitHub release command must attach the installer.'
}

function Test-NativeReleaseBuildSelectsVcvarsToolset {
    $combined = @(
        Get-Content -Path $BuildReleaseSkill -Raw
        Get-Content -Path $ClaudeBuildReleaseSkill -Raw
        Get-Content -Path $BuildNativeScript -Raw
    ) -join "`n"

    Assert-Contains -Text $combined -Expected '-vcvars_ver=14.44' -Message 'Release native build docs/scripts must initialize vcvars with the known-good 14.44 toolset family.'
    Assert-Contains -Text $combined -Expected '$vcvarsVersion' -Message 'Native build script must derive and pass a vcvars toolset selector.'
}

function Test-ReleaseArtifactValidatorExists {
    Assert-True -Condition (Test-Path $ReleaseArtifactValidator) -Message "Release artifact validator is missing: $ReleaseArtifactValidator"
    $content = Get-Content -Path $ReleaseArtifactValidator -Raw

    Assert-Contains -Text $content -Expected 'installer_sha256' -Message 'Release artifact validator must emit installer SHA-256.'
    Assert-Contains -Text $content -Expected 'ffmpeg_source_bundle_sha256' -Message 'Release artifact validator must emit FFmpeg source bundle SHA-256.'
    Assert-Contains -Text $content -Expected 'git_sha' -Message 'Release artifact validator must bind artifacts to a git SHA.'
    Assert-Contains -Text $content -Expected 'System.Reflection.AssemblyName' -Message 'Release artifact validator must inspect managed assembly versions.'
    Assert-Contains -Text $content -Expected 'VersionInfo' -Message 'Release artifact validator must inspect native file version metadata.'
}

function Test-NativePdbRequirementIsConsistent {
    $combined = @(
        Get-Content -Path $BuildReleaseSkill -Raw
        Get-Content -Path $IssSourcePaths -Raw
        Get-Content -Path $ClaudeBuildReleaseSkill -Raw
        Get-Content -Path $ClaudeIssSourcePaths -Raw
    ) -join "`n"
    $agentIss = Get-Content -Path $IssSourcePaths -Raw
    $claudeIss = Get-Content -Path $ClaudeIssSourcePaths -Raw

    Assert-Contains -Text $combined -Expected 'RookNative.pdb` | Optional' -Message 'Release source checklist must describe the native PDB as optional to match installer skipifsourcedoesntexist behavior.'
    Assert-Contains -Text $combined -Expected '$optionalFiles' -Message 'Release source verification script must put optional artifacts in an optional file list.'
    Assert-Contains -Text $combined -Expected 'OPTIONAL MISSING' -Message 'Release source verification script must report absent optional artifacts without failing the checklist.'
    Assert-NotContains -Text $agentIss -Unexpected '$files = @(
  "src\RookNative\bin\Release\x64\RookNative.rhp",
  "src\RookNative\bin\Release\x64\RookNative.pdb",' -Message 'Codex release source verification script must not require RookNative.pdb.'
    Assert-NotContains -Text $claudeIss -Unexpected '$files = @(
  "src\RookNative\bin\Release\x64\RookNative.rhp",
  "src\RookNative\bin\Release\x64\RookNative.pdb",' -Message 'Claude release source verification script must not require RookNative.pdb.'
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
    Assert-Contains -Text $combined -Expected 'scripts\ffmpeg\build-rook-ffmpeg.ps1' -Message 'Release docs must require the Rook-owned FFmpeg build script.'
    Assert-Contains -Text $combined -Expected 'scripts\ffmpeg\rook-ffmpeg-enable-allowlist.json' -Message 'Release docs must reference the FFmpeg configure allowlist.'
    Assert-Contains -Text $combined -Expected 'scripts\ffmpeg\rook-ffmpeg-source.json' -Message 'Release docs must reference the pinned FFmpeg source metadata.'
    Assert-Contains -Text $combined -Expected 'SourceBundleManifestPath' -Message 'Release docs must pass the staged source-bundle manifest to FFmpeg validation.'
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

Test-InstallerPackagesMultiRuntimeCompanionPayloads
Test-BuiltCompanionPayloadsExist
Test-InstallerPackagesBundledFfmpegPayload
Test-FfmpegValidatorRequiresReleaseSourceBundleArgument
Test-FfmpegBuildScriptUsesAgentlessSignatureVerification
Test-FfmpegBuildRecipeTargetsOnlyFfmpegProgram
Test-InstallerRequiresNativePluginBuildOutput
Test-InstallerRegistersRhinoPluginFileNamesUnderPluginSubkey
Test-InstallerWritesRhinoPluginEnumerationMetadata
Test-InstallerBlocksWhenRhinoOrRevitAreRunning
Test-InstallerWarnsRegistrationIsPerWindowsUser
Test-InstallerVerifiesRhinoPluginRegistrationAfterInstall
Test-UninstallRemovesGeneratedRuntimeArtifacts
Test-PostInstallValidationUsesMultiRuntimeCompanionLayout
Test-ReleaseWorkflowDocsUseMultiRuntimeCompanionOutputs
Test-BuildReleaseWorkflowUsesWindowsPowerShellCommands
Test-BuildReleaseReferencesStaySynchronized
Test-BuildReleaseWorkflowUsesReleaseBranchAndExactArtifacts
Test-BuildReleaseDocsRequirePerHostSmokeManifest
Test-BuildReleaseWorkflowPublishesFfmpegSourceBundle
Test-NativeReleaseBuildSelectsVcvarsToolset
Test-ReleaseArtifactValidatorExists
Test-NativePdbRequirementIsConsistent
Test-BuildReleaseDocsRequireFfmpegValidation
Test-LegacyGitHubReleaseWorkflowIsDisabled

Write-Host 'Release installer guard tests passed.'
