from __future__ import annotations

import ast
from collections import Counter
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from mcp import types as mcp_types

from rook import server
from rook import targeting
from rook.agent import tool_dispatcher as dispatcher_module
from rook.agent.tool_dispatcher import ToolDispatcher

from rook.gh_authoring_contract import (
    GH_SCRIPT_LANGUAGE_CONFIGS,
    MODEL_FACING_COMPONENT_CREATION_ROUTES,
    model_facing_script_handoff,
)
from rook.tool_lifecycle import resolve_contained_tool


def _edit_with(selector: dict[str, str]) -> dict:
    return {
        "epoch": 7,
        "create": [{"temp_id": "T1", **selector, "pos": [100, 200]}],
    }


def _solve_receipt(receipt_id: str = "script-receipt") -> dict[str, object]:
    return {
        "schema": "rook.gh_solve_readiness_receipt:v1",
        "receipt_id": receipt_id,
        "document_session_id": "session-1",
        "mutation_epoch": 3,
        "solution_run_epoch": None,
        "completed_solution_run_epoch": 2,
        "status": "pending",
        "reason": None,
        "completion_signal": None,
        "issued_at": "2026-08-12T12:00:00+00:00",
        "completed_at": None,
    }


async def _public_call(name: str, arguments: dict):
    handler = server.mcp.request_handlers[mcp_types.CallToolRequest]
    request = mcp_types.CallToolRequest(
        params=mcp_types.CallToolRequestParams(name=name, arguments=arguments)
    )
    return (await handler(request)).root


@pytest.mark.parametrize("language", ["python", "csharp"])
@pytest.mark.parametrize("selector_key", ["guid", "name", "nickname"])
def test_supported_script_selectors_produce_one_closed_handoff(
    language: str,
    selector_key: str,
) -> None:
    config = GH_SCRIPT_LANGUAGE_CONFIGS[language]
    selector = (
        {"guid": config["guid"]}
        if selector_key == "guid"
        else {"name": config["names"][0 if selector_key == "name" else 1]}
    )
    request = _edit_with(selector)

    result = model_facing_script_handoff("gh_edit", request)

    assert result is not None
    assert result["success"] is False
    assert result["_is_handoff"] is True
    assert set(result["data"]) == {
        "code",
        "handoff_required",
        "source_tool",
        "selector",
        "component_guid",
        "recommended_tool",
        "recommended_language",
        "alias_tool",
        "request",
        "message",
    }
    assert result["data"]["code"] == "script_component_requires_dedicated_tool"
    assert result["data"]["handoff_required"] is True
    assert result["data"]["source_tool"] == "gh_edit"
    assert result["data"]["component_guid"] == config["guid"]
    assert result["data"]["recommended_tool"] == "gh_create_script"
    assert result["data"]["recommended_language"] == language
    assert result["data"]["alias_tool"] == config["alias"]
    assert result["data"]["request"] == request
    assert result["data"]["request"] is not request


@pytest.mark.parametrize(
    "tool_name",
    ["gh_explore_component", "gh_explore_deep", "gh_investigate"],
)
def test_active_guid_creation_routes_share_the_handoff(tool_name: str) -> None:
    config = GH_SCRIPT_LANGUAGE_CONFIGS["python"]
    request = {"guid": config["guid"]}

    result = model_facing_script_handoff(tool_name, request)

    assert result is not None
    assert result["data"]["source_tool"] == tool_name
    assert result["data"]["recommended_language"] == "python"
    assert result["data"]["request"] == request


def test_instance_exploration_and_non_script_creation_are_admitted() -> None:
    python_guid = GH_SCRIPT_LANGUAGE_CONFIGS["python"]["guid"]
    assert model_facing_script_handoff(
        "gh_explore_component",
        {"guid": python_guid, "instanceGuid": "existing-instance"},
    ) is None
    assert model_facing_script_handoff(
        "gh_edit",
        _edit_with({"guid": "fbac3e32-f100-4292-8692-77240a42fd1a"}),
    ) is None


@pytest.mark.parametrize(
    "language",
    ["python", "csharp"],
)
def test_contradictory_guid_and_script_name_fails_closed(language: str) -> None:
    config = GH_SCRIPT_LANGUAGE_CONFIGS[language]
    request = _edit_with({
        "guid": "fbac3e32-f100-4292-8692-77240a42fd1a",
        "name": config["names"][0],
    })

    result = model_facing_script_handoff("gh_edit", request)

    assert result is not None
    assert result["data"]["recommended_language"] == language
    assert result["data"]["selector"] == {
        "kind": "name",
        "value": config["names"][0],
    }


