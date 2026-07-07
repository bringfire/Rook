# Director v3 Slice 4A: Worker Capture + Display-Mode Passes + Assembly

**Status:** DESIGN — approved direction with amendments (2026-07-06); pending Codex review
**Parent spec:** `docs/superpowers/specs/2026-07-06-director-v3-snapshot-boundary-design.md`
(Decision 2 items 2/4/5). Slice split: 4A = capture + passes + assembly (this spec);
4B = worker lifecycle (second instance via workbench/router plane, heartbeat, TTL sweep,
crash recovery, minimized-capture proof) — explicitly out of 4A.
**Predecessors:** S1 take package (`d5ecea0e`, #429) · S2 worker prepare (`e231600d`, #430) ·
S3 file-backed compile + delta playback (`9df22984`, #438).

## Goal

Given a prepared worker document (`prepared.3dm` + `track.json` from S3), deterministically
capture one or more display-mode passes as PNG frame sequences and assemble them into MP4s
using the existing Media Foundation pipeline — producing the first v3 video artifact.

S3 proved the transform loop at 19.18 ms/frame @300 objects unpaced; ViewCapture is the
budget item this slice measures.

## Decision 1: Capture extends `/director/worker-play` (optional `capture` block)

Capture lives inside the same UI-thread loop that already owns the pristine self-gate,
delta application, post-transform object re-lookup, probes, and the in-loop drift gate
(`DirectorWorkerPlayHandler.cpp`). No sibling route; no premature factoring of a
just-proven loop.

**Hard regression gate:** when `capture` is absent, S3 behavior is preserved exactly —
same request shape, same response keys, same play evidence, same error taxonomy. All
S3 unit suites pass unchanged. `camera_frames` in track.json remain ignored in
no-capture mode (S3 behavior).

When `capture` is present, the per-frame loop becomes:

1. Apply object deltas (unchanged S3 math: `delta_i = A_i · inv(A_{i-1})`, premultiply,
   `pDoc->TransformObject(objRef, delta, true, false, true)`, re-lookup after transform).
2. Apply the frame's camera from `track.camera_frames` (Decision 3).
3. Verify the active display mode by readback (Decision 4).
4. Redraw + capture to `framesDir/frame_%04d.png` (Decision 5).

The in-loop drift gate and pristine self-gate run unchanged. A capture failure on any
frame aborts immediately with typed `capture_failed` and the failing frame index in
evidence; frames already written are left on disk (the run root is reported as failed
and is never assembled — Decision 6).

**Full-range only (exact rule):** with `capture` present, `fromFrame` must be absent
or `0`, and `playTo` must be absent or **exactly** `frame_count`; any other value of
either is `invalid_input` (see the wire rule below). An explicit
`playTo == frame_count` is valid. Chunked/resumable capture is a 4B (crash recovery)
concern; a capture invocation is one full deterministic take.

**Wire rule for capture-mode request failures (pinned):** every failure specific to
the `capture` block — capture-block parse/validation errors (closed schema, odd
dimensions, missing/`"current"` displayMode, path policy, collision) and the
capture×chunking interaction — returns typed `data.reason = "invalid_input"` (or the
more specific `output_policy_violation`/`run_root_exists` where defined), never a
generic `SendError` and never S3's `track_invalid` request_parameters path. Python
adds `invalid_input` to the known native reasons for the capture wrapper so it
re-raises typed instead of collapsing to `capture_route_failed`. All failure paths
that exist in S3 (no-capture requests, shared parameters like `driftTolerance`)
keep their exact S3 behavior — the regression gate covers them.

## Decision 2: Policy-shaped capture paths — native never accepts a free write target

Request extension (native wire contract, camelCase):

```json
{
  "expectedDocumentPath": "...",
  "trackPath": "...",
  "capture": {
    "runRoot": "<director_output_root>/takes/<take_id>/<pass_id>",
    "framesDir": "<runRoot>/frames",
    "displayMode": "Arctic",
    "width": 1280,
    "height": 720
  }
}
```

(The S3 request surface — `expectedDocumentPath`, `trackPath`, `fromFrame`, `playTo`,
`probeFrames`, `driftTolerance` — is unchanged; `capture` is the only addition. There
is no `packageRoot` at the native layer: Python owns package verification and
document opening, native owns only the document/track/capture contract.)

Native validation (all failures typed, before any frame is played):

- `runRoot` must be under the Director output root (`GetAllowedDirectorRoot()`:
  `ROOK_DIRECTOR_OUTPUT_ROOT` else `%LOCALAPPDATA%\Rook\rookvision_director`) —
  reuse the existing `IsSameOrDescendantPath` policy check; violation →
  `output_policy_violation`.
- `framesDir` must be exactly `runRoot/frames` → `output_policy_violation` otherwise.
- Frame filename pattern is pinned to `frame_%04d.png`, 1-based. No `framePattern`
  field exists in 4A; unknown fields in `capture` are `invalid_input` (closed schema,
  matching S3's strict parsing posture).
- `width`/`height` must be positive even integers (the assembly requirement, enforced
  early) → `invalid_input`.
- **Collision policy — fresh by default:** if `runRoot` exists at all, fail with
  `run_root_exists`. No replace/overwrite mode in 4A. Native creates
  `runRoot` and `runRoot/frames` itself. This prevents stale frames from a prior run
  satisfying downstream count checks. Documented consequence: retrying a failed
  pass under the same `pass_id` requires manually deleting its failed run root (or
  choosing a new `pass_id`) — an accepted 4A friction; a designed replace mode is
  deferred with it.

Python constructs these paths (Decision 6 layout) but native re-verifies; the
orchestrator is not trusted with path policy.

**Pre-frame ordering (pinned, so pre-frame failures have a run root to mark):**

1. Parse request incl. capture block shape (closed schema, dimensions,
   displayMode presence — `invalid_input` class).
2. Load + parse track, incl. `camera_frames` contract when capture is present
   (`track_invalid` class).
3. Document gate (`wrong_document`) and capture path policy + collision checks
   (`output_policy_violation` / `run_root_exists`).
4. **Reserve the run root:** create `runRoot` and `runRoot/frames`.
5. Resolve the display mode (`display_mode_missing`).
6. Pristine self-gate, then the frame loop.

Steps 1–3 fail with no run root created (nothing to clean, no collision poisoning a
retry). From step 4 onward, any failure — including `display_mode_missing` — leaves
the empty reserved run root behind, and Python marks it `state: "failed"` (Decision
6). Gate C asserts exactly this: typed failure, zero frames, failed run root.

## Decision 3: Camera application from `track.camera_frames`

S3's compile always emits `camera_frames` (`director_worker_compile.py` →
`director_compiler.build_camera_frames`, default camera when the package has none):

```json
"camera_frames": [ { "frame_index": 1, "camera": { ... } }, ... ]
```

- **Indexing contract (off-by-one trap, pinned):** `camera_frames[i].frame_index == i + 1`
  (1-based), while track object frames are 0-based positions. Native validates the
  1-based contiguity of `camera_frames` at parse time and pairs object frame position
  `i` with `camera_frames[i]`. Captured file for position `i` is `frame_%04d.png` with
  index `i + 1`.
- When `capture` is present: `camera_frames` must exist with length exactly equal to
  the track frame count, else `track_invalid`. (Determinism: the camera comes from the
  compiled track, never from the worker's ambient viewport state.)
- Application reuses the existing pure camera-set helper shared with replay/frame
  capture (`SetCameraFromFrame`, already externally linked via
  `DirectorFrame.h:100`), inside a `DirectorViewportGuard` that snapshots the worker
  viewport before frame 0 and restores it after the run (success or failure). This resolves parent open question 5
  as predicted: the guard transfers unchanged.
- The worker-play track parser stays self-contained (S3 rule); it gains its own
  `camera_frames` parsing — it does not import the `DirectorFrame` parser.

## Decision 4: Display mode — resolve once, fail hard, readback per frame

- **`capture.displayMode` is required, non-empty, and must not be `"current"`**
  (case-insensitive) → `invalid_input`. Capture determinism forbids inheriting the
  worker's ambient display mode; `display_mode_missing` is reserved for a concrete
  name/UUID that fails to resolve.
- Resolution happens once, before frame 0 (after run-root reservation — Decision 2
  ordering), using the same strict name-or-UUID resolution logic as the existing
  single-frame path. A mode that does not resolve → `display_mode_missing`
  (translated from the resolver's throw; never generic `invalid_input`).
- **Linkage (pinned, corrected round 2):** `CurrentDisplayModeId` and
  `DisplayModeToJson` are already shared with external linkage in
  `DirectorFrame.h:109-110` — worker-play uses them directly. Only
  `ResolveDisplayModeId` is file-local (`DirectorHandler.cpp` anonymous namespace);
  4A moves that one function into `DirectorFrame.{h,cpp}` beside the existing
  display-mode helpers, with `DirectorHandler.cpp` calling the shared version
  (mechanical move, behavior-identical — resolution strictness stays
  single-sourced). No new file; no broader refactor. Note: S3's "worker-play parser
  stays self-contained" rule bars importing the `DirectorFrame` track/frame
  *parser* (which hard-rejects non-bbox_only); it does not bar linking
  `DirectorFrame.h` helper functions — S4A uses the helper closure, never the
  parser. The `"current"`-rejection rule above is enforced by the worker-play call
  site, not by changing the shared resolver's semantics (the single-frame route
  legitimately accepts `current`).
- The resolved mode is set on the capture viewport once (inside the guard scope),
  then **verified by readback after camera application on every frame** before
  capture (the `CurrentDisplayModeId` readback pattern, `DirectorHandler.cpp:1684`).
  Any per-frame mismatch → `display_mode_mismatch` with the frame index in evidence.
- The managed silent-fallback path (`ViewportHandler.cs:186`) is structurally
  unreachable: this route never touches managed viewport capture.
- Settings fingerprinting (`.ini` hash, parent open question 4) stays out of 4A;
  name/id + fail-hard + per-frame readback is the 4A floor, matching the parent
  spec's stated minimum.

## Decision 5: Capture mechanism — SDK path proven first, not assumed

The existing single-frame Director capture shells out to the scripted
`_-ViewCaptureToFile` command (`DirectorHandler.cpp:1768`). A scripted command per
frame inside a 240-iteration loop (command stack, string parsing, modal surface) is
the wrong default — but the C++ SDK offscreen capture path is **not yet proven** for
this use.

**Task 1 of the implementation plan is a proof gate, not scaffolding:** demonstrate a
C++ SDK capture path (candidate family: the display-pipeline offscreen capture that
`ViewCaptureToFile` itself drives) producing correct PNGs with (a) a custom
user-profile display mode, (b) exact requested dimensions independent of window size,
(c) a background/non-foreground Rhino window. Evidence: captured files + dimension
check + pixel-level spot check that the custom mode's encoding survived (Spike A
precedent).

**Fallback if the SDK proof fails:** per-frame scripted `_-ViewCaptureToFile`
(proven working in Spike A), with the command-stack risk accepted explicitly and the
throughput cost measured in Gate D. The spec licenses either outcome; the plan must
not proceed past Task 1 without recording which path won and why.

## Decision 6: Python `rhino_director_capture_take` — pass orchestration + assembly-compatible runs

New module `director_worker_capture.py` (reusing `director_worker_common.py`
machinery), exposed as MCP tool `rhino_director_capture_take` (MUTATE; pins 441→442).

Request:

```json
{
  "package_root": "...",
  "passes": [
    { "type": "display_mode", "display_mode": "Arctic", "pass_id": "arctic" },
    { "type": "display_mode", "display_mode": "Pen",    "pass_id": "pen" }
  ],
  "resolution": { "width": 1280, "height": 720 },
  "port": null
}
```

- `type != "display_mode"` → `unsupported_pass_type`, rejected **before any native
  call or document mutation**. The `type` field exists so depth/layer-state passes
  slot in later without schema breakage.
- `pass_id` must be unique within the request, non-empty, filesystem-safe
  (`[a-z0-9_-]+`) → `invalid_input` otherwise.
- `port`/routing context is explicit and threaded through all native calls (the 4B
  portability guardrail: no hardcoded discovery assumptions; a workbench-owned
  instance plugs in without rewriting capture).
- Package verification: full S2/S3 hash-chain re-verification (member map,
  resolved_motion, track, prepared.3dm) before pass 1 — same strict `!=` checks as
  `director_worker_play.py`.

Per pass, in order:

1. Fresh-open `prepared.3dm` via `open_package_document(mode="require_fresh")`
   (proven S3 Gate B reset — determinism between passes is guaranteed by reset,
   not trust).
2. Derive `run_root = <director_output_root>/takes/<take_id>/<pass_id>` (director
   output root resolved from the same env/default rule as native; `take_id` from the
   package manifest). Pre-check nonexistence Python-side for a friendly early error;
   native remains the authority (`run_root_exists`).
3. One native `/director/worker-play` call with the `capture` block.
4. Verify output: every `frame_%04d.png` for 1..frame_count exists, is non-empty,
   **and its PNG header (IHDR) reports exactly the requested `width × height`** —
   same semantics as `director_video.py:_png_size` (use a shared helper, do not
   duplicate the header parse). Any missing, empty, unparsable, or wrong-dimension
   frame → `pass_output_incomplete` with the failing frame and observed dimensions
   in evidence. A run that would fail assembly must never be marked complete.
5. Write assembly-compatible run metadata into the run root (amendment 2 — package
   `status.json` evidence alone is not enough):
   - `manifest.json`: `schema_version: 1`, `director_version: "slice1"` (the exact
     identity `director_video.py:_validate_manifest_identity` pins — written
     verbatim as a compatibility shim; renaming the identity is out of 4A scope),
     `run_id`, `frame_count`, `resolution: {width, height}`,
     `timeline: {fps, frame_count}` (fps from resolved_motion.json's timeline),
     `frames: [ { "frame_index": i, "file": "frames/frame_%04d.png" } ]` with
     length exactly `frame_count`.
   - `status.json` (run-root-local, distinct from the package ledger):
     `state: "complete"` plus timing/drift summary. Written **only after** step 4
     passes; a failed pass writes `state: "failed"` with the typed reason.
   - Both writes atomic (staging + `os.replace`), matching S1–S3 write discipline.
6. Append pass evidence to the **package** `status.json` (`evidence.capture_passes`,
   append-only, matching `evidence.play_runs` precedent): pass_id, display mode
   (requested + resolved), run_root, frame count, per-frame timing split
   (transform vs capture), drift result, outcome.

**Partial completion:** pass N failure preserves passes 1..N-1 evidence and their
completed run roots; the tool returns a typed failure naming the failed pass, with
`completed_passes` in the payload. A failed pass's run root is never marked
`state: "complete"` and therefore can never be assembled.

**Assembly:** consumed unchanged via the existing `rhino_director_assemble_video` /
`rhino_director_publish_video` tools against each pass run root. 4A adds no assembly
code; Gate A proves the seam end-to-end. (Assembly remains a separate user/agent
step, not an automatic tail of `capture_take` — one tool, one responsibility; a
combined convenience wrapper can come later if usage demands it.)

## Error taxonomy (additive; S2/S3 codes frozen)

Native `data.reason` additions: `invalid_input` (capture-mode request-shape
failures — the Decision 1 wire rule), `output_policy_violation` (reused semantics
from the assemble policy), `run_root_exists`, `display_mode_missing`,
`display_mode_mismatch`, `capture_failed`. Existing S3 reasons pass through
unchanged.

Python additions: `unsupported_pass_type`, `pass_output_incomplete`,
`capture_route_failed` (unknown native reason fallback, mirroring
`play_route_failed`). Known native reasons re-raise under their own codes — the
capture wrapper's known-reason set is the S3 set plus the six native additions
above, including `invalid_input`, so no typed native failure collapses to
`capture_route_failed`.

## Native response additions (camelCase, only when `capture` present)

```json
"capture": {
  "runRoot": "...", "framesDir": "...", "framesWritten": 240,
  "displayModeRequested": "Arctic", "displayModeResolved": { "id": "...", "name": "Arctic" },
  "timing": { "captureTotalMs": 0.0, "capturePerFrameMs": [0.0, 0.0] }
}
```

**Timing shape (pinned):** `capturePerFrameMs` is an **array**, one entry per frame
in play order, length exactly `framesWritten` — Gate D requires the per-frame
distribution, not a mean. `captureTotalMs` is its sum. Existing
`timing.{totalMs,perFrameMs}` keep their S3 shapes and cover the whole loop;
non-capture time per run derives from `totalMs - captureTotalMs`. The pass evidence
Python writes (Decision 6 step 6) stores the aggregate summary (total, mean, p95,
max) and keeps the full array in the native response only.

## Test gates

Unit (all mocked-native where applicable; TDD):

1. `capture` absent → S3 worker-play behavior unchanged (request/response
   golden-pin test; S3 suites pass unmodified).
2. Run-root / frames-dir policy rejection (outside root; framesDir ≠ runRoot/frames;
   existing runRoot → `run_root_exists`).
3. Camera-frame 1-based indexing, including an explicit off-by-one trap test
   (camera_frames starting at 0 or with a gap → `track_invalid`; pairing of object
   frame position i with camera index i+1 asserted).
4. `unsupported_pass_type` rejected before any native call (mock asserts zero calls).
4b. Output verification: wrong-dimension PNG (valid header, wrong IHDR size) →
   `pass_output_incomplete`, run root not marked complete; explicit
   `playTo == frame_count` with capture is accepted.
5. Partial pass failure preserves prior pass evidence, marks failed run root
   `state: "failed"`, and the failed pass is not assemblable.
6. Generated run root contains assembly-compatible `manifest.json`/`status.json`
   (validated against `director_video.py:_validate_manifest_identity` and the
   `state == "complete"` gate — imported, not duplicated).
7. Even-dimension validation; closed capture schema (unknown field → invalid_input);
   capture + fromFrame/playTo chunking → invalid_input; `displayMode` absent, empty,
   or `"current"` (any case) → invalid_input.
8. Capture timing contract: `capturePerFrameMs` array length equals `framesWritten`;
   pass evidence stores the aggregate summary (total, mean, p95, max).

Live gates (current manually-managed Rhino instance, saved scratch doc, opt-in env
vars, deploy ritual unchanged):

- **Gate A — first v3 video:** package → prepare → compile → single-pass capture →
  frames on disk → `rhino_director_assemble_video` → playable MP4.
- **Gate B — multi-pass determinism + encoding fidelity:** two passes (Arctic + Pen)
  with reset between; pixel-level spot check that the two passes differ and that
  layer-color/display-mode encoding survives PNG + MP4 (Spike A precedent).
- **Gate C — display-mode fail-hard:** request a nonexistent mode → typed
  `display_mode_missing`, zero frames written, run root marked failed.
- **Gate D — capture throughput:** per-frame transform vs capture timing split at
  meaningful object count; fills in the parent spec's open question 1 budget.

## Out of scope (4A)

4B: second Rhino instance (workbench/router plane), heartbeat/worker-id ledger
fields, TTL sweep, crash recovery/resumable capture, minimized-second-instance
fidelity proof. Further: depth pass (`type: "depth"` reserved), layer-state passes,
`framePattern` override, run-root replace mode, relaxing the `director_version:
"slice1"` assembly identity pin, display-mode `.ini` fingerprinting, automatic
assembly tail in `capture_take`.
