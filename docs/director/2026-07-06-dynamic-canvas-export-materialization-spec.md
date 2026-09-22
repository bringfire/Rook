# Director Dynamic Canvas Export And Capture Materialization Spec

Status: provisional review draft
Date: 2026-07-06
Branch: `codex/director-canvas-export-spec`

## Purpose

This document captures the current working agreement for making Director behave like a Chirp-style dynamic system without turning it into an uncontrolled rewrite.

The immediate goal is to preserve the Grasshopper authoring model the prototype already demonstrates:

- Grasshopper coordinates timing, movement, actor sets, camera, controls, and preview.
- A movement component owns the scripted movement logic for one actor/object set.
- Multiple movement components may exist in one take.
- CanvasDirector Export assembles the total deterministic take.
- Director replay/capture continues to consume validated deterministic replay data.

This is not yet an implementation plan. It is a scope and contract draft to review before design/implementation.

## Confirmed Context

Live Grasshopper document inspected:

- `C:/Users/aryan/V2/animation test_smoke-01.gh`
- No Grasshopper errors or warnings at time of inspection.

The live prototype is already organized around:

- `Director Clock`
- `Director Timing Gate`
- `Director Oscillator`
- `Director Actors`
- `Director Band Peel Wave Preview`
- `Director Camera Path`
- `Director Camera Controller`
- `CanvasDirector Export:pearson_animation_test`

The live prototype currently has a mismatch:

- The movement component contains the real authored/previewed movement behavior.
- The export marker still emits a smoke-test simple vertical motion payload.

The practical missing bridge is therefore:

> Movement components need to emit an authoritative motion/take fragment, and CanvasDirector Export needs to assemble those fragments into a deterministic Director export.

## Historical Findings

The older prototype reference at:

- `H:/AI EXPERIMENTS/Pearson/ANIMATION/_rook_prototype_reference_20260702/.rook`

shows that prior Director planning was metadata-first.

Important historical notes:

- `rhino_director_prepare_take` was metadata-only.
- `rhino_director_materialize_take` did not exist.
- Full-model capture was done through a project-local helper script around metadata capture.
- Prior `director_takes` audit data recorded `materialized_record_count: 0`.
- The historical tooling register identified Director materialization as an open P1 gap.

Current v2 tooling exists for metadata:

- `rhino_director_capture_source_occurrence_v2`
- `rhino_director_write_actor_metadata_v2`
- `rhino_director_read_actor_metadata_v2`

Current reusable infrastructure also exists for document-bound metadata and geometry duplication:

- `/usertext/object-set` and `/usertext/object-get` can persist non-GUID object metadata on top-level document objects.
- `/usertext/document-set` and `/usertext/document-get` can persist document-level indexes or binding manifests.
- `/block/set-object-user-strings` and `/block/set-object-user-strings-batch` can stamp metadata onto block definition objects where needed.
- Existing block handlers contain exact duplication/materialization primitives that can be reused by Director-specific tools.

Current v2 tooling does not yet include:

- a Director actor binding/materialization tool,
- a Director actor binding query/rebuild tool,
- a Director actor-set materializer,
- a capture-scene duplicate creator,
- or a take-owned source-to-capture object mapping writer.

## Current Implementation Constraints

These are not accepted product limits. They are current implementation constraints that must be accounted for before implementation scope is finalized.

### Replay And Compile Scale Caps

The current Python compiler and native `/director/replay` path both cap one replay track at 256 animated objects:

- `mcp_server/src/rook/director_compiler.py` rejects `object_count > 256`.
- `src/RookNative/Handlers/DirectorReplayHandler.cpp` rejects `animated_object_ids` arrays larger than 256.

The Pearson band-peel actor grouping currently has 338 grouped members. If each member becomes its own top-level capture object, the current cap conflicts with the desired v1 Pearson proof.

This is a settled v1 scale gate:

- Director v1 targets a hard supported ceiling of 512 animated capture objects per take.
- The first required acceptance proof is the real Pearson 338-member actor set at target frame count.
- The current 256-object compiler and native replay caps are implementation guards to raise and prove, not product limits.
- A 1024-object run may be used as a measurement-only stretch test, but 1024 is not a v1 support contract unless separately proven and accepted.

The design distinguishes final capture support from interactive full-track replay preview support:

- V1 must support final capture for up to 512 animated capture objects per take.
- Interactive full-track preview through `/director/replay` may hit its existing 8 MiB request body cap before final capture does.
- That 8 MiB issue is an interactive `/director/replay` transport limitation, not a general replay or final-capture limitation, because final frame capture uses `/director/frame-capture` per frame and has a different payload profile.

Schema 2 should therefore remain a single take-level track/capture contract for v1. Sharded replay/capture is deferred and should only shape the schema if the 512-object proof fails.

Implementation signoff requires this scale proof:

> 338 members at the target frame count must compile and final-capture successfully, and interactive `/director/replay` behavior must either pass within the 8 MiB transport cap or fail with a documented transport limitation that does not weaken the 512 final-capture contract.

The proof must distinguish product support from implementation guards:

- 512 animated capture objects per take is the v1 final-capture support contract.
- The existing 256-object checks in the Python compiler and native replay handler are implementation guards that must be raised, parameterized, or bypassed for the final-capture path only after validation.
- Interactive full-track `/director/replay` remains a separate transport path. If it fails solely because the request exceeds the current 8 MiB limit before replay execution begins, it must return or report typed `replay_transport_limit_exceeded` with payload size, limit details, and limit source.
- `replay_transport_limit_exceeded` is valid only when the request body size exceeds the configured `/director/replay` transport limit before replay execution begins. Runtime failures, validation failures, object-count guard failures, malformed payloads, or native replay errors must use distinct diagnostics and do not preserve the interactive replay-preview claim.
- The diagnostic shape should include:

```json
{
  "code": "replay_transport_limit_exceeded",
  "payload_bytes": 10490000,
  "limit_bytes": 8388608,
  "limit_source": "DirectorReplayHandler.max_body_bytes",
  "final_capture_proven": true
}
```

`final_capture_proven` may be true only after the corresponding final-capture proof has passed for that take or test case. It must not mean merely that the code path intends to support final capture.

- The 512-object synthetic cap test must use 512 take-owned capture objects with real duplicated renderable geometry and normalized motion tracks. It may use simple identical lift tracks, but it must exercise capture object mapping, source-state snapshotting, compile, and final frame capture.

Required proof measurements:

- `director_compile_request_v1` size,
- interactive `/director/replay` request size,
- per-frame `/director/frame-capture` request size,
- compile duration,
- native replay setup duration,
- final frame capture duration,
- peak process memory or process memory delta during compile/replay/capture.

### Current Export Marker Shape

The checked-in `export_marker.cs` currently accepts one `Motion` input with `metadata_kind: director_motion_payload`, writes `schema_version: 1`, uses `template_id: canvas_director.basic_motion`, and emits `payload.motion`.

The proposed take-assembler export is therefore a breaking schema transition unless compatibility is specified.

The v1 compatibility decision is:

- persist schema 2 as the authoritative authoring/take export with `motion_fragments`, validation, provenance, and take-level references,
- persist a separate normalized `director_compile_request_v1` artifact with its own schema, version, and hash after actor binding reconciliation and capture-scene materialization,
- have `director_compile_request_v1` carry enough source hashes to prove which schema 2 export, actor binding manifest, capture scene manifest, materialization policy, and compiler version produced it,
- keep schema 1 compatibility as compiler-facing adapter vocabulary where needed, not as a co-equal authoring format.

The current recommendation is:

> CanvasDirector Export vNext should emit schema 2 for authoring provenance and validation. The Python extraction/compile-prep layer should derive and persist a separate normalized `director_compile_request_v1` artifact after actor binding and capture materialization.

## Key Decisions So Far

### 1. Movement Component Role

A movement component is not universal. It is a generated or updated scripted strategy component for one actor/object set.

Example user intent:

> Lift and rotate these pieces over the animation.

Expected result:

- The movement component receives actor payload, timing state, oscillator/modulator values, and canvas controls.
- The movement component contains the custom scripted behavior for that actor set.
- The movement component previews the result in Grasshopper.
- The movement component emits an authoritative motion fragment for export.

### 2. Grasshopper Is The Coordinator

The Grasshopper definition is the orchestration surface.

It coordinates:

- actor metadata inputs,
- local timing and delays,
- oscillator/time remapping,
- movement-specific parameters,
- camera controls,
- preview,
- and export.

This reduces the need for a large generic animation composition engine in v1.

### 3. Multiple Movement Components Are Allowed

The correct v1 rule is:

> Multiple movement components are allowed, but their ownership claims must be disjoint unless an explicit later composition mode is introduced.

This means:

- one movement component owns one actor set,
- many movement components can exist in one take,
- no two movement components can claim the same canonical source member occurrence,
- no two movement components can claim the same materialized capture object,
- export should fail loudly on conflicts.

Actor-set id disjointness is not sufficient by itself. Two actor sets may overlap through members, grouping refs, nested occurrence paths, or materialization into the same capture objects.

No v1 support for:

- additive transforms,
- blending,
- ordering/layering transforms on the same actor,
- or overlapping motion ownership.

### 4. CanvasDirector Export Becomes A Take Assembler

The export marker should stop inventing motion.

Its role should become:

- receive actor payloads and/or actor refs,
- receive one or more movement fragments,
- receive camera fragment/state,
- receive timeline/resolution,
- validate fragment compatibility,
- validate disjoint canonical source-member movement ownership,
- emit one deterministic Director export.

### 5. Deterministic Replay Target Remains Valid

The deterministic replay/capture contract is not the uncertain part.

The existing direction remains:

- compile/export to deterministic replay data,
- replay validated transforms/camera instructions,
- capture frames,
- assemble video.

The current missing piece is the bridge from authored GH movement behavior to the deterministic replay payload.

Keeping the deterministic replay/capture contract is a goal, but the current 256-object guards must be raised and proven for the v1 512-object final-capture contract. If the 512 proof fails, sharded replay/capture becomes a fallback design decision; it should not shape the first schema 2 contract.

### 6. Capture Objects Must Be Exact Duplicates

The capture scene must not use bounding boxes or simplified proxy geometry.

Use the term:

> capture-scene duplicate

Avoid the term:

> proxy

The invariant should be:

> Every animated capture object is real duplicated renderable geometry derived from the source actor member, with material, layer, object attributes, and provenance preserved as far as Rhino allows.

### 7. Do Not Destructively Explode The Authoring Model

The source Rhino model and block hierarchy should remain the authoring truth.

Director should create take-owned capture duplicates when needed, rather than destructively exploding the working model.

### 8. Document-Bound Actor Binding Layer

Director v1 should introduce a document-bound actor binding layer.

Binding records durable actor membership on Rhino objects using Rook-owned metadata. Rhino GUIDs are current-document runtime handles, not durable actor identity.

Binding behavior:

- Existing top-level animatable objects are tagged in place.
- Non-top-level actor members may be materialized into persistent exact design-time actor objects and then tagged.
- Binding metadata records actor identity and grouping only.
- Binding metadata must not encode movement behavior, take-specific timing, easing, or animation strategy.
- Binding remains separate from take-time capture duplication.

