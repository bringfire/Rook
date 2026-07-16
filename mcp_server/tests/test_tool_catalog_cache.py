from __future__ import annotations

import asyncio
import importlib
import inspect
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from rook.tool_lifecycle import contained_names, lifecycle_fingerprint


tool_registry = importlib.import_module("rook.agent.tool_registry")
_CACHE_CONTRACT_NAMES = (
    "CatalogCacheState",
    "CatalogStartupResult",
    "load_catalog_cache_state",
    "load_catalog_from_cache",
    "save_catalog_to_cache",
    "refresh_catalog_at_startup",
)
_CACHE_CONTRACT_AVAILABLE = all(
    hasattr(tool_registry, name) for name in _CACHE_CONTRACT_NAMES
)
_AGENT_MANAGEMENT_NAMES = frozenset({
    "spawn_agent",
    "plan_and_execute",
    "agent_status",
    "agent_abort",
    "agent_answer",
})


def test_catalog_cache_contract_is_available():
    assert _CACHE_CONTRACT_AVAILABLE, (
        "EXPECTED_RED:T2:PYTEST safe catalog cache/startup contract is missing"
    )


def _schema(name: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": name,
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    }


def _mcp_tool(name: str):
    return SimpleNamespace(
        name=name,
        description=name,
        inputSchema={"type": "object", "properties": {}},
    )


def _telemetry_store(monkeypatch, tmp_path: Path):
    from rook.learning import metrics_store

    store = metrics_store.MetricsStore(tmp_path / "metrics.json")
    monkeypatch.setattr(metrics_store, "_metrics_store", store)
    return store


