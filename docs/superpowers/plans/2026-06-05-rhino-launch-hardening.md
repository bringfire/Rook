# Rhino Launch Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Replace the bare `Popen([Rhino.exe])` shared by the test harness and the product Workbench launcher with one hardened primitive that reaches RookNative readiness or returns a structured, legible failure — diagnosing, never UI-automating.

**Architecture:** New leaf module `rhino_launch.py` **owns** the launch + readiness primitives (moved out of `runtime_harness.py` to avoid a cycle); both callers use it. Phase 1 ships `/nosplash` + structured `LaunchOutcome` + capability flags (default **false**) with the operational path = default profile. Phase 2 (capability-gated, only if live config-discovery proves out) adds validated scheme isolation + scheme-local recovery reset.

**Tech Stack:** Python 3.10+ (editable install — no rebuild for unit tests), `pytest`, Win32 window enumeration (already present). Spec: `docs/superpowers/specs/2026-06-05-rhino-launch-hardening-design.md`.

**Pytest:** `mcp_server/.venv/Scripts/python.exe -m pytest`

---

## Setup

- [ ] **Branch off main:**

```bash
cd C:/Users/aryan/source/repos/Rook
git checkout main && git checkout -b feature/rhino-launch-hardening
```

---

## Task 1: Create `rhino_launch.py`; move the launch/readiness primitives; re-export

Breaks the cycle: `rhino_launch.py` will own the primitives; `runtime_harness.py` imports them back via re-export so existing importers don't change.

**Files:**
- Create: `mcp_server/src/rook/rhino_launch.py`
- Modify: `mcp_server/src/rook/runtime_harness.py`

- [ ] **Step 1: Create `rhino_launch.py` and MOVE these entities verbatim from `runtime_harness.py`** (cut from `runtime_harness.py`, paste into the new module, preserving their bodies and any module-level constants they need — `WM_CLOSE` at l.63 moves too since the window/cleanup helpers use it; copy it, and keep a re-export):
  - `DiscoveryFailureReason` (l.66–73)
  - `DiscoveryError` (l.76–79)
  - `OwnedRhinoRecord` (l.82–88)
  - `OwnedRhinoDiscovery` (l.949+) and its helpers `default_discovery_dir` (l.29) and `ping_native` (l.932)
  - `describe_windows_for_pid` (the Win32 window-enum used for evidence) and `WM_CLOSE`

  The new module's imports: `subprocess`, `os`, `time`, `json`, `enum`, `dataclasses`, `pathlib.Path`, `typing`, and `from .bridge import DEFAULT_HOST` if needed for ping. It imports **nothing** from `runtime_harness` or `workbench`.

- [ ] **Step 2: In `runtime_harness.py`, replace the moved definitions with re-exports** at the top (after its own imports):

```python
from .rhino_launch import (  # re-exported for back-compat; canonical home is rhino_launch
    DiscoveryError,
    DiscoveryFailureReason,
    OwnedRhinoDiscovery,
    OwnedRhinoRecord,
    default_discovery_dir,
    describe_windows_for_pid,
    ping_native,
)
```

  `RhinoHarnessResult` (l.134), `CleanupStatus`, `HarnessStatus`, `SmokeCommandResult`, `force_owned_process_cleanup`, `request_external_graceful_close`, and `run_rhino_runtime_harness` **stay** in `runtime_harness.py` (harness orchestration).

- [ ] **Step 3: Run the existing importer tests to verify the move is behavior-preserving**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_runtime_harness.py mcp_server/tests/test_workbench.py -q`
Expected: PASS (same counts as before the move — `workbench.py` and the tests import the moved names via the re-export unchanged).

- [ ] **Step 4: Add an import-resolution test**

Create `mcp_server/tests/test_rhino_launch.py`:

```python
def test_primitives_resolve_from_both_modules():
    from rook import rhino_launch, runtime_harness
    # canonical home
    assert rhino_launch.DiscoveryError is runtime_harness.DiscoveryError
    assert rhino_launch.DiscoveryFailureReason is runtime_harness.DiscoveryFailureReason
    assert rhino_launch.OwnedRhinoDiscovery is runtime_harness.OwnedRhinoDiscovery
    assert rhino_launch.OwnedRhinoRecord is runtime_harness.OwnedRhinoRecord
    assert rhino_launch.ping_native is runtime_harness.ping_native
