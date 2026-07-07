# Director v3 Per-Member Simulation Export — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Tasks 1–3 and 5 are Python (Codex-implementable, TDD). Tasks 4 and 6 are **live** Rhino/Grasshopper operations performed by the controller (Claude has the live connection); their "tests" are live-gate assertions, not pytest.

**Goal:** Render the CanvasDirector band-peel wave's per-member motion as a Director v3 take by harvesting per-member offsets + camera from the live canvas and feeding them through the existing package/prepare/compile/capture pipeline as ordinary per-member `motion.json` tracks.

**Architecture:** C42 "Director Band Peel Wave Preview" emits a per-frame samples JSON string (`{ids, z}`) on its `H` output (as-built — see Task 4; the original plan added a `Samples` pin, which RhinoCode won't create via SetSource); a new Python orchestrator scrubs the Clock 0→N, assembles a typed `director_member_motion_samples_v1` artifact, generates a per-member `motion.json` keyed by `actor_member_id`, and drives the existing pipeline unchanged (no compile/prepare/camera/native changes).

**Tech Stack:** Python 3 (`mcp_server/src/rook/`); pytest (`mcp_server/tests/`); RhinoCode C# script (live canvas edit); native HTTP routes via `httpx` (`/gh/*`, `/block/objects-detailed`, `/director/*`).

**Spec:** `docs/superpowers/specs/2026-07-07-director-v3-simulation-export-design.md`.

## Global Constraints

- Never mutate the Pearson document; only `prepared.3dm` copies inside the take package are written; the live doc is restored (`modified:False`) in a `finally`.
- `transform_semantics = "absolute_from_source"` end to end; a member offset is measured from rest and drops into the track as an absolute-from-rest translate.
- Indexing: N frames; `frame_index` is 1-based (`1..N`); `dz[p]` is the offset at `frame_index p+1`, `t = p/(N-1)`; `dz[0]` is rest (`t=0`). Matches the compiler grid (`director_motion.py`: `t = i/(N-1)`, `frame_index = i+1`).
- `frame_count >= 2` (hard input gate).
- Canonical JSON hashing = `json.dumps(payload, indent=2, sort_keys=True)` UTF-8 sha256 (matches `director_take_package.canonical_json_text`, director_take_package.py:49).
- `actor_member_id = f"{actor_set_id}_member_{index:04d}"` where `index`/`definition_object_id` come from `/block/objects-detailed` (matches director_take_package.py:157).
- Do NOT modify `director_worker_compile.py`, `director_worker_prepare.py`, `director_compiler.py`, `camera_planner.py`, `director_take_package.py`, or native code. The declarative path uses them unchanged. (A baked fallback exists in the spec §9 only if the motion round-trip gate fails; it is out of scope unless a gate forces it — escalate to the human.)
- Rhino launch/close is the user's; never launch/close/restart Rhino. Deploy is not required (no native change).

## Resolution chain (why no compile change) — reference, do not re-implement

`motion.json target = actor_member_id` → `prepare_take._derive_resolved_motion` builds `resolved_groups[actor_member_id] = created_object_ids` (director_worker_prepare.py:319,383) → `compile_take.expand_targets` expands that group (director_compiler.py:124). Unknown target fails in **prepare**; duplicate targets are **not** caught by prepare (it skips already-resolved targets) so the orchestrator preflight-rejects them.

## File Structure

- Create `mcp_server/src/rook/director_simulation_export.py` — all Python: typed artifact, invariants, member-id mapping, motion.json generation, verification seams, and the live orchestrator (scrub-collect + drive pipeline). One focused module; the pure functions are unit-tested, the live functions take an injected `call_native` for testability.
- Create `mcp_server/tests/test_director_simulation_export.py` — unit tests for every pure function (Tasks 1–3, and the pure parts of Task 5).
- Create `docs/superpowers/specs/artifacts/2026-07-07-c42-band-peel-wave-preview-samples.cs` — reference copy of the modified C42 source (Task 4), for reproducibility (C42 is a live prototype, not yet a template).
- Create `scripts/run_simulation_export.py` — thin live driver invoking the orchestrator (Task 6 live gate).

---

### Task 1: Typed artifact + structural invariants

**Files:**
- Create: `mcp_server/src/rook/director_simulation_export.py`
- Test: `mcp_server/tests/test_director_simulation_export.py`

**Interfaces:**
- Produces: `SimulationExportError(code, message)`; `canonical_json_text(payload)->str`; `ids_sha256(ids: list[str])->str`; `build_samples_artifact(ids: list[str], per_frame_z: list[list[float]], meta: dict)->dict`; `assert_samples_invariants(artifact: dict)->None`.

- [ ] **Step 1: Write the failing tests**

```python
# mcp_server/tests/test_director_simulation_export.py
import pytest
from rook import director_simulation_export as sx


def _meta():
    return {"actor_set_id": "actor_x", "source_block_name": "BLK",
            "source_top_level_object_id": "a28cbdb5", "fps": 24, "units": "millimeters",
            "component_provenance": {"component_nick": "Director Band Peel Wave Preview"}}


def test_build_samples_artifact_shape():
    art = sx.build_samples_artifact(["id0", "id1"], [[0.0, 0.0], [0.0, 5.0], [0.0, 10.0]], _meta())
    assert art["metadata_kind"] == "director_member_motion_samples_v1"
    assert art["schema_version"] == 1
    assert art["frame_count"] == 3
    assert art["transform_semantics"] == "absolute_from_source"
    assert art["sample_kind"] == "translate_z"
    assert art["id_space"] == "top_level_definition_object_id"
    assert art["ids"] == ["id0", "id1"]
    assert art["frames"][0] == {"frame_index": 1, "translate_z": [0.0, 0.0]}
    assert art["frames"][2] == {"frame_index": 3, "translate_z": [0.0, 10.0]}
    assert art["ids_sha256"] == sx.ids_sha256(["id0", "id1"])


def test_ids_sha256_order_sensitive_and_canonical():
    assert sx.ids_sha256(["a", "b"]) != sx.ids_sha256(["b", "a"])
    import hashlib, json
    expected = hashlib.sha256(json.dumps(["a", "b"], indent=2, sort_keys=True).encode("utf-8")).hexdigest()
    assert sx.ids_sha256(["a", "b"]) == expected


def test_invariants_pass_on_valid_artifact():
    art = sx.build_samples_artifact(["id0", "id1"], [[0.0, 0.0], [0.0, 5.0]], _meta())
    sx.assert_samples_invariants(art)  # no raise


def test_invariants_reject_frame_count_lt_2():
    art = sx.build_samples_artifact(["id0"], [[0.0]], _meta())
    with pytest.raises(sx.SimulationExportError) as ei:
        sx.assert_samples_invariants(art)
    assert ei.value.code == "frame_count_too_small"


def test_invariants_reject_duplicate_ids():
    art = sx.build_samples_artifact(["id0", "id0"], [[0.0, 0.0], [0.0, 5.0]], _meta())
    with pytest.raises(sx.SimulationExportError) as ei:
        sx.assert_samples_invariants(art)
    assert ei.value.code == "duplicate_member_id"


def test_invariants_reject_frame0_not_rest():
    art = sx.build_samples_artifact(["id0"], [[3.0], [5.0]], _meta())
    with pytest.raises(sx.SimulationExportError) as ei:
        sx.assert_samples_invariants(art)
    assert ei.value.code == "frame0_not_rest"


def test_invariants_reject_member_count_mismatch():
    art = sx.build_samples_artifact(["id0", "id1"], [[0.0, 0.0], [0.0]], _meta())
    with pytest.raises(sx.SimulationExportError) as ei:
        sx.assert_samples_invariants(art)
    assert ei.value.code == "member_count_mismatch"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd mcp_server && python -m pytest tests/test_director_simulation_export.py -v`
Expected: FAIL (`ModuleNotFoundError: rook.director_simulation_export`).

- [ ] **Step 3: Write the implementation**

```python
# mcp_server/src/rook/director_simulation_export.py
"""Director v3 per-member simulation export.

Harvests the CanvasDirector band-peel wave's per-member offsets + camera by
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
    """Typed failure with a stable code (mirrors the director_* error classes)."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def canonical_json_text(payload: Any) -> str:
    """Repo canonical JSON — matches director_take_package.canonical_json_text."""
    return json.dumps(payload, indent=2, sort_keys=True)


def ids_sha256(ids: list[str]) -> str:
    return hashlib.sha256(canonical_json_text(list(ids)).encode("utf-8")).hexdigest()


def build_samples_artifact(ids: list[str], per_frame_z: list[list[float]],
                           meta: dict[str, Any]) -> dict[str, Any]:
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
            "frame_count_too_small", f"frame_count must be >= 2, got {frame_count}")
    ids = artifact["ids"]
    if len(set(ids)) != len(ids):
        raise SimulationExportError(
            "duplicate_member_id", "ids contains a duplicate definition_object_id")
    frames = artifact["frames"]
    if len(frames) != frame_count:
        raise SimulationExportError(
            "frame_count_mismatch", f"{len(frames)} frames != frame_count {frame_count}")
    m = len(ids)
    for p, frame in enumerate(frames):
        if frame["frame_index"] != p + 1:
            raise SimulationExportError(
                "frame_index_disorder", f"frame {p}: frame_index {frame['frame_index']} != {p + 1}")
        if len(frame["translate_z"]) != m:
            raise SimulationExportError(
                "member_count_mismatch",
                f"frame {p}: translate_z len {len(frame['translate_z'])} != {m} ids")
    if any(z != 0 for z in frames[0]["translate_z"]):
        raise SimulationExportError(
            "frame0_not_rest", "frame 0 (frame_index 1) is not rest (translate_z has non-zero)")
    if artifact["ids_sha256"] != ids_sha256(ids):
        raise SimulationExportError("ids_hash_mismatch", "ids_sha256 does not match ids")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd mcp_server && python -m pytest tests/test_director_simulation_export.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/director_simulation_export.py mcp_server/tests/test_director_simulation_export.py
git commit -m "feat(director-sim): typed member-motion-samples artifact + invariants"
```

---

### Task 2: Member-id mapping + `motion.json` generation

**Files:**
- Modify: `mcp_server/src/rook/director_simulation_export.py` (append functions)
- Test: `mcp_server/tests/test_director_simulation_export.py` (append tests)

**Interfaces:**
- Consumes: `SimulationExportError`, `build_samples_artifact` (Task 1).
- Produces: `build_actor_member_ids(block_objects: list[dict], actor_set_id: str) -> tuple[dict[str,str], dict[str,int]]` (returns `{def_id: actor_member_id}`, `{def_id: def_index}`); `build_motion_json(artifact: dict, def_to_member_id: dict[str,str], fps: int) -> dict`.

- [ ] **Step 1: Write the failing tests**

```python
def test_build_actor_member_ids_formats_index_4wide():
    objs = [{"id": "d0", "index": 3}, {"id": "d1", "index": 239}]
    mid, idx = sx.build_actor_member_ids(objs, "actor_x")
    assert mid == {"d0": "actor_x_member_0003", "d1": "actor_x_member_0239"}
    assert idx == {"d0": 3, "d1": 239}


def test_build_actor_member_ids_rejects_duplicate_def_id():
    with pytest.raises(sx.SimulationExportError) as ei:
        sx.build_actor_member_ids([{"id": "d0", "index": 1}, {"id": "d0", "index": 2}], "actor_x")
    assert ei.value.code == "duplicate_definition_object_id"


def test_build_motion_json_per_member_dense_keyframes():
    art = sx.build_samples_artifact(["d0", "d1"], [[0.0, 0.0], [0.0, 6.0], [0.0, 12.0]], _meta())
    def_to_member = {"d0": "actor_x_member_0003", "d1": "actor_x_member_0239"}
    mj = sx.build_motion_json(art, def_to_member, fps=24)
    assert mj["timeline"] == {"fps": 24, "frame_count": 3}
    assert mj["groups"] == {}
    assert mj["default_easing"] == "linear"
    assert len(mj["motion"]) == 2
    track = next(t for t in mj["motion"] if t["target"] == "actor_x_member_0239")
    # p=0 (rest) omitted; keyframes at p=1 (t=0.5) and p=2 (t=1.0)
    assert track["keyframes"] == [
        {"t": 0.5, "translate": [0.0, 0.0, 6.0]},
        {"t": 1.0, "translate": [0.0, 0.0, 12.0]},
    ]


def test_build_motion_json_rejects_unknown_def_id():
    art = sx.build_samples_artifact(["dX"], [[0.0], [0.0]], _meta())
    with pytest.raises(sx.SimulationExportError) as ei:
        sx.build_motion_json(art, {"d0": "actor_x_member_0003"}, fps=24)
    assert ei.value.code == "nested_or_unknown_id"


def test_build_motion_json_rejects_duplicate_generated_member_id():
    # two distinct def ids that (pathologically) map to the same member id
    art = sx.build_samples_artifact(["d0", "d1"], [[0.0, 0.0], [0.0, 5.0]], _meta())
    with pytest.raises(sx.SimulationExportError) as ei:
        sx.build_motion_json(art, {"d0": "actor_x_member_0003", "d1": "actor_x_member_0003"}, fps=24)
    assert ei.value.code == "duplicate_member_id"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd mcp_server && python -m pytest tests/test_director_simulation_export.py -k "member_ids or motion_json" -v`
Expected: FAIL (`AttributeError: module ... has no attribute 'build_actor_member_ids'`).

- [ ] **Step 3: Write the implementation**

```python
def build_actor_member_ids(block_objects: list[dict[str, Any]],
                           actor_set_id: str) -> tuple[dict[str, str], dict[str, int]]:
    """From /block/objects-detailed objects → ({def_id: actor_member_id}, {def_id: def_index}).
    actor_member_id = f"{actor_set_id}_member_{index:04d}" (matches director_take_package.py:157)."""
    def_to_member: dict[str, str] = {}
    def_to_index: dict[str, int] = {}
    for obj in block_objects:
        def_id = obj.get("id")
        index = obj.get("index")
        if def_id is None or index is None:
            continue
        if def_id in def_to_member:
            raise SimulationExportError(
                "duplicate_definition_object_id", f"block object id {def_id} appears twice")
        def_to_member[def_id] = f"{actor_set_id}_member_{int(index):04d}"
        def_to_index[def_id] = int(index)
    return def_to_member, def_to_index


def build_motion_json(artifact: dict[str, Any], def_to_member_id: dict[str, str],
                      fps: int) -> dict[str, Any]:
    """Per-member declarative motion.json. Keyframes at t=p/(N-1) for p=1..N-1;
    p=0 (rest) omitted so compile prepends the implicit t=0 identity."""
    ids = artifact["ids"]
    frames = artifact["frames"]
    n = artifact["frame_count"]
    if n < 2:
        raise SimulationExportError("frame_count_too_small", f"frame_count {n} < 2")
    seen_members: set[str] = set()
    tracks: list[dict[str, Any]] = []
    for m, def_id in enumerate(ids):
        member_id = def_to_member_id.get(def_id)
        if member_id is None:
            raise SimulationExportError(
                "nested_or_unknown_id", f"def id {def_id} is not a top-level block member")
        if member_id in seen_members:
            raise SimulationExportError(
                "duplicate_member_id", f"actor_member_id {member_id} generated twice")
        seen_members.add(member_id)
        keyframes = [
            {"t": p / (n - 1), "translate": [0.0, 0.0, float(frames[p]["translate_z"][m])]}
            for p in range(1, n)
        ]
        tracks.append({"target": member_id, "keyframes": keyframes})
    return {"timeline": {"fps": fps, "frame_count": n}, "groups": {},
            "default_easing": "linear", "motion": tracks}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd mcp_server && python -m pytest tests/test_director_simulation_export.py -v`
Expected: PASS (12 tests total).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/director_simulation_export.py mcp_server/tests/test_director_simulation_export.py
git commit -m "feat(director-sim): actor_member_id mapping + per-member motion.json generation"
```

---

### Task 3: Verification seams (manifest drift + motion/camera round-trip)

**Files:**
- Modify: `mcp_server/src/rook/director_simulation_export.py` (append)
- Test: `mcp_server/tests/test_director_simulation_export.py` (append)

**Interfaces:**
- Consumes: `SimulationExportError`, `build_samples_artifact`.
- Produces: `assert_manifest_matches(scene_manifest, actor_set_id, def_to_member_id, def_to_index)->None`; `verify_motion_roundtrip(track, artifact, member_map, sample_def_ids, tol=1e-6)->None` (`member_map` is `{def_id: [created_object_id,...]}`, 1:N applied uniformly); `verify_camera_roundtrip(track, cam_keyframes, tol=1e-6)->None`.

- [ ] **Step 1: Write the failing tests**

```python
def _track_with(members):  # members: {frame_index: {created_id: dz}}
    object_frames = []
    for fi in sorted(members):
        transforms = [{"object_id": cid,
                       "transform": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, dz], [0, 0, 0, 1]]}
                      for cid, dz in members[fi].items()]
        object_frames.append({"frame_index": fi, "object_transforms": transforms})
    return {"object_frames": object_frames}


