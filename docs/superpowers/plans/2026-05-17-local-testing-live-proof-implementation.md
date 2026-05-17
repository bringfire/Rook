# Local Testing Live Proof Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the local testing proof system defined in `docs/superpowers/specs/2026-05-17-local-testing-live-proof-design.md`.

**Architecture:** Keep `scripts/deploy-local-testing.ps1` as the authoritative deploy path, then prove the effective runtime with code imported from `%LOCALAPPDATA%/Rook/venv/Scripts/python.exe`. Add one installed-runtime Python proof module under `rook`, one PowerShell orchestrator for the five gates, and guard tests that reject repo-source fallbacks and release/local drift.

**Tech Stack:** PowerShell, Python stdlib, pytest, existing `rook.runtime_harness`, existing MCP `_call_tool_dispatch`, existing `scripts/tests/*.ps1` guard style.

---

## Source Spec

Implement from:

- `docs/superpowers/specs/2026-05-17-local-testing-live-proof-design.md`

Hard invariants:

- Local tests may be fast.
- Release-readiness tests must be installed-path, owned-process, and fail-closed.
- No test may silently fall back to repo source.
- Release-readiness performs a fresh local deploy from the current commit.
- Release-readiness uses PID-bound and port-bound owned Rhino routing.
- Chirp smoke is deterministic and does not call external LLM providers.

## File Structure

Create:

- `mcp_server/src/rook/local_testing_proof.py`
  - Installed-runtime proof CLI.
  - Gate result envelope.
  - Installed runtime verification.
  - Developer/owned live smoke implementation.
  - Owned release-readiness wrapper over `rook.runtime_harness`.

- `mcp_server/tests/test_local_testing_proof.py`
  - Unit tests for gate envelope, import-origin checks, stable labels, live smoke validation, and owned harness command construction.

- `scripts/validate-local-testing-stack.ps1`
  - Public release-readiness orchestrator.
  - Runs static guards, release non-interference, fresh local deploy, then installed AppData Python module.
  - Writes artifact logs and exits nonzero on failure.

- `scripts/tests/local-testing-stack-guards.tests.ps1`
  - Static guard tests for the orchestrator and installed-runtime module.

Modify:

- `mcp_server/src/rook/runtime_harness.py`
  - Add optional `keep_rhino_on_failure` support.
  - Add structured cleanup details needed by release-readiness artifacts without changing default behavior.

- `mcp_server/tests/test_runtime_harness.py`
  - Add tests for `keep_rhino_on_failure` and cleanup envelope behavior.

- `.agents/skills/deploy-local-testing/SKILL.md`
  - Mention the release-readiness proof command and its stronger claim boundary.

Do not modify:

- `installer/RookSetup.iss`
- release build scripts
- `.vcxproj` / `.vcxproj.filters`

## Task 1: Static Guards For The New Orchestrator

**Files:**
- Create: `scripts/tests/local-testing-stack-guards.tests.ps1`
- Create later in Task 5: `scripts/validate-local-testing-stack.ps1`
- Create later in Task 2: `mcp_server/src/rook/local_testing_proof.py`

- [ ] **Step 1: Write the failing guard test**

Create `scripts/tests/local-testing-stack-guards.tests.ps1` with this content:

```powershell
$ErrorActionPreference = 'Stop'

$TestRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestRoot)
$StackScript = Join-Path $RepoRoot 'scripts\validate-local-testing-stack.ps1'
$ProofModule = Join-Path $RepoRoot 'mcp_server\src\rook\local_testing_proof.py'
$DeployScript = Join-Path $RepoRoot 'scripts\deploy-local-testing.ps1'
$DeployGuards = Join-Path $RepoRoot 'scripts\tests\deploy-local-testing-guards.tests.ps1'
$ReleaseGuards = Join-Path $RepoRoot 'scripts\tests\release-installer-guards.tests.ps1'

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Assert-Contains {
    param([string]$Text, [string]$Expected, [string]$Message)
    Assert-True -Condition $Text.Contains($Expected) -Message $Message
}

function Assert-NotContains {
    param([string]$Text, [string]$Unexpected, [string]$Message)
    Assert-True -Condition (-not $Text.Contains($Unexpected)) -Message $Message
}

function Test-ValidateLocalTestingStackScriptContract {
    Assert-True -Condition (Test-Path $StackScript) -Message "Missing validate-local-testing-stack.ps1"
    $content = Get-Content -LiteralPath $StackScript -Raw

    Assert-Contains -Text $content -Expected '[switch]$ReleaseReadiness' -Message 'Release-readiness mode must be explicit.'
    Assert-Contains -Text $content -Expected '[switch]$KeepRhinoOnFailure' -Message 'Diagnostic keep-open mode must be explicit.'
    Assert-Contains -Text $content -Expected '$FailureLabel = ''static_guard_failed''' -Message 'Static guard failures must have a stable label.'
    Assert-Contains -Text $content -Expected '$FailureLabel = ''release_non_interference_failed''' -Message 'Release non-interference failures must have a stable label.'
    Assert-Contains -Text $content -Expected '$FailureLabel = ''local_deploy_failed''' -Message 'Local deploy failures must have a stable label.'
    Assert-Contains -Text $content -Expected '$FailureLabel = ''installed_runtime_failed''' -Message 'Installed runtime failures must have a stable label.'
    Assert-Contains -Text $content -Expected '& powershell -NoProfile -ExecutionPolicy Bypass -File $DeployGuards' -Message 'Release-readiness must run deploy guards.'
    Assert-Contains -Text $content -Expected '& powershell -NoProfile -ExecutionPolicy Bypass -File $ReleaseGuards' -Message 'Release-readiness must run release guards.'
    Assert-Contains -Text $content -Expected '& powershell -NoProfile -ExecutionPolicy Bypass -File $DeployScript' -Message 'Release-readiness must perform a fresh local deploy.'
    Assert-Contains -Text $content -Expected '-m rook.local_testing_proof owned-release-readiness' -Message 'Owned proof must run through installed rook module.'
    Assert-Contains -Text $content -Expected '$VenvPython = Join-Path $RuntimeRoot ''venv\Scripts\python.exe''' -Message 'Installed AppData venv must be the Python authority.'
    Assert-Contains -Text $content -Expected 'artifacts\local-testing' -Message 'Release-readiness must write deterministic artifacts.'
}

function Test-ProofModuleDoesNotInjectRepoSource {
    Assert-True -Condition (Test-Path $ProofModule) -Message "Missing local_testing_proof.py"
    $content = Get-Content -LiteralPath $ProofModule -Raw

    Assert-NotContains -Text $content -Unexpected 'sys.path.insert' -Message 'Installed-runtime proof must not inject repo source.'
    Assert-NotContains -Text $content -Unexpected 'mcp_server/src' -Message 'Installed-runtime proof must not hard-code repo MCP source.'
    Assert-Contains -Text $content -Expected 'rook_import_leakage' -Message 'Installed-runtime proof must reject stale rook imports.'
    Assert-Contains -Text $content -Expected 'chirp_import_leakage' -Message 'Installed-runtime proof must reject stale chirp imports.'
    Assert-Contains -Text $content -Expected 'chirp_component_compile_error' -Message 'Live proof must reject Chirp compile errors.'
    Assert-Contains -Text $content -Expected 'cleanup_failed' -Message 'Live proof must expose cleanup failures.'
    Assert-Contains -Text $content -Expected 'GateResult' -Message 'Proof module must emit machine-verifiable gate envelopes.'
}

Test-ValidateLocalTestingStackScriptContract
Test-ProofModuleDoesNotInjectRepoSource

Write-Host 'Local testing stack guard tests passed.'
```

