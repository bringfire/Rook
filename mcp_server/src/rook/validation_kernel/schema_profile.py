"""Closed Draft 2020-12 profiles over immutable kernel-owned JSON values."""

from __future__ import annotations

import hashlib
import importlib.metadata
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from itertools import islice
from typing import overload
from urllib.parse import quote

from jsonschema import Draft202012Validator, ValidationError, validators
from jsonschema.exceptions import SchemaError
from referencing import Registry

from .budget import BudgetLedger, SchemaShapeReservation
from .canonical_json import canonical_fingerprint
from .owned_json import (
    JsonArray,
    JsonBoolean,
    JsonNull,
    JsonNumber,
    JsonObject,
    JsonString,
    JsonValue,
    count_json_nodes,
    lookup_json_pointer,
    own_trusted_json,
)


PAYLOAD_SCHEMA_PROFILE_ID = "rook.json_schema_profile:lm9a_payload_v1"
CORE_SCHEMA_PROFILE_ID = "rook.json_schema_profile:lm9a_core_v1"
MAX_SCHEMA_ISSUES = 1_024

_DRAFT_2020_12_METASCHEMA_ID = "https://json-schema.org/draft/2020-12/schema"
_EVALUATOR_ID = "rook.json_schema_evaluator:jsonschema_draft202012_owned_v1"
_TYPE_CHECKER_ID = "rook.json_schema_type_checker:owned_values_v1"
_FORMAT_POLICY_ID = "rook.json_schema_format_policy:none_v1"
_REFERENCE_POLICY_ID = "rook.json_schema_reference_policy:local_rfc6901_no_retrieval_v1"
_FINGERPRINT_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_MACHINE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")

_PAYLOAD_ALLOWED_KEYWORDS = (
    "$schema",
    "$defs",
    "$ref",
    "$comment",
    "title",
    "description",
    "default",
    "examples",
    "deprecated",
    "readOnly",
    "writeOnly",
    "type",
    "enum",
    "const",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "prefixItems",
    "minItems",
    "maxItems",
    "minProperties",
    "maxProperties",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
)
_CORE_ONLY_KEYWORDS = (
    "allOf",
    "anyOf",
    "oneOf",
    "not",
    "if",
    "then",
    "else",
    "dependentRequired",
)
_COMMON_FORBIDDEN_KEYWORDS = (
    "$id",
    "$anchor",
    "$dynamicAnchor",
    "$dynamicRef",
    "$recursiveRef",
    "pattern",
    "patternProperties",
    "propertyNames",
    "format",
    "uniqueItems",
    "contains",
    "dependentSchemas",
    "unevaluatedItems",
    "unevaluatedProperties",
    "contentEncoding",
    "contentMediaType",
    "contentSchema",
)
_SCHEMA_MAP_KEYWORDS = frozenset({"$defs", "properties"})
_SCHEMA_SINGLE_KEYWORDS = frozenset(
    {"additionalProperties", "items", "not", "if", "then", "else"}
)
_SCHEMA_ARRAY_KEYWORDS = frozenset(
    {"prefixItems", "allOf", "anyOf", "oneOf"}
)
_COMBINATOR_KEYWORDS = frozenset(
    {"allOf", "anyOf", "oneOf", "not", "if", "then", "else"}
)
_ALTERNATIVE_KEYWORDS = frozenset({"allOf", "anyOf", "oneOf"})
_OWNED_VALUE_TYPES = (
    JsonNull,
    JsonBoolean,
    JsonString,
    JsonNumber,
    JsonArray,
    JsonObject,
)

