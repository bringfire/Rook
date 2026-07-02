from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import pytest


def _load_script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "lm5k_worker_probe.py"
    spec = importlib.util.spec_from_file_location("lm5k_worker_probe", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PROBE = _load_script()


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


def test_scenario_identity_constants() -> None:
    assert PROBE.SCENARIO_WORKFLOW_ID == "lm5k_first_probe"
    assert PROBE.SCENARIO_ID == "lm5k_golden_repair_v2"
    assert PROBE.SCENARIO_VERSION == "v2"
    assert PROBE.SCENARIO_STATE == "post_verify_needs_repair"


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
                "input": {"code": "A = 42.0;", "mode": "body"},
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


def _args(tmp_path, **overrides):
    values = {
        "local": "ollama_chat/fake:1", "cheap": None, "ceiling": None,
        "skip": ["cheap", "ceiling"], "attempts": 3,
        "capture_raw": False, "run_dir": str(tmp_path),
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_offline_probe_end_to_end_good_transport(tmp_path) -> None:
    run_dir = PROBE.run_probe(
        _args(tmp_path), transport_factory=_FakeGoodTransport
    )
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["generation_params"] == {"temperature": 0}
    assert manifest["prompt_text_version"] == "lm5j.prompt_text:v1"
    # scenario identity: structured block, versioned (spec section 5);
    # the bare scenario_workflow_id string is replaced, not kept alongside
    assert manifest["scenario"] == {
        "workflow_id": "lm5k_first_probe",
        "scenario_id": "lm5k_golden_repair_v2",
        "scenario_version": "v2",
        "state": "post_verify_needs_repair",
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


def test_derived_graph_state_is_coherent_post_verify() -> None:
    scaffold, result = PROBE.derive_probe_graph_state()
    assert result.stop_reason == "max_steps_reached"
    assert result.steps_attempted == 3
    assert [r.execution_kind for r in result.records] == [
        "producer", "verifier", "bind",
    ]
    assert [r.accepted_node_id for r in result.records] == [
        "create_script", "verify_create", "repair_same_component",
    ]
    # create producer record ran/applied with receipt evidence; the receipt
    # is intentionally created_with_errors with verification failed, so
    # "applied" must not be read as "script verified clean" (spec section 6)
    assert result.records[0].ran is True
    graph = result.final_graph
    assert graph.nodes["create_script"].evidence is not None
    # the repair signal lives on the verifier record, asserted separately
    assert result.records[1].verifier_outcome_status == "needs_repair"

    repair = graph.nodes["repair_same_component"]
    assert repair.status == "ready"
    from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY

    params = repair.metadata[EXECUTION_PARAMS_KEY]
    assert params["guid"] == PROBE.PROBE_COMPONENT_GUID
    assert params["mode"] == "body"
    # memory facts are receipt-derived by the producer projection --
    # nothing is hand-injected anymore
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


def test_graph_state_guard_message_repair_not_ready() -> None:
    scaffold, result = PROBE.derive_probe_graph_state()
    result.final_graph.nodes["repair_same_component"].status = "pending"
    with pytest.raises(RuntimeError, match="repair node is not ready"):
        PROBE._require_coherent_graph_state(scaffold, result)


def test_graph_state_guard_message_params_missing() -> None:
    from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY

    scaffold, result = PROBE.derive_probe_graph_state()
    del result.final_graph.nodes["repair_same_component"].metadata[
        EXECUTION_PARAMS_KEY
    ]
    with pytest.raises(
        RuntimeError, match="execution params missing on repair node"
    ):
        PROBE._require_coherent_graph_state(scaffold, result)


def test_graph_state_guard_message_memory_facts_missing() -> None:
    scaffold, result = PROBE.derive_probe_graph_state()
    result.final_graph.memory.facts.clear()
    with pytest.raises(RuntimeError, match="memory facts missing repair anchor"):
        PROBE._require_coherent_graph_state(scaffold, result)


def test_graph_state_guard_message_pre_bind_sequence() -> None:
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
            max_steps=2,
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
    assert node["has_execution_params"] is True
    assert "repair_anchor" in node["memory_keys"]
    assert "component_guid" in node["memory_keys"]

    history = context["history"]
    assert history["current_step_count"] == 3
    assert [
        step["execution_kind"] for step in history["recent_steps"]
    ] == ["producer", "verifier", "bind"]
    assert [
        step["accepted_node_id"] for step in history["recent_steps"]
    ] == ["create_script", "verify_create", "repair_same_component"]

    action_ids = [a["action_id"] for a in context["allowed_actions"]]
    assert "draft_repair_params" in action_ids


def test_probe_envelope_never_exposes_internal_values() -> None:
    # The visibility boundary itself (spec section 3.5): bound execution
    # param values and memory fact values must NOT appear anywhere in the
    # rendered request payload — the worker sees has_execution_params and
    # memory_keys, not payloads.
    from rook.agent.local_worker_turn_request import (
        render_local_worker_turn_request_payload,
    )

    payload = render_local_worker_turn_request_payload(
        PROBE.build_probe_context()
    )
    rendered = json.dumps(payload)
    assert PROBE.PROBE_COMPONENT_GUID not in rendered
    assert "A = 42.0;" not in rendered


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
