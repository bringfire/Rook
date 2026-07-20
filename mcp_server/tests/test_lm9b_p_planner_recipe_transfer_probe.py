from __future__ import annotations

import builtins
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "scripts" / "lm9b_p_fixtures"
READY_RECIPE = ROOT / "mcp_server/tests/fixtures/lm9b_p/non_r01_ready_recipe.json"
BLOCKED_RECIPE = ROOT / "mcp_server/tests/fixtures/lm9b_p/non_r01_blocked_recipe.json"
COMPILER_FIXTURES = ROOT / "scripts" / "lm9b_c_fixtures"
READY_RECIPE_BYTES = READY_RECIPE.read_bytes()


def _load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SUPPORT = _load_script("lm9b_p_planner_recipe_transfer_support")
ARTIFACTS = _load_script("lm9b_p_planner_recipe_transfer_artifacts")
PROBE = _load_script("lm9b_p_planner_recipe_transfer_probe")


ARCHIVE_IDENTITY = {
    "git_commit_sha": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip(),
    "planner_model_identity": "planner-model-2026-07-20",
    "evaluator_model_identity": "evaluator-model-2026-07-20",
    "provider_profile_identity": "provider-profile-2026-07-20",
}
ARCHIVE_RECORD_PATHS = (
    "inputs/attempt_context.json",
    "inputs/radial_brief.txt",
    "inputs/task_envelope.json",
    "inputs/environment_snapshot.json",
    "inputs/planning_policy.json",
    "inputs/payload_schema_registry.json",
    "inputs/capability_registry.json",
    "inputs/semantic_authority_code_vocabulary.json",
    "inputs/semantic_capability_code_vocabulary.json",
    "inputs/worker_slot_code_vocabulary.json",
    "inputs/semantic_materiality_code_vocabulary.json",
    "inputs/semantic_value_schema_registry.json",
    "inputs/planner_recipe_probe_schema.json",
    "inputs/recipe_normalization_profile.json",
    "inputs/planner_authoring_contract.json",
    "inputs/planner_exclusion_policy.json",
    "inputs/planner_evaluation_rubric.json",
    "inputs/manifest.json",
    "planner/request.json",
    "planner/turns/000/raw_response.bin",
    "planner/turns/000/feedback.json",
    "planner/turns/000/usage.json",
    "planner/turns/000/timing.json",
    "planner/attempts/000/capture.json",
    "planner/attempts/000/provider_request.json",
    "planner/attempts/000/raw_request.bin",
    "planner/attempts/000/raw_response.bin",
    "planner/attempts/000/usage.json",
    "planner/attempts/000/tool_arguments/000.bin",
    "planner/final_recipe.json",
    "planner/final_recipe_identity.json",
    "evaluator/request.json",
    "evaluator/raw_response.bin",
    "evaluator/report.json",
    "evaluator/usage.json",
    "evaluator/timing.json",
    "evaluator/attempts/000/capture.json",
    "evaluator/attempts/000/provider_request.json",
    "evaluator/attempts/000/raw_request.bin",
    "evaluator/attempts/000/raw_response.bin",
    "evaluator/attempts/000/usage.json",
    "evaluator/attempts/000/tool_arguments/000.bin",
    "checkpoint/classification.json",
    "checkpoint/session.json",
    "identity.json",
    "checksums.json",
)


class _Provider:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, object]] = []

    def __call__(self, request: dict[str, object]) -> object:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _planner_turn(recipe_path: Path) -> object:
    return _planner_turn_bytes(recipe_path.read_bytes())


def _planner_turn_bytes(recipe_bytes: bytes) -> object:
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
                            {
                                "recipe_json": recipe_bytes.decode("utf-8")
                            }
                        ),
                    },
                }
            ],
        },
        usage={},
        provider_metadata={
            "model_identity": "planner-model-2026-07-20",
            "profile_identity": "provider-profile-2026-07-20",
        },
    )


def _evaluator_turn(recommendation: str) -> object:
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
                                        "recommendation": recommendation,
                                        "evidence": [
                                            {
                                                "criterion_id": "brief_fidelity",
                                                "finding": "Evidence is recorded.",
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
            "model_identity": "evaluator-model-2026-07-20",
            "profile_identity": "provider-profile-2026-07-20",
        },
    )


