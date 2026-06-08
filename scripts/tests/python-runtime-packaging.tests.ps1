$ErrorActionPreference = 'Stop'

$TestRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestRoot)
$RuntimeConfigPath = Join-Path $RepoRoot 'installer\python-runtime\python-runtime.json'
$RuntimeStager = Join-Path $RepoRoot 'scripts\python-runtime\stage-rook-python-runtime.ps1'
$WheelhouseBuilder = Join-Path $RepoRoot 'scripts\python-runtime\build-rook-python-wheelhouse.ps1'

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Assert-Contains {
    param([string]$Text, [string]$Expected, [string]$Message)
    Assert-True -Condition $Text.Contains($Expected) -Message $Message
}

function Assert-NotContains {
    param([string]$Text, [string]$Expected, [string]$Message)
    Assert-True -Condition (-not $Text.Contains($Expected)) -Message $Message
}

function Get-CodeWithoutPowerShellComments {
    param([string]$Text)
    $tokens = $null
    $errors = $null
    $null = [System.Management.Automation.Language.Parser]::ParseInput($Text, [ref]$tokens, [ref]$errors)
    Assert-True -Condition ($errors.Count -eq 0) -Message "PowerShell parse errors in wheelhouse builder: $($errors -join '; ')"
    return (($tokens | Where-Object { $_.Kind -ne 'Comment' } | ForEach-Object { $_.Text }) -join ' ')
}

function Test-PythonRuntimeConfigIsPinned {
    Assert-True -Condition (Test-Path $RuntimeConfigPath) -Message "Missing runtime config: $RuntimeConfigPath"
    $config = Get-Content -Path $RuntimeConfigPath -Raw | ConvertFrom-Json
    Assert-True -Condition ($config.schema_version -eq 1) -Message 'Runtime config must declare schema_version 1.'
    Assert-True -Condition ($config.python_nuget_package -eq 'python') -Message 'Runtime config must use the official python NuGet package.'
    Assert-True -Condition ($config.python_version -eq '3.11.9') -Message 'Runtime config must pin exact Python version 3.11.9 for this release.'
    Assert-True -Condition ($config.python_abi -eq 'cp311') -Message 'Runtime config must record cp311 ABI.'
    Assert-True -Condition ($config.target_platform -eq 'win_amd64') -Message 'Runtime config must target win_amd64.'
    Assert-True -Condition ($config.nupkg_sha256 -match '^[A-F0-9]{64}$') -Message 'Runtime config must contain an uppercase SHA256 for the nupkg.'
    Assert-True -Condition ($config.nupkg_sha256 -eq '9283876D58C017E0E846F95B490DA3BCA0FC0A6EE1134B2870677CFB7EEC3C67') -Message 'Runtime config must pin the verified Python 3.11.9 nupkg SHA256.'
    Assert-True -Condition ($config.expected_executable -eq 'tools\python.exe') -Message 'Runtime config must record the expected NuGet tools python.exe.'
}

function Test-PythonRuntimeStagerExistsAndNeverRunsAtInstallTime {
    Assert-True -Condition (Test-Path $RuntimeStager) -Message "Missing runtime stager: $RuntimeStager"
    $content = Get-Content -Path $RuntimeStager -Raw
    Assert-Contains -Text $content -Expected 'installer\python-runtime\python-runtime.json' -Message 'Stager must read the pinned runtime config.'
    Assert-Contains -Text $content -Expected 'Get-FileHash' -Message 'Stager must verify the nupkg hash.'
    Assert-Contains -Text $content -Expected 'Expand-Archive' -Message 'Stager must extract the NuGet package.'
    Assert-Contains -Text $content -Expected 'tools\python.exe' -Message 'Stager must stage the NuGet tools python.exe layout.'
}

