from __future__ import annotations

import importlib.util
import json
import subprocess
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


def load_post_install():
    repo_root = Path(__file__).resolve().parents[2]
    installer_dir = repo_root / "installer"
    sys.path.insert(0, str(installer_dir))
    try:
        module_path = installer_dir / "post_install.py"
        spec = importlib.util.spec_from_file_location("rook_post_install", module_path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(installer_dir))


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


def test_bootstrap_pip_command_is_offline_and_hash_locked(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    command = runtime.build_offline_pip_bootstrap_command(
        tmp_path / "venv" / "Scripts" / "python.exe",
        tmp_path / "wheelhouse",
        tmp_path / "requirements-bootstrap-lock.txt",
    )

    runtime.assert_offline_pip_command(command)
    assert "requirements-bootstrap-lock.txt" in command[-1]
    assert "--no-index" in command
    assert "--find-links" in command
    assert "--require-hashes" in command


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
        "rook": {"python_identity_hash": "old-python", "lockfile_sha256": "old-lock"},
    }

    assert runtime.needs_venv_recreate(state, "rook", "new-python", "old-lock")
    assert runtime.needs_venv_recreate(state, "rook", "old-python", "new-lock")
    assert not runtime.needs_venv_recreate(state, "rook", "old-python", "old-lock")


def test_venv_invalidates_per_runtime_when_rook_installs_before_chirp(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    post_install = load_post_install()
    layout = runtime.RuntimeLayout.from_rook_root(tmp_path / "Rook", "3.11.9")
    old_runtime_hash = "0" * 64
    new_runtime_hash = "1" * 64
    old_lock_hash = "2" * 64

    runtime.write_install_state(
        layout.install_state,
        {
            "python": {"identity_hash": old_runtime_hash},
            "rook": {
                "python_identity_hash": old_runtime_hash,
                "lockfile_sha256": old_lock_hash,
            },
            "chirp": {
                "python_identity_hash": old_runtime_hash,
                "lockfile_sha256": old_lock_hash,
            },
        },
    )

    post_install._record_install_state(
        layout=layout,
        runtime_name="rook",
        venv_dir=layout.rook_venv,
        venv_python=layout.rook_venv / "Scripts" / "python.exe",
        lock=layout.rook_lock,
        python_identity_hash=new_runtime_hash,
        lockfile_sha256=old_lock_hash,
        pip_check_output="No broken requirements found.",
    )

    updated_state = runtime.read_install_state(layout.install_state)

    assert updated_state["rook"]["python_identity_hash"] == new_runtime_hash
    assert updated_state["chirp"]["python_identity_hash"] == old_runtime_hash
    assert runtime.needs_venv_recreate(
        updated_state,
        "chirp",
        new_runtime_hash,
        old_lock_hash,
    )


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


def test_post_install_extends_seeded_summary(tmp_path: Path) -> None:
    post_install = load_post_install()
    runtime_root = tmp_path / "Rook"
    logs = runtime_root / "logs"
    logs.mkdir(parents=True)
    summary = logs / "post_install_summary.json"
    summary.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "phase_reached": "preflight",
                "preflight": {"server_count": 5, "owners": ["Claude", "Codex"]},
            }
        ),
        encoding="utf-8",
    )

    post_install._configure_install_logging(runtime_root)
    post_install._update_install_summary(
        runtime_root, phase_reached="finalizer-started", final_outcome="running"
    )

    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["preflight"]["server_count"] == 5
    assert payload["phase_reached"] == "finalizer-started"
    assert payload["final_outcome"] == "running"


def test_post_install_summary_schema_version_is_pinned_to_one(tmp_path: Path) -> None:
    post_install = load_post_install()
    runtime_root = tmp_path / "Rook"
    logs = runtime_root / "logs"
    logs.mkdir(parents=True)
    summary = logs / "post_install_summary.json"
    summary.write_text(
        json.dumps(
            {
                "schema_version": 99,
                "phase_reached": "preflight",
                "preflight": {"server_count": 5},
            }
        ),
        encoding="utf-8",
    )

    post_install._update_install_summary(runtime_root, final_outcome="running")

    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["phase_reached"] == "preflight"
    assert payload["preflight"]["server_count"] == 5
    assert payload["final_outcome"] == "running"