Design-time bound objects are a rebuildable binding/cache layer, not a second source authoring model. The authority remains `.rook` actor metadata plus Rook-owned object metadata in the current document.

Binding reconciliation authority:

- `.rook` actor metadata is the durable expected membership and grouping record.
- Rhino object metadata is current-document binding evidence.
- Fresh reconciliation from `.rook` actor metadata plus current Rhino object metadata is the authoritative current GUID map.
- After successful reconciliation, Director may persist the binding manifest as a `.rook` artifact for audit, debugging, reproducibility, and downstream take assembly.
- A persisted binding manifest is not authoritative if the document has changed. It must carry document and binding fingerprints so it can be invalidated.
- Export/capture must not trust an old persisted GUID map without revalidation.
- Duplicate objects claiming the same actor member id are a hard conflict.
- Objects with Director actor metadata that do not match the current `.rook` actor metadata are stale/orphan bindings and must be reported.

## v1 Pipeline Decision

Materialization is an explicit document-mutating step after export assembly and actor binding reconciliation, before compile.

Recommended pipeline:

```text
CanvasDirector Export assembly
  -> validate fragments/ownership
  -> reconcile document-bound actor bindings
  -> prepare/materialize take-owned capture scene
  -> write capture scene + role-aware visibility manifests
  -> compile against capture object ids
  -> replay/final capture
```

Rationale:

- compile currently needs concrete top-level object ids and source state,
- actor metadata in `.rook` is planning/source truth, while compile/replay need current top-level document object ids,
- object metadata lets Director rebuild the current GUID map after file copy/save/import drift,
- export assembly stays a pure Grasshopper/data operation,
- hiding materialization inside compile would make compile mutate Rhino document state,
- lazy final-capture materialization would hide risky document mutation inside the longest-running step and cause late failures for unsupported geometry, nested references, visibility conflicts, or bbox proof,
- cleanup, source visibility, idempotency, and retry behavior need their own explicit contract,
- the capture scene manifest is the bridge from source actor metadata to replay object ids.

## Decision Log

The following decisions are considered settled for the next design pass unless new implementation evidence contradicts them.

| ID | Decision | Rationale | Implication |
| --- | --- | --- | --- |
| DEC-001 | Director should follow a Chirp-like dynamic pattern, but with Director-specific constraints. | The stable shell/dynamic body pattern fits, but Director spans GH, Python, managed extraction, native replay, and Rhino document state. | Do not copy Chirp directly; define Director-specific contracts for movement fragments, export assembly, and capture materialization. |
| DEC-002 | `transform.cs` is not the universal movement function. | The current file was a simplified prototype/test path, while the live GH prototype shows movement logic belongs in generated or updated movement components. | Treat movement scripts as strategy bodies for specific actor sets. |
| DEC-003 | Grasshopper is the primary animation coordinator. | The prototype already coordinates clock, timing gate, oscillator, actors, movement, camera, preview, and export on canvas. | Avoid building a broad generic animation graph/composition engine before it is needed. |
| DEC-004 | A movement component owns the scripted logic for one actor set. | The user expects requests such as lift/rotate/peel to be encoded into that component's C# body and tuned by canvas controls. | Generated movement components should expose stable pins and emit preview plus authoritative export data. |
| DEC-005 | Multiple movement components are supported only for disjoint canonical source member ownership in v1. | Actor-set ids alone are not enough because actor sets, grouping refs, nested occurrence paths, or materialization output can overlap. | CanvasDirector Export must reject duplicate source-member ownership; compile/materialization must also reject duplicate capture-object ownership. |
| DEC-006 | CanvasDirector Export should be a take assembler, not a motion author. | The live export marker currently emits hardcoded simple motion while the movement component contains real behavior. | Export should gather motion fragments, actor metadata, camera, timeline, and validation results. |
| DEC-007 | Deterministic replay remains the final execution target, but current 256-object guards must be raised and proven. | Prior tests validated the replay/compile/capture direction, but current compiler/native guards reject more than 256 animated objects and Pearson has 338 grouped members. | Do not introduce arbitrary runtime C# execution as the final native replay mechanism for v1. Raise/prove the guards for the v1 512-object final-capture contract before claiming Pearson support. |
| DEC-008 | Animated capture objects must be exact duplicated renderable geometry. | Bounding boxes, simplified meshes, or alternate proxies would not satisfy visual fidelity requirements. | Use the term capture-scene duplicate; preserve geometry and attributes as far as Rhino allows. |
| DEC-009 | Source model/block hierarchy should not be destructively exploded for authoring. | The source model remains the durable authoring truth, and generic `/block/explode` deletes the original instance. | Build a Director-specific materialization step that creates take-owned duplicates and provenance mappings. |
| DEC-010 | Current v2 tooling covers metadata capture, not capture-scene materialization. | `rhino_director_capture_source_occurrence_v2` and actor metadata tools exist; historical notes show materialization remained an open gap. | Add a durable v2 materializer rather than assuming the old prepare/capture flow already creates animatable objects. |
| DEC-011 | Materialization is an explicit step between export extraction and compile. | Compile needs concrete document object ids and source state; hiding materialization inside compile would make compile mutate the Rhino document. | Add a dedicated capture-scene preparation/materialization tool and manifest before replay compile. |
| DEC-012 | v1 motion fragments use deterministic expanded keyframes as the authoritative contract. | Strategy descriptors alone require Python to reimplement every generated C# strategy; baked per-frame matrices are large and harder to validate. Simple transforms and complex strategies both need the same deterministic boundary. | Use descriptors as provenance; allow shared `track_id` references to avoid duplicate identical tracks; resolve every claimed member to concrete compiler keyframes before compile; use baked frames only as an opt-in fallback with explicit size/cap checks. |
| DEC-013 | Source visibility changes must be role-aware and reversible for capture. | Leaving non-capture source objects visible risks double-rendering when exact capture duplicates are animated. The risky objects may be source top-level objects, persistent design-time actor objects, or both. | Materialization should create Director-owned take layers and record exactly which non-capture objects were hidden, their role, the reason, and the prior visibility state for restore. |
| DEC-014 | Nested `InstanceReference` members use proof-gated preserve-as-instance mode in v1. | Native code can recreate instance references with `CreateInstanceObject` while preserving the referenced definition and composed transform, but bbox validation alone is insufficient because different definitions can share the same bbox. Recursive leaf expansion needs stronger actor metadata and is not a silent fallback. | Existing top-level geometry is tagged in place; block-definition geometry members become exact design-time geometry duplicates; nested instance members become top-level instance-reference duplicates only when definition identity, composed transform, key render attributes, tight bbox, and non-zero-frame replay transform proof all pass. If any proof cannot be implemented reliably for Pearson, v1 rejects nested instance actors with typed failure diagnostics rather than flattening. |
| DEC-015 | Director v1 targets 512 animated capture objects per take. | Pearson needs the real 338-member actor set, while 1024 would turn v1 into a broader performance program before measurements justify it. | Raise/prove the current 256-object guards. Keep schema 2 as a single take-level track/capture contract. Treat `/director/replay` 8 MiB failures as interactive transport limitations unless final capture also fails. |
| DEC-016 | Director v1 introduces a document-bound actor binding layer. | `.rook` actor metadata is durable planning/source truth, but compile/replay need current document object ids and Rhino GUIDs can drift after file copy/save/import. | Stamp actor membership and grouping metadata onto existing top-level animatable objects; create persistent exact design-time actor objects only when members are not already individually animatable top-level objects; never encode movement behavior there; keep take-time capture duplicates separate. |
| DEC-017 | Fresh binding reconciliation is authoritative; persisted binding manifests are audit/cache artifacts. | Rhino GUID drift, file copy/import, deleted design-time actors, and duplicate stale objects mean old GUID maps cannot be trusted blindly. | Generate the current binding manifest from `.rook` actor metadata plus current object metadata whenever export/capture needs it. Persist successful manifests only with document/binding fingerprints and revalidate before reuse. |
| DEC-018 | V1 binding fingerprints are small, metadata-centered, and use tight bbox as drift evidence. | Full geometry hashes are potentially expensive and brittle, while fresh reconciliation remains authoritative. The drift modes to catch are wrong document, changed actor metadata, changed binding policy, missing objects, duplicate claims, object metadata mismatch, and obvious object changes. | Revalidate persisted binding manifests using source document, actor metadata, binding policy, per-member `director_metadata_hash`, object type, layer/name evidence, tight bbox fingerprint, and binding-kind-specific evidence. Bbox is never durable identity. |
| DEC-019 | Actor binding fingerprints come from a new Director-specific native route. | `/director/object-states` is compiler/replay-oriented and does not expose the document metadata, layer/name/type evidence, bbox policy details, or instance-reference definition/transform fields binding reconciliation needs. | Add batch route `POST /director/actor-binding/object-fingerprints`. Native reports current document facts and may reuse the existing `DirectorObjectPoseBbox` tight-bbox calculation path where useful, but not its fallback pass semantics. Python owns reconciliation, canonical metadata hashing, and binding-manifest persistence. A separate candidate-discovery step must supply object ids carrying Director actor metadata. |
| DEC-020 | Actor binding candidate discovery uses a narrow Director-specific native route. | `/usertext/object-get` requires a known object id, `/objects` does not expose user strings, and `/scene/graph/query` is a broad scene-index query rather than a sanctioned Director metadata namespace scan. | Add `POST /director/actor-binding/query-candidates`. Native scans only Rook-owned Director actor-binding metadata on active document objects and returns candidate ids plus minimal binding metadata facts. Python still owns `.rook` reconciliation, final stale/orphan diagnostics, and persistence. |
| DEC-021 | V1 authoritative bbox comparisons require tight object bounding boxes. | Repeated-run comparison with loose/cached object bboxes has already proven unstable for the same objects. | `bbox_method: "tight_object"` plus `validation_strength: "tight_bbox"` is the only bbox-based pass state. Loose/cached bbox data may be diagnostic only. If tight bbox cannot be produced, binding drift checks, capture duplicate proof, and replay validation fail unless another explicit proof mechanism is added. |
| DEC-022 | Take-owned capture duplicates are created by an explicit prepare-capture-scene step before compile. | Export assembly should remain pure GH/data work, compile should remain deterministic translation, and final capture should not hide the riskiest document mutation inside the longest-running step. | Add `rhino_director_prepare_capture_scene_v2` or equivalent. It is document-mutating, uses `take_id`/`capture_scene_id` as the ownership key, supports clear create/reuse/replace modes, writes capture scene and role-aware visibility manifests, ties the capture scene to the reconciled actor binding manifest, and maps canonical actor members to concrete capture object ids. Reuse validity requires hash/proof revalidation; compile and final capture consume the manifest and must not create capture duplicates implicitly. |
| DEC-023 | Mixed-block source visibility is unsupported in v1 unless the source top-level object is proven actor-only. | If an actor member comes from inside a source block that also contains non-actor renderable context, hiding the source top-level block prevents double-rendering but can remove required context from the shot. | Materialization preflight fails with `source_visibility_scope_unsupported` unless every renderable member under the source top-level object is represented in the actor binding manifest for the take, or is explicitly non-renderable/hidden before materialization. If Director cannot enumerate that source scope reliably, preflight fails. Static non-actor context materialization is deferred unless the Pearson proof requires it and explicitly expands the contract. |
| DEC-024 | Cleanup is an explicit operation scoped to a `take_id`/`capture_scene_id`, and restores visibility before removing capture duplicates. | Generated capture duplicates are safe to remove only when Director ownership metadata and the manifest agree. Restoring source/design-time visibility first leaves the user scene visible if duplicate removal/archive fails. | Cleanup first restores source/design-time visibility using the recorded mechanisms, then removes or archives only objects carrying `take_owned_capture_duplicate` metadata for the same capture scene. The manifest must record cleanup order. Missing or inconsistent manifests/ownership metadata produce typed conflicts rather than guessed cleanup. |
| DEC-025 | Schema 2 is the authoritative authoring/take export, and v1 persists a normalized compile request as a separate artifact. | The Grasshopper export marker cannot know final capture object ids because those exist only after actor binding reconciliation and capture-scene materialization. Persisting the compile request makes Pearson-scale debugging and deterministic replay audits reproducible. | CanvasDirector Export preserves only schema 2 authoring/take data. The Python extraction/compile-prep layer derives and persists `director_compile_request_v1` after binding/materialization. The compile request records hashes/refs for the schema 2 export, actor binding manifest, capture scene manifest, materialization policy, and compiler version. Schema 1 motion shape is allowed only inside this compile adapter where needed by existing compiler code. |
| DEC-026 | The 512-object v1 contract is a final-capture support contract, not an interactive full-track replay transport guarantee. | Final frame capture uses `/director/frame-capture` per frame and has a different payload profile from interactive `/director/replay`, which can hit the current 8 MiB request limit first. | Implementation must raise or parameterize the 256-object compiler/native guards for final capture, prove the Pearson 338-member take at target frame count, and run a structurally representative 512-object synthetic cap test using real duplicated renderable capture geometry and normalized motion tracks. `replay_transport_limit_exceeded` is valid only when request body size exceeds the configured `/director/replay` transport limit before replay execution begins; all other replay failures need distinct diagnostics and do not preserve the interactive preview claim. The proof must include size, duration, and memory measurements rather than only a pass/fail run. |
| DEC-027 | First implementation is multi-fragment/multi-actor capable, but the first end-to-end proof uses one real Pearson actor set. | Keeping the data contracts multi-actor avoids painting the system into a single-set corner, while validating first on one real Pearson actor set keeps the implementation path narrow. Multi-actor assembler completeness needs a separate proof from Pearson scale and 512 cap/performance. | Implement export/compile/materialization contracts to allow multiple disjoint actor sets and fragments. Validate the first production path with one Pearson actor set. Do not claim export assembler completeness until a second small disjoint actor set also passes assembly, ownership validation, materialization mapping, compile request generation, and final capture/replay proof. Keep Pearson proof, assembler proof, and 512 cap proof as separate acceptance gates. |

