from __future__ import annotations

import importlib.util
import inspect
import json
import re
import sys
from pathlib import Path

import pytest


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm8i_affine_publication_shape_support_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm8i_affine_publication_shape_support_probe",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()
SKELETAL_PASS1 = '{"kind": "action_request"}'
RECEIPT_ID = "opaque-lm8l-receipt-1"


class FakeToolExecutor:
    def __init__(self, responses):
        self.responses = dict(responses)
        self.calls = []

    async def __call__(self, tool_name, args):
        self.calls.append((tool_name, dict(args)))
        value = self.responses[tool_name]
        if isinstance(value, list):
            value = value.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class FakePublication:
    def __init__(self, row, response_payload=None):
        self.row = row
        self.response_payload = response_payload


def _fixture_tool_responses():
    return {
        "gh_library": [
            {
                "success": True,
                "count": 1,
                "components": [
                    {
                        "name": "Multiplication",
                        "nickName": "A*B",
                        "category": "Maths",
                        "guid": "MULTIPLY-PROXY-GUID",
                        "deprecated": False,
                    }
                ],
            },
            {
                "success": True,
                "count": 1,
                "components": [
                    {
                        "name": "Addition",
                        "nickName": "A+B",
                        "category": "Maths",
                        "guid": "ADDITION-PROXY-GUID",
                        "deprecated": False,
                    }
                ],
            },
        ],
        "gh_create_slider": [
            {
                "success": True,
                "data": {
                    "Created": True,
                    "Guid": "EDITABLE-GUID-1",
                    "NickName": "LM8I_Editable",
                },
            },
            {
                "success": True,
                "data": {
                    "Created": True,
                    "Guid": "FACTOR-GUID-1",
                    "NickName": "LM8I_Factor",
                },
            },
            {
                "success": True,
                "data": {
                    "Created": True,
                    "Guid": "OFFSET-GUID-1",
                    "NickName": "LM8I_Offset",
                },
            },
        ],
        "gh_create_component": [
            {
                "success": True,
                "data": {"Created": True, "Guid": "MULTIPLY-GUID-1", "NickName": "A*B"},
            },
            {
                "success": True,
                "data": {"Created": True, "Guid": "ADDITION-GUID-1", "NickName": "A+B"},
            },
        ],
        "gh_connect": [
            {"success": True, "data": {"connected": True}},
            {"success": True, "data": {"connected": True}},
            {"success": True, "data": {"connected": True}},
            {"success": True, "data": {"connected": True}},
        ],
        "gh_solve": {"success": True, "data": {"scheduled": True}},
        "gh_get_value": [
            {"success": True, "data": {"Guid": "EDITABLE-GUID-1", "Value": "2.0"}},
            {"success": True, "data": {"Guid": "FACTOR-GUID-1", "Value": "2.0"}},
            {"success": True, "data": {"Guid": "OFFSET-GUID-1", "Value": "1.5"}},
        ],
        "gh_inspect_output": {
            "success": True,
            "data": {"data_count": 1, "preview": ["5.5"]},
        },
    }


def _fixture_responses_for_success():
    responses = _fixture_tool_responses()
    responses.update(
        {
            "rhino_ping": "pong",
            "gh_document_new": {"success": True, "data": {"created": True}},
            "gh_set_value": {
                "success": True,
                "data": {"Guid": "EDITABLE-GUID-1", "Value": "3.0"},
            },
            "gh_inspect_output": [
                {
                    "success": True,
                    "data": {"data_count": 1, "preview": ["5.5"]},
                },
                {
                    "success": True,
                    "data": {"data_count": 1, "preview": ["7.5"]},
                },
            ],
        }
    )
    return responses


def _receipt(
    status,
    *,
    solution_run_epoch,
    completed_solution_run_epoch,
    reason=None,
):
    return {
        "schema": "rook.gh_solve_readiness_receipt:v1",
        "receipt_id": RECEIPT_ID,
        "document_session_id": "session-1",
        "mutation_epoch": 13,
        "solution_run_epoch": solution_run_epoch,
        "completed_solution_run_epoch": completed_solution_run_epoch,
        "status": status,
        "reason": reason,
    }


def _managed_success_responses():
    responses = _fixture_tool_responses()
    responses.update(
        {
            "rhino_ping": "pong",
            "gh_document_new": {"success": True, "data": {"created": True}},
            "gh_set_value": {
                "success": True,
                "data": {
                    "Guid": "EDITABLE-GUID-1",
                    "Value": "3.0",
                    "solve_readiness_receipt": _receipt(
                        "pending",
                        solution_run_epoch=None,
                        completed_solution_run_epoch=41,
                    ),
                },
            },
            "gh_wait_for_solve_readiness": {
                "success": True,
                "data": {
                    "schema": "rook.gh_solve_readiness_wait_result:v1",
                    "wait_status": "ready",
                    "receipt": _receipt(
                        "ready",
                        solution_run_epoch=42,
                        completed_solution_run_epoch=42,
                    ),
                },
            },
            "gh_inspect_output": [
                {
                    "success": True,
                    "data": {"data_count": 1, "preview": ["5.5"]},
                },
                {
                    "success": True,
                    "data": {
                        "data_count": 1,
                        "preview": ["7.5"],
                        "readiness_fenced": True,
                        "readiness_receipt_id": RECEIPT_ID,
                        "document_session_id": "session-1",
                        "mutation_epoch": 13,
                        "solution_run_epoch": 42,
                        "completed_solution_run_epoch": 42,
                    },
                },
            ],
        }
    )
    return responses


def _run_managed_probe(tmp_path, responses):
    executor = FakeToolExecutor(responses)
    run_dir = PROBE._run_probe(
        model=PROBE.DEFAULT_MODEL,
        endpoint=PROBE.DEFAULT_ENDPOINT,
        temperature=PROBE.DEFAULT_TEMPERATURE,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        verifier_profile=PROBE.MANAGED_VERIFIER_PROFILE,
        tool_executor=executor,
        publication_runner=lambda *_args, **_kwargs: _published_action(3.0),
    )
    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    return run_dir, executor, decision


def _assert_managed_invariant_rejection(
    decision,
    *,
    expected_failures,
    readiness_wait_count,
    fenced_output_read_count,
):
    assert decision["decision"] == "rejected"
    assert decision["phase"] == "verifier_readiness"
    assert decision["reason"] == "managed_verifier_invariant_failed"
    assert decision["managed_verifier"]["failed_invariants"] == list(
        expected_failures
    )
    assert (
        decision["managed_verifier"]["readiness_wait_count"]
        == readiness_wait_count
    )
    assert (
        decision["managed_verifier"]["fenced_output_read_count"]
        == fenced_output_read_count
    )
    assert decision["managed_verifier"]["settle_read_count"] == 0


