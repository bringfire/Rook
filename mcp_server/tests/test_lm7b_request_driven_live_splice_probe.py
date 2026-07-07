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


def test_script_static_guard_forbids_request_phase_and_retry_surfaces() -> None:
    script_source = _script_path().read_text(encoding="utf-8")
    forbidden = [
        "--request" + "-json",
        "--" + "phase",
        "--retry-clean" + "-observation",
        "lm6e_bounded" + "_retry_context",
        "_retry" + "_context_packet",
        "_request_payload" + "_with_retry_context",
        "_worker_request" + "_payload",
        "_acceptance_criteria" + "_evidence_packet",
    ]

    for marker in forbidden:
        assert marker not in script_source


def test_canonical_request_and_manifest_do_not_embed_hidden_answer_markers() -> None:
    request = PROBE._canonical_planner_request()
    manifest = PROBE._manifest(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        request_fingerprint="sha256:req",
        workflow_validate_report_fingerprint="sha256:report",
    )
    rendered = json.dumps({"request": request, "manifest": manifest}, sort_keys=True)
    forbidden = [
        "PROBE_REPAIR" + "_CODE",
        "A = " + "42.0",
        "BindStepSpec.base_params" + ".code",
        "BindStepSpec" + ".base_params",
        "repair_same_component.bind" + ".base_params",
    ]

    for marker in forbidden:
        assert marker not in rendered


def test_build_agent_uses_rook_agent_with_mcp_tool_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import types

    captured = {}

    def fake_executor():
        return None

    class FakeRookAgent:
        def __init__(self, *, tool_executor):
            captured["tool_executor"] = tool_executor

    monkeypatch.setitem(
        sys.modules,
        "rook.agent.base_agent",
        types.SimpleNamespace(RookAgent=FakeRookAgent),
    )
    monkeypatch.setitem(
        sys.modules,
        "rook.server",
        types.SimpleNamespace(_mcp_tool_executor=fake_executor),
    )

    agent = PROBE._build_agent()

    assert isinstance(agent, FakeRookAgent)
    assert captured["tool_executor"] is fake_executor


def test_main_runs_probe_with_built_agent_and_prints_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    built_agent = object()
    captured = {}
    run_dir = tmp_path / "lm7b-test-run"
    run_dir.mkdir()
    (run_dir / "decision.json").write_text(
        json.dumps({"decision": "accepted", "reason": "verify_repair_passed"}),
        encoding="utf-8",
    )

    def fake_run_probe(**kwargs):
        captured.update(kwargs)
        return run_dir

    monkeypatch.setattr(PROBE, "_build_agent", lambda: built_agent)
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
    assert captured == {
        "model": "test-model",
        "endpoint": "http://example.invalid/chat",
        "temperature": 0.25,
        "timeout_s": 3,
        "excerpt_chars": 17,
        "run_root": str(tmp_path),
        "agent": built_agent,
    }
    assert "LM7B request-driven live splice probe complete" in output
    assert f"run_dir={run_dir}" in output
    assert "decision=accepted" in output
    assert "reason=verify_repair_passed" in output


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


