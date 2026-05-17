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


def _write_repo_executable(repo_root, script_id="extract-layers", code="print('{\"layers\": []}')\n"):
    artifact_dir = repo_root / "rhino" / script_id
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "script.py").write_text(code, encoding="utf-8", newline="\n")
    script_hash = script_library.compute_file_sha256(artifact_dir / "script.py")
    manifest = {
        "id": script_id,
        "version": "0.1.0",
        "description": "Extract layer names.",
        "tags": ["layers"],
        "trigger_phrases": ["list layers"],
        "state": "validated",
        "source": "repo",
        "domain": "rhino",
        "entrypoint": "script.py",
        "execution": "run_as_is",
        "mutation": "read_only",
        "content_hash": script_hash,
        "parameters_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "output_schema": {
            "type": "object",
            "required": ["layers"],
            "properties": {"layers": {"type": "array"}},
        },
        "requires": {"rhino": "8", "rook_capabilities": ["rhino_execute"]},
        "safety": {"static_scan": "passed", "blocking_ui": "none", "network": "none", "filesystem": "none"},
        "evidence": {"validated_at": "2026-05-17", "validation_method": "bootstrap_unit_fixture"},
    }
    (artifact_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    lock = {
        "version": 1,
        "artifacts": {
            f"repo:rhino:{script_id}:0.1.0": {
                "content_hash": script_hash,
                "static_scan": {"status": "passed", "content_hash": script_hash},
            }
        },
    }
    (repo_root / "rook-library.lock.json").write_text(json.dumps(lock), encoding="utf-8")
    return artifact_dir


@pytest.mark.asyncio
async def test_run_library_script_refuses_project_source(monkeypatch, tmp_path):
    project_root = tmp_path / ".rook" / "scripts"
    artifact_dir = project_root / "captured-audit"
    artifact_dir.mkdir(parents=True)
    manifest = {
        "id": "captured-audit",
        "version": "0.1.0",
        "description": "Captured audit.",
        "state": "captured",
        "source": "project",
        "domain": "rhino",
        "entrypoint": "script.py",
        "execution": "adapt_and_run",
        "mutation": "read_only",
        "content_hash": "sha256:captured",
        "parameters_schema": {},
        "output_schema": {},
        "requires": {},
        "safety": {},
        "evidence": {},
    }
    (artifact_dir / "script.py").write_text("print('{}')\n", encoding="utf-8")
    (artifact_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    async def fail_call_rhino(*args, **kwargs):
        raise AssertionError("run_library_script must not call Rhino for project artifacts")

    payload = await script_library.run_library_script(
        script_id="captured-audit",
        source="project",
        parameters={},
        expected_mutation="read_only",
        call_rhino_func=fail_call_rhino,
        repo_library_root=tmp_path / "scripts" / "rook-library",
        project_scripts_root=project_root,
    )

    assert payload["success"] is False
    assert payload["verified"] is False
    assert payload["refusal_reason"] == "project_source_not_executable_in_v1"


@pytest.mark.asyncio
async def test_run_library_script_executes_repo_validated_read_only_script(monkeypatch, tmp_path):
    repo_root = tmp_path / "scripts" / "rook-library"
    _write_repo_executable(repo_root)
    calls = []

    async def fake_call_rhino(path, method="GET", payload=None, **kwargs):
        calls.append((path, method, payload))
        assert path == "/execute"
        assert method == "POST"
        assert "ROOK_LIBRARY_PARAMETERS" in payload["code"]
        return {
            "success": True,
            "data": {
                "output": "{\"layers\": []}\n",
                "stderr": "",
                "objectsCreated": 0,
                "objectIds": [],
                "objectCount": 3,
            },
        }

    payload = await script_library.run_library_script(
        script_id="extract-layers",
        source="repo",
        parameters={},
        expected_mutation="read_only",
        call_rhino_func=fake_call_rhino,
        repo_library_root=repo_root,
        project_scripts_root=None,
    )

    assert payload["success"] is True
    assert payload["verified"] is True
    assert payload["validated_output"] == {"layers": []}
    assert payload["mutation"] == "read_only"
    assert payload["policy_decision"]["allowed"] is True
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_run_library_script_validates_parameters_before_execution(tmp_path):
    repo_root = tmp_path / "scripts" / "rook-library"
    _write_repo_executable(repo_root)

    async def fail_call_rhino(*args, **kwargs):
        raise AssertionError("run_library_script must validate parameters before calling Rhino")

    payload = await script_library.run_library_script(
        script_id="extract-layers",
        source="repo",
        parameters={"unexpected": True},
        expected_mutation="read_only",
        call_rhino_func=fail_call_rhino,
        repo_library_root=repo_root,
        project_scripts_root=None,
    )

    assert payload["success"] is False
    assert payload["verified"] is False
    assert payload["refusal_reason"] == "parameters_schema_validation_failed"


@pytest.mark.asyncio
async def test_run_library_script_rejects_falsey_non_dict_parameters_before_execution(tmp_path):
    repo_root = tmp_path / "scripts" / "rook-library"
    _write_repo_executable(repo_root)

    async def fail_call_rhino(*args, **kwargs):
        raise AssertionError("run_library_script must validate non-dict parameters before calling Rhino")

    payload = await script_library.run_library_script(
        script_id="extract-layers",
        source="repo",
        parameters=[],
        expected_mutation="read_only",
        call_rhino_func=fail_call_rhino,
        repo_library_root=repo_root,
        project_scripts_root=None,
    )

    assert payload["success"] is False
    assert payload["verified"] is False
    assert payload["refusal_reason"] == "parameters_schema_validation_failed"


@pytest.mark.asyncio
async def test_run_library_script_rejects_mutation_before_execution(tmp_path):
    repo_root = tmp_path / "scripts" / "rook-library"
    code = "import rhinoscriptsyntax as rs\nrs.AddPoint(0, 0, 0)\nprint('{\"layers\": []}')\n"
    _write_repo_executable(repo_root, code=code)

    async def fail_call_rhino(*args, **kwargs):
        raise AssertionError("run_library_script must reject mutation scripts before calling Rhino")

    payload = await script_library.run_library_script(
        script_id="extract-layers",
        source="repo",
        parameters={},
        expected_mutation="read_only",
        call_rhino_func=fail_call_rhino,
        repo_library_root=repo_root,
        project_scripts_root=None,
    )

    assert payload["success"] is False
    assert payload["verified"] is False
    assert payload["refusal_reason"] == "failed_static_scan"


@pytest.mark.asyncio
async def test_run_library_script_treats_output_schema_failure_as_failed(tmp_path):
    repo_root = tmp_path / "scripts" / "rook-library"
    _write_repo_executable(repo_root)

    async def fake_call_rhino(path, method="GET", payload=None, **kwargs):
        return {"success": True, "data": {"output": "{\"wrong\": []}\n", "objectsCreated": 0, "objectIds": []}}

    payload = await script_library.run_library_script(
        script_id="extract-layers",
        source="repo",
        parameters={},
        expected_mutation="read_only",
        call_rhino_func=fake_call_rhino,
        repo_library_root=repo_root,
        project_scripts_root=None,
    )

    assert payload["success"] is False
    assert payload["verified"] is False
    assert payload["refusal_reason"] == "output_schema_validation_failed"
