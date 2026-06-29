from __future__ import annotations

import json
import base64
import threading
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest


def _compressed_pbr_ply(gaussian_count: int) -> bytes:
    lines = [
        "ply",
        "format binary_little_endian 1.0",
        f"element vertex {gaussian_count}",
        "property float x",
        "property float y",
        "property float z",
        "property uchar red",
        "property uchar green",
        "property uchar blue",
        "property uchar opacity",
        "property float rot_0",
        "property float rot_1",
        "property float rot_2",
        "property float rot_3",
        "property float scale_0",
        "property float scale_1",
        "property float scale_2",
        "property uchar octa_nx",
        "property uchar octa_ny",
        "property uchar roughness",
        "property uchar metallic",
        "end_header",
    ]
    header = "\n".join(lines).encode("ascii") + b"\n"
    return header + (b"\0" * gaussian_count * 48)


def _tiny_png() -> bytes:
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGA"
        "WjR9awAAAABJRU5ErkJggg=="
    )


def _capture_payload(
    *,
    texture_path: str | None = None,
    material_index: int = 0,
    material_source_index: int | None = None,
    uv_valid: bool = True,
    uvs: list[list[float]] | None = None,
    faces: list[list[int]] | None = None,
) -> dict[str, object]:
    texture = {
        "typeName": "bitmap",
        "enabled": True,
        "mappingChannel": 1,
        "fullPath": texture_path,
        "relativePath": "paint.png" if texture_path else None,
    }
    return {
        "documentUnits": "Millimeters",
        "unitScaleToMeters": 0.001,
        "estimatedJsonBytes": 2048,
        "objectCount": 1,
        "sourceObjectCount": 1,
        "requestedObjectCount": 1,
        "sourceVertexCount": 3,
        "sourceTriangleCount": 1,
        "materialCount": 1,
        "caps": {"maxVertices": 10},
        "objects": [
            {
                "name": "Triangle",
                "vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                "normals": [[0, 0, 1], [0, 0, 1], [0, 0, 1]],
                "uvs": uvs if uvs is not None else ([[0, 0], [1, 0], [0, 1]] if uv_valid else []),
                "faces": faces or [[0, 1, 2]],
                "materialIndex": material_index,
                "triangleCount": 1,
                "uvValid": uv_valid,
            }
        ],
        "materials": [
            {
                "index": material_source_index if material_source_index is not None else material_index,
                "name": "Paint",
                "baseColor": [0.2, 0.4, 0.6, 1.0],
                "textures": [texture] if texture_path else [],
            }
        ],
        "warnings": [{"code": "native_warn", "message": "native warning"}],
        "documentName": "model.3dm",
        "originSessionId": "session-1",
    }


