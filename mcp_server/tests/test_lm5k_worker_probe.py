from __future__ import annotations

import argparse
from collections.abc import Mapping
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from rook.agent.local_worker_prompt_artifact import (
    LOCAL_WORKER_PROMPT_TEXT_VERSION,
)


def _load_script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "lm5k_worker_probe.py"
    spec = importlib.util.spec_from_file_location("lm5k_worker_probe", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


PROBE = _load_script()


def _jsonable(value):
    if isinstance(value, Mapping):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value


def test_slot_vocabulary() -> None:
    assert PROBE.SLOT_LABELS == {
        "local": "local_worker_candidate",
        "cheap": "cheap_cloud_worker_candidate",
        "ceiling": "ceiling_worker_candidate",
    }
    assert PROBE.ENV_VARS == {
        "local": "ROOK_PROBE_LOCAL_WORKER",
        "cheap": "ROOK_PROBE_CHEAP_CLOUD_WORKER",
        "ceiling": "ROOK_PROBE_CEILING_WORKER",
    }
    assert PROBE.GENERATION_PARAMS == {"temperature": 0}
    assert PROBE.SLOT_GENERATION_PARAMS == {
        "local": {"temperature": 0},
        "cheap": {"temperature": 0},
        "ceiling": {},
    }


def test_transport_modes_are_source_of_truth() -> None:
    assert PROBE.TRANSPORT_MODES == ("free_text", "structured")
    assert PROBE.DEFAULT_LOCAL_TRANSPORT_MODE == "free_text"


def test_scenario_configs_are_source_of_truth() -> None:
    assert PROBE.SCENARIO_WORKFLOW_ID == "lm5k_first_probe"
    assert set(PROBE._SCENARIOS) == {
        "evidence_absent",
        "evidence_present",
        "evidence_present_v2",
        "evidence_present_v3",
    }

    absent = PROBE._SCENARIOS["evidence_absent"]
    assert absent.cli_name == "evidence_absent"
    assert absent.scenario_id == "lm5n_repair_evidence_absent"
    assert absent.scenario_version == "v3"
    assert absent.state == "post_verify_pre_bind"
    assert absent.evidence_packet == "none"
    assert absent.expected_disposition == "clarification_needed"
    assert absent.expected_response_kind == "clarification_request"
    assert absent.expected_action_id is None
    assert absent.expected_attempt_valid is True

    present = PROBE._SCENARIOS["evidence_present"]
    assert present.cli_name == "evidence_present"
    assert present.scenario_id == "lm5n_repair_evidence_present"
    assert present.scenario_version == "v3"
    assert present.state == "post_verify_pre_bind"
    assert present.evidence_packet == "repair_v1"
    assert present.expected_disposition == "candidate_action_request"
    assert present.expected_response_kind == "action_request"
    assert present.expected_action_id == "draft_repair_params"
    assert present.expected_attempt_valid is True

    present_v2 = PROBE._SCENARIOS["evidence_present_v2"]
    assert present_v2.cli_name == "evidence_present_v2"
    assert present_v2.scenario_id == "lm5t_repair_intent_evidence_present"
    assert present_v2.scenario_version == "v4"
    assert present_v2.state == "post_verify_pre_bind"
    assert present_v2.evidence_packet == "repair_intent_v2"
    assert present_v2.expected_disposition == "candidate_action_request"
    assert present_v2.expected_response_kind == "action_request"
    assert present_v2.expected_action_id == "draft_repair_params"
    assert present_v2.expected_attempt_valid is True

    present_v3 = PROBE._SCENARIOS["evidence_present_v3"]
    assert present_v3.cli_name == "evidence_present_v3"
    assert (
        present_v3.scenario_id
        == "lm5u_acceptance_criteria_evidence_present"
    )
    assert present_v3.scenario_version == "v5"
    assert present_v3.state == "post_verify_pre_bind"
    assert present_v3.evidence_packet == "acceptance_criteria_v3"
    assert present_v3.expected_disposition == "candidate_action_request"
    assert present_v3.expected_response_kind == "action_request"
    assert present_v3.expected_action_id == "draft_repair_params"
    assert present_v3.expected_attempt_valid is True

    assert "lm5k_golden_repair_v2" not in {
        absent.scenario_id,
        present.scenario_id,
        present_v2.scenario_id,
        present_v3.scenario_id,
    }


def test_scenario_config_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="unknown probe scenario"):
        PROBE._scenario_config("lm5k_golden_repair_v2")


def test_parse_candidate_spec() -> None:
    assert PROBE.parse_candidate_spec("ollama_chat/qwen3:8b") == (
        "ollama_chat/qwen3:8b",
        None,
    )
    assert PROBE.parse_candidate_spec(
        "openai/lmstudio-model@http://localhost:1234/v1"
    ) == ("openai/lmstudio-model", "http://localhost:1234/v1")
    with pytest.raises(ValueError):
        PROBE.parse_candidate_spec("@http://x")


def test_profile_inference_local_only_for_local_shaped_models() -> None:
    assert PROBE.profile_inferred_local("ollama_chat/qwen3:8b", None) == (
        "ollama_chat/qwen3:8b",
        None,
    )
    assert PROBE.profile_inferred_local(
        "openai/lmstudio-model", "http://localhost:1234/v1"
    ) == ("openai/lmstudio-model", "http://localhost:1234/v1")
    # openai/* WITHOUT api_base is ambiguous -> not safely inferable
    assert PROBE.profile_inferred_local("openai/lmstudio-model", None) is None
    # cloud models are never a local inference
    assert (
        PROBE.profile_inferred_local("anthropic/claude-haiku-4-5", None) is None
    )


def test_is_ollama_local_model() -> None:
    assert PROBE._is_ollama_local_model("ollama_chat/gemma4:12b-it-qat") is True
    assert PROBE._is_ollama_local_model("ollama/gemma4:12b-it-qat") is True
    assert PROBE._is_ollama_local_model("openai/lmstudio-model") is False
    assert PROBE._is_ollama_local_model(None) is False


