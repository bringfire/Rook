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
- **Native builds via the PowerShell tool** (`cmd /c "scripts\build-native.bat"`) — Git Bash `cmd /c` may emit only a banner; confirm `Build succeeded: …RookNative.rhp`.
- **`RookNative.vcxproj` lists sources EXPLICITLY (not globbed)** — e.g. `<ClCompile Include="Handlers\DirectorHandler.cpp" />` (vcxproj L134) with a parallel `RookNative.vcxproj.filters` entry. The two new `.cpp` + their `.h` (`DirectorFrame`, `DirectorReplayHandler`) **must** be added to BOTH `RookNative.vcxproj` and `RookNative.vcxproj.filters`, or the build silently omits the translation units / fails to link. **AGENTS.md:21 forbids editing `.vcxproj`/`.vcxproj.filters` without explicit approval — that approval is granted by this plan's review for exactly these four entries; do not make other project-file edits.** Stage these files in the relevant task commits.
- **Two existing RAII guards are reused, not reinvented:** `DirectorObjectPoseGuard` (object pose; partial-apply tracking, reverse-order restore, post-restore bbox validation, `HasDirtyPartialState`) and `DirectorViewportGuard` (camera snapshot/restore). Both are moved to `DirectorFrame` and gain a `Disarm()` (suppress destructor restore) for the `restore_on_finish:false` leave-final-state case. `Disarm()` is behavior-neutral for frame-capture (which always `Restore()`s).
- Running `dotnet test`/native-source pytest needs no Rhino; **live tests need Rhino + `fresh_document`**.

## File Structure

| File | Responsibility | New? |
|---|---|---|
| `src/RookNative/Handlers/DirectorFrame.h` / `.cpp` | **Pure** shared per-frame primitives moved from `DirectorHandler.cpp`: structs `FrameObjectTransform`/`FrameCamera`; `DirectorFrameValidationError`; `ParseTransformMatrix`, `ParsePointArray3`, `ParseCamera`, `ParseFrameObjectTransforms` (camera + `object_transforms` only — **no** capture fields); `ValidateFrameObjects`; `TransformObjectInPlace`, `BboxAlmostEqual`; `SetCameraFromFrame` (extracted from `ExecuteFrameTransaction` ~L1700–1750); guards `DirectorObjectPoseGuard` + `DirectorViewportGuard` (each gains `Disarm()`) | new |
| `src/RookNative/Handlers/DirectorHandler.cpp` | `frame-capture` refactored to call `DirectorFrame` helpers (behavior-preserving). **`ParseFrameInstruction` STAYS here** — it is capture-specific (`run_root`, `output_path`, `frame_id`, `director_version`, capture-bounded `resolution`, `ValidateOutputPolicy`) and now calls the shared `ParseCamera`/`ParseFrameObjectTransforms` | modify |
| `src/RookNative/Handlers/DirectorReplayHandler.h` / `.cpp` | `HandleDirectorReplay`, `HandleDirectorReplayCancel`, single active-slot registry | new |
| `src/RookNative/RookServer.cpp` | register `/director/replay` + `/director/replay/cancel` | modify |
| `src/RookNative/RookNative.vcxproj` + `…vcxproj.filters` | add `ClCompile`/`ClInclude` for `DirectorFrame.{cpp,h}` + `DirectorReplayHandler.{cpp,h}` (explicit-list project — see Global Constraints) | modify |
| `mcp_server/src/rook/director.py` | `run_replay`, `cancel_replay`, track-resolution + session-id helpers | modify |
| `mcp_server/src/rook/server.py` | `rhino_director_replay` + `rhino_director_replay_cancel` `Tool` + `case` | modify |
| `mcp_server/tests/test_director_replay_native_source.py` | native source-analysis tests | new |
| `mcp_server/tests/test_director_replay.py` | Python `run_replay`/`cancel_replay` unit tests (`FakeNative`) | new |
| `mcp_server/tests/test_director_mcp_tools.py` | MCP contract tests for the two new tools | modify |
| `mcp_server/tests/test_director_replay_live.py` | live Rhino tests | new |