_ADMISSION_MESSAGES = {
    "schema_id_invalid": "Schema identity is invalid.",
    "schema_profile_not_sealed": "Schema profile is not sealed.",
    "schema_root_invalid": "Schema root is invalid.",
    "schema_keyword_forbidden": "Schema contains a forbidden keyword.",
    "schema_keyword_unknown": "Schema contains an unknown keyword.",
    "schema_invalid": "Schema is invalid under the closed metaschema profile.",
    "schema_library_failed": "Schema library admission failed.",
    "schema_node_limit_exceeded": "Schema node limit exceeded.",
    "local_reference_invalid": "Local schema reference is invalid.",
    "local_reference_target_invalid": "Local schema reference target is invalid.",
    "local_reference_limit_exceeded": "Local schema reference limit exceeded.",
    "local_reference_cycle": "Local schema reference cycle detected.",
    "local_reference_depth_exceeded": "Local schema reference depth exceeded.",
    "combinator_alternative_limit_exceeded": "Schema combinator alternative limit exceeded.",
    "combinator_depth_limit_exceeded": "Schema combinator depth limit exceeded.",
}


class SchemaAdmissionError(ValueError):
    """A closed static or metaschema admission failure."""

    def __init__(self, code: str) -> None:
        if type(code) is not str or code not in _ADMISSION_MESSAGES:
            raise ValueError("invalid schema admission error code")
        self.code = code
        super().__init__(_ADMISSION_MESSAGES[code])


class SchemaEvaluationInputError(ValueError):
    """A trusted caller supplied an invalid evaluation capability."""


@dataclass(frozen=True, slots=True)
class SchemaProfile:
    """One immutable, release-owned closed schema profile identity."""

    profile_id: str
    allowed_keywords: tuple[str, ...]
    forbidden_keywords: tuple[str, ...]
    schema_node_limit: int
    local_reference_limit: int
    reference_depth_limit: int
    per_evaluation_shape_limit: int
    combinator_alternative_limit: int
    combinator_depth_limit: int
    runtime_dependencies: tuple[tuple[str, str], ...]
    metaschema_id: str
    metaschema_fingerprint: str
    evaluator_id: str
    type_checker_id: str
    format_policy_id: str
    reference_policy_id: str
    identity: JsonObject
    profile_fingerprint: str


@dataclass(frozen=True, slots=True, init=False)
class AdmittedSchema:
    """An immutable schema admitted by one exact release-owned profile."""

    schema_id: str
    schema_fingerprint: str
    profile_id: str
    schema_nodes: int
    local_reference_count: int
    maximum_reference_depth: int
    value: JsonObject

    def __init__(self) -> None:
        raise TypeError("AdmittedSchema values are created only by admit_schema")

    @classmethod
    def _create(
        cls,
        *,
        schema_id: str,
        schema_fingerprint: str,
        profile_id: str,
        schema_nodes: int,
        local_reference_count: int,
        maximum_reference_depth: int,
        value: JsonObject,
    ) -> "AdmittedSchema":
        admitted = object.__new__(cls)
        object.__setattr__(admitted, "schema_id", schema_id)
        object.__setattr__(admitted, "schema_fingerprint", schema_fingerprint)
        object.__setattr__(admitted, "profile_id", profile_id)
        object.__setattr__(admitted, "schema_nodes", schema_nodes)
        object.__setattr__(
            admitted, "local_reference_count", local_reference_count
        )
        object.__setattr__(
            admitted, "maximum_reference_depth", maximum_reference_depth
        )
        object.__setattr__(admitted, "value", value)
        return admitted


@dataclass(frozen=True, slots=True)
class InstanceBinding:
    """Identity of the immutable artifact root selected for evaluation."""

    artifact_id: str
    artifact_fingerprint: str
    instance_pointer: str

    def __post_init__(self) -> None:
        if type(self.artifact_id) is not str or not _MACHINE_ID_RE.fullmatch(
            self.artifact_id
        ):
            raise SchemaEvaluationInputError("invalid instance artifact identity")
        if (
            type(self.artifact_fingerprint) is not str
            or not _FINGERPRINT_RE.fullmatch(self.artifact_fingerprint)
        ):
            raise SchemaEvaluationInputError("invalid instance artifact fingerprint")
        if not _is_rfc6901_pointer(self.instance_pointer):
            raise SchemaEvaluationInputError("invalid selected instance pointer")


