$ErrorActionPreference = 'Stop'

$TestRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestRoot)
$RuntimeConfigPath = Join-Path $RepoRoot 'installer\python-runtime\python-runtime.json'
$RuntimeStager = Join-Path $RepoRoot 'scripts\python-runtime\stage-rook-python-runtime.ps1'
$WheelhouseBuilder = Join-Path $RepoRoot 'scripts\python-runtime\build-rook-python-wheelhouse.ps1'
$WheelhouseValidator = Join-Path $RepoRoot 'scripts\validate-python-wheelhouse.ps1'
$StagedRuntimeRoot = Join-Path $RepoRoot 'installer\runtime'
$GoogleAuthVersion = '2.56.3'
$GoogleAuthWheelSha256 = '8EC438808F813AD034535000261EED1067475D229D05BBF4216E78C3F2362E53'

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
    Assert-Contains -Text $code -Expected 'New-Object System.Diagnostics.ProcessStartInfo' -Message 'Wheelhouse builder must use Diagnostics.Process for reliable timeout-bounded exit-code capture.'
    Assert-Contains -Text $content -Expected '$process.ExitCode -ne 0' -Message 'Wheelhouse builder must fail on non-zero child process exit codes.'
    Assert-NotContains -Text $code -Expected 'Start-Process' -Message 'Wheelhouse builder must not use Start-Process because -PassThru can report a blank ExitCode after WaitForExit on this host.'
    Assert-Contains -Text $code -Expected 'Invoke-CheckedProcess -FilePath $buildPythonExe -Arguments @( ''-I'' , ''-m'' , ''pip'' , ''--isolated'' , ''wheel''' -Message 'Wheelhouse builder must build wheels through timeout-bounded patched build pip calls.'
    Assert-Contains -Text $code -Expected 'Invoke-CheckedProcess -FilePath $buildPythonExe -Arguments @( ''-I'' , ''-m'' , ''pip'' , ''--isolated'' , ''download''' -Message 'Wheelhouse builder must collect dependency wheels through timeout-bounded patched build pip calls.'
    Assert-Contains -Text $code -Expected '''--only-binary=:all:''' -Message 'Wheelhouse builder must reject sdists for public wheelhouse inputs.'
    Assert-Contains -Text $content -Expected '"pip", "check"' -Message 'Wheelhouse builder must run pip check.'
    Assert-Contains -Text $code -Expected '$pipAuditPackage = ''pip-audit==2.10.0''' -Message 'Wheelhouse builder must pin pip-audit tooling for reproducible release gates.'
    Assert-Contains -Text $code -Expected 'Invoke-CheckedProcess -FilePath $auditPython -Arguments @( ''-I'' , ''-m'' , ''pip'' , ''--isolated'' , ''--disable-pip-version-check'' , ''install'' , $pipAuditPackage )' -Message 'pip-audit install must ignore global/user pip configuration and be timeout bounded.'
    Assert-Contains -Text $content -Expected '''pip==26.2.1''' -Message 'Wheelhouse builder must pin patched pip bootstrap tooling.'
    Assert-Contains -Text $content -Expected '''setuptools==83.0.0''' -Message 'Wheelhouse builder must pin patched setuptools bootstrap tooling.'
    Assert-Contains -Text $content -Expected 'requirements-bootstrap-lock.txt' -Message 'Wheelhouse builder must write a hash-locked bootstrap requirements file.'
    Assert-Contains -Text $content -Expected 'packaging_tags.sys_tags()' -Message 'Wheelhouse builder must validate wheel tags against interpreter accepted tags.'
    Assert-Contains -Text $content -Expected '{module}.__file__' -Message 'Wheelhouse builder must record module import origin evidence.'
    Assert-Contains -Text $content -Expected 'import rook.server' -Message 'Wheelhouse builder must import rook.server from the clean packaged runtime.'
    Assert-Contains -Text $code -Expected '''--module'' , ''rook'' , ''--vision-smoke''' -Message 'Wheelhouse builder must verify the Rook install import origin.'
    Assert-Contains -Text $code -Expected '''--module'' , ''chirp'' , ''--output''' -Message 'Wheelhouse builder must verify the Chirp install import origin.'
    Assert-Contains -Text $content -Expected 'cv2' -Message 'Wheelhouse builder must run shipped vision stack import smokes.'
    Assert-Contains -Text $content -Expected 'restrict_pickle' -Message 'Wheelhouse builder must verify DSPy restricted pickle cache configuration.'
    Assert-Contains -Text $content -Expected 'CVE-2025-69872' -Message 'Wheelhouse builder must document the DiskCache CVE mitigation.'
    Assert-Contains -Text $code -Expected '''--ignore-vuln'' , ''CVE-2025-69872''' -Message 'Wheelhouse builder must narrowly suppress only the documented DiskCache CVE after mitigation evidence.'
    Assert-Contains -Text $content -Expected 'security_mitigations' -Message 'Runtime manifest must include explicit security mitigation evidence.'
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
    Assert-Contains -Text $content -Expected 'manifest path is outside RepoRoot and would leak a local absolute path' -Message 'Manifest path helper must fail closed instead of writing absolute local paths.'
    Assert-NotContains -Text $content -Expected 'return ConvertTo-ForwardSlashPath -Path $targetPath' -Message 'Manifest path helper must not fall back to absolute local paths.'
}