@pytest.mark.parametrize(
    ("result", "stage", "expected_reason"),
    [
        (
            {
                "success": True,
                "data": {
                    "wait_status": "timeout",
                    "receipt": _receipt(
                        "pending",
                        solution_run_epoch=None,
                        completed_solution_run_epoch=41,
                    ),
                },
            },
            "wait",
            "readiness_wait_timeout",
        ),
        (
            {
                "success": True,
                "data": {
                    "wait_status": "terminal",
                    "receipt": _receipt(
                        "unknown",
                        solution_run_epoch=None,
                        completed_solution_run_epoch=41,
                        reason="receipt_expired",
                    ),
                },
            },
            "wait",
            "readiness_receipt_expired",
        ),
        (
            {
                "success": False,
                "data": {
                    "error": "readiness_receipt_not_found_or_evicted_or_process_restarted"
                },
            },
            "wait",
            "readiness_receipt_not_found_or_evicted_or_process_restarted",
        ),
        (
            {"success": False, "data": {"error": "readiness_receipt_not_ready"}},
            "read",
            "readiness_receipt_not_ready",
        ),
        (
            {
                "success": True,
                "data": {
                    "wait_status": "terminal",
                    "receipt": _receipt(
                        "superseded",
                        solution_run_epoch=None,
                        completed_solution_run_epoch=41,
                    ),
                },
            },
            "wait",
            "readiness_receipt_superseded",
        ),
        (
            {
                "success": False,
                "data": {"error": "readiness_receipt_stale_solution_run"},
            },
            "wait",
            "readiness_receipt_stale_solution_run",
        ),
        (
            {
                "success": True,
                "data": {
                    "wait_status": "terminal",
                    "receipt": _receipt(
                        "document_replaced",
                        solution_run_epoch=None,
                        completed_solution_run_epoch=41,
                    ),
                },
            },
            "wait",
            "readiness_receipt_document_replaced",
        ),
        (
            {
                "success": True,
                "data": {
                    "wait_status": "terminal",
                    "receipt": _receipt(
                        "solver_locked",
                        solution_run_epoch=None,
                        completed_solution_run_epoch=41,
                    ),
                },
            },
            "wait",
            "readiness_receipt_solver_locked",
        ),
        (
            {
                "success": True,
                "data": {
                    "wait_status": "terminal",
                    "receipt": _receipt(
                        "unknown",
                        solution_run_epoch=None,
                        completed_solution_run_epoch=41,
                    ),
                },
            },
            "wait",
            "readiness_receipt_unknown",
        ),
        (
            {
                "success": False,
                "data": {"error": "readiness_wait_already_active"},
            },
            "wait",
            "readiness_wait_already_active",
        ),
    ],
)
def test_normalize_readiness_failure_preserves_product_reason(
    result, stage, expected_reason
):
    assert PROBE._normalize_readiness_failure(result, stage=stage) == expected_reason


def _pass1_missing_publication(excerpt=SKELETAL_PASS1):
    return FakePublication(
        row={
            "status": "pass1_decision_invalid",
            "failure_reason": "pass1_missing_action_id",
            "pass1_content_excerpt": excerpt,
            "pass1_content_sha256": "sha256:pass1",
            "observation_action_intent_anomaly": False,
        },
        response_payload=None,
    )


def _published_action(value=3.0):
    response_payload = {
        "schema": "rook.local_worker_turn_response:v1",
        "kind": "action_request",
        "action_id": "draft_gh_set_value_params",
        "rationale": "Use the affine relationship to match the expected output.",
        "input": {"value": value},
    }
    return FakePublication(
        row={
            "status": "published",
            "pass2_response_kind": "action_request",
            "pass2_content_excerpt": json.dumps(response_payload, sort_keys=True),
            "pass2_content_sha256": "sha256:pass2",
            "observation_action_intent_anomaly": False,
        },
        response_payload=response_payload,
    )


def _run(coro):
    import asyncio

    return asyncio.run(coro)


def test_cli_defaults_are_canonical_lm8i_shape():
    args = PROBE._args([])

    assert args.model == "gemma4:12b-it-qat"
    assert args.endpoint == "http://localhost:11434/api/chat"
    assert args.temperature == 0
    assert args.timeout_s == 120
    assert args.excerpt_chars == 1200
    assert args.run_dir == "probe_runs"
    assert args.canonical_evidence is True


def test_cli_defaults_to_settle_v1_without_changing_canonical_shape():
    args = PROBE._args([])
    assert args.verifier_profile == PROBE.SETTLE_VERIFIER_PROFILE
    assert args.canonical_evidence is True


def test_cli_accepts_only_managed_receipt_v2_as_the_alternate_profile():
    args = PROBE._args(["--verifier-profile", "managed_receipt_v2"])
    assert args.verifier_profile == PROBE.MANAGED_VERIFIER_PROFILE

    with pytest.raises(SystemExit):
        PROBE._args(["--verifier-profile", "unknown"])

    with pytest.raises(SystemExit):
        PROBE._args(["--readiness-wait-timeout-ms", "1"])


def test_cli_rejects_non_lm8i_surfaces():
    forbidden = [
        ["--phase", "receipt_recon"],
        ["--attempts", "5"],
        ["--retry-clean-observation"],
        ["--planner-provider-command", "x"],
        ["--prompt-profile", "shape_guidance_v2"],
        ["--request-json", "request.json"],
        ["--gh-edit"],
    ]
    for argv in forbidden:
        with pytest.raises(SystemExit):
            PROBE._args(argv)


def test_manifest_records_lm8i_identity():
    manifest = PROBE._manifest(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        canonical_evidence=True,
    )

    assert manifest["schema"] == "rook.lm8i_affine_publication_shape_support_probe:v1"
    assert manifest["attempts"] == 1
    assert manifest["publication_support_enabled"] is True
    assert manifest["publication_support_budget"] == 1
    assert manifest["support_eligibility"] == "exact_skeletal_action_request_missing_action_id"
    assert manifest["worker_retry_enabled"] is False
    assert manifest["planner_model"] is None
    assert manifest["gh_edit_enabled"] is False


def test_settle_manifest_is_exact_historical_shape():
    manifest = PROBE._manifest(
        model=PROBE.DEFAULT_MODEL,
        endpoint=PROBE.DEFAULT_ENDPOINT,
        temperature=PROBE.DEFAULT_TEMPERATURE,
        canonical_evidence=True,
        verifier_profile=PROBE.SETTLE_VERIFIER_PROFILE,
    )
    assert manifest["schema"] == PROBE.SCRIPT_SCHEMA
    assert "verifier_profile" not in manifest
    assert "verifier_mechanism" not in manifest
    assert "fixture_readiness_profile" not in manifest
    assert "readiness_wait_timeout_ms" not in manifest


def test_managed_manifest_records_only_the_new_profile_metadata():
    manifest = PROBE._manifest(
        model=PROBE.DEFAULT_MODEL,
        endpoint=PROBE.DEFAULT_ENDPOINT,
        temperature=PROBE.DEFAULT_TEMPERATURE,
        canonical_evidence=True,
        verifier_profile=PROBE.MANAGED_VERIFIER_PROFILE,
    )
    assert manifest["verifier_profile"] == "managed_receipt_v2"
    assert manifest["verifier_mechanism"] == "managed_solve_readiness_receipt"
    assert manifest["fixture_readiness_profile"] == "lm8i_legacy_setup_v1"
    assert manifest["readiness_wait_timeout_ms"] == 10_000