**Mechanism note (read before Task 1 — verified against the real code).**
- **Object pose** is applied/restored by **`DirectorObjectPoseGuard`** (`DirectorHandler.cpp` ~L1446): `.Apply()` applies each object's precomputed `delta` (source→pose, via `TransformObjectInPlace` + `Redraw`, tracking `m_applied[i]`, throwing `DirectorFrameValidationError("native_frame_failed")` on a mid-apply failure); `.Restore(evidence)` restores **in reverse order**, validates each object still exists and its bbox matches `sourceBbox`, writes per-object evidence + `HasDirtyPartialState()`; the **destructor best-effort restores** unless already attempted. `inverseDelta` = inverse of `delta` (computed in `ParseFrameObjectTransforms`, rejecting non-invertible transforms). **Replay reuses this guard per frame — do NOT replace it with naive helpers**, or partial-apply / dirty-state semantics are lost.
- **Camera** is snapshot/restored by **`DirectorViewportGuard`** (~L1596), used alongside the pose guard in `ExecuteFrameTransaction`. Replay constructs **one** `DirectorViewportGuard` for the whole replay (snapshots the pre-replay camera once) and restores it on terminal/cancel/error. Camera is *applied* per frame by the extracted `SetCameraFromFrame` (the `targetViewport.SetProjection/SetCameraLocation/…` block ~L1700–1750).
- **Leave-final-state (`restore_on_finish:false`)** requires suppressing each guard's destructor restore → add a `Disarm()` method (sets the guard's `m_restoreAttempted=true` without restoring) to both guards.
- **Parser split (hard):** `ParseFrameInstruction` requires `run_root`/`output_path`/`frame_id`/`director_version`/capture-bounded `resolution` — **capture-only**. Replay must call ONLY the pure shared `ParseCamera({"camera": …})` + `ParseFrameObjectTransforms({"object_transforms": …})`, never `ParseFrameInstruction`.

---

### Task 1: Extract shared `DirectorFrame` primitives; refactor frame-capture (behavior-preserving)

**Files:**
- Create: `src/RookNative/Handlers/DirectorFrame.h`, `src/RookNative/Handlers/DirectorFrame.cpp`
- Modify: `src/RookNative/Handlers/DirectorHandler.cpp` (move pure pieces out; keep capture-only `ParseFrameInstruction`; call shared helpers), `src/RookNative/RookNative.vcxproj`, `src/RookNative/RookNative.vcxproj.filters`
- Test: `mcp_server/tests/test_director_replay_native_source.py` (new — parity assertions)

**Interfaces — Produces (used by Tasks 2–3), in `DirectorFrame.h`:**
- `class DirectorFrameValidationError` (move definition here so both handlers throw the same type).
- `struct FrameObjectTransform { std::string objectId; ON_UUID uuid; ON_Xform delta; ON_Xform inverseDelta; std::string validationStrength; ON_BoundingBox sourceBbox; };` (move verbatim — match the real fields).
- `struct FrameCamera { /* the real fields: location/target/up + hasLensLength/lensLength, hasFovDegrees/fovDegrees, hasAspect/aspect, hasNearFar/nearClip/farClip */ };` (move verbatim).
- `ON_Xform ParseTransformMatrix(const nlohmann::json& transform, const std::string& objectId);`
- `ON_3dPoint ParsePointArray3(const nlohmann::json&, const char* name);`
- `FrameCamera ParseCamera(const nlohmann::json& body);` (reads `body["camera"]` — **pure**, no capture fields).
- `std::vector<FrameObjectTransform> ParseFrameObjectTransforms(const nlohmann::json& body);` (reads `body["object_transforms"]`; computes `delta`/`inverseDelta`, validating invertibility + bbox — **pure**, no capture fields).
- `void ValidateFrameObjects(CRhinoDoc* pDoc, const std::vector<FrameObjectTransform>& objects);` (existence + bbox match; throws).
- `bool TransformObjectInPlace(CRhinoDoc*, const FrameObjectTransform&, const ON_Xform&);` and `bool BboxAlmostEqual(...)`.
- `void SetCameraFromFrame(CRhinoView* pView, const FrameCamera& camera);` (extracted from `ExecuteFrameTransaction` ~L1700–1750: `targetViewport.SetProjection/SetCameraLocation/SetCameraDirection/SetCameraUp/lens/…` + `pView->Redraw()`).
- `class DirectorObjectPoseGuard` (move verbatim) **+ a new `void Disarm() { m_restoreAttempted = true; }`** so the destructor leaves the applied pose in place.
- `class DirectorViewportGuard` (move verbatim) **+ the same `void Disarm()`**.

