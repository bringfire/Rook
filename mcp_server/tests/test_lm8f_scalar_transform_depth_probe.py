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


def test_lm8f_source_does_not_import_repair_planner_retry_or_gh_edit_paths():
    source = inspect.getsource(PROBE)

    forbidden_import_or_call_fragments = (
        "lm6a_live_worker_splice_probe",
        "lm7b_request_driven_live_splice_probe",
        "lm7c_planner_authoring_probe",
        "lm7e_model_authored_live_splice_probe",
        "planner_worker_contract_request",
        "workflow_validate",
        "--retry-clean-observation",
        '"gh_edit"',
        "'gh_edit'",
        "gh_update_script",
    )
    for fragment in forbidden_import_or_call_fragments:
        assert fragment not in source

    policy_markers_allowed = (
        "PROBE_REPAIR_CODE",
        "A = 42.0",
        "BindStepSpec.base_params",
        "repair_same_component.bind.base_params",
    )
    for marker in policy_markers_allowed:
        assert marker in source


def test_lm8f_source_contains_hidden_expected_value_only_as_policy_or_test_oracle():
    source = inspect.getsource(PROBE)

    assert "EXPECTED_WORKER_VALUE" not in source
    assert "set editable value to 6.0" not in source
    assert "use 6.0" not in source


def test_scalar_transform_source_routing_artifact_uses_task1_canonical_route_ids():
    artifact = PROBE._scalar_transform_source_routing_artifact()

    route_ids = [
        item["route_id"]
        for item in artifact["routes"][0]["visible_sources"]
    ]

    assert route_ids == [
        "scalar_transform_expected_output",
        "scalar_transform_offset_value",
        "scalar_transform_projection",
        "scalar_transform_current_output",
        "scalar_transform_current_editable_value",
        "scalar_transform_editable_target_contract",
        "scalar_transform_set_value_convention",
    ]


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


class FakePublication:
    def __init__(self, row, response_payload=None):
        self.row = row
        self.response_payload = response_payload


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


def _valid_transform_fixture():
    return {
        "editable_component_guid": "EDITABLE-GUID-1",
        "offset_component_guid": "OFFSET-GUID-1",
        "addition_component_guid": "ADDITION-GUID-1",
        "editable_value": 2.0,
        "observed_output_value": 3.5,
        "receipt": {
            "editable_value": 2.0,
            "observed_output_value": 3.5,
            "scalar_anchor": {
                "internal_component_guid": "EDITABLE-GUID-1",
                "editable_value_contract": {
                    "label": "LM8F_Editable",
                    "value_type": "number",
                    "current_value": 2.0,
                    "projection_id": "editable_plus_offset",
                },
            },
        },
        "visible_receipt": {},
        "fixture_setup_summary": {},
    }


def test_scalar_transform_runtime_context_static_validates_without_lm5x_routability():
    graph = PROBE._graph_from_transform_receipt(_valid_transform_fixture()["receipt"])
    context = PROBE._scalar_runtime_context(
        graph=graph,
        workflow_contract_payload=PROBE._scalar_transform_contract_payload(),
        convention_packets=(),
    )

    routing_report = context["static_routing_report"]
    assert routing_report["valid"] is True
    assert routing_report["routability_evaluated"] is False
    assert context["scalar_runtime_ready"] is True
    assert context["sources"].expected_output_contract.value == 7.5
    assert context["sources"].offset_contract.value == 1.5
    assert context["sources"].editable_observation.value == 2.0
    assert context["sources"].observed_output.value == 3.5
    assert context["packet"]["fields"]["expected_output_value"] == 7.5
    assert context["packet"]["fields"]["offset_value"] == 1.5
    assert context["worker_visible"]["source"] == "gh_scalar_transform_expectation"


def test_scalar_transform_runtime_context_fails_when_live_receipt_missing_output():
    receipt = _valid_transform_fixture()["receipt"]
    receipt.pop("observed_output_value")
    graph = PROBE._graph_from_transform_receipt(receipt)

    with pytest.raises(ValueError, match="observed_output_value"):
        PROBE._scalar_runtime_context(
            graph=graph,
            workflow_contract_payload=PROBE._scalar_transform_contract_payload(),
            convention_packets=(),
        )


