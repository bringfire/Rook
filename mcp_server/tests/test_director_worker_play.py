from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from rook import director_worker_play as dwp
from rook.director_take_package import canonical_json_text, sha256_file, write_canonical_json

pytestmark = pytest.mark.asyncio

LIVE_DOC_PATH = "C:/work/live_project.3dm"

ABSOLUTE_MATRICES = [
    [
        [1.014222117604, -0.284700949613, 0.0, 1.928889411982],
        [0.271759997358, 1.062518408918, 0.0, -1.858799986788],
        [0.0, 0.0, 1.15, 0.25],
        [0.0, 0.0, 0.0, 1.0],
    ],
    [
        [0.952627944163, -0.6, 0.0, 4.236860279186],
        [0.55, 1.039230484541, 0.0, -3.75],
        [0.0, 0.0, 1.3, 0.5],
        [0.0, 0.0, 0.0, 1.0],
    ],
    [
        [0.813172798365, -0.919238815543, 0.0, 6.934136008177],
        [0.813172798365, 0.919238815543, 0.0, -5.565863991823],
        [0.0, 0.0, 1.45, 0.75],
        [0.0, 0.0, 0.0, 1.0],
    ],
    [
        [0.6, -1.212435565298, 0.0, 10.0],
        [1.039230484541, 0.7, 0.0, -7.196152422707],
        [0.0, 0.0, 1.6, 1.0],
        [0.0, 0.0, 0.0, 1.0],
    ],
    [
        [0.323523806378, -1.448888739434, 0.0, 13.382380968109],
        [1.207407282861, 0.388228567654, 0.0, -8.537036414307],
        [0.0, 0.0, 1.75, 1.25],
        [0.0, 0.0, 0.0, 1.0],
    ],
]


def _uuid(index: int) -> str:
    return f"00000000-0000-0000-0000-{index:012x}"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_file_sha(path: Path) -> str:
    return _sha256_text(path.read_text(encoding="utf-8"))


def mat_mul(a, b):
    return [
        [sum(a[row][k] * b[k][col] for k in range(4)) for col in range(4)]
        for row in range(4)
    ]


def mat_inv(m):
    width = 4
    aug = [
        [float(v) for v in m[row]]
        + [1.0 if row == col else 0.0 for col in range(width)]
        for row in range(width)
    ]
    for col in range(width):
        pivot = max(range(col, width), key=lambda row: abs(aug[row][col]))
        if abs(aug[pivot][col]) < 1e-15:
            raise ValueError("matrix is singular")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        pivot_value = aug[col][col]
        for j in range(width * 2):
            aug[col][j] /= pivot_value
        for row in range(width):
            if row == col:
                continue
            factor = aug[row][col]
            for j in range(width * 2):
                aug[row][j] -= factor * aug[col][j]
    return [row[width:] for row in aug]


def apply_pt(m, p):
    v = [float(p[0]), float(p[1]), float(p[2]), 1.0]
    return [sum(m[row][col] * v[col] for col in range(4)) for row in range(3)]


def envelope(bbox_min, bbox_max, m):
    corners = [
        [x, y, z]
        for x in (bbox_min[0], bbox_max[0])
        for y in (bbox_min[1], bbox_max[1])
        for z in (bbox_min[2], bbox_max[2])
    ]
    transformed = [apply_pt(m, pt) for pt in corners]
    return (
        [min(pt[i] for pt in transformed) for i in range(3)],
        [max(pt[i] for pt in transformed) for i in range(3)],
    )


def chain_deltas_correct(mats):
    identity = [[1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0]]
    prev = identity
    pose = identity
    out = []
    for absolute in mats:
        delta = mat_mul(absolute, mat_inv(prev))
        pose = mat_mul(delta, pose)
        out.append(pose)
        prev = absolute
    return out


def chain_deltas_wrong(mats):
    identity = [[1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0]]
    prev = identity
    pose = identity
    out = []
    for absolute in mats:
        delta = mat_mul(mat_inv(prev), absolute)
        pose = mat_mul(delta, pose)
        out.append(pose)
        prev = absolute
    return out


