from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from types import SimpleNamespace

import pytest

from rook import tool_lifecycle_runtime
from rook.agent import base_agent as base_agent_module
from rook.agent.base_agent import RookAgent
from rook.agent.config import AgentConfig
from rook.agent.events import TOOL_EXEC_END, TOOL_EXEC_START, TURN_END
from rook.tool_lifecycle import (
    DispatchOrigin,
    containment_envelope,
    contained_names,
    resolve_contained_identity,
)


EXPECTED_RED = "EXPECTED_RED:T5:AGENT_PROTOCOLS"
CONTAINED_NAMES = tuple(sorted(contained_names()))


def _entry(name: str):
    entry = resolve_contained_identity(name)
    assert entry is not None, EXPECTED_RED
    return entry


def _expected_envelope(name: str) -> dict[str, object]:
    return containment_envelope(_entry(name))


def _compact_envelope(name: str) -> str:
    return json.dumps(_expected_envelope(name), separators=(",", ":"))


def _tool_call(name: str, arguments: str, call_id: str):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _model_response(*tool_calls, content: str | None = None):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    role="assistant",
                    content=content,
                    tool_calls=list(tool_calls),
                )
            )
        ],
        usage=None,
    )


def _agent_config(**overrides) -> AgentConfig:
    values = {
        "max_turns": 4,
        "max_tool_calls_per_turn": 4,
        "knowledge_injection": False,
        "parameter_correction": True,
        "observation_recording": False,
        "tool_surface_adaptation": False,
    }
    values.update(overrides)
    return AgentConfig(**values)


def _telemetry_probe(monkeypatch, tmp_path):
    from rook.learning import metrics_store

    store = metrics_store.MetricsStore(tmp_path / "metrics.json")
    monkeypatch.setattr(metrics_store, "_metrics_store", store)
    attempts: list[tuple[str, str]] = []
    real_recorder = tool_lifecycle_runtime._record_containment_denial

    def recording_spy(entry, origin):
        attempts.append((entry.name, origin.value))
        return real_recorder(entry, origin)

    monkeypatch.setattr(
        tool_lifecycle_runtime,
        "_record_containment_denial",
        recording_spy,
    )
    return store, attempts


def _snapshot_delta(
    before: dict[str, object],
    after: dict[str, object],
) -> list[dict[str, str]]:
    assert before["process_id"] == after["process_id"], EXPECTED_RED
    assert (
        before["process_start_token"] == after["process_start_token"]
    ), EXPECTED_RED
    before_events = before["events"]
    after_events = after["events"]
    assert isinstance(before_events, list), EXPECTED_RED
    assert isinstance(after_events, list), EXPECTED_RED
    assert len(before_events) < 50, EXPECTED_RED
    assert after_events[: len(before_events)] == before_events, EXPECTED_RED
    return after_events[len(before_events):]


def _assert_one_denial(
    store,
    attempts: list[tuple[str, str]],
    before: dict[str, object],
    *,
    name: str,
    origin: DispatchOrigin,
) -> None:
    assert attempts == [(name, origin.value)], EXPECTED_RED
    added = _snapshot_delta(
        before,
        store.get_containment_denials_snapshot(),
    )
    assert len(added) == 1, EXPECTED_RED
    event = added[0]
    assert set(event) == {
        "tool",
        "disposition",
        "origin",
        "timestamp",
    }, EXPECTED_RED
    assert event["tool"] == name, EXPECTED_RED
    assert event["disposition"] == _entry(name).disposition.value, EXPECTED_RED
    assert event["origin"] == origin.value, EXPECTED_RED


def _install_model(agent: RookAgent, responses: list[object]):
    model_calls: list[list[dict]] = []

    async def call_model(context):
        model_calls.append(list(context))
        return responses.pop(0) if responses else None

    agent._call_model = call_model
    agent._track_usage = lambda _response: None
    return model_calls


