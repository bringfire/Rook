from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DIRECTOR_HANDLER = REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorHandler.cpp"
DIRECTOR_FRAME = REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorFrame.cpp"
DIRECTOR_FRAME_HEADER = REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorFrame.h"
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
    # CurrentDisplayModeId was moved to DirectorFrame.cpp (shared with replay).
    frame_source = (REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorFrame.cpp").read_text(encoding="utf-8")
    readback_body = _extract_function(frame_source, "ON_UUID CurrentDisplayModeId")

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
    assert '"frame_count_mismatch"' in parser_body
    assert "fps must be a positive finite number" in parser_body
    assert 'DirectorFrameValidationError("fps_missing"' in parser_body
    assert "width and height must be positive even integers" in parser_body
    assert "kMaxDirectorVideoFrameCount = 5000" in source
    assert "kMaxDirectorVideoWidth = kMaxDirectorCaptureWidth" in source
    assert "kMaxDirectorVideoHeight = kMaxDirectorCaptureHeight" in source
    assert "kMinDirectorVideoFps = 1.0" in source
    assert "kMaxDirectorVideoFps = 240.0" in source
    assert "codec must be h264" in parser_body
    assert "container must be mp4" in parser_body
    assert "input_pattern must be frame_%04d.png" in parser_body
    assert "start_number must be 1" in parser_body

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
    writer_release_index = backend_body.index("writer.Reset();", finalize_index)
    temp_size_index = backend_body.index("const uintmax_t tempBytes = fs::file_size(tempPath, ec);")
    overwrite_index = backend_body.index("result.overwroteExisting = fs::exists(request.outputPath, ec);")
    replace_index = backend_body.index("MoveFileExW")
    output_size_index = backend_body.index("result.bytes = fs::file_size(request.outputPath, ec);")

    assert finalize_index < writer_release_index < temp_size_index < overwrite_index < replace_index < output_size_index


def test_director_depth_pass_route_is_registered_and_delegated():
    handler_header = DIRECTOR_HEADER.read_text(encoding="utf-8")
    server_header = ROOK_SERVER_HEADER.read_text(encoding="utf-8")
    server_source = ROOK_SERVER_CPP.read_text(encoding="utf-8")

    assert re.search(
        r"void\s+HandleDirectorCaptureDepthPass\s*\(\s*const\s+httplib::Request&\s+req,\s*httplib::Response&\s+res\s*\)\s*;",
        handler_header,
    )
    assert re.search(
        r"void\s+HandleDirectorCaptureDepthPass\s*\(\s*const\s+httplib::Request&\s+req,\s*httplib::Response&\s+res\s*\)\s*;",
        server_header,
    )
    assert 'm_server->Post("/director/capture-depth-pass"' in server_source
    assert "Rook::Handlers::HandleDirectorCaptureDepthPass(req, res);" in server_source
    assert 'm_server->Post("/vision/capture-true-depth-test"' not in server_source


def test_director_depth_pass_has_strict_native_contract_and_artifact_schema():
    source = DIRECTOR_HANDLER.read_text(encoding="utf-8")
    parser_body = _extract_function(source, "DepthPassRequest ParseDepthPassRequest")
    capture_body = _extract_function(source, "DepthPassCapture CaptureDepthPassOnMain")
    artifact_body = _extract_function(source, "nlohmann::json BuildDepthPassArtifact")
    handler_body = _extract_function(source, "void HandleDirectorCaptureDepthPass")

    assert "ParseStrictBodyAndDocSn" in handler_body
    assert "request body must be a JSON object" in source
    assert "source must be an object" in parser_body
    assert "source.kind must be active_view or named_view" in parser_body
    assert "output_root must be inside the native director output root" in parser_body
    assert "near_percentile and far_percentile must satisfy 0 <= near < far <= 100" in parser_body
    assert 'OptionalIntInRange(body, "probe_grid", 32, 4, 256, "probe_grid")' in parser_body
    assert 'OptionalBool(body, "invert", true, "invert")' in parser_body

    assert "CRhinoZBuffer zbuffer" in capture_body
    assert "kMaxDirectorDepthPassPixelCount" in source
    assert "Depth capture pixel count exceeds native Director depth-pass bounds" in capture_body
    assert "!capture.cameraDirection.Unitize()" in capture_body
    assert "Depth capture camera direction is invalid" in capture_body
    assert "metric <= 0.0" in capture_body
    assert "restoreViewport();" in capture_body
    assert "viewportRestoredAfterExtract" in capture_body

    assert "std::sort(capture.validMetricDepths.begin(), capture.validMetricDepths.end())" in artifact_body
    assert "PercentileSorted(capture.validMetricDepths" in artifact_body
    assert "std::vector<double> sorted = capture.validMetricDepths" not in artifact_body
    assert "GuidSuffix()" in artifact_body
    assert "artifact_collision" in artifact_body
    assert "fs::create_directory(artifactRoot" in artifact_body
    assert 'result["success"]' not in artifact_body

    for token in [
        "director_depth_pass.v0",
        "experimental",
        "metric_depth",
        "depth_document_units_f32_le.bin",
        "float32",
        "little",
        "row_major",
        "stride_bytes",
        "invalid_value",
        "document_units",
        "mapped_preview",
        "uint16",
        "big",
        "valid_mask",
        "valid_mask_u8.pgm",
        "viewport_restored_after_extract",
        "full_valid_pixels",
    ]:
        assert token in artifact_body

    assert handler_body.index("future.get()") < handler_body.index("BuildDepthPassArtifact")


def test_director_depth_pass_is_not_exposed_as_mcp_tool_yet():
    mcp_source_root = REPO_ROOT / "mcp_server" / "src" / "rook"
    joined_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in mcp_source_root.rglob("*.py")
    )

    assert "/director/capture-depth-pass" not in joined_source
    assert "capture_depth_pass" not in joined_source
    assert "director_depth_pass" not in joined_source


