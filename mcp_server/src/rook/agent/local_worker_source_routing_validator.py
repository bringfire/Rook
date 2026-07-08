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

SCALAR_EXPECTED_OUTPUT_SOURCE_PATH = (
    "workflow_contract.rules.verify_scalar_output.expected_output_value"
)
SCALAR_OBSERVED_OUTPUT_SOURCE_PATH = (
    "create_scalar_expectation.receipt.gh_receipt.observed_output_value"
)
SCALAR_FIXTURE_ANCHOR_SOURCE_PATH = (
    "create_scalar_expectation.receipt.gh_receipt.scalar_anchor.editable_value_contract"
)
SCALAR_CONVENTION_SOURCE_PATH = "gh_set_value_scalar_convention"
SCALAR_TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH = (
    "workflow_contract.rules.verify_scalar_transform_output.expected_output_value"
)
SCALAR_TRANSFORM_OFFSET_VALUE_SOURCE_PATH = (
    "workflow_contract.rules.verify_scalar_transform_output.offset_value"
)
SCALAR_TRANSFORM_PROJECTION_SOURCE_PATH = (
    "workflow_contract.rules.verify_scalar_transform_output.projection"
)
SCALAR_TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH = (
    "create_scalar_transform.receipt.gh_receipt.observed_output_value"
)
SCALAR_TRANSFORM_EDITABLE_VALUE_SOURCE_PATH = (
    "create_scalar_transform.receipt.gh_receipt.editable_value"
)
SCALAR_TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH = (
    "create_scalar_transform.receipt.gh_receipt.scalar_anchor.editable_value_contract"
)
SCALAR_TRANSFORM_CONVENTION_SOURCE_PATH = "gh_scalar_transform_set_value_convention"

_ROUTE_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_SOURCE_CLASSES = (
    "pin_contract",
    "verifier_outcome",
    "receipt_diagnostic",
    "convention",
    "planner_user_intent",
    "expected_output_contract",
    "receipt_observation",
    "fixture_anchor",
)
_PURPOSES = ("acceptance_criteria", "evidence_context", "unresolved_intent")
_SOURCE_PURPOSES = {
    "pin_contract": ("acceptance_criteria", "evidence_context"),
    "verifier_outcome": ("acceptance_criteria", "evidence_context"),
    "receipt_diagnostic": ("acceptance_criteria", "evidence_context"),
    "convention": ("acceptance_criteria", "evidence_context"),
    "planner_user_intent": ("unresolved_intent",),
    "expected_output_contract": ("acceptance_criteria", "evidence_context"),
    "receipt_observation": ("acceptance_criteria", "evidence_context"),
    "fixture_anchor": ("evidence_context",),
}
_ALLOWED_SOURCE_PATHS = {
    "pin_contract": (
        PIN_SOURCE_PATH,
        "solve_grasshopper_definition.initial_execution_params.pins_out",
    ),
    "verifier_outcome": (
        VERIFY_SOURCE_PATH,
        "workflow_contract.rules.gh_solve.expected_outcome",
    ),
    "receipt_diagnostic": (
        DIAGNOSTIC_SOURCE_PATH,
        "solve_grasshopper_definition.receipt.gh_receipt.solver_errors",
    ),
    "convention": (
        CONVENTION_SOURCE_PATH,
        "grasshopper_definition_style_convention",
        SCALAR_CONVENTION_SOURCE_PATH,
        SCALAR_TRANSFORM_CONVENTION_SOURCE_PATH,
    ),
    "planner_user_intent": ("planner.intent.desired_output_value",),
    "expected_output_contract": (
        SCALAR_EXPECTED_OUTPUT_SOURCE_PATH,
        SCALAR_TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH,
        SCALAR_TRANSFORM_OFFSET_VALUE_SOURCE_PATH,
        SCALAR_TRANSFORM_PROJECTION_SOURCE_PATH,
    ),
    "receipt_observation": (
        SCALAR_OBSERVED_OUTPUT_SOURCE_PATH,
        SCALAR_TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH,
        SCALAR_TRANSFORM_EDITABLE_VALUE_SOURCE_PATH,
    ),
    "fixture_anchor": (
        SCALAR_FIXTURE_ANCHOR_SOURCE_PATH,
        SCALAR_TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH,
    ),
}
_FORBIDDEN_SOURCE_PATHS = ("PROBE_REPAIR_CODE", "A = 42.0")
_FORBIDDEN_SOURCE_PATH_PREFIXES = (
    "repair_same_component.bind.base_params",
    "BindStepSpec.base_params",
    "future_node.execution_params",
)
_LM5X_SOURCE_PATHS = frozenset(
    (
        PIN_SOURCE_PATH,
        VERIFY_SOURCE_PATH,
        DIAGNOSTIC_SOURCE_PATH,
        CONVENTION_SOURCE_PATH,
    )
)
_STATIC_VALID_SOURCE_PATHS = frozenset(
    source_path
    for source_paths in _ALLOWED_SOURCE_PATHS.values()
    for source_path in source_paths
)


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "static_diagnostics", tuple(self.static_diagnostics))
        object.__setattr__(
            self,
            "routability_diagnostics",
            tuple(self.routability_diagnostics),
        )


