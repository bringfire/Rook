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
        / "lm8c_gh_scalar_expectation_live_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm8c_gh_scalar_expectation_live_probe",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()


def test_cli_defaults_are_canonical_worker_shape() -> None:
    args = PROBE._args([])

    assert args.model == "gemma4:12b-it-qat"
    assert args.endpoint == "http://localhost:11434/api/chat"
    assert args.temperature == 0
    assert args.timeout_s == 120
    assert args.excerpt_chars == 1200
    assert args.run_dir == "probe_runs"
    assert args.canonical_evidence is True


def test_cli_overrides_are_exploratory_unless_explicitly_marked_canonical() -> None:
    args = PROBE._args(["--model", "qwen3:14b"])
    assert args.canonical_evidence is False


def test_cli_rejects_non_lm8c_surfaces() -> None:
    forbidden = [
        ["--phase", "receipt_recon"],
        ["--attempts", "5"],
        ["--retry-clean-observation"],
        ["--planner-provider-command", "x"],
        ["--prompt-profile", "shape_guidance_v2"],
        ["--request-json", "request.json"],
    ]
    for argv in forbidden:
        with pytest.raises(SystemExit):
            PROBE._args(argv)


def test_canonical_evidence_requires_default_shape() -> None:
    args = PROBE._args(["--canonical-evidence"])
    assert PROBE._canonical_evidence_is_valid(args) is True

    for argv in (
        ["--canonical-evidence", "--model", "qwen3:14b"],
        ["--canonical-evidence", "--endpoint", "http://example.invalid/chat"],
        ["--canonical-evidence", "--temperature", "0.2"],
    ):
        assert PROBE._canonical_evidence_is_valid(PROBE._args(argv)) is False


def test_decision_record_hashes_guid_without_raw_guid() -> None:
    decision = PROBE._decision_record(
        decision="accepted",
        reason="verify_scalar_output_succeeded",
        phase="verify_scalar_output",
        canonical_evidence=True,
        scalar_runtime_ready=True,
        live_fixture_created=True,
        worker_publication_ran=True,
        live_set_value_dispatched=True,
        verify_scalar_output_ran=True,
        component_guid="GUID-SECRET",
        extra={"observed_output_after": 7.5},
    )

    rendered = json.dumps(decision, sort_keys=True)
    assert decision["component_guid_sha256"].startswith("sha256:")
    assert decision["guid_present"] is True
    assert "GUID-SECRET" not in rendered
    assert decision["decision"] == "accepted"


def test_run_probe_callable_accepts_task_4_dependencies() -> None:
    signature = inspect.signature(PROBE._run_probe)

    assert list(signature.parameters) == [
        "model",
        "endpoint",
        "temperature",
        "timeout_s",
        "excerpt_chars",
        "run_root",
        "canonical_evidence",
        "tool_executor",
        "publication_runner",
    ]


@pytest.mark.parametrize(
    "extra",
    [
        {"component_guid": "GUID-SECRET"},
        {"sourceGuid": "GUID-SECRET"},
    ],
)
def test_decision_record_rejects_guid_bearing_extra_keys(extra) -> None:
    with pytest.raises(ValueError, match="LM8C decision extra"):
        PROBE._decision_record(
            decision="accepted",
            reason="verify_scalar_output_succeeded",
            phase="verify_scalar_output",
            canonical_evidence=True,
            component_guid="GUID-SECRET",
            extra=extra,
        )


def test_decision_record_rejects_extra_that_overwrites_base_field() -> None:
    with pytest.raises(ValueError, match="LM8C decision extra"):
        PROBE._decision_record(
            decision="accepted",
            reason="verify_scalar_output_succeeded",
            phase="verify_scalar_output",
            canonical_evidence=True,
            extra={"decision": "rejected"},
        )


@pytest.mark.parametrize(
    "extra",
    [
        {"note": "SLIDER-GUID-SECRET"},
        {"meta": {"component_guid": "SLIDER-GUID-SECRET"}},
        {"ids": ["550e8400-e29b-41d4-a716-446655440000"]},
    ],
)
def test_decision_record_rejects_guid_like_extra_values(extra) -> None:
    with pytest.raises(ValueError, match="LM8C decision extra"):
        PROBE._decision_record(
            decision="accepted",
            reason="verify_scalar_output_succeeded",
            phase="verify_scalar_output",
            canonical_evidence=True,
            component_guid="GUID-SECRET",
            extra=extra,
        )


