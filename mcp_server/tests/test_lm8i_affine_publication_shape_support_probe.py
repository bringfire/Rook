from __future__ import annotations

import importlib.util
import inspect
import json
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
