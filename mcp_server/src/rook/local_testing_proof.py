from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .bridge import rhino_request_context
from .runtime_harness import CleanupStatus, run_rhino_runtime_harness
from .runtime_paths import resolve_runtime_paths


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
        "print(json.dumps({'chirp_file': chirp.__file__}, sort_keys=True))"
    )
    completed = subprocess.run(
        [str(chirp_python), "-c", check],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
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
    assert_path_under(chirp_file, chirp_root, "chirp_import_leakage")
    return {
        "chirp_file": str(chirp_file),
        "chirp_root": str(chirp_root),
        "chirp_python": str(chirp_python),
    }


def _read_json(path: Path, missing_label: str = "mcp_config_missing") -> dict[str, Any]:
    if not path.exists():
        raise ProofFailure(missing_label, f"JSON file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
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
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
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
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProofFailure(
            "chat_manifest_stale",
            f"chat service manifest is malformed: {manifest_path}",
        ) from exc

    expected_working_dir = install_root / "mcp_server"
    expected_src = expected_working_dir / "src"
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
    if not entries or not _path_equal(entries[0], expected_src):
        raise ProofFailure(
            "chat_manifest_stale",
            "chat service pythonPathEntries mismatch",
            {"pythonPathEntries": entries},
        )
    return {"manifest_path": str(manifest_path), "working_directory": str(expected_working_dir)}


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

    for config_path in (
        home / ".claude.json",
        appdata / "Claude" / "claude_desktop_config.json",
    ):
        if config_path.exists():
            checked[str(config_path)] = verify_json_mcp_config(
                config_path=config_path,
                venv_python=venv_python,
                install_root=paths.install_root,
                data_root=paths.data_root,
                chirp_home=chirp_home,
            )

    codex_config = home / ".codex" / "config.toml"
    if codex_config.exists():
        checked[str(codex_config)] = verify_codex_mcp_config(
            config_path=codex_config,
            venv_python=venv_python,
            install_root=paths.install_root,
            data_root=paths.data_root,
            chirp_home=chirp_home,
        )

    if not checked:
        raise ProofFailure("mcp_config_missing", "no MCP config files were found to verify")

    return {
        "mcp_configs": checked,
        "chat_manifest": verify_chat_manifest(
            plugin_dir=plugin_dir,
            venv_python=venv_python,
            install_root=paths.install_root,
        ),
    }


def verify_installed_runtime(command: list[str]) -> GateResult:
    started = time.monotonic()
    try:
        import rook

        paths = resolve_runtime_paths()
        install_root = paths.install_root
        data_root = paths.data_root
        expected_rook_root = install_root / "mcp_server" / "src" / "rook"
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

        chirp_details = verify_chirp_runtime(expected_chirp_root)
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
                "install_root": str(install_root),
                "data_root": str(data_root),
                **chirp_details,
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


async def _call_tool_dispatch(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    from .server import _call_tool_dispatch as dispatch

    return await dispatch(name, arguments)


async def run_live_smoke(
    *,
    port: int | None = None,
    process_id: int | None = None,
) -> dict[str, Any]:
    args: dict[str, int] = {}
    if port:
        args["port"] = port
    if process_id:
        args["process_id"] = process_id

    with rhino_request_context(port=port, process_id=process_id):
        ping = await _call_tool_dispatch("rhino_ping", dict(args))
        if not ping.get("success"):
            raise ProofFailure("rhino_ping_failed", "rhino_ping failed", {"rhino_ping": ping})

        status = await _call_tool_dispatch("gh_status", dict(args))
        if not status.get("success"):
            raise ProofFailure("gh_not_ready", "gh_status failed", {"gh_status": status})

        chirp = await _call_tool_dispatch(
            "chirp_create",
            {
                **args,
                "category": "classifier",
                "name": "Rook Release Readiness Smoke",
                "pins_in": [{"name": "Input", "type": "string", "optional": True}],
                "pins_out": [{"name": "Result", "type": "string"}],
                "signature": "input -> result",
                "deterministic_code": "Result = Input ?? string.Empty;",
                "x": 40,
                "y": 40,
            },
        )
        if not chirp.get("success"):
            raise ProofFailure(
                "chirp_create_failed",
                "chirp_create failed",
                {"chirp_create": chirp},
            )
        chirp_data = chirp.get("data") or {}
        if chirp_data.get("warning"):
            raise ProofFailure(
                "chirp_component_warning",
                "chirp_create warning",
                {"chirp_create": chirp},
            )
        if chirp_data.get("compilation_errors"):
            raise ProofFailure(
                "chirp_component_compile_error",
                "chirp_create compilation errors",
                {"chirp_create": chirp},
            )

        component_guid = chirp_data.get("component_guid")
        if not component_guid:
            raise ProofFailure(
                "chirp_create_failed",
                "chirp_create did not return component_guid",
                {"chirp_create": chirp},
            )

        errors = await _call_tool_dispatch("gh_errors", dict(args))
        if not errors.get("success"):
            raise ProofFailure(
                "gh_component_error",
                "gh_errors failed",
                {"gh_errors": errors},
            )
        for item in (errors.get("data") or {}).get("errors", []):
            if item.get("guid") == component_guid and item.get("errors"):
                raise ProofFailure(
                    "gh_component_error",
                    "created component has GH errors",
                    {"gh_errors": errors},
                )

        undo = await _call_tool_dispatch("gh_undo", dict(args))
        if not undo.get("success"):
            raise ProofFailure("cleanup_failed", "gh_undo failed", {"gh_undo": undo})

    return {
        "rhino_ping": ping,
        "gh_status": status,
        "chirp_create": chirp,
        "gh_errors": errors,
        "gh_undo": undo,
    }


def live_smoke_gate(
    command: list[str],
    *,
    port: int | None,
    process_id: int | None,
) -> GateResult:
    started = time.monotonic()
    try:
        details = asyncio.run(run_live_smoke(port=port, process_id=process_id))
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


def _harness_failure_label(harness_result: Any) -> str:
    if harness_result.cleanup_status != CleanupStatus.GRACEFUL_EXIT:
        return "cleanup_failed"
    if harness_result.smoke and harness_result.smoke.returncode != 0:
        stderr = harness_result.smoke.stderr or ""
        for label in (
            "rhino_ping_failed",
            "gh_not_ready",
            "chirp_import_failed",
            "chirp_create_failed",
            "chirp_component_warning",
            "chirp_component_compile_error",
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
        cleanup_timeout_seconds=cleanup_timeout_seconds,
        keep_rhino_on_failure=keep_rhino_on_failure,
    )
    cleanup = _cleanup_payload(harness.cleanup_status.value)
    details = harness.to_manifest_dict()
    if harness.success:
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
