"""Cross-package and real process integration; synthetic stores and children only."""
import asyncio
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from rook import chirp_manager as chirp
from rook.providers.vertex_auth import VertexAuthError, VertexMode, VertexRecord
from rook.providers import vertex_backend as backend
from .test_vertex_workforce_store import fixture as workforce_fixture


@pytest.mark.parametrize('mode', ['oauth', 'adc'])
def test_actual_rook_v2_store_is_readable_by_chirp(workforce_fixture, mode):
    companion = pytest.importorskip('chirp.vertex_bootstrap', reason='Cross-package qualification requires the Chirp source or wheel.')
    VertexBootstrap, VertexRestartRequired = companion.VertexBootstrap, companion.VertexRestartRequired
    from rook.providers.vertex_oauth import DesktopOAuthClient
    base, store, settings, *_ = workforce_fixture
    if mode == 'oauth':
        result = backend.connect_vertex_oauth(DesktopOAuthClient('synthetic-client', 'synthetic-secret'), 'synthetic-project', 'us-central1', store=base, authorize=lambda _: {'type':'authorized_user','client_id':'synthetic-client','client_secret':'synthetic-secret','refresh_token':'synthetic-refresh'}, recycler=lambda _: None)
        assert result.success
    else:
        base.replace(VertexRecord(1, '0'*32, VertexMode.ADC, 'synthetic-project', 'us-central1', None, None))
    runtime = base.resolve_runtime()
    bootstrap = VertexBootstrap(1, runtime.generation, mode, runtime.project_id, runtime.region, runtime.vertex_credentials)
    bootstrap.assert_current_generation(base.path)
    store.import_pending(settings)
    bootstrap.assert_current_generation(base.path)
    assert base.read().generation == runtime.generation
    store.disconnect_all()
    with pytest.raises(VertexRestartRequired): bootstrap.assert_current_generation(base.path)


@pytest.mark.asyncio
async def test_admission_wait_does_not_block_independent_heartbeat(monkeypatch):
    acquired, release = threading.Event(), threading.Event()
    def hold():
        with chirp._replacement_lock:
            acquired.set(); release.wait(2)
    holder = threading.Thread(target=hold); holder.start()
    assert acquired.wait(1)
    monkeypatch.setattr(chirp.VertexStore, 'production', lambda: SimpleNamespace(read=lambda: None))
    async def healthy(*args): return {'status': 'ok'}
    monkeypatch.setattr(chirp, '_read_health', healthy)
    timer = threading.Timer(.35, release.set); timer.start()
    started = time.monotonic()
    admission = asyncio.create_task(chirp._handle_live_discovery({'host':'127.0.0.1','port':12345,'pid':123}, 'anthropic/claude-opus-5'))
    try:
        await asyncio.sleep(.02)
        assert time.monotonic()-started < .15
        release.set()
        assert (await asyncio.wait_for(admission, 2))['running']
    finally:
        release.set(); timer.cancel(); holder.join(2); timer.join()
        await asyncio.wait_for(admission, 2)


_LAUNCHER = r'''
import json, subprocess, sys, time
from pathlib import Path
from rook import chirp_manager as chirp
from rook.providers.vertex_auth import VertexStore
class Protector:
    def protect(self, value): return bytes(byte ^ 0xA5 for byte in value)
    unprotect = protect
root = Path(sys.argv[1])
base = VertexStore(root/'vertex.json', protector=Protector(), mutex_name=sys.argv[2])
VertexStore.production = classmethod(lambda cls: base)
chirp._start_chirp_unlocked = lambda *a, **k: k['launch'].start([sys.executable, str(root/'child.py')], creationflags=subprocess.CREATE_NO_WINDOW)
child = chirp._start_chirp(root)
(root/'child-pid').write_text(str(child.pid))
try:
    while not (root/'owner-exit').exists(): time.sleep(.01)
finally:
    if child.poll() is None: child.terminate()
    child.wait(timeout=3)
'''

_CHILD = r'''
import json, os, time
from pathlib import Path
root = Path(__file__).resolve().parent
while not (root/'publish').exists():
    if (root/'child-exit').exists(): raise SystemExit()
    time.sleep(.01)
folder = root/'discovery'; folder.mkdir(exist_ok=True)
(folder/'chirp-service-12345.json').write_text(json.dumps({'pid':os.getpid(),'host':'127.0.0.1','port':12345}))
(root/'published').write_text('yes')
while not (root/'child-exit').exists(): time.sleep(.01)
'''

def _wait_file(path):
    deadline = time.monotonic()+4
    while not path.exists() and time.monotonic() < deadline: time.sleep(.01)
    assert path.exists()


