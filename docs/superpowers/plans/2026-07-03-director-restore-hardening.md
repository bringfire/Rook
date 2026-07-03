# Director Restore Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden native Director bbox restore verification for large-coordinate block instances while preserving dirty-state safety and completing the Pearson CanvasDirector acceptance smoke.

**Architecture:** Keep CanvasDirector unchanged. Add restore evidence and bounded restore tolerance in the shared native `DirectorFrame` helper, but keep source-state validation and restore verification as separate gates. Run the implementation in two gated native phases: instrumentation-only first, then tolerance only after raw native deltas are observed.

**Tech Stack:** Rhino 8 C++ SDK, RookNative C++ handlers, Python MCP test harness, pytest live Rhino tests, existing Director `/director/frame-capture`, `/director/object-states`, and Media Foundation video assembly.

---

## Scope Check

This is one subsystem: native Director restore verification. Do not modify
CanvasDirector extraction, managed Companion extraction, Python
`dirty_partial_state` stop behavior, or Director authoring spec shape.

## File Structure

- Modify `src/RookNative/Handlers/DirectorFrame.h`
  - Expose named source/restore tolerance policy declarations if needed by source tests.
- Modify `src/RookNative/Handlers/DirectorFrame.cpp`
  - Add source/restore bbox policy names.
  - Add bbox evidence helpers.
  - Record restore evidence with `bbox_comparison_available`.
  - Keep hard restore failures hard.
- Modify `mcp_server/tests/test_director_native_source.py`
  - Add source-level contract tests for named gates and restore evidence fields.
- Modify `mcp_server/tests/test_director_replay_native_source.py`
  - Add or extend source-level replay assertions so shared `DirectorObjectPoseGuard` behavior is covered.
- Modify `mcp_server/tests/test_director_routes_live.py`
  - Add a synthetic large-coordinate block-instance repeated-frame regression.
  - Update the existing frame-capture success assertion to check restore evidence fields without requiring exact bbox equality for the new path.

No new production files are required.

---

### Task 1: Add Native Source Contract Tests

**Files:**
- Modify: `mcp_server/tests/test_director_native_source.py`
- Modify: `mcp_server/tests/test_director_replay_native_source.py`

- [ ] **Step 1: Add DirectorFrame source-path constants to `test_director_native_source.py`**

Add this constant near the existing `DIRECTOR_HANDLER` constants:

```python
DIRECTOR_FRAME = REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorFrame.cpp"
```

- [ ] **Step 2: Add source/restore policy and evidence contract tests**

Append these tests to `mcp_server/tests/test_director_native_source.py`:

```python
def test_director_restore_uses_separate_named_bbox_policies():
    source = DIRECTOR_FRAME.read_text(encoding="utf-8")
    validate_body = _extract_function(source, "void ValidateFrameObjects")
    restore_body = _extract_function(source, "bool DirectorObjectPoseGuard::Restore")

    assert "kDirectorSourceStateBboxTolerance" in source
    assert "DirectorSourceStateBboxTolerance" in validate_body
    assert "kDirectorRestoreBboxTolerance" in source
    assert "DirectorRestoreBboxTolerance" in restore_body
    assert "source_state_validation" in source
    assert "restore_verification" in source
    assert validate_body != restore_body


def test_director_restore_evidence_records_comparison_availability():
    source = DIRECTOR_FRAME.read_text(encoding="utf-8")
    restore_body = _extract_function(source, "bool DirectorObjectPoseGuard::Restore")

    for token in [
        "bbox_comparison_available",
        "source_object_type",
        "restored_object_type",
        "source_bbox",
        "restored_bbox",
        "bbox_delta_min",
        "bbox_delta_max",
        "bbox_max_delta",
        "bbox_tolerance",
        "bbox_tolerance_policy",
    ]:
        assert token in source

    assert "restored bbox did not match source bbox" in restore_body
    assert "InitializeRestoreDetail" in restore_body
    assert "AddRestoreBboxEvidence" in restore_body
    assert "MarkBboxComparisonUnavailable" in restore_body
    assert "bbox comparison unavailable" in source


def test_director_restore_hard_failures_precede_tolerance_acceptance():
    source = DIRECTOR_FRAME.read_text(encoding="utf-8")
    restore_body = _extract_function(source, "bool DirectorObjectPoseGuard::Restore")

    tolerance_index = restore_body.index("BboxAlmostEqual")
    for marker in [
        "restore transform failed",
        "object not found after restore",
        "restored bbox is invalid",
    ]:
        assert marker in restore_body
        assert restore_body.index(marker) < tolerance_index
```

