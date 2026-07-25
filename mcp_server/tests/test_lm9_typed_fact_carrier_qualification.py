from __future__ import annotations

import ast
import dataclasses
import hashlib
import importlib.util
import inspect
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

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


def _task1_transition():
    typed_values = _load_script("lm9_semantic_typed_values")
    carrier = _load_script("lm9_typed_fact_carrier_artifacts")
    qualification = _load_script("lm9_typed_fact_carrier_qualification")
    return typed_values, carrier, qualification._derive_transition(ROOT)


def _reclosed_envelope_bytes(typed_values: object, envelope: dict[str, object]) -> bytes:
    envelope["artifact_fingerprint"] = typed_values.fingerprint_without(
        envelope, "artifact_fingerprint"
    )
    return typed_values.canonical_json_bytes(envelope) + b"\n"


def _json_file(path: Path) -> dict[str, object]:
    value = json.loads(path.read_bytes())
    assert type(value) is dict
    return value


def _write_json(typed_values: object, path: Path, value: object) -> None:
    path.write_bytes(typed_values.canonical_json_bytes(value) + b"\n")


def _reclose_snapshot_and_record(
    typed_values: object,
    archive: Path,
) -> None:
    snapshot_path = archive / "snapshot.json"
    snapshot = _json_file(snapshot_path)
    projection = {
        key: value
        for key, value in snapshot.items()
        if key != "snapshot_fingerprint"
    }
    snapshot["snapshot_fingerprint"] = typed_values.fingerprint(projection)
    _write_json(typed_values, snapshot_path, snapshot)
    record_path = archive / "record.json"
    record = _json_file(record_path)
    record["snapshot_fingerprint"] = snapshot["snapshot_fingerprint"]
    _write_json(typed_values, record_path, record)


def _reclose_parent_witness(
    typed_values: object,
    archive: Path,
) -> None:
    path = archive / "results/blocked-parent.json"
    value = _json_file(path)
    projection = {
        key: item
        for key, item in value.items()
        if key not in {"schema", "witness_fingerprint"}
    }
    value["witness_fingerprint"] = typed_values.fingerprint(projection)
    _write_json(typed_values, path, value)


def _reclose_qualification_checksums(
    qualification: object,
    typed_values: object,
    archive: Path,
) -> str:
    rows = []
    for path in sorted(
        (
            item
            for item in archive.rglob("*")
            if item.is_file() and item.name != "checksums.json"
        ),
        key=lambda item: item.relative_to(archive).as_posix(),
    ):
        raw = path.read_bytes()
        rows.append(
            {
                "path": path.relative_to(archive).as_posix(),
                "raw_sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
            }
        )
    identity_source = {
        "schema": qualification.QUALIFICATION_SCHEMA_ID,
        "canonical_destination": str(archive.resolve()),
        "members": rows,
    }
    identity = typed_values.fingerprint(identity_source)
    checksums = {
        "schema": qualification.CHECKSUMS_SCHEMA_ID,
        "canonical_destination": str(archive.resolve()),
        "members": rows,
        "qualification_identity": identity,
    }
    _write_json(typed_values, archive / "checksums.json", checksums)
    return identity


def _restore_archive(archive: Path, pristine: dict[str, bytes]) -> None:
    for path in sorted(archive.rglob("*"), reverse=True):
        if path.is_file() and path.relative_to(archive).as_posix() not in pristine:
            path.unlink()
    for relative, raw in pristine.items():
        path = archive / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)


def _partition_inputs(carrier: object, transition: dict[str, object]):
    source = transition["source"]
    parent_values = carrier.reconstruct_observed_historical_task_values(
        source,
        registry=transition["registry"],
        unit_context_index=transition["unit_context_index"],
    )
    parent_bindings = carrier.historical_task_bindings(source)
    parent_recipe = json.loads(source.final_recipe_bytes)
    return parent_values, parent_bindings, parent_recipe