@dataclass(frozen=True, slots=True)
class SchemaIssue:
    """One bounded deterministic validation or evaluator issue."""

    code: str
    instance_path: str
    schema_path: str
    detail_sha256: str | None

    def __post_init__(self) -> None:
        if type(self.code) is not str or not self.code or len(self.code) > 64:
            raise SchemaEvaluationInputError("invalid schema issue code")
        if type(self.instance_path) is not str or type(self.schema_path) is not str:
            raise SchemaEvaluationInputError("invalid schema issue path")
        if self.detail_sha256 is not None and (
            type(self.detail_sha256) is not str
            or not _FINGERPRINT_RE.fullmatch(self.detail_sha256)
        ):
            raise SchemaEvaluationInputError("invalid schema issue detail fingerprint")


@dataclass(frozen=True, slots=True)
class SchemaEvaluationReceipt:
    """The complete immutable result of one charged evaluation attempt."""

    reservation: SchemaShapeReservation
    evaluator_invoked: bool
    evaluation_passed: bool | None
    bounded_errors: tuple[SchemaIssue, ...]
    failure_code: str | None


class _OwnedMappingView(Mapping[str, object]):
    """Lazy read-only mapping over one owned object."""

    __slots__ = ("_owned", "_translate_refs")

    def __init__(self, owned: JsonObject, *, translate_refs: bool) -> None:
        self._owned = owned
        self._translate_refs = translate_refs

    def __getitem__(self, key: str) -> object:
        child = self._owned[key]
        if self._translate_refs and key == "$ref" and type(child) is JsonString:
            return "#" + quote(child.value, safe="/~")
        return _adapt_owned(child, translate_refs=self._translate_refs)

    def __iter__(self) -> Iterator[str]:
        return iter(self._owned)

    def __len__(self) -> int:
        return len(self._owned)


class _OwnedSequenceView(Sequence[object]):
    """Lazy read-only sequence over one owned array."""

    __slots__ = ("_owned", "_translate_refs")

    def __init__(self, owned: JsonArray, *, translate_refs: bool) -> None:
        self._owned = owned
        self._translate_refs = translate_refs

    @overload
    def __getitem__(self, index: int) -> object: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[object, ...]: ...

    def __getitem__(self, index: int | slice) -> object | tuple[object, ...]:
        if isinstance(index, slice):
            return tuple(
                _adapt_owned(child, translate_refs=self._translate_refs)
                for child in self._owned[index]
            )
        return _adapt_owned(
            self._owned[index], translate_refs=self._translate_refs
        )

    def __len__(self) -> int:
        return len(self._owned)


def _adapt_owned(value: JsonValue, *, translate_refs: bool) -> object:
    value_type = type(value)
    if value_type is JsonNull:
        return None
    if value_type is JsonBoolean:
        return value.value
    if value_type is JsonString:
        return value.value
    if value_type is JsonNumber:
        return value.value
    if value_type is JsonArray:
        return _OwnedSequenceView(value, translate_refs=translate_refs)
    if value_type is JsonObject:
        return _OwnedMappingView(value, translate_refs=translate_refs)
    raise SchemaEvaluationInputError("evaluation requires an exact owned JSON value")


def _is_owned_array(_: object, instance: object) -> bool:
    return type(instance) is _OwnedSequenceView


def _is_owned_boolean(_: object, instance: object) -> bool:
    return type(instance) is bool


def _is_owned_integer(_: object, instance: object) -> bool:
    return type(instance) is float and instance.is_integer()


def _is_owned_null(_: object, instance: object) -> bool:
    return instance is None


def _is_owned_number(_: object, instance: object) -> bool:
    return type(instance) is float


def _is_owned_object(_: object, instance: object) -> bool:
    return type(instance) is _OwnedMappingView


def _is_owned_string(_: object, instance: object) -> bool:
    return type(instance) is str


_OWNED_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine_many(
    {
        "array": _is_owned_array,
        "boolean": _is_owned_boolean,
        "integer": _is_owned_integer,
        "null": _is_owned_null,
        "number": _is_owned_number,
        "object": _is_owned_object,
        "string": _is_owned_string,
    }
)
_OwnedDraft202012Validator = validators.extend(
    Draft202012Validator,
    type_checker=_OWNED_TYPE_CHECKER,
    version="rook-owned-draft202012-v1",
)


