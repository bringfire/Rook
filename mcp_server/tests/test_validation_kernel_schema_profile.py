from __future__ import annotations

import hashlib
import importlib.metadata
import re
import threading
import time
import tracemalloc
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace

import pytest
from jsonschema import Draft202012Validator

import rook.validation_kernel as validation_kernel
import rook.validation_kernel.schema_profile as schema_profile_module
from rook.validation_kernel.budget import (
    BudgetLedger,
    LM9A_BUDGET_MANIFEST,
    SchemaShapeReservation,
)
from rook.validation_kernel.canonical_json import (
    canonical_fingerprint,
    canonical_json_bytes,
)
from rook.validation_kernel.owned_json import (
    JsonObject,
    count_json_nodes,
    lookup_json_pointer,
    own_trusted_json,
)
from rook.validation_kernel.schema_profile import (
    CORE_PROFILE,
    CORE_SCHEMA_PROFILE_ID,
    MAX_SCHEMA_ISSUES,
    PAYLOAD_PROFILE,
    PAYLOAD_SCHEMA_PROFILE_ID,
    AdmittedSchema,
    InstanceBinding,
    SchemaAdmissionError,
    SchemaEvaluationInputError,
    SchemaEvaluationReservation,
    SchemaEvaluationReceipt,
    SchemaIssue,
    SchemaProfile,
    admit_schema,
    evaluate_schema,
    evaluate_schema_with_reservation,
    reserve_schema_evaluation,
)


DRAFT_2020_12_METASCHEMA_ID = "https://json-schema.org/draft/2020-12/schema"
EXPECTED_SCHEMA_ISSUE_PATH_BYTES = 512
EXPECTED_SCHEMA_ISSUE_EVIDENCE_BYTES = 65_536
EXPECTED_INSTANCE_POINTER_UTF8_BYTES = 4_096
EXPECTED_WRAPPED_VALUE_REPR_BYTES = 8
EXPECTED_EXCEPTION_PROJECTION_BYTES = 4_096
EXPECTED_EXCEPTION_PROJECTION_ITEMS = 128
EXPECTED_EXCEPTION_PROJECTION_DEPTH = 16
EXPECTED_EXCEPTION_INTEGER_SAMPLE_BITS = 256
EXPECTED_EXCEPTION_NEGATIVE_SAMPLE_POLICY = "twos_complement_sign_extension_only"
PAYLOAD_ALLOWED_CASES = {
    "$schema": {"$schema": DRAFT_2020_12_METASCHEMA_ID},
    "$defs": {"$defs": {"leaf": {"type": "null"}}},
    "$ref": {
        "$defs": {"leaf": {"type": "null"}},
        "$ref": "/$defs/leaf",
    },
    "$comment": {"$comment": "comment"},
    "title": {"title": "Title"},
    "description": {"description": "Description"},
    "default": {"default": {"annotation-key": [1, None]}},
    "examples": {"examples": [{"annotation-key": 1}]},
    "deprecated": {"deprecated": True},
    "readOnly": {"readOnly": True},
    "writeOnly": {"writeOnly": True},
    "type": {"type": ["null", "string"]},
    "enum": {"enum": [None, "value"]},
    "const": {"const": {"value": 1}},
    "properties": {"properties": {"name": {"type": "string"}}},
    "required": {"required": ["name"]},
    "additionalProperties": {"additionalProperties": False},
    "items": {"items": {"type": "string"}},
    "prefixItems": {"prefixItems": [{"type": "string"}]},
    "minItems": {"minItems": 0},
    "maxItems": {"maxItems": 1},
    "minProperties": {"minProperties": 0},
    "maxProperties": {"maxProperties": 1},
    "minLength": {"minLength": 0},
    "maxLength": {"maxLength": 1},
    "minimum": {"minimum": 0},
    "maximum": {"maximum": 1},
    "exclusiveMinimum": {"exclusiveMinimum": 0},
    "exclusiveMaximum": {"exclusiveMaximum": 1},
    "multipleOf": {"multipleOf": 1},
}
CORE_ONLY_ALLOWED_CASES = {
    "allOf": {"allOf": [{"type": "null"}]},
    "anyOf": {"anyOf": [{"type": "null"}]},
    "oneOf": {"oneOf": [{"type": "null"}]},
    "not": {"not": {"type": "string"}},
    "if": {"if": {"type": "string"}},
    "then": {"then": {"type": "string"}},
    "else": {"else": {"type": "string"}},
    "dependentRequired": {"dependentRequired": {"a": ["b"]}},
}
COMMON_FORBIDDEN_CASES = {
    "$id": {"$id": "urn:forbidden"},
    "$anchor": {"$anchor": "forbidden"},
    "$dynamicAnchor": {"$dynamicAnchor": "forbidden"},
    "$dynamicRef": {"$dynamicRef": "#forbidden"},
    "$recursiveRef": {"$recursiveRef": "#"},
    "pattern": {"pattern": "^x$"},
    "patternProperties": {"patternProperties": {"^x$": {}}},
    "propertyNames": {"propertyNames": {"type": "string"}},
    "format": {"format": "email"},
    "uniqueItems": {"uniqueItems": True},
    "contains": {"contains": {"type": "string"}},
    "dependentSchemas": {"dependentSchemas": {"a": {}}},
    "unevaluatedItems": {"unevaluatedItems": False},
    "unevaluatedProperties": {"unevaluatedProperties": False},
    "contentEncoding": {"contentEncoding": "base64"},
    "contentMediaType": {"contentMediaType": "application/json"},
    "contentSchema": {"contentSchema": {"type": "object"}},
}


def owned_schema(host: dict[str, object]) -> JsonObject:
    value = own_trusted_json(host)
    assert type(value) is JsonObject
    return value


def binding(pointer: str = "") -> InstanceBinding:
    return InstanceBinding(
        artifact_id="artifact:test-instance",
        artifact_fingerprint="sha256:" + "a" * 64,
        instance_pointer=pointer,
    )


def test_instance_binding_accepts_escaped_rfc6901_unicode_scalar_pointer() -> None:
    pointer = "/caf\u00e9/~0tilde~1slash/\U0001f642"

    result = binding(pointer)

    assert result.instance_pointer == pointer


@pytest.mark.parametrize("surrogate", ["\ud800", "\udfff"], ids=["high", "low"])
def test_instance_binding_rejects_lone_surrogate_pointer(surrogate: str) -> None:
    with pytest.raises(SchemaEvaluationInputError, match="invalid selected instance"):
        binding("/" + surrogate)


def test_instance_binding_pointer_utf8_byte_limit_is_inclusive() -> None:
    exact_pointer = "/" + "\u00e9" * 2_047 + "x"
    oversized_pointer = "/" + "\u00e9" * 2_048

    assert len(exact_pointer.encode("utf-8")) == EXPECTED_INSTANCE_POINTER_UTF8_BYTES
    assert len(oversized_pointer.encode("utf-8")) == (
        EXPECTED_INSTANCE_POINTER_UTF8_BYTES + 1
    )

    assert binding(exact_pointer).instance_pointer == exact_pointer
    with pytest.raises(SchemaEvaluationInputError, match="pointer byte limit"):
        binding(oversized_pointer)


def test_public_evaluation_rechecks_instance_pointer_utf8_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = admit({"type": "null"})
    instance = own_trusted_json(None)
    exact_pointer = "/" + "x" * (EXPECTED_INSTANCE_POINTER_UTF8_BYTES - 1)
    oversized = object.__new__(InstanceBinding)
    object.__setattr__(oversized, "artifact_id", binding().artifact_id)
    object.__setattr__(
        oversized,
        "artifact_fingerprint",
        binding().artifact_fingerprint,
    )
    object.__setattr__(
        oversized,
        "instance_pointer",
        "/" + "x" * EXPECTED_INSTANCE_POINTER_UTF8_BYTES,
    )
    evaluator_constructions: list[object] = []

    class PassingValidator:
        def iter_errors(self, _: object) -> tuple[()]:
            return ()

    def construct_evaluator(_: object) -> PassingValidator:
        evaluator_constructions.append(object())
        return PassingValidator()

    monkeypatch.setattr(
        schema_profile_module,
        "_validator_for",
        construct_evaluator,
    )

    accepted = evaluate_schema(
        schema,
        instance,
        instance_binding=binding(exact_pointer),
        ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
    )
    assert accepted.evaluation_passed is True

    with pytest.raises(SchemaEvaluationInputError, match="pointer byte limit"):
        evaluate_schema(
            schema,
            instance,
            instance_binding=oversized,
            ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
        )

    reservation = reserve_schema_evaluation(
        schema,
        instance_nodes=count_json_nodes(instance),
        ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
    )
    with pytest.raises(SchemaEvaluationInputError, match="pointer byte limit"):
        evaluate_schema_with_reservation(
            schema,
            instance,
            instance_binding=oversized,
            reservation=reservation,
        )

    assert len(evaluator_constructions) == 1


