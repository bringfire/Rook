# Director Pose Bbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove whether object-level `GetTightBoundingBox()` is the correct Director pose bbox primitive for the minimized Pearson restore failure, then wire it consistently through Director only if the hard gate passes.

**Architecture:** The slice has two checkpoints. First, add native evidence comparing raw cached `BoundingBox()` against object-level `GetTightBoundingBox()` for each object phase while leaving restore behavior unchanged. After a live minimized Pearson probe and review gate, add `DirectorObjectPoseBbox()` and use it consistently for Director object-states, source validation, phase evidence, and restore verification.

**Tech Stack:** Rhino 8 C++ SDK, RookNative free-function handlers, `nlohmann::json`, Python pytest source tests, live Rhino/RookNative probe through existing Director Python helpers.

---

## File Structure

Modify:

- `src/RookNative/Handlers/DirectorFrame.h`
  - Declare `DirectorPoseBboxResult` and `DirectorObjectPoseBbox()` in Checkpoint 2 only.

- `src/RookNative/Handlers/DirectorFrame.cpp`
  - Checkpoint 1: add raw-vs-tight bbox diagnostic evidence and phase-expected bbox comparison.
  - Checkpoint 2: add `DirectorObjectPoseBbox()` and use it in validation/evidence/restore.

- `src/RookNative/Handlers/DirectorHandler.cpp`
  - Checkpoint 2: use `DirectorObjectPoseBbox()` in `SerializeObjectState()` and include native `bbox_method` response metadata.

- `mcp_server/tests/test_director_native_source.py`
  - Add source tests that pin the probe evidence, hard gate shape, shared helper, and scope guards.

Do not modify:

- `mcp_server/src/rook/**/*.py`
- `src/Rook/Services/Vision/CanvasDirector/**/*`
- global measure/selection/block/scene graph bbox handlers
- tolerance constants

## Safety Rules

- Do not change `dirty_partial_state` behavior during Checkpoint 1.
- Do not proceed to Checkpoint 2 until the live minimized Pearson probe satisfies the hard gate.
- Do not add sleeps, redraw-based waits, bbox tolerance changes, snapshot restore, or CanvasDirector changes.
- If the live probe is ambiguous, stop and report the evidence.
- Every commit must pass `git diff --check`.
- Native deploy uses `scripts\deploy-local-testing.ps1 -NativeOnly`; Rhino must be closed for deploy.

## Task 1: Red Source Tests For Bbox Method Probe

**Files:**
- Modify: `mcp_server/tests/test_director_native_source.py`

- [ ] **Step 1: Add probe source tests**

Append these tests after `test_director_instance_restore_live_repro_is_scratch_and_two_frame()`:

```python
def test_director_pose_bbox_probe_records_raw_tight_and_expected_phase_bboxes():
    source = DIRECTOR_FRAME.read_text(encoding="utf-8")
    phase_body = _extract_function(source, "nlohmann::json NativeObjectPhaseEvidence")
    expected_body = _extract_function(source, "ON_BoundingBox TransformBoundingBoxByCorners")
    apply_body = _extract_function(source, "void DirectorObjectPoseGuard::Apply")
    restore_body = _extract_function(source, "bool DirectorObjectPoseGuard::Restore")

    for token in [
        '"raw_bbox"',
        '"raw_bbox_valid"',
        '"raw_bbox_delta_min"',
        '"raw_bbox_delta_max"',
        '"raw_bbox_max_delta"',
        '"tight_bbox"',
        '"tight_bbox_valid"',
        '"tight_bbox_delta_min"',
        '"tight_bbox_delta_max"',
        '"tight_bbox_max_delta"',
        '"phase_expected_bbox"',
        '"bbox_tolerance"',
        '"bbox_tolerance_policy"',
        "GetTightBoundingBox",
        "BoundingBox()",
    ]:
        assert token in phase_body

    assert "ExpectedPhaseBbox(m_objects[i], ON_Xform::IdentityTransformation)" in apply_body
    assert "ExpectedPhaseBbox(m_objects[i], m_objects[i].delta)" in apply_body
    assert "ExpectedPhaseBbox(object, object.delta)" in restore_body
    assert "ExpectedPhaseBbox(object, ON_Xform::IdentityTransformation)" in restore_body
    assert "transformed.Union(xform * corner)" in expected_body
    assert "corner * xform" not in expected_body
    assert "BboxDeltaToJson" in phase_body
    assert "BboxMaxDelta" in phase_body


def test_director_pose_bbox_probe_keeps_raw_restore_verifier_until_gate():
    source = DIRECTOR_FRAME.read_text(encoding="utf-8")
    restore_body = _extract_function(source, "bool DirectorObjectPoseGuard::Restore")

    assert "restoredObj->BoundingBox()" in restore_body
    assert "DirectorObjectPoseBbox" not in restore_body
    assert "GetTightBoundingBox" in source
    assert "kDirectorRestoreModelScaleFactor" not in source
    assert "kDirectorRestoreBboxToleranceCap" not in source
    assert "std::this_thread::sleep" not in source
    assert "Sleep(" not in source
```

