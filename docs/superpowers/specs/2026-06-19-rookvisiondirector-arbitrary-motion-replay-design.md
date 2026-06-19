# RookVisionDirector: Arbitrary Motion via Baked Animation Tracks + Live Replay

Date: 2026-06-19
Status: design approved (brainstorming complete); awaiting written-spec review before
implementation planning.

## Purpose

RookVisionDirector slice 1 proved a deterministic frame spine: Python orchestrates a
run, RookNative captures each frame transactionally, and a run folder preserves
manifest, status, frames, and evidence. Phases 1–4 of the camera/video roadmap added
keyframe and curve-follow camera planning, timeline authoring, native curve sampling,
and local MP4 assembly.

The one axis that was deliberately frozen is **object motion**. The authoring layer
accepts exactly one object-motion strategy, gated by a hard equality check in
`mcp_server/src/rook/director.py`:

```python
if motion.get("strategy", "radial_bbox_center") != "radial_bbox_center":
    raise DirectorInputError("motion strategy must be radial_bbox_center for slice1")
```

An agent asked to produce a *different* object motion has nowhere to put that intent.
The only knobs are `distance` and `per_object_scale`. This is why the existing
RookVisionDirector "felt un-adaptable" in practice.

The native frame-capture spine, however, is already general: it applies an arbitrary
per-object 4×4 transform plus one arbitrary camera per frame, captures, and restores.
The substrate can already express *any* motion. This design opens the authoring valve
without weakening the spine, and adds a live **replay** path so animation can be
evaluated without producing durable frames or video.

## Thesis

**Agents author arbitrary motion by generating a baked animation track; the Director
deterministically replays and captures that track.** The script is the *generator*;
the baked track is the *animation*. The native layer is never a runtime for motion
logic.

Guardrails carried from the design review:

- **The script is the generator, not the animation.** The baked track is the
  animation. The Director never imports or evaluates motion scripts during playback.
- **Absolute-from-source transforms (v1).** Each frame's per-object transform is an
  absolute pose relative to the source state, not a delta from the previous frame.
  This matches native capture's apply-then-restore-to-source semantics, keeps
  replay/video frame-order independent, and eliminates accumulated drift.
- **Once baked, the track is self-contained truth.** Replay and capture never reach
  back to a source curve, a named view, or the generator script.

## Architecture Boundaries

```
Python authoring layer                          │  Native playback layer
────────────────────────────────────────────────┼────────────────────────────────────
generators + agent scripts → bake object_frames │  apply resolved frames to Rhino
camera_planner → bake camera_frames             │  capture (PNG, transactional)
schema + source-compat validation               │  replay (live, frame-isolated)
range slicing, fps/speed, provenance            │  restore objects + viewport/display
draft↔frozen animation-track artifacts          │  output-root + payload policy (independent)
```

**Python owns** animation artifacts: generator/script execution, track baking, schema
and source-compatibility validation, range slicing, fps/speed resolution, provenance,
and the draft↔frozen track lifecycle.

**RookNative owns** live Rhino playback: applying one resolved frame at a time,
capturing PNGs, frame-isolated replay, and restore verification. Native receives
concrete resolved frames; it never loads track files and never owns run-folder policy.

Managed C# stays out of the Director core; video assembly/publish keep their existing
roles unchanged.

## The Animation Track (the contract)

One self-contained baked artifact with two independently addressable sections and a
single shared timebase. Named the **animation track** (or *baked animation*) because
after this design it carries both camera and object motion.

```jsonc
{
  "schema_version": 1,
  "animation_version": "v1",
  "frame_count": 120,
  "fps": 30,                                  // timebase; may be null for frame-count-only runs
  "resolution": { "width": 1280, "height": 720 },
  "transform_semantics": "absolute_from_source",  // scopes object motion only
  "animated_object_ids": [                    // declared once; completeness is checked against this set
    "00000000-0000-0000-0000-000000000001",
    "00000000-0000-0000-0000-000000000002"
  ],
  "camera_frames": [
    {
      "frame_index": 1,
      "camera": { "projection": "perspective", "location": [...], "target": [...],
                  "up": [...], "lens_length": 35.0, "fov_degrees": null,
                  "aspect": 1.7778, "near_clip": 0.1, "far_clip": 1000.0 }
    }
    // ... one explicit camera per frame
  ],
  "object_frames": [
    {
      "frame_index": 1,
      "object_transforms": [
        {
          "object_id": "00000000-0000-0000-0000-000000000001",
          "source_state": { "bbox_min": [...], "bbox_max": [...],
                            "validation_strength": "bbox_only", "state_hash": null },
          "transform": [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]   // absolute-from-source
        }
        // ... exactly the animated_object_ids set, every frame
      ]
    }
    // ... one entry per frame
  ],
  "camera_provenance": { "strategy": "curve_follow_target", "curve_id": "...",
                         "target": [...], "up": [...], "sampling": {...},
                         "aspect_authority": "resolution", "optics_authority": "lens_length" },
  "object_provenance": { "generator": "radial_bbox_center", "parameters": {...},
                         "script_artifact_id": null, "warnings": [] }
}
```

