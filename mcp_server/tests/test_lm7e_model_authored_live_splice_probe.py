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
