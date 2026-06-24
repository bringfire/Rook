# RookVisionDirector Replay Handler Decomposition (PR3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decompose `HandleDirectorReplay`'s ~625-line worker phase onto file-local typed parser helpers + a move-only `ReplayInstruction`, with zero public-behavior change.

**Architecture:** All new units are `static`/anonymous-namespace in `src/RookNative/Handlers/DirectorReplayHandler.cpp`. Worker-phase validation errors become a file-local `ReplayRequestError` exception carrying the exact error JSON, caught once in the handler. The UI replay loop (U7) and `HandleDirectorReplayCancel` are left semantically unchanged. No header, `.vcxproj`, new-file, Python, C#, or Meshy changes.

**Tech Stack:** C++17 (MSVC v143 `14.44.35207`), nlohmann/json, RhinoCommon SDK, httplib; Python 3.12 + pytest for source-analysis/live tests.

**Design spec:** `docs/superpowers/specs/2026-06-24-rookvisiondirector-replay-decomposition-design.md` (read it first — it holds the rationale, the error-code contract table, and the source-verified constraints).

## Global Constraints

- **Worktree root:** `C:\Users\aryan\source\repos\Rook\.worktrees\rookvisiondirector-replay-decomposition` (branch `feature/rookvisiondirector-replay-decomposition`, off `origin/main` `1f0ce948`). All file paths below are relative to this root. Run all commands from here.
- **Python for tests:** the worktree has no venv; use the main repo venv:
  `C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe`. Source-analysis tests import only `pathlib` and resolve `REPO_ROOT` from the test file's location, so they read **this worktree's** `.cpp`.