def _max_abs_diff(a, b) -> float:
    return max(abs(a[row][col] - b[row][col])
               for row in range(4) for col in range(4))


def _make_track(root: Path, object_ids: list[str]) -> dict[str, Any]:
    object_frames = []
    for frame_index, matrix in enumerate(ABSOLUTE_MATRICES, start=1):
        object_frames.append({
            "frame_index": frame_index,
            "object_transforms": [
                {
                    "object_id": object_id,
                    "source_state": {
                        "bbox_min": [0.0, 0.0, 0.0],
                        "bbox_max": [1.0, 1.0, 1.0],
                        "bbox_method": "tight_object",
                        "validation_strength": "tight_bbox",
                        "state_hash": f"state-{i}",
                    },
                    "transform": matrix,
                }
                for i, object_id in enumerate(object_ids)
            ],
        })
    return {
        "transform_semantics": "absolute_from_source",
        "fps": 24,
        "frame_count": len(ABSOLUTE_MATRICES),
        "animated_object_ids": object_ids,
        "camera_frames": [],
        "object_frames": object_frames,
        "derived_from": {},
    }


def make_compiled_package(tmp_path: Path, *, phase: str = "compiled",
                          tamper: str | None = None) -> Path:
    root = tmp_path / "take1"
    root.mkdir(parents=True)
    scene = root / "scene.3dm"
    prepared = root / "prepared.3dm"
    scene.write_bytes(b"scene-3dm")
    prepared.write_bytes(b"prepared-3dm")

    member_map = {
        "schema_version": 1,
        "metadata_kind": "director_member_map",
        "take_id": "take1",
        "package_id": "take1-abc123def456",
        "prepared_scene": {
            "file": "prepared.3dm",
            "sha256": sha256_file(prepared),
            "bytes": prepared.stat().st_size,
        },
        "actor_sets": [{
            "actor_set_id": "setA",
            "members": [
                {"actor_member_id": "setA_member_0000",
                 "created_object_ids": [_uuid(1)]},
                {"actor_member_id": "setA_member_0001",
                 "created_object_ids": [_uuid(2)]},
            ],
        }],
    }
    member_map_sha = write_canonical_json(root / "member_map.json", member_map)

    resolved_motion = {
        "schema_version": 1,
        "metadata_kind": "director_resolved_motion",
        "timeline": {"fps": 24, "frame_count": len(ABSOLUTE_MATRICES)},
        "groups": {"moving": [_uuid(1), _uuid(2)]},
        "motion": [{"target": "moving", "keyframes": [{"t": 1, "translate": [1, 0, 0]}]}],
    }
    resolved_sha = write_canonical_json(root / "resolved_motion.json", resolved_motion)

    track = _make_track(root, [_uuid(1), _uuid(2)])
    track["derived_from"] = {
        "resolved_motion_sha256": resolved_sha,
        "member_map_sha256": member_map_sha,
        "prepared_3dm_sha256": sha256_file(prepared),
    }
    track_sha = write_canonical_json(root / "track.json", track)

    status = {
        "schema_version": 1,
        "package_id": "take1-abc123def456",
        "take_id": "take1",
        "phase": phase,
        "heartbeat_utc": "2026-07-06T00:00:00+00:00",
        "evidence": {
            "member_map_sha256": member_map_sha,
            "resolved_motion_sha256": resolved_sha,
            "prepared_scene_sha256": sha256_file(prepared),
            "track_json_sha256": track_sha,
            "compile_provenance_sha256": "not-used-here",
        },
    }
    write_canonical_json(root / "status.json", status)

    if tamper == "track_hash":
        (root / "track.json").write_text(
            (root / "track.json").read_text(encoding="utf-8") + " ",
            encoding="utf-8")
    elif tamper == "missing_track":
        (root / "track.json").unlink()
    elif tamper == "member_map":
        (root / "member_map.json").write_text(
            (root / "member_map.json").read_text(encoding="utf-8") + " ",
            encoding="utf-8")
    elif tamper == "prepared":
        prepared.write_bytes(b"prepared-tampered")
    return root