### Section ownership and guarantees

- **`camera_frames`** — one explicit camera per frame, produced by the existing
  `camera_planner` (`keyframes`, `curve_follow_target`). Camera carries its own
  compatibility/provenance rules: aspect/resolution authority, projection support
  (perspective in v1), non-degenerate direction and up validation, and any Rhino doc
  references (named views, curves) recorded as *provenance only*.
- **`object_frames`** — uses native's existing `object_transforms[]` entry shape
  (`object_id`, `source_state`, `transform`) so it is **lossless** to what
  `/director/frame-capture` already consumes — no map format, no lossy adapter. The
  `absolute_from_source` semantics and `source_state`/`state_hash` compatibility data
  apply to this section.
- **Completeness (v1):** the `animated_object_ids` set is declared once. **Every frame
  must contain a transform entry for exactly that set.** Identity transforms are
  allowed (a held/static object emits identity). A missing entry is a **validation
  error**, never an implicit identity. This removes playback ambiguity.
- **Self-contained:** once baked, both sections are fully explicit. Playback never
  depends on the source curve, named view, or generator script still existing.

## Authoring: Generators and the Agent-Script Compile Step

Two ways to populate `object_frames`, both producing the identical track schema.

### Built-in generators

Generators are convenience functions that compile to `object_frames`. **v1 ships
`radial_bbox_center` ported** to emit the track schema, proving the compile path
against existing, live-verified behavior. Camera sections are produced by the existing
`keyframes` / `curve_follow_target` planners. Additional generators (orbit,
object-path-follow, staggered-explode) are deferred and added incrementally once the
compile path is proven.

### Agent-authored object-motion script (the thesis-prover)

This is the path that delivers "arbitrary motion." It is scoped as a **compile step,
not a runtime**:

- **Where it runs:** the Python/MCP authoring process. Never in RookNative, never on
  the Rhino UI thread, never during playback.
- **Inputs (`context`, plain JSON-serializable data):** resolved object state (ids,
  bbox/source state, units), `frame_count`, `fps`/timebase, and optional caller
  `parameters`.
- **Output:** `object_frames` data, **returned** from a `generate(context) ->
  object_frames` function. The script never writes the track or any file directly.
- **Constraint model (convention + validation, NOT structural prevention):** the
  script is executed with a restricted globals namespace that injects no
  Rhino/MCP/bridge client and no `call_rhino` transport. This is a **guardrail and
  convention, not a sandbox** — a determined script could still `import` a client, reach
  `localhost`, or touch the filesystem, and **v1 does not prevent that**. We explicitly
  do **not** claim "the script structurally cannot mutate Rhino." The trust model is
  identical to agent-authored Rook scripts that already run today (`run_library_script`,
  durable script artifacts): agent-authored, under user oversight. A hardened sandbox
  for untrusted (non-agent) scripts is a separate future effort, out of v1 scope.
- **What IS enforced (the load-bearing invariants):** (1) **playback never invokes the
  script** — only baked frames are replayed/captured; (2) the script's returned
  `object_frames` are **schema- and source-compat-validated before use**, so a
  misbehaving script still cannot inject an invalid track into playback; (3) replay and
  capture **restore source on every exit**. Determinism and safety come from baking +
  validation + restore, **not** from sandboxing the generator.
- **Provenance + reuse:** the script is stored via the existing durable
  script-artifact machinery; its artifact id is recorded in
  `object_frames`/`object_provenance`. Playback ignores it.
- **Validation:** the returned `object_frames` are schema-validated (shape,
  completeness, finite numeric matrices, source-compat) **before** any replay or
  capture. A malformed generator output fails at bake time, not at playback.

## Live Replay

Replay plays a baked track live in the active Rhino viewport so the animation can be
evaluated **without** producing durable frames or video.

### Semantics

