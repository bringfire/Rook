from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


SAFE_ENV_NAMES = ("SystemRoot", "windir", "TEMP", "TMP")


@dataclass(frozen=True)
class Mesh2SplatProcessResult:
    success: bool
    returncode: int | None
    stdout: str
    stderr: str
    parsed_stdout: dict[str, object] | None = None
    error_code: str | None = None
    diagnostics: dict[str, object] = field(default_factory=dict)


class Mesh2SplatProcessError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        diagnostics: dict[str, object] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.diagnostics = diagnostics or {}
        self.envelope: dict[str, object] = {
            "success": False,
            "data": {
                "code": code,
                "message": message,
                "retryable": False,
                "diagnostics": self.diagnostics,
            },
        }


def validate_working_directory(value: str | None, executable_path: Path) -> Path:
    if value is None:
        return executable_path.parent.resolve(strict=True)

    working_directory = Path(value).expanduser()
    if not working_directory.is_absolute():
        _raise_invalid_working_directory(value)

    try:
        resolved = working_directory.resolve(strict=True)
    except (OSError, RuntimeError):
        _raise_invalid_working_directory(value)

    if not resolved.is_dir():
        _raise_invalid_working_directory(value)
    return resolved


def sanitized_child_environment(
    *, source_requires_path: bool, parent_env: Mapping[str, str]
) -> dict[str, str]:
    allowed = {name: parent_env[name] for name in SAFE_ENV_NAMES if name in parent_env}
    if source_requires_path and "PATH" in parent_env:
        allowed["PATH"] = parent_env["PATH"]
    return allowed


def run_mesh2splat(
    argv: list[str], *, cwd: Path, env: dict[str, str], timeout_seconds: int
) -> Mesh2SplatProcessResult:
    process = subprocess.Popen(
        list(argv),
        cwd=str(cwd),
        env=dict(env),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
    )
    diagnostics: dict[str, object] = {}
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        diagnostics["processTreeTermination"] = _terminate_process_tree(process)
        stdout, stderr = _collect_after_timeout(process)
        return Mesh2SplatProcessResult(
            success=False,
            returncode=getattr(process, "returncode", None),
            stdout=stdout,
            stderr=stderr,
            parsed_stdout=parse_last_stdout_json(stdout),
            error_code="mesh2splat_timeout",
            diagnostics=diagnostics,
        )

    parsed = parse_last_stdout_json(stdout)
    error_code = _map_process_error(process.returncode, parsed)
    return Mesh2SplatProcessResult(
        success=error_code is None,
        returncode=process.returncode,
        stdout=stdout,
        stderr=stderr,
        parsed_stdout=parsed,
        error_code=error_code,
        diagnostics=diagnostics,
    )


def parse_last_stdout_json(stdout: str) -> dict[str, object] | None:
    for line in reversed(stdout.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _raise_invalid_working_directory(path: str) -> None:
    raise Mesh2SplatProcessError(
        "invalid_working_directory",
        "mesh2splatWorkingDirectory must resolve to an existing directory",
        diagnostics={"path": path},
    )


def _terminate_process_tree(process: subprocess.Popen[str]) -> str:
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                return "windows_taskkill_tree"
        except (OSError, subprocess.SubprocessError):
            pass

    try:
        process.terminate()
    except OSError:
        pass
    return "direct_child_only"


def _collect_after_timeout(process: subprocess.Popen[str]) -> tuple[str, str]:
    try:
        return process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except OSError:
            pass
        try:
            return process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            return "", ""


def _map_process_error(
    returncode: int | None, parsed_stdout: dict[str, object] | None
) -> str | None:
    cli_code = _cli_error_code(parsed_stdout)
    if returncode == 4 or cli_code == "GLB_PARSE_FAILED":
        return "mesh2splat_glb_parse_failed"
    if cli_code == "CAPACITY_EXCEEDED":
        return "mesh2splat_capacity_exceeded"
    if cli_code == "GL_CONTEXT_INIT_FAILED":
        return "mesh2splat_gl_context_init_failed"
    if _cli_reported_failure(parsed_stdout):
        return "mesh2splat_failed"
    if returncode not in (0, None):
        return "mesh2splat_failed"
    return None


def _cli_reported_failure(parsed_stdout: dict[str, object] | None) -> bool:
    return bool(parsed_stdout and parsed_stdout.get("ok") is False)


def _cli_error_code(parsed_stdout: dict[str, object] | None) -> str | None:
    if not parsed_stdout:
        return None

    code = parsed_stdout.get("code") or parsed_stdout.get("errorCode")
    if isinstance(code, str):
        return code

    nested_error = parsed_stdout.get("error")
    if isinstance(nested_error, dict):
        nested_code = nested_error.get("code") or nested_error.get("errorCode")
        if isinstance(nested_code, str):
            return nested_code
    return None
