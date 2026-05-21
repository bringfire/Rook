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


def test_director_video_assemble_route_is_registered_and_delegated():
    handler_header = DIRECTOR_HEADER.read_text(encoding="utf-8")
    server_header = ROOK_SERVER_HEADER.read_text(encoding="utf-8")
    server_source = ROOK_SERVER_CPP.read_text(encoding="utf-8")

    assert re.search(
        r"void\s+HandleDirectorVideoAssemble\s*\(\s*const\s+httplib::Request&\s+req,\s*httplib::Response&\s+res\s*\)\s*;",
        handler_header,
    )
    assert re.search(
        r"void\s+HandleDirectorVideoAssemble\s*\(\s*const\s+httplib::Request&\s+req,\s*httplib::Response&\s+res\s*\)\s*;",
        server_header,
    )
    assert 'm_server->Post("/director/video-assemble"' in server_source
    assert "Rook::Handlers::HandleDirectorVideoAssemble(req, res);" in server_source


def test_director_video_assemble_has_native_parser_policy_and_backend_contract():
    source = DIRECTOR_HANDLER.read_text(encoding="utf-8")
    parser_body = _extract_function(source, "VideoAssembleRequest ParseVideoAssembleRequest")
    policy_body = _extract_function(source, "void ValidateVideoAssemblyPolicy")
    handler_body = _extract_function(source, "void HandleDirectorVideoAssemble")

    assert "run_root is required" in parser_body
    assert "frames_dir is required" in parser_body
    assert "output_path is required" in parser_body
    assert "frame_count must be a positive integer" in parser_body
    assert "fps must be a positive finite number" in parser_body
    assert "width and height must be positive even integers" in parser_body
    assert "kMaxDirectorVideoFrameCount = 5000" in source
    assert "kMaxDirectorVideoWidth = kMaxDirectorCaptureWidth" in source
    assert "kMaxDirectorVideoHeight = kMaxDirectorCaptureHeight" in source
    assert "kMinDirectorVideoFps = 1.0" in source
    assert "kMaxDirectorVideoFps = 240.0" in source
    assert "codec must be h264" in parser_body
    assert "container must be mp4" in parser_body
    assert "input_pattern must be frame_%04d.png" in parser_body

    assert "GetAllowedDirectorRoot()" in policy_body
    assert "run_root_policy_violation" in policy_body
    assert "frames_dir_policy_violation" in policy_body
    assert "output_policy_violation" in policy_body
    assert 'request.runRoot / L"frames"' in policy_body
    assert 'request.runRoot / L"videos"' in policy_body

    assert "MFCreateSinkWriterFromURL" in source
    assert "MFVideoFormat_H264" in source
    assert "MFVideoFormat_NV12" in source
    assert "CLSID_WICImagingFactory" in source
    assert "unsupported_frame_format" in source
    assert "unsupported_dimensions" in source
    assert "backend_unavailable" in source
    assert "backend_encode_failed" in source
    assert "alpha_background" in source
    assert "MoveFileExW" in source
    assert "MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH" in source
    assert ".tmp.mp4" in source
    assert "MakeVideoErrorData" in handler_body


def test_director_video_assemble_validates_temp_mp4_before_replacing_preview():
    source = DIRECTOR_HANDLER.read_text(encoding="utf-8")
    backend_body = _extract_function(source, "VideoBackendResult EncodeMp4WithMediaFoundation")

    finalize_index = backend_body.index('writer->Finalize()')
    temp_size_index = backend_body.index("const uintmax_t tempBytes = fs::file_size(tempPath, ec);")
    overwrite_index = backend_body.index("result.overwroteExisting = fs::exists(request.outputPath, ec);")
    replace_index = backend_body.index("MoveFileExW")
    output_size_index = backend_body.index("result.bytes = fs::file_size(request.outputPath, ec);")

    assert finalize_index < temp_size_index < overwrite_index < replace_index < output_size_index
