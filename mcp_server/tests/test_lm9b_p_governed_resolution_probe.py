from __future__ import annotations

import copy
import base64
import json
import os
import shutil
import subprocess
import sys
import threading
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


def _expected_litellm_request_bytes(
    request: dict[str, object],
    *,
    model: str = "gpt-5.4",
    temperature: float = 0.0,
) -> bytes:
    value = {
        "model": model,
        "messages": request["messages"],
        "tools": request["tools"],
        "tool_choice": request["tool_choice"],
        "parallel_tool_calls": False,
        "max_tokens": request["max_completion_tokens"],
        "temperature": temperature,
        "timeout": request["provider_timeout_s"],
        "stream": False,
    }
    return _canonical_bytes(value) + b"\n"


def _planner_turn(
    *,
    recipe_bytes: bytes,
    call_id: str,
    total_tokens: int = 50,
    cost_usd: float = 0.001,
) -> object:
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
        usage={"total_tokens": total_tokens, "cost_usd": cost_usd},
        provider_metadata={
            "model_identity": "gpt-5.4",
            "profile_identity": "litellm.completion.tool_calling.no_parallel:v1",
        },
    )


def _evaluator_turn(
    recommendation: str = "semantically_faithful",
) -> object:
    report = {
        "recommendation": recommendation,
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
        provider_metadata={
            "model_identity": "gpt-5.4",
            "profile_identity": "litellm.completion.tool_calling.no_parallel:v1",
        },
    )


class _FakeProvider:
    def __init__(self, responses: list[object], *, staging_path: Path) -> None:
        self.responses = list(responses)
        self.staging_path = staging_path
        self.requests: list[bytes] = []
        self.staging_existed_at_every_call: list[bool] = []
        self.model = "gpt-5.4"
        self.temperature = 0.0
        self.profile_identity = "litellm.completion.tool_calling.no_parallel:v1"
        self.identity = {
            "adapter_path": "litellm.completion",
            "model": self.model,
            "profile_identity": self.profile_identity,
            "temperature": self.temperature,
        }

    def __call__(self, request: dict[str, object]) -> object:
        self.staging_existed_at_every_call.append(self.staging_path.is_dir())
        self.requests.append(_canonical_bytes(copy.deepcopy(request)))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        if callable(response):
            return response(request)
        return response


def _provider_failure_action(
    *,
    failure_type: str = "ProviderAPIError",
    raw_request: bytes | None = None,
    raw_error: bytes = b'{"provider":"failed"}\n',
) -> object:
    def fail(request: dict[str, object]) -> object:
        captured_request = (
            _expected_litellm_request_bytes(request)
            if raw_request is None
            else raw_request
        )
        raise PLANNER_SUPPORT.ProviderCallFailure(
            failure_type=failure_type,
            message="provider failed",
            raw_request=captured_request,
            raw_error=raw_error,
        )

    return fail


def _install_role_providers(
    monkeypatch: pytest.MonkeyPatch,
    *,
    planner: object,
    evaluator: object,
) -> None:
    delegates = {"planner": planner, "planner_evaluator": evaluator}

    class BoundFakeAdapter:
        def __init__(self, delegate: object) -> None:
            self.delegate = delegate
            self.model = "gpt-5.4"
            self.temperature = 0.0
            self.profile_identity = (
                "litellm.completion.tool_calling.no_parallel:v1"
            )
            self.identity = {
                "adapter_path": "litellm.completion",
                "model": self.model,
                "profile_identity": self.profile_identity,
                "temperature": self.temperature,
            }

        def __call__(self, request: dict[str, object]) -> object:
            raw_request = COMPILER_PROBE.build_litellm_completion_request_bytes(
                model=self.model,
                temperature=self.temperature,
                provider_request=request,
            )
            response = self.delegate(request)
            if type(response) is not PLANNER_SUPPORT.ProviderTurn:
                return response
            metadata = dict(response.provider_metadata)
            metadata.update(
                {
                    "model_identity": self.model,
                    "profile_identity": self.profile_identity,
                    "requested_model": self.model,
                    "requested_profile": self.profile_identity,
                }
            )
            return replace(
                response,
                raw_request=raw_request,
                provider_metadata=metadata,
            )

    def construct(*, role: str, model: str, temperature: float) -> object:
        assert model == "gpt-5.4"
        assert temperature == 0.0
        return BoundFakeAdapter(delegates[role])

    monkeypatch.setattr(
        RESOLUTION_PROBE,
        "_construct_resolution_role_provider",
        construct,
    )


