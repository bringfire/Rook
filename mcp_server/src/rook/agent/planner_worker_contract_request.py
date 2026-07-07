from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA = "rook.planner_worker_contract_request:v1"
WORKFLOW_CONTRACT_SCHEMA = "rook.workflow_contract:v1"
SOURCE_ROUTING_SCHEMA = "rook.worker_visible_source_routing:v1"
LM7A_TEMPLATE_ID = "repair_same_component_from_create_error"
LM7A_WORKER_NODE_ID = "repair_same_component"

CREATE_NODE_ID = "create_script"
VERIFY_CREATE_NODE_ID = "verify_create"
REPAIR_NODE_ID = "repair_same_component"
VERIFY_REPAIR_NODE_ID = "verify_repair"
DONE_NODE_ID = "done"

LM7A_WORKFLOW_ID = "lm7a_repair_same_component_from_create_error"
LEGACY_TEMPLATE_ID = "gh_csharp_create_verify_repair_verify"

LOCKED_REPAIR_ROUTE_IDS = (
    "repair_pin_contract",
    "repair_expected_outcome",
    "repair_target_diagnostics",
    "repair_body_mode_convention",
)
ROUTE_DELTA_PERMISSIONS = {
    route_id: {
        "enable": False,
        "disable": False,
        "set_required": False,
    }
    for route_id in LOCKED_REPAIR_ROUTE_IDS
}
MISSING_DESIRED_OUTPUT_ROUTE_ID = "missing_desired_output_value"
DESIRED_OUTPUT_VALUE_INTENT_ID = "desired_output_value"

PIN_SOURCE_PATH = "create_script.initial_execution_params.pins_out"
VERIFY_SOURCE_PATH = "workflow_contract.rules.verify_repair.expected_outcome"
DIAGNOSTIC_SOURCE_PATH = "create_script.receipt.script_receipt.repair_anchor.target_errors"
CONVENTION_SOURCE_PATH = "script_body_gotcha"
PLANNER_INTENT_SOURCE_PATH = "planner.intent.desired_output_value"

HIDDEN_ANSWER_MARKERS = (
    "PROBE_REPAIR_CODE",
    "A = 42.0",
    "repair_same_component.bind.base_params",
    "BindStepSpec.base_params",
    "BindStepSpec.base_params.code",
)

_REQUEST_FIELDS = frozenset(
    {"schema", "template_id", "initial_params", "routing_delta", "intent_slots"}
)

_ROUTE_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class PlannerRequestDiagnostic:
    severity: str
    code: str
    phase: str
    message: str
    path: str | None = None
    template_id: str | None = None
    node_id: str | None = None
    route_id: str | None = None
    intent_id: str | None = None
    source_class: str | None = None
    source_path: str | None = None
    purpose: str | None = None


@dataclass(frozen=True)
class PlannerWorkerContractMaterialization:
    request_payload: Mapping[str, Any]
    workflow_contract_payload: Mapping[str, Any] | None
    resolved_routing_artifact: Mapping[str, Any] | None
    worker_node_ids: tuple[str, ...]
    diagnostics: tuple[PlannerRequestDiagnostic, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "worker_node_ids", tuple(self.worker_node_ids))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


def materialize_planner_worker_contract_request(
    payload: Mapping[str, Any],
) -> PlannerWorkerContractMaterialization:
    request_copy = _json_copy(payload) if isinstance(payload, Mapping) else {}
    diagnostics = _request_diagnostics(payload)
    if _has_errors(diagnostics):
        return PlannerWorkerContractMaterialization(
            request_payload=request_copy,
            workflow_contract_payload=None,
            resolved_routing_artifact=None,
            worker_node_ids=(),
            diagnostics=tuple(diagnostics),
        )

    pins_out = list(payload["initial_params"][CREATE_NODE_ID]["pins_out"])
    contract_payload = _workflow_contract_payload(pins_out)
    routing_artifact, routing_diagnostics = _resolved_routing_artifact(
        payload["routing_delta"]
    )
    intent_diagnostics = _intent_diagnostics(
        payload["intent_slots"], routing_artifact
    )
    all_diagnostics = tuple(diagnostics + routing_diagnostics + intent_diagnostics)
    if _has_errors(list(all_diagnostics)):
        return PlannerWorkerContractMaterialization(
            request_payload=request_copy,
            workflow_contract_payload=None,
            resolved_routing_artifact=None,
            worker_node_ids=(),
            diagnostics=all_diagnostics,
        )
    return PlannerWorkerContractMaterialization(
        request_payload=request_copy,
        workflow_contract_payload=contract_payload,
        resolved_routing_artifact=routing_artifact,
        worker_node_ids=(LM7A_WORKER_NODE_ID,),
        diagnostics=all_diagnostics,
    )