def test_instance_pointer_byte_work_is_bounded_and_charged_before_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = "x" * (EXPECTED_INSTANCE_POINTER_UTF8_BYTES - 1)
    pointer = "/" + key
    root = own_trusted_json({key: None})
    instance = lookup_json_pointer(root, pointer)
    events: list[tuple[str, object]] = []

    def charge(amount: int) -> None:
        events.append(("charge", amount))

    def tracked_lookup(value: object, selected_pointer: str) -> object:
        events.append(("lookup", selected_pointer))
        return lookup_json_pointer(value, selected_pointer)  # type: ignore[arg-type]

    monkeypatch.setattr(
        schema_profile_module,
        "lookup_json_pointer",
        tracked_lookup,
    )

    resolved = schema_profile_module._resolve_instance_binding(
        instance_root=root,
        instance_root_fingerprint=binding().artifact_fingerprint,
        instance=instance,
        instance_binding=binding(pointer),
        charge_work_units=charge,
        precomputed_instance_fingerprint=canonical_fingerprint(instance),
    )

    assert resolved.instance is instance
    assert events == [
        ("charge", EXPECTED_INSTANCE_POINTER_UTF8_BYTES),
        ("charge", 2),
        ("lookup", pointer),
    ]

    events.clear()
    oversized_pointer = "/" + "x" * EXPECTED_INSTANCE_POINTER_UTF8_BYTES
    oversized_binding = object.__new__(InstanceBinding)
    object.__setattr__(
        oversized_binding,
        "artifact_id",
        binding().artifact_id,
    )
    object.__setattr__(
        oversized_binding,
        "artifact_fingerprint",
        binding().artifact_fingerprint,
    )
    object.__setattr__(
        oversized_binding,
        "instance_pointer",
        oversized_pointer,
    )
    with pytest.raises(SchemaEvaluationInputError, match="pointer byte limit"):
        schema_profile_module._resolve_instance_binding(
            instance_root=instance,
            instance_root_fingerprint=binding().artifact_fingerprint,
            instance=instance,
            instance_binding=oversized_binding,
            charge_work_units=charge,
            precomputed_instance_fingerprint=canonical_fingerprint(instance),
        )
    assert events == [
        ("charge", EXPECTED_INSTANCE_POINTER_UTF8_BYTES + 1),
    ]
    for profile in (PAYLOAD_PROFILE, CORE_PROFILE):
        identity = canonical_json_bytes(profile.identity)
        assert b'"instance_pointer_utf8_bytes":4096' in identity


def schema_issue_evidence_bytes(issue: SchemaIssue) -> int:
    fields = (
        issue.code,
        issue.instance_path,
        issue.schema_path,
        issue.detail_sha256 or "",
    )
    return sum(len(field.encode("utf-8")) for field in fields)


def evaluator_failure_receipt(
    monkeypatch: pytest.MonkeyPatch, exception: Exception
) -> SchemaEvaluationReceipt:
    class BrokenValidator:
        def iter_errors(self, _: object) -> tuple[()]:
            raise exception

    monkeypatch.setattr(
        schema_profile_module,
        "_validator_for",
        lambda _: BrokenValidator(),
    )
    return evaluate_schema(
        admit({"type": "null"}),
        own_trusted_json(None),
        instance_binding=binding(),
        ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
    )


def admit(host: dict[str, object], profile: SchemaProfile = PAYLOAD_PROFILE) -> AdmittedSchema:
    return admit_schema("schema.test", owned_schema(host), profile)


def nested_alternative_schema(
    keyword: str, depth: int, alternatives: int
) -> dict[str, object]:
    if depth == 0:
        return {"type": "number"}
    return {
        keyword: [
            nested_alternative_schema(keyword, depth - 1, alternatives)
            for _ in range(alternatives)
        ]
    }


def validation_error_tree(errors: object) -> tuple[object, ...]:
    flattened: list[object] = []
    pending = list(errors)
    while pending:
        error = pending.pop()
        flattened.append(error)
        pending.extend(error.context)
    return tuple(flattened)


@pytest.mark.parametrize(
    ("keyword", "schema_host"),
    PAYLOAD_ALLOWED_CASES.items(),
    ids=PAYLOAD_ALLOWED_CASES,
)
def test_payload_profile_admits_every_exact_allowed_keyword(
    keyword: str, schema_host: dict[str, object]
) -> None:
    admitted = admit(schema_host)

    assert keyword in PAYLOAD_PROFILE.allowed_keywords
    assert admitted.profile_id == PAYLOAD_SCHEMA_PROFILE_ID


@pytest.mark.parametrize(
    ("keyword", "schema_host"),
    CORE_ONLY_ALLOWED_CASES.items(),
    ids=CORE_ONLY_ALLOWED_CASES,
)
def test_core_profile_admits_every_exact_additional_keyword(
    keyword: str, schema_host: dict[str, object]
) -> None:
    admitted = admit(schema_host, CORE_PROFILE)

    assert keyword in CORE_PROFILE.allowed_keywords
    assert keyword not in PAYLOAD_PROFILE.allowed_keywords
    assert admitted.profile_id == CORE_SCHEMA_PROFILE_ID


@pytest.mark.parametrize(
    ("keyword", "schema_host"),
    {**COMMON_FORBIDDEN_CASES, **CORE_ONLY_ALLOWED_CASES}.items(),
    ids={**COMMON_FORBIDDEN_CASES, **CORE_ONLY_ALLOWED_CASES},
)
def test_payload_profile_rejects_every_exact_forbidden_keyword(
    keyword: str, schema_host: dict[str, object]
) -> None:
    with pytest.raises(SchemaAdmissionError) as raised:
        admit(schema_host)

    assert keyword not in PAYLOAD_PROFILE.allowed_keywords
    assert raised.value.code == "schema_keyword_forbidden"


@pytest.mark.parametrize(
    ("keyword", "schema_host"),
    COMMON_FORBIDDEN_CASES.items(),
    ids=COMMON_FORBIDDEN_CASES,
)
def test_core_profile_rejects_every_exact_forbidden_keyword(
    keyword: str, schema_host: dict[str, object]
) -> None:
    with pytest.raises(SchemaAdmissionError) as raised:
        admit(schema_host, CORE_PROFILE)

    assert keyword not in CORE_PROFILE.allowed_keywords
    assert raised.value.code == "schema_keyword_forbidden"


def test_unknown_keyword_is_rejected_before_library_schema_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def library_must_not_run(_: object) -> None:
        raise AssertionError("library construction ran before static admission")

    monkeypatch.setattr(
        schema_profile_module,
        "_check_schema_with_library",
        library_must_not_run,
    )

    with pytest.raises(SchemaAdmissionError) as raised:
        admit({"x-unknown": True})

    assert raised.value.code == "schema_keyword_unknown"


def test_annotation_objects_are_counted_but_not_treated_as_schema_objects() -> None:
    schema = owned_schema(
        {
            "$defs": {"unused": {"type": "string"}},
            "default": {"unknown-annotation-key": [1, None]},
            "examples": [{"another-annotation-key": False}],
        }
    )

    admitted = admit_schema("schema.annotations", schema, PAYLOAD_PROFILE)

    assert admitted.schema_nodes == count_json_nodes(schema)
    assert admitted.schema_nodes == 11
    assert admitted.local_reference_count == 0


def test_library_metaschema_rejection_is_closed_after_static_admission() -> None:
    with pytest.raises(SchemaAdmissionError) as raised:
        admit({"minItems": -1})

    assert raised.value.code == "schema_invalid"
    assert "-1" not in str(raised.value)


@pytest.mark.parametrize("profile", [PAYLOAD_PROFILE, CORE_PROFILE])
def test_exact_bound_draft_2020_12_schema_uri_is_admitted(
    profile: SchemaProfile,
) -> None:
    admitted = admit({"$schema": DRAFT_2020_12_METASCHEMA_ID}, profile)

    assert admitted.profile_id == profile.profile_id


@pytest.mark.parametrize("profile", [PAYLOAD_PROFILE, CORE_PROFILE])
@pytest.mark.parametrize(
    "wrong_dialect",
    [
        "https://json-schema.org/draft/2019-09/schema",
        "urn:example:unrelated-dialect",
        "",
        None,
        20_201_212,
        True,
        [],
        {"uri": DRAFT_2020_12_METASCHEMA_ID},
    ],
    ids=[
        "draft-2019-09",
        "unrelated-urn",
        "empty",
        "null",
        "number",
        "boolean",
        "array",
        "object",
    ],
)
def test_wrong_schema_dialect_is_rejected_during_static_admission(
    monkeypatch: pytest.MonkeyPatch,
    profile: SchemaProfile,
    wrong_dialect: object,
) -> None:
    def library_must_not_run(_: object) -> None:
        raise AssertionError("wrong schema dialect reached library construction")

    monkeypatch.setattr(
        schema_profile_module,
        "_check_schema_with_library",
        library_must_not_run,
    )

    with pytest.raises(SchemaAdmissionError) as raised:
        admit({"$schema": wrong_dialect}, profile)

    assert raised.value.code == "schema_dialect_invalid"


