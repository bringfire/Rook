import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from rook import server


class _DummyPhaseTracker:
    def record_call(self, _name: str) -> None:
        pass


def _decode_response(response):
    text = response[0].text
    if text.startswith("Error: "):
        return {"success": False, "data": text[len("Error: "):]}
    return {"success": True, "data": json.loads(text)}


@pytest.fixture
def patched_server(monkeypatch):
    monkeypatch.setattr(server, "should_inject", lambda _name, _result: False)
    monkeypatch.setattr(server, "_record_observation", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "get_phase_tracker", lambda: _DummyPhaseTracker())


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
                    "access": "list",
                    "optional": False,
                    "description": "All values",
                }],
                "outputs": [{
                    "name": "Sum",
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
async def test_gh_create_python_script_accepts_rich_pin_objects(monkeypatch, patched_server):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/create-component":
            return {"success": True, "data": {"guid": "py-script-guid"}}
        if route == "/gh/script-params":
            assert payload == {
                "guid": "py-script-guid",
                "inputs": [{
                    "name": "Pts",
                    "access": "list",
                    "optional": False,
                    "description": "Input points",
                }],
                "outputs": [{
                    "name": "Result",
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
            "current_name": "Curves",
            "nick": "Crv",
            "access": "list",
            "optional": False,
            "description": "All input curves",
            "hidden": False,
        }],
        "outputs": [{
            "name": "JoinedResult",
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
                    "access": "tree",
                    "optional": False,
                    "description": "Tree of brief fragments",
                }],
                "outputs": [{
                    "name": "Span",
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
