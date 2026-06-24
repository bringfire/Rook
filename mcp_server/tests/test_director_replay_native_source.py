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