**NOT in `DirectorFrame`:** `ParseFrameInstruction` and `struct FrameInstruction` stay in `DirectorHandler.cpp` — they are capture-specific (`run_root`, `output_path`, `frame_id`, `director_version=="slice1"`, capture-bounded `resolution`, `ValidateOutputPolicy`). `ParseFrameInstruction` now calls the shared `ParseCamera` + `ParseFrameObjectTransforms`. Replay (Task 3) must **never** call `ParseFrameInstruction`.

- [ ] **Step 1: Read the real internals (no edit).** In `DirectorHandler.cpp`: `FrameObjectTransform`/`FrameCamera` structs (~L76–140); `ParseCamera` (~L590, reads `body["camera"]`); `ParseFrameObjectTransforms` (~L1169, computes `delta`/`inverseDelta`); `ParseFrameInstruction` (~L1223 — note the capture-only `run_root`/`output_path`/`frame_id`/`resolution` requirements); `ValidateFrameObjects` (~L1295); `TransformObjectInPlace` (~L1341); `DirectorObjectPoseGuard` (~L1446, with `Apply`/`Restore(evidence)`/`HasDirtyPartialState`/dtor `BestEffortRestore`); `DirectorViewportGuard` (~L1596); the camera-apply block + `ExecuteFrameTransaction` (~L1700–1990). Confirm exactly which symbols move (the pure list above) vs. stay (`FrameInstruction`/`ParseFrameInstruction`).

- [ ] **Step 2: Write the failing parity source-analysis test.** Create `mcp_server/tests/test_director_replay_native_source.py`:

```python
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRAME_H = REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorFrame.h"
DIRECTOR_CPP = REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorHandler.cpp"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_directorframe_exposes_pure_shared_primitives():
    header = _read(FRAME_H)
    for sym in [
        "struct FrameObjectTransform", "struct FrameCamera",
        "ParseCamera", "ParseFrameObjectTransforms", "ValidateFrameObjects",
        "SetCameraFromFrame", "class DirectorObjectPoseGuard",
        "class DirectorViewportGuard", "void Disarm",
    ]:
        assert sym in header, f"DirectorFrame.h missing {sym}"
    # Capture-only parser must NOT leak into the shared unit.
    assert "ParseFrameInstruction" not in header
    assert "run_root" not in header and "output_path" not in header


def test_frame_capture_uses_shared_unit_and_keeps_capture_parser():
    src = _read(DIRECTOR_CPP)
    assert '#include "Handlers/DirectorFrame.h"' in src or '#include "DirectorFrame.h"' in src
    assert "DirectorObjectPoseGuard" in src      # still used by ExecuteFrameTransaction
    assert "DirectorViewportGuard" in src
    assert "SetCameraFromFrame(" in src
    assert "FrameInstruction ParseFrameInstruction(" in src  # capture parser stays here
```

- [ ] **Step 3: Run — verify fail.** `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_director_replay_native_source.py -q` → FAIL (`DirectorFrame.h` absent).

