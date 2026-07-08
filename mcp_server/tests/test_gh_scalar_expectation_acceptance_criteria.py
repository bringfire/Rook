import ast
import hashlib
import inspect
import json

import pytest

from rook.agent import gh_scalar_expectation_acceptance_criteria as module
from rook.agent.gh_scalar_expectation_acceptance_criteria import (
    GH_SCALAR_EXPECTATION_PACKET_SCHEMA,
    GhScalarExpectationSource,
    GhScalarExpectationSources,
    assemble_gh_scalar_expectation_packet,
    project_gh_scalar_expectation_legacy,
)


EXPECTED_PATH = "workflow_contract.rules.verify_scalar_output.expected_output_value"
OBSERVED_PATH = "create_scalar_expectation.receipt.gh_receipt.observed_output_value"
ANCHOR_PATH = (
    "create_scalar_expectation.receipt.gh_receipt.scalar_anchor.editable_value_contract"
)
CONVENTION_PATH = "gh_set_value_scalar_convention"


def _valid_sources(**overrides):
    values = {
        "expected_output_contract": GhScalarExpectationSource(
            source_class="expected_output_contract",
            source_path=EXPECTED_PATH,
            value=7.5,
        ),
        "receipt_observation": GhScalarExpectationSource(
            source_class="receipt_observation",
            source_path=OBSERVED_PATH,
            value=0.0,
        ),
        "fixture_anchor": GhScalarExpectationSource(
            source_class="fixture_anchor",
            source_path=ANCHOR_PATH,
            value={
                "label": "Target scalar value",
                "value_type": "number",
                "current_value": 0.0,
                "identity_projection": True,
            },
        ),
        "convention": GhScalarExpectationSource(
            source_class="convention",
            source_path=CONVENTION_PATH,
            value={"action_id": "draft_gh_set_value_params"},
        ),
    }
    values.update(overrides)
    return GhScalarExpectationSources(**values)


def _without_fingerprint(packet):
    copied = dict(packet)
    copied.pop("fingerprint")
    return copied


def test_public_surface():
    assert module.__all__ == (
        "GH_SCALAR_EXPECTATION_PACKET_SCHEMA",
        "GhScalarExpectationSource",
        "GhScalarExpectationSources",
        "assemble_gh_scalar_expectation_packet",
        "project_gh_scalar_expectation_legacy",
    )
    assert GH_SCALAR_EXPECTATION_PACKET_SCHEMA == "rook.gh_scalar_expectation_packet:v1"


def test_assembles_scalar_expectation_packet():
    packet = assemble_gh_scalar_expectation_packet(_valid_sources())

    assert packet["schema"] == GH_SCALAR_EXPECTATION_PACKET_SCHEMA
    assert packet["source_set"] == {
        "source_classes": [
            "convention",
            "expected_output_contract",
            "fixture_anchor",
            "receipt_observation",
        ],
        "source_paths": sorted([
            CONVENTION_PATH,
            ANCHOR_PATH,
            OBSERVED_PATH,
            EXPECTED_PATH,
        ]),
    }
    assert packet["fields"] == {
        "current_observed_output": 0.0,
        "expected_output_value": 7.5,
        "editable_value_contract": {
            "label": "Target scalar value",
            "value_type": "number",
            "current_value": 0.0,
            "identity_projection": True,
        },
        "recommended_action_id": "draft_gh_set_value_params",
        "acceptance_criteria": {
            "source": "gh_scalar_expectation",
            "criteria": [
                {
                    "criterion_id": "set_scalar_to_match_expected_output",
                    "description": "Set the editable scalar value to the source-owned expected output value.",
                    "source": EXPECTED_PATH,
                },
                {
                    "criterion_id": "identity_projection_output_matches_value",
                    "description": "In this v1 fixture, the editable scalar value is the inspected output value.",
                    "source": OBSERVED_PATH,
                },
            ],
        },
    }
    assert [criterion["source_class"] for criterion in packet["criteria"]] == [
        "expected_output_contract",
        "receipt_observation",
    ]
    assert "component_guid" not in json.dumps(packet, sort_keys=True)
    assert packet["fingerprint"].startswith("sha256:")


def test_legacy_projection_excludes_schema_source_set_and_fingerprint():
    packet = assemble_gh_scalar_expectation_packet(_valid_sources())

    projection = project_gh_scalar_expectation_legacy(packet)

    assert projection == packet["fields"]["acceptance_criteria"]
    rendered = json.dumps(projection, sort_keys=True)
    for forbidden in ("schema", "source_set", "source_class", "fingerprint"):
        assert forbidden not in rendered


def test_fingerprint_matches_canonical_packet_without_fingerprint():
    packet = assemble_gh_scalar_expectation_packet(_valid_sources())

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
        assemble_gh_scalar_expectation_packet(
            _valid_sources(
                expected_output_contract=GhScalarExpectationSource(
                    source_class="expected_output_contract",
                    source_path=EXPECTED_PATH,
                    value=bad_value,
                )
            )
        )


def test_fixture_anchor_cannot_contain_guid_or_feed_criteria():
    with pytest.raises(ValueError, match="fixture_anchor"):
        assemble_gh_scalar_expectation_packet(
            _valid_sources(
                fixture_anchor=GhScalarExpectationSource(
                    source_class="fixture_anchor",
                    source_path=ANCHOR_PATH,
                    value={
                        "label": "Target scalar value",
                        "value_type": "number",
                        "current_value": 0.0,
                        "identity_projection": True,
                        "component_guid": "GUID-1",
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
        "lm7e_model_authored_live_splice_probe",
        "LiteLLM",
        "yaml",
    )
    for fragment in forbidden_import_fragments:
        assert not any(fragment in imported for imported in imports)
    assert "base_params" not in source