def test_manifest_matches_ok_and_drift():
    manifest = {"actor_sets": [{"actor_set_id": "actor_x", "members": [
        {"definition_object_id": "d0", "definition_object_index": 3, "actor_member_id": "actor_x_member_0003"}]}]}
    sx.assert_manifest_matches(manifest, "actor_x", {"d0": "actor_x_member_0003"}, {"d0": 3})
    bad = {"actor_sets": [{"actor_set_id": "actor_x", "members": [
        {"definition_object_id": "d0", "definition_object_index": 99, "actor_member_id": "actor_x_member_0003"}]}]}
    with pytest.raises(sx.SimulationExportError) as ei:
        sx.assert_manifest_matches(bad, "actor_x", {"d0": "actor_x_member_0003"}, {"d0": 3})
    assert ei.value.code == "manifest_drift"


def test_motion_roundtrip_ok_including_nested_member():
    # d0 -> one created (c0); dNest -> two created (cA, cB) — nested applies uniformly
    art = sx.build_samples_artifact(["d0", "dNest"], [[0.0, 0.0], [0.0, 7.0]], _meta())
    member_map = {"d0": ["c0"], "dNest": ["cA", "cB"]}
    track = _track_with({1: {"c0": 0.0, "cA": 0.0, "cB": 0.0}, 2: {"c0": 0.0, "cA": 7.0, "cB": 7.0}})
    sx.verify_motion_roundtrip(track, art, member_map, ["d0", "dNest"])  # no raise


