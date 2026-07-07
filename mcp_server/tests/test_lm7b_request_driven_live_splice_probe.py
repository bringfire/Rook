from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from rook.agent.planner_worker_contract_request import (
    LM7A_TEMPLATE_ID,
    PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA,
    materialize_planner_worker_contract_request,
)
from rook.agent.local_worker_source_routing_validator import (
    SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA,
    SourceRoutingDiagnostic,
    WorkerVisibleSourceRoutingValidationReport,
)
from rook.agent.workflow_validate import validate_planner_worker_contract_request


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm7b_request_driven_live_splice_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm7b_request_driven_live_splice_probe",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()


def test_cli_defaults_are_canonical() -> None:
    args = PROBE._args([])

    assert args.model == "gemma4:12b-it-qat"
    assert args.endpoint == "http://localhost:11434/api/chat"
    assert args.temperature == 0
    assert args.timeout_s == 120
    assert args.excerpt_chars == 1200
    assert args.run_dir == "probe_runs"


def test_cli_forbids_request_phase_and_retry_options() -> None:
    with pytest.raises(SystemExit):
        PROBE._args(["--request-json", "request.json"])
    with pytest.raises(SystemExit):
        PROBE._args(["--phase", "receipt_recon"])
    with pytest.raises(SystemExit):
        PROBE._args(["--retry-clean-observation"])


def test_canonical_planner_request_matches_lm7a_schema_and_validates() -> None:
    request = PROBE._canonical_planner_request()

    assert request["schema"] == PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA
    assert request["template_id"] == LM7A_TEMPLATE_ID
    assert request["initial_params"] == {
        "create_script": {"pins_out": ["A:double"]}
    }
    assert request["intent_slots"] == [
        {
            "intent_id": "desired_output_value",
            "status": "unresolved",
            "source_path": "planner.intent.desired_output_value",
            "description": "Desired output value was not provided.",
        }
    ]

    report = validate_planner_worker_contract_request(request)
    assert report["valid"] is True

    materialization = materialize_planner_worker_contract_request(request)
    assert materialization.diagnostics == ()
    assert materialization.workflow_contract_payload is not None
    assert materialization.resolved_routing_artifact is not None
    assert materialization.worker_node_ids == ("repair_same_component",)


def test_fingerprint_is_stable_against_dict_order() -> None:
    request = PROBE._canonical_planner_request()
    reordered = {
        "intent_slots": request["intent_slots"],
        "routing_delta": request["routing_delta"],
        "initial_params": request["initial_params"],
        "template_id": request["template_id"],
        "schema": request["schema"],
    }

    assert PROBE._fingerprint(request) == PROBE._fingerprint(reordered)
    assert PROBE._fingerprint(request).startswith("sha256:")


def test_manifest_records_request_driven_identity() -> None:
    manifest = PROBE._manifest(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        request_fingerprint="sha256:req",
        workflow_validate_report_fingerprint="sha256:report",
    )

    assert manifest["script_schema"] == "rook.lm7b_request_driven_live_splice_probe:v1"
    assert manifest["planner_request_source"] == "script_local_canonical_lm7a_request"
    assert manifest["worker_retry_enabled"] is False
    assert manifest["request_fingerprint"] == "sha256:req"
    assert manifest["workflow_validate_report_fingerprint"] == "sha256:report"


def test_authoring_gate_rejects_invalid_workflow_validate_without_live_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_called = False
    materialize_called = False

    def fake_validate(_request):
        return {
            "valid": False,
            "request_fingerprint": "sha256:req",
            "report_fingerprint": "sha256:report",
        }

    def fake_live(**_kwargs):
        nonlocal live_called
        live_called = True
        return {}

    def fake_materialize(_request):
        nonlocal materialize_called
        materialize_called = True
        return None

    monkeypatch.setattr(PROBE, "validate_planner_worker_contract_request", fake_validate)
    monkeypatch.setattr(
        PROBE,
        "materialize_planner_worker_contract_request",
        fake_materialize,
    )
    monkeypatch.setattr(PROBE, "_run_live_create_and_verify", fake_live)

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        agent="lm7b",
    )

    decision = json.loads((run_dir / "decision.json").read_text())

    assert live_called is False
    assert materialize_called is False
    assert decision["decision"] == "rejected_by_validate"
    assert decision["reason"] == "workflow_validate_failed"
    assert decision["workflow_validate_valid"] is False
    assert decision["workflow_validate_report_fingerprint"] == "sha256:report"
    assert decision["runtime_routing_valid"] is None
    assert decision["runtime_routability_evaluated"] is False
    assert (run_dir / "planner_request.json").exists()
    assert (run_dir / "workflow_validate_report.json").exists()
    assert not (run_dir / "live_create_summary.json").exists()


