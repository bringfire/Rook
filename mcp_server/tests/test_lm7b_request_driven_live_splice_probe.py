from __future__ import annotations

import importlib.util
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