def validate_worker_visible_source_routing(
    artifact: Any,
    *,
    workflow_contract: RookWorkflowContract | None = None,
    graph: PlanGraph | None = None,
    convention_packets: Collection[WorkerKnowledgePacket] | None = None,
    worker_node_ids: Collection[str] | None = None,
) -> WorkerVisibleSourceRoutingValidationReport:
    routability_inputs = (
        workflow_contract,
        graph,
        convention_packets,
        worker_node_ids,
    )
    provided_count = sum(value is not None for value in routability_inputs)
    if provided_count not in (0, len(routability_inputs)):
        raise ValueError("routability inputs must be all provided or all omitted")

    static_diagnostics = tuple(_static_diagnostics(artifact))
    routability_diagnostics: tuple[SourceRoutingDiagnostic, ...] = ()
    routability_evaluated = False
    if provided_count == len(routability_inputs) and not _has_errors(static_diagnostics):
        routability_evaluated = True
        routability_diagnostics = tuple(
            _routability_diagnostics(
                artifact,
                workflow_contract=workflow_contract,
                graph=graph,
                convention_packets=convention_packets,
                worker_node_ids=worker_node_ids,
            )
        )

    diagnostics = static_diagnostics + routability_diagnostics
    return WorkerVisibleSourceRoutingValidationReport(
        schema=SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA,
        valid=not _has_errors(diagnostics),
        routability_evaluated=routability_evaluated,
        static_diagnostics=static_diagnostics,
        routability_diagnostics=routability_diagnostics,
    )


def _static_diagnostics(artifact: Any) -> list[SourceRoutingDiagnostic]:
    diagnostics: list[SourceRoutingDiagnostic] = []
    if not isinstance(artifact, Mapping):
        diagnostics.append(
            _diagnostic(
                "invalid_schema",
                "Source routing artifact must be a mapping.",
            )
        )
        return diagnostics
    if artifact.get("schema") != SOURCE_ROUTING_SCHEMA:
        diagnostics.append(
            _diagnostic(
                "invalid_schema",
                "Source routing artifact schema is invalid.",
            )
        )

    routes = artifact.get("routes")
    if not isinstance(routes, list):
        diagnostics.append(
            _diagnostic(
                "invalid_routes_shape",
                "Source routing artifact routes must be a list.",
            )
        )
        return diagnostics

    seen_node_ids: set[str] = set()
    for route in routes:
        if not isinstance(route, Mapping):
            diagnostics.append(
                _diagnostic(
                    "invalid_routes_shape",
                    "Source routing route entries must be mappings.",
                )
            )
            continue

        node_id = route.get("node_id")
        node_id_value = node_id if isinstance(node_id, str) else None
        if not isinstance(node_id, str) or not node_id:
            diagnostics.append(
                _diagnostic(
                    "invalid_node_id",
                    "Source routing route node_id must be a non-empty string.",
                    node_id=node_id_value,
                )
            )
        elif node_id in seen_node_ids:
            diagnostics.append(
                _diagnostic(
                    "duplicate_node_route",
                    "Source routing routes must not repeat node_id entries.",
                    node_id=node_id,
                )
            )
        else:
            seen_node_ids.add(node_id)

        visible_sources = route.get("visible_sources")
        if not isinstance(visible_sources, list) or not visible_sources:
            diagnostics.append(
                _diagnostic(
                    "invalid_visible_sources_shape",
                    "Route visible_sources must be a non-empty list.",
                    node_id=node_id_value,
                )
            )
            continue

        diagnostics.extend(_visible_source_diagnostics(node_id_value, visible_sources))
    return diagnostics


