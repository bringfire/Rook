# Director Actor-Set Builder — Design Spec

> **PARTIALLY SUPERSEDED — Director MCP retirement (2026-07-13):** The general
> non-Director architecture and dated evidence in this document remain available.
> All `rhino_director_*`, `/director`, VisionDirector, and Director-domain examples,
> allowlist entries, count assumptions, acceptance criteria, and positive dispatch
> tests are superseded as of 2026-07-13. Replace those examples with
> non-Director fixtures when maintaining or replaying this work. This document must
> not be used to restore a Director MCP tool. See the
> [Director MCP Surface Retirement Design][director-mcp-retirement].

[director-mcp-retirement]: 2026-07-13-director-mcp-surface-retirement-design.md

**Tool:** `rhino_director_build_actor_set_from_source_occurrence_v2`
**Status:** spec for reviewer (Codex) sign-off, design-review amendments folded in.
**Date:** 2026-07-07
**Branch:** `feature/director-actor-set-builder`
**Layer:** Python-only (`mcp_server/src/rook/director_actor_metadata.py`). No native/C# changes.

---

## 1. Goal

Add the missing **build** capability to the Director authoring-metadata layer: turn an
already-captured source block occurrence into a durable, schema-v2 `director_actor_set`
via deterministic enumeration of the block definition's direct objects.

## 2. Context & gap (verified in-repo)

The authoring layer has capture + persist + read, but no builder:

- `capture_source_occurrence_v2` writes a **SelectionSnapshot of the source occurrence**
  (block instance + inventory/nested summary). It captures the *source*, not the members.
- `write_actor_metadata_v2` (`write_actor_metadata_bundle_v2`) is **schema/ref plumbing** —
  it persists a **pre-built** object graph; it validates schema + `.rook` refs, not semantics.
- The roof actor set on disk was **hand-authored (v1) then migrated**
  (`docs/superpowers/specs/2026-07-02-director-v2-relative-actor-metadata-design.md`, scope
  line 42; hand-authored JSON, lines 332–337; "semantic regrouping/classifier reruns" parked,
  line 54).

The deterministic enumeration this builder needs **already exists** as
`director_take_package._resolve_actor_sets` (`director_take_package.py:145`), which walks
`/block/objects-detailed` into members. This tool relocates that proven logic into the durable
authoring phase, emitting the v2 authoring schema instead of a per-take manifest.

## 3. Architecture & placement

- **Capability tier** between `capture_source_occurrence_v2` (capture) and
  `write_actor_metadata_v2` (persist). It **calls the writer internally**; the writer is not
  the agent-facing surface for actor-set creation.
