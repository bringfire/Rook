# Director v3: Snapshot Boundary + Disposable-Copy Render Worker

Status: direction design, validated by live spikes
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
  scene.3dm            # raw disk copy of the source document (preserves render
                       # meshes; SaveSmall would force a costly re-mesh on open)
  scene_manifest.json  # actor member -> object id map frozen at package time,
                       # layers/display-mode inventory, document fingerprint
  motion.json          # the existing compile-motion authoring request
                       # (from GH canvas extract / motion fragments)
  camera.json          # camera planner spec
```

Nothing downstream ever reads or mutates the live document again. Authoring
(GH clock/oscillator/movement components, CanvasDirector Export, motion
fragment contract = Slices 1–2 of the canvas-export spec) is unchanged and
feeds `motion.json`.

## Decision 2: Final Capture Runs in a Disposable-Copy Worker

A second Rhino instance (router plane: slots, owned launcher, discovery —
already shipped), launched explicitly by the user, opens `scene.3dm` and runs
capture there:

1. **Prepare (destructive, allowed):** explode actor-source blocks so every
   actor member is a top-level object. No capture duplicates, no visibility
   manifests, no cleanup ledger, no binding reconciliation — the copy is
   throwaway. Record the post-explode member -> object id map (spike 2 shows
   layer attributes survive; the map comes from the explode results keyed by
   the scene manifest).
2. **Compile:** existing `director_compiler` against post-explode ids. Raise
   caps freely (no interactivity constraint); pass tracks by file path, not
   HTTP body, killing the 8 MiB transport issue.
3. **Capture:** per-frame apply + `ViewCapture` at the chosen display mode.
   No per-frame restore needed (next frame overwrites), no drain-suspension
   pressure on a user, no 60 s cap. Multi-pass = re-run the deterministic take
   per display mode / layer state; `rhino_capture_depth` covers depth.
4. **Assemble:** existing Media Foundation video assembly + publish pipeline.

The user's Rhino stays free the whole time. Worker crash = delete copy, retry.

## What This Deletes From the Materialization Spec

- Slices 3–4 entirely: actor binding layer, binding manifests, fingerprint
  routes (`/director/actor-binding/*`), capture-scene materialization,
  role-aware visibility manifests, cleanup contracts (~20 of 24 decision
  records).
- The 256/512-object contract question: explode-in-copy has no such cliff.
- Slice 5 simplifies to compile-against-post-explode-ids.
- Slices 1–2 (motion fragment contract, take assembler, disjoint ownership
  validation) survive as the authoring source of `motion.json`.

## Repositioned: Live Replay = Small-Scale Preview Only

The shipped `/director/replay` stays for quick in-viewport preview of small
takes. Document its measured ceiling (spike 3) and keep its caps. It is no
longer on the path to final capture. Fix the undo-corruption bug regardless.

## Deferred (Cleanly, Behind the Boundary)

- **Three.js consumer** of the same take package (WebView2 substrate,
  Pattern A): timeline scrubbing preview + per-object ID masks / depth /
  normal / lineart conditioning passes when v2v experimentation starts.
  Pen ~= lineart and Arctic ~= clay conditioning; the tuned encodings port.
- **Blender backend** behind the same package if render quality ever demands.

## Open Questions For Implementation Design

1. Worker capture throughput: measure apply+capture per frame in a dedicated
   instance on the copied doc (spike 3 measured the user-session replay path,
   which pays per-frame restore + drain suspension; the worker loop is
   different and should be faster, but must be measured).
2. Second-instance `ViewCapture` fidelity while minimized (residual of
   spike 1; expected to pass since capture is offscreen-buffer based).
3. Take package copy cost for large documents (426 MB Pearson copy was
   instant on local disk; SaveSmall vs raw file copy).
4. Display-mode transport: custom modes live in the user's Rhino profile, not
   the document — worker must import/verify the named mode (`.ini` export or
   shared scheme) before capture, else fail loudly.
5. Camera track application in the worker (existing `DirectorViewportGuard`
   frame-camera path should transfer unchanged).
6. Worker launch UX honoring user-controlled Rhino lifecycle.

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

- Take package round-trip: package -> worker open -> prepare -> member map
  covers 100% of claimed actor members or fails loudly per member.
- Pearson proof: 338-member actor set, 240 frames, final capture completes in
  the worker with layer-color encoding verified on first/last frames.
- Multi-pass determinism: two runs of the same take produce byte-identical
  frame sequences per display mode.
- User-session invariance: during a worker render, the user's document is
  untouched (object count, undo stack, display mode).
