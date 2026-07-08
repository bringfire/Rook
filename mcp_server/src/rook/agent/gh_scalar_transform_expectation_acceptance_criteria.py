from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from rook.agent.gh_scalar_transform_expectation_sources import (
    EXPECTED_PROJECTION,
    TRANSFORM_CONVENTION_SOURCE_PATH,
    TRANSFORM_EDITABLE_VALUE_SOURCE_PATH,
    TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH,
    TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH,
    TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH,
    TRANSFORM_OFFSET_VALUE_SOURCE_PATH,
    TRANSFORM_PROJECTION_SOURCE_PATH,
    GhScalarTransformExpectationSource,
    GhScalarTransformExpectationSources,
)


GH_SCALAR_TRANSFORM_EXPECTATION_PACKET_SCHEMA = (
    "rook.gh_scalar_transform_expectation_packet:v1"
)


def scalar_transform_action_selection_contract() -> dict[str, Any]:
    return {
        "contract_id": "gh_scalar_transform_action_selection:v1",
        "worker_agency": (
            "If the acceptance criteria are sufficient and action is warranted, "
            "publish action_request with the exact required_action_id. If action "
            "is not warranted, publish a non-action response."
        ),
        "required_response_kind_if_acting": "action_request",
        "required_action_id": "draft_gh_set_value_params",
        "pass1_decision_required_fields_if_acting": ["kind", "action_id"],
        "final_action_request_required_fields": [
            "schema",
            "kind",
            "action_id",
            "rationale",
            "input",
        ],
        "action_input_schema": {
            "type": "object",
            "required": ["value"],
            "properties": {"value": {"type": "number"}},
            "additionalProperties": False,
        },
        "authority_limits": [
            "do not author target GUID",
            "do not call GH tools directly",
            "do not author topology, code, or batch edits",
        ],
    }


def assemble_gh_scalar_transform_expectation_packet(
    sources: GhScalarTransformExpectationSources,
) -> dict[str, Any]:
    _validate_sources(sources)
    source_classes = {
        sources.expected_output_contract.source_class,
        sources.offset_contract.source_class,
        sources.projection_contract.source_class,
        sources.observed_output.source_class,
        sources.editable_observation.source_class,
        sources.fixture_anchor.source_class,
    }
    source_paths = {
        sources.expected_output_contract.source_path,
        sources.offset_contract.source_path,
        sources.projection_contract.source_path,
        sources.observed_output.source_path,
        sources.editable_observation.source_path,
        sources.fixture_anchor.source_path,
    }
    if sources.convention is not None:
        source_classes.add(sources.convention.source_class)
        source_paths.add(sources.convention.source_path)

    criteria = [
        {
            "criterion_id": "match_expected_observed_output",
            "description": "Set the editable scalar value so the inspected GH output equals the source-owned expected output value.",
            "source": sources.expected_output_contract.source_path,
            "source_class": sources.expected_output_contract.source_class,
        },
        {
            "criterion_id": "use_editable_plus_offset_projection",
            "description": "Use the source-owned scalar projection relationship: observed_output = editable_value + offset_value.",
            "source": sources.projection_contract.source_path,
            "source_class": sources.projection_contract.source_class,
        },
    ]
    acceptance_criteria = {
        "source": "gh_scalar_transform_expectation",
        "criteria": [
            {
                "criterion_id": criterion["criterion_id"],
                "description": criterion["description"],
                "source": criterion["source"],
            }
            for criterion in criteria
        ],
    }
    packet = {
        "schema": GH_SCALAR_TRANSFORM_EXPECTATION_PACKET_SCHEMA,
        "source_set": {
            "source_classes": sorted(source_classes),
            "source_paths": sorted(source_paths),
        },
        "criteria": criteria,
        "fields": {
            "current_editable_value": sources.editable_observation.value,
            "offset_value": sources.offset_contract.value,
            "current_observed_output": sources.observed_output.value,
            "expected_output_value": sources.expected_output_contract.value,
            "projection": dict(sources.projection_contract.value),
            "editable_value_contract": dict(sources.fixture_anchor.value),
            "recommended_action_id": "draft_gh_set_value_params",
            "action_selection_contract": scalar_transform_action_selection_contract(),
            "acceptance_criteria": acceptance_criteria,
        },
    }
    canonical_packet = json.dumps(packet, sort_keys=True, separators=(",", ":"))
    packet["fingerprint"] = (
        f"sha256:{hashlib.sha256(canonical_packet.encode('utf-8')).hexdigest()}"
    )
    return packet


