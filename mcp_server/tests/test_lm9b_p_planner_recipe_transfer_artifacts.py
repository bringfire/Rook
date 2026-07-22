from __future__ import annotations

import importlib.util
import builtins
import io
import inspect
import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

import pytest


ROOT = Path(__file__).resolve().parents[2]
PLANNER_FIXTURES = ROOT / "scripts" / "lm9b_p_fixtures"
COMPILER_FIXTURES = ROOT / "scripts" / "lm9b_c_fixtures"


def _load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SUPPORT = _load_script("lm9b_p_planner_recipe_transfer_support")
ARTIFACTS = _load_script("lm9b_p_planner_recipe_transfer_artifacts")


def test_sealed_archive_verification_recomputes_the_persisted_aggregate(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "checkpoint-1"
    archive.mkdir()
    checksums = {
        "schema": "rook.lm9b_p.checkpoint_checksums:v1",
        "records": [],
        "aggregate_identity": "sha256:" + "0" * 64,
    }
    (archive / "checksums.json").write_text(
        json.dumps(checksums), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="sealed checkpoint archive"):
        ARTIFACTS.verify_sealed_planner_checkpoint_archive(
            archive, expected_aggregate_identity="sha256:" + "0" * 64
        )


def test_archive_exports_one_authoritative_sealer_and_aggregate_bound_verifier() -> None:
    source = inspect.getsource(ARTIFACTS)
    assert source.count("def seal_planner_checkpoint_archive(") == 1
    assert source.count("def verify_sealed_planner_checkpoint_archive(") == 1
    with pytest.raises(TypeError):
        ARTIFACTS.verify_sealed_planner_checkpoint_archive(Path("missing"))


def test_complete_pre_freeze_process_audit_covers_import_and_low_level_reads() -> None:
    code = f'''
import builtins, io, os, subprocess, sys
from pathlib import Path
root = Path({str(ROOT)!r})
forbidden = {{
    (root / "scripts/lm9b_c_fixtures/input_manifest.json").resolve(),
    (root / "scripts/lm9b_c_fixtures/r01_recipe.json").resolve(),
    (root / "mcp_server/tests/fixtures/lm9b_p/non_r01_ready_recipe.json").resolve(),
    (root / "mcp_server/tests/fixtures/lm9b_p/non_r01_blocked_recipe.json").resolve(),
}}
observed = set()
def notice(value):
    try:
        resolved = Path(value).resolve(strict=False)
    except (TypeError, ValueError, OSError):
        return
    if resolved in forbidden:
        observed.add(str(resolved))
path_read_bytes, path_open = Path.read_bytes, Path.open
builtin_open, io_open, os_open = builtins.open, io.open, os.open
def audited_read_bytes(path):
    notice(path); return path_read_bytes(path)
def audited_path_open(path, *args, **kwargs):
    notice(path); return path_open(path, *args, **kwargs)
def audited_builtin_open(path, *args, **kwargs):
    notice(path); return builtin_open(path, *args, **kwargs)
def audited_io_open(path, *args, **kwargs):
    notice(path); return io_open(path, *args, **kwargs)
def audited_os_open(path, *args, **kwargs):
    notice(path); return os_open(path, *args, **kwargs)
Path.read_bytes, Path.open = audited_read_bytes, audited_path_open
builtins.open, io.open, os.open = audited_builtin_open, audited_io_open, audited_os_open
sys.path[:0] = [str(root / "mcp_server/src"), str(root / "scripts")]
import lm9b_p_planner_recipe_transfer_support as support
import lm9b_p_planner_recipe_transfer_probe as probe
class Provider:
    def __init__(self): self.calls = 0
    def __call__(self, request):
        self.calls += 1
        return support.ProviderTurn(b'{{}}', {{"role": "assistant", "tool_calls": []}}, {{}}, {{"model_identity": "planner", "profile_identity": "profile"}}, b'{{}}')
head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
probe.run_planner_checkpoint(
    fixture_dir=root / "scripts/lm9b_p_fixtures", planner_provider=Provider(), evaluator_provider=Provider(),
    archive_destination=root / ".pytest-pre-freeze-archive",
    archive_identity={{"git_commit_sha": head, "planner_model_identity": "planner", "evaluator_model_identity": "evaluator", "provider_profile_identity": "profile"}},
)
if observed: raise AssertionError(sorted(observed))
'''
    archive = ROOT / ".pytest-pre-freeze-archive"
    try:
        subprocess.run(
            [sys.executable, "-c", code], cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT / "mcp_server/src")}, check=True,
        )
    finally:
        if archive.exists():
            shutil.rmtree(archive)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_bytes())


