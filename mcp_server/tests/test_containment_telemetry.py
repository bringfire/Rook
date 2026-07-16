from __future__ import annotations

import importlib
import json
import os
import re
from copy import deepcopy
from pathlib import Path

import pytest

from rook.tool_lifecycle import (
    DispatchOrigin,
    containment_envelope,
    filter_mcp_records,
    resolve_contained_identity,
)


try:
    runtime = importlib.import_module("rook.tool_lifecycle_runtime")
except ModuleNotFoundError as exc:
    if exc.name != "rook.tool_lifecycle_runtime":
        raise
    runtime = None
    metrics_store = None
    _CONTRACT_MISSING = True
else:
    metrics_store = importlib.import_module("rook.learning.metrics_store")
    _CONTRACT_MISSING = not all(
        hasattr(metrics_store, name)
        for name in ("MetricsStore", "Observation", "get_metrics_store")
    ) or not hasattr(
        metrics_store.MetricsStore,
        "get_containment_denials_snapshot",
    )


def test_containment_telemetry_contract_is_available() -> None:
    assert not _CONTRACT_MISSING, (
        "EXPECTED_RED:T1:TELEMETRY containment telemetry runtime is not implemented"
    )


if runtime is not None and not _CONTRACT_MISSING:
    from rook import server
    from rook.agent import substrate_analytics
    from aiohttp.test_utils import TestClient, TestServer
    from unittest.mock import AsyncMock

    from rook.agent.chat import server as chat_server
    from rook.agent.chat.server import create_chat_app
    from rook.mcp_tool_profiles import PUBLIC_LEAN_TOOL_NAMES

    MetricsStore = metrics_store.MetricsStore
    Observation = metrics_store.Observation

    _TIMESTAMP_RE = re.compile(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$"
    )

    def _entry(name: str = "gh_execute_intent"):
        entry = resolve_contained_identity(name)
        assert entry is not None
        return entry

    def _snapshot_delta(
        before: dict[str, object],
        after: dict[str, object],
    ) -> list[dict[str, str]]:
        assert after["process_id"] == before["process_id"]
        assert after["process_start_token"] == before["process_start_token"]
        before_events = before["events"]
        after_events = after["events"]
        assert isinstance(before_events, list)
        assert isinstance(after_events, list)

        if len(before_events) < 50:
            assert len(after_events) == len(before_events) + 1
            assert after_events[:-1] == before_events
        else:
            assert len(before_events) == len(after_events) == 50
            assert after_events[:-1] == before_events[1:]

        return [after_events[-1]]

    def _observation() -> Observation:
        return Observation(
            tool_name="safe_tool",
            success=True,
            duration_ms=12.5,
            knowledge_injected=False,
            knowledge_hint="",
            gotchas_provided=[],
            correction_detected=False,
            attempt_number=1,
            phase="execute",
            timestamp="2026-07-16T12:34:56.000000+00:00",
            intent="inspect",
        )

    def _set_singleton(monkeypatch, store: MetricsStore) -> None:
        monkeypatch.setattr(metrics_store, "_metrics_store", store)

    def _parse_success_text(contents) -> dict[str, object]:
        assert len(contents) == 1
        assert contents[0].type == "text"
        assert not contents[0].text.startswith("Error: ")
        parsed = json.loads(contents[0].text)
        assert isinstance(parsed, dict)
        return parsed

    def test_snapshot_shape_uses_live_process_identity_and_closed_empty_ring(
        tmp_path: Path,
    ) -> None:
        store = MetricsStore(tmp_path / "metrics.json")
        snapshot = store.get_containment_denials_snapshot()

        assert set(snapshot) == {
            "process_id",
            "process_start_token",
            "events",
        }
        assert snapshot["process_id"] == os.getpid()
        assert re.fullmatch(r"[0-9a-f]{32}", snapshot["process_start_token"])
        assert snapshot["events"] == []

    def test_process_start_token_is_interpreter_owned_not_store_owned(
        monkeypatch,
        tmp_path: Path,
    ) -> None:
        module_token = metrics_store._PROCESS_START_TOKEN

        def unexpected_uuid_call():
            raise AssertionError("store construction must not mint a process token")

        monkeypatch.setattr(metrics_store.uuid, "uuid4", unexpected_uuid_call)
        first = MetricsStore(tmp_path / "first.json")
        second = MetricsStore(tmp_path / "second.json")
        _set_singleton(monkeypatch, first)

        assert first.get_containment_denials_snapshot()["process_start_token"] == module_token
        assert second.get_containment_denials_snapshot()["process_start_token"] == module_token
        assert metrics_store.get_metrics_store() is first
        assert metrics_store.get_metrics_store() is first
        assert (
            metrics_store.get_metrics_store()
            .get_containment_denials_snapshot()["process_start_token"]
            == module_token
        )

    def test_event_has_exact_four_keys_and_utc_microsecond_z_timestamp(
        tmp_path: Path,
    ) -> None:
        store = MetricsStore(tmp_path / "metrics.json")
        store.record_containment_denial(
            _entry("gh_execute_intent"),
            DispatchOrigin.PUBLIC_MCP,
        )
        event = store.get_containment_denials_snapshot()["events"][0]

        assert set(event) == {
            "tool",
            "disposition",
            "origin",
            "timestamp",
        }
        assert event["tool"] == "gh_execute_intent"
        assert event["disposition"] == "retired"
        assert event["origin"] == "public_mcp"
        assert _TIMESTAMP_RE.fullmatch(event["timestamp"])

    def test_dedicated_ring_evicts_only_the_oldest_at_capacity(
        tmp_path: Path,
    ) -> None:
        store = MetricsStore(tmp_path / "metrics.json")
        store.record_containment_denial(
            _entry("gh_execute_intent"),
            DispatchOrigin.PUBLIC_MCP,
        )
        store.record_containment_denial(
            _entry("rhino_execute_intent"),
            DispatchOrigin.SERVER_DISPATCH,
        )
        second = deepcopy(
            store.get_containment_denials_snapshot()["events"][-1]
        )
        for _ in range(48):
            store.record_containment_denial(
                _entry("spawn_agent"),
                DispatchOrigin.ROOK_AGENT,
            )
        before = store.get_containment_denials_snapshot()
        assert len(before["events"]) == 50
        assert before["events"][0]["tool"] == "gh_execute_intent"

        store.record_containment_denial(
            _entry("plan_and_execute"),
            DispatchOrigin.PLAN_GRAPH,
        )
        after = store.get_containment_denials_snapshot()
        added = _snapshot_delta(before, after)

        assert after["events"][0] == second
        assert added[0]["tool"] == "plan_and_execute"
        assert added[0]["origin"] == "plan_graph"

    def test_ring_delta_helper_rejects_pid_or_start_token_change() -> None:
        before = {
            "process_id": 10,
            "process_start_token": "a" * 32,
            "events": [],
        }
        event = {
            "tool": "spawn_agent",
            "disposition": "suspended",
            "origin": "rook_agent",
            "timestamp": "2026-07-16T12:34:56.000000Z",
        }
        with pytest.raises(AssertionError):
            _snapshot_delta(
                before,
                {
                    "process_id": 11,
                    "process_start_token": "a" * 32,
                    "events": [event],
                },
            )
        with pytest.raises(AssertionError):
            _snapshot_delta(
                before,
                {
                    "process_id": 10,
                    "process_start_token": "b" * 32,
                    "events": [event],
                },
            )

    def test_snapshot_is_a_defensive_copy(tmp_path: Path) -> None:
        store = MetricsStore(tmp_path / "metrics.json")
        store.record_containment_denial(
            _entry("spawn_agent"),
            DispatchOrigin.TOOL_DISPATCHER,
        )
        snapshot = store.get_containment_denials_snapshot()
        snapshot["events"][0]["tool"] = "tampered"
        snapshot["events"].append({"unexpected": "event"})

        fresh = store.get_containment_denials_snapshot()
        assert len(fresh["events"]) == 1
        assert fresh["events"][0]["tool"] == "spawn_agent"

    def test_accessor_reads_emit_no_containment_event(tmp_path: Path) -> None:
        store = MetricsStore(tmp_path / "metrics.json")
        store.record_containment_denial(
            _entry("gh_replay_recipe"),
            DispatchOrigin.INTERNAL_HANDLER,
        )
        before = store.get_containment_denials_snapshot()
        middle = store.get_containment_denials_snapshot()
        after = store.get_containment_denials_snapshot()
        assert before == middle == after

    def test_denial_recording_does_not_enter_observation_or_aggregate_paths(
        monkeypatch,
        tmp_path: Path,
    ) -> None:
        store = MetricsStore(tmp_path / "metrics.json")
        recent_before = list(store._recent)
        periods_before = dict(store._periods)
        tools_before = dict(store._tools)
        failures_before = store._recording_failures

        def observation_path_must_not_run(*args, **kwargs):
            raise AssertionError("containment denial must not call record(Observation)")

        def substrate_persistence_must_not_run(*args, **kwargs):
            raise AssertionError(
                "containment denial must not persist a substrate observation"
            )

        monkeypatch.setattr(store, "record", observation_path_must_not_run)
        monkeypatch.setattr(
            substrate_analytics,
            "persist_substrate_observation",
            substrate_persistence_must_not_run,
        )
        store.record_containment_denial(
            _entry("gh_explore_workflow"),
            DispatchOrigin.ROOK_CHAT,
        )

        assert list(store._recent) == recent_before
        assert store._periods == periods_before
        assert store._tools == tools_before
        assert store._recording_failures == failures_before
        assert len(store.get_containment_denials_snapshot()["events"]) == 1

    def test_existing_metrics_json_and_containment_ring_round_trip(
        tmp_path: Path,
    ) -> None:
        path = tmp_path / "metrics.json"
        first = MetricsStore(path)
        first.record(_observation())
        first.record_containment_denial(
            _entry("spawn_agent"),
            DispatchOrigin.INTERNAL_HANDLER,
        )
        first.save()

        persisted = json.loads(path.read_text(encoding="utf-8"))
        assert set(persisted) == {
            "periods",
            "tools",
            "recent",
            "containment_denials",
        }
        assert "process_id" not in persisted
        assert "process_start_token" not in persisted
        assert len(persisted["containment_denials"]) == 1
        assert set(persisted["containment_denials"][0]) == {
            "tool",
            "disposition",
            "origin",
            "timestamp",
        }

        second = MetricsStore(path)
        assert second.get_recent() == first.get_recent()
        assert second.get_tool_metrics() == first.get_tool_metrics()
        assert (
            second.get_containment_denials_snapshot()["events"]
            == first.get_containment_denials_snapshot()["events"]
        )

    def test_pre_containment_metrics_json_loads_and_gains_ring_without_loss(
        tmp_path: Path,
    ) -> None:
        path = tmp_path / "metrics.json"
        legacy = {
            "periods": {},
            "tools": {},
            "recent": [
                {
                    "tool": "safe_tool",
                    "success": True,
                    "duration_ms": 1.0,
                    "knowledge": False,
                    "hint": "",
                    "phase": "execute",
                    "timestamp": "2026-07-16T12:34:56.000000+00:00",
                    "intent": "",
                    "error": "",
                }
            ],
        }
        path.write_text(json.dumps(legacy), encoding="utf-8")

        store = MetricsStore(path)
        assert store.get_recent() == legacy["recent"]
        assert store.get_containment_denials_snapshot()["events"] == []
        store.record_containment_denial(
            _entry("spawn_agent"),
            DispatchOrigin.INTERNAL_HANDLER,
        )
        store.save()

        persisted = json.loads(path.read_text(encoding="utf-8"))
        assert persisted["periods"] == legacy["periods"]
        assert persisted["tools"] == legacy["tools"]
        assert persisted["recent"] == legacy["recent"]
        assert len(persisted["containment_denials"]) == 1

    def test_containment_denials_participate_in_existing_auto_save_lifecycle(
        tmp_path: Path,
    ) -> None:
        path = tmp_path / "metrics.json"
        store = MetricsStore(path)
        for _ in range(10):
            store.record_containment_denial(
                _entry("spawn_agent"),
                DispatchOrigin.INTERNAL_HANDLER,
            )

        assert path.is_file()
        assert store._dirty_count == 0
        persisted = json.loads(path.read_text(encoding="utf-8"))
        assert len(persisted["containment_denials"]) == 10

    def test_runtime_denial_attempts_once_and_appends_one_event_when_healthy(
        monkeypatch,
        tmp_path: Path,
    ) -> None:
        store = MetricsStore(tmp_path / "metrics.json")
        _set_singleton(monkeypatch, store)
        attempts = 0
        real_recorder = runtime._record_containment_denial

        def recording_spy(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            return real_recorder(*args, **kwargs)

        monkeypatch.setattr(runtime, "_record_containment_denial", recording_spy)
        before = store.get_containment_denials_snapshot()
        actual = runtime.deny_if_contained(
            "spawn_agent",
            DispatchOrigin.ROOK_AGENT,
        )
        after = store.get_containment_denials_snapshot()

        assert attempts == 1
        assert actual == containment_envelope(_entry("spawn_agent"))
        added = _snapshot_delta(before, after)
        assert added[0]["tool"] == "spawn_agent"
        assert added[0]["disposition"] == "suspended"
        assert added[0]["origin"] == "rook_agent"

    @pytest.mark.parametrize(
        "raw_name",
        [
            None,
            1,
            b"spawn_agent",
            "spawn_agent ",
            "Spawn_Agent",
            "spawn_agen",
            "safe_tool",
        ],
    )
    def test_runtime_near_matches_do_not_record_or_deny(
        monkeypatch,
        raw_name: object,
    ) -> None:
        attempts = 0

        def unexpected_recording(*args, **kwargs):
            nonlocal attempts
            attempts += 1

        monkeypatch.setattr(
            runtime,
            "_record_containment_denial",
            unexpected_recording,
        )
        assert runtime.deny_if_contained(
            raw_name,
            DispatchOrigin.PUBLIC_MCP,
        ) is None
        assert attempts == 0

    def test_denial_is_unchanged_when_recording_raises(
        monkeypatch,
        tmp_path: Path,
    ) -> None:
        store = MetricsStore(tmp_path / "metrics.json")
        _set_singleton(monkeypatch, store)
        before = store.get_containment_denials_snapshot()
        attempts = 0

        def explode(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            raise OSError("sink unavailable")

        monkeypatch.setattr(runtime, "_record_containment_denial", explode)
        actual = runtime.deny_if_contained(
            "gh_execute_intent",
            DispatchOrigin.PUBLIC_MCP,
        )
        after = store.get_containment_denials_snapshot()

        assert attempts == 1
        assert actual == containment_envelope(_entry("gh_execute_intent"))
        assert after == before

    @pytest.mark.asyncio
    @pytest.mark.parametrize("profile", [None, "lean", "readonly"])
    async def test_metrics_summary_includes_only_its_process_snapshot_when_admitted(
        monkeypatch,
        tmp_path: Path,
        profile: str | None,
    ) -> None:
        own_store = MetricsStore(tmp_path / f"own-{profile}.json")
        own_store.record_containment_denial(
            _entry("gh_execute_intent"),
            DispatchOrigin.PUBLIC_MCP,
        )
        other_store = MetricsStore(tmp_path / f"other-{profile}.json")
        other_store.record_containment_denial(
            _entry("spawn_agent"),
            DispatchOrigin.ROOK_CHAT,
        )
        _set_singleton(monkeypatch, own_store)
        if profile is None:
            monkeypatch.delenv("ROOK_MCP_TOOL_PROFILE", raising=False)
        else:
            monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", profile)

        before = own_store.get_containment_denials_snapshot()
        payload = _parse_success_text(
            await server.call_tool("metrics_summary", {})
        )
        after = own_store.get_containment_denials_snapshot()

        assert payload["containment_denials"] == before
        assert payload["containment_denials"] != (
            other_store.get_containment_denials_snapshot()
        )
        assert after == before
        payload["containment_denials"]["events"][0]["tool"] = "tampered"
        assert (
            own_store.get_containment_denials_snapshot()["events"][0]["tool"]
            == "gh_execute_intent"
        )

    @pytest.mark.asyncio
    async def test_metrics_summary_keeps_ordinary_profile_advertisement_rules(
        monkeypatch,
    ) -> None:
        monkeypatch.delenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", raising=False)

        monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
        full = {tool.name for tool in await server.list_tools()}
        assert "metrics_summary" in full

        monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
        readonly = {tool.name for tool in await server.list_tools()}
        assert "metrics_summary" in readonly

        monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
        raw_lean = await server.list_tools()
        projected_lean = filter_mcp_records(raw_lean)
        assert len(PUBLIC_LEAN_TOOL_NAMES) == 22
        assert len(raw_lean) == 22
        assert len(projected_lean) == 20
        assert "metrics_summary" not in {tool.name for tool in raw_lean}
        assert {
            "gh_execute_intent",
            "rhino_execute_intent",
        }.isdisjoint({tool.name for tool in projected_lean})

    @pytest.mark.asyncio
    async def test_rookchat_uses_accessor_without_endpoint_or_health_leak(
        monkeypatch,
        tmp_path: Path,
    ) -> None:
        store = MetricsStore(tmp_path / "chat-process.json")
        store.record_containment_denial(
            _entry("spawn_agent"),
            DispatchOrigin.ROOK_CHAT,
        )
        _set_singleton(monkeypatch, store)
        direct = metrics_store.get_metrics_store().get_containment_denials_snapshot()
        app = create_chat_app()
        route_paths = {
            route.resource.canonical
            for route in app.router.routes()
            if getattr(route.resource, "canonical", None)
        }

        assert direct["process_id"] == os.getpid()
        assert "/agent/chat/health" in route_paths
        assert not any("containment" in path for path in route_paths)
        assert not any("metrics" in path for path in route_paths)

        monkeypatch.setattr(
            chat_server,
            "collect_runtime_facts",
            AsyncMock(
                return_value={
                    "rhino": {"connected": True, "data": "pong"},
                    "prompt": {
                        "available": True,
                        "is_active": False,
                        "prompt": "Command",
                    },
                    "verified_runtime_facts": [],
                }
            ),
        )
        client = TestClient(TestServer(app))
        await client.start_server()
        try:
            response = await client.get("/agent/chat/health")
            assert response.status == 200
            health = await response.json()
        finally:
            await client.close()

        serialized_health = json.dumps(health, sort_keys=True)
        assert "containment_denials" not in serialized_health
        assert "process_start_token" not in serialized_health
        assert direct["events"][0]["tool"] == "spawn_agent"