def test_decision_record_allows_safe_scalar_and_excerpt_extra_values() -> None:
    decision = PROBE._decision_record(
        decision="accepted",
        reason="verify_scalar_output_succeeded",
        phase="verify_scalar_output",
        canonical_evidence=True,
        component_guid="GUID-SECRET",
        extra={
            "observed_output_after": 7.5,
            "worker_action_input_excerpt": "{\"value\": 7.5}",
        },
    )

    assert decision["observed_output_after"] == 7.5
    assert decision["worker_action_input_excerpt"] == "{\"value\": 7.5}"


def test_manifest_records_lm8c_identity() -> None:
    manifest = PROBE._manifest(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        canonical_evidence=True,
    )

    assert manifest["schema"] == "rook.lm8c_gh_scalar_expectation_live_probe:v1"
    assert manifest["attempts"] == 1
    assert manifest["expected_output_value"] == 7.5
    assert manifest["initial_scalar_value"] == 0.0
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


def test_preflight_accepts_pong_and_document_created() -> None:
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


def test_preflight_classifies_ping_and_document_failures() -> None:
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


def test_create_scalar_fixture_uses_direct_slider_tools_and_hashes_guid() -> None:
    executor = FakeToolExecutor(
        {
            "gh_create_slider": {
                "success": True,
                "data": {
                    "Created": True,
                    "Guid": "SLIDER-GUID-1",
                    "NickName": "LM8C_Target",
                },
            },
            "gh_get_value": {
                "success": True,
                "data": {
                    "Guid": "SLIDER-GUID-1",
                    "Value": "0.0",
                },
            },
        }
    )

    fixture = _run(PROBE._create_scalar_fixture(executor))

    assert executor.calls == [
        (
            "gh_create_slider",
            {
                "nickname": "LM8C_Target",
                "min": 0,
                "max": 10,
                "value": 0.0,
                "x": 20,
                "y": 80,
            },
        ),
        ("gh_get_value", {"guid": "SLIDER-GUID-1"}),
    ]
    assert fixture["component_guid"] == "SLIDER-GUID-1"
    assert fixture["observed_output_value"] == 0.0
    assert (
        fixture["receipt"]["scalar_anchor"]["internal_component_guid"]
        == "SLIDER-GUID-1"
    )
    assert "component_guid" not in fixture["receipt"]["scalar_anchor"][
        "editable_value_contract"
    ]
    rendered_sources = json.dumps(fixture["visible_receipt"], sort_keys=True)
    assert "SLIDER-GUID-1" not in rendered_sources
    assert fixture["live_create_scalar_summary"]["component_guid"] == "SLIDER-GUID-1"
    assert fixture["live_create_scalar_summary"]["component_guid_sha256"].startswith(
        "sha256:"
    )


def test_guid_from_result_prefers_top_level_field_in_mixed_envelope() -> None:
    result = {"success": True, "guid": "TOP", "data": {"Guid": "NESTED"}}

    assert PROBE._guid_from_result(result) == "TOP"


def test_tool_field_prefers_top_level_value_in_mixed_envelope() -> None:
    result = {"success": True, "value": "TOP", "data": {"Value": "NESTED"}}

    assert PROBE._tool_field(result, "value", "Value") == "TOP"


def test_create_scalar_fixture_rejects_nested_created_false_even_with_guid() -> None:
    executor = FakeToolExecutor(
        {
            "gh_create_slider": {
                "success": True,
                "data": {"Created": False, "Guid": "SLIDER-GUID-1"},
            },
            "gh_get_value": {
                "success": True,
                "data": {"Guid": "SLIDER-GUID-1", "Value": 0},
            },
        }
    )

    with pytest.raises(ValueError, match="gh_create_slider_failed"):
        _run(PROBE._create_scalar_fixture(executor))

    assert executor.calls == [
        (
            "gh_create_slider",
            {
                "nickname": "LM8C_Target",
                "min": 0,
                "max": 10,
                "value": 0.0,
                "x": 20,
                "y": 80,
            },
        )
    ]


