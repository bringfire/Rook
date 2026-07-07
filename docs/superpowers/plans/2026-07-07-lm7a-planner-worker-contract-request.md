# LM7A Planner Worker Contract Request Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic PlannerWorkerContractRequest v1 loader/materializer and workflow_validate v1 report composer for the LM7A repair fixture, with no model, live Rhino/GH, worker protocol, or runtime dispatch changes.

**Architecture:** Add two small agent-layer modules. `planner_worker_contract_request.py` owns the request schema, template bundle fixture, routing-delta application, intent-slot validation, and contract materialization. `workflow_validate.py` composes that materialization with the existing workflow compiler and LM5AA static routing validator into one versioned report.

**Tech Stack:** Python 3.10, frozen dataclasses, existing `rook.agent.plan_graph_workflow_contract`, existing `rook.agent.local_worker_source_routing_validator`, pytest.

---

## File Structure

Create:

```text
mcp_server/src/rook/agent/planner_worker_contract_request.py
mcp_server/src/rook/agent/workflow_validate.py
mcp_server/tests/test_planner_worker_contract_request.py
mcp_server/tests/test_workflow_validate.py
```

Modify:

```text
docs/superpowers/plans/2026-07-07-lm7a-planner-worker-contract-request.md
```

Do not modify:

```text
mcp_server/src/rook/agent/__init__.py
scripts/lm6a_live_worker_splice_probe.py
scripts/lm6c_repeatability_probe.py
scripts/lm_worker_two_pass_publication.py
mcp_server/src/rook/agent/local_worker_source_routing_validator.py
mcp_server/src/rook/agent/local_worker_acceptance_criteria.py
mcp_server/src/rook/agent/local_worker_acceptance_criteria_sources.py
mcp_server/src/rook/agent/plan_graph_worker_action_apply.py
```

## Public Surface

`planner_worker_contract_request.py` should expose:

```python
PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA = "rook.planner_worker_contract_request:v1"
LM7A_TEMPLATE_ID = "repair_same_component_from_create_error"
LM7A_WORKER_NODE_ID = "repair_same_component"

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

def materialize_planner_worker_contract_request(
    payload: Mapping[str, Any],
) -> PlannerWorkerContractMaterialization:
    raise NotImplementedError
```

`workflow_validate.py` should expose:

```python
WORKFLOW_VALIDATE_REPORT_SCHEMA = "rook.workflow_validate_report:v1"

def validate_planner_worker_contract_request(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    raise NotImplementedError
```

No package-level re-export.

## Diagnostic Codes

Implement these codes exactly, plus any lower-level LM5AA codes embedded in the routing sub-report:

```text
invalid_schema
unknown_field
invalid_template_id
unknown_template_id
invalid_initial_params
missing_initial_param
undeclared_initial_param
hidden_answer_marker
invalid_routing_delta
conflicting_route_operation
unknown_route_id
route_delta_not_allowed
set_required_on_disabled_route
duplicate_added_route_id
added_route_id_collides
invalid_unresolved_intent_route
invalid_intent_slot
duplicate_intent_id
unresolved_intent_route_missing_slot
intent_slot_not_routed
contract_load_failed
contract_compile_failed
worker_bind_step_forbidden
```

Severity vocabulary:

```text
error
warning
```

Phase vocabulary:

```text
request
template
contract
routing
intent
```

## Canonical Constants

Use these exact values in implementation and tests:

```python
CREATE_NODE_ID = "create_script"
VERIFY_CREATE_NODE_ID = "verify_create"
REPAIR_NODE_ID = "repair_same_component"
VERIFY_REPAIR_NODE_ID = "verify_repair"
DONE_NODE_ID = "done"

LM7A_WORKFLOW_ID = "lm7a_repair_same_component_from_create_error"
LM7A_TEMPLATE_ID = "repair_same_component_from_create_error"
LEGACY_TEMPLATE_ID = "gh_csharp_create_verify_repair_verify"
```

Default routing route ids:

```python
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
```

Planner intent route id:

```python
MISSING_DESIRED_OUTPUT_ROUTE_ID = "missing_desired_output_value"
```

