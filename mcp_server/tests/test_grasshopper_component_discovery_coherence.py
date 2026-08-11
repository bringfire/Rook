"""Python custody tests for coherent Grasshopper component discovery metadata."""

import ast
import copy
import inspect
import json
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from mcp import types as mcp_types

from rook import server
from rook.agent import tool_dispatcher
from rook.agent.tool_dispatcher import ToolDispatcher, _transform_gh_library
from rook.learning import knowledge_injector


GUID = "10000000-0000-0000-0000-000000000001"
SHARED_CANDIDATE_FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "grasshopper_component_candidate_shapes.json")
    .read_text(encoding="utf-8")
)


class _DummyPhaseTracker:
    def record_call(self, _name: str) -> None:
        pass


async def _public_call(name: str, arguments: dict):
    handler = server.mcp.request_handlers[mcp_types.CallToolRequest]
    request = mcp_types.CallToolRequest(
        params=mcp_types.CallToolRequestParams(name=name, arguments=arguments)
    )
    return (await handler(request)).root


@pytest.fixture(autouse=True)
def isolated_server(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    monkeypatch.setattr(server, "should_inject", lambda _name, _result: False)
    monkeypatch.setattr(server, "_record_observation", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "get_phase_tracker", lambda: _DummyPhaseTracker())
    monkeypatch.setattr(
        server.targeting,
        "policy_for_tool",
        lambda _name: server.targeting.RhinoToolPolicy(False, "read"),
    )


def _compiled_success(selector_kind: str, selector_value: str) -> dict:
    return {
        "selector": {"kind": selector_kind, "value": selector_value},
        "status": "success",
        "guid": GUID,
        "name": "Area",
        "nickName": "Area",
        "description": "Computes area.",
        "category": "Surface",
        "subCategory": "Analysis",
        "sourceKind": "compiled",
        "provenance": {
            "libraryGuid": "20000000-0000-0000-0000-000000000001",
            "libraryName": "Grasshopper",
            "libraryVersion": "8.0",
            "assemblyFullName": "Grasshopper, Version=8.0.0.0",
            "assemblyVersion": "8.0.0.0",
            "assemblyLocation": "C:\\Program Files\\Rhino 8\\Grasshopper.dll",
        },
        "implementation": {
            "baseGuid": None,
            "componentGuid": GUID,
            "runtimeType": "Grasshopper.Kernel.Components.Component_Area",
            "runtimeAssemblyName": "Grasshopper",
            "runtimeAssemblyVersion": "8.0.0.0",
            "runtimeAssemblyLocation": "C:\\Program Files\\Rhino 8\\Grasshopper.dll",
        },
        "params": None,
    }


def _host_batch(results: list[dict], *, errors: int | None = None) -> dict:
    error_count = (
        sum(item["status"] != "success" for item in results)
        if errors is None
        else errors
    )
    return {
        "success": True,
        "data": {"count": len(results), "errors": error_count, "results": results},
    }


def _candidate(guid: str, name: str) -> dict:
    return {
        "guid": guid,
        "name": name,
        "nickName": name,
        "description": None,
        "category": "Maths",
        "subCategory": "Operators",
        "sourceKind": "compiled",
        "nativeScore": None,
        "matchSource": "exact_name",
    }


def _compiled_failure_prefix(selector_value: str, status: str, error: str) -> dict:
    success = _compiled_success("name", selector_value)
    return {
        key: value
        for key, value in success.items()
        if key not in {"implementation", "params"}
    } | {"status": status, "error": error}


@pytest.mark.asyncio
async def test_schema_advertises_names_and_guids_without_provider_oneof():
    tools = {tool.name: tool for tool in await server.list_tools()}

    schema = tools["gh_batch_component_info"].inputSchema

    assert set(schema["properties"]) == {"names", "guids"}
    assert schema["required"] == []
    assert "oneOf" not in schema
    assert "exactly one" in tools["gh_batch_component_info"].description.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"names": ["Area"], "guids": [GUID]},
        {"names": []},
        {"guids": []},
        {"names": "Area"},
        {"guids": GUID},
        {"names": [1]},
        {"guids": [False]},
    ],
)
async def test_invalid_selector_family_refuses_before_identity_or_target_contact(
    monkeypatch, arguments
):
    target = AsyncMock()
    identity = Mock(side_effect=AssertionError("knowledge identity must not run"))
    monkeypatch.setattr(server, "call_rhino", target)
    monkeypatch.setattr(server, "get_unified_store", identity)

    result = await server._call_tool_dispatch("gh_batch_component_info", arguments)

    assert result["success"] is False
    assert target.await_count == 0
    assert identity.call_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("arguments", "selector_kind", "selector_value"),
    [
        ({"names": ["Area"]}, "name", "Area"),
        ({"guids": [GUID.upper()]}, "guid", GUID.upper()),
    ],
)
async def test_admitted_selector_family_is_forwarded_once_unchanged(
    monkeypatch, arguments, selector_kind, selector_value
):
    target = AsyncMock(
        return_value=_host_batch([_compiled_success(selector_kind, selector_value)])
    )
    identity = Mock(side_effect=AssertionError("knowledge identity must not run"))
    monkeypatch.setattr(server, "call_rhino", target)
    monkeypatch.setattr(server, "get_unified_store", identity)

    result = await server._call_tool_dispatch("gh_batch_component_info", arguments)

    assert result["success"] is True
    target.assert_awaited_once_with(
        "/gh/batch-component-info", "POST", arguments, port=None
    )
    assert identity.call_count == 0