def project_gh_scalar_transform_expectation_legacy(
    packet: dict[str, Any],
) -> dict[str, Any]:
    fields = packet.get("fields")
    if not isinstance(fields, dict):
        raise ValueError("GH scalar transform packet fields missing")
    acceptance_criteria = fields.get("acceptance_criteria")
    if not isinstance(acceptance_criteria, dict):
        raise ValueError("GH scalar transform acceptance_criteria missing")
    return {
        "source": acceptance_criteria["source"],
        "criteria": [dict(item) for item in acceptance_criteria["criteria"]],
    }


def _validate_sources(sources: GhScalarTransformExpectationSources) -> None:
    _validate_source(
        sources.expected_output_contract,
        source_class="expected_output_contract",
        source_path=TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH,
    )
    _validate_source(
        sources.offset_contract,
        source_class="expected_output_contract",
        source_path=TRANSFORM_OFFSET_VALUE_SOURCE_PATH,
    )
    _validate_source(
        sources.projection_contract,
        source_class="expected_output_contract",
        source_path=TRANSFORM_PROJECTION_SOURCE_PATH,
    )
    _validate_source(
        sources.observed_output,
        source_class="receipt_observation",
        source_path=TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH,
    )
    _validate_source(
        sources.editable_observation,
        source_class="receipt_observation",
        source_path=TRANSFORM_EDITABLE_VALUE_SOURCE_PATH,
    )
    _validate_source(
        sources.fixture_anchor,
        source_class="fixture_anchor",
        source_path=TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH,
    )
    if sources.convention is not None:
        _validate_source(
            sources.convention,
            source_class="convention",
            source_path=TRANSFORM_CONVENTION_SOURCE_PATH,
        )
    _finite_number(sources.expected_output_contract.value, "expected_output_contract")
    _finite_number(sources.offset_contract.value, "offset_contract")
    _finite_number(sources.observed_output.value, "observed_output")
    _finite_number(sources.editable_observation.value, "editable_observation")
    _validate_projection(sources.projection_contract.value)
    _validate_fixture_anchor(sources.fixture_anchor.value)
    if sources.convention is not None:
        _validate_convention(sources.convention.value)


def _validate_source(
    source: GhScalarTransformExpectationSource,
    *,
    source_class: str,
    source_path: str,
) -> None:
    if source.source_class != source_class:
        raise ValueError(f"expected source class {source_class!r}.")
    if source.source_path != source_path:
        raise ValueError(f"expected source path {source_path!r}.")


def _finite_number(value: Any, context: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{context} value must be a finite number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{context} value must be a finite number")


def _validate_projection(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError("projection_contract value must be a mapping")
    if value != EXPECTED_PROJECTION:
        raise ValueError("projection_contract value must match EXPECTED_PROJECTION")


def _validate_fixture_anchor(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError("fixture_anchor value must be a mapping")
    if "guid" in value or "component_guid" in value:
        raise ValueError("fixture_anchor value must not contain a guid")
    required = {
        "label",
        "value_type",
        "current_value",
        "projection_id",
    }
    if set(value) != required:
        raise ValueError("fixture_anchor value has invalid fields")
    if not isinstance(value["label"], str) or not value["label"]:
        raise ValueError("fixture_anchor label must be non-empty")
    if value["value_type"] != "number":
        raise ValueError("fixture_anchor value_type must be number")
    _finite_number(value["current_value"], "fixture_anchor.current_value")
    if value["projection_id"] != EXPECTED_PROJECTION["projection_id"]:
        raise ValueError("fixture_anchor projection_id must match EXPECTED_PROJECTION")


def _validate_convention(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError("convention value must be a mapping")
    if set(value) != {"action_id"}:
        raise ValueError("convention value must only contain action_id")
    if value["action_id"] != "draft_gh_set_value_params":
        raise ValueError("convention action_id invalid")


__all__ = (
    "GH_SCALAR_TRANSFORM_EXPECTATION_PACKET_SCHEMA",
    "GhScalarTransformExpectationSource",
    "GhScalarTransformExpectationSources",
    "assemble_gh_scalar_transform_expectation_packet",
    "project_gh_scalar_transform_expectation_legacy",
    "scalar_transform_action_selection_contract",
)
