from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass, field
from typing import Iterable


FLOAT = 5126
UNSIGNED_SHORT = 5123
UNSIGNED_INT = 5125


@dataclass(frozen=True)
class CapturedMaterial:
    name: str
    base_color_factor: tuple[float, float, float, float] | None = None
    embedded_png: bytes | None = None


@dataclass(frozen=True)
class CapturedMesh:
    name: str
    positions: tuple[tuple[float, float, float], ...]
    faces: tuple[tuple[int, int, int], ...]
    normals: tuple[tuple[float, float, float] | None, ...] | None = None
    uvs: tuple[tuple[float, float] | None, ...] | None = None
    material_indices: tuple[int, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CapturedPayload:
    meshes: tuple[CapturedMesh, ...]
    materials: tuple[CapturedMaterial, ...]
    document_units: str
    unit_scale_to_meters: float


@dataclass(frozen=True)
class ValidationWarning:
    code: str
    message: str


@dataclass(frozen=True)
class GlbBuildResult:
    glb: bytes
    warnings: tuple[ValidationWarning, ...] = ()
    sidecar_paths: tuple[str, ...] = ()
    primitive_instance_count: int = 0


@dataclass(frozen=True)
class SourceExpectations:
    expected_primitive_instance_count: int | None = None
    expected_textured_material_count: int | None = None
    expected_scalar_material_count: int | None = None


class GlbBuildError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def write_glb(
    capture: CapturedPayload,
    *,
    units_mode: str,
    allow_dummy_scalar_uv: bool,
) -> GlbBuildResult:
    if units_mode not in {"meters", "raw"}:
        raise GlbBuildError("invalid_units_mode", "units_mode must be meters or raw")

    builder = _GlbBuilder()
    warnings: list[ValidationWarning] = []
    material_uses = _collect_material_uses(capture)
    material_defs, material_texture_state = _build_materials(
        capture.materials,
        material_uses,
        warnings,
    )

    gltf: dict[str, object] = {
        "asset": {"version": "2.0", "generator": "Rook mesh2splat GLB writer"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(capture.meshes)))}],
        "nodes": [],
        "meshes": [],
        "materials": material_defs,
        "buffers": [{"byteLength": 0}],
        "bufferViews": [],
        "accessors": [],
        "extras": {
            "unitsMode": units_mode,
            "sourceDocumentUnits": capture.document_units,
            "unitScaleToMeters": capture.unit_scale_to_meters,
            "upAxis": "Z",
            "mesh2splatLoadedMeshCount": 0,
        },
    }

    primitive_instance_count = 0
    for mesh_index, captured_mesh in enumerate(capture.meshes):
        gltf["nodes"].append({"name": captured_mesh.name, "mesh": mesh_index})
        primitives: list[dict[str, object]] = []
        for material_index, face_indices in _faces_by_material(captured_mesh):
            material = capture.materials[material_index]
            texture_state = material_texture_state[material_index]
            primitive = _build_primitive(
                captured_mesh,
                face_indices,
                material_index,
                material,
                texture_state,
                units_mode=units_mode,
                unit_scale_to_meters=capture.unit_scale_to_meters,
                allow_dummy_scalar_uv=allow_dummy_scalar_uv,
                gltf=gltf,
                builder=builder,
            )
            primitives.append(primitive)
            primitive_instance_count += 1
        gltf["meshes"].append({"name": captured_mesh.name, "primitives": primitives})

    gltf["extras"]["mesh2splatLoadedMeshCount"] = primitive_instance_count

    if builder.images:
        gltf["images"] = builder.images
        gltf["textures"] = builder.textures

    bin_chunk = bytes(builder.data)
    bin_chunk += b"\x00" * _padding_len(len(bin_chunk))
    gltf["buffers"][0]["byteLength"] = len(bin_chunk)
    json_chunk = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * _padding_len(len(json_chunk))

    total_length = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
    glb = (
        struct.pack("<4sII", b"glTF", 2, total_length)
        + struct.pack("<I4s", len(json_chunk), b"JSON")
        + json_chunk
        + struct.pack("<I4s", len(bin_chunk), b"BIN\x00")
        + bin_chunk
    )
    return GlbBuildResult(
        glb=glb,
        warnings=tuple(warnings),
        sidecar_paths=(),
        primitive_instance_count=primitive_instance_count,
    )


