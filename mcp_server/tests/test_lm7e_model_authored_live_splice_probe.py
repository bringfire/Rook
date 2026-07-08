from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from rook.agent.planner_worker_contract_request import (
    PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA,
    materialize_planner_worker_contract_request,
)
from rook.agent.local_worker_source_routing_validator import (
    SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA,
    SourceRoutingDiagnostic,
    WorkerVisibleSourceRoutingValidationReport,
)


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm7e_model_authored_live_splice_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm7e_model_authored_live_splice_probe",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()


def _valid_incomplete_request() -> dict[str, object]:
    return {
        "schema": PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA,
        "template_id": "repair_same_component_from_create_error",
        "initial_params": {"create_script": {"pins_out": ["A:double"]}},
        "routing_delta": {
            "enable_routes": [],
            "disable_routes": [],
            "set_required": {},
            "add_unresolved_intent_routes": [
                {
                    "route_id": "missing_desired_output_value",
                    "source_class": "planner_user_intent",
                    "source_path": "planner.intent.desired_output_value",
                    "purpose": "unresolved_intent",
                    "required": False,
                }
            ],
        },
        "intent_slots": [
            {
                "intent_id": "desired_output_value",
                "status": "unresolved",
                "source_path": "planner.intent.desired_output_value",
                "description": "Desired output value was not provided.",
            }
        ],
    }


def _valid_runtime_routing_report() -> WorkerVisibleSourceRoutingValidationReport:
    return WorkerVisibleSourceRoutingValidationReport(
        schema=SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA,
        valid=True,
        routability_evaluated=True,
        static_diagnostics=(),
        routability_diagnostics=(),
    )


def _invalid_runtime_routing_report() -> WorkerVisibleSourceRoutingValidationReport:
    diagnostic = SourceRoutingDiagnostic(
        severity="error",
        code="required_route_unresolved",
        node_id="repair_same_component",
        route_id="repair_target_diagnostics",
        source_class="receipt_diagnostic",
        source_path=(
            "create_script.receipt.script_receipt.repair_anchor.target_errors"
        ),
        purpose="acceptance_criteria",
        message="target diagnostics did not resolve",
    )
    return WorkerVisibleSourceRoutingValidationReport(
        schema=SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA,
        valid=False,
        routability_evaluated=True,
        static_diagnostics=(),
        routability_diagnostics=(diagnostic,),
    )


def _real_live_for_lm7e() -> dict[str, object]:
    from rook.agent.plan_graph_workflow_contract import compile_workflow_contract
    from rook.learning.plan_graph_runner import apply_producer_result, apply_verifier_step

    materialization = materialize_planner_worker_contract_request(
        _valid_incomplete_request()
    )
    contract = PROBE.load_workflow_contract_payload(
        materialization.workflow_contract_payload
    )
    scaffold = compile_workflow_contract(contract)
    graph = scaffold.graph
    graph.nodes["create_script"].metadata["execution_params"] = dict(
        contract.initial_params[0].execution_params
    )
    producer_result = apply_producer_result(
        graph,
        "create_script",
        {
            "success": False,
            "message": "Component created with compile errors.",
            "data": {
                "script_receipt": {
                    "version": 1,
                    "operation": "create",
                    "language": "csharp",
                    "artifact_status": "created_with_errors",
                    "mutation": {
                        "status": "created",
                        "component_guid": "component-1",
                    },
                    "verification": {
                        "status": "failed",
                        "target_error_count": 1,
                    },
                    "repair_anchor": {
                        "component_guid": "component-1",
                        "language": "csharp",
                        "target_errors": [
                            "The name 'DefinitelyMissingSymbol' does not exist."
                        ],
                    },
                },
            },
        },
    )
    graph = producer_result.graph
    verify_create = apply_verifier_step(graph, "verify_create", "create_script")
    graph = verify_create.graph
    return {
        "workflow_contract": contract,
        "scaffold": scaffold,
        "graph": graph,
        "convention_packets": (PROBE._script_body_gotcha_packet(),),
        "anchor_binding": {"component_guid": "component-1", "language": "csharp"},
        "live_create_summary": {
            "node_id": "create_script",
            "repair_anchor": {
                "component_guid": "component-1",
                "language": "csharp",
                "target_errors": [
                    "The name 'DefinitelyMissingSymbol' does not exist."
                ],
            },
        },
        "verify_create_summary": {"verifier_node_id": "verify_create"},
    }


