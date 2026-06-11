"""Rook post-install setup - called by the Inno Setup installer.

This script runs after the installer copies files. It handles:
  1. Create a managed Rook runtime under %LOCALAPPDATA%\\Rook
  2. Install the rook-mcp Python package into that managed venv
  3. Set up Chirp adapter service (venv + pip install -e)
  4. Register rook MCP server in documented user-scope client config
  5. Merge Rook config into Claude Desktop config (if installed)
  6. Generate user-level config.toml for OpenAI Codex CLI
  7. Copy curated Codex skills to ~/.codex/skills (Claude Code gets skills via the marketplace plugin)
  8. Validate the installation

Uses only stdlib so it can run before dependencies are installed.
"""

import argparse
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


MANAGED_COMPANION_RUNTIMES = ("net8.0", "net7.0", "net48")
DEFAULT_PIP_INSTALL_TIMEOUT_SECONDS = 7200
DEFAULT_VENV_SETUP_TIMEOUT_SECONDS = 900
INSTALL_HEARTBEAT_SECONDS = 30


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


def get_venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _pip_install_timeout_seconds() -> int:
    """Return the pip install timeout, allowing release support overrides."""
    raw_value = os.environ.get("ROOK_POST_INSTALL_PIP_TIMEOUT_SECONDS")
    if not raw_value:
        return DEFAULT_PIP_INSTALL_TIMEOUT_SECONDS

    try:
        return int(raw_value)
    except ValueError:
        print(
            "Ignoring invalid ROOK_POST_INSTALL_PIP_TIMEOUT_SECONDS="
            f"{raw_value!r}; using {DEFAULT_PIP_INSTALL_TIMEOUT_SECONDS} seconds."
        )
        return DEFAULT_PIP_INSTALL_TIMEOUT_SECONDS


def _format_command(args: list[str]) -> str:
    return " ".join(f'"{arg}"' if " " in arg else arg for arg in args)


def _print_repair_command(label: str, args: list[str]) -> None:
    print(f"{label} timed out before completion.")
    print("Repair command:")
    print(f"  {_format_command(args)}")


