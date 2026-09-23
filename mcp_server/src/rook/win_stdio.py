"""Non-blocking stdin for the stdio MCP transport on Windows.

The MCP stdio server reads ``sys.stdin`` on a worker thread with a synchronous,
blocking ``ReadFile`` on the stdin pipe. Windows serializes I/O on a
non-overlapped pipe object, so while that read is pending *any other operation
on the same pipe blocks*, including ``PeekNamedPipe``, which the C runtime's
``fstat`` uses to size a pipe. OpenBLAS calls ``fstat`` on the standard
descriptors from its DLL initializer, and numpy and scipy each bundle a copy.
Because the learning stack is imported lazily on first use, the first tool call
that reached it (via knowledge injection) loaded numpy inside ``LoadLibrary``,
``fstat`` waited on the pipe behind the idle reader, the reader waited for the
next request, and the client waited for the response: a three-way deadlock
that took the whole server down (seen live as ``rookbim_status`` never
answering; native stacks in ``rook-audit-2026-09-22/mcp-hang-native-stacks*.log``).
Duplicating the descriptor or bypassing the CRT lock does not help: the
serialization is on the kernel pipe object.

``install_polling_stdin()`` replaces ``sys.stdin`` with a reader that polls the
pipe with ``PeekNamedPipe`` and only issues ``ReadFile`` when bytes are already
available, so no read is ever pending while the server is idle. Idle polling
sleeps ``POLL_INTERVAL`` seconds between checks (added request latency is at
most that). Non-pipe stdin (a console or a file) is left untouched.
"""

from __future__ import annotations

import io
import sys
import time

__all__ = ["install_polling_stdin", "PollingPipeReader", "POLL_INTERVAL"]

POLL_INTERVAL = 0.01

_ERROR_BROKEN_PIPE = 109
_ERROR_NO_DATA = 232
_ERROR_PIPE_NOT_CONNECTED = 233
_FILE_TYPE_PIPE = 0x0003


class PollingPipeReader(io.RawIOBase):
    """Raw reader over a Win32 pipe handle that never leaves a ReadFile pending."""

    def __init__(self, handle: int, poll_interval: float = POLL_INTERVAL) -> None:
        import ctypes
        from ctypes import wintypes

        self._ctypes = ctypes
        self._wintypes = wintypes
        self._handle = wintypes.HANDLE(handle)
        self._poll_interval = poll_interval
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.ReadFile.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
        k32.ReadFile.restype = wintypes.BOOL
        k32.PeekNamedPipe.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
        k32.PeekNamedPipe.restype = wintypes.BOOL
        self._k32 = k32

    def readable(self) -> bool:
        return True

    def _available(self) -> int | None:
        """Bytes waiting in the pipe, or None at EOF (writer gone)."""
        ctypes, wintypes = self._ctypes, self._wintypes
        avail = wintypes.DWORD(0)
        if self._k32.PeekNamedPipe(self._handle, None, 0, None, ctypes.byref(avail), None):
            return avail.value
        err = ctypes.get_last_error()
        if err in (_ERROR_BROKEN_PIPE, _ERROR_NO_DATA, _ERROR_PIPE_NOT_CONNECTED):
            return None
        raise OSError(err, ctypes.FormatError(err))

    def readinto(self, buffer) -> int:  # type: ignore[override]
        ctypes, wintypes = self._ctypes, self._wintypes
        view = memoryview(buffer).cast("B")
        if len(view) == 0:
            return 0
        while True:
            avail = self._available()
            if avail is None:
                return 0
            if avail > 0:
                break
            time.sleep(self._poll_interval)
        want = min(avail, len(view))
        read = wintypes.DWORD(0)
        target = (ctypes.c_char * want).from_buffer(view[:want])
        if not self._k32.ReadFile(self._handle, target, want, ctypes.byref(read), None):
            err = ctypes.get_last_error()
            if err in (_ERROR_BROKEN_PIPE, _ERROR_NO_DATA, _ERROR_PIPE_NOT_CONNECTED):
                return 0
            raise OSError(err, ctypes.FormatError(err))
        return read.value


def install_polling_stdin() -> bool:
    """On Windows, when stdin is a pipe, rebind ``sys.stdin`` to a polling reader.

    Returns True when the reader was installed.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        import msvcrt
        from ctypes import wintypes

        if getattr(sys.stdin, "buffer", None) is None:
            return False
        handle = msvcrt.get_osfhandle(sys.stdin.fileno())
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetFileType.argtypes = [wintypes.HANDLE]
        k32.GetFileType.restype = wintypes.DWORD
        if k32.GetFileType(wintypes.HANDLE(handle)) != _FILE_TYPE_PIPE:
            return False
    except (OSError, ValueError, AttributeError):
        return False
    raw = PollingPipeReader(handle)
    sys.stdin = io.TextIOWrapper(io.BufferedReader(raw), encoding="utf-8", errors="replace")
    return True
