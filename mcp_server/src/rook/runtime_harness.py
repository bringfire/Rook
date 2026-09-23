from __future__ import annotations

import asyncio
import ctypes
from ctypes import wintypes
import inspect
import json
import os
import signal
import shutil
import subprocess
import time
import tempfile
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import httpx
from .bridge import NATIVE_CLIENT_HEADERS

from .bridge import resolve_discovery_folder
from .rhino_launch import (  # noqa: F401  canonical home is rhino_launch; re-exported for back-compat
    DiscoveryError,
    DiscoveryFailureReason,
    LaunchExecError,
    OwnedRhinoDiscovery,
    OwnedRhinoRecord,
    PingFunction,
    _run_awaitable_sync,
    _windows_user32,
    build_launch_env,
    default_discovery_dir,
    describe_windows_for_pid,
    exec_failure_outcome,
    ping_native,
    resolve_requested_scheme,
    start_rhino_process,
    wait_for_rook_readiness,
)


def default_temp_rook_dir() -> Path:
    return default_discovery_dir()


@dataclass(frozen=True)
class ArtifactRoot:
    label: str
    path: Path


def default_artifact_roots() -> list[ArtifactRoot]:
    primary, _, diagnostics = resolve_discovery_folder(temp_root=Path(tempfile.gettempdir()))
    roots = [ArtifactRoot("shared-discovery", primary)]
    legacy = Path(str(diagnostics["legacyTempDiscoveryFolder"]))
    if legacy != primary:
        roots.append(ArtifactRoot("legacy-temp-rook", legacy))
    return roots


DEFAULT_DISCOVERY_DIR = default_discovery_dir()
HARNESS_ENV_KEYS = (
    "ROOK_RHINO_PORT",
    "ROOK_RHINO_PROCESS_ID",
    "NATIVE_PORT",
    "ROOK_HARNESS_ARTIFACT_DIR",
)
RUNSCRIPT_SAFETY_UNRECOVERED_SENTINEL = "runscript_safety_unrecovered.json"
FINAL_SMOKE_DRAIN_TIMEOUT_SECONDS = 1.0
WM_CLOSE = 0x0010


class CleanupStatus(Enum):
    NOT_ATTEMPTED = "not_attempted"
    GRACEFUL_EXIT = "graceful_exit"
    GRACEFUL_EXIT_DISCOVERY_LEFTOVER = "graceful_exit_discovery_leftover"
    GRACEFUL_TIMEOUT_FORCED_KILL = "graceful_timeout_forced_kill"
    ALREADY_EXITED_BEFORE_CLEANUP = "already_exited_before_cleanup"
    FORCE_KILL_FAILED = "force_kill_failed"


class HarnessStatus(Enum):
    SUCCESS = "success"
    NON_GREEN = "non_green"


@dataclass(frozen=True)
class SmokeCommandResult:
    command: list[str]
    scoped_env: dict[str, str]
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    timeout_seconds: float | None = None

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def to_manifest_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "scoped_env": self.scoped_env,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_seconds": self.duration_seconds,
            "timed_out": self.timed_out,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True)