def test_mixed_edit_refuses_on_first_supported_selector_in_request_order() -> None:
    python = GH_SCRIPT_LANGUAGE_CONFIGS["python"]
    csharp = GH_SCRIPT_LANGUAGE_CONFIGS["csharp"]
    request = {
        "epoch": 9,
        "create": [
            {"temp_id": "T1", "guid": "fbac3e32-f100-4292-8692-77240a42fd1a"},
            {"temp_id": "T2", "name": csharp["names"][0]},
            {"temp_id": "T3", "guid": python["guid"]},
        ],
    }

    result = model_facing_script_handoff("gh_edit", request)

    assert result is not None
    assert result["data"]["recommended_language"] == "csharp"


def test_name_matching_is_exact_case_insensitive_without_fuzzy_or_legacy_aliases() -> None:
    assert model_facing_script_handoff(
        "gh_edit",
        _edit_with({"name": "pYtHoN 3 sCrIpT"}),
    )["data"]["recommended_language"] == "python"
    for name in ("Python", "Python Script", "GhPython", "CSharp Script", "C# Script (Legacy)"):
        assert model_facing_script_handoff("gh_edit", _edit_with({"name": name})) is None


@pytest.mark.parametrize("form", ["N", "D", "B", "P", "X"])
def test_known_dotnet_guid_text_forms_are_recognized(form: str) -> None:
    config = GH_SCRIPT_LANGUAGE_CONFIGS["python"]
    guid = config["guid"]
    compact = guid.replace("-", "")
    variants = {
        "N": compact.upper(),
        "D": guid.upper(),
        "B": "{" + guid.upper() + "}",
        "P": "(" + guid.upper() + ")",
        "X": "{0x719467e6,0x7cf5,0x4848,{0x99,0xb0,0xc5,0xdd,0x57,0xe5,0x44,0x2c}}",
    }

    result = model_facing_script_handoff("gh_edit", _edit_with({"guid": variants[form]}))

    assert result is not None
    assert result["data"]["component_guid"] == guid


def test_unknown_and_urn_guid_text_are_not_reclassified_as_supported() -> None:
    guid = GH_SCRIPT_LANGUAGE_CONFIGS["python"]["guid"]
    assert model_facing_script_handoff(
        "gh_edit",
        _edit_with({"guid": "urn:uuid:" + guid}),
    ) is None
    assert model_facing_script_handoff(
        "gh_edit",
        _edit_with({"guid": "10000000-0000-0000-0000-000000000001"}),
    ) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("selector_key", ["name", "guid"])
