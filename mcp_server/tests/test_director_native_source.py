from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DIRECTOR_HANDLER = REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorHandler.cpp"
DIRECTOR_HEADER = REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorHandler.h"
ROOK_SERVER_CPP = REPO_ROOT / "src" / "RookNative" / "RookServer.cpp"
ROOK_SERVER_HEADER = REPO_ROOT / "src" / "RookNative" / "RookServer.h"
SNAPSHOTS_HEADER = REPO_ROOT / "src" / "RookNative" / "Models" / "Snapshots.h"
DOCUMENT_HANDLER = REPO_ROOT / "src" / "RookNative" / "Handlers" / "DocumentHandler.cpp"
RHINO_SERIALIZER = REPO_ROOT / "src" / "RookNative" / "Serialization" / "RhinoSerializer.cpp"


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


def _extract_struct(source: str, signature: str) -> str:
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
    raise AssertionError(f"Could not extract struct for {signature!r}")


def _extract_occurrence_inventory_source(source: str) -> str:
    start = source.index("kMaxDirectorOccurrencePageSize")
    end = source.index("void HandleDirectorObjectStates", start)
    return source[start:end]


def test_document_snapshot_has_session_id_and_saved_fields():
    source = SNAPSHOTS_HEADER.read_text(encoding="utf-8")
    struct_body = _extract_struct(source, "struct DocumentSnapshot")

    assert re.search(r"std::string\s+documentSessionId\s*;", struct_body)
    assert re.search(r"bool\s+isSaved\s*=\s*false\s*;", struct_body)


def test_document_serializer_emits_session_id_and_saved_fields():
    source = RHINO_SERIALIZER.read_text(encoding="utf-8")
    serializer_body = _extract_function(source, "nlohmann::json SerializeDocument")

    assert '{"documentSessionId", doc.documentSessionId}' in serializer_body
    assert '{"isSaved", doc.isSaved}' in serializer_body


def test_document_handler_sets_saved_from_path_not_modified_state():
    source = DOCUMENT_HANDLER.read_text(encoding="utf-8")
    handler_body = _extract_function(source, "void HandleDocument")

    assert "snap.path = WideToUtf8(pDoc->GetPathName());" in handler_body
    assert re.search(r"snap\.isSaved\s*=\s*!\s*snap\.path\.empty\s*\(\s*\)\s*;", handler_body)
    assert not re.search(r"snap\.isSaved\s*=\s*[^;]*IsModified\s*\(", handler_body)


def test_document_handler_generates_session_id_instead_of_exposing_runtime_serial():
    source = DOCUMENT_HANDLER.read_text(encoding="utf-8")
    handler_body = _extract_function(source, "void HandleDocument")

    assert "CoCreateGuid" in source
    assert "UuidToString" in source
    assert re.search(r"snap\.documentSessionId\s*=\s*\w+\s*\(\s*pDoc->RuntimeSerialNumber\(\)\s*\)\s*;", handler_body)
    assert not re.search(
        r"snap\.documentSessionId\s*=\s*(?:std::to_string\s*\(\s*)?pDoc->RuntimeSerialNumber\s*\(",
        handler_body,
    )
    assert "std::to_string(runtimeSerial)" not in source


def test_document_session_id_cache_is_keyed_by_runtime_serial_primitives_only():
    source = DOCUMENT_HANDLER.read_text(encoding="utf-8")
    helper_body = _extract_function(source, "std::string DocumentSessionIdForRuntimeSerial")

    assert re.search(r"std::unordered_map\s*<\s*unsigned\s+int\s*,\s*std::string\s*>", source)
    assert re.search(r"\.find\s*\(\s*runtimeSerial\s*\)", helper_body)
    assert re.search(r"\[\s*runtimeSerial\s*\]\s*=", helper_body)
    assert "std::lock_guard<std::mutex>" in helper_body
    assert "CRhinoDoc*" not in helper_body


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


