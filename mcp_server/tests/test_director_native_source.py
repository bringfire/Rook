from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DIRECTOR_HANDLER = REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorHandler.cpp"


def _extract_function(source: str, signature: str) -> str:
    start = source.index(signature)
    body_start = source.index("{", start)
    depth = 0
    for index in range(body_start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"Could not extract function for {signature!r}")


def test_display_readback_mismatch_copies_diagnostics_before_failure():
    source = DIRECTOR_HANDLER.read_text(encoding="utf-8")
    apply_body = _extract_function(source, "nlohmann::json ApplyViewportForFrame")
    transaction_body = _extract_function(source, "nlohmann::json ExecuteFrameTransaction")

    assert "Applied display mode did not match requested mode" not in apply_body

    copy_index = transaction_body.index(
        'data["display"]["readback_matches"] = viewportApplyEvidence["display_readback_matches"];'
    )
    failure_index = transaction_body.index('if (!data["display"]["applied"].get<bool>())')
    capture_index = transaction_body.index("CaptureViewportToFile")

    assert copy_index < failure_index < capture_index
    assert "Applied display mode did not match requested mode" in transaction_body[failure_index:capture_index]


def test_display_readback_uses_viewport_setting_not_pipeline_attributes():
    source = DIRECTOR_HANDLER.read_text(encoding="utf-8")
    readback_body = _extract_function(source, "ON_UUID CurrentDisplayModeId")

    assert "ActiveViewport().m_v.m_display_mode_id" in readback_body
    assert "DisplayAttributes()" not in readback_body
