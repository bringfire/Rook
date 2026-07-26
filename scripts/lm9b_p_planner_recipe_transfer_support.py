"""Deterministic mechanical support for the LM9B-P transfer probe."""

from __future__ import annotations

import copy
import json
import math
import queue
import re
import sys
import threading
import time
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Mapping, NoReturn, Sequence

from jsonschema import Draft202012Validator
from rook.validation_kernel.canonical_json import canonical_fingerprint, sha256_prefixed
from rook.validation_kernel.owned_json import own_trusted_json


_MCP_SERVER_SRC = Path(__file__).resolve().parents[1] / "mcp_server" / "src"
_SCRIPTS_DIR = Path(__file__).resolve().parent
for _import_path in (str(_MCP_SERVER_SRC), str(_SCRIPTS_DIR)):
    if _import_path not in sys.path:
        sys.path.insert(0, _import_path)

from lm9b_c_compiler_sufficiency_support import (  # noqa: E402
    ProviderCallFailure,
    ProviderTurn,
)


MAX_RECIPE_BYTES = 1_048_576
MAX_JSON_DEPTH = 64
MAX_INTEGER_TOKEN_CHARS = 1_024
PLANNER_MAX_TURNS = 6
PLANNER_MAX_COMPLETION_TOKENS = 16_384
PLANNER_PROVIDER_TIMEOUT_S = 180.0
PLANNER_OVERALL_DEADLINE_S = 600.0
PLANNER_TOKEN_STOP_THRESHOLD = 120_000
PLANNER_COST_STOP_THRESHOLD_USD = 10.0
PLANNER_EVALUATOR_MAX_COMPLETION_TOKENS = 8_192
PLANNER_EVALUATOR_PROVIDER_TIMEOUT_S = 180.0
PLANNER_EVALUATOR_SYSTEM_PROMPT = (
    "Evaluate the submitted Planner recipe only against the visible brief, exact "
    "authority, deterministic findings, and frozen rubric. Do not infer compiler "
    "behavior, use hidden context, repair the recipe, or classify the probe. Submit "
    "exactly one evidence-backed recommendation through submit_planner_evaluation."
)
_PLANNER_RECIPE_ARGUMENT_SOURCE = ("recipe_json", 1, 1_048_576)
_PLANNER_EVALUATION_ARGUMENT_SOURCE = ("evaluation_json", 1, 65_536)
# Authority boundary: the evaluator model is authorized to establish semantic
# fidelity ONLY. Advancement (blocked vs ready) is a deterministic system state
# derived by the controller from the mechanically accepted recipe's explicit
# unresolved_intent - never from a model recommendation.
PLANNER_EVALUATION_RECOMMENDATIONS = (
    "semantically_faithful",
    "semantically_unfaithful",
    "evaluation_inconclusive",
)
PLANNER_EVALUATION_RECOMMENDATION_MEANINGS = {
    "semantically_faithful": (
        "The recipe faithfully represents the brief under the exact authority "
        "context, without invention, contradiction, or unauthorized content. "
        "This verdict says nothing about readiness: blocked-versus-ready is "
        "derived deterministically by the system from the recipe's explicit "
        "unresolved_intent state and is not the evaluator's decision."
    ),
    "semantically_unfaithful": (
        "The recipe contains unauthorized, contradictory, invented, or "
        "otherwise unfaithful content relative to the brief and authority."
    ),
    "evaluation_inconclusive": (
        "The evaluator cannot establish semantic fidelity either way from the "
        "visible evidence."
    ),
}
_PLANNER_EVALUATION_CRITERIA = (
    "brief_fidelity",
    "provenance_fidelity",
    "material_authority",
    "unresolved_intent_honesty",
    "implementation_leakage",
)


def _planner_tool_parameters_from_source() -> dict[str, object]:
    name, minimum, maximum = _PLANNER_RECIPE_ARGUMENT_SOURCE
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            name: {"type": "string", "minLength": minimum, "maxLength": maximum}
        },
        "required": [name],
    }


PLANNER_TOOL_PARAMETERS = _planner_tool_parameters_from_source()


