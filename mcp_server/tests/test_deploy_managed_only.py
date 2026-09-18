"""Managed-only entrypoint with disposable files and no real build/deployment."""
import json
import os
from pathlib import Path
import subprocess

import pytest

REPO = Path(__file__).resolve().parents[2]
DEPLOY = REPO / "scripts/deploy-local-testing.ps1"
RUNTIMES = ("net8.0", "net7.0", "net48")
DRIVER = r"""
$ErrorActionPreference = 'Stop'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:TEST_DEPLOY,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw 'Deployment syntax failure' }
if ($ast.ParamBlock.Parameters.Name.VariablePath.UserPath -notcontains 'ManagedOnly') { throw 'Missing ManagedOnly mode' }
foreach ($fn in $ast.EndBlock.Statements | Where-Object { $_ -is [System.Management.Automation.Language.FunctionDefinitionAst] }) {
    . ([scriptblock]::Create($fn.Extent.Text))
}
$RepoRoot=$env:TEST_ROOT
$PluginDir=Join-Path $RepoRoot 'installed/plugin'
$Configuration='Release'
$ManagedCompanionRuntimes=@('net8.0','net7.0','net48')
$ManagedOnly=$true
$NativeOnly=$PayloadOnly=$AllowRunning=$SkipBuild=$SkipChirpInstall=$UseRepoVenv=$LiveSmoke=$ManifestSmokeOnly=$false
$DevPythonRuntime=$PrimeRuntimePayload=$PythonBuildRoot=$RevitInstallDir=''
if ($env:TEST_OPTION) {
    $value=if ($env:TEST_OPTION -in @('DevPythonRuntime','PrimeRuntimePayload','PythonBuildRoot','RevitInstallDir')) { 'unused-fixture' } else { $true }
    Set-Variable -Name $env:TEST_OPTION -Value $value
}
if ($env:TEST_CASE -eq 'corrupt-copy') {
    function Copy-RequiredFile { param($Source,$Destination) Set-Content -LiteralPath $Destination -Value 'corrupt fixture copy' }
}
function Get-Process {
    Add-Content (Join-Path $RepoRoot 'calls.txt') 'rhino-check'
    $checks=@(Get-Content (Join-Path $RepoRoot 'calls.txt') | Where-Object { $_ -eq 'rhino-check' }).Count
    if ($env:TEST_CASE -eq 'running' -or ($env:TEST_CASE -eq 'started-during-build' -and $checks -gt 1)) {
        [pscustomobject]@{ProcessName='Rhino';Id=123;Path='fixture'}
    }
}
function dotnet {
    Add-Content (Join-Path $RepoRoot 'calls.txt') ('build:'+($args | ConvertTo-Json -Compress))
    $global:LASTEXITCODE=if ($env:TEST_CASE -eq 'build-failed') { 1 } else { 0 }
}
# Any escape into another deployment mode is a test failure, never a real action.
foreach ($name in @('Resolve-DeployRuntimeContract','Invoke-NativeBuild',
    'Assert-RookBimBuildPrerequisites','Get-RunningRookMcpProcesses','Deploy-PluginPayload',
    'Deploy-CompanionPayload','Register-Plugins','Sync-AppPayload','Sync-ChirpPayload',
    'Assert-PrimeRuntimePayload','Sync-ReleasePythonPayload','Invoke-PostInstallConfig')) {
    Set-Item "Function:$name" ([scriptblock]::Create("throw 'Forbidden boundary: $name'"))
}
$statements=@($ast.EndBlock.Statements)
$start=0
while ($start -lt $statements.Count -and $statements[$start].Extent.Text -cne 'Set-Location $RepoRoot') { $start++ }
if ($start -eq $statements.Count) { throw 'Entrypoint not found' }
& ([scriptblock]::Create(($statements[$start..($statements.Count-1)].Extent.Text -join "`n")))
"""


def fixture(tmp_path):
    for runtime in RUNTIMES:
        source = tmp_path / f"src/Rook/bin/Release/{runtime}"
        installed = tmp_path / f"installed/plugin/{runtime}"
        for root in (source, installed):
            root.mkdir(parents=True)
            for name in ("Rook.deps.json", "Rook.runtimeconfig.json", "Dependency.dll",
                         "runtimes/win-x64/native/WebView2Loader.dll"):
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(b"unchanged dependency")
            (root / "Rook.rhp").write_bytes(b"new companion" if root == source else b"old companion")
            (root / "Rook.pdb").write_bytes(b"new symbols" if root == source else b"old symbols")
            (root / "RookBim.dll").write_bytes(b"stale build BIM" if root == source else b"installed BIM")
        (installed / "RookChatService.json").write_bytes(b"preserved service identity")
    for name in ("plugin/RookNative.rhp", "plugin/ffmpeg/ffmpeg.exe", "app/prime/current.json",
                 "app/chirp/config", "venv/python.exe", "config/client.json"):
        file = tmp_path / "installed" / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"unrelated installed bytes")


def snapshot(tmp_path):
    return {p.relative_to(tmp_path / "installed").as_posix(): p.read_bytes()
            for p in (tmp_path / "installed").rglob("*") if p.is_file()}