def _library_host(candidate: dict) -> dict:
    return {
        "success": True,
        "data": {
            "count": 1,
            "returnedCount": 1,
            "totalMatches": 1,
            "truncated": False,
            "components": [copy.deepcopy(candidate)],
        },
    }


def _fixture_search_candidate(match_source: str) -> dict:
    candidate = copy.deepcopy(SHARED_CANDIDATE_FIXTURES["search"])
    candidate["matchSource"] = match_source
    return candidate


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("arguments", "shape"),
    [
        ({}, "catalog"),
        ({"search": "Contract Candidate"}, "search"),
    ],
)
async def test_shared_candidate_fixture_passes_python_library_projection(
    monkeypatch, arguments, shape
):
    host = _library_host(SHARED_CANDIDATE_FIXTURES[shape])
    target = AsyncMock(return_value=copy.deepcopy(host))
    monkeypatch.setattr(server, "call_rhino", target)

    result = await server._call_tool_dispatch("gh_library", arguments)

    assert result == host


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["canonical", "direct"])
@pytest.mark.parametrize(
    ("exact", "match_source", "admitted"),
    [
        (False, "native_search", True),
        (True, "exact_name", True),
        (True, "native_search", False),
        (False, "exact_name", False),
    ],
)
async def test_search_source_is_bound_to_request_context_on_both_python_surfaces(
    monkeypatch, surface, exact, match_source, admitted
):
    arguments = {"search": "Contract Candidate", "exact": exact}
    host = _library_host(_fixture_search_candidate(match_source))
    target = AsyncMock(return_value=copy.deepcopy(host))
    if surface == "canonical":
        monkeypatch.setattr(server, "call_rhino", target)
        result = await server._call_tool_dispatch("gh_library", arguments)
    else:
        monkeypatch.setattr(tool_dispatcher, "call_rhino", target)
        result = await ToolDispatcher(port=9950).dispatch("gh_library", arguments)

    expected = (
        host
        if admitted
        else {"success": False, "data": "Malformed gh_library response"}
    )
    assert result == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("arguments", "wrong_shape"),
    [
        ({}, "search"),
        ({}, "ambiguity"),
        ({"search": "Contract Candidate"}, "catalog"),
        ({"search": "Contract Candidate"}, "ambiguity"),
    ],
)
async def test_python_library_projection_rejects_cross_shape_substitution(
    monkeypatch, arguments, wrong_shape
):
    target = AsyncMock(
        return_value=_library_host(SHARED_CANDIDATE_FIXTURES[wrong_shape])
    )
    monkeypatch.setattr(server, "call_rhino", target)

    result = await server._call_tool_dispatch("gh_library", arguments)

    assert result == {"success": False, "data": "Malformed gh_library response"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("nativeScore", None),
        ("nativeScore", "17.5"),
        ("nativeScore", float("nan")),
        ("nativeScore", float("inf")),
        ("nativeScore", 10**1000),
        ("matchSource", "wrong_source"),
    ],
)
async def test_library_search_rejects_each_invalid_evidence_field_without_raising(
    monkeypatch, field, value
):
    candidate = copy.deepcopy(SHARED_CANDIDATE_FIXTURES["search"])
    candidate[field] = value
    monkeypatch.setattr(
        server,
        "call_rhino",
        AsyncMock(return_value=_library_host(candidate)),
    )

    result = await server._call_tool_dispatch(
        "gh_library", {"search": "Contract Candidate"}
    )

    assert result == {"success": False, "data": "Malformed gh_library response"}


