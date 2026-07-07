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


def assert_manifest_matches(
    scene_manifest: dict[str, Any],
    actor_set_id: str,
    def_to_member_id: dict[str, str],
    def_to_index: dict[str, int],
) -> None:
    """Package-manifest drift gate: the manifest is the authority."""
    actor_sets = scene_manifest.get("actor_sets") or []
    manifest_set = next(
        (a for a in actor_sets if a.get("actor_set_id") == actor_set_id),
        None,
    )
    if manifest_set is None:
        raise SimulationExportError(
            "manifest_actor_set_missing",
            f"actor set {actor_set_id} not in scene_manifest",
        )

    by_def = {
        m["definition_object_id"]: m
        for m in (manifest_set.get("members") or [])
    }
    for def_id, member_id in def_to_member_id.items():
        member = by_def.get(def_id)
        if member is None:
            raise SimulationExportError(
                "manifest_member_missing",
                f"def id {def_id} absent from manifest",
            )
        if member.get("actor_member_id") != member_id:
            raise SimulationExportError(
                "manifest_drift",
                f"{def_id}: manifest member {member.get('actor_member_id')} != {member_id}",
            )
        if member.get("definition_object_index") != def_to_index[def_id]:
            raise SimulationExportError(
                "manifest_drift",
                f"{def_id}: manifest index {member.get('definition_object_index')} != {def_to_index[def_id]}",
            )


def verify_motion_roundtrip(
    track: dict[str, Any],
    artifact: dict[str, Any],
    member_map: dict[str, list[str]],
    sample_def_ids: list[str],
    tol: float = 1e-6,
) -> None:
    """Verify compiled transform z offsets match sampled z for representative members."""
    ids = artifact["ids"]
    id_pos = {def_id: i for i, def_id in enumerate(ids)}
    frames_by_index = {f["frame_index"]: f for f in track["object_frames"]}

    for def_id in sample_def_ids:
        if def_id not in id_pos:
            raise SimulationExportError(
                "roundtrip_unknown_member",
                f"{def_id} not in artifact ids",
            )
        created = member_map.get(def_id) or []
        if not created:
            raise SimulationExportError(
                "roundtrip_no_created",
                f"{def_id} has no created objects",
            )

        pos = id_pos[def_id]
        for p, art_frame in enumerate(artifact["frames"]):
            frame_index = p + 1
            expected = float(art_frame["translate_z"][pos])
            tframe = frames_by_index.get(frame_index)
            if tframe is None:
                raise SimulationExportError(
                    "motion_roundtrip_mismatch",
                    f"compiled track has no frame {frame_index}",
                )
            xf_by_obj = {
                t["object_id"]: t["transform"]
                for t in tframe["object_transforms"]
            }
            for created_id in created:
                if created_id not in xf_by_obj:
                    raise SimulationExportError(
                        "motion_roundtrip_mismatch",
                        f"{def_id}->{created_id} absent from frame {frame_index}",
                    )
                got = float(xf_by_obj[created_id][2][3])
                if abs(got - expected) > tol:
                    raise SimulationExportError(
                        "motion_roundtrip_mismatch",
                        f"{def_id}->{created_id} frame {frame_index}: transform z {got} != sampled {expected}",
                    )


def verify_camera_roundtrip(
    track: dict[str, Any],
    cam_keyframes: list[dict[str, Any]],
    tol: float = 1e-6,
) -> None:
    cam_frames = track["camera_frames"]
    if len(cam_frames) != len(cam_keyframes):
        raise SimulationExportError(
            "camera_frame_count_mismatch",
            f"{len(cam_frames)} camera_frames != {len(cam_keyframes)} harvested",
        )

    for p, (compiled_frame, keyframe) in enumerate(zip(cam_frames, cam_keyframes)):
        frame_index = p + 1
        if compiled_frame.get("frame_index") != frame_index:
            raise SimulationExportError(
                "camera_frame_disorder",
                f"camera_frames[{p}].frame_index {compiled_frame.get('frame_index')} != {frame_index}",
            )
        want = keyframe["source"]["camera"]
        got = compiled_frame["camera"]
        if got.get("projection") != want.get("projection"):
            raise SimulationExportError(
                "camera_roundtrip_mismatch",
                f"camera frame {frame_index} projection: {got.get('projection')} != {want.get('projection')}",
            )
        if abs(float(got.get("lens_length")) - float(want.get("lens_length"))) > tol:
            raise SimulationExportError(
                "camera_roundtrip_mismatch",
                f"camera frame {frame_index} lens_length: {got.get('lens_length')} != {want.get('lens_length')}",
            )
        for key in ("location", "target", "up"):
            for actual, expected in zip(got[key], want[key]):
                if abs(float(actual) - float(expected)) > tol:
                    raise SimulationExportError(
                        "camera_roundtrip_mismatch",
                        f"camera frame {frame_index} {key}: {got[key]} != {want[key]}",
                    )