def test_resolve_slot_order_cli_env_profile_none() -> None:
    cli = PROBE.resolve_slot(
        "local",
        cli_value="ollama_chat/a:1",
        env_value="ollama_chat/b:1",
        profile_worker="ollama_chat/c:1",
        profile_api_base=None,
        skipped=False,
    )
    assert (cli["model"], cli["source"], cli["status"]) == (
        "ollama_chat/a:1",
        "cli",
        None,
    )
    env = PROBE.resolve_slot(
        "local",
        cli_value=None,
        env_value="ollama_chat/b:1",
        profile_worker="ollama_chat/c:1",
        profile_api_base=None,
        skipped=False,
    )
    assert (env["model"], env["source"]) == ("ollama_chat/b:1", "env")
    prof = PROBE.resolve_slot(
        "local",
        cli_value=None,
        env_value=None,
        profile_worker="ollama_chat/c:1",
        profile_api_base=None,
        skipped=False,
    )
    assert (prof["model"], prof["source"]) == ("ollama_chat/c:1", "profile")
    none = PROBE.resolve_slot(
        "local",
        cli_value=None,
        env_value=None,
        profile_worker="anthropic/claude-haiku-4-5",
        profile_api_base=None,
        skipped=False,
    )
    assert (none["model"], none["source"], none["status"]) == (
        None,
        "none",
        "unavailable",
    )


def test_cheap_and_ceiling_never_profile_inferred() -> None:
    for slot in ("cheap", "ceiling"):
        resolution = PROBE.resolve_slot(
            slot,
            cli_value=None,
            env_value=None,
            profile_worker="ollama_chat/c:1",
            profile_api_base=None,
            skipped=False,
        )
        assert resolution["status"] == "unavailable"
        assert resolution["source"] == "none"


def test_skipped_slot() -> None:
    resolution = PROBE.resolve_slot(
        "ceiling",
        cli_value="anthropic/claude-sonnet-5",
        env_value=None,
        profile_worker="x",
        profile_api_base=None,
        skipped=True,
    )
    assert resolution["status"] == "skipped"
    assert resolution["model"] is None


def test_candidate_status_classification() -> None:
    assert PROBE.classify_candidate_status(
        ["transport_error", "transport_error"]
    ) == "transport_error"
    assert PROBE.classify_candidate_status(
        ["transport_error", "raw_output_invalid"]
    ) == "ran"
    assert PROBE.classify_candidate_status(["response_loaded"]) == "ran"
    with pytest.raises(ValueError):
        PROBE.classify_candidate_status([])


def test_attempt_metrics_pair() -> None:
    loaded_passed = {"adapter_status": "response_loaded", "evaluation_passed": True}
    loaded_failed = {"adapter_status": "response_loaded", "evaluation_passed": False}
    invalid = {"adapter_status": "raw_output_invalid", "evaluation_passed": None}
    assert PROBE.attempt_metrics(loaded_passed) == (True, True)
    assert PROBE.attempt_metrics(loaded_failed) == (True, False)
    assert PROBE.attempt_metrics(invalid) == (False, False)


class _FakeCallInfo:
    def __init__(self):
        self.latency_ms = 12.5
        self.prompt_tokens = 100
        self.completion_tokens = 20
        self.cost_usd = 0.0001


class _FakeGoodTransport:
    """Deterministic offline model: reads the allowed action from the
    prompt artifact's user JSON (mirrors LM5J's integration transport)."""

    def __init__(self, resolution):
        self.last_call_info = None
        self.last_raw_output = None

    def send(self, prompt_artifact):
        self.last_call_info = None
        self.last_raw_output = None
        envelope = json.loads(prompt_artifact["messages"][1]["content"])
        action_id = envelope["context"]["allowed_actions"][0]["action_id"]
        raw = json.dumps(
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": action_id,
                "rationale": "Draft repair parameters for the failed component.",
                "input": {"code": PROBE.PROBE_REPAIR_CODE, "mode": "body"},
            }
        )
        self.last_raw_output = raw
        self.last_call_info = _FakeCallInfo()
        return raw


class _FakeFencedTransport(_FakeGoodTransport):
    def send(self, prompt_artifact):
        raw = super().send(prompt_artifact)
        fenced = "```json\n" + raw + "\n```"
        self.last_raw_output = fenced
        return fenced


class _FakeScenarioAwareTransport:
    """Clarifies without evidence, acts with the bounded evidence packet."""

    def __init__(self, resolution):
        self.last_call_info = None
        self.last_raw_output = None

    def send(self, prompt_artifact):
        self.last_call_info = _FakeCallInfo()
        envelope = json.loads(prompt_artifact["messages"][1]["content"])
        context = envelope["context"]
        packet_ids = [packet["packet_id"] for packet in context["knowledge"]]
        if "lm5n_repair_evidence" not in packet_ids:
            raw = json.dumps(
                {
                    "schema": "rook.local_worker_turn_response:v1",
                    "kind": "clarification_request",
                    "question": "Please provide the repair evidence.",
                    "rationale": (
                        "The visible context does not include enough evidence "
                        "to author the action input."
                    ),
                }
            )
        else:
            action_id = context["allowed_actions"][0]["action_id"]
            evidence = next(
                packet for packet in context["knowledge"]
                if packet["packet_id"] == "lm5n_repair_evidence"
            )
            fields = evidence["content"]["fields"]
            raw = json.dumps(
                {
                    "schema": "rook.local_worker_turn_response:v1",
                    "kind": "action_request",
                    "action_id": action_id,
                    "rationale": "Use bounded repair evidence.",
                    "input": {
                        "code": fields["current_code"]["value"],
                        "mode": fields["recommended_mode"]["value"],
                    },
                }
            )
        self.last_raw_output = raw
        return raw