def _accepted_gate(inputs, recipe_bytes: bytes | None = None):
    raw = recipe_bytes or (
        ROOT / "mcp_server/tests/fixtures/lm9b_p/non_r01_ready_recipe.json"
    ).read_bytes()
    result = SUPPORT.evaluate_mechanical_gate(
        recipe_bytes=raw,
        authority=inputs.authority,
        recipe_schema=inputs.recipe_schema,
        normalization_profile=inputs.authority.normalization_profile,
        exclusion_policy=inputs.exclusion_policy,
    )
    assert result.status == "mechanically_accepted"
    return result


def test_corrected_authority_preserves_facts_not_placeholder_bytes() -> None:
    for filename in ("task_envelope.json", "environment_snapshot.json"):
        corrected = _json(PLANNER_FIXTURES / filename)
        historical = _json(COMPILER_FIXTURES / filename)
        assert corrected["payload"] == historical["payload"]
        assert (PLANNER_FIXTURES / filename).read_bytes() != (
            COMPILER_FIXTURES / filename
        ).read_bytes()
        assert corrected["artifact_fingerprint"] == SUPPORT.fingerprint_without(
            corrected, "artifact_fingerprint"
        )


def test_value_binding_fingerprints_cover_schema_and_resolved_value() -> None:
    for filename in ("task_envelope.json", "environment_snapshot.json"):
        artifact = _json(PLANNER_FIXTURES / filename)
        for binding in artifact["value_bindings"]:
            resolved = SUPPORT.resolve_json_pointer(
                artifact["payload"], binding["json_pointer"]
            )
            subject = {"schema": binding["value_schema"], "value": resolved}
            assert binding["typed_value_fingerprint"] == SUPPORT.fingerprint(subject)


def test_payload_schema_registry_binds_both_complete_schemas() -> None:
    registry = _json(PLANNER_FIXTURES / "payload_schema_registry.json")
    assert registry["schema"] == "rook.payload_schema_registry:v1"
    assert [item["schema_id"] for item in registry["entries"]] == [
        "rook.lm9b_c.r01_environment_payload:v1",
        "rook.lm9b_c.r01_task_payload:v1",
    ]
    for entry in registry["entries"]:
        assert entry["schema_fingerprint"] == SUPPORT.fingerprint(
            entry["schema_document"]
        )
    assert registry["registry_fingerprint"] == SUPPORT.fingerprint_without(
        registry, "registry_fingerprint"
    )


def test_planning_policy_remains_exact_historical_control() -> None:
    assert (PLANNER_FIXTURES / "planning_policy.json").read_bytes() == (
        COMPILER_FIXTURES / "planning_policy.json"
    ).read_bytes()


def test_capability_registry_is_closed_available_unavailable_control() -> None:
    registry = _json(PLANNER_FIXTURES / "capability_registry.json")
    assert set(registry) == {
        "schema",
        "registry_id",
        "registry_session_id",
        "observed_at",
        "expires_at",
        "entries",
        "registry_fingerprint",
    }
    assert registry["registry_fingerprint"] == SUPPORT.fingerprint_without(
        registry, "registry_fingerprint"
    )
    assert [entry["capability_code"] for entry in registry["entries"]] == [
        "construct_parametric_geometry",
        "manage_document_layers",
    ]
    assert all(
        set(entry)
        == {
            "capability_code",
            "availability",
            "implementation_refs",
            "constraints_fingerprint",
        }
        for entry in registry["entries"]
    )
    assert registry["entries"][0]["availability"] == "available"
    assert registry["entries"][0]["implementation_refs"]
    assert registry["entries"][1]["availability"] == "unavailable"
    assert registry["entries"][1]["implementation_refs"] == []


