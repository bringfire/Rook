from __future__ import annotations

import asyncio
import math
import os
import time
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from rook import artifacts
from rook.bridge import call_rhino

from .contracts import (
    FORMAT_STRIDES,
    MESH2SPLAT_MAX_GAUSSIANS,
    RequestValidationError,
    validate_request,
)
from .executable import (
    ExecutableResolution,
    Mesh2SplatExecutableError,
    resolve_mesh2splat_executable,
)
from .glb_writer import (
    CapturedMaterial as GlbCapturedMaterial,
    CapturedMesh,
    CapturedPayload,
    GlbBuildError,
    SourceExpectations,
    ValidationWarning,
    validate_glb_bytes,
    write_glb,
)
from .output_safety import (
    CAPTURE_GLB_NAME,
    CAPTURE_PLY_NAME,
    RunManifest,
    cleanup_manifest_files,
    create_manifest,
    create_run_directory,
    exclusive_write_bytes,
    update_manifest,
    validate_output_directory,
)
from .ply import check_estimated_ply_guard, validate_ply
from .process import (
    Mesh2SplatProcessError,
    Mesh2SplatProcessResult,
    run_mesh2splat,
    sanitized_child_environment,
    validate_working_directory,
)
from .textures import (
    CapturedMaterial as TextureCapturedMaterial,
    TextureError,
    normalize_material_texture,
)


DEFAULT_TIMEOUT_SECONDS = 300
LONG_TIMEOUT_SECONDS = 900
STDERR_TAIL_BYTES = 8192


@dataclass(frozen=True)
class PipelineDeps:
    env: Mapping[str, str]
    now: Callable[[], datetime]
    new_run_id: Callable[[], str]
    resolve_executable: Callable[..., ExecutableResolution]
    call_native_capture: Callable[..., Any]
    create_run_directory: Callable[..., Any]
    create_manifest: Callable[[RunManifest], None]
    update_manifest: Callable[[RunManifest], None]
    write_glb: Callable[..., Any]
    validate_glb_bytes: Callable[..., list[ValidationWarning]]
    run_mesh2splat: Callable[..., Mesh2SplatProcessResult]
    register_artifact: Callable[..., dict[str, object]]


def _default_deps() -> PipelineDeps:
    return PipelineDeps(
        env=os.environ,
        now=lambda: datetime.now(timezone.utc),
        new_run_id=lambda: uuid.uuid4().hex,
        resolve_executable=resolve_mesh2splat_executable,
        call_native_capture=call_rhino,
        create_run_directory=create_run_directory,
        create_manifest=create_manifest,
        update_manifest=update_manifest,
        write_glb=write_glb,
        validate_glb_bytes=validate_glb_bytes,
        run_mesh2splat=run_mesh2splat,
        register_artifact=_register_mesh2splat_artifact,
    )