def test_motion_roundtrip_mismatch():
    art = sx.build_samples_artifact(["d0"], [[0.0], [9.0]], _meta())
    track = _track_with({1: {"c0": 0.0}, 2: {"c0": 8.0}})  # frame 2: 8 != sampled 9
    with pytest.raises(sx.SimulationExportError) as ei:
        sx.verify_motion_roundtrip(track, art, {"d0": ["c0"]}, ["d0"])
    assert ei.value.code == "motion_roundtrip_mismatch"


def test_camera_roundtrip_ok_and_length_mismatch():
    cam = {"projection": "perspective", "location": [1, 2, 3], "target": [0, 0, 0],
           "up": [0, 0, 1], "lens_length": 50}
    kfs = [{"frame_index": 1, "source": {"kind": "explicit_camera", "camera": cam}},
           {"frame_index": 2, "source": {"kind": "explicit_camera", "camera": cam}}]
    track = {"camera_frames": [{"frame_index": 1, "camera": cam}, {"frame_index": 2, "camera": cam}]}
    sx.verify_camera_roundtrip(track, kfs)  # no raise
    with pytest.raises(sx.SimulationExportError) as ei:
        sx.verify_camera_roundtrip({"camera_frames": [{"frame_index": 1, "camera": cam}]}, kfs)
    assert ei.value.code == "camera_frame_count_mismatch"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd mcp_server && python -m pytest tests/test_director_simulation_export.py -k "manifest or roundtrip or camera" -v`
Expected: FAIL (functions undefined).

- [ ] **Step 3: Write the implementation**

```python
def assert_manifest_matches(scene_manifest: dict[str, Any], actor_set_id: str,
                            def_to_member_id: dict[str, str],
                            def_to_index: dict[str, int]) -> None:
    """Package-manifest drift gate (spec §8): the manifest is the authority."""
    actor_sets = scene_manifest.get("actor_sets") or []
    manifest_set = next((a for a in actor_sets if a.get("actor_set_id") == actor_set_id), None)
    if manifest_set is None:
        raise SimulationExportError(
            "manifest_actor_set_missing", f"actor set {actor_set_id} not in scene_manifest")
    by_def = {m["definition_object_id"]: m for m in (manifest_set.get("members") or [])}
    for def_id, member_id in def_to_member_id.items():
        m = by_def.get(def_id)
        if m is None:
            raise SimulationExportError("manifest_member_missing", f"def id {def_id} absent from manifest")
        if m.get("actor_member_id") != member_id:
            raise SimulationExportError(
                "manifest_drift", f"{def_id}: manifest member {m.get('actor_member_id')} != {member_id}")
        if m.get("definition_object_index") != def_to_index[def_id]:
            raise SimulationExportError(
                "manifest_drift", f"{def_id}: manifest index {m.get('definition_object_index')} != {def_to_index[def_id]}")


