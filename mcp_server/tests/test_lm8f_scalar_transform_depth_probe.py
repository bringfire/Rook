from __future__ import annotations

import importlib.util
import inspect
import json
import sys
from pathlib import Path

import pytest


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm8f_scalar_transform_depth_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm8f_scalar_transform_depth_probe",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()


def test_cli_defaults_are_canonical_transform_shape():
    args = PROBE._args([])

    assert args.model == "gemma4:12b-it-qat"
    assert args.endpoint == "http://localhost:11434/api/chat"
    assert args.temperature == 0
    assert args.timeout_s == 120
    assert args.excerpt_chars == 1200
    assert args.run_dir == "probe_runs"
    assert args.canonical_evidence is True


def test_cli_overrides_are_exploratory_unless_explicitly_marked_canonical():
    args = PROBE._args(["--model", "qwen3:14b"])

    assert args.canonical_evidence is False


def test_cli_rejects_non_lm8f_surfaces():
    forbidden = [
        ["--phase", "receipt_recon"],
        ["--attempts", "5"],
        ["--retry-clean-observation"],
        ["--planner-provider-command", "x"],
        ["--prompt-profile", "shape_guidance_v2"],
        ["--request-json", "request.json"],
        ["--gh-edit"],
    ]
    for argv in forbidden:
        with pytest.raises(SystemExit):
            PROBE._args(argv)


def test_canonical_evidence_requires_default_shape():
    args = PROBE._args(["--canonical-evidence"])
    assert PROBE._canonical_evidence_is_valid(args) is True

    for argv in (
        ["--canonical-evidence", "--model", "qwen3:14b"],
        ["--canonical-evidence", "--endpoint", "http://example.invalid/chat"],
        ["--canonical-evidence", "--temperature", "0.2"],
    ):
        assert PROBE._canonical_evidence_is_valid(PROBE._args(argv)) is False


def test_manifest_records_lm8f_identity():
    manifest = PROBE._manifest(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        canonical_evidence=True,
    )

    assert manifest["schema"] == "rook.lm8f_scalar_transform_depth_probe:v1"
    assert manifest["attempts"] == 1
    assert manifest["expected_output_value"] == 7.5
    assert manifest["initial_editable_value"] == 2.0
    assert manifest["offset_value"] == 1.5
    assert manifest["initial_observed_output"] == 3.5
    assert manifest["projection_id"] == "editable_plus_offset"
    assert manifest["worker_retry_enabled"] is False
    assert manifest["planner_model"] is None
    assert manifest["gh_edit_enabled"] is False


class FakeToolExecutor:
    def __init__(self, responses):
        self.responses = dict(responses)
        self.calls = []

    async def __call__(self, tool_name, args):
        self.calls.append((tool_name, dict(args)))
        value = self.responses[tool_name]
        if isinstance(value, list):
            value = value.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def _run(coro):
    import asyncio

    return asyncio.run(coro)


def test_preflight_accepts_pong_and_document_created():
    executor = FakeToolExecutor(
        {
            "rhino_ping": "pong",
            "gh_document_new": {"success": True, "data": {"Created": True}},
        }
    )

    ok, reason, summaries = _run(PROBE._run_preflight(executor))

    assert ok is True
    assert reason is None
    assert summaries["rhino_ping"] == "pong"
    assert summaries["gh_document_new"] == {"success": True, "data": {"Created": True}}
    assert executor.calls == [("rhino_ping", {}), ("gh_document_new", {})]


def test_preflight_classifies_ping_and_document_failures():
    ping_failed = FakeToolExecutor(
        {
            "rhino_ping": {"success": False, "error": "offline"},
            "gh_document_new": {"created": True},
        }
    )
    ok, reason, _summaries = _run(PROBE._run_preflight(ping_failed))
    assert ok is False
    assert reason == "rhino_ping_failed"
    assert ping_failed.calls == [("rhino_ping", {})]

    document_failed = FakeToolExecutor(
        {
            "rhino_ping": "pong",
            "gh_document_new": {"created": False},
        }
    )
    ok, reason, _summaries = _run(PROBE._run_preflight(document_failed))
    assert ok is False
    assert reason == "gh_document_new_failed"