def test_live_create_stages_materialized_pins_as_json_lists() -> None:
    from rook.agent.plan_graph_live import LiveProducerResult
    from rook.learning.plan_graph_runner import apply_producer_result

    materialization = materialize_planner_worker_contract_request(
        PROBE._canonical_planner_request()
    )
    workflow_contract = PROBE.load_workflow_contract_payload(
        materialization.workflow_contract_payload
    )
    initial_params = workflow_contract.initial_params[0].execution_params
    assert isinstance(initial_params["pins_in"], tuple)
    assert isinstance(initial_params["pins_out"], tuple)
    captured_params = {}

    class FakeAgent:
        async def run_live_producer_node(self, graph, node_id):
            captured_params.update(graph.nodes[node_id].metadata["execution_params"])
            inner = apply_producer_result(
                graph,
                node_id,
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
            return LiveProducerResult(
                graph=inner.graph,
                applied=inner.applied,
                node_id=node_id,
                tool_name="gh_create_csharp_script",
                outcome_status=inner.outcome_status,
                reason=inner.reason,
            )

    PROBE._run_live_create_and_verify(
        agent=FakeAgent(),
        workflow_contract=workflow_contract,
    )

    assert captured_params["pins_in"] == []
    assert captured_params["pins_out"] == ["A:double"]
    assert isinstance(captured_params["pins_in"], list)
    assert isinstance(captured_params["pins_out"], list)


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
        return _real_live()

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
        return _real_live()

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
    assert "lm5u_acceptance_criteria_evidence" in packets_by_id
    packet = packets_by_id["lm5u_acceptance_criteria_evidence"]
    assert packet["kind"] == "evidence"
    content = packet["content"]
    assert content["source"] == "planner_worker_contract_request"
    assert content["trust"] == "high"
    assert content["state"] == "post_verify_pre_worker"
    fields = content["fields"]
    assert {
        "current_code",
        "language",
        "recommended_mode",
        "repair_anchor",
        "pin_contract",
        "target_diagnostics",
        "expected_repair_outcome",
        "acceptance_criteria",
    } <= set(fields)
    acceptance = fields["acceptance_criteria"]
    assert acceptance["source"] == (
        "workflow_contract + create_script.initial_execution_params + "
        "create_script.receipt.script_receipt.repair_anchor + script_body_gotcha"
    )
    assert acceptance["criteria"]
    assert all(
        set(criterion) == {"criterion_id", "description", "source"}
        for criterion in acceptance["criteria"]
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


def test_runtime_routability_receives_json_style_contract_params(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_params = []

    class FakePublication:
        row = {"status": "published"}
        response_payload = {"kind": "observation"}

    live = _real_live()
    assert isinstance(
        live["workflow_contract"].initial_params[0].execution_params["pins_out"],
        tuple,
    )

    def fake_live(**_kwargs):
        return live

    def fake_validate_routing(*_args, **kwargs):
        params = kwargs["workflow_contract"].initial_params[0].execution_params
        captured_params.append(params)
        return WorkerVisibleSourceRoutingValidationReport(
            schema=SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA,
            valid=True,
            routability_evaluated=True,
            static_diagnostics=(),
            routability_diagnostics=(),
        )

    monkeypatch.setattr(PROBE, "_run_live_create_and_verify", fake_live)
    monkeypatch.setattr(
        PROBE,
        "validate_worker_visible_source_routing",
        fake_validate_routing,
    )
    monkeypatch.setattr(
        PROBE,
        "run_two_pass_worker_publication",
        lambda _payload, **_kwargs: FakePublication(),
    )

    PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        agent="lm7b",
    )

    assert len(captured_params) == 1
    assert captured_params[0]["pins_in"] == []
    assert captured_params[0]["pins_out"] == ["A:double"]
    assert isinstance(captured_params[0]["pins_in"], list)
    assert isinstance(captured_params[0]["pins_out"], list)


def test_contract_param_helpers_normalize_nested_json_arrays() -> None:
    from dataclasses import replace

    materialization = materialize_planner_worker_contract_request(
        PROBE._canonical_planner_request()
    )
    workflow_contract = PROBE.load_workflow_contract_payload(
        materialization.workflow_contract_payload
    )
    initial = workflow_contract.initial_params[0]
    workflow_contract = replace(
        workflow_contract,
        initial_params=(
            replace(
                initial,
                execution_params={
                    **initial.execution_params,
                    "nested": (("a", "b"), {"items": ("c", "d")}),
                },
            ),
        ),
    )

    create_params = PROBE._create_initial_execution_params_from_contract(
        workflow_contract
    )
    acceptance_contract = PROBE._acceptance_source_contract(workflow_contract)
    acceptance_params = acceptance_contract.initial_params[0].execution_params

    assert create_params["nested"] == [["a", "b"], {"items": ["c", "d"]}]
    assert acceptance_params["nested"] == [["a", "b"], {"items": ["c", "d"]}]
    assert isinstance(create_params["nested"], list)
    assert isinstance(create_params["nested"][0], list)
    assert isinstance(create_params["nested"][1]["items"], list)
    assert isinstance(acceptance_params["nested"], list)
    assert isinstance(acceptance_params["nested"][0], list)
    assert isinstance(acceptance_params["nested"][1]["items"], list)


def test_publication_failure_writes_terminal_decision_without_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs = []

    class FakePublication:
        row = {"status": "failed", "failure_reason": "model_timeout"}
        response_payload = None

    def fake_publication(_payload, **kwargs):
        captured_kwargs.append(kwargs)
        return FakePublication()

    _install_publication_path_fakes(
        monkeypatch,
        publication=fake_publication,
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
    row = json.loads((run_dir / "worker_publication_row.json").read_text())

    assert decision["schema"] == "rook.lm7b_decision:v1"
    assert decision["decision"] == "publication_failed"
    assert decision["reason"] == "model_timeout"
    assert decision["worker_retry_enabled"] is False
    assert decision["retry_attempted"] is False
    assert decision["retry_count"] == 0
    assert row["status"] == "failed"
    assert captured_kwargs[0]["decision_guard"] is (
        PROBE._pass1_decision_hidden_answer_failure
    )
    assert not (run_dir / "retry_context.json").exists()
    assert not (run_dir / "worker_publication_rows.json").exists()


def test_hidden_answer_in_rendered_worker_payload_fails_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publication_called = False

    def leaking_request_payload(_context):
        return {"context": {"instructions": "Do not expose A = 42.0;"}}

    def fail_publication(_payload, **_kwargs):
        nonlocal publication_called
        publication_called = True
        raise AssertionError("publication must not run after request leak")

    _install_publication_path_fakes(
        monkeypatch,
        publication=fail_publication,
    )
    monkeypatch.setattr(
        PROBE,
        "render_local_worker_turn_request_payload",
        leaking_request_payload,
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

    assert publication_called is False
    assert decision["decision"] == "gate_failed"
    assert decision["reason"] == "phase_a_hidden_answer_leak"
    assert not (run_dir / "worker_publication_row.json").exists()


def test_published_observation_writes_declined_terminal_without_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakePublication:
        row = {"status": "published"}
        response_payload = {"kind": "observation", "message": "Cannot repair safely."}

    _install_publication_path_fakes(
        monkeypatch,
        publication=lambda _payload, **_kwargs: FakePublication(),
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
    row = json.loads((run_dir / "worker_publication_row.json").read_text())

    assert decision["decision"] == "worker_declined"
    assert decision["reason"] == "worker_observed"
    assert decision["worker_response_kind"] == "observation"
    assert decision["worker_retry_enabled"] is False
    assert decision["retry_attempted"] is False
    assert decision["retry_count"] == 0
    assert row["status"] == "published"
    assert not (run_dir / "retry_context.json").exists()
    assert not (run_dir / "worker_publication_rows.json").exists()
    assert not (run_dir / "worker_action.json").exists()


def test_action_request_apply_rejection_writes_worker_action_and_rejected_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    action_response = {
        "kind": "action_request",
        "action_id": "draft_repair_params",
        "input": {"code": "A = 0.0;", "mode": "replace"},
    }

    class FakePublication:
        row = {"status": "published"}
        response_payload = action_response

    def fail_dispatch(**_kwargs):
        raise AssertionError("repair dispatch should not run after apply rejection")

    _install_publication_path_fakes(
        monkeypatch,
        publication=lambda _payload, **_kwargs: FakePublication(),
    )
    monkeypatch.setattr(PROBE, "_dispatch_repair_and_verify", fail_dispatch)

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
    worker_action = json.loads((run_dir / "worker_action.json").read_text())

    assert worker_action == action_response
    assert decision["schema"] == "rook.lm7b_decision:v1"
    assert decision["decision"] == "rejected"
    assert decision["reason"] == "worker_action_apply_failed:invalid_mode"
    assert decision["phase"] == "worker_action_apply"
    assert decision["worker_action_id"] == "draft_repair_params"
    assert decision["worker_action_input_sha256"]
    assert decision["worker_action_input_full_path"].endswith("worker_action.json")
    assert decision["worker_action_apply"] == {
        "applied": False,
        "params_sha256": None,
        "reason": "invalid_mode",
    }
    assert decision["worker_retry_enabled"] is False
    assert decision["retry_attempted"] is False
    assert decision["retry_count"] == 0
    assert not (run_dir / "live_repair_summary.json").exists()


def test_action_request_success_dispatches_repair_verify_and_writes_final_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    action_response = {
        "kind": "action_request",
        "action_id": "draft_repair_params",
        "input": {"code": "A = 0.0;", "mode": "body"},
    }
    dispatch_calls = []

    class FakePublication:
        row = {"status": "published"}
        response_payload = action_response

    def fake_dispatch(**kwargs):
        dispatch_calls.append(kwargs)
        return {
            "decision": {
                "schema": "rook.lm6a_decision:v1",
                "decision": "accepted",
                "reason": "verify_repair_passed",
                "phase": "verify_repair",
                "live_repair_dispatched": True,
                "verify_repair_ran": True,
            }
        }

    _install_publication_path_fakes(
        monkeypatch,
        publication=lambda _payload, **_kwargs: FakePublication(),
    )
    monkeypatch.setattr(PROBE, "_dispatch_repair_and_verify", fake_dispatch)

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

    assert len(dispatch_calls) == 1
    assert dispatch_calls[0]["params_sha256"]
    assert dispatch_calls[0]["action_context"]["worker_action_id"] == (
        "draft_repair_params"
    )
    assert decision["schema"] == "rook.lm7b_decision:v1"
    assert decision["decision"] == "accepted"
    assert decision["reason"] == "verify_repair_passed"
    assert decision["phase"] == "verify_repair"
    assert decision["live_repair_dispatched"] is True
    assert decision["verify_repair_ran"] is True
    assert decision["worker_retry_enabled"] is False
    assert decision["retry_attempted"] is False
    assert decision["retry_count"] == 0
    assert (run_dir / "worker_action.json").exists()
    assert not (run_dir / "retry_context.json").exists()


def _install_publication_path_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    publication,
) -> None:
    monkeypatch.setattr(
        PROBE,
        "_run_live_create_and_verify",
        lambda **_kwargs: _real_live(),
    )
    monkeypatch.setattr(
        PROBE,
        "validate_worker_visible_source_routing",
        lambda *_args, **_kwargs: _valid_routing_report(),
    )
    monkeypatch.setattr(PROBE, "run_two_pass_worker_publication", publication)


def _valid_routing_report() -> WorkerVisibleSourceRoutingValidationReport:
    return WorkerVisibleSourceRoutingValidationReport(
        schema=SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA,
        valid=True,
        routability_evaluated=True,
        static_diagnostics=(),
        routability_diagnostics=(),
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
