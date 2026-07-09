from __future__ import annotations

import importlib.util
import inspect
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm8h_affine_scalar_depth_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm8h_affine_scalar_depth_probe",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()


def test_cli_defaults_are_canonical_affine_shape():
    args = PROBE._args([])

    assert args.model == "gemma4:12b-it-qat"
    assert args.endpoint == "http://localhost:11434/api/chat"
    assert args.temperature == 0
    assert args.timeout_s == 120
    assert args.excerpt_chars == 1200
    assert args.run_dir == "probe_runs"
    assert args.canonical_evidence is True


def test_cli_rejects_non_lm8h_surfaces():
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


def test_manifest_records_lm8h_identity():
    manifest = PROBE._manifest(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        canonical_evidence=True,
    )

    assert manifest["schema"] == "rook.lm8h_affine_scalar_depth_probe:v1"
    assert manifest["attempts"] == 1
    assert manifest["initial_editable_value"] == 2.0
    assert manifest["factor_value"] == 2.0
    assert manifest["offset_value"] == 1.5
    assert manifest["initial_observed_output"] == 5.5
    assert manifest["expected_output_value"] == 7.5
    assert manifest["projection_id"] == "editable_times_factor_plus_offset"
    assert manifest["worker_retry_enabled"] is False
    assert manifest["planner_model"] is None
    assert manifest["gh_edit_enabled"] is False