def test_lm8i_identity_surfaces_do_not_emit_lm8h_labels():
    failure = PROBE.FixtureSetupFailure(
        step="gh_create_slider",
        tool_name="gh_create_slider",
        failure_reason="boom",
        result={"Guid": "GUID-1", "NickName": "LM8I_Editable"},
    )
    summary = PROBE._fixture_failure_summary(failure, excerpt_chars=1200)
    scaffold = PROBE._affine_scalar_scaffold(
        PROBE.PlanGraph(nodes={}, memory=PROBE.GraphMemory())
    )

    assert summary["schema"] == "rook.lm8i_fixture_failure_summary:v1"
    assert scaffold.workflow_id == "lm8i-gh-affine-scalar-transform"
    assert scaffold.contract_snapshot.workflow_id == "lm8i-gh-affine-scalar-transform"
    assert scaffold.contract_snapshot.normalized_contract["workflow_id"] == "lm8i-gh-affine-scalar-transform"
    assert scaffold.compile_record.workflow_id == "lm8i-gh-affine-scalar-transform"
    assert scaffold.compile_record.compiler_id == "lm8i.script_local_affine_scaffold:v1"
    assert scaffold.compile_record.provider_id == "lm8i.script_local_provider:v1"

    rendered = json.dumps(
        {
            "summary": summary,
            "contract": scaffold.contract_snapshot.normalized_contract,
            "compile_record": {
                "workflow_id": scaffold.compile_record.workflow_id,
                "compiler_id": scaffold.compile_record.compiler_id,
                "provider_id": scaffold.compile_record.provider_id,
            },
        },
        sort_keys=True,
        default=str,
    ).casefold()
    assert "lm8h" not in rendered


def test_create_affine_fixture_uses_lm8i_nicknames_and_labels():
    executor = FakeToolExecutor(_fixture_tool_responses())
    fixture = _run(PROBE._create_affine_fixture(executor))

    assert fixture["visible_receipt"]["scalar_anchor"]["editable_value_contract"][
        "label"
    ] == "LM8I_Editable"
    assert fixture["receipt"]["scalar_anchor"]["editable_value_contract"][
        "label"
    ] == "LM8I_Editable"
    assert executor.calls[2:5] == [
        (
            "gh_create_slider",
            {"nickname": "LM8I_Editable", "min": 0, "max": 10, "value": 2.0, "x": 20, "y": 80},
        ),
        (
            "gh_create_slider",
            {"nickname": "LM8I_Factor", "min": 0, "max": 10, "value": 2.0, "x": 20, "y": 180},
        ),
        (
            "gh_create_slider",
            {"nickname": "LM8I_Offset", "min": 0, "max": 10, "value": 1.5, "x": 20, "y": 280},
        ),
    ]
    rendered = json.dumps(fixture, sort_keys=True, default=str).casefold()
    assert "lm8h" not in rendered


def _pass1_missing_row(excerpt, *, sha="sha256:abc"):
    return {
        "status": "pass1_decision_invalid",
        "failure_reason": "pass1_missing_action_id",
        "pass1_content_excerpt": excerpt,
        "pass1_content_sha256": sha,
    }


def test_support_eligibility_accepts_exact_skeletal_action_request_excerpt():
    result = PROBE._publication_support_eligibility(
        _pass1_missing_row(SKELETAL_PASS1)
    )

    assert result == {
        "support_eligible": True,
        "support_not_attempted_reason": None,
        "previous_response_kind": "action_request",
        "previous_response_excerpt": SKELETAL_PASS1,
        "previous_response_sha256": "sha256:abc",
    }


@pytest.mark.parametrize(
    ("excerpt", "reason"),
    [
        ('{"kind":"action_reques', "pass1_excerpt_not_exact_skeletal_json"),
        ('{"kind":"action_request"}', "pass1_excerpt_not_exact_skeletal_json"),
        (' {"kind": "action_request"}', "pass1_excerpt_not_exact_skeletal_json"),
        ('{"kind": "action_request"} ', "pass1_excerpt_not_exact_skeletal_json"),
        ('{"kind": "observation", "kind": "action_request"}', "pass1_excerpt_not_exact_skeletal_json"),
        ('{"kind":"action_request","action_id":""}', "pass1_excerpt_not_exact_skeletal_json"),
        ('{"kind":"action_request","action_id":"wrong"}', "pass1_excerpt_not_exact_skeletal_json"),
        ('{"kind":"action_request","input":{"value":3.0}}', "pass1_excerpt_not_exact_skeletal_json"),
        ('{"kind":"observation"}', "pass1_excerpt_not_exact_skeletal_json"),
        ("not json", "pass1_excerpt_not_exact_skeletal_json"),
    ],
)
def test_support_eligibility_rejects_non_exact_excerpts(excerpt, reason):
    result = PROBE._publication_support_eligibility(_pass1_missing_row(excerpt))

    assert result["support_eligible"] is False
    assert result["support_not_attempted_reason"] == reason


def test_support_eligibility_rejects_missing_pass1_hash():
    result = PROBE._publication_support_eligibility(
        _pass1_missing_row(SKELETAL_PASS1, sha="")
    )

    assert result["support_eligible"] is False
    assert result["support_not_attempted_reason"] == "pass1_content_sha256_missing"


def test_support_eligibility_rejects_wrong_status_or_failure_reason():
    wrong_status = PROBE._publication_support_eligibility(
        {
            "status": "published",
            "failure_reason": None,
            "pass1_content_excerpt": SKELETAL_PASS1,
            "pass1_content_sha256": "sha256:abc",
        }
    )
    wrong_reason = PROBE._publication_support_eligibility(
        {
            "status": "pass1_decision_invalid",
            "failure_reason": "pass1_unknown_kind",
            "pass1_content_excerpt": SKELETAL_PASS1,
            "pass1_content_sha256": "sha256:abc",
        }
    )

    assert wrong_status["support_eligible"] is False
    assert wrong_status["support_not_attempted_reason"] == (
        "first_publication_not_exact_skeletal_missing_action_id"
    )
    assert wrong_reason["support_eligible"] is False
    assert wrong_reason["support_not_attempted_reason"] == (
        "first_publication_not_exact_skeletal_missing_action_id"
    )


def test_publication_support_context_is_bounded_and_contains_no_authority_leaks():
    row = _pass1_missing_row(SKELETAL_PASS1, sha="sha256:pass1")

    context = PROBE._publication_support_context(row, excerpt_chars=1200)
    rendered = json.dumps(context, sort_keys=True)

    assert context["packet_id"] == "lm8i_publication_support_context"
    assert context["kind"] == "publication_support"
    assert context["fields"]["support_reason"] == "previous_pass1_missing_action_id"
    assert context["fields"]["previous_response_kind"] == "action_request"
    assert context["fields"]["previous_response_excerpt"] == SKELETAL_PASS1
    assert context["fields"]["previous_response_sha256"] == "sha256:pass1"
    assert context["fields"]["required_action_id"] == "draft_gh_set_value_params"
    assert context["fields"]["pass1_decision_required_fields_if_acting"] == [
        "kind",
        "action_id",
    ]
    assert "3.0" not in rendered
    assert "EDITABLE-GUID-1" not in rendered
    assert '"gh_set_value"' not in rendered
    assert '"tool"' not in rendered
    assert '"tool_name"' not in rendered
    assert "gh_edit" not in rendered
    assert "topology" not in rendered.casefold()


def test_publication_support_context_refuses_ineligible_row():
    with pytest.raises(ValueError, match="support_context_requires_exact_eligibility"):
        PROBE._publication_support_context(
            _pass1_missing_row('{"kind":"action_request","action_id":""}'),
            excerpt_chars=1200,
        )


