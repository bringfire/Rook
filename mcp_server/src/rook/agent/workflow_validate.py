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
    phase_diagnostics: dict[str, list[dict[str, Any]]] = {
        phase: [] for phase in _PHASES
    }
    for diagnostic in materialization.diagnostics:
        phase_diagnostics[diagnostic.phase].append(_diagnostic_to_dict(diagnostic))

    if (
        materialization.workflow_contract_payload is None
        and not _has_errors(phase_diagnostics["request"])
        and not _has_errors(phase_diagnostics["template"])
        and not phase_diagnostics["contract"]
    ):
        phase_diagnostics["contract"].append(
            {
                "severity": "warning",
                "code": "contract_not_evaluated",
                "phase": "contract",
                "message": (
                    "Workflow contract was not evaluated because request "
                    "materialization did not complete."
                ),
            }
        )

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
                    "message": (
                        "Workflow contract failed to load: "
                        f"{type(exc).__name__}"
                    ),
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
                    "message": (
                        "Workflow contract failed to compile: "
                        f"{type(exc).__name__}"
                    ),
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
            "valid": not _has_errors(phase_diagnostics[phase]),
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
            _has_errors(diagnostics) for diagnostics in phase_diagnostics.values()
        ),
        "request_schema": PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA,
        "template_id": payload.get("template_id")
        if isinstance(payload, Mapping)
        else None,
        "request_fingerprint": _fingerprint(payload),
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
    return [
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
        for diagnostic in (
            report.static_diagnostics + report.routability_diagnostics
        )
    ]


def _source_routing_report_to_dict(
    report: WorkerVisibleSourceRoutingValidationReport,
) -> dict[str, Any]:
    return {
        "schema": report.schema,
        "valid": report.valid,
        "routability_evaluated": report.routability_evaluated,
        "static_diagnostics": [
            _source_routing_diagnostic_to_dict(diagnostic)
            for diagnostic in report.static_diagnostics
        ],
        "routability_diagnostics": [
            _source_routing_diagnostic_to_dict(diagnostic)
            for diagnostic in report.routability_diagnostics
        ],
    }


def _source_routing_diagnostic_to_dict(diagnostic: Any) -> dict[str, Any]:
    return {
        "severity": diagnostic.severity,
        "code": diagnostic.code,
        "node_id": diagnostic.node_id,
        "route_id": diagnostic.route_id,
        "source_class": diagnostic.source_class,
        "source_path": diagnostic.source_path,
        "purpose": diagnostic.purpose,
        "message": diagnostic.message,
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


def _has_errors(diagnostics: list[dict[str, Any]]) -> bool:
    return any(diagnostic["severity"] == "error" for diagnostic in diagnostics)


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(
        _canonical_json_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _canonical_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return [
            [str(key), _canonical_json_value(nested_value)]
            for key, nested_value in sorted(
                value.items(),
                key=lambda item: (
                    str(item[0]),
                    type(item[0]).__name__,
                    repr(item[0]),
                ),
            )
        ]
    if isinstance(value, list):
        return [_canonical_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_canonical_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _fingerprint_without_report_fingerprint(report: Mapping[str, Any]) -> str:
    clone = dict(report)
    clone.pop("report_fingerprint", None)
    return _fingerprint(clone)


__all__ = (
    "WORKFLOW_VALIDATE_REPORT_SCHEMA",
    "validate_planner_worker_contract_request",
)