def test_new_run_dir_adds_suffix_on_same_second_collision(tmp_path: Path, monkeypatch):
    class FixedDateTime:
        @classmethod
        def now(cls, tz):
            return datetime(2026, 7, 8, 12, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(PROBE, "datetime", FixedDateTime)
    monkeypatch.setattr(PROBE, "_git_short_sha", lambda: "abc123")

    first = PROBE._new_run_dir(tmp_path)
    second = PROBE._new_run_dir(tmp_path)

    assert first.name == "lm8h-20260708T120000Z-abc123"
    assert second.name == "lm8h-20260708T120000Z-abc123-001"
    assert first.is_dir()
    assert second.is_dir()


def test_lm8h_source_does_not_import_lm8f_lm8g_repair_planner_retry_or_gh_edit_paths():
    source = inspect.getsource(PROBE)
    forbidden_import_or_call_fragments = (
        "lm8f_scalar_transform_depth_probe",
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


def test_lm8h_source_does_not_contain_hidden_worker_value_literal():
    assert "3.0" not in inspect.getsource(PROBE)


def test_lm8h_source_contains_hidden_expected_value_only_as_policy_or_test_oracle():
    source = inspect.getsource(PROBE)
    assert "3.0" not in source
    assert "EXPECTED_WORKER_VALUE" not in source
    assert "set editable value to 3.0" not in source
    assert "use 3.0" not in source


def test_lm8h_source_policy_markers_are_not_worker_visible_evidence():
    source = inspect.getsource(PROBE)
    for marker in (
        "PROBE_REPAIR_CODE",
        "A = 42.0",
        "BindStepSpec.base_params",
        "repair_same_component.bind.base_params",
    ):
        assert marker in source


def test_affine_source_routing_artifact_uses_canonical_route_ids():
    artifact = PROBE._affine_scalar_source_routing_artifact()
    route_ids = [item["route_id"] for item in artifact["routes"][0]["visible_sources"]]

    assert route_ids == [
        "affine_scalar_expected_output",
        "affine_scalar_factor_value",
        "affine_scalar_offset_value",
        "affine_scalar_projection",
        "affine_scalar_current_output",
        "affine_scalar_current_editable_value",
        "affine_scalar_editable_target_contract",
        "affine_scalar_set_value_convention",
    ]


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


def _published_action(value=3.0):
    return FakePublication(
        row={
            "status": "published",
            "pass2_response_kind": "action_request",
            "observation_action_intent_anomaly": False,
        },
        response_payload={
            "schema": "rook.local_worker_turn_response:v1",
            "kind": "action_request",
            "action_id": "draft_gh_set_value_params",
            "rationale": "Use the affine relationship to match the expected output.",
            "input": {"value": value},
        },
    )


def _published_action_with_payload(payload, *, row_overrides=None):
    row = {
        "status": "published",
        "pass2_response_kind": "action_request",
        "observation_action_intent_anomaly": False,
    }
    if row_overrides:
        row.update(row_overrides)
    return FakePublication(row=row, response_payload=payload)


def _run(coro):
    import asyncio

    return asyncio.run(coro)


def _library_result_for(name, guid, *, deprecated=False):
    return {
        "name": name,
        "nickName": "A*B" if name == "Multiplication" else "A+B",
        "category": "Maths",
        "guid": guid,
        "deprecated": deprecated,
    }


def _fixture_tool_responses(
    *,
    editable_value="2.0",
    factor_value="2.0",
    offset_value="1.5",
    observed_output="5.5",
):
    return {
        "gh_library": [
            {
                "success": True,
                "count": 1,
                "components": [_library_result_for("Multiplication", "MULTIPLY-PROXY-GUID")],
            },
            {
                "success": True,
                "count": 1,
                "components": [_library_result_for("Addition", "ADDITION-PROXY-GUID")],
            },
        ],
        "gh_create_slider": [
            {"success": True, "data": {"Created": True, "Guid": "EDITABLE-GUID-1", "NickName": "LM8H_Editable"}},
            {"success": True, "data": {"Created": True, "Guid": "FACTOR-GUID-1", "NickName": "LM8H_Factor"}},
            {"success": True, "data": {"Created": True, "Guid": "OFFSET-GUID-1", "NickName": "LM8H_Offset"}},
        ],
        "gh_create_component": [
            {"success": True, "data": {"Created": True, "Guid": "MULTIPLY-GUID-1", "NickName": "A*B"}},
            {"success": True, "data": {"Created": True, "Guid": "ADDITION-GUID-1", "NickName": "A+B"}},
        ],
        "gh_connect": [
            {"success": True, "data": {"connected": True}},
            {"success": True, "data": {"connected": True}},
            {"success": True, "data": {"connected": True}},
            {"success": True, "data": {"connected": True}},
        ],
        "gh_solve": {"success": True, "data": {"scheduled": True}},
        "gh_get_value": [
            {"success": True, "data": {"Guid": "EDITABLE-GUID-1", "Value": editable_value}},
            {"success": True, "data": {"Guid": "FACTOR-GUID-1", "Value": factor_value}},
            {"success": True, "data": {"Guid": "OFFSET-GUID-1", "Value": offset_value}},
        ],
        "gh_inspect_output": {
            "success": True,
            "data": {"param_nickname": "R", "structure": "single", "data_count": 1, "preview": [observed_output]},
        },
    }


def _fixture_responses_for_success():
    responses = _fixture_tool_responses()
    responses.update(
        {
            "rhino_ping": "pong",
            "gh_document_new": {"success": True, "data": {"Created": True}},
            "gh_solve": [
                {"success": True, "data": {"scheduled": True}},
                {"success": True, "data": {"scheduled": True}},
            ],
            "gh_inspect_output": [
                {"success": True, "data": {"data_count": 1, "preview": ["5.5"]}},
                {"success": True, "data": {"data_count": 1, "preview": ["7.5"]}},
            ],
            "gh_set_value": {"success": True, "data": {"Guid": "EDITABLE-GUID-1"}},
        }
    )
    return responses


def test_component_proxy_guid_uses_top_level_fields_only():
    with pytest.raises(ValueError, match="tool_result_guid_missing"):
        PROBE._component_proxy_guid({"data": {"guid": "NESTED-GUID"}})

    assert PROBE._component_proxy_guid({"Guid": "TOP-GUID"}) == "TOP-GUID"


def test_create_affine_fixture_uses_direct_tools_and_hashes_worker_hidden_guid():
    executor = FakeToolExecutor(_fixture_tool_responses())

    fixture = _run(PROBE._create_affine_fixture(executor))

    assert executor.calls == [
        ("gh_library", {"search": "multiplication", "limit": 20}),
        ("gh_library", {"search": "addition", "limit": 20}),
        ("gh_create_slider", {"nickname": "LM8H_Editable", "min": 0, "max": 10, "value": 2.0, "x": 20, "y": 80}),
        ("gh_create_slider", {"nickname": "LM8H_Factor", "min": 0, "max": 10, "value": 2.0, "x": 20, "y": 180}),
        ("gh_create_slider", {"nickname": "LM8H_Offset", "min": 0, "max": 10, "value": 1.5, "x": 20, "y": 280}),
        ("gh_create_component", {"guid": "MULTIPLY-PROXY-GUID", "x": 280, "y": 130}),
        ("gh_create_component", {"guid": "ADDITION-PROXY-GUID", "x": 520, "y": 180}),
        ("gh_connect", {"sourceGuid": "EDITABLE-GUID-1", "targetGuid": "MULTIPLY-GUID-1", "targetParam": "A"}),
        ("gh_connect", {"sourceGuid": "FACTOR-GUID-1", "targetGuid": "MULTIPLY-GUID-1", "targetParam": "B"}),
        ("gh_connect", {"sourceGuid": "MULTIPLY-GUID-1", "sourceParam": "R", "targetGuid": "ADDITION-GUID-1", "targetParam": "A"}),
        ("gh_connect", {"sourceGuid": "OFFSET-GUID-1", "targetGuid": "ADDITION-GUID-1", "targetParam": "B"}),
        ("gh_solve", {"delay": 25}),
        ("gh_get_value", {"guid": "EDITABLE-GUID-1"}),
        ("gh_get_value", {"guid": "FACTOR-GUID-1"}),
        ("gh_get_value", {"guid": "OFFSET-GUID-1"}),
        ("gh_inspect_output", {"guid": "ADDITION-GUID-1", "param": "R"}),
    ]
    assert fixture["editable_component_guid"] == "EDITABLE-GUID-1"
    assert fixture["factor_component_guid"] == "FACTOR-GUID-1"
    assert fixture["offset_component_guid"] == "OFFSET-GUID-1"
    assert fixture["multiplication_component_guid"] == "MULTIPLY-GUID-1"
    assert fixture["addition_component_guid"] == "ADDITION-GUID-1"
    assert fixture["editable_value"] == 2.0
    assert fixture["factor_value"] == 2.0
    assert fixture["offset_value"] == 1.5
    assert fixture["observed_output_value"] == 5.5
    rendered_visible = json.dumps(fixture["visible_receipt"], sort_keys=True)
    for raw_guid in ("EDITABLE-GUID-1", "FACTOR-GUID-1", "OFFSET-GUID-1", "MULTIPLY-GUID-1", "ADDITION-GUID-1"):
        assert raw_guid not in rendered_visible


def test_create_affine_fixture_rejects_deprecated_first_multiplication_without_active_exact_match():
    responses = _fixture_tool_responses()
    responses["gh_library"][0] = {
        "success": True,
        "count": 1,
        "components": [_library_result_for("Multiplication", "DEPRECATED-MUL-GUID", deprecated=True)],
    }
    executor = FakeToolExecutor(responses)

    with pytest.raises(PROBE.FixtureSetupFailure) as exc:
        _run(PROBE._create_affine_fixture(executor))

    assert exc.value.step == "gh_library_multiplication"
    assert exc.value.failure_reason == "active_multiplication_component_missing"


def test_create_affine_fixture_selects_active_multiplication_after_deprecated_alias():
    responses = _fixture_tool_responses()
    responses["gh_library"][0] = {
        "success": True,
        "count": 2,
        "components": [
            _library_result_for("Multiplication", "DEPRECATED-MUL-GUID", deprecated=True),
            _library_result_for("Multiplication", "ACTIVE-MUL-PROXY-GUID"),
        ],
    }
    executor = FakeToolExecutor(responses)

    fixture = _run(PROBE._create_affine_fixture(executor))

    assert fixture["multiplication_component_guid"] == "MULTIPLY-GUID-1"
    assert ("gh_create_component", {"guid": "ACTIVE-MUL-PROXY-GUID", "x": 280, "y": 130}) in executor.calls


@pytest.mark.parametrize(
    ("responses", "expected_reason"),
    [
        (_fixture_tool_responses(editable_value="2.25"), "initial_editable_value_mismatch"),
        (_fixture_tool_responses(factor_value="2.25"), "factor_value_mismatch"),
        (_fixture_tool_responses(offset_value="1.25"), "offset_value_mismatch"),
        (_fixture_tool_responses(observed_output="5.25"), "initial_observed_output_mismatch"),
    ],
)
def test_create_affine_fixture_rejects_noncanonical_initial_state(responses, expected_reason):
    with pytest.raises(PROBE.FixtureSetupFailure) as exc:
        _run(PROBE._create_affine_fixture(FakeToolExecutor(responses)))

    assert exc.value.failure_reason == expected_reason


def test_run_probe_writes_fixture_failure_summary_for_noncanonical_initial_state(tmp_path):
    responses = _fixture_responses_for_success()
    responses["gh_get_value"][0] = {
        "success": True,
        "data": {"Guid": "EDITABLE-GUID-1", "Value": "2.25"},
    }
    executor = FakeToolExecutor(responses)

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *args, **kwargs: _published_action(3.0),
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    summary = json.loads(
        (run_dir / "fixture_failure_summary.json").read_text(encoding="utf-8")
    )

    assert decision["decision"] == "gate_failed"
    assert decision["reason"] == "affine_fixture_failed:initial_editable_value_mismatch"
    assert summary["failure_reason"] == "initial_editable_value_mismatch"


def test_run_probe_writes_fixture_failure_summary_for_projection_invariant_mismatch(
    tmp_path, monkeypatch
):
    original = PROBE._affine_scalar_contract_payload

    def broken_payload():
        payload = original()
        payload["rules"]["verify_affine_scalar_transform_output"]["offset_value"] = 1.25
        return payload

    monkeypatch.setattr(PROBE, "_affine_scalar_contract_payload", broken_payload)
    executor = FakeToolExecutor(_fixture_responses_for_success())

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *args, **kwargs: _published_action(3.0),
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    summary = json.loads(
        (run_dir / "fixture_failure_summary.json").read_text(encoding="utf-8")
    )

    assert decision["decision"] == "gate_failed"
    assert decision["reason"] == "affine_fixture_failed:projection_invariant_mismatch"
    assert summary["failure_reason"] == "projection_invariant_mismatch"


def _valid_affine_fixture():
    return {
        "editable_component_guid": "EDITABLE-GUID-1",
        "factor_component_guid": "FACTOR-GUID-1",
        "offset_component_guid": "OFFSET-GUID-1",
        "multiplication_component_guid": "MULTIPLY-GUID-1",
        "addition_component_guid": "ADDITION-GUID-1",
        "editable_value": 2.0,
        "factor_value": 2.0,
        "offset_value": 1.5,
        "observed_output_value": 5.5,
        "receipt": {
            "editable_value": 2.0,
            "observed_output_value": 5.5,
            "scalar_anchor": {
                "internal_component_guid": "EDITABLE-GUID-1",
                "editable_value_contract": {
                    "label": "LM8H_Editable",
                    "value_type": "number",
                    "current_value": 2.0,
                    "projection_id": "editable_times_factor_plus_offset",
                },
            },
        },
        "visible_receipt": {},
        "fixture_setup_summary": {},
    }


def test_affine_runtime_context_static_validates_and_marks_scalar_ready():
    graph = PROBE._graph_from_affine_receipt(_valid_affine_fixture()["receipt"])
    context = PROBE._affine_runtime_context(
        graph=graph,
        workflow_contract_payload=PROBE._affine_scalar_contract_payload(),
        convention_packets=(),
    )

    routing_report = context["static_routing_report"]
    assert routing_report["valid"] is True
    assert routing_report["routability_evaluated"] is False
    assert context["scalar_runtime_ready"] is True
    assert context["sources"].expected_output_contract.value == 7.5
    assert context["sources"].factor_contract.value == 2.0
    assert context["sources"].offset_contract.value == 1.5
    assert context["sources"].editable_observation.value == 2.0
    assert context["sources"].observed_output.value == 5.5
    assert context["packet"]["fields"]["expected_output_value"] == 7.5
    assert context["packet"]["fields"]["factor_value"] == 2.0
    assert context["packet"]["fields"]["offset_value"] == 1.5
    assert context["worker_visible"]["source"] == "gh_affine_scalar_transform_expectation"


def test_affine_runtime_context_rejects_projection_invariant_mismatch():
    graph = PROBE._graph_from_affine_receipt(_valid_affine_fixture()["receipt"])
    payload = PROBE._affine_scalar_contract_payload()
    payload["rules"]["verify_affine_scalar_transform_output"]["offset_value"] = 1.25

    with pytest.raises(ValueError, match="projection_invariant_mismatch"):
        PROBE._affine_runtime_context(
            graph=graph,
            workflow_contract_payload=payload,
            convention_packets=(),
        )


def test_run_probe_accepts_worker_value_that_matches_affine_output(tmp_path):
    executor = FakeToolExecutor(_fixture_responses_for_success())

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *args, **kwargs: _published_action(3.0),
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    request = json.loads((run_dir / "worker_request_payload.json").read_text(encoding="utf-8"))
    worker_action = json.loads((run_dir / "worker_action.json").read_text(encoding="utf-8"))
    live_set = json.loads((run_dir / "live_set_value_summary.json").read_text(encoding="utf-8"))
    verify = json.loads((run_dir / "verify_scalar_output_summary.json").read_text(encoding="utf-8"))

    assert decision["decision"] == "accepted"
    assert decision["reason"] == "verify_scalar_output_succeeded"
    assert decision["scalar_runtime_ready"] is True
    assert decision["worker_publication_ran"] is True
    assert decision["live_set_value_dispatched"] is True
    assert decision["verify_scalar_output_ran"] is True
    assert worker_action["input"] == {"value": 3.0}
    assert live_set["worker_action_value"] == 3.0
    assert verify["observed_output_value"] == 7.5
    assert "3.0" not in json.dumps(request, sort_keys=True)
    assert "3.0" in json.dumps(worker_action, sort_keys=True)


def test_run_probe_prepublication_artifacts_do_not_contain_hidden_derived_value(tmp_path):
    executor = FakeToolExecutor(_fixture_responses_for_success())

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *args, **kwargs: _published_action(3.0),
    )

    forbidden_pre_publication = [
        "scalar_sources.json",
        "acceptance_criteria_packet.json",
        "worker_visible_acceptance_criteria.json",
        "worker_request_payload.json",
    ]
    for filename in forbidden_pre_publication:
        rendered = (run_dir / filename).read_text(encoding="utf-8")
        assert "3.0" not in rendered

    allowed_post_publication = [
        "worker_action.json",
        "live_set_value_summary.json",
        "decision.json",
    ]
    assert any("3.0" in (run_dir / filename).read_text(encoding="utf-8") for filename in allowed_post_publication)


def test_run_probe_artifacts_keep_raw_guid_out_of_source_request_decision_and_verifier(tmp_path):
    executor = FakeToolExecutor(_fixture_responses_for_success())

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *args, **kwargs: _published_action(3.0),
    )

    forbidden_guid_files = [
        "scalar_sources.json",
        "acceptance_criteria_packet.json",
        "worker_visible_acceptance_criteria.json",
        "worker_request_payload.json",
        "verify_scalar_output_summary.json",
        "decision.json",
    ]
    for filename in forbidden_guid_files:
        rendered = (run_dir / filename).read_text(encoding="utf-8")
        for raw_guid in ("EDITABLE-GUID-1", "FACTOR-GUID-1", "OFFSET-GUID-1", "MULTIPLY-GUID-1", "ADDITION-GUID-1"):
            assert raw_guid not in rendered

    assert "EDITABLE-GUID-1" in (run_dir / "fixture_setup_summary.json").read_text(encoding="utf-8")
    assert "EDITABLE-GUID-1" in (run_dir / "live_set_value_summary.json").read_text(encoding="utf-8")