function Test-McpDependencyIsExactlyPinned {
    $pyproject = Join-Path $RepoRoot 'mcp_server\pyproject.toml'
    $content = Get-Content -Path $pyproject -Raw

    $defaultDepsBlock = [regex]::Match($content, 'dependencies\s*=\s*\[(?s:.*?)\]')
    Assert-True -Condition $defaultDepsBlock.Success -Message 'pyproject must have project dependencies block.'
    $mcpDependencyLines = @(
        $defaultDepsBlock.Value -split "`r?`n" |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ -match '^"mcp[^\"]*",$' }
    )
    Assert-True -Condition ($mcpDependencyLines.Count -eq 1) -Message 'pyproject must declare exactly one default MCP dependency.'
    Assert-True -Condition ($mcpDependencyLines[0] -eq '"mcp==1.28.1",') -Message 'pyproject must exactly pin MCP 1.28.1.'
}

function Test-OcrDependencyIsNotDefaultRuntimeDependency {
    $pyproject = Join-Path $RepoRoot 'mcp_server\pyproject.toml'
    $content = Get-Content -Path $pyproject -Raw

    $defaultDepsBlock = [regex]::Match($content, 'dependencies\s*=\s*\[(?s:.*?)\]')
    Assert-True -Condition $defaultDepsBlock.Success -Message 'pyproject must have project dependencies block.'
    Assert-NotContains -Text $defaultDepsBlock.Value -Expected 'pytesseract' -Message 'pytesseract must not be part of default public release dependencies.'
    Assert-Contains -Text $content -Expected 'ocr = [' -Message 'pyproject must keep OCR wrapper as an optional extra if retained.'
    Assert-Contains -Text $content -Expected 'pytesseract>=0.3.10' -Message 'OCR optional extra must contain pytesseract.'
}

