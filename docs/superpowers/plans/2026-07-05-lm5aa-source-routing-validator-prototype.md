# LM5AA Source Routing Validator Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic validator prototype for `rook.worker_visible_source_routing:v1` that separates static artifact validation from LM5X-backed routability validation.

**Architecture:** Add one adjacent production module, `local_worker_source_routing_validator.py`, beside the LM5W assembler and LM5X extractor. The validator returns frozen dataclass reports, performs accumulative static validation first, and performs routability only by calling `extract_acceptance_criteria_sources(...)` and comparing declared routes to LM5X-extracted `(source_class, source_path)` pairs.

**Tech Stack:** Python 3.10, pytest, frozen dataclasses, existing LM5W/LM5X modules, existing LM5K fixture helpers in tests only.

---

## Files

Create:

```text
mcp_server/src/rook/agent/local_worker_source_routing_validator.py
mcp_server/tests/test_local_worker_source_routing_validator.py
```

Modify only docs:

```text
docs/superpowers/plans/2026-07-05-lm5aa-source-routing-validator-prototype.md
```

Do not modify:

```text
scripts/lm5k_worker_probe.py
scripts/lm5r_two_pass_publication_probe.py
mcp_server/src/rook/agent/local_worker_acceptance_criteria.py
mcp_server/src/rook/agent/local_worker_acceptance_criteria_sources.py
mcp_server/src/rook/agent/__init__.py
```

## Task 1: RED Public Surface And Invocation Tests

**Files:**
- Create: `mcp_server/tests/test_local_worker_source_routing_validator.py`

- [ ] **Step 1: Create the test file with imports and shared helpers**

Create `mcp_server/tests/test_local_worker_source_routing_validator.py` with:

```python
import ast
import copy
import importlib.util
import inspect
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from rook.agent import local_worker_source_routing_validator as module
from rook.agent.local_worker_source_routing_validator import (
    SOURCE_ROUTING_DIAGNOSTIC_CODES,
    SOURCE_ROUTING_SCHEMA,
    SOURCE_ROUTING_SEVERITIES,
    SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA,
    SourceRoutingDiagnostic,
    WorkerVisibleSourceRoutingValidationReport,
    validate_worker_visible_source_routing,
)


PIN_SOURCE_PATH = "create_script.initial_execution_params.pins_out"
VERIFY_SOURCE_PATH = "workflow_contract.rules.verify_repair.expected_outcome"
DIAGNOSTIC_SOURCE_PATH = (
    "create_script.receipt.script_receipt.repair_anchor.target_errors"
)
CONVENTION_SOURCE_PATH = "script_body_gotcha"
PLANNER_INTENT_SOURCE_PATH = "planner.intent.desired_output_value"

GH_VERIFY_SOURCE_PATH = "workflow_contract.rules.gh_solve.expected_outcome"
GH_DIAGNOSTIC_SOURCE_PATH = (
    "solve_grasshopper_definition.receipt.gh_receipt.solver_errors"
)
GH_PIN_SOURCE_PATH = "solve_grasshopper_definition.initial_execution_params.pins_out"
GH_CONVENTION_SOURCE_PATH = "grasshopper_definition_style_convention"


def _valid_repair_artifact(*, visible_sources=None):
    return {
        "schema": SOURCE_ROUTING_SCHEMA,
        "routes": [
            {
                "node_id": "repair_same_component",
                "visible_sources": list(
                    visible_sources
                    if visible_sources is not None
                    else (
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
                    )
                ),
            }
        ],
    }


def _gh_pressure_artifact():
    return {
        "schema": SOURCE_ROUTING_SCHEMA,
        "routes": [
            {
                "node_id": "solve_grasshopper_definition",
                "visible_sources": [
                    {
                        "route_id": "gh_expected_solve_status",
                        "source_class": "verifier_outcome",
                        "source_path": GH_VERIFY_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "gh_solver_errors",
                        "source_class": "receipt_diagnostic",
                        "source_path": GH_DIAGNOSTIC_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "gh_component_pin_contract",
                        "source_class": "pin_contract",
                        "source_path": GH_PIN_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "gh_convention_definition_style",
                        "source_class": "convention",
                        "source_path": GH_CONVENTION_SOURCE_PATH,
                        "purpose": "evidence_context",
                        "required": False,
                    },
                ],
            }
        ],
    }


def _load_lm5k_probe_script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "lm5k_worker_probe.py"
    spec = importlib.util.spec_from_file_location("lm5k_worker_probe_for_lm5aa", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fixture_objects():
    probe = _load_lm5k_probe_script()
    _scaffold, result = probe.derive_probe_graph_state()
    return {
        "probe": probe,
        "workflow_contract": probe._probe_contract(),
        "graph": result.final_graph,
        "convention_packets": (probe._script_body_gotcha_packet(),),
    }


def _codes(diagnostics):
    return [diagnostic.code for diagnostic in diagnostics]


def _by_code(diagnostics, code):
    return [diagnostic for diagnostic in diagnostics if diagnostic.code == code]


def _import_names(source):
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
            imports.update(alias.name for alias in node.names)
            if node.module:
                imports.update(f"{node.module}.{alias.name}" for alias in node.names)
    return imports
```

- [ ] **Step 2: Add public surface and dataclass tests**

Append:

```python
def test_public_surface_and_closed_vocabularies():
    assert module.__all__ == (
        "SOURCE_ROUTING_SCHEMA",
        "SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA",
        "SOURCE_ROUTING_SEVERITIES",
        "SOURCE_ROUTING_DIAGNOSTIC_CODES",
        "SourceRoutingDiagnostic",
        "WorkerVisibleSourceRoutingValidationReport",
        "validate_worker_visible_source_routing",
    )
    assert SOURCE_ROUTING_SCHEMA == "rook.worker_visible_source_routing:v1"
    assert SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA == (
        "rook.worker_visible_source_routing_validation_report:v1"
    )
    assert SOURCE_ROUTING_SEVERITIES == ("error", "warning")
    assert SOURCE_ROUTING_DIAGNOSTIC_CODES == (
        "invalid_schema",
        "invalid_routes_shape",
        "duplicate_node_route",
        "invalid_node_id",
        "worker_node_not_found",
        "invalid_visible_sources_shape",
        "invalid_route_id",
        "duplicate_route_id",
        "unknown_source_class",
        "unknown_purpose",
        "invalid_source_purpose",
        "invalid_source_path",
        "forbidden_source_path",
        "duplicate_route_tuple",
        "required_route_unresolved",
        "optional_route_unresolved",
    )


def test_report_and_diagnostics_are_frozen_dataclasses():
    diagnostic = SourceRoutingDiagnostic(
        severity="error",
        code="invalid_schema",
        node_id=None,
        route_id=None,
        source_class=None,
        source_path=None,
        purpose=None,
        message="Schema is invalid.",
    )
    report = WorkerVisibleSourceRoutingValidationReport(
        schema=SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA,
        valid=False,
        routability_evaluated=False,
        static_diagnostics=(diagnostic,),
        routability_diagnostics=(),
    )

    with pytest.raises(FrozenInstanceError):
        diagnostic.code = "mutated"
    with pytest.raises(FrozenInstanceError):
        report.valid = True
    assert isinstance(report.static_diagnostics, tuple)
    assert isinstance(report.routability_diagnostics, tuple)
```

- [ ] **Step 3: Add static-only and partial-input tests**

Append:

```python
def test_static_only_valid_artifact_returns_valid_report_without_routability():
    report = validate_worker_visible_source_routing(_valid_repair_artifact())

    assert report.schema == SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA
    assert report.valid is True
    assert report.routability_evaluated is False
    assert report.static_diagnostics == ()
    assert report.routability_diagnostics == ()


def test_partial_routability_inputs_raise_value_error():
    with pytest.raises(ValueError, match="routability inputs"):
        validate_worker_visible_source_routing(
            _valid_repair_artifact(),
            workflow_contract=object(),
        )
```

- [ ] **Step 4: Run RED public surface tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_public_surface_and_closed_vocabularies `
  -q
```

Expected:

```text
ERROR ... ModuleNotFoundError: No module named 'rook.agent.local_worker_source_routing_validator'
```

- [ ] **Step 5: Commit RED tests**

```powershell
git add mcp_server\tests\test_local_worker_source_routing_validator.py
git commit -m "test(lm5aa): define source routing validator surface"
```

## Task 2: Implement Public Surface And Invocation Modes

**Files:**
- Create: `mcp_server/src/rook/agent/local_worker_source_routing_validator.py`

- [ ] **Step 1: Create the validator module with public surface and minimal static flow**

Create `mcp_server/src/rook/agent/local_worker_source_routing_validator.py` with:

```python
from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
import re
from typing import Any

from rook.agent.local_worker_acceptance_criteria import AcceptanceCriteriaSources
from rook.agent.local_worker_acceptance_criteria_sources import (
    CONVENTION_SOURCE_PATH,
    DIAGNOSTIC_SOURCE_PATH,
    PIN_SOURCE_PATH,
    VERIFY_SOURCE_PATH,
    extract_acceptance_criteria_sources,
)
from rook.agent.local_worker_turn_context import WorkerKnowledgePacket
from rook.agent.plan_graph_workflow_contract import RookWorkflowContract
from rook.learning.plan_graph import PlanGraph


SOURCE_ROUTING_SCHEMA = "rook.worker_visible_source_routing:v1"
SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA = (
    "rook.worker_visible_source_routing_validation_report:v1"
)

SOURCE_ROUTING_SEVERITIES = ("error", "warning")
SOURCE_ROUTING_DIAGNOSTIC_CODES = (
    "invalid_schema",
    "invalid_routes_shape",
    "duplicate_node_route",
    "invalid_node_id",
    "worker_node_not_found",
    "invalid_visible_sources_shape",
    "invalid_route_id",
    "duplicate_route_id",
    "unknown_source_class",
    "unknown_purpose",
    "invalid_source_purpose",
    "invalid_source_path",
    "forbidden_source_path",
    "duplicate_route_tuple",
    "required_route_unresolved",
    "optional_route_unresolved",
)

_ACCEPTANCE_CRITERIA = "acceptance_criteria"
_EVIDENCE_CONTEXT = "evidence_context"
_UNRESOLVED_INTENT = "unresolved_intent"

_ALLOWED_PURPOSES_BY_SOURCE_CLASS = {
    "pin_contract": frozenset({_ACCEPTANCE_CRITERIA, _EVIDENCE_CONTEXT}),
    "verifier_outcome": frozenset({_ACCEPTANCE_CRITERIA, _EVIDENCE_CONTEXT}),
    "receipt_diagnostic": frozenset({_ACCEPTANCE_CRITERIA, _EVIDENCE_CONTEXT}),
    "convention": frozenset({_ACCEPTANCE_CRITERIA, _EVIDENCE_CONTEXT}),
    "planner_user_intent": frozenset({_UNRESOLVED_INTENT}),
}

_GH_PIN_SOURCE_PATH = "solve_grasshopper_definition.initial_execution_params.pins_out"
_GH_VERIFY_SOURCE_PATH = "workflow_contract.rules.gh_solve.expected_outcome"
_GH_DIAGNOSTIC_SOURCE_PATH = (
    "solve_grasshopper_definition.receipt.gh_receipt.solver_errors"
)
_GH_CONVENTION_SOURCE_PATH = "grasshopper_definition_style_convention"
_PLANNER_INTENT_SOURCE_PATH = "planner.intent.desired_output_value"

_SOURCE_PATHS_BY_CLASS = {
    "pin_contract": frozenset({PIN_SOURCE_PATH, _GH_PIN_SOURCE_PATH}),
    "verifier_outcome": frozenset({VERIFY_SOURCE_PATH, _GH_VERIFY_SOURCE_PATH}),
    "receipt_diagnostic": frozenset(
        {DIAGNOSTIC_SOURCE_PATH, _GH_DIAGNOSTIC_SOURCE_PATH}
    ),
    "convention": frozenset({CONVENTION_SOURCE_PATH, _GH_CONVENTION_SOURCE_PATH}),
    "planner_user_intent": frozenset({_PLANNER_INTENT_SOURCE_PATH}),
}

_LM5X_SOURCE_PATHS = frozenset(
    {
        PIN_SOURCE_PATH,
        VERIFY_SOURCE_PATH,
        DIAGNOSTIC_SOURCE_PATH,
        CONVENTION_SOURCE_PATH,
    }
)

_FORBIDDEN_PATH_PREFIXES = (
    "repair_same_component.bind.base_params",
    "BindStepSpec.base_params",
    "future_node.execution_params",
)
_FORBIDDEN_PATH_EXACT = ("PROBE_REPAIR_CODE", "A = 42.0")

_ROUTE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class SourceRoutingDiagnostic:
    severity: str
    code: str
    node_id: str | None
    route_id: str | None
    source_class: str | None
    source_path: str | None
    purpose: str | None
    message: str


@dataclass(frozen=True)
class WorkerVisibleSourceRoutingValidationReport:
    schema: str
    valid: bool
    routability_evaluated: bool
    static_diagnostics: tuple[SourceRoutingDiagnostic, ...]
    routability_diagnostics: tuple[SourceRoutingDiagnostic, ...]


def validate_worker_visible_source_routing(
    artifact: object,
    *,
    workflow_contract: RookWorkflowContract | None = None,
    graph: PlanGraph | None = None,
    convention_packets: Sequence[WorkerKnowledgePacket] | None = None,
    worker_node_ids: Collection[str] | None = None,
) -> WorkerVisibleSourceRoutingValidationReport:
    _require_routability_inputs_all_or_none(
        workflow_contract=workflow_contract,
        graph=graph,
        convention_packets=convention_packets,
        worker_node_ids=worker_node_ids,
    )
    static_diagnostics = tuple(_static_diagnostics(artifact))
    has_static_errors = _has_errors(static_diagnostics)
    routability_requested = all(
        value is not None
        for value in (workflow_contract, graph, convention_packets, worker_node_ids)
    )

    if has_static_errors or not routability_requested:
        return _report(
            static_diagnostics=static_diagnostics,
            routability_evaluated=False,
            routability_diagnostics=(),
        )

    routability_diagnostics = tuple(
        _routability_diagnostics(
            artifact,
            workflow_contract=workflow_contract,
            graph=graph,
            convention_packets=convention_packets,
            worker_node_ids=worker_node_ids,
        )
    )
    return _report(
        static_diagnostics=static_diagnostics,
        routability_evaluated=True,
        routability_diagnostics=routability_diagnostics,
    )


def _require_routability_inputs_all_or_none(
    *,
    workflow_contract: RookWorkflowContract | None,
    graph: PlanGraph | None,
    convention_packets: Sequence[WorkerKnowledgePacket] | None,
    worker_node_ids: Collection[str] | None,
) -> None:
    provided = (
        workflow_contract is not None,
        graph is not None,
        convention_packets is not None,
        worker_node_ids is not None,
    )
    if any(provided) and not all(provided):
        raise ValueError(
            "routability inputs must be provided together: "
            "workflow_contract, graph, convention_packets, worker_node_ids"
        )


def _report(
    *,
    static_diagnostics: tuple[SourceRoutingDiagnostic, ...],
    routability_evaluated: bool,
    routability_diagnostics: tuple[SourceRoutingDiagnostic, ...],
) -> WorkerVisibleSourceRoutingValidationReport:
    return WorkerVisibleSourceRoutingValidationReport(
        schema=SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA,
        valid=not _has_errors(static_diagnostics + routability_diagnostics),
        routability_evaluated=routability_evaluated,
        static_diagnostics=static_diagnostics,
        routability_diagnostics=routability_diagnostics,
    )


def _has_errors(diagnostics: tuple[SourceRoutingDiagnostic, ...]) -> bool:
    return any(diagnostic.severity == "error" for diagnostic in diagnostics)


def _diagnostic(
    *,
    severity: str,
    code: str,
    node_id: str | None = None,
    route_id: str | None = None,
    source_class: str | None = None,
    source_path: str | None = None,
    purpose: str | None = None,
    message: str,
) -> SourceRoutingDiagnostic:
    return SourceRoutingDiagnostic(
        severity=severity,
        code=code,
        node_id=node_id,
        route_id=route_id,
        source_class=source_class,
        source_path=source_path,
        purpose=purpose,
        message=message,
    )


def _static_diagnostics(artifact: object) -> list[SourceRoutingDiagnostic]:
    if not isinstance(artifact, Mapping):
        return [
            _diagnostic(
                severity="error",
                code="invalid_schema",
                message="Routing artifact must be a mapping.",
            )
        ]
    diagnostics: list[SourceRoutingDiagnostic] = []
    if artifact.get("schema") != SOURCE_ROUTING_SCHEMA:
        diagnostics.append(
            _diagnostic(
                severity="error",
                code="invalid_schema",
                message="Routing artifact schema is invalid.",
            )
        )
    routes = artifact.get("routes")
    if not isinstance(routes, list):
        diagnostics.append(
            _diagnostic(
                severity="error",
                code="invalid_routes_shape",
                message="Routing artifact routes must be a list.",
            )
        )
        return diagnostics
    seen_nodes: set[str] = set()
    for route in routes:
        diagnostics.extend(_route_static_diagnostics(route, seen_nodes))
    return diagnostics


def _route_static_diagnostics(
    route: object,
    seen_nodes: set[str],
) -> list[SourceRoutingDiagnostic]:
    diagnostics: list[SourceRoutingDiagnostic] = []
    if not isinstance(route, Mapping):
        return [
            _diagnostic(
                severity="error",
                code="invalid_routes_shape",
                message="Route entry must be a mapping.",
            )
        ]
    node_id = route.get("node_id")
    node_id_value = node_id if isinstance(node_id, str) else None
    if not isinstance(node_id, str) or not node_id:
        diagnostics.append(
            _diagnostic(
                severity="error",
                code="invalid_node_id",
                message="Route entry node_id must be a non-empty string.",
            )
        )
    elif node_id in seen_nodes:
        diagnostics.append(
            _diagnostic(
                severity="error",
                code="duplicate_node_route",
                node_id=node_id,
                message="Route entry node_id is duplicated.",
            )
        )
    else:
        seen_nodes.add(node_id)

    visible_sources = route.get("visible_sources")
    if not isinstance(visible_sources, list) or not visible_sources:
        diagnostics.append(
            _diagnostic(
                severity="error",
                code="invalid_visible_sources_shape",
                node_id=node_id_value,
                message="visible_sources must be a non-empty list.",
            )
        )
        return diagnostics

    seen_route_ids: set[str] = set()
    seen_tuples: set[tuple[str, str, str]] = set()
    for visible_source in visible_sources:
        diagnostics.extend(
            _visible_source_static_diagnostics(
                visible_source,
                node_id=node_id_value,
                seen_route_ids=seen_route_ids,
                seen_tuples=seen_tuples,
            )
        )
    return diagnostics


def _visible_source_static_diagnostics(
    visible_source: object,
    *,
    node_id: str | None,
    seen_route_ids: set[str],
    seen_tuples: set[tuple[str, str, str]],
) -> list[SourceRoutingDiagnostic]:
    diagnostics: list[SourceRoutingDiagnostic] = []
    if not isinstance(visible_source, Mapping):
        return [
            _diagnostic(
                severity="error",
                code="invalid_visible_sources_shape",
                node_id=node_id,
                message="visible_sources entries must be mappings.",
            )
        ]

    route_id = visible_source.get("route_id")
    source_class = visible_source.get("source_class")
    source_path = visible_source.get("source_path")
    purpose = visible_source.get("purpose")

    route_id_value = route_id if isinstance(route_id, str) else None
    source_class_value = source_class if isinstance(source_class, str) else None
    source_path_value = source_path if isinstance(source_path, str) else None
    purpose_value = purpose if isinstance(purpose, str) else None

    if not isinstance(route_id, str) or not _ROUTE_ID_PATTERN.fullmatch(route_id):
        diagnostics.append(
            _diagnostic(
                severity="error",
                code="invalid_route_id",
                node_id=node_id,
                route_id=route_id_value,
                source_class=source_class_value,
                source_path=source_path_value,
                purpose=purpose_value,
                message="route_id must be stable lowercase snake_case.",
            )
        )
    elif route_id in seen_route_ids:
        diagnostics.append(
            _diagnostic(
                severity="error",
                code="duplicate_route_id",
                node_id=node_id,
                route_id=route_id,
                source_class=source_class_value,
                source_path=source_path_value,
                purpose=purpose_value,
                message="route_id is duplicated within the node.",
            )
        )
    else:
        seen_route_ids.add(route_id)

    source_class_known = (
        isinstance(source_class, str)
        and source_class in _ALLOWED_PURPOSES_BY_SOURCE_CLASS
    )
    purpose_known = isinstance(purpose, str) and purpose in {
        _ACCEPTANCE_CRITERIA,
        _EVIDENCE_CONTEXT,
        _UNRESOLVED_INTENT,
    }

    if not source_class_known:
        diagnostics.append(
            _diagnostic(
                severity="error",
                code="unknown_source_class",
                node_id=node_id,
                route_id=route_id_value,
                source_class=source_class_value,
                source_path=source_path_value,
                purpose=purpose_value,
                message="source_class is not in the closed allowlist.",
            )
        )
    if not purpose_known:
        diagnostics.append(
            _diagnostic(
                severity="error",
                code="unknown_purpose",
                node_id=node_id,
                route_id=route_id_value,
                source_class=source_class_value,
                source_path=source_path_value,
                purpose=purpose_value,
                message="purpose is not in the closed allowlist.",
            )
        )
    if source_class_known and purpose_known:
        allowed_purposes = _ALLOWED_PURPOSES_BY_SOURCE_CLASS[source_class]
        if purpose not in allowed_purposes:
            diagnostics.append(
                _diagnostic(
                    severity="error",
                    code="invalid_source_purpose",
                    node_id=node_id,
                    route_id=route_id_value,
                    source_class=source_class_value,
                    source_path=source_path_value,
                    purpose=purpose_value,
                    message="source_class cannot be used with this purpose.",
                )
            )

    if not isinstance(source_path, str) or not source_path:
        diagnostics.append(
            _diagnostic(
                severity="error",
                code="invalid_source_path",
                node_id=node_id,
                route_id=route_id_value,
                source_class=source_class_value,
                source_path=source_path_value,
                purpose=purpose_value,
                message="source_path must be a non-empty canonical string.",
            )
        )
    elif _is_forbidden_path(source_path):
        diagnostics.append(
            _diagnostic(
                severity="error",
                code="forbidden_source_path",
                node_id=node_id,
                route_id=route_id_value,
                source_class=source_class_value,
                source_path=source_path,
                purpose=purpose_value,
                message="source_path is forbidden for worker-visible routing.",
            )
        )
    elif source_class_known and source_path not in _SOURCE_PATHS_BY_CLASS[source_class]:
        diagnostics.append(
            _diagnostic(
                severity="error",
                code="invalid_source_path",
                node_id=node_id,
                route_id=route_id_value,
                source_class=source_class_value,
                source_path=source_path,
                purpose=purpose_value,
                message="source_path is not allowed for this source_class.",
            )
        )

    if not isinstance(visible_source.get("required"), bool):
        diagnostics.append(
            _diagnostic(
                severity="error",
                code="invalid_visible_sources_shape",
                node_id=node_id,
                route_id=route_id_value,
                source_class=source_class_value,
                source_path=source_path_value,
                purpose=purpose_value,
                message="required must be a boolean.",
            )
        )

    if (
        isinstance(source_class, str)
        and isinstance(source_path, str)
        and isinstance(purpose, str)
    ):
        route_tuple = (source_class, source_path, purpose)
        if route_tuple in seen_tuples:
            diagnostics.append(
                _diagnostic(
                    severity="error",
                    code="duplicate_route_tuple",
                    node_id=node_id,
                    route_id=route_id_value,
                    source_class=source_class,
                    source_path=source_path,
                    purpose=purpose,
                    message="source_class/source_path/purpose route tuple is duplicated.",
                )
            )
        else:
            seen_tuples.add(route_tuple)

    return diagnostics


def _is_forbidden_path(source_path: str) -> bool:
    return source_path in _FORBIDDEN_PATH_EXACT or any(
        source_path.startswith(prefix) for prefix in _FORBIDDEN_PATH_PREFIXES
    )


def _routability_diagnostics(
    artifact: Mapping[str, Any],
    *,
    workflow_contract: RookWorkflowContract,
    graph: PlanGraph,
    convention_packets: Sequence[WorkerKnowledgePacket],
    worker_node_ids: Collection[str],
) -> list[SourceRoutingDiagnostic]:
    return []


__all__ = (
    "SOURCE_ROUTING_SCHEMA",
    "SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA",
    "SOURCE_ROUTING_SEVERITIES",
    "SOURCE_ROUTING_DIAGNOSTIC_CODES",
    "SourceRoutingDiagnostic",
    "WorkerVisibleSourceRoutingValidationReport",
    "validate_worker_visible_source_routing",
)
```

