# Issue #222 Rhino Launch Env Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every Python-owned Rhino launch receive a controlled Windows startup environment even when the MCP parent process was launched with stripped environment variables.

**Architecture:** Add one pure environment-construction seam in `mcp_server/src/rook/rhino_launch.py`, propagate its deterministic report through existing `LaunchEvidence`, and wire both Python Rhino launch sites through the seam. The fix preserves the `LaunchOutcome` shape while adding optional `launchEnv` evidence, then proves the bound MCP runtime, not only the repo venv.

**Tech Stack:** Python 3.10+, `dataclasses`, `ctypes` for guarded Windows discovery, `subprocess.Popen`, pytest, Rook MCP workbench tools.

---

## Context

Issue #251's gate found `rhino_workbench_launch` failed in the MCP path with `workbench_exited_before_bind`, while the direct async control succeeded. The focused #222 probe isolated the variable: the Codex-launched Rook MCP server environment lacked `windir`. Reusing that exact environment reproduced Rhino's `0xE0434352` startup crash; adding only `windir=C:\Windows` let Rhino bind and close cleanly.

This plan implements only the #222 environment hardening slice. It does not implement #251 `rhino_launch` delegation. After this plan lands and is live-proven on the bound MCP runtime, rerun the already-approved #251 launch gate from a clean/cold state before any delegation code.

## File Structure

| File | Responsibility |
| --- | --- |
| `mcp_server/src/rook/rhino_launch.py` | Owns `build_launch_env(base_env=None, os_info=None)`, Windows OS discovery, launch-env report construction, and optional `launchEnv` evidence propagation through `LaunchEvidence`, `StartedRhino`, and `LaunchExecError`. |
| `mcp_server/src/rook/workbench.py` | Uses `build_launch_env()` exactly once per owned launch, passes the built env into both `start_rhino_process(env=...)` and the patchable `workbench.subprocess.Popen` lambda, and exposes success/failure `launchEnv` evidence. |
| `mcp_server/src/rook/runtime_harness.py` | Applies harness overrides first, then runs `build_launch_env()`, passes the built env into both launch paths, and preserves `launchEnv` in `launch_outcome` / manifest. |
| `mcp_server/tests/test_rhino_launch.py` | Pure unit tests for policy, report determinism, exception-safe OS discovery, evidence JSON serialization, and exec-failure evidence propagation. |
| `mcp_server/tests/test_workbench.py` | Wiring tests for owned workbench env injection and success/failure `launchEnv` evidence. |
| `mcp_server/tests/test_runtime_harness.py` | Wiring tests for override ordering, controlled env injection, and manifest evidence. |
| `docs/superpowers/audits/2026-06-14-issue-222-rhino-launch-env-live-proof.md` | Created after implementation to record the bound-runtime #222 live proof and the separate #251 gate rerun result. |

## Implementation Tasks

### Task 1: Add Pure Launch-Env Policy Tests

**Files:**
- Modify: `mcp_server/tests/test_rhino_launch.py`

- [ ] **Step 1: Append failing pure helper tests**

Append this block after `test_outcome_to_dict_round_shape()` and before the `# ---- Task 4` comment:

```python
# ---- Issue #222: launch environment policy ----

def test_build_launch_env_authoritatively_sets_windows_invariants():
    from rook.rhino_launch import LaunchOsInfo, build_launch_env

    base = {
        "windir": r"Z:\Wrong",
        "SystemRoot": r"Y:\Wrong",
        "SystemDrive": "Y:",
        "PATH": r"C:\Tools",
    }

    result = build_launch_env(
        base,
        os_info=LaunchOsInfo(windows_dir=r"D:\Windows", windows_dir_exists=True),
    )

    assert result.env["windir"] == r"D:\Windows"
    assert result.env["SystemRoot"] == r"D:\Windows"
    assert result.env["SystemDrive"] == "D:"
    assert result.report["authoritative"] == {
        "SystemDrive": "D:",
        "SystemRoot": r"D:\Windows",
        "windir": r"D:\Windows",
    }
    assert result.report["inherited"]["PATH"] == r"C:\Tools"


def test_build_launch_env_backfills_customizables_from_non_empty_sources():
    from rook.rhino_launch import LaunchOsInfo, build_launch_env

    result = build_launch_env(
        {"USERPROFILE": r"C:\Users\Ada", "PATH": ""},
        os_info=LaunchOsInfo(windows_dir=r"C:\Windows", windows_dir_exists=True),
    )

    assert result.env["ProgramData"] == r"C:\ProgramData"
    assert result.env["APPDATA"] == r"C:\Users\Ada\AppData\Roaming"
    assert result.env["LOCALAPPDATA"] == r"C:\Users\Ada\AppData\Local"
    assert result.env["TEMP"] == r"C:\Users\Ada\AppData\Local\Temp"
    assert result.env["TMP"] == r"C:\Users\Ada\AppData\Local\Temp"
    assert result.env["PATH"] == r"C:\Windows\System32;C:\Windows"
    assert result.report["backfilled"] == {
        "APPDATA": r"C:\Users\Ada\AppData\Roaming",
        "LOCALAPPDATA": r"C:\Users\Ada\AppData\Local",
        "PATH": r"C:\Windows\System32;C:\Windows",
        "ProgramData": r"C:\ProgramData",
        "TEMP": r"C:\Users\Ada\AppData\Local\Temp",
        "TMP": r"C:\Users\Ada\AppData\Local\Temp",
    }
    assert result.report["inherited"] == {"USERPROFILE": r"C:\Users\Ada"}
    assert result.report["missing_unresolved"] == []


def test_build_launch_env_records_unresolved_customizables_without_fabricating():
    from rook.rhino_launch import LaunchOsInfo, build_launch_env

    result = build_launch_env(
        {},
        os_info=LaunchOsInfo(windows_dir=r"C:\Windows", windows_dir_exists=True),
    )

    assert result.env["windir"] == r"C:\Windows"
    assert result.env["SystemRoot"] == r"C:\Windows"
    assert result.env["SystemDrive"] == "C:"
    assert result.env["ProgramData"] == r"C:\ProgramData"
    assert result.env["PATH"] == r"C:\Windows\System32;C:\Windows"
    for name in ("APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "USERPROFILE"):
        assert name not in result.env
    assert result.report["missing_unresolved"] == [
        "APPDATA",
        "LOCALAPPDATA",
        "TEMP",
        "TMP",
        "USERPROFILE",
    ]


def test_build_launch_env_does_not_merge_present_minimal_path():
    from rook.rhino_launch import LaunchOsInfo, build_launch_env

    result = build_launch_env(
        {"PATH": r"C:\venv\Scripts"},
        os_info=LaunchOsInfo(windows_dir=r"C:\Windows", windows_dir_exists=True),
    )

    assert result.env["PATH"] == r"C:\venv\Scripts"
    assert result.report["inherited"]["PATH"] == r"C:\venv\Scripts"
    assert "PATH" not in result.report["backfilled"]


def test_build_launch_env_uses_fallback_when_discovery_invalid():
    from rook.rhino_launch import LaunchOsInfo, build_launch_env

    result = build_launch_env(
        {"PATH": r"C:\Tools"},
        os_info=LaunchOsInfo(windows_dir=r"Q:\MissingWindows", windows_dir_exists=False),
    )

    assert result.env["windir"] == r"C:\Windows"
    assert result.env["SystemRoot"] == r"C:\Windows"
    assert result.env["SystemDrive"] == "C:"
    assert result.report["fallback_used"] == ["windows_dir"]


def test_build_launch_env_catches_os_info_exception_and_records_fallback():
    from rook.rhino_launch import build_launch_env

    def raise_os_info():
        raise RuntimeError("ctypes failed")

    result = build_launch_env({"PATH": r"C:\Tools"}, os_info=raise_os_info)

    assert result.env["windir"] == r"C:\Windows"
    assert result.env["SystemRoot"] == r"C:\Windows"
    assert result.env["SystemDrive"] == "C:"
    assert result.report["fallback_used"] == ["os_info_exception", "windows_dir"]


def test_build_launch_env_does_not_mutate_base_env():
    from rook.rhino_launch import LaunchOsInfo, build_launch_env

    base = {"PATH": r"C:\Tools", "windir": r"Z:\Wrong"}
    original = dict(base)

    result = build_launch_env(
        base,
        os_info=LaunchOsInfo(windows_dir=r"C:\Windows", windows_dir_exists=True),
    )
    result.env["PATH"] = r"C:\Changed"

    assert base == original


def test_build_launch_env_report_is_deterministic():
    from rook.rhino_launch import LaunchOsInfo, build_launch_env

    result = build_launch_env(
        {
            "TMP": r"C:\Tmp",
            "APPDATA": r"C:\Users\Ada\AppData\Roaming",
            "PATH": r"C:\Tools",
            "USERPROFILE": r"C:\Users\Ada",
        },
        os_info=LaunchOsInfo(windows_dir=r"C:\Windows", windows_dir_exists=True),
    )

    assert list(result.report["authoritative"]) == ["SystemDrive", "SystemRoot", "windir"]
    assert list(result.report["backfilled"]) == ["LOCALAPPDATA", "ProgramData", "TEMP"]
    assert list(result.report["inherited"]) == ["APPDATA", "PATH", "TMP", "USERPROFILE"]
    assert result.report["missing_unresolved"] == []
    assert result.report["fallback_used"] == []
```

- [ ] **Step 2: Run the new pure tests and verify they fail for missing names**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_rhino_launch.py -k "build_launch_env" -q
```

Expected: FAIL with import errors for `LaunchOsInfo` or `build_launch_env`.

### Task 2: Implement `build_launch_env()` and Evidence Types

**Files:**
- Modify: `mcp_server/src/rook/rhino_launch.py`
- Modify: `mcp_server/tests/test_rhino_launch.py`

- [ ] **Step 1: Add launch-env dataclasses and constants**

In `mcp_server/src/rook/rhino_launch.py`, add `PureWindowsPath` to the existing `pathlib` import:

```python
from pathlib import Path, PureWindowsPath
```

Add these dataclasses after the capability flags:

```python
WINDOWS_ENV_INVARIANTS = ("SystemDrive", "SystemRoot", "windir")
CUSTOMIZABLE_LAUNCH_ENV_KEYS = (
    "APPDATA",
    "LOCALAPPDATA",
    "PATH",
    "ProgramData",
    "TEMP",
    "TMP",
    "USERPROFILE",
)
FALLBACK_WINDOWS_DIR = r"C:\Windows"