def test_support_payload_adds_second_knowledge_packet_without_changing_allowed_action():
    graph = PROBE._graph_from_affine_receipt(
        _run(PROBE._create_affine_fixture(FakeToolExecutor(_fixture_tool_responses())))["receipt"]
    )
    runtime = PROBE._affine_runtime_context(
        graph=graph,
        workflow_contract_payload=PROBE._affine_scalar_contract_payload(),
        convention_packets=(),
    )
    support_context = PROBE._publication_support_context(
        _pass1_missing_row(SKELETAL_PASS1, sha="sha256:pass1"),
        excerpt_chars=1200,
    )

    payload = PROBE._build_local_turn_payload(
        graph=graph,
        packet=runtime["packet"],
        worker_visible=runtime["worker_visible"],
        publication_support_context=support_context,
    )

    knowledge = payload["context"]["knowledge"]
    packets_by_id = {packet["packet_id"]: packet for packet in knowledge}
    support = packets_by_id["lm8i_publication_support_context"]

    assert "gh_affine_scalar_transform_evidence" in packets_by_id
    assert support["kind"] == "publication_support"
    assert support["content"]["required_action_id"] == "draft_gh_set_value_params"
    assert support["content"]["previous_response_sha256"] == "sha256:pass1"
    assert payload["context"]["allowed_actions"] == [
        {
            "action_id": "draft_gh_set_value_params",
            "kind": "stage_params",
            "description": "Draft parameters for setting the trusted editable GH scalar value.",
            "input_schema": {
                "type": "object",
                "required": ["value"],
                "properties": {"value": {"type": "number"}},
                "additionalProperties": False,
            },
        }
    ]
    rendered = json.dumps(payload, sort_keys=True)
    support_rendered = json.dumps(support, sort_keys=True)
    assert "3.0" not in rendered
    assert "EDITABLE-GUID-1" not in rendered
    assert '"gh_set_value"' not in support_rendered
    assert '"tool"' not in support_rendered
    assert '"tool_name"' not in support_rendered


def test_run_probe_supports_exact_skeletal_pass1_then_accepts(tmp_path):
    executor = FakeToolExecutor(_fixture_responses_for_success())
    captured_payloads = []
    publications = [_pass1_missing_publication(), _published_action(3.0)]

    def fake_publication_runner(payload, **_kwargs):
        captured_payloads.append(payload)
        return publications.pop(0)

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=fake_publication_runner,
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    rows = json.loads(
        (run_dir / "worker_publication_rows.json").read_text(encoding="utf-8")
    )
    final_row = json.loads(
        (run_dir / "worker_publication_row.json").read_text(encoding="utf-8")
    )
    support_context = json.loads(
        (run_dir / "publication_support_context.json").read_text(encoding="utf-8")
    )
    worker_action = json.loads(
        (run_dir / "worker_action.json").read_text(encoding="utf-8")
    )

    assert len(captured_payloads) == 2
    assert decision["decision"] == "accepted"
    assert decision["reason"] == "verify_scalar_output_succeeded"
    assert decision["publication_support_attempted"] is True
    assert decision["publication_support_count"] == 1
    assert decision["support_eligible"] is True
    assert decision["first_publication_status"] == "pass1_decision_invalid"
    assert decision["first_publication_failure_reason"] == "pass1_missing_action_id"
    assert decision["final_publication_status"] == "published"
    assert decision["final_worker_response_kind"] == "action_request"
    assert rows[0]["turn_index"] == 0
    assert rows[0]["turn_role"] == "initial"
    assert rows[0]["publication_support_context_present"] is False
    assert rows[1]["turn_index"] == 1
    assert rows[1]["turn_role"] == "publication_support"
    assert rows[1]["publication_support_context_present"] is True
    assert final_row == rows[1]["row"]
    assert support_context["fields"]["previous_response_sha256"] == "sha256:pass1"
    assert worker_action["input"] == {"value": 3.0}
    assert "lm8i_publication_support_context" in json.dumps(
        captured_payloads[1]["context"]["knowledge"],
        sort_keys=True,
    )


def test_default_settle_path_preserves_tool_tail_and_verify_artifact_shape(tmp_path):
    executor = FakeToolExecutor(_fixture_responses_for_success())
    run_dir = PROBE._run_probe(
        model=PROBE.DEFAULT_MODEL,
        endpoint=PROBE.DEFAULT_ENDPOINT,
        temperature=PROBE.DEFAULT_TEMPERATURE,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *_args, **_kwargs: _published_action(3.0),
    )

    assert [name for name, _ in executor.calls][-3:] == [
        "gh_set_value",
        "gh_solve",
        "gh_inspect_output",
    ]
    assert not (run_dir / "readiness_wait_summary.json").exists()
    verify = json.loads(
        (run_dir / "verify_scalar_output_summary.json").read_text()
    )
    assert "verifier_profile" not in verify
    assert "settle_read_count" not in verify


def test_managed_receipt_path_waits_then_reads_once_with_bounded_artifacts(tmp_path):
    executor = FakeToolExecutor(_managed_success_responses())
    run_dir = PROBE._run_probe(
        model=PROBE.DEFAULT_MODEL,
        endpoint=PROBE.DEFAULT_ENDPOINT,
        temperature=PROBE.DEFAULT_TEMPERATURE,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        verifier_profile=PROBE.MANAGED_VERIFIER_PROFILE,
        tool_executor=executor,
        publication_runner=lambda *_args, **_kwargs: _published_action(3.0),
    )

    tool_tail = [name for name, _ in executor.calls][-3:]
    assert tool_tail == [
        "gh_set_value",
        "gh_wait_for_solve_readiness",
        "gh_inspect_output",
    ]
    assert "gh_solve" not in tool_tail
    wait_call = executor.calls[-2]
    inspect_call = executor.calls[-1]
    assert wait_call[1] == {
        "readiness_receipt_id": RECEIPT_ID,
        "timeout_ms": 10_000,
    }
    assert inspect_call[1]["readiness_receipt_id"] == RECEIPT_ID

    decision = json.loads((run_dir / "decision.json").read_text())
    assert decision["decision"] == "accepted"
    assert decision["reason"] == "verify_scalar_output_succeeded"

    mutation = json.loads((run_dir / "live_set_value_summary.json").read_text())
    wait = json.loads((run_dir / "readiness_wait_summary.json").read_text())
    verify = json.loads(
        (run_dir / "verify_scalar_output_summary.json").read_text()
    )

    managed_mutation = mutation["managed_mutation"]
    assert managed_mutation == {
        "schema": "rook.lm8l_managed_mutation_summary:v1",
        "receipt_schema": "rook.gh_solve_readiness_receipt:v1",
        "receipt_status": "pending",
        "receipt_id_sha256": PROBE._receipt_id_sha256(RECEIPT_ID),
        "document_session_id": "session-1",
        "mutation_epoch": 13,
        "solution_run_epoch": None,
        "completed_solution_run_epoch": 41,
    }
    assert wait == {
        "schema": "rook.lm8l_readiness_wait_summary:v1",
        "tool_name": "gh_wait_for_solve_readiness",
        "requested_timeout_ms": 10_000,
        "readiness_wait_count": 1,
        "wait_status": "ready",
        "receipt_schema": "rook.gh_solve_readiness_receipt:v1",
        "receipt_status": "ready",
        "receipt_id_sha256": PROBE._receipt_id_sha256(RECEIPT_ID),
        "document_session_id": "session-1",
        "mutation_epoch": 13,
        "solution_run_epoch": 42,
        "completed_solution_run_epoch": 42,
    }
    assert verify == {
        "schema": "rook.lm8l_fenced_output_verification_summary:v1",
        "tool_name": "gh_inspect_output",
        "component_guid_sha256": PROBE._guid_sha256("ADDITION-GUID-1"),
        "verifier_profile": PROBE.MANAGED_VERIFIER_PROFILE,
        "readiness_wait_timeout_ms": 10_000,
        "readiness_wait_count": 1,
        "fenced_output_read_count": 1,
        "settle_read_count": 0,
        "readiness_fenced": True,
        "expected_output_value": 7.5,
        "observed_output_value": 7.5,
        "tolerance": PROBE.SCALAR_TOLERANCE,
        "matched": True,
        "reported_success": True,
        "receipt_id_sha256": PROBE._receipt_id_sha256(RECEIPT_ID),
        "document_session_id": "session-1",
        "mutation_epoch": 13,
        "solution_run_epoch": 42,
        "completed_solution_run_epoch": 42,
    }
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", managed_mutation["receipt_id_sha256"])
    assert wait["receipt_id_sha256"] == managed_mutation["receipt_id_sha256"]
    assert verify["receipt_id_sha256"] == managed_mutation["receipt_id_sha256"]
    assert wait["document_session_id"] == managed_mutation["document_session_id"]
    assert verify["document_session_id"] == managed_mutation["document_session_id"]
    assert wait["mutation_epoch"] == managed_mutation["mutation_epoch"]
    assert verify["mutation_epoch"] == managed_mutation["mutation_epoch"]
    assert verify["solution_run_epoch"] == wait["solution_run_epoch"]
    assert verify["completed_solution_run_epoch"] == wait["completed_solution_run_epoch"]
    assert wait["solution_run_epoch"] > managed_mutation["completed_solution_run_epoch"]
    assert decision["managed_verifier"] == {
        "schema": "rook.lm8l_managed_verifier_decision:v1",
        "verifier_profile": PROBE.MANAGED_VERIFIER_PROFILE,
        "verifier_mechanism": PROBE.VERIFIER_MECHANISM,
        "fixture_readiness_profile": PROBE.FIXTURE_READINESS_PROFILE,
        "readiness_wait_timeout_ms": 10_000,
        "readiness_wait_count": 1,
        "fenced_output_read_count": 1,
        "settle_read_count": 0,
        "failed_invariants": [],
    }

    for artifact in (mutation, wait, verify, decision):
        assert RECEIPT_ID not in json.dumps(artifact, sort_keys=True)


