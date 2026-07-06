# Director v3: Snapshot Boundary + Disposable-Copy Render Worker

Status: direction design, validated by live spikes; amended after Codex review round 1
Date: 2026-07-06
Supersedes (in part): `docs/director/2026-07-06-dynamic-canvas-export-materialization-spec.md` (worktree `director-canvas-export-spec`)

## Why This Redesign

The Director pipeline has needed repeated rewrites because it animates and captures
inside the user's live Rhino document. Nearly all of its hard machinery compensates
for that single choice, not for animation itself:

| Machinery | Compensates for |
| --- | --- |
| Capture duplicates, visibility manifests, cleanup ledgers | Block members are not individually animatable top-level objects |
| Binding manifests, fingerprints, tight-bbox proofs | Rhino GUIDs are not durable identity across save/copy/import |
| `absolute_from_source`, per-frame bbox validation, RAII restore guards | Mutating the user's document and undoing it perfectly |
| 256-object / 8 MiB / 60 s / 250 ms caps, `DispatchDrainSuspension` | Every frame is a document mutation serialized through the user's UI thread |

The animation core itself (`director_motion.py`, the compile-motion vocabulary,
camera planner, GH authoring prototype) is small, pure, and sound. It survives
this redesign unchanged.

## Product Constraints

- The rendered video feeds AI restyling (RookVision video-to-video, not yet
  implemented). The AI-steering encoding is layer colors + materials +
  **stylized display modes** (Arctic/Pen/Ghosted plus ~30 tuned custom modes in
  production documents). This encoding is empirically tuned; near-miss
  reproduction in another renderer forces re-tuning. The render source must be
  Rhino for the control-channel pass.
- No paid external software. Blender permitted only as an optional backend
  behind an interchange boundary, not as the architecture.
- The user controls Rhino instance lifecycle; worker launches must be explicit
  user-invoked actions.

## Spike Evidence (2026-07-06, live Pearson document, 426 MB, 120 layers)

1. **Background capture fidelity — PASS.** `ViewCapture` produced correct
   Arctic, Pen, and custom-mode (`Render_Layer_Color_AMR`) frames while Rhino
   was a background window. Custom display modes work through the capture
   override. (Residual: repeat once in a second, minimized instance.)
2. **Control channel survives explode — PASS.** The real Pearson roof block
   (`3D_BLOCK_ARCH_ROOF_0502 UPLIFT ROOF - VERTICAL`, 890 members, the exact
   source object named in the materialization spec) uses `ColorFromLayer` /
   `MaterialFromLayer` on every member with per-member layer assignments.
   After explode, 421 breps landed top-level on `001_MATERIAL::001_01_GARDEN
   WOOD` matching the pre-explode census. Layer-driven encoding is preserved
   exactly; no re-tuning.
3. **Live-document replay does not scale — CONFIRMED.** A 48-frame, 250-object
   compiled replay took 60–85 s wall (~1.3–1.7 s/frame vs the 41.7 ms real-time
   budget; ~35x too slow) while suspending the user's UI dispatch, and blew the
   MCP client timeout. The compact baked track was 4.4 MB for 250x48;
   extrapolated Pearson (338x240) is ~30 MB against the 8 MiB transport cap.
4. **Live-document replay corrupts undo — BUG FOUND.** After explode -> replay
   (restore_on_finish) -> undo, the undo stack could only partially revert the
   explode, leaving 250 orphan duplicates and reporting "Nothing to undo".
   Tracked as a separate fix task. This is the restore/undo class of
   brittleness made concrete.

## Decision 1: The Snapshot Boundary

A new explicit step — **take packaging** — resolves actor sets against the live
document once and writes an immutable take package:

```text
take_package/
  scene.3dm              # scene snapshot (see below; NOT a naive raw file copy)
  scene_manifest.json    # real contract, see below
  motion.json            # the existing compile-motion authoring request
                         # (from GH canvas extract / motion fragments)
  camera.json            # camera planner spec
  status.json            # job ledger: package id, phase, heartbeat, evidence
```

