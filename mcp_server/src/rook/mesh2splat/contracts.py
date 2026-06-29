from __future__ import annotations

import ntpath
from dataclasses import dataclass
from typing import Any


DEFAULT_FORMAT = "compressed-pbr"
DEFAULT_UNITS_MODE = "meters"
VALID_FORMATS = {"compressed-pbr", "standard"}
MIN_SAMPLING_RESOLUTION = 16
MAX_SAMPLING_RESOLUTION = 4096
LARGE_OUTPUT_SAMPLING_THRESHOLD = 512
MESH2SPLAT_MAX_GAUSSIANS = 7_000_000
FORMAT_STRIDES = {"compressed-pbr": 48, "standard": 248}

VALID_UNITS_MODES = {"meters", "raw"}

SAMPLING_RESOLUTION_MESSAGE = (
    "samplingResolution must be an integer from 16 to 4096"
)
LARGE_OUTPUT_MESSAGE = (
    "samplingResolution > 512 or format standard requires allowLargeOutput=true"
)


@dataclass(frozen=True)
class Mesh2SplatRequest:
    output_directory: str
    format: str = DEFAULT_FORMAT
    sampling_resolution: int = 128
    units_mode: str = DEFAULT_UNITS_MODE
    allow_large_output: bool = False
    allow_network_textures: bool = False
    preserve_debug_artifacts: bool = False
    object_ids: tuple[str, ...] | None = None
    allow_partial: bool = False
    mesh2splat_path: str | None = None
    mesh2splat_working_directory: str | None = None
    mesh2splat_timeout_seconds: int | None = None


class RequestValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.envelope: dict[str, object] = {
            "success": False,
            "data": {
                "code": code,
                "message": message,
                "retryable": False,
            },
        }


def validate_request(
    raw: dict[str, object], *, default_sampling_resolution: int
) -> Mesh2SplatRequest:
    if not isinstance(raw, dict):
        _raise_invalid("request must be an object")

    output_directory = _required_absolute_path(
        raw.get("outputDirectory"),
        "outputDirectory is required and must be an absolute path",
    )
    format_name = _optional_string(raw, "format", DEFAULT_FORMAT)
    if format_name not in VALID_FORMATS:
        _raise_invalid("format must be one of: compressed-pbr, standard")

    sampling_resolution = raw.get(
        "samplingResolution", default_sampling_resolution
    )
    sampling_resolution = _sampling_resolution(sampling_resolution)

    units_mode = _optional_string(raw, "unitsMode", DEFAULT_UNITS_MODE)
    if units_mode not in VALID_UNITS_MODES:
        _raise_invalid("unitsMode must be one of: meters, raw")

    allow_large_output = _optional_bool(raw, "allowLargeOutput", False)
    if (
        sampling_resolution > LARGE_OUTPUT_SAMPLING_THRESHOLD
        or format_name == "standard"
    ) and not allow_large_output:
        raise RequestValidationError(
            "large_output_requires_opt_in",
            LARGE_OUTPUT_MESSAGE,
        )

    return Mesh2SplatRequest(
        output_directory=output_directory,
        format=format_name,
        sampling_resolution=sampling_resolution,
        units_mode=units_mode,
        allow_large_output=allow_large_output,
        allow_network_textures=_optional_bool(raw, "allowNetworkTextures", False),
        preserve_debug_artifacts=_optional_bool(
            raw, "preserveDebugArtifacts", False
        ),
        object_ids=_optional_object_ids(raw),
        allow_partial=_optional_bool(raw, "allowPartial", False),
        mesh2splat_path=_optional_string_or_none(raw, "mesh2splatPath"),
        mesh2splat_working_directory=_optional_string_or_none(
            raw, "mesh2splatWorkingDirectory"
        ),
        mesh2splat_timeout_seconds=_optional_positive_int_or_none(
            raw, "mesh2splatTimeoutSeconds"
        ),
    )


def _required_absolute_path(value: object, message: str) -> str:
    if not isinstance(value, str) or not value or not ntpath.isabs(value):
        _raise_invalid(message)
    return value


def _optional_string(
    raw: dict[str, object], key: str, default: str
) -> str:
    value = raw.get(key, default)
    if not isinstance(value, str) or not value:
        _raise_invalid(f"{key} must be a string")
    return value


def _optional_string_or_none(
    raw: dict[str, object], key: str
) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        _raise_invalid(f"{key} must be a string")
    return value


def _optional_bool(
    raw: dict[str, object], key: str, default: bool
) -> bool:
    value = raw.get(key, default)
    if not isinstance(value, bool):
        _raise_invalid(f"{key} must be a boolean")
    return value


def _optional_int_or_none(
    raw: dict[str, object], key: str
) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        _raise_invalid(f"{key} must be an integer")
    return value


def _optional_positive_int_or_none(
    raw: dict[str, object], key: str
) -> int | None:
    value = _optional_int_or_none(raw, key)
    if value is None:
        return None
    if value <= 0:
        _raise_invalid(f"{key} must be a positive integer")
    return value


def _optional_object_ids(raw: dict[str, object]) -> tuple[str, ...] | None:
    if "object_ids" not in raw:
        return None
    value = raw["object_ids"]
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
    ):
        _raise_invalid("object_ids must be a non-empty list of strings")
    return tuple(value)


def _sampling_resolution(value: Any) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < MIN_SAMPLING_RESOLUTION
        or value > MAX_SAMPLING_RESOLUTION
    ):
        _raise_invalid(SAMPLING_RESOLUTION_MESSAGE)
    return value


def _raise_invalid(message: str) -> None:
    raise RequestValidationError("invalid_request", message)