@pytest.mark.parametrize(
    ("receipt_status", "receipt_reason", "expected_reason"),
    [
        ("solver_locked", "solver_locked", "readiness_receipt_solver_locked"),
        ("unknown", "scheduling_unknown", "readiness_receipt_unknown"),
        ("unknown", "receipt_expired", "readiness_receipt_expired"),
    ],
)
def test_managed_terminal_mutation_receipt_stops_before_wait(
    tmp_path, receipt_status, receipt_reason, expected_reason
):
    responses = _managed_success_responses()
    responses["gh_set_value"]["data"]["solve_readiness_receipt"] = _receipt(
        receipt_status,
        solution_run_epoch=None,
        completed_solution_run_epoch=41,
        reason=receipt_reason,
    )

    run_dir, executor, decision = _run_managed_probe(tmp_path, responses)

    assert decision["decision"] == "rejected"
    assert decision["phase"] == "verifier_readiness"
    assert decision["reason"] == expected_reason
    assert decision["managed_verifier"]["readiness_wait_count"] == 0
    assert decision["managed_verifier"]["fenced_output_read_count"] == 0
    assert decision["managed_verifier"]["settle_read_count"] == 0
    names = [name for name, _ in executor.calls]
    assert names.count("gh_wait_for_solve_readiness") == 0
    assert names.count("gh_inspect_output") == 1
    mutation = json.loads(
        (run_dir / "live_set_value_summary.json").read_text(encoding="utf-8")
    )
    assert mutation["managed_mutation"]["receipt_status"] == receipt_status
    assert RECEIPT_ID not in json.dumps(mutation, sort_keys=True)


@pytest.mark.parametrize(
    ("wait_result", "expected_reason"),
    [
        (
            {
                "success": True,
                "data": {
                    "schema": "rook.gh_solve_readiness_wait_result:v1",
                    "wait_status": "timeout",
                    "receipt": _receipt(
                        "pending",
                        solution_run_epoch=None,
                        completed_solution_run_epoch=41,
                    ),
                },
            },
            "readiness_wait_timeout",
        ),
        (
            {
                "success": True,
                "data": {
                    "schema": "rook.gh_solve_readiness_wait_result:v1",
                    "wait_status": "terminal",
                    "receipt": _receipt(
                        "superseded",
                        solution_run_epoch=None,
                        completed_solution_run_epoch=41,
                    ),
                },
            },
            "readiness_receipt_superseded",
        ),
        (
            {
                "success": False,
                "data": {"error": "readiness_receipt_stale_solution_run"},
            },
            "readiness_receipt_stale_solution_run",
        ),
        (
            {
                "success": True,
                "data": {
                    "schema": "rook.gh_solve_readiness_wait_result:v1",
                    "wait_status": "terminal",
                    "receipt": _receipt(
                        "document_replaced",
                        solution_run_epoch=None,
                        completed_solution_run_epoch=41,
                    ),
                },
            },
            "readiness_receipt_document_replaced",
        ),
        (
            {
                "success": True,
                "data": {
                    "schema": "rook.gh_solve_readiness_wait_result:v1",
                    "wait_status": "terminal",
                    "receipt": _receipt(
                        "solver_locked",
                        solution_run_epoch=None,
                        completed_solution_run_epoch=41,
                    ),
                },
            },
            "readiness_receipt_solver_locked",
        ),
        (
            {
                "success": True,
                "data": {
                    "schema": "rook.gh_solve_readiness_wait_result:v1",
                    "wait_status": "terminal",
                    "receipt": _receipt(
                        "unknown",
                        solution_run_epoch=None,
                        completed_solution_run_epoch=41,
                    ),
                },
            },
            "readiness_receipt_unknown",
        ),
        (
            {
                "success": True,
                "data": {
                    "schema": "rook.gh_solve_readiness_wait_result:v1",
                    "wait_status": "terminal",
                    "receipt": _receipt(
                        "unknown",
                        solution_run_epoch=None,
                        completed_solution_run_epoch=41,
                        reason="receipt_expired",
                    ),
                },
            },
            "readiness_receipt_expired",
        ),
        (
            {
                "success": False,
                "data": {
                    "error": "readiness_receipt_not_found_or_evicted_or_process_restarted"
                },
            },
            "readiness_receipt_not_found_or_evicted_or_process_restarted",
        ),
        (
            {
                "success": False,
                "data": {"error": "readiness_wait_already_active"},
            },
            "readiness_wait_already_active",
        ),
    ],
)
def test_managed_terminal_wait_outcome_stops_before_fenced_read(
    tmp_path, wait_result, expected_reason
):
    responses = _managed_success_responses()
    responses["gh_wait_for_solve_readiness"] = wait_result

    run_dir, executor, decision = _run_managed_probe(tmp_path, responses)

    assert decision["decision"] == "rejected"
    assert decision["phase"] == "verifier_readiness"
    assert decision["reason"] == expected_reason
    assert decision["managed_verifier"]["readiness_wait_count"] == 1
    assert decision["managed_verifier"]["fenced_output_read_count"] == 0
    assert decision["managed_verifier"]["settle_read_count"] == 0
    names = [name for name, _ in executor.calls]
    assert names.count("gh_wait_for_solve_readiness") == 1
    assert names.count("gh_inspect_output") == 1
    wait = json.loads(
        (run_dir / "readiness_wait_summary.json").read_text(encoding="utf-8")
    )
    assert wait["normalized_reason"] == expected_reason
    assert RECEIPT_ID not in json.dumps(wait, sort_keys=True)