@pytest.mark.parametrize("profile", [PAYLOAD_PROFILE, CORE_PROFILE])
@pytest.mark.parametrize(
    "reference",
    [
        "#",
        "#/\u0024defs/leaf",
        "other.json#/leaf",
        "https://example.test/schema",
        "urn:example:schema",
        "relative/schema",
        "/bad~",
        "/bad~2escape",
    ],
)
def test_refs_reject_uri_fragments_remote_uris_and_invalid_rfc6901(
    profile: SchemaProfile, reference: str
) -> None:
    with pytest.raises(SchemaAdmissionError) as raised:
        admit({"$defs": {"leaf": {"type": "null"}}, "$ref": reference}, profile)

    assert raised.value.code == "local_reference_invalid"


@pytest.mark.parametrize("reference", ["/missing", "/default/not-a-schema"])
def test_refs_must_resolve_to_a_schema_node(reference: str) -> None:
    with pytest.raises(SchemaAdmissionError) as raised:
        admit({"default": {"not-a-schema": 1}, "$ref": reference})

    assert raised.value.code == "local_reference_target_invalid"


@pytest.mark.parametrize(
    "schema_host",
    [
        {"$ref": ""},
        {
            "$defs": {
                "a": {"$ref": "/$defs/b"},
                "b": {"$ref": "/$defs/a"},
            }
        },
    ],
)
def test_local_reference_graph_cycles_are_rejected(schema_host: dict[str, object]) -> None:
    with pytest.raises(SchemaAdmissionError) as raised:
        admit(schema_host)

    assert raised.value.code == "local_reference_cycle"


@pytest.mark.parametrize(
    ("profile", "schema_host"),
    [
        (PAYLOAD_PROFILE, {"properties": {"child": {"$ref": ""}}}),
        (
            CORE_PROFILE,
            {
                "allOf": [
                    {"properties": {"child": {"$ref": ""}}},
                ]
            },
        ),
    ],
    ids=["properties", "allOf-properties"],
)
def test_structural_reference_reachability_rejects_ancestor_recursion_before_library(
    monkeypatch: pytest.MonkeyPatch,
    profile: SchemaProfile,
    schema_host: dict[str, object],
) -> None:
    def library_must_not_run(_: object) -> None:
        raise AssertionError("recursive schema reached library construction")

    monkeypatch.setattr(
        schema_profile_module,
        "_check_schema_with_library",
        library_must_not_run,
    )

    with pytest.raises(SchemaAdmissionError) as raised:
        admit(schema_host, profile)

    assert raised.value.code == "local_reference_cycle"


def reference_count_schema(reference_count: int) -> dict[str, object]:
    definitions: dict[str, object] = {"target": {"type": "null"}}
    for index in range(reference_count):
        definitions[f"source-{index}"] = {"$ref": "/$defs/target"}
    return {"$defs": definitions}


@pytest.mark.parametrize(
    ("profile", "limit"),
    [(PAYLOAD_PROFILE, 256), (CORE_PROFILE, 1_024)],
    ids=["payload", "core"],
)
def test_reference_count_limit_is_inclusive_and_rejects_limit_plus_one(
    profile: SchemaProfile, limit: int
) -> None:
    admitted = admit(reference_count_schema(limit), profile)

    assert admitted.local_reference_count == limit
    with pytest.raises(SchemaAdmissionError) as raised:
        admit(reference_count_schema(limit + 1), profile)
    assert raised.value.code == "local_reference_limit_exceeded"


def reference_chain_schema(depth: int) -> dict[str, object]:
    definitions: dict[str, object] = {"terminal": {"type": "null"}}
    for index in reversed(range(depth)):
        target = "terminal" if index == depth - 1 else f"node-{index + 1}"
        definitions[f"node-{index}"] = {"$ref": f"/$defs/{target}"}
    return {"$defs": definitions}


def structurally_nested_reference_chain(depth: int) -> dict[str, object]:
    definitions: dict[str, object] = {"terminal": {"type": "null"}}
    for index in reversed(range(depth)):
        target = "terminal" if index == depth - 1 else f"node-{index + 1}"
        definitions[f"node-{index}"] = {
            "properties": {
                "next": {"$ref": f"/$defs/{target}"},
            }
        }
    return {"$defs": definitions}


