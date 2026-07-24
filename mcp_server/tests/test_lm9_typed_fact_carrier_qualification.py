from __future__ import annotations

import ast
import importlib.util
import inspect
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
OFFICIAL_DERIVATIVE = Path(
    r"C:\Users\bring\rook-lm9b-p-attempts"
    r"\2026-07-22-evaluator-only-continuation"
    r"\derivatives\visibility-evaluator-01"
)
OFFICIAL_DERIVATIVE_IDENTITY = (
    "sha256:48bcdcb36fb3ccee49fe358335f577ffabcb83b0f74e9f84d96951d6b3950b94"
)
EXPECTED_UNRESOLVED_KEYS = {
    "box_footprint_x",
    "box_footprint_y",
    "grid_spacing",
    "maximum_height",
    "minimum_height",
}
FINAL_MEMBERS = {
    "record.json",
    "snapshot.json",
    "contracts/profile.json",
    "contracts/semantic-value-registry.json",
    "contracts/task-payload-schema.json",
    "source/historical-binding.json",
    "source/derivative-binding.json",
    "results/blocked-parent.json",
    "results/control-compatibility.json",
    "results/radial-witness.json",
    "results/annotation-witness.json",
    "results/negative-cases.json",
    "boundary.json",
    "checksums.json",
}


