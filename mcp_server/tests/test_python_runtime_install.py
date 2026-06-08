from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def load_runtime_install():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "installer" / "python_runtime_install.py"
    spec = importlib.util.spec_from_file_location("rook_python_runtime_install", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_pip_command_is_offline_and_hash_locked(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    command = runtime.build_offline_pip_install_command(
        tmp_path / "venv" / "Scripts" / "python.exe",
        tmp_path / "wheelhouse",
        tmp_path / "requirements-rook-lock.txt",
    )

    assert command[:4] == [
        str(tmp_path / "venv" / "Scripts" / "python.exe"),
        "-m",
        "pip",
        "--isolated",
    ]
    assert "install" in command
    assert "--no-index" in command
    assert "--find-links" in command
    assert "--require-hashes" in command
    assert "--index-url" not in command
    assert "--extra-index-url" not in command


def test_sanitized_install_env_removes_python_and_pip_index_state(monkeypatch) -> None:
    runtime = load_runtime_install()
    monkeypatch.setenv("PYTHONHOME", "C:/bad")
    monkeypatch.setenv("PYTHONPATH", "C:/bad")
    monkeypatch.setenv("PIP_INDEX_URL", "https://bad.example/simple")
    monkeypatch.setenv("PIP_EXTRA_INDEX_URL", "https://bad.example/extra")

    env = runtime.build_sanitized_python_env(require_virtualenv=True)

    assert "PYTHONHOME" not in env
    assert "PYTHONPATH" not in env
    assert "PIP_INDEX_URL" not in env
    assert "PIP_EXTRA_INDEX_URL" not in env
    assert env["PIP_NO_INDEX"] == "1"
    assert env["PIP_DISABLE_PIP_VERSION_CHECK"] == "1"
    assert env["PIP_REQUIRE_VIRTUALENV"] == "1"


def test_venv_invalidates_on_python_or_lock_hash_change(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    state = {
        "schema_version": 1,
        "python": {"identity_hash": "old-python"},
        "rook": {"lockfile_sha256": "old-lock"},
    }

    assert runtime.needs_venv_recreate(state, "rook", "new-python", "old-lock")
    assert runtime.needs_venv_recreate(state, "rook", "old-python", "new-lock")
    assert not runtime.needs_venv_recreate(state, "rook", "old-python", "old-lock")


def test_import_origin_must_be_site_packages(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    site_packages = tmp_path / "venv" / "Lib" / "site-packages" / "rook" / "__init__.py"
    source_tree = tmp_path / "app" / "mcp_server" / "src" / "rook" / "__init__.py"

    assert runtime.is_site_packages_import(site_packages)
    assert not runtime.is_site_packages_import(source_tree)


def test_install_state_has_schema_version(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    path = tmp_path / "data" / "install-state.json"
    runtime.write_install_state(
        path,
        {
            "python": {"path": "C:/Rook/python/cpython-3.11.9/python.exe"},
            "rook": {"venv_path": "C:/Rook/venv"},
            "chirp": {"venv_path": "C:/Rook/app/chirp/.venv"},
        },
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["python"]["path"].endswith("python.exe")


def test_release_chat_manifest_has_no_source_pythonpath_entries(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    manifest = runtime.build_chat_service_manifest(
        mcp_server_dir=tmp_path / "app" / "mcp_server",
        rook_venv_python=tmp_path / "venv" / "Scripts" / "python.exe",
        release_mode=True,
    )

    assert manifest["pythonPath"].endswith("venv\\Scripts\\python.exe") or manifest[
        "pythonPath"
    ].endswith("venv/Scripts/python.exe")
    assert manifest["workingDirectory"].endswith("mcp_server")
    assert manifest["pythonPathEntries"] == []


def test_mcp_env_points_to_chirp_home_and_clears_python_paths(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    env = runtime.build_release_mcp_env(
        install_dir=tmp_path / "app",
        data_dir=tmp_path / "data",
        chirp_dir=tmp_path / "app" / "chirp",
    )

    assert env["ROOK_INSTALL_ROOT"].endswith("app")
    assert env["ROOK_DATA_DIR"].endswith("data")
    assert env["ROOK_MODE"] == "release"
    assert env["PYTHONHOME"] == ""
    assert env["PYTHONPATH"] == ""
    assert env["CHIRP_HOME"].endswith("app/chirp")


def test_runtime_layout_uses_private_python_and_two_venvs(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    layout = runtime.RuntimeLayout.from_rook_root(tmp_path / "Rook", "3.11.9")

    assert (
        layout.private_python
        == tmp_path / "Rook" / "python" / "cpython-3.11.9" / "python.exe"
    )
    assert layout.rook_venv == tmp_path / "Rook" / "venv"
    assert layout.chirp_venv == tmp_path / "Rook" / "app" / "chirp" / ".venv"
    assert layout.wheelhouse == tmp_path / "Rook" / "app" / "python-wheelhouse"


def test_pip_output_evidence_rejects_index_lookup() -> None:
    runtime = load_runtime_install()
    runtime.assert_local_wheelhouse_output(
        "Looking in links: C:/Rook/app/python-wheelhouse\nProcessing rook_mcp.whl"
    )

    try:
        runtime.assert_local_wheelhouse_output("Looking in indexes: https://pypi.org/simple")
    except ValueError as exc:
        assert "network index" in str(exc)
    else:
        raise AssertionError("expected network index output to be rejected")