class RhinoHarnessResult:
    run_id: str
    artifact_dir: Path
    pid: int
    port: int
    ready_record_path: Path | None = None
    smoke: SmokeCommandResult | None = None
    cleanup_status: CleanupStatus = CleanupStatus.NOT_ATTEMPTED
    runscript_safety_unrecovered_path: Path | None = None
    run_started_at: float = field(default_factory=time.time)
    warnings: list[str] = field(default_factory=list)
    launch_outcome: dict[str, Any] | None = None

    @property
    def success(self) -> bool:
        return (
            self.smoke is not None
            and self.smoke.succeeded
            and self.cleanup_status == CleanupStatus.GRACEFUL_EXIT
            and self.runscript_safety_unrecovered_path is None
        )

    @property
    def status(self) -> HarnessStatus:
        if self.success:
            return HarnessStatus.SUCCESS
        return HarnessStatus.NON_GREEN

    def to_manifest_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "artifact_dir": str(self.artifact_dir),
            "pid": self.pid,
            "port": self.port,
            "ready": {
                "record_snapshot_path": str(self.ready_record_path) if self.ready_record_path else None,
                "record_available": self.ready_record_path is not None,
            },
            "smoke": self.smoke.to_manifest_dict() if self.smoke else None,
            "cleanup": {
                "status": self.cleanup_status.value,
                "path": self.cleanup_status.value,
            },
            "runscript_safety": {
                "unrecovered": self.runscript_safety_unrecovered_path is not None,
                "sentinel_path": (
                    str(self.runscript_safety_unrecovered_path)
                    if self.runscript_safety_unrecovered_path
                    else None
                ),
            },
            "warnings": self.warnings,
            "launch_outcome": self.launch_outcome,
            "status": self.status.value,
            "success": self.success,
        }

    def write_manifest(self) -> Path:
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = self.artifact_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(self.to_manifest_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return manifest_path


def _scoped_env_subset(env_additions: dict[str, str]) -> dict[str, str]:
    return {key: str(env_additions[key]) for key in HARNESS_ENV_KEYS if key in env_additions}


def _apply_env_overrides(
    base_env: Mapping[str, str],
    overrides: dict[str, str | None] | None,
) -> dict[str, str]:
    env = {str(key): str(value) for key, value in base_env.items()}
    if not overrides:
        return env
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = str(value)
    return env


def _runscript_safety_unrecovered_path(artifact_dir: Path) -> Path | None:
    sentinel_path = artifact_dir / RUNSCRIPT_SAFETY_UNRECOVERED_SENTINEL
    if sentinel_path.exists():
        return sentinel_path
    return None


def _decode_timeout_stream(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def _smoke_popen_kwargs() -> dict[str, Any]:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def close_windows_for_pid(pid: int) -> int:
    if os.name != "nt":
        return 0

    user32 = _windows_user32()
    posted_count = 0

    def enum_window(hwnd, lparam):
        nonlocal posted_count
        if not user32.IsWindowVisible(hwnd):
            return True

        window_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        if window_pid.value == pid and user32.PostMessageW(hwnd, WM_CLOSE, 0, 0):
            posted_count += 1
        return True

    enum_windows_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(enum_windows_proc(enum_window), 0)
    return posted_count


def request_external_graceful_close(
    process,
    timeout_seconds: float,
    close_windows_for_pid_fn: Callable[[int], int] = close_windows_for_pid,
    describe_windows_for_pid_fn: Callable[[int], list[dict[str, Any]]] = describe_windows_for_pid,
    diagnostics: list[str] | None = None,
) -> bool:
    windows_before = describe_windows_for_pid_fn(process.pid)
    posted_count = close_windows_for_pid_fn(process.pid)
    try:
        process.wait(timeout=timeout_seconds)
        return False
    except Exception:
        if diagnostics is not None:
            diagnostics.append(
                f"cleanup WM_CLOSE posted to {posted_count} window(s) for pid {process.pid}; "
                f"windows before close: {windows_before}"
            )
            diagnostics.append(
                f"cleanup timed out after {timeout_seconds} seconds for pid {process.pid}; "
                f"windows after timeout: {describe_windows_for_pid_fn(process.pid)}"
            )
        process.kill()
        try:
            process.wait(timeout=1.0)
        except Exception:
            pass
        return True


def force_owned_process_cleanup(process, diagnostics: list[str]) -> bool:
    if process.poll() is not None:
        return True

    if os.name == "nt":
        try:
            taskkill_result = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/F"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            diagnostics.append(f"force cleanup taskkill failed for pid {process.pid}: {exc}")
            try:
                process.kill()
            except Exception as kill_exc:
                diagnostics.append(f"force cleanup process.kill failed for pid {process.pid}: {kill_exc}")
                return False
        else:
            if taskkill_result.returncode != 0:
                diagnostics.append(
                    "force cleanup taskkill returned "
                    f"{taskkill_result.returncode} for pid {process.pid}: "
                    f"{taskkill_result.stderr or taskkill_result.stdout}"
                )
                try:
                    process.kill()
                except Exception as kill_exc:
                    diagnostics.append(f"force cleanup process.kill failed for pid {process.pid}: {kill_exc}")
                    return False
    else:
        try:
            process.kill()
        except Exception as exc:
            diagnostics.append(f"force cleanup process.kill failed for pid {process.pid}: {exc}")
            return False

    try:
        process.wait(timeout=1.0)
    except Exception as exc:
        diagnostics.append(f"force cleanup wait failed for pid {process.pid}: {exc}")
        return False
    if process.poll() is None:
        diagnostics.append(f"force cleanup did not stop pid {process.pid}")
        return False
    return True


def _windows_kernel32() -> ctypes.WinDLL:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


def _create_windows_job_for_process(process: subprocess.Popen[str]) -> int | None:
    if os.name != "nt":
        return None

    kernel32 = _windows_kernel32()
    job_handle = kernel32.CreateJobObjectW(None, None)
    if not job_handle:
        return None

    if not kernel32.AssignProcessToJobObject(job_handle, int(process._handle)):
        kernel32.CloseHandle(job_handle)
        return None
    return int(job_handle)


def _close_windows_job(job_handle: int | None) -> None:
    if os.name != "nt" or job_handle is None:
        return
    _windows_kernel32().CloseHandle(job_handle)


def _terminate_smoke_process_tree(process: subprocess.Popen[str], job_handle: int | None) -> None:
    if os.name == "nt" and job_handle is not None:
        _windows_kernel32().TerminateJobObject(job_handle, 1)
        return

    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
        return

    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except OSError:
        process.kill()


def run_smoke_command(
    command: list[str],
    env_additions: dict[str, str],
    cwd: Path | None = None,
    timeout_seconds: float | None = None,
) -> SmokeCommandResult:
    start = time.monotonic()
    scoped_env = _scoped_env_subset(env_additions)
    env = os.environ.copy()
    env.update({key: str(value) for key, value in env_additions.items()})

    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **_smoke_popen_kwargs(),
    )
    job_handle = _create_windows_job_for_process(process)
    try:
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            _terminate_smoke_process_tree(process, job_handle)
            drain_error: subprocess.TimeoutExpired | None = None
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired as post_terminate_exc:
                drain_error = post_terminate_exc
                process.kill()
                try:
                    stdout, stderr = process.communicate(timeout=FINAL_SMOKE_DRAIN_TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired as final_drain_exc:
                    drain_error = final_drain_exc
                    stdout = final_drain_exc.stdout or post_terminate_exc.stdout or exc.stdout or ""
                    stderr = final_drain_exc.stderr or post_terminate_exc.stderr or exc.stderr or ""

            duration_seconds = time.monotonic() - start
            stdout = _decode_timeout_stream(stdout or exc.stdout)
            stderr = _decode_timeout_stream(stderr or exc.stderr)
            diagnostic = f"smoke command timed out after {timeout_seconds} seconds"
            if drain_error is not None:
                diagnostic = (
                    f"{diagnostic}; could not drain smoke command output after cleanup "
                    f"within {drain_error.timeout} seconds"
                )
            if stderr:
                stderr = f"{stderr}\n{diagnostic}"
            else:
                stderr = diagnostic
            return SmokeCommandResult(
                command=command,
                scoped_env=scoped_env,
                returncode=124,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=duration_seconds,
                timed_out=True,
                timeout_seconds=timeout_seconds,
            )
    finally:
        _close_windows_job(job_handle)

    duration_seconds = time.monotonic() - start
    return SmokeCommandResult(
        command=command,
        scoped_env=scoped_env,
        returncode=process.returncode if process.returncode is not None else 0,
        stdout=stdout,
        stderr=stderr,
        duration_seconds=duration_seconds,
        timeout_seconds=timeout_seconds,
    )


def run_ping_smoke(
    record: OwnedRhinoRecord,
    ping: PingFunction | None = None,
) -> SmokeCommandResult:
    start = time.monotonic()
    ping = ping or ping_native
    env = {
        "ROOK_RHINO_PORT": str(record.port),
        "ROOK_RHINO_PROCESS_ID": str(record.pid),
    }
    try:
        ping_result = ping(record.host, record.port)
        if inspect.isawaitable(ping_result):
            ping_result = _run_awaitable_sync(ping_result)
    except Exception as exc:
        return SmokeCommandResult(
            command=["ping-only"],
            scoped_env=_scoped_env_subset(env),
            returncode=1,
            stdout="",
            stderr=f"ping-only smoke failed: {exc}",
            duration_seconds=time.monotonic() - start,
        )

    return SmokeCommandResult(
        command=["ping-only"],
        scoped_env=_scoped_env_subset(env),
        returncode=0 if ping_result else 1,
        stdout="pong\n" if ping_result else "",
        stderr="" if ping_result else "ping-only smoke did not receive pong",
        duration_seconds=time.monotonic() - start,
    )


def save_owned_document_for_cleanup(
    record: OwnedRhinoRecord,
    artifact_dir: Path,
    warnings: list[str],
    timeout_seconds: float = 20.0,
) -> Path | None:
    cleanup_dir = artifact_dir / "cleanup"
    save_path = cleanup_dir / f"owned-rhino-{record.pid}-cleanup.3dm"
    try:
        cleanup_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        warnings.append(f"cleanup document save failed before request: {exc}")
        return None

    url = f"http://{record.host}:{record.port}/document/save"
    try:
        response = httpx.post(
            url,
            json={"path": str(save_path), "small": True},
            timeout=timeout_seconds, headers=NATIVE_CLIENT_HEADERS
        )
    except httpx.HTTPError as exc:
        warnings.append(f"cleanup document save failed: {exc}")
        return None

    if response.status_code >= 400:
        warnings.append(
            f"cleanup document save failed with HTTP {response.status_code}: {response.text}"
        )
        return None

    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict) and payload.get("success") is False:
        warnings.append(f"cleanup document save failed: {payload.get('error') or payload}")
        return None

    return save_path


def copy_temp_rook_artifacts(
    result: RhinoHarnessResult,
    temp_rook_dir: Path,
    label: str,
    mtime_slop_seconds: float = 0.0,
) -> list[Path]:
    if not temp_rook_dir.exists():
        result.warnings.append(f"temp Rook artifact directory is missing: {temp_rook_dir}")
        return []
    if not temp_rook_dir.is_dir():
        result.warnings.append(f"temp Rook artifact path is not a directory: {temp_rook_dir}")
        return []

    copied: list[Path] = []
    artifact_root = result.artifact_dir.resolve()
    destination_root = (artifact_root / label).resolve()
    if not destination_root.is_relative_to(artifact_root):
        result.warnings.append(
            f"unsafe temp Rook artifact label would copy outside artifact directory: {label}"
        )
        return []
    min_mtime = result.run_started_at - mtime_slop_seconds

    for source_path in sorted(temp_rook_dir.rglob("*")):
        if not source_path.is_file():
            continue
        try:
            if source_path.stat().st_mtime < min_mtime:
                continue
            relative_path = source_path.relative_to(temp_rook_dir)
            destination_path = (destination_root / relative_path).resolve()
            if not destination_path.is_relative_to(artifact_root):
                result.warnings.append(
                    f"unsafe temp Rook artifact destination would copy outside artifact directory: {destination_path}"
                )
                continue
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination_path)
        except OSError as exc:
            result.warnings.append(f"could not copy temp Rook artifact {source_path}: {exc}")
            continue
        copied.append(destination_path)

    return copied


