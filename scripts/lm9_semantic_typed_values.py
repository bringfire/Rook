"""Deterministic typed-value mechanics for the LM9 scientific instrument."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
import sys
import weakref
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Literal, Mapping

from jsonschema import Draft202012Validator, validators


PROFILE_ID = "rook.json_schema_profile:lm9_typed_fact_v1"
HELPER_CONTRACT_ID = "rook.lm9.semantic_typed_values:v1"
DIALECT = "https://json-schema.org/draft/2020-12/schema"
MACHINE_KEY_PATTERN = r"^[a-z0-9]+(?:[._:-][a-z0-9]+)*$"
SCALAR_PATTERN = r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$"
ALLOWED_KEYWORDS = frozenset(
    {
        "$schema",
        "$id",
        "type",
        "const",
        "properties",
        "required",
        "additionalProperties",
        "propertyNames",
        "pattern",
        "not",
        "minProperties",
        "maxProperties",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
    }
)
FORBIDDEN_REFERENCE_KEYWORDS = frozenset(
    {
        "$ref",
        "$dynamicRef",
        "$recursiveRef",
        "$defs",
        "definitions",
        "$anchor",
        "$dynamicAnchor",
    }
)
ALLOWED_PATTERNS = frozenset({MACHINE_KEY_PATTERN, SCALAR_PATTERN})
REGISTRY_SCHEMA_ID = "rook.semantic_value_schema_registry:v2"
REGISTRY_VERSION = "rook.semantic_value_schemas:v2"
FORWARD_PAYLOAD_SCHEMA_ID = "rook.planner_task_typed_facts_payload:v1"
MAX_SAFE_INTEGER = 9_007_199_254_740_991
MAX_REGISTRY_BYTES = 4_194_304
MAX_ENVELOPE_BYTES = 1_048_576
MAX_SCHEMA_CANONICAL_BYTES = 65_536
MAX_SCHEMA_DEPTH = 32
MAX_SCHEMA_NODES = 4_096
MAX_COLLECTION_SIZE = 256
MAX_STRING_BYTES = 65_536
MAX_INSTANCE_DEPTH = 32
MAX_INSTANCE_NODES = 256 * 32
MAX_ISSUES = 1_024
MAX_EXPANSION_UNITS = 32_768
MAX_EVALUATION_SHAPE = 2_000_000
MAX_AGGREGATE_SHAPE = 16_000_000


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        _thaw_json(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def fingerprint(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def fingerprint_without(value: Mapping[str, object], field: str) -> str:
    return fingerprint({key: item for key, item in value.items() if key != field})


def sha256_prefixed(raw: bytes) -> str:
    if type(raw) is not bytes:
        raise TypeError("raw bytes are required")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _strict_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def parse_strict_json(raw: bytes, *, label: str = "JSON") -> object:
    if type(raw) is not bytes:
        raise TypeError(f"{label} bytes are required")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"{label} must not contain a UTF-8 BOM")
    try:
        text = raw.decode("utf-8", errors="strict")
        return json.loads(
            text,
            object_pairs_hook=_strict_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"invalid JSON constant: {token}")
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not strict UTF-8 JSON") from exc


def _freeze_json(value: object) -> object:
    if type(value) is dict:
        return MappingProxyType(
            {key: _freeze_json(item) for key, item in value.items()}
        )
    if type(value) is list:
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def resolve_json_pointer(value: object, pointer: str) -> object:
    if type(pointer) is not str or not pointer.startswith("/"):
        raise ValueError("JSON pointer is invalid")
    current = value
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping) and token in current:
            current = current[token]
        elif isinstance(current, (list, tuple)) and token.isdigit():
            index = int(token)
            if index >= len(current):
                raise ValueError("JSON pointer does not resolve")
            current = current[index]
        else:
            raise ValueError("JSON pointer does not resolve")
    return current


@dataclass(frozen=True)
class RuntimeIdentity:
    implementation_name: str
    implementation_cache_tag: str | None
    implementation_version: tuple[int, int, int, str, int]
    implementation_hexversion: int
    version_info: tuple[int, int, int, str, int]
    version: str
    jsonschema_version: str
    validator_class: str


@dataclass(frozen=True)
class ProfileIdentity:
    value: Mapping[str, object]
    fingerprint: str


@dataclass(frozen=True)
class AdmittedSchema:
    schema_id: str
    schema_fingerprint: str
    schema_document: Mapping[str, object]
    schema_nodes: int
    expansion_units: int


@dataclass(frozen=True)
class VerifiedSemanticValueRegistry:
    value: Mapping[str, object]
    fingerprint: str
    entries: Mapping[str, AdmittedSchema]
    profile: ProfileIdentity


@dataclass(frozen=True)
class ValidationIssue:
    instance_path: str
    schema_path: str
    keyword: str
    detail_fingerprint: str


@dataclass(frozen=True)
class EvaluationBudget:
    limit: int = MAX_AGGREGATE_SHAPE


@dataclass(frozen=True)
class VerifiedTypedValue:
    value: Mapping[str, object]
    canonical_bytes: bytes
    fingerprint: str
    schema: AdmittedSchema


@dataclass(frozen=True)
class VerifiedUnitContextEntry:
    artifact_id: str
    json_pointer: str
    value_schema: str
    canonical_value_bytes: bytes
    typed_value_fingerprint: str
    environment_session_id: str
    task_session_id: str
    observed_at: str
    expires_at: str


def runtime_identity_from_values(
    *,
    implementation_name: str,
    implementation_cache_tag: str | None,
    implementation_version: tuple[int, int, int, str, int],
    implementation_hexversion: int,
    version_info: tuple[int, int, int, str, int],
    version: str,
    jsonschema_version: str,
) -> RuntimeIdentity:
    return RuntimeIdentity(
        implementation_name=implementation_name,
        implementation_cache_tag=implementation_cache_tag,
        implementation_version=implementation_version,
        implementation_hexversion=implementation_hexversion,
        version_info=version_info,
        version=version,
        jsonschema_version=jsonschema_version,
        validator_class=(
            "jsonschema.validators.Draft202012Validator+rook_exact_json_types"
        ),
    )


def current_runtime_identity() -> RuntimeIdentity:
    implementation = sys.implementation.version
    version_info = sys.version_info
    return runtime_identity_from_values(
        implementation_name=sys.implementation.name,
        implementation_cache_tag=sys.implementation.cache_tag,
        implementation_version=(
            implementation.major,
            implementation.minor,
            implementation.micro,
            implementation.releaselevel,
            implementation.serial,
        ),
        implementation_hexversion=sys.implementation.hexversion,
        version_info=(
            version_info.major,
            version_info.minor,
            version_info.micro,
            version_info.releaselevel,
            version_info.serial,
        ),
        version=sys.version,
        jsonschema_version=importlib.metadata.version("jsonschema"),
    )


def runtime_identity_value(runtime: RuntimeIdentity) -> dict[str, object]:
    value = asdict(runtime)
    value["implementation_version"] = list(runtime.implementation_version)
    value["version_info"] = list(runtime.version_info)
    return value


def build_profile_identity(runtime: RuntimeIdentity) -> ProfileIdentity:
    if type(runtime) is not RuntimeIdentity:
        raise TypeError("exact runtime identity is required")
    value = {
        "profile_id": PROFILE_ID,
        "helper_contract_id": HELPER_CONTRACT_ID,
        "dialect": DIALECT,
        "ownership": "scientific_instrument_only",
        "runtime": runtime_identity_value(runtime),
        "evaluator": {
            "class": runtime.validator_class,
            "jsonschema_distribution_version": runtime.jsonschema_version,
            "metaschema_fingerprint": fingerprint(Draft202012Validator.META_SCHEMA),
            "type_policy": "rook.json_python_exact_types:v1",
            "format_checker": None,
            "reference_retrieval": False,
        },
        "admission": {
            "allowed_keywords": sorted(ALLOWED_KEYWORDS),
            "forbidden_reference_keywords": sorted(
                FORBIDDEN_REFERENCE_KEYWORDS
            ),
            "allowed_patterns": sorted(ALLOWED_PATTERNS),
            "structural_algorithm": "rook.lm9.schema_tree_admission:v1",
            "expansion_algorithm": (
                "rook.lm9.schema_structural_reachability:v1"
            ),
        },
        "limits": {
            "raw_registry_bytes": MAX_REGISTRY_BYTES,
            "raw_instance_envelope_bytes": MAX_ENVELOPE_BYTES,
            "embedded_schema_canonical_bytes": MAX_SCHEMA_CANONICAL_BYTES,
            "schema_depth": MAX_SCHEMA_DEPTH,
            "schema_nodes": MAX_SCHEMA_NODES,
            "schema_collection_size": MAX_COLLECTION_SIZE,
            "schema_string_bytes": MAX_STRING_BYTES,
            "instance_depth": MAX_INSTANCE_DEPTH,
            "instance_collection_size": MAX_COLLECTION_SIZE,
            "instance_string_bytes": MAX_STRING_BYTES,
            "scalar_characters": 1_024,
            "issues": MAX_ISSUES,
            "evaluation_expansion_units": MAX_EXPANSION_UNITS,
            "per_evaluation_shape_units": MAX_EVALUATION_SHAPE,
            "aggregate_shape_units": MAX_AGGREGATE_SHAPE,
        },
        "work_metric": (
            "rook.schema_evaluation_shape:"
            "max_schema_or_expansion_times_instance:v1"
        ),
        "issue_policy": {
            "ordering": [
                "instance_json_pointer",
                "schema_json_pointer",
                "failed_keyword",
                "bounded_detail_fingerprint",
            ],
            "truncation": "forbidden",
        },
    }
    return ProfileIdentity(_freeze_json(value), fingerprint(value))


def _schema_children(schema: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    children: list[Mapping[str, object]] = []
    properties = schema.get("properties")
    if isinstance(properties, Mapping):
        children.extend(
            item for item in properties.values() if isinstance(item, Mapping)
        )
    for key in ("additionalProperties", "propertyNames", "not"):
        item = schema.get(key)
        if isinstance(item, Mapping):
            children.append(item)
    return tuple(children)


def _walk_schema(
    schema: Mapping[str, object],
    *,
    depth: int = 1,
) -> tuple[int, int]:
    if depth > MAX_SCHEMA_DEPTH:
        raise ValueError("schema depth exceeds profile")
    for key in schema:
        if key not in ALLOWED_KEYWORDS:
            raise ValueError(f"schema keyword is not admitted: {key}")
    pattern = schema.get("pattern")
    if pattern is not None and pattern not in ALLOWED_PATTERNS:
        raise ValueError("schema pattern is not admitted")
    for item in schema.values():
        if isinstance(item, str) and len(item.encode("utf-8")) > MAX_STRING_BYTES:
            raise ValueError("schema string exceeds profile")
        if isinstance(item, (list, tuple, Mapping)) and len(item) > MAX_COLLECTION_SIZE:
            raise ValueError("schema collection exceeds profile")
    nodes = _json_node_count(schema)
    children = _schema_children(schema)
    expansion = max(
        1,
        sum(_walk_schema(child, depth=depth + 1)[1] for child in children),
    )
    return nodes, min(expansion, MAX_EXPANSION_UNITS + 1)


def _json_node_count(value: object) -> int:
    if isinstance(value, Mapping):
        return 1 + sum(
            1 + _json_node_count(item) for item in value.values()
        )
    if isinstance(value, (list, tuple)):
        return 1 + sum(_json_node_count(item) for item in value)
    return 1


def admit_schema_document(
    value: Mapping[str, object], *, profile: ProfileIdentity
) -> AdmittedSchema:
    if type(profile) is not ProfileIdentity:
        raise TypeError("verified profile identity is required")
    plain = _thaw_json(value)
    if type(plain) is not dict:
        raise ValueError("schema document must be an object")
    if plain.get("$schema") != DIALECT:
        raise ValueError("schema dialect mismatch")
    schema_id = plain.get("$id")
    if type(schema_id) is not str or not schema_id:
        raise ValueError("schema document identity is invalid")
    if len(canonical_json_bytes(plain)) > MAX_SCHEMA_CANONICAL_BYTES:
        raise ValueError("schema canonical bytes exceed profile")
    nodes, expansion = _walk_schema(plain)
    if nodes > MAX_SCHEMA_NODES or expansion > MAX_EXPANSION_UNITS:
        raise ValueError("schema structural budget exceeded")
    return AdmittedSchema(
        schema_id=schema_id,
        schema_fingerprint=fingerprint(plain),
        schema_document=_freeze_json(plain),
        schema_nodes=nodes,
        expansion_units=expansion,
    )


_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine_many(
    {
        "object": lambda _checker, value: type(value) is dict,
        "array": lambda _checker, value: type(value) is list,
        "string": lambda _checker, value: type(value) is str,
        "integer": lambda _checker, value: type(value) is int,
        "boolean": lambda _checker, value: type(value) is bool,
        "null": lambda _checker, value: value is None,
    }
)
_SEALED_VALIDATOR = validators.extend(
    Draft202012Validator,
    type_checker=_TYPE_CHECKER,
)


def verify_semantic_value_registry(
    value: Mapping[str, object],
    *,
    raw_registry_byte_count: int,
    runtime: RuntimeIdentity,
) -> VerifiedSemanticValueRegistry:
    if not 0 <= raw_registry_byte_count <= MAX_REGISTRY_BYTES:
        raise ValueError("registry byte limit exceeded")
    plain = _thaw_json(value)
    if type(plain) is not dict or set(plain) != {
        "schema",
        "registry_id",
        "registry_version",
        "json_schema_dialect",
        "schema_evaluator_profile",
        "schema_evaluator_profile_fingerprint",
        "entries",
        "registry_fingerprint",
    }:
        raise ValueError("semantic-value registry shape is invalid")
    profile = build_profile_identity(runtime)
    if (
        plain["schema"] != REGISTRY_SCHEMA_ID
        or plain["registry_id"] != "semantic_value_schema_registry"
        or plain["registry_version"] != REGISTRY_VERSION
        or plain["json_schema_dialect"] != DIALECT
        or plain["schema_evaluator_profile"] != PROFILE_ID
        or plain["schema_evaluator_profile_fingerprint"] != profile.fingerprint
    ):
        raise ValueError("semantic-value registry identity mismatch")
    rows = plain["entries"]
    if type(rows) is not list or len(rows) != 4:
        raise ValueError("semantic-value registry entries are invalid")
    entries: dict[str, AdmittedSchema] = {}
    for row in rows:
        if type(row) is not dict or set(row) != {
            "schema_id",
            "schema_fingerprint",
            "schema_document",
        }:
            raise ValueError("semantic-value registry entry shape is invalid")
        admitted = admit_schema_document(row["schema_document"], profile=profile)
        if (
            row["schema_id"] != admitted.schema_id
            or row["schema_fingerprint"] != admitted.schema_fingerprint
            or admitted.schema_id in entries
        ):
            raise ValueError("semantic-value registry entry identity mismatch")
        entries[admitted.schema_id] = admitted
    if list(entries) != sorted(entries):
        raise ValueError("semantic-value registry entries are not ordered")
    if set(entries) != {
        "rook.semantic_boolean:v1",
        "rook.semantic_integer:v1",
        "rook.semantic_scalar:v1",
        "rook.semantic_string:v1",
    }:
        raise ValueError("semantic-value registry entry set is invalid")
    if plain["registry_fingerprint"] != fingerprint_without(
        plain, "registry_fingerprint"
    ):
        raise ValueError("semantic-value registry fingerprint mismatch")
    return VerifiedSemanticValueRegistry(
        value=_freeze_json(plain),
        fingerprint=plain["registry_fingerprint"],
        entries=MappingProxyType(entries),
        profile=profile,
    )


def _instance_depth(value: object, depth: int = 1) -> int:
    if isinstance(value, Mapping):
        return max([depth] + [_instance_depth(item, depth + 1) for item in value.values()])
    if isinstance(value, (list, tuple)):
        return max([depth] + [_instance_depth(item, depth + 1) for item in value])
    return depth


def validate_schema_instance(
    instance: object,
    *,
    schema: AdmittedSchema,
    aggregate_budget: EvaluationBudget,
    instance_path: str,
) -> tuple[ValidationIssue, ...]:
    plain = _thaw_json(instance)
    nodes = _json_node_count(plain)
    if _instance_depth(plain) > MAX_INSTANCE_DEPTH:
        raise ValueError("instance depth exceeds profile")
    shape = max(schema.schema_nodes, schema.expansion_units) * nodes
    if shape > MAX_EVALUATION_SHAPE or shape > aggregate_budget.limit:
        raise ValueError("instance evaluation budget exceeded")
    errors = sorted(
        _SEALED_VALIDATOR(_thaw_json(schema.schema_document)).iter_errors(plain),
        key=lambda error: (list(error.path), list(error.schema_path)),
    )
    if len(errors) > MAX_ISSUES:
        raise ValueError("validation issue limit exceeded")
    return tuple(
        ValidationIssue(
            instance_path=instance_path
            + "".join(f"/{item}" for item in error.path),
            schema_path="".join(f"/{item}" for item in error.schema_path),
            keyword=str(error.validator),
            detail_fingerprint=fingerprint({"message": error.message}),
        )
        for error in errors
    )


class VerifiedUnitContextIndex:
    """Opaque module-issued carrier; public construction is forbidden."""

    __slots__ = ("__snapshot", "__entries", "__proof_fingerprint", "__weakref__")
    __hash__ = object.__hash__
    __eq__ = object.__eq__

    def __new__(cls, *_args: object, **_kwargs: object):
        raise TypeError("VerifiedUnitContextIndex is module-issued only")

    def __init_subclass__(cls, **_kwargs: object) -> None:
        raise TypeError("VerifiedUnitContextIndex cannot be subclassed")

    def __copy__(self):
        return self

    def __deepcopy__(self, _memo: object):
        return self

    def __reduce_ex__(self, _protocol: int):
        raise TypeError("VerifiedUnitContextIndex is not serializable")

    @property
    def entries(self) -> Mapping[tuple[str, str], VerifiedUnitContextEntry]:
        return object.__getattribute__(
            self, "_VerifiedUnitContextIndex__entries"
        )

    @property
    def proof_fingerprint(self) -> str:
        return object.__getattribute__(
            self, "_VerifiedUnitContextIndex__proof_fingerprint"
        )


def _instant(value: object, label: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise ValueError(f"invalid {label}")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"invalid {label}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"invalid {label}")
    return parsed


def _unit_entry_value(entry: VerifiedUnitContextEntry) -> dict[str, object]:
    return {
        "artifact_id": entry.artifact_id,
        "json_pointer": entry.json_pointer,
        "value_schema": entry.value_schema,
        "canonical_value_raw_sha256": sha256_prefixed(
            entry.canonical_value_bytes
        ),
        "typed_value_fingerprint": entry.typed_value_fingerprint,
        "environment_session_id": entry.environment_session_id,
        "task_session_id": entry.task_session_id,
        "observed_at": entry.observed_at,
        "expires_at": entry.expires_at,
    }


def _validate_and_derive_unit_context_authority(
    *,
    environment_artifact_bytes: bytes,
    environment_payload_schema_bytes: bytes,
    attempt_context_bytes: bytes,
    expected_artifact_fingerprint: str,
    expected_environment_session_id: str,
    expected_task_session_id: str,
    evaluated_at: str,
) -> tuple[bytes, tuple[VerifiedUnitContextEntry, ...], str]:
    environment = parse_strict_json(
        environment_artifact_bytes, label="environment artifact"
    )
    payload_schema = parse_strict_json(
        environment_payload_schema_bytes, label="environment payload schema"
    )
    attempt = parse_strict_json(attempt_context_bytes, label="attempt context")
    if type(environment) is not dict or type(payload_schema) is not dict:
        raise ValueError("environment authority objects are invalid")
    if type(attempt) is not dict:
        raise ValueError("attempt context is invalid")
    if attempt.get("context_fingerprint") != fingerprint_without(
        attempt, "context_fingerprint"
    ):
        raise ValueError("attempt context fingerprint mismatch")
    if (
        attempt.get("trusted_clock_source") != "deterministic_fixture"
        or attempt.get("task_session_id") != expected_task_session_id
        or attempt.get("environment_session_id")
        != expected_environment_session_id
        or attempt.get("evaluated_at") != evaluated_at
    ):
        raise ValueError("attempt context authority mismatch")
    if environment.get("artifact_fingerprint") != fingerprint_without(
        environment, "artifact_fingerprint"
    ) or environment.get("artifact_fingerprint") != expected_artifact_fingerprint:
        raise ValueError("environment artifact fingerprint mismatch")
    if (
        environment.get("artifact_id") != "environment_snapshot"
        or environment.get("schema") != "rook.environment_snapshot:v1"
        or environment.get("environment_session_id")
        != expected_environment_session_id
        or environment.get("payload_schema_fingerprint")
        != fingerprint(payload_schema)
    ):
        raise ValueError("environment artifact identity mismatch")
    issuer = environment.get("issuer")
    if (
        type(issuer) is not dict
        or issuer.get("kind") != "trusted_environment_gateway"
        or type(issuer.get("authority_id")) is not str
    ):
        raise ValueError("environment issuer is not trusted")
    errors = list(
        Draft202012Validator(payload_schema).iter_errors(environment.get("payload"))
    )
    if errors:
        raise ValueError("environment payload schema failed")
    observed_at = environment.get("observed_at")
    expires_at = environment.get("expires_at")
    if not _instant(observed_at, "observed_at") <= _instant(
        evaluated_at, "evaluated_at"
    ) < _instant(expires_at, "expires_at"):
        raise ValueError("environment observation is stale")
    bindings = environment.get("value_bindings")
    if type(bindings) is not list or len(bindings) != 1:
        raise ValueError("environment unit-context binding is invalid")
    binding = bindings[0]
    if type(binding) is not dict or set(binding) != {
        "binding_id",
        "json_pointer",
        "semantic_key",
        "value_schema",
        "typed_value_fingerprint",
        "authority_kind",
    }:
        raise ValueError("environment unit-context binding shape is invalid")
    if (
        binding["binding_id"] != "environment-value.document_unit_context"
        or binding["json_pointer"] != "/document/unit_context"
        or binding["semantic_key"] != "document_unit_context"
        or binding["value_schema"] != "rook.semantic_unit_context:v1"
        or binding["authority_kind"] != "environment_observation"
    ):
        raise ValueError("environment unit-context binding identity mismatch")
    resolved = resolve_json_pointer(environment["payload"], binding["json_pointer"])
    expected_typed_fingerprint = fingerprint(
        {"schema": binding["value_schema"], "value": resolved}
    )
    if binding["typed_value_fingerprint"] != expected_typed_fingerprint:
        raise ValueError("environment unit-context fingerprint mismatch")
    assert isinstance(observed_at, str) and isinstance(expires_at, str)
    entry = VerifiedUnitContextEntry(
        artifact_id="environment_snapshot",
        json_pointer="/document/unit_context",
        value_schema="rook.semantic_unit_context:v1",
        canonical_value_bytes=canonical_json_bytes(resolved),
        typed_value_fingerprint=expected_typed_fingerprint,
        environment_session_id=expected_environment_session_id,
        task_session_id=expected_task_session_id,
        observed_at=observed_at,
        expires_at=expires_at,
    )
    snapshot_value = {
        "environment_artifact_hex": environment_artifact_bytes.hex(),
        "environment_payload_schema_hex": environment_payload_schema_bytes.hex(),
        "attempt_context_hex": attempt_context_bytes.hex(),
        "expected_artifact_fingerprint": expected_artifact_fingerprint,
        "expected_environment_session_id": expected_environment_session_id,
        "expected_task_session_id": expected_task_session_id,
        "evaluated_at": evaluated_at,
    }
    snapshot = canonical_json_bytes(snapshot_value)
    entries = (entry,)
    proof = fingerprint(
        {
            "snapshot_raw_sha256": sha256_prefixed(snapshot),
            "entries": [_unit_entry_value(entry)],
        }
    )
    return snapshot, entries, proof


def _build_unit_context_authority_gate():
    @dataclass(frozen=True)
    class AuthoritySeal:
        canonical_authority_snapshot: bytes
        entries: tuple[VerifiedUnitContextEntry, ...]
        proof_fingerprint: str

    issued: weakref.WeakKeyDictionary[
        VerifiedUnitContextIndex, AuthoritySeal
    ] = weakref.WeakKeyDictionary()

    def compare_projection_to_seal(
        carrier: VerifiedUnitContextIndex,
        authority: AuthoritySeal,
    ) -> None:
        projected_snapshot = object.__getattribute__(
            carrier, "_VerifiedUnitContextIndex__snapshot"
        )
        projected_entries = object.__getattribute__(
            carrier, "_VerifiedUnitContextIndex__entries"
        )
        projected_fingerprint = object.__getattribute__(
            carrier, "_VerifiedUnitContextIndex__proof_fingerprint"
        )
        expected_entries = MappingProxyType(
            {
                (entry.artifact_id, entry.json_pointer): entry
                for entry in authority.entries
            }
        )
        if (
            projected_snapshot != authority.canonical_authority_snapshot
            or dict(projected_entries) != dict(expected_entries)
            or projected_fingerprint != authority.proof_fingerprint
        ):
            raise ValueError("unit-context proof projection differs from authority")

    def rederive_and_compare_authority(authority: AuthoritySeal) -> None:
        snapshot = parse_strict_json(
            authority.canonical_authority_snapshot,
            label="unit-context proof snapshot",
        )
        if type(snapshot) is not dict:
            raise ValueError("unit-context proof snapshot is invalid")
        rebuilt_snapshot, rebuilt_entries, rebuilt_fingerprint = (
            _validate_and_derive_unit_context_authority(
                environment_artifact_bytes=bytes.fromhex(
                    snapshot["environment_artifact_hex"]
                ),
                environment_payload_schema_bytes=bytes.fromhex(
                    snapshot["environment_payload_schema_hex"]
                ),
                attempt_context_bytes=bytes.fromhex(
                    snapshot["attempt_context_hex"]
                ),
                expected_artifact_fingerprint=snapshot[
                    "expected_artifact_fingerprint"
                ],
                expected_environment_session_id=snapshot[
                    "expected_environment_session_id"
                ],
                expected_task_session_id=snapshot["expected_task_session_id"],
                evaluated_at=snapshot["evaluated_at"],
            )
        )
        if (
            rebuilt_snapshot != authority.canonical_authority_snapshot
            or rebuilt_entries != authority.entries
            or rebuilt_fingerprint != authority.proof_fingerprint
        ):
            raise ValueError("unit-context proof authority reconstruction failed")

    def derive(
        *,
        environment_artifact_bytes: bytes,
        environment_payload_schema_bytes: bytes,
        attempt_context_bytes: bytes,
        expected_artifact_fingerprint: str,
        expected_environment_session_id: str,
        expected_task_session_id: str,
        evaluated_at: str,
    ) -> VerifiedUnitContextIndex:
        snapshot, entries, proof_fingerprint = (
            _validate_and_derive_unit_context_authority(
                environment_artifact_bytes=environment_artifact_bytes,
                environment_payload_schema_bytes=environment_payload_schema_bytes,
                attempt_context_bytes=attempt_context_bytes,
                expected_artifact_fingerprint=expected_artifact_fingerprint,
                expected_environment_session_id=expected_environment_session_id,
                expected_task_session_id=expected_task_session_id,
                evaluated_at=evaluated_at,
            )
        )
        authority = AuthoritySeal(snapshot, entries, proof_fingerprint)
        carrier = object.__new__(VerifiedUnitContextIndex)
        object.__setattr__(
            carrier,
            "_VerifiedUnitContextIndex__snapshot",
            authority.canonical_authority_snapshot,
        )
        object.__setattr__(
            carrier,
            "_VerifiedUnitContextIndex__entries",
            MappingProxyType(
                {
                    (entry.artifact_id, entry.json_pointer): entry
                    for entry in authority.entries
                }
            ),
        )
        object.__setattr__(
            carrier,
            "_VerifiedUnitContextIndex__proof_fingerprint",
            authority.proof_fingerprint,
        )
        issued[carrier] = authority
        return carrier

    def consume(
        carrier: VerifiedUnitContextIndex,
    ) -> VerifiedUnitContextIndex:
        if type(carrier) is not VerifiedUnitContextIndex:
            raise ValueError("unit-context proof carrier was not issued")
        authority = issued.get(carrier)
        if authority is None:
            raise ValueError("unit-context proof carrier was not issued")
        compare_projection_to_seal(carrier, authority)
        rederive_and_compare_authority(authority)
        return carrier

    return derive, consume


derive_verified_unit_context_index, _consume_unit_context_index = (
    _build_unit_context_authority_gate()
)
del _build_unit_context_authority_gate


def validate_typed_value(
    value: Mapping[str, object],
    *,
    registry: VerifiedSemanticValueRegistry,
    unit_context_index: VerifiedUnitContextIndex | None,
    required_presence: Literal[
        "forward_fact", "recipe_assumption", "recipe_derived"
    ],
    aggregate_budget: EvaluationBudget,
    instance_path: str,
) -> VerifiedTypedValue:
    plain = _thaw_json(value)
    if type(plain) is not dict:
        raise ValueError("typed value must be an object")
    if required_presence in {"forward_fact", "recipe_assumption"}:
        expected_fields = {"schema", "value", "unit", "unit_context_ref"}
    elif required_presence == "recipe_derived":
        expected_fields = {"schema", "value"}
    else:
        raise ValueError("unknown typed-value occurrence")
    if set(plain) != expected_fields:
        raise ValueError("typed-value occurrence fields are invalid")
    schema_id = plain.get("schema")
    schema = registry.entries.get(schema_id)
    if schema is None:
        raise ValueError("typed-value schema is not registered")
    issues = validate_schema_instance(
        plain,
        schema=schema,
        aggregate_budget=aggregate_budget,
        instance_path=instance_path,
    )
    if issues:
        raise ValueError(
            f"typed value failed {issues[0].keyword} at {issues[0].instance_path}"
        )
    if schema_id == "rook.semantic_scalar:v1":
        if required_presence == "recipe_derived":
            raise ValueError("current recipe-derived occurrence cannot carry scalar")
        if unit_context_index is None:
            raise ValueError("scalar requires verified unit-context authority")
        verified_index = _consume_unit_context_index(unit_context_index)
        reference = plain["unit_context_ref"]
        assert isinstance(reference, dict)
        key = (reference["artifact_id"], reference["json_pointer"])
        entry = verified_index.entries.get(key)
        if entry is None or entry.value_schema != "rook.semantic_unit_context:v1":
            raise ValueError("scalar unit-context authority is unresolved")
    raw = canonical_json_bytes(plain)
    return VerifiedTypedValue(
        value=_freeze_json(plain),
        canonical_bytes=raw,
        fingerprint=sha256_prefixed(raw),
        schema=schema,
    )


__all__ = [
    "AdmittedSchema",
    "DIALECT",
    "EvaluationBudget",
    "FORWARD_PAYLOAD_SCHEMA_ID",
    "HELPER_CONTRACT_ID",
    "MACHINE_KEY_PATTERN",
    "PROFILE_ID",
    "ProfileIdentity",
    "REGISTRY_SCHEMA_ID",
    "REGISTRY_VERSION",
    "RuntimeIdentity",
    "SCALAR_PATTERN",
    "ValidationIssue",
    "VerifiedSemanticValueRegistry",
    "VerifiedTypedValue",
    "VerifiedUnitContextEntry",
    "VerifiedUnitContextIndex",
    "admit_schema_document",
    "build_profile_identity",
    "canonical_json_bytes",
    "current_runtime_identity",
    "derive_verified_unit_context_index",
    "fingerprint",
    "fingerprint_without",
    "parse_strict_json",
    "resolve_json_pointer",
    "runtime_identity_from_values",
    "runtime_identity_value",
    "sha256_prefixed",
    "validate_schema_instance",
    "validate_typed_value",
    "verify_semantic_value_registry",
]
