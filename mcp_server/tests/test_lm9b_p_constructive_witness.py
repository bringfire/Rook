from __future__ import annotations

import importlib.util
import builtins
import json
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PLANNER_FIXTURES = ROOT / "scripts" / "lm9b_p_fixtures"
COMPILER_FIXTURES = ROOT / "scripts" / "lm9b_c_fixtures"
NON_R01_RECIPE = ROOT / "mcp_server" / "tests" / "fixtures" / "lm9b_p" / "non_r01_ready_recipe.json"


def _load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


LM9B_C_SUPPORT = _load_script("lm9b_c_compiler_sufficiency_support")
LM9B_C_ARTIFACTS = _load_script("lm9b_c_compiler_sufficiency_artifacts")
LM9B_C_PROBE = _load_script("lm9b_c_compiler_sufficiency_probe")
SUPPORT = _load_script("lm9b_p_planner_recipe_transfer_support")
ARTIFACTS = _load_script("lm9b_p_planner_recipe_transfer_artifacts")
PROBE = _load_script("lm9b_p_planner_recipe_transfer_probe")


class _Provider:
    def __init__(self, response: object) -> None:
        self.response = response

    def __call__(self, request: dict[str, object]) -> object:
        return self.response


def _planner_turn(recipe_bytes: bytes) -> object:
    return SUPPORT.ProviderTurn(
        raw_request=b'{"planner":"request"}',
        raw_response=b'{"planner":"response"}',
        assistant_message={
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "planner-call-1",
                    "function": {
                        "name": "submit_planner_recipe",
                        "arguments": json.dumps(
                            {"recipe_json": recipe_bytes.decode("utf-8")}
                        ),
                    },
                }
            ],
        },
        usage={},
        provider_metadata={
            "model_identity": "constructive-planner",
            "profile_identity": "constructive-profile",
        },
    )


def _evaluator_turn() -> object:
    return SUPPORT.ProviderTurn(
        raw_request=b'{"evaluator":"request"}',
        raw_response=b'{"evaluator":"response"}',
        assistant_message={
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "evaluator-call-1",
                    "function": {
                        "name": "submit_planner_evaluation",
                        "arguments": json.dumps(
                            {
                                "evaluation_json": json.dumps(
                                    {
                                        "recommendation": "faithful_ready",
                                        "evidence": [
                                            {
                                                "criterion_id": "brief_fidelity",
                                                "finding": "Constructive witness is ready.",
                                            }
                                        ],
                                    }
                                )
                            }
                        ),
                    },
                }
            ],
        },
        usage={},
        provider_metadata={
            "model_identity": "constructive-evaluator",
            "profile_identity": "constructive-profile",
        },
    )


def _ready_join_proof(
    *, destination: Path, fixture_dir: Path = PLANNER_FIXTURES
) -> tuple[object, object]:
    recipe_bytes = NON_R01_RECIPE.read_bytes()
    checkpoint = PROBE.run_planner_checkpoint(
        fixture_dir=fixture_dir,
        planner_provider=_Provider(_planner_turn(recipe_bytes)),
        evaluator_provider=_Provider(_evaluator_turn()),
        archive_destination=destination,
        archive_identity={
            "git_commit_sha": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "planner_model_identity": "constructive-planner",
            "evaluator_model_identity": "constructive-evaluator",
            "provider_profile_identity": "constructive-profile",
        },
    )
    assert checkpoint.classification == "probe_candidate_ready"
    assert checkpoint.sealed_archive is not None
    assert checkpoint.planner_inputs is not None
    assert checkpoint.gate_result is not None
    assert checkpoint.final_recipe_bytes is not None
    proof = ARTIFACTS.verify_ready_checkpoint_for_join(
        checkpoint_archive=checkpoint.sealed_archive,
        checkpoint_classification=checkpoint.classification,
        planner_inputs=checkpoint.planner_inputs,
        gate_result=checkpoint.gate_result,
        final_recipe_bytes=checkpoint.final_recipe_bytes,
    )
    return checkpoint, proof