def _request_diagnostics(payload: Any) -> list[PlannerRequestDiagnostic]:
    diagnostics: list[PlannerRequestDiagnostic] = []
    if not isinstance(payload, Mapping):
        return [
            _diagnostic(
                "invalid_schema",
                "request",
                "Planner worker contract request must be a mapping.",
            )
        ]
    if payload.get("schema") != PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA:
        diagnostics.append(
            _diagnostic(
                "invalid_schema",
                "request",
                "Planner worker contract request schema is invalid.",
                path="schema",
            )
        )
    unknown = _sorted_unknown_fields(payload, _REQUEST_FIELDS)
    for field in unknown:
        diagnostics.append(
            _diagnostic(
                "unknown_field",
                "request",
                f"Unknown top-level field: {field}.",
                path=str(field),
            )
        )
    if payload.get("template_id") != LM7A_TEMPLATE_ID:
        diagnostics.append(
            _diagnostic(
                "unknown_template_id",
                "template",
                "Unknown planner worker contract template_id.",
                path="template_id",
                template_id=payload.get("template_id")
                if isinstance(payload.get("template_id"), str)
                else None,
            )
        )
    diagnostics.extend(_initial_param_diagnostics(payload.get("initial_params")))
    diagnostics.extend(_routing_delta_shape_diagnostics(payload.get("routing_delta")))
    diagnostics.extend(_intent_slot_shape_diagnostics(payload.get("intent_slots")))
    if _contains_hidden_answer_marker(payload):
        diagnostics.append(
            _diagnostic(
                "hidden_answer_marker",
                "request",
                "Planner-authored payload contains a hidden-answer marker.",
            )
        )
    return diagnostics


def _initial_param_diagnostics(value: Any) -> list[PlannerRequestDiagnostic]:
    diagnostics: list[PlannerRequestDiagnostic] = []
    if not isinstance(value, Mapping):
        return [
            _diagnostic(
                "invalid_initial_params",
                "request",
                "initial_params must be a mapping.",
                path="initial_params",
            )
        ]
    unknown_nodes = _sorted_unknown_fields(value, {CREATE_NODE_ID})
    for node_id in unknown_nodes:
        diagnostics.append(
            _diagnostic(
                "undeclared_initial_param",
                "request",
                "initial_params contains an undeclared node.",
                path=f"initial_params.{node_id}",
                node_id=node_id if isinstance(node_id, str) else None,
            )
        )
    create_params = value.get(CREATE_NODE_ID)
    if not isinstance(create_params, Mapping):
        diagnostics.append(
            _diagnostic(
                "missing_initial_param",
                "request",
                "initial_params.create_script is required.",
                path="initial_params.create_script",
                node_id=CREATE_NODE_ID,
            )
        )
        return diagnostics
    unknown_fields = _sorted_unknown_fields(create_params, {"pins_out"})
    for field in unknown_fields:
        diagnostics.append(
            _diagnostic(
                "undeclared_initial_param",
                "request",
                f"create_script initial param is undeclared: {field}.",
                path=f"initial_params.create_script.{field}",
                node_id=CREATE_NODE_ID,
            )
        )
    pins_out = create_params.get("pins_out")
    if pins_out != ["A:double"]:
        diagnostics.append(
            _diagnostic(
                "invalid_initial_params",
                "request",
                "create_script.pins_out must equal ['A:double'] in LM7A.",
                path="initial_params.create_script.pins_out",
                node_id=CREATE_NODE_ID,
            )
        )
    return diagnostics