function Test-GoogleAuthReleaseDependencyIsExactlyPinned {
    $pyprojectPath = Join-Path $RepoRoot 'mcp_server\pyproject.toml'
    $lockPath = Join-Path $RepoRoot 'mcp_server\uv.lock'
    $pyproject = Get-Content -LiteralPath $pyprojectPath -Raw
    $uvLock = Get-Content -LiteralPath $lockPath -Raw
    $builder = Get-Content -LiteralPath $WheelhouseBuilder -Raw
    $validator = Get-Content -LiteralPath $WheelhouseValidator -Raw

    $directPins = @([regex]::Matches($pyproject, '(?m)^\s*"google-auth==2\.56\.3",\s*$'))
    Assert-True -Condition ($directPins.Count -eq 1) -Message 'Rook must declare exactly one google-auth==2.56.3 direct dependency.'

    $packageBlocks = @([regex]::Matches($uvLock, '(?ms)^\[\[package\]\]\r?\nname = "google-auth"\r?\nversion = "([^"]+)".*?(?=^\[\[package\]\]|\z)'))
    Assert-True -Condition ($packageBlocks.Count -eq 1) -Message 'uv.lock must contain exactly one google-auth package record.'
    Assert-True -Condition ($packageBlocks[0].Groups[1].Value -eq $GoogleAuthVersion) -Message 'uv.lock must resolve google-auth 2.56.3.'
    Assert-Contains -Text $packageBlocks[0].Value -Expected "hash = `"sha256:$($GoogleAuthWheelSha256.ToLowerInvariant())`"" -Message 'uv.lock must retain the admitted google-auth wheel hash.'

    Assert-Contains -Text $builder -Expected "if (Test-Path -LiteralPath `$wheelhouse) { Remove-Item -LiteralPath `$wheelhouse -Recurse -Force }" -Message 'Wheelhouse generation must begin from an exact empty payload.'
    Assert-Contains -Text $builder -Expected '''--package'', "rook-mcp==$Version", ''--output'', $lockRook' -Message 'Builder must generate the Rook lock from the sealed Rook wheel.'
    Assert-Contains -Text $builder -Expected '''--package'', ''chirp==0.1.0'', ''--output'', $lockChirp' -Message 'Builder must generate the Chirp lock from the sealed Chirp wheel.'
    Assert-Contains -Text $builder -Expected 'lines.append(f"{name}=={version} --hash=sha256:{digest}")' -Message 'Generated locks must bind each package to its staged wheel hash.'
    Assert-Contains -Text $builder -Expected 'wheels = $wheelMetadata.wheels' -Message 'The manifest must own the staged wheel inventory.'
    Assert-Contains -Text $validator -Expected '$manifest.wheelhouse.wheels' -Message 'The validator must derive its expected inventory from the manifest.'
    Assert-Contains -Text $validator -Expected '$diskWheels.Count' -Message 'The validator must report the actual manifest-reconciled wheel count.'
    Assert-NotContains -Text $validator -Expected '103 wheels' -Message 'The release guard must not freeze a historical wheel count.'
}

function Test-StagedGoogleAuthPayloadWhenPresent {
    $manifestPath = Join-Path $StagedRuntimeRoot 'python-runtime-manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        Write-Host 'Staged google-auth payload check deferred until the release payload exists.'
        return
    }

    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $wheelhouse = Join-Path $StagedRuntimeRoot 'python-wheelhouse'
    $manifestRecords = @($manifest.wheelhouse.wheels | Where-Object {
        (([string]$_.project -replace '[-_.]+', '-').ToLowerInvariant()) -eq 'google-auth'
    })
    Assert-True -Condition ($manifestRecords.Count -eq 1) -Message 'Manifest must contain exactly one google-auth wheel.'
    $record = $manifestRecords[0]
    Assert-True -Condition ([string]$record.version -eq $GoogleAuthVersion) -Message 'Manifest google-auth version mismatch.'
    Assert-True -Condition ([string]$record.sha256 -eq $GoogleAuthWheelSha256) -Message 'Manifest google-auth hash mismatch.'

    $googleWheels = @(Get-ChildItem -LiteralPath $wheelhouse -Filter 'google_auth-*.whl' -File)
    Assert-True -Condition ($googleWheels.Count -eq 1) -Message 'Wheelhouse must contain exactly one google-auth wheel version.'
    Assert-True -Condition ($googleWheels[0].Name -eq [string]$record.file) -Message 'Manifest and disk google-auth wheel names must match.'
    Assert-True -Condition ((Get-FileHash -LiteralPath $googleWheels[0].FullName -Algorithm SHA256).Hash -eq $GoogleAuthWheelSha256) -Message 'Staged google-auth wheel hash mismatch.'

    $diskWheelCount = @(Get-ChildItem -LiteralPath $wheelhouse -Filter '*.whl' -File).Count
    $manifestWheelCount = @($manifest.wheelhouse.wheels).Count
    Assert-True -Condition ($diskWheelCount -eq $manifestWheelCount) -Message 'Wheelhouse total must equal the manifest-derived wheel count.'

    foreach ($lockName in @('rook', 'chirp')) {
        $lockRelativePath = [string]$manifest.lockfiles.$lockName.path
        $lockPath = Join-Path $RepoRoot $lockRelativePath
        $lockContent = Get-Content -LiteralPath $lockPath -Raw
        $matches = @([regex]::Matches($lockContent, '(?im)^\s*google-auth==2\.56\.3\s+--hash=sha256:([0-9a-f]{64})\s*$'))
        Assert-True -Condition ($matches.Count -eq 1) -Message "$lockName lock must contain exactly one google-auth==2.56.3 record."
        Assert-True -Condition ($matches[0].Groups[1].Value.ToUpperInvariant() -eq $GoogleAuthWheelSha256) -Message "$lockName lock google-auth hash mismatch."
        Assert-True -Condition (-not [regex]::IsMatch($lockContent, '(?im)^\s*google-auth==(?!2\.56\.3\b)')) -Message "$lockName lock contains another google-auth version."
    }
}

Test-PythonRuntimeConfigIsPinned
Test-PythonRuntimeStagerExistsAndNeverRunsAtInstallTime
Test-PythonRuntimeStagerStagesRuntimeIntoTempRoots
Test-WheelhouseBuilderExists
Test-WheelhouseBuilderEnforcesReleaseContracts
Test-McpDependencyIsExactlyPinned
Test-OcrDependencyIsNotDefaultRuntimeDependency
Test-GoogleAuthReleaseDependencyIsExactlyPinned
Test-StagedGoogleAuthPayloadWhenPresent

Write-Host 'Python runtime packaging guard tests passed.'