def test_shared_ambiguity_fixture_passes_only_ambiguity_projection():
    candidate = SHARED_CANDIDATE_FIXTURES["ambiguity"]
    host = _host_batch(
        [
            {
                "selector": {"kind": "name", "value": "Contract Candidate"},
                "status": "ambiguous_name",
                "candidates": [copy.deepcopy(candidate), copy.deepcopy(candidate)],
            }
        ]
    )

    result = server._project_gh_batch_component_info_result(
        "name", ["Contract Candidate"], host
    )

    assert result["success"] is True
    for wrong_shape in ("catalog", "search"):
        substituted = copy.deepcopy(host)
        substituted["data"]["results"][0]["candidates"] = [
            copy.deepcopy(SHARED_CANDIDATE_FIXTURES[wrong_shape]),
            copy.deepcopy(SHARED_CANDIDATE_FIXTURES[wrong_shape]),
        ]
        assert server._project_gh_batch_component_info_result(
            "name", ["Contract Candidate"], substituted
        ) == {"success": False, "data": "Malformed gh_batch_component_info response"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data",
    [
        {"count": 2, "errors": 0, "results": [_compiled_success("name", "Area")]},
        {"count": 1, "errors": 0, "results": []},
        {
            "count": 1,
            "errors": 0,
            "results": [_compiled_success("name", "Rewritten")],
        },
        {
            "count": 1,
            "errors": 0,
            "results": [
                {
                    **_compiled_success("name", "Area"),
                    "status": "invented_status",
                }
            ],
        },
    ],
)
async def test_malformed_host_correlation_fails_the_whole_operation(monkeypatch, data):
    monkeypatch.setattr(
        server, "call_rhino", AsyncMock(return_value={"success": True, "data": data})
    )
    monkeypatch.setattr(
        server,
        "get_unified_store",
        Mock(side_effect=AssertionError("knowledge identity must not run")),
    )

    result = await server._call_tool_dispatch(
        "gh_batch_component_info", {"names": ["Area"]}
    )

    assert result["success"] is False


@pytest.mark.asyncio
async def test_mixed_name_outcomes_preserve_order_and_legacy_summaries(monkeypatch):
    second_guid = "10000000-0000-0000-0000-000000000002"
    results = [
        _compiled_success("name", "Area"),
        {
            "selector": {"kind": "name", "value": "Missing"},
            "status": "not_found",
            "error": "component_not_found",
        },
        {
            "selector": {"kind": "name", "value": "Duplicate"},
            "status": "ambiguous_name",
            "candidates": [
                _candidate(GUID, "Duplicate"),
                _candidate(second_guid, "Duplicate"),
            ],
        },
        {
            "selector": {"kind": "name", "value": "Broken"},
            "status": "projection_failure",
            "error": "proxy_projection_failed",
        },
        _compiled_failure_prefix(
            "Factory", "instantiation_failure", "component_instantiation_failed"
        ),
        _compiled_failure_prefix(
            "Implementation", "projection_failure", "implementation_projection_failed"
        ),
        _compiled_success("name", "Area"),
    ]
    target = AsyncMock(return_value=_host_batch(results))
    monkeypatch.setattr(server, "call_rhino", target)
    arguments = {
        "names": [
            "Area", "Missing", "Duplicate", "Broken", "Factory",
            "Implementation", "Area",
        ]
    }

    result = await server._call_tool_dispatch("gh_batch_component_info", arguments)

    assert result["success"] is True
    assert result["data"]["count"] == 7
    assert result["data"]["errors"] == 5
    assert [item["selector"]["value"] for item in result["data"]["results"]] == [
        "Area", "Missing", "Duplicate", "Broken", "Factory", "Implementation", "Area"
    ]
    assert result["data"]["resolved"] == {"Area": GUID}
    assert result["data"]["unresolved"] == [
        "Missing", "Duplicate", "Broken", "Factory", "Implementation"
    ]
    target.assert_awaited_once_with(
        "/gh/batch-component-info", "POST", arguments, port=None
    )


