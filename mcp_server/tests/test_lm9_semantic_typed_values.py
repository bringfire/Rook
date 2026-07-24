from __future__ import annotations

import ast
import copy
import dataclasses
import functools
import importlib
import importlib.util
import inspect
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
REGISTRY_PATH = (
    SCRIPTS
    / "lm9_typed_fact_carrier_contracts"
    / "semantic_value_schema_registry.json"
)
PAYLOAD_SCHEMA_PATH = (
    SCRIPTS
    / "lm9_typed_fact_carrier_contracts"
    / "planner_task_typed_facts_payload_schema.json"
)


def _load_script(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TYPED_VALUES = _load_script("lm9_semantic_typed_values")
CONT_ARTIFACTS = _load_script("lm9b_p_evaluator_only_continuation_artifacts")
QUALIFICATION = _load_script("lm9_typed_fact_carrier_qualification")


def _runtime():
    return TYPED_VALUES.current_runtime_identity()


def _profile():
    return TYPED_VALUES.build_profile_identity(_runtime())


def _registry_value() -> dict[str, object]:
    return json.loads(REGISTRY_PATH.read_bytes())


def _reclose_registry(value: dict[str, object]) -> None:
    for row in value["entries"]:
        row["schema_fingerprint"] = TYPED_VALUES.fingerprint(
            row["schema_document"]
        )
    value["schema_evaluator_profile_fingerprint"] = _profile().fingerprint
    value["registry_fingerprint"] = TYPED_VALUES.fingerprint_without(
        value, "registry_fingerprint"
    )


def _verify_registry(value: dict[str, object]):
    raw = TYPED_VALUES.canonical_json_bytes(value)
    return TYPED_VALUES.verify_semantic_value_registry(
        value,
        raw_registry_byte_count=len(raw),
        runtime=_runtime(),
    )


def _schema(schema_id: str) -> dict[str, object]:
    return copy.deepcopy(
        next(
            row["schema_document"]
            for row in _registry_value()["entries"]
            if row["schema_id"] == schema_id
        )
    )


def _string_schema() -> dict[str, object]:
    return _schema("rook.semantic_string:v1")


def _set_unknown_id(schema: dict[str, object]) -> None:
    schema["$id"] = "rook.semantic_unknown:v1"


@pytest.mark.parametrize(
    ("mutation", "expected"),
    (
        (
            lambda schema: schema.update(
                {"$schema": "https://example.invalid/schema"}
            ),
            "dialect",
        ),
        (_set_unknown_id, "document identity"),
        (lambda schema: schema.update({"$ref": "#/anything"}), "keyword"),
        (lambda schema: schema.update({"$defs": {}}), "keyword"),
        (lambda schema: schema.update({"format": "decimal"}), "keyword"),
        (lambda schema: schema.update({"pattern": "^.*$"}), "pattern"),
    ),
)
def test_schema_profile_rejects_unsealed_documents(
    mutation, expected: str
) -> None:
    schema = _string_schema()
    mutation(schema)
    with pytest.raises(ValueError, match=expected):
        TYPED_VALUES.admit_schema_document(schema, profile=_profile())


def test_profile_identity_closes_runtime_evaluator_and_type_policy() -> None:
    runtime = _runtime()
    profile = TYPED_VALUES.build_profile_identity(runtime)
    value = json.loads(TYPED_VALUES.canonical_json_bytes(profile.value))

    assert value["profile_id"] == TYPED_VALUES.PROFILE_ID
    assert value["helper_contract_id"] == TYPED_VALUES.HELPER_CONTRACT_ID
    assert value["dialect"] == TYPED_VALUES.DIALECT
    assert value["ownership"] == "scientific_instrument_only"
    assert value["runtime"] == TYPED_VALUES.runtime_identity_value(runtime)
    assert value["evaluator"] == {
        "class": (
            "jsonschema.validators.Draft202012Validator"
            "+rook_exact_json_types"
        ),
        "jsonschema_distribution_version": "4.26.0",
        "metaschema_id": TYPED_VALUES.DIALECT,
        "metaschema_fingerprint": TYPED_VALUES.fingerprint(
            TYPED_VALUES.Draft202012Validator.META_SCHEMA
        ),
        "type_policy": "rook.json_python_exact_types:v1",
        "python_type_checker": {
            "array": "type(value) is list",
            "boolean": "type(value) is bool",
            "integer": "type(value) is int",
            "null": "value is None",
            "object": "type(value) is dict",
            "string": "type(value) is str",
        },
        "format_checker": None,
        "resolver": None,
        "reference_retrieval": False,
    }
    assert value["admission"] == {
        "allowed_keywords": sorted(TYPED_VALUES.ALLOWED_KEYWORDS),
        "forbidden_reference_keywords": sorted(
            TYPED_VALUES.FORBIDDEN_REFERENCE_KEYWORDS
        ),
        "allowed_patterns": sorted(TYPED_VALUES.ALLOWED_PATTERNS),
        "structural_algorithm": "rook.lm9.schema_tree_admission:v1",
        "expansion_algorithm": (
            "rook.lm9.schema_structural_reachability:v1"
        ),
    }
    assert value["work_metric"] == (
        "rook.schema_evaluation_shape:"
        "max_schema_or_expansion_times_instance:v1"
    )
    assert value["issue_policy"] == {
        "ordering": [
            "instance_json_pointer",
            "schema_json_pointer",
            "failed_keyword",
            "bounded_detail_fingerprint",
        ],
        "truncation": "forbidden",
    }
    assert value["limits"] == {
        "raw_registry_bytes": 4_194_304,
        "raw_instance_envelope_bytes": 1_048_576,
        "embedded_schema_canonical_bytes": 65_536,
        "schema_depth": 32,
        "schema_nodes": 4_096,
        "schema_collection_size": 256,
        "schema_string_bytes": 65_536,
        "instance_depth": 32,
        "instance_collection_size": 256,
        "instance_string_bytes": 65_536,
        "scalar_characters": 1_024,
        "issues": 1_024,
        "evaluation_expansion_units": 32_768,
        "per_evaluation_shape_units": 2_000_000,
        "aggregate_shape_units": 16_000_000,
    }
    assert profile.fingerprint == TYPED_VALUES.fingerprint(value)


def test_schema_admission_reauthenticates_profile_identity() -> None:
    profile = _profile()
    forged = TYPED_VALUES.ProfileIdentity(
        value=profile.value,
        fingerprint="sha256:" + "0" * 64,
    )
    with pytest.raises(ValueError, match="profile identity"):
        TYPED_VALUES.admit_schema_document(_string_schema(), profile=forged)


def test_schema_admission_isolated_from_global_validator_registration() -> None:
    importlib.import_module("rook.validation_kernel.schema_profile")

    admitted = TYPED_VALUES.admit_schema_document(
        _string_schema(), profile=_profile()
    )
    assert admitted.schema_id == "rook.semantic_string:v1"


def _schema_with_null_keyword(
    keyword: str, *, nested: bool = False
) -> dict[str, object]:
    schema: dict[str, object] = {
        "$schema": TYPED_VALUES.DIALECT,
        "$id": "rook.test:malformed-keyword",
        "type": "object",
    }
    target = schema
    if nested:
        child: dict[str, object] = {}
        schema["properties"] = {"child": child}
        target = child
    target[keyword] = None
    return schema


@pytest.mark.parametrize(
    ("keyword", "nested", "expected"),
    (
        ("$schema", True, "dialect"),
        ("$id", True, "identity"),
        ("type", False, "type"),
        ("properties", False, "properties"),
        ("required", False, "required"),
        ("additionalProperties", False, "additionalProperties"),
        ("propertyNames", False, "propertyNames"),
        ("pattern", False, "pattern"),
        ("not", False, "not"),
        ("minProperties", False, "minProperties"),
        ("maxProperties", False, "maxProperties"),
        ("minLength", False, "minLength"),
        ("maxLength", False, "maxLength"),
        ("minimum", False, "minimum"),
        ("maximum", False, "maximum"),
    ),
)
def test_schema_admission_refuses_explicit_null_keyword_values(
    keyword: str,
    nested: bool,
    expected: str,
) -> None:
    with pytest.raises(ValueError, match=expected):
        TYPED_VALUES.admit_schema_document(
            _schema_with_null_keyword(keyword, nested=nested),
            profile=_profile(),
        )


def test_schema_admission_preserves_valid_explicit_null_const() -> None:
    schema = {
        "$schema": TYPED_VALUES.DIALECT,
        "$id": "rook.test:null-const",
        "const": None,
    }
    admitted = TYPED_VALUES.admit_schema_document(schema, profile=_profile())

    assert admitted.schema_id == "rook.test:null-const"


def test_exact_boolean_is_not_an_integer() -> None:
    integer = TYPED_VALUES.admit_schema_document(
        _schema("rook.semantic_integer:v1"), profile=_profile()
    )
    issues = TYPED_VALUES.validate_schema_instance(
        {"schema": "rook.semantic_integer:v1", "value": True},
        schema=integer,
        aggregate_budget=TYPED_VALUES.EvaluationBudget(),
        instance_path="/fact",
    )
    assert len(issues) == 1
    assert issues[0].keyword == "type"


def test_instrument_failures_have_one_code_owned_exception_type() -> None:
    assert hasattr(TYPED_VALUES, "InstrumentFailure")
    assert issubclass(TYPED_VALUES.InstrumentFailure, RuntimeError)


def test_evaluation_budget_is_code_owned_and_reports_reserved_work() -> None:
    budget = TYPED_VALUES.EvaluationBudget()

    assert budget.limit == TYPED_VALUES.MAX_AGGREGATE_SHAPE
    assert budget.used == 0
    with pytest.raises(TypeError):
        TYPED_VALUES.EvaluationBudget(limit=1)


def test_work_reservation_accepts_exact_limits_and_refuses_first_over() -> None:
    budget = TYPED_VALUES.EvaluationBudget()

    assert TYPED_VALUES._reserve_evaluation_shape(
        budget,
        schema_shape_units=1,
        instance_nodes=TYPED_VALUES.MAX_EVALUATION_SHAPE,
    ) == TYPED_VALUES.MAX_EVALUATION_SHAPE
    assert budget.used == TYPED_VALUES.MAX_EVALUATION_SHAPE

    with pytest.raises(TYPED_VALUES.InstrumentFailure, match="per-evaluation"):
        TYPED_VALUES._reserve_evaluation_shape(
            TYPED_VALUES.EvaluationBudget(),
            schema_shape_units=1,
            instance_nodes=TYPED_VALUES.MAX_EVALUATION_SHAPE + 1,
        )

    aggregate = TYPED_VALUES.EvaluationBudget()
    for _ in range(
        TYPED_VALUES.MAX_AGGREGATE_SHAPE
        // TYPED_VALUES.MAX_EVALUATION_SHAPE
    ):
        TYPED_VALUES._reserve_evaluation_shape(
            aggregate,
            schema_shape_units=1,
            instance_nodes=TYPED_VALUES.MAX_EVALUATION_SHAPE,
        )
    assert aggregate.used == TYPED_VALUES.MAX_AGGREGATE_SHAPE
    with pytest.raises(TYPED_VALUES.InstrumentFailure, match="aggregate"):
        TYPED_VALUES._reserve_evaluation_shape(
            aggregate,
            schema_shape_units=1,
            instance_nodes=1,
        )
    assert aggregate.used == TYPED_VALUES.MAX_AGGREGATE_SHAPE


def _depth_schema(depth: int) -> dict[str, object]:
    root: dict[str, object] = {
        "$schema": TYPED_VALUES.DIALECT,
        "$id": "rook.test:depth",
    }
    current = root
    for _ in range(depth - 1):
        child: dict[str, object] = {}
        current["not"] = child
        current = child
    current["type"] = "string"
    return root


def _node_bound_schema(*, over: bool) -> dict[str, object]:
    properties: dict[str, object] = {}
    remaining_leaves = 1_532
    for index in range(256):
        leaf_count = min(6, remaining_leaves)
        remaining_leaves -= leaf_count
        properties[f"p{index:x}"] = {
            "type": "object",
            "properties": {
                chr(ord("a") + leaf): {"type": "string"}
                for leaf in range(leaf_count)
            },
            "additionalProperties": False,
        }
    schema = {
        "$schema": TYPED_VALUES.DIALECT,
        "$id": "rook.test:nodes",
        "type": "object",
        "properties": properties,
        "required": ["p0", "p1", "p2"] if over else ["p0", "p1"],
    }
    expected = 4_097 if over else 4_096
    assert TYPED_VALUES._json_node_count(schema) == expected
    return schema


def test_json_node_count_matches_lm9a_value_node_accounting() -> None:
    assert TYPED_VALUES._json_node_count({"key": "value"}) == 2
    assert TYPED_VALUES._json_node_count(["value"]) == 2


def _canonical_size_schema(target: int) -> dict[str, object]:
    schema = {
        "$schema": TYPED_VALUES.DIALECT,
        "$id": "x",
        "type": "string",
    }
    current = len(TYPED_VALUES.canonical_json_bytes(schema))
    schema["$id"] = "x" * (target - current + 1)
    assert len(TYPED_VALUES.canonical_json_bytes(schema)) == target
    return schema


def _expansion_bound_schema(*, over: bool) -> dict[str, object]:
    properties: dict[str, object] = {}
    for outer in range(256):
        leaf_count = 129 if over and outer == 0 else 128
        properties[f"p{outer:x}"] = {
            "type": "object",
            "properties": {
                f"v{leaf:x}": {"type": "string"}
                for leaf in range(leaf_count)
            },
        }
    return {
        "$schema": TYPED_VALUES.DIALECT,
        "$id": "rook.test:expansion",
        "type": "object",
        "properties": properties,
    }


def test_expansion_counts_only_structural_child_schemas() -> None:
    schema = {
        "$schema": TYPED_VALUES.DIALECT,
        "$id": "rook.test:shape",
        "type": "object",
        "properties": {
            "a": {
                "type": "string",
                "pattern": TYPED_VALUES.MACHINE_KEY_PATTERN,
            },
            "b": {"type": "string", "not": {"const": "x"}},
        },
        "propertyNames": {"pattern": TYPED_VALUES.MACHINE_KEY_PATTERN},
        "additionalProperties": False,
    }
    admitted = TYPED_VALUES.admit_schema_document(schema, profile=_profile())
    assert admitted.expansion_units == 4


@pytest.mark.parametrize("depth", (32,))
def test_schema_depth_accepts_exact_bound(depth: int) -> None:
    TYPED_VALUES.admit_schema_document(_depth_schema(depth), profile=_profile())


def test_schema_depth_refuses_first_value_over_bound() -> None:
    with pytest.raises(TYPED_VALUES.InstrumentFailure, match="depth"):
        TYPED_VALUES.admit_schema_document(
            _depth_schema(33), profile=_profile()
        )


def test_schema_nodes_accept_exact_bound_and_refuse_first_over() -> None:
    admitted = TYPED_VALUES.admit_schema_document(
        _node_bound_schema(over=False), profile=_profile()
    )
    assert admitted.schema_nodes == 4_096
    with pytest.raises(TYPED_VALUES.InstrumentFailure, match="node"):
        TYPED_VALUES.admit_schema_document(
            _node_bound_schema(over=True), profile=_profile()
        )


def test_schema_collection_accepts_256_and_refuses_257() -> None:
    def schema(count: int) -> dict[str, object]:
        return {
            "$schema": TYPED_VALUES.DIALECT,
            "$id": "rook.test:collection",
            "type": "object",
            "properties": {
                f"p{index:x}": {"type": "string"}
                for index in range(count)
            },
        }

    TYPED_VALUES.admit_schema_document(schema(256), profile=_profile())
    with pytest.raises(TYPED_VALUES.InstrumentFailure, match="collection"):
        TYPED_VALUES.admit_schema_document(schema(257), profile=_profile())


def test_schema_string_accepts_65536_bytes_and_refuses_65537(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(TYPED_VALUES, "MAX_SCHEMA_CANONICAL_BYTES", 131_072)
    accepted = {
        "$schema": TYPED_VALUES.DIALECT,
        "$id": "rook.test:string-bound",
        "const": "x" * 65_536,
    }
    refused = copy.deepcopy(accepted)
    refused["const"] += "x"
    TYPED_VALUES.admit_schema_document(accepted, profile=_profile())
    with pytest.raises(TYPED_VALUES.InstrumentFailure, match="string"):
        TYPED_VALUES.admit_schema_document(refused, profile=_profile())


def test_canonical_schema_bytes_accept_65536_and_refuse_65537() -> None:
    TYPED_VALUES.admit_schema_document(
        _canonical_size_schema(65_536), profile=_profile()
    )
    with pytest.raises(TYPED_VALUES.InstrumentFailure, match="canonical bytes"):
        TYPED_VALUES.admit_schema_document(
            _canonical_size_schema(65_537), profile=_profile()
        )


def test_expansion_accepts_32768_and_refuses_32769(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(TYPED_VALUES, "MAX_SCHEMA_NODES", 1_000_000)
    monkeypatch.setattr(
        TYPED_VALUES, "MAX_SCHEMA_CANONICAL_BYTES", 4_194_304
    )
    admitted = TYPED_VALUES.admit_schema_document(
        _expansion_bound_schema(over=False), profile=_profile()
    )
    assert admitted.expansion_units == 32_768
    with pytest.raises(TYPED_VALUES.InstrumentFailure, match="expansion"):
        TYPED_VALUES.admit_schema_document(
            _expansion_bound_schema(over=True), profile=_profile()
        )


def _any_schema() -> dict[str, object]:
    return {
        "$schema": TYPED_VALUES.DIALECT,
        "$id": "rook.test:any-instance",
    }


def _nested_instance(depth: int) -> object:
    value: object = None
    for _ in range(depth - 1):
        value = [value]
    return value


def test_instance_resources_accept_exact_bounds_and_refuse_first_over() -> None:
    schema = TYPED_VALUES.admit_schema_document(
        _any_schema(), profile=_profile()
    )

    accepted = (
        _nested_instance(32),
        [None] * 256,
        "x" * 65_536,
    )
    for instance in accepted:
        TYPED_VALUES.validate_schema_instance(
            instance,
            schema=schema,
            aggregate_budget=TYPED_VALUES.EvaluationBudget(),
            instance_path="/value",
        )

    refused = (
        (_nested_instance(33), "depth"),
        ([None] * 257, "collection"),
        ("x" * 65_537, "string"),
    )
    for instance, expected in refused:
        with pytest.raises(TYPED_VALUES.InstrumentFailure, match=expected):
            TYPED_VALUES.validate_schema_instance(
                instance,
                schema=schema,
                aggregate_budget=TYPED_VALUES.EvaluationBudget(),
                instance_path="/value",
            )


def test_validation_reserves_work_before_evaluator_invocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = TYPED_VALUES.admit_schema_document(
        _any_schema(), profile=_profile()
    )
    budget = TYPED_VALUES.EvaluationBudget()
    expected = max(schema.schema_nodes, schema.expansion_units)

    class RecordingValidator:
        def __init__(self, _schema: object) -> None:
            assert budget.used == expected

        def iter_errors(self, _instance: object):
            return iter(())

    monkeypatch.setattr(TYPED_VALUES, "_SEALED_VALIDATOR", RecordingValidator)
    assert TYPED_VALUES.validate_schema_instance(
        None,
        schema=schema,
        aggregate_budget=budget,
        instance_path="/value",
    ) == ()
    assert budget.used == expected


def _many_issue_case(count: int) -> tuple[dict[str, object], dict[str, object]]:
    schema_groups: dict[str, object] = {}
    instance_groups: dict[str, object] = {}
    remaining = count
    group = 0
    while remaining:
        group_size = min(256, remaining)
        properties = {
            f"v{index:x}": {"type": "string"}
            for index in range(group_size)
        }
        values = {f"v{index:x}": 0 for index in range(group_size)}
        schema_groups[f"g{group:x}"] = {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        }
        instance_groups[f"g{group:x}"] = values
        remaining -= group_size
        group += 1
    return (
        {
            "$schema": TYPED_VALUES.DIALECT,
            "$id": "rook.test:issue-count",
            "type": "object",
            "properties": schema_groups,
            "additionalProperties": False,
        },
        instance_groups,
    )


def test_issue_count_accepts_1024_and_refuses_1025_without_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(TYPED_VALUES, "MAX_SCHEMA_NODES", 20_000)
    monkeypatch.setattr(TYPED_VALUES, "MAX_SCHEMA_CANONICAL_BYTES", 262_144)
    monkeypatch.setattr(TYPED_VALUES, "MAX_EVALUATION_SHAPE", 100_000_000)
    monkeypatch.setattr(TYPED_VALUES, "MAX_AGGREGATE_SHAPE", 100_000_000)

    accepted_schema, accepted_instance = _many_issue_case(1_024)
    admitted = TYPED_VALUES.admit_schema_document(
        accepted_schema, profile=_profile()
    )
    issues = TYPED_VALUES.validate_schema_instance(
        accepted_instance,
        schema=admitted,
        aggregate_budget=TYPED_VALUES.EvaluationBudget(),
        instance_path="/facts",
    )
    assert len(issues) == 1_024

    refused_schema, refused_instance = _many_issue_case(1_025)
    admitted = TYPED_VALUES.admit_schema_document(
        refused_schema, profile=_profile()
    )
    with pytest.raises(TYPED_VALUES.InstrumentFailure, match="issue"):
        TYPED_VALUES.validate_schema_instance(
            refused_instance,
            schema=admitted,
            aggregate_budget=TYPED_VALUES.EvaluationBudget(),
            instance_path="/facts",
        )


def test_issues_use_canonical_pointers_and_complete_sort_key() -> None:
    schema = TYPED_VALUES.admit_schema_document(
        {
            "$schema": TYPED_VALUES.DIALECT,
            "$id": "rook.test:issue-order",
            "type": "object",
            "properties": {
                "a/b": {"type": "string"},
                "a~b": {"type": "string"},
            },
        },
        profile=_profile(),
    )
    issues = TYPED_VALUES.validate_schema_instance(
        {"a/b": 0, "a~b": 0},
        schema=schema,
        aggregate_budget=TYPED_VALUES.EvaluationBudget(),
        instance_path="/root",
    )

    assert [issue.instance_path for issue in issues] == [
        "/root/a~0b",
        "/root/a~1b",
    ]
    assert [issue.schema_path for issue in issues] == [
        "/properties/a~0b/type",
        "/properties/a~1b/type",
    ]
    assert all(issue.keyword == "type" for issue in issues)
    assert all(
        issue.detail_fingerprint.startswith("sha256:")
        and len(issue.detail_fingerprint) == 71
        for issue in issues
    )


def _duplicate_registry_id(value: dict[str, object]) -> None:
    value["entries"][1] = copy.deepcopy(value["entries"][0])
    _reclose_registry(value)


def _unsort_registry(value: dict[str, object]) -> None:
    value["entries"].reverse()
    _reclose_registry(value)


def _wrong_schema_fingerprint(value: dict[str, object]) -> None:
    _reclose_registry(value)
    value["entries"][0]["schema_fingerprint"] = "sha256:" + "0" * 64
    value["registry_fingerprint"] = TYPED_VALUES.fingerprint_without(
        value, "registry_fingerprint"
    )


def _wrong_profile_fingerprint(value: dict[str, object]) -> None:
    _reclose_registry(value)
    value["schema_evaluator_profile_fingerprint"] = "sha256:" + "0" * 64
    value["registry_fingerprint"] = TYPED_VALUES.fingerprint_without(
        value, "registry_fingerprint"
    )


def _extra_registry_field(value: dict[str, object]) -> None:
    _reclose_registry(value)
    value["extra"] = True
    value["registry_fingerprint"] = TYPED_VALUES.fingerprint_without(
        value, "registry_fingerprint"
    )


def _unknown_fifth_registry_entry(value: dict[str, object]) -> None:
    value["entries"].append(
        {
            "schema_id": "rook.semantic_unknown:v1",
            "schema_fingerprint": "",
            "schema_document": {
                "$schema": TYPED_VALUES.DIALECT,
                "$id": "rook.semantic_unknown:v1",
                "type": "object",
                "properties": {
                    "schema": {"const": "rook.semantic_unknown:v1"},
                    "value": {"type": "string"},
                },
                "required": ["schema", "value"],
                "additionalProperties": False,
            },
        }
    )
    value["entries"].sort(key=lambda row: row["schema_id"])
    _reclose_registry(value)


def _registry_fingerprint_drift(value: dict[str, object]) -> None:
    _reclose_registry(value)
    value["registry_fingerprint"] = "sha256:" + "0" * 64


def _reclosed_schema_document_mutation(value: dict[str, object]) -> None:
    integer = next(
        row
        for row in value["entries"]
        if row["schema_id"] == "rook.semantic_integer:v1"
    )
    integer["schema_document"]["properties"]["value"]["maximum"] = 100
    _reclose_registry(value)


def test_code_owned_registry_verifies_with_exact_entry_set() -> None:
    value = _registry_value()
    verified = _verify_registry(value)

    assert set(verified.entries) == {
        "rook.semantic_boolean:v1",
        "rook.semantic_integer:v1",
        "rook.semantic_scalar:v1",
        "rook.semantic_string:v1",
    }
    assert verified.profile == _profile()
    assert verified.fingerprint == value["registry_fingerprint"]


@pytest.mark.parametrize(
    ("mutation", "expected"),
    (
        (_duplicate_registry_id, "entry identity"),
        (_unsort_registry, "ordered"),
        (_wrong_schema_fingerprint, "entry identity"),
        (_wrong_profile_fingerprint, "registry identity"),
        (_extra_registry_field, "registry shape"),
        (_unknown_fifth_registry_entry, "entries"),
        (_registry_fingerprint_drift, "registry fingerprint"),
        (_reclosed_schema_document_mutation, "code-owned registry"),
    ),
)
def test_registry_refuses_fully_reclosed_contract_mutations(
    mutation, expected: str
) -> None:
    value = _registry_value()
    mutation(value)
    with pytest.raises(ValueError, match=expected):
        _verify_registry(value)


def test_forward_payload_schema_is_closed_generic_four_field_shell() -> None:
    raw = PAYLOAD_SCHEMA_PATH.read_bytes()
    value = TYPED_VALUES.parse_strict_json(raw, label="payload schema")
    admitted = TYPED_VALUES.admit_schema_document(
        value, profile=_profile()
    )

    assert admitted.schema_id == TYPED_VALUES.FORWARD_PAYLOAD_SCHEMA_ID
    facts = value["properties"]["facts"]
    assert facts["minProperties"] == 1
    assert facts["maxProperties"] == 256
    assert facts["propertyNames"] == {
        "type": "string",
        "minLength": 1,
        "maxLength": 245,
        "pattern": TYPED_VALUES.MACHINE_KEY_PATTERN,
    }
    shell = facts["additionalProperties"]
    assert shell["required"] == [
        "schema",
        "value",
        "unit",
        "unit_context_ref",
    ]
    assert set(shell["properties"]) == {
        "schema",
        "value",
        "unit",
        "unit_context_ref",
    }
    serialized = TYPED_VALUES.canonical_json_bytes(value).decode("utf-8")
    assert "grid_spacing" not in serialized
    assert "annotation_text" not in serialized


def test_forward_payload_schema_refuses_fully_reclosed_contract_drift() -> None:
    value = TYPED_VALUES.parse_strict_json(
        PAYLOAD_SCHEMA_PATH.read_bytes(), label="payload schema"
    )
    value["properties"]["facts"]["maxProperties"] = 255

    with pytest.raises(ValueError, match="code-owned schema"):
        TYPED_VALUES.admit_schema_document(value, profile=_profile())


def _registry():
    return _verify_registry(_registry_value())


@functools.lru_cache(maxsize=1)
def _valid_frozen_unit_context_inputs() -> dict[str, object]:
    source = CONT_ARTIFACTS.verify_historical_source()
    records = {record.role: record for record in source.input_records}
    environment = json.loads(
        records["authority.environment_snapshot"].raw_bytes
    )
    attempt = json.loads(records["attempt_context"].raw_bytes)
    return {
        "environment_artifact_bytes": records[
            "authority.environment_snapshot"
        ].raw_bytes,
        "environment_payload_schema_bytes": (
            QUALIFICATION._environment_payload_schema_bytes(records)
        ),
        "attempt_context_bytes": records["attempt_context"].raw_bytes,
        "expected_artifact_fingerprint": environment[
            "artifact_fingerprint"
        ],
        "expected_issuer_id": environment["issuer"]["authority_id"],
        "expected_environment_session_id": attempt[
            "environment_session_id"
        ],
        "expected_task_session_id": attempt["task_session_id"],
        "evaluated_at": attempt["evaluated_at"],
    }


def _unit_context_index():
    return TYPED_VALUES.derive_verified_unit_context_index(
        **_valid_frozen_unit_context_inputs()
    )


def _scalar(lexeme: str) -> dict[str, object]:
    return {
        "schema": "rook.semantic_scalar:v1",
        "value": lexeme,
        "unit": "model_unit",
        "unit_context_ref": {
            "kind": "artifact_value",
            "artifact_id": "environment_snapshot",
            "json_pointer": "/document/unit_context",
        },
    }


def _unitless(
    schema: str,
    value: object,
    *,
    complete: bool,
) -> dict[str, object]:
    result = {"schema": schema, "value": value}
    if complete:
        result.update({"unit": None, "unit_context_ref": None})
    return result


def _validate_typed(
    value: dict[str, object],
    *,
    required_presence: str = "forward_fact",
    unit_context_index: object | None = None,
):
    return TYPED_VALUES.validate_typed_value(
        value,
        registry=_registry(),
        unit_context_index=(
            _unit_context_index()
            if unit_context_index is None
            else unit_context_index
        ),
        required_presence=required_presence,
        aggregate_budget=TYPED_VALUES.EvaluationBudget(),
        instance_path="/typed_value",
    )


def test_every_supported_typed_value_occurrence_preserves_exact_value() -> None:
    index = _unit_context_index()
    rows = (
        (
            "forward_fact",
            _unitless("rook.semantic_string:v1", "label", complete=True),
        ),
        (
            "forward_fact",
            _unitless("rook.semantic_integer:v1", 3, complete=True),
        ),
        (
            "forward_fact",
            _unitless("rook.semantic_boolean:v1", True, complete=True),
        ),
        ("forward_fact", _scalar("2")),
        (
            "recipe_assumption",
            _unitless("rook.semantic_string:v1", "label", complete=True),
        ),
        ("recipe_assumption", _scalar("2.5")),
        (
            "recipe_derived",
            _unitless("rook.semantic_string:v1", "label", complete=False),
        ),
        (
            "recipe_derived",
            _unitless("rook.semantic_integer:v1", 3, complete=False),
        ),
        (
            "recipe_derived",
            _unitless("rook.semantic_boolean:v1", False, complete=False),
        ),
    )

    for presence, value in rows:
        original = copy.deepcopy(value)
        verified = TYPED_VALUES.validate_typed_value(
            value,
            registry=_registry(),
            unit_context_index=index,
            required_presence=presence,
            aggregate_budget=TYPED_VALUES.EvaluationBudget(),
            instance_path="/typed_value",
        )
        expected_bytes = TYPED_VALUES.canonical_json_bytes(original)
        assert value == original
        assert verified.canonical_bytes == expected_bytes
        assert verified.fingerprint == TYPED_VALUES.sha256_prefixed(
            expected_bytes
        )
        assert json.loads(verified.canonical_bytes) == original


def test_two_field_scalar_is_not_a_valid_registered_scalar() -> None:
    with pytest.raises(ValueError, match="typed value failed"):
        _validate_typed(
            {"schema": "rook.semantic_scalar:v1", "value": "2"},
            required_presence="recipe_derived",
        )


def test_four_field_scalar_is_unreachable_as_current_recipe_derived_fact() -> None:
    scalar = _scalar("2")
    scalar_schema = _registry().entries["rook.semantic_scalar:v1"]
    assert TYPED_VALUES.validate_schema_instance(
        scalar,
        schema=scalar_schema,
        aggregate_budget=TYPED_VALUES.EvaluationBudget(),
        instance_path="/typed_value",
    ) == ()

    with pytest.raises(ValueError, match="occurrence fields"):
        _validate_typed(scalar, required_presence="recipe_derived")

    recipe_schema = json.loads(
        (
            SCRIPTS
            / "lm9b_p_fixtures"
            / "planner_recipe_probe_schema.json"
        ).read_bytes()
    )
    derived_value_schema = recipe_schema["properties"]["derived_facts"][
        "items"
    ]["properties"]["typed_value"]
    assert list(
        TYPED_VALUES.Draft202012Validator(
            derived_value_schema
        ).iter_errors(scalar)
    )


@pytest.mark.parametrize(
    "value",
    (
        _unitless("rook.semantic_string:v1", 1, complete=True),
        _unitless("rook.semantic_integer:v1", True, complete=True),
        _unitless(
            "rook.semantic_integer:v1",
            TYPED_VALUES.MAX_SAFE_INTEGER + 1,
            complete=True,
        ),
        _unitless("rook.semantic_unknown:v1", "x", complete=True),
        {
            **_unitless("rook.semantic_string:v1", "x", complete=True),
            "extra": True,
        },
        {
            **_unitless("rook.semantic_string:v1", "x", complete=True),
            "unit": "model_unit",
        },
        {
            "schema": "rook.semantic_string:v1",
            "value": "x",
            "unit": None,
        },
    ),
)
def test_typed_value_refuses_type_discriminator_and_presence_mutations(
    value: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        _validate_typed(value)


@pytest.mark.parametrize(
    "lexeme",
    ("-0", "2.0", "2.50", "02", "+2", ".5", "2.", "1e3", " 2"),
)
def test_scalar_rejects_noncanonical_lexemes(lexeme: str) -> None:
    with pytest.raises(ValueError):
        _validate_typed(_scalar(lexeme))


@pytest.mark.parametrize("lexeme", ("0", "2", "-2", "0.5", "-0.5", "2.5"))
def test_scalar_accepts_canonical_lexemes(lexeme: str) -> None:
    assert _validate_typed(_scalar(lexeme)).value["value"] == lexeme


def test_scalar_lexeme_accepts_1024_characters_and_refuses_1025() -> None:
    accepted = "1" * 1_024
    refused = "1" * 1_025

    assert _validate_typed(_scalar(accepted)).value["value"] == accepted
    with pytest.raises(ValueError):
        _validate_typed(_scalar(refused))


def _reclose_environment(environment: dict[str, object]) -> None:
    environment["artifact_fingerprint"] = TYPED_VALUES.fingerprint_without(
        environment, "artifact_fingerprint"
    )


def _reclose_attempt(attempt: dict[str, object]) -> None:
    attempt["context_fingerprint"] = TYPED_VALUES.fingerprint_without(
        attempt, "context_fingerprint"
    )


def _mutated_unit_context_inputs(case: str) -> dict[str, object]:
    inputs = dict(_valid_frozen_unit_context_inputs())
    environment = json.loads(inputs["environment_artifact_bytes"])
    payload_schema = json.loads(inputs["environment_payload_schema_bytes"])
    attempt = json.loads(inputs["attempt_context_bytes"])

    if case == "wrong_artifact_fingerprint":
        inputs["expected_artifact_fingerprint"] = "sha256:" + "0" * 64
        return inputs
    if case == "payload_schema_id":
        environment["payload_schema"] = "rook.environment_payload:other"
    elif case == "payload_schema_fingerprint":
        environment["payload_schema_fingerprint"] = "sha256:" + "0" * 64
    elif case == "reclosed_payload_schema":
        payload_schema["minProperties"] = 0
        environment["payload_schema_fingerprint"] = TYPED_VALUES.fingerprint(
            payload_schema
        )
    elif case == "environment_session":
        environment["environment_session_id"] = "other-environment-session"
    elif case == "task_session":
        attempt["task_session_id"] = "other-task-session"
    elif case == "issuer":
        environment["issuer"]["kind"] = "untrusted_fixture"
    elif case == "empty_issuer_id":
        environment["issuer"]["authority_id"] = ""
    elif case == "wrong_nonempty_issuer_id":
        environment["issuer"]["authority_id"] = "alternate-environment-gateway"
    elif case == "extra_issuer_field":
        environment["issuer"]["extra"] = True
    elif case == "stale_observation":
        environment["expires_at"] = inputs["evaluated_at"]
    elif case == "future_observation":
        environment["observed_at"] = "2026-07-20T11:30:00Z"
    elif case == "duplicate_binding":
        environment["value_bindings"].append(
            copy.deepcopy(environment["value_bindings"][0])
        )
    elif case == "missing_binding":
        environment["value_bindings"] = []
    elif case == "wrong_pointer":
        environment["value_bindings"][0]["json_pointer"] = "/document/other"
    elif case == "wrong_schema":
        environment["value_bindings"][0]["value_schema"] = (
            "rook.semantic_string:v1"
        )
    elif case == "wrong_typed_value_fingerprint":
        environment["value_bindings"][0]["typed_value_fingerprint"] = (
            "sha256:" + "0" * 64
        )
    elif case == "extra_artifact_field":
        environment["extra"] = True
    elif case == "extra_attempt_field":
        attempt["extra"] = True
    elif case == "attempt_schema":
        attempt["schema"] = "rook.attempt_context:other"
    else:
        raise AssertionError(f"unknown mutation case: {case}")

    _reclose_environment(environment)
    _reclose_attempt(attempt)
    inputs["environment_artifact_bytes"] = (
        TYPED_VALUES.canonical_json_bytes(environment) + b"\n"
    )
    inputs["environment_payload_schema_bytes"] = (
        TYPED_VALUES.canonical_json_bytes(payload_schema) + b"\n"
    )
    inputs["attempt_context_bytes"] = (
        TYPED_VALUES.canonical_json_bytes(attempt) + b"\n"
    )
    inputs["expected_artifact_fingerprint"] = environment[
        "artifact_fingerprint"
    ]
    return inputs


@pytest.mark.parametrize(
    ("case", "expected"),
    (
        ("wrong_artifact_fingerprint", "artifact fingerprint"),
        ("payload_schema_id", "payload schema"),
        ("payload_schema_fingerprint", "payload schema"),
        ("reclosed_payload_schema", "payload schema"),
        ("environment_session", "artifact identity"),
        ("task_session", "attempt context authority"),
        ("issuer", "issuer"),
        ("empty_issuer_id", "issuer"),
        ("wrong_nonempty_issuer_id", "issuer identity"),
        ("extra_issuer_field", "issuer"),
        ("stale_observation", "stale"),
        ("future_observation", "stale"),
        ("duplicate_binding", "binding"),
        ("missing_binding", "binding"),
        ("wrong_pointer", "binding identity"),
        ("wrong_schema", "binding identity"),
        ("wrong_typed_value_fingerprint", "fingerprint"),
        ("extra_artifact_field", "artifact shape"),
        ("extra_attempt_field", "attempt context shape"),
        ("attempt_schema", "attempt context authority"),
    ),
)
def test_unit_context_derivation_refuses_authority_mutations(
    case: str,
    expected: str,
) -> None:
    with pytest.raises(ValueError, match=expected):
        TYPED_VALUES.derive_verified_unit_context_index(
            **_mutated_unit_context_inputs(case)
        )


def test_unit_context_index_exposes_sealed_evaluation_time() -> None:
    index = _unit_context_index()
    assert index.evaluated_at == _valid_frozen_unit_context_inputs()[
        "evaluated_at"
    ]


def test_scalar_rejects_caller_authored_authority_dictionary() -> None:
    with pytest.raises(TypeError, match="VerifiedUnitContextIndex"):
        _validate_typed(
            _scalar("2"),
            unit_context_index={
                ("environment_snapshot", "/document/unit_context"): {
                    "fresh": True
                }
            },
        )


def test_scalar_requires_a_verified_unit_context_index() -> None:
    with pytest.raises(ValueError, match="requires verified"):
        TYPED_VALUES.validate_typed_value(
            _scalar("2"),
            registry=_registry(),
            unit_context_index=None,
            required_presence="forward_fact",
            aggregate_budget=TYPED_VALUES.EvaluationBudget(),
            instance_path="/typed_value",
        )


def test_exact_unit_context_class_cannot_be_constructed_publicly() -> None:
    with pytest.raises(TypeError, match="module-issued"):
        TYPED_VALUES.VerifiedUnitContextIndex()


def test_unit_context_carrier_is_final_and_copy_is_identity() -> None:
    with pytest.raises(TypeError):

        class Forged(TYPED_VALUES.VerifiedUnitContextIndex):
            pass

    issued = _unit_context_index()
    assert copy.copy(issued) is issued
    assert copy.deepcopy(issued) is issued
    with pytest.raises(TypeError):
        dataclasses.replace(issued)


def _copy_unit_context_slots(source: object, target: object) -> None:
    for slot in ("__snapshot", "__entries", "__proof_fingerprint"):
        private = f"_VerifiedUnitContextIndex{slot}"
        object.__setattr__(target, private, object.__getattribute__(source, private))


def _manually_allocate_exact_class_clone(source: object):
    clone = object.__new__(TYPED_VALUES.VerifiedUnitContextIndex)
    _copy_unit_context_slots(source, clone)
    return clone


def test_exact_slot_clone_has_no_module_authority_seal() -> None:
    cloned = _manually_allocate_exact_class_clone(_unit_context_index())
    with pytest.raises(ValueError, match="was not issued"):
        _validate_typed(_scalar("2"), unit_context_index=cloned)


def _assert_closed_unit_context_minting_surface() -> None:
    allowed = {
        "derive_verified_unit_context_index",
        "_consume_unit_context_index",
    }
    carrier_functions: set[str] = set()
    for name, value in vars(TYPED_VALUES).items():
        if not inspect.isfunction(value):
            continue
        signature = inspect.signature(value)
        if signature.return_annotation in {
            "VerifiedUnitContextIndex",
            TYPED_VALUES.VerifiedUnitContextIndex,
        }:
            carrier_functions.add(name)
        assert "seal" not in signature.parameters
        assert "register" not in signature.parameters
    assert carrier_functions == allowed


def _assert_single_post_validation_registry_insertion() -> None:
    tree = ast.parse(
        (SCRIPTS / "lm9_semantic_typed_values.py").read_text(
            encoding="utf-8"
        )
    )
    factory = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_build_unit_context_authority_gate"
    )
    derive = next(
        node
        for node in factory.body
        if isinstance(node, ast.FunctionDef) and node.name == "derive"
    )
    assignments = [
        node
        for node in ast.walk(derive)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Name)
            and target.value.id == "issued"
            for target in node.targets
        )
    ]
    validations = [
        node
        for node in ast.walk(derive)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_validate_and_derive_unit_context_authority"
    ]
    assert len(assignments) == 1
    assert len(validations) == 1
    assert validations[0].lineno < assignments[0].lineno


def test_module_exposes_no_raw_unit_context_minting_capability() -> None:
    assert not hasattr(TYPED_VALUES, "_issue_unit_context_index")
    assert not hasattr(TYPED_VALUES, "AuthoritySeal")
    assert not hasattr(TYPED_VALUES, "_UnitContextAuthoritySeal")
    assert not hasattr(TYPED_VALUES, "_build_unit_context_authority_gate")
    _assert_closed_unit_context_minting_surface()
    _assert_single_post_validation_registry_insertion()
    with pytest.raises(TypeError):
        TYPED_VALUES.derive_verified_unit_context_index(
            **_valid_frozen_unit_context_inputs(),
            seal=object(),
        )


def _alternate_valid_unit_context_index():
    inputs = dict(_valid_frozen_unit_context_inputs())
    attempt = json.loads(inputs["attempt_context_bytes"])
    attempt["attempt_id"] = "alternate-unit-context-attempt"
    _reclose_attempt(attempt)
    inputs["attempt_context_bytes"] = (
        TYPED_VALUES.canonical_json_bytes(attempt) + b"\n"
    )
    return TYPED_VALUES.derive_verified_unit_context_index(**inputs)


def test_fully_reclosed_actual_issued_object_disagrees_with_external_seal() -> None:
    issued = _unit_context_index()
    alternate = _alternate_valid_unit_context_index()
    assert not hasattr(issued, "_VerifiedUnitContextIndex__consume")
    _copy_unit_context_slots(alternate, issued)

    with pytest.raises(ValueError, match="proof projection"):
        _validate_typed(_scalar("2"), unit_context_index=issued)


def test_actual_issued_entry_mutation_fails_authority_reconstruction() -> None:
    issued = _unit_context_index()
    entry = next(iter(issued.entries.values()))
    object.__setattr__(entry, "expires_at", "2026-07-20T13:00:00Z")

    with pytest.raises(ValueError, match="authority reconstruction"):
        _validate_typed(_scalar("2"), unit_context_index=issued)


@pytest.mark.parametrize(
    "mutation",
    ("entries", "proof_fingerprint", "snapshot"),
)
def test_consumption_rederives_opaque_carrier(mutation: str) -> None:
    clone = _manually_allocate_exact_class_clone(_unit_context_index())
    private = f"_VerifiedUnitContextIndex__{mutation}"
    object.__setattr__(clone, private, None)

    with pytest.raises(ValueError, match="unit-context proof"):
        _validate_typed(_scalar("2"), unit_context_index=clone)
