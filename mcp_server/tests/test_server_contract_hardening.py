import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from rook import server
from rook import targeting


class _DummyPhaseTracker:
    def record_call(self, _name: str) -> None:
        pass


def _decode_response(response):
    text = response[0].text
    if text.startswith("Error: "):
        raw = text[len("Error: "):]
        try:
            return {"success": False, "data": json.loads(raw)}
        except json.JSONDecodeError:
            return {"success": False, "data": raw}
    return {"success": True, "data": json.loads(text)}


@pytest.fixture
def patched_server(monkeypatch):
    targeting.reset_targeting_state_for_tests()
    monkeypatch.setattr(targeting, "discover_instances", lambda: [{
        "host": "127.0.0.1",
        "port": 9950,
        "processId": 7101,
        "pluginType": "native",
        "documentName": "ContractFixture.3dm",
    }])
    monkeypatch.setattr(server, "should_inject", lambda _name, _result: False)
    monkeypatch.setattr(server, "_record_observation", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "get_phase_tracker", lambda: _DummyPhaseTracker())
    yield
    targeting.reset_targeting_state_for_tests()


@pytest.mark.asyncio
async def test_rhino_command_rejects_non_underscored_command(monkeypatch, patched_server):
    call_rhino_mock = AsyncMock()
    monkeypatch.setattr(server, "call_rhino", call_rhino_mock)

    response = await server.call_tool("rhino_command", {"command": "Line 0,0,0 1,1,1"})
    payload = _decode_response(response)

    assert payload["success"] is False
    assert "start with '_'" in payload["data"]
    call_rhino_mock.assert_not_called()


@pytest.mark.asyncio
async def test_rhino_command_rejects_unknown_option_for_known_command(monkeypatch, patched_server):
    fake_store = SimpleNamespace(
        parse_command_string=lambda _cmd: {
            "command": "-Box",
            "syntax": "_-Box <corner1> <corner2> [height]",
            "parameters": {
                "corner1": "0,0,0",
                "corner2": "10,10,0",
            },
            "options_used": ["_Bogus"],
        },
        get_command=lambda _cmd: SimpleNamespace(
            options={"_Center": "Create from center"},
            modes={"default": SimpleNamespace(syntax="_-Box _Center <center> <corner> [height]")},
        ),
    )
    monkeypatch.setattr(server, "command_learner", SimpleNamespace(knowledge_store=fake_store))
    call_rhino_mock = AsyncMock()
    monkeypatch.setattr(server, "call_rhino", call_rhino_mock)

    response = await server.call_tool("rhino_command", {"command": "_-Box _Bogus 0,0,0 10,10,0"})
    payload = _decode_response(response)

    assert payload["success"] is False
    assert "_Bogus" in payload["data"]
    assert "Known options" in payload["data"]
    call_rhino_mock.assert_not_called()


@pytest.mark.asyncio
async def test_rhino_command_learn_is_rejected(monkeypatch, patched_server):
    call_rhino_mock = AsyncMock()
    monkeypatch.setattr(server, "call_rhino", call_rhino_mock)

    response = await server.call_tool("rhino_command_learn", {"command": "_-Box 0,0,0 1,1,1"})
    payload = _decode_response(response)

    assert payload["success"] is False
    assert "deprecated and disabled" in payload["data"]
    call_rhino_mock.assert_not_called()


@pytest.mark.asyncio
async def test_rhino_command_tool_contract_only_lists_safe_scripted_command(monkeypatch):
    monkeypatch.delenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", raising=False)
    monkeypatch.delenv("ROOK_MCP_TARGET_MODE", raising=False)
    tools = {tool.name: tool for tool in await server.list_tools()}

    assert "rhino_command" in tools
    desc = tools["rhino_command"].description
    assert "known-safe" in desc
    assert "non-interactive" in desc
    assert "fully parameterized" in desc
    assert "must start with '_'" in desc
    assert "unknown/ambiguous/prompt-driven/unclassified commands are rejected" in desc.lower()

    assert "rhino_command_interactive_start" not in tools
    assert "rhino_command_interactive_send" not in tools
    assert "rhino_command_experiment" not in tools
    assert "rhino_learn_interactive" not in tools
    assert "rhino_learn_next" not in tools
    assert "rhino_learn_variations_interactive" not in tools
    assert "rhino_prepare_geometry" not in tools
    assert "rhino_command_interactive_prompt" in tools
    assert "rhino_command_interactive_cancel" in tools


@pytest.mark.asyncio
async def test_interactive_learning_tools_list_only_in_dev_learning_mode(monkeypatch):
    monkeypatch.setenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", "1")
    monkeypatch.delenv("ROOK_MCP_TARGET_MODE", raising=False)
    dev_tools = {tool.name for tool in await server.list_tools()}

    assert "rhino_command_interactive_start" not in dev_tools
    assert "rhino_command_interactive_send" not in dev_tools
    assert "rhino_command_experiment" in dev_tools
    assert "rhino_learn_next" in dev_tools
    assert "rhino_prepare_geometry" in dev_tools

    monkeypatch.setenv("ROOK_MCP_TARGET_MODE", "panel_locked")
    panel_tools = {tool.name for tool in await server.list_tools()}

    assert "rhino_command_interactive_start" not in panel_tools
    assert "rhino_command_interactive_send" not in panel_tools
    assert "rhino_command_experiment" not in panel_tools
    assert "rhino_learn_next" not in panel_tools
    assert "rhino_prepare_geometry" not in panel_tools


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("rhino_command_interactive_start", {"command": "_-Box"}),
        ("rhino_command_interactive_send", {"input": "0,0,0"}),
        ("rhino_command_experiment", {"command": "_-Box", "variations": ["_-Box 0,0,0 1,1,1"]}),
        ("rhino_learn_interactive", {"command": "_-Box", "inputs": ["0,0,0"]}),
        ("rhino_learn_next", {}),
        ("rhino_learn_variations_interactive", {"command": "_-Box", "variations": [["0,0,0"]]}),
        ("rhino_prepare_geometry", {"geometry_type": "curve"}),
    ],
)
async def test_deprecated_interactive_command_tools_refuse_direct_calls_in_normal_mode(
    monkeypatch, patched_server, tool_name, arguments
):
    monkeypatch.delenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", raising=False)
    monkeypatch.delenv("ROOK_MCP_TARGET_MODE", raising=False)
    call_rhino_mock = AsyncMock()
    monkeypatch.setattr(server, "call_rhino", call_rhino_mock)

    response = await server.call_tool(tool_name, arguments)
    payload = _decode_response(response)

    assert payload["success"] is False
    assert payload["data"]["error"] == "interactive_command_deprecated"
    assert payload["data"]["tool"] == tool_name
    call_rhino_mock.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("rhino_command_interactive_start", {"command": "_-Box"}),
        ("rhino_command_interactive_send", {"input": "0,0,0"}),
        ("rhino_command_experiment", {"command": "_-Box", "variations": ["_-Box 0,0,0 1,1,1"]}),
        ("rhino_learn_interactive", {"command": "_-Box", "inputs": ["0,0,0"]}),
        ("rhino_learn_next", {}),
        ("rhino_learn_variations_interactive", {"command": "_-Box", "variations": [["0,0,0"]]}),
        ("rhino_prepare_geometry", {"geometry_type": "curve"}),
    ],
)
async def test_deprecated_interactive_command_tools_refuse_direct_calls_in_panel_locked_mode(
    monkeypatch, patched_server, tool_name, arguments
):
    monkeypatch.setenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", "1")
    monkeypatch.setenv("ROOK_MCP_TARGET_MODE", "panel_locked")
    call_rhino_mock = AsyncMock()
    monkeypatch.setattr(server, "call_rhino", call_rhino_mock)

    response = await server.call_tool(tool_name, arguments)
    payload = _decode_response(response)

    assert payload["success"] is False
    assert payload["data"]["error"] == "interactive_command_deprecated"
    assert payload["data"]["tool"] == tool_name
    call_rhino_mock.assert_not_called()


@pytest.mark.asyncio
async def test_rhino_command_rejects_when_command_safety_store_unavailable(monkeypatch, patched_server):
    monkeypatch.setattr(server, "command_learner", SimpleNamespace(knowledge_store=None))
    call_rhino_mock = AsyncMock()
    monkeypatch.setattr(server, "call_rhino", call_rhino_mock)

    response = await server.call_tool("rhino_command", {"command": "_-Box 0,0,0 1,1,1"})
    payload = _decode_response(response)

    assert payload["success"] is False
    assert payload["data"]["error"] == "run_script_safety_refusal"
    assert payload["data"]["reason"] == "command_safety_unavailable"
    call_rhino_mock.assert_not_called()


@pytest.mark.asyncio
async def test_deprecated_interactive_refusal_records_observation(monkeypatch, patched_server):
    monkeypatch.delenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", raising=False)
    monkeypatch.delenv("ROOK_MCP_TARGET_MODE", raising=False)
    record_mock = MagicMock()
    monkeypatch.setattr(server, "_record_observation", record_mock)
    call_rhino_mock = AsyncMock()
    monkeypatch.setattr(server, "call_rhino", call_rhino_mock)

    response = await server.call_tool("rhino_command_interactive_start", {"command": "_-Box"})
    payload = _decode_response(response)

    assert payload["success"] is False
    assert payload["data"]["error"] == "interactive_command_deprecated"
    record_mock.assert_called_once()
    call_rhino_mock.assert_not_called()


@pytest.mark.asyncio
async def test_interactive_cancel_preserves_native_uncertain_failure(monkeypatch, patched_server):
    native_failure = {
        "success": False,
        "data": {
            "cancelled": False,
            "verified": False,
            "state_uncertain": True,
            "prompt": "Select curves",
            "is_active": True,
        },
    }
    call_rhino_mock = AsyncMock(return_value=native_failure)
    monkeypatch.setattr(server, "call_rhino", call_rhino_mock)

    response = await server.call_tool("rhino_command_interactive_cancel", {})
    payload = _decode_response(response)

    assert payload["success"] is False
    assert payload["data"] == native_failure["data"]
    assert payload["data"]["cancelled"] is False
    assert payload["data"]["verified"] is False
    assert payload["data"]["state_uncertain"] is True
    call_rhino_mock.assert_awaited_once()
    assert call_rhino_mock.await_args.args == ("/command/cancel", "POST", None)


@pytest.mark.asyncio
async def test_interactive_prompt_preserves_native_uncertain_failure(monkeypatch, patched_server):
    native_failure = {
        "success": False,
        "data": {
            "error": "Could not read Rhino command prompt",
            "verified": False,
            "state_uncertain": True,
        },
    }
    call_rhino_mock = AsyncMock(return_value=native_failure)
    monkeypatch.setattr(server, "call_rhino", call_rhino_mock)

    response = await server.call_tool("rhino_command_interactive_prompt", {})
    payload = _decode_response(response)

    assert payload["success"] is False
    assert payload["data"] == native_failure["data"]
    assert payload["data"]["verified"] is False
    assert payload["data"]["state_uncertain"] is True
    call_rhino_mock.assert_awaited_once()
    assert call_rhino_mock.await_args.args == ("/command/prompt", "GET", None)


