from __future__ import annotations

from pathlib import Path

from rook import runtime_paths


def test_direct_installed_venv_resolves_release_runtime_without_rook_env(monkeypatch, tmp_path: Path):
    runtime_root = tmp_path / "Rook"
    install_root = runtime_root / "app"
    mcp_server_dir = install_root / "mcp_server"

    monkeypatch.delenv("ROOK_INSTALL_ROOT", raising=False)
    monkeypatch.delenv("ROOK_DATA_DIR", raising=False)
    monkeypatch.delenv("ROOK_MODE", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(runtime_paths, "_cached_runtime_paths", None)
    monkeypatch.setattr(
        runtime_paths,
        "_repo_fallback_roots",
        lambda: (install_root, mcp_server_dir),
    )

    paths = runtime_paths.resolve_runtime_paths()

    assert paths.mode == "release"
    assert paths.install_root == install_root.resolve()
    assert paths.data_root == (runtime_root / "data").resolve()
    assert paths.logs_root == (runtime_root / "logs").resolve()
    assert paths.runtime_root == runtime_root.resolve()
    assert paths.mcp_server_dir == mcp_server_dir.resolve()


def test_release_knowledge_roots_never_resolve_under_venv(monkeypatch, tmp_path: Path):
    runtime_root = tmp_path / "Rook"
    install_root = runtime_root / "app"
    data_root = runtime_root / "data"
    venv_root = runtime_root / "venv"
    bundled_command_path = install_root / "knowledge" / "commands" / "command_knowledge.json"
    bundled_command_path.parent.mkdir(parents=True)
    bundled_command_path.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("ROOK_INSTALL_ROOT", str(install_root))
    monkeypatch.setenv("ROOK_DATA_DIR", str(data_root))
    monkeypatch.setenv("ROOK_MODE", "release")
    monkeypatch.setattr(runtime_paths, "_cached_runtime_paths", None)

    paths = runtime_paths.resolve_runtime_paths()
    bundled_root = runtime_paths.get_bundled_knowledge_root(paths)
    mutable_root = runtime_paths.get_mutable_knowledge_root(paths)
    readable_command_path = runtime_paths.resolve_readable_knowledge_path(
        "commands",
        "command_knowledge.json",
        runtime_paths=paths,
    )

    assert bundled_root == install_root.resolve() / "knowledge"
    assert mutable_root == data_root.resolve()
    assert readable_command_path == bundled_command_path.resolve()
    assert venv_root.resolve() not in readable_command_path.resolve().parents
