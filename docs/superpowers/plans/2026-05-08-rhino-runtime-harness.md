# Rhino Runtime Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a non-invasive process-owning Rhino runtime harness that starts one Rhino process, proves exact RookNative readiness, runs a tiny scoped live smoke, captures artifacts, and cleans up only the owned PID.

**Architecture:** Add a focused Python harness module under `mcp_server/src/rook/runtime_harness.py`, a thin script entry point under `scripts/run_rhino_runtime_harness.py`, and harness-aware pytest scoping in `mcp_server/tests/conftest.py`. The harness uses exact `%TEMP%/rook/instance-{pid}-native.json` discovery and never falls back to broad discovery after it owns a PID.

**Tech Stack:** Python 3.10+, stdlib `subprocess`, `pathlib`, `json`, `dataclasses`, `enum`, `time`, `shutil`; existing `httpx`; existing `rook.bridge` request context; pytest.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `mcp_server/src/rook/runtime_harness.py` | Create | Own process lifecycle, exact owned-PID discovery, ping, smoke subprocess execution, best-effort artifact copy, manifest writing, cleanup classification. |
| `scripts/run_rhino_runtime_harness.py` | Create | CLI wrapper that imports the harness from the source tree and exits `0` only for a green harness run. |
| `mcp_server/tests/test_runtime_harness.py` | Create | Unit tests for discovery, no broad fallback, smoke env, run result cleanup states, manifest/artifact behavior. No live Rhino required. |
| `mcp_server/src/rook/bridge.py` | Modify | Make direct `get_rhino_host()` calls honor the active `rhino_request_context` when explicit args are absent. |
| `mcp_server/tests/test_bridge.py` | Modify | Pin `get_rhino_host()` context behavior so direct live-test helper calls cannot escape harness scoping. |
| `mcp_server/tests/conftest.py` | Modify | Add harness-mode env parsing and an autouse `requires_rhino` fixture that binds the entire live test body to both `ROOK_RHINO_PORT` and `ROOK_RHINO_PROCESS_ID`. Ambient mode remains unchanged. |
| `mcp_server/tests/test_live_harness_scoping.py` | Create | Unit tests for pytest harness-mode parsing and failure/skip semantics without live Rhino. |
| `BUILDING.md` | Modify | Document the opt-in harness command and state that default live pytest behavior remains ambient unless harness env vars are set. |

## Task 1: Owned Discovery Helper

**Files:**
- Create: `mcp_server/src/rook/runtime_harness.py`
- Test: `mcp_server/tests/test_runtime_harness.py`

- [ ] **Step 1: Write failing discovery tests**

Create `mcp_server/tests/test_runtime_harness.py`:

```python
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook.runtime_harness import DiscoveryError, OwnedRhinoDiscovery


class FakeProcess:
    def __init__(self, pid: int, returncode: int | None = None) -> None:
        self.pid = pid
        self.returncode = returncode

    def poll(self) -> int | None:
        return self.returncode


def write_discovery(root: Path, pid: int, data: dict) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"instance-{pid}-native.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_owned_discovery_accepts_exact_native_pid(tmp_path: Path) -> None:
    write_discovery(
        tmp_path,
        1234,
        {
            "host": "127.0.0.1",
            "port": 34567,
            "processId": 1234,
            "pluginType": "native",
        },
    )

    discovery = OwnedRhinoDiscovery(discovery_dir=tmp_path)

    record = discovery.read_owned_record(1234)

    assert record.pid == 1234
    assert record.host == "127.0.0.1"
    assert record.port == 34567
    assert record.path == tmp_path / "instance-1234-native.json"


def test_owned_discovery_rejects_wrong_process_id(tmp_path: Path) -> None:
    write_discovery(
        tmp_path,
        1234,
        {
            "host": "127.0.0.1",
            "port": 34567,
            "processId": 9999,
            "pluginType": "native",
        },
    )

    discovery = OwnedRhinoDiscovery(discovery_dir=tmp_path)

    with pytest.raises(DiscoveryError, match="wrong processId"):
        discovery.read_owned_record(1234)


def test_owned_discovery_rejects_non_native_plugin_type(tmp_path: Path) -> None:
    write_discovery(
        tmp_path,
        1234,
        {
            "host": "127.0.0.1",
            "port": 34567,
            "processId": 1234,
            "pluginType": "csharp",
        },
    )

    discovery = OwnedRhinoDiscovery(discovery_dir=tmp_path)

    with pytest.raises(DiscoveryError, match="pluginType"):
        discovery.read_owned_record(1234)


@pytest.mark.parametrize("port", [None, 0, -1, "abc"])
def test_owned_discovery_rejects_invalid_port(tmp_path: Path, port: object) -> None:
    data = {
        "host": "127.0.0.1",
        "processId": 1234,
        "pluginType": "native",
    }
    if port is not None:
        data["port"] = port
    write_discovery(tmp_path, 1234, data)

    discovery = OwnedRhinoDiscovery(discovery_dir=tmp_path)

    with pytest.raises(DiscoveryError, match="port"):
        discovery.read_owned_record(1234)


def test_owned_discovery_rejects_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "instance-1234-native.json"
    path.write_text("{not json", encoding="utf-8")

    discovery = OwnedRhinoDiscovery(discovery_dir=tmp_path)

    with pytest.raises(DiscoveryError, match="malformed JSON"):
        discovery.read_owned_record(1234)


def test_owned_discovery_rejects_non_loopback_host(tmp_path: Path) -> None:
    write_discovery(
        tmp_path,
        1234,
        {
            "host": "evil.test",
            "port": 34567,
            "processId": 1234,
            "pluginType": "native",
        },
    )

    discovery = OwnedRhinoDiscovery(discovery_dir=tmp_path)

    with pytest.raises(DiscoveryError, match="loopback"):
        discovery.read_owned_record(1234)


def test_owned_discovery_snapshots_json(tmp_path: Path) -> None:
    write_discovery(
        tmp_path,
        1234,
        {
            "host": "127.0.0.1",
            "port": 34567,
            "processId": 1234,
            "pluginType": "native",
        },
    )
    artifact_dir = tmp_path / "artifacts"
    discovery = OwnedRhinoDiscovery(discovery_dir=tmp_path)
    record = discovery.read_owned_record(1234)

    snapshot = discovery.snapshot_owned_record(record, artifact_dir)

    assert snapshot == artifact_dir / "owned-discovery-instance-1234-native.json"
    assert json.loads(snapshot.read_text(encoding="utf-8"))["processId"] == 1234


def test_owned_discovery_never_reads_other_healthy_rhino(tmp_path: Path) -> None:
    write_discovery(
        tmp_path,
        9999,
        {
            "host": "127.0.0.1",
            "port": 45678,
            "processId": 9999,
            "pluginType": "native",
        },
    )
    discovery = OwnedRhinoDiscovery(discovery_dir=tmp_path)

    with pytest.raises(DiscoveryError, match="not found"):
        discovery.read_owned_record(1234)
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
cd mcp_server
pytest tests/test_runtime_harness.py -v
```

