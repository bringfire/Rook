# Director Instance Restore Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a native-path diagnostic probe that determines whether Director's apply/inverse restore semantics fail specifically for large-coordinate `InstanceReference` objects or more broadly for the current transform call path.

**Architecture:** This is not a CanvasDirector change and not a tolerance fix. The implementation instruments `DirectorObjectPoseGuard` so apply/restore phase evidence is captured inside the native Director transform path, then adds a scratch-document live repro that compares a simple object and a block instance through the existing `run_compiled_track -> /director/frame-capture` path.

**Tech Stack:** Rhino 8 C++ SDK, RookNative C++ handlers, nlohmann/json, Python pytest live tests, existing MCP/RookNative bridge.

---

## File Structure

- Modify `src/RookNative/Handlers/DirectorFrame.cpp`
  - Add native transform call-path constant.
  - Add transform matrix JSON serialization.
  - Add native object phase evidence helper.
  - Record phase evidence before/after apply and before/after restore.
- Modify `src/RookNative/Handlers/DirectorFrame.h`
  - Store per-object diagnostic detail state across apply and restore.
- Modify `mcp_server/tests/test_director_native_source.py`
  - Add source-level tests for call-path evidence and native instance phase evidence.
- Modify `mcp_server/tests/test_director_routes_live.py`
  - Add scratch-document live repro with a large-coordinate simple control object and block instance.
- Modify `docs/superpowers/specs/2026-07-03-director-instance-restore-semantics-design.md`
  - Already patched for disposable fixture, Pearson-scale two-frame repro, and native-path evidence boundary.

## Safety Rules

- Do not run the live repro against the Pearson project model.
- Do not run the live repro without `fresh_document` or an owned throwaway Rhino harness.
- Do not change CanvasDirector files.
- Do not change restore tolerance constants.
- Do not continue to video assembly after an `unsafe_failed` diagnostic run.
- Stop after the diagnostic evidence is collected and classify the result before designing a fix.

## Task 1: Source Tests For Native Diagnostic Contract

**Files:**
- Modify: `mcp_server/tests/test_director_native_source.py`

- [ ] **Step 1: Append failing source tests**

Add these tests at the end of `mcp_server/tests/test_director_native_source.py`:

```python
def test_director_transform_call_path_is_evidenced_inside_native_restore():
    source = DIRECTOR_FRAME.read_text(encoding="utf-8")
    transform_body = _extract_function(source, "bool TransformObjectInPlace")
    apply_body = _extract_function(source, "void DirectorObjectPoseGuard::Apply")
    restore_body = _extract_function(source, "bool DirectorObjectPoseGuard::Restore")

    assert (
        'constexpr const char* kDirectorTransformObjectCallPath = '
        '"pDoc->TransformObject(objRef, xform, true, false, true)";'
    ) in source
    assert "pDoc->TransformObject(objRef, xform, true, false, true)" in transform_body
    assert "kDirectorTransformObjectCallPath" in source
    assert '"transform_call_path"' in source
    assert "requested_transform" in apply_body
    assert "requested_inverse_transform" in apply_body
    assert "phase_before_apply" in apply_body
    assert "phase_after_apply" in apply_body
    assert "phase_before_restore" in restore_body
    assert "phase_after_restore" in restore_body


def test_director_instance_restore_diagnostics_use_native_instance_state():
    source = DIRECTOR_FRAME.read_text(encoding="utf-8")
    helper_body = _extract_function(source, "nlohmann::json NativeObjectPhaseEvidence")

    for token in [
        "RuntimeSerialNumber()",
        "CRhinoInstanceObject::Cast",
        "InstanceDefinition()",
        "InstanceXform()",
        "instance_definition_id",
        "instance_definition_name",
        "instance_xform",
        "object_found",
        "object_deleted",
        "runtime_serial_number",
        "bbox",
    ]:
        assert token in helper_body

    assert "sourceObjectType" not in helper_body
    assert "source_state" not in helper_body
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_director_native_source.py -q
```

Expected: the two new tests fail because native phase evidence does not exist yet.

- [ ] **Step 3: Commit the red tests**

Run:

```powershell
git add mcp_server/tests/test_director_native_source.py
git commit -m "test(director): pin instance restore diagnostic contract"
```

## Task 2: Native Transform Phase Evidence

**Files:**
- Modify: `src/RookNative/Handlers/DirectorFrame.cpp`
- Modify: `src/RookNative/Handlers/DirectorFrame.h`
- Test: `mcp_server/tests/test_director_native_source.py`

- [ ] **Step 1: Add per-object detail storage to the pose guard header**