async def test_canonical_gh_edit_refuses_before_target_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    selector_key: str,
) -> None:
    config = GH_SCRIPT_LANGUAGE_CONFIGS["python"]
    selector = {
        selector_key: config["names"][0] if selector_key == "name" else config["guid"]
    }
    calls = []

    async def fail_if_contacted(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("target dispatch occurred")

    monkeypatch.setattr(server, "call_rhino", fail_if_contacted)

    result = await server._call_tool_dispatch("gh_edit", _edit_with(selector))

    assert result["data"]["recommended_language"] == "python"
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("selector_key", ["name", "guid"])
async def test_direct_gh_edit_matches_canonical_handoff_without_target_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    selector_key: str,
) -> None:
    config = GH_SCRIPT_LANGUAGE_CONFIGS["csharp"]
    selector = {
        selector_key: config["names"][0] if selector_key == "name" else config["guid"]
    }
    request = _edit_with(selector)
    calls = []

    async def fail_if_contacted(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("target dispatch occurred")

    monkeypatch.setattr(server, "call_rhino", fail_if_contacted)
    monkeypatch.setattr(dispatcher_module, "call_rhino", fail_if_contacted)

    canonical = await server._call_tool_dispatch("gh_edit", request)
    direct = await ToolDispatcher(port=9950).dispatch("gh_edit", request)

    canonical.pop("_is_handoff")
    assert direct == canonical
    assert "_is_handoff" not in direct
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name",
    ["gh_explore_component", "gh_explore_deep", "gh_investigate"],
)
async def test_active_exploration_creation_refuses_before_any_target_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
) -> None:
    calls = []

    async def fail_if_contacted(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("target dispatch occurred")

    monkeypatch.setattr(server, "call_rhino", fail_if_contacted)
    config = GH_SCRIPT_LANGUAGE_CONFIGS["python"]
    request = {"guid": config["guid"]}

    result = await server._call_tool_dispatch(tool_name, request)

    assert result["data"]["source_tool"] == tool_name
    assert calls == []


@pytest.mark.asyncio
async def test_non_script_gh_edit_keeps_one_unchanged_target_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _edit_with({"guid": "fbac3e32-f100-4292-8692-77240a42fd1a"})
    request["connect"] = [f"C1.O{'0' * 5000}>T1.I0"]
    native_result = {
        "success": True,
        "data": {"edit_summary": {"created": 1, "errors": []}},
    }
    calls = []

    async def fake_call_rhino(endpoint, method, arguments, port=None):
        calls.append((endpoint, method, arguments, port))
        return native_result

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(server, "_record_gh_to_session", lambda *args, **kwargs: None)

    result = await server._call_tool_dispatch("gh_edit", request)

    assert result is native_result
    assert calls == [("/gh/edit", "POST", request, None)]


@pytest.mark.asyncio
async def test_public_mcp_handoff_is_structured_error_without_private_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    server.targeting.reset_targeting_state_for_tests()
    monkeypatch.setattr(server.targeting, "discover_instances", lambda: [{
        "host": "127.0.0.1",
        "port": 9950,
        "processId": 7101,
        "pluginType": "native",
        "documentName": "RoutingFixture.3dm",
    }])
    calls = []

    async def fail_if_contacted(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("target dispatch occurred")

    monkeypatch.setattr(server, "call_rhino", fail_if_contacted)
    request = _edit_with({"guid": GH_SCRIPT_LANGUAGE_CONFIGS["python"]["guid"]})
    request["expectedGhDocumentId"] = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    result = await _public_call("gh_edit", request)

    assert result.isError is True
    assert result.structuredContent["success"] is False
    assert result.structuredContent["data"]["recommended_tool"] == "gh_create_script"
    assert "_is_handoff" not in result.structuredContent
    assert calls == []
    server.targeting.reset_targeting_state_for_tests()


@pytest.mark.asyncio
async def test_panel_locked_canonical_and_direct_handoffs_preserve_caller_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_HOST_GENERATION_ID": (
            "11111111-1111-1111-1111-111111111111"
        ),
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    request = _edit_with({"guid": GH_SCRIPT_LANGUAGE_CONFIGS["python"]["guid"]})
    public_request = {
        **request,
        "expectedGhDocumentId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    }

    def fail_route_resolution(*_args, **_kwargs):
        raise AssertionError("handoff attempted target resolution")

    monkeypatch.setattr(targeting, "resolve_tool_route", fail_route_resolution)
    try:
        canonical = await server.call_tool("gh_edit", public_request, _public_mcp=True)
        direct = await ToolDispatcher(port=9950).dispatch("gh_edit", request)
    finally:
        targeting.reset_targeting_state_for_tests()

    assert canonical.structuredContent == direct
    assert canonical.structuredContent["data"]["request"] == request
    assert "documentSerialNumber" not in canonical.structuredContent["data"]["request"]
    assert request == _edit_with({"guid": GH_SCRIPT_LANGUAGE_CONFIGS["python"]["guid"]})


@pytest.mark.asyncio
async def test_canonical_handoff_precedes_target_availability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    calls = []

    def fail_route_resolution(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("target availability was consulted")

    monkeypatch.setattr(targeting, "resolve_tool_route", fail_route_resolution)

    result = await server.call_tool(
        "gh_edit",
        _edit_with(
            {"name": GH_SCRIPT_LANGUAGE_CONFIGS["csharp"]["names"][0]}
        ),
        _public_mcp=True,
    )

    assert result.structuredContent["data"]["code"] == (
        "script_component_requires_dedicated_tool"
    )
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("flow", "expected_issue"),
    [
        (
            "N1.O0>TActorSetControl.I0",
            {
                "path": "/connect/0",
                "code": "invalid_component_reference",
                "value": "N1",
            },
        ),
        (
            "C1.O\u00a01>TActorSetControl.I0",
            {
                "path": "/connect/0",
                "code": "invalid_flow",
                "value": "C1.O\u00a01>TActorSetControl.I0",
            },
        ),
        (
            "C1.O\u00851>TActorSetControl.I0",
            {
                "path": "/connect/0",
                "code": "invalid_flow",
                "value": "C1.O\u00851>TActorSetControl.I0",
            },
        ),
    ],
)
async def test_invalid_gh_edit_references_refuse_before_canonical_or_direct_target_contact(
    monkeypatch: pytest.MonkeyPatch,
    flow: str,
    expected_issue: dict,
) -> None:
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    targeting.reset_targeting_state_for_tests()
    request = {
        "epoch": 7,
        "create": [
            {"temp_id": "TActorSetControl", "type": "slider", "pos": [100, 200]}
        ],
        "connect": [flow],
    }
    calls = []

    def fail_route_resolution(*args, **kwargs):
        calls.append(("route", args, kwargs))
        raise AssertionError("target resolution occurred")

    async def fail_if_dispatched(*args, **kwargs):
        calls.append(("dispatch", args, kwargs))
        raise AssertionError("target dispatch occurred")

    monkeypatch.setattr(targeting, "resolve_tool_route", fail_route_resolution)
    monkeypatch.setattr(server, "call_rhino", fail_if_dispatched)
    monkeypatch.setattr(dispatcher_module, "call_rhino", fail_if_dispatched)
    try:
        canonical = await server.call_tool("gh_edit", request, _public_mcp=True)
        direct = await ToolDispatcher(port=9950).dispatch("gh_edit", request)
    finally:
        targeting.reset_targeting_state_for_tests()

    assert canonical.structuredContent == direct
    assert direct == {
        "success": False,
        "data": {
            "error": "gh_edit_admission_failed",
            "issues": [expected_issue],
        },
    }
    assert calls == []


@pytest.mark.asyncio
async def test_gh_edit_temp_id_schema_exposes_the_shared_closed_grammar() -> None:
    tools = {tool.name: tool for tool in await server.list_tools()}
    temp_id = (
        tools["gh_edit"]
        .inputSchema["properties"]["create"]["items"]["properties"]["temp_id"]
    )

    assert temp_id == {
        "type": "string",
        "pattern": "^T[A-Za-z0-9_]{1,63}$",
        "minLength": 2,
        "maxLength": 64,
        "description": "Temporary ID (T1, T2, ...) for referencing in connect/groups",
    }


@pytest.mark.asyncio
async def test_profile_wall_precedes_script_handoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
    calls = []

    def fail_if_classified(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("handoff ran before profile wall")

    monkeypatch.setattr(server, "model_facing_script_handoff", fail_if_classified)

    result = await server.call_tool(
        "gh_edit",
        _edit_with({"guid": GH_SCRIPT_LANGUAGE_CONFIGS["python"]["guid"]}),
        _public_mcp=True,
    )

    assert result.structuredContent["data"] == {
        "code": "tool_profile_blocked",
        "tool": "gh_edit",
        "profile": "readonly",
    }
    assert calls == []


@pytest.mark.asyncio
async def test_public_schema_validation_precedes_script_handoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    calls = []

    def fail_if_classified(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("handoff ran before public schema validation")

    monkeypatch.setattr(server, "model_facing_script_handoff", fail_if_classified)

    result = await _public_call("gh_edit", {
        "create": [{
            "temp_id": "T1",
            "guid": GH_SCRIPT_LANGUAGE_CONFIGS["python"]["guid"],
        }],
    })

    assert result.isError is True
    assert "validation error" in result.content[0].text.lower()
    assert calls == []


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        (
            "gh_edit",
            _edit_with({"guid": GH_SCRIPT_LANGUAGE_CONFIGS["python"]["guid"]}),
        ),
        (
            "rook_tools_call",
            {
                "name": "gh_edit",
                "arguments": _edit_with(
                    {"guid": GH_SCRIPT_LANGUAGE_CONFIGS["python"]["guid"]}
                ),
            },
        ),
    ],
)
@pytest.mark.asyncio
async def test_gh_edit_custody_precedes_script_handoff(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    arguments: dict,
) -> None:
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    calls = []

    def fail_if_classified(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("script handoff ran before GH custody")

    monkeypatch.setattr(server, "model_facing_script_handoff", fail_if_classified)
    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_HOST_GENERATION_ID": (
            "11111111-1111-1111-1111-111111111111"
        ),
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    try:
        result = await server.call_tool(name, arguments, _public_mcp=True)
    finally:
        targeting.reset_targeting_state_for_tests()

    assert result.structuredContent["success"] is False
    assert result.structuredContent["data"]["error"] == "gh_target_required"
    assert calls == []


@pytest.mark.asyncio
async def test_meta_dispatch_precedes_script_handoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    calls = []

    def fail_if_classified(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("handoff ran before meta dispatch")

    monkeypatch.setattr(server, "model_facing_script_handoff", fail_if_classified)

    result = await server.call_tool(
        "rook_tools_read",
        {"name": "gh_edit"},
        _public_mcp=True,
    )

    assert result.isError is False
    assert calls == []


@pytest.mark.asyncio
async def test_containment_wall_precedes_script_handoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    calls = []

    def fail_if_classified(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("handoff ran before containment wall")

    monkeypatch.setattr(server, "model_facing_script_handoff", fail_if_classified)

    result = await server.call_tool(
        "gh_execute_intent",
        {"guid": GH_SCRIPT_LANGUAGE_CONFIGS["python"]["guid"]},
        _public_mcp=True,
    )

    assert result.structuredContent["data"]["code"] == "legacy_semantic_tool_contained"
    assert calls == []


@pytest.mark.asyncio
async def test_chirp_delegates_generated_csharp_to_canonical_script_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generated_script = "public class Script_Instance { }"
    chirp_models = []

    async def ensure_running(model=None):
        chirp_models.append(model)
        return {"running": True, "host": "127.0.0.1", "port": 8765}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "script": generated_script,
                "name": "Grid Worker",
                "category": "interpreter",
                "pins_in": [{"name": "Rows", "type": "int", "access": "item"}],
                "pins_out": [{"name": "Points", "type": "Point3d", "access": "list"}],
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json):
            assert url == "http://127.0.0.1:8765/chirp/create"
            return FakeResponse()

    helper_calls = []
    managed_receipt = _solve_receipt()

    async def fake_create_script(
        language,
        arguments,
        port,
        *,
        tool_name="gh_create_script",
        defer_verification=False,
    ):
        helper_calls.append((
            language,
            arguments,
            port,
            tool_name,
            defer_verification,
        ))
        return {
            "success": True,
            "data": {
                "component_guid": "11111111-1111-4111-8111-111111111111",
                "compilation_errors": ["sentinel compile error"],
                "solve_relevant_mutation_committed": True,
                "solve_readiness_receipt": managed_receipt,
            },
        }

    raw_calls = []

    async def fail_raw_contact(*args, **kwargs):
        raw_calls.append((args, kwargs))
        raise AssertionError("chirp bypassed canonical script creation")

    async def record_noop(**kwargs):
        return None

    monkeypatch.setattr("rook.chirp_manager.ensure_chirp_running", ensure_running)
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda *args, **kwargs: FakeClient())
    monkeypatch.setattr(server, "_execute_gh_create_script", fake_create_script)
    monkeypatch.setattr(server, "call_rhino", fail_raw_contact)
    monkeypatch.setattr(server, "_record_gh_to_session", record_noop)

    result = await server._call_tool_dispatch("chirp_create", {
        "signature": "Build an XY grid",
        "category": "interpreter",
        "name": "Grid Worker",
        "pins_in": [{"name": "Rows", "type": "int", "access": "item"}],
        "pins_out": [{"name": "Points", "type": "Point3d", "access": "list"}],
        "x": 300,
        "y": 400,
    })

    assert len(helper_calls) == 1
    (
        language,
        arguments,
        port,
        tool_name,
        defer_verification,
    ) = helper_calls[0]
    assert language == "csharp"
    assert port is None
    assert tool_name == "chirp_create"
    assert defer_verification is True
    assert arguments == {
        "code": generated_script,
        "name": "Grid Worker",
        "pins_in": [{
            "name": "Rows",
            "type": "int",
            "access": "item",
            "optional": True,
        }],
        "pins_out": [{
            "name": "Points",
            "type": "Point3d",
            "access": "list",
        }],
        "x": 300,
        "y": 400,
    }
    assert raw_calls == []
    assert chirp_models == [None]
    assert result["success"] is True
    assert result["data"]["signature"] == "Build an XY grid"
    assert result["data"]["category"] == "interpreter"
    assert result["data"]["component_errors"] == ["sentinel compile error"]
    assert "compilation_errors" not in result["data"]
    assert result["data"]["solve_readiness_receipt"] is managed_receipt


@pytest.mark.asyncio
async def test_direct_chirp_create_uses_shared_owner_without_rebuilding_receipt(monkeypatch):
    managed_receipt = _solve_receipt("chirp-direct")
    owned_result = {"success": True, "data": {
        "component_guid": "component-guid",
        "solve_relevant_mutation_committed": True,
        "solve_readiness_receipt": managed_receipt,
        "script_receipt": {"schema": "rook.gh_script_receipt:v1"},
    }}
    calls = []

    async def fake_execute(arguments, port):
        calls.append((dict(arguments), port))
        return owned_result, False, False

    async def prompt_idle(*args, **kwargs):
        return {"success": True, "data": {"active": False}}

    monkeypatch.setattr(server, "_execute_chirp_create", fake_execute)
    monkeypatch.setattr(dispatcher_module, "call_rhino", prompt_idle)
    dispatcher = ToolDispatcher(
        port=6011,
        local_tools=dispatcher_module.build_local_tools(),
    )

    result = await dispatcher.dispatch("chirp_create", {"signature": "Grid"})

    assert calls == [({"signature": "Grid"}, 6011)]
    assert result["data"]["solve_readiness_receipt"] is managed_receipt


@pytest.mark.asyncio
async def test_chirp_preserves_closed_script_pipeline_failure_without_decoration(monkeypatch):
    managed_receipt = _solve_receipt("chirp-failure")
    failure = server._script_pipeline_incomplete(
        "solve_readiness",
        component_created=True,
        pins_configured=True,
        component_guid="component-guid",
        component_short_id=None,
        final_write_dispatched=True,
        final_write_success=True,
        solve_relevant_mutation_committed=True,
        solve_readiness_receipt=managed_receipt,
        script_receipt=None,
    )

    async def ensure_running(model=None):
        return {"running": True, "host": "127.0.0.1", "port": 8765}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "script": "public class Script_Instance { }",
                "pins_in": [{"name": "Rows", "type": "int", "access": "item"}],
                "pins_out": [{"name": "Points", "type": "Point3d", "access": "list"}],
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json):
            return FakeResponse()

    async def fake_create_script(*args, **kwargs):
        return failure

    async def record_noop(**kwargs):
        return None

    monkeypatch.setattr("rook.chirp_manager.ensure_chirp_running", ensure_running)
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda *args, **kwargs: FakeClient())
    monkeypatch.setattr(server, "_execute_gh_create_script", fake_create_script)
    monkeypatch.setattr(server, "_record_gh_to_session", record_noop)

    result = await server._call_tool_dispatch("chirp_create", {
        "signature": "Build an XY grid",
        "category": "interpreter",
        "pins_in": [{"name": "Rows", "type": "int", "access": "item"}],
        "pins_out": [{"name": "Points", "type": "Point3d", "access": "list"}],
    })

    assert result is failure
    assert set(result["data"]) == {
        "error",
        "phase",
        "committed_preparatory",
        "component",
        "final_write",
        "solve_readiness_receipt",
        "script_receipt",
    }
    assert result["data"]["solve_readiness_receipt"] is managed_receipt


