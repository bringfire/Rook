from __future__ import annotations

import copy
import base64
import json
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
MCP_SRC = ROOT / "mcp_server" / "src"
for entry in (SCRIPTS, MCP_SRC):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))
HISTORICAL_SOURCE = Path(
    r"C:\Users\bring\rook-lm9b-p-attempts\2026-07-22-visibility-intervention"
)
DERIVATIVE_ARCHIVE = Path(
    r"C:\Users\bring\rook-lm9b-p-attempts"
    r"\2026-07-22-evaluator-only-continuation"
    r"\derivatives\visibility-evaluator-01"
)
DERIVATIVE_IDENTITY = (
    "sha256:48bcdcb36fb3ccee49fe358335f577ffabcb83b0f74e9f84d96951d6b3950b94"
)
CARRIER_QUALIFICATION = Path(
    r"C:\Users\bring\rook-lm9b-p-attempts"
    r"\2026-07-23-typed-fact-carrier-post-merge"
    r"\d6330a61a21d56abf16af6ba3b8f1678ede2c3ec"
)
CARRIER_QUALIFICATION_IDENTITY = (
    "sha256:ad12f0cec491b64f51982b7069acfa1301c1d577071cff9498cf7fba260446e1"
)
CARRIER_COMMIT = "d6330a61a21d56abf16af6ba3b8f1678ede2c3ec"
ISOLATED_SUCCESSOR_RECIPE = (
    SCRIPTS
    / "lm9b_p_governed_resolution_fixtures"
    / "radial_isolated_successor_recipe.json"
)
ISOLATION_POLICY = (
    SCRIPTS / "lm9b_p_governed_resolution_contracts" / "isolation_policy.json"
)
EVALUATION_RUBRIC = (
    SCRIPTS
    / "lm9b_p_governed_resolution_contracts"
    / "planner_revision_evaluation_rubric.json"
)


import lm9_semantic_typed_values as TYPED_VALUES
import lm9_typed_fact_carrier_artifacts as CARRIER
import lm9_typed_fact_carrier_qualification as QUALIFICATION
import lm9b_c_compiler_sufficiency_probe as COMPILER_PROBE
import lm9b_c_compiler_sufficiency_support as COMPILER_SUPPORT
import lm9b_p_evaluator_only_continuation_artifacts as CONT_ARTIFACTS
import lm9b_p_governed_resolution_artifacts as RESOLUTION_ARTIFACTS
import lm9b_p_governed_resolution_probe as RESOLUTION_PROBE
import lm9b_p_governed_resolution_support as RESOLUTION_SUPPORT
import lm9b_p_planner_recipe_transfer_artifacts as PLANNER_ARTIFACTS
import lm9b_p_planner_recipe_transfer_support as PLANNER_SUPPORT
import lm9b_p_readiness_contract as READINESS


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _planner_turn(*, recipe_bytes: bytes, call_id: str) -> object:
    recipe_text = recipe_bytes.decode("utf-8", errors="strict")
    arguments = json.dumps(
        {"recipe_json": recipe_text},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return PLANNER_SUPPORT.ProviderTurn(
        raw_request=b'{"adapter":"planner-request"}',
        raw_response=(f'{{"planner_turn":"{call_id}"}}').encode("utf-8"),
        assistant_message={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": "submit_planner_recipe",
                        "arguments": arguments,
                    },
                }
            ],
        },
        usage={"total_tokens": 50, "cost_usd": 0.001},
        provider_metadata={"model_identity": "gpt-5.4"},
    )