def make_fake_native(root: Path, *, start_path: str | None = None,
                     modified: bool = False,
                     play_envelopes: list[dict[str, Any]] | None = None):
    prepared = str(root / "prepared.3dm")
    state = {
        "current_path": start_path or prepared,
        "modified": modified,
        "calls": [],
        "opens": [],
    }
    play_envelopes = list(play_envelopes or [{
        "success": True,
        "data": {
            "documentPath": prepared,
            "playedFrom": 0,
            "playedTo": 5,
            "frameCount": 5,
            "objectCount": 2,
            "probes": [{"frameIndex": 5, "objects": []}],
            "drift": {"tolerance": 0.01, "worstCentroidOffset": 0.0,
                      "worstDiagonalRatio": 1.0},
            "timing": {"totalMs": 12.5, "perFrameMs": [2.5] * 5},
        },
    }])

    async def fake(endpoint: str, method: str, data: dict | None = None, *,
                   port: int | None = None) -> dict:
        state["calls"].append((endpoint, method, data))
        if endpoint == "/document" and method == "GET":
            return {"success": True, "data": {
                "path": state["current_path"],
                "modified": state["modified"],
                "objectCount": 10,
            }}
        if endpoint == "/document/open" and method == "POST":
            state["opens"].append(data["path"])
            state["current_path"] = data["path"]
            state["modified"] = False
            return {"success": True, "data": {"path": data["path"]}}
        if endpoint == "/director/worker-play" and method == "POST":
            if not play_envelopes:
                raise AssertionError("unexpected extra worker-play call")
            return play_envelopes.pop(0)
        raise AssertionError(f"unexpected native call: {endpoint} {method}")

    fake.state = state
    return fake


async def expect_error(coro, code: str) -> dwp.DirectorWorkerPlayError:
    with pytest.raises(dwp.DirectorWorkerPlayError) as exc_info:
        await coro
    assert exc_info.value.code == code, exc_info.value
    return exc_info.value


async def test_wrong_phase_is_package_invalid(tmp_path):
    root = make_compiled_package(tmp_path, phase="prepared")
    fake = make_fake_native(root)
    await expect_error(
        dwp.play_take({"package_root": str(root)}, call_native=fake),
        "package_invalid")


async def test_track_hash_tamper_is_package_hash_mismatch(tmp_path):
    root = make_compiled_package(tmp_path, tamper="track_hash")
    fake = make_fake_native(root)
    await expect_error(
        dwp.play_take({"package_root": str(root)}, call_native=fake),
        "package_hash_mismatch")


async def test_missing_track_is_package_invalid(tmp_path):
    root = make_compiled_package(tmp_path, tamper="missing_track")
    fake = make_fake_native(root)
    await expect_error(
        dwp.play_take({"package_root": str(root)}, call_native=fake),
        "package_invalid")


async def test_dirty_nonpackage_doc_blocks_genuine_switch(tmp_path):
    root = make_compiled_package(tmp_path)
    fake = make_fake_native(root, start_path=LIVE_DOC_PATH, modified=True)
    await expect_error(
        dwp.play_take({"package_root": str(root)}, call_native=fake),
        "document_not_saved")
    assert fake.state["opens"] == []


async def test_dirty_package_scene_doc_is_discardable_on_genuine_switch(tmp_path):
    root = make_compiled_package(tmp_path)
    fake = make_fake_native(
        root, start_path=str(root / "scene.3dm"), modified=True)
    await dwp.play_take({"package_root": str(root)}, call_native=fake)
    assert fake.state["opens"] == [str(root / "prepared.3dm")]


async def test_reset_true_uses_fresh_reload(tmp_path):
    root = make_compiled_package(tmp_path)
    fake = make_fake_native(root)
    result = await dwp.play_take(
        {"package_root": str(root), "reset": True},
        call_native=fake)
    assert result["played_to"] == 5
    assert fake.state["opens"] == [str(root / "prepared.3dm")]


async def test_default_mode_does_not_reopen_active_prepared_doc(tmp_path):
    root = make_compiled_package(tmp_path)
    fake = make_fake_native(root, start_path=str(root / "prepared.3dm"))
    await dwp.play_take({"package_root": str(root)}, call_native=fake)
    assert fake.state["opens"] == []
    play_request = next(c[2] for c in fake.state["calls"]
                        if c[0] == "/director/worker-play")
    assert play_request["expectedDocumentPath"] == str(root / "prepared.3dm")