def _installed_dependency_versions() -> tuple[tuple[str, str], ...]:
    expected = (
        ("jsonschema", "4.26.0"),
        ("referencing", "0.37.0"),
        ("jsonschema-specifications", "2025.9.1"),
    )
    actual = tuple(
        (distribution, importlib.metadata.version(distribution))
        for distribution, _ in expected
    )
    if actual != expected:
        raise RuntimeError("closed schema evaluator dependency versions do not match")
    return actual


_RUNTIME_DEPENDENCIES = _installed_dependency_versions()
_METASCHEMA_VALUE = own_trusted_json(Draft202012Validator.META_SCHEMA)
_METASCHEMA_FINGERPRINT = canonical_fingerprint(_METASCHEMA_VALUE)


def _make_profile(
    *,
    profile_id: str,
    allowed_keywords: tuple[str, ...],
    forbidden_keywords: tuple[str, ...],
    schema_node_limit: int,
    local_reference_limit: int,
    reference_depth_limit: int,
    per_evaluation_shape_limit: int,
    combinator_alternative_limit: int,
    combinator_depth_limit: int,
) -> SchemaProfile:
    identity_value = own_trusted_json(
        {
            "profile_id": profile_id,
            "draft": _DRAFT_2020_12_METASCHEMA_ID,
            "allowed_keywords": allowed_keywords,
            "forbidden_keywords": forbidden_keywords,
            "limits": {
                "schema_nodes": schema_node_limit,
                "local_references": local_reference_limit,
                "local_reference_depth": reference_depth_limit,
                "per_evaluation_shape_units": per_evaluation_shape_limit,
                "combinator_alternatives": combinator_alternative_limit,
                "combinator_depth": combinator_depth_limit,
                "bounded_issues": MAX_SCHEMA_ISSUES,
            },
            "evaluator": {
                "evaluator_id": _EVALUATOR_ID,
                "type_checker_id": _TYPE_CHECKER_ID,
                "format_policy_id": _FORMAT_POLICY_ID,
                "reference_policy_id": _REFERENCE_POLICY_ID,
                "runtime_dependencies": [
                    {"distribution": name, "version": version}
                    for name, version in _RUNTIME_DEPENDENCIES
                ],
                "metaschema_id": _DRAFT_2020_12_METASCHEMA_ID,
                "metaschema_fingerprint": _METASCHEMA_FINGERPRINT,
            },
        }
    )
    if type(identity_value) is not JsonObject:
        raise AssertionError("schema profile identity must be an owned object")
    return SchemaProfile(
        profile_id=profile_id,
        allowed_keywords=allowed_keywords,
        forbidden_keywords=forbidden_keywords,
        schema_node_limit=schema_node_limit,
        local_reference_limit=local_reference_limit,
        reference_depth_limit=reference_depth_limit,
        per_evaluation_shape_limit=per_evaluation_shape_limit,
        combinator_alternative_limit=combinator_alternative_limit,
        combinator_depth_limit=combinator_depth_limit,
        runtime_dependencies=_RUNTIME_DEPENDENCIES,
        metaschema_id=_DRAFT_2020_12_METASCHEMA_ID,
        metaschema_fingerprint=_METASCHEMA_FINGERPRINT,
        evaluator_id=_EVALUATOR_ID,
        type_checker_id=_TYPE_CHECKER_ID,
        format_policy_id=_FORMAT_POLICY_ID,
        reference_policy_id=_REFERENCE_POLICY_ID,
        identity=identity_value,
        profile_fingerprint=canonical_fingerprint(identity_value),
    )