@pytest.mark.asyncio
@pytest.mark.parametrize("skip_mode", ("abort", "steering", "budget"))
async def test_rook_agent_skips_before_containment_and_argument_decode(
    monkeypatch,
    tmp_path,
    skip_mode,
):
    contained_name = "gh_execute_intent"
    denied_arguments = '{"must_not_decode":"skip"}'
    safe_arguments = '{"safe":true}'
    executor_calls: list[tuple[str, dict]] = []
    events = []
    parsed_arguments: list[object] = []

    agent: RookAgent

    async def executor(name, params):
        executor_calls.append((name, params))
        if skip_mode == "steering":
            agent._steering_queue.append("redirect now")
        return {"success": True}

    agent = RookAgent(
        config=_agent_config(
            max_tool_calls_per_turn=0 if skip_mode == "budget" else 4
        ),
        tool_executor=executor,
    )
    agent.subscribe(events.append)

    calls = []
    if skip_mode == "steering":
        calls.append(_tool_call("safe_tool", safe_arguments, "call_safe"))
    calls.append(_tool_call(contained_name, denied_arguments, "call_skip"))
    responses = [_model_response(*calls)]
    if skip_mode != "abort":
        responses.append(_model_response(content="continued"))
    model_calls = _install_model(agent, responses)

    if skip_mode == "abort":
        original_call_model = agent._call_model

        async def aborting_call_model(context):
            response = await original_call_model(context)
            agent._abort = True
            return response

        agent._call_model = aborting_call_model

    real_loads = json.loads

    def tracking_loads(raw, *_args, **_kwargs):
        parsed_arguments.append(raw)
        return {}

    monkeypatch.setattr(base_agent_module.json, "loads", tracking_loads)
    store, attempts = _telemetry_probe(monkeypatch, tmp_path)
    before = store.get_containment_denials_snapshot()

    await agent.prompt("exercise skip ordering")

    expected_parsed = [safe_arguments] if skip_mode == "steering" else []
    skipped = [
        message
        for message in agent.messages
        if message.get("role") == "tool"
        and message.get("tool_call_id") == "call_skip"
    ]
    denied_tool_events = [
        event
        for event in events
        if event.type in {TOOL_EXEC_START, TOOL_EXEC_END}
        and event.data.get("call_id") == "call_skip"
    ]
    after = store.get_containment_denials_snapshot()

    assert (
        parsed_arguments == expected_parsed
        and len(skipped) == 1
        and real_loads(skipped[0]["content"]).get("skipped") is True
        and denied_tool_events == []
        and attempts == []
        and after == before
        and len(model_calls) == (1 if skip_mode == "abort" else 2)
    ), f"{EXPECTED_RED} {skip_mode} skip reached containment or argument parsing"


@pytest.mark.asyncio
@pytest.mark.parametrize("contained_name", CONTAINED_NAMES)
async def test_rook_agent_denial_is_one_protocol_result_and_primary_model_continues(
    monkeypatch,
    tmp_path,
    contained_name,
):
    raw_arguments = '{"private":"assistant-protocol-only"}'
    executor_calls: list[tuple[str, dict]] = []
    parse_calls: list[object] = []
    gotcha_calls: list[tuple[str, object]] = []
    observation_calls: list[tuple[str, object, object]] = []
    substrate_calls: list[str] = []
    persist_calls: list[object] = []
    adapt_calls: list[set[str]] = []
    events = []

    async def executor(name, params):
        executor_calls.append((name, params))
        return {"success": False, "error": "must not execute"}

    agent = RookAgent(config=_agent_config(), tool_executor=executor)
    agent.subscribe(events.append)
    model_calls = _install_model(
        agent,
        [
            _model_response(
                _tool_call(contained_name, raw_arguments, "call_denied")
            ),
            _model_response(content="recovered after refusal"),
        ],
    )

    def tracking_loads(raw, *_args, **_kwargs):
        parse_calls.append(raw)
        return {}

    def tracking_gotchas(name, params):
        gotcha_calls.append((name, params))
        return None

    def tracking_observation(name, params, result, **_kwargs):
        observation_calls.append((name, params, result))

    def tracking_substrate(name, _result):
        substrate_calls.append(name)
        return None

    monkeypatch.setattr(base_agent_module.json, "loads", tracking_loads)
    monkeypatch.setattr(
        base_agent_module,
        "extract_substrate_observation",
        tracking_substrate,
    )
    monkeypatch.setattr(
        base_agent_module,
        "persist_substrate_observation",
        lambda *args, **kwargs: persist_calls.append((args, kwargs)),
    )
    agent._check_blocking_gotchas = tracking_gotchas
    agent._record_observation = tracking_observation
    agent._post_turn_adapt = lambda names: adapt_calls.append(set(names))

    store, attempts = _telemetry_probe(monkeypatch, tmp_path)
    before = store.get_containment_denials_snapshot()

    await agent.prompt("deny one contained identity")

    denial_messages = [
        message
        for message in agent.messages
        if message.get("role") == "tool"
        and message.get("tool_call_id") == "call_denied"
    ]
    assistant_call = next(
        message
        for message in agent.messages
        if message.get("role") == "assistant" and message.get("tool_calls")
    )
    denied_events = [
        event
        for event in events
        if event.type in {TOOL_EXEC_START, TOOL_EXEC_END}
        and event.data.get("call_id") == "call_denied"
    ]
    first_turn_end = next(event for event in events if event.type == TURN_END)

    assert len(denial_messages) == 1, EXPECTED_RED
    assert denial_messages[0]["content"] == _compact_envelope(contained_name), EXPECTED_RED
    assert (
        assistant_call["tool_calls"][0]["function"]["arguments"] == raw_arguments
    ), EXPECTED_RED
    assert raw_arguments not in denial_messages[0]["content"], EXPECTED_RED
    assert parse_calls == [], EXPECTED_RED
    assert executor_calls == [], EXPECTED_RED
    assert gotcha_calls == [], EXPECTED_RED
    assert observation_calls == [], EXPECTED_RED
    assert substrate_calls == [], EXPECTED_RED
    assert persist_calls == [], EXPECTED_RED
    assert adapt_calls == [], EXPECTED_RED
    assert denied_events == [], EXPECTED_RED
    assert contained_name not in agent._failure_counts, EXPECTED_RED
    assert len(model_calls) == 2, EXPECTED_RED
    assert first_turn_end.data["tool_calls"] == 1, EXPECTED_RED
    assert first_turn_end.data["tools_used"] == [], EXPECTED_RED
    _assert_one_denial(
        store,
        attempts,
        before,
        name=contained_name,
        origin=DispatchOrigin.ROOK_AGENT,
    )


