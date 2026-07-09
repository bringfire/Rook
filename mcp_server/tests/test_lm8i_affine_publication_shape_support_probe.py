from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm8i_affine_publication_shape_support_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm8i_affine_publication_shape_support_probe",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()


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


def _fixture_tool_responses():
    return {
        "gh_library": [
            {
                "success": True,
                "count": 1,
                "components": [
                    {
                        "name": "Multiplication",
                        "nickName": "A*B",
                        "category": "Maths",
                        "guid": "MULTIPLY-PROXY-GUID",
                        "deprecated": False,
                    }
                ],
            },
            {
                "success": True,
                "count": 1,
                "components": [
                    {
                        "name": "Addition",
                        "nickName": "A+B",
                        "category": "Maths",
                        "guid": "ADDITION-PROXY-GUID",
                        "deprecated": False,
                    }
                ],
            },
        ],
        "gh_create_slider": [
            {
                "success": True,
                "data": {
                    "Created": True,
                    "Guid": "EDITABLE-GUID-1",
                    "NickName": "LM8I_Editable",
                },
            },
            {
                "success": True,
                "data": {
                    "Created": True,
                    "Guid": "FACTOR-GUID-1",
                    "NickName": "LM8I_Factor",
                },
            },
            {
                "success": True,
                "data": {
                    "Created": True,
                    "Guid": "OFFSET-GUID-1",
                    "NickName": "LM8I_Offset",
                },
            },
        ],
        "gh_create_component": [
            {
                "success": True,
                "data": {"Created": True, "Guid": "MULTIPLY-GUID-1", "NickName": "A*B"},
            },
            {
                "success": True,
                "data": {"Created": True, "Guid": "ADDITION-GUID-1", "NickName": "A+B"},
            },
        ],
        "gh_connect": [
            {"success": True, "data": {"connected": True}},
            {"success": True, "data": {"connected": True}},
            {"success": True, "data": {"connected": True}},
            {"success": True, "data": {"connected": True}},
        ],
        "gh_solve": {"success": True, "data": {"scheduled": True}},
        "gh_get_value": [
            {"success": True, "data": {"Guid": "EDITABLE-GUID-1", "Value": "2.0"}},
            {"success": True, "data": {"Guid": "FACTOR-GUID-1", "Value": "2.0"}},
            {"success": True, "data": {"Guid": "OFFSET-GUID-1", "Value": "1.5"}},
        ],
        "gh_inspect_output": {
            "success": True,
            "data": {"data_count": 1, "preview": ["5.5"]},
        },
    }


def _run(coro):
    import asyncio

    return asyncio.run(coro)


def test_cli_defaults_are_canonical_lm8i_shape():
    args = PROBE._args([])

    assert args.model == "gemma4:12b-it-qat"
    assert args.endpoint == "http://localhost:11434/api/chat"
    assert args.temperature == 0
    assert args.timeout_s == 120
    assert args.excerpt_chars == 1200
    assert args.run_dir == "probe_runs"
    assert args.canonical_evidence is True


def test_cli_rejects_non_lm8i_surfaces():
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


def test_manifest_records_lm8i_identity():
    manifest = PROBE._manifest(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        canonical_evidence=True,
    )

    assert manifest["schema"] == "rook.lm8i_affine_publication_shape_support_probe:v1"
    assert manifest["attempts"] == 1
    assert manifest["publication_support_enabled"] is True
    assert manifest["publication_support_budget"] == 1
    assert manifest["support_eligibility"] == "exact_skeletal_action_request_missing_action_id"
    assert manifest["worker_retry_enabled"] is False
    assert manifest["planner_model"] is None
    assert manifest["gh_edit_enabled"] is False


def test_lm8i_identity_surfaces_do_not_emit_lm8h_labels():
    failure = PROBE.FixtureSetupFailure(
        step="gh_create_slider",
        tool_name="gh_create_slider",
        failure_reason="boom",
        result={"Guid": "GUID-1", "NickName": "LM8I_Editable"},
    )
    summary = PROBE._fixture_failure_summary(failure, excerpt_chars=1200)
    scaffold = PROBE._affine_scalar_scaffold(
        PROBE.PlanGraph(nodes={}, memory=PROBE.GraphMemory())
    )

    assert summary["schema"] == "rook.lm8i_fixture_failure_summary:v1"
    assert scaffold.workflow_id == "lm8i-gh-affine-scalar-transform"
    assert scaffold.contract_snapshot.workflow_id == "lm8i-gh-affine-scalar-transform"
    assert scaffold.contract_snapshot.normalized_contract["workflow_id"] == "lm8i-gh-affine-scalar-transform"
    assert scaffold.compile_record.workflow_id == "lm8i-gh-affine-scalar-transform"
    assert scaffold.compile_record.compiler_id == "lm8i.script_local_affine_scaffold:v1"
    assert scaffold.compile_record.provider_id == "lm8i.script_local_provider:v1"

    rendered = json.dumps(
        {
            "summary": summary,
            "contract": scaffold.contract_snapshot.normalized_contract,
            "compile_record": {
                "workflow_id": scaffold.compile_record.workflow_id,
                "compiler_id": scaffold.compile_record.compiler_id,
                "provider_id": scaffold.compile_record.provider_id,
            },
        },
        sort_keys=True,
        default=str,
    ).casefold()
    assert "lm8h" not in rendered


def test_create_affine_fixture_uses_lm8i_nicknames_and_labels():
    executor = FakeToolExecutor(_fixture_tool_responses())
    fixture = _run(PROBE._create_affine_fixture(executor))

    assert fixture["visible_receipt"]["scalar_anchor"]["editable_value_contract"][
        "label"
    ] == "LM8I_Editable"
    assert fixture["receipt"]["scalar_anchor"]["editable_value_contract"][
        "label"
    ] == "LM8I_Editable"
    assert executor.calls[2:5] == [
        (
            "gh_create_slider",
            {"nickname": "LM8I_Editable", "min": 0, "max": 10, "value": 2.0, "x": 20, "y": 80},
        ),
        (
            "gh_create_slider",
            {"nickname": "LM8I_Factor", "min": 0, "max": 10, "value": 2.0, "x": 20, "y": 180},
        ),
        (
            "gh_create_slider",
            {"nickname": "LM8I_Offset", "min": 0, "max": 10, "value": 1.5, "x": 20, "y": 280},
        ),
    ]
    rendered = json.dumps(fixture, sort_keys=True, default=str).casefold()
    assert "lm8h" not in rendered
