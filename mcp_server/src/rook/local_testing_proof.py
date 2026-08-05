from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager, nullcontext
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from uuid import UUID

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 support floor.
    tomllib = None  # type: ignore[assignment]

from .bridge import call_rhino, rhino_request_context
from .learning.command_knowledge_store import CommandKnowledgeStore
from .preflight import preflight_rhino_command
from . import runtime_paths as runtime_paths_module
from .runtime_harness import CleanupStatus, run_rhino_runtime_harness
from .runtime_paths import resolve_runtime_paths


_CHIRP_CLEANUP_MAX_UNDO_ATTEMPTS = 8
_CHIRP_ACCEPTANCE_PROVIDER_DELAY_SECONDS = 35.0
_CHIRP_ACCEPTANCE_WATCHDOG_SECONDS = 1860.0
_CHIRP_ACCEPTANCE_CONTENT = "[[ ## result ## ]]\nslow-ok\n\n[[ ## completed ## ]]"


@dataclass
class _SlowProvider:
    host: str
    port: int
    request_path: Path
    server: HTTPServer
    thread: threading.Thread
    stop_event: threading.Event
    request_count: int = 0


def _exception_payload(exc: BaseException) -> dict[str, str]:
    return {"exception_type": type(exc).__name__, "message": str(exc)}


def _stop_slow_provider(provider: _SlowProvider) -> None:
    failures: list[dict[str, str]] = []
    provider.stop_event.set()
    for operation, action in (
        ("shutdown", provider.server.shutdown),
        ("server_close", provider.server.server_close),
    ):
        try:
            action()
        except BaseException as exc:
            failures.append({"operation": operation, **_exception_payload(exc)})
    provider.thread.join(timeout=5.0)
    if provider.thread.is_alive():
        failures.append(
            {
                "operation": "thread_join",
                "exception_type": "TimeoutError",
                "message": "slow provider thread remained alive after five seconds",
            }
        )
    if failures:
        raise ProofFailure(
            "slow_provider_cleanup_failed",
            "slow provider cleanup failed",
            {"cleanup_failures": failures},
        )


