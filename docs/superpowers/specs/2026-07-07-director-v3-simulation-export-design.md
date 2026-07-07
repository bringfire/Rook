# Director v3 Simulation Export — Per-Member Canvas Motion (Design)

Date: 2026-07-07
Branch: `worktree-director-v3-sim-export` (worktree `.claude/worktrees/director-v3-sim-export`, off `origin/main`)
Status: DESIGN — for Codex second review before writing the implementation plan.

## Goal

Capture the CanvasDirector Grasshopper canvas's **per-member** motion (the band-peel
wave) as a Director v3 render, by driving the Director Clock across all frames and
harvesting each member's per-frame value — a "simulation export" — then feeding it
through the **existing** package → prepare → compile → capture → assemble pipeline as
ordinary per-member `motion.json` tracks.

## Architecture (one sentence)

The canvas motion primitive (C42 "Director Band Peel Wave Preview") is taught to emit
its resolved per-member identity (`Ids`) alongside the offsets it already emits (`H`);
a new Python orchestrator scrubs the Clock 0→N, assembles a typed
`director_member_motion_samples_v1` artifact, derives a per-member `motion.json` from it,
and drives the existing v3 pipeline unchanged.

## Tech Stack

RhinoCode C# script component (canvas, hand-authored prototype); Python
(`mcp_server/src/rook/`); native HTTP routes consumed read-only via `/gh/*`,
`/block/objects-detailed`, `/director/*`. No native code changes. No changes to
`director_worker_compile.py`, `director_worker_prepare.py`, `camera_planner.py`, or the
native handlers **unless the round-trip gate fails** (documented baked fallback).

## Global Constraints

- The Pearson document (`C:\Users\aryan\V2\Axon_Pearson_Experimental_TESTING.3dm`) is
  **never mutated**. Only `prepared.3dm` copies inside the take package are written. The
  live doc is restored (`modified:False`) in a `finally`.
- The Director Clock is authoritative: render frame `j` (1-based) corresponds to timeline
  position `t = (j-1)/(N-1)`; the Clock `FrameIn` slider is scrubbed to the value that
  produces that timeline state, and the harvested value is recorded — never recomputed.
- Rhino launch/close is the user's. The orchestrator runs against a live instance the
  user has open; it never launches, closes, or restarts Rhino.
- Preview toggles stay OFF during scrubbing (no per-scrub viewport redraw).
- `transform_semantics = "absolute_from_source"` end to end: a member's sampled offset is
  measured from its rest pose, and drops into the track as an absolute-from-rest translate.

---

## 1. Context

Director v3 renders from an immutable **take package** (scene `.3dm` copy + scene
manifest + `motion.json` + `camera.json`), destructively exploded into a disposable
`prepared.3dm`, compiled to a file-backed `track.json`, then captured and assembled.
The canvas→v3 bridge (`scratchpad/render_from_canvas.py`) already drives this for
**uniform** actor motion and a harvested camera.

What has been missing is **per-member differential motion**: the band-peel wave lifts
each mullion on a band-dependent delay, so each member has its own Z curve over time.
The wave is computed live on the canvas by **C42 "Director Band Peel Wave Preview"**
("Director movement primitive v2"), a hand-authored script that is *ahead* of the
template pack (`canvas_director.transform` is an older, declarative, uniform design).
C42 is **preview-only** — its geometry feeds a `Custom Preview`, never the Export — so
its motion never reaches a render.

This slice makes that motion renderable **without reverse-engineering the wave math**:
we harvest what the canvas produces (the "harvest, don't reimplement" rule already used
for the camera).

## 2. Verified identity model (proofs, not assumptions)

- **C42 already emits per-member offsets.** Output `H` = ordered list of per-member Z
  offsets, `dz = maxH·smoothstep(clamp((front − bandIndex)/spread, 0, 1))`,
  `front = effectiveProgress·((bandCount−1)+spread)` — a pure function of `Progress`
  (← Oscillator ← Clock), deterministic. At `progress = 0`, all `H = 0` (rest).