@dataclass(frozen=True)
class LaunchOsInfo:
    windows_dir: str | None
    windows_dir_exists: bool = True
    fallback_used: tuple[str, ...] = ()


@dataclass(frozen=True)
class LaunchEnvResult:
    env: dict[str, str]
    report: dict[str, Any]
```

- [ ] **Step 2: Add production OS discovery**

Add this helper below the dataclasses from Step 1:

```python
def _discover_windows_launch_os_info() -> LaunchOsInfo:
    if os.name != "nt":
        return LaunchOsInfo(
            windows_dir=FALLBACK_WINDOWS_DIR,
            windows_dir_exists=True,
            fallback_used=("non_windows_fallback",),
        )
    try:
        import ctypes

        buffer = ctypes.create_unicode_buffer(32768)
        length = ctypes.windll.kernel32.GetWindowsDirectoryW(buffer, len(buffer))
        if length <= 0 or length >= len(buffer):
            return LaunchOsInfo(
                windows_dir=FALLBACK_WINDOWS_DIR,
                windows_dir_exists=True,
                fallback_used=("windows_dir",),
            )
        candidate = buffer.value
        return LaunchOsInfo(
            windows_dir=candidate,
            windows_dir_exists=Path(candidate).exists(),
            fallback_used=(),
        )
    except Exception:
        return LaunchOsInfo(
            windows_dir=FALLBACK_WINDOWS_DIR,
            windows_dir_exists=True,
            fallback_used=("os_info_exception",),
        )
```

- [ ] **Step 3: Add small normalization helpers**

Add this block below `_discover_windows_launch_os_info()`:

```python
def _non_empty(value: object) -> bool:
    return str(value).strip() != ""


def _sorted_mapping(values: dict[str, str]) -> dict[str, str]:
    return {key: values[key] for key in sorted(values)}


def _resolve_launch_os_info(os_info) -> LaunchOsInfo:
    if os_info is None:
        return _discover_windows_launch_os_info()
    if callable(os_info):
        return os_info()
    return os_info


def _fallback_launch_os_info(extra_fallbacks: list[str] | None = None) -> LaunchOsInfo:
    fallbacks = ["windows_dir"]
    if extra_fallbacks:
        fallbacks = [*extra_fallbacks, *fallbacks]
    return LaunchOsInfo(
        windows_dir=FALLBACK_WINDOWS_DIR,
        windows_dir_exists=True,
        fallback_used=tuple(dict.fromkeys(fallbacks)),
    )
```

- [ ] **Step 4: Implement `build_launch_env()`**

Add this function below the helpers from Step 3:

```python
def build_launch_env(base_env=None, os_info=None) -> LaunchEnvResult:
    source = os.environ if base_env is None else base_env
    env = {str(key): str(value) for key, value in source.items()}

    try:
        info = _resolve_launch_os_info(os_info)
    except Exception:
        info = _fallback_launch_os_info(["os_info_exception"])

    if not isinstance(info, LaunchOsInfo):
        info = _fallback_launch_os_info(["os_info_invalid"])
    elif not _non_empty(info.windows_dir) or not info.windows_dir_exists:
        info = _fallback_launch_os_info(list(info.fallback_used))

    windows_dir = str(info.windows_dir or FALLBACK_WINDOWS_DIR).rstrip("\\/")
    system_drive = PureWindowsPath(windows_dir).drive or "C:"

    authoritative = {
        "SystemDrive": system_drive,
        "SystemRoot": windows_dir,
        "windir": windows_dir,
    }
    env.update(authoritative)

    backfilled: dict[str, str] = {}
    inherited: dict[str, str] = {}
    missing_unresolved: list[str] = []

    def has_value(name: str) -> bool:
        return name in env and _non_empty(env[name])

    def inherit_or_backfill(name: str, value: str | None) -> None:
        if has_value(name):
            inherited[name] = env[name]
            return
        if value is not None and _non_empty(value):
            env[name] = value
            backfilled[name] = value
            return
        missing_unresolved.append(name)

    userprofile = env.get("USERPROFILE") if has_value("USERPROFILE") else None
    inherit_or_backfill("USERPROFILE", None)
    inherit_or_backfill("ProgramData", rf"{system_drive}\ProgramData")
    inherit_or_backfill(
        "APPDATA",
        rf"{userprofile}\AppData\Roaming" if userprofile else None,
    )
    inherit_or_backfill(
        "LOCALAPPDATA",
        rf"{userprofile}\AppData\Local" if userprofile else None,
    )

    local_app_data = env.get("LOCALAPPDATA") if has_value("LOCALAPPDATA") else None
    temp_value = rf"{local_app_data}\Temp" if local_app_data else None
    inherit_or_backfill("TEMP", temp_value)
    inherit_or_backfill("TMP", temp_value)
    inherit_or_backfill("PATH", rf"{windows_dir}\System32;{windows_dir}")

    report = {
        "authoritative": _sorted_mapping(authoritative),
        "backfilled": _sorted_mapping(backfilled),
        "inherited": _sorted_mapping(inherited),
        "missing_unresolved": sorted(dict.fromkeys(missing_unresolved)),
        "fallback_used": sorted(dict.fromkeys(info.fallback_used)),
    }
    return LaunchEnvResult(env=env, report=report)