- **Capture-first, strict two-step.** Input is an existing
  `source_occurrence_snapshot_ref`; the tool does **not** accept a live selection and does not
  fuse capture. (Matches the subsystem spec's "capture seeds the actor set" framing.)
- **Conforms to LM2A capability-inventory invariants** (`agent/capability_record.py`:
  dispatch path, closed schema, group/profile membership, risk classification). It does **not**
  conform to a typed produces/consumes capability-DAG — that does not exist in-repo yet
  (`2026-07-02-rook-planner-harness-north-star.md` §4.3: "discoverable metadata ≠ callable
  authority").
- **Mutating** (writes under `.rook`). Not a read tool.
- Flow legibility (agent discovering the authoring order) is handled by a **separate Director
  skill**, out of scope here.

## 4. Tool contract

**Name:** `rhino_director_build_actor_set_from_source_occurrence_v2`

**Inputs:**
| field | type | required | notes |
|---|---|---|---|
| `source_occurrence_snapshot_ref` | string (`.rook/...` ref) | yes | Must resolve to a `director_selection_snapshot` whose `source_occurrences` has length `1` and whose single source occurrence is a block instance. |
| `actor_set_id` | string | no | Safe filename segment. **Default = the snapshot's `snapshot_id`** (already validated as a safe filename segment by capture). Caller may override with a semantic name. |
| `replace_existing` | bool | no (default `false`) | Must be a real boolean, not a truthy string. When `false`, fail if the target actor-set ref already exists. When `true`, overwrite **only if** the existing file's `source_occurrence_snapshot_ref` equals this call's. |

**Algorithm:**
1. Resolve active project root via `resolve_active_project_root` (raises `document_path_required`
   if no active/saved `.3dm`).
2. Load + validate the snapshot via `load_metadata_ref` (`expected_kind = director_selection_snapshot`;
   raises `metadata_ref_not_found` / `metadata_kind_mismatch`). Require
   `len(snapshot["source_occurrences"]) == 1` (else `snapshot_not_single_source`). Treat
   `snapshot["source_occurrences"][0]` as authoritative. If the `snapshot["source_occurrence"]`
   convenience field is present, it must equal `source_occurrences[0]` exactly, otherwise fail
   `snapshot_source_mismatch`. Require the authoritative source occurrence's `object_type` be a
   block instance (else `snapshot_source_not_block`). **Note:** the snapshot carries
   `source_occurrences` (list) + `source_occurrence` (convenience when length 1); it does **not**
   carry `source_take_context` — that field exists only in the Director Actors *runtime payload*,
   not the selection snapshot.
3. **Drift gates (fail typed, never silently rebuild):**
   - read block `id`/`name` from `snapshot.source_occurrence.block_definition`;
   - call `/block/instances` for that block name; require the snapshot's
     `source_top_level_object_id` to be present among the returned instances
     (else `source_occurrence_missing_in_document`);
   - call `/block/info` for that block name; require its definition `id` and `name` match the
     snapshot's `block_definition` (else `block_definition_drift`).
4. Enumerate the block definition's direct objects via `/block/objects-detailed` (native
   `BlocksHandler.cpp:3457`). The route skips geometry-less objects and returns the def-table
   `index` per object (see §8). Empty result → `block_enumeration_empty`. Malformed member
   identity from the route (missing/non-integer/negative `index`, missing/non-GUID `id`,
   duplicate `index`, duplicate definition object id) → `block_enumeration_invalid`.
5. Build members (schema §5). Require tight bbox for every member (`bboxMethod == "tight_object"`);
   any `loose_fallback` / `unavailable` → fail typed `tight_bbox_unavailable` (mirrors
   `package_take` DEC-021, `director_take_package.py:160`).
6. Assemble the `director_actor_set` object (schema §6) and persist via
   `write_actor_metadata_v2` honoring the overwrite policy (§7).

**Output:** `{ schema_version, metadata_kind, actor_set_id, actor_set_ref,
resolved_actor_set_path, member_count }`.

## 5. Member schema (LOCKED)

Each member records **only** durable identity, the grouping join key, and verification evidence:

```jsonc
{
  "ordinal": 12,                                  // = /block/objects-detailed def-table `index` (may be non-contiguous)
  "resolved_reference": {
    "definition_object_id": "<def-object GUID>"   // durable member identity (copy-stable spine)
  },
  "expected": { "type": "Brep", "layer": "...", "name": "..." },
  "bbox_evidence": {
    "bbox_method": "tight_object",
    "bbox_space": "definition_object",
    "min": [x,y,z], "max": [x,y,z],
    "rounding_policy": "round_to_4_decimal_places",
    "validation_strength": "tight_bbox"
  }
}
```

**Identity model (locked, from design review):**
- **Durable member identity → `resolved_reference.definition_object_id`.** This is the only
  field that must be correct for canvas resolution; the wave's `LoadActorCandidates` matches
  candidate GUIDs against `idef.GetObjects()` and resolves by this GUID. The builder must validate
  the native id parses as a GUID and persist canonical UUID text.
- **Ordering / grouping join → `ordinal`.** `ordinal` is a **metadata-local join key**: the
  wave's `LoadBandMembers` cross-references `actorCandidates[ordinal]` between the actor-set and
  grouping files. It is **not** a claim about live-document position — a later block edit cannot
  misalign resolution because the wave resolves by `definition_object_id`, not by `ordinal`.
  `ordinal` is set to the native route's def-table `index` (the `def->Object(i)` loop index),
  which **may be non-contiguous** because geometry-less objects are skipped (§8). This matches
  `package_take`'s `index` usage, so any downstream grouping must key on the same `ordinal`
  values — the builder must not re-number to a contiguous array position.
- **`current_reference` / `observed_selection` are OMITTED.** For definition-derived members
  there is no current-document member identity; echoing the def-object GUID into
  `document_object_id` would be semantically false. The wave tolerates their absence
  (`TryGetProperty`-guarded).
- **`actor_member_id` is NOT part of this schema.** Any `actor_member_id` is a render/compiler-
  local label that `package_take` derives from the **take-local** `actor_set_id`
  (`director_take_package.py:157`), which differs from the authoring `actor_set_id`. Persisting
  it here would assert a cross-layer continuity that does not hold.
- **`definition_object_index` is NOT in authoring metadata.** `package_take` derives its own
  `definition_object_index` from its own live `/block/objects-detailed` read; freezing it here
  risks silent disagreement if the block is edited between authoring and render. Authoring uses
  `ordinal`; the render manifest keeps `definition_object_index`; both independently equal the
  enumeration index, with `definition_object_id` as the shared spine.

## 6. Actor-set top-level schema

```jsonc
{
  "schema_version": 2,
  "metadata_kind": "director_actor_set",
  "actor_set_id": "<safe id>",
  "source_occurrence_snapshot_ref": ".rook/.../selection_snapshots/<...>.json",
  "summary": { "member_count": N, "resolved_count": N },
  "members": [ /* §5 */ ]
}
```
`resolved_count == member_count` at build time (every enumerated object with a tight bbox becomes
a resolved member; anything without fails the build rather than lowering `resolved_count`).

## 7. Overwrite semantics (LOCKED)

- Default `replace_existing = false` → **fail typed** (`actor_set_exists`) if the target ref exists.
- `replace_existing = true` → overwrite **only if** the existing file's
  `source_occurrence_snapshot_ref` equals this call's; otherwise fail typed
  (`actor_set_source_mismatch`). Prevents repointing an existing actor-set id at a different source.

## 8. "Full set" contract (resolved against the native handler)

Members = the **full direct-geometry member set as returned by `/block/objects-detailed`**, not
every raw definition-table entry. Confirmed against the native handler
(`src/RookNative/Handlers/BlocksHandler.cpp:3457`): it loops `def->Object(i)` over the definition
table and **skips any object where `!obj || !obj->Geometry()`**, emitting `index = i` (the
def-table position) for the surviving objects. Consequences the builder must honor:
- geometry-less table entries never appear → they are legitimately absent from the actor set;
- surviving `index` values can be **non-contiguous** → `ordinal` inherits those gaps (§5);
- each surviving object carries `bboxMethod ∈ {tight_object, loose_fallback, unavailable}`
  (`BlocksHandler.cpp:3513`); the builder admits only `tight_object` (§4 step 5).

Separately, the wave skips non-breps at solve time (`cache.NonBrep++`), so `member_count` may
legitimately exceed the animatable count — expected, not a builder concern.

## 9. Non-goals

- No subsetting (`director_actor_subset` — separate capability).
- No banding / grouping (`director_actor_grouping` — the semantic, often partial, creative layer).
- No canvas wiring (pointing `Director Actors` at the new refs is a separate step).
- No fused live-selection capture.
- No native/C# changes.

## 10. Failure modes (all typed, fail-closed)

**Reuse existing `director_actor_metadata` codes** where the condition already has one — do not
invent parallel names:
- no active/saved `.3dm` → **`document_path_required`** (from `resolve_active_project_root`).
- snapshot ref missing/unreadable → **`metadata_ref_not_found`** (from `load_metadata_ref`).
- snapshot wrong kind → **`metadata_kind_mismatch`** (from `validate_loaded_metadata`).

New codes for genuinely-new conditions: `snapshot_not_single_source`, `snapshot_source_mismatch`,
`snapshot_source_not_block`, `source_occurrence_missing_in_document` (drift),
`block_definition_drift` (id/name mismatch or route-level missing/renamed block failure),
`block_enumeration_empty` (zero surviving objects), `block_enumeration_invalid` (malformed,
non-GUID, or duplicate member identity from `/block/objects-detailed`), `tight_bbox_unavailable`,
`actor_set_exists`, `actor_set_source_mismatch`.

## 11. Exposure / classification

Source files to update:
- `server.py` — MCP tool definition + dispatch case (alongside the sibling `..._v2` tools).
- `agent/tool_groups.py` — Director tool group membership.
- `targeting.py` — classify as **mutating** (not in read sets).
- `mcp_tool_profiles.py` — profile membership.

Test files to update (grep the set name, not the number — the plan must confirm which apply):
- `test_director_mcp_tools.py`
- `test_multi_instance_targeting.py`
- `test_server_tool_profiles.py`
- `test_mcp_tool_profiles.py`

## 12. Test matrix (required)

Unit tests (mock native, per the sibling `test_director_actor_metadata.py` pattern):
1. Happy path — single-block snapshot → full member set, correct `ordinal`/`definition_object_id`,
   tight bbox, `member_count == resolved_count`.
2. Non-block snapshot → `snapshot_source_not_block`.
3. Multi-source snapshot → `snapshot_not_single_source`.
4. Mismatched `source_occurrence` convenience field vs `source_occurrences[0]` →
   `snapshot_source_mismatch`.
5. Zero enumerated objects → `block_enumeration_empty`.
6. Missing/non-integer/negative `index`, missing/non-GUID definition object id, duplicate ordinal,
   or duplicate definition object id → `block_enumeration_invalid`.
7. Loose / missing bbox (`bboxMethod != "tight_object"`), malformed bbox arrays, non-numeric bbox
   values, or non-finite bbox values → `tight_bbox_unavailable`. Error data for rejected bbox
   values must stay strict-JSON-safe; do not include raw `NaN`/`Infinity` floats.
8. Existing actor set, `replace_existing=false` → `actor_set_exists` even if the existing file is
   corrupt or wrong-kind.
9. `replace_existing=true`, same snapshot ref → overwrite succeeds.
10. `replace_existing=true`, different snapshot ref → `actor_set_source_mismatch`.
11. Non-boolean `replace_existing` such as `"false"` → `metadata_bundle_invalid`.
12. **Drift** — snapshot block def id/name ≠ live `/block/info`, or native `/block/instances` /
   `/block/info` reports the captured block name missing → `block_definition_drift`;
   source occurrence absent from doc → `source_occurrence_missing_in_document`.
13. Unsaved / no active document → `document_path_required`.
14. Schema assertion — emitted member has `ordinal` + `resolved_reference.definition_object_id`
    and **no** `actor_member_id`, `definition_object_index`, `current_reference`,
    `observed_selection`.
15. MCP exposure — tool present, classified mutating, in both targeting + profile surfaces.

## 13. Resolved code facts (verified this session)

- `/block/objects-detailed` semantics — resolved in §8 (native `BlocksHandler.cpp:3457`: skips
  `!obj || !obj->Geometry()`, emits def-table `index`, per-object `bboxMethod`).
- Snapshot field names — `source_occurrences` (authoritative list) + `source_occurrence`
  (optional convenience mirror); **no `source_take_context`** in the selection snapshot (that
  field is runtime-payload only). Drift gate reads the authoritative source occurrence's
  `block_definition.{id,name}` and `source_top_level_object_id`.
- Existing error codes — `document_path_required`, `metadata_ref_not_found`,
  `metadata_kind_mismatch` (reused per §10).
- All four exposure test files exist under `mcp_server/tests/`.

---

**Reviewer focus:** ref-field and overwrite semantics (§5, §7) are the two places most likely to
create durable metadata debt; both are now resolved to the design-review decisions. The builder
is intentionally the mechanical half — it stops at the complete member set; subset and banding
are separate capabilities.
