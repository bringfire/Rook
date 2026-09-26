"""Offline build-script controls; no real package process or index is contacted."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO = Path(__file__).resolve().parents[2]
BUILDER = REPO / "scripts/python-runtime/build-rook-python-wheelhouse.ps1"
OFFICIAL_SHA256 = "71138ADF1F4CA900CDB7D289C21B7494329F2332B6D85F0E1C42108C0384ED3E"

# Execute the actual entrypoint through lock generation, then its actual audit
# block. Only Git identity and child execution are replaced. Temporary install
# handoffs between these blocks have separate tests in test_python_runtime_install.
DRIVER = r"""
$ErrorActionPreference='Stop'
$root=$env:TEST_ROOT
$source=Get-Content -LiteralPath $env:TEST_BUILDER -Raw
if ($env:TEST_CASE -notin @('missing','mismatch','oversized')) {
    # Synthetic wheel bytes test control flow, never production wheel admission.
    $source=$source.Replace($env:OFFICIAL_SHA256,$env:FIXTURE_SHA256)
}
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseInput($source,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw 'Builder syntax failure' }
$statements=@($ast.EndBlock.Statements)
$lockStart=@($statements | Where-Object { $_ -is [System.Management.Automation.Language.AssignmentStatementAst] -and $_.Left.Extent.Text -ceq '$lockScript' })
$auditStart=@($statements | Where-Object { $_ -is [System.Management.Automation.Language.AssignmentStatementAst] -and $_.Left.Extent.Text -ceq '$auditVenv' })
$auditEnd=@($statements | Where-Object { $_ -is [System.Management.Automation.Language.AssignmentStatementAst] -and $_.Left.Extent.Text -ceq '$rookManifestVerification' })
if ($lockStart.Count -ne 1 -or $auditStart.Count -ne 1 -or $auditEnd.Count -ne 1) { throw 'Statement boundaries differ' }
$entry=$source.Substring(0,$lockStart[0].Extent.StartOffset)
$audit=$source.Substring($auditStart[0].Extent.StartOffset,$auditEnd[0].Extent.StartOffset-$auditStart[0].Extent.StartOffset)
$fake=@'
function Invoke-CheckedProcess {
    param($FilePath,$Arguments,$Label)
    $calls.Add(@{file=$FilePath; argv=@($Arguments); label=$Label})
    if ($Label -eq 'build pip version check' -and $env:TEST_CASE -eq 'wrong-version') { Fail 'pip version mismatch' }
    if ($Label -eq 'build pip offline bootstrap' -and $env:TEST_CASE -eq 'bootstrap-fails') { Fail 'offline bootstrap failed' }
    if ($Label -eq 'pip-audit Rook temp venv' -and $env:TEST_CASE -eq 'audit-fails') { Fail 'audit returned 1' }
    switch ($Label) {
        'build venv creation' {
            New-Item -ItemType Directory -Force -Path (Join-Path $Arguments[-1] 'Scripts') | Out-Null
            if ($env:TEST_CASE -eq 'substituted-input') { [IO.File]::WriteAllText($PipBootstrapWheel,'substituted after admission') }
        }
        'build pip offline bootstrap' { }
        'build pip version check' { }
        'audit pip version check' { }
        'rook-mcp wheel build' { [IO.File]::WriteAllText((Join-Path $rookWheelDir 'rook_mcp-1.5.18-py3-none-any.whl'),'rook') }
        'chirp wheel build' { [IO.File]::WriteAllText((Join-Path $chirpWheelDir 'chirp-0.1.0-py3-none-any.whl'),'chirp') }
        'hash-locked dependency wheel acquisition' {
            [IO.File]::WriteAllText((Join-Path $wheelhouse 'pip-26.2.1-py3-none-any.whl'),'fixture pip')
            [IO.File]::WriteAllText((Join-Path $wheelhouse 'setuptools-83.0.0-py3-none-any.whl'),'setuptools')
            [IO.File]::WriteAllText((Join-Path $wheelhouse 'uv-0.12.5-py3-none-win_amd64.whl'),'fixture uv')
        }
        'pip-audit venv creation' { }
        'pip-audit install' { }
        'pip-audit Rook temp venv' { }
        'pip-audit Chirp temp venv' { }
        default { throw "Unregistered process boundary: $Label" }
    }
}
'@
foreach ($fn in @($ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]},$true))) {
    if ($fn.Name -ceq 'Invoke-CheckedProcess') { $entry=$entry.Replace($fn.Extent.Text,$fake) }
    if ($fn.Name -in @('Require-CleanGitSource','Require-CleanGitRepo')) {
        $entry=$entry.Replace($fn.Extent.Text,('function '+$fn.Name+' { param($Root,$Label,$ExcludedPathSpecs) return (''1''*40) }'))
    }
}
$calls=[System.Collections.Generic.List[object]]::new()
$failure=$null; $completed=$false
try {
    . ([scriptblock]::Create($entry)) -Version '1.5.18' -RepoRoot $root -ChirpRoot (Join-Path $root 'chirp')
    $rookVerification=Join-Path $root 'verification.json'
    $chirpVerification=$rookVerification
    . ([scriptblock]::Create($audit))
    $completed=$true
} catch { $failure=$_.Exception.Message }
@{calls=@($calls); failure=$failure; completed=$completed} | ConvertTo-Json -Depth 6 -Compress
"""


def run_fixture(tmp_path, case):
    runtime = tmp_path / "installer/runtime/python/cpython-3.11.9/python.exe"
    runtime.parent.mkdir(parents=True)
    runtime.write_bytes(b"staged interpreter marker: never execute")
    config = tmp_path / "installer/python-runtime/python-runtime.json"
    config.parent.mkdir(parents=True)
    config.write_text("{}")
    # Admitted third-party inputs: only the row format is checked before the fake acquisition.
    (tmp_path / "installer/python-runtime/requirements-third-party-lock.txt").write_text(
        f"certifi==2026.7.22 --hash=sha256:{'0' * 64}\n"
    )
    chirp = tmp_path / "chirp/pyproject.toml"
    chirp.parent.mkdir()
    chirp.write_text("# fixture")
    wheel = tmp_path / "artifacts/python-bootstrap/pip-26.2.1-py3-none-any.whl"
    wheel.parent.mkdir(parents=True)
    if case != "missing":
        wheel.write_bytes(b"x" * 2097153 if case == "oversized" else b"synthetic bootstrap wheel")
    (tmp_path / "verification.json").write_text(json.dumps({
        "audit_site_packages": str(tmp_path / "site-packages"),
        "dspy_cache": {"restrict_pickle": case != "mitigation-fails", "disk_cache_dir": str(tmp_path / "cache")},
    }))
    env = os.environ | {
        "TEST_ROOT": str(tmp_path), "TEST_BUILDER": str(BUILDER), "TEST_CASE": case,
        "OFFICIAL_SHA256": OFFICIAL_SHA256,
        "FIXTURE_SHA256": hashlib.sha256(b"synthetic bootstrap wheel").hexdigest().upper(),
    }
    result = subprocess.run(
        ["C:/Program Files/PowerShell/7/pwsh.exe", "-NoProfile", "-Command", DRIVER],
        env=env, capture_output=True, text=True, timeout=30, check=True,
    )
    assert runtime.read_bytes() == b"staged interpreter marker: never execute"
    return json.loads(result.stdout)


@pytest.mark.parametrize("case", ["missing", "mismatch", "oversized"])
def test_unadmitted_bootstrap_refuses_before_any_child(tmp_path, case):
    result = run_fixture(tmp_path, case)
    assert result["failure"] and "bootstrap wheel" in result["failure"].lower()
    assert result["calls"] == []
    assert not (tmp_path / "artifacts/python-wheelhouse").exists()


@pytest.mark.parametrize("case", ["valid", "substituted-input"])
def test_all_online_operations_use_offline_bootstrapped_build_pip(tmp_path, monkeypatch, case):
    result = run_fixture(tmp_path, case)
    assert result["completed"], result
    calls = result["calls"]
    labels = [call["label"] for call in calls]
    assert labels[:3] == ["build venv creation", "build pip offline bootstrap", "build pip version check"]
    build_python = str(tmp_path / "artifacts/python-wheelhouse/build-venv/Scripts/python.exe")
    bootstrap = calls[1]
    assert bootstrap["file"] == build_python
    assert {"-I", "--isolated", "--no-index", "--no-deps"} <= set(bootstrap["argv"])
    admitted_wheel = Path(bootstrap["argv"][-1])
    assert admitted_wheel.read_bytes() == b"synthetic bootstrap wheel"
    assert admitted_wheel.name == "pip-26.2.1-py3-none-any.whl"
    assert "pip.__version__ == '26.2.1'" in calls[2]["argv"][-1]
    version_code = calls[2]["argv"][-1]
    for version in ("24.0", "26.1.2", "26.2.1"):
        with monkeypatch.context() as patch:
            patch.setitem(sys.modules, "pip", SimpleNamespace(__version__=version, __file__="fixture-pip"))
            if version == "26.2.1":
                exec(compile(version_code, "build-pip-version-check", "exec"), {})
            else:
                with pytest.raises(AssertionError, match="Build pip version differs"):
                    exec(compile(version_code, "build-pip-version-check", "exec"), {})
    online = [call for call in calls if call["label"] in {
        "rook-mcp wheel build", "chirp wheel build", "hash-locked dependency wheel acquisition",
        "pip-audit install",
    }]
    assert len(online) == 4
    for call in online:
        assert call["file"] == build_python
        assert call["argv"][:4] == ["-I", "-m", "pip", "--isolated"]
    assert "pip-audit venv creation" not in labels
    audit_check = calls[labels.index("audit pip version check")]
    assert audit_check["file"] == build_python
    assert audit_check["argv"] == calls[2]["argv"]
    assert labels[-3:] == ["pip-audit install", "pip-audit Rook temp venv", "pip-audit Chirp temp venv"]
    for call in calls[-2:]:
        assert call["file"] == str(Path(build_python).with_name("pip-audit.exe"))
        assert call["argv"][-2:] == ["--ignore-vuln", "CVE-2025-69872"]
    lock = (tmp_path / "installer/runtime/requirements-bootstrap-lock.txt").read_text(encoding="utf-8-sig")
    assert f"pip==26.2.1 --hash=sha256:{hashlib.sha256(b'fixture pip').hexdigest()}" in lock
    assert "uv==" not in lock, "uv must never enter a lock that is installed into a venv"
    tools_lock = (tmp_path / "installer/runtime/requirements-installer-tools-lock.txt").read_text(encoding="utf-8-sig")
    assert f"uv==0.12.5 --hash=sha256:{hashlib.sha256(b'fixture uv').hexdigest()}" in tools_lock


@pytest.mark.parametrize("case", ["bootstrap-fails", "wrong-version"])
def test_build_bootstrap_failure_never_falls_back_to_staged_pip(tmp_path, case):
    result = run_fixture(tmp_path, case)
    assert result["failure"]
    assert not result["completed"]
    assert {c["label"] for c in result["calls"]} <= {
        "build venv creation", "build pip offline bootstrap", "build pip version check",
    }


@pytest.mark.parametrize("case", ["audit-fails", "mitigation-fails"])
def test_audit_or_mitigation_refusal_still_stops_build(tmp_path, case):
    result = run_fixture(tmp_path, case)
    assert result["failure"]
    assert not result["completed"]
    labels = [call["label"] for call in result["calls"]]
    assert "pip-audit Chirp temp venv" not in labels
    if case == "audit-fails":
        assert labels[-1] == "pip-audit Rook temp venv"
    else:
        assert "pip-audit Rook temp venv" not in labels
