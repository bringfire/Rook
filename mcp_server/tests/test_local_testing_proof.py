from __future__ import annotations

import asyncio
from contextlib import contextmanager
import json
import os
import sys
import threading
import time
import urllib.request
import uuid
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
command = "C:/Users/example/AppData/Local/Rook/venv/Scripts/python.exe"
args = ["-m", "rook"]
cwd = "C:/Users/example/AppData/Local/Rook/app/mcp_server"

[mcp_servers.rook.env]
ROOK_INSTALL_ROOT = "C:/Users/example/AppData/Local/Rook/app"
ROOK_DATA_DIR = "C:/Users/example/AppData/Local/Rook/data"
ROOK_MODE = "release"
PYTHONHOME = ""
PYTHONPATH = ""
DSPY_CACHEDIR = "C:/Users/example/AppData/Local/Rook/data/dspy-cache"
ROOK_DSPY_RESTRICT_PICKLE = "1"
CHIRP_HOME = "C:/Users/example/AppData/Local/Rook/app/chirp"
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
        monkeypatch.setenv(key, "test-placeholder")
        monkeypatch.delenv(key)
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
        monkeypatch.setenv(key, "test-placeholder")
        monkeypatch.delenv(key)
    monkeypatch.setenv("ROOK_DATA_DIR", str(explicit_data))

    seeded = proof.seed_release_env_from_installed_venv()

    assert seeded is True
    assert os.environ["ROOK_DATA_DIR"] == str(explicit_data)
    assert os.environ["ROOK_INSTALL_ROOT"] == str(rook_root / "app")


def test_installed_live_environment_overrides_source_chirp_home(monkeypatch, tmp_path: Path):
    local_appdata = tmp_path / "AppData" / "Local"
    rook_root = local_appdata / "Rook"
    venv_python = rook_root / "venv" / "Scripts" / "python.exe"
    chirp_home = rook_root / "app" / "chirp"
    (chirp_home / "src" / "chirp").mkdir(parents=True)
    (chirp_home / ".venv" / "Scripts").mkdir(parents=True)
    (chirp_home / ".venv" / "Scripts" / "python.exe").write_text("fake", encoding="utf-8")
    installed_module = rook_root / "venv" / "Lib" / "site-packages" / "rook" / "local_testing_proof.py"
    installed_module.parent.mkdir(parents=True)
    installed_module.write_text("# installed", encoding="utf-8")
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("fake", encoding="utf-8")

    monkeypatch.setattr(proof.sys, "executable", str(venv_python))
    monkeypatch.setattr(proof, "__file__", str(installed_module))
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
    monkeypatch.setenv("CHIRP_HOME", str(tmp_path / "source" / "Chirp"))
    monkeypatch.setenv("ROOK_INSTALL_ROOT", str(tmp_path / "source" / "Rook"))
    monkeypatch.setenv("ROOK_MODE", "dev")

    details = proof._require_installed_live_environment()

    assert details["chirp_home"] == str(chirp_home)
    assert os.environ["CHIRP_HOME"] == str(chirp_home)
    assert os.environ["ROOK_INSTALL_ROOT"] == str(rook_root / "app")
    assert os.environ["ROOK_DATA_DIR"] == str(rook_root / "data")
    assert os.environ["ROOK_MODE"] == "release"


def test_installed_live_environment_rejects_source_shadowing(monkeypatch, tmp_path: Path):
    local_appdata = tmp_path / "AppData" / "Local"
    rook_root = local_appdata / "Rook"
    venv_python = rook_root / "venv" / "Scripts" / "python.exe"
    chirp_home = rook_root / "app" / "chirp"
    (chirp_home / "src" / "chirp").mkdir(parents=True)
    (chirp_home / ".venv" / "Scripts").mkdir(parents=True)
    (chirp_home / ".venv" / "Scripts" / "python.exe").write_text("fake", encoding="utf-8")
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("fake", encoding="utf-8")

    monkeypatch.setattr(proof.sys, "executable", str(venv_python))
    monkeypatch.setattr(proof, "__file__", str(tmp_path / "source" / "rook" / "local_testing_proof.py"))
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))

    with pytest.raises(proof.ProofFailure) as exc:
        proof._require_installed_live_environment()

    assert exc.value.failure_label == "rook_import_leakage"


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


async def _async_value(value):
    return value


def _gh_undo_success() -> dict:
    return {
        "success": True,
        "data": {
            "message": "Undo successful",
            "snapshot": {
                # This is a stable component TYPE GUID, not an instance GUID.
                # Cleanup must ignore it and use the debug inventory instead.
                "components": [{"componentGuid": "stable-type-guid"}],
                "diagnostics": {"total": 1},
            },
        },
    }


def _gh_status_response(object_count: int) -> dict:
    return {
        "success": True,
        "data": {"ready": True, "ready_for_edit": True, "object_count": object_count},
    }


_TEST_GUID_NAMESPACE = uuid.UUID("8fc4bb29-66b2-41c3-bc42-9f5d94477063")
_UNSET = object()


def _test_guid(label: str) -> str:
    return str(uuid.uuid5(_TEST_GUID_NAMESPACE, label))


