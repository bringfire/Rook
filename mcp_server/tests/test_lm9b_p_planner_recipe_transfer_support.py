from __future__ import annotations

import copy
import importlib.util
import inspect
import json
import shutil
import sys
import threading
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
ARTIFACTS = _load_script("lm9b_p_planner_recipe_transfer_artifacts")
RECIPE_PATH = ROOT / "mcp_server/tests/fixtures/lm9b_p/non_r01_ready_recipe.json"
BLOCKED_RECIPE_PATH = (
    ROOT / "mcp_server/tests/fixtures/lm9b_p/non_r01_blocked_recipe.json"
)


def _authority():
    return ARTIFACTS.load_planner_authority_context(FIXTURES)


def _recipe() -> dict[str, object]:
    return json.loads(RECIPE_PATH.read_bytes())


def _bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _seal(value: dict[str, object]) -> dict[str, object]:
    value = copy.deepcopy(value)
    projection = {key: item for key, item in value.items() if key != "recipe_fingerprint"}
    normalized = SUPPORT.normalize_recipe(
        projection, _authority().normalization_profile
    )
    value["recipe_fingerprint"] = SUPPORT.fingerprint(normalized)
    return value


def _gate(raw: bytes):
    authority = _authority()
    return SUPPORT.evaluate_mechanical_gate(
        recipe_bytes=raw,
        authority=authority,
        recipe_schema=authority.recipe_schema,
        normalization_profile=authority.normalization_profile,
        exclusion_policy=authority.exclusion_policy,
    )


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
    assert (
        "/unresolved_intent/*/authorization_context_refs/policy_refs" in names
    )
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


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (b'{"schema":"\xff"}', "invalid_utf8"),
        (b'{"schema":', "invalid_json"),
        (b'{"schema":"a","schema":"b"}', "duplicate_key"),
        (b'{"n":' + b"1" * 1025 + b"}", "integer_token_too_long"),
        (b'{"n":1e10000}', "non_integer_json_number"),
        (b'{"n":1.5}', "non_integer_json_number"),
        (b'{"n":NaN}', "non_finite_json_number"),
    ],
)
def test_gate_rejects_invalid_physical_json(raw: bytes, code: str) -> None:
    result = _gate(raw)
    assert result.status == "probe_mechanically_rejected"
    assert [item.code for item in result.diagnostics] == [code]


def test_gate_rejects_missing_required_field() -> None:
    recipe = _recipe()
    del recipe["goal"]
    result = _gate(_bytes(recipe))
    assert result.status == "probe_mechanically_rejected"
    assert result.diagnostics[0].code == "recipe_schema_failed"


def test_gate_rejects_unknown_field() -> None:
    recipe = _recipe()
    recipe["unknown_probe_field"] = True
    result = _gate(_bytes(recipe))
    assert result.status == "probe_mechanically_rejected"
    assert result.diagnostics[0].code == "recipe_schema_failed"


def test_gate_rejects_unknown_artifact_reference() -> None:
    recipe = _recipe()
    recipe["goal"]["source_refs"][0]["artifact_id"] = "unknown_artifact"
    result = _gate(_bytes(recipe))
    assert result.diagnostics[0].code == "unknown_artifact"


def test_gate_rejects_missing_artifact_pointer() -> None:
    recipe = _recipe()
    recipe["goal"]["source_refs"][0]["json_pointer"] = "/facts/missing"
    result = _gate(_bytes(recipe))
    assert result.diagnostics[0].code == "artifact_pointer_unbound"


def test_gate_rejects_recipe_descriptor_artifact_hash_mismatch() -> None:
    recipe = _recipe()
    recipe["source_task"]["fingerprint"] = "sha256:" + "0" * 64
    result = _gate(_bytes(recipe))
    assert result.diagnostics[0].code == "authority_binding_failed"


def test_gate_rejects_vocabulary_fingerprint_mismatch() -> None:
    recipe = _recipe()
    recipe["shape"]["vocabulary_fingerprint"] = "sha256:" + "0" * 64
    result = _gate(_bytes(recipe))
    assert result.diagnostics[0].code == "vocabulary_binding_failed"


def test_gate_rejects_noncanonical_collection_order() -> None:
    recipe = _recipe()
    recipe["goal"]["source_refs"] = list(reversed(recipe["goal"]["source_refs"]))
    result = _gate(_bytes(recipe))
    assert result.diagnostics[0].code == "recipe_not_canonical_normal_form"


def test_gate_rejects_nonempty_worker_slots() -> None:
    recipe = _recipe()
    recipe["worker_slots"]["entries"] = [{"worker_slot_id": "worker.probe"}]
    result = _gate(_bytes(recipe))
    assert result.diagnostics[0].code == "recipe_schema_failed"


def test_gate_rejects_forbidden_control_marker_after_valid_fingerprinting() -> None:
    recipe = _recipe()
    recipe["goal"]["statement"] += " r01_recipe.json"
    result = _gate(_bytes(_seal(recipe)))
    assert result.diagnostics[0].code == "forbidden_context_marker"


def test_fingerprint_mismatch_is_the_only_resubmission_handshake() -> None:
    recipe = _recipe()
    recipe["recipe_fingerprint"] = "sha256:" + "0" * 64
    first = _gate(_bytes(recipe))
    assert first.status == "fingerprint_resubmission_required"
    assert first.diagnostics[0].path == "/recipe_fingerprint"
    assert first.diagnostics[0].message == first.ratified_recipe_fingerprint

    recipe["recipe_fingerprint"] = first.ratified_recipe_fingerprint
    submitted = _bytes(recipe)
    second = _gate(submitted)
    assert second.status == "mechanically_accepted"
    assert second.final_recipe_bytes == submitted