PAYLOAD_PROFILE = _make_profile(
    profile_id=PAYLOAD_SCHEMA_PROFILE_ID,
    allowed_keywords=_PAYLOAD_ALLOWED_KEYWORDS,
    forbidden_keywords=_COMMON_FORBIDDEN_KEYWORDS + _CORE_ONLY_KEYWORDS,
    schema_node_limit=4_096,
    local_reference_limit=256,
    reference_depth_limit=16,
    per_evaluation_shape_limit=2_000_000,
    combinator_alternative_limit=0,
    combinator_depth_limit=0,
)
CORE_PROFILE = _make_profile(
    profile_id=CORE_SCHEMA_PROFILE_ID,
    allowed_keywords=_PAYLOAD_ALLOWED_KEYWORDS + _CORE_ONLY_KEYWORDS,
    forbidden_keywords=_COMMON_FORBIDDEN_KEYWORDS,
    schema_node_limit=32_768,
    local_reference_limit=1_024,
    reference_depth_limit=32,
    per_evaluation_shape_limit=8_000_000,
    combinator_alternative_limit=16,
    combinator_depth_limit=8,
)


def _is_rfc6901_pointer(pointer: object) -> bool:
    if type(pointer) is not str:
        return False
    if pointer == "":
        return True
    if not pointer.startswith("/"):
        return False
    for token in pointer[1:].split("/"):
        index = 0
        while index < len(token):
            if token[index] != "~":
                index += 1
                continue
            if index + 1 == len(token) or token[index + 1] not in ("0", "1"):
                return False
            index += 2
    return True


def _child_pointer(parent: str, token: str) -> str:
    escaped = token.replace("~", "~0").replace("/", "~1")
    return f"{parent}/{escaped}"


def _push_schema_children(
    stack: list[tuple[JsonValue, str, int]],
    *,
    keyword: str,
    keyword_value: JsonValue,
    keyword_path: str,
    combinator_depth: int,
) -> None:
    child_depth = combinator_depth + (keyword in _COMBINATOR_KEYWORDS)
    if keyword in _SCHEMA_MAP_KEYWORDS and type(keyword_value) is JsonObject:
        for name, child in reversed(keyword_value.members):
            if type(child) in (JsonObject, JsonBoolean):
                stack.append(
                    (child, _child_pointer(keyword_path, name.value), child_depth)
                )
        return
    if keyword in _SCHEMA_SINGLE_KEYWORDS and type(keyword_value) in (
        JsonObject,
        JsonBoolean,
    ):
        stack.append((keyword_value, keyword_path, child_depth))
        return
    if keyword in _SCHEMA_ARRAY_KEYWORDS and type(keyword_value) is JsonArray:
        for index in reversed(range(len(keyword_value))):
            child = keyword_value[index]
            if type(child) in (JsonObject, JsonBoolean):
                stack.append((child, f"{keyword_path}/{index}", child_depth))


def _maximum_reference_depth(graph: dict[int, int]) -> int:
    depths: dict[int, int] = {}
    maximum = 0
    for start in graph:
        if start in depths:
            continue
        trail: list[int] = []
        positions: dict[int, int] = {}
        current = start
        while current in graph and current not in depths:
            if current in positions:
                raise SchemaAdmissionError("local_reference_cycle")
            positions[current] = len(trail)
            trail.append(current)
            current = graph[current]
        depth = depths.get(current, 0)
        for node in reversed(trail):
            depth += 1
            depths[node] = depth
            maximum = max(maximum, depth)
    return maximum


