"""Selected deployment generation; no build, installed runtime or network contact."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[2]
DEPLOY = REPO / "scripts/deploy-local-testing.ps1"

DRIVER = r"""
$ErrorActionPreference='Stop'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:TEST_DEPLOY,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw 'Deployment syntax failure' }
$RepoRoot=$env:TEST_ROOT
$PythonBuildRoot=if ($env:TEST_CASE -eq 'unspecified') { '' } else { Join-Path $RepoRoot 'fresh' }
$PrimeRuntimePayload=Join-Path $RepoRoot ('runtimes/'+('A'*64))
$RuntimeContract=@{IsDev=$false}
$AllowRunning=$false
$calls=[Collections.Generic.List[object]]::new()
function git { $global:LASTEXITCODE=0; return ('1'*40) }
function Get-Process { return @() }
function Get-CimInstance { return @() }
function Invoke-FixturePython {
 param($FilePath,$Argv)
 $calls.Add(@{file=$FilePath;argv=@($Argv)})
 if ($Argv[0] -ceq '-I' -and $Argv[1] -like '*.py' -and (Test-Path -LiteralPath $Argv[1] -PathType Leaf)) {
  # The origin probe runs from a temp file (PowerShell 5.1 quoting, #576). Only the
  # executable boundary is replaced: run that actual probe file's source against a
  # fixture package, not installed Rook; its verifier has no executable code.
  $prefix="import sys; sys.path.insert(0, sys.argv[1] + '/Lib/site-packages'); "
  $probe=[IO.File]::ReadAllText($Argv[1])
  & $env:TEST_PYTHON -I -B -c ($prefix+$probe) @($Argv[2..($Argv.Count-1)])
 } elseif ($Argv[1] -eq '-m') {
  $global:LASTEXITCODE=0
 } else { throw 'Unregistered child boundary' }
}
foreach ($name in @('Get-RunningRookMcpProcesses','Assert-NoRunningFullDeployBlockers','Assert-PrimeRuntimePayload')) {
 $fn=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name},$true)
 if (-not $fn) { throw 'Required owner missing' }
 $text=$fn.Extent.Text
 if ($name -eq 'Assert-PrimeRuntimePayload') {
  foreach ($call in $fn.FindAll({param($n) $n -is [System.Management.Automation.Language.CommandAst] -and $n.CommandElements[0].Extent.Text -ceq '$verificationPython'},$true)) {
   $argsText=($call.CommandElements | Select-Object -Skip 1 | ForEach-Object {
    if ($_ -is [System.Management.Automation.Language.CommandParameterAst] -or
        ($_ -is [System.Management.Automation.Language.StringConstantExpressionAst] -and $_.StringConstantType -eq 'BareWord')) {
        "'"+$_.Extent.Text+"'"
    } else { $_.Extent.Text }
   }) -join ','
   $text=$text.Replace($call.Extent.Text,('Invoke-FixturePython -FilePath $verificationPython -Argv @('+$argsText+')'))
  }
 }
 . ([scriptblock]::Create($text))
}
# Execute the real top-level admission calls, preserving their order.
$admission=@($ast.EndBlock.Statements | Where-Object {
 $_.Extent.Text -ceq 'if (-not $RuntimeContract.IsDev) { Assert-PrimeRuntimePayload }' -or
 $_.Extent.Text -ceq 'Assert-NoRunningFullDeployBlockers'
})
if ($admission.Count -ne 2) { throw 'Deployment admission wiring differs' }
$failure=$null
try { . ([scriptblock]::Create(($admission.Extent.Text -join "`n"))) } catch { $failure=$_.Exception.Message }
@{failure=$failure;calls=@($calls);parameters=@($ast.ParamBlock.Parameters.Name.VariablePath.UserPath)} | ConvertTo-Json -Depth 5 -Compress
"""


def run_case(tmp_path, case):
    payload = tmp_path / "runtimes" / ("A" * 64)
    payload.mkdir(parents=True)
    record = {
        "installer_tool": {"name": "uv", "version": "0.12.5", "wheel": "uv.whl", "wheel_sha256": "e" * 64},
        "uv_install_offline_contract": True, "uv_cache_removed_before_checks": True,
        "freeze_matches_locks": True, "bytecode_compiled": True,
        "pip_check": "No broken requirements found.",
        "import_record": {"module": "rook", "origin": "site-packages"},
    }
    for root in (tmp_path / "fresh", tmp_path / "artifacts/python-wheelhouse"):
        venv = root / "verify-rook-venv"
        python = venv / "Scripts/python.exe"
        python.parent.mkdir(parents=True)
        python.write_bytes(b"never executed; child boundary intercepted")
        site = venv / "Lib/site-packages"
        for relative in ("rook/__init__.py", "rook/agent/__init__.py", "rook/agent/chat/__init__.py", "rook/agent/chat/prime_runtime_artifact.py"):
            path = site / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# inert fixture\n", encoding="utf8")
        (root / "verification-rook.json").write_text(json.dumps(record | {"audit_site_packages": str(site)}), encoding="utf8")
    manifest = tmp_path / "installer/runtime/python-runtime-manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"rook_git_sha": "1" * 40, "release_version": "1.5.18", "verification": {"rook": record}}), encoding="utf8")
    project = tmp_path / "mcp_server/pyproject.toml"
    project.parent.mkdir()
    project.write_text('version = "1.5.18"\n', encoding="utf8")
    fresh = tmp_path / "fresh"
    if case == "missing-python":
        (fresh / "verify-rook-venv/Scripts/python.exe").unlink()
    elif case == "missing-record":
        (fresh / "verification-rook.json").unlink()
    elif case in ("wrong-site", "inconsistent-record"):
        path = fresh / "verification-rook.json"
        changed = json.loads(path.read_text())
        if case == "wrong-site":
            changed["audit_site_packages"] = str(tmp_path / "artifacts/python-wheelhouse/verify-rook-venv/Lib/site-packages")
        else:
            changed["extra_stale_value"] = True
        path.write_text(json.dumps(changed), encoding="utf8")
    env = {k: v for k, v in os.environ.items() if k.upper() != "PYTHONPATH"} | {
        "TEST_ROOT": str(tmp_path), "TEST_DEPLOY": str(DEPLOY),
        "TEST_CASE": case, "TEST_PYTHON": sys.executable,
    }
    result = subprocess.run(["C:/Program Files/PowerShell/7/pwsh.exe", "-NoProfile", "-Command", DRIVER],
                            env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_only_selected_fresh_verifier_is_invoked(tmp_path):
    result = run_case(tmp_path, "valid")
    assert result["failure"] is None, result
    assert "PythonBuildRoot" in result["parameters"]
    assert len(result["calls"]) == 2
    for call in result["calls"]:
        assert Path(call["file"]) == tmp_path / "fresh/verify-rook-venv/Scripts/python.exe"
    probe = result["calls"][0]["argv"]
    assert str(tmp_path / "fresh/verification-rook.json") in probe
    probe_file = Path(probe[1])
    assert probe[0] == "-I" and probe_file.name.startswith("rook-origin-probe-") and probe_file.suffix == ".py"
    assert not probe_file.exists(), "the temp origin probe must be removed after it runs"
    assert result["calls"][1]["argv"][:3] == ["-I", "-m", "rook.agent.chat.prime_runtime_artifact"]


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("unspecified", "requires an explicit absolute -PythonBuildRoot"),
        ("missing-python", "Sealed wheel verification input missing"),
        ("missing-record", "Sealed wheel verification input missing"),
        # These two must be refused by the real origin probe, not by a harness error.
        ("wrong-site", "Sealed-wheel verifier origin refused."),
        ("inconsistent-record", "Sealed-wheel verifier origin refused."),
    ],
)
def test_old_environment_cannot_rescue_selected_admission(tmp_path, case, reason):
    result = run_case(tmp_path, case)
    assert result["failure"] and reason in result["failure"], result
    for call in result["calls"]:
        assert Path(call["file"]) == tmp_path / "fresh/verify-rook-venv/Scripts/python.exe"
        assert "-m" not in call["argv"], "runtime verification must not follow failed origin admission"
    if case in ("unspecified", "missing-python", "missing-record"):
        assert not result["calls"]
