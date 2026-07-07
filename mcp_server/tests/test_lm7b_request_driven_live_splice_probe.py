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

    class FakeMaterialization:
        workflow_contract_payload = {"schema": "rook.workflow_contract:v1"}
        resolved_routing_artifact = {
            "schema": "rook.worker_visible_source_routing:v1"
        }
        worker_node_ids = ("repair_same_component",)
        diagnostics = ()

    def fake_materialize(request):
        captured.append(("materialize", request))
        return FakeMaterialization()

    def fake_live(**_kwargs):
        return {"decision": {"decision": "gate_failed", "reason": "stop_for_test"}}

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
    assert decision["schema"] == "rook.lm7b_decision:v1"
    assert decision["decision"] == "gate_failed"
    assert decision["reason"] == "stop_for_test"
    assert decision["request_fingerprint"] == "sha256:req"
    assert decision["workflow_validate_valid"] is True
    assert decision["workflow_validate_report_fingerprint"] == "sha256:report"
    assert decision["runtime_routing_valid"] is None
    assert decision["runtime_routability_evaluated"] is False
    assert decision["worker_retry_enabled"] is False
    assert decision["live_repair_dispatched"] is False
    assert decision["verify_repair_ran"] is False


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


def test_unsupported_temporary_live_seam_decision_writes_stable_gate_failure(
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

    assert decision["schema"] == "rook.lm7b_decision:v1"
    assert decision["decision"] == "gate_failed"
    assert decision["reason"] == "temporary_live_seam:demo"
    assert decision["request_fingerprint"].startswith("sha256:")
    assert decision["workflow_validate_valid"] is True
    assert decision["workflow_validate_report_fingerprint"].startswith("sha256:")
    assert decision["runtime_routing_valid"] is None
    assert decision["runtime_routability_evaluated"] is False
    assert decision["worker_retry_enabled"] is False
    assert decision["live_repair_dispatched"] is False
    assert decision["verify_repair_ran"] is False