def test_qualification_walks_real_transition_and_publicly_verifies(
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
    compiler_support = _load_script("lm9b_c_compiler_sufficiency_support")
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
    monkeypatch.setattr(compiler_support, "run_compiler_session", _boom)
    monkeypatch.setattr(compiler_support, "run_evaluator_once", _boom)
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
    assert type(verified.snapshot) is qualification.QualificationSnapshot
    assert verified.snapshot.commit_sha == "task1-uncommitted-test"
    assert verified.snapshot.clean_checkout is True
    assert verified.snapshot.runtime == typed_values.current_runtime_identity()
    assert verified.snapshot.helper_source_sha256.startswith("sha256:")
    assert verified.snapshot.snapshot_fingerprint.startswith("sha256:")
    assert verified.record["stage"] == "qualification_complete"
    assert verified.record["eligibility"] == "independent_review_candidate"
    assert (
        verified.record["snapshot_fingerprint"]
        == verified.snapshot.snapshot_fingerprint
    )
    assert set(verified.record) == {
        "schema",
        "stage",
        "eligibility",
        "canonical_destination",
        "reviewed_commit",
        "checkout_clean",
        "snapshot_fingerprint",
        "source_manifest_raw_sha256",
        "recipe_raw_sha256",
        "recipe_fingerprint",
        "derivative_archive_identity",
        "classification",
        "unresolved_keys",
        "migration_keys",
        "authority_delta_keys",
        "required_delta_keys",
        "partition_fingerprint",
    }
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

    snapshot = _json_file(destination / "snapshot.json")
    profile = _json_file(destination / "contracts/profile.json")
    registry = _json_file(
        destination / "contracts/semantic-value-registry.json"
    )
    payload_schema = _json_file(
        destination / "contracts/task-payload-schema.json"
    )
    historical = _json_file(destination / "source/historical-binding.json")
    derivative = _json_file(destination / "source/derivative-binding.json")
    parent = _json_file(destination / "results/blocked-parent.json")
    assert snapshot["schema"] == (
        "rook.lm9.typed_fact_carrier_qualification_snapshot:v1"
    )
    assert snapshot["runtime"] == typed_values.runtime_identity_value(
        typed_values.current_runtime_identity()
    )
    assert snapshot["runtime"]["jsonschema_version"] == "4.26.0"
    assert snapshot["helper_source_sha256"] == (
        "sha256:"
        + hashlib.sha256(
            (SCRIPTS / "lm9_semantic_typed_values.py").read_bytes()
        ).hexdigest()
    )
    assert typed_values.fingerprint(profile) == snapshot["profile_fingerprint"]
    assert registry["registry_fingerprint"] == snapshot["registry_fingerprint"]
    assert typed_values.fingerprint(payload_schema) == snapshot[
        "payload_schema_fingerprint"
    ]
    assert historical["schema"] == (
        "rook.lm9.typed_fact_carrier_historical_binding:v1"
    )
    assert historical["root_manifest_raw_sha256"] == verified.record[
        "source_manifest_raw_sha256"
    ]
    source = continuation_artifacts.verify_historical_source()
    _, expected_unit_context_index = carrier._verified_parent_value_context(
        source,
        runtime=typed_values.current_runtime_identity(),
    )
    assert historical["unit_context_proof_fingerprint"] == (
        expected_unit_context_index.proof_fingerprint
    )
    assert derivative == {
        "schema": "rook.lm9.typed_fact_carrier_derivative_binding:v1",
        "archive_dir": str(OFFICIAL_DERIVATIVE.resolve()),
        "derivative_archive_identity": OFFICIAL_DERIVATIVE_IDENTITY,
        "evaluator_recommendation": "semantically_faithful",
    }
    assert parent["schema"] == (
        "rook.lm9.typed_fact_carrier_blocked_parent:v1"
    )
    assert parent["classification"] == "probe_candidate_blocked"
    assert set(parent["unresolved_keys"]) == EXPECTED_UNRESOLVED_KEYS

    radial = json.loads((destination / "results/radial-witness.json").read_bytes())
    annotation = json.loads(
        (destination / "results/annotation-witness.json").read_bytes()
    )
    negatives = json.loads(
        (destination / "results/negative-cases.json").read_bytes()
    )
    controls = json.loads(
        (destination / "results/control-compatibility.json").read_bytes()
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
    assert negatives["required_case_set_fingerprint"] == (
        typed_values.fingerprint(list(carrier.required_negative_case_ids()))
    )
    assert all(
        row["status"] == "deterministically_refused"
        for row in negatives["results"]
    )
    assert controls["schema"] == (
        "rook.lm9.typed_fact_carrier_control_compatibility:v1"
    )
    assert [row["acceptance_boundary"] for row in controls["controls"]] == [
        "lm9b_c_frozen_input",
        "planner_mechanical_gate",
    ]
    assert [row["acceptance_status"] for row in controls["controls"]] == [
        "frozen_inputs_accepted",
        "mechanically_accepted",
    ]
    assert [row["recipe_raw_sha256"] for row in controls["controls"]] == [
        "sha256:c2a504e7a089c37fc174d53eeb7cd409690a63e7709cfea8ea7ce7a3c13ddad2",
        "sha256:d5fb1589b9d3b463fa16caf8c9c831f5b68fc73062ab831b091520aae9abe724",
    ]
    assert boundary["archived_evaluator_evidence_verified"] is True
    assert boundary["lm9b_c_manifest_verification"] is True
    assert boundary["planner_mechanical_gate_evaluation"] is True
    for key in (
        "model_activity",
        "provider_activity",
        "readiness_activity",
        "evaluator_dispatch_activity",
        "planner_dispatch_activity",
        "compiler_dispatch_activity",
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
    checksums = _json_file(destination / "checksums.json")
    assert checksums["schema"] == (
        "rook.lm9.typed_fact_carrier_qualification_checksums:v1"
    )
    assert [row["path"] for row in checksums["members"]] == sorted(
        FINAL_MEMBERS - {"checksums.json"}
    )
    assert not (tmp_path / "task1-qualification.staging").exists()
    assert {
        name for name in sys.modules if name.startswith("lm9b_c_compiler")
    } == compiler_modules_before


def test_forward_envelope_refuses_reclosed_cross_session_authority() -> None:
    typed_values, carrier, transition = _task1_transition()
    envelope = json.loads(carrier.RADIAL_FIXTURE_PATH.read_bytes())
    envelope["task_session_id"] = "different-task-session"

    with pytest.raises(ValueError, match="task session"):
        carrier.validate_forward_task_envelope(
            _reclosed_envelope_bytes(typed_values, envelope),
            payload_schema_raw_bytes=transition["payload_schema_raw"],
            registry_raw_bytes=transition["registry_raw"],
            unit_context_index=transition["unit_context_index"],
            runtime=transition["runtime"],
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "wrong_value_schema",
        "wrong_source_artifact",
        "wrong_source_pointer",
        "user_fact_not_permitted",
        "malformed_permission_container",
        "wrong_unit_context",
        "null_unit_context",
    ),
)
def test_partition_refuses_reclosed_delta_outside_parent_unresolved_contract(
    mutation: str,
) -> None:
    typed_values, carrier, transition = _task1_transition()
    parent_values, parent_bindings, parent_recipe = _partition_inputs(
        carrier, transition
    )
    successor = transition["radial"]

    if mutation == "wrong_value_schema":
        envelope = json.loads(carrier.RADIAL_FIXTURE_PATH.read_bytes())
        envelope["payload"]["facts"]["grid_spacing"] = {
            "schema": "rook.semantic_string:v1",
            "value": "2",
            "unit": None,
            "unit_context_ref": None,
        }
        binding = next(
            row
            for row in envelope["value_bindings"]
            if row["semantic_key"] == "grid_spacing"
        )
        binding["value_schema"] = "rook.semantic_string:v1"
        binding["typed_value_fingerprint"] = typed_values.fingerprint(
            envelope["payload"]["facts"]["grid_spacing"]
        )
        successor = carrier.validate_forward_task_envelope(
            _reclosed_envelope_bytes(typed_values, envelope),
            payload_schema_raw_bytes=transition["payload_schema_raw"],
            registry_raw_bytes=transition["registry_raw"],
            unit_context_index=transition["unit_context_index"],
            runtime=transition["runtime"],
        )
    else:
        row = next(
            item
            for item in parent_recipe["unresolved_intent"]
            if item["semantic_key"] == "grid_spacing"
        )
        if mutation == "wrong_source_artifact":
            row["expected_source_location"]["artifact_id"] = (
                "environment_snapshot"
            )
        elif mutation == "wrong_source_pointer":
            row["expected_source_location"]["json_pointer"] = (
                "/facts/other_spacing"
            )
        elif mutation == "user_fact_not_permitted":
            row["resolution_authority"]["permitted_kinds"] = [
                "planner_assumption"
            ]
        elif mutation == "malformed_permission_container":
            row["resolution_authority"]["permitted_kinds"] = "user_fact"
        elif mutation == "wrong_unit_context":
            row["unit_context_ref"] = {
                "kind": "artifact_value",
                "artifact_id": "environment_snapshot",
                "json_pointer": "/document/other_unit_context",
            }
        elif mutation == "null_unit_context":
            row["unit_context_ref"] = None
        parent_recipe["recipe_fingerprint"] = typed_values.fingerprint(
            {
                key: value
                for key, value in parent_recipe.items()
                if key != "recipe_fingerprint"
            }
        )

    with pytest.raises(ValueError, match="unresolved contract"):
        carrier.derive_authority_partition(
            parent_values=parent_values,
            parent_bindings=parent_bindings,
            successor=successor,
            parent_recipe=parent_recipe,
        )


def test_relational_authority_mutations_are_registered_in_negative_manifest() -> None:
    carrier = _load_script("lm9_typed_fact_carrier_artifacts")
    assert {
        "binding.task_session",
        "migration.unresolved_value_schema",
        "migration.unresolved_source_location",
        "migration.unresolved_authority_permission",
        "migration.unresolved_unit_context",
    } <= set(carrier.required_negative_case_ids())


def test_dirty_checkout_refuses_before_transition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    qualification = _load_script("lm9_typed_fact_carrier_qualification")
    monkeypatch.setattr(
        qualification,
        "_checkout_state",
        lambda _repo_root: ("dirty-test-commit", False),
    )
    monkeypatch.setattr(qualification, "_derive_transition", _boom)
    destination = tmp_path / "must-not-exist"

    with pytest.raises(ValueError, match="checkout is not clean"):
        qualification.write_qualification_archive(
            repo_root=ROOT,
            destination=destination,
        )

    assert not destination.exists()
    assert not destination.with_name(destination.name + ".staging").exists()


def test_runtime_drift_after_snapshot_refuses_before_transition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    qualification = _load_script("lm9_typed_fact_carrier_qualification")
    actual = qualification.TYPED_VALUES.current_runtime_identity()
    drifted = dataclasses.replace(actual, version=actual.version + " drift")
    drift_enabled = False
    build_snapshot = qualification.build_qualification_snapshot

    def runtime_identity():
        return drifted if drift_enabled else actual

    def snapshot(*, repo_root: Path):
        nonlocal drift_enabled
        result = build_snapshot(repo_root=repo_root)
        drift_enabled = True
        return result

    monkeypatch.setattr(
        qualification,
        "_checkout_state",
        lambda _repo_root: ("runtime-test-commit", True),
    )
    monkeypatch.setattr(
        qualification.TYPED_VALUES,
        "current_runtime_identity",
        runtime_identity,
    )
    monkeypatch.setattr(
        qualification,
        "build_qualification_snapshot",
        snapshot,
    )
    monkeypatch.setattr(qualification, "_derive_transition", _boom)

    with pytest.raises(ValueError, match="runtime identity"):
        qualification.write_qualification_archive(
            repo_root=ROOT,
            destination=tmp_path / "runtime-drift",
        )

    assert drift_enabled is True


def test_precreated_destination_refuses_before_transition_with_file_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    qualification = _load_script("lm9_typed_fact_carrier_qualification")
    monkeypatch.setattr(
        qualification,
        "_checkout_state",
        lambda _repo_root: ("destination-test-commit", True),
    )
    monkeypatch.setattr(qualification, "_derive_transition", _boom)
    destination = tmp_path / "already-present"
    destination.mkdir()

    with pytest.raises(FileExistsError, match="already exists"):
        qualification.write_qualification_archive(
            repo_root=ROOT,
            destination=destination,
        )


def test_writer_refuses_a_different_checkout_root_before_transition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    qualification = _load_script("lm9_typed_fact_carrier_qualification")
    other_checkout = tmp_path / "other-checkout"
    other_checkout.mkdir()
    monkeypatch.setattr(
        qualification,
        "_checkout_state",
        lambda _repo_root: ("other-checkout-commit", True),
    )
    monkeypatch.setattr(qualification, "_derive_transition", _boom)

    with pytest.raises(ValueError, match="calling checkout"):
        qualification.write_qualification_archive(
            repo_root=other_checkout,
            destination=tmp_path / "wrong-root-qualification",
        )


def test_snapshot_is_persisted_and_reread_before_transition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    qualification = _load_script("lm9_typed_fact_carrier_qualification")
    monkeypatch.setattr(
        qualification,
        "_checkout_state",
        lambda _repo_root: ("ordering-test-commit", True),
    )
    destination = tmp_path / "ordered-qualification"
    staging = destination.with_name(destination.name + ".staging")
    derive = qualification._derive_transition
    calls = 0

    def ordered_transition(repo_root: Path):
        nonlocal calls
        calls += 1
        if calls == 1:
            snapshot_path = staging / "snapshot.json"
            assert snapshot_path.is_file()
            persisted = snapshot_path.read_bytes()
            assert qualification._snapshot_from_bytes(persisted)
            assert persisted == snapshot_path.read_bytes()
        return derive(repo_root)

    monkeypatch.setattr(qualification, "_derive_transition", ordered_transition)

    qualification.write_qualification_archive(
        repo_root=ROOT,
        destination=destination,
    )

    assert calls >= 1


def test_cli_exposes_only_qualify_and_verify(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    qualification = _load_script("lm9_typed_fact_carrier_qualification")
    destination = tmp_path / "cli-qualification"
    observed: list[tuple[str, Path]] = []

    def qualify(*, repo_root: Path, destination: Path):
        observed.append(("qualify", destination))
        return SimpleNamespace(
            archive_dir=destination,
            qualification_identity="sha256:" + "1" * 64,
        )

    def verify(archive_dir: Path, *, expected_identity: str | None = None):
        observed.append(("verify", archive_dir))
        return SimpleNamespace(
            archive_dir=archive_dir,
            qualification_identity=expected_identity or "sha256:" + "2" * 64,
        )

    monkeypatch.setattr(qualification, "write_qualification_archive", qualify)
    monkeypatch.setattr(qualification, "verify_qualification_archive", verify)

    assert qualification.main(
        [
            "qualify",
            "--repo-root",
            str(ROOT),
            "--destination",
            str(destination),
        ]
    ) == 0
    assert qualification.main(
        [
            "verify",
            "--archive",
            str(destination),
            "--expected-identity",
            "sha256:" + "3" * 64,
        ]
    ) == 0
    assert observed == [("qualify", destination), ("verify", destination)]
    assert len(capsys.readouterr().out.splitlines()) == 2

    with pytest.raises(SystemExit):
        qualification.main(
            ["write", "--destination", str(destination)]
        )
    for forbidden in (
        "--model",
        "--provider",
        "--readiness-record",
        "--evaluator-model",
        "--planner-model",
        "--compiler-model",
        "--handoff-destination",
    ):
        with pytest.raises(SystemExit):
            qualification.main(
                [
                    "qualify",
                    "--destination",
                    str(destination),
                    forbidden,
                    "forbidden",
                ]
            )


def test_final_rename_is_no_clobber_and_retains_staging_on_race(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    qualification = _load_script("lm9_typed_fact_carrier_qualification")
    monkeypatch.setattr(
        qualification,
        "_checkout_state",
        lambda _repo_root: ("rename-race-test-commit", True),
    )
    destination = tmp_path / "rename-race"
    staging = destination.with_name(destination.name + ".staging")
    rename = Path.rename

    def racing_rename(path: Path, target: Path):
        if path.resolve() == staging.resolve():
            target.mkdir()
            (target / "racer.txt").write_text("must survive", encoding="utf-8")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", racing_rename)

    with pytest.raises(FileExistsError):
        qualification.write_qualification_archive(
            repo_root=ROOT,
            destination=destination,
        )

    assert (destination / "racer.txt").read_text(encoding="utf-8") == "must survive"
    assert (staging / "checksums.json").is_file()
    source = (SCRIPTS / "lm9_typed_fact_carrier_qualification.py").read_text(
        encoding="utf-8"
    )
    assert ".replace(" not in source


def test_fully_reclosed_claim_substitutions_fail_constructive_verification(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    qualification = _load_script("lm9_typed_fact_carrier_qualification")
    typed_values = qualification.TYPED_VALUES
    monkeypatch.setattr(
        qualification,
        "_checkout_state",
        lambda _repo_root: ("adversarial-test-commit", True),
    )
    destination = tmp_path / "adversarial-qualification"
    qualification.write_qualification_archive(
        repo_root=ROOT,
        destination=destination,
    )
    pristine = {
        path.relative_to(destination).as_posix(): path.read_bytes()
        for path in destination.rglob("*")
        if path.is_file()
    }

    def update_profile_and_registry(
        mutate_profile,
    ) -> None:
        profile_path = destination / "contracts/profile.json"
        registry_path = destination / "contracts/semantic-value-registry.json"
        profile = _json_file(profile_path)
        registry = _json_file(registry_path)
        mutate_profile(profile)
        profile_fingerprint = typed_values.fingerprint(profile)
        registry["schema_evaluator_profile_fingerprint"] = profile_fingerprint
        registry["registry_fingerprint"] = typed_values.fingerprint_without(
            registry, "registry_fingerprint"
        )
        _write_json(typed_values, profile_path, profile)
        _write_json(typed_values, registry_path, registry)
        snapshot = _json_file(destination / "snapshot.json")
        snapshot["profile_fingerprint"] = profile_fingerprint
        snapshot["registry_fingerprint"] = registry["registry_fingerprint"]
        _write_json(typed_values, destination / "snapshot.json", snapshot)
        _reclose_snapshot_and_record(typed_values, destination)

    cases = (
        "helper_source",
        "runtime_jsonschema",
        "type_policy",
        "registry_schema",
        "payload_schema",
        "unit_context_proof",
        "negative_case_set",
        "negative_omitted",
        "negative_renamed",
        "parent_classification",
        "parent_unresolved",
        "radial_result",
        "annotation_result",
        "migration_partition",
        "authority_partition",
        "historical_source",
        "derivative_identity",
        "provider_activity",
        "extra_member",
    )
    for case in cases:
        _restore_archive(destination, pristine)
        if case == "helper_source":
            snapshot = _json_file(destination / "snapshot.json")
            snapshot["helper_source_sha256"] = "sha256:" + "0" * 64
            _write_json(typed_values, destination / "snapshot.json", snapshot)
            _reclose_snapshot_and_record(typed_values, destination)
        elif case == "runtime_jsonschema":
            def mutate_runtime(profile: dict[str, object]) -> None:
                profile["runtime"]["jsonschema_version"] = "0.0.0"
                profile["evaluator"]["jsonschema_distribution_version"] = "0.0.0"

            update_profile_and_registry(mutate_runtime)
            snapshot = _json_file(destination / "snapshot.json")
            snapshot["runtime"]["jsonschema_version"] = "0.0.0"
            _write_json(typed_values, destination / "snapshot.json", snapshot)
            _reclose_snapshot_and_record(typed_values, destination)
        elif case == "type_policy":
            def mutate_type_policy(profile: dict[str, object]) -> None:
                profile["evaluator"]["python_type_checker"]["integer"] = (
                    "type(value) is int or bool"
                )

            update_profile_and_registry(mutate_type_policy)
        elif case == "registry_schema":
            path = destination / "contracts/semantic-value-registry.json"
            registry = _json_file(path)
            row = next(
                item
                for item in registry["entries"]
                if item["schema_id"] == "rook.semantic_string:v1"
            )
            row["schema_document"]["properties"]["value"]["maxLength"] = 17
            row["schema_fingerprint"] = typed_values.fingerprint(
                row["schema_document"]
            )
            registry["registry_fingerprint"] = typed_values.fingerprint_without(
                registry, "registry_fingerprint"
            )
            _write_json(typed_values, path, registry)
            snapshot = _json_file(destination / "snapshot.json")
            snapshot["registry_fingerprint"] = registry["registry_fingerprint"]
            _write_json(typed_values, destination / "snapshot.json", snapshot)
            _reclose_snapshot_and_record(typed_values, destination)
        elif case == "payload_schema":
            path = destination / "contracts/task-payload-schema.json"
            payload = _json_file(path)
            payload["properties"]["facts"]["maxProperties"] = 255
            _write_json(typed_values, path, payload)
            snapshot = _json_file(destination / "snapshot.json")
            snapshot["payload_schema_fingerprint"] = typed_values.fingerprint(payload)
            _write_json(typed_values, destination / "snapshot.json", snapshot)
            _reclose_snapshot_and_record(typed_values, destination)
        elif case == "unit_context_proof":
            path = destination / "source/historical-binding.json"
            binding = _json_file(path)
            binding["unit_context_proof_fingerprint"] = "sha256:" + "8" * 64
            _write_json(typed_values, path, binding)
        elif case == "negative_case_set":
            path = destination / "results/negative-cases.json"
            negative = _json_file(path)
            negative["required_case_set_fingerprint"] = "sha256:" + "9" * 64
            _write_json(typed_values, path, negative)
        elif case in {"negative_omitted", "negative_renamed"}:
            path = destination / "results/negative-cases.json"
            negative = _json_file(path)
            if case == "negative_omitted":
                negative["results"].pop()
            else:
                negative["results"][-1] = dict(negative["results"][-2])
            _write_json(typed_values, path, negative)
        elif case in {"parent_classification", "parent_unresolved"}:
            parent_path = destination / "results/blocked-parent.json"
            parent = _json_file(parent_path)
            record_path = destination / "record.json"
            record = _json_file(record_path)
            if case == "parent_classification":
                parent["classification"] = "probe_candidate_ready"
                record["classification"] = "probe_candidate_ready"
            else:
                parent["unresolved_keys"].pop()
                record["unresolved_keys"] = list(parent["unresolved_keys"])
            _write_json(typed_values, parent_path, parent)
            _write_json(typed_values, record_path, record)
            _reclose_parent_witness(typed_values, destination)
        elif case == "radial_result":
            path = destination / "results/radial-witness.json"
            radial = _json_file(path)
            radial["fact_count"] -= 1
            _write_json(typed_values, path, radial)
        elif case == "annotation_result":
            path = destination / "results/annotation-witness.json"
            annotation = _json_file(path)
            annotation["fact_count"] -= 1
            _write_json(typed_values, path, annotation)
        elif case in {"migration_partition", "authority_partition"}:
            radial_path = destination / "results/radial-witness.json"
            radial = _json_file(radial_path)
            record_path = destination / "record.json"
            record = _json_file(record_path)
            replacement = "sha256:" + ("4" if case == "migration_partition" else "5") * 64
            radial["partition_fingerprint"] = replacement
            record["partition_fingerprint"] = replacement
            if case == "migration_partition":
                radial["migration"].pop()
                record["migration_keys"].pop()
            else:
                record["authority_delta_keys"].pop()
                record["required_delta_keys"].pop()
            _write_json(typed_values, radial_path, radial)
            _write_json(typed_values, record_path, record)
        elif case == "historical_source":
            path = destination / "source/historical-binding.json"
            binding = _json_file(path)
            binding["root_manifest_raw_sha256"] = "sha256:" + "6" * 64
            _write_json(typed_values, path, binding)
            record = _json_file(destination / "record.json")
            record["source_manifest_raw_sha256"] = "sha256:" + "6" * 64
            _write_json(typed_values, destination / "record.json", record)
        elif case == "derivative_identity":
            replacement = "sha256:" + "7" * 64
            binding_path = destination / "source/derivative-binding.json"
            binding = _json_file(binding_path)
            binding["derivative_archive_identity"] = replacement
            _write_json(typed_values, binding_path, binding)
            record = _json_file(destination / "record.json")
            record["derivative_archive_identity"] = replacement
            _write_json(typed_values, destination / "record.json", record)
            parent = _json_file(destination / "results/blocked-parent.json")
            parent["derivative_archive_identity"] = replacement
            _write_json(
                typed_values,
                destination / "results/blocked-parent.json",
                parent,
            )
            _reclose_parent_witness(typed_values, destination)
        elif case == "provider_activity":
            path = destination / "boundary.json"
            boundary = _json_file(path)
            boundary["provider_activity"] = True
            _write_json(typed_values, path, boundary)
        else:
            (destination / "unexpected.json").write_bytes(b"{}\n")

        identity = _reclose_qualification_checksums(
            qualification,
            typed_values,
            destination,
        )
        assert _json_file(destination / "checksums.json")[
            "qualification_identity"
        ] == identity
        with pytest.raises(ValueError, match="qualification"):
            qualification.verify_qualification_archive(
                destination,
                expected_identity=identity,
            )


def test_copied_qualification_refuses_physical_location_substitution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    qualification = _load_script("lm9_typed_fact_carrier_qualification")
    monkeypatch.setattr(
        qualification,
        "_checkout_state",
        lambda _repo_root: ("location-test-commit", True),
    )
    destination = tmp_path / "location-bound"
    written = qualification.write_qualification_archive(
        repo_root=ROOT,
        destination=destination,
    )
    copied = tmp_path / "copied-qualification"
    shutil.copytree(destination, copied)

    with pytest.raises(ValueError, match="bound destination"):
        qualification.verify_qualification_archive(
            copied,
            expected_identity=written.qualification_identity,
        )


def test_qualification_verifies_from_second_checkout_root_at_same_commit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    qualification = _load_script("lm9_typed_fact_carrier_qualification")
    carrier = qualification.CARRIER
    commit = "same-commit-across-checkouts"
    monkeypatch.setattr(
        qualification,
        "_checkout_state",
        lambda _repo_root: (commit, True),
    )
    destination = tmp_path / "checkout-independent-qualification"
    written = qualification.write_qualification_archive(
        repo_root=ROOT,
        destination=destination,
    )

    second_checkout = tmp_path / "second-checkout"
    second_scripts = second_checkout / "scripts"
    second_scripts.mkdir(parents=True)
    shutil.copy2(
        SCRIPTS / "lm9_semantic_typed_values.py",
        second_scripts / "lm9_semantic_typed_values.py",
    )
    shutil.copytree(
        SCRIPTS / "lm9_typed_fact_carrier_contracts",
        second_scripts / "lm9_typed_fact_carrier_contracts",
    )
    shutil.copytree(
        SCRIPTS / "lm9_typed_fact_carrier_fixtures",
        second_scripts / "lm9_typed_fact_carrier_fixtures",
    )
    shutil.copytree(
        SCRIPTS / "lm9b_c_fixtures",
        second_scripts / "lm9b_c_fixtures",
    )
    second_non_r01 = (
        second_checkout
        / "mcp_server/tests/fixtures/lm9b_p/non_r01_ready_recipe.json"
    )
    second_non_r01.parent.mkdir(parents=True)
    shutil.copy2(
        ROOT / "mcp_server/tests/fixtures/lm9b_p/non_r01_ready_recipe.json",
        second_non_r01,
    )

    monkeypatch.setattr(qualification, "_REPO_ROOT", second_checkout)
    monkeypatch.setattr(qualification, "_SCRIPTS_DIR", second_scripts)
    monkeypatch.setattr(carrier, "_REPO_ROOT", second_checkout)
    monkeypatch.setattr(
        carrier,
        "REGISTRY_PATH",
        second_scripts
        / "lm9_typed_fact_carrier_contracts/semantic_value_schema_registry.json",
    )
    monkeypatch.setattr(
        carrier,
        "PAYLOAD_SCHEMA_PATH",
        second_scripts
        / "lm9_typed_fact_carrier_contracts/planner_task_typed_facts_payload_schema.json",
    )
    monkeypatch.setattr(
        carrier,
        "RADIAL_FIXTURE_PATH",
        second_scripts
        / "lm9_typed_fact_carrier_fixtures/radial_successor_task_envelope.json",
    )
    monkeypatch.setattr(
        carrier,
        "ANNOTATION_FIXTURE_PATH",
        second_scripts
        / "lm9_typed_fact_carrier_fixtures/annotation_task_envelope.json",
    )

    verified = qualification.verify_qualification_archive(
        destination,
        expected_identity=written.qualification_identity,
    )

    assert verified.qualification_identity == written.qualification_identity
    controls = _json_file(destination / "results/control-compatibility.json")
    assert [row["fixture_path"] for row in controls["controls"]] == [
        "scripts/lm9b_c_fixtures/r01_recipe.json",
        "mcp_server/tests/fixtures/lm9b_p/non_r01_ready_recipe.json",
    ]