def test_production_authority_loader_reauthenticates_all_companions() -> None:
    authority = ARTIFACTS.load_planner_authority_context(PLANNER_FIXTURES)
    assert set(authority.artifacts) == {
        "task_envelope",
        "environment_snapshot",
        "planning_policy",
    }
    assert len(authority.payload_schema_registry["entries"]) == 2
    assert len(authority.vocabularies) == 5
    assert authority.evaluated_at == "2026-07-20T11:00:00Z"
    assert authority.attempt_context["context_fingerprint"] == SUPPORT.fingerprint_without(
        authority.attempt_context, "context_fingerprint"
    )


@pytest.mark.parametrize(
    ("filename", "field", "value", "message"),
    [
        ("environment_snapshot.json", "expires_at", "2026-07-20T10:59:59Z", "stale"),
        ("planning_policy.json", "expires_at", "2026-07-20T10:59:59Z", "stale"),
        ("capability_registry.json", "expires_at", "2026-07-20T10:59:59Z", "stale"),
        (
            "environment_snapshot.json",
            "environment_session_id",
            "wrong-session",
            "session mismatch",
        ),
    ],
)
def test_authority_admission_is_bound_to_frozen_time_and_sessions(
    tmp_path: Path, filename: str, field: str, value: str, message: str
) -> None:
    copied = tmp_path / "fixtures"
    shutil.copytree(PLANNER_FIXTURES, copied)
    artifact = _json(copied / filename)
    artifact[field] = value
    fingerprint_field = (
        "registry_fingerprint" if filename == "capability_registry.json" else "artifact_fingerprint"
    )
    artifact[fingerprint_field] = SUPPORT.fingerprint_without(artifact, fingerprint_field)
    (copied / filename).write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        ARTIFACTS.load_planner_authority_context(copied)


EXPECTED_PLANNER_INPUT_ROLES = (
    "attempt_context",
    "brief",
    "authority.task_envelope",
    "authority.environment_snapshot",
    "authority.planning_policy",
    "registry.payload_schemas",
    "registry.capabilities",
    "vocabulary.semantic_authority_codes",
    "vocabulary.semantic_capability_codes",
    "vocabulary.worker_slot_codes",
    "vocabulary.semantic_materiality_codes",
    "vocabulary.semantic_value_schemas",
    "recipe_schema",
    "normalization_profile",
    "authoring_contract",
    "exclusion_policy",
    "evaluation_rubric",
)


def test_planner_input_loader_is_fixed_role_and_content_addressed() -> None:
    inputs = ARTIFACTS.load_planner_inputs(PLANNER_FIXTURES)
    assert tuple(record.role for record in inputs.records) == EXPECTED_PLANNER_INPUT_ROLES
    assert len({record.relative_path for record in inputs.records}) == len(
        inputs.records
    )
    for record in inputs.records:
        assert record.raw_sha256 == SUPPORT.sha256_prefixed(record.raw_bytes)
        assert record.canonical_fingerprint == SUPPORT.fingerprint(record.value)
    assert inputs.brief == (
        "Create a 10 x 10 array of boxes whose heights are lowest near the "
        "center and rise with radial distance from the center."
    )