- [ ] **Step 4: Create `DirectorFrame.{h,cpp}` by moving the pure pieces** (declarations in `.h`, definitions in `.cpp`, `namespace Rook { namespace Handlers {`, `#include` the RhinoCommon headers `DirectorHandler.cpp` uses for these): `DirectorFrameValidationError`, `FrameObjectTransform`, `FrameCamera`, `ParseTransformMatrix`, `ParsePointArray3`, `ParseCamera`, `ParseFrameObjectTransforms`, `BboxAlmostEqual`, `TransformObjectInPlace`, `ValidateFrameObjects`, `DirectorObjectPoseGuard`, `DirectorViewportGuard`. Add `void Disarm() { m_restoreAttempted = true; }` (public) to **both** guards. Extract the camera-apply block (~L1700–1750) into `void SetCameraFromFrame(CRhinoView* pView, const FrameCamera& camera)`. **Do not move** `FrameInstruction`/`ParseFrameInstruction`.

- [ ] **Step 5: Refactor `DirectorHandler.cpp`.** `#include "Handlers/DirectorFrame.h"`; delete the moved definitions; keep `FrameInstruction`/`ParseFrameInstruction` but make `ParseFrameInstruction` call the now-shared `ParseCamera` + `ParseFrameObjectTransforms`; make `ExecuteFrameTransaction`'s camera-apply call `SetCameraFromFrame(...)`. The pose/viewport guards are already used there — they now resolve to the moved classes. **Behavior-preserving:** same order, same error types/codes, same evidence shape.

- [ ] **Step 6: Add the new unit to the project files (APPROVED `.vcxproj` edit — see Global Constraints).** In `src/RookNative/RookNative.vcxproj`, beside `Handlers\DirectorHandler.cpp` (L134) / `Handlers\DirectorHandler.h` (L271): add `<ClCompile Include="Handlers\DirectorFrame.cpp" />` and `<ClInclude Include="Handlers\DirectorFrame.h" />`. In `src/RookNative/RookNative.vcxproj.filters`, mirror the `DirectorHandler` entries (same `<Filter>` group) for `DirectorFrame.cpp`/`.h`. (DirectorReplayHandler entries are added in Task 2.)

- [ ] **Step 7: Run the parity test — verify pass.** `…pytest mcp_server/tests/test_director_replay_native_source.py -q` → PASS.

- [ ] **Step 8: Native build + existing native-source regression.** PowerShell: `cmd /c "scripts\build-native.bat"` → `Build succeeded: …RookNative.rhp`; then `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_director_native_source.py -q` → PASS (existing frame-capture source asserts unbroken).

- [ ] **Step 9: Commit (stage the project files).**

```bash
git add src/RookNative/Handlers/DirectorFrame.h src/RookNative/Handlers/DirectorFrame.cpp \
        src/RookNative/Handlers/DirectorHandler.cpp \
        src/RookNative/RookNative.vcxproj src/RookNative/RookNative.vcxproj.filters \
        mcp_server/tests/test_director_replay_native_source.py
git commit -m "refactor(director): extract shared DirectorFrame primitives + guards (behavior-preserving)"
```

> **Behavioral regression proof** = the live frame-capture tests (`test_director_routes_live.py`) at Task 6. If Task 6 shows any frame-capture behavior change, STOP and fix Task 1 before trusting replay.

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

- [ ] **Step 7: Add `DirectorReplayHandler` to the project files (APPROVED `.vcxproj` edit).** In `RookNative.vcxproj` add `<ClCompile Include="Handlers\DirectorReplayHandler.cpp" />` + `<ClInclude Include="Handlers\DirectorReplayHandler.h" />`; mirror in `RookNative.vcxproj.filters` (same `Handlers` filter group as `DirectorHandler`).

- [ ] **Step 8: Native build.** PowerShell: `cmd /c "scripts\build-native.bat"` → `Build succeeded`.

- [ ] **Step 9: Commit (stage the project files).**

