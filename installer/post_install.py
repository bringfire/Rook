"""Rook post-install setup - called by the Inno Setup installer.

This script runs after the installer copies files. It handles:
  1. Create a managed Rook runtime under %LOCALAPPDATA%\\Rook
  2. Install the rook-mcp Python package from the bundled wheelhouse
  3. Set up Chirp adapter service from the bundled wheelhouse
  4. Register rook MCP server in documented user-scope client config
  5. Merge Rook config into Claude Desktop config (if installed)
  6. Generate user-level config.toml for OpenAI Codex CLI
  7. Copy curated Codex skills to ~/.codex/skills (Claude Code gets skills via the marketplace plugin)
  8. Validate the installation

Uses only stdlib so it can run before dependencies are installed.
"""

import argparse
import json
import logging
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import process_rebuild_guard
import python_runtime_install


MANAGED_COMPANION_RUNTIMES = ("net8.0", "net7.0", "net48")
PRIVATE_PYTHON_VERSION = "3.11.9"
PROFILE_ENV_VAR = "ROOK_MCP_TOOL_PROFILE"
INSTALL_COMMAND_TIMEOUT_SECONDS = 1800
_INSTALL_LOGGER = logging.getLogger("rook.post_install")
_INSTALL_LOGGING_CONFIGURED = False
_INSTALL_LOG_PATH: Path | None = None


def _codex_on_path() -> bool:
    """Check if the Codex CLI is available on PATH."""
    return shutil.which("codex") is not None


def find_python() -> str:
    """Return the bootstrap Python executable path."""
    return sys.executable


def get_runtime_root(explicit_root: str | None = None) -> Path:
    if explicit_root:
        return Path(explicit_root)
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "Rook"
    return Path.home() / "AppData" / "Local" / "Rook"


def get_runtime_paths(runtime_root: Path) -> tuple[Path, Path, Path]:
    return runtime_root / "venv", runtime_root / "data", runtime_root / "logs"


def _summary_path(runtime_root: Path) -> Path:
    return runtime_root / "logs" / "post_install_summary.json"


def _post_install_log_path(runtime_root: Path) -> Path:
    return runtime_root / "logs" / "post_install.log"


def _configure_install_logging(runtime_root: Path) -> None:
    global _INSTALL_LOGGING_CONFIGURED, _INSTALL_LOG_PATH
    log_path = _post_install_log_path(runtime_root)
    if _INSTALL_LOGGING_CONFIGURED and _INSTALL_LOG_PATH == log_path:
        return

    log_path.parent.mkdir(parents=True, exist_ok=True)
    _close_install_logging()

    handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    formatter = logging.Formatter("%(asctime)sZ %(levelname)s %(message)s")
    formatter.converter = time.gmtime
    handler.setFormatter(formatter)
    _INSTALL_LOGGER.setLevel(logging.INFO)
    _INSTALL_LOGGER.addHandler(handler)
    _INSTALL_LOGGER.propagate = False
    _INSTALL_LOGGING_CONFIGURED = True
    _INSTALL_LOG_PATH = log_path
    _INSTALL_LOGGER.info("post_install logging configured")


def _close_install_logging() -> None:
    global _INSTALL_LOGGING_CONFIGURED, _INSTALL_LOG_PATH
    for existing in list(_INSTALL_LOGGER.handlers):
        _INSTALL_LOGGER.removeHandler(existing)
        existing.close()
    _INSTALL_LOGGING_CONFIGURED = False
    _INSTALL_LOG_PATH = None


def _read_install_summary(runtime_root: Path) -> dict:
    path = _summary_path(runtime_root)
    if not path.exists():
        return {"schema_version": 1}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": 1}
    return payload if isinstance(payload, dict) else {"schema_version": 1}


