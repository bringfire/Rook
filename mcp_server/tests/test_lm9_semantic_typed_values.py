from __future__ import annotations

import copy
import importlib
import importlib.util
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