def _planner_evaluation_parameters_from_source() -> dict[str, object]:
    name, minimum, maximum = _PLANNER_EVALUATION_ARGUMENT_SOURCE
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            name: {"type": "string", "minLength": minimum, "maxLength": maximum}
        },
        "required": [name],
    }


PLANNER_EVALUATOR_TOOL_PARAMETERS = _planner_evaluation_parameters_from_source()
PLANNER_EVALUATION_REPORT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "recommendation": {"enum": list(PLANNER_EVALUATION_RECOMMENDATIONS)},
        "evidence": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "criterion_id": {"enum": list(_PLANNER_EVALUATION_CRITERIA)},
                    "finding": {"type": "string", "minLength": 1},
                },
                "required": ["criterion_id", "finding"],
            },
        },
    },
    "required": ["recommendation", "evidence"],
}
_PLANNER_EVALUATION_REPORT_VALIDATOR = Draft202012Validator(
    PLANNER_EVALUATION_REPORT_SCHEMA
)
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


def _finite_float(token: str) -> float:
    # Archive evidence may carry provider-shaped finite floats (e.g. temperature,
    # cost_usd). Accept finite floats but still reject non-finite values, including
    # overflow literals like 1e999 that Python parses to inf.
    value = float(token)
    if not math.isfinite(value):
        raise StrictJsonError("non_finite_json_number")
    return value


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


def _parse_bounded_json(raw: bytes, *, parse_float) -> object:
    # Shared bounded JSON grammar. The strict recipe parser and the archive
    # evidence parser differ ONLY in `parse_float`; every other bound (size,
    # UTF-8, BOM, duplicate keys, integer-token length, non-finite constants,
    # depth) is identical.
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
            parse_float=parse_float,
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


def parse_strict_json(raw: bytes) -> object:
    # Planner-authored recipe ingress: rejects every float.
    return _parse_bounded_json(raw, parse_float=_reject_float)


def parse_archive_json(raw: bytes) -> object:
    # Archive evidence readback: accepts finite floats (provider-shaped values
    # such as temperature and cost_usd), still rejecting non-finite numbers,
    # duplicate keys, and the other strict bounds.
    return _parse_bounded_json(raw, parse_float=_finite_float)


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


@dataclass(frozen=True)
class PlannerTurnRecord:
    turn_index: int
    raw_response: bytes
    tool_arguments: bytes | None
    gate_result: MechanicalGateResult | None
    usage: Mapping[str, object]
    elapsed_ms: int


@dataclass(frozen=True)
class PlannerSessionResult:
    termination: Literal[
        "mechanically_accepted",
        "mechanically_rejected",
        "provider_failure",
        "timeout",
    ]
    turns: tuple[PlannerTurnRecord, ...]
    final_recipe_bytes: bytes | None


@dataclass(frozen=True)
class PlannerEvaluationResult:
    termination: Literal[
        "valid_recommendation",
        "provider_failure",
        "timeout",
        "malformed",
    ]
    recommendation: Literal[
        "semantically_faithful", "semantically_unfaithful", "evaluation_inconclusive"
    ] | None
    evidence: tuple[Mapping[str, object], ...]
    raw_response: bytes | None
    usage: Mapping[str, object] | None
    quiescent: bool = True


@dataclass(frozen=True)
class _BoundedProviderCall:
    response: object | None
    exception: BaseException | None
    timed_out: bool
    quiescent: bool


@dataclass(frozen=True)
class PlannerProviderCallPlan:
    """Controller-owned state used to derive one Planner provider request."""

    turn_index: int
    session_started_monotonic_s: float
    call_started_monotonic_s: float
    elapsed_before_call_s: float
    remaining_before_call_s: float
    provider_timeout_s: float
    preceding_transcript_fingerprint: str
    request_raw_sha256: str
    request_bytes: bytes


