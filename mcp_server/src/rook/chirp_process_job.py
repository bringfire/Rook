"""Windows containment for a managed Chirp launch, including orphan descendants.

Create suspended, assign to a named job with default (no breakaway) limits, then
resume only after the durable containment receipt commits and the keeper opens
its query handle. Closing our handle does not kill associated processes.
"""
import ctypes
from ctypes import wintypes

from .providers.vertex_auth import VertexAuthError


def _failure():
    return VertexAuthError('vertex_restart_required', 'Managed Chirp process containment could not be verified.')


class _Accounting(ctypes.Structure):
    _fields_ = [(name, ctypes.c_longlong) for name in ('user', 'kernel', 'period_user', 'period_kernel')] + [
        (name, wintypes.DWORD) for name in ('faults', 'total', 'active', 'terminated')]


class _ThreadEntry(ctypes.Structure):
    _fields_ = [(name, wintypes.DWORD) for name in ('size', 'usage', 'tid', 'pid')] + [
        ('base_priority', wintypes.LONG), ('delta_priority', wintypes.LONG), ('flags', wintypes.DWORD)]


def _kernel():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    signatures = {
        'CreateJobObjectW': ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
        'OpenJobObjectW': ([wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
        'AssignProcessToJobObject': ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
        'QueryInformationJobObject': ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p], wintypes.BOOL),
        'CloseHandle': ([wintypes.HANDLE], wintypes.BOOL),
        'CreateToolhelp32Snapshot': ([wintypes.DWORD, wintypes.DWORD], wintypes.HANDLE),
        'Thread32First': ([wintypes.HANDLE, ctypes.POINTER(_ThreadEntry)], wintypes.BOOL),
        'Thread32Next': ([wintypes.HANDLE, ctypes.POINTER(_ThreadEntry)], wintypes.BOOL),
        'OpenThread': ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        'ResumeThread': ([wintypes.HANDLE], wintypes.DWORD),
        'GetProcessIdOfThread': ([wintypes.HANDLE], wintypes.DWORD),
        'WaitForSingleObject': ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(kernel, name)
        function.argtypes = arguments
        function.restype = result
    return kernel


class ProcessJob:
    def __init__(self, name):
        self.kernel = _kernel()
        ctypes.set_last_error(0)
        self.handle = self.kernel.CreateJobObjectW(None, name)
        if not self.handle or ctypes.get_last_error() == 183:
            self.close()
            raise _failure()

    def assign(self, process):
        # Popen retains this exact process handle, preventing PID-reuse races.
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise _failure()

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def job_is_active(name):
    kernel = _kernel()
    handle = kernel.OpenJobObjectW(0x0004, False, name)  # JOB_OBJECT_QUERY
    if not handle:
        if ctypes.get_last_error() == 2:
            return None  # A missing name alone cannot prove tree settlement.
        raise _failure()
    try:
        return query_active(kernel, handle)
    finally:
        kernel.CloseHandle(handle)


def query_active(kernel, handle):
    accounting = _Accounting()
    if not kernel.QueryInformationJobObject(handle, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None):
        raise _failure()
    return accounting.active != 0


def resume_process(process):
    """Popen closes its primary thread handle; reopen only that suspended thread."""
    kernel = _kernel()
    snapshot = kernel.CreateToolhelp32Snapshot(0x00000004, 0)  # TH32CS_SNAPTHREAD
    if not snapshot or snapshot == wintypes.HANDLE(-1).value:
        raise _failure()
    thread_ids = []
    try:
        entry = _ThreadEntry()
        entry.size = ctypes.sizeof(entry)
        if not kernel.Thread32First(snapshot, ctypes.byref(entry)):
            raise _failure()
        while True:
            if entry.pid == process.pid:
                thread_ids.append(entry.tid)
            if not kernel.Thread32Next(snapshot, ctypes.byref(entry)):
                if ctypes.get_last_error() != 18:
                    raise _failure()
                break
    finally:
        kernel.CloseHandle(snapshot)
    if len(thread_ids) != 1:
        raise _failure()
    handle = kernel.OpenThread(0x0002 | 0x0800, False, thread_ids[0])  # SUSPEND_RESUME | QUERY_LIMITED_INFORMATION
    if not handle:
        raise _failure()
    try:
        # The snapshot ID may have been reused before OpenThread. Both opened
        # handles must still identify the exact live Popen child before resume.
        if kernel.GetProcessIdOfThread(handle) != process.pid or kernel.WaitForSingleObject(int(process._handle), 0) != 258:
            raise _failure()
        if kernel.ResumeThread(handle) != 1:
            raise _failure()
    finally:
        kernel.CloseHandle(handle)
