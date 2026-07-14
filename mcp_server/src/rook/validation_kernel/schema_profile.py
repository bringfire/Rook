"""Closed Draft 2020-12 profiles over immutable kernel-owned JSON values."""

from __future__ import annotations

import hashlib
import importlib.metadata
import re
import struct
import threading
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
MAX_SCHEMA_ISSUE_PATH_BYTES = 512
MAX_SCHEMA_ISSUE_EVIDENCE_BYTES = 65_536
_MAX_WRAPPED_VALUE_REPR_BYTES = 8
_EXCEPTION_PROJECTION_MAX_BYTES = 4_096
_EXCEPTION_PROJECTION_MAX_ITEMS = 128
_EXCEPTION_PROJECTION_MAX_DEPTH = 16
_EXCEPTION_PROJECTION_EDGE_UNITS = 32
_EXCEPTION_PROJECTION_INTEGER_SAMPLE_BITS = 256
_EXCEPTION_PROJECTION_INTEGER_SAMPLE_MASK = (
    1 << _EXCEPTION_PROJECTION_INTEGER_SAMPLE_BITS
) - 1
_EXCEPTION_PROJECTION_NEGATIVE_SAMPLE_POLICY = (
    "twos_complement_sign_extension_only"
)
_TYPE_MODULE_DESCRIPTOR = type.__dict__["__module__"]
_TYPE_QUALNAME_DESCRIPTOR = type.__dict__["__qualname__"]

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
_SCHEMA_MAP_KEYWORDS = frozenset(
    {"$defs", "properties", "patternProperties", "dependentSchemas"}
)
_SCHEMA_SINGLE_KEYWORDS = frozenset(
    {
        "additionalProperties",
        "items",
        "not",
        "if",
        "then",
        "else",
        "propertyNames",
        "contains",
        "unevaluatedProperties",
        "unevaluatedItems",
    }
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
    "schema_dialect_invalid": "Schema dialect is invalid.",
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


def _utf8_size_with_limit(value: str, limit: int) -> int | None:
    size = 0
    for character in value:
        size += len(character.encode("utf-8"))
        if size > limit:
            return None
    return size


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
        if (
            _utf8_size_with_limit(
                self.instance_path, MAX_SCHEMA_ISSUE_PATH_BYTES
            )
            is None
            or _utf8_size_with_limit(
                self.schema_path, MAX_SCHEMA_ISSUE_PATH_BYTES
            )
            is None
        ):
            raise SchemaEvaluationInputError("schema issue path exceeds evidence limit")
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

    def __post_init__(self) -> None:
        if type(self.bounded_errors) is not tuple or any(
            type(issue) is not SchemaIssue for issue in self.bounded_errors
        ):
            raise SchemaEvaluationInputError(
                "schema evaluation errors must be an exact issue tuple"
            )
        if len(self.bounded_errors) > MAX_SCHEMA_ISSUES:
            raise SchemaEvaluationInputError("schema issue count exceeds limit")
        evidence_bytes = 0
        for issue in self.bounded_errors:
            evidence_bytes += _issue_evidence_bytes(issue)
            if evidence_bytes > MAX_SCHEMA_ISSUE_EVIDENCE_BYTES:
                raise SchemaEvaluationInputError(
                    "schema issue evidence exceeds byte limit"
                )


def _shape_reservation_signature(
    value: SchemaShapeReservation,
) -> tuple[bool, int | None, int, int | None, str | None]:
    return (
        value.accepted,
        value.attempted_shape_units,
        value.aggregate_before,
        value.aggregate_after,
        value.rejection_reason,
    )


class SchemaEvaluationReservation:
    """One-use authority for an exact schema and reserved instance shape."""

    __slots__ = (
        "_schema",
        "_schema_id",
        "_schema_fingerprint",
        "_schema_nodes",
        "_instance_nodes",
        "_per_evaluation_limit",
        "_shape_reservation",
        "_shape_signature",
        "_consumed",
        "_lock",
    )

    def __init__(self) -> None:
        raise TypeError(
            "SchemaEvaluationReservation values are created only by "
            "reserve_schema_evaluation"
        )

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("schema evaluation reservations are immutable")

    @classmethod
    def _create(
        cls,
        *,
        schema: AdmittedSchema,
        instance_nodes: int,
        per_evaluation_limit: int,
        shape_reservation: SchemaShapeReservation,
    ) -> "SchemaEvaluationReservation":
        value = object.__new__(cls)
        object.__setattr__(value, "_schema", schema)
        object.__setattr__(value, "_schema_id", schema.schema_id)
        object.__setattr__(
            value, "_schema_fingerprint", schema.schema_fingerprint
        )
        object.__setattr__(value, "_schema_nodes", schema.schema_nodes)
        object.__setattr__(value, "_instance_nodes", instance_nodes)
        object.__setattr__(
            value, "_per_evaluation_limit", per_evaluation_limit
        )
        object.__setattr__(value, "_shape_reservation", shape_reservation)
        object.__setattr__(
            value,
            "_shape_signature",
            _shape_reservation_signature(shape_reservation),
        )
        object.__setattr__(value, "_consumed", False)
        object.__setattr__(value, "_lock", threading.Lock())
        return value

    @property
    def schema_id(self) -> str:
        return self._schema_id

    @property
    def schema_fingerprint(self) -> str:
        return self._schema_fingerprint

    @property
    def schema_nodes(self) -> int:
        return self._schema_nodes

    @property
    def instance_nodes(self) -> int:
        return self._instance_nodes

    @property
    def per_evaluation_limit(self) -> int:
        return self._per_evaluation_limit

    @property
    def shape_reservation(self) -> SchemaShapeReservation:
        return self._shape_reservation

    def _claim(self, schema: AdmittedSchema, instance_nodes: int) -> None:
        with self._lock:
            if self._consumed:
                raise SchemaEvaluationInputError(
                    "schema evaluation reservation is already consumed"
                )
            object.__setattr__(self, "_consumed", True)
        if schema is not self._schema:
            raise SchemaEvaluationInputError(
                "schema evaluation reservation has the wrong schema identity"
            )
        if (
            schema.schema_id != self._schema_id
            or schema.schema_fingerprint != self._schema_fingerprint
            or schema.schema_nodes != self._schema_nodes
        ):
            raise SchemaEvaluationInputError(
                "schema evaluation reservation identity is inconsistent"
            )
        if instance_nodes != self._instance_nodes:
            raise SchemaEvaluationInputError(
                "schema evaluation reservation has the wrong instance node count"
            )
        if (
            type(self._shape_reservation) is not SchemaShapeReservation
            or _shape_reservation_signature(self._shape_reservation)
            != self._shape_signature
        ):
            raise SchemaEvaluationInputError(
                "schema evaluation shape reservation is inconsistent"
            )
        shape = self._shape_reservation
        if shape.accepted:
            expected_shape = self._schema_nodes * self._instance_nodes
            if (
                shape.attempted_shape_units != expected_shape
                or shape.aggregate_after != shape.aggregate_before + expected_shape
                or shape.rejection_reason is not None
            ):
                raise SchemaEvaluationInputError(
                    "schema evaluation shape reservation does not match its nodes"
                )
        elif (
            shape.attempted_shape_units is not None
            or shape.aggregate_after is not None
            or shape.rejection_reason
            not in (
                "shape_product_overflow",
                "per_evaluation_limit_exceeded",
                "invocation_shape_limit_exceeded",
            )
        ):
            raise SchemaEvaluationInputError(
                "schema evaluation rejection reservation is inconsistent"
            )

    def __copy__(self) -> object:
        raise TypeError("schema evaluation reservations cannot be copied")

    def __deepcopy__(self, memo: object) -> object:
        raise TypeError("schema evaluation reservations cannot be copied")

    def __reduce__(self) -> object:
        raise TypeError("schema evaluation reservations cannot be serialized")


@dataclass(frozen=True, slots=True)
class _BoundedPathEvidence:
    prefix: str
    full_byte_count: int
    full_sha256: bytes
    truncated: bool


@dataclass(frozen=True, slots=True)
class _ExceptionDetailProjection:
    digest: bytes
    projected_bytes: int
    projected_items: int
    maximum_depth: int
    truncated: bool


class _ExceptionProjectionWriter:
    __slots__ = ("_digest", "projected_bytes", "truncated")

    def __init__(self) -> None:
        self._digest = hashlib.sha256(
            b"rook.schema_evaluator_exception_projection:v2\0"
        )
        self.projected_bytes = 0
        self.truncated = False

    @property
    def exhausted(self) -> bool:
        return self.projected_bytes == _EXCEPTION_PROJECTION_MAX_BYTES

    @property
    def remaining(self) -> int:
        return _EXCEPTION_PROJECTION_MAX_BYTES - self.projected_bytes

    def mark_truncated(self) -> None:
        self.truncated = True

    def write(self, data: bytes) -> None:
        remaining = _EXCEPTION_PROJECTION_MAX_BYTES - self.projected_bytes
        if len(data) > remaining:
            self._digest.update(data[:remaining])
            self.projected_bytes += remaining
            self.truncated = True
            return
        self._digest.update(data)
        self.projected_bytes += len(data)

    def finish(self, *, projected_items: int, maximum_depth: int) -> bytes:
        self._digest.update(b"\x01" if self.truncated else b"\x00")
        self._digest.update(self.projected_bytes.to_bytes(8, "big"))
        self._digest.update(projected_items.to_bytes(8, "big"))
        self._digest.update(maximum_depth.to_bytes(8, "big"))
        return self._digest.digest()


class _BoundedUtf8Builder:
    __slots__ = ("_digest", "_full_byte_count", "_prefix", "_truncated")

    def __init__(self) -> None:
        self._digest = hashlib.sha256()
        self._full_byte_count = 0
        self._prefix = bytearray()
        self._truncated = False

    def write(self, piece: bytes) -> None:
        self._digest.update(piece)
        self._full_byte_count += len(piece)
        if self._truncated:
            return
        if len(self._prefix) + len(piece) > MAX_SCHEMA_ISSUE_PATH_BYTES:
            self._truncated = True
            return
        self._prefix.extend(piece)

    def finish(self) -> _BoundedPathEvidence:
        return _BoundedPathEvidence(
            prefix=self._prefix.decode("utf-8", errors="strict"),
            full_byte_count=self._full_byte_count,
            full_sha256=self._digest.digest(),
            truncated=self._truncated,
        )


class _OwnedStringView(str):
    """An exact immutable string whose diagnostic representation is constant."""

    __slots__ = ()

    def __new__(cls, value: str) -> "_OwnedStringView":
        if type(value) is not str:
            raise TypeError("owned string views require an exact string")
        return str.__new__(cls, value)

    def __repr__(self) -> str:
        return "<string>"


class _OwnedMappingView(Mapping[str, object]):
    """Lazy read-only mapping over one owned object."""

    __slots__ = ("_keys", "_owned", "_translate_refs")

    def __init__(self, owned: JsonObject, *, translate_refs: bool) -> None:
        self._owned = owned
        self._translate_refs = translate_refs
        self._keys = (
            None
            if translate_refs
            else tuple(_OwnedStringView(key) for key in owned)
        )

    def __getitem__(self, key: str) -> object:
        lookup_key = str.__str__(key) if type(key) is _OwnedStringView else key
        child = self._owned[lookup_key]
        if (
            self._translate_refs
            and lookup_key == "$ref"
            and type(child) is JsonString
        ):
            return _OwnedStringView("#" + quote(child.value, safe="/~"))
        return _adapt_owned(child, translate_refs=self._translate_refs)

    def __iter__(self) -> Iterator[str]:
        if self._keys is None:
            return iter(self._owned)
        return iter(self._keys)

    def __len__(self) -> int:
        return len(self._owned)

    def __repr__(self) -> str:
        return "<object>"


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

    def __repr__(self) -> str:
        return "<array>"


def _adapt_owned(value: JsonValue, *, translate_refs: bool) -> object:
    value_type = type(value)
    if value_type is JsonNull:
        return None
    if value_type is JsonBoolean:
        return value.value
    if value_type is JsonString:
        return _OwnedStringView(value.value)
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
    return type(instance) is _OwnedStringView


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
                "bounded_issue_path_utf8_bytes": MAX_SCHEMA_ISSUE_PATH_BYTES,
                "bounded_issue_evidence_utf8_bytes": (
                    MAX_SCHEMA_ISSUE_EVIDENCE_BYTES
                ),
                "bounded_wrapped_value_repr_kinds": (
                    "array",
                    "object",
                    "string",
                ),
                "bounded_wrapped_value_repr_utf8_bytes": (
                    _MAX_WRAPPED_VALUE_REPR_BYTES
                ),
                "exception_projection_bytes": _EXCEPTION_PROJECTION_MAX_BYTES,
                "exception_projection_items": _EXCEPTION_PROJECTION_MAX_ITEMS,
                "exception_projection_depth": _EXCEPTION_PROJECTION_MAX_DEPTH,
                "exception_integer_sample_bits": (
                    _EXCEPTION_PROJECTION_INTEGER_SAMPLE_BITS
                ),
                "exception_negative_integer_sample_policy": (
                    _EXCEPTION_PROJECTION_NEGATIVE_SAMPLE_POLICY
                ),
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
    if any(0xD800 <= ord(character) <= 0xDFFF for character in pointer):
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
    reachability_graph: dict[int, list[tuple[int, int]]],
    *,
    source: JsonValue,
    keyword: str,
    keyword_value: JsonValue,
    keyword_path: str,
    combinator_depth: int,
) -> None:
    child_depth = combinator_depth + (keyword in _COMBINATOR_KEYWORDS)

    def push(child: JsonValue, path: str) -> None:
        stack.append((child, path, child_depth))
        reachability_graph.setdefault(id(child), [])
        if keyword != "$defs":
            reachability_graph[id(source)].append((id(child), 0))

    if keyword in _SCHEMA_MAP_KEYWORDS and type(keyword_value) is JsonObject:
        for name, child in reversed(keyword_value.members):
            if type(child) in (JsonObject, JsonBoolean):
                push(child, _child_pointer(keyword_path, name.value))
        return
    if keyword in _SCHEMA_SINGLE_KEYWORDS and type(keyword_value) in (
        JsonObject,
        JsonBoolean,
    ):
        push(keyword_value, keyword_path)
        return
    if keyword in _SCHEMA_ARRAY_KEYWORDS and type(keyword_value) is JsonArray:
        for index in reversed(range(len(keyword_value))):
            child = keyword_value[index]
            if type(child) in (JsonObject, JsonBoolean):
                push(child, f"{keyword_path}/{index}")