def test_authoring_contract_and_rubric_bind_the_closure_ledger() -> None:
    inputs = ARTIFACTS.load_planner_inputs(PLANNER_FIXTURES)
    boundary = inputs.authoring_contract["language_boundary"]
    assert boundary["clause_source_reference_kind"] == "artifact_value"
    assert boundary["assumption_policy_reference_kind"] == "policy_rule"
    assert boundary["derived_fact_input_reference_kind"] == "artifact_value"
    assert boundary["derived_fact_operators"] == ("multiply",)
    assert boundary["clause_local_reference_kinds"] == (
        "assumption",
        "derived_fact",
    )
    assert boundary["assumption_unit_context_reference_kind"] == "artifact_value"
    assert boundary["assumption_basis_reference_kinds"] == (
        "artifact_value",
        "assumption",
        "capability",
        "clause",
        "derived_fact",
        "policy_rule",
        "shape",
        "unresolved_intent",
    )
    assert boundary["unresolved_policy_reference_kind"] == "policy_rule"
    assert boundary["unresolved_unit_context_reference_kind"] == "artifact_value"
    assert boundary["worker_slots_max_entries"] == 0
    assert boundary["confirmation_receipts_admitted"] is False
    assert boundary["synthesis_codes"] == {
        "canonicalization": "planner_semantic_classification",
        "goal": "planner_goal_synthesis",
        "invariant": "planner_invariant_projection",
        "maintains": "planner_semantic_synthesis",
        "postcondition": "planner_postcondition_projection",
        "requires": "planner_requirement_synthesis",
    }
    rubric_binding = inputs.evaluation_rubric["authoring_contract_binding"]
    assert rubric_binding == {
        "contract_id": inputs.authoring_contract["contract_id"],
        "contract_fingerprint": inputs.authoring_contract["contract_fingerprint"],
        "recipe_schema": "rook.planner_graph_recipe:v1",
    }
    assert inputs.evaluation_rubric["recommendations"] == (
        "evaluation_inconclusive",
        "semantically_faithful",
        "semantically_unfaithful",
    )


def test_planner_request_visibility_is_exact_and_r01_free() -> None:
    inputs = ARTIFACTS.load_planner_inputs(PLANNER_FIXTURES)
    rendered = ARTIFACTS.render_planner_request(inputs)
    payload = rendered.payload
    assert payload["brief"] == inputs.brief
    assert payload["attempt_context"] == inputs.attempt_context
    assert payload["authoring_contract"] == inputs.authoring_contract
    assert payload["recipe_schema"] == inputs.recipe_schema
    assert payload["normalization_profile"] == inputs.normalization_profile
    assert payload["exclusion_policy_binding"] == {
        "policy_id": inputs.exclusion_policy["policy_id"],
        "policy_fingerprint": inputs.exclusion_policy["policy_fingerprint"],
    }
    assert set(payload["authority_context"]["artifacts"]) == {
        "task_envelope",
        "environment_snapshot",
        "planning_policy",
    }
    assert set(payload["authority_context"]["vocabularies"]) == set(
        inputs.authority_context["vocabularies"]
    )
    lowered = rendered.raw_bytes.lower()
    for forbidden in (
        b"r01_recipe",
        b"lm9b_c_fixtures",
        b"planner_evaluation_rubric",
        b"submit_compiler_result",
        b"script_instance",
    ):
        assert forbidden not in lowered
    assert rendered.raw_sha256 == SUPPORT.sha256_prefixed(rendered.raw_bytes)


def test_planner_evaluator_visibility_excludes_transcript_and_compiler() -> None:
    inputs = ARTIFACTS.load_planner_inputs(PLANNER_FIXTURES)
    recipe_bytes = (
        ROOT / "mcp_server/tests/fixtures/lm9b_p/non_r01_ready_recipe.json"
    ).read_bytes()
    gate_result = _accepted_gate(inputs, recipe_bytes)
    rendered = ARTIFACTS.render_planner_evaluator_request(
        inputs,
        gate_result=gate_result,
    )
    assert rendered.payload["brief"] == inputs.brief
    assert rendered.payload["final_recipe_json"] == recipe_bytes.decode("utf-8")
    assert rendered.payload["deterministic_findings"]["status"] == gate_result.status
    assert rendered.payload["deterministic_findings"]["diagnostics"] == ()
    assert rendered.payload["evaluation_rubric"] == inputs.evaluation_rubric
    assert "authoring_contract" not in rendered.payload
    lowered = rendered.raw_bytes.lower()
    for forbidden in (
        b"planner_transcript",
        b"earlier_submission",
        b"compiler_output",
        b"r01_recipe",
        b"script_instance",
    ):
        assert forbidden not in lowered