def _write_install_summary(runtime_root: Path, payload: dict) -> None:
    payload = {**payload, "schema_version": 1}
    path = _summary_path(runtime_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _update_install_summary(runtime_root: Path, **updates) -> None:
    payload = _read_install_summary(runtime_root)
    payload.update({key: value for key, value in updates.items() if value is not None})
    _write_install_summary(runtime_root, payload)


def _append_install_summary_warnings(payload: dict, warnings: list[str]) -> None:
    if not warnings:
        return
    existing = payload.get("warnings")
    if not isinstance(existing, list):
        existing = []
    seen = {str(item) for item in existing}
    for warning in warnings:
        if warning not in seen:
            existing.append(warning)
            seen.add(warning)
    payload["warnings"] = existing


def get_venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _make_rebuild_guard(label: str, runtime_root: Path):
    return process_rebuild_guard.RebuildGuard(
        label=label,
        rook_root=str(runtime_root),
        current_pid=os.getpid(),
    )


def _combined_output(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(part for part in (result.stdout, result.stderr) if part)


def _run_install_command(
    command: list[str],
    *,
    env: dict[str, str],
    timeout: int = INSTALL_COMMAND_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    command_text = " ".join(command)
    print(f"Running: {command_text}")
    _INSTALL_LOGGER.info("Running: %s", command_text)
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if result.stdout:
        print(result.stdout)
        _INSTALL_LOGGER.info("stdout:\n%s", result.stdout)
    if result.stderr:
        print(result.stderr)
        _INSTALL_LOGGER.info("stderr:\n%s", result.stderr)
    return result


def _ensure_private_runtime_inputs(layout: python_runtime_install.RuntimeLayout, lock: Path) -> bool:
    required = [
        (layout.private_python, "private Python runtime"),
        (layout.wheelhouse, "Python wheelhouse"),
        (layout.bootstrap_lock, "bootstrap requirements lock"),
        (layout.installer_tools_lock, "installer tools lock"),
        (layout.runtime_manifest, "Python runtime manifest"),
        (lock, "requirements lock"),
    ]
    for path, label in required:
        if not path.exists():
            print(f"Missing {label}: {path}")
            return False
    return True


_BUNDLED_UV: dict[Path, python_runtime_install.BundledTool] = {}


def _bundled_uv(
    layout: python_runtime_install.RuntimeLayout,
) -> python_runtime_install.BundledTool | None:
    """uv.exe from the hash-locked wheelhouse wheel, extracted once per finalizer run."""
    if layout.rook_root in _BUNDLED_UV:
        return _BUNDLED_UV[layout.rook_root]
    try:
        tool = python_runtime_install.extract_bundled_uv(
            layout.wheelhouse,
            layout.installer_tools_lock,
            layout.installer_cache / "tools",
        )
    except (OSError, ValueError, KeyError) as exc:
        print(f"Could not prepare the bundled uv installer tool: {exc}")
        _INSTALL_LOGGER.error("bundled uv extraction failed: %r", exc)
        return None
    _INSTALL_LOGGER.info("bundled uv ready: %s", tool.evidence())
    _BUNDLED_UV[layout.rook_root] = tool
    return tool


def _remove_uv_cache(label: str, cache_dir: Path) -> None:
    try:
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
    except OSError as exc:
        # Not fatal: the venv does not depend on the cache (hardlinks survive it),
        # and the finalizer removes the whole installer-cache root at exit.
        _INSTALL_LOGGER.warning("%s uv cache cleanup failed at %s: %r", label, cache_dir, exc)


def _remove_installer_cache(runtime_root: Path) -> None:
    """Drop uv caches and the extracted uv.exe; runs on every finalizer exit."""
    installer_cache = python_runtime_install.RuntimeLayout.from_rook_root(
        runtime_root, PRIVATE_PYTHON_VERSION
    ).installer_cache
    _BUNDLED_UV.pop(runtime_root, None)
    try:
        if installer_cache.exists():
            shutil.rmtree(installer_cache)
    except OSError as exc:
        _INSTALL_LOGGER.warning("installer cache cleanup failed at %s: %r", installer_cache, exc)


def _create_venv(layout: python_runtime_install.RuntimeLayout, venv_dir: Path) -> Path | None:
    venv_python = get_venv_python(venv_dir)
    if venv_python.exists():
        return venv_python

    print(f"Creating virtual environment at {venv_dir}...")
    # --without-pip: ensurepip costs ~15 s per venv; uv installs the pinned pip +
    # setuptools from the bootstrap lock instead.
    result = _run_install_command(
        [str(layout.private_python), "-m", "venv", "--without-pip", str(venv_dir)],
        env=python_runtime_install.build_sanitized_python_env(require_virtualenv=False),
        timeout=600,
    )
    if result.returncode != 0:
        print(f"venv creation failed with exit code {result.returncode}")
        return None
    if not venv_python.exists():
        print(f"venv Python not found at {venv_python}")
        return None
    return venv_python


def _remove_stale_venv(label: str, venv_dir: Path) -> bool:
    try:
        shutil.rmtree(venv_dir)
    except OSError as exc:
        print(
            f"Could not remove stale {label} virtual environment at {venv_dir}: {exc}. "
            "Close Rhino/Revit and any Rook Python processes, then rerun the installer. "
            "If the directory is still locked, reboot and repair the installation."
        )
        return False
    if venv_dir.exists():
        print(
            f"Could not remove stale {label} virtual environment at {venv_dir}. "
            "Close Rhino/Revit and any Rook Python processes, then rerun the installer. "
            "If the directory is still locked, reboot and repair the installation."
        )
        return False
    return True


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _record_install_state(
    layout: python_runtime_install.RuntimeLayout,
    runtime_name: str,
    venv_dir: Path,
    venv_python: Path,
    lock: Path,
    python_identity_hash: str,
    lockfile_sha256: str,
    pip_check_output: str,
    installer_tool: dict[str, str],
) -> None:
    state = python_runtime_install.read_install_state(layout.install_state)
    state.pop("schema_version", None)
    state["python"] = {
        "path": str(layout.private_python),
        "version": PRIVATE_PYTHON_VERSION,
        "identity_hash": python_identity_hash,
        "runtime_manifest_path": str(layout.runtime_manifest),
        "runtime_manifest_sha256": python_identity_hash,
    }
    state[runtime_name] = {
        "venv_path": str(venv_dir),
        "python_path": str(venv_python),
        "python_identity_hash": python_identity_hash,
        "lockfile_path": str(lock),
        "lockfile_sha256": lockfile_sha256,
        "installed_utc": _utc_now(),
        "pip_check": pip_check_output.strip(),
        # The tool that installed this venv, and proof it installed exactly the locks.
        "installer_tool": installer_tool,
        "freeze_matches_locks": True,
    }
    python_runtime_install.write_install_state(layout.install_state, state)


def _record_venv_rebuild_summary(
    runtime_root: Path,
    runtime_name: str,
    label: str,
    retry_count: int,
    outcome: str,
    failure_stage: str | None = None,
    guard_close_failures: list[str] | None = None,
    guard_thread_died_unexpectedly: bool = False,
) -> None:
    payload = _read_install_summary(runtime_root)
    rebuilds = payload.get("venv_rebuilds")
    if not isinstance(rebuilds, dict):
        rebuilds = {}
    entry = {
        "guard_label": label,
        "retry_count": retry_count,
        "outcome": outcome,
        "updated_utc": _utc_now(),
    }
    if failure_stage is not None:
        entry["failure_stage"] = failure_stage
    if guard_close_failures:
        entry["guard_close_failures"] = guard_close_failures
    if guard_thread_died_unexpectedly:
        entry["guard_thread_died_unexpectedly"] = True
    rebuilds[runtime_name] = entry
    payload["venv_rebuilds"] = rebuilds
    warnings = [
        f"{label} rebuild guard close failure: {failure}"
        for failure in (guard_close_failures or [])
    ]
    if guard_thread_died_unexpectedly:
        warnings.append(f"{label} rebuild guard sweep thread died unexpectedly")
    _append_install_summary_warnings(payload, warnings)
    _write_install_summary(runtime_root, payload)


def _collect_rebuild_guard_health(label: str, guard) -> tuple[list[str], bool]:
    close_failures = [str(failure) for failure in getattr(guard, "close_failures", [])]
    for failure in close_failures:
        _INSTALL_LOGGER.error("%s rebuild guard close failure: %s", label, failure)

    thread_died = bool(getattr(guard, "thread_died_unexpectedly", False))
    if thread_died:
        _INSTALL_LOGGER.error("%s rebuild guard sweep thread died unexpectedly", label)

    return close_failures, thread_died


def _install_from_wheelhouse_once(
    label: str,
    layout: python_runtime_install.RuntimeLayout,
    venv_dir: Path,
    lock: Path,
    runtime_name: str,
    python_identity_hash: str,
    lockfile_sha256: str,
    *,
    force_recreate: bool = False,
) -> tuple[Path | None, str | None]:
    install_state = python_runtime_install.read_install_state(layout.install_state)
    if python_runtime_install.needs_venv_recreate(
        install_state,
        runtime_name,
        python_identity_hash,
        lockfile_sha256,
    ) or force_recreate:
        if venv_dir.exists():
            print(
                f"Recreating {label} virtual environment because Python runtime "
                "identity or lockfile changed..."
            )
            if not _remove_stale_venv(label, venv_dir):
                return None, "remove"

    venv_python = _create_venv(layout, venv_dir)
    if not venv_python:
        return None, "create"

    uv = _bundled_uv(layout)
    if uv is None:
        return None, "tools"

    cache_dir = layout.uv_cache_dir(runtime_name)
    _remove_uv_cache(label, cache_dir)
    try:
        # Bootstrap (pip + setuptools) first, then the runtime lock: the venv ends
        # up with the same distributions the pip-based installer produced.
        for stage, requirements, description in (
            ("bootstrap", layout.bootstrap_lock, "pip bootstrap tools"),
            ("install", lock, "runtime packages"),
        ):
            print(
                f"Installing {label} {description} from bundled wheelhouse into {venv_dir} "
                "(offline; no internet download required)..."
            )
            command = python_runtime_install.build_offline_uv_install_command(
                uv.executable, venv_python, layout.wheelhouse, requirements, cache_dir
            )
            python_runtime_install.assert_offline_uv_command(command)
            result = _run_install_command(
                command, env=python_runtime_install.build_sanitized_uv_env()
            )
            if result.returncode != 0:
                print(f"{label} {description} install failed with exit code {result.returncode}")
                return None, stage
            try:
                python_runtime_install.assert_uv_install_output(_combined_output(result))
            except ValueError as exc:
                print(f"{label} {description} failed release validation: {exc}")
                return None, "validation"
    finally:
        # Hardlinked files survive the cache; everything after this point (pip
        # check, freeze, validation imports) proves the venv stands on its own.
        _remove_uv_cache(label, cache_dir)

    return venv_python, None


def _venv_python_is_usable(venv_python: Path) -> bool:
    """Minimal liveness probe for degraded reuse (#300).

    An existing venv interpreter is only reusable if it actually runs. This
    guards against reusing a corrupt/half-deleted venv, which would otherwise
    let post_install continue and fail later with a confusing error.
    """
    if not venv_python.exists():
        return False
    try:
        result = _run_install_command(
            [str(venv_python), "-c", "import sys; sys.exit(0)"],
            env=python_runtime_install.build_sanitized_python_env(
                require_virtualenv=False
            ),
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _INSTALL_LOGGER.warning("venv liveness probe could not run %s: %r", venv_python, exc)
        return False
    return result.returncode == 0


def _install_from_wheelhouse(
    label: str,
    layout: python_runtime_install.RuntimeLayout,
    venv_dir: Path,
    lock: Path,
    runtime_name: str,
) -> Path | None:
    if not _ensure_private_runtime_inputs(layout, lock):
        existing_python = get_venv_python(venv_dir)
        if _venv_python_is_usable(existing_python):
            _INSTALL_LOGGER.warning(
                "%s: DEGRADED local-deploy reuse -- bundled private runtime/"
                "wheelhouse inputs are missing; reusing the existing venv at %s "
                "WITHOUT rebuild or wheelhouse install. This is NOT a clean "
                "install. The downstream source mirror and runtime verification "
                "(Test-EffectiveRuntime) must still prove the deployed "
                "site-packages imports the current rook.server. See #300.",
                label,
                existing_python,
            )
            print(
                f"{label}: DEGRADED reuse of existing venv at {existing_python} "
                f"(bundled private runtime inputs incomplete; no rebuild, no "
                f"wheelhouse install). Source mirror + runtime verification still "
                f"required downstream. See #300."
            )
            _record_venv_rebuild_summary(
                layout.rook_root, runtime_name, label, 0, "reused_existing", "inputs"
            )
            return existing_python
        _record_venv_rebuild_summary(
            layout.rook_root, runtime_name, label, 0, "failed", "inputs"
        )
        return None

    python_identity_hash = python_runtime_install.sha256_file(layout.runtime_manifest)
    lockfile_sha256 = python_runtime_install.sha256_file(lock)

    retry_count = 0
    guard_close_failures: list[str] = []
    guard_thread_died_unexpectedly = False

    with _make_rebuild_guard(label, layout.rook_root) as guard:
        venv_python, failure_stage = _install_from_wheelhouse_once(
            label,
            layout,
            venv_dir,
            lock,
            runtime_name,
            python_identity_hash,
            lockfile_sha256,
        )
    close_failures, thread_died = _collect_rebuild_guard_health(label, guard)
    guard_close_failures.extend(close_failures)
    guard_thread_died_unexpectedly = guard_thread_died_unexpectedly or thread_died

    if failure_stage in {"remove", "create", "bootstrap", "install"}:
        retry_count = 1
        _INSTALL_LOGGER.warning(
            "%s install failed at %s; retrying one full venv rebuild",
            label,
            failure_stage,
        )
        with _make_rebuild_guard(label, layout.rook_root) as guard:
            venv_python, failure_stage = _install_from_wheelhouse_once(
                label,
                layout,
                venv_dir,
                lock,
                runtime_name,
                python_identity_hash,
                lockfile_sha256,
                force_recreate=True,
            )
        close_failures, thread_died = _collect_rebuild_guard_health(label, guard)
        guard_close_failures.extend(close_failures)
        guard_thread_died_unexpectedly = guard_thread_died_unexpectedly or thread_died

    if not venv_python:
        _INSTALL_LOGGER.error("%s install failed at %s", label, failure_stage)
        _record_venv_rebuild_summary(
            layout.rook_root,
            runtime_name,
            label,
            retry_count,
            "failed",
            failure_stage,
            guard_close_failures,
            guard_thread_died_unexpectedly,
        )
        return None

    check = _run_install_command(
        [str(venv_python), "-m", "pip", "check"],
        env=python_runtime_install.build_sanitized_python_env(require_virtualenv=True),
        timeout=300,
    )
    if check.returncode != 0:
        print(f"{label} pip check failed with exit code {check.returncode}")
        _INSTALL_LOGGER.error("%s pip check failed with exit code %s", label, check.returncode)
        _record_venv_rebuild_summary(
            layout.rook_root,
            runtime_name,
            label,
            retry_count,
            "failed",
            "pip-check",
            guard_close_failures,
            guard_thread_died_unexpectedly,
        )
        return None

    uv = _bundled_uv(layout)  # memoised: the tool that just installed this venv
    freeze = _run_install_command(
        [str(venv_python), "-m", "pip", "freeze", "--all"],
        env=python_runtime_install.build_sanitized_python_env(require_virtualenv=True),
        timeout=300,
    )
    mismatches = (
        python_runtime_install.freeze_mismatches(freeze.stdout, [layout.bootstrap_lock, lock])
        if freeze.returncode == 0
        else [f"pip freeze exited {freeze.returncode}"]
    )
    if uv is None:
        mismatches.append("bundled uv evidence unavailable")
    if mismatches:
        print(f"{label} installed packages differ from the locks: {mismatches}")
        _INSTALL_LOGGER.error("%s freeze differs from locks: %s", label, mismatches)
        _record_venv_rebuild_summary(
            layout.rook_root,
            runtime_name,
            label,
            retry_count,
            "failed",
            "freeze",
            guard_close_failures,
            guard_thread_died_unexpectedly,
        )
        return None

    _record_install_state(
        layout,
        runtime_name,
        venv_dir,
        venv_python,
        lock,
        python_identity_hash,
        lockfile_sha256,
        _combined_output(check),
        uv.evidence(),
    )
    _record_venv_rebuild_summary(
        layout.rook_root,
        runtime_name,
        label,
        retry_count,
        "success",
        guard_close_failures=guard_close_failures,
        guard_thread_died_unexpectedly=guard_thread_died_unexpectedly,
    )
    print(f"{label} installed successfully in {venv_dir}.")
    return venv_python


def install_mcp_server(mcp_server_dir: Path, runtime_root: Path) -> Path | None:
    """Create a managed venv and install rook-mcp from the bundled wheelhouse."""
    del mcp_server_dir
    layout = python_runtime_install.RuntimeLayout.from_rook_root(
        runtime_root, PRIVATE_PYTHON_VERSION
    )
    _, data_dir, logs_dir = get_runtime_paths(runtime_root)

    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    (runtime_root / "discovery").mkdir(parents=True, exist_ok=True)

    return _install_from_wheelhouse(
        "rook-mcp",
        layout,
        layout.rook_venv,
        layout.rook_lock,
        "rook",
    )


def install_chirp(chirp_dir: Path, runtime_root: Path) -> bool:
    """Set up Chirp: create venv and install the package.

    Chirp needs its own venv because chirp_manager.py discovers it via
    {CHIRP_HOME}/.venv/Scripts/python.exe. Keeping Chirp's heavyweight
    dependencies isolated from the Rook MCP/chat venv.
    """
    layout = python_runtime_install.RuntimeLayout.from_rook_root(
        runtime_root, PRIVATE_PYTHON_VERSION
    )
    if layout.chirp_venv.parent != chirp_dir:
        print(f"Chirp home must be {layout.chirp_venv.parent}; got {chirp_dir}")
        return False

    return (
        _install_from_wheelhouse(
            "Chirp",
            layout,
            layout.chirp_venv,
            layout.chirp_lock,
            "chirp",
        )
        is not None
    )


def _build_mcp_env(
    install_dir: Path,
    data_dir: Path,
    mode: str,
    chirp_dir: Path | None,
) -> dict[str, str]:
    """Build deterministic env vars for generated MCP entries."""
    if mode != "release":
        raise ValueError(f"unsupported installer MCP mode: {mode}")
    return python_runtime_install.build_release_mcp_env(install_dir, data_dir, chirp_dir)


def _register_mcp_via_file(
    python_path: str, mcp_dir: str, env_vars: dict[str, str]
) -> bool:
    """Fallback: write rook MCP config directly to ~/.claude.json."""
    rook_entry = {
        "type": "stdio",
        "command": python_path,
        "args": ["-m", "rook"],
        "cwd": mcp_dir,
        "env": env_vars,
    }

    user_config_path = Path.home() / ".claude.json"

    if user_config_path.exists():
        # Explicit UTF-8 first: Path.read_text() defaults to the locale codec
        # (cp1252 on Windows), which crashes on any non-cp1252 byte in the
        # user's config — e.g. a curly quote in a project name. Fall back to
        # cp1252 for legacy locale-written configs so they keep working.
        raw = None
        try:
            raw = user_config_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                raw = user_config_path.read_text(encoding="cp1252")
            except (UnicodeDecodeError, OSError):
                raw = None
        except OSError:
            raw = None

        existing = None
        if raw is not None:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    existing = parsed
            except json.JSONDecodeError:
                existing = None

        if existing is None:
            # NEVER overwrite a config we could not read: that destroys the
            # user's projects and other MCP servers. Leave the file untouched,
            # skip Rook registration, and let the install complete.
            print(
                f"WARNING: could not read existing {user_config_path}; "
                "leaving it untouched. Rook was NOT registered for Claude "
                "Code. Repair or remove that file and rerun the installer, "
                "or add the rook MCP server manually (see AGENT_SETUP.md)."
            )
            return True
    else:
        existing = {}

    if "mcpServers" not in existing:
        existing["mcpServers"] = {}

    existing["mcpServers"]["rook"] = rook_entry
    user_config_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"Wrote rook MCP config to {user_config_path}")
    return True


def configure_claude_code(
    install_dir: Path,
    data_dir: Path,
    python_path: str,
    mcp_server_dir: Path,
    chirp_dir: Path | None = None,
) -> bool:
    """Register rook MCP server for Claude Code in ~/.claude.json."""
    mcp_dir = str(mcp_server_dir).replace("\\", "/")
    env_vars = _build_mcp_env(install_dir, data_dir, "release", chirp_dir)
    return _register_mcp_via_file(python_path, mcp_dir, env_vars)


def write_chat_service_manifest(mcp_server_dir: Path, python_path: str) -> bool:
    """Write RookChatService.json to the Rhino plugin directory.

    The C# companion plugin needs this manifest to launch the Python chat
    service from the Rhino panel. Without it, the chat panel shows
    'Chat service unavailable'.
    """
    plugin_dir = (
        Path(os.environ.get("APPDATA", ""))
        / "McNeel" / "Rhinoceros" / "8.0" / "Plug-ins" / "RookNative"
    )

    if not plugin_dir.exists():
        print(f"Plugin directory not found: {plugin_dir} - skipping chat manifest")
        return False

    manifest = python_runtime_install.build_chat_service_manifest(
        mcp_server_dir=mcp_server_dir,
        rook_venv_python=Path(python_path),
        release_mode=True,
    )

    payload = json.dumps(manifest, indent=2)
    targets = [plugin_dir / "RookChatService.json"]
    known_children = set(MANAGED_COMPANION_RUNTIMES)
    for runtime in MANAGED_COMPANION_RUNTIMES:
        child_dir = plugin_dir / runtime
        if child_dir.is_dir():
            targets.append(child_dir / "RookChatService.json")
    for child in plugin_dir.iterdir():
        if child.is_dir() and child.name.startswith("net") and child.name not in known_children:
            print(f"WARNING: unknown managed runtime child directory: {child}")
            _INSTALL_LOGGER.warning("unknown managed runtime child directory: %s", child)
    for manifest_path in targets:
        try:
            manifest_path.write_text(payload, encoding="utf-8")
        except OSError as exc:
            print(f"Failed to write chat service manifest: {manifest_path}: {exc}")
            _INSTALL_LOGGER.error(
                "failed to write chat service manifest: %s: %s",
                manifest_path,
                exc,
            )
            return False
        print(f"Wrote chat service manifest: {manifest_path}")
        _INSTALL_LOGGER.info("wrote chat service manifest: %s", manifest_path)
    # python_path is the managed venv's Scripts/python.exe; climb to the
    # Rook runtime root for the summary sidecar.
    runtime_root = Path(python_path).parent.parent.parent
    _update_install_summary(
        runtime_root,
        chat_service_manifest_paths=[str(manifest_path) for manifest_path in targets],
    )
    return True


def configure_claude_desktop(
    install_dir: Path,
    data_dir: Path,
    python_path: str,
    mcp_server_dir: Path,
    chirp_dir: Path | None = None,
) -> bool:
    """Merge Rook config into Claude Desktop's config if installed."""
    mcp_dir = str(mcp_server_dir).replace("\\", "/")

    config_path = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json"

    if not config_path.parent.exists():
        print("Claude Desktop not detected - skipping Desktop config.")
        return True

    env_vars = _build_mcp_env(install_dir, data_dir, "release", chirp_dir)

    rook_entry = {
        "type": "stdio",
        "command": python_path,
        "args": ["-m", "rook"],
        "cwd": mcp_dir,
        "env": env_vars,
    }

    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            existing = {"mcpServers": {}}

        # Backup before modifying (remove stale backup first - rename fails on Windows if target exists)
        backup_path = config_path.with_suffix(".json.bak")
        backup_path.unlink(missing_ok=True)
        config_path.rename(backup_path)
        print(f"Backed up {config_path} -> {backup_path}")
    else:
        existing = {"mcpServers": {}}

    if "mcpServers" not in existing:
        existing["mcpServers"] = {}

    existing["mcpServers"]["rook"] = rook_entry
    config_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"Updated {config_path}")

    return True


def _format_toml_value(value: str) -> str:
    """Format a string as a TOML basic string value (with escaping)."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _generate_codex_toml(python_path: str, mcp_dir: str, env_vars: dict[str, str]) -> str:
    """Generate TOML config content for Codex CLI."""
    lines = [
        "# Rook MCP Server configuration for OpenAI Codex CLI",
        "# Auto-generated by Rook installer",
        "",
        "[mcp_servers.rook]",
        f"command = {_format_toml_value(python_path)}",
        f'args = ["-m", "rook"]',
        f"cwd = {_format_toml_value(mcp_dir)}",
        "startup_timeout_sec = 30",
        "tool_timeout_sec = 120",
        "",
        "[mcp_servers.rook.env]",
    ]
    for key, val in env_vars.items():
        lines.append(f"{key} = {_format_toml_value(val)}")
    lines.append("")
    return "\n".join(lines)


def configure_codex(
    install_dir: Path,
    data_dir: Path,
    python_path: str,
    mcp_server_dir: Path,
    chirp_dir: Path | None = None,
) -> bool:
    """Generate user-level Codex CLI config."""
    mcp_dir = str(mcp_server_dir).replace("\\", "/")

    env_vars = _build_mcp_env(install_dir, data_dir, "release", chirp_dir)
    env_vars[PROFILE_ENV_VAR] = "lean"
    toml_content = _generate_codex_toml(python_path, mcp_dir, env_vars)

    user_codex_dir = Path.home() / ".codex"
    user_codex_dir.mkdir(exist_ok=True)
    user_config = user_codex_dir / "config.toml"

    if user_config.exists():
        existing = user_config.read_text(encoding="utf-8")
        if "[mcp_servers.rook]" in existing:
            # Already has rook - replace the rook block
            # Match from [mcp_servers.rook] to the next [section] or end of file
            pattern = r"\[mcp_servers\.rook\].*?(?=\n\[(?!mcp_servers\.rook[.\]])|$)"
            new_content = re.sub(pattern, toml_content.strip(), existing, flags=re.DOTALL)
            user_config.write_text(new_content, encoding="utf-8")
        else:
            # Append rook section
            with open(user_config, "a", encoding="utf-8") as f:
                f.write("\n" + toml_content)
    else:
        user_config.write_text(toml_content, encoding="utf-8")

    print(f"Updated {user_config}")
    return True


def create_env_examples(install_dir: Path, chirp_dir: Path | None = None) -> None:
    """Create .env.example templates (never overwrites existing .env)."""
    # Rook MCP server
    mcp_example = install_dir / "mcp_server" / ".env.example"
    if not mcp_example.exists():
        mcp_example.write_text(
            "# Rook MCP Server Configuration\n"
            "# Copy this file to .env and fill in your values.\n"
            "\n"
            "# Required for AI-powered features (chat, agents, consolidation)\n"
            "ANTHROPIC_API_KEY=your-key-here\n"
            "\n"
            "# Optional overrides\n"
            "# ROOK_LOG_LEVEL=INFO\n",
            encoding="utf-8",
        )
        print(f"Created {mcp_example}")

    # Chirp adapter
    if chirp_dir and chirp_dir.exists():
        chirp_example = chirp_dir / ".env.example"
        if not chirp_example.exists():
            chirp_example.write_text(
                "# Chirp Adapter Configuration\n"
                "# Copy this file to .env and fill in your values.\n"
                "\n"
                "# Required - powers LLM calls in Chirp components\n"
                "ANTHROPIC_API_KEY=your-key-here\n"
                "\n"
                "# Optional overrides\n"
                "CHIRP_INFERENCE_TIMEOUT_SECONDS=300\n"
                "# CHIRP_MODEL=anthropic/claude-sonnet-4-20250514\n"
                "# CHIRP_PORT=0\n"
                "# CHIRP_TRACE_DIR=./traces\n",
                encoding="utf-8",
            )
            print(f"Created {chirp_example}")


def _copy_children(source_root: Path, target_root: Path, label: str) -> bool:
    """Copy the direct children of a payload root into a target root."""
    if not source_root.exists():
        print(f"{label} source not found: {source_root} - skipping")
        return False

    target_root.mkdir(parents=True, exist_ok=True)
    for child in source_root.iterdir():
        destination = target_root / child.name
        removal = _remove_retired_codex_skill(destination)
        if removal["outcome"] == "failed":
            print(
                f"Could not replace {label} child {destination}: "
                f"{removal.get('error', 'unknown removal failure')}"
            )
            return False
        if child.is_dir():
            shutil.copytree(child, destination)
        else:
            shutil.copy2(child, destination)
    print(f"Installed {label} to {target_root}")
    return True


RETIRED_CODEX_SKILL_NAMES = ("design-road", "masterplan-roads", "consolidate")
_REPARSE_POINT_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _is_reparse_point(metadata: os.stat_result) -> bool:
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT_ATTRIBUTE
    )


def _remove_retired_codex_skill(target: Path) -> dict[str, str]:
    result = {"name": target.name, "outcome": "absent"}
    try:
        metadata = target.lstat()
    except FileNotFoundError:
        return result
    except OSError as exc:
        return {
            "name": target.name,
            "outcome": "failed",
            "error": str(exc)[:500],
        }

    try:
        if _is_reparse_point(metadata):
            if stat.S_ISDIR(metadata.st_mode):
                os.rmdir(target)
            else:
                target.unlink()
            result["outcome"] = "unlinked_reparse_point"
        elif stat.S_ISDIR(metadata.st_mode):
            shutil.rmtree(target)
            result["outcome"] = "removed_directory"
        else:
            target.unlink()
            result["outcome"] = "removed_file"
    except OSError as exc:
        result["outcome"] = "failed"
        result["error"] = str(exc)[:500]
    return result


def cleanup_retired_codex_skills(runtime_root: Path) -> list[dict[str, str]]:
    try:
        skills_root = (Path.home() / ".codex" / "skills").resolve(strict=False)
    except OSError as exc:
        outcomes = [
            {"name": name, "outcome": "failed", "error": str(exc)[:500]}
            for name in RETIRED_CODEX_SKILL_NAMES
        ]
    else:
        outcomes = []
        for name in RETIRED_CODEX_SKILL_NAMES:
            target = skills_root / name
            if target.parent != skills_root or target.name != name:
                outcomes.append({
                    "name": name,
                    "outcome": "failed",
                    "error": "target is not a direct child of the canonical Codex skills root",
                })
                continue
            outcomes.append(_remove_retired_codex_skill(target))

    failed = [item for item in outcomes if item["outcome"] == "failed"]
    payload = _read_install_summary(runtime_root)
    payload["retired_codex_skill_cleanup"] = {
        "complete": not failed,
        "targets": outcomes,
    }
    if failed:
        warning = (
            "Retired-skill containment is incomplete: "
            + ", ".join(item["name"] for item in failed)
        )
        _append_install_summary_warnings(payload, [warning])
        print(f"WARNING: {warning}")
        _INSTALL_LOGGER.warning("%s outcomes=%s", warning, outcomes)
    else:
        print(f"Retired Codex skill migration: {outcomes}")
        _INSTALL_LOGGER.info("Retired Codex skill migration outcomes=%s", outcomes)
    _write_install_summary(runtime_root, payload)
    return outcomes


def install_user_assets(install_dir: Path, install_claude: bool, install_codex: bool) -> bool:
    """Copy curated Codex skills to the user-level Codex home.

    Claude Code skills and hooks are delivered via the marketplace plugin,
    not by this installer.  This function only copies Codex skills.
    Returns True when there is nothing to do (Codex not selected).
    """
    if not install_codex:
        # Nothing for this installer to copy; Claude Code skills come from the marketplace plugin.
        return True

    return _copy_children(
        install_dir / ".agents" / "skills",
        Path.home() / ".codex" / "skills",
        "Codex skills",
    )


def managed_companion_payloads(plugin_dir: Path) -> list[tuple[str, Path]]:
    return [(runtime, plugin_dir / runtime / "Rook.rhp") for runtime in MANAGED_COMPANION_RUNTIMES]


def _consume_doctor_payload(payload: dict) -> tuple[list[tuple[str, bool]], list[str]]:
    """Split doctor checks into fatal validation entries and warnings.

    Doctor checks carry a severity field; warning-severity failures (e.g.
    "--fix left an unreadable config untouched") must surface as warnings,
    not fail the installer — doctor's own exit code already treats them
    as non-fatal (DoctorResult.ok ignores warning severity)."""
    checks: list[tuple[str, bool]] = []
    warnings: list[str] = []
    for check in payload.get("checks", []):
        name = check.get("name", "rook doctor check")
        ok = bool(check.get("ok"))
        if not ok and check.get("severity") == "warning":
            warnings.append(f"{name}: {check.get('detail') or 'warning (non-fatal)'}")
            continue
        checks.append((name, ok))
    for warning in payload.get("warnings", []):
        warnings.append(str(warning))
    return checks, warnings


def validate(
    install_dir: Path,
    runtime_root: Path,
    python_path: str,
    install_plugins: bool,
    install_claude: bool,
    install_codex: bool,
    chirp_dir: Path | None = None,
) -> bool:
    """Run basic validation checks."""
    checks = []
    warnings: list[str] = []
    venv_dir, data_dir, logs_dir = get_runtime_paths(runtime_root)

    if install_plugins:
        plugin_dir = Path(os.environ.get("APPDATA", "")) / "McNeel" / "Rhinoceros" / "8.0" / "Plug-ins" / "RookNative"
        native = plugin_dir / "RookNative.rhp"
        checks.append(("RookNative.rhp deployed", native.exists()))
        for runtime, companion in managed_companion_payloads(plugin_dir):
            checks.append((f"Rook.rhp {runtime} deployed", companion.exists()))

    checks.append(("Managed runtime venv", venv_dir.exists()))
    checks.append(("Managed runtime data dir", data_dir.exists()))
    checks.append(("Managed runtime logs dir", logs_dir.exists()))

    # Check Chirp venv
    if chirp_dir:
        if os.name == "nt":
            chirp_python = chirp_dir / ".venv" / "Scripts" / "python.exe"
        else:
            chirp_python = chirp_dir / ".venv" / "bin" / "python"
        checks.append(("Chirp venv", chirp_python.exists()))

        if chirp_python.exists():
            try:
                result = subprocess.run(
                    [str(chirp_python), "-c", "import chirp; print('ok')"],
                    capture_output=True, text=True, timeout=10,
                )
                checks.append(("Chirp importable", result.returncode == 0))
            except Exception:
                checks.append(("Chirp importable", False))

    doctor_env = os.environ.copy()
    doctor_env.update(_build_mcp_env(install_dir, data_dir, "release", chirp_dir))
    doctor_cwd = install_dir / "mcp_server"
    doctor_cmd = [
        python_path,
        "-m",
        "rook",
        "doctor",
        "--json",
        "--skip-handshake",
        "--python-path",
        python_path,
    ]
    if install_claude:
        doctor_cmd.append("--claude")
    if install_codex:
        doctor_cmd.append("--codex")
    if install_claude or install_codex:
        doctor_cmd.append("--fix")
    if install_plugins:
        doctor_cmd.append("--plugins")

    if not doctor_cwd.exists():
        checks.append(("rook doctor payload cwd", False))
        warnings.append(f"Expected MCP payload directory is missing: {doctor_cwd}")
    else:
        try:
            doctor_result = subprocess.run(
                doctor_cmd,
                capture_output=True,
                text=True,
                timeout=90,
                env=doctor_env,
                cwd=doctor_cwd,
            )
            if doctor_result.returncode not in (0, 1):
                checks.append(("rook doctor execution", False))
                warnings.append(f"rook doctor exited unexpectedly: {doctor_result.returncode}")
            else:
                payload = json.loads(doctor_result.stdout)
                doctor_checks, doctor_warnings = _consume_doctor_payload(payload)
                checks.extend(doctor_checks)
                warnings.extend(doctor_warnings)
        except Exception as exc:
            checks.append(("rook doctor execution", False))
            warnings.append(f"rook doctor failed: {exc}")

    legacy_claude = Path.home() / ".claude" / ".mcp.json"
    if legacy_claude.exists():
        warnings.append(f"Legacy Claude MCP path still exists: {legacy_claude}")

    print("\n--- Validation ---")
    all_ok = True
    for name, ok in checks:
        status = "OK" if ok else "MISSING"
        print(f"  [{status}] {name}")
        if not ok:
            all_ok = False
    for warning in warnings:
        print(f"  [WARN] {warning}")

    return all_ok


def _remove_tree(path: Path, label: str) -> None:
    try:
        if path.exists():
            shutil.rmtree(path)
            print(f"Removed {label}: {path}")
    except Exception as e:
        print(f"Warning: could not remove {label} {path}: {e}")


def uninstall_cleanup() -> None:
    """Remove installed runtime files while preserving user data and artifacts."""
    # Remove user-level MCP registration - try CLI first, then manual cleanup
    claude = shutil.which("claude")
    if claude:
        try:
            subprocess.run(
                [claude, "mcp", "remove", "-s", "user", "rook"],
                capture_output=True, text=True, timeout=15,
            )
            print("Removed rook MCP server via CLI (user scope)")
        except Exception:
            pass

    # Clean ~/.claude.json (current canonical path)
    user_config = Path.home() / ".claude.json"
    if user_config.exists():
        try:
            data = json.loads(user_config.read_text(encoding="utf-8"))
            if "mcpServers" in data and "rook" in data["mcpServers"]:
                del data["mcpServers"]["rook"]
                user_config.write_text(json.dumps(data, indent=2), encoding="utf-8")
                print(f"Removed rook from {user_config}")
        except Exception as e:
            print(f"Warning: could not clean {user_config}: {e}")

    # Clean legacy ~/.claude/.mcp.json (old path, may exist from prior installs)
    legacy_mcp = Path.home() / ".claude" / ".mcp.json"
    if legacy_mcp.exists():
        try:
            data = json.loads(legacy_mcp.read_text(encoding="utf-8"))
            if "mcpServers" in data and "rook" in data["mcpServers"]:
                del data["mcpServers"]["rook"]
                legacy_mcp.write_text(json.dumps(data, indent=2), encoding="utf-8")
                print(f"Removed rook from {legacy_mcp} (legacy)")
        except Exception as e:
            print(f"Warning: could not clean {legacy_mcp}: {e}")

    # Remove from Claude Desktop config
    config_path = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json"
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            if "mcpServers" in data and "rook" in data["mcpServers"]:
                del data["mcpServers"]["rook"]
                config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                print(f"Removed rook from {config_path}")
        except Exception as e:
            print(f"Warning: could not clean {config_path}: {e}")

    install_dir = Path(__file__).resolve().parent

    for source_root, target_root, label in [
        (install_dir / ".claude" / "skills", Path.home() / ".claude" / "skills", "Claude skill"),
        (install_dir / ".claude" / "agents", Path.home() / ".claude" / "agents", "Claude agent"),
        (install_dir / ".agents" / "skills", Path.home() / ".codex" / "skills", "Codex skill"),
    ]:
        if not source_root.exists() or not target_root.exists():
            continue
        for child in source_root.iterdir():
            destination = target_root / child.name
            try:
                if destination.is_dir():
                    shutil.rmtree(destination)
                    print(f"Removed {label} directory {destination}")
                elif destination.exists():
                    destination.unlink()
                    print(f"Removed {label} file {destination}")
            except Exception as e:
                print(f"Warning: could not remove {destination}: {e}")

    # Remove from Codex CLI config (~/.codex/config.toml)
    codex_config = Path.home() / ".codex" / "config.toml"
    if codex_config.exists():
        try:
            content = codex_config.read_text(encoding="utf-8")
            if "[mcp_servers.rook]" in content:
                # Remove rook section (from [mcp_servers.rook] to next section or EOF)
                cleaned = re.sub(
                    r"(\n?)\[mcp_servers\.rook\].*?(?=\n\[(?!mcp_servers\.rook[.\]])|$)",
                    "",
                    content,
                    flags=re.DOTALL,
                )
                codex_config.write_text(cleaned.strip() + "\n", encoding="utf-8")
                print(f"Removed rook from {codex_config}")
        except Exception as e:
            print(f"Warning: could not clean {codex_config}: {e}")

    runtime_root = get_runtime_root()
    temp_root = Path(tempfile.gettempdir()) / "rook"

    for path, label in [
        (runtime_root / "app", "runtime app payload"),
        (runtime_root / "python", "private Python runtime"),
        (runtime_root / "venv", "managed Python venv"),
        (runtime_root / "logs", "runtime logs"),
        (runtime_root / "discovery", "runtime discovery metadata"),
        (runtime_root / "docs", "runtime docs"),
        (temp_root, "temporary diagnostics"),
    ]:
        _remove_tree(path, label)

    for path, label in [
        (runtime_root / "CLAUDE.md", "Claude instruction file"),
        (runtime_root / "AGENTS.md", "Codex instruction file"),
    ]:
        try:
            if path.exists():
                path.unlink()
                print(f"Removed {label}: {path}")
        except Exception as e:
            print(f"Warning: could not remove {label} {path}: {e}")

    print("Uninstall cleanup complete.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Rook post-install setup")
    parser.add_argument("--install-dir", required=False, help="Rook install directory")
    parser.add_argument("--mcp-server-dir", required=False, help="MCP server directory")
    parser.add_argument("--runtime-root", required=False, help="Managed Rook runtime root")
    parser.add_argument("--chirp-dir", default=None, help="Chirp adapter directory")
    parser.add_argument("--prime-incoming-dir", help="Verified Prime payload staged beneath the installed prime/.incoming root")
    parser.add_argument("--claude", action="store_true", help="Configure Claude Code/Desktop MCP registration (skills/hooks come from the marketplace plugin, not this installer)")
    parser.add_argument("--codex", action="store_true", help="Configure OpenAI Codex CLI")
    parser.add_argument("--plugins", action="store_true", help="Validate Rhino plugin deployment")
    parser.add_argument("--uninstall", action="store_true", help="Run uninstall cleanup")
    parser.add_argument("--skip-chirp-install", action="store_true", help="Skip Chirp venv refresh while still using the supplied Chirp directory in generated config")
    parser.add_argument("--skip-validation", action="store_true", help="Skip post-install validation checks")
    args = parser.parse_args()

    if args.uninstall:
        _close_install_logging()
        uninstall_cleanup()
        return 0

    if not args.install_dir or not args.mcp_server_dir:
        parser.error("--install-dir and --mcp-server-dir are required for install")

    install_dir = Path(args.install_dir)
    mcp_server_dir = Path(args.mcp_server_dir)
    runtime_root = get_runtime_root(args.runtime_root)
    chirp_dir = Path(args.chirp_dir) if args.chirp_dir else None
    _configure_install_logging(runtime_root)
    _update_install_summary(
        runtime_root, phase_reached="finalizer-started", final_outcome="running"
    )

    print("=" * 50)
    print("Rook Post-Install Setup")
    print("=" * 50)
    print(f"Install root:  {install_dir}")
    print(f"Runtime root:  {runtime_root}")

    cleanup_retired_codex_skills(runtime_root)

    # Step 1: Install MCP server
    managed_python = install_mcp_server(mcp_server_dir, runtime_root)
    if not managed_python:
        print("\nWARNING: MCP server installation failed.")
        print("You can install manually later by creating a venv under %LOCALAPPDATA%\\Rook\\venv")
        return 1
    managed_python_path = str(managed_python).replace("\\", "/")

    if args.prime_incoming_dir:
        result = subprocess.run(
            [str(managed_python), "-I", "-m", "rook.agent.chat.prime_runtime_artifact", "promote",
             "--incoming-root", str(Path(args.prime_incoming_dir)), "--prime-root", str(install_dir / "prime")],
            shell=False,
            check=False,
        )
        if result.returncode != 0:
            print("\nERROR: Prime runtime promotion failed; chat service manifest was not published.")
            return 1

    # Step 2: Install Chirp (if selected)
    if chirp_dir:
        if not chirp_dir.exists():
            print(f"\nERROR: Selected Chirp install directory is missing: {chirp_dir}")
            return 1
        if args.skip_chirp_install:
            print("Skipping Chirp venv refresh.")
        elif not install_chirp(chirp_dir, runtime_root):
            print("\nERROR: Chirp installation failed.")
            print("Re-run the installer repair flow after verifying the bundled runtime payload.")
            return 1

    # Step 3: Generate user-level MCP config (includes CHIRP_HOME if Chirp installed)
    _, data_dir, _ = get_runtime_paths(runtime_root)
    if args.claude:
        if not configure_claude_code(install_dir, data_dir, managed_python_path, mcp_server_dir, chirp_dir):
            print("\nERROR: Failed to configure Claude Code MCP registration.")
            return 1
    else:
        print("Claude Code/Desktop not selected - skipping Claude config.")

    # Step 4: Configure Claude Desktop
    if args.claude:
        if not configure_claude_desktop(install_dir, data_dir, managed_python_path, mcp_server_dir, chirp_dir):
            print("\nERROR: Failed to configure Claude Desktop MCP registration.")
            return 1

    # Step 5: Configure OpenAI Codex CLI (if requested or detected)
    if args.codex:
        if not configure_codex(install_dir, data_dir, managed_python_path, mcp_server_dir, chirp_dir):
            print("\nERROR: Failed to configure Codex MCP registration.")
            return 1
    else:
        print("Codex not selected - skipping Codex config.")

    # Step 6: Copy curated Codex skills to ~/.codex/skills (Claude Code skills/hooks come from the marketplace plugin)
    if not install_user_assets(install_dir, install_claude=args.claude, install_codex=args.codex):
        print("\nERROR: Failed to copy selected user agent assets.")
        return 1

    # Step 7: Write chat service manifest for Rhino panel
    if not write_chat_service_manifest(mcp_server_dir, managed_python_path):
        print("\nERROR: Failed to write the Rhino chat service manifest.")
        print("Re-run the installer repair flow after verifying the RookNative plugin directory.")
        return 1

    # Step 8: Create .env.example templates
    create_env_examples(install_dir, chirp_dir)

    # Step 9: Validate
    if args.skip_validation:
        print("\nValidation skipped by request.")
    else:
        all_ok = validate(
            install_dir,
            runtime_root,
            managed_python_path,
            install_plugins=args.plugins,
            install_claude=args.claude,
            install_codex=args.codex,
            chirp_dir=chirp_dir,
        )

        if not all_ok:
            print("\nSetup failed validation.")
            return 1

    print("\nSetup complete!")
    print("Next steps:")
    print("  1. Open (or restart) Rhino 8")
    print("  2. Open Claude Code and type: rhino_ping")
    print("  3. You're connected!")
    if chirp_dir:
        print("  4. Ask Claude to create a Chirp component on the GH canvas!")
    return 0


def _last_gasp_args_from_argv(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--runtime-root", required=False)
    parser.add_argument("--uninstall", action="store_true")
    args, _ = parser.parse_known_args(argv)
    return args


def _last_gasp_runtime_root_from_argv(argv: list[str]) -> Path:
    args = _last_gasp_args_from_argv(argv)
    return get_runtime_root(args.runtime_root)


def _run_with_last_gasp(runtime_root: Path | None = None) -> int:
    argv = sys.argv[1:]
    args = _last_gasp_args_from_argv(argv)
    root = runtime_root or get_runtime_root(args.runtime_root)
    try:
        if not args.uninstall:
            _configure_install_logging(root)
        result = main()
        if not args.uninstall:
            if result == 0:
                _update_install_summary(
                    root,
                    phase_reached="finalizer-complete",
                    final_outcome="success",
                )
            else:
                _update_install_summary(
                    root,
                    phase_reached="finalizer-failed",
                    final_outcome="failed",
                )
        return result
    except SystemExit:
        raise
    except Exception:
        _configure_install_logging(root)
        _INSTALL_LOGGER.error("post_install crashed:\n%s", traceback.format_exc())
        _update_install_summary(
            root, phase_reached="finalizer-crashed", final_outcome="failed"
        )
        return 1
    finally:
        if not args.uninstall:
            _remove_installer_cache(root)


if __name__ == "__main__":
    sys.exit(_run_with_last_gasp())
