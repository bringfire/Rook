from __future__ import annotations

import importlib.metadata
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace

import pytest
from jsonschema import Draft202012Validator

import rook.validation_kernel as validation_kernel
import rook.validation_kernel.schema_profile as schema_profile_module
from rook.validation_kernel.budget import BudgetLedger, LM9A_BUDGET_MANIFEST
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
    SchemaEvaluationReceipt,
    SchemaIssue,
    SchemaProfile,
    admit_schema,
    evaluate_schema,
)


DRAFT_2020_12_METASCHEMA_ID = "https://json-schema.org/draft/2020-12/schema"
EXPECTED_SCHEMA_ISSUE_PATH_BYTES = 512
EXPECTED_SCHEMA_ISSUE_EVIDENCE_BYTES = 65_536
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


def schema_issue_evidence_bytes(issue: SchemaIssue) -> int:
    fields = (
        issue.code,
        issue.instance_path,
        issue.schema_path,
        issue.detail_sha256 or "",
    )
    return sum(len(field.encode("utf-8")) for field in fields)


def admit(host: dict[str, object], profile: SchemaProfile = PAYLOAD_PROFILE) -> AdmittedSchema:
    return admit_schema("schema.test", owned_schema(host), profile)


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
        assert canonical_fingerprint(profile.identity) == profile.profile_fingerprint


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
        instance_binding=binding("/" + "p" * 100_000),
        ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
    )

    issue = receipt.bounded_errors[0]
    assert ExpansiveError.stringify_calls == 0
    assert len(issue.instance_path.encode("utf-8")) <= EXPECTED_SCHEMA_ISSUE_PATH_BYTES
    assert issue.instance_path.startswith("/" + "p" * 32)
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", issue.detail_sha256 or "")
    assert schema_issue_evidence_bytes(issue) <= EXPECTED_SCHEMA_ISSUE_EVIDENCE_BYTES


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
