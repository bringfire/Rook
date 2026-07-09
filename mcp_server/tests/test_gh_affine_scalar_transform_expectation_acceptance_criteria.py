import ast
import hashlib
import inspect
import json

import pytest

from rook.agent import gh_affine_scalar_transform_expectation_acceptance_criteria as module
from rook.agent.gh_affine_scalar_transform_expectation_acceptance_criteria import (
    GH_AFFINE_SCALAR_TRANSFORM_EXPECTATION_PACKET_SCHEMA,
    GhAffineScalarTransformExpectationSource,
    GhAffineScalarTransformExpectationSources,
    affine_scalar_transform_action_selection_contract,
    assemble_gh_affine_scalar_transform_expectation_packet,
    project_gh_affine_scalar_transform_expectation_legacy,
)

EXPECTED_PATH = (
    "workflow_contract.rules.verify_affine_scalar_transform_output.expected_output_value"
)
FACTOR_PATH = "workflow_contract.rules.verify_affine_scalar_transform_output.factor_value"
OFFSET_PATH = "workflow_contract.rules.verify_affine_scalar_transform_output.offset_value"
PROJECTION_PATH = (
    "workflow_contract.rules.verify_affine_scalar_transform_output.projection"
)
OBSERVED_PATH = "create_affine_scalar_transform.receipt.gh_receipt.observed_output_value"
EDITABLE_PATH = "create_affine_scalar_transform.receipt.gh_receipt.editable_value"
ANCHOR_PATH = "create_affine_scalar_transform.receipt.gh_receipt.scalar_anchor.editable_value_contract"
CONVENTION_PATH = "gh_affine_scalar_transform_set_value_convention"


def _projection():
    return {
        "projection_id": "editable_times_factor_plus_offset",
        "description": "observed_output = editable_value * factor_value + offset_value",
        "editable_variable": "editable_value",
        "factor_variable": "factor_value",
        "offset_variable": "offset_value",
        "output_variable": "observed_output",
    }


def _valid_sources(**overrides):
    values = {
        "expected_output_contract": GhAffineScalarTransformExpectationSource(
            "expected_output_contract", EXPECTED_PATH, 7.5
        ),
        "factor_contract": GhAffineScalarTransformExpectationSource(
            "expected_output_contract", FACTOR_PATH, 2.0
        ),
        "offset_contract": GhAffineScalarTransformExpectationSource(
            "expected_output_contract", OFFSET_PATH, 1.5
        ),
        "projection_contract": GhAffineScalarTransformExpectationSource(
            "expected_output_contract", PROJECTION_PATH, _projection()
        ),
        "observed_output": GhAffineScalarTransformExpectationSource(
            "receipt_observation", OBSERVED_PATH, 5.5
        ),
        "editable_observation": GhAffineScalarTransformExpectationSource(
            "receipt_observation", EDITABLE_PATH, 2.0
        ),
        "fixture_anchor": GhAffineScalarTransformExpectationSource(
            "fixture_anchor",
            ANCHOR_PATH,
            {
                "label": "LM8H_Editable",
                "value_type": "number",
                "current_value": 2.0,
                "projection_id": "editable_times_factor_plus_offset",
            },
        ),
        "convention": GhAffineScalarTransformExpectationSource(
            "convention",
            CONVENTION_PATH,
            {"action_id": "draft_gh_set_value_params"},
        ),
    }
    values.update(overrides)
    return GhAffineScalarTransformExpectationSources(**values)


def _without_fingerprint(packet):
    copied = dict(packet)
    copied.pop("fingerprint")
    return copied


def test_public_surface():
    assert module.__all__ == (
        "GH_AFFINE_SCALAR_TRANSFORM_EXPECTATION_PACKET_SCHEMA",
        "GhAffineScalarTransformExpectationSource",
        "GhAffineScalarTransformExpectationSources",
        "affine_scalar_transform_action_selection_contract",
        "assemble_gh_affine_scalar_transform_expectation_packet",
        "project_gh_affine_scalar_transform_expectation_legacy",
    )
    assert (
        GH_AFFINE_SCALAR_TRANSFORM_EXPECTATION_PACKET_SCHEMA
        == "rook.gh_affine_scalar_transform_expectation_packet:v1"
    )


def test_action_selection_contract_preserves_two_pass_shapes():
    contract = affine_scalar_transform_action_selection_contract()

    assert contract["required_action_id"] == "draft_gh_set_value_params"
    assert contract["pass1_decision_required_fields_if_acting"] == ["kind", "action_id"]
    assert contract["final_action_request_required_fields"] == [
        "schema",
        "kind",
        "action_id",
        "rationale",
        "input",
    ]
    assert contract["action_input_schema"] == {
        "type": "object",
        "required": ["value"],
        "properties": {"value": {"type": "number"}},
        "additionalProperties": False,
    }
    assert "you must act" not in contract["worker_agency"].casefold()
    assert "input" not in contract["pass1_decision_required_fields_if_acting"]