@dataclass
class FakeDeps:
    tmp_path: Path
    capture: dict[str, object] | None = None
    executable_error: Exception | None = None
    native_error: dict[str, object] | None = None
    glb_validation_warnings: tuple[object, ...] = ()
    process_success: bool = True
    process_error_code: str | None = None
    process_stdout_json: dict[str, object] | None = None
    process_stdout_text: str | None = None
    process_stderr_text: str = ""
    registration_failure: bool = False
    preserve_written_ply: bool = False

    def __post_init__(self) -> None:
        self.events: list[str] = []
        self.argv: list[str] | None = None
        self.run_directory: Path | None = None
        self.native_calls: list[dict[str, object]] = []
        self.registered: list[tuple[Path, str]] = []
        self.run_mesh2splat_thread_id: int | None = None
        self.timeout_seconds: int | None = None
        self.last_capture = None
        self.allow_dummy_scalar_uv: bool | None = None

    def resolve_executable(self, request_path, *, env):
        self.events.append("resolve_executable")
        if self.executable_error is not None:
            raise self.executable_error
        return SimpleNamespace(
            path=self.tmp_path / "Mesh2Splat.exe",
            source="fake",
            source_requires_path=True,
            diagnostics={"selected": {"source": "fake"}},
        )

    async def call_native_capture(self, route, method, payload):
        self.events.append("native_capture")
        self.native_calls.append(payload)
        assert route == "/mesh2splat/capture"
        assert method == "POST"
        output_directory = Path(payload["outputDirectory"])
        assert not output_directory.exists()
        if self.native_error is not None:
            return self.native_error
        return {"success": True, "data": self.capture or _capture_payload()}

    def create_run_directory(self, output_directory, *, now, run_id):
        from rook.mesh2splat.output_safety import create_run_directory

        self.events.append("create_run_directory")
        paths = create_run_directory(output_directory, now=now, run_id=run_id)
        self.run_directory = paths.run_directory
        return paths

    def create_manifest(self, manifest):
        from rook.mesh2splat.output_safety import create_manifest

        self.events.append("create_manifest")
        create_manifest(manifest)

    def update_manifest(self, manifest):
        from rook.mesh2splat.output_safety import update_manifest

        self.events.append(f"update_manifest:{manifest.status}")
        update_manifest(manifest)

    def write_glb(self, capture, *, units_mode, allow_dummy_scalar_uv):
        from rook.mesh2splat.glb_writer import GlbBuildError, GlbBuildResult, ValidationWarning

        self.events.append("write_glb")
        self.last_capture = capture
        self.allow_dummy_scalar_uv = allow_dummy_scalar_uv
        warnings = []
        for material_index, material in enumerate(capture.materials):
            material_has_invalid_uv = any(
                material_index in mesh.material_indices
                and not _mesh_material_has_valid_uvs(mesh, material_index)
                for mesh in capture.meshes
            )
            if material.embedded_png is None and material_has_invalid_uv and not allow_dummy_scalar_uv:
                raise GlbBuildError(
                    "scalar_material_requires_uv",
                    "scalar-only material requires valid UVs unless dummy UVs are allowed",
                )
            if material.embedded_png is None:
                continue
            if material_has_invalid_uv:
                warnings.append(
                    ValidationWarning(
                        "texture_invalid_uv_scalar_fallback",
                        "textured material fell back to scalar color because UVs were invalid",
                    )
                )
        return GlbBuildResult(
            glb=b"glTFfake",
            warnings=tuple(warnings),
            primitive_instance_count=len(capture.meshes),
        )

    def validate_glb_bytes(self, glb, *, source_expectations):
        from rook.mesh2splat.glb_writer import ValidationWarning

        self.events.append("validate_glb")
        warnings = list(self.glb_validation_warnings)
        if self.last_capture is not None:
            actual_textured = 0
            for material_index, material in enumerate(self.last_capture.materials):
                if material.embedded_png is None:
                    continue
                material_has_valid_uvs = _capture_material_has_valid_uvs(
                    self.last_capture,
                    material_index,
                )
                if material_has_valid_uvs:
                    actual_textured += 1
            if source_expectations.expected_textured_material_count != actual_textured:
                warnings.append(
                    ValidationWarning(
                        "textured_material_count_mismatch",
                        "textured material count does not match source expectation",
                    )
                )
        return warnings

    def run_mesh2splat(self, argv, *, cwd, env, timeout_seconds):
        from rook.mesh2splat.process import Mesh2SplatProcessResult

        self.events.append("run_mesh2splat")
        self.run_mesh2splat_thread_id = threading.get_ident()
        self.timeout_seconds = timeout_seconds
        self.argv = list(argv)
        if self.process_success or self.preserve_written_ply:
            Path(argv[4]).write_bytes(_compressed_pbr_ply(3))
        stdout_json = self.process_stdout_json
        if self.process_stdout_text is not None:
            stdout_text = self.process_stdout_text
        else:
            if stdout_json is None:
                sampling_resolution = int(argv[argv.index("--sampling-resolution") + 1])
                fmt = str(argv[argv.index("--format") + 1])
                stdout_json = {
                    "ok": self.process_success,
                    "format": fmt,
                    "samplingResolution": sampling_resolution,
                    "effectiveResolution": sampling_resolution,
                    "gaussianCount": 3,
                    "durationMs": 12,
                }
            stdout_text = json.dumps(stdout_json) + "\n"
        return Mesh2SplatProcessResult(
            success=self.process_success,
            returncode=0 if self.process_success else 1,
            stdout=stdout_text,
            stderr=self.process_stderr_text,
            parsed_stdout=stdout_json,
            error_code=self.process_error_code,
        )

    def register_artifact(self, path, *, label, document_name, origin_session_id):
        self.events.append(f"register:{label}")
        if self.registration_failure:
            raise RuntimeError("registry unavailable")
        artifact = {
            "artifactId": f"artifact-{Path(path).suffix[1:]}",
            "path": str(path),
            "label": label,
            "documentName": document_name,
            "originSessionId": origin_session_id,
            "sizeBytes": Path(path).stat().st_size,
        }
        self.registered.append((Path(path), label))
        return artifact