def _guid_or_label(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return _test_guid(value)


def _debug_inventory_response(*instance_guids: str) -> dict:
    normalized = [_guid_or_label(guid) for guid in instance_guids]
    return {
        "success": True,
        "data": {
            "totalComponents": len(normalized),
            "debugInfo": [{"guid": guid} for guid in normalized],
        },
    }


class _LiveSmokeHarness:
    def __init__(
        self,
        *,
        inventories: list[object],
        status_responses: list[object] | None = None,
        chirp_response: object | BaseException = _UNSET,
        errors_response: object | BaseException = _UNSET,
        undo_responses: list[object] | None = None,
    ) -> None:
        self.inventories = list(inventories)
        if status_responses is None:
            counts = [inventory["data"]["totalComponents"] for inventory in inventories]
            status_responses = [
                _gh_status_response(counts[0]),
                *[_gh_status_response(count) for count in counts],
            ]
        self.status_responses = list(status_responses)
        self.chirp_response = (
            {
                "success": True,
                "data": {
                    "component_guid": _test_guid("abc"),
                    "component_errors": [],
                },
            }
            if chirp_response is _UNSET
            else chirp_response
        )
        self.errors_response = (
            {"success": True, "data": {"errors": []}}
            if errors_response is _UNSET
            else errors_response
        )
        self.undo_responses = list(undo_responses or [])
        self.status_index = 0
        self.inventory_index = 0
        self.undo_calls = 0
        self.chirp_calls = 0
        self.events: list[str] = []

    async def dispatch(self, name: str, _args: dict) -> object:
        assert os.environ["ROOK_MCP_TOOL_PROFILE"] == "lean"
        self.events.append(name)
        if name == "rhino_ping":
            return {"success": True, "data": {"processId": 42, "port": 9001}}
        if name == "gh_status":
            response = self.status_responses[self.status_index]
            self.status_index += 1
            if isinstance(response, BaseException):
                raise response
            return response
        if name == "chirp_create":
            self.chirp_calls += 1
            if isinstance(self.chirp_response, BaseException):
                raise self.chirp_response
            return self.chirp_response
        if name == "gh_errors":
            if isinstance(self.errors_response, BaseException):
                raise self.errors_response
            return self.errors_response
        if name == "gh_undo":
            response = self.undo_responses[self.undo_calls]
            self.undo_calls += 1
            return response
        raise AssertionError(name)

    async def call_rhino(
        self,
        endpoint: str,
        method: str = "GET",
        data: dict | None = None,
        **kwargs,
    ) -> object:
        assert endpoint == "/gh/errors"
        assert method == "GET"
        assert data == {"debug": True}
        assert kwargs == {"port": 9001, "process_id": 42}
        response = self.inventories[self.inventory_index]
        self.inventory_index += 1
        if isinstance(response, BaseException):
            raise response
        return response

    def install(self, monkeypatch) -> None:
        monkeypatch.setattr(proof, "_call_tool_dispatch", self.dispatch)
        monkeypatch.setattr(proof, "call_rhino", self.call_rhino, raising=False)


def _successful_live_harness(monkeypatch) -> _LiveSmokeHarness:
    baseline = ("base", "group-instance", "relay-instance")
    current = (*baseline, "abc")
    harness = _LiveSmokeHarness(
        inventories=[
            _debug_inventory_response(*baseline),
            _debug_inventory_response(*current),
            _debug_inventory_response(*current),
            _debug_inventory_response(*baseline),
        ],
        undo_responses=[_gh_undo_success(), _gh_undo_success()],
    )
    harness.install(monkeypatch)
    return harness


@pytest.mark.asyncio
async def test_slow_inference_acceptance_uses_scoped_environment_and_owned_cleanup(
    monkeypatch, tmp_path: Path
):
    deterministic_guid = _test_guid("deterministic")
    component_guid = _test_guid("slow")
    inventories = [
        _debug_inventory_response("baseline"),
        _debug_inventory_response("baseline", deterministic_guid),
        _debug_inventory_response("baseline"),
        _debug_inventory_response("baseline"),
        _debug_inventory_response("baseline", component_guid),
        _debug_inventory_response("baseline"),
    ]
    status_counts = [1, 1, 2, 1, 1, 2, 1]
    calls: list[tuple[str, dict]] = []
    create_count = 0
    inspect_count = 0
    sleep_delays: list[float] = []

    async def dispatch(name: str, args: dict):
        nonlocal create_count, inspect_count
        calls.append((name, dict(args)))
        if name == "rhino_ping":
            return {"success": True, "data": {"processId": 42, "port": 9001}}
        if name == "gh_status":
            return _gh_status_response(status_counts.pop(0))
        if name == "chirp_create":
            create_count += 1
            if create_count == 1:
                return {
                    "success": True,
                    "data": {
                        "component_guid": deterministic_guid,
                        "component_errors": [],
                    },
                }
            providers = json.loads(os.environ["CHIRP_PROVIDERS"])
            model_key = os.environ["CHIRP_MODEL"]
            assert model_key.startswith("openai/rook-timeout-acceptance-")
            provider = providers[model_key]
            payload = _post_json(
                provider["api_base"] + "/chat/completions",
                {"model": model_key.split("/", 1)[1], "messages": []},
            )
            assert "slow-ok" in payload["choices"][0]["message"]["content"]
            return {
                "success": True,
                "data": {
                    "component_guid": component_guid,
                    "verification_deferred": True,
                    "solve_scheduled": True,
                },
            }
        if name == "gh_inspect_output":
            inspect_count += 1
            if inspect_count == 1:
                return {"success": False, "data": "GH callback request timed out."}
            return {"success": True, "data": {"preview": ["slow-ok"]}}
        if name == "gh_errors":
            return {"success": True, "data": {"errors": []}}
        if name == "gh_undo":
            return _gh_undo_success()
        raise AssertionError(name)

    async def call_rhino(endpoint, method="GET", data=None, **kwargs):
        assert endpoint == "/gh/errors"
        assert method == "GET"
        assert data == {"debug": True}
        assert kwargs == {"port": 9001, "process_id": 42}
        return inventories.pop(0)

    async def record_sleep(delay: float):
        sleep_delays.append(delay)

    monkeypatch.setenv("CHIRP_MODEL", "prior-model")
    monkeypatch.delenv("CHIRP_CACHE", raising=False)
    monkeypatch.delenv("CHIRP_PROVIDERS", raising=False)
    monkeypatch.delenv("CHIRP_TIMEOUT_ACCEPTANCE_API_KEY", raising=False)
    monkeypatch.delenv("CHIRP_INFERENCE_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setattr(proof, "_call_tool_dispatch", dispatch)
    monkeypatch.setattr(proof, "call_rhino", call_rhino)
    monkeypatch.setattr(proof.asyncio, "sleep", record_sleep)
    monkeypatch.setattr(
        proof,
        "_stop_owned_chirp_sidecar",
        lambda: {"attempted": True, "success": True, "pid": 1234, "forced": False},
    )

    async def progressive(_args):
        return {"target": "gh_status", "target_hidden": True}

    monkeypatch.setattr(proof, "_run_live_progressive_gh_status", progressive)

    result = await proof.run_live_smoke(
        port=9001,
        process_id=42,
        artifact_dir=tmp_path,
        slow_provider_delay_seconds=0.05,
    )
    evidence = result["slow_inference"]

    assert evidence["output"] == "slow-ok"
    assert evidence["elapsed_seconds"] >= 0.05
    assert evidence["provider"]["request_count"] == 1
    assert evidence["transient_callback_timeouts"] == 1
    assert evidence["cleanup"]["component_removed"] is True
    assert evidence["sidecar_cleanup"]["success"] is True
    assert os.environ["CHIRP_MODEL"] == "prior-model"
    assert "CHIRP_PROVIDERS" not in os.environ
    assert "CHIRP_TIMEOUT_ACCEPTANCE_API_KEY" not in os.environ
    assert "CHIRP_INFERENCE_TIMEOUT_SECONDS" not in os.environ
    assert "CHIRP_CACHE" not in os.environ
    assert evidence["sidecar_cleanup"]["attempted"] is True
    assert [name for name, _ in calls].count("gh_inspect_output") == 2
    assert sleep_delays == [0.25]
    create_args = [args for name, args in calls if name == "chirp_create"][1]
    assert "deterministic_code" not in create_args
    assert create_args.get("deterministic_only") is not True


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ({"success": False, "data": "GH callback request timed out."}, True),
        ({"success": False, "data": "different failure"}, False),
        ({"success": False, "data": "GH callback request timed out.", "extra": True}, False),
        ({"success": True, "data": "GH callback request timed out."}, False),
        (None, False),
    ],
)
def test_slow_output_retry_is_limited_to_exact_callback_timeout(response, expected):
    assert proof._is_retryable_slow_inspection_timeout(response) is expected


@pytest.mark.asyncio
async def test_slow_inference_cancellation_still_cleans_provider_sidecar_and_component(
    monkeypatch, tmp_path: Path
):
    deterministic_guid = _test_guid("deterministic-before-cancel")
    component_guid = _test_guid("cancelled-slow")
    inventories = [
        _debug_inventory_response("baseline"),
        _debug_inventory_response("baseline", deterministic_guid),
        _debug_inventory_response("baseline"),
        _debug_inventory_response("baseline"),
        _debug_inventory_response("baseline", component_guid),
        _debug_inventory_response("baseline"),
    ]
    status_counts = [1, 1, 2, 1, 1, 2, 1]
    undo_calls = 0
    create_count = 0

    async def dispatch(name: str, _args: dict):
        nonlocal create_count, undo_calls
        if name == "rhino_ping":
            return {"success": True, "data": {"processId": 42, "port": 9001}}
        if name == "gh_status":
            return _gh_status_response(status_counts.pop(0))
        if name == "chirp_create":
            create_count += 1
            if create_count == 1:
                return {
                    "success": True,
                    "data": {
                        "component_guid": deterministic_guid,
                        "component_errors": [],
                    },
                }
            return {
                "success": True,
                "data": {
                    "component_guid": component_guid,
                    "verification_deferred": True,
                    "solve_scheduled": True,
                },
            }
        if name == "gh_inspect_output":
            raise asyncio.CancelledError("watchdog")
        if name == "gh_errors":
            return {"success": True, "data": {"errors": []}}
        if name == "gh_undo":
            undo_calls += 1
            return _gh_undo_success()
        raise AssertionError(name)

    async def call_rhino(_endpoint, method="GET", data=None, **_kwargs):
        return inventories.pop(0)

    captured = {}
    original_provider = proof._slow_openai_provider

    @contextmanager
    def capturing_provider(*args, **kwargs):
        with original_provider(*args, **kwargs) as provider:
            captured["provider"] = provider
            yield provider

    sidecar_cleanup_calls = []
    original_sidecar_cleanup = proof._stop_owned_chirp_sidecar

    def record_sidecar_cleanup():
        sidecar_cleanup_calls.append(True)
        return original_sidecar_cleanup()

    monkeypatch.setattr(proof, "_slow_openai_provider", capturing_provider)
    monkeypatch.setattr(proof, "_stop_owned_chirp_sidecar", record_sidecar_cleanup)
    monkeypatch.setattr(proof, "_call_tool_dispatch", dispatch)
    monkeypatch.setattr(proof, "call_rhino", call_rhino)

    async def progressive(_args):
        return {"target": "gh_status", "target_hidden": True}

    monkeypatch.setattr(proof, "_run_live_progressive_gh_status", progressive)

    with pytest.raises(asyncio.CancelledError, match="watchdog"):
        await proof.run_live_smoke(
            port=9001,
            process_id=42,
            artifact_dir=tmp_path,
            slow_provider_delay_seconds=0.02,
        )

    assert undo_calls == 2
    assert sidecar_cleanup_calls == [True]
    assert captured["provider"].thread.is_alive() is False


async def _ready_only_dispatch(name: str, _args: dict):
    assert os.environ["ROOK_MCP_TOOL_PROFILE"] == "lean"
    if name == "rhino_ping":
        return {"success": True, "data": {"processId": 42, "port": 9001}}
    if name == "gh_status":
        return _gh_status_response(3)
    raise AssertionError(name)


@pytest.fixture
def passing_live_progressive(monkeypatch):
    async def fake_progressive(_args):
        assert os.environ["ROOK_MCP_TOOL_PROFILE"] == "lean"
        return {
            "profile": "lean",
            "gateways": [
                "rook_tools_ls",
                "rook_tools_search",
                "rook_tools_read",
                "rook_tools_call",
            ],
            "target": "gh_status",
            "target_hidden": True,
            "search": [{"name": "gh_status"}],
            "read": {
                "name": "gh_status",
                "mcp_dispatchable": True,
                "input_schema": {"type": "object"},
            },
            "call": {"ready": True},
        }

    monkeypatch.setattr(proof, "_run_live_progressive_gh_status", fake_progressive)