def test_scalar_transform_runtime_context_rejects_projection_invariant_mismatch():
    graph = PROBE._graph_from_transform_receipt(_valid_transform_fixture()["receipt"])
    payload = PROBE._scalar_transform_contract_payload()
    payload["rules"]["verify_scalar_transform_output"]["offset_value"] = 1.25

    with pytest.raises(ValueError, match="projection_invariant_mismatch"):
        PROBE._scalar_runtime_context(
            graph=graph,
            workflow_contract_payload=payload,
            convention_packets=(),
        )


def test_worker_request_uses_transform_knowledge_and_never_exposes_raw_guid_or_derived_value():
    fixture = _valid_transform_fixture()
    graph = PROBE._graph_from_transform_receipt(fixture["receipt"])
    runtime = PROBE._scalar_runtime_context(
        graph=graph,
        workflow_contract_payload=PROBE._scalar_transform_contract_payload(),
        convention_packets=(),
    )

    payload = PROBE._build_local_turn_payload(
        graph=graph,
        packet=runtime["packet"],
        worker_visible=runtime["worker_visible"],
    )

    rendered = json.dumps(payload, sort_keys=True)
    assert payload["schema"] == "rook.local_worker_turn_request:v1"
    assert "gh_scalar_transform_expectation_evidence" in rendered
    assert "draft_gh_set_value_params" in rendered
    assert "observed_output = editable_value + offset_value" in rendered
    assert "current_editable_value" in rendered
    assert "offset_value" in rendered
    assert "expected_output_value" in rendered
    assert "EDITABLE-GUID-1" not in rendered
    assert "OFFSET-GUID-1" not in rendered
    assert "ADDITION-GUID-1" not in rendered
    assert "6.0" not in rendered
    assert "set editable value to 6" not in rendered.lower()
    assert "gh_edit" not in rendered
    assert "gh_update_script" not in rendered
    assert "repair_same_component" not in rendered
    assert "action_selection_contract" in rendered
    assert "pass1_decision_required_fields_if_acting" in rendered
    assert "final_action_request_required_fields" in rendered
    assert "do not author target GUID" in rendered
    assert "do not call GH tools directly" in rendered
    assert "do not author topology, code, or batch edits" in rendered


def test_publication_non_action_maps_to_worker_declined():
    row = {
        "status": "published",
        "pass2_response_kind": "observation",
        "observation_action_intent_anomaly": False,
    }
    payload = {
        "schema": "rook.local_worker_turn_response:v1",
        "kind": "observation",
        "message": "not acting",
        "data": None,
    }

    decision = PROBE._decision_from_publication(row, payload)

    assert decision == {
        "decision": "worker_declined",
        "reason": "worker_observed",
        "phase": "worker_publication",
        "final_worker_response_kind": "observation",
    }


def test_publication_failure_maps_to_publication_failed():
    decision = PROBE._decision_from_publication(
        {"status": "pass2_lm5g_invalid", "failure_reason": "bad-json"},
        None,
    )

    assert decision["decision"] == "publication_failed"
    assert decision["reason"] == "pass2_lm5g_invalid:bad-json"


def test_missing_pass1_action_id_stays_publication_failed():
    decision = PROBE._decision_from_publication(
        {
            "status": "pass1_decision_invalid",
            "failure_reason": "pass1_missing_action_id",
            "pass1_content_excerpt": '{"kind": "action_request"}',
        },
        None,
    )

    assert decision == {
        "decision": "publication_failed",
        "reason": "pass1_decision_invalid:pass1_missing_action_id",
        "phase": "worker_publication",
    }


def test_dispatch_set_value_solve_and_verify_accepts_inspected_output_match():
    executor = FakeToolExecutor(
        {
            "gh_set_value": {
                "success": True,
                "data": {"Guid": "EDITABLE-GUID-1", "NewValue": 6.0},
            },
            "gh_solve": {"success": True, "data": {"scheduled": True}},
            "gh_inspect_output": {
                "success": True,
                "data": {
                    "param_nickname": "R",
                    "structure": "single",
                    "data_count": 1,
                    "preview": ["7.5"],
                },
            },
        }
    )

    result = _run(
        PROBE._dispatch_set_value_solve_and_verify(
            tool_executor=executor,
            editable_component_guid="EDITABLE-GUID-1",
            addition_component_guid="ADDITION-GUID-1",
            worker_value=6.0,
            expected_value=7.5,
        )
    )

    assert result["decision"]["decision"] == "accepted"
    assert result["decision"]["reason"] == "verify_scalar_output_succeeded"
    assert result["live_set_value_summary"]["component_guid"] == "EDITABLE-GUID-1"
    assert result["live_set_value_summary"]["worker_action_value"] == 6.0
    assert result["verify_scalar_output_summary"]["component_guid_sha256"].startswith("sha256:")
    assert "component_guid" not in result["verify_scalar_output_summary"]
    assert result["verify_scalar_output_summary"]["observed_output_value"] == 7.5
    assert executor.calls == [
        ("gh_set_value", {"guid": "EDITABLE-GUID-1", "value": 6.0}),
        ("gh_solve", {"delay": 25}),
        ("gh_inspect_output", {"guid": "ADDITION-GUID-1", "param": "R"}),
    ]