def _args(tmp_path, **overrides):
    values = {
        "local": "ollama_chat/fake:1", "cheap": None, "ceiling": None,
        "skip": ["cheap", "ceiling"], "attempts": 3,
        "capture_raw": False, "run_dir": str(tmp_path),
        "scenario": "evidence_present",
        "local_transport_mode": "free_text",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_offline_probe_end_to_end_good_transport(tmp_path) -> None:
    run_dir = PROBE.run_probe(
        _args(tmp_path), transport_factory=_FakeGoodTransport
    )
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert "generation_params" not in manifest
    assert manifest["prompt_text_version"] == LOCAL_WORKER_PROMPT_TEXT_VERSION
    # scenario identity: structured block, versioned (spec section 5);
    # the bare scenario_workflow_id string is replaced, not kept alongside
    assert manifest["scenario"] == {
        "workflow_id": "lm5k_first_probe",
        "scenario_id": "lm5n_repair_evidence_present",
        "scenario_version": "v3",
        "state": "post_verify_pre_bind",
    }
    assert "scenario_workflow_id" not in manifest
    local = next(p for p in manifest["panel"] if p["slot"] == "local")
    assert local["status"] == "ran"
    assert local["strict_loadable"] == 3
    assert local["spine_passed"] == 3
    # per-candidate generation params are recorded; the ceiling slot omits
    # sampling params (reasoning-tier models reject non-default values)
    assert local["generation_params"] == {"temperature": 0}
    ceiling = next(p for p in manifest["panel"] if p["slot"] == "ceiling")
    assert ceiling["generation_params"] == {}
    skipped = [p for p in manifest["panel"] if p["status"] == "skipped"]
    assert len(skipped) == 2
    lines = (run_dir / "attempts.jsonl").read_text().strip().splitlines()
    assert len(lines) == 3
    first = json.loads(lines[0])
    assert first["run_id"] == run_dir.name
    assert first["adapter_status"] == "response_loaded"
    assert first["evaluation_passed"] is True
    assert first["disposition"] == "candidate_action_request"
    assert first["latency_ms"] == 12.5
    assert first["captured_raw_path"] is None
    assert not (run_dir / "raw").exists()


def test_offline_probe_evidence_absent_expects_clarification(tmp_path) -> None:
    run_dir = PROBE.run_probe(
        _args(tmp_path, scenario="evidence_absent", attempts=2),
        transport_factory=_FakeScenarioAwareTransport,
    )
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["scenario"] == {
        "workflow_id": "lm5k_first_probe",
        "scenario_id": "lm5n_repair_evidence_absent",
        "scenario_version": "v3",
        "state": "post_verify_pre_bind",
    }
    local = next(p for p in manifest["panel"] if p["slot"] == "local")
    assert local["status"] == "ran"
    assert local["strict_loadable"] == 2
    assert local["spine_passed"] == 2
    lines = (run_dir / "attempts.jsonl").read_text().strip().splitlines()
    first = json.loads(lines[0])
    assert first["adapter_status"] == "response_loaded"
    assert first["disposition"] == "clarification_needed"
    assert first["evaluation_passed"] is True


def test_offline_probe_evidence_present_expects_action(tmp_path) -> None:
    run_dir = PROBE.run_probe(
        _args(tmp_path, scenario="evidence_present", attempts=2),
        transport_factory=_FakeScenarioAwareTransport,
    )
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["scenario"] == {
        "workflow_id": "lm5k_first_probe",
        "scenario_id": "lm5n_repair_evidence_present",
        "scenario_version": "v3",
        "state": "post_verify_pre_bind",
    }
    local = next(p for p in manifest["panel"] if p["slot"] == "local")
    assert local["status"] == "ran"
    assert local["strict_loadable"] == 2
    assert local["spine_passed"] == 2
    lines = (run_dir / "attempts.jsonl").read_text().strip().splitlines()
    first = json.loads(lines[0])
    assert first["adapter_status"] == "response_loaded"
    assert first["disposition"] == "candidate_action_request"
    assert first["evaluation_passed"] is True


def test_offline_probe_fenced_output_counts_split(tmp_path) -> None:
    run_dir = PROBE.run_probe(
        _args(tmp_path, attempts=2), transport_factory=_FakeFencedTransport
    )
    manifest = json.loads((run_dir / "manifest.json").read_text())
    local = next(p for p in manifest["panel"] if p["slot"] == "local")
    assert local["status"] == "ran"
    assert local["strict_loadable"] == 0
    assert local["spine_passed"] == 0
    lines = (run_dir / "attempts.jsonl").read_text().strip().splitlines()
    assert json.loads(lines[0])["failure_reason"] == (
        "raw_output_invalid:json_decode"
    )


def test_structured_mode_requires_resolved_ollama_local(tmp_path) -> None:
    with pytest.raises(
        ValueError, match="structured local transport requires an Ollama local model"
    ):
        PROBE.run_probe(
            _args(
                tmp_path,
                local="openai/lmstudio-model@http://localhost:1234/v1",
                local_transport_mode="structured",
            ),
            transport_factory=_FakeGoodTransport,
        )


def test_structured_mode_rejects_skipped_local_slot(tmp_path) -> None:
    with pytest.raises(
        ValueError, match="structured local transport requires a runnable local slot"
    ):
        PROBE.run_probe(
            _args(
                tmp_path,
                local="ollama_chat/gemma4:12b-it-qat",
                local_transport_mode="structured",
                skip=["local", "cheap", "ceiling"],
            ),
            transport_factory=_FakeGoodTransport,
        )


def test_manifest_and_attempts_record_transport_mode(tmp_path) -> None:
    run_dir = PROBE.run_probe(
        _args(
            tmp_path,
            local="ollama_chat/gemma4:12b-it-qat",
            local_transport_mode="structured",
            attempts=1,
        ),
        transport_factory=_FakeGoodTransport,
    )
    manifest = json.loads((run_dir / "manifest.json").read_text())
    by_slot = {entry["slot"]: entry for entry in manifest["panel"]}
    assert by_slot["local"]["transport_mode"] == "structured"
    assert by_slot["cheap"]["transport_mode"] == "free_text"
    assert by_slot["ceiling"]["transport_mode"] == "free_text"
    first = json.loads((run_dir / "attempts.jsonl").read_text().splitlines()[0])
    assert first["transport_mode"] == "structured"


def test_transport_factory_receives_structured_schema_only_for_local_structured(
    tmp_path,
) -> None:
    captured = []

    class CapturingTransport(_FakeGoodTransport):
        def __init__(self, resolution):
            super().__init__(resolution)
            captured.append(resolution)

    PROBE.run_probe(
        _args(
            tmp_path,
            local="ollama_chat/gemma4:12b-it-qat",
            local_transport_mode="structured",
            attempts=1,
        ),
        transport_factory=CapturingTransport,
    )
    assert captured[0]["transport_mode"] == "structured"
    assert captured[0]["structured_response_schema"] is not None


def test_derived_graph_state_is_post_verify_pre_bind() -> None:
    scaffold, result = PROBE.derive_probe_graph_state()
    assert result.stop_reason == "max_steps_reached"
    assert result.steps_attempted == 2
    assert [r.execution_kind for r in result.records] == [
        "producer", "verifier",
    ]
    assert [r.accepted_node_id for r in result.records] == [
        "create_script", "verify_create",
    ]
    assert result.records[0].ran is True
    graph = result.final_graph
    assert graph.nodes["create_script"].evidence is not None
    assert result.records[1].verifier_outcome_status == "needs_repair"

    repair = graph.nodes["repair_same_component"]
    assert repair.status == "ready"
    from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY

    assert EXECUTION_PARAMS_KEY not in repair.metadata
    assert graph.memory.facts["component_guid"] == PROBE.PROBE_COMPONENT_GUID
    assert (
        graph.memory.facts["repair_anchor"]["component_guid"]
        == PROBE.PROBE_COMPONENT_GUID
    )


def test_offline_runner_refuses_non_create_nodes() -> None:
    import asyncio

    runner = PROBE._OfflineCreateRunner()
    _scaffold, result = PROBE.derive_probe_graph_state()
    with pytest.raises(RuntimeError, match="offline runner asked to execute"):
        asyncio.run(
            runner.run_live_producer_node(
                result.final_graph, "repair_same_component"
            )
        )
    assert runner.calls == ["repair_same_component"]


def _fresh_scaffold_and_empty_result():
    """The round-1b shape: freshly compiled graph, nothing executed."""
    from rook.agent.plan_graph_current_step_stream import (
        CurrentStepStreamResult,
    )
    from rook.agent.plan_graph_workflow_contract import (
        compile_workflow_contract,
    )

    scaffold = compile_workflow_contract(PROBE._probe_contract())
    return scaffold, CurrentStepStreamResult(
        final_graph=scaffold.graph,
        records=(),
        supply_records=(),
        stop_reason="max_steps_reached",
        steps_attempted=0,
    )


def test_graph_state_guard_rejects_round_1b_shape() -> None:
    # Regression: the guard must reject the exact fixture shape that
    # produced the round-1b false spine reading. It would have caught
    # round 1b; this proves it stays able to.
    scaffold, empty = _fresh_scaffold_and_empty_result()
    with pytest.raises(
        RuntimeError, match="LM5L coherent fixture invariant failed"
    ):
        PROBE._require_coherent_graph_state(scaffold, empty)


def test_graph_state_guard_accepts_derived_state() -> None:
    scaffold, result = PROBE.derive_probe_graph_state()
    PROBE._require_coherent_graph_state(scaffold, result)  # must not raise


def test_evidence_absent_knowledge_has_only_script_body_gotcha() -> None:
    _scaffold, result = PROBE.derive_probe_graph_state()
    packets = PROBE._knowledge_packets_for_scenario(
        PROBE._SCENARIOS["evidence_absent"], result.final_graph
    )
    assert [packet.packet_id for packet in packets] == ["script_body_gotcha"]
    assert [packet.kind for packet in packets] == ["gotcha"]


def test_evidence_present_knowledge_adds_exactly_one_evidence_packet() -> None:
    _scaffold, result = PROBE.derive_probe_graph_state()
    packets = PROBE._knowledge_packets_for_scenario(
        PROBE._SCENARIOS["evidence_present"], result.final_graph
    )
    assert [packet.packet_id for packet in packets] == [
        "script_body_gotcha",
        "lm5n_repair_evidence",
    ]
    assert [packet.kind for packet in packets] == ["gotcha", "evidence"]


def test_knowledge_packets_route_v2_repair_intent_evidence() -> None:
    _scaffold, result = PROBE.derive_probe_graph_state()
    packets = PROBE._knowledge_packets_for_scenario(
        PROBE._SCENARIOS["evidence_present_v2"], result.final_graph
    )
    assert [packet.packet_id for packet in packets] == [
        "script_body_gotcha",
        "lm5t_repair_intent_evidence",
    ]
    assert [packet.kind for packet in packets] == ["gotcha", "evidence"]


def test_knowledge_packets_route_v3_acceptance_criteria_evidence() -> None:
    _scaffold, result = PROBE.derive_probe_graph_state()
    packets = PROBE._knowledge_packets_for_scenario(
        PROBE._SCENARIOS["evidence_present_v3"], result.final_graph
    )
    assert [packet.packet_id for packet in packets] == [
        "script_body_gotcha",
        "lm5u_acceptance_criteria_evidence",
    ]
    assert [packet.kind for packet in packets] == ["gotcha", "evidence"]


def test_probe_evidence_constants_are_source_of_truth() -> None:
    assert PROBE.EVIDENCE_PACKET_ID == "lm5n_repair_evidence"
    assert (
        PROBE.REPAIR_INTENT_EVIDENCE_PACKET_ID
        == "lm5t_repair_intent_evidence"
    )
    assert (
        PROBE.ACCEPTANCE_CRITERIA_EVIDENCE_PACKET_ID
        == "lm5u_acceptance_criteria_evidence"
    )
    assert PROBE.EVIDENCE_TARGET_DIAGNOSTIC_MAX_ITEMS == 3
    assert PROBE.EVIDENCE_TARGET_DIAGNOSTIC_MAX_CHARS == 300
    assert PROBE.REPAIR_TARGET_ERROR == (
        "CS0103: The name 'DefinitelyMissingSymbol' "
        "does not exist in the current context."
    )


def test_upstream_receipt_contains_bounded_target_error() -> None:
    _scaffold, result = PROBE.derive_probe_graph_state()
    receipt = PROBE._require_receipt_mapping(result.final_graph)

    repair_anchor = receipt["repair_anchor"]
    assert repair_anchor["target_errors"] == [PROBE.REPAIR_TARGET_ERROR]
    assert "target_warnings" not in repair_anchor
    assert isinstance(repair_anchor["target_errors"][0], str)


def test_evidence_packet_fields_are_bounded_and_provenance_tagged() -> None:
    _scaffold, result = PROBE.derive_probe_graph_state()
    packet = PROBE._repair_evidence_packet(result.final_graph)

    assert packet.packet_id == "lm5n_repair_evidence"
    assert packet.kind == "evidence"
    assert packet.title == "Receipt-derived repair evidence"
    assert packet.content["source"] == "probe_fixture"
    assert packet.content["trust"] == "high"
    assert packet.content["state"] == "post_verify_pre_bind"

    fields = packet.content["fields"]
    assert set(fields) == {
        "source_node_id",
        "verifier_node_id",
        "producer_status",
        "verification_status",
        "target_error_count",
        "component_guid",
        "repair_anchor",
        "language",
        "current_code",
        "recommended_mode",
    }
    for name, item in fields.items():
        assert "value" in item, name
        assert isinstance(item["source"], str) and item["source"], name

    assert fields["source_node_id"] == {
        "value": "create_script",
        "source": "workflow_record",
    }
    assert fields["verifier_node_id"] == {
        "value": "verify_create",
        "source": "workflow_record",
    }
    assert fields["producer_status"]["value"] == "created_with_errors"
    assert fields["verification_status"]["value"] == "failed"
    assert fields["target_error_count"]["value"] == 1
    assert fields["component_guid"]["value"] == PROBE.PROBE_COMPONENT_GUID
    assert fields["repair_anchor"] == {
        "value": {
            "component_guid": PROBE.PROBE_COMPONENT_GUID,
            "language": "csharp",
        },
        "source": "graph.memory.facts.repair_anchor",
    }
    assert fields["language"]["value"] == "csharp"
    assert fields["current_code"]["value"] == "A = DefinitelyMissingSymbol;"
    assert len(fields["current_code"]["value"]) <= 500
    assert fields["current_code"]["truncated"] is False
    assert fields["current_code"]["max_chars"] == 500
    assert fields["recommended_mode"] == {
        "value": "body",
        "source": "script_body_gotcha",
        "derivation": "existing worker-visible gotcha convention",
    }


def test_repair_intent_evidence_v2_fields_are_bounded_and_provenance_tagged() -> None:
    _scaffold, result = PROBE.derive_probe_graph_state()
    packet = PROBE._repair_intent_evidence_packet(result.final_graph)

    assert packet.packet_id == "lm5t_repair_intent_evidence"
    assert packet.kind == "evidence"
    assert packet.title == "Receipt-derived repair intent evidence"
    assert packet.content["source"] == "probe_fixture"
    assert packet.content["trust"] == "high"
    assert packet.content["state"] == "post_verify_pre_bind"

    fields = packet.content["fields"]
    assert set(fields) == {
        "current_code",
        "recommended_mode",
        "language",
        "component_guid",
        "repair_anchor",
        "pin_contract",
        "current_verification",
        "target_diagnostics",
        "expected_repair_outcome",
    }

    assert fields["current_code"]["value"] == "A = DefinitelyMissingSymbol;"
    assert fields["recommended_mode"]["value"] == "body"
    assert fields["language"]["value"] == "csharp"
    assert fields["component_guid"]["value"] == PROBE.PROBE_COMPONENT_GUID

    repair_anchor = fields["repair_anchor"]
    assert repair_anchor == {
        "value": {
            "component_guid": PROBE.PROBE_COMPONENT_GUID,
            "language": "csharp",
        },
        "source": "graph.memory.facts.repair_anchor",
    }
    assert set(repair_anchor["value"]) == {"component_guid", "language"}
    assert "target_errors" not in repair_anchor["value"]
    assert "target_warnings" not in repair_anchor["value"]

    assert fields["pin_contract"] == {
        "source": "create_script.initial_execution_params",
        "value": {"pins_in": (), "pins_out": ("A:double",)},
    }
    assert fields["current_verification"] == {
        "value": {"status": "failed", "target_error_count": 1},
        "source": "create_script.receipt.script_receipt.verification",
    }
    assert fields["expected_repair_outcome"] == {
        "value": "succeeded",
        "source": "workflow_contract.rules.verify_repair.expected_outcome",
    }

    target_diagnostics = fields["target_diagnostics"]
    assert target_diagnostics["source"] == (
        "create_script.receipt.script_receipt.repair_anchor"
    )
    assert set(target_diagnostics["fields"]) == {"target_errors"}
    errors = target_diagnostics["fields"]["target_errors"]
    assert errors == {
        "value": (PROBE.REPAIR_TARGET_ERROR,),
        "source": (
            "create_script.receipt.script_receipt.repair_anchor.target_errors"
        ),
        "max_items": PROBE.EVIDENCE_TARGET_DIAGNOSTIC_MAX_ITEMS,
        "max_chars_per_item": PROBE.EVIDENCE_TARGET_DIAGNOSTIC_MAX_CHARS,
        "truncated": False,
    }
    assert all(isinstance(entry, str) for entry in errors["value"])


def test_acceptance_criteria_evidence_v3_fields_are_bounded_and_provenance_tagged() -> None:
    _scaffold, result = PROBE.derive_probe_graph_state()
    packet = PROBE._acceptance_criteria_evidence_packet(result.final_graph)

    assert packet.packet_id == "lm5u_acceptance_criteria_evidence"
    assert packet.kind == "evidence"
    assert packet.title == "Acceptance-criteria repair evidence"
    assert packet.content["source"] == "probe_fixture"
    assert packet.content["trust"] == "high"
    assert packet.content["state"] == "post_verify_pre_bind"

    fields = packet.content["fields"]
    assert set(fields) == {
        "current_code",
        "language",
        "recommended_mode",
        "repair_anchor",
        "pin_contract",
        "target_diagnostics",
        "expected_repair_outcome",
        "acceptance_criteria",
    }

    assert fields["current_code"]["value"] == "A = DefinitelyMissingSymbol;"
    assert fields["language"]["value"] == "csharp"
    assert fields["recommended_mode"]["value"] == "body"
    assert fields["repair_anchor"] == {
        "value": {
            "component_guid": PROBE.PROBE_COMPONENT_GUID,
            "language": "csharp",
        },
        "source": "graph.memory.facts.repair_anchor",
    }

    assert fields["pin_contract"] == {
        "source": "create_script.initial_execution_params.pins_out",
        "value": {
            "pins_out": ("A:double",),
            "output_requirements": (
                {
                    "requirement_id": "output_a_assigned",
                    "description": "Output A must be assigned.",
                    "source": "create_script.initial_execution_params.pins_out",
                },
                {
                    "requirement_id": "output_a_double_compatible",
                    "description": "Output A must be double-compatible.",
                    "source": "create_script.initial_execution_params.pins_out",
                },
            ),
        },
    }

    target_diagnostics = fields["target_diagnostics"]
    assert target_diagnostics["source"] == (
        "create_script.receipt.script_receipt.repair_anchor"
    )
    assert set(target_diagnostics["fields"]) == {"target_errors"}
    assert target_diagnostics["fields"]["target_errors"]["value"] == (
        PROBE.REPAIR_TARGET_ERROR,
    )

    assert fields["expected_repair_outcome"] == {
        "value": "succeeded",
        "source": "workflow_contract.rules.verify_repair.expected_outcome",
    }

    acceptance = fields["acceptance_criteria"]
    assert acceptance["source"] == (
        "workflow_contract + create_script.initial_execution_params + "
        "create_script.receipt.script_receipt.repair_anchor + script_body_gotcha"
    )
    assert [
        criterion["criterion_id"]
        for criterion in acceptance["criteria"]
    ] == [
        "output_a_assigned",
        "output_a_double_compatible",
        "verify_repair_succeeds",
        "preserve_body_mode",
        "resolve_target_diagnostics",
        "remove_unresolved_symbol",
    ]
    assert all(
        set(criterion) == {"criterion_id", "description", "source"}
        for criterion in acceptance["criteria"]
    )


def test_lm5t_probe_script_does_not_publish_hidden_repair_params() -> None:
    contract = PROBE._probe_contract()
    repair_rule = next(
        rule for rule in contract.rules
        if rule.node_id == "repair_same_component"
    )
    bind_step = next(
        step for step in repair_rule.steps_by_seen_count
        if getattr(step, "base_params", None)
    )
    assert bind_step.base_params["code"] == PROBE.PROBE_REPAIR_CODE
    assert bind_step.base_params["mode"] == "body"

    _scaffold, result = PROBE.derive_probe_graph_state()
    packet = PROBE._repair_intent_evidence_packet(result.final_graph)
    rendered = json.dumps(_jsonable(packet.content))

    assert PROBE.PROBE_REPAIR_CODE not in rendered
    assert "A = 42.0;" not in rendered
    assert "hidden BindStepSpec.base_params.code" not in rendered


def test_repair_evidence_v1_does_not_expose_target_diagnostics() -> None:
    _scaffold, result = PROBE.derive_probe_graph_state()
    packet = PROBE._repair_evidence_packet(result.final_graph)
    rendered = repr(packet.content)

    assert "target_errors" not in rendered
    assert "target_warnings" not in rendered
    assert PROBE.REPAIR_TARGET_ERROR not in rendered
    assert "DefinitelyMissingSymbol" in rendered


def test_evidence_ladder_visibility_is_stable() -> None:
    _scaffold, result = PROBE.derive_probe_graph_state()

    v1 = json.dumps(
        _jsonable(PROBE._repair_evidence_packet(result.final_graph).content),
        sort_keys=True,
    )
    v2 = json.dumps(
        _jsonable(
            PROBE._repair_intent_evidence_packet(result.final_graph).content
        ),
        sort_keys=True,
    )
    v3 = json.dumps(
        _jsonable(
            PROBE._acceptance_criteria_evidence_packet(result.final_graph).content
        ),
        sort_keys=True,
    )

    assert "target_errors" not in v1
    assert "acceptance_criteria" not in v1

    assert "target_errors" in v2
    assert "acceptance_criteria" not in v2

    assert "target_errors" in v3
    assert "acceptance_criteria" in v3

    for rendered in (v1, v2, v3):
        assert PROBE.PROBE_REPAIR_CODE not in rendered
        assert "A = 42.0;" not in rendered
        assert "hidden BindStepSpec.base_params.code" not in rendered


def test_acceptance_criteria_v3_does_not_publish_replacement_literals() -> None:
    _scaffold, result = PROBE.derive_probe_graph_state()
    packet = PROBE._acceptance_criteria_evidence_packet(result.final_graph)
    rendered = json.dumps(_jsonable(packet.content), sort_keys=True)

    assert "DefinitelyMissingSymbol" in rendered
    assert "Output A must be assigned." in rendered
    assert "Output A must be double-compatible." in rendered
    assert "A = 42.0;" not in rendered
    assert PROBE.PROBE_REPAIR_CODE not in rendered
    assert "set A to" not in rendered
    assert "replacement code" not in rendered
    assert "repair diff" not in rendered


def test_target_diagnostic_evidence_bounds_items_and_chars() -> None:
    long = "x" * (PROBE.EVIDENCE_TARGET_DIAGNOSTIC_MAX_CHARS + 10)
    evidence = PROBE._bounded_target_diagnostics(
        ["short", long, "kept", "dropped"], source="test.source"
    )

    assert evidence == {
        "value": [
            "short",
            long[:PROBE.EVIDENCE_TARGET_DIAGNOSTIC_MAX_CHARS],
            "kept",
        ],
        "source": "test.source",
        "max_items": PROBE.EVIDENCE_TARGET_DIAGNOSTIC_MAX_ITEMS,
        "max_chars_per_item": PROBE.EVIDENCE_TARGET_DIAGNOSTIC_MAX_CHARS,
        "truncated": True,
    }


def test_target_diagnostic_evidence_requires_string_items() -> None:
    with pytest.raises(RuntimeError, match="target diagnostic item not string"):
        PROBE._bounded_target_diagnostics(["ok", 42], source="test.source")


def test_pin_contract_evidence_rejects_tuple_pins() -> None:
    with pytest.raises(RuntimeError, match="pins_in contract missing"):
        PROBE._pin_contract_from_params(
            {"pins_in": (), "pins_out": ["A:double"]}
        )
    with pytest.raises(RuntimeError, match="pins_out contract missing"):
        PROBE._pin_contract_from_params(
            {"pins_in": [], "pins_out": ("A:double",)}
        )


def test_current_code_evidence_reads_derived_create_params_not_repair_literal() -> None:
    from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY

    _scaffold, result = PROBE.derive_probe_graph_state()
    params = result.final_graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY]
    params["code"] = "A = MutatedFromDerivedGraph;"

    packet = PROBE._repair_evidence_packet(result.final_graph)
    fields = packet.content["fields"]
    assert fields["current_code"]["value"] == "A = MutatedFromDerivedGraph;"
    assert fields["current_code"]["value"] != PROBE.PROBE_REPAIR_CODE