- **Output order** = band `sequence_index` (C42 `LoadBandMembers` stable-sorts by it).
  Order is irrelevant to the join once C42 also emits `Ids` (below).
- **C42 resolves members against `idef.GetObjects()`** — the **top-level** definition
  objects of the source block instance — and poses them with `InstanceXform`. This is
  the **same object space** v3 prepare explodes (`pDef->Object(i)`), so the join key is
  a **top-level `definition_object_id`**.
- **v3 `member_map` is keyed by `definitionObjectId = pDef->Object(i).m_uuid`**
  (`DirectorPrepareHandler.cpp:343`).
- **Proven live:** the actor-set's captured `document_object_id`s are exactly these
  definition ids — `member_000` `3944de90…` = def index **3**; `member_188` `6203a5f7…`
  = def index **239** (from `/block/objects-detailed`). `document_object_id` is
  **copy-stable** (same in the live doc and the take copy).
- **`ordinal ≠ def index`** (actor-set ordinal 0 lives at def index 3). We join **by id
  and by def index, never by ordinal.**
- **`actor_member_id` is deterministic**, assigned by the package builder as
  `f"{actor_set_id}_member_{index:04d}"` where `index` and `definition_object_id` both
  come from the **same** `/block/objects-detailed` call
  (`director_take_package.py:157,168-169`). It is **not** minted by prepare. So the
  orchestrator can reproduce every `actor_member_id` **before** packaging.

## 3. The declarative resolution chain (where each thing resolves and fails)

`actor_member_id` is **not** a compiler concept. The chain is:

```
motion.json  target = actor_member_id
   └─ prepare_take._derive_resolved_motion:  resolved_groups[actor_member_id] = created_object_ids
        (via member_map lookup: actor_member_id → created_object_ids; director_worker_prepare.py:319,383)
   └─ compile_take.expand_targets:  expands resolved_groups → {created_object_uuid: keyframes}
        (director_compiler.py:122-135)
```

Consequences the spec relies on:
- An **unknown** `actor_member_id` fails in **prepare** — `expand()` raises when the
  target is not in the `member_map` lookup (director_worker_prepare.py:323-334).
- **Duplicate** member tracks are **not** caught in prepare: `_derive_resolved_motion`
  *skips* an already-resolved target (director_worker_prepare.py:383), so a dup would
  surface only later in `compile.expand_targets` as `duplicate_object_target`. The
  orchestrator therefore **preflight-rejects duplicate generated `actor_member_id`s
  before packaging** (Section 8) — the earliest, correct failure surface.
- Created-id resolution and its hashes live in `resolved_motion.json`
  (`resolved_motion_sha256`, `member_map_sha256`) — provenance is intact; nothing
  bypasses the snapshot boundary.
- Compile only ever sees created UUIDs; it never learns about `actor_member_id`,
  `definition_object_id`, or live Grasshopper.

## 4. Scope / Non-goals

**In scope (this slice — "prove on the prototype"):**
1. C42 canvas edit: add an `Ids` output (ordered top-level `definition_object_id`s,
   parallel to `G`/`H`).
2. `director_member_motion_samples_v1` typed artifact (Section 6) assembled by the
   orchestrator from `Ids`+`H`.
3. A new Python orchestrator (`director_simulation_export.py`): scrub-collect, def-id →
   `actor_member_id` derivation, `motion.json` + dense camera generation, and driving
   the existing pipeline.
4. Hard gates (Section 8), including the sampled→`track.json` round-trip proof.
5. Live gate: render the Pearson mullion band-peel wave end to end.

**Non-goals (explicit — next slice):**
- Promoting the per-member motion primitive into the template pack, and having the
  template emit `director_member_motion_samples_v1` natively. (This slice's C42 edit is
  the interim prototype; the orchestrator assembles the typed artifact from `Ids`+`H`.)
- Any change to `director_worker_compile.py` / native compile/capture — unless the
  round-trip gate fails, in which case the baked fallback (Section 9) is the escalation.
