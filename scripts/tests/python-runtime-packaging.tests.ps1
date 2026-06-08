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

function Test-WheelhouseBuilderExists {
    Assert-True -Condition (Test-Path $WheelhouseBuilder) -Message "Missing wheelhouse builder: $WheelhouseBuilder"
}

Test-PythonRuntimeConfigIsPinned
Test-PythonRuntimeStagerExistsAndNeverRunsAtInstallTime
Test-WheelhouseBuilderExists

Write-Host 'Python runtime packaging guard tests passed.'