def test_tool_result_field_helpers_handle_top_level_and_nested_data():
    assert PROBE._tool_field(
        {"success": True, "value": "TOP", "data": {"Value": "NESTED"}},
        "value",
        "Value",
    ) == "TOP"
    assert PROBE._tool_field(
        {"success": True, "data": {"Value": "NESTED"}},
        "value",
        "Value",
    ) == "NESTED"
    assert PROBE._guid_from_result(
        {"success": True, "data": {"Guid": "COMPONENT-GUID"}}
    ) == "COMPONENT-GUID"


def test_inspect_output_scalar_value_accepts_real_preview_shape():
    assert PROBE._inspect_output_scalar_value(
        {
            "success": True,
            "data": {
                "param_nickname": "R",
                "structure": "single",
                "data_count": 1,
                "preview": ["7.5"],
            },
        }
    ) == 7.5
    assert PROBE._inspect_output_scalar_value(
        {"success": True, "data_count": 1, "preview": [3.5]}
    ) == 3.5


@pytest.mark.parametrize(
    "result",
    [
        {"success": True, "data": {"data_count": 0, "preview": []}},
        {"success": True, "data": {"data_count": 1, "preview": ["not-number"]}},
        {"success": False, "data": "Object not found"},
    ],
)
def test_inspect_output_scalar_value_rejects_invalid_live_shapes(result):
    with pytest.raises(ValueError, match="inspect output scalar"):
        PROBE._inspect_output_scalar_value(result)


def _fixture_tool_responses(*, editable_value="2.0", observed_output="3.5"):
    return {
        "gh_library": {
            "success": True,
            "count": 1,
            "components": [
                {
                    "name": "Addition",
                    "nickName": "A+B",
                    "category": "Maths",
                    "guid": "ADDITION-PROXY-GUID",
                }
            ],
        },
        "gh_create_slider": [
            {
                "success": True,
                "data": {
                    "Created": True,
                    "Guid": "EDITABLE-GUID-1",
                    "NickName": "LM8F_Editable",
                },
            },
            {
                "success": True,
                "data": {
                    "Created": True,
                    "Guid": "OFFSET-GUID-1",
                    "NickName": "LM8F_Offset",
                },
            },
        ],
        "gh_create_component": {
            "success": True,
            "data": {
                "Created": True,
                "Guid": "ADDITION-GUID-1",
                "NickName": "A+B",
            },
        },
        "gh_connect": [
            {"success": True, "data": {"connected": True}},
            {"success": True, "data": {"connected": True}},
        ],
        "gh_solve": {"success": True, "data": {"scheduled": True}},
        "gh_get_value": {
            "success": True,
            "data": {"Guid": "EDITABLE-GUID-1", "Value": editable_value},
        },
        "gh_inspect_output": {
            "success": True,
            "data": {
                "param_nickname": "R",
                "structure": "single",
                "data_count": 1,
                "preview": [observed_output],
            },
        },
    }