@pytest.mark.asyncio
async def test_guid_all_failure_batch_is_complete_without_name_summaries(monkeypatch):
    missing = "10000000-0000-0000-0000-000000000099"
    results = [
        {
            "selector": {"kind": "guid", "value": "not-a-guid"},
            "status": "invalid_guid",
            "error": "invalid_guid",
        },
        {
            "selector": {"kind": "guid", "value": missing.upper()},
            "status": "not_found",
            "error": "component_not_found",
            "guid": missing,
        },
    ]
    monkeypatch.setattr(server, "call_rhino", AsyncMock(return_value=_host_batch(results)))

    result = await server._call_tool_dispatch(
        "gh_batch_component_info", {"guids": ["not-a-guid", missing.upper()]}
    )

    assert result == {
        "success": True,
        "data": {"count": 2, "errors": 2, "results": results},
    }
    assert "resolved" not in result["data"]
    assert "unresolved" not in result["data"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        {"status": "invalid_guid", "error": "invalid_guid"},
        {"status": "not_found", "error": "wrong_error"},
        {"status": "projection_failure", "error": "unknown_projection"},
        {"status": "instantiation_failure", "error": "wrong_error"},
    ],
)
async def test_status_error_or_prefix_disagreement_refuses(monkeypatch, mutation):
    item = _compiled_success("name", "Area") | mutation
    monkeypatch.setattr(server, "call_rhino", AsyncMock(return_value=_host_batch([item], errors=1)))

    result = await server._call_tool_dispatch(
        "gh_batch_component_info", {"names": ["Area"]}
    )

    assert result["success"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("selector", "item"),
    [
        (
            f"({GUID})",
            _compiled_success("guid", f"({GUID})"),
        ),
        (
            "{0x10000000,0x0000,0x0000,{0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x01}}",
            _compiled_success(
                "guid",
                "{0x10000000,0x0000,0x0000,{0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x01}}",
            ),
        ),
    ],
)
async def test_dotnet_guid_syntax_success_is_owned_by_managed_host(
    monkeypatch, selector, item
):
    monkeypatch.setattr(
        server, "call_rhino", AsyncMock(return_value=_host_batch([item]))
    )

    result = await server._call_tool_dispatch(
        "gh_batch_component_info", {"guids": [selector]}
    )

    assert result["success"] is True
    assert result["data"]["results"] == [item]


@pytest.mark.asyncio
async def test_python_only_urn_guid_syntax_can_be_managed_invalid(monkeypatch):
    selector = f"urn:uuid:{GUID}"
    item = {
        "selector": {"kind": "guid", "value": selector},
        "status": "invalid_guid",
        "error": "invalid_guid",
    }
    monkeypatch.setattr(
        server, "call_rhino", AsyncMock(return_value=_host_batch([item]))
    )

    result = await server._call_tool_dispatch(
        "gh_batch_component_info", {"guids": [selector]}
    )

    assert result["success"] is True
    assert result["data"]["results"] == [item]


@pytest.mark.asyncio
async def test_invalid_guid_status_is_impossible_for_name_selector(monkeypatch):
    item = {
        "selector": {"kind": "name", "value": "Area"},
        "status": "invalid_guid",
        "error": "invalid_guid",
    }
    monkeypatch.setattr(
        server, "call_rhino", AsyncMock(return_value=_host_batch([item]))
    )

    result = await server._call_tool_dispatch(
        "gh_batch_component_info", {"names": ["Area"]}
    )

    assert result["success"] is False


@pytest.mark.asyncio
async def test_returned_guid_must_be_canonical_lowercase_d_format(monkeypatch):
    item = {
        **_compiled_success("guid", GUID),
        "guid": "ABCDEF00-0000-0000-0000-000000000001",
    }
    monkeypatch.setattr(
        server, "call_rhino", AsyncMock(return_value=_host_batch([item]))
    )

    result = await server._call_tool_dispatch(
        "gh_batch_component_info", {"guids": [GUID]}
    )

    assert result["success"] is False


