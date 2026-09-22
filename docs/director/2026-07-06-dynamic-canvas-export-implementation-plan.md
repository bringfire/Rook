# Director Dynamic Canvas Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Director v1 dynamic canvas export path defined in `docs/director/2026-07-06-dynamic-canvas-export-materialization-spec.md`, ending with separate Pearson, assembler, and 512-object final-capture proofs.

**Architecture:** Grasshopper remains the authoring coordinator and emits schema 2 authoring/take data only. Python owns extraction, validation, actor-binding reconciliation, capture-scene preparation orchestration, compile-request persistence, and proof reporting. Native Rhino routes provide current-document facts and document mutation primitives where Rhino SDK access is required.

**Tech Stack:** Grasshopper C# template scripts, managed CanvasDirector extraction, Python MCP/server modules, native Rhino 8 C++ handlers, `nlohmann::json`, existing Rook native HTTP/main-thread dispatch patterns, pytest, live Rhino integration tests.

---

## Source Spec

Primary spec:

- `docs/director/2026-07-06-dynamic-canvas-export-materialization-spec.md`

Implementation must preserve the claim matrix from the spec:

| Claim | Required proof |
| --- | --- |
| Pearson production path support | Pearson proof: one real actor set, 338 members, target frame count |
| Export assembler completeness | Assembler proof: two disjoint actor sets through assembly, ownership validation, materialization mapping, compile request generation, and final capture/replay proof |
| 512-object v1 final-capture support | 512 cap proof: synthetic 512 real capture objects with duplicated renderable geometry, source-state snapshotting, compile, final frame capture, and measurements |

## Scope Split

The spec spans several subsystems. Treat this document as the parent plan and execute it in slices. Each slice must be merged only after its tests and review gate pass.

1. Contract models and validation tests.
2. CanvasDirector schema 2 export and fragment assembly.
3. Actor-binding discovery and fingerprint native routes.
4. Python reconciliation, binding manifests, and metadata hashing.
5. Capture-scene preparation, role-aware visibility, and cleanup.
6. Compile request generation and compiler/replay adapter migration.
7. Nested `InstanceReference` preserve-as-instance proof.
8. 512 scale guard, transport diagnostics, instrumentation, and proof runs.

## Files And Responsibilities

### Existing Files To Modify

- `mcp_server/src/rook/canvas_director.py`: parse, validate, persist schema 2 exports and hand off to compile-prep without creating normalized compiler motion in the export marker.
- `mcp_server/src/rook/director_compiler.py`: accept normalized `director_compile_request_v1`, target capture object ids, and parameterized object-count limits for final capture.
- `mcp_server/src/rook/director.py`: expose new MCP tools and wire Python orchestration calls to native routes.
- `mcp_server/src/rook/director_actor_metadata.py`: reuse `.rook` actor metadata reading and hashing inputs; do not move binding reconciliation authority into old GUID maps.
- `mcp_server/src/rook/canvas_director_templates/scripts/export_marker.cs`: emit schema 2 authoring/take payload only; remove schema 1 `payload.motion` emission from the export marker.
- `mcp_server/src/rook/canvas_director_templates/scripts/transform.cs`: emit `director_motion_fragment_v1` for simple lift/rotate cases rather than opaque actor-set-level motion.
- `mcp_server/src/rook/canvas_director_templates/manifest.json`: update template metadata and expected pins when schema 2 inputs are introduced.
- `src/RookNative/RookServer.cpp`: register new Director actor-binding routes.
- `src/RookNative/Handlers/DirectorFrame.h`: expose or refine tight bbox helper contracts without accepting loose bbox as proof.
- `src/RookNative/Handlers/DirectorFrame.cpp`: keep tight bbox calculation aligned with frame-capture validation and prevent fallback proof semantics.
- `src/RookNative/Handlers/DirectorReplayHandler.cpp`: raise or parameterize object-count guards and return typed transport-limit diagnostics.
- `src/RookNative/Handlers/DirectorHandler.cpp`: reuse current object-state patterns where they fit; do not overload `/director/object-states` for binding proof.
- `mcp_server/tests/test_canvas_director.py`: schema 2 export, fragment ownership, and compile-prep adapter tests.
- `mcp_server/tests/test_canvas_director_templates.py`: template script contract tests for export marker and movement fragment payloads.
- `mcp_server/tests/test_director_compiler.py`: compile request, target invariant, source-state snapshot, and 512 guard tests.
- `mcp_server/tests/test_director_actor_metadata.py`: actor metadata fingerprint and binding reconciliation fixtures.
- `mcp_server/tests/test_director_native_source.py`: native route registration and source-level tight bbox/diagnostic guard checks.
- `mcp_server/tests/test_director_routes_live.py`: live Rhino proof tests for actor-binding routes, fingerprint routes, materialization, cleanup, and capture.

### New Files To Create