```

- [ ] **Step 5: Add optional `launchEnv` to evidence and start primitives**

Change `LaunchEvidence` by adding the final field:

```python
    launchEnv: dict[str, Any] | None = None
```

Change `_build_evidence()` signature and return:

```python
def _build_evidence(*, requested_scheme, active_scheme, isolation_mode, discovery_record_path,
                    discovery_log_seen, windows, exit_code, argv, elapsed,
                    launch_env=None) -> LaunchEvidence:
```

and include the field in `LaunchEvidence(...)`:

```python
        elapsedSeconds=elapsed, diagnosticHint=hint, launchEnv=launch_env)
```

Change `StartedRhino` by adding the final field:

```python
    launchEnv: dict[str, Any] | None = None
```

Change `LaunchExecError.__init__` to accept and store the report:

```python
    def __init__(self, message, *, argv, requested_scheme, active_scheme, isolation_mode,
                 launch_env=None):
        super().__init__(message)
        self.argv = list(argv)
        self.requested_scheme = requested_scheme
        self.active_scheme = active_scheme
        self.isolation_mode = isolation_mode
        self.launch_env = launch_env
```

Change `start_rhino_process()` to accept `launch_env_report` and propagate it:

```python
def start_rhino_process(rhino_exe, *, requested_scheme: str | None, env,
                        launch_env_report: dict[str, Any] | None = None,
                        scheme_isolation_available: bool = SCHEME_ISOLATION_AVAILABLE,
                        popen=None) -> StartedRhino:
```

In the `except OSError` block:

```python
        raise LaunchExecError(str(exc), argv=argv, requested_scheme=requested_scheme,
                              active_scheme=active_scheme, isolation_mode=isolation_mode,
                              launch_env=launch_env_report) from exc
```

In the returned `StartedRhino(...)`:

```python
                        isolationMode=isolation_mode, started_at=started_at,
                        started_wall=started_wall, launchEnv=launch_env_report)
```

Change `exec_failure_outcome()` to pass the report:

```python
                         discovery_log_seen=False, windows=[], exit_code=None,
                         argv=exc.argv, elapsed=0.0, launch_env=exc.launch_env)
```

Change both `_build_evidence(...)` calls in `wait_for_rook_readiness()` to pass:

```python
                             argv=started.argv, elapsed=now() - started.started_at,
                             launch_env=started.launchEnv)
```

- [ ] **Step 6: Add serialization and exec-failure tests**

Append these tests below the pure helper tests in `mcp_server/tests/test_rhino_launch.py`:

```python
def test_launch_evidence_with_launch_env_is_json_serializable():
    import json
    from rook.rhino_launch import LaunchEvidence

    ev = LaunchEvidence(
        requestedScheme="RookWorkbench",
        activeScheme=None,
        isolationMode="default",
        discoveryRecordPath=None,
        discoveryLogSeen=False,
        windows=[],
        visibleWindowCount=0,
        emptyTitleWindowPresent=False,
        exitCode=None,
        argv=["R.exe", "/nosplash"],
        elapsedSeconds=1.0,
        diagnosticHint=None,
        launchEnv={
            "authoritative": {"SystemDrive": "C:", "SystemRoot": r"C:\Windows", "windir": r"C:\Windows"},
            "backfilled": {},
            "inherited": {"PATH": r"C:\Tools"},
            "missing_unresolved": [],
            "fallback_used": [],
        },
    )

    dumped = json.dumps(ev.to_dict(), sort_keys=True)
    assert '"launchEnv"' in dumped
    assert ev.to_dict()["launchEnv"]["authoritative"]["windir"] == r"C:\Windows"


def test_exec_failure_outcome_includes_launch_env_report():
    from rook.rhino_launch import LaunchExecError, exec_failure_outcome

    exc = LaunchExecError(
        "nope",
        argv=["R.exe", "/nosplash"],
        requested_scheme="RookWorkbench",
        active_scheme=None,
        isolation_mode="default",
        launch_env={
            "authoritative": {"SystemDrive": "C:", "SystemRoot": r"C:\Windows", "windir": r"C:\Windows"},
            "backfilled": {},
            "inherited": {},
            "missing_unresolved": [],
            "fallback_used": [],
        },
    )

    out = exec_failure_outcome(exc)
    assert out.evidence.launchEnv["authoritative"]["windir"] == r"C:\Windows"
