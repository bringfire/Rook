from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRAME_H = REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorFrame.h"
DIRECTOR_CPP = REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorHandler.cpp"
REPLAY_CPP = REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorReplayHandler.cpp"
SERVER_CPP = REPO_ROOT / "src" / "RookNative" / "RookServer.cpp"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _extract_function(src: str, name: str) -> str:
    """Extract the body of a C++ function by brace-balancing after name(."""
    idx = src.find(name + "(")
    if idx == -1:
        return ""
    # Find the opening brace of the function body
    brace_start = src.find("{", idx)
    if brace_start == -1:
        return ""
    depth = 0
    i = brace_start
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[idx:i + 1]
        i += 1
    return src[idx:]


def test_directorframe_exposes_pure_shared_primitives():
    header = _read(FRAME_H)
    for sym in [
        "struct FrameObjectTransform", "struct FrameCamera",
        "ParseCamera", "ParseFrameObjectTransforms", "ValidateFrameObjects",
        "SetCameraFromFrame", "class DirectorObjectPoseGuard",
        "class DirectorViewportGuard", "void Disarm",
        # dependency closure of the viewport guard must be declared here too:
        "ViewportAlmostEqual", "CurrentDisplayModeId", "DisplayModeToJson",
        "ValidateSlice1ModelRhinoView",
    ]:
        assert sym in header, f"DirectorFrame.h missing {sym}"
    # Capture-only parser must NOT leak into the shared unit.
    assert "ParseFrameInstruction" not in header
    assert "run_root" not in header and "output_path" not in header
    # Header-exposed RAII guards must be non-copyable AND non-movable (double-restore hazard).
    for guard in ["DirectorObjectPoseGuard", "DirectorViewportGuard"]:
        assert f"{guard}(const {guard}&) = delete;" in header
        assert f"{guard}({guard}&&) = delete;" in header


def test_frame_capture_uses_shared_unit_and_keeps_capture_parser():
    src = _read(DIRECTOR_CPP)
    assert '#include "Handlers/DirectorFrame.h"' in src or '#include "DirectorFrame.h"' in src
    assert "DirectorObjectPoseGuard" in src      # still used by ExecuteFrameTransaction
    assert "DirectorViewportGuard" in src
    assert "SetCameraFromFrame(" in src
    assert "FrameInstruction ParseFrameInstruction(" in src  # capture parser stays here


def test_replay_routes_registered():
    server = _read(SERVER_CPP)
    assert 'm_server->Post("/director/replay"' in server
    assert "Rook::Handlers::HandleDirectorReplay(req, res);" in server
    assert 'm_server->Post("/director/replay/cancel"' in server
    assert "Rook::Handlers::HandleDirectorReplayCancel(req, res);" in server


def test_cancel_handler_is_worker_thread_only():
    src = _read(REPLAY_CPP)
    cancel = _extract_function(src, "HandleDirectorReplayCancel")
    # The cancel route must never dispatch to the UI thread.
    assert "CMainThreadDispatcher::Instance().Dispatch" not in cancel
    # Idempotent, structured outcomes; no active-id leak.
    assert "no_active_replay" in cancel
    assert "session_mismatch" in cancel
    assert "cancel_requested" in cancel
    assert "active_replay_session_id" not in cancel


def test_replay_session_id_validation_present():
    src = _read(REPLAY_CPP)
    assert "IsValidReplaySessionId" in src
    assert "invalid_session_id" in src


# ---------------------------------------------------------------------------
# Task-3 source-analysis tests — added for the guarded replay loop
# ---------------------------------------------------------------------------

def test_replay_loop_uses_single_guard_and_shared_primitives():
    replay = _extract_function(_read(REPLAY_CPP), "HandleDirectorReplay")
    assert "DispatchDrainSuspension" in replay
    assert replay.count("DispatchDrainSuspension ") == 1   # ONE guard for the whole loop
    assert "DirectorObjectPoseGuard" in replay             # real pose guard, per frame
    assert "DirectorViewportGuard" in replay               # real camera guard
    assert replay.count("DirectorViewportGuard ") == 1     # one camera snapshot for the whole replay
    assert "ParseFrameObjectTransforms(" in replay         # pure shared parsers only
    assert "ParseCamera(" in replay
    assert "SetCameraFromFrame(" in replay
    # Guard methods are called (idiomatic poseGuard->Apply() / viewportGuard.Restore() / Disarm()).
    assert "Apply()" in replay and "Restore(" in replay and "Disarm()" in replay


def test_replay_checks_cancel_before_applying_each_frame():
    # The per-frame cancel check must precede the apply (poseGuard.emplace), so a cancel
    # before frame 0 reports frames_played=0 and never applies a frame.
    replay = _extract_function(_read(REPLAY_CPP), "HandleDirectorReplay")
    loop = replay[replay.index("for (int i"):]
    assert "Slot().cancel.load" in loop
    assert "poseGuard.emplace" in loop
    assert loop.index("Slot().cancel.load") < loop.index("poseGuard.emplace"), \
        "cancel must be checked before the first poseGuard.emplace/Apply"


def test_replay_does_not_use_capture_parser_or_io():
    replay = _extract_function(_read(REPLAY_CPP), "HandleDirectorReplay")
    # Replay must NOT reach into capture-only parsing or file I/O.
    assert "ParseFrameInstruction" not in replay
    assert "CaptureViewportToFile" not in replay
    for token in ["output_path", "run_root", "output_root"]:
        assert token not in replay