def _empty_planner_turn() -> object:
    return SUPPORT.ProviderTurn(
        raw_request=b'{"planner":"request"}',
        raw_response=b'{"planner":"response"}',
        assistant_message={"role": "assistant", "tool_calls": []},
        usage={},
        provider_metadata={
            "model_identity": "planner-model-2026-07-20",
            "profile_identity": "provider-profile-2026-07-20",
        },
    )


def _turn_with_tool_calls(
    *,
    role: str,
    calls: list[object],
) -> object:
    return SUPPORT.ProviderTurn(
        raw_request=(f'{{"{role}":"request"}}').encode("utf-8"),
        raw_response=(f'{{"{role}":"response"}}').encode("utf-8"),
        assistant_message={"role": "assistant", "tool_calls": calls},
        usage={},
        provider_metadata={
            "model_identity": (
                "planner-model-2026-07-20"
                if role == "planner"
                else "evaluator-model-2026-07-20"
            ),
            "profile_identity": "provider-profile-2026-07-20",
        },
    )


def _recompute_checksums(archive_dir: Path) -> None:
    checksums_path = archive_dir / "checksums.json"
    checksums = json.loads(checksums_path.read_bytes())
    records = checksums["records"]
    checksums["aggregate_identity"] = ARTIFACTS.canonical_fingerprint(
        ARTIFACTS.own_trusted_json(
            {
                "schema": checksums["schema"],
                "records": records,
            }
        )
    )
    checksums_path.write_text(
        json.dumps(checksums, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


@pytest.mark.parametrize(
    ("recommendation", "classification"),
    [
        ("faithful_ready", "probe_candidate_ready"),
        ("planner_failure", "probe_planner_failure"),
    ],
)
def test_checkpoint_derives_the_only_public_classification(
    recommendation: str, classification: str
) -> None:
    planner = _Provider([_planner_turn(READY_RECIPE)])
    evaluator = _Provider([_evaluator_turn(recommendation)])
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=planner,
        evaluator_provider=evaluator,
    )
    assert result.classification == classification
    assert result.evaluator.recommendation == recommendation
    assert result.final_recipe_bytes == READY_RECIPE.read_bytes()
    assert result.checkpoint_2 == "not_evaluated"
    assert len(planner.requests) == 1
    assert len(evaluator.requests) == 1
    assert "probe_candidate" not in json.dumps(evaluator.requests[0])
    assert "planner-call-1" not in json.dumps(evaluator.requests[0])


def test_blocked_witness_never_enters_checkpoint_2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planner = _Provider([_planner_turn(BLOCKED_RECIPE)])
    evaluator = _Provider([_evaluator_turn("faithful_blocked")])
    compiler_calls: list[object] = []

    def unexpected_handoff(*args, **kwargs):
        compiler_calls.append((args, kwargs))
        raise AssertionError("Checkpoint 1 must not build a compiler handoff")

    monkeypatch.setattr(PROBE.ARTIFACTS, "build_lm9bc_handoff", unexpected_handoff)
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=planner,
        evaluator_provider=evaluator,
    )
    assert result.classification == "probe_candidate_blocked"
    assert result.final_recipe_bytes == BLOCKED_RECIPE.read_bytes()
    assert result.checkpoint_2 == "not_evaluated"
    assert compiler_calls == []
    assert len(planner.requests) == 1
    assert len(evaluator.requests) == 1


def test_mechanical_rejection_skips_evaluation() -> None:
    planner = _Provider(
        [
            SUPPORT.ProviderTurn(
                raw_request=b'{"planner":"request"}',
                raw_response=b'{"planner":"response"}',
                assistant_message={"role": "assistant", "tool_calls": []},
                usage={},
                provider_metadata={},
            )
            for _ in range(SUPPORT.PLANNER_MAX_TURNS)
        ]
    )
    evaluator = _Provider([RuntimeError("must not be consumed")])
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=planner,
        evaluator_provider=evaluator,
    )
    assert result.classification == "probe_mechanically_rejected"
    assert result.evaluator is None
    assert result.final_recipe_bytes is None
    assert result.checkpoint_2 == "not_evaluated"
    assert evaluator.requests == []


