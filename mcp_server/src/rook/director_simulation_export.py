"""Director v3 per-member simulation export.

Harvests the CanvasDirector band-peel wave's per-member offsets and camera by
scrubbing the Director Clock, emits ordinary per-member motion.json tracks, and
drives the existing package/prepare/compile/capture pipeline unchanged.
Spec: docs/superpowers/specs/2026-07-07-director-v3-simulation-export-design.md
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

SAMPLES_SCHEMA_VERSION = 1
SAMPLES_METADATA_KIND = "director_member_motion_samples_v1"


class SimulationExportError(Exception):
    """Typed failure with a stable code."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def canonical_json_text(payload: Any) -> str:
    """Repo canonical JSON, matching director_take_package.canonical_json_text."""
    return json.dumps(payload, indent=2, sort_keys=True)


def ids_sha256(ids: list[str]) -> str:
    return hashlib.sha256(canonical_json_text(list(ids)).encode("utf-8")).hexdigest()


def build_samples_artifact(
    ids: list[str],
    per_frame_z: list[list[float]],
    meta: dict[str, Any],
) -> dict[str, Any]:
    frame_count = len(per_frame_z)
    frames = [
        {"frame_index": p + 1, "translate_z": [float(v) for v in per_frame_z[p]]}
        for p in range(frame_count)
    ]
    return {
        "schema_version": SAMPLES_SCHEMA_VERSION,
        "metadata_kind": SAMPLES_METADATA_KIND,
        "actor_set_id": meta["actor_set_id"],
        "source_block_name": meta["source_block_name"],
        "source_top_level_object_id": meta["source_top_level_object_id"],
        "frame_count": frame_count,
        "fps": meta["fps"],
        "units": meta["units"],
        "transform_semantics": "absolute_from_source",
        "sample_kind": "translate_z",
        "id_space": "top_level_definition_object_id",
        "ids": list(ids),
        "frames": frames,
        "ids_sha256": ids_sha256(list(ids)),
        "component_provenance": dict(meta.get("component_provenance", {})),
        "warnings": list(meta.get("warnings", [])),
    }


def assert_samples_invariants(artifact: dict[str, Any]) -> None:
    frame_count = artifact["frame_count"]
    if frame_count < 2:
        raise SimulationExportError(
            "frame_count_too_small",
            f"frame_count must be >= 2, got {frame_count}",
        )

    ids = artifact["ids"]
    if len(set(ids)) != len(ids):
        raise SimulationExportError(
            "duplicate_member_id",
            "ids contains a duplicate definition_object_id",
        )

    frames = artifact["frames"]
    if len(frames) != frame_count:
        raise SimulationExportError(
            "frame_count_mismatch",
            f"{len(frames)} frames != frame_count {frame_count}",
        )

    member_count = len(ids)
    for p, frame in enumerate(frames):
        if frame["frame_index"] != p + 1:
            raise SimulationExportError(
                "frame_index_disorder",
                f"frame {p}: frame_index {frame['frame_index']} != {p + 1}",
            )
        if len(frame["translate_z"]) != member_count:
            raise SimulationExportError(
                "member_count_mismatch",
                f"frame {p}: translate_z len {len(frame['translate_z'])} != {member_count} ids",
            )

    if any(z != 0 for z in frames[0]["translate_z"]):
        raise SimulationExportError(
            "frame0_not_rest",
            "frame 0 (frame_index 1) is not rest (translate_z has non-zero)",
        )

    if artifact["ids_sha256"] != ids_sha256(ids):
        raise SimulationExportError(
            "ids_hash_mismatch",
            "ids_sha256 does not match ids",
        )


def build_actor_member_ids(
    block_objects: list[dict[str, Any]],
    actor_set_id: str,
) -> tuple[dict[str, str], dict[str, int]]:
    """Map /block/objects-detailed objects to Director actor_member_id values."""
    def_to_member: dict[str, str] = {}
    def_to_index: dict[str, int] = {}
    for obj in block_objects:
        def_id = obj.get("id")
        index = obj.get("index")
        if def_id is None or index is None:
            continue
        if def_id in def_to_member:
            raise SimulationExportError(
                "duplicate_definition_object_id",
                f"block object id {def_id} appears twice",
            )
        index_int = int(index)
        def_to_member[def_id] = f"{actor_set_id}_member_{index_int:04d}"
        def_to_index[def_id] = index_int
    return def_to_member, def_to_index


def build_motion_json(
    artifact: dict[str, Any],
    def_to_member_id: dict[str, str],
    fps: int,
) -> dict[str, Any]:
    """Build declarative per-member motion.json from absolute-from-rest z samples."""
    ids = artifact["ids"]
    frames = artifact["frames"]
    frame_count = artifact["frame_count"]
    if frame_count < 2:
        raise SimulationExportError(
            "frame_count_too_small",
            f"frame_count {frame_count} < 2",
        )

    seen_members: set[str] = set()
    tracks: list[dict[str, Any]] = []
    for member_index, def_id in enumerate(ids):
        member_id = def_to_member_id.get(def_id)
        if member_id is None:
            raise SimulationExportError(
                "nested_or_unknown_id",
                f"def id {def_id} is not a top-level block member",
            )
        if member_id in seen_members:
            raise SimulationExportError(
                "duplicate_member_id",
                f"actor_member_id {member_id} generated twice",
            )
        seen_members.add(member_id)
        keyframes = [
            {
                "t": p / (frame_count - 1),
                "translate": [0.0, 0.0, float(frames[p]["translate_z"][member_index])],
            }
            for p in range(1, frame_count)
        ]
        tracks.append({"target": member_id, "keyframes": keyframes})

    return {
        "timeline": {"fps": fps, "frame_count": frame_count},
        "groups": {},
        "default_easing": "linear",
        "motion": tracks,
    }