def test_fixture_receipt_raw_guid_is_internal_only() -> None:
    executor = FakeToolExecutor(
        {
            "gh_create_slider": {
                "success": True,
                "data": {
                    "Created": True,
                    "Guid": "INTERNAL-SLIDER-GUID",
                },
            },
            "gh_get_value": {
                "success": True,
                "data": {
                    "Guid": "INTERNAL-SLIDER-GUID",
                    "Value": 0,
                },
            },
        }
    )

    fixture = _run(PROBE._create_scalar_fixture(executor))

    internal_anchor = fixture["receipt"]["scalar_anchor"]
    visible_anchor = fixture["visible_receipt"]["scalar_anchor"]
    assert internal_anchor["internal_component_guid"] == "INTERNAL-SLIDER-GUID"
    assert "component_guid" not in internal_anchor
    assert "internal_component_guid" not in visible_anchor
    assert "component_guid" not in visible_anchor
    assert visible_anchor["guid_present"] is True
    assert visible_anchor["component_guid_sha256"].startswith("sha256:")
    assert "INTERNAL-SLIDER-GUID" not in json.dumps(
        fixture["visible_receipt"], sort_keys=True
    )


def test_create_scalar_fixture_accepts_top_level_lowercase_tool_fields() -> None:
    executor = FakeToolExecutor(
        {
            "gh_create_slider": {
                "success": True,
                "created": True,
                "guid": "SLIDER-GUID-2",
            },
            "gh_get_value": {
                "success": True,
                "guid": "SLIDER-GUID-2",
                "value": 0,
            },
        }
    )

    fixture = _run(PROBE._create_scalar_fixture(executor))

    assert fixture["component_guid"] == "SLIDER-GUID-2"
    assert fixture["observed_output_value"] == 0
    assert fixture["live_create_scalar_summary"]["created"] is True


@pytest.mark.parametrize("bad_value", ["not-number", True, None])
def test_create_scalar_fixture_rejects_bad_initial_get_value(bad_value) -> None:
    executor = FakeToolExecutor(
        {
            "gh_create_slider": {
                "success": True,
                "data": {"Created": True, "Guid": "SLIDER-GUID-1"},
            },
            "gh_get_value": {
                "success": True,
                "data": {"Guid": "SLIDER-GUID-1", "Value": bad_value},
            },
        }
    )

    with pytest.raises(ValueError, match="live scalar value"):
        _run(PROBE._create_scalar_fixture(executor))


def _valid_fixture():
    return {
        "component_guid": "SLIDER-GUID-1",
        "observed_output_value": 0.0,
        "receipt": {
            "observed_output_value": 0.0,
            "scalar_anchor": {
                "component_guid": "SLIDER-GUID-1",
                "editable_value_contract": {
                    "label": "LM8C_Target",
                    "value_type": "number",
                    "current_value": 0.0,
                    "identity_projection": True,
                },
            },
        },
        "visible_receipt": {},
        "live_create_scalar_summary": {},
    }


def test_scalar_runtime_context_static_validates_without_lm5x_routability() -> None:
    graph = PROBE._graph_from_scalar_receipt(_valid_fixture()["receipt"])
    context = PROBE._scalar_runtime_context(
        graph=graph,
        workflow_contract_payload=PROBE._scalar_contract_payload(),
        convention_packets=(),
    )

    routing_report = context["static_routing_report"]
    assert routing_report["valid"] is True
    assert routing_report["routability_evaluated"] is False
    assert context["scalar_runtime_ready"] is True
    assert context["sources"].expected_output_contract.value == 7.5
    assert context["sources"].receipt_observation.value == 0.0
    assert context["packet"]["fields"]["expected_output_value"] == 7.5
    assert context["worker_visible"]["source"] == "gh_scalar_expectation"


def test_scalar_runtime_context_fails_when_live_receipt_missing_observation() -> None:
    receipt = _valid_fixture()["receipt"]
    receipt.pop("observed_output_value")
    graph = PROBE._graph_from_scalar_receipt(receipt)

    with pytest.raises(ValueError, match="observed_output_value"):
        PROBE._scalar_runtime_context(
            graph=graph,
            workflow_contract_payload=PROBE._scalar_contract_payload(),
            convention_packets=(),
        )


