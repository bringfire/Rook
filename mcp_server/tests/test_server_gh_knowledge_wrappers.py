import pytest

from rook import server


@pytest.mark.asyncio
async def test_gh_connect_is_advertised_with_direct_connection_schema():
    tools = {tool.name: tool for tool in await server.list_tools()}

    gh_connect = tools["gh_connect"]

    assert gh_connect.inputSchema["required"] == ["sourceGuid", "targetGuid"]
    properties = gh_connect.inputSchema["properties"]
    assert properties["sourceGuid"]["type"] == "string"
    assert properties["targetGuid"]["type"] == "string"
    assert properties["targetParam"]["type"] == "string"
    assert properties["sourceParam"]["type"] == "string"
    assert properties["targetIndex"] == {"type": "integer", "minimum": 0}
    assert properties["sourceIndex"] == {"type": "integer", "minimum": 0}


@pytest.mark.asyncio
async def test_call_tool_dispatches_gh_connect_to_knowledge_wrapper(monkeypatch):
    calls: list[tuple[dict, int | None]] = []

    async def fake_execute_gh_connect_with_knowledge(arguments, port):
        calls.append((dict(arguments), port))
        return {"success": True, "data": {"success": True, "connected": True}}

    monkeypatch.setattr(
        server,
        "_execute_gh_connect_with_knowledge",
        fake_execute_gh_connect_with_knowledge,
    )

    result = await server._call_tool_dispatch(
        "gh_connect",
        {
            "sourceGuid": "SOURCE-GUID",
            "targetGuid": "TARGET-GUID",
            "targetIndex": 7,
        },
    )

    assert result["success"] is True
    assert result["data"]["connected"] is True
    assert calls == [
        (
            {
                "sourceGuid": "SOURCE-GUID",
                "targetGuid": "TARGET-GUID",
                "targetIndex": 7,
            },
            None,
        )
    ]


@pytest.mark.asyncio
async def test_gh_connect_knowledge_wrapper_posts_to_connect_route(
    monkeypatch,
    patch_gh_knowledge,
    patch_session_recording,
):
    calls: list[tuple[str, str, dict, int]] = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        calls.append((route, method, payload, port))
        return {
            "success": True,
            "data": {
                "success": True,
                "connected": True,
                "source": {"guid": "SOURCE-GUID", "param": "Result", "index": 1},
                "target": {"guid": "TARGET-GUID", "param": "I6", "index": 6},
            },
        }

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    result = await server._execute_gh_connect_with_knowledge(
        {
            "sourceGuid": "SOURCE-GUID",
            "targetGuid": "TARGET-GUID",
            "sourceIndex": 1,
            "targetIndex": 6,
        },
        port=64345,
    )

    assert calls == [
        (
            "/gh/connect",
            "POST",
            {
                "sourceGuid": "SOURCE-GUID",
                "targetGuid": "TARGET-GUID",
                "sourceIndex": 1,
                "targetIndex": 6,
            },
            64345,
        )
    ]
    assert result["success"] is True
    assert result["data"]["success"] is True
    assert result["data"]["connected"] is True
    assert result["data"]["correction_detected"] is False
    assert "observation_id" in result["data"]
    assert result["data"]["_entry_id"] == 123
    assert patch_session_recording[0]["params"] == {
        "source": "SOURCE-GUID",
        "target": "TARGET-GUID",
        "sourceIndex": 1,
        "targetIndex": 6,
        "sourceSelector": "index:1",
        "targetSelector": "index:6",
        "param": "index:6",
    }
    assert patch_session_recording[0]["connections_made"] == [
        ("SOURCE-GUID", "index:1", "TARGET-GUID", "index:6")
    ]


@pytest.mark.asyncio
async def test_gh_connect_indexed_failures_keep_distinct_correction_keys(
    monkeypatch,
    patch_gh_knowledge,
    patch_session_recording,
):
    async def fake_call_rhino(_route, method="GET", payload=None, port=None):
        return {"success": False, "data": "connection failed"}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    for target_index in (5, 6):
        await server._execute_gh_connect_with_knowledge(
            {
                "sourceGuid": "SOURCE-GUID",
                "targetGuid": "TARGET-GUID",
                "targetIndex": target_index,
            },
            port=64345,
        )

    assert set(server._recent_gh_failures) == {
        "wire:TARGET-GUID:index:5",
        "wire:TARGET-GUID:index:6",
    }


