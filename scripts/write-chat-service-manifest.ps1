# write-chat-service-manifest.ps1
#
# Writes the Rhino-owned chat service manifest into the deployed RookNative
# package. This gives the managed plugin an explicit runtime contract for
# starting the local Python chat service without depending on VSCode/Claude Code.
#
# Usage:
#   .\scripts\write-chat-service-manifest.ps1 -PluginDir "C:\...\Plug-ins\RookNative" `
#       -PythonPath "C:\...\mcp_server\.venv\Scripts\python.exe" `
#       -WorkingDirectory "C:\...\mcp_server"

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$PluginDir,

    [Parameter(Mandatory = $true)]
    [string]$PythonPath,

    [Parameter(Mandatory = $true)]
    [string]$WorkingDirectory,

    [string]$Module = "rook.agent.chat.service_main",
    [string]$Owner = "rhino-panel",
    [string[]]$PythonPathEntries
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $PluginDir)) {
    throw "Plugin directory not found: $PluginDir"
}

if (-not (Test-Path $PythonPath)) {
    throw "Python executable not found: $PythonPath"
}

if (-not (Test-Path $WorkingDirectory)) {
    throw "Working directory not found: $WorkingDirectory"
}

$manifest = @{
    pythonPath = (Resolve-Path $PythonPath).Path
    workingDirectory = (Resolve-Path $WorkingDirectory).Path
    module = $Module
    owner = $Owner
    pythonPathEntries = @()
}

$resolvedPythonPathEntries = @()
if ($PythonPathEntries) {
    foreach ($entry in $PythonPathEntries) {
        if (-not (Test-Path $entry)) {
            throw "Python path entry not found: $entry"
        }
        $resolvedPythonPathEntries += (Resolve-Path $entry).Path
    }
} else {
    $defaultSrc = Join-Path $WorkingDirectory "src"
    if (-not (Test-Path $defaultSrc)) {
        throw "Chat service source path not found: $defaultSrc"
    }
    $resolvedPythonPathEntries += (Resolve-Path $defaultSrc).Path
}

$manifest["pythonPathEntries"] = $resolvedPythonPathEntries

$manifestPath = Join-Path $PluginDir "RookChatService.json"
$json = $manifest | ConvertTo-Json -Depth 4
Set-Content -Path $manifestPath -Value $json -Encoding UTF8

if (-not (Test-Path $manifestPath)) {
    throw "Failed to write chat service manifest: $manifestPath"
}

Write-Host "Wrote chat service manifest: $manifestPath"
