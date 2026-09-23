import json
from pathlib import Path

import pytest


def _touch_exe(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("exe", encoding="utf-8")
    return path


def _write_config(root: Path, executable: Path | str) -> Path:
    config = root / "config" / "mesh2splat.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        json.dumps({"mesh2splat": {"executable": str(executable)}}),
        encoding="utf-8",
    )
    return config


def _patch_roots(monkeypatch, mutable_root: Path, bundled_root: Path) -> None:
    from rook.mesh2splat import executable

    monkeypatch.setattr(
        executable, "get_mutable_knowledge_root", lambda: mutable_root
    )
    monkeypatch.setattr(
        executable, "get_bundled_knowledge_root", lambda: bundled_root
    )


def test_explicit_path_wins_and_allows_nonstandard_basename(tmp_path, monkeypatch):
    from rook.mesh2splat import executable
    from rook.mesh2splat.executable import resolve_mesh2splat_executable

    mutable_root = tmp_path / "mutable"
    bundled_root = tmp_path / "bundled"
    _patch_roots(monkeypatch, mutable_root, bundled_root)
    monkeypatch.setattr(
        executable,
        "bundled_mesh2splat_executable_path",
        lambda: tmp_path / "bundle-exe" / "Mesh2Splat.exe",
    )

    explicit = _touch_exe(tmp_path / "custom-tools" / "my-trusted-exporter.exe")
    env_exe = _touch_exe(tmp_path / "env" / "Mesh2Splat.exe")
    _write_config(mutable_root, _touch_exe(tmp_path / "mutable-exe" / "Mesh2Splat.exe"))

    result = resolve_mesh2splat_executable(
        str(explicit), env={"ROOK_MESH2SPLAT_EXE": str(env_exe)}
    )

    assert result.path == explicit.resolve()
    assert result.source == "explicit"
    assert result.source_requires_path is False
    assert result.diagnostics["selected"] == {
        "source": "explicit",
        "path": str(explicit.resolve()),
    }
    assert result.diagnostics["explicitTrustedOverride"] is True
    assert result.diagnostics["rejectedCandidates"] == []


def test_lookup_order_env_mutable_bundled_bundled_location_then_path(
    tmp_path, monkeypatch
):
    from rook.mesh2splat import executable
    from rook.mesh2splat.executable import resolve_mesh2splat_executable

    mutable_root = tmp_path / "mutable"
    bundled_root = tmp_path / "bundled"
    _patch_roots(monkeypatch, mutable_root, bundled_root)

    env_exe = _touch_exe(tmp_path / "env" / "Mesh2Splat.exe")
    mutable_exe = _touch_exe(tmp_path / "mutable-exe" / "Mesh2Splat.exe")
    bundled_config_exe = _touch_exe(
        tmp_path / "bundled-config-exe" / "Mesh2Splat.exe"
    )
    bundled_location_exe = _touch_exe(
        tmp_path / "bundled-location" / "Mesh2Splat.exe"
    )
    path_exe = _touch_exe(tmp_path / "on-path" / "Mesh2Splat.exe")
    _write_config(mutable_root, mutable_exe)
    _write_config(bundled_root, bundled_config_exe)
    monkeypatch.setattr(
        executable,
        "bundled_mesh2splat_executable_path",
        lambda: bundled_location_exe,
    )
    monkeypatch.setattr(
        executable.shutil,
        "which",
        lambda name, path=None: str(path_exe),
    )

    result = resolve_mesh2splat_executable(
        None,
        env={
            "ROOK_MESH2SPLAT_EXE": str(env_exe),
            "PATH": str(path_exe.parent),
        },
    )
    assert result.source == "environment"
    assert result.path == env_exe.resolve()

    result = resolve_mesh2splat_executable(None, env={"PATH": str(path_exe.parent)})
    assert result.source == "mutable_config"
    assert result.path == mutable_exe.resolve()

    mutable_root.joinpath("config", "mesh2splat.json").unlink()
    result = resolve_mesh2splat_executable(None, env={"PATH": str(path_exe.parent)})
    assert result.source == "bundled_config"
    assert result.path == bundled_config_exe.resolve()

    bundled_root.joinpath("config", "mesh2splat.json").unlink()
    result = resolve_mesh2splat_executable(None, env={"PATH": str(path_exe.parent)})
    assert result.source == "bundled_location"
    assert result.path == bundled_location_exe.resolve()

    bundled_location_exe.unlink()
    result = resolve_mesh2splat_executable(None, env={"PATH": str(path_exe.parent)})
    assert result.source == "path"
    assert result.path == path_exe.resolve()
    assert result.source_requires_path is True


def test_malformed_mutable_config_is_diagnostic_only_and_falls_back_to_bundled(
    tmp_path, monkeypatch
):
    from rook.mesh2splat.executable import resolve_mesh2splat_executable

    mutable_root = tmp_path / "mutable"
    bundled_root = tmp_path / "bundled"
    _patch_roots(monkeypatch, mutable_root, bundled_root)
    mutable_config = mutable_root / "config" / "mesh2splat.json"
    mutable_config.parent.mkdir(parents=True, exist_ok=True)
    mutable_config.write_text("{not json", encoding="utf-8")
    bundled_exe = _touch_exe(tmp_path / "bundled" / "bin" / "Mesh2Splat.exe")
    _write_config(bundled_root, bundled_exe)

    result = resolve_mesh2splat_executable(None, env={})

    assert result.source == "bundled_config"
    assert result.path == bundled_exe.resolve()
    assert {
        "source": "mutable_config",
        "path": str(mutable_config),
        "reason": "config_malformed",
    } in result.diagnostics["rejectedCandidates"]