@pytest.mark.asyncio
async def test_gh_connect_duplicate_is_audited_without_mutation_or_learning_credit(
    monkeypatch,
    patch_gh_knowledge,
    patch_session_recording,
):
    context = {
        "source_guid": "SOURCE-GUID",
        "target_guid": "TARGET-GUID",
        "source_selector": "index:0",
        "target_selector": "index:1",
        "param": "index:1",
    }
    server._track_gh_failure("wire", context, "earlier failure")

    monkeypatch.setattr(
        "rook.learning.gh_knowledge.gh_query_operation",
        lambda _operation, _context: {"gotchas": [{"message": "known gotcha"}]},
    )

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        assert route == "/gh/connect"
        return {
            "success": True,
            "data": {
                "connected": False,
                "noOp": True,
                "reason": "connection_already_exists",
                "source": {"guid": "SOURCE-GUID", "param": "Result", "index": 0},
                "target": {"guid": "TARGET-GUID", "param": "I1", "index": 1},
            },
        }

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    result = await server._execute_gh_connect_with_knowledge(
        {
            "sourceGuid": "SOURCE-GUID",
            "targetGuid": "TARGET-GUID",
            "sourceIndex": 0,
            "targetIndex": 1,
        },
        port=64345,
    )

    assert result["success"] is True
    assert result["data"]["connected"] is False
    assert result["data"]["noOp"] is True
    assert result["data"]["correction_detected"] is False
    assert patch_gh_knowledge.successes == []
    assert "wire:TARGET-GUID:index:1" in server._recent_gh_failures
    assert len(patch_session_recording) == 1
    assert patch_session_recording[0]["connections_made"] is None
    assert patch_session_recording[0]["record_metadata"] == {
        "request_succeeded": True,
        "mutation_committed": False,
        "no_op": True,
    }


@pytest.mark.asyncio
async def test_gh_disconnect_missing_wire_is_audited_without_mutation_or_learning_credit(
    monkeypatch,
    patch_gh_knowledge,
    patch_session_recording,
):
    context = {
        "source_guid": "SOURCE-GUID",
        "target_guid": "TARGET-GUID",
        "source_selector": "index:0",
        "target_selector": "index:2",
        "param": "index:2",
    }
    server._track_gh_failure("disconnect", context, "earlier failure")

    monkeypatch.setattr(
        "rook.learning.gh_knowledge.gh_query_operation",
        lambda _operation, _context: {"gotchas": [{"message": "known gotcha"}]},
    )

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        assert route == "/gh/disconnect"
        return {
            "success": True,
            "data": {
                "disconnected": False,
                "noOp": True,
                "reason": "connection_does_not_exist",
                "source": {"guid": "SOURCE-GUID", "param": "Result", "index": 0},
                "target": {"guid": "TARGET-GUID", "param": "I2", "index": 2},
            },
        }

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    result = await server._execute_gh_disconnect_with_knowledge(
        {
            "sourceGuid": "SOURCE-GUID",
            "targetGuid": "TARGET-GUID",
            "sourceIndex": 0,
            "targetIndex": 2,
        },
        port=64345,
    )

    assert result["success"] is True
    assert result["data"]["disconnected"] is False
    assert result["data"]["noOp"] is True
    assert result["data"]["correction_detected"] is False
    assert patch_gh_knowledge.successes == []
    assert "disconnect:TARGET-GUID:index:2" in server._recent_gh_failures
    assert len(patch_session_recording) == 1
    assert patch_session_recording[0]["connections_removed"] is None
    assert patch_session_recording[0]["record_metadata"] == {
        "request_succeeded": True,
        "mutation_committed": False,
        "no_op": True,
    }


@pytest.mark.asyncio
async def test_gh_disconnect_records_route_resolved_indexed_endpoints(
    monkeypatch,
    patch_gh_knowledge,
    patch_session_recording,
):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        assert route == "/gh/disconnect"
        return {
            "success": True,
            "data": {
                "disconnected": True,
                "source": {"guid": "RESOLVED-SOURCE", "param": "Result", "index": 3},
                "target": {"guid": "RESOLVED-TARGET", "param": "I7", "index": 7},
            },
        }

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    result = await server._execute_gh_disconnect_with_knowledge(
        {
            "sourceGuid": "SOURCE-GUID",
            "targetGuid": "TARGET-GUID",
            "sourceIndex": 3,
            "targetIndex": 7,
        },
        port=64345,
    )

    assert result["data"]["disconnected"] is True
    assert patch_session_recording[0]["connections_removed"] == [
        ("RESOLVED-SOURCE", "index:3", "RESOLVED-TARGET", "index:7")
    ]
    assert patch_session_recording[0]["params"] == {
        "source": "SOURCE-GUID",
        "target": "TARGET-GUID",
        "sourceIndex": 3,
        "targetIndex": 7,
        "sourceSelector": "index:3",
        "targetSelector": "index:7",
        "param": "index:7",
    }
    assert patch_session_recording[0]["record_metadata"] == {
        "request_succeeded": True,
        "mutation_committed": True,
        "no_op": False,
    }


