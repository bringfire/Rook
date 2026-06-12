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
$CompanionNet48RookBimDll = Join-Path $RepoRoot 'src\Rook\bin\Release\net48\RookBim.dll'
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
    Assert-True -Condition (Test-Path $CompanionNet48RookBimDll) -Message "Built RookBIM net48 module is missing: $CompanionNet48RookBimDll"
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

function Test-InstallerPackagesBundledPythonRuntime {
    $content = Get-Content -Path $InstallerScript -Raw

    Assert-Contains -Text $content -Expected '#define PythonRuntimeDir RepoRoot + "\installer\runtime\python\cpython-3.11.9"' -Message 'Installer must define staged private Python runtime directory.'
    Assert-Contains -Text $content -Expected '#define PythonWheelhouseDir RepoRoot + "\installer\runtime\python-wheelhouse"' -Message 'Installer must define staged wheelhouse directory.'
    Assert-Contains -Text $content -Expected 'Source: "{#PythonRuntimeDir}\*"; DestDir: "{localappdata}\Rook\python\cpython-3.11.9"' -Message 'Installer must package private Python runtime.'
    Assert-Contains -Text $content -Expected 'Source: "{#PythonWheelhouseDir}\*"; DestDir: "{app}\python-wheelhouse"' -Message 'Installer must package offline wheelhouse.'
    Assert-Contains -Text $content -Expected 'requirements-bootstrap-lock.txt' -Message 'Installer must package bootstrap lockfile.'
    Assert-Contains -Text $content -Expected 'requirements-rook-lock.txt' -Message 'Installer must package Rook lockfile.'
    Assert-Contains -Text $content -Expected 'requirements-chirp-lock.txt' -Message 'Installer must package Chirp lockfile.'
    Assert-Contains -Text $content -Expected 'python-runtime-manifest.json' -Message 'Installer must package Python runtime manifest.'
    Assert-Contains -Text $content -Expected 'python_runtime_install.py' -Message 'Installer must package runtime install helper.'
}

function Test-PublicInstallerDoesNotRequireUserPython {
    $content = Get-Content -Path $InstallerScript -Raw

    Assert-NotContains -Text $content -Unexpected 'Python MCP Server (requires Python 3.10+)' -Message 'Public MCP component must not require user Python.'
    Assert-NotContains -Text $content -Unexpected 'Chirp — LLM-powered Grasshopper components (requires MCP + Python 3.10+)' -Message 'Public Chirp component must not require user Python.'
    Assert-NotContains -Text $content -Unexpected 'Python 3.10+ is required for the MCP server and Chirp but was not found.' -Message 'Installer must not block public MCP/Chirp install on user Python.'
    Assert-NotContains -Text $content -Unexpected 'Filename: "{code:GetPythonPath}"' -Message 'Post-install must not be launched through user Python discovery.'
    Assert-Contains -Text $content -Expected 'ExpandConstant(''{localappdata}\Rook\python\cpython-3.11.9\python.exe'')' -Message 'Post-install must run on bundled private Python.'
}

