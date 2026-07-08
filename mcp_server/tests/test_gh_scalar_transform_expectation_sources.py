import ast
import inspect

import pytest

from rook.agent.gh_scalar_transform_expectation_sources import (
    TRANSFORM_CONVENTION_SOURCE_PATH,
    TRANSFORM_EDITABLE_VALUE_SOURCE_PATH,
    TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH,
    TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH,
    TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH,
    TRANSFORM_OFFSET_VALUE_SOURCE_PATH,
    TRANSFORM_PROJECTION_SOURCE_PATH,
    extract_gh_scalar_transform_expectation_sources,
)
from rook.agent.local_worker_turn_context import WorkerKnowledgePacket
from rook.learning.plan_graph import GraphMemory, NodeEvidence, PlanGraph, PlanGraphNode


def _projection():
    return {
        "projection_id": "editable_plus_offset",
        "description": "observed_output = editable_value + offset_value",
        "editable_variable": "editable_value",
        "offset_variable": "offset_value",
        "output_variable": "observed_output",
    }


def _contract_payload(expected_value=7.5, offset_value=1.5, projection=None):
    return {
        "rules": {
            "verify_scalar_transform_output": {
                "expected_output_value": expected_value,
                "offset_value": offset_value,
                "projection": projection or _projection(),
            }
        }
    }


def _graph(
    *,
    observed_value=3.5,
    editable_value=2.0,
    editable_contract=None,
    guid="EDITABLE-GUID-1",
):
    editable_contract = editable_contract or {
        "label": "LM8F_Editable",
        "value_type": "number",
        "current_value": editable_value,
        "projection_id": "editable_plus_offset",
    }
    receipt = {
        "observed_output_value": observed_value,
        "editable_value": editable_value,
        "scalar_anchor": {
            "component_guid": guid,
            "editable_value_contract": editable_contract,
        },
    }
    return PlanGraph(
        nodes={
            "create_scalar_transform": PlanGraphNode(
                id="create_scalar_transform",
                intent="create scalar transform fixture",
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
        packet_id="gh_scalar_transform_set_value_convention",
        kind="convention",
        title="GH scalar transform values are changed with gh_set_value",
        content={"action_id": "draft_gh_set_value_params"},
    )


def test_extracts_transform_sources_without_guid_in_visible_anchor():
    sources = extract_gh_scalar_transform_expectation_sources(
        workflow_contract_payload=_contract_payload(),
        graph=_graph(),
        convention_packets=(_convention_packet(),),
    )

    assert sources.expected_output_contract.source_class == "expected_output_contract"
    assert (
        sources.expected_output_contract.source_path
        == TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH
    )
    assert sources.expected_output_contract.value == 7.5
    assert sources.offset_contract.source_class == "expected_output_contract"
    assert sources.offset_contract.source_path == TRANSFORM_OFFSET_VALUE_SOURCE_PATH
    assert sources.offset_contract.value == 1.5
    assert sources.projection_contract.source_class == "expected_output_contract"
    assert sources.projection_contract.source_path == TRANSFORM_PROJECTION_SOURCE_PATH
    assert sources.projection_contract.value == _projection()
    assert sources.observed_output.source_class == "receipt_observation"
    assert sources.observed_output.source_path == TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH
    assert sources.observed_output.value == 3.5
    assert sources.editable_observation.source_class == "receipt_observation"
    assert (
        sources.editable_observation.source_path == TRANSFORM_EDITABLE_VALUE_SOURCE_PATH
    )
    assert sources.editable_observation.value == 2.0
    assert sources.fixture_anchor.source_class == "fixture_anchor"
    assert sources.fixture_anchor.source_path == TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH
    assert sources.fixture_anchor.value == {
        "label": "LM8F_Editable",
        "value_type": "number",
        "current_value": 2.0,
        "projection_id": "editable_plus_offset",
    }
    assert sources.convention is not None
    assert sources.convention.source_path == TRANSFORM_CONVENTION_SOURCE_PATH
    assert "EDITABLE-GUID-1" not in repr(sources.fixture_anchor.value)


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), "7.5", True])
def test_expected_output_value_must_be_finite_number(bad_value):
    with pytest.raises(ValueError, match=TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH):
        extract_gh_scalar_transform_expectation_sources(
            workflow_contract_payload=_contract_payload(expected_value=bad_value),
            graph=_graph(),
            convention_packets=(),
        )


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), "1.5", False])
def test_offset_value_must_be_finite_number(bad_value):
    with pytest.raises(ValueError, match=TRANSFORM_OFFSET_VALUE_SOURCE_PATH):
        extract_gh_scalar_transform_expectation_sources(
            workflow_contract_payload=_contract_payload(offset_value=bad_value),
            graph=_graph(),
            convention_packets=(),
        )


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), "3.5", True])
def test_observed_output_value_must_be_finite_number(bad_value):
    with pytest.raises(ValueError, match=TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH):
        extract_gh_scalar_transform_expectation_sources(
            workflow_contract_payload=_contract_payload(),
            graph=_graph(observed_value=bad_value),
            convention_packets=(),
        )


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), "2.0", False])
def test_editable_value_must_be_finite_number(bad_value):
    with pytest.raises(ValueError, match=TRANSFORM_EDITABLE_VALUE_SOURCE_PATH):
        extract_gh_scalar_transform_expectation_sources(
            workflow_contract_payload=_contract_payload(),
            graph=_graph(editable_value=bad_value),
            convention_packets=(),
        )


def test_projection_must_be_exact_v1_relationship():
    bad_projection = {
        "projection_id": "editable_times_offset",
        "description": "observed_output = editable_value * offset_value",
        "editable_variable": "editable_value",
        "offset_variable": "offset_value",
        "output_variable": "observed_output",
    }

    with pytest.raises(ValueError, match=TRANSFORM_PROJECTION_SOURCE_PATH):
        extract_gh_scalar_transform_expectation_sources(
            workflow_contract_payload=_contract_payload(projection=bad_projection),
            graph=_graph(),
            convention_packets=(),
        )


def test_missing_fixture_anchor_contract_fails_closed():
    graph = _graph()
    graph.nodes["create_scalar_transform"].evidence.receipt["scalar_anchor"].pop(
        "editable_value_contract"
    )

    with pytest.raises(ValueError, match=TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH):
        extract_gh_scalar_transform_expectation_sources(
            workflow_contract_payload=_contract_payload(),
            graph=graph,
            convention_packets=(),
        )


def test_fixture_anchor_contract_must_not_expose_guid():
    graph = _graph(
        editable_contract={
            "label": "LM8F_Editable",
            "value_type": "number",
            "current_value": 2.0,
            "projection_id": "editable_plus_offset",
            "component_guid": "EDITABLE-GUID-1",
        }
    )

    with pytest.raises(ValueError, match=TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH):
        extract_gh_scalar_transform_expectation_sources(
            workflow_contract_payload=_contract_payload(),
            graph=graph,
            convention_packets=(),
        )


def test_transform_source_import_boundary_stays_narrow():
    import rook.agent.gh_scalar_transform_expectation_sources as module

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
        "scripts.lm8c_gh_scalar_expectation_live_probe",
        "scripts.lm7e_model_authored_live_splice_probe",
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