def _bounded_provider_call(
    provider: Callable[[dict[str, object]], ProviderTurn],
    request: dict[str, object],
    *,
    timeout_s: float,
) -> _BoundedProviderCall:
    """Invoke one provider call without accepting a result after its deadline."""

    outcomes: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)

    def invoke() -> None:
        try:
            outcomes.put(("response", provider(request)))
        except BaseException as exc:
            outcomes.put(("exception", exc))

    worker = threading.Thread(target=invoke, daemon=True)
    worker.start()
    worker.join(timeout_s)
    if worker.is_alive():
        return _BoundedProviderCall(
            response=None,
            exception=None,
            timed_out=True,
            quiescent=False,
        )
    kind, value = outcomes.get_nowait()
    if kind == "exception":
        assert isinstance(value, BaseException)
        return _BoundedProviderCall(
            response=None,
            exception=value,
            timed_out=False,
            quiescent=True,
        )
    return _BoundedProviderCall(
        response=value,
        exception=None,
        timed_out=False,
        quiescent=True,
    )


def planner_tool_definition() -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": "submit_planner_recipe",
            "description": (
                "Submit one proposed planner recipe as exact UTF-8 JSON text. "
                "A mechanically accepted submission ends the session."
            ),
            "parameters": _planner_tool_parameters_from_source(),
        },
    }


def planner_evaluator_tool_definition() -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": "submit_planner_evaluation",
            "description": (
                "Submit one independent Planner evaluation recommendation with "
                "visible evidence. This recommendation does not classify the probe "
                "and is never returned to the Planner."
            ),
            "parameters": _planner_evaluation_parameters_from_source(),
        },
    }


def build_planner_provider_call_request(
    *,
    messages: Sequence[Mapping[str, object]],
    provider_timeout_s: float,
) -> bytes:
    if (
        type(provider_timeout_s) not in (int, float)
        or not math.isfinite(float(provider_timeout_s))
        or provider_timeout_s <= 0
    ):
        raise ValueError("Planner provider timeout must be positive and finite")
    value = {
        "messages": json.loads(json.dumps(list(messages), ensure_ascii=False)),
        "tools": [planner_tool_definition()],
        "tool_choice": "auto",
        "max_completion_tokens": PLANNER_MAX_COMPLETION_TOKENS,
        "provider_timeout_s": float(provider_timeout_s),
    }
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def build_planner_provider_call_plan(
    *,
    turn_index: int,
    messages: Sequence[Mapping[str, object]],
    session_started_monotonic_s: float,
    call_started_monotonic_s: float,
) -> PlannerProviderCallPlan:
    """Derive the timeout and request from the controller's deadline state."""

    if type(turn_index) is not int or turn_index < 1:
        raise ValueError("Planner call-plan turn index must be positive")
    for label, value in (
        ("session start", session_started_monotonic_s),
        ("call start", call_started_monotonic_s),
    ):
        if type(value) not in (int, float) or not math.isfinite(float(value)):
            raise ValueError(f"Planner {label} must be finite")
    session_start = float(session_started_monotonic_s)
    call_start = float(call_started_monotonic_s)
    elapsed = call_start - session_start
    if elapsed < 0:
        raise ValueError("Planner call cannot precede the session start")
    remaining = PLANNER_OVERALL_DEADLINE_S - elapsed
    if remaining <= 0:
        raise ValueError("Planner call plan has no remaining deadline")
    timeout = min(PLANNER_PROVIDER_TIMEOUT_S, remaining)
    request_bytes = build_planner_provider_call_request(
        messages=messages,
        provider_timeout_s=timeout,
    )
    return PlannerProviderCallPlan(
        turn_index=turn_index,
        session_started_monotonic_s=session_start,
        call_started_monotonic_s=call_start,
        elapsed_before_call_s=elapsed,
        remaining_before_call_s=remaining,
        provider_timeout_s=timeout,
        preceding_transcript_fingerprint=fingerprint(list(messages)),
        request_raw_sha256=sha256_prefixed(request_bytes),
        request_bytes=request_bytes,
    )


def materialize_planner_provider_call_request(
    raw_bytes: bytes,
) -> dict[str, object]:
    value = parse_archive_json(raw_bytes)
    if type(value) is not dict:
        raise ValueError("Planner provider request must be an object")
    rebuilt = build_planner_provider_call_request(
        messages=value.get("messages", []),
        provider_timeout_s=value.get("provider_timeout_s"),
    )
    if rebuilt != raw_bytes:
        raise ValueError("Planner provider request differs from builder contract")
    return json.loads(raw_bytes)


