# RunScript Safety Live Smoke Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a runtime-only live Rhino smoke suite that validates RunScript fail-closed behavior, prompt quarantine, recovery, and deterministic safety hook branches against a harness-owned Rhino process.

**Architecture:** Extend the existing owned Rhino runtime harness with launch-time environment overrides, smoke artifact handoff, finite smoke timeouts, and unrecovered-prompt sentinel detection. Add narrow native RunScript safety test hooks inside existing command handler files, then add a focused live pytest suite that uses direct native HTTP for command/prompt/cancel behavior and in-process MCP calls only for wrapper and preflight contracts.

**Tech Stack:** Python pytest/httpx, existing Rook MCP Python server, existing Rhino runtime harness, RookNative C++ handlers using httplib and nlohmann/json.

---

## Approved Spec

Implement against:

`docs/superpowers/specs/2026-05-19-runscript-safety-live-smoke-design.md`

Do not broaden scope into P2 dispatcher modal allowlisting or all-route mutation quarantine.

## File Structure

- Modify: `mcp_server/src/rook/runtime_harness.py`
  - Add smoke artifact env scoping.
  - Add configured smoke timeout to the manifest.
  - Add launch-time Rhino environment overrides.
  - Detect `runscript_safety_unrecovered.json`.
  - Force cleanup of the owned process when the sentinel appears.

- Modify: `scripts/run_rhino_runtime_harness.py`
  - Add smoke modes `runscript-safety` and `runscript-safety-hooks`.
  - Pin cwd/path pairs.
  - Pass finite smoke timeout and Rhino launch env overrides.

- Modify: `mcp_server/tests/test_runtime_harness.py`
  - Cover launch env overrides, artifact env handoff, smoke timeout manifest fields, sentinel detection, and CLI mode mapping.

- Modify: `pytest.ini`
  - Register `runscript_safety_live` and `runscript_safety_hooks` markers.

- Modify: `src/RookNative/Handlers/CommandHandler.h`
  - Expose test-hook helpers and endpoint handler declarations needed by both command handlers and route registration.

- Modify: `src/RookNative/Handlers/CommandHandler.cpp`
  - Implement env-gated, one-shot RunScript safety hooks.
  - Inject `prompt_unknown` and `command_timeout` probes into the production decision branches.

- Modify: `src/RookNative/Handlers/CommandInteractiveHandler.cpp`
  - Inject `cancel_prompt_active` into the post-cancel prompt poll branch.

- Modify: `src/RookNative/RookServer.cpp`
  - Register the native test-hook endpoint without adding new project files.

- Create: `mcp_server/tests/test_runscript_safety_live.py`
  - Live smoke tests for normal, prompt-state, and hooked safety contracts.

No `.vcxproj` or `.vcxproj.filters` edits are needed because all native hook code lives in existing compiled files.

---

### Task 1: Harness Manifest, Env, Timeout, And Sentinel Plumbing

**Files:**
- Modify: `mcp_server/src/rook/runtime_harness.py`
- Test: `mcp_server/tests/test_runtime_harness.py`

- [ ] **Step 1: Write failing tests for artifact env, timeout manifest, launch env, and sentinel detection**

Append these tests near the existing runtime harness flow tests in `mcp_server/tests/test_runtime_harness.py`.

```python
def test_runtime_harness_passes_artifact_dir_and_timeout_to_smoke(tmp_path: Path, monkeypatch):
    rhino_exe = tmp_path / "Rhino.exe"
    rhino_exe.write_text("fake", encoding="utf-8")
    process = FakeHarnessProcess(pid=4321, poll_results=[None, None])
    discovery = FakeHarnessDiscovery(pid=4321, port=9921)
    smoke_calls: list[tuple[list[str], dict[str, str], Path | None, float | None]] = []

    monkeypatch.setattr("rook.runtime_harness.subprocess.Popen", lambda command, **kwargs: process)
    monkeypatch.setattr("rook.runtime_harness.copy_temp_rook_artifacts", lambda *args: [])
    monkeypatch.setattr(
        "rook.runtime_harness.request_external_graceful_close",
        lambda cleanup_process, timeout_seconds, **kwargs: cleanup_process.wait(timeout_seconds) or False,
    )

    def fake_smoke(command, env_additions, cwd=None, timeout_seconds=None):
        smoke_calls.append((command, env_additions, cwd, timeout_seconds))
        return SmokeCommandResult(
            command,
            _scoped_env_subset(env_additions),
            0,
            "",
            "",
            0.01,
            timeout_seconds=timeout_seconds,
        )

    monkeypatch.setattr("rook.runtime_harness.run_smoke_command", fake_smoke)

    result = run_rhino_runtime_harness(
        rhino_exe=rhino_exe,
        artifact_root=tmp_path / "artifacts",
        smoke_command=["smoke"],
        smoke_cwd=tmp_path,
        smoke_timeout_seconds=120.0,
        discovery=discovery,
    )

    assert result.success is True
    assert smoke_calls == [
        (
            ["smoke"],
            {
                "ROOK_RHINO_PORT": "9921",
                "ROOK_RHINO_PROCESS_ID": "4321",
                "ROOK_HARNESS_ARTIFACT_DIR": str(result.artifact_dir),
            },
            tmp_path,
            120.0,
        )
    ]
    manifest = json.loads((result.artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["smoke"]["timeout_seconds"] == 120.0
    assert manifest["runscript_safety"]["unrecovered"] is False
    assert manifest["runscript_safety"]["sentinel_path"] is None


def test_runtime_harness_applies_rhino_launch_env_overrides(tmp_path: Path, monkeypatch):
    rhino_exe = tmp_path / "Rhino.exe"
    rhino_exe.write_text("fake", encoding="utf-8")
    process = FakeHarnessProcess(pid=4321, poll_results=[None, None])
    discovery = FakeHarnessDiscovery(pid=4321, port=9921)
    popen_envs: list[dict[str, str]] = []

    monkeypatch.setenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", "1")
    monkeypatch.setenv("ROOK_ENABLE_RUNSCRIPT_SAFETY_TEST_HOOKS", "ambient")

    def fake_popen(command, **kwargs):
        popen_envs.append(dict(kwargs["env"]))
        return process

    monkeypatch.setattr("rook.runtime_harness.subprocess.Popen", fake_popen)
    monkeypatch.setattr("rook.runtime_harness.copy_temp_rook_artifacts", lambda *args: [])
    monkeypatch.setattr(
        "rook.runtime_harness.run_smoke_command",
        lambda command, env_additions, cwd=None, timeout_seconds=None: SmokeCommandResult(
            command,
            _scoped_env_subset(env_additions),
            0,
            "",
            "",
            0.01,
            timeout_seconds=timeout_seconds,
        ),
    )
    monkeypatch.setattr(
        "rook.runtime_harness.request_external_graceful_close",
        lambda cleanup_process, timeout_seconds, **kwargs: cleanup_process.wait(timeout_seconds) or False,
    )

    result = run_rhino_runtime_harness(
        rhino_exe=rhino_exe,
        artifact_root=tmp_path / "artifacts",
        smoke_command=["smoke"],
        launch_env_overrides={
            "ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING": None,
            "ROOK_ENABLE_RUNSCRIPT_SAFETY_TEST_HOOKS": "1",
        },
        discovery=discovery,
    )

    assert result.success is True
    assert popen_envs
    assert "ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING" not in popen_envs[0]
    assert popen_envs[0]["ROOK_ENABLE_RUNSCRIPT_SAFETY_TEST_HOOKS"] == "1"


def test_runtime_harness_unrecovered_sentinel_forces_owned_cleanup(tmp_path: Path, monkeypatch):
    rhino_exe = tmp_path / "Rhino.exe"
    rhino_exe.write_text("fake", encoding="utf-8")
    process = FakeHarnessProcess(pid=4321, poll_results=[None, 1])
    discovery = FakeHarnessDiscovery(pid=4321, port=9921)
    forced: list[int] = []
    graceful_calls: list[object] = []

    monkeypatch.setattr("rook.runtime_harness.subprocess.Popen", lambda command, **kwargs: process)
    monkeypatch.setattr("rook.runtime_harness.copy_temp_rook_artifacts", lambda *args: [])
    monkeypatch.setattr(
        "rook.runtime_harness.request_external_graceful_close",
        lambda *args, **kwargs: graceful_calls.append(args) or False,
    )
    monkeypatch.setattr(
        "rook.runtime_harness.force_owned_process_cleanup",
        lambda cleanup_process, diagnostics: forced.append(cleanup_process.pid) or True,
    )

    def fake_smoke(command, env_additions, cwd=None, timeout_seconds=None):
        sentinel = Path(env_additions["ROOK_HARNESS_ARTIFACT_DIR"]) / "runscript_safety_unrecovered.json"
        sentinel.write_text(json.dumps({"reason": "test"}), encoding="utf-8")
        return SmokeCommandResult(
            command,
            _scoped_env_subset(env_additions),
            2,
            "",
            "unrecovered",
            0.01,
            timeout_seconds=timeout_seconds,
        )

    monkeypatch.setattr("rook.runtime_harness.run_smoke_command", fake_smoke)

    result = run_rhino_runtime_harness(
        rhino_exe=rhino_exe,
        artifact_root=tmp_path / "artifacts",
        smoke_command=["smoke"],
        discovery=discovery,
    )

    assert result.success is False
    assert forced == [4321]
    assert graceful_calls == []
    assert result.runscript_safety_unrecovered_path == result.artifact_dir / "runscript_safety_unrecovered.json"
    manifest = json.loads((result.artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["runscript_safety"]["unrecovered"] is True
    assert manifest["runscript_safety"]["sentinel_path"] == str(result.artifact_dir / "runscript_safety_unrecovered.json")
```

