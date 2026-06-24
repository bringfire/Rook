# RookVisionDirector Replay Handler Decomposition (PR3) — Design

Date: 2026-06-24
Status: approved for implementation planning
Base: `origin/main` @ `1f0ce948` (PR #346 merge)
Branch: `feature/rookvisiondirector-replay-decomposition`

## Purpose

PR2 shipped native guarded display-only replay. `HandleDirectorReplay` works and is
covered by a 6/6 live gate, but it is the one Director handler that hand-rolls its entire
request envelope inline — ~625 lines mixing payload/JSON parsing, session-id validation,
slot reservation, track validation, option/cap parsing, per-frame pre-parse, the UI replay
loop, and response mapping in a single function.

PR3 is **behavior-preserving hardening**: decompose the worker phase onto the shared
request-envelope *pattern* (small typed parser/validator helpers + a typed instruction),
shrinking and clarifying `DirectorReplayHandler.cpp` while keeping replay semantics, error
codes, caps, restore behavior, cancellation behavior, and tests intact. This is **not** a
feature expansion and **not** an error-handling redesign.

This is the deferred refactor named in
`docs/superpowers/specs/2026-06-24-rookvisiondirector-animation-authoring-roadmap.md` (PR3).

## Scope

**In scope:** decompose the worker phase of `HandleDirectorReplay` into file-local typed
helpers in `src/RookNative/Handlers/DirectorReplayHandler.cpp`.

**Explicitly out of scope (non-goals):**
- Extracting the UI replay loop (the most recently hardened, riskiest part — three review
  rounds for restore-failure surfacing, viewport dirty-flag, and the non-idempotent
  `DirectorObjectPoseGuard::Restore` double-restore).
- Any new replay capability; any public-behavior change; any new error code.
- Any change across the native/managed/Python boundary.
- Any change to shared `DirectorFrame.{h,cpp}` (would touch frame-capture).
- Any change to `DirectorReplayHandler.h`, `RookNative.vcxproj`, or `.vcxproj.filters`
  (no new files; everything is file-local).
- Any change to `HandleDirectorReplayCancel`.

## Approach (selected: A — file-local helpers + typed instruction)

Considered and rejected:
- **B (extract the UI loop into a named function):** bigger, riskier diff over the
  hardened cancel/restore loop; cuts against keeping the loop recognizable. Could be a
  later, separate step if ever wanted.
- **C (promote parsers to a shared unit / new file):** the parsers are replay-specific
  (no reuse with frame-capture); forces a `.vcxproj` change or edits to shared
  `DirectorFrame.h`. Broader than warranted.

Approach A keeps everything file-local, leaves the UI loop in place, requires no header /
project / new-file changes, and keeps the source-analysis tests valid (they read the
`.cpp` text).

### Why not `ParseBodyAndDocSn` (source-verified behavior difference)

`ParseBodyAndDocSn` (`src/RookNative/Infrastructure/JsonHelpers.h`) is the dominant handler
shape, but it is **not** the right literal helper for replay because replay's envelope is
intentionally stricter:

| | `ParseBodyAndDocSn` (frame-capture) | replay envelope (today) |
|---|---|---|
| Payload size | no cap | **8 MiB cap → `payload_too_large`** |
| Bad JSON | non-throwing (`parse(.., nullptr, false)`) → silently `{}` | **throwing parse → `invalid_input` "Request body is not valid JSON"** |
| `documentSerialNumber` | extracted | ignored (replay uses the active doc) |

Adopting it literally would drop the payload cap and change the malformed-JSON error code —
a public-behavior change. PR3 therefore reuses the **request-envelope pattern** via a
replay-local `ParseReplayRequestBody`, **not** the literal `ParseBodyAndDocSn` function, and
does **not** introduce `documentSerialNumber` behavior into replay.

### Source-verified: move-only instruction is safe to dispatch

`CMainThreadDispatcher::Dispatch` is a template — `template<typename F> auto Dispatch(F&&)` —
that perfect-forwards the callable into `std::make_shared<std::decay_t<F>>(std::forward<F>(func))`
(`MainThreadDispatcher.h`). It **move-constructs** the closure and never copies it. Therefore
`ReplayInstruction` can be **strictly move-only** (deleted copy ctor/assign), captured by move
into the dispatch lambda, with zero copies of the frame payload — no `shared_ptr` wrapper
needed.

## Components (all file-local, anonymous namespace, in `DirectorReplayHandler.cpp`)

Nothing here is exposed in `DirectorReplayHandler.h`.

### `ReplayRequestError` (exception)

Holds a complete `nlohmann::json` error payload — not just `code`/`message` — because replay
errors already carry extra fields (`option`, `frame_index`, `object_id`).

```cpp
class ReplayRequestError : public std::exception {
public:
    explicit ReplayRequestError(nlohmann::json data) : m_data(std::move(data)) {}
    const nlohmann::json& data() const noexcept { return m_data; }
    const char* what() const noexcept override { return "ReplayRequestError"; }
private:
    nlohmann::json m_data;
};
```

`what()` returns a constant — callers use `data()`. Do **not** stringify the JSON into
`what()` (storage/lifetime noise for no benefit).

Two convenience throwers:

```cpp
[[noreturn]] static void ThrowReplayError(const std::string& code, const std::string& message);
[[noreturn]] static void ThrowReplayError(nlohmann::json data);   // multi-field cases stay clean
```

The existing file-local `SendCode` becomes unused once worker errors throw, and is removed.

### `ReplayInstruction` (move-only)

Owns the payload the UI lambda consumes:

```cpp
struct ReplayInstruction {
    std::vector<std::vector<FrameObjectTransform>> perFrameObjects;
    std::vector<FrameCamera>                       perFrameCameras;
    int    frameCount = 0;
    double dwellMs = 0.0, effectiveFps = 0.0, plannedDurationMs = 0.0;
    bool   restoreOnFinish = true;
    std::string sessionId;

    ReplayInstruction() = default;
    ReplayInstruction(ReplayInstruction&&) = default;
    ReplayInstruction& operator=(ReplayInstruction&&) = default;
    ReplayInstruction(const ReplayInstruction&) = delete;
    ReplayInstruction& operator=(const ReplayInstruction&) = delete;
};
```

Supporting value types (small, also file-local):
- `ReplayTrackInfo { int frameCount; std::set<std::string> animatedObjectIds; }`
- `ReplayOptions   { double effectiveFps, dwellMs, plannedDurationMs; bool restoreOnFinish; }`
- `ParsedReplayFrames { std::vector<std::vector<FrameObjectTransform>> perFrameObjects;
                        std::vector<FrameCamera> perFrameCameras; }`

### Worker-phase parsers (each throws `ReplayRequestError`)

- `nlohmann::json ParseReplayRequestBody(const httplib::Request& req)` — U1. 8 MiB cap →
  `payload_too_large`; **strict throwing** `nlohmann::json::parse` → `invalid_input`.
  Carries a comment: *intentionally not `ParseBodyAndDocSn`; replay enforces a stricter
  envelope and ignores `documentSerialNumber`.*
- `std::string ParseReplaySessionId(const nlohmann::json& body)` — U2. presence + `is_string`
  + `IsValidReplaySessionId` → `invalid_session_id`.
- `ReplayTrackInfo ParseReplayTrack(const nlohmann::json& body)` — **U4 in full**: track-is-object,
  `transform_semantics`, the `loop` rejection (**at its current position**, see below),
  `animated_object_ids` (shape, `<=256`, uniqueness), `frame_count` (shape, `>=1`, `<=3000`),
  `camera_frames`/`object_frames` existence + array + length-match + frame_index sequence.
  Returns `{frameCount, animatedObjectIds}`.
- `ReplayOptions ParseReplayOptions(const nlohmann::json& body, const nlohmann::json& track, int frameCount)` —
  U5: fps resolution (`body.fps` → `track.fps` → default `24`), `invalid_fps`, dwell cap
  (`frame_dwell_exceeds_cap`, >250ms), duration cap (`replay_duration_exceeds_cap`, >60000ms),
  `restore_on_finish` (default true). Kept separate so `ReplayInstruction` is not a parser
  dumping ground and cap logic is testable by source inspection.
- `ParsedReplayFrames ParseReplayFramePayloads(const nlohmann::json& track, const ReplayTrackInfo& info)` —
  U6: the typed per-frame **content** parser over the already-validated arrays. Per-frame
  camera/object parse, keeping the `DirectorFrameValidationError` → `track_invalid` remap
  **inside** this function; exact object-id set-equality vs `animatedObjectIds`; intra-frame
  duplicate check; sourceBbox drift check across frames.
- `ReplayInstruction BuildReplayInstructionFromBody(const nlohmann::json& body, std::string sessionId)` —
  orchestrates `ParseReplayTrack → ParseReplayOptions → ParseReplayFramePayloads` **in the
  original U4→U5→U6 order**, assembles and returns the move-only instruction. The name reads
  as worker-phase parsing/validation, not UI execution.

### Ordering decision (behavior-preservation): `loop` guard placement

The `loop` / `unsupported_replay_option` check stays at its **exact current position** inside
`ParseReplayTrack` — after `transform_semantics`, before `animated_object_ids`. Moving it into
`ParseReplayOptions` (called after track validation) would change error precedence: a request
with `loop:true` **and** a malformed track would then yield a track error instead of
`unsupported_replay_option`. Pinned to preserve current precedence over malformed later fields.

More generally, **each parser preserves the original *internal* check order**, not just the
inter-parser order — e.g. within `ParseReplayTrack`: array-nonempty → `object_count_exceeds_cap`
(>256) → per-element string check → uniqueness; within `ParseReplayOptions`: `invalid_fps` →
`frame_dwell_exceeds_cap` → `replay_duration_exceeds_cap`. Only the behavior-neutral grouping of
checks into functions changes, never their evaluation order (precedence is part of the contract).

## Orchestrator skeleton

```cpp
void HandleDirectorReplay(const httplib::Request& req, httplib::Response& res)
{
    try {
        const nlohmann::json body      = ParseReplayRequestBody(req);   // U1 cap + strict JSON
        std::string          sessionId = ParseReplaySessionId(body);    // U2 (before reserve)

        // U3 — reserve BEFORE building/validating the track. Deliberate, and may look out of
        // order to a future reviewer: it preserves today's precedence where a second
        // concurrent request gets replay_already_active rather than a track-validation error.
        if (!ReserveReplaySlot(sessionId))
            ThrowReplayError("replay_already_active", "A replay is already in progress");
        ReplaySlotReservation reservation;  reservation.held = true;    // releases on EVERY path

        // sessionId is moved here (its last use; ReserveReplaySlot above took it by const ref).
        ReplayInstruction instruction = BuildReplayInstructionFromBody(body, std::move(sessionId));  // U4+U5+U6

        auto future = CMainThreadDispatcher::Instance().Dispatch(
            [instruction = std::move(instruction)]() -> nlohmann::json {
                // Re-bind to the original local names so the hardened loop body is
                // semantically unchanged (no behavioral change to U7).
                auto& perFrameObjects = instruction.perFrameObjects;
                auto& perFrameCameras = instruction.perFrameCameras;
                const int    frameCount        = instruction.frameCount;
                const double dwellMs           = instruction.dwellMs;
                const double effectiveFps      = instruction.effectiveFps;
                const double plannedDurationMs = instruction.plannedDurationMs;
                const bool   restoreOnFinish   = instruction.restoreOnFinish;
                const std::string& sessionId   = instruction.sessionId;
                /* U7 (doc/view resolve, viewport guard, drain, UI-phase validation,
                   makeCancelled, restoreOrError, per-frame loop, terminal restore)
                   semantically unchanged. */
            });

        nlohmann::json result;                                          // U8 — reservation still held
        try { result = future.get(); }
        catch (const DirectorFrameValidationError& ex) { /* → ex.code (+ object_id) */ ... return; }
        catch (const std::exception& ex)               { /* → frame_apply_failed */     ... return; }
        if (result.contains("code")) { CRookServer::SendErrorData(res, result); return; }
        CRookServer::SendSuccess(res, result);
    }
    catch (const ReplayRequestError& ex) {
        CRookServer::SendErrorData(res, ex.data());
        return;
    }
}
```

Guarantees this encodes:
- **`reservation` visibly wraps both `BuildReplayInstructionFromBody` and `future.get()`** —
  declared right after a successful reserve, in scope through both; releases on normal return
  and on any `ReplayRequestError` unwind. (`ReserveReplaySlot` returning false does not
  reserve, so the throw on that path leaves nothing to release.)
- **U7 is semantically unchanged.** The lambda re-binds `instruction.*` to the original local
  names; the cancel/restore loop is not restructured. Formatting/rebinding may differ; behavior
  does not.

## Error-code preservation contract

This table is a **contract**. During implementation, copy the existing message strings
verbatim *before* moving code — do not rewrite them opportunistically.

| Code | Extra fields | PR3 thrower |
|---|---|---|
| `payload_too_large` | — | `ParseReplayRequestBody` |
| `invalid_input` | — | `ParseReplayRequestBody` (bad JSON); `ParseReplayTrack` (track-not-object, `animated_object_ids` shape/strings/uniqueness, `frame_count` shape/`>=1`) |
| `invalid_session_id` | — | `ParseReplaySessionId` |
| `replay_already_active` | — | orchestrator (reserve fail) |
| `unsupported_transform_semantics` | — | `ParseReplayTrack` |
| `unsupported_replay_option` | `option` | `ParseReplayTrack` (loop guard, original position) |
| `object_count_exceeds_cap` | — | `ParseReplayTrack` |
| `frame_count_exceeds_cap` | — | `ParseReplayTrack` |
| `track_invalid` | `frame_index`, `object_id`* | `ParseReplayTrack` (camera/object arrays, length mismatch, frame_index out of order); `ParseReplayFramePayloads` (camera/object parse remap, set-equality, dup, sourceBbox drift) |
| `invalid_fps` | — | `ParseReplayOptions` |
| `frame_dwell_exceeds_cap` | — | `ParseReplayOptions` |
| `replay_duration_exceeds_cap` | — | `ParseReplayOptions` |

\* `object_id` only where the original emits it.

**UI-phase codes are unchanged and out of decomposition scope** (remain in U7/U8):
`object_not_found`, `object_state_mismatch`, `frame_apply_failed`, `restore_failed`,
`unsupported_view`.

## Test & verification plan

**Existing behavior, MCP, and live tests stay green and unmodified. Source-structure tests
that currently assert worker-phase parsing lives inside `HandleDirectorReplay` will be updated
to assert the same intent at the new helper boundaries.**

### Behavior / MCP / live — green and unmodified
- `mcp_server/tests/test_director_replay.py` (unit + MCP dispatch).
- `mcp_server/tests/test_director_replay_live.py` (**6/6**).
- The PR2 review guards in `test_director_replay_native_source.py` — `surfaces_restore_failures_*`,
  `dirty_partial_state_includes_viewport`, `disengages_pose_guard_after_between_frame_restore`,
  plus `DispatchDrainSuspension` / cancel-worker-only / no-capture — stay green and unmodified
  (that content remains in U7/U8 inside the handler).
- Frame-capture source tests unaffected; the only failing test remains the pre-existing,
  unrelated `test_director_publish_video_native_route_is_thin_vision_proxy` (fails on `main`;
  replay branch does not touch `VisionHandler`).

### Source-structure tests re-pointed to the new boundaries (intent preserved)
Three tests in `test_director_replay_native_source.py` currently assert worker-phase content
lives inside `HandleDirectorReplay`; the decomposition moves it into the new parsers, so these
follow the architecture to its new boundary:
- `test_replay_loop_uses_single_guard_and_shared_primitives` — the `ParseCamera` /
  `ParseFrameObjectTransforms` usage assertion moves to `ParseReplayFramePayloads`. (The
  single-guard / `DispatchDrainSuspension` / loop-method assertions stay on the handler.)
- `test_replay_preparses_and_validates_every_frame_before_dispatch` — re-pointed to assert
  `BuildReplayInstructionFromBody` appears before `Dispatch(` in the handler, and that
  `BuildReplayInstructionFromBody` calls `ParseReplayTrack` → `ParseReplayOptions` →
  `ParseReplayFramePayloads` in order.
- `test_replay_remaps_shared_helper_errors_to_replay_codes` — the `DirectorFrameValidationError`
  catch + `track_invalid` remap assertion moves into `ParseReplayFramePayloads`.

### New source-structure tests (added to `test_director_replay_native_source.py`)
Structure, not implementation trivia; avoid asserting exact formatting:
1. `HandleDirectorReplay` builds a **move-only** `ReplayInstruction`
   (`ReplayInstruction(const ReplayInstruction&) = delete`) and dispatches it by move.
2. `ReplayRequestError` is defined, and there is **exactly one** `catch (const ReplayRequestError&`
   **scoped to `HandleDirectorReplay`** (so future cancel-route work cannot make the guard brittle).
3. `ParseReplayRequestBody` preserves the payload cap (`kMaxPayloadBytes` / `payload_too_large`)
   and a strict throwing parse, and `HandleDirectorReplay` does **not** reference
   `ParseBodyAndDocSn`.
4. the five named helpers exist: `ParseReplaySessionId`, `ParseReplayTrack`,
   `ParseReplayOptions`, `ParseReplayFramePayloads`, `BuildReplayInstructionFromBody`.
5. **reserve-before-build precedence:** within `HandleDirectorReplay`, `ReserveReplaySlot`
   appears before `BuildReplayInstructionFromBody`.
6. (existing, reasserted) U7 uses `DispatchDrainSuspension`; cancel is worker-thread-only;
   no capture/export APIs appear in replay; restore/double-restore guards remain intact.

### Build & live
- **Clean native rebuild** wiping `obj/` **and** `bin/` (LTCG `.iobj`/`.ipdb`) per the
  `docs/TROUBLESHOOTING.md` rule "Native handler behaves wrong / corrupt — but only on some
  builds." Confirm `Previous IPDB not found, fall back to full compilation`.
- Deploy; **6/6 live replay gate**.

### Success criteria (from the roadmap)
- Existing replay source/unit/MCP tests pass; live gate remains 6/6.
- Frame-capture behavior unchanged.
- `HandleDirectorReplay` is meaningfully smaller and follows the shared request-envelope
  pattern (expected: ~625-line function → ~60-line orchestrator + focused typed helpers; the
  UI loop untouched).
- No new replay capability; no Meshy work touched.

## Risks & mitigations
- **Check reordering** → `BuildReplayInstructionFromBody` calls parsers in the exact
  U4→U5→U6 order; the `loop` guard is pinned at its position inside `ParseReplayTrack`.
- **Message-string drift** → the error table is the contract; strings are copied verbatim.
- **Codegen fragility of a large TU** (the PR2 build-nondeterminism lesson) → mitigated *by*
  this PR (smaller function) and verified with a forced clean rebuild + 6/6 live gate.