Nothing downstream ever reads or mutates the live document again. Authoring
(GH clock/oscillator/movement components, CanvasDirector Export, motion
fragment contract = Slices 1–2 of the canvas-export spec) is unchanged and
feeds `motion.json`.

**Baked-evaluation invariant (explicit):** worker capture consumes only the
package files. It must never call Grasshopper, generated C#, or any live
document logic per frame. All motion and camera evaluation is baked into
`motion.json`/`camera.json` before packaging. If a movement cannot be expressed
as expanded keyframes, it cannot be captured in v3 — that is a property of the
motion-fragment contract (Slices 1–2), not a worker concern.

### Scene snapshot, not raw copy

A raw disk copy packages stale geometry whenever the live document has unsaved
edits while GH exports current motion (Codex review, finding 1). The `/document`
route already reports `path` and `modified`
(`src/RookNative/Handlers/DocumentHandler.cpp:51`, `:95` — verified). Contract:

- Add `POST /document/save-copy`: write the active document to a target path
  **without retargeting the document, clearing/setting its modified flag, or
  touching its undo stack**, and **including render meshes** (explicitly not
  SaveSmall — the worker viewport must not pay a full re-mesh on open).
  Rhino's autosave is the existence proof that such a write mode exists;
  implementation should use `CRhinoDoc::WriteFile` with the appropriate
  `CRhinoFileWriteOptions` mode and must *prove* the four invariants above in
  a live gate before the route is trusted.
- Until (or in addition to) save-copy: packaging hard-fails with
  `document_not_saved` when `modified == true` and falls back to a raw copy of
  the saved file only when `modified == false`.
- `scene_manifest.json` records which mechanism produced `scene.3dm` plus the
  source document fingerprint (path, modified flag at package time, object
  count).

### scene_manifest.json is a contract

Frozen at package time, consumed and verified by the worker:

- Per actor member: `actor_member_id`, canonical source occurrence path,
  source top-level object id, block definition id + name, definition object
  index and definition object id where applicable, expected type / layer /
  name, tight bbox (verification evidence, never identity).
- Actor-set level: disjoint-ownership validation result (from CanvasDirector
  Export), member counts.
- Display-mode requirements: for each requested pass, mode name, mode id if
  resolvable, and a settings fingerprint (exported mode `.ini` content hash)
  when exportable.
- Package hashes: motion.json hash, camera.json hash, scene.3dm size/hash.

## Decision 2: Final Capture Runs in a Disposable-Copy Worker

A second Rhino instance (router plane: slots, owned launcher, discovery —
already shipped), launched explicitly by the user, opens `scene.3dm` and runs
capture there:

1. **Prepare (destructive, allowed) — with provenance recorded at explode
   time.** A Director-specific prepare route (not generic `/block/explode`)
   explodes actor-source blocks so every claimed member is a top-level object.
   The generic explode loop already iterates `pDef->Object(i)` in definition
   index order (`src/RookNative/Handlers/BlocksHandler.cpp:1527` — verified),
   so the mapping `(definition_object_index, definition_object_id) ->
   created_object_id` is available for free **during** the explode. The
   prepare route records it as it creates objects — no post-hoc fingerprint
   matching. The scene manifest's type/layer/tight-bbox fields are then used
   as *verification evidence* against the created objects, not as matching
   keys. Notes:
   - The generic loop silently `continue`s on null/failed geometry (why the
     spike produced 880 of 890) — the prepare route must report every skipped
     definition object with a reason; coverage below 100% of *claimed actor
     members* is a hard failure (`prepare_coverage_incomplete`).
   - Nested `InstanceReference` members: recursive explode in the disposable
     copy is acceptable (easier than v2's preserve-as-instance) provided the
     recursion emits occurrence-path-keyed mapping entries and layer/visual
     encoding is preserved. Reject the member only when mapping or
     verification fails.
   - No capture duplicates, no visibility manifests, no cleanup ledger, no
     binding reconciliation — the copy is throwaway.
2. **Verify display modes — fail hard.** Current managed capture silently
   falls back to the active mode when the requested mode is missing
   (`src/Rook/Handlers/ViewportHandler.cs:186` — verified). Final capture must
   not inherit that behavior: custom display modes live in the user profile,
   not the document, so the worker verifies each requested mode by name/id
   (and settings fingerprint when packaged) and fails with
   `display_mode_missing` / `display_mode_mismatch` before capturing anything.
3. **Compile (file-backed):** existing `director_compiler` logic against
   post-explode ids, reading from and writing to package files. The
   preview-shaped caps stay where they are — in the preview path.
4. **Capture (file-backed, not `/director/replay`):** a worker capture route
   reads the compiled track from the package directory (no 8 MiB HTTP body,
   no 256-object or 60 s caps), applies frames, `ViewCapture`s at the verified
   display mode. No per-frame restore (the next frame overwrites; the copy is
   disposable). Multi-pass = re-run the deterministic take per display mode /
   layer state; `rhino_capture_depth` covers depth.
5. **Assemble:** existing Media Foundation video assembly + publish pipeline.

The user's Rhino stays free the whole time.

### Worker lifecycle

Owned workbench/router-plane substrate, plus the minimum job plumbing:
`status.json` in the package directory is the job ledger (package id, phase,
per-phase evidence, heartbeat timestamp, worker instance id/port). Crash
recovery = read the ledger, delete or re-open the copy, re-run — every phase is
idempotent because the copy is disposable. Package directories get a TTL sweep
(configurable, default generous) so 400 MB copies do not accumulate silently.

## What This Deletes From the Materialization Spec — And What It Keeps

Deleted (live-document machinery):

- Document-bound actor binding layer, binding manifests, fingerprint routes
  (`/director/actor-binding/*`), capture-scene materialization with exact
  capture duplicates, role-aware visibility manifests, cleanup contracts
  (~20 of 24 decision records).
- The 256/512-object contract question: explode-in-copy has no such cliff.
- Slice 5 simplifies to compile-against-post-explode-ids.

Retained (identity work does not disappear; it moves to two narrower places —
take packaging and worker prepare):

- Package-time actor membership resolution against the live document.
- Disjoint ownership validation (CanvasDirector Export, Slices 1–2 unchanged).
- Canonical source occurrence identity carried through the scene manifest.
- Scene manifest / package hashing.
- Display-mode inventory and requirements.
- Worker post-explode coverage proof (100% of claimed members or fail).

## Repositioned: Live Replay = Small-Scale Preview Only

The shipped `/director/replay` stays for quick in-viewport preview of small
takes. Its caps (256 objects, 8 MiB, 60 s, 250 ms dwell) are **kept, not
raised** — they are now correctly sized for the only job that path retains.
Final capture never goes through `/director/replay`. Fix the undo-corruption
bug regardless.

## Deferred (Cleanly, Behind the Boundary)

- **Three.js consumer** of the same take package (WebView2 substrate,
  Pattern A): timeline scrubbing preview + per-object ID masks / depth /
  normal / lineart conditioning passes when v2v experimentation starts.
  Pen ~= lineart and Arctic ~= clay conditioning; the tuned encodings port.
- **Blender backend** behind the same package if render quality ever demands.

## Open Questions For Implementation Design

Resolved by Codex review round 1: snapshot mechanism (save-copy route +
modified gate), display-mode transport (manifest + fail-hard verification),
post-explode mapping (provenance at explode time), determinism definition
(see Test Gates).

Still open:

1. Worker capture throughput: measure apply+capture per frame in a dedicated
   instance on the copied doc (spike 3 measured the user-session replay path,
   which pays per-frame restore + drain suspension; the worker loop is
   different and should be faster, but must be measured).
2. Second-instance `ViewCapture` fidelity while minimized (residual of
   spike 1; expected to pass since capture is offscreen-buffer based).
3. `CRhinoFileWriteOptions` mode selection for save-copy: which mode provably
   preserves document path, modified flag, undo stack, and render meshes
   (autosave-style vs export-style write) — a live gate, not an assumption.
4. Whether display-mode settings fingerprinting (`.ini` export) is available
   programmatically for all modes, or only name/id verification is feasible
   in v1 (name/id + fail-hard is the floor; fingerprint is the target).
5. Camera track application in the worker (existing `DirectorViewportGuard`
   frame-camera path should transfer unchanged).
6. Worker launch UX honoring user-controlled Rhino lifecycle.

## First Implementation Plan Shape (smaller than the old spec)

1. Take package builder (save-copy route + gate, scene manifest, hashes).
2. Worker open + prepare: explode with provenance, member map, 100% coverage
   proof, display-mode verification.
3. File-backed compile + worker frame-capture loop.
4. Proofs: Pearson 338-member take, minimized-worker capture, display-mode
   fail-hard, and user-session invariance.

## Appendix: Spike Narrative (2026-07-06)

All spikes ran live against the open production document
`C:\Users\aryan\V2\Axon_Pearson_Experimental_TESTING.3dm` (426 MB on disk,
112 top-level objects, 120 layers, ~200+ block definitions, unmodified at
session start), through the normal MCP tool surface, with Rhino as a
background window (Claude Code terminal in the foreground) the entire time.
No second Rhino instance was launched (user controls instance lifecycle);
the second-instance variants are the residual measurements.

### Spike A: capture fidelity of stylized/custom modes, backgrounded

1. `rhino_display_modes` enumerated 41 modes: the stock set plus ~30
   user-tuned custom modes (`Render_Layer_Color_AMR`, `PEN_WHITE_BKGND`,
   `Arctic with Object Color`, `Render_Sketch_White`, `WhiteCard`, project
   modes like `SOH-Rendered-2`, `MBS-Rendered-3`, ...). This inventory is
   what settled the render-backend question: the AI-steering encoding is not
   three stock modes but a tuned library.
2. `rhino_viewport` captures at 1280x720 with `displayMode` override (no
   persistent mode change) for `Arctic`, `Pen`, and custom
   `Render_Layer_Color_AMR`. All three rendered correctly while Rhino had no
   foreground focus: Arctic white-matte with linework, Pen dense line
   extraction, the custom mode with layer-color semantic coding intact.

### Spike B: does layer/material encoding survive explode?

1. Target selection: listed placed blocks by member count; chose
   `3D_BLOCK_ARCH_ROOF_0502 UPLIFT ROOF - VERTICAL` (890 members, 1 instance,
   id `a28cbdb5-51fa-46b2-b18b-ab880b54ded7`) — the same source object the
   materialization spec uses in its worked examples, i.e. the real Pearson
   proof target.
2. Pre-explode census via `rhino_block_objects_detailed`: 443 Breps, 221
   Curves, 220 Points, 6 nested InstanceReferences. Every member
   `ColorFromLayer` + `MaterialFromLayer`, with per-member layer assignments
   (425 on `001_MATERIAL::001_01_GARDEN WOOD`, 400 on setout-line layers,
   plus glass/concrete/metal layers). Also confirms the mixed-block case the
   spec worried about (renderable actors + setout linework + nested blocks in
   one definition) is the normal case, not an edge.
3. `rhino_block_explode` on the instance: 880 top-level objects created
   (document went 112 -> ~991).
4. Post-explode check: 421 Breps sat top-level on
   `001_MATERIAL::001_01_GARDEN WOOD`, matching the pre-explode census
   (Brep-only; curves/points account for the remainder). Layer-driven color
   encoding preserved exactly. PASS.

### Spike C: live-document replay throughput at near-Pearson scale

1. Took 250 of the exploded GARDEN WOOD brep ids (compiler cap is 256; the
   Pearson actor set is 338).
2. `rhino_director_compile_motion`: one group, one keyframe (t=1, translate
   +8 m Z, ease_in_out), 48 frames @ 24 fps. Compile succeeded; the baked
   track serialized to 4.4 MB compact JSON (12.2 MB pretty-printed tool
   response) — ~370 bytes per object-frame for a motion whose authoring form
   is one keyframe. Linear extrapolation to Pearson (338 objects x 240
   frames) is ~30 MB vs the 8 MiB replay transport cap.
3. `rhino_director_replay` (track_path, restore_on_finish=true,
   session `spike_throughput_01`): the MCP client timed out at ~60 s;
   wall-clock from dispatch to the post-timeout probe was ~85 s.
   `rhino_director_replay_cancel` then reported `no_active_replay`, so the
   replay had completed somewhere in the 60-85 s window: ~1.3-1.7 s/frame
   for apply-250-transforms + full-scene redraw + restore-250-transforms,
   vs the 41.7 ms/frame real-time budget (~35x too slow), with the user's
   UI dispatch suspended throughout.

### The unplanned finding: replay corrupts undo coverage

1. Cleanup plan was a single `undo` to revert the explode. Result: object
   count landed at 362 = 112 + exactly the 250 replay-touched objects, and a
   second undo reported "Nothing to undo". The undo restored the block
   instance and removed the 630 exploded objects the replay never touched,
   but the 250 objects the replay had transformed (and restored) were left
   as orphan duplicates outside undo's reach.
2. Recovery: verified the 250 orphans on the GARDEN WOOD layer were exactly
   the spike's id set (set comparison: exact match, zero non-spike ids),
   then `rhino_delete` on precisely that list. Document back to 112 objects,
   block instance intact.
3. Interpretation: `DirectorObjectPoseGuard`'s direct ON_Xform apply/restore
   interacts destructively with undo records of prior operations. Filed as a
   separate fix task (repro: explode -> replay -> undo must restore original
   object count). This is the restore/undo brittleness class of the
   live-document architecture demonstrated end-to-end in one session.

### Residuals not yet measured

- Capture throughput and `ViewCapture` fidelity in a dedicated minimized
  second instance (expected fine — capture is offscreen-buffer based — but
  unproven).
- Whether user-profile custom display modes resolve by name in a fresh
  worker instance (they are not stored in the document).

## Test Gates

- Save-copy invariants: after `POST /document/save-copy`, the live document's
  path, modified flag, and undo stack are unchanged, and the written copy
  opens with render meshes intact (no re-mesh pass).
- Staleness gate: packaging with `modified == true` and no save-copy fails
  with `document_not_saved`; never packages a stale saved file silently.
- Take package round-trip: package -> worker open -> prepare -> member map
  covers 100% of claimed actor members or fails loudly per member, with every
  skipped definition object reported with a reason.
- Post-explode mapping is recorded at creation time (definition object
  index/id -> created id) and verified against scene-manifest type/layer/
  tight-bbox evidence; bbox never acts as identity.
- Nested instance members: recursive explode produces occurrence-path-keyed
  mapping entries with layer encoding preserved, or rejects the member with a
  typed error.
- Display-mode gate: a missing or mismatched requested mode fails with
  `display_mode_missing`/`display_mode_mismatch` before any frame is captured;
  the silent-fallback path in generic viewport capture is not reachable from
  final capture.
- Baked-evaluation invariant: worker capture runs with no GH, generated C#,
  or live-document evaluation per frame (audit: the worker consumes only
  package files).
- Pearson proof: 338-member actor set, 240 frames, final capture completes in
  the worker with layer-color encoding verified on first/last frames.
- Determinism: two runs of the same take produce identical *scene state* per
  frame (object transforms + camera), and frame images match either by exact
  hash (if proven stable on the pinned setup) or by pixel-diff within a stated
  tolerance at fixed resolution, display mode, AA settings, Rhino version, and
  GPU — recorded in the run evidence.
- User-session invariance: during a worker render, the user's document is
  untouched (object count, undo stack, modified flag, display mode).