def _visible_source_diagnostics(
    node_id: str | None,
    visible_sources: list[Any],
) -> list[SourceRoutingDiagnostic]:
    diagnostics: list[SourceRoutingDiagnostic] = []
    seen_route_ids: set[str] = set()
    seen_route_tuples: set[tuple[str, str, str]] = set()

    for entry in visible_sources:
        if not isinstance(entry, Mapping):
            diagnostics.append(
                _diagnostic(
                    "invalid_visible_sources_shape",
                    "Visible source entries must be mappings.",
                    node_id=node_id,
                )
            )
            continue

        route_id = _string_or_none(entry.get("route_id"))
        source_class = _string_or_none(entry.get("source_class"))
        source_path = _string_or_none(entry.get("source_path"))
        purpose = _string_or_none(entry.get("purpose"))

        if not isinstance(entry.get("route_id"), str) or not _ROUTE_ID_RE.match(
            entry.get("route_id", "")
        ):
            diagnostics.append(
                _diagnostic(
                    "invalid_route_id",
                    "Visible source route_id must be lowercase snake_case.",
                    node_id=node_id,
                    route_id=route_id,
                    source_class=source_class,
                    source_path=source_path,
                    purpose=purpose,
                )
            )
        elif entry["route_id"] in seen_route_ids:
            diagnostics.append(
                _diagnostic(
                    "duplicate_route_id",
                    "Visible source route_id values must be unique within a node.",
                    node_id=node_id,
                    route_id=route_id,
                    source_class=source_class,
                    source_path=source_path,
                    purpose=purpose,
                )
            )
        else:
            seen_route_ids.add(entry["route_id"])

        if source_class not in _SOURCE_CLASSES:
            diagnostics.append(
                _diagnostic(
                    "unknown_source_class",
                    "Visible source source_class is unknown.",
                    node_id=node_id,
                    route_id=route_id,
                    source_class=source_class,
                    source_path=source_path,
                    purpose=purpose,
                )
            )

        if purpose not in _PURPOSES:
            diagnostics.append(
                _diagnostic(
                    "unknown_purpose",
                    "Visible source purpose is unknown.",
                    node_id=node_id,
                    route_id=route_id,
                    source_class=source_class,
                    source_path=source_path,
                    purpose=purpose,
                )
            )
        elif source_class in _SOURCE_PURPOSES and purpose not in _SOURCE_PURPOSES[source_class]:
            diagnostics.append(
                _diagnostic(
                    "invalid_source_purpose",
                    "Visible source purpose is not compatible with source_class.",
                    node_id=node_id,
                    route_id=route_id,
                    source_class=source_class,
                    source_path=source_path,
                    purpose=purpose,
                )
            )

        if not isinstance(entry.get("source_path"), str) or not entry.get("source_path"):
            diagnostics.append(
                _diagnostic(
                    "invalid_source_path",
                    "Visible source source_path must be a non-empty string.",
                    node_id=node_id,
                    route_id=route_id,
                    source_class=source_class,
                    source_path=source_path,
                    purpose=purpose,
                )
            )
        elif _is_forbidden_source_path(entry["source_path"]):
            diagnostics.append(
                _diagnostic(
                    "forbidden_source_path",
                    "Visible source source_path is forbidden.",
                    node_id=node_id,
                    route_id=route_id,
                    source_class=source_class,
                    source_path=source_path,
                    purpose=purpose,
                )
            )
        elif source_class in _ALLOWED_SOURCE_PATHS and (
            entry["source_path"] not in _ALLOWED_SOURCE_PATHS[source_class]
        ):
            diagnostics.append(
                _diagnostic(
                    "invalid_source_path",
                    "Visible source source_path is not valid for source_class.",
                    node_id=node_id,
                    route_id=route_id,
                    source_class=source_class,
                    source_path=source_path,
                    purpose=purpose,
                )
            )

        if not isinstance(entry.get("required"), bool):
            diagnostics.append(
                _diagnostic(
                    "invalid_visible_sources_shape",
                    "Visible source required must be a bool.",
                    node_id=node_id,
                    route_id=route_id,
                    source_class=source_class,
                    source_path=source_path,
                    purpose=purpose,
                )
            )

        if (
            isinstance(source_class, str)
            and isinstance(source_path, str)
            and isinstance(purpose, str)
        ):
            route_tuple = (source_class, source_path, purpose)
            if route_tuple in seen_route_tuples:
                diagnostics.append(
                    _diagnostic(
                        "duplicate_route_tuple",
                        "Visible source route tuple must be unique within a node.",
                        node_id=node_id,
                        route_id=route_id,
                        source_class=source_class,
                        source_path=source_path,
                        purpose=purpose,
                    )
                )
            else:
                seen_route_tuples.add(route_tuple)

    return diagnostics