def _maximum_reference_depth(
    graph: dict[int, list[tuple[int, int]]],
) -> int:
    indegrees = {node: 0 for node in graph}
    for edges in graph.values():
        for target, _ in edges:
            indegrees[target] += 1

    ready = [node for node, indegree in indegrees.items() if indegree == 0]
    depths = {node: 0 for node in graph}
    processed = 0
    maximum = 0
    while ready:
        source = ready.pop()
        processed += 1
        for target, reference_cost in graph[source]:
            target_depth = depths[source] + reference_cost
            if target_depth > depths[target]:
                depths[target] = target_depth
                maximum = max(maximum, target_depth)
            indegrees[target] -= 1
            if indegrees[target] == 0:
                ready.append(target)

    if processed != len(graph):
        raise SchemaAdmissionError("local_reference_cycle")
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
    reachability_graph: dict[int, list[tuple[int, int]]] = {id(value): []}

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
            if keyword == "$schema" and (
                type(keyword_value) is not JsonString
                or keyword_value.value != profile.metaschema_id
            ):
                raise SchemaAdmissionError("schema_dialect_invalid")
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
                reachability_graph,
                source=current,
                keyword=keyword,
                keyword_value=keyword_value,
                keyword_path=keyword_path,
                combinator_depth=combinator_depth,
            )

    for source, pointer in references:
        try:
            target = lookup_json_pointer(value, pointer)
        except ValueError:
            raise SchemaAdmissionError("local_reference_invalid") from None
        except KeyError:
            raise SchemaAdmissionError("local_reference_target_invalid") from None
        if id(target) not in schema_node_ids:
            raise SchemaAdmissionError("local_reference_target_invalid")
        reachability_graph[source].append((id(target), 1))

    maximum_reference_depth = _maximum_reference_depth(reachability_graph)
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


