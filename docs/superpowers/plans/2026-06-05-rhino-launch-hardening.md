# Rhino Launch Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Replace the bare `Popen([Rhino.exe])` shared by the test harness and the product Workbench launcher with composable launch primitives that reach RookNative readiness or return a structured, legible failure — diagnosing, never UI-automating — **while exposing the real process handle and preserving P5's durable-claim ordering**.

**Architecture:** New leaf module `rhino_launch.py` **owns** the launch + readiness primitives (moved out of `runtime_harness.py` to avoid a cycle). The primitives are **split, not a black box**: `build_rhino_argv()` → `start_rhino_process() -> StartedRhino(process, …)` → `wait_for_rook_readiness(started, …) -> LaunchOutcome`. **Callers own the lifecycle** (start → claim/registry → wait → bind/smoke → cleanup) so the `Popen` handle stays in the caller's hands and P5's `insert_launching`-immediately-after-start invariant is untouched. Phase 1 ships `/nosplash` + structured `LaunchOutcome` + capability flags (default **false**), operational path = default profile. Phase 2 (capability-gated, only if live config-discovery proves out) adds validated scheme isolation + scheme-local recovery reset.

**Tech Stack:** Python 3.10+ (editable install — no rebuild for unit tests), `pytest`, Win32 window enumeration (already present). Spec: `docs/superpowers/specs/2026-06-05-rhino-launch-hardening-design.md`.

**Pytest:** `mcp_server/.venv/Scripts/python.exe -m pytest`

---

## Revision history — 6 Codex blockers FOLDED IN (2026-06-05)

The first draft (`5500f53`) used a monolithic async `launch_rhino()` that hid the `Popen` handle and waited internally (claiming the registry too late). Codex flagged six blockers; **this revision folds all six into the task bodies below**. They are recorded here as the reviewer's invariants-preserved checklist:

1. **`Popen` handle is exposed.** Split primitive: `start_rhino_process(...) -> StartedRhino(process, pid, argv, requestedScheme, activeScheme, isolationMode, started_at)` then `wait_for_rook_readiness(started, ...) -> LaunchOutcome`. Both callers hold `started.process` for cleanup / `_OWNED` / `_reap_unclaimable`. (Tasks 6/7/8.)
2. **P5 durable-claim ordering preserved.** In `workbench.py`: `start_rhino_process()` → **immediately `insert_launching(...)`** (first statement after start) → `wait_for_rook_readiness()` → `bind`. The wait never happens before the claim. (Task 8.)
3. **`{success,data}` envelope honored** (the #220 lesson). `launch_owned_workbench` never returns `LaunchOutcome.to_dict()` raw; it merges `outcome.reason`/`outcome.evidence` into the existing P4/P5 `{"success": False, "data": {code, message, reason, evidence, retryable, …}}` envelope. (Task 8.)
4. **Evidence never claims isolation it didn't use.** `resolve_requested_scheme()` (what was asked) is separate from `resolve_active_scheme()` (what argv used). `LaunchEvidence` carries **both `requestedScheme` and `activeScheme`**; `isolationMode` derives from `activeScheme`. With `SCHEME_ISOLATION_AVAILABLE=False`, `activeScheme=None` / `isolationMode="default"` even when `requestedScheme="RookWorkbench"`. argv keys off `activeScheme`, never the request. (Tasks 3/4/6.)
5. **Task 1 moves the full transitive set.** `OwnedRhinoDiscovery` drags `default_discovery_dir`, `LOOPBACK_HOSTS`, `MIN_POLL_SECONDS`, `OwnedRhinoRecord`, `DiscoveryError`, `DiscoveryFailureReason`, `ProcessLike`, `PingFunction`, `ping_native`, `_run_awaitable_sync` (and imports `tempfile`/`httpx`/`inspect`, `from .bridge import resolve_discovery_folder`). `describe_windows_for_pid` drags `_windows_user32` + `_window_title` (+ `ctypes`/`wintypes`). After moving, grep both modules for every now-unresolved name and fix imports/re-exports until each imports clean.
6. **`WM_CLOSE` coherence.** `close_windows_for_pid()` (cleanup) and `WM_CLOSE` **stay** in `runtime_harness.py`. Only the window-**read** group moves (`describe_windows_for_pid`, `_window_title`, **and the shared `_windows_user32`**). Because `_windows_user32` is shared by close (stays) and read (moves) and `rhino_launch` must not import back from `runtime_harness`, `_windows_user32` **moves to `rhino_launch`** and `close_windows_for_pid` re-imports it via the re-export. Read = launch-evidence; close = cleanup.

**Corrected shape:** `rhino_launch.py` owns low-level primitives (argv, scheme resolution, `start_rhino_process`, `wait_for_rook_readiness`, evidence builder, capability flags, the moved discovery/window-read helpers); **callers own the lifecycle**. No monolithic orchestrator. The reason on any failure is **passed through** from the existing `DiscoveryError.reason` (reconcile, don't fork) — the evidence builder never re-derives a reason from window state.

---

## Setup

- [ ] **Branch off main:**

```bash
cd C:/Users/aryan/source/repos/Rook
git checkout main && git checkout -b feature/rhino-launch-hardening
```

---

## Task 1: Create `rhino_launch.py`; move the full transitive primitive set; re-export

Breaks the cycle: `rhino_launch.py` owns the primitives; `runtime_harness.py` imports them back via re-export so existing importers don't change. **This is the riskiest mechanical step — it must be behavior-preserving.**

**Files:**
- Create: `mcp_server/src/rook/rhino_launch.py`
- Modify: `mcp_server/src/rook/runtime_harness.py`
- Test: `mcp_server/tests/test_rhino_launch.py`

- [ ] **Step 1: Create `rhino_launch.py` and MOVE these entities verbatim from `runtime_harness.py`** (cut from `runtime_harness.py`, paste into the new module, preserving bodies). Move the **full transitive set** so the new module imports clean with no back-import:

  **Constants:** `LOOPBACK_HOSTS` (l.26), `MIN_POLL_SECONDS` (l.54).
  **Discovery types/helpers:** `default_discovery_dir` (l.29), `DiscoveryFailureReason` (l.66), `DiscoveryError` (l.76), `OwnedRhinoRecord` (l.82), `ProcessLike` (l.199), `PingFunction` (l.206), `_run_awaitable_sync` (l.922), `ping_native` (l.932), `OwnedRhinoDiscovery` (l.949).
  **Window-READ group (evidence):** `_windows_user32` (l.249), `_window_title` (l.288), `describe_windows_for_pid` (l.299).

  **Do NOT move (stay in `runtime_harness.py`):** `WM_CLOSE` (l.63), `close_windows_for_pid` (l.265), `request_external_graceful_close` (l.328), `force_owned_process_cleanup`, `default_temp_rook_dir`, `ArtifactRoot`/`default_artifact_roots`, `DEFAULT_DISCOVERY_DIR`, all Smoke/Harness/Cleanup types, `run_rhino_runtime_harness`.

  The new module's imports: `subprocess`, `os`, `time`, `json`, `asyncio`, `inspect`, `tempfile`, `ctypes`, `from ctypes import wintypes`, `from enum import Enum`, `from dataclasses import dataclass`, `from pathlib import Path`, `from typing import Any, Awaitable, Callable, Protocol`, `import httpx`, and `from .bridge import resolve_discovery_folder` (leaf-to-leaf; `bridge` imports nothing from `runtime_harness`/`rhino_launch`). It imports **nothing** from `runtime_harness` or `workbench`.

- [ ] **Step 2: In `runtime_harness.py`, replace the moved definitions with re-exports** at the top (after its own imports — keep `import ctypes` / `from ctypes import wintypes` / `WM_CLOSE` in `runtime_harness` since `close_windows_for_pid` stays):

```python
from .rhino_launch import (  # re-exported for back-compat; canonical home is rhino_launch
    DiscoveryError,
    DiscoveryFailureReason,
    LOOPBACK_HOSTS,
    MIN_POLL_SECONDS,
    OwnedRhinoDiscovery,
    OwnedRhinoRecord,
    PingFunction,
    ProcessLike,
    _run_awaitable_sync,
    _window_title,
    _windows_user32,
    default_discovery_dir,
    describe_windows_for_pid,
    ping_native,
)
```

  Then `close_windows_for_pid` (stays) uses the re-imported `_windows_user32` + local `WM_CLOSE`; `request_external_graceful_close`'s default arg `describe_windows_for_pid_fn=describe_windows_for_pid` resolves via the re-export; `default_temp_rook_dir` / `DEFAULT_DISCOVERY_DIR` use the re-imported `default_discovery_dir`. `RhinoHarnessResult` (l.134) and the harness orchestration **stay**.

- [ ] **Step 3: Grep both modules for every now-unresolved name and fix until clean**

```bash
mcp_server/.venv/Scripts/python.exe -c "import rook.rhino_launch, rook.runtime_harness, rook.workbench; print('import ok')"
```
Expected: `import ok` (no `NameError`/`ImportError`/circular-import). Grep `runtime_harness.py` for `OwnedRhinoDiscovery|DiscoveryError|ping_native|describe_windows_for_pid|_windows_user32|default_discovery_dir|LOOPBACK_HOSTS|MIN_POLL_SECONDS` and confirm each resolves via the re-export or a local use.

- [ ] **Step 4: Run the existing importer tests (move must be behavior-preserving)**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_runtime_harness.py mcp_server/tests/test_workbench.py -q`
Expected: PASS, same counts as before the move (`workbench.py` + the 4 importer tests import the moved names via the re-export unchanged).

- [ ] **Step 5: Add an import-resolution test**

Create `mcp_server/tests/test_rhino_launch.py`:

```python
def test_primitives_resolve_from_both_modules():
    from rook import rhino_launch, runtime_harness
    # canonical home is rhino_launch; runtime_harness re-exports the SAME objects
    for name in ("DiscoveryError", "DiscoveryFailureReason", "OwnedRhinoDiscovery",
                 "OwnedRhinoRecord", "ping_native", "describe_windows_for_pid",
                 "_windows_user32", "default_discovery_dir"):
        assert getattr(rhino_launch, name) is getattr(runtime_harness, name), name


def test_close_windows_stays_in_harness_with_wm_close():
    # WM_CLOSE + close_windows_for_pid are cleanup — they stay in runtime_harness.
    from rook import runtime_harness, rhino_launch
    assert hasattr(runtime_harness, "close_windows_for_pid")
    assert runtime_harness.WM_CLOSE == 0x0010
    assert not hasattr(rhino_launch, "WM_CLOSE")  # not moved
```

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_rhino_launch.py -q` → PASS.

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/rhino_launch.py mcp_server/src/rook/runtime_harness.py mcp_server/tests/test_rhino_launch.py
git commit -m "refactor(rhino-launch): move launch/readiness + window-read primitives to rhino_launch leaf + re-export"
```

---

## Task 2: Extend `DiscoveryFailureReason` (reconcile, don't fork)

The enum already has `FILE_NOT_FOUND`, `INVALID_RECORD`, `EXITED_BEFORE_BIND`, `EXITED_BEFORE_READY`, `BIND_TIMEOUT_NO_DISCOVERY`, `BIND_TIMEOUT_NO_PING`, `INVALID_DISCOVERY_RECORD`. Add **only** the two new launch-layer codes. The spec's `process_exited_before_discovery` maps to the existing `EXITED_BEFORE_BIND` — **do not add a duplicate**.

**Files:** Modify `mcp_server/src/rook/rhino_launch.py`; Test `mcp_server/tests/test_rhino_launch.py`

- [ ] **Step 1: Write the failing test** (append):

```python
from rook.rhino_launch import DiscoveryFailureReason

def test_reason_enum_extended_not_forked():
    assert DiscoveryFailureReason.LAUNCH_EXEC_FAILED.value == "launch_exec_failed"
    assert DiscoveryFailureReason.SCHEME_AUTOLOAD_NOT_VALIDATED.value == "scheme_autoload_not_validated"
    # existing members still present (reconciled, not forked)
    assert DiscoveryFailureReason.BIND_TIMEOUT_NO_DISCOVERY.value == "bind_timeout_no_discovery"
    assert DiscoveryFailureReason.EXITED_BEFORE_BIND.value == "exited_before_bind"
```

- [ ] **Step 2: Run → FAIL** (`AttributeError: LAUNCH_EXEC_FAILED`).

- [ ] **Step 3: Add two members** to the moved `DiscoveryFailureReason` enum:

```python
    LAUNCH_EXEC_FAILED = "launch_exec_failed"
    SCHEME_AUTOLOAD_NOT_VALIDATED = "scheme_autoload_not_validated"
```

- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `feat(rhino-launch): extend DiscoveryFailureReason with launch_exec_failed + scheme_autoload_not_validated`

---

## Task 3: `LaunchEvidence` (requested + active scheme) / `LaunchOutcome` + capability flags

**Files:** Modify `rhino_launch.py`; Test `test_rhino_launch.py`

- [ ] **Step 1: Write the failing test** (append):

```python
from rook.rhino_launch import (
    LaunchOutcome, LaunchEvidence,
    SCHEME_ISOLATION_AVAILABLE, CAN_RESET_SCHEME_RECOVERY_STATE,
)

def test_capability_flags_default_false():
    assert SCHEME_ISOLATION_AVAILABLE is False
    assert CAN_RESET_SCHEME_RECOVERY_STATE is False

def test_evidence_carries_requested_and_active_scheme():
    # requested isolation but isolation unavailable -> active is None / default
    ev = LaunchEvidence(requestedScheme="RookWorkbench", activeScheme=None, isolationMode="default",
                        discoveryRecordPath=None, discoveryLogSeen=False, windows=[],
                        visibleWindowCount=0, emptyTitleWindowPresent=False, exitCode=None,
                        argv=["R.exe", "/nosplash"], elapsedSeconds=1.5, diagnosticHint=None)
    d = ev.to_dict()
    assert d["requestedScheme"] == "RookWorkbench"
    assert d["activeScheme"] is None
    assert d["isolationMode"] == "default"

def test_outcome_to_dict_round_shape():
    ev = LaunchEvidence(requestedScheme=None, activeScheme=None, isolationMode="default",
                        discoveryRecordPath=None, discoveryLogSeen=False, windows=[],
                        visibleWindowCount=0, emptyTitleWindowPresent=False, exitCode=None,
                        argv=["x"], elapsedSeconds=1.5, diagnosticHint=None)
    out = LaunchOutcome(ok=True, schemeIsolationAvailable=False,
                        canResetSchemeRecoveryState=False, evidence=ev,
                        pid=123, port=4567, discoveryRecordPath="p.json", reason=None, message=None)
    d = out.to_dict()
    assert d["ok"] is True and d["pid"] == 123 and d["reason"] is None and d["message"] is None
    assert d["evidence"]["isolationMode"] == "default"
    assert d["schemeIsolationAvailable"] is False
```

- [ ] **Step 2: Run → FAIL** (import error).

- [ ] **Step 3: Implement** (append to `rhino_launch.py`):

```python
SCHEME_ISOLATION_AVAILABLE = False          # Phase 2 flips this only once autoload is validated
CAN_RESET_SCHEME_RECOVERY_STATE = False     # Phase 2 flips this only once a scheme-local marker is proven


@dataclass(frozen=True)
class LaunchEvidence:
    requestedScheme: str | None        # what the caller asked for
    activeScheme: str | None           # what argv actually used (None when isolation unavailable)
    isolationMode: str                 # "isolated" | "default" — derives from activeScheme, never the request
    discoveryRecordPath: str | None
    discoveryLogSeen: bool
    windows: list[dict[str, Any]]
    visibleWindowCount: int
    emptyTitleWindowPresent: bool
    exitCode: int | None
    argv: list[str]
    elapsedSeconds: float
    diagnosticHint: str | None         # NON-CAUSAL, e.g. "startup_window_present_no_discovery"

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class LaunchOutcome:
    ok: bool
    schemeIsolationAvailable: bool
    canResetSchemeRecoveryState: bool
    evidence: LaunchEvidence
    pid: int | None = None
    port: int | None = None
    discoveryRecordPath: str | None = None
    reason: DiscoveryFailureReason | None = None   # None on success; passed through on failure
    message: str | None = None                     # human-readable failure detail (str(exc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schemeIsolationAvailable": self.schemeIsolationAvailable,
            "canResetSchemeRecoveryState": self.canResetSchemeRecoveryState,
            "pid": self.pid,
            "port": self.port,
            "discoveryRecordPath": self.discoveryRecordPath,
            "reason": self.reason.value if self.reason else None,
            "message": self.message,
            "evidence": self.evidence.to_dict(),
        }
```

  Add `import dataclasses` to the module if not already present.

- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `feat(rhino-launch): LaunchOutcome/LaunchEvidence (requested+active scheme) + capability flags (default false)`

---

## Task 4: scheme resolution (requested vs active) + argv builder (nosplash always; /scheme only when active)

**argv keys off `activeScheme`, never the request** (finding #4). `resolve_requested_scheme` handles the opt-out env; `resolve_active_scheme` gates on `scheme_isolation_available`.

**Files:** Modify `rhino_launch.py`; Test `test_rhino_launch.py`

- [ ] **Step 1: Write the failing test** (append):

```python
from rook.rhino_launch import build_rhino_argv, resolve_requested_scheme, resolve_active_scheme

def test_requested_scheme_default_and_opt_out():
    assert resolve_requested_scheme("RookWorkbench", {}) == "RookWorkbench"
    assert resolve_requested_scheme("RookWorkbench", {"ROOK_WORKBENCH_SCHEME": "default"}) is None

def test_active_scheme_unavailable_is_default_even_when_requested():
    active, mode = resolve_active_scheme("RookWorkbench", scheme_isolation_available=False)
    assert (active, mode) == (None, "default")

def test_active_scheme_available_is_isolated():
    active, mode = resolve_active_scheme("RookWorkbench", scheme_isolation_available=True)
    assert (active, mode) == ("RookWorkbench", "isolated")

def test_active_scheme_none_request_is_default():
    assert resolve_active_scheme(None, scheme_isolation_available=True) == (None, "default")

def test_argv_always_nosplash_no_scheme_when_inactive():
    assert build_rhino_argv("R.exe", active_scheme=None) == ["R.exe", "/nosplash"]

def test_argv_adds_scheme_only_when_active():
    assert build_rhino_argv("R.exe", active_scheme="RookWorkbench") == \
        ["R.exe", "/nosplash", "/scheme=RookWorkbench"]
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** (append):

```python
def resolve_requested_scheme(default_scheme: str, env, *, env_var: str = "ROOK_WORKBENCH_SCHEME") -> str | None:
    """The scheme the caller REQUESTS. Explicit `<env_var>=default` opts out -> None (default profile)."""
    if env.get(env_var) == "default":
        return None
    return default_scheme


def resolve_active_scheme(requested_scheme: str | None, *, scheme_isolation_available: bool):
    """Return (activeScheme, isolationMode). Active ONLY if requested AND isolation is available."""
    if requested_scheme and scheme_isolation_available:
        return (requested_scheme, "isolated")
    return (None, "default")


def build_rhino_argv(rhino_exe, *, active_scheme: str | None) -> list[str]:
    """`/nosplash` ALWAYS; `/scheme=` only for an ACTIVE (validated+available) scheme."""
    argv = [str(rhino_exe), "/nosplash"]
    if active_scheme:
        argv.append(f"/scheme={active_scheme}")
    return argv
```

- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `feat(rhino-launch): requested-vs-active scheme resolution + explicit argv (/nosplash always)`

---

## Task 5: evidence builder (window is evidence + a non-causal hint, NEVER a reason)

The reason on a failure is **passed through** from the `DiscoveryError`/`LaunchExecError` in Task 6 — there is no signal-to-reason re-derivation here. This task builds *evidence only* and enforces the invariant that a window never becomes a reason.

**Files:** Modify `rhino_launch.py`; Test `test_rhino_launch.py`

- [ ] **Step 1: Write the failing test** (append):

```python
from rook.rhino_launch import _build_evidence

def test_evidence_window_facts_and_noncausal_hint():
    wins = [{"hwnd": "0x1", "title": "", "visible": True},
            {"hwnd": "0x2", "title": "Rhino", "visible": False}]
    ev = _build_evidence(requested_scheme="RookHarness", active_scheme=None, isolation_mode="default",
                         discovery_record_path=None, discovery_log_seen=False, windows=wins,
                         exit_code=None, argv=["R.exe", "/nosplash"], elapsed=2.0)
    assert ev.visibleWindowCount == 1               # only the visible one
    assert ev.emptyTitleWindowPresent is True
    assert ev.diagnosticHint == "startup_window_present_no_discovery"  # visible window + no discovery
    assert ev.requestedScheme == "RookHarness" and ev.activeScheme is None

def test_evidence_no_hint_when_discovery_present():
    wins = [{"hwnd": "0x1", "title": "", "visible": True}]
    ev = _build_evidence(requested_scheme=None, active_scheme=None, isolation_mode="default",
                         discovery_record_path="rec.json", discovery_log_seen=True, windows=wins,
                         exit_code=None, argv=["R.exe", "/nosplash"], elapsed=1.0)
    assert ev.diagnosticHint is None                # discovery present -> no "blocked" hint
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** (append). Pure evidence assembly; derives window facts + a strictly non-causal hint:

```python
def _build_evidence(*, requested_scheme, active_scheme, isolation_mode, discovery_record_path,
                    discovery_log_seen, windows, exit_code, argv, elapsed) -> LaunchEvidence:
    visible = [w for w in windows if w.get("visible")]
    empty_title_present = any((w.get("title") or "") == "" for w in visible)
    hint = "startup_window_present_no_discovery" if visible and discovery_record_path is None else None
    return LaunchEvidence(
        requestedScheme=requested_scheme, activeScheme=active_scheme, isolationMode=isolation_mode,
        discoveryRecordPath=discovery_record_path, discoveryLogSeen=discovery_log_seen,
        windows=list(windows), visibleWindowCount=len(visible),
        emptyTitleWindowPresent=empty_title_present, exitCode=exit_code, argv=list(argv),
        elapsedSeconds=elapsed, diagnosticHint=hint)
```

- [ ] **Step 4: Run → PASS** (2 tests).
- [ ] **Step 5: Commit** `feat(rhino-launch): evidence builder — window is evidence + non-causal hint, never a reason`

---

## Task 6: split primitives — `start_rhino_process()` + `wait_for_rook_readiness()`

The heart of the reshaping (findings #1/#2). `start_rhino_process` returns the live `StartedRhino(process, …)`; the caller holds `process`. `wait_for_rook_readiness` wraps the existing **sync** `OwnedRhinoDiscovery.wait_for_ready` and converts its `DiscoveryError` (reason passthrough) + window evidence into a `LaunchOutcome`. No monolithic orchestrator; no internal claim.

**Files:** Modify `rhino_launch.py`; Test `test_rhino_launch.py`

- [ ] **Step 1: Write the failing test** (append) — fakes for popen + discovery so it's unit-testable, no Rhino:

```python
from rook.rhino_launch import (
    StartedRhino, LaunchExecError, start_rhino_process, wait_for_rook_readiness,
    exec_failure_outcome, DiscoveryError, DiscoveryFailureReason as R,
)

class _FakeProc:
    def __init__(self, pid=111, code=None): self.pid = pid; self._code = code
    def poll(self): return self._code

def test_start_returns_live_process_handle_and_evidence_base():
    started = start_rhino_process("R.exe", requested_scheme="RookWorkbench", env={},
                                  scheme_isolation_available=False, popen=lambda a: _FakeProc(pid=222))
    assert started.pid == 222
    assert started.process.poll() is None            # caller holds the REAL handle
    assert started.argv == ["R.exe", "/nosplash"]    # isolation off -> default profile
    assert started.requestedScheme == "RookWorkbench" and started.activeScheme is None
    assert started.isolationMode == "default"

def test_start_exec_failure_raises_launchexecerror_with_evidence():
    def boom(_a): raise OSError("nope")
    try:
        start_rhino_process("R.exe", requested_scheme="RookWorkbench", env={},
                            scheme_isolation_available=False, popen=boom)
        assert False, "expected LaunchExecError"
    except LaunchExecError as exc:
        out = exec_failure_outcome(exc)
        assert out.ok is False and out.reason is R.LAUNCH_EXEC_FAILED
        assert out.evidence.argv[:2] == ["R.exe", "/nosplash"]

def test_wait_success_bundles_outcome_and_raw_record():
    started = StartedRhino(process=_FakeProc(pid=111), pid=111, argv=["R.exe", "/nosplash"],
                           requestedScheme=None, activeScheme=None, isolationMode="default",
                           started_at=0.0)
    class _Rec:
        pid, port = 111, 4567
        path = "rec.json"
    class _Disc:
        def wait_for_ready(self, *a, **k): return _Rec()
    rr = wait_for_rook_readiness(started, discovery=_Disc(), ping=lambda h, p: True,
                                 describe_windows=lambda pid: [], now=lambda: 1.0)
    assert rr.outcome.ok is True and rr.outcome.pid == 111 and rr.outcome.port == 4567
    assert rr.outcome.discoveryRecordPath == "rec.json" and rr.outcome.reason is None
    assert rr.record.port == 4567            # the live OwnedRhinoRecord, for in-process bind/_OWNED

def test_wait_passes_through_reason_and_window_is_only_evidence():
    started = StartedRhino(process=_FakeProc(pid=111), pid=111, argv=["R.exe", "/nosplash"],
                           requestedScheme="RookHarness", activeScheme=None, isolationMode="default",
                           started_at=0.0)
    class _Disc:
        def wait_for_ready(self, *a, **k):
            raise DiscoveryError("no disc", reason=R.BIND_TIMEOUT_NO_DISCOVERY)
    wins = [{"hwnd": "0x1", "title": "", "visible": True}]
    rr = wait_for_rook_readiness(started, discovery=_Disc(), ping=lambda h, p: False,
                                 describe_windows=lambda pid: wins, now=lambda: 2.0)
    assert rr.outcome.ok is False and rr.record is None
    assert rr.outcome.reason is R.BIND_TIMEOUT_NO_DISCOVERY   # FROM the exception, NOT the window
    assert rr.outcome.evidence.emptyTitleWindowPresent is True
    assert rr.outcome.evidence.diagnosticHint == "startup_window_present_no_discovery"
    assert rr.outcome.message == "no disc"
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** (append). `StartedRhino` + `LaunchExecError` + the two primitives + `exec_failure_outcome`:

```python
@dataclass(frozen=True)
class StartedRhino:
    process: Any                  # the live subprocess.Popen — CALLER owns cleanup / registry / _OWNED
    pid: int
    argv: list[str]
    requestedScheme: str | None
    activeScheme: str | None
    isolationMode: str
    started_at: float             # time.monotonic() at Popen


class LaunchExecError(RuntimeError):
    """Popen itself failed (exe missing / OSError) — carries the evidence base."""
    def __init__(self, message, *, argv, requested_scheme, active_scheme, isolation_mode):
        super().__init__(message)
        self.argv = list(argv)
        self.requested_scheme = requested_scheme
        self.active_scheme = active_scheme
        self.isolation_mode = isolation_mode


def start_rhino_process(rhino_exe, *, requested_scheme: str | None, env,
                        scheme_isolation_available: bool = SCHEME_ISOLATION_AVAILABLE,
                        popen=None) -> StartedRhino:
    active_scheme, isolation_mode = resolve_active_scheme(
        requested_scheme, scheme_isolation_available=scheme_isolation_available)
    argv = build_rhino_argv(rhino_exe, active_scheme=active_scheme)
    popen = popen or (lambda a: subprocess.Popen(a, env=dict(env) if env is not None else None))
    started_at = time.monotonic()
    try:
        proc = popen(argv)
    except OSError as exc:
        raise LaunchExecError(str(exc), argv=argv, requested_scheme=requested_scheme,
                              active_scheme=active_scheme, isolation_mode=isolation_mode) from exc
    return StartedRhino(process=proc, pid=int(proc.pid), argv=argv,
                        requestedScheme=requested_scheme, activeScheme=active_scheme,
                        isolationMode=isolation_mode, started_at=started_at)


def exec_failure_outcome(exc: LaunchExecError) -> LaunchOutcome:
    ev = _build_evidence(requested_scheme=exc.requested_scheme, active_scheme=exc.active_scheme,
                         isolation_mode=exc.isolation_mode, discovery_record_path=None,
                         discovery_log_seen=False, windows=[], exit_code=None, argv=exc.argv, elapsed=0.0)
    return LaunchOutcome(ok=False, schemeIsolationAvailable=SCHEME_ISOLATION_AVAILABLE,
                         canResetSchemeRecoveryState=CAN_RESET_SCHEME_RECOVERY_STATE, evidence=ev,
                         reason=DiscoveryFailureReason.LAUNCH_EXEC_FAILED, message=str(exc))


@dataclass(frozen=True)
class ReadinessResult:
    outcome: LaunchOutcome              # serializable structured result (manifest / envelope)
    record: OwnedRhinoRecord | None     # the live OwnedRhinoRecord on success; None on failure


def wait_for_rook_readiness(started: StartedRhino, *, discovery, ping=None,
                            timeout_seconds: float = 30.0, poll_seconds: float = 0.25,
                            describe_windows=None, now=time.monotonic) -> ReadinessResult:
    """SYNC (mirrors OwnedRhinoDiscovery.wait_for_ready). Workbench wraps this in asyncio.to_thread;
    the harness calls it directly. The failure reason is PASSED THROUGH from DiscoveryError.reason —
    never re-derived from window state. Returns ReadinessResult so the caller gets BOTH the serializable
    outcome AND the live record (no re-read, no lossy reconstruction)."""
    ping = ping or ping_native
    describe_windows = describe_windows or describe_windows_for_pid
    try:
        record = discovery.wait_for_ready(started.pid, started.process, ping,
                                          timeout_seconds, poll_seconds)
    except DiscoveryError as exc:
        windows = list(describe_windows(started.pid) or [])
        ev = _build_evidence(requested_scheme=started.requestedScheme, active_scheme=started.activeScheme,
                             isolation_mode=started.isolationMode, discovery_record_path=None,
                             discovery_log_seen=False, windows=windows, exit_code=started.process.poll(),
                             argv=started.argv, elapsed=now() - started.started_at)
        outcome = LaunchOutcome(ok=False, schemeIsolationAvailable=SCHEME_ISOLATION_AVAILABLE,
                                canResetSchemeRecoveryState=CAN_RESET_SCHEME_RECOVERY_STATE, evidence=ev,
                                reason=exc.reason or DiscoveryFailureReason.BIND_TIMEOUT_NO_DISCOVERY,
                                message=str(exc))
        return ReadinessResult(outcome=outcome, record=None)
    ev = _build_evidence(requested_scheme=started.requestedScheme, active_scheme=started.activeScheme,
                         isolation_mode=started.isolationMode, discovery_record_path=str(record.path),
                         discovery_log_seen=True, windows=[], exit_code=None, argv=started.argv,
                         elapsed=now() - started.started_at)
    outcome = LaunchOutcome(ok=True, schemeIsolationAvailable=SCHEME_ISOLATION_AVAILABLE,
                            canResetSchemeRecoveryState=CAN_RESET_SCHEME_RECOVERY_STATE, evidence=ev,
                            pid=record.pid, port=record.port, discoveryRecordPath=str(record.path))
    return ReadinessResult(outcome=outcome, record=record)
```

  > `Any` requires `from typing import Any` (already in the module imports). `ReadinessResult` bundles
  > the serializable `LaunchOutcome` with the live `OwnedRhinoRecord` (finding #1's `LaunchAttempt(process,
  > outcome, record)` shape, realized across the start/wait split) so neither caller re-reads the discovery
  > file or reconstructs a lossy record.

- [ ] **Step 4: Run → PASS** (4 tests).
- [ ] **Step 5: Commit** `feat(rhino-launch): start_rhino_process + wait_for_rook_readiness split primitives (handle exposed; reason passthrough)`

---

## Task 7: Wire `runtime_harness.py` to the split primitives; structured manifest

The harness composes: `start_rhino_process()` (catch `LaunchExecError`) → keep the existing `process = started.process` flow → `wait_for_rook_readiness()` → on `ok`, continue the existing confirmed-record/snapshot/smoke; on failure, write `launch_outcome` to the manifest. Cleanup still uses `started.process`.

**Files:** Modify `mcp_server/src/rook/runtime_harness.py` (the `Popen` region l.739–757 and the readiness block l.769–801) and `RhinoHarnessResult`.

- [ ] **Step 1: Add `launch_outcome` to `RhinoHarnessResult`** — a new optional field `launch_outcome: dict[str, Any] | None = None`, and include it in `write_manifest()` output (the manifest dict gains `"launch_outcome": self.launch_outcome`).

- [ ] **Step 2: Replace the bare `Popen` (l.739–757)** with the split start. Import the primitives at the top of `runtime_harness.py`: add `start_rhino_process, wait_for_rook_readiness, LaunchExecError, exec_failure_outcome, resolve_requested_scheme` to the existing `from .rhino_launch import (...)` block. Then:

```python
    discovery = discovery or OwnedRhinoDiscovery()
    requested = resolve_requested_scheme("RookHarness", os.environ, env_var="ROOK_HARNESS_SCHEME")
    try:
        started = start_rhino_process(
            rhino_exe, requested_scheme=requested,
            env=_apply_env_overrides(os.environ, launch_env_overrides))
    except LaunchExecError as exc:
        result = RhinoHarnessResult(
            run_id=run_id, artifact_dir=artifact_dir, pid=0, port=0,
            run_started_at=run_started_at, warnings=[f"Rhino launch failed: {exc}"],
            launch_outcome=exec_failure_outcome(exc).to_dict())
        copy_rook_artifacts(result, artifact_roots, "launch-failure")
        result.write_manifest()
        return result
    process = started.process
    pid = int(started.pid)
```

  (`process` and `pid` keep their existing names so the rest of the function — `wait`, cleanup, `_OWNED`-equivalent harness bookkeeping — is unchanged.)

- [ ] **Step 3: Replace the readiness wait (l.769–801)** — call `wait_for_rook_readiness` instead of `discovery.wait_for_ready`, thread the structured outcome into the manifest, and key the rest off `rr.record`. **The only substantive edits are (a) the wait call, (b) `launch_outcome` into `result`, (c) the failure branch. The existing `confirmed_record` try/except, snapshot, smoke, and cleanup are kept VERBATIM** — `rr.record` simply replaces the old `record` from `wait_for_ready`:

```python
    try:
        rr = wait_for_rook_readiness(
            started, discovery=discovery, ping=ping_native,
            timeout_seconds=readiness_timeout_seconds, poll_seconds=readiness_poll_seconds)
        result = replace(result, launch_outcome=rr.outcome.to_dict())
        if not rr.outcome.ok:
            warnings.append(
                f"Rhino readiness failed: {rr.outcome.reason.value if rr.outcome.reason else 'unknown'}")
            copy_rook_artifacts(result, artifact_roots, "readiness-failure")
        else:
            record = rr.record                       # the live OwnedRhinoRecord (was: wait_for_ready return)
            try:                                      # EXISTING post-ping confirmation — kept verbatim
                confirmed_record = discovery.read_owned_record(pid)
            except DiscoveryError as exc:
                warnings.append(f"Rhino discovery changed after ping: {exc}")
                copy_rook_artifacts(result, artifact_roots, "readiness-failure")
                confirmed_record = None
            else:
                if confirmed_record.port != record.port or confirmed_record.pid != record.pid:
                    warnings.append("Rhino discovery changed after ping: ...")   # EXISTING message verbatim
                    copy_rook_artifacts(result, artifact_roots, "readiness-failure")
                    confirmed_record = None
            if confirmed_record is not None:
                record = confirmed_record
                port = record.port
                # ... EXISTING snapshot + smoke flow unchanged, keyed off `record`/`port` ...
```

  The cleanup path (the `finally`/cleanup blocks below the wait) still operates on `process` (== `started.process`) — unchanged. Replace **only** the old `record = discovery.wait_for_ready(...)` + `except DiscoveryError` lines (l.771–780); everything from `confirmed_record` downward is preserved.

  > **Monkeypatch compatibility (do not regress).** `test_runtime_harness.py` monkeypatches `rook.runtime_harness.ping_native` at 3 sites (l.790/1790/1884). The re-export keeps `ping_native` a `runtime_harness` module attribute, so `monkeypatch.setattr` still rebinds it — **provided the harness keeps passing `ping=ping_native` resolved from the `runtime_harness` namespace** (as shown). Do NOT change it to `ping=rhino_launch.ping_native` or rely on `wait_for_rook_readiness`'s default ping; either would bypass the patch and break those tests.

- [ ] **Step 4: Run** `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_runtime_harness.py -q`. Adjust the harness tests that asserted the old `warnings=["Rhino readiness failed: ..."]` / `"Rhino launch failed: ..."` shapes to also assert `launch_outcome["reason"]` / `launch_outcome["evidence"]`. Expected PASS.

- [ ] **Step 5: Commit** `feat(rhino-launch): runtime_harness uses split primitives + structured launch_outcome in manifest`

---

## Task 8: Wire `workbench.py:launch_owned_workbench`; preserve P5 claim ordering; structured envelope

The product launcher composes the split primitives **without disturbing P5's durable-claim ordering** (finding #2) and returns the **`{success,data}` envelope** (finding #3), not raw `to_dict()`. The `process` handle stays in the caller for `_handle_launch_failure` / `_reap_unclaimable` / `_OWNED`.

**Files:** Modify `mcp_server/src/rook/workbench.py` (the launch path l.262–309 and `_handle_launch_failure` l.365–400).

- [ ] **Step 1: Add the import.** Append to the existing `from .runtime_harness import (...)` re-export-backed imports a new direct import from the canonical home:

```python
from .rhino_launch import (
    LaunchOutcome, LaunchExecError, exec_failure_outcome,
    resolve_requested_scheme, start_rhino_process, wait_for_rook_readiness,
)
```

- [ ] **Step 2: Replace the bare `Popen` (l.265–271)** with the split start — **preserving the exact P5 ordering**: start → pid → owner → `insert_launching` (claim) → wait. Only the first two lines change:

```python
    requested = resolve_requested_scheme("RookWorkbench", os.environ, env_var="ROOK_WORKBENCH_SCHEME")
    try:
        started = start_rhino_process(exe, requested_scheme=requested, env=os.environ)
    except LaunchExecError as exc:
        out = exec_failure_outcome(exc)
        return {"success": False, "data": {
            "code": "workbench_launch_failed", "message": out.message,
            "reason": out.reason.value, "evidence": out.evidence.to_dict(), "retryable": True}}

    process = started.process
    pid = int(started.pid)
    session = f"rhino-{pid}"
    owner = get_runtime_owner()
    # Durably claim the launch FIRST (first statement after start) — P5 invariant UNCHANGED.
    try:
        await asyncio.to_thread(
            lambda: _registry().insert_launching(session, pid, owner, scope, int(time.time())))
    except Exception as exc:
        return await _reap_unclaimable(process, pid, exc, owner=owner, scope=scope)
```

- [ ] **Step 3: Replace the readiness wait (l.283–289)** — drive `wait_for_rook_readiness` off-thread (it's sync), then branch on the outcome instead of catching `DiscoveryError`:

```python
    discovery = OwnedRhinoDiscovery()
    started_at = time.monotonic()
    rr = await asyncio.to_thread(
        wait_for_rook_readiness, started, discovery=discovery, ping=ping_native,
        timeout_seconds=timeout, poll_seconds=0.25)
    if not rr.outcome.ok:
        return await _handle_launch_failure(rr.outcome, process, pid, session)
    record = rr.record   # the live OwnedRhinoRecord — no re-read, no new failure path
```

  (The bind CAS / `_OWNED` block at l.291–309 is unchanged — it keys off `record.port` and `process`.)

- [ ] **Step 4: Revise `_handle_launch_failure`** to consume a `LaunchOutcome` instead of a `DiscoveryError`, and **merge** the structured reason+evidence into the existing P4/P5 envelope (do not return `to_dict()` raw):

```python
async def _handle_launch_failure(outcome: LaunchOutcome, process, pid: int, session: str) -> dict[str, Any]:
    code = _REASON_TO_CODE.get(outcome.reason, "workbench_launch_failed")
    data: dict[str, Any] = {"code": code, "message": outcome.message, "processId": pid,
                            "retryable": _RETRYABLE.get(code, True),
                            "reason": outcome.reason.value if outcome.reason else None,
                            "evidence": outcome.evidence.to_dict()}
    if outcome.reason is DiscoveryFailureReason.BIND_TIMEOUT_NO_DISCOVERY:
        windows = outcome.evidence.windows          # captured at readiness-failure time (no re-enum)
        if windows:
            data["blockingWindows"] = windows
            data["diagnosticConfidence"] = "window_present_no_discovery"   # NON-causal, matches evidence hint
            data["next_action"] = (
                "RookNative never published discovery before the timeout and a startup "
                "window was open — likely a modal (license/activation, 'another instance', "
                "or template chooser). The launch was cleaned up; resolve the underlying "
                "condition (e.g., activate Rhino) and retry.")
    reaped = await asyncio.to_thread(force_owned_process_cleanup, process, [])
    if reaped:
        try:
            await asyncio.to_thread(lambda: _registry().reap(session))
        except Exception as reap_exc:
            data["registryCleanupError"] = str(reap_exc)
        data["cleanupStatus"] = "forced_kill"
    else:
        async with _LOCK:
            _OWNED[pid] = OwnedWorkbench(record=None, process=process, session=session,
                                        launched_at=time.time())
        data["cleanupStatus"] = "force_kill_failed"
        data["session"] = session
        data["lifecycleStatus"] = "launching"
        data["port"] = None
        data["retryable"] = True
    return {"success": False, "data": data}
```

  This keeps every existing P4/P5 field (`code`/`message`/`cleanupStatus`/`blockingWindows`/`next_action`/the retain-vs-reap branch) and ADDS the structured `reason`/`evidence`. The `blockingWindows` now sources from `outcome.evidence.windows` (captured at failure time) rather than a second `describe_windows_for_pid(pid)` enumeration.

- [ ] **Step 5: Run** `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_workbench.py -q`. Update launch-path tests that constructed a `DiscoveryError` and called `_handle_launch_failure(exc, …)` to construct a `LaunchOutcome` (via `wait_for_rook_readiness` with a fake discovery, or directly) and call `_handle_launch_failure(outcome, …)`. Assert the envelope now carries `data["reason"]` + `data["evidence"]` alongside the existing `data["code"]`. Expected PASS.

- [ ] **Step 6: Commit** `feat(rhino-launch): launch_owned_workbench uses split primitives; P5 claim ordering preserved; structured envelope`

---

## Task 9 (Phase 2 — DISCOVERY D1): RookNative autoload in a named scheme

**Investigation task (needs Rhino-config inspection / McNeel docs — NOT a successful automated launch).** Acceptance is binary and fail-closed.

- [ ] **Step 1:** Determine how a named Rhino `/scheme=` enables RookNative load-at-startup. Inspect (read-only) the scheme's plugin-load storage: `HKCU\Software\McNeel\Rhinoceros\8.0\Scheme: <name>\...` registry and/or the scheme `settings*.json` under `%APPDATA%\McNeel\Rhinoceros\8.0\settings`. Compare a default-profile RookNative-loaded state vs a fresh scheme.
- [ ] **Step 2:** If a **documented, scheme-local** way to seed RookNative load-at-startup exists, write it up in the spec's §12 and implement a seeding helper in `rhino_launch.py` guarded so it only ever writes under the named Rook scheme. Then flip `SCHEME_ISOLATION_AVAILABLE = True` **only** behind a unit test proving the seeding writes nothing outside the Rook scheme path.
- [ ] **Step 3 (fail-closed):** If it cannot be done documented + scheme-local, leave `SCHEME_ISOLATION_AVAILABLE = False`, record findings in the spec, and STOP Phase 2 here. Phase 1 stands.
- [ ] **Step 4: Commit** the findings doc + (if proven) the seeding helper + flag.

---

## Task 10 (Phase 2 — DISCOVERY D2): scheme-local crash-recovery marker

**Investigation task, same discipline as Task 9.**

- [ ] **Step 1:** Identify the exact crash-recovery/autosave marker Rhino uses (file under the scheme's `AutoSave`/recovery dir, or a registry flag) and **prove it is scheme-local** (path contains the Rook scheme, not global/default).
- [ ] **Step 2:** If proven scheme-local: implement `reset_scheme_recovery_state(scheme)` in `rhino_launch.py` with a **dry-run** mode (returns what it would delete) + a logging path (records exactly what was cleared); guard it to refuse any path not under the Rook scheme. Unit test: dry-run lists the marker; a non-scheme-local path raises and mutates nothing. Flip `CAN_RESET_SCHEME_RECOVERY_STATE = True`.
- [ ] **Step 3 (fail-closed):** If not provably scheme-local, leave `CAN_RESET_SCHEME_RECOVERY_STATE = False`; the launcher only **detects + reports** recovery state in evidence. Record findings.
- [ ] **Step 4: Commit.**

---

## Task 11 (Phase 2 — conditional): scheme state machine + validation wiring

**Only if Task 9/10 proved out (`SCHEME_ISOLATION_AVAILABLE`/`CAN_RESET_SCHEME_RECOVERY_STATE` true).**

- [ ] **Step 1:** Implement the per-launch state machine (`scheme_requested` → validate → `scheme_validated_ready` | `scheme_not_ready`; `default_explicitly_requested` via opt-out). The states are computed from `requestedScheme` (Task 4) + the validation result. On `scheme_not_ready`, return `reason=SCHEME_AUTOLOAD_NOT_VALIDATED`; **no silent fallback** to the default profile. Unit-test each transition with injected validation results.
- [ ] **Step 2:** When `CAN_RESET_SCHEME_RECOVERY_STATE`, call `reset_scheme_recovery_state` before launch (dry-run logged) only for isolated Rook schemes.
- [ ] **Step 3: Commit.**

---

## Task 12: Baseline parity, gated live re-verify, finish

- [ ] **Step 1:** Full non-live gate: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests -m "not requires_rhino" -p no:cacheprovider -q -rfE`; then `git checkout -- knowledge/ ; rm -rf knowledge/selectors`. Confirm **baseline parity vs main** (failed/errors unchanged; passed up by the new `test_rhino_launch.py` count). The move (Task 1) must not change any existing test outcome — verify the `comm` diff of NAMED failed sets is empty in BOTH directions (as in #220); counts alone lie (cf. the `test_intent_orchestrator` order-dependent case, #221).
- [ ] **Step 2 (GATED — checkpoint with the user; bootstraps the #218 unblock):** With Rhino available, run `scripts/run_rhino_runtime_harness.py --smoke p6-artifact-perception` once and READ `launch_outcome` in the manifest. Phase 1's diagnostics tell us empirically whether `/nosplash` alone reaches readiness (then the four p3–p6 smokes should pass and #218 can close) or whether the evidence still shows `bind_timeout_no_discovery` + `startup_window_present_no_discovery` (then Phase 2 scheme isolation is genuinely required). **Do not overclaim** — read the structured outcome, report exactly what it says.
- [ ] **Step 3: Finish** — `superpowers:finishing-a-development-branch` → push + PR (Codex review), user pulls the merge trigger. PR body: the move (cycle fix), the split primitives (handle exposed + P5 ordering preserved), Phase-1-ships/Phase-2-gated, capability flags default false, signals-not-control, and the empirical Phase-1-diagnostics result.

---

## Notes for the implementer

- **`knowledge/` hygiene:** before any commit, if `git status` shows `knowledge/` changes, `git checkout -- knowledge/ && rm -rf knowledge/selectors`.
- **The move (Task 1) is the riskiest mechanical step** — it must be behavior-preserving; the re-export keeps `workbench.py` + the 4 importer tests unchanged. Run those tests immediately after, and `import rook.workbench` to prove no cycle.
- **The Popen handle is the caller's.** Neither primitive hides `started.process`; `workbench` and `runtime_harness` keep it for cleanup / `_OWNED` / `_reap_unclaimable`.
- **P5 ordering is sacred:** `start_rhino_process()` → `insert_launching()` (claim) → `wait_for_rook_readiness()` → `bind`. The wait never precedes the claim.
- **Reconcile, don't fork:** `LaunchOutcome.reason` is a `DiscoveryFailureReason` (extended by two members), **passed through** from `DiscoveryError.reason` — never a parallel enum, never re-derived from window state.
- **Envelope, not raw `to_dict()`:** `launch_owned_workbench` returns `{success, data}`; `data` merges the structured `reason`/`evidence` into the existing P4/P5 fields.
- **Evidence ≠ isolation claim:** `requestedScheme` vs `activeScheme`; argv keys off `activeScheme`; `isolationMode` derives from `activeScheme`.
- **Signals, not control:** no UI automation; window data is evidence + a non-causal hint only; never mutate the default profile or user documents; scheme reset is capability-gated and scheme-local-only.
- **Non-goals:** no changes to session routing (P3), registry semantics (P5), artifact registry (P6), or P7.