- [ ] **Step 2: Run the failing harness tests**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'
python -m pytest mcp_server/tests/test_runtime_harness.py::test_runtime_harness_passes_artifact_dir_and_timeout_to_smoke mcp_server/tests/test_runtime_harness.py::test_runtime_harness_applies_rhino_launch_env_overrides mcp_server/tests/test_runtime_harness.py::test_runtime_harness_unrecovered_sentinel_forces_owned_cleanup -q
```

Expected: FAIL because `SmokeCommandResult` has no `timeout_seconds`, `run_rhino_runtime_harness` has no `launch_env_overrides`, no artifact dir env is passed, no sentinel field exists, and `force_owned_process_cleanup` is not defined.

- [ ] **Step 3: Update harness dataclasses and scoped env**

In `mcp_server/src/rook/runtime_harness.py`, change the env keys and dataclasses as follows.

```python
HARNESS_ENV_KEYS = (
    "ROOK_RHINO_PORT",
    "ROOK_RHINO_PROCESS_ID",
    "NATIVE_PORT",
    "ROOK_HARNESS_ARTIFACT_DIR",
)
RUNSCRIPT_SAFETY_UNRECOVERED_SENTINEL = "runscript_safety_unrecovered.json"
```

Update `SmokeCommandResult`:

```python
@dataclass(frozen=True)
class SmokeCommandResult:
    command: list[str]
    scoped_env: dict[str, str]
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    timeout_seconds: float | None = None

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def to_manifest_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "scoped_env": self.scoped_env,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_seconds": self.duration_seconds,
            "timed_out": self.timed_out,
            "timeout_seconds": self.timeout_seconds,
        }
```

Update `RhinoHarnessResult`:

```python
@dataclass(frozen=True)
class RhinoHarnessResult:
    run_id: str
    artifact_dir: Path
    pid: int
    port: int
    ready_record_path: Path | None = None
    smoke: SmokeCommandResult | None = None
    cleanup_status: CleanupStatus = CleanupStatus.NOT_ATTEMPTED
    run_started_at: float = field(default_factory=time.time)
    warnings: list[str] = field(default_factory=list)
    runscript_safety_unrecovered_path: Path | None = None

    @property
    def success(self) -> bool:
        return (
            self.runscript_safety_unrecovered_path is None
            and self.smoke is not None
            and self.smoke.succeeded
            and self.cleanup_status == CleanupStatus.GRACEFUL_EXIT
        )
```

In `to_manifest_dict()`, add the RunScript safety section:

```python
            "runscript_safety": {
                "unrecovered": self.runscript_safety_unrecovered_path is not None,
                "sentinel_path": (
                    str(self.runscript_safety_unrecovered_path)
                    if self.runscript_safety_unrecovered_path
                    else None
                ),
            },
```

- [ ] **Step 4: Preserve timeout_seconds in run_smoke_command**

In `run_smoke_command()`, include `timeout_seconds=timeout_seconds` in both return sites.

```python
            return SmokeCommandResult(
                command=command,
                scoped_env=scoped_env,
                returncode=124,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=duration_seconds,
                timed_out=True,
                timeout_seconds=timeout_seconds,
            )
```

```python
    return SmokeCommandResult(
        command=command,
        scoped_env=scoped_env,
        returncode=process.returncode if process.returncode is not None else 0,
        stdout=stdout,
        stderr=stderr,
        duration_seconds=duration_seconds,
        timeout_seconds=timeout_seconds,
    )
