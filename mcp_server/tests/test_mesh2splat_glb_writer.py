from __future__ import annotations

import json
import math
import struct

import pytest


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"rook-png"


def material(
    name: str = "paint",
    *,
    color: tuple[float, float, float, float] | None = (0.2, 0.4, 0.6, 1.0),
    png: bytes | None = None,
):
    from rook.mesh2splat.glb_writer import CapturedMaterial

    return CapturedMaterial(
        name=name,
        base_color_factor=color,
        embedded_png=png,
    )


def mesh(
    *,
    name: str = "mesh",
    positions=((0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 4.0, 0.0)),
    faces=((0, 1, 2),),
    normals=None,
    uvs=((0.0, 0.0), (1.0, 0.0), (0.0, 1.0)),
    material_indices=(0,),
):
    from rook.mesh2splat.glb_writer import CapturedMesh

    return CapturedMesh(
        name=name,
        positions=tuple(positions),
        faces=tuple(faces),
        normals=None if normals is None else tuple(normals),
        uvs=None if uvs is None else tuple(uvs),
        material_indices=tuple(material_indices),
    )


def payload(*, meshes=None, materials=None, units="Millimeters", scale=0.001):
    from rook.mesh2splat.glb_writer import CapturedPayload

    return CapturedPayload(
        meshes=tuple(meshes if meshes is not None else (mesh(),)),
        materials=tuple(materials if materials is not None else (material(),)),
        document_units=units,
        unit_scale_to_meters=scale,
    )


def parse_glb(glb: bytes):
    magic, version, length = struct.unpack_from("<4sII", glb, 0)
    assert magic == b"glTF"
    assert version == 2
    assert length == len(glb)

    offset = 12
    chunks: list[tuple[bytes, bytes, int]] = []
    while offset < len(glb):
        chunk_length, chunk_type = struct.unpack_from("<I4s", glb, offset)
        offset += 8
        data = glb[offset : offset + chunk_length]
        chunks.append((chunk_type, data, chunk_length))
        offset += chunk_length

    assert offset == len(glb)
    assert [chunk[0] for chunk in chunks] == [b"JSON", b"BIN\x00"]
    assert all(chunk_length % 4 == 0 for _, _, chunk_length in chunks)

    gltf = json.loads(chunks[0][1].rstrip(b" ").decode("utf-8"))
    assert chunks[0][1].endswith(b" ") or len(chunks[0][1]) % 4 == 0
    return gltf, chunks[1][1]


def rebuild_glb(gltf: dict, bin_chunk: bytes) -> bytes:
    json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_bytes += b" " * ((4 - (len(json_bytes) % 4)) % 4)
    return (
        struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(json_bytes) + 8 + len(bin_chunk))
        + struct.pack("<I4s", len(json_bytes), b"JSON")
        + json_bytes
        + struct.pack("<I4s", len(bin_chunk), b"BIN\x00")
        + bin_chunk
    )


def accessor_values(gltf: dict, bin_chunk: bytes, accessor_index: int):
    accessor = gltf["accessors"][accessor_index]
    view = gltf["bufferViews"][accessor["bufferView"]]
    offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    type_counts = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
    component_counts = type_counts[accessor["type"]]
    formats = {
        5126: "f",
        5123: "H",
        5125: "I",
    }
    fmt = "<" + (formats[accessor["componentType"]] * component_counts)
    stride = struct.calcsize(fmt)
    values = []
    for index in range(accessor["count"]):
        item = struct.unpack_from(fmt, bin_chunk, offset + (index * stride))
        values.append(item[0] if component_counts == 1 else item)
    return values


def primitive(gltf: dict, mesh_index: int = 0, primitive_index: int = 0):
    return gltf["meshes"][mesh_index]["primitives"][primitive_index]


def write(capture, *, units_mode="meters", allow_dummy_scalar_uv=True):
    from rook.mesh2splat.glb_writer import write_glb

    return write_glb(
        capture,
        units_mode=units_mode,
        allow_dummy_scalar_uv=allow_dummy_scalar_uv,
    )


def test_writes_strict_glb_header_chunks_scene_metadata_and_converted_positions():
    result = write(payload(scale=0.5), units_mode="meters")

    assert result.sidecar_paths == ()
    assert result.primitive_instance_count == 1

    gltf, bin_chunk = parse_glb(result.glb)
    extras = gltf["extras"]
    assert extras["unitsMode"] == "meters"
    assert extras["sourceDocumentUnits"] == "Millimeters"
    assert extras["unitScaleToMeters"] == 0.5
    assert extras["upAxis"] == "Z"
    assert extras["mesh2splatLoadedMeshCount"] == 1
    assert len(gltf["scenes"]) == 1
    assert gltf["scene"] == 0
    assert gltf["scenes"][0]["nodes"] == [0]
    assert gltf["nodes"][0]["mesh"] == 0

    prim = primitive(gltf)
    positions = accessor_values(gltf, bin_chunk, prim["attributes"]["POSITION"])
    assert positions == [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 2.0, 0.0)]
    position_accessor = gltf["accessors"][prim["attributes"]["POSITION"]]
    assert position_accessor["min"] == [0.0, 0.0, 0.0]
    assert position_accessor["max"] == [1.0, 2.0, 0.0]


