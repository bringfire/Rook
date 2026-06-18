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
