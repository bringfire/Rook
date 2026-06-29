from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace


def _standard_properties() -> list[tuple[str, str]]:
    return (
        [("float", name) for name in ("x", "y", "z", "nx", "ny", "nz")]
        + [("float", f"f_dc_{index}") for index in range(3)]
        + [("float", f"f_rest_{index}") for index in range(45)]
        + [("float", "opacity")]
        + [("float", f"scale_{index}") for index in range(3)]
        + [("float", f"rot_{index}") for index in range(4)]
    )


def _compressed_pbr_properties() -> list[tuple[str, str]]:
    return (
        [("float", name) for name in ("x", "y", "z")]
        + [("uchar", name) for name in ("red", "green", "blue", "opacity")]
        + [("float", f"rot_{index}") for index in range(4)]
        + [("float", f"scale_{index}") for index in range(3)]
        + [("uchar", name) for name in ("octa_nx", "octa_ny", "roughness", "metallic")]
    )


def _header_bytes(
    *,
    gaussian_count: int,
    properties: list[tuple[str, str]],
    newline: bytes = b"\n",
    format_line: str = "format binary_little_endian 1.0",
) -> bytes:
    lines = [
        "ply",
        format_line,
        f"element vertex {gaussian_count}",
        *(f"property {kind} {name}" for kind, name in properties),
        "end_header",
    ]
    return newline.join(line.encode("ascii") for line in lines) + newline


def _write_ply(
    path: Path,
    *,
    gaussian_count: int,
    properties: list[tuple[str, str]],
    stride: int,
    newline: bytes = b"\n",
    format_line: str = "format binary_little_endian 1.0",
) -> int:
    header = _header_bytes(
        gaussian_count=gaussian_count,
        properties=properties,
        newline=newline,
        format_line=format_line,
    )
    path.write_bytes(header + (b"\0" * gaussian_count * stride))
    return len(header)


class _HeaderOnlyPath:
    def __init__(self, header: bytes, apparent_size: int):
        self.header = header
        self.apparent_size = apparent_size
        self.read_bytes_called = False

    def is_file(self) -> bool:
        return True

    def stat(self) -> SimpleNamespace:
        return SimpleNamespace(st_size=self.apparent_size)

    def open(self, mode: str):
        assert mode == "rb"
        return BytesIO(self.header)

    def read_bytes(self) -> bytes:
        self.read_bytes_called = True
        raise AssertionError("validate_ply must not read the full payload")


def test_standard_header_contains_required_gaussian_splat_fields(tmp_path: Path):
    from rook.mesh2splat.ply import validate_ply

    ply_path = tmp_path / "standard.ply"
    _write_ply(
        ply_path,
        gaussian_count=1,
        properties=_standard_properties(),
        stride=248,
    )

    result = validate_ply(ply_path, fmt="standard", gaussian_count=1)

    assert result.ok is True
    assert result.errors == []
    header = ply_path.read_bytes().split(b"end_header\n", 1)[0]
    assert b"property float f_dc_0" in header
    assert b"property float scale_0" in header
    assert b"property float rot_0" in header


def test_compressed_pbr_header_matches_fork_compressed_fields(tmp_path: Path):
    from rook.mesh2splat.ply import validate_ply

    ply_path = tmp_path / "compressed.ply"
    _write_ply(
        ply_path,
        gaussian_count=2,
        properties=_compressed_pbr_properties(),
        stride=48,
    )

    result = validate_ply(ply_path, fmt="compressed-pbr", gaussian_count=2)

    assert result.ok is True
    assert result.header_vertex_count == 2
    assert result.stride == 48
    assert result.errors == []


def test_header_element_vertex_must_match_cli_gaussian_count(tmp_path: Path):
    from rook.mesh2splat.ply import validate_ply

    ply_path = tmp_path / "count-mismatch.ply"
    _write_ply(
        ply_path,
        gaussian_count=3,
        properties=_compressed_pbr_properties(),
        stride=48,
    )

    result = validate_ply(ply_path, fmt="compressed-pbr", gaussian_count=2)

    assert result.ok is False
    assert result.header_vertex_count == 3
    assert "ply_vertex_count_mismatch" in result.errors


def test_actual_byte_count_uses_exact_lf_header_bytes(tmp_path: Path):
    from rook.mesh2splat.ply import validate_ply

    ply_path = tmp_path / "exact-lf.ply"
    header_length = _write_ply(
        ply_path,
        gaussian_count=4,
        properties=_compressed_pbr_properties(),
        stride=48,
        newline=b"\n",
    )

    result = validate_ply(ply_path, fmt="compressed-pbr", gaussian_count=4)

    assert result.ok is True
    assert result.actual_ply_bytes == header_length + 4 * 48
    assert result.errors == []