```

- [ ] **Step 5: Add launch env override and force cleanup helpers**

Add these helpers near the smoke process helpers in `mcp_server/src/rook/runtime_harness.py`.

```python
def _apply_env_overrides(
    base_env: dict[str, str],
    overrides: dict[str, str | None] | None,
) -> dict[str, str]:
    env = dict(base_env)
    for key, value in (overrides or {}).items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = str(value)
    return env


def _runscript_safety_unrecovered_path(artifact_dir: Path) -> Path:
    return artifact_dir / RUNSCRIPT_SAFETY_UNRECOVERED_SENTINEL


def force_owned_process_cleanup(process: ProcessLike, diagnostics: list[str]) -> bool:
    if process.poll() is not None:
        return True

    if os.name == "nt":
        try:
            completed = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            diagnostics.append(f"forced owned Rhino cleanup failed: {exc}")
            return False
        if completed.returncode != 0:
            diagnostics.append(
                "forced owned Rhino cleanup failed: "
                f"{completed.stderr.strip() or completed.stdout.strip()}"
            )
            return False
    else:
        try:
            process.kill()
        except OSError as exc:
            diagnostics.append(f"forced owned Rhino cleanup failed: {exc}")
            return False

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return True
        time.sleep(0.05)
    diagnostics.append(f"forced owned Rhino cleanup did not exit pid {process.pid}")
    return False
```

- [ ] **Step 6: Thread launch overrides, artifact env, and sentinel detection through the harness**

Update the `run_rhino_runtime_harness()` signature:

```python
def run_rhino_runtime_harness(
    *,
    rhino_exe: Path,
    artifact_root: Path,
    smoke_command: list[str],
    smoke_kind: str = "pytest-select",
    smoke_cwd: Path | None = None,
    smoke_timeout_seconds: float | None = None,
    launch_env_overrides: dict[str, str | None] | None = None,
    discovery: OwnedRhinoDiscovery | None = None,
    temp_rook_dir: Path = DEFAULT_DISCOVERY_DIR,
    readiness_timeout_seconds: float = 30.0,
    readiness_poll_seconds: float = 0.25,
    cleanup_timeout_seconds: float = 10.0,
    keep_rhino_on_failure: bool = False,
) -> RhinoHarnessResult:
```

Replace Rhino launch:

```python
        process = subprocess.Popen(
            [str(rhino_exe)],
            env=_apply_env_overrides(os.environ, launch_env_overrides),
        )
```

Add artifact dir to `smoke_env`:

```python
                smoke_env = {
                    "ROOK_RHINO_PORT": str(record.port),
                    "ROOK_RHINO_PROCESS_ID": str(record.pid),
                    "ROOK_HARNESS_ARTIFACT_DIR": str(artifact_dir),
                }
```

After `result = replace(result, smoke=smoke)`, check the sentinel before any further Rhino HTTP cleanup call:

```python
                    sentinel_path = _runscript_safety_unrecovered_path(artifact_dir)
                    if sentinel_path.exists():
                        result = replace(result, runscript_safety_unrecovered_path=sentinel_path)
                        warnings.append(
                            f"RunScript safety smoke reported unrecovered Rhino state: {sentinel_path}"
                        )
```

Then skip `save_owned_document_for_cleanup()` when the sentinel exists. Replace the current save/copy block with this structure:

```python
                    if result.runscript_safety_unrecovered_path is None:
                        if smoke_kind != "ping-only":
                            save_owned_document_for_cleanup(record, artifact_dir, warnings)
                    else:
                        warnings.append(
                            "Skipping Rhino document save after unrecovered RunScript safety state."
                        )
                    copy_temp_rook_artifacts(result, temp_rook_dir, "before-shutdown")
```

Do not make any Rhino HTTP requests after the unrecovered sentinel has been observed. The remaining cleanup path must be owned-process force cleanup only.

In the cleanup `finally`, before graceful cleanup, compute:

```python
        unrecovered_runscript_state = result.runscript_safety_unrecovered_path is not None
```

Then replace the cleanup branch:

```python
        elif unrecovered_runscript_state:
            forced = force_owned_process_cleanup(process, warnings)
            force_failed = not forced
        elif not already_exited_before_cleanup:
```

- [ ] **Step 7: Run the focused harness tests again**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'
python -m pytest mcp_server/tests/test_runtime_harness.py::test_runtime_harness_passes_artifact_dir_and_timeout_to_smoke mcp_server/tests/test_runtime_harness.py::test_runtime_harness_applies_rhino_launch_env_overrides mcp_server/tests/test_runtime_harness.py::test_runtime_harness_unrecovered_sentinel_forces_owned_cleanup -q
```

Expected: PASS.

- [ ] **Step 8: Run all runtime harness unit tests and update expected manifests if needed**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'
python -m pytest mcp_server/tests/test_runtime_harness.py -q
```

Expected: PASS.

Update existing tests that stub `subprocess.Popen` to accept keyword arguments, because Rhino launch now passes `env=...`. Change stubs like:

```python
monkeypatch.setattr("rook.runtime_harness.subprocess.Popen", lambda command: process)
```

to:

```python
monkeypatch.setattr("rook.runtime_harness.subprocess.Popen", lambda command, **kwargs: process)
```

Update existing exact smoke env assertions to include `ROOK_HARNESS_ARTIFACT_DIR`. For example:

```python
{
    "ROOK_RHINO_PORT": "9921",
    "ROOK_RHINO_PROCESS_ID": "4321",
    "ROOK_HARNESS_ARTIFACT_DIR": str(result.artifact_dir),
}
```

For `rhino-operational`, include both artifact dir and `NATIVE_PORT`:

```python
{
    "ROOK_RHINO_PORT": "9921",
    "ROOK_RHINO_PROCESS_ID": "4321",
    "ROOK_HARNESS_ARTIFACT_DIR": str(result.artifact_dir),
    "NATIVE_PORT": "9921",
}
```

If existing exact manifest tests fail because `smoke.timeout_seconds` or `runscript_safety` is now present, update their expected dictionaries to include:

```python
"timeout_seconds": None,
```

inside `manifest["smoke"]`, and:

```python
"runscript_safety": {
    "sentinel_path": None,
    "unrecovered": False,
},
```

at the top level.

- [ ] **Step 9: Commit harness core plumbing**

```powershell
git add mcp_server/src/rook/runtime_harness.py mcp_server/tests/test_runtime_harness.py
git commit -m "test: add runscript safety harness plumbing"
```

---

### Task 2: Runtime Harness CLI Smoke Modes

**Files:**
- Modify: `scripts/run_rhino_runtime_harness.py`
- Test: `mcp_server/tests/test_runtime_harness.py`

- [ ] **Step 1: Write failing CLI mapping tests**

Append these tests near the existing CLI smoke mapping tests in `mcp_server/tests/test_runtime_harness.py`.

```python
def test_runtime_harness_maps_runscript_safety_smoke():
    module = _load_harness_cli_module()
    repo_root = Path(__file__).resolve().parents[2]

    command, cwd = module._smoke_command("runscript-safety", repo_root)

    assert cwd == repo_root / "mcp_server"
    assert command == [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_runscript_safety_live.py",
        "-m",
        "requires_rhino and runscript_safety_live and not runscript_safety_hooks",
        "-v",
    ]
    assert module._smoke_timeout_seconds("runscript-safety") == 120.0
    assert module._launch_env_overrides("runscript-safety") == {
        "ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING": None,
        "ROOK_ENABLE_RUNSCRIPT_SAFETY_TEST_HOOKS": None,
    }