```

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_rhino_launch.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/rhino_launch.py mcp_server/src/rook/runtime_harness.py mcp_server/tests/test_rhino_launch.py
git commit -m "refactor(rhino-launch): move launch/readiness primitives to rhino_launch leaf + re-export"
```

---

## Task 2: Extend `DiscoveryFailureReason` (reconcile, don't fork)

**Files:** Modify `mcp_server/src/rook/rhino_launch.py`; Test `mcp_server/tests/test_rhino_launch.py`

- [ ] **Step 1: Write the failing test** (append):

```python
from rook.rhino_launch import DiscoveryFailureReason

def test_reason_enum_extended():
    assert DiscoveryFailureReason.LAUNCH_EXEC_FAILED.value == "launch_exec_failed"
    assert DiscoveryFailureReason.SCHEME_AUTOLOAD_NOT_VALIDATED.value == "scheme_autoload_not_validated"
    # existing members still present (reconciled, not forked)
    assert DiscoveryFailureReason.BIND_TIMEOUT_NO_DISCOVERY.value == "bind_timeout_no_discovery"
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

## Task 3: `LaunchOutcome` / `LaunchEvidence` + capability flags (default false)

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

def test_outcome_to_dict_round_shape():
    ev = LaunchEvidence(scheme=None, isolationMode="default", discoveryRecordPath=None,
                        discoveryLogSeen=False, windows=[], visibleWindowCount=0,
                        emptyTitleWindowPresent=False, exitCode=None, argv=["x"],
                        elapsedSeconds=1.5, diagnosticHint=None)
    out = LaunchOutcome(ok=True, schemeIsolationAvailable=False,
                        canResetSchemeRecoveryState=False, evidence=ev,
                        pid=123, port=4567, discoveryRecordPath="p.json", reason=None)
    d = out.to_dict()
    assert d["ok"] is True and d["pid"] == 123 and d["reason"] is None
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
    scheme: str | None
    isolationMode: str                 # "isolated" | "default"
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
    reason: DiscoveryFailureReason | None = None   # None on success

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schemeIsolationAvailable": self.schemeIsolationAvailable,
            "canResetSchemeRecoveryState": self.canResetSchemeRecoveryState,
            "pid": self.pid,
            "port": self.port,
            "discoveryRecordPath": self.discoveryRecordPath,
            "reason": self.reason.value if self.reason else None,
            "evidence": self.evidence.to_dict(),
        }
```

- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `feat(rhino-launch): LaunchOutcome/LaunchEvidence + capability flags (default false)`

---

## Task 4: argv builder + scheme resolution (nosplash always; /scheme only when available)

**Files:** Modify `rhino_launch.py`; Test `test_rhino_launch.py`

- [ ] **Step 1: Write the failing test** (append):

```python
from rook.rhino_launch import build_rhino_argv, resolve_scheme

def test_argv_always_nosplash_no_scheme_when_unavailable():
    argv = build_rhino_argv("R.exe", scheme="RookWorkbench", scheme_isolation_available=False)
    assert argv == ["R.exe", "/nosplash"]   # Phase 1: isolation off -> default profile

def test_argv_adds_scheme_when_available_and_requested():
    argv = build_rhino_argv("R.exe", scheme="RookWorkbench", scheme_isolation_available=True)
    assert argv == ["R.exe", "/nosplash", "/scheme=RookWorkbench"]

def test_resolve_scheme_explicit_opt_out():
    assert resolve_scheme("RookWorkbench", {"ROOK_WORKBENCH_SCHEME": "default"}) == (None, "default")

def test_resolve_scheme_default_is_isolated_request():
    assert resolve_scheme("RookWorkbench", {}) == ("RookWorkbench", "isolated")
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** (append):

```python
def build_rhino_argv(rhino_exe, *, scheme: str | None, scheme_isolation_available: bool) -> list[str]:
    argv = [str(rhino_exe), "/nosplash"]
    if scheme and scheme_isolation_available:
        argv.append(f"/scheme={scheme}")
    return argv


