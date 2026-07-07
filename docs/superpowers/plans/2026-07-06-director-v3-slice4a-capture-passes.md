# Director v3 Slice 4A: Worker Capture + Display-Mode Passes — Implementation Plan

> **For agentic workers:** This plan is written for an external implementer (Codex) executing task-by-task with a review checkpoint after every task. Steps use checkbox (`- [ ]`) syntax. **STOP at the end of each task and wait for review sign-off before starting the next task.**

**Goal:** Extend the proven `/director/worker-play` loop with per-frame ViewCapture + camera application, orchestrate multi-display-mode passes from Python with per-pass reset and assembly-compatible run roots, and prove the first v3 video end-to-end.

**Architecture:** A shared native capture primitive + strict display-mode resolver move into `DirectorFrame.{h,cpp}` (Task 1, with a live proof gate on the capture backend); the worker-play handler gains an optional `capture` block executed inside its existing delta loop (Task 2); a new Python orchestrator `director_worker_capture.py` owns the pass loop, per-pass `prepared.3dm` reset, output verification, and run metadata (Task 3); one MCP tool exposes it (Task 4); env-gated live gates prove video, multi-pass fidelity, fail-hard, and throughput (Task 5).

**Tech Stack:** Python 3 asyncio + pytest (`mcp_server/`), C++ Rhino SDK (`src/RookNative/`), MCP registration in `server.py`.

**Spec:** `docs/superpowers/specs/2026-07-06-director-v3-slice4a-capture-passes-design.md` (this branch — the binding contract; read it first, Codex-reviewed 2 rounds). Parent: `docs/superpowers/specs/2026-07-06-director-v3-snapshot-boundary-design.md`.

## Execution Contract (read before Task 1)

- **Branch/worktree:** `codex/director-v3-slice4a-capture-passes` at `.worktrees/director-v3-slice4a-capture`. Commit there, conventional-commit messages, one commit per green test cycle.
- **Python tests:** `cd mcp_server && python -m pytest tests/<file> -v`. Full covering set before each commit: the task's test file + `tests/test_director_worker_play.py` + `tests/test_director_worker_compile.py` + `tests/test_director_worker_common.py` + `tests/test_director_worker_prepare.py` (the S2/S3 suites are the regression gate — they must pass UNMODIFIED).
- **Native build:** `cmd /c scripts\build-native.bat` from the worktree root. Never raw msbuild. There is no native unit harness — the compile gate + live gates are the native tests.
- **NEVER touch Rhino:** do not deploy, launch, close, or send commands to a live Rhino. Live proofs and gates are run by the controller with the human. Unit tests use the fake-native pattern only.
- **Frozen surfaces (do not modify):** everything the S3 plan froze, plus: `director_worker_play.py` (import from it only), `director_worker_common.py`, `director_worker_compile.py`, `director_video.py` (import `_png_size` and `_default_output_root` only), `tests/test_director_worker_{common,prepare,compile,play}.py`, `DirectorReplayHandler.{h,cpp}`, `DirectorWorkerPlayHandler.cpp`'s S3 behavior when `capture` is absent (same request/response/error shapes). `DirectorHandler.cpp` may be modified ONLY to delete helpers that move to `DirectorFrame.{h,cpp}` and requalify their call sites — no behavior change.
- **STOP FOR REVIEW** at the end of every task: report status (DONE / DONE_WITH_CONCERNS / BLOCKED / NEEDS_CONTEXT), commits, test evidence (RED and GREEN output for TDD tasks), files changed, and any deviation from this plan with its reason. Do not start the next task until the reviewer signs off.
- If the plan contradicts the code you find, STOP and report — do not silently improvise. The spec is the authority over this plan; this plan is the authority over your judgment calls.

## Global Constraints

- **Error taxonomy (exact strings).** Native `data.reason` additions: `invalid_input`, `output_policy_violation`, `run_root_exists`, `display_mode_missing`, `display_mode_mismatch`, `capture_failed`. S3 reasons (`wrong_document`, `track_invalid`, `track_objects_missing`, `worker_scene_not_pristine`, `playback_drift_detected`) unchanged. Python codes: `unsupported_pass_type`, `pass_output_incomplete`, `capture_route_failed`, plus re-raised native reasons under their own names. No other codes.
- **Capture-mode wire rule:** every failure specific to the `capture` block (closed schema, odd/oversized dimensions, missing/empty/`"current"` displayMode, capture×chunking) → `data.reason = "invalid_input"`; path policy → `output_policy_violation`; collision → `run_root_exists`. Never generic `SendError`, never S3's `track_invalid` request_parameters path. All failure paths that exist in S3 keep their exact S3 behavior.
- **Full-range rule (exact):** with `capture` present, `fromFrame` must be absent or `0`, and `playTo` must be absent or exactly `frame_count`. Explicit `playTo == frame_count` is VALID. Anything else → `invalid_input`.
- **Frame files:** `frame_%04d.png`, 1-based, in `runRoot/frames/`. Loop frame index `i` (1..frame_count) → file index `i` → camera entry `camera_frames[i-1]` (whose `frame_index` == `i`).
- **Ordering (native, pinned):** parse request → load/parse track → `wrong_document` gate → object lookup (`track_objects_missing`) → capture path policy + collision → create `runRoot` + `runRoot/frames` → resolve display mode → viewport guard + set mode → pristine gate → loop. Failures before directory creation leave no run root; failures after leave an empty/partial run root for Python to mark failed.
- **Display mode:** resolve once by name/UUID (strict, shared resolver); `capture.displayMode` required, non-empty, not `"current"` (case-insensitive) → `invalid_input`; unresolvable concrete mode → `display_mode_missing`; per-frame post-camera readback mismatch → `display_mode_mismatch` with `frameIndex`.
- **Run-root layout:** `<director_output_root>/takes/<take_id>/<pass_id>` where director_output_root = `ROOK_DIRECTOR_OUTPUT_ROOT` env else `%LOCALAPPDATA%/Rook/rookvision_director` (both sides use their existing resolution helpers).
- **Run metadata (assembly-compatible, exact):** `manifest.json` = `{schema_version: 1, director_version: "slice1", run_id, frame_count, resolution: {width, height}, timeline: {fps, frame_count}, frames: [{frame_index, file}]}` (frames length == frame_count); run-local `status.json` = `{state: "complete"|"failed", ...}` written LAST, only after PNG verification. Both via atomic staging + `os.replace`.
- **PNG verification:** every frame exists, non-empty, and IHDR reports exactly requested width×height, via `director_video._png_size` (imported, never duplicated) → `pass_output_incomplete` otherwise.
- **Canonical JSON:** package artifacts written via `canonical_json_text` from `director_take_package.py`. Package `status.json` gains append-only `evidence.capture_passes` (mirror `evidence.play_runs`).
- **Native registration pattern (S2/S3-verified):** free function in `Rook::Handlers`, direct lambda registration next to the director siblings in `RookServer.cpp` (~line 1008) — NO member forwarder, NO `McpRequestGuard`.
- **Pinned MCP counts go 441 → 442.** Find every site with `rg -n "rhino_director_worker_play" mcp_server/src mcp_server/tests` and mirror it; the new tool is MUTATE (never in `_RHINO_READ_TOOLS` or any read-only list).
- **snake_case artifacts / camelCase native wire.** Track/manifest/status files snake_case; native request/response keys camelCase.

## Wire + Artifact Contracts

**`POST /director/worker-play` request — S3 surface unchanged, plus optional `capture`:**

```json
{
  "expectedDocumentPath": "C:/takes/take1/prepared.3dm",
  "trackPath": "C:/takes/take1/track.json",
  "capture": {
    "runRoot": "C:/Users/u/AppData/Local/Rook/rookvision_director/takes/take1/arctic",
    "framesDir": "C:/Users/u/AppData/Local/Rook/rookvision_director/takes/take1/arctic/frames",
    "displayMode": "Arctic",
    "width": 1280,
    "height": 720
  }
}
```