In `src/RookNative/Handlers/DirectorFrame.h`, add one private member next to `m_applied` and `m_restored`:

```cpp
    std::vector<nlohmann::json> m_objectDetails;
```

- [ ] **Step 2: Add native evidence helpers**

In `src/RookNative/Handlers/DirectorFrame.cpp`, inside the anonymous namespace near the existing bbox helpers, add:

```cpp
constexpr const char* kDirectorTransformObjectCallPath =
    "pDoc->TransformObject(objRef, xform, true, false, true)";

nlohmann::json XformToDirectorJson(const ON_Xform& xform)
{
    nlohmann::json rows = nlohmann::json::array();
    for (int row = 0; row < 4; ++row)
    {
        nlohmann::json values = nlohmann::json::array();
        for (int col = 0; col < 4; ++col)
            values.push_back(xform.m_xform[row][col]);
        rows.push_back(std::move(values));
    }
    return rows;
}

nlohmann::json NullableUuidToJson(const ON_UUID& id)
{
    if (ON_UuidIsNil(id))
        return nullptr;
    return UuidToString(id);
}

nlohmann::json NativeObjectPhaseEvidence(
    CRhinoDoc* pDoc,
    const FrameObjectTransform& object)
{
    nlohmann::json phase;
    phase["object_id_requested"] = object.objectId;
    phase["document_runtime_serial_number"] = pDoc ? nlohmann::json(pDoc->RuntimeSerialNumber()) : nlohmann::json(nullptr);

    const CRhinoObject* obj = pDoc ? pDoc->LookupObject(object.uuid) : nullptr;
    phase["object_found"] = obj != nullptr;
    phase["object_deleted"] = obj ? nlohmann::json(obj->IsDeleted()) : nlohmann::json(nullptr);

    if (!obj)
    {
        phase["object_id"] = nullptr;
        phase["runtime_serial_number"] = nullptr;
        phase["object_type"] = nullptr;
        phase["bbox"] = nullptr;
        phase["instance_definition_id"] = nullptr;
        phase["instance_definition_name"] = nullptr;
        phase["instance_xform"] = nullptr;
        return phase;
    }

    phase["object_id"] = UuidToString(obj->Attributes().m_uuid);
    phase["runtime_serial_number"] = obj->RuntimeSerialNumber();
    phase["object_type"] = ObjectTypeToString(obj->ObjectType());

    const ON_BoundingBox bbox = obj->BoundingBox();
    phase["bbox"] = bbox.IsValid() ? BoundingBoxToDirectorJson(bbox) : nlohmann::json(nullptr);

    const CRhinoInstanceObject* instance = CRhinoInstanceObject::Cast(obj);
    if (!instance)
    {
        phase["instance_definition_id"] = nullptr;
        phase["instance_definition_name"] = nullptr;
        phase["instance_xform"] = nullptr;
        return phase;
    }

    const CRhinoInstanceDefinition* definition = instance->InstanceDefinition();
    phase["instance_definition_id"] = definition ? NullableUuidToJson(definition->Id()) : nlohmann::json(nullptr);
    phase["instance_definition_name"] = definition ? nlohmann::json(WideToUtf8(definition->Name())) : nlohmann::json(nullptr);
    phase["instance_xform"] = XformToDirectorJson(instance->InstanceXform());
    return phase;
}
```

- [ ] **Step 3: Initialize detail storage in the constructor**

Change the constructor body to resize `m_objectDetails` with the same length as the objects:

```cpp
DirectorObjectPoseGuard::DirectorObjectPoseGuard(CRhinoDoc* pDoc, std::vector<FrameObjectTransform> objects)
    : m_doc(pDoc), m_objects(std::move(objects))
{
    m_applied.resize(m_objects.size(), false);
    m_restored.resize(m_objects.size(), false);
    m_objectDetails.resize(m_objects.size());
}
```

- [ ] **Step 4: Record native evidence in Apply**

Replace the body of `DirectorObjectPoseGuard::Apply()` with:

```cpp
void DirectorObjectPoseGuard::Apply()
{
    for (size_t i = 0; i < m_objects.size(); ++i)
    {
        nlohmann::json detail = InitializeRestoreDetail(m_objects[i], false);
        detail["transform_call_path"] = kDirectorTransformObjectCallPath;
        detail["requested_transform"] = XformToDirectorJson(m_objects[i].delta);
        detail["requested_inverse_transform"] = XformToDirectorJson(m_objects[i].inverseDelta);
        detail["phase_before_apply"] = NativeObjectPhaseEvidence(m_doc, m_objects[i]);

        const bool applied = TransformObjectInPlace(m_doc, m_objects[i], m_objects[i].delta);
        detail["apply_transform_returned"] = applied;
        detail["phase_after_apply"] = NativeObjectPhaseEvidence(m_doc, m_objects[i]);
        m_objectDetails[i] = std::move(detail);

        if (!applied)
            throw DirectorFrameValidationError(
                "native_frame_failed",
                "Failed to apply transform for object: " + m_objects[i].objectId,
                { m_objects[i].objectId });
        m_applied[i] = true;
        m_objectDetails[i]["applied"] = true;
    }
    if (m_doc)
        m_doc->Redraw();
}
```

