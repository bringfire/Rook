from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from rook import local_testing_proof as proof


def test_gate_result_envelope_contains_required_fields(tmp_path: Path):
    result = proof.GateResult.failure(
        gate="installed_runtime",
        failure_label="rook_import_leakage",
        command=["python", "-m", "rook.local_testing_proof", "installed-runtime"],
        started_at=10.0,
        ended_at=12.5,
        stdout_path=tmp_path / "stdout.log",
        stderr_path=tmp_path / "stderr.log",
        details={"rook_file": "C:/repo/mcp_server/src/rook/__init__.py"},
    )

    payload = result.to_dict()

    assert payload["gate"] == "installed_runtime"
    assert payload["success"] is False
    assert payload["failure_label"] == "rook_import_leakage"
    assert payload["command"] == ["python", "-m", "rook.local_testing_proof", "installed-runtime"]
    assert payload["duration_seconds"] == pytest.approx(2.5)
    assert payload["stdout_path"].endswith("stdout.log")
    assert payload["stderr_path"].endswith("stderr.log")
    assert payload["details"]["rook_file"].endswith("__init__.py")
    assert payload["cleanup"] == {
        "attempted": False,
        "success": None,
        "label": None,
        "details": {},
    }


def test_verify_path_under_rejects_repo_leakage(tmp_path: Path):
    expected_root = tmp_path / "AppData" / "Local" / "Rook" / "app" / "mcp_server" / "src" / "rook"
    repo_file = tmp_path / "source" / "repos" / "Rook" / "mcp_server" / "src" / "rook" / "__init__.py"

    with pytest.raises(proof.ProofFailure) as exc:
        proof.assert_path_under(repo_file, expected_root, "rook_import_leakage")

    assert exc.value.failure_label == "rook_import_leakage"


def test_verify_chirp_origin_rejects_non_appdata_path(tmp_path: Path):
    chirp_module = SimpleNamespace(__file__=str(tmp_path / "repos" / "Chirp" / "src" / "chirp" / "__init__.py"))

    with pytest.raises(proof.ProofFailure) as exc:
        proof.verify_chirp_origin(chirp_module, tmp_path / "Rook" / "app" / "chirp")

    assert exc.value.failure_label == "chirp_import_leakage"


def test_verify_chirp_runtime_uses_installed_chirp_venv(monkeypatch, tmp_path: Path):
    chirp_root = tmp_path / "Rook" / "app" / "chirp"
    chirp_python = chirp_root / ".venv" / "Scripts" / "python.exe"
    chirp_python.parent.mkdir(parents=True)
    chirp_python.write_text("fake", encoding="utf-8")
    calls = []

    class Completed:
        returncode = 0
        stdout = json.dumps({"chirp_file": str(chirp_root / "src" / "chirp" / "__init__.py")})
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append(command)
        return Completed()

    monkeypatch.setattr(proof.subprocess, "run", fake_run)

    details = proof.verify_chirp_runtime(chirp_root)

    assert calls[0][0] == str(chirp_python)
    assert details["chirp_file"].replace("\\", "/").endswith("src/chirp/__init__.py")


def test_verify_mcp_entry_rejects_repo_cwd(tmp_path: Path):
    entry = {
        "command": str(tmp_path / "Rook" / "venv" / "Scripts" / "python.exe"),
        "args": ["-m", "rook"],
        "cwd": str(tmp_path / "source" / "repos" / "Rook" / "mcp_server"),
        "env": {
            "ROOK_INSTALL_ROOT": str(tmp_path / "Rook" / "app"),
            "ROOK_DATA_DIR": str(tmp_path / "Rook" / "data"),
            "ROOK_MODE": "release",
            "CHIRP_HOME": str(tmp_path / "Rook" / "app" / "chirp"),
        },
    }

    with pytest.raises(proof.ProofFailure) as exc:
        proof.verify_mcp_entry(
            config_path=tmp_path / "config.json",
            entry=entry,
            venv_python=tmp_path / "Rook" / "venv" / "Scripts" / "python.exe",
            install_root=tmp_path / "Rook" / "app",
            data_root=tmp_path / "Rook" / "data",
            chirp_home=tmp_path / "Rook" / "app" / "chirp",
        )

    assert exc.value.failure_label == "mcp_config_stale"