def test_non_r01_recipe_reaches_unchanged_fake_compiler_provider(tmp_path: Path) -> None:
    checkpoint, proof = _ready_join_proof(destination=tmp_path / "checkpoint-1")
    inputs = checkpoint.planner_inputs
    assert inputs is not None
    authority = inputs.authority
    recipe_bytes = NON_R01_RECIPE.read_bytes()
    gate = checkpoint.gate_result
    assert gate is not None
    assert gate.status == "mechanically_accepted"
    assert gate.final_recipe_bytes == recipe_bytes
    assert gate.ratified_recipe_fingerprint == gate.historical_recipe_fingerprint

    handoff = ARTIFACTS.build_lm9bc_handoff(
        join_proof=proof,
        compiler_fixture_dir=COMPILER_FIXTURES,
        destination=tmp_path / "handoff",
    )
    assert handoff.archived_recipe_bytes == recipe_bytes
    assert handoff.compiler_renderer_id == LM9B_C_ARTIFACTS.COMPILER_RENDERER_ID
    assert handoff.attempt_context_fingerprint == authority.attempt_context[
        "context_fingerprint"
    ]
    assert handoff.manifest["probe_attempt_context"] == authority.attempt_context
    assert "r01_recipe" not in json.dumps(handoff.manifest).lower()
    manifest_bytes = (handoff.fixture_dir / "input_manifest.json").read_bytes()
    assert handoff.manifest_raw_sha256 == SUPPORT.sha256_prefixed(manifest_bytes)
    assert handoff.manifest_canonical_fingerprint == SUPPORT.fingerprint(
        json.loads(manifest_bytes)
    )

    loaded = LM9B_C_ARTIFACTS.load_frozen_inputs(handoff.fixture_dir)
    rendered = LM9B_C_ARTIFACTS.render_compiler_request(loaded)
    assert recipe_bytes == handoff.archived_recipe_bytes == loaded.recipe_bytes
    assert rendered.renderer_id == LM9B_C_ARTIFACTS.COMPILER_RENDERER_ID
    compiler_payload = json.loads(rendered.user_prompt)
    assert compiler_payload["semantic_source"]["recipe"]["artifact"] == loaded.recipe
    assert compiler_payload["legal_trace_reference_catalog"] == (
        LM9B_C_ARTIFACTS.derive_legal_trace_reference_catalog(loaded.contract_index)
    )
    assert compiler_payload["terminal_result_schema"] == (
        LM9B_C_SUPPORT.COMPILER_RESULT_SCHEMA
    )

    calls: list[dict[str, object]] = []

    def fake_compiler(payload: dict[str, object]):
        calls.append(payload)
        raise LM9B_C_SUPPORT.ProviderCallFailure(
            failure_type="constructive_witness_stop",
            message="constructive witness stop",
            raw_request=b"",
            raw_error=b"constructive witness stop",
        )

    result = LM9B_C_PROBE.run_probe(
        run_root=tmp_path / "compiler-run",
        fixture_dir=handoff.fixture_dir,
        compiler_provider=fake_compiler,
        evaluator_provider=lambda payload: (_ for _ in ()).throw(
            AssertionError("evaluator must not run")
        ),
        compiler_identity={"provider": "fake", "model": "constructive-witness"},
        evaluator_identity={"provider": "fake", "model": "unused"},
        git_sha="constructivewitness",
    )
    assert len(calls) == 1
    assert result.decision.outcome == "inconclusive"
    assert (
        result.run_dir / "inputs" / "recipe.json"
    ).read_bytes() == loaded.recipe_bytes == recipe_bytes


def test_reordered_set_like_recipe_fails_checkpoint_1_without_rewrite(
    tmp_path: Path,
) -> None:
    inputs = ARTIFACTS.load_planner_inputs(PLANNER_FIXTURES)
    reordered = json.loads(NON_R01_RECIPE.read_bytes())
    reordered["assumptions"].reverse()
    reordered_bytes = json.dumps(reordered, indent=2).encode("utf-8") + b"\n"

    gate = SUPPORT.evaluate_mechanical_gate(
        recipe_bytes=reordered_bytes,
        authority=inputs.authority,
        recipe_schema=inputs.recipe_schema,
        normalization_profile=inputs.authority.normalization_profile,
        exclusion_policy=inputs.exclusion_policy,
    )

    assert gate.status == "probe_mechanically_rejected"
    assert [item.code for item in gate.diagnostics] == [
        "recipe_not_canonical_normal_form"
    ]
    destination = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="join proof"):
        ARTIFACTS.build_lm9bc_handoff(
            join_proof=gate,
            compiler_fixture_dir=COMPILER_FIXTURES,
            destination=destination,
        )
    assert not destination.exists()


