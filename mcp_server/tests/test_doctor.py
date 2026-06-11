from pathlib import Path

import rook.doctor as doctor
from rook.doctor import (
    _build_probe_server_parameters,
    _config_targets,
    _managed_companion_payloads,
    _probe_stderr_buffer,
    _should_check_claude,
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
            "DSPY_CACHEDIR": str(runtime_paths.data_root / "dspy-cache").replace("\\", "/"),
            "ROOK_DSPY_RESTRICT_PICKLE": "1",
            "CHIRP_HOME": "C:/custom/chirp",
        },
    }

    ok, detail = _validate_mcp_entry(entry, runtime_paths, expected_python_path=str(python_path))

    assert ok is True
    assert detail is None


def test_expected_mcp_entry_includes_dspy_cache_release_env(tmp_path: Path):
    runtime_paths = _runtime_paths(tmp_path)
    chirp_home = runtime_paths.install_root / "chirp"
    chirp_home.mkdir()

    entry = doctor._build_expected_mcp_entry(
        runtime_paths,
        str(tmp_path / "venv" / "Scripts" / "python.exe"),
        chirp_home=str(chirp_home),
    )

    env = entry["env"]
    assert env["DSPY_CACHEDIR"] == str(runtime_paths.data_root / "dspy-cache").replace("\\", "/")
    assert env["ROOK_DSPY_RESTRICT_PICKLE"] == "1"
    assert env["CHIRP_HOME"] == str(chirp_home).replace("\\", "/")


def test_validate_mcp_entry_rejects_missing_dspy_cache_contract(tmp_path: Path):
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
        },
    }

    ok, detail = doctor._validate_mcp_entry(
        entry,
        runtime_paths,
        expected_python_path=str(python_path),
    )

    assert ok is False
    assert detail == "env DSPY_CACHEDIR does not match expected value"


def test_config_targets_use_supported_codex_skill_root(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    targets = _config_targets()

    assert targets["codex_skill_root"] == tmp_path / ".codex" / "skills"


def test_should_check_codex_detects_supported_skill_root(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / ".codex" / "skills").mkdir(parents=True)

    assert _should_check_codex(force=False) is True


def test_should_check_claude_ignores_marketplace_skill_root(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    (tmp_path / ".claude" / "skills").mkdir(parents=True)

    assert _should_check_claude(force=False) is False
    assert _should_check_claude(force=True) is True


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
    python_normalized = str(python_path).replace("\\", "/")
    mcp_server_normalized = str(runtime_paths.mcp_server_dir).replace("\\", "/")
    install_root_normalized = str(runtime_paths.install_root).replace("\\", "/")
    data_root_normalized = str(runtime_paths.data_root).replace("\\", "/")
    config_path.write_text(
        "\n".join(
            [
                "[mcp_servers.rook]",
                f'command = "{python_normalized}"',
                'args = ["-m", "rook"]',
                f'cwd = "{mcp_server_normalized}"',
                "",
                "[mcp_servers.rook.env]",
                'PYTHONPATH = ""',
                'PYTHONHOME = ""',
                f'ROOK_INSTALL_ROOT = "{install_root_normalized}"',
                f'ROOK_DATA_DIR = "{data_root_normalized}"',
                'ROOK_MODE = "release"',
                f'DSPY_CACHEDIR = "{data_root_normalized}/dspy-cache"',
                'ROOK_DSPY_RESTRICT_PICKLE = "1"',
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


def test_validate_codex_config_parses_on_python310_without_tomllib(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(doctor, "tomllib", None)
    monkeypatch.setattr(doctor, "TOMLDecodeError", ValueError)
    runtime_paths = _runtime_paths(tmp_path)
    python_path = tmp_path / "python.exe"
    python_path.write_text("")
    config_path = tmp_path / "config.toml"
    python_normalized = str(python_path).replace("\\", "/")
    mcp_server_normalized = str(runtime_paths.mcp_server_dir).replace("\\", "/")
    install_root_normalized = str(runtime_paths.install_root).replace("\\", "/")
    data_root_normalized = str(runtime_paths.data_root).replace("\\", "/")
    config_path.write_text(
        "\n".join(
            [
                "[mcp_servers.rook]",
                f'command = "{python_normalized}"',
                'args = ["-m", "rook"]',
                f'cwd = "{mcp_server_normalized}"',
                "startup_timeout_sec = 30",
                "",
                "[mcp_servers.rook.env]",
                'PYTHONPATH = ""',
                'PYTHONHOME = ""',
                f'ROOK_INSTALL_ROOT = "{install_root_normalized}"',
                f'ROOK_DATA_DIR = "{data_root_normalized}"',
                'ROOK_MODE = "release"',
                f'DSPY_CACHEDIR = "{data_root_normalized}/dspy-cache"',
                'ROOK_DSPY_RESTRICT_PICKLE = "1"',
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


def test_write_claude_user_config_never_clobbers_malformed_config(tmp_path: Path, monkeypatch):
    """Regression for the 1.5.11 release smoke (PR #238 re-review): doctor
    --fix must NEVER overwrite an existing ~/.claude.json it cannot parse —
    that destroys the user's projects and other MCP entries."""
    import pytest

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    runtime_paths = _runtime_paths(tmp_path)
    target = _config_targets()["claude_user"]
    target.parent.mkdir(parents=True, exist_ok=True)
    broken = b'{ "mcpServers": { broken json \x9d\xff'
    target.write_bytes(broken)

    with pytest.raises(doctor._UnreadableConfigError):
        doctor._write_claude_user_config(runtime_paths, str(tmp_path / "python.exe"))

    # Byte-identical: nothing was rewritten.
    assert target.read_bytes() == broken


def test_read_json_for_update_missing_file_and_cp1252_fallback(tmp_path: Path):
    """Missing file -> fresh {}; legacy cp1252 content (invalid UTF-8 start
    byte 0xE9 for an accented char) -> parsed via fallback, not rejected."""
    import json as _json

    assert doctor._read_json_for_update(tmp_path / "absent.json") == {}

    legacy = tmp_path / "legacy.json"
    legacy.write_bytes(_json.dumps({"projects": {"Café": {}}}, ensure_ascii=False).encode("cp1252"))
    parsed = doctor._read_json_for_update(legacy)
    assert "Café" in parsed["projects"]


def test_run_doctor_fix_survives_invalid_utf8_claude_config(tmp_path: Path, monkeypatch):
    """Re-review repro: run_doctor(fix=True, check_claude=True,
    skip_handshake=True) against an invalid-UTF-8 ~/.claude.json must not
    crash, must leave the file byte-identical, and must report both the fix
    skip and the config validation as WARNING severity (non-fatal)."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    runtime_paths = _runtime_paths(tmp_path)
    monkeypatch.setattr(doctor, "resolve_runtime_paths", lambda: runtime_paths)

    target = _config_targets()["claude_user"]
    target.parent.mkdir(parents=True, exist_ok=True)
    broken = b"\xff\xfe{ not utf8 \x9d"
    target.write_bytes(broken)

    result = doctor.run_doctor(fix=True, check_claude=True, skip_handshake=True)

    assert target.read_bytes() == broken
    fix_checks = [c for c in result.checks if c.name == "--fix Claude integration"]
    assert fix_checks and fix_checks[0].severity == "warning"
    config_checks = [c for c in result.checks if c.name == "Claude Code config"]
    assert config_checks and config_checks[0].severity == "warning"
    assert "left untouched" in (config_checks[0].detail or "")
