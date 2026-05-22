from pathlib import Path

from rook.doctor import (
    _build_probe_server_parameters,
    _config_targets,
    _managed_companion_payloads,
    _probe_stderr_buffer,
    _should_check_codex,
    _upsert_toml_section,
    _validate_codex_config,
    _validate_mcp_entry,
)
from rook.runtime_paths import RuntimePaths


def _runtime_paths(tmp_path: Path) -> RuntimePaths:
    install_root = tmp_path / "install"
    data_root = tmp_path / "data"
    logs_root = tmp_path / "logs"
    mcp_server_dir = install_root / "mcp_server"
    install_root.mkdir(parents=True)
    data_root.mkdir(parents=True)
    logs_root.mkdir(parents=True)
    mcp_server_dir.mkdir(parents=True)
    return RuntimePaths(
        mode="release",
        install_root=install_root,
        data_root=data_root,
        logs_root=logs_root,
        runtime_root=tmp_path,
        mcp_server_dir=mcp_server_dir,
        repo_root=tmp_path,
    )


def test_managed_companion_payloads_use_runtime_child_folders(tmp_path: Path):
    payloads = dict(_managed_companion_payloads(tmp_path / "RookNative"))

    assert payloads == {
        "net8.0": tmp_path / "RookNative" / "net8.0" / "Rook.rhp",
        "net7.0": tmp_path / "RookNative" / "net7.0" / "Rook.rhp",
        "net48": tmp_path / "RookNative" / "net48" / "Rook.rhp",
    }
    assert tmp_path / "RookNative" / "Rook.rhp" not in payloads.values()


def test_validate_mcp_entry_checks_required_fields_but_ignores_optional_chirp_home(tmp_path: Path):
    runtime_paths = _runtime_paths(tmp_path)
    python_path = tmp_path / "python.exe"
    python_path.write_text("")

    entry = {
        "type": "stdio",
        "command": str(python_path),
        "args": ["-m", "rook"],
        "cwd": str(runtime_paths.mcp_server_dir),
        "env": {
            "PYTHONPATH": "",
            "PYTHONHOME": "",
            "ROOK_INSTALL_ROOT": str(runtime_paths.install_root).replace("\\", "/"),
            "ROOK_DATA_DIR": str(runtime_paths.data_root).replace("\\", "/"),
            "ROOK_MODE": "release",
            "CHIRP_HOME": "C:/custom/chirp",
        },
    }

    ok, detail = _validate_mcp_entry(entry, runtime_paths, expected_python_path=str(python_path))

    assert ok is True
    assert detail is None


def test_config_targets_use_supported_codex_skill_root(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    targets = _config_targets()

    assert targets["codex_skill_root"] == tmp_path / ".codex" / "skills"


def test_should_check_codex_detects_supported_skill_root(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / ".codex" / "skills").mkdir(parents=True)

    assert _should_check_codex(force=False) is True


def test_probe_stdio_uses_replacement_decoding_for_windows_encoded_output(tmp_path: Path):
    runtime_paths = _runtime_paths(tmp_path)
    python_path = tmp_path / "python.exe"
    python_path.write_text("")

    server = _build_probe_server_parameters(runtime_paths, str(python_path))

    assert server.encoding_error_handler == "replace"
    with _probe_stderr_buffer() as stderr_buffer:
        stderr_buffer.buffer.write(b"cp1252 dash: \x97")
        stderr_buffer.seek(0)
        assert stderr_buffer.read() == "cp1252 dash: \ufffd"


def test_validate_codex_config_parses_semantically(tmp_path: Path):
    runtime_paths = _runtime_paths(tmp_path)
    python_path = tmp_path / "python.exe"
    python_path.write_text("")
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                "[mcp_servers.rook]",
                f'command = "{str(python_path).replace("\\", "/")}"',
                'args = ["-m", "rook"]',
                f'cwd = "{str(runtime_paths.mcp_server_dir).replace("\\", "/")}"',
                "",
                "[mcp_servers.rook.env]",
                'PYTHONPATH = ""',
                'PYTHONHOME = ""',
                f'ROOK_INSTALL_ROOT = "{str(runtime_paths.install_root).replace("\\", "/")}"',
                f'ROOK_DATA_DIR = "{str(runtime_paths.data_root).replace("\\", "/")}"',
                'ROOK_MODE = "release"',
                "",
                "[other]",
                'value = "kept"',
            ]
        ),
        encoding="utf-8",
    )

    ok, detail = _validate_codex_config(config_path, runtime_paths, expected_python_path=str(python_path))

    assert ok is True
    assert detail is None