**Frame-isolated playback (not accumulated).** For each displayed frame, the visible
state is *source plus that frame's absolute transforms*. Native may restore/apply
internally, but the viewport is only redrawn after the next frame's pose is applied.
**Final state restores to source on completion, cancel, timeout, ESC, detected
disconnect, or failure** — with cancel and timeout as the guaranteed exits and
ESC/disconnect best-effort.

### Native route and cancellation model

Replay is a long-running viewport operation in a server where requests serialize
through the Rhino UI thread. A native route therefore **cannot both *return* a session
id and *block* until the sequence finishes** — the caller would learn the id too late
to cancel it. v1 resolves this by having the **caller provide the session id**, so the
id is known independently of when the call returns.

`POST /director/replay`

- Caller (Python) generates and supplies **`replay_session_id`** in the request.
- Accepts a **resolved, already-sliced** payload: `replay_session_id`, `frames` (each
  carrying `camera`, `object_transforms`, `display`), an **effective positive `fps`**,
  and optional `speed`. Range selection (`start_frame`/`end_frame`) is applied at the
  MCP/Python layer before native is called — native receives only the frames it should
  play.
- Writes **no PNG, no manifest, no run folder**.
- Runs the replay loop on the Rhino UI thread (apply → redraw → hold), pacing
  `fps × speed` **best-effort** (replay is a preview; if per-frame apply+redraw cannot
  hit real time, it plays as fast as it can).
- **Interruptible pacing (load-bearing for "live" replay).** The per-frame hold is
  **never a single blocking sleep** on the UI thread. The effective dwell
  `min(1/(fps×speed), max_per_frame_dwell)` is sliced into short intervals
  (**≈16 ms**, ~one display refresh — `pump_slice`). Each slice keeps the window
  responsive with a **bounded pump that must not drain the HTTP→UI dispatch queue** (no
  foreign request may mutate the document mid-replay — a reentrancy hazard the
  implementation plan must verify against RookNative's dispatch mechanism), then checks
  the exit conditions. Cancel/timeout latency is therefore bounded by **one
  non-interruptible `apply → redraw` step plus one pump slice — not by the frame
  dwell**. It is *not* literally ~16 ms: a heavy frame (many object transforms or an
  expensive redraw) extends the non-interruptible step, and cancel/timeout can only be
  observed after that step completes.
- **Exit conditions, split by guarantee:**
  - **Guaranteed, pump-free:** the worker-thread **cancel flag** (an atomic the replay
    loop reads each slice — it needs no UI pump because the cancel route set it from a
    different thread) and the running **wall-clock timeout**. These are the exits v1
    promises.
  - **Best-effort:** the Rhino **ESC key** and **client disconnect**, which depend on a
    bounded pump and on cpp-httplib's disconnect being safely observable from the
    dispatched loop. The implementation plan verifies the exact APIs; if either is not
    safely observable, the **timeout remains the guaranteed backstop** for an abandoned
    replay.
- **Restores objects + viewport/display on every exit path** — completion, cancel,
  timeout, ESC, **detected** disconnect, and failure. Disconnect-triggered restore is
  best-effort (it fires only if the disconnect is observed); when a client abandons a
  replay without a detectable disconnect, the **wall-clock timeout is the guaranteed
  abandoned-client backstop** that restores and ends the session. Returns structured
  **replay evidence**: frames attempted, frames displayed, terminal reason
  (`completed`/`cancelled`/`timeout`/`esc`/`disconnect`/`failed`), any `pacing_clamped`
  warning, dirty-state flag, and restore status.
- Replay is **bounded by explicit duration caps** (see Payload & Duration Limits), so it
  cannot hold the UI thread longer than `max_effective_replay_duration`. Within that
  bound, **v1 treats replay as a foreground interactive operation: other Rook requests
  queue until it ends.** This is acceptable because the user is actively watching the
  preview and the agent is waiting on their verdict; the async evolution below is the
  escape hatch if replays ever need to run without holding the UI thread.

`POST /director/replay/cancel`

- Accepts `{ "replay_session_id": "..." }`.
- **Handled entirely on the HTTP worker thread and explicitly NOT enqueued on the
  UI-thread dispatch** — it only sets the atomic cancel flag for that session id.
  Running it on a worker thread is what makes it serviceable *while* the replay loop
  holds the UI thread; if it were routed through the same serialization queue it would
  deadlock behind the replay it is trying to stop. This is the load-bearing threading
  invariant for the whole cancellation story.

**Session lifecycle and races (v1):**

- The server keys an in-memory **replay session registry** by `replay_session_id`. The
  session is **registered when `/director/replay` is received, before the replay loop is
  dispatched to the UI thread**, so a cancel arriving immediately after can find it.
- **One active replay at a time.** A second `/director/replay` while one is active is
  **rejected** with a structured error — no queued or concurrent replays in v1, because
  two loops must never contend for the UI thread.
- **Duplicate `replay_session_id`** (one already registered) is rejected.
- **Cancel for an unknown or already-finished id is idempotent**: it returns a benign
  "no active session" result, never an error — a late cancel must not break a caller.
- **Cancel before the loop starts** sets the flag; the loop sees it on its first slice
  check and exits immediately with full restore.
- The session is **unregistered only after the terminal state and after restore
  completes**, so an id cannot leak or block the next replay.

**Deferred evolution (not v1):** if bounded synchronous replay proves too coarse for
long tracks, split replay into async `start` / `status` / `cancel` routes with
timer/idle-driven frame advance, so the UI thread is never held for more than a single
frame. The frame/track schema and the resolved-frame payload do not change; only the
route lifecycle does.

### MCP tool

`rhino_director_replay` accepts **either** a `track_path` **or** an inline `track`,
plus optional `start_frame` / `end_frame` / `speed`:

```jsonc
{ "track_path": "<run>/animation_track.json", "start_frame": 20, "end_frame": 80, "speed": 0.5 }
// or
{ "track": { /* baked animation track */ }, "speed": 1.0 }
```

Python owns track-path and schema validation, source-compatibility checks, range
slicing, provenance, and two resolutions native depends on: it **generates the
`replay_session_id`** and resolves an **effective positive FPS** for pacing — using the
track's `fps`, or a **default preview FPS** (frame-count-only tracks where `fps` is
null) or an explicit caller override. It resolves the selected frames and sends native
a concrete frame list with the id and effective fps. Native never loads track files and
never receives a null fps.