def test_director_publish_video_native_route_is_thin_vision_proxy():
    server_source = ROOK_SERVER_CPP.read_text(encoding="utf-8")
    header_source = (REPO_ROOT / "src" / "RookNative" / "Handlers" / "VisionHandler.h").read_text(encoding="utf-8")
    handler_source = (REPO_ROOT / "src" / "RookNative" / "Handlers" / "VisionHandler.cpp").read_text(encoding="utf-8")

    assert 'm_server->Post("/vision/director/publish-video"' in server_source
    assert "HandleVisionDirectorPublishVideo" in header_source
    assert "void HandleVisionDirectorPublishVideo" in handler_source
    assert 'DispatchVisionOp(req, res, "POST /vision/director/publish-video", "publish_director_video")' in handler_source
    assert "DirectorVideoPublisher" not in handler_source
    assert "ArtifactStore" not in handler_source
    assert "director_publish_standard_v1" not in handler_source


def test_occurrence_inventory_route_declared_registered_and_delegated():
    handler_header = DIRECTOR_HEADER.read_text(encoding="utf-8")
    server_header = ROOK_SERVER_HEADER.read_text(encoding="utf-8")
    server_source = ROOK_SERVER_CPP.read_text(encoding="utf-8")

    signature = (
        r"void\s+HandleDirectorOccurrenceInventory\s*\("
        r"\s*const\s+httplib::Request&\s+req,\s*httplib::Response&\s+res\s*\)\s*;"
    )

    assert re.search(signature, handler_header)
    assert re.search(signature, server_header)
    assert 'm_server->Post("/director/occurrence-inventory"' in server_source
    assert "void CRookServer::HandleDirectorOccurrenceInventory" in server_source
    assert "Rook::Handlers::HandleDirectorOccurrenceInventory(req, res);" in server_source


def test_occurrence_inventory_has_paging_session_and_error_contract():
    source = DIRECTOR_HANDLER.read_text(encoding="utf-8")
    occurrence_source = _extract_occurrence_inventory_source(source)

    assert "kMaxDirectorOccurrencePageSize" in source
    assert "source_object_ids" in occurrence_source
    assert "inventory_session_id" in occurrence_source
    assert "page_size" in occurrence_source
    assert "cursor" in occurrence_source
    assert "records" in occurrence_source
    assert "next_cursor" in occurrence_source
    assert "complete" in occurrence_source
    assert "warnings" in occurrence_source
    assert "source_document_key" in occurrence_source
    assert "inventory_context_fingerprint" in occurrence_source
    assert "document_runtime_serial" in occurrence_source
    assert "traversal_ordering" in occurrence_source
    assert "inventory_session_invalid" in occurrence_source
    assert "inventory_stale" in occurrence_source
    assert "source_document_fingerprint" not in source


def test_occurrence_inventory_source_document_key_is_not_raw_runtime_context():
    source = DIRECTOR_HANDLER.read_text(encoding="utf-8")
    source_key_body = _extract_function(source, "std::string SourceDocumentKeyForOccurrence")
    context_key_body = _extract_function(source, "std::string DocumentContextKeyForOccurrence")

    assert "source_path_hash:" in source_key_body
    assert "unsaved_session:" in source_key_body
    assert "native-runtime:" not in source
    assert "std::to_string(pDoc->RuntimeSerialNumber())" not in source_key_body
    assert "document_runtime_serial" in context_key_body


def test_occurrence_inventory_emits_required_record_and_path_facts():
    source = DIRECTOR_HANDLER.read_text(encoding="utf-8")
    occurrence_source = _extract_occurrence_inventory_source(source)

    assert '"actor_root"' in occurrence_source
    assert '"nested_instance"' in occurrence_source
    assert '"definition_object"' in occurrence_source
    assert "source_top_level_object_id" in occurrence_source
    assert "source_occurrence_path" in occurrence_source
    assert "native_role_hint" in occurrence_source

    required_fact_names = [
        "kind",
        "definition_name",
        "definition_id",
        "definition_object_index",
        "instance_reference_id",
        "sibling_ordinal",
        "object_id",
        "object_name",
        "object_type",
        "layer_path",
        "local_transform",
        "world_transform",
        "local_bbox",
        "world_bbox",
        "segment_fingerprint",
        "material_ref",
    ]
    for fact_name in required_fact_names:
        assert fact_name in occurrence_source

    assert "CRhinoInstanceObject::Cast" in occurrence_source
    assert "InstanceDefinition()" in occurrence_source
    assert "ObjectCount()" in occurrence_source
    assert "Object(" in occurrence_source
    assert "InstanceXform()" in occurrence_source
    assert "GetTightBoundingBox" in occurrence_source
    assert "GetLayerPathName" in occurrence_source
    assert "MaterialSource()" in occurrence_source