def _run_resolution_attempt(
    *,
    monkeypatch: pytest.MonkeyPatch,
    planner_provider: object,
    evaluator_provider: object,
    **kwargs: object,
) -> object:
    _install_role_providers(
        monkeypatch,
        planner=planner_provider,
        evaluator=evaluator_provider,
    )
    return RESOLUTION_PROBE.run_resolution_attempt(**kwargs)


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
        "goal_unresolved_projection",
        "clause_ownership",
        "authority_reference_additions",
        "affected_clause_residual",
        "recipe_fingerprint",
        "global_residual_equality",
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
    result = _run_resolution_attempt(
        monkeypatch=monkeypatch,
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

    for member, field, changed, expected_error in (
        (
            "planner-session.json",
            "schema",
            "rook.lm9b_p.governed_resolution_planner_session:altered",
            "Planner ledger",
        ),
        (
            "evaluator.json",
            "schema",
            "rook.lm9b_p.governed_resolution_evaluator:altered",
            "evaluator evidence",
        ),
        (
            "evaluator.json",
            "termination",
            "evaluation_inconclusive",
            "evaluator evidence",
        ),
    ):
        claim_tamper = tmp_path / f"claim-tamper-{field}-{member.split('.')[0]}"
        shutil.copytree(result.sealed_checkpoint.archive_dir, claim_tamper)
        claim = json.loads((claim_tamper / member).read_bytes())
        claim[field] = changed
        (claim_tamper / member).write_bytes(_canonical_bytes(claim))
        claim_tamper_identity = _reclose_task1_checkpoint(claim_tamper)
        with pytest.raises(ValueError, match=expected_error):
            RESOLUTION_ARTIFACTS.verify_sealed_resolution_checkpoint(
                claim_tamper,
                expected_identity=claim_tamper_identity,
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
        "role_membership_substitution",
        "route_identity_substitution",
        "route_identity_reclosed_substitution",
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
    elif mutation == "role_membership_substitution":
        changed_route = replace(route, member_roles=("compiler",))
        manifest = READINESS.RouteManifest(
            routes=(changed_route,),
            manifest_fingerprint=manifest.manifest_fingerprint,
        )
        record["routes"][0]["member_roles"] = ["compiler"]
    elif mutation == "route_identity_substitution":
        changed_route = replace(
            route,
            adapter_path="forged.adapter",
            provider="forged-provider",
            model="forged-model",
            credential_source=("FORGED_CREDENTIAL",),
        )
        manifest = READINESS.RouteManifest(
            routes=(changed_route,),
            manifest_fingerprint=manifest.manifest_fingerprint,
        )
        record["routes"][0]["request_fingerprint"] = (
            READINESS.request_fingerprint(changed_route)
        )
    elif mutation == "route_identity_reclosed_substitution":
        changed_identity = {
            "adapter_path": "forged.adapter",
            "provider": "forged-provider",
            "model": "forged-model",
            "credential_source": ["FORGED_CREDENTIAL"],
        }
        changed_route_fingerprint = READINESS.canonical_fingerprint(
            changed_identity
        )
        changed_route = replace(
            route,
            route_fingerprint=changed_route_fingerprint,
            adapter_path=changed_identity["adapter_path"],
            provider=changed_identity["provider"],
            model=changed_identity["model"],
            credential_source=tuple(changed_identity["credential_source"]),
        )
        manifest = READINESS.RouteManifest(
            routes=(changed_route,),
            manifest_fingerprint=READINESS.canonical_fingerprint(
                [changed_route_fingerprint]
            ),
        )
        record["route_manifest_fingerprint"] = manifest.manifest_fingerprint
        record["routes"][0]["route_fingerprint"] = changed_route_fingerprint
        record["routes"][0]["request_fingerprint"] = (
            READINESS.request_fingerprint(changed_route)
        )
        credential_present = {changed_route_fingerprint: True}
    if mutation in {
        "missing_route",
        "extra_role",
        "wrong_route",
        "wrong_canary_protocol",
        "wrong_manifest",
        "wrong_commit",
        "role_membership_substitution",
        "route_identity_substitution",
        "route_identity_reclosed_substitution",
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
        _run_resolution_attempt(
            monkeypatch=monkeypatch,
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


def test_task2_run_refuses_dangling_destination_alias_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    preflight = _task2_preflight(tmp_path)
    head_sha = preflight.record["reviewed_commit_sha"]
    record, manifest, route = _fresh_readiness(head_sha)
    invocation = _invocation(preflight, record)

    def create_dangling_alias(*_args: object) -> None:
        preflight.attempt.destination.symlink_to(
            preflight.attempt.staging_path,
            target_is_directory=True,
        )

    monkeypatch.setattr(
        RESOLUTION_ARTIFACTS,
        "require_clean_reviewed_checkout",
        create_dangling_alias,
    )
    calls = {"planner": 0, "planner_evaluator": 0}

    def planner_provider(_request: object) -> object:
        calls["planner"] += 1
        raise AssertionError("Planner was dispatched")

    def evaluator_provider(_request: object) -> object:
        calls["planner_evaluator"] += 1
        raise AssertionError("evaluator was dispatched")

    with pytest.raises(ValueError, match="alias|reparse|destination"):
        _run_resolution_attempt(
            monkeypatch=monkeypatch,
            preflight=preflight,
            invocation_binding=invocation,
            readiness_record=record,
            readiness_manifest=manifest,
            head_sha=head_sha,
            now_iso="2026-07-25T20:00:06Z",
            credential_present={route.route_fingerprint: True},
            planner_provider=planner_provider,
            evaluator_provider=evaluator_provider,
        )
    assert calls == {"planner": 0, "planner_evaluator": 0}
    assert os.path.lexists(preflight.attempt.destination)
    assert preflight.attempt.staging_path.exists() is False
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
        _run_resolution_attempt(
            monkeypatch=monkeypatch,
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


OUTCOME_CASES = (
    ("max_turns", "probe_mechanically_rejected", 0),
    ("token_stop", "probe_mechanically_rejected", 0),
    ("cost_stop", "probe_mechanically_rejected", 0),
    ("planner_provider_failure", "probe_inconclusive", 0),
    ("planner_terminal_timeout", "probe_inconclusive", 0),
    ("isolation_rejected", "probe_resolution_isolation_failure", 0),
    ("semantic_unfaithful", "probe_planner_failure", 1),
    ("semantic_faithful", "probe_candidate_ready", 1),
    ("evaluation_inconclusive", "probe_inconclusive", 1),
    ("evaluator_malformed", "probe_inconclusive", 1),
    ("evaluator_provider_failure", "probe_inconclusive", 1),
    ("evaluator_terminal_timeout", "probe_inconclusive", 1),
)


def _task4_provider_scripts(case: str, preflight: object) -> tuple[list[object], list[object]]:
    invalid = lambda index, **usage: _planner_turn(  # noqa: E731
        recipe_bytes=b"{}", call_id=f"planner-{index}", **usage
    )
    if case == "max_turns":
        return (
            [invalid(index) for index in range(1, PLANNER_SUPPORT.PLANNER_MAX_TURNS + 1)],
            [],
        )
    if case == "token_stop":
        return [
            invalid(
                1,
                total_tokens=PLANNER_SUPPORT.PLANNER_TOKEN_STOP_THRESHOLD,
            )
        ], []
    if case == "cost_stop":
        return [
            invalid(
                1,
                cost_usd=PLANNER_SUPPORT.PLANNER_COST_STOP_THRESHOLD_USD,
            )
        ], []
    if case == "planner_provider_failure":
        return [_provider_failure_action()], []
    if case == "planner_terminal_timeout":
        return [
            _provider_failure_action(failure_type="ProviderTimeoutError")
        ], []

    candidate = ISOLATED_SUCCESSOR_RECIPE.read_bytes()
    if case == "isolation_rejected":
        changed = json.loads(candidate)
        changed["goal"]["statement"] += " Unauthorized change."
        candidate = _reclose_recipe(changed, preflight.instrument.inputs)
    planner = [_planner_turn(recipe_bytes=candidate, call_id="planner-1")]
    if case == "isolation_rejected":
        return planner, []
    if case == "semantic_unfaithful":
        return planner, [_evaluator_turn("semantically_unfaithful")]
    if case == "evaluation_inconclusive":
        return planner, [_evaluator_turn("evaluation_inconclusive")]
    if case == "evaluator_malformed":
        malformed = replace(
            _evaluator_turn(),
            assistant_message={"role": "assistant", "content": "malformed"},
        )
        return planner, [malformed]
    if case == "evaluator_provider_failure":
        return planner, [_provider_failure_action()]
    if case == "evaluator_terminal_timeout":
        return planner, [
            _provider_failure_action(failure_type="ProviderTimeoutError")
        ]
    return planner, [_evaluator_turn("semantically_faithful")]


@pytest.mark.parametrize(
    ("case", "expected_classification", "expected_evaluator_calls"),
    OUTCOME_CASES,
)
def test_task4_complete_outcome_table_stops_at_first_terminal_boundary(
    case: str,
    expected_classification: str,
    expected_evaluator_calls: int,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    preflight = _task2_preflight(tmp_path)
    head_sha = preflight.record["reviewed_commit_sha"]
    readiness, manifest, route = _fresh_readiness(head_sha)
    planner_script, evaluator_script = _task4_provider_scripts(case, preflight)
    planner = _FakeProvider(planner_script, staging_path=preflight.attempt.staging_path)
    evaluator = _FakeProvider(
        evaluator_script, staging_path=preflight.attempt.staging_path
    )
    monkeypatch.setattr(
        RESOLUTION_ARTIFACTS, "require_clean_reviewed_checkout", lambda *_a: None
    )

    result = _run_resolution_attempt(
        monkeypatch=monkeypatch,
        preflight=preflight,
        invocation_binding=_invocation(preflight, readiness),
        readiness_record=readiness,
        readiness_manifest=manifest,
        head_sha=head_sha,
        now_iso="2026-07-25T20:00:06Z",
        credential_present={route.route_fingerprint: True},
        planner_provider=planner,
        evaluator_provider=evaluator,
    )

    assert result.classification == expected_classification
    assert len(evaluator.requests) == expected_evaluator_calls
    assert not planner.responses
    assert not evaluator.responses
    assert [row["call_index"] for row in result.call_ledger] == list(
        range(len(result.call_ledger))
    )
    roles = [row["role"] for row in result.call_ledger]
    assert roles == ["planner"] * len(planner.requests) + [
        "planner_evaluator"
    ] * expected_evaluator_calls
    assert "compiler" not in roles


def _run_task4_raised_call(
    *,
    role: str,
    raised_action: object,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[object, object, dict[str, object]]:
    preflight = _task2_preflight(tmp_path)
    head_sha = preflight.record["reviewed_commit_sha"]
    readiness, manifest, route = _fresh_readiness(head_sha)
    accepted = _planner_turn(
        recipe_bytes=ISOLATED_SUCCESSOR_RECIPE.read_bytes(),
        call_id="planner-1",
    )
    planner = _FakeProvider(
        [raised_action] if role == "planner" else [accepted],
        staging_path=preflight.attempt.staging_path,
    )
    evaluator = _FakeProvider(
        [raised_action] if role == "planner_evaluator" else [],
        staging_path=preflight.attempt.staging_path,
    )
    monkeypatch.setattr(
        RESOLUTION_ARTIFACTS, "require_clean_reviewed_checkout", lambda *_a: None
    )

    result = _run_resolution_attempt(
        monkeypatch=monkeypatch,
        preflight=preflight,
        invocation_binding=_invocation(preflight, readiness),
        readiness_record=readiness,
        readiness_manifest=manifest,
        head_sha=head_sha,
        now_iso="2026-07-25T20:00:06Z",
        credential_present={route.route_fingerprint: True},
        planner_provider=planner,
        evaluator_provider=evaluator,
    )
    row = next(item for item in result.call_ledger if item["role"] == role)
    return preflight, result, row


@pytest.mark.parametrize("role", ("planner", "planner_evaluator"))
def test_task4_provider_call_failure_retains_reconstructible_adapter_evidence(
    role: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    preflight, result, row = _run_task4_raised_call(
        role=role,
        raised_action=_provider_failure_action(),
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
    )

    assert result.state == "terminal_evidence_complete"
    assert result.classification == "probe_inconclusive"
    request = json.loads(row["canonical_request_json"])
    raw_request = base64.b64decode(
        row["provider_claimed_raw_request_b64"], validate=True
    )
    raw_error = base64.b64decode(row["provider_raw_error_b64"], validate=True)
    assert raw_request == _expected_litellm_request_bytes(request)
    assert row["provider_claimed_raw_request_sha256"] == (
        PLANNER_SUPPORT.sha256_prefixed(raw_request)
    )
    assert raw_error == b'{"provider":"failed"}\n'
    assert row["provider_raw_error_sha256"] == (
        PLANNER_SUPPORT.sha256_prefixed(raw_error)
    )

    reclosed_ledger = [copy.deepcopy(item) for item in result.call_ledger]
    mutated = next(item for item in reclosed_ledger if item["role"] == role)
    contradictory_request = b'{"wrong":"reclosed"}\n'
    mutated["provider_claimed_raw_request_b64"] = base64.b64encode(
        contradictory_request
    ).decode("ascii")
    mutated["provider_claimed_raw_request_sha256"] = (
        PLANNER_SUPPORT.sha256_prefixed(contradictory_request)
    )
    with pytest.raises(ValueError, match="LiteLLM failure request"):
        RESOLUTION_ARTIFACTS.verify_resolution_call_ledger(
            preflight=preflight,
            planner_session=result.planner_session,
            evaluator_result=result.evaluator_result,
            isolation_result=result.isolation_result,
            classification=result.classification,
            candidate_recipe_bytes=result.candidate_recipe_bytes,
            call_ledger=tuple(reclosed_ledger),
            derived_stop_cause=result.derived_stop_cause,
        )


@pytest.mark.parametrize("role", ("planner", "planner_evaluator"))
def test_task4_wrong_provider_failure_request_is_post_dispatch_unsealed(
    role: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _preflight, result, row = _run_task4_raised_call(
        role=role,
        raised_action=_provider_failure_action(
            raw_request=b'{"wrong":"request"}\n'
        ),
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
    )

    assert result.state == "post_dispatch_unsealed"
    assert result.classification is None
    stop_role = "evaluator" if role == "planner_evaluator" else "planner"
    assert result.derived_stop_cause == f"{stop_role}_adapter_request_mismatch"
    assert base64.b64decode(
        row["provider_claimed_raw_request_b64"], validate=True
    ) == b'{"wrong":"request"}\n'


@pytest.mark.parametrize("role", ("planner", "planner_evaluator"))
@pytest.mark.parametrize("exception_type", (RuntimeError, TimeoutError))
def test_task4_exception_without_adapter_evidence_is_post_dispatch_unsealed(
    role: str,
    exception_type: type[BaseException],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _preflight, result, _row = _run_task4_raised_call(
        role=role,
        raised_action=exception_type("failed without adapter evidence"),
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
    )

    assert result.state == "post_dispatch_unsealed"
    assert result.classification is None
    stop_role = "evaluator" if role == "planner_evaluator" else "planner"
    assert result.derived_stop_cause == f"{stop_role}_adapter_evidence_incomplete"


def test_task4_evaluator_request_is_parent_comparison_blind_and_authority_current() -> None:
    *_prefix, inputs = _verified_resolution_inputs()
    rendered = RESOLUTION_SUPPORT.render_planner_revision_evaluation_request(
        inputs,
        candidate_recipe_bytes=ISOLATED_SUCCESSOR_RECIPE.read_bytes(),
    )
    request = json.loads(rendered.raw_bytes)

    assert set(request) == {
        "schema",
        "renderer_id",
        "attempt_context",
        "brief",
        "authority_context",
        "final_recipe_json",
        "final_recipe_raw_sha256",
        "evaluation_rubric",
        "evaluation_report_contract",
    }
    forbidden_keys = {
        "parent_recipe",
        "correspondence",
        "policy_instance",
        "isolation_report",
        "expected_classification",
        "session_transcript",
        "compiler_context",
        "mechanical_gate_accepted",
        "isolation_accepted",
    }
    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {
                nested
                for item in value.values()
                for nested in keys(item)
            }
        if isinstance(value, list):
            return {nested for item in value for nested in keys(item)}
        return set()

    assert forbidden_keys.isdisjoint(keys(request))

    def values(value: object, path: str = "") -> list[tuple[str, object]]:
        if isinstance(value, dict):
            return [
                nested
                for key, item in value.items()
                for nested in values(item, f"{path}/{key}")
            ]
        if isinstance(value, list):
            return [
                nested
                for index, item in enumerate(value)
                for nested in values(item, f"{path}/{index}")
            ]
        return [(path, value)]

    scalar_values = values(request)
    r01_paths = {
        path
        for path, value in scalar_values
        if isinstance(value, str) and "r01" in value.casefold()
    }
    assert r01_paths == {
        "/attempt_context/environment_session_id",
        "/attempt_context/task_session_id",
        "/authority_context/artifacts/environment_snapshot/environment_session_id",
        "/authority_context/artifacts/environment_snapshot/payload_schema",
        "/authority_context/artifacts/planning_policy/policy_registry_id",
        "/authority_context/artifacts/task_envelope/task_session_id",
        "/authority_context/artifacts/task_envelope/value_bindings/2/provenance/issuer_id",
        "/authority_context/artifacts/task_envelope/value_bindings/3/provenance/issuer_id",
        "/authority_context/artifacts/task_envelope/value_bindings/4/provenance/issuer_id",
        "/authority_context/artifacts/task_envelope/value_bindings/8/provenance/issuer_id",
        "/authority_context/artifacts/task_envelope/value_bindings/9/provenance/issuer_id",
        "/authority_context/artifacts/task_envelope/value_bindings/10/provenance/issuer_id",
        "/authority_context/artifacts/task_envelope/value_bindings/11/provenance/issuer_id",
    }
    prohibited_control_values = {
        "probe_candidate_ready",
        "probe_resolution_isolation_failure",
        "source_descriptor",
        "affected_clause_residual",
        "residual_equality",
    }
    assert prohibited_control_values.isdisjoint(
        {value for _path, value in scalar_values if isinstance(value, str)}
    )


def test_task4_arbitrary_caller_provider_is_not_an_execution_capability(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    preflight = _task2_preflight(tmp_path)
    head_sha = preflight.record["reviewed_commit_sha"]
    readiness, manifest, route = _fresh_readiness(head_sha)
    calls = {"planner": 0, "planner_evaluator": 0}

    def arbitrary(_request: object) -> object:
        calls["planner"] += 1
        raise AssertionError("arbitrary caller provider was dispatched")

    monkeypatch.setattr(
        RESOLUTION_ARTIFACTS, "require_clean_reviewed_checkout", lambda *_a: None
    )
    with pytest.raises(ValueError, match="arguments"):
        RESOLUTION_PROBE.run_resolution_attempt(
            preflight=preflight,
            invocation_binding=_invocation(preflight, readiness),
            readiness_record=readiness,
            readiness_manifest=manifest,
            head_sha=head_sha,
            now_iso="2026-07-25T20:00:06Z",
            credential_present={route.route_fingerprint: True},
            planner_provider=arbitrary,
            evaluator_provider=arbitrary,
        )
    assert calls == {"planner": 0, "planner_evaluator": 0}
    assert not preflight.attempt.staging_path.exists()


def test_task4_constructed_adapter_identity_is_bound_before_reservation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    preflight = _task2_preflight(tmp_path)
    head_sha = preflight.record["reviewed_commit_sha"]
    readiness, manifest, route = _fresh_readiness(head_sha)
    constructed = _FakeProvider([], staging_path=preflight.attempt.staging_path)
    constructed.identity = {**constructed.identity, "adapter_path": "forged.adapter"}
    monkeypatch.setattr(
        RESOLUTION_PROBE,
        "_construct_resolution_role_provider",
        lambda **_kwargs: constructed,
    )
    monkeypatch.setattr(
        RESOLUTION_ARTIFACTS, "require_clean_reviewed_checkout", lambda *_a: None
    )
    with pytest.raises(ValueError, match="adapter identity"):
        RESOLUTION_PROBE.run_resolution_attempt(
            preflight=preflight,
            invocation_binding=_invocation(preflight, readiness),
            readiness_record=readiness,
            readiness_manifest=manifest,
            head_sha=head_sha,
            now_iso="2026-07-25T20:00:06Z",
            credential_present={route.route_fingerprint: True},
        )
    assert not preflight.attempt.staging_path.exists()


@pytest.mark.parametrize("role", ("planner", "planner_evaluator"))
def test_task4_provider_returned_model_is_preserved_without_equality_claim(
    role: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    preflight = _task2_preflight(tmp_path)
    head_sha = preflight.record["reviewed_commit_sha"]
    readiness, manifest, route = _fresh_readiness(head_sha)
    planner_turn = _planner_turn(
        recipe_bytes=ISOLATED_SUCCESSOR_RECIPE.read_bytes(),
        call_id="planner-1",
    )
    evaluator_turn = _evaluator_turn()
    if role == "planner":
        planner_turn = replace(
            planner_turn,
            provider_metadata={
                **planner_turn.provider_metadata,
                "response_model": "gpt-5.4-planner-hosted-revision",
            },
        )
    else:
        evaluator_turn = replace(
            evaluator_turn,
            provider_metadata={
                **evaluator_turn.provider_metadata,
                "response_model": "gpt-5.4-evaluator-hosted-revision",
            },
        )
    planner = _FakeProvider(
        [planner_turn], staging_path=preflight.attempt.staging_path
    )
    evaluator = _FakeProvider(
        [evaluator_turn], staging_path=preflight.attempt.staging_path
    )
    monkeypatch.setattr(
        RESOLUTION_ARTIFACTS, "require_clean_reviewed_checkout", lambda *_a: None
    )
    result = _run_resolution_attempt(
        monkeypatch=monkeypatch,
        preflight=preflight,
        invocation_binding=_invocation(preflight, readiness),
        readiness_record=readiness,
        readiness_manifest=manifest,
        head_sha=head_sha,
        now_iso="2026-07-25T20:00:06Z",
        credential_present={route.route_fingerprint: True},
        planner_provider=planner,
        evaluator_provider=evaluator,
    )
    assert result.state == "sealed"
    assert result.classification == "probe_candidate_ready"
    row = next(item for item in result.call_ledger if item["role"] == role)
    assert row["provider_metadata"]["requested_model"] == "gpt-5.4"
    assert row["provider_metadata"]["requested_profile"] == (
        "litellm.completion.tool_calling.no_parallel:v1"
    )
    assert row["provider_metadata"]["response_model"] == (
        "gpt-5.4-planner-hosted-revision"
        if role == "planner"
        else "gpt-5.4-evaluator-hosted-revision"
    )


@pytest.mark.parametrize(
    ("section", "field", "changed"),
    (
        ("planner", "system_prompt_fingerprint", "sha256:" + "1" * 64),
        ("planner", "tool_schema_fingerprint", "sha256:" + "2" * 64),
        ("planner", "provider_profile", "altered.provider.profile:v1"),
        ("planner", "model", "gpt-5.3"),
        ("planner", "provider_timeout_s", 179.0),
        ("planner", "feedback_renderer_source_fingerprint", "sha256:" + "3" * 64),
        ("evaluator", "system_prompt_fingerprint", "sha256:" + "4" * 64),
        ("evaluator", "tool_schema_fingerprint", "sha256:" + "5" * 64),
        ("evaluator", "report_schema_fingerprint", "sha256:" + "6" * 64),
        ("evaluator", "rubric_fingerprint", "sha256:" + "7" * 64),
        ("evaluator", "model", "gpt-5.3"),
        ("evaluator", "max_completion_tokens", 4096),
    ),
)
def test_task4_reclosed_request_or_control_drift_refuses_before_dispatch(
    section: str,
    field: str,
    changed: object,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    preflight = _task2_preflight(tmp_path)

    def mutate(record: dict[str, object]) -> None:
        record["instrument_contracts"][section][field] = changed
        record["instrument_fingerprint"] = PLANNER_SUPPORT.fingerprint(
            record["instrument_contracts"]
        )

    preflight = _reclose_preflight(preflight, mutate)
    head_sha = preflight.record["reviewed_commit_sha"]
    readiness, manifest, route = _fresh_readiness(head_sha)
    calls = {"planner": 0, "planner_evaluator": 0}

    def planner_provider(_request: object) -> object:
        calls["planner"] += 1
        raise AssertionError("Planner was dispatched")

    def evaluator_provider(_request: object) -> object:
        calls["planner_evaluator"] += 1
        raise AssertionError("evaluator was dispatched")

    monkeypatch.setattr(
        RESOLUTION_ARTIFACTS, "require_clean_reviewed_checkout", lambda *_a: None
    )
    with pytest.raises(ValueError, match="instrument|preflight"):
        _run_resolution_attempt(
            monkeypatch=monkeypatch,
            preflight=preflight,
            invocation_binding=_invocation(preflight, readiness),
            readiness_record=readiness,
            readiness_manifest=manifest,
            head_sha=head_sha,
            now_iso="2026-07-25T20:00:06Z",
            credential_present={route.route_fingerprint: True},
            planner_provider=planner_provider,
            evaluator_provider=evaluator_provider,
        )
    assert calls == {"planner": 0, "planner_evaluator": 0}
    assert not preflight.attempt.staging_path.exists()


def test_task4_provider_mutation_cannot_change_staged_or_ledger_request_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    preflight = _task2_preflight(tmp_path)
    head_sha = preflight.record["reviewed_commit_sha"]
    readiness, manifest, route = _fresh_readiness(head_sha)
    scripted = [
        _planner_turn(
            recipe_bytes=ISOLATED_SUCCESSOR_RECIPE.read_bytes(),
            call_id="planner-1",
        ),
        _evaluator_turn(),
    ]
    seen: list[dict[str, object]] = []

    def mutating_provider(request: dict[str, object]) -> object:
        seen.append(request)
        response = scripted.pop(0)
        request.clear()
        request["mutated_by_provider"] = True
        return response

    monkeypatch.setattr(
        RESOLUTION_ARTIFACTS, "require_clean_reviewed_checkout", lambda *_a: None
    )
    result = _run_resolution_attempt(
        monkeypatch=monkeypatch,
        preflight=preflight,
        invocation_binding=_invocation(preflight, readiness),
        readiness_record=readiness,
        readiness_manifest=manifest,
        head_sha=head_sha,
        now_iso="2026-07-25T20:00:06Z",
        credential_present={route.route_fingerprint: True},
        planner_provider=mutating_provider,
        evaluator_provider=mutating_provider,
    )

    assert len(seen) == 2
    assert all(value == {"mutated_by_provider": True} for value in seen)
    planner_raw = result.call_ledger[0]["canonical_request_json"].encode("utf-8")
    evaluator_raw = result.call_ledger[1]["canonical_request_json"].encode("utf-8")
    assert "mutated_by_provider" not in result.call_ledger[0]["canonical_request_json"]
    assert "mutated_by_provider" not in result.call_ledger[1]["canonical_request_json"]
    assert all(
        type(row["elapsed_ms"]) is int and row["elapsed_ms"] >= 0
        for row in result.call_ledger
    )
    PLANNER_SUPPORT.materialize_planner_provider_call_request(planner_raw)
    PLANNER_SUPPORT.materialize_planner_evaluator_provider_call_request(evaluator_raw)
    for row in result.call_ledger:
        request = json.loads(row["canonical_request_json"])
        assert base64.b64decode(
            row["provider_claimed_raw_request_b64"], validate=True
        ) == _expected_litellm_request_bytes(request)


def test_task4_terminal_evidence_retains_exact_staged_execution_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    preflight = _task2_preflight(tmp_path)
    head_sha = preflight.record["reviewed_commit_sha"]
    readiness, manifest, route = _fresh_readiness(head_sha)
    planner = _FakeProvider(
        [
            _planner_turn(
                recipe_bytes=ISOLATED_SUCCESSOR_RECIPE.read_bytes(),
                call_id="planner-1",
            )
        ],
        staging_path=preflight.attempt.staging_path,
    )
    evaluator = _FakeProvider(
        [_evaluator_turn("semantically_unfaithful")],
        staging_path=preflight.attempt.staging_path,
    )
    monkeypatch.setattr(
        RESOLUTION_ARTIFACTS, "require_clean_reviewed_checkout", lambda *_a: None
    )
    result = _run_resolution_attempt(
        monkeypatch=monkeypatch,
        preflight=preflight,
        invocation_binding=_invocation(preflight, readiness),
        readiness_record=readiness,
        readiness_manifest=manifest,
        head_sha=head_sha,
        now_iso="2026-07-25T20:00:06Z",
        credential_present={route.route_fingerprint: True},
        planner_provider=planner,
        evaluator_provider=evaluator,
    )

    assert result.state == "terminal_evidence_complete"
    runtime = preflight.attempt.staging_path / ".resolution-runtime"
    assert (runtime / "preflight.json").read_bytes() == (
        preflight.archive_dir / "record.json"
    ).read_bytes()
    assert (runtime / "initial-request.json").read_bytes() == (
        preflight.archive_dir / "initial-request.json"
    ).read_bytes()
    attempt = json.loads((runtime / "attempt.json").read_bytes())
    assert attempt == {
        "schema": "rook.lm9b_p.governed_resolution_staged_attempt:v1",
        "attempt_id": preflight.attempt.attempt_id,
        "attempt_fingerprint": preflight.attempt.attempt_fingerprint,
        "canonical_destination": str(preflight.attempt.destination),
        "staging_path": str(preflight.attempt.staging_path),
    }
    archived_readiness = json.loads((runtime / "readiness.json").read_bytes())
    assert archived_readiness == {
        "schema": "rook.lm9b_p.governed_resolution_staged_readiness:v1",
        "record": readiness,
        "verified_at": "2026-07-25T20:00:06Z",
    }
    assert len(list((runtime / "calls").glob("*-request.json"))) == 2
    assert len(list((runtime / "calls").glob("*-dispatch_started.json"))) == 2


def test_task4_execution_uses_only_frozen_snapshot_after_reservation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    preflight = _task2_preflight(tmp_path)
    head_sha = preflight.record["reviewed_commit_sha"]
    readiness, manifest, route = _fresh_readiness(head_sha)
    planner = _FakeProvider(
        [
            _planner_turn(
                recipe_bytes=ISOLATED_SUCCESSOR_RECIPE.read_bytes(),
                call_id="planner-1",
            )
        ],
        staging_path=preflight.attempt.staging_path,
    )
    evaluator = _FakeProvider(
        [_evaluator_turn()], staging_path=preflight.attempt.staging_path
    )
    ledger_init = RESOLUTION_PROBE._StagedCallLedger.__init__

    def initialize_then_close_external_sources(value: object, **kwargs: object) -> None:
        ledger_init(value, **kwargs)
        monkeypatch.setattr(
            RESOLUTION_ARTIFACTS,
            "_load_current_resolution_sources",
            lambda *_a, **_k: (_ for _ in ()).throw(
                AssertionError("external source was reread after reservation")
            ),
        )

    monkeypatch.setattr(
        RESOLUTION_PROBE._StagedCallLedger,
        "__init__",
        initialize_then_close_external_sources,
    )
    monkeypatch.setattr(
        RESOLUTION_ARTIFACTS, "require_clean_reviewed_checkout", lambda *_a: None
    )
    result = _run_resolution_attempt(
        monkeypatch=monkeypatch,
        preflight=preflight,
        invocation_binding=_invocation(preflight, readiness),
        readiness_record=readiness,
        readiness_manifest=manifest,
        head_sha=head_sha,
        now_iso="2026-07-25T20:00:06Z",
        credential_present={route.route_fingerprint: True},
        planner_provider=planner,
        evaluator_provider=evaluator,
    )

    assert result.state == "sealed"
    assert result.classification == "probe_candidate_ready"


@pytest.mark.parametrize(
    "mutation",
    (
        "call_index",
        "role",
        "dynamic_timeout",
        "adapter_dispatch_reclosure",
        "request",
        "usage",
        "elapsed",
        "stop_cause",
        "requested_identity",
    ),
)
def test_task4_public_call_ledger_reconstruction_rejects_reclosed_claims(
    mutation: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    preflight = _task2_preflight(tmp_path)
    head_sha = preflight.record["reviewed_commit_sha"]
    readiness, manifest, route = _fresh_readiness(head_sha)
    planner = _FakeProvider(
        [
            _planner_turn(
                recipe_bytes=ISOLATED_SUCCESSOR_RECIPE.read_bytes(),
                call_id="planner-1",
            )
        ],
        staging_path=preflight.attempt.staging_path,
    )
    evaluator = _FakeProvider(
        [_evaluator_turn()], staging_path=preflight.attempt.staging_path
    )
    monkeypatch.setattr(
        RESOLUTION_ARTIFACTS, "require_clean_reviewed_checkout", lambda *_a: None
    )
    result = _run_resolution_attempt(
        monkeypatch=monkeypatch,
        preflight=preflight,
        invocation_binding=_invocation(preflight, readiness),
        readiness_record=readiness,
        readiness_manifest=manifest,
        head_sha=head_sha,
        now_iso="2026-07-25T20:00:06Z",
        credential_present={route.route_fingerprint: True},
        planner_provider=planner,
        evaluator_provider=evaluator,
    )
    ledger = copy.deepcopy(list(result.call_ledger))
    stop_cause = result.derived_stop_cause
    if mutation == "call_index":
        ledger[0]["call_index"] = 7
    elif mutation == "role":
        ledger[0]["role"] = "compiler"
    elif mutation == "dynamic_timeout":
        request = json.loads(ledger[0]["canonical_request_json"])
        request["provider_timeout_s"] = PLANNER_SUPPORT.PLANNER_PROVIDER_TIMEOUT_S - 1
        ledger[0]["canonical_request_json"] = _canonical_bytes(request).decode()
        ledger[0]["request_raw_sha256"] = PLANNER_SUPPORT.sha256_prefixed(
            ledger[0]["canonical_request_json"].encode()
        )
        ledger[0]["provider_timeout_s"] = request["provider_timeout_s"]
        marker = {
            "schema": ledger[0]["schema"],
            "call_index": ledger[0]["call_index"],
            "role": ledger[0]["role"],
            "request_raw_sha256": ledger[0]["request_raw_sha256"],
            "preceding_transcript_fingerprint": ledger[0][
                "preceding_transcript_fingerprint"
            ],
            "provider_timeout_s": ledger[0]["provider_timeout_s"],
            "controller_deadline_state": ledger[0]["controller_deadline_state"],
            "role_contract_fingerprint": ledger[0][
                "role_contract_fingerprint"
            ],
        }
        ledger[0]["dispatch_marker_raw_sha256"] = (
            PLANNER_SUPPORT.sha256_prefixed(_canonical_bytes(marker))
        )
    elif mutation == "adapter_dispatch_reclosure":
        request = json.loads(ledger[0]["canonical_request_json"])
        request["provider_timeout_s"] = 179.0
        ledger[0]["canonical_request_json"] = _canonical_bytes(request).decode()
        ledger[0]["request_raw_sha256"] = PLANNER_SUPPORT.sha256_prefixed(
            ledger[0]["canonical_request_json"].encode()
        )
        ledger[0]["provider_timeout_s"] = 179.0
        state = ledger[0]["controller_deadline_state"]
        state["call_started_monotonic_s"] = (
            state["session_started_monotonic_s"] + 421.0
        )
        state["elapsed_before_call_s"] = 421.0
        state["remaining_before_call_s"] = 179.0
        marker = {
            "schema": ledger[0]["schema"],
            "call_index": ledger[0]["call_index"],
            "role": ledger[0]["role"],
            "request_raw_sha256": ledger[0]["request_raw_sha256"],
            "preceding_transcript_fingerprint": ledger[0][
                "preceding_transcript_fingerprint"
            ],
            "provider_timeout_s": ledger[0]["provider_timeout_s"],
            "controller_deadline_state": state,
            "role_contract_fingerprint": ledger[0][
                "role_contract_fingerprint"
            ],
        }
        ledger[0]["dispatch_marker_raw_sha256"] = (
            PLANNER_SUPPORT.sha256_prefixed(_canonical_bytes(marker))
        )
    elif mutation == "request":
        ledger[0]["preceding_transcript_fingerprint"] = "sha256:" + "8" * 64
    elif mutation == "usage":
        ledger[0]["usage"]["total_tokens"] = (
            PLANNER_SUPPORT.PLANNER_TOKEN_STOP_THRESHOLD
        )
    elif mutation == "elapsed":
        ledger[0]["elapsed_ms"] = int(
            (PLANNER_SUPPORT.PLANNER_PROVIDER_TIMEOUT_S + 2) * 1000
        )
    elif mutation == "stop_cause":
        stop_cause = "max_turns"
    elif mutation == "requested_identity":
        ledger[0]["provider_metadata"]["requested_model"] = "gpt-5.3"

    with pytest.raises(
        ValueError, match="ledger|request|timeout|usage|stop|identity"
    ):
        RESOLUTION_ARTIFACTS.verify_resolution_call_ledger(
            preflight=preflight,
            planner_session=result.planner_session,
            evaluator_result=result.evaluator_result,
            isolation_result=result.isolation_result,
            classification=result.classification,
            candidate_recipe_bytes=result.candidate_recipe_bytes,
            call_ledger=tuple(ledger),
            derived_stop_cause=stop_cause,
        )


def test_task4_call_ledger_derives_planner_termination_from_provider_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    preflight = _task2_preflight(tmp_path)
    head_sha = preflight.record["reviewed_commit_sha"]
    readiness, manifest, route = _fresh_readiness(head_sha)
    planner = _FakeProvider(
        [_provider_failure_action()],
        staging_path=preflight.attempt.staging_path,
    )
    monkeypatch.setattr(
        RESOLUTION_ARTIFACTS, "require_clean_reviewed_checkout", lambda *_a: None
    )
    result = _run_resolution_attempt(
        monkeypatch=monkeypatch,
        preflight=preflight,
        invocation_binding=_invocation(preflight, readiness),
        readiness_record=readiness,
        readiness_manifest=manifest,
        head_sha=head_sha,
        now_iso="2026-07-25T20:00:06Z",
        credential_present={route.route_fingerprint: True},
        planner_provider=planner,
        evaluator_provider=lambda _request: None,
    )
    forged_session = replace(result.planner_session, termination="timeout")

    with pytest.raises(ValueError, match="termination|provider evidence"):
        RESOLUTION_ARTIFACTS.verify_resolution_call_ledger(
            preflight=preflight,
            planner_session=forged_session,
            evaluator_result=None,
            isolation_result=None,
            classification="probe_inconclusive",
            candidate_recipe_bytes=None,
            call_ledger=result.call_ledger,
            derived_stop_cause="planner_terminal_timeout",
        )


@pytest.mark.parametrize("role", ("planner", "planner_evaluator"))
def test_task4_still_live_timeout_is_post_dispatch_unsealed(
    role: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    preflight = _task2_preflight(tmp_path)
    head_sha = preflight.record["reviewed_commit_sha"]
    readiness, manifest, route = _fresh_readiness(head_sha)
    release = threading.Event()
    bounded_call = PLANNER_SUPPORT._bounded_provider_call

    def short_bounded_call(
        provider: object,
        request: dict[str, object],
        *,
        timeout_s: float,
    ) -> object:
        return bounded_call(provider, request, timeout_s=min(timeout_s, 0.2))

    monkeypatch.setattr(PLANNER_SUPPORT, "_bounded_provider_call", short_bounded_call)

    def hanging_provider(_request: dict[str, object]) -> object:
        release.wait(5)
        return (
            _planner_turn(
                recipe_bytes=ISOLATED_SUCCESSOR_RECIPE.read_bytes(),
                call_id="planner-1",
            )
            if role == "planner"
            else _evaluator_turn()
        )

    planner_provider = (
        hanging_provider
        if role == "planner"
        else _FakeProvider(
            [
                _planner_turn(
                    recipe_bytes=ISOLATED_SUCCESSOR_RECIPE.read_bytes(),
                    call_id="planner-1",
                )
            ],
            staging_path=preflight.attempt.staging_path,
        )
    )
    evaluator_provider = hanging_provider if role == "planner_evaluator" else _boom
    monkeypatch.setattr(
        RESOLUTION_ARTIFACTS, "require_clean_reviewed_checkout", lambda *_a: None
    )
    try:
        result = _run_resolution_attempt(
            monkeypatch=monkeypatch,
            preflight=preflight,
            invocation_binding=_invocation(preflight, readiness),
            readiness_record=readiness,
            readiness_manifest=manifest,
            head_sha=head_sha,
            now_iso="2026-07-25T20:00:06Z",
            credential_present={route.route_fingerprint: True},
            planner_provider=planner_provider,
            evaluator_provider=evaluator_provider,
        )
    finally:
        release.set()

    assert result.state == "post_dispatch_unsealed"
    assert result.classification is None
    assert result.call_ledger[-1]["terminal"] is False
    markers = list(
        preflight.attempt.staging_path.glob(
            ".resolution-runtime/calls/*-dispatch_started.json"
        )
    )
    assert len(markers) == (1 if role == "planner" else 2)


def test_task4_terminal_row_is_not_published_before_evidence_capture_and_join(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    preflight = _task2_preflight(tmp_path)
    head_sha = preflight.record["reviewed_commit_sha"]
    readiness, manifest, route = _fresh_readiness(head_sha)
    capture_entered = threading.Event()
    release_capture = threading.Event()
    bounded_call = PLANNER_SUPPORT._bounded_provider_call

    def short_bounded_call(
        provider: object,
        request: dict[str, object],
        *,
        timeout_s: float,
    ) -> object:
        return bounded_call(provider, request, timeout_s=min(timeout_s, 0.2))

    monkeypatch.setattr(PLANNER_SUPPORT, "_bounded_provider_call", short_bounded_call)

    class BlockingEvidence(dict):
        def items(self):
            capture_entered.set()
            release_capture.wait(5)
            return super().items()

    ordinary_turn = _planner_turn(
        recipe_bytes=ISOLATED_SUCCESSOR_RECIPE.read_bytes(),
        call_id="planner-1",
    )
    planner_turn = replace(
        ordinary_turn,
        assistant_message=BlockingEvidence(dict(ordinary_turn.assistant_message)),
    )
    planner = _FakeProvider(
        [planner_turn], staging_path=preflight.attempt.staging_path
    )
    evaluator = _FakeProvider([], staging_path=preflight.attempt.staging_path)
    monkeypatch.setattr(
        RESOLUTION_ARTIFACTS, "require_clean_reviewed_checkout", lambda *_a: None
    )
    try:
        result = _run_resolution_attempt(
            monkeypatch=monkeypatch,
            preflight=preflight,
            invocation_binding=_invocation(preflight, readiness),
            readiness_record=readiness,
            readiness_manifest=manifest,
            head_sha=head_sha,
            now_iso="2026-07-25T20:00:06Z",
            credential_present={route.route_fingerprint: True},
            planner_provider=planner,
            evaluator_provider=evaluator,
        )
        assert capture_entered.is_set()
    finally:
        release_capture.set()

    assert result.state == "post_dispatch_unsealed"
    assert result.classification is None
    assert result.call_ledger[-1]["terminal"] is False
    assert result.call_ledger[-1]["provider_metadata"] is None