def _run_streaming_command(
    args: list[str],
    label: str,
    timeout_seconds: int,
    log_path: Path,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, bool]:
    """Run a command while streaming output and heartbeat progress to the user."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"\n--- {label} ---")
    print(f"Command: {_format_command(args)}")
    print(f"Log: {log_path}")

    with log_path.open("a", encoding="utf-8", errors="replace") as log_file:
        log_file.write(f"\n--- {label} ---\n")
        log_file.write(f"Command: {_format_command(args)}\n")
        log_file.flush()

        try:
            process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(cwd) if cwd else None,
                env=env,
            )
        except OSError as exc:
            print(f"{label} failed to start: {exc}")
            log_file.write(f"Failed to start: {exc}\n")
            return 1, False

        output_queue: queue.Queue[str] = queue.Queue()

        def read_output() -> None:
            if process.stdout is None:
                return
            for line in process.stdout:
                output_queue.put(line)

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        started = time.monotonic()
        last_heartbeat = started

        while True:
            try:
                line = output_queue.get(timeout=1)
                print(line, end="")
                log_file.write(line)
                log_file.flush()
            except queue.Empty:
                pass

            returncode = process.poll()
            now = time.monotonic()

            if returncode is not None:
                while True:
                    try:
                        line = output_queue.get_nowait()
                    except queue.Empty:
                        break
                    print(line, end="")
                    log_file.write(line)
                log_file.write(f"Exit code: {returncode}\n")
                log_file.flush()
                reader.join(timeout=1)
                return returncode, False

            if timeout_seconds > 0 and now - started > timeout_seconds:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
                message = f"{label} timed out after {timeout_seconds} seconds."
                print(message)
                log_file.write(message + "\n")
                log_file.flush()
                return process.returncode or 124, True

            if now - last_heartbeat >= INSTALL_HEARTBEAT_SECONDS:
                elapsed_minutes = int((now - started) // 60)
                message = (
                    f"[Rook installer] Still working on {label} after "
                    f"{elapsed_minutes} minute(s). First-time Python dependency "
                    "installs can take a while; please do not close this window."
                )
                print(message)
                log_file.write(message + "\n")
                log_file.flush()
                last_heartbeat = now


def install_mcp_server(mcp_server_dir: Path, runtime_root: Path) -> Path | None:
    """Create a managed venv and install rook-mcp into it."""
    bootstrap_python = find_python()
    venv_dir, data_dir, logs_dir = get_runtime_paths(runtime_root)
    venv_python = get_venv_python(venv_dir)
    log_path = logs_dir / "post_install.log"

    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    if not venv_python.exists():
        print(f"Creating managed Rook venv at {venv_dir}...")
        venv_cmd = [bootstrap_python, "-m", "venv", str(venv_dir)]
        returncode, timed_out = _run_streaming_command(
            venv_cmd,
            "Create managed Rook Python environment",
            DEFAULT_VENV_SETUP_TIMEOUT_SECONDS,
            log_path,
        )
        if returncode != 0:
            if timed_out:
                _print_repair_command("Managed Rook venv creation", venv_cmd)
            else:
                print("Managed Rook venv creation failed.")
            return None

    print(f"Installing rook-mcp from {mcp_server_dir} into {venv_dir}...")
    print(
        "This installs Rook's Python dependency stack. On a cold machine it can "
        "take 10-30+ minutes while pip downloads and builds packages."
    )

    pip_cmd = [str(venv_python), "-m", "pip", "install", "-e", str(mcp_server_dir)]
    returncode, timed_out = _run_streaming_command(
        pip_cmd,
        "Install rook-mcp Python dependencies",
        _pip_install_timeout_seconds(),
        log_path,
    )

    if returncode != 0:
        if timed_out:
            _print_repair_command("rook-mcp dependency install", pip_cmd)
        else:
            print("rook-mcp dependency install failed. Review the log above for pip output.")
        return None

    print(f"rook-mcp installed successfully in {venv_dir}.")
    return venv_python


def install_chirp(chirp_dir: Path) -> bool:
    """Set up Chirp: create venv and install the package.

    Chirp needs its own venv because chirp_manager.py discovers it via
    {CHIRP_HOME}/.venv/Scripts/python.exe. Keeping Chirp's heavyweight
    dependencies (DSPy, FastAPI, uvicorn) isolated from the system Python.
    """
    python = find_python()
    venv_dir = chirp_dir / ".venv"
    log_path = chirp_dir / "logs" / "post_install.log"

    # Step 1: Create venv
    print(f"Creating Chirp virtual environment at {venv_dir}...")
    venv_cmd = [python, "-m", "venv", str(venv_dir)]
    returncode, timed_out = _run_streaming_command(
        venv_cmd,
        "Create Chirp Python environment",
        DEFAULT_VENV_SETUP_TIMEOUT_SECONDS,
        log_path,
    )
    if returncode != 0:
        if timed_out:
            _print_repair_command("Chirp venv creation", venv_cmd)
        else:
            print("Chirp venv creation failed.")
        return False

    # Step 2: Find the venv's pip
    if os.name == "nt":
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python"

    if not venv_python.exists():
        print(f"venv Python not found at {venv_python}")
        return False

    # Step 3: pip install -e inside the venv
    print(f"Installing Chirp package into venv...")
    print(
        "This installs Chirp's Python dependency stack. On a cold machine it can "
        "take 10-30+ minutes while pip downloads and builds packages."
    )
    pip_cmd = [str(venv_python), "-m", "pip", "install", "-e", str(chirp_dir)]
    returncode, timed_out = _run_streaming_command(
        pip_cmd,
        "Install Chirp Python dependencies",
        _pip_install_timeout_seconds(),
        log_path,
    )
    if returncode != 0:
        if timed_out:
            _print_repair_command("Chirp dependency install", pip_cmd)
        else:
            print("Chirp dependency install failed. Review the log above for pip output.")
        return False

    print("Chirp installed successfully.")
    return True


def _build_mcp_env(
    install_dir: Path,
    data_dir: Path,
    mode: str,
    chirp_dir: Path | None,
) -> dict[str, str]:
    """Build deterministic env vars for generated MCP entries."""
    env_vars = {
        "PYTHONPATH": "",
        "PYTHONHOME": "",
        "ROOK_INSTALL_ROOT": str(install_dir).replace("\\", "/"),
        "ROOK_DATA_DIR": str(data_dir).replace("\\", "/"),
        "ROOK_MODE": mode,
    }
    if chirp_dir and chirp_dir.exists():
        env_vars["CHIRP_HOME"] = str(chirp_dir).replace("\\", "/")
    return env_vars


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
        try:
            existing = json.loads(user_config_path.read_text())
        except (json.JSONDecodeError, OSError):
            existing = {}
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

    src_dir = mcp_server_dir / "src"
    python_path_entries = [str(src_dir)] if src_dir.exists() else []

    manifest = {
        "pythonPath": python_path,
        "workingDirectory": str(mcp_server_dir),
        "module": "rook.agent.chat.service_main",
        "owner": "rhino-panel",
        "pythonPathEntries": python_path_entries,
    }

    manifest_path = plugin_dir / "RookChatService.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Wrote chat service manifest: {manifest_path}")
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
            existing = json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
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


def _remove_rook_installer_comment_stanzas(content: str) -> str:
    """Remove generated Rook comment headers that may survive failed installs."""
    lines = content.splitlines()
    cleaned: list[str] = []
    i = 0
    while i < len(lines):
        if (
            lines[i] == "# Rook MCP Server configuration for OpenAI Codex CLI"
            and i + 1 < len(lines)
            and lines[i + 1] == "# Auto-generated by Rook installer"
        ):
            i += 2
            while i < len(lines) and lines[i] == "":
                i += 1
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue
        cleaned.append(lines[i])
        i += 1

    return "\n".join(cleaned).rstrip()


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
    toml_content = _generate_codex_toml(python_path, mcp_dir, env_vars)

    user_codex_dir = Path.home() / ".codex"
    user_codex_dir.mkdir(exist_ok=True)
    user_config = user_codex_dir / "config.toml"

    if user_config.exists():
        existing = _remove_rook_installer_comment_stanzas(
            user_config.read_text(encoding="utf-8")
        )
        if "[mcp_servers.rook]" in existing:
            # Already has rook - replace the rook block
            # Match from [mcp_servers.rook] to the next [section] or end of file
            pattern = r"\[mcp_servers\.rook\].*?(?=\n\[(?!mcp_servers\.rook[.\]])|$)"
            new_content = re.sub(pattern, toml_content.strip(), existing, flags=re.DOTALL)
            user_config.write_text(new_content.rstrip() + "\n", encoding="utf-8")
        else:
            # Append rook section
            separator = "\n\n" if existing else ""
            user_config.write_text(existing + separator + toml_content, encoding="utf-8")
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
            "# (If you entered your API key during install, .env already exists.)\n"
            "\n"
            "# Required for AI-powered features (chat, agents, consolidation)\n"
            "ANTHROPIC_API_KEY=your-key-here\n"
            "\n"
            "# Optional overrides\n"
            "# ROOK_LOG_LEVEL=INFO\n"
        )
        print(f"Created {mcp_example}")

    # Chirp adapter
    if chirp_dir and chirp_dir.exists():
        chirp_example = chirp_dir / ".env.example"
        if not chirp_example.exists():
            chirp_example.write_text(
                "# Chirp Adapter Configuration\n"
                "# Copy this file to .env and fill in your values.\n"
                "# (If you entered your API key during install, .env already exists.)\n"
                "\n"
                "# Required - powers LLM calls in Chirp components\n"
                "ANTHROPIC_API_KEY=your-key-here\n"
                "\n"
                "# Optional overrides\n"
                "# CHIRP_MODEL=anthropic/claude-sonnet-4-20250514\n"
                "# CHIRP_PORT=0\n"
                "# CHIRP_TRACE_DIR=./traces\n"
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
        if child.is_dir():
            shutil.copytree(child, destination, dirs_exist_ok=True)
        else:
            shutil.copy2(child, destination)
    print(f"Installed {label} to {target_root}")
    return True


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
                for check in payload.get("checks", []):
                    checks.append((check.get("name", "rook doctor check"), bool(check.get("ok"))))
                for warning in payload.get("warnings", []):
                    warnings.append(str(warning))
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
    """Remove Rook entries and generated runtime artifacts during uninstall."""
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
            data = json.loads(user_config.read_text())
            if "mcpServers" in data and "rook" in data["mcpServers"]:
                del data["mcpServers"]["rook"]
                user_config.write_text(json.dumps(data, indent=2))
                print(f"Removed rook from {user_config}")
        except Exception as e:
            print(f"Warning: could not clean {user_config}: {e}")

    # Clean legacy ~/.claude/.mcp.json (old path, may exist from prior installs)
    legacy_mcp = Path.home() / ".claude" / ".mcp.json"
    if legacy_mcp.exists():
        try:
            data = json.loads(legacy_mcp.read_text())
            if "mcpServers" in data and "rook" in data["mcpServers"]:
                del data["mcpServers"]["rook"]
                legacy_mcp.write_text(json.dumps(data, indent=2))
                print(f"Removed rook from {legacy_mcp} (legacy)")
        except Exception as e:
            print(f"Warning: could not clean {legacy_mcp}: {e}")

    # Remove from Claude Desktop config
    config_path = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json"
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text())
            if "mcpServers" in data and "rook" in data["mcpServers"]:
                del data["mcpServers"]["rook"]
                config_path.write_text(json.dumps(data, indent=2))
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
    roaming_root = Path(os.environ.get("APPDATA", "")) / "Rook"
    temp_root = Path(tempfile.gettempdir()) / "rook"

    for path, label in [
        (runtime_root / "app", "runtime app payload"),
        (runtime_root / "venv", "managed Python venv"),
        (runtime_root / "data", "runtime data"),
        (runtime_root / "logs", "runtime logs"),
        (runtime_root / "discovery", "runtime discovery metadata"),
        (runtime_root / "docs", "runtime docs"),
        (roaming_root, "roaming Rook data"),
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
    parser.add_argument("--claude", action="store_true", help="Configure Claude Code/Desktop MCP registration (skills/hooks come from the marketplace plugin, not this installer)")
    parser.add_argument("--codex", action="store_true", help="Configure OpenAI Codex CLI")
    parser.add_argument("--plugins", action="store_true", help="Validate Rhino plugin deployment")
    parser.add_argument("--uninstall", action="store_true", help="Run uninstall cleanup")
    parser.add_argument("--skip-chirp-install", action="store_true", help="Skip Chirp venv refresh while still using the supplied Chirp directory in generated config")
    parser.add_argument("--skip-validation", action="store_true", help="Skip post-install validation checks")
    args = parser.parse_args()

    if args.uninstall:
        uninstall_cleanup()
        return 0

    if not args.install_dir or not args.mcp_server_dir:
        parser.error("--install-dir and --mcp-server-dir are required for install")

    install_dir = Path(args.install_dir)
    mcp_server_dir = Path(args.mcp_server_dir)
    runtime_root = get_runtime_root(args.runtime_root)
    chirp_dir = Path(args.chirp_dir) if args.chirp_dir else None

    print("=" * 50)
    print("Rook Post-Install Setup")
    print("=" * 50)
    print(f"Install root:  {install_dir}")
    print(f"Runtime root:  {runtime_root}")

    # Step 1: Install MCP server
    managed_python = install_mcp_server(mcp_server_dir, runtime_root)
    if not managed_python:
        print("\nWARNING: MCP server installation failed.")
        print("You can install manually later by creating a venv under %LOCALAPPDATA%\\Rook\\venv")
        return 1
    managed_python_path = str(managed_python).replace("\\", "/")

    # Step 2: Install Chirp (if selected)
    if chirp_dir and chirp_dir.exists():
        if args.skip_chirp_install:
            print("Skipping Chirp venv refresh.")
        elif not install_chirp(chirp_dir):
            print("\nWARNING: Chirp installation failed.")
            print("You can install manually later:")
            print(f"  cd {chirp_dir}")
            print(f"  python -m venv .venv")
            print(f"  .venv\\Scripts\\pip install -e .")

    # Step 3: Generate user-level MCP config (includes CHIRP_HOME if Chirp installed)
    _, data_dir, _ = get_runtime_paths(runtime_root)
    if args.claude:
        configure_claude_code(install_dir, data_dir, managed_python_path, mcp_server_dir, chirp_dir)
    else:
        print("Claude Code/Desktop not selected - skipping Claude config.")

    # Step 4: Configure Claude Desktop
    if args.claude:
        configure_claude_desktop(install_dir, data_dir, managed_python_path, mcp_server_dir, chirp_dir)

    # Step 5: Configure OpenAI Codex CLI (if requested or detected)
    if args.codex:
        configure_codex(install_dir, data_dir, managed_python_path, mcp_server_dir, chirp_dir)
    else:
        print("Codex not selected - skipping Codex config.")

    # Step 6: Copy curated Codex skills to ~/.codex/skills (Claude Code skills/hooks come from the marketplace plugin)
    install_user_assets(install_dir, install_claude=args.claude, install_codex=args.codex)

    # Step 7: Write chat service manifest for Rhino panel
    write_chat_service_manifest(mcp_server_dir, managed_python_path)

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


if __name__ == "__main__":
    sys.exit(main())