- [ ] **Step 3: Add replay shared-helper verification**

Append this test to `mcp_server/tests/test_director_replay_native_source.py`:

```python
def test_replay_verification_covers_shared_pose_guard_restore_contract():
    frame = _read(FRAME_H)
    replay = _extract_function(_read(REPLAY_CPP), "HandleDirectorReplay")

    assert "DirectorObjectPoseGuard" in frame
    assert "bbox_comparison_available" in _read(FRAME_H) or "bbox_comparison_available" in _read(REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorFrame.cpp")
    assert "restore_failed" in replay
    assert "dirty_partial_state" in replay
    assert "poseGuard->Restore(evidence)" in replay
```

- [ ] **Step 4: Run the source tests and verify they fail**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_director_native_source.py::test_director_restore_uses_separate_named_bbox_policies `
  mcp_server/tests/test_director_native_source.py::test_director_restore_evidence_records_comparison_availability `
  mcp_server/tests/test_director_native_source.py::test_director_restore_hard_failures_precede_tolerance_acceptance `
  mcp_server/tests/test_director_replay_native_source.py::test_replay_verification_covers_shared_pose_guard_restore_contract `
  -q
```

Expected: FAIL because `DirectorFrame.cpp` does not yet expose the named policies or evidence fields.

---

### Task 2: Implement Instrumentation-Only Restore Evidence

**Files:**
- Modify: `src/RookNative/Handlers/DirectorFrame.cpp`
- Modify: `src/RookNative/Handlers/DirectorFrame.h` only if source tests need declarations
- Test: `mcp_server/tests/test_director_native_source.py`
- Test: `mcp_server/tests/test_director_replay_native_source.py`

- [ ] **Step 1: Add named bbox policies and evidence helpers**

In `src/RookNative/Handlers/DirectorFrame.cpp`, after `ViewportAlmostEqual`, add:

```cpp
constexpr double kDirectorSourceStateBboxTolerance = 1.0e-4;
constexpr double kDirectorRestoreBboxTolerance = 1.0e-4;

double DirectorSourceStateBboxTolerance()
{
    return kDirectorSourceStateBboxTolerance;
}

double DirectorRestoreBboxTolerance(const ON_BoundingBox&, const ON_BoundingBox&)
{
    return kDirectorRestoreBboxTolerance;
}

const char* DirectorSourceStateBboxTolerancePolicy()
{
    return "source_state_validation.fixed_1e-4";
}

const char* DirectorRestoreBboxTolerancePolicy()
{
    return "restore_verification.instrumentation_only.fixed_1e-4";
}

nlohmann::json PointToDirectorEvidenceJson(const ON_3dPoint& point)
{
    return nlohmann::json::array({
        RoundTo(point.x, 9),
        RoundTo(point.y, 9),
        RoundTo(point.z, 9)
    });
}

nlohmann::json BboxToDirectorEvidenceJson(const ON_BoundingBox& bbox)
{
    nlohmann::json data;
    data["min"] = PointToDirectorEvidenceJson(bbox.m_min);
    data["max"] = PointToDirectorEvidenceJson(bbox.m_max);
    return data;
}

nlohmann::json BboxDeltaToJson(const ON_3dPoint& a, const ON_3dPoint& b)
{
    return nlohmann::json::array({
        RoundTo(std::fabs(a.x - b.x), 9),
        RoundTo(std::fabs(a.y - b.y), 9),
        RoundTo(std::fabs(a.z - b.z), 9)
    });
}

double BboxMaxDelta(const ON_BoundingBox& a, const ON_BoundingBox& b)
{
    double maxDelta = 0.0;
    maxDelta = (std::max)(maxDelta, std::fabs(a.m_min.x - b.m_min.x));
    maxDelta = (std::max)(maxDelta, std::fabs(a.m_min.y - b.m_min.y));
    maxDelta = (std::max)(maxDelta, std::fabs(a.m_min.z - b.m_min.z));
    maxDelta = (std::max)(maxDelta, std::fabs(a.m_max.x - b.m_max.x));
    maxDelta = (std::max)(maxDelta, std::fabs(a.m_max.y - b.m_max.y));
    maxDelta = (std::max)(maxDelta, std::fabs(a.m_max.z - b.m_max.z));
    return maxDelta;
}