def _routability_diagnostics(
    artifact: Mapping[str, Any],
    *,
    workflow_contract: RookWorkflowContract,
    graph: PlanGraph,
    convention_packets: Collection[WorkerKnowledgePacket],
    worker_node_ids: Collection[str],
) -> list[SourceRoutingDiagnostic]:
    diagnostics: list[SourceRoutingDiagnostic] = []
    route_entries = artifact["routes"]
    worker_node_id_set = frozenset(worker_node_ids)

    routable_pairs: frozenset[tuple[str, str]] | None = None
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

    for route in route_entries:
        node_id = route["node_id"]
        if node_id not in worker_node_id_set:
            diagnostics.append(
                _diagnostic(
                    "worker_node_not_found",
                    "node_id was not present in caller-provided worker_node_ids.",
                    node_id=node_id,
                )
            )
            continue

        for visible_source in route["visible_sources"]:
            source_class = visible_source["source_class"]
            source_path = visible_source["source_path"]
            if failed_paths is not None:
                if source_path in failed_paths or source_path not in _LM5X_SOURCE_PATHS:
                    diagnostics.append(
                        _unresolved_route_diagnostic(node_id, visible_source)
                    )
                continue

            if (source_class, source_path) not in routable_pairs:
                diagnostics.append(
                    _unresolved_route_diagnostic(node_id, visible_source)
                )

    return diagnostics


def _lm5x_routable_pairs(
    *,
    workflow_contract: RookWorkflowContract,
    graph: PlanGraph,
    convention_packets: Collection[WorkerKnowledgePacket],
) -> frozenset[tuple[str, str]]:
    sources = extract_acceptance_criteria_sources(
        workflow_contract=workflow_contract,
        graph=graph,
        convention_packets=tuple(convention_packets),
    )
    return _routable_pairs_from_sources(sources)


def _lm5x_failed_source_paths(
    *,
    workflow_contract: RookWorkflowContract,
    graph: PlanGraph,
    convention_packets: Collection[WorkerKnowledgePacket],
) -> frozenset[str] | None:
    try:
        extract_acceptance_criteria_sources(
            workflow_contract=workflow_contract,
            graph=graph,
            convention_packets=tuple(convention_packets),
        )
    except ValueError as exc:
        message = str(exc)
        failed_paths = frozenset(
            source_path
            for source_path in _LM5X_SOURCE_PATHS
            if source_path in message
        )
        return failed_paths or _STATIC_VALID_SOURCE_PATHS
    return None


def _routable_pairs_from_sources(
    sources: AcceptanceCriteriaSources,
) -> frozenset[tuple[str, str]]:
    return frozenset(
        (
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
        )
    )


def _unresolved_route_diagnostic(
    node_id: str,
    visible_source: Mapping[str, Any],
) -> SourceRoutingDiagnostic:
    required = visible_source["required"]
    return SourceRoutingDiagnostic(
        severity="error" if required else "warning",
        code="required_route_unresolved" if required else "optional_route_unresolved",
        node_id=node_id,
        route_id=visible_source["route_id"],
        source_class=visible_source["source_class"],
        source_path=visible_source["source_path"],
        purpose=visible_source["purpose"],
        message="Visible source route could not be resolved from LM5X sources.",
    )


def _diagnostic(
    code: str,
    message: str,
    *,
    node_id: str | None = None,
    route_id: str | None = None,
    source_class: str | None = None,
    source_path: str | None = None,
    purpose: str | None = None,
) -> SourceRoutingDiagnostic:
    return SourceRoutingDiagnostic(
        severity="error",
        code=code,
        node_id=node_id,
        route_id=route_id,
        source_class=source_class,
        source_path=source_path,
        purpose=purpose,
        message=message,
    )


def _has_errors(diagnostics: Sequence[SourceRoutingDiagnostic]) -> bool:
    return any(diagnostic.severity == "error" for diagnostic in diagnostics)


def _is_forbidden_source_path(source_path: str) -> bool:
    return source_path in _FORBIDDEN_SOURCE_PATHS or any(
        source_path.startswith(prefix) for prefix in _FORBIDDEN_SOURCE_PATH_PREFIXES
    )


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


__all__ = (
    "SOURCE_ROUTING_SCHEMA",
    "SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA",
    "SOURCE_ROUTING_SEVERITIES",
    "SOURCE_ROUTING_DIAGNOSTIC_CODES",
    "SourceRoutingDiagnostic",
    "WorkerVisibleSourceRoutingValidationReport",
    "validate_worker_visible_source_routing",
)