def _write_pointer_token(builder: _BoundedUtf8Builder, token: str) -> None:
    for character in token:
        if character == "~":
            builder.write(b"~0")
        elif character == "/":
            builder.write(b"~1")
        else:
            builder.write(character.encode("utf-8"))


def _bounded_path_pointer(path: Sequence[object]) -> _BoundedPathEvidence:
    builder = _BoundedUtf8Builder()
    for component in path:
        builder.write(b"/")
        if type(component) in (str, _OwnedStringView):
            _write_pointer_token(builder, component)
        elif type(component) is int:
            _write_pointer_token(builder, str(component))
        else:
            builder.write(b"?")
    return builder.finish()


def _bounded_existing_pointer(pointer: str) -> _BoundedPathEvidence:
    builder = _BoundedUtf8Builder()
    index = 0
    while index < len(pointer):
        character = pointer[index]
        if character == "~" and index + 1 < len(pointer):
            builder.write(pointer[index : index + 2].encode("ascii"))
            index += 2
            continue
        builder.write(character.encode("utf-8"))
        index += 1
    return builder.finish()


def _path_detail_fingerprint(
    instance_path: _BoundedPathEvidence,
    schema_path: _BoundedPathEvidence,
) -> str | None:
    if not instance_path.truncated and not schema_path.truncated:
        return None
    digest = hashlib.sha256(b"rook.schema_issue_paths:v1\0")
    for evidence in (instance_path, schema_path):
        digest.update(evidence.full_byte_count.to_bytes(16, "big"))
        digest.update(evidence.full_sha256)
    return f"sha256:{digest.hexdigest()}"