def _evaluator_turn() -> object:
    report = {
        "recommendation": "semantically_faithful",
        "evidence": [
            {
                "criterion_id": "brief_fidelity",
                "finding": (
                    "The current recipe faithfully represents the brief and "
                    "successor authority."
                ),
            }
        ],
    }
    arguments = json.dumps(
        {"evaluation_json": json.dumps(report, separators=(",", ":"))},
        separators=(",", ":"),
    )
    return PLANNER_SUPPORT.ProviderTurn(
        raw_request=b'{"adapter":"evaluator-request"}',
        raw_response=b'{"evaluator":"faithful"}',
        assistant_message={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "evaluator-1",
                    "type": "function",
                    "function": {
                        "name": "submit_planner_evaluation",
                        "arguments": arguments,
                    },
                }
            ],
        },
        usage={"total_tokens": 25, "cost_usd": 0.001},
        provider_metadata={"model_identity": "gpt-5.4"},
    )


class _FakeProvider:
    def __init__(self, responses: list[object], *, staging_path: Path) -> None:
        self.responses = list(responses)
        self.staging_path = staging_path
        self.requests: list[bytes] = []
        self.staging_existed_at_every_call: list[bool] = []

    def __call__(self, request: dict[str, object]) -> object:
        self.staging_existed_at_every_call.append(self.staging_path.is_dir())
        self.requests.append(_canonical_bytes(copy.deepcopy(request)))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _fresh_readiness(head_sha: str):
    manifest = READINESS.derive_routes(
        READINESS.role_routes_from_models(
            {"planner": "gpt-5.4", "planner_evaluator": "gpt-5.4"}
        ),
        lambda _model: "OPENAI_API_KEY",
    )
    assert len(manifest.routes) == 1
    route = manifest.routes[0]
    record = {
        "schema_id": READINESS.SCHEMA_ID,
        "reviewed_commit_sha": head_sha,
        "route_manifest_fingerprint": manifest.manifest_fingerprint,
        "canary_protocol_fingerprint": READINESS.canary_protocol_fingerprint(),
        "max_age_seconds": READINESS.FROZEN_MAX_AGE_S,
        "completed_at": "2026-07-25T20:00:05Z",
        "routes": [
            {
                "route_fingerprint": route.route_fingerprint,
                "member_roles": list(route.member_roles),
                "observed_at": "2026-07-25T20:00:04Z",
                "request_fingerprint": READINESS.request_fingerprint(route),
                "outcome": {
                    "kind": "model_response",
                    "assistant_present": True,
                    "tool_calls": [
                        {"name": "ack", "arguments": '{"ok": true}'}
                    ],
                    "raw_response_fingerprint": "sha256:fake-readiness",
                },
            }
        ],
    }
    record["record_fingerprint"] = READINESS.record_fingerprint(record)
    return record, manifest, route


def _invocation(preflight, readiness_record):
    return RESOLUTION_ARTIFACTS.build_resolution_invocation_binding(
        supplied_preflight_fingerprint=preflight.preflight_fingerprint,
        transmit=True,
        reviewed_commit_sha=preflight.record["reviewed_commit_sha"],
        readiness_identity=readiness_record["record_fingerprint"],
        attempt_id=preflight.attempt.attempt_id,
        attempt_fingerprint=preflight.attempt.attempt_fingerprint,
    )


def _task2_preflight(tmp_path: Path):
    sources = RESOLUTION_ARTIFACTS.load_verified_resolution_sources(
        historical_source_dir=HISTORICAL_SOURCE,
        derivative_archive=DERIVATIVE_ARCHIVE,
        derivative_identity=DERIVATIVE_IDENTITY,
        carrier_qualification_archive=CARRIER_QUALIFICATION,
        carrier_qualification_identity=CARRIER_QUALIFICATION_IDENTITY,
        repo_root=ROOT,
        successor_envelope_path=CARRIER.RADIAL_FIXTURE_PATH,
    )
    instrument = RESOLUTION_ARTIFACTS.assemble_resolution_instrument(
        sources=sources,
        isolation_policy_path=ISOLATION_POLICY,
        evaluation_rubric_path=EVALUATION_RUBRIC,
    )
    root = tmp_path / "resolution-root"
    root.mkdir()
    attempt = RESOLUTION_ARTIFACTS.bind_resolution_attempt(
        instrument=instrument,
        attempt_id="task2-precontact",
        resolution_root=root,
        destination=root / "task2-precontact",
    )
    return RESOLUTION_ARTIFACTS.write_resolution_preflight(
        destination=tmp_path / "preflight",
        instrument=instrument,
        attempt_binding=attempt,
    )


