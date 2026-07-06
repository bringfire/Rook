# Director v3 Slice 3: File-Backed Compile + Delta Worker Playback — Design

**Status:** approved design, pre-implementation
**Parent spec:** `docs/superpowers/specs/2026-07-06-director-v3-snapshot-boundary-design.md` (Decision 2 items 3–4, "Worker playback math" section)
**Predecessors:** Slice 1 take packages (`d5ecea0e`, PR #429), Slice 2 worker prepare (`e231600d`, PR #430)
**Scope boundary:** NO capture, NO camera application, NO worker lifecycle/TTL (all Slice 4). `compile_motion`, `validate_caps`, and `DirectorReplayHandler` are untouched.

## What This Slice Builds

The worker pipeline's middle: compile the prepared take into a frame-exact
track, and play that track in the worker document with delta math — proven,
gated, and capture-less. Slice 4 wraps `ViewCapture` around the already-gated
loop.

```
scene.3dm ──prepare (S2+)──> prepared.3dm ──compile (S3)──> track.json ──worker-play (S3)──> proven playback
                              [authoritative reset artifact]                                   [S4: + capture]
```

## Decision 1: `prepared.3dm` is the authoritative reset artifact (S2 extension)

Fresh-opening `scene.3dm` destroys the prepare: exploded, member-mapped
objects exist only in the open document, and re-preparing mints new UUIDs
that invalidate every downstream artifact. The parent spec's "fresh-open
scene.3dm" reset is therefore replaced:

> Slice 3 persists the prepared worker document as `prepared.3dm` immediately
> after successful prepare. `member_map.json` and `resolved_motion.json` are
> valid against `prepared.3dm`, not merely the current Rhino session. Every
> playback/capture run starts by opening `prepared.3dm` fresh, establishing
> pristine state with stable prepared object UUIDs. Runtime inverse-restore
> may still be used as an optimization within a run, but it is not the
> authoritative reset mechanism.

Mechanics (change to `director_worker_prepare.py`):

- After coverage + evidence verification pass and BEFORE the member-map /
  resolved-motion writes: call `POST /document/save-copy` with target
  `<package>/.prepared.3dm.staging`, enforce the same seven-field invariant
  evidence contract as Slice 1 (path/title/modified unchanged, no SaveSmall),
  then `os.replace` → `prepared.3dm`. Object UUIDs persist through 3dm
  save/open, so the member map remains valid against the file.
- `member_map.json` gains an additive block (no schema-version bump):
  `"prepared_scene": {"file": "prepared.3dm", "sha256": ..., "bytes": ...}`.
  `status.json` evidence mirrors it. Packages prepared before this change
  fail compile with `package_invalid` ("missing prepared.3dm; re-run
  prepare") — acceptable: the copy is disposable, re-prepare is the recovery.
- Re-prepare overwrites `prepared.3dm` (staging + `os.replace`, never a
  partial file at the final name).

## Decision 2: Compiler — `director_worker_compile.py` (new module)

`async def compile_take(arguments={"package_root"}, *, call_native, port,
now_fn)` mirroring the S1/S2 module shape (`DirectorWorkerCompileError(code,
message)` with `.to_data()`).

**Pipeline:**

1. Load + validate package: files present (now including `prepared.3dm`,
   `member_map.json`, `resolved_motion.json`); status phase in
   `("prepared", "compiled")` (recompile allowed — artifacts overwritten);
   hash chain verified end-to-end: status ↔ manifest,
   `resolved_motion.derived_from.member_map_sha256` ↔ `member_map.json`
   bytes, `member_map.prepared_scene.sha256` ↔ `prepared.3dm` bytes.
2. **Self-contained document handling:** `compile_take` opens `prepared.3dm`
   itself (refuse dirty live doc with `document_not_saved`; ALWAYS issue the
   open; verify active path after). It is NOT an external precondition that
   the doc is already open — the MCP tool must be operator-ergonomic and
   sequencing-proof. Opening `prepared.3dm` fresh on every compile doubles
   as the round-trip proof that the snapshot is self-sufficient
   (member-mapped UUIDs resolvable after save/open).
   **Same-path reload contract (S3 refinement of the S2 rule):** when the
   native open reports `alreadyOpen: true` (no reload happened), compile
   does NOT fail closed — it performs a **double-hop reload**: open
   `scene.3dm`, then open `prepared.3dm`. Both hops are genuine path
   changes, so neither can no-op; the result is a provably fresh load with
   zero new native surface. Only if the double-hop still lands on the wrong
   path does it fail (`take_copy_not_pristine`). S2's prepare keeps its
   original fail-closed behavior (its intermediate file may not exist yet).
3. **Reuse compiler math, not compiler evidence policy:** call
   `director_compiler.resolve_compiler_timeline`, `expand_targets` (the
   resolved motion is already in its vocabulary — groups are created-UUID
   lists), `build_object_frames`, `build_camera_frames` (camera spec from
   packaged `camera.json`; absent → existing active-view default; camera
   frames are compiled into the track now, applied only in S4). Do NOT call
   `validate_caps` — the only worker constant is
   `WORKER_MAX_FRAME_COUNT = 100_000` (absurdity guard, its own explicit
   constant per the parent spec).
4. **Worker source-state path (tight-bbox contract):** do NOT reuse
   `resolve_source_states` unchanged — it discards `bbox_method` and
   hardcodes `validation_strength: "bbox_only"`
   (`director_compiler.py:201`). The native route already emits
   `bbox_method` per object (`SerializeObjectState`,
   `DirectorHandler.cpp:539`) — no native change needed. New
   `resolve_worker_source_states`: same `/director/object-states` call,
   REQUIRES `bbox_method == "tight_object"` for every animated object
   (else `compile_source_state_not_tight`, listing offenders), and writes
   `{"bbox_min", "bbox_max", "bbox_method": "tight_object",
   "validation_strength": "tight_bbox", "state_hash"}` into each
   `object_frames[].object_transforms[].source_state`.
   Additionally cross-check the animated id set == the member map's
   created-object id set (`compile_track_mismatch` on any difference — the
   resolved motion and the member map must describe the same objects).
5. Write `track.json` (schema otherwise unchanged:
   `transform_semantics: "absolute_from_source"`, fps, frame_count,
   `animated_object_ids`, `camera_frames`, `object_frames`) plus a
   `derived_from` block `{resolved_motion_sha256, member_map_sha256,
   prepared_3dm_sha256}`; write `compile_provenance.json` (the compiler's
   provenance return). All-or-nothing: hash/serialize before any write.
   Advance status: phase `compiled`, evidence gains `track_json_sha256` +
   `compile_provenance_sha256`. Track size scales as objects × frames
   (~9 MB at 886×48) — a disk artifact by design; it never rides an HTTP
   body.

## Decision 3: Native worker playback — `DirectorWorkerPlayHandler.cpp` (new file)

`POST /director/worker-play`. Self-contained, stateless, capture-less.
Shares nothing with `DirectorReplayHandler` except the track schema it
reads: no slot/session state, no caps, no dwell pacing, no restore-on-finish
semantics, no preview transport. Pure math utilities may be factored and
shared where practical; route machinery may not.

**Request:**

```json
{
  "expectedDocumentPath": "<package>/prepared.3dm",
  "trackPath": "<package>/track.json",
  "fromFrame": 0,
  "playTo": 48,
  "probeFrames": [24, 48],
  "driftTolerance": null
}
```

`fromFrame` default 0 (source pose); `playTo` default `frame_count`;
`probeFrames` optional (≤ 32 entries); `driftTolerance` optional override,
default `10 × doc absolute tolerance`.

**Sequence (all gates before any mutation):**

1. Document-path refusal (case/slash-normalized), same
   `data.reason = "wrong_document"` failure shape as prepare-take.
2. Read + parse `track.json` from disk. Validate: `transform_semantics ==
   "absolute_from_source"`, `object_frames` length == `frame_count`,
   `frame_index` ordering, `0 <= fromFrame < playTo <= frame_count`
   (`track_invalid` otherwise).
3. Resolve every animated object id (`pDoc->LookupObject`); any miss →
   failure `track_objects_missing` listing the ids.
4. **Stateless pristine self-gate:** every animated object's observed tight
   bbox must match its pose at `fromFrame` within tolerance — the
   `source_state` bbox for `fromFrame == 0`, or the predicted envelope of
   `A_fromFrame` for a chunked resume. Mismatch → failure
   `worker_scene_not_pristine` (per-object evidence). This is what makes
   the stateless route safe: every call proves the document is where the
   caller claims before mutating anything.
5. **Forward delta loop:** for `i` in `fromFrame+1 .. playTo`:
   `delta_i = A_i · A_{i-1}⁻¹` (with `A_0 = I`), applied per object as a
   premultiplier (Rhino's `xform · point` convention; ON_Xform inverse —
   invertibility is guaranteed upstream by the motion parser's
   `scale > 0` rule, but a failed `Inverse()` is still a `track_invalid`
   failure, never a silent skip). Unpaced: no dwell, no per-frame redraw;
   one `Redraw()` after the loop. Per-frame wall-clock recorded.
6. **Probes:** after applying frame `i ∈ probeFrames`, record every animated
   object's observed tight bbox → response
   `probes: [{frame_index, objects: [{object_id, bbox_min, bbox_max}]}]`.
7. **In-loop drift gate at `playTo`:** per object, predicted envelope =
   bbox of the 8 `source_state` bbox corners transformed by `A_playTo`.
   Generic gate = **containment**: observed tight bbox ⊆ predicted envelope
   expanded by tolerance, plus reported (not gated) bbox-delta diagnostics
   (centroid offset, diagonal ratio) in the response. Exact/centroid
   equality is NOT gated generically — arbitrary Breps/curves do not fill
   their source bbox, so strict matching false-fails; exactness is asserted
   only by the proof fixtures (below), whose geometry is chosen to make it
   meaningful. Violation → failure `playback_drift_detected` with
   per-object evidence. The gate lives in the loop's route so Slice 4's
   capture aborts in-engine before wasting a run.

**Response (success):** `{documentPath, playedFrom, playedTo, frameCount,
objectCount, probes, drift: {tolerance, worstCentroidOffset,
worstDiagonalRatio}, timing: {totalMs, perFrameMs}}`. Per-object drift
diagnostics appear only in the `playback_drift_detected` failure payload —
the success path reports the worst-case scalars.

Registration follows the S2 pattern exactly: free-function handler in
`Rook::Handlers`, direct lambda registration next to the director siblings
(no member forwarder — verified S2 finding), vcxproj/filters entries.

## Decision 4: Orchestrator — `director_worker_play.py` (new module)

`async def play_take(arguments={"package_root", "from_frame"?, "play_to"?,
"probe_frames"?, "drift_tolerance"?, "reset"?}, ...)`:

1. Load + validate package (phase `compiled`; `track.json` hash vs status
   evidence; `track.derived_from` chain vs member map + prepared.3dm).
2. **Document handling — two modes.** Default (`reset: false`): verify the
   active document path is `prepared.3dm` and do NOT force a reopen — after
   a compile, the doc is untouched (compile only reads), and the native
   route's frame-`fromFrame` pose gate is the pristine proof; if the doc is
   mid-mutated from a crashed run, that gate fails with
   `worker_scene_not_pristine` and the operator resets. If the active doc
   is something else entirely, open `prepared.3dm` (genuine switch).
   With `reset: true` (Gate B / between-run reset): force a fresh reload —
   direct reopen, with the double-hop fallback (`scene.3dm` →
   `prepared.3dm`) when the native open reports `alreadyOpen`. This is the
   authoritative reset path.
3. Call `/director/worker-play` (single full-range call by default;
   `from_frame`/`play_to` pass through for chunked runs).
4. Record a run entry in `status.json` evidence (`play_runs`: append
   `{at_utc, played_from, played_to, probe_count, drift, timing}` — plays
   are repeatable evidence, not a phase).
5. Return the native response summary.

Shared-machinery note: the S2 open/pristine helpers in
`director_worker_prepare.py` are generalized into module-level functions
reused by compile and play (extract, don't duplicate — same rationale as
S2's canonical-JSON helper promotion; behavior-preserving, covered by the
existing S2 unit tests plus new ones).

**MCP tools:** `rhino_director_compile_take` and `rhino_director_worker_play`
— both classified MUTATE (both switch the active document; play mutates the
copy). Mirror `rhino_director_prepare_take` at every classification site;
pinned counts 439 → 441.

## Error taxonomy (S3)

Reused from S2 verbatim: `invalid_input`, `package_invalid`,
`package_hash_mismatch`, `document_not_saved`, `document_open_failed`,
`wrong_document`, `take_copy_not_pristine`.

New:

| code | meaning |
|------|---------|
| `compile_source_state_not_tight` | an animated object's `/director/object-states` bbox is not `tight_object` |
| `compile_track_mismatch` | resolved-motion animated ids ≠ member-map created ids |
| `compile_failed` | wrapped `DirectorCompileError` from reused compiler math (original code in detail) |
| `track_invalid` | track.json unreadable/malformed/inconsistent, bad frame range, non-invertible pose |
| `track_objects_missing` | animated ids not resolvable in the open document |
| `worker_scene_not_pristine` | pre-play pose gate failed (doc not at `fromFrame` pose) |
| `playback_drift_detected` | final-frame containment gate failed |
| `play_route_failed` | `/director/worker-play` envelope failure |

Native failure `data.reason` strings mirror the code names (`wrong_document`,
`track_invalid`, `track_objects_missing`, `worker_scene_not_pristine`,
`playback_drift_detected`).

## Proof gates

Unit level (fake native + tmp packages, S2 test pattern):
- Compiler: hash-chain failures, tight-bbox requirement, id-set cross-check,
  cap-free compile at >256 objects (the preview cap must demonstrably NOT
  apply), all-or-nothing writes, recompile-overwrite.
- **Matrix oracle:** an independent expected-pose implementation inside the
  test file (explicit translate/rotate/scale matrix construction — no
  imports from `director_motion`) that (a) predicts per-frame poses and
  envelopes for the proof fixture, and (b) PROVES the fixture distinguishes
  composition orders: the wrong-order delta (`A_{i-1}⁻¹ · A_i`, or
  postmultiplied application) must produce mid-frame envelopes that differ
  from the correct ones by far more than the gate tolerance. A proof that
  cannot fail is not a proof.
- Orchestrator: same guard matrix as S2 (open/alreadyOpen/pristine/hash),
  probe pass-through, run-evidence append.

Live gates (scratch doc, opt-in env `ROOK_S3_DOC_SWITCH=1`, save+cleanup
flow per the S2 lesson — never the evaporation trick):
- **Gate A — composition order:** fixture block containing an asymmetric
  1×2×3 box off-origin; motion = translate + rotate 45° about pivot
  `[5,0,0]` axis `[0,0,1]` + non-uniform scale `[1,1.5,2]` (full TRS is
  already in the motion vocabulary). package → prepare (writes
  prepared.3dm) → compile → play with probes at mid + final. Observed probe
  bboxes must match the oracle's predictions within tolerance — for THIS
  fixture, exact envelope equality is asserted (box geometry fills its
  bbox), which is what makes wrong composition order detectable.
- **Gate B — reset authority:** full play → reset (`reset: true`, exercising
  the direct-or-double-hop reload) → full play again → probe results
  identical within tolerance. This gate also empirically answers whether
  Rhino's scripted `_-Open` reloads a same-path document or no-ops — either
  behavior passes, because the double-hop fallback makes reset
  deterministic regardless.
- **Gate C — gates fire:** second play WITHOUT reset →
  `worker_scene_not_pristine` (live negative). Drift-gate negative is
  unit-level (tampered track).
- **Gate D — throughput measurement (not pass/fail):** synthetic ~300-member
  block; record unpaced ms/frame from the route's timing evidence — the
  S4 capture-budget input. The Pearson 886-member play is **blocked on the
  TL_Brep prepare fix** (chip `task_a06e920a`); noted as a dependency, not
  worked around.

## Explicitly Out of Scope

Capture and camera application (S4 wraps the gated loop); worker
lifecycle/TTL; inverse-restore reset optimization (permitted later, never
authoritative); preview-path (`/director/replay`) changes of any kind;
TL_Brep geometry support.

## Open Questions

1. Worker-play duration on the UI thread for large tracks: a full-range call
   dispatches once and holds the UI thread for the whole loop. Gate D
   measures it; if a Pearson-scale full play approaches the HTTP client
   timeout, the chunked `fromFrame`/`playTo` path (already stateless by
   design) is the mitigation — the orchestrator chooses chunk size. Not a
   blocker for S3's fixtures.
2. Whether S4 capture needs per-frame camera application to happen inside
   this same loop or as a wrapping phase — deferred to S4 design; the track
   already carries `camera_frames`.
