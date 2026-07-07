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


def _assert_not_materialized(result):
    assert result.workflow_contract_payload is None
    assert result.resolved_routing_artifact is None
    assert result.worker_node_ids == ()


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
    _assert_not_materialized(result)


def test_invalid_schema_is_rejected():
    request = _valid_request()
    request["schema"] = "rook.other:v1"

    result = materialize_planner_worker_contract_request(request)

    assert "invalid_schema" in _codes(result.diagnostics)
    _assert_not_materialized(result)


def test_unknown_template_id_is_rejected():
    request = _valid_request()
    request["template_id"] = "unknown"

    result = materialize_planner_worker_contract_request(request)

    assert "unknown_template_id" in _codes(result.diagnostics)
    _assert_not_materialized(result)


def test_unknown_field_is_rejected():
    request = _valid_request()
    request["surprise"] = True

    result = materialize_planner_worker_contract_request(request)

    assert "unknown_field" in _codes(result.diagnostics)
    _assert_not_materialized(result)


def test_unknown_top_level_non_comparable_key_reports_diagnostic_without_crashing():
    request = _valid_request()
    request[("tuple", "key")] = True

    result = materialize_planner_worker_contract_request(request)

    diagnostic = _diagnostics_by_code(result.diagnostics, "unknown_field")[0]
    assert diagnostic.path == "('tuple', 'key')"
    _assert_not_materialized(result)


def test_missing_initial_param_is_rejected():
    request = _valid_request()
    request["initial_params"] = {}

    result = materialize_planner_worker_contract_request(request)

    assert "missing_initial_param" in _codes(result.diagnostics)
    _assert_not_materialized(result)


def test_undeclared_initial_param_is_rejected():
    request = _valid_request()
    request["initial_params"]["extra_node"] = {"pins_out": ["A:double"]}

    result = materialize_planner_worker_contract_request(request)

    assert "undeclared_initial_param" in _codes(result.diagnostics)
    _assert_not_materialized(result)


def test_hidden_code_under_create_script_reports_undeclared_initial_param():
    request = _valid_request()
    request["initial_params"]["create_script"]["code"] = "A = 42.0"

    result = materialize_planner_worker_contract_request(request)

    assert "undeclared_initial_param" in _codes(result.diagnostics)
    assert "hidden_answer_marker" in _codes(result.diagnostics)
    _assert_not_materialized(result)


@pytest.mark.parametrize("field_name", ["disable_routes", "enable_routes"])
def test_route_delta_not_allowed_for_route_lists(field_name):
    request = _valid_request()
    request["routing_delta"][field_name] = ["repair_pin_contract"]

    result = materialize_planner_worker_contract_request(request)

    diagnostic = _diagnostics_by_code(result.diagnostics, "route_delta_not_allowed")[0]
    assert diagnostic.route_id == "repair_pin_contract"
    assert diagnostic.path == f"routing_delta.{field_name}"
    _assert_not_materialized(result)


def test_route_delta_not_allowed_for_set_required():
    request = _valid_request()
    request["routing_delta"]["set_required"] = {"repair_pin_contract": False}

    result = materialize_planner_worker_contract_request(request)

    diagnostic = _diagnostics_by_code(result.diagnostics, "route_delta_not_allowed")[0]
    assert diagnostic.route_id == "repair_pin_contract"
    assert diagnostic.path == "routing_delta.set_required"
    _assert_not_materialized(result)


def test_conflicting_route_operation_is_rejected():
    request = _valid_request()
    request["routing_delta"]["enable_routes"] = ["repair_pin_contract"]
    request["routing_delta"]["disable_routes"] = ["repair_pin_contract"]

    result = materialize_planner_worker_contract_request(request)

    assert "conflicting_route_operation" in _codes(result.diagnostics)
    _assert_not_materialized(result)


def test_unknown_route_id_is_rejected():
    request = _valid_request()
    request["routing_delta"]["enable_routes"] = ["not_a_template_route"]

    result = materialize_planner_worker_contract_request(request)

    diagnostic = _diagnostics_by_code(result.diagnostics, "unknown_route_id")[0]
    assert diagnostic.route_id == "not_a_template_route"
    _assert_not_materialized(result)


def test_set_required_on_disabled_route_is_rejected():
    request = _valid_request()
    request["routing_delta"]["disable_routes"] = ["repair_pin_contract"]
    request["routing_delta"]["set_required"] = {"repair_pin_contract": True}

    result = materialize_planner_worker_contract_request(request)

    assert "set_required_on_disabled_route" in _codes(result.diagnostics)
    _assert_not_materialized(result)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("purpose", "acceptance_criteria"),
        ("source_path", "planner.intent.other"),
    ],
)
def test_invalid_unresolved_intent_route_is_rejected(field_name, value):
    request = _valid_request()
    request["routing_delta"]["add_unresolved_intent_routes"][0][field_name] = value

    routing_artifact, routing_diagnostics = module._resolved_routing_artifact(
        request["routing_delta"]
    )
    result = materialize_planner_worker_contract_request(request)

    visible_sources = routing_artifact["routes"][0]["visible_sources"]
    assert "invalid_unresolved_intent_route" in _codes(routing_diagnostics)
    assert [route["route_id"] for route in visible_sources].count(
        "missing_desired_output_value"
    ) == 0
    assert "invalid_unresolved_intent_route" in _codes(result.diagnostics)
    _assert_not_materialized(result)


