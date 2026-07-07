from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from rook.agent import planner_worker_contract_request as module
from rook.agent.planner_worker_contract_request import (
    LM7A_TEMPLATE_ID,
    LM7A_WORKER_NODE_ID,
    PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA,
    materialize_planner_worker_contract_request,
)


def _valid_request() -> dict:
    return {
        "schema": PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA,
        "template_id": LM7A_TEMPLATE_ID,
        "initial_params": {
            "create_script": {
                "pins_out": ["A:double"],
            },
        },
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


def _codes(diagnostics):
    return [diagnostic.code for diagnostic in diagnostics]


def _diagnostics_by_code(diagnostics, code):
    return [diagnostic for diagnostic in diagnostics if diagnostic.code == code]


def test_public_surface_constants_are_stable():
    assert PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA == (
        "rook.planner_worker_contract_request:v1"
    )
    assert LM7A_TEMPLATE_ID == "repair_same_component_from_create_error"
    assert LM7A_WORKER_NODE_ID == "repair_same_component"
    assert "materialize_planner_worker_contract_request" in module.__all__
    assert "PlannerWorkerContractMaterialization" in module.__all__
    assert "PlannerRequestDiagnostic" in module.__all__


def test_materializes_valid_request_to_contract_and_routing():
    result = materialize_planner_worker_contract_request(_valid_request())

    assert result.diagnostics == ()
    assert result.worker_node_ids == ("repair_same_component",)
    assert result.workflow_contract_payload is not None
    assert result.workflow_contract_payload["schema"] == "rook.workflow_contract:v1"
    assert result.workflow_contract_payload["workflow_id"] == (
        "lm7a_repair_same_component_from_create_error"
    )
    assert result.resolved_routing_artifact is not None
    assert result.resolved_routing_artifact["schema"] == (
        "rook.worker_visible_source_routing:v1"
    )
    visible_sources = result.resolved_routing_artifact["routes"][0]["visible_sources"]
    assert [route["route_id"] for route in visible_sources] == [
        "repair_pin_contract",
        "repair_expected_outcome",
        "repair_target_diagnostics",
        "repair_body_mode_convention",
        "missing_desired_output_value",
    ]


def test_materialization_returns_fresh_containers():
    request = _valid_request()

    first = materialize_planner_worker_contract_request(request)
    second = materialize_planner_worker_contract_request(request)

    assert first.workflow_contract_payload is not second.workflow_contract_payload
    assert first.resolved_routing_artifact is not second.resolved_routing_artifact
    first.resolved_routing_artifact["routes"][0]["visible_sources"][0][
        "required"
    ] = False
    second_first_route = second.resolved_routing_artifact["routes"][0][
        "visible_sources"
    ][0]
    assert second_first_route["required"] is True


def test_non_json_unknown_field_reports_diagnostic_without_crashing():
    request = _valid_request()
    request["unexpected"] = Path("not-json")

    result = materialize_planner_worker_contract_request(request)

    assert "unknown_field" in _codes(result.diagnostics)
    assert result.request_payload["unexpected"] == Path("not-json")


def test_malformed_route_id_list_entries_report_diagnostic_without_crashing():
    request = _valid_request()
    request["routing_delta"]["enable_routes"] = [{}]

    result = materialize_planner_worker_contract_request(request)

    assert "invalid_routing_delta" in _codes(result.diagnostics)
    assert result.workflow_contract_payload is None
    assert result.resolved_routing_artifact is None