@pytest.mark.parametrize(
    "evaluator_response",
    [
        RuntimeError("provider unavailable"),
        _evaluator_turn("probe_candidate_ready"),
    ],
)
def test_evaluator_failure_or_malformed_output_is_inconclusive_without_retry(
    evaluator_response: object,
) -> None:
    planner = _Provider([_planner_turn(READY_RECIPE)])
    evaluator = _Provider([evaluator_response, RuntimeError("must not be consumed")])
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=planner,
        evaluator_provider=evaluator,
    )
    assert result.classification == "probe_inconclusive"
    assert result.checkpoint_2 == "not_evaluated"
    assert len(evaluator.requests) == 1


@pytest.fixture
def sealed_checkpoint(tmp_path: Path):
    archive_dir = tmp_path / "checkpoint-1"
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=_Provider([_planner_turn_bytes(READY_RECIPE_BYTES)]),
        evaluator_provider=_Provider([_evaluator_turn("faithful_ready")]),
        archive_destination=archive_dir,
        archive_identity=ARCHIVE_IDENTITY,
    )
    assert result.sealed_archive is not None
    return result, archive_dir


def test_checkpoint_archive_is_complete_atomic_and_byte_derived(
    sealed_checkpoint,
) -> None:
    result, archive_dir = sealed_checkpoint
    sealed = ARTIFACTS.verify_sealed_planner_checkpoint_archive(archive_dir)
    assert result.sealed_archive.aggregate_identity == sealed.aggregate_identity
    assert sorted(
        path.relative_to(archive_dir).as_posix()
        for path in archive_dir.rglob("*")
        if path.is_file()
    ) == sorted(ARCHIVE_RECORD_PATHS)
    assert not list(archive_dir.parent.glob(f".{archive_dir.name}.tmp-*"))
    identity = json.loads((archive_dir / "identity.json").read_bytes())
    assert identity == {
        "schema": "rook.lm9b_p.checkpoint_identity:v1",
        "git_commit_sha": ARCHIVE_IDENTITY["git_commit_sha"],
        "planner_model_identity": "planner-model-2026-07-20",
        "evaluator_model_identity": "evaluator-model-2026-07-20",
        "provider_profile_identity": "provider-profile-2026-07-20",
        "normalization_profile_identity": {
            "profile_id": "lm9b_p.recipe_normalization_profile:v1",
            "profile_fingerprint": "sha256:5b8833bd1f2554c1d91fb8f04aa71a8e7509d850ccca28036096ea24f1ac000e",
        },
        "bounds": {
            "planner_max_turns": SUPPORT.PLANNER_MAX_TURNS,
            "evaluator_max_attempts": 1,
        },
        "execution_permitted": False,
    }
    classification = json.loads(
        (archive_dir / "checkpoint/classification.json").read_bytes()
    )
    assert classification == {
        "schema": "rook.lm9b_p.checkpoint_classification:v1",
        "classification": "probe_candidate_ready",
        "checkpoint_2": "not_evaluated",
    }


@pytest.mark.parametrize("relative_path", ARCHIVE_RECORD_PATHS)
def test_checkpoint_archive_rejects_deletion_of_every_required_record(
    sealed_checkpoint, tmp_path: Path, relative_path: str
) -> None:
    _, archive_dir = sealed_checkpoint
    damaged = tmp_path / "deleted"
    shutil.copytree(archive_dir, damaged)
    (damaged / relative_path).unlink()
    with pytest.raises(ValueError, match="sealed checkpoint archive"):
        ARTIFACTS.verify_sealed_planner_checkpoint_archive(damaged)


@pytest.mark.parametrize("relative_path", ARCHIVE_RECORD_PATHS)
def test_checkpoint_archive_rejects_mutation_of_every_required_record(
    sealed_checkpoint, tmp_path: Path, relative_path: str
) -> None:
    _, archive_dir = sealed_checkpoint
    damaged = tmp_path / "mutated"
    shutil.copytree(archive_dir, damaged)
    target = damaged / relative_path
    target.write_bytes(b"{}" if target.name == "checksums.json" else target.read_bytes() + b"!")
    with pytest.raises(ValueError, match="sealed checkpoint archive"):
        ARTIFACTS.verify_sealed_planner_checkpoint_archive(damaged)