@pytest.mark.asyncio
async def test_direct_deterministic_chirp_is_recorder_free(monkeypatch):
    managed_receipt = _solve_receipt("direct-deterministic")

    async def fake_execute(arguments, port):
        assert arguments["deterministic_only"] is True
        return ({"success": True, "data": {
            "component_guid": "component-guid",
            "solve_relevant_mutation_committed": True,
            "solve_readiness_receipt": managed_receipt,
        }}, False, True)

    async def forbidden_record(**kwargs):
        raise AssertionError("direct ToolDispatcher entered the canonical recorder")

    async def prompt_idle(*args, **kwargs):
        return {"success": True, "data": {"active": False}}

    monkeypatch.setattr(server, "_execute_chirp_create", fake_execute)
    monkeypatch.setattr(server, "_record_gh_to_session", forbidden_record)
    monkeypatch.setattr(dispatcher_module, "call_rhino", prompt_idle)

    result = await ToolDispatcher(
        port=6011,
        local_tools=dispatcher_module.build_local_tools(),
    ).dispatch("chirp_create", {
        "signature": "Grid",
        "deterministic_only": True,
    })

    assert result["success"] is True
    assert result["data"]["solve_readiness_receipt"] is managed_receipt


def _match_case_name(pattern: ast.pattern) -> str | None:
    if isinstance(pattern, ast.MatchValue) and isinstance(pattern.value, ast.Constant):
        return pattern.value.value if isinstance(pattern.value.value, str) else None
    return None