- [ ] **Step 2: Run guard test to verify it fails**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\local-testing-stack-guards.tests.ps1
```

Expected: FAIL because `scripts\validate-local-testing-stack.ps1` and `mcp_server\src\rook\local_testing_proof.py` do not exist.

- [ ] **Step 3: Commit the failing guard test**

```powershell
git add scripts/tests/local-testing-stack-guards.tests.ps1
git commit -m "test: guard local testing proof contract"
```

## Task 2: Installed Runtime Proof Module

**Files:**
- Create: `mcp_server/src/rook/local_testing_proof.py`
- Create: `mcp_server/tests/test_local_testing_proof.py`

- [ ] **Step 1: Write failing unit tests**

Create `mcp_server/tests/test_local_testing_proof.py`:

```python
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from rook import local_testing_proof as proof


def test_gate_result_envelope_contains_required_fields(tmp_path: Path):
    result = proof.GateResult.failure(
        gate="installed_runtime",
        failure_label="rook_import_leakage",
        command=["python", "-m", "rook.local_testing_proof", "installed-runtime"],
        started_at=10.0,
        ended_at=12.5,
        stdout_path=tmp_path / "stdout.log",
        stderr_path=tmp_path / "stderr.log",
        details={"rook_file": "C:/repo/mcp_server/src/rook/__init__.py"},
    )

    payload = result.to_dict()

    assert payload["gate"] == "installed_runtime"
    assert payload["success"] is False
    assert payload["failure_label"] == "rook_import_leakage"
    assert payload["command"] == ["python", "-m", "rook.local_testing_proof", "installed-runtime"]
    assert payload["duration_seconds"] == pytest.approx(2.5)
    assert payload["stdout_path"].endswith("stdout.log")
    assert payload["stderr_path"].endswith("stderr.log")
    assert payload["details"]["rook_file"].endswith("__init__.py")
    assert payload["cleanup"] == {
        "attempted": False,
        "success": None,
        "label": None,
        "details": {},
    }


def test_verify_path_under_rejects_repo_leakage(tmp_path: Path):
    expected_root = tmp_path / "AppData" / "Local" / "Rook" / "app" / "mcp_server" / "src" / "rook"
    repo_file = tmp_path / "source" / "repos" / "Rook" / "mcp_server" / "src" / "rook" / "__init__.py"

    with pytest.raises(proof.ProofFailure) as exc:
        proof.assert_path_under(repo_file, expected_root, "rook_import_leakage")

    assert exc.value.failure_label == "rook_import_leakage"


def test_verify_chirp_origin_rejects_non_appdata_path(tmp_path: Path):
    chirp_module = SimpleNamespace(__file__=str(tmp_path / "repos" / "Chirp" / "src" / "chirp" / "__init__.py"))
    with pytest.raises(proof.ProofFailure) as exc:
        proof.verify_chirp_origin(chirp_module, tmp_path / "Rook" / "app" / "chirp")
    assert exc.value.failure_label == "chirp_import_leakage"


def test_verify_chirp_runtime_uses_installed_chirp_venv(monkeypatch, tmp_path: Path):
    chirp_root = tmp_path / "Rook" / "app" / "chirp"
    chirp_python = chirp_root / ".venv" / "Scripts" / "python.exe"
    chirp_python.parent.mkdir(parents=True)
    chirp_python.write_text("fake", encoding="utf-8")
    calls = []

    class Completed:
        returncode = 0
        stdout = json.dumps({"chirp_file": str(chirp_root / "src" / "chirp" / "__init__.py")})
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append(command)
        return Completed()

    monkeypatch.setattr(proof.subprocess, "run", fake_run)

    details = proof.verify_chirp_runtime(chirp_root)

    assert calls[0][0] == str(chirp_python)
    assert details["chirp_file"].endswith("src\\chirp\\__init__.py") or details["chirp_file"].endswith("src/chirp/__init__.py")


