from __future__ import annotations

import json

import pytest

import rook.agent.workflow_validate as workflow_validate_module
from rook.agent.local_worker_source_routing_validator import (
    SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA,
    SourceRoutingDiagnostic,
    WorkerVisibleSourceRoutingValidationReport,
)
from rook.agent.planner_worker_contract_request import (
    LM7A_TEMPLATE_ID,
    PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA,
)
from rook.agent.workflow_validate import (
    WORKFLOW_VALIDATE_REPORT_SCHEMA,
    validate_planner_worker_contract_request,
)


def _valid_request() -> dict:
    return {
        "schema": PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA,
        "template_id": LM7A_TEMPLATE_ID,
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


def _codes(report, phase):
    return [diagnostic["code"] for diagnostic in report["phases"][phase]["diagnostics"]]


def test_workflow_validate_happy_path_report_shape():
    report = validate_planner_worker_contract_request(_valid_request())

    assert report["schema"] == WORKFLOW_VALIDATE_REPORT_SCHEMA
    assert report["valid"] is True
    assert report["request_schema"] == PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA
    assert report["template_id"] == LM7A_TEMPLATE_ID
    assert report["request_fingerprint"].startswith("sha256:")
    assert report["report_fingerprint"].startswith("sha256:")
    assert set(report["phases"]) == {
        "request",
        "template",
        "contract",
        "routing",
        "intent",
    }
    assert report["phases"]["routing"]["source_routing_report"]["schema"] == (
        SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA
    )
    assert report["phases"]["routing"]["source_routing_report"][
        "routability_evaluated"
    ] is False
    assert report["resolved"]["workflow_contract_schema"] == "rook.workflow_contract:v1"
    assert report["resolved"]["routing_schema"] == "rook.worker_visible_source_routing:v1"
    assert report["resolved"]["worker_nodes"] == ["repair_same_component"]


def test_lm5aa_static_routing_failure_is_surfaced(monkeypatch):
    def fake_validate(_artifact):
        return WorkerVisibleSourceRoutingValidationReport(
            schema=SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA,
            valid=False,
            routability_evaluated=False,
            static_diagnostics=(
                SourceRoutingDiagnostic(
                    severity="error",
                    code="unknown_source_class",
                    node_id="repair_same_component",
                    route_id="repair_pin_contract",
                    source_class="unknown",
                    source_path="create_script.initial_execution_params.pins_out",
                    purpose="acceptance_criteria",
                    message="Unknown source class.",
                ),
            ),
            routability_diagnostics=(),
        )

    monkeypatch.setattr(
        workflow_validate_module,
        "validate_worker_visible_source_routing",
        fake_validate,
    )

    report = validate_planner_worker_contract_request(_valid_request())

    assert report["valid"] is False
    assert "unknown_source_class" in _codes(report, "routing")
    assert report["phases"]["routing"]["source_routing_report"]["valid"] is False


def test_report_fingerprint_is_stable_against_input_dict_order():
    request = _valid_request()
    reordered = {
        "intent_slots": request["intent_slots"],
        "routing_delta": request["routing_delta"],
        "initial_params": request["initial_params"],
        "template_id": request["template_id"],
        "schema": request["schema"],
    }

    first = validate_planner_worker_contract_request(request)
    second = validate_planner_worker_contract_request(reordered)

    assert first["request_fingerprint"] == second["request_fingerprint"]
    assert first["report_fingerprint"] == second["report_fingerprint"]


def test_malformed_request_with_mixed_key_types_reports_diagnostics():
    request = {"schema": "wrong", 1: "x"}

    report = validate_planner_worker_contract_request(request)

    assert report["valid"] is False
    assert "invalid_schema" in _codes(report, "request")
    assert "unknown_field" in _codes(report, "request")
    assert report["request_fingerprint"].startswith("sha256:")


def test_report_valid_false_when_request_has_error():
    request = _valid_request()
    request["schema"] = "wrong"

    report = validate_planner_worker_contract_request(request)

    assert report["valid"] is False
    assert "invalid_schema" in _codes(report, "request")


def test_intent_warning_does_not_block_validity():
    request = _valid_request()
    request["routing_delta"]["add_unresolved_intent_routes"] = []

    report = validate_planner_worker_contract_request(request)

    assert report["valid"] is True
    assert "intent_slot_not_routed" in _codes(report, "intent")
    assert report["phases"]["intent"]["diagnostics"][0]["severity"] == "warning"


def test_contract_phase_warns_when_routing_error_prevents_evaluation():
    request = _valid_request()
    request["routing_delta"]["enable_routes"] = ["missing_route"]

    report = validate_planner_worker_contract_request(request)

    assert report["valid"] is False
    assert report["phases"]["contract"]["valid"] is True
    assert "unknown_route_id" in _codes(report, "routing")
    assert "contract_not_evaluated" in _codes(report, "contract")
    assert report["phases"]["contract"]["diagnostics"][0]["severity"] == "warning"
    assert report["resolved"]["workflow_contract_fingerprint"] is None