def test_current_code_evidence_truncates_long_derived_code() -> None:
    from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY

    _scaffold, result = PROBE.derive_probe_graph_state()
    long_code = "A = " + "x" * (PROBE.EVIDENCE_CURRENT_CODE_MAX_CHARS + 25)
    params = result.final_graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY]
    params["code"] = long_code

    packet = PROBE._repair_evidence_packet(result.final_graph)
    current_code = packet.content["fields"]["current_code"]
    assert current_code["value"] == long_code[:PROBE.EVIDENCE_CURRENT_CODE_MAX_CHARS]
    assert len(current_code["value"]) == PROBE.EVIDENCE_CURRENT_CODE_MAX_CHARS
    assert current_code["truncated"] is True
    assert current_code["max_chars"] == PROBE.EVIDENCE_CURRENT_CODE_MAX_CHARS


def test_graph_state_guard_message_repair_not_ready() -> None:
    scaffold, result = PROBE.derive_probe_graph_state()
    result.final_graph.nodes["repair_same_component"].status = "pending"
    with pytest.raises(RuntimeError, match="repair node is not ready"):
        PROBE._require_coherent_graph_state(scaffold, result)


def test_graph_state_guard_message_repair_node_missing() -> None:
    scaffold, result = PROBE.derive_probe_graph_state()
    del result.final_graph.nodes["repair_same_component"]
    with pytest.raises(RuntimeError, match="repair node missing"):
        PROBE._require_coherent_graph_state(scaffold, result)