def _mesh_material_has_valid_uvs(mesh, material_index: int) -> bool:
    saw_material = False
    for face_index, face in enumerate(mesh.faces):
        if not mesh.material_indices or mesh.material_indices[face_index] != material_index:
            continue
        saw_material = True
        if not all(
            _mesh_corner_has_valid_uv(mesh, corner_index, position_index)
            for corner_index, position_index in enumerate(face)
        ):
            return False
    return saw_material


def _capture_material_has_valid_uvs(capture, material_index: int) -> bool:
    saw_material = False
    for mesh in capture.meshes:
        if material_index not in mesh.material_indices:
            continue
        saw_material = True
        if not _mesh_material_has_valid_uvs(mesh, material_index):
            return False
    return saw_material


def _mesh_corner_has_valid_uv(mesh, corner_index: int, position_index: int) -> bool:
    if mesh.uvs is None:
        return False
    if position_index >= len(mesh.uvs):
        return False
    uv = mesh.uvs[position_index]
    return len(uv) == 2


@pytest.mark.asyncio
async def test_happy_path_orchestrates_capture_conversion_registration_and_result(tmp_path):
    from rook.mesh2splat import pipeline

    deps = FakeDeps(tmp_path)
    output_directory = tmp_path / "exports"
    event_loop_thread_id = threading.get_ident()

    result = await pipeline.export_mesh2splat_capture(
        {
            "outputDirectory": str(output_directory),
            "format": "compressed-pbr",
            "samplingResolution": 256,
            "unitsMode": "raw",
            "object_ids": ["id-1"],
            "allowPartial": True,
        },
        deps=deps,
    )

    assert result["success"] is True
    assert deps.events[:3] == [
        "resolve_executable",
        "native_capture",
        "create_run_directory",
    ]
    assert deps.events.index("validate_glb") < deps.events.index("run_mesh2splat")
    assert deps.argv == [
        str(tmp_path / "Mesh2Splat.exe"),
        "--input",
        str(deps.run_directory / "capture.glb"),
        "--output",
        str(deps.run_directory / "capture.ply"),
        "--format",
        "compressed-pbr",
        "--sampling-resolution",
        "256",
    ]

    data = result["data"]
    assert Path(data["runDirectory"]).is_dir()
    assert data["outputs"]["glb"]["name"] == "capture.glb"
    assert data["outputs"]["ply"]["name"] == "capture.ply"
    assert data["outputs"]["glb"]["artifactId"] == "artifact-glb"
    assert data["outputs"]["ply"]["artifactId"] == "artifact-ply"
    assert "textureArtifactIds" not in data["outputs"]
    assert data["sourceUnits"] == {
        "documentUnits": "Millimeters",
        "unitScaleToMeters": 0.001,
        "unitsMode": "raw",
    }
    assert data["counts"]["sourceVertexCount"] == 3
    assert data["counts"]["sourceTriangleCount"] == 1
    assert data["counts"]["gaussianCount"] == 3
    assert data["estimate"]["estimatedPlyBytes"] > 0
    assert data["actualBytes"]["glb"] == len(b"glTFfake")
    assert data["actualBytes"]["ply"] == (deps.run_directory / "capture.ply").stat().st_size
    assert data["warnings"] == [{"code": "native_warn", "message": "native warning"}]
    assert data["cli"]["executableSource"] == "fake"
    assert data["cli"]["stdoutJson"]["gaussianCount"] == 3
    assert data["cli"]["stdoutJson"]["samplingResolution"] == 256
    assert deps.run_mesh2splat_thread_id != event_loop_thread_id
    assert json.loads((deps.run_directory / "manifest.json").read_text())["status"] == "complete"


@pytest.mark.asyncio
async def test_missing_executable_calls_no_native_capture_and_creates_no_files(tmp_path):
    from rook.mesh2splat import executable, pipeline

    output_directory = tmp_path / "exports"
    deps = FakeDeps(
        tmp_path,
        executable_error=executable.Mesh2SplatExecutableError(
            "mesh2splat_not_found",
            "missing",
        ),
    )

    result = await pipeline.export_mesh2splat_capture(
        {"outputDirectory": str(output_directory)},
        deps=deps,
    )

    assert result["success"] is False
    assert result["data"]["code"] == "mesh2splat_not_found"
    assert deps.native_calls == []
    assert not output_directory.exists()