`capture` schema is CLOSED: exactly these five keys, all required; any unknown or missing key → `invalid_input`. No `packageRoot` at the native layer. When `capture` is absent the request/response/error contract is byte-for-byte S3.

**Success response `data` additions (only when `capture` present):**

```json
"capture": {
  "backend": "sdk",
  "runRoot": "...", "framesDir": "...", "framesWritten": 240,
  "displayModeRequested": "Arctic",
  "displayModeResolved": {"id": "...", "name": "Arctic"},
  "timing": {"captureTotalMs": 812.5, "capturePerFrameMs": [3.4, 3.3]}
}
```

`capturePerFrameMs` is an ARRAY, one entry per frame in play order, length == `framesWritten`; it measures everything capture mode adds per frame (camera set + readback + redraw + capture-to-file). `captureTotalMs` is its sum. Existing `timing.{totalMs,perFrameMs}` keep S3 shapes.

**`POST /director/capture-probe` (Task 1 diagnostic, HTTP-only, no MCP tool):**

```json
{"displayMode": "Arctic", "width": 1280, "height": 720,
 "outputPath": "C:/Users/u/AppData/Local/Rook/rookvision_director/takes/_probe/probe.png"}
```

Same displayMode/dimension rules as `capture`; `outputPath` must be under the director output root (`output_policy_violation`); parent directories created. Success data: `{"backend", "outputPath", "displayModeResolved", "readbackMatches": true}`.

**Python `capture_take` arguments:**

```json
{
  "package_root": "C:/takes/take1",
  "passes": [
    {"type": "display_mode", "display_mode": "Arctic", "pass_id": "arctic"},
    {"type": "display_mode", "display_mode": "Pen", "pass_id": "pen"}
  ],
  "resolution": {"width": 1280, "height": 720}
}
```

`pass_id` unique, non-empty, matches `^[a-z0-9_-]+$`. `type != "display_mode"` → `unsupported_pass_type` BEFORE any native call. Resolution: positive even ints.

**`capture_take` success payload:**

```json
{
  "package_root": "...", "take_id": "take1",
  "output_root": "<director_output_root>/takes/take1",
  "passes": [
    {"pass_id": "arctic", "display_mode": "Arctic", "run_root": "...",
     "frames_written": 240, "backend": "sdk",
     "capture_ms": {"total": 812.5, "mean": 3.4, "p95": 4.1, "max": 6.0},
     "drift": {"tolerance": 0.01, "worstCentroidOffset": 0.0003, "worstDiagonalRatio": 1.0001}}
  ]
}
```

**Typed failure payload extra (partial completion):** raised `DirectorWorkerCaptureError.to_data()` includes `{"failed_pass": "<pass_id>", "completed_passes": ["arctic"]}` when at least one pass had started.

**Package `status.json` — `evidence.capture_passes` entry (append-only, most recent last):**

```json
{"pass_index": 0, "pass_id": "arctic", "display_mode": "Arctic",
 "captured_at_utc": "...", "run_root": "...", "frames_written": 240,
 "backend": "sdk", "outcome": "complete",
 "capture_ms": {"total": 812.5, "mean": 3.4, "p95": 4.1, "max": 6.0},
 "drift": {"tolerance": 0.01, "worstCentroidOffset": 0.0003, "worstDiagonalRatio": 1.0001}}
```

Failed passes append the same entry with `"outcome": "failed", "reason": "<code>"` and whatever fields exist.

---

### Task 1: Native capture primitive + shared resolver + `/director/capture-probe`

**Files:**
- Modify: `src/RookNative/Handlers/DirectorFrame.h` (declarations), `src/RookNative/Handlers/DirectorFrame.cpp` (implementations)
- Modify: `src/RookNative/Handlers/DirectorHandler.cpp` (delete moved helpers, requalify call sites — NO behavior change)
- Modify: `src/RookNative/Handlers/DirectorWorkerPlayHandler.h` (declare `HandleDirectorCaptureProbe`), `src/RookNative/Handlers/DirectorWorkerPlayHandler.cpp` (implement it)
- Modify: `src/RookNative/RookServer.cpp` (register the probe route beside `/director/worker-play`, ~line 1008)

**Interfaces (later tasks consume these exactly):**

```cpp
// DirectorFrame.h — new section "Path policy + capture primitives (Slice 4A)".
// DirectorFrame.h has NO <filesystem> include today: add `#include <filesystem>`
// to its include block, and use fully qualified std::filesystem::path in the
// header (no `fs` alias in a header — it would leak into every includer).
std::filesystem::path GetAllowedDirectorRoot();          // moved from DirectorHandler.cpp
std::filesystem::path NormalizePolicyPath(const std::filesystem::path& path);  // moved
bool IsSameOrDescendantPath(const std::filesystem::path& root,
                            const std::filesystem::path& candidate);           // moved
bool IsSamePath(const std::filesystem::path& a, const std::filesystem::path& b);  // moved
ON_UUID ResolveDisplayModeId(const std::string& displayMode);  // moved (behavior identical)

struct DirectorCaptureResult { std::string backend; };   // "sdk" or "scripted_command"
// Captures pView (must be pDoc's active view) to a PNG at exactly width x height.
// Writes to a temp file first, verifies non-empty, renames into place.
// Throws DirectorFrameValidationError("capture_failed", ...) on any failure.
DirectorCaptureResult CaptureViewToPng(CRhinoDoc* pDoc, CRhinoView* pView,
                                       int width, int height,
                                       const std::filesystem::path& outputPath);