```bash
git add src/RookNative/Handlers/DirectorReplayHandler.h src/RookNative/Handlers/DirectorReplayHandler.cpp \
        src/RookNative/RookServer.cpp \
        src/RookNative/RookNative.vcxproj src/RookNative/RookNative.vcxproj.filters \
        mcp_server/tests/test_director_replay_native_source.py
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
- **Loop lambda (UI thread):**
  - Resolve doc + active `CRhinoView* pView`.
  - **UI-phase validation:** parse frame 0's objects via `ParseFrameObjectTransforms({"object_transforms": track["object_frames"][0]["object_transforms"]})` and `ValidateFrameObjects(pDoc, objs0)` → `object_not_found` if any id is missing (all frames share `animated_object_ids`, so one existence check covers them).
  - Construct **one** `DirectorViewportGuard viewportGuard(pDoc);` (snapshots the pre-replay camera once) and **one** `DispatchDrainSuspension guard;` for the whole loop.
  - `int framesPlayed = 0; nlohmann::json evidence;`
  - For `i` in `0..frame_count-1`:
    - `auto objs = ParseFrameObjectTransforms({"object_transforms": track["object_frames"][i]["object_transforms"]});`
    - `auto cam = ParseCamera({"camera": track["camera_frames"][i]["camera"]});`
    - `DirectorObjectPoseGuard poseGuard(pDoc, objs); poseGuard.Apply();` (applies `delta`, redraws, tracks partial; throws on apply failure) → `framesPlayed = i + 1;`
    - `SetCameraFromFrame(pView, cam);`
    - **sliced dwell:** loop pumping ~16ms slices (`PeekMessage/TranslateMessage/DispatchMessage`) until `dwell_ms` elapsed, checking `Slot().cancel.load(std::memory_order_acquire)` each slice. **If cancel seen:** `poseGuard.Restore(evidence); viewportGuard.Restore(evidence);` and return `{status:"cancelled", cancelled:true, frames_played:framesPlayed, frame_count, restored:true, replay_session_id}`.
    - **Between frames** (`i < frame_count-1`): `poseGuard.Restore(evidence);` (objects → source for the next frame; camera left, overwritten next). Also re-check `Slot().cancel` before the next iteration; if set, `viewportGuard.Restore(evidence)` (objects already restored) and return cancelled.
    - **Final frame** (`i == frame_count-1`): do **not** restore inside the loop — the terminal-restore block below decides.
  - **Terminal restore (completed):** the final frame's `poseGuard` is still in scope here (its iteration is the last). If `restore_on_finish` → `poseGuard.Restore(evidence); viewportGuard.Restore(evidence);` else → `poseGuard.Disarm(); viewportGuard.Disarm();` (leave final pose + camera; suppress destructor restore). Return `{status:"completed", frames_played:frame_count, frame_count, effective_fps, dwell_ms, planned_duration_ms, restored:(bool)restore_on_finish, replay_session_id}`.
    - *(Implementation note: to keep the final `poseGuard` alive for the terminal block, structure the loop so the final iteration's guard outlives the loop body — e.g. hoist a `std::optional<DirectorObjectPoseGuard>` updated each iteration, or special-case `i == frame_count-1` to skip the in-loop restore and fall through. Either way the dtor must not double-restore.)*
- **`frames_played` (single rule):** the count of frames whose pose was applied — incremented to `i + 1` immediately after `poseGuard.Apply()` succeeds for frame `i`. So: cancel before frame 0 applies → `0`; cancel during frame `K`'s dwell (after `K` was applied) → `K + 1`. (No other convention appears anywhere in this plan.)
- **Late-cancel-on-final-frame:** the per-slice cancel check lives **inside** the final frame's dwell and returns the cancel result (restore + `cancelled`) before control reaches the terminal-restore block — so a late cancel during the final dwell always restores and **cannot** fall into the `restore_on_finish:false` leave-final branch.
- Wrap the lambda body in try/catch: `DirectorFrameValidationError` → return that validation error (`object_not_found` etc.); other `std::exception` → the in-scope `poseGuard`/`viewportGuard` destructors best-effort-restore (do not `Disarm`) → return `{code:"frame_apply_failed", message, frame_index:i, object_id?}` (include `HasDirtyPartialState()` in the message if true).
- Envelope: success outcomes (`completed`/`cancelled`) → `SendSuccess`; error codes → `SendErrorData`.

- [ ] **Step 1: Write failing source-analysis tests for the replay loop invariants.** Add:

```python
REPLAY_CPP = REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorReplayHandler.cpp"


