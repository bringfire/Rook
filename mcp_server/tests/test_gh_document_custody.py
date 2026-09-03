import asyncio
from contextlib import contextmanager
import json
from types import SimpleNamespace

import pytest
from mcp import types as mcp_types

from rook import server
from rook.gh_document_custody import (
    EXPECTED_GH_DOCUMENT_ID_ARGUMENT,
    INTERNAL_EXPECTED_GH_DOCUMENT_ID_FIELD,
    INTERNAL_GH_SCOPE_FIELD,
    GhDispatchContext,
    GhToolClassification,
    classify_gh_tool,
    current_gh_dispatch_context,
    gh_dispatch_scope,
    observe_gh_document_id,
    project_current_gh_document_id,
)


EXPECTED_PUBLIC_GH_CLASSIFICATIONS = {
    GhToolClassification.DOCUMENT_INDEPENDENT: frozenset(
        {
            "gh_add_pattern",
            "gh_categories",
            "gh_consolidate",
            "gh_constraints",
            "gh_end_exploration",
            "gh_knowledge_query",
            "gh_knowledge_reload",
            "gh_library",
            "gh_migration_status",
            "gh_pattern_links",
            "gh_pattern_stats",
            "gh_query_observations",
            "gh_query_patterns",
            "gh_record_investigation",
            "gh_record_learning",
            "gh_record_pattern_use",
            "gh_reflect",
            "gh_save_pattern",
            "gh_save_recipe",
            "gh_session_current",
            "gh_session_end",
            "gh_session_history",
            "gh_session_note",
            "gh_start_exploration",
            "gh_structure_query",
            "gh_validate_latency",
            "gh_validate_regression",
            "gh_validate_scenarios",
        }
    ),
    GhToolClassification.OBSERVATION: frozenset(
        {
            "gh_batch_component_info",
            "gh_canvas_image",
            "gh_errors",
            "gh_extract_recipe",
            "gh_get_reference",
            "gh_inspect_output",
            "gh_learn_canvas",
            "gh_selection",
            "gh_snapshot",
            "gh_solve_readiness",
            "gh_status",
            "gh_upgrade_recipe",
            "gh_wait_for_solve_readiness",
        }
    ),
    GhToolClassification.MUTATION: frozenset(
        {
            "chirp_create",
            "gh_align",
            "gh_bake_output",
            "gh_canvas_cleanup",
            "gh_canvas_focus",
            "gh_canvas_zoom",
            "gh_clear",
            "gh_clear_reference",
            "gh_cluster",
            "gh_connect",
            "gh_create_csharp_script",
            "gh_create_python_script",
            "gh_create_script",
            "gh_distribute",
            "gh_edit",
            "gh_explore_component",
            "gh_explore_deep",
            "gh_investigate",
            "gh_move",
            "gh_preview",
            "gh_set_reference",
            "gh_set_script",
            "gh_set_script_pins",
            "gh_straighten_wires",
            "gh_undo",
            "gh_update_script",
        }
    ),
    GhToolClassification.TRANSITION: frozenset(
        {
            "gh_document_new",
            "gh_document_open",
            "gh_learn_directory",
        }
    ),
}


@contextmanager
def _panel_locked():
    server.targeting.reset_targeting_state_for_tests()
    server.targeting.initialize_from_environment(
        {
            "ROOK_MCP_TARGET_MODE": "panel_locked",
            "ROOK_MCP_TARGET_HOST_GENERATION_ID": (
                "11111111-1111-1111-1111-111111111111"
            ),
            "ROOK_MCP_TARGET_PROCESS_ID": "7101",
            "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
        }
    )
    server._reset_capability_index_cache()
    try:
        yield
    finally:
        server.targeting.reset_targeting_state_for_tests()
        server._reset_capability_index_cache()


@pytest.mark.parametrize(
    ("name", "scope"),
    [
        ("gh_component_search", "document_independent"),
        ("gh_status", "observation"),
        ("gh_snapshot", "observation"),
        ("gh_canvas_image", "observation"),
        ("gh_structure_query", "document_independent"),
        ("gh_set_value", "mutation"),
        ("gh_update_script", "mutation"),
        ("chirp_create", "mutation"),
        ("gh_document_open", "transition"),
        ("gh_document_new", "transition"),
        ("gh_learn_directory", "transition"),
    ],
)
def test_gh_classification_has_one_owner(name, scope):
    assert classify_gh_tool(name).value == scope