void InitializeRestoreDetail(nlohmann::json& detail, const FrameObjectTransform& object)
{
    detail["object_id"] = object.objectId;
    detail["applied"] = false;
    detail["restored"] = false;
    detail["validation_strength"] = object.validationStrength;
    detail["source_object_type"] = nullptr;
    detail["restored_object_type"] = nullptr;
    detail["bbox_comparison_available"] = false;
    detail["bbox_tolerance"] = kDirectorRestoreBboxTolerance;
    detail["bbox_tolerance_policy"] = DirectorRestoreBboxTolerancePolicy();
}

void MarkBboxComparisonUnavailable(nlohmann::json& detail, const std::string& reason)
{
    detail["bbox_comparison_available"] = false;
    detail["restore_error"] = reason;
    detail["bbox_comparison_reason"] = "bbox comparison unavailable: " + reason;
}

void AddRestoreBboxEvidence(
    nlohmann::json& detail,
    const ON_BoundingBox& sourceBbox,
    const ON_BoundingBox& restoredBbox)
{
    const double tolerance = DirectorRestoreBboxTolerance(sourceBbox, restoredBbox);
    detail["bbox_comparison_available"] = true;
    detail["source_bbox"] = BboxToDirectorEvidenceJson(sourceBbox);
    detail["restored_bbox"] = BboxToDirectorEvidenceJson(restoredBbox);
    detail["bbox_delta_min"] = BboxDeltaToJson(sourceBbox.m_min, restoredBbox.m_min);
    detail["bbox_delta_max"] = BboxDeltaToJson(sourceBbox.m_max, restoredBbox.m_max);
    detail["bbox_max_delta"] = RoundTo(BboxMaxDelta(sourceBbox, restoredBbox), 9);
    detail["bbox_tolerance"] = tolerance;
    detail["bbox_tolerance_policy"] = DirectorRestoreBboxTolerancePolicy();
}
```

This is instrumentation-only: `DirectorRestoreBboxTolerance()` still returns `1.0e-4`.

- [ ] **Step 2: Replace source validation tolerance with the named source policy**

In `ValidateFrameObjects`, replace:

```cpp
constexpr double kBboxTolerance = 1.0e-4;
```

and the comparison call with:

```cpp
const double tolerance = DirectorSourceStateBboxTolerance();
```

Then use:

```cpp
if (!BboxAlmostEqual(currentBbox, frameObject.sourceBbox, tolerance))
```

- [ ] **Step 3: Replace `DirectorObjectPoseGuard::Restore()` detail construction**

Inside `DirectorObjectPoseGuard::Restore()`, replace the per-object initialization block:

```cpp
nlohmann::json detail;
detail["object_id"] = object.objectId;
detail["applied"] = m_applied[static_cast<size_t>(i)];
detail["restored"] = false;
detail["validation_strength"] = object.validationStrength;
```

with:

```cpp
nlohmann::json detail;
InitializeRestoreDetail(detail, object);
detail["applied"] = m_applied[static_cast<size_t>(i)];

const CRhinoObject* beforeRestoreObj = m_doc ? m_doc->LookupObject(object.uuid) : nullptr;
if (beforeRestoreObj && !beforeRestoreObj->IsDeleted())
    detail["source_object_type"] = ObjectTypeToString(beforeRestoreObj->ObjectType());
```

- [ ] **Step 4: Update the not-applied branch**

Replace the existing not-applied branch body with:

```cpp
if (!m_applied[static_cast<size_t>(i)])
{
    detail["restored"] = true;
    detail["bbox_comparison_available"] = false;
    detail["bbox_comparison_reason"] = "object transform was not applied";
    m_restored[static_cast<size_t>(i)] = true;
    details.push_back(std::move(detail));
    ++restoredCount;
    continue;
}
```

- [ ] **Step 5: Update hard failure branches before bbox comparison**

For the transform-back failure branch, replace the restore error assignment with:

```cpp
if (!transformedBack)
{
    MarkBboxComparisonUnavailable(
        detail,
        detail.value("restore_error", "restore transform failed"));
    details.push_back(std::move(detail));
    continue;
}
```

For the missing object branch, use:

```cpp
if (!restoredObj || restoredObj->IsDeleted())
{
    MarkBboxComparisonUnavailable(detail, "object not found after restore");
    details.push_back(std::move(detail));
    continue;
}
```

For the invalid bbox branch, split it from the tolerance comparison:

```cpp
detail["restored_object_type"] = ObjectTypeToString(restoredObj->ObjectType());

ON_BoundingBox restoredBbox = restoredObj->BoundingBox();
if (!restoredBbox.IsValid())
{
    MarkBboxComparisonUnavailable(detail, "restored bbox is invalid");
    details.push_back(std::move(detail));
    continue;
}