def copy_rook_artifacts(
    result: RhinoHarnessResult,
    artifact_roots: list[ArtifactRoot],
    label: str,
    mtime_slop_seconds: float = 0.0,
) -> list[Path]:
    copied: list[Path] = []
    for root in artifact_roots:
        root_label = label if not root.label else f"{label}-{root.label}"
        if mtime_slop_seconds:
            copied.extend(
                copy_temp_rook_artifacts(
                    result,
                    root.path,
                    root_label,
                    mtime_slop_seconds=mtime_slop_seconds,
                )
            )
        else:
            copied.extend(copy_temp_rook_artifacts(result, root.path, root_label))
    return copied


def _new_run_id() -> str:
    return f"rhino-runtime-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


def run_rhino_runtime_harness(
    *,
    rhino_exe: Path,
    artifact_root: Path,
    smoke_command: list[str],
    smoke_kind: str = "pytest-select",
    smoke_cwd: Path | None = None,
    smoke_timeout_seconds: float | None = None,
    discovery: OwnedRhinoDiscovery | None = None,
    temp_rook_dir: Path | None = None,
    readiness_timeout_seconds: float = 30.0,
    readiness_poll_seconds: float = 0.25,
    cleanup_timeout_seconds: float = 10.0,
    keep_rhino_on_failure: bool = False,
    launch_env_overrides: dict[str, str | None] | None = None,
) -> RhinoHarnessResult:
    """Run one owned Rhino process through readiness, smoke, artifacts, and cleanup.

    The harness intentionally waits only for the discovery file matching the
    launched process id and cleans up only through that owned process object.
    """
    run_id = _new_run_id()
    artifact_dir = artifact_root / run_id
    run_started_at = time.time()
    warnings: list[str] = []
    artifact_roots = (
        [ArtifactRoot("", Path(temp_rook_dir))]
        if temp_rook_dir is not None
        else default_artifact_roots()
    )

    rhino_exe = Path(rhino_exe)
    artifact_root = Path(artifact_root)
    if not rhino_exe.exists():
        result = RhinoHarnessResult(
            run_id=run_id,
            artifact_dir=artifact_dir,
            pid=0,
            port=0,
            run_started_at=run_started_at,
            warnings=[f"Rhino executable not found: {rhino_exe}"],
        )
        result.write_manifest()
        return result

    discovery = discovery or OwnedRhinoDiscovery()
    requested_scheme = resolve_requested_scheme("RookHarness", os.environ, env_var="ROOK_HARNESS_SCHEME")
    launch_env_base = _apply_env_overrides(os.environ, launch_env_overrides)
    launch_env = build_launch_env(launch_env_base)
    try:
        started = start_rhino_process(
            rhino_exe,
            requested_scheme=requested_scheme,
            env=launch_env.env,
            launch_env_report=launch_env.report,
            # Launch via THIS module's subprocess.Popen so harness tests that patch
            # rook.runtime_harness.subprocess.Popen still intercept the owned-Rhino launch.
            # start_rhino_process still owns argv (/nosplash) + scheme; the primitive's own
            # popen-injection path is exercised directly in test_rhino_launch.
            # The explicit env is intentionally duplicated here and in start_rhino_process(env=...):
            # removing this lambda later must still preserve the controlled launch environment.
            popen=lambda argv: subprocess.Popen(argv, env=launch_env.env),
        )
    except LaunchExecError as exc:
        result = RhinoHarnessResult(
            run_id=run_id,
            artifact_dir=artifact_dir,
            pid=0,
            port=0,
            run_started_at=run_started_at,
            warnings=[f"Rhino launch failed: {exc}"],
            launch_outcome=exec_failure_outcome(exc).to_dict(),
        )
        copy_rook_artifacts(result, artifact_roots, "launch-failure")
        result.write_manifest()
        return result
    process = started.process
    pid = int(started.pid)
    port = 0
    before_shutdown_copied = False
    result = RhinoHarnessResult(
        run_id=run_id,
        artifact_dir=artifact_dir,
        pid=pid,
        port=port,
        run_started_at=run_started_at,
        warnings=warnings,
    )

    try:
        readiness = wait_for_rook_readiness(
            started,
            discovery=discovery,
            ping=ping_native,
            timeout_seconds=readiness_timeout_seconds,
            poll_seconds=readiness_poll_seconds,
        )
        result = replace(result, launch_outcome=readiness.outcome.to_dict())
        if not readiness.outcome.ok:
            # Preserve the original warning text (full DiscoveryError message); the structured
            # reason/evidence ride in result.launch_outcome.
            warnings.append(f"Rhino readiness failed: {readiness.outcome.message}")
            copy_rook_artifacts(result, artifact_roots, "readiness-failure")
        else:
            record = readiness.record
            try:
                confirmed_record = discovery.read_owned_record(pid)
            except DiscoveryError as exc:
                warnings.append(f"Rhino discovery changed after ping: {exc}")
                copy_rook_artifacts(result, artifact_roots, "readiness-failure")
                confirmed_record = None
            else:
                if confirmed_record.port != record.port or confirmed_record.pid != record.pid:
                    warnings.append(
                        "Rhino discovery changed after ping: "
                        f"was pid {record.pid} port {record.port}, "
                        f"now pid {confirmed_record.pid} port {confirmed_record.port}"
                    )
                    copy_rook_artifacts(result, artifact_roots, "readiness-failure")
                    confirmed_record = None
            if confirmed_record is not None:
                record = confirmed_record
                port = record.port
                ready_record_path = discovery.snapshot_owned_record(record, artifact_dir)
                result = replace(result, port=port, ready_record_path=ready_record_path)
                smoke_env = {
                    "ROOK_RHINO_PORT": str(record.port),
                    "ROOK_RHINO_PROCESS_ID": str(record.pid),
                    "ROOK_HARNESS_ARTIFACT_DIR": str(artifact_dir),
                }
                if smoke_kind == "rhino-operational":
                    smoke_env["NATIVE_PORT"] = str(record.port)
                try:
                    if smoke_kind == "ping-only":
                        smoke = run_ping_smoke(record, ping_native)
                    else:
                        smoke = run_smoke_command(
                            smoke_command,
                            smoke_env,
                            cwd=smoke_cwd,
                            timeout_seconds=smoke_timeout_seconds,
                        )
                except Exception as exc:
                    warnings.append(f"Rhino smoke command failed before result: {exc}")
                    unrecovered_path = _runscript_safety_unrecovered_path(artifact_dir)
                    if unrecovered_path is not None:
                        warnings.append(
                            f"RunScript safety unrecovered sentinel observed: {unrecovered_path}"
                        )
                        result = replace(
                            result,
                            runscript_safety_unrecovered_path=unrecovered_path,
                        )
                    copy_rook_artifacts(result, artifact_roots, "smoke-failure")
                else:
                    result = replace(result, smoke=smoke)
                    unrecovered_path = _runscript_safety_unrecovered_path(artifact_dir)
                    if unrecovered_path is not None:
                        warnings.append(
                            f"RunScript safety unrecovered sentinel observed: {unrecovered_path}"
                        )
                        result = replace(
                            result,
                            runscript_safety_unrecovered_path=unrecovered_path,
                        )
                    elif smoke_kind != "ping-only":
                        save_owned_document_for_cleanup(record, artifact_dir, warnings)
                    copy_rook_artifacts(result, artifact_roots, "before-shutdown")
                    before_shutdown_copied = True
                    if not smoke.succeeded:
                        warnings.append(f"Rhino smoke command failed with exit code {smoke.returncode}")
                        copy_rook_artifacts(result, artifact_roots, "smoke-failure")
    finally:
        if not before_shutdown_copied:
            copy_rook_artifacts(result, artifact_roots, "before-shutdown")
        already_exited_before_cleanup = process.poll() is not None
        should_keep_on_failure = (
            keep_rhino_on_failure
            and not already_exited_before_cleanup
            and result.smoke is not None
            and not result.smoke.succeeded
            and result.runscript_safety_unrecovered_path is None
        )
        forced = False
        force_failed = False
        if should_keep_on_failure:
            warnings.append(
                f"KeepRhinoOnFailure requested; leaving owned Rhino pid {pid} running for diagnostics"
            )
        elif not already_exited_before_cleanup:
            if result.runscript_safety_unrecovered_path is not None:
                forced = True
                try:
                    force_failed = not force_owned_process_cleanup(process, warnings)
                except Exception as exc:
                    warnings.append(f"Rhino force cleanup failed: {exc}")
                    force_failed = True
            else:
                try:
                    forced = request_external_graceful_close(
                        process,
                        cleanup_timeout_seconds,
                        diagnostics=warnings,
                    )
                except Exception as exc:
                    warnings.append(f"Rhino cleanup failed: {exc}")
                    force_failed = True
        process_exited_after_cleanup = process.poll() is not None
        if should_keep_on_failure:
            cleanup_status = CleanupStatus.NOT_ATTEMPTED
        else:
            discovery_leftover = discovery.owned_path(pid).exists()
            cleanup_status = classify_cleanup_status(
                already_exited_before_cleanup=already_exited_before_cleanup,
                process_exited_after_cleanup=process_exited_after_cleanup,
                discovery_leftover=discovery_leftover,
                forced=forced,
                force_failed=force_failed,
            )
        result = replace(result, cleanup_status=cleanup_status)
        copy_rook_artifacts(result, artifact_roots, "after-shutdown")
        result.write_manifest()

    return result


def classify_cleanup_status(
    *,
    already_exited_before_cleanup: bool,
    process_exited_after_cleanup: bool,
    discovery_leftover: bool,
    forced: bool,
    force_failed: bool,
) -> CleanupStatus:
    if already_exited_before_cleanup:
        return CleanupStatus.ALREADY_EXITED_BEFORE_CLEANUP
    if force_failed or not process_exited_after_cleanup:
        return CleanupStatus.FORCE_KILL_FAILED
    if forced:
        return CleanupStatus.GRACEFUL_TIMEOUT_FORCED_KILL
    if discovery_leftover:
        return CleanupStatus.GRACEFUL_EXIT_DISCOVERY_LEFTOVER
    return CleanupStatus.GRACEFUL_EXIT