def test_gate_preserves_nonsemantic_json_encoding_of_accepted_submission() -> None:
    recipe = _recipe()
    submitted = (json.dumps(recipe, separators=(",", ":")) + "\n\n").encode("utf-8")
    result = _gate(submitted)
    assert result.status == "mechanically_accepted"
    assert result.final_recipe_bytes == submitted


def test_semantic_change_moves_computed_fingerprint_without_repair() -> None:
    recipe = _recipe()
    prior = recipe["recipe_fingerprint"]
    recipe["goal"]["statement"] += " Additional governed meaning."
    recipe["recipe_fingerprint"] = "sha256:" + "0" * 64
    result = _gate(_bytes(recipe))
    assert result.status == "fingerprint_resubmission_required"
    assert result.ratified_recipe_fingerprint != prior
    assert result.final_recipe_bytes is None


def test_noncanonical_order_cannot_be_cleared_by_supplying_normalized_hash() -> None:
    recipe = _recipe()
    recipe["goal"]["source_refs"] = list(reversed(recipe["goal"]["source_refs"]))
    normalized = SUPPORT.normalize_recipe(
        {key: item for key, item in recipe.items() if key != "recipe_fingerprint"},
        _authority().normalization_profile,
    )
    recipe["recipe_fingerprint"] = SUPPORT.fingerprint(normalized)
    result = _gate(_bytes(recipe))
    assert result.status == "probe_mechanically_rejected"
    assert result.diagnostics[0].code == "recipe_not_canonical_normal_form"


def test_gate_rejects_dangling_local_assumption_reference() -> None:
    recipe = _recipe()
    recipe["maintains"][0]["assumption_refs"][0][
        "assumption_id"
    ] = "assumption.missing"
    result = _gate(_bytes(_seal(recipe)))
    assert result.diagnostics[0].code == "dangling_local_reference"


def test_gate_rejects_local_reference_to_wrong_symbol_kind() -> None:
    recipe = _recipe()
    recipe["maintains"][0]["assumption_refs"][0]["assumption_id"] = recipe[
        "derived_facts"
    ][0]["derived_fact_id"]
    result = _gate(_bytes(_seal(recipe)))
    assert result.diagnostics[0].code == "dangling_local_reference"


def test_gate_rejects_duplicate_global_clause_identity() -> None:
    recipe = _recipe()
    recipe["requires"][0]["clause_id"] = recipe["maintains"][0]["clause_id"]
    result = _gate(_bytes(_seal(recipe)))
    assert result.diagnostics[0].code == "duplicate_identifier"


def test_gate_rejects_non_machine_identifier() -> None:
    # Language-visibility closure (M3): the identifier grammar is now a model-visible
    # schema carrier ($defs/machine_identifier), so a malformed identifier is rejected
    # earlier and more legibly at the schema. The gate's invalid_machine_identifier
    # check remains unchanged as defense-in-depth.
    recipe = _recipe()
    recipe["goal"]["clause_id"] = "goal contains spaces"
    result = _gate(_bytes(_seal(recipe)))
    assert result.diagnostics[0].code == "recipe_schema_failed"


@pytest.mark.parametrize(
    ("section", "code_field"),
    [
        ("shape", "authority_code"),
        ("required_capabilities", "capability_code"),
    ],
)
def test_gate_rejects_unknown_vocabulary_entry(
    section: str, code_field: str
) -> None:
    recipe = _recipe()
    entries = (
        recipe[section]["delegates"]
        if section == "shape"
        else recipe[section]["entries"]
    )
    entries[0][code_field] = "unknown_probe_code"
    result = _gate(_bytes(_seal(recipe)))
    assert result.diagnostics[0].code == "unknown_vocabulary_code"


def test_gate_rejects_policy_pointer_outside_rules_map() -> None:
    # Language-visibility closure (M4): the policy json_pointer grammar is now a
    # model-visible schema carrier (pattern ^/rules/<id>$), so a pointer outside the
    # rules map is rejected at the schema. The gate's policy_pointer_outside_rules
    # check remains unchanged as defense-in-depth.
    recipe = _recipe()
    recipe["assumptions"][0]["authorization_refs"]["policy_refs"][0][
        "json_pointer"
    ] = "/issuer/kind"
    result = _gate(_bytes(_seal(recipe)))
    assert result.diagnostics[0].code == "recipe_schema_failed"


def test_gate_rejects_policy_pointer_below_rule_object() -> None:
    # Language-visibility closure (M4): a pointer that reaches below a rule object
    # violates the model-visible ^/rules/<id>$ pattern and is rejected at the schema.
    recipe = _recipe()
    pointer = recipe["assumptions"][0]["authorization_refs"]["policy_refs"][0][
        "json_pointer"
    ]
    recipe["assumptions"][0]["authorization_refs"]["policy_refs"][0][
        "json_pointer"
    ] = pointer + "/effect"
    result = _gate(_bytes(_seal(recipe)))
    assert result.diagnostics[0].code == "recipe_schema_failed"


def test_gate_rejects_reference_to_undeclared_authority_companion() -> None:
    recipe = _recipe()
    recipe["authority_artifacts"] = [
        item
        for item in recipe["authority_artifacts"]
        if item["artifact_id"] != "planning_policy"
    ]
    result = _gate(_bytes(_seal(recipe)))
    assert result.diagnostics[0].code == "authority_descriptor_unbound"


