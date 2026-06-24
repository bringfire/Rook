# RookVisionDirector Native Replay — Implementation Plan (PR2 proper)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add native, guarded, cancellable **display-only** live replay of a baked animation track: `/director/replay` + `/director/replay/cancel`, the `rhino_director_replay` + `rhino_director_replay_cancel` MCP tools, and shared `DirectorFrame` per-frame primitives extracted (behavior-preserving) from frame-capture.

**Architecture:** Replay holds the Rhino UI thread inside a `Dispatch`ed lambda wrapped in a **single `DispatchDrainSuspension`** for the whole loop; per frame it applies the track pose (reusing frame-capture's `delta`/`inverseDelta` object transform + camera primitives), redraws, and holds an interruptible bounded message-pump dwell; a worker-thread cancel route flips an atomic the loop checks. One replay at a time via a single active slot.

**Tech Stack:** C++ (RookNative, RhinoCommon C++ SDK, httplib, `DispatchDrainSuspension`), Python MCP (`director.py`, `server.py`, `bridge.call_rhino`), pytest (`FakeNative`, source-analysis), live Rhino integration tests.

**Spec:** `docs/superpowers/specs/2026-06-24-rookvisiondirector-replay-native-design.md` (read it first — this plan implements it).

## Global Constraints

- **Display-only:** no PNG/frame output, no output-dir param, no `capture` flag, no reuse of frame-capture's file-writing side. (Replay reuses the per-frame *application* logic only.)
- **One input contract:** full `track` inline; native validates/zips/caps; **ignores `resolution` and `provenance`**. No `frames[]` shape.
- **Timing:** `effective_fps = request.fps ?? track.fps ?? 24` (finite, positive); `dwell_ms = 1000/effective_fps`; **reject (not clamp)** `dwell_ms > 250` and `frame_count*dwell_ms > 60000`.
- **Caps:** `pump_slice_ms ≈ 16`, `max_per_frame_dwell_ms = 250`, `max_effective_replay_duration_ms = 60000`, `max_frame_count = 3000`, `max_object_count = 256` (unique `object_id`s across the track), `max_payload_bytes = 8 MiB` (check raw body before full parse where practical).
- **`transform_semantics` must equal `"absolute_from_source"`** (else `unsupported_transform_semantics`).
- **`replay_session_id`:** non-empty string, ≤128 chars, `[A-Za-z0-9._-]` only; Python default `uuid4().hex`. Same rule on replay + cancel.
- **`loop:true` → reject** `unsupported_replay_option` (`{option:"loop"}`); never silently ignored.
- **Single active slot**; second replay → `replay_already_active` **before any Dispatch**. RAII slot release on every path.
- **Cancel = pure worker thread:** no `CMainThreadDispatcher::Instance().Dispatch`, no Rhino-doc API; idempotent (`no_active_replay`/`session_mismatch`); **no active-session-id leak**.
- **Whole replay loop under ONE `DispatchDrainSuspension`** (the spike's S2 pattern) — prevents between-frame interleave.
- **Restore contract:** objects restored between **non-final** frames (apply that frame's `inverseDelta`); **terminal restore** is the single point honoring `restore_on_finish` (completed+`false` leaves final pose+camera; otherwise restore objects+camera); **cancel/error always restore** (incl. a late cancel during the *final* frame's dwell). Camera is set absolutely each frame; only the terminal/cancel/error restore touches the pre-replay camera snapshot.
- **`status`** discriminates success (`completed`/`cancelled`); **`code`** discriminates errors. Error-code ownership: Python-only `invalid_track_input`/`track_not_found`/`track_read_failed`; everything else native.
- **Native builds via the PowerShell tool** (`cmd /c "scripts\build-native.bat"`) — Git Bash `cmd /c` may emit only a banner; confirm `Build succeeded: …RookNative.rhp`. **Do not change `.vcxproj`** unless a new file requires it (RookNative globs sources — verify, see Task 1).
- Running `dotnet test`/native-source pytest needs no Rhino; **live tests need Rhino + `fresh_document`**.

## File Structure

| File | Responsibility | New? |
|---|---|---|
| `src/RookNative/Handlers/DirectorFrame.h` / `.cpp` | Shared per-frame primitives: `FrameObjectTransform`/`FrameCamera`/`FrameInstruction` structs, `ParseFrameInstruction`, `ApplyFrameObjects` (delta), `RestoreFrameObjects` (inverseDelta), `SetCameraFromFrame`, `ValidateFrameObjects`, `CaptureViewportCamera`/`ApplyViewportCamera` (for snapshots) — moved/extracted from `DirectorHandler.cpp` | new |
| `src/RookNative/Handlers/DirectorHandler.cpp` | `frame-capture` refactored to call `DirectorFrame` helpers — behavior-preserving | modify |
| `src/RookNative/Handlers/DirectorReplayHandler.h` / `.cpp` | `HandleDirectorReplay`, `HandleDirectorReplayCancel`, single active-slot registry | new |
| `src/RookNative/RookServer.cpp` | register `/director/replay` + `/director/replay/cancel` | modify |
| `mcp_server/src/rook/director.py` | `run_replay`, `cancel_replay`, track-resolution + session-id helpers | modify |
| `mcp_server/src/rook/server.py` | `rhino_director_replay` + `rhino_director_replay_cancel` `Tool` + `case` | modify |
| `mcp_server/tests/test_director_replay_native_source.py` | native source-analysis tests | new |
| `mcp_server/tests/test_director_replay.py` | Python `run_replay`/`cancel_replay` unit tests (`FakeNative`) | new |
| `mcp_server/tests/test_director_mcp_tools.py` | MCP contract tests for the two new tools | modify |
| `mcp_server/tests/test_director_replay_live.py` | live Rhino tests | new |

**Mechanism note (read before Task 1).** Frame-capture's object apply is **relative** via `TransformObjectInPlace(pDoc, frameObject, xform)` where each `FrameObjectTransform` carries a precomputed `delta` (apply: source→pose) and `inverseDelta` (restore: pose→source) — see `ParseFrameInstruction` (~L1170) and the `FrameRestoreGuard` (~L1450–1521) in `DirectorHandler.cpp`. Replay reuses these: per frame apply `delta`; "restore to source" = apply that frame's `inverseDelta`. The **camera** has no such inverse — replay snapshots the pre-replay viewport camera and re-applies it on terminal/cancel/error restore.

---

### Task 1: Extract shared `DirectorFrame` primitives; refactor frame-capture (behavior-preserving)

**Files:**
- Create: `src/RookNative/Handlers/DirectorFrame.h`, `src/RookNative/Handlers/DirectorFrame.cpp`
- Modify: `src/RookNative/Handlers/DirectorHandler.cpp` (move structs + helpers out; call them)
- Test: `mcp_server/tests/test_director_replay_native_source.py` (new — parity assertions)

**Interfaces — Produces (used by Tasks 2–3):**
- `struct FrameObjectTransform { std::string objectId; ON_UUID uuid; ON_Xform delta; ON_Xform inverseDelta; /* + existing fields */ };`
- `struct FrameCamera { /* existing fields: projection, location, target, up, lens_length, … */ };`
- `struct FrameInstruction { /* existing: frameIndex, camera (FrameCamera), objects (vector<FrameObjectTransform>), resolution, display, … */ };`
- `FrameInstruction ParseFrameInstruction(const nlohmann::json& body);` (moved verbatim)
- `void ValidateFrameObjects(CRhinoDoc* pDoc, const std::vector<FrameObjectTransform>& objects);` (moved verbatim; throws `DirectorFrameValidationError`)
- `bool ApplyFrameObjects(CRhinoDoc* pDoc, const std::vector<FrameObjectTransform>& objects);` (applies each `delta` via `TransformObjectInPlace`)
- `bool RestoreFrameObjects(CRhinoDoc* pDoc, const std::vector<FrameObjectTransform>& objects);` (applies each `inverseDelta`)
- `void SetCameraFromFrame(CRhinoView* pView, const FrameCamera& camera);` (extracted camera-set)
- `bool CaptureViewportCamera(CRhinoView* pView, ON_3dmView& outView);` and `bool ApplyViewportCamera(CRhinoView* pView, const ON_3dmView& view);` (pre-replay camera snapshot/restore — extracted/new)
- `DirectorFrameValidationError` (move its definition here so both handlers throw the same type).

- [ ] **Step 1: Read the current frame-capture internals.** Open `src/RookNative/Handlers/DirectorHandler.cpp` and locate: the `FrameObjectTransform`/`FrameCamera`/`FrameInstruction` structs (~L76–140), `ParseFrameInstruction`, `ParseTransformMatrix`, `TransformObjectInPlace` (~L1341), `ValidateFrameObjects` (~L1295), the camera-set code inside `ExecuteFrameTransaction`, and the `FrameRestoreGuard` (~L1450). Note exactly which functions/structs you will move vs. extract. No edit yet.

- [ ] **Step 2: Write the failing parity source-analysis test.**

Create `mcp_server/tests/test_director_replay_native_source.py`:

```python
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRAME_H = REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorFrame.h"
FRAME_CPP = REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorFrame.cpp"
DIRECTOR_CPP = REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorHandler.cpp"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_directorframe_unit_exposes_shared_primitives():
    header = _read(FRAME_H)
    for sym in [
        "struct FrameInstruction",
        "struct FrameObjectTransform",
        "struct FrameCamera",
        "ParseFrameInstruction",
        "ValidateFrameObjects",
        "ApplyFrameObjects",
        "RestoreFrameObjects",
        "SetCameraFromFrame",
    ]:
        assert sym in header, f"DirectorFrame.h missing {sym}"


def test_frame_capture_calls_shared_apply_and_restore():
    src = _read(DIRECTOR_CPP)
    # Frame-capture must route through the shared helpers, not private copies.
    assert "ApplyFrameObjects(" in src
    assert "RestoreFrameObjects(" in src
    assert "SetCameraFromFrame(" in src
    # And it must include the shared unit.
    assert '#include "Handlers/DirectorFrame.h"' in src or '#include "DirectorFrame.h"' in src
```

- [ ] **Step 3: Run the test — verify it fails.**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_director_replay_native_source.py -q`
Expected: FAIL — `DirectorFrame.h` does not exist / symbols absent.

- [ ] **Step 4: Create `DirectorFrame.h`/`.cpp` by moving the structs + helpers.** Move `FrameObjectTransform`, `FrameCamera`, `FrameInstruction`, `DirectorFrameValidationError`, `ParseFrameInstruction`, `ParseTransformMatrix`, `ParsePointArray3` (if only used here), `TransformObjectInPlace`, `ValidateFrameObjects` from `DirectorHandler.cpp` into `DirectorFrame.{h,cpp}` (declarations in `.h`, definitions in `.cpp`, under `namespace Rook { namespace Handlers {`). Add new `ApplyFrameObjects`/`RestoreFrameObjects` that loop over objects calling `TransformObjectInPlace(pDoc, obj, obj.delta)` and `…obj.inverseDelta)` respectively, and `SetCameraFromFrame` extracted from `ExecuteFrameTransaction`'s camera block, plus `CaptureViewportCamera`/`ApplyViewportCamera` (wrap `pView->Viewport()` get/set of the `ON_3dmView`/camera — use the same view API the camera-set uses). Keep signatures exactly as in the Interfaces block.

- [ ] **Step 5: Refactor `DirectorHandler.cpp` to call the shared helpers.** `#include "Handlers/DirectorFrame.h"`. In `ExecuteFrameTransaction`, replace the inline apply/camera/restore with `ApplyFrameObjects(...)`, `SetCameraFromFrame(...)`, and `RestoreFrameObjects(...)` (the `FrameRestoreGuard` should call `RestoreFrameObjects` or be reduced to wrap it). **Do not change behavior** — same order (apply → camera → capture → restore), same error types, same outputs.

- [ ] **Step 6: Confirm the new `.cpp` is in the build.** Check whether `src/RookNative/RookNative.vcxproj` globs `Handlers/*.cpp` or lists files explicitly: `rg -n "DirectorHandler.cpp|ClCompile Include=.*Handlers" src/RookNative/RookNative.vcxproj | head`. If globbed, nothing to do. If explicit, add `DirectorFrame.cpp` and `DirectorReplayHandler.cpp` (Task 2) entries mirroring `DirectorHandler.cpp` (this is the one allowed `.vcxproj` change).

- [ ] **Step 7: Run the parity test — verify it passes.**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_director_replay_native_source.py -q`
Expected: PASS (both tests).

- [ ] **Step 8: Native build — confirm behavior-preserving compile.**

Run (PowerShell tool): `cmd /c "scripts\build-native.bat"`
Expected: `Build succeeded: …RookNative.rhp`. (The existing `test_director_native_source.py` frame-capture asserts must also still pass: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_director_native_source.py -q` → PASS.)

- [ ] **Step 9: Commit.**

```bash
git add src/RookNative/Handlers/DirectorFrame.h src/RookNative/Handlers/DirectorFrame.cpp src/RookNative/Handlers/DirectorHandler.cpp mcp_server/tests/test_director_replay_native_source.py
git commit -m "refactor(director): extract shared DirectorFrame per-frame primitives (behavior-preserving)"
```

> **Behavioral regression proof** (the live frame-capture tests in `test_director_routes_live.py`) runs at Task 6 against live Rhino. If Task 6 surfaces a frame-capture behavior change, STOP and fix Task 1 before adding replay behavior.

---

### Task 2: Native single active-slot registry + `/director/replay/cancel`

**Files:**
- Create: `src/RookNative/Handlers/DirectorReplayHandler.h`, `src/RookNative/Handlers/DirectorReplayHandler.cpp`
- Modify: `src/RookNative/RookServer.cpp` (register cancel route)
- Test: `mcp_server/tests/test_director_replay_native_source.py` (add cases)

**Interfaces — Produces:**
- `void HandleDirectorReplay(const httplib::Request&, httplib::Response&);` (declared now; implemented Task 3)
- `void HandleDirectorReplayCancel(const httplib::Request&, httplib::Response&);`
- File-scope registry (in `.cpp`): `struct ReplaySlot { std::mutex mutex; bool active=false; std::string sessionId; std::atomic<bool> cancel{false}; };` + a `ReplaySlotReservation` RAII type that releases (`active=false`) on destruction. Helpers: `bool ReserveReplaySlot(const std::string& sessionId)` (returns false if active), `void ReleaseReplaySlot()`, and the cancel logic.
- `bool IsValidReplaySessionId(const std::string& id);` (non-empty, ≤128, `[A-Za-z0-9._-]`).

- [ ] **Step 1: Write failing source-analysis tests for the cancel route + registry.** Add to `test_director_replay_native_source.py`:

```python
def test_replay_routes_registered():
    server = _read(REPO_ROOT / "src" / "RookNative" / "RookServer.cpp")
    assert 'm_server->Post("/director/replay"' in server
    assert "Rook::Handlers::HandleDirectorReplay(req, res);" in server
    assert 'm_server->Post("/director/replay/cancel"' in server
    assert "Rook::Handlers::HandleDirectorReplayCancel(req, res);" in server


def test_cancel_handler_is_worker_thread_only():
    src = _read(REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorReplayHandler.cpp")
    cancel = _extract_function(src, "HandleDirectorReplayCancel")
    # The cancel route must never dispatch to the UI thread.
    assert "CMainThreadDispatcher::Instance().Dispatch" not in cancel
    # Idempotent, structured outcomes; no active-id leak.
    assert "no_active_replay" in cancel
    assert "session_mismatch" in cancel
    assert "cancel_requested" in cancel
    assert "active_replay_session_id" not in cancel


def test_replay_session_id_validation_present():
    src = _read(REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorReplayHandler.cpp")
    assert "IsValidReplaySessionId" in src
    assert "invalid_session_id" in src
```

Add an `_extract_function(src, name)` brace-matching helper to the test file (mirror the C# `ExtractFunction`: find `name(`, then balance `{`/`}`).

- [ ] **Step 2: Run — verify fail.** `…pytest mcp_server/tests/test_director_replay_native_source.py -q` → FAIL (file/symbols absent).

- [ ] **Step 3: Create `DirectorReplayHandler.h`** with the two handler declarations under `namespace Rook { namespace Handlers {`, and `#include` for httplib forward decls (mirror `DirectorHandler.h`).

- [ ] **Step 4: Implement the registry + cancel in `DirectorReplayHandler.cpp`.**

```cpp
#include "stdafx.h"
#include "Handlers/DirectorReplayHandler.h"
#include "Handlers/DirectorFrame.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"
#include <atomic>
#include <mutex>
#include <regex>

namespace Rook { namespace Handlers {

namespace {
struct ReplaySlot {
    std::mutex mutex;
    bool active = false;
    std::string sessionId;
    std::atomic<bool> cancel{false};
};
ReplaySlot& Slot() { static ReplaySlot s; return s; }

bool IsValidReplaySessionId(const std::string& id) {
    if (id.empty() || id.size() > 128) return false;
    for (char c : id)
        if (!(std::isalnum(static_cast<unsigned char>(c)) || c=='.' || c=='_' || c=='-'))
            return false;
    return true;
}

// Reserve under lock; returns false if a replay is already active.
bool ReserveReplaySlot(const std::string& sessionId) {
    auto& s = Slot();
    std::lock_guard<std::mutex> lk(s.mutex);
    if (s.active) return false;
    s.active = true;
    s.sessionId = sessionId;
    s.cancel.store(false, std::memory_order_release);
    return true;
}
void ReleaseReplaySlot() {
    auto& s = Slot();
    std::lock_guard<std::mutex> lk(s.mutex);
    s.active = false;
    s.sessionId.clear();
    s.cancel.store(false, std::memory_order_release);
}
struct ReplaySlotReservation {  // RAII release on every path
    bool held = false;
    ~ReplaySlotReservation() { if (held) ReleaseReplaySlot(); }
};
} // namespace

// Pure worker-thread cancel: touches only the registry + atomic. No Dispatch, no doc API.
void HandleDirectorReplayCancel(const httplib::Request& req, httplib::Response& res) {
    nlohmann::json body;
    try { body = nlohmann::json::parse(req.body); }
    catch (...) { nlohmann::json d; d["code"]="invalid_input"; d["message"]="invalid JSON";
                  CRookServer::SendErrorData(res, d); return; }

    std::string id = body.value("replay_session_id", std::string());
    if (!IsValidReplaySessionId(id)) {
        nlohmann::json d; d["code"]="invalid_session_id"; d["message"]="replay_session_id must be a 1..128 char [A-Za-z0-9._-] token";
        CRookServer::SendErrorData(res, d); return;
    }

    nlohmann::json data; data["replay_session_id"] = id;
    auto& s = Slot();
    std::lock_guard<std::mutex> lk(s.mutex);
    if (!s.active) { data["cancel_requested"]=false; data["reason"]="no_active_replay"; }
    else if (s.sessionId != id) { data["cancel_requested"]=false; data["reason"]="session_mismatch"; }
    else { s.cancel.store(true, std::memory_order_release); data["cancel_requested"]=true; }
    CRookServer::SendSuccess(res, data);
}

}} // namespace
```

Expose `ReserveReplaySlot`/`ReleaseReplaySlot`/`ReplaySlotReservation`/`Slot()`/`IsValidReplaySessionId` to Task 3 (same translation unit — Task 3's `HandleDirectorReplay` goes in this file, so keep them file-scope here and implement replay below them in Task 3).

- [ ] **Step 5: Register both routes in `RookServer.cpp`** beside the existing director routes (~L987):

```cpp
m_server->Post("/director/replay", [this](const httplib::Request& req, httplib::Response& res) {
    Rook::Handlers::HandleDirectorReplay(req, res);
});
m_server->Post("/director/replay/cancel", [this](const httplib::Request& req, httplib::Response& res) {
    Rook::Handlers::HandleDirectorReplayCancel(req, res);
});
```

(`HandleDirectorReplay` is declared in Task 2's header; implemented in Task 3. To compile now, add a minimal stub `void HandleDirectorReplay(...) { CRookServer::SendErrorData(res, {{"code","not_implemented"},{"message","replay not implemented"}}); }` and replace it in Task 3.)

- [ ] **Step 6: Run source-analysis — verify pass.** `…pytest test_director_replay_native_source.py -q` → PASS (note `test_replay_routes_registered` passes via the stub registration).

- [ ] **Step 7: Native build.** PowerShell: `cmd /c "scripts\build-native.bat"` → `Build succeeded`.

- [ ] **Step 8: Commit.**

```bash
git add src/RookNative/Handlers/DirectorReplayHandler.h src/RookNative/Handlers/DirectorReplayHandler.cpp src/RookNative/RookServer.cpp mcp_server/tests/test_director_replay_native_source.py
git commit -m "feat(director): replay single active-slot registry + worker-thread cancel route"
```

---

### Task 3: Native `/director/replay` — validation + guarded replay loop

**Files:**
- Modify: `src/RookNative/Handlers/DirectorReplayHandler.cpp` (implement `HandleDirectorReplay`, replace the stub)
- Test: `mcp_server/tests/test_director_replay_native_source.py` (add cases)

**Interfaces — Consumes:** `DirectorFrame` helpers (Task 1); `ReserveReplaySlot`/`ReleaseReplaySlot`/`ReplaySlotReservation`/`Slot()` (Task 2); `DispatchDrainSuspension`, `CMainThreadDispatcher` (main).

**Behavioral contract (from spec — implement exactly):**
- **Worker-phase validation** (before any Dispatch): parse body; `IsValidReplaySessionId`; raw-body-size ≤ 8 MiB (check `req.body.size()` before parse where practical → `payload_too_large`); `track` is an object; `track.transform_semantics == "absolute_from_source"` (else `unsupported_transform_semantics`); `track.frame_count ≥ 1` and `camera_frames`/`object_frames` lengths == `frame_count` with `frame_index` 1..N in order (else `track_invalid`); `frame_count ≤ 3000` (`frame_count_exceeds_cap`); unique object-id count ≤ 256 (`object_count_exceeds_cap`); `loop` absent/false (true → `unsupported_replay_option {option:"loop"}`); compute `effective_fps = request.fps ?? track.fps ?? 24`, require finite+positive (`invalid_fps`); `dwell_ms = 1000/effective_fps`; `dwell_ms ≤ 250` (else `frame_dwell_exceeds_cap {dwell_ms,cap_ms:250}`); `frame_count*dwell_ms ≤ 60000` (else `replay_duration_exceeds_cap {planned_duration_ms,cap_ms:60000}`).
- **Reserve slot** → if false, `replay_already_active`. Bind a `ReplaySlotReservation reservation; reservation.held = true;` immediately so every later return releases it.
- **Dispatch the loop lambda**; block on `future.get()` on the worker thread.
- **Loop lambda (UI thread):** resolve doc; **UI-phase** `ValidateFrameObjects` (→ `object_not_found`); `CaptureViewportCamera(pView, preCam)`; construct **one** `DispatchDrainSuspension guard;`. For `i` in `0..frame_count-1`: `ParseFrameInstruction` for frame `i` (build the per-frame instruction from `camera_frames[i]` + `object_frames[i]`); `ApplyFrameObjects(delta)`; `SetCameraFromFrame`; redraw the view; **sliced dwell**: loop pumping ~16ms slices with `PeekMessage/TranslateMessage/DispatchMessage` until `dwell_ms` elapsed, checking `Slot().cancel.load(acquire)` each slice; if cancel seen → `RestoreFrameObjects(inverseDelta of frame i)` + `ApplyViewportCamera(preCam)` → return `{status:"cancelled", frames_played:i (frame i counts since applied), …}`; if `i < frame_count-1` → `RestoreFrameObjects(inverseDelta of frame i)` (restore objects to source; camera left, next frame overwrites); check cancel before next frame (same restore+return if set). After the loop (completed): if `restore_on_finish` → `RestoreFrameObjects(inverseDelta of final frame)` + `ApplyViewportCamera(preCam)`; else leave final pose+camera. Return `{status:"completed", frames_played:frame_count, effective_fps, dwell_ms, planned_duration_ms, restored, …}`.
- **`frames_played`:** count frames whose pose was applied (cancel before frame 0 → 0; cancel during/after applying frame K → K+1 counted as "K... " — use the convention: frames fully entered the apply step. Cancel during frame K's dwell → `frames_played = K+1` since K was applied). *(Spec wording: cancel during frame K's dwell after applying it → that frame counts.)*
- **Late-cancel-on-final-frame:** the per-slice cancel check inside the final frame's dwell must take the **cancel path** (restore + `cancelled`), so `restore_on_finish:false` cannot win after a late cancel. (The cancel check is inside the dwell loop, evaluated before the completed-branch terminal restore — so it naturally wins.)
- Wrap the lambda body in try/catch: on `DirectorFrameValidationError` → return that validation error; on `std::exception` → `RestoreFrameObjects` + `ApplyViewportCamera` + return `{code:"frame_apply_failed", frame_index, object_id?}`.
- Envelope: success outcomes (`completed`/`cancelled`) → `SendSuccess`; error codes → `SendErrorData`.

- [ ] **Step 1: Write failing source-analysis tests for the replay loop invariants.** Add:

```python
def test_replay_loop_uses_single_guard_and_shared_helpers():
    src = _read(REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorReplayHandler.cpp")
    replay = _extract_function(src, "HandleDirectorReplay")
    assert "DispatchDrainSuspension" in replay          # the guard
    assert replay.count("DispatchDrainSuspension ") == 1  # ONE guard, not per-frame
    assert "ApplyFrameObjects(" in replay
    assert "RestoreFrameObjects(" in replay
    assert "SetCameraFromFrame(" in replay
    assert "CaptureViewportCamera(" in replay and "ApplyViewportCamera(" in replay


def test_replay_has_no_capture_or_output_io():
    src = _read(REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorReplayHandler.cpp")
    replay = _extract_function(src, "HandleDirectorReplay")
    assert "CaptureViewportToFile" not in replay
    assert "output_path" not in replay


def test_replay_validation_and_caps_present():
    src = _read(REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorReplayHandler.cpp")
    for token in [
        "absolute_from_source", "unsupported_transform_semantics",
        "unsupported_replay_option", "invalid_fps",
        "frame_dwell_exceeds_cap", "replay_duration_exceeds_cap",
        "frame_count_exceeds_cap", "object_count_exceeds_cap",
        "replay_already_active", "object_not_found", "frame_apply_failed",
        "250", "60000", "3000", "256",
    ]:
        assert token in src, f"replay handler missing {token}"
    replay = _extract_function(src, "HandleDirectorReplay")
    assert "Slot().cancel.load" in replay  # cancel checked in the loop
```

- [ ] **Step 2: Run — verify fail.** FAIL (stub has none of these).

- [ ] **Step 3: Implement `HandleDirectorReplay`** in `DirectorReplayHandler.cpp` per the behavioral contract above, replacing the stub. Reuse `DirectorFrame` helpers for all geometry/camera; the only replay-specific UI work is the sliced-dwell pump + the camera snapshot + the cancel checks. The pump slice mirrors the validated spike: `MSG msg; while (PeekMessage(&msg,nullptr,0,0,PM_REMOVE)) { TranslateMessage(&msg); DispatchMessage(&msg); }` then a short `Sleep`/wait to fill the ~16ms slice, all inside the single `DispatchDrainSuspension`.

- [ ] **Step 4: Run source-analysis — verify pass.** `…pytest test_director_replay_native_source.py -q` → PASS.

- [ ] **Step 5: Native build.** PowerShell `cmd /c "scripts\build-native.bat"` → `Build succeeded`.

- [ ] **Step 6: Commit.**

```bash
git add src/RookNative/Handlers/DirectorReplayHandler.cpp mcp_server/tests/test_director_replay_native_source.py
git commit -m "feat(director): native /director/replay guarded synchronous replay loop"
```

---

### Task 4: Python `run_replay` + `cancel_replay`

**Files:**
- Modify: `mcp_server/src/rook/director.py`
- Test: `mcp_server/tests/test_director_replay.py` (new)

**Interfaces — Consumes:** `call_rhino` (bridge), `DirectorError`/`DirectorInputError` (director.py). **Produces:** `async def run_replay(arguments, *, call_native=call_rhino, port=None) -> dict`; `async def cancel_replay(arguments, *, call_native=call_rhino, port=None) -> dict`.

- [ ] **Step 1: Write failing unit tests.** Create `mcp_server/tests/test_director_replay.py`:

```python
import json, pytest
from pathlib import Path
from rook import director


class FakeNative:
    def __init__(self, response): self.response = response; self.calls = []
    async def __call__(self, endpoint, method="POST", data=None, port=None):
        self.calls.append((endpoint, method, data, port)); return self.response


VALID_TRACK = {"schema_version": 1, "transform_semantics": "absolute_from_source",
               "frame_count": 1, "fps": 24, "resolution": {"width": 16, "height": 16},
               "animated_object_ids": ["a"], "camera_frames": [], "object_frames": []}


@pytest.mark.asyncio
async def test_run_replay_inline_track_generates_session_id_and_posts():
    native = FakeNative({"success": True, "data": {"status": "completed", "frames_played": 1}})
    out = await director.run_replay({"track": VALID_TRACK}, call_native=native)
    assert out["status"] == "completed"
    ep, _m, body, _p = native.calls[0]
    assert ep == "/director/replay"
    assert body["track"] == VALID_TRACK
    assert isinstance(body["replay_session_id"], str) and body["replay_session_id"]


@pytest.mark.asyncio
async def test_run_replay_passthrough_session_id():
    native = FakeNative({"success": True, "data": {"status": "completed"}})
    await director.run_replay({"track": VALID_TRACK, "replay_session_id": "my-id_1"}, call_native=native)
    assert native.calls[0][2]["replay_session_id"] == "my-id_1"


@pytest.mark.asyncio
async def test_run_replay_track_path_read(tmp_path):
    p = tmp_path / "t.json"; p.write_text(json.dumps(VALID_TRACK), encoding="utf-8")
    native = FakeNative({"success": True, "data": {"status": "completed"}})
    await director.run_replay({"track_path": str(p)}, call_native=native)
    assert native.calls[0][2]["track"] == VALID_TRACK


@pytest.mark.asyncio
async def test_run_replay_both_or_neither_track_is_error():
    native = FakeNative({"success": True, "data": {}})
    with pytest.raises(director.DirectorError, match="invalid_track_input"):
        await director.run_replay({"track": VALID_TRACK, "track_path": "x"}, call_native=native)
    with pytest.raises(director.DirectorError, match="invalid_track_input"):
        await director.run_replay({}, call_native=native)


@pytest.mark.asyncio
async def test_run_replay_missing_path_and_bad_json(tmp_path):
    native = FakeNative({"success": True, "data": {}})
    with pytest.raises(director.DirectorError, match="track_not_found"):
        await director.run_replay({"track_path": str(tmp_path / "nope.json")}, call_native=native)
    bad = tmp_path / "bad.json"; bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(director.DirectorError, match="track_read_failed"):
        await director.run_replay({"track_path": str(bad)}, call_native=native)


@pytest.mark.asyncio
async def test_run_replay_native_error_raises_directorerror():
    native = FakeNative({"success": False, "data": {"code": "replay_already_active", "message": "busy"}})
    with pytest.raises(director.DirectorError, match="replay_already_active"):
        await director.run_replay({"track": VALID_TRACK}, call_native=native)


@pytest.mark.asyncio
async def test_cancel_replay_requires_id_and_posts():
    native = FakeNative({"success": True, "data": {"cancel_requested": True}})
    out = await director.cancel_replay({"replay_session_id": "abc"}, call_native=native)
    assert out["cancel_requested"] is True
    assert native.calls[0][0] == "/director/replay/cancel"
    with pytest.raises(director.DirectorError, match="invalid_session_id"):
        await director.cancel_replay({}, call_native=native)
```

- [ ] **Step 2: Run — verify fail.** `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_director_replay.py -q` → FAIL (`run_replay` undefined).

- [ ] **Step 3: Implement in `director.py`.**

```python
import uuid
_SESSION_RE = __import__("re").compile(r"^[A-Za-z0-9._-]{1,128}$")

def _resolve_track(arguments: dict) -> dict:
    inline = arguments.get("track")
    path = arguments.get("track_path")
    if (inline is None) == (path is None):  # both or neither
        raise DirectorInputError("invalid_track_input: provide exactly one of track or track_path")
    if inline is not None:
        if not isinstance(inline, dict):
            raise DirectorInputError("invalid_track_input: track must be an object")
        return inline
    p = Path(path)
    if not p.is_file():
        raise DirectorInputError(f"track_not_found: {path}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DirectorInputError(f"track_read_failed: {exc}") from exc

def _resolve_session_id(arguments: dict) -> str:
    sid = arguments.get("replay_session_id") or uuid.uuid4().hex
    if not _SESSION_RE.match(sid):
        raise DirectorInputError("invalid_session_id: must be a 1..128 char [A-Za-z0-9._-] token")
    return sid

async def run_replay(arguments: dict, *, call_native=call_rhino, port=None) -> dict:
    track = _resolve_track(arguments)
    sid = _resolve_session_id(arguments)
    req = {"replay_session_id": sid, "track": track,
           "restore_on_finish": arguments.get("restore_on_finish", True),
           "loop": arguments.get("loop", False)}
    if arguments.get("fps") is not None:
        req["fps"] = arguments["fps"]
    result = await call_native("/director/replay", "POST", req, port=port)
    if not result.get("success", False):
        data = result.get("data", {})
        raise DirectorError(f"{data.get('code','director_error')}: {data.get('message','')}")
    return result["data"]

async def cancel_replay(arguments: dict, *, call_native=call_rhino, port=None) -> dict:
    sid = arguments.get("replay_session_id")
    if not sid or not _SESSION_RE.match(str(sid)):
        raise DirectorInputError("invalid_session_id: must be a 1..128 char [A-Za-z0-9._-] token")
    result = await call_native("/director/replay/cancel", "POST", {"replay_session_id": sid}, port=port)
    if not result.get("success", False):
        data = result.get("data", {})
        raise DirectorError(f"{data.get('code','director_error')}: {data.get('message','')}")
    return result["data"]
```

Ensure `Path`, `json` are imported in `director.py` (they already are — verify).

- [ ] **Step 4: Run — verify pass.** `…pytest mcp_server/tests/test_director_replay.py -q` → PASS (8 tests).

- [ ] **Step 5: Commit.**

```bash
git add mcp_server/src/rook/director.py mcp_server/tests/test_director_replay.py
git commit -m "feat(director): Python run_replay + cancel_replay (thin track resolver)"
```

---

### Task 5: MCP tools `rhino_director_replay` + `rhino_director_replay_cancel`

**Files:**
- Modify: `mcp_server/src/rook/server.py` (`list_tools()` + `call_tool()`)
- Test: `mcp_server/tests/test_director_mcp_tools.py` (add cases)

**Interfaces — Consumes:** `director.run_replay`, `director.cancel_replay`.

- [ ] **Step 1: Write failing MCP contract tests.** Add to `mcp_server/tests/test_director_mcp_tools.py` (mirror its existing style — it lists tools and asserts schema/dispatch):

```python
@pytest.mark.asyncio
async def test_replay_tools_registered_with_clean_schema():
    tools = {t.name: t for t in await server.list_tools()}
    assert "rhino_director_replay" in tools
    assert "rhino_director_replay_cancel" in tools
    schema = tools["rhino_director_replay"].inputSchema
    blob = json.dumps(schema)
    for forbidden in ["oneOf", "anyOf", "allOf"]:
        assert forbidden not in blob
    # display-only: no capture/output surface
    for banned in ["capture", "output_path", "output_dir", "output_root"]:
        assert banned not in blob
    props = schema["properties"]
    assert {"track", "track_path", "replay_session_id", "fps", "restore_on_finish", "loop"} <= set(props)
    cancel_props = tools["rhino_director_replay_cancel"].inputSchema["properties"]
    assert "replay_session_id" in cancel_props


@pytest.mark.asyncio
async def test_replay_dispatch_routes_to_director(monkeypatch):
    import rook.server as srv
    called = {}
    async def fake_run(args, port=None): called["run"] = args; return {"status": "completed"}
    async def fake_cancel(args, port=None): called["cancel"] = args; return {"cancel_requested": True}
    monkeypatch.setattr(srv.director, "run_replay", fake_run)
    monkeypatch.setattr(srv.director, "cancel_replay", fake_cancel)
    await srv.call_tool("rhino_director_replay", {"track": {"x": 1}})
    await srv.call_tool("rhino_director_replay_cancel", {"replay_session_id": "abc"})
    assert called["run"] == {"track": {"x": 1}}
    assert called["cancel"] == {"replay_session_id": "abc"}
```

- [ ] **Step 2: Run — verify fail.** FAIL (tools absent).

- [ ] **Step 3: Register the two `Tool`s in `list_tools()`** (beside the other `rhino_director_*` tools):

```python
Tool(
    name="rhino_director_replay",
    description=("RookVisionDirector: live, display-only replay of a baked animation track in the "
                 "Rhino viewport. Synchronous and guarded; blocks until the replay completes or is "
                 "cancelled out-of-band. Does NOT capture/export — capture is a separate step."),
    inputSchema={
        "type": "object",
        "properties": {
            "track": {"type": "object", "description": "Full baked animation track (inline). Provide exactly one of track or track_path."},
            "track_path": {"type": "string", "description": "Path to a baked animation_track.json. Provide exactly one of track or track_path."},
            "replay_session_id": {"type": "string", "description": "Optional caller id (<=128 chars, [A-Za-z0-9._-]); generated if omitted. Use it to cancel."},
            "fps": {"type": "number", "description": "Optional playback fps override; defaults to the track fps or 24."},
            "restore_on_finish": {"type": "boolean", "description": "Default true: restore objects+camera to pre-replay state on clean completion. False leaves the final frame."},
            "loop": {"type": "boolean", "description": "Must be false in v1; true is rejected."},
        },
    },
),
Tool(
    name="rhino_director_replay_cancel",
    description=("RookVisionDirector: request cancellation of an in-progress replay by replay_session_id "
                 "(out-of-band; the replay call itself returns the terminal outcome)."),
    inputSchema={
        "type": "object",
        "required": ["replay_session_id"],
        "properties": {
            "replay_session_id": {"type": "string", "description": "The id of the replay to cancel (<=128 chars, [A-Za-z0-9._-])."},
        },
    },
),
```

- [ ] **Step 4: Add the dispatch `case`s in `call_tool()`** (mirror `rhino_director_run`'s wrapper):

```python
case "rhino_director_replay":
    try:
        result = {"success": True, "data": await director.run_replay(arguments, port=port)}
    except director.DirectorError as exc:
        result = {"success": False, "data": {"code": "director_error", "message": str(exc)}}

case "rhino_director_replay_cancel":
    try:
        result = {"success": True, "data": await director.cancel_replay(arguments, port=port)}
    except director.DirectorError as exc:
        result = {"success": False, "data": {"code": "director_error", "message": str(exc)}}
```

- [ ] **Step 5: Run — verify pass.** `…pytest mcp_server/tests/test_director_mcp_tools.py -q` → PASS. Also run `…pytest mcp_server/tests/test_director_replay.py mcp_server/tests/test_director_mcp_tools.py -q` green.

- [ ] **Step 6: Commit.**

```bash
git add mcp_server/src/rook/server.py mcp_server/tests/test_director_mcp_tools.py
git commit -m "feat(mcp): rhino_director_replay + rhino_director_replay_cancel tools"
```

---

### Task 6: Live Rhino tests + the empirical gate

**Files:**
- Create: `mcp_server/tests/test_director_replay_live.py`
- Requires: deployed native build + live Rhino (`fresh_document` fixture). **This is the load-bearing gate — the live cancel test is the only proof a worker-thread atomic interrupts a held UI-thread loop.**

**Interfaces — Consumes:** the live test harness from `test_director_routes_live.py` (the `fresh_document` fixture + `call_rhino`). Build a small valid track in-test (create N boxes, read their bbox/source state via `/director/object-states`, hand-assemble a 2–N frame `absolute_from_source` track with small translations).

- [ ] **Step 1: Write the live tests** (`@pytest.mark.live` or the marker `test_director_routes_live.py` uses):
  - `test_replay_completes_and_restores`: 3-frame track; `run_replay(restore_on_finish=True)` → `status=="completed"`, `frames_played==3`, `restored is True`; assert each object's xform + the camera equal pre-replay (read via `/director/object-states` / view-state).
  - `test_replay_restore_on_finish_false_leaves_final_frame`: same track, `restore_on_finish=False` → object xforms + camera match the final frame; then a follow-up `restore_on_finish=True` run returns to source.
  - `test_replay_cancel_mid_replay` **(load-bearing):** a track long enough to dwell (e.g. 20 frames at low fps within caps); `asyncio.gather(run_replay(session_id="s1", ...), _cancel_after(0.2, "s1"))` where `_cancel_after` sleeps then calls `cancel_replay`; assert the replay result `status=="cancelled"`, `0 < frames_played < frame_count`, `restored is True`, and the doc is back at source.
  - `test_replay_already_active`: `asyncio.gather` two `run_replay` calls (distinct ids) → exactly one raises/returns `replay_already_active`.
  - `test_replay_validation_errors_live`: `loop=True` → `unsupported_replay_option`; a track with `transform_semantics="delta"` → `unsupported_transform_semantics`; a track referencing a non-existent object id → `object_not_found`.

- [ ] **Step 2: Deploy the build.** PowerShell `cmd /c "scripts\deploy-native.bat"` (Rhino closed). Then the user launches Rhino (per `[[feedback_user_controls_rhino_launch]]` — hand them the command; do not auto-launch). Verify `rhino_ping` → `pong`.

- [ ] **Step 3: Run the live suite** against Rhino: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_director_replay_live.py -q`. Expected: all pass. **The cancel test passing is the gate** that proves the design works end to end.

- [ ] **Step 4: Run the existing live frame-capture regression** to confirm Task 1's extraction preserved behavior: `…pytest mcp_server/tests/test_director_routes_live.py -q` → green. If red, STOP and fix Task 1.

- [ ] **Step 5: Commit.**

```bash
git add mcp_server/tests/test_director_replay_live.py
git commit -m "test(director): live replay completion/restore/cancel/busy/validation"
```

## Self-Review

**Spec coverage:**
- Display-only / no-capture → Task 1 (shared apply only) + Task 3 (`test_replay_has_no_capture_or_output_io`) + Task 5 (no capture fields). ✅
- Full inline track, native validate/zip/caps, ignore resolution/provenance → Task 3 worker-phase validation. ✅
- FPS-driven dwell, reject-not-clamp → Task 3 (`frame_dwell_exceeds_cap`/`replay_duration_exceeds_cap`). ✅
- Lifecycle/restore (non-final restore, terminal restore, cancel/error always restore, late-final-cancel) → Task 3 loop contract + the explicit late-cancel note. ✅
- Single slot, `replay_already_active` pre-dispatch, RAII release → Task 2 registry + Task 3 reserve. ✅
- Worker-thread idempotent cancel, no leak → Task 2 (`test_cancel_handler_is_worker_thread_only`). ✅
- One guard for whole loop → Task 3 (`DispatchDrainSuspension count == 1`). ✅
- status/code split, distinct codes, ownership → Task 3 (native codes) + Task 4 (Python codes) + tests. ✅
- Shared `DirectorFrame` extraction, behavior-preserving → Task 1 + Task 6 Step 4 regression. ✅
- Two-phase validation (worker + UI `object_not_found`) → Task 3 contract. ✅
- Python thin resolver (track path|inline, session id) → Task 4. ✅
- MCP tools, clean schema → Task 5. ✅
- Tests: source-analysis / unit / MCP / live + structural-primary parity + live cancel load-bearing → Tasks 1–6. ✅
- `replay_session_id` shape, object-count rule → Task 2 (`IsValidReplaySessionId`) + Task 3 (`object_count_exceeds_cap`). ✅
- Caps constants → Task 3 (`250/60000/3000/256`) + raw-body 8 MiB. ✅

**Placeholder scan:** native handler bodies are specified behaviorally with the load-bearing snippets (registry, cancel, guard, restore ordering) shown in full and exact reuse targets named; Python/test code is complete. The one judgment area — extracting `ExecuteFrameTransaction`'s inline camera/apply into helpers — is bounded by Step 1's read + the exact Interfaces signatures, not a vague "refactor."

**Type consistency:** `FrameInstruction`/`FrameObjectTransform`/`FrameCamera`, `ApplyFrameObjects`/`RestoreFrameObjects`/`SetCameraFromFrame`/`ValidateFrameObjects`/`CaptureViewportCamera`/`ApplyViewportCamera`, `ReserveReplaySlot`/`ReleaseReplaySlot`/`ReplaySlotReservation`/`Slot()`/`IsValidReplaySessionId`, `run_replay`/`cancel_replay`/`_resolve_track`/`_resolve_session_id`, tools `rhino_director_replay`/`rhino_director_replay_cancel` — used identically across tasks.
