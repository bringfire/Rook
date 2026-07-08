from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from rook.agent.gh_scalar_expectation_sources import (
    CONVENTION_SOURCE_PATH,
    EXPECTED_OUTPUT_SOURCE_PATH,
    FIXTURE_ANCHOR_SOURCE_PATH,
    OBSERVED_OUTPUT_SOURCE_PATH,
    GhScalarExpectationSource,
    GhScalarExpectationSources,
)


GH_SCALAR_EXPECTATION_PACKET_SCHEMA = "rook.gh_scalar_expectation_packet:v1"


def assemble_gh_scalar_expectation_packet(
    sources: GhScalarExpectationSources,
) -> dict[str, Any]:
    _validate_sources(sources)
    source_classes = {
        sources.expected_output_contract.source_class,
        sources.receipt_observation.source_class,
        sources.fixture_anchor.source_class,
    }
    source_paths = {
        sources.expected_output_contract.source_path,
        sources.receipt_observation.source_path,
        sources.fixture_anchor.source_path,
    }
    if sources.convention is not None:
        source_classes.add(sources.convention.source_class)
        source_paths.add(sources.convention.source_path)

    criteria = [
        {
            "criterion_id": "set_scalar_to_match_expected_output",
            "description": "Set the editable scalar value to the source-owned expected output value.",
            "source": sources.expected_output_contract.source_path,
            "source_class": sources.expected_output_contract.source_class,
        },
        {
            "criterion_id": "identity_projection_output_matches_value",
            "description": "In this v1 fixture, the editable scalar value is the inspected output value.",
            "source": sources.receipt_observation.source_path,
            "source_class": sources.receipt_observation.source_class,
        },
    ]
    acceptance_criteria = {
        "source": "gh_scalar_expectation",
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
        "schema": GH_SCALAR_EXPECTATION_PACKET_SCHEMA,
        "source_set": {
            "source_classes": sorted(source_classes),
            "source_paths": sorted(source_paths),
        },
        "criteria": criteria,
        "fields": {
            "current_observed_output": sources.receipt_observation.value,
            "expected_output_value": sources.expected_output_contract.value,
            "editable_value_contract": dict(sources.fixture_anchor.value),
            "recommended_action_id": "draft_gh_set_value_params",
            "acceptance_criteria": acceptance_criteria,
        },
    }
    canonical_packet = json.dumps(packet, sort_keys=True, separators=(",", ":"))
    packet["fingerprint"] = (
        f"sha256:{hashlib.sha256(canonical_packet.encode('utf-8')).hexdigest()}"
    )
    return packet


def project_gh_scalar_expectation_legacy(packet: dict[str, Any]) -> dict[str, Any]:
    fields = packet.get("fields")
    if not isinstance(fields, dict):
        raise ValueError("GH scalar packet fields missing")
    acceptance_criteria = fields.get("acceptance_criteria")
    if not isinstance(acceptance_criteria, dict):
        raise ValueError("GH scalar acceptance_criteria missing")
    return {
        "source": acceptance_criteria["source"],
        "criteria": [dict(item) for item in acceptance_criteria["criteria"]],
    }


def _validate_sources(sources: GhScalarExpectationSources) -> None:
    _validate_source(
        sources.expected_output_contract,
        source_class="expected_output_contract",
        source_path=EXPECTED_OUTPUT_SOURCE_PATH,
    )
    _validate_source(
        sources.receipt_observation,
        source_class="receipt_observation",
        source_path=OBSERVED_OUTPUT_SOURCE_PATH,
    )
    _validate_source(
        sources.fixture_anchor,
        source_class="fixture_anchor",
        source_path=FIXTURE_ANCHOR_SOURCE_PATH,
    )
    if sources.convention is not None:
        _validate_source(
            sources.convention,
            source_class="convention",
            source_path=CONVENTION_SOURCE_PATH,
        )
    _finite_number(sources.expected_output_contract.value, "expected_output_contract")
    _finite_number(sources.receipt_observation.value, "receipt_observation")
    _validate_fixture_anchor(sources.fixture_anchor.value)


def _validate_source(
    source: GhScalarExpectationSource,
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


def _validate_fixture_anchor(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError("fixture_anchor value must be a mapping")
    if "guid" in value or "component_guid" in value:
        raise ValueError("fixture_anchor value must not contain a guid")
    required = {
        "label",
        "value_type",
        "current_value",
        "identity_projection",
    }
    if set(value) != required:
        raise ValueError("fixture_anchor value has invalid fields")
    if not isinstance(value["label"], str) or not value["label"]:
        raise ValueError("fixture_anchor label must be non-empty")
    if value["value_type"] != "number":
        raise ValueError("fixture_anchor value_type must be number")
    _finite_number(value["current_value"], "fixture_anchor.current_value")
    if value["identity_projection"] is not True:
        raise ValueError("fixture_anchor identity_projection must be true")


__all__ = (
    "GH_SCALAR_EXPECTATION_PACKET_SCHEMA",
    "GhScalarExpectationSource",
    "GhScalarExpectationSources",
    "assemble_gh_scalar_expectation_packet",
    "project_gh_scalar_expectation_legacy",
)
