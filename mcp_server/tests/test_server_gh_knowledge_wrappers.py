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
            "targetParam": "A",
        },
    )

    assert result["success"] is True
    assert result["data"]["connected"] is True
    assert calls == [
        (
            {
                "sourceGuid": "SOURCE-GUID",
                "targetGuid": "TARGET-GUID",
                "targetParam": "A",
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
        return {"success": True, "data": {"success": True, "connected": True}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    result = await server._execute_gh_connect_with_knowledge(
        {
            "sourceGuid": "SOURCE-GUID",
            "targetGuid": "TARGET-GUID",
            "targetParam": "A",
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
                "targetParam": "A",
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