Deferred decisions:

- The exact code changes and measured runtime/payload impact required to raise the implementation guards from 256 to 512 must be verified during implementation.
- `director_compile_request_v1` optional fields beyond the required v1 baseline, canonical JSON hash implementation details, and schema 1 compiler-facing adapter migration tests still need design confirmation.
- Whether generated capture objects live only in the active document or in a saved duplicated capture `.3dm` remains open.

## Proposed Runtime Shape

Authoring/canvas side:

```text
.rook actor metadata -> document-bound actor binding -> Director Actors A -> Movement A -> Motion Fragment A + ownership claims
.rook actor metadata -> document-bound actor binding -> Director Actors B -> Movement B -> Motion Fragment B + ownership claims
.rook actor metadata -> document-bound actor binding -> Director Actors C -> Movement C -> Motion Fragment C + ownership claims

Director Clock / Timing Gate / Oscillator -> movement controls
Director Camera Path / Controller -> Camera Fragment

CanvasDirector Export
  -> validates fragments
  -> checks disjoint source-member ownership
  -> emits deterministic Director export
```

Capture/replay side:

```text
Director export/spec
  -> reconcile document-bound actor bindings
  -> prepare/materialize take-owned capture scene
  -> write capture scene + role-aware visibility manifests
  -> check disjoint capture-object ownership
  -> compile movement fragments against capture object ids
  -> replay deterministic track
  -> capture frames
  -> assemble video
```

## Proposed Data Contracts

### Director Actor Runtime Payload

Already present in the prototype through `Director Actors`.

Core fields currently observed:

- `schema_version`
- `metadata_kind: director_actor_runtime_payload`
- `actor_set_ref`
- `actor_grouping_ref`
- `resolved_actor_set_path`
- `resolved_actor_grouping_path`
- `grouping_kind`
- `actor_set_id`
- `member_count`
- `resolved_count`
- `group_count`
- `grouped_member_count`
- `band_count`
- `band_member_count`
- `cache_key`
- `source_occurrence`
- `source_take_context`

This component is the boundary between project metadata and the GH canvas.

### Director Motion Fragment v1

New proposed output from movement components.

V1 default representation:

- expanded keyframes in the compiler vocabulary,
- grouped or per-member tracks are allowed,
- members may share a keyframe track by explicit `track_id` reference,
- every claimed member must resolve to concrete keyframes before compile,
- strategy descriptors are provenance only,
- baked per-frame transforms are an opt-in fallback with explicit payload/cap checks.

Director v1 does not prefer complex movement strategies over simple transforms. A simple lift/rotate movement is valid if it emits the same authoritative `director_motion_fragment_v1` contract: canonical source-member ownership plus deterministic expanded keyframes. Members may share a keyframe track by explicit `track_id` reference, but every claimed member must resolve to concrete keyframes before compile. Strategy descriptors are provenance only.

A fragment must not collapse actor/member-specific behavior into an opaque actor-set-level transform unless the export also provides an explicit member-level expansion that preserves the authored behavior. For a simple transform, that expansion may assign the same track to every claimed member. For band peel, it must preserve per-band/per-member phase.

Draft fields:

```json
{
  "schema_version": 1,
  "metadata_kind": "director_motion_fragment_v1",
  "fragment_id": "roof_peel_001",
  "actor_set_id": "roof_uplift_vertical_test_chunk_001",
  "actor_set_ref": ".rook/director_planning/actor_sets/roof_uplift_vertical_test_chunk_001.json",
  "actor_grouping_ref": ".rook/director_planning/actor_sets/roof_uplift_vertical_test_chunk_001_subsets/same_orientation_mullions_001_band_sets/same_orientation_mullions_001_bands_001.json",
  "ownership_claims": [
    {
      "canonical_source_member_occurrence_id": "occurrence-path-hash-or-stable-member-id",
      "actor_member_ordinal": 47,
      "definition_object_id": "<guid>",
      "source_occurrence_path": []
    }
  ],
  "track_library": {
    "band_088_lift": {
      "keyframes": [
        {
          "t": "0.0",
          "translate": [0, 0, 0]
        },
        {
          "t": "1.0",
          "translate": [0, 0, 12000],
          "ease_from_previous": "ease_in_out"
        }
      ]
    }
  },
  "member_tracks": [
    {
      "canonical_source_member_occurrence_id": "occurrence-path-hash-or-stable-member-id",
      "group_id": "same_orientation_mullions_001__band_088",
      "track_id": "band_088_lift"
    }
  ],
  "strategy_provenance": {
    "nickname": "Director Band Peel Wave Preview",
    "strategy": "band_peel_wave",
    "script_sha256": "<sha>",
    "inputs_sha256": "<sha>"
  },
  "parameters": {
    "max_height": 12000,
    "spread_bands": 16,
    "local_t_source": "Director Oscillator.Value"
  },
  "validation": {
    "status": "ok",
    "member_count": 338,
    "warnings": []
  }
}
```

Required behavior:

- A fragment must not lose actor/member/group phase behavior.
- Simple transforms are first-class movement strategies; they still emit member ownership and deterministic expanded keyframes.
- A shared track library may de-duplicate identical keyframes, but unresolved `track_id` references are invalid.
- A fragment must identify each canonical source member occurrence it claims.
- A fragment must provide enough expanded keyframe data for Python to compile without reimplementing the generated C# strategy body.
- Strategy names/descriptors can explain how tracks were generated, but cannot be the only deterministic motion source in v1.

### CanvasDirector Export vNext

Draft payload shape:

```json
{
  "metadata_kind": "rook.canvas_director.export",
  "schema_version": 2,
  "export_id": "pearson_animation_test",
  "proposal_id": "pearson_v2_smoke",
  "template_id": "canvas_director.take_assembler",
  "template_version": "0.2.0",
  "payload": {
    "timeline": {
      "fps": 24,
      "frame_count": 240
    },
    "resolution": {
      "width": 1280,
      "height": 720
    },
    "actor_sets": [],
    "motion_fragments": [],
    "camera": {},
    "validation": {
      "ownership": "disjoint_canonical_source_members",
      "status": "ok",
      "errors": [],
      "warnings": []
    }
  }
}
```

Export marker responsibilities:

- Parse all connected motion fragments.
- Parse camera fragment/state.
- Parse actor runtime payloads as needed.
- Validate each fragment has an actor set and ownership claims.
- Validate canonical source member occurrence ownership is disjoint.
- Validate each fragment is internally well-formed.
- Preserve only schema 2 authoring/take data, including `motion_fragments`, validation diagnostics, provenance, camera/timeline state, and take-level refs.
- Do not emit normalized compiler `payload.motion` from the Grasshopper export marker.
- Emit a clear error/diagnostic output if validation fails.

Compatibility policy:

- Schema 2 is the authoritative persisted authoring/take export.
- Schema 2 export adds `motion_fragments`, validation, provenance, and capture-scene materialization inputs.
- The Python extraction/compile-prep layer derives the normalized compiler payload after actor binding reconciliation and capture-scene materialization.
- The normalized compiler payload is persisted as a separate `director_compile_request_v1` artifact with its own schema/version/hash.
- `director_compile_request_v1` records refs/hashes for the schema 2 export, actor binding manifest, capture scene manifest, materialization policy, and compiler version.
- Schema 1 `payload.motion` remains compiler-facing adapter vocabulary for existing tests and callers during migration, not a co-equal authoring format.

### Director Compile Request v1

New proposed artifact persisted by the Python extraction/compile-prep layer after actor binding reconciliation and capture-scene materialization.

Minimum draft fields:

