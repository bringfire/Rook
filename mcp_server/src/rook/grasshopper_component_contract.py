"""Pure validation for public Grasshopper component candidate results."""

from __future__ import annotations

import math
from typing import Any


_CANDIDATE_IDENTITY_FIELDS = {
    "guid", "name", "nickName", "description", "category", "subCategory", "sourceKind"
}
_CANDIDATE_NULLABLE_STRINGS = {
    "nickName", "description", "category", "subCategory"
}


def is_canonical_lower_guid(value: Any) -> bool:
    if type(value) is not str or len(value) != 36:
        return False
    parts = value.split("-")
    return (
        [len(part) for part in parts] == [8, 4, 4, 4, 12]
        and all(
            char in "0123456789abcdef"
            for part in parts
            for char in part
        )
    )


def _is_finite_json_number(value: Any) -> bool:
    if type(value) not in {int, float}:
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def valid_component_candidate(candidate: Any, shape: str) -> bool:
    """Validate one closed managed candidate shape without coercion."""
    if type(candidate) is not dict:
        return False
    expected = set(_CANDIDATE_IDENTITY_FIELDS)
    if shape in {"search", "ambiguity"}:
        expected |= {"nativeScore", "matchSource"}
    elif shape != "catalog":
        raise ValueError(f"Unknown Grasshopper candidate shape: {shape}")
    if set(candidate) != expected:
        return False
    if (
        not is_canonical_lower_guid(candidate.get("guid"))
        or type(candidate.get("name")) is not str
        or candidate.get("sourceKind") not in {"compiled", "user_object"}
        or not all(
            type(candidate.get(key)) is str or candidate.get(key) is None
            for key in _CANDIDATE_NULLABLE_STRINGS
        )
    ):
        return False
    if shape == "catalog":
        return True
    if shape == "ambiguity":
        return (
            candidate.get("nativeScore") is None
            and candidate.get("matchSource") == "exact_name"
        )
    return (
        _is_finite_json_number(candidate.get("nativeScore"))
        and candidate.get("matchSource") in {"native_search", "exact_name"}
    )


def project_gh_library_result(arguments: dict[str, Any], result: Any) -> dict:
    """Validate one ordinary managed library response in its exact request context."""
    malformed = {"success": False, "data": "Malformed gh_library response"}
    if type(result) is not dict or type(result.get("success")) is not bool:
        return malformed
    if not result["success"]:
        return result
    data = result.get("data")
    expected_data = {"count", "returnedCount", "totalMatches", "truncated", "components"}
    if type(data) is not dict or set(data) != expected_data:
        return malformed
    count = data["count"]
    returned_count = data["returnedCount"]
    total_matches = data["totalMatches"]
    truncated = data["truncated"]
    components = data["components"]
    if (
        type(count) is not int
        or type(returned_count) is not int
        or type(total_matches) is not int
        or min(count, returned_count, total_matches) < 0
        or type(truncated) is not bool
        or type(components) is not list
        or count != returned_count
        or returned_count != len(components)
        or total_matches < returned_count
        or truncated != (returned_count < total_matches)
    ):
        return malformed
    has_search = "search" in arguments and arguments["search"] != ""
    shape = "search" if has_search else "catalog"
    if not all(valid_component_candidate(candidate, shape) for candidate in components):
        return malformed
    if has_search:
        expected_source = "exact_name" if arguments.get("exact") is True else "native_search"
        if any(candidate["matchSource"] != expected_source for candidate in components):
            return malformed
    return result