function Test-PythonRuntimeStagerStagesRuntimeIntoTempRoots {
    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) "rook-python-runtime-packaging-$([System.Guid]::NewGuid().ToString('N'))"
    $outputRoot = Join-Path $tempRoot 'runtime'
    $downloadRoot = Join-Path $tempRoot 'downloads'

    try {
        $stageOutput = & powershell -NoProfile -ExecutionPolicy Bypass -File $RuntimeStager -OutputRoot $outputRoot -DownloadRoot $downloadRoot 2>&1
        Assert-True -Condition ($LASTEXITCODE -eq 0) -Message "Runtime stager failed:`n$($stageOutput -join "`n")"

        $stagedPython = Join-Path $outputRoot 'cpython-3.11.9\python.exe'
        Assert-True -Condition (Test-Path -LiteralPath $stagedPython -PathType Leaf) -Message "Stager did not create expected python.exe: $stagedPython"
    }
    finally {
        if (Test-Path -LiteralPath $tempRoot) {
            Remove-Item -LiteralPath $tempRoot -Recurse -Force
        }
    }
}

function Test-WheelhouseBuilderExists {
    Assert-True -Condition (Test-Path $WheelhouseBuilder) -Message "Missing wheelhouse builder: $WheelhouseBuilder"
}

function Test-WheelhouseBuilderEnforcesReleaseContracts {
    $content = Get-Content -Path $WheelhouseBuilder -Raw
    $code = Get-CodeWithoutPowerShellComments -Text $content
    Assert-NotContains -Text $content -Expected 'Release contract markers used by scripts/tests/python-runtime-packaging.tests.ps1' -Message 'Wheelhouse builder must not satisfy guard tests with marker comments.'
    Assert-Contains -Text $code -Expected 'Invoke-CheckedProcess -FilePath $pythonExe -Arguments @( ''-m'' , ''pip'' , ''wheel''' -Message 'Wheelhouse builder must build wheels through timeout-bounded pip wheel calls.'
    Assert-Contains -Text $code -Expected 'Invoke-CheckedProcess -FilePath $pythonExe -Arguments @( ''-m'' , ''pip'' , ''download''' -Message 'Wheelhouse builder must collect dependency wheels through a timeout-bounded pip download call.'
    Assert-Contains -Text $code -Expected '''--only-binary=:all:''' -Message 'Wheelhouse builder must reject sdists for public wheelhouse inputs.'
    Assert-Contains -Text $content -Expected '"pip", "check"' -Message 'Wheelhouse builder must run pip check.'
    Assert-Contains -Text $code -Expected '$pipAuditPackage = ''pip-audit==2.10.0''' -Message 'Wheelhouse builder must pin pip-audit tooling for reproducible release gates.'
    Assert-Contains -Text $code -Expected 'Invoke-CheckedProcess -FilePath $auditPython -Arguments @( ''-m'' , ''pip'' , ''--isolated'' , ''--disable-pip-version-check'' , ''install'' , $pipAuditPackage )' -Message 'pip-audit install must ignore global/user pip configuration and be timeout bounded.'
    Assert-Contains -Text $content -Expected 'packaging_tags.sys_tags()' -Message 'Wheelhouse builder must validate wheel tags against interpreter accepted tags.'
    Assert-Contains -Text $content -Expected '{module}.__file__' -Message 'Wheelhouse builder must record module import origin evidence.'
    Assert-Contains -Text $code -Expected '''--module'' , ''rook'' , ''--vision-smoke''' -Message 'Wheelhouse builder must verify the Rook install import origin.'
    Assert-Contains -Text $code -Expected '''--module'' , ''chirp'' , ''--output''' -Message 'Wheelhouse builder must verify the Chirp install import origin.'
    Assert-Contains -Text $content -Expected 'cv2' -Message 'Wheelhouse builder must run shipped vision stack import smokes.'
    Assert-Contains -Text $content -Expected 'license_provenance' -Message 'Runtime manifest must include Python and third-party package license/provenance evidence.'
    Assert-Contains -Text $content -Expected 'metadata.get("License-Expression"' -Message 'Wheel provenance collector must inspect modern wheel license metadata.'
    Assert-Contains -Text $content -Expected 'chirp_git_sha' -Message 'Manifest must include Chirp sibling repo git SHA.'
    Assert-Contains -Text $content -Expected 'chirp_source_archive_sha256' -Message 'Manifest must include Chirp source archive hash.'
    Assert-Contains -Text $content -Expected 'python-runtime-manifest.json' -Message 'Wheelhouse builder must write the runtime manifest.'
    Assert-Contains -Text $content -Expected '[int]$CommandTimeoutSeconds = 1800' -Message 'Embedded Python subprocess helpers must have a bounded default timeout.'
    Assert-Contains -Text $content -Expected 'timeout=args.command_timeout_seconds' -Message 'Embedded Python subprocess helpers must pass the configured timeout into subprocess.run.'
    Assert-Contains -Text $content -Expected 'subprocess timed out after {timeout} seconds' -Message 'Embedded Python subprocess helper timeout failures must be clear.'
    Assert-Contains -Text $code -Expected 'Require-CleanGitSource -Root $RepoRoot -Label ''Rook'' -ExcludedPathSpecs @(' -Message 'Rook clean check must be scoped to source files with generated payload paths excluded.'
    Assert-Contains -Text $content -Expected '''installer/runtime/**''' -Message 'Rook clean check must exclude generated staged runtime output.'
    Assert-Contains -Text $content -Expected '''artifacts/**''' -Message 'Rook clean check must exclude generated build artifacts.'
    Assert-Contains -Text $content -Expected 'Require-CleanGitRepo -Root $ChirpRoot -Label ''Chirp''' -Message 'Chirp clean check must remain whole-repo clean.'
    Assert-Contains -Text $content -Expected 'Get-RepoRelativePath' -Message 'Manifest artifact paths should be repo-relative or installer-relative where possible.'
}

Test-PythonRuntimeConfigIsPinned
Test-PythonRuntimeStagerExistsAndNeverRunsAtInstallTime
Test-PythonRuntimeStagerStagesRuntimeIntoTempRoots
Test-WheelhouseBuilderExists
Test-WheelhouseBuilderEnforcesReleaseContracts

Write-Host 'Python runtime packaging guard tests passed.'
