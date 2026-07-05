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
    unresolved_intent = _render_unresolved_intent(sources.unresolved_intent)

    source_classes = {
        sources.pin_contract.source_class,
        sources.verifier_outcome.source_class,
        sources.receipt_diagnostic.source_class,
        sources.convention.source_class,
    }
    source_paths = {
        sources.pin_contract.source_path,
        sources.verifier_outcome.source_path,
        sources.receipt_diagnostic.source_path,
        sources.convention.source_path,
    }
    for entry in unresolved_intent:
        source_classes.add(entry["source_class"])
        source_paths.add(entry["source_path"])

    packet = {
        "schema": ACCEPTANCE_CRITERIA_PACKET_SCHEMA,
        "source_set": {
            "source_classes": sorted(source_classes),
            "source_paths": sorted(source_paths),
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
        "unresolved_intent": unresolved_intent,
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

    _validate_pin_contract(sources.pin_contract.value)
    if sources.verifier_outcome.value != "succeeded":
        raise ValueError("LM5W v1 requires verifier outcome 'succeeded'.")
    if sources.convention.value != {"mode": "body"}:
        raise ValueError("LM5W v1 requires convention mode 'body'.")
    _validate_receipt_diagnostic(sources.receipt_diagnostic.value)
    _render_unresolved_intent(sources.unresolved_intent)


def _validate_pin_contract(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"pins_out"}:
        raise ValueError(
            "LM5W v1 pin_contract value must contain exactly the pins_out field."
        )
    pins_out = value["pins_out"]
    if not isinstance(pins_out, list) or len(pins_out) != 1:
        raise ValueError("LM5W v1 requires exactly one output pin.")
    pin = pins_out[0]
    if not isinstance(pin, str) or ":" not in pin:
        raise ValueError("LM5W v1 pins_out entries must use <name>:<type> format.")
    if pin != "A:double":
        raise ValueError("LM5W v1 requires output pin A:double.")


def _validate_receipt_diagnostic(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError("LM5W v1 requires a non-empty receipt diagnostic list.")
    if not all(isinstance(diagnostic, str) for diagnostic in value):
        raise ValueError("LM5W v1 receipt diagnostics must be strings.")
    if _TARGET_DIAGNOSTIC not in value:
        raise ValueError(
            "LM5W v1 requires the DefinitelyMissingSymbol target diagnostic."
        )
    if value != [_TARGET_DIAGNOSTIC]:
        raise ValueError(
            "LM5W v1 requires exactly one target diagnostic: DefinitelyMissingSymbol."
        )


def _render_unresolved_intent(
    unresolved_intent: tuple[UnresolvedIntentEntry, ...],
) -> list[dict[str, str]]:
    rendered = []
    for entry in unresolved_intent:
        if not isinstance(entry, UnresolvedIntentEntry):
            raise ValueError("unresolved_intent entries must be UnresolvedIntentEntry")
        if entry.source_class != "planner_user_intent":
            raise ValueError(
                "unresolved_intent entries must use source_class planner_user_intent."
            )
        for field in (
            "intent_id",
            "description",
            "source_path",
            "reason",
        ):
            value = getattr(entry, field)
            if not isinstance(value, str) or not value:
                raise ValueError(
                    f"unresolved_intent entry {field} must be a non-empty string."
                )
        rendered.append(
            {
                "intent_id": entry.intent_id,
                "description": entry.description,
                "source_class": entry.source_class,
                "source_path": entry.source_path,
                "reason": entry.reason,
            }
        )
    return sorted(rendered, key=lambda entry: entry["intent_id"])


def _validate_source(
    source: AcceptanceCriteriaSource,
    *,
    source_class: str,
    source_path: str,
) -> None:
    if source.source_class != source_class:
        raise ValueError(f"expected source class {source_class!r}.")
    if not isinstance(source.source_path, str) or not source.source_path:
        raise ValueError(f"Expected non-empty string source_path for {source_path!r}.")


__all__ = (
    "ACCEPTANCE_CRITERIA_PACKET_SCHEMA",
    "AcceptanceCriteriaSource",
    "UnresolvedIntentEntry",
    "AcceptanceCriteriaSources",
    "assemble_acceptance_criteria_packet",
)
