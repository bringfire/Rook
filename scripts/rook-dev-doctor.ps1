# rook-dev-doctor.ps1
#
# Read-only local development readiness checks for Rook. This script reports
# machine and repository state, but does not deploy, register, create, delete,
# kill, or persistently change anything.

[CmdletBinding()]
param(
    [switch]$Strict
)

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $PSCommandPath
$RepoRoot = Split-Path -Parent $ScriptDir

$ManagedCompanionRuntimes = @('net8.0', 'net7.0', 'net48')
$OcctRequiredHeaders = @('Standard.hxx','TopoDS_Shape.hxx','BRep_Builder.hxx','Geom_BSplineSurface.hxx','gp_Pnt.hxx','OSD.hxx')
$OcctRuntimeDlls = @('TKernel.dll','TKMath.dll','TKG2d.dll','TKG3d.dll','TKGeomBase.dll','TKGeomAlgo.dll','TKBRep.dll','TKTopAlgo.dll','TKPrim.dll','TKBO.dll','TKShHealing.dll')

$script:PassCount = 0
$script:WarnCount = 0
$script:FailCount = 0

function Write-CheckResult {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet('PASS', 'WARN', 'FAIL')]
        [string]$Status,

        [Parameter(Mandatory = $true)]
        [string]$Name,

        [string]$Detail = ''
    )

    switch ($Status) {
        'PASS' { $script:PassCount++ }
        'WARN' { $script:WarnCount++ }
        'FAIL' { $script:FailCount++ }
    }

    if ([string]::IsNullOrWhiteSpace($Detail)) {
        Write-Host "[$Status] $Name"
    } else {
        Write-Host "[$Status] $Name - $Detail"
    }
}

function Test-RequiredPath {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string]$Path
    )

    if (Test-Path $Path) {
        Write-CheckResult -Status PASS -Name $Label -Detail $Path
    } else {
        Write-CheckResult -Status FAIL -Name $Label -Detail "Missing: $Path"
    }
}

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = @(& git @Arguments 2>$null)
        return [pscustomobject]@{
            ExitCode = $LASTEXITCODE
            Output = $output
        }
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
}

function Resolve-OcctRuntimeRoot {
    if (-not [string]::IsNullOrWhiteSpace($env:OCCT_ROOT)) {
        return [pscustomobject]@{
            Root = $env:OCCT_ROOT
            Source = 'OCCT_ROOT'
        }
    }

    return $null
}

function Invoke-GitChecks {
    $gitCommand = Get-Command git -ErrorAction SilentlyContinue
    if (-not $gitCommand) {
        Write-CheckResult -Status FAIL -Name 'Git command' -Detail 'git was not found on PATH.'
        return
    }

    Write-CheckResult -Status PASS -Name 'Git command' -Detail $gitCommand.Source

    $insideRepoResult = Invoke-Git -Arguments @('-C', $RepoRoot, 'rev-parse', '--is-inside-work-tree')
    $insideRepo = (($insideRepoResult.Output) -join '').Trim()
    if ($insideRepoResult.ExitCode -ne 0 -or $insideRepo -ne 'true') {
        Write-CheckResult -Status FAIL -Name 'Git repo inspect' -Detail "git could not inspect $RepoRoot."
        return
    }

    Write-CheckResult -Status PASS -Name 'Git repo inspect' -Detail $RepoRoot

    $branchResult = Invoke-Git -Arguments @('-C', $RepoRoot, 'rev-parse', '--abbrev-ref', 'HEAD')
    $branch = (($branchResult.Output) -join '').Trim()
    if ($branchResult.ExitCode -eq 0 -and $branch) {
        Write-CheckResult -Status PASS -Name 'Git branch' -Detail $branch
    } else {
        Write-CheckResult -Status WARN -Name 'Git branch' -Detail 'Unable to determine current branch.'
    }

    $dirtyResult = Invoke-Git -Arguments @('-C', $RepoRoot, 'status', '--porcelain')
    $dirty = @($dirtyResult.Output)
    if ($dirtyResult.ExitCode -eq 0 -and $dirty.Count -gt 0) {
        Write-CheckResult -Status WARN -Name 'Git working tree' -Detail "$($dirty.Count) changed path(s)."
    } elseif ($dirtyResult.ExitCode -eq 0) {
        Write-CheckResult -Status PASS -Name 'Git working tree' -Detail 'Clean.'
    } else {
        Write-CheckResult -Status WARN -Name 'Git working tree' -Detail 'Unable to inspect working tree status.'
    }

    $upstreamResult = Invoke-Git -Arguments @('-C', $RepoRoot, 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}')
    $upstream = (($upstreamResult.Output) -join '').Trim()
    if ($upstreamResult.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($upstream)) {
        Write-CheckResult -Status WARN -Name 'Git upstream' -Detail 'No upstream branch configured.'
        return
    }

    Write-CheckResult -Status PASS -Name 'Git upstream' -Detail $upstream

    $aheadBehindResult = Invoke-Git -Arguments @('-C', $RepoRoot, 'rev-list', '--left-right', '--count', 'HEAD...@{u}')
    $aheadBehind = (($aheadBehindResult.Output) -join '').Trim()
    if ($aheadBehindResult.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($aheadBehind)) {
        Write-CheckResult -Status WARN -Name 'Git upstream sync' -Detail 'Unable to compare ahead/behind state.'
        return
    }

    $parts = $aheadBehind -split '\s+'
    $ahead = [int]$parts[0]
    $behind = [int]$parts[1]
    if ($ahead -gt 0 -or $behind -gt 0) {
        Write-CheckResult -Status WARN -Name 'Git upstream sync' -Detail "Ahead $ahead, behind $behind relative to $upstream."
    } else {
        Write-CheckResult -Status PASS -Name 'Git upstream sync' -Detail "In sync with $upstream."
    }
}

