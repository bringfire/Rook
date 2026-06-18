# RookBIM Export Preset To Rhino Demo Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `rookbim_export_preset_to_rhino`, a demo-safe MCP workflow tool that exports a RookBIM preset bundle, imports the generated `.3dm`, projects BIM sidecar facts for the imported objects, and optionally returns a scene-wide BIM relationship scan.

**Architecture:** Add one Python orchestration module that owns request shaping, generated output naming, path extraction, partial-failure envelopes, and calls to existing surfaces. Wire that helper into the MCP server and local dispatcher without changing native, C#, or the existing `rookbim_export_preset` contract.

**Tech Stack:** Python 3.10+, MCP server tool registration in `mcp_server/src/rook/server.py`, local agent dispatcher in `mcp_server/src/rook/agent/tool_dispatcher.py`, pytest/pytest-asyncio.

---

## File Structure

- Create `mcp_server/src/rook/rookbim_export_to_rhino.py`
  - Pure-ish workflow helper plus small injected async call seams.
  - Owns:
    - default output generation;
    - export request shaping;
    - artifact path resolution from export response with fallback;
    - import request shaping;
    - projection/facts call ordering;
    - partial failure response envelopes.
  - Does not parse sidecars, mutate Rhino directly, or duplicate projection/query logic.
- Modify `mcp_server/src/rook/server.py`
  - Add `_rookbim_export_preset_to_rhino_schema()`.
  - Add `Tool(name="rookbim_export_preset_to_rhino", ...)`.
  - Add `_call_tool_dispatch` case using the helper.
- Modify `mcp_server/src/rook/agent/tool_dispatcher.py`
  - Add optional local tool wrapper using the same helper.
  - Do not add a raw bridge route because this is Python orchestration, not a native HTTP route.
- Modify `mcp_server/src/rook/agent/tool_groups.py`
  - Add the tool to `TOOL_GROUPS["rookbim"]`.
  - Do not add it to `rookbim_readonly`.
- Modify `mcp_server/src/rook/targeting.py`
  - Add `rookbim_export_preset_to_rhino` to `_ALL_KNOWN_TOOLS` only, so it derives `RhinoToolPolicy(True, "mutate")`.
- Add `mcp_server/tests/test_rookbim_export_to_rhino_workflow.py`
  - Unit tests for helper behavior, partial failures, output/path rules, dispatch call order, and local/server wiring.
- Modify existing tests only where needed:
  - `mcp_server/tests/test_rookbim_export_preset_tool.py`
  - `mcp_server/tests/test_rookbim_mcp_tools.py`

## Task 1: Workflow Helper Foundation

**Files:**
- Create: `mcp_server/src/rook/rookbim_export_to_rhino.py`
- Test: `mcp_server/tests/test_rookbim_export_to_rhino_workflow.py`

- [ ] **Step 1: Write failing tests for default output and export request shaping**

Add this file:

```python
import datetime as dt

import pytest

from rook import rookbim_export_to_rhino as workflow


def test_default_output_uses_temp_root_and_safe_timestamp(monkeypatch, tmp_path):
    monkeypatch.setenv("TEMP", str(tmp_path))
    now = dt.datetime(2026, 6, 18, 9, 4, 5)

    output = workflow.default_output_for_preset("openings_and_hosts", now=now)

    assert output == {
        "directory": str(tmp_path / "rookbim-export-to-rhino"),
        "name": "openings_and_hosts-20260618-090405",
    }


def test_default_output_sanitizes_preset_name(monkeypatch, tmp_path):
    monkeypatch.setenv("TEMP", str(tmp_path))
    now = dt.datetime(2026, 6, 18, 9, 4, 5)

    output = workflow.default_output_for_preset("../", now=now)

    assert output["name"] == "rookbim-20260618-090405"


def test_build_export_request_preserves_camel_case_fields(monkeypatch, tmp_path):
    monkeypatch.setenv("TEMP", str(tmp_path))
    now = dt.datetime(2026, 6, 18, 9, 4, 5)

    request, effective_output = workflow.build_export_request(
        {
            "preset": "openings_and_hosts",
            "scope": "active_view",
            "includeCategories": ["Doors", "Windows"],
            "limitPerCategory": 10,
            "allowTruncated": True,
            "allowBboxProxy": True,
            "projectRelationships": False,
            "relationshipSummary": False,
            "targetLayer": "Demo",
            "port": 9876,
        },
        now=now,
    )

    assert effective_output == {
        "directory": str(tmp_path / "rookbim-export-to-rhino"),
        "name": "openings_and_hosts-20260618-090405",
    }
    assert request == {
        "preset": "openings_and_hosts",
        "scope": "active_view",
        "includeCategories": ["Doors", "Windows"],
        "limitPerCategory": 10,
        "allowTruncated": True,
        "allowBboxProxy": True,
        "output": effective_output,
    }
    assert "projectRelationships" not in request
    assert "relationshipSummary" not in request
    assert "targetLayer" not in request
    assert "port" not in request
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```bash
python -m pytest mcp_server/tests/test_rookbim_export_to_rhino_workflow.py -q
```

Expected: fails with `ImportError` or missing attributes for `rook.rookbim_export_to_rhino`.

- [ ] **Step 3: Implement helper foundation**

Create `mcp_server/src/rook/rookbim_export_to_rhino.py`:

```python
from __future__ import annotations