def test_worker_request_uses_scalar_knowledge_and_never_exposes_raw_guid() -> None:
    fixture = _valid_fixture()
    graph = PROBE._graph_from_scalar_receipt(fixture["receipt"])
    runtime = PROBE._scalar_runtime_context(
        graph=graph,
        workflow_contract_payload=PROBE._scalar_contract_payload(),
        convention_packets=(),
    )

    payload = PROBE._build_local_turn_payload(
        graph=graph,
        packet=runtime["packet"],
        worker_visible=runtime["worker_visible"],
    )

    rendered = json.dumps(payload, sort_keys=True)
    assert payload["schema"] == "rook.local_worker_turn_request:v1"
    assert "gh_scalar_expectation_evidence" in rendered
    assert "draft_gh_set_value_params" in rendered
    assert '"value"' in rendered
    assert "SLIDER-GUID-1" not in rendered
    assert "gh_edit" not in rendered
    assert "gh_update_script" not in rendered
    assert "repair_same_component" not in rendered


class FakePublication:
    def __init__(self, row, response_payload=None):
        self.row = row
        self.response_payload = response_payload


def test_publication_non_action_maps_to_worker_declined() -> None:
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


def test_publication_failure_maps_to_publication_failed() -> None:
    decision = PROBE._decision_from_publication(
        {"status": "pass2_lm5g_invalid", "failure_reason": "bad-json"},
        None,
    )

    assert decision["decision"] == "publication_failed"
    assert decision["reason"] == "pass2_lm5g_invalid:bad-json"


def test_dispatch_set_value_and_verify_accepts_live_observed_match() -> None:
    executor = FakeToolExecutor(
        {
            "gh_set_value": {
                "success": True,
                "data": {"Guid": "SLIDER-GUID-1", "NewValue": 7.5},
            },
            "gh_get_value": {
                "success": True,
                "data": {"Guid": "SLIDER-GUID-1", "Value": "7.5"},
            },
        }
    )

    result = _run(
        PROBE._dispatch_set_value_and_verify(
            tool_executor=executor,
            component_guid="SLIDER-GUID-1",
            worker_value=7.5,
            expected_value=7.5,
        )
    )

    assert result["decision"]["decision"] == "accepted"
    assert result["decision"]["reason"] == "verify_scalar_output_succeeded"
    assert result["live_set_value_summary"]["component_guid"] == "SLIDER-GUID-1"
    assert result["verify_scalar_output_summary"]["component_guid_sha256"].startswith(
        "sha256:"
    )
    assert "component_guid" not in result["verify_scalar_output_summary"]


def test_dispatch_set_value_and_verify_rejects_live_observed_mismatch() -> None:
    executor = FakeToolExecutor(
        {
            "gh_set_value": {
                "success": True,
                "data": {"Guid": "SLIDER-GUID-1", "NewValue": 0.0},
            },
            "gh_get_value": {
                "success": True,
                "data": {"Guid": "SLIDER-GUID-1", "Value": "0.0"},
            },
        }
    )

    result = _run(
        PROBE._dispatch_set_value_and_verify(
            tool_executor=executor,
            component_guid="SLIDER-GUID-1",
            worker_value=7.5,
            expected_value=7.5,
        )
    )

    assert result["decision"]["decision"] == "rejected"
    assert result["decision"]["reason"] == "verify_scalar_output_failed"


def test_dispatch_set_value_and_verify_receipts_invalid_final_value() -> None:
    executor = FakeToolExecutor(
        {
            "gh_set_value": {
                "success": True,
                "data": {"Guid": "SLIDER-GUID-1", "NewValue": 7.5},
            },
            "gh_get_value": {
                "success": True,
                "data": {"Guid": "SLIDER-GUID-1", "Value": "not-number"},
            },
        }
    )

    result = _run(
        PROBE._dispatch_set_value_and_verify(
            tool_executor=executor,
            component_guid="SLIDER-GUID-1",
            worker_value=7.5,
            expected_value=7.5,
        )
    )

    assert result["decision"]["decision"] == "rejected"
    assert result["decision"]["reason"] == "verify_scalar_output_invalid_value"
    assert result["verify_scalar_output_summary"]["matched"] is False