def test_managed_fenced_read_product_failure_is_terminal_without_follow_up(tmp_path):
    responses = _managed_success_responses()
    responses["gh_inspect_output"][1] = {
        "success": False,
        "data": {"error": "readiness_receipt_not_ready"},
    }

    _run_dir, executor, decision = _run_managed_probe(tmp_path, responses)

    assert decision["decision"] == "rejected"
    assert decision["phase"] == "verifier_readiness"
    assert decision["reason"] == "readiness_receipt_not_ready"
    assert decision["managed_verifier"]["readiness_wait_count"] == 1
    assert decision["managed_verifier"]["fenced_output_read_count"] == 1
    assert decision["managed_verifier"]["settle_read_count"] == 0
    names = [name for name, _ in executor.calls]
    assert names.count("gh_wait_for_solve_readiness") == 1
    assert names.count("gh_inspect_output") == 2


@pytest.mark.parametrize(
    ("case", "expected_failures"),
    [
        ("missing_receipt", ("mutation_receipt_missing",)),
        ("wrong_receipt_schema", ("mutation_receipt_schema_invalid",)),
        ("mutation_epoch_zero", ("mutation_epoch_not_positive",)),
        (
            "pending_solution_run_non_null",
            ("pending_solution_run_epoch_not_null",),
        ),
        (
            "pending_completed_run_missing",
            ("pending_completed_solution_run_epoch_invalid",),
        ),
        (
            "pending_completed_run_non_integer",
            ("pending_completed_solution_run_epoch_invalid",),
        ),
    ],
)
def test_managed_mutation_invariant_failure_stops_before_wait(
    tmp_path, case, expected_failures
):
    responses = _managed_success_responses()
    receipt = responses["gh_set_value"]["data"]["solve_readiness_receipt"]
    if case == "missing_receipt":
        del responses["gh_set_value"]["data"]["solve_readiness_receipt"]
    elif case == "wrong_receipt_schema":
        receipt["schema"] = "rook.gh_solve_readiness_receipt:v0"
    elif case == "mutation_epoch_zero":
        receipt["mutation_epoch"] = 0
    elif case == "pending_solution_run_non_null":
        receipt["solution_run_epoch"] = 42
    elif case == "pending_completed_run_missing":
        del receipt["completed_solution_run_epoch"]
    elif case == "pending_completed_run_non_integer":
        receipt["completed_solution_run_epoch"] = "41"

    _run_dir, executor, decision = _run_managed_probe(tmp_path, responses)

    _assert_managed_invariant_rejection(
        decision,
        expected_failures=expected_failures,
        readiness_wait_count=0,
        fenced_output_read_count=0,
    )
    names = [name for name, _ in executor.calls]
    assert names.count("gh_wait_for_solve_readiness") == 0
    assert names.count("gh_inspect_output") == 1


@pytest.mark.parametrize(
    ("case", "expected_failures"),
    [
        ("ready_not_advanced", ("post_mutation_solution_run_not_advanced",)),
        ("receipt_hash_mismatch", ("receipt_id_sha256_mismatch",)),
        ("session_mismatch", ("document_session_id_mismatch",)),
        ("mutation_epoch_mismatch", ("mutation_epoch_mismatch",)),
        (
            "wait_completed_run_mismatch",
            ("wait_completed_solution_run_mismatch",),
        ),
        (
            "wait_completed_run_boolean",
            ("wait_completed_solution_run_mismatch",),
        ),
        ("mutation_epoch_boolean", ("mutation_epoch_mismatch",)),
        ("wrong_wait_receipt_schema", ("wait_receipt_schema_invalid",)),
    ],
)
def test_managed_wait_invariant_failure_stops_before_fenced_read(
    tmp_path, case, expected_failures
):
    responses = _managed_success_responses()
    receipt = responses["gh_wait_for_solve_readiness"]["data"]["receipt"]
    if case == "ready_not_advanced":
        receipt["solution_run_epoch"] = 41
        receipt["completed_solution_run_epoch"] = 41
    elif case == "receipt_hash_mismatch":
        receipt["receipt_id"] = "different-receipt"
    elif case == "session_mismatch":
        receipt["document_session_id"] = "session-2"
    elif case == "mutation_epoch_mismatch":
        receipt["mutation_epoch"] = 14
    elif case == "wait_completed_run_mismatch":
        receipt["completed_solution_run_epoch"] = 43
    elif case == "wait_completed_run_boolean":
        responses["gh_set_value"]["data"]["solve_readiness_receipt"][
            "completed_solution_run_epoch"
        ] = 0
        receipt["solution_run_epoch"] = 1
        receipt["completed_solution_run_epoch"] = True
    elif case == "mutation_epoch_boolean":
        responses["gh_set_value"]["data"]["solve_readiness_receipt"][
            "mutation_epoch"
        ] = 1
        receipt["mutation_epoch"] = True
    elif case == "wrong_wait_receipt_schema":
        receipt["schema"] = "rook.gh_solve_readiness_receipt:v0"

    _run_dir, executor, decision = _run_managed_probe(tmp_path, responses)

    _assert_managed_invariant_rejection(
        decision,
        expected_failures=expected_failures,
        readiness_wait_count=1,
        fenced_output_read_count=0,
    )
    names = [name for name, _ in executor.calls]
    assert names.count("gh_wait_for_solve_readiness") == 1
    assert names.count("gh_inspect_output") == 1