def test_replay_validation_caps_and_cancel_present():
    src = _read(REPLAY_CPP)
    for token in [
        "absolute_from_source", "unsupported_transform_semantics",
        "unsupported_replay_option", "invalid_fps",
        "frame_dwell_exceeds_cap", "replay_duration_exceeds_cap",
        "frame_count_exceeds_cap", "object_count_exceeds_cap",
        "replay_already_active", "object_not_found", "object_state_mismatch",
        "unsupported_view", "frame_apply_failed",
        "250", "60000", "3000", "256",
    ]:
        assert token in src, f"replay handler missing {token}"
    replay = _extract_function(src, "HandleDirectorReplay")
    assert "Slot().cancel.load" in replay


def test_replay_preparses_and_validates_every_frame_before_dispatch():
    handler = _extract_function(_read(REPLAY_CPP), "HandleDirectorReplay")
    # Every frame's object set is checked against the declared ids, pre-parsed up front.
    assert "animated_object_ids" in handler           # exact-set-equality check
    assert "perFrameObjects" in handler               # pre-parsed per-frame vector
    assert "perFrameCameras" in handler
    # The pre-parse + the Dispatch must be ordered: parsing precedes the UI dispatch.
    assert handler.index("perFrameObjects") < handler.index("Dispatch(")


def test_replay_remaps_shared_helper_errors_to_replay_codes():
    handler = _extract_function(_read(REPLAY_CPP), "HandleDirectorReplay")
    # Replay catches the shared helper's exception and remaps — it does not emit
    # the helper's generic invalid_input, and does not change the helper.
    assert "catch (const DirectorFrameValidationError" in handler or \
           "catch (DirectorFrameValidationError" in handler
    assert "track_invalid" in handler          # worker-phase parse failures
    assert "object_not_found" in handler       # UI-phase ValidateFrameObjects failures
    assert "affectedObjectIds" in handler      # object_id carried from the helper


def test_replay_surfaces_restore_failures_instead_of_reporting_success():
    """PR2 safety contract: DirectorObjectPoseGuard::Restore and
    DirectorViewportGuard::Restore return false when restoration is incomplete.
    Replay must CHECK every restore result — a failed restore must not (a) continue
    to the next frame from dirty object state, nor (b) be reported as
    status:completed / status:cancelled with restored:true. On restore failure the
    handler must return a restore-failure outcome (restored:false, dirty_partial_state).
    """
    handler = _extract_function(_read(REPLAY_CPP), "HandleDirectorReplay")
    # A dedicated restore-failure outcome exists.
    assert "restore_failed" in handler, "no restore-failure outcome — restore results are ignored"
    # Restore results are consumed in a boolean/branch context, not discarded as bare
    # statements (the pre-fix bug was `poseGuard->Restore(evidence);` with the bool dropped).
    assert ("restoreOrError" in handler) or ("!poseGuard->Restore(" in handler) \
        or ("= poseGuard->Restore(" in handler), "restore result is not checked"
    # dirty_partial_state must now be signalled on restore-failure paths too, not only on
    # the single apply-failure catch it was originally limited to.
    assert handler.count("dirty_partial_state") >= 2, \
        "restore-failure paths must signal dirty_partial_state, not just frame_apply_failed"


def test_replay_restore_failure_dirty_partial_state_includes_viewport():
    """A viewport-only restore failure (objects restored, camera not) is still dirty
    partial state. The restoreOrError helper must derive dirty_partial_state from BOTH
    the object AND viewport restore results, not only poseGuard->HasDirtyPartialState()
    — otherwise a failed camera restore reports restored:false but dirty_partial_state:false.
    """
    src = _read(REPLAY_CPP)
    start = src.index("auto restoreOrError")
    end = src.index("for (int i", start)
    helper = src[start:end]
    dps_idx = helper.index("dirty_partial_state")
    dps_stmt = helper[dps_idx:helper.index(";", dps_idx)]
    assert "!viewportOk" in dps_stmt and "!objectsOk" in dps_stmt, dps_stmt


def test_replay_disengages_pose_guard_after_between_frame_restore():
    """DirectorObjectPoseGuard::Restore re-applies the inverse delta on every call for an
    applied object (NOT idempotent — no m_restored guard before TransformObjectInPlace). The
    between-frame restore returns objects to source but leaves the guard engaged; a cancel
    observed immediately after (between-frame inner cancel) or at the top of the next frame
    routes through restoreOrError(), which would call Restore() a SECOND time → double inverse
    → corrupted position + false restore_failed. So after a successful between-frame restore the
    guard must be disengaged (poseGuard.reset()) before the cancel check.
    """
    handler = _extract_function(_read(REPLAY_CPP), "HandleDirectorReplay")
    idx = handler.index("Between non-final frames")
    block = handler[idx:handler.index("Final frame:", idx)]   # exactly the between-frames block
    assert "poseGuard.reset()" in block, "pose guard not reset after between-frame restore"
    # reset must come AFTER the between-frame Restore and BEFORE the cancel check that calls
    # restoreOrError (otherwise the cancel path re-restores already-restored objects).
    assert block.index("poseGuard->Restore(evidence)") < block.index("poseGuard.reset()"), \
        "reset must follow the between-frame restore"
    assert block.index("poseGuard.reset()") < block.index("Slot().cancel.load"), \
        "reset must precede the between-frame cancel check"