Expected: fail during import with `ModuleNotFoundError: No module named 'rook.runtime_harness'`.

- [ ] **Step 3: Implement minimal discovery code**

Create `mcp_server/src/rook/runtime_harness.py`:

```python
from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}
DEFAULT_DISCOVERY_DIR = Path(tempfile.gettempdir()) / "rook"


class DiscoveryError(RuntimeError):
    """Raised when the owned Rhino discovery file is absent or invalid."""


@dataclass(frozen=True)
class OwnedRhinoRecord:
    pid: int
    host: str
    port: int
    path: Path
    raw: dict[str, Any]


class OwnedRhinoDiscovery:
    def __init__(self, discovery_dir: Path = DEFAULT_DISCOVERY_DIR) -> None:
        self.discovery_dir = Path(discovery_dir)

    def owned_path(self, pid: int) -> Path:
        return self.discovery_dir / f"instance-{pid}-native.json"

    def read_owned_record(self, pid: int) -> OwnedRhinoRecord:
        path = self.owned_path(pid)
        if not path.exists():
            raise DiscoveryError(f"owned discovery file not found: {path}")

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DiscoveryError(f"owned discovery file contains malformed JSON: {path}") from exc

        process_id = raw.get("processId")
        if process_id != pid:
            raise DiscoveryError(f"owned discovery file has wrong processId: expected {pid}, got {process_id!r}")

        plugin_type = raw.get("pluginType")
        if plugin_type != "native":
            raise DiscoveryError(f"owned discovery file has invalid pluginType: {plugin_type!r}")

        host = raw.get("host") or "127.0.0.1"
        if not isinstance(host, str) or host.strip().lower() not in LOOPBACK_HOSTS:
            raise DiscoveryError(f"owned discovery file host is not loopback: {host!r}")
        host = host.strip().lower()

        port = raw.get("port")
        if not isinstance(port, int) or port <= 0:
            raise DiscoveryError(f"owned discovery file has invalid port: {port!r}")

        return OwnedRhinoRecord(pid=pid, host=host, port=port, path=path, raw=raw)

    def snapshot_owned_record(self, record: OwnedRhinoRecord, artifact_dir: Path) -> Path:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        snapshot = artifact_dir / f"owned-discovery-{record.path.name}"
        snapshot.write_text(json.dumps(record.raw, indent=2), encoding="utf-8")
        return snapshot
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
cd mcp_server
pytest tests/test_runtime_harness.py -v
```

Expected: all tests in `test_runtime_harness.py` pass.

- [ ] **Step 5: Commit**

```powershell
git add mcp_server/src/rook/runtime_harness.py mcp_server/tests/test_runtime_harness.py
git commit -m "test: add owned Rhino discovery harness"
```

## Task 2: Readiness Wait and Exact Ping

**Files:**
- Modify: `mcp_server/src/rook/runtime_harness.py`
- Modify: `mcp_server/tests/test_runtime_harness.py`

- [ ] **Step 1: Add failing readiness tests**

Append to `mcp_server/tests/test_runtime_harness.py`:

```python
import httpx


class PingRecorder:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.urls: list[str] = []

    async def __call__(self, host: str, port: int) -> bool:
        self.urls.append(f"http://{host}:{port}/ping")
        return self.ok


def test_wait_for_ready_reports_owned_process_exit_before_discovery(tmp_path: Path) -> None:
    process = FakeProcess(1234, returncode=5)
    discovery = OwnedRhinoDiscovery(discovery_dir=tmp_path)

    with pytest.raises(DiscoveryError, match="exited with code 5 before RookNative discovery appeared"):
        discovery.wait_for_ready(
            pid=1234,
            process=process,
            ping=PingRecorder(),
            timeout_seconds=0.01,
            poll_seconds=0.001,
        )


def test_wait_for_ready_pings_exact_owned_port(tmp_path: Path) -> None:
    write_discovery(
        tmp_path,
        1234,
        {
            "host": "127.0.0.1",
            "port": 34567,
            "processId": 1234,
            "pluginType": "native",
        },
    )
    ping = PingRecorder(ok=True)
    discovery = OwnedRhinoDiscovery(discovery_dir=tmp_path)

    record = discovery.wait_for_ready(
        pid=1234,
        process=FakeProcess(1234),
        ping=ping,
        timeout_seconds=0.1,
        poll_seconds=0.001,
    )

    assert record.pid == 1234
    assert ping.urls == ["http://127.0.0.1:34567/ping"]


def test_wait_for_ready_times_out_when_ping_never_succeeds(tmp_path: Path) -> None:
    write_discovery(
        tmp_path,
        1234,
        {
            "host": "127.0.0.1",
            "port": 34567,
            "processId": 1234,
            "pluginType": "native",
        },
    )
    discovery = OwnedRhinoDiscovery(discovery_dir=tmp_path)

    with pytest.raises(DiscoveryError, match="did not become pingable"):
        discovery.wait_for_ready(
            pid=1234,
            process=FakeProcess(1234),
            ping=PingRecorder(ok=False),
            timeout_seconds=0.01,
            poll_seconds=0.001,
        )
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
cd mcp_server
pytest tests/test_runtime_harness.py -v
```

Expected: fail with `AttributeError: 'OwnedRhinoDiscovery' object has no attribute 'wait_for_ready'`.

- [ ] **Step 3: Implement readiness wait and ping function**

Modify `mcp_server/src/rook/runtime_harness.py`:

```python
import time
from collections.abc import Callable
from typing import Protocol

import httpx


class ProcessLike(Protocol):
    pid: int
    returncode: int | None

    def poll(self) -> int | None:
        ...


async def ping_native(host: str, port: int) -> bool:
    url = f"http://{host}:{port}/ping"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(url)
            if response.status_code != 200:
                return False
            body = response.json()
            return body == "pong" or body.get("data") == "pong" or body.get("success") is True
    except Exception:
        return False
```

Then add this method inside `OwnedRhinoDiscovery`:

```python
    def wait_for_ready(
        self,
        *,
        pid: int,
        process: ProcessLike,
        ping: Callable[[str, int], Any],
        timeout_seconds: float,
        poll_seconds: float,
    ) -> OwnedRhinoRecord:
        deadline = time.monotonic() + timeout_seconds
        last_error: str | None = None

        while time.monotonic() < deadline:
            exit_code = process.poll()
            if exit_code is not None:
                raise DiscoveryError(
                    f"Rhino exited with code {exit_code} before RookNative discovery appeared"
                )

            try:
                record = self.read_owned_record(pid)
            except DiscoveryError as exc:
                last_error = str(exc)
                time.sleep(poll_seconds)
                continue

            ok = ping(record.host, record.port)
            if hasattr(ok, "__await__"):
                import asyncio

                ok = asyncio.run(ok)
            if ok:
                return record

            last_error = f"owned RookNative at {record.host}:{record.port} did not become pingable"
            time.sleep(poll_seconds)

        if last_error:
            raise DiscoveryError(last_error)
        raise DiscoveryError(f"owned discovery file not found before timeout for PID {pid}")
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
cd mcp_server
pytest tests/test_runtime_harness.py -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add mcp_server/src/rook/runtime_harness.py mcp_server/tests/test_runtime_harness.py
git commit -m "feat: wait for owned RookNative readiness"
```

## Task 3: Harness Result, Smoke Command, and Manifest

**Files:**
- Modify: `mcp_server/src/rook/runtime_harness.py`
- Modify: `mcp_server/tests/test_runtime_harness.py`

- [ ] **Step 1: Add failing smoke/env/manifest tests**

Append to `mcp_server/tests/test_runtime_harness.py`:

```python
from rook.runtime_harness import CleanupPath, RhinoRuntimeHarness, SmokeCommand


def test_smoke_command_receives_pytest_owned_env_only(tmp_path: Path) -> None:
    harness = RhinoRuntimeHarness(artifact_root=tmp_path)
    env = harness.build_smoke_env(
        base_env={},
        pid=1234,
        port=34567,
        command=SmokeCommand(kind="pytest", argv=["pytest", "tests/test_pipe_live.py"]),
    )

    assert env["ROOK_RHINO_PORT"] == "34567"
    assert env["ROOK_RHINO_PROCESS_ID"] == "1234"
    assert "NATIVE_PORT" not in env


def test_smoke_command_receives_native_port_for_validation_script(tmp_path: Path) -> None:
    harness = RhinoRuntimeHarness(artifact_root=tmp_path)
    env = harness.build_smoke_env(
        base_env={},
        pid=1234,
        port=34567,
        command=SmokeCommand(kind="validation-script", argv=["python", "scripts/validate_rhino_operational_suite.py"]),
    )

    assert env["ROOK_RHINO_PORT"] == "34567"
    assert env["ROOK_RHINO_PROCESS_ID"] == "1234"
    assert env["NATIVE_PORT"] == "34567"


def test_manifest_records_smoke_output_and_cleanup(tmp_path: Path) -> None:
    harness = RhinoRuntimeHarness(artifact_root=tmp_path)
    result = harness.new_result(pid=1234, port=34567, artifact_dir=tmp_path / "run")
    result.smoke_stdout = "out"
    result.smoke_stderr = "err"
    result.smoke_exit_code = 7
    result.cleanup_path = CleanupPath.GRACEFUL_TIMEOUT_FORCED_KILL
    result.green = False

    manifest = harness.write_manifest(result)
    body = json.loads(manifest.read_text(encoding="utf-8"))

    assert body["pid"] == 1234
    assert body["port"] == 34567
    assert body["smoke"]["stdout"] == "out"
    assert body["smoke"]["stderr"] == "err"
    assert body["smoke"]["exit_code"] == 7
    assert body["cleanup"]["path"] == "graceful_timeout_forced_kill"
    assert body["green"] is False
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
cd mcp_server
pytest tests/test_runtime_harness.py -v
```

Expected: fail importing `CleanupPath`, `RhinoRuntimeHarness`, or `SmokeCommand`.

- [ ] **Step 3: Implement result, smoke env, and manifest**

Append to `mcp_server/src/rook/runtime_harness.py`:

```python
import os
from dataclasses import field
from enum import Enum
from typing import Literal


class CleanupPath(str, Enum):
    GRACEFUL_EXIT = "graceful_exit"
    GRACEFUL_EXIT_DISCOVERY_LEFTOVER = "graceful_exit_discovery_leftover"
    GRACEFUL_TIMEOUT_FORCED_KILL = "graceful_timeout_forced_kill"
    ALREADY_EXITED_BEFORE_CLEANUP = "already_exited_before_cleanup"
    FORCE_KILL_FAILED = "force_kill_failed"


@dataclass(frozen=True)
class SmokeCommand:
    kind: Literal["pytest", "validation-script"]
    argv: list[str]


@dataclass
class HarnessRunResult:
    pid: int
    port: int | None
    artifact_dir: Path
    run_started_at: float
    green: bool = False
    smoke_stdout: str = ""
    smoke_stderr: str = ""
    smoke_exit_code: int | None = None
    cleanup_path: CleanupPath | None = None
    warnings: list[str] = field(default_factory=list)


class RhinoRuntimeHarness:
    def __init__(self, artifact_root: Path) -> None:
        self.artifact_root = Path(artifact_root)

    def new_result(self, *, pid: int, port: int | None, artifact_dir: Path) -> HarnessRunResult:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        return HarnessRunResult(
            pid=pid,
            port=port,
            artifact_dir=artifact_dir,
            run_started_at=time.time(),
        )

    def build_smoke_env(
        self,
        *,
        base_env: dict[str, str] | None,
        pid: int,
        port: int,
        command: SmokeCommand,
    ) -> dict[str, str]:
        env = dict(base_env or os.environ)
        env["ROOK_RHINO_PORT"] = str(port)
        env["ROOK_RHINO_PROCESS_ID"] = str(pid)
        if command.kind == "validation-script":
            env["NATIVE_PORT"] = str(port)
        else:
            env.pop("NATIVE_PORT", None)
        return env

    def write_manifest(self, result: HarnessRunResult) -> Path:
        result.artifact_dir.mkdir(parents=True, exist_ok=True)
        manifest = result.artifact_dir / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "pid": result.pid,
                    "port": result.port,
                    "green": result.green,
                    "smoke": {
                        "stdout": result.smoke_stdout,
                        "stderr": result.smoke_stderr,
                        "exit_code": result.smoke_exit_code,
                    },
                    "cleanup": {
                        "path": result.cleanup_path.value if result.cleanup_path else None,
                    },
                    "warnings": result.warnings,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return manifest
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
cd mcp_server
pytest tests/test_runtime_harness.py -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add mcp_server/src/rook/runtime_harness.py mcp_server/tests/test_runtime_harness.py
git commit -m "feat: record Rhino harness smoke results"
```

