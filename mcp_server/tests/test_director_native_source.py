from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DIRECTOR_HANDLER = REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorHandler.cpp"
DIRECTOR_HEADER = REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorHandler.h"
ROOK_SERVER_CPP = REPO_ROOT / "src" / "RookNative" / "RookServer.cpp"
ROOK_SERVER_HEADER = REPO_ROOT / "src" / "RookNative" / "RookServer.h"


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


def test_director_curve_samples_route_is_registered_and_delegated():
    handler_header = DIRECTOR_HEADER.read_text(encoding="utf-8")
    server_header = ROOK_SERVER_HEADER.read_text(encoding="utf-8")
    server_source = ROOK_SERVER_CPP.read_text(encoding="utf-8")

    assert re.search(
        r"void\s+HandleDirectorCurveSamples\s*\(\s*const\s+httplib::Request&\s+req,\s*httplib::Response&\s+res\s*\)\s*;",
        handler_header,
    )
    assert re.search(
        r"void\s+HandleDirectorCurveSamples\s*\(\s*const\s+httplib::Request&\s+req,\s*httplib::Response&\s+res\s*\)\s*;",
        server_header,
    )
    assert 'm_server->Post("/director/curve-samples"' in server_source
    assert "Rook::Handlers::HandleDirectorCurveSamples(req, res);" in server_source


def test_director_curve_samples_has_required_contract_guards():
    source = DIRECTOR_HANDLER.read_text(encoding="utf-8")
    parser_body = _extract_function(source, "CurveSampleRequest ParseCurveSampleRequest")
    sampler_body = _extract_function(source, "nlohmann::json SampleDirectorCurve")
    handler_body = _extract_function(source, "void HandleDirectorCurveSamples")

    assert "kMaxDirectorCurveSampleFrameCount = 5000" in source
    assert "sampling must be an object" in parser_body
    assert 'RequireString(sampling, "mode", "sampling.mode")' in parser_body
    assert 'RequireFiniteNumber(sampling, "start", "sampling.start")' in parser_body
    assert 'RequireFiniteNumber(sampling, "end", "sampling.end")' in parser_body
    assert "normalized_parameter" in parser_body
    assert "request.samplingEnd < request.samplingStart" in parser_body
    assert "sampling.start must be less than or equal to sampling.end" in parser_body
    assert "!obj || obj->IsDeleted()" in sampler_body
    assert "curve_not_found" in sampler_body
    assert "not_curve" in sampler_body
    assert "invalid_curve_sample" in sampler_body
    assert "director_read_failed" in handler_body
    assert "MakeErrorData(ex.code, ex.what())" in handler_body