@pytest.mark.asyncio
async def test_live_progressive_gh_status_uses_public_search_read_call(monkeypatch):
    calls = []
    monkeypatch.setattr(
        proof,
        "_list_public_tools",
        lambda: _async_value(
            [
                SimpleNamespace(name=name)
                for name in (
                    "rook_tools_ls",
                    "rook_tools_search",
                    "rook_tools_read",
                    "rook_tools_call",
                    "rhino_ping",
                )
            ]
        ),
    )

    async def fake_public(name, arguments):
        calls.append((name, arguments))
        if name == "rook_tools_search":
            return [{"name": "gh_status"}]
        if name == "rook_tools_read":
            return {
                "name": "gh_status",
                "mcp_dispatchable": True,
                "input_schema": {"type": "object"},
            }
        if name == "rook_tools_call":
            return {"ready": True}
        raise AssertionError(name)

    monkeypatch.setattr(proof, "_call_public_tool", fake_public)
    result = await proof._run_live_progressive_gh_status(
        {"port": 9001, "process_id": 42}
    )
    assert [name for name, _ in calls] == [
        "rook_tools_search",
        "rook_tools_read",
        "rook_tools_call",
    ]
    assert calls[-1][1] == {
        "name": "gh_status",
        "arguments": {"port": 9001, "process_id": 42},
    }
    assert result["target_hidden"] is True
    assert result["call"] == {"ready": True}


