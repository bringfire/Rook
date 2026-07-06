# Director v3 Slice 1: Take Package Builder — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the immutable take package: a `POST /document/save-copy` native route with proven invariants, and a Python `package_take` builder that writes `scene.3dm` + `scene_manifest.json` + `motion.json` + `camera.json` + `status.json` with hashes.

**Architecture:** The snapshot boundary from `docs/superpowers/specs/2026-07-06-director-v3-snapshot-boundary-design.md`. Native gains one route (save-copy, mirroring `HandleDocumentSave` but with `SetUpdateDocumentPath(false)`); Python gains one module (`director_take_package.py`) orchestrating native calls through the existing `call_rhino` bridge; MCP gains one tool (`rhino_director_package_take`) plus a `save_copy` action on `rhino_document_ops`. Worker prepare/compile/capture are Slices 2–3, NOT in this plan.

**Tech Stack:** C++ (Rhino 8 C++ SDK, httplib, nlohmann::json), Python 3 (httpx via `rook.bridge.call_rhino`, pytest, pytest-asyncio).

## Global Constraints

- Work happens in the worktree `.worktrees/director-v3-snapshot-boundary` on branch `codex/director-v3-snapshot-boundary`. All paths below are relative to the worktree root.
- Native build: `cmd /c scripts\build-native.bat` (never invoke msbuild directly — user rule). Deploy: `cmd /c scripts\deploy-native.bat` requires Rhino **closed**; only the user launches/closes Rhino (hand them the step, verify with `rhino_ping`).
- Python tests run from `mcp_server/`: `python -m pytest tests/<file> -v`. Live tests carry `pytest.mark.requires_rhino` and skip when the native plugin is not discoverable.
- `scene.3dm` must include render meshes — never SaveSmall on the save-copy path (spec).
- The save-copy invariants (SDK-documented for `SetUpdateDocumentPath(false)`): document path, title, and modified state unchanged "under any circumstances"; the undo stack is proven unchanged by the live gate. Do not trust these until the live gate passes (spec: "a live gate, not an assumption").
- New MCP tools must be classified in BOTH `mcp_server/src/rook/agent/targeting.py` AND `mcp_server/src/rook/mcp_tool_profiles.py`, and surface counts are pinned in two test files — grep for the set/group name containing `rhino_director_compile_motion`, never search for the raw number (project memory rule).
- Error taxonomy for this slice (typed codes on `DirectorTakePackageError`): `invalid_input`, `document_not_saved`, `save_copy_failed`, `save_copy_invariant_violation`, `package_already_exists`, `display_mode_missing`, `actor_set_resolution_failed`, `source_instance_mismatch`, `package_state_drift`, `tight_bbox_unavailable`.
- Save-copy proof scope (honest claims only): the route evidence and live gate prove path, title, and modified-flag invariance plus undo-stack survival, and record `save_small_used: false` as route evidence. A nonzero file with a valid 3dm header proves the copy exists — it does NOT prove render meshes are present; render-mesh/open-fidelity proof belongs to the Slice 2 worker gate.
- Use `rg` (ripgrep), not `grep`, for all search instructions in this plan.
- Tight-bbox rule (spec DEC-021 lineage): `tight_object` is the ONLY bbox method admissible as manifest evidence. `/block/objects-detailed` already computes tight bbox first but silently falls back to the loose cached bbox (`BlocksHandler.cpp:3496-3498`) with no method label — Task 1 adds the label, and the package builder hard-fails (`tight_bbox_unavailable`) for any member whose bbox is not labeled `tight_object`. Loose/unlabeled bboxes never enter `scene_manifest.json` as evidence. Manifest bbox values are rounded to 4 decimal places with the rounding policy recorded.

---

### Task 1: Native `POST /document/save-copy` route

**Files:**
- Modify: `src/RookNative/Handlers/DocumentOpsHandler.cpp` (add handler after `HandleDocumentSave`, which ends at ~line 271)
- Modify: the header declaring `HandleDocumentSave` (find it: `rg -n "HandleDocumentSave" src/RookNative/Handlers/ -g "*.h"`) — add `HandleDocumentSaveCopy` beside it
- Modify: `src/RookNative/RookServer.cpp` (route registration near line 1183 where `/document/save` is registered; member forwarder near line 2824 where `CRookServer::HandleDocumentSave` forwards)
- Modify: `src/RookNative/RookServer.h` (member declaration beside `HandleDocumentSave` — find with rg)
- Modify: `src/RookNative/Handlers/BlocksHandler.cpp:3496-3504` (label the bbox method in `/block/objects-detailed`)
- Modify: `src/RookNative/Handlers/BlocksHandler.cpp:2187-2203` (emit full instance xform + definition identity on `/block/instances`)

**Interfaces:**
- Produces: `POST /document/save-copy` with body `{"path": "<absolute .3dm target>"}`. Success data:
  `{"copy_path": str, "path_before": str, "path_after": str, "title_before": str, "title_after": str, "modified_before": bool, "modified_after": bool, "save_small_used": false}`.
  Errors use the standard `CRookServer::SendError` envelope. Task 3's Python treats any non-success as `save_copy_failed`.
- Produces: `/block/instances` entries additionally carry `"xform"` (nested 4x4 row-major, same convention as director tracks), `"definitionId"`, `"definitionName"`.

- [ ] **Step 1: Add the handler to `DocumentOpsHandler.cpp`** (directly below `HandleDocumentSave`; mirror its structure exactly — same `ParseBodyAndDocSn`, `ValidateFilePath`, dispatcher, try/catch):

```cpp
// ─── POST /document/save-copy ───────────────────────────────────────
// Writes the active document to a target path WITHOUT retargeting the
// document, changing its modified flag, or touching its undo stack.
// SDK contract: CRhinoFileWriteOptions::SetUpdateDocumentPath(false) =>
// "The document's default file path, title and modified state will not
// be changed under any circumstances." Render meshes stay included.

void HandleDocumentSaveCopy(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::string path;
    if (body.contains("path") && body["path"].is_string())
        path = body["path"].get<std::string>();

    if (path.empty())
    {
        CRookServer::SendError(res, "Missing required parameter 'path'");
        return;
    }

    std::string pathErr = Rook::ValidateFilePath(path);
    if (!pathErr.empty())
    {
        CRookServer::SendError(res, pathErr);
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, path]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        const ON_wString pathBefore = pDoc->GetPathName();
        const ON_wString titleBefore = pDoc->GetTitle();
        const bool modifiedBefore = pDoc->IsModified();

        ON_wString copyPath = Utf8ToWide(path);

        CRhinoFileWriteOptions opts;
        opts.SetFileName(static_cast<const wchar_t*>(copyPath));
        opts.SetUpdateDocumentPath(false);
        opts.SetUseBatchMode(true);
        // Render meshes: default is included; never SetIncludeRenderMeshes(false) here.

        if (!pDoc->WriteFile(opts))
            throw std::runtime_error("save-copy write failed");

        WriteResult wr;
        wr.success = true;
        wr.data["copy_path"] = path;
        wr.data["path_before"] = WideToUtf8(pathBefore);
        wr.data["path_after"] = WideToUtf8(pDoc->GetPathName());
        wr.data["title_before"] = WideToUtf8(titleBefore);
        wr.data["title_after"] = WideToUtf8(pDoc->GetTitle());
        wr.data["modified_before"] = modifiedBefore;
        wr.data["modified_after"] = pDoc->IsModified();
        wr.data["save_small_used"] = false;
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendError(res, result.error);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}
```