@pytest.mark.parametrize("valid_value", ["yes", "false"])
def test_authoring_gate_requires_strict_true_workflow_validate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    valid_value: str,
) -> None:
    live_called = False
    materialize_called = False

    def fake_validate(_request):
        return {
            "valid": valid_value,
            "request_fingerprint": "sha256:req",
            "report_fingerprint": "sha256:report",
        }

    def fake_materialize(_request):
        nonlocal materialize_called
        materialize_called = True
        return None

    def fake_live(**_kwargs):
        nonlocal live_called
        live_called = True
        return {}

    monkeypatch.setattr(PROBE, "validate_planner_worker_contract_request", fake_validate)
    monkeypatch.setattr(
        PROBE,
        "materialize_planner_worker_contract_request",
        fake_materialize,
    )
    monkeypatch.setattr(PROBE, "_run_live_create_and_verify", fake_live)

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        agent="lm7b",
    )

    decision = json.loads((run_dir / "decision.json").read_text())

    assert decision["decision"] == "rejected_by_validate"
    assert decision["workflow_validate_valid"] is False
    assert materialize_called is False
    assert live_called is False


def test_materialization_uses_same_emitted_planner_request_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = []

    def fake_validate(request):
        captured.append(("validate", request))
        return {
            "valid": True,
            "request_fingerprint": "sha256:req",
            "report_fingerprint": "sha256:report",
        }

    def fake_materialize(request):
        captured.append(("materialize", request))
        return materialize_planner_worker_contract_request(request)

    def fake_live(**_kwargs):
        raise NotImplementedError("stop for materialization test")

    monkeypatch.setattr(PROBE, "validate_planner_worker_contract_request", fake_validate)
    monkeypatch.setattr(
        PROBE,
        "materialize_planner_worker_contract_request",
        fake_materialize,
    )
    monkeypatch.setattr(PROBE, "_run_live_create_and_verify", fake_live)

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        agent="lm7b",
    )

    emitted = json.loads((run_dir / "planner_request.json").read_text())
    decision = json.loads((run_dir / "decision.json").read_text())

    assert captured == [("validate", emitted), ("materialize", emitted)]
    assert decision["reason"] == "runtime_not_implemented"


def test_valid_workflow_without_live_seam_writes_runtime_not_implemented_decision(
    tmp_path: Path,
) -> None:
    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        agent="lm7b",
    )

    decision = json.loads((run_dir / "decision.json").read_text())

    assert decision["decision"] == "gate_failed"
    assert decision["reason"] == "runtime_not_implemented"


def test_temporary_live_seam_decision_does_not_bypass_runtime_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_live(**_kwargs):
        return {
            "decision": {
                "decision": "temporary_live_seam",
                "reason": "demo",
            }
        }

    monkeypatch.setattr(PROBE, "_run_live_create_and_verify", fake_live)

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        agent="lm7b",
    )

    decision = json.loads((run_dir / "decision.json").read_text())

    assert decision["decision"] == "gate_failed"
    assert decision["reason"] != "temporary_live_seam:demo"
    assert decision["reason"] == "runtime_not_implemented"


def test_temporary_live_seam_decision_normalizes_runtime_routing_valid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_live(**_kwargs):
        return {
            "decision": {
                "decision": "gate_failed",
                "reason": "stop_for_test",
                "runtime_routing_valid": "yes",
            }
        }

    monkeypatch.setattr(PROBE, "_run_live_create_and_verify", fake_live)

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        agent="lm7b",
    )

    decision = json.loads((run_dir / "decision.json").read_text())

    assert decision["runtime_routing_valid"] is None
    assert decision["reason"] != "stop_for_test"


def test_runtime_routability_not_evaluated_gate_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_live(**_kwargs):
        return _fake_live()

    def fake_validate_routing(*_args, **_kwargs):
        return WorkerVisibleSourceRoutingValidationReport(
            schema=SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA,
            valid=True,
            routability_evaluated=False,
            static_diagnostics=(),
            routability_diagnostics=(),
        )

    monkeypatch.setattr(PROBE, "_run_live_create_and_verify", fake_live)
    monkeypatch.setattr(
        PROBE,
        "validate_worker_visible_source_routing",
        fake_validate_routing,
    )

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        agent="lm7b",
    )

    decision = json.loads((run_dir / "decision.json").read_text())

    assert decision["decision"] == "gate_failed"
    assert decision["reason"] == "runtime_routability_not_evaluated"
    assert decision["runtime_routing_valid"] is True
    assert decision["runtime_routability_evaluated"] is False
    assert not (run_dir / "worker_publication_row.json").exists()