def _boom(*_args: object, **_kwargs: object) -> object:
    raise AssertionError("compiler entry was reached")


def _verified_resolution_inputs():
    sources = RESOLUTION_ARTIFACTS.load_verified_resolution_sources(
        historical_source_dir=HISTORICAL_SOURCE,
        derivative_archive=DERIVATIVE_ARCHIVE,
        derivative_identity=DERIVATIVE_IDENTITY,
        carrier_qualification_archive=CARRIER_QUALIFICATION,
        carrier_qualification_identity=CARRIER_QUALIFICATION_IDENTITY,
        repo_root=ROOT,
        successor_envelope_path=CARRIER.RADIAL_FIXTURE_PATH,
    )
    inputs = RESOLUTION_SUPPORT.assemble_verified_resolution_inputs(
        sources=sources,
        isolation_policy_bytes=ISOLATION_POLICY.read_bytes(),
        evaluation_rubric_bytes=EVALUATION_RUBRIC.read_bytes(),
    )
    return (
        sources.reviewed_commit_sha,
        sources.historical_source,
        sources.parent_derivative,
        sources.carrier_qualification,
        inputs,
    )


def _reclose_recipe(value: dict[str, object], inputs: object) -> bytes:
    projection = {
        key: item for key, item in value.items() if key != "recipe_fingerprint"
    }
    normalized = PLANNER_SUPPORT.normalize_recipe(
        copy.deepcopy(projection), inputs.normalization_profile
    )
    value["recipe_fingerprint"] = PLANNER_SUPPORT.fingerprint(normalized)
    return _canonical_bytes(value)


def _reclose_task1_checkpoint(archive: Path) -> str:
    member_paths = sorted(
        path.name for path in archive.iterdir() if path.name != "checksums.json"
    )
    raw_members = {name: (archive / name).read_bytes() for name in member_paths}
    identity_rows = [
        {
            "path": name,
            "raw_sha256": PLANNER_SUPPORT.sha256_prefixed(raw),
        }
        for name, raw in sorted(raw_members.items())
        if name != "record.json"
    ]
    identity = PLANNER_SUPPORT.fingerprint(
        {
            "schema": RESOLUTION_ARTIFACTS.CHECKPOINT_SCHEMA_ID,
            "canonical_destination": str(archive.resolve()),
            "members": identity_rows,
        }
    )
    record = json.loads(raw_members["record.json"])
    record["canonical_destination"] = str(archive.resolve())
    record["checkpoint_identity"] = identity
    (archive / "record.json").write_bytes(_canonical_bytes(record))
    raw_members["record.json"] = (archive / "record.json").read_bytes()
    checksums = {
        "schema": "rook.lm9b_p.governed_resolution_checkpoint_checksums:v1",
        "members": [
            {
                "path": name,
                "raw_sha256": PLANNER_SUPPORT.sha256_prefixed(raw),
            }
            for name, raw in sorted(raw_members.items())
        ],
    }
    (archive / "checksums.json").write_bytes(_canonical_bytes(checksums))
    return identity


