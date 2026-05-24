$ErrorActionPreference = 'Stop'

$TestRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestRoot)
$RookServerCpp = Join-Path $RepoRoot 'src\RookNative\RookServer.cpp'
$RookServerHeader = Join-Path $RepoRoot 'src\RookNative\RookServer.h'

function Assert-Contains {
    param(
        [string]$Text,
        [string]$Expected,
        [string]$Message
    )

    if (-not $Text.Contains($Expected)) {
        throw $Message
    }
}

function Assert-Matches {
    param(
        [string]$Text,
        [string]$Pattern,
        [string]$Message
    )

    if ($Text -notmatch $Pattern) {
        throw $Message
    }
}

function Test-NativeDiscoveryUsesSharedRoot {
    $content = Get-Content -Path $RookServerCpp -Raw

    Assert-Contains -Text $content -Expected 'ResolveDiscoveryRootInfo' -Message 'RookServer.cpp must resolve discovery root details in one helper.'
    Assert-Contains -Text $content -Expected 'nativeTempRoot' -Message 'RookServer.cpp must log the native temp root separately.'
    Assert-Contains -Text $content -Expected 'sharedDiscoveryFolder' -Message 'RookServer.cpp must resolve a shared discovery folder.'
    Assert-Contains -Text $content -Expected 'LOCALAPPDATA' -Message 'Native discovery must prefer the deterministic per-user LOCALAPPDATA root.'
    Assert-Matches -Text $content -Pattern '"Rook"\s*/\s*"discovery"' -Message 'Native discovery must construct the shared per-user Rook discovery child.'
    Assert-Contains -Text $content -Expected 'selectionBranch' -Message 'Native diagnostics must report the root selection branch.'
}

function Test-NativeDiscoveryPublishesRhinoInsideMetadata {
    $content = Get-Content -Path $RookServerCpp -Raw

    Assert-Contains -Text $content -Expected 'info["processId"] = ::GetCurrentProcessId();' -Message 'Discovery JSON must publish host process ID.'
    Assert-Contains -Text $content -Expected 'info["rhinoInside"] = CRookNativePlugin::IsRhinoInside();' -Message 'Discovery JSON must publish rhinoInside.'
    Assert-Contains -Text $content -Expected 'info["pluginType"] = "native";' -Message 'Discovery JSON must publish native plugin type.'
    Assert-Contains -Text $content -Expected 'info["capabilities"]' -Message 'Discovery JSON must publish capabilities.'
}

function Test-NativeDiscoveryDiagnosticsAreDurable {
    $content = Get-Content -Path $RookServerCpp -Raw

    Assert-Contains -Text $content -Expected 'native-discovery-' -Message 'Native diagnostics must write a durable per-process diagnostic log.'
    Assert-Contains -Text $content -Expected 'WriteDiscoveryDiagnostic' -Message 'Native diagnostics must have a centralized best-effort writer.'
    Assert-Contains -Text $content -Expected 'post-rename verification' -Message 'Native diagnostics must record post-rename verification.'
    Assert-Contains -Text $content -Expected 'fs::file_size' -Message 'Post-rename verification must check final file size.'
    Assert-Matches -Text $content -Pattern 'nlohmann::json::parse\(' -Message 'Post-rename verification must read back or parse the final file.'
    Assert-Contains -Text $content -Expected 'MoveFileExW' -Message 'Atomic rename must remain explicit.'
    Assert-Contains -Text $content -Expected 'GetLastError' -Message 'Rename diagnostics must include Windows error code.'
}

function Test-NativeCleanupDiagnostics {
    $content = Get-Content -Path $RookServerCpp -Raw

    Assert-Contains -Text $content -Expected 'cleanup scan' -Message 'Startup cleanup must log scan decisions.'
    Assert-Contains -Text $content -Expected 'jsonPid=' -Message 'Startup cleanup must log JSON PID decisions for non-filename discovery records.'
    Assert-Contains -Text $content -Expected 'remove-on-unload' -Message 'Unload cleanup must log remove-on-unload decisions.'
    Assert-Contains -Text $content -Expected 'IsPidAlive' -Message 'Cleanup must keep using PID liveness.'
}

function Test-NativeDiscoveryKeepsOperationalPathsNative {
    $cppContent = Get-Content -Path $RookServerCpp -Raw
    $headerContent = Get-Content -Path $RookServerHeader -Raw

    if ($cppContent.Contains('discoveryPath.string()')) {
        throw 'Native discovery must not convert discoveryPath to ACP string for operational path storage.'
    }
    if ($cppContent.Contains('tmpPath.string()')) {
        throw 'Native discovery must not convert tmpPath to ACP string for operational file operations.'
    }

    Assert-Contains -Text $headerContent -Expected 'std::filesystem::path m_discovery_path;' -Message 'Native discovery should retain the unload path as std::filesystem::path.'
    Assert-Contains -Text $cppContent -Expected 'PathToUtf8String(m_discovery_path)' -Message 'Unload diagnostics should convert the retained native path to UTF-8 only for logging.'
}

function Test-HeaderDocumentsSharedDiscoveryRoot {
    $content = Get-Content -Path $RookServerHeader -Raw

    Assert-Contains -Text $content -Expected 'shared discovery root' -Message 'RookServer.h must document shared discovery root instead of only %TEMP%/rook.'
}

Test-NativeDiscoveryUsesSharedRoot
Test-NativeDiscoveryPublishesRhinoInsideMetadata
Test-NativeDiscoveryDiagnosticsAreDurable
Test-NativeCleanupDiagnostics
Test-NativeDiscoveryKeepsOperationalPathsNative
Test-HeaderDocumentsSharedDiscoveryRoot

Write-Host 'rhino-inside-discovery-guards.tests.ps1 passed'