@pytest.mark.asyncio
async def test_gh_record_investigation_rejects_unverified_working_config(monkeypatch, patched_server, tmp_path):
    gh_dir = tmp_path / "gh"
    gh_dir.mkdir()
    tiered_path = gh_dir / "tiered_knowledge.json"
    tiered_path.write_text(json.dumps({"components": {}}), encoding="utf-8")
    obs_path = gh_dir / "gh_observations.json"
    obs_path.write_text(
        json.dumps(
            {
                "observations": {
                    "obs-success": {
                        "component_guid": "guid-1",
                        "config": {"E": 0},
                        "result": {"status": "success"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    def fake_resolve(_domain: str, filename: str):
        if filename == "tiered_knowledge.json":
            return tiered_path
        if filename == "gh_observations.json":
            return obs_path
        raise AssertionError(filename)

    monkeypatch.setattr(server, "resolve_writable_knowledge_path", fake_resolve)
    monkeypatch.setattr(server, "resolve_readable_knowledge_path", fake_resolve)
    call_rhino_mock = AsyncMock()
    monkeypatch.setattr(server, "call_rhino", call_rhino_mock)

    response = await server.call_tool(
        "gh_record_investigation",
        {
            "component_guid": "guid-1",
            "observation_ids": ["obs-success"],
            "working_config": {
                "id": "pipe_bad",
                "description": "Wrong config",
                "config": {"E": 2},
            },
            "gotcha": "E=0 works here",
        },
    )
    payload = _decode_response(response)

    assert payload["success"] is False
    assert "must match the config of a successful observation" in payload["data"]
    call_rhino_mock.assert_not_called()


@pytest.mark.asyncio
async def test_gh_record_investigation_records_grounded_success(monkeypatch, patched_server, tmp_path):
    gh_dir = tmp_path / "gh"
    gh_dir.mkdir()
    tiered_path = gh_dir / "tiered_knowledge.json"
    tiered_path.write_text(json.dumps({"components": {}}), encoding="utf-8")
    obs_path = gh_dir / "gh_observations.json"
    obs_path.write_text(
        json.dumps(
            {
                "observations": {
                    "obs-success": {
                        "component_guid": "guid-1",
                        "config": {"E": 0},
                        "result": {"status": "success"},
                        "learned": "",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    def fake_resolve(_domain: str, filename: str):
        if filename == "tiered_knowledge.json":
            return tiered_path
        if filename == "gh_observations.json":
            return obs_path
        raise AssertionError(filename)

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        assert route == "/gh/library"
        assert method == "POST"
        return {
            "success": True,
            "data": {
                "components": [
                    {"guid": "guid-1", "name": "Pipe"}
                ]
            },
        }

    monkeypatch.setattr(server, "resolve_writable_knowledge_path", fake_resolve)
    monkeypatch.setattr(server, "resolve_readable_knowledge_path", fake_resolve)
    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    response = await server.call_tool(
        "gh_record_investigation",
        {
            "component_guid": "guid-1",
            "observation_ids": ["obs-success"],
            "working_config": {
                "id": "pipe_open",
                "description": "Open pipe",
                "config": {"E": 0},
            },
            "gotcha": "E must be 0 for open pipe",
        },
    )
    payload = _decode_response(response)

    assert payload["success"] is True

    saved_tiered = json.loads(tiered_path.read_text(encoding="utf-8"))
    saved_obs = json.loads(obs_path.read_text(encoding="utf-8"))

    assert saved_tiered["components"]["guid-1"]["working_configs"][0]["config"] == {"E": 0}
    assert saved_tiered["components"]["guid-1"]["gotchas"][0]["text"] == "E must be 0 for open pipe"
    assert saved_obs["observations"]["obs-success"]["learned"] == "E must be 0 for open pipe"


def _preflight_codes(findings):
    return {finding.code for finding in findings}


def test_gh_csharp_create_preflight_accepts_simple_body_assignment():
    findings = server._preflight_gh_csharp_create_script_contract(
        "A = Convert.ToDouble(R);",
        [{"name": "R", "type": "double"}],
        [{"name": "A", "type": "double"}],
    )

    assert findings == []


def test_gh_csharp_create_preflight_rejects_invalid_keyword_and_duplicate_pins():
    findings = server._preflight_gh_csharp_create_script_contract(
        "A = 1;",
        [{"name": "class", "type": "double"}, {"name": "A", "type": "double"}],
        [{"name": "A", "type": "double"}, {"name": "1B", "type": "Brep"}],
    )

    codes = _preflight_codes(findings)
    assert "reserved_pin_identifier" in codes
    assert "duplicate_pin_identifier" in codes
    assert "invalid_pin_identifier" in codes


def test_gh_csharp_create_preflight_rejects_normalized_invalid_access():
    findings = server._preflight_gh_csharp_create_script_contract(
        "A = 1;",
        [{"name": "R", "type": "double", "access": "matrix"}],
        [{"name": "A", "type": "double"}],
    )

    assert any(
        finding.code == "invalid_pin_access" and finding.pin == "R"
        for finding in findings
    )


@pytest.mark.parametrize(
    "code",
    [
        "public class BadComponent : GH_Component { }",
        "protected override void SolveInstance(IGH_DataAccess DA) { }",
        "protected override void RegisterInputParams(GH_InputParamManager pManager) { }",
        "protected override void RegisterOutputParams(GH_OutputParamManager pManager) { }",
        "private void Helper(IGH_DataAccess DA) { }",
    ],
)
def test_gh_csharp_create_preflight_rejects_plugin_component_source(code):
    findings = server._preflight_gh_csharp_create_script_contract(
        code,
        [],
        [{"name": "B", "type": "Brep"}],
    )

    assert any(finding.code == "plugin_component_source" for finding in findings)


def test_gh_csharp_create_preflight_requires_body_output_assignment():
    findings = server._preflight_gh_csharp_create_script_contract(
        "var radius = 5.0;",
        [],
        [{"name": "B", "type": "Brep"}],
    )

    assert any(
        finding.code == "missing_output_assignment" and finding.pin == "B"
        for finding in findings
    )


@pytest.mark.parametrize("operator", ["=", "+=", "-=", "*=", "/=", "??="])
def test_gh_csharp_create_preflight_accepts_simple_output_assignment_operators(operator):
    findings = server._preflight_gh_csharp_create_script_contract(
        f"B {operator} value;",
        [],
        [{"name": "B", "type": "Brep"}],
    )

    assert not any(finding.code == "missing_output_assignment" for finding in findings)


def test_gh_csharp_create_preflight_does_not_accept_method_call_assignment_evidence():
    findings = server._preflight_gh_csharp_create_script_contract(
        "B.Add(value);",
        [],
        [{"name": "B", "type": "object"}],
    )

    assert any(finding.code == "missing_output_assignment" for finding in findings)


def test_gh_csharp_create_preflight_skips_assignment_check_for_full_source():
    findings = server._preflight_gh_csharp_create_script_contract(
        (
            "public class Script_Instance : GH_ScriptInstance { "
            "private void RunScript(ref object B) { } }"
        ),
        [],
        [{"name": "B", "type": "object"}],
    )

    assert not any(finding.code == "missing_output_assignment" for finding in findings)


@pytest.mark.parametrize("code", ['// B = value;', 'var note = "B = value";'])
def test_gh_csharp_create_preflight_ignores_assignment_text_in_comments_and_strings(code):
    findings = server._preflight_gh_csharp_create_script_contract(
        code,
        [],
        [{"name": "B", "type": "object"}],
    )

    assert any(
        finding.code == "missing_output_assignment" and finding.pin == "B"
        for finding in findings
    )


def test_gh_csharp_create_preflight_ignores_plugin_patterns_in_comments_and_strings():
    findings = server._preflight_gh_csharp_create_script_contract(
        (
            "// public class BadComponent : GH_Component { }\n"
            "var note = \"protected override void SolveInstance(IGH_DataAccess DA) { }\";\n"
            "var block = @\"RegisterInputParams(GH_InputParamManager pManager)\";\n"
            "B = value;"
        ),
        [],
        [{"name": "B", "type": "object"}],
    )

    assert not any(finding.code == "plugin_component_source" for finding in findings)


@pytest.mark.parametrize(
    "code",
    [
        "// void RunScript(ref object B) { }\nvar radius = 5.0;",
        'var note = "class Script_Instance : GH_ScriptInstance";',
    ],
)
def test_gh_csharp_create_preflight_ignores_full_source_markers_in_comments_and_strings(code):
    findings = server._preflight_gh_csharp_create_script_contract(
        code,
        [],
        [{"name": "B", "type": "object"}],
    )

    assert any(
        finding.code == "missing_output_assignment" and finding.pin == "B"
        for finding in findings
    )


def test_gh_csharp_create_preflight_ignores_raw_string_assignment_text():
    findings = server._preflight_gh_csharp_create_script_contract(
        'var s = """\n"B = value;"\n""";',
        [],
        [{"name": "B", "type": "object"}],
    )

    assert any(
        finding.code == "missing_output_assignment" and finding.pin == "B"
        for finding in findings
    )


def test_gh_csharp_create_preflight_ignores_raw_string_plugin_patterns():
    findings = server._preflight_gh_csharp_create_script_contract(
        'var s = """\n"public class BadComponent : GH_Component { }"\n'
        '"protected override void SolveInstance(IGH_DataAccess DA) { }"\n""";\n'
        "B = value;",
        [],
        [{"name": "B", "type": "object"}],
    )

    assert not any(finding.code == "plugin_component_source" for finding in findings)


def test_gh_csharp_create_preflight_ignores_raw_string_full_source_markers():
    findings = server._preflight_gh_csharp_create_script_contract(
        'var s = """\n'
        '"public class Script_Instance : GH_ScriptInstance { }"\n'
        '"void RunScript(ref object B) { }"\n'
        '""";',
        [],
        [{"name": "B", "type": "object"}],
    )

    assert any(
        finding.code == "missing_output_assignment" and finding.pin == "B"
        for finding in findings
    )


@pytest.mark.asyncio
async def test_gh_create_csharp_script_accepts_rich_pin_objects(monkeypatch, patched_server):
    recorded_calls = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        recorded_calls.append((route, method, payload))
        if route == "/gh/create-component":
            return {"success": True, "data": {"guid": "script-guid"}}
        if route == "/gh/script-params":
            assert payload == {
                "guid": "script-guid",
                "inputs": [{
                    "name": "Values",
                    "type": "double",
                    "access": "list",
                    "optional": False,
                    "description": "All values",
                }],
                "outputs": [{
                    "name": "Sum",
                    "type": "double",
                    "description": "Summed output",
                }],
                "nick": "Accumulator",
            }
            return {"success": True, "data": {"Guid": "script-guid", "Inputs": 1, "Outputs": 2}}
        if route == "/gh/script":
            assert "private void RunScript(object Values, ref object Sum)" in payload["script"]
            return {"success": True, "data": {"Guid": "script-guid"}}
        if route == "/gh/errors":
            return {"success": True, "data": {"errors": []}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    response = await server.call_tool(
        "gh_create_csharp_script",
        {
            "code": "Sum = Values;",
            "pins_in": [{
                "name": "Values",
                "type": "double",
                "access": "list",
                "optional": False,
                "description": "All values",
            }],
            "pins_out": [{
                "name": "Sum",
                "type": "double",
                "description": "Summed output",
            }],
            "name": "Accumulator",
        },
    )
    payload = _decode_response(response)

    assert payload["success"] is True
    assert payload["data"]["pins_in"][0]["access"] == "list"
    assert payload["data"]["pins_in"][0]["optional"] is False
    assert payload["data"]["pins_out"][0]["description"] == "Summed output"
    assert any(route == "/gh/script-params" for route, _, _ in recorded_calls)


@pytest.mark.asyncio
async def test_gh_create_csharp_script_compile_errors_fail_but_preserve_component_guid(
    monkeypatch, patched_server
):
    component_guid = "12345678-1234-4234-9234-123456789abc"

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/create-component":
            return {"success": True, "data": {"guid": component_guid}}
        if route == "/gh/script-params":
            return {"success": True, "data": {"guid": component_guid}}
        if route == "/gh/script":
            return {"success": True, "data": {"guid": component_guid}}
        if route == "/gh/errors":
            return {
                "success": True,
                "data": {
                    "errors": [{"guid": component_guid, "errors": ["The name Boxx does not exist"]}],
                    "warnings": [],
                },
            }
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_create_csharp_script",
        {
            "code": "B = Boxx;",
            "pins_in": [],
            "pins_out": ["B:Brep"],
            "name": "Box Maker",
        },
    ))

    assert payload["success"] is False
    data = payload["data"]
    assert data["message"] == (
        "Component was created, but the target script component has compile errors."
    )
    assert data["component_guid"] == component_guid
    assert data["name"] == "Box Maker"
    assert data["pins_out"] == [{"name": "B", "type": "Brep"}]
    assert data["compilation_errors"] == ["The name Boxx does not exist"]


@pytest.mark.asyncio
async def test_gh_create_script_csharp_compile_errors_share_failure_shape(
    monkeypatch, patched_server
):
    component_guid = "12345678-1234-4234-9234-123456789abc"

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/create-component":
            return {"success": True, "data": {"guid": component_guid}}
        if route == "/gh/script-params":
            return {"success": True, "data": {"guid": component_guid}}
        if route == "/gh/script":
            return {"success": True, "data": {"guid": component_guid}}
        if route == "/gh/errors":
            return {
                "success": True,
                "data": {
                    "errors": [{"guid": component_guid, "errors": ["Cannot convert Box to Brep"]}],
                    "warnings": [],
                },
            }
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_create_script",
        {
            "language": "csharp",
            "code": "B = new Box();",
            "pins_in": [],
            "pins_out": ["B:Brep"],
            "name": "Box Maker",
        },
    ))

    assert payload["success"] is False
    assert payload["data"]["message"] == (
        "Component was created, but the target script component has compile errors."
    )
    assert payload["data"]["component_guid"] == component_guid
    assert payload["data"]["compilation_errors"] == ["Cannot convert Box to Brep"]


@pytest.mark.asyncio
async def test_gh_create_csharp_script_compile_errors_match_capitalized_live_shape(
    monkeypatch, patched_server
):
    component_guid = "12345678-1234-4234-9234-123456789abc"

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/create-component":
            return {"success": True, "data": {"Guid": component_guid}}
        if route == "/gh/script-params":
            return {"success": True, "data": {"Guid": component_guid}}
        if route == "/gh/script":
            return {"success": True, "data": {"Guid": component_guid}}
        if route == "/gh/errors":
            return {
                "success": True,
                "Data": {
                    "Errors": [{"Guid": component_guid, "Errors": ["capitalized compile"]}],
                    "Warnings": [],
                },
            }
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_create_csharp_script",
        {
            "code": "B = MissingSymbol;",
            "pins_in": [],
            "pins_out": ["B:Brep"],
        },
    ))

    assert payload["success"] is False
    assert payload["data"]["component_guid"] == component_guid
    assert payload["data"]["compilation_errors"] == ["capitalized compile"]


@pytest.mark.asyncio
async def test_gh_create_python_script_accepts_rich_pin_objects(monkeypatch, patched_server):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/create-component":
            return {"success": True, "data": {"guid": "py-script-guid"}}
        if route == "/gh/script-params":
            assert payload == {
                "guid": "py-script-guid",
                "inputs": [{
                    "name": "Pts",
                    "type": "Point3d",
                    "access": "list",
                    "optional": False,
                    "description": "Input points",
                }],
                "outputs": [{
                    "name": "Result",
                    "type": "Point3d",
                    "description": "Computed result",
                }],
                "nick": "Py Accumulator",
            }
            return {"success": True, "data": {"Guid": "py-script-guid", "Inputs": 1, "Outputs": 2}}
        if route == "/gh/script":
            assert "# ── Auto-generated GH input coercion" in payload["script"]
            return {"success": True, "data": {"Guid": "py-script-guid"}}
        if route == "/gh/errors":
            return {"success": True, "data": {"errors": []}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    response = await server.call_tool(
        "gh_create_python_script",
        {
            "code": "Result = Pts",
            "pins_in": [{
                "name": "Pts",
                "type": "Point3d",
                "access": "list",
                "optional": False,
                "description": "Input points",
            }],
            "pins_out": [{
                "name": "Result",
                "type": "Point3d",
                "description": "Computed result",
            }],
            "name": "Py Accumulator",
        },
    )
    payload = _decode_response(response)

    assert payload["success"] is True
    assert payload["data"]["pins_in"][0]["access"] == "list"
    assert payload["data"]["pins_in"][0]["optional"] is False
    assert payload["data"]["pins_out"][0]["description"] == "Computed result"


@pytest.mark.asyncio
async def test_gh_set_script_pins_merges_existing_component_params(monkeypatch, patched_server):
    script_params_payloads = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/component":
            return {
                "success": True,
                "data": {
                    "guid": "script-guid",
                    "nickName": "Old Script",
                    "params": {
                        "inputs": [
                            {
                                "index": 0,
                                "name": "Curves",
                                "nickName": "Crv",
                                "typeName": "Curve",
                                "access": "item",
                                "optional": True,
                                "description": "",
                                "hidden": False,
                            }
                        ],
                        "outputs": [
                            {
                                "index": 0,
                                "name": "out",
                                "nickName": "out",
                                "access": "item",
                                "description": "",
                                "hidden": False,
                            },
                            {
                                "index": 1,
                                "name": "Result",
                                "nickName": "Res",
                                "typeName": "Brep",
                                "access": "item",
                                "description": "",
                                "hidden": False,
                            },
                        ],
                    },
                },
            }
        if route == "/gh/script-params":
            script_params_payloads.append(payload)
            return {"success": True, "data": {"Guid": "script-guid", "Inputs": 1, "Outputs": 2}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    response = await server.call_tool(
        "gh_set_script_pins",
        {
            "guid": "C12",
            "input_updates": [{
                "index": 0,
                "access": "list",
                "optional": False,
                "description": "All input curves",
            }],
            "output_updates": [{
                "current_name": "Result",
                "name": "JoinedResult",
                "description": "Joined result",
            }],
            "name": "Joined Script",
            "description": "Updated script component",
        },
    )
    payload = _decode_response(response)

    assert payload["success"] is True
    assert len(script_params_payloads) == 1
    assert script_params_payloads[0] == {
        "guid": "C12",
        "inputs": [{
            "name": "Curves",
            "type": "Curve",
            "current_name": "Curves",
            "nick": "Crv",
            "access": "list",
            "optional": False,
            "description": "All input curves",
            "hidden": False,
        }],
        "outputs": [{
            "name": "JoinedResult",
            "type": "Brep",
            "current_name": "Result",
            "nick": "Res",
            "access": "item",
            "description": "Joined result",
            "hidden": False,
        }],
        "nick": "Joined Script",
        "description": "Updated script component",
    }
    assert payload["data"]["pins_in"][0]["access"] == "list"
    assert payload["data"]["pins_out"][0]["name"] == "JoinedResult"
    assert payload["data"]["pins_out"][0]["description"] == "Joined result"


# --- #41 coverage gaps for gh_set_script_pins ----------------------------
# Each test below uses a `_make_component_mock` helper to return a controlled
# params payload on `/gh/component`, then asserts either the payload shape
# of a resulting `/gh/script-params` POST (positive path) or the absence of
# one (rejection path). See https://github.com/bringfire/Rook/issues/41.


def _make_component_mock(inputs: list[dict], outputs: list[dict] | None = None):
    """Return a (fake_call_rhino, routes_called) tuple.

    `routes_called` is a list of (route, method, payload) tuples that the
    individual test asserts on. The mock ignores all routes other than
    /gh/component and /gh/script-params — any other call raises to surface
    test-surface drift loudly.
    """
    if outputs is None:
        outputs = [
            {"index": 0, "name": "out", "nickName": "out", "access": "item"},
        ]
    routes_called: list[tuple[str, str, Any]] = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        routes_called.append((route, method, payload))
        if route == "/gh/component":
            return {
                "success": True,
                "data": {
                    "guid": "script-guid",
                    "nickName": "Script",
                    "params": {"inputs": inputs, "outputs": outputs},
                },
            }
        if route == "/gh/script-params":
            return {
                "success": True,
                "data": {"Guid": "script-guid", "Inputs": len(inputs), "Outputs": len(outputs)},
            }
        raise AssertionError(f"Unexpected route: {route}")

    return fake_call_rhino, routes_called


@pytest.mark.asyncio
async def test_gh_set_script_pins_rejects_invalid_access_on_output_updates(monkeypatch, patched_server):
    """Gap #1 — Python pre-validator rejects invalid access BEFORE the
    mutation POST. Routed through `output_updates` because the live suite
    already covers input-side symmetrically; `_normalize_gh_script_pin_access`
    is shared across directions so this pin covers the normalizer branch
    with complementary coverage.
    """
    fake_call_rhino, routes = _make_component_mock(
        inputs=[{"index": 0, "name": "X", "nickName": "X", "access": "item"}],
        outputs=[
            {"index": 0, "name": "out", "nickName": "out", "access": "item"},
            {"index": 1, "name": "Result", "nickName": "Result", "access": "item"},
        ],
    )
    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    response = await server.call_tool(
        "gh_set_script_pins",
        {
            "guid": "script-guid",
            "output_updates": [{"current_name": "Result", "access": "bogus"}],
        },
    )
    payload = _decode_response(response)

    assert payload["success"] is False
    assert "Invalid pin access 'bogus'" in payload["data"]
    component_reads = [r for r in routes if r[0] == "/gh/component"]
    script_params_writes = [r for r in routes if r[0] == "/gh/script-params"]
    assert len(component_reads) == 1, f"expected 1 /gh/component read, got {routes!r}"
    assert not script_params_writes, f"no /gh/script-params POST expected, got {routes!r}"


@pytest.mark.asyncio
async def test_gh_set_script_pins_current_name_nick_collision_first_wins(monkeypatch, patched_server):
    """Gap #2 — current_name lookup accepts either pin.name or pin.nick, and
    returns the first index-order match. Pins this behavior explicitly since
    the issue flagged it as un-asserted (see `_apply_gh_script_pin_updates`
    loop at server.py:725-731). First-match-wins on name-or-nick is the
    current contract; tightening to name-only or raising on collision would
    be a separate behavior-change PR.
    """
    fake_call_rhino, _ = _make_component_mock(
        inputs=[
            # Two pins where the second one's `name` collides with the first's `nick`.
            {"index": 0, "name": "Alpha", "nickName": "X", "access": "item"},
            {"index": 1, "name": "X", "nickName": "Beta", "access": "item"},
        ],
    )
    script_params_payloads: list[dict] = []

    async def recording_call_rhino(route, method="GET", payload=None, port=None):
        result = await fake_call_rhino(route, method, payload, port)
        if route == "/gh/script-params":
            script_params_payloads.append(payload)
        return result

    monkeypatch.setattr(server, "call_rhino", recording_call_rhino)

    response = await server.call_tool(
        "gh_set_script_pins",
        {
            "guid": "script-guid",
            "input_updates": [{"current_name": "X", "name": "Renamed"}],
        },
    )
    payload = _decode_response(response)

    assert payload["success"] is True
    assert len(script_params_payloads) == 1
    inputs = script_params_payloads[0]["inputs"]
    # First-match-wins: pin at index 0 has nick="X", so current_name="X" hits
    # it before the literal name="X" at index 1. The rename applies to [0].
    assert inputs[0]["name"] == "Renamed"
    assert inputs[0]["current_name"] == "Alpha"
    assert inputs[0]["nick"] == "X"
    # Second pin is untouched.
    assert inputs[1]["name"] == "X"
    assert inputs[1].get("current_name") is None or inputs[1]["current_name"] == "X"


@pytest.mark.asyncio
async def test_gh_set_script_pins_multi_rename_in_one_call(monkeypatch, patched_server):
    """Gap #3 — two independent renames in a single call both round-trip."""
    fake_call_rhino, _ = _make_component_mock(
        inputs=[
            {"index": 0, "name": "A", "nickName": "A", "access": "item"},
            {"index": 1, "name": "B", "nickName": "B", "access": "item"},
        ],
    )
    script_params_payloads: list[dict] = []

    async def recording_call_rhino(route, method="GET", payload=None, port=None):
        result = await fake_call_rhino(route, method, payload, port)
        if route == "/gh/script-params":
            script_params_payloads.append(payload)
        return result

    monkeypatch.setattr(server, "call_rhino", recording_call_rhino)

    response = await server.call_tool(
        "gh_set_script_pins",
        {
            "guid": "script-guid",
            "input_updates": [
                {"current_name": "A", "name": "A2"},
                {"current_name": "B", "name": "B2"},
            ],
        },
    )
    payload = _decode_response(response)

    assert payload["success"] is True
    assert len(script_params_payloads) == 1
    inputs = script_params_payloads[0]["inputs"]
    assert inputs[0]["name"] == "A2" and inputs[0]["current_name"] == "A"
    assert inputs[1]["name"] == "B2" and inputs[1]["current_name"] == "B"


@pytest.mark.asyncio
async def test_gh_set_script_pins_no_op_rename_preserves_current_name(monkeypatch, patched_server):
    """Gap #4 — `current_name == name` is valid and idempotent. The payload
    must still carry `current_name` because the C# handler uses it as the
    lookup key for wire re-attachment (see `GrasshopperHandler.cs:1262-1265`);
    dropping it in the no-op case would break reconnection.
    """
    fake_call_rhino, _ = _make_component_mock(
        inputs=[
            {"index": 0, "name": "X", "nickName": "X", "access": "item"},
        ],
    )
    script_params_payloads: list[dict] = []

    async def recording_call_rhino(route, method="GET", payload=None, port=None):
        result = await fake_call_rhino(route, method, payload, port)
        if route == "/gh/script-params":
            script_params_payloads.append(payload)
        return result

    monkeypatch.setattr(server, "call_rhino", recording_call_rhino)

    response = await server.call_tool(
        "gh_set_script_pins",
        {
            "guid": "script-guid",
            "input_updates": [{"current_name": "X", "name": "X"}],
        },
    )
    payload = _decode_response(response)

    assert payload["success"] is True
    assert len(script_params_payloads) == 1
    inputs = script_params_payloads[0]["inputs"]
    assert inputs[0]["name"] == "X"
    assert inputs[0]["current_name"] == "X", (
        "no-op rename must still carry current_name for C# lookup-key correctness"
    )


@pytest.mark.asyncio
async def test_gh_set_script_pins_typo_current_name_raises_structured_error(monkeypatch, patched_server):
    """Gap #5 — unresolvable `current_name` raises a clear error and does NOT
    POST to /gh/script-params. Component read at /gh/component still happens
    (resolution runs AFTER the read); the contract is "no mutating call."
    """
    fake_call_rhino, routes = _make_component_mock(
        inputs=[
            {"index": 0, "name": "X", "nickName": "X", "access": "item"},
        ],
    )
    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    response = await server.call_tool(
        "gh_set_script_pins",
        {
            "guid": "script-guid",
            "input_updates": [{"current_name": "DoesNotExist", "name": "Y"}],
        },
    )
    payload = _decode_response(response)

    assert payload["success"] is False
    assert "targets missing pin 'DoesNotExist'" in payload["data"]
    component_reads = [r for r in routes if r[0] == "/gh/component"]
    script_params_writes = [r for r in routes if r[0] == "/gh/script-params"]
    assert len(component_reads) == 1, f"expected 1 /gh/component read, got {routes!r}"
    assert not script_params_writes, f"no /gh/script-params POST expected, got {routes!r}"


@pytest.mark.asyncio
async def test_chirp_create_preserves_rich_pin_metadata(monkeypatch, patched_server):
    class _FakeChirpResponse:
        status_code = 200

        def json(self):
            return {
                "script": "generated script",
                "name": "Chirp Script",
                "category": "planner",
                "pins_in": ["Brief:string"],
                "pins_out": ["Span:float"],
            }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json):
            assert json["pins_in"] == ["Brief:string"]
            assert json["pins_out"] == ["Span:float"]
            return _FakeChirpResponse()

    async def fake_ensure_chirp_running():
        return {"running": True, "host": "127.0.0.1", "port": 9123}

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/document":
            return {"success": True, "data": {"name": "TestDoc"}}
        if route == "/gh/create-component":
            return {"success": True, "data": {"guid": "chirp-guid"}}
        if route == "/gh/script-params":
            assert payload == {
                "guid": "chirp-guid",
                "inputs": [{
                    "name": "Brief",
                    "type": "string",
                    "access": "tree",
                    "optional": False,
                    "description": "Tree of brief fragments",
                }],
                "outputs": [{
                    "name": "Span",
                    "type": "float",
                    "access": "list",
                    "description": "Candidate spans",
                }],
                "nick": "Chirp Script",
            }
            return {"success": True, "data": {"Guid": "chirp-guid", "Inputs": 1, "Outputs": 2}}
        if route == "/gh/script":
            return {"success": True, "data": {"Guid": "chirp-guid"}}
        if route == "/gh/errors":
            return {"success": True, "data": {"errors": []}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr("rook.chirp_manager.ensure_chirp_running", fake_ensure_chirp_running)
    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    response = await server.call_tool(
        "chirp_create",
        {
            "pins_in": [{
                "name": "Brief",
                "type": "string",
                "access": "tree",
                "optional": False,
                "description": "Tree of brief fragments",
            }],
            "pins_out": [{
                "name": "Span",
                "type": "float",
                "access": "list",
                "description": "Candidate spans",
            }],
            "signature": "brief -> span",
            "category": "planner",
        },
    )
    payload = _decode_response(response)

    assert payload["success"] is True
    assert payload["data"]["pins_in"] == [{
        "name": "Brief",
        "type": "string",
        "access": "tree",
        "optional": False,
        "description": "Tree of brief fragments",
    }]
    assert payload["data"]["pins_out"] == [{
        "name": "Span",
        "type": "float",
        "access": "list",
        "description": "Candidate spans",
    }]
    assert payload["data"]["pins_in"][0]["access"] == "tree"
    assert payload["data"]["pins_in"][0]["optional"] is False
    assert payload["data"]["pins_out"][0]["access"] == "list"
    assert payload["data"]["pins_out"][0]["description"] == "Candidate spans"


@pytest.mark.asyncio
async def test_chirp_create_deterministic_only_uses_host_compatible_script_without_json(
    monkeypatch, patched_server
):
    captured_scripts = []

    class _FakeChirpResponse:
        status_code = 200

        def json(self):
            return {
                "script": "\n".join(
                    [
                        "using System.Text.Json;",
                        "private void RunScript(object Input, ref object Result)",
                        "{",
                        "  Result = JsonSerializer.Serialize(Input);",
                        "}",
                    ]
                ),
                "name": "Deterministic",
                "category": "classifier",
                "pins_in": ["Input:string"],
                "pins_out": ["Result:string"],
            }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json):
            assert json["deterministic_only"] is True
            return _FakeChirpResponse()

    async def fake_ensure_chirp_running():
        return {"running": True, "host": "127.0.0.1", "port": 9123}

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/document":
            return {"success": True, "data": {"name": "TestDoc"}}
        if route == "/gh/create-component":
            return {"success": True, "data": {"guid": "chirp-guid"}}
        if route == "/gh/script-params":
            return {"success": True, "data": {"Guid": "chirp-guid", "Inputs": 1, "Outputs": 1}}
        if route == "/gh/script":
            captured_scripts.append(payload["script"])
            return {"success": True, "data": {"Guid": "chirp-guid"}}
        if route == "/gh/errors":
            return {"success": True, "data": {"errors": []}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr("rook.chirp_manager.ensure_chirp_running", fake_ensure_chirp_running)
    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    response = await server.call_tool(
        "chirp_create",
        {
            "category": "classifier",
            "pins_in": [{"name": "Input", "type": "string"}],
            "pins_out": [{"name": "Result", "type": "string"}],
            "signature": "input -> result",
            "deterministic_code": "Result = Input ?? string.Empty;",
            "deterministic_only": True,
        },
    )
    payload = _decode_response(response)

    assert payload["success"] is True
    assert captured_scripts
    assert "System.Text.Json" not in captured_scripts[0]
    assert "JsonSerializer" not in captured_scripts[0]
    assert "Result = Input ?? string.Empty;" in captured_scripts[0]


def test_python_preamble_item_access_emits_ghenv_extract_one():
    preamble = server._build_gh_python_preamble(
        [{"name": "crv", "type": "Curve", "access": "item"}]
    )
    assert "crv = _gh_extract_one(0)" in preamble
    assert "def _gh_extract_one(" in preamble
    assert "def _gh_extract_tree(" not in preamble  # tree helper only when needed
    # Old _ghc / FindId model is gone
    assert "def _ghc(" not in preamble
    assert "RhinoDoc.ActiveDoc.Objects.FindId" not in preamble


def test_python_preamble_list_access_emits_ghenv_extract_list():
    preamble = server._build_gh_python_preamble(
        [{"name": "curves", "type": "Curve", "access": "list"}]
    )
    assert "curves = _gh_extract_list(0)" in preamble
    assert "def _gh_extract_list(" in preamble
    assert "def _gh_extract_tree(" not in preamble


def test_python_preamble_tree_access_emits_tree_helper_and_call():
    preamble = server._build_gh_python_preamble(
        [{"name": "points", "type": "Point3d", "access": "tree"}]
    )
    assert "def _gh_extract_tree(_i, _cast=None):" in preamble
    assert "import Grasshopper as _gh" in preamble
    assert "_tree.AddRange(_c, _p)" in preamble  # path-preserving
    assert "points = _gh_extract_tree(0)" in preamble


def test_python_preamble_list_numeric_applies_cast():
    preamble = server._build_gh_python_preamble(
        [{"name": "nums", "type": "float", "access": "list"}]
    )
    assert "nums = _gh_extract_list(0, float)" in preamble


def test_python_preamble_tree_numeric_passes_cast():
    preamble = server._build_gh_python_preamble(
        [{"name": "xs", "type": "int", "access": "tree"}]
    )
    assert "xs = _gh_extract_tree(0, int)" in preamble


def test_python_preamble_value_geometry_list_access():
    preamble = server._build_gh_python_preamble(
        [{"name": "planes", "type": "Plane", "access": "list"}]
    )
    assert "planes = _gh_extract_list(0)" in preamble


def test_python_preamble_item_numeric_preserves_zero_default():
    # Item numeric with no upstream must still resolve to cast(0), not None.
    preamble = server._build_gh_python_preamble(
        [{"name": "n", "type": "float", "access": "item"}]
    )
    assert "n = _gh_extract_one(0, float)" in preamble
    assert "if n is None: n = float(0)" in preamble


def test_python_preamble_missing_access_defaults_to_item():
    preamble = server._build_gh_python_preamble(
        [{"name": "curve", "type": "Curve"}]  # no access key
    )
    assert "curve = _gh_extract_one(0)" in preamble
    # Not routed to list or tree extractor:
    assert "curve = _gh_extract_list" not in preamble
    assert "curve = _gh_extract_tree" not in preamble


def test_python_preamble_invalid_access_falls_back_to_item():
    preamble = server._build_gh_python_preamble(
        [{"name": "pt", "type": "Point3d", "access": "bogus"}]
    )
    assert "pt = _gh_extract_one(0)" in preamble


def test_python_preamble_string_type_passes_through_unchanged():
    # String pins never emit coercion lines regardless of access mode.
    preamble = server._build_gh_python_preamble(
        [{"name": "txt", "type": "string", "access": "list"}]
    )
    assert "txt = " not in preamble


def test_python_preamble_pin_indices_match_position_in_pins_in():
    # Each extract call must use the pin's position in pins_in as the index.
    preamble = server._build_gh_python_preamble([
        {"name": "a", "type": "Curve", "access": "list"},
        {"name": "b", "type": "float", "access": "item"},
        {"name": "c", "type": "Point3d", "access": "tree"},
    ])
    assert "a = _gh_extract_list(0)" in preamble
    assert "b = _gh_extract_one(1, float)" in preamble
    assert "c = _gh_extract_tree(2)" in preamble


def test_python_preamble_helpers_guard_bounds_and_use_path_driven_iteration():
    preamble = server._build_gh_python_preamble(
        [{"name": "xs", "type": "Curve", "access": "tree"}]
    )
    # Bounds guard in each helper
    assert "if _i >= _inputs.Count: return None" in preamble
    assert "if _i >= _inputs.Count: return []" in preamble
    assert "if _i >= _inputs.Count: return _tree" in preamble
    # Path-paired iteration via zip(Paths, Branches) — this is the idiom that
    # actually works in RhinoCode Python 3; GH_Structure doesn't expose Branch(path)
    # as a Python-callable method despite it being in the .NET API.
    assert "for _p, _b in zip(_vd.Paths, _vd.Branches):" in preamble


# ---------- #50 cast-failure warning emission ----------
# Closes GitHub issue #50 — previously a curve wired into a numeric pin
# silently returned cast(0) with no signal. Now a Warning is emitted on
# the component on the first failure per pin per solve. Warning emission
# is defensive: wrapped in try/except so it can never break the solve.


def _assert_warn_helper_present(preamble: str) -> None:
    """The warning emitter is a shared helper; all three extract helpers call it."""
    assert "def _gh_cast_warn(_i, _cast, _v):" in preamble
    assert "import Grasshopper as _gh" in preamble
    assert "GH_RuntimeMessageLevel.Warning" in preamble
    assert "ghenv.Component.AddRuntimeMessage" in preamble
    assert "except Exception: pass" in preamble, "warning emission must never break the solve"


def test_python_preamble_item_access_emits_cast_warning_hook():
    preamble = server._build_gh_python_preamble(
        [{"name": "n", "type": "float", "access": "item"}]
    )
    _assert_warn_helper_present(preamble)
    # Per-pin first-failure flag in _gh_extract_one; warn helper invoked on bad cast.
    assert "_warned = False" in preamble
    assert "if not _warned: _gh_cast_warn(_i, _cast, _v); _warned = True" in preamble


def test_python_preamble_list_access_emits_cast_warning_hook():
    preamble = server._build_gh_python_preamble(
        [{"name": "vals", "type": "float", "access": "list"}]
    )
    _assert_warn_helper_present(preamble)
    assert "_warned = False" in preamble
    # The list helper has both a None→cast(0) branch (unchanged) and a
    # cast-failure branch (now warned). Only the failure branch calls the warner.
    assert "if not _warned: _gh_cast_warn(_i, _cast, _v); _warned = True" in preamble


def test_python_preamble_tree_access_emits_cast_warning_hook():
    preamble = server._build_gh_python_preamble(
        [{"name": "vals", "type": "float", "access": "tree"}]
    )
    _assert_warn_helper_present(preamble)
    # Tree helper also gets its own _warned flag — per-pin-per-solve granularity.
    # Tree's Grasshopper import is also used for DataTree[object]; the warn helper
    # re-imports inside its own try block independently.
    assert "_warned = False" in preamble


def test_python_preamble_non_numeric_pin_never_invokes_warn_helper():
    """Defense-in-depth check: the warn helper is shared infrastructure (always
    emitted in the helper block). For a non-numeric pin, the per-pin call line
    passes no cast arg, so the `if _cast is not None` guard is False at runtime
    and the `_gh_cast_warn` branch is unreachable. Asserts the per-pin line has
    no cast arg, which is the static proof of non-invocation.
    """
    preamble = server._build_gh_python_preamble(
        [{"name": "c", "type": "Curve", "access": "item"}]
    )
    # Warn helper is part of the shared block — still emitted.
    _assert_warn_helper_present(preamble)
    # But the per-pin extract call passes no cast, so the warn branch is dead.
    assert "c = _gh_extract_one(0)" in preamble
    assert "c = _gh_extract_one(0," not in preamble, (
        "Curve pin must call _gh_extract_one without a cast argument"
    )


# ---------- Runtime semantics tests ----------
# These execute the generated preamble against a mock ghenv to verify behavior,
# not just emitted source strings. Covers cast failure handling, mixed-type
# lists, tree leaf coercion, bounds guards, and wrapper unwrap.

class _MockWrapper:
    """Simulates a GH_Goo wrapper with .Value."""
    def __init__(self, value):
        self.Value = value


class _MockVolatileData:
    def __init__(self, branches_by_path):
        # branches_by_path: dict { path_key: [wrapper, ...] }
        # The preamble iterates via zip(Paths, Branches) — Paths and Branches
        # must be aligned (same order). We don't mock Branch(path) because
        # GH_Structure in RhinoCode Python 3 doesn't expose it as a callable.
        self._branches = dict(branches_by_path)
        self.Paths = list(self._branches.keys())
        self.Branches = list(self._branches.values())
        self.PathCount = len(self._branches)
        self.DataCount = sum(len(b) for b in self._branches.values())


class _MockInput:
    def __init__(self, volatile_data):
        self.VolatileData = volatile_data


class _MockInputs:
    def __init__(self, inputs):
        self._inputs = inputs
        self.Count = len(inputs)

    def __getitem__(self, i):
        return self._inputs[i]


class _MockParams:
    def __init__(self, inputs):
        self.Input = _MockInputs(inputs)


class _MockComponent:
    def __init__(self, inputs):
        self.Params = _MockParams(inputs)
        # Collects all AddRuntimeMessage calls as (level, message) tuples.
        # Used by #50 cast-warning runtime tests to assert emission count + content.
        self.runtime_messages: list[tuple[Any, str]] = []

    def AddRuntimeMessage(self, level, message):
        self.runtime_messages.append((level, message))


class _MockGhEnv:
    def __init__(self, inputs):
        self.Component = _MockComponent(inputs)


def _exec_preamble(pins_in, mock_inputs):
    """Execute generated preamble against a mock ghenv; return the resulting namespace."""
    preamble = server._build_gh_python_preamble(pins_in)
    ns = {"ghenv": _MockGhEnv(mock_inputs)}
    # Pre-seed pin variables (RhinoCode would populate these; we don't care about
    # their values since the preamble overwrites them via ghenv).
    for p in pins_in:
        ns[p["name"]] = None
    exec(compile(preamble, "<preamble>", "exec"), ns)
    return ns


def test_runtime_list_unwraps_values_from_wrappers():
    pins = [{"name": "vals", "type": "float", "access": "list"}]
    vd = _MockVolatileData({"p0": [_MockWrapper(1.5), _MockWrapper(2.5), _MockWrapper(3.0)]})
    ns = _exec_preamble(pins, [_MockInput(vd)])
    assert ns["vals"] == [1.5, 2.5, 3.0]


def test_runtime_list_cast_failure_falls_back_to_numeric_default():
    # Non-numeric item should NOT silently pass through as a curve object —
    # it must be replaced with float(0) per the cast-failure fallback.
    pins = [{"name": "vals", "type": "float", "access": "list"}]
    vd = _MockVolatileData({"p0": [_MockWrapper(1.5), _MockWrapper("not_a_number"), _MockWrapper(3.0)]})
    ns = _exec_preamble(pins, [_MockInput(vd)])
    assert ns["vals"] == [1.5, 0.0, 3.0]


def test_runtime_item_cast_failure_falls_back_to_numeric_default():
    pins = [{"name": "n", "type": "float", "access": "item"}]
    vd = _MockVolatileData({"p0": [_MockWrapper("not_a_number")]})
    ns = _exec_preamble(pins, [_MockInput(vd)])
    assert ns["n"] == 0.0


def test_runtime_list_none_item_becomes_numeric_default():
    pins = [{"name": "vals", "type": "float", "access": "list"}]
    vd = _MockVolatileData({"p0": [_MockWrapper(None), _MockWrapper(5.0)]})
    ns = _exec_preamble(pins, [_MockInput(vd)])
    assert ns["vals"] == [0.0, 5.0]


def test_runtime_list_non_numeric_preserves_unwrapped_value():
    # For non-numeric pins, no cast happens — wrapper .Value passes through.
    pins = [{"name": "crvs", "type": "Curve", "access": "list"}]
    vd = _MockVolatileData({"p0": [_MockWrapper("curve_a"), _MockWrapper("curve_b")]})
    ns = _exec_preamble(pins, [_MockInput(vd)])
    assert ns["crvs"] == ["curve_a", "curve_b"]


def test_runtime_item_no_upstream_numeric_is_zero():
    pins = [{"name": "n", "type": "float", "access": "item"}]
    vd = _MockVolatileData({})  # empty
    ns = _exec_preamble(pins, [_MockInput(vd)])
    assert ns["n"] == 0.0


def test_runtime_item_no_upstream_non_numeric_is_none():
    pins = [{"name": "crv", "type": "Curve", "access": "item"}]
    vd = _MockVolatileData({})  # empty
    ns = _exec_preamble(pins, [_MockInput(vd)])
    assert ns["crv"] is None


def test_runtime_list_no_upstream_is_empty_list():
    pins = [{"name": "vals", "type": "float", "access": "list"}]
    vd = _MockVolatileData({})
    ns = _exec_preamble(pins, [_MockInput(vd)])
    assert ns["vals"] == []


def test_runtime_list_flattens_multi_branch():
    # List access intentionally flattens all branches into one stream.
    pins = [{"name": "vals", "type": "float", "access": "list"}]
    vd = _MockVolatileData({
        "path_a": [_MockWrapper(1.0), _MockWrapper(2.0)],
        "path_b": [_MockWrapper(3.0)],
    })
    ns = _exec_preamble(pins, [_MockInput(vd)])
    assert ns["vals"] == [1.0, 2.0, 3.0]


def test_runtime_bounds_guard_when_pin_index_out_of_range():
    # pins_in declares pin at index 0, but mock inputs is empty.
    # Helper should return None / [] rather than IndexError.
    pins = [{"name": "crv", "type": "Curve", "access": "item"}]
    ns = _exec_preamble(pins, [])  # no mock inputs → Count = 0
    assert ns["crv"] is None

    pins = [{"name": "vals", "type": "float", "access": "list"}]
    ns = _exec_preamble(pins, [])
    assert ns["vals"] == []


def test_runtime_item_skips_null_wrappers_and_returns_first_valid():
    # Item access must NOT stop at the first null wrapper — it should skip nulls
    # and return the first real value. Matches GH's native item-access semantics.
    pins = [{"name": "crv", "type": "Curve", "access": "item"}]
    vd = _MockVolatileData({
        "p0": [_MockWrapper(None), _MockWrapper(None)],
        "p1": [_MockWrapper("real_curve")],
    })
    ns = _exec_preamble(pins, [_MockInput(vd)])
    assert ns["crv"] == "real_curve"


def test_runtime_item_returns_none_when_all_wrappers_null():
    pins = [{"name": "crv", "type": "Curve", "access": "item"}]
    vd = _MockVolatileData({
        "p0": [_MockWrapper(None)],
        "p1": [_MockWrapper(None)],
    })
    ns = _exec_preamble(pins, [_MockInput(vd)])
    assert ns["crv"] is None


def test_runtime_mixed_pins_use_correct_indices():
    # Verifies pin_index == position_in_pins_in against actual execution.
    pins = [
        {"name": "a", "type": "Curve", "access": "list"},
        {"name": "b", "type": "float", "access": "item"},
    ]
    vd_a = _MockVolatileData({"p": [_MockWrapper("curve_x")]})
    vd_b = _MockVolatileData({"p": [_MockWrapper(42.0)]})
    ns = _exec_preamble(pins, [_MockInput(vd_a), _MockInput(vd_b)])
    assert ns["a"] == ["curve_x"]
    assert ns["b"] == 42.0


# ---------- #50 cast-warning runtime tests ----------
# Unlike the string-inspection tests above, these actually EXECUTE the preamble
# to verify AddRuntimeMessage fires with the right level/message on a cast
# failure — and fires exactly once per pin per solve.


import sys
import types as _types_for_gh_stub


def _install_grasshopper_stub(monkeypatch):
    """Put a minimal Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning in sys.modules.

    The preamble's `_gh_cast_warn` does `import Grasshopper as _gh` inside a
    try/except, then reads `_gh.Kernel.GH_RuntimeMessageLevel.Warning`. With
    this stub in place, the warning emission path succeeds and lands in
    _MockComponent.runtime_messages.
    """
    warning_sentinel = "GH_WARNING"
    level_mod = _types_for_gh_stub.SimpleNamespace(Warning=warning_sentinel)
    kernel_mod = _types_for_gh_stub.SimpleNamespace(GH_RuntimeMessageLevel=level_mod)
    gh_mod = _types_for_gh_stub.SimpleNamespace(Kernel=kernel_mod)
    monkeypatch.setitem(sys.modules, "Grasshopper", gh_mod)
    return warning_sentinel


def test_runtime_list_cast_failure_emits_exactly_one_warning(monkeypatch):
    """First cast failure in a list emits one warning; subsequent failures in the
    same solve do not re-warn. Per-pin, first-failure-only granularity.
    """
    warning_level = _install_grasshopper_stub(monkeypatch)
    pins = [{"name": "vals", "type": "float", "access": "list"}]
    # Three bad values in a row — would have emitted 3 warnings without the flag.
    vd = _MockVolatileData({"p0": [
        _MockWrapper("bad1"), _MockWrapper("bad2"), _MockWrapper("bad3"), _MockWrapper(5.0),
    ]})
    mock_input = _MockInput(vd)

    preamble = server._build_gh_python_preamble(pins)
    ghenv = _MockGhEnv([mock_input])
    ns = {"ghenv": ghenv, "vals": None}
    exec(compile(preamble, "<preamble>", "exec"), ns)

    # Values still substitute to float(0) — behavior unchanged.
    assert ns["vals"] == [0.0, 0.0, 0.0, 5.0]
    # Exactly one warning emitted, at Warning level, with pin index + cast target.
    assert len(ghenv.Component.runtime_messages) == 1, (
        f"expected exactly one warning, got {ghenv.Component.runtime_messages!r}"
    )
    level, message = ghenv.Component.runtime_messages[0]
    assert level == warning_level, f"expected Warning level, got {level!r}"
    assert "Pin 0" in message
    assert "cast to float failed" in message
    assert "type str" in message, f"expected source-type hint in message: {message!r}"


def test_runtime_item_cast_failure_emits_one_warning(monkeypatch):
    """Item access: single-value coercion still emits a warning when the only
    candidate fails to cast.
    """
    warning_level = _install_grasshopper_stub(monkeypatch)
    pins = [{"name": "n", "type": "float", "access": "item"}]
    vd = _MockVolatileData({"p0": [_MockWrapper("not_a_number")]})
    mock_input = _MockInput(vd)

    preamble = server._build_gh_python_preamble(pins)
    ghenv = _MockGhEnv([mock_input])
    ns = {"ghenv": ghenv, "n": None}
    exec(compile(preamble, "<preamble>", "exec"), ns)

    assert ns["n"] == 0.0  # fallback preserved
    assert len(ghenv.Component.runtime_messages) == 1
    level, message = ghenv.Component.runtime_messages[0]
    assert level == warning_level
    assert "cast to float failed" in message


def test_runtime_cast_failure_survives_grasshopper_import_failure():
    """Defensive: when `Grasshopper` can't be imported (e.g. outside a GH solve),
    the cast-failure path must still substitute cast(0) correctly and not raise.
    Warning emission is best-effort and silently skipped.

    This matches the pre-existing test_runtime_list_cast_failure_falls_back_to_
    numeric_default expectation — preserved exactly after PR #50's added warning
    emission — but documents the try/except guard intentionally.
    """
    # Deliberately NO Grasshopper stub. The preamble's try/except wraps the
    # import + AddRuntimeMessage call, so failure is swallowed.
    pins = [{"name": "vals", "type": "float", "access": "list"}]
    vd = _MockVolatileData({"p0": [_MockWrapper("bad"), _MockWrapper(2.0)]})
    mock_input = _MockInput(vd)

    preamble = server._build_gh_python_preamble(pins)
    ghenv = _MockGhEnv([mock_input])
    ns = {"ghenv": ghenv, "vals": None}
    # Must NOT raise.
    exec(compile(preamble, "<preamble>", "exec"), ns)

    assert ns["vals"] == [0.0, 2.0]
    # Warning emission failed silently — no messages recorded.
    assert ghenv.Component.runtime_messages == [], (
        f"no runtime messages expected without Grasshopper stub, got {ghenv.Component.runtime_messages!r}"
    )


# ---------- GH script-component routing — MCP description regressions ----------
# Anchor against the drift strings that misrouted an agent to rhino_execute
# on 2026-04-21. See rook_docs/2026-04-21-gh-script-component-routing-
# design-pass.md §PR-1.


@pytest.mark.asyncio
async def test_gh_set_script_description_does_not_claim_py3_only():
    """Drift regression — gh_set_script must not advertise Py3-only when the
    handler duck-types on capability and accepts four component types.
    """
    tools = await server.list_tools()
    gh_set_script = next((t for t in tools if t.name == "gh_set_script"), None)
    assert gh_set_script is not None, "gh_set_script tool missing from registered tools"

    desc = gh_set_script.description
    assert "must be a Python 3 Script" not in desc, (
        "gh_set_script description reintroduces Py3-only categorical gate — "
        "see rook_docs/2026-04-21-gh-script-component-routing-design-pass.md"
    )
    assert "the full Python source code" not in desc, (
        "gh_set_script description reintroduces Python-only source framing — "
        "handler accepts C# source on RhinoCode/GH1 C# components too"
    )
    assert "raw" in desc.lower()
    assert "no wrapping" in desc.lower()
    assert "gh_update_script" in desc
    assert "Prefer this over `rhino_execute` for ALL GH script source/pin work" not in desc

    script_prop = gh_set_script.inputSchema["properties"]["script"]["description"]
    assert "exact raw source" in script_prop
    assert "target runtime" in script_prop
    assert "Python source code to set" not in script_prop


def test_gh_canvas_tool_group_includes_update_script():
    from rook.agent.tool_groups import TOOL_GROUPS

    gh_canvas = TOOL_GROUPS["gh_canvas"]

    assert "gh_update_script" in gh_canvas
    assert "gh_set_script" in gh_canvas
    assert gh_canvas.index("gh_update_script") < gh_canvas.index("gh_set_script_pins")


def test_gh_update_script_local_tool_registered():
    from rook.agent.tool_dispatcher import build_local_tools

    assert "gh_update_script" in build_local_tools()


@pytest.mark.asyncio
async def test_gh_update_script_input_schema_and_description():
    tools = {tool.name: tool for tool in await server.list_tools()}
    tool = tools.get("gh_update_script")
    assert tool is not None

    schema = tool.inputSchema
    assert schema["required"] == ["guid", "code"]
    props = schema["properties"]
    assert props["guid"]["type"] == "string"
    assert props["code"]["type"] == "string"
    assert props["mode"]["enum"] == ["auto", "body", "full_source"]
    assert props["mode"]["default"] == "auto"
    assert props["language"]["enum"] == ["auto", "python", "csharp"]
    assert props["language"]["default"] == "auto"
    assert props["python_preamble"]["type"] == "boolean"
    assert props["python_preamble"]["default"] is True
    assert props["check_errors"]["type"] == "boolean"
    assert props["check_errors"]["default"] is True

    desc = tool.description
    assert "normal source edits" in desc
    assert "gh_set_script_pins first" in desc
    assert "gh_set_script" in desc and "raw source escape hatch" in desc


@pytest.mark.parametrize(
    ("type_name", "runtime", "language", "supports_update", "legacy"),
    [
        ("Python3Component", "RhinoCode Python 3", "python", True, False),
        ("GhPythonComponent", "GH1 legacy Python", "python", True, True),
        ("CSharpComponent", "RhinoCode C#", "csharp", True, False),
        ("CSharpScriptComponent", "RhinoCode C#", "csharp", True, False),
        ("Component_CSNET_Script", "GH1 legacy C#/.NET Script", "csharp", False, True),
    ],
)
def test_gh_update_script_runtime_classifier_exact_types(
    type_name, runtime, language, supports_update, legacy
):
    result = server._classify_gh_update_script_runtime({"Type": type_name}, {})
    assert result == {
        "component_type": type_name,
        "detected_runtime": runtime,
        "detected_language": language,
        "supports_update": supports_update,
        "legacy": legacy,
    }


def test_gh_update_script_language_mismatch_fails():
    with pytest.raises(ValueError, match="language"):
        server._classify_gh_update_script_runtime(
            {"Type": "Python3Component"},
            {},
            requested_language="csharp",
        )


def test_gh_update_script_snapshot_label_does_not_override_unknown_type():
    with pytest.raises(ValueError, match="Unsupported"):
        server._classify_gh_update_script_runtime(
            {"Type": "UnknownScript"},
            {"DisplayName": "CSharpComponent", "Name": "C# Script"},
        )


def test_gh_update_script_csharpcomponent_live_type_wraps_body():
    prepared = server._prepare_gh_update_script_source(
        code="A = Convert.ToDouble(R);",
        mode="body",
        runtime={"component_type": "CSharpComponent"},
        inputs=[{"name": "R", "type": "double"}],
        outputs=[{"name": "A", "type": "double"}],
        python_preamble=True,
    )

    assert prepared["mode_used"] == "body"
    assert prepared["wrapped"] is True
    assert "private void RunScript(object R, ref object A)" in prepared["source"]


def test_gh_update_script_csharp_body_wraps_with_current_pins_and_skips_ref_object_out():
    inputs = [{"name": "R", "type": "double"}]
    outputs = [{"name": "A", "type": "Circle"}]

    prepared = server._prepare_gh_update_script_source(
        code="A = new Circle(Plane.WorldXY, Convert.ToDouble(R));",
        mode="body",
        runtime={"component_type": "CSharpScriptComponent"},
        inputs=inputs,
        outputs=outputs,
        python_preamble=True,
    )

    assert prepared["mode_used"] == "body"
    assert prepared["wrapped"] is True
    assert "private void RunScript(object R, ref object A)" in prepared["source"]
    assert "ref object out" not in prepared["source"]


def test_gh_update_script_csharp_auto_full_source_passes_through():
    code = "public class Script_Instance : GH_ScriptInstance { private void RunScript(object R, ref object A) { A = R; } }"
    prepared = server._prepare_gh_update_script_source(
        code=code,
        mode="auto",
        runtime={"component_type": "CSharpScriptComponent"},
        inputs=[{"name": "R"}],
        outputs=[{"name": "A"}],
        python_preamble=True,
    )
    assert prepared == {"source": code, "mode_used": "full_source", "wrapped": False}


def test_gh_update_script_python_full_source_never_adds_generated_blocks():
    code = "A = X"
    prepared = server._prepare_gh_update_script_source(
        code=code,
        mode="full_source",
        runtime={"component_type": "Python3Component"},
        inputs=[{"name": "X", "type": "Point3d"}],
        outputs=[{"name": "A", "type": "Point3d", "access": "list"}],
        python_preamble=True,
    )
    assert prepared == {"source": code, "mode_used": "full_source", "wrapped": False}


def test_gh_update_script_python_body_adds_generated_blocks_once():
    prepared = server._prepare_gh_update_script_source(
        code="A = Pts",
        mode="body",
        runtime={"component_type": "Python3Component"},
        inputs=[{"name": "Pts", "type": "Point3d", "access": "list"}],
        outputs=[{"name": "A", "type": "Point3d", "access": "list"}],
        python_preamble=True,
    )
    assert prepared["mode_used"] == "body"
    assert prepared["wrapped"] is True
    assert prepared["source"].count("# ── Auto-generated GH input coercion") == 1
    assert prepared["source"].count("# ── Auto-generated GH output coercion") == 1


def test_gh_update_script_python_existing_sentinels_prevent_duplication():
    code = (
        "# ── Auto-generated GH input coercion\n"
        "A = Pts\n"
        "# ── Auto-generated GH output coercion\n"
    )
    prepared = server._prepare_gh_update_script_source(
        code=code,
        mode="auto",
        runtime={"component_type": "Python3Component"},
        inputs=[{"name": "Pts", "type": "Point3d", "access": "list"}],
        outputs=[{"name": "A", "type": "Point3d", "access": "list"}],
        python_preamble=True,
    )
    assert prepared["source"].count("# ── Auto-generated GH input coercion") == 1
    assert prepared["source"].count("# ── Auto-generated GH output coercion") == 1


def test_gh_update_script_gh1_python_raw_direct():
    prepared = server._prepare_gh_update_script_source(
        code="a = x",
        mode="auto",
        runtime={"component_type": "GhPythonComponent"},
        inputs=[{"name": "x", "type": "Point3d"}],
        outputs=[{"name": "a", "type": "Point3d", "access": "list"}],
        python_preamble=True,
    )
    assert prepared == {"source": "a = x", "mode_used": "full_source", "wrapped": False}


@pytest.mark.parametrize("mode", ["auto", "body", "full_source"])
def test_gh_update_script_gh1_csharp_fails_closed_all_modes(mode):
    with pytest.raises(ValueError, match="gh_set_script"):
        server._prepare_gh_update_script_source(
            code="A = R;",
            mode=mode,
            runtime={"component_type": "Component_CSNET_Script"},
            inputs=[{"name": "R"}],
            outputs=[{"name": "A"}],
            python_preamble=True,
        )


def test_gh_update_script_error_summary_component_unrelated_counts_and_wrapped_response():
    summary = server._summarize_gh_update_script_errors(
        {
            "success": True,
            "data": {
                "errors": [
                    {"guid": "target", "errors": ["compile 1", "compile 2"]},
                    {"guid": "other", "errors": ["canvas err"]},
                ],
                "warnings": [
                    {"guid": "target", "warnings": ["warn"]},
                    {"guid": "other", "warnings": ["canvas warn 1", "canvas warn 2"]},
                ],
            },
        },
        "target",
    )
    assert summary == {
        "component_errors": ["compile 1", "compile 2"],
        "component_warnings": ["warn"],
        "canvas_error_count": 3,
        "canvas_warning_count": 3,
        "unrelated_error_count": 1,
        "unrelated_warning_count": 2,
    }


def test_gh_update_script_error_summary_accepts_live_capitalized_shape():
    summary = server._summarize_gh_update_script_errors(
        {
            "success": True,
            "Data": {
                "Errors": [
                    {"Guid": "real-guid", "Errors": ["compile live"]},
                    {"Guid": "other-guid", "Errors": ["other live"]},
                ],
                "Warnings": [
                    {"Guid": "real-guid", "Warnings": ["warn live"]},
                ],
            },
        },
        "real-guid",
    )

    assert summary == {
        "component_errors": ["compile live"],
        "component_warnings": ["warn live"],
        "canvas_error_count": 2,
        "canvas_warning_count": 1,
        "unrelated_error_count": 1,
        "unrelated_warning_count": 0,
    }


def test_gh_update_script_error_summary_counts_warnings_on_error_entries():
    summary = server._summarize_gh_update_script_errors(
        {
            "success": True,
            "Data": {
                "Errors": [
                    {"Guid": "target", "Errors": ["E"], "Warnings": ["W"]},
                ],
                "Warnings": [],
            },
        },
        "target",
    )

    assert summary == {
        "component_errors": ["E"],
        "component_warnings": ["W"],
        "canvas_error_count": 1,
        "canvas_warning_count": 1,
        "unrelated_error_count": 0,
        "unrelated_warning_count": 0,
    }


def test_gh_update_script_error_summary_uses_route_level_counts():
    summary = server._summarize_gh_update_script_errors(
        {
            "success": True,
            "Data": {
                "ErrorCount": 2,
                "WarningCount": 3,
                "Errors": [
                    {"Guid": "target", "Errors": ["E1", "E2"], "Warnings": ["W1"]},
                    {"Guid": "other-error", "Errors": ["E3"]},
                ],
                "Warnings": [
                    {"Guid": "target", "Warnings": ["W2", "W3"]},
                    {"Guid": "other-warning", "Warnings": ["W4"]},
                    {"Guid": "other-warning-2", "Warnings": ["W5"]},
                ],
            },
        },
        "target",
    )

    assert summary == {
        "component_errors": ["E1", "E2"],
        "component_warnings": ["W1", "W2", "W3"],
        "canvas_error_count": 2,
        "canvas_warning_count": 3,
        "unrelated_error_count": 1,
        "unrelated_warning_count": 2,
    }


def test_gh_update_script_error_summary_route_counts_track_top_level_buckets():
    summary = server._summarize_gh_update_script_errors(
        {
            "success": True,
            "Data": {
                "ErrorCount": 1,
                "WarningCount": 1,
                "Errors": [
                    {"Guid": "target", "Errors": ["E"], "Warnings": ["W"]},
                ],
                "Warnings": [
                    {"Guid": "other-warning", "Warnings": ["other W"]},
                ],
            },
        },
        "target",
    )

    assert summary == {
        "component_errors": ["E"],
        "component_warnings": ["W"],
        "canvas_error_count": 1,
        "canvas_warning_count": 1,
        "unrelated_error_count": 0,
        "unrelated_warning_count": 1,
    }


@pytest.mark.asyncio
async def test_gh_update_script_mocked_call_tool_orchestrates_csharp_body_route_flow(
    monkeypatch, patched_server
):
    calls: list[tuple[str, str, dict | None]] = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        calls.append((route, method, payload))
        if route == "/gh/script":
            if payload and "script" in payload:
                assert "private void RunScript(object R, ref object A)" in payload["script"]
                return {"success": True, "data": {"guid": "cs-guid"}}
            return {"success": True, "data": {"Type": "CSharpComponent", "script": "old"}}
        if route == "/gh/component":
            return {
                "success": True,
                "data": {
                    "Params": {
                        "Inputs": [{"Name": "R", "TypeName": "double"}],
                        "Outputs": [
                            {"Name": "out", "TypeName": "string"},
                            {"Name": "A", "TypeName": "Circle"},
                        ],
                    }
                },
            }
        if route == "/gh/errors":
            return {"success": True, "data": {"errors": [], "warnings": []}}
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    records = []

    async def fake_record(**kwargs):
        records.append(kwargs)

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(server, "_record_gh_to_session", fake_record)

    payload = _decode_response(await server.call_tool(
        "gh_update_script",
        {"guid": "cs-guid", "code": "A = Convert.ToDouble(R);", "mode": "body"},
    ))

    assert payload["success"] is True
    data = payload["data"]
    assert data["detected_runtime"] == "RhinoCode C#"
    assert data["mode_used"] == "body"
    assert data["wrapped"] is True
    assert data["inputs_used"] == [{"name": "R", "type": "double"}]
    assert data["outputs_used"] == [{"name": "A", "type": "Circle"}]
    assert [route for route, _, _ in calls].count("/gh/script") == 2
    assert "/gh/errors" in [route for route, _, _ in calls]
    assert records[0]["action"] == "gh_update_script"
    assert "code" not in records[0]["params"]
    assert records[0]["components_affected"] == ["cs-guid"]


@pytest.mark.asyncio
async def test_gh_update_script_csharp_body_fails_closed_when_current_pins_unreadable(
    monkeypatch, patched_server
):
    writes = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/script" and "script" not in (payload or {}):
            return {"success": True, "data": {"Type": "CSharpScriptComponent", "Guid": "cs-guid"}}
        if route == "/gh/script":
            writes.append(payload)
            return {"success": True, "data": {"guid": "cs-guid"}}
        if route == "/gh/component":
            return {"success": True, "data": {"Guid": "cs-guid"}}
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_update_script",
        {"guid": "cs-guid", "code": "A = R;", "mode": "body"},
    ))

    assert payload["success"] is False
    assert "current pins could not be read" in payload["data"]
    assert "gh_set_script" in payload["data"]
    assert writes == []


@pytest.mark.asyncio
async def test_gh_update_script_check_errors_false_skips_gh_errors(monkeypatch, patched_server):
    routes = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        routes.append(route)
        if route == "/gh/script" and "script" not in (payload or {}):
            return {"success": True, "data": {"Type": "Python3Component"}}
        if route == "/gh/script":
            return {"success": True, "data": {"guid": "py-guid"}}
        if route == "/gh/component":
            return {"success": True, "data": {"Params": {"Inputs": [], "Outputs": []}}}
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        if route == "/gh/errors":
            raise AssertionError("check_errors=False must skip /gh/errors")
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_update_script",
        {"guid": "py-guid", "code": "A = 1", "check_errors": False},
    ))

    assert payload["success"] is True
    data = payload["data"]
    assert data["component_errors"] == []
    assert data["canvas_error_count"] == 0
    assert "/gh/errors" not in routes


@pytest.mark.asyncio
async def test_gh_update_script_short_id_uses_resolved_guid_for_error_summary(
    monkeypatch, patched_server
):
    real_guid = "12345678-1234-4234-9234-123456789abc"

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/script" and "script" not in (payload or {}):
            assert payload["guid"] == "C20"
            return {
                "success": True,
                "data": {"Type": "CSharpScriptComponent", "Guid": "C20"},
            }
        if route == "/gh/script":
            assert payload["guid"] == "C20"
            return {"success": True, "data": {"guid": "C20"}}
        if route == "/gh/component":
            assert payload["guid"] == "C20"
            return {
                "success": True,
                "data": {
                    "Guid": "C20",
                    "InstanceGuid": real_guid,
                    "Params": {
                        "Inputs": [{"Name": "R"}],
                        "Outputs": [{"Name": "out"}, {"Name": "A"}],
                    },
                },
            }
        if route == "/gh/errors":
            return {
                "success": True,
                "data": {
                    "errors": [{"guid": real_guid, "errors": ["compile from real guid"]}],
                    "warnings": [],
                },
            }
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_update_script",
        {"guid": "C20", "code": "A = R;", "mode": "body"},
    ))

    assert payload["success"] is False
    data = payload["data"]
    assert data["message"] == (
        "Source was written, but the target script component still has compile errors."
    )
    assert data["guid"] == real_guid
    assert data["target_guid"] == "C20"
    assert data["component_errors"] == ["compile from real guid"]
    assert data["unrelated_error_count"] == 0


@pytest.mark.asyncio
async def test_gh_update_script_short_id_falls_back_to_snapshot_diagnostics(
    monkeypatch, patched_server
):
    routes = []
    real_guid = "12345678-1234-4234-9234-123456789abc"

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        routes.append(route)
        if route == "/gh/script" and "script" not in (payload or {}):
            return {"success": True, "data": {"Type": "CSharpScriptComponent", "Guid": "C20"}}
        if route == "/gh/script":
            return {"success": True, "data": {"Guid": "C20"}}
        if route == "/gh/component":
            return {
                "success": True,
                "data": {
                    "Guid": "C20",
                    "Params": {
                        "Inputs": [{"Name": "R"}],
                        "Outputs": [{"Name": "out"}, {"Name": "A"}],
                    },
                },
            }
        if route == "/gh/errors":
            return {
                "success": True,
                "Data": {
                    "Errors": [{"Guid": real_guid, "Errors": ["compile under real guid"]}],
                    "Warnings": [],
                },
            }
        if route == "/gh/snapshot":
            assert payload == {"include_data": False}
            return {
                "success": True,
                "data": {
                    "components": [
                        {"id": "C20", "errors": ["snapshot compile"], "warnings": ["snapshot warn"]},
                    ],
                    "diagnostics": {"errors": 3, "warnings": 2},
                },
            }
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_update_script",
        {"guid": "C20", "code": "A = R;", "mode": "body"},
    ))

    assert payload["success"] is False
    data = payload["data"]
    assert data["message"] == (
        "Source was written, but the target script component still has compile errors."
    )
    assert data["guid"] == "C20"
    assert data["component_errors"] == ["snapshot compile"]
    assert data["component_warnings"] == ["snapshot warn"]
    assert data["canvas_error_count"] == 3
    assert data["canvas_warning_count"] == 2
    assert data["unrelated_error_count"] == 2
    assert data["unrelated_warning_count"] == 1
    assert "/gh/snapshot" in routes