@pytest.mark.asyncio
async def test_invalid_working_directory_calls_no_native_capture_and_creates_no_files(tmp_path):
    from rook.mesh2splat import pipeline

    output_directory = tmp_path / "exports"
    missing_working_directory = tmp_path / "missing-cwd"
    deps = FakeDeps(tmp_path)

    result = await pipeline.export_mesh2splat_capture(
        {
            "outputDirectory": str(output_directory),
            "mesh2splatWorkingDirectory": str(missing_working_directory),
        },
        deps=deps,
    )

    assert result["success"] is False
    assert result["data"]["code"] == "invalid_working_directory"
    assert deps.native_calls == []
    assert not output_directory.exists()


@pytest.mark.asyncio
async def test_output_directory_file_fails_as_invalid_output_directory_before_capture(tmp_path):
    from rook.mesh2splat import pipeline

    output_path = tmp_path / "not-a-directory"
    output_path.write_text("file")
    deps = FakeDeps(tmp_path)

    result = await pipeline.export_mesh2splat_capture(
        {"outputDirectory": str(output_path)},
        deps=deps,
    )

    assert result["success"] is False
    assert result["data"]["code"] == "invalid_output_directory"
    assert deps.native_calls == []
    assert output_path.is_file()


@pytest.mark.asyncio
async def test_native_failure_creates_no_output_directory_run_directory_or_manifest(tmp_path):
    from rook.mesh2splat import pipeline

    output_directory = tmp_path / "exports"
    deps = FakeDeps(
        tmp_path,
        native_error={
            "success": False,
            "data": {
                "code": "capture_failed",
                "message": "capture failed",
                "retryable": True,
            },
        },
    )

    result = await pipeline.export_mesh2splat_capture(
        {"outputDirectory": str(output_directory)},
        deps=deps,
    )

    assert result["success"] is False
    assert result["data"]["code"] == "capture_failed"
    assert not output_directory.exists()
    assert deps.run_directory is None


@pytest.mark.asyncio
async def test_glb_validation_failure_does_not_run_mesh2splat(tmp_path):
    from rook.mesh2splat import pipeline
    from rook.mesh2splat.glb_writer import ValidationWarning

    deps = FakeDeps(
        tmp_path,
        glb_validation_warnings=(
            ValidationWarning("glb_header_invalid", "GLB header is invalid"),
        ),
    )

    result = await pipeline.export_mesh2splat_capture(
        {"outputDirectory": str(tmp_path / "exports")},
        deps=deps,
    )

    assert result["success"] is False
    assert result["data"]["code"] == "glb_validation_failed"
    assert "run_mesh2splat" not in deps.events
    assert not (deps.run_directory / "capture.glb").exists()
    assert not (deps.run_directory / "capture.ply").exists()
    manifest = json.loads((deps.run_directory / "manifest.json").read_text())
    assert manifest["status"] == "failed:glb_validation_failed"


@pytest.mark.asyncio
async def test_timeout_cleanup_removes_only_manifest_listed_partial_ply(tmp_path):
    from rook.mesh2splat import pipeline

    deps = FakeDeps(
        tmp_path,
        process_success=False,
        process_error_code="mesh2splat_timeout",
        preserve_written_ply=True,
    )

    result = await pipeline.export_mesh2splat_capture(
        {"outputDirectory": str(tmp_path / "exports")},
        deps=deps,
    )

    assert result["success"] is False
    assert result["data"]["code"] == "mesh2splat_timeout"
    assert not (deps.run_directory / "capture.ply").exists()
    assert (deps.run_directory / "manifest.json").exists()
    assert (deps.run_directory / "capture.glb").exists()
    assert deps.run_directory.is_dir()
    manifest = json.loads((deps.run_directory / "manifest.json").read_text())
    assert manifest["status"] == "failed:mesh2splat_timeout"
    assert deps.registered == [
        (deps.run_directory / "capture.glb", "mesh2splat capture GLB"),
    ]
    assert deps.events.index("register:mesh2splat capture GLB") < deps.events.index("run_mesh2splat")