def _issue_from_validation_error(error: ValidationError) -> SchemaIssue:
    validator = error.validator
    code = validator if type(validator) is str and validator else "schema_validation"
    if len(code) > 64:
        code = "schema_validation"
    instance_path = _bounded_path_pointer(tuple(error.absolute_path))
    schema_path = _bounded_path_pointer(tuple(error.absolute_schema_path))
    return SchemaIssue(
        code=code,
        instance_path=instance_path.prefix,
        schema_path=schema_path.prefix,
        detail_sha256=_path_detail_fingerprint(instance_path, schema_path),
    )


def _projection_uint(value: int) -> bytes:
    if value >= 1 << 128:
        return b"\xff" * 16
    return value.to_bytes(16, "big")


def _project_exception_string(
    writer: _ExceptionProjectionWriter, value: str
) -> None:
    length = len(value)
    if length <= _EXCEPTION_PROJECTION_EDGE_UNITS * 2:
        prefix_count = length
        suffix_count = 0
        locally_truncated = False
    else:
        prefix_count = _EXCEPTION_PROJECTION_EDGE_UNITS
        suffix_count = _EXCEPTION_PROJECTION_EDGE_UNITS
        locally_truncated = True
        writer.mark_truncated()
    writer.write(b"S")
    writer.write(_projection_uint(length))
    writer.write(prefix_count.to_bytes(2, "big"))
    writer.write(suffix_count.to_bytes(2, "big"))
    writer.write(b"\x01" if locally_truncated else b"\x00")
    for index in range(prefix_count):
        writer.write(ord(value[index]).to_bytes(4, "big"))
    for index in range(length - suffix_count, length):
        writer.write(ord(value[index]).to_bytes(4, "big"))