### Payload & duration limits (v1)

**Payload caps**, enforced in Python and **independently re-enforced in native**
(defense-in-depth, like output-root policy):

- max **3000 frames** per replay request (after range slicing);
- max **256 animated objects**;
- max **8 MiB** inline payload.

**All three apply simultaneously**, and a request is rejected if it exceeds **any** of
them. Because 3000 frames × 256 objects of matrix + source-state data far exceeds 8 MiB,
the **payload-size limit (8 MiB) is usually the binding constraint**; the frame and
object caps are coarse safety ceilings. Python slices the requested range before sending
and does not silently truncate.

**Duration caps** — the bound that actually protects the UI thread (payload caps alone
do not bound *time*):

- **`max_per_frame_dwell` = 250 ms (v1 default).** The effective per-frame hold is
  `min(1/(fps×speed), max_per_frame_dwell)`. A low-FPS or slow-`speed` request that
  would dwell longer is **clamped** to this value, and evidence records a
  `pacing_clamped` warning — the preview plays faster than nominal timing rather than
  hanging a single frame on the UI thread.
- **`max_effective_replay_duration` = 60 s (v1 default), enforced two ways:**
  - **Pre-validation:** if projected duration `frame_count × effective_dwell` exceeds the
    cap, the request is **rejected before playback** with a structured error (shorten the
    range, raise FPS/speed, or split the replay) — an upfront error, not a surprise
    mid-replay stop.
  - **Runtime:** the running **wall-clock timeout** enforces the same cap during the
    loop, covering per-frame apply/redraw cost as well as dwell. This is the `timeout`
    exit.
- **`pump_slice` ≈ 16 ms (v1 default)** — the granularity at which the hold is sliced and
  exits are checked. Cancel/timeout latency = one non-interruptible `apply → redraw` step
  + one `pump_slice` (a heavy frame extends the apply/redraw step), **not** the frame
  dwell and not literally one slice.

All durations are v1 defaults, tunable, and re-enforced by native independently of
Python.

## run_director Refactor + Draft↔Frozen Tracks

`run_director` is refactored from "compute motion inline, then capture" to **"bake an
animation track, then capture from it."** Concretely:

1. Resolve objects + camera plan + object motion (generator or script) into an
   in-memory/draft animation track.
2. Validate the track (schema, completeness, source compatibility).
3. Optionally **replay** the draft for evaluation.
4. On capture, capture frames **from the track** and **freeze** the track to
   `<run>/animation_track.json` alongside the existing `manifest.json`, `status.json`,
   `frames/`, `logs/`.

