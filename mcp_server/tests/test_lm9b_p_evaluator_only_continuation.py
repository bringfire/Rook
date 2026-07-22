from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

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
CONT_ARTIFACTS = _load_script("lm9b_p_evaluator_only_continuation_artifacts")
CONTINUATION = _load_script("lm9b_p_evaluator_only_continuation")


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


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