def test_actual_byte_count_uses_exact_crlf_header_bytes(tmp_path: Path):
    from rook.mesh2splat.ply import validate_ply

    ply_path = tmp_path / "exact-crlf.ply"
    header_length = _write_ply(
        ply_path,
        gaussian_count=4,
        properties=_compressed_pbr_properties(),
        stride=48,
        newline=b"\r\n",
    )

    result = validate_ply(ply_path, fmt="compressed-pbr", gaussian_count=4)

    assert result.ok is True
    assert result.actual_ply_bytes == header_length + 4 * 48
    assert result.errors == []


def test_size_mismatch_reports_exact_actual_bytes(tmp_path: Path):
    from rook.mesh2splat.ply import validate_ply

    ply_path = tmp_path / "truncated.ply"
    header_length = _write_ply(
        ply_path,
        gaussian_count=4,
        properties=_compressed_pbr_properties(),
        stride=48,
    )
    ply_path.write_bytes(ply_path.read_bytes()[:-1])

    result = validate_ply(ply_path, fmt="compressed-pbr", gaussian_count=4)

    assert result.ok is False
    assert result.actual_ply_bytes == header_length + 4 * 48 - 1
    assert "ply_size_mismatch" in result.errors


def test_validation_streams_header_and_uses_stat_size_for_large_payloads():
    from rook.mesh2splat.ply import validate_ply

    header = _header_bytes(
        gaussian_count=1,
        properties=_compressed_pbr_properties(),
    )
    ply_path = _HeaderOnlyPath(header, apparent_size=len(header) + 48)

    result = validate_ply(ply_path, fmt="compressed-pbr", gaussian_count=1)

    assert result.ok is True
    assert result.actual_ply_bytes == len(header) + 48
    assert ply_path.read_bytes_called is False


def test_ascii_ply_format_is_rejected(tmp_path: Path):
    from rook.mesh2splat.ply import validate_ply

    ply_path = tmp_path / "ascii.ply"
    _write_ply(
        ply_path,
        gaussian_count=1,
        properties=_compressed_pbr_properties(),
        stride=48,
        format_line="format ascii 1.0",
    )

    result = validate_ply(ply_path, fmt="compressed-pbr", gaussian_count=1)

    assert result.ok is False
    assert "ply_header_invalid" in result.errors


def test_binary_big_endian_ply_format_is_rejected(tmp_path: Path):
    from rook.mesh2splat.ply import validate_ply

    ply_path = tmp_path / "big-endian.ply"
    _write_ply(
        ply_path,
        gaussian_count=1,
        properties=_compressed_pbr_properties(),
        stride=48,
        format_line="format binary_big_endian 1.0",
    )

    result = validate_ply(ply_path, fmt="compressed-pbr", gaussian_count=1)

    assert result.ok is False
    assert "ply_header_invalid" in result.errors


def test_estimated_ply_bytes_uses_current_mesh2splat_capacity_formula():
    from rook.mesh2splat.ply import estimate_ply_bytes

    result = estimate_ply_bytes(
        sampling_resolution=1024,
        mesh2splat_loaded_mesh_count=2,
        fmt="standard",
    )

    capacity = min(1024 * 1024 * 6 * 2, 7_000_000)
    assert result.estimated_ply_bytes == 1_048_576 + capacity * 248
    assert result.estimate_basis == (
        "1MiB + min(samplingResolution^2 * 6 * "
        "mesh2splatLoadedMeshCount, maxGaussians) * formatStride"
    )
    assert result.estimate_confidence == "low"
    assert result.warnings == []
    assert result.errors == []


def test_one_primitive_cube_standard_1024_estimate_passes_current_cap():
    from rook.mesh2splat.ply import check_estimated_ply_guard

    result = check_estimated_ply_guard(
        sampling_resolution=1024,
        mesh2splat_loaded_mesh_count=1,
        fmt="standard",
        max_estimated_ply_bytes_guard=1_048_576 + 7_000_000 * 248,
    )

    assert result.ok is True
    assert result.estimated_ply_bytes == 1_048_576 + (1024 * 1024 * 6) * 248
    assert result.errors == []


def test_lower_estimated_ply_guard_rejects_large_output():
    from rook.mesh2splat.ply import check_estimated_ply_guard

    result = check_estimated_ply_guard(
        sampling_resolution=1024,
        mesh2splat_loaded_mesh_count=1,
        fmt="standard",
        max_estimated_ply_bytes_guard=100,
    )

    assert result.ok is False
    assert "estimated_ply_too_large" in result.errors


def test_invalid_format_is_reported_for_estimate_and_validation(tmp_path: Path):
    from rook.mesh2splat.ply import estimate_ply_bytes, validate_ply

    ply_path = tmp_path / "capture.ply"
    _write_ply(
        ply_path,
        gaussian_count=1,
        properties=_compressed_pbr_properties(),
        stride=48,
    )

    estimate = estimate_ply_bytes(
        sampling_resolution=128,
        mesh2splat_loaded_mesh_count=1,
        fmt="unknown",
    )
    validation = validate_ply(ply_path, fmt="unknown", gaussian_count=1)

    assert estimate.ok is False
    assert validation.ok is False
    assert "invalid_format" in estimate.errors
    assert "invalid_format" in validation.errors