@pytest.mark.asyncio
async def test_every_public_gh_affecting_tool_has_one_semantic_classification(
    monkeypatch,
):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    server._reset_capability_index_cache()
    tools = await server._all_live_tools()
    public_names = {
        tool.name
        for tool in tools
        if tool.name.startswith("gh_") or tool.name == "chirp_create"
    }
    expected_names = set().union(*EXPECTED_PUBLIC_GH_CLASSIFICATIONS.values())

    assert public_names == expected_names
    for classification, names in EXPECTED_PUBLIC_GH_CLASSIFICATIONS.items():
        for name in names:
            assert classify_gh_tool(name) is classification


def _result_payload(result):
    text = result[0].text
    if text.startswith("Error: "):
        return False, json.loads(text.removeprefix("Error: "))
    return True, json.loads(text)


async def _public_call(name: str, arguments: dict):
    handler = server.mcp.request_handlers[mcp_types.CallToolRequest]
    request = mcp_types.CallToolRequest(
        params=mcp_types.CallToolRequestParams(name=name, arguments=arguments)
    )
    return (await handler(request)).root


@pytest.mark.asyncio
async def test_every_live_gh_mutation_advertises_required_expected_document_id():
    with _panel_locked():
        tools = await server._all_live_tools()

    mutations = [
        tool
        for tool in tools
        if classify_gh_tool(tool.name) is GhToolClassification.MUTATION
    ]
    assert mutations
    for tool in mutations:
        expected = tool.inputSchema["properties"][EXPECTED_GH_DOCUMENT_ID_ARGUMENT]
        assert expected == {
            "type": "string",
            "description": (
                "Canonical Grasshopper DocumentID observed immediately before "
                "this mutation."
            ),
        }
        assert EXPECTED_GH_DOCUMENT_ID_ARGUMENT in tool.inputSchema["required"]


@pytest.mark.asyncio
async def test_chirp_create_advertises_required_expected_document_id():
    with _panel_locked():
        tools = {tool.name: tool for tool in await server._all_live_tools()}
    schema = tools["chirp_create"].inputSchema

    assert EXPECTED_GH_DOCUMENT_ID_ARGUMENT in schema["properties"]
    assert EXPECTED_GH_DOCUMENT_ID_ARGUMENT in schema["required"]


@pytest.mark.parametrize("name", ["gh_update_script", "chirp_create"])
@pytest.mark.asyncio
async def test_non_panel_mutation_schema_preserves_legacy_contract(name):
    server.targeting.reset_targeting_state_for_tests()
    tools = {tool.name: tool for tool in await server._all_live_tools()}
    schema = tools[name].inputSchema

    assert EXPECTED_GH_DOCUMENT_ID_ARGUMENT not in schema.get("properties", {})
    assert EXPECTED_GH_DOCUMENT_ID_ARGUMENT not in schema.get("required", [])


@pytest.mark.parametrize(
    "name",
    [
        "gh_status",
        "gh_snapshot",
        "gh_canvas_image",
        "gh_structure_query",
        "gh_component_search",
        "gh_library",
        "gh_document_open",
        "gh_document_new",
        "gh_learn_directory",
    ],
)
@pytest.mark.asyncio
async def test_non_mutating_gh_schemas_do_not_advertise_expected_document_id(name):
    with _panel_locked():
        tools = {tool.name: tool for tool in await server._all_live_tools()}
    if name not in tools:
        return

    schema = tools[name].inputSchema
    assert EXPECTED_GH_DOCUMENT_ID_ARGUMENT not in schema.get("properties", {})
    assert EXPECTED_GH_DOCUMENT_ID_ARGUMENT not in schema.get("required", [])


