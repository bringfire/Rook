import ast
import inspect

import pytest

from rook.agent.gh_scalar_expectation_sources import (
    CONVENTION_SOURCE_PATH,
    EXPECTED_OUTPUT_SOURCE_PATH,
    FIXTURE_ANCHOR_SOURCE_PATH,
    OBSERVED_OUTPUT_SOURCE_PATH,
    extract_gh_scalar_expectation_sources,
)
from rook.agent.local_worker_turn_context import WorkerKnowledgePacket
from rook.learning.plan_graph import GraphMemory, NodeEvidence, PlanGraph, PlanGraphNode


def _contract_payload(expected_value=7.5):
    return {
        "rules": {
            "verify_scalar_output": {
                "expected_output_value": expected_value,
            }
        }
    }


def _graph(*, observed_value=0.0, editable_contract=None, guid="GUID-1"):
    editable_contract = editable_contract or {
        "label": "Target scalar value",
        "value_type": "number",
        "current_value": observed_value,
        "identity_projection": True,
    }
    receipt = {
        "observed_output_value": observed_value,
        "scalar_anchor": {
            "component_guid": guid,
            "editable_value_contract": editable_contract,
        },
    }
    return PlanGraph(
        nodes={
            "create_scalar_expectation": PlanGraphNode(
                id="create_scalar_expectation",
                intent="create scalar expectation",
                evidence=NodeEvidence(
                    tool_status="success",
                    verified=True,
                    receipt=receipt,
                ),
            )
        },
        memory=GraphMemory(),
    )


def _convention_packet():
    return WorkerKnowledgePacket(
        packet_id="gh_set_value_scalar_convention",
        kind="convention",
        title="GH scalar values are changed with gh_set_value",
        content={"action_id": "draft_gh_set_value_params"},
    )


def test_extracts_all_scalar_sources_without_guid_in_visible_anchor():
    sources = extract_gh_scalar_expectation_sources(
        workflow_contract_payload=_contract_payload(expected_value=7.5),
        graph=_graph(observed_value=0.0),
        convention_packets=(_convention_packet(),),
    )

    assert sources.expected_output_contract.source_class == "expected_output_contract"
    assert sources.expected_output_contract.source_path == EXPECTED_OUTPUT_SOURCE_PATH
    assert sources.expected_output_contract.value == 7.5
    assert sources.receipt_observation.source_class == "receipt_observation"
    assert sources.receipt_observation.source_path == OBSERVED_OUTPUT_SOURCE_PATH
    assert sources.receipt_observation.value == 0.0
    assert sources.fixture_anchor.source_class == "fixture_anchor"
    assert sources.fixture_anchor.source_path == FIXTURE_ANCHOR_SOURCE_PATH
    assert sources.fixture_anchor.value == {
        "label": "Target scalar value",
        "value_type": "number",
        "current_value": 0.0,
        "identity_projection": True,
    }
    assert sources.convention is not None
    assert sources.convention.source_class == "convention"
    assert sources.convention.source_path == CONVENTION_SOURCE_PATH
    assert "GUID-1" not in repr(sources.fixture_anchor.value)


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), "7.5", True])
def test_expected_output_value_must_be_finite_number(bad_value):
    with pytest.raises(ValueError, match=EXPECTED_OUTPUT_SOURCE_PATH):
        extract_gh_scalar_expectation_sources(
            workflow_contract_payload=_contract_payload(expected_value=bad_value),
            graph=_graph(),
            convention_packets=(),
        )


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), "0.0", False])
def test_observed_output_value_must_be_finite_number(bad_value):
    with pytest.raises(ValueError, match=OBSERVED_OUTPUT_SOURCE_PATH):
        extract_gh_scalar_expectation_sources(
            workflow_contract_payload=_contract_payload(),
            graph=_graph(observed_value=bad_value),
            convention_packets=(),
        )


def test_missing_observed_output_fails_closed():
    graph = _graph()
    graph.nodes["create_scalar_expectation"].evidence.receipt.pop(
        "observed_output_value"
    )

    with pytest.raises(ValueError, match=OBSERVED_OUTPUT_SOURCE_PATH):
        extract_gh_scalar_expectation_sources(
            workflow_contract_payload=_contract_payload(),
            graph=graph,
            convention_packets=(),
        )


def test_missing_fixture_anchor_contract_fails_closed():
    graph = _graph()
    graph.nodes["create_scalar_expectation"].evidence.receipt["scalar_anchor"].pop(
        "editable_value_contract"
    )

    with pytest.raises(ValueError, match=FIXTURE_ANCHOR_SOURCE_PATH):
        extract_gh_scalar_expectation_sources(
            workflow_contract_payload=_contract_payload(),
            graph=graph,
            convention_packets=(),
        )


def test_extractor_import_boundary_stays_narrow():
    import rook.agent.gh_scalar_expectation_sources as module

    source = inspect.getsource(module)
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")

    forbidden = {
        "rook.server",
        "scripts.lm7e_model_authored_live_splice_probe",
        "scripts.lm7b_request_driven_live_splice_probe",
        "yaml",
        "LiteLLM",
        "BindStepSpec",
    }
    assert imports.isdisjoint(forbidden)
    assert "base_params" not in source
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "base_params"
        for node in ast.walk(tree)
    )