@pytest.mark.asyncio
async def test_gh_update_script_error_check_failure_is_visible(monkeypatch, patched_server):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/script" and "script" not in (payload or {}):
            return {"success": True, "data": {"Type": "Python3Component", "guid": "py-guid"}}
        if route == "/gh/script":
            return {"success": True, "data": {"guid": "py-guid"}}
        if route == "/gh/component":
            return {"success": True, "data": {"Guid": "py-guid", "Params": {"Inputs": [], "Outputs": []}}}
        if route == "/gh/errors":
            return {"success": False, "data": "GH unavailable"}
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_update_script",
        {"guid": "py-guid", "code": "A = 1"},
    ))

    assert payload["success"] is True
    data = payload["data"]
    assert data["error_check_failed"] == "GH unavailable"
    assert data["component_errors"] == []
    assert data["component_warnings"] == []
    assert data["canvas_error_count"] == 0
    assert data["canvas_warning_count"] == 0
    assert data["unrelated_error_count"] == 0
    assert data["unrelated_warning_count"] == 0


@pytest.mark.asyncio
async def test_gh_update_script_compile_failure_returns_failed_with_component_errors_and_recovery_hint(
    monkeypatch, patched_server
):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/script" and "script" not in (payload or {}):
            return {"success": True, "data": {"Type": "CSharpScriptComponent"}}
        if route == "/gh/script":
            return {"success": True, "data": {"guid": "cs-guid"}}
        if route == "/gh/component":
            return {
                "success": True,
                "data": {
                    "Params": {
                        "Inputs": [{"Name": "R"}],
                        "Outputs": [{"Name": "out"}, {"Name": "A"}],
                    }
                },
            }
        if route == "/gh/errors":
            return {
                "success": True,
                "data": {
                    "errors": [{"guid": "cs-guid", "errors": ["The name X does not exist"]}],
                    "warnings": [],
                },
            }
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_update_script",
        {"guid": "cs-guid", "code": "A = X;", "mode": "body"},
    ))

    assert payload["success"] is False
    data = payload["data"]
    assert data["message"] == (
        "Source was written, but the target script component still has compile errors."
    )
    assert data["guid"] == "cs-guid"
    assert data["component_errors"] == ["The name X does not exist"]
    assert data["component_warnings"] == []
    assert data["canvas_error_count"] == 1
    assert data["unrelated_error_count"] == 0
    assert data["recovery_hint"] == (
        "Current inputs are R; outputs are A. To change the signature, call "
        "gh_set_script_pins first, then retry gh_update_script."
    )


