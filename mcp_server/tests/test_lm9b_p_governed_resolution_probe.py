from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
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


def _load_script(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PLANNER_SUPPORT = _load_script("lm9b_p_planner_recipe_transfer_support")
PLANNER_ARTIFACTS = _load_script("lm9b_p_planner_recipe_transfer_artifacts")
CONT_ARTIFACTS = _load_script("lm9b_p_evaluator_only_continuation_artifacts")
TYPED_VALUES = _load_script("lm9_semantic_typed_values")
CARRIER = _load_script("lm9_typed_fact_carrier_artifacts")
QUALIFICATION = _load_script("lm9_typed_fact_carrier_qualification")
READINESS = _load_script("lm9b_p_readiness_contract")
RESOLUTION_SUPPORT = _load_script("lm9b_p_governed_resolution_support")
RESOLUTION_ARTIFACTS = _load_script("lm9b_p_governed_resolution_artifacts")
RESOLUTION_PROBE = _load_script("lm9b_p_governed_resolution_probe")
COMPILER_SUPPORT = _load_script("lm9b_c_compiler_sufficiency_support")
COMPILER_PROBE = _load_script("lm9b_c_compiler_sufficiency_probe")


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


def _boom(*_args: object, **_kwargs: object) -> object:
    raise AssertionError("compiler entry was reached")


def _verified_resolution_inputs():
    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    source = CONT_ARTIFACTS.verify_historical_source()
    derivative = CONT_ARTIFACTS.verify_sealed_derivative_archive(
        DERIVATIVE_ARCHIVE,
        expected_derivative_identity=DERIVATIVE_IDENTITY,
    )
    compatibility = (
        RESOLUTION_ARTIFACTS.verify_historical_carrier_qualification_compatibility(
            archive_dir=CARRIER_QUALIFICATION,
            expected_identity=CARRIER_QUALIFICATION_IDENTITY,
            repo_root=ROOT,
            consuming_commit_sha=head_sha,
        )
    )
    inputs = RESOLUTION_SUPPORT.assemble_verified_resolution_inputs(
        historical_source=source,
        parent_derivative=derivative,
        carrier_qualification=compatibility,
        successor_envelope_bytes=CARRIER.RADIAL_FIXTURE_PATH.read_bytes(),
        payload_schema_bytes=CARRIER.PAYLOAD_SCHEMA_PATH.read_bytes(),
        semantic_registry_bytes=CARRIER.REGISTRY_PATH.read_bytes(),
        isolation_policy_bytes=ISOLATION_POLICY.read_bytes(),
        evaluation_rubric_bytes=EVALUATION_RUBRIC.read_bytes(),
        reviewed_commit_sha=head_sha,
    )
    return head_sha, source, derivative, compatibility, inputs


def _reclose_recipe(value: dict[str, object], inputs: object) -> bytes:
    projection = {
        key: item for key, item in value.items() if key != "recipe_fingerprint"
    }
    normalized = PLANNER_SUPPORT.normalize_recipe(
        copy.deepcopy(projection), inputs.normalization_profile
    )
    value["recipe_fingerprint"] = PLANNER_SUPPORT.fingerprint(normalized)
    return _canonical_bytes(value)


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
    source = CONT_ARTIFACTS.verify_historical_source()
    derivative = CONT_ARTIFACTS.verify_sealed_derivative_archive(
        DERIVATIVE_ARCHIVE,
        expected_derivative_identity=DERIVATIVE_IDENTITY,
    )
    compatibility = (
        RESOLUTION_ARTIFACTS.verify_historical_carrier_qualification_compatibility(
            archive_dir=CARRIER_QUALIFICATION,
            expected_identity=CARRIER_QUALIFICATION_IDENTITY,
            repo_root=ROOT,
            consuming_commit_sha=head_sha,
        )
    )
    assert compatibility.historical_commit_sha == CARRIER_COMMIT
    assert compatibility.consuming_commit_sha == head_sha

    inputs = RESOLUTION_SUPPORT.assemble_verified_resolution_inputs(
        historical_source=source,
        parent_derivative=derivative,
        carrier_qualification=compatibility,
        successor_envelope_bytes=CARRIER.RADIAL_FIXTURE_PATH.read_bytes(),
        payload_schema_bytes=CARRIER.PAYLOAD_SCHEMA_PATH.read_bytes(),
        semantic_registry_bytes=CARRIER.REGISTRY_PATH.read_bytes(),
        isolation_policy_bytes=ISOLATION_POLICY.read_bytes(),
        evaluation_rubric_bytes=EVALUATION_RUBRIC.read_bytes(),
        reviewed_commit_sha=head_sha,
    )
    instrument = RESOLUTION_ARTIFACTS.assemble_task1_resolution_instrument(inputs)
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
    verified = RESOLUTION_ARTIFACTS.verify_sealed_resolution_checkpoint(
        result.sealed_checkpoint.archive_dir,
        expected_identity=result.sealed_checkpoint.checkpoint_identity,
    )
    assert verified.classification == "probe_candidate_ready"
    assert verified.exact_recipe_bytes == ISOLATED_SUCCESSOR_RECIPE.read_bytes()