@pytest.mark.asyncio
async def test_live_smoke_rejects_chirp_warning(monkeypatch):
    calls = []

    async def fake_dispatch(name: str, args: dict):
        calls.append((name, args))
        if name == "rhino_ping":
            return {"success": True, "data": {"processId": 42, "port": 9001}}
        if name == "gh_status":
            return {"success": True, "data": {"ready": True}}
        if name == "chirp_create":
            return {
                "success": True,
                "data": {
                    "component_guid": "abc",
                    "warning": "compiled with warning",
                    "compilation_errors": [],
                },
            }
        raise AssertionError(name)

    monkeypatch.setattr(proof, "_call_tool_dispatch", fake_dispatch)

    with pytest.raises(proof.ProofFailure) as exc:
        await proof.run_live_smoke(port=9001, process_id=42)

    assert exc.value.failure_label == "chirp_component_warning"
    assert calls[0] == ("rhino_ping", {"port": 9001, "process_id": 42})


@pytest.mark.asyncio
async def test_live_smoke_requires_undo_success(monkeypatch):
    async def fake_dispatch(name: str, args: dict):
        if name == "rhino_ping":
            return {"success": True, "data": {"processId": 42, "port": 9001}}
        if name == "gh_status":
            return {"success": True, "data": {"ready": True}}
        if name == "chirp_create":
            return {"success": True, "data": {"component_guid": "abc", "compilation_errors": []}}
        if name == "gh_errors":
            return {"success": True, "data": {"errors": []}}
        if name == "gh_undo":
            return {"success": False, "data": "nothing to undo"}
        raise AssertionError(name)

    monkeypatch.setattr(proof, "_call_tool_dispatch", fake_dispatch)

    with pytest.raises(proof.ProofFailure) as exc:
        await proof.run_live_smoke(port=9001, process_id=42)

    assert exc.value.failure_label == "cleanup_failed"