```json
{
  "metadata_kind": "director_compile_request",
  "schema_version": 1,
  "compile_request_id": "pearson_animation_test_compile_001",
  "take_id": "pearson_animation_test_take_001",
  "capture_scene_id": "pearson_animation_test_capture_001",
  "source_export_ref": ".rook/director_exports/pearson_animation_test.schema2.json",
  "source_export_hash": "<hash>",
  "actor_binding_manifest_ref": ".rook/director_binding_manifests/pearson_animation_test_binding_001.json",
  "actor_binding_manifest_hash": "<hash>",
  "capture_scene_manifest_ref": ".rook/director_capture_scenes/pearson_animation_test_capture_001.json",
  "capture_scene_manifest_hash": "<hash>",
  "materialization_policy_hash": "<hash>",
  "compiler_version": "<version>",
  "compile_adapter_version": "<version>",
  "transform_semantics": "absolute_from_source",
  "timeline": {
    "fps": 24,
    "frame_count": 240
  },
  "resolution": {
    "width": 1280,
    "height": 720
  },
  "camera": {},
  "motion": [
    {
      "track_id": "roof_lift_track_001",
      "target_capture_object_id": "<take-owned capture object guid>",
      "canonical_source_member_occurrence_id": "<id>",
      "actor_member_id": "<id>",
      "transform_semantics": "absolute_from_source",
      "keyframes": []
    }
  ],
  "source_state_snapshot_ref": ".rook/director_source_states/pearson_animation_test_compile_001_source_states.json",
  "source_state_snapshot_hash": "<hash>",
  "validation_counts": {
    "source_members": 338,
    "capture_objects": 338,
    "tracks": 338,
    "frames": 240,
    "cap_status": "within_v1_512_final_capture_contract"
  }
}
```

Compile request invariant:

- A `director_compile_request_v1` artifact is invalid unless every normalized motion target is a take-owned capture object present in the referenced capture scene manifest.
- Normalized `motion` may use schema 1-compatible compiler vocabulary internally, but all targets must be capture object ids, not source document object ids, actor member ids, or block definition ids.
- V1 compile requests require top-level `transform_semantics: "absolute_from_source"`. Track-level `transform_semantics` should be omitted in v1; if present for diagnostics or adapter compatibility, it must match the top-level value exactly. V1 has no transform-semantics override behavior.
- Each normalized motion item must carry enough provenance to debug and validate the target mapping at scale: `target_capture_object_id`, `canonical_source_member_occurrence_id`, and `actor_member_id`.
- `source_state_snapshot_ref` and `source_state_snapshot_hash` are required in v1. The snapshot identifies the exact source/capture object state baseline used by compile/replay audits.

Source-state snapshot minimum:

- The source-state snapshot must include baseline object states for every `target_capture_object_id` referenced by normalized motion.
- Each baseline state must identify the capture object id, source/canonical member provenance when available, transform/source transform state needed by `absolute_from_source` compile/replay, and tight-bbox proof metadata where relevant.
- The snapshot must record the source-state route/tool name and version used to capture it, such as `/director/object-states` plus the Director/Rook tool version.
- If source-state capture uses compatibility fields such as `bbox_only`, the compile request may use those fields as replay source-state data, but not as v1 binding/capture proof unless the separate tight-bbox proof contract is satisfied.

Hashing rule:

- Artifact hashes are computed over canonical JSON with sorted object keys, UTF-8 encoding, stable numeric formatting, and arrays kept in semantic order.
- Semantic order means arrays such as motion tracks, keyframes, actor members, capture objects, and validation diagnostics remain in their authored or compiler-significant order rather than being sorted for hashing.
- Stable numeric formatting means finite JSON numbers only; `NaN`, `Infinity`, and `-Infinity` are invalid. Producers must not emit insignificant trailing zeros, and fixed rounding is allowed only where the producing contract already requires rounding, such as bbox fingerprint tolerances.

### Actor Binding Manifest v1

New proposed artifact generated by fresh reconciliation before export/capture. It may be persisted under `.rook` for audit/cache purposes, but it is not authoritative without revalidation.

Authority model:

- `.rook` actor metadata defines expected members and groupings.
- Rhino object metadata proves current-document bindings.
- The binding manifest records the validated current GUID map.
- Persisted binding manifests must carry enough fingerprints to detect document or binding drift.
- A persisted binding manifest is reusable only after revalidation against the current document.
- Missing objects, duplicate member claims, actor metadata hash mismatches, object metadata mismatches, or binding-kind evidence mismatches invalidate the manifest and require fresh reconciliation or rebind.
- `actor_set_id`, `actor_member_id`, and `director_metadata_hash` are the identity check.
- Object type, layer/name evidence, and bbox are drift evidence.
- Bbox alone must never be used as durable identity.

Draft fields:

```json
{
  "schema_version": 1,
  "metadata_kind": "director_actor_binding_manifest",
  "actor_binding_id": "roof_uplift_vertical_test_chunk_001_binding_001",
  "actor_set_id": "roof_uplift_vertical_test_chunk_001",
  "actor_set_ref": ".rook/director_planning/actor_sets/roof_uplift_vertical_test_chunk_001.json",
  "source_document": {
    "path": "<active .3dm path>",
    "runtime_serial": "<optional>",
    "document_fingerprint": {
      "source_document_fingerprint": "<hash>",
      "path": "<active .3dm path>",
      "runtime_serial": "<optional>",
      "modified_timestamp": "<optional>",
      "director_binding_namespace": "rook.director.binding",
      "director_binding_namespace_version": 1
    }
  },
  "reconciliation": {
    "mode": "fresh_from_actor_metadata_and_object_metadata",
    "status": "ok",
    "generated_at_utc": "<timestamp>",
    "actor_metadata_fingerprint": {
      "sha256": "<hash>",
      "actor_set_ref": ".rook/director_planning/actor_sets/roof_uplift_vertical_test_chunk_001.json",
      "actor_grouping_ref": ".rook/director_planning/actor_sets/roof_uplift_vertical_test_chunk_001_subsets/same_orientation_mullions_001_band_sets/same_orientation_mullions_001_bands_001.json",
      "source_occurrence_snapshot_ref": ".rook/director_planning/selection_snapshots/source_occurrence_roof_uplift_vertical_test_chunk_001.json"
    },
    "binding_policy_fingerprint": {
      "sha256": "<hash>",
      "binding_schema_version": 1,
      "binding_policy_version": "director_actor_binding_v1",
      "rook_director_tool_version": "<optional>"
    },
    "object_binding_fingerprint": "<hash>",
    "member_count_expected": 338,
    "member_count_bound": 338,
    "stale_binding_count": 0,
    "duplicate_claim_count": 0,
    "warnings": []
  },
  "members": [
    {
      "canonical_source_member_occurrence_id": "occurrence-path-hash-or-stable-member-id",
      "actor_member_id": "roof_uplift_vertical_test_chunk_001_member_047",
      "actor_member_ordinal": 47,
      "current_object_id": "<current top-level guid>",
      "binding_kind": "top_level_instance_reference_duplicate",
      "group_ids": ["same_orientation_mullions_001__band_088"],
      "object_type": "InstanceReference",
      "object_name": "<name>",
      "layer": {
        "full_path": "Director::Actors::roof_uplift_vertical_test_chunk_001",
        "layer_id": "<optional>"
      },
      "bbox_fingerprint": {
        "bbox_method": "tight_object",
        "tight_bbox_min": [0, 0, 0],
        "tight_bbox_max": [100, 100, 100],
        "model_units": "<units>",
        "rounding_policy": "round_to_4_decimal_places",
        "bbox_tolerance": "<tolerance>",
        "validation_strength": "tight_bbox"
      },
      "director_metadata_hash": "<hash-of-director_metadata-excluding-runtime-guid-fields>",
      "source_occurrence_path": [],
      "definition_object_id": "<guid>",
      "world_transform_chain": [],
      "binding_kind_evidence": {
        "referenced_block_definition_id": "<guid>",
        "referenced_block_definition_name": "<block-name>",
        "composed_instance_transform_hash": "<hash>",
        "matrix_tolerance_policy": {
          "name": "matrix_abs_tolerance",
          "value": 1e-9
        }
      },
      "validation_evidence": {
        "object_metadata_match": true,
        "grouping_match": true,
        "fingerprint_match": true,
        "attributes_preserved": true,
        "instance_definition_preserved": true,
        "composed_transform_preserved": true,
        "nested_instance_reference_proof": {
          "source_definition_id": "<guid>",
          "source_definition_name": "<block-name>",
          "capture_definition_id": "<guid>",
          "capture_definition_name": "<block-name>",
          "composed_source_transform_hash": "<hash>",
          "capture_instance_transform_hash": "<hash>",
          "matrix_tolerance": {
            "name": "matrix_abs_tolerance",
            "value": 1e-9
          },
          "attribute_preservation": {
            "layer": "preserved",
            "material_source": "preserved",
            "material_index": "preserved",
            "color_source": "preserved",
            "color_value": "preserved",
            "name": "preserved",
            "visibility": "preserved",
            "user_strings": "preserved"
          },
          "tight_bbox_before": {
            "bbox_method": "tight_object",
            "tight_bbox_min": [0, 0, 0],
            "tight_bbox_max": [100, 100, 100]
          },
          "tight_bbox_after": {
            "bbox_method": "tight_object",
            "tight_bbox_min": [0, 0, 0],
            "tight_bbox_max": [100, 100, 100]
          },
          "replay_probe_frames": [
            {
              "frame": 12,
              "bbox_method": "tight_object",
              "status": "passed"
            }
          ]
        }
      }
    }
  ]
}
```

Allowed `binding_kind` values:

- `tagged_existing_top_level`
- `exact_geometry_duplicate`
- `top_level_instance_reference_duplicate`

Minimum v1 fingerprint set:

- `source_document_fingerprint`: active `.3dm` path when available, document runtime serial, document modified timestamp if available, and document user-text binding namespace/version.
- `actor_metadata_fingerprint`: hash of the `.rook` actor set ref, grouping ref, and source occurrence snapshot ref used for reconciliation.
- `binding_policy_fingerprint`: binding schema version, materialization/binding policy version, and Rook/Director tool version if available.
- Per member: `actor_set_id`, `actor_member_id`, `binding_kind`, current `object_id`, object type, object name, layer full path or id/path, tight bbox fingerprint, Python-computed `director_metadata_hash` excluding runtime GUID fields, and binding-kind-specific evidence.

Binding-kind-specific evidence:

- `exact_geometry_duplicate`: source occurrence/member ref and source geometry fingerprint if available.
- `top_level_instance_reference_duplicate`: referenced block definition id/name plus composed instance transform hash.

V1 does not require a full geometry hash unless a cheap existing route can supply it. Full geometry hashing is deferred because it may be expensive and brittle.

Tight bbox policy:

- V1 binding fingerprints use the object's tight bounding box for every authoritative bbox comparison.
- The manifest must record `bbox_method`, rounded `tight_bbox_min`, rounded `tight_bbox_max`, model units, and the bbox tolerance/rounding policy.
- `bbox_method: "tight_object"` is required for any bbox-based pass.
- `validation_strength: "tight_bbox"` is the only bbox-based pass state.
- Loose/object cached bbox results are diagnostic only. They must not pass binding drift checks, capture duplicate proof, or replay validation.
- If tight bbox cannot be computed, the route must report `bbox_method: "unavailable"` or `validation_strength: "none"`, and Python must treat the binding/capture proof as failed unless another explicit proof mechanism is added.
- If a loose/cached bbox is useful for troubleshooting, it may be returned as `diagnostic_bbox`, but it must not be compared for pass/fail.
- Existing native `DirectorObjectPoseBbox` calculation code may be reused where useful, but Director binding/capture proof routes must not inherit its fallback pass semantics.
- If tight bbox fails, the proof route must report `bbox_method: "unavailable"` or `validation_strength: "none"`; any loose/cached bbox belongs only in `diagnostic_bbox`.
- Existing replay/object-state vocabulary such as `bbox_only` is not accepted as a v1 binding/capture proof. Either replay validation is upgraded to produce/consume `tight_bbox`, or final capture relies on the new binding/materialization proof before replay.
- Tight bbox is drift evidence, not durable identity.