AddRestoreBboxEvidence(detail, object.sourceBbox, restoredBbox);
const double restoreTolerance = detail["bbox_tolerance"].get<double>();
if (!BboxAlmostEqual(restoredBbox, object.sourceBbox, restoreTolerance))
{
    detail["restore_error"] = "restored bbox did not match source bbox";
    details.push_back(std::move(detail));
    continue;
}
```

Keep the existing success block after this comparison:

```cpp
detail["restored"] = true;
m_restored[static_cast<size_t>(i)] = true;
++restoredCount;
details.push_back(std::move(detail));
```

- [ ] **Step 6: Remove or stop using the private class tolerance**

In `src/RookNative/Handlers/DirectorFrame.h`, remove the private class member:

```cpp
static constexpr double kBboxTolerance = 1.0e-4;
```

The source and restore tolerances now live as separately named policies in `DirectorFrame.cpp`.

- [ ] **Step 7: Run source tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_director_native_source.py::test_director_restore_uses_separate_named_bbox_policies `
  mcp_server/tests/test_director_native_source.py::test_director_restore_evidence_records_comparison_availability `
  mcp_server/tests/test_director_native_source.py::test_director_restore_hard_failures_precede_tolerance_acceptance `
  mcp_server/tests/test_director_replay_native_source.py::test_replay_verification_covers_shared_pose_guard_restore_contract `
  -q
```

Expected: PASS.

- [ ] **Step 8: Build native**

Run from a normal PowerShell:

```powershell
cmd /c "call `"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat`" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected: exit code `0`.

- [ ] **Step 9: Commit instrumentation-only patch**

```powershell
git add src/RookNative/Handlers/DirectorFrame.cpp src/RookNative/Handlers/DirectorFrame.h mcp_server/tests/test_director_native_source.py mcp_server/tests/test_director_replay_native_source.py
git commit -m "fix(director): add restore bbox evidence"
```

---

### Task 3: Deploy Instrumentation And Collect Raw Restore Deltas

**Files:**
- Read: `C:\Users\bring\OneDrive\Desktop\Pearson\ANIMATION\V2\.rook\director\specs\pearson_animation_test.json`
- Read: generated run `logs/frame_evidence.jsonl`

- [ ] **Step 1: Deploy the instrumentation build**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -PayloadOnly -AllowRunning -UseRepoVenv
```

Expected: deploy completes. If Rhino has the native plugin locked and deploy cannot replace payload files, stop and restart Rhino/Rook, then rerun the command.

- [ ] **Step 2: Run the Pearson compiled-track capture with instrumentation-only threshold**

Run:

```powershell
$env:PYTHONPATH='C:\Users\bring\.config\superpowers\worktrees\Rook\rookvision-canvas-director\mcp_server\src'
$env:ROOK_MODE='dev'
$env:ROOK_INSTALL_ROOT='C:\Users\bring\.config\superpowers\worktrees\Rook\rookvision-canvas-director'
$env:ROOK_PROJECT_ROOT='C:\Users\bring\.config\superpowers\worktrees\Rook\rookvision-canvas-director'
@'
import asyncio
import json
import pathlib
from datetime import datetime, timezone

from rook import director, director_compiler
from rook.bridge import call_rhino

spec_path = pathlib.Path(r"C:\Users\bring\OneDrive\Desktop\Pearson\ANIMATION\V2\.rook\director\specs\pearson_animation_test.json")
spec = json.loads(spec_path.read_text(encoding="utf-8"))
run_id = "restore_evidence_probe_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

