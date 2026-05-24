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
