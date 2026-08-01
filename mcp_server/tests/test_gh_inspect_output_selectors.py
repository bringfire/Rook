import pytest

from rook import server


@pytest.fixture(autouse=True)
def disable_persistent_knowledge_injection(monkeypatch):
    monkeypatch.setattr(server, "should_inject", lambda *_args, **_kwargs: False)


@pytest.mark.asyncio
async def test_schema_advertises_distinct_output_index_selector():
    tools = {tool.name: tool for tool in await server.list_tools()}
    schema = tools["gh_inspect_output"].inputSchema

    assert schema["properties"]["param"]["type"] == "string"
    assert schema["properties"]["outputIndex"] == {
        "type": "integer",
        "minimum": 0,
        "description": "Zero-based output parameter index.",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("selector", "expected_payload"),
    [
        ({"param": "Result"}, {"guid": "COMPONENT", "param": "Result"}),
        ({"param": "5"}, {"guid": "COMPONENT", "param": "5"}),
        ({"outputIndex": 5}, {"guid": "COMPONENT", "outputIndex": 5}),
        ({}, {"guid": "COMPONENT"}),
    ],
)
async def test_dispatch_preserves_the_selected_contract_without_injecting_output_zero(
    monkeypatch, selector, expected_payload
):
    calls = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        calls.append((route, method, payload, port))
        return {"success": True, "data": {"index": 5}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    result = await server._call_tool_dispatch(
        "gh_inspect_output",
        {"guid": "COMPONENT", **selector},
    )

    assert result["success"] is True
    assert calls == [
        ("/gh/inspect-output", "GET", expected_payload, None),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("selector", "expected_field"),
    [
        (
            {"param": "Result", "outputIndex": 0},
            "selector: specify only one of param and outputIndex",
        ),
        ({"param": None}, "param: must be a non-empty string"),
        ({"param": ""}, "param: must be a non-empty string"),
        ({"param": "   "}, "param: must be a non-empty string"),
        ({"param": 5}, "param: must be a non-empty string"),
        (
            {"outputIndex": None},
            "outputIndex: must be a non-negative integer",
        ),
        ({"outputIndex": -1}, "outputIndex: must be a non-negative integer"),
        ({"outputIndex": 1.5}, "outputIndex: must be a non-negative integer"),
        ({"outputIndex": "5"}, "outputIndex: must be a non-negative integer"),
        ({"outputIndex": True}, "outputIndex: must be a non-negative integer"),
    ],
)
async def test_invalid_explicit_selector_uses_invalid_arguments_without_http(
    monkeypatch, selector, expected_field
):
    async def unexpected_call_rhino(*_args, **_kwargs):
        raise AssertionError("invalid selector reached HTTP transport")

    monkeypatch.setattr(server, "call_rhino", unexpected_call_rhino)

    result = await server._call_tool_dispatch(
        "gh_inspect_output",
        {"guid": "COMPONENT", **selector},
    )

    assert result == {
        "success": False,
        "data": {
            "error": "invalid_arguments",
            "name": "gh_inspect_output",
            "fields": [expected_field],
        },
    }