def test_graph_state_guard_message_create_node_missing() -> None:
    scaffold, result = PROBE.derive_probe_graph_state()
    del result.final_graph.nodes["create_script"]
    with pytest.raises(RuntimeError, match="create node missing"):
        PROBE._require_coherent_graph_state(scaffold, result)


def test_graph_state_guard_message_params_present_too_early() -> None:
    from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY

    scaffold, result = PROBE.derive_probe_graph_state()
    result.final_graph.nodes["repair_same_component"].metadata[
        EXECUTION_PARAMS_KEY
    ] = {"code": PROBE.PROBE_REPAIR_CODE, "mode": "body"}
    with pytest.raises(
        RuntimeError, match="execution params unexpectedly present"
    ):
        PROBE._require_coherent_graph_state(scaffold, result)


def test_graph_state_guard_message_memory_facts_missing() -> None:
    scaffold, result = PROBE.derive_probe_graph_state()
    result.final_graph.memory.facts.clear()
    with pytest.raises(RuntimeError, match="memory facts missing repair anchor"):
        PROBE._require_coherent_graph_state(scaffold, result)


def test_graph_state_guard_rejects_post_bind_sequence() -> None:
    import asyncio

    from rook.agent.plan_graph_current_step_stream import (
        run_current_step_stream,
    )
    from rook.agent.plan_graph_workflow_contract import (
        compile_workflow_contract,
    )

    scaffold = compile_workflow_contract(PROBE._probe_contract())
    result = asyncio.run(
        run_current_step_stream(
            scaffold.graph,
            scaffold.provider,
            max_steps=3,
            runner=PROBE._OfflineCreateRunner(),
        )
    )
    with pytest.raises(RuntimeError, match="unexpected step sequence"):
        PROBE._require_coherent_graph_state(scaffold, result)