async def main():
    compiled = await director_compiler.compile_motion(spec, call_native=call_rhino)
    request = {
        "track": compiled["track"],
        "resolution": spec["resolution"],
        "display": {"mode": "Rendered"},
        "run_id": run_id,
        "compile_provenance": compiled["provenance"],
        "run_inputs": {
            "director_authoring_spec": spec,
            "provenance": {
                "source_spec_id": spec.get("spec_id"),
                "canvas_export_state_sha256": (spec.get("source") or {}).get("canvas_export_state_sha256"),
                "template_id": (spec.get("source") or {}).get("template_id"),
                "template_version": (spec.get("source") or {}).get("template_version"),
                "export_id": (spec.get("source") or {}).get("export_id"),
            },
        },
    }
    summary = await director.run_compiled_track(request, call_native=call_rhino)
    run_root = pathlib.Path(summary["run_root"])
    evidence_path = run_root / "logs" / "frame_evidence.jsonl"
    rows = [json.loads(line) for line in evidence_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    detail_rows = []
    for row in rows:
        for detail in (((row.get("objects") or {}).get("details")) or []):
            detail_rows.append({
                "frame_index": row.get("frame_index"),
                "success": row.get("success"),
                "dirty_partial_state": row.get("dirty_partial_state"),
                "object_id": detail.get("object_id"),
                "restored": detail.get("restored"),
                "bbox_comparison_available": detail.get("bbox_comparison_available"),
                "bbox_max_delta": detail.get("bbox_max_delta"),
                "bbox_tolerance": detail.get("bbox_tolerance"),
                "bbox_tolerance_policy": detail.get("bbox_tolerance_policy"),
                "restore_error": detail.get("restore_error"),
                "bbox_delta_min": detail.get("bbox_delta_min"),
                "bbox_delta_max": detail.get("bbox_delta_max"),
            })
    print(json.dumps({
        "summary": summary,
        "run_root": str(run_root),
        "frame_count_with_evidence": len(rows),
        "details": detail_rows[-5:],
        "max_observed_delta": max(
            [float(item["bbox_max_delta"]) for item in detail_rows if item.get("bbox_max_delta") is not None],
            default=None,
        ),
    }, indent=2))

asyncio.run(main())
'@ | & 'C:\Users\bring\.config\superpowers\worktrees\Rook\rookvision-canvas-director\mcp_server\.venv\Scripts\python.exe' -
```

Expected: the run either reproduces `unsafe_failed` with new evidence fields, or completes with current `1e-4` tolerance. If it completes, stop and report that the original symptom no longer reproduces under instrumentation. If it fails, record `max_observed_delta`, the failing frame, and `bbox_tolerance_policy`.

- [ ] **Step 3: Gate before tolerance**

Proceed to Task 4 only when all are true:

- evidence contains `bbox_comparison_available:true` for the failing object;
- the failing object was restored by inverse transform and has a valid restored bbox;
- `max_observed_delta <= 0.001`;
- repeated evidence does not show deltas increasing frame-over-frame.

If any condition is false, stop and escalate to snapshot/original-state restore design.

---

### Task 4: Add Bounded Restore Tolerance Policy

**Files:**
- Modify: `src/RookNative/Handlers/DirectorFrame.cpp`
- Test: `mcp_server/tests/test_director_native_source.py`

- [ ] **Step 1: Tighten the source test to require bounded policy names**

In `test_director_restore_uses_separate_named_bbox_policies`, add these assertions:

```python
    assert "kDirectorRestoreSerializationFloor" in source
    assert "kDirectorRestoreModelScaleFactor" in source
    assert "kDirectorRestoreBboxToleranceCap" in source
    assert "serialization_floor_plus_bounded_model_scale" in source
```

Run the same source-test command from Task 2. Expected: FAIL until the bounded policy is implemented.

- [ ] **Step 2: Replace restore policy constants and function**

In `DirectorFrame.cpp`, replace:

```cpp
constexpr double kDirectorRestoreBboxTolerance = 1.0e-4;
```

with:

```cpp
constexpr double kDirectorRestoreSerializationFloor = 1.0e-4;
constexpr double kDirectorRestoreModelScaleFactor = 1.0e-9;
constexpr double kDirectorRestoreBboxToleranceCap = 1.0e-3;
```

Replace `DirectorRestoreBboxTolerance()` and `DirectorRestoreBboxTolerancePolicy()` with:

```cpp
double MaxBboxCoordinateMagnitude(const ON_BoundingBox& a, const ON_BoundingBox& b)
{
    double maxMagnitude = 0.0;
    const double values[] = {
        a.m_min.x, a.m_min.y, a.m_min.z,
        a.m_max.x, a.m_max.y, a.m_max.z,
        b.m_min.x, b.m_min.y, b.m_min.z,
        b.m_max.x, b.m_max.y, b.m_max.z
    };
    for (double value : values)
        maxMagnitude = (std::max)(maxMagnitude, std::fabs(value));
    return maxMagnitude;
}

double DirectorRestoreBboxTolerance(const ON_BoundingBox& sourceBbox, const ON_BoundingBox& restoredBbox)
{
    const double modelAllowance = MaxBboxCoordinateMagnitude(sourceBbox, restoredBbox) * kDirectorRestoreModelScaleFactor;
    return (std::min)(
        kDirectorRestoreBboxToleranceCap,
        kDirectorRestoreSerializationFloor + modelAllowance);
}

const char* DirectorRestoreBboxTolerancePolicy()
{
    return "restore_verification.serialization_floor_plus_bounded_model_scale.cap_1e-3";
}
```

- [ ] **Step 3: Fix `InitializeRestoreDetail()` default tolerance**

Because `InitializeRestoreDetail()` does not yet have a restored bbox, set its default tolerance to the serialization floor:

```cpp
detail["bbox_tolerance"] = kDirectorRestoreSerializationFloor;
```

`AddRestoreBboxEvidence()` will overwrite the value with the computed restore tolerance once comparison data exists.

- [ ] **Step 4: Run source tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_director_native_source.py::test_director_restore_uses_separate_named_bbox_policies `
  mcp_server/tests/test_director_native_source.py::test_director_restore_evidence_records_comparison_availability `
  mcp_server/tests/test_director_native_source.py::test_director_restore_hard_failures_precede_tolerance_acceptance `
  mcp_server/tests/test_director_replay_native_source.py::test_replay_verification_covers_shared_pose_guard_restore_contract `
  -q
```

Expected: PASS.

- [ ] **Step 5: Build native**

Run:

```powershell
cmd /c "call `"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat`" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected: exit code `0`.

- [ ] **Step 6: Commit bounded tolerance patch**

```powershell
git add src/RookNative/Handlers/DirectorFrame.cpp mcp_server/tests/test_director_native_source.py
git commit -m "fix(director): bound restore bbox tolerance"
```

---

### Task 5: Add Synthetic Large-Coordinate Block Instance Live Regression

**Files:**
- Modify: `mcp_server/tests/test_director_routes_live.py`

- [ ] **Step 1: Import block helpers**

Change the existing import:

```python
from .conftest import _create_brep
```

to:

```python
from .conftest import _block_create, _block_insert, _create_brep
```

- [ ] **Step 2: Add bbox tolerance assertion helper**

Add this helper near `_assert_vector_close`:

```python
def _assert_bbox_within_tolerance(actual: dict[str, Any], expected: dict[str, Any], tolerance: float) -> None:
    for key in ("bbox_min", "bbox_max"):
        assert key in actual and key in expected
        for actual_value, expected_value in zip(actual[key], expected[key]):
            assert abs(float(actual_value) - float(expected_value)) <= tolerance
```

- [ ] **Step 3: Add restore evidence helper**

Add this helper near `_read_jsonl`:

```python
def _single_restore_detail(evidence: dict[str, Any]) -> dict[str, Any]:
    details = ((evidence.get("objects") or {}).get("details")) or []
    assert len(details) == 1, evidence
    detail = details[0]
    assert detail.get("bbox_comparison_available") is True
    assert detail.get("bbox_tolerance") is not None
    assert detail.get("bbox_tolerance_policy")
    assert detail.get("bbox_max_delta") is not None
    assert detail.get("source_bbox")
    assert detail.get("restored_bbox")
    assert "source_object_type" in detail
    assert "restored_object_type" in detail
    return detail
```

- [ ] **Step 4: Add repeated-frame large block instance test**

Append this test after `test_director_frame_capture_success_writes_png_and_restores_state`:

```python
async def test_director_frame_capture_restores_large_coordinate_block_instance_repeatedly():
    _require_host()
    suffix = uuid4().hex
    base = [625000.0, -184000.0, 103000.0]
    source_id = await _create_brep(
        [base[0], base[1], base[2]],
        [base[0] + 12.0, base[1] + 8.0, base[2] + 5.0],
        f"director_restore_source_{suffix}",
    )
    block_name = f"director_restore_block_{suffix}"
    await _block_create(block_name, [source_id], base, replace_with_instance=False)
    instance_id = await _block_insert(block_name, base)

    _, state_envelope = await _post_director("object-states", {"object_ids": [instance_id]})
    assert state_envelope["success"] is True
    source_state = state_envelope["data"]["objects"][0]
    assert source_state["object_type"] == "InstanceReference"

    _, view_envelope = await _post_director("view-state", {"source": {"kind": "active_view"}})
    assert view_envelope["success"] is True
    camera = view_envelope["data"]["camera"]
    if camera["projection"] != "perspective":
        pytest.skip("Active Rhino view is not perspective; slice 1 frame capture rejects parallel cameras.")

    max_tolerance = 0.0
    observed_max_delta = 0.0
    for frame_index, dz in enumerate([0.25, 0.5, 0.125, 0.75, 0.0], start=1):
        run_root = _director_output_root() / f"restore_large_instance_{suffix}_{frame_index}"
        output_path = run_root / "frames" / f"frame_{frame_index:04d}.png"
        instruction = _frame_instruction(
            run_root=run_root,
            output_path=output_path,
            camera_overrides=camera,
            object_transforms=[
                {
                    "object_id": instance_id,
                    "transform": _translation_matrix(0.0, 0.0, dz),
                    "source_state": {
                        "bbox_min": source_state["bbox_min"],
                        "bbox_max": source_state["bbox_max"],
                        "validation_strength": source_state["validation_strength"],
                        "state_hash": source_state.get("state_hash"),
                    },
                }
            ],
        )

        _, capture_envelope = await _post_director("frame-capture", instruction)
        assert capture_envelope["success"] is True
        evidence = capture_envelope["data"]
        assert evidence["success"] is True
        assert evidence["dirty_partial_state"] is False
        assert evidence["objects"]["restored"] == 1
        detail = _single_restore_detail(evidence)
        assert detail["restored"] is True
        assert detail["source_object_type"] == "InstanceReference"
        assert detail["restored_object_type"] == "InstanceReference"
        max_tolerance = max(max_tolerance, float(detail["bbox_tolerance"]))
        observed_max_delta = max(observed_max_delta, float(detail["bbox_max_delta"]))

    assert observed_max_delta <= max_tolerance

    _, final_state_envelope = await _post_director("object-states", {"object_ids": [instance_id]})
    assert final_state_envelope["success"] is True
    final_state = final_state_envelope["data"]["objects"][0]
    _assert_bbox_within_tolerance(final_state, source_state, max_tolerance)
```

- [ ] **Step 5: Deploy bounded-tolerance build**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -PayloadOnly -AllowRunning -UseRepoVenv
```

Expected: deploy completes. Restart Rhino/Rook if the payload is locked.

- [ ] **Step 6: Run the live regression**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_director_routes_live.py::test_director_frame_capture_restores_large_coordinate_block_instance_repeatedly `
  -q
```

Expected: PASS with a live Rhino/Rook session. If Rhino is not discoverable, the test skips; do not claim live verification.

- [ ] **Step 7: Commit the live regression**

```powershell
git add mcp_server/tests/test_director_routes_live.py
git commit -m "test(director): cover large instance restore"
```

---

### Task 6: Run Focused Replay, Python, And Native Verification

**Files:**
- Read: `mcp_server/tests/test_director_replay_native_source.py`
- Read: `mcp_server/tests/test_director.py`
- Read: `mcp_server/tests/test_canvas_director.py`

- [ ] **Step 1: Run native source and replay source tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_director_native_source.py `
  mcp_server/tests/test_director_replay_native_source.py `
  -q
```

Expected: PASS.

- [ ] **Step 2: Run focused Python Director artifact tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_director.py `
  mcp_server/tests/test_canvas_director.py `
  -q -k "canvas_director or run_compiled_track or validate_run_inputs or unsafe_failed"
```

Expected: PASS.

- [ ] **Step 3: Run native build once more**

Run:

```powershell
cmd /c "call `"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat`" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected: exit code `0`.

- [ ] **Step 4: Check formatting**

Run:

```powershell
git diff --check
```

Expected: no output and exit code `0`.

---

### Task 7: Pearson CanvasDirector Acceptance Smoke Through Video Assembly

**Files:**
- Read: `C:\Users\bring\OneDrive\Desktop\Pearson\ANIMATION\V2\.rook\director\specs\pearson_animation_test.json`
- Read/write: Director run root under `%LOCALAPPDATA%\Rook\rookvision_director`

- [ ] **Step 1: Confirm GH canvas is clean**

Run through MCP or Rook tool gateway:

```text
gh_errors
```

Expected: `errorCount: 0`, `warningCount: 0`.

- [ ] **Step 2: Re-extract CanvasDirector state**

Run through MCP:

```json
{
  "tool": "rhino_director_canvas_extract",
  "arguments": {
    "project_root": "C:\\Users\\bring\\OneDrive\\Desktop\\Pearson\\ANIMATION\\V2",
    "export_id": "pearson_animation_test",
    "spec_id": "pearson_animation_test",
    "proposal_id": "pearson_v2_smoke",
    "solve_mode": "require_fresh_solve",
    "replace_spec": true
  }
}
```

Expected: success, export/spec paths under `V2\.rook\director`, and a `compile_motion_request` in the response.

- [ ] **Step 3: Run full compiled-track capture and assemble video**

Run:

```powershell
$env:PYTHONPATH='C:\Users\bring\.config\superpowers\worktrees\Rook\rookvision-canvas-director\mcp_server\src'
$env:ROOK_MODE='dev'
$env:ROOK_INSTALL_ROOT='C:\Users\bring\.config\superpowers\worktrees\Rook\rookvision-canvas-director'
$env:ROOK_PROJECT_ROOT='C:\Users\bring\.config\superpowers\worktrees\Rook\rookvision-canvas-director'
@'
import asyncio
import json
import pathlib
from datetime import datetime, timezone

from rook import director, director_compiler, director_video
from rook.bridge import call_rhino

spec_path = pathlib.Path(r"C:\Users\bring\OneDrive\Desktop\Pearson\ANIMATION\V2\.rook\director\specs\pearson_animation_test.json")
spec = json.loads(spec_path.read_text(encoding="utf-8"))
run_id = "canvas_director_acceptance_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

async def main():
    compiled = await director_compiler.compile_motion(spec, call_native=call_rhino)
    run = await director.run_compiled_track({
        "track": compiled["track"],
        "resolution": spec["resolution"],
        "display": {"mode": "Rendered"},
        "run_id": run_id,
        "compile_provenance": compiled["provenance"],
        "run_inputs": {
            "director_authoring_spec": spec,
            "provenance": {
                "source_spec_id": spec.get("spec_id"),
                "canvas_export_state_sha256": (spec.get("source") or {}).get("canvas_export_state_sha256"),
                "template_id": (spec.get("source") or {}).get("template_id"),
                "template_version": (spec.get("source") or {}).get("template_version"),
                "export_id": (spec.get("source") or {}).get("export_id"),
            },
        },
    }, call_native=call_rhino)
    if run.get("state") != "complete":
        print(json.dumps({"ok": False, "phase": "run_compiled_track", "run": run}, indent=2))
        return 2

    video = await director_video.assemble_director_video({"run_root": run["run_root"]}, call_native=call_rhino)
    run_root = pathlib.Path(run["run_root"])
    evidence_path = run_root / "logs" / "frame_evidence.jsonl"
    rows = [json.loads(line) for line in evidence_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    detail = (((rows[-1].get("objects") or {}).get("details")) or [{}])[0]
    result = {
        "ok": True,
        "run": run,
        "video": video,
        "frame_evidence_rows": len(rows),
        "preview_mp4_exists": (run_root / "videos" / "preview.mp4").exists(),
        "video_manifest_exists": (run_root / "video_manifest.json").exists(),
        "last_restore_detail": {
            "bbox_comparison_available": detail.get("bbox_comparison_available"),
            "bbox_max_delta": detail.get("bbox_max_delta"),
            "bbox_tolerance": detail.get("bbox_tolerance"),
            "bbox_tolerance_policy": detail.get("bbox_tolerance_policy"),
            "restored": detail.get("restored"),
        },
    }
    print(json.dumps(result, indent=2))
    return 0

raise SystemExit(asyncio.run(main()))
'@ | & 'C:\Users\bring\.config\superpowers\worktrees\Rook\rookvision-canvas-director\mcp_server\.venv\Scripts\python.exe' -
```

Expected:

- `ok: true`
- run `state: complete`
- `frame_evidence_rows: 240`
- `preview_mp4_exists: true`
- `video_manifest_exists: true`
- last restore detail has `bbox_comparison_available:true`, `restored:true`, and a recorded tolerance policy.

- [ ] **Step 4: Commit final verification notes if code changed after prior commits**

If Task 7 required any code changes, commit them with:

```powershell
git add src/RookNative/Handlers/DirectorFrame.cpp src/RookNative/Handlers/DirectorFrame.h mcp_server/tests/test_director_routes_live.py mcp_server/tests/test_director_native_source.py mcp_server/tests/test_director_replay_native_source.py
git commit -m "fix(director): complete restore hardening smoke"
```

If no code changed, do not create an empty commit.

---

## Final Verification Checklist

Run before marking implementation complete:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_director_native_source.py mcp_server/tests/test_director_replay_native_source.py -q
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_director.py mcp_server/tests/test_canvas_director.py -q -k "canvas_director or run_compiled_track or validate_run_inputs or unsafe_failed"
cmd /c "call `"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat`" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
git diff --check
```

Live verification requires:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_director_routes_live.py::test_director_frame_capture_restores_large_coordinate_block_instance_repeatedly -q
```

Then run the Pearson acceptance harness from Task 7.