- [ ] **Step 2: Run red tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_director_native_source.py::test_director_pose_bbox_probe_records_raw_tight_and_expected_phase_bboxes `
  mcp_server/tests/test_director_native_source.py::test_director_pose_bbox_probe_keeps_raw_restore_verifier_until_gate `
  -q
```

Expected: fail because raw/tight evidence and `ExpectedPhaseBbox` do not exist yet.

- [ ] **Step 3: Commit red tests**

Run:

```powershell
git add mcp_server/tests/test_director_native_source.py
git commit -m "test(director): pin pose bbox probe evidence"
```

## Task 2: Implement Bbox Method Probe Evidence

**Files:**
- Modify: `src/RookNative/Handlers/DirectorFrame.cpp`
- Test: `mcp_server/tests/test_director_native_source.py`

- [ ] **Step 1: Add bbox evidence helpers**

In `src/RookNative/Handlers/DirectorFrame.cpp`, inside the anonymous namespace after `BboxMaxDelta`, add:

```cpp
ON_BoundingBox TransformBoundingBoxByCorners(const ON_BoundingBox& bbox, const ON_Xform& xform)
{
    ON_BoundingBox transformed = ON_BoundingBox::EmptyBoundingBox;
    const ON_3dPoint corners[8] = {
        ON_3dPoint(bbox.m_min.x, bbox.m_min.y, bbox.m_min.z),
        ON_3dPoint(bbox.m_max.x, bbox.m_min.y, bbox.m_min.z),
        ON_3dPoint(bbox.m_min.x, bbox.m_max.y, bbox.m_min.z),
        ON_3dPoint(bbox.m_max.x, bbox.m_max.y, bbox.m_min.z),
        ON_3dPoint(bbox.m_min.x, bbox.m_min.y, bbox.m_max.z),
        ON_3dPoint(bbox.m_max.x, bbox.m_min.y, bbox.m_max.z),
        ON_3dPoint(bbox.m_min.x, bbox.m_max.y, bbox.m_max.z),
        ON_3dPoint(bbox.m_max.x, bbox.m_max.y, bbox.m_max.z)
    };

    for (const ON_3dPoint& corner : corners)
        transformed.Union(xform * corner);

    return transformed;
}

ON_BoundingBox ExpectedPhaseBbox(const FrameObjectTransform& object, const ON_Xform& phaseXform)
{
    return TransformBoundingBoxByCorners(object.sourceBbox, phaseXform);
}

void AddObservedBboxComparison(
    nlohmann::json& phase,
    const std::string& prefix,
    const ON_BoundingBox& expected,
    const ON_BoundingBox& observed,
    bool observedValid)
{
    phase[prefix + "_bbox_valid"] = observedValid;
    if (!observedValid)
    {
        phase[prefix + "_bbox"] = nullptr;
        phase[prefix + "_bbox_delta_min"] = nullptr;
        phase[prefix + "_bbox_delta_max"] = nullptr;
        phase[prefix + "_bbox_max_delta"] = nullptr;
        return;
    }

    phase[prefix + "_bbox"] = BoundingBoxToDirectorJson(observed);
    if (!expected.IsValid())
    {
        phase[prefix + "_bbox_delta_min"] = nullptr;
        phase[prefix + "_bbox_delta_max"] = nullptr;
        phase[prefix + "_bbox_max_delta"] = nullptr;
        return;
    }

    phase[prefix + "_bbox_delta_min"] = BboxDeltaToJson(observed.m_min, expected.m_min);
    phase[prefix + "_bbox_delta_max"] = BboxDeltaToJson(observed.m_max, expected.m_max);
    phase[prefix + "_bbox_max_delta"] = BboxMaxDelta(observed, expected);
}
```

- [ ] **Step 2: Change `NativeObjectPhaseEvidence` signature and body**

Change the signature from:

```cpp
nlohmann::json NativeObjectPhaseEvidence(
    CRhinoDoc* pDoc,
    const FrameObjectTransform& object)