def test_cli_defaults_split_planner_and_worker_models() -> None:
    args = PROBE._args(["--planner-provider-command", "fake-provider"])

    assert args.planner_provider_command == "fake-provider"
    assert args.planner_provider == "codex-cli-chatgpt"
    assert args.planner_model == "gpt-5.5"
    assert args.worker_model == "gemma4:12b-it-qat"
    assert args.worker_endpoint == "http://localhost:11434/api/chat"
    assert args.worker_temperature == 0
    assert args.worker_timeout_s == 120
    assert args.output_excerpt_chars == 1200
    assert args.run_dir == "probe_runs"
    assert args.canonical_evidence is False


def test_cli_rejects_forbidden_scenario_attempt_and_retry_options() -> None:
    for option in (
        "--request-json",
        "--scenario",
        "--attempts",
        "--retry-clean-observation",
        "--phase",
        "--prompt-profile",
    ):
        with pytest.raises(SystemExit):
            PROBE._args([option, "x"])


def test_parse_failure_writes_raw_output_and_no_request_or_live(tmp_path: Path) -> None:
    live_called = False

    def fake_provider(_payload):
        return "```json\n{}\n```"

    def fake_live(*_args, **_kwargs):
        nonlocal live_called
        live_called = True

    run_dir = PROBE._run_probe(
        planner_provider="codex-cli-chatgpt",
        planner_model="gpt-5.5",
        planner_provider_command="unused",
        planner_provider_timeout_s=1,
        worker_model="gemma4:12b-it-qat",
        worker_endpoint="http://localhost:11434/api/chat",
        worker_temperature=0,
        worker_timeout_s=120,
        output_excerpt_chars=20,
        run_root=tmp_path,
        canonical_evidence=True,
        call_provider=fake_provider,
        agent=fake_live,
    )

    decision = json.loads((run_dir / "decision.json").read_text())

    assert (run_dir / "planner_model_output.txt").exists()
    assert not (run_dir / "planner_request.json").exists()
    assert not (run_dir / "workflow_validate_report.json").exists()
    assert decision["decision"] == "rejected_by_validate"
    assert decision["reason"] == "planner_parse_failed"
    assert decision["live_rhino_work_started"] is False
    assert decision["worker_publication_ran"] is False
    assert live_called is False


def test_provider_failure_writes_decision_and_stops_before_request_or_validate(
    tmp_path: Path,
) -> None:
    def fake_provider(_payload):
        raise RuntimeError("provider exploded")

    run_dir = PROBE._run_probe(
        planner_provider="codex-cli-chatgpt",
        planner_model="gpt-5.5",
        planner_provider_command="unused",
        planner_provider_timeout_s=1,
        worker_model="gemma4:12b-it-qat",
        worker_endpoint="http://localhost:11434/api/chat",
        worker_temperature=0,
        worker_timeout_s=120,
        output_excerpt_chars=20,
        run_root=tmp_path,
        canonical_evidence=True,
        call_provider=fake_provider,
        agent=object(),
    )

    decision = json.loads((run_dir / "decision.json").read_text())

    assert (run_dir / "planner_model_output.txt").exists()
    assert not (run_dir / "planner_request.json").exists()
    assert not (run_dir / "workflow_validate_report.json").exists()
    assert decision["decision"] == "rejected_by_validate"
    assert decision["reason"].startswith("planner_provider_failed:")
    assert decision["planner_parse_status"] == "parse_failed"
    assert decision["planner_validation_status"] == "not_evaluated"
    assert decision["live_rhino_work_started"] is False
    assert decision["worker_publication_ran"] is False