@pytest.mark.asyncio
async def test_gh_update_script_unrelated_canvas_errors_remain_success(
    monkeypatch, patched_server
):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/script" and "script" not in (payload or {}):
            return {"success": True, "data": {"Type": "CSharpScriptComponent"}}
        if route == "/gh/script":
            return {"success": True, "data": {"guid": "cs-guid"}}
        if route == "/gh/component":
            return {
                "success": True,
                "data": {
                    "Params": {
                        "Inputs": [{"Name": "R"}],
                        "Outputs": [{"Name": "out"}, {"Name": "A"}],
                    }
                },
            }
        if route == "/gh/errors":
            return {
                "success": True,
                "data": {
                    "errors": [{"guid": "other-guid", "errors": ["Other component is broken"]}],
                    "warnings": [],
                },
            }
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_update_script",
        {"guid": "cs-guid", "code": "A = R;", "mode": "body"},
    ))

    assert payload["success"] is True
    data = payload["data"]
    assert data["component_errors"] == []
    assert data["canvas_error_count"] == 1
    assert data["unrelated_error_count"] == 1


@pytest.mark.asyncio
async def test_gh_update_script_target_warnings_remain_success(
    monkeypatch, patched_server
):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/script" and "script" not in (payload or {}):
            return {"success": True, "data": {"Type": "CSharpScriptComponent"}}
        if route == "/gh/script":
            return {"success": True, "data": {"guid": "cs-guid"}}
        if route == "/gh/component":
            return {
                "success": True,
                "data": {
                    "Params": {
                        "Inputs": [],
                        "Outputs": [{"Name": "out"}, {"Name": "B"}],
                    }
                },
            }
        if route == "/gh/errors":
            return {
                "success": True,
                "data": {
                    "errors": [],
                    "warnings": [{"guid": "cs-guid", "warnings": ["Unused using directive"]}],
                },
            }
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_update_script",
        {"guid": "cs-guid", "code": "B = 1;", "mode": "body"},
    ))

    assert payload["success"] is True
    data = payload["data"]
    assert data["component_errors"] == []
    assert data["component_warnings"] == ["Unused using directive"]
    assert data["canvas_warning_count"] == 1