def test_planner_evaluator_rejects_caller_forged_acceptance() -> None:
    inputs = ARTIFACTS.load_planner_inputs(PLANNER_FIXTURES)
    accepted = _accepted_gate(inputs)
    forged = replace(
        accepted,
        final_recipe_bytes=b"{}",
        recipe_value_fingerprint=SUPPORT.fingerprint({}),
    )
    with pytest.raises(ValueError, match="accepted gate result"):
        ARTIFACTS.render_planner_evaluator_request(
            inputs,
            gate_result=forged,
        )

    rejected = SUPPORT.evaluate_mechanical_gate(
        recipe_bytes=b"{}",
        authority=inputs.authority,
        recipe_schema=inputs.recipe_schema,
        normalization_profile=inputs.authority.normalization_profile,
        exclusion_policy=inputs.exclusion_policy,
    )
    with pytest.raises(ValueError, match="accepted gate result"):
        ARTIFACTS.render_planner_evaluator_request(inputs, gate_result=rejected)

    class ForgedGateResult(SUPPORT.MechanicalGateResult):
        def __eq__(self, other: object) -> bool:
            return True

    subclass_forgery = ForgedGateResult(
        status="mechanically_accepted",
        diagnostics=(),
        final_recipe_bytes=b"{}",
        recipe_value_fingerprint=SUPPORT.fingerprint({}),
        ratified_recipe_fingerprint=accepted.ratified_recipe_fingerprint,
        historical_recipe_fingerprint=accepted.historical_recipe_fingerprint,
    )
    with pytest.raises(ValueError, match="accepted gate result"):
        ARTIFACTS.render_planner_evaluator_request(
            inputs, gate_result=subclass_forgery
        )

    substituted_context = dict(inputs.authority_context)
    substituted_context["compiler_output"] = {"leak": True}
    substituted_inputs = replace(inputs, authority_context=substituted_context)
    with pytest.raises(ValueError, match="authority context binding"):
        ARTIFACTS.render_planner_evaluator_request(
            substituted_inputs, gate_result=accepted
        )


def test_loaded_inputs_and_rendered_payload_are_transitively_immutable() -> None:
    inputs = ARTIFACTS.load_planner_inputs(PLANNER_FIXTURES)
    with pytest.raises(TypeError):
        inputs.exclusion_policy["forbidden_recipe_markers"] = []
    with pytest.raises(TypeError):
        inputs.authority.artifacts["task_envelope"]["payload"] = {}
    with pytest.raises(TypeError):
        inputs.authority_context["compiler_output"] = {"leak": True}

    rendered = ARTIFACTS.render_planner_request(inputs)
    original_raw = rendered.raw_bytes
    with pytest.raises(TypeError):
        rendered.payload["brief"] = "changed"
    assert rendered.raw_bytes == original_raw
    assert rendered.raw_sha256 == SUPPORT.sha256_prefixed(original_raw)


def test_second_read_cannot_diverge_from_content_addressed_records(
    tmp_path: Path, monkeypatch
) -> None:
    copied = tmp_path / "fixtures"
    shutil.copytree(PLANNER_FIXTURES, copied)
    original_loader = ARTIFACTS.load_planner_authority_context

    def mutating_loader(fixture_dir: Path):
        path = Path(fixture_dir) / "attempt_context.json"
        value = json.loads(path.read_bytes())
        value["attempt_id"] = "lm9b-p-mutated-between-reads"
        value["context_fingerprint"] = SUPPORT.fingerprint_without(
            value, "context_fingerprint"
        )
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return original_loader(fixture_dir)

    monkeypatch.setattr(ARTIFACTS, "load_planner_authority_context", mutating_loader)
    with pytest.raises(ValueError, match="snapshot mismatch"):
        ARTIFACTS.load_planner_inputs(copied)