def test_raw_units_preserve_source_position_numbers():
    result = write(payload(scale=0.5), units_mode="raw")

    gltf, bin_chunk = parse_glb(result.glb)
    positions = accessor_values(
        gltf,
        bin_chunk,
        primitive(gltf)["attributes"]["POSITION"],
    )

    assert gltf["extras"]["unitsMode"] == "raw"
    assert positions == [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 4.0, 0.0)]


def test_triangle_winding_is_preserved_and_missing_normals_are_generated():
    result = write(
        payload(meshes=(mesh(faces=((2, 1, 0),), normals=None),)),
        units_mode="raw",
    )

    gltf, bin_chunk = parse_glb(result.glb)
    prim = primitive(gltf)

    assert accessor_values(gltf, bin_chunk, prim["indices"]) == [0, 1, 2]
    assert accessor_values(gltf, bin_chunk, prim["attributes"]["POSITION"]) == [
        (0.0, 4.0, 0.0),
        (2.0, 0.0, 0.0),
        (0.0, 0.0, 0.0),
    ]
    normals = accessor_values(gltf, bin_chunk, prim["attributes"]["NORMAL"])
    assert normals == [(0.0, 0.0, -1.0)] * 3


def test_source_normals_are_used_when_provided():
    source_normals = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))

    result = write(payload(meshes=(mesh(normals=source_normals),)), units_mode="raw")

    gltf, bin_chunk = parse_glb(result.glb)
    normals = accessor_values(
        gltf,
        bin_chunk,
        primitive(gltf)["attributes"]["NORMAL"],
    )
    assert normals == list(source_normals)


def test_vertices_split_across_position_normal_uv_and_material_seams():
    seam_mesh = mesh(
        positions=((0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)),
        faces=((0, 1, 2), (0, 2, 3), (0, 3, 1)),
        normals=(
            (0, 0, 1),
            (0, 0, 1),
            (0, 0, 1),
            (0, 1, 0),
            (0, 0, 1),
            (0, 0, 1),
            (0, 0, 1),
            (0, 1, 0),
            (1, 0, 0),
        ),
        uvs=(
            (0, 0),
            (1, 0),
            (0, 1),
            (0.5, 0.5),
            (0.2, 0.8),
            (1, 1),
            (0.25, 0.25),
            (1, 1),
            (1, 0),
        ),
        material_indices=(0, 0, 1),
    )

    result = write(
        payload(
            meshes=(seam_mesh,),
            materials=(material("mat-a"), material("mat-b", color=(1, 0, 0, 1))),
        ),
        units_mode="raw",
    )

    gltf, bin_chunk = parse_glb(result.glb)
    primitives = gltf["meshes"][0]["primitives"]
    assert len(primitives) == 2
    assert result.primitive_instance_count == 2
    assert gltf["extras"]["mesh2splatLoadedMeshCount"] == 2

    counts = [
        gltf["accessors"][prim["attributes"]["POSITION"]]["count"]
        for prim in primitives
    ]
    assert counts == [6, 3]
    assert accessor_values(gltf, bin_chunk, primitives[0]["indices"]) == [
        0,
        1,
        2,
        3,
        4,
        5,
    ]
    assert accessor_values(gltf, bin_chunk, primitives[1]["indices"]) == [0, 1, 2]


def test_textured_material_with_invalid_uv_falls_back_to_scalar_color_warning():
    bad_uv_mesh = mesh(uvs=((0.0, 0.0), None, (1.0, 1.0)))

    result = write(
        payload(
            meshes=(bad_uv_mesh,),
            materials=(material(png=PNG_BYTES, color=(0.1, 0.2, 0.3, 1.0)),),
        ),
        units_mode="raw",
    )

    gltf, _ = parse_glb(result.glb)
    pbr = gltf["materials"][0]["pbrMetallicRoughness"]
    assert pbr["baseColorFactor"] == [0.1, 0.2, 0.3, 1.0]
    assert "baseColorTexture" not in pbr
    assert "images" not in gltf
    assert "textures" not in gltf
    assert [warning.code for warning in result.warnings] == [
        "texture_invalid_uv_scalar_fallback"
    ]