@pytest.mark.parametrize(
    ("case", "expected_failures"),
    [
        ("receipt_hash_mismatch", ("receipt_id_sha256_mismatch",)),
        ("session_mismatch", ("document_session_id_mismatch",)),
        ("mutation_epoch_mismatch", ("mutation_epoch_mismatch",)),
        ("read_solution_run_mismatch", ("read_solution_run_mismatch",)),
        (
            "read_completed_run_mismatch",
            ("read_completed_solution_run_mismatch",),
        ),
        ("read_solution_run_boolean", ("read_solution_run_mismatch",)),
        (
            "read_completed_run_boolean",
            ("read_completed_solution_run_mismatch",),
        ),
        ("mutation_epoch_boolean", ("mutation_epoch_mismatch",)),
        ("readiness_fenced_false", ("readiness_fenced_not_true",)),
        ("readiness_fenced_missing", ("readiness_fenced_not_true",)),
    ],
)
def test_matching_scalar_cannot_override_fenced_read_provenance_failure(
    tmp_path, case, expected_failures
):
    responses = _managed_success_responses()
    read = responses["gh_inspect_output"][1]["data"]
    if case == "receipt_hash_mismatch":
        read["readiness_receipt_id"] = "different-receipt"
    elif case == "session_mismatch":
        read["document_session_id"] = "session-2"
    elif case == "mutation_epoch_mismatch":
        read["mutation_epoch"] = 14
    elif case == "read_solution_run_mismatch":
        read["solution_run_epoch"] = 43
    elif case == "read_completed_run_mismatch":
        read["completed_solution_run_epoch"] = 43
    elif case == "read_solution_run_boolean":
        responses["gh_set_value"]["data"]["solve_readiness_receipt"][
            "completed_solution_run_epoch"
        ] = 0
        wait = responses["gh_wait_for_solve_readiness"]["data"]["receipt"]
        wait["solution_run_epoch"] = 1
        wait["completed_solution_run_epoch"] = 1
        read["solution_run_epoch"] = True
        read["completed_solution_run_epoch"] = 1
    elif case == "read_completed_run_boolean":
        responses["gh_set_value"]["data"]["solve_readiness_receipt"][
            "completed_solution_run_epoch"
        ] = 0
        wait = responses["gh_wait_for_solve_readiness"]["data"]["receipt"]
        wait["solution_run_epoch"] = 1
        wait["completed_solution_run_epoch"] = 1
        read["solution_run_epoch"] = 1
        read["completed_solution_run_epoch"] = True
    elif case == "mutation_epoch_boolean":
        responses["gh_set_value"]["data"]["solve_readiness_receipt"][
            "mutation_epoch"
        ] = 1
        responses["gh_wait_for_solve_readiness"]["data"]["receipt"][
            "mutation_epoch"
        ] = 1
        read["mutation_epoch"] = True
    elif case == "readiness_fenced_false":
        read["readiness_fenced"] = False
    elif case == "readiness_fenced_missing":
        del read["readiness_fenced"]

    _run_dir, executor, decision = _run_managed_probe(tmp_path, responses)

    _assert_managed_invariant_rejection(
        decision,
        expected_failures=expected_failures,
        readiness_wait_count=1,
        fenced_output_read_count=1,
    )
    names = [name for name, _ in executor.calls]
    assert names.count("gh_wait_for_solve_readiness") == 1
    assert names.count("gh_inspect_output") == 2


def test_managed_scalar_mismatch_with_correct_provenance_stays_scalar_failure(tmp_path):
    responses = _managed_success_responses()
    responses["gh_inspect_output"][1]["data"]["preview"] = ["7.4"]

    _run_dir, executor, decision = _run_managed_probe(tmp_path, responses)

    assert decision["decision"] == "rejected"
    assert decision["phase"] == "verify_scalar_output"
    assert decision["reason"] == "verify_scalar_output_failed"
    assert decision["managed_verifier"]["failed_invariants"] == [
        "fenced_output_scalar"
    ]
    assert decision["managed_verifier"]["readiness_wait_count"] == 1
    assert decision["managed_verifier"]["fenced_output_read_count"] == 1
    assert decision["managed_verifier"]["settle_read_count"] == 0
    names = [name for name, _ in executor.calls]
    assert names.count("gh_wait_for_solve_readiness") == 1
    assert names.count("gh_inspect_output") == 2


@pytest.mark.parametrize(
    "publication",
    [
        _pass1_missing_publication('{"kind":"action_request","action_id":""}'),
        _pass1_missing_publication('{"kind":"action_request","action_id":"wrong"}'),
        _pass1_missing_publication('{"kind":"action_request","input":{"value":3.0}}'),
        _pass1_missing_publication('{"kind":"action_reques'),
    ],
)
def test_run_probe_does_not_support_non_exact_pass1_rows(tmp_path, publication):
    executor = FakeToolExecutor(_fixture_responses_for_success())
    calls = []

    def fake_publication_runner(payload, **_kwargs):
        calls.append(payload)
        return publication

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=fake_publication_runner,
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    rows = json.loads(
        (run_dir / "worker_publication_rows.json").read_text(encoding="utf-8")
    )
    final_row = json.loads(
        (run_dir / "worker_publication_row.json").read_text(encoding="utf-8")
    )

    assert len(calls) == 1
    assert decision["decision"] == "publication_failed"
    assert decision["publication_support_attempted"] is False
    assert decision["publication_support_count"] == 0
    assert decision["support_eligible"] is False
    assert decision["support_not_attempted_reason"] in {
        "pass1_excerpt_not_exact_skeletal_json",
        "first_publication_not_exact_skeletal_missing_action_id",
    }
    assert len(rows) == 1
    assert rows[0]["turn_role"] == "initial"
    assert final_row == rows[0]["row"]
    assert not (run_dir / "publication_support_context.json").exists()
    assert not (run_dir / "worker_action.json").exists()


def test_run_probe_support_repeat_missing_action_id_remains_publication_failed(tmp_path):
    executor = FakeToolExecutor(_fixture_responses_for_success())
    publications = [_pass1_missing_publication(), _pass1_missing_publication()]

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *_args, **_kwargs: publications.pop(0),
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    rows = json.loads(
        (run_dir / "worker_publication_rows.json").read_text(encoding="utf-8")
    )

    assert decision["decision"] == "publication_failed"
    assert decision["reason"] == "pass1_decision_invalid:pass1_missing_action_id"
    assert decision["publication_support_attempted"] is True
    assert decision["publication_support_count"] == 1
    assert len(rows) == 2
    assert not (run_dir / "worker_action.json").exists()


def test_run_probe_does_not_write_raw_pass1_transcript_artifact(tmp_path):
    executor = FakeToolExecutor(_fixture_responses_for_success())
    publications = [_pass1_missing_publication(), _published_action(3.0)]

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *_args, **_kwargs: publications.pop(0),
    )

    artifact_names = {path.name for path in run_dir.iterdir()}
    forbidden_names = {
        "pass1_raw.txt",
        "pass1_provider_output.txt",
        "worker_pass1_transcript.txt",
        "raw_provider_output.txt",
    }
    assert artifact_names.isdisjoint(forbidden_names)
    assert all("transcript" not in name for name in artifact_names)
    rows = json.loads((run_dir / "worker_publication_rows.json").read_text(encoding="utf-8"))
    assert rows[0]["row"]["pass1_content_excerpt"] == SKELETAL_PASS1
    assert rows[0]["row"]["pass1_content_sha256"] == "sha256:pass1"


def test_run_probe_support_and_prepublication_artifacts_do_not_contain_hidden_value(
    tmp_path,
):
    executor = FakeToolExecutor(_fixture_responses_for_success())
    publications = [_pass1_missing_publication(), _published_action(3.0)]

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *_args, **_kwargs: publications.pop(0),
    )

    forbidden_pre_publication = [
        "scalar_sources.json",
        "acceptance_criteria_packet.json",
        "worker_visible_acceptance_criteria.json",
        "worker_request_payload.json",
        "publication_support_context.json",
    ]
    for filename in forbidden_pre_publication:
        rendered = (run_dir / filename).read_text(encoding="utf-8")
        assert "3.0" not in rendered

    allowed_post_publication = [
        "worker_publication_rows.json",
        "worker_publication_row.json",
        "worker_action.json",
        "live_set_value_summary.json",
        "decision.json",
    ]
    assert any(
        "3.0" in (run_dir / filename).read_text(encoding="utf-8")
        for filename in allowed_post_publication
    )
    rows = json.loads((run_dir / "worker_publication_rows.json").read_text(encoding="utf-8"))
    assert "3.0" not in json.dumps(rows[0], sort_keys=True)
    assert "3.0" in json.dumps(rows[1], sort_keys=True)