def build_planner_evaluator_provider_call_request(
    *,
    system_prompt: str,
    user_prompt: str,
) -> bytes:
    """Build the canonical evaluator request at Rook's provider boundary."""

    request = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "tools": [planner_evaluator_tool_definition()],
        "tool_choice": {
            "type": "function",
            "function": {"name": "submit_planner_evaluation"},
        },
        "max_completion_tokens": PLANNER_EVALUATOR_MAX_COMPLETION_TOKENS,
        "provider_timeout_s": PLANNER_EVALUATOR_PROVIDER_TIMEOUT_S,
    }
    return json.dumps(
        request,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def materialize_planner_evaluator_provider_call_request(
    raw_bytes: bytes,
) -> dict[str, object]:
    """Validate canonical bytes and return one fresh mutable provider value."""

    value = parse_archive_json(raw_bytes)
    if type(value) is not dict:
        raise ValueError("provider-call request must be an object")
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if canonical != raw_bytes:
        raise ValueError("provider-call request bytes are not canonical")
    return value


def _malformed_planner_evaluation(
    response: ProviderTurn | None = None,
) -> PlannerEvaluationResult:
    return PlannerEvaluationResult(
        termination="malformed",
        recommendation=None,
        evidence=(),
        raw_response=None if response is None else response.raw_response,
        usage=None if response is None else response.usage,
    )


def _planner_evaluation_from_message(
    response: ProviderTurn,
) -> PlannerEvaluationResult:
    message = response.assistant_message
    calls = message.get("tool_calls", []) if isinstance(message, MappingABC) else []
    if type(calls) is not list or len(calls) != 1 or type(calls[0]) is not dict:
        return _malformed_planner_evaluation(response)
    function = calls[0].get("function")
    if (
        type(function) is not dict
        or function.get("name") != "submit_planner_evaluation"
        or type(function.get("arguments")) is not str
    ):
        return _malformed_planner_evaluation(response)
    try:
        envelope = parse_strict_json(function["arguments"].encode("utf-8"))
    except (StrictJsonError, UnicodeError):
        return _malformed_planner_evaluation(response)
    if (
        type(envelope) is not dict
        or set(envelope) != {"evaluation_json"}
        or type(envelope.get("evaluation_json")) is not str
    ):
        return _malformed_planner_evaluation(response)
    try:
        report = parse_strict_json(envelope["evaluation_json"].encode("utf-8"))
    except (StrictJsonError, UnicodeError):
        return _malformed_planner_evaluation(response)
    if type(report) is not dict or any(
        _PLANNER_EVALUATION_REPORT_VALIDATOR.iter_errors(report)
    ):
        return _malformed_planner_evaluation(response)
    recommendation = report["recommendation"]
    evidence = report["evidence"]
    assert recommendation in PLANNER_EVALUATION_RECOMMENDATIONS
    assert isinstance(evidence, list)
    return PlannerEvaluationResult(
        termination="valid_recommendation",
        recommendation=recommendation,
        evidence=tuple(evidence),
        raw_response=response.raw_response,
        usage=response.usage,
    )


def derive_planner_evaluation_result(
    *,
    outcome: Literal["returned", "raised", "timeout"],
    response: ProviderTurn | None = None,
    exception_type: str | None = None,
    failure_type: str | None = None,
    quiescent: bool = True,
) -> PlannerEvaluationResult:
    """Purely derive evaluator meaning from terminal provider evidence."""

    if outcome == "timeout":
        return PlannerEvaluationResult(
            "timeout", None, (), None, None, quiescent=quiescent
        )
    if outcome == "raised":
        if exception_type == "TimeoutError" or (
            exception_type == "ProviderCallFailure"
            and isinstance(failure_type, str)
            and "timeout" in failure_type.casefold()
        ):
            return PlannerEvaluationResult("timeout", None, (), None, None)
        return PlannerEvaluationResult("provider_failure", None, (), None, None)
    if type(response) is not ProviderTurn:
        return PlannerEvaluationResult("provider_failure", None, (), None, None)
    return _planner_evaluation_from_message(response)


def run_planner_evaluation(
    *,
    provider: Callable[[dict[str, object]], ProviderTurn],
    provider_call_request_bytes: bytes,
    materialized_request: dict[str, object] | None = None,
) -> PlannerEvaluationResult:
    """Run one independent Planner evaluator call with no feedback path."""

    if materialized_request is None:
        request = materialize_planner_evaluator_provider_call_request(
            provider_call_request_bytes
        )
    else:
        canonical = json.dumps(
            materialized_request,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if canonical != provider_call_request_bytes:
            raise ValueError("materialized provider request does not match canonical bytes")
        request = materialized_request
    outcome = _bounded_provider_call(
        provider,
        request,
        timeout_s=PLANNER_EVALUATOR_PROVIDER_TIMEOUT_S,
    )
    if outcome.timed_out:
        return derive_planner_evaluation_result(
            outcome="timeout",
            quiescent=outcome.quiescent,
        )
    if outcome.exception is not None:
        return derive_planner_evaluation_result(
            outcome="raised",
            exception_type=type(outcome.exception).__name__,
            failure_type=getattr(outcome.exception, "failure_type", None),
        )
    return derive_planner_evaluation_result(
        outcome="returned",
        response=(
            outcome.response if type(outcome.response) is ProviderTurn else None
        ),
    )


def build_planner_mechanical_feedback_message(
    gate_result: MechanicalGateResult,
    tool_call_id: str | None,
) -> dict[str, object]:
    content = json.dumps(
        {
            "accepted": False,
            "feedback": [
                {
                    "code": diagnostic.code,
                    "path": diagnostic.path,
                    "message": diagnostic.message,
                }
                for diagnostic in gate_result.diagnostics
            ],
            "instruction": "Submit exactly one conforming planner recipe tool call.",
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if tool_call_id is not None:
        return {"role": "tool", "tool_call_id": tool_call_id, "content": content}
    return {"role": "user", "content": content}


def _planner_protocol_rejection(
    code: str,
    path: str,
    message: str,
) -> tuple[None, None, MechanicalGateResult, None]:
    return None, None, _reject(code, path, message), None


def derive_planner_submission_from_message(
    message: Mapping[str, object],
) -> tuple[bytes | None, bytes | None, MechanicalGateResult | None, str | None]:
    tool_calls = message.get("tool_calls", [])
    if type(tool_calls) is not list:
        return _planner_protocol_rejection(
            "provider_tool_calls_malformed",
            "/tool_calls",
            "provider tool calls must be a list",
        )
    if not tool_calls:
        return _planner_protocol_rejection(
            "planner_tool_missing",
            "/tool_calls",
            "exactly one submit_planner_recipe tool call is required",
        )
    if len(tool_calls) != 1:
        return _planner_protocol_rejection(
            "multiple_tool_calls",
            "/tool_calls",
            "at most one tool call is permitted per Planner turn",
        )
    tool_call = tool_calls[0]
    if type(tool_call) is not dict:
        return _planner_protocol_rejection(
            "provider_tool_call_malformed",
            "/tool_calls/0",
            "provider tool call must be an object",
        )
    tool_call_id = tool_call.get("id")
    if type(tool_call_id) is not str or not tool_call_id:
        tool_call_id = None
    function = tool_call.get("function")
    if type(function) is not dict:
        return None, None, _reject(
            "provider_tool_call_malformed",
            "/tool_calls/0/function",
            "provider tool function must be an object",
        ), tool_call_id
    if function.get("name") != "submit_planner_recipe":
        return None, None, _reject(
            "unknown_tool",
            "/tool_calls/0/function/name",
            "only submit_planner_recipe is available",
        ), tool_call_id
    arguments = function.get("arguments")
    if type(arguments) is not str:
        return None, None, _reject(
            "tool_arguments_not_exact_string",
            "/tool_calls/0/function/arguments",
            "provider must expose the exact tool argument string",
        ), tool_call_id
    try:
        tool_arguments = arguments.encode("utf-8", errors="strict")
    except (StrictJsonError, UnicodeError):
        return None, None, _reject(
            "tool_arguments_not_utf8",
            "/tool_calls/0/function/arguments",
            "tool arguments must be representable as UTF-8",
        ), tool_call_id
    try:
        envelope = parse_strict_json(tool_arguments)
    except StrictJsonError:
        return tool_arguments, None, _reject(
            "tool_arguments_invalid_json",
            "/tool_calls/0/function/arguments",
            "tool arguments must be strict JSON",
        ), tool_call_id
    if (
        type(envelope) is not dict
        or set(envelope) != {"recipe_json"}
        or type(envelope.get("recipe_json")) is not str
        or not envelope["recipe_json"]
        or len(envelope["recipe_json"]) > MAX_RECIPE_BYTES
    ):
        return tool_arguments, None, _reject(
            "tool_arguments_shape_invalid",
            "/tool_calls/0/function/arguments",
            "tool arguments must be the closed recipe_json object",
        ), tool_call_id
    try:
        recipe_bytes = envelope["recipe_json"].encode("utf-8", errors="strict")
    except UnicodeError:
        return tool_arguments, None, _reject(
            "tool_arguments_not_utf8",
            "/tool_calls/0/function/arguments/recipe_json",
            "recipe_json must be representable as UTF-8",
        ), tool_call_id
    return tool_arguments, recipe_bytes, None, tool_call_id


def _planner_usage_values(usage: Mapping[str, object]) -> tuple[int, float, bool]:
    token_value = usage.get("total_tokens", 0)
    tokens = token_value if type(token_value) is int and token_value >= 0 else 0
    cost_value = usage.get("cost_usd")
    if type(cost_value) in (int, float) and float(cost_value) >= 0:
        return tokens, float(cost_value), True
    return tokens, 0.0, False


def run_planner_session(
    *,
    provider: Callable[[dict[str, object]], ProviderTurn],
    system_prompt: str,
    user_prompt: str,
    authority: object,
    recipe_schema: Mapping[str, object],
    normalization_profile: NormalizationProfile,
    exclusion_policy: Mapping[str, object],
    monotonic: Callable[[], float] = time.monotonic,
    call_plan_observer: Callable[[PlannerProviderCallPlan], None] | None = None,
    call_completion_observer: Callable[[bool], None] | None = None,
) -> PlannerSessionResult:
    """Run one bounded Planner session with deterministic mechanical feedback."""

    started = monotonic()
    messages: list[dict[str, object]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    turns: list[PlannerTurnRecord] = []
    total_tokens = 0
    total_cost = 0.0
    cost_complete = True

    def finish(
        termination: Literal[
            "mechanically_accepted",
            "mechanically_rejected",
            "provider_failure",
            "timeout",
        ],
        final_recipe_bytes: bytes | None = None,
    ) -> PlannerSessionResult:
        return PlannerSessionResult(
            termination=termination,
            turns=tuple(turns),
            final_recipe_bytes=final_recipe_bytes,
        )

    for turn_index in range(1, PLANNER_MAX_TURNS + 1):
        call_started = monotonic()
        if call_started - started >= PLANNER_OVERALL_DEADLINE_S:
            return finish("timeout")
        call_plan = build_planner_provider_call_plan(
            turn_index=turn_index,
            messages=messages,
            session_started_monotonic_s=started,
            call_started_monotonic_s=call_started,
        )
        if call_plan_observer is not None:
            call_plan_observer(call_plan)
        call_timeout_s = call_plan.provider_timeout_s
        request_bytes = call_plan.request_bytes
        request = materialize_planner_provider_call_request(request_bytes)
        turn_started = monotonic()
        try:
            outcome = _bounded_provider_call(
                provider,
                request,
                timeout_s=call_timeout_s,
            )
        except Exception:
            return finish("provider_failure")
        if call_completion_observer is not None:
            call_completion_observer(outcome.quiescent)
        if outcome.timed_out:
            return finish("timeout")
        if isinstance(outcome.exception, ProviderCallFailure):
            exc = outcome.exception
            termination = (
                "timeout"
                if "timeout" in exc.failure_type.casefold()
                else "provider_failure"
            )
            return finish(termination)
        if isinstance(outcome.exception, TimeoutError):
            return finish("timeout")
        if outcome.exception is not None:
            return finish("provider_failure")
        response = outcome.response
        elapsed_ms = max(0, int((monotonic() - turn_started) * 1000))
        if type(response) is not ProviderTurn:
            return finish("provider_failure")
        if type(response.raw_response) is not bytes or not isinstance(
            response.assistant_message, MappingABC
        ):
            return finish("provider_failure")

        usage = dict(response.usage) if isinstance(response.usage, MappingABC) else {}
        turn_tokens, turn_cost, turn_cost_complete = _planner_usage_values(usage)
        total_tokens += turn_tokens
        total_cost += turn_cost
        cost_complete = cost_complete and turn_cost_complete
        (
            tool_arguments,
            recipe_bytes,
            protocol_rejection,
            tool_call_id,
        ) = derive_planner_submission_from_message(response.assistant_message)

        if monotonic() - started >= PLANNER_OVERALL_DEADLINE_S:
            turns.append(
                PlannerTurnRecord(
                    turn_index=turn_index,
                    raw_response=response.raw_response,
                    tool_arguments=tool_arguments,
                    gate_result=protocol_rejection,
                    usage=usage,
                    elapsed_ms=elapsed_ms,
                )
            )
            return finish("timeout")

        gate_result = protocol_rejection
        if recipe_bytes is not None:
            gate_result = evaluate_mechanical_gate(
                recipe_bytes=recipe_bytes,
                authority=authority,
                recipe_schema=recipe_schema,
                normalization_profile=normalization_profile,
                exclusion_policy=exclusion_policy,
            )
        turns.append(
            PlannerTurnRecord(
                turn_index=turn_index,
                raw_response=response.raw_response,
                tool_arguments=tool_arguments,
                gate_result=gate_result,
                usage=usage,
                elapsed_ms=elapsed_ms,
            )
        )
        assert gate_result is not None
        if gate_result.status == "mechanically_accepted":
            assert gate_result.final_recipe_bytes is not None
            return finish("mechanically_accepted", gate_result.final_recipe_bytes)

        messages.append(dict(response.assistant_message))
        messages.append(
            build_planner_mechanical_feedback_message(gate_result, tool_call_id)
        )
        if total_tokens >= PLANNER_TOKEN_STOP_THRESHOLD:
            return finish("mechanically_rejected")
        if cost_complete and total_cost >= PLANNER_COST_STOP_THRESHOLD_USD:
            return finish("mechanically_rejected")

    return finish("mechanically_rejected")


__all__ = (
    "MechanicalDiagnostic",
    "MechanicalGateResult",
    "NormalizationProfile",
    "NormalizationRow",
    "PLANNER_COST_STOP_THRESHOLD_USD",
    "PLANNER_EVALUATOR_MAX_COMPLETION_TOKENS",
    "PLANNER_EVALUATOR_PROVIDER_TIMEOUT_S",
    "PLANNER_EVALUATOR_SYSTEM_PROMPT",
    "PLANNER_EVALUATOR_TOOL_PARAMETERS",
    "PLANNER_MAX_COMPLETION_TOKENS",
    "PLANNER_MAX_TURNS",
    "PLANNER_OVERALL_DEADLINE_S",
    "PLANNER_PROVIDER_TIMEOUT_S",
    "PLANNER_TOKEN_STOP_THRESHOLD",
    "PLANNER_TOOL_PARAMETERS",
    "PlannerSessionResult",
    "PlannerEvaluationResult",
    "PlannerTurnRecord",
    "ProviderCallFailure",
    "ProviderTurn",
    "PlannerProviderCallPlan",
    "StrictJsonError",
    "build_planner_evaluator_provider_call_request",
    "build_planner_mechanical_feedback_message",
    "build_planner_provider_call_request",
    "build_planner_provider_call_plan",
    "derive_planner_submission_from_message",
    "derive_planner_evaluation_result",
    "evaluate_mechanical_gate",
    "fingerprint",
    "fingerprint_without",
    "load_normalization_profile",
    "materialize_planner_evaluator_provider_call_request",
    "materialize_planner_provider_call_request",
    "normalization_profile_from_value",
    "normalize_recipe",
    "parse_archive_json",
    "parse_strict_json",
    "planner_tool_definition",
    "planner_evaluator_tool_definition",
    "resolve_json_pointer",
    "run_planner_session",
    "run_planner_evaluation",
    "sha256_prefixed",
    "validate_exclusion_policy",
)