def test_non_explicit_candidates_must_be_named_mesh2splat_exe(tmp_path, monkeypatch):
    from rook.mesh2splat import executable
    from rook.mesh2splat.executable import resolve_mesh2splat_executable

    mutable_root = tmp_path / "mutable"
    bundled_root = tmp_path / "bundled"
    _patch_roots(monkeypatch, mutable_root, bundled_root)

    env_exe = _touch_exe(tmp_path / "env" / "renamed.exe")
    config_exe = _touch_exe(tmp_path / "config" / "mesh2splat-cli.exe")
    bundled_exe = _touch_exe(tmp_path / "bundled-location" / "other.exe")
    path_exe = _touch_exe(tmp_path / "on-path" / "mesh2splat.cmd")
    _write_config(mutable_root, config_exe)
    monkeypatch.setattr(
        executable, "bundled_mesh2splat_executable_path", lambda: bundled_exe
    )
    monkeypatch.setattr(
        executable.shutil, "which", lambda name, path=None: str(path_exe)
    )

    with pytest.raises(executable.Mesh2SplatExecutableError) as exc:
        resolve_mesh2splat_executable(
            None,
            env={"ROOK_MESH2SPLAT_EXE": str(env_exe), "PATH": str(path_exe.parent)},
        )

    assert exc.value.code == "mesh2splat_not_found"
    reasons = {
        candidate["path"]: candidate["reason"]
        for candidate in exc.value.diagnostics["rejectedCandidates"]
    }
    assert reasons[str(env_exe)] == "unexpected_basename"
    assert reasons[str(config_exe)] == "unexpected_basename"
    assert reasons[str(bundled_exe)] == "unexpected_basename"
    assert reasons[str(path_exe)] == "unexpected_basename"


def test_non_explicit_candidates_must_resolve_to_mesh2splat_exe(
    tmp_path, monkeypatch
):
    from rook.mesh2splat import executable
    from rook.mesh2splat.executable import resolve_mesh2splat_executable

    mutable_root = tmp_path / "mutable"
    bundled_root = tmp_path / "bundled"
    _patch_roots(monkeypatch, mutable_root, bundled_root)
    monkeypatch.setattr(
        executable,
        "bundled_mesh2splat_executable_path",
        lambda: tmp_path / "missing" / "Mesh2Splat.exe",
    )
    target = _touch_exe(tmp_path / "target" / "not-mesh2splat.exe")
    symlink = tmp_path / "env" / "Mesh2Splat.exe"
    symlink.parent.mkdir(parents=True, exist_ok=True)
    try:
        symlink.symlink_to(target)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(executable.Mesh2SplatExecutableError) as exc:
        resolve_mesh2splat_executable(
            None,
            env={"ROOK_MESH2SPLAT_EXE": str(symlink)},
        )

    assert exc.value.code == "mesh2splat_not_found"
    assert {
        "source": "environment",
        "path": str(target.resolve()),
        "reason": "unexpected_basename",
    } in exc.value.diagnostics["rejectedCandidates"]


def test_path_lookup_uses_only_provided_env_path(tmp_path, monkeypatch):
    from rook.mesh2splat import executable
    from rook.mesh2splat.executable import resolve_mesh2splat_executable

    mutable_root = tmp_path / "mutable"
    bundled_root = tmp_path / "bundled"
    _patch_roots(monkeypatch, mutable_root, bundled_root)
    monkeypatch.setattr(
        executable,
        "bundled_mesh2splat_executable_path",
        lambda: tmp_path / "missing" / "Mesh2Splat.exe",
    )

    def fake_which(name, path=None):
        assert path is not None
        return None

    monkeypatch.setattr(executable.shutil, "which", fake_which)

    with pytest.raises(executable.Mesh2SplatExecutableError) as exc:
        resolve_mesh2splat_executable(None, env={})

    assert exc.value.code == "mesh2splat_not_found"
    assert {
        "source": "path",
        "path": "Mesh2Splat.exe",
        "reason": "path_env_missing",
    } in exc.value.diagnostics["rejectedCandidates"]


def test_invalid_explicit_path_fails_hard_without_fallback(tmp_path, monkeypatch):
    from rook.mesh2splat import executable
    from rook.mesh2splat.executable import resolve_mesh2splat_executable

    mutable_root = tmp_path / "mutable"
    bundled_root = tmp_path / "bundled"
    _patch_roots(monkeypatch, mutable_root, bundled_root)
    fallback = _touch_exe(tmp_path / "fallback" / "Mesh2Splat.exe")
    _write_config(mutable_root, fallback)

    missing_explicit = tmp_path / "missing" / "custom.exe"
    with pytest.raises(executable.Mesh2SplatExecutableError) as exc:
        resolve_mesh2splat_executable(str(missing_explicit), env={})

    assert exc.value.code == "invalid_executable"
    assert exc.value.diagnostics["explicitTrustedOverride"] is True
    assert exc.value.diagnostics["rejectedCandidates"] == [
        {
            "source": "explicit",
            "path": str(missing_explicit),
            "reason": "not_file",
        }
    ]


def test_no_hardcoded_developer_local_repo_path():
    from rook.mesh2splat import executable

    source = Path(executable.__file__).read_text(encoding="utf-8")

    # No developer-machine absolute path may be baked into the module.
    assert "C:/Users/" not in source and ("C:" + chr(92) + "Users" + chr(92)) not in source