```

to:

```cpp
nlohmann::json NativeObjectPhaseEvidence(
    CRhinoDoc* pDoc,
    const FrameObjectTransform& object,
    const ON_BoundingBox& phaseExpectedBbox)
```

Inside the function, replace:

```cpp
    const ON_BoundingBox bbox = obj->BoundingBox();
    phase["bbox"] = bbox.IsValid() ? BoundingBoxToDirectorJson(bbox) : nlohmann::json(nullptr);
```

with:

```cpp
    phase["phase_expected_bbox"] = phaseExpectedBbox.IsValid()
        ? BoundingBoxToDirectorJson(phaseExpectedBbox)
        : nlohmann::json(nullptr);
    phase["bbox_tolerance"] = DirectorRestoreBboxTolerance();
    phase["bbox_tolerance_policy"] = "pose_bbox_probe_uses_existing_restore_tolerance";

    const ON_BoundingBox rawBbox = obj->BoundingBox();
    const bool rawBboxValid = rawBbox.IsValid();
    phase["bbox"] = rawBboxValid ? BoundingBoxToDirectorJson(rawBbox) : nlohmann::json(nullptr);
    AddObservedBboxComparison(phase, "raw", phaseExpectedBbox, rawBbox, rawBboxValid);

    ON_BoundingBox tightBbox;
    const bool tightBboxValid = obj->GetTightBoundingBox(tightBbox) && tightBbox.IsValid();
    AddObservedBboxComparison(phase, "tight", phaseExpectedBbox, tightBbox, tightBboxValid);
```

In the `if (!obj)` branch, add nulls so missing-object evidence has stable fields:

```cpp
        phase["phase_expected_bbox"] = phaseExpectedBbox.IsValid()
            ? BoundingBoxToDirectorJson(phaseExpectedBbox)
            : nlohmann::json(nullptr);
        phase["bbox_tolerance"] = DirectorRestoreBboxTolerance();
        phase["bbox_tolerance_policy"] = "pose_bbox_probe_uses_existing_restore_tolerance";
        phase["raw_bbox"] = nullptr;
        phase["raw_bbox_valid"] = false;
        phase["raw_bbox_delta_min"] = nullptr;
        phase["raw_bbox_delta_max"] = nullptr;
        phase["raw_bbox_max_delta"] = nullptr;
        phase["tight_bbox"] = nullptr;
        phase["tight_bbox_valid"] = false;
        phase["tight_bbox_delta_min"] = nullptr;
        phase["tight_bbox_delta_max"] = nullptr;
        phase["tight_bbox_max_delta"] = nullptr;
```

- [ ] **Step 3: Pass phase-expected bbox at call sites**

In `DirectorObjectPoseGuard::Apply()`, replace:

```cpp
        detail["phase_before_apply"] = NativeObjectPhaseEvidence(m_doc, m_objects[i]);
```

with:

```cpp
        detail["phase_before_apply"] = NativeObjectPhaseEvidence(
            m_doc,
            m_objects[i],
            ExpectedPhaseBbox(m_objects[i], ON_Xform::IdentityTransformation));
```

Replace:

```cpp
        detail["phase_after_apply"] = NativeObjectPhaseEvidence(m_doc, m_objects[i]);
```

with:

```cpp
        detail["phase_after_apply"] = NativeObjectPhaseEvidence(
            m_doc,
            m_objects[i],
            ExpectedPhaseBbox(m_objects[i], m_objects[i].delta));
```

In `DirectorObjectPoseGuard::Restore()`, replace:

```cpp
        detail["phase_before_restore"] = NativeObjectPhaseEvidence(m_doc, object);
```

with:

```cpp
        detail["phase_before_restore"] = NativeObjectPhaseEvidence(
            m_doc,
            object,
            m_applied[static_cast<size_t>(i)]
                ? ExpectedPhaseBbox(object, object.delta)
                : ExpectedPhaseBbox(object, ON_Xform::IdentityTransformation));
```

Replace both existing `phase_after_restore` assignments with:

```cpp
            detail["phase_after_restore"] = NativeObjectPhaseEvidence(
                m_doc,
                object,
                ExpectedPhaseBbox(object, ON_Xform::IdentityTransformation));
```

and:

```cpp
        detail["phase_after_restore"] = NativeObjectPhaseEvidence(
            m_doc,
            object,
            transformedBack
                ? ExpectedPhaseBbox(object, ON_Xform::IdentityTransformation)
                : ExpectedPhaseBbox(object, object.delta));