def _static_admission(
    value: JsonObject, profile: SchemaProfile
) -> tuple[int, int, int]:
    schema_nodes = count_json_nodes(value)
    if schema_nodes > profile.schema_node_limit:
        raise SchemaAdmissionError("schema_node_limit_exceeded")

    allowed = frozenset(profile.allowed_keywords)
    forbidden = frozenset(profile.forbidden_keywords)
    schema_node_ids: set[int] = set()
    references: list[tuple[int, str]] = []
    stack: list[tuple[JsonValue, str, int]] = [(value, "", 0)]

    while stack:
        current, current_path, combinator_depth = stack.pop()
        schema_node_ids.add(id(current))
        if combinator_depth > profile.combinator_depth_limit:
            raise SchemaAdmissionError("combinator_depth_limit_exceeded")
        if type(current) is JsonBoolean:
            continue
        if type(current) is not JsonObject:
            raise SchemaAdmissionError("schema_invalid")

        for key, keyword_value in current.members:
            keyword = key.value
            if keyword not in allowed:
                code = (
                    "schema_keyword_forbidden"
                    if keyword in forbidden
                    else "schema_keyword_unknown"
                )
                raise SchemaAdmissionError(code)
            keyword_path = _child_pointer(current_path, keyword)
            if keyword == "$ref":
                if type(keyword_value) is not JsonString or not _is_rfc6901_pointer(
                    keyword_value.value
                ):
                    raise SchemaAdmissionError("local_reference_invalid")
                references.append((id(current), keyword_value.value))
                if len(references) > profile.local_reference_limit:
                    raise SchemaAdmissionError("local_reference_limit_exceeded")
            if (
                keyword in _ALTERNATIVE_KEYWORDS
                and type(keyword_value) is JsonArray
                and len(keyword_value) > profile.combinator_alternative_limit
            ):
                raise SchemaAdmissionError(
                    "combinator_alternative_limit_exceeded"
                )
            _push_schema_children(
                stack,
                keyword=keyword,
                keyword_value=keyword_value,
                keyword_path=keyword_path,
                combinator_depth=combinator_depth,
            )

    reference_graph: dict[int, int] = {}
    for source, pointer in references:
        try:
            target = lookup_json_pointer(value, pointer)
        except ValueError:
            raise SchemaAdmissionError("local_reference_invalid") from None
        except KeyError:
            raise SchemaAdmissionError("local_reference_target_invalid") from None
        if id(target) not in schema_node_ids:
            raise SchemaAdmissionError("local_reference_target_invalid")
        reference_graph[source] = id(target)

    maximum_reference_depth = _maximum_reference_depth(reference_graph)
    if maximum_reference_depth > profile.reference_depth_limit:
        raise SchemaAdmissionError("local_reference_depth_exceeded")
    return schema_nodes, len(references), maximum_reference_depth


def _check_schema_with_library(value: JsonObject) -> None:
    schema_view = _OwnedMappingView(value, translate_refs=True)
    _OwnedDraft202012Validator.check_schema(schema_view)


def admit_schema(
    schema_id: str, value: JsonObject, profile: SchemaProfile
) -> AdmittedSchema:
    """Admit one owned schema through static checks before library construction."""

    if type(schema_id) is not str or not _MACHINE_ID_RE.fullmatch(schema_id):
        raise SchemaAdmissionError("schema_id_invalid")
    if type(value) is not JsonObject:
        raise SchemaAdmissionError("schema_root_invalid")
    if profile is not PAYLOAD_PROFILE and profile is not CORE_PROFILE:
        raise SchemaAdmissionError("schema_profile_not_sealed")

    schema_nodes, reference_count, reference_depth = _static_admission(
        value, profile
    )
    try:
        _check_schema_with_library(value)
    except SchemaError:
        raise SchemaAdmissionError("schema_invalid") from None
    except Exception:
        raise SchemaAdmissionError("schema_library_failed") from None

    return AdmittedSchema._create(
        schema_id=schema_id,
        schema_fingerprint=canonical_fingerprint(value),
        profile_id=profile.profile_id,
        schema_nodes=schema_nodes,
        local_reference_count=reference_count,
        maximum_reference_depth=reference_depth,
        value=value,
    )


def _profile_for_admitted(schema: AdmittedSchema) -> SchemaProfile:
    if schema.profile_id == PAYLOAD_SCHEMA_PROFILE_ID:
        return PAYLOAD_PROFILE
    if schema.profile_id == CORE_SCHEMA_PROFILE_ID:
        return CORE_PROFILE
    raise SchemaEvaluationInputError("admitted schema has an unknown profile")


def _validator_for(schema: AdmittedSchema) -> object:
    schema_view = _OwnedMappingView(schema.value, translate_refs=True)
    return _OwnedDraft202012Validator(
        schema_view,
        registry=Registry(),
        format_checker=None,
    )


def _path_pointer(path: Sequence[object]) -> str:
    pointer = ""
    for component in path:
        token = str(component)
        pointer = _child_pointer(pointer, token)
    return pointer