function Invoke-RequiredPathChecks {
    Test-RequiredPath -Label 'Repo root' -Path $RepoRoot
    Test-RequiredPath -Label 'scripts' -Path $ScriptDir
    Test-RequiredPath -Label 'deploy-local-testing.ps1' -Path (Join-Path $ScriptDir 'deploy-local-testing.ps1')
    Test-RequiredPath -Label 'mcp_server' -Path (Join-Path $RepoRoot 'mcp_server')
    Test-RequiredPath -Label 'mcp_server\.venv\Scripts\python.exe' -Path (Join-Path $RepoRoot 'mcp_server\.venv\Scripts\python.exe')
    Test-RequiredPath -Label 'src\RookNative' -Path (Join-Path $RepoRoot 'src\RookNative')
    Test-RequiredPath -Label 'src\Rook' -Path (Join-Path $RepoRoot 'src\Rook')
    Test-RequiredPath -Label 'src\RookBim' -Path (Join-Path $RepoRoot 'src\RookBim')
}

function Invoke-ProcessChecks {
    $rhino = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match '^(Rhino|Rhinoceros)$' })
    if ($rhino.Count -gt 0) {
        $ids = ($rhino | Select-Object -ExpandProperty Id) -join ', '
        Write-CheckResult -Status WARN -Name 'Rhino processes' -Detail "Rhino/Rhinoceros is running. Process IDs: $ids"
    } else {
        Write-CheckResult -Status PASS -Name 'Rhino processes' -Detail 'No Rhino/Rhinoceros process detected.'
    }

    try {
        $rookPython = @(Get-CimInstance Win32_Process |
            Where-Object {
                $_.Name -match '^pythonw?\.exe$' -and
                $_.CommandLine -match '(^|\s)-m\s+rook(\s|$)'
            })
        if ($rookPython.Count -gt 0) {
            $ids = ($rookPython | Select-Object -ExpandProperty ProcessId) -join ', '
            Write-CheckResult -Status WARN -Name 'python -m rook processes' -Detail "Detected python -m rook process IDs: $ids. Use scripts\rook-mcp-processes.ps1 to list them, or add -Stop to stop only these processes."
        } else {
            Write-CheckResult -Status PASS -Name 'python -m rook processes' -Detail 'No stale rook MCP process detected.'
        }
    } catch {
        Write-CheckResult -Status WARN -Name 'python -m rook processes' -Detail "Unable to inspect python command lines: $($_.Exception.Message)"
    }
}