def test_run_probe_happy_path_writes_bounded_artifacts(tmp_path: Path) -> None:
    executor = FakeToolExecutor(
        {
            "rhino_ping": "pong",
            "gh_document_new": {"success": True, "data": {"Created": True}},
            "gh_create_slider": {
                "success": True,
                "data": {"Created": True, "Guid": "SLIDER-GUID-1"},
            },
            "gh_get_value": [
                {"success": True, "data": {"Guid": "SLIDER-GUID-1", "Value": "0.0"}},
                {"success": True, "data": {"Guid": "SLIDER-GUID-1", "Value": "7.5"}},
            ],
            "gh_set_value": {
                "success": True,
                "data": {"Guid": "SLIDER-GUID-1", "NewValue": 7.5},
            },
        }
    )

    def fake_publication_runner(*_args, **_kwargs):
        return FakePublication(
            row={"status": "published", "pass2_response_kind": "action_request"},
            response_payload={
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_gh_set_value_params",
                "rationale": "Set to the expected scalar value.",
                "input": {"value": 7.5},
            },
        )

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=fake_publication_runner,
    )

    decision = json.loads((run_dir / "decision.json").read_text())
    worker_payload = (run_dir / "worker_request_payload.json").read_text()
    verify_summary = json.loads(
        (run_dir / "verify_scalar_output_summary.json").read_text()
    )

    assert decision["decision"] == "accepted"
    assert decision["reason"] == "verify_scalar_output_succeeded"
    assert decision["scalar_runtime_ready"] is True
    assert decision["live_fixture_created"] is True
    assert decision["worker_publication_ran"] is True
    assert decision["live_set_value_dispatched"] is True
    assert decision["verify_scalar_output_ran"] is True
    assert "SLIDER-GUID-1" not in worker_payload
    assert "component_guid" not in verify_summary
    assert verify_summary["matched"] is True


def _run_probe_with_publication(tmp_path: Path, publication: FakePublication) -> Path:
    executor = FakeToolExecutor(
        {
            "rhino_ping": "pong",
            "gh_document_new": {"success": True, "data": {"Created": True}},
            "gh_create_slider": {
                "success": True,
                "data": {"Created": True, "Guid": "SLIDER-GUID-SECRET"},
            },
            "gh_get_value": [
                {
                    "success": True,
                    "data": {"Guid": "SLIDER-GUID-SECRET", "Value": "0.0"},
                },
                {
                    "success": True,
                    "data": {"Guid": "SLIDER-GUID-SECRET", "Value": "7.5"},
                },
            ],
            "gh_set_value": {
                "success": True,
                "data": {"Guid": "SLIDER-GUID-SECRET", "NewValue": 7.5},
            },
        }
    )

    return PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *_args, **_kwargs: publication,
    )


def test_run_probe_blocks_publication_row_raw_guid_leak(tmp_path: Path) -> None:
    run_dir = _run_probe_with_publication(
        tmp_path,
        FakePublication(
            row={
                "status": "published",
                "pass2_response_kind": "action_request",
                "note": "SLIDER-GUID-SECRET",
            },
            response_payload={
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_gh_set_value_params",
                "input": {"value": 7.5},
            },
        ),
    )

    decision = json.loads((run_dir / "decision.json").read_text())
    rendered = json.dumps(decision, sort_keys=True)

    assert decision["decision"] == "publication_failed"
    assert decision["reason"] == "worker_publication_guid_leak"
    assert decision["phase"] == "worker_publication"
    assert decision["worker_publication_ran"] is True
    assert decision["guid_present"] is True
    assert decision["component_guid_sha256"].startswith("sha256:")
    assert "SLIDER-GUID-SECRET" not in rendered
    assert not (run_dir / "worker_publication_row.json").exists()
    assert not (run_dir / "worker_action.json").exists()