@pytest.mark.asyncio
async def test_rook_agent_mixed_round_adapts_once_with_admitted_names_only(
    monkeypatch,
    tmp_path,
):
    contained_name = "spawn_agent"
    denied_arguments = '{"private":"denied"}'
    safe_arguments = '{"value":1}'
    executor_calls: list[tuple[str, dict]] = []
    parse_calls: list[object] = []
    observation_names: list[str] = []
    substrate_names: list[str] = []
    adapt_calls: list[set[str]] = []
    events = []

    async def executor(name, params):
        executor_calls.append((name, params))
        if name == contained_name:
            return {"success": False, "error": "must not execute"}
        return {"success": True, "data": {"value": 1}}

    agent = RookAgent(config=_agent_config(), tool_executor=executor)
    agent.subscribe(events.append)
    model_calls = _install_model(
        agent,
        [
            _model_response(
                _tool_call(contained_name, denied_arguments, "call_denied"),
                _tool_call("safe_tool", safe_arguments, "call_safe"),
            ),
            _model_response(content="continued"),
        ],
    )

    def tracking_loads(raw, *_args, **_kwargs):
        parse_calls.append(raw)
        return {"value": 1} if raw == safe_arguments else {"private": "denied"}

    monkeypatch.setattr(base_agent_module.json, "loads", tracking_loads)
    monkeypatch.setattr(
        base_agent_module,
        "extract_substrate_observation",
        lambda name, _result: substrate_names.append(name) or None,
    )
    agent._check_blocking_gotchas = lambda _name, _params: None
    agent._record_observation = (
        lambda name, _params, _result, **_kwargs: observation_names.append(name)
    )
    agent._post_turn_adapt = lambda names: adapt_calls.append(set(names))

    store, attempts = _telemetry_probe(monkeypatch, tmp_path)
    before = store.get_containment_denials_snapshot()

    await agent.prompt("mixed contained and admitted calls")

    first_turn_end = next(event for event in events if event.type == TURN_END)
    denied_events = [
        event
        for event in events
        if event.type in {TOOL_EXEC_START, TOOL_EXEC_END}
        and event.data.get("call_id") == "call_denied"
    ]
    safe_events = [
        event
        for event in events
        if event.type in {TOOL_EXEC_START, TOOL_EXEC_END}
        and event.data.get("call_id") == "call_safe"
    ]
    denial_message = next(
        message
        for message in agent.messages
        if message.get("tool_call_id") == "call_denied"
    )

    assert parse_calls == [safe_arguments], EXPECTED_RED
    assert executor_calls == [("safe_tool", {"value": 1})], EXPECTED_RED
    assert observation_names == ["safe_tool"], EXPECTED_RED
    assert substrate_names == ["safe_tool"], EXPECTED_RED
    assert adapt_calls == [{"safe_tool"}], EXPECTED_RED
    assert denied_events == [], EXPECTED_RED
    assert len(safe_events) == 2, EXPECTED_RED
    assert denial_message["content"] == _compact_envelope(contained_name), EXPECTED_RED
    assert contained_name not in agent._failure_counts, EXPECTED_RED
    assert first_turn_end.data["tool_calls"] == 2, EXPECTED_RED
    assert set(first_turn_end.data["tools_used"]) == {"safe_tool"}, EXPECTED_RED
    assert len(model_calls) == 2, EXPECTED_RED
    _assert_one_denial(
        store,
        attempts,
        before,
        name=contained_name,
        origin=DispatchOrigin.ROOK_AGENT,
    )