- [ ] **Step 2: Declare it in the Handlers header** — one line beside the existing `HandleDocumentSave` declaration:

```cpp
void HandleDocumentSaveCopy(const httplib::Request& req, httplib::Response& res);
```

- [ ] **Step 3: Register the route in `RookServer.cpp`** — beside the `/document/save` registration (~line 1183):

```cpp
m_server->Post("/document/save-copy", [this](const httplib::Request& req, httplib::Response& res) {
    HandleDocumentSaveCopy(req, res);
});
```

And the member forwarder beside `CRookServer::HandleDocumentSave` (~line 2824), plus its declaration in `RookServer.h` beside `HandleDocumentSave`:

```cpp
void CRookServer::HandleDocumentSaveCopy(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleDocumentSaveCopy(req, res);
}
```

- [ ] **Step 4: Label the bbox method in `/block/objects-detailed`** — in `BlocksHandler.cpp`, replace the silent-fallback bbox block (lines 3496–3504):

```cpp
            ON_BoundingBox bbox;
            const bool tight = obj->GetTightBoundingBox(bbox) && bbox.IsValid();
            if (!tight)
                bbox = obj->BoundingBox();
            if (bbox.IsValid())
            {
                info["bbox"]["min"] = { bbox.Min().x, bbox.Min().y, bbox.Min().z };
                info["bbox"]["max"] = { bbox.Max().x, bbox.Max().y, bbox.Max().z };
                info["bboxMethod"] = tight ? "tight_object" : "loose_fallback";
                defBbox.Union(bbox);
            }
            else
            {
                info["bboxMethod"] = "unavailable";
            }
```