def _reclose_preflight(preflight, mutate) -> object:
    record_path = preflight.archive_dir / "record.json"
    record = json.loads(record_path.read_bytes())
    mutate(record)
    record["preflight_fingerprint"] = PLANNER_SUPPORT.fingerprint_without(
        record, "preflight_fingerprint"
    )
    record_path.write_bytes(_canonical_bytes(record))
    raw_members = {
        "record.json": record_path.read_bytes(),
        "initial-request.json": (
            preflight.archive_dir / "initial-request.json"
        ).read_bytes(),
    }
    checksums = {
        "schema": "rook.lm9b_p.governed_resolution_preflight_checksums:v1",
        "members": [
            {
                "path": name,
                "raw_sha256": PLANNER_SUPPORT.sha256_prefixed(raw),
            }
            for name, raw in sorted(raw_members.items())
        ],
    }
    (preflight.archive_dir / "checksums.json").write_bytes(
        _canonical_bytes(checksums)
    )
    return replace(
        preflight, preflight_fingerprint=record["preflight_fingerprint"]
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "retain_removable_descriptor",
        "remove_retained_descriptor",
        "add_descriptor",
        "reorder_parent_descriptors",
        "mutate_retained_descriptor",
    ),
)
def test_task1_descriptor_reachability_rejects_adversarial_delta(
    mutation: str,
) -> None:
    _head, _source, _derivative, _compatibility, inputs = (
        _verified_resolution_inputs()
    )
    assert list(
        inputs.policy_instance.value["descriptor_removal_eligible_ids"]
    ) == ["planning_policy"]
    candidate = json.loads(ISOLATED_SUCCESSOR_RECIPE.read_bytes())
    parent_descriptors = copy.deepcopy(inputs.parent_recipe["authority_artifacts"])
    if mutation == "retain_removable_descriptor":
        candidate["authority_artifacts"] = parent_descriptors
    elif mutation == "remove_retained_descriptor":
        candidate["authority_artifacts"] = []
    elif mutation == "add_descriptor":
        candidate["authority_artifacts"].append(
            {
                "artifact_id": "extra_authority",
                "artifact_kind": "environment_snapshot",
                "schema": "rook.environment_snapshot:v1",
                "fingerprint": "sha256:" + "0" * 64,
            }
        )
    elif mutation == "reorder_parent_descriptors":
        candidate["authority_artifacts"] = list(reversed(parent_descriptors))
    elif mutation == "mutate_retained_descriptor":
        candidate["authority_artifacts"][0]["fingerprint"] = "sha256:" + "0" * 64
    raw = _reclose_recipe(candidate, inputs)
    result = RESOLUTION_SUPPORT.evaluate_resolution_isolation(
        inputs=inputs,
        candidate_recipe_bytes=raw,
    )
    assert result.status == "isolation_rejected"
    assert "authority_descriptor_reachability" in {
        row["equation_id"] for row in result.bounded_differences
    }


def test_task1_descriptor_reachability_accepts_exact_derived_removal() -> None:
    _head, _source, _derivative, _compatibility, inputs = (
        _verified_resolution_inputs()
    )
    result = RESOLUTION_SUPPORT.evaluate_resolution_isolation(
        inputs=inputs,
        candidate_recipe_bytes=ISOLATED_SUCCESSOR_RECIPE.read_bytes(),
    )
    assert result.status == "isolated"
    assert [row["equation_id"] for row in result.equations] == [
        "source_descriptor",
        "resolved_unresolved_rows",
        "authority_descriptor_reachability",
        "goal_projection",
        "clause_ownership",
        "authority_reference_additions",
        "affected_clause_residual",
        "recipe_fingerprint",
        "residual_equality",
    ]


def test_task1_revision_renderer_keeps_descriptor_reachability_generic() -> None:
    _head, _source, _derivative, _compatibility, inputs = (
        _verified_resolution_inputs()
    )
    rendered = RESOLUTION_SUPPORT.render_planner_revision_request(inputs)
    visible_policy = rendered.payload["isolation_policy"]
    assert "descriptor_removal_eligible_ids" not in visible_policy
    assert any(
        "descriptors whose complete parent references" in obligation
        for obligation in visible_policy["model_obligations"]
    )