def test_textured_material_with_invalid_uv_falls_back_without_dummy_uv_opt_in():
    bad_uv_mesh = mesh(uvs=((0.0, 0.0), None, (1.0, 1.0)))

    result = write(
        payload(
            meshes=(bad_uv_mesh,),
            materials=(material(png=PNG_BYTES, color=(0.1, 0.2, 0.3, 1.0)),),
        ),
        units_mode="raw",
        allow_dummy_scalar_uv=False,
    )

    gltf, _ = parse_glb(result.glb)
    pbr = gltf["materials"][0]["pbrMetallicRoughness"]
    assert pbr["baseColorFactor"] == [0.1, 0.2, 0.3, 1.0]
    assert "baseColorTexture" not in pbr
    assert "images" not in gltf
    assert "textures" not in gltf
    assert [warning.code for warning in result.warnings] == [
        "texture_invalid_uv_scalar_fallback"
    ]


def test_textured_material_with_valid_uv_embeds_png_image_buffer_view():
    result = write(
        payload(materials=(material(png=PNG_BYTES, color=(0.1, 0.2, 0.3, 1.0)),)),
        units_mode="raw",
    )

    gltf, bin_chunk = parse_glb(result.glb)
    pbr = gltf["materials"][0]["pbrMetallicRoughness"]
    assert pbr["baseColorTexture"] == {"index": 0}
    assert "baseColorFactor" not in pbr
    assert gltf["textures"] == [{"source": 0}]
    assert gltf["images"][0]["mimeType"] == "image/png"
    view = gltf["bufferViews"][gltf["images"][0]["bufferView"]]
    png = bin_chunk[view["byteOffset"] : view["byteOffset"] + view["byteLength"]]
    assert png == PNG_BYTES
    assert result.sidecar_paths == ()


def test_unused_textured_material_does_not_reference_missing_texture():
    result = write(
        payload(
            meshes=(mesh(material_indices=(0,),),),
            materials=(
                material("used", color=(0.2, 0.4, 0.6, 1.0)),
                material("unused-textured", color=(0.7, 0.8, 0.9, 1.0), png=PNG_BYTES),
            ),
        ),
        units_mode="raw",
    )

    gltf, _ = parse_glb(result.glb)
    unused_pbr = gltf["materials"][1]["pbrMetallicRoughness"]

    assert unused_pbr["baseColorFactor"] == [0.7, 0.8, 0.9, 1.0]
    assert "baseColorTexture" not in unused_pbr


def test_scalar_only_no_uv_mesh_fails_until_dummy_uv_smoke_flag_is_enabled():
    capture = payload(meshes=(mesh(uvs=None),), materials=(material(png=None),))

    from rook.mesh2splat.glb_writer import GlbBuildError

    with pytest.raises(GlbBuildError) as exc:
        write(capture, allow_dummy_scalar_uv=False)

    assert exc.value.code == "scalar_material_requires_uv"

    result = write(capture, allow_dummy_scalar_uv=True)
    gltf, bin_chunk = parse_glb(result.glb)
    texcoords = accessor_values(
        gltf,
        bin_chunk,
        primitive(gltf)["attributes"]["TEXCOORD_0"],
    )
    assert texcoords == [(0.0, 0.0)] * 3


def test_missing_scalar_color_falls_back_to_white_with_warning():
    result = write(
        payload(materials=(material(color=None),)),
        units_mode="raw",
    )

    gltf, _ = parse_glb(result.glb)
    pbr = gltf["materials"][0]["pbrMetallicRoughness"]
    assert pbr["baseColorFactor"] == [1.0, 1.0, 1.0, 1.0]
    assert [warning.code for warning in result.warnings] == [
        "material_scalar_color_defaulted"
    ]


def test_index_component_type_is_unsigned_short_under_65536_otherwise_unsigned_int():
    small_result = write(payload(), units_mode="raw")
    small_gltf, _ = parse_glb(small_result.glb)
    assert small_gltf["accessors"][primitive(small_gltf)["indices"]]["componentType"] == 5123

    vertex_count = 65536
    large_faces = tuple(
        (index, index + 1, index + 2) for index in range(0, vertex_count - 2, 3)
    ) + ((vertex_count - 3, vertex_count - 2, vertex_count - 1),)
    large_mesh = mesh(
        positions=tuple((float(index), 0.0, 0.0) for index in range(vertex_count)),
        faces=large_faces,
        normals=tuple((0.0, 0.0, 1.0) for _ in range(vertex_count)),
        uvs=tuple((0.0, 0.0) for _ in range(vertex_count)),
        material_indices=tuple(0 for _ in large_faces),
    )

    large_result = write(payload(meshes=(large_mesh,)), units_mode="raw")
    large_gltf, _ = parse_glb(large_result.glb)

    assert large_gltf["accessors"][primitive(large_gltf)["indices"]]["componentType"] == 5125