Native fingerprint route:

V1 should add:

```text
POST /director/actor-binding/object-fingerprints
```

This route is distinct from `/director/object-states`. `/director/object-states` remains compiler/replay-oriented source-state input for object transforms. Actor binding reconciliation needs richer current-document evidence and nested instance-reference details.

Native responsibilities:

- Resolve requested object ids in the current Rhino document.
- Report current document facts only.
- Reuse the existing `DirectorObjectPoseBbox` tight-bbox calculation path where useful, but not its fallback pass semantics.
- Include Director object metadata.
- Include layer/name/type evidence and model units.
- Include instance-reference definition and transform details when applicable.
- Avoid owning reconciliation, binding policy, canonical metadata hashing, or manifest persistence.

Request shape:

```json
{
  "object_ids": ["<guid>"],
  "include_director_metadata": true
}
```

Request requirements:

- The route is batch-oriented.
- `object_ids` is required and must be a non-empty array of UUID strings.
- Invalid UUIDs are rejected with typed `invalid_input`.
- Missing objects are rejected with typed `not_found`.
- Over-limit batches are rejected with typed `batch_size_exceeds_cap`.
- The normal v1 design target is 512 objects per request.
- The native route may allow a slightly higher batch cap for diagnostics, but the cap must be explicit in implementation diagnostics and tests.
- `include_director_metadata` defaults to `true` for Director callers. If false, metadata fields may be omitted for low-level diagnostics only and the result is not sufficient for binding reconciliation.

Python responsibilities:

- Reconcile `.rook` actor metadata with current object fingerprints.
- Compute the canonical Director metadata hash used in binding manifests, excluding runtime GUID fields.
- Decide whether a binding manifest is valid or stale.
- Persist successful binding manifests as `.rook` audit/cache artifacts.
- Emit diagnostics for missing objects, duplicate claims, stale/orphan metadata, and policy mismatches.

Hash authority:

- Native may return a diagnostic metadata hash only if useful for troubleshooting.
- Python owns the authoritative `director_metadata_hash` stored in binding manifests.
- If a native diagnostic hash is exposed, the response must label it as diagnostic unless the spec later pins the exact canonical JSON algorithm and excluded fields.

Candidate discovery:

- `POST /director/actor-binding/object-fingerprints` fingerprints requested ids only.
- V1 adds `POST /director/actor-binding/query-candidates` as the authoritative current-document discovery route for Director actor-binding metadata.
- The discovery route scans active document objects for Rook-owned Director actor-binding user strings and returns candidate object ids plus minimal metadata facts.
- The discovery route must only inspect the sanctioned Director actor-binding metadata namespace. It must not become a general user-text search API.
- The discovery route does not compute tight bboxes, final fingerprints, source-state payloads, or capture proof evidence.
- Python passes selected candidate ids to `/director/actor-binding/object-fingerprints` for full current-document facts.
- Python remains responsible for reconciliation against `.rook`, manifest validity, final orphan/stale diagnostics, and persistence.

Candidate discovery request shape:

```json
{
  "actor_set_id": "<optional>",
  "actor_member_ids": ["<optional>"],
  "include_malformed": true,
  "limit": 2048
}
```

Candidate discovery request requirements:

- `actor_set_id` is optional. When present, native filters parseable Director binding metadata to that actor set.
- `actor_member_ids` is optional. When present, native filters parseable Director binding metadata to those actor members.
- `include_malformed` defaults to `true` for Director diagnostics. When true, native includes objects carrying malformed sanctioned Director binding metadata with `status: "malformed_metadata"`.
- `limit` defaults to `2048`. The implementation may set a higher hard cap for diagnostics, but must reject over-limit requests with a typed `batch_size_exceeds_cap` or equivalent route-local typed error.

Candidate discovery response shape:

```json
{
  "candidates": [
    {
      "object_id": "<guid>",
      "actor_set_id": "roof_uplift_vertical_test_chunk_001",
      "actor_member_id": "roof_uplift_vertical_test_chunk_001_member_047",
      "binding_kind": "top_level_instance_reference_duplicate",
      "binding_version": 1,
      "status": "valid_candidate"
    }
  ],
  "limit": 2048,
  "truncated": false,
  "malformed_count": 0
}
```

Candidate status values:

- `valid_candidate`: the sanctioned Director binding metadata parsed and contains the required actor set, actor member, binding kind, and binding version fields.
- `malformed_metadata`: the sanctioned Director binding namespace is present but cannot be parsed or is missing required binding identity fields.
- `orphan_candidate`: optional native-local diagnostic status for parseable Director binding metadata that fails route-local filters or version support. Python still owns final `.rook` orphan/stale classification.

Minimum native response per object:

```json
{
  "object_id": "<guid>",
  "object_type": "InstanceReference",
  "name": "<object name>",
  "layer_path": "Director::Actors::roof_uplift_vertical_test_chunk_001",
  "director_metadata": {},
  "bbox_method": "tight_object",
  "tight_bbox_min": [0, 0, 0],
  "tight_bbox_max": [100, 100, 100],
  "model_units": "<units>",
  "bbox_rounding_policy": "round_to_4_decimal_places",
  "validation_strength": "tight_bbox",
  "instance_definition_id": "<guid>",
  "instance_definition_name": "<block-name>",
  "instance_transform": [],
  "instance_transform_hash": "<hash>",
  "diagnostic_director_metadata_hash": "<optional>"
}
```

If tight bbox cannot be produced for a requested object, the binding fingerprint response must not claim bbox validation strength:

```json
{
  "object_id": "<guid>",
  "bbox_method": "unavailable",
  "validation_strength": "none",
  "diagnostic_bbox": "<optional loose/cached bbox for troubleshooting only>"
}
```

Nested `InstanceReference` policy:

- V1 prefers preserve-as-instance for nested `InstanceReference` actor members.
- When exact preservation is possible, Director creates a top-level instance-reference duplicate pointing to the same definition with the composed transform and actor metadata.
- V1 does not recursively explode nested references into leaf geometry by default.
- If the referenced definition, transform chain, key render attributes, tight bbox proof, or replay transform proof cannot be resolved and preserved, binding/materialization fails for that member.
- Top-level instance-reference duplicates require an explicit proof gate. Bbox validation is necessary but not sufficient because two different definitions can have the same bbox.
- If preserve-as-instance proof cannot be implemented reliably for the first Pearson nested instance actors, v1 must reject those actors rather than silently flattening them.

Nested instance preserve-as-instance proof:

- The generated/bound top-level actor object is an `InstanceReference`, not exploded leaf geometry.
- It references the same block definition id and name as the nested source reference.
- Its instance transform equals the composed nested transform within v1 `matrix_abs_tolerance: 1e-9`.
- Its key render attributes are preserved or explicitly recorded as intentionally changed: layer, material source/index, color source/value, name, visibility, and user strings.
- Its tight bbox matches the source occurrence's expected world-space tight bbox after composed transform.
- Replay transform moves the top-level instance reference correctly under `absolute_from_source`, proven by tight bbox at one or more non-zero frames.
- The binding/capture manifests must record the actual proof evidence, not only pass/fail: `source_definition_id/name`, `capture_definition_id/name`, `composed_source_transform_hash`, `capture_instance_transform_hash`, `matrix_tolerance`, `attribute_preservation`, `tight_bbox_before`, `tight_bbox_after`, and `replay_probe_frames`.

Nested instance failure taxonomy:

- `nested_instance_reference_definition_unresolved`
- `nested_instance_reference_transform_unresolved`
- `nested_instance_reference_attribute_mismatch`
- `nested_instance_reference_tight_bbox_unavailable`
- `nested_instance_reference_replay_transform_failed`
- `nested_instance_reference_unsupported`

### Capture Scene Manifest v1

New proposed artifact written during materialization.

Draft fields:

```json
{
  "schema_version": 1,
  "metadata_kind": "director_capture_scene",
  "capture_scene_id": "pearson_animation_test_capture_001",
  "take_id": "pearson_animation_test_take_001",
  "actor_binding_manifest_ref": ".rook/director_binding_manifests/pearson_animation_test_binding_001.json",
  "actor_binding_manifest_hash": "<hash>",
  "materialization_status": "succeeded",
  "materialization_mode": "reuse_if_valid",
  "materialization_policy_hash": "<hash>",
  "export_hash": "<hash>",
  "source_document": {
    "path": "<active .3dm path>",
    "runtime_serial": "<optional>"
  },
  "actor_sets": [
    {
      "actor_set_id": "roof_uplift_vertical_test_chunk_001",
      "source_occurrence_ref": ".rook/director_planning/selection_snapshots/source_occurrence_roof_uplift_vertical_test_chunk_001.json",
      "members": [
        {
          "canonical_source_member_occurrence_id": "occurrence-path-hash-or-stable-member-id",
          "actor_member_ordinal": 47,
          "source_occurrence_path": [],
          "definition_object_id": "<guid>",
          "source_top_level_object_id": "a28cbdb5-51fa-46b2-b18b-ab880b54ded7",
          "source_bound_object_id": "<current top-level bound object guid>",
          "source_binding_kind": "exact_geometry_duplicate",
          "director_metadata_hash": "<hash-from-binding-manifest>",
          "world_transform_chain": [],
          "nested_instance_reference_proof": {
            "source_definition_id": "<guid>",
            "source_definition_name": "<block-name>",
            "capture_definition_id": "<guid>",
            "capture_definition_name": "<block-name>",
            "composed_source_transform_hash": "<hash>",
            "capture_instance_transform_hash": "<hash>",
            "matrix_tolerance": {
              "name": "matrix_abs_tolerance",
              "value": 1e-9
            },
            "attribute_preservation": {
              "layer": "preserved",
              "material_source": "preserved",
              "material_index": "preserved",
              "color_source": "preserved",
              "color_value": "preserved",
              "name": "preserved",
              "visibility": "preserved",
              "user_strings": "preserved"
            },
            "tight_bbox_before": {
              "bbox_method": "tight_object",
              "tight_bbox_min": [0, 0, 0],
              "tight_bbox_max": [100, 100, 100]
            },
            "tight_bbox_after": {
              "bbox_method": "tight_object",
              "tight_bbox_min": [0, 0, 0],
              "tight_bbox_max": [100, 100, 100]
            },
            "replay_probe_frames": [
              {
                "frame": 12,
                "bbox_method": "tight_object",
                "status": "passed"
              }
            ]
          },
          "capture_status": "materialized",
          "unsupported_reason": null,
          "capture_objects": [
            {
              "capture_object_id": "<new top-level guid>",
              "role": "take_owned_capture_duplicate",
              "geometry_kind": "Brep",
              "capture_kind": "exact_top_level_geometry_duplicate",
              "attributes_preserved": {
                "layer": true,
                "material": true,
                "name": true,
                "user_strings": true
              }
            }
          ]
        }
      ]
    }
  ],
  "visibility": {
    "policy": "hide_non_capture_render_conflicts",
    "source_visibility_scope": "actor_only_source_required",
    "targets": [
      {
        "object_id": "a28cbdb5-51fa-46b2-b18b-ab880b54ded7",
        "role": "source_top_level_object",
        "reason": "prevents_original_source_double_render",
        "mechanisms": [
          {
            "kind": "object_hidden_state",
            "previous_hidden": false,
            "new_hidden": true
          }
        ]
      },
      {
        "object_id": "<design-time actor object guid>",
        "role": "design_time_actor_object",
        "reason": "prevents_design_time_actor_duplicate_double_render",
        "mechanisms": [
          {
            "kind": "object_hidden_state",
            "previous_hidden": false,
            "new_hidden": true
          },
          {
            "kind": "object_layer_assignment",
            "previous_layer": "Source::ActorBindings",
            "new_layer": "Director::Takes::pearson_animation_test_take_001::HiddenSources"
          }
        ]
      }
    ],
    "layer_changes": [
      {
        "kind": "created_layer",
        "layer_path": "Director::Takes::pearson_animation_test_take_001::HiddenSources",
        "previously_existed": false
      }
    ],
    "restore_required": true
  },
  "ownership": {
    "owner": "Director",
    "take_layer_root": "Director::Takes::pearson_animation_test_take_001",
    "generated_capture_object_ids": ["<new top-level guid>"],
    "cleanup_allowed": true,
    "restore_visibility_required": true
  },
  "cleanup_policy": {
    "operation_key": ["take_id", "capture_scene_id"],
    "cleanup_order": ["restore_source_and_design_time_visibility", "remove_or_archive_take_owned_capture_duplicates"],
    "allowed_remove_roles": ["take_owned_capture_duplicate"],
    "source_delete_allowed": false,
    "design_time_actor_delete_allowed": false,
    "missing_or_inconsistent_manifest_action": "typed_conflict"
  },
  "failure_recovery": {
    "state": null,
    "created_object_ids": [],
    "visibility_changes": []
  }
}
```

