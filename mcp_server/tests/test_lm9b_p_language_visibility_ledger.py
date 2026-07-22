"""LM9B-P workerless language-visibility closure — carrier ledger + boundary.

These tests PIN the reviewed M1-M6 ledger: every reviewed recipe-language rule the
mechanical gate enforces has an exact model-visible carrier (recipe schema, the
authoring-contract language_boundary/relational_invariants, or an already-available
runtime hook), and that carrier actually reaches the model through the renderer.
They fail on drift; they do not claim to prove that every future gate rule has a
carrier. Boundary tests separate the two intended loci: rules made visible in the
schema now reject at `recipe_schema_failed`; rules JSON Schema cannot express stay
enforced by the UNCHANGED mechanical gate while the contract states them."""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "scripts" / "lm9b_p_fixtures"
RECIPE_PATH = ROOT / "mcp_server/tests/fixtures/lm9b_p/non_r01_ready_recipe.json"

MID = "^[a-z0-9]+(?:[._:-][a-z0-9]+)*$"
POINTER = "^/rules/[a-z0-9]+(?:[._:-][a-z0-9]+)*$"
REF = {"$ref": "#/$defs/machine_identifier"}


def _load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SUPPORT = _load_script("lm9b_p_planner_recipe_transfer_support")
ARTIFACTS = _load_script("lm9b_p_planner_recipe_transfer_artifacts")


def _schema() -> dict:
    return json.loads((FIXTURES / "planner_recipe_probe_schema.json").read_text(encoding="utf-8"))


def _contract() -> dict:
    return json.loads((FIXTURES / "planner_authoring_contract.json").read_text(encoding="utf-8"))


def _rubric() -> dict:
    return json.loads((FIXTURES / "planner_evaluation_rubric.json").read_text(encoding="utf-8"))


def _recipe() -> dict:
    return json.loads(RECIPE_PATH.read_bytes())


def _authority():
    return ARTIFACTS.load_planner_authority_context(FIXTURES)


def _validate(recipe: dict) -> list:
    return sorted(Draft202012Validator(_schema()).iter_errors(recipe), key=lambda e: list(e.path))


def _seal(value: dict) -> dict:
    value = copy.deepcopy(value)
    projection = {k: v for k, v in value.items() if k != "recipe_fingerprint"}
    normalized = SUPPORT.normalize_recipe(projection, _authority().normalization_profile)
    value["recipe_fingerprint"] = SUPPORT.fingerprint(normalized)
    return value