- `mcp_server/src/rook/director_contracts.py`: dataclasses or typed dict validators for schema 2 exports, motion fragments, actor binding manifests, capture scene manifests, compile requests, and proof reports.
- `mcp_server/src/rook/director_binding.py`: Python reconciliation logic, candidate selection, metadata canonicalization, binding manifest creation, and revalidation.
- `mcp_server/src/rook/director_capture_scene.py`: prepare/reuse/replace/cleanup orchestration and capture scene manifest persistence.
- `mcp_server/src/rook/director_compile_request.py`: compile-request derivation from schema 2 export, binding manifest, capture scene manifest, and source-state snapshot.
- `mcp_server/src/rook/director_proofs.py`: proof report assembly, claim matrix status, scale measurements, and transport-limit diagnostics.
- `mcp_server/tests/test_director_contracts.py`: pure Python contract and canonical JSON tests.
- `mcp_server/tests/test_director_binding.py`: pure Python binding reconciliation and manifest validity tests.
- `mcp_server/tests/test_director_capture_scene.py`: pure Python capture-scene manifest, idempotency, visibility, and cleanup tests.
- `mcp_server/tests/test_director_compile_request.py`: compile-request schema, hashing, target-map, and source-state snapshot tests.
- `src/RookNative/Handlers/DirectorActorBindingHandler.h`: native handler declarations for actor-binding candidate query and object fingerprint routes.
- `src/RookNative/Handlers/DirectorActorBindingHandler.cpp`: native route implementations for sanctioned Director metadata discovery and tight-bbox object fingerprints.

## Core Invariants

- Schema 2 is the only persisted authoring/take export format for v1.
- Schema 1 motion shape may exist only inside the compiler-facing adapter.
- `director_compile_request_v1` is invalid unless every normalized motion target is a take-owned capture object in the referenced capture scene manifest.
- `transform_semantics` is top-level `"absolute_from_source"` for v1; track-level semantics are omitted or must match exactly.
- Tight object bbox is the only bbox-based pass state: `bbox_method: "tight_object"` and `validation_strength: "tight_bbox"`.
- Loose/cached bbox output is diagnostic only and cannot pass binding drift, capture duplicate proof, or replay validation.
- Actor-binding manifests are generated fresh from `.rook` actor metadata plus current Rhino object metadata, then persisted as audit/cache artifacts.
- Cleanup never deletes source objects or persistent design-time actor objects.
- Nested `InstanceReference` support is proof-gated preserve-as-instance; recursive leaf flattening is not a silent fallback.

## Task 1: Contract Models And Canonical JSON

**Files:**

- Create: `mcp_server/src/rook/director_contracts.py`
- Create: `mcp_server/tests/test_director_contracts.py`

- [ ] **Step 1: Write canonical JSON hash tests**

Add tests that pin sorted object keys, semantic array order, finite numbers, and no NaN/Infinity:

```python
import math
import pytest

from rook import director_contracts as dc


def test_canonical_json_hash_sorts_object_keys_and_keeps_array_order():
    left = {"b": 2, "a": [{"z": 1, "y": 0}, {"n": 3}]}
    right = {"a": [{"y": 0, "z": 1}, {"n": 3}], "b": 2}
    assert dc.canonical_json_bytes(left) == dc.canonical_json_bytes(right)
    assert dc.canonical_json_hash(left) == dc.canonical_json_hash(right)


def test_canonical_json_hash_keeps_semantic_array_order():
    first = {"tracks": [{"track_id": "a"}, {"track_id": "b"}]}
    second = {"tracks": [{"track_id": "b"}, {"track_id": "a"}]}
    assert dc.canonical_json_hash(first) != dc.canonical_json_hash(second)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_canonical_json_rejects_non_finite_numbers(value):
    with pytest.raises(dc.DirectorContractError, match="non_finite_number"):
        dc.canonical_json_bytes({"value": value})
```

- [ ] **Step 2: Run the new tests and verify failure**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_contracts.py -q
```

Expected: fails because `rook.director_contracts` does not exist.

- [ ] **Step 3: Implement canonical JSON helpers**

Create `mcp_server/src/rook/director_contracts.py` with:

```python
from __future__ import annotations

import hashlib
import json
import math
from typing import Any


class DirectorContractError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _reject_non_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise DirectorContractError("non_finite_number", "Director canonical JSON accepts finite numbers only.")
    if isinstance(value, dict):
        for child in value.values():
            _reject_non_finite(child)
    elif isinstance(value, list):
        for child in value:
            _reject_non_finite(child)