def verify_motion_roundtrip(track: dict[str, Any], artifact: dict[str, Any],
                            member_map: dict[str, list[str]], sample_def_ids: list[str],
                            tol: float = 1e-6) -> None:
    """For each sampled member, every created child's transform[2][3] == the sampled z, per frame."""
    ids = artifact["ids"]
    id_pos = {d: i for i, d in enumerate(ids)}
    frames_by_index = {f["frame_index"]: f for f in track["object_frames"]}
    for def_id in sample_def_ids:
        if def_id not in id_pos:
            raise SimulationExportError("roundtrip_unknown_member", f"{def_id} not in artifact ids")
        created = member_map.get(def_id) or []
        if not created:
            raise SimulationExportError("roundtrip_no_created", f"{def_id} has no created objects")
        pos = id_pos[def_id]
        for p, art_frame in enumerate(artifact["frames"]):
            expected = float(art_frame["translate_z"][pos])
            tframe = frames_by_index[p + 1]
            xf_by_obj = {t["object_id"]: t["transform"] for t in tframe["object_transforms"]}
            for cid in created:
                got = float(xf_by_obj[cid][2][3])
                if abs(got - expected) > tol:
                    raise SimulationExportError(
                        "motion_roundtrip_mismatch",
                        f"{def_id}->{cid} frame {p + 1}: transform z {got} != sampled {expected}")