def run(tmp_path, case="valid", option=""):
    env = os.environ | {"TEST_DEPLOY": str(DEPLOY), "TEST_ROOT": str(tmp_path),
                        "TEST_CASE": case, "TEST_OPTION": option}
    result = subprocess.run(["C:/Program Files/PowerShell/7/pwsh.exe", "-NoProfile", "-Command", DRIVER],
                            env=env, capture_output=True, text=True, timeout=30)
    calls = tmp_path / "calls.txt"
    return result, calls.read_text().splitlines() if calls.exists() else []


@pytest.mark.parametrize("skip", [False, True])
def test_managed_entrypoint_changes_only_companion_and_symbols(tmp_path, skip):
    fixture(tmp_path)
    before = snapshot(tmp_path)
    result, calls = run(tmp_path, option="SkipBuild" if skip else "")
    assert result.returncode == 0, result.stdout + result.stderr
    after = snapshot(tmp_path)
    expected = dict(before)
    for runtime in RUNTIMES:
        expected[f"plugin/{runtime}/Rook.rhp"] = b"new companion"
        expected[f"plugin/{runtime}/Rook.pdb"] = b"new symbols"
    assert after == expected
    builds = [json.loads(c.removeprefix("build:")) for c in calls if c.startswith("build:")]
    if skip:
        assert builds == []
    else:
        assert len(builds) == 1
        assert Path(builds[0][1]) == tmp_path / "src/Rook/Rook.csproj"
        assert builds[0][0] == "build"
        assert "--no-restore" in builds[0]
        assert "-p:RhinoPluginDir=" in builds[0]
    assert calls[0] == calls[-1] == "rhino-check"
    assert "SHA256" in result.stdout


@pytest.mark.parametrize("case", ["running", "started-during-build", "build-failed",
                                  "missing-source", "missing-installed", "changed-dependency",
                                  "missing-dependency", "changed-runtime-asset"])
def test_refusal_precedes_any_installed_write(tmp_path, case):
    fixture(tmp_path)
    source = tmp_path / "src/Rook/bin/Release/net48"
    installed = tmp_path / "installed/plugin/net48"
    if case == "missing-source":
        (source / "Rook.rhp").unlink()
    elif case == "missing-installed":
        (installed / "Rook.rhp").unlink()
    elif case == "changed-dependency":
        (source / "Dependency.dll").write_bytes(b"new incompatible dependency")
    elif case == "missing-dependency":
        (installed / "Dependency.dll").unlink()
    elif case == "changed-runtime-asset":
        (source / "runtimes/win-x64/native/WebView2Loader.dll").write_bytes(b"changed")
    before = snapshot(tmp_path)
    result, calls = run(tmp_path, case)
    assert result.returncode != 0
    expected_error = {
        "running": "Refusing plugin deploy while Rhino is running",
        "started-during-build": "Refusing plugin deploy while Rhino is running",
        "build-failed": "Managed build failed",
        "missing-source": "Managed-only requires existing build and installed companions",
        "missing-installed": "Managed-only requires existing build and installed companions",
        "changed-dependency": "Managed-only dependency differs",
        "missing-dependency": "Managed-only dependency differs",
        "changed-runtime-asset": "Managed-only dependency differs",
    }[case]
    assert expected_error in result.stderr, result.stderr
    assert snapshot(tmp_path) == before
    if case == "running":
        assert not any(c.startswith("build:") for c in calls)


@pytest.mark.parametrize("option", ["NativeOnly", "PayloadOnly", "AllowRunning", "LiveSmoke",
                                    "UseRepoVenv", "ManifestSmokeOnly", "SkipChirpInstall",
                                    "DevPythonRuntime", "PrimeRuntimePayload", "PythonBuildRoot", "RevitInstallDir"])
def test_conflicting_modes_refuse_before_build_or_copy(tmp_path, option):
    fixture(tmp_path)
    before = snapshot(tmp_path)
    result, calls = run(tmp_path, option=option)
    assert result.returncode != 0
    assert "-ManagedOnly" in result.stderr
    assert calls == []
    assert snapshot(tmp_path) == before


def test_installed_byte_mismatch_cannot_report_success(tmp_path):
    fixture(tmp_path)
    result, _ = run(tmp_path, "corrupt-copy")
    assert result.returncode != 0
    assert "Managed-only installed byte verification failed" in result.stderr
    assert "Managed-only deploy complete" not in result.stdout
    assert (tmp_path / "installed/plugin/net7.0/Rook.rhp").read_bytes() == b"old companion"


def test_existing_msbuild_autodeploy_respects_explicit_empty_location():
    from xml.etree import ElementTree
    project = ElementTree.parse(REPO / "src/Rook/Rook.csproj")
    target = project.find(".//Target[@Name='DeployToRhino']")
    assert "Exists('$(RhinoPluginDir)')" in target.attrib["Condition"]
    # Evaluate properties only: no target, build, restore or installed file copy.
    result = subprocess.run([
        "C:/Program Files/dotnet/dotnet.exe", "msbuild", str(REPO / "src/Rook/Rook.csproj"),
        "-p:Configuration=Release", "-p:TargetFramework=net8.0", "-p:RhinoPluginDir=",
        "-getProperty:RhinoPluginDir",
    ], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == ""