@pytest.mark.asyncio
async def test_run_live_smoke_restores_profile_after_progressive_failure(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
    monkeypatch.setattr(proof, "_call_tool_dispatch", _ready_only_dispatch)

    async def fail_progressive(_args):
        assert os.environ["ROOK_MCP_TOOL_PROFILE"] == "lean"
        raise proof.ProofFailure(
            "progressive_discovery_failed", "missing gh_status"
        )

    monkeypatch.setattr(proof, "_run_live_progressive_gh_status", fail_progressive)
    with pytest.raises(proof.ProofFailure):
        await proof.run_live_smoke(port=9001, process_id=42)
    assert os.environ["ROOK_MCP_TOOL_PROFILE"] == "readonly"


@pytest.mark.asyncio
async def test_run_live_smoke_restores_profile_after_success(
    monkeypatch, passing_live_progressive
):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    _successful_live_harness(monkeypatch)
    result = await proof.run_live_smoke(port=9001, process_id=42)
    assert os.environ["ROOK_MCP_TOOL_PROFILE"] == "full"
    assert result["progressive_discovery"]["target"] == "gh_status"


@pytest.mark.asyncio
async def test_run_live_smoke_restores_profile_to_unset_state(
    monkeypatch, passing_live_progressive
):
    monkeypatch.delenv("ROOK_MCP_TOOL_PROFILE", raising=False)
    _successful_live_harness(monkeypatch)
    result = await proof.run_live_smoke(port=9001, process_id=42)
    assert "ROOK_MCP_TOOL_PROFILE" not in os.environ
    assert result["progressive_discovery"]["profile"] == "lean"


@pytest.mark.asyncio
async def test_run_live_smoke_orders_progressive_chain_before_chirp(monkeypatch):
    events = []
    harness = _successful_live_harness(monkeypatch)

    async def fake_direct(name, args):
        events.append(name)
        return await harness.dispatch(name, args)

    async def fake_progressive(_args):
        events.extend(["rook_tools_search", "rook_tools_read", "rook_tools_call"])
        return {"target": "gh_status", "target_hidden": True}

    monkeypatch.setattr(proof, "_call_tool_dispatch", fake_direct)
    monkeypatch.setattr(proof, "_run_live_progressive_gh_status", fake_progressive)
    await proof.run_live_smoke(port=9001, process_id=42)
    assert events.index("rhino_ping") < events.index("gh_status")
    assert events.index("gh_status") < events.index("rook_tools_search")
    assert events.index("rook_tools_search") < events.index("rook_tools_read")
    assert events.index("rook_tools_read") < events.index("rook_tools_call")
    assert events.index("rook_tools_call") < events.index("chirp_create")


@pytest.mark.asyncio
async def test_live_smoke_uses_instance_inventory_for_two_undo_grouped_canvas(
    monkeypatch, passing_live_progressive
):
    harness = _successful_live_harness(monkeypatch)

    result = await proof.run_live_smoke(port=9001, process_id=42)

    cleanup = result["gh_undo"]
    assert harness.undo_calls == 2
    assert harness.inventory_index == 4
    assert cleanup["attempt_count"] == 2
    assert cleanup["attempts"] == harness.undo_responses
    assert cleanup["component_guid"] == _test_guid("abc")
    assert cleanup["component_observed_after_attempt"] is True
    assert cleanup["component_removed"] is True
    assert cleanup["baseline_object_count"] == 3
    assert cleanup["final_object_count"] == 3
    assert cleanup["baseline_instance_guids"] == [
        _test_guid("base"),
        _test_guid("relay-instance"),
        _test_guid("group-instance"),
    ]
    assert cleanup["final_instance_guids"] == cleanup["baseline_instance_guids"]


@pytest.mark.asyncio
async def test_live_smoke_stops_without_undo_when_failed_create_changed_nothing(
    monkeypatch, passing_live_progressive
):
    baseline = ("base", "group-instance", "relay-instance")
    harness = _LiveSmokeHarness(
        inventories=[
            _debug_inventory_response(*baseline),
            _debug_inventory_response(*baseline),
        ],
        chirp_response={"success": False, "data": "script injection failed"},
    )
    harness.install(monkeypatch)

    with pytest.raises(proof.ProofFailure) as exc:
        await proof.run_live_smoke(port=9001, process_id=42)

    assert exc.value.failure_label == "chirp_create_failed"
    assert harness.undo_calls == 0
    assert harness.inventory_index == 2
    assert exc.value.details["cleanup"]["attempt_count"] == 0
    assert exc.value.details["cleanup"]["component_removed"] is False


@pytest.mark.asyncio
async def test_live_smoke_refuses_to_undo_unknown_addition_after_failed_chirp_response(
    monkeypatch, passing_live_progressive
):
    baseline = ("base",)
    harness = _LiveSmokeHarness(
        inventories=[
            _debug_inventory_response(*baseline),
            _debug_inventory_response(*baseline, "unknown-created"),
            _debug_inventory_response(*baseline),
        ],
        chirp_response={"success": False, "data": "component created but GUID lost"},
        undo_responses=[_gh_undo_success()],
    )
    harness.install(monkeypatch)

    with pytest.raises(proof.ProofFailure) as exc:
        await proof.run_live_smoke(port=9001, process_id=42)

    assert exc.value.failure_label == "cleanup_failed"
    assert "identity is unknown" in str(exc.value)
    assert harness.undo_calls == 0
    assert exc.value.details["gh_undo"]["attempt_count"] == 0
    assert exc.value.details["gh_undo"]["component_removed"] is False
    assert exc.value.details["original_failure"]["failure_label"] == (
        "chirp_create_failed"
    )


@pytest.mark.parametrize(
    (
        "chirp_response",
        "errors_response",
        "expected_label",
        "created_guid",
        "expected_undo_calls",
    ),
    [
        (
            {
                "success": True,
                "data": {
                    "component_guid": _test_guid("abc"),
                    "warning": "compiled with warning",
                    "component_errors": [],
                },
            },
            None,
            "chirp_component_warning",
            _test_guid("abc"),
            1,
        ),
        (
            {
                "success": True,
                "data": {
                    "component_guid": _test_guid("abc"),
                    "component_errors": ["component failed"],
                },
            },
            None,
            "chirp_component_error",
            _test_guid("abc"),
            1,
        ),
        (
            {"success": True, "data": {"component_errors": []}},
            None,
            "cleanup_failed",
            "unknown-created",
            0,
        ),
        (
            {
                "success": True,
                "data": {
                    "component_guid": _test_guid("abc"),
                    "component_errors": [],
                },
            },
            {"success": False, "data": "diagnostics unavailable"},
            "gh_component_error",
            _test_guid("abc"),
            1,
        ),
        (
            {
                "success": True,
                "data": {
                    "component_guid": _test_guid("abc"),
                    "component_errors": [],
                },
            },
            {
                "success": True,
                "data": {
                    "errors": [
                        {
                            "guid": "{" + _test_guid("abc").upper() + "}",
                            "errors": ["boom"],
                        }
                    ]
                },
            },
            "gh_component_error",
            _test_guid("abc"),
            1,
        ),
        (
            [],
            None,
            "cleanup_failed",
            _test_guid("unknown-non-dict"),
            0,
        ),
        (
            {"success": True, "data": []},
            None,
            "cleanup_failed",
            _test_guid("unknown-malformed-data"),
            0,
        ),
        (
            RuntimeError("chirp transport broke"),
            None,
            "cleanup_failed",
            _test_guid("unknown-dispatch-exception"),
            0,
        ),
        (
            {
                "success": True,
                "data": {
                    "component_guid": _test_guid("abc"),
                    "component_errors": [],
                },
            },
            {"success": True, "data": []},
            "gh_component_error",
            _test_guid("abc"),
            1,
        ),
        (
            {
                "success": True,
                "data": {
                    "component_guid": _test_guid("abc"),
                    "component_errors": [],
                },
            },
            {"success": True, "data": {"errors": [{"guid": 7, "errors": []}]}},
            "gh_component_error",
            _test_guid("abc"),
            1,
        ),
        (
            {
                "success": True,
                "data": {
                    "component_guid": _test_guid("abc"),
                    "component_errors": [],
                },
            },
            RuntimeError("gh_errors transport broke"),
            "gh_component_error",
            _test_guid("abc"),
            1,
        ),
    ],
    ids=[
        "warning",
        "compile-error",
        "missing-guid",
        "gh-errors-failure",
        "component-error-alternate-guid-spelling",
        "non-dict-chirp",
        "malformed-chirp-data",
        "chirp-dispatch-exception",
        "malformed-gh-errors-data",
        "malformed-gh-errors-entry",
        "gh-errors-dispatch-exception",
    ],
)
@pytest.mark.asyncio
async def test_live_smoke_restores_canvas_before_propagating_validation_failure(
    monkeypatch,
    passing_live_progressive,
    chirp_response,
    errors_response,
    expected_label,
    created_guid,
    expected_undo_calls,
):
    baseline = ("base",)
    harness = _LiveSmokeHarness(
        inventories=[
            _debug_inventory_response(*baseline),
            _debug_inventory_response(*baseline, created_guid),
            _debug_inventory_response(*baseline),
        ],
        chirp_response=chirp_response,
        errors_response=errors_response,
        undo_responses=[_gh_undo_success()],
    )
    harness.install(monkeypatch)

    with pytest.raises(proof.ProofFailure) as exc:
        await proof.run_live_smoke(port=9001, process_id=42)

    assert exc.value.failure_label == expected_label
    assert harness.undo_calls == expected_undo_calls
    if expected_undo_calls:
        assert exc.value.details["cleanup"]["attempt_count"] == 1
        assert exc.value.details["cleanup"]["final_instance_guids"] == [
            _test_guid("base")
        ]
    else:
        assert exc.value.details["gh_undo"]["attempt_count"] == 0
        assert exc.value.details["gh_undo"]["component_removed"] is False
        assert exc.value.details["original_failure"]["failure_label"] == (
            "chirp_create_failed"
        )


@pytest.mark.asyncio
async def test_live_smoke_canonicalizes_alternate_valid_instance_guid_spellings(
    monkeypatch, passing_live_progressive
):
    baseline = ("base",)
    target = _test_guid("abc")
    harness = _LiveSmokeHarness(
        inventories=[
            _debug_inventory_response(*baseline),
            _debug_inventory_response(*baseline, target),
            _debug_inventory_response(*baseline),
        ],
        chirp_response={
            "success": True,
            "data": {
                "component_guid": "{" + target.upper() + "}",
                "component_errors": [],
            },
        },
        undo_responses=[_gh_undo_success()],
    )
    harness.install(monkeypatch)

    result = await proof.run_live_smoke(port=9001, process_id=42)

    assert result["gh_undo"]["component_guid"] == target
    assert result["gh_undo"]["component_observed_after_attempt"] is True
    assert harness.undo_calls == 1


@pytest.mark.asyncio
async def test_live_smoke_rejects_invalid_inventory_guid_without_undo(
    monkeypatch, passing_live_progressive
):
    harness = _LiveSmokeHarness(
        inventories=[
            _debug_inventory_response("base"),
            {
                "success": True,
                "data": {
                    "totalComponents": 2,
                    "debugInfo": [
                        {"guid": _test_guid("base")},
                        {"guid": "not-an-instance-guid"},
                    ],
                },
            },
        ],
        status_responses=[
            _gh_status_response(1),
            _gh_status_response(1),
            _gh_status_response(2),
        ],
    )
    harness.install(monkeypatch)

    with pytest.raises(proof.ProofFailure) as exc:
        await proof.run_live_smoke(port=9001, process_id=42)

    assert exc.value.failure_label == "cleanup_failed"
    assert "malformed instance GUID" in str(exc.value)
    assert harness.undo_calls == 0


@pytest.mark.asyncio
async def test_live_smoke_rejects_invalid_created_guid_without_undoing_unknown_addition(
    monkeypatch, passing_live_progressive
):
    baseline = ("base",)
    harness = _LiveSmokeHarness(
        inventories=[
            _debug_inventory_response(*baseline),
            _debug_inventory_response(*baseline, "unknown-created"),
            _debug_inventory_response(*baseline),
        ],
        chirp_response={
            "success": True,
            "data": {
                "component_guid": "not-an-instance-guid",
                "component_errors": [],
            },
        },
        undo_responses=[_gh_undo_success()],
    )
    harness.install(monkeypatch)

    with pytest.raises(proof.ProofFailure) as exc:
        await proof.run_live_smoke(port=9001, process_id=42)

    assert exc.value.failure_label == "cleanup_failed"
    assert "identity is unknown" in str(exc.value)
    assert exc.value.details["gh_undo"]["attempt_count"] == 0
    assert exc.value.details["gh_undo"]["component_removed"] is False
    assert exc.value.details["original_failure"]["failure_label"] == (
        "chirp_create_failed"
    )
    assert harness.undo_calls == 0


@pytest.mark.asyncio
async def test_live_smoke_rejects_created_target_already_in_baseline_before_undo(
    monkeypatch, passing_live_progressive
):
    target = _test_guid("abc")
    harness = _LiveSmokeHarness(
        inventories=[
            _debug_inventory_response("base", target),
            _debug_inventory_response("base", target, "other-new"),
        ],
        chirp_response={
            "success": True,
            "data": {"component_guid": target, "component_errors": []},
        },
        undo_responses=[_gh_undo_success()],
    )
    harness.install(monkeypatch)

    with pytest.raises(proof.ProofFailure) as exc:
        await proof.run_live_smoke(port=9001, process_id=42)

    assert exc.value.failure_label == "cleanup_failed"
    assert "already present in baseline" in str(exc.value)
    assert exc.value.details["original_failure"]["failure_label"] == (
        "chirp_create_failed"
    )
    assert harness.undo_calls == 0


@pytest.mark.asyncio
async def test_live_smoke_fails_successful_create_when_target_was_never_observed(
    monkeypatch, passing_live_progressive
):
    baseline = ("base",)
    harness = _LiveSmokeHarness(
        inventories=[
            _debug_inventory_response(*baseline),
            _debug_inventory_response(*baseline),
        ]
    )
    harness.install(monkeypatch)

    with pytest.raises(proof.ProofFailure) as exc:
        await proof.run_live_smoke(port=9001, process_id=42)

    assert exc.value.failure_label == "chirp_create_failed"
    assert "was not observed" in str(exc.value)
    assert exc.value.details["cleanup"]["attempt_count"] == 0
    assert exc.value.details["cleanup"]["component_observed_after_attempt"] is False
    assert harness.undo_calls == 0


@pytest.mark.parametrize(
    ("inventories", "status_responses", "expected_text"),
    [
        (
            [
                {
                    "success": True,
                    "data": {
                        "totalComponents": 1,
                        "debugInfo": [{"guid": 7}],
                    },
                }
            ],
            [_gh_status_response(1), _gh_status_response(1)],
            "debug inventory entry",
        ),
        (
            [_debug_inventory_response("base")],
            [
                _gh_status_response(1),
                _gh_status_response(1),
                {"success": True, "data": {"object_count": "2"}},
            ],
            "gh_status",
        ),
        (
            [
                _debug_inventory_response("base"),
                {"success": True, "data": {"totalComponents": 2, "debugInfo": "bad"}},
            ],
            [_gh_status_response(1), _gh_status_response(1), _gh_status_response(2)],
            "debug inventory",
        ),
    ],
    ids=["malformed-entry", "malformed-status", "malformed-inventory"],
)
@pytest.mark.asyncio
async def test_live_smoke_fails_closed_on_malformed_cleanup_probe(
    monkeypatch,
    passing_live_progressive,
    inventories,
    status_responses,
    expected_text,
):
    harness = _LiveSmokeHarness(
        inventories=inventories,
        status_responses=status_responses,
        undo_responses=[_gh_undo_success()],
    )
    harness.install(monkeypatch)

    with pytest.raises(proof.ProofFailure) as exc:
        await proof.run_live_smoke(port=9001, process_id=42)

    assert exc.value.failure_label == "cleanup_failed"
    assert expected_text in str(exc.value)
    assert harness.undo_calls == 0
    if expected_text == "debug inventory entry":
        assert harness.chirp_calls == 0


@pytest.mark.asyncio
async def test_live_smoke_normalizes_post_attempt_inventory_exception_and_retains_original(
    monkeypatch, passing_live_progressive
):
    baseline = ("base",)
    harness = _LiveSmokeHarness(
        inventories=[
            _debug_inventory_response(*baseline),
            RuntimeError("debug inventory transport broke"),
        ],
        status_responses=[
            _gh_status_response(1),
            _gh_status_response(1),
            _gh_status_response(2),
        ],
        chirp_response={
            "success": True,
            "data": {
                "component_guid": _test_guid("abc"),
                "warning": "compiled with warning",
                "component_errors": [],
            },
        },
    )
    harness.install(monkeypatch)

    with pytest.raises(proof.ProofFailure) as exc:
        await proof.run_live_smoke(port=9001, process_id=42)

    assert exc.value.failure_label == "cleanup_failed"
    assert exc.value.details["original_failure"]["failure_label"] == (
        "chirp_component_warning"
    )
    probe = exc.value.details["probe_failure"]
    assert probe["details"]["exception_type"] == "RuntimeError"
    assert "debug inventory transport broke" in probe["details"]["message"]
    assert harness.undo_calls == 0


@pytest.mark.asyncio
async def test_live_smoke_normalizes_post_undo_status_exception_with_attempt_evidence(
    monkeypatch, passing_live_progressive
):
    baseline = ("base",)
    harness = _LiveSmokeHarness(
        inventories=[
            _debug_inventory_response(*baseline),
            _debug_inventory_response(*baseline, "abc"),
        ],
        status_responses=[
            _gh_status_response(1),
            _gh_status_response(1),
            _gh_status_response(2),
            RuntimeError("status transport broke"),
        ],
        undo_responses=[_gh_undo_success()],
    )
    harness.install(monkeypatch)

    with pytest.raises(proof.ProofFailure) as exc:
        await proof.run_live_smoke(port=9001, process_id=42)

    assert exc.value.failure_label == "cleanup_failed"
    assert exc.value.details["gh_undo"]["attempt_count"] == 1
    assert exc.value.details["gh_undo"]["attempts"] == [_gh_undo_success()]
    probe = exc.value.details["probe_failure"]
    assert probe["details"]["exception_type"] == "RuntimeError"
    assert "status transport broke" in probe["details"]["message"]
    assert harness.undo_calls == 1


@pytest.mark.asyncio
async def test_live_smoke_preserves_prior_attempts_for_unforeseen_restore_exception(
    monkeypatch, passing_live_progressive
):
    baseline = ("base",)
    harness = _LiveSmokeHarness(
        inventories=[
            _debug_inventory_response(*baseline),
            _debug_inventory_response(*baseline, "abc"),
        ],
        undo_responses=[_gh_undo_success()],
    )
    harness.install(monkeypatch)
    original_capture = proof._capture_chirp_cleanup_state
    capture_calls = 0

    async def capture_then_raise(*args, **kwargs):
        nonlocal capture_calls
        capture_calls += 1
        if capture_calls == 3:
            raise ValueError("unforeseen restore failure")
        return await original_capture(*args, **kwargs)

    monkeypatch.setattr(proof, "_capture_chirp_cleanup_state", capture_then_raise)

    with pytest.raises(proof.ProofFailure) as exc:
        await proof.run_live_smoke(port=9001, process_id=42)

    assert exc.value.failure_label == "cleanup_failed"
    assert exc.value.details["restore_exception"]["exception_type"] == "ValueError"
    assert exc.value.details["gh_undo"]["attempt_count"] == 1
    assert exc.value.details["gh_undo"]["attempts"] == [_gh_undo_success()]
    assert harness.undo_calls == 1


@pytest.mark.asyncio
async def test_live_smoke_records_non_dict_undo_before_failing(
    monkeypatch, passing_live_progressive
):
    baseline = ("base",)
    harness = _LiveSmokeHarness(
        inventories=[
            _debug_inventory_response(*baseline),
            _debug_inventory_response(*baseline, "abc"),
        ],
        undo_responses=["malformed-undo"],
    )
    harness.install(monkeypatch)

    with pytest.raises(proof.ProofFailure) as exc:
        await proof.run_live_smoke(port=9001, process_id=42)

    assert exc.value.failure_label == "cleanup_failed"
    assert harness.undo_calls == 1
    assert exc.value.details["gh_undo"]["attempts"] == ["malformed-undo"]
    assert exc.value.details["gh_undo"]["attempt_count"] == 1


@pytest.mark.asyncio
async def test_live_smoke_fails_without_undo_when_baseline_guid_is_already_lost(
    monkeypatch, passing_live_progressive
):
    baseline = ("base-a", "base-b")
    harness = _LiveSmokeHarness(
        inventories=[
            _debug_inventory_response(*baseline),
            _debug_inventory_response("base-a", "abc", "other-new"),
        ],
        undo_responses=[_gh_undo_success()],
    )
    harness.install(monkeypatch)

    with pytest.raises(proof.ProofFailure) as exc:
        await proof.run_live_smoke(port=9001, process_id=42)

    assert exc.value.failure_label == "cleanup_failed"
    assert "baseline instance GUID" in str(exc.value)
    assert harness.undo_calls == 0


@pytest.mark.asyncio
async def test_live_smoke_does_not_over_undo_at_baseline_count_with_new_guid(
    monkeypatch, passing_live_progressive
):
    baseline = ("base-a", "base-b")
    harness = _LiveSmokeHarness(
        inventories=[
            _debug_inventory_response(*baseline),
            _debug_inventory_response(*baseline, "abc"),
            _debug_inventory_response("base-a", "abc"),
        ],
        undo_responses=[_gh_undo_success(), _gh_undo_success()],
    )
    harness.install(monkeypatch)

    with pytest.raises(proof.ProofFailure) as exc:
        await proof.run_live_smoke(port=9001, process_id=42)

    assert exc.value.failure_label == "cleanup_failed"
    assert harness.undo_calls == 1
    assert exc.value.details["gh_undo"]["final_object_count"] == 2


@pytest.mark.asyncio
async def test_live_smoke_refuses_initial_target_plus_unrelated_addition_without_undo(
    monkeypatch, passing_live_progressive
):
    baseline = ("base",)
    harness = _LiveSmokeHarness(
        inventories=[
            _debug_inventory_response(*baseline),
            _debug_inventory_response(*baseline, "abc", "other-new"),
        ],
        undo_responses=[_gh_undo_success(), _gh_undo_success()],
    )
    harness.install(monkeypatch)

    with pytest.raises(proof.ProofFailure) as exc:
        await proof.run_live_smoke(port=9001, process_id=42)

    assert exc.value.failure_label == "cleanup_failed"
    assert "only the created target" in str(exc.value)
    assert harness.undo_calls == 0
    assert exc.value.details["gh_undo"]["attempt_count"] == 0


@pytest.mark.asyncio
async def test_live_smoke_stops_before_second_undo_when_unrelated_addition_appears(
    monkeypatch, passing_live_progressive
):
    baseline = ("base",)
    harness = _LiveSmokeHarness(
        inventories=[
            _debug_inventory_response(*baseline),
            _debug_inventory_response(*baseline, "abc"),
            _debug_inventory_response(*baseline, "abc", "other-new"),
        ],
        undo_responses=[_gh_undo_success(), _gh_undo_success()],
    )
    harness.install(monkeypatch)

    with pytest.raises(proof.ProofFailure) as exc:
        await proof.run_live_smoke(port=9001, process_id=42)

    assert exc.value.failure_label == "cleanup_failed"
    assert "only the created target" in str(exc.value)
    assert harness.undo_calls == 1
    assert exc.value.details["gh_undo"]["attempt_count"] == 1


@pytest.mark.asyncio
async def test_live_smoke_fails_when_safe_cleanup_bound_is_exhausted(
    monkeypatch, passing_live_progressive
):
    baseline = ("base",)
    current = (*baseline, "abc")
    harness = _LiveSmokeHarness(
        inventories=[
            _debug_inventory_response(*baseline),
            _debug_inventory_response(*current),
            _debug_inventory_response(*current),
            _debug_inventory_response(*current),
        ],
        undo_responses=[_gh_undo_success(), _gh_undo_success()],
    )
    harness.install(monkeypatch)
    monkeypatch.setattr(proof, "_CHIRP_CLEANUP_MAX_UNDO_ATTEMPTS", 2)

    with pytest.raises(proof.ProofFailure) as exc:
        await proof.run_live_smoke(port=9001, process_id=42)

    assert exc.value.failure_label == "cleanup_failed"
    assert harness.undo_calls == 2
    assert exc.value.details["gh_undo"]["attempt_count"] == 2


@pytest.mark.asyncio
async def test_live_smoke_cleanup_failure_wins_and_retains_original_failure(
    monkeypatch, passing_live_progressive
):
    baseline = ("base-a", "base-b")
    harness = _LiveSmokeHarness(
        inventories=[
            _debug_inventory_response(*baseline),
            _debug_inventory_response("base-a", "abc", "other-new"),
        ],
        chirp_response={
            "success": True,
            "data": {
                "component_guid": _test_guid("abc"),
                "warning": "compiled with warning",
                "component_errors": [],
            },
        },
    )
    harness.install(monkeypatch)

    with pytest.raises(proof.ProofFailure) as exc:
        await proof.run_live_smoke(port=9001, process_id=42)

    assert exc.value.failure_label == "cleanup_failed"
    assert exc.value.details["original_failure"]["failure_label"] == (
        "chirp_component_warning"
    )
    assert harness.undo_calls == 0


@pytest.mark.asyncio
async def test_live_smoke_cleanup_failure_retains_prior_failure_and_real_cancellation(
    monkeypatch, passing_live_progressive
):
    baseline = ("base",)
    harness = _LiveSmokeHarness(
        inventories=[
            _debug_inventory_response(*baseline),
            _debug_inventory_response(*baseline, "abc"),
        ],
        chirp_response={
            "success": True,
            "data": {
                "component_guid": _test_guid("abc"),
                "warning": "compiled with warning",
                "component_errors": [],
            },
        },
    )
    harness.install(monkeypatch)
    undo_started = asyncio.Event()
    release_undo = asyncio.Event()
    base_dispatch = harness.dispatch

    async def dispatch(name: str, args: dict) -> object:
        if name != "gh_undo":
            return await base_dispatch(name, args)
        harness.events.append(name)
        harness.undo_calls += 1
        undo_started.set()
        await release_undo.wait()
        return {"success": False, "data": "undo failed"}

    monkeypatch.setattr(proof, "_call_tool_dispatch", dispatch)

    task = asyncio.create_task(proof.run_live_smoke(port=9001, process_id=42))
    await asyncio.wait_for(undo_started.wait(), timeout=1)
    task.cancel("outer cleanup cancelled")
    release_undo.set()

    with pytest.raises(proof.ProofFailure) as exc:
        await task

    assert exc.value.failure_label == "cleanup_failed"
    assert harness.undo_calls == 1
    assert exc.value.details["original_failure"]["failure_label"] == (
        "chirp_component_warning"
    )
    cancellations = exc.value.details["cancellation_context"]
    assert len(cancellations) == 1
    assert cancellations[0]["failure_label"] == "operation_cancelled"
    assert cancellations[0]["details"] == {
        "stage": "cleanup_wait",
        "exception_type": "CancelledError",
        "message": "outer cleanup cancelled",
    }


@pytest.mark.asyncio
async def test_live_smoke_real_cancellation_waits_for_successful_cleanup_then_reraises(
    monkeypatch, passing_live_progressive
):
    baseline = ("base",)
    harness = _LiveSmokeHarness(
        inventories=[
            _debug_inventory_response(*baseline),
            _debug_inventory_response(*baseline, "abc"),
            _debug_inventory_response(*baseline),
        ]
    )
    harness.install(monkeypatch)
    undo_started = asyncio.Event()
    release_undo = asyncio.Event()
    base_dispatch = harness.dispatch

    async def dispatch(name: str, args: dict) -> object:
        if name != "gh_undo":
            return await base_dispatch(name, args)
        harness.events.append(name)
        harness.undo_calls += 1
        undo_started.set()
        await release_undo.wait()
        return _gh_undo_success()

    monkeypatch.setattr(proof, "_call_tool_dispatch", dispatch)

    task = asyncio.create_task(proof.run_live_smoke(port=9001, process_id=42))
    await asyncio.wait_for(undo_started.wait(), timeout=1)
    task.cancel("outer cleanup cancelled")
    release_undo.set()

    with pytest.raises(asyncio.CancelledError, match="outer cleanup cancelled"):
        await task

    assert harness.undo_calls == 1
    assert harness.inventory_index == 3


@pytest.mark.asyncio
async def test_live_smoke_chirp_cancellation_proves_no_mutation_then_reraises(
    monkeypatch, passing_live_progressive
):
    baseline = ("base",)
    harness = _LiveSmokeHarness(
        inventories=[
            _debug_inventory_response(*baseline),
            _debug_inventory_response(*baseline),
        ],
        chirp_response=asyncio.CancelledError("chirp dispatch cancelled"),
    )
    harness.install(monkeypatch)
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")

    with pytest.raises(asyncio.CancelledError, match="chirp dispatch cancelled"):
        await proof.run_live_smoke(port=9001, process_id=42)

    assert harness.inventory_index == 2
    assert harness.undo_calls == 0
    assert os.environ["ROOK_MCP_TOOL_PROFILE"] == "full"


@pytest.mark.asyncio
async def test_live_smoke_chirp_cancellation_with_unknown_addition_fails_without_undo(
    monkeypatch, passing_live_progressive
):
    baseline = ("base",)
    harness = _LiveSmokeHarness(
        inventories=[
            _debug_inventory_response(*baseline),
            _debug_inventory_response(*baseline, "unknown-created"),
        ],
        chirp_response=asyncio.CancelledError("chirp dispatch cancelled"),
        undo_responses=[_gh_undo_success()],
    )
    harness.install(monkeypatch)

    with pytest.raises(proof.ProofFailure) as exc:
        await proof.run_live_smoke(port=9001, process_id=42)

    assert exc.value.failure_label == "cleanup_failed"
    assert "identity is unknown" in str(exc.value)
    assert harness.undo_calls == 0
    assert exc.value.details["gh_undo"]["component_removed"] is False
    cancellation = exc.value.details["original_failure"]
    assert cancellation["failure_label"] == "operation_cancelled"
    assert cancellation["details"]["stage"] == "chirp_create"
    assert cancellation["details"]["exception_type"] == "CancelledError"


@pytest.mark.asyncio
async def test_live_smoke_gh_errors_cancellation_cleans_known_target_then_reraises(
    monkeypatch, passing_live_progressive
):
    baseline = ("base",)
    harness = _LiveSmokeHarness(
        inventories=[
            _debug_inventory_response(*baseline),
            _debug_inventory_response(*baseline, "abc"),
            _debug_inventory_response(*baseline),
        ],
        errors_response=asyncio.CancelledError("gh_errors cancelled"),
        undo_responses=[_gh_undo_success()],
    )
    harness.install(monkeypatch)

    with pytest.raises(asyncio.CancelledError, match="gh_errors cancelled"):
        await proof.run_live_smoke(port=9001, process_id=42)

    assert harness.undo_calls == 1
    assert harness.inventory_index == 3


@pytest.mark.asyncio
async def test_live_smoke_cleanup_failure_wins_over_gh_errors_cancellation(
    monkeypatch, passing_live_progressive
):
    baseline = ("base",)
    harness = _LiveSmokeHarness(
        inventories=[
            _debug_inventory_response(*baseline),
            _debug_inventory_response(*baseline, "abc"),
        ],
        errors_response=asyncio.CancelledError("gh_errors cancelled"),
        undo_responses=[{"success": False, "data": "undo failed"}],
    )
    harness.install(monkeypatch)

    with pytest.raises(proof.ProofFailure) as exc:
        await proof.run_live_smoke(port=9001, process_id=42)

    assert exc.value.failure_label == "cleanup_failed"
    assert harness.undo_calls == 1
    assert exc.value.details["gh_undo"]["attempt_count"] == 1
    cancellation = exc.value.details["original_failure"]
    assert cancellation["failure_label"] == "operation_cancelled"
    assert cancellation["details"]["stage"] == "gh_errors"
    assert cancellation["details"]["exception_type"] == "CancelledError"


@pytest.mark.asyncio
async def test_cleanup_shield_records_cancellation_when_cleanup_just_finished(monkeypatch):
    interruptions = []

    async def cleanup():
        return {"restored": True}

    async def cancel_after_inner_finishes(task):
        await task
        raise asyncio.CancelledError("late cleanup cancellation")

    monkeypatch.setattr(proof.asyncio, "shield", cancel_after_inner_finishes)

    result = await proof._await_cleanup_shielded(cleanup(), interruptions)

    assert result == {"restored": True}
    assert len(interruptions) == 1
    assert str(interruptions[0]) == "late cleanup cancellation"


def _embedded_live_smoke_source() -> str:
    path = Path(__file__).resolve().parents[2] / "scripts" / "deploy-local-testing.ps1"
    content = path.read_text(encoding="utf-8")
    start_marker = '$smoke = @"'
    start = content.index(start_marker) + len(start_marker)
    end = content.index('"@', start)
    return content[start:end]


def test_deploy_embedded_live_smoke_executes_shared_mutation_helper(
    monkeypatch, capsys
):
    from rook import bridge as bridge_module
    from rook import server as server_module

    mutation_calls = []

    async def fake_dispatch(name, _arguments):
        if name == "rhino_ping":
            return {"success": True, "data": "pong"}
        if name == "gh_status":
            return _gh_status_response(1)
        raise AssertionError(f"embedded smoke bypassed shared mutation helper: {name}")

    async def fake_list_tools():
        return [
            SimpleNamespace(name=name)
            for name in (
                "rook_tools_ls",
                "rook_tools_search",
                "rook_tools_read",
                "rook_tools_call",
            )
        ]

    async def fake_call_tool(name, _arguments):
        if name == "rook_tools_search":
            payload = [{"name": "gh_status"}]
        elif name == "rook_tools_read":
            payload = {
                "name": "gh_status",
                "mcp_dispatchable": True,
                "input_schema": {"type": "object"},
            }
        elif name == "rook_tools_call":
            payload = {"ready_for_edit": True}
        else:
            raise AssertionError(name)
        return [SimpleNamespace(text=json.dumps(payload))]

    async def fake_mutation(
        args,
        *,
        component_name,
        dispatch_fn,
        call_rhino_fn,
    ):
        mutation_calls.append(
            {
                "args": args,
                "component_name": component_name,
                "dispatch_fn": dispatch_fn,
                "call_rhino_fn": call_rhino_fn,
            }
        )
        return {
            "chirp_create": {
                "success": True,
                "data": {"component_guid": _test_guid("abc")},
            },
            "gh_errors": {"success": True, "data": {"errors": []}},
            "gh_undo": {
                "attempts": [_gh_undo_success(), _gh_undo_success()],
                "attempt_count": 2,
                "component_guid": _test_guid("abc"),
                "component_removed": True,
                "baseline_object_count": 1,
                "final_object_count": 1,
                "baseline_instance_guids": [_test_guid("base")],
                "final_instance_guids": [_test_guid("base")],
            },
        }

    async def fake_call_rhino(*_args, **_kwargs):
        raise AssertionError("shared mutation helper was replaced in this test")

    monkeypatch.setattr(server_module, "_call_tool_dispatch", fake_dispatch)
    monkeypatch.setattr(server_module, "list_tools", fake_list_tools)
    monkeypatch.setattr(server_module, "call_tool", fake_call_tool)
    monkeypatch.setattr(bridge_module, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(
        proof, "_run_chirp_smoke_mutation", fake_mutation, raising=False
    )

    source = _embedded_live_smoke_source().rsplit("asyncio.run(main())", 1)[0]
    namespace = {"__name__": "embedded_live_smoke_test"}
    exec(compile(source, "<embedded-live-smoke>", "exec"), namespace)
    asyncio.run(namespace["main"]())

    assert len(mutation_calls) == 1
    assert mutation_calls[0]["args"] == {}
    assert mutation_calls[0]["component_name"] == "Rook Local Deploy Smoke"
    assert mutation_calls[0]["dispatch_fn"] is fake_dispatch
    assert mutation_calls[0]["call_rhino_fn"] is fake_call_rhino
    evidence = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert evidence["gh_undo"]["attempt_count"] == 2

    async def fake_failed_mutation(*_args, **_kwargs):
        raise proof.ProofFailure(
            "cleanup_failed",
            "embedded cleanup failed",
            {
                "gh_undo": {
                    "attempts": ["malformed-undo"],
                    "attempt_count": 1,
                    "component_removed": False,
                }
            },
        )

    namespace["_run_chirp_smoke_mutation"] = fake_failed_mutation
    with pytest.raises(SystemExit) as exc:
        asyncio.run(namespace["main"]())

    failure = json.loads(str(exc.value))
    assert failure["failure_label"] == "cleanup_failed"
    assert failure["message"] == "embedded cleanup failed"
    assert failure["details"]["gh_undo"]["attempt_count"] == 1


@pytest.mark.asyncio
async def test_live_smoke_launches_grasshopper_when_not_ready(
    monkeypatch, passing_live_progressive
):
    calls = []
    mutation_state = {"created": False, "undo_count": 0}
    inventories = [
        _debug_inventory_response("baseline"),
        _debug_inventory_response("baseline", "abc"),
        _debug_inventory_response("baseline"),
    ]

    async def fake_dispatch(name: str, args: dict):
        calls.append((name, args))
        if name == "rhino_ping":
            return {"success": True, "data": {"processId": 42, "port": 9001}}
        if name == "gh_status":
            if any(call[0] == "gh_document_new" for call in calls):
                object_count = (
                    2
                    if mutation_state["created"]
                    and mutation_state["undo_count"] == 0
                    else 1
                )
                return {
                    "success": True,
                    "data": {
                        "ready_for_edit": True,
                        "object_count": object_count,
                    },
                }
            return {
                "success": True,
                "data": {
                    "available": False,
                    "ready_for_edit": False,
                    "object_count": 0,
                },
            }
        if name == "rhino_command":
            return {"success": True, "data": {"command": args["command"]}}
        if name == "gh_document_new":
            return {"success": True, "data": {"documentName": "Untitled"}}
        if name == "chirp_create":
            mutation_state["created"] = True
            return {
                "success": True,
                "data": {
                    "component_guid": _test_guid("abc"),
                    "component_errors": [],
                },
            }
        if name == "gh_errors":
            return {"success": True, "data": {"errors": []}}
        if name == "gh_undo":
            mutation_state["undo_count"] += 1
            return _gh_undo_success()
        raise AssertionError(name)

    monkeypatch.setattr(proof, "_call_tool_dispatch", fake_dispatch)

    async def fake_call_rhino(_endpoint, _method, _data, **_kwargs):
        return inventories.pop(0)

    monkeypatch.setattr(proof, "call_rhino", fake_call_rhino)

    result = await proof.run_live_smoke(port=9001, process_id=42)

    assert result["grasshopper_ready"]["opened"] is True
    assert any(name == "rhino_command" and args["command"] == "_Grasshopper" for name, args in calls)
    assert any(name == "gh_document_new" for name, _ in calls)
    chirp_call = next(args for name, args in calls if name == "chirp_create")
    assert chirp_call["deterministic_only"] is True


@pytest.mark.asyncio
async def test_live_smoke_polls_after_grasshopper_command_timeout(
    monkeypatch, passing_live_progressive
):
    calls = []
    mutation_state = {"created": False, "undo_count": 0}
    inventories = [
        _debug_inventory_response("baseline"),
        _debug_inventory_response("baseline", "abc"),
        _debug_inventory_response("baseline"),
    ]

    async def fake_dispatch(name: str, args: dict):
        calls.append((name, args))
        if name == "rhino_ping":
            return {"success": True, "data": {"processId": 42, "port": 9001}}
        if name == "gh_status":
            if any(call[0] == "gh_document_new" for call in calls):
                object_count = (
                    2
                    if mutation_state["created"]
                    and mutation_state["undo_count"] == 0
                    else 1
                )
                return {
                    "success": True,
                    "data": {
                        "ready_for_edit": True,
                        "object_count": object_count,
                    },
                }
            return {
                "success": True,
                "data": {
                    "available": False,
                    "ready_for_edit": False,
                    "object_count": 0,
                },
            }
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
            mutation_state["created"] = True
            return {
                "success": True,
                "data": {
                    "component_guid": _test_guid("abc"),
                    "component_errors": [],
                },
            }
        if name == "gh_errors":
            return {"success": True, "data": {"errors": []}}
        if name == "gh_undo":
            mutation_state["undo_count"] += 1
            return _gh_undo_success()
        raise AssertionError(name)

    monkeypatch.setattr(proof, "_call_tool_dispatch", fake_dispatch)

    async def fake_call_rhino(_endpoint, _method, _data, **_kwargs):
        return inventories.pop(0)

    monkeypatch.setattr(proof, "call_rhino", fake_call_rhino)

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


def test_live_smoke_gate_requires_installed_environment(monkeypatch, tmp_path: Path):
    calls = []

    def require_installed_environment():
        calls.append("installed")
        return {"chirp_home": "C:/installed/Rook/app/chirp"}

    def run_coroutine(coroutine):
        coroutine.close()
        return {"slow_inference": {}}

    monkeypatch.setattr(proof, "_require_installed_live_environment", require_installed_environment)
    monkeypatch.setattr(proof.asyncio, "run", run_coroutine)
    monkeypatch.setenv("ROOK_HARNESS_ARTIFACT_DIR", str(tmp_path))

    result = proof.live_smoke_gate(
        ["python", "-m", "rook.local_testing_proof", "live-smoke"],
        port=9876,
        process_id=1234,
    )

    assert result.success is True
    assert calls == ["installed"]
    assert result.details["installed_environment"]["chirp_home"].endswith("app/chirp")


def test_owned_release_readiness_uses_installed_python_for_smoke(monkeypatch, tmp_path: Path):
    calls = {}
    live_envelope = {
        "gate": "live_smoke",
        "success": True,
        "failure_label": None,
        "details": {
            "progressive_discovery": {
                "target": "gh_status",
                "target_hidden": True,
            }
        },
    }

    class FakeHarnessResult:
        success = True
        artifact_dir = tmp_path / "run"
        cleanup_status = SimpleNamespace(value="graceful_exit")
        pid = 1234
        port = 9876
        warnings = []
        smoke = SimpleNamespace(
            returncode=0,
            stdout=f"harness prelude\n{json.dumps(live_envelope)}\n",
            stderr="",
        )

        def to_manifest_dict(self):
            return {
                "success": True,
                "pid": self.pid,
                "port": self.port,
                "smoke": {"stdout": self.smoke.stdout},
            }

    def fake_run_harness(**kwargs):
        assert os.environ["CHIRP_HOME"] == "C:/installed/Rook/app/chirp"
        calls.update(kwargs)
        return FakeHarnessResult()

    def require_installed_environment():
        monkeypatch.setenv("CHIRP_HOME", "C:/installed/Rook/app/chirp")
        return {"chirp_home": "C:/installed/Rook/app/chirp"}

    monkeypatch.setattr(proof, "_require_installed_live_environment", require_installed_environment)
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
    assert calls["smoke_timeout_seconds"] == 1860
    assert (
        result.details["progressive_discovery"]
        == live_envelope["details"]["progressive_discovery"]
    )


def test_owned_release_readiness_requires_progressive_evidence_on_success(
    monkeypatch, tmp_path: Path
):
    class FakeHarnessResult:
        success = True
        cleanup_status = proof.CleanupStatus.GRACEFUL_EXIT
        smoke = SimpleNamespace(returncode=0, stdout="harness completed\n", stderr="")

        def to_manifest_dict(self):
            return {"success": True, "smoke": {"stdout": self.smoke.stdout}}

    monkeypatch.setattr(proof, "_require_installed_live_environment", lambda: {})
    monkeypatch.setattr(
        proof, "run_rhino_runtime_harness", lambda **_: FakeHarnessResult()
    )

    result = proof.owned_release_readiness_gate(
        command=["python", "-m", "rook.local_testing_proof", "owned-release-readiness"],
        rhino_exe=Path("C:/Program Files/Rhino 8/System/Rhino.exe"),
        artifact_root=tmp_path,
        keep_rhino_on_failure=False,
        readiness_timeout_seconds=1.0,
        cleanup_timeout_seconds=1.0,
    )

    assert result.success is False
    assert result.failure_label == "progressive_discovery_failed"


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

    monkeypatch.setattr(proof, "_require_installed_live_environment", lambda: {})
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


def _forced_cleanup_live_envelope(*, success: bool = True) -> dict:
    component_guid = _test_guid("forced-cleanup-slow")
    return {
        "gate": "live_smoke",
        "success": success,
        "failure_label": None if success else "chirp_verification_failed",
        "details": {
            "progressive_discovery": {
                "target": "gh_status",
                "target_hidden": True,
            },
            "slow_inference": {
                "output": "slow-ok",
                "provider": {"request_count": 1},
                "chirp_create": {
                    "success": True,
                    "data": {"component_guid": component_guid},
                },
                "cleanup": {
                    "component_guid": component_guid,
                    "component_observed_after_attempt": True,
                    "component_removed": True,
                    "baseline_object_count": 0,
                    "final_object_count": 0,
                    "baseline_instance_guids": [],
                    "final_instance_guids": [],
                },
            },
        },
    }


def _forced_cleanup_harness(
    tmp_path: Path,
    *,
    envelope: dict | None = None,
    discovery_leftover: bool = False,
):
    pid = 4321
    port = 9876
    artifact_dir = tmp_path / "run"
    artifact_dir.mkdir()
    ready_record_path = artifact_dir / f"owned-discovery-instance-{pid}-native.json"
    ready_record_path.write_text(
        json.dumps(
            {
                "processId": pid,
                "pluginType": "native",
                "host": "127.0.0.1",
                "port": port,
            }
        ),
        encoding="utf-8",
    )
    discovery_path = tmp_path / f"instance-{pid}-native.json"
    if discovery_leftover:
        discovery_path.write_text("{}", encoding="utf-8")
    envelope = envelope or _forced_cleanup_live_envelope()
    smoke = SimpleNamespace(
        returncode=0 if envelope.get("success") is True else 1,
        timed_out=False,
        succeeded=envelope.get("success") is True,
        stdout=json.dumps(envelope),
        stderr="",
    )

    class FakeHarnessResult:
        success = False
        cleanup_status = proof.CleanupStatus.GRACEFUL_TIMEOUT_FORCED_KILL
        runscript_safety_unrecovered_path = None

        def __init__(self):
            self.pid = pid
            self.port = port
            self.artifact_dir = artifact_dir
            self.ready_record_path = ready_record_path
            self.smoke = smoke
            self.launch_outcome = {
                "ok": True,
                "pid": pid,
                "port": port,
                "discoveryRecordPath": str(discovery_path),
            }

        def to_manifest_dict(self):
            return {
                "success": False,
                "pid": self.pid,
                "port": self.port,
                "ready": {"record_snapshot_path": str(self.ready_record_path)},
                "smoke": {"stdout": self.smoke.stdout},
                "cleanup": {"status": self.cleanup_status.value},
                "launch_outcome": self.launch_outcome,
            }

    return FakeHarnessResult()


def test_owned_release_readiness_admits_verified_forced_cleanup_only_locally(
    monkeypatch, tmp_path: Path
):
    harness = _forced_cleanup_harness(tmp_path)
    monkeypatch.setattr(proof, "_require_installed_live_environment", lambda: {})
    monkeypatch.setattr(proof, "run_rhino_runtime_harness", lambda **_: harness)
    monkeypatch.setattr(proof, "_is_pid_alive", lambda pid: False)

    result = proof.owned_release_readiness_gate(
        command=["python", "-m", "rook.local_testing_proof", "owned-release-readiness"],
        rhino_exe=Path("C:/Program Files/Rhino 8/System/Rhino.exe"),
        artifact_root=tmp_path,
        keep_rhino_on_failure=False,
        readiness_timeout_seconds=1.0,
        cleanup_timeout_seconds=1.0,
    )

    assert result.success is True
    assert result.cleanup == {
        "attempted": True,
        "success": False,
        "label": "cleanup_failed",
        "details": {"status": "graceful_timeout_forced_kill"},
    }
    assert result.details["forced_cleanup_admission"] == {
        "admitted": True,
        "status": "graceful_timeout_forced_kill",
        "pid": 4321,
        "process_terminated": True,
        "discovery_record_removed": True,
    }


@pytest.mark.parametrize("failure_kind", ["body", "process", "discovery"])
def test_owned_release_readiness_rejects_unproven_forced_cleanup(
    monkeypatch, tmp_path: Path, failure_kind: str
):
    envelope = _forced_cleanup_live_envelope(success=failure_kind != "body")
    harness = _forced_cleanup_harness(
        tmp_path,
        envelope=envelope,
        discovery_leftover=failure_kind == "discovery",
    )
    monkeypatch.setattr(proof, "_require_installed_live_environment", lambda: {})
    monkeypatch.setattr(proof, "run_rhino_runtime_harness", lambda **_: harness)
    monkeypatch.setattr(proof, "_is_pid_alive", lambda pid: failure_kind == "process")

    result = proof.owned_release_readiness_gate(
        command=["python", "-m", "rook.local_testing_proof", "owned-release-readiness"],
        rhino_exe=Path("C:/Program Files/Rhino 8/System/Rhino.exe"),
        artifact_root=tmp_path,
        keep_rhino_on_failure=False,
        readiness_timeout_seconds=1.0,
        cleanup_timeout_seconds=1.0,
    )

    assert result.success is False
    assert result.failure_label == (
        "chirp_verification_failed" if failure_kind == "body" else "cleanup_failed"
    )


@pytest.mark.parametrize("failure_kind", ["component", "request_bool", "canvas_bool"])
def test_owned_release_readiness_rejects_malformed_forced_cleanup_evidence(
    monkeypatch, tmp_path: Path, failure_kind: str
):
    envelope = _forced_cleanup_live_envelope()
    slow = envelope["details"]["slow_inference"]
    if failure_kind == "component":
        slow["cleanup"]["component_guid"] = _test_guid("different-component")
    elif failure_kind == "request_bool":
        slow["provider"]["request_count"] = True
    else:
        slow["cleanup"]["baseline_object_count"] = False
    harness = _forced_cleanup_harness(tmp_path, envelope=envelope)
    monkeypatch.setattr(proof, "_require_installed_live_environment", lambda: {})
    monkeypatch.setattr(proof, "run_rhino_runtime_harness", lambda **_: harness)
    monkeypatch.setattr(proof, "_is_pid_alive", lambda pid: False)

    result = proof.owned_release_readiness_gate(
        command=["python", "-m", "rook.local_testing_proof", "owned-release-readiness"],
        rhino_exe=Path("C:/Program Files/Rhino 8/System/Rhino.exe"),
        artifact_root=tmp_path,
        keep_rhino_on_failure=False,
        readiness_timeout_seconds=1.0,
        cleanup_timeout_seconds=1.0,
    )

    assert result.success is False
    assert result.failure_label == "cleanup_failed"


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


def _post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=2.0) as response:
        return json.loads(response.read().decode("utf-8"))


def test_slow_provider_is_loopback_single_request_and_bounded(tmp_path: Path):
    with proof._slow_openai_provider(tmp_path, delay_seconds=0.02) as provider:
        assert provider.host == "127.0.0.1"
        assert provider.port > 0
        payload = _post_json(
            f"http://{provider.host}:{provider.port}/v1/chat/completions",
            {"model": "rook-timeout-acceptance", "messages": [{"role": "user", "content": "go"}]},
        )
        assert payload["choices"][0]["message"]["content"] == (
            "[[ ## result ## ]]\nslow-ok\n\n[[ ## completed ## ]]"
        )
        assert payload["usage"] == {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
        }
        assert provider.request_count == 1

    assert provider.thread.is_alive() is False
    receipt = json.loads(provider.request_path.read_text(encoding="utf-8"))
    assert receipt["path"] == "/v1/chat/completions"
    assert receipt["request"]["model"] == "rook-timeout-acceptance"


def test_slow_provider_cleanup_runs_after_body_failure(tmp_path: Path):
    provider = None
    with pytest.raises(RuntimeError, match="body failed"):
        with proof._slow_openai_provider(tmp_path, delay_seconds=0.02) as provider:
            raise RuntimeError("body failed")

    assert provider is not None
    assert provider.thread.is_alive() is False


def test_slow_provider_cleanup_interrupts_active_request(tmp_path: Path):
    client_failures = []
    client = None
    provider = None

    with pytest.raises(RuntimeError, match="body failed"):
        with proof._slow_openai_provider(tmp_path, delay_seconds=10.0) as provider:
            def request_provider():
                try:
                    _post_json(
                        f"http://{provider.host}:{provider.port}/v1/chat/completions",
                        {"model": "rook-timeout-acceptance", "messages": []},
                    )
                except BaseException as exc:
                    client_failures.append(exc)

            client = threading.Thread(target=request_provider, daemon=False)
            client.start()
            deadline = time.monotonic() + 2.0
            while provider.request_count == 0 and time.monotonic() < deadline:
                time.sleep(0.01)
            assert provider.request_count == 1
            raise RuntimeError("body failed")

    assert provider is not None
    assert client is not None
    client.join(timeout=2.0)
    assert client.is_alive() is False
    assert provider.thread.is_alive() is False
    assert client_failures


def test_slow_provider_preserves_body_and_cleanup_failures(monkeypatch, tmp_path: Path):
    original_stop = proof._stop_slow_provider

    def cleanup_then_fail(provider):
        original_stop(provider)
        raise RuntimeError("cleanup failed")

    monkeypatch.setattr(proof, "_stop_slow_provider", cleanup_then_fail)

    with pytest.raises(proof.ProofFailure) as captured:
        with proof._slow_openai_provider(tmp_path, delay_seconds=0.02):
            raise ValueError("body failed")

    assert captured.value.failure_label == "slow_provider_cleanup_failed"
    assert captured.value.details["body_failure"]["message"] == "body failed"
    assert captured.value.details["cleanup_failure"]["message"] == "cleanup failed"