def _load_script(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _assert_closed_unit_context_minting_surface(module: object) -> None:
    allowed = {
        "derive_verified_unit_context_index",
        "_consume_unit_context_index",
    }
    carrier_functions: set[str] = set()
    for name, value in vars(module).items():
        if not inspect.isfunction(value):
            continue
        signature = inspect.signature(value)
        if signature.return_annotation in {
            "VerifiedUnitContextIndex",
            getattr(module, "VerifiedUnitContextIndex"),
        }:
            carrier_functions.add(name)
        assert "seal" not in signature.parameters
        assert "register" not in signature.parameters
    assert carrier_functions == allowed


def _assert_single_post_validation_registry_insertion(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
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
    validation_calls = [
        node
        for node in ast.walk(derive)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_validate_and_derive_unit_context_authority"
    ]
    assert len(assignments) == 1
    assert len(validation_calls) == 1
    assert validation_calls[0].lineno < assignments[0].lineno


def _boom(*_args: object, **_kwargs: object) -> object:
    raise AssertionError("irreversible or provider path was reached")


def test_task1_walks_real_transition_and_publicly_verifies(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    required = [
        SCRIPTS / "lm9_semantic_typed_values.py",
        SCRIPTS / "lm9_typed_fact_carrier_artifacts.py",
        SCRIPTS / "lm9_typed_fact_carrier_qualification.py",
        SCRIPTS
        / "lm9_typed_fact_carrier_contracts/semantic_value_schema_registry.json",
        SCRIPTS
        / "lm9_typed_fact_carrier_contracts/planner_task_typed_facts_payload_schema.json",
        SCRIPTS
        / "lm9_typed_fact_carrier_fixtures/radial_successor_task_envelope.json",
        SCRIPTS
        / "lm9_typed_fact_carrier_fixtures/annotation_task_envelope.json",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    assert not missing, f"Task-1 walking boundary is absent: {missing}"

    support = _load_script("lm9b_p_planner_recipe_transfer_support")
    planner_artifacts = _load_script("lm9b_p_planner_recipe_transfer_artifacts")
    continuation_artifacts = _load_script(
        "lm9b_p_evaluator_only_continuation_artifacts"
    )
    continuation = _load_script("lm9b_p_evaluator_only_continuation")
    typed_values = _load_script("lm9_semantic_typed_values")
    carrier = _load_script("lm9_typed_fact_carrier_artifacts")
    qualification = _load_script("lm9_typed_fact_carrier_qualification")

    assert not hasattr(typed_values, "_issue_unit_context_index")
    assert not hasattr(typed_values, "AuthoritySeal")
    assert not hasattr(typed_values, "_UnitContextAuthoritySeal")
    assert not hasattr(typed_values, "_build_unit_context_authority_gate")
    _assert_closed_unit_context_minting_surface(typed_values)
    _assert_single_post_validation_registry_insertion(
        SCRIPTS / "lm9_semantic_typed_values.py"
    )
    with pytest.raises(TypeError, match="seal"):
        typed_values.derive_verified_unit_context_index(seal=object())
    forged = object.__new__(typed_values.VerifiedUnitContextIndex)
    with pytest.raises(ValueError, match="was not issued"):
        typed_values._consume_unit_context_index(forged)

    monkeypatch.setattr(support, "run_planner_session", _boom)
    monkeypatch.setattr(support, "run_planner_evaluation", _boom)
    monkeypatch.setattr(planner_artifacts, "build_lm9bc_handoff", _boom)
    monkeypatch.setattr(continuation, "_build_evaluator_provider", _boom)
    monkeypatch.setattr(
        qualification,
        "_checkout_state",
        lambda _repo_root: ("task1-uncommitted-test", True),
    )

    compiler_modules_before = {
        name for name in sys.modules if name.startswith("lm9b_c_compiler")
    }
    destination = tmp_path / "task1-qualification"
    written = qualification.write_qualification_archive(
        repo_root=ROOT,
        destination=destination,
    )
    verified = qualification.verify_qualification_archive(
        destination,
        expected_identity=written.qualification_identity,
    )

    assert verified.archive_dir == destination.resolve()
    assert verified.qualification_identity == written.qualification_identity
    assert verified.record["stage"] == "task1_vertical_unhardened"
    assert verified.record["eligibility"] == "independent_review_only"
    assert verified.record["source_manifest_raw_sha256"] == (
        "sha256:ac7716b7d5a61e2e6359bc0e01e145d7d17e0871ff03d1d5329710541d274c90"
    )
    assert verified.record["recipe_raw_sha256"] == (
        "sha256:5c5dba9def1ffc3002240f3154f02f36e60134019659d5e6a9d546b0317965af"
    )
    assert verified.record["recipe_fingerprint"] == (
        "sha256:eb70994fa9ead99fbe75f6f25e81327045258389d46e91474cc5b581befc068a"
    )
    assert verified.record["derivative_archive_identity"] == (
        OFFICIAL_DERIVATIVE_IDENTITY
    )
    assert verified.record["classification"] == "probe_candidate_blocked"
    assert set(verified.record["unresolved_keys"]) == EXPECTED_UNRESOLVED_KEYS
    assert set(verified.record["authority_delta_keys"]) == EXPECTED_UNRESOLVED_KEYS
    assert set(verified.record["required_delta_keys"]) == EXPECTED_UNRESOLVED_KEYS
    assert len(verified.record["migration_keys"]) == 7

    radial = json.loads((destination / "results/radial-witness.json").read_bytes())
    annotation = json.loads(
        (destination / "results/annotation-witness.json").read_bytes()
    )
    negatives = json.loads(
        (destination / "results/negative-cases.json").read_bytes()
    )
    boundary = json.loads((destination / "boundary.json").read_bytes())
    assert radial["validated"] is True
    assert radial["fact_count"] == 12
    assert annotation["validated"] is True
    assert annotation["schemas"] == [
        "rook.semantic_boolean:v1",
        "rook.semantic_integer:v1",
        "rook.semantic_scalar:v1",
        "rook.semantic_string:v1",
    ]
    assert [row["case_id"] for row in negatives["results"]] == list(
        carrier.required_negative_case_ids()
    )
    assert all(
        row["status"] == "task1_registered_not_hardened"
        for row in negatives["results"]
    )
    assert boundary["archived_evaluator_evidence_verified"] is True
    for key in (
        "model_activity",
        "provider_activity",
        "readiness_activity",
        "evaluator_dispatch_activity",
        "compiler_activity",
        "rhino_activity",
        "grasshopper_activity",
        "product_authority_activity",
    ):
        assert boundary[key] is False

    members = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    }
    assert members == FINAL_MEMBERS
    assert not (tmp_path / "task1-qualification.staging").exists()
    assert {
        name for name in sys.modules if name.startswith("lm9b_c_compiler")
    } == compiler_modules_before