def test_checkpoint_archive_rejects_reduced_records_even_after_recomputed_checksums(
    sealed_checkpoint, tmp_path: Path
) -> None:
    _, archive_dir = sealed_checkpoint
    damaged = tmp_path / "reduced"
    shutil.copytree(archive_dir, damaged)
    removed = "planner/final_recipe_identity.json"
    (damaged / removed).unlink()
    checksums_path = damaged / "checksums.json"
    checksums = json.loads(checksums_path.read_bytes())
    checksums["records"] = [
        record for record in checksums["records"] if record["path"] != removed
    ]
    checksums_path.write_text(json.dumps(checksums), encoding="utf-8")
    _recompute_checksums(damaged)
    with pytest.raises(ValueError, match="sealed checkpoint archive"):
        ARTIFACTS.verify_sealed_planner_checkpoint_archive(damaged)


def test_checkpoint_archive_preserves_every_planner_tool_argument(
    tmp_path: Path,
) -> None:
    first = '{"recipe_json":"{}"}'
    second = '{"malformed":true}'
    planner = _turn_with_tool_calls(
        role="planner",
        calls=[
            {
                "id": "planner-call-1",
                "function": {"name": "submit_planner_recipe", "arguments": first},
            },
            {
                "id": "planner-call-2",
                "function": {"name": "unexpected", "arguments": second},
            },
        ],
    )
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=_Provider([planner]),
        evaluator_provider=_Provider([RuntimeError("must not be consumed")]),
        archive_destination=tmp_path / "checkpoint-1",
        archive_identity=ARCHIVE_IDENTITY,
    )
    assert result.classification == "probe_inconclusive"
    assert (tmp_path / "checkpoint-1/planner/attempts/000/tool_arguments/000.bin").read_bytes() == first.encode("utf-8")
    assert (tmp_path / "checkpoint-1/planner/attempts/000/tool_arguments/001.bin").read_bytes() == second.encode("utf-8")


def test_checkpoint_archive_preserves_every_evaluator_tool_argument(
    tmp_path: Path,
) -> None:
    first = '{"evaluation_json":"{}"}'
    second = '{"extra":true}'
    evaluator = _turn_with_tool_calls(
        role="evaluator",
        calls=[
            {
                "id": "evaluator-call-1",
                "function": {
                    "name": "submit_planner_evaluation",
                    "arguments": first,
                },
            },
            {
                "id": "evaluator-call-2",
                "function": {"name": "unexpected", "arguments": second},
            },
        ],
    )
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=_Provider([_planner_turn_bytes(READY_RECIPE_BYTES)]),
        evaluator_provider=_Provider([evaluator]),
        archive_destination=tmp_path / "checkpoint-1",
        archive_identity=ARCHIVE_IDENTITY,
    )
    assert result.classification == "probe_inconclusive"
    assert (tmp_path / "checkpoint-1/evaluator/attempts/000/tool_arguments/000.bin").read_bytes() == first.encode("utf-8")
    assert (tmp_path / "checkpoint-1/evaluator/attempts/000/tool_arguments/001.bin").read_bytes() == second.encode("utf-8")


def test_checkpoint_archive_preserves_argument_after_a_malformed_tool_call(
    tmp_path: Path,
) -> None:
    argument = '{"evaluation_json":"{}"}'
    evaluator = _turn_with_tool_calls(
        role="evaluator",
        calls=[
            {"id": "malformed", "function": []},
            {
                "id": "evaluator-call-2",
                "function": {
                    "name": "submit_planner_evaluation",
                    "arguments": argument,
                },
            },
        ],
    )
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=_Provider([_planner_turn_bytes(READY_RECIPE_BYTES)]),
        evaluator_provider=_Provider([evaluator]),
        archive_destination=tmp_path / "checkpoint-1",
        archive_identity=ARCHIVE_IDENTITY,
    )
    assert result.classification == "probe_inconclusive"
    assert (tmp_path / "checkpoint-1/evaluator/attempts/000/tool_arguments/001.bin").read_bytes() == argument.encode("utf-8")
    assert ARTIFACTS.verify_sealed_planner_checkpoint_archive(tmp_path / "checkpoint-1")