async def export_mesh2splat_capture(
    raw_request: dict[str, object],
    *,
    deps: PipelineDeps | Any | None = None,
) -> dict[str, object]:
    deps = deps or _default_deps()
    manifest: RunManifest | None = None
    warnings: list[dict[str, object]] = []

    try:
        request = validate_request(raw_request, default_sampling_resolution=128)
        executable = deps.resolve_executable(
            request.mesh2splat_path,
            env=deps.env if hasattr(deps, "env") else os.environ,
        )
        cwd = validate_working_directory(
            request.mesh2splat_working_directory,
            Path(executable.path),
        )
        try:
            output_directory = validate_output_directory(request.output_directory)
        except (OSError, RuntimeError, ValueError) as exc:
            return _err("invalid_output_directory", str(exc))

        capture_request = _native_capture_request(request)
        native_result = await deps.call_native_capture(
            "/mesh2splat/capture",
            "POST",
            capture_request,
        )
        capture_data, native_error = _capture_data_or_error(native_result)
        if native_error is not None:
            return native_error

        warnings.extend(_warnings_from(capture_data.get("warnings")))

        run_id = deps.new_run_id() if hasattr(deps, "new_run_id") else uuid.uuid4().hex
        try:
            paths = deps.create_run_directory(
                output_directory,
                now=deps.now() if hasattr(deps, "now") else datetime.now(timezone.utc),
                run_id=run_id,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return _err("invalid_output_directory", str(exc))
        manifest = RunManifest(
            run_id=run_id,
            run_directory=paths.run_directory,
            manifest_path=paths.manifest,
            artifact_paths=(),
            status="created",
            warnings=tuple(warnings),
            selected_executable=_manifest_executable_payload(executable),
            output_names={
                "glb": paths.capture_glb.name,
                "ply": paths.capture_ply.name,
            },
        )
        deps.create_manifest(manifest)

        capture_payload, texture_warnings, texture_counts = _captured_payload(
            capture_data,
            allow_network_textures=request.allow_network_textures,
        )
        warnings.extend(texture_warnings)

        glb_result = deps.write_glb(
            capture_payload,
            units_mode=request.units_mode,
            allow_dummy_scalar_uv=False,
        )
        exclusive_write_bytes(paths.capture_glb, glb_result.glb)
        manifest = replace(
            manifest,
            artifact_paths=(paths.capture_glb,),
            status="glb_written",
        )
        deps.update_manifest(manifest)
        warnings.extend(_warnings_from(glb_result.warnings))

        glb_validation_warnings = deps.validate_glb_bytes(
            glb_result.glb,
            source_expectations=SourceExpectations(
                expected_primitive_instance_count=glb_result.primitive_instance_count,
                expected_textured_material_count=texture_counts["textured"],
                expected_scalar_material_count=texture_counts["scalar"],
            ),
        )
        if glb_validation_warnings:
            warnings.extend(_warnings_from(glb_validation_warnings))
            return _fail_after_manifest(
                "glb_validation_failed",
                "GLB validation reported blocking warnings",
                manifest,
                request.preserve_debug_artifacts,
                warnings=warnings,
                cleanup_artifact_paths=(paths.capture_glb,),
            )

        glb_artifact, glb_registration_warning = _try_register_artifact(
            deps,
            paths.capture_glb,
            label="mesh2splat capture GLB",
            document_name=_optional_str(capture_data.get("documentName")),
            origin_session_id=_optional_str(capture_data.get("originSessionId")),
        )
        if glb_registration_warning is not None:
            warnings.append(glb_registration_warning)

        estimate = check_estimated_ply_guard(
            sampling_resolution=request.sampling_resolution,
            mesh2splat_loaded_mesh_count=int(glb_result.primitive_instance_count),
            fmt=request.format,
            max_estimated_ply_bytes_guard=(
                1024 * 1024 + MESH2SPLAT_MAX_GAUSSIANS * FORMAT_STRIDES[request.format]
            ),
        )
        if not estimate.ok:
            return _fail_after_manifest(
                "estimated_ply_too_large",
                "Estimated PLY output exceeds the configured guard",
                manifest,
                request.preserve_debug_artifacts,
                warnings=warnings,
                extra={"estimate": _estimate_payload(estimate)},
            )

        child_env = sanitized_child_environment(
            source_requires_path=bool(executable.source_requires_path),
            parent_env=deps.env if hasattr(deps, "env") else os.environ,
        )
        argv = _mesh2splat_argv(
            executable.path,
            paths.capture_glb,
            paths.capture_ply,
            fmt=request.format,
            sampling_resolution=request.sampling_resolution,
        )
        process_result = await asyncio.to_thread(
            deps.run_mesh2splat,
            argv,
            cwd=cwd,
            env=child_env,
            timeout_seconds=_timeout_seconds(request),
        )
        if not process_result.success:
            if paths.capture_ply.exists():
                manifest = replace(
                    manifest,
                    artifact_paths=(*manifest.artifact_paths, paths.capture_ply),
                    status="mesh2splat_failed",
                )
                deps.update_manifest(manifest)
            return _fail_after_manifest(
                process_result.error_code or "mesh2splat_failed",
                "Mesh2Splat conversion failed",
                manifest,
                request.preserve_debug_artifacts,
                warnings=warnings,
                cleanup_artifact_paths=(paths.capture_ply,),
                extra={"cli": _cli_payload(process_result, executable, argv, cwd)},
            )

        stdout_error = _validate_success_stdout(process_result.parsed_stdout, request)
        if stdout_error is not None:
            if paths.capture_ply.exists():
                manifest = replace(
                    manifest,
                    artifact_paths=(*manifest.artifact_paths, paths.capture_ply),
                    status="mesh2splat_stdout_invalid",
                )
                deps.update_manifest(manifest)
            return _fail_after_manifest(
                "mesh2splat_stdout_invalid",
                stdout_error,
                manifest,
                request.preserve_debug_artifacts,
                warnings=warnings,
                cleanup_artifact_paths=(paths.capture_ply,),
                extra={"cli": _cli_payload(process_result, executable, argv, cwd)},
            )

        gaussian_count = _gaussian_count(process_result.parsed_stdout)
        ply_validation = validate_ply(
            paths.capture_ply,
            fmt=request.format,
            gaussian_count=gaussian_count,
        )
        manifest = replace(
            manifest,
            artifact_paths=(*manifest.artifact_paths, paths.capture_ply),
            status="ply_written",
        )
        deps.update_manifest(manifest)
        if not ply_validation.ok:
            return _fail_after_manifest(
                "ply_validation_failed",
                "PLY validation failed",
                manifest,
                request.preserve_debug_artifacts,
                warnings=warnings,
                cleanup_artifact_paths=(paths.capture_ply,),
                extra={"plyValidation": _ply_validation_payload(ply_validation)},
            )

        ply_artifact, ply_registration_warning = _try_register_artifact(
            deps,
            paths.capture_ply,
            label="mesh2splat capture PLY",
            document_name=_optional_str(capture_data.get("documentName")),
            origin_session_id=_optional_str(capture_data.get("originSessionId")),
        )
        if ply_registration_warning is not None:
            warnings.append(ply_registration_warning)

        manifest = replace(
            manifest,
            status="complete",
            warnings=tuple(warnings),
        )
        deps.update_manifest(manifest)

        return {
            "success": True,
            "data": {
                "runDirectory": str(paths.run_directory),
                "manifest": str(paths.manifest),
                "outputs": {
                    "glb": _output_payload(paths.capture_glb, glb_artifact),
                    "ply": _output_payload(paths.capture_ply, ply_artifact),
                },
                "sourceUnits": {
                    "documentUnits": capture_payload.document_units,
                    "unitScaleToMeters": capture_payload.unit_scale_to_meters,
                    "unitsMode": request.units_mode,
                },
                "counts": _counts_payload(capture_data, gaussian_count),
                "estimate": _estimate_payload(estimate),
                "actualBytes": {
                    "glb": paths.capture_glb.stat().st_size,
                    "ply": ply_validation.actual_ply_bytes,
                },
                "warnings": warnings,
                "cli": _cli_payload(process_result, executable, argv, cwd),
                "plyValidation": _ply_validation_payload(ply_validation),
            },
        }
    except (RequestValidationError, Mesh2SplatExecutableError, Mesh2SplatProcessError) as exc:
        return exc.envelope
    except GlbBuildError as exc:
        if manifest is not None:
            return _fail_after_manifest(
                exc.code,
                str(exc),
                manifest,
                _preserve_debug(raw_request),
                warnings=warnings,
            )
        return _err(exc.code, str(exc))
    except TextureError as exc:
        if manifest is not None:
            return _fail_after_manifest(
                exc.code,
                str(exc),
                manifest,
                _preserve_debug(raw_request),
                warnings=warnings,
            )
        return _err(exc.code, str(exc))
    except Exception as exc:
        if manifest is not None:
            return _fail_after_manifest(
                "mesh2splat_pipeline_failed",
                str(exc),
                manifest,
                _preserve_debug(raw_request),
                warnings=warnings,
            )
        return _err("mesh2splat_pipeline_failed", str(exc))


def _native_capture_request(request: Any) -> dict[str, object]:
    payload: dict[str, object] = {
        "outputDirectory": request.output_directory,
        "format": request.format,
        "samplingResolution": request.sampling_resolution,
        "unitsMode": request.units_mode,
        "allowNetworkTextures": request.allow_network_textures,
        "allowPartial": request.allow_partial,
    }
    if request.object_ids is not None:
        payload["object_ids"] = list(request.object_ids)
    return payload


def _capture_data_or_error(result: object) -> tuple[dict[str, object], dict[str, object] | None]:
    if isinstance(result, dict) and result.get("success") is False:
        return {}, result
    if isinstance(result, dict) and result.get("success") is True:
        data = result.get("data")
        if isinstance(data, dict):
            return data, None
    if isinstance(result, dict):
        return result, None
    return {}, _err("native_capture_failed", "Native capture returned an invalid response")


def _captured_payload(
    capture: dict[str, object],
    *,
    allow_network_textures: bool,
) -> tuple[CapturedPayload, list[dict[str, object]], dict[str, int]]:
    materials, warnings, material_index_map = _captured_materials(
        capture.get("materials"),
        allow_network_textures=allow_network_textures,
    )
    meshes = _captured_meshes(
        capture.get("objects"),
        len(materials),
        material_index_map=material_index_map,
    )
    payload = CapturedPayload(
        meshes=tuple(meshes),
        materials=tuple(materials),
        document_units=_optional_str(capture.get("documentUnits")) or "Unknown",
        unit_scale_to_meters=float(capture.get("unitScaleToMeters") or 1.0),
    )
    return (
        payload,
        warnings,
        _texture_expectation_counts(payload),
    )


def _captured_materials(
    raw_materials: object,
    *,
    allow_network_textures: bool,
) -> tuple[list[GlbCapturedMaterial], list[dict[str, object]], dict[int, int]]:
    if not isinstance(raw_materials, list):
        raw_materials = []
    materials: list[GlbCapturedMaterial] = []
    warnings: list[dict[str, object]] = []
    material_index_map: dict[int, int] = {}
    for index, raw in enumerate(raw_materials):
        if not isinstance(raw, dict):
            continue
        compact_index = len(materials)
        source_index = _optional_int(raw.get("index"))
        if source_index is not None:
            material_index_map[source_index] = compact_index
        texture_material = TextureCapturedMaterial(
            name=_optional_str(raw.get("name")) or f"material-{index}",
            base_color_texture=_base_color_texture(raw.get("textures")),
            base_color_factor=_rgba(raw.get("baseColor")),
        )
        normalized = normalize_material_texture(
            texture_material,
            allow_network_textures=allow_network_textures,
        )
        warnings.extend(_warnings_from(normalized.warnings))
        embedded_png = normalized.base_color_texture
        materials.append(
            GlbCapturedMaterial(
                name=texture_material.name,
                base_color_factor=normalized.base_color_factor,
                embedded_png=embedded_png,
            )
        )
    if not materials:
        materials.append(
            GlbCapturedMaterial(
                name="Default",
                base_color_factor=(1.0, 1.0, 1.0, 1.0),
                embedded_png=None,
            )
        )
    return materials, warnings, material_index_map


def _base_color_texture(raw_textures: object) -> str | None:
    if not isinstance(raw_textures, list):
        return None
    for texture in raw_textures:
        if not isinstance(texture, dict):
            continue
        if texture.get("enabled") is not True:
            continue
        if texture.get("mappingChannel") not in (1, None):
            continue
        type_name = _optional_str(texture.get("typeName")) or ""
        if "bitmap" not in type_name.lower():
            continue
        full_path = _optional_str(texture.get("fullPath"))
        if full_path:
            return full_path
    return None


def _captured_meshes(
    raw_objects: object,
    material_count: int,
    *,
    material_index_map: dict[int, int],
) -> list[CapturedMesh]:
    if not isinstance(raw_objects, list):
        return []
    meshes: list[CapturedMesh] = []
    for index, raw in enumerate(raw_objects):
        if not isinstance(raw, dict):
            continue
        faces = tuple(_index_triplet(face) for face in _list(raw.get("faces")))
        source_material_index = _optional_int(raw.get("materialIndex")) or 0
        material_index = material_index_map.get(source_material_index, source_material_index)
        if material_index < 0 or material_index >= material_count:
            material_index = 0
        meshes.append(
            CapturedMesh(
                name=_optional_str(raw.get("name")) or f"object-{index}",
                positions=tuple(_float_triplet(item) for item in _list(raw.get("vertices"))),
                faces=faces,
                normals=tuple(_float_triplet(item) for item in _list(raw.get("normals")))
                if isinstance(raw.get("normals"), list)
                else None,
                uvs=tuple(_float_pair(item) for item in _list(raw.get("uvs")))
                if isinstance(raw.get("uvs"), list)
                else None,
                material_indices=tuple(material_index for _ in faces),
            )
        )
    return meshes


def _texture_expectation_counts(capture: CapturedPayload) -> dict[str, int]:
    counts = {"textured": 0, "scalar": 0}
    for material_index, material in enumerate(capture.materials):
        if material.embedded_png is None:
            counts["scalar"] += 1
            continue

        has_valid_uvs = _capture_material_has_valid_uvs(capture, material_index)
        if has_valid_uvs:
            counts["textured"] += 1
        else:
            counts["scalar"] += 1
    return counts


def _material_use_has_valid_uvs(mesh: CapturedMesh, material_index: int) -> bool:
    saw_material = False
    for face_index, face in enumerate(mesh.faces):
        if not mesh.material_indices or mesh.material_indices[face_index] != material_index:
            continue
        saw_material = True
        if not all(
            _valid_corner_uv(mesh, face_index, corner_index, position_index)
            for corner_index, position_index in enumerate(face)
        ):
            return False
    return saw_material


def _capture_material_has_valid_uvs(capture: CapturedPayload, material_index: int) -> bool:
    saw_material = False
    for mesh in capture.meshes:
        if material_index not in mesh.material_indices:
            continue
        saw_material = True
        if not _material_use_has_valid_uvs(mesh, material_index):
            return False
    return saw_material


def _valid_corner_uv(
    mesh: CapturedMesh,
    face_index: int,
    corner_index: int,
    position_index: int,
) -> bool:
    uvs = mesh.uvs
    if uvs is None:
        return False
    uv: tuple[float, float] | None = None
    if len(uvs) == len(mesh.faces) * 3:
        uv = uvs[(face_index * 3) + corner_index]
    elif position_index < len(uvs):
        uv = uvs[position_index]
    if uv is None or len(uv) != 2:
        return False
    return all(isinstance(component, (int, float)) and math.isfinite(component) for component in uv)


def _mesh2splat_argv(
    executable_path: Path | str,
    glb_path: Path,
    ply_path: Path,
    *,
    fmt: str,
    sampling_resolution: int,
) -> list[str]:
    return [
        str(executable_path),
        "--input",
        str(glb_path),
        "--output",
        str(ply_path),
        "--format",
        fmt,
        "--sampling-resolution",
        str(sampling_resolution),
    ]


def _timeout_seconds(request: Any) -> int:
    if request.mesh2splat_timeout_seconds is not None:
        return request.mesh2splat_timeout_seconds
    if request.format == "standard" or request.sampling_resolution > 512:
        return LONG_TIMEOUT_SECONDS
    return DEFAULT_TIMEOUT_SECONDS


def _validate_success_stdout(
    parsed_stdout: dict[str, object] | None,
    request: Any,
) -> str | None:
    if not isinstance(parsed_stdout, dict):
        return "Mesh2Splat stdout must include a parseable JSON object"
    if parsed_stdout.get("ok") is not True:
        return "Mesh2Splat stdout JSON must include ok=true"

    required = ("format", "samplingResolution", "effectiveResolution", "gaussianCount", "durationMs")
    missing = [key for key in required if key not in parsed_stdout]
    if missing:
        return "Mesh2Splat stdout JSON missing required field(s): " + ", ".join(missing)

    if parsed_stdout.get("format") != request.format:
        return "Mesh2Splat stdout JSON format does not match requested format"
    if parsed_stdout.get("samplingResolution") != request.sampling_resolution:
        return "Mesh2Splat stdout JSON samplingResolution does not match request"

    effective_resolution = parsed_stdout.get("effectiveResolution")
    gaussian_count = parsed_stdout.get("gaussianCount")
    duration_ms = parsed_stdout.get("durationMs")
    if not isinstance(effective_resolution, int) or isinstance(effective_resolution, bool) or effective_resolution <= 0:
        return "Mesh2Splat stdout JSON effectiveResolution must be a positive integer"
    if not isinstance(gaussian_count, int) or isinstance(gaussian_count, bool) or gaussian_count < 0:
        return "Mesh2Splat stdout JSON gaussianCount must be a non-negative integer"
    if (
        not isinstance(duration_ms, (int, float))
        or isinstance(duration_ms, bool)
        or duration_ms < 0
    ):
        return "Mesh2Splat stdout JSON durationMs must be a non-negative number"
    return None


def _register_mesh2splat_artifact(
    path: Path,
    *,
    label: str,
    document_name: str | None,
    origin_session_id: str | None,
) -> dict[str, object]:
    norm = artifacts.normalize_path(str(path))
    state, size, mtime = artifacts.stat_file_state(norm)
    if state != "present":
        raise RuntimeError(f"artifact file is {state}")
    registry = artifacts.artifact_registry()
    unsupported = getattr(registry, "schema_unsupported", None)
    if unsupported is not None:
        raise RuntimeError(f"artifact registry schema is unsupported: {unsupported!r}")
    result = registry.upsert(
        norm,
        source="mesh2splat_capture",
        file_state=state,
        size=size,
        mtime=mtime,
        document_name=document_name,
        origin_session_id=origin_session_id,
        label=label,
        now=int(time.time()),
    )
    if result == "id_collision":
        raise RuntimeError("artifact id collision")
    row = registry.get(path=norm)
    if row is None:
        raise RuntimeError("artifact registration did not create a row")
    return artifacts._project(row)


def _try_register_artifact(
    deps: PipelineDeps | Any,
    path: Path,
    *,
    label: str,
    document_name: str | None,
    origin_session_id: str | None,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    try:
        return (
            deps.register_artifact(
                path,
                label=label,
                document_name=document_name,
                origin_session_id=origin_session_id,
            ),
            None,
        )
    except Exception as exc:
        return None, _register_artifact_warning(exc, label, path)


def _register_artifact_warning(exc: Exception, label: str, path: Path) -> dict[str, object]:
    return {
        "code": "artifact_registration_failed",
        "message": f"{label} registration failed: {exc}",
        "path": str(path),
    }


def _manifest_executable_payload(executable: ExecutableResolution) -> dict[str, object]:
    return {
        "path": str(executable.path),
        "source": executable.source,
    }


def _fail_after_manifest(
    code: str,
    message: str,
    manifest: RunManifest,
    preserve_debug_artifacts: bool,
    *,
    warnings: list[dict[str, object]],
    cleanup_artifact_paths: tuple[Path, ...] | None = None,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    failed_manifest = replace(
        manifest,
        status=f"failed:{code}",
        warnings=tuple(warnings),
    )
    cleanup_result = cleanup_manifest_files(
        failed_manifest,
        preserve_debug_artifacts=preserve_debug_artifacts,
        preserve_manifest=True,
        delete_artifact_paths=cleanup_artifact_paths or (),
    )
    combined_warnings = [*warnings, *cleanup_result.warnings]
    cleanup_payload = {
        "preserveDebugArtifacts": preserve_debug_artifacts,
        "deleted": cleanup_result.deleted,
        "warnings": cleanup_result.warnings,
    }
    manifest = replace(
        failed_manifest,
        warnings=tuple(combined_warnings),
        cleanup=cleanup_payload,
    )
    update_manifest(manifest)

    payload: dict[str, object] = {
        "code": code,
        "message": message,
        "retryable": code == "mesh2splat_timeout",
        "runDirectory": str(manifest.run_directory),
        "warnings": combined_warnings,
        "cleanup": cleanup_payload,
    }
    if extra:
        payload.update(extra)
    return {"success": False, "data": payload}


def _err(code: str, message: str, **extra: object) -> dict[str, object]:
    return {
        "success": False,
        "data": {
            "code": code,
            "message": message,
            "retryable": False,
            **extra,
        },
    }


def _warnings_from(raw_warnings: object) -> list[dict[str, object]]:
    if raw_warnings is None:
        return []
    warnings: list[dict[str, object]] = []
    if not isinstance(raw_warnings, (list, tuple)):
        raw_warnings = [raw_warnings]
    for warning in raw_warnings:
        code = getattr(warning, "code", None)
        message = getattr(warning, "message", None)
        if isinstance(warning, dict):
            code = warning.get("code", code)
            message = warning.get("message", message)
        warnings.append(
            {
                "code": str(code or "warning"),
                "message": str(message or warning),
            }
        )
    return warnings


def _gaussian_count(parsed_stdout: dict[str, object] | None) -> int:
    if not parsed_stdout:
        return 0
    for key in ("gaussianCount", "gaussian_count", "count"):
        value = parsed_stdout.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return 0


def _counts_payload(capture_data: dict[str, object], gaussian_count: int) -> dict[str, object]:
    keys = (
        "objectCount",
        "sourceObjectCount",
        "requestedObjectCount",
        "sourceVertexCount",
        "sourceTriangleCount",
        "materialCount",
        "estimatedJsonBytes",
    )
    counts = {key: capture_data.get(key) for key in keys if key in capture_data}
    counts["gaussianCount"] = gaussian_count
    return counts


def _estimate_payload(estimate: Any) -> dict[str, object]:
    return {
        "ok": estimate.ok,
        "estimatedPlyBytes": estimate.estimated_ply_bytes,
        "estimateBasis": estimate.estimate_basis,
        "estimateConfidence": estimate.estimate_confidence,
        "stride": estimate.stride,
        "warnings": estimate.warnings,
        "errors": estimate.errors,
    }


def _ply_validation_payload(validation: Any) -> dict[str, object]:
    return {
        "ok": validation.ok,
        "actualPlyBytes": validation.actual_ply_bytes,
        "headerVertexCount": validation.header_vertex_count,
        "stride": validation.stride,
        "warnings": validation.warnings,
        "errors": validation.errors,
    }


def _cli_payload(
    result: Mesh2SplatProcessResult,
    executable: ExecutableResolution,
    argv: list[str],
    cwd: Path,
) -> dict[str, object]:
    return {
        "argv": argv,
        "cwd": str(cwd),
        "exitCode": result.returncode,
        "errorCode": result.error_code,
        "stdoutTail": _tail_text(result.stdout, STDERR_TAIL_BYTES),
        "stderrTail": _tail_text(result.stderr, STDERR_TAIL_BYTES),
        "stdoutTailBytes": STDERR_TAIL_BYTES,
        "stderrTailBytes": STDERR_TAIL_BYTES,
        "stdoutJson": result.parsed_stdout,
        "executablePath": str(executable.path),
        "executableSource": executable.source,
        "executableDiagnostics": executable.diagnostics,
        "diagnostics": result.diagnostics,
    }


def _tail_text(value: str, max_bytes: int) -> str:
    encoded = value.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return value
    return encoded[-max_bytes:].decode("utf-8", errors="replace")


def _output_payload(path: Path, artifact: dict[str, object] | None) -> dict[str, object]:
    return {
        "name": path.name,
        "path": str(path),
        "artifactId": artifact.get("artifactId") if artifact else None,
        "artifact": artifact,
    }


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _rgba(value: object) -> tuple[float, float, float, float] | None:
    if not isinstance(value, list | tuple) or len(value) != 4:
        return None
    return tuple(float(component) for component in value)  # type: ignore[return-value]


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _float_triplet(value: object) -> tuple[float, float, float]:
    items = value if isinstance(value, (list, tuple)) else (0.0, 0.0, 0.0)
    return (float(items[0]), float(items[1]), float(items[2]))


def _float_pair(value: object) -> tuple[float, float]:
    items = value if isinstance(value, (list, tuple)) else (0.0, 0.0)
    return (float(items[0]), float(items[1]))


def _index_triplet(value: object) -> tuple[int, int, int]:
    items = value if isinstance(value, (list, tuple)) else (0, 0, 0)
    return (int(items[0]), int(items[1]), int(items[2]))


def _preserve_debug(raw_request: dict[str, object]) -> bool:
    return raw_request.get("preserveDebugArtifacts") is True
