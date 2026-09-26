$ErrorActionPreference = 'Stop'

if ($PSVersionTable.PSEdition -eq 'Core') {
    $windowsPowerShell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
    if (-not (Test-Path -LiteralPath $windowsPowerShell -PathType Leaf)) {
        throw "Windows PowerShell is required to run this test script, but was not found at: $windowsPowerShell"
    }

    & $windowsPowerShell -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath @args
    exit $LASTEXITCODE
}

$TestRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestRoot)
$ValidatorScript = Join-Path $RepoRoot 'scripts\validate-python-wheelhouse.ps1'
$TestVersion = '1.5.12'

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Assert-Contains {
    param([string]$Text, [string]$Expected, [string]$Message)
    $normalizedText = (($Text -replace '\s+', ' ').Trim())
    $normalizedExpected = (($Expected -replace '\s+', ' ').Trim())
    Assert-True -Condition $normalizedText.Contains($normalizedExpected) -Message "$Message`nExpected to find: $Expected`nActual output:`n$Text"
}

function Get-Sha256 {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

function Get-TestInstallerContent {
    return @'
#define PythonWheelhouseDir RepoRoot + "\installer\runtime\python-wheelhouse"
Source: "{#PythonWheelhouseDir}\*"; DestDir: "{app}\python-wheelhouse"; Components: mcp chirp; Flags: ignoreversion
Source: "{#PythonRuntimeManifest}"; DestDir: "{app}"; Components: mcp; Flags: ignoreversion
Source: "{#BootstrapLockfile}"; DestDir: "{app}"; Components: mcp chirp; Flags: ignoreversion
Source: "{#InstallerToolsLockfile}"; DestDir: "{app}"; Components: mcp chirp; Flags: ignoreversion
Source: "{#RookLockfile}"; DestDir: "{app}"; Components: mcp; Flags: ignoreversion
Source: "{#ChirpLockfile}"; DestDir: "{app}"; Components: chirp; Flags: ignoreversion
'@
}

function Build-TestManifest {
    param([object]$Payload)

    $wheelRecords = @()
    foreach ($wheel in (Get-ChildItem -LiteralPath $Payload.Wheelhouse -Filter '*.whl' -File | Sort-Object Name)) {
        if ($wheel.Name -match '^(?<proj>.+?)-(?<ver>[0-9][^-]*)-') {
            $proj = $Matches['proj']
            $ver = $Matches['ver']
        } else {
            $proj = $wheel.BaseName
            $ver = '0'
        }
        $wheelRecords += [ordered]@{
            file = $wheel.Name
            project = $proj
            version = $ver
            sha256 = (Get-Sha256 -Path $wheel.FullName)
            tags = @('py3-none-any')
        }
    }

    $manifest = [ordered]@{
        schema_version = 1
        release_version = $TestVersion
        rook_git_sha = '0123456789abcdef0123456789abcdef01234567'
        chirp_git_sha = 'fedcba9876543210fedcba9876543210fedcba98'
        python = [ordered]@{ version = '3.11.9'; abi = 'cp311'; platform = 'win_amd64' }
        wheelhouse = [ordered]@{
            path = 'installer/runtime/python-wheelhouse'
            wheels = $wheelRecords
        }
        lockfiles = [ordered]@{
            bootstrap = [ordered]@{ path = 'installer/runtime/requirements-bootstrap-lock.txt'; sha256 = (Get-Sha256 -Path $Payload.BootstrapLock) }
            installer_tools = [ordered]@{ path = 'installer/runtime/requirements-installer-tools-lock.txt'; sha256 = (Get-Sha256 -Path $Payload.InstallerToolsLock) }
            rook = [ordered]@{ path = 'installer/runtime/requirements-rook-lock.txt'; sha256 = (Get-Sha256 -Path $Payload.RookLock) }
            chirp = [ordered]@{ path = 'installer/runtime/requirements-chirp-lock.txt'; sha256 = (Get-Sha256 -Path $Payload.ChirpLock) }
        }
    }

    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Payload.Manifest -Encoding UTF8
}

function New-TestPayload {
    $root = Join-Path ([System.IO.Path]::GetTempPath()) "rook-wheelhouse-policy-$([System.Guid]::NewGuid().ToString('N'))"
    $runtime = Join-Path $root 'installer\runtime'
    $wheelhouse = Join-Path $runtime 'python-wheelhouse'
    $installerDir = Join-Path $root 'installer'
    $installer = Join-Path $installerDir 'RookSetup.iss'

    New-Item -ItemType Directory -Path $wheelhouse | Out-Null

    # Fake wheels: rook_mcp (release-coupled), chirp, and one dependency.
    Set-Content -Path (Join-Path $wheelhouse "rook_mcp-$TestVersion-py3-none-any.whl") -Value 'fake rook wheel' -Encoding ASCII
    Set-Content -Path (Join-Path $wheelhouse 'chirp-0.1.0-py3-none-any.whl') -Value 'fake chirp wheel' -Encoding ASCII
    Set-Content -Path (Join-Path $wheelhouse 'certifi-2024.1.1-py3-none-any.whl') -Value 'fake certifi wheel' -Encoding ASCII

    $bootstrapLock = Join-Path $runtime 'requirements-bootstrap-lock.txt'
    $installerToolsLock = Join-Path $runtime 'requirements-installer-tools-lock.txt'
    $rookLock = Join-Path $runtime 'requirements-rook-lock.txt'
    $chirpLock = Join-Path $runtime 'requirements-chirp-lock.txt'

    Set-Content -Path $bootstrapLock -Value "pip==26.2.1 --hash=sha256:$('0'*64)`nsetuptools==82.0.1 --hash=sha256:$('0'*64)" -Encoding UTF8
    Set-Content -Path $installerToolsLock -Value "uv==0.12.5 --hash=sha256:$('0'*64)" -Encoding UTF8
    Set-Content -Path $rookLock -Value "rook-mcp==$TestVersion --hash=sha256:$('0'*64)`ncertifi==2024.1.1 --hash=sha256:$('0'*64)" -Encoding UTF8
    Set-Content -Path $chirpLock -Value "chirp==0.1.0 --hash=sha256:$('0'*64)" -Encoding UTF8

    Set-Content -Path $installer -Value (Get-TestInstallerContent) -Encoding ASCII

    $manifest = Join-Path $runtime 'python-runtime-manifest.json'

    $payload = [pscustomobject]@{
        Root = $root
        Wheelhouse = $wheelhouse
        Manifest = $manifest
        Installer = $installer
        BootstrapLock = $bootstrapLock
        InstallerToolsLock = $installerToolsLock
        RookLock = $rookLock
        ChirpLock = $chirpLock
    }

    Build-TestManifest -Payload $payload
    return $payload
}

function Read-Manifest {
    param([object]$Payload)
    return Get-Content -LiteralPath $Payload.Manifest -Raw | ConvertFrom-Json
}

function Write-Manifest {
    param([object]$Payload, [object]$Manifest)
    $Manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Payload.Manifest -Encoding UTF8
}

function Invoke-Validator {
    param([object]$Payload)
    $previous = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = & powershell -NoProfile -ExecutionPolicy Bypass -File $ValidatorScript `
            -Version $TestVersion `
            -RepoRoot $Payload.Root `
            -WheelhouseDir $Payload.Wheelhouse `
            -ManifestPath $Payload.Manifest `
            -InstallerScriptPath $Payload.Installer 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    return [pscustomobject]@{ ExitCode = $exitCode; Text = ($output -join "`n") }
}

function Invoke-ValidationExpectPass {
    param([object]$Payload)
    $result = Invoke-Validator -Payload $Payload
    if ($result.ExitCode -ne 0) { throw "Expected validation to pass, but it failed:`n$($result.Text)" }
    return $result.Text
}

function Invoke-ValidationExpectFailure {
    param([object]$Payload)
    $result = Invoke-Validator -Payload $Payload
    if ($result.ExitCode -eq 0) { throw "Expected validation to fail, but it passed:`n$($result.Text)" }
    return $result.Text
}

function Invoke-PayloadTest {
    param([scriptblock]$Body)
    $payload = New-TestPayload
    try {
        & $Body $payload
    } finally {
        if (Test-Path -LiteralPath $payload.Root) {
            Remove-Item -LiteralPath $payload.Root -Recurse -Force
        }
    }
}

# --- Tests ----------------------------------------------------------------

function Test-ValidPayloadPasses {
    Invoke-PayloadTest {
        param($payload)
        $output = Invoke-ValidationExpectPass -Payload $payload
        Assert-Contains -Text $output -Expected 'Python wheelhouse validation passed' -Message 'Valid payload should pass.'
    }
}

function Test-StaleReleaseVersionFails {
    Invoke-PayloadTest {
        param($payload)
        $manifest = Read-Manifest -Payload $payload
        $manifest.release_version = '1.5.11'
        Write-Manifest -Payload $payload -Manifest $manifest

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected "release_version '1.5.11' does not match release version '1.5.12'" -Message 'Stale wheelhouse release_version must fail closed.'
    }
}

function Test-MissingManifestFails {
    Invoke-PayloadTest {
        param($payload)
        Remove-Item -LiteralPath $payload.Manifest -Force
        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'python-runtime-manifest.json is missing' -Message 'Missing manifest must fail closed.'
    }
}

function Test-RookWheelVersionMismatchFails {
    Invoke-PayloadTest {
        param($payload)
        # Re-stamp the rook wheel + manifest record to a prior version (keep release_version current).
        Remove-Item -LiteralPath (Join-Path $payload.Wheelhouse "rook_mcp-$TestVersion-py3-none-any.whl") -Force
        Set-Content -Path (Join-Path $payload.Wheelhouse 'rook_mcp-1.5.11-py3-none-any.whl') -Value 'fake rook wheel' -Encoding ASCII
        Build-TestManifest -Payload $payload
        $manifest = Read-Manifest -Payload $payload
        $manifest.release_version = $TestVersion
        Write-Manifest -Payload $payload -Manifest $manifest

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected "rook-mcp wheel version '1.5.11' does not match release version '1.5.12'" -Message 'rook-mcp wheel version must equal the release version.'
    }
}

function Test-WheelChecksumMismatchFails {
    Invoke-PayloadTest {
        param($payload)
        Add-Content -LiteralPath (Join-Path $payload.Wheelhouse 'certifi-2024.1.1-py3-none-any.whl') -Value 'tamper'
        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'wheel checksum mismatch' -Message 'A tampered/edited wheel must fail closed.'
    }
}

function Test-ManifestWheelMissingFromDiskFails {
    Invoke-PayloadTest {
        param($payload)
        Remove-Item -LiteralPath (Join-Path $payload.Wheelhouse 'certifi-2024.1.1-py3-none-any.whl') -Force
        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'wheel listed in manifest is missing from the wheelhouse' -Message 'A truncated wheelhouse must fail closed.'
    }
}

function Test-ExtraWheelOnDiskFails {
    Invoke-PayloadTest {
        param($payload)
        Set-Content -Path (Join-Path $payload.Wheelhouse 'rogue-9.9.9-py3-none-any.whl') -Value 'rogue wheel' -Encoding ASCII
        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'wheelhouse contains a wheel not recorded in the manifest' -Message 'A contaminated wheelhouse must fail closed.'
    }
}

function Test-SdistInWheelhouseFails {
    Invoke-PayloadTest {
        param($payload)
        Set-Content -Path (Join-Path $payload.Wheelhouse 'somepkg-1.0.0.tar.gz') -Value 'fake sdist' -Encoding ASCII
        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'source distributions are not allowed in the wheelhouse' -Message 'Source distributions must be rejected.'
    }
}

function Test-LockfileChecksumMismatchFails {
    Invoke-PayloadTest {
        param($payload)
        Add-Content -LiteralPath $payload.RookLock -Value '# drift'
        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected "lockfile 'rook' checksum mismatch" -Message 'A drifted lockfile must fail closed.'
    }
}

function Test-LockfileMissingFails {
    Invoke-PayloadTest {
        param($payload)
        Remove-Item -LiteralPath $payload.ChirpLock -Force
        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected "lockfile 'chirp' is missing" -Message 'A missing lockfile must fail closed.'
    }
}

function Test-RookLockMissingPinFails {
    Invoke-PayloadTest {
        param($payload)
        Set-Content -LiteralPath $payload.RookLock -Value "certifi==2024.1.1 --hash=sha256:$('0'*64)" -Encoding UTF8
        # Keep the manifest lockfile hash consistent so the pin check is what fires.
        $manifest = Read-Manifest -Payload $payload
        $manifest.lockfiles.rook.sha256 = (Get-Sha256 -Path $payload.RookLock)
        Write-Manifest -Payload $payload -Manifest $manifest

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'rook lockfile does not pin rook-mcp==1.5.12' -Message 'The rook lockfile must pin the release version.'
    }
}

function Test-MissingInstallerWheelhouseEntryFails {
    Invoke-PayloadTest {
        param($payload)
        $content = (Get-TestInstallerContent) -split "`r?`n" | Where-Object { $_ -notmatch 'PythonWheelhouseDir' }
        Set-Content -LiteralPath $payload.Installer -Value ($content -join "`r`n") -Encoding ASCII
        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'installer script is missing a Source entry for the python wheelhouse' -Message 'Installer must package the wheelhouse.'
    }
}

function Test-InstallerSkipIfSourceDoesNotExistFails {
    Invoke-PayloadTest {
        param($payload)
        $content = (Get-TestInstallerContent).Replace(
            'Source: "{#PythonWheelhouseDir}\*"; DestDir: "{app}\python-wheelhouse"; Components: mcp chirp; Flags: ignoreversion',
            'Source: "{#PythonWheelhouseDir}\*"; DestDir: "{app}\python-wheelhouse"; Components: mcp chirp; Flags: ignoreversion skipifsourcedoesntexist'
        )
        Set-Content -LiteralPath $payload.Installer -Value $content -Encoding ASCII
        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'must fail closed and must not use skipifsourcedoesntexist' -Message 'Wheelhouse Source entry must fail closed.'
    }
}

Test-ValidPayloadPasses
Test-StaleReleaseVersionFails
Test-MissingManifestFails
Test-RookWheelVersionMismatchFails
Test-WheelChecksumMismatchFails
Test-ManifestWheelMissingFromDiskFails
Test-ExtraWheelOnDiskFails
Test-SdistInWheelhouseFails
Test-LockfileChecksumMismatchFails
Test-LockfileMissingFails
Test-RookLockMissingPinFails
Test-MissingInstallerWheelhouseEntryFails
Test-InstallerSkipIfSourceDoesNotExistFails

Write-Host 'Python wheelhouse validation policy tests passed.'