def test_probe_context_envelope_is_world_state_coherent() -> None:
    # Layer 2 (spec section 6): the envelope a model actually sees must
    # tell the same coherent story as the derived graph — asserted ONLY on
    # model-visible facts (has_execution_params flag, memory KEYS), never
    # param payloads or memory fact values (spec section 3.5). These are
    # point-for-point the negations of the ceiling's round-1b refusal.
    from rook.agent.local_worker_turn_request import (
        render_local_worker_turn_request_payload,
    )

    payload = render_local_worker_turn_request_payload(
        PROBE.build_probe_context()
    )
    context = payload["context"]

    assert (
        "repair_same_component" in context["current_graph"]["ready_node_ids"]
    )
    node = context["current_node"]
    assert node["node_id"] == "repair_same_component"
    assert node["status"] == "ready"
    assert node["has_execution_params"] is False
    assert "repair_anchor" in node["memory_keys"]
    assert "component_guid" in node["memory_keys"]

    history = context["history"]
    assert history["current_step_count"] == 2
    assert [
        step["execution_kind"] for step in history["recent_steps"]
    ] == ["producer", "verifier"]
    assert [
        step["accepted_node_id"] for step in history["recent_steps"]
    ] == ["create_script", "verify_create"]

    action_ids = [a["action_id"] for a in context["allowed_actions"]]
    assert "draft_repair_params" in action_ids