## Task 4: Artifact Copy and Cleanup Classifier

**Files:**
- Modify: `mcp_server/src/rook/runtime_harness.py`
- Modify: `mcp_server/tests/test_runtime_harness.py`

- [ ] **Step 1: Add failing artifact and cleanup tests**

Append to `mcp_server/tests/test_runtime_harness.py`:

```python
def test_copy_rook_temp_artifacts_warns_when_missing(tmp_path: Path) -> None:
    harness = RhinoRuntimeHarness(artifact_root=tmp_path)
    result = harness.new_result(pid=1234, port=34567, artifact_dir=tmp_path / "run")

    copied = harness.copy_rook_temp_artifacts(
        result=result,
        temp_rook_dir=tmp_path / "missing",
        label="before-shutdown",
    )

    assert copied == []
    assert any("does not exist" in warning for warning in result.warnings)


def test_copy_rook_temp_artifacts_copies_readable_files(tmp_path: Path) -> None:
    source = tmp_path / "rook"
    source.mkdir()
    (source / "companion-startup.log").write_text("startup", encoding="utf-8")
    (source / "instance-1234-native.json").write_text("{}", encoding="utf-8")
    harness = RhinoRuntimeHarness(artifact_root=tmp_path)
    result = harness.new_result(pid=1234, port=34567, artifact_dir=tmp_path / "run")

    copied = harness.copy_rook_temp_artifacts(result=result, temp_rook_dir=source, label="before-shutdown")

    assert len(copied) == 2
    assert (tmp_path / "run" / "before-shutdown" / "companion-startup.log").read_text(encoding="utf-8") == "startup"


def test_copy_rook_temp_artifacts_filters_before_run_window(tmp_path: Path) -> None:
    source = tmp_path / "rook"
    source.mkdir()
    old_log = source / "old.log"
    new_log = source / "new.log"
    old_log.write_text("old", encoding="utf-8")
    new_log.write_text("new", encoding="utf-8")
    os.utime(old_log, (1000, 1000))
    os.utime(new_log, (2000, 2000))
    harness = RhinoRuntimeHarness(artifact_root=tmp_path)
    result = harness.new_result(pid=1234, port=34567, artifact_dir=tmp_path / "run")
    result.run_started_at = 1500

    copied = harness.copy_rook_temp_artifacts(result=result, temp_rook_dir=source, label="before-shutdown")

    assert [path.name for path in copied] == ["new.log"]
    assert not (tmp_path / "run" / "before-shutdown" / "old.log").exists()


def test_classify_graceful_exit_with_discovery_leftover_is_non_green(tmp_path: Path) -> None:
    harness = RhinoRuntimeHarness(artifact_root=tmp_path)
    result = harness.new_result(pid=1234, port=34567, artifact_dir=tmp_path / "run")

    harness.classify_cleanup(
        result,
        already_exited_before_cleanup=False,
        process_exited_after_cleanup=True,
        discovery_leftover=True,
        forced=False,
        force_failed=False,
    )

    assert result.cleanup_path == CleanupPath.GRACEFUL_EXIT_DISCOVERY_LEFTOVER
    assert result.green is False


def test_classify_forced_cleanup_is_non_green(tmp_path: Path) -> None:
    harness = RhinoRuntimeHarness(artifact_root=tmp_path)
    result = harness.new_result(pid=1234, port=34567, artifact_dir=tmp_path / "run")

    harness.classify_cleanup(
        result,
        already_exited_before_cleanup=False,
        process_exited_after_cleanup=True,
        discovery_leftover=True,
        forced=True,
        force_failed=False,
    )

    assert result.cleanup_path == CleanupPath.GRACEFUL_TIMEOUT_FORCED_KILL
    assert result.green is False


def test_classify_already_exited_before_cleanup_is_distinct(tmp_path: Path) -> None:
    harness = RhinoRuntimeHarness(artifact_root=tmp_path)
    result = harness.new_result(pid=1234, port=34567, artifact_dir=tmp_path / "run")

    harness.classify_cleanup(
        result,
        already_exited_before_cleanup=True,
        process_exited_after_cleanup=True,
        discovery_leftover=False,
        forced=False,
        force_failed=False,
    )

    assert result.cleanup_path == CleanupPath.ALREADY_EXITED_BEFORE_CLEANUP
    assert result.green is False


def test_classify_force_kill_failed_when_still_running_after_cleanup(tmp_path: Path) -> None:
    harness = RhinoRuntimeHarness(artifact_root=tmp_path)
    result = harness.new_result(pid=1234, port=34567, artifact_dir=tmp_path / "run")

    harness.classify_cleanup(
        result,
        already_exited_before_cleanup=False,
        process_exited_after_cleanup=False,
        discovery_leftover=True,
        forced=True,
        force_failed=True,
    )

    assert result.cleanup_path == CleanupPath.FORCE_KILL_FAILED
    assert result.green is False
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
cd mcp_server
pytest tests/test_runtime_harness.py -v
```

Expected: fail with missing `copy_rook_temp_artifacts` and `classify_cleanup`.

- [ ] **Step 3: Implement artifact copy and cleanup classification**

Add methods to `RhinoRuntimeHarness`:

```python
    def copy_rook_temp_artifacts(
        self,
        *,
        result: HarnessRunResult,
        temp_rook_dir: Path,
        label: str,
        mtime_slop_seconds: float = 5.0,
    ) -> list[Path]:
        destination = result.artifact_dir / label
        copied: list[Path] = []
        if not temp_rook_dir.exists():
            result.warnings.append(f"{temp_rook_dir} does not exist; no Rook temp artifacts copied")
            return copied

        destination.mkdir(parents=True, exist_ok=True)
        for source in temp_rook_dir.rglob("*"):
            if not source.is_file():
                continue
            try:
                if source.stat().st_mtime < result.run_started_at - mtime_slop_seconds:
                    continue
                relative = source.relative_to(temp_rook_dir)
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                copied.append(target)
            except Exception as exc:
                result.warnings.append(f"could not copy {source}: {exc!r}")
        return copied

    def classify_cleanup(
        self,
        result: HarnessRunResult,
        *,
        already_exited_before_cleanup: bool,
        process_exited_after_cleanup: bool,
        discovery_leftover: bool,
        forced: bool,
        force_failed: bool,
    ) -> None:
        if already_exited_before_cleanup:
            result.cleanup_path = CleanupPath.ALREADY_EXITED_BEFORE_CLEANUP
            result.green = False
            return
        if force_failed:
            result.cleanup_path = CleanupPath.FORCE_KILL_FAILED
            result.green = False
            return
        if forced:
            result.cleanup_path = CleanupPath.GRACEFUL_TIMEOUT_FORCED_KILL
            result.green = False
            return
        if not process_exited_after_cleanup:
            result.cleanup_path = CleanupPath.FORCE_KILL_FAILED
            result.green = False
            return
        if discovery_leftover:
            result.cleanup_path = CleanupPath.GRACEFUL_EXIT_DISCOVERY_LEFTOVER
            result.green = False
            return
        result.cleanup_path = CleanupPath.GRACEFUL_EXIT
        result.green = result.smoke_exit_code == 0
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
cd mcp_server
pytest tests/test_runtime_harness.py -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add mcp_server/src/rook/runtime_harness.py mcp_server/tests/test_runtime_harness.py
git commit -m "feat: capture Rhino harness artifacts"
```