function Test-InstallerFailsWhenPostInstallFails {
    $content = Get-Content -Path $InstallerScript -Raw

    Assert-NotContains -Text $content -Unexpected 'Filename: "{localappdata}\Rook\python\cpython-3.11.9\python.exe"; Parameters: """{app}\post_install.py""' -Message 'Post-install must not run through [Run], which cannot gate child exit codes.'
    Assert-Contains -Text $content -Expected 'function RunPostInstallSetup(): Boolean;' -Message 'Installer must run post_install.py from Pascal script where ResultCode can be checked.'
    Assert-Contains -Text $content -Expected 'Exec(PythonExe, Args, '''', SW_HIDE, ewWaitUntilTerminated, ResultCode)' -Message 'Installer post-install runner must capture the child process exit code.'
    Assert-Contains -Text $content -Expected 'ResultCode <> 0' -Message 'Installer must explicitly reject a nonzero post_install.py exit code.'
    Assert-Contains -Text $content -Expected 'Abort;' -Message 'Installer must abort when post_install.py fails instead of reporting success.'
    Assert-NotContains -Text $content -Unexpected 'Rook Python setup failed' -Message 'Installer must not misdiagnose client/finalization failures as Python setup failures.'
    Assert-Contains -Text $content -Expected 'Rook post-install finalization failed' -Message 'Installer failure dialog must name post-install finalization, not only Python setup.'
}

function Test-InstallerExplainsOfflineWheelhouseProgress {
    $content = Get-Content -Path $InstallerScript -Raw

    Assert-Contains -Text $content -Expected 'installing bundled wheels offline (no internet download required)' -Message 'Installer progress must explain the long Python finalization is offline wheelhouse work, not dependency download.'
    Assert-Contains -Text $content -Expected 'WizardForm.StatusLabel.Update' -Message 'Installer must repaint the progress label before long post-install work starts.'
}

function Test-UninstallUsesRecordedPrivatePython {
    $content = Get-Content -Path $InstallerScript -Raw

    Assert-Contains -Text $content -Expected 'python_path.txt' -Message 'Installer must record private Python path for uninstall cleanup.'
    Assert-Contains -Text $content -Expected '{localappdata}\Rook\python\cpython-3.11.9\python.exe' -Message 'Uninstall must have a deterministic private Python fallback path.'
    Assert-Contains -Text $content -Expected 'CurUninstallStepChanged' -Message 'Installer must run uninstall cleanup from the uninstall hook.'
    Assert-Contains -Text $content -Expected '--uninstall' -Message 'Uninstall cleanup must invoke post_install.py --uninstall.'
    Assert-NotContains -Text $content -Unexpected 'PythonExe := GetPythonPath()' -Message 'Uninstall must not depend on user Python discovery.'
}

function Test-ChatServiceUserPythonFallbackIsDevOnly {
    $chatManager = Join-Path $RepoRoot 'src\Rook\UI\Chat\ChatServiceManager.cs'
    $content = Get-Content -Path $chatManager -Raw

    Assert-Contains -Text $content -Expected 'ROOK_ALLOW_USER_PYTHON_DISCOVERY' -Message 'Chat service PATH Python discovery must be gated by explicit support override.'
    Assert-Contains -Text $content -Expected 'AllowUserPythonDiscovery' -Message 'Chat manager must centralize user Python fallback policy.'
    Assert-Contains -Text $content -Expected 'DiscoverManagedVenvPython()' -Message 'Chat manager must prefer managed Rook venv.'
    Assert-Contains -Text $content -Expected 'IsReleaseManifestContract' -Message 'Chat manager must reject stale/source-shaped release manifests.'
    Assert-Contains -Text $content -Expected 'AllowProjectRootEnvironment' -Message 'ROOK_PROJECT_ROOT propagation must be gated behind explicit dev/support mode.'
    Assert-Contains -Text $content -Expected 'release manifest workingDirectory' -Message 'Release chat manifest validation must enforce the installed mcp_server working directory.'
    Assert-Contains -Text $content -Expected 'release manifest module' -Message 'Release chat manifest validation must enforce the chat service module.'
    Assert-Contains -Text $content -Expected 'Path.Combine(localAppData, "Rook", "app")' -Message 'Release chat manifest validation must compare ROOK_INSTALL_ROOT to the exact installed app path.'
    Assert-Contains -Text $content -Expected 'Path.Combine(localAppData, "Rook", "data")' -Message 'Release chat manifest validation must compare ROOK_DATA_DIR to the exact installed data path.'
    Assert-Contains -Text $content -Expected 'ROOK_DSPY_RESTRICT_PICKLE' -Message 'Release chat manifest validation must require DSPy restricted pickle.'
    Assert-Contains -Text $content -Expected 'DSPY_CACHEDIR' -Message 'Release chat manifest validation must require the installed DSPy cache directory.'
    Assert-Contains -Text $content -Expected 'Path.Combine(expectedDataDir, "dspy-cache")' -Message 'Release chat manifest validation must compare DSPY_CACHEDIR to the exact installed data cache path.'
    Assert-Contains -Text $content -Expected 'Path.Combine(expectedInstallRoot, "chirp")' -Message 'Release chat manifest validation must compare CHIRP_HOME to the exact installed Chirp home.'
    Assert-Contains -Text $content -Expected 'BuildReleaseManifestEnvironment' -Message 'Auto-generated release chat manifests must include the full release environment contract.'
    Assert-Contains -Text $content -Expected 'IsReleaseManifestContract(manifest, out var generatedReleaseReason)' -Message 'Auto-generated release-shaped manifests must be validated before use.'
    Assert-NotContains -Text $content -Unexpected 'DiscoverManagedVenvPython() ?? DiscoverPython()' -Message 'Chat manager must not unconditionally fall back to PATH Python.'
    Assert-NotContains -Text $content -Unexpected '"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ROOK_PROJECT_ROOT", "ROOK_LOG_LEVEL"' -Message 'Release chat child process must not unconditionally inherit ROOK_PROJECT_ROOT.'
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
        '{localappdata}\Rook\python',
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
    Assert-Contains -Text $postInstallContent -Expected 'runtime_root / "python"' -Message 'Uninstall cleanup must remove the private Python runtime installed by the public installer.'
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
    Assert-Contains -Text $combined -Expected 'dotnet build src\RookBim\RookBim.csproj -c Release' -Message 'Release workflow docs must build the RookBIM module after the managed companion.'
    Assert-Contains -Text $combined -Expected 'src\Rook\bin\Release\net8.0\Rook.rhp' -Message 'Release workflow docs must reference the net8.0 companion output.'
    Assert-Contains -Text $combined -Expected 'src\Rook\bin\Release\net8.0\Rook.runtimeconfig.json' -Message 'Release workflow docs must mention the net8.0 runtimeconfig output.'
    Assert-Contains -Text $combined -Expected 'src\Rook\bin\Release\net7.0\Rook.rhp' -Message 'Release workflow docs must reference the net7.0 companion output.'
    Assert-Contains -Text $combined -Expected 'src\Rook\bin\Release\net7.0\Rook.runtimeconfig.json' -Message 'Release workflow docs must mention the net7.0 runtimeconfig output.'
    Assert-Contains -Text $combined -Expected 'src\Rook\bin\Release\net48\Rook.rhp' -Message 'Release workflow docs must reference the net48 companion output.'
    Assert-Contains -Text $combined -Expected 'src\Rook\bin\Release\net48\RookBim.dll' -Message 'Release workflow docs must require the RookBIM module in the net48 companion payload.'
    Assert-Contains -Text $combined -Expected 'src\Rook\bin\Release\net48\runtimes' -Message 'Release workflow docs must copy net48 runtime assets for WebView2 panels.'
    Assert-Contains -Text $combined -Expected 'Rhino.Inside.Revit' -Message 'Release workflow docs must require Rhino.Inside.Revit smoke coverage for release validation.'
    Assert-Contains -Text $combined -Expected 'direct-registry' -Message 'Release workflow docs must call out the direct-registry loader assumption.'
    Assert-Contains -Text $combined -Expected 'companion self-report' -Message 'Release workflow docs must require managed companion self-report evidence.'
    Assert-Contains -Text $combined -Expected 'companion_self_report' -Message 'Release workflow docs must include companion_self_report in smoke manifests.'
    Assert-Contains -Text $combined -Expected 'statusUpdatedUtc' -Message 'Release workflow docs must require the managed companion self-report freshness timestamp.'
    Assert-Contains -Text $combined -Expected 'smoke_started_utc' -Message 'Release workflow docs must include the release smoke start timestamp.'
    Assert-Contains -Text $combined -Expected 'Do not cite Yak/package-manager layout docs as proof' -Message 'Release workflow docs must not treat Yak package layout docs as proof for the Inno installer.'
}

function Test-BuildReleaseDocsRequireBundledPythonPayload {
    $combined = @(
        Get-Content -Path $BuildReleaseSkill -Raw
        Get-Content -Path $ClaudeBuildReleaseSkill -Raw
        Get-Content -Path $IssSourcePaths -Raw
        Get-Content -Path $ClaudeIssSourcePaths -Raw
    ) -join "`n"

    Assert-Contains -Text $combined -Expected 'scripts\python-runtime\stage-rook-python-runtime.ps1' -Message 'Release docs must stage private Python runtime.'
    Assert-Contains -Text $combined -Expected 'scripts\python-runtime\build-rook-python-wheelhouse.ps1' -Message 'Release docs must build offline Python wheelhouse.'
    Assert-Contains -Text $combined -Expected 'installer\runtime\python\cpython-3.11.9\python.exe' -Message 'Source checklist must require staged private Python runtime.'
    Assert-Contains -Text $combined -Expected 'installer\runtime\python-wheelhouse' -Message 'Source checklist must require staged wheelhouse.'
    Assert-Contains -Text $combined -Expected 'installer\runtime\requirements-bootstrap-lock.txt' -Message 'Source checklist must require bootstrap lockfile.'
    Assert-Contains -Text $combined -Expected 'installer\runtime\requirements-rook-lock.txt' -Message 'Source checklist must require Rook lockfile.'
    Assert-Contains -Text $combined -Expected 'installer\runtime\requirements-chirp-lock.txt' -Message 'Source checklist must require Chirp lockfile.'
    Assert-Contains -Text $combined -Expected 'installer\runtime\python-runtime-manifest.json' -Message 'Source checklist must require Python runtime manifest.'
    Assert-Contains -Text $combined -Expected 'rook.local_testing_proof python-smoke-evidence' -Message 'Release docs must collect Python smoke evidence mechanically from the installed runtime.'
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

function Test-BuildReleaseVersionBumpIncludesRookBim {
    $combined = @(
        Get-Content -Path $BuildReleaseSkill -Raw
        Get-Content -Path $ClaudeBuildReleaseSkill -Raw
        Get-Content -Path $VersionLocations -Raw
        Get-Content -Path $ClaudeVersionLocations -Raw
    ) -join "`n"

    Assert-Contains -Text $combined -Expected 'Release branch version bump (7 files / 10 edits)' -Message 'Release workflow must count RookBIM in the version bump surface.'
    Assert-NotContains -Text $combined -Unexpected 'Release branch version bump (6 files / 8 edits)' -Message 'Release workflow must not retain the stale pre-RookBIM version bump count.'
    Assert-Contains -Text $combined -Expected 'Every release requires updating these 7 files.' -Message 'Version-location docs must include RookBIM in the release file count.'
    Assert-Contains -Text $combined -Expected 'src/RookBim/RookBim.csproj' -Message 'Version-location docs must list the RookBIM project version.'
    Assert-Contains -Text $combined -Expected 'src\RookBim\RookBim.csproj, `' -Message 'Step 1 version verification must scan RookBIM.'
    Assert-Contains -Text $combined -Expected 'Expect 8 string matches' -Message 'Step 1 version verification must expect the additional RookBIM string match.'
    Assert-Contains -Text $combined -Expected 'git add mcp_server\pyproject.toml installer\RookSetup.iss src\Rook\Rook.csproj src\RookBim\RookBim.csproj' -Message 'Release commit command must stage the RookBIM version bump.'
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
    Assert-Contains -Text $combined -Expected 'companion_self_report' -Message 'Release smoke manifest must record managed companion self-report evidence.'
    Assert-Contains -Text $combined -Expected 'assemblyLocation' -Message 'Release smoke manifest must record self-reported companion assemblyLocation.'
    Assert-Contains -Text $combined -Expected 'startupComplete' -Message 'Release smoke manifest must record self-reported companion startup completion.'
    Assert-Contains -Text $combined -Expected 'statusUpdatedUtc' -Message 'Release smoke manifest must record self-reported companion status freshness.'
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
    Assert-Contains -Text $content -Expected 'src\Rook\bin\Release\net48\RookBim.dll' -Message 'Release artifact validator must require the built RookBIM net48 module.'
    Assert-Contains -Text $content -Expected 'rook_bim' -Message 'Release artifact validator must record RookBIM module identity in the release manifest.'
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

function Test-InstallerUsesRookProcessPreflight {
    $content = Get-Content -Path $InstallerScript -Raw

    Assert-Contains -Text $content -Expected 'CloseApplications=no' -Message 'Installer must disable Inno Restart Manager close-app behavior.'
    Assert-Contains -Text $content -Expected 'RestartApplications=no' -Message 'Installer must not restart raw python -m rook processes after install.'
    Assert-Contains -Text $content -Expected 'SetupLogging=yes' -Message 'Installer must enable Inno setup logging as a backstop.'
    Assert-Contains -Text $content -Expected 'Source: "rook_process_preflight.ps1"; Flags: dontcopy' -Message 'Preflight helper must be embedded for ExtractTemporaryFile before [Files].'
    Assert-Contains -Text $content -Expected 'ExtractTemporaryFile(''rook_process_preflight.ps1'')' -Message 'PrepareToInstall must extract the helper to {tmp}.'
    Assert-Contains -Text $content -Expected 'function RunRookProcessPreflight' -Message 'Installer must run Rook process preflight before [Files].'
    Assert-Contains -Text $content -Expected 'RunRookPreflightHelper(''enumerate''' -Message 'Preflight must run helper enumeration mode.'
    Assert-Contains -Text $content -Expected 'RunRookPreflightHelper(''close''' -Message 'Preflight must run helper close mode after consent or silent implied consent.'
    Assert-Contains -Text $content -Expected 'RunRookPreflightHelper(''record-outcome''' -Message 'Consent cancellation must be recorded by the helper, not Pascal SaveStringToFile.'
    Assert-Contains -Text $content -Expected 'WizardSilent' -Message 'Silent and very-silent installs must imply consent.'
    Assert-Contains -Text $content -Expected 'CurInstallProgressChanged' -Message 'Installer must either re-sweep during [Files] or explicitly document the accepted race in the PR.'
    Assert-Contains -Text $content -Expected 'function GetTickCount: Cardinal; external ''GetTickCount@kernel32.dll stdcall'';' -Message '[Files] re-sweep timer must import GetTickCount from kernel32.dll for Inno Pascal Script compilation.'
    Assert-Contains -Text $content -Expected 'GetTickCount' -Message '[Files] re-sweep must be time-throttled and not spawn PowerShell on every progress tick.'
    Assert-Contains -Text $content -Expected 'Rook agent server' -Message 'Consent dialog must name Rook agent servers in plain language.'
}