- Per-leaf nested motion (see Section 7 — member tracks move a member *as a unit*).
- Promoting the orchestrator to an MCP tool/route (stays a module + driver script here).

## 5. Component 1 — C42 canvas edit (`Samples` output)

**Read-path constraint (verified):** `/gh/inspect-output` caps list previews at **5
items** (`GrasshopperHandler.cs:4988` — `if (previewCount >= 5) break`) and has **no
length cap on a single-item string** (a ~1KB `Info` string reads in full via
`preview[0]`). A 338-element **list** output is therefore unreadable in full — this is
true of the existing `H` list too. The harvestable shape is **one packed JSON string**.

C42 already computes the resolved definition object per member in `BuildCache` (`source`
in the `objectsById` match) but keeps only `Ordinal` on `CachedMember` and discards the
id. The edit:

- Add `public string DefId;` to `CachedMember`; in `BuildCache`, set
  `DefId = source.Id.ToString()` when the member resolves.
- Add a single `ref object Samples` output to `RunScript` (appended **after** `Info` to
  preserve the indices of `G`/`H`/`Info` and their existing wires).
- Emit `Samples` = a compact JSON **string** for the current frame:
  `{"ids":[<DefId…>],"z":[<heights…>]}`, `ids[k]` and `z[k]` in `cache.Members` order
  (same order as `G`/`H`). Build it with a `StringBuilder` (no `System.Linq` dependency),
  reusing the file's existing `Escape`/`Num` helpers for the id strings and offsets.

`G`/`H` are left unchanged (they still drive the visual preview / debug panels). Only
`Samples` is harvested.

**Contract:** `Samples.ids[k]` is the **top-level** `definition_object_id` of the member
whose offset is `Samples.z[k]`. C42 only ever matches against `idef.GetObjects()`
(top-level, non-recursive), so `ids` are always top-level member ids — never nested leaf
ids. `Samples` is the per-frame slice of `director_member_motion_samples_v1` (Section 6).

**Edit mechanics / risk:** apply via `gh_set_script` (raw source write; recompiles +
`ExpireSolution`). Appending an output pin *may* force RhinoCode to drop this
component's outgoing wires (`G→C47 Preview`, `G→C46`, `H→C38`). Mitigation: after the
write, `gh_snapshot` and verify (a) `Samples` present and parses to `len(ids)==len(z)`,
(b) the three output wires intact; if any dropped, restore via `gh_edit` from the mapped
topology. `gh_undo` is the rollback. This is a one-time, reversible edit on the user's
hand-built canvas and is gated by a live check before any render.

## 6. Component 2 — typed artifact `director_member_motion_samples_v1`

The durable member-motion contract (assembled by the orchestrator this slice; emitted by
the template natively next slice). `H` stays preview/debug; this typed artifact is the
boundary record of what the canvas produced.

```jsonc
{
  "schema_version": 1,
  "metadata_kind": "director_member_motion_samples_v1",
  "actor_set_id": "actor_a28cbdb551fa",          // orchestrator-chosen take actor-set id
  "source_block_name": "3D_BLOCK_ARCH_ROOF_0502 UPLIFT ROOF - VERTICAL",
  "source_top_level_object_id": "a28cbdb5-51fa-46b2-b18b-ab880b54ded7",
  "frame_count": 240,                            // N
  "fps": 24,
  "units": "millimeters",                        // model units
  "transform_semantics": "absolute_from_source",
  "sample_kind": "translate_z",                  // this primitive lifts in Z; contract allows others later
  "id_space": "top_level_definition_object_id",
  "ids": ["3944de90-…", "…"],                    // ordered top-level def ids (== C42.Ids), length M
  "frames": [                                    // length N, 1-based frame_index
    { "frame_index": 1, "translate_z": [0.0, 0.0, /* … M values, aligned to ids[] */] },
    { "frame_index": 2, "translate_z": [ /* … */ ] }
    // …
  ],
  "ids_sha256": "…",                             // sha256 of the canonical ids[] (stability proof, Section 8)
  "component_provenance": {
    "component_guid": "b6ba1144-…",              // C42 script type guid
    "component_nick": "Director Band Peel Wave Preview",
    "actor_grouping_ref": ".rook/…/same_orientation_mullions_001_bands_001.json",
    "clock_denominator": 240,
    "frame_in_guid": "…", "camera_controller_guid": "…"
  },
  "warnings": []
}
```

