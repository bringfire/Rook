"""Install-time management for Rook's private Python runtime.

Stdlib-only. Imported by post_install.py after the installer has copied files.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


SCHEMA_VERSION = 1


def build_sanitized_python_env(require_virtualenv: bool) -> dict[str, str]:
    env = os.environ.copy()
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
        "-r",
        str(requirements_lock),
    ]


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


def needs_venv_recreate(
    install_state: dict,
    runtime_name: str,
    python_identity_hash: str,
    lockfile_sha256: str,
) -> bool:
    if install_state.get("schema_version") != SCHEMA_VERSION:
        return True
    if install_state.get("python", {}).get("identity_hash") != python_identity_hash:
        return True
    runtime_state = install_state.get(runtime_name, {})
    return runtime_state.get("lockfile_sha256") != lockfile_sha256


def is_site_packages_import(module_file: Path) -> bool:
    normalized = str(module_file).replace("\\", "/").lower()
    return "/site-packages/" in normalized


def write_install_state(path: Path, payload: dict) -> None:
    state = {"schema_version": SCHEMA_VERSION}
    state.update(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