function Test-InstallerDeletesStaleChildChatManifests {
    $content = Get-Content -Path $InstallerScript -Raw
    $installDeleteMatch = [regex]::Match($content, '(?ms)^\[InstallDelete\]\s*(?<block>.*?)(?=^\[Files\])')
    Assert-True -Condition $installDeleteMatch.Success -Message 'Installer must place [InstallDelete] before [Files] so stale child manifests are removed before payload copy.'
    $installDeleteBlock = $installDeleteMatch.Groups['block'].Value

    foreach ($runtime in @('net8.0', 'net7.0', 'net48')) {
        $expectedLine = "Type: files; Name: `"{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\$runtime\RookChatService.json`""
        Assert-Contains -Text $installDeleteBlock -Expected $expectedLine -Message "Installer must delete stale $runtime child chat manifest with Type: files in [InstallDelete] before [Files]."
    }
}

Test-InstallerPackagesBundledPythonRuntime
Test-PublicInstallerDoesNotRequireUserPython
Test-InstallerFailsWhenPostInstallFails
Test-InstallerExplainsOfflineWheelhouseProgress
Test-UninstallUsesRecordedPrivatePython
Test-ChatServiceUserPythonFallbackIsDevOnly
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
Test-BuildReleaseDocsRequireBundledPythonPayload
Test-BuildReleaseWorkflowUsesWindowsPowerShellCommands
Test-BuildReleaseReferencesStaySynchronized
Test-BuildReleaseVersionBumpIncludesRookBim
Test-BuildReleaseWorkflowUsesReleaseBranchAndExactArtifacts
Test-BuildReleaseDocsRequirePerHostSmokeManifest
Test-BuildReleaseWorkflowPublishesFfmpegSourceBundle
Test-NativeReleaseBuildSelectsVcvarsToolset
Test-ReleaseArtifactValidatorExists
Test-NativePdbRequirementIsConsistent
Test-BuildReleaseDocsRequireFfmpegValidation
Test-LegacyGitHubReleaseWorkflowIsDisabled
Test-InstallerUsesRookProcessPreflight
Test-InstallerDeletesStaleChildChatManifests

Write-Host 'Release installer guard tests passed.'
