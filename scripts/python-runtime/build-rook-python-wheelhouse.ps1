param(
    [string]$Version = '1.5.10',
    [string]$RepoRoot = '',
    [string]$ChirpRoot = '',
    [string]$RuntimeRoot = '',
    [string]$OutputRoot = '',
    [string]$BuildRoot = ''
)

$ErrorActionPreference = 'Stop'

# Release contract markers used by scripts/tests/python-runtime-packaging.tests.ps1:
# pip wheel, pip download, pip check, rook.__file__, chirp.__file__

function Fail {
    param([string]$Message)
    throw "Rook Python wheelhouse build failed: $Message"
}

function Require-CleanGitRepo {
    param([string]$Root, [string]$Label)
    $head = ((& git -C $Root rev-parse HEAD 2>$null) -join '').Trim().ToLowerInvariant()
    if ($LASTEXITCODE -ne 0 -or $head -notmatch '^[0-9a-f]{40}$') {
        Fail "Could not resolve $Label git SHA"
    }
    $dirty = (& git -C $Root status --porcelain)
    if ($dirty) {
        $dirty | ForEach-Object { Write-Host $_ }
        Fail "$Label worktree is dirty"
    }
    return $head
}

function Get-Sha256 {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
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

$rookGitSha = Require-CleanGitRepo -Root $RepoRoot -Label 'Rook'
$chirpGitSha = Require-CleanGitRepo -Root $ChirpRoot -Label 'Chirp'

if (Test-Path -LiteralPath $BuildRoot) { Remove-Item -LiteralPath $BuildRoot -Recurse -Force }
New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null
$wheelhouse = Join-Path $OutputRoot 'python-wheelhouse'
if (Test-Path -LiteralPath $wheelhouse) { Remove-Item -LiteralPath $wheelhouse -Recurse -Force }
New-Item -ItemType Directory -Force -Path $wheelhouse | Out-Null

$rookWheelDir = Join-Path $BuildRoot 'rook-wheel'
$chirpWheelDir = Join-Path $BuildRoot 'chirp-wheel'
New-Item -ItemType Directory -Force -Path $rookWheelDir,$chirpWheelDir | Out-Null

& $pythonExe -m pip wheel --no-deps --wheel-dir $rookWheelDir (Join-Path $RepoRoot 'mcp_server')
if ($LASTEXITCODE -ne 0) { Fail 'rook-mcp wheel build failed' }
& $pythonExe -m pip wheel --no-deps --wheel-dir $chirpWheelDir $ChirpRoot
if ($LASTEXITCODE -ne 0) { Fail 'chirp wheel build failed' }

$rookWheel = Get-ChildItem -Path $rookWheelDir -Filter 'rook_mcp-*.whl' | Select-Object -First 1
if (-not $rookWheel) { Fail 'rook-mcp wheel was not produced' }
$chirpWheel = Get-ChildItem -Path $chirpWheelDir -Filter 'chirp-*.whl' | Select-Object -First 1
if (-not $chirpWheel) { Fail 'chirp wheel was not produced' }

Copy-Item -LiteralPath $rookWheel.FullName -Destination $wheelhouse
Copy-Item -LiteralPath $chirpWheel.FullName -Destination $wheelhouse

& $pythonExe -m pip download --dest $wheelhouse --only-binary=:all: --implementation cp --python-version 3.11 --abi cp311 --platform win_amd64 $rookWheel.FullName $chirpWheel.FullName
if ($LASTEXITCODE -ne 0) { Fail 'dependency wheel download failed' }

$sdists = @(Get-ChildItem -Path $wheelhouse -Include *.tar.gz,*.zip -File -Recurse)
if ($sdists.Count -gt 0) {
    $sdists | ForEach-Object { Write-Host "Source distribution rejected: $($_.FullName)" }
    Fail 'source distributions are not allowed in the public installer wheelhouse'
}

$lockRook = Join-Path $OutputRoot 'requirements-rook-lock.txt'
$lockChirp = Join-Path $OutputRoot 'requirements-chirp-lock.txt'
$lockScript = Join-Path $BuildRoot 'generate_hash_lock.py'
@'
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
from pathlib import Path

from pip._vendor.packaging.utils import canonicalize_name, parse_wheel_filename


def run(cmd: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
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


def freeze_env(python: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    output = run([str(python), "-m", "pip", "freeze", "--all", "--exclude-editable"])
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
    parser.add_argument("--package", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--work-dir", required=True)
    args = parser.parse_args()

    base_python = Path(args.base_python)
    wheelhouse = Path(args.wheelhouse)
    work_dir = Path(args.work_dir)
    venv_dir = work_dir / ("venv-" + args.package.replace("-", "_").replace("==", "_"))
    if venv_dir.exists():
        shutil.rmtree(venv_dir)
    run([str(base_python), "-m", "venv", str(venv_dir)])
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
        args.package,
    ])
    rows = freeze_env(venv_python)
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
    ])
    run([str(venv_python), "-m", "pip", "check"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@ | Set-Content -LiteralPath $lockScript -Encoding UTF8

& $pythonExe $lockScript --base-python $pythonExe --wheelhouse $wheelhouse --package "rook-mcp==$Version" --output $lockRook --work-dir $BuildRoot
if ($LASTEXITCODE -ne 0) { Fail 'Rook hash lock generation failed' }
& $pythonExe $lockScript --base-python $pythonExe --wheelhouse $wheelhouse --package 'chirp==0.1.0' --output $lockChirp --work-dir $BuildRoot
if ($LASTEXITCODE -ne 0) { Fail 'Chirp hash lock generation failed' }

$verificationScript = Join-Path $BuildRoot 'verify_temp_runtime_install.py'
@'
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path


def run(cmd: list[str], env: dict[str, str] | None = None) -> str:
    result = subprocess.run(cmd, text=True, capture_output=True, env=env)
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-python", required=True)
    parser.add_argument("--wheelhouse", required=True)
    parser.add_argument("--lockfile", required=True)
    parser.add_argument("--venv-dir", required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--vision-smoke", action="store_true")
    args = parser.parse_args()

    venv_dir = Path(args.venv_dir)
    if venv_dir.exists():
        shutil.rmtree(venv_dir)
    run([args.base_python, "-m", "venv", str(venv_dir)])

    venv_python = venv_dir / "Scripts" / "python.exe"
    env = clean_env()
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
    ], env=env)
    if "Looking in indexes:" in install_output:
        raise SystemExit("pip used an index during offline verification")
    if "Looking in links:" not in install_output:
        raise SystemExit("pip did not report local wheelhouse links during offline verification")

    pip_check = run([str(venv_python), "-m", "pip", "check"], env=env)
    module_expr = (
        "import json, pathlib, {module}; "
        "p = pathlib.Path({module}.__file__).resolve(); "
        "print(json.dumps({{'module': '{module}', '{module}.__file__': str(p)}}))"
    ).format(module=args.module)
    import_record = json.loads(run([str(venv_python), "-c", module_expr], env=env))
    import_file = Path(import_record[f"{args.module}.__file__"]).resolve()
    site_packages = Path(run([
        str(venv_python),
        "-c",
        "import sysconfig; print(sysconfig.get_paths()['purelib'])",
    ], env=env).strip()).resolve()
    if site_packages not in import_file.parents:
        raise SystemExit(f"{args.module} imported outside site-packages: {import_file}")

    vision = {}
    if args.vision_smoke:
        vision_expr = (
            "import cv2, PIL, numpy, skimage, json; "
            "print(json.dumps({'cv2': cv2.__file__, 'PIL': PIL.__file__, "
            "'numpy': numpy.__file__, 'skimage': skimage.__file__}))"
        )
        vision = json.loads(run([str(venv_python), "-c", vision_expr], env=env))

    Path(args.output).write_text(json.dumps({
        "venv_python": str(venv_python.resolve()),
        "site_packages": str(site_packages),
        "pip_check": pip_check.strip(),
        "pip_install_no_index": True,
        "pip_install_output_sample": install_output[:2000],
        "import_record": import_record,
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

& $pythonExe $verificationScript --base-python $pythonExe --wheelhouse $wheelhouse --lockfile $lockRook --venv-dir $rookTempVenv --module rook --vision-smoke --output $rookVerification
if ($LASTEXITCODE -ne 0) { Fail 'Rook temp install verification failed' }
& $pythonExe $verificationScript --base-python $pythonExe --wheelhouse $wheelhouse --lockfile $lockChirp --venv-dir $chirpTempVenv --module chirp --output $chirpVerification
if ($LASTEXITCODE -ne 0) { Fail 'Chirp temp install verification failed' }

$auditVenv = Join-Path $BuildRoot 'pip-audit-venv'
$pipAuditPackage = 'pip-audit==2.10.0'
& $pythonExe -m venv $auditVenv
if ($LASTEXITCODE -ne 0) { Fail 'pip-audit venv creation failed' }
$auditPython = Join-Path $auditVenv 'Scripts\python.exe'
& $auditPython -m pip install $pipAuditPackage
if ($LASTEXITCODE -ne 0) { Fail 'pip-audit install failed' }
$pipAudit = Join-Path $auditVenv 'Scripts\pip-audit.exe'
$rookVerificationObject = Get-Content -LiteralPath $rookVerification -Raw | ConvertFrom-Json
$chirpVerificationObject = Get-Content -LiteralPath $chirpVerification -Raw | ConvertFrom-Json
$rookAuditJson = Join-Path $BuildRoot 'pip-audit-rook.json'
$chirpAuditJson = Join-Path $BuildRoot 'pip-audit-chirp.json'
& $pipAudit --path $rookVerificationObject.site_packages --format json --output $rookAuditJson
if ($LASTEXITCODE -ne 0) { Fail 'pip-audit failed for Rook temp venv' }
& $pipAudit --path $chirpVerificationObject.site_packages --format json --output $chirpAuditJson
if ($LASTEXITCODE -ne 0) { Fail 'pip-audit failed for Chirp temp venv' }

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
    print(json.dumps({
        "interpreter_accepted_tags_sample": sorted(accepted_tags)[:100],
        "wheels": records,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@ | Set-Content -LiteralPath $wheelTagScript -Encoding UTF8

$wheelMetadata = (& $pythonExe $wheelTagScript --wheelhouse $wheelhouse | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0) { Fail 'wheel tag metadata collection failed' }

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
    args = parser.parse_args()
    wheelhouse = Path(args.wheelhouse)
    wheels = [metadata_for_wheel(wheel) for wheel in sorted(wheelhouse.glob("*.whl"))]
    print(json.dumps({"schema_version": 1, "third_party_wheels": wheels}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@ | Set-Content -LiteralPath $provenanceScript -Encoding UTF8

$wheelLicenseProvenance = (& $pythonExe $provenanceScript --wheelhouse $wheelhouse | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0) { Fail 'wheel license provenance collection failed' }

$sourceRoot = Join-Path $BuildRoot 'source-archives'
$rookSourceArchive = Join-Path $sourceRoot "rook-$rookGitSha.tar"
$chirpSourceArchive = Join-Path $sourceRoot "chirp-$chirpGitSha.tar"
$rookSourceSha = New-SourceArchive -Root $RepoRoot -GitSha $rookGitSha -OutPath $rookSourceArchive
$chirpSourceSha = New-SourceArchive -Root $ChirpRoot -GitSha $chirpGitSha -OutPath $chirpSourceArchive

$manifest = [ordered]@{
    schema_version = 1
    generated_utc = [DateTimeOffset]::UtcNow.ToString('o')
    release_version = $Version
    rook_git_sha = $rookGitSha
    rook_source_archive_sha256 = $rookSourceSha
    chirp_git_sha = $chirpGitSha
    chirp_source_archive_sha256 = $chirpSourceSha
    python = [ordered]@{
        version = '3.11.9'
        executable = $pythonExe
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
        path = $wheelhouse
        accepted_tag_sample = $wheelMetadata.interpreter_accepted_tags_sample
        wheels = $wheelMetadata.wheels
    }
    lockfiles = [ordered]@{
        rook = [ordered]@{ path = $lockRook; sha256 = Get-Sha256 -Path $lockRook }
        chirp = [ordered]@{ path = $lockChirp; sha256 = Get-Sha256 -Path $lockChirp }
    }
    verification = [ordered]@{
        rook = $rookVerificationObject
        chirp = $chirpVerificationObject
        pip_audit = [ordered]@{
            tool = $pipAuditPackage
            rook = [ordered]@{ path = $rookAuditJson; sha256 = Get-Sha256 -Path $rookAuditJson }
            chirp = [ordered]@{ path = $chirpAuditJson; sha256 = Get-Sha256 -Path $chirpAuditJson }
        }
    }
}

$manifestPath = Join-Path $OutputRoot 'python-runtime-manifest.json'
$manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
Write-Host "Python runtime manifest: $manifestPath"