def test_dispatch_set_value_solve_and_verify_rejects_inspected_output_mismatch():
    executor = FakeToolExecutor(
        {
            "gh_set_value": {
                "success": True,
                "data": {"Guid": "EDITABLE-GUID-1", "NewValue": 6.0},
            },
            "gh_solve": {"success": True, "data": {"scheduled": True}},
            "gh_inspect_output": {
                "success": True,
                "data": {"data_count": 1, "preview": ["6.5"]},
            },
        }
    )

    result = _run(
        PROBE._dispatch_set_value_solve_and_verify(
            tool_executor=executor,
            editable_component_guid="EDITABLE-GUID-1",
            addition_component_guid="ADDITION-GUID-1",
            worker_value=6.0,
            expected_value=7.5,
        )
    )

    assert result["decision"]["decision"] == "rejected"
    assert result["decision"]["reason"] == "verify_scalar_output_failed"
    assert result["verify_scalar_output_summary"]["observed_output_value"] == 6.5
    assert result["verify_scalar_output_summary"]["attempt_count"] == 3
    assert [attempt["observed_output_value"] for attempt in result["verify_scalar_output_summary"]["attempts"]] == [
        6.5,
        6.5,
        6.5,
    ]


def test_dispatch_set_value_solve_and_verify_accepts_when_set_reports_false_but_output_matches():
    executor = FakeToolExecutor(
        {
            "gh_set_value": {
                "success": False,
                "data": {"Guid": "EDITABLE-GUID-1", "NewValue": 6.0},
            },
            "gh_solve": {"success": True, "data": {"scheduled": True}},
            "gh_inspect_output": {
                "success": True,
                "data": {"data_count": 1, "preview": ["7.5"]},
            },
        }
    )

    result = _run(
        PROBE._dispatch_set_value_solve_and_verify(
            tool_executor=executor,
            editable_component_guid="EDITABLE-GUID-1",
            addition_component_guid="ADDITION-GUID-1",
            worker_value=6.0,
            expected_value=7.5,
        )
    )

    assert result["live_set_value_summary"]["set_value_reported_success"] is False
    assert result["decision"]["decision"] == "accepted"


def test_dispatch_set_value_solve_and_verify_rejects_transport_exception_without_verifier():
    executor = FakeToolExecutor(
        {
            "gh_set_value": RuntimeError("transport down"),
            "gh_solve": {"success": True, "data": {"scheduled": True}},
            "gh_inspect_output": {"success": True, "data": {"preview": ["7.5"]}},
        }
    )

    result = _run(
        PROBE._dispatch_set_value_solve_and_verify(
            tool_executor=executor,
            editable_component_guid="EDITABLE-GUID-1",
            addition_component_guid="ADDITION-GUID-1",
            worker_value=6.0,
            expected_value=7.5,
        )
    )

    assert result["decision"]["decision"] == "rejected"
    assert result["decision"]["reason"].startswith("gh_set_value_exception:")
    assert result["verify_scalar_output_summary"] is None
    assert executor.calls == [
        ("gh_set_value", {"guid": "EDITABLE-GUID-1", "value": 6.0})
    ]


