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
    src = _read(REPLAY_CPP)
    replay = _extract_function(src, "HandleDirectorReplay")
    assert "DispatchDrainSuspension" in replay
    assert replay.count("DispatchDrainSuspension ") == 1     # ONE guard for the whole loop
    assert "DirectorObjectPoseGuard" in replay
    assert "DirectorViewportGuard" in replay
    assert replay.count("DirectorViewportGuard ") == 1
    assert "SetCameraFromFrame(" in replay
    assert "Apply()" in replay and "Restore(" in replay and "Disarm()" in replay
    # Shared pure parsers now live in the frame-payload parser, not inline in the handler.
    frames = _extract_function(src, "ParseReplayFramePayloads")
    assert "ParseFrameObjectTransforms(" in frames
    assert "ParseCamera(" in frames


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
    src = _read(REPLAY_CPP)
    handler = _extract_function(src, "HandleDirectorReplay")
    assert "BuildReplayInstructionFromBody" in handler
    assert handler.index("BuildReplayInstructionFromBody") < handler.index("Dispatch(")
    build = _extract_function(src, "BuildReplayInstructionFromBody")
    assert build.index("ParseReplayTrack") < build.index("ParseReplayOptions") < build.index("ParseReplayFramePayloads")


def test_replay_remaps_shared_helper_errors_to_replay_codes():
    src = _read(REPLAY_CPP)
    frames = _extract_function(src, "ParseReplayFramePayloads")
    assert "catch (const DirectorFrameValidationError" in frames or \
           "catch (DirectorFrameValidationError" in frames
    assert "track_invalid" in frames
    assert "affectedObjectIds" in frames
    handler = _extract_function(src, "HandleDirectorReplay")
    assert "object_not_found" in handler


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


def test_replay_uses_replay_request_error_with_single_handler_catch():
    src = _read(REPLAY_CPP)
    assert "class ReplayRequestError" in src
    handler = _extract_function(src, "HandleDirectorReplay")
    assert handler.count("catch (const ReplayRequestError&") == 1


def test_replay_request_body_parser_preserves_strict_envelope():
    src = _read(REPLAY_CPP)
    body_parser = _extract_function(src, "ParseReplayRequestBody")
    assert "kMaxPayloadBytes" in body_parser and "payload_too_large" in body_parser
    assert "nlohmann::json::parse(" in body_parser          # strict throwing parse
    assert "ParseBodyAndDocSn" not in src                   # replay keeps its stricter envelope


def test_replay_session_id_parser_exists():
    src = _read(REPLAY_CPP)
    assert "ParseReplaySessionId(" in src
    parser = _extract_function(src, "ParseReplaySessionId")
    assert "IsValidReplaySessionId" in parser and "invalid_session_id" in parser


def test_replay_instruction_is_move_only_and_dispatched_by_move():
    src = _read(REPLAY_CPP)
    assert "struct ReplayInstruction" in src
    assert "ReplayInstruction(const ReplayInstruction&) = delete" in src
    handler = _extract_function(src, "HandleDirectorReplay")
    assert "ReplayInstruction instruction = BuildReplayInstructionFromBody(" in handler
    assert "instruction = std::move(instruction)" in handler   # captured by move into the lambda


def test_replay_reserves_slot_before_building_instruction():
    handler = _extract_function(_read(REPLAY_CPP), "HandleDirectorReplay")
    assert handler.index("ReserveReplaySlot(") < handler.index("BuildReplayInstructionFromBody(")


def test_replay_named_worker_phase_helpers_exist():
    src = _read(REPLAY_CPP)
    for fn in ["ParseReplayRequestBody", "ParseReplaySessionId", "BuildReplayInstructionFromBody"]:
        assert f"{fn}(" in src, f"missing helper {fn}"


def test_replay_track_parser_owns_envelope():
    src = _read(REPLAY_CPP)
    track = _extract_function(src, "ParseReplayTrack")
    for tok in ["transform_semantics", "unsupported_transform_semantics",
                "unsupported_replay_option", "animated_object_ids",
                "object_count_exceeds_cap", "frame_count", "frame_count_exceeds_cap",
                "camera_frames", "object_frames", "track_invalid"]:
        assert tok in track, f"ParseReplayTrack missing {tok}"
    build = _extract_function(src, "BuildReplayInstructionFromBody")
    assert "ParseReplayTrack(" in build


def test_replay_options_parser_owns_caps():
    src = _read(REPLAY_CPP)
    opts = _extract_function(src, "ParseReplayOptions")
    for tok in ["invalid_fps", "frame_dwell_exceeds_cap", "replay_duration_exceeds_cap",
                "restore_on_finish"]:
        assert tok in opts, f"ParseReplayOptions missing {tok}"
    assert opts.index("invalid_fps") < opts.index("frame_dwell_exceeds_cap") < opts.index("replay_duration_exceeds_cap")
    build = _extract_function(src, "BuildReplayInstructionFromBody")
    assert "ParseReplayOptions(" in build


def test_replay_frame_parser_owns_per_frame_content():
    frames = _extract_function(_read(REPLAY_CPP), "ParseReplayFramePayloads")
    assert "ParseCamera(" in frames and "ParseFrameObjectTransforms(" in frames
    assert "track_invalid" in frames
    assert "animated_object_ids" in frames or "frameIds" in frames   # exact-set equality check


def test_replay_verification_covers_shared_pose_guard_restore_contract():
    frame = _read(FRAME_H)
    replay = _extract_function(_read(REPLAY_CPP), "HandleDirectorReplay")

    assert "DirectorObjectPoseGuard" in frame
    assert "bbox_comparison_available" in _read(FRAME_H) or "bbox_comparison_available" in _read(REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorFrame.cpp")
    assert "restore_failed" in replay
    assert "dirty_partial_state" in replay
    assert "poseGuard->Restore(evidence)" in replay