def validate_glb_bytes(
    glb: bytes,
    *,
    source_expectations: SourceExpectations,
) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    parsed = _parse_glb_for_validation(glb, warnings)
    if parsed is None:
        return warnings

    gltf, bin_chunk = parsed
    primitives = [
        primitive
        for mesh in gltf.get("meshes", [])
        for primitive in mesh.get("primitives", [])
    ]
    material_defs = gltf.get("materials", [])
    textured_count = 0
    scalar_count = 0
    for material in material_defs:
        pbr = material.get("pbrMetallicRoughness", {})
        if "baseColorTexture" in pbr:
            textured_count += 1
        if "baseColorFactor" in pbr:
            scalar_count += 1

    expected_primitives = source_expectations.expected_primitive_instance_count
    if expected_primitives is not None and expected_primitives != len(primitives):
        warnings.append(
            ValidationWarning(
                "primitive_instance_count_mismatch",
                "emitted primitive count does not match source expectation",
            )
        )

    expected_textured = source_expectations.expected_textured_material_count
    if expected_textured is not None and expected_textured != textured_count:
        warnings.append(
            ValidationWarning(
                "textured_material_count_mismatch",
                "textured material count does not match source expectation",
            )
        )

    expected_scalar = source_expectations.expected_scalar_material_count
    if expected_scalar is not None and expected_scalar != scalar_count:
        warnings.append(
            ValidationWarning(
                "scalar_material_count_mismatch",
                "scalar material count does not match source expectation",
            )
        )

    if len(gltf.get("buffers", [])) != 1:
        warnings.append(ValidationWarning("buffer_count_mismatch", "expected one buffer"))
    if not isinstance(bin_chunk, bytes):
        warnings.append(ValidationWarning("bin_chunk_missing", "expected one BIN chunk"))

    _validate_material_texture_references(gltf, warnings)

    for primitive in primitives:
        attributes = primitive.get("attributes", {})
        position_index = attributes.get("POSITION")
        if isinstance(position_index, int):
            _validate_position_accessor_range(gltf, bin_chunk, position_index, warnings)

    return warnings


class _GlbBuilder:
    def __init__(self):
        self.data = bytearray()
        self.images: list[dict[str, object]] = []
        self.textures: list[dict[str, object]] = []

    def append_buffer_view(
        self,
        gltf: dict[str, object],
        payload: bytes,
        *,
        target: int | None = None,
    ) -> int:
        self.data.extend(b"\x00" * _padding_len(len(self.data)))
        offset = len(self.data)
        self.data.extend(payload)
        view: dict[str, object] = {
            "buffer": 0,
            "byteOffset": offset,
            "byteLength": len(payload),
        }
        if target is not None:
            view["target"] = target
        gltf["bufferViews"].append(view)
        return len(gltf["bufferViews"]) - 1

    def append_accessor(
        self,
        gltf: dict[str, object],
        payload: bytes,
        *,
        component_type: int,
        accessor_type: str,
        count: int,
        target: int | None = None,
        min_value: list[float] | None = None,
        max_value: list[float] | None = None,
    ) -> int:
        view_index = self.append_buffer_view(gltf, payload, target=target)
        accessor: dict[str, object] = {
            "bufferView": view_index,
            "componentType": component_type,
            "count": count,
            "type": accessor_type,
        }
        if min_value is not None:
            accessor["min"] = min_value
        if max_value is not None:
            accessor["max"] = max_value
        gltf["accessors"].append(accessor)
        return len(gltf["accessors"]) - 1

    def append_png_image(self, gltf: dict[str, object], png: bytes) -> int:
        view_index = self.append_buffer_view(gltf, png)
        self.images.append({"bufferView": view_index, "mimeType": "image/png"})
        texture_index = len(self.textures)
        self.textures.append({"source": len(self.images) - 1})
        return texture_index


