param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9]+\.[0-9]+\.[0-9]+$')]
    [string]$Version,
    [string]$RepoRoot = '',
    [string]$ChirpRoot = '',
    [string]$RuntimeRoot = '',
    [string]$OutputRoot = '',
    [string]$BuildRoot = '',
    [string]$PipBootstrapWheel = '',
    [string]$DependencyWheelhouse = '',
    [int]$CommandTimeoutSeconds = 1800
)

$ErrorActionPreference = 'Stop'

function Fail {
    param([string]$Message)
    throw "Rook Python wheelhouse build failed: $Message"
}

function Get-GitHeadSha {
    param([string]$Root, [string]$Label)
    $head = ((& git -C $Root rev-parse HEAD 2>$null) -join '').Trim().ToLowerInvariant()
    if ($LASTEXITCODE -ne 0 -or $head -notmatch '^[0-9a-f]{40}$') {
        Fail "Could not resolve $Label git SHA"
    }
    return $head
}

function Require-CleanGitRepo {
    param([string]$Root, [string]$Label)
    $head = Get-GitHeadSha -Root $Root -Label $Label
    $dirty = (& git -C $Root status --porcelain)
    if ($dirty) {
        $dirty | ForEach-Object { Write-Host $_ }
        Fail "$Label worktree is dirty"
    }
    return $head
}

function Require-CleanGitSource {
    param([string]$Root, [string]$Label, [string[]]$ExcludedPathSpecs = @())
    $head = Get-GitHeadSha -Root $Root -Label $Label
    $pathSpecs = @(':/')
    foreach ($pathSpec in $ExcludedPathSpecs) {
        $pathSpecs += ":(exclude)$pathSpec"
    }
    $dirty = (& git -C $Root status --porcelain --untracked-files=all -- $pathSpecs)
    if ($dirty) {
        $dirty | ForEach-Object { Write-Host $_ }
        Fail "$Label source worktree is dirty"
    }
    return $head
}