This manifest becomes the mapping from source actor metadata to concrete replay object ids.

Capture scene manifests must be tied to the reconciled actor binding manifest used to create them. The manifest records `actor_binding_manifest_ref` and `actor_binding_manifest_hash`, and each canonical member records `source_bound_object_id`, `source_binding_kind`, and `director_metadata_hash` from that binding manifest. `reuse_if_valid` must prove the capture scene still corresponds to the current export, current actor binding, and current materialization policy; matching `take_id` and `capture_scene_id` alone is not sufficient.

`ownership.generated_capture_object_ids` is a required derived index. It must equal the union of every `capture_objects[].capture_object_id` in member order with no extras or omissions. The per-member `capture_objects[]` entries remain the authoritative source-to-capture mapping; the generated id index exists for cleanup, conflict diagnostics, and quick ownership checks. Validation must fail if the two disagree.

Visibility and ownership records are role-aware. The manifest must identify each non-capture object hidden for capture, whether it is a `source_top_level_object` or a `design_time_actor_object`, and the reason it was hidden. Take-owned capture duplicates are recorded with `take_owned_capture_duplicate` role in capture object ownership and are normally visible for capture. Visibility restore records must capture the mechanism changed, such as object hidden state, layer visibility, object layer assignment, or created take layers, with enough prior state to restore exactly.

Mixed-block source visibility is not supported implicitly in v1. If an actor member comes from inside a source top-level block that also contains non-actor renderable context, hiding that source block could remove required static context from the shot. V1 must fail preflight with `source_visibility_scope_unsupported` unless the source top-level object is proven actor-only for the take. Actor-only is a proof, not an assertion: every renderable member under the source top-level object must be represented in the actor binding manifest for this take, or must already be explicitly non-renderable/hidden before materialization. If Director cannot enumerate that source scope reliably, preflight fails. Materializing non-actor block context as static capture geometry is a possible later extension, not an implicit v1 fallback.

Materialization timing and ownership:

- Director v1 materializes take-owned capture duplicates through an explicit `prepare capture scene` step before compile.
- This step runs after CanvasDirector Export assembly, fragment/ownership validation, and fresh actor binding reconciliation.
- This step is document-mutating; `take_id` and `capture_scene_id` are the ownership/discovery key for finding existing take-owned capture objects.
- Reuse validity is separate from ownership discovery and must revalidate export, actor binding, materialization policy, object ownership metadata, tight-bbox proof, and visibility state.
- Compile and final capture consume the capture scene manifest and must not create capture duplicates implicitly.
- Export assembly must remain a pure Grasshopper/data operation.
- Compile must remain a deterministic translation from validated inputs and capture object ids to replay/capture payloads.
- Final capture must not lazily materialize capture duplicates.
- Materialization must complete preflight before mutating the Rhino document.
- If mutation partially fails, materialization must write or report a recoverable failed state with created object ids and visibility changes; Rhino document mutation is not truly transactional, so the manifest is the recovery ledger.
- Cleanup remains a separate explicit operation keyed by `take_id` and `capture_scene_id`; materialization must record enough ownership and visibility mechanism state to safely restore visibility and remove or archive generated capture objects later.

Materialization modes:

- `create`: create a new take-owned capture scene and fail with a typed conflict if objects for the same `take_id`/`capture_scene_id` already exist.
- `reuse_if_valid`: reuse existing take-owned capture objects only if the capture scene manifest, ownership metadata, role-aware visibility manifest, export hash, actor binding manifest hash, materialization policy hash, selected object fingerprints, and tight-bbox proof revalidate.
- `replace_existing`: restore prior source/design-time visibility state as needed, then remove or archive existing matching take-owned capture objects for the same `take_id`/`capture_scene_id`, then create a fresh capture scene.

Stale take-owned objects:

- Existing take-owned objects without a matching valid manifest are a typed conflict.
- Existing take-owned objects with stale ownership metadata, stale export hash, stale actor binding manifest hash, stale materialization policy, missing visibility restore data, failed visibility revalidation, or failed tight-bbox proof must not be silently reused.
- Conflict diagnostics must list the conflicting object ids, `take_id`, `capture_scene_id`, and recommended allowed mode, such as `replace_existing` or explicit cleanup.

Cleanup policy:

- Cleanup is an explicit operation keyed by `take_id` and `capture_scene_id`.
- Cleanup order is fixed for v1: restore source/design-time visibility first, then remove or archive take-owned capture duplicates.
- Cleanup must record the cleanup order used in the manifest or cleanup result.
- Cleanup may restore visibility for source top-level objects and persistent design-time actor objects using the recorded visibility mechanisms and prior state.
- After visibility restore, cleanup may remove or archive only objects carrying `take_owned_capture_duplicate` metadata for the same `take_id` and `capture_scene_id`.
- Cleanup must never delete source objects or persistent design-time actor objects.
- Cleanup must fail with a typed conflict if the capture scene manifest, generated object id index, object ownership metadata, or visibility restore data is missing or inconsistent.
- Cleanup must not infer ownership from layer path, object name, bbox, or selection alone.

Materialization preflight requirements:

- Unsupported geometry, ownership conflicts, invalid binding provenance, mixed-block source visibility scope, and planned visibility conflicts must fail before mutation.
- The failure response/manifest must list unsupported members and geometry types.
- If hiding a source top-level block would also hide non-actor renderable context, preflight must fail with `source_visibility_scope_unsupported` unless that source top-level object is proven actor-only for the take.
- One actor member may materialize to zero, one, or many capture objects.
- Direct block-definition geometry members should materialize as exact top-level geometry duplicates.
- Nested `InstanceReference` members should materialize as exact top-level instance-reference duplicates when possible, or fail with `nested_instance_reference_unsupported`.
- Recursive flattening of nested references is deferred until actor metadata can address every resulting leaf.

## Current Implementation Surface

Likely Python files:

- `mcp_server/src/rook/canvas_director.py`
- `mcp_server/src/rook/director_compiler.py`
- `mcp_server/src/rook/director_motion.py`
- `mcp_server/src/rook/director_actor_metadata.py`
- new possible `mcp_server/src/rook/director_actor_binding.py`
- new possible `mcp_server/src/rook/director_capture_scene.py`

Likely template files:

- `mcp_server/src/rook/canvas_director_templates/manifest.json`
- `mcp_server/src/rook/canvas_director_templates/instantiator.py`
- `mcp_server/src/rook/canvas_director_templates/scripts/export_marker.cs`
- movement template scripts such as `transform.cs` or generated movement component bodies

Likely native files if a dedicated native route is needed:

- `src/RookNative/RookServer.cpp`
- `src/RookNative/Handlers/DirectorHandler.cpp`
- `src/RookNative/Handlers/DirectorFrame.cpp`
- possibly reuse code patterns from `src/RookNative/Handlers/BlocksHandler.cpp`

New native route:

- `POST /director/actor-binding/query-candidates`
- `POST /director/actor-binding/object-fingerprints`

Important existing native utility behavior:

- `/director/object-states` already uses `DirectorObjectPoseBbox`, but remains compiler/replay source-state infrastructure.
- Existing `/director/object-states` responses such as `validation_strength: "bbox_only"` are compatibility/source-state data, not accepted v1 binding/capture proof.
- `/block/explode` duplicates direct block definition geometry into the document and deletes the original instance.
- This is not acceptable as the Director v2 materializer behavior.
- It does prove that native has exact-geometry duplication/materialization patterns that can be reused.

## Proposed Work Scope

### Slice 1: Contract And Export Assembly

Goal:

- Make CanvasDirector Export a take assembler for multiple movement fragments.

Tasks:

- Define `director_motion_fragment` v1.
- Add `Motion` or `Fragment` output to movement components.
- Update export marker to consume a list/tree of fragments.
- Validate disjoint canonical source member ownership.
- Define the normalized `director_compile_request_v1` artifact and preserve schema 1 compiler-facing adapter compatibility inside that adapter where needed.
- Add a scale note for every export showing claimed source member count and expected capture object count.

### Slice 2: Python Extraction And Compile

Goal:

- Teach Python to persist and compile the new export payload.

Tasks:

- Update Canvas Director export parsing.
- Convert schema 2 `motion_fragments` to authoring spec data only; compile-prep later derives `director_compile_request_v1` after binding/materialization.
- Preserve provenance.
- Add tests for multiple disjoint movement fragments.
- Add tests for duplicate canonical source member rejection.
- Add tests for duplicate final capture object rejection after materialization mapping.
- Add schema 1 compatibility tests.
- Add schema 2 persistence and normalized `director_compile_request_v1` tests.

### Slice 3: Document-Bound Actor Binding

Goal:

- Bind actor members to current top-level document objects through durable Rook-owned metadata.

Tasks:

- Add a Director v2 tool such as `rhino_director_bind_actor_set_v2`.
- Input: actor set refs, optional grouping refs, binding policy, and optional source occurrence refs.
- Output: actor binding manifest mapping stable actor member ids to current document object ids.
- Stamp actor membership and grouping metadata onto existing top-level animatable objects when they already exist.
- Create persistent exact design-time actor objects only when actor members are not already individually animatable top-level objects.
- For nested `InstanceReference` actor members, prefer preserve-as-instance mode by creating top-level instance-reference duplicates only when exact definition identity, composed transform, key render attributes, tight bbox, and replay transform proof can be proven.
- Do not encode movement behavior, take-specific timing, easing, or strategy in object metadata.
- Use Director-owned actor/binding layers for human-visible organization.
- Add a query/rebuild tool such as `rhino_director_resolve_actor_binding_v2` that rebuilds the current GUID map from object metadata and validates counts/grouping/fingerprints.
- Add `POST /director/actor-binding/query-candidates`, with a Python MCP wrapper if needed, to discover current document objects carrying sanctioned Director actor-binding metadata.
- Add `POST /director/actor-binding/object-fingerprints`, with a Python MCP wrapper if needed, to report current object facts for binding reconciliation.
- Compute canonical `director_metadata_hash` values in Python for binding manifests, excluding runtime GUID fields.
- Keep `/director/object-states` unchanged for compiler/replay source-state use.
- Have native report candidate ids/facts and object fingerprints only; Python owns reconciliation and manifest persistence.
- Generate binding manifests fresh from `.rook` actor metadata plus current Rhino object metadata whenever export/capture needs them.
- Persist successful binding manifests only as audit/cache artifacts with document and binding fingerprints.
- Treat persisted binding manifests as invalid until revalidated against the current document.
- Treat design-time bound objects as a rebuildable cache layer. The authority remains `.rook` actor metadata plus Rook-owned object metadata in the current document.
- Do not destructively explode source blocks.

### Slice 4: Exact Capture-Scene Materialization

Goal:

- Create exact top-level capture-scene duplicates for actor members.

Tasks:

- Add a durable Director v2 tool such as `rhino_director_prepare_capture_scene_v2`.
- Input: validated Director export/spec, freshly reconciled actor binding manifest/ref/hash, actor set refs, optional grouping refs, `take_id`, `capture_scene_id`, materialization mode, and materialization policy.
- Output: capture scene manifest with source-to-capture mapping, binding provenance, role-aware visibility changes, visibility restore mechanisms, ownership metadata, a generated capture id index, cleanup policy, and any recoverable failure ledger.
- Run only after export assembly, fragment/ownership validation, and actor binding reconciliation.
- Never run inside CanvasDirector Export, replay compile, or final capture.
- Preserve layer/material/name/user strings as far as Rhino allows.
- Do not destructively explode or mutate source blocks or design-time actor objects.
- Preflight all source members, binding provenance, ownership conflicts, mixed-block source visibility scope, planned visibility changes, and unsupported geometry before mutation.
- Materialize direct geometry as exact top-level duplicates.
- Materialize nested `InstanceReference` members as exact top-level instance-reference duplicates when the preserve-as-instance proof passes; otherwise fail with a typed nested-instance diagnostic such as `nested_instance_reference_unsupported`.
- Create Director-owned take layers.
- Hide only the role-aware non-capture objects needed to prevent double-rendering, and write a reversible visibility manifest that records object role, reason, changed mechanism, prior state, and new state.
- Fail with `source_visibility_scope_unsupported` when hiding a source top-level block would also hide non-actor renderable context, unless that source top-level object is proven actor-only for the take by enumerating every renderable member under that source top-level object and confirming each is represented in the actor binding manifest or is explicitly non-renderable/hidden before materialization.
- Define `ownership.generated_capture_object_ids` as the required derived union of every per-member `capture_objects[].capture_object_id`.
- Add cleanup or archival as a separate explicit operation keyed by `take_id` and `capture_scene_id`.
- Cleanup restores source/design-time visibility first, then removes or archives only `take_owned_capture_duplicate` objects with matching ownership metadata, and must never delete source objects or persistent design-time actor objects.
- Cleanup records the order used, with v1 defaulting to `restore_source_and_design_time_visibility` before `remove_or_archive_take_owned_capture_duplicates`.
- Cleanup must fail with a typed conflict if the manifest, generated id index, ownership metadata, or visibility restore data is missing or inconsistent.
- Use `take_id` and `capture_scene_id` as the take-owned object discovery key; require `export_hash`, `actor_binding_manifest_hash`, `materialization_policy_hash`, ownership metadata, tight-bbox proof, and role-aware visibility revalidation before reuse.
- Support `create`, `reuse_if_valid`, and `replace_existing` modes.
- Return typed conflicts when stale take-owned objects already exist and the requested mode does not allow replacement.
- Record ownership and visibility state sufficient to safely restore or remove generated capture objects.
- If mutation partially fails, report or persist a recoverable failed materialization state containing created object ids and visibility changes.

### Slice 5: Replay Integration

Goal:

- Compile movement fragments against capture object ids and run deterministic replay/capture.

Tasks:

- Use actor binding and capture scene manifests to resolve actor members to top-level capture object ids.
- Compile final replay track with `absolute_from_source` semantics.
- Reject compile requests that require capture duplicates but do not provide a valid capture scene manifest.
- Compile and final capture must not create capture duplicates implicitly.
- Do not treat existing `bbox_only` replay/object-state vocabulary as v1 binding/capture proof; either upgrade replay validation to `tight_bbox` or rely on the new binding/materialization proof before replay.
- Raise/prove the implementation guards for the v1 512-object final-capture contract and run the real 338-member Pearson scale proof.
- Capture frames.
- Assemble video.

## Explicit Non-Goals For v1

- No arbitrary C# execution during final native replay.
- No motion blending/composition on the same actor set.
- No additive transform stack.
- No destructive global explode of the source model.
- No bounding-box or simplified proxy geometry for animated capture objects.
- No silent recursive nested block flattening.
- No movement behavior stored in document-bound actor metadata.
- No treatment of design-time bound actor objects as the source authoring truth; they are a rebuildable binding/cache layer.
- No implicit capture duplicate creation during CanvasDirector Export, replay compile, or final capture.
- No claim of Pearson-scale support until 338-member compile and final capture have been proven, with interactive `/director/replay` either passing or reporting a documented transport limitation.

## Implementation Proof Questions

1. What exact compiler/native changes are required to raise the implementation guards from 256 to the v1 contract of 512 animated capture objects per take?

2. What are the measured payload sizes, runtimes, and memory deltas for the Pearson 338-member proof at target frame count and the 512-object synthetic cap test?

3. Does interactive `/director/replay` full-track preview pass within the 8 MiB transport cap for the Pearson proof, and if not, does it return/report typed `replay_transport_limit_exceeded` diagnostics with payload size, limit details, limit source, and confirmation that replay execution did not begin?

4. What optional fields, canonical JSON hash implementation tests, and schema 1 compiler-adapter migration tests should `director_compile_request_v1` carry beyond the required v1 baseline?

5. Should generated capture objects live in the active document only, or should Director save a duplicated capture `.3dm` file?

6. Do the first Pearson actor sources prove actor-only source visibility scope, or does Pearson expose a need for explicit static non-actor context materialization after v1?

7. What exact CanvasDirector Export input wiring should carry actor payloads alongside motion fragments while preserving the settled schema 2 authoring/take boundary?

8. Do top-level instance-reference duplicates pass the full preserve-as-instance proof for the first Pearson animation needs, including definition id/name, composed transform, key render attributes, tight bbox, and non-zero-frame replay transform proof?

## Recommended Implementation Planning Focus

Before writing implementation code, turn these settled design gates into implementation slices and test gates:

1. First implementation scope: one Pearson actor set first while export/compile contracts allow multiple disjoint actor sets, then a second small actor-set test before claiming assembler completeness.
2. Implementation details for DEC-026 guard changes and measurement instrumentation, now that the scale-proof contract is settled.
3. `director_compile_request_v1` optional fields, canonical JSON hashing implementation tests, and schema 1 compiler-adapter migration tests.
4. Pearson source visibility scope proof and cleanup route request/response details for the settled explicit pre-compile materialization step.
5. Native route/API field details for nested `InstanceReference` preserve-as-instance proof evidence.

The current recommendation is:

- implement contracts as multi-fragment and multi-actor capable with disjoint canonical source-member ownership,
- validate the first end-to-end production path with one real Pearson actor set,
- then add a second synthetic or small live disjoint actor set test before calling the export assembler complete.

Acceptance split:

- Pearson proof: one real actor set, 338 members, target frame count, validates the real production path.
- Assembler proof: two disjoint actor sets, smaller geometry acceptable, validates ownership isolation and multi-fragment assembly.
- 512 cap proof: synthetic 512 real capture objects, validates cap/performance without requiring Pearson to have 512 members.

Claim matrix:

- `Pearson production path support` requires the Pearson proof.
- `Export assembler completeness` requires the assembler proof.
- `512-object v1 final-capture support` requires the 512 cap proof.

## Test Gates

Spec implementation should not be considered complete without tests/proofs in these categories.

### Export And Schema Tests

- Multi-fragment export assembly succeeds for disjoint canonical source member claims.
- Duplicate canonical source member ownership is rejected before materialization.
- First implementation supports schema/export/compile contracts for multiple disjoint actor sets even if the first production proof uses one Pearson actor set.
- Export assembler completeness is not claimed until a second small disjoint actor set passes assembly, ownership validation, materialization mapping, compile request generation, and final capture/replay proof.
- Schema 1 compiler-facing adapter compatibility is preserved where needed or the migration failure is explicit and tested.
- Schema 2 export persistence includes fragments, validation diagnostics, provenance, camera/timeline state, and take-level refs, but no normalized compiler `payload.motion`.
- CanvasDirector Export does not emit normalized compiler `payload.motion`.
- The Python extraction/compile-prep layer persists `director_compile_request_v1` only after actor binding reconciliation and capture-scene materialization.
- The normalized `director_compile_request_v1` artifact has its own schema/version/hash and records the source schema 2 export, actor binding manifest, capture scene manifest, materialization policy, and compiler version hashes/refs.
- `director_compile_request_v1` includes `metadata_kind`, `schema_version`, `compile_request_id`, `take_id`, `capture_scene_id`, source refs/hashes, compiler versions, `transform_semantics`, timeline, resolution, camera, normalized motion, required source-state snapshot ref/hash, and validation counts.
- `director_compile_request_v1` is rejected if any normalized motion target is not a take-owned capture object present in the referenced capture scene manifest.
- `director_compile_request_v1` is rejected if normalized motion lacks `target_capture_object_id`, `canonical_source_member_occurrence_id`, or `actor_member_id`.
- `director_compile_request_v1` is rejected if top-level transform semantics are missing or not `absolute_from_source` in v1.
- Track-level transform semantics are omitted in v1, or if present for diagnostics/adapter compatibility must match the top-level `absolute_from_source` exactly.
- `director_compile_request_v1` is rejected if source-state snapshot ref/hash is missing.
- The referenced source-state snapshot includes baseline object states for every normalized `target_capture_object_id`.
- The referenced source-state snapshot records source-state capture route/tool name and version.
- The referenced source-state snapshot includes tight-bbox proof metadata where relevant, while compatibility source-state fields such as `bbox_only` are not accepted as v1 binding/capture proof.
- `director_compile_request_v1` hash tests use canonical JSON with sorted object keys, UTF-8 encoding, stable numeric formatting, and arrays kept in semantic order.
- Stable numeric formatting tests reject `NaN`, `Infinity`, `-Infinity`, insignificant trailing zeros, and fixed rounding outside contracts that explicitly require rounding.
- Current `transform.cs`-style group-level motion payload is rejected or upgraded if it loses required member/group phase behavior.

