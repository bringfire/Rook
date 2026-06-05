"""Unit tests for the rhino_launch leaf module (the launch + readiness primitives).

Grows task-by-task with the Rhino-launch-hardening plan. Task 1 covers the move +
re-export contract; later tasks add the LaunchOutcome/evidence/argv/classifier/primitives.
"""

from __future__ import annotations


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


# ---- Task 2: reason enum extension (reconcile, don't fork) ----

def test_reason_enum_extended_not_forked():
    from rook.rhino_launch import DiscoveryFailureReason
    assert DiscoveryFailureReason.LAUNCH_EXEC_FAILED.value == "launch_exec_failed"
    assert DiscoveryFailureReason.SCHEME_AUTOLOAD_NOT_VALIDATED.value == "scheme_autoload_not_validated"
    # existing members still present (reconciled, not forked)
    assert DiscoveryFailureReason.BIND_TIMEOUT_NO_DISCOVERY.value == "bind_timeout_no_discovery"
    assert DiscoveryFailureReason.EXITED_BEFORE_BIND.value == "exited_before_bind"


# ---- Task 3: LaunchEvidence / LaunchOutcome + capability flags ----

def test_capability_flags_default_false():
    from rook.rhino_launch import SCHEME_ISOLATION_AVAILABLE, CAN_RESET_SCHEME_RECOVERY_STATE
    assert SCHEME_ISOLATION_AVAILABLE is False
    assert CAN_RESET_SCHEME_RECOVERY_STATE is False


def test_evidence_carries_requested_and_active_scheme():
    from rook.rhino_launch import LaunchEvidence
    ev = LaunchEvidence(requestedScheme="RookWorkbench", activeScheme=None, isolationMode="default",
                        discoveryRecordPath=None, discoveryLogSeen=False, windows=[],
                        visibleWindowCount=0, emptyTitleWindowPresent=False, exitCode=None,
                        argv=["R.exe", "/nosplash"], elapsedSeconds=1.5, diagnosticHint=None)
    d = ev.to_dict()
    assert d["requestedScheme"] == "RookWorkbench"
    assert d["activeScheme"] is None
    assert d["isolationMode"] == "default"


def test_outcome_to_dict_round_shape():
    from rook.rhino_launch import LaunchOutcome, LaunchEvidence
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


# ---- Task 4: scheme resolution (requested vs active) + argv builder ----

def test_requested_scheme_default_and_opt_out():
    from rook.rhino_launch import resolve_requested_scheme
    assert resolve_requested_scheme("RookWorkbench", {}) == "RookWorkbench"
    assert resolve_requested_scheme("RookWorkbench", {"ROOK_WORKBENCH_SCHEME": "default"}) is None


def test_active_scheme_unavailable_is_default_even_when_requested():
    from rook.rhino_launch import resolve_active_scheme
    active, mode = resolve_active_scheme("RookWorkbench", scheme_isolation_available=False)
    assert (active, mode) == (None, "default")


def test_active_scheme_available_is_isolated():
    from rook.rhino_launch import resolve_active_scheme
    active, mode = resolve_active_scheme("RookWorkbench", scheme_isolation_available=True)
    assert (active, mode) == ("RookWorkbench", "isolated")


def test_active_scheme_none_request_is_default():
    from rook.rhino_launch import resolve_active_scheme
    assert resolve_active_scheme(None, scheme_isolation_available=True) == (None, "default")


def test_argv_always_nosplash_no_scheme_when_inactive():
    from rook.rhino_launch import build_rhino_argv
    assert build_rhino_argv("R.exe", active_scheme=None) == ["R.exe", "/nosplash"]


def test_argv_adds_scheme_only_when_active():
    from rook.rhino_launch import build_rhino_argv
    assert build_rhino_argv("R.exe", active_scheme="RookWorkbench") == \
        ["R.exe", "/nosplash", "/scheme=RookWorkbench"]


# ---- Task 5: evidence builder (window is evidence + non-causal hint, never a reason) ----

def test_evidence_window_facts_and_noncausal_hint():
    from rook.rhino_launch import _build_evidence
    wins = [{"hwnd": "0x1", "title": "", "visible": True},
            {"hwnd": "0x2", "title": "Rhino", "visible": False}]
    ev = _build_evidence(requested_scheme="RookHarness", active_scheme=None, isolation_mode="default",
                         discovery_record_path=None, discovery_log_seen=False, windows=wins,
                         exit_code=None, argv=["R.exe", "/nosplash"], elapsed=2.0)
    assert ev.visibleWindowCount == 1                # only the visible one
    assert ev.emptyTitleWindowPresent is True
    assert ev.diagnosticHint == "startup_window_present_no_discovery"  # visible window + no discovery
    assert ev.requestedScheme == "RookHarness" and ev.activeScheme is None


def test_evidence_no_hint_when_discovery_present():
    from rook.rhino_launch import _build_evidence
    wins = [{"hwnd": "0x1", "title": "", "visible": True}]
    ev = _build_evidence(requested_scheme=None, active_scheme=None, isolation_mode="default",
                         discovery_record_path="rec.json", discovery_log_seen=True, windows=wins,
                         exit_code=None, argv=["R.exe", "/nosplash"], elapsed=1.0)
    assert ev.diagnosticHint is None                 # discovery present -> no "blocked" hint