def _issue_from_validation_error(error: ValidationError) -> SchemaIssue:
    validator = error.validator
    code = validator if type(validator) is str and validator else "schema_validation"
    if len(code) > 64:
        code = "schema_validation"
    return SchemaIssue(
        code=code,
        instance_path=_path_pointer(tuple(error.absolute_path)),
        schema_path=_path_pointer(tuple(error.absolute_schema_path)),
        detail_sha256=None,
    )


def _exception_detail_fingerprint(exception: BaseException) -> str:
    exception_type = f"{type(exception).__module__}.{type(exception).__qualname__}"
    try:
        detail = str(exception)
    except Exception:
        detail = "<unprintable>"
    digest = hashlib.sha256()
    digest.update(exception_type.encode("utf-8"))
    digest.update(b"\0")
    digest.update(detail.encode("utf-8", errors="backslashreplace"))
    return f"sha256:{digest.hexdigest()}"


def evaluate_schema(
    schema: AdmittedSchema,
    instance: JsonValue,
    *,
    instance_binding: InstanceBinding,
    ledger: BudgetLedger,
) -> SchemaEvaluationReceipt:
    """Reserve exact shape units, then evaluate once with no retrieval or formats."""

    if type(schema) is not AdmittedSchema:
        raise SchemaEvaluationInputError("evaluation requires an admitted schema")
    if type(instance) not in _OWNED_VALUE_TYPES:
        raise SchemaEvaluationInputError("evaluation requires an owned instance")
    if type(instance_binding) is not InstanceBinding:
        raise SchemaEvaluationInputError("evaluation requires an instance binding")
    if type(ledger) is not BudgetLedger:
        raise SchemaEvaluationInputError("evaluation requires the invocation ledger")
    profile = _profile_for_admitted(schema)
    if (
        schema.schema_nodes != count_json_nodes(schema.value)
        or schema.schema_fingerprint != canonical_fingerprint(schema.value)
    ):
        raise SchemaEvaluationInputError("admitted schema identity is inconsistent")

    reservation = ledger.reserve_schema_shape(
        schema_nodes=schema.schema_nodes,
        instance_nodes=count_json_nodes(instance),
        per_evaluation_limit=profile.per_evaluation_shape_limit,
    )
    if not reservation.accepted:
        return SchemaEvaluationReceipt(
            reservation=reservation,
            evaluator_invoked=False,
            evaluation_passed=None,
            bounded_errors=(),
            failure_code=reservation.rejection_reason,
        )

    try:
        validator = _validator_for(schema)
        instance_view = _adapt_owned(instance, translate_refs=False)
        errors = tuple(
            sorted(
                (
                    _issue_from_validation_error(error)
                    for error in islice(
                        validator.iter_errors(instance_view), MAX_SCHEMA_ISSUES
                    )
                ),
                key=lambda issue: (
                    issue.instance_path,
                    issue.schema_path,
                    issue.code,
                ),
            )
        )
    except Exception as exception:
        return SchemaEvaluationReceipt(
            reservation=reservation,
            evaluator_invoked=True,
            evaluation_passed=None,
            bounded_errors=(
                SchemaIssue(
                    code="schema_evaluator_exception",
                    instance_path=instance_binding.instance_pointer,
                    schema_path="",
                    detail_sha256=_exception_detail_fingerprint(exception),
                ),
            ),
            failure_code="schema_evaluator_failed",
        )

    passed = not errors
    return SchemaEvaluationReceipt(
        reservation=reservation,
        evaluator_invoked=True,
        evaluation_passed=passed,
        bounded_errors=errors,
        failure_code=None if passed else "instance_schema_failed",
    )


__all__ = (
    "AdmittedSchema",
    "CORE_PROFILE",
    "CORE_SCHEMA_PROFILE_ID",
    "InstanceBinding",
    "MAX_SCHEMA_ISSUES",
    "PAYLOAD_PROFILE",
    "PAYLOAD_SCHEMA_PROFILE_ID",
    "SchemaAdmissionError",
    "SchemaEvaluationInputError",
    "SchemaEvaluationReceipt",
    "SchemaIssue",
    "SchemaProfile",
    "admit_schema",
    "evaluate_schema",
)
