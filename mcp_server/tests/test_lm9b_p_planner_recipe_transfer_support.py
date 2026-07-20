from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "scripts" / "lm9b_p_fixtures"


def _load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SUPPORT = _load_script("lm9b_p_planner_recipe_transfer_support")


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (b'{"a":1,"a":2}', "duplicate_key"),
        (b"\xef\xbb\xbf{}", "utf8_bom"),
        (b'{"a":\xff}', "invalid_utf8"),
        (b'{"n":' + b"1" * 1025 + b"}", "integer_token_too_long"),
        (b'{"n":1e10000}', "non_integer_json_number"),
        (b'{"n":1.5}', "non_integer_json_number"),
        (b'{"n":NaN}', "non_finite_json_number"),
    ],
)
def test_strict_parser_rejects_declared_input(raw: bytes, code: str) -> None:
    with pytest.raises(SUPPORT.StrictJsonError, match=code):
        SUPPORT.parse_strict_json(raw)


def test_strict_parser_rejects_depth_65() -> None:
    raw = ("[" * 65 + "0" + "]" * 65).encode("ascii")
    with pytest.raises(SUPPORT.StrictJsonError, match="json_depth_exceeded"):
        SUPPORT.parse_strict_json(raw)


def test_normalization_profile_is_the_complete_reviewed_inventory() -> None:
    profile = SUPPORT.load_normalization_profile(
        FIXTURES / "recipe_normalization_profile.json"
    )
    assert profile.profile_id == "lm9b_p.recipe_normalization_profile:v1"
    assert len(profile.rows) == 32
    names = {row.path_pattern for row in profile.rows}
    assert any("applies_to_clause_ids" in item for item in names)
    assert any("inherited_support_from" in item for item in names)
    assert any("affected_clause_ids" in item for item in names)
    assert sum("policy_refs" in item for item in names) == 2


def _normalization_subject(row):
    if row.sort_kind == "field":
        return [{row.field: "z"}, {row.field: "a"}]
    if row.sort_kind == "scalar_utf16":
        return ["z", "a"]
    if row.sort_kind == "semantic_reference":
        return [
            {"kind": "assumption", "assumption_id": "z"},
            {"kind": "assumption", "assumption_id": "a"},
        ]
    raise AssertionError(row.sort_kind)


def _document_at_pattern(pattern: str, items: list[object]) -> dict[str, object]:
    parts = [part for part in pattern.split("/") if part]
    parts = ["semantic" if part == "**" else "0" if part == "*" else part for part in parts]
    root: dict[str, object] = {}
    current: object = root
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        next_is_index = not last and parts[index + 1].isdigit()
        if isinstance(current, dict):
            current[part] = items if last else ([] if next_is_index else {})
            current = current[part]
        else:
            assert isinstance(current, list)
            while len(current) <= int(part):
                current.append({})
            current[int(part)] = items if last else ([] if next_is_index else {})
            current = current[int(part)]
    return root


@pytest.mark.parametrize(
    "row",
    SUPPORT.load_normalization_profile(
        FIXTURES / "recipe_normalization_profile.json"
    ).rows,
    ids=lambda row: row.path_pattern,
)
def test_every_normalization_row_has_a_movement_or_empty_only_proof(row) -> None:
    profile = SUPPORT.NormalizationProfile(
        profile_id="test.single_row:v1",
        profile_fingerprint="sha256:" + "0" * 64,
        rows=(replace(row, matching="required_container"),),
    )
    if row.admission == "empty_only":
        empty = _document_at_pattern(row.path_pattern, [])
        assert SUPPORT.normalize_recipe(empty, profile) == empty
        with pytest.raises(ValueError, match="profile feature not admitted"):
            SUPPORT.normalize_recipe(
                _document_at_pattern(row.path_pattern, _normalization_subject(row)),
                profile,
            )
        return

    reversed_document = _document_at_pattern(
        row.path_pattern, _normalization_subject(row)
    )
    ordered_document = _document_at_pattern(
        row.path_pattern, list(reversed(_normalization_subject(row)))
    )
    assert SUPPORT.fingerprint(reversed_document) != SUPPORT.fingerprint(ordered_document)
    assert SUPPORT.normalize_recipe(reversed_document, profile) == SUPPORT.normalize_recipe(
        ordered_document, profile
    )