def _component_creation_call_graph() -> Counter[tuple[str, str, str | None]]:
    tree = ast.parse(Path(server.__file__).read_text(encoding="utf-8"))
    calls: list[tuple[str, str, str | None]] = []

    def walk(node: ast.AST, function: str = "<module>", case: str | None = None) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function = node.name
        if isinstance(node, ast.match_case):
            case = _match_case_name(node.pattern)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "call_rhino"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value in {"/gh/create-component", "/gh/edit"}
        ):
            calls.append((node.args[0].value, function, case))
        for child in ast.iter_child_nodes(node):
            walk(child, function, case)

    walk(tree)
    return Counter(calls)


def test_raw_component_creation_call_graph_is_closed_and_classified() -> None:
    expected = Counter({
        ("/gh/create-component", "_execute_gh_create_script", None): 1,
        ("/gh/create-component", "_call_tool_dispatch", "gh_create_component"): 1,
        ("/gh/create-component", "_call_tool_dispatch", "gh_explore_component"): 1,
        ("/gh/create-component", "_call_tool_dispatch", "gh_explore_deep"): 11,
        ("/gh/create-component", "_call_tool_dispatch", "gh_investigate"): 3,
        ("/gh/create-component", "_call_tool_dispatch", "gh_execute_intent"): 1,
        ("/gh/create-component", "_call_tool_dispatch", "gh_explore_workflow"): 1,
        ("/gh/edit", "_call_tool_dispatch", "gh_edit"): 1,
        ("/gh/edit", "_call_tool_dispatch", "gh_replay_recipe"): 1,
        ("/gh/edit", "_call_tool_dispatch", "gh_execute_intent"): 1,
    })

    assert _component_creation_call_graph() == expected
    assert MODEL_FACING_COMPONENT_CREATION_ROUTES == frozenset({
        "gh_edit",
        "gh_explore_component",
        "gh_explore_deep",
        "gh_investigate",
    })
    assert resolve_contained_tool("gh_execute_intent") is not None
    assert resolve_contained_tool("gh_explore_workflow") is not None
    assert resolve_contained_tool("gh_replay_recipe") is not None