```

- [ ] **Step 7: Run focused `rhino_launch` tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_rhino_launch.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit the pure helper and evidence propagation**

Run:

```powershell
git branch --show-current
git status --short
git add mcp_server\src\rook\rhino_launch.py mcp_server\tests\test_rhino_launch.py
git commit -m "Harden Rhino launch environment construction"
```

Expected branch before commit: `codex/rhino-launch-workbench-spec`.

### Task 3: Wire `launch_owned_workbench()` Through the Env Seam

**Files:**
- Modify: `mcp_server/src/rook/workbench.py`
- Modify: `mcp_server/tests/test_workbench.py`

- [ ] **Step 1: Add failing workbench env-injection success test**

Append this test after `test_launch_success_registers_owned()` in `mcp_server/tests/test_workbench.py`:

```python
@pytest.mark.asyncio
async def test_launch_success_uses_built_launch_env_and_returns_evidence(monkeypatch):
    from types import SimpleNamespace

    launch_envs: list[dict[str, str]] = []
    report = {
        "authoritative": {
            "SystemDrive": "C:",
            "SystemRoot": r"C:\Windows",
            "windir": r"C:\Windows",
        },
        "backfilled": {"ProgramData": r"C:\ProgramData"},
        "inherited": {"PATH": r"C:\Tools"},
        "missing_unresolved": [],
        "fallback_used": [],
    }
    fake_env = SimpleNamespace(
        env={"windir": r"C:\Windows", "SystemRoot": r"C:\Windows", "SystemDrive": "C:", "PATH": r"C:\Tools"},
        report=report,
    )

    monkeypatch.setattr(workbench, "build_launch_env", lambda base_env: fake_env)
    monkeypatch.setattr(
        workbench.subprocess,
        "Popen",
        lambda command, **kwargs: launch_envs.append(kwargs["env"]) or _FakeProc(7778),
    )
    monkeypatch.setattr(workbench.Path, "exists", lambda self: True)
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)
    monkeypatch.setattr(
        workbench.OwnedRhinoDiscovery,
        "wait_for_ready",
        lambda self, *a, **k: _record(7778, port=64001),
    )

    out = await workbench.launch_owned_workbench(readiness_timeout_seconds=5)

    assert out["success"] is True
    assert launch_envs == [fake_env.env]
    assert out["data"]["evidence"]["launchEnv"] == report
```

- [ ] **Step 2: Add failing workbench failure evidence test**

Append this test after `test_launch_failure_maps_reason_to_code()`:

```python
@pytest.mark.asyncio
async def test_launch_failure_returns_launch_env_evidence(monkeypatch):
    from types import SimpleNamespace

    report = {
        "authoritative": {
            "SystemDrive": "C:",
            "SystemRoot": r"C:\Windows",
            "windir": r"C:\Windows",
        },
        "backfilled": {},
        "inherited": {"PATH": r"C:\Tools"},
        "missing_unresolved": [],
        "fallback_used": [],
    }
    fake_env = SimpleNamespace(
        env={"windir": r"C:\Windows", "SystemRoot": r"C:\Windows", "SystemDrive": "C:", "PATH": r"C:\Tools"},
        report=report,
    )

    monkeypatch.setattr(workbench, "build_launch_env", lambda base_env: fake_env)
    monkeypatch.setattr(workbench.subprocess, "Popen", lambda command, **kwargs: _FakeProc(8891))
    monkeypatch.setattr(workbench.Path, "exists", lambda self: True)
    monkeypatch.setattr(workbench, "describe_windows_for_pid", lambda pid: [])
    monkeypatch.setattr(workbench, "force_owned_process_cleanup", lambda p, d: True)
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)

    def raise_wfr(self, *a, **k):
        raise DiscoveryError("boom", reason=DiscoveryFailureReason.EXITED_BEFORE_BIND)

    monkeypatch.setattr(workbench.OwnedRhinoDiscovery, "wait_for_ready", raise_wfr)

    out = await workbench.launch_owned_workbench()

    assert out["success"] is False
    assert out["data"]["code"] == "workbench_exited_before_bind"
    assert out["data"]["evidence"]["launchEnv"] == report
```

- [ ] **Step 3: Run the two new tests and verify they fail**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_workbench.py -k "launch_env_evidence or built_launch_env" -q
```

Expected: FAIL because `workbench.build_launch_env` does not exist or because success data does not include `evidence`.

- [ ] **Step 4: Import and call `build_launch_env()` in workbench**

In `mcp_server/src/rook/workbench.py`, add `build_launch_env` to the import from `rook.rhino_launch`:

```python
    build_launch_env,
```

Inside `launch_owned_workbench()`, replace the existing requested-scheme and `start_rhino_process()` block with:

```python
    launch_env = build_launch_env(os.environ)
    requested = resolve_requested_scheme("RookWorkbench", launch_env.env, env_var="ROOK_WORKBENCH_SCHEME")
    try:
        started = start_rhino_process(
            exe,
            requested_scheme=requested,
            env=launch_env.env,
            launch_env_report=launch_env.report,
            # Launch via THIS module's subprocess.Popen so tests patching
            # workbench.subprocess.Popen still intercept; start_rhino_process owns argv (/nosplash).
            # The explicit env is intentionally duplicated here and in start_rhino_process(env=...):
            # removing this lambda later must still preserve the controlled launch environment.
            popen=lambda argv: subprocess.Popen(argv, env=launch_env.env),
        )
```

- [ ] **Step 5: Return success evidence from workbench**

In the final success return block, add the evidence field beside `mode` and `boundInSeconds`:

```python
        "mode": "workbench", "boundInSeconds": round(time.monotonic() - started_at, 2),
        "evidence": rr.outcome.evidence.to_dict()}}
```

