import json

import pytest

from rook import script_library
from rook import server
from rook import targeting


def _decode_response(response):
    text = response[0].text
    if text.startswith("Error: "):
        return json.loads(text[len("Error: "):])
    return json.loads(text)


@pytest.mark.asyncio
async def test_script_library_search_tool_returns_executable_and_refusal_reason(monkeypatch):
    def fake_search_scripts(**kwargs):
        return {
            "success": True,
            "query": kwargs.get("query"),
            "results": [
                {
                    "id": "extract-layers",
                    "version": "0.1.0",
                    "description": "Extract layer names.",
                    "source": "repo",
                    "domain": "rhino",
                    "state": "validated",
                    "execution": "run_as_is",
                    "mutation": "read_only",
                    "executable": True,
                    "refusal_reason": None,
                },
                {
                    "id": "captured-audit",
                    "version": "0.1.0",
                    "description": "Captured audit.",
                    "source": "project",
                    "domain": "rhino",
                    "state": "captured",
                    "execution": "adapt_and_run",
                    "mutation": "read_only",
                    "executable": False,
                    "refusal_reason": "project_source_not_executable_in_v1",
                },
            ],
        }

    monkeypatch.setattr(script_library, "search_scripts", fake_search_scripts)

    response = await server.call_tool("script_library_search", {"query": "layers"})
    payload = _decode_response(response)

    assert payload["success"] is True
    assert payload["results"][0]["executable"] is True
    assert payload["results"][1]["refusal_reason"] == "project_source_not_executable_in_v1"


@pytest.mark.asyncio
async def test_capture_script_artifact_tool_writes_captured_artifact(monkeypatch, tmp_path):
    captured = {}

    def fake_capture_script_artifact(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "id": kwargs["script_id"],
            "state": "captured",
            "source": "project",
            "executable": False,
            "refusal_reason": "project_source_not_executable_in_v1",
        }

    monkeypatch.setattr(script_library, "capture_script_artifact", fake_capture_script_artifact)

    response = await server.call_tool(
        "capture_script_artifact",
        {
            "id": "audit-layer-names",
            "script_source": "print('{}')\n",
            "description": "Captured layer audit.",
            "session_id": "session-123",
        },
    )
    payload = _decode_response(response)

    assert payload["success"] is True
    assert captured["script_id"] == "audit-layer-names"
    assert captured["script_source"] == "print('{}')\n"
    assert captured["session_id"] == "session-123"


def test_script_library_tools_have_explicit_targeting_policy():
    assert targeting.policy_for_tool("script_library_search") == targeting.RhinoToolPolicy(False, "read")
    assert targeting.policy_for_tool("capture_script_artifact") == targeting.RhinoToolPolicy(False, "mutate")
    assert targeting.policy_for_tool("run_library_script") == targeting.RhinoToolPolicy(True, "read")