def test_gate_rejects_unused_authority_descriptor() -> None:
    recipe = _recipe()
    recipe["requires"] = []
    for assumption in recipe["assumptions"]:
        assumption["typed_value"]["unit_context_ref"] = None
    result = _gate(_bytes(_seal(recipe)))
    assert result.diagnostics[0].code == "unreferenced_authority_descriptor"


def test_closed_unresolved_fixture_is_mechanically_admitted() -> None:
    raw = BLOCKED_RECIPE_PATH.read_bytes()
    recipe = json.loads(raw)
    assert recipe["unresolved_intent"]
    assert not any(
        item["semantic_key"] == "grid_spacing" for item in recipe["assumptions"]
    )
    result = _gate(raw)
    assert result.status == "mechanically_accepted"
    assert result.final_recipe_bytes == raw


def test_gate_rejects_dangling_unresolved_affected_clause() -> None:
    recipe = json.loads(BLOCKED_RECIPE_PATH.read_bytes())
    recipe["unresolved_intent"][0]["affected_clause_ids"] = ["goal.missing"]
    result = _gate(_bytes(_seal(recipe)))
    assert result.diagnostics[0].code == "dangling_local_reference"


def test_unresolved_affected_clause_cannot_target_an_assumption_namespace() -> None:
    recipe = json.loads(BLOCKED_RECIPE_PATH.read_bytes())
    recipe["unresolved_intent"][0]["affected_clause_ids"] = [
        recipe["assumptions"][0]["assumption_id"]
    ]
    result = _gate(_bytes(_seal(recipe)))
    assert result.diagnostics[0].code == "dangling_local_reference"


def test_unresolved_value_schema_must_be_registered() -> None:
    recipe = json.loads(BLOCKED_RECIPE_PATH.read_bytes())
    recipe["unresolved_intent"][0]["value_schema"] = "rook.unknown_value:v1"
    result = _gate(_bytes(_seal(recipe)))
    assert result.diagnostics[0].code == "unknown_value_schema"


def test_closed_invariant_contract_is_mechanically_admitted() -> None:
    recipe = _recipe()
    invariant_id = "probe.invariant.task.scope"
    recipe["invariants"] = [
        {
            "clause_id": invariant_id,
            "statement": "All paths preserve the supplied task scope.",
            "source_refs": [
                {
                    "kind": "artifact_value",
                    "artifact_id": "task_envelope",
                    "json_pointer": "/facts/task_scope",
                }
            ],
            "assumption_refs": [],
            "derived_fact_refs": [],
            "synthesis": None,
        }
    ]
    recipe["goal"]["projected_into"]["invariant_clause_ids"] = [invariant_id]
    result = _gate(_bytes(_seal(recipe)))
    assert result.status == "mechanically_accepted"


CLAUSE_SOURCE_KINDS = (
    "goal",
    "requires",
    "maintains",
    "canonicalization",
    "postcondition",
    "invariant",
)
CLAUSE_SYNTHESIS_CODES = {
    "goal": "planner_goal_synthesis",
    "requires": "planner_requirement_synthesis",
    "maintains": "planner_semantic_synthesis",
    "canonicalization": "planner_semantic_classification",
    "postcondition": "planner_postcondition_projection",
    "invariant": "planner_invariant_projection",
}


def _set_clause_source(
    recipe: dict[str, object], clause_kind: str, reference: dict[str, str]
) -> None:
    if clause_kind == "goal":
        recipe["goal"]["source_refs"] = [reference]
    elif clause_kind == "requires":
        recipe["requires"][0]["source_refs"] = [reference]
    elif clause_kind == "maintains":
        recipe["maintains"][0]["source_refs"] = [reference]
    elif clause_kind == "canonicalization":
        recipe["maintains"][0]["canonicalization"][0]["source_refs"] = [
            reference
        ]
    elif clause_kind == "postcondition":
        recipe["maintains"][0]["postconditions"][0]["source_refs"] = [
            reference
        ]
    else:
        invariant_id = "probe.invariant.task.scope"
        recipe["invariants"] = [
            {
                "clause_id": invariant_id,
                "statement": "All paths preserve the supplied task scope.",
                "source_refs": [reference],
                "assumption_refs": [],
                "derived_fact_refs": [],
                "synthesis": None,
            }
        ]
        recipe["goal"]["projected_into"]["invariant_clause_ids"] = [
            invariant_id
        ]


def _set_clause_synthesis(
    recipe: dict[str, object], clause_kind: str, synthesis_kind: str
) -> None:
    if clause_kind == "goal":
        clause = recipe["goal"]
    elif clause_kind == "requires":
        clause = recipe["requires"][0]
    elif clause_kind == "maintains":
        clause = recipe["maintains"][0]
    elif clause_kind == "canonicalization":
        clause = recipe["maintains"][0]["canonicalization"][0]
    elif clause_kind == "postcondition":
        clause = recipe["maintains"][0]["postconditions"][0]
    else:
        invariant_id = "probe.invariant.task.scope"
        recipe["invariants"] = [
            {
                "clause_id": invariant_id,
                "statement": "All paths preserve the supplied task scope.",
                "source_refs": [],
                "assumption_refs": [],
                "derived_fact_refs": [],
                "synthesis": None,
            }
        ]
        recipe["goal"]["projected_into"]["invariant_clause_ids"] = [
            invariant_id
        ]
        clause = recipe["invariants"][0]
    clause["synthesis"] = {"kind": synthesis_kind}