def test_structural_reference_chain_reports_honest_depth_and_rejects_17_before_library(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admitted = admit(structurally_nested_reference_chain(16))

    assert admitted.local_reference_count == 16
    assert admitted.maximum_reference_depth == 16

    def library_must_not_run(_: object) -> None:
        raise AssertionError("over-depth schema reached library construction")

    monkeypatch.setattr(
        schema_profile_module,
        "_check_schema_with_library",
        library_must_not_run,
    )
    with pytest.raises(SchemaAdmissionError) as raised:
        admit(structurally_nested_reference_chain(17))
    assert raised.value.code == "local_reference_depth_exceeded"


@pytest.mark.parametrize(
    ("profile", "limit"),
    [(PAYLOAD_PROFILE, 16), (CORE_PROFILE, 32)],
    ids=["payload", "core"],
)
def test_reference_depth_limit_is_inclusive_and_rejects_limit_plus_one(
    profile: SchemaProfile, limit: int
) -> None:
    admitted = admit(reference_chain_schema(limit), profile)

    assert admitted.maximum_reference_depth == limit
    with pytest.raises(SchemaAdmissionError) as raised:
        admit(reference_chain_schema(limit + 1), profile)
    assert raised.value.code == "local_reference_depth_exceeded"


@pytest.mark.parametrize(
    ("profile", "limit"),
    [(PAYLOAD_PROFILE, 4_096), (CORE_PROFILE, 32_768)],
    ids=["payload", "core"],
)
def test_schema_node_limit_counts_unreachable_annotations_at_exact_boundary(
    profile: SchemaProfile, limit: int
) -> None:
    at_limit = owned_schema({"default": [None] * (limit - 2)})
    over_limit = owned_schema({"default": [None] * (limit - 1)})

    admitted = admit_schema("schema.node-limit", at_limit, profile)

    assert admitted.schema_nodes == limit
    with pytest.raises(SchemaAdmissionError) as raised:
        admit_schema("schema.node-over-limit", over_limit, profile)
    assert raised.value.code == "schema_node_limit_exceeded"


@pytest.mark.parametrize("keyword", ["allOf", "anyOf", "oneOf"])
def test_core_combinator_alternative_limit_is_16_inclusive(keyword: str) -> None:
    admitted = admit({keyword: [{} for _ in range(16)]}, CORE_PROFILE)

    assert admitted.profile_id == CORE_SCHEMA_PROFILE_ID
    with pytest.raises(SchemaAdmissionError) as raised:
        admit({keyword: [{} for _ in range(17)]}, CORE_PROFILE)
    assert raised.value.code == "combinator_alternative_limit_exceeded"


def nested_not_schema(depth: int) -> dict[str, object]:
    schema: dict[str, object] = {"type": "null"}
    for _ in range(depth):
        schema = {"not": schema}
    return schema


def test_core_combinator_nesting_limit_is_8_inclusive() -> None:
    assert admit(nested_not_schema(8), CORE_PROFILE).profile_id == CORE_SCHEMA_PROFILE_ID
    with pytest.raises(SchemaAdmissionError) as raised:
        admit(nested_not_schema(9), CORE_PROFILE)
    assert raised.value.code == "combinator_depth_limit_exceeded"


def exponentially_branching_reference_schema(depth: int) -> dict[str, object]:
    definitions: dict[str, object] = {"leaf": {"type": "null"}}
    for index in range(depth):
        target = "leaf" if index == 0 else f"level-{index - 1}"
        definitions[f"level-{index}"] = {
            "allOf": [
                {"$ref": f"/$defs/{target}"},
                {"$ref": f"/$defs/{target}"},
            ]
        }
    return {
        "$defs": definitions,
        "$ref": f"/$defs/level-{depth - 1}",
    }


def test_core_expansion_limit_accepts_boundary_and_rejects_exponential_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    library_checks: list[JsonObject] = []
    real_library_check = schema_profile_module._check_schema_with_library

    def tracked_library_check(value: JsonObject) -> None:
        library_checks.append(value)
        real_library_check(value)

    monkeypatch.setattr(
        schema_profile_module,
        "_check_schema_with_library",
        tracked_library_check,
    )

    boundary = admit(exponentially_branching_reference_schema(16), CORE_PROFILE)

    assert CORE_PROFILE.evaluation_expansion_limit == 65_536
    assert boundary.evaluation_expansion_units == 65_536
    assert b'"evaluation_expansion_units":65536' in canonical_json_bytes(
        CORE_PROFILE.identity
    )
    with pytest.raises(SchemaAdmissionError) as raised:
        admit(exponentially_branching_reference_schema(17), CORE_PROFILE)
    assert raised.value.code == "schema_expansion_limit_exceeded"
    assert len(library_checks) == 1


def test_only_release_owned_exact_profiles_are_admissible() -> None:
    forged = replace(PAYLOAD_PROFILE)
    assert forged == PAYLOAD_PROFILE
    assert forged is not PAYLOAD_PROFILE

    with pytest.raises(SchemaAdmissionError) as raised:
        admit_schema("schema.forged-profile", owned_schema({}), forged)

    assert raised.value.code == "schema_profile_not_sealed"


def test_schema_admission_is_immutable_and_retains_the_exact_owned_value() -> None:
    schema = owned_schema({"type": "object"})

    admitted = admit_schema("schema.identity", schema, PAYLOAD_PROFILE)

    with pytest.raises(TypeError):
        AdmittedSchema()
    assert type(admitted) is AdmittedSchema
    assert admitted.value is schema
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", admitted.schema_fingerprint)
    with pytest.raises((AttributeError, TypeError)):
        admitted.schema_nodes = 0


def test_admitted_schema_private_factory_requires_issuer_capability() -> None:
    schema = owned_schema({"type": "object"})

    with pytest.raises(TypeError, match="issuer"):
        AdmittedSchema._create(
            schema_id="schema.forged",
            schema_fingerprint=canonical_fingerprint(schema),
            profile_id=PAYLOAD_PROFILE.profile_id,
            schema_nodes=count_json_nodes(schema),
            local_reference_count=0,
            maximum_reference_depth=0,
            evaluation_expansion_units=1,
            value=schema,
        )


def test_slot_copied_admitted_schema_is_rejected() -> None:
    admitted = admit({"type": "null"})
    copied = object.__new__(AdmittedSchema)
    for slot in AdmittedSchema.__slots__:
        attribute = (
            f"_AdmittedSchema{slot}" if slot.startswith("__") else slot
        )
        object.__setattr__(
            copied,
            attribute,
            object.__getattribute__(admitted, attribute),
        )

    with pytest.raises(SchemaEvaluationInputError, match="admitted schema"):
        evaluate_schema(
            copied,
            own_trusted_json(None),
            instance_binding=binding(),
            ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
        )


def test_schema_fingerprint_accepts_finite_integer_outside_product_safe_range() -> None:
    schema = owned_schema({"type": "integer", "maximum": 9_007_199_254_740_992})

    admitted = admit_schema("schema.large", schema, CORE_PROFILE)

    assert admitted.schema_fingerprint.startswith("sha256:")
    assert b"9007199254740992" in canonical_json_bytes(admitted.value)


def test_profile_identity_binds_exact_dependencies_and_draft_metaschema() -> None:
    expected_dependencies = (
        ("jsonschema", "4.26.0"),
        ("referencing", "0.37.0"),
        ("jsonschema-specifications", "2025.9.1"),
    )
    metaschema = own_trusted_json(Draft202012Validator.META_SCHEMA)
    expected_metaschema_fingerprint = canonical_fingerprint(metaschema)

    for profile in (PAYLOAD_PROFILE, CORE_PROFILE):
        identity_bytes = canonical_json_bytes(profile.identity)
        assert profile.runtime_dependencies == expected_dependencies
        for distribution, version in expected_dependencies:
            assert importlib.metadata.version(distribution) == version
            assert distribution.encode("ascii") in identity_bytes
            assert version.encode("ascii") in identity_bytes
        assert profile.metaschema_id == DRAFT_2020_12_METASCHEMA_ID
        assert profile.metaschema_fingerprint == expected_metaschema_fingerprint
        assert profile.metaschema_fingerprint.encode("ascii") in identity_bytes
        assert b'"bounded_evaluator_value_repr_utf8_bytes"' not in identity_bytes
        assert (
            b'"bounded_wrapped_value_repr_kinds":["array","object","string"]'
            in identity_bytes
        )
        assert b'"bounded_wrapped_value_repr_utf8_bytes":8' in identity_bytes
        assert b'"exception_projection_bytes":4096' in identity_bytes
        assert b'"exception_projection_items":128' in identity_bytes
        assert b'"exception_projection_depth":16' in identity_bytes
        assert b'"exception_integer_sample_bits":256' in identity_bytes
        assert (
            b'"exception_negative_integer_sample_policy":'
            b'"twos_complement_sign_extension_only"' in identity_bytes
        )
        assert canonical_fingerprint(profile.identity) == profile.profile_fingerprint


def test_profile_repr_bound_matches_only_wrapped_runtime_kinds() -> None:
    wrapped_values = {
        "array": schema_profile_module._adapt_owned(
            own_trusted_json([]), translate_refs=False
        ),
        "object": schema_profile_module._adapt_owned(
            own_trusted_json({}), translate_refs=False
        ),
        "string": schema_profile_module._adapt_owned(
            own_trusted_json("full semantics remain available"),
            translate_refs=False,
        ),
    }
    native_float = schema_profile_module._adapt_owned(
        own_trusted_json(-1.7976931348623157e308), translate_refs=False
    )

    assert tuple(wrapped_values) == ("array", "object", "string")
    assert max(
        len(repr(value).encode("utf-8")) for value in wrapped_values.values()
    ) == EXPECTED_WRAPPED_VALUE_REPR_BYTES
    assert type(native_float) is float
    assert len(repr(native_float).encode("utf-8")) == 24
    assert schema_profile_module._MAX_WRAPPED_VALUE_REPR_BYTES == (
        EXPECTED_WRAPPED_VALUE_REPR_BYTES
    )


@pytest.mark.parametrize(
    ("schema_host", "accepted", "rejected"),
    [
        ({"type": "null"}, None, False),
        ({"type": "boolean"}, True, 1),
        ({"type": "string"}, "value", 1),
        ({"type": "number"}, 1.5, True),
        ({"type": "integer"}, 1.0, 1.5),
        ({"type": "array"}, [1], {"0": 1}),
        ({"type": "object"}, {"value": 1}, [1]),
    ],
    ids=["null", "boolean", "string", "number", "integer", "array", "object"],
)
def test_evaluator_uses_exact_owned_value_type_checking(
    schema_host: dict[str, object], accepted: object, rejected: object
) -> None:
    schema = admit(schema_host)

    accepted_receipt = evaluate_schema(
        schema,
        own_trusted_json(accepted),
        instance_binding=binding(),
        ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
    )
    rejected_receipt = evaluate_schema(
        schema,
        own_trusted_json(rejected),
        instance_binding=binding(),
        ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
    )

    assert accepted_receipt.evaluation_passed is True
    assert accepted_receipt.failure_code is None
    assert rejected_receipt.evaluation_passed is False
    assert rejected_receipt.failure_code == "instance_schema_failed"


def assert_nested_alternative_error_evidence_is_bounded(
    *, keyword: str, depth: int, alternatives: int, text: str, expected_errors: int
) -> None:
    schema = admit(
        nested_alternative_schema(keyword, depth, alternatives), CORE_PROFILE
    )
    instance_view = schema_profile_module._adapt_owned(
        own_trusted_json(text), translate_refs=False
    )

    assert isinstance(instance_view, str)
    assert schema_profile_module._MAX_WRAPPED_VALUE_REPR_BYTES == (
        EXPECTED_WRAPPED_VALUE_REPR_BYTES
    )
    assert len(instance_view) == len(text)
    assert instance_view.startswith(text[:16])
    assert instance_view.endswith(text[-16:])
    assert re.fullmatch(r"[A-Z-]+z+", instance_view)
    assert schema_profile_module._OWNED_TYPE_CHECKER.is_type(instance_view, "string")

    roots = tuple(schema_profile_module._validator_for(schema).iter_errors(instance_view))
    errors = validation_error_tree(roots)
    representations = tuple(repr(error.instance) for error in errors)
    messages = tuple(error.message for error in errors)

    assert len(roots) == 1
    assert len(errors) == expected_errors
    assert max(len(value.encode("utf-8")) for value in representations) <= (
        EXPECTED_WRAPPED_VALUE_REPR_BYTES
    )
    assert sum(len(value.encode("utf-8")) for value in representations) <= (
        EXPECTED_SCHEMA_ISSUE_EVIDENCE_BYTES
    )
    assert max(len(message.encode("utf-8")) for message in messages) <= 128
    assert text[:16] not in "".join(messages)


@pytest.mark.parametrize("keyword", ["anyOf", "oneOf"])
def test_nested_alternative_internal_errors_use_constant_bounded_instance_repr(
    keyword: str,
) -> None:
    assert_nested_alternative_error_evidence_is_bounded(
        keyword=keyword,
        depth=2,
        alternatives=4,
        text="INTERNAL-SECRET-" + "z" * 32_768,
        expected_errors=21,
    )


def test_reviewer_scale_nested_any_of_error_tree_cannot_amplify_instance_text() -> None:
    schema = nested_alternative_schema("anyOf", depth=3, alternatives=16)
    assert count_json_nodes(owned_schema(schema)) == 8_738

    assert_nested_alternative_error_evidence_is_bounded(
        keyword="anyOf",
        depth=3,
        alternatives=16,
        text="REVIEWER-PROBE-SECRET-" + "z" * 1_000_000,
        expected_errors=4_369,
    )


def test_internal_additional_properties_error_bounds_long_owned_key_repr() -> None:
    secret = "LONG-KEY-SECRET-" + "k" * 32_768
    schema = admit({"additionalProperties": False})
    instance_view = schema_profile_module._adapt_owned(
        own_trusted_json({secret: None}), translate_refs=False
    )

    errors = tuple(schema_profile_module._validator_for(schema).iter_errors(instance_view))

    assert len(errors) == 1
    assert secret not in errors[0].message
    assert len(errors[0].message.encode("utf-8")) <= 128
    assert len(repr(errors[0].instance).encode("utf-8")) <= (
        EXPECTED_WRAPPED_VALUE_REPR_BYTES
    )


def test_local_pointer_ref_evaluates_without_retrieval() -> None:
    schema = admit(
        {
            "$defs": {"text": {"type": "string", "minLength": 2}},
            "$ref": "/$defs/text",
        }
    )

    passed = evaluate_schema(
        schema,
        own_trusted_json("ok"),
        instance_binding=binding(),
        ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
    )
    failed = evaluate_schema(
        schema,
        own_trusted_json("x"),
        instance_binding=binding(),
        ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
    )

    assert passed.evaluation_passed is True
    assert failed.evaluation_passed is False


def test_local_pointer_ref_preserves_uri_sensitive_rfc6901_token_data() -> None:
    token = "a b%2F#?"
    schema = admit(
        {
            "$defs": {token: {"const": "matched"}},
            "$ref": f"/$defs/{token}",
        }
    )

    receipt = evaluate_schema(
        schema,
        own_trusted_json("matched"),
        instance_binding=binding(),
        ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
    )

    assert receipt.evaluation_passed is True
    assert receipt.failure_code is None


def test_instance_adapter_exposes_read_only_views_without_mutable_container_copies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = own_trusted_json({"array": [{"value": 1}], "flag": True})
    schema = admit({"type": "object"})

    class CapturingValidator:
        def iter_errors(self, adapted_instance: object) -> tuple[()]:
            pending = [adapted_instance]
            while pending:
                current = pending.pop()
                assert not isinstance(current, (dict, list, set, bytearray))
                if isinstance(current, Mapping):
                    pending.extend(current.values())
                elif isinstance(current, Sequence) and not isinstance(current, str):
                    pending.extend(current)
            return ()

    monkeypatch.setattr(
        schema_profile_module,
        "_validator_for",
        lambda _: CapturingValidator(),
    )

    receipt = evaluate_schema(
        schema,
        instance,
        instance_binding=binding(),
        ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
    )

    assert receipt.evaluation_passed is True


def test_selected_instance_root_alone_determines_reserved_instance_nodes() -> None:
    artifact_root = own_trusted_json(
        {"selected": {"value": 1}, "unselected": [None] * 100}
    )
    selected = lookup_json_pointer(artifact_root, "/selected")
    schema = admit({"type": "object"})
    ledger = BudgetLedger(LM9A_BUDGET_MANIFEST)

    receipt = evaluate_schema(
        schema,
        selected,
        instance_binding=binding("/selected"),
        ledger=ledger,
    )

    expected = schema.schema_nodes * count_json_nodes(selected)
    whole_artifact_product = schema.schema_nodes * count_json_nodes(artifact_root)
    assert receipt.reservation.attempted_shape_units == expected
    assert expected < whole_artifact_product
    assert ledger.snapshot().schema_evaluation_shape_units == expected


def test_direct_evaluation_counts_instance_once_without_rehashing_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = admit({"type": "object", "required": ["value"]})
    instance = own_trusted_json({"value": 1})
    real_count_json_nodes = schema_profile_module.count_json_nodes
    real_canonical_fingerprint = schema_profile_module.canonical_fingerprint
    counted_values: list[object] = []
    hashed_values: list[object] = []

    def tracked_count_json_nodes(value: object) -> int:
        counted_values.append(value)
        return real_count_json_nodes(value)  # type: ignore[arg-type]

    def tracked_canonical_fingerprint(value: object) -> str:
        hashed_values.append(value)
        return real_canonical_fingerprint(value)  # type: ignore[arg-type]

    monkeypatch.setattr(
        schema_profile_module,
        "count_json_nodes",
        tracked_count_json_nodes,
    )
    monkeypatch.setattr(
        schema_profile_module,
        "canonical_fingerprint",
        tracked_canonical_fingerprint,
    )

    receipt = evaluate_schema(
        schema,
        instance,
        instance_binding=binding(),
        ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
    )

    assert receipt.evaluation_passed is True
    assert counted_values == [instance]
    assert hashed_values == []


def test_reserved_evaluation_runs_after_freeze_without_mutating_frozen_ledger() -> None:
    schema = admit({"type": "object", "required": ["value"]})
    instance = own_trusted_json({"value": 1})
    ledger = BudgetLedger(LM9A_BUDGET_MANIFEST)
    reservation = reserve_schema_evaluation(
        schema,
        instance_nodes=count_json_nodes(instance),
        ledger=ledger,
    )
    frozen_receipt = ledger.reserve_report_seal_and_freeze()

    result = evaluate_schema_with_reservation(
        schema,
        instance,
        instance_binding=binding(),
        reservation=reservation,
    )

    assert type(reservation) is SchemaEvaluationReservation
    assert reservation.per_evaluation_limit == PAYLOAD_PROFILE.per_evaluation_shape_limit
    with pytest.raises(AttributeError):
        reservation._instance_nodes = 99  # type: ignore[attr-defined]
    assert result.reservation is reservation.shape_reservation
    assert result.evaluator_invoked is True
    assert result.evaluation_passed is True
    assert ledger.snapshot() == frozen_receipt.observed


@pytest.mark.parametrize(
    ("schema_host", "instance_host", "profile"),
    (
        ({"const": "expected"}, "actual", PAYLOAD_PROFILE),
        ({"enum": ["expected", "other"]}, "actual", PAYLOAD_PROFILE),
        (
            {"type": "object", "minProperties": 2},
            {"only": 1},
            PAYLOAD_PROFILE,
        ),
        (
            {"type": "object", "maxProperties": 1},
            {"first": 1, "second": 2},
            PAYLOAD_PROFILE,
        ),
        ({"type": "number", "exclusiveMinimum": 1}, 1, PAYLOAD_PROFILE),
        ({"type": "number", "exclusiveMaximum": 1}, 1, PAYLOAD_PROFILE),
        ({"type": "number", "multipleOf": 2}, 3, PAYLOAD_PROFILE),
        (
            {"allOf": [{"type": "string"}, {"const": "expected"}]},
            "actual",
            CORE_PROFILE,
        ),
        (
            {"anyOf": [{"const": "expected"}, {"const": "other"}]},
            "actual",
            CORE_PROFILE,
        ),
        (
            {"oneOf": [{"type": "number"}, {"type": "integer"}]},
            1,
            CORE_PROFILE,
        ),
    ),
    ids=(
        "const",
        "enum",
        "minProperties",
        "maxProperties",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "allOf",
        "anyOf",
        "oneOf",
    ),
)
def test_reserved_evaluator_is_differentially_exact_for_reviewer_schema_probes(
    schema_host: dict[str, object],
    instance_host: object,
    profile: SchemaProfile,
) -> None:
    schema = admit(schema_host, profile)
    instance = own_trusted_json(instance_host)
    direct = evaluate_schema(
        schema,
        instance,
        instance_binding=binding(),
        ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
    )
    reserved_ledger = BudgetLedger(LM9A_BUDGET_MANIFEST)
    reservation = reserve_schema_evaluation(
        schema,
        instance_nodes=count_json_nodes(instance),
        ledger=reserved_ledger,
    )
    reserved_ledger.reserve_report_seal_and_freeze()

    delayed = evaluate_schema_with_reservation(
        schema,
        instance,
        instance_binding=binding(),
        reservation=reservation,
    )

    assert delayed == direct
    assert delayed.evaluation_passed is False
    assert delayed.failure_code == "instance_schema_failed"


def test_reserved_evaluation_rejects_wrong_schema_and_consumes_capability() -> None:
    schema = admit({"type": "null"})
    equivalent = admit({"type": "null"})
    instance = own_trusted_json(None)
    reservation = reserve_schema_evaluation(
        schema,
        instance_nodes=count_json_nodes(instance),
        ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
    )

    with pytest.raises(SchemaEvaluationInputError, match="schema identity"):
        evaluate_schema_with_reservation(
            equivalent,
            instance,
            instance_binding=binding(),
            reservation=reservation,
        )
    with pytest.raises(SchemaEvaluationInputError, match="already consumed"):
        evaluate_schema_with_reservation(
            schema,
            instance,
            instance_binding=binding(),
            reservation=reservation,
        )


def test_reserved_evaluation_rejects_wrong_instance_shape_and_reuse() -> None:
    schema = admit({"type": "array"})
    reservation = reserve_schema_evaluation(
        schema,
        instance_nodes=1,
        ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
    )

    with pytest.raises(SchemaEvaluationInputError, match="instance node count"):
        evaluate_schema_with_reservation(
            schema,
            own_trusted_json([None]),
            instance_binding=binding(),
            reservation=reservation,
        )
    with pytest.raises(SchemaEvaluationInputError, match="already consumed"):
        evaluate_schema_with_reservation(
            schema,
            own_trusted_json(None),
            instance_binding=binding(),
            reservation=reservation,
        )


def test_reserved_evaluation_requires_exact_kernel_reservation() -> None:
    schema = admit({"type": "null"})
    instance = own_trusted_json(None)

    with pytest.raises(SchemaEvaluationInputError, match="evaluation reservation"):
        evaluate_schema_with_reservation(
            schema,
            instance,
            instance_binding=binding(),
            reservation=object(),  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError):
        SchemaEvaluationReservation()


def test_copied_or_reconstructed_reservation_is_rejected_before_evaluator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = admit({"type": "null"})
    instance = own_trusted_json(None)
    issued = reserve_schema_evaluation(
        schema,
        instance_nodes=count_json_nodes(instance),
        ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
    )
    issued_shape = issued.shape_reservation
    reconstructed_shape = SchemaShapeReservation(
        accepted=issued_shape.accepted,
        attempted_shape_units=issued_shape.attempted_shape_units,
        aggregate_before=issued_shape.aggregate_before,
        aggregate_after=issued_shape.aggregate_after,
        rejection_reason=issued_shape.rejection_reason,
    )

    def copied_reservation(
        shape: SchemaShapeReservation,
    ) -> SchemaEvaluationReservation:
        copied = object.__new__(SchemaEvaluationReservation)
        for slot in SchemaEvaluationReservation.__slots__:
            attribute = (
                f"_SchemaEvaluationReservation{slot}"
                if slot.startswith("__")
                else slot
            )
            if slot == "_shape_reservation":
                slot_value = shape
            elif slot == "_consumed":
                slot_value = False
            elif slot == "_lock":
                slot_value = threading.Lock()
            else:
                slot_value = object.__getattribute__(issued, attribute)
            object.__setattr__(copied, attribute, slot_value)
        return copied

    evaluator_constructions: list[object] = []

    class PassingValidator:
        def iter_errors(self, _: object) -> tuple[()]:
            return ()

    def construct_evaluator(_: object) -> PassingValidator:
        evaluator_constructions.append(object())
        return PassingValidator()

    monkeypatch.setattr(
        schema_profile_module,
        "_validator_for",
        construct_evaluator,
    )

    for forged in (
        copied_reservation(issued_shape),
        copied_reservation(reconstructed_shape),
    ):
        with pytest.raises(SchemaEvaluationInputError, match="reservation"):
            evaluate_schema_with_reservation(
                schema,
                instance,
                instance_binding=binding(),
                reservation=forged,
            )

    assert evaluator_constructions == []


def test_shape_reservation_authority_stays_out_of_public_dataclass_fields() -> None:
    shape = BudgetLedger(LM9A_BUDGET_MANIFEST).reserve_schema_shape(
        schema_nodes=2,
        instance_nodes=3,
        per_evaluation_limit=6,
    )

    assert asdict(shape) == {
        "accepted": True,
        "attempted_shape_units": 6,
        "aggregate_before": 0,
        "aggregate_after": 6,
        "rejection_reason": None,
    }


def test_repeated_evaluation_charges_again_even_for_identical_cached_ref_shape() -> None:
    schema = admit(
        {"$defs": {"leaf": {"type": "null"}}, "$ref": "/$defs/leaf"}
    )
    instance = own_trusted_json(None)
    ledger = BudgetLedger(LM9A_BUDGET_MANIFEST)

    first = evaluate_schema(
        schema, instance, instance_binding=binding(), ledger=ledger
    )
    second = evaluate_schema(
        schema, instance, instance_binding=binding(), ledger=ledger
    )

    shape = schema.schema_nodes * count_json_nodes(instance)
    assert first.reservation.attempted_shape_units == shape
    assert first.reservation.aggregate_before == 0
    assert first.reservation.aggregate_after == shape
    assert second.reservation.attempted_shape_units == shape
    assert second.reservation.aggregate_before == shape
    assert second.reservation.aggregate_after == shape * 2
    assert ledger.snapshot().schema_evaluation_shape_units == shape * 2


def test_per_evaluation_rejection_happens_before_evaluator_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = admit({"default": [None] * (PAYLOAD_PROFILE.schema_node_limit - 2)})
    instance = own_trusted_json([None] * 488)
    ledger = BudgetLedger(LM9A_BUDGET_MANIFEST)

    def evaluator_must_not_run(_: object) -> object:
        raise AssertionError("evaluator constructed after rejected reservation")

    monkeypatch.setattr(schema_profile_module, "_validator_for", evaluator_must_not_run)

    receipt = evaluate_schema(
        schema,
        instance,
        instance_binding=binding(),
        ledger=ledger,
    )

    assert receipt.reservation.accepted is False
    assert receipt.reservation.rejection_reason == "per_evaluation_limit_exceeded"
    assert receipt.evaluator_invoked is False
    assert receipt.evaluation_passed is None
    assert receipt.bounded_errors == ()
    assert receipt.failure_code == "per_evaluation_limit_exceeded"
    assert ledger.snapshot().schema_evaluation_shape_units == 0


def test_private_rejected_reservation_receipt_consumes_exact_capability_without_instance() -> None:
    schema = admit({"type": "null"})
    ledger = BudgetLedger(LM9A_BUDGET_MANIFEST)
    for _ in range(4):
        shape = ledger.reserve_schema_shape(
            schema_nodes=1,
            instance_nodes=4_000_000,
            per_evaluation_limit=4_000_000,
        )
        assert shape.accepted is True
    reservation = reserve_schema_evaluation(
        schema,
        instance_nodes=1,
        ledger=ledger,
    )
    assert reservation.shape_reservation.accepted is False

    receipt = schema_profile_module._rejected_schema_evaluation_receipt(
        schema, reservation
    )

    assert receipt.reservation is reservation.shape_reservation
    assert receipt.reservation.rejection_reason == "invocation_shape_limit_exceeded"
    assert receipt.evaluator_invoked is False
    assert receipt.evaluation_passed is None
    assert receipt.bounded_errors == ()
    assert receipt.failure_code == "invocation_shape_limit_exceeded"
    with pytest.raises(SchemaEvaluationInputError, match="already consumed"):
        schema_profile_module._rejected_schema_evaluation_receipt(
            schema, reservation
        )


def test_schema_rejection_has_deterministic_bounded_keyword_and_paths() -> None:
    schema = admit(
        {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        }
    )

    receipt = evaluate_schema(
        schema,
        own_trusted_json({"value": 1}),
        instance_binding=binding(),
        ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
    )

    assert receipt.evaluator_invoked is True
    assert receipt.evaluation_passed is False
    assert receipt.failure_code == "instance_schema_failed"
    assert receipt.bounded_errors == (
        SchemaIssue(
            code="type",
            instance_path="/value",
            schema_path="/properties/value/type",
            detail_sha256=None,
        ),
    )


def test_schema_issues_are_bounded_and_deterministic() -> None:
    schema = admit({"items": {"type": "string"}})
    instance = own_trusted_json(list(range(MAX_SCHEMA_ISSUES + 20)))

    first = evaluate_schema(
        schema,
        instance,
        instance_binding=binding(),
        ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
    )
    second = evaluate_schema(
        schema,
        instance,
        instance_binding=binding(),
        ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
    )

    assert len(first.bounded_errors) == MAX_SCHEMA_ISSUES == 1_024
    assert first.bounded_errors == second.bounded_errors
    assert all(issue.code == "type" for issue in first.bounded_errors)


def test_full_receipt_selects_canonical_issues_across_large_error_orders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = admit({"items": {"type": "string"}})
    instance = own_trusted_json(list(range(MAX_SCHEMA_ISSUES + 257)))
    validator = schema_profile_module._validator_for(schema)
    instance_view = schema_profile_module._adapt_owned(
        instance,
        translate_refs=False,
    )
    errors = tuple(validator.iter_errors(instance_view))
    assert len(errors) > MAX_SCHEMA_ISSUES

    expected = tuple(
        sorted(
            (
                schema_profile_module._issue_from_validation_error(error)
                for error in errors
            ),
            key=lambda issue: (
                issue.instance_path,
                issue.schema_path,
                issue.code,
                issue.detail_sha256 or "",
            ),
        )[:MAX_SCHEMA_ISSUES]
    )
    orders = (
        errors,
        tuple(reversed(errors)),
        tuple(
            sorted(
                errors,
                key=lambda error: hashlib.sha256(
                    repr(tuple(error.absolute_path)).encode("utf-8")
                ).digest(),
            )
        ),
    )

    receipts = []
    for ordered_errors in orders:
        class OrderedValidator:
            def iter_errors(self, _: object) -> object:
                return iter(ordered_errors)

        monkeypatch.setattr(
            schema_profile_module,
            "_validator_for",
            lambda _: OrderedValidator(),
        )
        receipts.append(
            evaluate_schema(
                schema,
                instance,
                instance_binding=binding(),
                ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
            )
        )

    assert all(receipt.bounded_errors == expected for receipt in receipts)
    assert receipts[0] == receipts[1] == receipts[2]


def test_long_key_issue_amplification_has_per_path_and_aggregate_byte_bounds() -> None:
    keys = [f"{index:04d}-" + "x" * 2_048 for index in range(MAX_SCHEMA_ISSUES)]
    schema = admit(
        {
            "type": "object",
            "properties": {key: {"type": "string"} for key in keys},
        },
        CORE_PROFILE,
    )
    instance = own_trusted_json({key: index for index, key in enumerate(keys)})

    first = evaluate_schema(
        schema,
        instance,
        instance_binding=binding(),
        ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
    )
    second = evaluate_schema(
        schema,
        instance,
        instance_binding=binding(),
        ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
    )

    assert first.evaluation_passed is False
    assert first.failure_code == "instance_schema_failed"
    assert max(
        len(path.encode("utf-8"))
        for issue in first.bounded_errors
        for path in (issue.instance_path, issue.schema_path)
    ) <= EXPECTED_SCHEMA_ISSUE_PATH_BYTES
    assert sum(map(schema_issue_evidence_bytes, first.bounded_errors)) <= (
        EXPECTED_SCHEMA_ISSUE_EVIDENCE_BYTES
    )
    assert 0 < len(first.bounded_errors) < MAX_SCHEMA_ISSUES
    assert first == second
    assert all(issue.detail_sha256 is not None for issue in first.bounded_errors)
    assert schema_profile_module.MAX_SCHEMA_ISSUE_PATH_BYTES == (
        EXPECTED_SCHEMA_ISSUE_PATH_BYTES
    )
    assert schema_profile_module.MAX_SCHEMA_ISSUE_EVIDENCE_BYTES == (
        EXPECTED_SCHEMA_ISSUE_EVIDENCE_BYTES
    )
    identity = canonical_json_bytes(CORE_PROFILE.identity)
    assert b'"bounded_issue_path_utf8_bytes":512' in identity
    assert b'"bounded_issue_evidence_utf8_bytes":65536' in identity


def test_truncated_path_prefixes_are_useful_and_hash_the_complete_paths() -> None:
    shared = "x" * (EXPECTED_SCHEMA_ISSUE_PATH_BYTES * 2)

    def one_issue(tail: str) -> SchemaIssue:
        key = shared + tail
        receipt = evaluate_schema(
            admit({"properties": {key: {"type": "string"}}}),
            own_trusted_json({key: 1}),
            instance_binding=binding(),
            ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
        )
        assert len(receipt.bounded_errors) == 1
        return receipt.bounded_errors[0]

    first = one_issue("-first")
    repeated = one_issue("-first")
    different = one_issue("-second")

    assert first == repeated
    assert first.instance_path == different.instance_path
    assert first.schema_path == different.schema_path
    assert first.instance_path.startswith("/" + "x" * 32)
    assert first.schema_path.startswith("/properties/" + "x" * 32)
    assert len(first.instance_path.encode("utf-8")) <= (
        EXPECTED_SCHEMA_ISSUE_PATH_BYTES
    )
    assert len(first.schema_path.encode("utf-8")) <= EXPECTED_SCHEMA_ISSUE_PATH_BYTES
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", first.detail_sha256 or "")
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", different.detail_sha256 or "")
    assert first.detail_sha256 != different.detail_sha256


def test_evaluator_exception_does_not_stringify_detail_and_bounds_binding_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ExpansiveError(RuntimeError):
        stringify_calls = 0

        def __str__(self) -> str:
            type(self).stringify_calls += 1
            return "must-not-materialize-" + "z" * 100_000

    exception = ExpansiveError("hashed-argument-" + "y" * 100_000)

    class BrokenValidator:
        def iter_errors(self, _: object) -> tuple[()]:
            raise exception

    monkeypatch.setattr(
        schema_profile_module,
        "_validator_for",
        lambda _: BrokenValidator(),
    )
    receipt = evaluate_schema(
        admit({"type": "null"}),
        own_trusted_json(None),
        instance_binding=binding(
            "/" + "p" * (EXPECTED_INSTANCE_POINTER_UTF8_BYTES - 1)
        ),
        ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
    )

    issue = receipt.bounded_errors[0]
    assert ExpansiveError.stringify_calls == 0
    assert len(issue.instance_path.encode("utf-8")) <= EXPECTED_SCHEMA_ISSUE_PATH_BYTES
    assert issue.instance_path.startswith("/" + "p" * 32)
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", issue.detail_sha256 or "")
    assert schema_issue_evidence_bytes(issue) <= EXPECTED_SCHEMA_ISSUE_EVIDENCE_BYTES


def test_evaluator_exception_hash_is_total_for_lone_surrogate_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = evaluator_failure_receipt(monkeypatch, RuntimeError("\ud800"))

    assert receipt.evaluator_invoked is True
    assert receipt.evaluation_passed is None
    assert receipt.failure_code == "schema_evaluator_failed"
    assert len(receipt.bounded_errors) == 1
    assert re.fullmatch(
        r"sha256:[0-9a-f]{64}", receipt.bounded_errors[0].detail_sha256 or ""
    )


def test_evaluator_exception_hash_binds_exact_builtin_structure() -> None:
    digest = schema_profile_module._exception_detail_digest

    assert digest(RuntimeError(1)) != digest(RuntimeError(2))
    assert digest(RuntimeError(True)) != digest(RuntimeError(1))
    assert digest(RuntimeError(b"one")) != digest(RuntimeError(b"two"))
    assert digest(
        RuntimeError((None, True, 7, -0.0, "text", b"bytes", ("nested", 1)))
    ) != digest(
        RuntimeError((None, True, 7, -0.0, "text", b"bytes", ("nested", 2)))
    )


def test_evaluator_exception_integer_projection_keeps_complete_middle_bytes() -> None:
    first_value = (1 << 1_023) | 1
    second_value = first_value | (1 << 500)

    first = schema_profile_module._exception_detail_projection(
        RuntimeError(first_value)
    )
    second = schema_profile_module._exception_detail_projection(
        RuntimeError(second_value)
    )
    zero = schema_profile_module._exception_detail_projection(RuntimeError(0))

    assert first.truncated is False
    assert second.truncated is False
    assert first.projected_bytes == zero.projected_bytes + 127
    assert first.digest != second.digest


@pytest.mark.parametrize("negative", [False, True], ids=["positive", "negative"])
def test_evaluator_exception_integer_projection_full_to_truncated_boundary(
    negative: bool,
) -> None:
    zero = schema_profile_module._exception_detail_projection(RuntimeError(0))
    complete_magnitude_bytes = (
        EXPECTED_EXCEPTION_PROJECTION_BYTES - zero.projected_bytes + 1
    )
    complete_magnitude = (1 << ((complete_magnitude_bytes - 1) * 8)) | 1
    oversized_magnitude = (1 << (complete_magnitude_bytes * 8)) | 1
    oversized_middle_changed = oversized_magnitude | (
        1 << (complete_magnitude_bytes * 4)
    )
    oversized_high_changed = oversized_magnitude | (
        1 << (complete_magnitude_bytes * 8 - 64)
    )
    oversized_low_changed = oversized_magnitude | (1 << 64)

    def signed(magnitude: int) -> int:
        return -magnitude if negative else magnitude

    complete = schema_profile_module._exception_detail_projection(
        RuntimeError(signed(complete_magnitude))
    )
    oversized = schema_profile_module._exception_detail_projection(
        RuntimeError(signed(oversized_magnitude))
    )
    changed = schema_profile_module._exception_detail_projection(
        RuntimeError(signed(oversized_middle_changed))
    )
    high_changed = schema_profile_module._exception_detail_projection(
        RuntimeError(signed(oversized_high_changed))
    )
    low_changed = schema_profile_module._exception_detail_projection(
        RuntimeError(signed(oversized_low_changed))
    )

    assert complete.projected_bytes == EXPECTED_EXCEPTION_PROJECTION_BYTES
    assert complete.truncated is False
    assert oversized.truncated is True
    assert changed.truncated is True
    assert oversized.digest == changed.digest
    if negative:
        assert oversized.digest == high_changed.digest
        assert oversized.digest == low_changed.digest
    else:
        assert oversized.digest != high_changed.digest
        assert oversized.digest != low_changed.digest


@pytest.mark.parametrize(
    "magnitude_bytes",
    [1_048_576, 4_194_304],
    ids=["one-mib", "four-mib"],
)
@pytest.mark.parametrize("negative", [False, True], ids=["positive", "negative"])
def test_oversized_exception_integer_projection_has_constant_transient_memory(
    magnitude_bytes: int, negative: bool
) -> None:
    value = (1 << (magnitude_bytes * 8 - 1)) | 1
    if negative:
        value = -value

    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        projection = schema_profile_module._exception_detail_projection(
            RuntimeError(value)
        )
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert projection.truncated is True
    assert projection.projected_bytes < 1_024
    assert peak_bytes < 262_144
    assert schema_profile_module._EXCEPTION_PROJECTION_INTEGER_SAMPLE_BITS == (
        EXPECTED_EXCEPTION_INTEGER_SAMPLE_BITS
    )
    assert (
        schema_profile_module._EXCEPTION_PROJECTION_NEGATIVE_SAMPLE_POLICY
        == EXPECTED_EXCEPTION_NEGATIVE_SAMPLE_POLICY
    )


def test_oversized_negative_exception_integer_projection_has_constant_work() -> None:
    iterations = 128
    small = -((1 << (1_048_576 * 8 - 1)) | 1)
    large = -((1 << (4_194_304 * 8 - 1)) | 1)

    def best_elapsed(value: int) -> float:
        samples = []
        for _ in range(3):
            started = time.perf_counter()
            for _ in range(iterations):
                projection = schema_profile_module._exception_detail_projection(
                    RuntimeError(value)
                )
                assert projection.truncated is True
            samples.append(time.perf_counter() - started)
        return min(samples)

    small_elapsed = best_elapsed(small)
    large_elapsed = best_elapsed(large)

    assert large_elapsed < small_elapsed * 2 + 0.003


def test_evaluator_exception_hash_never_calls_unknown_object_text_hooks() -> None:
    class HostileDetail:
        str_calls = 0
        repr_calls = 0

        def __str__(self) -> str:
            type(self).str_calls += 1
            raise AssertionError("exception hashing called hostile __str__")

        def __repr__(self) -> str:
            type(self).repr_calls += 1
            raise AssertionError("exception hashing called hostile __repr__")

    first = schema_profile_module._exception_detail_digest(
        RuntimeError(HostileDetail())
    )
    second = schema_profile_module._exception_detail_digest(
        RuntimeError(HostileDetail())
    )

    assert first == second
    assert HostileDetail.str_calls == 0
    assert HostileDetail.repr_calls == 0


def test_evaluator_exception_hash_bypasses_hostile_type_metadata_descriptors() -> None:
    class HostileMetadata(type):
        module_calls = 0

        @property
        def __module__(cls) -> str:
            type(cls).module_calls += 1
            raise AssertionError("exception hashing invoked metaclass descriptor")

    class HostileDetail(metaclass=HostileMetadata):
        """An exception detail whose metaclass metadata must remain unread."""

    first = schema_profile_module._exception_detail_digest(
        RuntimeError(HostileDetail())
    )
    second = schema_profile_module._exception_detail_digest(
        RuntimeError(HostileDetail())
    )

    assert first == second
    assert HostileMetadata.module_calls == 0


def test_evaluator_exception_projection_is_iterative_and_mechanically_bounded() -> None:
    deep: object = 1
    for _ in range(10_000):
        deep = (deep,)
    cycle: list[object] = []
    cycle.append(cycle)

    depth_projection = schema_profile_module._exception_detail_projection(
        RuntimeError((deep, cycle))
    )
    item_projection = schema_profile_module._exception_detail_projection(
        RuntimeError(tuple(range(10_000)))
    )
    byte_projection = schema_profile_module._exception_detail_projection(
        RuntimeError("\ud800" + "x" * 100_000)
    )

    for projection in (depth_projection, item_projection, byte_projection):
        assert type(projection.digest) is bytes
        assert len(projection.digest) == 32
        assert projection.projected_bytes <= EXPECTED_EXCEPTION_PROJECTION_BYTES
        assert projection.projected_items <= EXPECTED_EXCEPTION_PROJECTION_ITEMS
        assert projection.maximum_depth <= EXPECTED_EXCEPTION_PROJECTION_DEPTH
        assert projection.truncated is True
    assert schema_profile_module._EXCEPTION_PROJECTION_MAX_BYTES == (
        EXPECTED_EXCEPTION_PROJECTION_BYTES
    )
    assert schema_profile_module._EXCEPTION_PROJECTION_MAX_ITEMS == (
        EXPECTED_EXCEPTION_PROJECTION_ITEMS
    )
    assert schema_profile_module._EXCEPTION_PROJECTION_MAX_DEPTH == (
        EXPECTED_EXCEPTION_PROJECTION_DEPTH
    )


def test_evaluator_exception_returns_hash_only_and_keeps_reservation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "never expose evaluator exception detail"
    schema = admit({"type": "null"})
    ledger = BudgetLedger(LM9A_BUDGET_MANIFEST)

    class BrokenValidator:
        def iter_errors(self, _: object) -> tuple[()]:
            raise RuntimeError(secret)

    monkeypatch.setattr(
        schema_profile_module,
        "_validator_for",
        lambda _: BrokenValidator(),
    )

    receipt = evaluate_schema(
        schema,
        own_trusted_json(None),
        instance_binding=binding(),
        ledger=ledger,
    )

    serialized = repr(asdict(receipt))
    assert receipt.reservation.accepted is True
    assert receipt.evaluator_invoked is True
    assert receipt.evaluation_passed is None
    assert receipt.failure_code == "schema_evaluator_failed"
    assert len(receipt.bounded_errors) == 1
    assert receipt.bounded_errors[0].code == "schema_evaluator_exception"
    assert re.fullmatch(
        r"sha256:[0-9a-f]{64}", receipt.bounded_errors[0].detail_sha256 or ""
    )
    assert secret not in repr(receipt)
    assert secret not in serialized
    assert ledger.snapshot().schema_evaluation_shape_units == schema.schema_nodes


def test_evaluation_receipts_and_issues_are_immutable() -> None:
    receipt = evaluate_schema(
        admit({"type": "string"}),
        own_trusted_json(1),
        instance_binding=binding(),
        ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
    )

    assert type(receipt) is SchemaEvaluationReceipt
    assert type(receipt.bounded_errors) is tuple
    with pytest.raises((AttributeError, TypeError)):
        receipt.failure_code = None
    with pytest.raises((AttributeError, TypeError)):
        receipt.bounded_errors[0].code = "forged"


def test_issue_and_receipt_constructors_enforce_evidence_byte_limits() -> None:
    with pytest.raises(SchemaEvaluationInputError):
        SchemaIssue(
            code="type",
            instance_path="/" + "x" * EXPECTED_SCHEMA_ISSUE_PATH_BYTES,
            schema_path="",
            detail_sha256=None,
        )

    issue = SchemaIssue(
        code="x" * 64,
        instance_path="i" * EXPECTED_SCHEMA_ISSUE_PATH_BYTES,
        schema_path="s" * EXPECTED_SCHEMA_ISSUE_PATH_BYTES,
        detail_sha256="sha256:" + "a" * 64,
    )
    issue_count = EXPECTED_SCHEMA_ISSUE_EVIDENCE_BYTES // (
        schema_issue_evidence_bytes(issue) + 4
    ) + 1
    valid = evaluate_schema(
        admit({"type": "null"}),
        own_trusted_json(None),
        instance_binding=binding(),
        ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
    )

    with pytest.raises(SchemaEvaluationInputError):
        SchemaEvaluationReceipt(
            reservation=valid.reservation,
            evaluator_invoked=True,
            evaluation_passed=False,
            bounded_errors=(issue,) * issue_count,
            failure_code="instance_schema_failed",
        )


def test_schema_profile_api_is_exported_from_the_stable_kernel_surface() -> None:
    expected = {
        "AdmittedSchema",
        "CORE_PROFILE",
        "CORE_SCHEMA_PROFILE_ID",
        "InstanceBinding",
        "PAYLOAD_PROFILE",
        "PAYLOAD_SCHEMA_PROFILE_ID",
        "SchemaAdmissionError",
        "SchemaEvaluationReceipt",
        "SchemaIssue",
        "SchemaProfile",
        "admit_schema",
        "evaluate_schema",
    }

    assert expected.issubset(set(validation_kernel.__all__))
    for name in expected:
        assert getattr(validation_kernel, name) is getattr(schema_profile_module, name)