def _project_exception_bytes(
    writer: _ExceptionProjectionWriter, value: bytes
) -> None:
    length = len(value)
    if length <= _EXCEPTION_PROJECTION_EDGE_UNITS * 2:
        prefix_count = length
        suffix_count = 0
        locally_truncated = False
    else:
        prefix_count = _EXCEPTION_PROJECTION_EDGE_UNITS
        suffix_count = _EXCEPTION_PROJECTION_EDGE_UNITS
        locally_truncated = True
        writer.mark_truncated()
    writer.write(b"Y")
    writer.write(_projection_uint(length))
    writer.write(prefix_count.to_bytes(2, "big"))
    writer.write(suffix_count.to_bytes(2, "big"))
    writer.write(b"\x01" if locally_truncated else b"\x00")
    writer.write(value[:prefix_count])
    if suffix_count:
        writer.write(value[length - suffix_count :])


def _project_type_identity(
    writer: _ExceptionProjectionWriter, value_type: type[object]
) -> None:
    for marker, descriptor in (
        (b"M", _TYPE_MODULE_DESCRIPTOR),
        (b"Q", _TYPE_QUALNAME_DESCRIPTOR),
    ):
        writer.write(marker)
        try:
            component = descriptor.__get__(value_type, type)
        except Exception:
            component = None
        if type(component) is str:
            _project_exception_string(writer, component)
        else:
            writer.write(b"?")