def test_occurrence_inventory_world_bbox_uses_accumulated_world_transform():
    source = DIRECTOR_HANDLER.read_text(encoding="utf-8")
    occurrence_source = _extract_occurrence_inventory_source(source)

    assert (
        "const ON_BoundingBox worldBbox = nestedInstance\n"
        "            ? TransformBoundingBoxForOccurrence(localBbox, parentWorldTransform)\n"
        "            : TransformBoundingBoxForOccurrence(localBbox, worldTransform);"
    ) in occurrence_source
    assert (
        "const ON_BoundingBox worldBbox = instance\n"
        "        ? localBbox\n"
        "        : TransformBoundingBoxForOccurrence(localBbox, worldTransform);"
    ) in occurrence_source
    assert "const ON_BoundingBox worldBbox = TransformBoundingBoxForOccurrence(localBbox, worldTransform);" not in occurrence_source


def test_occurrence_inventory_handler_is_read_only():
    source = DIRECTOR_HANDLER.read_text(encoding="utf-8")
    occurrence_source = _extract_occurrence_inventory_source(source)

    mutation_patterns = [
        "UndoScope",
        "RunScript",
        "CreateInstanceObject",
        "AddInstanceDefinition",
        "ModifyInstanceDefinition",
        "DeleteInstanceDefinition",
        "AddCurveObject",
        "AddBrepObject",
        "AddMeshObject",
        "AddPointObject",
        "DeleteObject",
        "SetUserString",
        "SetMaterialSource",
        "SetColorSource",
        "ModifyObjectAttributes",
        "Redraw()",
    ]
    for pattern in mutation_patterns:
        assert pattern not in occurrence_source


def test_occurrence_inventory_missing_selected_roots_fail_hard():
    source = DIRECTOR_HANDLER.read_text(encoding="utf-8")
    populate_body = _extract_function(source, "void PopulateOccurrenceInventorySession")

    assert "missing_source_object" in populate_body
    assert "DirectorFrameValidationError" in populate_body
    assert '"inventory_stale"' in populate_body
    assert not re.search(
        r"missing_source_object[\s\S]{0,240}continue\s*;",
        populate_body,
    )


def test_occurrence_inventory_bbox_required_facts_have_non_null_fallback():
    source = DIRECTOR_HANDLER.read_text(encoding="utf-8")
    occurrence_source = _extract_occurrence_inventory_source(source)

    assert "RequiredBoundingBoxJsonForOccurrence" in occurrence_source
    assert "bbox_unavailable_zero_fallback" in occurrence_source
    assert 'segment["local_bbox"] = RequiredBoundingBoxJsonForOccurrence' in occurrence_source
    assert 'segment["world_bbox"] = RequiredBoundingBoxJsonForOccurrence' in occurrence_source


def test_occurrence_inventory_sessions_are_not_retained_after_complete_page():
    source = DIRECTOR_HANDLER.read_text(encoding="utf-8")
    start_body = _extract_function(source, "nlohmann::json StartOccurrenceInventory")
    continue_body = _extract_function(source, "nlohmann::json ContinueOccurrenceInventory")

    assert "kMaxDirectorOccurrenceInventorySessions" in source
    assert 'firstPage.value("complete", false)' in start_body
    assert "RecordOccurrenceInventorySession(std::move(session))" in start_body
    assert "EraseOccurrenceInventorySession(request.inventorySessionId)" in continue_body


def test_occurrence_inventory_session_eviction_is_oldest_first():
    source = DIRECTOR_HANDLER.read_text(encoding="utf-8")
    occurrence_source = _extract_occurrence_inventory_source(source)
    start_body = _extract_function(source, "nlohmann::json StartOccurrenceInventory")
    continue_body = _extract_function(source, "nlohmann::json ContinueOccurrenceInventory")

    assert "std::deque<std::string> g_occurrenceInventorySessionOrder" in occurrence_source
    assert "bool EvictOldestOccurrenceInventorySession" in occurrence_source
    assert "void RecordOccurrenceInventorySession" in occurrence_source
    assert "EraseOccurrenceInventorySession(request.inventorySessionId)" in continue_body
    assert "RecordOccurrenceInventorySession(" in start_body
    assert "g_occurrenceInventorySessions.erase(g_occurrenceInventorySessions.begin())" not in occurrence_source