def _clause_for_kind(recipe: dict[str, object], clause_kind: str) -> dict[str, object]:
    if clause_kind == "goal":
        return recipe["goal"]
    if clause_kind == "requires":
        return recipe["requires"][0]
    if clause_kind == "maintains":
        return recipe["maintains"][0]
    if clause_kind == "canonicalization":
        return recipe["maintains"][0]["canonicalization"][0]
    if clause_kind == "postcondition":
        return recipe["maintains"][0]["postconditions"][0]
    invariant_id = "probe.invariant.task.scope"
    recipe["invariants"] = [
        {
            "clause_id": invariant_id,
            "statement": "All paths preserve the supplied task scope.",
            "source_refs": [],
            "assumption_refs": [],
            "derived_fact_refs": [],
            "synthesis": None,
        }
    ]
    recipe["goal"]["projected_into"]["invariant_clause_ids"] = [invariant_id]
    return recipe["invariants"][0]


@pytest.mark.parametrize("clause_kind", CLAUSE_SOURCE_KINDS)
def test_artifact_value_is_reachable_as_every_clause_source_kind(
    clause_kind: str,
) -> None:
    recipe = _recipe()
    _set_clause_source(
        recipe,
        clause_kind,
        {
            "kind": "artifact_value",
            "artifact_id": "task_envelope",
            "json_pointer": "/facts/task_scope",
        },
    )
    result = _gate(_bytes(_seal(recipe)))
    assert result.status == "mechanically_accepted"


@pytest.mark.parametrize(
    "clause_kind",
    CLAUSE_SOURCE_KINDS,
)
def test_policy_rule_cannot_masquerade_as_clause_source_truth(
    clause_kind: str,
) -> None:
    recipe = _recipe()
    policy_ref = {
        "kind": "policy_rule",
        "artifact_id": "planning_policy",
        "json_pointer": "/rules/rule.grid_spacing",
    }
    _set_clause_source(recipe, clause_kind, policy_ref)
    result = _gate(_bytes(_seal(recipe)))
    assert result.diagnostics[0].code == "recipe_schema_failed"


@pytest.mark.parametrize("clause_kind", CLAUSE_SOURCE_KINDS)
def test_clause_synthesis_uses_its_ratified_kind(clause_kind: str) -> None:
    recipe = _recipe()
    _set_clause_synthesis(
        recipe, clause_kind, CLAUSE_SYNTHESIS_CODES[clause_kind]
    )
    assert _gate(_bytes(_seal(recipe))).status == "mechanically_accepted"

    wrong_kind = (
        "planner_invariant_projection"
        if clause_kind != "invariant"
        else "planner_goal_synthesis"
    )
    _set_clause_synthesis(recipe, clause_kind, wrong_kind)
    result = _gate(_bytes(_seal(recipe)))
    assert result.diagnostics[0].code == "recipe_schema_failed"


@pytest.mark.parametrize("clause_kind", CLAUSE_SOURCE_KINDS)
def test_clause_requires_direct_support_or_synthesis(clause_kind: str) -> None:
    recipe = _recipe()
    clause = _clause_for_kind(recipe, clause_kind)
    clause["source_refs"] = []
    clause["assumption_refs"] = []
    if "derived_fact_refs" in clause:
        clause["derived_fact_refs"] = []
    clause["synthesis"] = None
    result = _gate(_bytes(_seal(recipe)))
    assert result.diagnostics[0].code == "clause_support_missing"

    clause["synthesis"] = {"kind": CLAUSE_SYNTHESIS_CODES[clause_kind]}
    assert _gate(_bytes(_seal(recipe))).status == "mechanically_accepted"


def _append_sibling_maintains(recipe: dict[str, object]) -> str:
    sibling_id = "probe.maintained.sibling"
    recipe["maintains"].append(
        {
            "clause_id": sibling_id,
            "statement": "A sibling maintained result remains independently scoped.",
            "source_refs": [
                {
                    "kind": "artifact_value",
                    "artifact_id": "task_envelope",
                    "json_pointer": "/facts/task_scope",
                }
            ],
            "derived_fact_refs": [],
            "assumption_refs": [],
            "synthesis": None,
            "canonicalization": [],
            "postconditions": [],
        }
    )
    return sibling_id


@pytest.mark.parametrize(
    "relationship",
    (
        "canonicalization_applies_to",
        "canonicalization_inherits_from",
        "canonicalization_inherits_missing",
        "postcondition_inherits_from",
    ),
)
def test_nested_clause_relationships_bind_the_containing_parent(
    relationship: str,
) -> None:
    recipe = _recipe()
    sibling_id = _append_sibling_maintains(recipe)
    parent = recipe["maintains"][0]
    if relationship == "canonicalization_applies_to":
        parent["canonicalization"][0]["applies_to_clause_ids"] = [sibling_id]
    elif relationship == "canonicalization_inherits_from":
        parent["canonicalization"][0]["inherited_support_from"] = [sibling_id]
    elif relationship == "canonicalization_inherits_missing":
        parent["canonicalization"][0]["inherited_support_from"] = [
            "probe.maintained.missing"
        ]
    else:
        parent["postconditions"][0]["inherited_support_from"] = [sibling_id]
    result = _gate(_bytes(_seal(recipe)))
    assert result.diagnostics[0].code == "nested_parent_mismatch"


def test_nested_clause_may_decline_parent_support_inheritance() -> None:
    recipe = _recipe()
    parent = recipe["maintains"][0]
    parent["canonicalization"][0]["inherited_support_from"] = []
    parent["postconditions"][0]["inherited_support_from"] = []
    assert _gate(_bytes(_seal(recipe))).status == "mechanically_accepted"