def _project_exception_integer(
    writer: _ExceptionProjectionWriter, value: int
) -> None:
    negative = value < 0
    sign = b"\x01" if negative else b"\x00"
    bit_length = value.bit_length()
    magnitude_length = max(1, (bit_length + 7) // 8)
    length_record = _projection_uint(magnitude_length)
    full_header = b"I" + sign + b"F" + length_record
    if len(full_header) + magnitude_length <= writer.remaining:
        magnitude = -value if negative else value
        writer.write(full_header)
        writer.write(magnitude.to_bytes(magnitude_length, "big"))
        return

    writer.mark_truncated()
    if negative:
        # Python has no bounded public operation for finite limbs of a negative
        # bigint. Its infinite two's-complement sign extension is all ones;
        # finite payload windows are intentionally omitted under truncation.
        high_window = _EXCEPTION_PROJECTION_INTEGER_SAMPLE_MASK
        low_window = _EXCEPTION_PROJECTION_INTEGER_SAMPLE_MASK
    else:
        high_shift = max(
            bit_length - _EXCEPTION_PROJECTION_INTEGER_SAMPLE_BITS,
            0,
        )
        high_window = (
            value >> high_shift
        ) & _EXCEPTION_PROJECTION_INTEGER_SAMPLE_MASK
        low_window = value & _EXCEPTION_PROJECTION_INTEGER_SAMPLE_MASK
    sample_bytes = _EXCEPTION_PROJECTION_INTEGER_SAMPLE_BITS // 8
    writer.write(b"I" + sign + b"T")
    writer.write(_projection_uint(bit_length))
    writer.write(length_record)
    writer.write(_EXCEPTION_PROJECTION_INTEGER_SAMPLE_BITS.to_bytes(2, "big"))
    writer.write(high_window.to_bytes(sample_bytes, "big"))
    writer.write(low_window.to_bytes(sample_bytes, "big"))


def _project_exception_scalar(
    writer: _ExceptionProjectionWriter, value: object
) -> None:
    value_type = type(value)
    if value is None:
        writer.write(b"N")
    elif value_type is bool:
        writer.write(b"B\x01" if value else b"B\x00")
    elif value_type is int:
        _project_exception_integer(writer, value)
    elif value_type is float:
        writer.write(b"F")
        writer.write(struct.pack(">d", value))
    elif value_type is str:
        _project_exception_string(writer, value)
    elif value_type is bytes:
        _project_exception_bytes(writer, value)
    else:
        writer.write(b"U")
        _project_type_identity(writer, value_type)


def _exception_detail_projection(
    exception: BaseException,
) -> _ExceptionDetailProjection:
    writer = _ExceptionProjectionWriter()
    writer.write(b"E")
    _project_type_identity(writer, type(exception))
    writer.write(b"A")
    try:
        arguments = BaseException.args.__get__(exception, BaseException)
    except Exception:
        arguments = ()
        writer.mark_truncated()

    stack: list[tuple[object, int]] = [(arguments, 0)]
    projected_items = 0
    maximum_depth = 0
    while stack and not writer.exhausted:
        if projected_items == _EXCEPTION_PROJECTION_MAX_ITEMS:
            writer.mark_truncated()
            break
        value, depth = stack.pop()
        projected_items += 1
        maximum_depth = max(maximum_depth, depth)

        if type(value) is not tuple:
            _project_exception_scalar(writer, value)
            continue

        length = len(value)
        if depth >= _EXCEPTION_PROJECTION_MAX_DEPTH:
            child_count = 0
            depth_limited = bool(length)
        else:
            available_items = (
                _EXCEPTION_PROJECTION_MAX_ITEMS
                - projected_items
                - len(stack)
            )
            child_count = min(length, max(available_items, 0))
            depth_limited = False
        children_truncated = child_count < length
        if children_truncated:
            writer.mark_truncated()
        writer.write(b"T")
        writer.write(_projection_uint(length))
        writer.write(child_count.to_bytes(2, "big"))
        writer.write(b"\x01" if depth_limited else b"\x00")
        writer.write(b"\x01" if children_truncated else b"\x00")
        for index in range(child_count - 1, -1, -1):
            stack.append((value[index], depth + 1))

    if stack:
        writer.mark_truncated()
    digest = writer.finish(
        projected_items=projected_items,
        maximum_depth=maximum_depth,
    )
    return _ExceptionDetailProjection(
        digest=digest,
        projected_bytes=writer.projected_bytes,
        projected_items=projected_items,
        maximum_depth=maximum_depth,
        truncated=writer.truncated,
    )


def _exception_detail_digest(exception: BaseException) -> bytes:
    return _exception_detail_projection(exception).digest


def _exception_detail_fingerprint(
    exception: BaseException,
    instance_path: _BoundedPathEvidence,
) -> str:
    digest = hashlib.sha256(b"rook.schema_evaluator_failure_evidence:v1\0")
    digest.update(_exception_detail_digest(exception))
    digest.update(instance_path.full_byte_count.to_bytes(16, "big"))
    digest.update(instance_path.full_sha256)
    return f"sha256:{digest.hexdigest()}"


def _issue_evidence_bytes(issue: SchemaIssue) -> int:
    fields = (
        issue.code,
        issue.instance_path,
        issue.schema_path,
        issue.detail_sha256 or "",
    )
    return 4 + sum(len(field.encode("utf-8")) for field in fields)


def _bounded_validation_issues(errors: object) -> tuple[SchemaIssue, ...]:
    bounded: list[SchemaIssue] = []
    evidence_bytes = 0
    for error in islice(iter(errors), MAX_SCHEMA_ISSUES):
        issue = _issue_from_validation_error(error)
        issue_bytes = _issue_evidence_bytes(issue)
        if evidence_bytes + issue_bytes > MAX_SCHEMA_ISSUE_EVIDENCE_BYTES:
            break
        evidence_bytes += issue_bytes
        bounded.append(issue)
    bounded.sort(
        key=lambda issue: (
            issue.instance_path,
            issue.schema_path,
            issue.code,
            issue.detail_sha256 or "",
        )
    )
    return tuple(bounded)


def _require_evaluation_schema(schema: object) -> tuple[AdmittedSchema, SchemaProfile]:
    if type(schema) is not AdmittedSchema:
        raise SchemaEvaluationInputError("evaluation requires an admitted schema")
    profile = _profile_for_admitted(schema)
    if (
        schema.schema_nodes != count_json_nodes(schema.value)
        or schema.schema_fingerprint != canonical_fingerprint(schema.value)
    ):
        raise SchemaEvaluationInputError("admitted schema identity is inconsistent")
    return schema, profile


def _require_evaluation_instance(
    instance: object, instance_binding: object
) -> JsonValue:
    if type(instance) not in _OWNED_VALUE_TYPES:
        raise SchemaEvaluationInputError("evaluation requires an owned instance")
    if type(instance_binding) is not InstanceBinding:
        raise SchemaEvaluationInputError("evaluation requires an instance binding")
    return instance


def reserve_schema_evaluation(
    schema: AdmittedSchema,
    *,
    instance_nodes: int,
    ledger: BudgetLedger,
) -> SchemaEvaluationReservation:
    """Reserve exact shape units now for one later canonical evaluation."""

    accepted_schema, profile = _require_evaluation_schema(schema)
    if type(instance_nodes) is not int or instance_nodes < 0:
        raise SchemaEvaluationInputError(
            "schema evaluation instance node count must be nonnegative"
        )
    if type(ledger) is not BudgetLedger:
        raise SchemaEvaluationInputError("evaluation requires the invocation ledger")
    shape_reservation = ledger.reserve_schema_shape(
        schema_nodes=accepted_schema.schema_nodes,
        instance_nodes=instance_nodes,
        per_evaluation_limit=profile.per_evaluation_shape_limit,
    )
    return SchemaEvaluationReservation._create(
        schema=accepted_schema,
        instance_nodes=instance_nodes,
        per_evaluation_limit=profile.per_evaluation_shape_limit,
        shape_reservation=shape_reservation,
    )


def evaluate_schema_with_reservation(
    schema: AdmittedSchema,
    instance: JsonValue,
    *,
    instance_binding: InstanceBinding,
    reservation: SchemaEvaluationReservation,
) -> SchemaEvaluationReceipt:
    """Consume one exact reservation without reading or mutating its ledger."""

    accepted_schema, _ = _require_evaluation_schema(schema)
    accepted_instance = _require_evaluation_instance(instance, instance_binding)
    if type(reservation) is not SchemaEvaluationReservation:
        raise SchemaEvaluationInputError(
            "evaluation requires an exact schema evaluation reservation"
        )
    instance_nodes = count_json_nodes(accepted_instance)
    reservation._claim(accepted_schema, instance_nodes)
    shape_reservation = reservation.shape_reservation
    if not shape_reservation.accepted:
        return SchemaEvaluationReceipt(
            reservation=shape_reservation,
            evaluator_invoked=False,
            evaluation_passed=None,
            bounded_errors=(),
            failure_code=shape_reservation.rejection_reason,
        )

    try:
        validator = _validator_for(accepted_schema)
        instance_view = _adapt_owned(accepted_instance, translate_refs=False)
        errors = _bounded_validation_issues(
            validator.iter_errors(instance_view)
        )
    except Exception as exception:
        instance_path = _bounded_existing_pointer(
            instance_binding.instance_pointer
        )
        return SchemaEvaluationReceipt(
            reservation=shape_reservation,
            evaluator_invoked=True,
            evaluation_passed=None,
            bounded_errors=(
                SchemaIssue(
                    code="schema_evaluator_exception",
                    instance_path=instance_path.prefix,
                    schema_path="",
                    detail_sha256=_exception_detail_fingerprint(
                        exception, instance_path
                    ),
                ),
            ),
            failure_code="schema_evaluator_failed",
        )

    passed = not errors
    return SchemaEvaluationReceipt(
        reservation=shape_reservation,
        evaluator_invoked=True,
        evaluation_passed=passed,
        bounded_errors=errors,
        failure_code=None if passed else "instance_schema_failed",
    )


def evaluate_schema(
    schema: AdmittedSchema,
    instance: JsonValue,
    *,
    instance_binding: InstanceBinding,
    ledger: BudgetLedger,
) -> SchemaEvaluationReceipt:
    """Reserve exact shape units, then evaluate once with no retrieval or formats."""

    accepted_schema, _ = _require_evaluation_schema(schema)
    accepted_instance = _require_evaluation_instance(instance, instance_binding)
    if type(ledger) is not BudgetLedger:
        raise SchemaEvaluationInputError("evaluation requires the invocation ledger")
    reservation = reserve_schema_evaluation(
        accepted_schema,
        instance_nodes=count_json_nodes(accepted_instance),
        ledger=ledger,
    )
    return evaluate_schema_with_reservation(
        accepted_schema,
        accepted_instance,
        instance_binding=instance_binding,
        reservation=reservation,
    )


__all__ = (
    "AdmittedSchema",
    "CORE_PROFILE",
    "CORE_SCHEMA_PROFILE_ID",
    "InstanceBinding",
    "MAX_SCHEMA_ISSUE_EVIDENCE_BYTES",
    "MAX_SCHEMA_ISSUE_PATH_BYTES",
    "MAX_SCHEMA_ISSUES",
    "PAYLOAD_PROFILE",
    "PAYLOAD_SCHEMA_PROFILE_ID",
    "SchemaAdmissionError",
    "SchemaEvaluationInputError",
    "SchemaEvaluationReservation",
    "SchemaEvaluationReceipt",
    "SchemaIssue",
    "SchemaProfile",
    "admit_schema",
    "evaluate_schema",
    "evaluate_schema_with_reservation",
    "reserve_schema_evaluation",
)