def _routing_delta_shape_diagnostics(value: Any) -> list[PlannerRequestDiagnostic]:
    if not isinstance(value, Mapping):
        return [
            _diagnostic(
                "invalid_routing_delta",
                "request",
                "routing_delta must be a mapping.",
                path="routing_delta",
            )
        ]
    diagnostics: list[PlannerRequestDiagnostic] = []
    expected_fields = {
        "enable_routes",
        "disable_routes",
        "set_required",
        "add_unresolved_intent_routes",
    }
    for field in _sorted_unknown_fields(value, expected_fields):
        diagnostics.append(
            _diagnostic(
                "invalid_routing_delta",
                "request",
                f"Unknown routing_delta field: {field}.",
                path=f"routing_delta.{field}",
            )
        )
    enable_routes = value.get("enable_routes")
    if not isinstance(enable_routes, list):
        diagnostics.append(
            _diagnostic(
                "invalid_routing_delta",
                "request",
                "routing_delta.enable_routes must be a list.",
                path="routing_delta.enable_routes",
            )
        )
    else:
        diagnostics.extend(
            _route_id_list_entry_diagnostics("enable_routes", enable_routes)
        )
    disable_routes = value.get("disable_routes")
    if not isinstance(disable_routes, list):
        diagnostics.append(
            _diagnostic(
                "invalid_routing_delta",
                "request",
                "routing_delta.disable_routes must be a list.",
                path="routing_delta.disable_routes",
            )
        )
    else:
        diagnostics.extend(
            _route_id_list_entry_diagnostics("disable_routes", disable_routes)
        )
    if not isinstance(value.get("set_required"), Mapping):
        diagnostics.append(
            _diagnostic(
                "invalid_routing_delta",
                "request",
                "routing_delta.set_required must be a mapping.",
                path="routing_delta.set_required",
            )
        )
    else:
        diagnostics.extend(_set_required_entry_diagnostics(value["set_required"]))
    if not isinstance(value.get("add_unresolved_intent_routes"), list):
        diagnostics.append(
            _diagnostic(
                "invalid_routing_delta",
                "request",
                "routing_delta.add_unresolved_intent_routes must be a list.",
                path="routing_delta.add_unresolved_intent_routes",
            )
        )
    return diagnostics


def _route_id_list_entry_diagnostics(
    field_name: str,
    values: list[Any],
) -> list[PlannerRequestDiagnostic]:
    diagnostics: list[PlannerRequestDiagnostic] = []
    for index, route_id in enumerate(values):
        if not isinstance(route_id, str):
            diagnostics.append(
                _diagnostic(
                    "invalid_routing_delta",
                    "request",
                    f"routing_delta.{field_name} entries must be strings.",
                    path=f"routing_delta.{field_name}[{index}]",
                )
            )
    return diagnostics


def _set_required_entry_diagnostics(
    values: Mapping[Any, Any],
) -> list[PlannerRequestDiagnostic]:
    diagnostics: list[PlannerRequestDiagnostic] = []
    for route_id, required in values.items():
        if not isinstance(route_id, str):
            diagnostics.append(
                _diagnostic(
                    "invalid_routing_delta",
                    "request",
                    "routing_delta.set_required route ids must be strings.",
                    path=f"routing_delta.set_required.{route_id}",
                )
            )
        if not isinstance(required, bool):
            diagnostics.append(
                _diagnostic(
                    "invalid_routing_delta",
                    "request",
                    "routing_delta.set_required values must be booleans.",
                    path=f"routing_delta.set_required.{route_id}",
                )
            )
    return diagnostics


def _intent_slot_shape_diagnostics(value: Any) -> list[PlannerRequestDiagnostic]:
    if not isinstance(value, list):
        return [
            _diagnostic(
                "invalid_intent_slot",
                "request",
                "intent_slots must be a list.",
                path="intent_slots",
            )
        ]
    return []