function Get-Sha256 {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

function ConvertTo-ForwardSlashPath {
    param([string]$Path)
    return $Path.Replace('\', '/')
}

function Get-RepoRelativePath {
    param([string]$Root, [string]$Path)
    $rootPath = (Resolve-Path -LiteralPath $Root).Path.TrimEnd('\') + '\'
    $targetPath = (Resolve-Path -LiteralPath $Path).Path
    $rootUri = New-Object System.Uri($rootPath)
    $targetUri = New-Object System.Uri($targetPath)
    $relativeUri = $rootUri.MakeRelativeUri($targetUri)
    $relativePath = [System.Uri]::UnescapeDataString($relativeUri.ToString()).Replace('/', '\')
    if ($relativePath -eq '.' -or $relativePath.StartsWith('..')) {
        Fail "manifest path is outside RepoRoot and would leak a local absolute path: $targetPath"
    }
    return ConvertTo-ForwardSlashPath -Path $relativePath
}

function Join-ProcessArguments {
    param([string[]]$Arguments)
    $quoted = @()
    foreach ($argument in $Arguments) {
        if ($argument -match '[\s"]') {
            $quoted += '"' + ($argument -replace '"', '\"') + '"'
        } else {
            $quoted += $argument
        }
    }
    return ($quoted -join ' ')
}

function Invoke-CheckedProcess {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$Label
    )
    $argumentList = Join-ProcessArguments -Arguments $Arguments
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $FilePath
    $startInfo.Arguments = $argumentList
    $startInfo.UseShellExecute = $false
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    try {
        $null = $process.Start()
        $timeoutMs = $CommandTimeoutSeconds * 1000
        if (-not $process.WaitForExit($timeoutMs)) {
            try { $process.Kill() } catch { }
            Fail "$Label timed out after $CommandTimeoutSeconds seconds"
        }
        if ($process.ExitCode -ne 0) {
            Fail "$Label failed with exit code $($process.ExitCode)"
        }
    }
    finally {
        $process.Dispose()
    }
}

function Get-LockedDependencyArguments {
    param([string]$RequirementsLock, [string]$Wheelhouse, [string]$DependencyWheelhouse = '')
    if (-not (Test-Path -LiteralPath $RequirementsLock -PathType Leaf)) {
        Fail "Approved dependency input lock missing: $RequirementsLock"
    }
    # This input deliberately accepts only the generated one-pin/one-hash format.
    $names = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($line in (Get-Content -LiteralPath $RequirementsLock -Encoding UTF8)) {
        $row = $line.Trim()
        if (-not $row -or $row.StartsWith('#')) { continue }
        if ($row -notmatch '^([A-Za-z0-9][A-Za-z0-9._-]*)==[A-Za-z0-9.!+_-]+ --hash=sha256:[a-fA-F0-9]{64}$') {
            Fail 'Dependency input must contain exactly pinned versions with SHA256 hashes.'
        }
        $name = $Matches[1] -replace '[-_.]+', '-'
        if (-not $names.Add($name)) { Fail 'Duplicate dependency input pin.' }
    }
    if ($names.Count -eq 0) { Fail 'Dependency input lock is empty.' }
    $arguments = @('-I', '-m', 'pip', '--isolated', '--disable-pip-version-check', '--no-cache-dir',
        'download', '--dest', $Wheelhouse, '--only-binary=:all:', '--no-deps', '--require-hashes',
        '--implementation', 'cp', '--python-version', '3.11', '--abi', 'cp311', '--platform', 'win_amd64',
        '-r', $RequirementsLock)
    if (-not [string]::IsNullOrWhiteSpace($DependencyWheelhouse)) {
        if (-not (Test-Path -LiteralPath $DependencyWheelhouse -PathType Container)) {
            Fail "Accepted dependency wheelhouse missing: $DependencyWheelhouse"
        }
        $arguments += @('--no-index', '--find-links', $DependencyWheelhouse)
    }
    return $arguments
}

function Stage-LockedDependencies {
    param([string]$PythonExe, [string]$RequirementsLock, [string]$Wheelhouse, [string]$DependencyWheelhouse = '')
    $arguments = Get-LockedDependencyArguments -RequirementsLock $RequirementsLock -Wheelhouse $Wheelhouse -DependencyWheelhouse $DependencyWheelhouse
    Invoke-CheckedProcess -FilePath $PythonExe -Arguments $arguments -Label 'hash-locked dependency wheel acquisition'
}

function Assert-DependencyCacheLocation {
    param([string]$DependencyWheelhouse, [string[]]$OutputPaths)
    if ([string]::IsNullOrWhiteSpace($DependencyWheelhouse)) { return }
    $cache = (Resolve-Path -LiteralPath $DependencyWheelhouse).Path.TrimEnd('\')
    foreach ($path in $OutputPaths) {
        $output = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($path).TrimEnd('\')
        if ($cache.Equals($output, [StringComparison]::OrdinalIgnoreCase) -or
            $cache.StartsWith($output + '\', [StringComparison]::OrdinalIgnoreCase) -or
            $output.StartsWith($cache + '\', [StringComparison]::OrdinalIgnoreCase)) {
            Fail 'Accepted dependency wheelhouse must be separate from disposable build/output paths.'
        }
    }
}

function New-SourceArchive {
    param([string]$Root, [string]$GitSha, [string]$OutPath)
    $parent = Split-Path -Parent $OutPath
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    & git -C $Root archive --format=tar --output=$OutPath $GitSha
    if ($LASTEXITCODE -ne 0) { Fail "git archive failed for $Root" }
    return Get-Sha256 -Path $OutPath
}

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}
if ([string]::IsNullOrWhiteSpace($ChirpRoot)) {
    $ChirpRoot = Join-Path (Split-Path -Parent $RepoRoot) 'Chirp'
}
if ([string]::IsNullOrWhiteSpace($RuntimeRoot)) {
    $RuntimeRoot = Join-Path $RepoRoot 'installer\runtime\python\cpython-3.11.9'
}
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $RepoRoot 'installer\runtime'
}
if ([string]::IsNullOrWhiteSpace($BuildRoot)) {
    $BuildRoot = Join-Path $RepoRoot 'artifacts\python-wheelhouse'
}
if ($CommandTimeoutSeconds -le 0) {
    Fail '-CommandTimeoutSeconds must be greater than zero'
}

# Acquire this wheel separately from the official PyPI file URL, never via old pip.
# https://pypi.org/project/pip/26.2.1/#files
if ([string]::IsNullOrWhiteSpace($PipBootstrapWheel)) {
    $PipBootstrapWheel = Join-Path $RepoRoot 'artifacts\python-bootstrap\pip-26.2.1-py3-none-any.whl'
}
if (-not (Test-Path -LiteralPath $PipBootstrapWheel -PathType Leaf)) {
    Fail "Verified pip bootstrap wheel is required before package-index access: $PipBootstrapWheel"
}
$reader = [System.IO.BinaryReader]::new([System.IO.File]::OpenRead($PipBootstrapWheel))
try { $pipBootstrapBytes = $reader.ReadBytes(2097153) } finally { $reader.Dispose() }
if ($pipBootstrapBytes.Length -gt 2097152) { Fail 'Pip bootstrap wheel exceeds 2 MiB' }
$sha = [System.Security.Cryptography.SHA256]::Create()
try { $pipBootstrapHash = [BitConverter]::ToString($sha.ComputeHash($pipBootstrapBytes)).Replace('-', '') } finally { $sha.Dispose() }
if ($pipBootstrapHash -cne '71138ADF1F4CA900CDB7D289C21B7494329F2332B6D85F0E1C42108C0384ED3E') {
    Fail 'Pip bootstrap wheel SHA256 does not match official pip 26.2.1'
}

$pythonExe = Join-Path $RuntimeRoot 'python.exe'
if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
    Fail "Private Python runtime missing. Run scripts\python-runtime\stage-rook-python-runtime.ps1 first: $pythonExe"
}
if (-not (Test-Path -LiteralPath (Join-Path $ChirpRoot 'pyproject.toml') -PathType Leaf)) {
    Fail "Chirp sibling repo missing: $ChirpRoot"
}
$runtimeConfigPath = Join-Path $RepoRoot 'installer\python-runtime\python-runtime.json'
if (-not (Test-Path -LiteralPath $runtimeConfigPath -PathType Leaf)) {
    Fail "Runtime config missing: $runtimeConfigPath"
}
$runtimeConfig = Get-Content -LiteralPath $runtimeConfigPath -Raw | ConvertFrom-Json

$rookGitSha = Require-CleanGitSource -Root $RepoRoot -Label 'Rook' -ExcludedPathSpecs @(
    'installer/runtime/**',
    'artifacts/**'
)
$chirpGitSha = Require-CleanGitRepo -Root $ChirpRoot -Label 'Chirp'

$dependencyInputLock = Join-Path $RepoRoot 'installer\python-runtime\requirements-third-party-lock.txt'
$wheelhouse = Join-Path $OutputRoot 'python-wheelhouse'
# Admit the immutable inputs before removing any previous disposable output.
$null = Get-LockedDependencyArguments -RequirementsLock $dependencyInputLock -Wheelhouse $wheelhouse -DependencyWheelhouse $DependencyWheelhouse
Assert-DependencyCacheLocation -DependencyWheelhouse $DependencyWheelhouse -OutputPaths @($BuildRoot, $wheelhouse)
$dependencyInputHash = Get-Sha256 -Path $dependencyInputLock

if (Test-Path -LiteralPath $BuildRoot) { Remove-Item -LiteralPath $BuildRoot -Recurse -Force }
New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null
if (Test-Path -LiteralPath $wheelhouse) { Remove-Item -LiteralPath $wheelhouse -Recurse -Force }
New-Item -ItemType Directory -Force -Path $wheelhouse | Out-Null

$admittedDependencyLock = Join-Path $BuildRoot 'requirements-third-party-inputs.txt'
Copy-Item -LiteralPath $dependencyInputLock -Destination $admittedDependencyLock
if ((Get-Sha256 -Path $admittedDependencyLock) -cne $dependencyInputHash) { Fail 'Dependency input lock changed during admission.' }

# Only this disposable build environment is upgraded; customer Python stays intact.
$admittedPipWheel = Join-Path $BuildRoot 'pip-26.2.1-py3-none-any.whl'
[System.IO.File]::WriteAllBytes($admittedPipWheel, $pipBootstrapBytes)
$buildVenv = Join-Path $BuildRoot 'build-venv'
Invoke-CheckedProcess -FilePath $pythonExe -Arguments @('-I', '-m', 'venv', $buildVenv) -Label 'build venv creation'
$buildPythonExe = Join-Path $buildVenv 'Scripts\python.exe'
Invoke-CheckedProcess -FilePath $buildPythonExe -Arguments @('-I', '-m', 'pip', '--isolated', 'install', '--no-index', '--no-deps', $admittedPipWheel) -Label 'build pip offline bootstrap'
$pipVersionCheck = @('-I', '-c', "import pip; assert pip.__version__ == '26.2.1', 'Build pip version differs'; print('Build pip: ' + pip.__version__ + ' at ' + pip.__file__)")
Invoke-CheckedProcess -FilePath $buildPythonExe -Arguments $pipVersionCheck -Label 'build pip version check'

Stage-LockedDependencies -PythonExe $buildPythonExe -RequirementsLock $admittedDependencyLock -Wheelhouse $wheelhouse -DependencyWheelhouse $DependencyWheelhouse

$rookWheelDir = Join-Path $BuildRoot 'rook-wheel'
$chirpWheelDir = Join-Path $BuildRoot 'chirp-wheel'
New-Item -ItemType Directory -Force -Path $rookWheelDir,$chirpWheelDir | Out-Null

Invoke-CheckedProcess -FilePath $buildPythonExe -Arguments @('-I', '-m', 'pip', '--isolated', 'wheel', '--no-deps', '--wheel-dir', $rookWheelDir, (Join-Path $RepoRoot 'mcp_server')) -Label 'rook-mcp wheel build'
Invoke-CheckedProcess -FilePath $buildPythonExe -Arguments @('-I', '-m', 'pip', '--isolated', 'wheel', '--no-deps', '--wheel-dir', $chirpWheelDir, $ChirpRoot) -Label 'chirp wheel build'

$rookWheel = Get-ChildItem -Path $rookWheelDir -Filter 'rook_mcp-*.whl' | Select-Object -First 1
if (-not $rookWheel) { Fail 'rook-mcp wheel was not produced' }
$chirpWheel = Get-ChildItem -Path $chirpWheelDir -Filter 'chirp-*.whl' | Select-Object -First 1
if (-not $chirpWheel) { Fail 'chirp wheel was not produced' }

Copy-Item -LiteralPath $rookWheel.FullName -Destination $wheelhouse
Copy-Item -LiteralPath $chirpWheel.FullName -Destination $wheelhouse

$bootstrapToolPackages = @('pip==26.2.1', 'setuptools==83.0.0')

$sdists = @(Get-ChildItem -Path $wheelhouse -Include *.tar.gz,*.zip -File -Recurse)
if ($sdists.Count -gt 0) {
    $sdists | ForEach-Object { Write-Host "Source distribution rejected: $($_.FullName)" }
    Fail 'source distributions are not allowed in the public installer wheelhouse'
}

$lockBootstrap = Join-Path $OutputRoot 'requirements-bootstrap-lock.txt'
$lockRook = Join-Path $OutputRoot 'requirements-rook-lock.txt'
$lockChirp = Join-Path $OutputRoot 'requirements-chirp-lock.txt'

$bootstrapLockLines = @(
    '# Generated by scripts/python-runtime/build-rook-python-wheelhouse.ps1',
    '# Install with --isolated --no-index --find-links python-wheelhouse --require-hashes'
)
foreach ($packageSpec in $bootstrapToolPackages) {
    $parts = $packageSpec -split '==', 2
    $packageName = $parts[0]
    $packageVersion = $parts[1]
    $packageWheel = Get-ChildItem -Path $wheelhouse -Filter "$packageName-$packageVersion-*.whl" | Select-Object -First 1
    if (-not $packageWheel) {
        Fail "bootstrap wheel was not produced for $packageSpec"
    }
    $bootstrapLockLines += "$packageName==$packageVersion --hash=sha256:$((Get-Sha256 -Path $packageWheel.FullName).ToLowerInvariant())"
}
$bootstrapLockLines | Set-Content -LiteralPath $lockBootstrap -Encoding UTF8

$lockScript = Join-Path $BuildRoot 'generate_hash_lock.py'
@'
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
from pathlib import Path

from pip._vendor.packaging.utils import canonicalize_name, parse_wheel_filename


def run(cmd: list[str], cwd: Path | None = None, *, timeout: int) -> str:
    try:
        result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        raise SystemExit(
            f"subprocess timed out after {timeout} seconds: {' '.join(cmd)}\n{stdout}{stderr}"
        )
    if result.returncode != 0:
        raise SystemExit(result.stdout + result.stderr)
    return result.stdout


def wheel_index(wheelhouse: Path) -> dict[tuple[str, str], tuple[Path, str]]:
    index: dict[tuple[str, str], tuple[Path, str]] = {}
    for wheel in sorted(wheelhouse.glob("*.whl")):
        name, version, _build, _tags = parse_wheel_filename(wheel.name)
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        index[(canonicalize_name(name), str(version))] = (wheel, digest)
    return index


def freeze_env(python: Path, timeout: int) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    output = run([str(python), "-m", "pip", "freeze", "--all", "--exclude-editable"], timeout=timeout)
    for line in output.splitlines():
        if "==" not in line:
            continue
        name, version = line.split("==", 1)
        canonical = canonicalize_name(name)
        if canonical in {"pip", "setuptools", "wheel"}:
            continue
        rows.append((canonical, version))
    return sorted(rows)


def write_lock(rows: list[tuple[str, str]], index: dict[tuple[str, str], tuple[Path, str]], output: Path) -> None:
    lines = [
        "# Generated by scripts/python-runtime/build-rook-python-wheelhouse.ps1",
        "# Install with --isolated --no-index --find-links python-wheelhouse --require-hashes",
    ]
    missing: list[str] = []
    for name, version in rows:
        key = (canonicalize_name(name), version)
        if key not in index:
            missing.append(f"{name}=={version}")
            continue
        _wheel, digest = index[key]
        lines.append(f"{name}=={version} --hash=sha256:{digest}")
    if missing:
        raise SystemExit("missing wheels for locked packages: " + ", ".join(missing))
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-python", required=True)
    parser.add_argument("--wheelhouse", required=True)
    parser.add_argument("--bootstrap-lock", required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--command-timeout-seconds", type=int, default=1800)
    args = parser.parse_args()
    if args.command_timeout_seconds <= 0:
        raise SystemExit("--command-timeout-seconds must be greater than zero")

    base_python = Path(args.base_python)
    wheelhouse = Path(args.wheelhouse)
    bootstrap_lock = Path(args.bootstrap_lock)
    work_dir = Path(args.work_dir)
    venv_dir = work_dir / ("venv-" + args.package.replace("-", "_").replace("==", "_"))
    if venv_dir.exists():
        shutil.rmtree(venv_dir)
    run([str(base_python), "-m", "venv", str(venv_dir)], timeout=args.command_timeout_seconds)
    venv_python = venv_dir / "Scripts" / "python.exe"
    run([
        str(venv_python),
        "-m",
        "pip",
        "--isolated",
        "install",
        "--no-index",
        "--find-links",
        str(wheelhouse),
        "--require-hashes",
        "-r",
        str(bootstrap_lock),
    ], timeout=args.command_timeout_seconds)
    run([
        str(venv_python),
        "-m",
        "pip",
        "--isolated",
        "install",
        "--no-index",
        "--find-links",
        str(wheelhouse),
        args.package,
    ], timeout=args.command_timeout_seconds)
    rows = freeze_env(venv_python, args.command_timeout_seconds)
    index = wheel_index(wheelhouse)
    write_lock(rows, index, Path(args.output))
    run([
        str(venv_python),
        "-m",
        "pip",
        "--isolated",
        "install",
        "--force-reinstall",
        "--no-index",
        "--find-links",
        str(wheelhouse),
        "--require-hashes",
        "-r",
        str(Path(args.output)),
    ], timeout=args.command_timeout_seconds)
    run([str(venv_python), "-m", "pip", "check"], timeout=args.command_timeout_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@ | Set-Content -LiteralPath $lockScript -Encoding UTF8

Invoke-CheckedProcess -FilePath $pythonExe -Arguments @($lockScript, '--base-python', $pythonExe, '--wheelhouse', $wheelhouse, '--bootstrap-lock', $lockBootstrap, '--package', "rook-mcp==$Version", '--output', $lockRook, '--work-dir', $BuildRoot, '--command-timeout-seconds', "$CommandTimeoutSeconds") -Label 'Rook hash lock generation'
Invoke-CheckedProcess -FilePath $pythonExe -Arguments @($lockScript, '--base-python', $pythonExe, '--wheelhouse', $wheelhouse, '--bootstrap-lock', $lockBootstrap, '--package', 'chirp==0.1.0', '--output', $lockChirp, '--work-dir', $BuildRoot, '--command-timeout-seconds', "$CommandTimeoutSeconds") -Label 'Chirp hash lock generation'

$verificationScript = Join-Path $BuildRoot 'verify_temp_runtime_install.py'
@'
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path


def run(cmd: list[str], env: dict[str, str] | None = None, *, timeout: int) -> str:
    try:
        result = subprocess.run(cmd, text=True, capture_output=True, env=env, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        raise SystemExit(
            f"subprocess timed out after {timeout} seconds: {' '.join(cmd)}\n{stdout}{stderr}"
        )
    if result.returncode != 0:
        raise SystemExit(result.stdout + result.stderr)
    return result.stdout


def clean_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    env["PIP_NO_INDEX"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["PIP_REQUIRE_VIRTUALENV"] = "1"
    return env


def configure_runtime_env(env: dict[str, str], module: str, venv_dir: Path) -> dict[str, str]:
    data_dir = venv_dir / "rook-data"
    env["ROOK_MODE"] = "release"
    env["ROOK_DATA_DIR"] = str(data_dir)
    if module == "chirp":
        chirp_home = venv_dir / "chirp-home"
        env["CHIRP_HOME"] = str(chirp_home)
        env["DSPY_CACHEDIR"] = str(chirp_home / "data" / "dspy-cache")
        env["CHIRP_DSPY_RESTRICT_PICKLE"] = "1"
    else:
        env["DSPY_CACHEDIR"] = str(data_dir / "dspy-cache")
        env["ROOK_DSPY_RESTRICT_PICKLE"] = "1"
    return env


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-python", required=True)
    parser.add_argument("--wheelhouse", required=True)
    parser.add_argument("--bootstrap-lock", required=True)
    parser.add_argument("--lockfile", required=True)
    parser.add_argument("--venv-dir", required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--vision-smoke", action="store_true")
    parser.add_argument("--command-timeout-seconds", type=int, default=1800)
    args = parser.parse_args()
    if args.command_timeout_seconds <= 0:
        raise SystemExit("--command-timeout-seconds must be greater than zero")

    venv_dir = Path(args.venv_dir)
    if venv_dir.exists():
        shutil.rmtree(venv_dir)
    run([args.base_python, "-m", "venv", str(venv_dir)], timeout=args.command_timeout_seconds)

    venv_python = venv_dir / "Scripts" / "python.exe"
    env = configure_runtime_env(clean_env(), args.module, venv_dir)
    bootstrap_output = run([
        str(venv_python),
        "-m",
        "pip",
        "--isolated",
        "install",
        "--no-index",
        "--find-links",
        args.wheelhouse,
        "--require-hashes",
        "-r",
        args.bootstrap_lock,
    ], env=env, timeout=args.command_timeout_seconds)
    if "Looking in indexes:" in bootstrap_output:
        raise SystemExit("pip used an index during offline bootstrap verification")
    if "Looking in links:" not in bootstrap_output:
        raise SystemExit("pip did not report local wheelhouse links during offline bootstrap verification")
    install_output = run([
        str(venv_python),
        "-m",
        "pip",
        "--isolated",
        "install",
        "--no-index",
        "--find-links",
        args.wheelhouse,
        "--require-hashes",
        "-r",
        args.lockfile,
    ], env=env, timeout=args.command_timeout_seconds)
    if "Looking in indexes:" in install_output:
        raise SystemExit("pip used an index during offline verification")
    if "Looking in links:" not in install_output:
        raise SystemExit("pip did not report local wheelhouse links during offline verification")

    pip_check = run([str(venv_python), "-m", "pip", "check"], env=env, timeout=args.command_timeout_seconds)
    module_expr = (
        "import json, pathlib, {module}; "
        "p = pathlib.Path({module}.__file__).resolve(); "
        "print(json.dumps({{'module': '{module}', '{module}.__file__': str(p)}}))"
    ).format(module=args.module)
    import_record = json.loads(run([str(venv_python), "-c", module_expr], env=env, timeout=args.command_timeout_seconds))
    import_file = Path(import_record[f"{args.module}.__file__"]).resolve()
    site_packages = Path(run([
        str(venv_python),
        "-c",
        "import sysconfig; print(sysconfig.get_paths()['purelib'])",
    ], env=env, timeout=args.command_timeout_seconds).strip()).resolve()
    if site_packages not in import_file.parents:
        raise SystemExit(f"{args.module} imported outside site-packages: {import_file}")
    sanitized_import_record = {
        "module": args.module,
        f"{args.module}.__file__": "<site-packages>/" + import_file.relative_to(site_packages).as_posix(),
        "origin": "site-packages",
    }

    if args.module == "rook":
        run([str(venv_python), "-c", "import rook.server"], env=env, timeout=args.command_timeout_seconds)

    dspy_cache = {}
    if args.module == "rook":
        dspy_expr = (
            "from rook.learning.dspy_config import configure_secure_dspy_cache; "
            "import json; print(json.dumps(configure_secure_dspy_cache()))"
        )
        dspy_cache = json.loads(run([str(venv_python), "-c", dspy_expr], env=env, timeout=args.command_timeout_seconds))
    elif args.module == "chirp":
        dspy_expr = (
            "from chirp.adapter import configure_secure_dspy_cache; "
            "import json; print(json.dumps(configure_secure_dspy_cache()))"
        )
        dspy_cache = json.loads(run([str(venv_python), "-c", dspy_expr], env=env, timeout=args.command_timeout_seconds))
    if dspy_cache:
        if dspy_cache.get("restrict_pickle") is not True:
            raise SystemExit(f"{args.module} DSPy cache is not restricted: {dspy_cache}")
        if not dspy_cache.get("disk_cache_dir"):
            raise SystemExit(f"{args.module} DSPy cache does not declare a disk cache dir")

    vision = {}
    if args.vision_smoke:
        vision_expr = (
            "import cv2, PIL, numpy, skimage, json; "
            "print(json.dumps({'cv2': cv2.__file__, 'PIL': PIL.__file__, "
            "'numpy': numpy.__file__, 'skimage': skimage.__file__}))"
        )
        vision_paths = json.loads(run([str(venv_python), "-c", vision_expr], env=env, timeout=args.command_timeout_seconds))
        for name, raw_path in vision_paths.items():
            resolved_path = Path(raw_path).resolve()
            if site_packages in resolved_path.parents:
                vision[name] = "<site-packages>/" + resolved_path.relative_to(site_packages).as_posix()
            else:
                vision[name] = "<outside-site-packages>"

    Path(args.output).write_text(json.dumps({
        "venv_python": "<temp-venv>/Scripts/python.exe",
        "site_packages": "<temp-venv>/Lib/site-packages",
        "audit_site_packages": str(site_packages),
        "pip_check": pip_check.strip(),
        "pip_install_no_index": True,
        "pip_install_looked_in_links": "Looking in links:" in install_output,
        "pip_install_looked_in_indexes": "Looking in indexes:" in install_output,
        "import_record": sanitized_import_record,
        "dspy_cache": dspy_cache,
        "vision_imports": vision,
    }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@ | Set-Content -LiteralPath $verificationScript -Encoding UTF8

$rookVerification = Join-Path $BuildRoot 'verification-rook.json'
$chirpVerification = Join-Path $BuildRoot 'verification-chirp.json'
$rookTempVenv = Join-Path $BuildRoot 'verify-rook-venv'
$chirpTempVenv = Join-Path $BuildRoot 'verify-chirp-venv'

Invoke-CheckedProcess -FilePath $pythonExe -Arguments @($verificationScript, '--base-python', $pythonExe, '--wheelhouse', $wheelhouse, '--bootstrap-lock', $lockBootstrap, '--lockfile', $lockRook, '--venv-dir', $rookTempVenv, '--module', 'rook', '--vision-smoke', '--output', $rookVerification, '--command-timeout-seconds', "$CommandTimeoutSeconds") -Label 'Rook temp install verification'
Invoke-CheckedProcess -FilePath $pythonExe -Arguments @($verificationScript, '--base-python', $pythonExe, '--wheelhouse', $wheelhouse, '--bootstrap-lock', $lockBootstrap, '--lockfile', $lockChirp, '--venv-dir', $chirpTempVenv, '--module', 'chirp', '--output', $chirpVerification, '--command-timeout-seconds', "$CommandTimeoutSeconds") -Label 'Chirp temp install verification'

$auditVenv = $buildVenv
$pipAuditPackage = 'pip-audit==2.10.0'
$auditPython = $buildPythonExe
Invoke-CheckedProcess -FilePath $auditPython -Arguments $pipVersionCheck -Label 'audit pip version check'
Invoke-CheckedProcess -FilePath $auditPython -Arguments @('-I', '-m', 'pip', '--isolated', '--disable-pip-version-check', 'install', $pipAuditPackage) -Label 'pip-audit install'
$pipAudit = Join-Path $auditVenv 'Scripts\pip-audit.exe'
$rookVerificationObject = Get-Content -LiteralPath $rookVerification -Raw | ConvertFrom-Json
$chirpVerificationObject = Get-Content -LiteralPath $chirpVerification -Raw | ConvertFrom-Json

function Require-DspyCacheMitigation {
    param([object]$VerificationObject, [string]$Label)
    if (-not $VerificationObject.dspy_cache) {
        Fail "$Label verification did not record DSPy cache mitigation"
    }
    if ($VerificationObject.dspy_cache.restrict_pickle -ne $true) {
        Fail "$Label verification did not enable DSPy restrict_pickle"
    }
    if ([string]::IsNullOrWhiteSpace([string]$VerificationObject.dspy_cache.disk_cache_dir)) {
        Fail "$Label verification did not record a Rook-owned DSPy disk cache directory"
    }
}

Require-DspyCacheMitigation -VerificationObject $rookVerificationObject -Label 'Rook temp venv'
Require-DspyCacheMitigation -VerificationObject $chirpVerificationObject -Label 'Chirp temp venv'

$rookAuditJson = Join-Path $BuildRoot 'pip-audit-rook.json'
$chirpAuditJson = Join-Path $BuildRoot 'pip-audit-chirp.json'
Invoke-CheckedProcess -FilePath $pipAudit -Arguments @('--path', $rookVerificationObject.audit_site_packages, '--format', 'json', '--output', $rookAuditJson, '--ignore-vuln', 'CVE-2025-69872') -Label 'pip-audit Rook temp venv'
Invoke-CheckedProcess -FilePath $pipAudit -Arguments @('--path', $chirpVerificationObject.audit_site_packages, '--format', 'json', '--output', $chirpAuditJson, '--ignore-vuln', 'CVE-2025-69872') -Label 'pip-audit Chirp temp venv'
$rookManifestVerification = $rookVerificationObject | Select-Object * -ExcludeProperty audit_site_packages
$chirpManifestVerification = $chirpVerificationObject | Select-Object * -ExcludeProperty audit_site_packages

$wheelTagScript = Join-Path $BuildRoot 'collect_wheel_metadata.py'
@'
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pip._vendor.packaging.tags as packaging_tags
from pip._vendor.packaging.utils import parse_wheel_filename


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheelhouse", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    wheelhouse = Path(args.wheelhouse)
    accepted_tags = {str(tag) for tag in packaging_tags.sys_tags()}
    records = []
    for wheel in sorted(wheelhouse.glob("*.whl")):
        name, version, _build, wheel_tags = parse_wheel_filename(wheel.name)
        tag_strings = sorted(str(tag) for tag in wheel_tags)
        if accepted_tags.isdisjoint(tag_strings):
            raise SystemExit(f"wheel is not compatible with this interpreter tag set: {wheel.name}")
        records.append({
            "file": wheel.name,
            "project": str(name),
            "version": str(version),
            "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest().upper(),
            "tags": tag_strings,
        })
    Path(args.output).write_text(json.dumps({
        "interpreter_accepted_tags_sample": sorted(accepted_tags)[:100],
        "wheels": records,
    }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@ | Set-Content -LiteralPath $wheelTagScript -Encoding UTF8

$wheelMetadataJson = Join-Path $BuildRoot 'wheel-metadata.json'
Invoke-CheckedProcess -FilePath $pythonExe -Arguments @($wheelTagScript, '--wheelhouse', $wheelhouse, '--output', $wheelMetadataJson) -Label 'wheel tag metadata collection'
$wheelMetadata = Get-Content -LiteralPath $wheelMetadataJson -Raw | ConvertFrom-Json

$provenanceScript = Join-Path $BuildRoot 'collect_license_provenance.py'
@'
from __future__ import annotations

import argparse
import email.parser
import hashlib
import json
import zipfile
from pathlib import Path


def metadata_for_wheel(wheel: Path) -> dict:
    with zipfile.ZipFile(wheel) as archive:
        metadata_name = next(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
        metadata = email.parser.Parser().parsestr(archive.read(metadata_name).decode("utf-8", "replace"))
        license_files = sorted(
            name for name in archive.namelist()
            if ".dist-info/licenses/" in name.lower()
            or name.rsplit("/", 1)[-1].lower().startswith(("license", "copying", "notice"))
        )
    return {
        "wheel_file": wheel.name,
        "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest().upper(),
        "name": metadata.get("Name", ""),
        "version": metadata.get("Version", ""),
        "summary": metadata.get("Summary", ""),
        "license": metadata.get("License", ""),
        "license_expression": metadata.get("License-Expression", ""),
        "license_files": metadata.get_all("License-File", []),
        "bundled_license_file_paths": license_files,
        "home_page": metadata.get("Home-page", ""),
        "project_urls": metadata.get_all("Project-URL", []),
        "provenance_source": "wheel dist-info/METADATA",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheelhouse", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    wheelhouse = Path(args.wheelhouse)
    wheels = [metadata_for_wheel(wheel) for wheel in sorted(wheelhouse.glob("*.whl"))]
    Path(args.output).write_text(
        json.dumps({"schema_version": 1, "third_party_wheels": wheels}, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@ | Set-Content -LiteralPath $provenanceScript -Encoding UTF8

$wheelLicenseProvenanceJson = Join-Path $BuildRoot 'wheel-license-provenance.json'
Invoke-CheckedProcess -FilePath $pythonExe -Arguments @($provenanceScript, '--wheelhouse', $wheelhouse, '--output', $wheelLicenseProvenanceJson) -Label 'wheel license provenance collection'
$wheelLicenseProvenance = Get-Content -LiteralPath $wheelLicenseProvenanceJson -Raw | ConvertFrom-Json

$sourceRoot = Join-Path $BuildRoot 'source-archives'
$rookSourceArchive = Join-Path $sourceRoot "rook-$rookGitSha.tar"
$chirpSourceArchive = Join-Path $sourceRoot "chirp-$chirpGitSha.tar"
$rookSourceSha = New-SourceArchive -Root $RepoRoot -GitSha $rookGitSha -OutPath $rookSourceArchive
$chirpSourceSha = New-SourceArchive -Root $ChirpRoot -GitSha $chirpGitSha -OutPath $chirpSourceArchive

$manifest = [ordered]@{
    schema_version = 1
    release_version = $Version
    rook_git_sha = $rookGitSha
    rook_source_archive_sha256 = $rookSourceSha
    chirp_git_sha = $chirpGitSha
    chirp_source_archive_sha256 = $chirpSourceSha
    dependency_inputs = [ordered]@{
        path = Get-RepoRelativePath -Root $RepoRoot -Path $dependencyInputLock
        sha256 = $dependencyInputHash
    }
    python = [ordered]@{
        version = '3.11.9'
        executable = Get-RepoRelativePath -Root $RepoRoot -Path $pythonExe
        abi = 'cp311'
        platform = 'win_amd64'
    }
    license_provenance = [ordered]@{
        schema_version = 1
        python_runtime = [ordered]@{
            package = $runtimeConfig.python_nuget_package
            version = $runtimeConfig.python_version
            nupkg_sha256 = $runtimeConfig.nupkg_sha256
            source_url = "https://www.nuget.org/api/v2/package/$($runtimeConfig.python_nuget_package)/$($runtimeConfig.python_version)"
            provenance_source = 'installer\python-runtime\python-runtime.json'
            license = 'Python Software Foundation License'
        }
        third_party_wheels = $wheelLicenseProvenance.third_party_wheels
    }
    wheelhouse = [ordered]@{
        path = Get-RepoRelativePath -Root $RepoRoot -Path $wheelhouse
        accepted_tag_sample = $wheelMetadata.interpreter_accepted_tags_sample
        wheels = $wheelMetadata.wheels
    }
    lockfiles = [ordered]@{
        bootstrap = [ordered]@{ path = Get-RepoRelativePath -Root $RepoRoot -Path $lockBootstrap; sha256 = Get-Sha256 -Path $lockBootstrap }
        rook = [ordered]@{ path = Get-RepoRelativePath -Root $RepoRoot -Path $lockRook; sha256 = Get-Sha256 -Path $lockRook }
        chirp = [ordered]@{ path = Get-RepoRelativePath -Root $RepoRoot -Path $lockChirp; sha256 = Get-Sha256 -Path $lockChirp }
    }
    security_mitigations = [ordered]@{
        diskcache_cve_2025_69872 = [ordered]@{
            id = 'CVE-2025-69872'
            ghsa = 'GHSA-w8v5-vhqr-4h9v'
            package = 'diskcache'
            reason = 'DSPy disk cache is configured with restrict_pickle=True and Rook-owned cache directories before Rook/Chirp runtime use.'
            audit_policy = 'pip-audit runs with --ignore-vuln CVE-2025-69872 only after temp install verification records restricted cache evidence.'
            rook = $rookManifestVerification.dspy_cache
            chirp = $chirpManifestVerification.dspy_cache
        }
    }
    verification = [ordered]@{
        rook = $rookManifestVerification
        chirp = $chirpManifestVerification
        pip_audit = [ordered]@{
            tool = $pipAuditPackage
            rook = [ordered]@{ path = Get-RepoRelativePath -Root $RepoRoot -Path $rookAuditJson; sha256 = Get-Sha256 -Path $rookAuditJson }
            chirp = [ordered]@{ path = Get-RepoRelativePath -Root $RepoRoot -Path $chirpAuditJson; sha256 = Get-Sha256 -Path $chirpAuditJson }
        }
    }
}

$manifestPath = Join-Path $OutputRoot 'python-runtime-manifest.json'
# Write BOM-less UTF-8. Windows PowerShell `Set-Content -Encoding UTF8` emits a
# UTF-8 BOM, which makes Python `json.loads(read_text(encoding="utf-8"))` throw
# "Unexpected UTF-8 BOM" on the consuming side (release smoke evidence gate).
$manifestJson = $manifest | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($manifestPath, $manifestJson, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "Python runtime manifest: $manifestPath"