def test_upsert_toml_section_replaces_only_target_section():
    original = "\n".join(
        [
            "[alpha]",
            'value = "a"',
            "",
            "[mcp_servers.rook]",
            'command = "old"',
            "",
            "[beta]",
            'value = "b"',
            "",
        ]
    )

    updated = _upsert_toml_section(
        original,
        "[mcp_servers.rook]",
        "\n".join(
            [
                "[mcp_servers.rook]",
                'command = "new"',
                'args = ["-m", "rook"]',
            ]
        ),
    )

    assert '[alpha]\nvalue = "a"' in updated
    assert '[mcp_servers.rook]\ncommand = "new"\nargs = ["-m", "rook"]' in updated
    assert '[beta]\nvalue = "b"' in updated
    assert 'command = "old"' not in updated


def test_validate_mcp_entry_fails_for_wrong_args(tmp_path: Path):
    runtime_paths = _runtime_paths(tmp_path)
    python_path = tmp_path / "python.exe"
    python_path.write_text("")
    entry = {
        "type": "stdio",
        "command": str(python_path),
        "args": ["-m", "not-rook"],
        "cwd": str(runtime_paths.mcp_server_dir),
        "env": {
            "PYTHONPATH": "",
            "PYTHONHOME": "",
            "ROOK_INSTALL_ROOT": str(runtime_paths.install_root).replace("\\", "/"),
            "ROOK_DATA_DIR": str(runtime_paths.data_root).replace("\\", "/"),
            "ROOK_MODE": "release",
        },
    }

    ok, detail = _validate_mcp_entry(entry, runtime_paths, expected_python_path=str(python_path))

    assert ok is False
    assert detail == "entry args do not match ['-m', 'rook']"


def test_validate_codex_config_fails_for_invalid_toml(tmp_path: Path):
    runtime_paths = _runtime_paths(tmp_path)
    config_path = tmp_path / "config.toml"
    config_path.write_text("[mcp_servers.rook\nbroken = true", encoding="utf-8")

    ok, detail = _validate_codex_config(config_path, runtime_paths)

    assert ok is False
    assert detail is not None
    assert detail.startswith("invalid TOML:")


def test_upsert_toml_section_appends_when_missing():
    original = '[alpha]\nvalue = "a"\n'

    updated = _upsert_toml_section(
        original,
        "[mcp_servers.rook]",
        "\n".join(
            [
                "[mcp_servers.rook]",
                'command = "new"',
            ]
        ),
    )

    assert updated.startswith(original)
    assert '[mcp_servers.rook]\ncommand = "new"' in updated


def test_upsert_toml_section_replaces_child_sections_with_parent():
    original = "\n".join(
        [
            "[mcp_servers.rook]",
            'command = "old"',
            "",
            "[mcp_servers.rook.env]",
            'ROOK_MODE = "release"',
            "",
            "[beta]",
            'value = "b"',
            "",
        ]
    )

    updated = _upsert_toml_section(
        original,
        "[mcp_servers.rook]",
        "\n".join(
            [
                "[mcp_servers.rook]",
                'command = "new"',
                "",
                "[mcp_servers.rook.env]",
                'ROOK_MODE = "dev"',
            ]
        ),
    )

    assert updated.count("[mcp_servers.rook.env]") == 1
    assert 'ROOK_MODE = "dev"' in updated
    assert 'ROOK_MODE = "release"' not in updated
    assert '[beta]\nvalue = "b"' in updated