def test_derived_fact_operator_is_closed_for_the_probe_profile() -> None:
    recipe = _recipe()
    recipe["derived_facts"][0]["derivation"]["operator"] = "invented_operator"
    result = _gate(_bytes(_seal(recipe)))
    assert result.diagnostics[0].code == "recipe_schema_failed"


@pytest.mark.parametrize(
    "authority_role",
    (
        "assumption_unit_context",
        "assumption_policy_context",
        "derived_fact_input",
        "unresolved_policy_context",
        "unresolved_unit_context",
    ),
)
def test_authority_reference_kinds_are_field_specific(authority_role: str) -> None:
    recipe = (
        json.loads(BLOCKED_RECIPE_PATH.read_bytes())
        if authority_role.startswith("unresolved_")
        else _recipe()
    )
    policy_ref = {
        "kind": "policy_rule",
        "artifact_id": "planning_policy",
        "json_pointer": "/rules/rule.grid_spacing",
    }
    artifact_ref = {
        "kind": "artifact_value",
        "artifact_id": "task_envelope",
        "json_pointer": "/facts/task_scope",
    }
    if authority_role == "assumption_unit_context":
        recipe["assumptions"][1]["typed_value"]["unit_context_ref"] = policy_ref
    elif authority_role == "assumption_policy_context":
        recipe["assumptions"][0]["authorization_refs"]["policy_refs"] = [
            artifact_ref
        ]
    elif authority_role == "derived_fact_input":
        recipe["derived_facts"][0]["derivation"]["input_refs"] = [policy_ref]
    elif authority_role == "unresolved_policy_context":
        recipe["unresolved_intent"][0]["authorization_context_refs"][
            "policy_refs"
        ] = [artifact_ref]
    else:
        recipe["unresolved_intent"][0]["unit_context_ref"] = policy_ref
    result = _gate(_bytes(_seal(recipe)))
    assert result.diagnostics[0].code == "recipe_schema_failed"


@pytest.mark.parametrize(
    ("kind", "id_field", "target"),
    (
        ("clause", "clause_id", "probe.goal.radial_box_field"),
        (
            "assumption",
            "assumption_id",
            "probe.assumption.array_center_definition",
        ),
        ("derived_fact", "derived_fact_id", "probe.derived.element_count"),
        (
            "shape",
            "shape_id",
            "probe.shape.delegate.representation",
        ),
        (
            "capability",
            "capability_id",
            "probe.capability.construct_parametric_geometry",
        ),
    ),
)
def test_assumption_basis_admits_ratified_local_reference_variants(
    kind: str, id_field: str, target: str
) -> None:
    recipe = _recipe()
    recipe["assumptions"][0]["basis_refs"] = [
        {"kind": kind, id_field: target}
    ]
    result = _gate(_bytes(_seal(recipe)))
    assert result.status == "mechanically_accepted"


def test_same_machine_identifier_is_allowed_in_distinct_symbol_namespaces() -> None:
    recipe = _recipe()
    old_id = recipe["assumptions"][0]["assumption_id"]
    shared_id = recipe["goal"]["clause_id"]
    recipe["assumptions"][0]["assumption_id"] = shared_id
    for _path, current in SUPPORT._walk(recipe):
        if isinstance(current, dict) and current.get("kind") == "assumption":
            if current["assumption_id"] == old_id:
                current["assumption_id"] = shared_id
    projection = {
        key: item for key, item in recipe.items() if key != "recipe_fingerprint"
    }
    canonical = SUPPORT.normalize_recipe(
        projection, _authority().normalization_profile
    )
    canonical["recipe_fingerprint"] = SUPPORT.fingerprint(canonical)
    result = _gate(_bytes(canonical))
    assert result.status == "mechanically_accepted"


def test_content_addressed_exclusion_policy_moves_gate_and_request(
    tmp_path: Path,
) -> None:
    original_inputs = ARTIFACTS.load_planner_inputs(FIXTURES)
    recipe_bytes = RECIPE_PATH.read_bytes()
    original_gate = SUPPORT.evaluate_mechanical_gate(
        recipe_bytes=recipe_bytes,
        authority=original_inputs.authority,
        recipe_schema=original_inputs.recipe_schema,
        normalization_profile=original_inputs.authority.normalization_profile,
        exclusion_policy=original_inputs.exclusion_policy,
    )
    assert original_gate.status == "mechanically_accepted"

    copied = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, copied)
    policy_path = copied / "planner_exclusion_policy.json"
    policy = json.loads(policy_path.read_bytes())
    policy["forbidden_recipe_markers"].append("probe.goal.radial_box_field")
    policy["forbidden_recipe_markers"].sort()
    policy["policy_fingerprint"] = SUPPORT.fingerprint_without(
        policy, "policy_fingerprint"
    )
    policy_path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    changed_inputs = ARTIFACTS.load_planner_inputs(copied)
    changed_gate = SUPPORT.evaluate_mechanical_gate(
        recipe_bytes=recipe_bytes,
        authority=changed_inputs.authority,
        recipe_schema=changed_inputs.recipe_schema,
        normalization_profile=changed_inputs.authority.normalization_profile,
        exclusion_policy=changed_inputs.exclusion_policy,
    )
    assert changed_gate.diagnostics[0].code == "forbidden_context_marker"
    assert (
        ARTIFACTS.render_planner_request(original_inputs).raw_sha256
        != ARTIFACTS.render_planner_request(changed_inputs).raw_sha256
    )
    assert not hasattr(SUPPORT, "FORBIDDEN_RECIPE_MARKERS")