def _workflow_contract_payload(pins_out: list[str]) -> dict[str, Any]:
    return {
        "schema": WORKFLOW_CONTRACT_SCHEMA,
        "workflow_id": LM7A_WORKFLOW_ID,
        "template": {
            "descriptor": {
                "domain": "grasshopper",
                "operation": "create_verify_repair_verify",
                "language": "csharp",
            },
            "expected_template_id": LEGACY_TEMPLATE_ID,
        },
        "initial_params": [
            {
                "node_id": CREATE_NODE_ID,
                "execution_params": {
                    "code": "A = DefinitelyMissingSymbol;",
                    "pins_in": [],
                    "pins_out": pins_out,
                    "name": "LM7APlannerContract",
                    "x": 360,
                    "y": 1100,
                },
            }
        ],
        "rules": [
            {
                "node_id": CREATE_NODE_ID,
                "steps_by_seen_count": [{"kind": "producer", "node_id": CREATE_NODE_ID}],
            },
            {
                "node_id": VERIFY_CREATE_NODE_ID,
                "steps_by_seen_count": [
                    {
                        "kind": "verifier",
                        "verifier_node_id": VERIFY_CREATE_NODE_ID,
                        "source_node_id": CREATE_NODE_ID,
                        "expected_outcome": "needs_repair",
                    }
                ],
            },
            {
                "node_id": REPAIR_NODE_ID,
                "steps_by_seen_count": [
                    {"kind": "producer", "node_id": REPAIR_NODE_ID}
                ],
            },
            {
                "node_id": VERIFY_REPAIR_NODE_ID,
                "steps_by_seen_count": [
                    {
                        "kind": "verifier",
                        "verifier_node_id": VERIFY_REPAIR_NODE_ID,
                        "source_node_id": REPAIR_NODE_ID,
                        "expected_outcome": "succeeded",
                    }
                ],
            },
        ],
        "terminal_node_ids": [DONE_NODE_ID],
        "expected_refs": [
            {"node_id": CREATE_NODE_ID, "execution_ref": "gh_create_csharp_script:v1"},
            {"node_id": REPAIR_NODE_ID, "execution_ref": "gh_update_script:v1"},
        ],
        "max_steps": 6,
        "metadata": {
            "workflow_label": "LM7A planner repair contract",
            "slice": "LM7A",
        },
    }