`sample_kind: "translate_z"` and `transform_semantics: "absolute_from_source"` fix the
interpretation: `frames[j].translate_z[m]` is the absolute-from-rest Z translation of
member `ids[m]` at frame `j+1`. `id_space` fixes the ids as top-level definition object
ids (Section 8 gate rejects anything else).

**`ids_sha256` canonicalization (Finding 5):** `ids_sha256 = sha256(canonical_json_text(ids)
.encode("utf-8"))`, where `canonical_json_text` is the repo helper
(`director_take_package.py:49` — `json.dumps(payload, indent=2, sort_keys=True)`). This is
the **same** canonical-JSON rule used for `motion_json_sha256` / `scene_manifest_sha256`,
so every producer/consumer hashes the identical byte representation. `sort_keys` does not
reorder the `ids` array (it is a list), so the ordered ids — hence any reordering across
frames — is what the hash pins.

Camera is **not** part of this artifact (it is not member motion). It is harvested in
parallel as dense `explicit_camera` keyframes (Section 7).

## 7. Component 3 — orchestrator `director_simulation_export.py`

**Indexing convention (used throughout).** N frames. `frame_index` is 1-based
(`1..N`). A member's harvested offsets are `dz[0..N-1]`, where `dz[p]` is the offset at
`frame_index = p+1`, `t = p/(N-1)`. `dz[0]` is the **rest** frame (`t=0`). The compiler
uses the same grid (`director_motion.py`: `t = i/(N-1)`, `frame_index = i+1`).

### 7a. Scrub-collect (live; reuses the proven camera-scrub mechanism)

For `p` in `0..N-1`: set `FrameIn` to the value producing timeline position
`t = p/(N-1)` (`round(t · clock_denominator)`), then read (via native
`/gh/inspect-output`, `preview[0]` = the full single-string output):
- `C42.Samples` — **every frame**; `json.loads(preview[0])` → `{ids, z}`. Hash `ids`
  each frame (`ids_sha256`, Section 6) and assert equal to the frame-0 hash (Finding 2).
  `ids` are used from frame 0; later frames only re-assert the hash. `z[k]` is member
  `ids[k]`'s offset `dz[p]` at this frame.
- `C16.Camera` (`director_camera_state`) — the resolved camera at this frame; staleness
  guard `local_t ≈ FrameIn/clock_denominator`.

Restore `FrameIn = 0` in a `finally`. Reading C42/C16 outputs does not mutate the `.3dm`
(C42 moves *duplicated* preview geometry, not the doc's block). Produces:
`member_dz = {def_id: [dz[0] … dz[N-1]]}` (from `ids`+`z`) and
`cam_keyframes = [{frame_index: p+1, source: {kind: "explicit_camera", camera: …}}]`.

### 7b. def-id → actor_member_id (reproduce the package builder's assignment)

Call `/block/objects-detailed` for `source_block_name` → `{def_id: def_index}`
(the same route/values `package_take` uses). For each animated `def_id`:
`actor_member_id = f"{actor_set_id}_member_{def_index:04d}"`.

### 7c. Generate `motion.json` (per-member declarative tracks)

```jsonc
{
  "timeline": { "fps": 24, "frame_count": 240 },
  "groups": {},
  "default_easing": "linear",               // irrelevant: a keyframe at every frame ⇒ no interpolation
  "motion": [
    { "target": "actor_a28cbdb551fa_member_0003",
      "keyframes": [ { "t": <1/(N-1)>, "translate": [0,0,<dz[1]>] }, … { "t": 1.0, "translate": [0,0,<dz[N-1]>] } ] }
    // one track per animated member
  ]
}
```

- Keyframes cover `t = p/(N-1)` for `p = 1..N-1`. Index `p=0` (`t=0`, rest) is **omitted**
  and left to compile's implicit `t=0` identity (`director_motion.compile_object_track`
  prepends identity when `t=0` is absent, and **rejects** an explicit non-identity
  `t=0`). This requires `dz[0] = 0` (rest) — a hard gate (Section 8).