if _CACHE_CONTRACT_AVAILABLE:
    CatalogCacheState = tool_registry.CatalogCacheState
    CatalogStartupResult = tool_registry.CatalogStartupResult
    load_catalog_cache_state = tool_registry.load_catalog_cache_state
    load_catalog_from_cache = tool_registry.load_catalog_from_cache
    save_catalog_to_cache = tool_registry.save_catalog_to_cache
    refresh_catalog_at_startup = tool_registry.refresh_catalog_at_startup

    def test_build_catalog_from_mcp_tools_filters_contained_records_without_telemetry(
        monkeypatch,
        tmp_path,
    ):
        store = _telemetry_store(monkeypatch, tmp_path)
        before = store.get_containment_denials_snapshot()
        catalog = tool_registry.build_catalog_from_mcp_tools(
            [
                _mcp_tool("safe_tool"),
                _mcp_tool("spawn_agent"),
                _mcp_tool("gh_replay_recipe"),
            ]
        )
        after = store.get_containment_denials_snapshot()

        assert (
            set(catalog) == {"safe_tool"}
            and after == before
        ), "EXPECTED_RED:T2:PYTEST MCP catalog builder admits contained tools"

    def test_matching_fingerprint_still_revalidates_contained_cache_records(
        monkeypatch,
        tmp_path,
    ):
        store = _telemetry_store(monkeypatch, tmp_path)
        cache = tmp_path / "catalog.json"
        cache.write_text(
            json.dumps(
                {
                    "lifecycle_fingerprint": lifecycle_fingerprint(),
                    "catalog": {
                        "safe_tool": _schema("safe_tool"),
                        "spawn_agent": _schema("safe_embedded"),
                        "safe_raw_hidden_embedded": _schema(
                            "gh_replay_recipe"
                        ),
                    },
                }
            ),
            encoding="utf-8",
        )
        before = store.get_containment_denials_snapshot()
        state = load_catalog_cache_state(cache)
        after = store.get_containment_denials_snapshot()

        assert (
            state.source == "current"
            and state.refresh_requested is False
            and set(state.catalog or {}) == {"safe_tool"}
            and after == before
        ), "EXPECTED_RED:T2:PYTEST matching cache fingerprint bypasses revalidation"

    def test_legacy_plain_mapping_is_readable_and_requests_refresh(
        monkeypatch,
        tmp_path,
    ):
        store = _telemetry_store(monkeypatch, tmp_path)
        cache = tmp_path / "legacy.json"
        cache.write_text(
            json.dumps(
                {
                    "safe_tool": _schema("safe_tool"),
                    "plan_and_execute": _schema("safe_embedded"),
                    "safe_raw_hidden_embedded": _schema(
                        "gh_explore_workflow"
                    ),
                }
            ),
            encoding="utf-8",
        )
        before = store.get_containment_denials_snapshot()
        state = load_catalog_cache_state(cache)
        after = store.get_containment_denials_snapshot()

        assert (
            state.source == "legacy"
            and state.refresh_requested is True
            and set(state.catalog or {}) == {"safe_tool"}
            and after == before
        ), "EXPECTED_RED:T2:PYTEST legacy cache is not safely revalidated"

    def test_changed_lifecycle_fingerprint_requests_refresh(tmp_path):
        cache = tmp_path / "changed.json"
        cache.write_text(
            json.dumps(
                {
                    "lifecycle_fingerprint": "0" * 64,
                    "catalog": {"safe_tool": _schema("safe_tool")},
                }
            ),
            encoding="utf-8",
        )

        state = load_catalog_cache_state(cache)

        assert (
            state.source == "fingerprint_mismatch"
            and state.refresh_requested is True
            and set(state.catalog or {}) == {"safe_tool"}
        ), "EXPECTED_RED:T2:PYTEST changed cache fingerprint does not request refresh"

    @pytest.mark.parametrize(
        "payload",
        [
            "not-json",
            json.dumps([_schema("safe_tool")]),
            json.dumps({}),
            json.dumps(
                {
                    "lifecycle_fingerprint": lifecycle_fingerprint(),
                    "catalog": {},
                }
            ),
        ],
        ids=["corrupt", "wrong-type", "legacy-empty", "envelope-empty"],
    )
    def test_corrupt_wrong_type_and_empty_cache_are_unreadable(
        tmp_path,
        payload,
    ):
        cache = tmp_path / "bad.json"
        cache.write_text(payload, encoding="utf-8")

        state = load_catalog_cache_state(cache)

        assert (
            state.catalog is None
            and state.source == "unreadable"
            and state.refresh_requested is True
        ), "EXPECTED_RED:T2:PYTEST invalid or empty cache is treated as usable"

    def test_missing_cache_reports_missing_and_requests_refresh(tmp_path):
        state = load_catalog_cache_state(tmp_path / "missing.json")

        assert (
            state.catalog is None
            and state.source == "missing"
            and state.refresh_requested is True
        ), "EXPECTED_RED:T2:PYTEST missing cache state is not explicit"

    def test_load_catalog_wrapper_returns_only_safe_normalized_catalog(
        monkeypatch,
        tmp_path,
    ):
        store = _telemetry_store(monkeypatch, tmp_path)
        cache = tmp_path / "catalog.json"
        cache.write_text(
            json.dumps(
                {
                    "lifecycle_fingerprint": lifecycle_fingerprint(),
                    "catalog": {
                        "safe_tool": _schema("safe_tool"),
                        "spawn_agent": _schema("safe_embedded"),
                        "safe_raw_hidden_embedded": _schema("gh_replay_recipe"),
                    },
                }
            ),
            encoding="utf-8",
        )
        before = store.get_containment_denials_snapshot()
        catalog = load_catalog_from_cache(cache)
        after = store.get_containment_denials_snapshot()

        assert (
            set(catalog or {}) == {"safe_tool"}
            and after == before
        ), "EXPECTED_RED:T2:PYTEST cache wrapper exposes contained records"

    def test_save_filters_before_persistence_without_mutating_caller(
        monkeypatch,
        tmp_path,
    ):
        store = _telemetry_store(monkeypatch, tmp_path)
        cache = tmp_path / "catalog.json"
        dirty = {
            "safe_tool": _schema("safe_tool"),
            "spawn_agent": _schema("safe_embedded"),
            "safe_raw_hidden_embedded": _schema("gh_replay_recipe"),
        }
        original = deepcopy(dirty)
        before = store.get_containment_denials_snapshot()
        saved = save_catalog_to_cache(dirty, cache)
        after = store.get_containment_denials_snapshot()
        persisted = json.loads(cache.read_text(encoding="utf-8"))

        assert (
            saved is True
            and set(persisted) == {"lifecycle_fingerprint", "catalog"}
            and persisted["lifecycle_fingerprint"] == lifecycle_fingerprint()
            and set(persisted["catalog"]) == {"safe_tool"}
            and dirty == original
            and after == before
        ), "EXPECTED_RED:T2:PYTEST save path persists dirty contained records"

    @pytest.mark.asyncio
    async def test_refresh_success_persists_and_returns_fresh_catalog(tmp_path):
        cache = tmp_path / "catalog.json"
        loader = AsyncMock(
            return_value=[
                _mcp_tool("safe_tool"),
                _mcp_tool("spawn_agent"),
            ]
        )

        result = await refresh_catalog_at_startup(
            loader,
            cache_path=cache,
        )
        persisted = json.loads(cache.read_text(encoding="utf-8"))

        assert (
            result.status == "fresh"
            and result.persisted is True
            and result.refresh_requested is False
            and set(result.catalog or {}) == {"safe_tool"}
            and set(persisted["catalog"]) == {"safe_tool"}
            and loader.await_count == 1
        ), "EXPECTED_RED:T2:PYTEST startup refresh does not persist safe fresh catalog"

    @pytest.mark.asyncio
    async def test_fresh_construction_survives_persistence_failure(
        monkeypatch,
        tmp_path,
    ):
        monkeypatch.setattr(
            tool_registry,
            "save_catalog_to_cache",
            lambda *_args, **_kwargs: False,
        )
        loader = AsyncMock(return_value=[_mcp_tool("safe_tool")])

        result = await refresh_catalog_at_startup(
            loader,
            cache_path=tmp_path / "catalog.json",
        )

        assert (
            result.status == "degraded_cache"
            and result.persisted is False
            and result.refresh_requested is True
            and set(result.catalog or {}) == {"safe_tool"}
        ), "EXPECTED_RED:T2:PYTEST persistence failure discards fresh in-memory catalog"

    @pytest.mark.asyncio
    async def test_construction_failure_retains_only_revalidated_older_cache(
        monkeypatch,
        tmp_path,
    ):
        store = _telemetry_store(monkeypatch, tmp_path)
        cache = tmp_path / "catalog.json"
        cache.write_text(
            json.dumps(
                {
                    "lifecycle_fingerprint": lifecycle_fingerprint(),
                    "catalog": {
                        "safe_cached": _schema("safe_cached"),
                        "spawn_agent": _schema("safe_embedded"),
                    },
                }
            ),
            encoding="utf-8",
        )
        loader = AsyncMock(side_effect=RuntimeError("construction failed"))
        before = store.get_containment_denials_snapshot()

        result = await refresh_catalog_at_startup(
            loader,
            cache_path=cache,
            fallback={"safe_fallback": _schema("safe_fallback")},
        )
        after = store.get_containment_denials_snapshot()

        assert (
            result.status == "degraded_cache"
            and set(result.catalog or {}) == {"safe_cached"}
            and result.persisted is False
            and result.refresh_requested is True
            and after == before
        ), "EXPECTED_RED:T2:PYTEST failed refresh does not retain safe old cache"

    @pytest.mark.asyncio
    async def test_rejected_cache_content_never_merges_into_fallback(tmp_path):
        cache = tmp_path / "catalog.json"
        cache.write_text(
            json.dumps(
                {
                    "lifecycle_fingerprint": lifecycle_fingerprint(),
                    "catalog": ["rejected-cache-content"],
                }
            ),
            encoding="utf-8",
        )
        loader = AsyncMock(side_effect=RuntimeError("construction failed"))

        result = await refresh_catalog_at_startup(
            loader,
            cache_path=cache,
            fallback={"safe_fallback": _schema("safe_fallback")},
        )

        assert (
            result.status == "degraded_fallback"
            and set(result.catalog or {}) == {"safe_fallback"}
            and "rejected-cache-content" not in repr(result.catalog)
        ), "EXPECTED_RED:T2:PYTEST rejected cache content merges into fallback"

    @pytest.mark.asyncio
    async def test_no_safe_cache_uses_only_filtered_code_owned_fallback(
        monkeypatch,
        tmp_path,
    ):
        store = _telemetry_store(monkeypatch, tmp_path)
        loader = AsyncMock(side_effect=RuntimeError("construction failed"))
        fallback = {
            "safe_fallback": _schema("safe_fallback"),
            "plan_and_execute": _schema("safe_embedded"),
            "safe_raw_hidden_embedded": _schema("gh_explore_workflow"),
        }
        before = store.get_containment_denials_snapshot()

        result = await refresh_catalog_at_startup(
            loader,
            cache_path=tmp_path / "missing.json",
            fallback=fallback,
        )
        after = store.get_containment_denials_snapshot()

        assert (
            result.status == "degraded_fallback"
            and set(result.catalog or {}) == {"safe_fallback"}
            and result.persisted is False
            and result.refresh_requested is True
            and after == before
        ), "EXPECTED_RED:T2:PYTEST fallback catalog is not lifecycle-filtered"

    @pytest.mark.asyncio
    async def test_no_safe_cache_or_fallback_returns_explicit_unavailable(
        tmp_path,
    ):
        result = await refresh_catalog_at_startup(
            AsyncMock(side_effect=RuntimeError("construction failed")),
            cache_path=tmp_path / "missing.json",
        )

        assert (
            result.status == "unavailable"
            and result.catalog is None
            and result.persisted is False
            and result.refresh_requested is True
        ), "EXPECTED_RED:T2:PYTEST unavailable startup silently returns empty catalog"

    def test_list_tools_performs_no_catalog_write(monkeypatch):
        from rook import server

        writer = MagicMock(side_effect=AssertionError("list_tools wrote cache"))
        monkeypatch.setattr(tool_registry, "save_catalog_to_cache", writer)

        asyncio.run(server.list_tools())

        assert writer.call_count == 0

    def test_agent_handlers_do_not_write_cache_and_keep_management_exclusions():
        from rook import server

        spawn_source = inspect.getsource(server._handle_spawn_agent)
        plan_source = inspect.getsource(server._handle_plan_and_execute)

        assert (
            "save_catalog_to_cache" not in spawn_source
            and "save_catalog_to_cache" not in plan_source
            and "_AGENT_MANAGEMENT_TOOLS" in spawn_source
            and "_AGENT_MANAGEMENT_TOOLS" in plan_source
        ), "EXPECTED_RED:T2:PYTEST agent handlers still write catalog cache"

    @pytest.mark.asyncio
    async def test_spawn_cached_catalog_keeps_agent_management_tools_out_of_worker_registry(
        monkeypatch,
        tmp_path,
    ):
        from rook.agent import spawn

        store = _telemetry_store(monkeypatch, tmp_path)
        cached_catalog = {
            "safe_agent_inspect": _schema("safe_agent_inspect"),
            "agent_status": _schema("agent_status"),
            "agent_abort": _schema("agent_abort"),
            "agent_answer": _schema("agent_answer"),
        }
        original_catalog = deepcopy(cached_catalog)
        monkeypatch.setattr(
            tool_registry,
            "load_catalog_cache_state",
            lambda *_args, **_kwargs: CatalogCacheState(
                catalog=cached_catalog,
                refresh_requested=False,
                source="current",
            ),
        )

        agent = MagicMock()
        agent.prompt = AsyncMock()
        agent.wait_for_idle = AsyncMock()
        agent.messages = []
        agent._turn_count = 0
        agent._total_input_tokens = 0
        agent._total_output_tokens = 0
        agent._total_cost = 0.0
        agent.config = SimpleNamespace(model="test-model")
        agent_ctor = MagicMock(return_value=agent)
        monkeypatch.setattr("rook.agent.base_agent.RookAgent", agent_ctor)
        before = store.get_containment_denials_snapshot()

        result = await spawn.run_task(
            "inspect",
            catalog=None,
            tool_executor=AsyncMock(),
            guardian_enabled=False,
            task_id="task-management-cache",
        )

        after = store.get_containment_denials_snapshot()
        worker_registry = agent_ctor.call_args.kwargs["tool_registry"]
        assert (
            result.status == "success"
            and "safe_agent_inspect" in worker_registry._catalog
            and _AGENT_MANAGEMENT_NAMES.isdisjoint(worker_registry._catalog)
            and cached_catalog == original_catalog
            and after == before
        ), "EXPECTED_RED:T2:REVIEW cached worker registry admits management tools"

    @pytest.mark.asyncio
    async def test_planner_injected_catalog_keeps_agent_management_tools_out(
        monkeypatch,
        tmp_path,
    ):
        from rook.agent import spawn

        store = _telemetry_store(monkeypatch, tmp_path)
        injected_catalog = {
            "safe_agent_inspect": _schema("safe_agent_inspect"),
            **{
                name: _schema(name)
                for name in _AGENT_MANAGEMENT_NAMES
            },
        }
        original_catalog = deepcopy(injected_catalog)
        expected_result = object()
        planner = MagicMock()
        planner.run = AsyncMock(return_value=expected_result)
        planner_ctor = MagicMock(return_value=planner)
        monkeypatch.setattr("rook.agent.planner.Planner", planner_ctor)
        before = store.get_containment_denials_snapshot()

        result = await spawn.run_plan(
            "inspect",
            config=MagicMock(),
            catalog=injected_catalog,
            tool_executor=AsyncMock(),
        )

        after = store.get_containment_denials_snapshot()
        planner_catalog = planner_ctor.call_args.kwargs["catalog"]
        assert (
            result is expected_result
            and set(planner_catalog) == {"safe_agent_inspect"}
            and injected_catalog == original_catalog
            and after == before
        ), "EXPECTED_RED:T2:REVIEW injected planner catalog admits management tools"

    def test_mcp_main_refreshes_unprofiled_catalog_once_before_transport(
        monkeypatch,
    ):
        from rook import server

        assert hasattr(server, "refresh_catalog_at_startup"), (
            "EXPECTED_RED:T2:PYTEST MCP startup refresh hook is missing"
        )
        refresh = AsyncMock(
            return_value=CatalogStartupResult(
                catalog=None,
                status="unavailable",
                persisted=False,
                refresh_requested=True,
            )
        )
        transport_run = AsyncMock()

        class FakeStdio:
            async def __aenter__(self):
                return object(), object()

            async def __aexit__(self, *_args):
                return False

        monkeypatch.setattr(server, "refresh_catalog_at_startup", refresh)
        monkeypatch.setattr(server, "stdio_server", lambda: FakeStdio())
        monkeypatch.setattr(server.mcp, "run", transport_run)

        server.main()

        assert (
            refresh.await_count == 1
            and refresh.await_args.args[0] is server._all_live_tools
            and transport_run.await_count == 1
        ), "EXPECTED_RED:T2:PYTEST MCP refresh is profiled, repeated, or kills transport"

    @pytest.mark.asyncio
    async def test_spawn_cache_consumer_returns_catalog_unavailable(
        monkeypatch,
        tmp_path,
    ):
        from rook.agent import spawn

        monkeypatch.setattr(
            tool_registry,
            "load_catalog_cache_state",
            lambda *_args, **_kwargs: CatalogCacheState(
                catalog=None,
                refresh_requested=True,
                source="missing",
            ),
        )
        agent_ctor = MagicMock()
        monkeypatch.setattr("rook.agent.base_agent.RookAgent", agent_ctor)

        result = await spawn.run_task(
            "inspect",
            catalog=None,
            tool_executor=AsyncMock(),
            guardian_enabled=False,
            task_id="task-cache-missing",
        )

        assert (
            result.status == "error"
            and result.failure_reason == "catalog_unavailable"
            and "catalog_unavailable" in result.errors
            and agent_ctor.call_count == 0
        ), "EXPECTED_RED:T2:PYTEST spawn silently constructs empty registry"

    @pytest.mark.asyncio
    async def test_planner_cache_consumer_returns_catalog_unavailable(
        monkeypatch,
    ):
        from rook.agent import spawn

        monkeypatch.setattr(
            tool_registry,
            "load_catalog_cache_state",
            lambda *_args, **_kwargs: CatalogCacheState(
                catalog=None,
                refresh_requested=True,
                source="unreadable",
            ),
        )
        planner_ctor = MagicMock()
        monkeypatch.setattr("rook.agent.planner.Planner", planner_ctor)

        result = await spawn.run_plan("inspect", catalog=None)

        assert (
            result.status == "error"
            and result.summary == "catalog_unavailable"
            and planner_ctor.call_count == 0
        ), "EXPECTED_RED:T2:PYTEST planner silently constructs empty registry"