def test_dispatch_set_value_solve_and_verify_rejects_invalid_inspected_value():
    executor = FakeToolExecutor(
        {
            "gh_set_value": {
                "success": True,
                "data": {"Guid": "EDITABLE-GUID-1", "NewValue": 6.0},
            },
            "gh_solve": {"success": True, "data": {"scheduled": True}},
            "gh_inspect_output": {
                "success": True,
                "data": {"data_count": 1, "preview": ["not-number"]},
            },
        }
    )

    result = _run(
        PROBE._dispatch_set_value_solve_and_verify(
            tool_executor=executor,
            editable_component_guid="EDITABLE-GUID-1",
            addition_component_guid="ADDITION-GUID-1",
            worker_value=6.0,
            expected_value=7.5,
        )
    )

    assert result["decision"]["decision"] == "rejected"
    assert result["decision"]["reason"] == "verify_scalar_output_invalid_value"
    assert result["verify_scalar_output_summary"]["reported_success"] is True
    assert result["verify_scalar_output_summary"]["attempt_count"] == 3
    assert result["verify_scalar_output_summary"]["attempts"][0]["failure_reason"] == (
        "inspect_output_scalar_value_invalid"
    )


def test_dispatch_set_value_solve_and_verify_accepts_invalid_first_valid_second():
    executor = FakeToolExecutor(
        {
            "gh_set_value": {
                "success": True,
                "data": {"Guid": "EDITABLE-GUID-1", "NewValue": 6.0},
            },
            "gh_solve": {"success": True, "data": {"scheduled": True}},
            "gh_inspect_output": [
                {
                    "success": True,
                    "data": {"data_count": 1, "preview": ["not-ready"]},
                },
                {
                    "success": True,
                    "data": {"data_count": 1, "preview": ["7.5"]},
                },
            ],
        }
    )

    result = _run(
        PROBE._dispatch_set_value_solve_and_verify(
            tool_executor=executor,
            editable_component_guid="EDITABLE-GUID-1",
            addition_component_guid="ADDITION-GUID-1",
            worker_value=6.0,
            expected_value=7.5,
        )
    )

    assert result["decision"]["decision"] == "accepted"
    assert result["decision"]["reason"] == "verify_scalar_output_succeeded"
    verify = result["verify_scalar_output_summary"]
    assert verify["observed_output_value"] == 7.5
    assert verify["attempt_count"] == 2
    assert verify["attempts"][0]["attempt_index"] == 1
    assert verify["attempts"][0]["reported_success"] is True
    assert verify["attempts"][0]["observed_output_value"] is None
    assert verify["attempts"][0]["failure_reason"] == "inspect_output_scalar_value_invalid"
    assert verify["attempts"][0]["result_shape"]["data"]["keys"] == [
        "data_count",
        "preview",
    ]
    assert verify["attempts"][0]["result_sha256"].startswith("sha256:")
    assert "not-ready" in verify["attempts"][0]["result_excerpt"]
    assert verify["attempts"][1]["attempt_index"] == 2
    assert verify["attempts"][1]["observed_output_value"] == 7.5
    assert "EDITABLE-GUID-1" not in json.dumps(verify, sort_keys=True)
    assert "ADDITION-GUID-1" not in json.dumps(verify, sort_keys=True)


def test_dispatch_set_value_solve_and_verify_rejects_inspect_exception_without_crashing():
    executor = FakeToolExecutor(
        {
            "gh_set_value": {
                "success": True,
                "data": {"Guid": "EDITABLE-GUID-1", "NewValue": 6.0},
            },
            "gh_solve": {"success": True, "data": {"scheduled": True}},
            "gh_inspect_output": RuntimeError("verifier transport down"),
        }
    )

    result = _run(
        PROBE._dispatch_set_value_solve_and_verify(
            tool_executor=executor,
            editable_component_guid="EDITABLE-GUID-1",
            addition_component_guid="ADDITION-GUID-1",
            worker_value=6.0,
            expected_value=7.5,
        )
    )

    assert result["decision"]["decision"] == "rejected"
    assert result["decision"]["reason"] == "gh_inspect_output_exception:RuntimeError"
    assert result["verify_scalar_output_summary"]["exception"] == "RuntimeError"
    assert result["verify_scalar_output_summary"]["observed_output_value"] is None
    assert result["verify_scalar_output_summary"]["attempt_count"] == 3
    assert executor.calls == [
        ("gh_set_value", {"guid": "EDITABLE-GUID-1", "value": 6.0}),
        ("gh_solve", {"delay": 25}),
        ("gh_inspect_output", {"guid": "ADDITION-GUID-1", "param": "R"}),
        ("gh_inspect_output", {"guid": "ADDITION-GUID-1", "param": "R"}),
        ("gh_inspect_output", {"guid": "ADDITION-GUID-1", "param": "R"}),
    ]