def test_unfingerprinted_exclusion_policy_cannot_replace_frozen_input() -> None:
    inputs = ARTIFACTS.load_planner_inputs(FIXTURES)
    substituted = dict(inputs.exclusion_policy)
    substituted["forbidden_recipe_markers"] = []
    result = SUPPORT.evaluate_mechanical_gate(
        recipe_bytes=RECIPE_PATH.read_bytes(),
        authority=inputs.authority,
        recipe_schema=inputs.recipe_schema,
        normalization_profile=inputs.authority.normalization_profile,
        exclusion_policy=substituted,
    )
    assert result.diagnostics[0].code == "invalid_exclusion_policy"
    substituted["policy_fingerprint"] = SUPPORT.fingerprint_without(
        substituted, "policy_fingerprint"
    )
    result = SUPPORT.evaluate_mechanical_gate(
        recipe_bytes=RECIPE_PATH.read_bytes(),
        authority=inputs.authority,
        recipe_schema=inputs.recipe_schema,
        normalization_profile=inputs.authority.normalization_profile,
        exclusion_policy=substituted,
    )
    assert result.diagnostics[0].code == "invalid_exclusion_policy"


def _planner_turn(
    *,
    tool_calls: object,
    content: object = None,
    usage: dict[str, object] | None = None,
) -> object:
    return SUPPORT.ProviderTurn(
        raw_request=b'{"planner":"request"}',
        raw_response=b'{"planner":"response"}',
        assistant_message={
            "role": "assistant",
            "content": content,
            "tool_calls": tool_calls,
        },
        usage={} if usage is None else usage,
        provider_metadata={},
    )


def _planner_tool_call(
    recipe_text: str, *, name: str = "submit_planner_recipe"
) -> dict[str, object]:
    return {
        "id": "planner-call-1",
        "function": {
            "name": name,
            "arguments": json.dumps({"recipe_json": recipe_text}),
        },
    }


def _planner_arguments_bytes(recipe_text: str) -> bytes:
    return json.dumps({"recipe_json": recipe_text}).encode("utf-8")


class _PlannerProvider:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, object]] = []

    def __call__(self, request: dict[str, object]) -> object:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _planner_session(
    provider: object, *, monotonic: object | None = None
):
    authority = _authority()
    values: dict[str, object] = {
        "provider": provider,
        "system_prompt": "planner system",
        "user_prompt": "planner user",
        "authority": authority,
        "recipe_schema": authority.recipe_schema,
        "normalization_profile": authority.normalization_profile,
        "exclusion_policy": authority.exclusion_policy,
    }
    if monotonic is not None:
        values["monotonic"] = monotonic
    return SUPPORT.run_planner_session(**values)


def test_planner_tool_definition_is_exactly_one_closed_recipe_submission() -> None:
    assert SUPPORT.planner_tool_definition() == {
        "type": "function",
        "function": {
            "name": "submit_planner_recipe",
            "description": (
                "Submit one proposed planner recipe as exact UTF-8 JSON text. "
                "A mechanically accepted submission ends the session."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "recipe_json": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 1_048_576,
                    }
                },
                "required": ["recipe_json"],
            },
        },
    }


@pytest.mark.parametrize(
    ("tool_calls", "code"),
    [
        ([], "planner_tool_missing"),
        ([_planner_tool_call("{}", name="unknown")], "unknown_tool"),
        ([_planner_tool_call("{}"), _planner_tool_call("{}")], "multiple_tool_calls"),
        ("not-a-list", "provider_tool_calls_malformed"),
        ([{"id": "planner-call-1", "function": []}], "provider_tool_call_malformed"),
    ],
)
def test_planner_protocol_rejects_bad_or_absent_tool_calls(
    tool_calls: object, code: str
) -> None:
    recipe_text = RECIPE_PATH.read_text(encoding="utf-8")
    provider = _PlannerProvider(
        [
            _planner_turn(tool_calls=tool_calls),
            _planner_turn(tool_calls=[_planner_tool_call(recipe_text)]),
        ]
    )
    result = _planner_session(provider)
    assert result.termination == "mechanically_accepted"
    assert result.turns[0].gate_result.diagnostics[0].code == code
    assert code in provider.requests[1]["messages"][-1]["content"]


def test_planner_protocol_rejects_free_text_and_mapping_only_arguments() -> None:
    recipe_text = RECIPE_PATH.read_text(encoding="utf-8")
    free_text = _PlannerProvider(
        [
            _planner_turn(tool_calls=[], content="recipe"),
            _planner_turn(tool_calls=[_planner_tool_call(recipe_text)]),
        ]
    )
    free_text_result = _planner_session(free_text)
    assert free_text_result.termination == "mechanically_accepted"
    assert free_text_result.turns[0].gate_result.diagnostics[0].code == "planner_tool_missing"

    mapped = _planner_tool_call("{}")
    mapped["function"]["arguments"] = {"recipe_json": "{}"}
    mapping_only = _PlannerProvider(
        [
            _planner_turn(tool_calls=[mapped]),
            _planner_turn(tool_calls=[_planner_tool_call(recipe_text)]),
        ]
    )
    mapping_result = _planner_session(mapping_only)
    assert mapping_result.termination == "mechanically_accepted"
    assert (
        mapping_result.turns[0].gate_result.diagnostics[0].code
        == "tool_arguments_not_exact_string"
    )


def test_planner_preserves_exact_recipe_argument_bytes_and_accepts_immediately() -> None:
    recipe_text = RECIPE_PATH.read_text(encoding="utf-8")
    provider = _PlannerProvider([_planner_turn(tool_calls=[_planner_tool_call(recipe_text)])])
    result = _planner_session(provider)
    assert result.termination == "mechanically_accepted"
    assert result.final_recipe_bytes == recipe_text.encode("utf-8")
    assert result.turns[0].tool_arguments == _planner_arguments_bytes(recipe_text)
    assert result.turns[0].gate_result.status == "mechanically_accepted"
    assert len(provider.requests) == 1


