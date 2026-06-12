"""Stdlib-only process matching and rebuild guard for Rook installer finalization."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import ctypes
from ctypes import wintypes
import os
import threading


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    parent_pid: int | None
    image_path: str
    command_line: str = ""
    created_utc: float | None = None


@dataclass(frozen=True)
class CloseResult:
    ok: bool
    closed_pids: list[int]
    failures: list[str]


def normalize_root(path: str | Path) -> str:
    return str(Path(path)).replace("/", "\\").rstrip("\\").lower() + "\\"


def is_under_root(process: ProcessInfo, rook_root: str | Path) -> bool:
    image = process.image_path.replace("/", "\\").lower()
    return image.startswith(normalize_root(rook_root))


def by_pid(processes: list[ProcessInfo]) -> dict[int, ProcessInfo]:
    return {p.pid: p for p in processes}


def is_valid_parent(parent: ProcessInfo, child: ProcessInfo) -> bool:
    if child.parent_pid != parent.pid:
        return False
    if parent.created_utc is None or child.created_utc is None:
        return True
    return parent.created_utc <= child.created_utc


def find_matched_roots(
    processes: list[ProcessInfo], rook_root: str | Path
) -> list[ProcessInfo]:
    processes_by_pid = by_pid(processes)
    roots: list[ProcessInfo] = []

    for process in processes:
        if not is_under_root(process, rook_root):
            continue

        parent = (
            processes_by_pid.get(process.parent_pid)
            if process.parent_pid is not None
            else None
        )
        if (
            parent is not None
            and is_under_root(parent, rook_root)
            and is_valid_parent(parent, process)
        ):
            continue

        roots.append(process)

    return roots


def descendant_closure(
    processes: list[ProcessInfo], root_pids: set[int]
) -> list[ProcessInfo]:
    processes_by_pid = by_pid(processes)
    children_by_parent: dict[int, list[ProcessInfo]] = {}

    for process in processes:
        if process.parent_pid is None:
            continue
        parent = processes_by_pid.get(process.parent_pid)
        if parent is None or not is_valid_parent(parent, process):
            continue
        children_by_parent.setdefault(process.parent_pid, []).append(process)

    result: list[ProcessInfo] = []
    visited: set[int] = set()

    def visit(process: ProcessInfo) -> None:
        if process.pid in visited:
            return
        visited.add(process.pid)
        for child in children_by_parent.get(process.pid, []):
            visit(child)
        result.append(process)

    for process in processes:
        if process.pid in root_pids:
            visit(process)

    return result


def compute_kill_order(
    processes: list[ProcessInfo],
    rook_root: str | Path,
    exclude_root_pids: set[int] | None = None,
) -> list[ProcessInfo]:
    exclude_root_pids = exclude_root_pids or set()
    matched_roots = find_matched_roots(processes, rook_root)
    kill_order = descendant_closure(processes, {p.pid for p in matched_roots})
    excluded = {
        p.pid for p in descendant_closure(processes, set(exclude_root_pids))
    }
    return [p for p in kill_order if p.pid not in excluded]


class SequenceSnapshotProvider:
    def __init__(self, snapshots: list[list[ProcessInfo]]) -> None:
        self._snapshots = list(snapshots)
        self.calls = 0

    def snapshot(self) -> list[ProcessInfo]:
        self.calls += 1
        if self.calls <= len(self._snapshots):
            return list(self._snapshots[self.calls - 1])
        return []


class WindowsSnapshotProvider:
    TH32CS_SNAPPROCESS = 0x00000002
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    MAX_PATH_BUFFER = 32768
    INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(wintypes.ULONG)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * wintypes.MAX_PATH),
        ]

    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError("WindowsSnapshotProvider is only available on Windows")
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.CreateToolhelp32Snapshot.argtypes = [
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        self.kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        self.kernel32.Process32FirstW.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(self.PROCESSENTRY32W),
        ]
        self.kernel32.Process32FirstW.restype = wintypes.BOOL
        self.kernel32.Process32NextW.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(self.PROCESSENTRY32W),
        ]
        self.kernel32.Process32NextW.restype = wintypes.BOOL
        self.kernel32.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        self.kernel32.OpenProcess.restype = wintypes.HANDLE
        self.kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        self.kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        self.kernel32.GetProcessTimes.restype = wintypes.BOOL
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = wintypes.BOOL

    def snapshot(self) -> list[ProcessInfo]:
        handle = self.kernel32.CreateToolhelp32Snapshot(
            self.TH32CS_SNAPPROCESS, 0
        )
        if handle == self.INVALID_HANDLE_VALUE:
            return []

        try:
            entry = self.PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(self.PROCESSENTRY32W)
            processes: list[ProcessInfo] = []
            ok = self.kernel32.Process32FirstW(handle, ctypes.byref(entry))

            while ok:
                pid = int(entry.th32ProcessID)
                parent_pid = int(entry.th32ParentProcessID)
                image_path = self._query_image_path(pid) or entry.szExeFile
                created_utc = self._query_created_utc(pid)
                processes.append(
                    ProcessInfo(
                        pid=pid,
                        parent_pid=parent_pid,
                        image_path=image_path,
                        created_utc=created_utc,
                    )
                )
                ok = self.kernel32.Process32NextW(handle, ctypes.byref(entry))

            return processes
        finally:
            self.kernel32.CloseHandle(handle)

    def _open_query_handle(self, pid: int):
        return self.kernel32.OpenProcess(
            self.PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )

    def _query_image_path(self, pid: int) -> str | None:
        handle = self._open_query_handle(pid)
        if not handle:
            return None

        try:
            buffer = ctypes.create_unicode_buffer(self.MAX_PATH_BUFFER)
            size = wintypes.DWORD(len(buffer))
            ok = self.kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size)
            )
            if not ok:
                return None
            return buffer.value
        finally:
            self.kernel32.CloseHandle(handle)

    def _query_created_utc(self, pid: int) -> float | None:
        handle = self._open_query_handle(pid)
        if not handle:
            return None

        try:
            creation = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel = wintypes.FILETIME()
            user = wintypes.FILETIME()
            ok = self.kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_time),
                ctypes.byref(kernel),
                ctypes.byref(user),
            )
            if not ok:
                return None
            value = (creation.dwHighDateTime << 32) + creation.dwLowDateTime
            return (value - 116444736000000000) / 10_000_000
        finally:
            self.kernel32.CloseHandle(handle)


class WindowsTerminator:
    PROCESS_TERMINATE = 0x0001

    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError("WindowsTerminator is only available on Windows")
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        self.kernel32.OpenProcess.restype = wintypes.HANDLE
        self.kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.kernel32.TerminateProcess.restype = wintypes.BOOL
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = wintypes.BOOL

    def close_processes(
        self, label: str, processes: list[ProcessInfo]
    ) -> CloseResult:
        closed_pids: list[int] = []
        failures: list[str] = []

        for process in processes:
            handle = self.kernel32.OpenProcess(
                self.PROCESS_TERMINATE, False, process.pid
            )
            if not handle:
                error = ctypes.get_last_error()
                failures.append(
                    f"{label}: failed to open pid {process.pid} "
                    f"({process.image_path}) for termination; Win32 error {error}"
                )
                continue

            try:
                if self.kernel32.TerminateProcess(handle, 1):
                    closed_pids.append(process.pid)
                else:
                    error = ctypes.get_last_error()
                    failures.append(
                        f"{label}: failed to terminate pid {process.pid} "
                        f"({process.image_path}); Win32 error {error}"
                    )
            finally:
                self.kernel32.CloseHandle(handle)

        return CloseResult(
            ok=not failures,
            closed_pids=closed_pids,
            failures=failures,
        )


class RebuildGuard:
    MAX_CLOSE_ATTEMPTS_PER_IDENTITY = 3
    MAX_CONSECUTIVE_SWEEP_FAILURES = 3

    def __init__(
        self,
        label: str,
        rook_root: str | Path,
        snapshot_provider=None,
        terminator=None,
        current_pid: int | None = None,
        sweep_interval_seconds: float = 1.0,
        run_background: bool = True,
        max_close_attempts_per_identity: int = MAX_CLOSE_ATTEMPTS_PER_IDENTITY,
        max_consecutive_sweep_failures: int = MAX_CONSECUTIVE_SWEEP_FAILURES,
    ) -> None:
        self.label = label
        self.rook_root = rook_root
        self.snapshot_provider = (
            snapshot_provider
            if snapshot_provider is not None
            else WindowsSnapshotProvider()
        )
        self.terminator = terminator if terminator is not None else WindowsTerminator()
        self.current_pid = current_pid if current_pid is not None else os.getpid()
        self.sweep_interval_seconds = sweep_interval_seconds
        self.run_background = run_background
        self.max_close_attempts_per_identity = max_close_attempts_per_identity
        self.max_consecutive_sweep_failures = max_consecutive_sweep_failures
        self.close_failures: list[str] = []
        self.thread_died_unexpectedly = False
        self._close_attempts_by_identity: dict[tuple[int, float | None, str], int] = {}
        self._recorded_close_failures: set[str] = set()
        self._consecutive_sweep_failures = 0
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self):
        self.sweep_once()
        if self.run_background:
            self._thread = threading.Thread(
                target=self._run, name=f"{self.label}-rebuild-guard", daemon=True
            )
            self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def stop(self) -> None:
        self._stopped.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=max(self.sweep_interval_seconds, 0.1) + 1.0)

    def sweep_once(self) -> CloseResult:
        if self._stopped.is_set():
            return CloseResult(ok=True, closed_pids=[], failures=[])

        processes = self.snapshot_provider.snapshot()
        kill_order = compute_kill_order(
            processes, self.rook_root, exclude_root_pids={self.current_pid}
        )
        if not kill_order:
            return CloseResult(ok=True, closed_pids=[], failures=[])

        attemptable = [
            process
            for process in kill_order
            if self._close_attempts_by_identity.get(self._identity_key(process), 0)
            < self.max_close_attempts_per_identity
        ]
        if not attemptable:
            return CloseResult(ok=True, closed_pids=[], failures=[])

        result = self.terminator.close_processes(self.label, attemptable)
        closed_pids = set(result.closed_pids)
        for process in attemptable:
            if process.pid not in closed_pids:
                identity = self._identity_key(process)
                self._close_attempts_by_identity[identity] = (
                    self._close_attempts_by_identity.get(identity, 0) + 1
                )
        for failure in result.failures:
            if failure not in self._recorded_close_failures:
                self._recorded_close_failures.add(failure)
                self.close_failures.append(failure)
        return result

    def _run(self) -> None:
        while not self._stopped.wait(self.sweep_interval_seconds):
            try:
                self.sweep_once()
                self._consecutive_sweep_failures = 0
            except Exception as exc:
                self._consecutive_sweep_failures += 1
                self.close_failures.append(f"{self.label}: guard sweep failed: {exc}")
                if (
                    self._consecutive_sweep_failures
                    >= self.max_consecutive_sweep_failures
                ):
                    self.thread_died_unexpectedly = True
                    self.close_failures.append(
                        f"{self.label}: guard thread failed after "
                        f"{self._consecutive_sweep_failures} consecutive sweep errors"
                    )
                    break

    @staticmethod
    def _identity_key(process: ProcessInfo) -> tuple[int, float | None, str]:
        return (
            process.pid,
            process.created_utc,
            process.image_path.replace("/", "\\").lower(),
        )
