from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from dataclasses import fields
from pathlib import Path
from threading import Barrier, Thread
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
FIXTURES = SCRIPTS / "lm9b_p_fixtures"
BLOCKED_RECIPE = (
    ROOT / "mcp_server/tests/fixtures/lm9b_p/non_r01_blocked_recipe.json"
)


def _load_script(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SUPPORT = _load_script("lm9b_p_planner_recipe_transfer_support")
PLANNER_ARTIFACTS = _load_script("lm9b_p_planner_recipe_transfer_artifacts")
READINESS_CONTRACT = _load_script("lm9b_p_readiness_contract")
READINESS_PROBE = _load_script("lm9b_p_readiness_probe")
CONT_ARTIFACTS = _load_script("lm9b_p_evaluator_only_continuation_artifacts")
CONTINUATION = _load_script("lm9b_p_evaluator_only_continuation")
PLANNER_PROBE = CONTINUATION.PLANNER_PROBE


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


class _ReadinessClock:
    def __init__(self) -> None:
        self.second = 0

    def __call__(self) -> str:
        self.second += 1
        return f"2026-07-22T12:00:{self.second:02d}Z"


def _readiness_provider(_route):
    def call(_request):
        return SUPPORT.ProviderTurn(
            raw_request=b'{"canary":true}',
            raw_response=b'{"canary":"ok"}',
            assistant_message={
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "canary-1",
                        "type": "function",
                        "function": {
                            "name": "ack",
                            "arguments": '{"ok": true}',
                        },
                    }
                ],
            },
            usage={},
            provider_metadata={},
        )

    return call


class _EvaluatorProvider:
    def __init__(self, recommendation: str = "semantically_faithful") -> None:
        self.model = "gpt-5.4"
        self.temperature = 0.0
        self.profile_identity = "litellm.completion.tool_calling.no_parallel:v1"
        self.identity = {
            "adapter_path": "litellm.completion",
            "model": self.model,
            "profile_identity": self.profile_identity,
            "temperature": self.temperature,
        }
        self.calls = 0
        self.received_canonical_bytes: bytes | None = None
        self.recommendation = recommendation

    def __call__(self, request: dict[str, object]):
        self.calls += 1
        self.received_canonical_bytes = json.dumps(
            request,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        request["provider_mutation"] = True
        report = {
            "recommendation": self.recommendation,
            "evidence": [
                {
                    "criterion_id": "brief_fidelity",
                    "finding": "The submitted recipe preserves the visible brief.",
                }
            ],
        }
        arguments = json.dumps(
            {"evaluation_json": json.dumps(report, separators=(",", ":"))},
            separators=(",", ":"),
        )
        return SUPPORT.ProviderTurn(
            raw_request=b'{"adapter":"request"}',
            raw_response=b'{"provider":"response"}',
            assistant_message={
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "evaluation-1",
                        "type": "function",
                        "function": {
                            "name": "submit_planner_evaluation",
                            "arguments": arguments,
                        },
                    }
                ],
            },
            usage={"total_tokens": 37},
            provider_metadata={
                "model_identity": self.model,
                "profile_identity": self.profile_identity,
                "provider": "openai",
            },
        )