- [ ] **Step 5: Reuse and complete native evidence in Restore**

In `DirectorObjectPoseGuard::Restore()`, replace the initialization of `detail` with:

```cpp
        nlohmann::json detail = m_objectDetails[static_cast<size_t>(i)].is_object()
            ? m_objectDetails[static_cast<size_t>(i)]
            : InitializeRestoreDetail(object, m_applied[static_cast<size_t>(i)]);
        detail["phase_before_restore"] = NativeObjectPhaseEvidence(m_doc, object);
```

Immediately after the inverse transform attempt, before checking `!transformedBack`, add:

```cpp
        detail["restore_transform_returned"] = transformedBack;
        detail["phase_after_restore"] = NativeObjectPhaseEvidence(m_doc, object);
```

Keep all existing hard-failure branches in the same order. Do not change `kDirectorRestoreBboxTolerance`.

- [ ] **Step 6: Run source tests and verify they pass**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_director_native_source.py mcp_server/tests/test_director_replay_native_source.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit the native diagnostic implementation**

Run:

```powershell
git add src/RookNative/Handlers/DirectorFrame.cpp src/RookNative/Handlers/DirectorFrame.h mcp_server/tests/test_director_native_source.py
git commit -m "fix(director): capture native transform phase evidence"
```

## Task 3: Scratch Live Repro For Instance Restore Semantics

**Files:**
- Modify: `mcp_server/tests/test_director_routes_live.py`
- Modify: `mcp_server/tests/test_director_native_source.py`
- Test: `mcp_server/tests/test_director_routes_live.py::test_director_instance_restore_semantics_large_coordinate_probe`

- [ ] **Step 1: Add the failing live-repro source contract**

Append this test to `mcp_server/tests/test_director_native_source.py`:

```python
def test_director_instance_restore_live_repro_is_scratch_and_two_frame():
    live_source = (REPO_ROOT / "mcp_server" / "tests" / "test_director_routes_live.py").read_text(encoding="utf-8")
    start = live_source.index("async def test_director_instance_restore_semantics_large_coordinate_probe")
    body = live_source[start:]

    assert "fresh_document" in body[: body.index(":")]
    assert "_cleanup_instance_restore_probe(created_ids, block_name)" in body
    assert "rhino_delete" in live_source
    assert "rhino_block_delete" in live_source
    assert '"frame_count": 2' in body
    assert "director.identity_matrix()" in body
    assert "director.translation_matrix([0.0, 0.0, 0.628483])" in body
    assert "125718.338195" in body
    assert "-328450.993563" in body
    assert "InstanceReference" in body
```

- [ ] **Step 2: Run the source contract and verify it fails**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_director_native_source.py::test_director_instance_restore_live_repro_is_scratch_and_two_frame -q
```

Expected: fail because `test_director_instance_restore_semantics_large_coordinate_probe` does not exist yet.

- [ ] **Step 3: Extend live-test imports**

Change the existing conftest import near the top of `mcp_server/tests/test_director_routes_live.py` to:

```python
from .conftest import _block_create, _block_insert, _create_brep
```

- [ ] **Step 4: Add live repro helpers**

Add these helpers near the existing `_translation_matrix()` helper:

```python
def _director_source_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "bbox_min": state["bbox_min"],
        "bbox_max": state["bbox_max"],
        "validation_strength": state["validation_strength"],
        "state_hash": state.get("state_hash"),
    }


def _compiled_object_transform(object_id: str, source_state: dict[str, Any], matrix: list[list[float]]) -> dict[str, Any]:
    return {
        "object_id": object_id,
        "source_state": _director_source_state(source_state),
        "transform": matrix,
    }


def _required_native_phase_keys_present(detail: dict[str, Any]) -> bool:
    required = [
        "transform_call_path",
        "requested_transform",
        "requested_inverse_transform",
        "phase_before_apply",
        "phase_after_apply",
        "phase_before_restore",
        "phase_after_restore",
    ]
    return all(key in detail for key in required)