def test_run_probe_rejects_worker_value_that_does_not_match_affine_output(tmp_path):
    responses = _fixture_responses_for_success()
    responses["gh_inspect_output"] = [
        {"success": True, "data": {"data_count": 1, "preview": ["5.5"]}},
        {"success": True, "data": {"data_count": 1, "preview": ["9.5"]}},
        {"success": True, "data": {"data_count": 1, "preview": ["9.5"]}},
        {"success": True, "data": {"data_count": 1, "preview": ["9.5"]}},
    ]
    executor = FakeToolExecutor(responses)

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *args, **kwargs: _published_action(4.0),
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    assert decision["decision"] == "rejected"
    assert decision["reason"] == "verify_scalar_output_failed"
    assert decision["observed_output_after"] == 9.5


def test_run_probe_receipts_invalid_published_action_id_before_worker_action_artifact(
    tmp_path,
):
    executor = FakeToolExecutor(_fixture_responses_for_success())
    publication = _published_action_with_payload(
        {
            "schema": "rook.local_worker_turn_response:v1",
            "kind": "action_request",
            "action_id": "gh_edit",
            "rationale": "Use gh_edit to patch the graph.",
            "input": {"value": 3.0},
        }
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
        publication_runner=lambda *args, **kwargs: publication,
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    assert decision["decision"] == "publication_failed"
    assert decision["reason"] == "worker_publication_invalid_action_id"
    assert not (run_dir / "worker_action.json").exists()


@pytest.mark.parametrize(
    ("payload", "expected_reason"),
    [
        (
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_gh_set_value_params",
                "rationale": "Use gh_edit to patch the graph.",
                "input": {"value": 3.0},
            },
            "worker_publication_forbidden_content:gh_edit",
        ),
        (
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_gh_set_value_params",
                "rationale": "Provide code to perform the edit.",
                "input": {"value": 3.0},
            },
            "worker_publication_forbidden_content:code",
        ),
        (
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_gh_set_value_params",
                "topology_note": "Adjust graph shape to reach the target.",
                "input": {"value": 3.0},
            },
            "worker_publication_forbidden_content:topology",
        ),
        (
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_gh_set_value_params",
                "notes": {"script_hint": "gh_update_script"},
                "input": {"value": 3.0},
            },
            "worker_publication_forbidden_content:gh_update_script",
        ),
        (
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_gh_set_value_params",
                "notes": {"tool": "gh_set_value"},
                "input": {"value": 3.0},
            },
            "worker_publication_forbidden_content:gh_set_value",
        ),
        (
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_gh_set_value_params",
                "target_guid": "EDITABLE-GUID-1",
                "input": {"value": 3.0},
            },
            "worker_publication_guid_leak",
        ),
    ],
)
def test_run_probe_receipts_forbidden_published_content_before_worker_action_artifact(
    tmp_path, payload, expected_reason
):
    executor = FakeToolExecutor(_fixture_responses_for_success())

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *args, **kwargs: _published_action_with_payload(
            payload
        ),
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    assert decision["decision"] == "publication_failed"
    assert decision["reason"] == expected_reason
    assert not (run_dir / "worker_action.json").exists()