def test_transition_revalidates_frozen_session_authority() -> None:
    inputs = ARTIFACTS.load_planner_inputs(PLANNER_FIXTURES)
    accepted = _accepted_gate(inputs)
    attempt = dict(inputs.attempt_context)
    attempt["task_session_id"] = "wrong-task-session"
    attempt["context_fingerprint"] = SUPPORT.fingerprint_without(
        attempt, "context_fingerprint"
    )
    frozen_attempt = MappingProxyType(attempt)
    raw = (json.dumps(attempt, indent=2) + "\n").encode("utf-8")
    original = next(
        record for record in inputs.records if record.role == "attempt_context"
    )
    changed_record = replace(
        original,
        raw_bytes=raw,
        raw_sha256=SUPPORT.sha256_prefixed(raw),
        canonical_fingerprint=SUPPORT.fingerprint(attempt),
        value=frozen_attempt,
    )
    changed_records = tuple(
        changed_record if record.role == "attempt_context" else record
        for record in inputs.records
    )
    changed_authority = replace(
        inputs.authority,
        attempt_context=frozen_attempt,
    )
    changed_inputs = replace(
        inputs,
        records=changed_records,
        attempt_context=frozen_attempt,
        authority=changed_authority,
    )
    with pytest.raises(ValueError, match="task session mismatch"):
        ARTIFACTS.render_planner_evaluator_request(
            changed_inputs, gate_result=accepted
        )


def test_transition_rejects_substituted_recipe_schema() -> None:
    inputs = ARTIFACTS.load_planner_inputs(PLANNER_FIXTURES)
    accepted = _accepted_gate(inputs)
    changed_schema = ARTIFACTS._thaw_json(inputs.recipe_schema)
    changed_schema["$comment"] = "caller-substituted schema"
    frozen_schema = ARTIFACTS._freeze_json(changed_schema)
    raw = (json.dumps(changed_schema, indent=2) + "\n").encode("utf-8")
    original = next(
        record for record in inputs.records if record.role == "recipe_schema"
    )
    changed_record = replace(
        original,
        raw_bytes=raw,
        raw_sha256=SUPPORT.sha256_prefixed(raw),
        canonical_fingerprint=SUPPORT.fingerprint(changed_schema),
        value=frozen_schema,
    )
    changed_inputs = replace(
        inputs,
        records=tuple(
            changed_record if record.role == "recipe_schema" else record
            for record in inputs.records
        ),
        recipe_schema=frozen_schema,
    )
    with pytest.raises(ValueError, match="authority binding mismatch: recipe_schema"):
        ARTIFACTS.render_planner_evaluator_request(
            changed_inputs, gate_result=accepted
        )


def test_transition_rejects_substituted_executable_normalization_rows() -> None:
    inputs = ARTIFACTS.load_planner_inputs(PLANNER_FIXTURES)
    accepted = _accepted_gate(inputs)
    changed_inputs = replace(
        inputs,
        authority=replace(
            inputs.authority,
            normalization_profile=replace(
                inputs.authority.normalization_profile,
                rows=(),
            ),
        ),
    )
    with pytest.raises(ValueError, match="normalization profile authority binding"):
        ARTIFACTS.render_planner_evaluator_request(
            changed_inputs, gate_result=accepted
        )

    class ForgedNormalizationProfile(SUPPORT.NormalizationProfile):
        def __eq__(self, other: object) -> bool:
            return True

    subclass_profile = ForgedNormalizationProfile(
        profile_id=inputs.authority.normalization_profile.profile_id,
        profile_fingerprint=(
            inputs.authority.normalization_profile.profile_fingerprint
        ),
        rows=(),
    )
    subclass_inputs = replace(
        inputs,
        authority=replace(
            inputs.authority,
            normalization_profile=subclass_profile,
        ),
    )
    with pytest.raises(ValueError, match="normalization profile authority binding"):
        ARTIFACTS.render_planner_evaluator_request(
            subclass_inputs, gate_result=accepted
        )