def test_planner_allows_fingerprint_resubmission_without_controller_edit() -> None:
    recipe = _recipe()
    recipe["recipe_fingerprint"] = "sha256:" + "0" * 64
    stale_text = _bytes(recipe).decode("utf-8")
    sealed_text = _bytes(_seal(recipe)).decode("utf-8")
    provider = _PlannerProvider(
        [
            _planner_turn(tool_calls=[_planner_tool_call(stale_text)]),
            _planner_turn(tool_calls=[_planner_tool_call(sealed_text)]),
        ]
    )
    result = _planner_session(provider)
    assert result.termination == "mechanically_accepted"
    assert result.turns[0].tool_arguments == _planner_arguments_bytes(stale_text)
    assert (
        result.turns[0].gate_result.status == "fingerprint_resubmission_required"
    )
    assert result.final_recipe_bytes == sealed_text.encode("utf-8")
    assert result.turns[1].tool_arguments == _planner_arguments_bytes(sealed_text)
    assert result.turns[1].gate_result.status == "mechanically_accepted"


def test_planner_normal_turn_limit_is_mechanical_rejection() -> None:
    provider = _PlannerProvider(
        [_planner_turn(tool_calls=[]) for _ in range(SUPPORT.PLANNER_MAX_TURNS)]
    )
    result = _planner_session(provider)
    assert result.termination == "mechanically_rejected"
    assert result.final_recipe_bytes is None
    assert len(result.turns) == SUPPORT.PLANNER_MAX_TURNS
    assert len(provider.requests) == SUPPORT.PLANNER_MAX_TURNS


def test_planner_provider_failure_and_timeout_are_terminal() -> None:
    failed = _PlannerProvider([RuntimeError("provider unavailable")])
    failed_result = _planner_session(failed)
    assert failed_result.termination == "provider_failure"
    assert failed_result.turns == ()

    ticks = iter((0.0, 0.0, 0.0, 0.0, 601.0))
    recipe_text = RECIPE_PATH.read_text(encoding="utf-8")
    timed_out = _PlannerProvider(
        [_planner_turn(tool_calls=[_planner_tool_call(recipe_text)])]
    )
    timeout_result = _planner_session(timed_out, monotonic=lambda: next(ticks))
    assert timeout_result.termination == "timeout"
    assert len(timeout_result.turns) == 1
    assert timeout_result.turns[0].tool_arguments == _planner_arguments_bytes(
        recipe_text
    )


def test_planner_stops_after_an_accepted_submission() -> None:
    recipe_text = RECIPE_PATH.read_text(encoding="utf-8")
    provider = _PlannerProvider(
        [
            _planner_turn(tool_calls=[_planner_tool_call(recipe_text)]),
            RuntimeError("must not be consumed"),
        ]
    )
    result = _planner_session(provider)
    assert result.termination == "mechanically_accepted"
    assert len(provider.requests) == 1


def test_bounded_provider_call_times_out_without_late_session_publication() -> None:
    started = threading.Event()
    release = threading.Event()
    completed = threading.Event()
    recipe_text = RECIPE_PATH.read_text(encoding="utf-8")

    def blocked_provider(_request: dict[str, object]) -> object:
        started.set()
        assert release.wait(1.0)
        completed.set()
        return _planner_turn(tool_calls=[_planner_tool_call(recipe_text)])

    outcome = SUPPORT._bounded_provider_call(
        blocked_provider,
        {"request": "value"},
        timeout_s=0.01,
    )
    assert started.is_set()
    assert outcome.timed_out is True
    assert outcome.response is None
    release.set()
    assert completed.wait(1.0)
    assert outcome.response is None


def test_timed_out_planner_session_never_records_a_late_provider_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(SUPPORT, "PLANNER_PROVIDER_TIMEOUT_S", 0.01)
    started = threading.Event()
    release = threading.Event()
    completed = threading.Event()
    recipe_text = RECIPE_PATH.read_text(encoding="utf-8")

    def blocked_provider(_request: dict[str, object]) -> object:
        started.set()
        assert release.wait(1.0)
        completed.set()
        return _planner_turn(tool_calls=[_planner_tool_call(recipe_text)])

    result = _planner_session(blocked_provider)
    assert started.is_set()
    assert result.termination == "timeout"
    assert result.turns == ()
    release.set()
    assert completed.wait(1.0)
    assert result.turns == ()


def test_planner_session_bounds_are_not_caller_overridable() -> None:
    parameters = inspect.signature(SUPPORT.run_planner_session).parameters
    assert not {
        "max_turns",
        "max_completion_tokens",
        "provider_timeout_s",
        "overall_deadline_s",
        "token_stop_threshold",
        "cost_stop_threshold_usd",
    } & set(parameters)

    provider = _PlannerProvider(
        [_planner_turn(tool_calls=[]) for _ in range(SUPPORT.PLANNER_MAX_TURNS)]
    )
    result = _planner_session(provider)
    assert result.termination == "mechanically_rejected"
    assert all(
        request["max_completion_tokens"] == SUPPORT.PLANNER_MAX_COMPLETION_TOKENS
        and request["provider_timeout_s"] == SUPPORT.PLANNER_PROVIDER_TIMEOUT_S
        for request in provider.requests
    )


