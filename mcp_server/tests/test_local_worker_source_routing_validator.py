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
DIAGNOSTIC_SOURCE_PATH = "create_script.receipt.script_receipt.repair_anchor.target_errors"
CONVENTION_SOURCE_PATH = "script_body_gotcha"
PLANNER_INTENT_SOURCE_PATH = "planner.intent.desired_output_value"
GH_VERIFY_SOURCE_PATH = "workflow_contract.rules.gh_solve.expected_outcome"
GH_DIAGNOSTIC_SOURCE_PATH = "solve_grasshopper_definition.receipt.gh_receipt.solver_errors"
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


def test_static_only_valid_artifact_returns_valid_report_without_routability():
    report = validate_worker_visible_source_routing(_valid_repair_artifact())

    assert report.schema == SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA
    assert report.valid is True
    assert report.routability_evaluated is False
    assert report.static_diagnostics == ()
    assert report.routability_diagnostics == ()


def test_static_validation_collects_shape_and_allowlist_errors():
    artifact = {
        "schema": "bad.schema:v0",
        "routes": [
            {
                "node_id": "repair_same_component",
                "visible_sources": [
                    {
                        "route_id": "Bad-Id",
                        "source_class": "pin_contract",
                        "source_path": PIN_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "repair_unknown_class",
                        "source_class": "mystery",
                        "source_path": PIN_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "repair_unknown_purpose",
                        "source_class": "pin_contract",
                        "source_path": PIN_SOURCE_PATH,
                        "purpose": "not_a_purpose",
                        "required": True,
                    },
                    {
                        "route_id": "repair_required_shape",
                        "source_class": "verifier_outcome",
                        "source_path": VERIFY_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": "yes",
                    },
                    {
                        "route_id": "repair_forbidden_path",
                        "source_class": "pin_contract",
                        "source_path": "repair_same_component.bind.base_params.code",
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "repair_cross_class",
                        "source_class": "convention",
                        "source_path": PIN_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "repair_duplicate_id",
                        "source_class": "receipt_diagnostic",
                        "source_path": DIAGNOSTIC_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "repair_duplicate_id",
                        "source_class": "convention",
                        "source_path": CONVENTION_SOURCE_PATH,
                        "purpose": "evidence_context",
                        "required": False,
                    },
                    {
                        "route_id": "repair_duplicate_tuple",
                        "source_class": "receipt_diagnostic",
                        "source_path": DIAGNOSTIC_SOURCE_PATH,
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
    static_codes = set(_codes(report.static_diagnostics))
    assert {
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
    } <= static_codes
    assert [
        diagnostic.code
        for diagnostic in report.static_diagnostics
        if diagnostic.route_id == "repair_cross_class"
    ] == ["invalid_source_path"]
    assert [
        diagnostic.code
        for diagnostic in report.static_diagnostics
        if diagnostic.route_id == "repair_required_shape"
    ] == ["invalid_visible_sources_shape"]


def test_planner_user_intent_cannot_feed_acceptance_criteria_in_v1():
    report = validate_worker_visible_source_routing(
        _valid_repair_artifact(
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
    )

    assert _codes(report.static_diagnostics) == ["invalid_source_purpose"]
    assert report.valid is False


def test_partial_routability_inputs_raise_value_error():
    with pytest.raises(ValueError, match="routability inputs"):
        validate_worker_visible_source_routing(
            _valid_repair_artifact(),
            workflow_contract=object(),
        )