def test_run_probe_blocks_publication_row_raw_guid_leak_with_different_casing(
    tmp_path: Path,
) -> None:
    run_dir = _run_probe_with_publication(
        tmp_path,
        FakePublication(
            row={
                "status": "published",
                "pass2_response_kind": "action_request",
                "note": "slider-guid-secret",
            },
            response_payload={
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_gh_set_value_params",
                "input": {"value": 7.5},
            },
        ),
    )

    decision = json.loads((run_dir / "decision.json").read_text())

    assert decision["decision"] == "publication_failed"
    assert decision["reason"] == "worker_publication_guid_leak"
    assert decision["phase"] == "worker_publication"
    assert not (run_dir / "worker_publication_row.json").exists()
    assert not (run_dir / "worker_action.json").exists()


def test_run_probe_blocks_worker_action_raw_guid_leak(tmp_path: Path) -> None:
    run_dir = _run_probe_with_publication(
        tmp_path,
        FakePublication(
            row={"status": "published", "pass2_response_kind": "action_request"},
            response_payload={
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_gh_set_value_params",
                "input": {"value": 7.5, "note": "SLIDER-GUID-SECRET"},
            },
        ),
    )

    decision = json.loads((run_dir / "decision.json").read_text())
    rendered = json.dumps(decision, sort_keys=True)

    assert decision["decision"] == "publication_failed"
    assert decision["reason"] == "worker_publication_guid_leak"
    assert decision["phase"] == "worker_publication"
    assert decision["worker_publication_ran"] is True
    assert decision["guid_present"] is True
    assert decision["component_guid_sha256"].startswith("sha256:")
    assert "SLIDER-GUID-SECRET" not in rendered
    assert not (run_dir / "worker_publication_row.json").exists()
    assert not (run_dir / "worker_action.json").exists()


def test_run_probe_blocks_worker_action_raw_guid_leak_with_different_casing(
    tmp_path: Path,
) -> None:
    run_dir = _run_probe_with_publication(
        tmp_path,
        FakePublication(
            row={"status": "published", "pass2_response_kind": "action_request"},
            response_payload={
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_gh_set_value_params",
                "input": {"value": 7.5, "note": "slider-guid-secret"},
            },
        ),
    )

    decision = json.loads((run_dir / "decision.json").read_text())

    assert decision["decision"] == "publication_failed"
    assert decision["reason"] == "worker_publication_guid_leak"
    assert decision["phase"] == "worker_publication"
    assert not (run_dir / "worker_publication_row.json").exists()
    assert not (run_dir / "worker_action.json").exists()


def test_run_probe_rejects_malformed_action_without_decision_guid_excerpt(
    tmp_path: Path,
) -> None:
    run_dir = _run_probe_with_publication(
        tmp_path,
        FakePublication(
            row={"status": "published", "pass2_response_kind": "action_request"},
            response_payload={
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_gh_set_value_params",
                "input": {"value": 7.5, "guid": "FAKE-NOT-TRUSTED"},
            },
        ),
    )

    decision = json.loads((run_dir / "decision.json").read_text())
    rendered = json.dumps(decision, sort_keys=True)

    assert decision["decision"] == "rejected"
    assert decision["reason"].startswith("worker_action_apply_failed:")
    assert decision["phase"] == "worker_action_apply"
    assert "FAKE-NOT-TRUSTED" not in rendered
    assert "guid" not in decision["worker_action_input_excerpt"].casefold()
    assert (run_dir / "worker_action.json").exists()


def test_run_probe_preflight_failure_writes_terminal_decision(tmp_path: Path) -> None:
    executor = FakeToolExecutor({"rhino_ping": {"success": False, "error": "offline"}})

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *_args, **_kwargs: pytest.fail("worker called"),
    )

    decision = json.loads((run_dir / "decision.json").read_text())
    assert decision["decision"] == "preflight_failed"
    assert decision["reason"] == "rhino_ping_failed"
    assert decision["worker_publication_ran"] is False


