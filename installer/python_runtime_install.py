"""Install-time management for Rook's private Python runtime.

Stdlib-only. Imported by post_install.py after the installer has copied files.
"""

from __future__ import annotations

import json
import os
import hashlib
from dataclasses import dataclass
from pathlib import Path


SCHEMA_VERSION = 1
BOOTSTRAP_TOOL_REQUIREMENTS = ("pip==26.2.1", "setuptools==83.0.0")


@dataclass(frozen=True)
class RuntimeLayout:
    rook_root: Path
    app_dir: Path
    data_dir: Path
    private_python: Path
    rook_venv: Path
    chirp_venv: Path
    wheelhouse: Path
    bootstrap_lock: Path
    rook_lock: Path
    chirp_lock: Path
    runtime_manifest: Path
    install_state: Path

    @classmethod
    def from_rook_root(cls, rook_root: Path, python_version: str) -> "RuntimeLayout":
        app_dir = rook_root / "app"
        data_dir = rook_root / "data"
        return cls(
            rook_root=rook_root,
            app_dir=app_dir,
            data_dir=data_dir,
            private_python=rook_root
            / "python"
            / f"cpython-{python_version}"
            / "python.exe",
            rook_venv=rook_root / "venv",
            chirp_venv=app_dir / "chirp" / ".venv",
            wheelhouse=app_dir / "python-wheelhouse",
            bootstrap_lock=app_dir / "requirements-bootstrap-lock.txt",
            rook_lock=app_dir / "requirements-rook-lock.txt",
            chirp_lock=app_dir / "requirements-chirp-lock.txt",
            runtime_manifest=app_dir / "python-runtime-manifest.json",
            install_state=data_dir / "install-state.json",
        )


def _is_under_user_profile(entry: str) -> bool:
    profile = os.environ.get("USERPROFILE")
    if not profile or not entry:
        return False
    try:
        return os.path.normcase(os.path.normpath(entry)).startswith(
            os.path.normcase(os.path.normpath(profile)) + os.sep
        )
    except (TypeError, ValueError):
        return False


def sanitized_path_entries(path_value: str) -> list[str]:
    """PATH entries pip may see: everything outside the user profile.

    pip resolves every PATH entry (``Path(i).resolve()``) when it checks whether
    installed scripts are on PATH. On Windows 11 25H2 that traversal is refused
    for junctions under the user profile (e.g. scoop's ``apps\\<tool>\\current``)
    with ``[WinError 448] The path cannot be traversed because it contains an
    untrusted mount point``, which aborted the Rook venv install for a user with
    scoop on PATH. Nothing pip runs here needs a user-profile PATH entry: the
    interpreter, wheelhouse and lockfiles are all passed as absolute paths.
    """
    return [entry for entry in path_value.split(os.pathsep) if entry and not _is_under_user_profile(entry)]


def build_sanitized_python_env(require_virtualenv: bool) -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join(sanitized_path_entries(env.get("PATH", "")))
    for key in (
        "PYTHONHOME",
        "PYTHONPATH",
        "PIP_INDEX_URL",
        "PIP_EXTRA_INDEX_URL",
        "PIP_CONFIG_FILE",
    ):
        env.pop(key, None)
    env["PIP_NO_INDEX"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    if require_virtualenv:
        env["PIP_REQUIRE_VIRTUALENV"] = "1"
    else:
        env.pop("PIP_REQUIRE_VIRTUALENV", None)
    return env


def build_offline_pip_install_command(
    venv_python: Path,
    wheelhouse_dir: Path,
    requirements_lock: Path,
) -> list[str]:
    return [
        str(venv_python),
        "-m",
        "pip",
        "--isolated",
        "install",
        "--no-index",
        "--find-links",
        str(wheelhouse_dir),
        "--require-hashes",
        # Skip pip's "scripts not on PATH" scan: it resolves every PATH entry and
        # fails on user-profile junctions (WinError 448); see sanitized_path_entries.
        "--no-warn-script-location",
        "-r",
        str(requirements_lock),
    ]


def build_offline_pip_bootstrap_command(
    venv_python: Path,
    wheelhouse_dir: Path,
    requirements_bootstrap_lock: Path,
) -> list[str]:
    return build_offline_pip_install_command(
        venv_python,
        wheelhouse_dir,
        requirements_bootstrap_lock,
    )


def assert_offline_pip_command(command: list[str]) -> None:
    forbidden = {"--index-url", "--extra-index-url", "-i"}
    missing = {"--no-index", "--find-links", "--require-hashes"} - set(command)
    if missing:
        raise ValueError(f"offline pip command missing required flags: {sorted(missing)}")
    present_forbidden = forbidden.intersection(command)
    if present_forbidden:
        raise ValueError(
            f"offline pip command contains network index flags: {sorted(present_forbidden)}"
        )


def assert_local_wheelhouse_output(output: str) -> None:
    if "Looking in indexes:" in output:
        raise ValueError("pip output shows network index lookup")
    if "Looking in links:" not in output and "Processing " not in output:
        raise ValueError("pip output does not prove local wheelhouse use")


def needs_venv_recreate(
    install_state: dict,
    runtime_name: str,
    python_identity_hash: str,
    lockfile_sha256: str,
) -> bool:
    if install_state.get("schema_version") != SCHEMA_VERSION:
        return True
    runtime_state = install_state.get(runtime_name, {})
    return (
        runtime_state.get("python_identity_hash") != python_identity_hash
        or runtime_state.get("lockfile_sha256") != lockfile_sha256
    )


def read_install_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_site_packages_import(module_file: Path) -> bool:
    normalized = str(module_file).replace("\\", "/").lower()
    return "/site-packages/" in normalized


def write_install_state(path: Path, payload: dict) -> None:
    state = {"schema_version": SCHEMA_VERSION}
    state.update(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _slash(path: Path) -> str:
    return str(path).replace("\\", "/")


def build_release_mcp_env(
    install_dir: Path, data_dir: Path, chirp_dir: Path | None
) -> dict[str, str]:
    dspy_cache_dir = data_dir / "dspy-cache"
    env_vars = {
        "PYTHONPATH": "",
        "PYTHONHOME": "",
        "ROOK_INSTALL_ROOT": _slash(install_dir),
        "ROOK_DATA_DIR": _slash(data_dir),
        "ROOK_MODE": "release",
        "DSPY_CACHEDIR": _slash(dspy_cache_dir),
        "ROOK_DSPY_RESTRICT_PICKLE": "1",
    }
    if chirp_dir is not None:
        env_vars["CHIRP_HOME"] = _slash(chirp_dir)
    return env_vars


def build_chat_service_manifest(
    mcp_server_dir: Path,
    rook_venv_python: Path,
    release_mode: bool,
) -> dict:
    rook_root = rook_venv_python.parent.parent.parent
    app_dir = rook_root / "app"
    data_dir = rook_root / "data"
    chirp_dir = app_dir / "chirp"
    return {
        "pythonPath": str(rook_venv_python),
        "workingDirectory": str(mcp_server_dir),
        "module": "rook.agent.chat.service_main",
        "owner": "rhino-panel",
        "pythonPathEntries": [] if release_mode else [str(mcp_server_dir / "src")],
        "environment": build_release_mcp_env(app_dir, data_dir, chirp_dir)
        if release_mode
        else {},
    }
