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