- **Behavior preservation is the contract.** Copy existing message strings **verbatim** before moving code; never rewrite them. Preserve check-evaluation order both across and within parsers (precedence is part of the contract — see the spec's error table).
- **Error-conversion rule (apply mechanically when moving a worker-phase error out of `HandleDirectorReplay`):**
  - `SendCode(res, "<code>", "<msg>"); return;` → `ThrowReplayError("<code>", "<msg>");`
  - A multi-field block `nlohmann::json d; d["code"]=...; d["message"]=...; d[<extra>]=...; CRookServer::SendErrorData(res, d); return;` → keep the `d` construction **identical**, replace the send+return with `throw ReplayRequestError(std::move(d));`.
- **Do NOT touch:** `DirectorReplayHandler.h`, `RookNative.vcxproj(.filters)`, `DirectorFrame.{h,cpp}`, `HandleDirectorReplayCancel`, the U7 dispatch-lambda loop body, any Python/C#/Meshy file.
- **Helper definition order:** define every new `static` helper/struct in the anonymous namespace **above** `HandleDirectorReplay`, and define each parser before the function that calls it (so the source tests' `_extract_function` finds the definition first).
- **No new error codes, no new capability.** UI-phase codes (`object_not_found`, `object_state_mismatch`, `frame_apply_failed`, `restore_failed`, `unsupported_view`) stay in U7/U8 unchanged.
- **Intermediate builds may be incremental (compile-check only). The final behavior proof (Task 6) requires a fully clean rebuild** wiping `obj/` AND `bin/` (LTCG), per `docs/TROUBLESHOOTING.md` "Native handler behaves wrong / corrupt — but only on some builds."

### Standard per-task verification commands

- Source tests (fast, no Rhino):
  ```
  & "C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe" -m pytest mcp_server\tests\test_director_replay_native_source.py -q
  ```
- Compile-check (incremental, no Rhino, from worktree root):
  ```
  & ".\build_native.ps1" -Configuration Release
  ```
  Expected tail: `Build succeeded:`.

## File Structure

- **Modify:** `src/RookNative/Handlers/DirectorReplayHandler.cpp` — the only production file. Gains a file-local exception, a move-only instruction struct + 3 small value structs, and 6 parser/orchestration helpers; `HandleDirectorReplay` becomes a thin orchestrator; the UI loop and cancel handler are untouched; `SendCode` is removed.
- **Modify (tests):** `mcp_server/tests/test_director_replay_native_source.py` — add new structure tests; re-point 3 existing tests to the new helper boundaries.
- **Unchanged behavior nets:** `mcp_server/tests/test_director_replay.py`, `mcp_server/tests/test_director_replay_live.py`.

---

### Task 1: Foundation — `ReplayRequestError`, envelope + session parsers, try/catch shell

**Files:**
- Modify: `src/RookNative/Handlers/DirectorReplayHandler.cpp`
- Test: `mcp_server/tests/test_director_replay_native_source.py`

**Interfaces:**
- Produces:
  - `class ReplayRequestError : public std::exception` with `const nlohmann::json& data() const noexcept`.
  - `[[noreturn]] static void ThrowReplayError(const std::string& code, const std::string& message);`
  - `[[noreturn]] static void ThrowReplayError(nlohmann::json data);`
  - `static nlohmann::json ParseReplayRequestBody(const httplib::Request& req);` (U1: 8 MiB cap → `payload_too_large`; strict throwing parse → `invalid_input`)
  - `static std::string ParseReplaySessionId(const nlohmann::json& body);` (U2 → `invalid_session_id`)

- [ ] **Step 1: Write the new structure tests** (append to `test_director_replay_native_source.py`):

```python
def test_replay_uses_replay_request_error_with_single_handler_catch():
    src = _read(REPLAY_CPP)
    assert "class ReplayRequestError" in src
    handler = _extract_function(src, "HandleDirectorReplay")
    assert handler.count("catch (const ReplayRequestError&") == 1


def test_replay_request_body_parser_preserves_strict_envelope():
    src = _read(REPLAY_CPP)
    body_parser = _extract_function(src, "ParseReplayRequestBody")
    assert "kMaxPayloadBytes" in body_parser and "payload_too_large" in body_parser
    assert "nlohmann::json::parse(" in body_parser          # strict throwing parse
    assert "ParseBodyAndDocSn" not in src                   # replay keeps its stricter envelope


def test_replay_session_id_parser_exists():
    src = _read(REPLAY_CPP)
    assert "ParseReplaySessionId(" in src
    parser = _extract_function(src, "ParseReplaySessionId")
    assert "IsValidReplaySessionId" in parser and "invalid_session_id" in parser
```

- [ ] **Step 2: Run the new tests — verify they FAIL**

Run:
```
& "C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe" -m pytest mcp_server\tests\test_director_replay_native_source.py -q -k "replay_request_error or request_body_parser or session_id_parser"
```
Expected: 3 FAIL (`ReplayRequestError`/`ParseReplayRequestBody`/`ParseReplaySessionId` not defined).

- [ ] **Step 3: Add `ReplayRequestError` + `ThrowReplayError` to the anonymous namespace**

In the `namespace {` block (after `SendCode`, before its closing `}`), add:

```cpp
// Worker-phase validation failure carrying the EXACT error payload (code, message, and any
// extra fields like option/frame_index/object_id). Private to this .cpp; caught once in
// HandleDirectorReplay. Callers use data(); what() is a constant on purpose.
class ReplayRequestError : public std::exception
{
public:
    explicit ReplayRequestError(nlohmann::json data) : m_data(std::move(data)) {}
    const nlohmann::json& data() const noexcept { return m_data; }
    const char* what() const noexcept override { return "ReplayRequestError"; }
private:
    nlohmann::json m_data;
};

[[noreturn]] static void ThrowReplayError(nlohmann::json data)
{
    throw ReplayRequestError(std::move(data));
}

[[noreturn]] static void ThrowReplayError(const std::string& code, const std::string& message)
{
    nlohmann::json d;
    d["code"] = code;
    d["message"] = message;
    throw ReplayRequestError(std::move(d));
}
```

- [ ] **Step 4: Add `ParseReplayRequestBody` + `ParseReplaySessionId`** (anonymous namespace, after the throwers):

```cpp
// U1 — request envelope. INTENTIONALLY NOT ParseBodyAndDocSn: replay enforces an 8 MiB
// payload cap and a strict (throwing) JSON parse, and ignores documentSerialNumber.
static nlohmann::json ParseReplayRequestBody(const httplib::Request& req)
{
    static constexpr size_t kMaxPayloadBytes = 8u * 1024u * 1024u;  // 8 MiB
    if (req.body.size() > kMaxPayloadBytes)
        ThrowReplayError("payload_too_large", "Request body exceeds 8 MiB limit");

    try { return nlohmann::json::parse(req.body); }
    catch (...) { ThrowReplayError("invalid_input", "Request body is not valid JSON"); }
}

// U2 — session id: presence + is_string + content validation.
static std::string ParseReplaySessionId(const nlohmann::json& body)
{
    if (!body.contains("replay_session_id") || !body["replay_session_id"].is_string())
        ThrowReplayError("invalid_session_id",
                         "replay_session_id must be a 1..128 char [A-Za-z0-9._-] string");
    std::string sessionId = body["replay_session_id"].get<std::string>();
    if (!IsValidReplaySessionId(sessionId))
        ThrowReplayError("invalid_session_id",
                         "replay_session_id must be a 1..128 char [A-Za-z0-9._-] string");
    return sessionId;
}
```
Note: `ParseReplayRequestBody`'s `try` returns on success; the `catch` calls a `[[noreturn]]` thrower, so all control paths are covered (no missing-return warning).

- [ ] **Step 5: Rewrite the top of `HandleDirectorReplay` + add the outer try/catch**

In `HandleDirectorReplay`, replace the inline payload-cap block (`// 0. Payload size cap`), the JSON-parse block (`// 1. Parse JSON`), and the session-id block (`// 2. Session id`) with calls to the new helpers, and wrap the **entire** worker phase in a single try/catch. The current body (reservation, track validation, options, per-frame pre-parse, Dispatch, future.get, response) stays **inline and unchanged** inside the `try`:

```cpp
void HandleDirectorReplay(const httplib::Request& req, httplib::Response& res)
{
    try
    {
        const nlohmann::json body      = ParseReplayRequestBody(req);   // U1
        std::string          sessionId = ParseReplaySessionId(body);    // U2

        // ---- existing body from "// 3. Reserve replay slot" through the end of the
        //      response mapping stays here, UNCHANGED, for now ----
        if (!ReserveReplaySlot(sessionId)) { SendCode(res, "replay_already_active", "A replay is already in progress"); return; }
        ReplaySlotReservation reservation; reservation.held = true;
        /* ... track validation (U4), options (U5), per-frame pre-parse (U6),
               Dispatch lambda (U7), future.get + response (U8) — all verbatim ... */
    }
    catch (const ReplayRequestError& ex)
    {
        CRookServer::SendErrorData(res, ex.data());
        return;
    }
}
```
The inline `SendCode(...); return;` paths inside the `try` are unaffected (they don't throw). Only U1/U2 now throw `ReplayRequestError`. Keep `body` and `sessionId` as the names the rest of the body already uses.

- [ ] **Step 6: Run source tests + compile-check — verify PASS**

Run the source suite:
```
& "C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe" -m pytest mcp_server\tests\test_director_replay_native_source.py -q
```
Expected: all PASS (the 3 new + every existing test; U4–U6 still inline, so the 3 to-be-re-pointed tests still pass here).

Compile-check:
```
& ".\build_native.ps1" -Configuration Release
```
Expected tail: `Build succeeded:`.

- [ ] **Step 7: Commit**

```
git add src/RookNative/Handlers/DirectorReplayHandler.cpp mcp_server/tests/test_director_replay_native_source.py
git commit -m "refactor(director): extract replay request-body + session-id parsers; ReplayRequestError shell"
```

---

### Task 2: Orchestrator rewrite — `ReplayInstruction` + `BuildReplayInstructionFromBody` + final handler

This is the core task: move U4+U5+U6 verbatim into `BuildReplayInstructionFromBody` (converting their errors via the conversion rule), introduce the move-only `ReplayInstruction`, and rewrite the handler to its final orchestrator shape (move-capture + re-bind preamble), removing `SendCode` and converting `replay_already_active` to a throw. U7's loop body is left semantically unchanged.

**Files:**
- Modify: `src/RookNative/Handlers/DirectorReplayHandler.cpp`
- Test: `mcp_server/tests/test_director_replay_native_source.py`

**Interfaces:**
- Consumes (Task 1): `ParseReplayRequestBody`, `ParseReplaySessionId`, `ThrowReplayError`, `ReplayRequestError`.
- Produces:
  - move-only `struct ReplayInstruction { std::vector<std::vector<FrameObjectTransform>> perFrameObjects; std::vector<FrameCamera> perFrameCameras; int frameCount; double dwellMs, effectiveFps, plannedDurationMs; bool restoreOnFinish; std::string sessionId; }` (copy ctor/assign deleted).
  - `static ReplayInstruction BuildReplayInstructionFromBody(const nlohmann::json& body, std::string sessionId);`

- [ ] **Step 1: Re-point the 3 monolith-structure tests + add new ones** (edit `test_director_replay_native_source.py`)

Replace the body of `test_replay_loop_uses_single_guard_and_shared_primitives` with:
```python
def test_replay_loop_uses_single_guard_and_shared_primitives():
    src = _read(REPLAY_CPP)
    replay = _extract_function(src, "HandleDirectorReplay")
    assert "DispatchDrainSuspension" in replay
    assert replay.count("DispatchDrainSuspension ") == 1     # ONE guard for the whole loop
    assert "DirectorObjectPoseGuard" in replay
    assert "DirectorViewportGuard" in replay
    assert replay.count("DirectorViewportGuard ") == 1
    assert "SetCameraFromFrame(" in replay
    assert "Apply()" in replay and "Restore(" in replay and "Disarm()" in replay
    # Shared pure parsers now live in the worker-phase builder, not inline in the handler.
    build = _extract_function(src, "BuildReplayInstructionFromBody")
    assert "ParseFrameObjectTransforms(" in build
    assert "ParseCamera(" in build
```

Replace the body of `test_replay_remaps_shared_helper_errors_to_replay_codes` with:
```python
def test_replay_remaps_shared_helper_errors_to_replay_codes():
    src = _read(REPLAY_CPP)
    build = _extract_function(src, "BuildReplayInstructionFromBody")
    assert "catch (const DirectorFrameValidationError" in build or \
           "catch (DirectorFrameValidationError" in build
    assert "track_invalid" in build            # worker-phase parse failures
    assert "affectedObjectIds" in build        # object_id carried from the helper
    handler = _extract_function(src, "HandleDirectorReplay")
    assert "object_not_found" in handler       # UI-phase doc validation stays in the handler
```

Replace the body of `test_replay_preparses_and_validates_every_frame_before_dispatch` with:
```python
def test_replay_preparses_and_validates_every_frame_before_dispatch():
    src = _read(REPLAY_CPP)
    handler = _extract_function(src, "HandleDirectorReplay")
    assert "BuildReplayInstructionFromBody" in handler
    assert handler.index("BuildReplayInstructionFromBody") < handler.index("Dispatch(")
    build = _extract_function(src, "BuildReplayInstructionFromBody")
    assert "animated_object_ids" in build      # exact-set check lives in the builder
    assert "perFrameObjects" in build and "perFrameCameras" in build
```

Append new structure tests:
```python
def test_replay_instruction_is_move_only_and_dispatched_by_move():
    src = _read(REPLAY_CPP)
    assert "struct ReplayInstruction" in src
    assert "ReplayInstruction(const ReplayInstruction&) = delete" in src
    handler = _extract_function(src, "HandleDirectorReplay")
    assert "ReplayInstruction instruction = BuildReplayInstructionFromBody(" in handler
    assert "instruction = std::move(instruction)" in handler   # captured by move into the lambda


def test_replay_reserves_slot_before_building_instruction():
    handler = _extract_function(_read(REPLAY_CPP), "HandleDirectorReplay")
    assert handler.index("ReserveReplaySlot(") < handler.index("BuildReplayInstructionFromBody(")


def test_replay_named_worker_phase_helpers_exist():
    src = _read(REPLAY_CPP)
    for fn in ["ParseReplayRequestBody", "ParseReplaySessionId", "BuildReplayInstructionFromBody"]:
        assert f"{fn}(" in src, f"missing helper {fn}"
```

- [ ] **Step 2: Run these tests — verify they FAIL**

Run:
```
& "C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe" -m pytest mcp_server\tests\test_director_replay_native_source.py -q -k "single_guard or remaps or preparses or instruction_is_move_only or reserves_slot or named_worker_phase"
```
Expected: FAIL (`BuildReplayInstructionFromBody` / `ReplayInstruction` not defined; `instruction = std::move(instruction)` absent).

- [ ] **Step 3: Add `ReplayInstruction`** (anonymous namespace, above `HandleDirectorReplay`):

```cpp
// Move-only: owns the (potentially large) per-frame payload the UI lambda consumes.
// Deleted copy ctor prevents accidental copies; CMainThreadDispatcher::Dispatch is a
// template that move-constructs the closure (make_shared<decay_t<F>>), so capturing this
// by move into the dispatch lambda copies no frame data.
struct ReplayInstruction
{
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

- [ ] **Step 4: Create `BuildReplayInstructionFromBody`** (anonymous namespace, above `HandleDirectorReplay`)

**Move** the three inline blocks currently in `HandleDirectorReplay` — `// 4. Extract + validate top-level track structure`, `// 5. Compute effective_fps + dwell_ms`, and `// 6. Worker-phase per-frame pre-parse` (everything from `const auto& track = body["track"];` setup through the `perFrameObjects.push_back(...)` loop) — into this function body, **verbatim**, then **apply the error-conversion rule** to every `SendCode`/`SendErrorData` error in the moved code, and assemble the instruction:

```cpp
static ReplayInstruction BuildReplayInstructionFromBody(const nlohmann::json& body, std::string sessionId)
{
    // ---- moved U4 (track envelope, incl. the loop guard at its original position),
    //      U5 (fps/dwell/duration caps + restore_on_finish),
    //      U6 (per-frame pre-parse: ParseCamera / ParseFrameObjectTransforms with the
    //          DirectorFrameValidationError -> track_invalid remap, set-equality, dup,
    //          sourceBbox drift) ----
    //
    // Conversion rule applied verbatim:
    //   SendCode(res, code, msg); return;                  ->  ThrowReplayError(code, msg);
    //   nlohmann::json d; ...; SendErrorData(res, d); return;  ->  throw ReplayRequestError(std::move(d));
    // Message strings and field names copied EXACTLY. Internal check order unchanged.

    /* <moved + converted U4 → produces: const auto& track, int frameCount,
       std::set<std::string> animatedObjectIds> */
    /* <moved + converted U5 → produces: double effectiveFps, dwellMs, plannedDurationMs;
       bool restoreOnFinish> */
    /* <moved + converted U6 → produces: std::vector<FrameCamera> perFrameCameras,
       std::vector<std::vector<FrameObjectTransform>> perFrameObjects> */

    ReplayInstruction instruction;
    instruction.perFrameObjects   = std::move(perFrameObjects);
    instruction.perFrameCameras   = std::move(perFrameCameras);
    instruction.frameCount        = frameCount;
    instruction.dwellMs           = dwellMs;
    instruction.effectiveFps      = effectiveFps;
    instruction.plannedDurationMs = plannedDurationMs;
    instruction.restoreOnFinish   = restoreOnFinish;
    instruction.sessionId         = std::move(sessionId);
    return instruction;
}
```
The moved local names (`track`, `frameCount`, `animatedObjectIds`, `effectiveFps`, `dwellMs`, `plannedDurationMs`, `restoreOnFinish`, `perFrameObjects`, `perFrameCameras`, `sourceBoxRef`, `kBboxTolerance`) are exactly those already used by the inline code — keep them. The U4/U5/U6 code accesses `body[...]` and `track[...]`; `body` is the function parameter, `track` is `body["track"]` as today.

- [ ] **Step 5: Rewrite the handler body to the final orchestrator**

Replace everything in the `try` after `sessionId` (the old inline reservation + U4 + U5 + U6 + Dispatch capture list + future.get) with:

```cpp
        if (!ReserveReplaySlot(sessionId))
            ThrowReplayError("replay_already_active", "A replay is already in progress");
        ReplaySlotReservation reservation;  reservation.held = true;   // released on every path below

        // sessionId is moved here (its last use; ReserveReplaySlot above took it by const ref).
        ReplayInstruction instruction = BuildReplayInstructionFromBody(body, std::move(sessionId));  // U4+U5+U6

        auto future = CMainThreadDispatcher::Instance().Dispatch(
            [instruction = std::move(instruction)]() -> nlohmann::json
        {
            // Re-bind to the original local names so the hardened loop body is semantically
            // unchanged (no behavioral change to U7).
            const auto& perFrameObjects = instruction.perFrameObjects;
            const auto& perFrameCameras = instruction.perFrameCameras;
            const int          frameCount        = instruction.frameCount;
            const double       dwellMs           = instruction.dwellMs;
            const double       effectiveFps      = instruction.effectiveFps;
            const double       plannedDurationMs = instruction.plannedDurationMs;
            const bool         restoreOnFinish   = instruction.restoreOnFinish;
            const std::string& sessionId         = instruction.sessionId;

            /* ---- U7 body VERBATIM: "Resolve document + view" through "return result;"
                    (viewport guard, DispatchDrainSuspension, UI-phase validation,
                    makeCancelled, restoreOrError, per-frame loop, terminal restore) ---- */
        });

        // U8 — block on the worker, map outcome. reservation still held across future.get().
        nlohmann::json result;
        try { result = future.get(); }
        catch (const DirectorFrameValidationError& ex)
        {
            nlohmann::json d; d["code"] = ex.code; d["message"] = ex.what();
            if (!ex.affectedObjectIds.empty()) d["object_id"] = ex.affectedObjectIds[0];
            CRookServer::SendErrorData(res, d); return;
        }
        catch (const std::exception& ex)
        {
            nlohmann::json d; d["code"] = "frame_apply_failed"; d["message"] = ex.what();
            CRookServer::SendErrorData(res, d); return;
        }
        if (result.contains("code")) { CRookServer::SendErrorData(res, result); return; }
        CRookServer::SendSuccess(res, result);
```
The U7 lambda body is the existing code; only the **capture list** changed (`[instruction = std::move(instruction)]`) and the **re-bind preamble** was added. Do not edit the loop logic. The original lambda was non-`mutable` (captures const); `instruction` is likewise const inside the lambda, so the `const auto&` / `const ...` re-binds match the original const access.

- [ ] **Step 6: Remove the now-unused `SendCode`**

Delete the `static void SendCode(...)` definition in the anonymous namespace (all worker-phase errors now throw; `HandleDirectorReplayCancel` builds its JSON inline and never used `SendCode`). If the compiler still reports it referenced, leave it; otherwise remove it.

- [ ] **Step 7: Run source tests + compile-check — verify PASS**

```
& "C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe" -m pytest mcp_server\tests\test_director_replay_native_source.py -q
& ".\build_native.ps1" -Configuration Release
```
Expected: all source tests PASS; `Build succeeded:`.

- [ ] **Step 8: Commit**

```
git add src/RookNative/Handlers/DirectorReplayHandler.cpp mcp_server/tests/test_director_replay_native_source.py
git commit -m "refactor(director): move replay worker phase into BuildReplayInstructionFromBody; thin orchestrator + move-only instruction"
```

---

### Task 3: Sub-extract `ParseReplayTrack` (+ `ReplayTrackInfo`)

Pure internal refactor of `BuildReplayInstructionFromBody`; the handler is untouched.

**Files:** Modify `src/RookNative/Handlers/DirectorReplayHandler.cpp`; Test `mcp_server/tests/test_director_replay_native_source.py`.

**Interfaces:**
- Produces: `struct ReplayTrackInfo { int frameCount; std::set<std::string> animatedObjectIds; };`
  and `static ReplayTrackInfo ParseReplayTrack(const nlohmann::json& body);` — owns the full U4 envelope (track-is-object, `transform_semantics`, the `loop` guard at its current position, `animated_object_ids` shape/`<=256`/uniqueness, `frame_count` shape/`>=1`/`<=3000`, `camera_frames`/`object_frames` existence + array + length-match + frame_index sequence). Internal check order preserved.
- Consumes: `BuildReplayInstructionFromBody` now calls it first.

- [ ] **Step 1: Add the structure test**
```python
def test_replay_track_parser_owns_envelope():
    src = _read(REPLAY_CPP)
    track = _extract_function(src, "ParseReplayTrack")
    for tok in ["transform_semantics", "unsupported_transform_semantics",
                "unsupported_replay_option", "animated_object_ids",
                "object_count_exceeds_cap", "frame_count", "frame_count_exceeds_cap",
                "camera_frames", "object_frames", "track_invalid"]:
        assert tok in track, f"ParseReplayTrack missing {tok}"
    build = _extract_function(src, "BuildReplayInstructionFromBody")
    assert "ParseReplayTrack(" in build
```

- [ ] **Step 2: Run it — verify FAIL**
```
& "C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe" -m pytest mcp_server\tests\test_director_replay_native_source.py -q -k track_parser_owns_envelope
```
Expected: FAIL (`ParseReplayTrack` not defined).

- [ ] **Step 3: Extract `ParseReplayTrack`**

Add `struct ReplayTrackInfo { int frameCount = 0; std::set<std::string> animatedObjectIds; };` above the parsers. Move the U4 block out of `BuildReplayInstructionFromBody` into:
```cpp
static ReplayTrackInfo ParseReplayTrack(const nlohmann::json& body)
{
    /* <moved U4 block, verbatim incl. loop guard at its original position; errors already
       use ThrowReplayError / throw ReplayRequestError from Task 2> */
    ReplayTrackInfo info;
    info.frameCount        = frameCount;
    info.animatedObjectIds = std::move(animatedObjectIds);
    return info;
}
```
In `BuildReplayInstructionFromBody`, replace the moved block with `ReplayTrackInfo track = ParseReplayTrack(body);` and update later references: `frameCount` → `track.frameCount`, the `animatedObjectIds` set used by U6 → `track.animatedObjectIds`, and `const auto& track = body["track"];` (the raw JSON, still needed by U5/U6) is re-derived locally as `const nlohmann::json& trackJson = body["track"];` to avoid the name clash with `ReplayTrackInfo track`. Update U5/U6's `track[...]` accesses to `trackJson[...]`.

- [ ] **Step 4: Run source tests + compile-check — verify PASS**
```
& "C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe" -m pytest mcp_server\tests\test_director_replay_native_source.py -q
& ".\build_native.ps1" -Configuration Release
```
Expected: all PASS; `Build succeeded:`.

- [ ] **Step 5: Commit**
```
git add src/RookNative/Handlers/DirectorReplayHandler.cpp mcp_server/tests/test_director_replay_native_source.py
git commit -m "refactor(director): extract ParseReplayTrack (U4 envelope)"
```

---

### Task 4: Sub-extract `ParseReplayOptions` (+ `ReplayOptions`)

**Files:** Modify `src/RookNative/Handlers/DirectorReplayHandler.cpp`; Test `mcp_server/tests/test_director_replay_native_source.py`.

**Interfaces:**
- Produces: `struct ReplayOptions { double effectiveFps; double dwellMs; double plannedDurationMs; bool restoreOnFinish; };`
  and `static ReplayOptions ParseReplayOptions(const nlohmann::json& body, int frameCount);` — U5: fps resolution (`body.fps` → `body["track"].fps` → default 24) → `invalid_fps`; dwell cap → `frame_dwell_exceeds_cap`; duration cap → `replay_duration_exceeds_cap`; `restore_on_finish` default true. Internal order: invalid_fps → dwell → duration.

- [ ] **Step 1: Add the structure test**
```python
def test_replay_options_parser_owns_caps():
    src = _read(REPLAY_CPP)
    opts = _extract_function(src, "ParseReplayOptions")
    for tok in ["invalid_fps", "frame_dwell_exceeds_cap", "replay_duration_exceeds_cap",
                "restore_on_finish"]:
        assert tok in opts, f"ParseReplayOptions missing {tok}"
    assert opts.index("invalid_fps") < opts.index("frame_dwell_exceeds_cap") < opts.index("replay_duration_exceeds_cap")
    build = _extract_function(src, "BuildReplayInstructionFromBody")
    assert "ParseReplayOptions(" in build
```

- [ ] **Step 2: Run it — verify FAIL**
```
& "C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe" -m pytest mcp_server\tests\test_director_replay_native_source.py -q -k options_parser_owns_caps
```
Expected: FAIL (`ParseReplayOptions` not defined).

- [ ] **Step 3: Extract `ParseReplayOptions`**

Add `struct ReplayOptions { double effectiveFps = 0, dwellMs = 0, plannedDurationMs = 0; bool restoreOnFinish = true; };`. Move the U5 block into:
```cpp
static ReplayOptions ParseReplayOptions(const nlohmann::json& body, int frameCount)
{
    const nlohmann::json& track = body["track"];   // already validated by ParseReplayTrack
    /* <moved U5 block, verbatim; throws already in place> producing effectiveFps, dwellMs,
       plannedDurationMs, restoreOnFinish */
    ReplayOptions opts;
    opts.effectiveFps      = effectiveFps;
    opts.dwellMs           = dwellMs;
    opts.plannedDurationMs = plannedDurationMs;
    opts.restoreOnFinish   = restoreOnFinish;
    return opts;
}
```
In `BuildReplayInstructionFromBody`, replace the moved block with `ReplayOptions opts = ParseReplayOptions(body, track.frameCount);` and update later references (`effectiveFps` → `opts.effectiveFps`, etc.) in the instruction assembly.

- [ ] **Step 4: Run source tests + compile-check — verify PASS**
```
& "C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe" -m pytest mcp_server\tests\test_director_replay_native_source.py -q
& ".\build_native.ps1" -Configuration Release
```
Expected: all PASS; `Build succeeded:`.

- [ ] **Step 5: Commit**
```
git add src/RookNative/Handlers/DirectorReplayHandler.cpp mcp_server/tests/test_director_replay_native_source.py
git commit -m "refactor(director): extract ParseReplayOptions (U5 fps/dwell/duration caps)"
```

---

### Task 5: Sub-extract `ParseReplayFramePayloads` (+ `ParsedReplayFrames`) and finalize re-pointed tests

**Files:** Modify `src/RookNative/Handlers/DirectorReplayHandler.cpp`; Test `mcp_server/tests/test_director_replay_native_source.py`.

**Interfaces:**
- Produces: `struct ParsedReplayFrames { std::vector<std::vector<FrameObjectTransform>> perFrameObjects; std::vector<FrameCamera> perFrameCameras; };`
  and `static ParsedReplayFrames ParseReplayFramePayloads(const nlohmann::json& body, const ReplayTrackInfo& info);` — U6: per-frame camera/object parse with the `DirectorFrameValidationError`→`track_invalid` remap, exact object-id set-equality vs `info.animatedObjectIds`, intra-frame dup, sourceBbox drift.

- [ ] **Step 1: Finalize the re-pointed tests to the frame parser**

Update `test_replay_loop_uses_single_guard_and_shared_primitives` — change the last two asserts from `build` to the frame parser:
```python
    frames = _extract_function(src, "ParseReplayFramePayloads")
    assert "ParseFrameObjectTransforms(" in frames
    assert "ParseCamera(" in frames
```
Update `test_replay_remaps_shared_helper_errors_to_replay_codes` — point the remap asserts at the frame parser:
```python
    frames = _extract_function(src, "ParseReplayFramePayloads")
    assert "catch (const DirectorFrameValidationError" in frames or \
           "catch (DirectorFrameValidationError" in frames
    assert "track_invalid" in frames
    assert "affectedObjectIds" in frames
    handler = _extract_function(src, "HandleDirectorReplay")
    assert "object_not_found" in handler
```
Update `test_replay_preparses_and_validates_every_frame_before_dispatch` — finalize the build-order:
```python
    build = _extract_function(src, "BuildReplayInstructionFromBody")
    assert build.index("ParseReplayTrack") < build.index("ParseReplayOptions") < build.index("ParseReplayFramePayloads")
```
Add a frame-parser test:
```python
def test_replay_frame_parser_owns_per_frame_content():
    frames = _extract_function(_read(REPLAY_CPP), "ParseReplayFramePayloads")
    assert "ParseCamera(" in frames and "ParseFrameObjectTransforms(" in frames
    assert "track_invalid" in frames
    assert "animated_object_ids" in frames or "frameIds" in frames   # exact-set equality check
```

- [ ] **Step 2: Run the affected tests — verify FAIL**
```
& "C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe" -m pytest mcp_server\tests\test_director_replay_native_source.py -q -k "single_guard or remaps or preparses or frame_parser_owns"
```
Expected: FAIL (`ParseReplayFramePayloads` not defined; build-order assert references it).

- [ ] **Step 3: Extract `ParseReplayFramePayloads`**

Add `struct ParsedReplayFrames { std::vector<std::vector<FrameObjectTransform>> perFrameObjects; std::vector<FrameCamera> perFrameCameras; };`. Move the U6 block into:
```cpp
static ParsedReplayFrames ParseReplayFramePayloads(const nlohmann::json& body, const ReplayTrackInfo& info)
{
    const nlohmann::json& track = body["track"];
    const auto& cameraFramesJson = track["camera_frames"];   // validated by ParseReplayTrack
    const auto& objectFramesJson = track["object_frames"];
    const int frameCount = info.frameCount;
    const std::set<std::string>& animatedObjectIds = info.animatedObjectIds;
    /* <moved U6 per-frame loop, verbatim; the set-equality check compares against
       animatedObjectIds; throws already in place> producing perFrameCameras + perFrameObjects */
    ParsedReplayFrames out;
    out.perFrameObjects = std::move(perFrameObjects);
    out.perFrameCameras = std::move(perFrameCameras);
    return out;
}
```
In `BuildReplayInstructionFromBody`, replace the moved block with `ParsedReplayFrames frames = ParseReplayFramePayloads(body, track);` and assign `instruction.perFrameObjects = std::move(frames.perFrameObjects); instruction.perFrameCameras = std::move(frames.perFrameCameras);`. `BuildReplayInstructionFromBody` now reads, in order: `ParseReplayTrack` → `ParseReplayOptions` → `ParseReplayFramePayloads` → assemble.

- [ ] **Step 4: Run full source suite + compile-check — verify PASS**
```
& "C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe" -m pytest mcp_server\tests\test_director_replay_native_source.py -q
& ".\build_native.ps1" -Configuration Release
```
Expected: all PASS; `Build succeeded:`. `BuildReplayInstructionFromBody` is now a thin ~15-line orchestration of the three parsers.

- [ ] **Step 5: Commit**
```
git add src/RookNative/Handlers/DirectorReplayHandler.cpp mcp_server/tests/test_director_replay_native_source.py
git commit -m "refactor(director): extract ParseReplayFramePayloads (U6 per-frame content); finalize structure tests"
```

---

### Task 6: Clean rebuild + deploy + 6/6 live gate (behavior proof)

This task proves behavior preservation on a deterministic build. Requires Rhino (user-controlled) and a throwaway document.

**Files:** none (verification only).

- [ ] **Step 1: Run the Python unit + MCP dispatch + source tests** (no Rhino — gate before the expensive build)
```
& "C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe" -m pytest mcp_server\tests\test_director_replay.py mcp_server\tests\test_director_replay_native_source.py -q
```
Expected: all PASS.

- [ ] **Step 2: Fully clean rebuild + deploy via the established script** (Rhino must be CLOSED — the `.rhp` is file-locked while Rhino runs)

Ask the user to close Rhino. Then wipe `obj/` AND `bin/` (LTCG) to force a clean codegen per the troubleshooting rule, and use the repo's deploy script (it builds, then copies `RookNative.rhp`/`.pdb` to the correct Rhino plugin directory and guards against Rhino being open). **Run `cmd /c` via the PowerShell tool** — Git Bash `cmd /c` emits only a banner; confirm the success lines yourself:
```
Remove-Item -Recurse -Force "src\RookNative\obj\RookNative\Release" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "src\RookNative\bin\Release" -ErrorAction SilentlyContinue
cmd /c "scripts\deploy-native.bat Release"
```
Expected: `Previous IPDB not found, fall back to full compilation` / `All NNNNN functions were compiled` / `Build succeeded:` / `Deploy succeeded.` (If it prints `DEPLOY FAILED — is Rhino running?`, Rhino is still open — close it and re-run.) Do **not** hand-copy the `.rhp`; the script owns the destination path.

- [ ] **Step 3: Launch Rhino + verify** — ask the user to launch Rhino with a throwaway document, then confirm `rhino_ping` → `pong`.

- [ ] **Step 4: Run the live replay gate**
```
& "C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe" -m pytest mcp_server\tests\test_director_replay_live.py -v --no-header -p no:warnings
```
Expected: **6 passed**, including `test_replay_cancel_mid_replay` and `test_replay_completes_and_restores`.

- [ ] **Step 5: Final whole-file review (no commit)**
Confirm: `HandleDirectorReplay` is a thin orchestrator (~60 lines); U7 loop body and `HandleDirectorReplayCancel` are byte-unchanged from `origin/main`; `SendCode` removed; no `ParseBodyAndDocSn` reference; no `.h`/`.vcxproj`/Python/C#/Meshy changes (`git diff --stat origin/main...HEAD` shows only `DirectorReplayHandler.cpp` + `test_director_replay_native_source.py` + the spec/plan docs).

Then finish the branch via `superpowers:finishing-a-development-branch` (PR to `main`; test plan notes the pre-existing unrelated `publish_video` failure).

## Self-Review

- **Spec coverage:** every component (`ReplayRequestError`, `ReplayInstruction`, `ParseReplayRequestBody`, `ParseReplaySessionId`, `ParseReplayTrack`, `ParseReplayOptions`, `ParseReplayFramePayloads`, `BuildReplayInstructionFromBody`) has a creating task (1, 2, 3, 4, 5). The error table is preserved by the conversion rule + verbatim-string constraint. The reserve-before-build precedence is encoded in Task 2 Step 5 + tested in Task 2 Step 1. The 3 re-pointed tests are handled at Tasks 2 (→builder) and 5 (→frame parser). The clean-rebuild + 6/6 gate is Task 6.
- **Type consistency:** `ReplayTrackInfo{frameCount, animatedObjectIds}`, `ReplayOptions{effectiveFps, dwellMs, plannedDurationMs, restoreOnFinish}`, `ParsedReplayFrames{perFrameObjects, perFrameCameras}`, and `ReplayInstruction`'s fields are used consistently across Tasks 2–5. `BuildReplayInstructionFromBody(const nlohmann::json&, std::string)` and the parser signatures match between definition and call sites.
- **Placeholders:** the `/* <moved ...> */` markers denote *existing code being relocated verbatim under the stated conversion rule* (the code already exists in `origin/main`); they are not undecided logic. Every NEW unit (types, signatures, tests, orchestrator, re-binds) is given in full.