def test_replay_loop_uses_single_guard_and_shared_primitives():
    replay = _extract_function(_read(REPLAY_CPP), "HandleDirectorReplay")
    assert "DispatchDrainSuspension" in replay
    assert replay.count("DispatchDrainSuspension ") == 1   # ONE guard for the whole loop
    assert "DirectorObjectPoseGuard" in replay             # real pose guard, per frame
    assert "DirectorViewportGuard" in replay               # real camera guard
    assert replay.count("DirectorViewportGuard ") == 1     # one camera snapshot for the whole replay
    assert "ParseFrameObjectTransforms(" in replay         # pure shared parsers only
    assert "ParseCamera(" in replay
    assert "SetCameraFromFrame(" in replay
    assert ".Apply()" in replay and ".Restore(" in replay and ".Disarm()" in replay


def test_replay_does_not_use_capture_parser_or_io():
    replay = _extract_function(_read(REPLAY_CPP), "HandleDirectorReplay")
    # Replay must NOT reach into capture-only parsing or file I/O.
    assert "ParseFrameInstruction" not in replay
    assert "CaptureViewportToFile" not in replay
    for token in ["output_path", "run_root", "output_root"]:
        assert token not in replay


def test_replay_validation_caps_and_cancel_present():
    src = _read(REPLAY_CPP)
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
    assert "Slot().cancel.load" in replay