function Invoke-MsvcChecks {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (-not (Test-Path $vswhere)) {
        Write-CheckResult -Status WARN -Name 'vswhere' -Detail "Missing: $vswhere"
        return
    }

    Write-CheckResult -Status PASS -Name 'vswhere' -Detail $vswhere

    $installations = @(& $vswhere -all -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2>$null)
    if ($LASTEXITCODE -ne 0 -or $installations.Count -eq 0) {
        Write-CheckResult -Status WARN -Name 'Visual Studio C++ installs' -Detail 'No Visual Studio C++ installation was reported by vswhere.'
        return
    }

    $requiredVersion = '14.44.35207'
    $found = $false
    foreach ($install in $installations) {
        $afxwin = Join-Path $install "VC\Tools\MSVC\$requiredVersion\atlmfc\include\afxwin.h"
        if (Test-Path $afxwin) {
            Write-CheckResult -Status PASS -Name 'MSVC/MFC 14.44.35207' -Detail $afxwin
            $found = $true
            break
        }
    }

    if (-not $found) {
        Write-CheckResult -Status FAIL -Name 'MSVC/MFC 14.44.35207' -Detail 'Visual Studio was found, but VC\Tools\MSVC\14.44.35207\atlmfc\include\afxwin.h was not.'
    }
}

function Invoke-OcctChecks {
    $occt = Resolve-OcctRuntimeRoot
    if (-not $occt) {
        Write-CheckResult -Status FAIL -Name 'OCCT root source' -Detail 'OCCT_ROOT is not set. Set OCCT_ROOT to the active OCCT build root before native build or deploy.'
        return
    }

    Write-CheckResult -Status PASS -Name 'OCCT root source' -Detail "Using $($occt.Source): $($occt.Root)."

    $required = @(
        (Join-Path $occt.Root 'win64\vc14\lib\TKernel.lib'),
        (Join-Path $occt.Root 'win64\vc14\bin')
    )

    foreach ($path in $required) {
        if (Test-Path $path) {
            Write-CheckResult -Status PASS -Name 'OCCT required path' -Detail $path
        } else {
            Write-CheckResult -Status FAIL -Name 'OCCT required path' -Detail "Missing: $path"
        }
    }

    $includeRoot = Join-Path $occt.Root 'inc'
    foreach ($header in $OcctRequiredHeaders) {
        $headerPath = Join-Path $includeRoot $header
        if (Test-Path $headerPath) {
            Write-CheckResult -Status PASS -Name "OCCT header $header" -Detail $headerPath
        } else {
            Write-CheckResult -Status FAIL -Name "OCCT header $header" -Detail "Missing: $headerPath"
        }
    }

    $binRoot = Join-Path $occt.Root 'win64\vc14\bin'
    foreach ($dll in $OcctRuntimeDlls) {
        $dllPath = Join-Path $binRoot $dll
        if (Test-Path $dllPath) {
            Write-CheckResult -Status PASS -Name "OCCT runtime DLL $dll" -Detail $dllPath
        } else {
            Write-CheckResult -Status FAIL -Name "OCCT runtime DLL $dll" -Detail "Missing: $dllPath"
        }
    }

    $header = Join-Path $includeRoot 'Standard.hxx'
    if (Test-Path $header) {
        $firstLines = (Get-Content -Path $header -TotalCount 20) -join "`n"
        if ($firstLines -match '[A-Za-z]:\\[^\n]*\\OCCT\\') {
            Write-CheckResult -Status FAIL -Name 'OCCT header forwarding' -Detail 'inc\Standard.hxx appears to forward to an absolute OCCT source tree on this machine.'
        } else {
            Write-CheckResult -Status PASS -Name 'OCCT header forwarding' -Detail 'inc\Standard.hxx does not expose a local source-tree forwarding path in its first lines.'
        }
    }
}

function Invoke-RepoVenvImportCheck {
    $python = Join-Path $RepoRoot 'mcp_server\.venv\Scripts\python.exe'
    if (-not (Test-Path $python)) {
        Write-CheckResult -Status FAIL -Name 'Repo venv import rook' -Detail "Missing: $python"
        return
    }

    $previousPythonPath = $env:PYTHONPATH
    $previousPythonDontWriteBytecode = $env:PYTHONDONTWRITEBYTECODE
    try {
        $env:PYTHONPATH = Join-Path $RepoRoot 'mcp_server\src'
        $env:PYTHONDONTWRITEBYTECODE = '1'
        $output = @(& $python -B -c "import rook; print(rook.__file__)" 2>&1)
        if ($LASTEXITCODE -eq 0) {
            Write-CheckResult -Status PASS -Name 'Repo venv import rook' -Detail (($output -join ' ').Trim())
        } else {
            Write-CheckResult -Status FAIL -Name 'Repo venv import rook' -Detail (($output -join ' ').Trim())
        }
    } finally {
        $env:PYTHONPATH = $previousPythonPath
        $env:PYTHONDONTWRITEBYTECODE = $previousPythonDontWriteBytecode
    }
}