def test_task1_assembler_rejects_forged_resolution_source_carrier() -> None:
    sources = RESOLUTION_ARTIFACTS.load_verified_resolution_sources(
        historical_source_dir=HISTORICAL_SOURCE,
        derivative_archive=DERIVATIVE_ARCHIVE,
        derivative_identity=DERIVATIVE_IDENTITY,
        carrier_qualification_archive=CARRIER_QUALIFICATION,
        carrier_qualification_identity=CARRIER_QUALIFICATION_IDENTITY,
        repo_root=ROOT,
        successor_envelope_path=CARRIER.RADIAL_FIXTURE_PATH,
    )
    duck_typed = SimpleNamespace(
        exact_successor_bytes=sources.exact_successor_bytes,
        exact_contract_bytes=sources.exact_contract_bytes,
        reviewed_commit_sha=sources.reviewed_commit_sha,
    )
    for forged in (replace(sources), duck_typed):
        with pytest.raises((TypeError, ValueError), match="closure-issued"):
            RESOLUTION_SUPPORT.assemble_verified_resolution_inputs(
                sources=forged,
                isolation_policy_bytes=ISOLATION_POLICY.read_bytes(),
                evaluation_rubric_bytes=EVALUATION_RUBRIC.read_bytes(),
            )


def test_task1_two_turn_vertical_witness_publicly_verifies(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(PLANNER_ARTIFACTS, "build_lm9bc_handoff", _boom)
    monkeypatch.setattr(COMPILER_SUPPORT, "run_compiler_session", _boom)
    monkeypatch.setattr(COMPILER_PROBE, "run_probe", _boom)

    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    sources = RESOLUTION_ARTIFACTS.load_verified_resolution_sources(
        historical_source_dir=HISTORICAL_SOURCE,
        derivative_archive=DERIVATIVE_ARCHIVE,
        derivative_identity=DERIVATIVE_IDENTITY,
        carrier_qualification_archive=CARRIER_QUALIFICATION,
        carrier_qualification_identity=CARRIER_QUALIFICATION_IDENTITY,
        repo_root=ROOT,
        successor_envelope_path=CARRIER.RADIAL_FIXTURE_PATH,
    )
    compatibility = sources.carrier_qualification
    assert compatibility.historical_commit_sha == CARRIER_COMMIT
    assert compatibility.consuming_commit_sha == head_sha

    instrument = RESOLUTION_ARTIFACTS.assemble_resolution_instrument(
        sources=sources,
        isolation_policy_path=ISOLATION_POLICY,
        evaluation_rubric_path=EVALUATION_RUBRIC,
    )
    resolution_root = tmp_path / "resolution-root"
    resolution_root.mkdir()
    attempt = RESOLUTION_ARTIFACTS.bind_resolution_attempt(
        instrument=instrument,
        attempt_id="task1-two-turn",
        resolution_root=resolution_root,
        destination=resolution_root / "task1-two-turn",
    )
    written_preflight = RESOLUTION_ARTIFACTS.write_resolution_preflight(
        destination=tmp_path / "preflight",
        instrument=instrument,
        attempt_binding=attempt,
    )
    preflight = RESOLUTION_ARTIFACTS.verify_resolution_preflight(
        written_preflight.archive_dir,
        expected_fingerprint=written_preflight.preflight_fingerprint,
    )
    ready_contract = preflight.record["instrument_contracts"]["ready_proof"]
    assert ready_contract["contract_id"] == (
        "lm9b_p.governed_resolution_ready_proof:v1"
    )
    assert not {
        "proof_instance_identity",
        "checkpoint_identity",
        "eligible_recipe_identity",
    } & set(ready_contract)

    readiness_record, readiness_manifest, route = _fresh_readiness(head_sha)
    monkeypatch.setattr(
        RESOLUTION_ARTIFACTS, "require_clean_reviewed_checkout", lambda *_a: None
    )
    planner = _FakeProvider(
        [
            _planner_turn(recipe_bytes=b"{}", call_id="planner-1"),
            _planner_turn(
                recipe_bytes=ISOLATED_SUCCESSOR_RECIPE.read_bytes(),
                call_id="planner-2",
            ),
        ],
        staging_path=attempt.staging_path,
    )
    evaluator = _FakeProvider(
        [_evaluator_turn()],
        staging_path=attempt.staging_path,
    )
    result = RESOLUTION_PROBE.run_resolution_attempt(
        preflight=preflight,
        invocation_binding=_invocation(preflight, readiness_record),
        readiness_record=readiness_record,
        readiness_manifest=readiness_manifest,
        head_sha=head_sha,
        now_iso="2026-07-25T20:00:06Z",
        credential_present={route.route_fingerprint: True},
        planner_provider=planner,
        evaluator_provider=evaluator,
    )

    assert result.classification == "probe_candidate_ready"
    assert result.state == "sealed"
    assert len(planner.requests) == 2
    assert len(evaluator.requests) == 1
    assert planner.staging_existed_at_every_call == [True, True]
    assert evaluator.staging_existed_at_every_call == [True]
    assert json.loads(planner.requests[1])["messages"][-1]["role"] in {
        "tool",
        "user",
    }
    assert result.isolation_result is not None
    assert result.isolation_result.status == "isolated"
    assert result.sealed_checkpoint is not None
    planner_evidence = json.loads(
        (result.sealed_checkpoint.archive_dir / "planner-session.json").read_bytes()
    )
    accepted_message = planner_evidence["calls"][1]["assistant_message"]
    _arguments, emitted_recipe, _rejection, _call_id = (
        PLANNER_SUPPORT.derive_planner_submission_from_message(accepted_message)
    )
    assert emitted_recipe == ISOLATED_SUCCESSOR_RECIPE.read_bytes()
    evaluator_evidence = json.loads(
        (result.sealed_checkpoint.archive_dir / "evaluator.json").read_bytes()
    )
    dispatched = base64.b64decode(evaluator_evidence["dispatched_request_b64"])
    provider_claimed = base64.b64decode(
        evaluator_evidence["provider_claimed_raw_request_b64"]
    )
    assert dispatched != provider_claimed
    rendered_evaluator = (
        RESOLUTION_SUPPORT.render_planner_revision_evaluation_request(
            preflight.instrument.inputs,
            candidate_recipe_bytes=ISOLATED_SUCCESSOR_RECIPE.read_bytes(),
        )
    )
    assert dispatched == PLANNER_SUPPORT.build_planner_evaluator_provider_call_request(
        system_prompt=PLANNER_SUPPORT.PLANNER_EVALUATOR_SYSTEM_PROMPT,
        user_prompt=rendered_evaluator.raw_bytes.decode("utf-8"),
    )
    verified = RESOLUTION_ARTIFACTS.verify_sealed_resolution_checkpoint(
        result.sealed_checkpoint.archive_dir,
        expected_identity=result.sealed_checkpoint.checkpoint_identity,
    )
    assert verified.classification == "probe_candidate_ready"
    assert verified.exact_recipe_bytes == ISOLATED_SUCCESSOR_RECIPE.read_bytes()

    planner_tamper = tmp_path / "planner-provenance-tamper"
    shutil.copytree(result.sealed_checkpoint.archive_dir, planner_tamper)
    changed_candidate = json.loads(
        (planner_tamper / "candidate-recipe.json").read_bytes()
    )
    changed_candidate["goal"]["statement"] += " Unauthorized change."
    changed_candidate_raw = _reclose_recipe(
        changed_candidate, preflight.instrument.inputs
    )
    (planner_tamper / "candidate-recipe.json").write_bytes(changed_candidate_raw)
    changed_session = json.loads(
        (planner_tamper / "planner-session.json").read_bytes()
    )
    changed_session["final_recipe_raw_sha256"] = (
        PLANNER_SUPPORT.sha256_prefixed(changed_candidate_raw)
    )
    (planner_tamper / "planner-session.json").write_bytes(
        _canonical_bytes(changed_session)
    )
    planner_tamper_identity = _reclose_task1_checkpoint(planner_tamper)
    with pytest.raises(ValueError, match="accepted Planner tool bytes differ"):
        RESOLUTION_ARTIFACTS.verify_sealed_resolution_checkpoint(
            planner_tamper,
            expected_identity=planner_tamper_identity,
        )

    evaluator_tamper = tmp_path / "evaluator-request-tamper"
    shutil.copytree(result.sealed_checkpoint.archive_dir, evaluator_tamper)
    changed_evaluator = json.loads(
        (evaluator_tamper / "evaluator.json").read_bytes()
    )
    changed_evaluator["dispatched_request_b64"] = base64.b64encode(
        b'{"messages":[]}'
    ).decode("ascii")
    (evaluator_tamper / "evaluator.json").write_bytes(
        _canonical_bytes(changed_evaluator)
    )
    evaluator_tamper_identity = _reclose_task1_checkpoint(evaluator_tamper)
    with pytest.raises(ValueError, match="evaluator dispatch differs"):
        RESOLUTION_ARTIFACTS.verify_sealed_resolution_checkpoint(
            evaluator_tamper,
            expected_identity=evaluator_tamper_identity,
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "stale",
        "missing_route",
        "extra_role",
        "wrong_model",
        "wrong_route",
        "wrong_canary_protocol",
        "wrong_manifest",
        "wrong_commit",
        "missing_credential",
        "invocation_fingerprint",
        "dirty_checkout",
    ),
)
def test_task2_precontact_refusal_has_zero_dispatch(
    mutation: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    preflight = _task2_preflight(tmp_path)
    head_sha = preflight.record["reviewed_commit_sha"]
    record, manifest, route = _fresh_readiness(head_sha)
    now_iso = "2026-07-25T20:00:06Z"
    credential_present = {route.route_fingerprint: True}
    if mutation == "stale":
        now_iso = "2026-07-25T21:00:06Z"
    elif mutation == "missing_route":
        record["routes"] = []
    elif mutation == "extra_role":
        record["routes"][0]["member_roles"].append("compiler")
    elif mutation == "wrong_model":
        changed_route = replace(route, model="gpt-5.3")
        manifest = READINESS.RouteManifest(
            routes=(changed_route,),
            manifest_fingerprint=READINESS.canonical_fingerprint(
                [changed_route.route_fingerprint]
            ),
        )
    elif mutation == "wrong_route":
        record["routes"][0]["route_fingerprint"] = "sha256:" + "9" * 64
    elif mutation == "wrong_canary_protocol":
        record["canary_protocol_fingerprint"] = "sha256:" + "8" * 64
    elif mutation == "wrong_manifest":
        record["route_manifest_fingerprint"] = "sha256:" + "7" * 64
    elif mutation == "wrong_commit":
        record["reviewed_commit_sha"] = "0" * 40
    elif mutation == "missing_credential":
        credential_present[route.route_fingerprint] = False
    if mutation in {
        "missing_route",
        "extra_role",
        "wrong_route",
        "wrong_canary_protocol",
        "wrong_manifest",
        "wrong_commit",
    }:
        record["record_fingerprint"] = READINESS.record_fingerprint(record)
    invocation = _invocation(preflight, record)
    if mutation == "invocation_fingerprint":
        invocation = dict(invocation)
        invocation["attempt_id"] = "other-attempt"
    if mutation == "dirty_checkout":
        monkeypatch.setattr(
            RESOLUTION_ARTIFACTS,
            "require_clean_reviewed_checkout",
            lambda *_a: (_ for _ in ()).throw(ValueError("reviewed checkout is dirty")),
            raising=False,
        )
    else:
        monkeypatch.setattr(
            RESOLUTION_ARTIFACTS,
            "require_clean_reviewed_checkout",
            lambda *_a: None,
            raising=False,
        )
    calls = {"planner": 0, "planner_evaluator": 0}

    def planner_provider(_request: object) -> object:
        calls["planner"] += 1
        raise AssertionError("Planner was dispatched")

    def evaluator_provider(_request: object) -> object:
        calls["planner_evaluator"] += 1
        raise AssertionError("evaluator was dispatched")

    expected_error = (
        "invocation" if mutation == "invocation_fingerprint" else
        "dirty" if mutation == "dirty_checkout" else
        "readiness"
    )
    with pytest.raises((TypeError, ValueError), match=expected_error):
        RESOLUTION_PROBE.run_resolution_attempt(
            preflight=preflight,
            invocation_binding=invocation,
            readiness_record=record,
            readiness_manifest=manifest,
            head_sha=head_sha,
            now_iso=now_iso,
            credential_present=credential_present,
            planner_provider=planner_provider,
            evaluator_provider=evaluator_provider,
        )
    assert calls == {"planner": 0, "planner_evaluator": 0}
    assert not preflight.attempt.staging_path.exists()
    assert not preflight.attempt.destination.exists()
    assert not list(preflight.attempt.resolution_root.glob("**/dispatch_started*"))


@pytest.mark.parametrize(
    "mutation",
    (
        "execution_wrong_commit",
        "altered_preflight",
        "altered_qualification_identity",
        "altered_contract_manifest",
        "destination_exists",
        "staging_exists",
    ),
)
def test_task2_precontact_identity_or_destination_refusal_has_zero_dispatch(
    mutation: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    preflight = _task2_preflight(tmp_path)
    head_sha = preflight.record["reviewed_commit_sha"]
    record, manifest, route = _fresh_readiness(head_sha)
    if mutation == "altered_preflight":
        preflight = _reclose_preflight(
            preflight,
            lambda value: value.__setitem__(
                "carrier_compatibility_fingerprint", "sha256:" + "1" * 64
            ),
        )
    elif mutation == "altered_qualification_identity":
        preflight = _reclose_preflight(
            preflight,
            lambda value: value.__setitem__(
                "historical_qualification_identity", "sha256:" + "2" * 64
            ),
        )
    elif mutation == "altered_contract_manifest":
        def mutate_contract(value: dict[str, object]) -> None:
            value["instrument_contracts"]["decision"][
                "classifier_contract_id"
            ] = "lm9b_p.evaluated_recipe_classification:altered"
            value["instrument_fingerprint"] = PLANNER_SUPPORT.fingerprint(
                value["instrument_contracts"]
            )

        preflight = _reclose_preflight(preflight, mutate_contract)
    elif mutation == "destination_exists":
        preflight.attempt.destination.mkdir()
    elif mutation == "staging_exists":
        preflight.attempt.staging_path.mkdir()
    invocation = _invocation(preflight, record)
    monkeypatch.setattr(
        RESOLUTION_ARTIFACTS,
        "require_clean_reviewed_checkout",
        lambda *_a: None,
    )
    calls = {"planner": 0, "planner_evaluator": 0}

    def planner_provider(_request: object) -> object:
        calls["planner"] += 1
        raise AssertionError("Planner was dispatched")

    def evaluator_provider(_request: object) -> object:
        calls["planner_evaluator"] += 1
        raise AssertionError("evaluator was dispatched")

    with pytest.raises((TypeError, ValueError, FileExistsError)):
        RESOLUTION_PROBE.run_resolution_attempt(
            preflight=preflight,
            invocation_binding=invocation,
            readiness_record=record,
            readiness_manifest=manifest,
            head_sha=("0" * 40 if mutation == "execution_wrong_commit" else head_sha),
            now_iso="2026-07-25T20:00:06Z",
            credential_present={route.route_fingerprint: True},
            planner_provider=planner_provider,
            evaluator_provider=evaluator_provider,
        )
    assert calls == {"planner": 0, "planner_evaluator": 0}
    assert not list(preflight.attempt.resolution_root.glob("**/dispatch_started*"))
