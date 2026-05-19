from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .runtime_paths import resolve_runtime_paths

SCHEMA_VERSION = 1
DIRECTOR_VERSION = "slice1"


class DirectorError(Exception):
    pass


class DirectorInputError(DirectorError):
    pass


@dataclass(frozen=True)
class DirectorRuntimePaths:
    director_output_root: Path | None = None


def _runtime_paths() -> DirectorRuntimePaths:
    resolve_runtime_paths()
    return DirectorRuntimePaths()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _default_director_output_root(runtime: DirectorRuntimePaths | None = None) -> Path:
    runtime = runtime or _runtime_paths()
    if runtime.director_output_root is not None:
        return Path(runtime.director_output_root).expanduser().resolve()
    env_root = os.environ.get("ROOK_DIRECTOR_OUTPUT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise DirectorInputError(
            "LOCALAPPDATA is required when ROOK_DIRECTOR_OUTPUT_ROOT is not set"
        )
    return (Path(local_app_data) / "Rook" / "rookvision_director").resolve()


def resolve_output_root(
    output_root: str | None, runtime: DirectorRuntimePaths | None = None
) -> Path:
    allowed_root = _default_director_output_root(runtime)
    if output_root is None:
        return allowed_root
    candidate = Path(output_root).expanduser().resolve()
    if not _is_relative_to(candidate, allowed_root):
        raise DirectorInputError(
            "output_root must resolve under the configured RookVisionDirector output root"
        )
    return candidate


def validate_authoring_request(request: dict[str, Any]) -> None:
    frame_count = int(request.get("frame_count", 0))
    if frame_count < 1:
        raise DirectorInputError("frame_count must be >= 1")

    resolution = request.get("resolution") or {}
    width = int(resolution.get("width", 0))
    height = int(resolution.get("height", 0))
    if width <= 0 or height <= 0:
        raise DirectorInputError("resolution width and height must be positive")

    motion = request.get("motion") or {}
    if motion.get("strategy", "radial_bbox_center") != "radial_bbox_center":
        raise DirectorInputError("motion strategy must be radial_bbox_center for slice1")
    params = motion.get("parameters") or {}
    distance = float(params.get("distance", 10.0))
    if distance < 0:
        raise DirectorInputError("motion distance must be nonnegative")