- A keyframe exists at every sampled `t` (implicit `t=0` + explicit `p=1..N-1`), so
  `compile_object_track` samples each frame **exactly** on a keyframe → no interpolation
  → `track.json` `frame_index = p+1` translate.z `== dz[p]` exactly.

### 7d. Drive the pipeline (existing code, unchanged)

`package_take(actor_sets=[{actor_set_id, block_name, source_top_level_object_id}],
motion=<7c>, camera={strategy:"keyframes", keyframes: cam_keyframes},
display_modes=[…])` → `prepare_take` → `compile_take` → `capture_take` →
`/director/video-assemble`. Restore the live doc in `finally`.

### 7e. Testable seams (pure, no live canvas)

- `build_actor_member_ids(block_objects, actor_set_id) -> {def_id: actor_member_id}`.
- `build_motion_json(member_dz, def_to_member_id, timeline) -> motion.json dict`.
- `build_samples_artifact(ids, per_frame_H, meta) -> director_member_motion_samples_v1`.
- `assert_samples_invariants(artifact)` (Section 8 gates that don't need live/render).

## 8. Invariants & hard gates

Input gate (before anything):
- `frame_count >= 2` (Finding 4). `t = p/(N-1)` divides by zero at `N=1`, and a
  single-frame track has no explicit keyframes. Reject `N < 2`.

Harvest-time (fail the run before packaging):
- `len(Samples.ids) == len(Samples.z)` at every frame.
- `Samples.ids` **stable** across **all N frames** — `ids_sha256` (Section 6) identical
  for every frame's read (Finding 2), not just first/last.
- No duplicate ids in `Samples.ids`, and **no duplicate generated `actor_member_id`** —
  the orchestrator preflight-rejects dup ids/member ids before packaging (Finding 1; dups
  are not caught by prepare).
- Every `Samples.ids` entry maps to **exactly one** top-level member via
  `/block/objects-detailed` (`id_space` gate); any id not a top-level member id → fail
  (`nested_or_unknown_id`).
- **Frame-0 rest:** `dz[0] == 0` for all members (the rest frame, `frame_index 1`,
  `t=0`) — else the declarative path cannot represent it → baked fallback, Section 9.

Package-time (after `package_take`, before `prepare`) — **manifest drift gate** (Finding 3):
- Load `scene_manifest.json` and assert, for every animated member, that the manifest's
  `{definition_object_id, definition_object_index, actor_member_id}` triple **exactly
  matches** the orchestrator's precomputed mapping. `package_take` runs its own
  `/block/objects-detailed` and assigns ids independently (director_take_package.py:157);
  this gate makes the **package manifest the authority** and fails the run before prepare
  if the orchestrator's earlier snapshot diverged.

Motion round-trip — **hard gate**, after `compile_take`:
- For a representative set of members, the `track.json` frame with `frame_index = p+1`
  has `object_transforms[*].transform[2][3] == dz[p]` (exact, within float tolerance)
  for all `p in 0..N-1`. The set MUST include, where present in the animated actor set, a
  nested member and a TL_Brep-converted member; member types not present in the live
  subset are covered by unit tests with synthetic `member_map` shapes (Section 10).

Camera round-trip — **hard gate**:
- `camera_frames` has length N, 1-based `frame_index`, and each entry equals the
  harvested camera at that frame (location/target/up/lens exact within tolerance).

## 9. Nested-instance semantics & the baked fallback

- **Nested:** if one top-level member's `definition_object_id` explodes into multiple
  created objects (`member_map` `created_object_ids` is a **list**), the member's track
  is resolved to **all** those created ids and applies **uniformly** — "move this member
  as a unit." This is correct for the band-peel wave (a member lifts as a whole) and is
  explicitly **not** per-leaf nested motion.
- **Baked fallback (only if the round-trip or frame-0 gate fails):** a documented
  escalation that writes per-object per-frame matrices directly at the
  `build_worker_object_frames` seam (`director_worker_compile.py:230/351`), keeping
  `resolve_worker_source_states` (the native pristine-bbox check cannot be fabricated)
  and full `derived_from` provenance. Not implemented in this slice unless a gate forces
  it; the declarative path is expected to hold for band-peel (frame 0 = rest, dense
  keyframes sample exactly).

## 10. Testing

Unit (no Rhino):
- `build_actor_member_ids` — def index → `member_{index:04d}` formatting; def_id lookup.
- `build_motion_json` — per-member track shape; keyframe `t` grid `= j/(N-1)`, `j=1..N-1`;
  omits `t=0`; one track per animated member; frame-0-rest assertion.
- `build_samples_artifact` / `assert_samples_invariants` — all Section 8 harvest gates:
  `frame_count >= 2` rejection (Finding 4); `ids_sha256` stability across frames (Finding
  2); duplicate `Ids` **and** duplicate generated `actor_member_id` rejection (Finding 1);
  non-top-level-id rejection; frame-0-rest.
- Manifest drift gate (Finding 3): a synthetic `scene_manifest.json` whose
  `{definition_object_id, definition_object_index, actor_member_id}` triple disagrees with
  the precomputed mapping must fail before prepare; a matching manifest passes.
- Nested + TL_Brep round-trip at the data level: synthetic `member_map` with a 1→N
  member and a converted member; assert the generated tracks resolve to all created ids
  and that a compiled track (via the real `compile_take` over a stubbed prepare result)
  yields `transform[2][3] == H_j` for each child.

Live gate (Rhino open, Pearson canvas loaded):
1. Apply the C42 `Ids` edit; verify `Ids` count `== H` count and the three output wires
   intact (Section 5).
2. Run the orchestrator for a short take (e.g. N=48) on the mullion actor set.
3. Assert: package/prepare/compile/capture/assemble succeed; **round-trip gate** passes
   on representative mullions; camera round-trip passes; `take.mp4` produced; **Pearson
   restored `modified:False`**.
4. Visual check: mullions peel band-by-band (not a uniform lift), camera follows the path.

Capacity check to confirm during planning: the worker compile path's animated-object cap
accommodates the mullion count (338) — the earlier 1066-object Pearson render passed the
worker path, so this is expected, but pin it (the 256 cap in `director_compiler
.validate_caps` is the legacy replay path, not the worker path).

## 11. Risks & open questions

- **C42 pin edit** may drop outgoing wires on recompile → mitigated by post-edit verify +
  `gh_edit` restore + `gh_undo` (Section 5). First live step, before any render.
- **Round-trip gate failure** (implicit-identity/easing edge, or a run not starting at
  rest) → baked fallback (Section 9). Expected not to trigger for band-peel.
- **Scene-bound capture throughput** (unchanged from prior findings): a full 240f Pearson
  take is a single-instance marathon; keep the live gate short (≤48–120f). The definitive
  fix is 4B (second-instance chunked capture), out of scope here.
- **Generality:** `FrameIn`/`Camera Controller` guids and the actor-set/block mapping are
  currently canvas-specific; the orchestrator reads what it can from the live canvas but
  full generalization (and MCP-tool promotion) is deferred with the template-promotion
  slice.

## 12. Files

- `mcp_server/src/rook/director_simulation_export.py` — **new** orchestrator + pure seams.
- `tests/…/test_director_simulation_export.py` — **new** unit tests (Section 10).
- C42 canvas script — **live edit** (not a repo file this slice; promoted next slice).
- Driver script (scratchpad or `scripts/`) — invokes the orchestrator for the live gate.
- **No changes** to `director_worker_compile.py`, `director_worker_prepare.py`,
  `director_compiler.py`, `camera_planner.py`, `director_take_package.py`, or native —
  unless the round-trip gate forces the baked fallback.
