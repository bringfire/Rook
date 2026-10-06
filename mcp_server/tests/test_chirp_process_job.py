"""Opened thread ownership must be rechecked before a suspended-child resume."""
import ctypes
from types import SimpleNamespace

import pytest

from rook import chirp_process_job as jobs
from rook.providers.vertex_auth import VertexAuthError


@pytest.mark.parametrize('thread_owner, process_wait', [(999, 258), (42, 0)])
def test_reused_thread_or_exited_original_child_is_never_resumed(monkeypatch, thread_owner, process_wait):
    calls = []
    def first(snapshot, pointer):
        entry = ctypes.cast(pointer, ctypes.POINTER(jobs._ThreadEntry)).contents
        entry.pid, entry.tid = 42, 7
        return True
    def last(*args): ctypes.set_last_error(18); return False
    kernel = SimpleNamespace(CreateToolhelp32Snapshot=lambda *args: 1, Thread32First=first,
        Thread32Next=last, OpenThread=lambda *args: 2, GetProcessIdOfThread=lambda _: thread_owner,
        WaitForSingleObject=lambda *args: process_wait, ResumeThread=lambda _: calls.append('resume'),
        CloseHandle=lambda handle: calls.append(('close', handle)))
    monkeypatch.setattr(jobs, '_kernel', lambda: kernel)
    with pytest.raises(VertexAuthError): jobs.resume_process(SimpleNamespace(pid=42, _handle=3))
    assert 'resume' not in calls
    assert calls == [('close', 1), ('close', 2)]