def test_runtime_harness_maps_runscript_safety_hooks_smoke():
    module = _load_harness_cli_module()
    repo_root = Path(__file__).resolve().parents[2]

    command, cwd = module._smoke_command("runscript-safety-hooks", repo_root)

    assert cwd == repo_root / "mcp_server"
    assert command == [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_runscript_safety_live.py",
        "-m",
        "requires_rhino and runscript_safety_live and runscript_safety_hooks",
        "-v",
    ]
    assert module._smoke_timeout_seconds("runscript-safety-hooks") == 120.0
    assert module._launch_env_overrides("runscript-safety-hooks") == {
        "ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING": None,
        "ROOK_ENABLE_RUNSCRIPT_SAFETY_TEST_HOOKS": "1",
    }
```

- [ ] **Step 2: Run the failing CLI mapping tests**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'
python -m pytest mcp_server/tests/test_runtime_harness.py::test_runtime_harness_maps_runscript_safety_smoke mcp_server/tests/test_runtime_harness.py::test_runtime_harness_maps_runscript_safety_hooks_smoke -q
```

Expected: FAIL because the new smoke modes and helper functions do not exist.

- [ ] **Step 3: Add smoke modes and launch env helpers**

In `scripts/run_rhino_runtime_harness.py`, add:

```python
RUNSCRIPT_SAFETY_TIMEOUT_SECONDS = 120.0
```

Extend `_smoke_command()`:

```python
    if name == "runscript-safety":
        return (
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_runscript_safety_live.py",
                "-m",
                "requires_rhino and runscript_safety_live and not runscript_safety_hooks",
                "-v",
            ],
            repo_root / "mcp_server",
        )
    if name == "runscript-safety-hooks":
        return (
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_runscript_safety_live.py",
                "-m",
                "requires_rhino and runscript_safety_live and runscript_safety_hooks",
                "-v",
            ],
            repo_root / "mcp_server",
        )
```

Add helper functions below `_smoke_command()`:

```python
def _smoke_timeout_seconds(name: str) -> float | None:
    if name in {"runscript-safety", "runscript-safety-hooks"}:
        return RUNSCRIPT_SAFETY_TIMEOUT_SECONDS
    return None


def _launch_env_overrides(name: str) -> dict[str, str | None]:
    if name == "runscript-safety":
        return {
            "ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING": None,
            "ROOK_ENABLE_RUNSCRIPT_SAFETY_TEST_HOOKS": None,
        }
    if name == "runscript-safety-hooks":
        return {
            "ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING": None,
            "ROOK_ENABLE_RUNSCRIPT_SAFETY_TEST_HOOKS": "1",
        }
    return {}
```

Extend parser choices:

```python
            "runscript-safety",
            "runscript-safety-hooks",
```

Pass the helpers into `run_rhino_runtime_harness()`:

```python
        smoke_timeout_seconds=_smoke_timeout_seconds(args.smoke),
        launch_env_overrides=_launch_env_overrides(args.smoke),
```

- [ ] **Step 4: Run CLI mapping tests**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'
python -m pytest mcp_server/tests/test_runtime_harness.py::test_runtime_harness_maps_runscript_safety_smoke mcp_server/tests/test_runtime_harness.py::test_runtime_harness_maps_runscript_safety_hooks_smoke -q
```

Expected: PASS.

- [ ] **Step 5: Run all runtime harness tests**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'
python -m pytest mcp_server/tests/test_runtime_harness.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit CLI smoke modes**

```powershell
git add scripts/run_rhino_runtime_harness.py mcp_server/tests/test_runtime_harness.py
git commit -m "test: add runscript safety smoke modes"
```

---

### Task 3: Native RunScript Safety Test Hooks

**Files:**
- Modify: `src/RookNative/Handlers/CommandHandler.h`
- Modify: `src/RookNative/Handlers/CommandHandler.cpp`
- Modify: `src/RookNative/Handlers/CommandInteractiveHandler.cpp`
- Modify: `src/RookNative/RookServer.cpp`

- [ ] **Step 1: Add hook declarations to CommandHandler.h**

Modify `src/RookNative/Handlers/CommandHandler.h`:

```cpp
void HandleCommand(const httplib::Request& req, httplib::Response& res);
void HandleExecute(const httplib::Request& req, httplib::Response& res);
void HandleRunScriptSafetyTestHook(const httplib::Request& req, httplib::Response& res);
void ClearCommandStateUncertain();
bool ConsumeRunScriptSafetyTestHook(const char* hookName);
bool RunScriptSafetyTestHooksEnabled();
```

- [ ] **Step 2: Implement env-gated one-shot hook state in CommandHandler.cpp**

In `src/RookNative/Handlers/CommandHandler.cpp`, add `<cstdlib>` to the includes.

```cpp
#include <cstdlib>
```

Near `s_commandStateUncertain`, add hook atomics:

```cpp
static std::atomic<bool> s_testHookPromptUnknown{false};
static std::atomic<bool> s_testHookCommandTimeout{false};
static std::atomic<bool> s_testHookCancelPromptActive{false};
```

Inside the `Rook::Handlers` namespace, before `HandleCommand`, add:

```cpp
bool RunScriptSafetyTestHooksEnabled()
{
    const char* env = std::getenv("ROOK_ENABLE_RUNSCRIPT_SAFETY_TEST_HOOKS");
    return env != nullptr && std::string(env) == "1";
}