def test_assembles_affine_packet_without_derived_target_value():
    packet = assemble_gh_affine_scalar_transform_expectation_packet(_valid_sources())

    assert packet["schema"] == GH_AFFINE_SCALAR_TRANSFORM_EXPECTATION_PACKET_SCHEMA
    assert packet["fields"]["current_editable_value"] == 2.0
    assert packet["fields"]["factor_value"] == 2.0
    assert packet["fields"]["offset_value"] == 1.5
    assert packet["fields"]["current_observed_output"] == 5.5
    assert packet["fields"]["expected_output_value"] == 7.5
    assert packet["fields"]["projection"] == _projection()
    assert packet["fields"]["recommended_action_id"] == "draft_gh_set_value_params"
    assert packet["fields"]["acceptance_criteria"] == {
        "source": "gh_affine_scalar_transform_expectation",
        "criteria": [
            {
                "criterion_id": "match_expected_observed_output",
                "description": "Set the editable scalar value so the inspected GH output equals the source-owned expected output value.",
                "source": EXPECTED_PATH,
            },
            {
                "criterion_id": "use_affine_scalar_projection",
                "description": "Use the source-owned scalar projection relationship: observed_output = editable_value * factor_value + offset_value.",
                "source": PROJECTION_PATH,
            },
        ],
    }
    rendered = json.dumps(packet, sort_keys=True)
    assert "3.0" not in rendered
    assert "set editable value to 3" not in rendered.lower()
    assert "component_guid" not in rendered
    assert "EDITABLE-GUID" not in rendered
    assert "gh_edit" not in rendered
    assert "gh_update_script" not in rendered
    assert "repair_same_component" not in rendered
    assert packet["fingerprint"].startswith("sha256:")


def test_legacy_projection_excludes_schema_source_set_source_class_and_fingerprint():
    packet = assemble_gh_affine_scalar_transform_expectation_packet(_valid_sources())

    projection = project_gh_affine_scalar_transform_expectation_legacy(packet)

    assert projection == packet["fields"]["acceptance_criteria"]
    rendered = json.dumps(projection, sort_keys=True)
    for forbidden in ("schema", "source_set", "source_class", "fingerprint"):
        assert forbidden not in rendered
    assert "3.0" not in rendered


def test_fingerprint_matches_canonical_packet_without_fingerprint():
    packet = assemble_gh_affine_scalar_transform_expectation_packet(_valid_sources())

    expected = hashlib.sha256(
        json.dumps(
            _without_fingerprint(packet),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    assert packet["fingerprint"] == f"sha256:{expected}"


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), "7.5", True])
def test_numeric_sources_fail_closed_for_non_finite_number(bad_value):
    for field_name in (
        "expected_output_contract",
        "factor_contract",
        "offset_contract",
        "observed_output",
        "editable_observation",
    ):
        sources = _valid_sources(
            **{
                field_name: GhAffineScalarTransformExpectationSource(
                    source_class=(
                        "expected_output_contract"
                        if "contract" in field_name
                        else "receipt_observation"
                    ),
                    source_path=EXPECTED_PATH,
                    value=bad_value,
                )
            }
        )
        with pytest.raises(ValueError):
            assemble_gh_affine_scalar_transform_expectation_packet(sources)


def test_fixture_anchor_cannot_contain_guid_or_feed_criteria():
    with pytest.raises(ValueError, match="fixture_anchor"):
        assemble_gh_affine_scalar_transform_expectation_packet(
            _valid_sources(
                fixture_anchor=GhAffineScalarTransformExpectationSource(
                    source_class="fixture_anchor",
                    source_path=ANCHOR_PATH,
                    value={
                        "label": "LM8H_Editable",
                        "value_type": "number",
                        "current_value": 2.0,
                        "projection_id": "editable_times_factor_plus_offset",
                        "component_guid": "EDITABLE-GUID-1",
                    },
                )
            )
        )


def test_import_boundary_stays_narrow():
    source = inspect.getsource(module)
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")

    forbidden_import_fragments = (
        "plan_graph",
        "RookWorkflowContract",
        "lm5k_worker_probe",
        "lm8f_scalar_transform_depth_probe",
        "lm8c_gh_scalar_expectation_live_probe",
        "LiteLLM",
        "yaml",
    )
    for fragment in forbidden_import_fragments:
        assert not any(fragment in imported for imported in imports)
    assert "base_params" not in source
