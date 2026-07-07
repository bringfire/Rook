"""Director v3 per-member simulation export.

Harvests the CanvasDirector band-peel wave's per-member offsets and camera by
scrubbing the Director Clock, emits ordinary per-member motion.json tracks, and
drives the existing package/prepare/compile/capture pipeline unchanged.
Spec: docs/superpowers/specs/2026-07-07-director-v3-simulation-export-design.md
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
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


async def _gh_set_value(call_native, guid: str, value: Any) -> None:
    response = await call_native("/gh/value", "POST", {"guid": guid, "value": value})
    if not response.get("success"):
        raise SimulationExportError(
            "gh_set_value_failed",
            f"{guid}={value}: {response.get('data')}",
        )


async def _gh_read_output(call_native, guid: str, param: str) -> Any:
    response = await call_native(
        "/gh/inspect-output",
        "GET",
        {"guid": guid, "param": param},
    )
    data = response.get("data", response)
    preview = data.get("preview") if isinstance(data, dict) else None
    if not preview:
        raise SimulationExportError(
            "gh_output_empty",
            f"{guid}.{param} has no data",
        )
    return json.loads(preview[0])


async def harvest_samples(
    call_native,
    roles: dict[str, str],
    frame_count: int,
    clock_denominator: float,
) -> tuple[list[str], list[list[float]], list[dict[str, Any]]]:
    if frame_count < 2:
        raise SimulationExportError(
            "frame_count_too_small",
            f"frame_count {frame_count} < 2",
        )

    ids: list[str] | None = None
    ids_hash: str | None = None
    per_frame_z: list[list[float]] = []
    cam_keyframes: list[dict[str, Any]] = []
    try:
        for p in range(frame_count):
            t = p / (frame_count - 1)
            frame_in = round(t * clock_denominator)
            await _gh_set_value(call_native, roles["frame_in"], frame_in)

            samples = await _gh_read_output(call_native, roles["wave"], "Samples")
            frame_ids = list(samples["ids"])
            frame_z = [float(v) for v in samples["z"]]
            if len(frame_ids) != len(frame_z):
                raise SimulationExportError(
                    "samples_len_mismatch",
                    f"frame {p}: {len(frame_ids)} ids != {len(frame_z)} z",
                )
            current_ids_hash = ids_sha256(frame_ids)
            if ids is None:
                ids = frame_ids
                ids_hash = current_ids_hash
                if len(set(ids)) != len(ids):
                    raise SimulationExportError(
                        "duplicate_member_id",
                        "Samples.ids has duplicates",
                    )
            elif current_ids_hash != ids_hash:
                raise SimulationExportError(
                    "ids_unstable",
                    f"frame {p}: Samples.ids changed mid-scrub",
                )
            per_frame_z.append(frame_z)

            camera = await _gh_read_output(call_native, roles["camera_ctrl"], "Camera")
            local_t = float(camera.get("local_t"))
            expected_t = frame_in / clock_denominator
            if abs(local_t - expected_t) > 1e-3:
                raise SimulationExportError(
                    "camera_stale",
                    f"frame {p}: local_t {local_t} != {expected_t}",
                )
            cam_keyframes.append(
                {
                    "frame_index": p + 1,
                    "source": {
                        "kind": "explicit_camera",
                        "camera": {
                            "projection": camera.get("projection", "perspective"),
                            "location": camera["location"],
                            "target": camera["target"],
                            "up": camera.get("up", [0.0, 0.0, 1.0]),
                            "lens_length": camera.get("lens_length", 50.0),
                        },
                    },
                }
            )
    finally:
        await _gh_set_value(call_native, roles["frame_in"], 0)

    return ids or [], per_frame_z, cam_keyframes


async def resolve_canvas_roles(call_native) -> dict[str, str]:
    """Resolve live Grasshopper role GUIDs by exact nickName and component type.

    Verified /gh/query shape: {"data": {"objects": [{"guid", "nickName", "type", ...}]}}.
    The type filter is required because the canvas also contains a GH_Group whose
    nickname includes "Director Camera Controller".
    """
    response = await call_native("/gh/query", "GET", None)
    objects = response["data"]["objects"]

    def find(nickname: str, obj_type: str, role: str) -> str:
        hits = [
            obj
            for obj in objects
            if obj.get("nickName") == nickname and obj.get("type") == obj_type
        ]
        if len(hits) != 1:
            raise SimulationExportError(
                "canvas_role_unresolved",
                f"{role}: found {len(hits)} candidates",
            )
        return hits[0]["guid"]

    return {
        "frame_in": find("FrameIn", "GH_NumberSlider", "FrameIn slider"),
        "camera_ctrl": find(
            "Director Camera Controller",
            "CSharpComponent",
            "Camera Controller",
        ),
        "wave": find(
            "Director Band Peel Wave Preview",
            "CSharpComponent",
            "Band Peel Wave Preview",
        ),
    }


async def run_simulation_export(args: dict[str, Any], *, call_native) -> dict[str, Any]:
    """Harvest, package, prepare, compile, verify, then capture one pass.

    Video assembly is intentionally outside this function; the live driver calls
    director_video.assemble_director_video against the returned pass run root.
    """
    from rook import director_take_package as dtp
    from rook import director_worker_capture as dwcap
    from rook import director_worker_compile as dwc
    from rook import director_worker_prepare as dprep

    before = (await call_native("/document", "GET"))["data"]
    original_path = before.get("path") or ""
    if before.get("modified"):
        raise SimulationExportError(
            "live_doc_modified",
            "save the live document before rendering",
        )

    try:
        roles = await resolve_canvas_roles(call_native)
        ids, per_frame_z, cam_keyframes = await harvest_samples(
            call_native,
            roles,
            args["frame_count"],
            args["clock_denominator"],
        )
        meta = {
            "actor_set_id": args["actor_set_id"],
            "source_block_name": args["block_name"],
            "source_top_level_object_id": args["source_top_level_object_id"],
            "fps": args["fps"],
            "units": args["units"],
            "component_provenance": {
                "component_nick": "Director Band Peel Wave Preview",
                "clock_denominator": args["clock_denominator"],
            },
        }
        artifact = build_samples_artifact(ids, per_frame_z, meta)
        assert_samples_invariants(artifact)

        block = (
            await call_native(
                "/block/objects-detailed",
                "POST",
                {"name": args["block_name"]},
            )
        )["data"]
        def_to_member, def_to_index = build_actor_member_ids(
            block["objects"],
            args["actor_set_id"],
        )
        for def_id in ids:
            if def_id not in def_to_member:
                raise SimulationExportError(
                    "nested_or_unknown_id",
                    f"{def_id} not a top-level member of {args['block_name']}",
                )
        motion = build_motion_json(artifact, def_to_member, args["fps"])

        package_result = await dtp.package_take(
            {
                "take_id": args["take_id"],
                "output_root": args["output_root"],
                "actor_sets": [
                    {
                        "actor_set_id": args["actor_set_id"],
                        "block_name": args["block_name"],
                        "source_top_level_object_id": args["source_top_level_object_id"],
                    }
                ],
                "motion": motion,
                "camera": {"strategy": "keyframes", "keyframes": cam_keyframes},
                "display_modes": args["display_modes"],
            },
            call_native=call_native,
        )
        package_root = package_result["package_root"]

        manifest = json.loads(
            (Path(package_root) / "scene_manifest.json").read_text(encoding="utf-8")
        )
        assert_manifest_matches(
            manifest,
            args["actor_set_id"],
            {def_id: def_to_member[def_id] for def_id in ids},
            {def_id: def_to_index[def_id] for def_id in ids},
        )

        prepare_result = await dprep.prepare_take(
            {"package_root": package_root},
            call_native=call_native,
        )
        compile_result = await dwc.compile_take(
            {"package_root": package_root},
            call_native=call_native,
        )

        track = json.loads(
            (Path(package_root) / "track.json").read_text(encoding="utf-8")
        )
        member_map = _member_map_by_def_id(package_root)
        sample_def_ids = _pick_sample_members(ids, member_map)
        verify_motion_roundtrip(track, artifact, member_map, sample_def_ids)
        verify_camera_roundtrip(track, cam_keyframes)

        capture_result = await dwcap.capture_take(
            {
                "package_root": package_root,
                "passes": [
                    {
                        "type": "display_mode",
                        "pass_id": "sim",
                        "display_mode": args["capture_mode"],
                    }
                ],
                "resolution": args["resolution"],
            },
            call_native=call_native,
        )
        return {
            "package_root": package_root,
            "artifact": artifact,
            "prepared": prepare_result.get("phase"),
            "compiled": compile_result.get("phase"),
            "capture": capture_result["passes"][0],
        }
    finally:
        await call_native("/document/open", "POST", {"path": original_path})


def _member_map_by_def_id(package_root: str) -> dict[str, list[str]]:
    """Read package_root/member_map.json as {definition_object_id: created ids}."""
    member_map = json.loads(
        (Path(package_root) / "member_map.json").read_text(encoding="utf-8")
    )
    out: dict[str, list[str]] = {}
    for actor_set in member_map.get("actor_sets") or []:
        for member in actor_set.get("members") or []:
            out[member["definition_object_id"]] = list(member.get("created_object_ids") or [])
    return out


def _pick_sample_members(ids: list[str], member_map: dict[str, list[str]]) -> list[str]:
    picks = [ids[0]]
    nested = next((def_id for def_id in ids if len(member_map.get(def_id) or []) > 1), None)
    if nested and nested not in picks:
        picks.append(nested)
    if len(ids) > 1 and ids[-1] not in picks:
        picks.append(ids[-1])
    return picks