def test_script_static_guard_forbids_repair_and_batch_surfaces() -> None:
    import ast

    source = _script_path().read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_import_fragments = [
        "lm6a_live_worker_splice_probe",
        "lm7b_request_driven_live_splice_probe",
        "lm7e_model_authored_live_splice_probe",
        "planner_worker_contract_request",
    ]
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for marker in forbidden_import_fragments:
                assert marker not in node.module
        if isinstance(node, ast.Import):
            for alias in node.names:
                for marker in forbidden_import_fragments:
                    assert marker not in alias.name

    dispatched_tools = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        first_arg = node.args[0]
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            dispatched_tools.append(first_arg.value)

    forbidden_dispatched_tools = [
        "gh_edit",
        "gh_update_script",
        "gh_create_csharp_script",
    ]
    for marker in forbidden_dispatched_tools:
        assert marker not in dispatched_tools

    forbidden_call_names = [
        "_worker_request_payload",
        "materialize_planner_worker_contract_request",
        "validate_planner_worker_contract_request",
        "retry_clean_observation",
        "lm6e_bounded_retry_context",
    ]
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = ""
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            for marker in forbidden_call_names:
                assert marker not in name

    assert "repair_same_component" not in dispatched_tools


def test_source_and_worker_artifacts_do_not_contain_raw_guid(tmp_path: Path) -> None:
    executor = FakeToolExecutor(
        {
            "rhino_ping": "pong",
            "gh_document_new": {"success": True, "data": {"Created": True}},
            "gh_create_slider": {
                "success": True,
                "data": {"Created": True, "Guid": "SLIDER-GUID-SECRET"},
            },
            "gh_get_value": [
                {
                    "success": True,
                    "data": {"Guid": "SLIDER-GUID-SECRET", "Value": "0.0"},
                },
                {
                    "success": True,
                    "data": {"Guid": "SLIDER-GUID-SECRET", "Value": "7.5"},
                },
            ],
            "gh_set_value": {
                "success": True,
                "data": {"Guid": "SLIDER-GUID-SECRET", "NewValue": 7.5},
            },
        }
    )

    async def sequence_executor(tool_name, args):
        value = executor.responses[tool_name]
        executor.calls.append((tool_name, dict(args)))
        if isinstance(value, list):
            return value.pop(0)
        return value

    def fake_publication_runner(*_args, **_kwargs):
        return FakePublication(
            row={"status": "published", "pass2_response_kind": "action_request"},
            response_payload={
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_gh_set_value_params",
                "rationale": "Set to expected value.",
                "input": {"value": 7.5},
            },
        )

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=sequence_executor,
        publication_runner=fake_publication_runner,
    )

    no_guid_files = [
        "scalar_sources.json",
        "acceptance_criteria_packet.json",
        "worker_visible_acceptance_criteria.json",
        "worker_request_payload.json",
        "verify_scalar_output_summary.json",
        "decision.json",
    ]
    for name in no_guid_files:
        assert "SLIDER-GUID-SECRET" not in (run_dir / name).read_text()

    assert (
        "SLIDER-GUID-SECRET"
        in (run_dir / "live_create_scalar_summary.json").read_text()
    )
    assert "SLIDER-GUID-SECRET" in (run_dir / "live_set_value_summary.json").read_text()


def test_main_runs_probe_and_prints_completion(tmp_path: Path, monkeypatch, capsys) -> None:
    run_dir = tmp_path / "lm8c-test"
    run_dir.mkdir()
    (run_dir / "decision.json").write_text(
        json.dumps({"decision": "accepted", "reason": "verify_scalar_output_succeeded"}),
        encoding="utf-8",
    )
    captured = {}

    def fake_run_probe(**kwargs):
        captured.update(kwargs)
        return run_dir

    monkeypatch.setattr(PROBE, "_run_probe", fake_run_probe)

    result = PROBE.main(
        [
            "--model",
            "test-model",
            "--endpoint",
            "http://example.invalid/chat",
            "--temperature",
            "0.25",
            "--timeout-s",
            "3",
            "--excerpt-chars",
            "17",
            "--run-dir",
            str(tmp_path),
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert captured["model"] == "test-model"
    assert captured["endpoint"] == "http://example.invalid/chat"
    assert captured["temperature"] == 0.25
    assert captured["timeout_s"] == 3
    assert captured["excerpt_chars"] == 17
    assert captured["run_root"] == str(tmp_path)
    assert captured["canonical_evidence"] is False
    assert "LM8C GH scalar expectation live splice probe complete" in output
    assert f"run_dir={run_dir}" in output
    assert "decision=accepted" in output
