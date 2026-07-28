from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import copy
import re
import subprocess
import shutil
import sys
from types import SimpleNamespace
from dataclasses import fields
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
FORENSICS_PATH = SCRIPTS / "lm9b_p_governed_resolution_forensics.py"


def _load_forensics():
    if not FORENSICS_PATH.is_file():
        pytest.fail("governed-resolution forensics module is not implemented")
    name = "lm9b_p_governed_resolution_forensics"
    spec = importlib.util.spec_from_file_location(name, FORENSICS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_task4_forensic_types_import_without_operational_dependencies() -> None:
    """Catches read-only forensics importing execution or issuing active types."""

    module = _load_forensics()
    source = FORENSICS_PATH.read_text(encoding="utf-8")
    imported = {
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not {
        "lm9b_p_governed_resolution_probe",
        "lm9b_p_planner_recipe_transfer_probe",
        "lm9b_c_compiler_sufficiency_probe",
    } & imported
    assert [field.name for field in fields(module.ResolutionForensicReconstruction)] == [
        "observed_commit_sha",
        "forensic_commit_sha",
        "planner_call_count",
        "evaluator_call_count",
        "mechanical_status",
        "isolation_status",
        "reconstructed_classification",
        "candidate_recipe_raw_sha256",
        "runtime_call_projection_fingerprint",
        "authored_operational_accounting_fingerprint",
        "controller_conformance",
        "exact_timing_accounting",
        "cost_accounting",
        "cost_stop_compliance",
        "classification_scope",
        "original_attempt_state",
        "official_scientific_checkpoint",
        "ready_proof",
        "compiler_eligibility",
        "gate_fingerprint",
        "isolation_fingerprint",
        "reconstruction_fingerprint",
    ]
    assert [field.name for field in fields(module.ForensicSourceSnapshot)] == [
        "staging_path",
        "destination_path",
        "preflight_members",
        "marker_bytes",
        "candidate_members",
        "before_identity",
    ]
    with pytest.raises(TypeError, match="closure-issued"):
        module.VerifiedHistoricalResolutionPreflightForensics()
    with pytest.raises(TypeError, match="closure-issued"):
        module.VerifiedResolutionForensicSource()
    with pytest.raises(TypeError, match="closure-issued"):
        module.VerifiedRuntimeCallProjection()


def test_task4_verifies_only_the_pinned_physical_historical_preflight(
    tmp_path: Path,
) -> None:
    """Catches a checkpoint authorizing a relocated or self-authored preflight."""

    module = _load_forensics()
    carrier = module.verify_historical_resolution_preflight_forensics(
        repo_root=ROOT,
        preflight_archive=module.OBSERVED_PREFLIGHT_ARCHIVE,
        expected_preflight_fingerprint=module.OBSERVED_PREFLIGHT_FINGERPRINT,
    )
    assert type(carrier) is module.VerifiedHistoricalResolutionPreflightForensics

    copied = tmp_path / "copied-preflight"
    shutil.copytree(module.OBSERVED_PREFLIGHT_ARCHIVE, copied)
    with pytest.raises(ValueError, match="pin differs"):
        module.verify_historical_resolution_preflight_forensics(
            repo_root=ROOT,
            preflight_archive=copied,
            expected_preflight_fingerprint=module.OBSERVED_PREFLIGHT_FINGERPRINT,
        )
    with pytest.raises(ValueError, match="pin differs"):
        module.verify_historical_resolution_preflight_forensics(
            repo_root=ROOT,
            preflight_archive=module.OBSERVED_PREFLIGHT_ARCHIVE,
            expected_preflight_fingerprint="sha256:" + "0" * 64,
        )


def _historical_carrier(module):
    return module.verify_historical_resolution_preflight_forensics(
        repo_root=ROOT,
        preflight_archive=module.OBSERVED_PREFLIGHT_ARCHIVE,
        expected_preflight_fingerprint=module.OBSERVED_PREFLIGHT_FINGERPRINT,
    )


def _reclose_historical_preflight(module, members, record):
    record["instrument_fingerprint"] = module.PLANNER_SUPPORT.fingerprint(
        record["instrument_contracts"]
    )
    record["attempt"]["attempt_fingerprint"] = module.PLANNER_SUPPORT.fingerprint(
        {
            "instrument_fingerprint": record["instrument_fingerprint"],
            "attempt_id": record["attempt"]["attempt_id"],
            "canonical_destination": record["attempt"]["canonical_destination"],
        }
    )
    record["preflight_fingerprint"] = module.PLANNER_SUPPORT.fingerprint_without(
        record, "preflight_fingerprint"
    )
    changed = dict(members)
    changed["record.json"] = module._canonical_bytes(record)
    checksums = json.loads(changed["checksums.json"])
    checksums["members"] = [
        {
            "path": name,
            "raw_sha256": "sha256:"
            + hashlib.sha256(changed[name]).hexdigest(),
        }
        for name in ("initial-request.json", "record.json")
    ]
    changed["checksums.json"] = module._canonical_bytes(checksums)
    return changed


def test_task4_historical_reconstruction_rejects_authored_source_claim_drift() -> None:
    """The Git-derived source identity must equal the authored comparison target."""

    module = _load_forensics()
    _archive, members, _identity = module._flat_snapshot(
        module.OBSERVED_PREFLIGHT_ARCHIVE,
        expected=module._PREFLIGHT_MEMBERS,
    )
    git_blobs, _manifest = module._git_blob_map(ROOT)
    target = "scripts/lm9b_p_governed_resolution_support.py"
    record = json.loads(members["record.json"])
    source = module._source_bytes(
        git_blobs[target], "render_planner_revision_request"
    )
    record["instrument_contracts"]["planner"][
        "revision_renderer_source_fingerprint"
    ] = "sha256:" + hashlib.sha256(source + b"substituted").hexdigest()
    changed_members = _reclose_historical_preflight(module, members, record)
    with pytest.raises(
        ValueError, match="historical instrument reconstruction differs"
    ):
        module._verify_historical_preflight_projection(
            repo=ROOT,
            archive=module.OBSERVED_PREFLIGHT_ARCHIVE,
            members=changed_members,
            git_blobs=git_blobs,
        )


@pytest.mark.parametrize(
    "relative",
    [
        "scripts/lm9b_p_governed_resolution_contracts/isolation_policy.json",
        (
            "scripts/lm9b_p_governed_resolution_contracts/"
            "planner_revision_evaluation_rubric.json"
        ),
        (
            "scripts/lm9_typed_fact_carrier_contracts/"
            "semantic_value_schema_registry.json"
        ),
        (
            "scripts/lm9_typed_fact_carrier_contracts/"
            "planner_task_typed_facts_payload_schema.json"
        ),
        (
            "scripts/lm9_typed_fact_carrier_fixtures/"
            "radial_successor_task_envelope.json"
        ),
    ],
)
def test_task4_historical_data_git_blobs_are_constructive_roots(
    relative: str,
) -> None:
    """Historical Git data must equal the reviewed producer's exact Git bytes."""

    module = _load_forensics()
    git_blobs, _manifest = module._git_blob_map(ROOT)
    changed_blobs = dict(git_blobs)
    changed_blobs[relative] = git_blobs[relative] + b" "
    with pytest.raises(
        ValueError,
        match=re.escape(
            f"historical Git producer bytes differ: {relative}"
        ),
    ):
        module._reconstruct_historical_instrument_and_request(
            repo=ROOT,
            git_blobs=changed_blobs,
        )


def test_task4_historical_renderer_git_blob_is_bound_to_executing_renderer() -> None:
    """The historical renderer root must equal the producer that renders bytes."""

    module = _load_forensics()
    git_blobs, _manifest = module._git_blob_map(ROOT)
    relative = "scripts/lm9b_p_governed_resolution_support.py"
    changed_blobs = dict(git_blobs)
    changed_blobs[relative] = git_blobs[relative].replace(
        b"Revise the exact parent Planner recipe",
        b"Rework the exact parent Planner recipe",
        1,
    )
    assert changed_blobs[relative] != git_blobs[relative]
    with pytest.raises(
        ValueError,
        match=re.escape(f"historical Git producer bytes differ: {relative}"),
    ):
        module._reconstruct_historical_instrument_and_request(
            repo=ROOT,
            git_blobs=changed_blobs,
        )


def test_task4_historical_producer_graph_reaches_data_and_authority_globals() -> None:
    """The compatible producer graph must contain the inputs its roots consume."""

    module = _load_forensics()
    git_blobs, _manifest = module._git_blob_map(ROOT)
    relative = "scripts/lm9b_p_governed_resolution_artifacts.py"
    historical, _executed = module._reachable_artifact_producer_symbols(
        git_blobs[relative],
        module._HISTORICAL_ARTIFACT_PRODUCER_ROOTS,
    )
    assert {
        "HISTORICAL_CARRIER_QUALIFICATION_IDENTITY",
        "ISOLATION_POLICY_PATH",
        "EVALUATION_RUBRIC_PATH",
        "SUCCESSOR_ENVELOPE_PATH",
        "CARRIER",
        "QUALIFICATION",
        "SUPPORT",
        "CONT_ARTIFACTS",
        "PLANNER_SUPPORT",
    } <= historical


def test_task4_historical_request_is_the_actual_renderer_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The renderer output, not an archived request claim, drives comparison."""

    module = _load_forensics()
    original = module.ARTIFACTS.SUPPORT.render_planner_revision_request

    def substituted(inputs):
        rendered = original(inputs)
        payload = json.loads(rendered.raw_bytes)
        payload["brief"] += " substituted by producer"
        raw = module._canonical_bytes(payload)
        return module.SUPPORT.RenderedRevisionRequest(
            renderer_id=rendered.renderer_id,
            payload=payload,
            raw_bytes=raw,
            raw_sha256=module._sha256(raw),
            canonical_fingerprint=module.PLANNER_SUPPORT.fingerprint(payload),
        )

    monkeypatch.setattr(
        module.ARTIFACTS.SUPPORT,
        "render_planner_revision_request",
        substituted,
    )
    _archive, members, _identity = module._flat_snapshot(
        module.OBSERVED_PREFLIGHT_ARCHIVE,
        expected=module._PREFLIGHT_MEMBERS,
    )
    git_blobs, _manifest = module._git_blob_map(ROOT)
    with pytest.raises(
        ValueError, match="historical instrument reconstruction differs"
    ):
        module._verify_historical_preflight_projection(
            repo=ROOT,
            archive=module.OBSERVED_PREFLIGHT_ARCHIVE,
            members=members,
            git_blobs=git_blobs,
        )


def test_task4_execution_capability_ledger_rejects_a_missing_producer() -> None:
    """Deleting a callable owner must not silently weaken checkout closure."""

    module = _load_forensics()
    if not hasattr(module, "_execution_capability_ledger"):
        pytest.fail("forensic execution capability ledger is absent")
    ledger = module._execution_capability_ledger()
    assert any(
        row["capability_id"] == "historical_source_verifier"
        and row["relative_path"]
        == "scripts/lm9b_p_evaluator_only_continuation_artifacts.py"
        for row in ledger
    )
    reduced = tuple(
        row
        for row in ledger
        if row["capability_id"] != "historical_source_verifier"
    )
    with pytest.raises(ValueError, match="execution capability ledger is incomplete"):
        module._validate_execution_capability_ledger(reduced)


def test_task4_execution_capability_ledger_binds_the_actual_callable_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A canonical import must not hide the module object actually invoked."""

    module = _load_forensics()
    substituted = tmp_path / "substituted_continuation_artifacts.py"
    substituted.write_text("# not the reviewed verifier\n", encoding="utf-8")
    monkeypatch.setattr(
        module.ARTIFACTS,
        "CONT_ARTIFACTS",
        SimpleNamespace(__file__=str(substituted)),
    )
    with pytest.raises(ValueError, match="execution callable alias differs"):
        module._execution_capability_ledger()


def test_task4_historical_artifact_transitive_hash_producer_is_git_bound() -> None:
    """A helper reached by source loading may not sit outside the producer graph."""

    module = _load_forensics()
    git_blobs, _manifest = module._git_blob_map(ROOT)
    relative = "scripts/lm9b_p_governed_resolution_artifacts.py"
    changed_blobs = dict(git_blobs)
    changed_blobs[relative] = git_blobs[relative].replace(
        b'hashlib.sha256(raw).hexdigest()',
        b'hashlib.sha512(raw).hexdigest()',
        1,
    )
    assert changed_blobs[relative] != git_blobs[relative]
    with pytest.raises(
        ValueError,
        match=r"historical Git producer artifact capability differs: _sha256",
    ):
        module._reconstruct_historical_instrument_and_request(
            repo=ROOT,
            git_blobs=changed_blobs,
        )


def test_task4_historical_artifact_global_identity_is_git_bound() -> None:
    """A global consumed by a reached producer is part of the producer graph."""

    module = _load_forensics()
    git_blobs, _manifest = module._git_blob_map(ROOT)
    relative = "scripts/lm9b_p_governed_resolution_artifacts.py"
    changed_blobs = dict(git_blobs)
    changed_blobs[relative] = git_blobs[relative].replace(
        b"sha256:ad12f0cec491b64f51982b7069acfa1301c1d577071cff9498cf7fba260446e1",
        b"sha256:ad12f0cec491b64f51982b7069acfa1301c1d577071cff9498cf7fba260446e2",
        1,
    )
    assert changed_blobs[relative] != git_blobs[relative]
    with pytest.raises(
        ValueError,
        match=(
            "historical Git producer artifact capability differs: "
            "HISTORICAL_CARRIER_QUALIFICATION_IDENTITY"
        ),
    ):
        module._reconstruct_historical_instrument_and_request(
            repo=ROOT,
            git_blobs=changed_blobs,
        )


def test_task4_historical_artifact_bootstrap_statements_are_git_bound() -> None:
    """Executable module bootstrap is a producer even without a bound symbol."""

    module = _load_forensics()
    git_blobs, _manifest = module._git_blob_map(ROOT)
    relative = "scripts/lm9b_p_governed_resolution_artifacts.py"
    changed_blobs = dict(git_blobs)
    changed_blobs[relative] = git_blobs[relative].replace(
        b"sys.path.insert(0, str(_import_path))",
        b"sys.path.append(str(_import_path))",
        1,
    )
    assert changed_blobs[relative] != git_blobs[relative]
    with pytest.raises(
        ValueError,
        match="historical Git producer artifact bootstrap differs",
    ):
        module._reconstruct_historical_instrument_and_request(
            repo=ROOT,
            git_blobs=changed_blobs,
        )


def test_task4_historical_artifact_mutation_assignments_are_bootstrap_bound() -> None:
    """A subscript mutation is executable bootstrap, not a declaration."""

    module = _load_forensics()
    git_blobs, _manifest = module._git_blob_map(ROOT)
    relative = "scripts/lm9b_p_governed_resolution_artifacts.py"
    changed_blobs = dict(git_blobs)
    changed_blobs[relative] = git_blobs[relative].replace(
        b"PLANNER_SUPPORT.fingerprint(\n    _READY_PROOF_VALUE\n)",
        b"PLANNER_SUPPORT.sha256_prefixed(\n    _READY_PROOF_VALUE\n)",
        1,
    )
    assert changed_blobs[relative] != git_blobs[relative]
    with pytest.raises(
        ValueError,
        match="historical Git producer artifact bootstrap differs",
    ):
        module._reconstruct_historical_instrument_and_request(
            repo=ROOT,
            git_blobs=changed_blobs,
        )


@pytest.mark.parametrize(
    "injected_statement",
    [
        (
            '_UNUSED = _READY_PROOF_VALUE.__setitem__('
            '"schema_id", "forged")'
        ),
        "_UNUSED = _MISSING_BOOTSTRAP_NAME",
        "(_UNUSED_FIRST, _UNUSED_SECOND) = _READY_PROOF_VALUE",
        (
            'def _unreferenced(value=_READY_PROOF_VALUE.__setitem__('
            '"schema_id", "forged")):\n    return value'
        ),
        (
            '@_READY_PROOF_VALUE.__setitem__("schema_id", "forged")\n'
            'def _unreferenced():\n    return None'
        ),
        (
            'class _Unreferenced('
            '_READY_PROOF_VALUE.__setitem__("schema_id", "forged")'
            '):\n    pass'
        ),
        "import unreviewed_bootstrap_module",
    ],
    ids=(
        "mutating_name_binding_rhs",
        "name_resolution",
        "destructuring_iteration",
        "executable_function_default",
        "executable_function_decorator",
        "executable_class_construction",
        "import_execution",
    ),
)
def test_task4_historical_executable_statements_are_bootstrap_bound(
    injected_statement: str,
) -> None:
    """Unreferenced import-time execution remains in causal custody."""

    module = _load_forensics()
    git_blobs, _manifest = module._git_blob_map(ROOT)
    relative = "scripts/lm9b_p_governed_resolution_artifacts.py"
    changed_blobs = dict(git_blobs)
    changed_blobs[relative] = (
        git_blobs[relative]
        + b"\n\n"
        + injected_statement.encode("utf-8")
        + b"\n"
    )
    with pytest.raises(
        ValueError,
        match="historical Git producer artifact bootstrap differs",
    ):
        module._reconstruct_historical_instrument_and_request(
            repo=ROOT,
            git_blobs=changed_blobs,
        )


@pytest.mark.parametrize(
    ("reviewed", "substituted"),
    [
        (
            b"import lm9b_p_governed_resolution_archive_evidence as "
            b"ARCHIVE_EVIDENCE",
            b"import os as ARCHIVE_EVIDENCE",
        ),
        (
            b"ARCHIVE_EVIDENCE_PROFILE_PATH = (\n"
            b"    _SCRIPTS_DIR\n"
            b'    / "lm9b_p_governed_resolution_contracts"\n'
            b'    / "archive_evidence_resource_profile.json"\n'
            b")",
            b"ARCHIVE_EVIDENCE_PROFILE_PATH = "
            b'_READY_PROOF_VALUE.__setitem__("schema_id", "forged")',
        ),
        (
            b"@dataclass(frozen=True)\n"
            b"class ReconstructedResolutionAttempt:",
            b'@_READY_PROOF_VALUE.__setitem__("schema_id", "forged")\n'
            b"@dataclass(frozen=True)\n"
            b"class ReconstructedResolutionAttempt:",
        ),
        (
            b"RESOLUTION_ARCHIVE_MEMBERS = "
            b"ARCHIVE_EVIDENCE.RESOLUTION_ARCHIVE_MEMBERS",
            b"RESOLUTION_ARCHIVE_MEMBERS = ("
            b'_READY_PROOF_VALUE.__setitem__("schema_id", "forged"), '
            b"ARCHIVE_EVIDENCE.RESOLUTION_ARCHIVE_MEMBERS)[1]",
        ),
    ],
    ids=(
        "current_only_import",
        "current_only_profile_assignment",
        "current_only_class",
        "current_migrated_archive_members",
    ),
)
def test_task4_current_only_bootstrap_deltas_have_exact_reviewed_identity(
    reviewed: bytes,
    substituted: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An approved binding name cannot hide different import-time execution."""

    module = _load_forensics()
    git_blobs, _manifest = module._git_blob_map(ROOT)
    relative = "scripts/lm9b_p_governed_resolution_artifacts.py"
    original_git_object_at = module._git_object_at

    def changed_current_blob(repo: Path, commit: str, path: str) -> bytes:
        raw = original_git_object_at(repo, commit, path)
        if path != relative:
            return raw
        assert raw.count(reviewed) == 1
        changed = raw.replace(reviewed, substituted, 1)
        assert changed != raw
        return changed

    monkeypatch.setattr(module, "_git_object_at", changed_current_blob)
    with pytest.raises(
        ValueError,
        match="historical Git producer bootstrap delta differs",
    ):
        module._reconstruct_historical_instrument_and_request(
            repo=ROOT,
            git_blobs=git_blobs,
        )


def test_task4_execution_capability_ledger_binds_isolation_callable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reviewed module cannot hide a substituted callable actually invoked."""

    module = _load_forensics()
    original = module.SUPPORT.evaluate_resolution_isolation

    def substituted(*args, **kwargs):
        return original(*args, **kwargs)

    monkeypatch.setattr(
        module.SUPPORT,
        "evaluate_resolution_isolation",
        substituted,
    )
    with pytest.raises(ValueError, match="execution callable binding differs"):
        module._execution_capability_ledger()


def test_task4_execution_capability_ledger_binds_imported_callable_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two callables from one reviewed owner module are not interchangeable."""

    module = _load_forensics()
    monkeypatch.setattr(
        module.PLANNER_SUPPORT,
        "canonical_fingerprint",
        module.PLANNER_SUPPORT.sha256_prefixed,
    )
    with pytest.raises(ValueError, match="execution callable binding differs"):
        module._execution_capability_ledger()


@pytest.mark.parametrize(
    ("dotted", "replacement"),
    [
        ("verified_inputs.inputs_fingerprint", "sha256:" + "1" * 64),
        ("isolation.definition_fingerprint", "sha256:" + "2" * 64),
        ("evaluator.rubric_fingerprint", "sha256:" + "3" * 64),
        ("readiness.route_manifest_fingerprint", "sha256:" + "4" * 64),
        ("decision.outcome_equations_contract_id", "substituted:v1"),
        ("archive.finalization_equation", "substituted:v1"),
        ("ready_proof.contract_id", "substituted:v1"),
    ],
)
def test_task4_historical_manifest_claims_are_derived_not_self_authenticated(
    dotted: str,
    replacement: object,
) -> None:
    """Each row must reach the derived-manifest comparison, not a hash pin."""

    module = _load_forensics()
    _archive, members, _identity = module._flat_snapshot(
        module.OBSERVED_PREFLIGHT_ARCHIVE,
        expected=module._PREFLIGHT_MEMBERS,
    )
    git_blobs, _manifest = module._git_blob_map(ROOT)
    record = json.loads(members["record.json"])
    module._set_mapping_path(record["instrument_contracts"], dotted, replacement)
    changed = _reclose_historical_preflight(module, members, record)
    with pytest.raises(
        ValueError, match="historical instrument reconstruction differs"
    ):
        module._verify_historical_preflight_projection(
            repo=ROOT,
            archive=module.OBSERVED_PREFLIGHT_ARCHIVE,
            members=changed,
            git_blobs=git_blobs,
        )


def test_task4_historical_authored_request_must_equal_the_rerendered_root() -> None:
    """A reclosed authored request remains only a comparison target."""

    module = _load_forensics()
    _archive, members, _identity = module._flat_snapshot(
        module.OBSERVED_PREFLIGHT_ARCHIVE,
        expected=module._PREFLIGHT_MEMBERS,
    )
    git_blobs, _manifest = module._git_blob_map(ROOT)
    record = json.loads(members["record.json"])
    request = json.loads(members["initial-request.json"])
    request["brief"] += " substituted"
    changed = dict(members)
    changed["initial-request.json"] = module._canonical_bytes(request)
    request_sha = module._sha256(changed["initial-request.json"])
    record["initial_request_raw_sha256"] = request_sha
    record["instrument_contracts"]["planner"][
        "initial_request_raw_sha256"
    ] = request_sha
    changed = _reclose_historical_preflight(module, changed, record)
    with pytest.raises(
        ValueError, match="historical instrument reconstruction differs"
    ):
        module._verify_historical_preflight_projection(
            repo=ROOT,
            archive=module.OBSERVED_PREFLIGHT_ARCHIVE,
            members=changed,
            git_blobs=git_blobs,
        )


def test_task4_historical_checksum_schema_is_an_observed_constant() -> None:
    """Would pass if the checksum schema were copied from its own claim."""

    module = _load_forensics()
    _archive, members, _identity = module._flat_snapshot(
        module.OBSERVED_PREFLIGHT_ARCHIVE,
        expected=module._PREFLIGHT_MEMBERS,
    )
    git_blobs, _manifest = module._git_blob_map(ROOT)
    changed = dict(members)
    checksums = json.loads(changed["checksums.json"])
    checksums["schema"] = "rook.substituted_checksums:v1"
    changed["checksums.json"] = module._canonical_bytes(checksums)
    with pytest.raises(ValueError, match="checksum schema"):
        module._verify_historical_preflight_projection(
            repo=ROOT,
            archive=module.OBSERVED_PREFLIGHT_ARCHIVE,
            members=changed,
            git_blobs=git_blobs,
        )


def test_task4_loads_a_closed_read_only_copy_of_retained_staging(
    tmp_path: Path,
) -> None:
    """Catches checksum-only acceptance or source mutation during custody."""

    module = _load_forensics()
    historical = _historical_carrier(module)
    copied = tmp_path / module.OBSERVED_STAGING.name
    shutil.copytree(module.OBSERVED_STAGING, copied)
    before = module._recursive_snapshot(copied)
    source = module.load_verified_resolution_forensic_source(
        historical_preflight=historical,
        staging_dir=copied,
        expected_marker_sha256=module.OBSERVED_MARKER_SHA256,
        expected_candidate_checksums_sha256=(
            module.OBSERVED_CANDIDATE_CHECKSUMS_SHA256
        ),
    )
    assert type(source) is module.VerifiedResolutionForensicSource
    assert module._recursive_snapshot(copied) == before

    (copied / "unexpected").mkdir()
    with pytest.raises(ValueError, match="membership"):
        module.load_verified_resolution_forensic_source(
            historical_preflight=historical,
            staging_dir=copied,
            expected_marker_sha256=module.OBSERVED_MARKER_SHA256,
            expected_candidate_checksums_sha256=(
                module.OBSERVED_CANDIDATE_CHECKSUMS_SHA256
            ),
        )


def test_task4_reconstructs_the_six_turn_candidate_without_writes(
    tmp_path: Path,
) -> None:
    """Catches trusting authored outcome files instead of model root evidence."""

    module = _load_forensics()
    historical = _historical_carrier(module)
    copied = tmp_path / module.OBSERVED_STAGING.name
    shutil.copytree(module.OBSERVED_STAGING, copied)
    source = module.load_verified_resolution_forensic_source(
        historical_preflight=historical,
        staging_dir=copied,
        expected_marker_sha256=module.OBSERVED_MARKER_SHA256,
        expected_candidate_checksums_sha256=(
            module.OBSERVED_CANDIDATE_CHECKSUMS_SHA256
        ),
    )
    before = module._recursive_snapshot(copied)
    commit = module._current_commit(ROOT)
    result = module._reconstruct_resolution_forensic_candidate_unsealed(
        capability=module._consume_forensic_source(source),
        repo_root=ROOT,
        forensic_commit_sha=commit,
        require_executing_checkout=False,
    )
    assert result.planner_call_count == 6
    assert result.evaluator_call_count == 0
    assert result.mechanical_status == "accepted"
    assert result.isolation_status == "isolation_rejected"
    assert (
        result.reconstructed_classification
        == "probe_resolution_isolation_failure"
    )
    assert result.controller_conformance == "not_verified"
    assert result.exact_timing_accounting == "not_verified"
    assert result.cost_accounting == "preserved_unverified"
    assert result.cost_stop_compliance == "not_verified"
    assert result.classification_scope == "candidate_level_deterministic_projection"
    assert result.original_attempt_state == "post_dispatch_unsealed"
    assert result.official_scientific_checkpoint == "absent"
    assert result.ready_proof == "prohibited"
    assert result.compiler_eligibility is False
    assert module._recursive_snapshot(copied) == before


def test_task4_runtime_files_are_the_causal_call_projection(
    tmp_path: Path,
) -> None:
    """Would pass if the authored call ledger remained a derivation input."""

    module = _load_forensics()
    historical = _historical_carrier(module)
    copied = tmp_path / module.OBSERVED_STAGING.name
    shutil.copytree(module.OBSERVED_STAGING, copied)
    source = module.load_verified_resolution_forensic_source(
        historical_preflight=historical,
        staging_dir=copied,
        expected_marker_sha256=module.OBSERVED_MARKER_SHA256,
        expected_candidate_checksums_sha256=(
            module.OBSERVED_CANDIDATE_CHECKSUMS_SHA256
        ),
    )
    capability = module._consume_forensic_source(source)
    files, _identity = module._recursive_snapshot(copied)
    runtime_files = {
        path.removeprefix(".resolution-runtime/calls/"): raw
        for path, raw in files.items()
        if path.startswith(".resolution-runtime/calls/")
    }
    authored = json.loads(
        capability.source.candidate_members["call-ledger.json"]
    )
    contracts = capability.historical.record["instrument_contracts"]
    proof = module.derive_verified_runtime_call_projection(
        runtime_call_files=runtime_files,
        authored_call_ledger=authored,
        instrument_contracts=contracts,
    )
    assert type(proof) is module.VerifiedRuntimeCallProjection
    value = module._consume_verified_runtime_call_projection(proof)
    assert value["planner_call_count"] == 6
    assert value["evaluator_call_count"] == 0
    assert len(value["unverified_operational_accounting"]) == 6

    changed = copy.deepcopy(authored)
    changed["calls"][0]["assistant_message"]["content"] = "substituted"
    with pytest.raises(ValueError, match="causal call projection differs"):
        module._derive_runtime_call_projection_value(
            runtime_call_files=runtime_files,
            authored_call_ledger=changed,
            instrument_contracts=contracts,
        )

    accounting_only = copy.deepcopy(authored)
    accounting_only["calls"][0]["elapsed_ms"] += 1
    accounting_only["calls"][0]["usage"]["cost_usd"] += 1.0
    accounting_value = module._derive_runtime_call_projection_value(
        runtime_call_files=runtime_files,
        authored_call_ledger=accounting_only,
        instrument_contracts=contracts,
    )
    assert accounting_value["causal_rows"] == value["causal_rows"]
    assert (
        accounting_value["unverified_operational_accounting"]
        != value["unverified_operational_accounting"]
    )
    forged = object.__new__(module.VerifiedRuntimeCallProjection)
    with pytest.raises(ValueError, match="was not issued"):
        module._consume_verified_runtime_call_projection(forged)


def test_task4_public_reconstruction_refuses_dirty_or_alternate_checkout(
    tmp_path: Path,
) -> None:
    """Would pass if caller-supplied HEAD authenticated imported module bytes."""

    module = _load_forensics()
    historical = _historical_carrier(module)
    copied = tmp_path / module.OBSERVED_STAGING.name
    shutil.copytree(module.OBSERVED_STAGING, copied)
    source = module.load_verified_resolution_forensic_source(
        historical_preflight=historical,
        staging_dir=copied,
        expected_marker_sha256=module.OBSERVED_MARKER_SHA256,
        expected_candidate_checksums_sha256=(
            module.OBSERVED_CANDIDATE_CHECKSUMS_SHA256
        ),
    )
    commit = module._current_commit(ROOT)
    dirty_probe = ROOT / "scripts" / ".forensic-dirty-probe"
    dirty_probe.write_bytes(b"untracked")
    try:
        with pytest.raises(ValueError, match="executing checkout is dirty"):
            module.reconstruct_resolution_forensic_candidate(
                source=source,
                repo_root=ROOT,
                forensic_commit_sha=commit,
            )
    finally:
        dirty_probe.unlink(missing_ok=True)

    alternate = tmp_path / "alternate-checkout"
    subprocess.run(
        ["git", "clone", "--quiet", "--no-hardlinks", str(ROOT), str(alternate)],
        check=True,
    )
    subprocess.run(
        ["git", "checkout", "--quiet", commit],
        cwd=alternate,
        check=True,
    )
    with pytest.raises(ValueError, match="executing checkout root differs"):
        module.reconstruct_resolution_forensic_candidate(
            source=source,
            repo_root=alternate,
            forensic_commit_sha=commit,
        )


def test_task4_every_execution_identity_path_materializes_as_lf() -> None:
    """Clean Windows checkout bytes must equal the reviewed Git blobs."""

    module = _load_forensics()
    for relative in module._FORENSIC_EXECUTION_PATHS:
        if not relative.endswith((".py", ".json")):
            continue
        result = subprocess.run(
            ["git", "check-attr", "eol", "--", relative],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert result.endswith(": eol: lf"), relative
        assert b"\r\n" not in (ROOT / relative).read_bytes(), relative


def test_task4_public_reconstruction_succeeds_from_clean_reviewed_checkout() -> None:
    """Exercise the real public checkout/callable gate when HEAD is reviewable."""

    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    if status:
        pytest.skip("public success witness requires a clean reviewed checkout")
    module = _load_forensics()
    historical = _historical_carrier(module)
    source = module.load_verified_resolution_forensic_source(
        historical_preflight=historical,
        staging_dir=module.OBSERVED_STAGING,
        expected_marker_sha256=module.OBSERVED_MARKER_SHA256,
        expected_candidate_checksums_sha256=(
            module.OBSERVED_CANDIDATE_CHECKSUMS_SHA256
        ),
    )
    result = module.reconstruct_resolution_forensic_candidate(
        source=source,
        repo_root=ROOT,
        forensic_commit_sha=module._current_commit(ROOT),
    )
    assert result.reconstructed_classification == (
        "probe_resolution_isolation_failure"
    )
    assert result.classification_scope == "candidate_level_deterministic_projection"
    assert result.controller_conformance == "not_verified"
    assert result.original_attempt_state == "post_dispatch_unsealed"
    assert result.official_scientific_checkpoint == "absent"
    assert result.ready_proof == "prohibited"
    assert result.compiler_eligibility is False


def test_task4_forensic_capabilities_are_unforgeable_and_inert(
    tmp_path: Path,
) -> None:
    """Catches forensic evidence becoming an execution or ready-proof carrier."""

    module = _load_forensics()
    historical = _historical_carrier(module)
    copied = tmp_path / module.OBSERVED_STAGING.name
    shutil.copytree(module.OBSERVED_STAGING, copied)
    source = module.load_verified_resolution_forensic_source(
        historical_preflight=historical,
        staging_dir=copied,
        expected_marker_sha256=module.OBSERVED_MARKER_SHA256,
        expected_candidate_checksums_sha256=(
            module.OBSERVED_CANDIDATE_CHECKSUMS_SHA256
        ),
    )
    forged_historical = object.__new__(
        module.VerifiedHistoricalResolutionPreflightForensics
    )
    forged_source = object.__new__(module.VerifiedResolutionForensicSource)
    with pytest.raises(ValueError, match="was not issued"):
        module.load_verified_resolution_forensic_source(
            historical_preflight=forged_historical,
            staging_dir=copied,
            expected_marker_sha256=module.OBSERVED_MARKER_SHA256,
            expected_candidate_checksums_sha256=(
                module.OBSERVED_CANDIDATE_CHECKSUMS_SHA256
            ),
        )
    with pytest.raises(ValueError, match="was not issued"):
        module.reconstruct_resolution_forensic_candidate(
            source=forged_source,
            repo_root=ROOT,
            forensic_commit_sha=module._current_commit(ROOT),
        )

    for carrier in (historical, source):
        with pytest.raises(TypeError, match="verified resolution preflight"):
            module.ARTIFACTS.reserve_resolution_staging(carrier)
        with pytest.raises(TypeError, match="sealed resolution checkpoint"):
            module.ARTIFACTS.issue_resolution_ready_proof(
                carrier,
                preflight_archive=module.OBSERVED_PREFLIGHT_ARCHIVE,
                expected_preflight_fingerprint=module.OBSERVED_PREFLIGHT_FINGERPRINT,
            )
        with pytest.raises(TypeError, match="wrong type"):
            module.ARTIFACTS.consume_resolution_ready_proof(
                carrier,
                preflight_archive=module.OBSERVED_PREFLIGHT_ARCHIVE,
                expected_preflight_fingerprint=module.OBSERVED_PREFLIGHT_FINGERPRINT,
            )
        with pytest.raises(TypeError, match="verified resolution preflight"):
            module.ARTIFACTS.seal_resolution_checkpoint(
                preflight=carrier,
                invocation_binding={},
                readiness_record={},
                readiness_verified_at="",
                planner_session=None,
                evaluator_result=None,
                isolation_result=None,
                checkpoint_gate=None,
                candidate_recipe_bytes=None,
                call_ledger=(),
                derived_stop_cause="mechanically_rejected",
                classification="probe_mechanically_rejected",
            )

    assert not any(
        name.startswith("_issue_")
        for name, value in vars(module).items()
        if callable(value)
    )


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("marker", "marker fingerprint"),
        ("candidate_checksum", "retained bytes differ"),
        ("missing_marker", "marker is absent"),
        ("missing_candidate", "retained bytes differ"),
        ("missing_runtime", "retained bytes differ"),
        ("extra_file", "file membership"),
    ],
)
def test_task4_forensic_source_mutations_refuse_before_issuance(
    tmp_path: Path,
    mutation: str,
    match: str,
) -> None:
    """Catches a nearby checksum or directory being mistaken for root custody."""

    module = _load_forensics()
    historical = _historical_carrier(module)
    copied = tmp_path / module.OBSERVED_STAGING.name
    shutil.copytree(module.OBSERVED_STAGING, copied)
    if mutation == "marker":
        (copied / "post_dispatch_unsealed.json").write_bytes(b"{}")
    elif mutation == "candidate_checksum":
        (copied / ".archive-candidate" / "checksums.json").write_bytes(b"{}")
    elif mutation == "missing_marker":
        (copied / "post_dispatch_unsealed.json").unlink()
    elif mutation == "missing_candidate":
        (copied / ".archive-candidate" / "source.json").unlink()
    elif mutation == "missing_runtime":
        (copied / ".resolution-runtime" / "readiness.json").unlink()
    else:
        (copied / "unexpected.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match=match):
        module.load_verified_resolution_forensic_source(
            historical_preflight=historical,
            staging_dir=copied,
            expected_marker_sha256=module.OBSERVED_MARKER_SHA256,
            expected_candidate_checksums_sha256=(
                module.OBSERVED_CANDIDATE_CHECKSUMS_SHA256
            ),
        )


def test_task4_forensic_source_rejects_destination_presence_and_reparse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches following aliases or loading evidence after publication appeared."""

    module = _load_forensics()
    historical = _historical_carrier(module)
    copied = tmp_path / module.OBSERVED_STAGING.name
    shutil.copytree(module.OBSERVED_STAGING, copied)
    destination = tmp_path / "destination"
    destination.mkdir()
    monkeypatch.setattr(module, "OBSERVED_DESTINATION", destination)
    with pytest.raises(ValueError, match="destination is present"):
        module.load_verified_resolution_forensic_source(
            historical_preflight=historical,
            staging_dir=copied,
            expected_marker_sha256=module.OBSERVED_MARKER_SHA256,
            expected_candidate_checksums_sha256=(
                module.OBSERVED_CANDIDATE_CHECKSUMS_SHA256
            ),
        )
    monkeypatch.setattr(
        module,
        "OBSERVED_DESTINATION",
        module.OBSERVED_RESOLUTION_ROOT / module.OBSERVED_ATTEMPT_ID,
    )
    alias = copied / "alias"
    try:
        os.symlink(copied / ".archive-candidate", alias, target_is_directory=True)
    except OSError:
        pytest.skip("Windows symlink creation is unavailable")
    with pytest.raises(ValueError, match="reparse entry"):
        module.load_verified_resolution_forensic_source(
            historical_preflight=historical,
            staging_dir=copied,
            expected_marker_sha256=module.OBSERVED_MARKER_SHA256,
            expected_candidate_checksums_sha256=(
                module.OBSERVED_CANDIDATE_CHECKSUMS_SHA256
            ),
        )