def test_planner_provider_timeout_is_clamped_to_remaining_deadline() -> None:
    recipe_text = RECIPE_PATH.read_text(encoding="utf-8")
    provider = _PlannerProvider(
        [_planner_turn(tool_calls=[_planner_tool_call(recipe_text)])]
    )
    ticks = iter((0.0, 500.0, 500.0, 500.0, 500.0))
    result = _planner_session(provider, monotonic=lambda: next(ticks))
    assert result.termination == "mechanically_accepted"
    assert provider.requests[0]["provider_timeout_s"] == 100.0


def test_planner_tool_schema_is_fresh_per_turn_and_public_definition_is_unchanged() -> None:
    recipe_text = RECIPE_PATH.read_text(encoding="utf-8")
    original = copy.deepcopy(SUPPORT.PLANNER_TOOL_PARAMETERS)

    class MutatingProvider:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        def __call__(self, request: dict[str, object]) -> object:
            self.requests.append(request)
            parameters = request["tools"][0]["function"]["parameters"]
            if len(self.requests) == 1:
                parameters["properties"]["recipe_json"]["maxLength"] = 1
                return _planner_turn(tool_calls=[])
            return _planner_turn(tool_calls=[_planner_tool_call(recipe_text)])

    provider = MutatingProvider()
    try:
        result = _planner_session(provider)
        assert result.termination == "mechanically_accepted"
        assert (
            provider.requests[1]["tools"][0]["function"]["parameters"]
            ["properties"]["recipe_json"]["maxLength"]
            == 1_048_576
        )
        assert SUPPORT.PLANNER_TOOL_PARAMETERS == original
    finally:
        if isinstance(SUPPORT.PLANNER_TOOL_PARAMETERS, dict):
            SUPPORT.PLANNER_TOOL_PARAMETERS.clear()
            SUPPORT.PLANNER_TOOL_PARAMETERS.update(original)


def _planner_evaluation_turn(
    report: object,
    *,
    name: str = "submit_planner_evaluation",
) -> object:
    return SUPPORT.ProviderTurn(
        raw_request=b'{"evaluator":"request"}',
        raw_response=b'{"evaluator":"response"}',
        assistant_message={
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "evaluation-call-1",
                    "function": {
                        "name": name,
                        "arguments": json.dumps(
                            {"evaluation_json": json.dumps(report)}
                        ),
                    },
                }
            ],
        },
        usage={},
        provider_metadata={},
    )


def test_planner_evaluator_exposes_one_closed_recommendation_tool() -> None:
    definition = SUPPORT.planner_evaluator_tool_definition()
    assert definition["function"]["name"] == "submit_planner_evaluation"
    parameters = definition["function"]["parameters"]
    assert parameters["additionalProperties"] is False
    assert set(parameters["properties"]) == {"evaluation_json"}
    assert "probe_candidate_ready" not in json.dumps(definition)
    assert "probe_candidate_blocked" not in json.dumps(definition)


def test_planner_evaluation_accepts_one_evidence_backed_recommendation_without_retry() -> None:
    provider = _PlannerProvider(
        [
            _planner_evaluation_turn(
                {
                    "recommendation": "semantically_faithful",
                    "evidence": [
                        {
                            "criterion_id": "brief_fidelity",
                            "finding": "The requested radial box field is represented.",
                        }
                    ],
                }
            ),
            RuntimeError("must not be consumed"),
        ]
    )
    result = SUPPORT.run_planner_evaluation(
        provider=provider,
        system_prompt="evaluator system",
        user_prompt="evaluator user",
    )
    assert result.termination == "valid_recommendation"
    assert result.recommendation == "semantically_faithful"
    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert request["tool_choice"]["function"]["name"] == "submit_planner_evaluation"
    assert request["max_completion_tokens"] == SUPPORT.PLANNER_EVALUATOR_MAX_COMPLETION_TOKENS
    assert request["provider_timeout_s"] == SUPPORT.PLANNER_EVALUATOR_PROVIDER_TIMEOUT_S


@pytest.mark.parametrize(
    "response",
    [
        _planner_evaluation_turn(
            {"recommendation": "semantically_faithful", "evidence": []}
        ),
        _planner_evaluation_turn(
            {
                "recommendation": "probe_candidate_ready",
                "evidence": [
                    {
                        "criterion_id": "brief_fidelity",
                        "finding": "Not a recommendation.",
                    }
                ],
            }
        ),
        _planner_evaluation_turn(
            {
                "recommendation": "semantically_faithful",
                "evidence": [
                    {
                        "criterion_id": "not_a_rubric_criterion",
                        "finding": "Unknown evidence.",
                    }
                ],
            }
        ),
    ],
)
def test_planner_evaluation_malformed_or_missing_evidence_is_inconclusive_without_retry(
    response: object,
) -> None:
    provider = _PlannerProvider([response, RuntimeError("must not be consumed")])
    result = SUPPORT.run_planner_evaluation(
        provider=provider,
        system_prompt="evaluator system",
        user_prompt="evaluator user",
    )
    assert result.termination == "malformed"
    assert result.recommendation is None
    assert len(provider.requests) == 1


@pytest.mark.parametrize(
    ("failure", "termination"),
    [
        (RuntimeError("provider unavailable"), "provider_failure"),
        (TimeoutError("provider timeout"), "timeout"),
    ],
)
def test_planner_evaluation_provider_failure_is_inconclusive_without_retry(
    failure: BaseException, termination: str
) -> None:
    provider = _PlannerProvider([failure])
    result = SUPPORT.run_planner_evaluation(
        provider=provider,
        system_prompt="evaluator system",
        user_prompt="evaluator user",
    )
    assert result.termination == termination
    assert result.recommendation is None
    assert len(provider.requests) == 1

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