@pytest.mark.asyncio
async def test_raw_component_primitive_is_not_model_facing() -> None:
    names = {tool.name for tool in await server.list_tools()}

    assert "gh_create_component" not in names
    assert "gh_create_component" not in targeting._ALL_KNOWN_TOOLS
    assert "gh_create_component" not in dispatcher_module.BRIDGE_ROUTES
    assert {"gh_create_script", "gh_create_python_script", "gh_create_csharp_script"} <= names


@pytest.mark.asyncio
async def test_canonical_script_creation_preserves_four_input_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    code = "Points = BuildGrid(Start, XStep, YStep, Count);"
    pins_in = [
        {"name": "Start", "type": "Point3d", "access": "item", "optional": False},
        {"name": "XStep", "type": "double", "access": "item", "optional": False},
        {"name": "YStep", "type": "double", "access": "item", "optional": False},
        {"name": "Count", "type": "int", "access": "item", "optional": False},
    ]
    pins_out = [
        {"name": "Points", "type": "Point3d", "access": "list", "optional": False},
    ]
    calls = []
    managed_receipt = _solve_receipt("canonical-create")

    async def fake_call_rhino(route, method="GET", payload=None, port=None, **_kwargs):
        calls.append((route, method, payload, port))
        if route == "/gh/create-component":
            assert payload == {
                "guid": GH_SCRIPT_LANGUAGE_CONFIGS["csharp"]["guid"],
                "x": 250,
                "y": 350,
            }
            return {"success": True, "data": {"guid": "script-instance"}}
        if route == "/gh/script-params":
            assert payload == {
                "guid": "script-instance",
                "inputs": pins_in,
                "outputs": pins_out,
                "nick": "Grid Script",
            }
            return {"success": True, "data": {}}
        if route == "/gh/script":
            assert code in payload["script"]
            assert "private void RunScript(" in payload["script"]
            return {"success": True, "data": {
                "guid": "script-instance",
                "solve_relevant_mutation_committed": True,
                "solve_readiness_receipt": managed_receipt,
            }}
        if route == "/gh/wait-for-solve-readiness":
            ready = dict(managed_receipt)
            ready.update({
                "solution_run_epoch": 4,
                "completed_solution_run_epoch": 4,
                "status": "ready",
                "completion_signal": "solution_end",
                "completed_at": "2026-08-12T12:00:01+00:00",
            })
            return {"success": True, "data": {
                "schema": "rook.gh_solve_readiness_wait_result:v1",
                "wait_status": "ready",
                "receipt": ready,
            }}
        if route == "/gh/errors":
            return {"success": True, "data": {"errors": [], "warnings": []}}
        raise AssertionError(f"unexpected route: {route}")

    async def record_noop(**_kwargs):
        return None

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(server, "_record_gh_to_session", record_noop)

    result = await server._call_tool_dispatch("gh_create_script", {
        "language": "csharp",
        "code": code,
        "pins_in": pins_in,
        "pins_out": pins_out,
        "name": "Grid Script",
        "x": 250,
        "y": 350,
    })

    assert result["success"] is True
    assert result["data"]["pins_in"] == pins_in
    assert result["data"]["pins_out"] == pins_out
    assert [route for route, *_ in calls] == [
        "/gh/create-component",
        "/gh/script-params",
        "/gh/script",
        "/gh/wait-for-solve-readiness",
        "/gh/errors",
    ]
    assert result["data"]["solve_readiness_receipt"] is managed_receipt


