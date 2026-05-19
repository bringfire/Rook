from __future__ import annotations

import os
import math
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


def identity_matrix() -> list[list[float]]:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def translation_matrix(vector: list[float]) -> list[list[float]]:
    matrix = identity_matrix()
    matrix[0][3] = float(vector[0])
    matrix[1][3] = float(vector[1])
    matrix[2][3] = float(vector[2])
    return matrix


def _center(bbox_min: list[float], bbox_max: list[float]) -> list[float]:
    return [(float(a) + float(b)) / 2.0 for a, b in zip(bbox_min, bbox_max)]


def _normalize(vector: list[float]) -> list[float] | None:
    length = math.sqrt(sum(float(v) * float(v) for v in vector))
    if length < 1e-9:
        return None
    return [float(v) / length for v in vector]


def expand_radial_bbox_center(
    objects: list[dict[str, Any]],
    *,
    frame_count: int,
    distance: float,
    per_object_scale: dict[str, float],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    all_mins = [float(v) for obj in objects for v in obj["bbox_min"]]
    all_maxs = [float(v) for obj in objects for v in obj["bbox_max"]]
    selection_min = [min(all_mins[i::3]) for i in range(3)]
    selection_max = [max(all_maxs[i::3]) for i in range(3)]
    selection_center = _center(selection_min, selection_max)

    directions: dict[str, list[float]] = {}
    warnings: list[dict[str, Any]] = []
    for obj in objects:
        object_id = obj["object_id"]
        object_center = _center(obj["bbox_min"], obj["bbox_max"])
        raw = [object_center[i] - selection_center[i] for i in range(3)]
        direction = _normalize(raw)
        if direction is None:
            direction = [1.0, 0.0, 0.0]
            warnings.append({"code": "center_direction_fallback", "object_id": object_id})
        directions[object_id] = direction

    frames: list[dict[str, Any]] = []
    for index in range(1, frame_count + 1):
        t = 0.0 if frame_count == 1 else (index - 1) / (frame_count - 1)
        object_transforms = []
        for obj in objects:
            object_id = obj["object_id"]
            scale = float(per_object_scale.get(object_id, 1.0))
            direction = directions[object_id]
            vector = [component * float(distance) * scale * t for component in direction]
            object_transforms.append(
                {
                    "object_id": object_id,
                    "source_state": {
                        "bbox_min": obj["bbox_min"],
                        "bbox_max": obj["bbox_max"],
                        "validation_strength": obj.get(
                            "validation_strength", "bbox_only"
                        ),
                        "state_hash": obj.get("state_hash"),
                    },
                    "transform": translation_matrix(vector),
                }
            )
        frames.append({"frame_index": index, "object_transforms": object_transforms})
    return frames, warnings