def test_parsed_request_marker_fails_before_workflow_validate_and_live(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validate_called = False

    request = _valid_incomplete_request()
    request["extra"] = "A = 0.0"

    def fake_validate(_request):
        nonlocal validate_called
        validate_called = True
        return {"valid": True}

    monkeypatch.setattr(PROBE, "validate_planner_worker_contract_request", fake_validate)

    run_dir = PROBE._run_probe(
        planner_provider="codex-cli-chatgpt",
        planner_model="gpt-5.5",
        planner_provider_command="unused",
        planner_provider_timeout_s=1,
        worker_model="gemma4:12b-it-qat",
        worker_endpoint="http://localhost:11434/api/chat",
        worker_temperature=0,
        worker_timeout_s=120,
        output_excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        call_provider=lambda _payload: json.dumps(request),
        agent=object(),
    )

    decision = json.loads((run_dir / "decision.json").read_text())

    assert (run_dir / "planner_request.json").exists()
    assert not (run_dir / "workflow_validate_report.json").exists()
    assert validate_called is False
    assert decision["decision"] == "rejected_by_validate"
    assert decision["reason"] == "planner_hidden_marker_detected"
    assert decision["planner_parse_status"] == "parsed"
    assert decision["planner_validation_status"] == "not_evaluated"


def test_workflow_validate_failure_stops_before_materialization_and_live(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    materialize_called = False

    def fake_validate(_request):
        return {
            "valid": False,
            "request_fingerprint": "sha256:req",
            "report_fingerprint": "sha256:report",
        }

    def fake_materialize(_request):
        nonlocal materialize_called
        materialize_called = True

    monkeypatch.setattr(PROBE, "validate_planner_worker_contract_request", fake_validate)
    monkeypatch.setattr(
        PROBE,
        "materialize_planner_worker_contract_request",
        fake_materialize,
        raising=False,
    )

    run_dir = PROBE._run_probe(
        planner_provider="codex-cli-chatgpt",
        planner_model="gpt-5.5",
        planner_provider_command="unused",
        planner_provider_timeout_s=1,
        worker_model="gemma4:12b-it-qat",
        worker_endpoint="http://localhost:11434/api/chat",
        worker_temperature=0,
        worker_timeout_s=120,
        output_excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        call_provider=lambda _payload: json.dumps(_valid_incomplete_request()),
        agent=object(),
    )

    decision = json.loads((run_dir / "decision.json").read_text())

    assert (run_dir / "planner_request.json").exists()
    assert (run_dir / "workflow_validate_report.json").exists()
    assert materialize_called is False
    assert decision["decision"] == "rejected_by_validate"
    assert decision["reason"] == "workflow_validate_failed"
    assert decision["workflow_validate_valid"] is False


def test_valid_request_writes_resolved_routing_and_bounded_contract_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_live_not_implemented(**_kwargs):
        raise NotImplementedError("stop before live")

    monkeypatch.setattr(
        PROBE,
        "_run_live_create_and_verify",
        fake_live_not_implemented,
        raising=False,
    )

    run_dir = PROBE._run_probe(
        planner_provider="codex-cli-chatgpt",
        planner_model="gpt-5.5",
        planner_provider_command="unused",
        planner_provider_timeout_s=1,
        worker_model="gemma4:12b-it-qat",
        worker_endpoint="http://localhost:11434/api/chat",
        worker_temperature=0,
        worker_timeout_s=120,
        output_excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        call_provider=lambda _payload: json.dumps(_valid_incomplete_request()),
        agent=object(),
    )

    routing = json.loads((run_dir / "resolved_source_routing.json").read_text())
    summary = json.loads((run_dir / "workflow_contract_summary.json").read_text())
    decision = json.loads((run_dir / "decision.json").read_text())

    rendered_routing = json.dumps(routing, sort_keys=True)
    assert "missing_desired_output_value" in rendered_routing
    assert "planner.intent.desired_output_value" in rendered_routing
    assert summary["template_id"] == "repair_same_component_from_create_error"
    assert "repair_same_component" in summary["worker_node_ids"]
    assert summary["worker_node_bind_steps"]["repair_same_component"] is False
    rendered_summary = json.dumps(summary, sort_keys=True)
    for marker in (
        "base_params",
        "PROBE_REPAIR_CODE",
        "A = 42.0",
        "A = 0.0",
        "A = 1.0",
    ):
        assert marker not in rendered_summary
    assert decision["decision"] == "gate_failed"
    assert decision["reason"] == "runtime_not_implemented"


def test_workflow_contract_summary_reports_worker_bind_step_presence_without_base_params() -> None:
    payload = {
        "initial_params": [],
        "rules": [
            {
                "node_id": "repair_same_component",
                "steps_by_seen_count": [
                    {
                        "kind": "bind",
                        "node_id": "repair_same_component",
                        "base_params": {"code": "PROBE_REPAIR_CODE"},
                        "bindings": {},
                    }
                ],
            }
        ],
        "expected_refs": [{"node_id": "repair_same_component"}],
    }
    loaded_contract = SimpleNamespace(
        initial_params=(),
        rules=(
            SimpleNamespace(
                node_id="repair_same_component",
                steps_by_seen_count=(
                    SimpleNamespace(
                        kind="bind",
                        node_id="repair_same_component",
                        base_params={"code": "PROBE_REPAIR_CODE"},
                    ),
                ),
            ),
        ),
    )

    summary = PROBE._workflow_contract_summary(
        template_id="repair_same_component_from_create_error",
        workflow_contract_payload=payload,
        workflow_contract=loaded_contract,
        worker_node_ids=("repair_same_component",),
    )

    rendered = json.dumps(summary, sort_keys=True)
    assert summary["worker_node_bind_steps"]["repair_same_component"] is True
    assert "base_params" not in rendered
    assert "PROBE_REPAIR_CODE" not in rendered


def test_static_guard_forbids_hand_authored_request_and_non_neutral_worker_helpers() -> None:
    source = _script_path().read_text(encoding="utf-8")
    forbidden = [
        "_canonical_planner_request",
        "_worker_request_payload",
        "_acceptance_criteria_evidence_packet",
        "script_local_canonical_lm7a_request",
        "lm6e_bounded_retry_context",
        "retry_clean_observation",
    ]

    for marker in forbidden:
        assert marker not in source


def test_static_guard_no_live_prompt_or_protocol_drift() -> None:
    source = _script_path().read_text(encoding="utf-8")
    forbidden = [
        "lm6e_bounded_retry_context",
        "--retry-clean-observation",
        "worker_publication_rows.json",
        "_canonical_planner_request",
        "script_local_canonical_lm7a_request",
        "_worker_request_payload",
        "_acceptance_criteria_evidence_packet",
        "PROBE_REPAIR_CODE =",
        "A = 42.0;",
    ]

    for marker in forbidden:
        assert marker not in source


def test_planner_marker_scan_excludes_worker_action_fields() -> None:
    decision = {
        "worker_action_input_excerpt": "A = 0.0;",
        "worker_action_input_sha256": "sha256:abc",
        "planner_model_output_excerpt": "{}",
    }

    assert PROBE._planner_marker_matches_in_metadata(decision) == []


def test_lm7e_prompt_artifacts_match_lm7d_shape_guidance(tmp_path: Path) -> None:
    PROBE.write_prompt_artifacts(
        tmp_path,
        PROBE.PROMPT_PROFILE_SHAPE_GUIDANCE_V2,
        scenarios=("intent_incomplete",),
    )

    prompt = (tmp_path / "prompts" / "planner_authoring_prompt.txt").read_text()
    menu = (tmp_path / "prompts" / "template_menu.json").read_text()
    brief = (tmp_path / "prompts" / "intent_incomplete_brief.txt").read_text()

    assert "lm7d.planner_authoring_prompt_shape_guidance:v2" in prompt
    assert '"route_id": "missing_desired_output_value"' in prompt
    assert '"source_path": "planner.intent.desired_output_value"' in prompt
    assert "lm7c.template_menu:v1" in menu
    assert "lm7c.intent_incomplete_brief:v1" in brief
    for marker in ("PROBE_REPAIR_CODE", "A = 42.0", "A = 0.0", "A = 1.0"):
        assert marker not in prompt
        assert marker not in menu
        assert marker not in brief


def test_fake_live_action_request_reaches_accepted_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live = _real_live_for_lm7e()
    captured_worker_kwargs = []
    captured_routing_contracts = []

    class FakePublication:
        row = {"status": "published"}
        response_payload = {
            "kind": "action_request",
            "action_id": "draft_repair_params",
            "input": {"code": "A = 0.0;", "mode": "body"},
        }

    def fake_live_create(**_kwargs):
        return live

    def fake_validate_routing(*_args, **kwargs):
        captured_routing_contracts.append(kwargs["workflow_contract"])
        return _valid_runtime_routing_report()

    def fake_publication(payload, **kwargs):
        captured_worker_kwargs.append(kwargs)
        return FakePublication()

    def fake_apply(graph, node_id, *, action_id, action_input, anchor_binding, **_kwargs):
        class Result:
            applied = True
            reason = None
            params_sha256 = "sha256:params"
            graph = live["graph"]

        return Result()

    def fake_dispatch(**_kwargs):
        return {
            "decision": {
                "schema": "rook.lm6a_decision:v1",
                "decision": "accepted",
                "reason": "verify_repair_succeeded",
                "phase": "verify_repair",
                "live_repair_dispatched": True,
                "verify_repair_ran": True,
            }
        }

    monkeypatch.setattr(PROBE, "_run_live_create_and_verify", fake_live_create)
    monkeypatch.setattr(
        PROBE, "validate_worker_visible_source_routing", fake_validate_routing
    )
    monkeypatch.setattr(PROBE, "run_two_pass_worker_publication", fake_publication)
    monkeypatch.setattr(PROBE, "apply_worker_action_to_node", fake_apply)
    monkeypatch.setattr(PROBE, "_dispatch_repair_and_verify", fake_dispatch)

    run_dir = PROBE._run_probe(
        planner_provider="codex-cli-chatgpt",
        planner_model="gpt-5.5",
        planner_provider_command="unused",
        planner_provider_timeout_s=1,
        worker_model="gemma4:12b-it-qat",
        worker_endpoint="http://localhost:11434/api/chat",
        worker_temperature=0,
        worker_timeout_s=120,
        output_excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        call_provider=lambda _payload: json.dumps(_valid_incomplete_request()),
        agent=object(),
    )

    decision = json.loads((run_dir / "decision.json").read_text())

    assert decision["decision"] == "accepted"
    assert decision["reason"] == "verify_repair_succeeded"
    assert decision["worker_publication_ran"] is True
    assert decision["live_rhino_work_started"] is True
    assert decision["planner_validation_status"] == "workflow_validate_valid"
    assert (run_dir / "runtime_routing_validation.json").exists()
    assert (run_dir / "acceptance_criteria_packet.json").exists()
    assert (run_dir / "worker_visible_acceptance_criteria.json").exists()
    assert (run_dir / "worker_publication_row.json").exists()
    assert (run_dir / "worker_action.json").exists()
    assert captured_worker_kwargs[0]["model"] == "gemma4:12b-it-qat"
    assert captured_worker_kwargs[0]["endpoint"] == "http://localhost:11434/api/chat"
    assert captured_worker_kwargs[0]["temperature"] == 0
    routing_contract = captured_routing_contracts[0]
    create_initial = next(
        item for item in routing_contract.initial_params if item.node_id == "create_script"
    )
    assert create_initial.execution_params["pins_out"] == ["A:double"]
    assert isinstance(create_initial.execution_params["pins_out"], list)


def _run_valid_lm7e_with_live_fakes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    routing_report: WorkerVisibleSourceRoutingValidationReport | None = None,
    publication: object | None = None,
    apply_result: object | None = None,
) -> Path:
    live = _real_live_for_lm7e()

    if routing_report is None:
        routing_report = _valid_runtime_routing_report()

    if publication is None:
        class DefaultPublication:
            row = {"status": "published"}
            response_payload = {
                "kind": "action_request",
                "action_id": "draft_repair_params",
                "input": {"code": "A = 0.0;", "mode": "body"},
            }

        publication = DefaultPublication()

    if apply_result is None:
        class DefaultApplyResult:
            applied = True
            reason = None
            params_sha256 = "sha256:params"
            graph = live["graph"]

        apply_result = DefaultApplyResult()

    monkeypatch.setattr(PROBE, "_run_live_create_and_verify", lambda **_kwargs: live)
    monkeypatch.setattr(
        PROBE,
        "validate_worker_visible_source_routing",
        lambda *_args, **_kwargs: routing_report,
    )
    monkeypatch.setattr(
        PROBE,
        "run_two_pass_worker_publication",
        lambda *_args, **_kwargs: publication,
    )
    monkeypatch.setattr(
        PROBE,
        "apply_worker_action_to_node",
        lambda *_args, **_kwargs: apply_result,
    )
    monkeypatch.setattr(
        PROBE,
        "_dispatch_repair_and_verify",
        lambda **_kwargs: {
            "decision": {
                "schema": "rook.lm6a_decision:v1",
                "decision": "accepted",
                "reason": "verify_repair_succeeded",
                "phase": "verify_repair",
                "live_repair_dispatched": True,
                "verify_repair_ran": True,
            }
        },
    )

    return PROBE._run_probe(
        planner_provider="codex-cli-chatgpt",
        planner_model="gpt-5.5",
        planner_provider_command="unused",
        planner_provider_timeout_s=1,
        worker_model="gemma4:12b-it-qat",
        worker_endpoint="http://localhost:11434/api/chat",
        worker_temperature=0,
        worker_timeout_s=120,
        output_excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        call_provider=lambda _payload: json.dumps(_valid_incomplete_request()),
        agent=object(),
    )


def _assert_valid_planner_metadata(decision: dict[str, object]) -> None:
    assert decision["worker_retry_enabled"] is False
    assert decision["planner_parse_status"] == "parsed"
    assert decision["planner_validation_status"] == "workflow_validate_valid"
    assert isinstance(decision["request_fingerprint"], str)
    assert isinstance(decision["workflow_validate_report_fingerprint"], str)


def test_runtime_routing_error_writes_gate_failed_without_worker_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_valid_lm7e_with_live_fakes(
        tmp_path,
        monkeypatch,
        routing_report=_invalid_runtime_routing_report(),
    )

    decision = json.loads((run_dir / "decision.json").read_text())

    assert decision["decision"] == "gate_failed"
    assert decision["reason"] == "runtime_routability_failed"
    assert decision["worker_publication_ran"] is False
    assert (run_dir / "runtime_routing_validation.json").exists()
    assert not (run_dir / "worker_publication_row.json").exists()
    assert not (run_dir / "worker_action.json").exists()
    _assert_valid_planner_metadata(decision)


def test_worker_observation_decline_reuses_worker_declined_without_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ObservationPublication:
        row = {"status": "published", "observation_action_intent_anomaly": False}
        response_payload = {"kind": "observation", "message": "I cannot act."}

    run_dir = _run_valid_lm7e_with_live_fakes(
        tmp_path,
        monkeypatch,
        publication=ObservationPublication(),
    )

    decision = json.loads((run_dir / "decision.json").read_text())

    assert decision["decision"] == "worker_declined"
    assert decision["reason"] == "worker_observed"
    assert decision["worker_publication_ran"] is True
    assert not (run_dir / "worker_publication_rows.json").exists()
    assert not (run_dir / "retry_context.json").exists()
    assert not (run_dir / "worker_action.json").exists()
    _assert_valid_planner_metadata(decision)


def test_worker_publication_hidden_answer_leak_writes_publication_failed_without_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class LeakingPublication:
        row = {"status": "published", "debug": "PROBE_REPAIR_CODE"}
        response_payload = {"kind": "observation", "message": "no action"}

    run_dir = _run_valid_lm7e_with_live_fakes(
        tmp_path,
        monkeypatch,
        publication=LeakingPublication(),
    )

    decision = json.loads((run_dir / "decision.json").read_text())

    assert decision["decision"] == "publication_failed"
    assert decision["reason"] == "worker_publication_hidden_answer_leak"
    assert decision["worker_publication_ran"] is True
    assert not (run_dir / "worker_publication_row.json").exists()
    assert not (run_dir / "worker_action.json").exists()
    _assert_valid_planner_metadata(decision)


def test_worker_action_apply_rejection_writes_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RejectApplyResult:
        applied = False
        reason = "invalid_mode"
        params_sha256 = None
        graph = object()

    run_dir = _run_valid_lm7e_with_live_fakes(
        tmp_path,
        monkeypatch,
        apply_result=RejectApplyResult(),
    )

    decision = json.loads((run_dir / "decision.json").read_text())

    assert decision["decision"] == "rejected"
    assert decision["reason"] == "worker_action_apply_failed:invalid_mode"
    assert decision["worker_publication_ran"] is True
    assert decision["live_repair_dispatched"] is False
    assert decision["verify_repair_ran"] is False
    assert (run_dir / "worker_publication_row.json").exists()
    assert (run_dir / "worker_action.json").exists()
    _assert_valid_planner_metadata(decision)