class _RaisingEvaluatorProvider(_EvaluatorProvider):
    def __init__(self, exception: BaseException) -> None:
        super().__init__()
        self.exception = exception

    def __call__(self, request: dict[str, object]):
        self.calls += 1
        self.received_canonical_bytes = json.dumps(
            request,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        raise self.exception


class _MalformedEvaluatorProvider(_EvaluatorProvider):
    def __call__(self, request: dict[str, object]):
        self.calls += 1
        self.received_canonical_bytes = json.dumps(
            request,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return SUPPORT.ProviderTurn(
            raw_request=b'{"adapter":"request"}',
            raw_response=b'{"provider":"malformed"}',
            assistant_message={"role": "assistant", "content": "no tool call"},
            usage={"total_tokens": 9},
            provider_metadata={
                "model_identity": self.model,
                "profile_identity": self.profile_identity,
            },
        )


def _execution_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider: object,
):
    pins = _sealed_historical_source(tmp_path / "source")
    source_digest = _tree_digest(pins.source_root)
    head = "f" * 40
    monkeypatch.setattr(CONT_ARTIFACTS, "PRODUCTION_SOURCE_PINS", pins)
    monkeypatch.setattr(CONTINUATION, "_git_checkout_state", lambda: (head, True))
    derivative_root = tmp_path / "derivatives"
    derivative_root.mkdir()
    destination = derivative_root / "evaluator-observation-01"
    preflight = CONTINUATION.emit_no_contact_preflight(
        CONTINUATION.PreflightConfig(
            output_dir=tmp_path / "preflight",
            reviewed_commit_sha=head,
            attempt_id="evaluator-observation-01",
            derivative_root=derivative_root,
            destination=destination,
            launch_eligibility="operator_review_candidate",
        )
    )
    readiness_root = tmp_path / "readiness"
    READINESS_PROBE.run_readiness(
        run_root=readiness_root,
        head_sha=head,
        environ={"OPENAI_API_KEY": "present"},
        authenticate=True,
        provider_factory=_readiness_provider,
        clock=_ReadinessClock(),
        models={"planner_evaluator": "gpt-5.4"},
    )
    monkeypatch.setenv("OPENAI_API_KEY", "present")
    monkeypatch.setattr(
        CONTINUATION,
        "_readiness_now_iso",
        lambda: "2026-07-22T12:00:03Z",
        raising=False,
    )
    monkeypatch.setattr(CONTINUATION, "_build_evaluator_provider", lambda: provider)
    return pins, source_digest, preflight, readiness_root, destination


def _rewrite_preflight_record(preflight: Path, mutate) -> str:
    record_path = preflight / "record.json"
    record = json.loads(record_path.read_bytes())
    mutate(record)
    without = {
        key: value
        for key, value in record.items()
        if key != "preflight_fingerprint"
    }
    record["preflight_fingerprint"] = SUPPORT.fingerprint(without)
    raw = _json_bytes(record)
    record_path.write_bytes(raw)
    checksums_path = preflight / "checksums.json"
    checksums = json.loads(checksums_path.read_bytes())
    for row in checksums["records"]:
        if row["path"] == "record.json":
            row["raw_sha256"] = _sha256(raw)
            row["byte_length"] = len(raw)
    checksums["aggregate_identity"] = SUPPORT.fingerprint(
        {
            "schema_id": checksums["schema_id"],
            "records": checksums["records"],
        }
    )
    checksums_path.write_bytes(_json_bytes(checksums))
    return record["preflight_fingerprint"]


def _reclose_derivative_checksums(archive: Path) -> str:
    checksums_path = archive / "checksums.json"
    checksums = json.loads(checksums_path.read_bytes())
    for row in checksums["records"]:
        raw = (archive / row["path"]).read_bytes()
        row["raw_sha256"] = _sha256(raw)
        row["byte_length"] = len(raw)
    checksums["derivative_archive_identity"] = SUPPORT.fingerprint(
        {
            "schema": checksums["schema"],
            "records": checksums["records"],
        }
    )
    checksums_path.write_bytes(_json_bytes(checksums))
    return checksums["derivative_archive_identity"]


def _rewrite_derivative_subject_identity(archive: Path) -> None:
    identity_path = archive / "identity.json"
    identity = json.loads(identity_path.read_bytes())
    result = json.loads((archive / "evaluator/result.json").read_bytes())
    decision = json.loads((archive / "decision/classification.json").read_bytes())
    subject = {
        "preflight_fingerprint": identity["preflight_fingerprint"],
        "instrument_fingerprint": identity["instrument_fingerprint"],
        "attempt_id": identity["attempt_id"],
        "attempt_fingerprint": identity["attempt_fingerprint"],
        "reviewed_commit_sha": identity["reviewed_commit_sha"],
        "model": identity["model"],
        "provider_profile": identity["provider_profile"],
        "canonical_destination": identity["canonical_destination"],
        "evaluator_result": result,
        "classification": decision,
    }
    identity["derivative_subject_fingerprint"] = SUPPORT.fingerprint(subject)
    identity_path.write_bytes(_json_bytes(identity))


def _reclose_checkpoint(checkpoint: Path) -> str:
    checksums_path = checkpoint / "checksums.json"
    checksums = json.loads(checksums_path.read_bytes())
    for row in checksums["records"]:
        raw = (checkpoint / row["path"]).read_bytes()
        row["raw_sha256"] = _sha256(raw)
        row["byte_length"] = len(raw)
    checksums["aggregate_identity"] = SUPPORT.fingerprint(
        {
            "schema": checksums["schema"],
            "records": checksums["records"],
        }
    )
    checksums_path.write_bytes(_json_bytes(checksums))
    return checksums["aggregate_identity"]


def _historical_rubric_bytes() -> bytes:
    rubric = json.loads((FIXTURES / "planner_evaluation_rubric.json").read_bytes())
    rubric["recommendations"] = [
        "faithful_ready",
        "faithful_blocked",
        "planner_failure",
        "evaluation_inconclusive",
    ]
    rubric["rubric_fingerprint"] = SUPPORT.fingerprint_without(
        rubric, "rubric_fingerprint"
    )
    return _json_bytes(rubric)


def _sealed_historical_source(root: Path):
    checkpoint = root / "checkpoint-1"
    inputs = PLANNER_ARTIFACTS.load_planner_inputs(FIXTURES)
    recipe = BLOCKED_RECIPE.read_bytes()
    gate = SUPPORT.evaluate_mechanical_gate(
        recipe_bytes=recipe,
        authority=inputs.authority,
        recipe_schema=inputs.recipe_schema,
        normalization_profile=inputs.authority.normalization_profile,
        exclusion_policy=inputs.exclusion_policy,
    )
    assert gate.status == "mechanically_accepted", gate.diagnostics
    turn = SUPPORT.PlannerTurnRecord(
        turn_index=0,
        raw_response=b'{"planner":"response"}',
        tool_arguments=recipe,
        gate_result=gate,
        usage={},
        elapsed_ms=1,
    )
    session = SUPPORT.PlannerSessionResult(
        termination="mechanically_accepted",
        turns=(turn,),
        final_recipe_bytes=recipe,
    )
    evaluator = SUPPORT.PlannerEvaluationResult(
        termination="malformed",
        recommendation=None,
        evidence=(),
        raw_response=b'{"evaluator":"malformed"}',
        usage={},
    )
    planner_request = PLANNER_ARTIFACTS.render_planner_request(inputs)
    evaluator_request = PLANNER_ARTIFACTS.render_planner_evaluator_request(
        inputs, gate_result=gate
    )
    provider_metadata = {
        "model_identity": "gpt-5.4",
        "profile_identity": "litellm.completion.tool_calling.no_parallel:v1",
    }
    planner_provider_turn = SUPPORT.ProviderTurn(
        raw_response=turn.raw_response,
        assistant_message={},
        usage={},
        provider_metadata=provider_metadata,
        raw_request=b'{"request":true}',
    )
    evaluator_provider_turn = SUPPORT.ProviderTurn(
        raw_response=evaluator.raw_response,
        assistant_message={},
        usage={},
        provider_metadata=provider_metadata,
        raw_request=b'{"request":true}',
    )
    planner_attempt = PLANNER_ARTIFACTS.ProviderAttemptEvidence(
        provider_request_bytes=b'{"planner":true}',
        outcome="returned",
        provider_turn=planner_provider_turn,
        elapsed_ms=1,
    )
    evaluator_attempt = PLANNER_ARTIFACTS.ProviderAttemptEvidence(
        provider_request_bytes=b'{"evaluator":true}',
        outcome="returned",
        provider_turn=evaluator_provider_turn,
        elapsed_ms=1,
    )
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    PLANNER_ARTIFACTS.seal_planner_checkpoint_archive(
        destination=checkpoint,
        inputs=inputs,
        planner_request=planner_request,
        planner_session=session,
        evaluator=evaluator,
        evaluator_request=evaluator_request,
        planner_provider_attempts=(planner_attempt,),
        evaluator_provider_attempts=(evaluator_attempt,),
        evaluator_elapsed_ms=1,
        classification="probe_inconclusive",
        archive_identity={
            "git_commit_sha": head,
            "planner_model_identity": "gpt-5.4",
            "evaluator_model_identity": "gpt-5.4",
            "provider_profile_identity": "litellm.completion.tool_calling.no_parallel:v1",
        },
        checkpoint_gate=gate,
    )

    historical_rubric = _historical_rubric_bytes()
    rubric_path = checkpoint / "inputs/planner_evaluation_rubric.json"
    rubric_path.write_bytes(historical_rubric)
    input_manifest_path = checkpoint / "inputs/manifest.json"
    input_manifest = json.loads(input_manifest_path.read_bytes())
    for row in input_manifest["records"]:
        if row["role"] == "evaluation_rubric":
            value = json.loads(historical_rubric)
            row["raw_sha256"] = _sha256(historical_rubric)
            row["canonical_fingerprint"] = SUPPORT.fingerprint(value)
    input_manifest_path.write_bytes(_json_bytes(input_manifest))
    checkpoint_identity = _reclose_checkpoint(checkpoint)

    joined = root / "joined-aggregate"
    joined.mkdir(parents=True)
    joined_value = {
        "schema": "rook.lm9b_p.joined_aggregate:v1",
        "checkpoint_1": {
            "aggregate_identity": checkpoint_identity,
            "classification": "probe_inconclusive",
        },
        "checkpoint_2": {"outcome": "not_evaluated", "reason_codes": []},
        "aggregate_outcome": "probe_inconclusive",
        "handoff": None,
        "lm9b_c_archive": None,
        "pre_session_failure": None,
        "execution_permitted": False,
    }
    (joined / "aggregate.json").write_bytes(_json_bytes(joined_value))

    rows = []
    for path in sorted(path for path in root.rglob("*") if path.is_file()):
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        rows.append(f"{digest}  {relative}")
    manifest_bytes = ("\n".join(rows) + "\n").encode("utf-8")
    (root / "SHA256-MANIFEST.txt").write_bytes(manifest_bytes)

    recipe_identity = json.loads(
        (checkpoint / "planner/final_recipe_identity.json").read_bytes()
    )
    return CONT_ARTIFACTS.HistoricalSourcePins(
        source_root=root,
        root_manifest_raw_sha256=_sha256(manifest_bytes),
        checkpoint_aggregate_identity=checkpoint_identity,
        historical_commit_sha=head,
        historical_classification="probe_inconclusive",
        historical_checkpoint_2="not_evaluated",
        recipe_raw_sha256=_sha256(recipe),
        ratified_recipe_fingerprint=recipe_identity["ratified_recipe_fingerprint"],
        historical_recipe_fingerprint=recipe_identity[
            "historical_recipe_fingerprint"
        ],
    )


def test_no_contact_preflight_binds_exact_source_delta_requests_and_commit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_pins = _sealed_historical_source(tmp_path / "source")
    monkeypatch.setattr(CONT_ARTIFACTS, "PRODUCTION_SOURCE_PINS", source_pins)
    monkeypatch.setattr(
        CONTINUATION, "_git_checkout_state", lambda: ("a" * 40, True)
    )
    contacted = False

    def forbidden_provider_factory(*_args, **_kwargs):
        nonlocal contacted
        contacted = True
        raise AssertionError("preflight constructed a provider")

    monkeypatch.setattr(
        CONTINUATION, "_build_evaluator_provider", forbidden_provider_factory
    )
    derivative_root = tmp_path / "derivatives"
    derivative_root.mkdir()
    preflight = CONTINUATION.emit_no_contact_preflight(
        CONTINUATION.PreflightConfig(
            output_dir=tmp_path / "preflight",
            reviewed_commit_sha="a" * 40,
            attempt_id="visibility-evaluator-01",
            derivative_root=derivative_root,
            destination=derivative_root / "visibility-evaluator-01",
            launch_eligibility="development_non_operational",
        )
    )
    assert contacted is False
    assert preflight.record["schema_id"] == CONT_ARTIFACTS.PREFLIGHT_SCHEMA_ID
    assert preflight.record["reviewed_commit_sha"] == "a" * 40
    assert preflight.record["launch_eligibility"] == "development_non_operational"
    assert preflight.record["source"]["recipe_raw_sha256"] == source_pins.recipe_raw_sha256
    delta = json.loads(
        (preflight.archive_dir / "allowed-delta-manifest.json").read_bytes()
    )
    rows = delta["rows"]
    assert sum(
        row["disposition"] == "replaced_evaluator_rubric" for row in rows
    ) == 1
    assert all(
        row["disposition"] == "replaced_evaluator_rubric"
        or row["source_raw_sha256"] == row["instrument_raw_sha256"]
        for row in rows
    )
    assert CONT_ARTIFACTS.verify_preflight_archive(
        preflight.archive_dir,
        expected_preflight_fingerprint=preflight.preflight_fingerprint,
    ) == preflight
    assert preflight.attempt_id.encode() not in preflight.rendered_request_bytes
    assert str(preflight.destination).encode() not in preflight.rendered_request_bytes
    assert preflight.attempt_id.encode() not in preflight.provider_call_request_bytes
    assert str(preflight.destination).encode() not in preflight.provider_call_request_bytes


def test_equivalent_instruments_have_distinct_attempt_identities(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pins = _sealed_historical_source(tmp_path / "source")
    monkeypatch.setattr(CONT_ARTIFACTS, "PRODUCTION_SOURCE_PINS", pins)
    monkeypatch.setattr(
        CONTINUATION, "_git_checkout_state", lambda: ("b" * 40, True)
    )
    derivative_root = tmp_path / "derivatives"
    derivative_root.mkdir()

    def emit(name: str):
        return CONTINUATION.emit_no_contact_preflight(
            CONTINUATION.PreflightConfig(
                output_dir=tmp_path / f"preflight-{name}",
                reviewed_commit_sha="b" * 40,
                attempt_id=name,
                derivative_root=derivative_root,
                destination=derivative_root / name,
                launch_eligibility="development_non_operational",
            )
        )

    first = emit("attempt-one")
    second = emit("attempt-two")
    assert first.instrument_fingerprint == second.instrument_fingerprint
    assert first.attempt_fingerprint != second.attempt_fingerprint

    monkeypatch.setattr(
        CONTINUATION, "_git_checkout_state", lambda: ("c" * 40, True)
    )
    changed_commit = CONTINUATION.emit_no_contact_preflight(
        CONTINUATION.PreflightConfig(
            output_dir=tmp_path / "preflight-changed-commit",
            reviewed_commit_sha="c" * 40,
            attempt_id="attempt-three",
            derivative_root=derivative_root,
            destination=derivative_root / "attempt-three",
            launch_eligibility="development_non_operational",
        )
    )
    assert changed_commit.instrument_fingerprint != first.instrument_fingerprint
    assert changed_commit.attempt_fingerprint != first.attempt_fingerprint


def test_attempt_binding_rejects_noncanonical_destination(tmp_path: Path) -> None:
    derivative_root = tmp_path / "derivatives"
    derivative_root.mkdir()
    with pytest.raises(ValueError, match="canonical"):
        CONT_ARTIFACTS.bind_attempt(
            instrument_fingerprint="sha256:" + "a" * 64,
            attempt_id="traversal-attempt",
            derivative_root=derivative_root,
            destination=derivative_root / "temporary" / ".." / "traversal-attempt",
        )


def test_preflight_rejects_nested_destination(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pins = _sealed_historical_source(tmp_path / "source")
    monkeypatch.setattr(CONT_ARTIFACTS, "PRODUCTION_SOURCE_PINS", pins)
    monkeypatch.setattr(
        CONTINUATION, "_git_checkout_state", lambda: ("c" * 40, True)
    )
    derivative_root = tmp_path / "derivatives"
    derivative_root.mkdir()
    with pytest.raises(ValueError, match="direct child"):
        CONTINUATION.emit_no_contact_preflight(
            CONTINUATION.PreflightConfig(
                output_dir=tmp_path / "preflight",
                reviewed_commit_sha="c" * 40,
                attempt_id="nested-attempt",
                derivative_root=derivative_root,
                destination=derivative_root / "nested" / "nested-attempt",
                launch_eligibility="development_non_operational",
            )
        )


def test_preflight_verifier_rejects_extra_members(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pins = _sealed_historical_source(tmp_path / "source")
    monkeypatch.setattr(CONT_ARTIFACTS, "PRODUCTION_SOURCE_PINS", pins)
    monkeypatch.setattr(
        CONTINUATION, "_git_checkout_state", lambda: ("d" * 40, True)
    )
    derivative_root = tmp_path / "derivatives"
    derivative_root.mkdir()
    preflight = CONTINUATION.emit_no_contact_preflight(
        CONTINUATION.PreflightConfig(
            output_dir=tmp_path / "preflight",
            reviewed_commit_sha="d" * 40,
            attempt_id="closed-preflight",
            derivative_root=derivative_root,
            destination=derivative_root / "closed-preflight",
            launch_eligibility="development_non_operational",
        )
    )
    (preflight.archive_dir / "unexpected.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="file set"):
        CONT_ARTIFACTS.verify_preflight_archive(
            preflight.archive_dir,
            expected_preflight_fingerprint=preflight.preflight_fingerprint,
        )


@pytest.mark.parametrize(
    "mutation",
    ["source_shape", "protocol_shape", "nested_destination"],
)
def test_preflight_verifier_rejects_reclosed_identity_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mutation: str,
) -> None:
    pins = _sealed_historical_source(tmp_path / "source")
    monkeypatch.setattr(CONT_ARTIFACTS, "PRODUCTION_SOURCE_PINS", pins)
    monkeypatch.setattr(
        CONTINUATION, "_git_checkout_state", lambda: ("e" * 40, True)
    )
    derivative_root = tmp_path / "derivatives"
    derivative_root.mkdir()
    preflight = CONTINUATION.emit_no_contact_preflight(
        CONTINUATION.PreflightConfig(
            output_dir=tmp_path / "preflight",
            reviewed_commit_sha="e" * 40,
            attempt_id="identity-drift",
            derivative_root=derivative_root,
            destination=derivative_root / "identity-drift",
            launch_eligibility="development_non_operational",
        )
    )

    def mutate(record: dict[str, object]) -> None:
        if mutation == "source_shape":
            record["source"]["unexpected"] = True
        elif mutation == "protocol_shape":
            record["instrument"]["protocol_identity"]["unexpected"] = True
        elif mutation == "nested_destination":
            record["attempt"]["canonical_destination"] = str(
                derivative_root / "nested" / "identity-drift"
            )
        else:  # pragma: no cover - parameter list is closed above.
            raise AssertionError(mutation)

    changed_fingerprint = _rewrite_preflight_record(preflight.archive_dir, mutate)
    with pytest.raises(ValueError, match="identity|destination|shape"):
        CONT_ARTIFACTS.verify_preflight_archive(
            preflight.archive_dir,
            expected_preflight_fingerprint=changed_fingerprint,
        )


def test_vertical_continuation_dispatches_once_and_never_enters_compiler(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    provider = _EvaluatorProvider()
    pins, source_digest, preflight, readiness_root, destination = (
        _execution_fixture(monkeypatch, tmp_path, provider)
    )
    original_preflight_provider_bytes = (
        preflight.archive_dir / "provider-call-request.json"
    ).read_bytes()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("compiler-specific behavior was reached")

    monkeypatch.setattr(PLANNER_PROBE, "run_joined_probe", forbidden)
    monkeypatch.setattr(PLANNER_PROBE, "_freeze_compiler_controls", forbidden)
    monkeypatch.setattr(PLANNER_ARTIFACTS, "build_lm9bc_handoff", forbidden)

    assert CONTINUATION.main(
        [
            "execute",
            "--preflight-dir",
            str(preflight.archive_dir),
            "--expected-preflight-fingerprint",
            preflight.preflight_fingerprint,
            "--readiness-record",
            str(readiness_root / "readiness_record.json"),
            "--credential-preflight",
            str(readiness_root / "preflight.json"),
            "--transmit",
        ]
    ) == 0

    assert provider.calls == 1
    assert provider.received_canonical_bytes == preflight.provider_call_request_bytes
    assert preflight.provider_call_request_bytes == original_preflight_provider_bytes
    assert (
        preflight.archive_dir / "provider-call-request.json"
    ).read_bytes() == original_preflight_provider_bytes
    sealed = CONT_ARTIFACTS.verify_sealed_derivative_archive(destination)
    assert sealed.classification == "probe_candidate_blocked"
    assert sealed.identity["schema_id"] == CONT_ARTIFACTS.DERIVATIVE_SCHEMA_ID
    assert sealed.identity["attempt_fingerprint"] == preflight.attempt_fingerprint
    assert json.loads((destination / "boundary.json").read_bytes()) == {
        "schema": "rook.lm9b_p.evaluator.continuation_boundary:v1",
        "derivative_observation": True,
        "replaces_historical_result": False,
        "planner_entry": "absent",
        "compiler_entry": "absent",
        "checkpoint_2": "not_evaluated",
        "execution_permitted": False,
    }
    assert not any(
        "compiler" in path.relative_to(destination).as_posix().casefold()
        for path in destination.rglob("*")
    )
    assert _tree_digest(pins.source_root) == source_digest


@pytest.mark.parametrize(
    ("fault", "expected_state", "expected_classification"),
    [
        ("provider_mutates", "sealed", "probe_candidate_blocked"),
        ("provider_exception", "sealed", "probe_inconclusive"),
        ("quiescent_timeout", "sealed", "probe_inconclusive"),
        ("malformed_report", "sealed", "probe_inconclusive"),
        ("evaluation_inconclusive", "sealed", "probe_inconclusive"),
        ("semantically_unfaithful", "sealed", "probe_planner_failure"),
        ("ambiguous_timeout", "post_dispatch_unsealed", None),
        ("interrupt_after_dispatch_marker", "post_dispatch_unsealed", None),
        ("evidence_corruption", "post_dispatch_unsealed", None),
        ("snapshot_identity_mismatch", "post_dispatch_unsealed", None),
        ("classification_failure", "post_dispatch_unsealed", None),
        ("checksum_failure", "post_dispatch_unsealed", None),
    ],
)
def test_post_dispatch_outcome_and_fault_matrix(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fault: str,
    expected_state: str,
    expected_classification: str | None,
) -> None:
    if fault == "provider_exception":
        provider = _RaisingEvaluatorProvider(RuntimeError("provider failed"))
    elif fault == "quiescent_timeout":
        provider = _RaisingEvaluatorProvider(TimeoutError("provider timed out"))
    elif fault == "malformed_report":
        provider = _MalformedEvaluatorProvider()
    elif fault == "evaluation_inconclusive":
        provider = _EvaluatorProvider("evaluation_inconclusive")
    elif fault == "semantically_unfaithful":
        provider = _EvaluatorProvider("semantically_unfaithful")
    else:
        provider = _EvaluatorProvider()
    _pins, _source_digest, preflight, readiness_root, _destination = (
        _execution_fixture(monkeypatch, tmp_path, provider)
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("compiler-specific behavior was reached")

    monkeypatch.setattr(PLANNER_PROBE, "run_joined_probe", forbidden)
    monkeypatch.setattr(PLANNER_PROBE, "_freeze_compiler_controls", forbidden)
    monkeypatch.setattr(PLANNER_ARTIFACTS, "build_lm9bc_handoff", forbidden)

    if fault == "ambiguous_timeout":
        monkeypatch.setattr(
            SUPPORT,
            "run_planner_evaluation",
            lambda **_kwargs: SUPPORT.PlannerEvaluationResult(
                "timeout", None, (), None, None, quiescent=False
            ),
        )
    elif fault == "interrupt_after_dispatch_marker":
        monkeypatch.setattr(
            SUPPORT,
            "run_planner_evaluation",
            lambda **_kwargs: (_ for _ in ()).throw(
                RuntimeError("interrupted after dispatch marker")
            ),
        )
    elif fault == "evidence_corruption":
        monkeypatch.setattr(
            CONT_ARTIFACTS,
            "_attempt_members",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                ValueError("captured evidence corrupted")
            ),
        )
    elif fault == "snapshot_identity_mismatch":
        monkeypatch.setattr(
            CONT_ARTIFACTS,
            "seal_derivative_archive",
            lambda **_kwargs: (_ for _ in ()).throw(
                ValueError("staged snapshot identity mismatch")
            ),
        )
    elif fault == "classification_failure":
        monkeypatch.setattr(
            PLANNER_ARTIFACTS,
            "derive_evaluated_recipe_classification",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                ValueError("classification derivation failed")
            ),
        )
    elif fault == "checksum_failure":
        original_write = CONT_ARTIFACTS._write_exclusive

        def fail_checksum(path: Path, raw: bytes) -> None:
            if path.name == "checksums.json":
                raise OSError("checksum persistence failed")
            original_write(path, raw)

        monkeypatch.setattr(CONT_ARTIFACTS, "_write_exclusive", fail_checksum)

    result = CONTINUATION.execute_continuation(
        CONTINUATION.ExecutionConfig(
            preflight_dir=preflight.archive_dir,
            expected_preflight_fingerprint=preflight.preflight_fingerprint,
            readiness_record=readiness_root / "readiness_record.json",
            credential_preflight=readiness_root / "preflight.json",
            transmit=True,
        )
    )
    assert provider.calls <= 1
    assert result.state == expected_state
    if expected_state == "sealed":
        sealed = CONT_ARTIFACTS.verify_sealed_derivative_archive(result.archive_dir)
        assert sealed.classification == expected_classification
    else:
        marker = json.loads(
            (result.staging_dir / "post_dispatch_unsealed.json").read_bytes()
        )
        assert marker["schema_id"] == CONT_ARTIFACTS.UNSEALED_SCHEMA_ID
        assert marker["attempt_fingerprint"] == preflight.attempt_fingerprint
        assert marker["classification"] is None
        with pytest.raises(ValueError):
            CONT_ARTIFACTS.verify_sealed_derivative_archive(result.staging_dir)


@pytest.mark.parametrize(
    "mutation",
    [
        "source_manifest",
        "source_file",
        "checkpoint_seal",
        "non_rubric_input",
        "corrected_rubric",
        "allowed_delta",
        "system_prompt",
        "renderer",
        "report_schema",
        "recommendation_meanings",
        "tool_schema",
        "limit",
        "provider_builder",
        "route",
        "model",
        "profile",
        "commit",
        "dirty",
        "rendered_request",
        "provider_request",
        "destination_exists",
        "destination_nested",
        "destination_escape",
        "reparse_root",
    ],
)
def test_every_pre_contact_drift_refuses_before_evaluator_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mutation: str,
) -> None:
    provider = _EvaluatorProvider()
    pins, _source_digest, preflight, readiness_root, destination = (
        _execution_fixture(monkeypatch, tmp_path, provider)
    )
    expected_fingerprint = preflight.preflight_fingerprint

    if mutation == "source_manifest":
        manifest = pins.source_root / "SHA256-MANIFEST.txt"
        manifest.write_bytes(manifest.read_bytes() + b"x")
    elif mutation == "source_file":
        target = pins.source_root / "_launch-logs/2026-07-22-visibility.launch.out.txt"
        if not target.exists():
            target = next(
                path
                for path in pins.source_root.rglob("*")
                if path.is_file() and path.name != "SHA256-MANIFEST.txt"
            )
        target.write_bytes(target.read_bytes() + b"x")
    elif mutation == "checkpoint_seal":
        target = pins.source_root / "checkpoint-1/checksums.json"
        target.write_bytes(target.read_bytes() + b"x")
    elif mutation == "non_rubric_input":
        target = pins.source_root / "checkpoint-1/inputs/task_envelope.json"
        target.write_bytes(target.read_bytes() + b"x")
    elif mutation == "corrected_rubric":
        changed = tmp_path / "changed-rubric.json"
        value = json.loads(CONTINUATION.CORRECTED_RUBRIC_PATH.read_bytes())
        value["rubric_id"] = "changed-rubric"
        value["rubric_fingerprint"] = SUPPORT.fingerprint_without(
            value, "rubric_fingerprint"
        )
        changed.write_bytes(_json_bytes(value))
        monkeypatch.setattr(CONTINUATION, "CORRECTED_RUBRIC_PATH", changed)
    elif mutation == "allowed_delta":
        target = preflight.archive_dir / "allowed-delta-manifest.json"
        target.write_bytes(target.read_bytes() + b"x")
    elif mutation == "system_prompt":
        monkeypatch.setattr(
            SUPPORT,
            "PLANNER_EVALUATOR_SYSTEM_PROMPT",
            SUPPORT.PLANNER_EVALUATOR_SYSTEM_PROMPT + " drift",
        )
    elif mutation == "renderer":
        monkeypatch.setattr(
            PLANNER_ARTIFACTS,
            "PLANNER_EVALUATOR_RENDERER_ID",
            "lm9b_p.planner_evaluator_request_renderer:drift",
        )
    elif mutation == "report_schema":
        changed = copy.deepcopy(SUPPORT.PLANNER_EVALUATION_REPORT_SCHEMA)
        changed["title"] = "drift"
        monkeypatch.setattr(SUPPORT, "PLANNER_EVALUATION_REPORT_SCHEMA", changed)
    elif mutation == "recommendation_meanings":
        changed = dict(SUPPORT.PLANNER_EVALUATION_RECOMMENDATION_MEANINGS)
        changed["semantically_faithful"] += " drift"
        monkeypatch.setattr(
            SUPPORT, "PLANNER_EVALUATION_RECOMMENDATION_MEANINGS", changed
        )
    elif mutation == "tool_schema":
        original = SUPPORT.planner_evaluator_tool_definition

        def changed_tool():
            value = original()
            value["function"]["description"] += " drift"
            return value

        monkeypatch.setattr(SUPPORT, "planner_evaluator_tool_definition", changed_tool)
    elif mutation == "limit":
        monkeypatch.setattr(
            SUPPORT,
            "PLANNER_EVALUATOR_MAX_COMPLETION_TOKENS",
            SUPPORT.PLANNER_EVALUATOR_MAX_COMPLETION_TOKENS + 1,
        )
    elif mutation == "provider_builder":
        original = SUPPORT.build_planner_evaluator_provider_call_request

        def changed_builder(**kwargs):
            value = json.loads(original(**kwargs))
            value["builder_drift"] = True
            return json.dumps(
                value, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")

        monkeypatch.setattr(
            SUPPORT, "build_planner_evaluator_provider_call_request", changed_builder
        )
    elif mutation == "route":
        target = readiness_root / "readiness_record.json"
        value = json.loads(target.read_bytes())
        value["routes"][0]["member_roles"] = ["planner"]
        value["record_fingerprint"] = READINESS_CONTRACT.record_fingerprint(value)
        target.write_bytes(_json_bytes(value))
    elif mutation == "model":
        monkeypatch.setattr(CONT_ARTIFACTS, "EVALUATOR_MODEL", "gpt-5.5")
    elif mutation == "profile":
        provider.profile_identity = "profile-drift"
        provider.identity["profile_identity"] = "profile-drift"
    elif mutation == "commit":
        monkeypatch.setattr(
            CONTINUATION, "_git_checkout_state", lambda: ("0" * 40, True)
        )
    elif mutation == "dirty":
        monkeypatch.setattr(
            CONTINUATION, "_git_checkout_state", lambda: ("f" * 40, False)
        )
    elif mutation == "rendered_request":
        target = preflight.archive_dir / "rendered-evaluator-request.json"
        target.write_bytes(target.read_bytes() + b"x")
    elif mutation == "provider_request":
        target = preflight.archive_dir / "provider-call-request.json"
        target.write_bytes(target.read_bytes() + b"x")
    elif mutation == "destination_exists":
        destination.mkdir()
    elif mutation in {"destination_nested", "destination_escape"}:
        replacement = (
            preflight.derivative_root / "nested" / "observation"
            if mutation == "destination_nested"
            else tmp_path / "escaped-observation"
        )

        def change_destination(record: dict[str, object]) -> None:
            record["attempt"]["canonical_destination"] = str(replacement)

        expected_fingerprint = _rewrite_preflight_record(
            preflight.archive_dir, change_destination
        )
    elif mutation == "reparse_root":
        monkeypatch.setattr(
            CONT_ARTIFACTS.os,
            "lstat",
            lambda _path: SimpleNamespace(st_file_attributes=0x400),
        )
    else:  # pragma: no cover - parameter vocabulary is closed above.
        raise AssertionError(mutation)

    with pytest.raises((ValueError, RuntimeError, FileExistsError, OSError)):
        CONTINUATION._verify_pre_dispatch(
            CONTINUATION.ExecutionConfig(
                preflight_dir=preflight.archive_dir,
                expected_preflight_fingerprint=expected_fingerprint,
                readiness_record=readiness_root / "readiness_record.json",
                credential_preflight=readiness_root / "preflight.json",
                transmit=True,
            )
        )
    assert provider.calls == 0
    assert not (preflight.staging_path / "dispatch/dispatch-started.json").exists()


def test_irreversible_boundary_operation_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    provider = _EvaluatorProvider()
    _pins, _source_digest, preflight, readiness_root, _destination = (
        _execution_fixture(monkeypatch, tmp_path, provider)
    )
    trace: list[str] = []

    def wrap(module, name: str, label: str):
        original = getattr(module, name)

        def traced(*args, **kwargs):
            trace.append(label)
            return original(*args, **kwargs)

        monkeypatch.setattr(module, name, traced)

    wrap(CONT_ARTIFACTS, "verify_preflight_archive", "verify_preflight")
    wrap(CONTINUATION, "_git_checkout_state", "git_state")
    wrap(CONT_ARTIFACTS, "verify_historical_source", "verify_source")
    original_read = CONTINUATION._stable_read

    def traced_read(path: Path, label: str):
        if label == "corrected evaluator rubric":
            trace.append("read_rubric")
        elif label == "readiness record":
            trace.append("read_readiness")
        return original_read(path, label)

    monkeypatch.setattr(CONTINUATION, "_stable_read", traced_read)
    wrap(CONTINUATION, "_build_evaluator_provider", "build_provider")
    wrap(CONT_ARTIFACTS, "reserve_staging", "reserve_staging")
    wrap(CONT_ARTIFACTS, "write_static_derivative_snapshot", "persist_snapshot")
    wrap(
        SUPPORT,
        "materialize_planner_evaluator_provider_call_request",
        "materialize_request",
    )
    wrap(CONT_ARTIFACTS, "write_dispatch_started", "dispatch_marker")
    wrap(SUPPORT, "run_planner_evaluation", "run_evaluator")

    result = CONTINUATION.execute_continuation(
        CONTINUATION.ExecutionConfig(
            preflight_dir=preflight.archive_dir,
            expected_preflight_fingerprint=preflight.preflight_fingerprint,
            readiness_record=readiness_root / "readiness_record.json",
            credential_preflight=readiness_root / "preflight.json",
            transmit=True,
        )
    )
    assert result.state == "sealed"
    ordered = [
        "verify_preflight",
        "git_state",
        "verify_source",
        "read_rubric",
        "read_readiness",
        "build_provider",
        "reserve_staging",
        "persist_snapshot",
        "materialize_request",
        "dispatch_marker",
        "run_evaluator",
    ]
    cursor = -1
    for label in ordered:
        next_index = trace.index(label, cursor + 1)
        assert next_index > cursor, trace
        cursor = next_index
    assert trace.index("dispatch_marker") < trace.index("run_evaluator")
    assert provider.calls == 1


@pytest.mark.parametrize(
    ("rename_case", "expected"),
    [
        ("success", "sealed"),
        ("success_then_exception", "sealed"),
        ("failure_before_move", "post_dispatch_unsealed"),
        ("destination_appears_before_rename", "ambiguous_unsealed"),
        ("invalid_destination_after_move", "ambiguous_unsealed"),
        ("both_staging_and_destination", "ambiguous_unsealed"),
    ],
)
def test_atomic_rename_reconciliation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    rename_case: str,
    expected: str,
) -> None:
    provider = _EvaluatorProvider()
    _pins, _source_digest, preflight, readiness_root, destination = (
        _execution_fixture(monkeypatch, tmp_path, provider)
    )
    sealed = CONTINUATION.execute_continuation(
        CONTINUATION.ExecutionConfig(
            preflight_dir=preflight.archive_dir,
            expected_preflight_fingerprint=preflight.preflight_fingerprint,
            readiness_record=readiness_root / "readiness_record.json",
            credential_preflight=readiness_root / "preflight.json",
            transmit=True,
        )
    )
    staging = preflight.staging_path
    destination.rename(staging)
    expected_identity = sealed.derivative_archive_identity
    original_rename = Path.rename

    def rename_behavior(self: Path, target: Path):
        if rename_case == "success_then_exception":
            original_rename(self, target)
            raise OSError("ambiguous success")
        if rename_case == "failure_before_move":
            raise OSError("move did not begin")
        if rename_case == "destination_appears_before_rename":
            shutil.copytree(self, target)
            return original_rename(self, target)
        if rename_case == "invalid_destination_after_move":
            original_rename(self, target)
            (target / "identity.json").write_bytes(b"corrupt")
            raise OSError("move outcome invalid")
        if rename_case == "both_staging_and_destination":
            shutil.copytree(self, target)
            raise OSError("copy happened instead of move")
        return original_rename(self, target)

    if rename_case != "success":
        monkeypatch.setattr(Path, "rename", rename_behavior)
    result = CONT_ARTIFACTS.finalize_derivative_archive(
        staging,
        destination,
        expected_derivative_identity=expected_identity,
    )
    assert result.state == expected
    if expected == "sealed":
        verified = CONT_ARTIFACTS.verify_sealed_derivative_archive(
            destination,
            expected_derivative_identity=expected_identity,
        )
        assert verified.derivative_archive_identity == expected_identity
    else:
        assert result.classification is None
        assert staging.exists() or destination.exists()
        if rename_case == "invalid_destination_after_move":
            assert (destination / "post_dispatch_unsealed.json").is_file()
        if rename_case in {
            "destination_appears_before_rename",
            "both_staging_and_destination",
        }:
            assert staging.exists() and destination.exists()
            competing = CONT_ARTIFACTS.verify_sealed_derivative_archive(
                destination,
                expected_derivative_identity=expected_identity,
            )
            assert competing.derivative_archive_identity == expected_identity


def test_continuation_surface_has_no_planner_or_compiler_inputs(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert [field.name for field in fields(CONTINUATION.ExecutionConfig)] == [
        "preflight_dir",
        "expected_preflight_fingerprint",
        "readiness_record",
        "credential_preflight",
        "transmit",
    ]
    with pytest.raises(SystemExit) as stopped:
        CONTINUATION.main(["execute", "--help"])
    assert stopped.value.code == 0
    help_text = capsys.readouterr().out.casefold()
    for forbidden in (
        "planner-provider",
        "compiler-provider",
        "compiler-fixture",
        "compiler-identity",
        "handoff",
        "checkpoint-2",
    ):
        assert forbidden not in help_text


def test_concurrent_reservation_has_exactly_one_winner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    provider = _EvaluatorProvider()
    _pins, _source_digest, preflight, _readiness_root, _destination = (
        _execution_fixture(monkeypatch, tmp_path, provider)
    )
    attempt = CONT_ARTIFACTS.bind_attempt(
        instrument_fingerprint=preflight.instrument_fingerprint,
        attempt_id=preflight.attempt_id,
        derivative_root=preflight.derivative_root,
        destination=preflight.destination,
    )
    barrier = Barrier(2)
    outcomes: list[str] = []

    def reserve() -> None:
        barrier.wait()
        try:
            CONT_ARTIFACTS.reserve_staging(attempt)
        except FileExistsError:
            outcomes.append("exists")
        else:
            outcomes.append("reserved")

    threads = [Thread(target=reserve), Thread(target=reserve)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["exists", "reserved"]
    assert attempt.staging_path.is_dir()


def test_external_source_and_rubric_are_not_reread_after_reservation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    provider = _EvaluatorProvider()
    pins, _source_digest, preflight, readiness_root, _destination = (
        _execution_fixture(monkeypatch, tmp_path, provider)
    )
    reserved = False
    external_reads: list[Path] = []
    original_reserve = CONT_ARTIFACTS.reserve_staging
    original_read = Path.read_bytes

    def traced_reserve(attempt):
        nonlocal reserved
        result = original_reserve(attempt)
        reserved = True
        return result

    def guarded_read(path: Path):
        resolved = path.resolve()
        if reserved and (
            resolved.is_relative_to(pins.source_root.resolve())
            or resolved == CONTINUATION.CORRECTED_RUBRIC_PATH.resolve()
        ):
            external_reads.append(resolved)
            raise AssertionError("external source reread after reservation")
        return original_read(path)

    monkeypatch.setattr(CONT_ARTIFACTS, "reserve_staging", traced_reserve)
    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    result = CONTINUATION.execute_continuation(
        CONTINUATION.ExecutionConfig(
            preflight_dir=preflight.archive_dir,
            expected_preflight_fingerprint=preflight.preflight_fingerprint,
            readiness_record=readiness_root / "readiness_record.json",
            credential_preflight=readiness_root / "preflight.json",
            transmit=True,
        )
    )
    assert result.state == "sealed"
    assert external_reads == []


@pytest.mark.parametrize(
    "member",
    [
        "compiler/unexpected.json",
        "handoff/unexpected.json",
        "checkpoint-2/unexpected.json",
        "successor-disposition.json",
        "unknown.json",
    ],
)
def test_derivative_archive_rejects_forbidden_or_unknown_members(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    member: str,
) -> None:
    provider = _EvaluatorProvider()
    _pins, _source_digest, preflight, readiness_root, destination = (
        _execution_fixture(monkeypatch, tmp_path, provider)
    )
    result = CONTINUATION.execute_continuation(
        CONTINUATION.ExecutionConfig(
            preflight_dir=preflight.archive_dir,
            expected_preflight_fingerprint=preflight.preflight_fingerprint,
            readiness_record=readiness_root / "readiness_record.json",
            credential_preflight=readiness_root / "preflight.json",
            transmit=True,
        )
    )
    assert result.state == "sealed"
    injected = destination / member
    injected.parent.mkdir(parents=True, exist_ok=True)
    injected.write_bytes(b"{}")
    with pytest.raises(ValueError):
        CONT_ARTIFACTS.verify_sealed_derivative_archive(destination)


@pytest.mark.parametrize(
    "lifecycle",
    [
        "pre_dispatch_cleanup_reuse",
        "pre_dispatch_residue",
        "dispatch_started_consumed",
        "sealed_consumed",
    ],
)
def test_attempt_consumption_and_pre_dispatch_reuse_rules(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    lifecycle: str,
) -> None:
    provider = _EvaluatorProvider()
    _pins, _source_digest, preflight, readiness_root, destination = (
        _execution_fixture(monkeypatch, tmp_path, provider)
    )

    def config(root: Path) -> object:
        return CONTINUATION.ExecutionConfig(
            preflight_dir=preflight.archive_dir,
            expected_preflight_fingerprint=preflight.preflight_fingerprint,
            readiness_record=root / "readiness_record.json",
            credential_preflight=root / "preflight.json",
            transmit=True,
        )

    if lifecycle == "pre_dispatch_cleanup_reuse":
        original_static = CONT_ARTIFACTS.write_static_derivative_snapshot
        monkeypatch.setattr(
            CONT_ARTIFACTS,
            "write_static_derivative_snapshot",
            lambda **_kwargs: (_ for _ in ()).throw(
                OSError("pre-dispatch persistence failed")
            ),
        )
        with pytest.raises(OSError):
            CONTINUATION.execute_continuation(config(readiness_root))
        assert not preflight.staging_path.exists()
        assert not destination.exists()
        monkeypatch.setattr(
            CONT_ARTIFACTS,
            "write_static_derivative_snapshot",
            original_static,
        )
        fresh = tmp_path / "fresh-readiness"
        READINESS_PROBE.run_readiness(
            run_root=fresh,
            head_sha="f" * 40,
            environ={"OPENAI_API_KEY": "present"},
            authenticate=True,
            provider_factory=_readiness_provider,
            clock=_ReadinessClock(),
            models={"planner_evaluator": "gpt-5.4"},
        )
        result = CONTINUATION.execute_continuation(config(fresh))
        assert result.state == "sealed"
        assert provider.calls == 1
        return

    if lifecycle == "pre_dispatch_residue":
        def leave_residue(**kwargs):
            (kwargs["staging"] / "residue.bin").write_bytes(b"residue")
            raise OSError("pre-dispatch persistence failed")

        monkeypatch.setattr(
            CONT_ARTIFACTS,
            "write_static_derivative_snapshot",
            leave_residue,
        )
        monkeypatch.setattr(
            CONTINUATION,
            "_cleanup_unconsumed_staging",
            lambda _snapshot: (_ for _ in ()).throw(
                OSError("cleanup failed")
            ),
        )
        with pytest.raises(OSError, match="cleanup failed"):
            CONTINUATION.execute_continuation(config(readiness_root))
        assert preflight.staging_path.is_dir()
    elif lifecycle == "dispatch_started_consumed":
        monkeypatch.setattr(
            SUPPORT,
            "run_planner_evaluation",
            lambda **_kwargs: SUPPORT.PlannerEvaluationResult(
                "timeout", None, (), None, None, quiescent=False
            ),
        )
        result = CONTINUATION.execute_continuation(config(readiness_root))
        assert result.state == "post_dispatch_unsealed"
        assert (
            preflight.staging_path / "dispatch/dispatch-started.json"
        ).is_file()
    elif lifecycle == "sealed_consumed":
        result = CONTINUATION.execute_continuation(config(readiness_root))
        assert result.state == "sealed"
        assert destination.is_dir()
    else:  # pragma: no cover - parameter vocabulary is closed above.
        raise AssertionError(lifecycle)

    with pytest.raises((ValueError, RuntimeError, FileExistsError)):
        CONTINUATION._verify_pre_dispatch(config(readiness_root))


@pytest.mark.parametrize(
    "member",
    [
        "source/inputs/task_envelope.json",
        "instrument/corrected-evaluator-rubric.json",
        "instrument/allowed-delta-manifest.json",
        "evaluator/attempt/capture.json",
    ],
)
def test_reclosed_derivative_rejects_source_or_instrument_byte_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    member: str,
) -> None:
    provider = _EvaluatorProvider()
    _pins, _source_digest, preflight, readiness_root, destination = (
        _execution_fixture(monkeypatch, tmp_path, provider)
    )
    result = CONTINUATION.execute_continuation(
        CONTINUATION.ExecutionConfig(
            preflight_dir=preflight.archive_dir,
            expected_preflight_fingerprint=preflight.preflight_fingerprint,
            readiness_record=readiness_root / "readiness_record.json",
            credential_preflight=readiness_root / "preflight.json",
            transmit=True,
        )
    )
    assert result.state == "sealed"
    target = destination / member
    if member == "evaluator/attempt/capture.json":
        value = json.loads(target.read_bytes())
        value["outcome"] = "pending"
        target.write_bytes(_json_bytes(value))
    else:
        target.write_bytes(target.read_bytes() + b" ")
    changed_identity = _reclose_derivative_checksums(destination)
    with pytest.raises(
        ValueError,
        match="source|instrument|rubric|delta|evaluator|attempt|capture",
    ):
        CONT_ARTIFACTS.verify_sealed_derivative_archive(
            destination,
            expected_derivative_identity=changed_identity,
        )


@pytest.mark.parametrize(
    "claim",
    [
        "evaluator_result",
        "readiness_commit",
        "invocation_transmit",
        "dispatch_attempt",
    ],
)
def test_reclosed_derivative_rejects_claim_without_authority_provenance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    claim: str,
) -> None:
    provider = _EvaluatorProvider()
    _pins, _source_digest, preflight, readiness_root, destination = (
        _execution_fixture(monkeypatch, tmp_path, provider)
    )
    sealed = CONTINUATION.execute_continuation(
        CONTINUATION.ExecutionConfig(
            preflight_dir=preflight.archive_dir,
            expected_preflight_fingerprint=preflight.preflight_fingerprint,
            readiness_record=readiness_root / "readiness_record.json",
            credential_preflight=readiness_root / "preflight.json",
            transmit=True,
        )
    )
    assert sealed.state == "sealed"

    if claim == "evaluator_result":
        result_path = destination / "evaluator/result.json"
        result = json.loads(result_path.read_bytes())
        result["recommendation"] = "semantically_unfaithful"
        result_path.write_bytes(_json_bytes(result))
        decision_path = destination / "decision/classification.json"
        decision = json.loads(decision_path.read_bytes())
        decision["classification"] = "probe_planner_failure"
        decision["semantic_recommendation"] = "semantically_unfaithful"
        decision_path.write_bytes(_json_bytes(decision))
        _rewrite_derivative_subject_identity(destination)
    elif claim == "readiness_commit":
        readiness_path = destination / "readiness/readiness-record.json"
        readiness = json.loads(readiness_path.read_bytes())
        readiness["reviewed_commit_sha"] = "0" * 40
        readiness["record_fingerprint"] = (
            READINESS_CONTRACT.record_fingerprint(readiness)
        )
        readiness_path.write_bytes(_json_bytes(readiness))
        invocation_path = destination / "launch/invocation-binding.json"
        invocation = json.loads(invocation_path.read_bytes())
        invocation["readiness_record_fingerprint"] = readiness[
            "record_fingerprint"
        ]
        verification_path = destination / "readiness/verification.json"
        verification = json.loads(verification_path.read_bytes())
        verification["reviewed_commit_sha"] = "0" * 40
        verification["readiness_record_fingerprint"] = readiness[
            "record_fingerprint"
        ]
        verification_path.write_bytes(_json_bytes(verification))
        invocation["readiness_verification_fingerprint"] = (
            SUPPORT.fingerprint(verification)
        )
        invocation_path.write_bytes(_json_bytes(invocation))
    elif claim == "invocation_transmit":
        invocation_path = destination / "launch/invocation-binding.json"
        invocation = json.loads(invocation_path.read_bytes())
        invocation["transmit"] = False
        invocation_path.write_bytes(_json_bytes(invocation))
    elif claim == "dispatch_attempt":
        dispatch_path = destination / "dispatch/dispatch-started.json"
        dispatch = json.loads(dispatch_path.read_bytes())
        dispatch["attempt_id"] = "different-attempt"
        dispatch_path.write_bytes(_json_bytes(dispatch))
    else:  # pragma: no cover - parameter vocabulary is closed above.
        raise AssertionError(claim)

    changed_identity = _reclose_derivative_checksums(destination)
    with pytest.raises(ValueError, match="evaluator|readiness|invocation|dispatch"):
        CONT_ARTIFACTS.verify_sealed_derivative_archive(
            destination,
            expected_derivative_identity=changed_identity,
        )


def test_public_derivative_verifier_rejects_copied_destination(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    provider = _EvaluatorProvider()
    _pins, _source_digest, preflight, readiness_root, destination = (
        _execution_fixture(monkeypatch, tmp_path, provider)
    )
    sealed = CONTINUATION.execute_continuation(
        CONTINUATION.ExecutionConfig(
            preflight_dir=preflight.archive_dir,
            expected_preflight_fingerprint=preflight.preflight_fingerprint,
            readiness_record=readiness_root / "readiness_record.json",
            credential_preflight=readiness_root / "preflight.json",
            transmit=True,
        )
    )
    copied = preflight.derivative_root / "copied-derivative"
    shutil.copytree(destination, copied)
    with pytest.raises(ValueError, match="destination|location"):
        CONT_ARTIFACTS.verify_sealed_derivative_archive(
            copied,
            expected_derivative_identity=sealed.derivative_archive_identity,
        )