@pytest.mark.asyncio
async def test_target_failure_passes_through_without_reconstruction(monkeypatch):
    failure = {"success": False, "data": {"error": "rhino_target_unavailable"}}
    monkeypatch.setattr(server, "call_rhino", AsyncMock(return_value=failure))

    result = await server._call_tool_dispatch(
        "gh_batch_component_info", {"names": ["Area"]}
    )

    assert result == failure


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ({}, {}),
        ({"search": "", "category": "", "exact": False}, {"exact": False}),
        (
            {"search": "  ", "category": " Math ", "exact": True, "limit": 4},
            {"search": "  ", "category": " Math ", "exact": True, "limit": 4},
        ),
    ],
)
async def test_library_omits_empty_strings_and_preserves_present_values(
    monkeypatch, arguments, expected
):
    target = AsyncMock(
        return_value={
            "success": True,
            "data": {
                "count": 0,
                "returnedCount": 0,
                "totalMatches": 0,
                "truncated": False,
                "components": [],
            },
        }
    )
    monkeypatch.setattr(server, "call_rhino", target)

    result = await server._call_tool_dispatch("gh_library", arguments)

    assert result["success"] is True
    target.assert_awaited_once_with("/gh/library", "GET", expected, port=None)


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ({}, {}),
        ({"search": ""}, {}),
        ({"search": "   "}, {"search": "   "}),
        ({"category": ""}, {}),
        ({"category": "   "}, {"category": "   "}),
        ({"exact": False}, {"exact": False}),
        ({"exact": True}, {"exact": True}),
    ],
)
def test_direct_library_transform_matches_canonical_query_semantics(
    arguments, expected
):
    original = copy.deepcopy(arguments)

    transformed = _transform_gh_library(arguments)

    assert transformed == ("/gh/library", "GET", expected)
    assert arguments == original


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("arguments", "shape"),
    [
        ({}, "catalog"),
        ({"search": "Contract Candidate"}, "search"),
    ],
)
async def test_direct_dispatch_accepts_same_fixture_shapes_as_canonical(
    monkeypatch, arguments, shape
):
    host = _library_host(SHARED_CANDIDATE_FIXTURES[shape])
    target = AsyncMock(return_value=copy.deepcopy(host))
    monkeypatch.setattr(tool_dispatcher, "call_rhino", target)

    result = await ToolDispatcher(port=9950).dispatch("gh_library", arguments)

    assert result == host


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("arguments", "wrong_shape"),
    [
        ({}, "search"),
        ({}, "ambiguity"),
        ({"search": "Contract Candidate"}, "catalog"),
        ({"search": "Contract Candidate"}, "ambiguity"),
    ],
)
async def test_direct_dispatch_rejects_same_cross_shape_responses_as_canonical(
    monkeypatch, arguments, wrong_shape
):
    target = AsyncMock(
        return_value=_library_host(SHARED_CANDIDATE_FIXTURES[wrong_shape])
    )
    monkeypatch.setattr(tool_dispatcher, "call_rhino", target)

    result = await ToolDispatcher(port=9950).dispatch("gh_library", arguments)

    assert result == {"success": False, "data": "Malformed gh_library response"}
    endpoint, method, data = _transform_gh_library(arguments)
    target.assert_awaited_once_with(endpoint, method, data, 9950)


@pytest.mark.asyncio
async def test_direct_and_gateway_public_calls_keep_all_failure_batch_success(monkeypatch):
    results = [
        {
            "selector": {"kind": "name", "value": "Missing"},
            "status": "not_found",
            "error": "component_not_found",
        }
    ]
    monkeypatch.setattr(server, "call_rhino", AsyncMock(return_value=_host_batch(results)))

    direct = await _public_call("gh_batch_component_info", {"names": ["Missing"]})
    server._reset_capability_index_cache()
    gateway = await _public_call(
        "rook_tools_call",
        {
            "name": "gh_batch_component_info",
            "arguments": {"names": ["Missing"]},
        },
    )

    expected = {
        "success": True,
        "data": {
            "count": 1,
            "errors": 1,
            "results": results,
            "resolved": {},
            "unresolved": ["Missing"],
        },
    }
    for public in (direct, gateway):
        assert public.isError is False
        assert public.structuredContent == expected
        assert json.loads(public.content[0].text) == expected["data"]


@pytest.mark.asyncio
async def test_direct_and_gateway_public_calls_expose_top_level_failure(monkeypatch):
    failure = {"success": False, "data": {"error": "component_server_failed"}}
    monkeypatch.setattr(server, "call_rhino", AsyncMock(return_value=failure))

    direct = await _public_call("gh_batch_component_info", {"guids": [GUID]})
    server._reset_capability_index_cache()
    gateway = await _public_call(
        "rook_tools_call",
        {"name": "gh_batch_component_info", "arguments": {"guids": [GUID]}},
    )

    for public in (direct, gateway):
        assert public.isError is True
        assert public.structuredContent == failure
        assert public.content[0].text == 'Error: {\n  "error": "component_server_failed"\n}'