def _gate(recipe: dict):
    authority = _authority()
    raw = (json.dumps(recipe, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return SUPPORT.evaluate_mechanical_gate(
        recipe_bytes=raw,
        authority=authority,
        recipe_schema=authority.recipe_schema,
        normalization_profile=authority.normalization_profile,
        exclusion_policy=authority.exclusion_policy,
    )


# ============================ M2: descriptor kind + kind/schema pairing ============================

def test_m2_source_task_kind_and_schema_pinned() -> None:
    props = _schema()["properties"]["source_task"]["properties"]
    assert props["artifact_kind"] == {"const": "task_envelope"}
    assert props["schema"] == {"const": "rook.planner_task_envelope:v1"}


def test_m2_authority_kind_enum_and_kind_schema_pairing() -> None:
    items = _schema()["properties"]["authority_artifacts"]["items"]
    assert items["properties"]["artifact_kind"] == {"enum": ["environment_snapshot", "planning_policy"]}
    one_of = [x for x in items.get("allOf", []) if "oneOf" in x]
    assert one_of, "authority kind/schema oneOf pairing must be present"
    pairs = {
        (b["properties"]["artifact_kind"]["const"], b["properties"]["schema"]["const"])
        for b in one_of[0]["oneOf"]
    }
    assert pairs == {
        ("environment_snapshot", "rook.environment_snapshot:v1"),
        ("planning_policy", "rook.planning_policy:v1"),
    }


def test_m2_contract_language_boundary_mirrors_kind_schema() -> None:
    lb = _contract()["language_boundary"]
    assert lb["source_task_artifact_kind"] == "task_envelope"
    assert lb["source_task_schema"] == "rook.planner_task_envelope:v1"
    assert lb["authority_artifact_kinds"] == ["environment_snapshot", "planning_policy"]
    assert lb["descriptor_kind_schema"] == {
        "environment_snapshot": "rook.environment_snapshot:v1",
        "planning_policy": "rook.planning_policy:v1",
        "task_envelope": "rook.planner_task_envelope:v1",
    }


# ============================ M1: reserved identity + placement ============================

def test_m1_source_task_artifact_id_reserved_const() -> None:
    assert _schema()["properties"]["source_task"]["properties"]["artifact_id"] == {"const": "task_envelope"}


def test_m1_authority_artifact_id_forbids_reserved_and_grammar_bound() -> None:
    aid = _schema()["properties"]["authority_artifacts"]["items"]["properties"]["artifact_id"]
    assert REF in aid["allOf"]
    assert {"not": {"const": "task_envelope"}} in aid["allOf"]


def test_m1_no_uniqueitems_used_for_id_uniqueness() -> None:
    # uniqueItems compares whole objects, not artifact_id, so it must NOT be relied on.
    assert "uniqueItems" not in _schema()["properties"]["authority_artifacts"]


def test_m1_contract_declares_uniqueness_and_reserved_placement() -> None:
    ri = _contract()["relational_invariants"]
    assert any("globally unique" in s for s in ri)
    assert any("task_envelope" in s and "authority_artifacts" in s for s in ri)


# ============================ M3: complete machine-identifier coverage ============================

def test_m3_machine_identifier_def_present() -> None:
    assert _schema()["$defs"]["machine_identifier"] == {"type": "string", "pattern": MID}


def test_m3_every_applicable_field_refs_the_shared_def() -> None:
    schema = _schema()
    gaps: list[str] = []

    def walk(node, path=""):
        if isinstance(node, dict):
            props = node.get("properties")
            if isinstance(props, dict):
                for pk, pv in props.items():
                    p = f"{path}/{pk}"
                    if pk.endswith("_id"):
                        ok = (
                            pv == REF
                            or pv == {"const": "task_envelope"}  # source_task reserved id
                            or (isinstance(pv, dict) and REF in pv.get("allOf", []))  # authority id
                            or pv == {"type": "null"}  # workerless worker_slot_id
                        )
                        if not ok:
                            gaps.append(p)
                    elif pk.endswith("_ids") and isinstance(pv, dict) and pv.get("type") == "array":
                        if pv.get("items") != REF:
                            gaps.append(f"{p}/items")
                    elif pk == "affects" and isinstance(pv, dict) and pv.get("type") == "array":
                        if pv.get("items") != REF:
                            gaps.append(f"{p}/items")
                    elif pk == "semantic_key":
                        if pv != REF:
                            gaps.append(p)
                for pv in props.values():
                    walk(pv, path)
            for k, v in node.items():
                if k != "properties":
                    walk(v, path)
        elif isinstance(node, list):
            for i, x in enumerate(node):
                walk(x, f"{path}[{i}]")

    walk(schema)
    assert gaps == [], f"identifier-grammar coverage gaps: {gaps}"


# The remaining machine-scalar fields the gate applies the grammar to (support.py
# _MACHINE_SCALAR_FIELDS, minus semantic_key which is covered by the shared $def above).
_SCALAR_FIELDS = {
    "artifact_kind",
    "authority_code",
    "capability_code",
    "delegate_kind",
    "kind",
    "schema",
    "value_schema",
    "vocabulary_version",
}


def test_m3_machine_scalar_fields_have_visible_carriers_matching_grammar() -> None:
    # Each remaining machine-scalar field must have a model-visible carrier
    # (schema const/enum, or a vocabulary fixture), and every admitted value must
    # itself satisfy the machine-identifier grammar the gate enforces.
    schema = _schema()
    grammar = re.compile(MID)
    carriers: dict[str, set] = {}

    def collect(node):
        if isinstance(node, dict):
            props = node.get("properties")
            if isinstance(props, dict):
                for k, v in props.items():
                    if k in _SCALAR_FIELDS and isinstance(v, dict):
                        if "const" in v:
                            carriers.setdefault(k, set()).add(v["const"])
                        elif "enum" in v:
                            carriers.setdefault(k, set()).update(v["enum"])
                for v in props.values():
                    collect(v)
            for kk, vv in node.items():
                if kk != "properties":
                    collect(vv)
        elif isinstance(node, list):
            for x in node:
                collect(x)

    collect(schema)

    # Vocabulary-bound fields carry their admitted values in model-visible fixtures.
    def _codes(fname: str, code_key: str) -> set:
        entries = json.loads((FIXTURES / fname).read_text())["entries"]
        return {e[code_key] for e in entries}

    carriers.setdefault("authority_code", set()).update(
        _codes("semantic_authority_code_vocabulary.json", "code")
    )
    carriers.setdefault("capability_code", set()).update(
        _codes("semantic_capability_code_vocabulary.json", "code")
    )
    carriers.setdefault("value_schema", set()).update(
        _codes("semantic_value_schema_registry.json", "schema")
    )

    missing = _SCALAR_FIELDS - set(carriers)
    assert not missing, f"machine-scalar fields without a visible carrier: {missing}"

    ungrammatical = {
        (field, value)
        for field, values in carriers.items()
        for value in values
        if not grammar.fullmatch(value)
    }
    assert not ungrammatical, f"admitted values violate the machine grammar: {ungrammatical}"


# ============================ M4: policy pointer grammar ============================

def test_m4_policy_reference_json_pointer_pattern() -> None:
    schema = _schema()
    found = []

    def walk(node):
        if isinstance(node, dict):
            props = node.get("properties")
            if isinstance(props, dict):
                kind = props.get("kind")
                if isinstance(kind, dict) and kind.get("const") == "policy_rule":
                    found.append(props.get("json_pointer"))
                for pv in props.values():
                    walk(pv)
            for k, v in node.items():
                if k != "properties":
                    walk(v)
        elif isinstance(node, list):
            for x in node:
                walk(x)

    walk(schema)
    assert found, "at least one policy_rule reference must exist"
    assert all(p == {"type": "string", "pattern": POINTER} for p in found), found


# ============================ M5/M6: relational invariants (declarative) ============================

def test_m5_m6_relational_invariants_declared() -> None:
    ri = _contract()["relational_invariants"]
    assert any("referenced by recipe content" in s for s in ri), "M5 descriptor-use invariant"
    assert any("resolves to a declared symbol" in s for s in ri), "M6 local-reference invariant"


# ============================ visibility through the renderer ============================

def test_carriers_reach_the_model_through_the_renderer() -> None:
    # Assert the rendered payload carries the COMPLETE frozen recipe_schema and
    # authoring_contract (with the contract's expected fingerprint) — not merely that
    # some tokens appear, which stale or reconstructed content could satisfy.
    inputs = ARTIFACTS.load_planner_inputs(FIXTURES)
    payload = json.loads(ARTIFACTS.render_planner_request(inputs).raw_bytes)
    assert payload["recipe_schema"] == _schema()
    assert payload["authoring_contract"] == _contract()
    assert (
        payload["authoring_contract"]["contract_fingerprint"]
        == _contract()["contract_fingerprint"]
    )


# ============================ fingerprint / manifest consistency ============================

def test_contract_and_rubric_fingerprint_chain_consistent() -> None:
    c, r = _contract(), _rubric()
    assert c["contract_fingerprint"] == SUPPORT.fingerprint_without(c, "contract_fingerprint")
    assert r["rubric_fingerprint"] == SUPPORT.fingerprint_without(r, "rubric_fingerprint")
    assert r["authoring_contract_binding"]["contract_fingerprint"] == c["contract_fingerprint"]


# ============================ boundary: schema-rejection band (recipe_schema_failed) ============================

def test_boundary_positive_corrected_recipe_passes_schema() -> None:
    # The corrected synthetic descriptor set (bare tokens, unique ids, reserved
    # source_task, matching kind/schema) validates cleanly. Not R01-derived.
    assert _validate(_recipe()) == []


def test_boundary_wrong_authority_kind_fails_schema() -> None:
    recipe = _recipe()
    recipe["authority_artifacts"][0]["artifact_kind"] = "task_envelope"
    assert _gate(_seal(recipe)).diagnostics[0].code == "recipe_schema_failed"


def test_boundary_wrong_kind_schema_pair_fails_schema() -> None:
    recipe = _recipe()
    recipe["authority_artifacts"][0]["schema"] = "rook.planning_policy:v1"  # env kind, policy schema
    assert _gate(_seal(recipe)).diagnostics[0].code == "recipe_schema_failed"


def test_boundary_reserved_id_in_authority_fails_schema() -> None:
    recipe = _recipe()
    recipe["authority_artifacts"][0]["artifact_id"] = "task_envelope"
    assert _gate(_seal(recipe)).diagnostics[0].code == "recipe_schema_failed"


def test_boundary_malformed_identifier_fails_schema() -> None:
    recipe = _recipe()
    recipe["goal"]["clause_id"] = "goal contains spaces"
    assert _gate(_seal(recipe)).diagnostics[0].code == "recipe_schema_failed"


def test_boundary_malformed_policy_pointer_fails_schema() -> None:
    recipe = _recipe()
    recipe["assumptions"][0]["authorization_refs"]["policy_refs"][0]["json_pointer"] = "/issuer/kind"
    assert _gate(_seal(recipe)).diagnostics[0].code == "recipe_schema_failed"


# ============================ boundary: UNCHANGED mechanical-gate band ============================
# For each rule JSON Schema cannot express, prove BOTH: (1) the authoring contract
# visibly states it, and (2) the unchanged gate still rejects it.

def test_unchanged_gate_still_rejects_duplicate_descriptor_id() -> None:
    # Cross-object descriptor-id uniqueness is not JSON-Schema-expressible; it stays
    # gate-enforced. Duplicate an authority DESCRIPTOR (not a clause) and gate WITHOUT
    # _seal, because normalization refuses duplicate identities before the gate runs.
    ri = _contract()["relational_invariants"]
    assert any("globally unique" in s for s in ri)
    recipe = _recipe()
    recipe["authority_artifacts"].append(copy.deepcopy(recipe["authority_artifacts"][0]))
    diag = _gate(recipe).diagnostics[0]
    assert diag.code == "duplicate_identifier"
    assert diag.path == "/authority_artifacts/2/artifact_id"


def test_unchanged_gate_still_rejects_unreferenced_authority_descriptor() -> None:
    # Structural evaluation precedes fingerprint binding, so an unreferenced descriptor
    # must produce exactly unreferenced_authority_descriptor at its path.
    ri = _contract()["relational_invariants"]
    assert any("referenced by recipe content" in s for s in ri)
    recipe = _recipe()
    extra = copy.deepcopy(recipe["authority_artifacts"][0])
    extra["artifact_id"] = "unreferenced.descriptor"
    recipe["authority_artifacts"].append(extra)
    diag = _gate(recipe).diagnostics[0]
    assert diag.code == "unreferenced_authority_descriptor"
    assert diag.path == "/authority_artifacts/2"


def test_unchanged_gate_still_rejects_dangling_local_reference() -> None:
    ri = _contract()["relational_invariants"]
    assert any("resolves to a declared symbol" in s for s in ri)
    recipe = _recipe()
    recipe["maintains"][0]["assumption_refs"][0]["assumption_id"] = "assumption.missing"
    assert _gate(_seal(recipe)).diagnostics[0].code == "dangling_local_reference"