@dataclass(frozen=True)
class _TextureState:
    use_texture: bool
    color: tuple[float, float, float, float]
    scalar_from_invalid_texture_uv: bool = False


def _build_materials(
    materials: tuple[CapturedMaterial, ...],
    material_uses: dict[int, bool],
    warnings: list[ValidationWarning],
) -> tuple[list[dict[str, object]], dict[int, _TextureState]]:
    material_defs: list[dict[str, object]] = []
    states: dict[int, _TextureState] = {}
    for index, material in enumerate(materials):
        uses_valid_uv = material_uses.get(index)
        use_texture = material.embedded_png is not None and uses_valid_uv is True
        scalar_from_invalid_texture_uv = (
            material.embedded_png is not None and uses_valid_uv is False
        )
        color = material.base_color_factor
        if scalar_from_invalid_texture_uv:
            warnings.append(
                ValidationWarning(
                    "texture_invalid_uv_scalar_fallback",
                    "textured material fell back to scalar color because UVs were invalid",
                )
            )
        if not use_texture and color is None:
            color = (1.0, 1.0, 1.0, 1.0)
            warnings.append(
                ValidationWarning(
                    "material_scalar_color_defaulted",
                    "material had no scalar base color; defaulted to white",
                )
            )

        pbr: dict[str, object] = {
            "metallicFactor": 0,
            "roughnessFactor": 0.5,
        }
        if not use_texture:
            pbr["baseColorFactor"] = list(color or (1.0, 1.0, 1.0, 1.0))
        material_defs.append({"name": material.name, "pbrMetallicRoughness": pbr})
        states[index] = _TextureState(
            use_texture=use_texture,
            color=color or (1.0, 1.0, 1.0, 1.0),
            scalar_from_invalid_texture_uv=scalar_from_invalid_texture_uv,
        )
    return material_defs, states


def _collect_material_uses(capture: CapturedPayload) -> dict[int, bool]:
    uses: dict[int, bool] = {}
    for captured_mesh in capture.meshes:
        for face_index, face in enumerate(captured_mesh.faces):
            material_index = _material_index_for_face(captured_mesh, face_index)
            valid = all(
                _valid_uv(_corner_uv(captured_mesh, face_index, corner_index, position_index))
                for corner_index, position_index in enumerate(face)
            )
            uses[material_index] = uses.get(material_index, True) and valid
    return uses


def _faces_by_material(captured_mesh: CapturedMesh) -> list[tuple[int, list[int]]]:
    grouped: list[tuple[int, list[int]]] = []
    material_to_group: dict[int, list[int]] = {}
    for face_index in range(len(captured_mesh.faces)):
        material_index = _material_index_for_face(captured_mesh, face_index)
        if material_index not in material_to_group:
            material_to_group[material_index] = []
            grouped.append((material_index, material_to_group[material_index]))
        material_to_group[material_index].append(face_index)
    return grouped