@pytest.mark.asyncio
async def test_cli_payload_uses_capped_tails_and_error_code_not_full_streams(tmp_path):
    from rook.mesh2splat import pipeline

    stdout = "o" * 9000 + "\n" + json.dumps({"ok": False, "errorCode": "GL_CONTEXT_INIT_FAILED"}) + "\n"
    stderr = "e" * 9000
    deps = FakeDeps(
        tmp_path,
        process_success=False,
        process_error_code="mesh2splat_gl_context_init_failed",
        process_stdout_json={"ok": False, "errorCode": "GL_CONTEXT_INIT_FAILED"},
        process_stdout_text=stdout,
        process_stderr_text=stderr,
    )

    result = await pipeline.export_mesh2splat_capture(
        {"outputDirectory": str(tmp_path / "exports")},
        deps=deps,
    )

    assert result["success"] is False
    assert result["data"]["code"] == "mesh2splat_gl_context_init_failed"
    cli = result["data"]["cli"]
    assert cli["errorCode"] == "mesh2splat_gl_context_init_failed"
    assert cli["exitCode"] == 1
    assert cli["stdoutTailBytes"] == 8192
    assert cli["stderrTailBytes"] == 8192
    assert cli["stdoutTail"] == stdout[-8192:]
    assert cli["stderrTail"] == stderr[-8192:]
    assert "stdout" not in cli
    assert "stderr" not in cli


@pytest.mark.asyncio
async def test_scalar_material_without_uvs_does_not_emit_dummy_uvs_without_smoke_proof(tmp_path):
    from rook.mesh2splat import pipeline

    deps = FakeDeps(
        tmp_path,
        capture=_capture_payload(uv_valid=False),
    )

    result = await pipeline.export_mesh2splat_capture(
        {"outputDirectory": str(tmp_path / "exports")},
        deps=deps,
    )

    assert result["success"] is False
    assert result["data"]["code"] == "scalar_material_requires_uv"
    assert deps.allow_dummy_scalar_uv is False
    assert "run_mesh2splat" not in deps.events


@pytest.mark.asyncio
async def test_invalid_mesh2splat_success_stdout_fails_before_ply_validation(tmp_path):
    from rook.mesh2splat import pipeline

    deps = FakeDeps(
        tmp_path,
        process_stdout_json={"ok": True, "gaussianCount": 3},
    )

    result = await pipeline.export_mesh2splat_capture(
        {"outputDirectory": str(tmp_path / "exports")},
        deps=deps,
    )

    assert result["success"] is False
    assert result["data"]["code"] == "mesh2splat_stdout_invalid"
    assert "samplingResolution" in result["data"]["message"]


@pytest.mark.asyncio
async def test_standard_format_uses_long_default_timeout(tmp_path):
    from rook.mesh2splat import pipeline

    deps = FakeDeps(
        tmp_path,
        process_stdout_json={
            "ok": True,
            "format": "standard",
            "samplingResolution": 128,
            "effectiveResolution": 128,
            "gaussianCount": 3,
            "durationMs": 12,
        },
    )

    result = await pipeline.export_mesh2splat_capture(
        {
            "outputDirectory": str(tmp_path / "exports"),
            "format": "standard",
            "allowLargeOutput": True,
        },
        deps=deps,
    )

    assert result["success"] is False
    assert result["data"]["code"] == "ply_validation_failed"
    assert deps.timeout_seconds == 900


@pytest.mark.asyncio
async def test_artifact_registration_failure_is_warning_not_hard_failure(tmp_path):
    from rook.mesh2splat import pipeline

    deps = FakeDeps(tmp_path, registration_failure=True)

    result = await pipeline.export_mesh2splat_capture(
        {"outputDirectory": str(tmp_path / "exports")},
        deps=deps,
    )

    assert result["success"] is True
    assert result["data"]["outputs"]["glb"]["artifactId"] is None
    assert result["data"]["outputs"]["ply"]["artifactId"] is None
    assert [warning["code"] for warning in result["data"]["warnings"]] == [
        "native_warn",
        "artifact_registration_failed",
        "artifact_registration_failed",
    ]


@pytest.mark.asyncio
async def test_embedded_textures_do_not_create_texture_artifact_ids(tmp_path):
    from rook.mesh2splat import pipeline

    texture = tmp_path / "paint.png"
    texture.write_bytes(b"not-used-by-fake-normalizer")
    deps = FakeDeps(tmp_path, capture=_capture_payload(texture_path=str(texture)))

    result = await pipeline.export_mesh2splat_capture(
        {"outputDirectory": str(tmp_path / "exports")},
        deps=deps,
    )

    assert result["success"] is True
    assert deps.registered == [
        (deps.run_directory / "capture.glb", "mesh2splat capture GLB"),
        (deps.run_directory / "capture.ply", "mesh2splat capture PLY"),
    ]
    assert "textureArtifactIds" not in result["data"]["outputs"]