@pytest.mark.asyncio
async def test_connection_outcome_metadata_is_retained_by_session_recorder(monkeypatch):
    recorded: dict = {}

    class _Recorder:
        async def record(self, **kwargs):
            recorded.update(kwargs)
            return 456

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        assert route == "/gh/document"
        return {"success": True, "data": {"name": "audit.gh", "path": "C:/audit.gh"}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(
        "rook.learning.gh_session_history.get_session_recorder",
        lambda: _Recorder(),
    )

    entry_id = await server._record_gh_to_session(
        action="gh_connect",
        params={"source": "A", "target": "B"},
        result={"success": True, "data": {"connected": False, "noOp": True}},
        port=64345,
        record_metadata={
            "request_succeeded": True,
            "mutation_committed": False,
            "no_op": True,
        },
    )

    assert entry_id == 456
    assert recorded["result"].success is True
    assert recorded["result"].outcome == "success"
    assert recorded["result"].connections_made == []
    assert recorded["result"].data == {
        "request_succeeded": True,
        "mutation_committed": False,
        "no_op": True,
    }


class _DummyGhKnowledgeStore:
    def __init__(self) -> None:
        self.successes: list[str] = []

    def record_gotcha_success(self, operation: str) -> None:
        self.successes.append(operation)


@pytest.fixture(autouse=True)
def reset_server_gh_failures():
    if hasattr(server, "_recent_gh_failures"):
        server._recent_gh_failures.clear()
    yield
    if hasattr(server, "_recent_gh_failures"):
        server._recent_gh_failures.clear()


@pytest.fixture
def patch_gh_knowledge(monkeypatch):
    store = _DummyGhKnowledgeStore()

    def fake_query_operation(_operation, _context):
        return {"gotchas": []}

    monkeypatch.setattr("rook.learning.gh_knowledge.gh_query_operation", fake_query_operation)
    monkeypatch.setattr("rook.learning.gh_knowledge.get_gh_knowledge_store", lambda: store)
    return store


@pytest.fixture
def patch_session_recording(monkeypatch):
    recorded: list[dict] = []

    async def fake_record_gh_to_session(**kwargs):
        recorded.append(kwargs)
        return 123

    monkeypatch.setattr(server, "_record_gh_to_session", fake_record_gh_to_session)
    return recorded


@pytest.mark.asyncio
async def test_gh_set_value_success_result_does_not_fail_in_knowledge_wrapper(
    monkeypatch,
    patch_gh_knowledge,
    patch_session_recording,
):
    calls: list[tuple[str, str, dict, int]] = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        calls.append((route, method, payload, port))
        return {"success": True, "data": {"success": True, "Value": 7.5}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    result = await server._execute_gh_set_value_with_knowledge(
        {"guid": "SLIDER-GUID", "value": 7.5},
        port=9950,
    )

    assert calls == [("/gh/value", "POST", {"guid": "SLIDER-GUID", "value": 7.5}, 9950)]
    assert result["success"] is True
    assert result["data"]["success"] is True
    assert result["data"]["Value"] == 7.5
    assert result["data"]["correction_detected"] is False
    assert "observation_id" in result["data"]
    assert result["data"]["_entry_id"] == 123


@pytest.mark.asyncio
async def test_gh_set_value_knowledge_wrapper_preserves_solve_readiness_receipt(
    monkeypatch,
    patch_gh_knowledge,
    patch_session_recording,
):
    calls: list[tuple[str, str, dict, int]] = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        calls.append((route, method, payload, port))
        return {
            "success": True,
            "data": {
                "success": True,
                "Value": 7.5,
                "solve_readiness_receipt": "opaque",
            },
        }

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    result = await server._execute_gh_set_value_with_knowledge(
        {"guid": "SLIDER-GUID", "value": 7.5},
        port=9950,
    )

    assert calls == [
        ("/gh/value", "POST", {"guid": "SLIDER-GUID", "value": 7.5}, 9950)
    ]
    assert result["data"]["solve_readiness_receipt"] == "opaque"


@pytest.mark.asyncio
async def test_gh_set_value_failure_result_does_not_fail_in_knowledge_wrapper(
    monkeypatch,
    patch_gh_knowledge,
    patch_session_recording,
):
    async def fake_call_rhino(_route, method="GET", payload=None, port=None):
        return {"success": False, "data": {"success": False, "error": "bad value"}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    result = await server._execute_gh_set_value_with_knowledge(
        {"guid": "SLIDER-GUID", "value": 7.5},
        port=9950,
    )

    assert result["success"] is False
    assert result["data"]["success"] is False
    assert result["data"]["error"] == "bad value"
    assert result["data"]["correction_detected"] is False
    assert len(server._recent_gh_failures) == 1


@pytest.mark.asyncio
async def test_gh_set_value_failure_then_success_records_correction_info(
    monkeypatch,
    patch_gh_knowledge,
    patch_session_recording,
):
    results = [
        {"success": False, "data": {"success": False, "error": "bad value"}},
        {"success": True, "data": {"success": True, "Value": 7.5}},
    ]

    async def fake_call_rhino(_route, method="GET", payload=None, port=None):
        return results.pop(0)

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    first = await server._execute_gh_set_value_with_knowledge(
        {"guid": "SLIDER-GUID", "value": 6.0},
        port=9950,
    )
    second = await server._execute_gh_set_value_with_knowledge(
        {"guid": "SLIDER-GUID", "value": 7.5},
        port=9950,
    )

    assert first["data"]["correction_detected"] is False
    assert second["data"]["correction_detected"] is True
    assert second["data"]["correction_info"]["failed_context"] == {
        "target_guid": "SLIDER-GUID",
        "value": 6.0,
    }
    assert "bad value" in second["data"]["correction_info"]["error"]
    assert server._recent_gh_failures == {}