@pytest.mark.asyncio
async def test_rook_tools_read_returns_the_same_augmented_mutation_schema(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    server._reset_capability_index_cache()

    with _panel_locked():
        direct = {
            tool.name: tool for tool in await server._all_live_tools()
        }["gh_update_script"].inputSchema
        success, gateway = _result_payload(
            await server.call_tool("rook_tools_read", {"name": "gh_update_script"})
        )

    assert success is True
    assert gateway["input_schema"] == direct


@pytest.mark.parametrize(
    "outer",
    [
        ("gh_update_script", {"guid": "C1", "code": "x = 1"}),
        (
            "rook_tools_call",
            {
                "name": "gh_update_script",
                "arguments": {"guid": "C1", "code": "x = 1"},
            },
        ),
    ],
)
@pytest.mark.asyncio
async def test_missing_expected_document_id_refuses_before_routing(monkeypatch, outer):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    routed = False

    def policy(_name):
        nonlocal routed
        routed = True
        return SimpleNamespace(requires_rhino=False)

    monkeypatch.setattr(server.targeting, "policy_for_tool", policy)
    with _panel_locked():
        success, payload = _result_payload(await server.call_tool(*outer))

    assert success is False
    assert payload["error"] == "gh_target_required"
    assert routed is False


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("chirp_create", {"signature": "Create a narrator"}),
        (
            "rook_tools_call",
            {
                "name": "chirp_create",
                "arguments": {"signature": "Create a narrator"},
            },
        ),
    ],
)
@pytest.mark.asyncio
async def test_chirp_missing_expected_document_id_refuses_before_dispatch(
    monkeypatch, name, arguments
):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    dispatched = False

    async def fail_if_dispatched(_name, _arguments):
        nonlocal dispatched
        dispatched = True
        raise AssertionError("chirp_create dispatched without GH custody")

    monkeypatch.setattr(
        server.targeting,
        "policy_for_tool",
        lambda _name: SimpleNamespace(requires_rhino=False),
    )
    monkeypatch.setattr(server, "_call_tool_dispatch", fail_if_dispatched)

    with _panel_locked():
        success, payload = _result_payload(
            await server.call_tool(name, arguments)
        )

    assert success is False
    assert payload["error"] == "gh_target_required"
    assert dispatched is False


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("gh_update_script", {"guid": "C1", "code": "x = 1"}),
        (
            "chirp_create",
            {
                "pins_in": [],
                "pins_out": [],
                "signature": "Create a narrator",
                "category": "narrator",
            },
        ),
        (
            "rook_tools_call",
            {
                "name": "gh_update_script",
                "arguments": {"guid": "C1", "code": "x = 1"},
            },
        ),
        (
            "rook_tools_call",
            {
                "name": "chirp_create",
                "arguments": {
                    "pins_in": [],
                    "pins_out": [],
                    "signature": "Create a narrator",
                    "category": "narrator",
                },
            },
        ),
    ],
)
@pytest.mark.asyncio
async def test_non_panel_mutation_preserves_legacy_dispatch(
    monkeypatch, name, arguments
):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    server.targeting.reset_targeting_state_for_tests()
    monkeypatch.setattr(
        server.targeting,
        "policy_for_tool",
        lambda _name: SimpleNamespace(requires_rhino=False),
    )

    async def dispatch(dispatched_name, dispatched_arguments):
        return {
            "success": True,
            "data": {
                "name": dispatched_name,
                "arguments": dispatched_arguments,
            },
        }

    monkeypatch.setattr(server, "_call_tool_dispatch", dispatch)

    success, payload = _result_payload(await server.call_tool(name, arguments))

    assert success is True
    expected_name = arguments.get("name", name)
    expected_arguments = arguments.get("arguments", arguments)
    assert payload == {"name": expected_name, "arguments": expected_arguments}


@pytest.mark.asyncio
async def test_direct_mcp_missing_expected_document_id_uses_stable_rook_refusal(
    monkeypatch,
):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")

    with _panel_locked():
        result = await _public_call(
            "gh_update_script",
            {"guid": "C1", "code": "x = 1"},
        )

    assert result.isError is True
    assert result.structuredContent["data"]["error"] == "gh_target_required"


@pytest.mark.parametrize(
    "value",
    [
        "not-a-guid",
        "00000000-0000-0000-0000-000000000000",
        "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA",
        "{aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa}",
    ],
)
@pytest.mark.asyncio
async def test_invalid_or_noncanonical_expected_document_id_is_invalid_arguments(
    monkeypatch, value
):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    monkeypatch.setattr(
        server.targeting,
        "policy_for_tool",
        lambda _name: SimpleNamespace(requires_rhino=False),
    )

    with _panel_locked():
        success, payload = _result_payload(
            await server.call_tool(
                "gh_update_script",
                {
                    "guid": "C1",
                    "code": "x = 1",
                    EXPECTED_GH_DOCUMENT_ID_ARGUMENT: value,
                },
            )
        )

    assert success is False
    assert payload["error"] == "invalid_arguments"
    assert payload["name"] == "gh_update_script"


