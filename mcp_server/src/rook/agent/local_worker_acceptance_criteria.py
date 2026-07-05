from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any


ACCEPTANCE_CRITERIA_PACKET_SCHEMA = "rook.acceptance_criteria_packet:v1"

_PIN_SOURCE_PATH = "create_script.initial_execution_params.pins_out"
_VERIFY_SOURCE_PATH = "workflow_contract.rules.verify_repair.expected_outcome"
_DIAGNOSTIC_SOURCE_PATH = (
    "create_script.receipt.script_receipt.repair_anchor.target_errors"
)
_CONVENTION_SOURCE_PATH = "script_body_gotcha"
_TARGET_DIAGNOSTIC = (
    "CS0103: The name 'DefinitelyMissingSymbol' does not exist in the current context."
)


@dataclass(frozen=True)
class AcceptanceCriteriaSource:
    source_class: str
    source_path: str
    value: Any


@dataclass(frozen=True)
class UnresolvedIntentEntry:
    intent_id: str
    description: str
    source_class: str
    source_path: str
    reason: str


@dataclass(frozen=True)
class AcceptanceCriteriaSources:
    pin_contract: AcceptanceCriteriaSource
    verifier_outcome: AcceptanceCriteriaSource
    receipt_diagnostic: AcceptanceCriteriaSource
    convention: AcceptanceCriteriaSource
    unresolved_intent: tuple[UnresolvedIntentEntry, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "unresolved_intent", tuple(self.unresolved_intent))


def assemble_acceptance_criteria_packet(
    sources: AcceptanceCriteriaSources,
) -> dict[str, Any]:
    _validate_sources(sources)

    packet = {
        "schema": ACCEPTANCE_CRITERIA_PACKET_SCHEMA,
        "source_set": {
            "source_classes": sorted(
                {
                    sources.pin_contract.source_class,
                    sources.verifier_outcome.source_class,
                    sources.receipt_diagnostic.source_class,
                    sources.convention.source_class,
                }
            ),
            "source_paths": sorted(
                [
                    sources.pin_contract.source_path,
                    sources.verifier_outcome.source_path,
                    sources.receipt_diagnostic.source_path,
                    sources.convention.source_path,
                ]
            ),
        },
        "criteria": [
            {
                "criterion_id": "output_a_assigned",
                "description": "Output A must be assigned.",
                "source": sources.pin_contract.source_path,
                "source_class": sources.pin_contract.source_class,
            },
            {
                "criterion_id": "output_a_double_compatible",
                "description": "Output A must be double-compatible.",
                "source": sources.pin_contract.source_path,
                "source_class": sources.pin_contract.source_class,
            },
            {
                "criterion_id": "verify_repair_succeeds",
                "description": (
                    "The repaired body must satisfy the verify_repair "
                    "expected_outcome: succeeded."
                ),
                "source": sources.verifier_outcome.source_path,
                "source_class": sources.verifier_outcome.source_class,
            },
            {
                "criterion_id": "preserve_body_mode",
                "description": "The repair must preserve body-style code.",
                "source": sources.convention.source_path,
                "source_class": sources.convention.source_class,
            },
            {
                "criterion_id": "resolve_target_diagnostics",
                "description": "The repair must resolve the current target diagnostics.",
                "source": sources.receipt_diagnostic.source_path,
                "source_class": sources.receipt_diagnostic.source_class,
            },
            {
                "criterion_id": "remove_unresolved_symbol",
                "description": (
                    "The repaired body must not leave DefinitelyMissingSymbol "
                    "unresolved."
                ),
                "source": sources.receipt_diagnostic.source_path,
                "source_class": sources.receipt_diagnostic.source_class,
            },
        ],
        "unresolved_intent": [
            {
                "intent_id": entry.intent_id,
                "description": entry.description,
                "source_class": entry.source_class,
                "source_path": entry.source_path,
                "reason": entry.reason,
            }
            for entry in sources.unresolved_intent
        ],
    }
    canonical_packet = json.dumps(packet, sort_keys=True, separators=(",", ":"))
    packet["fingerprint"] = (
        f"sha256:{hashlib.sha256(canonical_packet.encode('utf-8')).hexdigest()}"
    )
    return packet


def _validate_sources(sources: AcceptanceCriteriaSources) -> None:
    _validate_source(
        sources.pin_contract,
        source_class="pin_contract",
        source_path=_PIN_SOURCE_PATH,
    )
    _validate_source(
        sources.verifier_outcome,
        source_class="verifier_outcome",
        source_path=_VERIFY_SOURCE_PATH,
    )
    _validate_source(
        sources.receipt_diagnostic,
        source_class="receipt_diagnostic",
        source_path=_DIAGNOSTIC_SOURCE_PATH,
    )
    _validate_source(
        sources.convention,
        source_class="convention",
        source_path=_CONVENTION_SOURCE_PATH,
    )

    if sources.pin_contract.value != {"pins_out": ["A:double"]}:
        raise ValueError("LM5W v1 requires pins_out ['A:double'].")
    if sources.verifier_outcome.value != "succeeded":
        raise ValueError("LM5W v1 requires verifier outcome 'succeeded'.")
    if sources.convention.value != {"mode": "body"}:
        raise ValueError("LM5W v1 requires convention mode 'body'.")
    if (
        not isinstance(sources.receipt_diagnostic.value, list)
        or _TARGET_DIAGNOSTIC not in sources.receipt_diagnostic.value
    ):
        raise ValueError(
            "LM5W v1 requires the DefinitelyMissingSymbol target diagnostic."
        )


def _validate_source(
    source: AcceptanceCriteriaSource,
    *,
    source_class: str,
    source_path: str,
) -> None:
    if source.source_class != source_class:
        raise ValueError(f"Expected source_class {source_class!r}.")
    if source.source_path != source_path:
        raise ValueError(f"Expected source_path {source_path!r}.")


__all__ = (
    "ACCEPTANCE_CRITERIA_PACKET_SCHEMA",
    "AcceptanceCriteriaSource",
    "UnresolvedIntentEntry",
    "AcceptanceCriteriaSources",
    "assemble_acceptance_criteria_packet",
)