@contextmanager
def _slow_openai_provider(artifact_dir: Path, *, delay_seconds: float):
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    request_path = artifact_dir / "slow-provider-request.json"
    stop_event = threading.Event()
    provider_ref: dict[str, _SlowProvider] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            if self.path != "/v1/chat/completions":
                self.send_error(404)
                return
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                request = json.loads(self.rfile.read(content_length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                self.send_error(400)
                return

            provider = provider_ref["provider"]
            provider.request_count += 1
            request_path.write_text(
                json.dumps({"path": self.path, "request": request}, indent=2) + "\n",
                encoding="utf-8",
            )
            if stop_event.wait(delay_seconds):
                return

            response = {
                "id": "chatcmpl-rook-timeout-acceptance",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "rook-timeout-acceptance",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": _CHIRP_ACCEPTANCE_CONTENT,
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            }
            encoded = json.dumps(response).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(
        target=server.serve_forever,
        name="rook-chirp-timeout-provider",
        daemon=False,
    )
    provider = _SlowProvider(
        host="127.0.0.1",
        port=int(server.server_address[1]),
        request_path=request_path,
        server=server,
        thread=thread,
        stop_event=stop_event,
    )
    provider_ref["provider"] = provider
    thread.start()

    body_failure: BaseException | None = None
    body_traceback = None
    try:
        yield provider
    except BaseException as exc:
        body_failure = exc
        body_traceback = exc.__traceback__

    cleanup_failure: BaseException | None = None
    try:
        _stop_slow_provider(provider)
    except BaseException as exc:
        cleanup_failure = exc

    if body_failure is not None and cleanup_failure is not None:
        raise ProofFailure(
            "slow_provider_cleanup_failed",
            "slow provider body and cleanup both failed",
            {
                "body_failure": _exception_payload(body_failure),
                "cleanup_failure": _exception_payload(cleanup_failure),
            },
        ) from body_failure
    if cleanup_failure is not None:
        raise cleanup_failure
    if body_failure is not None:
        raise body_failure.with_traceback(body_traceback)


@contextmanager
def _restoring_environment(updates: dict[str, str]):
    prior = {name: os.environ.get(name) for name in updates}
    present = {name: name in os.environ for name in updates}
    os.environ.update(updates)
    try:
        yield
    finally:
        for name in updates:
            if present[name]:
                os.environ[name] = prior[name] or ""
            else:
                os.environ.pop(name, None)


def _stop_owned_chirp_sidecar() -> dict[str, Any]:
    from . import chirp_manager

    process = chirp_manager._chirp_process
    if process is None:
        return {"attempted": False, "success": True, "pid": None, "forced": False}

    chirp_manager._chirp_process = None
    pid = getattr(process, "pid", None)
    forced = False
    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10.0)
            except subprocess.TimeoutExpired:
                forced = True
                process.kill()
                process.wait(timeout=5.0)
    except BaseException as exc:
        raise ProofFailure(
            "chirp_sidecar_cleanup_failed",
            "owned Chirp sidecar cleanup failed",
            {"pid": pid, "forced": forced, **_exception_payload(exc)},
        ) from exc
    return {"attempted": True, "success": True, "pid": pid, "forced": forced}


class ProofFailure(RuntimeError):
    def __init__(
        self,
        failure_label: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_label = failure_label
        self.details = details or {"error": message}


@dataclass(frozen=True)
class GateResult:
    gate: str
    success: bool
    failure_label: str | None
    command: list[str]
    started_at: float
    ended_at: float
    stdout_path: Path | None = None
    stderr_path: Path | None = None
    details: dict[str, Any] = field(default_factory=dict)
    cleanup: dict[str, Any] = field(default_factory=lambda: GateResult.default_cleanup())

    @staticmethod
    def default_cleanup() -> dict[str, Any]:
        return {"attempted": False, "success": None, "label": None, "details": {}}

    @classmethod
    def passed(
        cls,
        *,
        gate: str,
        command: list[str],
        started_at: float,
        ended_at: float,
        stdout_path: Path | None = None,
        stderr_path: Path | None = None,
        details: dict[str, Any] | None = None,
        cleanup: dict[str, Any] | None = None,
    ) -> GateResult:
        return cls(
            gate=gate,
            success=True,
            failure_label=None,
            command=command,
            started_at=started_at,
            ended_at=ended_at,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            details=details or {},
            cleanup=cleanup or cls.default_cleanup(),
        )

    @classmethod
    def failure(
        cls,
        *,
        gate: str,
        failure_label: str,
        command: list[str],
        started_at: float,
        ended_at: float,
        stdout_path: Path | None = None,
        stderr_path: Path | None = None,
        details: dict[str, Any] | None = None,
        cleanup: dict[str, Any] | None = None,
    ) -> GateResult:
        return cls(
            gate=gate,
            success=False,
            failure_label=failure_label,
            command=command,
            started_at=started_at,
            ended_at=ended_at,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            details=details or {},
            cleanup=cleanup or cls.default_cleanup(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "success": self.success,
            "failure_label": self.failure_label,
            "command": self.command,
            "duration_seconds": self.ended_at - self.started_at,
            "stdout_path": None if self.stdout_path is None else str(self.stdout_path),
            "stderr_path": None if self.stderr_path is None else str(self.stderr_path),
            "details": self.details,
            "cleanup": self.cleanup,
        }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _norm(path: Path | str) -> str:
    return str(Path(path).resolve()).replace("\\", "/").lower()


def _path_equal(actual: Any, expected: Path) -> bool:
    if actual is None:
        return False
    return _norm(str(actual)) == _norm(expected)


def assert_path_under(path: Path | str, expected_root: Path | str, failure_label: str) -> None:
    actual = _norm(path)
    expected = _norm(expected_root).rstrip("/") + "/"
    if not actual.startswith(expected):
        raise ProofFailure(
            failure_label,
            f"path is outside expected root: {path}",
            {"actual": actual, "expected_root": expected},
        )


def verify_chirp_origin(chirp_module: Any, chirp_root: Path) -> dict[str, Any]:
    chirp_file = Path(chirp_module.__file__).resolve()
    assert_path_under(chirp_file, chirp_root, "chirp_import_leakage")
    return {"chirp_file": str(chirp_file), "chirp_root": str(chirp_root)}


def verify_chirp_runtime(chirp_root: Path) -> dict[str, Any]:
    chirp_python = chirp_root / ".venv" / "Scripts" / "python.exe"
    if not chirp_python.exists():
        raise ProofFailure(
            "chirp_import_failed",
            f"installed Chirp venv Python not found: {chirp_python}",
        )

    check = (
        "import json, chirp; "
        "from chirp.adapter import configure_secure_dspy_cache; "
        "print(json.dumps({"
        "'chirp_file': chirp.__file__, "
        "'dspy_cache': configure_secure_dspy_cache()"
        "}, sort_keys=True))"
    )
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    env["CHIRP_HOME"] = str(chirp_root)
    env["DSPY_CACHEDIR"] = str(chirp_root / "data" / "dspy-cache")
    env["CHIRP_DSPY_RESTRICT_PICKLE"] = "1"
    completed = subprocess.run(
        [str(chirp_python), "-c", check],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
        env=env,
    )
    if completed.returncode != 0:
        raise ProofFailure(
            "chirp_import_failed",
            "installed Chirp import failed",
            {"stderr": completed.stderr, "returncode": completed.returncode},
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ProofFailure(
            "chirp_import_failed",
            "installed Chirp import produced invalid JSON",
            {"stdout": completed.stdout},
        ) from exc

    chirp_file = Path(payload["chirp_file"]).resolve()
    chirp_site_packages_root = chirp_root / ".venv" / "Lib" / "site-packages" / "chirp"
    assert_path_under(chirp_file, chirp_site_packages_root, "chirp_import_leakage")
    dspy_cache = payload.get("dspy_cache") or {}
    if dspy_cache.get("restrict_pickle") is not True:
        raise ProofFailure(
            "chirp_dspy_cache_unrestricted",
            "installed Chirp DSPy cache did not report restrict_pickle=true",
            {"dspy_cache": dspy_cache},
        )
    if not _path_equal(dspy_cache.get("disk_cache_dir"), chirp_root / "data" / "dspy-cache"):
        raise ProofFailure(
            "chirp_dspy_cache_unrestricted",
            "installed Chirp DSPy cache dir mismatch",
            {"dspy_cache": dspy_cache},
        )
    return {
        "chirp_file": str(chirp_file),
        "chirp_root": str(chirp_root),
        "chirp_python": str(chirp_python),
        "chirp_dspy_cache": dspy_cache,
    }


def verify_rook_dspy_cache(data_root: Path) -> dict[str, Any]:
    from .learning.dspy_config import configure_secure_dspy_cache

    dspy_cache = configure_secure_dspy_cache()
    if dspy_cache.get("restrict_pickle") is not True:
        raise ProofFailure(
            "rook_dspy_cache_unrestricted",
            "installed Rook DSPy cache did not report restrict_pickle=true",
            {"dspy_cache": dspy_cache},
        )
    if not _path_equal(dspy_cache.get("disk_cache_dir"), data_root / "dspy-cache"):
        raise ProofFailure(
            "rook_dspy_cache_unrestricted",
            "installed Rook DSPy cache dir mismatch",
            {"dspy_cache": dspy_cache},
        )
    return dspy_cache


def _read_json(path: Path, missing_label: str = "mcp_config_missing") -> dict[str, Any]:
    if not path.exists():
        raise ProofFailure(missing_label, f"JSON file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ProofFailure("mcp_config_stale", f"JSON file is malformed: {path}") from exc
    if not isinstance(data, dict):
        raise ProofFailure("mcp_config_stale", f"JSON file must contain an object: {path}")
    return data


def verify_mcp_entry(
    *,
    config_path: Path,
    entry: dict[str, Any],
    venv_python: Path,
    install_root: Path,
    data_root: Path,
    chirp_home: Path,
) -> dict[str, Any]:
    expected_cwd = install_root / "mcp_server"
    if not _path_equal(entry.get("command"), venv_python):
        raise ProofFailure(
            "mcp_config_stale",
            f"Rook MCP command mismatch in {config_path}",
            {"command": entry.get("command")},
        )
    if entry.get("args") != ["-m", "rook"]:
        raise ProofFailure(
            "mcp_config_stale",
            f"Rook MCP args mismatch in {config_path}",
            {"args": entry.get("args")},
        )
    if not _path_equal(entry.get("cwd"), expected_cwd):
        raise ProofFailure(
            "mcp_config_stale",
            f"Rook MCP cwd mismatch in {config_path}",
            {"cwd": entry.get("cwd")},
        )
    env = entry.get("env")
    if not isinstance(env, dict):
        raise ProofFailure("mcp_config_stale", f"Rook MCP env missing in {config_path}")
    for key, expected in {
        "ROOK_INSTALL_ROOT": install_root,
        "ROOK_DATA_DIR": data_root,
        "CHIRP_HOME": chirp_home,
    }.items():
        if not _path_equal(env.get(key), expected):
            raise ProofFailure(
                "mcp_config_stale",
                f"Rook MCP env {key} mismatch in {config_path}",
                {"actual": env.get(key), "expected": str(expected)},
            )
    if env.get("ROOK_MODE") != "release":
        raise ProofFailure(
            "mcp_config_stale",
            f"Rook MCP env ROOK_MODE mismatch in {config_path}",
            {"actual": env.get("ROOK_MODE")},
        )
    if env.get("PYTHONPATH") != "":
        raise ProofFailure(
            "mcp_config_stale",
            f"Rook MCP env PYTHONPATH must be cleared in {config_path}",
            {"actual": env.get("PYTHONPATH")},
        )
    if env.get("PYTHONHOME") != "":
        raise ProofFailure(
            "mcp_config_stale",
            f"Rook MCP env PYTHONHOME must be cleared in {config_path}",
            {"actual": env.get("PYTHONHOME")},
        )
    if env.get("ROOK_DSPY_RESTRICT_PICKLE") != "1":
        raise ProofFailure(
            "mcp_config_stale",
            f"Rook MCP env ROOK_DSPY_RESTRICT_PICKLE mismatch in {config_path}",
            {"actual": env.get("ROOK_DSPY_RESTRICT_PICKLE")},
        )
    if not _path_equal(env.get("DSPY_CACHEDIR"), data_root / "dspy-cache"):
        raise ProofFailure(
            "mcp_config_stale",
            f"Rook MCP env DSPY_CACHEDIR mismatch in {config_path}",
            {"actual": env.get("DSPY_CACHEDIR")},
        )
    return {"config_path": str(config_path), "cwd": str(expected_cwd)}


def verify_json_mcp_config(
    *,
    config_path: Path,
    venv_python: Path,
    install_root: Path,
    data_root: Path,
    chirp_home: Path,
) -> dict[str, Any]:
    data = _read_json(config_path)
    entry = (data.get("mcpServers") or {}).get("rook")
    if not isinstance(entry, dict):
        raise ProofFailure("mcp_config_missing", f"missing mcpServers.rook in {config_path}")
    return verify_mcp_entry(
        config_path=config_path,
        entry=entry,
        venv_python=venv_python,
        install_root=install_root,
        data_root=data_root,
        chirp_home=chirp_home,
    )


def _parse_toml_value(value: str) -> Any:
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        parts: list[str] = []
        current = []
        in_string = False
        escape = False
        for char in inner:
            if escape:
                current.append(char)
                escape = False
                continue
            if char == "\\" and in_string:
                current.append(char)
                escape = True
                continue
            if char == '"':
                in_string = not in_string
                current.append(char)
                continue
            if char == "," and not in_string:
                parts.append("".join(current).strip())
                current = []
                continue
            current.append(char)
        parts.append("".join(current).strip())
        return [_parse_toml_value(part) for part in parts if part]
    if value.isdigit():
        return int(value)
    return value


def _parse_codex_rook_toml_fallback(text: str) -> dict[str, Any]:
    entry: dict[str, Any] = {}
    env: dict[str, Any] = {}
    section: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        if section not in {"mcp_servers.rook", "mcp_servers.rook.env"} or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        target = env if section == "mcp_servers.rook.env" else entry
        target[key.strip()] = _parse_toml_value(raw_value)
    if env:
        entry["env"] = env
    return {"mcp_servers": {"rook": entry}}


def _load_codex_toml(text: str) -> dict[str, Any]:
    if tomllib is not None:
        return tomllib.loads(text)
    return _parse_codex_rook_toml_fallback(text)


def verify_codex_mcp_config(
    *,
    config_path: Path,
    venv_python: Path,
    install_root: Path,
    data_root: Path,
    chirp_home: Path,
) -> dict[str, Any]:
    if not config_path.exists():
        raise ProofFailure("mcp_config_missing", f"Codex MCP config not found: {config_path}")
    try:
        data = _load_codex_toml(config_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise ProofFailure(
            "mcp_config_stale",
            f"Codex MCP config is malformed TOML: {config_path}",
        ) from exc
    entry = (data.get("mcp_servers") or {}).get("rook")
    if not isinstance(entry, dict):
        raise ProofFailure("mcp_config_missing", f"missing mcp_servers.rook in {config_path}")
    return verify_mcp_entry(
        config_path=config_path,
        entry=entry,
        venv_python=venv_python,
        install_root=install_root,
        data_root=data_root,
        chirp_home=chirp_home,
    )


def verify_chat_manifest(
    *,
    plugin_dir: Path,
    venv_python: Path,
    install_root: Path,
) -> dict[str, Any]:
    manifest_path = plugin_dir / "RookChatService.json"
    if not manifest_path.exists():
        raise ProofFailure(
            "chat_manifest_missing",
            f"chat service manifest not found: {manifest_path}",
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ProofFailure(
            "chat_manifest_stale",
            f"chat service manifest is malformed: {manifest_path}",
        ) from exc

    expected_working_dir = install_root / "mcp_server"
    data_root = install_root.parent / "data"
    chirp_home = install_root / "chirp"
    if not _path_equal(manifest.get("pythonPath"), venv_python):
        raise ProofFailure(
            "chat_manifest_stale",
            "chat service pythonPath mismatch",
            {"pythonPath": manifest.get("pythonPath")},
        )
    if not _path_equal(manifest.get("workingDirectory"), expected_working_dir):
        raise ProofFailure(
            "chat_manifest_stale",
            "chat service workingDirectory mismatch",
            {"workingDirectory": manifest.get("workingDirectory")},
        )
    if manifest.get("module") != "rook.agent.chat.service_main":
        raise ProofFailure(
            "chat_manifest_stale",
            "chat service module mismatch",
            {"module": manifest.get("module")},
        )
    entries = manifest.get("pythonPathEntries") or []
    if entries:
        raise ProofFailure(
            "chat_manifest_stale",
            "release chat service manifest must not contain source pythonPathEntries",
            {"pythonPathEntries": entries},
        )
    env = manifest.get("environment") or {}
    expected_env = {
        "ROOK_INSTALL_ROOT": install_root,
        "ROOK_DATA_DIR": data_root,
        "CHIRP_HOME": chirp_home,
        "DSPY_CACHEDIR": data_root / "dspy-cache",
    }
    for key, expected in expected_env.items():
        if not _path_equal(env.get(key), expected):
            raise ProofFailure(
                "chat_manifest_stale",
                f"chat service environment {key} mismatch",
                {"actual": env.get(key), "expected": str(expected)},
            )
    for key, expected in {
        "ROOK_MODE": "release",
        "ROOK_DSPY_RESTRICT_PICKLE": "1",
        "PYTHONHOME": "",
        "PYTHONPATH": "",
    }.items():
        if env.get(key) != expected:
            raise ProofFailure(
                "chat_manifest_stale",
                f"chat service environment {key} mismatch",
                {"actual": env.get(key), "expected": expected},
            )
    return {
        "manifest_path": str(manifest_path),
        "python_path": str(venv_python),
        "working_directory": str(expected_working_dir),
        "chirp_home": str(chirp_home),
        "release_pythonpath_entries": False,
    }


def verify_effective_configs(
    *,
    paths: Any,
    venv_python: Path,
    chirp_home: Path,
) -> dict[str, Any]:
    appdata_value = os.environ.get("APPDATA")
    if not appdata_value:
        raise ProofFailure("runtime_path_mismatch", "APPDATA is not set")
    appdata = Path(appdata_value)
    home = Path.home()
    plugin_dir = appdata / "McNeel" / "Rhinoceros" / "8.0" / "Plug-ins" / "RookNative"
    checked: dict[str, Any] = {}
    warnings: list[dict[str, str]] = []

    for config_path in (
        home / ".claude.json",
        appdata / "Claude" / "claude_desktop_config.json",
    ):
        if config_path.exists():
            try:
                checked[str(config_path)] = verify_json_mcp_config(
                    config_path=config_path,
                    venv_python=venv_python,
                    install_root=paths.install_root,
                    data_root=paths.data_root,
                    chirp_home=chirp_home,
                )
            except ProofFailure as exc:
                warnings.append(
                    {
                        "path": str(config_path),
                        "failure_label": exc.failure_label,
                        "error": str(exc),
                    }
                )

    codex_config = home / ".codex" / "config.toml"
    if codex_config.exists():
        try:
            checked[str(codex_config)] = verify_codex_mcp_config(
                config_path=codex_config,
                venv_python=venv_python,
                install_root=paths.install_root,
                data_root=paths.data_root,
                chirp_home=chirp_home,
            )
        except ProofFailure as exc:
            warnings.append(
                {
                    "path": str(codex_config),
                    "failure_label": exc.failure_label,
                    "error": str(exc),
                }
            )

    if not checked:
        raise ProofFailure(
            "mcp_config_missing",
            "no valid MCP config files were found to verify",
            {"mcp_config_warnings": warnings},
        )

    return {
        "mcp_configs": checked,
        "mcp_config_warnings": warnings,
        "chat_manifest": verify_chat_manifest(
            plugin_dir=plugin_dir,
            venv_python=venv_python,
            install_root=paths.install_root,
        ),
    }


def verify_command_knowledge_runtime() -> dict[str, Any]:
    store = CommandKnowledgeStore()
    diagnostics = store.layering_diagnostics()
    grasshopper_source = store.get_command_source("-Grasshopper")
    preflight = preflight_rhino_command("_Grasshopper", store)
    details = {
        "command_knowledge": diagnostics,
        "grasshopper_source": grasshopper_source,
        "grasshopper_preflight": "passed" if preflight is None else preflight,
    }

    if preflight is not None:
        raise ProofFailure(
            "command_knowledge_stale",
            "Grasshopper command knowledge failed preflight",
            details,
        )
    if grasshopper_source == "missing":
        raise ProofFailure(
            "command_knowledge_stale",
            "Grasshopper command knowledge is missing",
            details,
        )
    if grasshopper_source not in {"bundled", "layered"}:
        raise ProofFailure(
            "command_knowledge_stale",
            "Grasshopper command knowledge must come from bundled release metadata",
            details,
        )

    return details


def seed_release_env_from_installed_venv() -> bool:
    """Seed release env when invoked from %LOCALAPPDATA%/Rook/venv.

    The public smoke command is intentionally simple for testers:
    %LOCALAPPDATA%/Rook/venv/Scripts/python.exe -m rook.local_testing_proof
    python-smoke-evidence. That process starts without the MCP/chat env block,
    so derive the installed runtime contract from sys.executable before the
    canonical runtime resolver runs.
    """

    executable = Path(sys.executable).resolve()
    if executable.name.lower() != "python.exe":
        return False
    if executable.parent.name.lower() != "scripts":
        return False
    venv_dir = executable.parent.parent
    if venv_dir.name.lower() != "venv":
        return False

    runtime_root = venv_dir.parent
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        return False
    expected_runtime_root = (Path(local_appdata) / "Rook").resolve()
    if _norm(runtime_root) != _norm(expected_runtime_root):
        return False

    install_root = runtime_root / "app"
    data_root = runtime_root / "data"

    os.environ.setdefault("ROOK_INSTALL_ROOT", str(install_root))
    os.environ.setdefault("ROOK_DATA_DIR", str(data_root))
    os.environ.setdefault("ROOK_MODE", "release")
    os.environ.setdefault("CHIRP_HOME", str(install_root / "chirp"))
    os.environ.setdefault("DSPY_CACHEDIR", str(data_root / "dspy-cache"))
    os.environ.setdefault("ROOK_DSPY_RESTRICT_PICKLE", "1")
    os.environ["PYTHONPATH"] = ""
    os.environ["PYTHONHOME"] = ""
    runtime_paths_module._cached_runtime_paths = None
    return True


def verify_installed_runtime(command: list[str]) -> GateResult:
    started = time.monotonic()
    try:
        import rook

        paths = resolve_runtime_paths()
        install_root = paths.install_root
        data_root = paths.data_root
        expected_rook_root = Path(sys.executable).resolve().parent.parent / "Lib" / "site-packages" / "rook"
        expected_chirp_root = install_root / "chirp"

        assert_path_under(
            Path(rook.__file__).resolve(),
            expected_rook_root,
            "rook_import_leakage",
        )
        if paths.mode != "release":
            raise ProofFailure(
                "runtime_path_mismatch",
                "ROOK_MODE did not resolve to release",
                {"mode": paths.mode},
            )
        if _norm(install_root) != _norm(Path(os.environ.get("ROOK_INSTALL_ROOT", install_root))):
            raise ProofFailure("runtime_path_mismatch", "ROOK_INSTALL_ROOT mismatch")
        if _norm(data_root) != _norm(Path(os.environ.get("ROOK_DATA_DIR", data_root))):
            raise ProofFailure("runtime_path_mismatch", "ROOK_DATA_DIR mismatch")

        rook_dspy_cache = verify_rook_dspy_cache(data_root)
        chirp_details = verify_chirp_runtime(expected_chirp_root)
        command_knowledge_details = verify_command_knowledge_runtime()
        config_details = verify_effective_configs(
            paths=paths,
            venv_python=Path(sys.executable),
            chirp_home=expected_chirp_root,
        )

        return GateResult.passed(
            gate="installed_runtime",
            command=command,
            started_at=started,
            ended_at=time.monotonic(),
            details={
                "rook_file": str(Path(rook.__file__).resolve()),
                "rook_dspy_cache": rook_dspy_cache,
                "install_root": str(install_root),
                "data_root": str(data_root),
                **chirp_details,
                **command_knowledge_details,
                **config_details,
            },
        )
    except ProofFailure as exc:
        return GateResult.failure(
            gate="installed_runtime",
            failure_label=exc.failure_label,
            command=command,
            started_at=started,
            ended_at=time.monotonic(),
            details=exc.details,
        )
    except Exception as exc:
        return GateResult.failure(
            gate="installed_runtime",
            failure_label="installed_runtime_failed",
            command=command,
            started_at=started,
            ended_at=time.monotonic(),
            details={"error": str(exc)},
        )


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _pip_check_ok(install_state: dict[str, Any], runtime_name: str) -> bool:
    runtime_state = install_state.get(runtime_name)
    if not isinstance(runtime_state, dict):
        return False
    return "No broken requirements found" in str(runtime_state.get("pip_check", ""))


def build_release_smoke_python_evidence(installed_details: dict[str, Any]) -> dict[str, Any]:
    paths = resolve_runtime_paths()
    venv_python = Path(sys.executable).resolve()
    private_python_version = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    runtime_manifest_path = paths.install_root / "python-runtime-manifest.json"
    install_state_path = paths.data_root / "install-state.json"
    runtime_manifest = _read_optional_json(runtime_manifest_path)
    install_state = _read_optional_json(install_state_path)
    chat_manifest = installed_details.get("chat_manifest") or {}

    return {
        "python_runtime_manifest": str(runtime_manifest_path),
        "install_state": str(install_state_path),
        "private_python_path": str(
            paths.runtime_root
            / "python"
            / f"cpython-{private_python_version}"
            / "python.exe"
        ),
        "private_python_version": private_python_version,
        "rook_venv_path": str(venv_python.parent.parent),
        "chirp_venv_path": str(paths.install_root / "chirp" / ".venv"),
        "rook_import_file": str(installed_details.get("rook_file", "")),
        "chirp_import_file": str(installed_details.get("chirp_file", "")),
        "pip_check": {
            "rook": {"ok": _pip_check_ok(install_state, "rook")},
            "chirp": {"ok": _pip_check_ok(install_state, "chirp")},
        },
        "rook_dspy_cache": installed_details.get("rook_dspy_cache") or {},
        "chirp_dspy_cache": installed_details.get("chirp_dspy_cache") or {},
        "license_provenance": {"manifest_path": str(runtime_manifest_path)},
        "config_identity": {
            "chat_service_python_path": str(chat_manifest.get("python_path", "")),
            "chirp_home": str(chat_manifest.get("chirp_home", "")),
            "release_pythonpath_entries": bool(
                chat_manifest.get("release_pythonpath_entries", True)
            ),
        },
        "no_index_install": True,
        "chirp_git_sha": str(runtime_manifest.get("chirp_git_sha", "")),
        "chirp_source_archive_sha256": str(
            runtime_manifest.get("chirp_source_archive_sha256", "")
        ),
    }


def python_smoke_evidence_gate(command: list[str]) -> GateResult:
    started = time.monotonic()
    seed_release_env_from_installed_venv()
    installed = verify_installed_runtime(command)
    if not installed.success:
        return GateResult.failure(
            gate="python_smoke_evidence",
            failure_label=installed.failure_label or "installed_runtime_failed",
            command=command,
            started_at=started,
            ended_at=time.monotonic(),
            details=installed.details,
        )
    return GateResult.passed(
        gate="python_smoke_evidence",
        command=command,
        started_at=started,
        ended_at=time.monotonic(),
        details=build_release_smoke_python_evidence(installed.details),
    )


async def _call_tool_dispatch(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    from .server import _call_tool_dispatch as dispatch

    return await dispatch(name, arguments)


async def _list_public_tools():
    from .server import list_tools

    return await list_tools()


async def _call_public_tool(name: str, arguments: dict[str, Any]) -> Any:
    from .server import call_tool

    response = await call_tool(name, arguments)
    if not response:
        raise ProofFailure(
            "progressive_discovery_failed", f"{name} returned no content"
        )
    text = str(response[0].text)
    if text.startswith("Error:"):
        raise ProofFailure(
            "progressive_discovery_failed",
            f"{name} failed",
            {"tool": name, "wire": text},
        )
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProofFailure(
            "progressive_discovery_failed",
            f"{name} returned invalid JSON",
            {"tool": name, "wire": text, "error": str(exc)},
        ) from exc


async def _run_live_progressive_gh_status(
    args: dict[str, int],
) -> dict[str, Any]:
    tools = await _list_public_tools()
    names = {tool.name for tool in tools}
    gateways = (
        "rook_tools_ls",
        "rook_tools_search",
        "rook_tools_read",
        "rook_tools_call",
    )
    missing = [name for name in gateways if name not in names]
    if missing or "gh_status" in names:
        raise ProofFailure(
            "progressive_discovery_failed",
            "lean catalog contract failed",
            {
                "missing_gateways": missing,
                "gh_status_directly_advertised": "gh_status" in names,
            },
        )

    search = await _call_public_tool(
        "rook_tools_search", {"query": "gh_status", "limit": 10}
    )
    if not isinstance(search, list) or not any(
        item.get("name") == "gh_status" for item in search
    ):
        raise ProofFailure(
            "progressive_discovery_failed",
            "gh_status exact-name search failed",
            {"search": search},
        )

    read = await _call_public_tool("rook_tools_read", {"name": "gh_status"})
    read_ok = (
        isinstance(read, dict)
        and read.get("name") == "gh_status"
        and read.get("mcp_dispatchable") is True
        and isinstance(read.get("input_schema"), dict)
        and read["input_schema"].get("type") == "object"
    )
    if not read_ok:
        raise ProofFailure(
            "progressive_discovery_failed",
            "gh_status read contract failed",
            {"read": read},
        )

    called = await _call_public_tool(
        "rook_tools_call", {"name": "gh_status", "arguments": dict(args)}
    )
    return {
        "profile": "lean",
        "gateways": list(gateways),
        "target": "gh_status",
        "target_hidden": True,
        "search": search,
        "read": read,
        "call": called,
    }


def _gh_ready(status: dict[str, Any]) -> bool:
    if not status.get("success"):
        return False
    data = status.get("data")
    if not isinstance(data, dict):
        return False
    return bool(
        data.get("ready_for_edit")
        or data.get("readyForEdit")
        or data.get("ready")
        or (data.get("available") and data.get("has_active_document"))
    )


def _grasshopper_launch_may_have_started(result: dict[str, Any]) -> bool:
    data = result.get("data")
    if isinstance(data, dict):
        return bool(data.get("execution_may_have_occurred") or data.get("state_uncertain"))
    return False


async def _ensure_grasshopper_ready(args: dict[str, int]) -> dict[str, Any]:
    status = await _call_tool_dispatch("gh_status", dict(args))
    if _gh_ready(status):
        return {"status": status, "opened": False}

    open_result = await _call_tool_dispatch(
        "rhino_command",
        {**args, "command": "_Grasshopper", "echo": False},
    )
    if not open_result.get("success") and not _grasshopper_launch_may_have_started(open_result):
        raise ProofFailure(
            "gh_not_ready",
            "failed to launch Grasshopper",
            {"gh_status": status, "rhino_command": open_result},
        )

    deadline = time.monotonic() + 45.0
    last_status = status
    last_new_doc: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        await asyncio.sleep(1.0)
        last_new_doc = await _call_tool_dispatch("gh_document_new", dict(args))
        if last_new_doc.get("success"):
            status = await _call_tool_dispatch("gh_status", dict(args))
            return {
                "status": status,
                "opened": True,
                "rhino_command": open_result,
                "gh_document_new": last_new_doc,
            }

        last_status = await _call_tool_dispatch("gh_status", dict(args))
        if _gh_ready(last_status):
            return {
                "status": last_status,
                "opened": True,
                "rhino_command": open_result,
                "gh_document_new": last_new_doc,
            }

    raise ProofFailure(
        "gh_not_ready",
        "Grasshopper did not become ready",
        {
            "gh_status": last_status,
            "rhino_command": open_result,
            "gh_document_new": last_new_doc,
        },
    )


def _dict_value_ci(mapping: dict[str, Any], *names: str) -> Any:
    wanted = {name.casefold() for name in names}
    for key, value in mapping.items():
        if isinstance(key, str) and key.casefold() in wanted:
            return value
    return None


def _canonical_instance_guid(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = UUID(value.strip())
    except (ValueError, AttributeError):
        return None
    if parsed.int == 0:
        return None
    return str(parsed)


def _failure_context(failure: ProofFailure) -> dict[str, Any]:
    return {
        "failure_label": failure.failure_label,
        "message": str(failure),
        "details": failure.details,
    }


def _cancellation_failure(
    stage: str, cancellation: asyncio.CancelledError
) -> ProofFailure:
    return ProofFailure(
        "operation_cancelled",
        f"{stage} was cancelled",
        {
            "stage": stage,
            "exception_type": type(cancellation).__name__,
            "message": str(cancellation),
        },
    )


def _cleanup_failure_details(
    details: dict[str, Any],
    *,
    original_failure: ProofFailure | None,
    interruptions: list[asyncio.CancelledError],
    direct_cancellation: tuple[str, asyncio.CancelledError] | None = None,
) -> dict[str, Any]:
    result = dict(details)
    cancellations = [
        _failure_context(_cancellation_failure("cleanup_wait", interruption))
        for interruption in interruptions
    ]
    if direct_cancellation is not None:
        stage, cancellation = direct_cancellation
        cancellations.append(
            _failure_context(_cancellation_failure(stage, cancellation))
        )

    if original_failure is not None:
        result["original_failure"] = _failure_context(original_failure)
    elif cancellations:
        result["original_failure"] = cancellations[0]
    if cancellations:
        result["cancellation_context"] = cancellations
    return result


async def _await_cleanup_shielded(
    cleanup_awaitable: Any,
    interruptions: list[asyncio.CancelledError],
) -> dict[str, Any]:
    cleanup_task = asyncio.create_task(cleanup_awaitable)
    while True:
        try:
            return await asyncio.shield(cleanup_task)
        except asyncio.CancelledError as exc:
            interruptions.append(exc)
            if cleanup_task.done():
                return cleanup_task.result()


async def _capture_chirp_cleanup_state(
    args: dict[str, int],
    *,
    dispatch_fn: Any,
    call_rhino_fn: Any,
) -> dict[str, Any]:
    try:
        status = await dispatch_fn("gh_status", dict(args))
    except Exception as exc:
        raise ProofFailure(
            "cleanup_failed",
            "cleanup gh_status probe raised an exception",
            {
                "probe": "gh_status",
                "exception_type": type(exc).__name__,
                "message": str(exc),
            },
        ) from exc
    if not isinstance(status, dict) or status.get("success") is not True:
        raise ProofFailure(
            "cleanup_failed",
            "cleanup gh_status probe failed",
            {"gh_status": status},
        )
    status_data = status.get("data")
    object_count = (
        _dict_value_ci(status_data, "object_count", "objectCount")
        if isinstance(status_data, dict)
        else None
    )
    if (
        not isinstance(object_count, int)
        or isinstance(object_count, bool)
        or object_count < 0
    ):
        raise ProofFailure(
            "cleanup_failed",
            "cleanup gh_status object_count was malformed",
            {"gh_status": status},
        )

    try:
        inventory = await call_rhino_fn(
            "/gh/errors",
            "GET",
            {"debug": True},
            port=args.get("port"),
            process_id=args.get("process_id"),
        )
    except Exception as exc:
        raise ProofFailure(
            "cleanup_failed",
            "cleanup debug inventory probe raised an exception",
            {
                "probe": "gh_errors_debug_inventory",
                "exception_type": type(exc).__name__,
                "message": str(exc),
            },
        ) from exc
    if not isinstance(inventory, dict) or inventory.get("success") is not True:
        raise ProofFailure(
            "cleanup_failed",
            "cleanup debug inventory probe failed",
            {"debug_inventory": inventory},
        )
    inventory_data = inventory.get("data")
    if not isinstance(inventory_data, dict):
        raise ProofFailure(
            "cleanup_failed",
            "cleanup debug inventory data was malformed",
            {"debug_inventory": inventory},
        )
    debug_total = _dict_value_ci(
        inventory_data, "totalComponents", "total_components"
    )
    entries = _dict_value_ci(inventory_data, "debugInfo", "debug_info")
    if (
        not isinstance(debug_total, int)
        or isinstance(debug_total, bool)
        or debug_total < 0
        or not isinstance(entries, list)
    ):
        raise ProofFailure(
            "cleanup_failed",
            "cleanup debug inventory was malformed",
            {"debug_inventory": inventory},
        )

    instance_guids: list[str] = []
    for index, entry in enumerate(entries):
        raw_guid = (
            _dict_value_ci(entry, "Guid", "guid") if isinstance(entry, dict) else None
        )
        guid = _canonical_instance_guid(raw_guid)
        if guid is None:
            raise ProofFailure(
                "cleanup_failed",
                f"cleanup debug inventory entry {index} had a malformed instance GUID",
                {"debug_inventory": inventory},
            )
        instance_guids.append(guid)

    if len(set(instance_guids)) != len(instance_guids):
        raise ProofFailure(
            "cleanup_failed",
            "cleanup debug inventory contained duplicate instance GUIDs",
            {"debug_inventory": inventory},
        )
    if debug_total != len(instance_guids) or object_count != debug_total:
        raise ProofFailure(
            "cleanup_failed",
            "cleanup gh_status and debug inventory counts were inconsistent",
            {
                "gh_status": status,
                "debug_inventory": inventory,
                "object_count": object_count,
                "debug_total": debug_total,
                "inventory_count": len(instance_guids),
            },
        )

    return {
        "instance_guids": sorted(instance_guids),
        "object_count": object_count,
        "debug_total": debug_total,
        "gh_status": status,
        "debug_inventory": inventory,
    }


def _chirp_cleanup_evidence(
    *,
    attempts: list[Any],
    component_guid: str | None,
    component_observed_after_attempt: bool | None,
    baseline: dict[str, Any],
    final: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized_guid = _canonical_instance_guid(component_guid)
    final_guids = final.get("instance_guids", []) if isinstance(final, dict) else []
    return {
        "attempts": attempts,
        "attempt_count": len(attempts),
        "component_guid": component_guid,
        "component_observed_after_attempt": component_observed_after_attempt,
        "component_removed": (
            final is not None
            and normalized_guid is not None
            and component_observed_after_attempt is True
            and normalized_guid not in set(final_guids)
        ),
        "baseline_object_count": baseline["object_count"],
        "final_object_count": final.get("object_count") if final else None,
        "baseline_instance_guids": baseline["instance_guids"],
        "final_instance_guids": final_guids,
        "baseline_state": baseline,
        "final_state": final,
    }


def _cleanup_failure(
    message: str,
    *,
    attempts: list[Any],
    component_guid: str | None,
    baseline: dict[str, Any],
    final: dict[str, Any] | None,
    component_observed_after_attempt: bool | None = None,
    extra: dict[str, Any] | None = None,
) -> ProofFailure:
    details: dict[str, Any] = {
        "gh_undo": _chirp_cleanup_evidence(
            attempts=attempts,
            component_guid=component_guid,
            component_observed_after_attempt=component_observed_after_attempt,
            baseline=baseline,
            final=final,
        )
    }
    if extra:
        details.update(extra)
    return ProofFailure("cleanup_failed", message, details)


async def _restore_chirp_cleanup_state(
    args: dict[str, int],
    *,
    baseline: dict[str, Any],
    component_guid: str | None,
    dispatch_fn: Any,
    call_rhino_fn: Any,
    attempt_log: list[Any] | None = None,
) -> dict[str, Any]:
    attempts = attempt_log if attempt_log is not None else []
    try:
        current = await _capture_chirp_cleanup_state(
            args,
            dispatch_fn=dispatch_fn,
            call_rhino_fn=call_rhino_fn,
        )
    except ProofFailure as exc:
        raise _cleanup_failure(
            f"cleanup state probe failed: {exc}",
            attempts=attempts,
            component_guid=component_guid,
            baseline=baseline,
            final=None,
            extra={"probe_failure": _failure_context(exc)},
        ) from exc

    baseline_guids = set(baseline["instance_guids"])
    normalized_guid = _canonical_instance_guid(component_guid)
    target_was_in_baseline = normalized_guid in baseline_guids if normalized_guid else False
    component_observed_after_attempt = (
        normalized_guid is not None
        and not target_was_in_baseline
        and normalized_guid in set(current["instance_guids"])
    )

    def fail(
        message: str,
        *,
        extra: dict[str, Any] | None = None,
    ) -> ProofFailure:
        return _cleanup_failure(
            message,
            attempts=attempts,
            component_guid=component_guid,
            component_observed_after_attempt=component_observed_after_attempt,
            baseline=baseline,
            final=current,
            extra=extra,
        )

    while True:
        current_guids = set(current["instance_guids"])
        if current_guids == baseline_guids:
            if current["object_count"] != baseline["object_count"]:
                raise fail(
                    "cleanup instance inventory matched baseline but object count did not"
                )
            evidence = _chirp_cleanup_evidence(
                attempts=attempts,
                component_guid=component_guid,
                component_observed_after_attempt=component_observed_after_attempt,
                baseline=baseline,
                final=current,
            )
            return evidence

        missing_baseline = sorted(baseline_guids - current_guids)
        if missing_baseline:
            raise fail(
                "cleanup state lost baseline instance GUIDs",
                extra={"missing_baseline_instance_guids": missing_baseline},
            )

        new_guids = sorted(current_guids - baseline_guids)
        if normalized_guid is None:
            raise fail(
                "cleanup cannot safely undo additions while the created target identity is unknown",
                extra={"remaining_new_instance_guids": new_guids},
            )
        if target_was_in_baseline:
            raise fail(
                "created instance GUID was already present in baseline; cleanup cannot "
                "safely identify post-attempt additions",
                extra={"remaining_new_instance_guids": new_guids},
            )
        if set(new_guids) != {normalized_guid}:
            raise fail(
                "cleanup can undo only the created target; unrelated new instance GUIDs "
                "make cleanup ambiguous",
                extra={"remaining_new_instance_guids": new_guids},
            )
        if not new_guids or current["object_count"] <= baseline["object_count"]:
            raise fail(
                "cleanup reached the baseline count while new instance GUIDs remained",
                extra={"remaining_new_instance_guids": new_guids},
            )
        if len(attempts) >= _CHIRP_CLEANUP_MAX_UNDO_ATTEMPTS:
            raise fail("gh_undo cleanup exhausted its safe attempt bound")

        try:
            undo = await dispatch_fn("gh_undo", dict(args))
        except asyncio.CancelledError as exc:
            undo = {"exception_type": type(exc).__name__, "message": str(exc)}
            attempts.append(undo)
            raise fail("gh_undo cleanup dispatch was cancelled") from exc
        except Exception as exc:
            undo = {"exception_type": type(exc).__name__, "message": str(exc)}
            attempts.append(undo)
            raise fail("gh_undo cleanup dispatch raised an exception") from exc
        attempts.append(undo)
        if not isinstance(undo, dict):
            raise fail("gh_undo cleanup returned a malformed response")
        if undo.get("success") is not True:
            raise fail("gh_undo cleanup failed")

        try:
            current = await _capture_chirp_cleanup_state(
                args,
                dispatch_fn=dispatch_fn,
                call_rhino_fn=call_rhino_fn,
            )
        except ProofFailure as exc:
            raise _cleanup_failure(
                f"cleanup state probe failed after gh_undo: {exc}",
                attempts=attempts,
                component_guid=component_guid,
                component_observed_after_attempt=component_observed_after_attempt,
                baseline=baseline,
                final=None,
                extra={"probe_failure": _failure_context(exc)},
            ) from exc


def _chirp_validation_failure(
    chirp: Any,
) -> tuple[ProofFailure | None, str | None]:
    if not isinstance(chirp, dict):
        return (
            ProofFailure(
                "chirp_create_failed",
                "chirp_create returned a malformed response",
                {"chirp_create": chirp},
            ),
            None,
        )
    chirp_data = chirp.get("data")
    raw_component_guid = (
        chirp_data.get("component_guid") if isinstance(chirp_data, dict) else None
    )
    component_guid = _canonical_instance_guid(raw_component_guid)
    if chirp.get("success") is not True:
        return (
            ProofFailure(
                "chirp_create_failed",
                "chirp_create failed",
                {"chirp_create": chirp},
            ),
            component_guid,
        )
    if not isinstance(chirp_data, dict):
        return (
            ProofFailure(
                "chirp_create_failed",
                "chirp_create data was malformed",
                {"chirp_create": chirp},
            ),
            component_guid,
        )
    if chirp_data.get("warning"):
        return (
            ProofFailure(
                "chirp_component_warning",
                "chirp_create warning",
                {"chirp_create": chirp},
            ),
            component_guid,
        )
    if chirp_data.get("component_errors"):
        return (
            ProofFailure(
                "chirp_component_error",
                "chirp_create component errors",
                {"chirp_create": chirp},
            ),
            component_guid,
        )
    if component_guid is None:
        return (
            ProofFailure(
                "chirp_create_failed",
                "chirp_create did not return a valid component_guid",
                {"chirp_create": chirp},
            ),
            None,
        )
    return None, component_guid


def _gh_errors_validation_failure(
    errors: Any, component_guid: str
) -> ProofFailure | None:
    if not isinstance(errors, dict) or errors.get("success") is not True:
        return ProofFailure(
            "gh_component_error",
            "gh_errors failed",
            {"gh_errors": errors},
        )
    data = errors.get("data")
    entries = _dict_value_ci(data, "errors") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return ProofFailure(
            "gh_component_error",
            "gh_errors returned malformed data",
            {"gh_errors": errors},
        )
    normalized_guid = _canonical_instance_guid(component_guid)
    if normalized_guid is None:
        return ProofFailure(
            "gh_component_error",
            "created component GUID was malformed",
            {"gh_errors": errors},
        )
    for index, item in enumerate(entries):
        raw_guid = _dict_value_ci(item, "guid") if isinstance(item, dict) else None
        guid = _canonical_instance_guid(raw_guid)
        messages = _dict_value_ci(item, "errors") if isinstance(item, dict) else None
        if guid is None or not isinstance(messages, list):
            return ProofFailure(
                "gh_component_error",
                f"gh_errors entry {index} was malformed",
                {"gh_errors": errors},
            )
        if guid == normalized_guid and messages:
            return ProofFailure(
                "gh_component_error",
                "created component has GH errors",
                {"gh_errors": errors},
            )
    return None


async def _run_chirp_smoke_mutation(
    args: dict[str, int],
    *,
    component_name: str,
    dispatch_fn: Any,
    call_rhino_fn: Any,
    create_arguments: dict[str, Any] | None = None,
    verify_created_fn: Any | None = None,
) -> dict[str, Any]:
    baseline = await _capture_chirp_cleanup_state(
        args,
        dispatch_fn=dispatch_fn,
        call_rhino_fn=call_rhino_fn,
    )
    chirp: Any = None
    errors: Any = None
    component_guid: str | None = None
    original_failure: ProofFailure | None = None
    pending_cancellation: asyncio.CancelledError | None = None
    verification: Any = None

    request = {
        **args,
        "category": "classifier",
        "name": component_name,
        "pins_in": [{"name": "Input", "type": "string", "optional": True}],
        "pins_out": [{"name": "Result", "type": "string"}],
        "signature": "input -> result",
        "deterministic_code": "Result = Input ?? string.Empty;",
        "deterministic_only": True,
        "x": 40,
        "y": 40,
    }
    if create_arguments is not None:
        request = {**args, **create_arguments}

    try:
        chirp = await dispatch_fn("chirp_create", request)
    except asyncio.CancelledError as exc:
        pending_cancellation = exc
        original_failure = _cancellation_failure("chirp_create", exc)
    except Exception as exc:
        original_failure = ProofFailure(
            "chirp_create_failed",
            "chirp_create dispatch raised an exception",
            {"exception_type": type(exc).__name__, "message": str(exc)},
        )
    else:
        original_failure, component_guid = _chirp_validation_failure(chirp)

    if component_guid is not None and component_guid in set(baseline["instance_guids"]):
        details: dict[str, Any] = {"chirp_create": chirp}
        if original_failure is not None:
            details["prior_validation_failure"] = _failure_context(original_failure)
        original_failure = ProofFailure(
            "chirp_create_failed",
            "chirp_create returned an instance GUID already present in the baseline",
            details,
        )

    if (
        original_failure is None
        and component_guid is not None
        and verify_created_fn is not None
    ):
        try:
            verification = await verify_created_fn(component_guid, chirp)
        except asyncio.CancelledError as exc:
            pending_cancellation = exc
            original_failure = _cancellation_failure("chirp_verification", exc)
        except ProofFailure as exc:
            original_failure = exc
        except Exception as exc:
            original_failure = ProofFailure(
                "chirp_verification_failed",
                "Chirp verification raised an exception",
                {"exception_type": type(exc).__name__, "message": str(exc)},
            )

    if original_failure is None and component_guid is not None:
        try:
            errors = await dispatch_fn("gh_errors", dict(args))
        except asyncio.CancelledError as exc:
            pending_cancellation = exc
            original_failure = _cancellation_failure("gh_errors", exc)
        except Exception as exc:
            original_failure = ProofFailure(
                "gh_component_error",
                "gh_errors dispatch raised an exception",
                {"exception_type": type(exc).__name__, "message": str(exc)},
            )
        else:
            original_failure = _gh_errors_validation_failure(errors, component_guid)

    cleanup_attempts: list[Any] = []
    cleanup_interruptions: list[asyncio.CancelledError] = []
    try:
        cleanup = await _await_cleanup_shielded(
            _restore_chirp_cleanup_state(
                args,
                baseline=baseline,
                component_guid=component_guid,
                dispatch_fn=dispatch_fn,
                call_rhino_fn=call_rhino_fn,
                attempt_log=cleanup_attempts,
            ),
            cleanup_interruptions,
        )
    except ProofFailure as cleanup_failure:
        if original_failure is None and not cleanup_interruptions:
            raise
        details = _cleanup_failure_details(
            cleanup_failure.details,
            original_failure=original_failure,
            interruptions=cleanup_interruptions,
        )
        raise ProofFailure("cleanup_failed", str(cleanup_failure), details) from cleanup_failure
    except asyncio.CancelledError as exc:
        cleanup_failure = _cleanup_failure(
            "chirp cleanup task was cancelled",
            attempts=cleanup_attempts,
            component_guid=component_guid,
            baseline=baseline,
            final=None,
            extra={
                "restore_exception": {
                    "exception_type": type(exc).__name__,
                    "message": str(exc),
                }
            },
        )
        details = _cleanup_failure_details(
            cleanup_failure.details,
            original_failure=original_failure,
            interruptions=cleanup_interruptions,
            direct_cancellation=("cleanup", exc),
        )
        raise ProofFailure("cleanup_failed", str(cleanup_failure), details) from exc
    except Exception as exc:
        cleanup_failure = _cleanup_failure(
            "chirp cleanup raised an unexpected exception",
            attempts=cleanup_attempts,
            component_guid=component_guid,
            baseline=baseline,
            final=None,
            extra={
                "restore_exception": {
                    "exception_type": type(exc).__name__,
                    "message": str(exc),
                }
            },
        )
        details = _cleanup_failure_details(
            cleanup_failure.details,
            original_failure=original_failure,
            interruptions=cleanup_interruptions,
        )
        raise ProofFailure("cleanup_failed", str(cleanup_failure), details) from exc

    if pending_cancellation is not None:
        raise pending_cancellation
    if cleanup_interruptions:
        raise cleanup_interruptions[0]

    if (
        original_failure is None
        and component_guid is not None
        and cleanup.get("component_observed_after_attempt") is not True
    ):
        original_failure = ProofFailure(
            "chirp_create_failed",
            "successful chirp_create target was not observed after the attempt",
            {"chirp_create": chirp},
        )

    if original_failure is not None:
        details = dict(original_failure.details)
        details["cleanup"] = cleanup
        raise ProofFailure(
            original_failure.failure_label,
            str(original_failure),
            details,
        ) from original_failure

    return {
        "chirp_create": chirp,
        "gh_errors": errors,
        "gh_undo": cleanup,
        "verification": verification,
    }


async def _run_slow_chirp_smoke_mutation(
    args: dict[str, int],
    *,
    provider: _SlowProvider,
    delay_seconds: float,
    dispatch_fn: Any,
    call_rhino_fn: Any,
) -> dict[str, Any]:
    started = time.monotonic()

    async def verify_created(component_guid: str, chirp: dict[str, Any]) -> dict[str, Any]:
        data = chirp.get("data")
        if not isinstance(data, dict):
            raise ProofFailure(
                "chirp_create_failed",
                "slow Chirp creation data was malformed",
                {"chirp_create": chirp},
            )
        if data.get("verification_deferred") is not True:
            raise ProofFailure(
                "chirp_verification_failed",
                "slow Chirp creation did not defer inference verification",
                {"chirp_create": chirp},
            )
        if data.get("solve_scheduled") is not True:
            raise ProofFailure(
                "chirp_verification_failed",
                "slow Chirp creation did not schedule a solve",
                {"chirp_create": chirp},
            )
        if "component_errors" in data:
            raise ProofFailure(
                "chirp_component_error",
                "slow Chirp creation reported component errors",
                {"chirp_create": chirp},
            )

        while True:
            inspected = await dispatch_fn(
                "gh_inspect_output",
                {**args, "guid": component_guid, "param": "Result"},
            )
            if not isinstance(inspected, dict) or inspected.get("success") is not True:
                raise ProofFailure(
                    "chirp_verification_failed",
                    "gh_inspect_output failed during slow inference",
                    {"gh_inspect_output": inspected},
                )
            inspected_data = inspected.get("data")
            preview = inspected_data.get("preview") if isinstance(inspected_data, dict) else None
            if isinstance(preview, list) and any(str(value) == "slow-ok" for value in preview):
                return {"output": "slow-ok", "gh_inspect_output": inspected}
            await asyncio.sleep(0.25)

    mutation = await _run_chirp_smoke_mutation(
        args,
        component_name="Rook Slow Inference Acceptance",
        dispatch_fn=dispatch_fn,
        call_rhino_fn=call_rhino_fn,
        create_arguments={
            "category": "classifier",
            "name": "Rook Slow Inference Acceptance",
            "pins_in": [{"name": "Input", "type": "string", "optional": True}],
            "pins_out": [{"name": "Result", "type": "string"}],
            "signature": "input -> result",
            "x": 320,
            "y": 40,
        },
        verify_created_fn=verify_created,
    )
    elapsed = time.monotonic() - started
    if elapsed < delay_seconds:
        raise ProofFailure(
            "chirp_slow_response_too_fast",
            "slow inference completed before the provider delay elapsed",
            {"elapsed_seconds": elapsed, "provider_delay_seconds": delay_seconds},
        )
    if provider.request_count != 1 or not provider.request_path.is_file():
        raise ProofFailure(
            "chirp_provider_receipt_failed",
            "slow provider did not record exactly one request",
            {
                "request_count": provider.request_count,
                "request_path": str(provider.request_path),
            },
        )

    active_evidence = json.dumps(
        {
            "chirp_create": mutation["chirp_create"],
            "verification": mutation["verification"],
            "gh_errors": mutation["gh_errors"],
        },
        sort_keys=True,
    )
    forbidden = [
        token
        for token in (
            "chirp_inference_timeout",
            "chirp_transport_timeout",
            "component_errors",
        )
        if token in active_evidence
    ]
    if forbidden:
        raise ProofFailure(
            "chirp_slow_inference_failed",
            "slow inference evidence contained a failure vocabulary",
            {"forbidden": forbidden},
        )

    return {
        "output": mutation["verification"]["output"],
        "elapsed_seconds": elapsed,
        "provider": {
            "host": provider.host,
            "port": provider.port,
            "request_count": provider.request_count,
            "request_path": str(provider.request_path),
        },
        "chirp_create": mutation["chirp_create"],
        "gh_errors": mutation["gh_errors"],
        "cleanup": mutation["gh_undo"],
    }


async def run_live_smoke(
    *,
    port: int | None = None,
    process_id: int | None = None,
    slow_provider_delay_seconds: float | None = None,
    artifact_dir: Path | None = None,
) -> dict[str, Any]:
    args: dict[str, int] = {}
    if port:
        args["port"] = port
    if process_id:
        args["process_id"] = process_id

    profile_was_set = "ROOK_MCP_TOOL_PROFILE" in os.environ
    inherited_profile = os.environ.get("ROOK_MCP_TOOL_PROFILE")
    os.environ["ROOK_MCP_TOOL_PROFILE"] = "lean"
    try:
        if slow_provider_delay_seconds is not None and artifact_dir is None:
            raise ProofFailure(
                "slow_provider_artifact_missing",
                "slow inference acceptance requires the owned harness artifact directory",
            )
        provider_context = (
            _slow_openai_provider(
                Path(artifact_dir), delay_seconds=slow_provider_delay_seconds
            )
            if slow_provider_delay_seconds is not None
            else nullcontext(None)
        )
        with provider_context as provider:
            environment = (
                {
                    "CHIRP_MODEL": "openai/rook-timeout-acceptance",
                    "CHIRP_PROVIDERS": json.dumps(
                        {
                            "openai/rook-timeout-acceptance": {
                                "api_base": f"http://{provider.host}:{provider.port}/v1",
                                "api_key_env": "CHIRP_TIMEOUT_ACCEPTANCE_API_KEY",
                            }
                        },
                        separators=(",", ":"),
                    ),
                    "CHIRP_TIMEOUT_ACCEPTANCE_API_KEY": "loopback-only",
                    "CHIRP_INFERENCE_TIMEOUT_SECONDS": "300",
                }
                if provider is not None
                else {}
            )
            result: dict[str, Any] | None = None
            body_failure: BaseException | None = None
            body_traceback = None
            sidecar_cleanup: dict[str, Any] | None = None
            sidecar_cleanup_failure: BaseException | None = None
            with _restoring_environment(environment):
                try:
                    with rhino_request_context(port=port, process_id=process_id):
                        ping = await _call_tool_dispatch("rhino_ping", dict(args))
                        if not ping.get("success"):
                            raise ProofFailure(
                                "rhino_ping_failed",
                                "rhino_ping failed",
                                {"rhino_ping": ping},
                            )

                        gh_ready = await _ensure_grasshopper_ready(args)
                        status = gh_ready["status"]
                        progressive_discovery = await _run_live_progressive_gh_status(args)
                        mutation = await _run_chirp_smoke_mutation(
                            args,
                            component_name="Rook Release Readiness Smoke",
                            dispatch_fn=_call_tool_dispatch,
                            call_rhino_fn=call_rhino,
                        )
                        slow_inference = (
                            await _run_slow_chirp_smoke_mutation(
                                args,
                                provider=provider,
                                delay_seconds=slow_provider_delay_seconds,
                                dispatch_fn=_call_tool_dispatch,
                                call_rhino_fn=call_rhino,
                            )
                            if provider is not None
                            and slow_provider_delay_seconds is not None
                            else None
                        )
                    result = {
                        "rhino_ping": ping,
                        "grasshopper_ready": gh_ready,
                        "gh_status": status,
                        "progressive_discovery": progressive_discovery,
                        "chirp_create": mutation["chirp_create"],
                        "gh_errors": mutation["gh_errors"],
                        "gh_undo": mutation["gh_undo"],
                    }
                    if slow_inference is not None:
                        result["slow_inference"] = slow_inference
                except BaseException as exc:
                    body_failure = exc
                    body_traceback = exc.__traceback__

                if provider is not None:
                    try:
                        sidecar_cleanup = _stop_owned_chirp_sidecar()
                    except BaseException as exc:
                        sidecar_cleanup_failure = exc

            if body_failure is not None and sidecar_cleanup_failure is not None:
                raise ProofFailure(
                    "chirp_sidecar_cleanup_failed",
                    "live smoke body and Chirp sidecar cleanup both failed",
                    {
                        "body_failure": _exception_payload(body_failure),
                        "cleanup_failure": _exception_payload(sidecar_cleanup_failure),
                    },
                ) from body_failure
            if sidecar_cleanup_failure is not None:
                raise sidecar_cleanup_failure
            if body_failure is not None:
                raise body_failure.with_traceback(body_traceback)
            if result is None:
                raise ProofFailure("installed_runtime_failed", "live smoke produced no result")
            if sidecar_cleanup is not None:
                result["slow_inference"]["sidecar_cleanup"] = sidecar_cleanup
            return result
    finally:
        if profile_was_set:
            os.environ["ROOK_MCP_TOOL_PROFILE"] = inherited_profile or ""
        else:
            os.environ.pop("ROOK_MCP_TOOL_PROFILE", None)


def live_smoke_gate(
    command: list[str],
    *,
    port: int | None,
    process_id: int | None,
) -> GateResult:
    started = time.monotonic()
    try:
        raw_artifact_dir = os.environ.get("ROOK_HARNESS_ARTIFACT_DIR")
        if not raw_artifact_dir:
            raise ProofFailure(
                "slow_provider_artifact_missing",
                "ROOK_HARNESS_ARTIFACT_DIR is required for installed live acceptance",
            )
        details = asyncio.run(
            run_live_smoke(
                port=port,
                process_id=process_id,
                slow_provider_delay_seconds=_CHIRP_ACCEPTANCE_PROVIDER_DELAY_SECONDS,
                artifact_dir=Path(raw_artifact_dir),
            )
        )
        return GateResult.passed(
            gate="live_smoke",
            command=command,
            started_at=started,
            ended_at=time.monotonic(),
            details=details,
        )
    except ProofFailure as exc:
        return GateResult.failure(
            gate="live_smoke",
            failure_label=exc.failure_label,
            command=command,
            started_at=started,
            ended_at=time.monotonic(),
            details=exc.details,
        )


def _cleanup_payload(status_value: str) -> dict[str, Any]:
    return {
        "attempted": status_value != CleanupStatus.NOT_ATTEMPTED.value,
        "success": status_value == CleanupStatus.GRACEFUL_EXIT.value,
        "label": None if status_value == CleanupStatus.GRACEFUL_EXIT.value else "cleanup_failed",
        "details": {"status": status_value},
    }


def _failure_label_from_smoke_output(output: str) -> str | None:
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        label = payload.get("failure_label")
        if isinstance(label, str) and label:
            return label
    return None


def _live_smoke_envelope(output: str) -> dict[str, Any] | None:
    for line in reversed(output.splitlines()):
        try:
            payload = json.loads(line.strip())
        except (json.JSONDecodeError, AttributeError):
            continue
        if isinstance(payload, dict) and payload.get("gate") == "live_smoke":
            return payload
    return None


def _harness_failure_label(harness_result: Any) -> str:
    if harness_result.cleanup_status != CleanupStatus.GRACEFUL_EXIT:
        return "cleanup_failed"
    if harness_result.smoke and harness_result.smoke.returncode != 0:
        stdout_label = _failure_label_from_smoke_output(harness_result.smoke.stdout or "")
        if stdout_label:
            return stdout_label
        stderr = harness_result.smoke.stderr or ""
        for label in (
            "rhino_ping_failed",
            "gh_not_ready",
            "chirp_import_failed",
            "chirp_create_failed",
            "chirp_component_warning",
            "chirp_component_error",
            "gh_component_error",
            "cleanup_failed",
        ):
            if label in stderr:
                return label
        return "installed_runtime_failed"
    if harness_result.pid <= 0:
        return "rhino_launch_failed"
    if harness_result.port <= 0:
        return "owned_discovery_timeout"
    return "installed_runtime_failed"


def owned_release_readiness_gate(
    *,
    command: list[str],
    rhino_exe: Path,
    artifact_root: Path,
    keep_rhino_on_failure: bool,
    readiness_timeout_seconds: float,
    cleanup_timeout_seconds: float,
) -> GateResult:
    started = time.monotonic()
    harness = run_rhino_runtime_harness(
        rhino_exe=rhino_exe,
        artifact_root=artifact_root,
        smoke_command=[sys.executable, "-m", "rook.local_testing_proof", "live-smoke"],
        smoke_kind="installed-live-smoke",
        smoke_cwd=None,
        readiness_timeout_seconds=readiness_timeout_seconds,
        smoke_timeout_seconds=_CHIRP_ACCEPTANCE_WATCHDOG_SECONDS,
        cleanup_timeout_seconds=cleanup_timeout_seconds,
        keep_rhino_on_failure=keep_rhino_on_failure,
    )
    cleanup = _cleanup_payload(harness.cleanup_status.value)
    details = harness.to_manifest_dict()
    smoke = getattr(harness, "smoke", None)
    envelope = _live_smoke_envelope(getattr(smoke, "stdout", "") or "")
    envelope_details = envelope.get("details") if isinstance(envelope, dict) else None
    progressive_discovery = (
        envelope_details.get("progressive_discovery")
        if isinstance(envelope_details, dict)
        else None
    )
    if isinstance(progressive_discovery, dict):
        details["progressive_discovery"] = progressive_discovery
    if harness.success:
        if not isinstance(progressive_discovery, dict):
            return GateResult.failure(
                gate="owned_release_readiness",
                failure_label="progressive_discovery_failed",
                command=command,
                started_at=started,
                ended_at=time.monotonic(),
                details=details,
                cleanup=cleanup,
            )
        return GateResult.passed(
            gate="owned_release_readiness",
            command=command,
            started_at=started,
            ended_at=time.monotonic(),
            details=details,
            cleanup=cleanup,
        )
    return GateResult.failure(
        gate="owned_release_readiness",
        failure_label=_harness_failure_label(harness),
        command=command,
        started_at=started,
        ended_at=time.monotonic(),
        details=details,
        cleanup=cleanup,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Installed-runtime Rook local testing proof gates.")
    sub = parser.add_subparsers(dest="command", required=True)

    installed = sub.add_parser("installed-runtime")
    installed.add_argument("--out", type=Path)

    python_evidence = sub.add_parser("python-smoke-evidence")
    python_evidence.add_argument("--out", type=Path)

    live = sub.add_parser("live-smoke")
    live.add_argument("--out", type=Path)
    live.add_argument("--port", type=int, default=int(os.environ.get("ROOK_RHINO_PORT", "0") or "0"))
    live.add_argument(
        "--process-id",
        type=int,
        default=int(os.environ.get("ROOK_RHINO_PROCESS_ID", "0") or "0"),
    )

    owned = sub.add_parser("owned-release-readiness")
    owned.add_argument("--out", type=Path)
    owned.add_argument(
        "--rhino-exe",
        type=Path,
        default=Path(r"C:\Program Files\Rhino 8\System\Rhino.exe"),
    )
    owned.add_argument("--artifact-root", type=Path, required=True)
    owned.add_argument("--readiness-timeout", type=float, default=60.0)
    owned.add_argument("--cleanup-timeout", type=float, default=15.0)
    owned.add_argument("--keep-rhino-on-failure", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    command = [sys.executable, "-m", "rook.local_testing_proof", *argv]
    if args.command == "installed-runtime":
        result = verify_installed_runtime(command)
    elif args.command == "python-smoke-evidence":
        result = python_smoke_evidence_gate(command)
    elif args.command == "live-smoke":
        result = live_smoke_gate(command, port=args.port or None, process_id=args.process_id or None)
    elif args.command == "owned-release-readiness":
        result = owned_release_readiness_gate(
            command=command,
            rhino_exe=args.rhino_exe,
            artifact_root=args.artifact_root,
            keep_rhino_on_failure=args.keep_rhino_on_failure,
            readiness_timeout_seconds=args.readiness_timeout,
            cleanup_timeout_seconds=args.cleanup_timeout,
        )
    else:
        raise AssertionError(args.command)

    payload = result.to_dict()
    if getattr(args, "out", None):
        write_json(args.out, payload)
    print(json.dumps(payload, sort_keys=True))
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
