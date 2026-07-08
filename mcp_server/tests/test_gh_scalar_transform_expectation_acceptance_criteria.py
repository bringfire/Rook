import ast
import hashlib
import inspect
import json

import pytest

from rook.agent import gh_scalar_transform_expectation_acceptance_criteria as module
from rook.agent.gh_scalar_transform_expectation_acceptance_criteria import (
    GH_SCALAR_TRANSFORM_EXPECTATION_PACKET_SCHEMA,
    GhScalarTransformExpectationSource,
    GhScalarTransformExpectationSources,
    assemble_gh_scalar_transform_expectation_packet,
    project_gh_scalar_transform_expectation_legacy,
    scalar_transform_action_selection_contract,
)


EXPECTED_PATH = "workflow_contract.rules.verify_scalar_transform_output.expected_output_value"
OFFSET_PATH = "workflow_contract.rules.verify_scalar_transform_output.offset_value"
PROJECTION_PATH = "workflow_contract.rules.verify_scalar_transform_output.projection"
OBSERVED_PATH = "create_scalar_transform.receipt.gh_receipt.observed_output_value"
EDITABLE_PATH = "create_scalar_transform.receipt.gh_receipt.editable_value"
ANCHOR_PATH = (
    "create_scalar_transform.receipt.gh_receipt.scalar_anchor.editable_value_contract"
)
CONVENTION_PATH = "gh_scalar_transform_set_value_convention"


def _projection():
    return {
        "projection_id": "editable_plus_offset",
        "description": "observed_output = editable_value + offset_value",
        "editable_variable": "editable_value",
        "offset_variable": "offset_value",
        "output_variable": "observed_output",
    }


def _valid_sources(**overrides):
    values = {
        "expected_output_contract": GhScalarTransformExpectationSource(
            source_class="expected_output_contract",
            source_path=EXPECTED_PATH,
            value=7.5,
        ),
        "offset_contract": GhScalarTransformExpectationSource(
            source_class="expected_output_contract",
            source_path=OFFSET_PATH,
            value=1.5,
        ),
        "projection_contract": GhScalarTransformExpectationSource(
            source_class="expected_output_contract",
            source_path=PROJECTION_PATH,
            value=_projection(),
        ),
        "observed_output": GhScalarTransformExpectationSource(
            source_class="receipt_observation",
            source_path=OBSERVED_PATH,
            value=3.5,
        ),
        "editable_observation": GhScalarTransformExpectationSource(
            source_class="receipt_observation",
            source_path=EDITABLE_PATH,
            value=2.0,
        ),
        "fixture_anchor": GhScalarTransformExpectationSource(
            source_class="fixture_anchor",
            source_path=ANCHOR_PATH,
            value={
                "label": "LM8F_Editable",
                "value_type": "number",
                "current_value": 2.0,
                "projection_id": "editable_plus_offset",
            },
        ),
        "convention": GhScalarTransformExpectationSource(
            source_class="convention",
            source_path=CONVENTION_PATH,
            value={"action_id": "draft_gh_set_value_params"},
        ),
    }
    values.update(overrides)
    return GhScalarTransformExpectationSources(**values)


def _without_fingerprint(packet):
    copied = dict(packet)
    copied.pop("fingerprint")
    return copied


def test_public_surface():
    assert module.__all__ == (
        "GH_SCALAR_TRANSFORM_EXPECTATION_PACKET_SCHEMA",
        "GhScalarTransformExpectationSource",
        "GhScalarTransformExpectationSources",
        "assemble_gh_scalar_transform_expectation_packet",
        "project_gh_scalar_transform_expectation_legacy",
        "scalar_transform_action_selection_contract",
    )
    assert (
        GH_SCALAR_TRANSFORM_EXPECTATION_PACKET_SCHEMA
        == "rook.gh_scalar_transform_expectation_packet:v1"
    )


def test_action_selection_contract_preserves_two_pass_shapes():
    contract = scalar_transform_action_selection_contract()

    assert contract["required_action_id"] == "draft_gh_set_value_params"
    assert contract["pass1_decision_required_fields_if_acting"] == [
        "kind",
        "action_id",
    ]
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