def test_dispatch_set_value_solve_and_verify_rejects_failed_inspect_without_invalid_value_misclassifying():
    executor = FakeToolExecutor(
        {
            "gh_set_value": {
                "success": True,
                "data": {"Guid": "EDITABLE-GUID-1", "NewValue": 6.0},
            },
            "gh_solve": {"success": True, "data": {"scheduled": True}},
            "gh_inspect_output": {
                "success": False,
                "data": "Object not found",
            },
        }
    )

    result = _run(
        PROBE._dispatch_set_value_solve_and_verify(
            tool_executor=executor,
            editable_component_guid="EDITABLE-GUID-1",
            addition_component_guid="ADDITION-GUID-1",
            worker_value=6.0,
            expected_value=7.5,
        )
    )

    assert result["decision"]["decision"] == "rejected"
    assert result["decision"]["reason"] == "verify_scalar_output_failed"
    assert result["decision"]["reason"] != "verify_scalar_output_invalid_value"
    assert result["verify_scalar_output_summary"]["reported_success"] is False
    assert result["verify_scalar_output_summary"]["observed_output_value"] is None
    assert result["verify_scalar_output_summary"]["attempt_count"] == 3
    assert result["verify_scalar_output_summary"]["attempts"][-1]["failure_reason"] == (
        "gh_inspect_output_failed"
    )


def _published_action(value=6.0):
    return FakePublication(
        row={
            "status": "published",
            "pass2_response_kind": "action_request",
            "observation_action_intent_anomaly": False,
        },
        response_payload={
            "schema": "rook.local_worker_turn_response:v1",
            "kind": "action_request",
            "action_id": "draft_gh_set_value_params",
            "rationale": "Use the offset relationship to match the expected output.",
            "input": {"value": value},
        },
    )


def _fixture_responses_for_success():
    return {
        "rhino_ping": "pong",
        "gh_document_new": {"success": True, "data": {"Created": True}},
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
            {"success": True, "data": {"Created": True, "Guid": "EDITABLE-GUID-1"}},
            {"success": True, "data": {"Created": True, "Guid": "OFFSET-GUID-1"}},
        ],
        "gh_create_component": {
            "success": True,
            "data": {"Created": True, "Guid": "ADDITION-GUID-1"},
        },
        "gh_connect": [
            {"success": True, "data": {"connected": True}},
            {"success": True, "data": {"connected": True}},
        ],
        "gh_solve": [
            {"success": True, "data": {"scheduled": True}},
            {"success": True, "data": {"scheduled": True}},
        ],
        "gh_get_value": {"success": True, "data": {"Value": "2.0"}},
        "gh_inspect_output": [
            {"success": True, "data": {"data_count": 1, "preview": ["3.5"]}},
            {"success": True, "data": {"data_count": 1, "preview": ["7.5"]}},
        ],
        "gh_set_value": {"success": True, "data": {"Guid": "EDITABLE-GUID-1"}},
    }


def test_run_probe_accepts_worker_value_that_matches_transform_output(tmp_path):
    executor = FakeToolExecutor(_fixture_responses_for_success())

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *args, **kwargs: _published_action(6.0),
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    request = json.loads((run_dir / "worker_request_payload.json").read_text(encoding="utf-8"))
    worker_action = json.loads((run_dir / "worker_action.json").read_text(encoding="utf-8"))
    verify = json.loads((run_dir / "verify_scalar_output_summary.json").read_text(encoding="utf-8"))

    assert decision["decision"] == "accepted"
    assert decision["reason"] == "verify_scalar_output_succeeded"
    assert decision["scalar_runtime_ready"] is True
    assert decision["worker_publication_ran"] is True
    assert decision["live_set_value_dispatched"] is True
    assert decision["verify_scalar_output_ran"] is True
    assert worker_action["input"] == {"value": 6.0}
    assert verify["observed_output_value"] == 7.5
    rendered_request = json.dumps(request, sort_keys=True)
    assert "6.0" not in rendered_request
    assert "EDITABLE-GUID-1" not in rendered_request
    assert "ADDITION-GUID-1" not in rendered_request
    rendered_decision = json.dumps(decision, sort_keys=True)
    assert "EDITABLE-GUID-1" not in rendered_decision
    assert "ADDITION-GUID-1" not in rendered_decision