Planner intent slot id:

```python
DESIRED_OUTPUT_VALUE_INTENT_ID = "desired_output_value"
```

## Task 1: Request Module Skeleton And Happy-Path Fixture

**Files:**
- Create: `mcp_server/src/rook/agent/planner_worker_contract_request.py`
- Create: `mcp_server/tests/test_planner_worker_contract_request.py`

- [ ] **Step 1: Write failing tests for public constants and canonical fixture helpers**

Create `mcp_server/tests/test_planner_worker_contract_request.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_planner_worker_contract_request.py `
  -q
```

Expected: import failure because `planner_worker_contract_request` does not exist.

- [ ] **Step 3: Create module skeleton and happy-path materializer**

Create `mcp_server/src/rook/agent/planner_worker_contract_request.py`:

```python
from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from rook.agent.plan_graph_workflow_contract import (
    WORKFLOW_CONTRACT_SCHEMA,
)
from rook.agent.local_worker_source_routing_validator import SOURCE_ROUTING_SCHEMA


PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA = "rook.planner_worker_contract_request:v1"
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
    unknown = sorted(set(payload) - _REQUEST_FIELDS)
    for field in unknown:
        diagnostics.append(
            _diagnostic(
                "unknown_field",
                "request",
                f"Unknown top-level field: {field}.",
                path=field,
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
    unknown_nodes = sorted(set(value) - {CREATE_NODE_ID})
    for node_id in unknown_nodes:
        diagnostics.append(
            _diagnostic(
                "undeclared_initial_param",
                "request",
                "initial_params contains an undeclared node.",
                path=f"initial_params.{node_id}",
                node_id=node_id,
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
    unknown_fields = sorted(set(create_params) - {"pins_out"})
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
    for field in sorted(set(value) - expected_fields):
        diagnostics.append(
            _diagnostic(
                "invalid_routing_delta",
                "request",
                f"Unknown routing_delta field: {field}.",
                path=f"routing_delta.{field}",
            )
        )
    if not isinstance(value.get("enable_routes"), list):
        diagnostics.append(
            _diagnostic(
                "invalid_routing_delta",
                "request",
                "routing_delta.enable_routes must be a list.",
                path="routing_delta.enable_routes",
            )
        )
    if not isinstance(value.get("disable_routes"), list):
        diagnostics.append(
            _diagnostic(
                "invalid_routing_delta",
                "request",
                "routing_delta.disable_routes must be a list.",
                path="routing_delta.disable_routes",
            )
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
        seen_added.add(route_id)
        expected = {
            "route_id": route_id,
            "source_class": "planner_user_intent",
            "source_path": PLANNER_INTENT_SOURCE_PATH,
            "purpose": "unresolved_intent",
            "required": False,
        }
        if dict(route) != expected:
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
        if (
            not isinstance(intent_id, str)
            or not _ROUTE_ID_RE.fullmatch(intent_id)
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
        if intent_id in seen_ids:
            diagnostics.append(
                _diagnostic(
                    "duplicate_intent_id",
                    "intent",
                    "Duplicate intent_id.",
                    path=f"{path}.intent_id",
                    intent_id=intent_id,
                )
            )
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
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return any(marker in text for marker in HIDDEN_ANSWER_MARKERS)


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
    return json.loads(json.dumps(copy.deepcopy(value), sort_keys=True))


__all__ = (
    "PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA",
    "LM7A_TEMPLATE_ID",
    "LM7A_WORKER_NODE_ID",
    "PlannerRequestDiagnostic",
    "PlannerWorkerContractMaterialization",
    "materialize_planner_worker_contract_request",
)
```

- [ ] **Step 4: Run tests for Task 1**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_planner_worker_contract_request.py `
  -q
```

Expected: the three Task 1 tests pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add mcp_server\src\rook\agent\planner_worker_contract_request.py `
  mcp_server\tests\test_planner_worker_contract_request.py
git commit -m "feat: add planner worker request materializer"
```

## Task 2: Request Validation Negative Cases

**Files:**
- Modify: `mcp_server/tests/test_planner_worker_contract_request.py`
- Modify: `mcp_server/src/rook/agent/planner_worker_contract_request.py`

- [ ] **Step 1: Add request/routing/intent negative tests**

Append these tests to `mcp_server/tests/test_planner_worker_contract_request.py`:

```python
@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda payload: payload.update({"schema": "wrong"}), "invalid_schema"),
        (
            lambda payload: payload.update({"template_id": "unknown"}),
            "unknown_template_id",
        ),
        (lambda payload: payload.update({"extra": True}), "unknown_field"),
        (
            lambda payload: payload["initial_params"].pop("create_script"),
            "missing_initial_param",
        ),
        (
            lambda payload: payload["initial_params"].update({"other": {}}),
            "undeclared_initial_param",
        ),
        (
            lambda payload: payload["initial_params"]["create_script"].update(
                {"code": "A = 42.0;"}
            ),
            "undeclared_initial_param",
        ),
        (
            lambda payload: payload["routing_delta"]["disable_routes"].append(
                "repair_pin_contract"
            ),
            "route_delta_not_allowed",
        ),
        (
            lambda payload: payload["routing_delta"]["enable_routes"].append(
                "repair_pin_contract"
            ),
            "route_delta_not_allowed",
        ),
        (
            lambda payload: payload["routing_delta"]["set_required"].update(
                {"repair_pin_contract": False}
            ),
            "route_delta_not_allowed",
        ),
        (
            lambda payload: (
                payload["routing_delta"]["enable_routes"].append(
                    "repair_pin_contract"
                ),
                payload["routing_delta"]["disable_routes"].append(
                    "repair_pin_contract"
                ),
            ),
            "conflicting_route_operation",
        ),
        (
            lambda payload: payload["routing_delta"]["set_required"].update(
                {"missing_route": True}
            ),
            "unknown_route_id",
        ),
        (
            lambda payload: (
                payload["routing_delta"]["disable_routes"].append(
                    "repair_pin_contract"
                ),
                payload["routing_delta"]["set_required"].update(
                    {"repair_pin_contract": True}
                ),
            ),
            "set_required_on_disabled_route",
        ),
        (
            lambda payload: payload["routing_delta"][
                "add_unresolved_intent_routes"
            ][0].update({"purpose": "acceptance_criteria"}),
            "invalid_unresolved_intent_route",
        ),
        (
            lambda payload: payload["routing_delta"][
                "add_unresolved_intent_routes"
            ][0].update({"source_path": "planner.intent.other_value"}),
            "invalid_unresolved_intent_route",
        ),
        (
            lambda payload: payload["routing_delta"][
                "add_unresolved_intent_routes"
            ].append(
                copy.deepcopy(
                    payload["routing_delta"]["add_unresolved_intent_routes"][0]
                )
            ),
            "duplicate_added_route_id",
        ),
        (
            lambda payload: payload["routing_delta"][
                "add_unresolved_intent_routes"
            ][0].update({"route_id": "repair_pin_contract"}),
            "added_route_id_collides",
        ),
        (
            lambda payload: payload.update({"intent_slots": []}),
            "unresolved_intent_route_missing_slot",
        ),
        (
            lambda payload: payload["intent_slots"][0].update({"status": "resolved"}),
            "invalid_intent_slot",
        ),
        (
            lambda payload: payload["intent_slots"].append(
                copy.deepcopy(payload["intent_slots"][0])
            ),
            "duplicate_intent_id",
        ),
    ],
)
def test_request_validation_negative_cases(mutate, code):
    payload = _valid_request()
    mutate(payload)

    result = materialize_planner_worker_contract_request(payload)

    assert code in _codes(result.diagnostics)


def test_intent_slot_without_route_warns_but_materialization_remains_non_error():
    payload = _valid_request()
    payload["routing_delta"]["add_unresolved_intent_routes"] = []

    result = materialize_planner_worker_contract_request(payload)

    diagnostics = _diagnostics_by_code(result.diagnostics, "intent_slot_not_routed")
    assert len(diagnostics) == 1
    assert diagnostics[0].severity == "warning"
    assert not any(diagnostic.severity == "error" for diagnostic in result.diagnostics)


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
def test_hidden_answer_and_forbidden_bind_path_markers_are_rejected(marker):
    payload = _valid_request()
    payload["intent_slots"][0]["description"] = marker

    result = materialize_planner_worker_contract_request(payload)

    assert "hidden_answer_marker" in _codes(result.diagnostics)
```

- [ ] **Step 2: Run tests and inspect failures**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_planner_worker_contract_request.py `
  -q
```

Expected: fail on the new route-delta and duplicate-intent edge cases until
Step 3 tightens the implementation.

- [ ] **Step 3: Patch implementation for precise diagnostics**

Update `planner_worker_contract_request.py`:

1. In `_resolved_routing_artifact`, skip appending an added unresolved-intent
   route when the added route id collides with a template route or is duplicated.
2. In `_resolved_routing_artifact`, allow only the canonical
   `planner.intent.desired_output_value` source path; `planner.intent.other_value`
   should emit `invalid_unresolved_intent_route`.
3. In `_intent_diagnostics`, preserve duplicate-intent diagnostics without
   overwriting `slot_ids_by_path`.

Patch snippets:

```python
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
```

and:

```python
        if intent_id in seen_ids:
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
        seen_ids.add(intent_id)
        slot_ids_by_path[source_path] = intent_id
```

- [ ] **Step 4: Run Task 2 tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_planner_worker_contract_request.py `
  -q
```

Expected: all planner request tests pass.

- [ ] **Step 5: Commit Task 2**

```powershell
git add mcp_server\src\rook\agent\planner_worker_contract_request.py `
  mcp_server\tests\test_planner_worker_contract_request.py
git commit -m "test: cover planner request validation"
```

## Task 3: Contract Load/Compile And Bind-Step Guard

**Files:**
- Modify: `mcp_server/src/rook/agent/planner_worker_contract_request.py`
- Modify: `mcp_server/tests/test_planner_worker_contract_request.py`

- [ ] **Step 1: Add tests that materialized contract loads, compiles, and has no repair bind step**

Append:

```python
from rook.agent.plan_graph_workflow_contract import (
    BindStepSpec,
    compile_workflow_contract,
    load_workflow_contract_payload,
)


def test_materialized_workflow_contract_loads_and_compiles():
    result = materialize_planner_worker_contract_request(_valid_request())

    contract = load_workflow_contract_payload(result.workflow_contract_payload)
    scaffold = compile_workflow_contract(contract)

    assert scaffold.compile_record.workflow_id == (
        "lm7a_repair_same_component_from_create_error"
    )
    assert "repair_same_component" in scaffold.compile_record.graph_node_ids


def test_materialized_repair_rule_has_no_bind_step():
    result = materialize_planner_worker_contract_request(_valid_request())
    contract = load_workflow_contract_payload(result.workflow_contract_payload)

    repair_rule = next(
        rule for rule in contract.rules if rule.node_id == "repair_same_component"
    )

    assert not any(isinstance(step, BindStepSpec) for step in repair_rule.steps_by_seen_count)
```

- [ ] **Step 2: Run tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_planner_worker_contract_request.py::test_materialized_workflow_contract_loads_and_compiles `
  mcp_server\tests\test_planner_worker_contract_request.py::test_materialized_repair_rule_has_no_bind_step `
  -q
```

Expected: `test_materialized_workflow_contract_loads_and_compiles` may fail if the materialized contract payload does not match existing loader expectations. Patch the payload only enough to satisfy existing `load_workflow_contract_payload`.

- [ ] **Step 3: Add explicit worker bind-step scan helper**

Add to `planner_worker_contract_request.py`:

```python
def _worker_bind_step_diagnostics(
    workflow_contract_payload: Mapping[str, Any],
) -> list[PlannerRequestDiagnostic]:
    diagnostics: list[PlannerRequestDiagnostic] = []
    rules = workflow_contract_payload.get("rules", [])
    if not isinstance(rules, list):
        return diagnostics
    for rule_index, rule in enumerate(rules):
        if not isinstance(rule, Mapping):
            continue
        node_id = rule.get("node_id")
        if node_id != REPAIR_NODE_ID:
            continue
        steps = rule.get("steps_by_seen_count")
        if not isinstance(steps, list):
            continue
        for step_index, step in enumerate(steps):
            if isinstance(step, Mapping) and step.get("kind") == "bind":
                diagnostics.append(
                    _diagnostic(
                        "worker_bind_step_forbidden",
                        "contract",
                        "Worker-authored node must not have a BindStepSpec.",
                        path=f"rules[{rule_index}].steps_by_seen_count[{step_index}]",
                        node_id=REPAIR_NODE_ID,
                    )
                )
    return diagnostics
```

Then in `materialize_planner_worker_contract_request`, after building `contract_payload`, append:

```python
contract_diagnostics = _worker_bind_step_diagnostics(contract_payload)
```

and include those diagnostics in `all_diagnostics`.

- [ ] **Step 4: Add regression for guard helper using monkeypatch**

Append:

```python
def test_worker_bind_step_guard_rejects_repair_bind_step(monkeypatch):
    original_factory = module._workflow_contract_payload

    def with_bind_step(pins_out):
        payload = original_factory(pins_out)
        repair_rule = next(
            rule for rule in payload["rules"] if rule["node_id"] == "repair_same_component"
        )
        repair_rule["steps_by_seen_count"].insert(
            0,
            {
                "kind": "bind",
                "node_id": "repair_same_component",
                "base_params": {},
                "bindings": {},
            },
        )
        return payload

    monkeypatch.setattr(module, "_workflow_contract_payload", with_bind_step)

    result = materialize_planner_worker_contract_request(_valid_request())

    assert "worker_bind_step_forbidden" in _codes(result.diagnostics)
```

- [ ] **Step 5: Run Task 3 tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_planner_worker_contract_request.py `
  -q
```

Expected: all planner request tests pass.

- [ ] **Step 6: Commit Task 3**

```powershell
git add mcp_server\src\rook\agent\planner_worker_contract_request.py `
  mcp_server\tests\test_planner_worker_contract_request.py
git commit -m "feat: validate planner materialized contract"
```

## Task 4: workflow_validate Report Composer

**Files:**
- Create: `mcp_server/src/rook/agent/workflow_validate.py`
- Create: `mcp_server/tests/test_workflow_validate.py`

- [ ] **Step 1: Write failing report tests**

Create `mcp_server/tests/test_workflow_validate.py`:

```python
from __future__ import annotations

import copy
import json

import rook.agent.workflow_validate as workflow_validate_module
from rook.agent.local_worker_source_routing_validator import (
    SourceRoutingDiagnostic,
    SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA,
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
```

- [ ] **Step 2: Run tests and verify import failure**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_workflow_validate.py `
  -q
```

Expected: import failure because `workflow_validate.py` does not exist.

- [ ] **Step 3: Implement workflow_validate module**

Create `mcp_server/src/rook/agent/workflow_validate.py`:

```python
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from rook.agent.local_worker_source_routing_validator import (
    WorkerVisibleSourceRoutingValidationReport,
    validate_worker_visible_source_routing,
)
from rook.agent.plan_graph_workflow_contract import (
    compile_workflow_contract,
    load_workflow_contract_payload,
)
from rook.agent.planner_worker_contract_request import (
    PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA,
    PlannerRequestDiagnostic,
    materialize_planner_worker_contract_request,
)


WORKFLOW_VALIDATE_REPORT_SCHEMA = "rook.workflow_validate_report:v1"
_PHASES = ("request", "template", "contract", "routing", "intent")


def validate_planner_worker_contract_request(payload: Mapping[str, Any]) -> dict[str, Any]:
    materialization = materialize_planner_worker_contract_request(payload)
    request_fingerprint = _fingerprint(payload)
    phase_diagnostics = {phase: [] for phase in _PHASES}
    for diagnostic in materialization.diagnostics:
        phase_diagnostics[diagnostic.phase].append(_diagnostic_to_dict(diagnostic))

    contract_fingerprint: str | None = None
    contract = None
    if materialization.workflow_contract_payload is not None:
        try:
            contract = load_workflow_contract_payload(
                materialization.workflow_contract_payload
            )
        except Exception as exc:
            phase_diagnostics["contract"].append(
                {
                    "severity": "error",
                    "code": "contract_load_failed",
                    "phase": "contract",
                    "message": f"Workflow contract failed to load: {type(exc).__name__}",
                }
            )
    if contract is not None:
        try:
            scaffold = compile_workflow_contract(contract)
            contract_fingerprint = (
                "sha256:" + scaffold.contract_snapshot.contract_fingerprint
            )
        except Exception as exc:
            phase_diagnostics["contract"].append(
                {
                    "severity": "error",
                    "code": "contract_compile_failed",
                    "phase": "contract",
                    "message": f"Workflow contract failed to compile: {type(exc).__name__}",
                }
            )

    source_routing_report = None
    routing_fingerprint: str | None = None
    if materialization.resolved_routing_artifact is not None:
        routing_fingerprint = _fingerprint(materialization.resolved_routing_artifact)
        source_routing_report = validate_worker_visible_source_routing(
            materialization.resolved_routing_artifact
        )
        phase_diagnostics["routing"].extend(
            _source_routing_diagnostics(source_routing_report)
        )

    phases = {
        phase: {
            "valid": not any(
                diagnostic["severity"] == "error"
                for diagnostic in phase_diagnostics[phase]
            ),
            "diagnostics": phase_diagnostics[phase],
        }
        for phase in _PHASES
    }
    phases["routing"]["source_routing_report"] = (
        _source_routing_report_to_dict(source_routing_report)
        if source_routing_report is not None
        else None
    )
    report = {
        "schema": WORKFLOW_VALIDATE_REPORT_SCHEMA,
        "valid": not any(
            diagnostic["severity"] == "error"
            for diagnostics in phase_diagnostics.values()
            for diagnostic in diagnostics
        ),
        "request_schema": PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA,
        "template_id": payload.get("template_id") if isinstance(payload, Mapping) else None,
        "request_fingerprint": request_fingerprint,
        "report_fingerprint": None,
        "phases": phases,
        "resolved": {
            "workflow_contract_schema": (
                materialization.workflow_contract_payload.get("schema")
                if materialization.workflow_contract_payload is not None
                else None
            ),
            "workflow_contract_id": (
                materialization.workflow_contract_payload.get("workflow_id")
                if materialization.workflow_contract_payload is not None
                else None
            ),
            "workflow_contract_fingerprint": contract_fingerprint,
            "routing_schema": (
                materialization.resolved_routing_artifact.get("schema")
                if materialization.resolved_routing_artifact is not None
                else None
            ),
            "routing_fingerprint": routing_fingerprint,
            "worker_nodes": list(materialization.worker_node_ids),
        },
    }
    report["report_fingerprint"] = _fingerprint_without_report_fingerprint(report)
    return report


def _source_routing_diagnostics(
    report: WorkerVisibleSourceRoutingValidationReport,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for diagnostic in report.static_diagnostics:
        rows.append(
            {
                "severity": diagnostic.severity,
                "code": diagnostic.code,
                "phase": "routing",
                "message": diagnostic.message,
                "node_id": diagnostic.node_id,
                "route_id": diagnostic.route_id,
                "source_class": diagnostic.source_class,
                "source_path": diagnostic.source_path,
                "purpose": diagnostic.purpose,
            }
        )
    return rows


def _source_routing_report_to_dict(
    report: WorkerVisibleSourceRoutingValidationReport,
) -> dict[str, Any]:
    return {
        "schema": report.schema,
        "valid": report.valid,
        "routability_evaluated": report.routability_evaluated,
        "static_diagnostics": [
            {
                "severity": diagnostic.severity,
                "code": diagnostic.code,
                "node_id": diagnostic.node_id,
                "route_id": diagnostic.route_id,
                "source_class": diagnostic.source_class,
                "source_path": diagnostic.source_path,
                "purpose": diagnostic.purpose,
                "message": diagnostic.message,
            }
            for diagnostic in report.static_diagnostics
        ],
        "routability_diagnostics": [
            {
                "severity": diagnostic.severity,
                "code": diagnostic.code,
                "node_id": diagnostic.node_id,
                "route_id": diagnostic.route_id,
                "source_class": diagnostic.source_class,
                "source_path": diagnostic.source_path,
                "purpose": diagnostic.purpose,
                "message": diagnostic.message,
            }
            for diagnostic in report.routability_diagnostics
        ],
    }


def _diagnostic_to_dict(diagnostic: PlannerRequestDiagnostic) -> dict[str, Any]:
    row = {
        "severity": diagnostic.severity,
        "code": diagnostic.code,
        "phase": diagnostic.phase,
        "message": diagnostic.message,
    }
    for field in (
        "path",
        "template_id",
        "node_id",
        "route_id",
        "intent_id",
        "source_class",
        "source_path",
        "purpose",
    ):
        value = getattr(diagnostic, field)
        if value is not None:
            row[field] = value
    return row


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _fingerprint_without_report_fingerprint(report: Mapping[str, Any]) -> str:
    clone = json.loads(json.dumps(report, sort_keys=True, default=str))
    clone.pop("report_fingerprint", None)
    return _fingerprint(clone)


__all__ = (
    "WORKFLOW_VALIDATE_REPORT_SCHEMA",
    "validate_planner_worker_contract_request",
)
```

- [ ] **Step 4: Run workflow_validate tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_workflow_validate.py `
  -q
```

Expected: all workflow validate tests pass.

- [ ] **Step 5: Commit Task 4**

```powershell
git add mcp_server\src\rook\agent\workflow_validate.py `
  mcp_server\tests\test_workflow_validate.py
git commit -m "feat: compose workflow validate report"
```

## Task 5: Hidden Output, Import, And Scope Guards

**Files:**
- Modify: `mcp_server/tests/test_planner_worker_contract_request.py`
- Modify: `mcp_server/tests/test_workflow_validate.py`

- [ ] **Step 1: Add static/source guards**

Append to `mcp_server/tests/test_planner_worker_contract_request.py`:

```python
def test_materialized_contract_and_routing_do_not_expose_hidden_answer_markers():
    result = materialize_planner_worker_contract_request(_valid_request())
    text = json.dumps(
        {
            "contract": result.workflow_contract_payload,
            "routing": result.resolved_routing_artifact,
        },
        sort_keys=True,
    )

    assert "PROBE_REPAIR_CODE" not in text
    assert "A = 42.0" not in text
    assert "repair_same_component.bind.base_params" not in text
    assert "BindStepSpec.base_params" not in text
    assert "BindStepSpec.base_params.code" not in text


def test_planner_request_module_has_no_runtime_or_worker_protocol_imports():
    source = Path(module.__file__).read_text()

    forbidden = [
        "lm6a_live_worker_splice_probe",
        "lm6c_repeatability_probe",
        "lm_worker_two_pass_publication",
        "plan_graph_worker_action_apply",
        "RookAgent",
        "_mcp_tool_executor",
        "ollama",
        "LiteLLM",
    ]
    for text in forbidden:
        assert text not in source
```

Append to `mcp_server/tests/test_workflow_validate.py`:

```python
from pathlib import Path

import rook.agent.workflow_validate as workflow_validate_module


def test_workflow_validate_report_does_not_expose_full_graph_or_hidden_answers():
    report = validate_planner_worker_contract_request(_valid_request())
    text = json.dumps(report, sort_keys=True)

    assert "PROBE_REPAIR_CODE" not in text
    assert "A = 42.0" not in text
    assert "repair_same_component.bind.base_params" not in text
    assert "BindStepSpec.base_params" not in text
    assert "BindStepSpec.base_params.code" not in text
    assert "DefinitelyMissingSymbol" not in text
    assert "graph" not in report["resolved"]


def test_workflow_validate_module_has_no_runtime_or_model_imports():
    source = Path(workflow_validate_module.__file__).read_text()

    forbidden = [
        "lm6a_live_worker_splice_probe",
        "lm6c_repeatability_probe",
        "lm_worker_two_pass_publication",
        "plan_graph_worker_action_apply",
        "RookAgent",
        "_mcp_tool_executor",
        "ollama",
        "LiteLLM",
    ]
    for text in forbidden:
        assert text not in source
```

- [ ] **Step 2: Run targeted tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_planner_worker_contract_request.py `
  mcp_server\tests\test_workflow_validate.py `
  -q
```

Expected: pass.

- [ ] **Step 3: Commit Task 5**

```powershell
git add mcp_server\tests\test_planner_worker_contract_request.py `
  mcp_server\tests\test_workflow_validate.py `
  mcp_server\src\rook\agent\planner_worker_contract_request.py `
  mcp_server\src\rook\agent\workflow_validate.py
git commit -m "test: guard planner validation boundaries"
```

## Task 6: Determinism, Nearby Gates, And Final Scope

**Files:**
- Modify: `docs/superpowers/plans/2026-07-07-lm7a-planner-worker-contract-request.md`

- [ ] **Step 1: Run targeted tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_planner_worker_contract_request.py `
  mcp_server\tests\test_workflow_validate.py `
  -q
```

Expected: all tests pass.

- [ ] **Step 2: Run nearby seam tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_planner_worker_contract_request.py `
  mcp_server\tests\test_workflow_validate.py `
  mcp_server\tests\test_plan_graph_workflow_contract_loader.py `
  mcp_server\tests\test_plan_graph_workflow_contract.py `
  mcp_server\tests\test_local_worker_source_routing_validator.py `
  -q
```

Expected: pass.

- [ ] **Step 3: Run Python 3.10 compile**

Run:

```powershell
py -3.10 -m py_compile `
  mcp_server\src\rook\agent\planner_worker_contract_request.py `
  mcp_server\src\rook\agent\workflow_validate.py `
  mcp_server\tests\test_planner_worker_contract_request.py `
  mcp_server\tests\test_workflow_validate.py
```

Expected: exit code 0.

- [ ] **Step 4: Run diff checks**

Run:

```powershell
git diff --check main..HEAD
git diff --name-only main..HEAD
```

Expected diff scope:

```text
docs/superpowers/plans/2026-07-07-lm7a-planner-worker-contract-request.md
docs/superpowers/specs/2026-07-07-lm7a-planner-worker-contract-request-design.md
mcp_server/src/rook/agent/planner_worker_contract_request.py
mcp_server/src/rook/agent/workflow_validate.py
mcp_server/tests/test_planner_worker_contract_request.py
mcp_server/tests/test_workflow_validate.py
```

Known unrelated local dirt may remain unstaged:

```text
knowledge/gh/operations_knowledge.json
.understand-anything/
docs/superpowers/plans/2026-07-04-rook2-minimal-base-roadmap.md
docs/superpowers/probes/2026-07-04-rook20-v01-hermes-plugin-validation.md
docs/superpowers/specs/2026-07-03-rook-2.0-minimal-iteration-design.md
```

- [ ] **Step 5: Confirm no forbidden file drift**

Run:

```powershell
git diff --name-only main..HEAD -- `
  scripts `
  mcp_server\src\rook\agent\local_worker_source_routing_validator.py `
  mcp_server\src\rook\agent\local_worker_acceptance_criteria.py `
  mcp_server\src\rook\agent\local_worker_acceptance_criteria_sources.py `
  mcp_server\src\rook\agent\plan_graph_worker_action_apply.py
```

Expected: no output.

- [ ] **Step 6: Final commit if plan-only changes remain**

If this plan file has uncommitted changes:

```powershell
git add docs\superpowers\plans\2026-07-07-lm7a-planner-worker-contract-request.md
git commit -m "docs: plan LM7A planner request implementation"
```

## Self-Review Notes

Spec coverage:

- Planner request schema: Task 1 and Task 2.
- Template-owned defaults: Task 1.
- Non-disableable LM6 routes and delta guard: Task 2.
- Intent route/slot compatibility: Task 2.
- No repair bind step for worker node: Task 3.
- workflow_validate unified report: Task 4.
- LM5AA static-only routing report: Task 4.
- No hidden answer/full graph leakage: Task 5.
- No runtime/model/live changes: Task 5 and Task 6.

No live run, model call, Rhino/GH dependency, worker prompt change, or production runtime dispatch is part of this plan.