def test_handoff_never_reads_r01_or_its_source_manifest(
    tmp_path: Path, monkeypatch
) -> None:
    forbidden = {
        (COMPILER_FIXTURES / "r01_recipe.json").resolve(),
        (COMPILER_FIXTURES / "input_manifest.json").resolve(),
    }
    observed: set[Path] = set()
    original_read_bytes = Path.read_bytes
    original_path_open = Path.open
    original_stat = Path.stat
    original_open = builtins.open

    def audited_read_bytes(path: Path):
        resolved = path.resolve()
        if resolved in forbidden:
            observed.add(resolved)
        return original_read_bytes(path)

    def audited_stat(path: Path, *args, **kwargs):
        resolved = Path(path).absolute()
        if resolved in forbidden:
            observed.add(resolved)
        return original_stat(path, *args, **kwargs)

    def audited_path_open(path: Path, *args, **kwargs):
        resolved = path.resolve()
        if resolved in forbidden:
            observed.add(resolved)
        return original_path_open(path, *args, **kwargs)

    def audited_open(file, *args, **kwargs):
        if isinstance(file, (str, bytes, Path)):
            resolved = Path(file).resolve()
            if resolved in forbidden:
                observed.add(resolved)
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", audited_read_bytes)
    monkeypatch.setattr(Path, "open", audited_path_open)
    monkeypatch.setattr(Path, "stat", audited_stat)
    monkeypatch.setattr(builtins, "open", audited_open)

    _, proof = _ready_join_proof(
        destination=tmp_path / "checkpoint-1",
    )
    ARTIFACTS.build_lm9bc_handoff(
        join_proof=proof,
        compiler_fixture_dir=COMPILER_FIXTURES,
        destination=tmp_path / "audited-handoff",
    )
    assert observed == set()


@pytest.mark.parametrize(
    ("role", "filename"),
    (
        ("authority.task_envelope", "task_envelope.json"),
        ("authority.environment_snapshot", "environment_snapshot.json"),
        ("authority.planning_policy", "planning_policy.json"),
    ),
)
def test_handoff_preserves_frozen_planner_authority_after_fixture_mutation(
    tmp_path: Path, role: str, filename: str,
) -> None:
    copied = tmp_path / "planner-fixtures"
    shutil.copytree(PLANNER_FIXTURES, copied)
    checkpoint, proof = _ready_join_proof(
        destination=tmp_path / "checkpoint-1",
        fixture_dir=copied,
    )
    inputs = checkpoint.planner_inputs
    assert inputs is not None
    frozen_record = next(
        record
        for record in inputs.records
        if record.role == role
    )
    fixture_path = copied / filename
    fixture_path.write_bytes(fixture_path.read_bytes() + b"  \n")

    handoff = ARTIFACTS.build_lm9bc_handoff(
        join_proof=proof,
        compiler_fixture_dir=COMPILER_FIXTURES,
        destination=tmp_path / "frozen-handoff",
    )
    handed_off = (handoff.fixture_dir / filename).read_bytes()
    assert handed_off == frozen_record.raw_bytes
    assert handed_off != fixture_path.read_bytes()
    manifest_row = next(
        row
        for row in handoff.manifest["records"]
        if row["role"] == role
    )
    assert manifest_row["raw_sha256"] == frozen_record.raw_sha256


def test_handoff_rejects_caller_forged_acceptance_before_writing(
    tmp_path: Path,
) -> None:
    checkpoint, proof = _ready_join_proof(destination=tmp_path / "checkpoint-1")
    accepted = checkpoint.gate_result
    assert accepted is not None
    forged = replace(
        accepted,
        final_recipe_bytes=b"{}",
        recipe_value_fingerprint=SUPPORT.fingerprint({}),
    )
    destination = tmp_path / "forged-handoff"
    try:
        ARTIFACTS.build_lm9bc_handoff(
            join_proof=replace(proof, gate_result=forged),
            compiler_fixture_dir=COMPILER_FIXTURES,
            destination=destination,
        )
    except ValueError as exc:
        assert "join proof" in str(exc)
    else:
        raise AssertionError("forged acceptance reached the handoff")
    assert not destination.exists()

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
    subclass_destination = tmp_path / "subclass-forged-handoff"
    with pytest.raises(ValueError, match="join proof"):
        ARTIFACTS.build_lm9bc_handoff(
            join_proof=replace(proof, gate_result=subclass_forgery),
            compiler_fixture_dir=COMPILER_FIXTURES,
            destination=subclass_destination,
        )
    assert not subclass_destination.exists()


def test_handoff_rejects_corrupted_persisted_bytes(
    tmp_path: Path, monkeypatch,
) -> None:
    _, proof = _ready_join_proof(destination=tmp_path / "checkpoint-1")

    def short_write(path: Path, raw: bytes) -> None:
        path.write_bytes(raw[:-1])

    monkeypatch.setattr(ARTIFACTS, "_write_bytes", short_write)
    with pytest.raises(ValueError, match="handoff write verification failed: recipe"):
        ARTIFACTS.build_lm9bc_handoff(
            join_proof=proof,
            compiler_fixture_dir=COMPILER_FIXTURES,
            destination=tmp_path / "corrupted-handoff",
        )