- [ ] **Step 6: Run workbench tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_workbench.py -q
```

Expected: PASS.

### Task 4: Wire `runtime_harness` Through the Env Seam

**Files:**
- Modify: `mcp_server/src/rook/runtime_harness.py`
- Modify: `mcp_server/tests/test_runtime_harness.py`

- [ ] **Step 1: Add failing runtime harness env-policy test**

Append this test after `test_runtime_harness_applies_rhino_launch_env_overrides()`:

```python
def test_runtime_harness_applies_overrides_before_build_launch_env(
    tmp_path: Path,
    monkeypatch,
):
    from types import SimpleNamespace

    rhino_exe = tmp_path / "Rhino.exe"
    rhino_exe.write_text("fake", encoding="utf-8")
    process = FakeHarnessProcess(pid=4322, poll_results=[None, None])
    discovery = FakeHarnessDiscovery(pid=4322, port=9922)
    received_base_envs: list[dict[str, str]] = []
    popen_envs: list[dict[str, str]] = []
    report = {
        "authoritative": {
            "SystemDrive": "C:",
            "SystemRoot": r"C:\Windows",
            "windir": r"C:\Windows",
        },
        "backfilled": {"ProgramData": r"C:\ProgramData"},
        "inherited": {"ROOK_KEEP_ME": "ambient"},
        "missing_unresolved": [],
        "fallback_used": [],
    }
    fake_env = SimpleNamespace(
        env={"windir": r"C:\Windows", "SystemRoot": r"C:\Windows", "SystemDrive": "C:", "ROOK_KEEP_ME": "ambient"},
        report=report,
    )

    monkeypatch.setenv("ROOK_NATIVE_RUNSCRIPT_SAFETY", "ambient")
    monkeypatch.setenv("ROOK_KEEP_ME", "ambient")
    monkeypatch.setattr(
        "rook.runtime_harness.build_launch_env",
        lambda base_env: received_base_envs.append(dict(base_env)) or fake_env,
    )
    monkeypatch.setattr(
        "rook.runtime_harness.subprocess.Popen",
        lambda command, **kwargs: popen_envs.append(kwargs["env"]) or process,
    )
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
    monkeypatch.setattr("rook.runtime_harness.copy_temp_rook_artifacts", lambda *args: [])
    monkeypatch.setattr(
        "rook.runtime_harness.httpx.post",
        lambda url, json, timeout: httpx.Response(200, json={"success": True}),
    )
    monkeypatch.setattr(
        "rook.runtime_harness.request_external_graceful_close",
        lambda cleanup_process, timeout_seconds, **kwargs: cleanup_process.wait(timeout_seconds)
        or False,
    )

    result = run_rhino_runtime_harness(
        rhino_exe=rhino_exe,
        artifact_root=tmp_path / "artifacts",
        smoke_command=["smoke"],
        discovery=discovery,
        launch_env_overrides={
            "ROOK_NATIVE_RUNSCRIPT_SAFETY": None,
            "ROOK_NATIVE_RUNSCRIPT_SAFETY_MODE": "smoke",
        },
    )

    assert result.success is True
    assert len(received_base_envs) == 1
    assert "ROOK_NATIVE_RUNSCRIPT_SAFETY" not in received_base_envs[0]
    assert received_base_envs[0]["ROOK_NATIVE_RUNSCRIPT_SAFETY_MODE"] == "smoke"
    assert received_base_envs[0]["ROOK_KEEP_ME"] == "ambient"
    assert popen_envs == [fake_env.env]
    assert result.launch_outcome["evidence"]["launchEnv"] == report

    manifest = json.loads((result.artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["launch_outcome"]["evidence"]["launchEnv"] == report
```

- [ ] **Step 2: Run the new harness test and verify it fails**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_runtime_harness.py::test_runtime_harness_applies_overrides_before_build_launch_env -q
```

Expected: FAIL because `rook.runtime_harness.build_launch_env` does not exist or because launch evidence lacks `launchEnv`.

- [ ] **Step 3: Import and call `build_launch_env()` in runtime harness**

In `mcp_server/src/rook/runtime_harness.py`, add `build_launch_env` to the import from `rook.rhino_launch`:

```python
    build_launch_env,
```

Inside `run_rhino_runtime_harness()`, replace:

```python
    launch_env = _apply_env_overrides(os.environ, launch_env_overrides)
```

with:

```python
    launch_env_base = _apply_env_overrides(os.environ, launch_env_overrides)
    launch_env = build_launch_env(launch_env_base)
```

Then change `start_rhino_process()` and the patchable lambda:

```python
        started = start_rhino_process(
            rhino_exe,
            requested_scheme=requested_scheme,
            env=launch_env.env,
            launch_env_report=launch_env.report,
            # Launch via THIS module's subprocess.Popen so harness tests that patch
            # rook.runtime_harness.subprocess.Popen still intercept the owned-Rhino launch.
            # start_rhino_process still owns argv (/nosplash) + scheme; the primitive's own
            # popen-injection path is exercised directly in test_rhino_launch.
            # The explicit env is intentionally duplicated here and in start_rhino_process(env=...):
            # removing this lambda later must still preserve the controlled launch environment.
            popen=lambda argv: subprocess.Popen(argv, env=launch_env.env),
        )
```

- [ ] **Step 4: Run runtime harness tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_runtime_harness.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit workbench and harness wiring**

Run:

```powershell
git branch --show-current
git status --short
git add mcp_server\src\rook\workbench.py mcp_server\src\rook\runtime_harness.py mcp_server\tests\test_workbench.py mcp_server\tests\test_runtime_harness.py
git commit -m "Apply controlled env to owned Rhino launches"
```

Expected branch before commit: `codex/rhino-launch-workbench-spec`.

### Task 5: Focused Regression Verification

**Files:**
- Read: `mcp_server/src/rook/rhino_launch.py`
- Read: `mcp_server/src/rook/workbench.py`
- Read: `mcp_server/src/rook/runtime_harness.py`

- [ ] **Step 1: Run focused Python test suite**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_rhino_launch.py mcp_server\tests\test_workbench.py mcp_server\tests\test_runtime_harness.py -q
```

Expected: PASS.

- [ ] **Step 2: Run non-live MCP server tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests -m "not requires_rhino" -q
```

Expected: PASS, or only pre-existing unrelated failures verified against `main` before they are reported as residual risk.

- [ ] **Step 3: Run source guards**

Run:

```powershell
rg -n "build_launch_env|launchEnv|launch_env_report" mcp_server\src\rook\rhino_launch.py mcp_server\src\rook\workbench.py mcp_server\src\rook\runtime_harness.py
rg -n "subprocess\.Popen\(argv\)" mcp_server\src\rook\workbench.py mcp_server\src\rook\runtime_harness.py
git diff --check
```

Expected:
- First `rg` shows the helper definition plus both launch-site wirings.
- Second `rg` has no matches; both patchable lambdas pass `env=launch_env.env`.
- `git diff --check` exits 0.

### Task 6: Bound-Runtime #222 Live Proof

**Files:**
- Create: `docs/superpowers/audits/2026-06-14-issue-222-rhino-launch-env-live-proof.md`

- [ ] **Step 1: Confirm which runtime Codex will bind**

Run:

```powershell
$installedPython = Join-Path $env:LOCALAPPDATA "Rook\python\cpython-3.11.9\python.exe"
& $installedPython -c "import pathlib, rook; print(pathlib.Path(rook.__file__).resolve())"
```

Expected: prints the installed AppData `rook` module path. Record the printed path in the live-proof audit.

- [ ] **Step 2: Sync changed Python source into the installed runtime used by Codex**

Run:

```powershell
$repo = (Get-Location).Path
$installedPython = Join-Path $env:LOCALAPPDATA "Rook\python\cpython-3.11.9\python.exe"
$siteRook = & $installedPython -c "import pathlib, rook; print(pathlib.Path(rook.__file__).resolve().parent)"
Copy-Item -LiteralPath (Join-Path $repo "mcp_server\src\rook\rhino_launch.py") -Destination (Join-Path $siteRook "rhino_launch.py") -Force
Copy-Item -LiteralPath (Join-Path $repo "mcp_server\src\rook\workbench.py") -Destination (Join-Path $siteRook "workbench.py") -Force
Copy-Item -LiteralPath (Join-Path $repo "mcp_server\src\rook\runtime_harness.py") -Destination (Join-Path $siteRook "runtime_harness.py") -Force
& $installedPython -c "from rook.rhino_launch import build_launch_env; r=build_launch_env({'PATH':'C:\\Tools'}); print(r.env['windir']); print(r.report)"
```

Expected:
- The copy commands exit 0.
- The final command prints `C:\Windows`.
- The printed report includes `authoritative` keys `SystemDrive`, `SystemRoot`, and `windir`.

- [ ] **Step 3: Restart or refresh the Rook MCP binding before the live MCP call**

Use a fresh Codex session, or restart only the current Rook MCP server process so the already-imported Python modules cannot mask the sync. Before calling `rhino_workbench_launch`, confirm the live response can expose `evidence.launchEnv`; a response without `launchEnv` is stale installed code and is not evidence for #222.

- [ ] **Step 4: Run the MCP-owned workbench launch proof without closing unrelated user Rhino**

From the fixed MCP binding, call:

```json
{"tool": "rhino_workbench_launch", "arguments": {"readinessTimeoutSeconds": 90}}
```

Expected success shape:

```json
{
  "success": true,
  "data": {
    "session": "the returned rhino session id",
    "processId": 54321,
    "port": 65000,
    "owned": true,
    "mode": "workbench",
    "evidence": {
      "launchEnv": {
        "authoritative": {
          "SystemDrive": "C:",
          "SystemRoot": "C:\\Windows",
          "windir": "C:\\Windows"
        }
      }
    }
  }
}
```

Record the actual response in the audit, redacting only machine-local paths that are not needed for the finding. Do not require the user to close a separate non-owned Rhino session for this #222 proof; PID-correlated owned discovery is sufficient.

- [ ] **Step 5: Close the owned workbench through the owned teardown path**

Call `rhino_workbench_close` with the exact `data.session` value returned by Step 4.

Expected:
- Close returns `success: true`.
- The owned PID from Step 4 is gone.
- `rhino_workbench_list` reports no owned session for that PID.

- [ ] **Step 6: Write and commit the #222 live-proof audit**

Create `docs/superpowers/audits/2026-06-14-issue-222-rhino-launch-env-live-proof.md` with this structure:

```markdown
# Issue #222 Rhino Launch Env Live Proof

## Runtime Bound

Record the installed runtime module path printed by Step 1.

Record the sync method as: copied `rhino_launch.py`, `workbench.py`, and `runtime_harness.py` into the installed AppData `rook` package.

Record the binding refresh method used before the MCP call.

## MCP Launch Result

Record the exact `rhino_workbench_launch` response from Step 4.

Confirm the result is success and includes owned PID, session, port, and `evidence.launchEnv.authoritative` keys `SystemDrive`, `SystemRoot`, and `windir`.

Record `evidence.launchEnv.fallback_used`.

State that non-owned Rhino state was not required for #222 proof and unrelated user Rhino was not closed solely for this proof.

## MCP Close Result

Record the exact `rhino_workbench_close` response from Step 5.

Record the owned PID state after close and the `rhino_workbench_list` result.

## Classification

The #222 environment defect is fixed on the bound MCP runtime when the MCP-owned launch binds successfully and reports authoritative Windows invariants in `evidence.launchEnv`.
```

Then run:

```powershell
git branch --show-current
git status --short
git add docs\superpowers\audits\2026-06-14-issue-222-rhino-launch-env-live-proof.md
git commit -m "Record Rhino launch env live proof"
```

Expected branch before commit: `codex/rhino-launch-workbench-spec`.

### Task 7: Rerun the Approved #251 Launch Gate

**Files:**
- Create or update: `docs/superpowers/audits/2026-06-14-issue-251-rhino-workbench-launch-gate.md`

- [ ] **Step 1: Start the #251 gate from its own clean-state protocol**

Use the committed gate plan at `docs/superpowers/plans/2026-06-14-issue-251-rhino-launch-gate-plan.md`. The #251 gate is separate from the #222 live proof and still requires clean/cold state.

Before launch:
- Snapshot all `Rhino.exe` PIDs, window titles, and which sessions are Rook-owned.
- Close Rook-owned sessions through `rhino_workbench_close`.
- If any non-owned Rhino remains, stop and ask the user before closing it. The previously deferred kind of case, such as PID `42648`, belongs here rather than in the #222 proof.
- Detect crash-recovery/modal state and record it as evidence; do not clear it automatically.

- [ ] **Step 2: Run the MCP-wrapped gate arm**

Call:

```json
{"tool": "rhino_workbench_launch", "arguments": {"readinessTimeoutSeconds": 90}}
```

Record:
- elapsed time,
- success/failure payload,
- `evidence.launchEnv`,
- server still alive after call,
- launched Rhino PID state after call,
- recovery/modal evidence.

- [ ] **Step 3: Classify the rerun**

Use the existing approved enum:
- `clear`
- `unverified`
- `client_timeout`
- `event_loop_starvation`
- `server_death`
- `recovery_modal_222`

Expected after #222 fix: `clear`. If the classification is not `clear`, do not implement #251 delegation until the reviewer/user explicitly accepts the route.

- [ ] **Step 4: Commit the rerun artifact**

Run:

```powershell
git branch --show-current
git status --short
git add docs\superpowers\audits\2026-06-14-issue-251-rhino-workbench-launch-gate.md
git commit -m "Record rhino_workbench_launch gate rerun"
```

Expected branch before commit: `codex/rhino-launch-workbench-spec`.

## Final Verification Before Review

- [ ] Run focused tests:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_rhino_launch.py mcp_server\tests\test_workbench.py mcp_server\tests\test_runtime_harness.py -q
```

- [ ] Run non-live Python tests:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests -m "not requires_rhino" -q
```

- [ ] Run whitespace check:

```powershell
git diff --check
```

- [ ] Confirm committed diff scope:

```powershell
git status --short
git log --oneline --decorate -5
git diff --stat main...HEAD
git diff --name-only main...HEAD
```

Expected diff scope:
- `mcp_server/src/rook/rhino_launch.py`
- `mcp_server/src/rook/workbench.py`
- `mcp_server/src/rook/runtime_harness.py`
- `mcp_server/tests/test_rhino_launch.py`
- `mcp_server/tests/test_workbench.py`
- `mcp_server/tests/test_runtime_harness.py`
- `docs/superpowers/audits/2026-06-14-issue-222-rhino-launch-env-live-proof.md`
- `docs/superpowers/audits/2026-06-14-issue-251-rhino-workbench-launch-gate.md`

## Reviewer Handoff

Report these items to the reviewer:

- Branch name and latest commit hash.
- Focused pytest result.
- Non-live pytest result.
- `git diff --check` result.
- Bound-runtime sync method and module path.
- #222 live proof classification.
- #251 gate rerun classification.
- Any residual risk, especially present-but-minimal `PATH` remaining an accepted limitation rather than a merge policy.

If the #251 gate rerun is `clear`, the next slice can implement the already-approved #251 `rhino_launch` delegation design. If the gate rerun is not `clear`, stop at the artifact and route by the approved gate decision rule.