This is additive — existing consumers keep the `bbox` field unchanged; the new `bboxMethod` label lets Director callers reject non-tight evidence (spec: never inherit the silent fallback's pass semantics).

- [ ] **Step 5: Emit full instance xform + definition identity on `/block/instances`** — in `HandleBlockInstances` (`BlocksHandler.cpp`, instance JSON built at lines 2195–2201), the full `ON_Xform xf` is already in hand (line 2187) but only insertion point and derived scale are serialized. Add, after `ji["name"] = ...`:

```cpp
            nlohmann::json xformRows = nlohmann::json::array();
            for (int r = 0; r < 4; ++r)
                xformRows.push_back({ xf[r][0], xf[r][1], xf[r][2], xf[r][3] });
            ji["xform"] = std::move(xformRows);          // nested 4x4 row-major,
                                                          // same convention as
                                                          // director tracks
            ji["definitionId"] = UuidToString(pIdef->Id());
            ji["definitionName"] = WideToUtf8(pIdef->Name());
```

Additive — existing consumers (`rhino_block_instances`) keep their fields.

- [ ] **Step 6: Build**

Run: `cmd /c scripts\build-native.bat`
Expected: build succeeds with zero errors. (No native unit-test framework exists in this repo; the route's behavior test is the Task 5 live gate.)

- [ ] **Step 7: Commit**

```bash
git add src/RookNative
git commit -m "feat(director): save-copy route, bbox method labels, instance xform evidence"
```

---

### Task 2: `rhino_document_ops` gains action `save_copy`

**Files:**
- Modify: `mcp_server/src/rook/server.py` — dispatch at the `case "rhino_document_ops":` block (line ~14845), and the `rhino_document_ops` Tool `inputSchema`/description (find with `rg -n 'name="rhino_document_ops"' mcp_server/src/rook/server.py`)

**Interfaces:**
- Produces: MCP `rhino_document_ops` accepts `{"action": "save_copy", "path": "<target .3dm>"}` and forwards to `POST /document/save-copy`, returning the native evidence payload unchanged.

- [ ] **Step 1: Add the dispatch branch** — in the `rhino_document_ops` case, after the `save` branch:

```python
            elif action == "save_copy":
                path = arguments.get("path")
                if not path:
                    result = {"success": False, "data": "Missing required parameter 'path' for save_copy action"}
                else:
                    result = await call_rhino("/document/save-copy", "POST", {"path": path})
```

- [ ] **Step 2: Update the tool schema** — add `save_copy` to the `action`/`operation` enum lists in the `rhino_document_ops` Tool definition and append one description line:

```
- save_copy: Write the active document to a target path WITHOUT retargeting the document, changing its modified flag, or touching its undo stack (requires 'path'). Includes render meshes.
```

- [ ] **Step 3: Sanity-check the module imports**

Run: `cd mcp_server && python -c "import rook.server"`
Expected: no exception.

- [ ] **Step 4: Commit**

```bash
git add mcp_server/src/rook/server.py
git commit -m "feat(director): expose save_copy action on rhino_document_ops"
```

---

### Task 3: `director_take_package.py` — the package builder (TDD)

**Files:**
- Create: `mcp_server/src/rook/director_take_package.py`
- Test: `mcp_server/tests/test_director_take_package.py`

**Interfaces:**
- Consumes: `rook.bridge.call_rhino(endpoint, method, data, port=...)` returning the internal envelope `{"success": bool, "data": ...}`; native routes `GET /document`, `POST /document/save-copy`, `POST /block/instances` (body `{"name": <block>}` → `{"instances": [{"id","layer","name","xform","definitionId","definitionName",...}]}` — xform/definition fields from Task 1), `POST /block/objects-detailed` (body `{"name": <block>}` → `{"objects": [{"id","index","type","layer","name","bbox":{"min","max"},"bboxMethod","visible",...}]}`), `GET /display-modes` (→ `{"modes": [{"id","name","isActive"}]}`).
- Produces: `async def package_take(arguments: dict, *, call_native=call_rhino, port: int | None = None, now_fn=None) -> dict` and `class DirectorTakePackageError(Exception)` with `.code: str` and `.to_data() -> {"code", "message"}`. Task 4 dispatches to `package_take`; Task 5 calls it live.

**Input contract (`arguments`):**

```json
{
  "output_root": "<existing or creatable directory>",
  "take_id": "pearson_take_001",
  "actor_sets": [
    {"actor_set_id": "roof_uplift_001",
     "block_name": "3D_BLOCK_ARCH_ROOF_0502 UPLIFT ROOF - VERTICAL",
     "source_top_level_object_id": "a28cbdb5-51fa-46b2-b18b-ab880b54ded7"}
  ],
  "motion": {"timeline": {"fps": 24, "frame_count": 48}, "motion": [{"target": "roof_uplift_001", "keyframes": [{"t": 1, "translate": [0, 0, 8000]}]}]},
  "camera": null,
  "display_modes": ["Arctic", "Render_Layer_Color_AMR"]
}
```

**Package layout produced** (all under `<output_root>/<take_id>/`): `scene.3dm`, `scene_manifest.json`, `motion.json`, `camera.json` (only when camera given), `status.json`.

- [ ] **Step 1: Write the failing tests** — `mcp_server/tests/test_director_take_package.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from rook import director_take_package as dtp

pytestmark = pytest.mark.asyncio

DOC_PATH = "C:/models/live.3dm"
BLOCK = "ROOF_BLOCK"
INSTANCE_ID = "a28cbdb5-51fa-46b2-b18b-ab880b54ded7"


def _doc_data(modified: bool = False, object_count: int = 112) -> dict[str, Any]:
    return {"name": "live.3dm", "path": DOC_PATH, "modified": modified,
            "objectCount": object_count, "layerCount": 5, "units": "millimeters"}


def _members(loose_second: bool = False) -> list[dict[str, Any]]:
    return [
        {"id": "8136d5f4-6d5c-47df-8f89-590df238c8e7", "index": 0, "type": "Brep",
         "layer": "001_MATERIAL::001_01_GARDEN WOOD", "name": "",
         "bbox": {"min": [0, 0, 0], "max": [10.123456, 10, 10]},
         "bboxMethod": "tight_object", "visible": True},
        {"id": "9247e6a5-7e6d-58e0-9f9a-6a1ef349d9f8", "index": 1, "type": "Curve",
         "layer": "000_SETOUT LINES::000_SETOUT_PRIMARY", "name": "axis",
         "bbox": {"min": [0, 0, 0], "max": [5, 0, 0]},
         "bboxMethod": "loose_fallback" if loose_second else "tight_object",
         "visible": True},
    ]


IDENTITY_XFORM = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0],
                  [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]


def make_fake_native(*, modified=False, save_copy_ok=True, invariants_hold=True,
                     modes=("Arctic", "Render_Layer_Color_AMR"), drift=False,
                     loose_second_member=False, instance_id=INSTANCE_ID,
                     member_drift=False, instance_xform_drift=False,
                     legacy_evidence=False):
    calls: list[tuple[str, str, dict | None]] = []
    doc_reads = {"n": 0}
    member_reads = {"n": 0}
    instance_reads = {"n": 0}

    async def fake(endpoint: str, method: str = "GET", data: dict | None = None,
                   port: int | None = None, **kwargs: Any):
        calls.append((endpoint, method, data))
        if endpoint == "/document":
            doc_reads["n"] += 1
            count = 112 if (doc_reads["n"] == 1 or not drift) else 999
            return {"success": True, "data": _doc_data(modified=modified, object_count=count)}
        if endpoint == "/document/save-copy":
            if not save_copy_ok:
                return {"success": False, "data": "route not found"}
            target = data["path"]
            Path(target).write_bytes(b"3D Geometry File Format fake")
            if legacy_evidence:
                # Old native build: no title/save_small fields in evidence.
                return {"success": True, "data": {
                    "copy_path": target, "path_before": DOC_PATH,
                    "path_after": DOC_PATH, "modified_before": modified,
                    "modified_after": modified}}
            after = modified if invariants_hold else (not modified)
            return {"success": True, "data": {
                "copy_path": target, "path_before": DOC_PATH, "path_after": DOC_PATH,
                "title_before": "live", "title_after": "live",
                "modified_before": modified, "modified_after": after,
                "save_small_used": False}}
        if endpoint == "/block/instances":
            assert data == {"name": BLOCK}
            instance_reads["n"] += 1
            xform = IDENTITY_XFORM
            if instance_xform_drift and instance_reads["n"] > 1:
                # Same instance id, moved between enumeration and snapshot.
                xform = [[1.0, 0.0, 0.0, 5.0], [0.0, 1.0, 0.0, 0.0],
                         [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
            return {"success": True, "data": {"blockName": BLOCK, "instances": [{
                "id": instance_id, "layer": "004_DIAGRAM::STRUCTURE", "name": "",
                "xform": xform,
                "definitionId": "d1d1d1d1-0000-0000-0000-000000000001",
                "definitionName": BLOCK}]}}
        if endpoint == "/block/objects-detailed":
            assert data == {"name": BLOCK}
            member_reads["n"] += 1
            members = _members(loose_second=loose_second_member)
            if member_drift and member_reads["n"] > 1:
                # Simulate a dirty-doc edit between enumeration and snapshot:
                # same count, changed layer — object count would NOT catch this.
                members[0]["layer"] = "001_MATERIAL::001_01_CONCRETE"
            return {"success": True, "data": {"name": BLOCK, "objects": members}}
        if endpoint == "/display-modes":
            return {"success": True, "data": {"modes": [
                {"id": f"id-{m}", "name": m, "isActive": False} for m in modes]}}
        raise AssertionError(f"unexpected endpoint {endpoint}")

    fake.calls = calls
    return fake


def _args(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    args: dict[str, Any] = {
        "output_root": str(tmp_path / "packages"),
        "take_id": "take_001",
        "actor_sets": [{"actor_set_id": "roof_001", "block_name": BLOCK,
                        "source_top_level_object_id": INSTANCE_ID}],
        "motion": {"timeline": {"fps": 24, "frame_count": 48},
                   "motion": [{"target": "roof_001",
                               "keyframes": [{"t": 1, "translate": [0, 0, 8000]}]}]},
        "camera": None,
        "display_modes": ["Arctic", "Render_Layer_Color_AMR"],
    }
    args.update(overrides)
    return args


async def test_happy_path_writes_package(tmp_path):
    fake = make_fake_native()
    result = await dtp.package_take(_args(tmp_path), call_native=fake)

    root = Path(result["package_root"])
    assert root == tmp_path / "packages" / "take_001"
    for f in ("scene.3dm", "scene_manifest.json", "motion.json", "status.json"):
        assert (root / f).is_file(), f
    assert not (root / "camera.json").exists()  # camera was None
    # Staging dir was promoted atomically; no remnant left behind.
    assert not (tmp_path / "packages" / ".take_001.staging").exists()

    manifest = json.loads((root / "scene_manifest.json").read_text())
    assert manifest["schema_version"] == dtp.PACKAGE_SCHEMA_VERSION
    assert manifest["scene"]["mechanism"] == "save_copy"
    assert manifest["source_document"]["path"] == DOC_PATH
    [actor_set] = manifest["actor_sets"]
    assert actor_set["member_count"] == 2
    src = actor_set["source_instance"]
    assert src["instance_id"] == INSTANCE_ID
    assert src["definition_name"] == BLOCK
    assert src["definition_id"] == "d1d1d1d1-0000-0000-0000-000000000001"
    assert src["xform"] == IDENTITY_XFORM
    assert len(src["xform_sha256"]) == 64
    m0 = actor_set["members"][0]
    assert m0["actor_member_id"] == "roof_001_member_0000"
    assert m0["definition_object_index"] == 0
    assert m0["definition_object_id"] == "8136d5f4-6d5c-47df-8f89-590df238c8e7"
    assert m0["expected"]["layer"] == "001_MATERIAL::001_01_GARDEN WOOD"
    assert m0["bbox_evidence"]["bbox_method"] == "tight_object"
    assert m0["bbox_evidence"]["validation_strength"] == "tight_bbox"
    assert m0["bbox_evidence"]["rounding_policy"] == "round_to_4_decimal_places"
    assert m0["bbox_evidence"]["max"][0] == 10.1235  # rounded to 4 decimals
    dm = {d["name"]: d for d in manifest["display_mode_requirements"]}
    assert dm["Arctic"]["id"] == "id-Arctic"
    assert manifest["hashes"]["motion_json_sha256"] == result["hashes"]["motion_json_sha256"]
    assert manifest["hashes"]["scene_3dm_sha256"]

    status = json.loads((root / "status.json").read_text())
    assert status["phase"] == "packaged"
    assert status["package_id"] == result["package_id"]


async def test_modified_doc_without_save_copy_fails_document_not_saved(tmp_path):
    fake = make_fake_native(modified=True, save_copy_ok=False)
    with pytest.raises(dtp.DirectorTakePackageError) as exc:
        await dtp.package_take(_args(tmp_path), call_native=fake)
    assert exc.value.code == "document_not_saved"


async def test_unmodified_doc_without_save_copy_falls_back_to_raw_copy(tmp_path):
    src = tmp_path / "live.3dm"
    src.write_bytes(b"3D Geometry File Format fake-saved")
    fake = make_fake_native(modified=False, save_copy_ok=False)
    args = _args(tmp_path)
    result = await dtp.package_take(args, call_native=fake, source_path_override=str(src))
    manifest = json.loads((Path(result["package_root"]) / "scene_manifest.json").read_text())
    assert manifest["scene"]["mechanism"] == "raw_copy_saved_file"


async def test_save_copy_invariant_violation_is_typed(tmp_path):
    fake = make_fake_native(invariants_hold=False)
    with pytest.raises(dtp.DirectorTakePackageError) as exc:
        await dtp.package_take(_args(tmp_path), call_native=fake)
    assert exc.value.code == "save_copy_invariant_violation"


async def test_missing_display_mode_fails(tmp_path):
    fake = make_fake_native(modes=("Arctic",))
    with pytest.raises(dtp.DirectorTakePackageError) as exc:
        await dtp.package_take(_args(tmp_path), call_native=fake)
    assert exc.value.code == "display_mode_missing"
    assert "Render_Layer_Color_AMR" in str(exc.value)


async def test_existing_package_dir_conflicts(tmp_path):
    (tmp_path / "packages" / "take_001").mkdir(parents=True)
    fake = make_fake_native()
    with pytest.raises(dtp.DirectorTakePackageError) as exc:
        await dtp.package_take(_args(tmp_path), call_native=fake)
    assert exc.value.code == "package_already_exists"


async def test_document_drift_between_enumeration_and_finish_fails(tmp_path):
    fake = make_fake_native(drift=True)
    with pytest.raises(dtp.DirectorTakePackageError) as exc:
        await dtp.package_take(_args(tmp_path), call_native=fake)
    assert exc.value.code == "package_state_drift"


async def test_bad_take_id_rejected(tmp_path):
    fake = make_fake_native()
    with pytest.raises(dtp.DirectorTakePackageError) as exc:
        await dtp.package_take(_args(tmp_path, take_id="../evil"), call_native=fake)
    assert exc.value.code == "invalid_input"


async def test_loose_bbox_member_fails_tight_bbox_unavailable(tmp_path):
    """DEC-021: tight_object is the only admissible manifest bbox evidence."""
    fake = make_fake_native(loose_second_member=True)
    with pytest.raises(dtp.DirectorTakePackageError) as exc:
        await dtp.package_take(_args(tmp_path), call_native=fake)
    assert exc.value.code == "tight_bbox_unavailable"
    # The failing member is named so the user can fix or exclude it.
    assert "roof_001_member_0001" in str(exc.value)


async def test_id_not_an_instance_of_block_fails_source_instance_mismatch(tmp_path):
    """The claimed source id must be a CURRENT instance of the named block."""
    fake = make_fake_native(instance_id="00000000-0000-0000-0000-000000000099")
    with pytest.raises(dtp.DirectorTakePackageError) as exc:
        await dtp.package_take(_args(tmp_path), call_native=fake)
    assert exc.value.code == "source_instance_mismatch"


async def test_actor_member_drift_after_snapshot_fails(tmp_path):
    """Same object count, changed member layer between enumeration and
    snapshot: the deep actor-state gate must catch what count cannot."""
    fake = make_fake_native(member_drift=True)
    with pytest.raises(dtp.DirectorTakePackageError) as exc:
        await dtp.package_take(_args(tmp_path), call_native=fake)
    assert exc.value.code == "package_state_drift"
    # Atomicity: a failed run must not create the final package directory,
    # so a retry never hits package_already_exists.
    assert not (tmp_path / "packages" / "take_001").exists()


async def test_source_instance_xform_drift_after_snapshot_fails(tmp_path):
    """Same instance id, moved (xform changed) between enumeration and
    snapshot: instance identity/xform drift is gated, not just members."""
    fake = make_fake_native(instance_xform_drift=True)
    with pytest.raises(dtp.DirectorTakePackageError) as exc:
        await dtp.package_take(_args(tmp_path), call_native=fake)
    assert exc.value.code == "package_state_drift"
    assert not (tmp_path / "packages" / "take_001").exists()


async def test_legacy_save_copy_evidence_fails_invariant_check(tmp_path):
    """Old native builds returning partial evidence (no title/save_small
    fields) must not pass the invariant gate."""
    fake = make_fake_native(legacy_evidence=True)
    with pytest.raises(dtp.DirectorTakePackageError) as exc:
        await dtp.package_take(_args(tmp_path), call_native=fake)
    assert exc.value.code == "save_copy_invariant_violation"
    assert "title" in str(exc.value)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd mcp_server && python -m pytest tests/test_director_take_package.py -v`
Expected: FAIL — `ModuleNotFoundError` / `AttributeError` on `rook.director_take_package`.

- [ ] **Step 3: Implement `mcp_server/src/rook/director_take_package.py`:**

```python
"""Director v3 Slice 1: immutable take-package builder.

Spec: docs/superpowers/specs/2026-07-06-director-v3-snapshot-boundary-design.md
Builds <output_root>/<take_id>/ with scene.3dm (save-copy snapshot),
scene_manifest.json (member + display-mode contract), motion.json (authoring),
camera.json (optional), status.json (job ledger). Never mutates the live doc.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bridge import call_rhino

PACKAGE_SCHEMA_VERSION = 1
_TAKE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class DirectorTakePackageError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code

    def to_data(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self)}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> str:
    text = json.dumps(payload, indent=2, sort_keys=True)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _native(call_native, endpoint: str, method: str, data: dict | None,
                  port: int | None, error_code: str) -> Any:
    envelope = await call_native(endpoint, method, data, port=port)
    if not isinstance(envelope, dict) or not envelope.get("success"):
        detail = envelope.get("data") if isinstance(envelope, dict) else envelope
        raise DirectorTakePackageError(error_code, f"{endpoint} failed: {detail}")
    return envelope.get("data")


def _validate(arguments: dict[str, Any]) -> dict[str, Any]:
    take_id = arguments.get("take_id")
    if not isinstance(take_id, str) or not _TAKE_ID_RE.match(take_id):
        raise DirectorTakePackageError(
            "invalid_input", "take_id must match [A-Za-z0-9._-]{1,128}")
    output_root = arguments.get("output_root")
    if not isinstance(output_root, str) or not output_root.strip():
        raise DirectorTakePackageError("invalid_input", "output_root is required")
    actor_sets = arguments.get("actor_sets")
    if not isinstance(actor_sets, list) or not actor_sets:
        raise DirectorTakePackageError("invalid_input", "actor_sets must be non-empty")
    for entry in actor_sets:
        if not isinstance(entry, dict):
            raise DirectorTakePackageError("invalid_input", "actor_sets entries must be objects")
        for key in ("actor_set_id", "block_name", "source_top_level_object_id"):
            if not isinstance(entry.get(key), str) or not entry[key]:
                raise DirectorTakePackageError("invalid_input", f"actor_sets[].{key} is required")
        if not _UUID_RE.match(entry["source_top_level_object_id"]):
            raise DirectorTakePackageError(
                "invalid_input", "source_top_level_object_id must be a UUID")
    motion = arguments.get("motion")
    if not isinstance(motion, dict) or not motion:
        raise DirectorTakePackageError("invalid_input", "motion (authoring request) is required")
    display_modes = arguments.get("display_modes")
    if (not isinstance(display_modes, list) or not display_modes
            or not all(isinstance(m, str) and m for m in display_modes)):
        raise DirectorTakePackageError(
            "invalid_input", "display_modes must be a non-empty list of mode names")
    camera = arguments.get("camera")
    if camera is not None and not isinstance(camera, dict):
        raise DirectorTakePackageError("invalid_input", "camera must be an object or null")
    return {"take_id": take_id, "output_root": output_root, "actor_sets": actor_sets,
            "motion": motion, "display_modes": display_modes, "camera": camera}


async def _resolve_actor_state(call_native, actor_sets: list[dict[str, Any]],
                               port: int | None) -> list[dict[str, Any]]:
    """Resolve source instances + member evidence. Called twice: before the
    scene snapshot and after it — the two results must be identical
    (deep drift gate), so everything here must be deterministic."""
    resolved = []
    for entry in actor_sets:
        instances = await _native(call_native, "/block/instances", "POST",
                                  {"name": entry["block_name"]}, port,
                                  "actor_set_resolution_failed")
        match = next((inst for inst in (instances.get("instances") or [])
                      if inst.get("id") == entry["source_top_level_object_id"]), None)
        if match is None:
            raise DirectorTakePackageError(
                "source_instance_mismatch",
                f"object {entry['source_top_level_object_id']} is not a current "
                f"instance of block '{entry['block_name']}'")
        xform = match.get("xform")
        if not xform:
            raise DirectorTakePackageError(
                "source_instance_mismatch",
                "native /block/instances returned no xform; deploy the Slice 1 "
                "native build")
        xform_rounded = [[round(v, 6) for v in row] for row in xform]
        source_instance = {
            "instance_id": match["id"],
            "definition_id": match.get("definitionId"),
            "definition_name": match.get("definitionName"),
            "layer": match.get("layer"),
            "name": match.get("name") or "",
            "xform": xform_rounded,
            "xform_sha256": hashlib.sha256(
                json.dumps(xform_rounded).encode("utf-8")).hexdigest(),
        }

        block = await _native(call_native, "/block/objects-detailed", "POST",
                              {"name": entry["block_name"]}, port,
                              "actor_set_resolution_failed")
        objects = block.get("objects") or []
        if not objects:
            raise DirectorTakePackageError(
                "actor_set_resolution_failed",
                f"block '{entry['block_name']}' has no definition objects")
        members = []
        non_tight: list[str] = []
        for obj in objects:
            index = obj.get("index")
            member_id = f"{entry['actor_set_id']}_member_{index:04d}"
            bbox = obj.get("bbox") or {}
            bbox_method = obj.get("bboxMethod")
            if bbox_method != "tight_object":
                # DEC-021: loose/unlabeled bbox never enters the manifest as
                # evidence. Old native builds (no bboxMethod field) fail here
                # too — deploy the labeled build.
                non_tight.append(f"{member_id} (bboxMethod={bbox_method!r})")
                continue
            members.append({
                "actor_member_id": member_id,
                "definition_object_index": index,
                "definition_object_id": obj.get("id"),
                "expected": {"type": obj.get("type"), "layer": obj.get("layer"),
                             "name": obj.get("name") or ""},
                "bbox_evidence": {
                    "bbox_method": "tight_object",
                    "bbox_space": "definition_object",
                    "min": [round(v, 4) for v in (bbox.get("min") or [])],
                    "max": [round(v, 4) for v in (bbox.get("max") or [])],
                    "rounding_policy": "round_to_4_decimal_places",
                    "validation_strength": "tight_bbox",
                },
            })
        if non_tight:
            raise DirectorTakePackageError(
                "tight_bbox_unavailable",
                "tight bbox unavailable for members: " + ", ".join(non_tight))
        resolved.append({
            "actor_set_id": entry["actor_set_id"],
            "block_name": entry["block_name"],
            "source_top_level_object_id": entry["source_top_level_object_id"],
            "source_instance": source_instance,
            "member_count": len(members),
            "members": members,
        })
    return resolved


async def package_take(arguments: dict[str, Any], *, call_native=call_rhino,
                       port: int | None = None, now_fn=_utc_now,
                       source_path_override: str | None = None) -> dict[str, Any]:
    spec = _validate(arguments)

    package_root = Path(spec["output_root"]).expanduser().resolve() / spec["take_id"]
    if package_root.exists():
        raise DirectorTakePackageError(
            "package_already_exists",
            f"package directory already exists: {package_root}")

    doc = await _native(call_native, "/document", "GET", None, port, "invalid_input")
    doc_path = source_path_override or doc.get("path") or ""
    doc_modified = bool(doc.get("modified"))
    doc_object_count = doc.get("objectCount")

    # Display-mode requirements: verify every requested mode exists NOW, by name.
    modes_data = await _native(call_native, "/display-modes", "GET", None, port,
                               "display_mode_missing")
    available = {m.get("name"): m.get("id") for m in modes_data.get("modes", [])}
    missing = [m for m in spec["display_modes"] if m not in available]
    if missing:
        raise DirectorTakePackageError(
            "display_mode_missing",
            f"requested display modes not present in this Rhino: {missing}")
    display_mode_requirements = [
        {"name": name, "id": available[name], "settings_fingerprint": None}
        for name in spec["display_modes"]
    ]

    # Actor state resolution (source instance identity + member evidence).
    # Definition-object order = provenance order.
    actor_sets_manifest = await _resolve_actor_state(
        call_native, spec["actor_sets"], port)

    # Stage everything; promote atomically on success so a failed run can
    # never poison the output directory (retry-safe: a failed attempt leaves
    # no <take_id> dir behind, so retries do not hit package_already_exists).
    staging_root = package_root.parent / f".{spec['take_id']}.staging"
    if staging_root.exists():
        shutil.rmtree(staging_root)  # leftover from a crashed run; ours by construction
    staging_root.mkdir(parents=True, exist_ok=False)
    scene_path = staging_root / "scene.3dm"

    # Scene snapshot: save-copy preferred; raw copy only for a saved, unmodified doc.
    save_copy = await call_native("/document/save-copy", "POST",
                                  {"path": str(scene_path)}, port=port)
    if isinstance(save_copy, dict) and save_copy.get("success"):
        evidence = save_copy.get("data") or {}
        required = ("path_before", "path_after", "title_before", "title_after",
                    "modified_before", "modified_after", "save_small_used")
        missing_fields = [k for k in required if k not in evidence]
        if missing_fields:
            raise DirectorTakePackageError(
                "save_copy_invariant_violation",
                f"save-copy evidence incomplete (old native build?); "
                f"missing: {missing_fields}")
        if (evidence["path_before"] != evidence["path_after"]
                or evidence["title_before"] != evidence["title_after"]
                or evidence["modified_before"] != evidence["modified_after"]
                or evidence["save_small_used"] is not False):
            raise DirectorTakePackageError(
                "save_copy_invariant_violation",
                f"save-copy changed document state: {evidence}")
        scene_mechanism = "save_copy"
        scene_evidence = evidence
    elif doc_modified:
        raise DirectorTakePackageError(
            "document_not_saved",
            "document has unsaved edits and /document/save-copy is unavailable; "
            "save the document or deploy a native build with save-copy")
    else:
        if not doc_path:
            raise DirectorTakePackageError(
                "save_copy_failed", "document has no path to raw-copy from")
        shutil.copyfile(doc_path, scene_path)
        scene_mechanism = "raw_copy_saved_file"
        scene_evidence = {"copy_path": str(scene_path), "source_path": doc_path}

    if not scene_path.is_file() or scene_path.stat().st_size == 0:
        raise DirectorTakePackageError("save_copy_failed", "scene.3dm missing or empty")

    # Deep drift gate: the ACTOR STATE (instance identity/xform + every member's
    # id/type/layer/name/tight bbox) must be identical before and after the
    # scene snapshot. Object count alone is NOT sufficient — a dirty document
    # can mutate actors while preserving count (Codex plan review, finding 2).
    actor_state_after = await _resolve_actor_state(
        call_native, spec["actor_sets"], port)
    if actor_state_after != actor_sets_manifest:
        raise DirectorTakePackageError(
            "package_state_drift",
            "actor state changed between enumeration and snapshot; "
            "scene.3dm and scene_manifest.json would disagree — re-run packaging")

    # Cheap document-level check as a second line (path/modified/count).
    doc_after = await _native(call_native, "/document", "GET", None, port, "invalid_input")
    if (doc_after.get("objectCount") != doc_object_count
            or bool(doc_after.get("modified")) != doc_modified
            or (doc_after.get("path") or "") != (doc.get("path") or "")):
        raise DirectorTakePackageError(
            "package_state_drift",
            "live document changed during packaging; re-run packaging")

    motion_hash = _write_json(staging_root / "motion.json", spec["motion"])
    camera_hash = None
    if spec["camera"] is not None:
        camera_hash = _write_json(staging_root / "camera.json", spec["camera"])
    scene_hash = _sha256_file(scene_path)

    hashes = {
        "motion_json_sha256": motion_hash,
        "camera_json_sha256": camera_hash,
        "scene_3dm_sha256": scene_hash,
        "scene_3dm_bytes": scene_path.stat().st_size,
    }

    manifest = {
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "metadata_kind": "director_take_package_manifest",
        "take_id": spec["take_id"],
        "created_at_utc": now_fn(),
        "source_document": {
            "path": doc.get("path") or "",
            "modified_at_package_time": doc_modified,
            "object_count": doc_object_count,
            "units": doc.get("units"),
        },
        "scene": {"file": "scene.3dm", "mechanism": scene_mechanism,
                  "evidence": scene_evidence, "bytes": hashes["scene_3dm_bytes"],
                  "sha256": scene_hash},
        "actor_sets": actor_sets_manifest,
        "display_mode_requirements": display_mode_requirements,
        "hashes": hashes,
    }
    manifest_hash = _write_json(staging_root / "scene_manifest.json", manifest)

    package_id = f"{spec['take_id']}-{manifest_hash[:12]}"
    status = {
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "package_id": package_id,
        "take_id": spec["take_id"],
        "phase": "packaged",
        "heartbeat_utc": now_fn(),
        "scene_manifest_sha256": manifest_hash,
        "evidence": {"scene_mechanism": scene_mechanism},
    }
    _write_json(staging_root / "status.json", status)

    # Atomic promotion: the final <take_id> directory appears only for a
    # fully-gated, complete package. A failed run leaves only the staging
    # dir, which the next run removes — so retries never see
    # package_already_exists from a failure.
    staging_root.rename(package_root)

    return {
        "package_root": str(package_root),
        "package_id": package_id,
        "take_id": spec["take_id"],
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "scene": manifest["scene"],
        "actor_set_member_counts": {
            a["actor_set_id"]: a["member_count"] for a in actor_sets_manifest},
        "display_mode_requirements": display_mode_requirements,
        "hashes": hashes,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd mcp_server && python -m pytest tests/test_director_take_package.py -v`
Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/director_take_package.py mcp_server/tests/test_director_take_package.py
git commit -m "feat(director): take package builder with save-copy gate and scene manifest"
```

---

### Task 4: MCP tool `rhino_director_package_take`

**Files:**
- Modify: `mcp_server/src/rook/server.py` — Tool definition (place after `rhino_director_compile_motion`, ~line 4099) and dispatch case (place after `case "rhino_director_compile_motion":`, ~line 20834); add `director_take_package` to the module's director imports (rg `from . import` / `import director_compiler` near the top to find the import block and mirror it)
- Modify: `mcp_server/src/rook/agent/targeting.py` and `mcp_server/src/rook/mcp_tool_profiles.py` — classify the new tool in the SAME sets/groups that contain `rhino_director_compile_motion` (rg that name in each file)
- Modify: the two test files that pin tool-surface counts (find them: `rg -l "rhino_director_compile_motion" mcp_server/tests/` then within those, the ones asserting set sizes/membership) — update per their failure output
- Test: `mcp_server/tests/test_director_take_package.py` (extend)

**Interfaces:**
- Consumes: `director_take_package.package_take(arguments, port=port)` / `DirectorTakePackageError.to_data()` from Task 3.
- Produces: MCP tool `rhino_director_package_take` returning the internal `{"success", "data"}` envelope like its director siblings.

- [ ] **Step 1: Write the failing dispatch test** — append to `mcp_server/tests/test_director_take_package.py`:

```python
async def test_mcp_tool_is_registered_and_dispatches():
    """Mirrors the call_tool + AsyncMock pattern of test_director_mcp_tools.py."""
    from unittest.mock import AsyncMock, patch

    from rook import server

    request = {"take_id": "t", "output_root": "C:/x", "actor_sets": [],
               "motion": {}, "display_modes": ["Arctic"]}
    with patch.object(server.director_take_package, "package_take",
                      new_callable=AsyncMock) as mock:
        mock.return_value = {"package_root": "C:/x/t", "package_id": "t-abc",
                             "take_id": "t"}
        result = await server.call_tool("rhino_director_package_take", request)
    mock.assert_awaited_once()
    assert "t-abc" in result[0].text
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_director_take_package.py::test_mcp_tool_is_registered_and_dispatches -v`
Expected: FAIL — tool name not in registered tools.

- [ ] **Step 3: Register the tool** — after the `rhino_director_compile_motion` Tool definition:

```python
        Tool(
            name="rhino_director_package_take",
            description=(
                "RookVisionDirector v3: build an immutable take package (scene.3dm "
                "snapshot via non-retargeting save-copy, scene_manifest.json with actor "
                "member provenance and display-mode requirements, motion.json authoring "
                "request, optional camera.json, status.json ledger). Read-only for the "
                "live document; fails typed on unsaved edits without save-copy, missing "
                "display modes, or document drift during packaging."
            ),
            inputSchema={
                "type": "object",
                "required": ["output_root", "take_id", "actor_sets", "motion", "display_modes"],
                "properties": {
                    "output_root": {"type": "string", "description": "Directory that will contain the <take_id> package folder."},
                    "take_id": {"type": "string", "description": "Package folder name, [A-Za-z0-9._-]{1,128}."},
                    "actor_sets": {"type": "array", "items": {"type": "object"}, "description": "Each {actor_set_id, block_name, source_top_level_object_id (uuid)}."},
                    "motion": {"type": "object", "description": "Authoring compile-motion request (canonical targets, never worker object ids)."},
                    "camera": {"type": "object", "description": "Optional camera_planner spec."},
                    "display_modes": {"type": "array", "items": {"type": "string"}, "description": "Display mode names required for capture passes; verified to exist now."},
                },
            },
        ),
```

And the dispatch case after `rhino_director_compile_motion`'s:

```python
        case "rhino_director_package_take":
            try:
                result = {"success": True, "data": await director_take_package.package_take(arguments, port=port)}
            except director_take_package.DirectorTakePackageError as exc:
                result = {"success": False, "data": exc.to_data()}
```

Plus the import, mirroring how `director_compiler` is imported at the top of `server.py`.

- [ ] **Step 4: Classify the tool** — in `targeting.py` and `mcp_tool_profiles.py`, add `"rhino_director_package_take"` to every set/group where `"rhino_director_compile_motion"` appears. Then run the full unit layer and fix the two pinned-count tests per their failure messages:

Run: `cd mcp_server && python -m pytest tests/ -k "profile or targeting or surface" -v`
Expected: initial failures naming exact expected counts → update those pinned expectations → re-run → PASS.

- [ ] **Step 5: Run the new test + director suite**

Run: `cd mcp_server && python -m pytest tests/test_director_take_package.py tests/test_director_mcp_tools.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/server.py mcp_server/src/rook/agent/targeting.py mcp_server/src/rook/mcp_tool_profiles.py mcp_server/tests/
git commit -m "feat(director): register rhino_director_package_take MCP tool"
```

---

### Task 5: Live gate — save-copy invariants + package round-trip

**Files:**
- Create: `mcp_server/tests/test_director_take_package_live.py`

**Interfaces:**
- Consumes: deployed native plugin with `/document/save-copy` (Tasks 1–2), `package_take` (Task 3). Uses the live-test conventions from `mcp_server/tests/test_director_routes_live.py`: `pytest.mark.requires_rhino`, host discovery via `rook.bridge.get_rhino_host`, skip when undiscoverable.

- [ ] **Step 1: Deploy the native build (user handoff).**

Run: `cmd /c scripts\deploy-native.bat` — requires Rhino closed. **Hand the user these exact steps and wait:** (1) close Rhino, (2) tell me to deploy, (3) relaunch Rhino with the deployed plugin, (4) I verify with `rhino_ping`. Do not launch or close Rhino yourself (user rule).

- [ ] **Step 2: Write the live gate** — `mcp_server/tests/test_director_take_package_live.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from rook import director_take_package as dtp

pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


def _require_host() -> str:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")
    return base_url  # type: ignore[return-value]


async def _post(route: str, body: dict[str, Any]) -> dict[str, Any]:
    base_url = _require_host()
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(f"{base_url}{route}", json=body)
    return resp.json()


async def _get(route: str) -> dict[str, Any]:
    base_url = _require_host()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{base_url}{route}")
    return resp.json()


async def _doc() -> dict[str, Any]:
    envelope = await _get("/document")
    assert envelope.get("success"), envelope
    return envelope["data"]


async def _add_box() -> str:
    # Mutates the live doc; the test undoes it before finishing.
    envelope = await _post("/geometry/box", {
        "corner": [0, 0, 0], "width": 1.0, "depth": 1.0, "height": 1.0})
    # If this repo's box route differs, mirror the helper used in
    # tests/test_director_routes_live.py conftest (_create_brep) instead.
    assert envelope.get("success"), envelope
    return envelope["data"].get("id", "")


async def test_save_copy_four_invariants(tmp_path):
    """THE gate for CRhinoFileWriteOptions mode selection (spec open question 3)."""
    before = await _doc()
    added_id = await _add_box()  # make the doc dirty + create an undo record
    dirty = await _doc()
    assert dirty["modified"] is True
    assert dirty["objectCount"] == before["objectCount"] + 1

    target = tmp_path / "copy.3dm"
    envelope = await _post("/document/save-copy", {"path": str(target)})
    assert envelope.get("success"), envelope
    evidence = envelope["data"]

    # Invariants 1-3: path, title, and modified flag unchanged
    # (native evidence + independent re-read).
    assert evidence["path_before"] == evidence["path_after"]
    assert evidence["title_before"] == evidence["title_after"]
    assert evidence["modified_before"] is True and evidence["modified_after"] is True
    assert evidence["save_small_used"] is False
    after = await _doc()
    assert after["path"] == dirty["path"]
    assert after["modified"] is True

    # Copy-exists proof: nonzero file with a valid 3dm header. This does NOT
    # prove render meshes are present — that open-fidelity proof belongs to
    # the Slice 2 worker gate; save_small_used=False is the route's evidence.
    assert target.is_file() and target.stat().st_size > 0
    assert target.read_bytes()[:24].startswith(b"3D Geometry File Format")

    # Invariant 4: the undo stack survived the write — undo removes the box.
    envelope = await _post("/undo", {})
    assert envelope.get("success"), envelope
    restored = await _doc()
    assert restored["objectCount"] == before["objectCount"]


async def test_package_round_trip_against_live_doc(tmp_path):
    doc = await _doc()
    blocks = await _get("/blocks")
    assert blocks.get("success"), blocks
    placed = [b for b in blocks["data"]["blocks"]
              if b.get("instanceCount", 0) > 0 and b.get("objectCount", 0) >= 2]
    if not placed:
        pytest.skip("live doc has no placed multi-member block to package")
    block = placed[0]

    instances = await _post("/block/instances", {"name": block["name"]})
    if not instances.get("success") or not instances["data"].get("instances"):
        pytest.skip("could not resolve an instance id for the block")
    instance_id = instances["data"]["instances"][0]["id"]

    modes = await _get("/display-modes")
    mode_name = modes["data"]["modes"][0]["name"]

    result = await dtp.package_take({
        "output_root": str(tmp_path),
        "take_id": "live_gate_take",
        "actor_sets": [{"actor_set_id": "live_gate_set", "block_name": block["name"],
                        "source_top_level_object_id": instance_id}],
        "motion": {"timeline": {"fps": 24, "frame_count": 8},
                   "motion": [{"target": "live_gate_set",
                               "keyframes": [{"t": 1, "translate": [0, 0, 100]}]}]},
        "camera": None,
        "display_modes": [mode_name],
    })

    root = Path(result["package_root"])
    manifest = json.loads((root / "scene_manifest.json").read_text())
    assert manifest["actor_sets"][0]["member_count"] == block["objectCount"]
    # DEC-021 live proof: every manifest member carries tight-bbox evidence.
    for member in manifest["actor_sets"][0]["members"]:
        assert member["bbox_evidence"]["bbox_method"] == "tight_object"
        assert member["bbox_evidence"]["validation_strength"] == "tight_bbox"
    # Source-instance evidence proves the Task 1 /block/instances extension
    # is actually present in the deployed native route.
    src = manifest["actor_sets"][0]["source_instance"]
    assert src["instance_id"] == instance_id
    assert src["definition_id"] and src["definition_name"]
    assert len(src["xform"]) == 4 and all(len(row) == 4 for row in src["xform"])
    assert len(src["xform_sha256"]) == 64
    assert (root / "scene.3dm").stat().st_size > 0
    assert manifest["scene"]["mechanism"] in ("save_copy", "raw_copy_saved_file")
    # Live doc untouched:
    after = await _doc()
    assert after["objectCount"] == doc["objectCount"]
    assert after["modified"] == doc["modified"]
```

Adjust `_add_box` to the actual geometry-creation route: copy the exact helper (`_create_brep`) from `mcp_server/tests/conftest.py` used by `test_director_routes_live.py` rather than guessing `/geometry/box`. Similarly confirm the undo route path (`/undo`) matches what `rhino_document_ops` dispatch uses (server.py line ~14854 shows `/undo`).

- [ ] **Step 3: Run the live gate** (Rhino running with deployed build; any saved document open):

Run: `cd mcp_server && python -m pytest tests/test_director_take_package_live.py -v`
Expected: 2 passed (or explicit skips with reasons if the doc has no placed blocks — rerun with a real model open).

- [ ] **Step 4: If the modified flag or path DID change** — the `CRhinoFileWriteOptions` mode needs escalation: retry with `opts.SetIsAutosave(true)` added in the Task 1 handler, rebuild, redeploy, re-run the gate. Record the working option set in the spec's open question 3 (edit the spec's "Still open" list to mark it resolved with the proven mode).

- [ ] **Step 5: Run the full unit suite to check for regressions**

Run: `cd mcp_server && python -m pytest tests/ -x -q --ignore=tests/test_director_take_package_live.py -k "not live"`
Expected: pass (same count as before this branch plus the new tests).

- [ ] **Step 6: Commit**

```bash
git add mcp_server/tests/test_director_take_package_live.py docs/superpowers/specs/2026-07-06-director-v3-snapshot-boundary-design.md
git commit -m "test(director): live gate for save-copy invariants and take-package round trip"
```

---

## Out of Scope (later slices)

- Worker instance open/prepare/explode/member-map (Slice 2) — consumes `scene_manifest.json` produced here.
- `resolved_motion.json` derivation, file-backed compile, worker capture loop, delta playback (Slices 2–3).
- Display-mode settings fingerprinting (`settings_fingerprint` is written as `null` in Slice 1 — the name/id + fail-hard floor from the spec).
- Actor-metadata-ref (`.rook`) driven membership; Slice 1's actor-set input contract is explicit `{actor_set_id, block_name, source_top_level_object_id}`.