def test_last_gasp_handler_writes_traceback(tmp_path: Path, monkeypatch) -> None:
    post_install = load_post_install()
    runtime_root = tmp_path / "Rook"

    def boom() -> int:
        raise RuntimeError("forced install failure")

    monkeypatch.setattr(post_install, "main", boom)

    result = post_install._run_with_last_gasp(runtime_root=runtime_root)

    assert result == 1
    log = (runtime_root / "logs" / "post_install.log").read_text(encoding="utf-8")
    assert "forced install failure" in log
    assert "Traceback" in log


def test_uninstall_cleanup_runs_without_install_log_handler(
    tmp_path: Path, monkeypatch
) -> None:
    post_install = load_post_install()
    runtime_root = tmp_path / "Rook"
    post_install._configure_install_logging(runtime_root)

    def assert_logging_closed() -> None:
        assert post_install._INSTALL_LOGGER.handlers == []

    monkeypatch.setattr(post_install, "uninstall_cleanup", assert_logging_closed)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "post_install.py",
            "--uninstall",
            "--runtime-root",
            str(runtime_root),
        ],
    )

    assert post_install.main() == 0


def test_last_gasp_uses_runtime_root_from_argv(
    tmp_path: Path, monkeypatch
) -> None:
    post_install = load_post_install()
    default_parent = tmp_path / "default-local-appdata"
    default_root = default_parent / "Rook"
    custom_root = tmp_path / "custom-runtime"

    def boom() -> int:
        raise RuntimeError("custom runtime failure")

    monkeypatch.setenv("LOCALAPPDATA", str(default_parent))
    monkeypatch.setattr(post_install, "main", boom)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "post_install.py",
            "--runtime-root",
            str(custom_root),
        ],
    )

    result = post_install._run_with_last_gasp()

    assert result == 1
    custom_log = custom_root / "logs" / "post_install.log"
    custom_summary = custom_root / "logs" / "post_install_summary.json"
    assert "custom runtime failure" in custom_log.read_text(encoding="utf-8")
    assert json.loads(custom_summary.read_text(encoding="utf-8"))["final_outcome"] == "failed"
    assert not (default_root / "logs" / "post_install.log").exists()
    assert not (default_root / "logs" / "post_install_summary.json").exists()


def test_post_install_recreates_stale_venv_and_writes_install_state(
    tmp_path: Path, monkeypatch
) -> None:
    runtime = load_runtime_install()
    post_install = load_post_install()
    layout = runtime.RuntimeLayout.from_rook_root(tmp_path / "Rook", "3.11.9")

    layout.private_python.parent.mkdir(parents=True)
    layout.private_python.write_text("private python", encoding="utf-8")
    layout.wheelhouse.mkdir(parents=True)
    layout.bootstrap_lock.parent.mkdir(parents=True, exist_ok=True)
    layout.bootstrap_lock.write_text("pip==26.1.2 --hash=sha256:abc\n", encoding="utf-8")
    layout.rook_lock.write_text("rook-mcp==1.5.10 --hash=sha256:def\n", encoding="utf-8")
    layout.runtime_manifest.write_text('{"schema_version":1}', encoding="utf-8")

    stale_python = post_install.get_venv_python(layout.rook_venv)
    stale_python.parent.mkdir(parents=True)
    stale_python.write_text("stale", encoding="utf-8")
    stale_marker = layout.rook_venv / "stale-package.txt"
    stale_marker.write_text("orphaned package", encoding="utf-8")
    runtime.write_install_state(
        layout.install_state,
        {
            "python": {"identity_hash": "old-runtime"},
            "rook": {"lockfile_sha256": "old-lock"},
        },
    )

    def fake_run(command, *, env, timeout=post_install.INSTALL_COMMAND_TIMEOUT_SECONDS):
        if command[:3] == [str(layout.private_python), "-m", "venv"]:
            created_python = post_install.get_venv_python(Path(command[3]))
            created_python.parent.mkdir(parents=True, exist_ok=True)
            created_python.write_text("fresh", encoding="utf-8")
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="Looking in links: C:/Rook/app/python-wheelhouse\nNo broken requirements found.",
            stderr="",
        )

    monkeypatch.setattr(post_install, "_run_install_command", fake_run)

    venv_python = post_install._install_from_wheelhouse(
        "rook-mcp",
        layout,
        layout.rook_venv,
        layout.rook_lock,
        "rook",
    )

    assert venv_python == stale_python
    assert not stale_marker.exists()
    install_state = json.loads(layout.install_state.read_text(encoding="utf-8"))
    assert install_state["schema_version"] == 1
    assert install_state["python"]["path"] == str(layout.private_python)
    assert install_state["python"]["identity_hash"]
    assert install_state["rook"]["venv_path"] == str(layout.rook_venv)
    assert install_state["rook"]["python_identity_hash"] == install_state["python"]["identity_hash"]
    assert install_state["rook"]["lockfile_sha256"]