**Draft track path:** because replay can happen before durable capture, a
draft/temporary track path is supported. The track is frozen into the run folder only
when capture is approved/performed. This keeps the iterate loop (bake → replay →
refine) free of run-folder side effects.

**Approval is a workflow gate, not an API invariant.** `run_director` and the
lower-level tools remain **deterministic APIs**: given a valid track, they capture.
Only the `/animate` skill requires replay acceptance before capture. Direct API
callers may capture from any valid track.

Video assembly (`rhino_director_assemble_video`) and publish
(`rhino_director_publish_video`) are **inherited unchanged**, now fed from the
track-based run.

## Skills

### `/design-animation`

Mirrors `design-grasshopper`: explore the scene (objects, curves, units, existing
views), run **RookVisionDirector-specific Q&A**, and produce a **lightweight but real
reviewable brief**. The brief captures creative intent and constraints, not every
transform:

- subject / object set;
- motion intent;
- camera intent;
- timing / fps / duration;
- key moments / beats;
- required scene references: layers, curves, points, views;
- acceptance criteria for replay.

### `/animate`

Owns the iterative execution loop in **one context**, with **explicit internal
phases** (these are phases, not separate user-facing skills in v1):

1. load design brief;
2. inspect scene / current track;
3. choose a generator **or** author a motion script;
4. bake the absolute animation track;
5. validate track + source compatibility;
6. **replay**;
7. **refine** (edit generator/script/track, re-bake, replay again);
8. **capture only after replay approval**;
9. assemble / publish only when requested or approved.

The refine loop is why `/animate` is a single skill rather than a plan/execute split:
the user watches replay and says "stagger the parts more," "slow the camera," "hold on
the reveal," and the agent edits and replays again without crossing a skill boundary.

## Error Handling & Validation

- **Track schema validation** on every baked track: shape, finite numeric matrices,
  per-frame completeness against `animated_object_ids`, camera direction/up/aspect
  validity (existing `camera_planner` rules).
- **Source-compatibility gate** before replay/capture, with **explicit modes driven by
  `validation_strength`**:
  - `state_hash` present → **hash match required** (strongest).
  - `validation_strength == "bbox_only"` (hash null) → **bbox match within tolerance**
    between the live object and the recorded `source_state` bbox.
  - **Same-run** baking captures `source_state` fresh, so the gate passes by
    construction. **Cross-run reuse** is permitted only when the applicable mode passes,
    and replay/capture evidence records when the weaker bbox-only gate was used so the
    caller knows the validation strength. A failed gate **rejects** the track — it never
    silently applies transforms to the wrong geometry. (This is why the schema permits
    `state_hash: null`: that object is validated in bbox-only mode, not left
    unchecked.)
- **Generator/script failures** surface at bake time with structured errors; a
  malformed script output never reaches playback.
- **Native independence:** native re-validates output-root policy (capture) and
  payload limits (replay), and rejects non-perspective projection before mutation
  (v1).
- **Restore guarantee:** replay and capture both restore objects + viewport/display on
  every exit path — cancel, timeout, ESC, detected disconnect, and failure (cancel and
  timeout guaranteed; ESC/disconnect best-effort).
- **Capture safety:** in the `/animate` workflow, durable capture is gated behind
  replay approval so a bad track cannot silently produce durable output.

## Backward Compatibility

Existing `rhino_director_run` requests using `radial_bbox_center`, `keyframes`, and
`curve_follow_target` **continue to work unchanged**. The animation track is
**additive**:

- `run_director` now bakes a track internally, but the existing `manifest.json` fields
  (`frames[*].camera`, `frames[*].object_transforms`, `motion`, `camera_plan`,
  `camera_keyframes`, …) are preserved so existing manifest consumers do not break.
- `animation_track.json` and `animation_version` are new, additive artifacts/fields.
- Any future breaking change to the manifest shape would be explicitly versioned;
  v1 removes no slice-1 fields.

## Testing

- **Unit:** track schema validation (completeness, identity-allowed, missing-entry
  rejection, finite matrices); `radial_bbox_center` port **parity** against the current
  inline output; draft↔frozen lifecycle; range slicing and payload-limit enforcement;
  source-compatibility gate.
- **Native source/contract:** `/director/replay` restore-on-cancel and
  restore-on-timeout (guaranteed exits); best-effort restore-on-detected-disconnect;
  `/director/replay/cancel` flips the flag without touching Rhino; payload- and
  duration-limit re-enforcement.