def test_other_process_undiscovered_launch_keeps_retirement_block(workforce_fixture, monkeypatch):
    base, store, settings, _, candidate, exchange = workforce_fixture
    root = base.path.parent
    base.replace(VertexRecord(1, '0'*32, VertexMode.ADC, 'synthetic-project', 'us-central1', None, None))
    (root/'child.py').write_text(_CHILD)
    owner = subprocess.Popen([sys.executable, '-c', _LAUNCHER, str(root), base._mutex_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
    monkeypatch.setattr(chirp.VertexStore, 'production', lambda: base)
    monkeypatch.setattr(chirp, 'DISCOVERY_FOLDER', root/'discovery')
    monkeypatch.setattr(chirp, '_chirp_process', None)
    try:
        _wait_file(root/'child-pid')
        pid = int((root/'child-pid').read_text())
        assert chirp._is_pid_alive(pid)
        ticket = store.import_pending(settings)
        context = store.activate(ticket, candidate, exchange, cancel_check=lambda: None)
        with pytest.raises(VertexAuthError):
            backend.finish_workforce_retirement(store=store, expected_generation=context.generation, deadline=time.monotonic()+.2, cancel_check=lambda: None, retire=chirp.retire_after_workforce_commit)
        assert store.snapshot_active().chirp_retirement_pending
        (root/'publish').touch(); _wait_file(root/'published')
        assert chirp._is_pid_alive(pid)
        assert store.snapshot_active().chirp_retirement_pending
        (root/'child-exit').touch()
        deadline = time.monotonic()+3
        while chirp._is_pid_alive(pid) and time.monotonic() < deadline: time.sleep(.01)
        assert not chirp._is_pid_alive(pid)
        backend.finish_workforce_retirement(store=store, expected_generation=context.generation, deadline=time.monotonic()+2, cancel_check=lambda: None, retire=chirp.retire_after_workforce_commit)
        assert not store.snapshot_active().chirp_retirement_pending
        assert not list((root/'chirp-launches').glob('*.json'))
    finally:
        (root/'child-exit').touch(); (root/'owner-exit').touch()
        try: owner.communicate(timeout=5)
        except subprocess.TimeoutExpired: owner.kill(); owner.communicate(timeout=2)


def test_real_orphan_descendant_remains_in_job_after_intermediates_exit(workforce_fixture):
    from rook.chirp_launch_tracking import LaunchRegistry
    from rook.chirp_process_job import job_is_active
    base, *_ = workforce_fixture
    root = base.path.parent
    leaf = "import os,time; from pathlib import Path; root=Path(__file__).parent; (root/'leaf-pid').write_text(str(os.getpid()));\nwhile not (root/'leaf-exit').exists(): time.sleep(.01)\n"
    middle = "import os,subprocess,sys; from pathlib import Path; root=Path(__file__).parent; (root/'middle-pid').write_text(str(os.getpid())); subprocess.Popen([sys.executable,str(root/'leaf.py')],creationflags=subprocess.CREATE_NO_WINDOW); os._exit(0)"
    parent = "import os,subprocess,sys; from pathlib import Path; root=Path(__file__).parent; subprocess.Popen([sys.executable,str(root/'middle.py')],creationflags=subprocess.CREATE_NO_WINDOW); os._exit(0)"
    (root/'leaf.py').write_text(leaf)
    (root/'middle.py').write_text(middle)
    (root/'parent.py').write_text(parent)
    registry = LaunchRegistry(base)
    receipt = registry.begin()
    child = registry.launch(receipt).start([sys.executable, str(root/'parent.py')], creationflags=subprocess.CREATE_NO_WINDOW)
    name = registry._read(receipt)['job_name']
    try:
        child.wait(timeout=5)
        _wait_file(root/'leaf-pid')
        _wait_file(root/'middle-pid')
        middle_pid = int((root/'middle-pid').read_text())
        deadline = time.monotonic()+3
        while chirp._is_pid_alive(middle_pid) and time.monotonic() < deadline: time.sleep(.01)
        assert not chirp._is_pid_alive(middle_pid)
        assert chirp._is_pid_alive(int((root/'leaf-pid').read_text()))
        assert job_is_active(name) is True
        assert registry.pending() and receipt.exists()
    finally:
        (root/'leaf-exit').touch()
        if child.poll() is None: child.terminate(); child.wait(timeout=3)
        deadline = time.monotonic()+4
        while receipt.exists() and registry.pending() and time.monotonic() < deadline: time.sleep(.02)
        assert not receipt.exists()