def test_install_mcp_server_seeds_discovery_directory(tmp_path: Path, monkeypatch) -> None:
    post_install = load_post_install()
    runtime_root = tmp_path / "Rook"
    managed_python = runtime_root / "venv" / "Scripts" / "python.exe"

    def fake_install(*args, **kwargs):
        managed_python.parent.mkdir(parents=True)
        managed_python.write_text("fake", encoding="utf-8")
        return managed_python

    monkeypatch.setattr(post_install, "_install_from_wheelhouse", fake_install)

    result = post_install.install_mcp_server(tmp_path / "app" / "mcp_server", runtime_root)

    assert result == managed_python
    assert (runtime_root / "discovery").is_dir()


def test_post_install_fails_closed_when_stale_venv_cannot_be_deleted(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    runtime = load_runtime_install()
    post_install = load_post_install()
    layout = runtime.RuntimeLayout.from_rook_root(tmp_path / "Rook", "3.11.9")

    layout.private_python.parent.mkdir(parents=True)
    layout.private_python.write_text("private python", encoding="utf-8")
    layout.wheelhouse.mkdir(parents=True)
    layout.bootstrap_lock.parent.mkdir(parents=True, exist_ok=True)
    layout.bootstrap_lock.write_text("pip==26.1.2 --hash=sha256:abc\n", encoding="utf-8")
    layout.rook_lock.write_text("rook-mcp==1.5.10 --hash=sha256:def\n", encoding="utf-8")
    layout.runtime_manifest.write_text('{"schema_version":1}', encoding="utf-8")

    stale_python = post_install.get_venv_python(layout.rook_venv)
    stale_python.parent.mkdir(parents=True)
    stale_python.write_text("stale", encoding="utf-8")
    runtime.write_install_state(
        layout.install_state,
        {
            "python": {"identity_hash": "old-runtime"},
            "rook": {"lockfile_sha256": "old-lock"},
        },
    )

    install_commands: list[list[str]] = []

    def locked_delete(path):
        raise PermissionError("venv file is locked")

    def fake_run(command, *, env, timeout=post_install.INSTALL_COMMAND_TIMEOUT_SECONDS):
        install_commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(post_install.shutil, "rmtree", locked_delete)
    monkeypatch.setattr(post_install, "_run_install_command", fake_run)

    result = post_install._install_from_wheelhouse(
        "rook-mcp",
        layout,
        layout.rook_venv,
        layout.rook_lock,
        "rook",
    )

    assert result is None
    assert install_commands == []
    assert "Close Rhino/Revit" in capsys.readouterr().out


def test_post_install_requires_runtime_manifest_input(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    post_install = load_post_install()
    layout = runtime.RuntimeLayout.from_rook_root(tmp_path / "Rook", "3.11.9")

    layout.private_python.parent.mkdir(parents=True)
    layout.private_python.write_text("private python", encoding="utf-8")
    layout.wheelhouse.mkdir(parents=True)
    layout.bootstrap_lock.parent.mkdir(parents=True, exist_ok=True)
    layout.bootstrap_lock.write_text("pip==26.1.2 --hash=sha256:abc\n", encoding="utf-8")
    layout.rook_lock.write_text("rook-mcp==1.5.10 --hash=sha256:def\n", encoding="utf-8")

    assert post_install._install_from_wheelhouse(
        "rook-mcp",
        layout,
        layout.rook_venv,
        layout.rook_lock,
        "rook",
    ) is None


def test_post_install_main_fails_when_selected_chirp_install_fails(
    tmp_path: Path, monkeypatch
) -> None:
    post_install = load_post_install()
    install_dir = tmp_path / "app"
    mcp_server_dir = install_dir / "mcp_server"
    chirp_dir = install_dir / "chirp"
    mcp_server_dir.mkdir(parents=True)
    chirp_dir.mkdir()
    managed_python = tmp_path / "Rook" / "venv" / "Scripts" / "python.exe"
    managed_python.parent.mkdir(parents=True)
    managed_python.write_text("fake", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "post_install.py",
            "--install-dir",
            str(install_dir),
            "--mcp-server-dir",
            str(mcp_server_dir),
            "--runtime-root",
            str(tmp_path / "Rook"),
            "--chirp-dir",
            str(chirp_dir),
            "--skip-validation",
        ],
    )
    monkeypatch.setattr(post_install, "install_mcp_server", lambda *args, **kwargs: managed_python)
    monkeypatch.setattr(post_install, "install_chirp", lambda *args, **kwargs: False)
    monkeypatch.setattr(post_install, "configure_claude_code", lambda *args, **kwargs: True)
    monkeypatch.setattr(post_install, "configure_claude_desktop", lambda *args, **kwargs: True)
    monkeypatch.setattr(post_install, "configure_codex", lambda *args, **kwargs: True)
    monkeypatch.setattr(post_install, "install_user_assets", lambda *args, **kwargs: True)
    monkeypatch.setattr(post_install, "write_chat_service_manifest", lambda *args, **kwargs: None)
    monkeypatch.setattr(post_install, "create_env_examples", lambda *args, **kwargs: None)

    assert post_install.main() == 1


def test_post_install_main_fails_when_chat_manifest_write_fails(
    tmp_path: Path, monkeypatch
) -> None:
    post_install = load_post_install()
    install_dir = tmp_path / "app"
    mcp_server_dir = install_dir / "mcp_server"
    mcp_server_dir.mkdir(parents=True)
    managed_python = tmp_path / "Rook" / "venv" / "Scripts" / "python.exe"
    managed_python.parent.mkdir(parents=True)
    managed_python.write_text("fake", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "post_install.py",
            "--install-dir",
            str(install_dir),
            "--mcp-server-dir",
            str(mcp_server_dir),
            "--runtime-root",
            str(tmp_path / "Rook"),
            "--skip-validation",
        ],
    )
    monkeypatch.setattr(post_install, "install_mcp_server", lambda *args, **kwargs: managed_python)
    monkeypatch.setattr(post_install, "configure_claude_code", lambda *args, **kwargs: True)
    monkeypatch.setattr(post_install, "configure_claude_desktop", lambda *args, **kwargs: True)
    monkeypatch.setattr(post_install, "configure_codex", lambda *args, **kwargs: True)
    monkeypatch.setattr(post_install, "install_user_assets", lambda *args, **kwargs: True)
    monkeypatch.setattr(post_install, "write_chat_service_manifest", lambda *args, **kwargs: False)
    monkeypatch.setattr(post_install, "create_env_examples", lambda *args, **kwargs: None)

    assert post_install.main() == 1