async def test_happy_path_appends_play_runs(tmp_path):
    root = make_compiled_package(tmp_path)
    fake = make_fake_native(root, play_envelopes=[
        {
            "success": True,
            "data": {
                "documentPath": str(root / "prepared.3dm"),
                "playedFrom": 0,
                "playedTo": 3,
                "frameCount": 5,
                "objectCount": 2,
                "probes": [],
                "drift": {"tolerance": 0.01, "worstCentroidOffset": 0.1,
                          "worstDiagonalRatio": 0.9},
                "timing": {"totalMs": 10.0, "perFrameMs": [3.0, 3.0, 4.0]},
            },
        },
        {
            "success": True,
            "data": {
                "documentPath": str(root / "prepared.3dm"),
                "playedFrom": 3,
                "playedTo": 5,
                "frameCount": 5,
                "objectCount": 2,
                "probes": [{"frameIndex": 5, "objects": []}],
                "drift": {"tolerance": 0.01, "worstCentroidOffset": 0.0,
                          "worstDiagonalRatio": 1.0},
                "timing": {"totalMs": 7.5, "perFrameMs": [3.5, 4.0]},
            },
        },
    ])

    first = await dwp.play_take(
        {"package_root": str(root), "play_to": 3},
        call_native=fake, now_fn=lambda: "2026-07-06T01:00:00+00:00")
    second = await dwp.play_take(
        {"package_root": str(root), "from_frame": 3, "probe_frames": [5]},
        call_native=fake, now_fn=lambda: "2026-07-06T02:00:00+00:00")

    assert first["run_index"] == 0
    assert first["played_to"] == 3
    assert first["timing_total_ms"] == 10.0
    assert second["run_index"] == 1
    assert second["probe_count"] == 1

    status = json.loads((root / "status.json").read_text(encoding="utf-8"))
    assert status["phase"] == "compiled"
    play_runs = status["evidence"]["play_runs"]
    assert len(play_runs) == 2
    assert play_runs[0]["played_to"] == 3
    assert play_runs[1]["played_from"] == 3


async def test_native_known_reason_passthrough_and_unknown_reason_wrapped(tmp_path):
    known_root = make_compiled_package(tmp_path / "known")
    known_fake = make_fake_native(known_root, play_envelopes=[
        {"success": False, "data": {"reason": "worker_scene_not_pristine",
                                    "objects": []}},
    ])
    await expect_error(
        dwp.play_take({"package_root": str(known_root)}, call_native=known_fake),
        "worker_scene_not_pristine")

    unknown_root = make_compiled_package(tmp_path / "unknown")
    unknown_fake = make_fake_native(unknown_root, play_envelopes=[
        {"success": False, "data": {"reason": "some_new_native_reason"}},
    ])
    await expect_error(
        dwp.play_take({"package_root": str(unknown_root)}, call_native=unknown_fake),
        "play_route_failed")


async def test_oracle_delta_chain_reproduces_absolute_matrices():
    produced = chain_deltas_correct(ABSOLUTE_MATRICES)
    assert max(_max_abs_diff(a, b)
               for a, b in zip(ABSOLUTE_MATRICES, produced)) < 1e-9


async def test_oracle_composition_order_is_distinguishable():
    wrong = chain_deltas_wrong(ABSOLUTE_MATRICES)
    assert max(_max_abs_diff(a, b)
               for a, b in zip(ABSOLUTE_MATRICES, wrong)) > 1e-2


async def test_oracle_envelope_prediction_matches_expected_numbers():
    bbox_min, bbox_max = envelope(
        [4.0, 0.0, 0.0], [5.0, 2.0, 3.0], ABSOLUTE_MATRICES[-1])
    assert bbox_min == pytest.approx(
        [11.778698714755, -3.707407282861, 1.25], abs=1e-9)
    assert bbox_max == pytest.approx(
        [15.0, -1.723542864692, 6.5], abs=1e-9)