- **Live proof (the thesis test):** one **non-radial, agent-authored** custom motion
  (e.g. per-object staggered timing or a sinusoidal path) that the old
  `radial_bbox_center`-only request **could not express** → bake → validate → replay →
  capture → assemble. This is the test that proves the product thesis, not just a
  refactor.

## v1 Scope

**In v1:**

1. Animation-track schema (two sections, `absolute_from_source`), run-scoped at
   `<run>/animation_track.json` with draft-path support; source-hash present so
   cross-run reuse is *possible* later.
2. Generator → track compile path, with `radial_bbox_center` ported as the reference
   object-motion generator. Camera sections from existing planners.
3. Agent-authored object-motion script path (compile step, constrained namespace) →
   bakes `object_frames`, with the non-radial custom-motion live proof.
4. Native `/director/replay` + `/director/replay/cancel` + MCP `rhino_director_replay`
   (track_path or inline; Python resolves frames, native plays).
5. `run_director` refactor to bake-then-capture, draft↔frozen tracks, approval as a
   workflow (not API) gate.
6. Both skills: `/design-animation` and `/animate`.

**Deferred (explicitly out of v1):**

- Multi-clip composition / sequencing — a later **authoring-layer** utility that
  compiles multiple clips into one baked track; Director stays unchanged. (Note:
  `absolute_from_source` tracks are safe to concatenate as *data*, but boundary poses
  must be intentionally checked for smoothness — an authoring concern.)
- A richer built-in generator library (orbit, object-path-follow, staggered-explode).
- A project-level reusable track store.
- Live-evaluated scripts during playback (rejected: moves arbitrary code execution into
  playback, undermining replay/video determinism and debuggability).
- Mac replay/assembly backends (consistent with the existing Windows-first roadmap).

## Implementation PR Split

One product slice, sequenced into reviewable PRs:

1. **Schema + radial port + `run_director` captures-from-track** (draft↔frozen, parity
   test).
2. **Native `/director/replay` + `/director/replay/cancel` + MCP wrapper** (frame
   resolution, limits, restore/cancel contract tests). **PR2 must begin with a small
   native spike that verifies the "bounded pump that must not drain the HTTP→UI dispatch
   queue" assumption** (no foreign request mutates the document mid-replay; ESC is
   observable). If that pump cannot be done safely, the plan **removes pumping from
   synchronous replay** (cancel + wall-clock timeout stay guaranteed and pump-free; ESC
   is dropped) **or switches replay to the async `start`/`status`/`cancel` model**. The
   track/frame architecture does not change either way — only replay's pump/route
   lifecycle. **Critically, the "remove pumping" fallback still keeps the sliced
   wait/check loop** — it means "no UI message pump," never "go back to a blocking
   sleep"; the per-`pump_slice` cancel/timeout checks remain.
3. **Agent-script generator path + non-radial custom-motion proof** (constrained
   namespace, schema validation, live thesis test).
4. **`/design-animation` and `/animate` skills.**

## Self-Review

- The native frame-capture spine is unchanged; only the authoring valve opens and a new
  read-mostly replay route is added.
- The baked track is executable truth; scripts are authoring/provenance only and are
  never imported by playback.
- `absolute_from_source` keeps replay/video frame-order independent and drift-free.
- Cancellation is coherent and bounded: caller-provided session id (never learned too
  late); worker-thread cancel atomic + wall-clock timeout as **guaranteed, pump-free**
  exits (latency = one non-interruptible apply/redraw step + one pump slice, not
  literally ~16 ms); ESC/disconnect as best-effort; the per-frame hold is
  **sliced, never a blocking sleep**; explicit `max_per_frame_dwell` /
  `max_effective_replay_duration` caps mean replay cannot hold the UI thread beyond a
  bounded, validated duration; and a session registry defines registration/duplicate/
  idempotent-cancel/single-active rules. Async start/status/cancel is the documented
  evolution.
- The script boundary is honestly labeled: convention + validation, **not** structural
  prevention. The enforced invariants are no-script-at-playback, validated output, and
  source restore — not a sandbox. Trust model equals existing agent-run scripts.
- Approval is separated: `/animate` workflow gates capture on replay acceptance; APIs
  stay deterministic.
- Object-frame completeness and native-shaped frames remove playback ambiguity and
  avoid lossy conversion.
- Backward compatibility is preserved; the track is additive.