def test_evidence_absent_probe_envelope_does_not_expose_evidence_values() -> None:
    from rook.agent.local_worker_turn_request import (
        render_local_worker_turn_request_payload,
    )

    payload = render_local_worker_turn_request_payload(
        PROBE.build_probe_context(PROBE._SCENARIOS["evidence_absent"])
    )
    rendered = json.dumps(payload)
    assert PROBE.PROBE_COMPONENT_GUID not in rendered
    assert "A = DefinitelyMissingSymbol;" not in rendered
    assert "lm5n_repair_evidence" not in rendered


def test_evidence_present_probe_envelope_exposes_only_bounded_evidence_values() -> None:
    from rook.agent.local_worker_turn_request import (
        render_local_worker_turn_request_payload,
    )

    payload = render_local_worker_turn_request_payload(
        PROBE.build_probe_context(PROBE._SCENARIOS["evidence_present"])
    )
    rendered = json.dumps(payload)
    assert "lm5n_repair_evidence" in rendered
    assert PROBE.PROBE_COMPONENT_GUID in rendered
    assert "A = DefinitelyMissingSymbol;" in rendered
    assert PROBE.PROBE_REPAIR_CODE not in rendered
    assert "already-bound repair params" not in rendered


def test_evidence_present_v2_probe_envelope_exposes_repair_intent_evidence_only() -> None:
    from rook.agent.local_worker_turn_request import (
        render_local_worker_turn_request_payload,
    )

    payload = render_local_worker_turn_request_payload(
        PROBE.build_probe_context(PROBE._SCENARIOS["evidence_present_v2"])
    )
    rendered = json.dumps(payload)
    assert "lm5t_repair_intent_evidence" in rendered
    assert "target_errors" in rendered
    assert PROBE.REPAIR_TARGET_ERROR in rendered
    assert "DefinitelyMissingSymbol" in rendered
    assert PROBE.PROBE_COMPONENT_GUID in rendered
    assert "A = DefinitelyMissingSymbol;" in rendered
    assert PROBE.PROBE_REPAIR_CODE not in rendered
    assert "A = 42.0;" not in rendered
    assert "already-bound repair params" not in rendered


