from __future__ import annotations

import importlib.util
import subprocess
import sys
import re
import shutil
from pathlib import Path

import pytest

from rook.agent.chat import prime_runtime_artifact as artifact
from .test_prime_runtime_artifact import PAYLOAD, metadata, write_payload


REPO = Path(__file__).resolve().parents[2]


def load_post_install(monkeypatch):
    monkeypatch.syspath_prepend(str(REPO / "installer"))
    spec = importlib.util.spec_from_file_location("task10_post_install", REPO / "installer/post_install.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("exit_code", [0, 1])
def test_real_post_install_main_promotes_with_installed_wheel_before_chat_publication(tmp_path, monkeypatch, exit_code):
    module = load_post_install(monkeypatch)
    install = tmp_path / "app"
    install.mkdir()
    runtime = tmp_path / "runtime"
    incoming = install / "prime/.incoming/attempt"
    incoming.mkdir(parents=True)
    python = runtime / "venv/Scripts/python.exe"
    events = []
    monkeypatch.setattr(module, "_configure_install_logging", lambda *a: None)
    monkeypatch.setattr(module, "_update_install_summary", lambda *a, **k: None)
    monkeypatch.setattr(module, "cleanup_retired_codex_skills", lambda *a: None)
    monkeypatch.setattr(module, "get_runtime_paths", lambda root: (install, runtime / "data", runtime / "logs"))
    monkeypatch.setattr(module, "install_mcp_server", lambda *a: events.append("wheel") or python)
    monkeypatch.setattr(module, "install_user_assets", lambda *a, **k: True)
    monkeypatch.setattr(module, "create_env_examples", lambda *a: None)
    monkeypatch.setattr(module, "write_chat_service_manifest", lambda *a: events.append("chat") or True)

    def run(argv, **kwargs):
        assert events == ["wheel"]
        assert argv == [str(python), "-I", "-m", "rook.agent.chat.prime_runtime_artifact", "promote",
                        "--incoming-root", str(incoming), "--prime-root", str(install / "prime")]
        assert kwargs["shell"] is False and kwargs["check"] is False
        events.append("promote")
        return subprocess.CompletedProcess(argv, exit_code)

    monkeypatch.setattr(module.subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["post_install.py", "--install-dir", str(install), "--mcp-server-dir", str(install / "mcp_server"),
                                    "--runtime-root", str(runtime), "--prime-incoming-dir", str(incoming), "--skip-validation"])
    assert module.main() == exit_code
    assert events == (["wheel", "promote", "chat"] if exit_code == 0 else ["wheel", "promote"])


def test_install_upgrade_repair_rollback_and_uninstall_preserve_durable_data(tmp_path, monkeypatch):
    local = tmp_path / "Local"
    roaming = tmp_path / "Roaming"
    install = local / "Rook/app"
    data = local / "Rook/data/rookchat/acp/v1"
    retained = {"sessions/session.jsonl": b"Prime-owned\n", "presentation/00000001.json": b"UI-only\n",
                "claims/session.open.claim": b"", "conversations/session.json": b"association\n"}
    write_payload(data, retained)
    iss = (REPO / "installer/RookSetup.iss").read_text(encoding="utf-8")
    deletion = re.search(r"(?ms)^\[InstallDelete\](.*?)(?=^\[)", iss).group(1)

    def apply_install_delete():
        for line in deletion.splitlines():
            if not line.startswith("Type:"): continue
            name = re.search(r'Name: "([^"]+)"', line).group(1)
            path = Path(name.replace("{app}", str(install)).replace("{localappdata}", str(local))
                        .replace("{userappdata}", str(roaming)).replace("\\", "/"))
            assert path.is_relative_to(tmp_path)
            if path.is_dir(): shutil.rmtree(path)
            else: path.unlink(missing_ok=True)

    history = {}
    versions = []
    for phase in ("install", "upgrade", "repair", "rollback"):
        apply_install_delete()
        for relative, content in retained.items(): assert (data / relative).read_bytes() == content
        for runtime_id, files in history.items():
            root = install / "prime/runtimes" / runtime_id
            assert {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()} == files
        incoming = install / "prime/.incoming" / phase
        files = {**PAYLOAD, "pi.exe": b"version2" if phase in {"upgrade", "repair"} else b"version1"}
        write_payload(incoming, files)
        runtime_id = artifact.create_runtime_manifest(incoming, metadata(files))
        pointer = install / "prime/current.json"
        if versions: assert artifact.read_current_runtime_id(install / "prime") == versions[-1]
        else: assert not pointer.exists()
        artifact.promote_incoming_runtime(incoming, install / "prime")
        assert artifact.read_current_runtime_id(install / "prime") == runtime_id
        versions.append(runtime_id)
        root = install / "prime/runtimes" / runtime_id
        history[runtime_id] = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert versions[0] == versions[3] and versions[1] == versions[2] and len(history) == 2

    module = load_post_install(monkeypatch)
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("APPDATA", str(roaming))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "Home"))
    monkeypatch.setattr(module, "__file__", str(install / "post_install.py"))
    monkeypatch.setattr(module.shutil, "which", lambda name: None)
    monkeypatch.setattr(module.tempfile, "gettempdir", lambda: str(tmp_path / "Temp"))
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: pytest.fail("uninstall fixture cannot launch a process"))
    monkeypatch.setattr(sys, "argv", ["post_install.py", "--uninstall"])
    assert module.main() == 0
    assert not install.exists()
    assert {p.relative_to(data).as_posix(): p.read_bytes() for p in data.rglob("*") if p.is_file()} == retained