def test_added_unresolved_intent_route_requires_canonical_route_id():
    request = _valid_request()
    request["routing_delta"]["add_unresolved_intent_routes"][0][
        "route_id"
    ] = "other_missing_value"

    result = materialize_planner_worker_contract_request(request)

    diagnostic = _diagnostics_by_code(
        result.diagnostics, "invalid_unresolved_intent_route"
    )[0]
    assert diagnostic.route_id == "other_missing_value"
    _assert_not_materialized(result)


def test_duplicate_added_route_id_is_rejected_and_not_appended_twice():
    request = _valid_request()
    request["routing_delta"]["add_unresolved_intent_routes"].append(
        copy.deepcopy(request["routing_delta"]["add_unresolved_intent_routes"][0])
    )

    routing_artifact, routing_diagnostics = module._resolved_routing_artifact(
        request["routing_delta"]
    )
    result = materialize_planner_worker_contract_request(request)

    assert "duplicate_added_route_id" in _codes(routing_diagnostics)
    visible_sources = routing_artifact["routes"][0]["visible_sources"]
    assert [route["route_id"] for route in visible_sources].count(
        "missing_desired_output_value"
    ) == 1
    assert "duplicate_added_route_id" in _codes(result.diagnostics)
    _assert_not_materialized(result)


def test_added_route_id_collides_is_rejected_and_not_appended():
    request = _valid_request()
    request["routing_delta"]["add_unresolved_intent_routes"][0][
        "route_id"
    ] = "repair_pin_contract"

    routing_artifact, routing_diagnostics = module._resolved_routing_artifact(
        request["routing_delta"]
    )
    result = materialize_planner_worker_contract_request(request)

    assert "added_route_id_collides" in _codes(routing_diagnostics)
    visible_sources = routing_artifact["routes"][0]["visible_sources"]
    assert [route["route_id"] for route in visible_sources].count(
        "repair_pin_contract"
    ) == 1
    assert "added_route_id_collides" in _codes(result.diagnostics)
    _assert_not_materialized(result)


def test_unresolved_intent_route_missing_slot_is_rejected_when_slots_are_empty():
    request = _valid_request()
    request["intent_slots"] = []

    result = materialize_planner_worker_contract_request(request)

    assert "unresolved_intent_route_missing_slot" in _codes(result.diagnostics)
    _assert_not_materialized(result)


def test_invalid_intent_slot_is_rejected():
    request = _valid_request()
    request["intent_slots"][0]["status"] = "resolved"

    result = materialize_planner_worker_contract_request(request)

    assert "invalid_intent_slot" in _codes(result.diagnostics)
    _assert_not_materialized(result)


def test_intent_slot_requires_canonical_intent_id():
    request = _valid_request()
    request["intent_slots"][0]["intent_id"] = "other_desired_output"

    result = materialize_planner_worker_contract_request(request)

    diagnostic = _diagnostics_by_code(result.diagnostics, "invalid_intent_slot")[0]
    assert diagnostic.intent_id == "other_desired_output"
    _assert_not_materialized(result)


def test_second_intent_slot_for_canonical_source_path_is_rejected():
    request = _valid_request()
    duplicate_path = copy.deepcopy(request["intent_slots"][0])
    duplicate_path["intent_id"] = "other_desired_output"
    request["intent_slots"].append(duplicate_path)

    result = materialize_planner_worker_contract_request(request)

    diagnostic = _diagnostics_by_code(result.diagnostics, "invalid_intent_slot")[0]
    assert diagnostic.intent_id == "other_desired_output"
    assert "unresolved_intent_route_missing_slot" not in _codes(result.diagnostics)
    _assert_not_materialized(result)


def test_duplicate_intent_id_is_rejected_and_does_not_overwrite_routed_slot():
    request = _valid_request()
    duplicate = copy.deepcopy(request["intent_slots"][0])
    duplicate["source_path"] = "planner.intent.other"
    request["intent_slots"].append(duplicate)

    result = materialize_planner_worker_contract_request(request)

    assert "duplicate_intent_id" in _codes(result.diagnostics)
    assert "unresolved_intent_route_missing_slot" not in _codes(result.diagnostics)
    _assert_not_materialized(result)


def test_intent_slot_without_route_warns_but_materialization_remains_valid():
    request = _valid_request()
    request["routing_delta"]["add_unresolved_intent_routes"] = []

    result = materialize_planner_worker_contract_request(request)

    diagnostic = _diagnostics_by_code(result.diagnostics, "intent_slot_not_routed")[0]
    assert diagnostic.severity == "warning"
    assert not any(diagnostic.severity == "error" for diagnostic in result.diagnostics)
    assert result.workflow_contract_payload is not None
    assert result.resolved_routing_artifact is not None
    assert result.worker_node_ids == ("repair_same_component",)


@pytest.mark.parametrize(
    "marker",
    [
        "PROBE_REPAIR_CODE",
        "A = 42.0",
        "repair_same_component.bind.base_params",
        "BindStepSpec.base_params",
        "BindStepSpec.base_params.code",
    ],
)
def test_hidden_answer_markers_are_rejected(marker):
    request = _valid_request()
    request["initial_params"]["create_script"]["note"] = marker

    result = materialize_planner_worker_contract_request(request)

    assert "hidden_answer_marker" in _codes(result.diagnostics)
    _assert_not_materialized(result)