### Materialization Tests

- Prepare-capture-scene runs after export assembly and actor binding reconciliation, before compile.
- Compile rejects inputs that need capture duplicates but do not provide a valid capture scene manifest.
- Final capture does not create capture duplicates implicitly.
- Materializer preflight fails before mutation for unsupported geometry, invalid binding provenance, ownership conflicts, mixed-block source visibility scope, and planned visibility conflicts.
- Mixed-block source visibility fails with `source_visibility_scope_unsupported` when hiding a source top-level block would remove non-actor renderable context.
- Actor-only source top-level blocks can pass source visibility preflight only when Director enumerates every renderable member under the source top-level object and proves each member is represented in the actor binding manifest for the take or is explicitly non-renderable/hidden before materialization.
- Source visibility preflight fails with `source_visibility_scope_unsupported` when Director cannot reliably enumerate renderable members under the source top-level object.
- Direct Brep/Curve/Mesh/etc. members create exact top-level capture duplicates.
- Nested `InstanceReference` members are preserved as top-level instance-reference duplicates only when the full preserve-as-instance proof passes, or fail with typed nested-instance diagnostics.
- No source object or source block definition is deleted.
- One actor member can produce zero, one, or many capture objects and the manifest records that accurately.
- The capture scene manifest records `actor_binding_manifest_ref` and `actor_binding_manifest_hash`.
- Each materialized member records `source_bound_object_id`, `source_binding_kind`, and `director_metadata_hash` from the actor binding manifest.
- `ownership.generated_capture_object_ids` equals the union of all per-member `capture_objects[].capture_object_id` values, and validation fails if the index has extras or omissions.
- Materialization uses `take_id` and `capture_scene_id` as the ownership/discovery key for existing take-owned objects.
- `create` mode fails with a typed conflict if take-owned objects for the same `take_id`/`capture_scene_id` already exist.
- `reuse_if_valid` reuses existing take-owned capture objects only after manifest, ownership metadata, role-aware visibility manifest, export hash, actor binding manifest hash, materialization policy hash, selected object fingerprints, and tight-bbox proof revalidate.
- `replace_existing` restores prior source/design-time visibility state as needed, then removes or archives existing matching take-owned capture objects for the same `take_id`/`capture_scene_id`, then creates a fresh capture scene.
- Stale take-owned objects produce typed conflicts that include conflicting object ids, `take_id`, `capture_scene_id`, and the recommended allowed mode or cleanup action.
- Visibility and ownership manifests classify source top-level objects, persistent design-time actor objects, and take-owned capture duplicates by role.
- Source visibility changes record object role, reason, changed mechanism, prior state, new state, and restore correctly.
- Visibility restore supports object hidden state, layer visibility, object layer assignment, and created take-layer cleanup/restoration when those mechanisms are used.
- Block-derived actor members do not double-render through the original block instance when design-time actor duplicates or capture duplicates are visible.
- Cleanup is an explicit operation keyed by `take_id` and `capture_scene_id`.
- Cleanup records its order and restores source/design-time visibility before removing or archiving capture duplicates.
- Cleanup restores source/design-time visibility but never deletes source objects or persistent design-time actor objects.
- Cleanup removes or archives only objects carrying `take_owned_capture_duplicate` metadata for the same `take_id` and `capture_scene_id`.
- Cleanup fails with a typed conflict when the manifest, generated id index, ownership metadata, or visibility restore data is missing or inconsistent.
- Partial materialization failure writes or reports a recoverable failed state with created object ids and visibility changes.

### Actor Binding Tests

- `POST /director/actor-binding/query-candidates` scans only the sanctioned Director actor-binding metadata namespace.
- The query-candidates route does not expose general user-text search.
- The query-candidates route accepts request shape `{actor_set_id, actor_member_ids, include_malformed, limit}`.
- The query-candidates route returns `object_id`, `actor_set_id`, `actor_member_id`, `binding_kind`, `binding_version`, and local metadata `status`.
- The query-candidates route reports malformed sanctioned Director metadata as `malformed_metadata` when `include_malformed` is true.
- The query-candidates route does not compute or return authoritative bbox fingerprints.
- The query-candidates route rejects over-limit requests with a typed error.
- Python passes selected candidate ids from query-candidates into `/director/actor-binding/object-fingerprints`.
- `POST /director/actor-binding/object-fingerprints` returns current document facts without performing reconciliation or writing manifests.
- The object-fingerprints route accepts batch request shape `{object_ids, include_director_metadata}`.
- The object-fingerprints route rejects empty object id lists, invalid UUIDs, missing objects, and over-limit batches with typed errors.
- The object-fingerprints route supports at least the 512-object v1 design target per batch, with any higher diagnostic cap documented and tested.
- The object-fingerprints route may reuse the `DirectorObjectPoseBbox` tight-bbox calculation path, but rejects its fallback pass semantics.
- The object-fingerprints route returns Director object metadata, layer path, name, object type, model units, bbox method, bbox rounding policy, validation strength, and tight bbox fields.
- The object-fingerprints route uses `bbox_method: "tight_object"` and `validation_strength: "tight_bbox"` for any authoritative bbox-based pass.
- The object-fingerprints route reports `bbox_method: "unavailable"` or `validation_strength: "none"` when tight bbox cannot be produced.
- Loose/cached bbox data returned as `diagnostic_bbox` is never compared for pass/fail.
- The object-fingerprints route returns instance definition id/name, instance transform, and instance transform hash for instance-reference objects.
- Python computes the authoritative Director metadata hash used in binding manifests, excluding runtime GUID fields.
- Any native metadata hash is diagnostic unless the canonical JSON algorithm and excluded fields are explicitly pinned.
- The query-candidates route supplies current objects carrying the Director actor metadata namespace before fingerprinting.
- `/director/object-states` remains compiler/replay-oriented and is not expanded into the binding reconciliation API.
- Fresh reconciliation from `.rook` actor metadata plus current object metadata produces the authoritative current GUID map.
- Persisted binding manifests are invalidated when source document, actor metadata, binding policy, per-member object metadata, or binding-kind-specific evidence changes.
- Duplicate objects claiming the same `actor_member_id` are rejected as hard conflicts.
- Objects with Director actor metadata for unknown actor/member ids are reported as stale/orphan bindings.
- Binding manifests record `binding_kind` for every member.
- Binding manifests record the minimum v1 fingerprint set: source document fingerprint, actor metadata fingerprint, binding policy fingerprint, per-member `director_metadata_hash`, object type/name/layer evidence, tight bbox fingerprint, and binding-kind-specific evidence.
- Binding manifest revalidation treats bbox as drift evidence only; bbox never establishes identity.
- Missing tight bbox fails binding drift checks, capture duplicate proof, and replay validation unless another explicit proof mechanism is added.
- Repeated runs on the same objects must include a regression proof that loose/cached bbox comparison fails or is rejected, while tight bbox comparison passes within tolerance.
- Existing top-level geometry binds as `tagged_existing_top_level`.
- Block-definition geometry members bind as `exact_geometry_duplicate`.
- Nested `InstanceReference` members bind as `top_level_instance_reference_duplicate` when proof-gated exact preservation is possible.
- Top-level instance-reference duplicates carry validation evidence for object type, definition id/name preservation, composed transform preservation within `matrix_abs_tolerance: 1e-9`, key render attribute preservation or intentional-change records, tight bbox match, replay transform proof at non-zero frames, and grouping match.
- Binding and capture manifests record nested instance proof artifacts: source/capture definition id/name, composed source transform hash, capture instance transform hash, matrix tolerance, attribute preservation, tight bbox before/after, and replay probe frames.
- Nested `InstanceReference` proof failures use typed diagnostics: `nested_instance_reference_definition_unresolved`, `nested_instance_reference_transform_unresolved`, `nested_instance_reference_attribute_mismatch`, `nested_instance_reference_tight_bbox_unavailable`, `nested_instance_reference_replay_transform_failed`, or `nested_instance_reference_unsupported`.
- Nested `InstanceReference` proof does not pass on bbox alone.
- V1 does not silently flatten nested `InstanceReference` actors into leaf geometry when preserve-as-instance proof fails.
- Binding metadata does not contain movement strategy, take timing, easing, or transform instructions.

### Compile/Replay Scale Tests

- Duplicate capture object ids are rejected after materialization mapping.
- 338 members at the target frame count pass compile and final capture after the required cap increase is implemented and tested.
- A structurally representative 512-object synthetic cap case passes compile and final capture or fails with a typed proof failure before v1 support is claimed.
- The 512-object synthetic cap case uses 512 take-owned capture objects with real duplicated renderable geometry and normalized motion tracks.
- The 512-object synthetic cap case exercises capture object mapping, source-state snapshotting, compile, and final frame capture. It may use simple identical lift tracks.
- Interactive `/director/replay` full-track preview either passes for the Pearson target case or fails with typed `replay_transport_limit_exceeded` diagnostics that include payload size, limit bytes, limit source, and `final_capture_proven`.
- `final_capture_proven` is true only when the corresponding final-capture proof has passed for that take or test case.
- `replay_transport_limit_exceeded` is accepted only when request body size exceeds the configured `/director/replay` transport limit before replay execution begins.
- Runtime failures, validation failures, object-count guard failures, malformed payloads, and native replay errors use distinct diagnostics and do not preserve the interactive replay-preview claim.
- Interactive `/director/replay` transport failure does not fail the final-capture support proof when final capture passes and the failure is typed as transport-only.
- `director_compile_request_v1` size is measured for the Pearson target case and 512-object synthetic case.
- Interactive `/director/replay` request size is measured for the Pearson target case and 512-object synthetic case.
- Per-frame `/director/frame-capture` request size is measured for the Pearson target case and 512-object synthetic case.
- Compile duration is measured for the Pearson target case and 512-object synthetic case.
- Native replay setup duration is measured for the Pearson target case and 512-object synthetic case.
- Final frame capture duration is measured for the Pearson target case and 512-object synthetic case.
- Peak process memory or process memory delta is measured for compile/replay/capture in the Pearson target case and 512-object synthetic case.
- 1024-object runs, if performed, are reported only as measurement/stretch data and do not change the v1 support contract unless separately accepted.

### Live Rhino Proofs

- One direct Brep actor set materializes and replays.
- One block-definition direct-member actor set materializes and replays.
- One nested `InstanceReference` actor member preserves as a top-level instance-reference duplicate and passes definition id/name, composed transform, key render attribute, tight bbox, and non-zero-frame replay transform proof, or fails with a typed nested-instance proof failure.