## Task 5: External Graceful Close Adapter

**Files:**
- Modify: `mcp_server/src/rook/runtime_harness.py`
- Modify: `mcp_server/tests/test_runtime_harness.py`

- [ ] **Step 1: Add failing graceful-close adapter tests**

Append to `mcp_server/tests/test_runtime_harness.py`:

```python
class CloseProcess:
    def __init__(self, pid: int, exits_after_close: bool) -> None:
        self.pid = pid
        self.returncode = None
        self.closed = False
        self.killed = False
        self.exits_after_close = exits_after_close

    def poll(self) -> int | None:
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        if self.returncode is None:
            raise TimeoutError("still running")
        return self.returncode


def test_request_external_graceful_close_targets_owned_process(tmp_path: Path) -> None:
    process = CloseProcess(pid=1234, exits_after_close=True)
    harness = RhinoRuntimeHarness(artifact_root=tmp_path)

    def fake_close(pid: int) -> int:
        assert pid == 1234
        process.closed = True
        process.returncode = 0
        return 1

    forced = harness.request_external_graceful_close(
        process,
        timeout_seconds=0.01,
        close_windows_for_pid=fake_close,
    )

    assert forced is False
    assert process.closed is True
    assert process.killed is False


def test_request_external_graceful_close_force_kills_only_after_timeout(tmp_path: Path) -> None:
    process = CloseProcess(pid=1234, exits_after_close=False)
    harness = RhinoRuntimeHarness(artifact_root=tmp_path)

    def fake_close(pid: int) -> int:
        assert pid == 1234
        process.closed = True
        return 1

    forced = harness.request_external_graceful_close(
        process,
        timeout_seconds=0.01,
        close_windows_for_pid=fake_close,
    )

    assert forced is True
    assert process.closed is True
    assert process.killed is True
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
cd mcp_server
pytest tests/test_runtime_harness.py -v
```

Expected: fail with missing `request_external_graceful_close`.

- [ ] **Step 3: Implement the external close adapter**

Add imports to `runtime_harness.py`:

```python
import ctypes
from ctypes import wintypes
```

Add module-level Windows close helpers:

```python
WM_CLOSE = 0x0010


def close_windows_for_pid(pid: int) -> int:
    """Send WM_CLOSE to top-level visible windows owned by pid.

    This is the v1 non-invasive graceful-close mechanism. It does not use a
    RookNative route and it never targets ambient Rhino processes because it
    filters windows by the owned process id.
    """
    user32 = ctypes.windll.user32
    closed = 0

    enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd: int, lparam: int) -> bool:
        nonlocal closed
        window_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        if window_pid.value != pid:
            return True
        if not user32.IsWindowVisible(hwnd):
            return True
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        closed += 1
        return True

    user32.EnumWindows(enum_proc_type(callback), 0)
    return closed
```

Add to `RhinoRuntimeHarness`:

```python
    def request_external_graceful_close(
        self,
        process: ProcessLike,
        timeout_seconds: float,
        close_windows_for_pid=close_windows_for_pid,
    ) -> bool:
        """Request external graceful close for the owned PID, then force-kill on timeout."""
        close_windows_for_pid(process.pid)
        wait = getattr(process, "wait")
        try:
            wait(timeout=timeout_seconds)
            return False
        except Exception:
            kill = getattr(process, "kill")
            kill()
            try:
                wait(timeout=5)
            except Exception:
                pass
            return True
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
cd mcp_server
pytest tests/test_runtime_harness.py -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add mcp_server/src/rook/runtime_harness.py mcp_server/tests/test_runtime_harness.py
git commit -m "feat: add owned Rhino cleanup adapter"
```

## Task 6: Bridge Context Pins for Direct Host Lookup

**Files:**
- Modify: `mcp_server/src/rook/bridge.py`
- Modify: `mcp_server/tests/test_bridge.py`

- [ ] **Step 1: Add failing direct-host context test**

Append to `mcp_server/tests/test_bridge.py`:

```python
def test_get_rhino_host_uses_scoped_process_context(discovery_dir: Path) -> None:
    _write_instance(
        discovery_dir / "instance-7101-native.json",
        {
            "port": 9950,
            "processId": 7101,
            "pluginType": "native",
        },
    )
    _write_instance(
        discovery_dir / "instance-7102-native.json",
        {
            "port": 9951,
            "processId": 7102,
            "pluginType": "native",
        },
    )

    with bridge.rhino_request_context(port=9951, process_id=7102):
        host = bridge.get_rhino_host()

    assert host == "http://127.0.0.1:9951"


def test_get_rhino_host_rejects_scoped_port_with_wrong_process_id(discovery_dir: Path) -> None:
    _write_instance(
        discovery_dir / "instance-9999-native.json",
        {
            "port": 9951,
            "processId": 9999,
            "pluginType": "native",
        },
    )

    with bridge.rhino_request_context(port=9951, process_id=7102):
        host = bridge.get_rhino_host()

    assert host is None
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
cd mcp_server
pytest tests/test_bridge.py::test_get_rhino_host_uses_scoped_process_context -v
```

Expected before implementation: the first test fails because `get_rhino_host()` ignores the active request context and may select the first discovered native instance. The wrong-PID test fails because `select_rhino_instance(port=9951, process_id=7102)` accepts the port anchor before checking that the discovered process id matches `7102`.

- [ ] **Step 3: Make `select_rhino_instance()` reject port/PID mismatches**

Modify the `if port is not None:` block in `mcp_server/src/rook/bridge.py`:

```python
    if port is not None:
        anchor = next((inst for inst in instances if inst.get("port") == port), None)
        if anchor is None:
            return {"port": port} if process_id is None else None

        anchor_pid = anchor.get("processId")
        if process_id is not None and anchor_pid != process_id:
            return None

        if not normalized_endpoint or (
            not normalized_endpoint.startswith(GH_ROUTE_PREFIX)
            and not normalized_endpoint.startswith(RC_ROUTE_PREFIX)
        ):
            return anchor

        if anchor_pid:
            scoped_instances = [
                inst for inst in instances if inst.get("processId") == anchor_pid
            ]
        else:
            scoped_instances = [anchor]
```

This is the safety-critical selector change. In harness mode, port and PID are a pair; the right port with the wrong PID is not a valid owned runtime.

- [ ] **Step 4: Make `get_rhino_host()` honor request context**

Modify `mcp_server/src/rook/bridge.py`:

```python
def get_rhino_host(
    port: int | None = None,
    endpoint: str | None = None,
    process_id: int | None = None,
) -> str | None:
    """Get the Rhino host URL, optionally resolved for a specific endpoint.

    Returns None if no Rhino instance is discovered and no explicit/context
    port was provided. Callers must handle None to produce clear error messages.
    """
    resolved_port = port if port is not None else _RHINO_CONTEXT_PORT.get()
    resolved_process_id = (
        process_id if process_id is not None else _RHINO_CONTEXT_PROCESS_ID.get()
    )

    if resolved_port is not None and resolved_port <= 0:
        resolved_port = None
    if resolved_process_id is not None and resolved_process_id <= 0:
        resolved_process_id = None

    if resolved_port and endpoint is None and resolved_process_id is None:
        return f"http://{DEFAULT_HOST}:{resolved_port}"

    instance = select_rhino_instance(
        endpoint=endpoint,
        port=resolved_port,
        process_id=resolved_process_id,
    )
    if instance and instance.get("port"):
        host = instance.get("host") or DEFAULT_HOST
        return f"http://{host}:{instance['port']}"

    if resolved_port and resolved_process_id is None:
        return f"http://{DEFAULT_HOST}:{resolved_port}"

    return None
```

- [ ] **Step 5: Run bridge tests**

Run:

```powershell
cd mcp_server
pytest tests/test_bridge.py -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add mcp_server/src/rook/bridge.py mcp_server/tests/test_bridge.py
git commit -m "fix: route direct Rhino host lookup through context"
```

## Task 7: Harness-Aware Pytest Scoping

**Files:**
- Modify: `mcp_server/tests/conftest.py`
- Create: `mcp_server/tests/test_live_harness_scoping.py`

- [ ] **Step 1: Write failing pytest scoping tests**

Create `mcp_server/tests/test_live_harness_scoping.py`:

```python
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import conftest
from rook import bridge


def test_harness_env_absent_is_ambient(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ROOK_RHINO_PORT", raising=False)
    monkeypatch.delenv("ROOK_RHINO_PROCESS_ID", raising=False)

    assert conftest._get_harness_scope_from_env() is None


def test_harness_env_partial_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOK_RHINO_PORT", "34567")
    monkeypatch.delenv("ROOK_RHINO_PROCESS_ID", raising=False)

    with pytest.raises(RuntimeError, match="must both be set"):
        conftest._get_harness_scope_from_env()


def test_harness_env_malformed_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOK_RHINO_PORT", "not-int")
    monkeypatch.setenv("ROOK_RHINO_PROCESS_ID", "1234")

    with pytest.raises(RuntimeError, match="positive integers"):
        conftest._get_harness_scope_from_env()


def test_harness_env_returns_port_and_pid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOK_RHINO_PORT", "34567")
    monkeypatch.setenv("ROOK_RHINO_PROCESS_ID", "1234")

    assert conftest._get_harness_scope_from_env() == (34567, 1234)


def test_harness_live_context_wraps_direct_host_lookup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ROOK_RHINO_PORT", "34567")
    monkeypatch.setenv("ROOK_RHINO_PROCESS_ID", "1234")
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDER", tmp_path)
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    (tmp_path / "instance-1234-native.json").write_text(
        '{"host":"127.0.0.1","port":34567,"processId":1234,"pluginType":"native"}',
        encoding="utf-8",
    )

    with conftest._harness_rhino_request_context_for_test():
        assert bridge.get_rhino_host() == "http://127.0.0.1:34567"
        assert bridge.get_rhino_request_context()["port"] == 34567
        assert bridge.get_rhino_request_context()["process_id"] == 1234
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
cd mcp_server
pytest tests/test_live_harness_scoping.py -v
```

Expected: fail with missing `_get_harness_scope_from_env`.

- [ ] **Step 3: Implement env parsing and full-test context helpers**

Modify `mcp_server/tests/conftest.py` near `_is_error`:

```python
from contextlib import contextmanager


def _get_harness_scope_from_env() -> tuple[int, int] | None:
    port_raw = os.environ.get("ROOK_RHINO_PORT")
    pid_raw = os.environ.get("ROOK_RHINO_PROCESS_ID")

    if not port_raw and not pid_raw:
        return None
    if not port_raw or not pid_raw:
        raise RuntimeError(
            "ROOK_RHINO_PORT and ROOK_RHINO_PROCESS_ID must both be set for harness-mode live tests"
        )

    try:
        port = int(port_raw)
        pid = int(pid_raw)
    except ValueError as exc:
        raise RuntimeError("ROOK_RHINO_PORT and ROOK_RHINO_PROCESS_ID must be positive integers") from exc

    if port <= 0 or pid <= 0:
        raise RuntimeError("ROOK_RHINO_PORT and ROOK_RHINO_PROCESS_ID must be positive integers")

    return port, pid


@contextmanager
def _harness_rhino_request_context_for_test():
    from rook.bridge import rhino_request_context

    harness_scope = _get_harness_scope_from_env()
    if harness_scope is None:
        yield
        return

    port, process_id = harness_scope
    with rhino_request_context(port=port, process_id=process_id):
        yield
```

Add `import os` at the top of `conftest.py`.

- [ ] **Step 4: Add an autouse fixture that wraps entire live tests**

Add below `_harness_rhino_request_context_for_test()`:

```python
@pytest.fixture(autouse=True)
def _harness_scope_for_requires_rhino_tests(request):
    if "requires_rhino" not in request.keywords:
        yield
        return

    with _harness_rhino_request_context_for_test():
        yield
```

This fixture is the key safety boundary: it keeps both `_mcp_tool_executor()` calls and direct `get_rhino_host()` calls in live-test bodies scoped to the owned PID/port for the full duration of each `requires_rhino` test. Ambient mode remains unchanged because the context helper is a no-op when both env vars are absent.

