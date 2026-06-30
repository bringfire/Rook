from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from .contracts import FORMAT_STRIDES, MESH2SPLAT_MAX_GAUSSIANS, VALID_FORMATS


ESTIMATE_BASIS = (
    "1MiB + min(samplingResolution^2 * 6 * "
    "mesh2splatLoadedMeshCount, maxGaussians) * formatStride"
)


@dataclass(frozen=True)
class PlyEstimate:
    ok: bool
    estimated_ply_bytes: int
    estimate_basis: str
    estimate_confidence: str
    stride: int
    warnings: list[str]
    errors: list[str]


@dataclass(frozen=True)
class PlyValidationResult:
    ok: bool
    actual_ply_bytes: int
    header_vertex_count: int | None
    stride: int
    warnings: list[str]
    errors: list[str]


def estimate_ply_bytes(
    *,
    sampling_resolution: int,
    mesh2splat_loaded_mesh_count: int,
    fmt: str,
    max_gaussians: int = MESH2SPLAT_MAX_GAUSSIANS,
) -> PlyEstimate:
    if fmt not in VALID_FORMATS:
        return PlyEstimate(
            ok=False,
            estimated_ply_bytes=0,
            estimate_basis=ESTIMATE_BASIS,
            estimate_confidence="low",
            stride=0,
            warnings=[],
            errors=["invalid_format"],
        )

    stride = FORMAT_STRIDES[fmt]
    capacity = min(
        sampling_resolution
        * sampling_resolution
        * 6
        * mesh2splat_loaded_mesh_count,
        max_gaussians,
    )
    return PlyEstimate(
        ok=True,
        estimated_ply_bytes=(1024 * 1024) + capacity * stride,
        estimate_basis=ESTIMATE_BASIS,
        estimate_confidence="low",
        stride=stride,
        warnings=[],
        errors=[],
    )


def check_estimated_ply_guard(
    *,
    sampling_resolution: int,
    mesh2splat_loaded_mesh_count: int,
    fmt: str,
    max_estimated_ply_bytes_guard: int,
    max_gaussians: int = MESH2SPLAT_MAX_GAUSSIANS,
) -> PlyEstimate:
    estimate = estimate_ply_bytes(
        sampling_resolution=sampling_resolution,
        mesh2splat_loaded_mesh_count=mesh2splat_loaded_mesh_count,
        fmt=fmt,
        max_gaussians=max_gaussians,
    )
    if not estimate.ok:
        return estimate
    if estimate.estimated_ply_bytes <= max_estimated_ply_bytes_guard:
        return estimate
    return PlyEstimate(
        ok=False,
        estimated_ply_bytes=estimate.estimated_ply_bytes,
        estimate_basis=estimate.estimate_basis,
        estimate_confidence=estimate.estimate_confidence,
        stride=estimate.stride,
        warnings=estimate.warnings,
        errors=[*estimate.errors, "estimated_ply_too_large"],
    )


def validate_ply(
    path: Path,
    *,
    fmt: str,
    gaussian_count: int,
) -> PlyValidationResult:
    if fmt not in VALID_FORMATS:
        return PlyValidationResult(
            ok=False,
            actual_ply_bytes=_file_size_or_zero(path),
            header_vertex_count=None,
            stride=0,
            warnings=[],
            errors=["invalid_format"],
        )

    stride = FORMAT_STRIDES[fmt]
    if not path.is_file():
        return PlyValidationResult(
            ok=False,
            actual_ply_bytes=0,
            header_vertex_count=None,
            stride=stride,
            warnings=[],
            errors=["ply_missing"],
        )

    actual_ply_bytes = _file_size_or_zero(path)
    try:
        with path.open("rb") as ply_file:
            header = _parse_header(ply_file)
    except OSError:
        header = None

    if header is None:
        return PlyValidationResult(
            ok=False,
            actual_ply_bytes=actual_ply_bytes,
            header_vertex_count=None,
            stride=stride,
            warnings=[],
            errors=["ply_header_invalid"],
        )

    header_byte_length, lines = header
    header_vertex_count = _header_vertex_count(lines)
    properties = _header_properties(lines)
    errors: list[str] = []

    if header_vertex_count is None:
        errors.append("ply_header_invalid")
    elif header_vertex_count != gaussian_count:
        errors.append("ply_vertex_count_mismatch")

    if properties != _expected_properties(fmt):
        errors.append("ply_property_mismatch")

    expected_size = header_byte_length + gaussian_count * stride
    if actual_ply_bytes != expected_size:
        errors.append("ply_size_mismatch")

    return PlyValidationResult(
        ok=not errors,
        actual_ply_bytes=actual_ply_bytes,
        header_vertex_count=header_vertex_count,
        stride=stride,
        warnings=[],
        errors=errors,
    )


def _file_size_or_zero(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _parse_header(ply_file: BinaryIO) -> tuple[int, list[str]] | None:
    header_bytes = 0
    lines: list[str] = []
    for raw_line in ply_file:
        header_bytes += len(raw_line)
        try:
            line = raw_line.rstrip(b"\r\n").decode("ascii")
        except UnicodeDecodeError:
            return None
        lines.append(line)
        if line == "end_header":
            break
    else:
        return None

    if not lines or lines[0] != "ply":
        return None
    if len(lines) < 2 or lines[1] != "format binary_little_endian 1.0":
        return None
    return header_bytes, lines


def _header_vertex_count(lines: list[str]) -> int | None:
    for line in lines:
        parts = line.split()
        if len(parts) == 3 and parts[:2] == ["element", "vertex"]:
            try:
                return int(parts[2])
            except ValueError:
                return None
    return None


def _header_properties(lines: list[str]) -> list[tuple[str, str]]:
    properties: list[tuple[str, str]] = []
    in_vertex_element = False
    for line in lines:
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "element":
            in_vertex_element = len(parts) == 3 and parts[1] == "vertex"
            continue
        if in_vertex_element and len(parts) == 3 and parts[0] == "property":
            properties.append((_normalize_property_type(parts[1]), parts[2]))
            continue
        if line == "end_header":
            break
    return properties


def _expected_properties(fmt: str) -> list[tuple[str, str]]:
    if fmt == "compressed-pbr":
        return (
            [("float", name) for name in ("x", "y", "z")]
            + [("uint8", name) for name in ("red", "green", "blue", "opacity")]
            + [("float", f"rot_{index}") for index in range(4)]
            + [("float", f"scale_{index}") for index in range(3)]
            + [
                ("uint8", name)
                for name in ("octa_nx", "octa_ny", "roughness", "metallic")
            ]
        )

    return (
        [("float", name) for name in ("x", "y", "z", "nx", "ny", "nz")]
        + [("float", f"f_dc_{index}") for index in range(3)]
        + [("float", f"f_rest_{index}") for index in range(45)]
        + [("float", "opacity")]
        + [("float", f"scale_{index}") for index in range(3)]
        + [("float", f"rot_{index}") for index in range(4)]
    )


def _normalize_property_type(value: str) -> str:
    if value in {"uchar", "uint8"}:
        return "uint8"
    if value in {"float", "float32"}:
        return "float"
    return value