def resolve_scheme(default_scheme: str, env, *, env_var: str = "ROOK_WORKBENCH_SCHEME"):
    """Return (scheme_or_None, isolationMode). Explicit 'default' opts out of isolation."""
    if env.get(env_var) == "default":
        return (None, "default")
    return (default_scheme, "isolated")
```

- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `feat(rhino-launch): explicit argv (/nosplash always) + scheme opt-out resolution`

---

## Task 5: failure classifier (signals → reason + evidence; window is evidence, never a reason)

**Files:** Modify `rhino_launch.py`; Test `test_rhino_launch.py`

- [ ] **Step 1: Write the failing test** (append):

```python
from rook.rhino_launch import classify_launch, DiscoveryFailureReason as R

def _ev(**kw):
    base = dict(scheme=None, isolation_mode="default", discovery_record_path=None,
               discovery_log_seen=False, windows=[], exit_code=None, argv=["R.exe", "/nosplash"],
               elapsed=2.0)
    base.update(kw); return base

def test_exec_failed():
    out = classify_launch(exec_error=True, **_ev())
    assert out.ok is False and out.reason is R.LAUNCH_EXEC_FAILED

def test_process_exited_before_discovery():
    out = classify_launch(process_alive=False, discovery_record=None, exit_code=1, **_ev(exit_code=1))
    assert out.reason is R.EXITED_BEFORE_BIND and out.evidence.exitCode == 1

def test_bind_timeout_no_discovery_with_window_is_not_window_causal():
    wins = [{"hwnd": "0x1", "title": "", "visible": True}]
    out = classify_launch(process_alive=True, discovery_record=None, **_ev(windows=wins))
    assert out.reason is R.BIND_TIMEOUT_NO_DISCOVERY            # NOT a window-causal reason
    assert out.evidence.visibleWindowCount == 1
    assert out.evidence.emptyTitleWindowPresent is True
    assert out.evidence.diagnosticHint == "startup_window_present_no_discovery"

def test_bind_timeout_no_ping():
    out = classify_launch(process_alive=True, discovery_record={"port": 4}, ping_ok=False, **_ev())
    assert out.reason is R.BIND_TIMEOUT_NO_PING
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** (append). Builds `LaunchEvidence` (deriving window fields + the non-causal hint) and picks a `DiscoveryFailureReason` from the signals — never inferring window causation:

```python
def _build_evidence(*, scheme, isolation_mode, discovery_record_path, discovery_log_seen,
                    windows, exit_code, argv, elapsed) -> LaunchEvidence:
    visible = [w for w in windows if w.get("visible")]
    empty_title_present = any((w.get("title") or "") == "" for w in visible)
    hint = "startup_window_present_no_discovery" if visible and discovery_record_path is None else None
    return LaunchEvidence(
        scheme=scheme, isolationMode=isolation_mode, discoveryRecordPath=discovery_record_path,
        discoveryLogSeen=discovery_log_seen, windows=list(windows), visibleWindowCount=len(visible),
        emptyTitleWindowPresent=empty_title_present, exitCode=exit_code, argv=list(argv),
        elapsedSeconds=elapsed, diagnosticHint=hint)


def classify_launch(*, exec_error=False, process_alive=True, discovery_record=None, ping_ok=None,
                    invalid_record=False, scheme=None, isolation_mode="default",
                    discovery_record_path=None, discovery_log_seen=False, windows=(),
                    exit_code=None, argv=(), elapsed=0.0) -> LaunchOutcome:
    ev = _build_evidence(scheme=scheme, isolation_mode=isolation_mode,
                         discovery_record_path=discovery_record_path,
                         discovery_log_seen=discovery_log_seen, windows=windows,
                         exit_code=exit_code, argv=argv, elapsed=elapsed)
    if exec_error:
        reason = DiscoveryFailureReason.LAUNCH_EXEC_FAILED
    elif not process_alive and discovery_record is None:
        reason = DiscoveryFailureReason.EXITED_BEFORE_BIND
    elif invalid_record:
        reason = DiscoveryFailureReason.INVALID_DISCOVERY_RECORD
    elif discovery_record is None:
        reason = DiscoveryFailureReason.BIND_TIMEOUT_NO_DISCOVERY     # window (if any) is only evidence
    elif ping_ok is False:
        reason = DiscoveryFailureReason.BIND_TIMEOUT_NO_PING
    else:
        # success path is built by the launch orchestrator, not the classifier
        return LaunchOutcome(ok=True, schemeIsolationAvailable=SCHEME_ISOLATION_AVAILABLE,
                             canResetSchemeRecoveryState=CAN_RESET_SCHEME_RECOVERY_STATE,
                             evidence=ev, discoveryRecordPath=discovery_record_path)
    return LaunchOutcome(ok=False, schemeIsolationAvailable=SCHEME_ISOLATION_AVAILABLE,
                         canResetSchemeRecoveryState=CAN_RESET_SCHEME_RECOVERY_STATE,
                         evidence=ev, reason=reason)   # pid/port/discoveryRecordPath default to None
```

> The classifier accepts an optional `reason_override: DiscoveryFailureReason | None = None`; when the
> orchestrator (Task 6) catches a `DiscoveryError` that already carries a `.reason`, it passes that
> through (`reason_override=exc.reason`) so the existing P4 reason is preserved instead of re-derived.

- [ ] **Step 4: Run → PASS** (4 tests).
- [ ] **Step 5: Commit** `feat(rhino-launch): signal classifier (window is evidence, never a causal reason)`

---

## Task 6: `launch_rhino()` orchestrator (Popen → readiness wait → classify → LaunchOutcome)

**Files:** Modify `rhino_launch.py`; Test `test_rhino_launch.py`

- [ ] **Step 1: Write the failing test** (append) — inject a fake popen + fake discovery so it's unit-testable, no Rhino:

```python
import asyncio
from rook.rhino_launch import launch_rhino

class _FakeProc:
    def __init__(self, pid=111, code=None): self.pid = pid; self._code = code
    def poll(self): return self._code

def test_launch_exec_failure(monkeypatch):
    def boom(*a, **k): raise OSError("nope")
    out = asyncio.run(launch_rhino("R.exe", default_scheme="RookHarness", env={}, popen=boom))
    assert out.ok is False and out.reason.value == "launch_exec_failed"
    assert out.evidence.argv[:2] == ["R.exe", "/nosplash"]

def test_launch_success(monkeypatch):
    async def fake_wait(**k): return {"pid": 111, "port": 4567, "path": "rec.json"}
    out = asyncio.run(launch_rhino("R.exe", default_scheme="RookHarness", env={},
                                   popen=lambda *a, **k: _FakeProc(), wait_for_ready=fake_wait,
                                   describe_windows=lambda pid: []))
    assert out.ok is True and out.pid == 111 and out.port == 4567
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `launch_rhino`** (append). It is dependency-injectable (popen/wait_for_ready/describe_windows default to the real ones) so it's unit-testable; the real path uses `subprocess.Popen`, `OwnedRhinoDiscovery().wait_for_ready`, `describe_windows_for_pid`:

```python
async def launch_rhino(rhino_exe, *, default_scheme: str, env, env_var="ROOK_WORKBENCH_SCHEME",
                       readiness_timeout_seconds: float = 30.0, popen=None,
                       wait_for_ready=None, describe_windows=None) -> LaunchOutcome:
    scheme, isolation_mode = resolve_scheme(default_scheme, env, env_var=env_var)
    argv = build_rhino_argv(rhino_exe, scheme=scheme, scheme_isolation_available=SCHEME_ISOLATION_AVAILABLE)
    popen = popen or (lambda a: subprocess.Popen(a, env=dict(env) or None))
    describe_windows = describe_windows or describe_windows_for_pid
    t0 = time.monotonic()

    try:
        proc = popen(argv)
    except OSError:
        return classify_launch(exec_error=True, scheme=scheme, isolation_mode=isolation_mode,
                               argv=argv, windows=[], elapsed=time.monotonic() - t0)

    if wait_for_ready is None:
        disc = OwnedRhinoDiscovery()
        async def wait_for_ready(**_k):
            rec = disc.wait_for_ready(pid=proc.pid, process=proc, ping=ping_native,
                                      timeout_seconds=readiness_timeout_seconds)
            return {"pid": rec.pid, "port": rec.port, "path": str(rec.path)}

    try:
        rec = await wait_for_ready()
    except DiscoveryError as exc:
        windows = list(describe_windows(proc.pid) or [])
        return classify_launch(process_alive=(proc.poll() is None), discovery_record=None,
                               scheme=scheme, isolation_mode=isolation_mode, argv=argv,
                               windows=windows, exit_code=proc.poll(),
                               elapsed=time.monotonic() - t0)  # reason derived from DiscoveryError + signals

    ev = _build_evidence(scheme=scheme, isolation_mode=isolation_mode, discovery_record_path=rec["path"],
                         discovery_log_seen=True, windows=[], exit_code=None, argv=argv,
                         elapsed=time.monotonic() - t0)
    return LaunchOutcome(ok=True, schemeIsolationAvailable=SCHEME_ISOLATION_AVAILABLE,
                         canResetSchemeRecoveryState=CAN_RESET_SCHEME_RECOVERY_STATE, evidence=ev,
                         pid=rec["pid"], port=rec["port"], discoveryRecordPath=rec["path"])