```

- [ ] **Step 2: Run — verify fail.** FAIL (stub has none of these).

- [ ] **Step 3: Implement `HandleDirectorReplay`** in `DirectorReplayHandler.cpp` per the behavioral contract above, replacing the Task-2 stub. All geometry/camera goes through the shared `DirectorFrame` primitives — object pose via `DirectorObjectPoseGuard` (per frame), camera snapshot/restore via one `DirectorViewportGuard`, camera-apply via `SetCameraFromFrame`, parsing via `ParseFrameObjectTransforms`/`ParseCamera`. The only genuinely replay-specific UI work is the sliced-dwell pump + the cancel checks. The pump slice mirrors the validated spike: `MSG msg; while (PeekMessage(&msg,nullptr,0,0,PM_REMOVE)) { TranslateMessage(&msg); DispatchMessage(&msg); }` then a short wait to fill the ~16ms slice — all inside the single whole-loop `DispatchDrainSuspension`. Worker-phase validation (semantics/caps/fps/session-id/loop/payload) runs before `Dispatch`; bind the `ReplaySlotReservation` right after a successful `ReserveReplaySlot` so every return releases it.

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
@pytest.mark.parametrize("bad", ["", 123, {"x": 1}])
async def test_run_replay_rejects_explicit_invalid_session_id(bad):
    native = FakeNative({"success": True, "data": {}})
    with pytest.raises(director.DirectorError, match="invalid_session_id"):
        await director.run_replay({"track": VALID_TRACK, "replay_session_id": bad}, call_native=native)
    assert native.calls == []  # rejected before any native call


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
    # Absent (key missing or None) -> generate. Present -> must be a valid string.
    if arguments.get("replay_session_id") is None:
        return uuid.uuid4().hex
    sid = arguments["replay_session_id"]
    if not isinstance(sid, str) or not _SESSION_RE.match(sid):
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
    if not isinstance(sid, str) or not _SESSION_RE.match(sid):
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
- Display-only / no-capture → Task 1 (pure parser split: `ParseFrameInstruction` stays capture-only) + Task 3 (`test_replay_does_not_use_capture_parser_or_io`) + Task 5 (no capture fields). ✅
- Parser boundary (replay never calls the capture parser) → Task 1 Interfaces + Task 3 `test_replay_does_not_use_capture_parser_or_io`. ✅
- Project-file edits for the two new units (explicit `.vcxproj`/`.filters`, AGENTS-approved) → Task 1 Step 6 + Task 2 Step 7, staged in both commits. ✅
- Real restore semantics preserved (`DirectorObjectPoseGuard` partial-apply/reverse-restore/bbox/dirty-state, `DirectorViewportGuard` camera; `Disarm()` for leave-final) → Task 1 (move verbatim + `Disarm`) + Task 3 (reused per frame / once). ✅
- Full inline track, native validate/zip/caps, ignore resolution/provenance → Task 3 worker-phase validation. ✅
- FPS-driven dwell, reject-not-clamp → Task 3 (`frame_dwell_exceeds_cap`/`replay_duration_exceeds_cap`). ✅
- Lifecycle/restore (non-final restore, terminal restore, cancel/error always restore, late-final-cancel) → Task 3 loop contract + the explicit late-cancel note. ✅
- Single slot, `replay_already_active` pre-dispatch, RAII release → Task 2 registry + Task 3 reserve. ✅
- Worker-thread idempotent cancel, no leak → Task 2 (`test_cancel_handler_is_worker_thread_only`). ✅
- One guard for whole loop → Task 3 (`DispatchDrainSuspension count == 1`). ✅
- status/code split, distinct codes, ownership → Task 3 (native codes) + Task 4 (Python codes) + tests. ✅
- Shared `DirectorFrame` extraction (pure parsers + both real guards), behavior-preserving → Task 1 + Task 6 Step 4 regression. ✅
- Two-phase validation (worker + UI `object_not_found`) → Task 3 contract. ✅
- Python thin resolver (track path|inline, session id) → Task 4. ✅
- MCP tools, clean schema → Task 5. ✅
- Tests: source-analysis / unit / MCP / live + structural-primary parity + live cancel load-bearing → Tasks 1–6. ✅
- `replay_session_id` shape, object-count rule → Task 2 (`IsValidReplaySessionId`) + Task 3 (`object_count_exceeds_cap`). ✅
- Caps constants → Task 3 (`250/60000/3000/256`) + raw-body 8 MiB. ✅

**Placeholder scan:** native handler bodies are specified behaviorally with the load-bearing snippets (registry, cancel, guard usage, restore ordering, the single `frames_played` rule) shown in full and exact reuse targets named with real line numbers; Python/test code is complete. The one judgment area — extracting `ExecuteFrameTransaction`'s inline camera-apply into `SetCameraFromFrame` and adding `Disarm()` to the two existing guards — is bounded by Step 1's read + the exact Interfaces signatures, not a vague "refactor."

**Type consistency:** `FrameObjectTransform`/`FrameCamera` (capture-only `FrameInstruction`/`ParseFrameInstruction` stay in `DirectorHandler.cpp`), shared `ParseCamera`/`ParseFrameObjectTransforms`/`SetCameraFromFrame`/`ValidateFrameObjects`/`TransformObjectInPlace`/`BboxAlmostEqual`, guards `DirectorObjectPoseGuard`/`DirectorViewportGuard` (+ `Disarm()`), `ReserveReplaySlot`/`ReleaseReplaySlot`/`ReplaySlotReservation`/`Slot()`/`IsValidReplaySessionId`, `run_replay`/`cancel_replay`/`_resolve_track`/`_resolve_session_id`, tools `rhino_director_replay`/`rhino_director_replay_cancel` — used identically across tasks. (The earlier `ApplyFrameObjects`/`RestoreFrameObjects`/`CaptureViewportCamera` free-function names are gone — superseded by the real guards.)