def test_lm5n_rendered_current_node_has_no_execution_params() -> None:
    from rook.agent.local_worker_turn_request import (
        render_local_worker_turn_request_payload,
    )

    for scenario in PROBE._SCENARIOS.values():
        payload = render_local_worker_turn_request_payload(
            PROBE.build_probe_context(scenario)
        )
        node = payload["context"]["current_node"]
        assert node["node_id"] == "repair_same_component"
        assert node["has_execution_params"] is False


def test_probe_context_shape_guard_wired() -> None:
    import dataclasses

    context = PROBE.build_probe_context()
    stripped = dataclasses.replace(context, allowed_actions=())
    with pytest.raises(
        RuntimeError, match="allowed action draft_repair_params missing"
    ):
        PROBE._require_probe_context_shape(stripped)
    headless = dataclasses.replace(context, current_node=None)
    with pytest.raises(
        RuntimeError, match="current node is not repair_same_component"
    ):
        PROBE._require_probe_context_shape(headless)


def test_offline_probe_capture_raw(tmp_path) -> None:
    run_dir = PROBE.run_probe(
        _args(tmp_path, attempts=1, capture_raw=True),
        transport_factory=_FakeGoodTransport,
    )
    lines = (run_dir / "attempts.jsonl").read_text().strip().splitlines()
    first = json.loads(lines[0])
    assert first["captured_raw_path"] == "raw/local-0.txt"
    raw_text = (run_dir / "raw" / "local-0.txt").read_text(encoding="utf-8")
    assert '"kind": "action_request"' in raw_text


def test_attempts_must_be_positive(tmp_path) -> None:
    for bad in (0, -3):
        with pytest.raises(ValueError):
            PROBE.run_probe(
                _args(tmp_path, attempts=bad),
                transport_factory=_FakeGoodTransport,
            )
    with pytest.raises(argparse.ArgumentTypeError):
        PROBE._positive_int("0")
    with pytest.raises(argparse.ArgumentTypeError):
        PROBE._positive_int("-2")
    assert PROBE._positive_int("5") == 5


def test_main_rejects_legacy_scenario(monkeypatch) -> None:
    called = []

    def fake_run_probe(args):
        called.append(args)
        return Path("unused")

    monkeypatch.setattr(PROBE, "run_probe", fake_run_probe)
    with pytest.raises(SystemExit):
        PROBE.main(["--scenario", "lm5k_golden_repair_v2"])
    assert called == []


def test_main_accepts_lm5n_scenarios(monkeypatch) -> None:
    seen = []

    def fake_run_probe(args):
        seen.append(args.scenario)
        return Path("unused")

    monkeypatch.setattr(PROBE, "run_probe", fake_run_probe)
    assert PROBE.main(["--scenario", "evidence_absent"]) == 0
    assert PROBE.main(["--scenario", "evidence_present"]) == 0
    assert seen == ["evidence_absent", "evidence_present"]


def test_unavailable_slot_records_no_attempts(tmp_path, monkeypatch) -> None:
    for var in PROBE.ENV_VARS.values():
        monkeypatch.delenv(var, raising=False)
    run_dir = PROBE.run_probe(
        _args(tmp_path, local=None, skip=["ceiling"], attempts=1),
        transport_factory=_FakeGoodTransport,
    )
    manifest = json.loads((run_dir / "manifest.json").read_text())
    by_slot = {p["slot"]: p for p in manifest["panel"]}
    # cheap unresolved (no cli/env, never profile-inferred) -> unavailable
    assert by_slot["cheap"]["status"] == "unavailable"
    assert by_slot["cheap"]["attempts"] == 0
    assert by_slot["ceiling"]["status"] == "skipped"
    attempts_file = run_dir / "attempts.jsonl"
    if by_slot["local"]["status"] in ("unavailable", "skipped"):
        assert not attempts_file.exists()
