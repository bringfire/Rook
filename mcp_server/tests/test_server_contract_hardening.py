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