def canonical_json_bytes(payload: Any) -> bytes:
    _reject_non_finite(payload)
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_json_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
```

- [ ] **Step 4: Verify canonical JSON tests pass**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_contracts.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Add minimum schema validators**

Extend `director_contracts.py` with validators for required discriminators and top-level fields:

```python
def require_mapping(value: Any, code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DirectorContractError(code, "Expected JSON object.")
    return value


def require_string(payload: dict[str, Any], field: str, code: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise DirectorContractError(code, f"{field} must be a non-empty string.")
    return value


def require_int(payload: dict[str, Any], field: str, code: str) -> int:
    value = payload.get(field)
    if not isinstance(value, int):
        raise DirectorContractError(code, f"{field} must be an integer.")
    return value


def validate_schema2_export(payload: Any) -> dict[str, Any]:
    data = require_mapping(payload, "schema2_export_not_object")
    if data.get("metadata_kind") != "rook.canvas_director.export":
        raise DirectorContractError("schema2_export_kind_mismatch", "metadata_kind must be rook.canvas_director.export.")
    if data.get("schema_version") != 2:
        raise DirectorContractError("schema2_export_version_mismatch", "schema_version must be 2.")
    require_string(data, "export_id", "schema2_export_missing_export_id")
    motion_fragments = data.get("motion_fragments")
    if not isinstance(motion_fragments, list):
        raise DirectorContractError("schema2_export_motion_fragments_not_array", "motion_fragments must be an array.")
    if "motion" in data:
        raise DirectorContractError("schema2_export_contains_compiler_motion", "schema 2 export must not contain normalized compiler motion.")
    return data


def validate_motion_fragment(payload: Any) -> dict[str, Any]:
    data = require_mapping(payload, "motion_fragment_not_object")
    if data.get("metadata_kind") != "director_motion_fragment_v1":
        raise DirectorContractError("motion_fragment_kind_mismatch", "metadata_kind must be director_motion_fragment_v1.")
    if data.get("schema_version") != 1:
        raise DirectorContractError("motion_fragment_version_mismatch", "schema_version must be 1.")
    require_string(data, "fragment_id", "motion_fragment_missing_fragment_id")
    claims = data.get("ownership_claims")
    tracks = data.get("tracks")
    if not isinstance(claims, list) or not claims:
        raise DirectorContractError("motion_fragment_claims_empty", "ownership_claims must be a non-empty array.")
    if not isinstance(tracks, list) or not tracks:
        raise DirectorContractError("motion_fragment_tracks_empty", "tracks must be a non-empty array.")
    return data
```

- [ ] **Step 6: Add validator tests for schema 2 and fragments**

Add tests that:

- accept a schema 2 export with `motion_fragments`,
- reject schema 2 export payloads containing `"motion"`,
- accept simple transform fragments and band peel fragments using the same `director_motion_fragment_v1` discriminator,
- reject fragments without `ownership_claims`,
- reject fragments without `tracks`.

- [ ] **Step 7: Commit Task 1**

```powershell
git add mcp_server/src/rook/director_contracts.py mcp_server/tests/test_director_contracts.py
git commit -m "feat: add director v1 contract validators"
```

## Task 2: CanvasDirector Schema 2 Export And Fragment Assembly

**Files:**

- Modify: `mcp_server/src/rook/canvas_director.py`
- Modify: `mcp_server/src/rook/canvas_director_templates/scripts/export_marker.cs`
- Modify: `mcp_server/src/rook/canvas_director_templates/scripts/transform.cs`
- Modify: `mcp_server/src/rook/canvas_director_templates/manifest.json`
- Modify: `mcp_server/tests/test_canvas_director.py`
- Modify: `mcp_server/tests/test_canvas_director_templates.py`

- [ ] **Step 1: Write export marker tests**

Add tests asserting that `CanvasDirector Export` emits:

- `metadata_kind: "rook.canvas_director.export"`,
- `schema_version: 2`,
- `motion_fragments`,
- no top-level `motion`,
- no `payload.motion`.

The template source test should inspect `export_marker.cs` and fail if it contains `payload.motion` assignment.

- [ ] **Step 2: Write duplicate ownership tests**

In `mcp_server/tests/test_canvas_director.py`, add a fixture with two motion fragments claiming the same `canonical_source_member_occurrence_id`. Expected error code:

```python
"duplicate_source_member_ownership"
```

- [ ] **Step 3: Run export tests and verify failure**

```powershell
python -m pytest mcp_server/tests/test_canvas_director.py mcp_server/tests/test_canvas_director_templates.py -q
```

Expected: tests fail because current export marker is schema 1 and emits `payload.motion`.

- [ ] **Step 4: Update `transform.cs` to emit a motion fragment**

Change the simple movement script output contract so it produces `director_motion_fragment_v1` with:

- `ownership_claims` per canonical source member,
- shared `track_id` references for identical simple lift/rotate tracks,
- `tracks` containing deterministic expanded keyframes,
- strategy descriptor fields only as provenance.

- [ ] **Step 5: Update `export_marker.cs` to assemble schema 2 only**

The export marker must accept motion fragment JSON inputs and produce a schema 2 payload shaped like:

```json
{
  "metadata_kind": "rook.canvas_director.export",
  "schema_version": 2,
  "export_id": "pearson_animation_test",
  "take_id": "pearson_animation_test",
  "timeline": {},
  "camera": {},
  "actor_refs": [],
  "motion_fragments": [],
  "validation": {
    "duplicate_source_member_ownership": false
  }
}
```

Do not emit normalized compiler `payload.motion` in C#.

- [ ] **Step 6: Update Python extraction to validate schema 2**

In `canvas_director.py`, route extracted schema 2 exports through `director_contracts.validate_schema2_export`. Persist the authoring export as source truth and keep schema 1 compiler compatibility only in a later compile-prep adapter.

- [ ] **Step 7: Verify export tests**

```powershell
python -m pytest mcp_server/tests/test_canvas_director.py mcp_server/tests/test_canvas_director_templates.py mcp_server/tests/test_director_contracts.py -q
```

Expected: tests pass.

- [ ] **Step 8: Commit Task 2**

```powershell
git add mcp_server/src/rook/canvas_director.py mcp_server/src/rook/canvas_director_templates/scripts/export_marker.cs mcp_server/src/rook/canvas_director_templates/scripts/transform.cs mcp_server/src/rook/canvas_director_templates/manifest.json mcp_server/tests/test_canvas_director.py mcp_server/tests/test_canvas_director_templates.py
git commit -m "feat: emit schema 2 canvas director exports"
```

## Task 3: Native Actor-Binding Discovery And Fingerprint Routes

**Files:**

- Create: `src/RookNative/Handlers/DirectorActorBindingHandler.h`
- Create: `src/RookNative/Handlers/DirectorActorBindingHandler.cpp`
- Modify: `src/RookNative/RookServer.cpp`
- Modify: `src/RookNative/Handlers/DirectorFrame.h`
- Modify: `src/RookNative/Handlers/DirectorFrame.cpp`
- Modify: `mcp_server/tests/test_director_native_source.py`

- [ ] **Step 1: Add source tests for route registration**

Assert `RookServer.cpp` registers:

```text
/director/actor-binding/query-candidates
/director/actor-binding/object-fingerprints
```

Expected methods: `POST`.

- [ ] **Step 2: Add source tests for route boundaries**

Assert the new native handler source:

- scans only the sanctioned Director actor-binding metadata namespace,
- does not call `/objects`,
- does not call `/scene/graph/query`,
- calls `DirectorObjectPoseBbox`,
- returns `bbox_method: "tight_object"` only when tight bbox is available,
- returns `validation_strength: "tight_bbox"` only with `bbox_method: "tight_object"`,
- puts loose/cached bbox data only under `diagnostic_bbox`.

- [ ] **Step 3: Run native source tests and verify failure**

```powershell
python -m pytest mcp_server/tests/test_director_native_source.py -q
```

Expected: fails because the new handler and routes do not exist.

- [ ] **Step 4: Add handler declarations**

Create `DirectorActorBindingHandler.h` with free-function handler declarations under `Rook::Handlers`, matching existing handler style.

- [ ] **Step 5: Add `query-candidates` request contract**

Implement request validation for:

```json
{
  "actor_set_id": "optional",
  "actor_member_ids": ["optional"],
  "include_malformed": true,
  "limit": 2048
}
```

Reject invalid `limit`, invalid member arrays, and requests that attempt general user-text search. The response candidates must include:

```json
{
  "object_id": "...",
  "actor_set_id": "...",
  "actor_member_id": "...",
  "binding_kind": "...",
  "binding_version": 1,
  "status": "valid_candidate"
}
```

- [ ] **Step 6: Add `object-fingerprints` request contract**

Implement batch request validation for:

```json
{
  "object_ids": ["..."],
  "include_director_metadata": true
}
```

Reject empty input, invalid UUID strings, missing objects, and over-limit batches with typed errors.

- [ ] **Step 7: Add tight-bbox fingerprint response**

Each object response must include:

```json
{
  "object_id": "...",
  "object_type": "...",
  "name": "...",
  "layer_path": "...",
  "director_metadata": {},
  "bbox_method": "tight_object",
  "tight_bbox_min": [0.0, 0.0, 0.0],
  "tight_bbox_max": [1.0, 1.0, 1.0],
  "model_units": "Millimeters",
  "bbox_rounding_policy": "director_v1_default",
  "validation_strength": "tight_bbox"
}
```

For instance references, also include definition and transform fields:

```json
{
  "instance_definition_id": "...",
  "instance_definition_name": "...",
  "instance_transform": [],
  "instance_transform_hash": "..."
}
```

Do not make native `director_metadata_hash` authoritative unless a canonical JSON algorithm is pinned in C++. Python owns the manifest hash.

- [ ] **Step 8: Register routes in `RookServer.cpp`**

Use the existing Director route pattern and main-thread dispatch pattern from neighboring handler registrations.

- [ ] **Step 9: Verify native source tests**

```powershell
python -m pytest mcp_server/tests/test_director_native_source.py -q
```

Expected: source-level tests pass.

- [ ] **Step 10: Build native plugin in a Rhino-capable Visual Studio shell**

Run from the repo root when Visual Studio and Rhino SDK are available:

```powershell
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected: native build succeeds. If the build machine lacks Rhino SDK or MFC, record the missing prerequisite and keep source tests as the completed verification for this task.

- [ ] **Step 11: Commit Task 3**

```powershell
git add src/RookNative/Handlers/DirectorActorBindingHandler.h src/RookNative/Handlers/DirectorActorBindingHandler.cpp src/RookNative/RookServer.cpp src/RookNative/Handlers/DirectorFrame.h src/RookNative/Handlers/DirectorFrame.cpp mcp_server/tests/test_director_native_source.py
git commit -m "feat: add director actor binding native routes"
```

## Task 4: Python Actor Binding Reconciliation

**Files:**

- Create: `mcp_server/src/rook/director_binding.py`
- Modify: `mcp_server/src/rook/director.py`
- Modify: `mcp_server/src/rook/director_actor_metadata.py`
- Create: `mcp_server/tests/test_director_binding.py`
- Modify: `mcp_server/tests/test_director_actor_metadata.py`

- [ ] **Step 1: Write reconciliation tests**

Add fixtures covering:

- `.rook` actor metadata expects two members,
- native candidate route returns current objects with matching actor metadata,
- Python computes `director_metadata_hash`,
- fresh reconciliation produces an authoritative current GUID map,
- persisted binding manifest is audit/cache only,
- duplicate member claims invalidate reconciliation,
- missing objects invalidate reconciliation,
- bbox-only matches cannot pass identity checks.

- [ ] **Step 2: Run binding tests and verify failure**

```powershell
python -m pytest mcp_server/tests/test_director_binding.py mcp_server/tests/test_director_actor_metadata.py -q
```

Expected: fails because `director_binding.py` does not exist.

- [ ] **Step 3: Implement metadata hash helper**

Use `director_contracts.canonical_json_hash` and remove runtime GUID fields before hashing. Identity precedence is:

```text
actor_set_id + actor_member_id + director_metadata_hash
```

Bbox, type, layer, and name are drift evidence, not durable identity.

- [ ] **Step 4: Implement `reconcile_actor_bindings`**

Inputs:

- schema 2 export actor refs,
- `.rook` actor metadata payloads,
- native `query-candidates` result,
- native `object-fingerprints` result.

Output:

```json
{
  "metadata_kind": "director_actor_binding_manifest",
  "schema_version": 1,
  "binding_manifest_id": "...",
  "source_document_fingerprint": {},
  "actor_metadata_fingerprint": {},
  "binding_policy_fingerprint": {},
  "members": []
}
```

Supported `binding_kind` values:

- `tagged_existing_top_level`
- `exact_geometry_duplicate`
- `top_level_instance_reference_duplicate`

- [ ] **Step 5: Add manifest revalidation**

Revalidation must compare:

- actor metadata hash,
- binding policy version,
- object metadata hash,
- object type,
- layer/name evidence,
- rounded tight bbox evidence,
- binding-kind-specific evidence.

Missing objects, duplicate claims, actor metadata mismatches, object metadata hash mismatches, and binding-kind evidence mismatches must invalidate the manifest.

- [ ] **Step 6: Expose MCP tools**

Add Python tool dispatch entries for:

- `rhino_director_resolve_actor_binding_v2`
- `rhino_director_bind_actor_set_v2`

The resolving tool reads current candidates and fingerprints. The binding tool may stamp metadata or create persistent design-time actor objects only when required by the actor binding policy.

- [ ] **Step 7: Verify Python binding tests**

```powershell
python -m pytest mcp_server/tests/test_director_binding.py mcp_server/tests/test_director_actor_metadata.py -q
```

Expected: tests pass.

- [ ] **Step 8: Commit Task 4**

```powershell
git add mcp_server/src/rook/director_binding.py mcp_server/src/rook/director.py mcp_server/src/rook/director_actor_metadata.py mcp_server/tests/test_director_binding.py mcp_server/tests/test_director_actor_metadata.py
git commit -m "feat: reconcile director actor bindings"
```

## Task 5: Capture Scene Preparation, Visibility, And Cleanup

**Files:**

- Create: `mcp_server/src/rook/director_capture_scene.py`
- Modify: `mcp_server/src/rook/director.py`
- Create: `mcp_server/tests/test_director_capture_scene.py`
- Modify: `mcp_server/tests/test_director_routes_live.py`

- [ ] **Step 1: Write manifest tests**

Test capture scene manifests include:

- `actor_binding_manifest_ref`,
- `actor_binding_manifest_hash`,
- per-member `source_bound_object_id`,
- per-member `source_binding_kind`,
- per-member `director_metadata_hash`,
- `generated_capture_object_ids` as a derived index equal to the union of member capture ids,
- role-aware visibility changes,
- cleanup order.

- [ ] **Step 2: Write idempotency tests**

Cover modes:

- `create`: fails if matching take-owned capture objects already exist.
- `reuse_if_valid`: requires export hash, actor binding manifest hash, materialization policy hash, ownership metadata, tight bbox proof, and visibility revalidation.
- `replace_existing`: restores prior source/design-time visibility state, removes or archives matching take-owned capture objects, then creates a fresh capture scene.

- [ ] **Step 3: Write mixed-block visibility tests**

`source_visibility_scope_unsupported` must occur unless every renderable member under the source top-level object is represented in the actor binding manifest or is explicitly non-renderable/hidden before materialization.

- [ ] **Step 4: Run capture scene tests and verify failure**

```powershell
python -m pytest mcp_server/tests/test_director_capture_scene.py -q
```

Expected: fails because `director_capture_scene.py` does not exist.

- [ ] **Step 5: Implement manifest builders**

Create pure functions for:

- `build_capture_scene_manifest`,
- `validate_generated_capture_object_index`,
- `validate_visibility_restore_plan`,
- `validate_reuse_inputs`,
- `build_failed_materialization_state`.

Partial mutation failures must record created object ids and visibility changes so recovery can avoid guessing.

- [ ] **Step 6: Implement orchestration tool**

Expose `rhino_director_prepare_capture_scene_v2` from Python. It must:

1. validate fragments and ownership,
2. consume a fresh actor binding manifest,
3. preflight source visibility scope,
4. create or reuse take-owned exact capture duplicates,
5. write capture scene and visibility manifests,
6. return typed conflicts for stale take-owned objects,
7. avoid creating duplicates during compile or final capture.

- [ ] **Step 7: Implement cleanup tool**

Expose `rhino_director_cleanup_capture_scene_v2`. It must restore source/design-time visibility first, then remove or archive only objects carrying matching `take_owned_capture_duplicate` metadata for the same `take_id` and `capture_scene_id`.

- [ ] **Step 8: Verify capture scene tests**

```powershell
python -m pytest mcp_server/tests/test_director_capture_scene.py -q
```

Expected: tests pass.

- [ ] **Step 9: Add live Rhino smoke tests**

In `test_director_routes_live.py`, add a small live test that prepares and cleans up a capture scene for two simple objects. Validate that source visibility is restored and generated capture objects are discoverable by ownership metadata before cleanup.

- [ ] **Step 10: Commit Task 5**

```powershell
git add mcp_server/src/rook/director_capture_scene.py mcp_server/src/rook/director.py mcp_server/tests/test_director_capture_scene.py mcp_server/tests/test_director_routes_live.py
git commit -m "feat: prepare director capture scenes"
```

## Task 6: Compile Request Generation And Compiler Adapter

**Files:**

- Create: `mcp_server/src/rook/director_compile_request.py`
- Modify: `mcp_server/src/rook/director_compiler.py`
- Modify: `mcp_server/src/rook/director.py`
- Create: `mcp_server/tests/test_director_compile_request.py`
- Modify: `mcp_server/tests/test_director_compiler.py`

- [ ] **Step 1: Write compile request schema tests**

Require:

- `metadata_kind: "director_compile_request"`,
- `schema_version: 1`,
- `compile_request_id`,
- `take_id`,
- `capture_scene_id`,
- `source_export_ref/hash`,
- `actor_binding_manifest_ref/hash`,
- `capture_scene_manifest_ref/hash`,
- `materialization_policy_hash`,
- `compiler_version`,
- `compile_adapter_version`,
- `transform_semantics: "absolute_from_source"`,
- `timeline`,
- `resolution`,
- `camera`,
- `source_state_snapshot_ref/hash`,
- `motion` targeting capture object ids only,
- validation counts.

- [ ] **Step 2: Write target invariant tests**

A compile request is invalid unless every normalized motion target is a take-owned capture object present in the referenced capture scene manifest. A source design-time object id must fail with:

```python
"compile_target_not_take_owned_capture_object"
```

- [ ] **Step 3: Write source-state snapshot tests**

The required source-state snapshot must include baseline object states for every `target_capture_object_id` in normalized motion and must record the route/version used to capture it. `bbox_only` may remain replay baseline vocabulary but cannot be treated as binding/capture proof.

- [ ] **Step 4: Run compile request tests and verify failure**

```powershell
python -m pytest mcp_server/tests/test_director_compile_request.py mcp_server/tests/test_director_compiler.py -q
```

Expected: new compile request tests fail.

- [ ] **Step 5: Implement compile request builder**

Build `director_compile_request_v1` after schema 2 export validation, actor binding reconciliation, capture scene materialization, and source-state snapshot capture. Each motion item must include:

```json
{
  "track_id": "roof_lift_track_001",
  "target_capture_object_id": "<guid>",
  "canonical_source_member_occurrence_id": "<id>",
  "actor_member_id": "<id>",
  "keyframes": []
}
```

Do not allow track-level transform semantics overrides. If present, track-level `transform_semantics` must equal top-level `"absolute_from_source"`.

- [ ] **Step 6: Adapt compiler input**

Teach `director_compiler.py` to compile from `director_compile_request_v1` while retaining schema 1 adapter compatibility only behind the adapter boundary. The compiler should not accept schema 2 authoring exports directly.

- [ ] **Step 7: Verify compile request tests**

```powershell
python -m pytest mcp_server/tests/test_director_compile_request.py mcp_server/tests/test_director_compiler.py -q
```

Expected: tests pass.

- [ ] **Step 8: Commit Task 6**

```powershell
git add mcp_server/src/rook/director_compile_request.py mcp_server/src/rook/director_compiler.py mcp_server/src/rook/director.py mcp_server/tests/test_director_compile_request.py mcp_server/tests/test_director_compiler.py
git commit -m "feat: persist director compile requests"
```

## Task 7: Nested InstanceReference Preserve-As-Instance Proof

**Files:**

- Modify: `mcp_server/src/rook/director_binding.py`
- Modify: `mcp_server/src/rook/director_capture_scene.py`
- Modify: `src/RookNative/Handlers/DirectorActorBindingHandler.cpp`
- Modify: `mcp_server/tests/test_director_binding.py`
- Modify: `mcp_server/tests/test_director_capture_scene.py`
- Modify: `mcp_server/tests/test_director_routes_live.py`

- [ ] **Step 1: Write nested instance manifest tests**

For `binding_kind: "top_level_instance_reference_duplicate"`, require proof evidence:

- `source_definition_id`,
- `source_definition_name`,
- `capture_definition_id`,
- `capture_definition_name`,
- `composed_source_transform_hash`,
- `capture_instance_transform_hash`,
- `matrix_abs_tolerance: 1e-9`,
- `attribute_preservation`,
- `tight_bbox_before`,
- `tight_bbox_after`,
- `replay_probe_frames`.

- [ ] **Step 2: Write typed failure tests**

Require these diagnostics:

- `nested_instance_reference_definition_unresolved`,
- `nested_instance_reference_transform_unresolved`,
- `nested_instance_reference_attribute_mismatch`,
- `nested_instance_reference_tight_bbox_unavailable`,
- `nested_instance_reference_replay_transform_failed`,
- `nested_instance_reference_unsupported`.

- [ ] **Step 3: Run nested instance tests and verify failure**

```powershell
python -m pytest mcp_server/tests/test_director_binding.py mcp_server/tests/test_director_capture_scene.py -q
```

Expected: tests fail until preserve-as-instance evidence is implemented.

- [ ] **Step 4: Implement proof evidence in manifests**

Binding and capture scene manifests must store the actual evidence, not pass/fail only.

- [ ] **Step 5: Implement live replay probe**

For instance-reference duplicates, run at least one non-zero-frame `absolute_from_source` replay probe and validate tight bbox movement. Failure must produce `nested_instance_reference_replay_transform_failed`.

- [ ] **Step 6: Verify nested instance tests**

```powershell
python -m pytest mcp_server/tests/test_director_binding.py mcp_server/tests/test_director_capture_scene.py -q
```

Expected: tests pass.

- [ ] **Step 7: Commit Task 7**

```powershell
git add mcp_server/src/rook/director_binding.py mcp_server/src/rook/director_capture_scene.py src/RookNative/Handlers/DirectorActorBindingHandler.cpp mcp_server/tests/test_director_binding.py mcp_server/tests/test_director_capture_scene.py mcp_server/tests/test_director_routes_live.py
git commit -m "feat: prove nested instance actor bindings"
```

## Task 8: Scale Guards, Transport Diagnostics, And Proof Reporting

**Files:**

- Create: `mcp_server/src/rook/director_proofs.py`
- Modify: `mcp_server/src/rook/director_compiler.py`
- Modify: `mcp_server/src/rook/director_preview.py`
- Modify: `src/RookNative/Handlers/DirectorReplayHandler.cpp`
- Modify: `mcp_server/tests/test_director_compiler.py`
- Modify: `mcp_server/tests/test_director_preview.py`
- Modify: `mcp_server/tests/test_director_replay_native_source.py`
- Modify: `mcp_server/tests/test_director_routes_live.py`

- [ ] **Step 1: Write compiler cap tests**

Require:

- final-capture compile path accepts 512 animated capture objects,
- old 256 guard no longer rejects valid final-capture compile requests,
- interactive preview path reports capability separately from final-capture support.

- [ ] **Step 2: Write replay transport diagnostic tests**

Native replay must return/report:

```json
{
  "code": "replay_transport_limit_exceeded",
  "payload_bytes": 10490000,
  "limit_bytes": 8388608,
  "limit_source": "DirectorReplayHandler.max_body_bytes",
  "final_capture_proven": true
}
```

The diagnostic is valid only before replay execution begins when request body size exceeds the configured limit. Runtime failures, validation failures, object-count guard failures, malformed payloads, and native replay errors must use distinct diagnostics.

- [ ] **Step 3: Run scale guard tests and verify failure**

```powershell
python -m pytest mcp_server/tests/test_director_compiler.py mcp_server/tests/test_director_preview.py mcp_server/tests/test_director_replay_native_source.py -q
```

Expected: tests fail against current 256-object guards and generic payload-too-large diagnostic.

- [ ] **Step 4: Raise or parameterize object-count guards**

Update Python and native guards so 512 is supported for final capture. Keep interactive `/director/replay` transport size checks separate from final-capture support claims.

- [ ] **Step 5: Add proof measurement report**

`director_proofs.py` must capture:

- compile request size,
- replay request size,
- per-frame capture request size,
- compile duration,
- native replay setup duration,
- final frame capture duration,
- process memory delta when available,
- proof claim statuses.

- [ ] **Step 6: Verify scale guard tests**

```powershell
python -m pytest mcp_server/tests/test_director_compiler.py mcp_server/tests/test_director_preview.py mcp_server/tests/test_director_replay_native_source.py -q
```

Expected: tests pass.

- [ ] **Step 7: Commit Task 8**

```powershell
git add mcp_server/src/rook/director_proofs.py mcp_server/src/rook/director_compiler.py mcp_server/src/rook/director_preview.py src/RookNative/Handlers/DirectorReplayHandler.cpp mcp_server/tests/test_director_compiler.py mcp_server/tests/test_director_preview.py mcp_server/tests/test_director_replay_native_source.py mcp_server/tests/test_director_routes_live.py
git commit -m "feat: prove director 512 final capture scale"
```

## Task 9: End-To-End Acceptance Proofs

**Files:**

- Modify: `mcp_server/tests/test_director_routes_live.py`
- Add generated proof artifacts under the project `.rook` output paths used by live runs; do not commit large captured frames or videos unless a release process explicitly requires them.

- [ ] **Step 1: Pearson proof**

Prerequisites:

- Rhino is open with the Pearson file.
- Grasshopper has the Director canvas definition loaded.
- The real 338-member actor set is bound or materialized through the v1 actor-binding layer.

Run the full pipeline:

```text
CanvasDirector Export assembly
-> validate fragments/ownership
-> reconcile document-bound actor bindings
-> prepare/materialize take-owned capture scene
-> write capture scene + role-aware visibility manifests
-> build required source-state snapshot
-> persist director_compile_request_v1
-> compile against capture object ids
-> final capture at target frame count
```

Pass criteria:

- one real Pearson actor set,
- 338 members,
- target frame count,
- no source/capture object double-rendering,
- tight-bbox proof passes,
- final frame capture succeeds,
- `Pearson production path support` claim marked passed.

- [ ] **Step 2: Assembler proof**

Use two small disjoint actor sets. Pass criteria:

- two movement fragments,
- disjoint canonical source member ownership,
- two capture mapping groups,
- compile request contains both groups,
- final capture/replay proof passes,
- `Export assembler completeness` claim marked passed.

- [ ] **Step 3: 512 cap proof**

Use 512 real duplicated renderable capture objects and simple identical lift tracks. Pass criteria:

- source-state snapshot includes all 512 capture objects,
- compile request targets all 512 take-owned capture objects,
- final frame capture succeeds,
- measurement report includes all required size/duration/memory fields,
- `512-object v1 final-capture support` claim marked passed.

- [ ] **Step 4: Interactive replay transport proof**

If `/director/replay` exceeds 8 MiB, verify the failure is exactly `replay_transport_limit_exceeded`, includes `payload_bytes`, `limit_bytes`, `limit_source`, and sets `final_capture_proven` only after the matching final-capture proof has passed.

- [ ] **Step 5: Commit acceptance test updates**

```powershell
git add mcp_server/tests/test_director_routes_live.py
git commit -m "test: add director v1 acceptance proof gates"
```

## Self-Review Checklist

- [ ] Every settled DEC-001 through DEC-027 is represented by a task or invariant.
- [ ] Schema 2 examples do not include top-level `"motion"` or `payload.motion`.
- [ ] `payload.motion` appears only as schema 1 adapter vocabulary.
- [ ] Every persisted artifact has a schema/version/hash rule.
- [ ] Every route decision has a native source test or live route test.
- [ ] Tight bbox is the only bbox proof pass state.
- [ ] Cleanup and replacement restore visibility before removing or archiving capture duplicates.
- [ ] `final_capture_proven` is used only after the corresponding proof has passed.
- [ ] The Pearson, assembler, and 512-object claims remain separate in reports and summaries.
- [ ] The plan contains no broad refactor task that lacks a test gate.

## Suggested Execution Order

Execute in order. Do not start Task 5 before Task 4 has a passing binding manifest contract. Do not start Task 6 before Task 5 can produce capture scene manifests with real capture object ids. Do not start Task 8 before Task 6 can build compile requests from capture object ids.

Recommended worker model:

1. One subagent for Task 1 and Task 2 together, reviewed before merge.
2. One subagent for Task 3 native routes, reviewed with source tests and native build status.
3. One subagent for Task 4 Python reconciliation.
4. One subagent for Task 5 capture scene materialization and cleanup.
5. One subagent for Task 6 compile request generation.
6. One subagent for Task 7 nested instance proof.
7. One subagent for Task 8 scale proof tooling.
8. Main thread runs Task 9 live acceptance proofs with Rhino/Grasshopper open.