@pytest.mark.parametrize("failure", [RuntimeError("provider unavailable"), TimeoutError("provider timeout")])
def test_evaluator_failure_paths_still_seal_complete_inconclusive_evidence(
    failure: BaseException, tmp_path: Path
) -> None:
    archive_dir = tmp_path / "checkpoint-1"
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=_Provider([_planner_turn_bytes(READY_RECIPE_BYTES)]),
        evaluator_provider=_Provider([failure]),
        archive_destination=archive_dir,
        archive_identity=ARCHIVE_IDENTITY,
    )
    assert result.classification == "probe_inconclusive"
    assert result.sealed_archive is not None
    capture = json.loads(
        (archive_dir / "evaluator/attempts/000/capture.json").read_bytes()
    )
    assert capture["outcome"] == "raised"
    assert capture["exception_type"] == type(failure).__name__
    assert ARTIFACTS.verify_sealed_planner_checkpoint_archive(archive_dir)


def test_checkpoint_archive_rejects_a_valid_but_non_head_git_sha(
    tmp_path: Path,
) -> None:
    identity = dict(ARCHIVE_IDENTITY)
    identity["git_commit_sha"] = "f" * 40
    with pytest.raises(ValueError, match="checked-out HEAD"):
        PROBE.run_planner_checkpoint(
            fixture_dir=FIXTURES,
            planner_provider=_Provider([_planner_turn_bytes(READY_RECIPE_BYTES)]),
            evaluator_provider=_Provider([_evaluator_turn("faithful_ready")]),
            archive_destination=tmp_path / "checkpoint-1",
            archive_identity=identity,
        )


def test_checkpoint_archive_never_overwrites_an_existing_seal(
    sealed_checkpoint,
) -> None:
    _, archive_dir = sealed_checkpoint
    with pytest.raises(FileExistsError, match="already exists"):
        PROBE.run_planner_checkpoint(
            fixture_dir=FIXTURES,
            planner_provider=_Provider([_planner_turn_bytes(READY_RECIPE_BYTES)]),
            evaluator_provider=_Provider([_evaluator_turn("faithful_ready")]),
            archive_destination=archive_dir,
            archive_identity=ARCHIVE_IDENTITY,
        )


def test_mechanically_rejected_checkpoint_seals_without_an_evaluator_call(
    tmp_path: Path,
) -> None:
    archive_dir = tmp_path / "checkpoint-1"
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=_Provider(
            [_empty_planner_turn() for _ in range(SUPPORT.PLANNER_MAX_TURNS)]
        ),
        evaluator_provider=_Provider([RuntimeError("must not be consumed")]),
        archive_destination=archive_dir,
        archive_identity=ARCHIVE_IDENTITY,
    )
    assert result.classification == "probe_mechanically_rejected"
    assert result.sealed_archive is not None
    assert (archive_dir / "evaluator/not_run.json").is_file()
    assert ARTIFACTS.verify_sealed_planner_checkpoint_archive(archive_dir)


def test_pre_freeze_checkpoint_and_sealing_never_read_hidden_controls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    forbidden = {
        (COMPILER_FIXTURES / "input_manifest.json").resolve(),
        (COMPILER_FIXTURES / "r01_recipe.json").resolve(),
        READY_RECIPE.resolve(),
        BLOCKED_RECIPE.resolve(),
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
    PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=_Provider([_planner_turn_bytes(READY_RECIPE_BYTES)]),
        evaluator_provider=_Provider([_evaluator_turn("faithful_ready")]),
        archive_destination=tmp_path / "checkpoint-1",
        archive_identity=ARCHIVE_IDENTITY,
    )
    assert observed == set()


def test_post_freeze_r01_comparison_requires_verified_sealed_aggregate_and_preserves_archive(
    sealed_checkpoint,
) -> None:
    result, archive_dir = sealed_checkpoint
    before = (archive_dir / "checksums.json").read_bytes()
    with pytest.raises(ValueError, match="sealed aggregate identity"):
        ARTIFACTS.compare_sealed_checkpoint_with_r01(
            archive_dir=archive_dir,
            sealed_aggregate_identity="sha256:" + "0" * 64,
            r01_recipe_path=COMPILER_FIXTURES / "r01_recipe.json",
        )
    comparison = ARTIFACTS.compare_sealed_checkpoint_with_r01(
        archive_dir=archive_dir,
        sealed_aggregate_identity=result.sealed_archive.aggregate_identity,
        r01_recipe_path=COMPILER_FIXTURES / "r01_recipe.json",
    )
    assert comparison["sealed_aggregate_identity"] == result.sealed_archive.aggregate_identity
    assert comparison["r01_raw_sha256"].startswith("sha256:")
    assert (archive_dir / "checksums.json").read_bytes() == before