async def _cleanup_instance_restore_probe(created_ids: list[str], block_name: str) -> None:
    from rook.server import _mcp_tool_executor

    if created_ids:
        await _mcp_tool_executor("rhino_delete", {"ids": created_ids})
    await _mcp_tool_executor(
        "rhino_block_delete",
        {"name": block_name, "deleteInstances": True},
    )
```

- [ ] **Step 5: Add the diagnostic live test**

Append this test after `test_director_run_director_live_smoke_writes_three_frames_and_restores_state`:

```python
async def test_director_instance_restore_semantics_large_coordinate_probe(fresh_document):
    _require_host()
    base = [125718.338195, -328450.993563, -29189.909203]
    size = [24.0, 16.0, 8.0]
    tiny_z = 0.628483
    suffix = uuid4().hex
    block_name = f"director_instance_restore_probe_{suffix}"
    created_ids: list[str] = []

    control_id = await _create_brep(
        base,
        [base[0] + size[0], base[1] + size[1], base[2] + size[2]],
        f"director_instance_restore_control_{suffix}",
    )
    created_ids.append(control_id)
    definition_source_id = await _create_brep(
        [0.0, 0.0, 0.0],
        size,
        f"director_instance_restore_definition_source_{suffix}",
    )
    created_ids.append(definition_source_id)

    try:
        await _block_create(
            block_name,
            [definition_source_id],
            [0.0, 0.0, 0.0],
            replace_with_instance=False,
        )
        instance_id = await _block_insert(block_name, base)
        created_ids.append(instance_id)

        _, state_envelope = await _post_director(
            "object-states",
            {"object_ids": [control_id, instance_id]},
        )
        assert state_envelope["success"] is True
        state_by_id = {
            item["object_id"]: item
            for item in state_envelope["data"]["objects"]
        }
        assert state_by_id[instance_id]["object_type"] == "InstanceReference"

        _, view_envelope = await _post_director("view-state", {"source": {"kind": "active_view"}})
        assert view_envelope["success"] is True
        camera = view_envelope["data"]["camera"]
        if camera["projection"] != "perspective":
            pytest.skip("Active Rhino view is not perspective; frame capture rejects parallel cameras.")

        object_ids = [control_id, instance_id]
        identity_transforms = [
            _compiled_object_transform(object_id, state_by_id[object_id], director.identity_matrix())
            for object_id in object_ids
        ]
        z_transforms = [
            _compiled_object_transform(
                object_id,
                state_by_id[object_id],
                director.translation_matrix([0.0, 0.0, 0.628483]),
            )
            for object_id in object_ids
        ]
        run_id = f"instance_restore_semantics_{suffix}"
        result = await director.run_compiled_track(
            {
                "run_id": run_id,
                "output_root": str(_director_output_root()),
                "resolution": {"width": 320, "height": 180},
                "display": {"mode": "Rendered"},
                "track": {
                    "transform_semantics": "absolute_from_source",
                    "fps": 24,
                    "frame_count": 2,
                    "animated_object_ids": object_ids,
                    "camera_frames": [
                        {"frame_index": 1, "camera": camera},
                        {"frame_index": 2, "camera": camera},
                    ],
                    "object_frames": [
                        {"frame_index": 1, "object_transforms": identity_transforms},
                        {"frame_index": 2, "object_transforms": z_transforms},
                    ],
                },
                "compile_provenance": {
                    "probe": "director_instance_restore_semantics",
                    "tiny_z": tiny_z,
                    "base": base,
                    "control_object_id": control_id,
                    "instance_object_id": instance_id,
                },
            },
            port=_director_port(),
        )

        assert result["state"] in {"complete", "unsafe_failed"}
        run_root = Path(result["run_root"])
        evidence_rows = _read_jsonl(run_root / "logs" / "frame_evidence.jsonl")
        assert evidence_rows

        details = [
            detail
            for row in evidence_rows
            for detail in row["objects"]["details"]
        ]
        control_details = [detail for detail in details if detail["object_id"] == control_id]
        instance_details = [detail for detail in details if detail["object_id"] == instance_id]
        assert control_details
        assert instance_details

        for detail in control_details + instance_details:
            assert _required_native_phase_keys_present(detail), detail
            assert detail["transform_call_path"] == "pDoc->TransformObject(objRef, xform, true, false, true)"

        assert control_details[0]["phase_before_apply"]["object_type"] != "InstanceReference"
        assert instance_details[0]["phase_before_apply"]["object_type"] == "InstanceReference"
        assert instance_details[0]["phase_before_apply"]["instance_definition_name"] == block_name
        assert isinstance(instance_details[0]["phase_before_apply"]["instance_xform"], list)

        print(json.dumps({
            "director_instance_restore_semantics_probe": {
                "run_state": result["state"],
                "run_root": str(run_root),
                "control_object_id": control_id,
                "instance_object_id": instance_id,
                "control_restored": [detail.get("restored") for detail in control_details],
                "instance_restored": [detail.get("restored") for detail in instance_details],
                "control_bbox_max_delta": [detail.get("bbox_max_delta") for detail in control_details],
                "instance_bbox_max_delta": [detail.get("bbox_max_delta") for detail in instance_details],
            }
        }, indent=2, sort_keys=True))
    finally:
        await _cleanup_instance_restore_probe(created_ids, block_name)