def test_director_publish_video_native_route_is_thin_vision_proxy():
    server_source = ROOK_SERVER_CPP.read_text(encoding="utf-8")
    header_source = (REPO_ROOT / "src" / "RookNative" / "Handlers" / "VisionHandler.h").read_text(encoding="utf-8")
    handler_source = (REPO_ROOT / "src" / "RookNative" / "Handlers" / "VisionHandler.cpp").read_text(encoding="utf-8")

    assert 'm_server->Post("/vision/director/publish-video"' in server_source
    assert "HandleVisionDirectorPublishVideo" in header_source
    assert "void HandleVisionDirectorPublishVideo" in handler_source
    assert (
        'DispatchVisionOp(req, res, "POST /vision/director/publish-video", '
        '"publish_director_video")'
    ) in handler_source
    assert "DirectorVideoPublisher" not in handler_source
    assert "ArtifactStore" not in handler_source
    assert "director_publish_standard_v1" not in handler_source


def test_director_restore_uses_separate_named_bbox_policies():
    source = DIRECTOR_FRAME.read_text(encoding="utf-8")
    validate_body = _extract_function(source, "void ValidateFrameObjects")
    restore_body = _extract_function(source, "bool DirectorObjectPoseGuard::Restore")

    assert "kDirectorSourceStateBboxTolerance" in source
    assert "DirectorSourceStateBboxTolerance" in validate_body
    assert "kDirectorRestoreBboxTolerance" in source
    assert "DirectorRestoreBboxTolerance" in restore_body
    assert "source_state_validation" in source
    assert "DirectorSourceStateBboxTolerancePolicy()" in validate_body
    assert "restore_verification" in source
    assert validate_body != restore_body


def test_director_restore_evidence_records_comparison_availability():
    source = DIRECTOR_FRAME.read_text(encoding="utf-8")
    restore_body = _extract_function(source, "bool DirectorObjectPoseGuard::Restore")

    for token in [
        "bbox_comparison_available",
        "source_object_type",
        "restored_object_type",
        "source_bbox",
        "restored_bbox",
        "bbox_delta_min",
        "bbox_delta_max",
        "bbox_max_delta",
        "bbox_tolerance",
        "bbox_tolerance_policy",
    ]:
        assert token in source

    assert "restored bbox did not match source bbox" in restore_body
    assert "InitializeRestoreDetail" in restore_body
    assert "AddRestoreBboxEvidence" in restore_body
    assert "MarkBboxComparisonUnavailable" in restore_body
    assert "bbox comparison unavailable" in source