def test_post_install_main_fails_when_selected_codex_assets_fail(
    tmp_path: Path, monkeypatch
) -> None:
    post_install = load_post_install()
    install_dir = tmp_path / "app"
    mcp_server_dir = install_dir / "mcp_server"
    mcp_server_dir.mkdir(parents=True)
    managed_python = tmp_path / "Rook" / "venv" / "Scripts" / "python.exe"
    managed_python.parent.mkdir(parents=True)
    managed_python.write_text("fake", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "post_install.py",
            "--install-dir",
            str(install_dir),
            "--mcp-server-dir",
            str(mcp_server_dir),
            "--runtime-root",
            str(tmp_path / "Rook"),
            "--codex",
            "--skip-validation",
        ],
    )
    monkeypatch.setattr(post_install, "install_mcp_server", lambda *args, **kwargs: managed_python)
    monkeypatch.setattr(post_install, "configure_codex", lambda *args, **kwargs: True)
    monkeypatch.setattr(post_install, "install_user_assets", lambda *args, **kwargs: False)
    monkeypatch.setattr(post_install, "write_chat_service_manifest", lambda *args, **kwargs: True)
    monkeypatch.setattr(post_install, "create_env_examples", lambda *args, **kwargs: None)

    assert post_install.main() == 1


def test_post_install_validation_invokes_doctor_fix_for_selected_clients(
    tmp_path: Path, monkeypatch
) -> None:
    post_install = load_post_install()
    install_dir = tmp_path / "Rook" / "app"
    runtime_root = tmp_path / "Rook"
    mcp_server_dir = install_dir / "mcp_server"
    mcp_server_dir.mkdir(parents=True)
    (runtime_root / "venv").mkdir(parents=True)
    (runtime_root / "data").mkdir()
    (runtime_root / "logs").mkdir()
    chirp_python = install_dir / "chirp" / ".venv" / "Scripts" / "python.exe"
    chirp_python.parent.mkdir(parents=True)
    chirp_python.write_text("fake", encoding="utf-8")
    python_path = str(runtime_root / "venv" / "Scripts" / "python.exe")
    commands = []

    class Completed:
        returncode = 0
        stdout = json.dumps(
            {
                "checks": [
                    {"name": "Claude Code config", "ok": True},
                    {"name": "Codex config", "ok": True},
                    {"name": "Codex skills installed", "ok": True},
                ],
                "warnings": [],
                "fixes_applied": [
                    "updated C:/Users/test/.claude.json",
                    "updated C:/Users/test/.codex/config.toml",
                ],
            }
        )
        stderr = ""

    def fake_run(command, **kwargs):
        commands.append(command)
        return Completed()

    monkeypatch.setattr(post_install.subprocess, "run", fake_run)

    assert post_install.validate(
        install_dir=install_dir,
        runtime_root=runtime_root,
        python_path=python_path,
        install_plugins=False,
        install_claude=True,
        install_codex=True,
        chirp_dir=install_dir / "chirp",
    )

    doctor_command = next(command for command in commands if "-m" in command and "rook" in command)
    assert "--fix" in doctor_command
    assert "--claude" in doctor_command
    assert "--codex" in doctor_command


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
    assert manifest["environment"]["DSPY_CACHEDIR"].endswith("data/dspy-cache")
    assert manifest["environment"]["ROOK_DSPY_RESTRICT_PICKLE"] == "1"


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
    assert env["DSPY_CACHEDIR"].endswith("data/dspy-cache")
    assert env["ROOK_DSPY_RESTRICT_PICKLE"] == "1"
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
    assert (
        layout.bootstrap_lock
        == tmp_path / "Rook" / "app" / "requirements-bootstrap-lock.txt"
    )


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