def test_ratified_assumption_and_derived_references_are_discriminated_objects() -> None:
    recipe = json.loads(
        (ROOT / "mcp_server/tests/fixtures/lm9b_p/non_r01_ready_recipe.json").read_bytes()
    )
    for path, value in SUPPORT._walk(recipe):
        if path.endswith("/assumption_refs"):
            assert all(
                set(item) == {"kind", "assumption_id"}
                and item["kind"] == "assumption"
                for item in value
            )
        if path.endswith("/derived_fact_refs"):
            assert all(
                set(item) == {"kind", "derived_fact_id"}
                and item["kind"] == "derived_fact"
                for item in value
            )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("assumption_refs", "assumption.stale"),
        ("derived_fact_refs", "derived.stale"),
    ],
)
def test_probe_schema_rejects_bare_string_semantic_references(
    field: str, value: str
) -> None:
    from jsonschema import Draft202012Validator

    schema = json.loads((FIXTURES / "planner_recipe_probe_schema.json").read_bytes())
    recipe = json.loads(
        (ROOT / "mcp_server/tests/fixtures/lm9b_p/non_r01_ready_recipe.json").read_bytes()
    )
    recipe["maintains"][0][field] = [value]
    assert list(Draft202012Validator(schema).iter_errors(recipe))


def test_exact_vocabulary_companions_are_complete_and_fingerprinted() -> None:
    expected = {
        "semantic_authority_code_vocabulary.json": (
            "rook.semantic_authority_code_vocabulary:v1",
            {
                "select_representation",
                "construct_topology",
                "lower_verification",
                "instantiate_worker_slot",
            },
        ),
        "semantic_capability_code_vocabulary.json": (
            "rook.semantic_capability_code_vocabulary:v1",
            {"construct_parametric_geometry", "manage_document_layers"},
        ),
        "worker_slot_code_vocabulary.json": (
            "rook.worker_slot_code_vocabulary:v1",
            {"author_formula_realization"},
        ),
        "semantic_materiality_code_vocabulary.json": (
            "rook.semantic_materiality_code_vocabulary:v1",
            {
                "tool_arguments",
                "geometry_state",
                "document_state",
                "target_identity",
                "topology",
                "execution_branching",
                "verifier_predicate",
                "verifier_threshold",
                "fingerprint",
                "canonicalization",
                "capability_authority",
                "mutation_authority",
            },
        ),
        "semantic_value_schema_registry.json": (
            "rook.semantic_value_schema_registry:v1",
            {
                "rook.semantic_integer:v1",
                "rook.semantic_scalar:v1",
                "rook.semantic_string:v1",
                "rook.semantic_boolean:v1",
                "rook.semantic_unit_context:v1",
            },
        ),
    }
    for filename, (schema, entries) in expected.items():
        value = json.loads((FIXTURES / filename).read_bytes())
        assert value["schema"] == schema
        keys = {item.get("code", item.get("schema")) for item in value["entries"]}
        assert keys == entries
        assert value["vocabulary_fingerprint"] == SUPPORT.fingerprint_without(
            value, "vocabulary_fingerprint"
        )


def test_vocabulary_entries_use_the_closed_ratified_shapes() -> None:
    expected_fields = {
        "semantic_authority_code_vocabulary.json": {
            "code",
            "allowed_shape_sections",
            "allowed_delegate_kinds",
            "requires_worker_slot",
        },
        "semantic_capability_code_vocabulary.json": {
            "code",
            "permitted_supporting_clause_kinds",
        },
        "worker_slot_code_vocabulary.json": {
            "code",
            "allowed_output_schemas",
            "allowed_input_kinds",
            "required_shape_authority_code",
        },
        "semantic_materiality_code_vocabulary.json": {"code"},
        "semantic_value_schema_registry.json": {"schema"},
    }
    for filename, fields in expected_fields.items():
        value = json.loads((FIXTURES / filename).read_bytes())
        assert all(set(entry) == fields for entry in value["entries"])

    authority = json.loads(
        (FIXTURES / "semantic_authority_code_vocabulary.json").read_bytes()
    )
    by_code = {entry["code"]: entry for entry in authority["entries"]}
    assert all(
        entry["allowed_delegate_kinds"] == ["compile_phase"]
        for entry in by_code.values()
    )
    assert by_code["instantiate_worker_slot"]["requires_worker_slot"] is True
    assert all(
        not entry["requires_worker_slot"]
        for code, entry in by_code.items()
        if code != "instantiate_worker_slot"
    )

    worker = json.loads((FIXTURES / "worker_slot_code_vocabulary.json").read_bytes())
    entry = worker["entries"][0]
    assert entry["allowed_output_schemas"] == ["rook.worker_formula_realization:v1"]
    assert set(entry["allowed_input_kinds"]) == {
        "artifact_value",
        "assumption",
        "clause",
        "derived_fact",
    }
    assert entry["required_shape_authority_code"] == "instantiate_worker_slot"