def test_director_restore_hard_failures_precede_tolerance_acceptance():
    source = DIRECTOR_FRAME.read_text(encoding="utf-8")
    restore_body = _extract_function(source, "bool DirectorObjectPoseGuard::Restore")

    tolerance_index = restore_body.index("BboxAlmostEqual")
    for marker in [
        "restore transform failed",
        "object not found after restore",
        "restored bbox is invalid",
    ]:
        assert marker in restore_body
        assert restore_body.index(marker) < tolerance_index


def test_director_restore_reads_native_source_object_type_before_inverse_restore():
    source = DIRECTOR_FRAME.read_text(encoding="utf-8")
    restore_body = _extract_function(source, "bool DirectorObjectPoseGuard::Restore")

    init_index = restore_body.index("InitializeRestoreDetail")
    transform_index = restore_body.index("TransformObjectInPlace")
    lookup = "const CRhinoObject* beforeRestoreObj = m_doc ? m_doc->LookupObject(object.uuid) : nullptr;"

    assert lookup in restore_body
    lookup_index = restore_body.index(lookup)
    assert init_index < lookup_index < transform_index

    before_inverse_block = restore_body[lookup_index:transform_index]
    assert "beforeRestoreObj && !beforeRestoreObj->IsDeleted()" in before_inverse_block
    assert 'detail["source_object_type"] = ObjectTypeToString(beforeRestoreObj->ObjectType());' in before_inverse_block


def test_director_restore_source_object_type_is_native_only_evidence():
    source = DIRECTOR_FRAME.read_text(encoding="utf-8")
    header = DIRECTOR_FRAME_HEADER.read_text(encoding="utf-8")
    init_body = _extract_function(source, "nlohmann::json InitializeRestoreDetail")
    parser_body = _extract_function(source, "std::vector<FrameObjectTransform> ParseFrameObjectTransforms")

    assert 'detail["source_object_type"] = nullptr;' in init_body
    assert "NullableString(object.sourceObjectType)" not in init_body
    assert "sourceObjectType" not in source
    assert "sourceObjectType" not in header
    assert 'sourceState.contains("object_type")' not in parser_body
    assert 'sourceState["object_type"]' not in parser_body


def test_director_restore_bbox_axis_deltas_are_signed_directional():
    source = DIRECTOR_FRAME.read_text(encoding="utf-8")
    delta_body = _extract_function(source, "nlohmann::json BboxDeltaToJson")

    for axis in ["x", "y", "z"]:
        assert f"restored.{axis} - source.{axis}" in delta_body
        assert f"std::fabs(restored.{axis} - source.{axis})" not in delta_body


def test_director_transform_call_path_is_evidenced_inside_native_restore():
    source = DIRECTOR_FRAME.read_text(encoding="utf-8")
    transform_body = _extract_function(source, "bool TransformObjectInPlace")
    apply_body = _extract_function(source, "void DirectorObjectPoseGuard::Apply")
    restore_body = _extract_function(source, "bool DirectorObjectPoseGuard::Restore")

    assert (
        'constexpr const char* kDirectorTransformObjectCallPath = '
        '"pDoc->TransformObject(objRef, xform, true, false, true)";'
    ) in source
    assert "pDoc->TransformObject(objRef, xform, true, false, true)" in transform_body
    assert "kDirectorTransformObjectCallPath" in source
    assert '"transform_call_path"' in source
    assert "requested_transform" in apply_body
    assert "requested_inverse_transform" in apply_body
    assert "phase_before_apply" in apply_body
    assert "phase_after_apply" in apply_body
    assert "phase_before_restore" in restore_body
    assert "phase_after_restore" in restore_body