def verify_camera_roundtrip(track: dict[str, Any], cam_keyframes: list[dict[str, Any]],
                            tol: float = 1e-6) -> None:
    cam_frames = track["camera_frames"]
    if len(cam_frames) != len(cam_keyframes):
        raise SimulationExportError(
            "camera_frame_count_mismatch",
            f"{len(cam_frames)} camera_frames != {len(cam_keyframes)} harvested")
    for p, (cf, kf) in enumerate(zip(cam_frames, cam_keyframes)):
        if cf.get("frame_index") != p + 1:
            raise SimulationExportError(
                "camera_frame_disorder", f"camera_frames[{p}].frame_index {cf.get('frame_index')} != {p + 1}")
        want = kf["source"]["camera"]
        got = cf["camera"]
        for key in ("location", "target", "up"):
            for a, b in zip(got[key], want[key]):
                if abs(float(a) - float(b)) > tol:
                    raise SimulationExportError(
                        "camera_roundtrip_mismatch", f"camera frame {p + 1} {key}: {got[key]} != {want[key]}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd mcp_server && python -m pytest tests/test_director_simulation_export.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/director_simulation_export.py mcp_server/tests/test_director_simulation_export.py
git commit -m "feat(director-sim): manifest-drift + motion/camera round-trip verification seams"
```

---

### Task 4: C42 canvas edit — packed samples on `H` (LIVE — controller) [AS-BUILT]

**This is a live Grasshopper edit, not a pytest task**, performed by the controller (Claude); a Codex subagent cannot apply it.

**AS-BUILT correction:** the original plan added a dedicated `Samples` output pin. That does **not** work — `gh_set_script`/`SetSource` recompiles and RhinoCode regenerates the RunScript signature from the component's *existing* pins, dropping the added param (the body then references an undefined variable → compile error → empty outputs; "add pins = recreate"). Live pin surgery on the hand-built canvas is risky, so the shipped edit **repurposes the existing `H` output** to carry the packed samples JSON (its heights list was unreadable anyway under the 5-item preview cap). See spec §5.

**Files:**
- Create: `docs/superpowers/specs/artifacts/2026-07-07-c42-band-peel-wave-preview-samples.cs` (full modified source, live-applied)

**Edits to the current C42 source** (read live via `gh_set_script(guid=<wave>)` GET; wave instance guid on this canvas = `5e5398db-3031-44cb-af74-b1ce77f40599`):
1. Add field to `CachedMember`: `public string DefId;`
2. In `BuildCache`'s `cache.Members.Add(new CachedMember { ... })`, add `DefId = source.Id.ToString(),`.
3. Replace `H = heights;` with the packed-JSON emit — `System.Text.Json` is already imported; **no** `StringBuilder`/`Escape`/`Num` (those helpers do not exist in this script) and **no** new `using`:
   ```csharp
   var sampleIds = new string[cache.Members.Count];
   for (int i = 0; i < cache.Members.Count; i++)
       sampleIds[i] = cache.Members[i].DefId;
   H = System.Text.Json.JsonSerializer.Serialize(new { ids = sampleIds, z = heights });
   ```
   `G` (geometry → Preview) and `Info` are unchanged; **no signature/pin change → no wire loss.**

- [ ] **Step 1: Apply + verify live (hard gate)**

Read the current source, apply the edits, save the full modified source to the reference artifact, then `gh_set_script(guid=<wave>, script=<modified>)`. Force a solve (`POST /gh/value {guid: FrameIn, value: 0}`) and read `H` via `/gh/inspect-output?guid=<wave>&param=H`: `json.loads(preview[0])` must give `len(ids)==len(z)` (338), `ids[0]` a valid GUID. Confirm `G` still produces geometry and the camera still solves. Verify motion at a PingPong peak (FrameIn=30 → `z` lifts to `maxH`). Restore FrameIn=0. `gh_undo` is the rollback.

- [ ] **Step 2: Commit the reference artifact**

```bash
git add docs/superpowers/specs/artifacts/2026-07-07-c42-band-peel-wave-preview-samples.cs
git commit -m "feat(director-sim): C42 samples output on H (reference source) — live-applied"
```

---

### Task 5: Orchestrator — scrub-collect + drive the pipeline

**Files:**
- Modify: `mcp_server/src/rook/director_simulation_export.py` (append)
- Test: `mcp_server/tests/test_director_simulation_export.py` (append — `harvest_samples` with a mocked `call_native`)

**Interfaces:**
- Consumes: all Task 1–3 functions; the existing modules `director_take_package.package_take`, `director_worker_prepare.prepare_take`, `director_worker_compile.compile_take`, `director_worker_capture.capture_take` (async, `call_native=` injectable), and native routes `/block/objects-detailed`, `/gh/query`, `/gh/value`, `/gh/inspect-output`, `/document`, `/document/open`, `/director/video-assemble`.
- Produces: `resolve_canvas_roles(call_native)->dict` (`{frame_in, camera_ctrl, wave}` instance guids); `async harvest_samples(call_native, roles, frame_count, clock_denominator)->tuple[list[str], list[list[float]], list[dict]]` (ids, per_frame_z, cam_keyframes); `async run_simulation_export(args, *, call_native)->dict`.

**Reference — the proven harvest primitives** (from `scratchpad/render_from_canvas.py`, camera bake): `POST /gh/value {guid, value}` sets a slider; `GET /gh/inspect-output {guid, param}` returns `{preview:[...]}` (single-item string in `preview[0]`); staleness guard reads `local_t` from the camera state. Camera source kinds and dense keyframes flow through `package_take(camera=...)` → `build_camera_frames` unchanged (spec §7d).

- [ ] **Step 1: Write the failing test (harvest with mocked call_native)**

```python
import asyncio
import json as _json


class _FakeNative:
    """Simulates /gh/value + /gh/inspect-output for a 2-member, 3-frame wave."""
    def __init__(self):
        self.frame_in = 0
        # z(member1) ramps 0 -> 5 -> 10 with FrameIn; member0 static 0
        self._z = {0: [0.0, 0.0], 120: [0.0, 5.0], 240: [0.0, 10.0]}

    async def __call__(self, endpoint, method="GET", data=None, *, port=None):
        if endpoint == "/gh/value" and method == "POST":
            self.frame_in = data["value"]
            return {"success": True, "data": {}}
        if endpoint.startswith("/gh/inspect-output"):
            # endpoint carries guid+param as query in this fake; inspect data arg
            param = data["param"] if data else None
            local_t = self.frame_in / 240.0
            if param == "H":  # wave emits packed samples JSON on the H output
                z = self._z[self.frame_in]
                payload = _json.dumps({"ids": ["d0", "d1"], "z": z})
                return {"success": True, "data": {"preview": [payload]}}
            if param == "Camera":
                cam = {"projection": "perspective", "location": [self.frame_in, 0, 0],
                       "target": [0, 0, 0], "up": [0, 0, 1], "lens_length": 50, "local_t": local_t}
                return {"success": True, "data": {"preview": [_json.dumps(cam)]}}
        raise AssertionError(f"unexpected {endpoint} {data}")


def test_harvest_samples_maps_frames_and_hashes_ids():
    fake = _FakeNative()
    roles = {"frame_in": "fi", "camera_ctrl": "cc", "wave": "wv"}
    ids, per_frame_z, cams = asyncio.run(
        sx.harvest_samples(fake, roles, frame_count=3, clock_denominator=240))
    assert ids == ["d0", "d1"]
    assert per_frame_z == [[0.0, 0.0], [0.0, 5.0], [0.0, 10.0]]      # frames p=0,1,2 -> FrameIn 0,120,240
    assert [c["frame_index"] for c in cams] == [1, 2, 3]
    assert cams[1]["source"]["camera"]["location"] == [120, 0, 0]
    assert fake.frame_in == 0                                        # restored


def test_harvest_samples_rejects_ids_drift():
    fake = _FakeNative()
    # corrupt ids at the last frame
    orig = fake.__call__
    async def drift(endpoint, method="GET", data=None, *, port=None):
        r = await orig(endpoint, method, data, port=port)
        if data and data.get("param") == "H" and fake.frame_in == 240:
            r = {"success": True, "data": {"preview": [_json.dumps({"ids": ["d0", "dX"], "z": [0.0, 10.0]})]}}
        return r
    with pytest.raises(sx.SimulationExportError) as ei:
        asyncio.run(sx.harvest_samples(drift, {"frame_in": "fi", "camera_ctrl": "cc", "wave": "wv"},
                                       frame_count=3, clock_denominator=240))
    assert ei.value.code == "ids_unstable"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd mcp_server && python -m pytest tests/test_director_simulation_export.py -k harvest -v`
Expected: FAIL (`harvest_samples` undefined).

- [ ] **Step 3: Write the implementation**

```python
async def _gh_set_value(call_native, guid: str, value: Any) -> None:
    r = await call_native("/gh/value", "POST", {"guid": guid, "value": value})
    if not r.get("success"):
        raise SimulationExportError("gh_set_value_failed", f"{guid}={value}: {r.get('data')}")


async def _gh_read_output(call_native, guid: str, param: str) -> Any:
    r = await call_native("/gh/inspect-output", "GET", {"guid": guid, "param": param})
    d = r.get("data", r)
    preview = d.get("preview") if isinstance(d, dict) else None
    if not preview:
        raise SimulationExportError("gh_output_empty", f"{guid}.{param} has no data")
    return json.loads(preview[0])


async def harvest_samples(call_native, roles: dict[str, str], frame_count: int,
                          clock_denominator: float) -> tuple[list[str], list[list[float]], list[dict[str, Any]]]:
    if frame_count < 2:
        raise SimulationExportError("frame_count_too_small", f"frame_count {frame_count} < 2")
    ids: list[str] | None = None
    ids_hash: str | None = None
    per_frame_z: list[list[float]] = []
    cam_keyframes: list[dict[str, Any]] = []
    try:
        for p in range(frame_count):
            t = p / (frame_count - 1)
            frame_in = round(t * clock_denominator)
            await _gh_set_value(call_native, roles["frame_in"], frame_in)
            # Read camera FIRST: its local_t guard confirms this frame's solve
            # completed, which then guarantees the H read below is from the same
            # fresh solve (H carries no freshness marker).
            cam = await _gh_read_output(call_native, roles["camera_ctrl"], "Camera")
            local_t = float(cam.get("local_t"))
            if abs(local_t - frame_in / clock_denominator) > 1e-3:
                raise SimulationExportError("camera_stale", f"frame {p}: local_t {local_t} != {frame_in/clock_denominator}")
            cam_keyframes.append({"frame_index": p + 1, "source": {"kind": "explicit_camera", "camera": {
                "projection": cam.get("projection", "perspective"),
                "location": cam["location"], "target": cam["target"],
                "up": cam.get("up", [0.0, 0.0, 1.0]), "lens_length": cam.get("lens_length", 50.0)}}})

            # Wave samples are emitted on the H output (packed JSON), not a Samples pin.
            samples = await _gh_read_output(call_native, roles["wave"], "H")
            frame_ids = list(samples["ids"])
            frame_z = [float(v) for v in samples["z"]]
            if len(frame_ids) != len(frame_z):
                raise SimulationExportError("samples_len_mismatch",
                                            f"frame {p}: {len(frame_ids)} ids != {len(frame_z)} z")
            h = ids_sha256(frame_ids)
            if ids is None:
                ids, ids_hash = frame_ids, h
                if len(set(ids)) != len(ids):
                    raise SimulationExportError("duplicate_member_id", "samples ids has duplicates")
            elif h != ids_hash:
                raise SimulationExportError("ids_unstable", f"frame {p}: samples ids changed mid-scrub")
            per_frame_z.append(frame_z)
    finally:
        await _gh_set_value(call_native, roles["frame_in"], 0)
    return ids, per_frame_z, cam_keyframes


async def resolve_canvas_roles(call_native) -> dict[str, str]:
    """Resolve instance guids of the three canvas roles via /gh/query.
    VERIFIED shape (2026-07-07): {"data": {"objectCount": int,
    "objects": [{"guid", "nickName", "type", "category", "name", "position", "size", ...}]}}.
    Match by EXACT nickName + type: a 'Camera Controller' substring also matches a GH_Group
    'Director Camera Controller v0', so the type filter (CSharpComponent) is required to exclude it.
    Fails loudly unless exactly one match. Verified guids on the current canvas:
    FrameIn=c70b8895 (GH_NumberSlider), Director Camera Controller=224e065e (CSharpComponent),
    Director Band Peel Wave Preview=5e5398db (CSharpComponent)."""
    objs = (await call_native("/gh/query", "GET", None))["data"]["objects"]
    def _find(nick: str, typ: str, role: str) -> str:
        hits = [o for o in objs if o.get("nickName") == nick and o.get("type") == typ]
        if len(hits) != 1:
            raise SimulationExportError("canvas_role_unresolved", f"{role}: found {len(hits)} candidates")
        return hits[0]["guid"]
    return {
        "frame_in": _find("FrameIn", "GH_NumberSlider", "FrameIn slider"),
        "camera_ctrl": _find("Director Camera Controller", "CSharpComponent", "Camera Controller"),
        "wave": _find("Director Band Peel Wave Preview", "CSharpComponent", "Band Peel Wave Preview"),
    }
```

**`call_native` contract (used by the harvest helpers and unit-test fake):** GET passes `data`
as **query params**, POST passes `data` as the JSON body. The live driver (Task 6) must define
it accordingly (see Task 6 Step-0 code): `client.get(url, params=data or None)` /
`client.post(url, json=data or {})`. This is why `_gh_read_output(call_native, guid, param)`
passes `{"guid", "param"}` on a GET and `resolve_canvas_roles` passes `None`.

- [ ] **Step 4: Add `run_simulation_export` (orchestration wiring)**

```python
async def run_simulation_export(args: dict[str, Any], *, call_native) -> dict[str, Any]:
    """Harvest → artifact → motion.json → package/prepare/compile (+gates) → CAPTURE only.
    Assembly is the live driver's job (Task 6 calls director_video.assemble_director_video).
    args: {take_id, actor_set_id, block_name, source_top_level_object_id, output_root,
           frame_count, fps, units, display_modes, capture_mode, resolution, clock_denominator}."""
    from rook import director_take_package as dtp
    from rook import director_worker_prepare as dprep
    from rook import director_worker_compile as dwc
    from rook import director_worker_capture as dwcap

    # 0. Guard: live doc must be unmodified (we restore it at the end).
    before = (await call_native("/document", "GET"))["data"]
    original = before.get("path") or ""
    if before.get("modified"):
        raise SimulationExportError("live_doc_modified", "save the live document before rendering")

    try:
        # 1. Harvest.
        roles = await resolve_canvas_roles(call_native)
        ids, per_frame_z, cam_keyframes = await harvest_samples(
            call_native, roles, args["frame_count"], args["clock_denominator"])
        meta = {"actor_set_id": args["actor_set_id"], "source_block_name": args["block_name"],
                "source_top_level_object_id": args["source_top_level_object_id"],
                "fps": args["fps"], "units": args["units"],
                "component_provenance": {"component_nick": "Director Band Peel Wave Preview",
                                         "clock_denominator": args["clock_denominator"]}}
        artifact = build_samples_artifact(ids, per_frame_z, meta)
        assert_samples_invariants(artifact)

        # 2. def_id -> actor_member_id (reproduce the package builder's assignment).
        block = (await call_native("/block/objects-detailed", "POST", {"name": args["block_name"]}))["data"]
        def_to_member, def_to_index = build_actor_member_ids(block["objects"], args["actor_set_id"])
        for d in ids:
            if d not in def_to_member:
                raise SimulationExportError("nested_or_unknown_id", f"{d} not a top-level member of {args['block_name']}")
        motion = build_motion_json(artifact, def_to_member, args["fps"])

        # 3. Package (dense camera flows through unchanged).
        pkg = await dtp.package_take({
            "take_id": args["take_id"], "output_root": args["output_root"],
            "actor_sets": [{"actor_set_id": args["actor_set_id"], "block_name": args["block_name"],
                            "source_top_level_object_id": args["source_top_level_object_id"]}],
            "motion": motion, "camera": {"strategy": "keyframes", "keyframes": cam_keyframes},
            "display_modes": args["display_modes"],
        }, call_native=call_native)
        package_root = pkg["package_root"]

        # 3a. Manifest drift gate (manifest is authority).
        manifest = json.loads((__import__("pathlib").Path(package_root) / "scene_manifest.json").read_text())
        subset = {d: def_to_member[d] for d in ids}
        subset_idx = {d: def_to_index[d] for d in ids}
        assert_manifest_matches(manifest, args["actor_set_id"], subset, subset_idx)

        # 4. Prepare + compile.
        prep = await dprep.prepare_take({"package_root": package_root}, call_native=call_native)
        comp = await dwc.compile_take({"package_root": package_root}, call_native=call_native)

        # 4a. Round-trip gates (motion + camera) against the compiled track.
        track = json.loads((__import__("pathlib").Path(package_root) / "track.json").read_text())
        member_map = _member_map_by_def_id(package_root)
        sample_def_ids = _pick_sample_members(ids, member_map)
        verify_motion_roundtrip(track, artifact, member_map, sample_def_ids)
        verify_camera_roundtrip(track, cam_keyframes)

        # 5. Capture only (assembly is the driver's job — director_video.assemble_director_video).
        cap = await dwcap.capture_take({
            "package_root": package_root,
            "passes": [{"type": "display_mode", "pass_id": "sim", "display_mode": args["capture_mode"]}],
            "resolution": args["resolution"],
        }, call_native=call_native)
        return {"package_root": package_root, "artifact": artifact,
                "prepared": prep.get("phase"), "compiled": comp.get("phase"),
                "capture": cap["passes"][0]}
    finally:
        await call_native("/document/open", "POST", {"path": original})


def _member_map_by_def_id(package_root: str) -> dict[str, list[str]]:
    """Read package_root/member_map.json → {definition_object_id: [created_object_id,...]}.
    prepare_take's RETURN carries only actor-set summaries (director_worker_prepare.py:471);
    the per-member mapping lives in the member_map.json artifact (written at :458),
    shape {actor_sets: [{members: [{definition_object_id, created_object_ids, ...}]}]}."""
    from pathlib import Path
    mm = json.loads((Path(package_root) / "member_map.json").read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    for actor in mm.get("actor_sets") or []:
        for m in actor.get("members") or []:
            out[m["definition_object_id"]] = list(m.get("created_object_ids") or [])
    return out


def _pick_sample_members(ids: list[str], member_map: dict[str, list[str]]) -> list[str]:
    """Representative round-trip set: a 1:1 member, plus any nested (1:N) member present."""
    picks = [ids[0]]
    nested = next((d for d in ids if len(member_map.get(d) or []) > 1), None)
    if nested and nested not in picks:
        picks.append(nested)
    if len(ids) > 1 and ids[-1] not in picks:
        picks.append(ids[-1])
    return picks
```

> **Read-model shapes (verified, do not re-derive):** `member_map.json` and `track.json`
> are both written at `package_root` by prepare/compile (director_worker_prepare.py:458,
> director_worker_compile.py:380). `member_map.json` is `{actor_sets:[{members:[{
> definition_object_id, created_object_ids}]}]}`; `track.json` is `{object_frames:[{
> frame_index, object_transforms:[{object_id, transform}]}], camera_frames:[{frame_index,
> camera}]}` (spec §consumption). The functions above read exactly these.

- [ ] **Step 5: Run all unit tests**

Run: `cd mcp_server && python -m pytest tests/test_director_simulation_export.py -v`
Expected: PASS (all tests, including the two `harvest_samples` tests).

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/director_simulation_export.py mcp_server/tests/test_director_simulation_export.py
git commit -m "feat(director-sim): scrub-collect harvest + orchestration wiring"
```

---

### Task 6: Live gate — render the Pearson mullion wave (LIVE — controller)

**This is a live end-to-end gate, not a pytest task.** Prerequisites: Rhino open with the Pearson doc and the animation canvas loaded (shipped run used `animation test_smoke-02.gh`); Task 4 applied (C42 emits samples on `H` live); the live doc saved (`modified:False`).

**Files:**
- Create: `scripts/run_simulation_export.py` — a thin live driver. It defines `call_native`
  (GET → query params; POST → JSON body), builds `args`, runs `run_simulation_export`, then
  assembles via the sanctioned `director_video.assemble_director_video` wrapper (which reads the
  run's `manifest.json`/`status.json` and validates policy — NOT the raw `/director/video-assemble`
  route).

```python
# scripts/run_simulation_export.py (live gate driver)
import sys, asyncio, uuid
sys.path.insert(0, r"C:\Users\aryan\source\repos\Rook\mcp_server\src")
import httpx
from rook.bridge import get_rhino_host
from rook import director_simulation_export as sx
from rook import director_video

BASE = get_rhino_host()

async def call_native(endpoint, method="GET", data=None, *, port=None):
    async with httpx.AsyncClient(timeout=1800.0) as c:
        resp = (await c.get(f"{BASE}{endpoint}", params=data or None) if method == "GET"
                else await c.post(f"{BASE}{endpoint}", json=data or {}))
    return resp.json()

async def main():
    units = (await call_native("/document", "GET"))["data"].get("units", "millimeters")
    args = {
        "take_id": f"sim_{uuid.uuid4().hex[:6]}",
        "actor_set_id": "actor_a28cbdb551fa",
        "block_name": "3D_BLOCK_ARCH_ROOF_0502 UPLIFT ROOF - VERTICAL",
        "source_top_level_object_id": "a28cbdb5-51fa-46b2-b18b-ab880b54ded7",
        "output_root": r"C:\Users\aryan\AppData\Local\Temp\claude\...\scratchpad\sim_take",
        "frame_count": 48, "fps": 24, "units": units, "clock_denominator": 240,
        "display_modes": ["Shaded"], "capture_mode": "8bc8debe-...",  # Shaded UUID
        "resolution": {"width": 1280, "height": 720},
    }
    result = await sx.run_simulation_export(args, call_native=call_native)
    run_root = result["capture"]["run_root"]
    aenv = await director_video.assemble_director_video({"run_root": run_root}, call_native=call_native)
    print("VIDEO:", aenv)

asyncio.run(main())
```

- [ ] **Step 1: Confirm connection + doc pristine**

`rhino_ping` → `pong`; `/document` → `modified: False`; `gh_status` → canvas loaded, C42 emits samples on `H` (Task 4).

- [ ] **Step 2: Run the driver for N=48**

Run: `python scripts/run_simulation_export.py`
Expected: package → prepare (≈338 mullions animate, others static) → compile → **motion round-trip gate passes** → **camera round-trip gate passes** → capture 48 → **live doc restored `modified:False`** (in `run_simulation_export`'s `finally`) → driver assembles the video (`assemble_director_video`, reads frames from disk; Rhino stays alive for the encoder).

- [ ] **Step 3: Assert the gate results**

- Video exists, non-empty, under `%LOCALAPPDATA%/Rook/rookvision_director/takes/<take_id>/sim/videos/take.mp4`.
- `run_simulation_export` returned without raising (all invariants + drift + round-trip gates green).
- Visual check: mullions peel band-by-band (a wave, **not** a uniform lift); camera follows the path.
- Pearson on-disk `last_written` unchanged (copy model held).

- [ ] **Step 4: Commit the driver**

```bash
git add scripts/run_simulation_export.py
git commit -m "test(director-sim): live gate driver — Pearson mullion wave 48f"
```

---

## Self-Review

**Spec coverage:** §2 identity (Tasks 2/4 use def_id top-level + `_member_{index:04d}`); §3 resolution chain (Global Constraints + Task 2 targets); §4 scope (all tasks; no compile change); §5 C42 samples-on-`H` (Task 4); §6 typed artifact (Task 1); §7 orchestrator (Task 5) + camera dense keyframes (Task 5 harvest + `package_take` camera); §8 gates — frame_count>=2 (Task 1), len/stability/dup/top-level (Tasks 1/2/5), manifest drift (Task 3/5), motion + camera round-trip (Task 3/5), frame-0-rest (Task 1); §9 nested uniform (Task 3 `verify_motion_roundtrip` + Task 5 `_member_map_by_def_id`), baked fallback (Global Constraints — escalate); §10 tests (Tasks 1–3, 5) + live gate (Task 6); §11 risks (C42 pin edit Task 4, throughput 48f Task 6). No gaps.

**Placeholder scan:** no TBD/TODO, no live-discovery steps. The formerly-hedged read-model shapes are now pinned with file:line evidence: `/gh/query` → `{data:{objects:[{guid,nickName,type}]}}` (verified live 2026-07-07, exact role guids in `resolve_canvas_roles`); `member_map.json` at `package_root` (director_worker_prepare.py:458); `track.json` at `package_root` (director_worker_compile.py:380). The `call_native` GET→query-param / POST→body contract is pinned in the Task 6 driver and matched by the harvest unit-test fake.

**Type consistency:** `SimulationExportError(code,message)` used uniformly; `build_samples_artifact(ids, per_frame_z, meta)` / `build_motion_json(artifact, def_to_member_id, fps)` / `verify_motion_roundtrip(track, artifact, member_map, sample_def_ids)` signatures match across tasks; `member_map` is `{def_id: [created_id,...]}` in Task 3 and produced identically by `_member_map_by_def_id` in Task 5; `cam_keyframes` shape (`{frame_index, source:{kind:"explicit_camera", camera}}`) matches between `harvest_samples` (Task 5) and `verify_camera_roundtrip` (Task 3).