def _build_primitive(
    captured_mesh: CapturedMesh,
    face_indices: list[int],
    material_index: int,
    material: CapturedMaterial,
    texture_state: _TextureState,
    *,
    units_mode: str,
    unit_scale_to_meters: float,
    allow_dummy_scalar_uv: bool,
    gltf: dict[str, object],
    builder: _GlbBuilder,
) -> dict[str, object]:
    scale = unit_scale_to_meters if units_mode == "meters" else 1.0
    use_dummy_uv = False
    if not texture_state.use_texture:
        has_invalid_uv = any(
            not _valid_uv(_corner_uv(captured_mesh, face_index, corner_index, position_index))
            for face_index in face_indices
            for corner_index, position_index in enumerate(captured_mesh.faces[face_index])
        )
        if has_invalid_uv:
            if texture_state.scalar_from_invalid_texture_uv:
                use_dummy_uv = True
            elif not allow_dummy_scalar_uv:
                raise GlbBuildError(
                    "scalar_material_requires_uv",
                    "scalar-only material requires valid UVs unless dummy UVs are allowed",
                )
            else:
                use_dummy_uv = True

    vertices: list[tuple[float, float, float]] = []
    normals: list[tuple[float, float, float]] = []
    uvs: list[tuple[float, float]] = []
    indices: list[int] = []
    vertex_map: dict[
        tuple[int, tuple[float, float, float], tuple[float, float], int],
        int,
    ] = {}

    for face_index in face_indices:
        face = captured_mesh.faces[face_index]
        face_normal = _face_normal(captured_mesh, face)
        for corner_index, position_index in enumerate(face):
            source_position = captured_mesh.positions[position_index]
            position = tuple(float(component) * scale for component in source_position)
            normal = _corner_normal(
                captured_mesh,
                face_index,
                corner_index,
                position_index,
            )
            if normal is None:
                normal = face_normal
            uv = (0.0, 0.0) if use_dummy_uv else _corner_uv(
                captured_mesh,
                face_index,
                corner_index,
                position_index,
            )
            if not _valid_uv(uv):
                uv = (0.0, 0.0)
            key = (
                position_index,
                tuple(float(component) for component in normal),
                tuple(float(component) for component in uv),
                material_index,
            )
            vertex_index = vertex_map.get(key)
            if vertex_index is None:
                vertex_index = len(vertices)
                vertex_map[key] = vertex_index
                vertices.append(position)
                normals.append(tuple(float(component) for component in normal))
                uvs.append(tuple(float(component) for component in uv))
            indices.append(vertex_index)

    position_accessor = builder.append_accessor(
        gltf,
        _pack_floats(vertices),
        component_type=FLOAT,
        accessor_type="VEC3",
        count=len(vertices),
        target=34962,
        min_value=_component_min(vertices),
        max_value=_component_max(vertices),
    )
    normal_accessor = builder.append_accessor(
        gltf,
        _pack_floats(normals),
        component_type=FLOAT,
        accessor_type="VEC3",
        count=len(normals),
        target=34962,
        min_value=_component_min(normals),
        max_value=_component_max(normals),
    )
    uv_accessor = builder.append_accessor(
        gltf,
        _pack_floats(uvs),
        component_type=FLOAT,
        accessor_type="VEC2",
        count=len(uvs),
        target=34962,
        min_value=_component_min(uvs),
        max_value=_component_max(uvs),
    )
    index_component_type = UNSIGNED_SHORT if len(vertices) < 65536 else UNSIGNED_INT
    index_accessor = builder.append_accessor(
        gltf,
        _pack_indices(indices, index_component_type),
        component_type=index_component_type,
        accessor_type="SCALAR",
        count=len(indices),
        target=34963,
        min_value=[min(indices)] if indices else [0],
        max_value=[max(indices)] if indices else [0],
    )

    if texture_state.use_texture:
        texture_index = builder.append_png_image(gltf, material.embedded_png or b"")
        gltf["materials"][material_index]["pbrMetallicRoughness"][
            "baseColorTexture"
        ] = {"index": texture_index}

    return {
        "attributes": {
            "POSITION": position_accessor,
            "NORMAL": normal_accessor,
            "TEXCOORD_0": uv_accessor,
        },
        "indices": index_accessor,
        "material": material_index,
        "mode": 4,
    }


def _material_index_for_face(captured_mesh: CapturedMesh, face_index: int) -> int:
    if not captured_mesh.material_indices:
        return 0
    return captured_mesh.material_indices[face_index]


def _corner_normal(
    captured_mesh: CapturedMesh,
    face_index: int,
    corner_index: int,
    position_index: int,
) -> tuple[float, float, float] | None:
    normals = captured_mesh.normals
    if normals is None:
        return None
    if len(normals) == len(captured_mesh.faces) * 3:
        return normals[(face_index * 3) + corner_index]
    if position_index < len(normals):
        return normals[position_index]
    return None