def test_director_transform_diagnostics_do_not_delay_applied_bookkeeping():
    source = DIRECTOR_FRAME.read_text(encoding="utf-8")
    apply_body = _extract_function(source, "void DirectorObjectPoseGuard::Apply")
    restore_body = _extract_function(source, "bool DirectorObjectPoseGuard::Restore")

    transform_index = apply_body.index("const bool applied = TransformObjectInPlace")
    applied_index = apply_body.index("m_applied[i] = true;")
    apply_returned_index = apply_body.index('detail["apply_transform_returned"] = applied;')
    phase_after_apply_index = apply_body.index('detail["phase_after_apply"] = NativeObjectPhaseEvidence')
    assert transform_index < applied_index < apply_returned_index < phase_after_apply_index

    not_applied_index = restore_body.index("if (!m_applied[static_cast<size_t>(i)])")
    inverse_attempt_index = restore_body.index("bool transformedBack = false;", not_applied_index)
    not_applied_branch = restore_body[not_applied_index:inverse_attempt_index]
    push_index = not_applied_branch.index("details.push_back")
    restore_returned_index = not_applied_branch.index('detail["restore_transform_returned"] = false;')
    phase_after_restore_index = not_applied_branch.index('detail["phase_after_restore"] = NativeObjectPhaseEvidence')
    assert restore_returned_index < push_index
    assert phase_after_restore_index < push_index


def test_director_instance_restore_diagnostics_use_native_instance_state():
    source = DIRECTOR_FRAME.read_text(encoding="utf-8")
    helper_body = _extract_function(source, "nlohmann::json NativeObjectPhaseEvidence")

    for token in [
        "RuntimeSerialNumber()",
        "CRhinoInstanceObject::Cast",
        "InstanceDefinition()",
        "InstanceXform()",
        "instance_definition_id",
        "instance_definition_name",
        "instance_xform",
        "object_found",
        "object_deleted",
        "runtime_serial_number",
        "bbox",
    ]:
        assert token in helper_body

    assert "sourceObjectType" not in helper_body
    assert "source_state" not in helper_body


def test_director_instance_restore_slice_keeps_tolerance_and_canvasdirector_parked():
    source = DIRECTOR_FRAME.read_text(encoding="utf-8")
    lower_source = source.lower()
    # The implementation plan that used to declare the file structure was pruned from
    # the public tree (2026-09-22); the parked-module guarantee is now checked
    # directly against the repository instead of against the plan text.

    for token in [
        "kDirectorRestoreSerializationFloor",
        "kDirectorRestoreModelScaleAllowance",
        "kDirectorRestoreModelScaleFactor",
        "kDirectorRestoreAbsoluteCap",
        "kDirectorRestoreBboxToleranceCap",
        "EVIDENCE_SELECTED",
        "evidence_selected",
        "selected_restore_policy",
    ]:
        assert token not in source

    for token in [
        "restore_serialization_floor",
        "restore_model_scale_factor",
        "restore_bbox_tolerance_cap",
        "evidence-selected",
        "evidence_selected",
    ]:
        assert token not in lower_source

    # The parked CanvasDirector modules stay untouched by the restore slice: the
    # native frame must not reference them (the pruned plan's file structure used to
    # guarantee the same thing).
    for token in ["canvasdirector", "canvas_director"]:
        assert token not in lower_source


def test_director_instance_restore_live_repro_is_scratch_and_two_frame():
    live_source = (REPO_ROOT / "mcp_server" / "tests" / "test_director_routes_live.py").read_text(encoding="utf-8")
    start = live_source.index("async def test_director_instance_restore_semantics_large_coordinate_probe")
    body = live_source[start:]

    assert "fresh_document" in body[: body.index(":")]
    assert "_cleanup_instance_restore_probe(created_ids, block_name)" in body
    assert "rhino_delete" in live_source
    assert "rhino_block_delete" in live_source
    assert '"frame_count": 2' in body
    assert 'assert [row["frame_index"] for row in evidence_rows] == [1, 2]' in body
    assert "director.identity_matrix()" in body
    assert "director.translation_matrix([0.0, 0.0, tiny_z])" in body
    assert "125718.338195" in body
    assert "-328450.993563" in body
    assert "InstanceReference" in body
    assert "expected_instance_definition_name=block_name" in body
    assert "instance_restore_semantics_probe.json" in body
    assert body.index("summary_path.write_text") < body.index("for detail in control_details:")