def test_public_install_ignores_user_python_and_pip_contamination(
    tmp_path: Path, monkeypatch
) -> None:
    runtime = load_runtime_install()
    fake_user_python = tmp_path / "UserPython" / "python.exe"
    fake_user_python.parent.mkdir()
    fake_user_python.write_text("not real", encoding="utf-8")

    monkeypatch.setenv("PATH", str(fake_user_python.parent))
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "source-shadow"))
    monkeypatch.setenv("PYTHONHOME", str(tmp_path / "bad-pythonhome"))
    monkeypatch.setenv("PIP_INDEX_URL", "https://bad.example/simple")
    monkeypatch.setenv("PIP_EXTRA_INDEX_URL", "https://bad.example/extra")

    layout = runtime.RuntimeLayout.from_rook_root(tmp_path / "Rook", "3.11.9")
    env = runtime.build_sanitized_python_env(require_virtualenv=True)
    command = runtime.build_offline_pip_install_command(
        layout.rook_venv / "Scripts" / "python.exe",
        layout.wheelhouse,
        layout.rook_lock,
    )
    bootstrap_command = runtime.build_offline_pip_bootstrap_command(
        layout.rook_venv / "Scripts" / "python.exe",
        layout.wheelhouse,
        layout.bootstrap_lock,
    )

    runtime.assert_offline_pip_command(command)
    runtime.assert_offline_pip_command(bootstrap_command)
    assert str(fake_user_python) not in " ".join(command)
    assert str(fake_user_python) not in " ".join(bootstrap_command)
    assert command[0] == str(layout.rook_venv / "Scripts" / "python.exe")
    assert bootstrap_command[0] == str(layout.rook_venv / "Scripts" / "python.exe")
    assert env["PIP_NO_INDEX"] == "1"
    assert "PIP_INDEX_URL" not in env
    assert "PIP_EXTRA_INDEX_URL" not in env
    assert "PYTHONPATH" not in env
    assert "PYTHONHOME" not in env