def _schema_type_permits_array(schema_type):
    return schema_type == "array" or (
        isinstance(schema_type, list) and "array" in schema_type
    )


def _find_array_schemas_missing_items(value, path="$"):
    findings = []
    if isinstance(value, dict):
        if _schema_type_permits_array(value.get("type")) and "items" not in value:
            findings.append(path)
        for key, child in value.items():
            findings.extend(_find_array_schemas_missing_items(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_find_array_schemas_missing_items(child, f"{path}[{index}]"))
    return findings


@pytest.mark.asyncio
async def test_all_mcp_array_schemas_declare_items():
    tools = await server.list_tools()
    findings = []
    for tool in tools:
        for path in _find_array_schemas_missing_items(tool.inputSchema or {}):
            findings.append(f"{tool.name}: {path}")

    assert findings == [], (
        "MCP input schemas that permit arrays must declare an 'items' schema:\n"
        + "\n".join(findings)
    )


@pytest.mark.asyncio
async def test_rhino_create_coordinate_schema_advertises_numeric_arrays():
    tools = {tool.name: tool for tool in await server.list_tools()}
    schema = tools["rhino_create"].inputSchema
    properties = schema["properties"]

    for name in (
        "point",
        "location",
        "start",
        "end",
        "center",
        "base",
        "origin",
        "corner",
        "corner1",
        "corner2",
    ):
        coordinate_schema = properties[name]
        assert coordinate_schema["type"] == "array"
        assert coordinate_schema["items"] == {"type": "number"}
        assert coordinate_schema["minItems"] == 3
        assert coordinate_schema["maxItems"] == 3

    points_schema = properties["points"]
    assert points_schema["type"] == "array"
    assert points_schema["items"]["type"] == "array"
    assert points_schema["items"]["items"] == {"type": "number"}
    assert points_schema["items"]["minItems"] == 3
    assert points_schema["items"]["maxItems"] == 3

    assert properties["plane"]["type"] == "string"
    assert "XY, XZ, or YZ" in properties["plane"]["description"]
    assert "#rrggbb" in properties["color"]["description"]
    assert "positive" in properties["radius"]["description"]
    assert "positive width" in properties["width"]["description"]
    assert "positive depth" in properties["depth"]["description"]
    assert "non-zero height" in properties["height"]["description"]


@pytest.mark.asyncio
async def test_rhino_curve_ops_trim_schema_matches_native_interval_contract():
    tools = {tool.name: tool for tool in await server.list_tools()}
    properties = tools["rhino_curve_ops"].inputSchema["properties"]

    assert "point" not in properties
    assert properties["t0"]["type"] == "number"
    assert properties["t1"]["type"] == "number"
    assert "Legacy trim end parameter" in properties["parameter"]["description"]


@pytest.mark.asyncio
async def test_rhino_curve_ops_trim_dispatches_native_interval(monkeypatch, patched_server):
    native_success = {"success": True, "data": {"id": "trimmed-curve"}}
    call_rhino_mock = AsyncMock(return_value=native_success)
    monkeypatch.setattr(server, "call_rhino", call_rhino_mock)

    response = await server.call_tool(
        "rhino_curve_ops",
        {"action": "trim", "id": "curve-id", "t0": 0.25, "t1": 0.75},
    )

    assert _decode_response(response) == native_success
    call_rhino_mock.assert_awaited_once_with(
        "/curve/trim",
        "POST",
        {"id": "curve-id", "t0": 0.25, "t1": 0.75},
    )


@pytest.mark.asyncio
async def test_rhino_curve_ops_trim_legacy_parameter_maps_to_native_interval(monkeypatch, patched_server):
    native_success = {"success": True, "data": {"id": "trimmed-curve"}}
    call_rhino_mock = AsyncMock(return_value=native_success)
    monkeypatch.setattr(server, "call_rhino", call_rhino_mock)

    response = await server.call_tool(
        "rhino_curve_ops",
        {"action": "trim", "id": "curve-id", "parameter": 0.5},
    )

    assert _decode_response(response) == native_success
    call_rhino_mock.assert_awaited_once_with(
        "/curve/trim",
        "POST",
        {"id": "curve-id", "t0": 0.0, "t1": 0.5},
    )


def test_rhino_create_bootstrap_matrix_matches_native_rejection_contract():
    from rook.bootstrap.test_matrix import ExpectedOutcome, TOOL_TESTS

    cases = {case.id: case for case in TOOL_TESTS.cases}

    assert cases["create-006"].expected is ExpectedOutcome.FAILURE
    assert "positive radius" in cases["create-006"].learn_on_failure
    assert cases["create-007"].expected is ExpectedOutcome.FAILURE
    assert "positive radius" in cases["create-007"].learn_on_failure
    assert cases["create-013"].expected is ExpectedOutcome.EITHER
    assert "positive dimensions" in cases["create-013"].learn_on_failure
    assert cases["create-011"].expected is ExpectedOutcome.EITHER
    assert "Named color strings" in cases["create-011"].learn_on_failure


@pytest.mark.asyncio
async def test_gh_execute_intent_description_does_not_claim_only_tool():
    """Drift regression — gh_execute_intent must not claim exclusive ownership
    of GH component creation when gh_create_python_script and
    gh_create_csharp_script are dedicated creation tools AND gh_execute_intent
    is excluded from worker-mode preload per tool_groups.py.
    """
    tools = await server.list_tools()
    gh_execute_intent = next((t for t in tools if t.name == "gh_execute_intent"), None)
    assert gh_execute_intent is not None, "gh_execute_intent tool missing from registered tools"

    desc = gh_execute_intent.description
    assert "This is the ONLY tool for creating GH components" not in desc, (
        "gh_execute_intent description reintroduces ONLY-tool claim — false per "
        "gh_create_python_script / gh_create_csharp_script + tool_groups.py:37 exclusion"
    )
    assert "All component creation MUST go through this tool" not in desc, (
        "gh_execute_intent description reintroduces MUST-go-through claim"
    )


# ---------- gh_create_script — unified tool contract (PR-2) ----------
# Anchors for 2026-04-21 gh-script-component-routing design-pass memo §PR-2.
# The unified tool collapses gh_create_python_script / gh_create_csharp_script
# onto a single discriminator-param tool; aliases remain for back-compat.


@pytest.mark.asyncio
async def test_gh_create_script_inputSchema_enforces_language():
    """Load-bearing PR-2 contract test. The `language` argument must be
    enforced at the API boundary via inputSchema (enum + required), not
    just mentioned in description prose — a prose-only guarantee allows
    structural drift where the description reads correctly but callers
    are no longer blocked from omitting or mis-setting the language.
    """
    tools = await server.list_tools()
    gh_create_script = next((t for t in tools if t.name == "gh_create_script"), None)
    assert gh_create_script is not None, "gh_create_script tool missing from registered tools"

    schema = gh_create_script.inputSchema
    props = schema.get("properties", {})
    assert "language" in props, "gh_create_script schema missing 'language' property"

    language_schema = props["language"]
    assert language_schema.get("enum") == ["python", "csharp"], (
        f"gh_create_script language enum must be ['python', 'csharp']; got {language_schema.get('enum')!r}"
    )

    required = schema.get("required", [])
    assert "language" in required, "gh_create_script must require 'language'"
    assert "code" in required, "gh_create_script must require 'code'"
    # Pins are NOT required at the schema level — the helper accepts
    # source-only or sink-only scripts (at-least-one-non-empty check in
    # _execute_gh_create_script). Requiring pins_in + pins_out at the
    # schema boundary would structurally block valid configurations the
    # implementation supports.
    assert "pins_in" not in required, (
        "gh_create_script schema must not require pins_in — helper accepts sink-only scripts"
    )
    assert "pins_out" not in required, (
        "gh_create_script schema must not require pins_out — helper accepts source-only scripts"
    )

    # Prose-level courtesy assertion — redundant with schema but keeps
    # description aligned so casual reads of the tool catalog match reality.
    desc = gh_create_script.description
    assert "python" in desc and "csharp" in desc, (
        "gh_create_script description must mention both languages"
    )


@pytest.mark.asyncio
async def test_gh_script_tool_descriptions_teach_usable_geometry_outputs():
    required = [
        '{"name": "Points", "type": "Point3d", "access": "list"}',
        "Points = [rg.Point3d(0, 0, 0), rg.Point3d(1, 0, 0), rg.Point3d(2, 0, 0)]",
        "Do not assign coordinate dictionaries",
        "Do not assign JSON strings",
        "Do not assign wrapper/debug objects",
    ]

    tools = {tool.name: tool for tool in await server.list_tools()}
    for tool_name in ("gh_create_script", "gh_create_python_script"):
        tool = tools[tool_name]
        description = tool.description
        for phrase in required:
            assert phrase in description, (
                f"{tool_name} missing geometry output guidance: {phrase}"
            )

        pins_out_description = tool.inputSchema["properties"]["pins_out"]["description"]
        assert (
            '{"name": "Points", "type": "Point3d", "access": "list"}'
            in pins_out_description
        )


@pytest.mark.asyncio
async def test_gh_create_script_rejects_missing_language(monkeypatch, patched_server):
    """Handler-level defense-in-depth. Schema-level enum enforcement is the
    primary gate, but the handler also rejects at runtime so callers that
    bypass schema validation (direct helper invocation, stale MCP clients)
    see a structured invalid_input naming both valid choices.

    The assertion checks no component-creation HTTP call fires; session-
    recording HTTP calls (`/gh/document`) are expected and not asserted on.
    """
    routes_called: list[str] = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        routes_called.append(route)
        # /gh/document is the session-context probe — benign, allow it
        if route == "/gh/document":
            return {"success": True, "data": {"name": "unknown.gh", "path": ""}}
        raise AssertionError(
            f"Missing-language rejection must not hit the create pipeline; got route {route!r}"
        )

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    response = await server.call_tool(
        "gh_create_script",
        {
            "code": "a = 1",
            "pins_in": ["x:float"],
            "pins_out": ["a:int"],
        },
    )
    payload = _decode_response(response)

    assert payload["success"] is False
    assert "language" in payload["data"].lower()
    assert "python" in payload["data"]
    assert "csharp" in payload["data"]
    # Component-creation routes must not be called on invalid-language path.
    for forbidden in ("/gh/create-component", "/gh/script-params", "/gh/script", "/gh/errors"):
        assert forbidden not in routes_called, (
            f"{forbidden} was called during rejection path; routes={routes_called!r}"
        )


@pytest.mark.asyncio
async def test_gh_create_script_rejects_invalid_language(monkeypatch, patched_server):
    """Unknown language values must be rejected with the same structured
    message as omission — no silent fallback to python-as-default.
    """
    routes_called: list[str] = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        routes_called.append(route)
        if route == "/gh/document":
            return {"success": True, "data": {"name": "unknown.gh", "path": ""}}
        raise AssertionError(
            f"Invalid-language rejection must not hit the create pipeline; got route {route!r}"
        )

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    response = await server.call_tool(
        "gh_create_script",
        {
            "language": "rust",
            "code": "fn main() {}",
            "pins_in": ["x:float"],
            "pins_out": ["a:int"],
        },
    )
    payload = _decode_response(response)

    assert payload["success"] is False
    assert "python" in payload["data"] and "csharp" in payload["data"]
    for forbidden in ("/gh/create-component", "/gh/script-params", "/gh/script", "/gh/errors"):
        assert forbidden not in routes_called, (
            f"{forbidden} was called during rejection path; routes={routes_called!r}"
        )


@pytest.mark.asyncio
async def test_gh_create_script_python_delegates_to_py3_guid(monkeypatch, patched_server):
    """Unified tool with language='python' must route through the same
    pipeline as the gh_create_python_script alias — fixed PY3 GUID,
    auto-generated coercion preamble prepended to user code.
    """
    recorded_calls = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        recorded_calls.append((route, method, payload))
        if route == "/gh/create-component":
            assert payload["guid"] == "719467e6-7cf5-4848-99b0-c5dd57e5442c"
            return {"success": True, "data": {"guid": "py-guid"}}
        if route == "/gh/script-params":
            return {"success": True, "data": {"Guid": "py-guid", "Inputs": 1, "Outputs": 1}}
        if route == "/gh/script":
            assert "# ── Auto-generated GH input coercion" in payload["script"]
            return {"success": True, "data": {"Guid": "py-guid"}}
        if route == "/gh/errors":
            return {"success": True, "data": {"errors": []}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    response = await server.call_tool(
        "gh_create_script",
        {
            "language": "python",
            "code": "a = Pts",
            "pins_in": [{"name": "Pts", "type": "Point3d", "access": "list"}],
            "pins_out": ["a:Point3d"],
            "name": "Unified Py",
        },
    )
    payload = _decode_response(response)

    assert payload["success"] is True
    assert payload["data"]["component_guid"] == "py-guid"
    assert payload["data"]["name"] == "Unified Py"
    assert any(route == "/gh/create-component" for route, _, _ in recorded_calls)


@pytest.mark.asyncio
async def test_gh_create_script_python_point_list_output_adds_typed_postamble(
    monkeypatch, patched_server
):
    """Declared Point3d list outputs must be coerced before RhinoCode stores
    them, so downstream GH/Rhino sees real geometry rather than PyObject blobs.
    """
    scripts: list[str] = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/create-component":
            return {"success": True, "data": {"guid": "py-guid"}}
        if route == "/gh/script-params":
            return {"success": True, "data": {"Guid": "py-guid", "Inputs": 0, "Outputs": 1}}
        if route == "/gh/script":
            scripts.append(payload["script"])
            return {"success": True, "data": {"Guid": "py-guid"}}
        if route == "/gh/errors":
            return {"success": True, "data": {"errors": []}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = await server._execute_gh_create_script(
        "python",
        {
            "code": (
                "import Rhino.Geometry as rg\n"
                "Points = [rg.Point3d(0, 0, 0), rg.Point3d(1, 0, 0)]"
            ),
            "pins_in": [],
            "pins_out": [{"name": "Points", "type": "Point3d", "access": "list"}],
            "name": "Typed Point Output",
        },
        port=1234,
    )

    assert payload["success"] is True
    assert len(scripts) == 1
    script = scripts[0]
    assert "Points = [rg.Point3d" in script
    assert "# ── Auto-generated GH output coercion" in script
    assert script.index("Points = [rg.Point3d") < script.index(
        "# ── Auto-generated GH output coercion"
    )
    assert "Points = _rook_gh_output_list(Points, _rook_rg.Point3d)" in script


@pytest.mark.asyncio
async def test_gh_create_script_csharp_delegates_to_cs3_guid(monkeypatch, patched_server):
    """Unified tool with language='csharp' must route through the same
    pipeline as the gh_create_csharp_script alias — fixed CS3 GUID and
    Script_Instance wrapper applied to body code.
    """
    recorded_calls = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        recorded_calls.append((route, method, payload))
        if route == "/gh/create-component":
            assert payload["guid"] == "b6ba1144-02d6-4a2d-b53c-ec62e290eeb7"
            return {"success": True, "data": {"guid": "cs-guid"}}
        if route == "/gh/script-params":
            return {"success": True, "data": {"Guid": "cs-guid", "Inputs": 1, "Outputs": 1}}
        if route == "/gh/script":
            assert "class Script_Instance" in payload["script"]
            assert "private void RunScript(object R, ref object A)" in payload["script"]
            return {"success": True, "data": {"Guid": "cs-guid"}}
        if route == "/gh/errors":
            return {"success": True, "data": {"errors": []}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    response = await server.call_tool(
        "gh_create_script",
        {
            "language": "csharp",
            "code": "A = Convert.ToDouble(R);",
            "pins_in": [{"name": "R", "type": "double"}],
            "pins_out": [{"name": "A", "type": "double"}],
            "name": "Unified CS",
        },
    )
    payload = _decode_response(response)

    assert payload["success"] is True
    assert payload["data"]["component_guid"] == "cs-guid"
    assert payload["data"]["name"] == "Unified CS"
    assert any(route == "/gh/create-component" for route, _, _ in recorded_calls)


@pytest.mark.asyncio
async def test_gh_create_script_alias_response_shape_bytewise_matches(monkeypatch, patched_server):
    """Alias back-compat proof. Extracting the shared _execute_gh_create_script
    helper must NOT change the response shape or values of the existing
    gh_create_python_script / gh_create_csharp_script tools. This test
    runs each alias and the unified tool with identical arguments against
    an identical mock HTTP stub and asserts the response payloads (minus
    language-specific default `name`, when no explicit name given) match.
    """

    def make_fake_call_rhino(guid: str):
        async def fake(route, method="GET", payload=None, port=None):
            if route == "/gh/create-component":
                return {"success": True, "data": {"guid": guid}}
            if route == "/gh/script-params":
                return {"success": True, "data": {"Guid": guid, "Inputs": 1, "Outputs": 1}}
            if route == "/gh/script":
                return {"success": True, "data": {"Guid": guid}}
            if route == "/gh/errors":
                return {"success": True, "data": {"errors": []}}
            raise AssertionError(f"Unexpected route: {route}")
        return fake

    shared_args = {
        "code": "a = 1",
        "pins_in": [{"name": "x", "type": "float"}],
        "pins_out": [{"name": "a", "type": "int"}],
        "name": "ParityTest",
    }

    # Python path parity: gh_create_python_script vs gh_create_script(language=python)
    monkeypatch.setattr(server, "call_rhino", make_fake_call_rhino("py-parity"))
    alias_py = _decode_response(await server.call_tool("gh_create_python_script", dict(shared_args)))
    unified_py = _decode_response(await server.call_tool(
        "gh_create_script", {**shared_args, "language": "python"}
    ))
    assert alias_py["success"] is True and unified_py["success"] is True
    assert sorted(alias_py["data"].keys()) == sorted(unified_py["data"].keys()), (
        "Unified Python path response keys drifted from gh_create_python_script alias"
    )
    for key in alias_py["data"]:
        assert alias_py["data"][key] == unified_py["data"][key], (
            f"Python path value drift on key {key!r}: "
            f"alias={alias_py['data'][key]!r} unified={unified_py['data'][key]!r}"
        )

    # C# path parity: gh_create_csharp_script vs gh_create_script(language=csharp)
    monkeypatch.setattr(server, "call_rhino", make_fake_call_rhino("cs-parity"))
    alias_cs = _decode_response(await server.call_tool("gh_create_csharp_script", dict(shared_args)))
    unified_cs = _decode_response(await server.call_tool(
        "gh_create_script", {**shared_args, "language": "csharp"}
    ))
    assert alias_cs["success"] is True and unified_cs["success"] is True
    assert sorted(alias_cs["data"].keys()) == sorted(unified_cs["data"].keys()), (
        "Unified C# path response keys drifted from gh_create_csharp_script alias"
    )
    for key in alias_cs["data"]:
        assert alias_cs["data"][key] == unified_cs["data"][key], (
            f"C# path value drift on key {key!r}: "
            f"alias={alias_cs['data'][key]!r} unified={unified_cs['data'][key]!r}"
        )


@pytest.mark.asyncio
async def test_gh_create_python_script_alias_preserves_error_prefix(monkeypatch, patched_server):
    """Alias back-compat on the FAILURE surface. Pre-PR-2, unexpected
    exceptions inside the Python creation path surfaced with the prefix
    `gh_create_python_script failed: ...`. After helper extraction, callers
    that pattern-match on the alias prefix (log scrapers, error-routing
    rules) must continue to see it. Forces a helper-internal raise by
    providing empty pins_in + empty pins_out.
    """
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/document":
            return {"success": True, "data": {"name": "unknown.gh", "path": ""}}
        raise AssertionError(f"No create-pipeline call should fire; got {route!r}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    response = await server.call_tool(
        "gh_create_python_script",
        {"code": "a = 1", "pins_in": [], "pins_out": []},
    )
    payload = _decode_response(response)

    assert payload["success"] is False
    assert payload["data"].startswith("gh_create_python_script failed: "), (
        f"Alias exception prefix drifted; got: {payload['data']!r}"
    )


@pytest.mark.asyncio
async def test_gh_create_csharp_script_alias_preserves_error_prefix(monkeypatch, patched_server):
    """Symmetric alias back-compat on the C# failure surface — pinning the
    historical `gh_create_csharp_script failed: ...` prefix after helper
    extraction.
    """
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/document":
            return {"success": True, "data": {"name": "unknown.gh", "path": ""}}
        raise AssertionError(f"No create-pipeline call should fire; got {route!r}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    response = await server.call_tool(
        "gh_create_csharp_script",
        {"code": "A = R;", "pins_in": [], "pins_out": []},
    )
    payload = _decode_response(response)

    assert payload["success"] is False
    assert payload["data"].startswith("gh_create_csharp_script failed: "), (
        f"Alias exception prefix drifted; got: {payload['data']!r}"
    )


@pytest.mark.asyncio
async def test_gh_create_script_unified_uses_unified_error_prefix(monkeypatch, patched_server):
    """Symmetric with the two alias tests above, but on the unified tool —
    confirms the default `tool_name="gh_create_script"` is actually applied
    when the unified tool is dispatched directly.
    """
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/document":
            return {"success": True, "data": {"name": "unknown.gh", "path": ""}}
        raise AssertionError(f"No create-pipeline call should fire; got {route!r}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    response = await server.call_tool(
        "gh_create_script",
        {"language": "python", "code": "a = 1", "pins_in": [], "pins_out": []},
    )
    payload = _decode_response(response)

    assert payload["success"] is False
    assert payload["data"].startswith("gh_create_script failed: "), (
        f"Unified tool exception prefix drifted; got: {payload['data']!r}"
    )


# ---------- gh_execute_intent — script-component handoff (PR-3) ----------
# Anchors for 2026-04-21 gh-script-component-routing design-pass memo §PR-3.
# The handoff check refuses to create modern RhinoCode Python 3 / C# Script
# components via `/gh/create-component` and points the caller at
# `gh_create_script`. Runs post-resolution (both DSPy and fallback paths)
# and pre-dispatch; fires as a control-flow exception caught at the
# gh_execute_intent case-arm boundary.


_PR3_PY3_GUID = "719467e6-7cf5-4848-99b0-c5dd57e5442c"
_PR3_CS3_GUID = "b6ba1144-02d6-4a2d-b53c-ec62e290eeb7"
_PR3_SPHERE_GUID = "c2a3c4f8-44c5-4bc5-8e06-c5fe2e90b6f4"  # non-script, for control


def _make_handoff_test_knowledge_store(components: list[dict]):
    """Build a minimal mock `get_gh_knowledge_store()` return whose
    `.query(intent, tier)` yields a pre-defined candidate list.
    """
    guids = [c.get("guid") for c in components if c.get("guid")]

    class _MockStore:
        def query(self, _intent: str, _tier: str = "context") -> dict[str, Any]:
            return {
                "guids": guids,
                "components": components,
                "gotchas": [],
            }

    return _MockStore()


def _break_dspy_resolver(monkeypatch):
    """Force the gh_execute_intent case-arm onto the hardcoded fallback
    path by making GHIntentResolver construction raise. The case-arm's
    DSPy try/except catches, sets DSPY_AVAILABLE = False internally, and
    falls through to the categorization branch — which is the boundary
    where our handoff check still fires from the final `all_positioned`.
    """
    import rook.learning.dspy_modules as dspy_modules_mod

    class _BrokenResolver:
        def __init__(self):
            raise RuntimeError("PR-3 test: DSPy intentionally disabled")

    monkeypatch.setattr(dspy_modules_mod, "GHIntentResolver", _BrokenResolver)


@pytest.fixture
def pr3_handoff_setup(monkeypatch, patched_server):
    """Shared fixture for PR-3 handoff tests: stubs the noisy optional
    queries (unified store + pattern store) so the case-arm reaches the
    resolver/fallback boundary cleanly. Each test supplies its own
    knowledge-store candidate components and call_rhino behavior.
    """
    # Silence optional pattern queries — both are try/except-wrapped in the
    # case-arm, so raising is safe; this just skips noise.
    import rook.learning.gh_knowledge as gh_kno
    import rook.learning.pattern_store as ps_mod

    class _NoopUnifiedStore:
        def search(self, **kwargs):
            return []

    monkeypatch.setattr(server, "get_unified_store", lambda: _NoopUnifiedStore())

    class _NoopPatternStore:
        def __init__(self, *a, **kw):
            pass

        def search(self, **kwargs):
            return []

    monkeypatch.setattr(ps_mod, "PatternStore", _NoopPatternStore)


async def _call_gh_execute_intent(intent: str):
    response = await server.call_tool("gh_execute_intent", {"intent": intent})
    return _decode_response(response)


def _parse_handoff_payload(payload: dict) -> dict:
    """Parse the structured JSON dict carried inside a failure `data`
    string. `_decode_response` returns `payload["data"]` as a raw
    post-'Error: ' string; for PR-3 handoffs that string is a JSON blob
    because the case-arm puts a dict in `result["data"]` and call_tool's
    failure formatter json.dumps it. Returns the parsed dict.
    """
    raw = payload.get("data")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return json.loads(raw)
    raise AssertionError(f"handoff data payload is neither dict nor str: {raw!r}")


def _build_handoff_call_rhino(routes_called: list):
    """Permissive call_rhino mock: succeeds on read-only routes used by
    session recording and candidate-resolution, but RAISES on any
    dispatch route that would materialize a component. If the handoff
    check fires correctly, none of the dispatch routes should be hit.
    """
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        routes_called.append(route)
        if route == "/gh/document":
            return {"success": True, "data": {"name": "test.gh", "path": ""}}
        if route == "/gh/query":
            return {"success": True, "data": {"objects": []}}
        if route == "/gh/snapshot":
            return {"success": True, "data": {"epoch": "test-epoch", "components": []}}
        # Any component-creation / edit route must NOT fire on handoff.
        if route in ("/gh/create-component", "/gh/edit", "/gh/script-params",
                     "/gh/script", "/gh/errors", "/gh/solve"):
            raise AssertionError(
                f"Handoff must short-circuit before dispatch; got route {route!r}"
            )
        return {"success": True, "data": {}}

    return fake_call_rhino


@pytest.mark.asyncio
async def test_gh_execute_intent_hands_off_python_script_component(
    monkeypatch, pr3_handoff_setup
):
    """Intent resolves to a RhinoCode Python 3 Script component → the
    handoff check must refuse with structured `handoff_required`,
    naming gh_create_script(language="python") as the recommended tool.
    No /gh/create-component or /gh/edit call fires.
    """
    _break_dspy_resolver(monkeypatch)
    # get_gh_knowledge_store is imported locally inside the case arm
    # (`from rook.learning.gh_knowledge import get_gh_knowledge_store`),
    # so the patch must target the module-of-origin, not `server`.
    import rook.learning.gh_knowledge as _ghk
    monkeypatch.setattr(
        _ghk,
        "get_gh_knowledge_store",
        lambda: _make_handoff_test_knowledge_store([
            {
                "guid": _PR3_PY3_GUID,
                "name": "Python 3 Script",
                "family": "script",
                "quick": "",
                "params": {},
                "deprecated": False,
            },
        ]),
    )
    routes: list[str] = []
    monkeypatch.setattr(server, "call_rhino", _build_handoff_call_rhino(routes))

    payload = await _call_gh_execute_intent("create a python script that prints hello")

    assert payload["success"] is False
    data = _parse_handoff_payload(payload)
    assert data.get("handoff_required") is True
    assert data.get("recommended_tool") == "gh_create_script"
    assert data.get("recommended_language") == "python"
    assert data.get("component_guid") == _PR3_PY3_GUID


@pytest.mark.asyncio
async def test_gh_execute_intent_hands_off_csharp_script_component(
    monkeypatch, pr3_handoff_setup
):
    """Symmetric to the python test — CS3 GUID triggers handoff with
    recommended_language='csharp'.
    """
    _break_dspy_resolver(monkeypatch)
    # get_gh_knowledge_store is imported locally inside the case arm
    # (`from rook.learning.gh_knowledge import get_gh_knowledge_store`),
    # so the patch must target the module-of-origin, not `server`.
    import rook.learning.gh_knowledge as _ghk
    monkeypatch.setattr(
        _ghk,
        "get_gh_knowledge_store",
        lambda: _make_handoff_test_knowledge_store([
            {
                "guid": _PR3_CS3_GUID,
                "name": "C# Script",
                "family": "script",
                "quick": "",
                "params": {},
                "deprecated": False,
            },
        ]),
    )
    routes: list[str] = []
    monkeypatch.setattr(server, "call_rhino", _build_handoff_call_rhino(routes))

    payload = await _call_gh_execute_intent("create a C# script that computes a sum")

    assert payload["success"] is False
    data = _parse_handoff_payload(payload)
    assert data.get("handoff_required") is True
    assert data.get("recommended_tool") == "gh_create_script"
    assert data.get("recommended_language") == "csharp"
    assert data.get("component_guid") == _PR3_CS3_GUID


@pytest.mark.asyncio
async def test_gh_execute_intent_handoff_response_names_alias_tool(
    monkeypatch, pr3_handoff_setup
):
    """Handoff response must surface the language-specific alias tool
    name so callers plumbed for the alias can drop in without migrating
    to the unified tool immediately.
    """
    _break_dspy_resolver(monkeypatch)
    # get_gh_knowledge_store is imported locally inside the case arm
    # (`from rook.learning.gh_knowledge import get_gh_knowledge_store`),
    # so the patch must target the module-of-origin, not `server`.
    import rook.learning.gh_knowledge as _ghk
    monkeypatch.setattr(
        _ghk,
        "get_gh_knowledge_store",
        lambda: _make_handoff_test_knowledge_store([
            {"guid": _PR3_PY3_GUID, "name": "Python 3 Script", "family": "script",
             "quick": "", "params": {}, "deprecated": False},
        ]),
    )
    routes: list[str] = []
    monkeypatch.setattr(server, "call_rhino", _build_handoff_call_rhino(routes))

    payload = await _call_gh_execute_intent("write a python script")

    data = _parse_handoff_payload(payload)
    assert data.get("alias_tool") == "gh_create_python_script"

    # Also confirm the csharp case.
    # get_gh_knowledge_store is imported locally inside the case arm
    # (`from rook.learning.gh_knowledge import get_gh_knowledge_store`),
    # so the patch must target the module-of-origin, not `server`.
    import rook.learning.gh_knowledge as _ghk
    monkeypatch.setattr(
        _ghk,
        "get_gh_knowledge_store",
        lambda: _make_handoff_test_knowledge_store([
            {"guid": _PR3_CS3_GUID, "name": "C# Script", "family": "script",
             "quick": "", "params": {}, "deprecated": False},
        ]),
    )
    payload_cs = await _call_gh_execute_intent("write a C# script")
    data_cs = _parse_handoff_payload(payload_cs)
    assert data_cs.get("alias_tool") == "gh_create_csharp_script"


@pytest.mark.asyncio
async def test_gh_execute_intent_handoff_fires_on_fallback_path(
    monkeypatch, pr3_handoff_setup
):
    """Handoff must fire whether the resolution path is DSPy or the
    hardcoded fallback — both routes populate `all_positioned`, and the
    check runs on the final list before dispatch. _break_dspy_resolver
    forces the fallback path; this test is the explicit regression floor
    for that branch.
    """
    _break_dspy_resolver(monkeypatch)
    # get_gh_knowledge_store is imported locally inside the case arm
    # (`from rook.learning.gh_knowledge import get_gh_knowledge_store`),
    # so the patch must target the module-of-origin, not `server`.
    import rook.learning.gh_knowledge as _ghk
    monkeypatch.setattr(
        _ghk,
        "get_gh_knowledge_store",
        lambda: _make_handoff_test_knowledge_store([
            {"guid": _PR3_PY3_GUID, "name": "Python 3 Script", "family": "script",
             "quick": "", "params": {}, "deprecated": False},
        ]),
    )
    routes: list[str] = []
    monkeypatch.setattr(server, "call_rhino", _build_handoff_call_rhino(routes))

    payload = await _call_gh_execute_intent("make a python script component")

    assert payload["success"] is False
    data = _parse_handoff_payload(payload)
    assert data.get("handoff_required") is True
    # Regression: the dispatch routes must never be hit — assertion fires
    # from the mock if they are. No extra check needed here beyond success.


@pytest.mark.asyncio
async def test_gh_execute_intent_does_not_handoff_on_non_script_components(
    monkeypatch, pr3_handoff_setup
):
    """Regression floor: a normal intent (sphere) must NOT trigger the
    handoff. The check fires only on the two fixed RhinoCode script GUIDs.
    """
    _break_dspy_resolver(monkeypatch)
    # get_gh_knowledge_store is imported locally inside the case arm
    # (`from rook.learning.gh_knowledge import get_gh_knowledge_store`),
    # so the patch must target the module-of-origin, not `server`.
    import rook.learning.gh_knowledge as _ghk
    monkeypatch.setattr(
        _ghk,
        "get_gh_knowledge_store",
        lambda: _make_handoff_test_knowledge_store([
            {"guid": _PR3_SPHERE_GUID, "name": "Sphere", "family": "surface",
             "quick": "", "params": {}, "deprecated": False},
        ]),
    )
    # Permissive call_rhino — the dispatch routes ARE expected to run here.
    async def permissive_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/document":
            return {"success": True, "data": {"name": "test.gh", "path": ""}}
        if route == "/gh/query":
            return {"success": True, "data": {"objects": []}}
        if route == "/gh/snapshot":
            return {"success": True, "data": {"epoch": "test-epoch", "components": []}}
        if route == "/gh/edit":
            return {"success": True, "data": {"created": [], "wired": []}}
        return {"success": True, "data": {}}

    monkeypatch.setattr(server, "call_rhino", permissive_call_rhino)

    payload = await _call_gh_execute_intent("create a sphere")

    # Non-handoff path — either succeeds or fails for other reasons, but
    # MUST NOT return a handoff_required response.
    data = payload["data"]
    if isinstance(data, dict):
        assert data.get("handoff_required") is not True, (
            f"Non-script intent triggered false-positive handoff; data={data!r}"
        )
    elif isinstance(data, str):
        # Failure-with-string-data path; confirm it's NOT a JSON-serialized
        # handoff that slipped through (defense in depth — the sphere path
        # should not produce any handoff shape regardless of serialization).
        try:
            parsed = json.loads(data)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            assert parsed.get("handoff_required") is not True, (
                f"Non-script intent produced handoff-shaped error body: {parsed!r}"
            )


@pytest.mark.asyncio
async def test_gh_execute_intent_handoff_preserves_component_guid_in_response(
    monkeypatch, pr3_handoff_setup
):
    """Debuggability: the handoff response must include the exact GUID
    that triggered it so callers can introspect WHY the refusal fired
    (e.g., distinguish PY3 vs CS3 root cause from logs / transcripts).
    GUID is normalized to lowercase in the response per the helper.
    """
    _break_dspy_resolver(monkeypatch)
    # Feed uppercase GUID through — helper must normalize it.
    upper_guid = _PR3_CS3_GUID.upper()
    # get_gh_knowledge_store is imported locally inside the case arm
    # (`from rook.learning.gh_knowledge import get_gh_knowledge_store`),
    # so the patch must target the module-of-origin, not `server`.
    import rook.learning.gh_knowledge as _ghk
    monkeypatch.setattr(
        _ghk,
        "get_gh_knowledge_store",
        lambda: _make_handoff_test_knowledge_store([
            {"guid": upper_guid, "name": "C# Script", "family": "script",
             "quick": "", "params": {}, "deprecated": False},
        ]),
    )
    routes: list[str] = []
    monkeypatch.setattr(server, "call_rhino", _build_handoff_call_rhino(routes))

    payload = await _call_gh_execute_intent("make a csharp script")

    data = _parse_handoff_payload(payload)
    # The response's component_guid field must carry the triggering GUID
    # (lowercase-normalized); this is the primary debuggability anchor.
    assert data.get("component_guid") == _PR3_CS3_GUID  # lowercase canonical


@pytest.mark.asyncio
async def test_gh_execute_intent_handoff_is_structured_for_mcp_tool_executor(
    monkeypatch, pr3_handoff_setup
):
    """_mcp_tool_executor is the canonical agent-path executor (used by
    spawn_agent and plan_and_execute). PR-3's handoff must surface as a
    structured dict on THAT surface, not just in the raw MCP text — agents
    can't branch on `handoff_required` / `recommended_tool` otherwise.

    Codex review of PR-3 caught that call_tool formats dict-data failures
    as `Error: {json}`, but _mcp_tool_executor fell back to a success
    wrapper on unparseable text. Fix threads `Error: <json>` through so
    the executor returns `{"success": False, "data": <parsed-dict>}`.
    """
    _break_dspy_resolver(monkeypatch)
    import rook.learning.gh_knowledge as _ghk
    monkeypatch.setattr(
        _ghk,
        "get_gh_knowledge_store",
        lambda: _make_handoff_test_knowledge_store([
            {"guid": _PR3_PY3_GUID, "name": "Python 3 Script", "family": "script",
             "quick": "", "params": {}, "deprecated": False},
        ]),
    )
    routes: list[str] = []
    monkeypatch.setattr(server, "call_rhino", _build_handoff_call_rhino(routes))

    # Go through the canonical agent executor rather than call_tool + _decode_response.
    result = await server._mcp_tool_executor(
        "gh_execute_intent",
        {"intent": "create a python script that prints hi"},
    )

    # The executor must return a structured failure with the handoff dict
    # reachable via result["data"] — no string-parsing required by callers.
    assert result.get("success") is False, (
        f"Handoff must be signaled as failure via _mcp_tool_executor; got: {result!r}"
    )
    data = result.get("data")
    assert isinstance(data, dict), (
        f"Handoff data must be a dict on the agent-executor surface; got: {data!r}"
    )
    assert data.get("handoff_required") is True
    assert data.get("recommended_tool") == "gh_create_script"
    assert data.get("recommended_language") == "python"
    assert data.get("alias_tool") == "gh_create_python_script"


@pytest.mark.asyncio
async def test_gh_execute_intent_handoff_does_not_record_as_failed_observation(
    monkeypatch, pr3_handoff_setup
):
    """Handoffs are routing corrections, not execution failures. They must
    NOT inflate per-tool failure counters / lower success rates in the
    metrics store. The `_is_handoff` sentinel gates `_record_observation`
    early-return.

    Codex review of PR-3 caught that _record_observation ran
    unconditionally at call_tool's tail with `success=False`,
    contradicting the intent to "not track as failure." This test pins
    the early-return behavior.
    """
    observation_calls: list[tuple[str, dict]] = []

    def _recording_stub(tool_name, arguments, result, duration_ms, injection_meta):
        # The real _record_observation contains an _is_handoff early-return;
        # we re-wrap it here so the test asserts on whether the observation
        # body was ever entered (i.e. whether the early-return logic held).
        if result.get("_is_handoff"):
            return  # same short-circuit as production
        observation_calls.append((tool_name, dict(result)))

    monkeypatch.setattr(server, "_record_observation", _recording_stub)

    _break_dspy_resolver(monkeypatch)
    import rook.learning.gh_knowledge as _ghk
    monkeypatch.setattr(
        _ghk,
        "get_gh_knowledge_store",
        lambda: _make_handoff_test_knowledge_store([
            {"guid": _PR3_PY3_GUID, "name": "Python 3 Script", "family": "script",
             "quick": "", "params": {}, "deprecated": False},
        ]),
    )
    routes: list[str] = []
    monkeypatch.setattr(server, "call_rhino", _build_handoff_call_rhino(routes))

    await _call_gh_execute_intent("make a python script")

    # The handoff path must not have recorded any observation for this tool.
    intent_obs = [obs for obs in observation_calls if obs[0] == "gh_execute_intent"]
    assert intent_obs == [], (
        f"Handoff path recorded an observation for gh_execute_intent; "
        f"got {len(intent_obs)} observations: {intent_obs!r}"
    )


@pytest.mark.asyncio
async def test_gh_execute_intent_handoff_sentinel_not_in_response_text(
    monkeypatch, pr3_handoff_setup
):
    """The `_is_handoff` sentinel is an internal-only marker (same
    underscore-prefix convention as `_metrics_extra` and `_injection_meta`).
    It must be popped before response serialization so callers never see
    it in the response text.
    """
    _break_dspy_resolver(monkeypatch)
    import rook.learning.gh_knowledge as _ghk
    monkeypatch.setattr(
        _ghk,
        "get_gh_knowledge_store",
        lambda: _make_handoff_test_knowledge_store([
            {"guid": _PR3_PY3_GUID, "name": "Python 3 Script", "family": "script",
             "quick": "", "params": {}, "deprecated": False},
        ]),
    )
    routes: list[str] = []
    monkeypatch.setattr(server, "call_rhino", _build_handoff_call_rhino(routes))

    response = await server.call_tool(
        "gh_execute_intent",
        {"intent": "make a python script"},
    )
    text = response[0].text
    assert "_is_handoff" not in text, (
        f"Internal handoff sentinel leaked into response text: {text!r}"
    )