# ---- Task 6: split primitives (start_rhino_process + wait_for_rook_readiness) ----

class _FakeProc:
    def __init__(self, pid=111, code=None):
        self.pid = pid
        self._code = code

    def poll(self):
        return self._code


def test_start_returns_live_process_handle_and_evidence_base():
    from rook.rhino_launch import start_rhino_process
    started = start_rhino_process("R.exe", requested_scheme="RookWorkbench", env={},
                                  scheme_isolation_available=False, popen=lambda a: _FakeProc(pid=222))
    assert started.pid == 222
    assert started.process.poll() is None            # caller holds the REAL handle
    assert started.argv == ["R.exe", "/nosplash"]    # isolation off -> default profile
    assert started.requestedScheme == "RookWorkbench" and started.activeScheme is None
    assert started.isolationMode == "default"


def test_start_exec_failure_raises_launchexecerror_with_evidence():
    from rook.rhino_launch import start_rhino_process, exec_failure_outcome, LaunchExecError
    from rook.rhino_launch import DiscoveryFailureReason as R

    def boom(_a):
        raise OSError("nope")
    try:
        start_rhino_process("R.exe", requested_scheme="RookWorkbench", env={},
                            scheme_isolation_available=False, popen=boom)
        assert False, "expected LaunchExecError"
    except LaunchExecError as exc:
        out = exec_failure_outcome(exc)
        assert out.ok is False and out.reason is R.LAUNCH_EXEC_FAILED
        assert out.evidence.argv[:2] == ["R.exe", "/nosplash"]


def test_wait_success_bundles_outcome_and_raw_record():
    from rook.rhino_launch import StartedRhino, wait_for_rook_readiness
    started = StartedRhino(process=_FakeProc(pid=111), pid=111, argv=["R.exe", "/nosplash"],
                           requestedScheme=None, activeScheme=None, isolationMode="default",
                           started_at=0.0, started_wall=0.0)

    class _Rec:
        pid, port = 111, 4567
        path = "rec.json"

    class _Disc:
        def wait_for_ready(self, *a, **k):
            return _Rec()
    rr = wait_for_rook_readiness(started, discovery=_Disc(), ping=lambda h, p: True,
                                 describe_windows=lambda pid: [], log_seen=lambda: True, now=lambda: 1.0)
    assert rr.outcome.ok is True and rr.outcome.pid == 111 and rr.outcome.port == 4567
    assert rr.outcome.discoveryRecordPath == "rec.json" and rr.outcome.reason is None
    assert rr.outcome.evidence.discoveryLogSeen is True       # reflects the log predicate, not ok
    assert rr.record.port == 4567            # the live OwnedRhinoRecord, for in-process bind/_OWNED


def test_wait_passes_through_reason_and_window_is_only_evidence():
    from rook.rhino_launch import StartedRhino, wait_for_rook_readiness, DiscoveryError
    from rook.rhino_launch import DiscoveryFailureReason as R
    started = StartedRhino(process=_FakeProc(pid=111), pid=111, argv=["R.exe", "/nosplash"],
                           requestedScheme="RookHarness", activeScheme=None, isolationMode="default",
                           started_at=0.0, started_wall=0.0)

    class _Disc:
        def wait_for_ready(self, *a, **k):
            raise DiscoveryError("no disc", reason=R.BIND_TIMEOUT_NO_DISCOVERY)
    wins = [{"hwnd": "0x1", "title": "", "visible": True}]
    rr = wait_for_rook_readiness(started, discovery=_Disc(), ping=lambda h, p: False,
                                 describe_windows=lambda pid: wins, log_seen=lambda: False, now=lambda: 2.0)
    assert rr.outcome.ok is False and rr.record is None
    assert rr.outcome.reason is R.BIND_TIMEOUT_NO_DISCOVERY   # FROM the exception, NOT the window
    assert rr.outcome.evidence.emptyTitleWindowPresent is True
    assert rr.outcome.evidence.discoveryLogSeen is False      # no native-discovery log -> plugin likely never started
    assert rr.outcome.evidence.diagnosticHint == "startup_window_present_no_discovery"
    assert rr.outcome.message == "no disc"


def test_discovery_log_seen_true_for_fresh_pid_log(tmp_path):
    import time as _t
    from rook.rhino_launch import _discovery_log_seen
    (tmp_path / "native-discovery-4321.log").write_text("x")      # just written -> fresh mtime
    assert _discovery_log_seen(tmp_path, 4321, _t.time() - 5.0) is True


def test_discovery_log_seen_false_when_missing(tmp_path):
    from rook.rhino_launch import _discovery_log_seen
    assert _discovery_log_seen(tmp_path, 9999, 0.0) is False


def test_discovery_log_seen_false_for_stale_log_guards_pid_reuse(tmp_path):
    import os as _os
    import time as _t
    from rook.rhino_launch import _discovery_log_seen
    p = tmp_path / "native-discovery-4321.log"
    p.write_text("x")
    old = _t.time() - 3600
    _os.utime(p, (old, old))                                     # stale -> a recycled PID's old log
    assert _discovery_log_seen(tmp_path, 4321, _t.time() - 60.0) is False