```

- [ ] **Step 4: Update existing phase-ordering source test**

In `test_director_transform_diagnostics_do_not_delay_applied_bookkeeping`, update the exact old phase-evidence call assertions so the test continues to check ordering without depending on the old two-argument signature.

Replace:

```python
    phase_after_apply_index = apply_body.index('detail["phase_after_apply"] = NativeObjectPhaseEvidence(m_doc, m_objects[i]);')
```

with:

```python
    phase_after_apply_index = apply_body.index('detail["phase_after_apply"] = NativeObjectPhaseEvidence')
```

Replace:

```python
    phase_after_restore_index = not_applied_branch.index('detail["phase_after_restore"] = NativeObjectPhaseEvidence(m_doc, object);')
```

with:

```python
    phase_after_restore_index = not_applied_branch.index('detail["phase_after_restore"] = NativeObjectPhaseEvidence')
```

- [ ] **Step 5: Run source tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_director_native_source.py mcp_server/tests/test_director_replay_native_source.py -q
```

Expected: pass.

- [ ] **Step 6: Verify no forbidden scope drift**

Run:

```powershell
git diff --check
$diff = git diff --name-only HEAD | Select-String -Pattern 'canvas_director|CanvasDirector|MeasureHandler|SelectionHandler|BlocksHandler|SceneGraphHandler' -CaseSensitive:$false
if ($diff) { throw "Forbidden files changed:`n$diff" }
```

Expected: no output from `git diff --check`; no forbidden file matches.

- [ ] **Step 7: Commit probe implementation**

Run:

```powershell
git add src/RookNative/Handlers/DirectorFrame.cpp mcp_server/tests/test_director_native_source.py
git commit -m "fix(director): compare raw and tight pose bboxes"
```

## Task 3: Build, Deploy, And Run The Minimized Pearson Probe Gate

**Files:**
- No source edits expected.
- Build/deploy artifacts under `src/RookNative/bin/Debug/x64/`.

- [ ] **Step 1: Run source tests before native build**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_director_native_source.py mcp_server/tests/test_director_replay_native_source.py -q
```

Expected: pass.

- [ ] **Step 2: Close Rhino**

If Rhino is open, ask the user to close it cleanly before deploy. Do not kill Rhino unless the user explicitly asks.

Verify:

```powershell
Get-Process | Where-Object { $_.ProcessName -match '^(Rhino|Rhinoceros)$' }
```

Expected: no running Rhino process.

- [ ] **Step 3: Native-only deploy**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -NativeOnly
```

Expected: `Native-only deploy complete.`

- [ ] **Step 4: Restart Rhino with Pearson file**

Ask the user to open:

```text
C:\Users\bring\OneDrive\Desktop\Pearson\ANIMATION\V2\Axon_Pearson_Experimental_TESTING.3dm
```

Do not open Grasshopper for this minimized native probe. This diagnostic only needs the Pearson Rhino file and an active perspective model view.

- [ ] **Step 5: Bind MCP to the live Pearson Rhino instance**

Use the Rook MCP tools:

```text
rhino_instances
rhino_set_active_instance with the native Rook port reported for the Pearson document
rhino_ping
```

Expected: `rhino_ping` returns `"pong"` and the active document is the Pearson file.

- [ ] **Step 6: Run the minimized Pearson probe**

Run this exact command, replacing `PORT = 62574` only if `rhino_instances` reports a different native Rook port:

```powershell
@'
import asyncio, json, os
from datetime import datetime
from pathlib import Path
from rook import director

OBJECT_ID = "a28cbdb5-51fa-46b2-b18b-ab880b54ded7"
PORT = 62574
TINY_Z = 0.628483

def director_output_root() -> Path:
    configured = os.environ.get("ROOK_DIRECTOR_OUTPUT_ROOT")
    if configured:
        return Path(configured).resolve()
    return (Path(os.environ["LOCALAPPDATA"]) / "Rook" / "rookvision_director").resolve()

def source_state(state: dict) -> dict:
    return {
        "bbox_min": state["bbox_min"],
        "bbox_max": state["bbox_max"],
        "validation_strength": state["validation_strength"],
        "state_hash": state.get("state_hash"),
    }

def object_transform(object_id: str, state: dict, matrix: list[list[float]]) -> dict:
    return {
        "object_id": object_id,
        "source_state": source_state(state),
        "transform": matrix,
    }