class _PoisonParams(Mapping[str, object]):
    def _fail(self, action: str):
        raise AssertionError(f"{EXPECTED_RED} direct params accessed via {action}")

    def __getitem__(self, key: str) -> object:
        return self._fail(f"getitem:{key}")

    def __iter__(self) -> Iterator[str]:
        return self._fail("iter")

    def __len__(self) -> int:
        return self._fail("len")

    def get(self, key: str, default: object = None) -> object:
        return self._fail(f"get:{key}")

    def items(self):
        return self._fail("items")

    def keys(self):
        return self._fail("keys")

    def values(self):
        return self._fail("values")

    def __copy__(self):
        return self._fail("copy")

    def __deepcopy__(self, memo):
        return self._fail("deepcopy")


class _PoisonRegistry:
    def is_meta_tool(self, _name):
        raise AssertionError(f"{EXPECTED_RED} direct guard reached registry lookup")


class _PoisonLocals(Mapping[str, object]):
    def __getitem__(self, key: str) -> object:
        raise AssertionError(
            f"{EXPECTED_RED} direct local guard reached local lookup:{key}"
        )

    def __iter__(self) -> Iterator[str]:
        raise AssertionError(f"{EXPECTED_RED} direct local guard iterated locals")

    def __len__(self) -> int:
        raise AssertionError(f"{EXPECTED_RED} direct local guard sized locals")


@pytest.mark.asyncio
@pytest.mark.parametrize("contained_name", CONTAINED_NAMES)
async def test_execute_tool_direct_seam_denies_before_any_lookup_or_params(
    monkeypatch,
    tmp_path,
    contained_name,
):
    executor_calls = []

    async def executor(*args, **kwargs):
        executor_calls.append((args, kwargs))
        raise AssertionError(f"{EXPECTED_RED} direct guard reached executor")

    agent = RookAgent(config=_agent_config(), tool_executor=executor)
    agent._tool_registry = _PoisonRegistry()
    agent._local_tools = _PoisonLocals()
    agent._check_blocking_gotchas = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError(f"{EXPECTED_RED} direct guard reached gotchas")
    )
    agent._record_observation = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError(f"{EXPECTED_RED} direct guard reached observation")
    )
    store, attempts = _telemetry_probe(monkeypatch, tmp_path)
    before = store.get_containment_denials_snapshot()

    result = await agent._execute_tool(contained_name, _PoisonParams())

    assert result == _expected_envelope(contained_name), EXPECTED_RED
    assert executor_calls == [], EXPECTED_RED
    assert agent._failure_counts == {}, EXPECTED_RED
    _assert_one_denial(
        store,
        attempts,
        before,
        name=contained_name,
        origin=DispatchOrigin.ROOK_AGENT,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("contained_name", CONTAINED_NAMES)
async def test_execute_local_tool_direct_seam_denies_before_local_lookup_or_params(
    monkeypatch,
    tmp_path,
    contained_name,
):
    agent = RookAgent(config=_agent_config(), tool_executor=lambda *_args: {})
    agent._local_tools = _PoisonLocals()
    store, attempts = _telemetry_probe(monkeypatch, tmp_path)
    before = store.get_containment_denials_snapshot()

    result = await agent._execute_local_tool(contained_name, _PoisonParams())

    assert result == _expected_envelope(contained_name), EXPECTED_RED
    assert agent._failure_counts == {}, EXPECTED_RED
    _assert_one_denial(
        store,
        attempts,
        before,
        name=contained_name,
        origin=DispatchOrigin.ROOK_AGENT,
    )