- [ ] **Step 5: Simplify `fresh_document` to rely on the full-test context**

Keep the existing `fresh_document` behavior, but make harness-mode failures fail instead of skip. Replace the start of `_setup()` with:

```python
    async def _setup() -> tuple[bool, str | None]:
        harness_scope = _get_harness_scope_from_env()
        try:
            ping = await asyncio.wait_for(
                _mcp_tool_executor("rhino_ping", {}),
                timeout=3.0,
            )
        except RuntimeError:
            raise
        except (asyncio.TimeoutError, Exception) as ex:  # noqa: BLE001
            if harness_scope is not None:
                raise RuntimeError(f"Harness-owned Rhino ping failed: {ex!r}") from ex
            return False, f"Rhino ping raised: {ex!r}"

        if _is_error(ping):
            if harness_scope is not None:
                raise RuntimeError(f"Harness-owned Rhino ping returned error: {ping!r}")
            return False, f"Rhino ping returned error: {ping!r}"

        new_doc = await _mcp_tool_executor("rhino_document_ops", {"action": "new"})
        if _is_error(new_doc):
            if harness_scope is not None:
                raise RuntimeError(f"Harness-owned rhino_document_ops(new) failed: {new_doc!r}")
            return False, f"rhino_document_ops(new) failed: {new_doc!r}"

        blocks_list = await _mcp_tool_executor("rhino_blocks", {})
        if isinstance(blocks_list, dict) and isinstance(blocks_list.get("blocks"), list):
            for entry in blocks_list["blocks"]:
                name = entry.get("name") if isinstance(entry, dict) else None
                if name:
                    await _mcp_tool_executor(
                        "rhino_block_delete",
                        {"name": name, "deleteInstances": True},
                    )

        return True, None
```

Keep the existing skip after `asyncio.run(_setup())`; RuntimeError in harness mode should escape and fail the test.

- [ ] **Step 6: Run scoping tests**

Run:

```powershell
cd mcp_server
pytest tests/test_live_harness_scoping.py -v
```

Expected: pass.

- [ ] **Step 7: Run bridge context and scoping tests together**

Run:

```powershell
cd mcp_server
pytest tests/test_bridge.py::test_get_rhino_host_uses_scoped_process_context tests/test_live_harness_scoping.py -v
```

Expected: pass.

- [ ] **Step 8: Run a representative existing live-test file without harness env**

Run:

```powershell
cd mcp_server
pytest tests/test_select_additive_live.py -m requires_rhino -v
```

Expected without Rhino: skipped, not failed. Expected with ambient Rhino: existing behavior unchanged.

- [ ] **Step 9: Commit**

```powershell
git add mcp_server/tests/conftest.py mcp_server/tests/test_live_harness_scoping.py
git commit -m "test: scope live pytest to owned Rhino"
```

## Task 8: Harness CLI Runner

**Files:**
- Modify: `mcp_server/src/rook/runtime_harness.py`
- Create: `scripts/run_rhino_runtime_harness.py`
- Modify: `mcp_server/tests/test_runtime_harness.py`

- [ ] **Step 1: Add failing subprocess execution test**

Append to `mcp_server/tests/test_runtime_harness.py`:

```python
def test_run_smoke_command_records_stdout_stderr_and_exit_code(tmp_path: Path) -> None:
    harness = RhinoRuntimeHarness(artifact_root=tmp_path)
    result = harness.new_result(pid=1234, port=34567, artifact_dir=tmp_path / "run")

    harness.run_smoke_command(
        result=result,
        command=SmokeCommand(
            kind="pytest",
            argv=[
                sys.executable,
                "-c",
                "import sys; print('out'); print('err', file=sys.stderr); raise SystemExit(3)",
            ],
        ),
        env={"ROOK_RHINO_PORT": "34567", "ROOK_RHINO_PROCESS_ID": "1234"},
        cwd=Path.cwd(),
    )

    assert result.smoke_stdout.strip() == "out"
    assert result.smoke_stderr.strip() == "err"
    assert result.smoke_exit_code == 3
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
cd mcp_server
pytest tests/test_runtime_harness.py::test_run_smoke_command_records_stdout_stderr_and_exit_code -v
```

Expected: fail with missing `run_smoke_command`.

- [ ] **Step 3: Implement smoke subprocess execution**

Add imports to `runtime_harness.py`:

```python
import subprocess
```

Add to `RhinoRuntimeHarness`:

```python
    def run_smoke_command(
        self,
        *,
        result: HarnessRunResult,
        command: SmokeCommand,
        env: dict[str, str],
        cwd: Path,
    ) -> None:
        completed = subprocess.run(
            command.argv,
            cwd=str(cwd),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        result.smoke_stdout = completed.stdout
        result.smoke_stderr = completed.stderr
        result.smoke_exit_code = completed.returncode
```

- [ ] **Step 4: Create CLI wrapper**

Create `scripts/run_rhino_runtime_harness.py`:

```python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "mcp_server" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rook.runtime_harness import RhinoRuntimeHarness, SmokeCommand


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an owned Rhino runtime smoke harness.")
    parser.add_argument("--rhino-exe", default=r"C:\Program Files\Rhino 8\System\Rhino.exe")
    parser.add_argument("--artifact-root", default=str(REPO_ROOT / ".scratch" / "rhino-runtime-harness"))
    parser.add_argument(
        "--smoke",
        choices=["pytest-select", "rhino-operational"],
        default="pytest-select",
    )
    args = parser.parse_args()

    if args.smoke == "pytest-select":
        command = SmokeCommand(
            kind="pytest",
            argv=[
                sys.executable,
                "-m",
                "pytest",
                "tests/test_select_additive_live.py",
                "-m",
                "requires_rhino",
                "-v",
            ],
        )
        cwd = REPO_ROOT / "mcp_server"
    else:
        command = SmokeCommand(
            kind="validation-script",
            argv=[sys.executable, "scripts/validate_rhino_operational_suite.py"],
        )
        cwd = REPO_ROOT

    harness = RhinoRuntimeHarness(artifact_root=Path(args.artifact_root))
    result = harness.run(rhino_exe=Path(args.rhino_exe), smoke_command=command, smoke_cwd=cwd)
    print(f"Artifact directory: {result.artifact_dir}")
    return 0 if result.green else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Implement `RhinoRuntimeHarness.run` minimally**

Add to `RhinoRuntimeHarness`:

```python
    def run(
        self,
        *,
        rhino_exe: Path,
        smoke_command: SmokeCommand,
        smoke_cwd: Path,
        readiness_timeout_seconds: float = 120.0,
        cleanup_timeout_seconds: float = 20.0,
    ) -> HarnessRunResult:
        if not rhino_exe.exists():
            artifact_dir = self.artifact_root / "launch-failed"
            result = self.new_result(pid=0, port=None, artifact_dir=artifact_dir)
            result.warnings.append(f"Rhino executable not found: {rhino_exe}")
            self.write_manifest(result)
            return result

        process = subprocess.Popen([str(rhino_exe)])
        artifact_dir = self.artifact_root / f"run-{process.pid}"
        result = self.new_result(pid=process.pid, port=None, artifact_dir=artifact_dir)
        discovery = OwnedRhinoDiscovery()

        try:
            record = discovery.wait_for_ready(
                pid=process.pid,
                process=process,
                ping=ping_native,
                timeout_seconds=readiness_timeout_seconds,
                poll_seconds=0.5,
            )
            result.port = record.port
            discovery.snapshot_owned_record(record, artifact_dir)
            env = self.build_smoke_env(
                base_env=None,
                pid=process.pid,
                port=record.port,
                command=smoke_command,
            )
            self.run_smoke_command(result=result, command=smoke_command, env=env, cwd=smoke_cwd)
            self.copy_rook_temp_artifacts(result=result, temp_rook_dir=DEFAULT_DISCOVERY_DIR, label="before-shutdown")
        except Exception as exc:
            result.warnings.append(f"harness failure: {exc!r}")
            self.copy_rook_temp_artifacts(result=result, temp_rook_dir=DEFAULT_DISCOVERY_DIR, label="failure")
        finally:
            already_exited_before_cleanup = process.poll() is not None
            forced = False
            force_failed = False
            try:
                if process.poll() is None:
                    forced = self.request_external_graceful_close(process, cleanup_timeout_seconds)
            except Exception as exc:
                force_failed = True
                result.warnings.append(f"cleanup failed: {exc!r}")

            discovery_leftover = discovery.owned_path(process.pid).exists()
            process_exited_after_cleanup = process.poll() is not None
            self.classify_cleanup(
                result,
                already_exited_before_cleanup=already_exited_before_cleanup,
                process_exited_after_cleanup=process_exited_after_cleanup,
                discovery_leftover=discovery_leftover,
                forced=forced,
                force_failed=force_failed,
            )
            self.write_manifest(result)

        return result
```

- [ ] **Step 6: Run unit tests**

Run:

```powershell
cd mcp_server
pytest tests/test_runtime_harness.py tests/test_live_harness_scoping.py -v
```

Expected: pass.

- [ ] **Step 7: Run CLI help**

Run:

```powershell
python scripts/run_rhino_runtime_harness.py --help
```

Expected: usage output with `--rhino-exe`, `--artifact-root`, and `--smoke`.

- [ ] **Step 8: Commit**

```powershell
git add mcp_server/src/rook/runtime_harness.py scripts/run_rhino_runtime_harness.py mcp_server/tests/test_runtime_harness.py
git commit -m "feat: add Rhino runtime harness entry point"
```

## Task 9: Documentation and Final Verification

**Files:**
- Modify: `BUILDING.md`

- [ ] **Step 1: Update live testing docs**

Modify `BUILDING.md` after the live integration tests section:

```markdown
### Owned Rhino runtime harness

For repeatable local smoke runs where the tool should own Rhino's process
lifecycle, use the runtime harness:

```powershell
python scripts\run_rhino_runtime_harness.py --smoke pytest-select
```

The harness starts one Rhino process, waits only for
`%TEMP%\rook\instance-{PID}-native.json` for that owned PID, pings the exact
discovered RookNative port, runs a tiny selected live smoke with
`ROOK_RHINO_PORT` and `ROOK_RHINO_PROCESS_ID`, captures `%TEMP%\rook` artifacts
under `.scratch\rhino-runtime-harness`, and closes only the Rhino process it
started.

Ambient `pytest -m requires_rhino` behavior is unchanged. When the harness env
vars are absent, live tests still discover an available Rhino and skip if none
is reachable. When the harness env vars are present, both
`ROOK_RHINO_PORT` and `ROOK_RHINO_PROCESS_ID` must be valid and reachable, or
the live test fails instead of skipping.
```

- [ ] **Step 2: Run focused unit tests**

Run:

```powershell
cd mcp_server
pytest tests/test_runtime_harness.py tests/test_live_harness_scoping.py tests/test_bridge.py -v
```

Expected: pass.

- [ ] **Step 3: Run ambient skip check**

Run with no Rhino running if possible:

```powershell
cd mcp_server
pytest tests/test_select_additive_live.py -m requires_rhino -v
```

Expected: skipped when no Rhino is reachable; no harness-mode failure when env vars are absent.

- [ ] **Step 4: Run live harness smoke only when local Rhino use is intended**

Run:

```powershell
python scripts\run_rhino_runtime_harness.py --smoke pytest-select
```

Expected on a correctly deployed local Rhino/Rook setup: process starts, exact owned discovery appears, smoke runs, artifacts are written under `.scratch\rhino-runtime-harness`, Rhino exits cleanly, and process exit code is `0`. If Rhino cannot close gracefully or leaves the owned discovery file behind, exit code is `1` and the manifest records the non-green cleanup path.

- [ ] **Step 5: Inspect manifest**

Run:

```powershell
Get-ChildItem .scratch\rhino-runtime-harness -Recurse -Filter manifest.json |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1 |
  Get-Content
```

Expected: JSON includes `pid`, `port`, `green`, `smoke.stdout`, `smoke.stderr`, `smoke.exit_code`, `cleanup.path`, and `warnings`.

- [ ] **Step 6: Commit**

```powershell
git add BUILDING.md
git commit -m "docs: document Rhino runtime harness"
```

## Self-Review Checklist

- [ ] Spec coverage: exact owned-PID discovery, exact-port ping, pytest port/PID scoping, ambient skip preservation, artifact snapshot before shutdown, cleanup classifications, no native route.
- [ ] Placeholder scan: no `TBD`, `TODO`, "add appropriate", or "similar to" instructions remain.
- [ ] Type consistency: `OwnedRhinoRecord`, `OwnedRhinoDiscovery`, `RhinoRuntimeHarness`, `SmokeCommand`, `HarnessRunResult`, and `CleanupPath` names are consistent across tasks.
- [ ] Commands are PowerShell-compatible for this Windows repo.
- [ ] No `.vcxproj` or `.vcxproj.filters` changes are included.