import datetime as dt
import os
import re
from pathlib import Path
from typing import Any


WORKFLOW_NAME = "rookbim_export_preset_to_rhino"

EXPORT_FIELD_NAMES = {
    "preset",
    "output",
    "scope",
    "includeCategories",
    "excludeCategories",
    "layerPolicy",
    "namePolicy",
    "metadataProfile",
    "rooms",
    "limitPerCategory",
    "allowTruncated",
    "allowBboxProxy",
}


def _safe_preset_name(preset: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(preset or "")).strip("._-")
    return safe or "rookbim"


def default_output_for_preset(preset: str, *, now: dt.datetime | None = None) -> dict[str, str]:
    stamp = (now or dt.datetime.now()).strftime("%Y%m%d-%H%M%S")
    root = Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".")
    return {
        "directory": str(root / "rookbim-export-to-rhino"),
        "name": f"{_safe_preset_name(preset)}-{stamp}",
    }


def build_export_request(
    arguments: dict[str, Any],
    *,
    now: dt.datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    request = {
        key: value
        for key, value in arguments.items()
        if key in EXPORT_FIELD_NAMES and value is not None
    }
    if "output" not in request:
        request["output"] = default_output_for_preset(str(arguments.get("preset", "")), now=now)
    effective_output = dict(request["output"])
    return request, effective_output
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
python -m pytest mcp_server/tests/test_rookbim_export_to_rhino_workflow.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/rookbim_export_to_rhino.py mcp_server/tests/test_rookbim_export_to_rhino_workflow.py
git commit -m "feat: add RookBIM export-to-Rhino workflow helpers"
```

## Task 2: Artifact Paths and Stage Envelopes

**Files:**
- Modify: `mcp_server/src/rook/rookbim_export_to_rhino.py`
- Modify: `mcp_server/tests/test_rookbim_export_to_rhino_workflow.py`

- [ ] **Step 1: Add failing tests for authoritative path preference and fallback**

Append:

```python
def test_resolve_artifact_paths_prefers_export_response_paths(tmp_path):
    effective_output = {"directory": str(tmp_path / "derived"), "name": "derived-name"}
    export_response = {
        "success": True,
        "data": {
            "paths": {
                "model3dm": "C:/authoritative/model.3dm",
                "sidecar": "C:/authoritative/model.sidecar.json",
                "validation": "C:/authoritative/model.validation.json",
                "directory": "C:/authoritative",
            }
        },
    }

    paths = workflow.resolve_artifact_paths(export_response, effective_output)

    assert paths == {
        "bundleDirectory": "C:/authoritative",
        "model3dm": "C:/authoritative/model.3dm",
        "sidecar": "C:/authoritative/model.sidecar.json",
        "validation": "C:/authoritative/model.validation.json",
    }


def test_resolve_artifact_paths_falls_back_to_effective_output(tmp_path):
    effective_output = {"directory": str(tmp_path), "name": "shell"}

    paths = workflow.resolve_artifact_paths({"success": True, "data": {}}, effective_output)

    assert paths == {
        "bundleDirectory": str(tmp_path),
        "model3dm": str(tmp_path / "shell.3dm"),
        "sidecar": str(tmp_path / "shell.sidecar.json"),
        "validation": str(tmp_path / "shell.validation.json"),
    }


def test_partial_failure_envelope_preserves_completed_blocks():
    result = workflow.stage_failure(
        "projection",
        "no_imported_ids",
        "Import returned no object ids.",
        export={"response": {"success": True}},
        paths={"model3dm": "C:/x/shell.3dm"},
        import_result={"importedObjectCount": 0, "importedIds": []},
    )

    assert result["success"] is False
    assert result["partialSuccess"] is True
    assert result["workflow"] == workflow.WORKFLOW_NAME
    assert result["stage"] == "projection"
    assert result["error"] == "no_imported_ids"
    assert result["export"]["response"]["success"] is True
    assert result["paths"]["model3dm"].endswith("shell.3dm")
    assert result["import"]["importedObjectCount"] == 0
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python -m pytest mcp_server/tests/test_rookbim_export_to_rhino_workflow.py -q
```

Expected: failures for missing `resolve_artifact_paths` and `stage_failure`.

- [ ] **Step 3: Implement path and envelope helpers**

Add to `mcp_server/src/rook/rookbim_export_to_rhino.py`:

```python
def _nested_get(mapping: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _first_str(mapping: dict[str, Any], paths: tuple[tuple[str, ...], ...]) -> str | None:
    for path in paths:
        value = _nested_get(mapping, path)
        if value:
            return str(value)
    return None


def resolve_artifact_paths(
    export_response: dict[str, Any],
    effective_output: dict[str, Any],
) -> dict[str, str]:
    directory = str(effective_output["directory"])
    name = str(effective_output["name"])
    fallback_model = str(Path(directory) / f"{name}.3dm")
    fallback_sidecar = str(Path(directory) / f"{name}.sidecar.json")
    fallback_validation = str(Path(directory) / f"{name}.validation.json")

    model3dm = _first_str(
        export_response,
        (
            ("data", "paths", "model3dm"),
            ("data", "paths", "model3dmPath"),
            ("data", "bundle", "model3dm"),
            ("data", "bundle", "model3dmPath"),
            ("data", "model3dm"),
            ("data", "model3dmPath"),
            ("bundle", "model3dm"),
            ("model3dm",),
        ),
    ) or fallback_model
    sidecar = _first_str(
        export_response,
        (
            ("data", "paths", "sidecar"),
            ("data", "paths", "sidecarPath"),
            ("data", "bundle", "sidecar"),
            ("data", "bundle", "sidecarPath"),
            ("data", "sidecar"),
            ("data", "sidecarPath"),
            ("bundle", "sidecar"),
            ("sidecar",),
        ),
    ) or fallback_sidecar
    validation = _first_str(
        export_response,
        (
            ("data", "paths", "validation"),
            ("data", "paths", "validationPath"),
            ("data", "bundle", "validation"),
            ("data", "bundle", "validationPath"),
            ("data", "validation"),
            ("data", "validationPath"),
            ("bundle", "validation"),
            ("validation",),
        ),
    ) or fallback_validation
    bundle_dir = _first_str(
        export_response,
        (
            ("data", "paths", "directory"),
            ("data", "bundle", "directory"),
            ("data", "bundleDirectory"),
            ("bundle", "directory"),
        ),
    ) or str(Path(model3dm).parent)
    return {
        "bundleDirectory": bundle_dir,
        "model3dm": model3dm,
        "sidecar": sidecar,
        "validation": validation,
    }


def stage_failure(
    stage: str,
    error: str,
    message: str,
    *,
    partial_success: bool = True,
    export: Any = None,
    paths: Any = None,
    import_result: Any = None,
    projection: Any = None,
    bimFacts: Any = None,
) -> dict[str, Any]:
    result = {
        "success": False,
        "partialSuccess": partial_success,
        "workflow": WORKFLOW_NAME,
        "stage": stage,
        "error": error,
        "message": message,
    }
    if export is not None:
        result["export"] = export
    if paths is not None:
        result["paths"] = paths
    if import_result is not None:
        result["import"] = import_result
    if projection is not None:
        result["projection"] = projection
    if bimFacts is not None:
        result["bimFacts"] = bimFacts
    return result
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
python -m pytest mcp_server/tests/test_rookbim_export_to_rhino_workflow.py -q
```

Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/rookbim_export_to_rhino.py mcp_server/tests/test_rookbim_export_to_rhino_workflow.py
git commit -m "feat: resolve RookBIM workflow artifact paths"
```

## Task 3: Workflow Orchestration

**Files:**
- Modify: `mcp_server/src/rook/rookbim_export_to_rhino.py`
- Modify: `mcp_server/tests/test_rookbim_export_to_rhino_workflow.py`

- [ ] **Step 1: Add failing orchestration tests for success and scoped projection**

Append:

```python
@pytest.mark.asyncio
async def test_workflow_calls_export_import_projection_and_scene_wide_facts(tmp_path):
    calls = []

    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        calls.append(("rhino", path, method, payload, port))
        if path == "/bim/export-preset":
            return {"success": True, "data": {"bundle": {"model3dm": str(tmp_path / "model.3dm")}}}
        if path == "/import":
            return {"success": True, "data": {"importedIds": ["rh-door", "rh-wall"]}}
        raise AssertionError(path)

    async def fake_project(**kwargs):
        calls.append(("project", kwargs))
        return {"success": True, "joinedObjectCount": 2}

    def fake_facts(**kwargs):
        calls.append(("facts", kwargs))
        return {"success": True, "mode": "relationship_scan", "summary": {"relationshipCounts": {}}}

    result = await workflow.export_preset_to_rhino(
        {
            "preset": "openings_and_hosts",
            "output": {"directory": str(tmp_path), "name": "model"},
            "includeRooms": True,
            "includeLevels": False,
            "relationshipSampleLimit": 7,
            "port": 9876,
        },
        call_rhino_fn=fake_call_rhino,
        project_relationships_fn=fake_project,
        query_bim_facts_fn=fake_facts,
    )

    assert result["success"] is True
    assert result["workflow"] == workflow.WORKFLOW_NAME
    assert result["paths"]["model3dm"] == str(tmp_path / "model.3dm")
    assert result["paths"]["sidecar"] == str(tmp_path / "model.sidecar.json")
    assert result["import"]["importedIds"] == ["rh-door", "rh-wall"]
    assert result["import"]["importedObjectCount"] == 2
    assert result["projection"]["joinedObjectCount"] == 2
    assert result["bimFacts"]["mode"] == "relationship_scan"

    assert calls[0] == (
        "rhino",
        "/bim/export-preset",
        "POST",
        {
            "preset": "openings_and_hosts",
            "output": {"directory": str(tmp_path), "name": "model"},
        },
        9876,
    )
    assert calls[1] == (
        "rhino",
        "/import",
        "POST",
        {"path": str(tmp_path / "model.3dm")},
        9876,
    )
    assert calls[2] == (
        "project",
        {
            "sidecar_path": str(tmp_path / "model.sidecar.json"),
            "object_ids": ["rh-door", "rh-wall"],
            "include_rooms": True,
            "include_levels": False,
            "port": 9876,
        },
    )
    assert calls[3] == ("facts", {"mode": "relationship_scan", "sample_limit": 7})


@pytest.mark.asyncio
async def test_workflow_omits_target_layer_by_default_and_forwards_when_explicit(tmp_path):
    import_payloads = []

    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        if path == "/bim/export-preset":
            return {"success": True, "data": {}}
        if path == "/import":
            import_payloads.append(payload)
            return {"success": True, "data": {"importedIds": ["rh-1"]}}
        raise AssertionError(path)

    async def fake_project(**kwargs):
        return {"success": True}

    await workflow.export_preset_to_rhino(
        {"preset": "openings_and_hosts", "output": {"directory": str(tmp_path), "name": "a"}},
        call_rhino_fn=fake_call_rhino,
        project_relationships_fn=fake_project,
        query_bim_facts_fn=lambda **kwargs: {"success": True},
    )
    await workflow.export_preset_to_rhino(
        {
            "preset": "openings_and_hosts",
            "output": {"directory": str(tmp_path), "name": "b"},
            "targetLayer": "Demo Import",
        },
        call_rhino_fn=fake_call_rhino,
        project_relationships_fn=fake_project,
        query_bim_facts_fn=lambda **kwargs: {"success": True},
    )

    assert import_payloads[0] == {"path": str(tmp_path / "a.3dm")}
    assert import_payloads[1] == {"path": str(tmp_path / "b.3dm"), "targetLayer": "Demo Import"}
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python -m pytest mcp_server/tests/test_rookbim_export_to_rhino_workflow.py -q
```

Expected: failures for missing `export_preset_to_rhino`.

- [ ] **Step 3: Implement orchestration success path**

Add to `mcp_server/src/rook/rookbim_export_to_rhino.py`:

```python
def _unwrap_data(response: dict[str, Any]) -> Any:
    if isinstance(response, dict) and "data" in response:
        return response["data"]
    return response


def _is_success(response: dict[str, Any]) -> bool:
    return isinstance(response, dict) and response.get("success") is not False


def _imported_ids(import_response: dict[str, Any]) -> list[str]:
    data = _unwrap_data(import_response)
    if not isinstance(data, dict):
        return []
    raw = data.get("importedIds") or data.get("ids") or data.get("objectIds") or []
    return [str(item) for item in raw if item]


async def export_preset_to_rhino(
    arguments: dict[str, Any],
    *,
    call_rhino_fn,
    project_relationships_fn,
    query_bim_facts_fn,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    request, effective_output = build_export_request(arguments, now=now)
    port = arguments.get("port")

    export_response = await call_rhino_fn("/bim/export-preset", "POST", request, port=port)
    export_block = {"request": request, "response": export_response}
    if not _is_success(export_response):
        return stage_failure(
            "export",
            "export_failed",
            "RookBIM export preset failed.",
            partial_success=False,
            export=export_block,
        )

    paths = resolve_artifact_paths(export_response, effective_output)
    import_request = {"path": paths["model3dm"]}
    if arguments.get("targetLayer"):
        import_request["targetLayer"] = arguments["targetLayer"]

    import_response = await call_rhino_fn("/import", "POST", import_request, port=port)
    ids = _imported_ids(import_response)
    import_block = {
        "request": import_request,
        "response": import_response,
        "importedObjectCount": len(ids),
        "importedIds": ids,
    }
    if not _is_success(import_response):
        return stage_failure(
            "import",
            "import_failed",
            "Rhino import failed.",
            export=export_block,
            paths=paths,
            import_result=import_block,
        )

    projection_block: dict[str, Any] | None = None
    if arguments.get("projectRelationships", True):
        if not ids:
            return stage_failure(
                "projection",
                "no_imported_ids",
                "Import succeeded but returned no imported object ids; refusing to project over the whole scene.",
                export=export_block,
                paths=paths,
                import_result=import_block,
            )
        projection_block = await project_relationships_fn(
            sidecar_path=paths["sidecar"],
            object_ids=ids,
            include_rooms=arguments.get("includeRooms", True),
            include_levels=arguments.get("includeLevels", True),
            port=port,
        )
        if isinstance(projection_block, dict) and projection_block.get("success") is False:
            return stage_failure(
                "projection",
                str(projection_block.get("error") or "projection_failed"),
                str(projection_block.get("message") or "BIM relationship projection failed."),
                export=export_block,
                paths=paths,
                import_result=import_block,
                projection=projection_block,
            )

    facts_block: dict[str, Any] | None = None
    if arguments.get("relationshipSummary", True) and projection_block is not None:
        facts_block = query_bim_facts_fn(
            mode="relationship_scan",
            sample_limit=arguments.get("relationshipSampleLimit", 20),
        )
        if isinstance(facts_block, dict) and facts_block.get("success") is False:
            return stage_failure(
                "bimFacts",
                str(facts_block.get("error") or "bim_facts_failed"),
                str(facts_block.get("message") or "BIM relationship scan failed."),
                export=export_block,
                paths=paths,
                import_result=import_block,
                projection=projection_block,
                bimFacts=facts_block,
            )

    return {
        "success": True,
        "workflow": WORKFLOW_NAME,
        "export": export_block,
        "paths": paths,
        "import": import_block,
        "projection": projection_block or {},
        "bimFacts": facts_block or {},
        "warnings": [],
    }
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
python -m pytest mcp_server/tests/test_rookbim_export_to_rhino_workflow.py -q
```

Expected: all current workflow tests pass.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/rookbim_export_to_rhino.py mcp_server/tests/test_rookbim_export_to_rhino_workflow.py
git commit -m "feat: orchestrate RookBIM export import projection workflow"
```

## Task 4: Partial Failure Coverage

**Files:**
- Modify: `mcp_server/tests/test_rookbim_export_to_rhino_workflow.py`
- Modify: `mcp_server/src/rook/rookbim_export_to_rhino.py` only if tests expose a bug

- [ ] **Step 1: Add failing tests for failure semantics and skip flags**

Append:

```python
@pytest.mark.asyncio
async def test_workflow_import_no_ids_is_projection_failure_without_projection_call(tmp_path):
    project_calls = []

    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        if path == "/bim/export-preset":
            return {"success": True, "data": {}}
        if path == "/import":
            return {"success": True, "data": {"importedIds": []}}
        raise AssertionError(path)

    async def fake_project(**kwargs):
        project_calls.append(kwargs)
        return {"success": True}

    result = await workflow.export_preset_to_rhino(
        {
            "preset": "openings_and_hosts",
            "output": {"directory": str(tmp_path), "name": "model"},
        },
        call_rhino_fn=fake_call_rhino,
        project_relationships_fn=fake_project,
        query_bim_facts_fn=lambda **kwargs: {"success": True},
    )

    assert result["success"] is False
    assert result["partialSuccess"] is True
    assert result["stage"] == "projection"
    assert result["error"] == "no_imported_ids"
    assert result["import"]["importedObjectCount"] == 0
    assert project_calls == []


@pytest.mark.asyncio
async def test_workflow_projection_failure_preserves_export_and_import_blocks(tmp_path):
    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        if path == "/bim/export-preset":
            return {"success": True, "data": {}}
        if path == "/import":
            return {"success": True, "data": {"importedIds": ["rh-1"]}}
        raise AssertionError(path)

    async def fake_project(**kwargs):
        return {"success": False, "error": "bim_projection_invalid_sidecar", "message": "bad sidecar"}

    result = await workflow.export_preset_to_rhino(
        {"preset": "openings_and_hosts", "output": {"directory": str(tmp_path), "name": "model"}},
        call_rhino_fn=fake_call_rhino,
        project_relationships_fn=fake_project,
        query_bim_facts_fn=lambda **kwargs: {"success": True},
    )

    assert result["success"] is False
    assert result["partialSuccess"] is True
    assert result["stage"] == "projection"
    assert result["error"] == "bim_projection_invalid_sidecar"
    assert result["export"]["response"]["success"] is True
    assert result["import"]["importedIds"] == ["rh-1"]


@pytest.mark.asyncio
async def test_workflow_relationship_summary_false_skips_bim_facts(tmp_path):
    fact_calls = []

    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        if path == "/bim/export-preset":
            return {"success": True, "data": {}}
        if path == "/import":
            return {"success": True, "data": {"importedIds": ["rh-1"]}}
        raise AssertionError(path)

    async def fake_project(**kwargs):
        return {"success": True}

    def fake_facts(**kwargs):
        fact_calls.append(kwargs)
        return {"success": True}

    result = await workflow.export_preset_to_rhino(
        {
            "preset": "openings_and_hosts",
            "output": {"directory": str(tmp_path), "name": "model"},
            "relationshipSummary": False,
        },
        call_rhino_fn=fake_call_rhino,
        project_relationships_fn=fake_project,
        query_bim_facts_fn=fake_facts,
    )

    assert result["success"] is True
    assert result["bimFacts"] == {}
    assert fact_calls == []
```

- [ ] **Step 2: Run tests**

Run:

```bash
python -m pytest mcp_server/tests/test_rookbim_export_to_rhino_workflow.py -q
```

Expected: tests pass if Task 3 implementation already handles the cases; otherwise failures identify the minimal fix.

- [ ] **Step 3: Fix only failing behavior**

If any Task 4 failure-path test fails, make the smallest correction to `export_preset_to_rhino(...)`
so it uses the existing `stage_failure(...)` helper consistently and preserves the completed
`export`, `paths`, `import`, `projection`, and `bimFacts` blocks.

- [ ] **Step 4: Run workflow tests again**

Run:

```bash
python -m pytest mcp_server/tests/test_rookbim_export_to_rhino_workflow.py -q
```

Expected: all workflow tests pass.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/rookbim_export_to_rhino.py mcp_server/tests/test_rookbim_export_to_rhino_workflow.py
git commit -m "test: cover RookBIM workflow partial failures"
```

## Task 5: MCP Server Schema and Dispatch

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/tests/test_rookbim_export_to_rhino_workflow.py`

- [ ] **Step 1: Add failing server schema and dispatch tests**

Append:

```python
@pytest.mark.asyncio
async def test_server_schema_exposes_export_preset_to_rhino_tool():
    from rook.server import list_tools

    tools = {tool.name: tool for tool in await list_tools()}
    schema = tools["rookbim_export_preset_to_rhino"].inputSchema
    props = schema["properties"]

    assert "preset" in props
    assert "output" in props
    assert "projectRelationships" in props
    assert "includeRooms" in props
    assert "includeLevels" in props
    assert "relationshipSummary" in props
    assert "relationshipSampleLimit" in props
    assert "targetLayer" in props
    assert "may destroy exported BIM layer organization" in props["targetLayer"]["description"]
    assert schema["required"] == ["preset"]
    assert schema["additionalProperties"] is False


@pytest.mark.asyncio
async def test_server_dispatch_uses_workflow_helper(monkeypatch):
    from rook.server import _call_tool_dispatch

    calls = []

    async def fake_workflow(arguments, **deps):
        calls.append((arguments, sorted(deps)))
        return {"success": True, "workflow": "rookbim_export_preset_to_rhino"}

    monkeypatch.setattr("rook.rookbim_export_to_rhino.export_preset_to_rhino", fake_workflow)

    result = await _call_tool_dispatch(
        "rookbim_export_preset_to_rhino",
        {"preset": "openings_and_hosts", "port": 9876},
    )

    assert result["success"] is True
    assert result["data"]["workflow"] == "rookbim_export_preset_to_rhino"
    assert calls[0][0] == {"preset": "openings_and_hosts", "port": 9876}
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python -m pytest mcp_server/tests/test_rookbim_export_to_rhino_workflow.py -q
```

Expected: missing tool/schema/dispatch failures.

- [ ] **Step 3: Add server schema helper**

In `mcp_server/src/rook/server.py`, add this helper near `_rookbim_export_preset_schema()`:

```python
def _rookbim_export_preset_to_rhino_schema() -> dict[str, Any]:
    schema = _rookbim_export_preset_schema()
    props = dict(schema["properties"])
    props["projectRelationships"] = {
        "type": "boolean",
        "default": True,
        "description": "Project the exported sidecar into the Python scene graph after import.",
    }
    props["includeRooms"] = {
        "type": "boolean",
        "default": True,
        "description": "When projecting relationships, include room reference nodes and revit_in_room edges.",
    }
    props["includeLevels"] = {
        "type": "boolean",
        "default": True,
        "description": "When projecting relationships, include level reference nodes and revit_on_level edges.",
    }
    props["relationshipSummary"] = {
        "type": "boolean",
        "default": True,
        "description": "Return a scene-wide scene_bim_facts relationship_scan after projection.",
    }
    props["relationshipSampleLimit"] = {
        "type": "integer",
        "minimum": 0,
        "maximum": 100,
        "default": 20,
        "description": "Sample limit passed to scene_bim_facts relationship_scan.",
    }
    props["targetLayer"] = {
        "type": "string",
        "description": (
            "Advanced/discouraged: passes targetLayer to /import and may destroy exported BIM "
            "layer organization such as RookBim > Level > Category."
        ),
    }
    return {
        "type": "object",
        "properties": props,
        "required": ["preset"],
        "additionalProperties": False,
    }
```

- [ ] **Step 4: Register the MCP tool**

In `list_tools()` near `rookbim_export_preset`, add:

```python
        Tool(
            name="rookbim_export_preset_to_rhino",
            description=(
                "Demo workflow: export a RookBIM preset bundle, import the generated .3dm into "
                "the current Rhino/Rhino.Inside document, project BIM sidecar facts for the "
                "imported objects, and optionally return a scene-wide BIM relationship summary. "
                "Mutates Rhino by importing geometry; does not modify Revit."
            ),
            inputSchema=_rookbim_export_preset_to_rhino_schema(),
        ),
```

- [ ] **Step 5: Add server dispatch case**

In `_call_tool_dispatch`, near `case "rookbim_export_preset":`, add:

```python
        case "rookbim_export_preset_to_rhino":
            from . import rookbim_export_to_rhino
            from .scene.bim_relationship_projection import project_bim_relationships_for_tool
            from .scene.bim_facts_query import query_bim_facts
            from .scene.scene_graph import get_scene_graph

            def _query_bim_facts_for_workflow(**kwargs):
                return query_bim_facts(get_scene_graph(), **kwargs)

            payload = await rookbim_export_to_rhino.export_preset_to_rhino(
                arguments,
                call_rhino_fn=call_rhino,
                project_relationships_fn=project_bim_relationships_for_tool,
                query_bim_facts_fn=_query_bim_facts_for_workflow,
            )
            if payload.get("success") is False:
                result = {"success": False, "data": payload}
            else:
                result = {"success": True, "data": payload}
```

- [ ] **Step 6: Run server workflow tests**

Run:

```bash
python -m pytest mcp_server/tests/test_rookbim_export_to_rhino_workflow.py -q
```

Expected: all workflow tests pass.

- [ ] **Step 7: Commit**

```bash
git add mcp_server/src/rook/server.py mcp_server/src/rook/rookbim_export_to_rhino.py mcp_server/tests/test_rookbim_export_to_rhino_workflow.py
git commit -m "feat: expose RookBIM export-to-Rhino MCP tool"
```

## Task 6: Local Dispatcher, Groups, and Targeting

**Files:**
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Modify: `mcp_server/src/rook/agent/tool_groups.py`
- Modify: `mcp_server/src/rook/targeting.py`
- Modify: `mcp_server/tests/test_rookbim_export_preset_tool.py`
- Modify: `mcp_server/tests/test_rookbim_export_to_rhino_workflow.py`
- Modify: `mcp_server/tests/test_rookbim_mcp_tools.py`

- [ ] **Step 1: Add failing grouping/targeting/local dispatcher tests**

Append to `mcp_server/tests/test_rookbim_export_preset_tool.py`:

```python
def test_export_preset_to_rhino_derives_mutate_policy():
    assert policy_for_tool("rookbim_export_preset_to_rhino") == RhinoToolPolicy(True, "mutate")
    assert "rookbim_export_preset_to_rhino" in _ALL_KNOWN_TOOLS
    assert "rookbim_export_preset_to_rhino" not in _META_TOOLS
    assert "rookbim_export_preset_to_rhino" not in _RHINO_READ_TOOLS
    assert "rookbim_export_preset_to_rhino" not in _RHINO_INDEPENDENT_READ_TOOLS
    assert "rookbim_export_preset_to_rhino" not in _RHINO_INDEPENDENT_MUTATE_TOOLS


def test_export_preset_to_rhino_in_full_group_not_readonly():
    assert "rookbim_export_preset_to_rhino" in tool_groups.TOOL_GROUPS["rookbim"]
    assert "rookbim_export_preset_to_rhino" not in tool_groups.TOOL_GROUPS["rookbim_readonly"]
```

Append to `mcp_server/tests/test_rookbim_export_to_rhino_workflow.py`:

```python
@pytest.mark.asyncio
async def test_local_dispatcher_registers_export_preset_to_rhino(monkeypatch):
    from rook.agent.tool_dispatcher import build_local_tools

    calls = []

    async def fake_workflow(arguments, **deps):
        calls.append(arguments)
        return {"success": True, "workflow": "rookbim_export_preset_to_rhino"}

    monkeypatch.setattr("rook.rookbim_export_to_rhino.export_preset_to_rhino", fake_workflow)

    tools = build_local_tools()
    result = await tools["rookbim_export_preset_to_rhino"](
        preset="openings_and_hosts",
        limitPerCategory=10,
        port=9876,
    )

    assert result["success"] is True
    assert calls == [{"preset": "openings_and_hosts", "limitPerCategory": 10, "port": 9876}]
```

In `mcp_server/tests/test_rookbim_mcp_tools.py`, add `"rookbim_export_preset_to_rhino": (None, None)` only to tests that assert groups/context, not to `ROOKBIM_TOOL_ROUTES`, because this tool is Python orchestration and has no native bridge route. Add a focused assertion instead:

```python
def test_rookbim_workflow_tool_is_not_raw_bridge_route():
    assert "rookbim_export_preset_to_rhino" not in ROOKBIM_TOOL_ROUTES
    assert "rookbim_export_preset_to_rhino" in tool_groups.TOOL_GROUPS["rookbim"]
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run:

```bash
python -m pytest mcp_server/tests/test_rookbim_export_to_rhino_workflow.py mcp_server/tests/test_rookbim_export_preset_tool.py mcp_server/tests/test_rookbim_mcp_tools.py -q
```

Expected: failures for missing grouping, targeting, and local dispatcher wiring.

- [ ] **Step 3: Add local dispatcher wrapper**

In `mcp_server/src/rook/agent/tool_dispatcher.py`, after the existing `scene_bim_facts` local tool block, add:

```python
    # --- rookbim_export_preset_to_rhino (Python-side demo workflow orchestration) ---
    try:
        from .. import rookbim_export_to_rhino
        from ..scene.bim_relationship_projection import project_bim_relationships_for_tool
        from ..scene.bim_facts_query import query_bim_facts
        from ..scene.scene_graph import get_scene_graph

        async def _rookbim_export_preset_to_rhino(**kwargs) -> dict:
            def _query_bim_facts_for_workflow(**query_kwargs):
                return query_bim_facts(get_scene_graph(), **query_kwargs)

            return await rookbim_export_to_rhino.export_preset_to_rhino(
                dict(kwargs),
                call_rhino_fn=call_rhino,
                project_relationships_fn=project_bim_relationships_for_tool,
                query_bim_facts_fn=_query_bim_facts_for_workflow,
            )

        tools["rookbim_export_preset_to_rhino"] = _rookbim_export_preset_to_rhino
    except ImportError:
        logger.debug("rookbim_export_preset_to_rhino local tool unavailable (import failed)")
```

- [ ] **Step 4: Add tool group membership**

In `mcp_server/src/rook/agent/tool_groups.py`, add after `"rookbim_export_preset"`:

```python
        "rookbim_export_preset_to_rhino",
```

Do not edit `TOOL_GROUPS["rookbim_readonly"]`.

- [ ] **Step 5: Add targeting membership**

In `mcp_server/src/rook/targeting.py`, add `"rookbim_export_preset_to_rhino"` to `_ALL_KNOWN_TOOLS` near `"rookbim_export_preset"`.

Do not add it to `_META_TOOLS`, `_RHINO_READ_TOOLS`, `_RHINO_INDEPENDENT_READ_TOOLS`, or `_RHINO_INDEPENDENT_MUTATE_TOOLS`.

- [ ] **Step 6: Run focused tests and fix any route-list assumptions**

Run:

```bash
python -m pytest mcp_server/tests/test_rookbim_export_to_rhino_workflow.py mcp_server/tests/test_rookbim_export_preset_tool.py mcp_server/tests/test_rookbim_mcp_tools.py -q
```

Expected: pass. If `test_rookbim_tool_groups_match_phase1_scope` asserts exact equality to `ROOKBIM_TOOL_ROUTES`, update the expected list in that test to:

```python
expected_rookbim = list(ROOKBIM_TOOL_ROUTES) + ["rookbim_export_preset_to_rhino"]
assert tool_groups.TOOL_GROUPS["rookbim"] == expected_rookbim
```

- [ ] **Step 7: Commit**

```bash
git add mcp_server/src/rook/agent/tool_dispatcher.py mcp_server/src/rook/agent/tool_groups.py mcp_server/src/rook/targeting.py mcp_server/tests/test_rookbim_export_preset_tool.py mcp_server/tests/test_rookbim_export_to_rhino_workflow.py mcp_server/tests/test_rookbim_mcp_tools.py
git commit -m "feat: wire RookBIM export-to-Rhino workflow tool"
```

## Task 7: Regression Verification and Optional Live Smoke

**Files:**
- No expected source changes unless tests expose a defect.

- [ ] **Step 1: Run focused Python tests**

Run:

```bash
python -m pytest mcp_server/tests/test_rookbim_export_to_rhino_workflow.py mcp_server/tests/test_rookbim_export_preset_tool.py mcp_server/tests/test_rookbim_mcp_tools.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run adjacent BIM graph/read-model tests**

Run:

```bash
python -m pytest mcp_server/tests/test_bim_relationship_projection.py mcp_server/tests/test_bim_relationship_projection_tool.py mcp_server/tests/test_bim_facts_query.py mcp_server/tests/test_scene_graph.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Run bridge/targeting registration tests**

Run:

```bash
python -m pytest mcp_server/tests/test_bridge.py mcp_server/tests/test_session_routing.py -q
```

Expected: all tests pass.

- [ ] **Step 4: Run diff hygiene checks**

Run:

```bash
git diff --check
git status --short --branch
```

Expected: `git diff --check` prints nothing. Status shows only the feature branch and no unstaged changes after all commits.

- [ ] **Step 5: Optional live smoke when RIR/RookNative is discoverable**

Only run this if a native Rook instance is discoverable and the user has a Revit sample model open in Rhino.Inside.Revit with an active 3D view. Start from a clean or isolated Rhino/RIR document if validating `bimFacts` counts.

Use the MCP tool once it is installed in the active MCP server:

```json
{
  "preset": "openings_and_hosts",
  "scope": "active_view",
  "limitPerCategory": 10,
  "allowTruncated": true,
  "allowBboxProxy": true
}
```

Expected result:

```text
success=true
paths.model3dm exists
paths.sidecar exists
import.importedObjectCount > 0
projection.joinedObjectCount > 0
bimFacts.success=true when relationshipSummary is true
```

Then call `scene_context` on one imported id with `sync=false`:

```json
{
  "object_ids": ["<one imported id>"],
  "sync": false
}
```

Expected: context renders a BIM block with Revit identity and room/level/host facts where available.

- [ ] **Step 6: Commit only if verification required a fix**

If Task 7 required fixes, commit them:

```bash
git add <changed files>
git commit -m "fix: stabilize RookBIM export-to-Rhino workflow"
```

If Task 7 changed nothing, do not create an empty commit.

## Self-Review

- Spec coverage:
  - New MCP workflow tool: Tasks 5 and 6.
  - Python/MCP orchestration only: Tasks 1-6; no C++ or C# files.
  - Reuse `/bim/export-preset`, `/import`, projection, and facts: Task 3.
  - Preserve `rookbim_export_preset`: Tasks 1 and 5 forward only export fields; Task 5 adds a new schema helper.
  - Optional output generation: Task 1.
  - Path precedence: Task 2.
  - Projection scoped to imported ids: Task 3.
  - Scene-wide `bimFacts`: Tasks 3 and 4.
  - Partial failure semantics: Tasks 2 and 4.
  - `targetLayer` warning and no default target layer: Tasks 3 and 5.
  - Tool groups/targeting/local dispatcher: Task 6.
  - Focused tests and live smoke: Task 7.
- Placeholder scan:
  - No forbidden placeholder language or unspecified test steps.
- Type consistency:
  - Helper names are consistently `default_output_for_preset`, `build_export_request`, `resolve_artifact_paths`, `stage_failure`, and `export_preset_to_rhino`.
  - External tool name is consistently `rookbim_export_preset_to_rhino`.
  - Response block names match the spec: `export`, `paths`, `import`, `projection`, `bimFacts`.
