from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from rook.agent.local_worker_source_routing_validator import (
    validate_worker_visible_source_routing,
)


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm6a_live_worker_splice_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm6a_live_worker_splice_probe",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()


def test_cli_defaults_are_canonical() -> None:
    args = PROBE._args([])
    assert args.phase == "full"
    assert args.model == "gemma4:12b-it-qat"
    assert args.endpoint == "http://localhost:11434/api/chat"
    assert args.temperature == 0


def test_cli_receipt_recon_phase() -> None:
    args = PROBE._args(["--phase", "receipt_recon"])
    assert args.phase == "receipt_recon"


def test_bind_free_contract_removes_only_repair_bind_step() -> None:
    contract = PROBE._lm6a_bind_free_contract()
    repair_rules = [
        rule for rule in contract.rules if rule.node_id == "repair_same_component"
    ]
    assert len(repair_rules) == 1
    repair_rule = repair_rules[0]
    assert len(repair_rule.steps_by_seen_count) == 1
    assert repair_rule.steps_by_seen_count[0].node_id == "repair_same_component"
    assert repair_rule.steps_by_seen_count[0].__class__.__name__ == "ProducerStepSpec"


def test_bind_free_contract_keeps_node_identities_and_refs() -> None:
    contract = PROBE._lm6a_bind_free_contract()

    assert [initial.node_id for initial in contract.initial_params] == ["create_script"]
    assert {rule.node_id for rule in contract.rules} == {
        "create_script",
        "verify_create",
        "repair_same_component",
        "verify_repair",
    }
    assert {ref.node_id: ref.execution_ref for ref in contract.expected_refs} == {
        "create_script": "gh_create_csharp_script:v1",
        "repair_same_component": "gh_update_script:v1",
    }


def test_bind_free_contract_contains_no_hidden_repair_answer() -> None:
    rendered = json.dumps(
        PROBE._contract_to_jsonable(PROBE._lm6a_bind_free_contract()),
        sort_keys=True,
    )
    assert "PROBE_REPAIR_CODE" not in rendered
    assert "A = 42.0" not in rendered
    assert "base_params" not in rendered


def test_routing_artifact_is_static_valid() -> None:
    report = validate_worker_visible_source_routing(PROBE._LM6A_ROUTING_ARTIFACT)
    assert report.valid is True
    assert report.routability_evaluated is False
    assert report.static_diagnostics == ()


def test_worker_visible_acceptance_criteria_projection_excludes_lm5w_metadata() -> None:
    packet = {
        "schema": "rook.acceptance_criteria_packet:v1",
        "source_set": {"source_classes": ["pin_contract"], "source_paths": ["x"]},
        "criteria": [
            {
                "criterion_id": "output_a_assigned",
                "description": "Output A must be assigned.",
                "source": "create_script.initial_execution_params.pins_out",
                "source_class": "pin_contract",
            }
        ],
        "unresolved_intent": [],
        "fingerprint": "sha256:demo",
    }

    visible = PROBE._legacy_acceptance_criteria_projection(packet)

    assert visible == {
        "source": PROBE.ACCEPTANCE_CRITERIA_LEGACY_SOURCE,
        "criteria": [
            {
                "criterion_id": "output_a_assigned",
                "description": "Output A must be assigned.",
                "source": "create_script.initial_execution_params.pins_out",
            }
        ],
    }
    rendered = json.dumps(visible, sort_keys=True)
    assert "source_class" not in rendered
    assert "source_set" not in rendered
    assert "fingerprint" not in rendered
    assert "rook.acceptance_criteria_packet:v1" not in rendered


def test_decision_for_gate_failed_is_bounded() -> None:
    decision = PROBE._decision_record(
        decision="gate_failed",
        reason="phase_a_routability_failed",
        phase="receipt_recon",
    )

    assert decision["decision"] == "gate_failed"
    assert decision["reason"] == "phase_a_routability_failed"
    assert decision["live_repair_dispatched"] is False
    assert decision["verify_repair_ran"] is False
    rendered = json.dumps(decision, sort_keys=True)
    assert "A = 42.0" not in rendered
    assert "PROBE_REPAIR_CODE" not in rendered


def test_hidden_answer_scan_rejects_visible_leak() -> None:
    assert PROBE._hidden_answer_leaks({"code": "A = 42.0;"}) == ["A = 42.0"]
    assert PROBE._hidden_answer_leaks({"text": "PROBE_REPAIR_CODE"}) == [
        "PROBE_REPAIR_CODE"
    ]
    assert PROBE._hidden_answer_leaks({"code": "A = 0.0;"}) == []


def test_phase_a_gate_fails_when_routability_not_evaluated(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class _Report:
        valid = True
        routability_evaluated = False
        static_diagnostics = ()
        routability_diagnostics = ()

    monkeypatch.setattr(
        PROBE,
        "_run_live_create_and_verify",
        lambda *args, **kwargs: {
            "graph": object(),
            "workflow_contract": PROBE._lm6a_bind_free_contract(),
            "convention_packets": (),
            "live_create_summary": {},
            "verify_create_summary": {},
        },
    )
    monkeypatch.setattr(
        PROBE,
        "validate_worker_visible_source_routing",
        lambda *args, **kwargs: _Report(),
    )

    recon = PROBE._run_phase_a_recon(run_dir=tmp_path, agent=None)

    assert recon["decision"]["decision"] == "gate_failed"
    assert recon["decision"]["reason"] == "phase_a_routability_not_evaluated"


def _published_payload(kind: str, **extra) -> dict:
    payload = {"schema": "rook.local_worker_turn_response:v1", "kind": kind}
    payload.update(extra)
    return payload


def test_publication_failed_decision_for_invalid_publication() -> None:
    decision = PROBE._decision_from_worker_publication(
        publication_row={"status": "pass2_lm5g_invalid", "failure_reason": "bad"},
        response_payload=None,
    )

    assert decision["decision"] == "publication_failed"
    assert decision["reason"] == "bad"
    assert decision["live_repair_dispatched"] is False


def test_worker_declined_clarification() -> None:
    decision = PROBE._decision_from_worker_publication(
        publication_row={
            "status": "published",
            "observation_action_intent_anomaly": False,
            "observation_action_intent_reasons": [],
        },
        response_payload=_published_payload(
            "clarification_request",
            question="Need desired value?",
            rationale=None,
        ),
    )

    assert decision["decision"] == "worker_declined"
    assert decision["reason"] == "worker_clarified"


def test_worker_declined_observation_anomaly() -> None:
    decision = PROBE._decision_from_worker_publication(
        publication_row={
            "status": "published",
            "observation_action_intent_anomaly": True,
            "observation_action_intent_reasons": [
                "observation_data_action_id_allowed"
            ],
        },
        response_payload=_published_payload("observation", message="x", data=None),
    )

    assert decision["decision"] == "worker_declined"
    assert decision["reason"] == "worker_observation_action_intent_anomaly"


def test_worker_action_apply_failure_maps_to_rejected() -> None:
    class _ApplyResult:
        applied = False
        reason = "invalid_mode"
        params_sha256 = None

    decision = PROBE._decision_from_worker_action_apply(_ApplyResult())

    assert decision["decision"] == "rejected"
    assert decision["reason"] == "worker_action_apply_failed:invalid_mode"
    assert decision["live_repair_dispatched"] is False
    assert decision["verify_repair_ran"] is False