@pytest.mark.asyncio
async def test_valid_expected_document_id_is_service_context_not_tool_argument(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    monkeypatch.setattr(
        server.targeting,
        "policy_for_tool",
        lambda _name: SimpleNamespace(requires_rhino=False),
    )

    async def inspect_dispatch(name, arguments):
        context = current_gh_dispatch_context()
        observe_gh_document_id(
            {"success": True, "data": {"ghDocumentId": expected}}
        )
        return {
            "success": True,
            "data": {
                "name": name,
                "arguments": arguments,
                "scope": context.classification.value,
                "expected": context.expected_gh_document_id,
            },
        }

    monkeypatch.setattr(server, "_call_tool_dispatch", inspect_dispatch)
    expected = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    with _panel_locked():
        success, payload = _result_payload(
            await server.call_tool(
                "gh_update_script",
                {
                    "guid": "C1",
                    "code": "x = 1",
                    EXPECTED_GH_DOCUMENT_ID_ARGUMENT: expected,
                },
            )
        )

    assert success is True
    assert payload == {
        "name": "gh_update_script",
        "arguments": {"guid": "C1", "code": "x = 1"},
        "scope": "mutation",
        "expected": expected,
        "ghDocumentId": expected,
    }


@pytest.mark.asyncio
async def test_gateway_mutation_reenters_the_same_service_owned_dispatch(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    monkeypatch.setattr(
        server.targeting,
        "policy_for_tool",
        lambda _name: SimpleNamespace(requires_rhino=False),
    )

    async def inspect_dispatch(name, arguments):
        context = current_gh_dispatch_context()
        observe_gh_document_id(
            {"success": True, "data": {"ghDocumentId": expected}}
        )
        return {
            "success": True,
            "data": {
                "arguments": arguments,
                "scope": context.classification.value,
                "expected": context.expected_gh_document_id,
            },
        }

    monkeypatch.setattr(server, "_call_tool_dispatch", inspect_dispatch)
    expected = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    with _panel_locked():
        success, payload = _result_payload(
            await server.call_tool(
                "rook_tools_call",
                {
                    "name": "gh_update_script",
                    "arguments": {
                        "guid": "C1",
                        "code": "x = 1",
                        EXPECTED_GH_DOCUMENT_ID_ARGUMENT: expected,
                    },
                },
            )
        )

    assert success is True
    assert payload == {
        "arguments": {"guid": "C1", "code": "x = 1"},
        "scope": "mutation",
        "expected": expected,
        "ghDocumentId": expected,
    }


@pytest.mark.asyncio
async def test_service_context_never_enters_authoring_or_routing_arguments(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    observed = []

    def inspect_authoring(_name, arguments):
        observed.append(dict(arguments))
        return None

    monkeypatch.setattr(server, "model_facing_script_handoff", inspect_authoring)
    monkeypatch.setattr(
        server.targeting,
        "policy_for_tool",
        lambda _name: SimpleNamespace(requires_rhino=False),
    )
    monkeypatch.setattr(
        server,
        "_call_tool_dispatch",
        lambda _name, _arguments: asyncio.sleep(
            0, result={"success": True, "data": {}}
        ),
    )

    with _panel_locked():
        await server.call_tool(
            "gh_update_script",
            {
                "guid": "C1",
                "code": "x = 1",
                EXPECTED_GH_DOCUMENT_ID_ARGUMENT: (
                    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
                ),
            },
        )

    assert observed
    assert EXPECTED_GH_DOCUMENT_ID_ARGUMENT not in observed[0]
    assert INTERNAL_GH_SCOPE_FIELD not in observed[0]
    assert INTERNAL_EXPECTED_GH_DOCUMENT_ID_FIELD not in observed[0]


@pytest.mark.parametrize(
    "field",
    [INTERNAL_GH_SCOPE_FIELD, INTERNAL_EXPECTED_GH_DOCUMENT_ID_FIELD],
)
@pytest.mark.asyncio
async def test_model_cannot_supply_service_owned_dispatch_fields(monkeypatch, field):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    with _panel_locked():
        success, payload = _result_payload(
            await server.call_tool(
                "gh_status",
                {field: "model-supplied"},
            )
        )

    assert success is False
    assert payload["error"] == "invalid_arguments"
    assert payload["name"] == "gh_status"


def test_composite_transition_projects_final_nested_document_identity():
    context = GhDispatchContext(GhToolClassification.TRANSITION, None)
    document_id = "11111111-1111-1111-1111-111111111111"

    with gh_dispatch_scope(context):
        observe_gh_document_id(
            {"success": True, "data": {"ghDocumentId": document_id}}
        )
        result = project_current_gh_document_id(
            {"success": True, "data": {"processed": 1}}, context
        )

    assert result["data"]["ghDocumentId"] == document_id


@pytest.mark.asyncio
async def test_guarded_mutation_rejects_contradictory_managed_identity(monkeypatch):
    expected = "11111111-1111-1111-1111-111111111111"
    returned = "22222222-2222-2222-2222-222222222222"
    calls = []

    async def bridge(endpoint, method="GET", data=None, **kwargs):
        calls.append((endpoint, method, data))
        return {"success": True, "data": {"ghDocumentId": returned}}

    monkeypatch.setattr(server, "_bridge_call_rhino", bridge)
    context = GhDispatchContext(GhToolClassification.MUTATION, expected)

    with gh_dispatch_scope(context):
        result = await server.call_rhino("/gh/set-value", "POST", {"guid": "C1"})
        projected = project_current_gh_document_id(result, context)

    assert calls == [
        (
            "/gh/set-value",
            "POST",
            {
                "guid": "C1",
                INTERNAL_GH_SCOPE_FIELD: "mutation",
                INTERNAL_EXPECTED_GH_DOCUMENT_ID_FIELD: expected,
            },
        )
    ]
    assert result["success"] is False
    assert result["data"]["error"] == "gh_target_changed"
    assert projected["success"] is False
    assert projected["data"]["error"] == "gh_target_changed"


@pytest.mark.parametrize(
    "mutation_data",
    [
        {"updated": True},
        {"updated": True, "ghDocumentId": "not-a-guid"},
        {
            "updated": True,
            "ghDocumentId": "00000000-0000-0000-0000-000000000000",
        },
    ],
    ids=["missing", "malformed", "zero"],
)
@pytest.mark.asyncio
async def test_mutation_cannot_reuse_preflight_identity(monkeypatch, mutation_data):
    expected = "11111111-1111-1111-1111-111111111111"
    responses = iter(
        [
            {"success": True, "data": {"ghDocumentId": expected}},
            {"success": True, "data": mutation_data},
        ]
    )

    async def bridge(endpoint, method="GET", data=None, **kwargs):
        return next(responses)

    monkeypatch.setattr(server, "_bridge_call_rhino", bridge)
    context = GhDispatchContext(GhToolClassification.MUTATION, expected)

    with gh_dispatch_scope(context):
        preflight = await server.call_rhino("/gh/status")
        mutation = await server.call_rhino("/gh/set-value", "POST", {"guid": "C1"})
        projected = project_current_gh_document_id(mutation, context)

    assert preflight["success"] is True
    assert mutation["success"] is False
    assert mutation["data"]["error"] == "gh_target_unavailable"
    assert projected["success"] is False
    assert projected["data"]["error"] == "gh_target_unavailable"


@pytest.mark.asyncio
async def test_composite_observation_latches_first_identity_before_later_calls(
    monkeypatch,
):
    first = "11111111-1111-1111-1111-111111111111"
    changed = "22222222-2222-2222-2222-222222222222"
    calls = []
    responses = iter(
        [
            {"success": True, "data": {"ghDocumentId": first}},
            {"success": True, "data": {"ghDocumentId": changed}},
        ]
    )

    async def bridge(endpoint, method="GET", data=None, **kwargs):
        calls.append((endpoint, method, data))
        return next(responses)

    monkeypatch.setattr(server, "_bridge_call_rhino", bridge)
    context = GhDispatchContext(GhToolClassification.OBSERVATION, None)

    with gh_dispatch_scope(context):
        first_result = await server.call_rhino("/gh/snapshot")
        changed_result = await server.call_rhino(
            "/gh/batch-component-info",
            "POST",
            {"guids": ["C1"]},
        )
        projected = project_current_gh_document_id(
            {"success": True, "data": {"learned": True}}, context
        )

    assert first_result["success"] is True
    assert INTERNAL_EXPECTED_GH_DOCUMENT_ID_FIELD not in calls[0][2]
    assert calls[1][2][INTERNAL_EXPECTED_GH_DOCUMENT_ID_FIELD] == first
    assert changed_result["success"] is False
    assert changed_result["data"]["error"] == "gh_target_changed"
    assert projected["success"] is False
    assert projected["data"]["error"] == "gh_target_changed"


@pytest.mark.parametrize(
    "later_data",
    [
        {"objects": []},
        {"objects": [], "ghDocumentId": "not-a-guid"},
        {
            "objects": [],
            "ghDocumentId": "00000000-0000-0000-0000-000000000000",
        },
    ],
    ids=["missing", "malformed", "zero"],
)
@pytest.mark.asyncio
async def test_composite_observation_requires_identity_from_every_managed_call(
    monkeypatch, later_data
):
    first = "11111111-1111-1111-1111-111111111111"
    responses = iter(
        [
            {"success": True, "data": {"ghDocumentId": first}},
            {"success": True, "data": later_data},
        ]
    )

    async def bridge(endpoint, method="GET", data=None, **kwargs):
        return next(responses)

    monkeypatch.setattr(server, "_bridge_call_rhino", bridge)
    context = GhDispatchContext(GhToolClassification.OBSERVATION, None)

    with gh_dispatch_scope(context):
        await server.call_rhino("/gh/snapshot")
        later = await server.call_rhino("/gh/batch-component-info", "POST", {})
        projected = project_current_gh_document_id(
            {"success": True, "data": {"learned": True}}, context
        )

    assert later["success"] is False
    assert later["data"]["error"] == "gh_target_unavailable"
    assert projected["success"] is False
    assert projected["data"]["error"] == "gh_target_unavailable"


@pytest.mark.asyncio
async def test_learn_canvas_cannot_hide_nested_document_drift(monkeypatch):
    first = "11111111-1111-1111-1111-111111111111"
    changed = "22222222-2222-2222-2222-222222222222"
    calls = []
    responses = iter(
        [
            {"success": True, "data": {"ghDocumentId": first}},
            {"success": True, "data": {"ghDocumentId": changed}},
        ]
    )

    async def bridge(endpoint, method="GET", data=None, **kwargs):
        calls.append((endpoint, method, data))
        return next(responses)

    async def composite(call, **kwargs):
        await call("/gh/snapshot")
        await call("/gh/batch-component-info", "POST", {"guids": ["C1"]})
        return {"errors": 0, "learned": True}

    monkeypatch.setattr(server, "_bridge_call_rhino", bridge)
    monkeypatch.setattr("rook.learning.canvas_learner.learn_from_canvas", composite)
    context = GhDispatchContext(GhToolClassification.OBSERVATION, None)

    result = await server._call_tool_dispatch_with_gh_context(
        "gh_learn_canvas", {}, context=context
    )

    assert calls[1][2][INTERNAL_EXPECTED_GH_DOCUMENT_ID_FIELD] == first
    assert result["success"] is False
    assert result["data"]["error"] == "gh_target_changed"


@pytest.mark.parametrize(
    ("bridge_data", "expected_error"),
    [
        (
            {"ghDocumentId": "22222222-2222-2222-2222-222222222222"},
            "gh_target_changed",
        ),
        ({}, "gh_target_unavailable"),
    ],
)
@pytest.mark.asyncio
async def test_panel_chirp_preflights_document_before_contacting_chirp(
    monkeypatch, bridge_data, expected_error
):
    expected = "11111111-1111-1111-1111-111111111111"
    managed_calls = []
    chirp_contacted = False

    async def bridge(endpoint, method="GET", data=None, **kwargs):
        managed_calls.append((endpoint, method, data))
        return {"success": True, "data": bridge_data}

    async def forbidden_chirp_start(_model):
        nonlocal chirp_contacted
        chirp_contacted = True
        raise AssertionError("Chirp started before GH target validation")

    monkeypatch.setattr(server, "_bridge_call_rhino", bridge)
    monkeypatch.setattr(
        "rook.chirp_manager.ensure_chirp_running", forbidden_chirp_start
    )
    context = GhDispatchContext(GhToolClassification.MUTATION, expected)

    with gh_dispatch_scope(context):
        result, terminal_failure, deterministic_only = (
            await server._execute_chirp_create(
                {
                    "signature": "Create a narrator",
                    "category": "narrator",
                    "pins_in": [{"name": "Question", "type": "string"}],
                    "pins_out": [{"name": "Answer", "type": "string"}],
                },
                None,
            )
        )

    assert result["success"] is False
    assert result["data"]["error"] == expected_error
    assert terminal_failure is False
    assert deterministic_only is False
    assert chirp_contacted is False
    assert managed_calls == [
        (
            "/gh/status",
            "GET",
            {
                INTERNAL_GH_SCOPE_FIELD: "mutation",
                INTERNAL_EXPECTED_GH_DOCUMENT_ID_FIELD: expected,
            },
        )
    ]


@pytest.mark.parametrize(
    "creation_identity",
    [None, "not-a-guid", "00000000-0000-0000-0000-000000000000"],
    ids=["missing", "malformed", "zero"],
)
@pytest.mark.asyncio
async def test_chirp_creation_cannot_reuse_preflight_identity(
    monkeypatch, creation_identity
):
    expected = "11111111-1111-1111-1111-111111111111"

    async def bridge(endpoint, method="GET", data=None, **kwargs):
        assert endpoint == "/gh/status"
        return {"success": True, "data": {"ghDocumentId": expected}}

    async def ensure_running(_model):
        return {"running": True, "host": "127.0.0.1", "port": 8765}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "script": "public class Script_Instance { }",
                "pins_in": [{"name": "Question", "type": "string"}],
                "pins_out": [{"name": "Answer", "type": "string"}],
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json):
            return FakeResponse()

    async def create_script(*args, **kwargs):
        data = {"component_guid": "C1"}
        if creation_identity is not None:
            data["ghDocumentId"] = creation_identity
        return {"success": True, "data": data}

    monkeypatch.setattr(server, "_bridge_call_rhino", bridge)
    monkeypatch.setattr("rook.chirp_manager.ensure_chirp_running", ensure_running)
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda *args, **kwargs: FakeClient())
    monkeypatch.setattr(server, "_execute_gh_create_script", create_script)
    context = GhDispatchContext(GhToolClassification.MUTATION, expected)

    with gh_dispatch_scope(context):
        result, _, _ = await server._execute_chirp_create(
            {
                "signature": "Create a narrator",
                "category": "narrator",
                "pins_in": [{"name": "Question", "type": "string"}],
                "pins_out": [{"name": "Answer", "type": "string"}],
            },
            None,
        )
        projected = project_current_gh_document_id(result, context)

    assert projected["success"] is False
    assert projected["data"]["error"] == "gh_target_unavailable"


def test_document_identity_observation_is_scoped_and_ignores_untrusted_shapes():
    context = GhDispatchContext(GhToolClassification.OBSERVATION, None)
    with gh_dispatch_scope(context):
        observe_gh_document_id(
            {"success": True, "data": {"ghDocumentId": "not-canonical"}}
        )
        projected = project_current_gh_document_id({"success": True}, context)
        assert projected["success"] is False
        assert projected["data"]["error"] == "gh_target_unavailable"

    with gh_dispatch_scope(context):
        projected = project_current_gh_document_id({"success": True}, context)
        assert projected["success"] is False
        assert projected["data"]["error"] == "gh_target_unavailable"


def test_document_independent_success_needs_no_document_identity():
    context = GhDispatchContext(GhToolClassification.DOCUMENT_INDEPENDENT, None)

    with gh_dispatch_scope(context):
        assert project_current_gh_document_id(
            {"success": True, "data": {"count": 2}}, context
        ) == {"success": True, "data": {"count": 2}}


@pytest.mark.asyncio
async def test_local_operation_needs_no_managed_document_identity(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    monkeypatch.setattr(
        server.targeting,
        "policy_for_tool",
        lambda _name: SimpleNamespace(requires_rhino=False),
    )

    async def local_dispatch(name, arguments):
        context = current_gh_dispatch_context()
        assert context.classification is GhToolClassification.DOCUMENT_INDEPENDENT
        return {"success": True, "data": {"name": name, "arguments": arguments}}

    monkeypatch.setattr(server, "_call_tool_dispatch", local_dispatch)

    with _panel_locked():
        success, payload = _result_payload(
            await server.call_tool("gh_structure_query", {"name": "Inputs"})
        )

    assert success is True
    assert payload == {
        "name": "gh_structure_query",
        "arguments": {"name": "Inputs"},
    }


@pytest.mark.parametrize("data", [None, "legacy success"])
def test_document_scoped_success_requires_projectable_identity_data(data):
    context = GhDispatchContext(GhToolClassification.OBSERVATION, None)

    with gh_dispatch_scope(context):
        observe_gh_document_id(
            {
                "success": True,
                "data": {
                    "ghDocumentId": "11111111-1111-1111-1111-111111111111"
                },
            }
        )
        projected = project_current_gh_document_id(
            {"success": True, "data": data}, context
        )

    assert projected["success"] is False
    assert projected["data"]["error"] == "gh_target_unavailable"


@pytest.mark.parametrize("with_file", [False, True], ids=["empty", "all-opens-fail"])
@pytest.mark.asyncio
async def test_learn_directory_observes_final_document_identity(
    monkeypatch, tmp_path, with_file
):
    if with_file:
        (tmp_path / "broken.gh").write_bytes(b"fixture")
    calls = []
    document_id = "11111111-1111-1111-1111-111111111111"

    async def bridge(endpoint, method="GET", data=None, **kwargs):
        calls.append((endpoint, method, data))
        if endpoint == "/gh/document/open":
            return {"success": False, "data": {"error": "open_failed"}}
        if endpoint == "/gh/status":
            return {"success": True, "data": {"ghDocumentId": document_id}}
        raise AssertionError(f"unexpected managed call: {endpoint}")

    monkeypatch.setattr(server, "_bridge_call_rhino", bridge)
    context = GhDispatchContext(GhToolClassification.TRANSITION, None)

    result = await server._call_tool_dispatch_with_gh_context(
        "gh_learn_directory",
        {"directory": str(tmp_path)},
        context=context,
    )

    assert calls[-1][0] == "/gh/status"
    assert result["success"] is True
    assert result["data"]["ghDocumentId"] == document_id


@pytest.mark.asyncio
async def test_non_panel_learn_directory_preserves_legacy_empty_result(
    monkeypatch, tmp_path
):
    calls = []

    async def bridge(endpoint, method="GET", data=None, **kwargs):
        calls.append((endpoint, method, data))
        raise AssertionError(f"unexpected managed call: {endpoint}")

    monkeypatch.setattr(server, "_bridge_call_rhino", bridge)

    result = await server._call_tool_dispatch_with_gh_context(
        "gh_learn_directory",
        {"directory": str(tmp_path)},
        context=None,
    )

    assert calls == []
    assert result["success"] is True
    assert result["data"]["processed"] == 0
    assert result["data"]["total_files_found"] == 0
    assert "ghDocumentId" not in result["data"]


@pytest.mark.asyncio
async def test_learn_directory_requires_identity_from_its_final_observation(
    monkeypatch, tmp_path
):
    (tmp_path / "opened.gh").write_bytes(b"fixture")
    earlier_id = "11111111-1111-1111-1111-111111111111"

    async def bridge(endpoint, method="GET", data=None, **kwargs):
        if endpoint == "/gh/document/open":
            return {"success": True, "data": {"ghDocumentId": earlier_id}}
        if endpoint == "/gh/snapshot":
            return {"success": True, "data": {"objects": []}}
        if endpoint == "/gh/status":
            return {"success": True, "data": {}}
        raise AssertionError(f"unexpected managed call: {endpoint}")

    monkeypatch.setattr(server, "_bridge_call_rhino", bridge)
    context = GhDispatchContext(GhToolClassification.TRANSITION, None)

    result = await server._call_tool_dispatch_with_gh_context(
        "gh_learn_directory",
        {"directory": str(tmp_path)},
        context=context,
    )

    assert result["success"] is False
    assert result["data"]["error"] == "gh_target_unavailable"