@pytest.mark.asyncio
async def test_gateway_vertical_preserves_authoritative_results_without_knowledge(
    monkeypatch,
):
    first_guid = "30000000-0000-0000-0000-000000000001"
    second_guid = "30000000-0000-0000-0000-000000000002"
    candidate_one = {
        "guid": first_guid,
        "name": "Area",
        "nickName": "Area",
        "description": "First installed Area.",
        "category": "Maths",
        "subCategory": "Operators",
        "sourceKind": "compiled",
        "nativeScore": None,
        "matchSource": "exact_name",
    }
    candidate_two = {
        **candidate_one,
        "guid": second_guid,
        "description": "Second installed Area.",
        "sourceKind": "user_object",
    }
    library_component = {
        **candidate_one,
        "name": "Series",
        "nickName": "Series",
        "description": "Create an arithmetic progression.",
        "nativeScore": 1.0,
        "matchSource": "exact_name",
    }
    calls = []

    async def fake_native(route, method="GET", payload=None, port=None):
        calls.append((route, method, payload, port))
        if route == "/gh/library":
            return {
                "success": True,
                "data": {
                    "count": 1,
                    "returnedCount": 1,
                    "totalMatches": 1,
                    "truncated": False,
                    "components": [library_component],
                },
            }
        if route == "/gh/batch-component-info":
            result = {
                "selector": {"kind": "name", "value": "Area"},
                "status": "ambiguous_name",
                "candidates": [candidate_one, candidate_two],
            }
            return {
                "success": True,
                "data": {"count": 1, "errors": 1, "results": [result]},
            }
        raise AssertionError(f"unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_native)
    monkeypatch.setattr(server, "should_inject", knowledge_injector.should_inject)
    injection = AsyncMock(side_effect=AssertionError("knowledge injection must not run"))
    monkeypatch.setattr(server, "inject_knowledge", injection)
    server._reset_capability_index_cache()

    library = await _public_call(
        "rook_tools_call",
        {
            "name": "gh_library",
            "arguments": {"search": "Series", "exact": True, "limit": 3},
        },
    )
    metadata = await _public_call(
        "rook_tools_call",
        {
            "name": "gh_batch_component_info",
            "arguments": {"names": ["Area"]},
        },
    )

    assert calls == [
        (
            "/gh/library",
            "GET",
            {"search": "Series", "exact": True, "limit": 3},
            None,
        ),
        ("/gh/batch-component-info", "POST", {"names": ["Area"]}, None),
    ]
    assert injection.await_count == 0
    assert library.isError is False
    assert library.structuredContent == {
        "success": True,
        "data": {
            "count": 1,
            "returnedCount": 1,
            "totalMatches": 1,
            "truncated": False,
            "components": [library_component],
        },
    }
    assert set(library.structuredContent["data"]["components"][0]) == {
        "guid", "name", "nickName", "description", "category", "subCategory",
        "sourceKind", "nativeScore", "matchSource",
    }
    assert metadata.isError is False
    assert metadata.structuredContent == {
        "success": True,
        "data": {
            "count": 1,
            "errors": 1,
            "results": [
                {
                    "selector": {"kind": "name", "value": "Area"},
                    "status": "ambiguous_name",
                    "candidates": [candidate_one, candidate_two],
                }
            ],
            "resolved": {},
            "unresolved": ["Area"],
        },
    }
    assert json.loads(library.content[0].text) == library.structuredContent["data"]
    assert json.loads(metadata.content[0].text) == metadata.structuredContent["data"]


def test_metadata_dispatch_source_has_one_target_call_and_no_identity_fallback():
    source = textwrap.dedent(inspect.getsource(server._call_tool_dispatch))
    tree = ast.parse(source)
    match_case = next(
        case
        for node in ast.walk(tree)
        if isinstance(node, ast.Match)
        for case in node.cases
        if isinstance(case.pattern, ast.MatchValue)
        and isinstance(case.pattern.value, ast.Constant)
        and case.pattern.value.value == "gh_batch_component_info"
    )
    isolated = ast.unparse(ast.Module(body=match_case.body, type_ignores=[]))
    target_calls = [
        node
        for statement in match_case.body
        for node in ast.walk(statement)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "call_rhino"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "/gh/batch-component-info"
    ]

    assert len(target_calls) == 1
    assert "get_unified_store" not in isolated
    assert "resolve_active_component_guid_by_name" not in isolated
    assert '"/gh/library"' not in isolated
