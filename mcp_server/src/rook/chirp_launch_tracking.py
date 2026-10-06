"""Credential-lock-owned launch records shared by Rook configuration processes.

Only process identities are stored. Uncertain intent or process inspection keeps
retirement blocked; no process is terminated through this registry.
"""
import ctypes
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
import uuid
from ctypes import wintypes

from .providers.vertex_auth import VertexAuthError
from .chirp_process_job import ProcessJob, job_is_active, resume_process

CREATE_SUSPENDED = 0x00000004


def _failure():
    return VertexAuthError('vertex_restart_required', 'Managed Chirp launch settlement could not be verified.')


def process_identity(pid):
    if type(pid) is not int or pid <= 0: raise _failure()
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x1000 | 0x100000, False, pid)  # QUERY_LIMITED_INFORMATION | SYNCHRONIZE
    if not handle:
        if ctypes.get_last_error() == 87: return None  # PID no longer exists.
        raise _failure()
    try:
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *[ctypes.byref(value) for value in times]): raise _failure()
        state = kernel.WaitForSingleObject(handle, 0)
        if state == 0: return None
        if state != 258: raise _failure()
        return {'pid':pid, 'created':(times[0].dwHighDateTime << 32) | times[0].dwLowDateTime}
    finally:
        kernel.CloseHandle(handle)


class LaunchRegistry:
    def __init__(self, store):
        self.folder = store.path.parent/'chirp-launches'
        self.mutex_name = store._mutex_name

    def _write(self, path, value):
        raw = json.dumps(value, sort_keys=True).encode()
        if len(raw) > 4096: raise _failure()
        self.folder.mkdir(parents=True, exist_ok=True)
        temporary = self.folder/(uuid.uuid4().hex+'.tmp')
        try:
            with temporary.open('xb') as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _paths(self):
        try:
            paths = []
            for path in self.folder.iterdir():
                if path.suffix == '.json':
                    paths.append(path)
                    if len(paths) > 128:
                        raise _failure()
            return paths
        except FileNotFoundError:
            return []
        except OSError:
            # Path.glob can suppress directory-enumeration errors, which must
            # never be mistaken for proof that all launches have settled.
            raise _failure() from None

    def begin(self):
        if len(self._paths()) >= 128:
            raise _failure()
        owner = process_identity(os.getpid())
        if owner is None: raise _failure()
        path = self.folder/(uuid.uuid4().hex+'.json')
        self._write(path, {'schema_version':1, 'owner':owner,
            'job_name':'Local\\Rook.Chirp.Launch.'+uuid.uuid4().hex, 'contained':False, 'settled':False})
        return path

    def launch(self, path):
        return ContainedLaunch(self, path)

    def contained(self, path):
        value = self._read(path)
        value['contained'] = True
        self._write(path, value)

    def _read(self, path):
        try:
            with path.open('rb') as stream: raw = stream.read(4097)
            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result: raise _failure()
                    result[key] = value
                return result
            value = json.loads(raw, object_pairs_hook=unique)
            if len(raw) > 4096 or set(value) != {'schema_version','owner','job_name','contained','settled'} or type(value['schema_version']) is not int or value['schema_version'] != 1: raise _failure()
            identity = value['owner']
            if not isinstance(identity, dict) or set(identity) != {'pid','created'} or any(type(identity[key]) is not int or identity[key] <= 0 for key in identity): raise _failure()
            if type(value['contained']) is not bool or type(value['settled']) is not bool or (value['settled'] and not value['contained']) or not isinstance(value['job_name'], str) or not re.fullmatch(r'Local\\Rook\.Chirp\.Launch\.[0-9a-f]{32}', value['job_name']): raise _failure()
            return value
        except (OSError, ValueError, TypeError, KeyError): raise _failure() from None

    def pending(self):
        paths = self._paths()
        pending = False
        for path in paths:
            value = self._read(path)
            if not value['contained']:
                # A crash during suspended creation makes the launch uncertain.
                # Never infer settlement from the owner's absence.
                pending = True
                continue
            if not value['settled'] and job_is_active(value['job_name']) is not False:
                pending = True
            else:
                path.unlink()
        return pending


class ContainedLaunch:
    def __init__(self, registry, path):
        self.registry, self.path = registry, path

    def start(self, arguments, **kwargs):
        job_name = self.registry._read(self.path)['job_name']
        job = ProcessJob(job_name)
        process = None
        try:
            kwargs['creationflags'] = kwargs.get('creationflags', 0) | CREATE_SUSPENDED
            process = subprocess.Popen(arguments, **kwargs)
            job.assign(process)
            # Every descendant belongs to this job, even if intermediates exit
            # before the first retirement scan. Commit before any code executes.
            self.registry.contained(self.path)
            keep_job_open(self.path, self.registry.mutex_name, job_name)
            resume_process(process)
            return process
        except BaseException:
            if process is not None:
                try: process.terminate(); process.wait(timeout=2)
                except Exception: pass
            raise
        finally:
            job.close()


def keep_job_open(receipt, mutex_name, expected):
    env = os.environ.copy()
    env.pop('PYTHONHOME', None)
    env.pop('PYTHONPATH', None)
    keeper = subprocess.Popen([sys.executable, '-I', str(Path(__file__).with_name('chirp_job_keeper.py')), str(receipt), mutex_name],
        env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        close_fds=True, creationflags=subprocess.CREATE_NO_WINDOW)
    ready = receipt.with_suffix('.ready')
    deadline = time.monotonic()+5
    while time.monotonic() < deadline and keeper.poll() is None:
        try:
            if ready.read_text(encoding='ascii') == expected:
                ready.unlink(missing_ok=True)
                return
        except FileNotFoundError:
            pass
        time.sleep(.01)
    # Only the newly created keeper can be terminated here, never another job.
    if keeper.poll() is None:
        keeper.terminate()
        keeper.wait(timeout=2)
    raise _failure()