```

- [ ] **Step 6: Run source tests and verify the live-test source contract passes**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_director_native_source.py -q
```

Expected: pass.

- [ ] **Step 7: Commit the live repro test**

Run:

```powershell
git add mcp_server/tests/test_director_routes_live.py mcp_server/tests/test_director_native_source.py
git commit -m "test(director): add instance restore semantics live probe"
```

## Task 4: Build, Deploy, And Run The Diagnostic

**Files:**
- No source edits expected.
- Build/deploy artifacts under `src/RookNative/bin/Debug/x64/`.

- [ ] **Step 1: Run Python source tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_director_native_source.py mcp_server/tests/test_director_replay_native_source.py -q
```

Expected: pass.

- [ ] **Step 2: Build RookNative Debug with the working MSVC toolset**

Run:

```powershell
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected: `Build succeeded.`

- [ ] **Step 3: Deploy the Debug native plugin**

Close Rhino before this step if Windows reports the plugin file is locked.

Run:

```powershell
$pluginDir = Join-Path $env:APPDATA "McNeel\Rhinoceros\8.0\Plug-ins\RookNative"
New-Item -ItemType Directory -Force -Path $pluginDir | Out-Null
Copy-Item -LiteralPath "src\RookNative\bin\Debug\x64\RookNative.rhp" -Destination (Join-Path $pluginDir "RookNative.rhp") -Force
Copy-Item -LiteralPath "src\RookNative\bin\Debug\x64\RookNative.pdb" -Destination (Join-Path $pluginDir "RookNative.pdb") -Force
```

Expected: both copy commands complete without error.

- [ ] **Step 4: Restart Rhino and MCP server**

Open a throwaway Rhino session with RookNative loaded. Restart the MCP server so it targets the current branch runtime. Do not open the Pearson model for this diagnostic run.

- [ ] **Step 5: Run the live diagnostic probe**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_director_routes_live.py::test_director_instance_restore_semantics_large_coordinate_probe -q -s
```

Expected: the test passes and prints `director_instance_restore_semantics_probe`. The printed `run_state` may be `complete` or `unsafe_failed`; either state is acceptable for this diagnostic slice as long as the native phase evidence is present.

- [ ] **Step 6: Preserve the diagnostic output**

Record the printed JSON block and the run root path in the next review comment or follow-up spec. Do not start a restore fix in the same commit.

## Task 5: Diagnostic Review Gate

**Files:**
- No source edits unless the evidence is missing required fields.

- [ ] **Step 1: Classify the result**

Use the live probe output:

```text
Simple object restores and InstanceReference fails:
  write the next design for instance-specific restore semantics.

Simple object and InstanceReference both fail:
  investigate matrix convention, source-state setup, or TransformObject call usage.

UUID/runtime serial changes:
  treat TransformObject as replacement-observable for Director bookkeeping.

InstanceXform fails to round-trip while bbox drifts:
  focus the next design on instance transform restore, not bbox serialization.

Both objects round-trip cleanly:
  extend the synthetic fixture toward nested/non-uniform Pearson-like block structure before changing restore.
```

- [ ] **Step 2: Run final static verification**

Run:

```powershell
git diff --check
git status --short --branch
```

Expected: no whitespace errors. Worktree may be clean or may contain only the diagnostic output note if a follow-up doc is being written.

- [ ] **Step 3: Commit any diagnostic-note doc update**

If a doc is updated with the diagnostic result, commit it separately:

```powershell
git add docs/superpowers/specs/2026-07-03-director-instance-restore-semantics-design.md
git commit -m "docs(director): record instance restore diagnostic result"
```

## Execution Mode

Use subagent-driven execution, but only one task at a time:

1. Task 1 worker: red source tests.
2. Review checkpoint.
3. Task 2 worker: native phase evidence.
4. Review checkpoint plus source tests.
5. Task 3 worker: scratch live repro.
6. Review checkpoint.
7. Lead coder: build/deploy/live diagnostic and result classification.

No worker should begin a semantic restore fix until Task 5 classifies the diagnostic evidence.