- [ ] **Step 2: Run Task 1 tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_public_surface_and_closed_vocabularies `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_report_and_diagnostics_are_frozen_dataclasses `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_static_only_valid_artifact_returns_valid_report_without_routability `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_partial_routability_inputs_raise_value_error `
  -q
```

Expected:

```text
4 passed
```

- [ ] **Step 3: Commit implementation surface**

```powershell
git add `
  mcp_server\src\rook\agent\local_worker_source_routing_validator.py `
  mcp_server\tests\test_local_worker_source_routing_validator.py
git commit -m "feat(lm5aa): add source routing validator surface"
```

## Task 3: Static Validation Regression Tests

**Files:**
- Modify: `mcp_server/tests/test_local_worker_source_routing_validator.py`

- [ ] **Step 1: Add static validation failure tests**

Append:

```python
def test_static_validation_collects_shape_and_allowlist_errors():
    artifact = {
        "schema": "bad.schema:v0",
        "routes": [
            {
                "node_id": "repair_same_component",
                "visible_sources": [
                    {
                        "route_id": "Bad-Id",
                        "source_class": "mystery",
                        "source_path": PIN_SOURCE_PATH,
                        "purpose": "not_a_purpose",
                        "required": "yes",
                    },
                    {
                        "route_id": "repair_answer",
                        "source_class": "pin_contract",
                        "source_path": "repair_same_component.bind.base_params.code",
                        "purpose": "acceptance_criteria",
                        "required": False,
                    },
                    {
                        "route_id": "repair_cross_class",
                        "source_class": "convention",
                        "source_path": PIN_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "repair_pin_contract",
                        "source_class": "pin_contract",
                        "source_path": PIN_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "repair_pin_contract",
                        "source_class": "pin_contract",
                        "source_path": PIN_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "repair_pin_contract_duplicate_tuple",
                        "source_class": "pin_contract",
                        "source_path": PIN_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                ],
            },
            {
                "node_id": "repair_same_component",
                "visible_sources": [],
            },
        ],
    }

    report = validate_worker_visible_source_routing(artifact)

    assert report.valid is False
    assert report.routability_evaluated is False
    assert set(_codes(report.static_diagnostics)) >= {
        "invalid_schema",
        "duplicate_node_route",
        "invalid_visible_sources_shape",
        "invalid_route_id",
        "duplicate_route_id",
        "unknown_source_class",
        "unknown_purpose",
        "invalid_source_path",
        "forbidden_source_path",
        "duplicate_route_tuple",
    }
    cross_class = [
        diagnostic
        for diagnostic in report.static_diagnostics
        if diagnostic.route_id == "repair_cross_class"
    ]
    assert _codes(cross_class) == ["invalid_source_path"]


def test_planner_user_intent_cannot_feed_acceptance_criteria_in_v1():
    artifact = _valid_repair_artifact(
        visible_sources=[
            {
                "route_id": "desired_output_value_criteria",
                "source_class": "planner_user_intent",
                "source_path": PLANNER_INTENT_SOURCE_PATH,
                "purpose": "acceptance_criteria",
                "required": True,
            }
        ]
    )

    report = validate_worker_visible_source_routing(artifact)

    assert report.valid is False
    assert _codes(report.static_diagnostics) == ["invalid_source_purpose"]
```

- [ ] **Step 2: Run RED static validation tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_static_validation_collects_shape_and_allowlist_errors `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_planner_user_intent_cannot_feed_acceptance_criteria_in_v1 `
  -q
```

Expected before Task 4 if Task 2 code was copied exactly:

```text
2 passed
```

If these already pass, keep the tests as the RED/green guard for the static implementation. Do not weaken them.

- [ ] **Step 3: Commit static validation tests**

```powershell
git add mcp_server\tests\test_local_worker_source_routing_validator.py
git commit -m "test(lm5aa): pin static source routing diagnostics"
```

## Task 4: RED Routability Tests

**Files:**
- Modify: `mcp_server/tests/test_local_worker_source_routing_validator.py`

- [ ] **Step 1: Add routability success test**

Append:

```python
def test_lm5u_repair_route_set_is_routable_against_fixture_objects():
    fixture = _fixture_objects()

    report = validate_worker_visible_source_routing(
        _valid_repair_artifact(),
        workflow_contract=fixture["workflow_contract"],
        graph=fixture["graph"],
        convention_packets=fixture["convention_packets"],
        worker_node_ids={"repair_same_component"},
    )

    assert report.valid is True
    assert report.routability_evaluated is True
    assert report.static_diagnostics == ()
    assert report.routability_diagnostics == ()
```

- [ ] **Step 2: Add routability failure tests**

Append:

```python
def test_gh_pressure_example_is_static_valid_but_not_routable_in_v1():
    fixture = _fixture_objects()

    report = validate_worker_visible_source_routing(
        _gh_pressure_artifact(),
        workflow_contract=fixture["workflow_contract"],
        graph=fixture["graph"],
        convention_packets=fixture["convention_packets"],
        worker_node_ids={"solve_grasshopper_definition"},
    )

    assert report.routability_evaluated is True
    assert report.static_diagnostics == ()
    assert report.valid is False
    assert _codes(report.routability_diagnostics) == [
        "required_route_unresolved",
        "required_route_unresolved",
        "required_route_unresolved",
        "optional_route_unresolved",
    ]


def test_worker_node_not_found_skips_route_level_routability():
    fixture = _fixture_objects()

    report = validate_worker_visible_source_routing(
        _valid_repair_artifact(),
        workflow_contract=fixture["workflow_contract"],
        graph=fixture["graph"],
        convention_packets=fixture["convention_packets"],
        worker_node_ids=set(),
    )

    assert report.valid is False
    assert report.routability_evaluated is True
    assert _codes(report.routability_diagnostics) == ["worker_node_not_found"]
    assert report.routability_diagnostics[0].node_id == "repair_same_component"


def test_required_and_optional_planner_intent_routes_are_unroutable_in_v1():
    fixture = _fixture_objects()
    artifact = _valid_repair_artifact(
        visible_sources=[
            {
                "route_id": "missing_desired_output_value_required",
                "source_class": "planner_user_intent",
                "source_path": PLANNER_INTENT_SOURCE_PATH,
                "purpose": "unresolved_intent",
                "required": True,
            },
            {
                "route_id": "missing_desired_output_value_optional",
                "source_class": "planner_user_intent",
                "source_path": PLANNER_INTENT_SOURCE_PATH,
                "purpose": "unresolved_intent",
                "required": False,
            },
        ]
    )

    report = validate_worker_visible_source_routing(
        artifact,
        workflow_contract=fixture["workflow_contract"],
        graph=fixture["graph"],
        convention_packets=fixture["convention_packets"],
        worker_node_ids={"repair_same_component"},
    )

    assert report.valid is False
    assert report.routability_evaluated is True
    assert [(item.code, item.severity, item.route_id) for item in report.routability_diagnostics] == [
        (
            "required_route_unresolved",
            "error",
            "missing_desired_output_value_required",
        ),
        (
            "optional_route_unresolved",
            "warning",
            "missing_desired_output_value_optional",
        ),
    ]


def test_optional_unresolved_route_warns_without_invalidating_report():
    fixture = _fixture_objects()
    visible_sources = list(_valid_repair_artifact()["routes"][0]["visible_sources"])
    visible_sources.append(
        {
            "route_id": "missing_desired_output_value_optional",
            "source_class": "planner_user_intent",
            "source_path": PLANNER_INTENT_SOURCE_PATH,
            "purpose": "unresolved_intent",
            "required": False,
        }
    )

    report = validate_worker_visible_source_routing(
        _valid_repair_artifact(visible_sources=visible_sources),
        workflow_contract=fixture["workflow_contract"],
        graph=fixture["graph"],
        convention_packets=fixture["convention_packets"],
        worker_node_ids={"repair_same_component"},
    )

    assert report.valid is True
    assert report.routability_evaluated is True
    assert [(item.code, item.severity, item.route_id) for item in report.routability_diagnostics] == [
        (
            "optional_route_unresolved",
            "warning",
            "missing_desired_output_value_optional",
        )
    ]
```

- [ ] **Step 3: Add LM5X ValueError mapping test**

Append:

```python
def test_lm5x_value_error_mapping_uses_declared_routes_and_known_path_fragments():
    fixture = _fixture_objects()

    report = validate_worker_visible_source_routing(
        _valid_repair_artifact(),
        workflow_contract=fixture["workflow_contract"],
        graph=fixture["graph"],
        convention_packets=(),
        worker_node_ids={"repair_same_component"},
    )

    assert report.routability_evaluated is True
    assert report.valid is False
    assert _codes(report.routability_diagnostics) == ["required_route_unresolved"]
    diagnostic = report.routability_diagnostics[0]
    assert diagnostic.route_id == "repair_body_mode_convention"
    assert diagnostic.source_class == "convention"
    assert diagnostic.source_path == CONVENTION_SOURCE_PATH


def test_lm5x_value_error_without_known_fragment_fails_declared_lm5x_routes_closed(
    monkeypatch,
):
    fixture = _fixture_objects()

    def raise_unmapped_value_error(**_kwargs):
        raise ValueError("unmapped extraction failure")

    monkeypatch.setattr(
        module,
        "extract_acceptance_criteria_sources",
        raise_unmapped_value_error,
    )

    report = validate_worker_visible_source_routing(
        _valid_repair_artifact(),
        workflow_contract=fixture["workflow_contract"],
        graph=fixture["graph"],
        convention_packets=fixture["convention_packets"],
        worker_node_ids={"repair_same_component"},
    )

    assert report.routability_evaluated is True
    assert report.valid is False
    assert _codes(report.routability_diagnostics) == [
        "required_route_unresolved",
        "required_route_unresolved",
        "required_route_unresolved",
        "required_route_unresolved",
    ]
    assert [item.route_id for item in report.routability_diagnostics] == [
        "repair_pin_contract",
        "repair_expected_outcome",
        "repair_target_diagnostics",
        "repair_body_mode_convention",
    ]
```

- [ ] **Step 4: Run RED routability tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_lm5u_repair_route_set_is_routable_against_fixture_objects `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_gh_pressure_example_is_static_valid_but_not_routable_in_v1 `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_worker_node_not_found_skips_route_level_routability `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_required_and_optional_planner_intent_routes_are_unroutable_in_v1 `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_optional_unresolved_route_warns_without_invalidating_report `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_lm5x_value_error_mapping_uses_declared_routes_and_known_path_fragments `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_lm5x_value_error_without_known_fragment_fails_declared_lm5x_routes_closed `
  -q
```

Expected before Task 5 if Task 2 code was copied exactly:

```text
FAILED ... routability diagnostics are empty
```

- [ ] **Step 5: Commit RED routability tests**

```powershell
git add mcp_server\tests\test_local_worker_source_routing_validator.py
git commit -m "test(lm5aa): pin lm5x-backed routability diagnostics"
```

## Task 5: Implement LM5X-Backed Routability

**Files:**
- Modify: `mcp_server/src/rook/agent/local_worker_source_routing_validator.py`

- [ ] **Step 1: Replace `_routability_diagnostics` with LM5X-backed implementation**

Replace the existing `_routability_diagnostics(...)` stub with:

```python
def _routability_diagnostics(
    artifact: Mapping[str, Any],
    *,
    workflow_contract: RookWorkflowContract,
    graph: PlanGraph,
    convention_packets: Sequence[WorkerKnowledgePacket],
    worker_node_ids: Collection[str],
) -> list[SourceRoutingDiagnostic]:
    diagnostics: list[SourceRoutingDiagnostic] = []
    routes = artifact["routes"]
    route_entries = [
        route for route in routes if isinstance(route, Mapping)
    ]

    nodes_to_check = [
        route for route in route_entries if isinstance(route.get("node_id"), str)
    ]
    missing_nodes = {
        route["node_id"] for route in nodes_to_check if route["node_id"] not in worker_node_ids
    }
    for node_id in sorted(missing_nodes):
        diagnostics.append(
            _diagnostic(
                severity="error",
                code="worker_node_not_found",
                node_id=node_id,
                message="node_id was not present in caller-provided worker_node_ids.",
            )
        )

    failed_paths = _lm5x_failed_source_paths(
        workflow_contract=workflow_contract,
        graph=graph,
        convention_packets=convention_packets,
    )
    if failed_paths is None:
        routable_pairs = _lm5x_routable_pairs(
            workflow_contract=workflow_contract,
            graph=graph,
            convention_packets=convention_packets,
        )
    else:
        routable_pairs = None

    for route in nodes_to_check:
        node_id = route["node_id"]
        if node_id in missing_nodes:
            continue
        for visible_source in route["visible_sources"]:
            source_class = visible_source["source_class"]
            source_path = visible_source["source_path"]
            if failed_paths is not None:
                if source_path not in failed_paths:
                    continue
            elif (source_class, source_path) in routable_pairs:
                continue
            diagnostics.append(
                _unresolved_route_diagnostic(
                    node_id=node_id,
                    route_id=visible_source["route_id"],
                    source_class=source_class,
                    source_path=source_path,
                    purpose=visible_source["purpose"],
                    required=visible_source["required"],
                )
            )
    return diagnostics
```

- [ ] **Step 2: Add LM5X extraction helpers below `_routability_diagnostics`**

Add:

```python
def _lm5x_routable_pairs(
    *,
    workflow_contract: RookWorkflowContract,
    graph: PlanGraph,
    convention_packets: Sequence[WorkerKnowledgePacket],
) -> frozenset[tuple[str, str]]:
    sources = extract_acceptance_criteria_sources(
        workflow_contract=workflow_contract,
        graph=graph,
        convention_packets=convention_packets,
    )
    return _routable_pairs_from_sources(sources)


def _lm5x_failed_source_paths(
    *,
    workflow_contract: RookWorkflowContract,
    graph: PlanGraph,
    convention_packets: Sequence[WorkerKnowledgePacket],
) -> frozenset[str] | None:
    try:
        extract_acceptance_criteria_sources(
            workflow_contract=workflow_contract,
            graph=graph,
            convention_packets=convention_packets,
        )
    except ValueError as exc:
        message = str(exc)
        failed_paths = {
            source_path for source_path in _LM5X_SOURCE_PATHS if source_path in message
        }
        if not failed_paths:
            return frozenset(_LM5X_SOURCE_PATHS)
        return frozenset(failed_paths)
    return None


def _routable_pairs_from_sources(
    sources: AcceptanceCriteriaSources,
) -> frozenset[tuple[str, str]]:
    return frozenset(
        {
            (sources.pin_contract.source_class, sources.pin_contract.source_path),
            (
                sources.verifier_outcome.source_class,
                sources.verifier_outcome.source_path,
            ),
            (
                sources.receipt_diagnostic.source_class,
                sources.receipt_diagnostic.source_path,
            ),
            (sources.convention.source_class, sources.convention.source_path),
        }
    )


def _unresolved_route_diagnostic(
    *,
    node_id: str,
    route_id: str,
    source_class: str,
    source_path: str,
    purpose: str,
    required: bool,
) -> SourceRoutingDiagnostic:
    if required:
        return _diagnostic(
            severity="error",
            code="required_route_unresolved",
            node_id=node_id,
            route_id=route_id,
            source_class=source_class,
            source_path=source_path,
            purpose=purpose,
            message="Required route could not be resolved by LM5X extraction.",
        )
    return _diagnostic(
        severity="warning",
        code="optional_route_unresolved",
        node_id=node_id,
        route_id=route_id,
        source_class=source_class,
        source_path=source_path,
        purpose=purpose,
        message="Optional route could not be resolved by LM5X extraction.",
    )
```

This intentionally calls `extract_acceptance_criteria_sources(...)`. Do not add any helper that reads `workflow_contract.initial_params`, graph receipts, or convention packet fields directly.

- [ ] **Step 3: Run routability tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_lm5u_repair_route_set_is_routable_against_fixture_objects `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_gh_pressure_example_is_static_valid_but_not_routable_in_v1 `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_worker_node_not_found_skips_route_level_routability `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_required_and_optional_planner_intent_routes_are_unroutable_in_v1 `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_optional_unresolved_route_warns_without_invalidating_report `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_lm5x_value_error_mapping_uses_declared_routes_and_known_path_fragments `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_lm5x_value_error_without_known_fragment_fails_declared_lm5x_routes_closed `
  -q
```

Expected:

```text
7 passed
```

- [ ] **Step 4: Run full validator test file**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_source_routing_validator.py `
  -q
```

Expected:

```text
13 passed
```

- [ ] **Step 5: Commit routability implementation**

```powershell
git add `
  mcp_server\src\rook\agent\local_worker_source_routing_validator.py `
  mcp_server\tests\test_local_worker_source_routing_validator.py
git commit -m "feat(lm5aa): validate source routing routability"
```

## Task 6: Import Guards And Regression Coverage

**Files:**
- Modify: `mcp_server/tests/test_local_worker_source_routing_validator.py`

- [ ] **Step 1: Add import boundary tests**

Append:

```python
def test_validator_import_boundary_stays_narrow():
    source = inspect.getsource(module)
    tree = ast.parse(source)
    imports = _import_names(source)

    assert "rook.agent.local_worker_acceptance_criteria_sources" in imports
    assert "extract_acceptance_criteria_sources" in imports
    forbidden_fragments = (
        "lm5k_worker_probe",
        "lm5r_two_pass_publication_probe",
        "Planner",
        "Compiler",
        "LiteLLM",
        "run_local_worker",
        "yaml",
    )
    for fragment in forbidden_fragments:
        assert fragment not in source
    assert "BindStepSpec" not in imports
    assert all(
        not (isinstance(node, ast.Name) and node.id == "BindStepSpec")
        for node in ast.walk(tree)
    )
    assert all(
        not (isinstance(node, ast.Attribute) and node.attr == "base_params")
        for node in ast.walk(tree)
    )


def test_forbidden_path_policy_strings_are_data_not_coupling():
    forbidden_paths = (
        "repair_same_component.bind.base_params.code",
        "BindStepSpec.base_params",
        "future_node.execution_params",
        "PROBE_REPAIR_CODE",
        "A = 42.0",
    )

    for index, source_path in enumerate(forbidden_paths):
        artifact = _valid_repair_artifact(
            visible_sources=[
                {
                    "route_id": f"forbidden_route_{index}",
                    "source_class": "receipt_diagnostic",
                    "source_path": source_path,
                    "purpose": "evidence_context",
                    "required": True,
                }
            ]
        )

        report = validate_worker_visible_source_routing(artifact)

        diagnostics = _by_code(report.static_diagnostics, "forbidden_source_path")
        assert len(diagnostics) == 1
        assert diagnostics[0].source_path == source_path


def test_acceptance_criteria_modules_do_not_import_routing_validator():
    import rook.agent.local_worker_acceptance_criteria as criteria_module
    import rook.agent.local_worker_acceptance_criteria_sources as source_module

    assert "local_worker_source_routing_validator" not in inspect.getsource(
        criteria_module
    )
    assert "local_worker_source_routing_validator" not in inspect.getsource(
        source_module
    )


def test_agent_package_does_not_reexport_routing_validator():
    import rook.agent as agent_package

    assert "local_worker_source_routing_validator" not in agent_package.__all__
    assert "validate_worker_visible_source_routing" not in agent_package.__all__
    assert "local_worker_source_routing_validator" not in agent_package._EXPORT_MODULES
    assert "validate_worker_visible_source_routing" not in agent_package._EXPORT_MODULES
```

- [ ] **Step 2: Add copy-safety regression for input artifact**

Append:

```python
def test_validator_does_not_mutate_artifact():
    artifact = _valid_repair_artifact()
    before = copy.deepcopy(artifact)

    validate_worker_visible_source_routing(artifact)

    assert artifact == before
```

- [ ] **Step 3: Run guard tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_validator_import_boundary_stays_narrow `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_forbidden_path_policy_strings_are_data_not_coupling `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_acceptance_criteria_modules_do_not_import_routing_validator `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_agent_package_does_not_reexport_routing_validator `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_validator_does_not_mutate_artifact `
  -q
```

Expected:

```text
5 passed
```

- [ ] **Step 4: Run all LM5AA tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_source_routing_validator.py `
  -q
```

Expected:

```text
18 passed
```

- [ ] **Step 5: Commit guards**

```powershell
git add mcp_server\tests\test_local_worker_source_routing_validator.py
git commit -m "test(lm5aa): guard routing validator boundaries"
```

## Task 7: Final Verification And Scope Checks

**Files:**
- Verify only

- [ ] **Step 1: Run targeted LM5AA test file**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_source_routing_validator.py `
  -q
```

Expected:

```text
18 passed
```

- [ ] **Step 2: Run nearby seam tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_acceptance_criteria.py `
  mcp_server\tests\test_local_worker_acceptance_criteria_sources.py `
  mcp_server\tests\test_local_worker_source_routing_validator.py `
  -q
```

Expected: all tests pass. The exact count may differ if adjacent files gain tests during another branch, but failures are not acceptable.

- [ ] **Step 3: Run Python 3.10 compile**

Run:

```powershell
py -3.10 -m py_compile `
  mcp_server\src\rook\agent\local_worker_source_routing_validator.py `
  mcp_server\tests\test_local_worker_source_routing_validator.py
```

Expected: no output and exit code 0.

- [ ] **Step 4: Run diff check**

Run:

```powershell
git diff --check main..HEAD
```

Expected: no output.

- [ ] **Step 5: Confirm exact diff scope**

Run:

```powershell
$expected = @(
  "docs/superpowers/plans/2026-07-05-lm5aa-source-routing-validator-prototype.md",
  "docs/superpowers/specs/2026-07-05-lm5aa-source-routing-validator-prototype-design.md",
  "mcp_server/src/rook/agent/local_worker_source_routing_validator.py",
  "mcp_server/tests/test_local_worker_source_routing_validator.py"
) | Sort-Object
$actual = git diff --name-only main..HEAD | Sort-Object
Compare-Object $expected $actual
```

Expected: no output.

- [ ] **Step 6: Confirm forbidden files unchanged**

Run:

```powershell
git diff --name-only main..HEAD -- `
  scripts/lm5k_worker_probe.py `
  scripts/lm5r_two_pass_publication_probe.py `
  mcp_server/src/rook/agent/local_worker_acceptance_criteria.py `
  mcp_server/src/rook/agent/local_worker_acceptance_criteria_sources.py `
  mcp_server/src/rook/agent/__init__.py
```

Expected: no output.

- [ ] **Step 7: Final status**

Run:

```powershell
git status --short --branch
```

Expected: current branch with only known unrelated untracked files, no unstaged or staged LM5AA changes.