def test_run_probe_artifacts_keep_raw_guid_out_of_source_request_decision_and_verifier(
    tmp_path,
):
    executor = FakeToolExecutor(_fixture_responses_for_success())

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *args, **kwargs: _published_action(6.0),
    )

    forbidden_guid_files = [
        "scalar_sources.json",
        "acceptance_criteria_packet.json",
        "worker_visible_acceptance_criteria.json",
        "worker_request_payload.json",
        "verify_scalar_output_summary.json",
        "decision.json",
    ]
    for filename in forbidden_guid_files:
        rendered = (run_dir / filename).read_text(encoding="utf-8")
        assert "EDITABLE-GUID-1" not in rendered
        assert "OFFSET-GUID-1" not in rendered
        assert "ADDITION-GUID-1" not in rendered

    assert "EDITABLE-GUID-1" in (
        run_dir / "fixture_setup_summary.json"
    ).read_text(encoding="utf-8")
    assert "EDITABLE-GUID-1" in (
        run_dir / "live_set_value_summary.json"
    ).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("responses", "expected_reason", "expected_step", "expected_tool"),
    [
        (
            {
                **_fixture_responses_for_success(),
                "gh_library": {"success": False, "data": "library offline"},
            },
            "transform_fixture_failed:gh_library_failed",
            "gh_library",
            "gh_library",
        ),
        (
            {
                **_fixture_responses_for_success(),
                "gh_create_slider": [
                    {"success": False, "data": "slider failed"},
                ],
            },
            "transform_fixture_failed:gh_create_editable_slider_failed",
            "gh_create_editable_slider",
            "gh_create_slider",
        ),
        (
            {
                **_fixture_responses_for_success(),
                "gh_create_component": {
                    "success": True,
                    "data": {"Created": True},
                },
            },
            "transform_fixture_failed:tool_result_guid_missing",
            "gh_create_addition",
            "gh_create_component",
        ),
        (
            {
                **_fixture_responses_for_success(),
                "gh_connect": [
                    {"success": False, "data": "connect failed"},
                ],
            },
            "transform_fixture_failed:gh_connect_editable_failed",
            "gh_connect_editable",
            "gh_connect",
        ),
        (
            {
                **_fixture_responses_for_success(),
                "gh_get_value": {"success": False, "data": "value unavailable"},
            },
            "transform_fixture_failed:gh_get_value_failed",
            "gh_get_value",
            "gh_get_value",
        ),
        (
            {
                **_fixture_responses_for_success(),
                "gh_inspect_output": [
                    {"success": False, "data": "inspect failed"},
                ],
            },
            "transform_fixture_failed:inspect_output_scalar_result_failed",
            "gh_inspect_output",
            "gh_inspect_output",
        ),
    ],
)
def test_run_probe_writes_bounded_fixture_failure_summary_for_setup_failures(
    tmp_path, responses, expected_reason, expected_step, expected_tool
):
    executor = FakeToolExecutor(responses)

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=120,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *args, **kwargs: pytest.fail(
            "worker publication must not run after fixture setup failure"
        ),
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    failure = json.loads(
        (run_dir / "fixture_failure_summary.json").read_text(encoding="utf-8")
    )

    assert decision["decision"] == "gate_failed"
    assert decision["reason"] == expected_reason
    assert decision["phase"] == "live_fixture"
    assert decision["live_fixture_created"] is False
    assert decision["worker_publication_ran"] is False
    assert decision["live_set_value_dispatched"] is False
    assert decision["verify_scalar_output_ran"] is False
    assert not (run_dir / "worker_publication_row.json").exists()
    assert not (run_dir / "live_set_value_summary.json").exists()
    assert not (run_dir / "verify_scalar_output_summary.json").exists()

    assert failure["step"] == expected_step
    assert failure["tool_name"] == expected_tool
    assert failure["failure_reason"] == expected_reason.removeprefix(
        "transform_fixture_failed:"
    )
    assert failure["result_sha256"].startswith("sha256:")
    assert len(failure["result_excerpt"]) <= 120
    assert "result_shape" in failure
    rendered_failure = json.dumps(failure, sort_keys=True)
    assert "EDITABLE-GUID-1" not in rendered_failure
    assert "OFFSET-GUID-1" not in rendered_failure
    assert "ADDITION-GUID-1" not in rendered_failure
