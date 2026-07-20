"""Deterministic mechanical support for the LM9B-P transfer probe."""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, NoReturn

from jsonschema import Draft202012Validator
from rook.validation_kernel.canonical_json import canonical_fingerprint, sha256_prefixed
from rook.validation_kernel.owned_json import own_trusted_json


MAX_RECIPE_BYTES = 1_048_576
MAX_JSON_DEPTH = 64
MAX_INTEGER_TOKEN_CHARS = 1_024
_MACHINE_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:[._:-][a-z0-9]+)*$")
_MACHINE_SCALAR_FIELDS = {
    "artifact_kind",
    "authority_code",
    "capability_code",
    "delegate_kind",
    "kind",
    "schema",
    "semantic_key",
    "value_schema",
    "vocabulary_version",
}


class StrictJsonError(ValueError):
    """A bounded, mechanically classified JSON input failure."""


def fingerprint(value: object) -> str:
    return canonical_fingerprint(own_trusted_json(_json_builtins(value)))


def _json_builtins(value: object) -> object:
    if isinstance(value, MappingABC):
        return {key: _json_builtins(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_builtins(item) for item in value]
    return value


def fingerprint_without(value: Mapping[str, object], field: str) -> str:
    return fingerprint({key: item for key, item in value.items() if key != field})


def validate_exclusion_policy(
    value: Mapping[str, object],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    expected_fields = {
        "schema",
        "policy_id",
        "forbidden_recipe_markers",
        "forbidden_request_markers",
        "excluded_input_roles",
        "policy_fingerprint",
    }
    if set(value) != expected_fields:
        raise ValueError("invalid exclusion policy shape")
    if value.get("schema") != "rook.lm9b_p.planner_exclusion_policy:v1":
        raise ValueError("invalid exclusion policy schema")
    if value.get("policy_id") != "lm9b_p.planner_exclusion_policy:v1":
        raise ValueError("invalid exclusion policy ID")
    if value.get("policy_fingerprint") != fingerprint_without(
        value, "policy_fingerprint"
    ):
        raise ValueError("exclusion policy fingerprint mismatch")

    collections: dict[str, tuple[str, ...]] = {}
    for field in (
        "forbidden_recipe_markers",
        "forbidden_request_markers",
        "excluded_input_roles",
    ):
        raw_items = value.get(field)
        if not isinstance(raw_items, (list, tuple)) or not all(
            isinstance(item, str) and item for item in raw_items
        ):
            raise ValueError(f"invalid exclusion policy {field}")
        items = tuple(raw_items)
        if len(set(items)) != len(items) or items != tuple(sorted(items)):
            raise ValueError(f"noncanonical exclusion policy {field}")
        collections[field] = items
    return (
        collections["forbidden_recipe_markers"],
        collections["forbidden_request_markers"],
    )


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
        if isinstance(current, MappingABC) and token in current:
            current = current[token]
        elif isinstance(current, (list, tuple)) and token.isdigit():
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


def normalization_profile_from_value(
    value: Mapping[str, object],
) -> NormalizationProfile:
    if not isinstance(value, Mapping):
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


def load_normalization_profile(path: Path) -> NormalizationProfile:
    value = parse_strict_json(Path(path).read_bytes())
    if not isinstance(value, dict):
        raise ValueError("normalization profile must be an object")
    return normalization_profile_from_value(value)


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
    status: Literal[
        "probe_mechanically_rejected",
        "fingerprint_resubmission_required",
        "mechanically_accepted",
    ]
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


def _issue(code: str, path: str, message: str) -> MechanicalDiagnostic:
    return MechanicalDiagnostic(code=code, path=path, message=message)


def _machine_identifier_issue(recipe: Mapping[str, object]) -> MechanicalDiagnostic | None:
    candidates: list[tuple[str, object]] = []
    for path, current in _walk(recipe):
        if not isinstance(current, dict):
            continue
        for key, value in current.items():
            field_path = f"{path}/{key}"
            if key.endswith("_id") or key in _MACHINE_SCALAR_FIELDS:
                if value is not None:
                    candidates.append((field_path, value))
            elif key.endswith("_ids") or key == "affects":
                if isinstance(value, list):
                    candidates.extend(
                        (f"{field_path}/{index}", item)
                        for index, item in enumerate(value)
                    )
    for path, value in sorted(candidates, key=lambda item: item[0]):
        if not isinstance(value, str) or _MACHINE_IDENTIFIER.fullmatch(value) is None:
            return _issue(
                "invalid_machine_identifier",
                path,
                "machine identifier does not match the ratified grammar",
            )
    return None


def _structural_integrity_issue(
    recipe: Mapping[str, object], authority: object
) -> MechanicalDiagnostic | None:
    machine_issue = _machine_identifier_issue(recipe)
    if machine_issue is not None:
        return machine_issue

    symbols: dict[str, dict[str, tuple[str, str]]] = {
        "clause": {},
        "assumption": {},
        "derived_fact": {},
        "unresolved_intent": {},
        "shape": {},
        "capability": {},
        "worker_slot": {},
    }

    def declare(
        identifier: str, namespace: str, kind: str, path: str
    ) -> MechanicalDiagnostic | None:
        prior = symbols[namespace].get(identifier)
        if prior is not None:
            return _issue(
                "duplicate_identifier",
                path,
                f"identifier duplicates {prior[1]}",
            )
        symbols[namespace][identifier] = (kind, path)
        return None

    declarations: list[tuple[str, str, str, str]] = [
        (recipe["goal"]["clause_id"], "clause", "goal", "/goal/clause_id")
    ]
    for collection, kind in (
        ("requires", "requires"),
        ("invariants", "invariants"),
    ):
        declarations.extend(
            (item["clause_id"], "clause", kind, f"/{collection}/{index}/clause_id")
            for index, item in enumerate(recipe[collection])
        )
    for index, maintained in enumerate(recipe["maintains"]):
        declarations.append(
            (
                maintained["clause_id"],
                "clause",
                "maintains",
                f"/maintains/{index}/clause_id",
            )
        )
        declarations.extend(
            (
                item["clause_id"],
                "clause",
                "canonicalization",
                f"/maintains/{index}/canonicalization/{nested}/clause_id",
            )
            for nested, item in enumerate(maintained["canonicalization"])
        )
        declarations.extend(
            (
                item["clause_id"],
                "clause",
                "postcondition",
                f"/maintains/{index}/postconditions/{nested}/clause_id",
            )
            for nested, item in enumerate(maintained["postconditions"])
        )
    for collection, id_field, kind in (
        ("assumptions", "assumption_id", "assumption"),
        ("derived_facts", "derived_fact_id", "derived_fact"),
        ("unresolved_intent", "intent_id", "unresolved_intent"),
    ):
        declarations.extend(
            (item[id_field], kind, kind, f"/{collection}/{index}/{id_field}")
            for index, item in enumerate(recipe[collection])
        )
    for section in ("self", "delegates", "prohibited"):
        declarations.extend(
            (
                item["shape_id"],
                "shape",
                "shape",
                f"/shape/{section}/{index}/shape_id",
            )
            for index, item in enumerate(recipe["shape"][section])
        )
    declarations.extend(
        (
            item["capability_id"],
            "capability",
            "capability",
            f"/required_capabilities/entries/{index}/capability_id",
        )
        for index, item in enumerate(recipe["required_capabilities"]["entries"])
    )
    declarations.extend(
        (
            item["worker_slot_id"],
            "worker_slot",
            "worker_slot",
            f"/worker_slots/entries/{index}/worker_slot_id",
        )
        for index, item in enumerate(recipe["worker_slots"]["entries"])
    )
    for identifier, namespace, kind, path in declarations:
        duplicate = declare(identifier, namespace, kind, path)
        if duplicate is not None:
            return duplicate

    def require_support_or_synthesis(
        clause: Mapping[str, object], path: str
    ) -> MechanicalDiagnostic | None:
        has_direct_support = bool(clause["source_refs"]) or bool(
            clause["assumption_refs"]
        )
        if "derived_fact_refs" in clause:
            has_direct_support = has_direct_support or bool(
                clause["derived_fact_refs"]
            )
        if not has_direct_support and clause["synthesis"] is None:
            return _issue(
                "clause_support_missing",
                path,
                "clause without direct support requires synthesis",
            )
        return None

    clause_locations: list[tuple[Mapping[str, object], str]] = [
        (recipe["goal"], "/goal")
    ]
    clause_locations.extend(
        (item, f"/requires/{index}")
        for index, item in enumerate(recipe["requires"])
    )
    clause_locations.extend(
        (item, f"/invariants/{index}")
        for index, item in enumerate(recipe["invariants"])
    )
    for index, maintained in enumerate(recipe["maintains"]):
        clause_locations.append((maintained, f"/maintains/{index}"))
        clause_locations.extend(
            (item, f"/maintains/{index}/canonicalization/{nested}")
            for nested, item in enumerate(maintained["canonicalization"])
        )
        clause_locations.extend(
            (item, f"/maintains/{index}/postconditions/{nested}")
            for nested, item in enumerate(maintained["postconditions"])
        )
    for clause, path in clause_locations:
        support_issue = require_support_or_synthesis(clause, path)
        if support_issue is not None:
            return support_issue

    descriptors = [recipe["source_task"], *recipe["authority_artifacts"]]
    descriptor_by_id: dict[str, Mapping[str, object]] = {}
    for index, descriptor in enumerate(descriptors):
        artifact_id = descriptor["artifact_id"]
        path = "/source_task" if index == 0 else f"/authority_artifacts/{index - 1}"
        if artifact_id in descriptor_by_id:
            return _issue(
                "duplicate_identifier",
                f"{path}/artifact_id",
                "artifact descriptor identity is duplicated",
            )
        descriptor_by_id[artifact_id] = descriptor

    local_reference_fields = {
        "assumption": ("assumption_id", "assumption"),
        "derived_fact": ("derived_fact_id", "derived_fact"),
        "clause": ("clause_id", "clause"),
        "unresolved_intent": ("intent_id", "unresolved_intent"),
        "shape": ("shape_id", "shape"),
        "capability": ("capability_id", "capability"),
        "worker_slot": ("worker_slot_id", "worker_slot"),
    }
    referenced_artifacts: set[str] = set()
    for path, item in sorted(_walk(recipe), key=lambda pair: pair[0]):
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        if kind in local_reference_fields:
            id_field, namespace = local_reference_fields[kind]
            target = symbols[namespace].get(item[id_field])
            if target is None:
                return _issue(
                    "dangling_local_reference",
                    path,
                    "local semantic reference does not resolve to its declared kind",
                )
        if kind not in ("artifact_value", "policy_rule"):
            continue
        artifact_id = item["artifact_id"]
        descriptor = descriptor_by_id.get(artifact_id)
        if descriptor is None:
            code = (
                "unknown_artifact"
                if artifact_id not in authority.artifacts
                else "authority_descriptor_unbound"
            )
            return _issue(
                code,
                path,
                "external reference has no recipe-bound authority descriptor",
            )
        referenced_artifacts.add(artifact_id)
        if kind == "policy_rule":
            if descriptor["artifact_kind"] != "planning_policy":
                return _issue(
                    "authority_descriptor_kind_mismatch",
                    path,
                    "policy reference does not target a planning-policy descriptor",
                )
            pointer = item["json_pointer"]
            if re.fullmatch(r"/rules/[a-z0-9]+(?:[._:-][a-z0-9]+)*", pointer) is None:
                return _issue(
                    "policy_pointer_outside_rules",
                    f"{path}/json_pointer",
                    "policy reference must target exactly one stable rule",
                )
            policy = authority.artifacts.get(artifact_id)
            try:
                rule = resolve_json_pointer(policy, pointer)
            except (KeyError, TypeError, ValueError):
                rule = None
            if not isinstance(rule, MappingABC) or rule.get("rule_id") != pointer.removeprefix(
                "/rules/"
            ):
                return _issue(
                    "policy_pointer_unbound",
                    f"{path}/json_pointer",
                    "policy reference does not resolve to its exact stable rule",
                )
        elif descriptor["artifact_kind"] not in (
            "task_envelope",
            "environment_snapshot",
        ):
            return _issue(
                "authority_descriptor_kind_mismatch",
                path,
                "artifact-value reference targets an incompatible descriptor",
            )

    for index, descriptor in enumerate(recipe["authority_artifacts"]):
        if descriptor["artifact_id"] not in referenced_artifacts:
            return _issue(
                "unreferenced_authority_descriptor",
                f"/authority_artifacts/{index}",
                "recipe-bound authority descriptor has no semantic reference",
            )

    def require_targets(
        values: object, namespace: str, allowed_kinds: set[str], path: str
    ) -> MechanicalDiagnostic | None:
        for index, identifier in enumerate(values):
            target = symbols[namespace].get(identifier)
            if target is None or target[0] not in allowed_kinds:
                return _issue(
                    "dangling_local_reference",
                    f"{path}/{index}",
                    "schema-defined identity link does not resolve to an allowed kind",
                )
        return None

    projection = recipe["goal"]["projected_into"]
    links = (
        (projection["maintains_clause_ids"], "clause", {"maintains"}, "/goal/projected_into/maintains_clause_ids"),
        (projection["invariant_clause_ids"], "clause", {"invariants"}, "/goal/projected_into/invariant_clause_ids"),
        (projection["unresolved_intent_ids"], "unresolved_intent", {"unresolved_intent"}, "/goal/projected_into/unresolved_intent_ids"),
    )
    for values, namespace, kinds, path in links:
        issue = require_targets(values, namespace, kinds, path)
        if issue is not None:
            return issue
    for index, requirement in enumerate(recipe["requires"]):
        issue = require_targets(
            requirement["supports_clause_ids"],
            "clause",
            {"maintains", "invariants"},
            f"/requires/{index}/supports_clause_ids",
        )
        if issue is not None:
            return issue
    for index, maintained in enumerate(recipe["maintains"]):
        parent_id = maintained["clause_id"]
        for nested, item in enumerate(maintained["canonicalization"]):
            base_path = f"/maintains/{index}/canonicalization/{nested}"
            if item["applies_to_clause_ids"] != [parent_id]:
                return _issue(
                    "nested_parent_mismatch",
                    f"{base_path}/applies_to_clause_ids",
                    "canonicalization must apply to its containing maintains clause",
                )
            if item["inherited_support_from"] not in ([], [parent_id]):
                return _issue(
                    "nested_parent_mismatch",
                    f"{base_path}/inherited_support_from",
                    "canonicalization may inherit only from its containing parent",
                )
        for nested, item in enumerate(maintained["postconditions"]):
            inherited = item["inherited_support_from"]
            if inherited not in ([], [parent_id]):
                return _issue(
                    "nested_parent_mismatch",
                    f"/maintains/{index}/postconditions/{nested}/inherited_support_from",
                    "postcondition may inherit only from its containing parent",
                )
    for index, unresolved in enumerate(recipe["unresolved_intent"]):
        issue = require_targets(
            unresolved["affected_clause_ids"],
            "clause",
            {"goal", "maintains", "invariants"},
            f"/unresolved_intent/{index}/affected_clause_ids",
        )
        if issue is not None:
            return issue

    authority_codes = {
        item["code"]: item
        for item in authority.vocabularies[
            "semantic_authority_code_vocabulary"
        ]["entries"]
    }
    for section in ("self", "delegates", "prohibited"):
        for index, item in enumerate(recipe["shape"][section]):
            entry = authority_codes.get(item["authority_code"])
            path = f"/shape/{section}/{index}/authority_code"
            if entry is None:
                return _issue(
                    "unknown_vocabulary_code", path, "unknown semantic authority code"
                )
            if section not in entry["allowed_shape_sections"]:
                return _issue(
                    "vocabulary_code_context_mismatch",
                    path,
                    "semantic authority code is not allowed in this shape section",
                )
            if section == "delegates" and item["delegate_kind"] not in entry[
                "allowed_delegate_kinds"
            ]:
                return _issue(
                    "vocabulary_code_context_mismatch",
                    path,
                    "semantic authority code does not permit this delegate kind",
                )
            if section == "delegates" and bool(item["worker_slot_id"]) != bool(
                entry["requires_worker_slot"]
            ):
                return _issue(
                    "vocabulary_code_context_mismatch",
                    path,
                    "semantic authority code worker-slot requirement is not satisfied",
                )

    capability_codes = {
        item["code"]: item
        for item in authority.vocabularies[
            "semantic_capability_code_vocabulary"
        ]["entries"]
    }
    for index, item in enumerate(recipe["required_capabilities"]["entries"]):
        entry = capability_codes.get(item["capability_code"])
        path = f"/required_capabilities/entries/{index}/capability_code"
        if entry is None:
            return _issue(
                "unknown_vocabulary_code", path, "unknown semantic capability code"
            )
        issue = require_targets(
            item["supports_clause_ids"],
            "clause",
            set(entry["permitted_supporting_clause_kinds"]),
            f"/required_capabilities/entries/{index}/supports_clause_ids",
        )
        if issue is not None:
            return issue
    return None


def evaluate_mechanical_gate(
    *,
    recipe_bytes: bytes,
    authority: object,
    recipe_schema: Mapping[str, object],
    normalization_profile: NormalizationProfile,
    exclusion_policy: Mapping[str, object],
) -> MechanicalGateResult:
    try:
        forbidden_recipe_markers, _ = validate_exclusion_policy(exclusion_policy)
    except ValueError as exc:
        return _reject("invalid_exclusion_policy", "/exclusion_policy", str(exc))
    if exclusion_policy != getattr(authority, "exclusion_policy", None):
        return _reject(
            "invalid_exclusion_policy",
            "/exclusion_policy",
            "exclusion policy is not the frozen authority input",
        )
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

    structural_issue = _structural_integrity_issue(recipe, authority)
    if structural_issue is not None:
        return _reject(
            structural_issue.code,
            structural_issue.path,
            structural_issue.message,
        )

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
    for unresolved in recipe["unresolved_intent"]:
        if unresolved["value_schema"] not in value_schemas:
            return _reject(
                "unknown_value_schema",
                "/unresolved_intent",
                unresolved["intent_id"],
            )
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
    for path, item in _walk(recipe):
        if isinstance(item, str):
            folded = item.casefold()
            if any(marker.casefold() in folded for marker in forbidden_recipe_markers):
                return _reject(
                    "forbidden_context_marker",
                    path,
                    "submitted recipe contains a forbidden control marker",
                )
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
    "normalization_profile_from_value",
    "normalize_recipe",
    "parse_strict_json",
    "resolve_json_pointer",
    "sha256_prefixed",
    "validate_exclusion_policy",
)