def test_assembles_scalar_transform_packet_without_derived_target_value():
    packet = assemble_gh_scalar_transform_expectation_packet(_valid_sources())

    assert packet["schema"] == GH_SCALAR_TRANSFORM_EXPECTATION_PACKET_SCHEMA
    assert packet["source_set"] == {
        "source_classes": [
            "convention",
            "expected_output_contract",
            "fixture_anchor",
            "receipt_observation",
        ],
        "source_paths": sorted(
            [
                CONVENTION_PATH,
                ANCHOR_PATH,
                EDITABLE_PATH,
                OBSERVED_PATH,
                OFFSET_PATH,
                PROJECTION_PATH,
                EXPECTED_PATH,
            ]
        ),
    }
    assert packet["fields"]["current_editable_value"] == 2.0
    assert packet["fields"]["offset_value"] == 1.5
    assert packet["fields"]["current_observed_output"] == 3.5
    assert packet["fields"]["expected_output_value"] == 7.5
    assert packet["fields"]["projection"] == _projection()
    assert packet["fields"]["editable_value_contract"] == {
        "label": "LM8F_Editable",
        "value_type": "number",
        "current_value": 2.0,
        "projection_id": "editable_plus_offset",
    }
    assert packet["fields"]["recommended_action_id"] == "draft_gh_set_value_params"
    assert packet["fields"]["action_selection_contract"]["required_action_id"] == (
        "draft_gh_set_value_params"
    )
    assert packet["fields"]["acceptance_criteria"] == {
        "source": "gh_scalar_transform_expectation",
        "criteria": [
            {
                "criterion_id": "match_expected_observed_output",
                "description": "Set the editable scalar value so the inspected GH output equals the source-owned expected output value.",
                "source": EXPECTED_PATH,
            },
            {
                "criterion_id": "use_editable_plus_offset_projection",
                "description": "Use the source-owned scalar projection relationship: observed_output = editable_value + offset_value.",
                "source": PROJECTION_PATH,
            },
        ],
    }
    rendered = json.dumps(packet, sort_keys=True)
    assert "6.0" not in rendered
    assert "set editable value to 6" not in rendered.lower()
    assert "component_guid" not in rendered
    assert "EDITABLE-GUID" not in rendered
    assert "gh_edit" not in rendered
    assert "gh_update_script" not in rendered
    assert "repair_same_component" not in rendered
    assert packet["fingerprint"].startswith("sha256:")


def test_legacy_projection_excludes_schema_source_set_source_class_and_fingerprint():
    packet = assemble_gh_scalar_transform_expectation_packet(_valid_sources())

    projection = project_gh_scalar_transform_expectation_legacy(packet)

    assert projection == packet["fields"]["acceptance_criteria"]
    rendered = json.dumps(projection, sort_keys=True)
    for forbidden in ("schema", "source_set", "source_class", "fingerprint"):
        assert forbidden not in rendered
    assert "6.0" not in rendered


def test_fingerprint_matches_canonical_packet_without_fingerprint():
    packet = assemble_gh_scalar_transform_expectation_packet(_valid_sources())

    expected = hashlib.sha256(
        json.dumps(
            _without_fingerprint(packet),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    assert packet["fingerprint"] == f"sha256:{expected}"


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), "7.5", True])
def test_expected_value_fails_closed_for_non_finite_number(bad_value):
    with pytest.raises(ValueError, match="expected_output_contract"):
        assemble_gh_scalar_transform_expectation_packet(
            _valid_sources(
                expected_output_contract=GhScalarTransformExpectationSource(
                    source_class="expected_output_contract",
                    source_path=EXPECTED_PATH,
                    value=bad_value,
                )
            )
        )


def test_fixture_anchor_cannot_contain_guid_or_feed_criteria():
    with pytest.raises(ValueError, match="fixture_anchor"):
        assemble_gh_scalar_transform_expectation_packet(
            _valid_sources(
                fixture_anchor=GhScalarTransformExpectationSource(
                    source_class="fixture_anchor",
                    source_path=ANCHOR_PATH,
                    value={
                        "label": "LM8F_Editable",
                        "value_type": "number",
                        "current_value": 2.0,
                        "projection_id": "editable_plus_offset",
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
        "lm8c_gh_scalar_expectation_live_probe",
        "LiteLLM",
        "yaml",
    )
    for fragment in forbidden_import_fragments:
        assert not any(fragment in imported for imported in imports)
    assert "base_params" not in source