def test_all_emitted_accessors_include_min_max_matching_binary_data():
    source_normals = ((1.0, 2.0, 3.0), (-1.0, 0.5, 4.0), (0.0, -2.0, -3.0))
    source_uvs = ((0.2, 0.7), (0.8, -0.25), (1.5, 0.0))

    result = write(
        payload(meshes=(mesh(normals=source_normals, uvs=source_uvs),)),
        units_mode="raw",
    )

    gltf, bin_chunk = parse_glb(result.glb)
    for accessor_index, accessor in enumerate(gltf["accessors"]):
        values = accessor_values(gltf, bin_chunk, accessor_index)
        if accessor["type"] == "SCALAR":
            component_values = [(float(value),) for value in values]
        else:
            component_values = [
                tuple(float(component) for component in value) for value in values
            ]
        expected_min = [
            min(value[component_index] for value in component_values)
            for component_index in range(len(component_values[0]))
        ]
        expected_max = [
            max(value[component_index] for value in component_values)
            for component_index in range(len(component_values[0]))
        ]

        assert accessor["min"] == pytest.approx(expected_min)
        assert accessor["max"] == pytest.approx(expected_max)


def test_validator_reports_lightweight_source_export_consistency_warnings():
    from rook.mesh2splat.glb_writer import SourceExpectations, validate_glb_bytes

    result = write(payload(materials=(material(color=(0.2, 0.4, 0.6, 1.0)),)))
    warnings = validate_glb_bytes(
        result.glb,
        source_expectations=SourceExpectations(
            expected_primitive_instance_count=2,
            expected_textured_material_count=1,
            expected_scalar_material_count=0,
        ),
    )

    assert [warning.code for warning in warnings] == [
        "primitive_instance_count_mismatch",
        "textured_material_count_mismatch",
        "scalar_material_count_mismatch",
    ]


def test_validator_warns_for_accessor_ranges_that_disagree_with_binary_positions():
    from rook.mesh2splat.glb_writer import SourceExpectations, validate_glb_bytes

    result = write(payload(), units_mode="raw")
    gltf, bin_chunk = parse_glb(result.glb)
    position_accessor = gltf["meshes"][0]["primitives"][0]["attributes"]["POSITION"]
    gltf["accessors"][position_accessor]["max"] = [99.0, 99.0, 99.0]
    rebuilt = rebuild_glb(gltf, bin_chunk)

    warnings = validate_glb_bytes(
        rebuilt,
        source_expectations=SourceExpectations(expected_primitive_instance_count=1),
    )

    assert [warning.code for warning in warnings] == ["accessor_range_mismatch"]


def test_validator_warns_for_material_texture_index_out_of_range():
    from rook.mesh2splat.glb_writer import SourceExpectations, validate_glb_bytes

    result = write(payload(materials=(material(png=PNG_BYTES),)), units_mode="raw")
    gltf, bin_chunk = parse_glb(result.glb)
    gltf["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"]["index"] = 99

    warnings = validate_glb_bytes(
        rebuild_glb(gltf, bin_chunk),
        source_expectations=SourceExpectations(),
    )

    assert [warning.code for warning in warnings] == ["material_texture_index_invalid"]


def test_validator_warns_for_texture_source_out_of_range():
    from rook.mesh2splat.glb_writer import SourceExpectations, validate_glb_bytes

    result = write(payload(materials=(material(png=PNG_BYTES),)), units_mode="raw")
    gltf, bin_chunk = parse_glb(result.glb)
    gltf["textures"][0]["source"] = 99

    warnings = validate_glb_bytes(
        rebuild_glb(gltf, bin_chunk),
        source_expectations=SourceExpectations(),
    )

    assert [warning.code for warning in warnings] == ["texture_source_index_invalid"]


@pytest.mark.parametrize("image_patch", [{"bufferView": 99}, {}])
def test_validator_warns_for_image_buffer_view_missing_or_out_of_range(image_patch):
    from rook.mesh2splat.glb_writer import SourceExpectations, validate_glb_bytes

    result = write(payload(materials=(material(png=PNG_BYTES),)), units_mode="raw")
    gltf, bin_chunk = parse_glb(result.glb)
    gltf["images"][0] = {"mimeType": "image/png", **image_patch}

    warnings = validate_glb_bytes(
        rebuild_glb(gltf, bin_chunk),
        source_expectations=SourceExpectations(),
    )

    assert [warning.code for warning in warnings] == ["image_buffer_view_invalid"]
