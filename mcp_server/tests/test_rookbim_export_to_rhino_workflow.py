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


def test_helpers_accept_positional_now(monkeypatch, tmp_path):
    monkeypatch.setenv("TEMP", str(tmp_path))
    now = dt.datetime(2026, 6, 18, 9, 4, 5)

    output = workflow.default_output_for_preset("openings_and_hosts", now)
    request, effective_output = workflow.build_export_request(
        {"preset": "openings_and_hosts"},
        now,
    )

    assert output["name"] == "openings_and_hosts-20260618-090405"
    assert request["output"] == effective_output
    assert effective_output["name"] == "openings_and_hosts-20260618-090405"


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
    await workflow.export_preset_to_rhino(
        {
            "preset": "openings_and_hosts",
            "output": {"directory": str(tmp_path), "name": "c"},
            "targetLayer": "",
        },
        call_rhino_fn=fake_call_rhino,
        project_relationships_fn=fake_project,
        query_bim_facts_fn=lambda **kwargs: {"success": True},
    )

    assert import_payloads[0] == {"path": str(tmp_path / "a.3dm")}
    assert import_payloads[1] == {"path": str(tmp_path / "b.3dm"), "targetLayer": "Demo Import"}
    assert import_payloads[2] == {"path": str(tmp_path / "c.3dm"), "targetLayer": ""}


@pytest.mark.asyncio
async def test_workflow_accepts_positional_dependency_functions(tmp_path):
    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        if path == "/bim/export-preset":
            return {"success": True, "data": {}}
        if path == "/import":
            return {"success": True, "data": {"importedIds": ["rh-1"]}}
        raise AssertionError(path)

    async def fake_project(**kwargs):
        return {"success": True}

    result = await workflow.export_preset_to_rhino(
        {"preset": "openings_and_hosts", "output": {"directory": str(tmp_path), "name": "a"}},
        fake_call_rhino,
        fake_project,
        lambda **kwargs: {"success": True},
    )

    assert result["success"] is True
    assert result["import"]["importedIds"] == ["rh-1"]


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
        return {
            "success": False,
            "error": "bim_projection_invalid_sidecar",
            "message": "bad sidecar",
        }

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
    project_calls = []
    projection_block = {"success": True, "joinedObjectCount": 1, "source": "projection-still-ran"}

    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        if path == "/bim/export-preset":
            return {"success": True, "data": {}}
        if path == "/import":
            return {"success": True, "data": {"importedIds": ["rh-1"]}}
        raise AssertionError(path)

    async def fake_project(**kwargs):
        project_calls.append(kwargs)
        return projection_block

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
    assert result["projection"] == projection_block
    assert result["bimFacts"] == {}
    assert project_calls == [
        {
            "sidecar_path": str(tmp_path / "model.sidecar.json"),
            "object_ids": ["rh-1"],
            "include_rooms": True,
            "include_levels": True,
            "port": None,
        }
    ]
    assert fact_calls == []
