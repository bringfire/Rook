from __future__ import annotations

import json
import os
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
    run_kwargs = []

    class Completed:
        returncode = 0
        stdout = json.dumps(
            {
                "chirp_file": str(
                    chirp_root / ".venv" / "Lib" / "site-packages" / "chirp" / "__init__.py"
                ),
                "dspy_cache": {
                    "restrict_pickle": True,
                    "disk_cache_dir": str(chirp_root / "data" / "dspy-cache"),
                },
            }
        )
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append(command)
        run_kwargs.append(kwargs)
        return Completed()

    monkeypatch.setattr(proof.subprocess, "run", fake_run)
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "source-shadow"))
    monkeypatch.setenv("PYTHONHOME", str(tmp_path / "bad-pythonhome"))

    details = proof.verify_chirp_runtime(chirp_root)

    assert calls[0][0] == str(chirp_python)
    assert run_kwargs[0]["env"]["CHIRP_DSPY_RESTRICT_PICKLE"] == "1"
    assert "PYTHONPATH" not in run_kwargs[0]["env"]
    assert "PYTHONHOME" not in run_kwargs[0]["env"]
    assert details["chirp_file"].replace("\\", "/").endswith("site-packages/chirp/__init__.py")
    assert details["chirp_dspy_cache"]["restrict_pickle"] is True


def test_verify_chirp_runtime_rejects_source_import_under_chirp_home(monkeypatch, tmp_path: Path):
    chirp_root = tmp_path / "Rook" / "app" / "chirp"
    chirp_python = chirp_root / ".venv" / "Scripts" / "python.exe"
    chirp_python.parent.mkdir(parents=True)
    chirp_python.write_text("fake", encoding="utf-8")

    class Completed:
        returncode = 0
        stdout = json.dumps(
            {
                "chirp_file": str(chirp_root / "src" / "chirp" / "__init__.py"),
                "dspy_cache": {
                    "restrict_pickle": True,
                    "disk_cache_dir": str(chirp_root / "data" / "dspy-cache"),
                },
            }
        )
        stderr = ""

    monkeypatch.setattr(proof.subprocess, "run", lambda *args, **kwargs: Completed())

    with pytest.raises(proof.ProofFailure) as exc:
        proof.verify_chirp_runtime(chirp_root)

    assert exc.value.failure_label == "chirp_import_leakage"


def test_load_codex_toml_fallback_parses_rook_entry(monkeypatch):
    text = """
[mcp_servers.rook]
command = "C:/Users/aryan/AppData/Local/Rook/venv/Scripts/python.exe"
args = ["-m", "rook"]
cwd = "C:/Users/aryan/AppData/Local/Rook/app/mcp_server"

[mcp_servers.rook.env]
ROOK_INSTALL_ROOT = "C:/Users/aryan/AppData/Local/Rook/app"
ROOK_DATA_DIR = "C:/Users/aryan/AppData/Local/Rook/data"
ROOK_MODE = "release"
PYTHONHOME = ""
PYTHONPATH = ""
DSPY_CACHEDIR = "C:/Users/aryan/AppData/Local/Rook/data/dspy-cache"
ROOK_DSPY_RESTRICT_PICKLE = "1"
CHIRP_HOME = "C:/Users/aryan/AppData/Local/Rook/app/chirp"
"""
    monkeypatch.setattr(proof, "tomllib", None)

    payload = proof._load_codex_toml(text)
    entry = payload["mcp_servers"]["rook"]

    assert entry["command"].endswith("python.exe")
    assert entry["args"] == ["-m", "rook"]
    assert entry["cwd"].endswith("mcp_server")
    assert entry["env"]["ROOK_MODE"] == "release"
    assert entry["env"]["CHIRP_HOME"].endswith("/chirp")