function Invoke-ChirpSiblingCheck {
    $chirpRoot = Join-Path (Split-Path -Parent $RepoRoot) 'Chirp'
    $missing = @()
    foreach ($relative in @('pyproject.toml', 'src\chirp')) {
        $path = Join-Path $chirpRoot $relative
        if (-not (Test-Path $path)) {
            $missing += $relative
        }
    }

    if ($missing.Count -gt 0) {
        Write-CheckResult -Status WARN -Name 'Chirp sibling' -Detail "Missing under $chirpRoot`: $($missing -join ', ')"
    } else {
        Write-CheckResult -Status PASS -Name 'Chirp sibling' -Detail $chirpRoot
    }
}

function Invoke-RevitApiCheck {
    $revitRoot = if (-not [string]::IsNullOrWhiteSpace($env:RevitInstallDir)) {
        $env:RevitInstallDir
    } else {
        Join-Path $env:ProgramFiles 'Autodesk\Revit 2024'
    }

    foreach ($dll in @('RevitAPI.dll', 'RevitAPIUI.dll')) {
        $path = Join-Path $revitRoot $dll
        if (Test-Path $path) {
            Write-CheckResult -Status PASS -Name "Revit API $dll" -Detail $path
        } else {
            Write-CheckResult -Status FAIL -Name "Revit API $dll" -Detail "Missing: $path"
        }
    }
}

function Invoke-InnoSetupCheck {
    $candidates = @(
        (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')
    )

    $found = @($candidates | Where-Object { Test-Path $_ } | Select-Object -First 1)
    if ($found.Count -gt 0) {
        Write-CheckResult -Status PASS -Name 'Inno Setup ISCC.exe' -Detail $found[0]
    } else {
        Write-CheckResult -Status WARN -Name 'Inno Setup ISCC.exe' -Detail "Missing from: $($candidates -join '; ')"
    }
}

function Test-ChatManifest {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string]$Path
    )

    if (-not (Test-Path $Path)) {
        Write-CheckResult -Status WARN -Name $Label -Detail "Missing RookChatService.json: $Path"
        return
    }

    try {
        $manifest = Get-Content -Path $Path -Raw | ConvertFrom-Json
        $mode = $manifest.environment.ROOK_MODE
        if ($mode -eq 'dev' -or $mode -eq 'release') {
            Write-CheckResult -Status PASS -Name $Label -Detail "RookChatService.json environment.ROOK_MODE=$mode"
        } else {
            Write-CheckResult -Status WARN -Name $Label -Detail "RookChatService.json has unexpected environment.ROOK_MODE='$mode'."
        }
    } catch {
        Write-CheckResult -Status WARN -Name $Label -Detail "Unable to parse RookChatService.json: $($_.Exception.Message)"
    }
}

function Invoke-ChatManifestChecks {
    $pluginDir = Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'McNeel\Rhinoceros\8.0\Plug-ins\RookNative'
    Test-ChatManifest -Label 'Chat manifest root' -Path (Join-Path $pluginDir 'RookChatService.json')

    $runtimeLabels = @{
        'net8.0' = 'Chat manifest net8.0'
        'net7.0' = 'Chat manifest net7.0'
        'net48' = 'Chat manifest net48'
    }

    foreach ($runtime in $ManagedCompanionRuntimes) {
        $label = $runtimeLabels[$runtime]
        $runtimeDir = Join-Path $pluginDir $runtime
        $manifestPath = Join-Path $runtimeDir 'RookChatService.json'
        Test-ChatManifest -Label $label -Path $manifestPath
    }
}

Write-Host "Rook dev doctor"
Write-Host "Repo root: $RepoRoot"
Write-Host ""

Invoke-GitChecks
Invoke-RequiredPathChecks
Invoke-ProcessChecks
Invoke-MsvcChecks
Invoke-OcctChecks
Invoke-RepoVenvImportCheck
Invoke-ChirpSiblingCheck
Invoke-RevitApiCheck
Invoke-InnoSetupCheck
Invoke-ChatManifestChecks

Write-Host ""
Write-Host "Summary: $script:PassCount PASS, $script:WarnCount WARN, $script:FailCount FAIL"

if ($script:FailCount -gt 0 -or ($Strict -and $script:WarnCount -gt 0)) {
    exit 1
}

exit 0