bool ConsumeRunScriptSafetyTestHook(const char* hookName)
{
    if (!RunScriptSafetyTestHooksEnabled() || hookName == nullptr)
        return false;

    std::string name(hookName);
    if (name == "prompt_unknown")
        return s_testHookPromptUnknown.exchange(false, std::memory_order_acq_rel);
    if (name == "command_timeout")
        return s_testHookCommandTimeout.exchange(false, std::memory_order_acq_rel);
    if (name == "cancel_prompt_active")
        return s_testHookCancelPromptActive.exchange(false, std::memory_order_acq_rel);
    return false;
}

void HandleRunScriptSafetyTestHook(const httplib::Request& req, httplib::Response& res)
{
    if (!RunScriptSafetyTestHooksEnabled())
    {
        nlohmann::json data;
        data["error"] = "runscript_safety_test_hooks_disabled";
        data["verified"] = false;
        data["recovery"] = "Launch the owned Rhino smoke process with ROOK_ENABLE_RUNSCRIPT_SAFETY_TEST_HOOKS=1.";
        CRookServer::SendErrorData(res, data);
        return;
    }

    nlohmann::json body;
    if (!req.body.empty())
        body = nlohmann::json::parse(req.body, nullptr, false);
    if (body.is_discarded() || !body.is_object())
    {
        CRookServer::SendError(res, "Invalid JSON body");
        return;
    }

    std::string hook = body.value("hook", "");
    bool enabled = body.value("enabled", true);

    if (hook == "reset")
    {
        s_testHookPromptUnknown.store(false, std::memory_order_release);
        s_testHookCommandTimeout.store(false, std::memory_order_release);
        s_testHookCancelPromptActive.store(false, std::memory_order_release);
        CRookServer::SendSuccess(res, {{"reset", true}});
        return;
    }

    if (hook == "prompt_unknown")
        s_testHookPromptUnknown.store(enabled, std::memory_order_release);
    else if (hook == "command_timeout")
        s_testHookCommandTimeout.store(enabled, std::memory_order_release);
    else if (hook == "cancel_prompt_active")
        s_testHookCancelPromptActive.store(enabled, std::memory_order_release);
    else
    {
        CRookServer::SendError(res, "Unknown RunScript safety test hook");
        return;
    }

    nlohmann::json data;
    data["hook"] = hook;
    data["enabled"] = enabled;
    data["one_shot"] = true;
    CRookServer::SendSuccess(res, data);
}
```

- [ ] **Step 3: Inject prompt_unknown into TryReadCommandPrompt**

At the top of `TryReadCommandPrompt()` in `CommandHandler.cpp`, add:

```cpp
        if (ConsumeRunScriptSafetyTestHook("prompt_unknown"))
            return {CommandPromptState::Unknown, ""};
```

- [ ] **Step 4: Inject command_timeout into HandleCommand**

Replace the `/command` wait branch with:

```cpp
        const bool simulateTimeout = ConsumeRunScriptSafetyTestHook("command_timeout");
        if (simulateTimeout || future.wait_for(kCommandRunTimeout) != std::future_status::ready)
        {
            s_commandStateUncertain.store(true, std::memory_order_release);
            CRookServer::SendErrorData(res, BuildCommandTimeoutError(command));
            return;
        }
```

This deliberately reuses the production timeout branch and sets native state uncertain.

- [ ] **Step 5: Inject cancel_prompt_active into post-cancel polling**

In `src/RookNative/Handlers/CommandInteractiveHandler.cpp`, at the start of `PollForIdlePromptAfterCancel()`, add:

```cpp
    if (ConsumeRunScriptSafetyTestHook("cancel_prompt_active"))
        return {PromptReadState::Active, "RunScript safety test hook active prompt"};
```

- [ ] **Step 6: Register the hook endpoint**

In `src/RookNative/RookServer.cpp`, near command interactive route registration, add:

```cpp
    m_server->Post("/command/_test/runscript-safety-hook", [this](const httplib::Request& req, httplib::Response& res) {
        HandleRunScriptSafetyTestHook(req, res);
    });
```

- [ ] **Step 7: Build native plugin**

Run:

```powershell
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected: Build succeeds with `0 errors`.

- [ ] **Step 8: Commit native hook probes**

```powershell
git add src/RookNative/Handlers/CommandHandler.h src/RookNative/Handlers/CommandHandler.cpp src/RookNative/Handlers/CommandInteractiveHandler.cpp src/RookNative/RookServer.cpp
git commit -m "test: add runscript safety native hooks"
```

---

### Task 4: Live Smoke Test Helpers And Normal-Mode Tests

**Files:**
- Modify: `pytest.ini`
- Create: `mcp_server/tests/test_runscript_safety_live.py`

- [ ] **Step 1: Register pytest markers**

Update `pytest.ini`:

```ini
[pytest]
markers =
    requires_rhino: integration test that requires a live Rhino session with the plugin loaded
    runscript_safety_live: live RunScript safety smoke tests for an owned Rhino runtime
    runscript_safety_hooks: RunScript safety smoke tests that require native test hooks at Rhino launch
```

- [ ] **Step 2: Create live test file with helpers and guards**

Create `mcp_server/tests/test_runscript_safety_live.py` with this initial content.

