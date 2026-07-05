import ast
import copy
import importlib.util
import inspect
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

from rook.agent.local_worker_acceptance_criteria import (
    AcceptanceCriteriaSource,
    AcceptanceCriteriaSources,
    assemble_acceptance_criteria_packet,
)
from rook.agent import local_worker_acceptance_criteria_sources as module
from rook.agent.local_worker_acceptance_criteria_sources import (
    extract_acceptance_criteria_sources,
)


PIN_SOURCE_PATH = "create_script.initial_execution_params.pins_out"
VERIFY_SOURCE_PATH = "workflow_contract.rules.verify_repair.expected_outcome"
DIAGNOSTIC_SOURCE_PATH = "create_script.receipt.script_receipt.repair_anchor.target_errors"
CONVENTION_SOURCE_PATH = "script_body_gotcha"
TARGET_DIAGNOSTIC = (
    "CS0103: The name 'DefinitelyMissingSymbol' does not exist in the current context."
)


def _expected_sources(**overrides):
    values = {
        "pin_contract": AcceptanceCriteriaSource(
            source_class="pin_contract",
            source_path=PIN_SOURCE_PATH,
            value={"pins_out": ["A:double"]},
        ),
        "verifier_outcome": AcceptanceCriteriaSource(
            source_class="verifier_outcome",
            source_path=VERIFY_SOURCE_PATH,
            value="succeeded",
        ),
        "receipt_diagnostic": AcceptanceCriteriaSource(
            source_class="receipt_diagnostic",
            source_path=DIAGNOSTIC_SOURCE_PATH,
            value=[TARGET_DIAGNOSTIC],
        ),
        "convention": AcceptanceCriteriaSource(
            source_class="convention",
            source_path=CONVENTION_SOURCE_PATH,
            value={"mode": "body"},
        ),
        "unresolved_intent": (),
    }
    values.update(overrides)
    return AcceptanceCriteriaSources(**values)


def _load_lm5k_probe_script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "lm5k_worker_probe.py"
    spec = importlib.util.spec_from_file_location("lm5k_worker_probe_for_lm5x", path)
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


def _extract_from_fixture():
    fixture = _fixture_objects()
    return extract_acceptance_criteria_sources(
        workflow_contract=fixture["workflow_contract"],
        graph=fixture["graph"],
        convention_packets=fixture["convention_packets"],
    )


def _jsonable(value):
    if isinstance(value, Mapping):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value


def _legacy_projection(packet):
    return [
        {
            "criterion_id": criterion["criterion_id"],
            "description": criterion["description"],
            "source": criterion["source"],
        }
        for criterion in packet["criteria"]
    ]


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


def _call_names(source):
    tree = ast.parse(source)
    calls = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            calls.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                calls.add(f"{node.func.value.id}.{node.func.attr}")
            calls.add(node.func.attr)
    return calls


def test_public_surface_exports_only_extractor():
    assert module.__all__ == ("extract_acceptance_criteria_sources",)


def test_extracts_lm5u_fixture_sources():
    assert _extract_from_fixture() == _expected_sources()


def test_assemble_extracted_sources_matches_lm5w_expected_packet_fingerprint():
    extracted_packet = assemble_acceptance_criteria_packet(_extract_from_fixture())
    expected_packet = assemble_acceptance_criteria_packet(_expected_sources())

    assert extracted_packet["fingerprint"] == expected_packet["fingerprint"]
    assert extracted_packet == expected_packet


def test_extracted_sources_match_lm5u_legacy_acceptance_criteria_projection():
    fixture = _fixture_objects()
    lm5u_packet = _jsonable(
        fixture["probe"]._acceptance_criteria_evidence_packet(
            fixture["graph"]
        ).content
    )
    extracted_packet = assemble_acceptance_criteria_packet(
        extract_acceptance_criteria_sources(
            workflow_contract=fixture["workflow_contract"],
            graph=fixture["graph"],
            convention_packets=fixture["convention_packets"],
        )
    )

    assert _legacy_projection(extracted_packet) == (
        lm5u_packet["fields"]["acceptance_criteria"]["criteria"]
    )


def _replace_contract_initial_params(workflow_contract, initial_params):
    from dataclasses import replace

    return replace(workflow_contract, initial_params=tuple(initial_params))


def _replace_contract_rules(workflow_contract, rules):
    from dataclasses import replace

    return replace(workflow_contract, rules=tuple(rules))


def _replace_graph_create_receipt(graph, receipt):
    graph_copy = copy.deepcopy(graph)
    graph_copy.nodes["create_script"].evidence.receipt = receipt
    return graph_copy


def test_missing_create_initial_params_fails_with_pin_source_path():
    fixture = _fixture_objects()
    contract = _replace_contract_initial_params(fixture["workflow_contract"], ())

    with pytest.raises(ValueError, match="create_script.initial_execution_params.pins_out"):
        extract_acceptance_criteria_sources(
            workflow_contract=contract,
            graph=fixture["graph"],
            convention_packets=fixture["convention_packets"],
        )


def test_missing_verify_repair_rule_fails_with_verifier_source_path():
    fixture = _fixture_objects()
    contract = _replace_contract_rules(
        fixture["workflow_contract"],
        [
            rule
            for rule in fixture["workflow_contract"].rules
            if rule.node_id != "verify_repair"
        ],
    )

    with pytest.raises(
        ValueError,
        match="workflow_contract.rules.verify_repair.expected_outcome",
    ):
        extract_acceptance_criteria_sources(
            workflow_contract=contract,
            graph=fixture["graph"],
            convention_packets=fixture["convention_packets"],
        )


def test_target_errors_wrong_shape_fails_with_diagnostic_source_path():
    fixture = _fixture_objects()
    receipt = copy.deepcopy(
        fixture["graph"].nodes["create_script"].evidence.receipt
    )
    receipt["repair_anchor"]["target_errors"] = "not-a-list"
    graph = _replace_graph_create_receipt(fixture["graph"], receipt)

    with pytest.raises(
        ValueError,
        match="create_script.receipt.script_receipt.repair_anchor.target_errors",
    ):
        extract_acceptance_criteria_sources(
            workflow_contract=fixture["workflow_contract"],
            graph=graph,
            convention_packets=fixture["convention_packets"],
        )


def test_missing_script_body_gotcha_fails_with_packet_id():
    fixture = _fixture_objects()

    with pytest.raises(ValueError, match="script_body_gotcha"):
        extract_acceptance_criteria_sources(
            workflow_contract=fixture["workflow_contract"],
            graph=fixture["graph"],
            convention_packets=(),
        )


def test_wrong_diagnostic_shape_extracts_but_assembler_rejects_semantics():
    fixture = _fixture_objects()
    receipt = copy.deepcopy(
        fixture["graph"].nodes["create_script"].evidence.receipt
    )
    receipt["repair_anchor"]["target_errors"] = ["CS0000: Different diagnostic"]
    graph = _replace_graph_create_receipt(fixture["graph"], receipt)

    sources = extract_acceptance_criteria_sources(
        workflow_contract=fixture["workflow_contract"],
        graph=graph,
        convention_packets=fixture["convention_packets"],
    )

    assert sources.receipt_diagnostic.value == ["CS0000: Different diagnostic"]
    with pytest.raises(ValueError, match="DefinitelyMissingSymbol"):
        assemble_acceptance_criteria_packet(sources)