def test_director_pose_bbox_probe_records_raw_tight_and_expected_phase_bboxes():
    source = DIRECTOR_FRAME.read_text(encoding="utf-8")
    phase_body = _extract_function(source, "nlohmann::json NativeObjectPhaseEvidence")
    expected_body = _extract_function(source, "ON_BoundingBox TransformBoundingBoxByCorners")
    apply_body = _extract_function(source, "void DirectorObjectPoseGuard::Apply")
    restore_body = _extract_function(source, "bool DirectorObjectPoseGuard::Restore")

    for token in [
        '"raw_bbox"',
        '"raw_bbox_valid"',
        '"raw_bbox_delta_min"',
        '"raw_bbox_delta_max"',
        '"raw_bbox_max_delta"',
        '"tight_bbox"',
        '"tight_bbox_valid"',
        '"tight_bbox_delta_min"',
        '"tight_bbox_delta_max"',
        '"tight_bbox_max_delta"',
        '"phase_expected_bbox"',
        '"bbox_tolerance"',
        '"bbox_tolerance_policy"',
        "GetTightBoundingBox",
        "BoundingBox()",
    ]:
        assert token in phase_body

    assert "ExpectedPhaseBbox(m_objects[i], ON_Xform::IdentityTransformation)" in apply_body
    assert "ExpectedPhaseBbox(m_objects[i], m_objects[i].delta)" in apply_body
    assert "ExpectedPhaseBbox(object, object.delta)" in restore_body
    assert "ExpectedPhaseBbox(object, ON_Xform::IdentityTransformation)" in restore_body
    assert "const ON_3dPoint transformedCorner = xform * corner" in expected_body
    assert "transformed.Union(ON_BoundingBox(transformedCorner, transformedCorner))" in expected_body
    assert "corner * xform" not in expected_body
    assert "transformed.Union(xform * corner)" not in expected_body
    assert "BboxDeltaToJson" in phase_body
    assert "BboxMaxDelta" in phase_body


def test_director_pose_bbox_helper_prefers_tight_with_raw_fallback():
    source = DIRECTOR_FRAME.read_text(encoding="utf-8")
    header = DIRECTOR_FRAME_HEADER.read_text(encoding="utf-8")

    assert "struct DirectorPoseBboxResult" in header
    assert "DirectorPoseBboxResult DirectorObjectPoseBbox(const CRhinoObject& obj);" in header

    helper_body = _extract_function(source, "DirectorPoseBboxResult DirectorObjectPoseBbox")
    helper_index = source.index("DirectorPoseBboxResult DirectorObjectPoseBbox")
    validate_index = source.index("void ValidateFrameObjects")
    assert source.index("bool BboxAlmostEqual") < helper_index < validate_index
    assert "obj.GetTightBoundingBox(bbox)" in helper_body
    assert '"tight_object"' in helper_body
    assert "obj.BoundingBox()" in helper_body
    assert '"raw_object_fallback"' in helper_body
    assert '"unavailable"' in helper_body


def test_director_pose_bbox_helper_is_used_for_director_pose_truth():
    frame_source = DIRECTOR_FRAME.read_text(encoding="utf-8")
    handler_source = DIRECTOR_HANDLER.read_text(encoding="utf-8")

    serialize_body = _extract_function(handler_source, "nlohmann::json SerializeObjectState")
    validate_body = _extract_function(frame_source, "void ValidateFrameObjects")
    phase_body = _extract_function(frame_source, "nlohmann::json NativeObjectPhaseEvidence")
    restore_body = _extract_function(frame_source, "bool DirectorObjectPoseGuard::Restore")

    for body in [serialize_body, validate_body, phase_body, restore_body]:
        assert "DirectorObjectPoseBbox(*obj)" in body or "DirectorObjectPoseBbox(*restoredObj)" in body

    assert '"bbox_method"' in serialize_body
    assert '"bbox_method"' in phase_body
    assert '"restored_bbox_method"' in restore_body
    assert "restoredObj->BoundingBox()" not in restore_body
    assert "ON_BoundingBox currentBbox = obj->BoundingBox();" not in validate_body
    assert "ON_BoundingBox bbox = obj->BoundingBox();" not in serialize_body
    assert "kDirectorRestoreModelScaleFactor" not in frame_source
    assert "kDirectorRestoreBboxToleranceCap" not in frame_source
    assert "std::this_thread::sleep" not in frame_source
    assert "Sleep(" not in frame_source