def _corner_uv(
    captured_mesh: CapturedMesh,
    face_index: int,
    corner_index: int,
    position_index: int,
) -> tuple[float, float] | None:
    uvs = captured_mesh.uvs
    if uvs is None:
        return None
    if len(uvs) == len(captured_mesh.faces) * 3:
        return uvs[(face_index * 3) + corner_index]
    if position_index < len(uvs):
        return uvs[position_index]
    return None


def _valid_uv(uv: tuple[float, float] | None) -> bool:
    if uv is None or len(uv) != 2:
        return False
    return all(isinstance(component, (int, float)) and math.isfinite(component) for component in uv)


def _face_normal(
    captured_mesh: CapturedMesh,
    face: tuple[int, int, int],
) -> tuple[float, float, float]:
    a, b, c = (captured_mesh.positions[index] for index in face)
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    cross = (
        (ab[1] * ac[2]) - (ab[2] * ac[1]),
        (ab[2] * ac[0]) - (ab[0] * ac[2]),
        (ab[0] * ac[1]) - (ab[1] * ac[0]),
    )
    length = math.sqrt(sum(component * component for component in cross))
    if length == 0:
        return (0.0, 0.0, 1.0)
    return tuple(component / length for component in cross)


def _component_min(values: list[tuple[float, ...]]) -> list[float]:
    return [min(value[index] for value in values) for index in range(len(values[0]))]


def _component_max(values: list[tuple[float, ...]]) -> list[float]:
    return [max(value[index] for value in values) for index in range(len(values[0]))]


def _pack_floats(values: Iterable[tuple[float, ...]]) -> bytes:
    flattened = [component for value in values for component in value]
    return struct.pack("<" + ("f" * len(flattened)), *flattened)


def _pack_indices(indices: list[int], component_type: int) -> bytes:
    format_code = "H" if component_type == UNSIGNED_SHORT else "I"
    return struct.pack("<" + (format_code * len(indices)), *indices)


def _padding_len(length: int) -> int:
    return (4 - (length % 4)) % 4