```python
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from .conftest import _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.runscript_safety_live]

REQUEST_TIMEOUT = 3.0
PROMPT_RECOVERY_DEADLINE_SECONDS = 5.0


def _owned_port() -> int:
    value = os.environ.get("ROOK_RHINO_PORT")
    assert value is not None and value.isdigit() and int(value) > 0
    return int(value)


def _owned_pid() -> int:
    value = os.environ.get("ROOK_RHINO_PROCESS_ID")
    assert value is not None and value.isdigit() and int(value) > 0
    return int(value)


def _artifact_dir() -> Path:
    value = os.environ.get("ROOK_HARNESS_ARTIFACT_DIR")
    assert value, "ROOK_HARNESS_ARTIFACT_DIR must be set by the runtime harness"
    path = Path(value)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _base_url() -> str:
    return f"http://127.0.0.1:{_owned_port()}"


def _assert_not_parallel(config: pytest.Config | None = None) -> None:
    assert os.environ.get("PYTEST_XDIST_WORKER") is None, (
        "RunScript safety live smoke tests must run serially, not under pytest-xdist"
    )
    if config is not None:
        assert not hasattr(config, "workerinput"), (
            "RunScript safety live smoke tests must run serially, not under pytest-xdist"
        )


def _native_get(path: str) -> dict[str, Any]:
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        response = client.get(f"{_base_url()}{path}")
    try:
        return response.json()
    except ValueError as exc:
        pytest.fail(f"{path} returned non-JSON response: {response.text!r} ({exc!r})")


def _native_post(path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        response = client.post(f"{_base_url()}{path}", json=body or {})
    try:
        return response.json()
    except ValueError as exc:
        pytest.fail(f"{path} returned non-JSON response: {response.text!r} ({exc!r})")


def _prompt_text(payload: dict[str, Any]) -> str:
    data = payload.get("data")
    if not isinstance(data, dict):
        return ""
    prompt = data.get("prompt")
    return prompt if isinstance(prompt, str) else ""


def _is_idle_prompt_text(prompt: str) -> bool:
    return prompt == "" or prompt == "Command" or prompt.startswith("Command:")


def _is_idle_prompt_response(payload: dict[str, Any]) -> bool:
    data = payload.get("data")
    return (
        payload.get("success") is True
        and isinstance(data, dict)
        and data.get("is_active") is False
        and _is_idle_prompt_text(str(data.get("prompt") or ""))
    )


def _is_verified_cancel_response(payload: dict[str, Any]) -> bool:
    data = payload.get("data")
    return (
        payload.get("success") is True
        and isinstance(data, dict)
        and data.get("cancelled") is True
        and data.get("verified") is True
        and data.get("is_active") is False
        and _is_idle_prompt_text(str(data.get("prompt") or ""))
    )


def _write_unrecovered_sentinel(
    request: pytest.FixtureRequest,
    *,
    reason: str,
    last_command: dict[str, Any] | None = None,
    last_cancel: dict[str, Any] | None = None,
    last_prompt: dict[str, Any] | None = None,
) -> Path:
    sentinel = _artifact_dir() / "runscript_safety_unrecovered.json"
    sentinel.write_text(
        json.dumps(
            {
                "test": request.node.nodeid,
                "reason": reason,
                "pid": _owned_pid(),
                "port": _owned_port(),
                "last_command": last_command,
                "last_cancel": last_cancel,
                "last_prompt": last_prompt,
                "timestamp": time.time(),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return sentinel


def _kill_owned_pid() -> None:
    pid = _owned_pid()
    assert pid > 0
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )


def _ensure_idle_or_abort(request: pytest.FixtureRequest) -> None:
    prompt = _native_get("/command/prompt")
    if _is_idle_prompt_response(prompt):
        return

    cancel = _native_post("/command/cancel")
    deadline = time.monotonic() + PROMPT_RECOVERY_DEADLINE_SECONDS
    last_prompt = prompt
    while time.monotonic() < deadline:
        last_prompt = _native_get("/command/prompt")
        if _is_idle_prompt_response(last_prompt):
            return
        time.sleep(0.1)

    _write_unrecovered_sentinel(
        request,
        reason="could_not_verify_idle_prompt",
        last_cancel=cancel,
        last_prompt=last_prompt,
    )
    _kill_owned_pid()
    pytest.exit("RunScript safety smoke could not verify idle Rhino prompt", returncode=2)


def _require_verified_cancel_or_abort(request: pytest.FixtureRequest) -> None:
    cancel = _native_post("/command/cancel")
    prompt = _native_get("/command/prompt")
    if _is_verified_cancel_response(cancel) and _is_idle_prompt_response(prompt):
        return

    _write_unrecovered_sentinel(
        request,
        reason="cancel_did_not_verify_idle",
        last_cancel=cancel,
        last_prompt=prompt,
    )
    _kill_owned_pid()
    pytest.exit("RunScript safety smoke could not verify cancel recovery", returncode=2)


def setup_module(module):
    _assert_not_parallel()


@pytest.fixture
def owned_rhino_runtime(request):
    _assert_not_parallel(request.config)
    ping = _native_get("/ping")
    assert ping.get("success") is True or ping.get("data") == "pong" or ping == {"success": True}
    return {"port": _owned_port(), "pid": _owned_pid(), "base_url": _base_url()}


@pytest.fixture
def prompt_recovery_guard(request):
    _assert_not_parallel(request.config)
    _ensure_idle_or_abort(request)
    yield
    _require_verified_cancel_or_abort(request)
```

`prompt_recovery_guard` deliberately calls `/command/cancel` and requires verified cancel recovery after every hazardous/hooked test, even if `/command/prompt` already appears idle. Prompt observation alone does not clear native `/command` uncertainty.

- [ ] **Step 3: Add normal-mode tests**

Append these tests to `mcp_server/tests/test_runscript_safety_live.py`.

```python
def test_native_prompt_and_cancel_idle_contracts(owned_rhino_runtime):
    prompt = _native_get("/command/prompt")
    assert _is_idle_prompt_response(prompt), prompt

    cancel = _native_post("/command/cancel")
    assert _is_verified_cancel_response(cancel), cancel


def test_native_start_and_send_refused_in_normal_mode(owned_rhino_runtime):
    start = _native_post("/command/start", {"command": "_Line"})
    send = _native_post("/command/send", {"input": "0,0,0"})

    for payload in (start, send):
        assert payload.get("success") is False
        data = payload.get("data")
        assert isinstance(data, dict)
        assert data.get("error") == "interactive_command_deprecated"
        assert data.get("verified") is False


def test_native_command_allows_harmless_complete_command(owned_rhino_runtime):
    result = _native_post("/command", {"command": "_SelNone", "echo": False})
    assert result.get("success") is True, result
    data = result.get("data")
    assert isinstance(data, dict)
    assert data.get("executed") is True
    assert data.get("command") == "_SelNone"


@pytest.mark.asyncio
async def test_mcp_prompt_and_cancel_wrappers_preserve_native_success(owned_rhino_runtime):
    from rook.server import _mcp_tool_executor

    prompt = await _mcp_tool_executor("rhino_command_interactive_prompt", {})
    assert prompt.get("success") is True
    assert isinstance(prompt.get("data"), dict)
    assert prompt["data"].get("is_active") is False

    cancel = await _mcp_tool_executor("rhino_command_interactive_cancel", {})
    assert cancel.get("success") is True
    assert isinstance(cancel.get("data"), dict)
    assert cancel["data"].get("cancelled") is True
    assert cancel["data"].get("verified") is True


@pytest.mark.asyncio
async def test_mcp_rhino_command_rejects_before_native_command(monkeypatch):
    from rook import server

    calls: list[tuple[str, str, object]] = []

    async def fake_call_rhino(endpoint, method="GET", data=None, **kwargs):
        calls.append((endpoint, method, data))
        raise AssertionError("rhino_command preflight must not call native /command")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(server.command_learner, "knowledge_store", None)

    result = await server._mcp_tool_executor("rhino_command", {"command": "_-Line"})

    assert result.get("success") is False
    assert isinstance(result.get("data"), dict)
    assert result["data"].get("error") == "run_script_safety_refusal"
    assert result["data"].get("reason") == "command_safety_unavailable"
    assert calls == []


@pytest.mark.asyncio
async def test_mcp_rhino_command_allows_explicit_safe_metadata(monkeypatch, owned_rhino_runtime):
    from rook import server

    class SafeSelNoneStore:
        def parse_command_string(self, command_string):
            return {
                "command": "-SelNone",
                "mode": "default",
                "syntax": "_SelNone",
                "parameters": {},
                "options_used": [],
            }

        def get_command(self, command):
            if command != "-SelNone":
                return None
            return {
                "preconditions": {"safe_non_interactive": True},
                "modes": {"default": {"syntax": "_SelNone"}},
                "options": {},
            }

    monkeypatch.setattr(server.command_learner, "knowledge_store", SafeSelNoneStore())

    result = await server._mcp_tool_executor("rhino_command", {"command": "_SelNone"})

    assert result.get("success") is True, result
    assert isinstance(result.get("data"), dict)
    assert result["data"].get("executed") is True


@pytest.mark.asyncio
async def test_deprecated_prompt_driving_tools_not_listed_in_normal_tools():
    from rook.server import list_tools

    names = {tool.name for tool in await list_tools()}

    assert "rhino_command_interactive_start" not in names
    assert "rhino_command_interactive_send" not in names
    assert "rhino_learn_interactive" not in names
    assert "rhino_learn_variations_interactive" not in names
    assert "rhino_command_interactive_prompt" in names
    assert "rhino_command_interactive_cancel" in names
```