@pytest.mark.asyncio
async def test_non_contiguous_native_material_indices_are_remapped(tmp_path):
    from rook.mesh2splat import pipeline

    capture = _capture_payload(material_index=42, material_source_index=7)
    capture["materials"].append(
        {
            "index": 42,
            "name": "Target Paint",
            "baseColor": [0.8, 0.2, 0.1, 1.0],
            "textures": [],
        }
    )
    deps = FakeDeps(tmp_path, capture=capture)

    result = await pipeline.export_mesh2splat_capture(
        {"outputDirectory": str(tmp_path / "exports")},
        deps=deps,
    )

    assert result["success"] is True
    assert [material.name for material in deps.last_capture.materials] == [
        "Paint",
        "Target Paint",
    ]
    assert deps.last_capture.meshes[0].material_indices == (1,)


@pytest.mark.asyncio
async def test_textured_material_with_invalid_uvs_falls_back_without_blocking(tmp_path):
    from rook.mesh2splat import pipeline

    texture = tmp_path / "paint.png"
    texture.write_bytes(_tiny_png())
    deps = FakeDeps(
        tmp_path,
        capture=_capture_payload(
            texture_path=str(texture),
            uv_valid=False,
        ),
    )

    result = await pipeline.export_mesh2splat_capture(
        {"outputDirectory": str(tmp_path / "exports")},
        deps=deps,
    )

    assert result["success"] is True
    assert any(
        warning["code"] == "texture_invalid_uv_scalar_fallback"
        for warning in result["data"]["warnings"]
    )


@pytest.mark.asyncio
async def test_textured_material_with_incomplete_uvs_falls_back_without_blocking(tmp_path):
    from rook.mesh2splat import pipeline

    texture = tmp_path / "paint.png"
    texture.write_bytes(_tiny_png())
    deps = FakeDeps(
        tmp_path,
        capture=_capture_payload(
            texture_path=str(texture),
            uvs=[[0, 0]],
        ),
    )

    result = await pipeline.export_mesh2splat_capture(
        {"outputDirectory": str(tmp_path / "exports")},
        deps=deps,
    )

    assert result["success"] is True
    assert any(
        warning["code"] == "texture_invalid_uv_scalar_fallback"
        for warning in result["data"]["warnings"]
    )


@pytest.mark.asyncio
async def test_textured_material_with_mixed_face_uv_validity_falls_back_without_blocking(tmp_path):
    from rook.mesh2splat import pipeline

    texture = tmp_path / "paint.png"
    texture.write_bytes(_tiny_png())
    deps = FakeDeps(
        tmp_path,
        capture=_capture_payload(
            texture_path=str(texture),
            faces=[[0, 1, 2], [0, 2, 3]],
            uvs=[[0, 0], [1, 0], [0, 1]],
        ),
    )

    result = await pipeline.export_mesh2splat_capture(
        {"outputDirectory": str(tmp_path / "exports")},
        deps=deps,
    )

    assert result["success"] is True
    assert any(
        warning["code"] == "texture_invalid_uv_scalar_fallback"
        for warning in result["data"]["warnings"]
    )


@pytest.mark.asyncio
async def test_textured_material_with_mixed_mesh_uv_validity_falls_back_without_blocking(tmp_path):
    from rook.mesh2splat import pipeline

    texture = tmp_path / "paint.png"
    texture.write_bytes(_tiny_png())
    capture = _capture_payload(texture_path=str(texture))
    invalid_mesh = dict(capture["objects"][0])
    invalid_mesh["name"] = "Triangle Missing UVs"
    invalid_mesh["uvs"] = []
    capture["objects"].append(invalid_mesh)
    deps = FakeDeps(tmp_path, capture=capture)

    result = await pipeline.export_mesh2splat_capture(
        {"outputDirectory": str(tmp_path / "exports")},
        deps=deps,
    )

    assert result["success"] is True
    assert any(
        warning["code"] == "texture_invalid_uv_scalar_fallback"
        for warning in result["data"]["warnings"]
    )
