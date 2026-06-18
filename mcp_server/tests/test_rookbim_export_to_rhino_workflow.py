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