```

**Filesystem plumbing (build-breaking if skipped):** `DirectorFrame.cpp` and
`DirectorWorkerPlayHandler.cpp` currently have neither `<filesystem>` nor an `fs`
alias. In BOTH `.cpp` files add `#include <filesystem>` and
`namespace fs = std::filesystem;` below the includes (matching
`DirectorHandler.cpp`'s existing pattern) — the `.cpp` snippets in this plan use
`fs::path` and assume that alias. Header declarations stay fully qualified.

- [ ] **Step 1: Move the path-policy helpers and `ResolveDisplayModeId` to `DirectorFrame.{h,cpp}`**

These currently live in `DirectorHandler.cpp`'s anonymous namespace: `GetAllowedDirectorRoot` (:365), `NormalizePolicyPath`, `IsSameOrDescendantPath`, `IsSamePath`, `ResolveDisplayModeId` (:1609). Move each function body VERBATIM into `DirectorFrame.cpp` (external linkage, `Rook::Handlers` namespace), declare in `DirectorFrame.h` under a new `// Path policy + capture primitives (Slice 4A)` section, delete the anonymous-namespace copies from `DirectorHandler.cpp`, and confirm every former call site in `DirectorHandler.cpp` resolves to the shared versions. If any of these functions calls another file-local helper (e.g. `PathFromUtf8`, `Utf8ToWide`, `IEquals`), check whether that helper is already shared (many are in `Infrastructure/JsonHelpers.h` or `GrasshopperProxyHandler.h`); move it too ONLY if it is file-local, following the same verbatim rule. Zero behavior change — this step is pure linkage.

- [ ] **Step 2: Investigate the SDK capture path (timeboxed)**

Find the Rhino C++ SDK include directory from `src/RookNative/RookNative.vcxproj` (AdditionalIncludeDirectories). Search it:

```
rg -n "CaptureToDib|DrawToDib|CaptureToBitmap|class CRhinoDib" <sdk-include-dir>
```

Candidates to evaluate, in order: a `CRhinoView`/`CRhinoDisplayPipeline` offscreen draw-to-DIB API at caller-specified dimensions, then `CRhinoDib::WriteToFile` (or equivalent) for PNG output by extension. Acceptance for the SDK backend, verified later in the live proof (Step 6): (a) renders with the CURRENT display mode of the view, (b) honors exact requested width×height regardless of window size, (c) works with the Rhino window in the background. If no such API exists, or it cannot render display-mode-faithful output, fall back to Step 3's scripted backend — the spec licenses either outcome. Record the decision and the evidence (API found/not found, header + signature) in your task report; do not spend more than one focused investigation cycle before falling back.

- [ ] **Step 3: Implement `CaptureViewToPng`**

In `DirectorFrame.cpp`. If the SDK path won Step 2, implement it there and set `backend = "sdk"`. Otherwise implement the scripted backend below verbatim (adapted from the proven single-frame pattern at `DirectorHandler.cpp:1756-1802`), `backend = "scripted_command"`:

```cpp
DirectorCaptureResult CaptureViewToPng(CRhinoDoc* pDoc, CRhinoView* pView,
                                       int width, int height,
                                       const std::filesystem::path& outputPath)
{
    if (!pDoc || !pView)
        throw DirectorFrameValidationError("capture_failed", "document or view unavailable");
    if (pDoc->ActiveView() != pView)
        throw DirectorFrameValidationError("capture_failed", "capture view must be the active view");

    const std::filesystem::path tempPath =
        outputPath.parent_path() / (outputPath.filename().native() + L".tmp.png");

    std::error_code ec;
    std::filesystem::remove(tempPath, ec);

    ON_wString wFilePath(tempPath.native().c_str());
    std::wstring captureCmd = std::wstring(L"_-ViewCaptureToFile") +
        L" _Width=" + std::to_wstring(width) +
        L" _Height=" + std::to_wstring(height) +
        L" _Scale=1" +
        L" _DrawGrid=No" +
        L" _DrawWorldAxes=No" +
        L" _DrawCPlaneAxes=No" +
        L" _TransparentBackground=No" +
        L" \"" + std::wstring(static_cast<const wchar_t*>(wFilePath)) + L"\"" +
        L" _Enter";
    RhinoApp().RunScript(pDoc->RuntimeSerialNumber(), captureCmd.c_str(), 0);

    if (!std::filesystem::exists(tempPath, ec) || std::filesystem::file_size(tempPath, ec) == 0)
        throw DirectorFrameValidationError("capture_failed",
            "capture did not produce a non-empty file: " + outputPath.filename().string());
    std::filesystem::remove(outputPath, ec);
    std::filesystem::rename(tempPath, outputPath, ec);
    if (ec || !std::filesystem::exists(outputPath, ec))
        throw DirectorFrameValidationError("capture_failed",
            "failed to move capture into place: " + ec.message());

    DirectorCaptureResult result;
    result.backend = "scripted_command";
    return result;
}
```

If the SDK backend is implemented, keep the identical temp-write/verify/rename discipline and the identical throw contract; only the middle (render + write) differs.

- [ ] **Step 4: Implement `POST /director/capture-probe`**

Free function `HandleDirectorCaptureProbe(const httplib::Request&, httplib::Response&)` in `DirectorWorkerPlayHandler.cpp`, declared in the `.h`. Body:

```cpp
void HandleDirectorCaptureProbe(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::string displayMode;
    int width = 0, height = 0;
    std::string outputPathUtf8;
    try
    {
        ValidateStringField(body, "displayMode", displayMode);
        if (IEquals(displayMode, "current"))
            throw std::invalid_argument("displayMode must name a concrete mode, not 'current'");
        if (!body.contains("width") || !body["width"].is_number_integer() ||
            !body.contains("height") || !body["height"].is_number_integer())
            throw std::invalid_argument("width and height must be integers");
        width = body["width"].get<int>();
        height = body["height"].get<int>();
        if (width <= 0 || height <= 0 || (width % 2) != 0 || (height % 2) != 0 ||
            width > 8192 || height > 8192)
            throw std::invalid_argument("width and height must be positive even integers <= 8192");
        ValidateStringField(body, "outputPath", outputPathUtf8);
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendErrorData(res, nlohmann::json{
            {"reason", "invalid_input"}, {"message", ex.what()}});
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, displayMode, width, height, outputPathUtf8]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const fs::path outputPath = NormalizePolicyPath(fs::path(Utf8ToWide(outputPathUtf8)));
        const fs::path allowedRoot = GetAllowedDirectorRoot();
        if (!IsSameOrDescendantPath(allowedRoot, outputPath))
            return FailureResult("output_policy_violation",
                {{"message", "outputPath must be inside the director output root"}});
        std::error_code ec;
        fs::create_directories(outputPath.parent_path(), ec);

        ON_UUID modeId;
        try { modeId = ResolveDisplayModeId(displayMode); }
        catch (const DirectorFrameValidationError& ex)
        {
            return FailureResult("display_mode_missing", {{"message", ex.what()}});
        }

        DirectorViewportGuard guard(pDoc);
        CRhinoView* pView = guard.View();
        if (!pView)
            return FailureResult("capture_failed", {{"message", "no active view"}});
        CRhinoViewport& vp = pView->ActiveViewport();
        vp.SetDisplayMode(modeId);
        pView->Redraw();
        const ON_UUID applied = CurrentDisplayModeId(pView);
        if (ON_UuidCompare(applied, modeId) != 0)
            return FailureResult("display_mode_mismatch",
                {{"requested", DisplayModeToJson(modeId)},
                 {"applied", DisplayModeToJson(applied)}});

        nlohmann::json data;
        try
        {
            const DirectorCaptureResult capture =
                CaptureViewToPng(pDoc, pView, width, height, outputPath);
            data["backend"] = capture.backend;
        }
        catch (const DirectorFrameValidationError& ex)
        {
            return FailureResult(ex.code.c_str(), {{"message", ex.what()}});
        }
        data["outputPath"] = outputPathUtf8;
        data["displayModeResolved"] = DisplayModeToJson(modeId);
        data["readbackMatches"] = true;
        WriteResult wr;
        wr.success = true;
        wr.data = std::move(data);
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}
```

Notes: `FailureResult`, `ValidateStringField`, `ParseBodyAndDocSn`, `ResolveDoc` already exist in this file; `DirectorViewportGuard`, `CurrentDisplayModeId`, `DisplayModeToJson` come from `DirectorFrame.h`; the moved helpers from Step 1 are now shared. If `IEquals`/`Utf8ToWide` are not visible in this translation unit, include the header that provides them (check how `DirectorHandler.cpp` gets them).

- [ ] **Step 5: Register the route, build, commit**

In `RookServer.cpp` beside `/director/worker-play`:

```cpp
m_server->Post("/director/capture-probe", [this](const httplib::Request& req, httplib::Response& res) {
    Rook::Handlers::HandleDirectorCaptureProbe(req, res);
});
```

Run: `cmd /c scripts\build-native.bat` — expected: clean build, zero new warnings in the touched files.

```bash
git add src/RookNative
git commit -m "feat(director): shared capture primitive + strict resolver + capture-probe route (S4A T1)"
```

- [ ] **Step 6: STOP FOR REVIEW — includes controller-run live proof**

Report per the Execution Contract, including the Step 2 backend decision + evidence. The controller and human will then deploy and run the live proof (custom display mode, exact dimensions, background window, pixel spot check) against `/director/capture-probe`. **The backend decision is only final after this proof; if the SDK backend fails live, the fix is to switch `CaptureViewToPng` to the scripted backend — same function contract, no downstream changes.**

---

### Task 2: `/director/worker-play` capture extension

**Files:**
- Modify: `src/RookNative/Handlers/DirectorWorkerPlayHandler.cpp`

**Interfaces:**
- Consumes: `CaptureViewToPng`, `ResolveDisplayModeId`, path-policy helpers, `ParseCamera`, `SetCameraFromFrame`, `CurrentDisplayModeId`, `DisplayModeToJson`, `DirectorViewportGuard` (all from `DirectorFrame.h` after Task 1).
- Produces: the extended wire contract (see Wire + Artifact Contracts) that Task 3's orchestrator calls.

- [ ] **Step 1: Add the capture request struct + parser**

In the anonymous namespace, near `PlayRequest`:

```cpp
struct CaptureRequest
{
    bool present = false;
    fs::path runRoot;
    fs::path framesDir;
    std::string displayMode;
    int width = 0;
    int height = 0;
};

constexpr int kMaxCaptureDim = 8192;

// Throws std::invalid_argument on any violation; caller maps to invalid_input.
CaptureRequest ParseCaptureBlock(const nlohmann::json& body)
{
    CaptureRequest capture;
    if (!body.contains("capture") || body["capture"].is_null())
        return capture;
    const nlohmann::json& block = body["capture"];
    if (!block.is_object())
        throw std::invalid_argument("capture must be an object");

    static const std::set<std::string> kAllowed =
        {"runRoot", "framesDir", "displayMode", "width", "height"};
    for (const auto& item : block.items())
    {
        if (!kAllowed.count(item.key()))
            throw std::invalid_argument("capture has unknown field: " + item.key());
    }

    std::string runRoot, framesDir;
    ValidateStringField(block, "runRoot", runRoot);
    ValidateStringField(block, "framesDir", framesDir);
    ValidateStringField(block, "displayMode", capture.displayMode);
    if (IEquals(capture.displayMode, "current"))
        throw std::invalid_argument("capture.displayMode must name a concrete mode, not 'current'");
    if (!block.contains("width") || !block["width"].is_number_integer() ||
        !block.contains("height") || !block["height"].is_number_integer())
        throw std::invalid_argument("capture.width and capture.height must be integers");
    capture.width = block["width"].get<int>();
    capture.height = block["height"].get<int>();
    if (capture.width <= 0 || capture.height <= 0 ||
        (capture.width % 2) != 0 || (capture.height % 2) != 0 ||
        capture.width > kMaxCaptureDim || capture.height > kMaxCaptureDim)
        throw std::invalid_argument("capture.width and capture.height must be positive even integers <= 8192");

    capture.runRoot = NormalizePolicyPath(fs::path(Utf8ToWide(runRoot)));
    capture.framesDir = NormalizePolicyPath(fs::path(Utf8ToWide(framesDir)));
    capture.present = true;
    return capture;
}
```

Add an `InvalidInputData` helper beside `TrackInvalidData`:

```cpp
nlohmann::json InvalidInputData(nlohmann::json evidence = nlohmann::json::object())
{
    evidence["reason"] = "invalid_input";
    return evidence;
}
```

- [ ] **Step 2: Parse capture in the handler entry, with the capture-mode wire rule**

In `HandleDirectorWorkerPlay`, after the existing `ParsePlayRequest` try/catch (do not touch that catch — S3 behavior), add:

```cpp
CaptureRequest captureRequest;
try
{
    captureRequest = ParseCaptureBlock(body);
}
catch (const std::invalid_argument& ex)
{
    CRookServer::SendErrorData(res, InvalidInputData({{"message", ex.what()}}));
    return;
}
```

- [ ] **Step 3: Camera frames — parse when capture is present**

Extend `WorkerTrack` with `std::vector<FrameCamera> cameraFrames;`. Add a standalone parser (NOT inside `ParseWorkerTrack` — the S3 parser and its behavior stay untouched):

```cpp
// Throws std::invalid_argument (caller maps to track_invalid).
std::vector<FrameCamera> ParseCameraFrames(const nlohmann::json& trackJson, int frameCount)
{
    if (!trackJson.contains("camera_frames") || !trackJson["camera_frames"].is_array())
        throw std::invalid_argument("capture requires track camera_frames array");
    const auto& entries = trackJson["camera_frames"];
    if (static_cast<int>(entries.size()) != frameCount)
        throw std::invalid_argument("camera_frames length must equal frame_count");

    std::vector<FrameCamera> cameras;
    cameras.reserve(entries.size());
    for (int i = 0; i < static_cast<int>(entries.size()); ++i)
    {
        const auto& entry = entries[static_cast<size_t>(i)];
        if (!entry.is_object() || !entry.contains("frame_index") ||
            !entry["frame_index"].is_number_integer() ||
            entry["frame_index"].get<int>() != i + 1)
            throw std::invalid_argument(
                "camera_frames must be 1-based and contiguous (bad entry at position "
                + std::to_string(i) + ")");
        try
        {
            cameras.push_back(ParseCamera(entry));  // shared helper; reads entry["camera"]
        }
        catch (const DirectorFrameValidationError& ex)
        {
            throw std::invalid_argument(std::string("camera_frames[") + std::to_string(i)
                + "]: " + ex.what());
        }
    }
    return cameras;
}
```

Wire it into the handler in this exact order — the full-range `invalid_input` check
must fire BEFORE camera parsing, so a chunked capture request never surfaces as
`track_invalid` merely because the track's camera data is also bad:

1. The existing track-loading `try` block stays as-is through `ValidateFrameRange`
   (S3 behavior untouched) — but hoist `trackJson` so it remains in scope after
   the block (declare `nlohmann::json trackJson;` before the `try`, assign inside).
2. Immediately AFTER that `try`/`catch`, enforce the full-range rule (values, not
   defaulting — an explicit `playTo == track.frameCount` passes):

```cpp
if (captureRequest.present &&
    (playRequest.fromFrame != 0 || playRequest.playTo != track.frameCount))
{
    CRookServer::SendErrorData(res, InvalidInputData({
        {"message", "capture requires a full-range play: fromFrame 0 and playTo == frame_count"},
        {"fromFrame", playRequest.fromFrame}, {"playTo", playRequest.playTo},
        {"frameCount", track.frameCount}}));
    return;
}
```

3. THEN parse camera frames in their own `try` block, mapping to `track_invalid`
   (the spec's class for camera-contract violations):

```cpp
if (captureRequest.present)
{
    try
    {
        track.cameraFrames = ParseCameraFrames(trackJson, track.frameCount);
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendErrorData(res, TrackInvalidData({
            {"check", "camera_frames"},
            {"message", ex.what()}
        }));
        return;
    }
}
```

- [ ] **Step 4: Capture setup inside the dispatch lambda (pinned ordering)**

Add `captureRequest` to the dispatch lambda's capture list. Insert AFTER the `track_objects_missing` check and BEFORE the pristine gate:

```cpp
ON_UUID captureModeId = ON_nil_uuid;
std::unique_ptr<DirectorViewportGuard> viewportGuard;
CRhinoView* captureView = nullptr;
if (captureRequest.present)
{
    const fs::path allowedRoot = GetAllowedDirectorRoot();
    if (!IsSameOrDescendantPath(allowedRoot, captureRequest.runRoot))
        return FailureResult("output_policy_violation",
            {{"message", "capture.runRoot must be inside the director output root"}});
    if (!IsSamePath(captureRequest.runRoot / L"frames", captureRequest.framesDir))
        return FailureResult("output_policy_violation",
            {{"message", "capture.framesDir must be exactly runRoot/frames"}});
    std::error_code ec;
    if (fs::exists(captureRequest.runRoot, ec))
        return FailureResult("run_root_exists",
            {{"runRoot", PathToUtf8(captureRequest.runRoot)}});
    fs::create_directories(captureRequest.framesDir, ec);
    if (ec)
        return FailureResult("capture_failed",
            {{"message", "failed to create frames directory: " + ec.message()}});

    try { captureModeId = ResolveDisplayModeId(captureRequest.displayMode); }
    catch (const DirectorFrameValidationError& ex)
    {
        return FailureResult("display_mode_missing", {{"message", ex.what()}});
    }

    viewportGuard = std::make_unique<DirectorViewportGuard>(pDoc);
    captureView = viewportGuard->View();
    if (!captureView)
        return FailureResult("capture_failed", {{"message", "no active view for capture"}});
    captureView->ActiveViewport().SetDisplayMode(captureModeId);
    captureView->Redraw();
    const ON_UUID initialApplied = CurrentDisplayModeId(captureView);
    if (ON_UuidCompare(initialApplied, captureModeId) != 0)
        return FailureResult("display_mode_mismatch",
            {{"requested", DisplayModeToJson(captureModeId)},
             {"applied", DisplayModeToJson(initialApplied)}});
}
```

(`viewportGuard`'s destructor best-effort-restores the viewport on every exit path — worker doc is disposable, no explicit restore evidence needed. `PathToUtf8`: use the same helper `DirectorHandler.cpp` uses; include its header if needed.)

- [ ] **Step 5: Per-frame capture inside the loop**

Declare before the loop:

```cpp
std::vector<double> capturePerFrameMs;
std::string captureBackend;
int framesWritten = 0;
if (captureRequest.present)
    capturePerFrameMs.reserve(static_cast<size_t>(playRequest.playTo));
```

Insert AFTER the per-object transform loop and BEFORE the existing `frameEnd` timing line (so S3's `perFrameMs` now includes capture time when capture is on — the capture split makes the non-capture share derivable; when capture is absent nothing changes):

```cpp
if (captureRequest.present)
{
    const auto captureStart = std::chrono::steady_clock::now();
    SetCameraFromFrame(captureView, track.cameraFrames[static_cast<size_t>(frameIndex - 1)]);
    const ON_UUID appliedMode = CurrentDisplayModeId(captureView);
    if (ON_UuidCompare(appliedMode, captureModeId) != 0)
        return FailureResult("display_mode_mismatch",
            {{"frameIndex", frameIndex},
             {"requested", DisplayModeToJson(captureModeId)},
             {"applied", DisplayModeToJson(appliedMode)}});
    captureView->Redraw();

    wchar_t frameName[32] = {};
    swprintf_s(frameName, L"frame_%04d.png", frameIndex);
    const fs::path framePath = captureRequest.framesDir / frameName;
    try
    {
        const DirectorCaptureResult captureResult =
            CaptureViewToPng(pDoc, captureView, captureRequest.width,
                             captureRequest.height, framePath);
        captureBackend = captureResult.backend;
    }
    catch (const DirectorFrameValidationError& ex)
    {
        return FailureResult("capture_failed",
            {{"frameIndex", frameIndex}, {"message", ex.what()}});
    }
    ++framesWritten;
    const auto captureEnd = std::chrono::steady_clock::now();
    capturePerFrameMs.push_back(
        std::chrono::duration<double, std::milli>(captureEnd - captureStart).count());
}
```

- [ ] **Step 6: Response additions**

After the existing `wr.data["timing"]` assignment, add:

```cpp
if (captureRequest.present)
{
    double captureTotal = 0.0;
    nlohmann::json capturePerFrame = nlohmann::json::array();
    for (double ms : capturePerFrameMs) { captureTotal += ms; capturePerFrame.push_back(ms); }
    wr.data["capture"] = {
        {"backend", captureBackend},
        {"runRoot", PathToUtf8(captureRequest.runRoot)},
        {"framesDir", PathToUtf8(captureRequest.framesDir)},
        {"framesWritten", framesWritten},
        {"displayModeRequested", captureRequest.displayMode},
        {"displayModeResolved", DisplayModeToJson(captureModeId)},
        {"timing", {{"captureTotalMs", captureTotal},
                    {"capturePerFrameMs", std::move(capturePerFrame)}}}
    };
}
```

- [ ] **Step 7: Build, commit, STOP FOR REVIEW**

Run: `cmd /c scripts\build-native.bat` — expected: clean build.

```bash
git add src/RookNative
git commit -m "feat(director): worker-play optional capture block — camera, mode readback, per-frame PNG (S4A T2)"
```

Report per the Execution Contract. Reviewer will check the no-capture path against S3 line-by-line.

---

### Task 3: `director_worker_capture.py` — pass orchestration (TDD)

**Files:**
- Create: `mcp_server/src/rook/director_worker_capture.py`
- Test: `mcp_server/tests/test_director_worker_capture.py`

**Interfaces:**
- Consumes: `_load_play_package`, `DirectorWorkerPlayError` from `director_worker_play.py` (import — do not modify that module); `open_package_document`, `get_document`, `norm_path` from `director_worker_common.py`; `canonical_json_text`, `utc_now_iso` from `director_take_package.py`; `_png_size`, `_default_output_root` from `director_video.py`.
- Produces: `async def capture_take(arguments, *, call_native=call_rhino, port=None, now_fn=utc_now_iso) -> dict` and `class DirectorWorkerCaptureError` (Task 4 registers the tool over these).

- [ ] **Step 1: Write the failing tests**

Read `tests/test_director_worker_play.py` FIRST — reuse its fake-native and package-fixture conventions (fixture builder that writes a full hash-consistent package: `scene.3dm`, `prepared.3dm`, `member_map.json`, `resolved_motion.json`, `track.json`, `status.json` with phase `"compiled"` and complete evidence hashes). The capture fake-native must additionally: record every `/director/worker-play` request body; on a capture request, create the requested `framesDir` and write `frame_count` valid PNG files (a real 8-byte-signature + IHDR header helper writing `width×height` — a 33-byte minimal PNG header + zero-length IDAT is fine since only `_png_size` semantics are checked), then return a success envelope with the capture response shape from the Wire Contracts section; support per-test overrides (fail pass N with a given reason, write wrong-dimension PNGs, skip one file, return `alreadyOpen` on open). Point `_default_output_root` at a tmp dir via `ROOK_DIRECTOR_OUTPUT_ROOT` monkeypatch in every test.

Tests (25):

1. `test_rejects_non_dict_arguments` — `capture_take("x")` → `invalid_input`.
2. `test_unsupported_pass_type_rejected_before_native` — pass `{"type": "depth", ...}` → `unsupported_pass_type`; fake native asserts ZERO calls of any kind.
3. `test_pass_id_validation` — missing / empty / `"Bad ID!"` / duplicate pass_ids → `invalid_input`; no native calls.
4. `test_resolution_validation` — odd width, zero height, missing resolution, non-int → `invalid_input`.
5. `test_display_mode_validation` — missing `display_mode`, empty, `"current"` (and `"CURRENT"`) → `invalid_input` before any native call.
6. `test_package_verification_reuses_play_loader` — tamper `track.json` after fixture build → `package_hash_mismatch` (re-raised through `DirectorWorkerCaptureError`).
7. `test_take_id_required` — remove `take_id` from status.json fixture → `package_invalid`.
8. `test_run_root_layout` — single pass `arctic` → native request `capture.runRoot` ends with `takes/<take_id>/arctic` under the env root and `framesDir` == `runRoot + "/frames"`, both as strings with the platform separator normalized the way the native side expects (use `str(Path(...))`).
9. `test_existing_run_root_fails_early` — pre-create the run root dir → `run_root_exists`, zero native calls for that pass.
10. `test_reset_before_each_pass` — two passes → the fake's recorded open sequence shows a `require_fresh` prepared.3dm open before EACH `/director/worker-play` call (assert order: open, play, open, play).
11. `test_native_request_shape` — full-range request: no `fromFrame`/`playTo` keys sent; `capture` block has exactly the five keys; `expectedDocumentPath`/`trackPath` point into the package.
12. `test_manifest_json_assembly_compatible` — after one pass, `run_root/manifest.json` validates against `director_video.py`'s identity gate: import `_validate_manifest_identity` and assert it returns `None`; also assert `frames` length == frame_count, entries are `{"frame_index": i, "file": f"frames/frame_{i:04d}.png"}`, `timeline == {"fps": <track fps>, "frame_count": <track frame_count>}`.
13. `test_run_status_complete_written_last` — successful pass: `run_root/status.json` has `state: "complete"` and `manifest.json` exists; fake configured to write one PNG short → status has `state: "failed"` and NO `manifest.json` exists (metadata is written only after verification passes).
14. `test_png_dimension_verification` — fake writes one frame at 640×480 when 1280×720 requested → `pass_output_incomplete`, error message names the frame; run status `"failed"`.
15. `test_missing_frame_detected` — fake skips frame 3 → `pass_output_incomplete`.
16. `test_partial_pass_failure_preserves_prior_evidence` — pass 1 succeeds, pass 2's native call fails `display_mode_missing` → raised error code `display_mode_missing`, `to_data()` has `failed_pass == "pen"` and `completed_passes == ["arctic"]`; package status.json `evidence.capture_passes` has 2 entries: outcome `complete` then `failed`; pass 1's run root still has `state: "complete"`.
17. `test_failed_native_pass_marks_run_root_failed` — native returns failure AFTER creating the run root (fake creates dir then fails) → run-local `status.json` written with `state: "failed"` and the reason.
18. `test_failed_native_pass_without_run_root` — native fails `wrong_document` without creating the dir → no run-local status written, no crash.
19. `test_known_native_reasons_reraise` — parametrize over `invalid_input`, `output_policy_violation`, `run_root_exists`, `display_mode_missing`, `display_mode_mismatch`, `capture_failed`, `worker_scene_not_pristine` → same code re-raised; unknown reason `"weird"` → `capture_route_failed`.
20. `test_capture_timing_aggregates` — fake returns `capturePerFrameMs: [1.0, 2.0, 3.0, 4.0]` → result pass `capture_ms == {"total": 10.0, "mean": 2.5, "p95": 4.0, "max": 4.0}` (p95 = `sorted[ceil(0.95*n)-1]`).
21. `test_frames_written_mismatch_is_incomplete` — native reports `framesWritten` != frame_count → `pass_output_incomplete` (defense-in-depth even if files exist).
22. `test_package_evidence_append_only` — run capture_take twice (fresh pass_ids) → `evidence.capture_passes` has entries from both runs, prior entries untouched, `pass_index` monotonically increasing.
23. `test_success_payload_shape` — matches the Wire Contracts `capture_take` payload exactly (keys, types), `backend` threaded from native.
24. `test_atomic_metadata_writes` — no `*.staging` residue in the run root after success or failure.
25. `test_bad_capture_timing_shape_is_incomplete` — parametrize the fake's capture
    response over `capturePerFrameMs`: scalar `3.5`, array one short, array with a
    string entry, absent key → each yields `pass_output_incomplete` (never a raw
    `TypeError`/`ValueError`), run-local status `state: "failed"`, no `manifest.json`.

- [ ] **Step 2: Run to verify failure**

Run: `cd mcp_server && python -m pytest tests/test_director_worker_capture.py -v`
Expected: FAIL, `ModuleNotFoundError: rook.director_worker_capture`.

- [ ] **Step 3: Implement the module**

```python
"""Director v3 Slice 4A: multi-pass worker capture orchestrator."""

from __future__ import annotations

import math
import os
import re
from pathlib import Path
from typing import Any

from .bridge import call_rhino
from .director_take_package import canonical_json_text, utc_now_iso
from .director_video import _default_output_root, _png_size, DirectorVideoError
from .director_worker_common import open_package_document
from .director_worker_play import DirectorWorkerPlayError, _load_play_package

KNOWN_NATIVE_REASONS = {
    # S3 set
    "wrong_document", "track_invalid", "track_objects_missing",
    "worker_scene_not_pristine", "playback_drift_detected",
    # S4A additions
    "invalid_input", "output_policy_violation", "run_root_exists",
    "display_mode_missing", "display_mode_mismatch", "capture_failed",
}

_PASS_ID_RE = re.compile(r"^[a-z0-9_-]+$")


class DirectorWorkerCaptureError(Exception):
    def __init__(self, code: str, message: str,
                 extra: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.extra = dict(extra or {})

    def to_data(self) -> dict[str, Any]:
        data = {"code": self.code, "message": str(self)}
        data.update(self.extra)
        return data
```

Validation helpers (each raising `DirectorWorkerCaptureError("invalid_input", ...)` / `unsupported_pass_type`):

```python
def _validate_resolution(arguments: dict[str, Any]) -> tuple[int, int]:
    resolution = arguments.get("resolution")
    if not isinstance(resolution, dict):
        raise DirectorWorkerCaptureError("invalid_input", "resolution must be an object")
    out = []
    for key in ("width", "height"):
        value = resolution.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0 or value % 2:
            raise DirectorWorkerCaptureError(
                "invalid_input", f"resolution.{key} must be a positive even integer")
        out.append(value)
    return out[0], out[1]


def _validate_passes(arguments: dict[str, Any]) -> list[dict[str, str]]:
    passes = arguments.get("passes")
    if not isinstance(passes, list) or not passes:
        raise DirectorWorkerCaptureError("invalid_input", "passes must be a non-empty list")
    seen: set[str] = set()
    validated = []
    for index, item in enumerate(passes):
        if not isinstance(item, dict):
            raise DirectorWorkerCaptureError("invalid_input", f"passes[{index}] must be an object")
        pass_type = item.get("type")
        if pass_type != "display_mode":
            raise DirectorWorkerCaptureError(
                "unsupported_pass_type",
                f"passes[{index}].type {pass_type!r} is not supported in 4A")
        pass_id = item.get("pass_id")
        if not isinstance(pass_id, str) or not _PASS_ID_RE.fullmatch(pass_id):
            raise DirectorWorkerCaptureError(
                "invalid_input", f"passes[{index}].pass_id must match ^[a-z0-9_-]+$")
        if pass_id in seen:
            raise DirectorWorkerCaptureError(
                "invalid_input", f"duplicate pass_id: {pass_id}")
        seen.add(pass_id)
        display_mode = item.get("display_mode")
        if (not isinstance(display_mode, str) or not display_mode.strip()
                or display_mode.strip().lower() == "current"):
            raise DirectorWorkerCaptureError(
                "invalid_input",
                f"passes[{index}].display_mode must name a concrete display mode")
        validated.append({"pass_id": pass_id, "display_mode": display_mode})
    return validated
```

Run metadata + verification (atomic staging like S1–S3: write `<name>.staging`, `os.replace`):

```python
def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    staging = path.parent / f"{path.name}.staging"
    staging.write_text(canonical_json_text(payload), encoding="utf-8")
    os.replace(staging, path)


def _write_run_manifest(run_root: Path, *, run_id: str, frame_count: int,
                        width: int, height: int, fps: float) -> None:
    _write_json_atomic(run_root / "manifest.json", {
        "schema_version": 1,
        "director_version": "slice1",  # assembly identity shim — spec Decision 6
        "run_id": run_id,
        "frame_count": frame_count,
        "resolution": {"width": width, "height": height},
        "timeline": {"fps": fps, "frame_count": frame_count},
        "frames": [
            {"frame_index": i, "file": f"frames/frame_{i:04d}.png"}
            for i in range(1, frame_count + 1)
        ],
    })


def _write_run_status(run_root: Path, *, state: str, now_fn,
                      detail: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {"state": state, "written_at_utc": now_fn()}
    payload.update(detail or {})
    _write_json_atomic(run_root / "status.json", payload)


def _verify_frames(frames_dir: Path, frame_count: int,
                   width: int, height: int) -> None:
    for i in range(1, frame_count + 1):
        frame = frames_dir / f"frame_{i:04d}.png"
        if not frame.is_file() or frame.stat().st_size == 0:
            raise DirectorWorkerCaptureError(
                "pass_output_incomplete", f"missing or empty frame: {frame.name}")
        try:
            observed = _png_size(frame)
        except DirectorVideoError as exc:
            raise DirectorWorkerCaptureError(
                "pass_output_incomplete", f"unparsable PNG {frame.name}: {exc}") from exc
        if observed != (width, height):
            raise DirectorWorkerCaptureError(
                "pass_output_incomplete",
                f"{frame.name} is {observed[0]}x{observed[1]}, expected {width}x{height}")


def _capture_ms_summary(per_frame: list[float]) -> dict[str, float]:
    if not per_frame:
        return {"total": 0.0, "mean": 0.0, "p95": 0.0, "max": 0.0}
    ordered = sorted(per_frame)
    p95_index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "total": sum(per_frame),
        "mean": sum(per_frame) / len(per_frame),
        "p95": ordered[p95_index],
        "max": ordered[-1],
    }
```

Native call (own copy — `director_worker_play._call_worker_play` hardcodes the S3 reason set and error class; 15 duplicated lines beat modifying a frozen module):

```python
async def _call_worker_play_capture(call_native, request: dict[str, Any],
                                    port: int | None) -> dict[str, Any]:
    envelope = await call_native("/director/worker-play", "POST", request, port=port)
    if not isinstance(envelope, dict) or not envelope.get("success"):
        detail = envelope.get("data") if isinstance(envelope, dict) else envelope
        reason = detail.get("reason") if isinstance(detail, dict) else None
        if reason in KNOWN_NATIVE_REASONS:
            raise DirectorWorkerCaptureError(reason, str(detail))
        raise DirectorWorkerCaptureError(
            "capture_route_failed", f"/director/worker-play failed: {detail}")
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise DirectorWorkerCaptureError(
            "capture_route_failed", "/director/worker-play returned no data object")
    return data
```

Package-evidence append (mirror `_append_play_run`):

```python
def _append_capture_pass(root: Path, status: dict[str, Any],
                         entry: dict[str, Any], now_fn) -> dict[str, Any]:
    evidence = dict(status.get("evidence") or {})
    capture_passes = list(evidence.get("capture_passes") or [])
    entry = dict(entry)
    entry["pass_index"] = len(capture_passes)
    capture_passes.append(entry)
    evidence["capture_passes"] = capture_passes
    status = dict(status)
    status["heartbeat_utc"] = now_fn()
    status["evidence"] = evidence
    (root / "status.json").write_text(canonical_json_text(status), encoding="utf-8")
    return status
```

The orchestrator:

```python
async def capture_take(arguments: dict[str, Any], *, call_native=call_rhino,
                       port: int | None = None,
                       now_fn=utc_now_iso) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise DirectorWorkerCaptureError("invalid_input", "capture request must be an object")
    passes = _validate_passes(arguments)
    width, height = _validate_resolution(arguments)

    try:
        pkg = _load_play_package(arguments.get("package_root"))
    except DirectorWorkerPlayError as exc:
        raise DirectorWorkerCaptureError(exc.code, str(exc)) from exc
    root: Path = pkg["root"]
    status = pkg["status"]

    take_id = status.get("take_id")
    if not isinstance(take_id, str) or not take_id.strip():
        raise DirectorWorkerCaptureError("package_invalid", "package status.json has no take_id")
    track = pkg["track"]
    fps = track.get("fps")
    frame_count = track.get("frame_count")
    if not isinstance(fps, (int, float)) or isinstance(fps, bool) or fps <= 0:
        raise DirectorWorkerCaptureError("package_invalid", "track.json has no valid fps")
    if not isinstance(frame_count, int) or frame_count <= 0:
        raise DirectorWorkerCaptureError("package_invalid", "track.json has no valid frame_count")

    output_root = _default_output_root() / "takes" / take_id
    completed: list[dict[str, Any]] = []

    for pass_spec in passes:
        pass_id = pass_spec["pass_id"]
        run_root = output_root / pass_id
        frames_dir = run_root / "frames"

        def _fail(code: str, message: str, *, mark_failed: bool) -> None:
            if mark_failed and run_root.is_dir():
                _write_run_status(run_root, state="failed", now_fn=now_fn,
                                  detail={"reason": code, "message": message})
            status_entry = {
                "pass_id": pass_id, "display_mode": pass_spec["display_mode"],
                "captured_at_utc": now_fn(), "run_root": str(run_root),
                "outcome": "failed", "reason": code,
            }
            _append_capture_pass(root, status, status_entry, now_fn)
            raise DirectorWorkerCaptureError(code, message, extra={
                "failed_pass": pass_id,
                "completed_passes": [p["pass_id"] for p in completed],
            })

        if run_root.exists():
            _fail("run_root_exists", f"run root already exists: {run_root}",
                  mark_failed=False)

        try:
            await open_package_document(
                call_native, root, root / "prepared.3dm", port=port,
                error_cls=DirectorWorkerCaptureError, mode="require_fresh")
        except DirectorWorkerCaptureError as exc:
            _fail(exc.code, str(exc), mark_failed=False)

        request = {
            "expectedDocumentPath": str(root / "prepared.3dm"),
            "trackPath": str(root / "track.json"),
            "capture": {
                "runRoot": str(run_root),
                "framesDir": str(frames_dir),
                "displayMode": pass_spec["display_mode"],
                "width": width,
                "height": height,
            },
        }
        try:
            play_data = await _call_worker_play_capture(call_native, request, port)
        except DirectorWorkerCaptureError as exc:
            _fail(exc.code, str(exc), mark_failed=True)

        capture_data = play_data.get("capture") or {}
        frames_written = capture_data.get("framesWritten")
        raw_per_frame = (capture_data.get("timing") or {}).get("capturePerFrameMs")
        try:
            if frames_written != frame_count:
                raise DirectorWorkerCaptureError(
                    "pass_output_incomplete",
                    f"native reported {frames_written} frames, expected {frame_count}")
            # Timing contract: numeric array, one entry per frame. A scalar, short
            # array, or non-numeric entry is a broken native response — it must take
            # the failed-status path, never leak a raw TypeError past the run root.
            if (not isinstance(raw_per_frame, list)
                    or len(raw_per_frame) != frame_count
                    or not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                               for v in raw_per_frame)):
                raise DirectorWorkerCaptureError(
                    "pass_output_incomplete",
                    "native capture timing is not a numeric array of length "
                    f"{frame_count}: {type(raw_per_frame).__name__}")
            _verify_frames(frames_dir, frame_count, width, height)
        except DirectorWorkerCaptureError as exc:
            _fail(exc.code, str(exc), mark_failed=True)
        per_frame = [float(v) for v in raw_per_frame]

        run_id = f"{take_id}-{pass_id}"
        _write_run_manifest(run_root, run_id=run_id, frame_count=frame_count,
                            width=width, height=height, fps=float(fps))
        capture_ms = _capture_ms_summary(per_frame)
        _write_run_status(run_root, state="complete", now_fn=now_fn, detail={
            "run_id": run_id, "frame_count": frame_count,
            "capture_ms": capture_ms, "drift": play_data.get("drift"),
        })

        pass_result = {
            "pass_id": pass_id,
            "display_mode": pass_spec["display_mode"],
            "run_root": str(run_root),
            "frames_written": frame_count,
            "backend": capture_data.get("backend"),
            "capture_ms": capture_ms,
            "drift": play_data.get("drift"),
        }
        status = _append_capture_pass(root, status, {
            "pass_id": pass_id, "display_mode": pass_spec["display_mode"],
            "captured_at_utc": now_fn(), "run_root": str(run_root),
            "frames_written": frame_count, "backend": capture_data.get("backend"),
            "outcome": "complete", "capture_ms": capture_ms,
            "drift": play_data.get("drift"),
        }, now_fn)
        completed.append(pass_result)

    return {
        "package_root": str(root),
        "take_id": take_id,
        "output_root": str(output_root),
        "passes": completed,
    }
```

- [ ] **Step 4: Run the full covering set**

Run: `cd mcp_server && python -m pytest tests/test_director_worker_capture.py tests/test_director_worker_play.py tests/test_director_worker_compile.py tests/test_director_worker_common.py tests/test_director_worker_prepare.py -v`
Expected: ALL PASS; the four S2/S3 files unmodified.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/director_worker_capture.py mcp_server/tests/test_director_worker_capture.py
git commit -m "feat(director): multi-pass worker capture orchestrator with assembly-compatible run roots (S4A T3)"
```

**STOP FOR REVIEW.**

---

### Task 4: `rhino_director_capture_take` MCP tool + classification

**Files:**
- Modify: `mcp_server/src/rook/server.py`, `mcp_server/src/rook/targeting.py`, `mcp_server/src/rook/agent/tool_groups.py`, `mcp_server/src/rook/mcp_tool_profiles.py` (if the rg sweep shows it), `mcp_server/tests/test_server_tool_profiles.py` (pinned counts), plus every other site the sweep finds
- Test: existing pinned-count tests (updated), plus `tests/test_director_worker_capture.py` (unchanged)

- [ ] **Step 1: Sweep for every registration/classification site**

Run: `rg -n "rhino_director_worker_play" mcp_server/src mcp_server/tests`

Mirror EVERY hit for `rhino_director_capture_take`: tool definition in `server.py` (schema mirroring `rhino_director_worker_play`'s argument style: `package_root` string required; `passes` array required — items object with `type`/`display_mode`/`pass_id` strings; `resolution` object required with integer `width`/`height`), dispatch to `director_worker_capture.capture_take` with the same error-envelope wrapping the play tool uses (catch `DirectorWorkerCaptureError`, return `to_data()` in the error payload — the `extra` fields ride along), classification in `targeting.py` `_ALL_KNOWN_TOOLS` (MUTATE — NOT `_RHINO_READ_TOOLS`), `agent/tool_groups.py` director group, and any profile lists. The tool description must state it is DESTRUCTIVE to the worker document and writes under the director output root.

- [ ] **Step 2: Bump pinned counts 441 → 442**

Grep the pinned set NAMES (not the numbers) per `project_mcp_tool_exposure_profiles`: `rg -n "441" mcp_server/tests` and fix each pin that counts the full tool surface; verify with the test run, not arithmetic.

- [ ] **Step 3: Run the covering set + commit**

Run: `cd mcp_server && python -m pytest tests/test_server_tool_profiles.py tests/test_director_worker_capture.py -v`
Expected: ALL PASS.

```bash
git add mcp_server
git commit -m "feat(director): rhino_director_capture_take MCP tool, pins 441->442 (S4A T4)"
```

**STOP FOR REVIEW.**

---

### Task 5: Live gates A–D (env-gated file; controller runs them)

**Files:**
- Create: `mcp_server/tests/test_director_worker_capture_live.py`

**Interfaces:**
- Consumes: everything shipped in Tasks 1–4, `director_take_package.package_take`, `director_worker_prepare.prepare_take`, `director_worker_compile.compile_take` (the S1–S3 pipeline), plus direct `httpx` against the discovered native port (the sanctioned live-test exception to MCP-only).

- [ ] **Step 1: Write the live gate file**

Read `tests/test_director_worker_play_live.py` FIRST and mirror its structure exactly: env-var gating, port discovery, scratch-document fixture creation via native routes, try/finally save + block-delete cleanup, and its helper for building a small animated take (package → prepare → compile). Gates (each `@pytest.mark.skipif` unless its env var is set):

- `test_gate_a_single_pass_to_video` (`ROOK_S4A_CAPTURE=1`): build a 3-object, 24-frame take with translate + rotate-about-pivot + non-uniform-scale motion in a scratch doc; `capture_take` with one pass (`pass_id="arctic"`, a display mode read from `ROOK_S4A_MODE` env, default `"Arctic"`); assert 24 verified frames, run status `complete`; then call the existing video-assemble route against the run root (`run_root`, `frames_dir`, `output_path=run_root/videos/take.mp4`, `frame_count`, `fps` from the track, `width`/`height`, `codec="h264"`, `container="mp4"`, `input_pattern="frame_%04d.png"`, `start_number=1`) and assert a non-empty MP4 exists. **This is the first v3 video.**
- `test_gate_b_two_pass_fidelity` (`ROOK_S4A_CAPTURE=1`): two passes (`arctic` + `pen`, modes from `ROOK_S4A_MODE`/`ROOK_S4A_MODE_B` env, defaults `"Arctic"`/`"Pen"`); assert both run roots complete; load frame 12 of each pass and assert the two files' `sha256` digests differ (same geometry + camera + dimensions, different display mode — identical bytes would mean the mode was not applied). Document in a comment that visual encoding fidelity (layer colors surviving, mode look correct) is the human's review step in the gate protocol, on the printed frame paths.
- `test_gate_c_display_mode_fail_hard` (`ROOK_S4A_CAPTURE=1`): request pass with `display_mode="RookNoSuchMode_S4A"` → `DirectorWorkerCaptureError` code `display_mode_missing`; assert the run root exists with `status.json state: "failed"` and `frames/` contains ZERO files.
- `test_gate_d_capture_throughput` (`ROOK_S4A_THROUGHPUT=1`): 300-object synthetic take (mirror Gate D's S3 builder), 60 frames, one pass; report (print) `capture_ms` summary and per-frame mean vs the S3 19.2 ms/frame transform baseline; no hard threshold — this gate MEASURES (the number feeds the parent spec's open question 1).

**Output-root rule (AMENDED after Task 5 round 1 — the original instruction was a
plan bug):** do NOT set `ROOK_DIRECTOR_OUTPUT_ROOT` in the live-gate process. The
env var only affects the pytest process, while native `GetAllowedDirectorRoot()`
reads the RHINO process environment — a pytest-local tmp root makes every capture
call fail `output_policy_violation` before any frame plays. Live gates instead use
the SAME root both sides resolve by default: derive
`output_root = director_video._default_output_root()` (real
`%LOCALAPPDATA%/Rook/rookvision_director` unless Rhino itself was launched with the
env var — note this assumption in a comment). Uniqueness comes from uuid-suffixed
`take_id`s. Cleanup targets ONLY `<output_root>/takes/<take_id>` (never the shared
director root — it holds real user outputs); Gate A's take dir survives cleanup
under `ROOK_S4A_KEEP_OUTPUT=1` with the MP4 path printed for human review. Gate C
computes its expected run root from the derived output root. (The Task 3 unit
tests keep their env pinning — the fake native runs in-process, where it is
correct.)

- [ ] **Step 2: Run the file WITHOUT env vars**

Run: `cd mcp_server && python -m pytest tests/test_director_worker_capture_live.py -v`
Expected: all SKIPPED (no live Rhino in CI; controller runs the real gates).

- [ ] **Step 3: Commit**

```bash
git add mcp_server/tests/test_director_worker_capture_live.py
git commit -m "test(director): S4A live gates A-D — first-video, two-pass fidelity, fail-hard, throughput (S4A T5)"
```

**STOP FOR REVIEW.** The controller + human then run the deploy ritual and gates; findings route back as fix cycles.

---

## Plan Self-Review (completed at authoring)

- **Spec coverage:** Decision 1 → Task 2 (steps 2–6) + frozen no-capture rule; Decision 2 → Task 2 step 4 + Task 3 layout/collision; Decision 3 → Task 2 step 3/5 (1-based pairing pinned in code); Decision 4 → Task 1 step 1 + Task 2 step 4/5 readback; Decision 5 → Task 1 steps 2–3 + live proof at step 6; Decision 6 → Task 3 + Task 4; error taxonomy → Global Constraints + tests 19; unit gates 1–8 → tests mapped in Task 3 (gate 1 = frozen S3 suites + no-capture parse path untouched, 2→T2 code + T3 test 9, 3→T2 step 3 + native contract, 4→test 2, 5→tests 16/17, 6→test 12, 7→T2 step 1 + tests 3/4/5, 8→test 20); live gates A–D → Task 5.
- **Placeholder scan:** clean — every code step carries the code; the single deliberately open point (SDK API selection) is spec-mandated as an investigation with a complete fallback implementation provided.
- **Type consistency:** `capture_take`/`DirectorWorkerCaptureError`/`KNOWN_NATIVE_REASONS` names match between Tasks 3–5; native `CaptureRequest`/`CaptureViewToPng`/`DirectorCaptureResult` match between Tasks 1–2; wire keys match the Wire Contracts section throughout.