def _default_routing_artifact() -> dict[str, Any]:
    return {
        "schema": SOURCE_ROUTING_SCHEMA,
        "routes": [
            {
                "node_id": REPAIR_NODE_ID,
                "visible_sources": [
                    {
                        "route_id": "repair_pin_contract",
                        "source_class": "pin_contract",
                        "source_path": PIN_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "repair_expected_outcome",
                        "source_class": "verifier_outcome",
                        "source_path": VERIFY_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "repair_target_diagnostics",
                        "source_class": "receipt_diagnostic",
                        "source_path": DIAGNOSTIC_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "repair_body_mode_convention",
                        "source_class": "convention",
                        "source_path": CONVENTION_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                ],
            }
        ],
    }


def _resolved_routing_artifact(
    routing_delta: Mapping[str, Any],
) -> tuple[dict[str, Any], list[PlannerRequestDiagnostic]]:
    artifact = _default_routing_artifact()
    diagnostics: list[PlannerRequestDiagnostic] = []
    visible_sources = artifact["routes"][0]["visible_sources"]
    route_ids = {route["route_id"] for route in visible_sources}
    enable_routes = list(routing_delta.get("enable_routes", []))
    disable_routes = list(routing_delta.get("disable_routes", []))
    set_required = dict(routing_delta.get("set_required", {}))

    conflict_ids = sorted(set(enable_routes) & set(disable_routes))
    for route_id in conflict_ids:
        diagnostics.append(
            _diagnostic(
                "conflicting_route_operation",
                "routing",
                "Route cannot appear in both enable_routes and disable_routes.",
                path="routing_delta",
                route_id=route_id,
            )
        )

    for route_id in enable_routes + disable_routes + list(set_required):
        if route_id not in route_ids:
            diagnostics.append(
                _diagnostic(
                    "unknown_route_id",
                    "routing",
                    "Routing delta targets an unknown template route id.",
                    path="routing_delta",
                    route_id=route_id,
                )
            )

    for operation, field_name, route_ids_for_operation in (
        ("enable", "enable_routes", enable_routes),
        ("disable", "disable_routes", disable_routes),
        ("set_required", "set_required", list(set_required)),
    ):
        for route_id in route_ids_for_operation:
            permissions = ROUTE_DELTA_PERMISSIONS.get(route_id)
            if permissions is not None and not permissions[operation]:
                diagnostics.append(
                    _diagnostic(
                        "route_delta_not_allowed",
                        "routing",
                        "Route delta operation is not allowed for this template route.",
                        path=f"routing_delta.{field_name}",
                        route_id=route_id,
                    )
                )

    for route_id in set_required:
        if route_id in disable_routes:
            diagnostics.append(
                _diagnostic(
                    "set_required_on_disabled_route",
                    "routing",
                    "set_required cannot target a disabled route.",
                    path=f"routing_delta.set_required.{route_id}",
                    route_id=route_id,
                )
            )

    added = routing_delta.get("add_unresolved_intent_routes", [])
    seen_added: set[str] = set()
    for index, route in enumerate(added):
        path = f"routing_delta.add_unresolved_intent_routes[{index}]"
        if not isinstance(route, Mapping):
            diagnostics.append(
                _diagnostic(
                    "invalid_unresolved_intent_route",
                    "routing",
                    "Added unresolved-intent route must be a mapping.",
                    path=path,
                )
            )
            continue
        route_id = route.get("route_id")
        if not isinstance(route_id, str) or not _ROUTE_ID_RE.fullmatch(route_id):
            diagnostics.append(
                _diagnostic(
                    "invalid_unresolved_intent_route",
                    "routing",
                    "Added unresolved-intent route has invalid route_id.",
                    path=f"{path}.route_id",
                )
            )
            continue
        if route_id in route_ids:
            diagnostics.append(
                _diagnostic(
                    "added_route_id_collides",
                    "routing",
                    "Added route id collides with a template-default route.",
                    path=f"{path}.route_id",
                    route_id=route_id,
                )
            )
            continue
        if route_id in seen_added:
            diagnostics.append(
                _diagnostic(
                    "duplicate_added_route_id",
                    "routing",
                    "Duplicate added route id.",
                    path=f"{path}.route_id",
                    route_id=route_id,
                )
            )
            continue
        seen_added.add(route_id)
        expected = {
            "route_id": route_id,
            "source_class": "planner_user_intent",
            "source_path": PLANNER_INTENT_SOURCE_PATH,
            "purpose": "unresolved_intent",
            "required": False,
        }
        if route_id != MISSING_DESIRED_OUTPUT_ROUTE_ID or dict(route) != expected:
            diagnostics.append(
                _diagnostic(
                    "invalid_unresolved_intent_route",
                    "routing",
                    "LM7A added routes must be planner_user_intent unresolved_intent.",
                    path=path,
                    route_id=route_id,
                    source_class=route.get("source_class")
                    if isinstance(route.get("source_class"), str)
                    else None,
                    source_path=route.get("source_path")
                    if isinstance(route.get("source_path"), str)
                    else None,
                    purpose=route.get("purpose")
                    if isinstance(route.get("purpose"), str)
                    else None,
                )
            )
            continue
        visible_sources.append(dict(expected))

    return artifact, diagnostics


def _intent_diagnostics(
    intent_slots: list[Mapping[str, Any]],
    routing_artifact: Mapping[str, Any],
) -> list[PlannerRequestDiagnostic]:
    diagnostics: list[PlannerRequestDiagnostic] = []
    seen_ids: set[str] = set()
    slot_ids_by_path: dict[str, str] = {}
    for index, slot in enumerate(intent_slots):
        path = f"intent_slots[{index}]"
        if not isinstance(slot, Mapping):
            diagnostics.append(
                _diagnostic(
                    "invalid_intent_slot",
                    "intent",
                    "Intent slot must be a mapping.",
                    path=path,
                )
            )
            continue
        expected_fields = {"intent_id", "status", "source_path", "description"}
        if set(slot) != expected_fields:
            diagnostics.append(
                _diagnostic(
                    "invalid_intent_slot",
                    "intent",
                    "Intent slot has invalid fields.",
                    path=path,
                )
            )
            continue
        intent_id = slot["intent_id"]
        source_path = slot["source_path"]
        if isinstance(intent_id, str) and intent_id in seen_ids:
            diagnostics.append(
                _diagnostic(
                    "duplicate_intent_id",
                    "intent",
                    "Duplicate intent_id.",
                    path=f"{path}.intent_id",
                    intent_id=intent_id,
                )
            )
            continue
        if (
            not isinstance(intent_id, str)
            or not _ROUTE_ID_RE.fullmatch(intent_id)
            or intent_id != DESIRED_OUTPUT_VALUE_INTENT_ID
            or slot["status"] != "unresolved"
            or source_path != PLANNER_INTENT_SOURCE_PATH
            or not isinstance(slot["description"], str)
            or not slot["description"]
        ):
            diagnostics.append(
                _diagnostic(
                    "invalid_intent_slot",
                    "intent",
                    "Intent slot is invalid for LM7A.",
                    path=path,
                    intent_id=intent_id if isinstance(intent_id, str) else None,
                    source_path=source_path if isinstance(source_path, str) else None,
                )
            )
            continue
        if source_path in slot_ids_by_path:
            diagnostics.append(
                _diagnostic(
                    "invalid_intent_slot",
                    "intent",
                    "Intent slot source_path is already declared for LM7A.",
                    path=f"{path}.source_path",
                    intent_id=intent_id,
                    source_path=source_path,
                )
            )
            continue
        seen_ids.add(intent_id)
        slot_ids_by_path[source_path] = intent_id

    intent_route_paths: set[str] = set()
    for route in routing_artifact["routes"][0]["visible_sources"]:
        if route["purpose"] == "unresolved_intent":
            source_path = route["source_path"]
            intent_route_paths.add(source_path)
            if source_path not in slot_ids_by_path:
                diagnostics.append(
                    _diagnostic(
                        "unresolved_intent_route_missing_slot",
                        "intent",
                        "Unresolved-intent route has no matching intent slot.",
                        route_id=route["route_id"],
                        source_class=route["source_class"],
                        source_path=source_path,
                        purpose=route["purpose"],
                    )
                )

    for source_path, intent_id in slot_ids_by_path.items():
        if source_path not in intent_route_paths:
            diagnostics.append(
                _diagnostic(
                    "intent_slot_not_routed",
                    "intent",
                    "Intent slot is not routed to the worker.",
                    intent_id=intent_id,
                    source_path=source_path,
                    severity="warning",
                )
            )
    return diagnostics


def _contains_hidden_answer_marker(value: Any) -> bool:
    text = json.dumps(_stringify_for_marker_scan(value), separators=(",", ":"))
    return any(marker in text for marker in HIDDEN_ANSWER_MARKERS)


def _sorted_unknown_fields(
    value: Mapping[Any, Any],
    expected_fields: set[str] | frozenset[str],
) -> list[Any]:
    return sorted((field for field in value if field not in expected_fields), key=str)


def _stringify_for_marker_scan(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _stringify_for_marker_scan(nested_value)
            for key, nested_value in value.items()
        }
    if isinstance(value, list):
        return [_stringify_for_marker_scan(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_stringify_for_marker_scan(item) for item in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _has_errors(diagnostics: list[PlannerRequestDiagnostic]) -> bool:
    return any(diagnostic.severity == "error" for diagnostic in diagnostics)


def _diagnostic(
    code: str,
    phase: str,
    message: str,
    *,
    severity: str = "error",
    path: str | None = None,
    template_id: str | None = None,
    node_id: str | None = None,
    route_id: str | None = None,
    intent_id: str | None = None,
    source_class: str | None = None,
    source_path: str | None = None,
    purpose: str | None = None,
) -> PlannerRequestDiagnostic:
    return PlannerRequestDiagnostic(
        severity=severity,
        code=code,
        phase=phase,
        message=message,
        path=path,
        template_id=template_id,
        node_id=node_id,
        route_id=route_id,
        intent_id=intent_id,
        source_class=source_class,
        source_path=source_path,
        purpose=purpose,
    )


def _json_copy(value: Any) -> Any:
    return copy.deepcopy(value)


__all__ = (
    "PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA",
    "LM7A_TEMPLATE_ID",
    "LM7A_WORKER_NODE_ID",
    "PlannerRequestDiagnostic",
    "PlannerWorkerContractMaterialization",
    "materialize_planner_worker_contract_request",
)