@pytest.mark.asyncio
async def test_canonical_script_tool_is_readable_through_progressive_disclosure() -> None:
    result = await server._handle_meta_tool(
        "rook_tools_read",
        {"name": "gh_create_script"},
        server.Profile.FULL,
    )
    record = json.loads(result[0].text)

    assert record["name"] == "gh_create_script"
    assert "language" in record["input_schema"]["properties"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments", "expected_language"),
    [
        ("gh_create_script", {"language": "python", "code": "A = 1"}, "python"),
        ("gh_create_python_script", {"code": "A = 1"}, "python"),
        ("gh_create_csharp_script", {"code": "A = 1;"}, "csharp"),
    ],
)
async def test_script_creation_aliases_preserve_managed_receipt_in_canonical_and_direct_paths(
    monkeypatch,
    tool_name,
    arguments,
    expected_language,
):
    managed_receipt = _solve_receipt(f"{tool_name}-receipt")
    helper_calls = []

    async def fake_execute(language, helper_arguments, port, *, tool_name="gh_create_script", defer_verification=False):
        helper_calls.append((language, dict(helper_arguments), port, tool_name, defer_verification))
        return {"success": True, "data": {
            "component_guid": "component-guid",
            "solve_relevant_mutation_committed": True,
            "solve_readiness_receipt": managed_receipt,
            "script_receipt": {"schema": "rook.gh_script_receipt:v1"},
        }}

    async def record_noop(**kwargs):
        return None

    async def prompt_idle(*args, **kwargs):
        return {"success": True, "data": {"active": False}}

    monkeypatch.setattr(server, "_execute_gh_create_script", fake_execute)
    monkeypatch.setattr(server, "_record_gh_to_session", record_noop)
    monkeypatch.setattr(dispatcher_module, "call_rhino", prompt_idle)

    canonical = await server._call_tool_dispatch(tool_name, {**arguments, "port": 6011})
    direct = await ToolDispatcher(
        port=6011,
        local_tools=dispatcher_module.build_local_tools(),
    ).dispatch(tool_name, dict(arguments))

    assert canonical["data"]["solve_readiness_receipt"] is managed_receipt
    assert direct["data"]["solve_readiness_receipt"] is managed_receipt
    assert all(call[0] == expected_language for call in helper_calls)
    assert all(call[3] == tool_name for call in helper_calls)
    assert len(helper_calls) == 2