def test_pre_freeze_loading_and_rendering_never_read_hidden_controls(
    monkeypatch,
) -> None:
    forbidden = {
        (COMPILER_FIXTURES / "input_manifest.json").resolve(),
        (COMPILER_FIXTURES / "r01_recipe.json").resolve(),
        (
            ROOT
            / "mcp_server/tests/fixtures/lm9b_p/non_r01_ready_recipe.json"
        ).resolve(),
        (
            ROOT
            / "mcp_server/tests/fixtures/lm9b_p/non_r01_blocked_recipe.json"
        ).resolve(),
    }
    observed: set[Path] = set()
    original_read_bytes = Path.read_bytes
    original_open = Path.open
    original_stat = Path.stat
    original_builtin_open = builtins.open

    def notice(value) -> None:
        try:
            resolved = Path(value).absolute()
        except TypeError:
            return
        if resolved in forbidden:
            observed.add(resolved)

    def audited_read_bytes(path: Path):
        notice(path)
        return original_read_bytes(path)

    def audited_open(path: Path, *args, **kwargs):
        notice(path)
        return original_open(path, *args, **kwargs)

    def audited_stat(path: Path, *args, **kwargs):
        notice(path)
        return original_stat(path, *args, **kwargs)

    def audited_builtin_open(file, *args, **kwargs):
        notice(file)
        return original_builtin_open(file, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", audited_read_bytes)
    monkeypatch.setattr(Path, "open", audited_open)
    monkeypatch.setattr(Path, "stat", audited_stat)
    monkeypatch.setattr(builtins, "open", audited_builtin_open)
    inputs = ARTIFACTS.load_planner_inputs(PLANNER_FIXTURES)
    ARTIFACTS.render_planner_request(inputs)
    assert observed == set()


def test_rendered_planner_request_is_hashseed_stable() -> None:
    code = f"""
import importlib.util, sys
from pathlib import Path
root = Path({str(ROOT)!r})
sys.path.insert(0, str(root / 'mcp_server/src'))
sys.path.insert(0, str(root / 'scripts'))
path = root / 'scripts/lm9b_p_planner_recipe_transfer_artifacts.py'
spec = importlib.util.spec_from_file_location('seed_artifacts', path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
inputs = module.load_planner_inputs(root / 'scripts/lm9b_p_fixtures')
print(module.render_planner_request(inputs).raw_sha256)
"""
    outputs = []
    for seed in ("1", "8675309"):
        env = os.environ.copy()
        env["PYTHONHASHSEED"] = seed
        env["PYTHONPATH"] = str(ROOT / "mcp_server/src")
        outputs.append(
            subprocess.check_output(
                [sys.executable, "-c", code],
                cwd=ROOT,
                env=env,
                text=True,
            ).strip()
        )
    assert outputs[0] == outputs[1]


def test_import_and_render_are_whole_process_read_isolated() -> None:
    code = f'''
import builtins, importlib.util, sys
from pathlib import Path
root = Path({str(ROOT)!r})
forbidden = {{
    (root / "scripts/lm9b_c_fixtures/input_manifest.json").absolute(),
    (root / "scripts/lm9b_c_fixtures/r01_recipe.json").absolute(),
    (root / "mcp_server/tests/fixtures/lm9b_p/non_r01_ready_recipe.json").absolute(),
    (root / "mcp_server/tests/fixtures/lm9b_p/non_r01_blocked_recipe.json").absolute(),
}}
observed = set()
original_read_bytes = Path.read_bytes
original_open = Path.open
original_stat = Path.stat
original_builtin_open = builtins.open
def notice(value):
    try:
        resolved = Path(value).absolute()
    except TypeError:
        return
    if resolved in forbidden:
        observed.add(str(resolved))
def audited_read_bytes(path):
    notice(path); return original_read_bytes(path)
def audited_open(path, *args, **kwargs):
    notice(path); return original_open(path, *args, **kwargs)
def audited_stat(path, *args, **kwargs):
    notice(path); return original_stat(path, *args, **kwargs)
def audited_builtin_open(file, *args, **kwargs):
    notice(file); return original_builtin_open(file, *args, **kwargs)
Path.read_bytes = audited_read_bytes
Path.open = audited_open
Path.stat = audited_stat
builtins.open = audited_builtin_open
sys.path[:0] = [str(root / "mcp_server/src"), str(root / "scripts")]
path = root / "scripts/lm9b_p_planner_recipe_transfer_artifacts.py"
spec = importlib.util.spec_from_file_location("isolated_artifacts", path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
inputs = module.load_planner_inputs(root / "scripts/lm9b_p_fixtures")
module.render_planner_request(inputs)
if observed:
    raise AssertionError(sorted(observed))
'''
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "mcp_server/src")},
        check=True,
    )