def method_summary(phase: dict) -> dict:
    return {
        "object_type": phase.get("object_type"),
        "instance_xform": phase.get("instance_xform"),
        "phase_expected_bbox": phase.get("phase_expected_bbox"),
        "bbox_tolerance": phase.get("bbox_tolerance"),
        "bbox_tolerance_policy": phase.get("bbox_tolerance_policy"),
        "raw_bbox_valid": phase.get("raw_bbox_valid"),
        "raw_bbox": phase.get("raw_bbox"),
        "raw_bbox_delta_min": phase.get("raw_bbox_delta_min"),
        "raw_bbox_delta_max": phase.get("raw_bbox_delta_max"),
        "raw_bbox_max_delta": phase.get("raw_bbox_max_delta"),
        "tight_bbox_valid": phase.get("tight_bbox_valid"),
        "tight_bbox": phase.get("tight_bbox"),
        "tight_bbox_delta_min": phase.get("tight_bbox_delta_min"),
        "tight_bbox_delta_max": phase.get("tight_bbox_delta_max"),
        "tight_bbox_max_delta": phase.get("tight_bbox_max_delta"),
    }

async def main():
    state = await director.call_rhino(
        "/director/object-states", "POST", {"object_ids": [OBJECT_ID]}, port=PORT
    )
    if not state.get("success"):
        raise SystemExit(json.dumps({"object_state_error": state}, indent=2))
    obj_state = state["data"]["objects"][0]

    view = await director.call_rhino(
        "/director/view-state", "POST", {"source": {"kind": "active_view"}}, port=PORT
    )
    if not view.get("success"):
        raise SystemExit(json.dumps({"view_state_error": view}, indent=2))
    camera = view["data"]["camera"]
    if camera.get("projection") != "perspective":
        raise SystemExit(json.dumps({"error": "active_view_not_perspective", "camera": camera}, indent=2))

    run_id = "pearson_pose_bbox_probe_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    result = await director.run_compiled_track({
        "run_id": run_id,
        "output_root": str(director_output_root()),
        "resolution": {"width": 320, "height": 180},
        "display": {"mode": "Rendered"},
        "track": {
            "transform_semantics": "absolute_from_source",
            "fps": 24,
            "frame_count": 2,
            "animated_object_ids": [OBJECT_ID],
            "camera_frames": [
                {"frame_index": 1, "camera": camera},
                {"frame_index": 2, "camera": camera},
            ],
            "object_frames": [
                {"frame_index": 1, "object_transforms": [object_transform(OBJECT_ID, obj_state, director.identity_matrix())]},
                {"frame_index": 2, "object_transforms": [object_transform(OBJECT_ID, obj_state, director.translation_matrix([0.0, 0.0, TINY_Z]))]},
            ],
        },
        "compile_provenance": {
            "probe": "pearson_pose_bbox_probe",
            "object_id": OBJECT_ID,
            "tiny_z": TINY_Z,
        },
    }, port=PORT)

    run_root = Path(result["run_root"])
    rows = [
        json.loads(line)
        for line in (run_root / "logs" / "frame_evidence.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    summary = {
        "pearson_pose_bbox_probe": {
            "result": result,
            "run_root": str(run_root),
            "object_state": obj_state,
            "frames": [
                {
                    "frame_index": row.get("frame_index"),
                    "success": row.get("success"),
                    "dirty_partial_state": row.get("dirty_partial_state"),
                    "error": row.get("error"),
                    "details": [
                        {
                            "object_id": detail.get("object_id"),
                            "restored": detail.get("restored"),
                            "restore_error": detail.get("restore_error"),
                            "bbox_max_delta": detail.get("bbox_max_delta"),
                            "phase_before_apply": method_summary(detail.get("phase_before_apply", {})),
                            "phase_after_apply": method_summary(detail.get("phase_after_apply", {})),
                            "phase_before_restore": method_summary(detail.get("phase_before_restore", {})),
                            "phase_after_restore": method_summary(detail.get("phase_after_restore", {})),
                        }
                        for detail in row.get("objects", {}).get("details", [])
                    ],
                }
                for row in rows
            ],
        }
    }
    summary_path = run_root / "logs" / "pearson_pose_bbox_probe_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))

asyncio.run(main())
'@ | mcp_server\.venv\Scripts\python.exe -
```

Expected: the command prints `pearson_pose_bbox_probe` and writes `logs\pearson_pose_bbox_probe_summary.json`.

- [ ] **Step 7: Hard gate review**

Stop here. Do not implement Task 4 until a lead reviewer confirms all gate conditions:

```text
raw BoundingBox reproduces wrong X/Y in frame 2
tight GetTightBoundingBox is valid in all four phases
tight bbox matches the pure-translation phase-expected bbox within 1e-4 in all four phases
InstanceXform sequence is source, Z 0.628483, Z 0.628483, source
no missing/deleted object, failed transform, invalid bbox, or other hard failure was masked
```

If any gate condition is false, stop and write a diagnostic note instead of implementing the helper.

## Task 4: Red Source Tests For Director Pose Bbox Helper

**Files:**
- Modify: `mcp_server/tests/test_director_native_source.py`

Run this task only after Task 3 gate is explicitly approved.

- [ ] **Step 1: Add helper source tests**

Append these tests after the probe tests from Task 1:

```python
def test_director_pose_bbox_helper_prefers_tight_with_raw_fallback():
    source = DIRECTOR_FRAME.read_text(encoding="utf-8")
    header = DIRECTOR_FRAME_HEADER.read_text(encoding="utf-8")

    assert "struct DirectorPoseBboxResult" in header
    assert "DirectorPoseBboxResult DirectorObjectPoseBbox(const CRhinoObject& obj);" in header

    helper_body = _extract_function(source, "DirectorPoseBboxResult DirectorObjectPoseBbox")
    helper_index = source.index("DirectorPoseBboxResult DirectorObjectPoseBbox")
    validate_index = source.index("void ValidateFrameObjects")
    assert source.index("bool BboxAlmostEqual") < helper_index < validate_index
    assert "obj.GetTightBoundingBox(bbox)" in helper_body
    assert '"tight_object"' in helper_body
    assert "obj.BoundingBox()" in helper_body
    assert '"raw_object_fallback"' in helper_body
    assert '"unavailable"' in helper_body


def test_director_pose_bbox_helper_is_used_for_director_pose_truth():
    frame_source = DIRECTOR_FRAME.read_text(encoding="utf-8")
    handler_source = DIRECTOR_HANDLER.read_text(encoding="utf-8")

    serialize_body = _extract_function(handler_source, "nlohmann::json SerializeObjectState")
    validate_body = _extract_function(frame_source, "void ValidateFrameObjects")
    phase_body = _extract_function(frame_source, "nlohmann::json NativeObjectPhaseEvidence")
    restore_body = _extract_function(frame_source, "bool DirectorObjectPoseGuard::Restore")

    for body in [serialize_body, validate_body, phase_body, restore_body]:
        assert "DirectorObjectPoseBbox(*obj)" in body or "DirectorObjectPoseBbox(*restoredObj)" in body

    assert '"bbox_method"' in serialize_body
    assert '"bbox_method"' in phase_body
    assert '"restored_bbox_method"' in restore_body
    assert "restoredObj->BoundingBox()" not in restore_body
    assert "ON_BoundingBox currentBbox = obj->BoundingBox();" not in validate_body
    assert "ON_BoundingBox bbox = obj->BoundingBox();" not in serialize_body
```

- [ ] **Step 2: Run red tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_director_native_source.py::test_director_pose_bbox_helper_prefers_tight_with_raw_fallback `
  mcp_server/tests/test_director_native_source.py::test_director_pose_bbox_helper_is_used_for_director_pose_truth `
  -q
```

Expected: fail because `DirectorObjectPoseBbox()` does not exist yet.

- [ ] **Step 3: Commit red tests**

Run:

```powershell
git add mcp_server/tests/test_director_native_source.py
git commit -m "test(director): pin pose bbox helper contract"
```

## Task 5: Implement Shared Director Pose Bbox Helper

**Files:**
- Modify: `src/RookNative/Handlers/DirectorFrame.h`
- Modify: `src/RookNative/Handlers/DirectorFrame.cpp`
- Modify: `src/RookNative/Handlers/DirectorHandler.cpp`
- Test: `mcp_server/tests/test_director_native_source.py`

- [ ] **Step 1: Declare helper result in header**

In `src/RookNative/Handlers/DirectorFrame.h`, after `FrameCamera`, add:

```cpp
struct DirectorPoseBboxResult
{
    ON_BoundingBox bbox;
    std::string method;
    bool valid = false;
};
```

Under `// Validation helpers`, add:

```cpp
DirectorPoseBboxResult DirectorObjectPoseBbox(const CRhinoObject& obj);
```

- [ ] **Step 2: Implement helper with external linkage**

In `src/RookNative/Handlers/DirectorFrame.cpp`, add the helper outside the anonymous namespace so it satisfies the declaration in `DirectorFrame.h` and can link from `DirectorHandler.cpp`.

Do not place this function after `BboxMaxDelta`; that area is inside `namespace { ... }`.

Place it after `BboxAlmostEqual()` and before `ValidateFrameObjects()`:

```cpp
DirectorPoseBboxResult DirectorObjectPoseBbox(const CRhinoObject& obj)
{
    DirectorPoseBboxResult result;

    ON_BoundingBox bbox;
    if (obj.GetTightBoundingBox(bbox) && bbox.IsValid())
    {
        result.bbox = bbox;
        result.method = "tight_object";
        result.valid = true;
        return result;
    }

    bbox = obj.BoundingBox();
    if (bbox.IsValid())
    {
        result.bbox = bbox;
        result.method = "raw_object_fallback";
        result.valid = true;
        return result;
    }

    result.bbox = ON_BoundingBox::EmptyBoundingBox;
    result.method = "unavailable";
    result.valid = false;
    return result;
}
```

- [ ] **Step 3: Use helper in phase evidence**

In `NativeObjectPhaseEvidence`, replace the legacy raw assignment to `phase["bbox"]` with:

```cpp
    const DirectorPoseBboxResult poseBbox = DirectorObjectPoseBbox(*obj);
    phase["bbox"] = poseBbox.valid ? BoundingBoxToDirectorJson(poseBbox.bbox) : nlohmann::json(nullptr);
    phase["bbox_method"] = poseBbox.method;
```

Keep the Checkpoint 1 `raw_bbox` and `tight_bbox` diagnostic fields. They should remain separate from `bbox`, which now represents Director pose truth.

- [ ] **Step 4: Use helper in source validation**

In `ValidateFrameObjects`, replace:

```cpp
        ON_BoundingBox currentBbox = obj->BoundingBox();
        if (!currentBbox.IsValid())
            throw DirectorFrameValidationError("invalid_input", "Object has invalid bounding box: " + frameObject.objectId, { frameObject.objectId });

        if (!BboxAlmostEqual(currentBbox, frameObject.sourceBbox, bboxTolerance))
```

with:

```cpp
        const DirectorPoseBboxResult currentBbox = DirectorObjectPoseBbox(*obj);
        if (!currentBbox.valid)
            throw DirectorFrameValidationError("invalid_input", "Object has invalid Director pose bbox: " + frameObject.objectId, { frameObject.objectId });

        if (!BboxAlmostEqual(currentBbox.bbox, frameObject.sourceBbox, bboxTolerance))
```

Update the error message body to include `bbox_method=`:

```cpp
                std::string("Object source_state bbox does not match current document state; bbox_method=") +
                    currentBbox.method +
                    "; bbox_tolerance_policy=" +
                    bboxTolerancePolicy,
```

- [ ] **Step 5: Use helper in restore verification**

In `DirectorObjectPoseGuard::Restore`, replace:

```cpp
        ON_BoundingBox restoredBbox = restoredObj->BoundingBox();
        detail["restored_object_type"] = ObjectTypeToString(restoredObj->ObjectType());
        if (!restoredBbox.IsValid())
```

with:

```cpp
        const DirectorPoseBboxResult restoredBbox = DirectorObjectPoseBbox(*restoredObj);
        detail["restored_object_type"] = ObjectTypeToString(restoredObj->ObjectType());
        detail["restored_bbox_method"] = restoredBbox.method;
        if (!restoredBbox.valid)
```

Change:

```cpp
            restoredBbox,
```

to:

```cpp
            restoredBbox.bbox,
```

and change:

```cpp
        if (!BboxAlmostEqual(restoredBbox, object.sourceBbox, restoreTolerance))
```

to:

```cpp
        if (!BboxAlmostEqual(restoredBbox.bbox, object.sourceBbox, restoreTolerance))
```

- [ ] **Step 6: Use helper in `/director/object-states`**

In `src/RookNative/Handlers/DirectorHandler.cpp`, replace the bbox block in `SerializeObjectState`:

```cpp
    ON_BoundingBox bbox = obj->BoundingBox();
    if (!bbox.IsValid())
        throw std::runtime_error("Object has invalid bounding box: " + UuidToString(attrs.m_uuid));
```

with:

```cpp
    const DirectorPoseBboxResult poseBbox = DirectorObjectPoseBbox(*obj);
    if (!poseBbox.valid)
        throw std::runtime_error("Object has invalid Director pose bbox: " + UuidToString(attrs.m_uuid));
    const ON_BoundingBox& bbox = poseBbox.bbox;
```

After `state["bbox_max"] = PointToJson(bbox.m_max);`, add:

```cpp
    state["bbox_method"] = poseBbox.method;
```

- [ ] **Step 7: Run source tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_director_native_source.py mcp_server/tests/test_director_replay_native_source.py -q
```

Expected: pass.

- [ ] **Step 8: Run static scope guard**

Run:

```powershell
git diff --check
$forbidden = git diff --name-only HEAD | Select-String -Pattern 'canvas_director|CanvasDirector|MeasureHandler|SelectionHandler|BlocksHandler|SceneGraphHandler|mcp_server/src/rook/.*\.py' -CaseSensitive:$false
if ($forbidden) { throw "Forbidden files changed:`n$forbidden" }
```

Expected: no forbidden file matches.

- [ ] **Step 9: Commit helper**

Run:

```powershell
git add src/RookNative/Handlers/DirectorFrame.h src/RookNative/Handlers/DirectorFrame.cpp src/RookNative/Handlers/DirectorHandler.cpp mcp_server/tests/test_director_native_source.py
git commit -m "fix(director): use tight pose bbox for Director verification"
```

## Task 6: Build, Deploy, And Verify Helper

**Files:**
- No source edits expected unless verification fails.

- [ ] **Step 1: Build and native-only deploy**

Close Rhino, then run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -NativeOnly
```

Expected: `Native-only deploy complete.`

- [ ] **Step 2: Run minimized Pearson probe**

Reopen the Pearson file and run the same probe command from Task 3.

Expected:

```text
run state: complete
no dirty_partial_state:true
frame 2 evidence records bbox_method: tight_object
raw bbox may still show wrong X/Y
Director pose bbox / tight bbox matches phase-expected bbox
```

- [ ] **Step 3: Run full Pearson CanvasDirector acceptance only if minimized probe passes**

Run the existing CanvasDirector chain:

```text
extract -> spec -> compile -> run_compiled_track -> assemble_director_video
```

Expected: run artifacts and video assembly complete. If it fails, stop and classify the new failure; do not add another restore fix.

- [ ] **Step 4: Final verification**

Run:

```powershell
git diff --check
$canvasDiff = git diff --name-only b227c10e..HEAD | Select-String -Pattern 'canvas_director|CanvasDirector' -CaseSensitive:$false
if ($canvasDiff) { throw "CanvasDirector files changed:`n$canvasDiff" }
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_director_native_source.py mcp_server/tests/test_director_replay_native_source.py -q
git status --short --branch
```

Expected:

```text
no diff-check output
no CanvasDirector diff matches
source/replay tests pass
worktree clean or contains only an approved diagnostic doc update
```

## Task 7: Record Diagnostic Result

**Files:**
- Modify: `docs/superpowers/specs/2026-07-03-director-pose-bbox-design.md`

- [ ] **Step 1: Add a result section**

Append a section named `## Implementation Result`.

The section must include concrete observed values for:

- Checkpoint 1 live probe run root.
- Whether raw bbox reproduced the Pearson X/Y mismatch.
- Whether tight bbox was valid in all phases.
- Whether tight bbox matched the pure-translation phase expectation.
- The observed `InstanceXform()` sequence.
- The gate decision and reviewer approval.
- Checkpoint 2 minimized Pearson run state, if executed.
- The native `bbox_method` used by the helper, if executed.
- Full Pearson CanvasDirector acceptance status, if executed.

If Checkpoint 1 stops the slice, record the stopped gate condition and do not add Checkpoint 2 claims.

- [ ] **Step 2: Self-check the result section**

Run:

```powershell
rg -n "TBD|TODO|placeholder|replace|not run" docs/superpowers/specs/2026-07-03-director-pose-bbox-design.md
```

Expected: no matches unless `not run` is intentionally part of a stopped-gate explanation.

- [ ] **Step 3: Commit result section**

Run:

```powershell
git add docs/superpowers/specs/2026-07-03-director-pose-bbox-design.md
git commit -m "docs(director): record pose bbox verification result"
```

## Execution Notes

Recommended execution mode: **Subagent-Driven, staged/sequential**.

- Worker 1: Task 1 only, then review.
- Worker 2: Task 2 only, then review.
- Lead coder: Task 3 live gate.
- If the gate is clean, Worker 3: Task 4 only, then review.
- Worker 4: Task 5 only, then review.
- Lead coder: Task 6 live verification and Task 7 result note.

Do not run Task 4 or Task 5 until Task 3 is reviewed and explicitly approved.
