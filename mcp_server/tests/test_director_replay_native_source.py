from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRAME_H = REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorFrame.h"
DIRECTOR_CPP = REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorHandler.cpp"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


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