def test_write_json_writes_gate_envelope(tmp_path: Path):
    path = tmp_path / "gate.json"
    result = proof.GateResult.success(
        gate="static_guard",
        command=["powershell", "-File", "scripts/tests/deploy-local-testing-guards.tests.ps1"],
        started_at=1.0,
        ended_at=2.0,
    )

    proof.write_json(path, result.to_dict())

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["gate"] == "static_guard"
    assert payload["success"] is True
    assert payload["failure_label"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest mcp_server/tests/test_local_testing_proof.py -q
```

Expected: FAIL with import error because `rook.local_testing_proof` does not exist.

- [ ] **Step 3: Implement `local_testing_proof.py`**

Create `mcp_server/src/rook/local_testing_proof.py`:

```python
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .bridge import rhino_request_context
from .runtime_harness import CleanupStatus, run_rhino_runtime_harness
from .runtime_paths import resolve_runtime_paths
from .server import _call_tool_dispatch


class ProofFailure(RuntimeError):
    def __init__(self, failure_label: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.failure_label = failure_label
        self.details = details or {}


@dataclass(frozen=True)
class GateResult:
    gate: str
    success: bool
    failure_label: str | None
    command: list[str]
    started_at: float
    ended_at: float
    stdout_path: Path | None = None
    stderr_path: Path | None = None
    details: dict[str, Any] = field(default_factory=dict)
    cleanup: dict[str, Any] = field(
        default_factory=lambda: {
            "attempted": False,
            "success": None,
            "label": None,
            "details": {},
        }
    )

    @classmethod
    def success_result(
        cls,
        *,
        gate: str,
        command: list[str],
        started_at: float,
        ended_at: float,
        details: dict[str, Any] | None = None,
        cleanup: dict[str, Any] | None = None,
    ) -> "GateResult":
        return cls(
            gate=gate,
            success=True,
            failure_label=None,
            command=command,
            started_at=started_at,
            ended_at=ended_at,
            details=details or {},
            cleanup=cleanup or cls._default_cleanup(),
        )

    @classmethod
    def success(cls, **kwargs) -> "GateResult":
        return cls.success_result(**kwargs)

    @classmethod
    def failure(
        cls,
        *,
        gate: str,
        failure_label: str,
        command: list[str],
        started_at: float,
        ended_at: float,
        stdout_path: Path | None = None,
        stderr_path: Path | None = None,
        details: dict[str, Any] | None = None,
        cleanup: dict[str, Any] | None = None,
    ) -> "GateResult":
        return cls(
            gate=gate,
            success=False,
            failure_label=failure_label,
            command=command,
            started_at=started_at,
            ended_at=ended_at,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            details=details or {},
            cleanup=cleanup or cls._default_cleanup(),
        )

    @staticmethod
    def _default_cleanup() -> dict[str, Any]:
        return {"attempted": False, "success": None, "label": None, "details": {}}

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "success": self.success,
            "failure_label": self.failure_label,
            "command": self.command,
            "duration_seconds": self.ended_at - self.started_at,
            "stdout_path": None if self.stdout_path is None else str(self.stdout_path),
            "stderr_path": None if self.stderr_path is None else str(self.stderr_path),
            "details": self.details,
            "cleanup": self.cleanup,
        }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _norm(path: Path | str) -> str:
    return str(Path(path).resolve()).replace("\\", "/").lower()


def assert_path_under(path: Path | str, expected_root: Path | str, failure_label: str) -> None:
    actual = _norm(path)
    expected = _norm(expected_root).rstrip("/") + "/"
    if not actual.startswith(expected):
        raise ProofFailure(
            failure_label,
            f"path is outside expected root: {path}",
            {"actual": actual, "expected_root": expected},
        )


def verify_chirp_origin(chirp_module: Any, chirp_root: Path) -> dict[str, Any]:
    chirp_file = Path(chirp_module.__file__).resolve()
    assert_path_under(chirp_file, chirp_root, "chirp_import_leakage")
    return {"chirp_file": str(chirp_file), "chirp_root": str(chirp_root)}


def verify_chirp_runtime(chirp_root: Path) -> dict[str, Any]:
    chirp_python = chirp_root / ".venv" / "Scripts" / "python.exe"
    if not chirp_python.exists():
        raise ProofFailure("chirp_import_failed", f"installed Chirp venv Python not found: {chirp_python}")
    check = (
        "import json, chirp; "
        "print(json.dumps({'chirp_file': chirp.__file__}, sort_keys=True))"
    )
    completed = subprocess.run(
        [str(chirp_python), "-c", check],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if completed.returncode != 0:
        raise ProofFailure(
            "chirp_import_failed",
            "installed Chirp import failed",
            {"stderr": completed.stderr, "returncode": completed.returncode},
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ProofFailure("chirp_import_failed", "installed Chirp import produced invalid JSON", {"stdout": completed.stdout}) from exc
    chirp_file = Path(payload["chirp_file"]).resolve()
    assert_path_under(chirp_file, chirp_root, "chirp_import_leakage")
    return {"chirp_file": str(chirp_file), "chirp_root": str(chirp_root), "chirp_python": str(chirp_python)}


def verify_installed_runtime(command: list[str]) -> GateResult:
    started = time.monotonic()
    try:
        import rook

        paths = resolve_runtime_paths()
        install_root = paths.install_root
        data_root = paths.data_root
        expected_rook_root = install_root / "mcp_server" / "src" / "rook"
        expected_chirp_root = install_root / "chirp"

        assert_path_under(Path(rook.__file__).resolve(), expected_rook_root, "rook_import_leakage")
        chirp_details = verify_chirp_runtime(expected_chirp_root)

        if paths.mode != "release":
            raise ProofFailure("runtime_path_mismatch", "ROOK_MODE did not resolve to release", {"mode": paths.mode})
        if _norm(install_root) != _norm(Path(os.environ.get("ROOK_INSTALL_ROOT", install_root))):
            raise ProofFailure("runtime_path_mismatch", "ROOK_INSTALL_ROOT mismatch")
        if _norm(data_root) != _norm(Path(os.environ.get("ROOK_DATA_DIR", data_root))):
            raise ProofFailure("runtime_path_mismatch", "ROOK_DATA_DIR mismatch")

        return GateResult.success(
            gate="installed_runtime",
            command=command,
            started_at=started,
            ended_at=time.monotonic(),
            details={
                "rook_file": str(Path(rook.__file__).resolve()),
                "install_root": str(install_root),
                "data_root": str(data_root),
                **chirp_details,
            },
        )
    except ProofFailure as exc:
        return GateResult.failure(
            gate="installed_runtime",
            failure_label=exc.failure_label,
            command=command,
            started_at=started,
            ended_at=time.monotonic(),
            details=exc.details,
        )
    except Exception as exc:
        return GateResult.failure(
            gate="installed_runtime",
            failure_label="installed_runtime_failed",
            command=command,
            started_at=started,
            ended_at=time.monotonic(),
            details={"error": str(exc)},
        )


async def run_live_smoke(*, port: int | None = None, process_id: int | None = None) -> dict[str, Any]:
    args = {}
    if port:
        args["port"] = port
    if process_id:
        args["process_id"] = process_id

    with rhino_request_context(port=port, process_id=process_id):
        ping = await _call_tool_dispatch("rhino_ping", dict(args))
        if not ping.get("success"):
            raise ProofFailure("rhino_ping_failed", "rhino_ping failed", {"rhino_ping": ping})

        status = await _call_tool_dispatch("gh_status", dict(args))
        if not status.get("success"):
            raise ProofFailure("gh_not_ready", "gh_status failed", {"gh_status": status})

        chirp = await _call_tool_dispatch(
            "chirp_create",
            {
                **args,
                "category": "classifier",
                "name": "Rook Release Readiness Smoke",
                "pins_in": [{"name": "Input", "type": "string", "optional": True}],
                "pins_out": [{"name": "Result", "type": "string"}],
                "signature": "input -> result",
                "deterministic_code": "Result = Input ?? string.Empty;",
                "x": 40,
                "y": 40,
            },
        )
        if not chirp.get("success"):
            raise ProofFailure("chirp_create_failed", "chirp_create failed", {"chirp_create": chirp})
        chirp_data = chirp.get("data") or {}
        if chirp_data.get("warning"):
            raise ProofFailure("chirp_component_warning", "chirp_create warning", {"chirp_create": chirp})
        if chirp_data.get("compilation_errors"):
            raise ProofFailure("chirp_component_compile_error", "chirp_create compilation errors", {"chirp_create": chirp})

        component_guid = chirp_data.get("component_guid")
        errors = await _call_tool_dispatch("gh_errors", dict(args))
        if not errors.get("success"):
            raise ProofFailure("gh_component_error", "gh_errors failed", {"gh_errors": errors})
        for item in (errors.get("data") or {}).get("errors", []):
            if item.get("guid") == component_guid and item.get("errors"):
                raise ProofFailure("gh_component_error", "created component has GH errors", {"gh_errors": errors})

        undo = await _call_tool_dispatch("gh_undo", dict(args))
        if not undo.get("success"):
            raise ProofFailure("cleanup_failed", "gh_undo failed", {"gh_undo": undo})

    return {"rhino_ping": ping, "gh_status": status, "chirp_create": chirp, "gh_errors": errors, "gh_undo": undo}


def live_smoke_gate(command: list[str], *, port: int | None, process_id: int | None) -> GateResult:
    started = time.monotonic()
    try:
        details = asyncio.run(run_live_smoke(port=port, process_id=process_id))
        return GateResult.success(gate="live_smoke", command=command, started_at=started, ended_at=time.monotonic(), details=details)
    except ProofFailure as exc:
        return GateResult.failure(gate="live_smoke", failure_label=exc.failure_label, command=command, started_at=started, ended_at=time.monotonic(), details=exc.details)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Installed-runtime Rook local testing proof gates.")
    sub = parser.add_subparsers(dest="command", required=True)

    installed = sub.add_parser("installed-runtime")
    installed.add_argument("--out", type=Path)

    live = sub.add_parser("live-smoke")
    live.add_argument("--out", type=Path)
    live.add_argument("--port", type=int, default=int(os.environ.get("ROOK_RHINO_PORT", "0") or "0"))
    live.add_argument("--process-id", type=int, default=int(os.environ.get("ROOK_RHINO_PROCESS_ID", "0") or "0"))

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    command = [sys.executable, "-m", "rook.local_testing_proof", *argv]
    if args.command == "installed-runtime":
        result = verify_installed_runtime(command)
    elif args.command == "live-smoke":
        result = live_smoke_gate(command, port=args.port or None, process_id=args.process_id or None)
    else:
        raise AssertionError(args.command)

    payload = result.to_dict()
    if getattr(args, "out", None):
        write_json(args.out, payload)
    print(json.dumps(payload, sort_keys=True))
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_local_testing_proof.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add mcp_server/src/rook/local_testing_proof.py mcp_server/tests/test_local_testing_proof.py
git commit -m "feat: add installed runtime proof module"
```

## Task 3: Owned Release-Readiness Harness Mode

**Files:**
- Modify: `mcp_server/src/rook/local_testing_proof.py`
- Modify: `mcp_server/src/rook/runtime_harness.py`
- Modify: `mcp_server/tests/test_local_testing_proof.py`
- Modify: `mcp_server/tests/test_runtime_harness.py`

- [ ] **Step 1: Add failing tests for owned command construction and cleanup policy**

Append to `mcp_server/tests/test_local_testing_proof.py`:

```python
def test_owned_release_readiness_uses_installed_python_for_smoke(monkeypatch, tmp_path: Path):
    calls = {}

    class FakeHarnessResult:
        success = True
        artifact_dir = tmp_path / "run"
        cleanup_status = SimpleNamespace(value="graceful_exit")
        pid = 1234
        port = 9876
        warnings = []

        def to_manifest_dict(self):
            return {"success": True, "pid": self.pid, "port": self.port}

    def fake_run_harness(**kwargs):
        calls.update(kwargs)
        return FakeHarnessResult()

    monkeypatch.setattr(proof, "run_rhino_runtime_harness", fake_run_harness)

    result = proof.owned_release_readiness_gate(
        command=["python", "-m", "rook.local_testing_proof", "owned-release-readiness"],
        rhino_exe=Path("C:/Program Files/Rhino 8/System/Rhino.exe"),
        artifact_root=tmp_path,
        keep_rhino_on_failure=False,
        readiness_timeout_seconds=1.0,
        cleanup_timeout_seconds=1.0,
    )

    assert result.success is True
    assert calls["smoke_command"] == [sys.executable, "-m", "rook.local_testing_proof", "live-smoke"]
    assert calls["smoke_kind"] == "installed-live-smoke"
    assert calls["keep_rhino_on_failure"] is False
```

Append to `mcp_server/tests/test_runtime_harness.py`:

```python
def test_runtime_harness_keep_rhino_on_failure_skips_cleanup(monkeypatch, tmp_path: Path):
    fake_process = FakeHarnessProcess(pid=4321, poll_results=[None, None])
    fake_discovery = FakeHarnessDiscovery(pid=4321, port=9921)
    cleanup_calls = []
    (tmp_path / "Rhino.exe").write_text("fake", encoding="utf-8")

    monkeypatch.setattr("rook.runtime_harness.subprocess.Popen", lambda *args, **kwargs: fake_process)
    monkeypatch.setattr("rook.runtime_harness.run_smoke_command", lambda *args, **kwargs: _smoke_result(returncode=7))
    monkeypatch.setattr("rook.runtime_harness.request_external_graceful_close", lambda *args, **kwargs: cleanup_calls.append(args) or False)
    monkeypatch.setattr("rook.runtime_harness.ping_native", lambda host, port: True)

    result = run_rhino_runtime_harness(
        rhino_exe=tmp_path / "Rhino.exe",
        artifact_root=tmp_path / "artifacts",
        smoke_command=["smoke"],
        smoke_kind="installed-live-smoke",
        discovery=fake_discovery,
        keep_rhino_on_failure=True,
    )

    assert result.success is False
    assert cleanup_calls == []
    assert result.cleanup_status == CleanupStatus.NOT_ATTEMPTED
    assert any("KeepRhinoOnFailure" in warning for warning in result.warnings)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest mcp_server/tests/test_local_testing_proof.py mcp_server/tests/test_runtime_harness.py -q
```

Expected: FAIL because `owned_release_readiness_gate` and `keep_rhino_on_failure` do not exist.

- [ ] **Step 3: Add `keep_rhino_on_failure` to `run_rhino_runtime_harness`**

Modify `mcp_server/src/rook/runtime_harness.py`:

```python
def run_rhino_runtime_harness(
    *,
    rhino_exe: Path,
    artifact_root: Path,
    smoke_command: list[str],
    smoke_kind: str = "pytest-select",
    smoke_cwd: Path | None = None,
    smoke_timeout_seconds: float | None = None,
    discovery: OwnedRhinoDiscovery | None = None,
    temp_rook_dir: Path = DEFAULT_DISCOVERY_DIR,
    readiness_timeout_seconds: float = 30.0,
    readiness_poll_seconds: float = 0.25,
    cleanup_timeout_seconds: float = 10.0,
    keep_rhino_on_failure: bool = False,
) -> RhinoHarnessResult:
```

Inside the `finally` block, before graceful cleanup, compute:

```python
should_keep_on_failure = (
    keep_rhino_on_failure
    and result.smoke is not None
    and not result.smoke.succeeded
)
if should_keep_on_failure:
    warnings.append(f"KeepRhinoOnFailure requested; leaving owned Rhino pid {pid} running for diagnostics")
```

Then skip `request_external_graceful_close(...)` when `should_keep_on_failure` is true and set `cleanup_status` to `CleanupStatus.NOT_ATTEMPTED`.

- [ ] **Step 4: Add owned release-readiness command to `local_testing_proof.py`**

Extend `build_parser()`:

```python
owned = sub.add_parser("owned-release-readiness")
owned.add_argument("--out", type=Path)
owned.add_argument("--rhino-exe", type=Path, default=Path(r"C:\Program Files\Rhino 8\System\Rhino.exe"))
owned.add_argument("--artifact-root", type=Path, required=True)
owned.add_argument("--readiness-timeout", type=float, default=60.0)
owned.add_argument("--cleanup-timeout", type=float, default=15.0)
owned.add_argument("--keep-rhino-on-failure", action="store_true")
```

Add:

```python
def _cleanup_payload(status_value: str) -> dict[str, Any]:
    return {
        "attempted": status_value != CleanupStatus.NOT_ATTEMPTED.value,
        "success": status_value == CleanupStatus.GRACEFUL_EXIT.value,
        "label": None if status_value == CleanupStatus.GRACEFUL_EXIT.value else "cleanup_failed",
        "details": {"status": status_value},
    }


def _harness_failure_label(harness_result) -> str:
    if harness_result.cleanup_status != CleanupStatus.GRACEFUL_EXIT:
        return "cleanup_failed"
    if harness_result.smoke and harness_result.smoke.returncode != 0:
        stderr = harness_result.smoke.stderr or ""
        for label in (
            "rhino_ping_failed",
            "gh_not_ready",
            "chirp_import_failed",
            "chirp_create_failed",
            "chirp_component_warning",
            "chirp_component_compile_error",
            "gh_component_error",
            "cleanup_failed",
        ):
            if label in stderr:
                return label
        return "installed_runtime_failed"
    if harness_result.pid <= 0:
        return "rhino_launch_failed"
    if harness_result.port <= 0:
        return "owned_discovery_timeout"
    return "installed_runtime_failed"


def owned_release_readiness_gate(
    *,
    command: list[str],
    rhino_exe: Path,
    artifact_root: Path,
    keep_rhino_on_failure: bool,
    readiness_timeout_seconds: float,
    cleanup_timeout_seconds: float,
) -> GateResult:
    started = time.monotonic()
    harness = run_rhino_runtime_harness(
        rhino_exe=rhino_exe,
        artifact_root=artifact_root,
        smoke_command=[sys.executable, "-m", "rook.local_testing_proof", "live-smoke"],
        smoke_kind="installed-live-smoke",
        smoke_cwd=None,
        readiness_timeout_seconds=readiness_timeout_seconds,
        cleanup_timeout_seconds=cleanup_timeout_seconds,
        keep_rhino_on_failure=keep_rhino_on_failure,
    )
    cleanup = _cleanup_payload(harness.cleanup_status.value)
    details = harness.to_manifest_dict()
    if harness.success:
        return GateResult.success(
            gate="owned_release_readiness",
            command=command,
            started_at=started,
            ended_at=time.monotonic(),
            details=details,
            cleanup=cleanup,
        )
    return GateResult.failure(
        gate="owned_release_readiness",
        failure_label=_harness_failure_label(harness),
        command=command,
        started_at=started,
        ended_at=time.monotonic(),
        details=details,
        cleanup=cleanup,
    )
```

Handle in `main()`:

```python
elif args.command == "owned-release-readiness":
    result = owned_release_readiness_gate(
        command=command,
        rhino_exe=args.rhino_exe,
        artifact_root=args.artifact_root,
        keep_rhino_on_failure=args.keep_rhino_on_failure,
        readiness_timeout_seconds=args.readiness_timeout,
        cleanup_timeout_seconds=args.cleanup_timeout,
    )
```

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_local_testing_proof.py mcp_server/tests/test_runtime_harness.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add mcp_server/src/rook/local_testing_proof.py mcp_server/src/rook/runtime_harness.py mcp_server/tests/test_local_testing_proof.py mcp_server/tests/test_runtime_harness.py
git commit -m "feat: add owned local testing proof gate"
```

## Task 4: Release-Readiness Orchestrator

**Files:**
- Create: `scripts/validate-local-testing-stack.ps1`
- Modify: `scripts/tests/local-testing-stack-guards.tests.ps1`

- [ ] **Step 1: Create orchestrator script**

Create `scripts/validate-local-testing-stack.ps1`:

```powershell
# validate-local-testing-stack.ps1
#
# Orchestrates the installed-runtime and live proof gates for local Rook testing.

[CmdletBinding()]
param(
    [switch]$ReleaseReadiness,
    [switch]$KeepRhinoOnFailure,
    [string]$RhinoExe = 'C:\Program Files\Rhino 8\System\Rhino.exe'
)

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $PSCommandPath
$RepoRoot = Split-Path -Parent $ScriptDir
$DeployScript = Join-Path $RepoRoot 'scripts\deploy-local-testing.ps1'
$DeployGuards = Join-Path $RepoRoot 'scripts\tests\deploy-local-testing-guards.tests.ps1'
$ReleaseGuards = Join-Path $RepoRoot 'scripts\tests\release-installer-guards.tests.ps1'
$StackGuards = Join-Path $RepoRoot 'scripts\tests\local-testing-stack-guards.tests.ps1'
$RuntimeRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Rook'
$InstallRoot = Join-Path $RuntimeRoot 'app'
$DataRoot = Join-Path $RuntimeRoot 'data'
$ChirpHome = Join-Path $InstallRoot 'chirp'
$VenvPython = Join-Path $RuntimeRoot 'venv\Scripts\python.exe'
$ArtifactRoot = Join-Path $RepoRoot 'artifacts\local-testing'

function New-GateArtifactDir {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $path = Join-Path $ArtifactRoot "$stamp-release-readiness"
    New-Item -ItemType Directory -Force -Path $path | Out-Null
    return $path
}

function Invoke-GateCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Gate,
        [Parameter(Mandatory = $true)][string]$FailureLabel,
        [Parameter(Mandatory = $true)][string]$ArtifactDir,
        [Parameter(Mandatory = $true)][scriptblock]$Command
    )

    $stdout = Join-Path $ArtifactDir "$Gate.stdout.log"
    $stderr = Join-Path $ArtifactDir "$Gate.stderr.log"
    $started = Get-Date
    try {
        & $Command 1> $stdout 2> $stderr
        if ($LASTEXITCODE -ne 0) {
            throw "$Gate exited with code $LASTEXITCODE"
        }
        $success = $true
        $label = $null
        $details = @{}
    } catch {
        $success = $false
        $label = $FailureLabel
        $details = @{ error = $_.Exception.Message }
    }
    $ended = Get-Date
    $payload = [ordered]@{
        gate = $Gate
        success = $success
        failure_label = $label
        command = "$Command"
        duration_seconds = ($ended - $started).TotalSeconds
        stdout_path = $stdout
        stderr_path = $stderr
        details = $details
        cleanup = @{
            attempted = $false
            success = $null
            label = $null
            details = @{}
        }
    }
    $payload | ConvertTo-Json -Depth 8 | Set-Content -Path (Join-Path $ArtifactDir "$Gate.json") -Encoding UTF8
    if (-not $success) {
        throw "$FailureLabel`: $($details.error)"
    }
}

function Assert-NoRhinoRunningForReleaseReadiness {
    $rhino = Get-Process | Where-Object { $_.ProcessName -match '^(Rhino|Rhinoceros)$' }
    if ($rhino) {
        $rhino | Select-Object ProcessName, Id, Path | Format-Table | Out-String | Write-Host
        throw 'rhino_already_running'
    }
}

function Invoke-ReleaseReadiness {
    $artifactDir = New-GateArtifactDir
    Write-Host "Artifact directory: $artifactDir"

    Invoke-GateCommand -Gate 'static_guard' -FailureLabel 'static_guard_failed' -ArtifactDir $artifactDir -Command {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $DeployGuards
        & powershell -NoProfile -ExecutionPolicy Bypass -File $StackGuards
    }

    Invoke-GateCommand -Gate 'release_non_interference' -FailureLabel 'release_non_interference_failed' -ArtifactDir $artifactDir -Command {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $ReleaseGuards
    }

    Assert-NoRhinoRunningForReleaseReadiness

    Invoke-GateCommand -Gate 'local_deploy' -FailureLabel 'local_deploy_failed' -ArtifactDir $artifactDir -Command {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $DeployScript
    }

    if (-not (Test-Path $VenvPython)) {
        throw "installed_runtime_failed: Installed venv Python not found: $VenvPython"
    }

    $env:ROOK_INSTALL_ROOT = $InstallRoot.Replace('\', '/')
    $env:ROOK_DATA_DIR = $DataRoot.Replace('\', '/')
    $env:ROOK_MODE = 'release'
    $env:CHIRP_HOME = $ChirpHome.Replace('\', '/')

    $installedRuntimeJson = Join-Path $artifactDir 'installed-runtime.json'
    & $VenvPython -m rook.local_testing_proof installed-runtime --out $installedRuntimeJson
    if ($LASTEXITCODE -ne 0) {
        throw 'installed_runtime_failed'
    }

    Assert-NoRhinoRunningForReleaseReadiness

    $ownedJson = Join-Path $artifactDir 'owned-release-readiness.json'
    $args = @(
        '-m', 'rook.local_testing_proof',
        'owned-release-readiness',
        '--out', $ownedJson,
        '--rhino-exe', $RhinoExe,
        '--artifact-root', $artifactDir
    )
    if ($KeepRhinoOnFailure) {
        $args += '--keep-rhino-on-failure'
    }
    & $VenvPython @args
    if ($LASTEXITCODE -ne 0) {
        throw "owned_release_readiness_failed; see $ownedJson"
    }

    Write-Host 'release-readiness proven'
}

if (-not $ReleaseReadiness) {
    throw 'Specify -ReleaseReadiness. No default live action is provided.'
}

Invoke-ReleaseReadiness
```

- [ ] **Step 2: Run static guard**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\local-testing-stack-guards.tests.ps1
```

Expected: PASS.

- [ ] **Step 3: Run PowerShell parser**

Run:

```powershell
powershell -NoProfile -Command "[scriptblock]::Create((Get-Content -Raw scripts\validate-local-testing-stack.ps1)) | Out-Null"
```

Expected: no output and exit code 0.

- [ ] **Step 4: Commit**

```powershell
git add scripts/validate-local-testing-stack.ps1 scripts/tests/local-testing-stack-guards.tests.ps1
git commit -m "feat: add local testing stack orchestrator"
```

## Task 5: Skill Documentation Boundary

**Files:**
- Modify: `.agents/skills/deploy-local-testing/SKILL.md`
- Modify: `scripts/tests/deploy-local-testing-guards.tests.ps1`

- [ ] **Step 1: Add failing guard assertions**

Add to `Test-DeploySkillPointsToAuthoritativeScriptAndChirpChecks` in `scripts/tests/deploy-local-testing-guards.tests.ps1`:

```powershell
Assert-Contains -Text $content -Expected 'scripts\validate-local-testing-stack.ps1 -ReleaseReadiness' -Message 'Skill must point release-readiness proof at the stack validator.'
Assert-Contains -Text $content -Expected 'Only `scripts\validate-local-testing-stack.ps1 -ReleaseReadiness` may justify the phrase release-readiness proven' -Message 'Skill must preserve strict pass/fail language.'
```

- [ ] **Step 2: Run guard to verify it fails**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
```

Expected: FAIL until the skill is updated.

- [ ] **Step 3: Update deploy-local-testing skill**

Add this section to `.agents/skills/deploy-local-testing/SKILL.md` near the existing live smoke guidance:

````markdown
## Release-Readiness Proof

For the stronger proof path, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\validate-local-testing-stack.ps1 -ReleaseReadiness
```

Only `scripts\validate-local-testing-stack.ps1 -ReleaseReadiness` may justify the phrase release-readiness proven. The ordinary deploy script can verify installed runtime and can run a developer-open live smoke, but it does not prove clean startup or owned-process routing.

Use `-KeepRhinoOnFailure` only when the user explicitly wants to preserve the owned Rhino process for diagnostics.
````

- [ ] **Step 4: Run guard**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add .agents/skills/deploy-local-testing/SKILL.md scripts/tests/deploy-local-testing-guards.tests.ps1
git commit -m "docs: document release readiness proof command"
```

## Task 6: Full Verification

**Files:**
- No new files.

- [ ] **Step 1: Run Python tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_local_testing_proof.py mcp_server/tests/test_runtime_harness.py -q
```

Expected: PASS.

- [ ] **Step 2: Run guard tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\local-testing-stack-guards.tests.ps1
```

Expected: all PASS.

- [ ] **Step 3: Run parser and compile checks**

Run:

```powershell
powershell -NoProfile -Command "[scriptblock]::Create((Get-Content -Raw scripts\deploy-local-testing.ps1)) | Out-Null"
powershell -NoProfile -Command "[scriptblock]::Create((Get-Content -Raw scripts\validate-local-testing-stack.ps1)) | Out-Null"
python -m py_compile installer/post_install.py mcp_server/src/rook/local_testing_proof.py mcp_server/src/rook/runtime_harness.py
```

Expected: all commands exit 0.

- [ ] **Step 4: Run installed-runtime deploy verification**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -SkipBuild
```

Expected: PASS. This verifies installed AppData runtime, Chirp import, MCP configs, and chat manifest. It does not claim live capability.

- [ ] **Step 5: Run developer-open live smoke only if Rhino/GH is open**

Run only after a full deploy and Rhino restart:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -PayloadOnly -AllowRunning -LiveSmoke
```

Expected: PASS if Rhino/GH is open and RookNative loaded. Report as "developer-open live smoke passed."

- [ ] **Step 6: Run release-readiness proof**

Close all Rhino instances first.

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\validate-local-testing-stack.ps1 -ReleaseReadiness
```

Expected:

- static guards pass;
- release non-interference passes;
- fresh local deploy passes;
- installed runtime passes from AppData venv;
- owned Rhino launches;
- live smoke passes against owned PID/port;
- owned Rhino cleanup succeeds;
- output includes `release-readiness proven`.

- [ ] **Step 7: Run diff hygiene**

Run:

```powershell
git diff --check
git status --short
```

Expected: `git diff --check` clean. `git status --short` shows only intentional committed or staged changes.

## Self-Review Checklist

- Static Guard Gate: Task 1, Task 4, Task 6.
- Installed Runtime Gate: Task 2, Task 4, Task 6.
- Developer-Open Live Smoke Gate: Task 2, Task 6.
- Owned Rhino Release-Readiness Gate: Task 3, Task 4, Task 6.
- Release Non-Interference Gate: Task 4, Task 6.
- No repo-source fallback: Task 1 guard and Task 2 module design.
- Fresh deploy default: Task 4 orchestrator.
- Machine-verifiable artifacts: Task 2 `GateResult`, Task 4 gate JSON files.
- Stable failure labels: Task 1 guards, Task 2/3 implementations, Task 4 wrapper labels.
- Deterministic Chirp smoke: Task 2 `deterministic_code`.
- Cleanup policy: Task 3 and Task 6 release-readiness run.