- [ ] **Step 4: Run non-live syntax/import checks**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'
python -m pytest --collect-only mcp_server/tests/test_runscript_safety_live.py -q
```

Expected: collection succeeds and lists the new tests.

- [ ] **Step 5: Run the normal live smoke mode against a deployed branch runtime**

Prerequisite: build/deploy/register this branch with the existing local testing workflow.

Run:

```powershell
python scripts/run_rhino_runtime_harness.py --smoke runscript-safety
```

Expected: PASS. The harness prints an artifact directory and exits `0`.

- [ ] **Step 6: Commit normal live tests**

```powershell
git add pytest.ini mcp_server/tests/test_runscript_safety_live.py
git commit -m "test: add runscript safety live smoke tests"
```

---

### Task 5: Prompt-State And Hooked Live Tests

**Files:**
- Modify: `mcp_server/tests/test_runscript_safety_live.py`

- [ ] **Step 1: Add active prompt/quarantine live test**

Append:

```python
def _assert_command_uncertain_failure(payload: dict[str, Any]) -> None:
    assert payload.get("success") is False, payload
    data = payload.get("data")
    assert isinstance(data, dict), payload
    assert data.get("verified") is False
    assert data.get("executed") is not True
    assert (
        data.get("state_uncertain") is True
        or data.get("waitingFor")
        or data.get("code") in {"native_command_prompt_unknown", "native_command_timeout"}
    ), payload


def test_active_prompt_quarantines_command_until_cancel(prompt_recovery_guard):
    first = _native_post("/command", {"command": "_-Line", "echo": False})
    _assert_command_uncertain_failure(first)

    refused = _native_post("/command", {"command": "_SelNone", "echo": False})
    assert refused.get("success") is False
    refused_data = refused.get("data")
    assert isinstance(refused_data, dict)
    assert refused_data.get("code") == "native_command_state_uncertain"
    assert refused_data.get("verified") is False

    cancel = _native_post("/command/cancel")
    assert _is_verified_cancel_response(cancel), cancel

    prompt = _native_get("/command/prompt")
    assert _is_idle_prompt_response(prompt), prompt

    after = _native_post("/command", {"command": "_SelNone", "echo": False})
    assert after.get("success") is True, after
```

- [ ] **Step 2: Add hook control helpers and disabled-hook test**

Append:

```python
def _set_hook(hook: str, enabled: bool = True) -> dict[str, Any]:
    return _native_post(
        "/command/_test/runscript-safety-hook",
        {"hook": hook, "enabled": enabled},
    )


def test_runscript_safety_hooks_disabled_by_default(owned_rhino_runtime):
    result = _set_hook("prompt_unknown")
    assert result.get("success") is False
    data = result.get("data")
    assert isinstance(data, dict)
    assert data.get("error") == "runscript_safety_test_hooks_disabled"
```

- [ ] **Step 3: Add hooked tests**

Append:

```python
@pytest.mark.runscript_safety_hooks
def test_hook_prompt_unknown_sets_uncertain_state(prompt_recovery_guard):
    hook = _set_hook("prompt_unknown")
    assert hook.get("success") is True, hook

    result = _native_post("/command", {"command": "_SelNone", "echo": False})

    assert result.get("success") is False
    data = result.get("data")
    assert isinstance(data, dict)
    assert data.get("code") == "native_command_prompt_unknown"
    assert data.get("verified") is False
    assert data.get("state_uncertain") is True

    refused = _native_post("/command", {"command": "_SelNone", "echo": False})
    refused_data = refused.get("data")
    assert refused.get("success") is False
    assert isinstance(refused_data, dict)
    assert refused_data.get("code") == "native_command_state_uncertain"


@pytest.mark.runscript_safety_hooks
def test_hook_command_timeout_sets_uncertain_state(prompt_recovery_guard):
    hook = _set_hook("command_timeout")
    assert hook.get("success") is True, hook

    result = _native_post("/command", {"command": "_SelNone", "echo": False})

    assert result.get("success") is False
    data = result.get("data")
    assert isinstance(data, dict)
    assert data.get("code") == "native_command_timeout"
    assert data.get("verified") is False
    assert data.get("state_uncertain") is True

    refused = _native_post("/command", {"command": "_SelNone", "echo": False})
    refused_data = refused.get("data")
    assert refused.get("success") is False
    assert isinstance(refused_data, dict)
    assert refused_data.get("code") == "native_command_state_uncertain"


@pytest.mark.runscript_safety_hooks
def test_hook_cancel_active_prompt_preserves_uncertain_state(prompt_recovery_guard):
    first = _native_post("/command", {"command": "_-Line", "echo": False})
    _assert_command_uncertain_failure(first)

    hook = _set_hook("cancel_prompt_active")
    assert hook.get("success") is True, hook

    result = _native_post("/command/cancel")

    assert result.get("success") is False
    data = result.get("data")
    assert isinstance(data, dict)
    assert data.get("cancelled") is False
    assert data.get("verified") is False
    assert data.get("state_uncertain") is True
    assert data.get("is_active") is True

    refused = _native_post("/command", {"command": "_SelNone", "echo": False})
    refused_data = refused.get("data")
    assert refused.get("success") is False
    assert isinstance(refused_data, dict)
    assert refused_data.get("code") == "native_command_state_uncertain"