def test_verify_codex_mcp_config_accepts_appdata_paths(tmp_path: Path):
    runtime = tmp_path / "Rook"
    install_root = runtime / "app"
    data_root = runtime / "data"
    chirp_home = install_root / "chirp"
    venv_python = runtime / "venv" / "Scripts" / "python.exe"
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir()

    def toml_path(path: Path) -> str:
        return str(path).replace("\\", "\\\\")

    config.write_text(
        f'''
[mcp_servers.rook]
command = "{toml_path(venv_python)}"
args = ["-m", "rook"]
cwd = "{toml_path(install_root / "mcp_server")}"

[mcp_servers.rook.env]
ROOK_INSTALL_ROOT = "{toml_path(install_root)}"
ROOK_DATA_DIR = "{toml_path(data_root)}"
ROOK_MODE = "release"
CHIRP_HOME = "{toml_path(chirp_home)}"
''',
        encoding="utf-8",
    )

    details = proof.verify_codex_mcp_config(
        config_path=config,
        venv_python=venv_python,
        install_root=install_root,
        data_root=data_root,
        chirp_home=chirp_home,
    )

    assert details["config_path"] == str(config)


def test_verify_chat_manifest_rejects_stale_python(tmp_path: Path):
    plugin_dir = tmp_path / "RookNative"
    plugin_dir.mkdir()
    manifest = {
        "pythonPath": str(tmp_path / "source" / "repos" / "Rook" / ".venv" / "Scripts" / "python.exe"),
        "workingDirectory": str(tmp_path / "Rook" / "app" / "mcp_server"),
        "module": "rook.agent.chat.service_main",
        "pythonPathEntries": [str(tmp_path / "Rook" / "app" / "mcp_server" / "src")],
    }
    (plugin_dir / "RookChatService.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(proof.ProofFailure) as exc:
        proof.verify_chat_manifest(
            plugin_dir=plugin_dir,
            venv_python=tmp_path / "Rook" / "venv" / "Scripts" / "python.exe",
            install_root=tmp_path / "Rook" / "app",
        )

    assert exc.value.failure_label == "chat_manifest_stale"


@pytest.mark.asyncio
async def test_live_smoke_rejects_chirp_warning(monkeypatch):
    calls = []

    async def fake_dispatch(name: str, args: dict):
        calls.append((name, args))
        if name == "rhino_ping":
            return {"success": True, "data": {"processId": 42, "port": 9001}}
        if name == "gh_status":
            return {"success": True, "data": {"ready": True}}
        if name == "chirp_create":
            return {
                "success": True,
                "data": {
                    "component_guid": "abc",
                    "warning": "compiled with warning",
                    "compilation_errors": [],
                },
            }
        raise AssertionError(name)

    monkeypatch.setattr(proof, "_call_tool_dispatch", fake_dispatch)

    with pytest.raises(proof.ProofFailure) as exc:
        await proof.run_live_smoke(port=9001, process_id=42)

    assert exc.value.failure_label == "chirp_component_warning"
    assert calls[0] == ("rhino_ping", {"port": 9001, "process_id": 42})


@pytest.mark.asyncio
async def test_live_smoke_requires_undo_success(monkeypatch):
    async def fake_dispatch(name: str, args: dict):
        if name == "rhino_ping":
            return {"success": True, "data": {"processId": 42, "port": 9001}}
        if name == "gh_status":
            return {"success": True, "data": {"ready": True}}
        if name == "chirp_create":
            return {"success": True, "data": {"component_guid": "abc", "compilation_errors": []}}
        if name == "gh_errors":
            return {"success": True, "data": {"errors": []}}
        if name == "gh_undo":
            return {"success": False, "data": "nothing to undo"}
        raise AssertionError(name)

    monkeypatch.setattr(proof, "_call_tool_dispatch", fake_dispatch)

    with pytest.raises(proof.ProofFailure) as exc:
        await proof.run_live_smoke(port=9001, process_id=42)

    assert exc.value.failure_label == "cleanup_failed"


@pytest.mark.asyncio
async def test_live_smoke_requires_component_guid(monkeypatch):
    async def fake_dispatch(name: str, args: dict):
        if name == "rhino_ping":
            return {"success": True, "data": {"processId": 42, "port": 9001}}
        if name == "gh_status":
            return {"success": True, "data": {"ready": True}}
        if name == "chirp_create":
            return {"success": True, "data": {"compilation_errors": []}}
        raise AssertionError(name)

    monkeypatch.setattr(proof, "_call_tool_dispatch", fake_dispatch)

    with pytest.raises(proof.ProofFailure) as exc:
        await proof.run_live_smoke(port=9001, process_id=42)

    assert exc.value.failure_label == "chirp_create_failed"


def test_write_json_writes_gate_envelope(tmp_path: Path):
    path = tmp_path / "gate.json"
    result = proof.GateResult.passed(
        gate="static_guard",
        command=["powershell", "-File", "scripts/tests/deploy-local-testing-guards.tests.ps1"],
        started_at=1.0,
        ended_at=2.0,
    )

    proof.write_json(path, result.to_dict())

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["gate"] == "static_guard"
    assert payload["success"] is True
    assert payload["failure_label"] is None
