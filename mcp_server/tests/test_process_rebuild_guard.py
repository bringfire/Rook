from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD_PATH = REPO_ROOT / "installer" / "process_rebuild_guard.py"


def load_guard():
    spec = importlib.util.spec_from_file_location("process_rebuild_guard", GUARD_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def proc(module, pid, ppid, image, created):
    return module.ProcessInfo(
        pid=pid,
        parent_pid=ppid,
        image_path=image,
        command_line="",
        created_utc=created,
    )


def test_matching_roots_count_stub_only_when_child_is_also_matched():
    guard = load_guard()
    root = r"C:\Users\me\AppData\Local\Rook"
    processes = [
        proc(guard, 10, 900, root + r"\venv\Scripts\python.exe", 10.0),
        proc(guard, 11, 10, root + r"\python\cpython-3.11.9\python.exe", 11.0),
        proc(guard, 900, 1, r"C:\Program Files\Claude\claude.exe", 1.0),
    ]

    roots = guard.find_matched_roots(processes, root)

    assert [p.pid for p in roots] == [10]


def test_descendant_closure_includes_out_of_boundary_system_python_child():
    guard = load_guard()
    root = r"C:\Users\me\AppData\Local\Rook"
    processes = [
        proc(guard, 10, 900, root + r"\venv\Scripts\python.exe", 10.0),
        proc(guard, 11, 10, r"C:\Python311\python.exe", 11.0),
        proc(guard, 12, 11, r"C:\Python311\python.exe", 12.0),
    ]

    closure = guard.descendant_closure(processes, {10})

    assert [p.pid for p in closure] == [12, 11, 10]


def test_pid_reuse_rejects_parent_created_after_child():
    guard = load_guard()
    parent = proc(guard, 10, 1, r"C:\parent.exe", 20.0)
    child = proc(guard, 11, 10, r"C:\child.exe", 10.0)

    assert guard.is_valid_parent(parent, child) is False


def test_finalizer_exclusion_removes_self_and_descendants():
    guard = load_guard()
    root = r"C:\Users\me\AppData\Local\Rook"
    processes = [
        proc(guard, 100, 50, root + r"\python\cpython-3.11.9\python.exe", 100.0),
        proc(guard, 101, 100, root + r"\venv\Scripts\python.exe", 101.0),
        proc(guard, 200, 900, root + r"\venv\Scripts\python.exe", 200.0),
    ]

    kill_set = guard.compute_kill_order(processes, root, exclude_root_pids={100})

    assert [p.pid for p in kill_set] == [200]


def test_rebuild_guard_stands_down_after_success():
    guard = load_guard()
    events: list[str] = []

    class FakeTerminator:
        def close_processes(self, label, processes):
            events.append(f"{label}:{[p.pid for p in processes]}")
            return guard.CloseResult(ok=True, closed_pids=[p.pid for p in processes], failures=[])

    snapshots = [
        [proc(guard, 10, 900, r"C:\Rook\venv\Scripts\python.exe", 10.0)],
        [],
    ]

    provider = guard.SequenceSnapshotProvider(snapshots)
    guard_instance = guard.RebuildGuard(
        label="rook-mcp",
        rook_root=r"C:\Rook",
        snapshot_provider=provider,
        terminator=FakeTerminator(),
        current_pid=999,
        sweep_interval_seconds=0,
        run_background=False,
    )
    with guard_instance:
        pass

    guard_instance.sweep_once()
    assert events == ["rook-mcp:[10]"]
    assert provider.calls == 1


def test_rebuild_guard_defaults_to_windows_dependencies(monkeypatch):
    guard = load_guard()

    class FakeSnapshotProvider:
        instances = []

        def __init__(self):
            self.calls = 0
            self.snapshots = [
                [proc(guard, 10, 900, r"C:\Rook\venv\Scripts\python.exe", 10.0)],
                [],
            ]
            self.__class__.instances.append(self)

        def snapshot(self):
            self.calls += 1
            if self.calls <= len(self.snapshots):
                return self.snapshots[self.calls - 1]
            return []

    class FakeTerminator:
        instances = []

        def __init__(self):
            self.calls = []
            self.__class__.instances.append(self)

        def close_processes(self, label, processes):
            self.calls.append((label, [p.pid for p in processes]))
            return guard.CloseResult(
                ok=True,
                closed_pids=[p.pid for p in processes],
                failures=[],
            )

    monkeypatch.setattr(guard, "WindowsSnapshotProvider", FakeSnapshotProvider)
    monkeypatch.setattr(guard, "WindowsTerminator", FakeTerminator)

    guard_instance = guard.RebuildGuard(
        label="rook-mcp",
        rook_root=r"C:\Rook",
        current_pid=999,
        run_background=False,
    )

    result = guard_instance.sweep_once()
    with guard_instance:
        pass

    assert guard_instance.snapshot_provider is FakeSnapshotProvider.instances[0]
    assert guard_instance.terminator is FakeTerminator.instances[0]
    assert result.closed_pids == [10]
    assert FakeSnapshotProvider.instances[0].calls == 2
    assert FakeTerminator.instances[0].calls == [("rook-mcp", [10])]


def test_windows_terminator_failure_messages_include_win32_error_and_image_path(
    monkeypatch,
):
    guard = load_guard()
    terminator = object.__new__(guard.WindowsTerminator)
    error_codes = iter([5, 87])

    class FakeKernel32:
        def __init__(self):
            self.closed_handles = []

        def OpenProcess(self, access, inherit_handle, pid):
            if pid == 100:
                return 0
            return 1234

        def TerminateProcess(self, handle, exit_code):
            return False

        def CloseHandle(self, handle):
            self.closed_handles.append(handle)
            return True

    fake_kernel32 = FakeKernel32()
    terminator.kernel32 = fake_kernel32
    monkeypatch.setattr(guard.ctypes, "get_last_error", lambda: next(error_codes))

    result = terminator.close_processes(
        "rook-mcp",
        [
            proc(guard, 100, 1, r"C:\Rook\open-fails.exe", 10.0),
            proc(guard, 200, 1, r"C:\Rook\terminate-fails.exe", 20.0),
        ],
    )

    assert result.ok is False
    assert result.closed_pids == []
    assert result.failures == [
        (
            r"rook-mcp: failed to open pid 100 "
            r"(C:\Rook\open-fails.exe) for termination; Win32 error 5"
        ),
        (
            r"rook-mcp: failed to terminate pid 200 "
            r"(C:\Rook\terminate-fails.exe); Win32 error 87"
        ),
    ]
    assert fake_kernel32.closed_handles == [1234]
