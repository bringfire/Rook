from __future__ import annotations

from typing import Any


IDENTITY_FIELDS = (
    "relationship",
    "fromFeature",
    "toFeature",
    "graphSource",
    "graphRevision",
    "pose",
)

METADATA_FIELDS = (
    "contactKind",
    "provenance",
    "status",
)

CONTRACT_FIELDS = (*IDENTITY_FIELDS, *METADATA_FIELDS)


def _normalize_fact(fact: dict[str, Any]) -> dict[str, Any]:
    return {field: fact.get(field) for field in CONTRACT_FIELDS}


def _identity(fact: dict[str, Any]) -> dict[str, Any]:
    return {field: fact.get(field) for field in IDENTITY_FIELDS}


def _identity_key(fact: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(fact.get(field) for field in IDENTITY_FIELDS)


def _metadata_delta(expected: dict[str, Any], actual: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    expected_delta: dict[str, Any] = {}
    actual_delta: dict[str, Any] = {}
    for field in METADATA_FIELDS:
        expected_value = expected.get(field)
        actual_value = actual.get(field)
        if expected_value != actual_value:
            expected_delta[field] = expected_value
            actual_delta[field] = actual_value
    return expected_delta, actual_delta


def compare_roundtrip(
    *,
    expected_facts: list[dict[str, Any]],
    actual_facts: list[dict[str, Any]],
    context_text: str,
    required_substrings: list[str],
) -> dict[str, Any]:
    expected_by_key = {_identity_key(fact): _normalize_fact(fact) for fact in expected_facts}
    actual_by_key = {_identity_key(fact): _normalize_fact(fact) for fact in actual_facts}

    missing_facts = [
        expected
        for key, expected in expected_by_key.items()
        if key not in actual_by_key
    ]
    unexpected_facts = [
        actual
        for key, actual in actual_by_key.items()
        if key not in expected_by_key
    ]
    wrong_metadata = []
    for key, expected in expected_by_key.items():
        actual = actual_by_key.get(key)
        if actual is None:
            continue
        expected_delta, actual_delta = _metadata_delta(expected, actual)
        if expected_delta or actual_delta:
            wrong_metadata.append(
                {
                    "identity": _identity(expected),
                    "expected": expected_delta,
                    "actual": actual_delta,
                }
            )

    missing_context_substrings = [
        substring
        for substring in required_substrings
        if substring not in context_text
    ]

    success = not (
        missing_facts
        or unexpected_facts
        or wrong_metadata
        or missing_context_substrings
    )
    return {
        "success": success,
        "missingFacts": missing_facts,
        "unexpectedFacts": unexpected_facts,
        "wrongMetadata": wrong_metadata,
        "missingContextSubstrings": missing_context_substrings,
    }