def test_verify_mcp_entry_rejects_repo_cwd(tmp_path: Path):
    entry = {
        "command": str(tmp_path / "Rook" / "venv" / "Scripts" / "python.exe"),
        "args": ["-m", "rook"],
        "cwd": str(tmp_path / "source" / "repos" / "Rook" / "mcp_server"),
        "env": {
            "ROOK_INSTALL_ROOT": str(tmp_path / "Rook" / "app"),
            "ROOK_DATA_DIR": str(tmp_path / "Rook" / "data"),
            "ROOK_MODE": "release",
            "PYTHONHOME": "",
            "PYTHONPATH": "",
            "DSPY_CACHEDIR": str(tmp_path / "Rook" / "data" / "dspy-cache"),
            "ROOK_DSPY_RESTRICT_PICKLE": "1",
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
PYTHONHOME = ""
PYTHONPATH = ""
DSPY_CACHEDIR = "{toml_path(data_root / "dspy-cache")}"
ROOK_DSPY_RESTRICT_PICKLE = "1"
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


def test_verify_effective_configs_ignores_unrelated_empty_claude_when_codex_is_valid(
    monkeypatch, tmp_path: Path
):
    home = tmp_path / "home"
    appdata = tmp_path / "AppData" / "Roaming"
    rook_root = tmp_path / "Rook"
    install_root = rook_root / "app"
    data_root = rook_root / "data"
    chirp_home = install_root / "chirp"
    venv_python = rook_root / "venv" / "Scripts" / "python.exe"
    plugin_dir = appdata / "McNeel" / "Rhinoceros" / "8.0" / "Plug-ins" / "RookNative"

    home.mkdir()
    (home / ".claude.json").write_text('{"mcpServers": {}}', encoding="utf-8")
    codex_config = home / ".codex" / "config.toml"
    codex_config.parent.mkdir()
    plugin_dir.mkdir(parents=True)

    def toml_path(path: Path) -> str:
        return str(path).replace("\\", "\\\\")

    codex_config.write_text(
        f'''
[mcp_servers.rook]
command = "{toml_path(venv_python)}"
args = ["-m", "rook"]
cwd = "{toml_path(install_root / "mcp_server")}"

[mcp_servers.rook.env]
ROOK_INSTALL_ROOT = "{toml_path(install_root)}"
ROOK_DATA_DIR = "{toml_path(data_root)}"
ROOK_MODE = "release"
PYTHONHOME = ""
PYTHONPATH = ""
DSPY_CACHEDIR = "{toml_path(data_root / "dspy-cache")}"
ROOK_DSPY_RESTRICT_PICKLE = "1"
CHIRP_HOME = "{toml_path(chirp_home)}"
''',
        encoding="utf-8",
    )
    (plugin_dir / "RookChatService.json").write_text(
        json.dumps(
            {
                "pythonPath": str(venv_python),
                "workingDirectory": str(install_root / "mcp_server"),
                "module": "rook.agent.chat.service_main",
                "pythonPathEntries": [],
                "environment": {
                    "ROOK_INSTALL_ROOT": str(install_root),
                    "ROOK_DATA_DIR": str(data_root),
                    "ROOK_MODE": "release",
                    "PYTHONHOME": "",
                    "PYTHONPATH": "",
                    "DSPY_CACHEDIR": str(data_root / "dspy-cache"),
                    "ROOK_DSPY_RESTRICT_PICKLE": "1",
                    "CHIRP_HOME": str(chirp_home),
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setattr(proof.Path, "home", classmethod(lambda cls: home))

    details = proof.verify_effective_configs(
        paths=SimpleNamespace(install_root=install_root, data_root=data_root),
        venv_python=venv_python,
        chirp_home=chirp_home,
    )

    assert str(codex_config) in details["mcp_configs"]
    assert details["mcp_config_warnings"][0]["path"] == str(home / ".claude.json")
    assert details["mcp_config_warnings"][0]["failure_label"] == "mcp_config_missing"
    assert details["chat_manifest"]["python_path"] == str(venv_python)


def test_verify_effective_configs_fails_when_no_mcp_config_is_valid(
    monkeypatch, tmp_path: Path
):
    home = tmp_path / "home"
    appdata = tmp_path / "AppData" / "Roaming"
    rook_root = tmp_path / "Rook"
    install_root = rook_root / "app"
    data_root = rook_root / "data"
    chirp_home = install_root / "chirp"
    venv_python = rook_root / "venv" / "Scripts" / "python.exe"
    plugin_dir = appdata / "McNeel" / "Rhinoceros" / "8.0" / "Plug-ins" / "RookNative"

    home.mkdir()
    (home / ".claude.json").write_text('{"mcpServers": {}}', encoding="utf-8")
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "RookChatService.json").write_text(
        json.dumps(
            {
                "pythonPath": str(venv_python),
                "workingDirectory": str(install_root / "mcp_server"),
                "module": "rook.agent.chat.service_main",
                "pythonPathEntries": [],
                "environment": {
                    "ROOK_INSTALL_ROOT": str(install_root),
                    "ROOK_DATA_DIR": str(data_root),
                    "ROOK_MODE": "release",
                    "PYTHONHOME": "",
                    "PYTHONPATH": "",
                    "DSPY_CACHEDIR": str(data_root / "dspy-cache"),
                    "ROOK_DSPY_RESTRICT_PICKLE": "1",
                    "CHIRP_HOME": str(chirp_home),
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setattr(proof.Path, "home", classmethod(lambda cls: home))

    with pytest.raises(proof.ProofFailure) as exc:
        proof.verify_effective_configs(
            paths=SimpleNamespace(install_root=install_root, data_root=data_root),
            venv_python=venv_python,
            chirp_home=chirp_home,
        )

    assert exc.value.failure_label == "mcp_config_missing"
    assert exc.value.details["mcp_config_warnings"][0]["path"] == str(home / ".claude.json")


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


def test_verify_chat_manifest_accepts_release_contract(tmp_path: Path):
    rook_root = tmp_path / "Rook"
    install_root = rook_root / "app"
    data_root = rook_root / "data"
    plugin_dir = tmp_path / "RookNative"
    plugin_dir.mkdir()
    venv_python = rook_root / "venv" / "Scripts" / "python.exe"
    manifest = {
        "pythonPath": str(venv_python),
        "workingDirectory": str(install_root / "mcp_server"),
        "module": "rook.agent.chat.service_main",
        "pythonPathEntries": [],
        "environment": {
            "ROOK_INSTALL_ROOT": str(install_root),
            "ROOK_DATA_DIR": str(data_root),
            "ROOK_MODE": "release",
            "PYTHONHOME": "",
            "PYTHONPATH": "",
            "DSPY_CACHEDIR": str(data_root / "dspy-cache"),
            "ROOK_DSPY_RESTRICT_PICKLE": "1",
            "CHIRP_HOME": str(install_root / "chirp"),
        },
    }
    (plugin_dir / "RookChatService.json").write_text(json.dumps(manifest), encoding="utf-8")

    details = proof.verify_chat_manifest(
        plugin_dir=plugin_dir,
        venv_python=venv_python,
        install_root=install_root,
    )

    assert details["release_pythonpath_entries"] is False
    assert details["python_path"] == str(venv_python)
    assert details["chirp_home"] == str(install_root / "chirp")


def test_build_release_smoke_python_evidence_uses_installed_runtime_facts(
    monkeypatch, tmp_path: Path
):
    rook_root = tmp_path / "Rook"
    install_root = rook_root / "app"
    data_root = rook_root / "data"
    venv_python = rook_root / "venv" / "Scripts" / "python.exe"
    venv_python.parent.mkdir(parents=True)
    runtime_manifest = {
        "chirp_git_sha": "a" * 40,
        "chirp_source_archive_sha256": "b" * 64,
    }
    install_root.mkdir(parents=True)
    data_root.mkdir(parents=True)
    (install_root / "python-runtime-manifest.json").write_text(
        json.dumps(runtime_manifest),
        encoding="utf-8",
    )
    (data_root / "install-state.json").write_text(
        json.dumps(
            {
                "rook": {"pip_check": "No broken requirements found."},
                "chirp": {"pip_check": "No broken requirements found."},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        proof,
        "resolve_runtime_paths",
        lambda: SimpleNamespace(
            install_root=install_root,
            data_root=data_root,
            runtime_root=rook_root,
        ),
    )
    monkeypatch.setattr(proof.sys, "executable", str(venv_python))

    evidence = proof.build_release_smoke_python_evidence(
        {
            "rook_file": str(rook_root / "venv" / "Lib" / "site-packages" / "rook" / "__init__.py"),
            "chirp_file": str(
                install_root / "chirp" / ".venv" / "Lib" / "site-packages" / "chirp" / "__init__.py"
            ),
            "rook_dspy_cache": {
                "restrict_pickle": True,
                "disk_cache_dir": str(data_root / "dspy-cache"),
            },
            "chirp_dspy_cache": {
                "restrict_pickle": True,
                "disk_cache_dir": str(install_root / "chirp" / "data" / "dspy-cache"),
            },
            "chat_manifest": {
                "python_path": str(venv_python),
                "chirp_home": str(install_root / "chirp"),
                "release_pythonpath_entries": False,
            },
        }
    )

    assert evidence["python_runtime_manifest"] == str(install_root / "python-runtime-manifest.json")
    assert evidence["install_state"] == str(data_root / "install-state.json")
    assert evidence["rook_venv_path"] == str(rook_root / "venv")
    assert evidence["chirp_venv_path"] == str(install_root / "chirp" / ".venv")
    assert evidence["pip_check"]["rook"]["ok"] is True
    assert evidence["pip_check"]["chirp"]["ok"] is True
    assert evidence["rook_dspy_cache"]["restrict_pickle"] is True
    assert evidence["config_identity"]["chat_service_python_path"] == str(venv_python)
    assert evidence["config_identity"]["release_pythonpath_entries"] is False
    assert evidence["no_index_install"] is True
    assert evidence["chirp_git_sha"] == "a" * 40


def test_python_smoke_evidence_seeds_release_env_from_installed_venv(
    monkeypatch, tmp_path: Path
):
    local_appdata = tmp_path / "AppData" / "Local"
    rook_root = local_appdata / "Rook"
    (rook_root / "app" / "mcp_server").mkdir(parents=True)
    venv_python = rook_root / "venv" / "Scripts" / "python.exe"
    venv_python.parent.mkdir(parents=True)
    monkeypatch.setattr(proof.sys, "executable", str(venv_python))
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
    for key in (
        "ROOK_INSTALL_ROOT",
        "ROOK_DATA_DIR",
        "ROOK_MODE",
        "CHIRP_HOME",
        "DSPY_CACHEDIR",
        "ROOK_DSPY_RESTRICT_PICKLE",
        "PYTHONPATH",
        "PYTHONHOME",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "shadow-src"))
    monkeypatch.setenv("PYTHONHOME", str(tmp_path / "shadow-python"))

    seeded = proof.seed_release_env_from_installed_venv()

    assert seeded is True
    assert os.environ["ROOK_INSTALL_ROOT"] == str(rook_root / "app")
    assert os.environ["ROOK_DATA_DIR"] == str(rook_root / "data")
    assert os.environ["ROOK_MODE"] == "release"
    assert os.environ["CHIRP_HOME"] == str(rook_root / "app" / "chirp")
    assert os.environ["DSPY_CACHEDIR"] == str(rook_root / "data" / "dspy-cache")
    assert os.environ["ROOK_DSPY_RESTRICT_PICKLE"] == "1"
    assert os.environ["PYTHONPATH"] == ""
    assert os.environ["PYTHONHOME"] == ""


def test_python_smoke_evidence_seeds_legacy_release_root_from_installed_venv(
    monkeypatch, tmp_path: Path
):
    local_appdata = tmp_path / "AppData" / "Local"
    rook_root = local_appdata / "Rook"
    (rook_root / "mcp_server").mkdir(parents=True)
    (rook_root / "app" / "chirp" / "src" / "chirp").mkdir(parents=True)
    venv_python = rook_root / "venv" / "Scripts" / "python.exe"
    venv_python.parent.mkdir(parents=True)
    monkeypatch.setattr(proof.sys, "executable", str(venv_python))
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
    for key in (
        "ROOK_INSTALL_ROOT",
        "ROOK_DATA_DIR",
        "ROOK_MODE",
        "CHIRP_HOME",
        "DSPY_CACHEDIR",
        "ROOK_DSPY_RESTRICT_PICKLE",
        "PYTHONPATH",
        "PYTHONHOME",
    ):
        monkeypatch.delenv(key, raising=False)

    seeded = proof.seed_release_env_from_installed_venv()

    assert seeded is True
    assert os.environ["ROOK_INSTALL_ROOT"] == str(rook_root)
    assert os.environ["ROOK_DATA_DIR"] == str(rook_root / "data")
    assert os.environ["CHIRP_HOME"] == str(rook_root / "chirp")
    assert os.environ["DSPY_CACHEDIR"] == str(rook_root / "data" / "dspy-cache")
    assert os.environ["PYTHONPATH"] == ""
    assert os.environ["PYTHONHOME"] == ""


def test_python_smoke_evidence_seed_ignores_non_localappdata_venv(
    monkeypatch, tmp_path: Path
):
    dev_root = tmp_path / "Rook-bundled-python"
    dev_python = dev_root / "venv" / "Scripts" / "python.exe"
    dev_python.parent.mkdir(parents=True)
    monkeypatch.setattr(proof.sys, "executable", str(dev_python))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    monkeypatch.setenv("ROOK_MODE", "dev")
    monkeypatch.setenv("ROOK_INSTALL_ROOT", str(dev_root))
    monkeypatch.setenv("PYTHONPATH", str(dev_root / "mcp_server" / "src"))

    seeded = proof.seed_release_env_from_installed_venv()

    assert seeded is False
    assert os.environ["ROOK_MODE"] == "dev"
    assert os.environ["ROOK_INSTALL_ROOT"] == str(dev_root)
    assert os.environ["PYTHONPATH"] == str(dev_root / "mcp_server" / "src")


def test_python_smoke_evidence_seed_preserves_explicit_release_env(
    monkeypatch, tmp_path: Path
):
    rook_root = tmp_path / "AppData" / "Local" / "Rook"
    venv_python = rook_root / "venv" / "Scripts" / "python.exe"
    explicit_data = tmp_path / "explicit-data"
    venv_python.parent.mkdir(parents=True)
    monkeypatch.setattr(proof.sys, "executable", str(venv_python))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    for key in (
        "ROOK_INSTALL_ROOT",
        "ROOK_MODE",
        "CHIRP_HOME",
        "DSPY_CACHEDIR",
        "ROOK_DSPY_RESTRICT_PICKLE",
        "PYTHONPATH",
        "PYTHONHOME",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ROOK_DATA_DIR", str(explicit_data))

    seeded = proof.seed_release_env_from_installed_venv()

    assert seeded is True
    assert os.environ["ROOK_DATA_DIR"] == str(explicit_data)
    assert os.environ["ROOK_INSTALL_ROOT"] == str(rook_root / "app")


def test_verify_command_knowledge_runtime_requires_grasshopper_preflight(monkeypatch):
    class FakeStore:
        def layering_diagnostics(self):
            return {
                "bundled_path": "C:/Rook/app/knowledge/commands/command_knowledge.json",
                "mutable_path": "C:/Rook/data/commands/command_knowledge.json",
                "effective_count": 2,
                "bundled_count": 1,
                "mutable_only_count": 1,
            }

        def get_command_source(self, command):
            return "bundled" if command == "-Grasshopper" else "missing"

    monkeypatch.setattr(proof, "CommandKnowledgeStore", FakeStore, raising=False)
    monkeypatch.setattr(proof, "preflight_rhino_command", lambda command, store: None, raising=False)

    details = proof.verify_command_knowledge_runtime()

    assert details["grasshopper_preflight"] == "passed"
    assert details["grasshopper_source"] == "bundled"
    assert details["command_knowledge"]["effective_count"] == 2


def test_verify_command_knowledge_runtime_rejects_shadowed_grasshopper(monkeypatch):
    class FakeStore:
        def layering_diagnostics(self):
            return {"effective_count": 1}

        def get_command_source(self, command):
            return "mutable" if command == "-Grasshopper" else "missing"

    monkeypatch.setattr(proof, "CommandKnowledgeStore", FakeStore, raising=False)
    monkeypatch.setattr(
        proof,
        "preflight_rhino_command",
        lambda command, store: {"success": False, "data": {"error": "run_script_safety_refusal"}},
        raising=False,
    )

    with pytest.raises(proof.ProofFailure) as exc:
        proof.verify_command_knowledge_runtime()

    assert exc.value.failure_label == "command_knowledge_stale"


def test_verify_command_knowledge_runtime_rejects_mutable_only_grasshopper_even_if_preflight_passes(monkeypatch):
    class FakeStore:
        def layering_diagnostics(self):
            return {"effective_count": 1, "bundled_count": 0, "mutable_only_count": 1}

        def get_command_source(self, command):
            return "mutable" if command == "-Grasshopper" else "missing"

    monkeypatch.setattr(proof, "CommandKnowledgeStore", FakeStore, raising=False)
    monkeypatch.setattr(proof, "preflight_rhino_command", lambda command, store: None, raising=False)

    with pytest.raises(proof.ProofFailure) as exc:
        proof.verify_command_knowledge_runtime()

    assert exc.value.failure_label == "command_knowledge_stale"
    assert exc.value.details["grasshopper_source"] == "mutable"


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


@pytest.mark.asyncio
async def test_live_smoke_launches_grasshopper_when_not_ready(monkeypatch):
    calls = []

    async def fake_dispatch(name: str, args: dict):
        calls.append((name, args))
        if name == "rhino_ping":
            return {"success": True, "data": {"processId": 42, "port": 9001}}
        if name == "gh_status":
            if any(call[0] == "gh_document_new" for call in calls):
                return {"success": True, "data": {"ready_for_edit": True}}
            return {"success": True, "data": {"available": False, "ready_for_edit": False}}
        if name == "rhino_command":
            return {"success": True, "data": {"command": args["command"]}}
        if name == "gh_document_new":
            return {"success": True, "data": {"documentName": "Untitled"}}
        if name == "chirp_create":
            return {"success": True, "data": {"component_guid": "abc", "compilation_errors": []}}
        if name == "gh_errors":
            return {"success": True, "data": {"errors": []}}
        if name == "gh_undo":
            return {"success": True, "data": {"undone": True}}
        raise AssertionError(name)

    monkeypatch.setattr(proof, "_call_tool_dispatch", fake_dispatch)

    result = await proof.run_live_smoke(port=9001, process_id=42)

    assert result["grasshopper_ready"]["opened"] is True
    assert any(name == "rhino_command" and args["command"] == "_Grasshopper" for name, args in calls)
    assert any(name == "gh_document_new" for name, _ in calls)
    chirp_call = next(args for name, args in calls if name == "chirp_create")
    assert chirp_call["deterministic_only"] is True


@pytest.mark.asyncio
async def test_live_smoke_polls_after_grasshopper_command_timeout(monkeypatch):
    calls = []

    async def fake_dispatch(name: str, args: dict):
        calls.append((name, args))
        if name == "rhino_ping":
            return {"success": True, "data": {"processId": 42, "port": 9001}}
        if name == "gh_status":
            if any(call[0] == "gh_document_new" for call in calls):
                return {"success": True, "data": {"ready_for_edit": True}}
            return {"success": True, "data": {"available": False, "ready_for_edit": False}}
        if name == "rhino_command":
            return {
                "success": False,
                "data": {
                    "code": "native_command_timeout",
                    "execution_may_have_occurred": True,
                    "state_uncertain": True,
                },
            }
        if name == "gh_document_new":
            return {"success": True, "data": {"documentName": "Untitled"}}
        if name == "chirp_create":
            return {"success": True, "data": {"component_guid": "abc", "compilation_errors": []}}
        if name == "gh_errors":
            return {"success": True, "data": {"errors": []}}
        if name == "gh_undo":
            return {"success": True, "data": {"undone": True}}
        raise AssertionError(name)

    monkeypatch.setattr(proof, "_call_tool_dispatch", fake_dispatch)

    async def fake_sleep(_seconds: float):
        return None

    monkeypatch.setattr(proof.asyncio, "sleep", fake_sleep)

    result = await proof.run_live_smoke(port=9001, process_id=42)

    assert result["grasshopper_ready"]["opened"] is True
    assert result["grasshopper_ready"]["rhino_command"]["data"]["code"] == "native_command_timeout"
    assert any(name == "gh_document_new" for name, _ in calls)


@pytest.mark.asyncio
async def test_live_smoke_rejects_grasshopper_timeout_without_uncertain_launch_flags(monkeypatch):
    async def fake_dispatch(name: str, args: dict):
        if name == "rhino_ping":
            return {"success": True, "data": {"processId": 42, "port": 9001}}
        if name == "gh_status":
            return {"success": True, "data": {"available": False, "ready_for_edit": False}}
        if name == "rhino_command":
            return {
                "success": False,
                "data": {
                    "code": "native_command_timeout",
                    "command": "_Grasshopper",
                },
            }
        raise AssertionError(name)

    monkeypatch.setattr(proof, "_call_tool_dispatch", fake_dispatch)

    with pytest.raises(proof.ProofFailure) as exc:
        await proof.run_live_smoke(port=9001, process_id=42)

    assert exc.value.failure_label == "gh_not_ready"
    assert exc.value.details["rhino_command"]["data"]["code"] == "native_command_timeout"


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


def test_owned_release_readiness_uses_installed_python_for_smoke(monkeypatch, tmp_path: Path):
    calls = {}

    class FakeHarnessResult:
        success = True
        artifact_dir = tmp_path / "run"
        cleanup_status = SimpleNamespace(value="graceful_exit")
        pid = 1234
        port = 9876
        warnings = []

        def to_manifest_dict(self):
            return {"success": True, "pid": self.pid, "port": self.port}

    def fake_run_harness(**kwargs):
        calls.update(kwargs)
        return FakeHarnessResult()

    monkeypatch.setattr(proof, "run_rhino_runtime_harness", fake_run_harness)

    result = proof.owned_release_readiness_gate(
        command=["python", "-m", "rook.local_testing_proof", "owned-release-readiness"],
        rhino_exe=Path("C:/Program Files/Rhino 8/System/Rhino.exe"),
        artifact_root=tmp_path,
        keep_rhino_on_failure=False,
        readiness_timeout_seconds=1.0,
        cleanup_timeout_seconds=1.0,
    )

    assert result.success is True
    assert calls["smoke_command"] == [sys.executable, "-m", "rook.local_testing_proof", "live-smoke"]
    assert calls["smoke_kind"] == "installed-live-smoke"
    assert calls["keep_rhino_on_failure"] is False


def test_owned_release_readiness_preserves_live_smoke_failure_label(monkeypatch, tmp_path: Path):
    class FakeSmoke:
        returncode = 1
        stdout = json.dumps(
            {
                "gate": "live_smoke",
                "success": False,
                "failure_label": "chirp_create_failed",
            }
        )
        stderr = ""

    class FakeHarnessResult:
        success = False
        cleanup_status = proof.CleanupStatus.GRACEFUL_EXIT
        smoke = FakeSmoke()

        def to_manifest_dict(self):
            return {"success": False, "smoke": {"stdout": self.smoke.stdout}}

    monkeypatch.setattr(proof, "run_rhino_runtime_harness", lambda **_: FakeHarnessResult())

    result = proof.owned_release_readiness_gate(
        command=["python", "-m", "rook.local_testing_proof", "owned-release-readiness"],
        rhino_exe=Path("C:/Program Files/Rhino 8/System/Rhino.exe"),
        artifact_root=tmp_path,
        keep_rhino_on_failure=False,
        readiness_timeout_seconds=1.0,
        cleanup_timeout_seconds=1.0,
    )

    assert result.success is False
    assert result.failure_label == "chirp_create_failed"


def test_read_optional_json_tolerates_utf8_bom(tmp_path: Path):
    """Windows PowerShell `Set-Content -Encoding UTF8` writes the runtime manifest
    with a UTF-8 BOM. The reader must parse it; otherwise json.loads raises
    "Unexpected UTF-8 BOM", the gate swallows it to {}, and chirp_git_sha /
    chirp_source_archive_sha256 come back empty -> validate-release-artifacts
    fails the cross-check. Regression for the 1.5.12 release blocker."""
    manifest = tmp_path / "python-runtime-manifest.json"
    payload = {
        "chirp_git_sha": "c9ea6c0cf77cb06f9ce7c9e8c3bb8dd09f96d455",
        "chirp_source_archive_sha256": "CDD42532",
        "release_version": "1.5.12",
    }
    manifest.write_bytes(b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8"))

    data = proof._read_optional_json(manifest)

    assert data.get("chirp_git_sha") == "c9ea6c0cf77cb06f9ce7c9e8c3bb8dd09f96d455"
    assert data.get("chirp_source_archive_sha256") == "CDD42532"
    assert data.get("release_version") == "1.5.12"


def test_read_optional_json_still_reads_plain_utf8(tmp_path: Path):
    manifest = tmp_path / "plain.json"
    manifest.write_text(json.dumps({"chirp_git_sha": "abc123"}), encoding="utf-8")

    assert proof._read_optional_json(manifest).get("chirp_git_sha") == "abc123"