```

- [ ] **Step 4: Ensure hook state resets after hook tests**

Add this autouse fixture to `mcp_server/tests/test_runscript_safety_live.py`:

```python
@pytest.fixture(autouse=True)
def _reset_safety_hooks_after_test(request):
    yield
    if request.node.get_closest_marker("runscript_safety_hooks") is not None:
        result = _set_hook("reset")
        assert result.get("success") is True or result.get("success") is False
```

The permissive assertion handles the normal smoke mode where hooks are disabled and the reset endpoint refuses.

- [ ] **Step 5: Run collection and marker selection checks**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'
python -m pytest --collect-only mcp_server/tests/test_runscript_safety_live.py -m "requires_rhino and runscript_safety_live and not runscript_safety_hooks" -q
python -m pytest --collect-only mcp_server/tests/test_runscript_safety_live.py -m "requires_rhino and runscript_safety_live and runscript_safety_hooks" -q
```

Expected: first command lists only non-hook tests; second command lists only hook tests.

- [ ] **Step 6: Run normal and hook-enabled live smoke modes against a deployed branch runtime**

Prerequisite: rebuild/deploy/register the branch after native hook changes.

Run:

```powershell
python scripts/run_rhino_runtime_harness.py --smoke runscript-safety
python scripts/run_rhino_runtime_harness.py --smoke runscript-safety-hooks
```

Expected: both commands exit `0`. Each prints its own artifact directory. The normal-mode manifest must show hooks disabled; the hook-mode manifest must show `smoke.timeout_seconds` as `120.0`.

- [ ] **Step 7: Commit prompt-state and hooked live tests**

```powershell
git add mcp_server/tests/test_runscript_safety_live.py
git commit -m "test: cover runscript prompt quarantine hooks"
```

---

### Task 6: Final Verification And PR Notes

**Files:**
- Modify: PR description manually or via GitHub tooling after tests pass.

- [ ] **Step 1: Run Python focused suites**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'
python -m pytest mcp_server/tests/test_runtime_harness.py mcp_server/tests/test_preflight_rhino_command_safety.py mcp_server/tests/test_server_execute_safety.py -q
```

Expected: PASS.

- [ ] **Step 2: Run native build**

Run:

```powershell
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected: Build succeeds with `0 errors`.

- [ ] **Step 3: Deploy branch runtime for live smoke**

Use the existing local deployment workflow for this repo. Do not make the smoke harness build or deploy the runtime.

Record the deployment command and result in the PR notes.

- [ ] **Step 4: Run both live smoke modes**

Run:

```powershell
python scripts/run_rhino_runtime_harness.py --smoke runscript-safety
python scripts/run_rhino_runtime_harness.py --smoke runscript-safety-hooks
```

Expected: both exit `0`.

- [ ] **Step 5: Inspect harness manifests**

Open the printed artifact directories and inspect `manifest.json`.

Expected normal manifest facts:

```json
{
  "runscript_safety": {
    "unrecovered": false,
    "sentinel_path": null
  },
  "smoke": {
    "timed_out": false,
    "timeout_seconds": 120.0
  },
  "success": true
}
```

Expected hook manifest facts:

```json
{
  "runscript_safety": {
    "unrecovered": false,
    "sentinel_path": null
  },
  "smoke": {
    "timed_out": false,
    "timeout_seconds": 120.0
  },
  "success": true
}
```

- [ ] **Step 6: Run diff checks**

Run:

```powershell
git diff --check
git status --short
```

Expected: `git diff --check` prints no errors. `git status --short` shows only intentional changes if any remain uncommitted.

- [ ] **Step 7: Update draft PR description**

Add the live smoke results to PR #161:

```markdown
Live Rhino smoke:

- `python scripts/run_rhino_runtime_harness.py --smoke runscript-safety`: PASS
- `python scripts/run_rhino_runtime_harness.py --smoke runscript-safety-hooks`: PASS
- Normal smoke artifact: `<artifact-dir>`
- Hook smoke artifact: `<artifact-dir>`

Notes:

- Smoke harness is runtime-only; build/deploy remains an explicit prerequisite.
- Hook smoke launches owned Rhino with `ROOK_ENABLE_RUNSCRIPT_SAFETY_TEST_HOOKS=1` and interactive learning disabled.
- Normal smoke launches owned Rhino with interactive learning and safety hooks explicitly unset.
- `runscript_safety.unrecovered=false` in both manifests.
```

- [ ] **Step 8: Commit final verification/docs updates if any**

If PR description is the only update, no commit is needed. If any tracked docs changed during verification, commit them:

```powershell
git add <tracked-doc-paths>
git commit -m "docs: record runscript safety smoke results"
```

---

## Self-Review

### Spec Coverage

- Runtime-only harness: covered by CLI smoke modes and final deployment prerequisite.
- Owned Rhino only: covered by existing harness plus `ROOK_RHINO_PROCESS_ID` checks and PID-scoped fixture kill.
- Sanitized normal mode: covered by `_launch_env_overrides("runscript-safety")`.
- Hook mode launch-time env: covered by `_launch_env_overrides("runscript-safety-hooks")`.
- Finite smoke timeout: covered by CLI timeout helper, `SmokeCommandResult.timeout_seconds`, and manifest check.
- Bounded HTTP timeouts: covered by live helper `httpx.Client(timeout=REQUEST_TIMEOUT)`.
- Sentinel/force-kill: covered by runtime harness sentinel test and fixture sentinel write/kill.
- Prompt/cancel semantics: covered by helper predicates and normal live tests.
- MCP pre-native rejection proof: covered by in-process `call_rhino` spy.
- MCP allow metadata boundary: covered by in-process temporary `SafeSelNoneStore`.
- Natural active prompt: covered by `_-Line` quarantine test.
- Hooked unknown/timeout/cancel-active paths: covered by hook tests.
- Tool listing/deprecation: covered by normal live tests.
- P2 not overclaimed: subsequent mutation refusal uses native `/command`, not typed mutation routes.

### Placeholder Scan

The plan avoids deferred-detail markers and vague "add tests" wording. Code snippets use concrete paths, commands, expected results, and exact hook names.

### Type Consistency

- `timeout_seconds` is the new `SmokeCommandResult` field and manifest key.
- `runscript_safety_unrecovered_path` is the new `RhinoHarnessResult` field.
- Native hook names are consistent: `prompt_unknown`, `command_timeout`, `cancel_prompt_active`, `reset`.
- Smoke markers are consistent: `runscript_safety_live`, `runscript_safety_hooks`.