def test_lm8i_never_autofills_missing_action_id(tmp_path):
    executor = FakeToolExecutor(_fixture_responses_for_success())
    publications = [_pass1_missing_publication(), _pass1_missing_publication()]

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *_args, **_kwargs: publications.pop(0),
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    rows = json.loads((run_dir / "worker_publication_rows.json").read_text(encoding="utf-8"))

    assert decision["decision"] == "publication_failed"
    assert decision["reason"] == "pass1_decision_invalid:pass1_missing_action_id"
    assert all(row["row"].get("pass1_action_id") in {None, ""} for row in rows)
    assert not (run_dir / "worker_action.json").exists()
    assert not (run_dir / "live_set_value_summary.json").exists()


def test_run_probe_first_publication_safety_failure_includes_support_metadata(tmp_path):
    executor = FakeToolExecutor(_fixture_responses_for_success())
    publication = FakePublication(
        row={
            "status": "pass1_decision_invalid",
            "failure_reason": "pass1_missing_action_id",
            "pass1_content_excerpt": SKELETAL_PASS1,
            "pass1_content_sha256": "sha256:pass1",
            "observation_action_intent_anomaly": False,
        },
        response_payload={
            "kind": "action_request",
            "rationale": "EDITABLE-GUID-1",
        },
    )

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *_args, **_kwargs: publication,
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    rows = json.loads((run_dir / "worker_publication_rows.json").read_text(encoding="utf-8"))
    final_row = json.loads((run_dir / "worker_publication_row.json").read_text(encoding="utf-8"))
    rows_rendered = json.dumps(rows, sort_keys=True)
    final_row_rendered = json.dumps(final_row, sort_keys=True)

    assert decision["decision"] == "publication_failed"
    assert decision["reason"] == "worker_publication_guid_leak"
    assert decision["publication_support_attempted"] is False
    assert decision["publication_support_count"] == 0
    assert decision["support_eligible"] is True
    assert decision["support_not_attempted_reason"] is None
    assert decision["first_publication_status"] == "pass1_decision_invalid"
    assert decision["first_publication_failure_reason"] == "pass1_missing_action_id"
    assert decision["final_publication_status"] == "pass1_decision_invalid"
    assert decision["final_publication_failure_reason"] == "pass1_missing_action_id"
    assert len(rows) == 1
    assert rows[0]["turn_role"] == "initial"
    assert rows[0]["row"]["row_redacted"] is True
    assert rows[0]["row"]["redaction_reason"] == "worker_publication_guid_leak"
    assert rows[0]["row"]["pass1_content_sha256"] == "sha256:pass1"
    assert final_row == rows[0]["row"]
    assert "EDITABLE-GUID-1" not in rows_rendered
    assert "EDITABLE-GUID-1" not in final_row_rendered
    assert not (run_dir / "worker_action.json").exists()


def test_run_probe_support_turn_safety_failure_writes_support_row_and_final_row(tmp_path):
    executor = FakeToolExecutor(_fixture_responses_for_success())
    publications = [
        _pass1_missing_publication(),
        FakePublication(
            row={
                "status": "published",
                "pass2_response_kind": "action_request",
                "observation_action_intent_anomaly": False,
            },
            response_payload={
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_gh_set_value_params",
                "rationale": "OFFSET-GUID-1",
                "input": {"value": 3.0},
            },
        ),
    ]

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *_args, **_kwargs: publications.pop(0),
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    rows = json.loads(
        (run_dir / "worker_publication_rows.json").read_text(encoding="utf-8")
    )
    final_row = json.loads(
        (run_dir / "worker_publication_row.json").read_text(encoding="utf-8")
    )

    assert decision["decision"] == "publication_failed"
    assert decision["reason"] == "worker_publication_guid_leak"
    assert decision["publication_support_attempted"] is True
    assert decision["publication_support_count"] == 1
    assert decision["support_eligible"] is True
    assert len(rows) == 2
    assert rows[0]["turn_index"] == 0
    assert rows[0]["turn_role"] == "initial"
    assert rows[1]["turn_index"] == 1
    assert rows[1]["turn_role"] == "publication_support"
    assert rows[1]["publication_support_context_present"] is True
    assert rows[1]["row"]["row_redacted"] is True
    assert rows[1]["row"]["redaction_reason"] == "worker_publication_guid_leak"
    assert rows[1]["row"]["response_kind"] == "action_request"
    assert "OFFSET-GUID-1" not in json.dumps(rows, sort_keys=True)
    assert "OFFSET-GUID-1" not in json.dumps(final_row, sort_keys=True)
    assert final_row == rows[1]["row"]
    assert decision["first_publication_status"] == "pass1_decision_invalid"
    assert decision["final_publication_status"] == "published"
    assert decision["final_worker_response_kind"] == "action_request"
    assert not (run_dir / "worker_action.json").exists()


def test_run_probe_does_not_write_worker_action_before_apply_accepts(tmp_path):
    executor = FakeToolExecutor(_fixture_responses_for_success())
    publications = [
        _pass1_missing_publication(),
        _published_action("bad scalar"),
    ]

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *_args, **_kwargs: publications.pop(0),
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))

    assert decision["decision"] == "rejected"
    assert decision["reason"].startswith("worker_action_apply_failed:")
    assert decision["publication_support_attempted"] is True
    assert not (run_dir / "worker_action.json").exists()
    assert not (run_dir / "live_set_value_summary.json").exists()


def test_run_probe_support_non_action_maps_to_worker_declined(tmp_path):
    executor = FakeToolExecutor(_fixture_responses_for_success())
    publications = [
        _pass1_missing_publication(),
        FakePublication(
            row={
                "status": "published",
                "pass2_response_kind": "observation",
                "observation_action_intent_anomaly": False,
            },
            response_payload={
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "observation",
                "message": "I will not act.",
                "data": None,
            },
        ),
    ]

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *_args, **_kwargs: publications.pop(0),
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))

    assert decision["decision"] == "worker_declined"
    assert decision["reason"] == "worker_observed"
    assert decision["publication_support_attempted"] is True
    assert decision["final_worker_response_kind"] == "observation"
    assert not (run_dir / "worker_action.json").exists()


def test_lm8i_source_does_not_import_lm8h_lm8g_repair_planner_retry_or_gh_edit_paths():
    source = inspect.getsource(PROBE)
    forbidden_import_or_call_fragments = (
        "lm8h_affine_scalar_depth_probe",
        "lm8g_scalar_transform_repeatability_probe",
        "lm6a_live_worker_splice_probe",
        "lm7e_model_authored_live_splice_probe",
        "planner_worker_contract_request",
        "workflow_validate",
        "--retry-clean-observation",
        '"gh_edit"',
        "'gh_edit'",
        "gh_update_script",
    )
    for fragment in forbidden_import_or_call_fragments:
        assert fragment not in source


def test_lm8i_source_does_not_contain_hidden_worker_value_literal():
    source = inspect.getsource(PROBE)
    assert "3.0" not in source
    assert "EXPECTED_WORKER_VALUE" not in source
    assert "set editable value to 3.0" not in source
    assert "use 3.0" not in source


def test_lm8i_does_not_modify_or_import_shared_publication_helper_for_support_policy():
    source = inspect.getsource(PROBE)
    assert "run_two_pass_worker_publication" in source
    assert "pass1_content_excerpt" in source
    assert "pass1_content_sha256" in source
    helper_source = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm_worker_two_pass_publication.py"
    ).read_text(encoding="utf-8")
    assert "lm8i_publication_support_context" not in helper_source
