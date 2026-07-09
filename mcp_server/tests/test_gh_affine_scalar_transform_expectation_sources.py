import ast
import inspect

import pytest

from rook.agent.gh_affine_scalar_transform_expectation_sources import (
    AFFINE_CONVENTION_SOURCE_PATH,
    AFFINE_EDITABLE_VALUE_SOURCE_PATH,
    AFFINE_EXPECTED_OUTPUT_SOURCE_PATH,
    AFFINE_FACTOR_VALUE_SOURCE_PATH,
    AFFINE_FIXTURE_ANCHOR_SOURCE_PATH,
    AFFINE_OBSERVED_OUTPUT_SOURCE_PATH,
    AFFINE_OFFSET_VALUE_SOURCE_PATH,
    AFFINE_PROJECTION_SOURCE_PATH,
    EXPECTED_AFFINE_PROJECTION,
    extract_gh_affine_scalar_transform_expectation_sources,
)
from rook.agent.local_worker_turn_context import WorkerKnowledgePacket
from rook.learning.plan_graph import GraphMemory, NodeEvidence, PlanGraph, PlanGraphNode


def _contract_payload(expected_value=7.5, factor_value=2.0, offset_value=1.5, projection=None):
    return {
        "rules": {
            "verify_affine_scalar_transform_output": {
                "expected_output_value": expected_value,
                "factor_value": factor_value,
                "offset_value": offset_value,
                "projection": projection or EXPECTED_AFFINE_PROJECTION,
            }
        }
    }


def _graph(
    *,
    observed_value=5.5,
    editable_value=2.0,
    editable_contract=None,
    component_guid="EDITABLE-GUID-1",
    internal_component_guid=None,
):
    editable_contract = editable_contract or {
        "label": "LM8H_Editable",
        "value_type": "number",
        "current_value": editable_value,
        "projection_id": "editable_times_factor_plus_offset",
    }
    receipt = {
        "observed_output_value": observed_value,
        "editable_value": editable_value,
        "scalar_anchor": {"editable_value_contract": editable_contract},
    }
    if component_guid is not None:
        receipt["scalar_anchor"]["component_guid"] = component_guid
    if internal_component_guid is not None:
        receipt["scalar_anchor"]["internal_component_guid"] = internal_component_guid
    return PlanGraph(
        nodes={
            "create_affine_scalar_transform": PlanGraphNode(
                id="create_affine_scalar_transform",
                intent="create affine scalar transform fixture",
                evidence=NodeEvidence(tool_status="success", verified=True, receipt=receipt),
            )
        },
        memory=GraphMemory(),
    )


def _convention_packet():
    return WorkerKnowledgePacket(
        packet_id="gh_affine_scalar_transform_set_value_convention",
        kind="convention",
        title="GH affine scalar transform values are changed with gh_set_value",
        content={"action_id": "draft_gh_set_value_params"},
    )


def test_extracts_affine_sources_without_guid_in_visible_anchor():
    sources = extract_gh_affine_scalar_transform_expectation_sources(
        workflow_contract_payload=_contract_payload(),
        graph=_graph(),
        convention_packets=(_convention_packet(),),
    )

    assert sources.expected_output_contract.source_path == AFFINE_EXPECTED_OUTPUT_SOURCE_PATH
    assert sources.expected_output_contract.value == 7.5
    assert sources.factor_contract.source_path == AFFINE_FACTOR_VALUE_SOURCE_PATH
    assert sources.factor_contract.value == 2.0
    assert sources.offset_contract.source_path == AFFINE_OFFSET_VALUE_SOURCE_PATH
    assert sources.offset_contract.value == 1.5
    assert sources.projection_contract.source_path == AFFINE_PROJECTION_SOURCE_PATH
    assert sources.projection_contract.value == EXPECTED_AFFINE_PROJECTION
    assert sources.observed_output.source_path == AFFINE_OBSERVED_OUTPUT_SOURCE_PATH
    assert sources.observed_output.value == 5.5
    assert sources.editable_observation.source_path == AFFINE_EDITABLE_VALUE_SOURCE_PATH
    assert sources.editable_observation.value == 2.0
    assert sources.fixture_anchor.source_path == AFFINE_FIXTURE_ANCHOR_SOURCE_PATH
    assert sources.fixture_anchor.value == {
        "label": "LM8H_Editable",
        "value_type": "number",
        "current_value": 2.0,
        "projection_id": "editable_times_factor_plus_offset",
    }
    assert sources.convention is not None
    assert sources.convention.source_path == AFFINE_CONVENTION_SOURCE_PATH
    assert "EDITABLE-GUID-1" not in repr(sources.fixture_anchor.value)


@pytest.mark.parametrize("field", ["expected_output_value", "factor_value", "offset_value"])
@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), "2.0", True])
def test_affine_contract_numbers_must_be_finite(field, bad_value):
    payload = _contract_payload()
    payload["rules"]["verify_affine_scalar_transform_output"][field] = bad_value

    with pytest.raises(ValueError, match=field):
        extract_gh_affine_scalar_transform_expectation_sources(
            workflow_contract_payload=payload,
            graph=_graph(),
            convention_packets=(),
        )


def test_projection_must_be_exact_affine_relationship():
    bad_projection = {
        "projection_id": "editable_plus_offset",
        "description": "observed_output = editable_value + offset_value",
        "editable_variable": "editable_value",
        "offset_variable": "offset_value",
        "output_variable": "observed_output",
    }

    with pytest.raises(ValueError, match=AFFINE_PROJECTION_SOURCE_PATH):
        extract_gh_affine_scalar_transform_expectation_sources(
            workflow_contract_payload=_contract_payload(projection=bad_projection),
            graph=_graph(),
            convention_packets=(),
        )


def test_fixture_anchor_contract_must_not_expose_guid():
    graph = _graph(
        editable_contract={
            "label": "LM8H_Editable",
            "value_type": "number",
            "current_value": 2.0,
            "projection_id": "editable_times_factor_plus_offset",
            "component_guid": "EDITABLE-GUID-1",
        }
    )

    with pytest.raises(ValueError, match=AFFINE_FIXTURE_ANCHOR_SOURCE_PATH):
        extract_gh_affine_scalar_transform_expectation_sources(
            workflow_contract_payload=_contract_payload(),
            graph=graph,
            convention_packets=(),
        )


def test_affine_source_import_boundary_stays_narrow():
    import rook.agent.gh_affine_scalar_transform_expectation_sources as module

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
        "scripts.lm8f_scalar_transform_depth_probe",
        "scripts.lm8c_gh_scalar_expectation_live_probe",
        "scripts.lm7e_model_authored_live_splice_probe",
        "yaml",
        "LiteLLM",
        "BindStepSpec",
    }
    assert imports.isdisjoint(forbidden)
    assert "base_params" not in source