def _parse_glb_for_validation(
    glb: bytes,
    warnings: list[ValidationWarning],
) -> tuple[dict[str, object], bytes] | None:
    if len(glb) < 20:
        warnings.append(ValidationWarning("glb_too_short", "GLB is too short"))
        return None
    magic, version, length = struct.unpack_from("<4sII", glb, 0)
    if magic != b"glTF" or version != 2 or length != len(glb):
        warnings.append(ValidationWarning("glb_header_invalid", "GLB header is invalid"))
        return None

    offset = 12
    json_chunk: bytes | None = None
    bin_chunks: list[bytes] = []
    while offset + 8 <= len(glb):
        chunk_length, chunk_type = struct.unpack_from("<I4s", glb, offset)
        offset += 8
        chunk_data = glb[offset : offset + chunk_length]
        offset += chunk_length
        if chunk_type == b"JSON":
            json_chunk = chunk_data
        elif chunk_type == b"BIN\x00":
            bin_chunks.append(chunk_data)

    if json_chunk is None:
        warnings.append(ValidationWarning("json_chunk_missing", "missing JSON chunk"))
        return None
    if len(bin_chunks) != 1:
        warnings.append(ValidationWarning("bin_chunk_count_invalid", "expected one BIN chunk"))
        return None
    try:
        gltf = json.loads(json_chunk.rstrip(b" ").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        warnings.append(ValidationWarning("json_chunk_invalid", "JSON chunk is invalid"))
        return None
    return gltf, bin_chunks[0]


def _validate_material_texture_references(
    gltf: dict[str, object],
    warnings: list[ValidationWarning],
) -> None:
    materials = gltf.get("materials", [])
    textures = gltf.get("textures", [])
    images = gltf.get("images", [])
    buffer_views = gltf.get("bufferViews", [])

    if not isinstance(materials, list):
        return
    if not isinstance(textures, list):
        textures = []
    if not isinstance(images, list):
        images = []
    if not isinstance(buffer_views, list):
        buffer_views = []

    for material in materials:
        if not isinstance(material, dict):
            continue
        pbr = material.get("pbrMetallicRoughness", {})
        if not isinstance(pbr, dict):
            continue
        base_color_texture = pbr.get("baseColorTexture")
        if not isinstance(base_color_texture, dict):
            continue
        texture_index = base_color_texture.get("index")
        if (
            not isinstance(texture_index, int)
            or texture_index < 0
            or texture_index >= len(textures)
        ):
            warnings.append(
                ValidationWarning(
                    "material_texture_index_invalid",
                    "material baseColorTexture index is invalid",
                )
            )
            continue

        texture = textures[texture_index]
        if not isinstance(texture, dict):
            warnings.append(
                ValidationWarning(
                    "texture_source_index_invalid",
                    "texture source index is invalid",
                )
            )
            continue
        source_index = texture.get("source")
        if (
            not isinstance(source_index, int)
            or source_index < 0
            or source_index >= len(images)
        ):
            warnings.append(
                ValidationWarning(
                    "texture_source_index_invalid",
                    "texture source index is invalid",
                )
            )
            continue

        image = images[source_index]
        if not isinstance(image, dict):
            warnings.append(
                ValidationWarning(
                    "image_buffer_view_invalid",
                    "image bufferView index is invalid",
                )
            )
            continue
        view_index = image.get("bufferView")
        if (
            not isinstance(view_index, int)
            or view_index < 0
            or view_index >= len(buffer_views)
        ):
            warnings.append(
                ValidationWarning(
                    "image_buffer_view_invalid",
                    "image bufferView index is invalid",
                )
            )


def _validate_position_accessor_range(
    gltf: dict[str, object],
    bin_chunk: bytes,
    accessor_index: int,
    warnings: list[ValidationWarning],
) -> None:
    accessors = gltf.get("accessors", [])
    buffer_views = gltf.get("bufferViews", [])
    if accessor_index >= len(accessors):
        warnings.append(ValidationWarning("accessor_missing", "accessor index is invalid"))
        return
    accessor = accessors[accessor_index]
    if accessor.get("componentType") != FLOAT or accessor.get("type") != "VEC3":
        warnings.append(
            ValidationWarning("position_accessor_invalid", "POSITION accessor is not FLOAT VEC3")
        )
        return
    view_index = accessor.get("bufferView")
    if not isinstance(view_index, int) or view_index >= len(buffer_views):
        warnings.append(ValidationWarning("buffer_view_missing", "bufferView index is invalid"))
        return
    view = buffer_views[view_index]
    offset = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    count = int(accessor.get("count", 0))
    required = offset + (count * 12)
    if required > len(bin_chunk):
        warnings.append(
            ValidationWarning("accessor_out_of_bounds", "accessor extends beyond BIN chunk")
        )
        return
    values = [
        struct.unpack_from("<fff", bin_chunk, offset + (index * 12))
        for index in range(count)
    ]
    if not values:
        return
    actual_min = _component_min(values)
    actual_max = _component_max(values)
    expected_min = accessor.get("min")
    expected_max = accessor.get("max")
    if not _vectors_close(expected_min, actual_min) or not _vectors_close(
        expected_max,
        actual_max,
    ):
        warnings.append(
            ValidationWarning(
                "accessor_range_mismatch",
                "POSITION accessor min/max do not match binary data",
            )
        )


def _vectors_close(candidate: object, expected: list[float]) -> bool:
    if not isinstance(candidate, list) or len(candidate) != len(expected):
        return False
    return all(
        isinstance(left, (int, float)) and math.isclose(left, right, abs_tol=1e-6)
        for left, right in zip(candidate, expected)
    )