def test_install_from_wheelhouse_uses_guard_and_retries_full_rebuild(
    tmp_path: Path, monkeypatch
) -> None:
    runtime = load_runtime_install()
    post_install = load_post_install()
    layout = runtime.RuntimeLayout.from_rook_root(tmp_path / "Rook", "3.11.9")

    layout.private_python.parent.mkdir(parents=True)
    layout.private_python.write_text("private python", encoding="utf-8")
    layout.wheelhouse.mkdir(parents=True)
    layout.bootstrap_lock.parent.mkdir(parents=True, exist_ok=True)
    layout.bootstrap_lock.write_text("pip==26.1.2 --hash=sha256:abc\n", encoding="utf-8")
    layout.rook_lock.write_text("rook-mcp==1.5.10 --hash=sha256:def\n", encoding="utf-8")
    layout.runtime_manifest.write_text('{"schema_version":1}', encoding="utf-8")
    summary = layout.rook_root / "logs" / "post_install_summary.json"
    summary.parent.mkdir(parents=True)
    summary.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "phase_reached": "preflight",
                "preflight": {"server_count": 5},
            }
        ),
        encoding="utf-8",
    )
    stale_python = post_install.get_venv_python(layout.rook_venv)
    stale_python.parent.mkdir(parents=True)
    stale_python.write_text("stale", encoding="utf-8")

    guard_events: list[str] = []

    class FakeGuard:
        def __init__(self, label, **kwargs):
            self.label = label

        def __enter__(self):
            guard_events.append(f"enter:{self.label}")
            return self

        def __exit__(self, exc_type, exc, tb):
            guard_events.append(f"exit:{self.label}")
            return False

    monkeypatch.setattr(
        post_install, "_make_rebuild_guard", lambda label, runtime_root: FakeGuard(label)
    )

    attempts = {"install": 0}

    def fake_run(command, *, env, timeout=post_install.INSTALL_COMMAND_TIMEOUT_SECONDS):
        if command[:3] == [str(layout.private_python), "-m", "venv"]:
            created_python = post_install.get_venv_python(Path(command[3]))
            created_python.parent.mkdir(parents=True, exist_ok=True)
            created_python.write_text("fresh", encoding="utf-8")
        if (
            "-m" in command
            and "pip" in command
            and "install" in command
            and str(layout.rook_lock) in command
        ):
            attempts["install"] += 1
            if attempts["install"] == 1:
                return subprocess.CompletedProcess(
                    command, 1, stdout="", stderr="access denied"
                )
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="Looking in links: C:/Rook/app/python-wheelhouse\nNo broken requirements found.",
            stderr="",
        )

    monkeypatch.setattr(post_install, "_run_install_command", fake_run)

    venv_python = post_install._install_from_wheelhouse(
        "rook-mcp",
        layout,
        layout.rook_venv,
        layout.rook_lock,
        "rook",
    )

    assert venv_python == stale_python
    assert attempts["install"] == 2
    assert guard_events == [
        "enter:rook-mcp",
        "exit:rook-mcp",
        "enter:rook-mcp",
        "exit:rook-mcp",
    ]
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["preflight"]["server_count"] == 5
    assert payload["venv_rebuilds"]["rook"]["guard_label"] == "rook-mcp"
    assert payload["venv_rebuilds"]["rook"]["retry_count"] == 1
    assert payload["venv_rebuilds"]["rook"]["outcome"] == "success"


def test_chirp_install_uses_separate_guard_window(
    tmp_path: Path, monkeypatch
) -> None:
    post_install = load_post_install()
    runtime_root = tmp_path / "Rook"
    chirp_dir = runtime_root / "app" / "chirp"
    chirp_dir.mkdir(parents=True)
    labels: list[str] = []

    monkeypatch.setattr(
        post_install,
        "_install_from_wheelhouse",
        lambda label, layout, venv_dir, lock, runtime_name: labels.append(label)
        or (venv_dir / "Scripts" / "python.exe"),
    )

    assert post_install.install_chirp(chirp_dir, runtime_root) is True
    assert labels == ["Chirp"]