@pytest.mark.asyncio
async def test_update_script_preserves_same_failure_object_in_canonical_and_direct_paths(monkeypatch):
    managed_receipt = _solve_receipt("update-failure")
    failure = server._script_pipeline_incomplete(
        "source_write",
        component_created=False,
        pins_configured=False,
        component_guid="component-guid",
        component_short_id="C1",
        final_write_dispatched=True,
        final_write_success=False,
        solve_relevant_mutation_committed=True,
        solve_readiness_receipt=managed_receipt,
        script_receipt=None,
    )

    async def fake_update(arguments, port):
        return failure

    async def record_noop(**kwargs):
        return None

    monkeypatch.setattr(server, "_execute_gh_update_script", fake_update)
    monkeypatch.setattr(server, "_record_gh_to_session", record_noop)

    arguments = {"guid": "C1", "code": "A = 2"}
    canonical = await server._call_tool_dispatch("gh_update_script", {**arguments, "port": 6011})
    direct = await ToolDispatcher(
        port=6011,
        local_tools=dispatcher_module.build_local_tools(),
    ).dispatch("gh_update_script", dict(arguments))

    assert canonical is failure
    assert direct is failure
    assert canonical["data"]["solve_readiness_receipt"] is managed_receipt


def test_execute_skill_routes_creation_by_capability() -> None:
    skill = Path(".agents/skills/execute-grasshopper/SKILL.md").read_text(encoding="utf-8")

    assert "create ordinary Grasshopper components through `gh_edit`" in skill
    assert "create modern Python or C# script components through `gh_create_script`" in skill
    assert "create Chirp components through `chirp_create`" in skill
    assert "correct existing script source or pins through `gh_update_script`" in skill
    assert "Do not repeat the refused ordinary request" in skill