```

> During impl: map the caught `DiscoveryError.reason` (it already carries a `DiscoveryFailureReason`) onto `classify_launch` so the existing reason is preserved (pass it through rather than re-deriving when present).

- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `feat(rhino-launch): launch_rhino orchestrator (Popen -> readiness -> structured LaunchOutcome)`

---

## Task 7: Wire `runtime_harness.py` to `launch_rhino`; structured manifest

**Files:** Modify `mcp_server/src/rook/runtime_harness.py` (the `Popen` at l.741 region) and its `RhinoHarnessResult` manifest.

- [ ] **Step 1:** Replace the bare `subprocess.Popen([str(rhino_exe)], env=...)` (l.741) with a call to `launch_rhino(rhino_exe, default_scheme="RookHarness", env=..., env_var="ROOK_HARNESS_SCHEME", readiness_timeout_seconds=readiness_timeout_seconds)`. Use its `LaunchOutcome`: on `ok`, continue with `outcome.pid`/`outcome.port` into the existing smoke/cleanup flow; on failure, write the manifest with `launch_outcome=outcome.to_dict()` and return (replacing the ad-hoc `warnings.append("Rhino readiness failed: ...")`).
- [ ] **Step 2:** Add `launch_outcome` to `RhinoHarnessResult.write_manifest()` output.
- [ ] **Step 3:** Run `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_runtime_harness.py -q` → adjust the harness tests that asserted the old warning shape to assert `launch_outcome.reason`/evidence instead. Expected PASS.
- [ ] **Step 4: Commit** `feat(rhino-launch): runtime_harness uses launch_rhino + structured launch_outcome in manifest`

---

## Task 8: Wire `workbench.py:launch_owned_workbench` to `launch_rhino`; opt-out env; return outcome

**Files:** Modify `mcp_server/src/rook/workbench.py` (the `Popen` at l.266 region).

- [ ] **Step 1:** Replace `subprocess.Popen([str(exe)])` (l.266) with `launch_rhino(exe, default_scheme="RookWorkbench", env=os.environ, env_var="ROOK_WORKBENCH_SCHEME", readiness_timeout_seconds=readiness_timeout_seconds)`. Preserve the existing durable-claim ordering (`insert_launching` as the first statement after a successful launch) — the structured outcome's `pid`/`port` feed the registry exactly as the old `proc.pid`/discovered port did.
- [ ] **Step 2:** On a failure outcome, return the structured dict (`outcome.to_dict()`) up through `rhino_workbench_launch` so a coordinator sees `{ok:false, reason, evidence, schemeIsolationAvailable}` instead of a hang/`DiscoveryError` string. Keep `_handle_launch_failure` for the cleanup of a partially-launched process.
- [ ] **Step 3:** Run `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_workbench.py -q` → update launch-path tests to the structured outcome. Expected PASS.
- [ ] **Step 4: Commit** `feat(rhino-launch): launch_owned_workbench uses launch_rhino; legible structured failure to coordinator`

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

- [ ] **Step 1:** Implement the per-launch state machine (`scheme_requested` → validate → `scheme_validated_ready` | `scheme_not_ready`; `default_explicitly_requested` via opt-out). On `scheme_not_ready`, return `reason=SCHEME_AUTOLOAD_NOT_VALIDATED`; **no silent fallback** to default. Unit-test each transition with injected validation results.
- [ ] **Step 2:** When `CAN_RESET_SCHEME_RECOVERY_STATE`, call `reset_scheme_recovery_state` before launch (dry-run logged) only for isolated Rook schemes.
- [ ] **Step 3: Commit.**

---

## Task 12: Baseline parity, gated live re-verify, finish

- [ ] **Step 1:** Full non-live gate: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests -m "not requires_rhino" -p no:cacheprovider -q -rfE`; then `git checkout -- knowledge/ ; rm -rf knowledge/selectors`. Confirm **baseline parity vs main** (failed/errors unchanged; passed up by the new `test_rhino_launch.py` count). The move (Task 1) must not change any existing test outcome — verify the `comm` diff of failed sets is empty (as in #220).
- [ ] **Step 2 (GATED — checkpoint with the user; bootstraps the #218 unblock):** With Rhino available, run `scripts/run_rhino_runtime_harness.py --smoke p6-artifact-perception` once and READ `launch_outcome` in the manifest. Phase 1's diagnostics tell us empirically whether `/nosplash` alone reaches readiness (then the four p3–p6 smokes should pass and #218 can close) or whether the evidence still shows `bind_timeout_no_discovery` + `startup_window_present_no_discovery` (then Phase 2 scheme isolation is genuinely required).
- [ ] **Step 3: Finish** — `superpowers:finishing-a-development-branch` → push + PR (Codex review), user pulls the merge trigger. PR body: the move (cycle fix), Phase-1-ships-Phase-2-gated, capability flags default false, signals-not-control, and the empirical Phase-1-diagnostics result.

---

## Notes for the implementer

- **`knowledge/` hygiene:** before any commit, if `git status` shows `knowledge/` changes, `git checkout -- knowledge/ && rm -rf knowledge/selectors`.
- **The move (Task 1) is the riskiest mechanical step** — it must be behavior-preserving; the re-export keeps `workbench.py` + the 4 importer tests unchanged. Run those tests immediately after.
- **Reconcile, don't fork:** `LaunchOutcome.reason` is a `DiscoveryFailureReason` (extended), never a parallel enum.
- **Signals, not control:** no UI automation; window data is evidence + a non-causal hint only; never mutate the default profile or user documents; scheme reset is capability-gated and scheme-local-only.
- **Non-goals:** no changes to session routing (P3), registry semantics (P5), artifact registry (P6), or P7.