def test_create_transform_fixture_uses_direct_tools_and_hashes_worker_hidden_guid():
    executor = FakeToolExecutor(
        {
            "gh_library": {
                "success": True,
                "count": 1,
                "components": [
                    {
                        "name": "Addition",
                        "nickName": "A+B",
                        "category": "Maths",
                        "guid": "ADDITION-PROXY-GUID",
                    }
                ],
            },
            "gh_create_slider": [
                {
                    "success": True,
                    "data": {
                        "Created": True,
                        "Guid": "EDITABLE-GUID-1",
                        "NickName": "LM8F_Editable",
                    },
                },
                {
                    "success": True,
                    "data": {
                        "Created": True,
                        "Guid": "OFFSET-GUID-1",
                        "NickName": "LM8F_Offset",
                    },
                },
            ],
            "gh_create_component": {
                "success": True,
                "data": {
                    "Created": True,
                    "Guid": "ADDITION-GUID-1",
                    "NickName": "A+B",
                },
            },
            "gh_connect": [
                {"success": True, "data": {"connected": True}},
                {"success": True, "data": {"connected": True}},
            ],
            "gh_solve": {"success": True, "data": {"scheduled": True}},
            "gh_get_value": {
                "success": True,
                "data": {"Guid": "EDITABLE-GUID-1", "Value": "2.0"},
            },
            "gh_inspect_output": {
                "success": True,
                "data": {
                    "param_nickname": "R",
                    "structure": "single",
                    "data_count": 1,
                    "preview": ["3.5"],
                },
            },
        }
    )

    fixture = _run(PROBE._create_transform_fixture(executor))

    assert executor.calls == [
        ("gh_library", {"search": "addition", "limit": 20}),
        (
            "gh_create_slider",
            {
                "nickname": "LM8F_Editable",
                "min": 0,
                "max": 10,
                "value": 2.0,
                "x": 20,
                "y": 80,
            },
        ),
        (
            "gh_create_slider",
            {
                "nickname": "LM8F_Offset",
                "min": 0,
                "max": 10,
                "value": 1.5,
                "x": 20,
                "y": 180,
            },
        ),
        ("gh_create_component", {"guid": "ADDITION-PROXY-GUID", "x": 280, "y": 120}),
        (
            "gh_connect",
            {
                "sourceGuid": "EDITABLE-GUID-1",
                "targetGuid": "ADDITION-GUID-1",
                "targetParam": "A",
            },
        ),
        (
            "gh_connect",
            {
                "sourceGuid": "OFFSET-GUID-1",
                "targetGuid": "ADDITION-GUID-1",
                "targetParam": "B",
            },
        ),
        ("gh_solve", {"delay": 25}),
        ("gh_get_value", {"guid": "EDITABLE-GUID-1"}),
        ("gh_inspect_output", {"guid": "ADDITION-GUID-1", "param": "R"}),
    ]
    assert fixture["editable_component_guid"] == "EDITABLE-GUID-1"
    assert fixture["offset_component_guid"] == "OFFSET-GUID-1"
    assert fixture["addition_component_guid"] == "ADDITION-GUID-1"
    assert fixture["editable_value"] == 2.0
    assert fixture["observed_output_value"] == 3.5
    assert fixture["receipt"]["editable_value"] == 2.0
    assert fixture["receipt"]["observed_output_value"] == 3.5
    assert fixture["receipt"]["scalar_anchor"]["internal_component_guid"] == "EDITABLE-GUID-1"
    rendered_visible = json.dumps(fixture["visible_receipt"], sort_keys=True)
    assert "EDITABLE-GUID-1" not in rendered_visible
    assert "OFFSET-GUID-1" not in rendered_visible
    assert "ADDITION-GUID-1" not in rendered_visible
    assert fixture["fixture_setup_summary"]["editable_component_guid"] == "EDITABLE-GUID-1"
    assert fixture["fixture_setup_summary"]["addition_component_guid"] == "ADDITION-GUID-1"


def test_create_transform_fixture_rejects_missing_addition_component():
    executor = FakeToolExecutor(
        {
            "gh_library": {
                "success": True,
                "count": 1,
                "components": [{"name": "Multiply", "nickName": "A*B", "category": "Maths"}],
            },
        }
    )

    with pytest.raises(ValueError, match="gh_library_addition_not_found"):
        _run(PROBE._create_transform_fixture(executor))

    assert executor.calls == [("gh_library", {"search": "addition", "limit": 20})]


def test_create_transform_fixture_rejects_noncanonical_editable_precheck_value():
    executor = FakeToolExecutor(_fixture_tool_responses(editable_value="2.25"))

    with pytest.raises(ValueError, match="initial_editable_value_mismatch"):
        _run(PROBE._create_transform_fixture(executor))


def test_create_transform_fixture_rejects_noncanonical_initial_observed_output():
    executor = FakeToolExecutor(_fixture_tool_responses(observed_output="3.25"))

    with pytest.raises(ValueError, match="initial_observed_output_mismatch"):
        _run(PROBE._create_transform_fixture(executor))
