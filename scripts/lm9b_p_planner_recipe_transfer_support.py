"""Deterministic mechanical support for the LM9B-P transfer probe."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, NoReturn

from jsonschema import Draft202012Validator
from rook.validation_kernel.canonical_json import canonical_fingerprint, sha256_prefixed
from rook.validation_kernel.owned_json import own_trusted_json


MAX_RECIPE_BYTES = 1_048_576
MAX_JSON_DEPTH = 64
MAX_INTEGER_TOKEN_CHARS = 1_024


class StrictJsonError(ValueError):
    """A bounded, mechanically classified JSON input failure."""


def fingerprint(value: object) -> str:
    return canonical_fingerprint(own_trusted_json(value))


def fingerprint_without(value: Mapping[str, object], field: str) -> str:
    return fingerprint({key: item for key, item in value.items() if key != field})


def _parse_int(token: str) -> int:
    if len(token) > MAX_INTEGER_TOKEN_CHARS:
        raise StrictJsonError("integer_token_too_long")
    return int(token)


def _reject_float(_token: str) -> NoReturn:
    raise StrictJsonError("non_integer_json_number")


def _reject_constant(_token: str) -> NoReturn:
    raise StrictJsonError("non_finite_json_number")


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJsonError("duplicate_key")
        result[key] = value
    return result


def _json_depth(value: object) -> int:
    maximum = 0
    stack: list[tuple[object, int]] = [(value, 0)]
    while stack:
        current, depth = stack.pop()
        maximum = max(maximum, depth)
        if isinstance(current, dict):
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)
    return maximum


def parse_strict_json(raw: bytes) -> object:
    if len(raw) > MAX_RECIPE_BYTES:
        raise StrictJsonError("recipe_input_bytes_exceeded")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise StrictJsonError("utf8_bom")
    try:
        decoded = raw.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise StrictJsonError("invalid_utf8") from exc
    try:
        value = json.loads(
            decoded,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_int=_parse_int,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except StrictJsonError:
        raise
    except json.JSONDecodeError as exc:
        raise StrictJsonError("invalid_json") from exc
    except (RecursionError, ValueError) as exc:
        raise StrictJsonError("invalid_json") from exc
    if _json_depth(value) > MAX_JSON_DEPTH:
        raise StrictJsonError("json_depth_exceeded")
    return value


def resolve_json_pointer(value: object, pointer: str) -> object:
    if pointer == "":
        return value
    if not pointer.startswith("/"):
        raise ValueError("invalid_json_pointer")
    current = value
    for encoded in pointer[1:].split("/"):
        token = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit():
            index = int(token)
            if index >= len(current):
                raise KeyError(pointer)
            current = current[index]
        else:
            raise KeyError(pointer)
    return current


@dataclass(frozen=True)
class NormalizationRow:
    path_pattern: str
    sort_kind: str
    field: str | None
    admission: str
    matching: str


@dataclass(frozen=True)
class NormalizationProfile:
    profile_id: str
    profile_fingerprint: str
    rows: tuple[NormalizationRow, ...]


def load_normalization_profile(path: Path) -> NormalizationProfile:
    value = parse_strict_json(Path(path).read_bytes())
    if not isinstance(value, dict):
        raise ValueError("normalization profile must be an object")
    if value.get("profile_fingerprint") != fingerprint_without(
        value, "profile_fingerprint"
    ):
        raise ValueError("normalization profile fingerprint mismatch")
    rows = tuple(
        NormalizationRow(
            path_pattern=item["path_pattern"],
            sort_kind=item["sort_kind"],
            field=item.get("field"),
            admission=item["admission"],
            matching=item["matching"],
        )
        for item in value["rows"]
    )
    return NormalizationProfile(
        profile_id=value["profile_id"],
        profile_fingerprint=value["profile_fingerprint"],
        rows=rows,
    )


def _pointer_parts(pointer: str) -> tuple[str, ...]:
    if not pointer:
        return ()
    return tuple(pointer[1:].split("/"))


def _matches(pattern: tuple[str, ...], path: tuple[str, ...]) -> bool:
    if not pattern:
        return not path
    head, *tail = pattern
    if head == "**":
        return _matches(tuple(tail), path) or (
            bool(path) and _matches(pattern, path[1:])
        )
    if not path or (head != "*" and head != path[0]):
        return False
    return _matches(tuple(tail), path[1:])


def _lists(value: object) -> list[tuple[tuple[str, ...], list[object]]]:
    found: list[tuple[tuple[str, ...], list[object]]] = []
    stack: list[tuple[tuple[str, ...], object]] = [((), value)]
    while stack:
        path, current = stack.pop()
        if isinstance(current, list):
            found.append((path, current))
            stack.extend((path + (str(i),), item) for i, item in enumerate(current))
        elif isinstance(current, dict):
            stack.extend((path + (key,), item) for key, item in current.items())
    return found


def _utf16(value: str) -> bytes:
    return value.encode("utf-16-be")


_REFERENCE_RANK = {
    "artifact_value": 0,
    "policy_rule": 1,
    "receipt": 2,
    "clause": 3,
    "assumption": 4,
    "derived_fact": 5,
    "unresolved_intent": 6,
    "shape": 7,
    "capability": 8,
    "worker_slot": 9,
}


def _reference_key(item: object) -> tuple[object, ...]:
    if not isinstance(item, dict) or item.get("kind") not in _REFERENCE_RANK:
        raise ValueError("invalid semantic reference")
    kind = item["kind"]
    names = {
        "artifact_value": ("artifact_id", "json_pointer"),
        "policy_rule": ("artifact_id", "json_pointer"),
        "receipt": ("artifact_id", "receipt_id", "receipt_fingerprint"),
        "clause": ("clause_id",),
        "assumption": ("assumption_id",),
        "derived_fact": ("derived_fact_id",),
        "unresolved_intent": ("intent_id",),
        "shape": ("shape_id",),
        "capability": ("capability_id",),
        "worker_slot": ("worker_slot_id",),
    }[kind]
    return (_REFERENCE_RANK[kind], *(_utf16(str(item[name])) for name in names))


def _sort_key(row: NormalizationRow, item: object) -> object:
    if row.sort_kind == "semantic_reference":
        return _reference_key(item)
    if row.sort_kind == "scalar_utf16":
        return _utf16(str(item))
    if row.sort_kind == "field" and row.field and isinstance(item, dict):
        return _utf16(str(item[row.field]))
    raise ValueError("invalid normalization row")


def normalize_recipe(recipe: Mapping[str, object], profile: NormalizationProfile) -> dict[str, object]:
    normalized = copy.deepcopy(dict(recipe))
    list_rows = _lists(normalized)
    for row in profile.rows:
        pattern = _pointer_parts(row.path_pattern)
        matched = [items for path, items in list_rows if _matches(pattern, path)]
        if not matched and row.matching == "required_container":
            raise ValueError(f"required normalization path absent: {row.path_pattern}")
        for items in matched:
            if row.admission == "empty_only":
                if items:
                    raise ValueError(f"profile feature not admitted: {row.path_pattern}")
                continue
            keyed = [(_sort_key(row, item), item) for item in items]
            keys = [key for key, _ in keyed]
            if len(set(keys)) != len(keys):
                raise ValueError(f"duplicate normalization identity: {row.path_pattern}")
            items[:] = [item for _, item in sorted(keyed, key=lambda pair: pair[0])]
    return normalized


@dataclass(frozen=True)
class MechanicalDiagnostic:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class MechanicalGateResult:
    status: str
    diagnostics: tuple[MechanicalDiagnostic, ...]
    final_recipe_bytes: bytes | None
    recipe_value_fingerprint: str | None
    ratified_recipe_fingerprint: str | None
    historical_recipe_fingerprint: str | None


def _walk(value: object):
    stack = [("", value)]
    while stack:
        path, current = stack.pop()
        yield path, current
        if isinstance(current, dict):
            stack.extend((f"{path}/{key}", item) for key, item in current.items())
        elif isinstance(current, list):
            stack.extend((f"{path}/{i}", item) for i, item in enumerate(current))


def _reject(code: str, path: str, message: str) -> MechanicalGateResult:
    return MechanicalGateResult(
        status="probe_mechanically_rejected",
        diagnostics=(MechanicalDiagnostic(code, path, message),),
        final_recipe_bytes=None,
        recipe_value_fingerprint=None,
        ratified_recipe_fingerprint=None,
        historical_recipe_fingerprint=None,
    )


def evaluate_mechanical_gate(
    *,
    recipe_bytes: bytes,
    authority: object,
    recipe_schema: Mapping[str, object],
    normalization_profile: NormalizationProfile,
) -> MechanicalGateResult:
    try:
        recipe = parse_strict_json(recipe_bytes)
    except StrictJsonError as exc:
        return _reject(str(exc), "", str(exc))
    if not isinstance(recipe, dict):
        return _reject("recipe_not_object", "", "recipe must be an object")
    errors = sorted(Draft202012Validator(recipe_schema).iter_errors(recipe), key=lambda e: list(e.path))
    if errors:
        error = errors[0]
        path = "".join(f"/{item}" for item in error.path)
        return _reject("recipe_schema_failed", path, error.message)

    artifacts = authority.artifacts
    descriptors = [recipe["source_task"], *recipe["authority_artifacts"]]
    for descriptor in descriptors:
        artifact = artifacts.get(descriptor["artifact_id"])
        if artifact is None or descriptor["fingerprint"] != artifact["artifact_fingerprint"]:
            return _reject("authority_binding_failed", "", descriptor["artifact_id"])

    for path, item in _walk(recipe):
        if not isinstance(item, dict):
            continue
        if item.get("kind") == "artifact_value":
            artifact = artifacts.get(item.get("artifact_id"))
            if artifact is None:
                return _reject("unknown_artifact", path, str(item.get("artifact_id")))
            matches = [
                binding
                for binding in artifact.get("value_bindings", [])
                if binding["json_pointer"] == item.get("json_pointer")
            ]
            if len(matches) != 1:
                return _reject("artifact_pointer_unbound", path, str(item.get("json_pointer")))
        elif item.get("kind") == "policy_rule":
            artifact = artifacts.get(item.get("artifact_id"))
            try:
                resolve_json_pointer(artifact, item["json_pointer"])
            except (KeyError, TypeError, ValueError):
                return _reject("policy_pointer_unbound", path, str(item.get("json_pointer")))

    bindings = {
        "shape": authority.vocabularies["semantic_authority_code_vocabulary"],
        "required_capabilities": authority.vocabularies[
            "semantic_capability_code_vocabulary"
        ],
        "worker_slots": authority.vocabularies["worker_slot_code_vocabulary"],
    }
    for field, vocabulary in bindings.items():
        if recipe[field]["vocabulary_version"] != vocabulary["vocabulary_version"] or recipe[field][
            "vocabulary_fingerprint"
        ] != vocabulary["vocabulary_fingerprint"]:
            return _reject("vocabulary_binding_failed", f"/{field}", field)

    materiality = {
        item["code"]
        for item in authority.vocabularies["semantic_materiality_code_vocabulary"]["entries"]
    }
    value_schemas = {
        item["schema"]
        for item in authority.vocabularies["semantic_value_schema_registry"]["entries"]
    }
    for assumption in recipe["assumptions"]:
        if not set(assumption["affects"]).issubset(materiality):
            return _reject("unknown_materiality_code", "/assumptions", assumption["assumption_id"])
        if assumption["typed_value"]["schema"] not in value_schemas:
            return _reject("unknown_value_schema", "/assumptions", assumption["assumption_id"])
    if recipe["worker_slots"]["entries"]:
        return _reject("profile_feature_not_admitted", "/worker_slots/entries", "worker slots")

    recipe_value_fingerprint = fingerprint(recipe)
    claimed = recipe["recipe_fingerprint"]
    projection = {key: value for key, value in recipe.items() if key != "recipe_fingerprint"}
    try:
        normalized = normalize_recipe(projection, normalization_profile)
    except ValueError as exc:
        return _reject("recipe_normalization_failed", "", str(exc))
    if normalized != projection:
        return _reject("recipe_not_canonical_normal_form", "", "set-like collection order")
    ratified = fingerprint(normalized)
    historical = fingerprint(projection)
    if claimed != ratified:
        return MechanicalGateResult(
            status="fingerprint_resubmission_required",
            diagnostics=(MechanicalDiagnostic("recipe_fingerprint_mismatch", "/recipe_fingerprint", ratified),),
            final_recipe_bytes=None,
            recipe_value_fingerprint=recipe_value_fingerprint,
            ratified_recipe_fingerprint=ratified,
            historical_recipe_fingerprint=historical,
        )
    if ratified != historical:
        return _reject("historical_fingerprint_mismatch", "", "recipe not compatible")
    return MechanicalGateResult(
        status="mechanically_accepted",
        diagnostics=(),
        final_recipe_bytes=recipe_bytes,
        recipe_value_fingerprint=recipe_value_fingerprint,
        ratified_recipe_fingerprint=ratified,
        historical_recipe_fingerprint=historical,
    )


__all__ = (
    "MechanicalDiagnostic",
    "MechanicalGateResult",
    "NormalizationProfile",
    "NormalizationRow",
    "StrictJsonError",
    "evaluate_mechanical_gate",
    "fingerprint",
    "fingerprint_without",
    "load_normalization_profile",
    "normalize_recipe",
    "parse_strict_json",
    "resolve_json_pointer",
    "sha256_prefixed",
)