def test_runtime_routability_error_gate_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostic = SourceRoutingDiagnostic(
        severity="error",
        code="required_route_unresolved",
        node_id="repair_same_component",
        route_id="repair_pin_contract",
        source_class="pin_contract",
        source_path="create_script.initial_execution_params.pins_out",
        purpose="acceptance_criteria",
        message="Required route was not resolvable.",
    )

    def fake_live(**_kwargs):
        return _fake_live()

    def fake_validate_routing(*_args, **_kwargs):
        return WorkerVisibleSourceRoutingValidationReport(
            schema=SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA,
            valid=False,
            routability_evaluated=True,
            static_diagnostics=(),
            routability_diagnostics=(diagnostic,),
        )

    monkeypatch.setattr(PROBE, "_run_live_create_and_verify", fake_live)
    monkeypatch.setattr(
        PROBE,
        "validate_worker_visible_source_routing",
        fake_validate_routing,
    )

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        agent="lm7b",
    )

    decision = json.loads((run_dir / "decision.json").read_text())
    routing_report = json.loads(
        (run_dir / "runtime_routing_validation.json").read_text()
    )

    assert decision["decision"] == "gate_failed"
    assert decision["reason"] == "runtime_routability_failed"
    assert decision["runtime_routing_valid"] is False
    assert decision["runtime_routability_evaluated"] is True
    assert routing_report["routability_diagnostics"][0]["code"] == (
        "required_route_unresolved"
    )


def test_optional_unresolved_intent_warning_reaches_real_worker_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostic = SourceRoutingDiagnostic(
        severity="warning",
        code="optional_route_unresolved",
        node_id="repair_same_component",
        route_id="missing_desired_output_value",
        source_class="planner_user_intent",
        source_path="planner.intent.desired_output_value",
        purpose="unresolved_intent",
        message="Optional intent route was unresolved.",
    )
    captured_payloads = []

    class FakePublication:
        row = {"status": "published"}
        response_payload = {"kind": "observation"}

    live = _real_live()

    def fake_live(**_kwargs):
        return live

    def fake_validate_routing(*_args, **_kwargs):
        return WorkerVisibleSourceRoutingValidationReport(
            schema=SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA,
            valid=True,
            routability_evaluated=True,
            static_diagnostics=(),
            routability_diagnostics=(diagnostic,),
        )

    def fake_publication(payload, **_kwargs):
        captured_payloads.append(payload)
        return FakePublication()

    monkeypatch.setattr(PROBE, "_run_live_create_and_verify", fake_live)
    monkeypatch.setattr(
        PROBE,
        "validate_worker_visible_source_routing",
        fake_validate_routing,
    )
    monkeypatch.setattr(PROBE, "run_two_pass_worker_publication", fake_publication)

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        agent="lm7b",
    )

    decision = json.loads((run_dir / "decision.json").read_text())

    assert (run_dir / "worker_publication_row.json").exists()
    assert decision["decision"] == "worker_declined"
    assert decision["runtime_routing_valid"] is True
    assert decision["runtime_routability_evaluated"] is True
    assert len(captured_payloads) == 1
    knowledge = captured_payloads[0]["context"]["knowledge"]
    packets_by_id = {packet["packet_id"]: packet for packet in knowledge}
    assert "acceptance_criteria" in packets_by_id
    content = packets_by_id["acceptance_criteria"]["content"]
    assert set(content) == {"source", "criteria"}
    assert content["source"] == (
        "workflow_contract + create_script.initial_execution_params + "
        "create_script.receipt.script_receipt.repair_anchor + script_body_gotcha"
    )
    assert content["criteria"]
    assert all(
        set(criterion) == {"criterion_id", "description", "source"}
        for criterion in content["criteria"]
    )
    rendered = json.dumps(content, sort_keys=True)
    for forbidden in (
        "schema",
        "source_set",
        "source_class",
        "unresolved_intent",
        "fingerprint",
    ):
        assert forbidden not in rendered
    assert captured_payloads[0]["context"]["current_node"]["node_id"] == (
        "repair_same_component"
    )


def _fake_live() -> dict:
    return {
        "workflow_contract": object(),
        "scaffold": object(),
        "graph": object(),
        "convention_packets": (object(),),
        "anchor_binding": {"component_guid": "component-1", "language": "csharp"},
        "live_create_summary": {"node_id": "create_script"},
        "verify_create_summary": {"verifier_node_id": "verify_create"},
    }


def _real_live() -> dict:
    from rook.agent.plan_graph_workflow_contract import compile_workflow_contract
    from rook.learning.plan_graph_runner import apply_producer_result, apply_verifier_step

    materialization = materialize_planner_worker_contract_request(
        PROBE._canonical_planner_request()
    )
    contract = PROBE.load_workflow_contract_payload(
        materialization.workflow_contract_payload
    )
    scaffold = compile_workflow_contract(contract)
    graph = scaffold.graph
    graph.nodes["create_script"].metadata["execution_params"] = {
        "pins_out": ["A:double"]
    }
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
