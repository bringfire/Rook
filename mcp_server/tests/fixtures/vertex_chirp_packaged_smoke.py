"""Paired installed-wheel compatibility and process retirement; loopback/local only.

Run with the isolated Rook interpreter and pass the isolated Chirp interpreter
and the qualified Chirp source root. All authorization and jobs are synthetic.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

from rook import chirp_manager as chirp
from rook.providers import vertex_backend as backend
from rook.providers.vertex_auth import VertexAuthError, VertexMode, VertexRecord, VertexStore
from rook.providers.vertex_oauth import DesktopOAuthClient
from rook.providers.vertex_workforce_contract import (
    EntraSessionCandidate, FirmSettings, PrivatePrincipal, VerifiedEntraAssertion, WorkforceExchangeResult,
)
from rook.providers.vertex_workforce_store import VertexWorkforceStore

parser = argparse.ArgumentParser()
parser.add_argument('--chirp-python', required=True)
parser.add_argument('--chirp-root', required=True)
args = parser.parse_args()
assert sys.version_info[:3] == (3, 11, 9)

settings = FirmSettings(2, 'Synthetic paired smoke', '11111111-1111-1111-1111-111111111111',
    '22222222-2222-2222-2222-222222222222', '123456789', 'synthetic-pool', 'synthetic-provider',
    'synthetic-firm-project', 'synthetic-firm-project', None, 'us-central1')

READER = r'''
import json, sys
from pathlib import Path
from chirp.vertex_bootstrap import VertexBootstrap, VertexRestartRequired
import chirp.vertex_bootstrap as reader
assert sys.version_info[:3] == (3,11,9)
installed = Path(reader.__file__).resolve()
assert installed.is_relative_to(Path(sys.prefix).resolve())
assert installed.read_text(encoding='utf-8') == (Path(sys.argv[2])/'src/chirp/vertex_bootstrap.py').read_text(encoding='utf-8')
envelope = json.load(sys.stdin)
bootstrap = VertexBootstrap(**envelope)
try: bootstrap.assert_current_generation(sys.argv[1])
except VertexRestartRequired:
    assert sys.argv[3] == 'blocked'
else:
    assert sys.argv[3] == 'ready'
'''

def check_reader(base, runtime, mode, expected):
    envelope = dict(schema_version=1, generation=runtime.generation, mode=mode,
        project_id=runtime.project_id, region=runtime.region, vertex_credentials=runtime.vertex_credentials)
    result = subprocess.run([args.chirp_python, '-I', '-c', READER, str(base.path), args.chirp_root, expected],
        input=json.dumps(envelope).encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
    assert result.returncode == 0, 'Installed Chirp reader contract failed (synthetic fixture).'


with tempfile.TemporaryDirectory(prefix='rook-chirp-paired-smoke-') as directory:
    root = Path(directory)
    base = VertexStore(root/'vertex.json', mutex_name='Local\\Rook.PairedSmoke.'+uuid.uuid4().hex)
    store = VertexWorkforceStore(base)
    for mode in ('oauth', 'adc'):
        if mode == 'oauth':
            result = backend.connect_vertex_oauth(DesktopOAuthClient('synthetic-client', 'synthetic-secret'),
                'synthetic-project', 'us-central1', store=base,
                authorize=lambda _: dict(type='authorized_user', client_id='synthetic-client',
                    client_secret='synthetic-secret', refresh_token='synthetic-refresh'), recycler=lambda _: None)
            assert result.success
        else:
            base.replace(VertexRecord(1, '0'*32, VertexMode.ADC, 'synthetic-project', 'us-central1', None, None))
        runtime = base.resolve_runtime()
        check_reader(base, runtime, mode, 'ready')
        store.import_pending(settings)
        check_reader(base, runtime, mode, 'ready')
        assert base.read().generation == runtime.generation
        store.disconnect_all()
        check_reader(base, runtime, mode, 'blocked')

    # The separate launcher runs from the installed Rook wheel. Its Popen child
    # is undiscovered when activation occurs, then publishes a late synthetic
    # discovery file. Retirement must remain blocked until actual settlement.
    base.replace(VertexRecord(1, '0'*32, VertexMode.ADC, 'synthetic-project', 'us-central1', None, None))
    child_code = r'''
import json, os, time
from pathlib import Path
root = Path(__file__).resolve().parent
while not (root/'publish').exists():
    if (root/'child-exit').exists(): raise SystemExit()
    time.sleep(.01)
folder = root/'discovery'; folder.mkdir(exist_ok=True)
(folder/'chirp-service-12345.json').write_text(json.dumps(dict(pid=os.getpid(),host='127.0.0.1',port=12345)))
(root/'published').touch()
while not (root/'child-exit').exists(): time.sleep(.01)
'''
    (root/'child.py').write_text(child_code)
    launch_code = r'''
import subprocess, sys, time
from pathlib import Path
from rook import chirp_manager as chirp
from rook.providers.vertex_auth import VertexStore
root = Path(sys.argv[1])
base = VertexStore(root/'vertex.json', mutex_name=sys.argv[2])
VertexStore.production = classmethod(lambda cls: base)
chirp._start_chirp_unlocked = lambda *a,**k: k['launch'].start([sys.executable,'-I',str(root/'child.py')],creationflags=subprocess.CREATE_NO_WINDOW)
child = chirp._start_chirp(root)
(root/'child-pid').write_text(str(child.pid))
try:
    while not (root/'owner-exit').exists(): time.sleep(.01)
finally:
    if child.poll() is None: child.terminate()
    child.wait(timeout=3)
'''
    def wait_file(path):
        deadline = time.monotonic()+8
        while not path.exists() and time.monotonic() < deadline: time.sleep(.01)
        assert path.exists(), 'Local child did not reach the synthetic barrier.'
    owner = subprocess.Popen([sys.executable, '-I', '-c', launch_code, str(root), base._mutex_name],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        wait_file(root/'child-pid')
        pid = int((root/'child-pid').read_text())
        assert chirp._is_pid_alive(pid)
        principal = PrivatePrincipal(settings.entra_tenant_id, '33333333-3333-3333-3333-333333333333', 'synthetic-account')
        candidate = EntraSessionCandidate(principal, '{"refresh":"synthetic-refresh"}',
            VerifiedEntraAssertion('synthetic-assertion', principal, int(time.time())+3600))
        exchange = WorkforceExchangeResult('synthetic-bearer', int(time.time())+3600,
            settings.project_id, settings.workforce_pool_user_project, settings.quota_project_id)
        context = store.activate(store.import_pending(settings), candidate, exchange, cancel_check=lambda: None)
        VertexStore.production = classmethod(lambda cls: base)
        chirp.DISCOVERY_FOLDER = root/'discovery'
        chirp._chirp_process = None
        try:
            backend.finish_workforce_retirement(store=store, expected_generation=context.generation,
                deadline=time.monotonic()+.25, cancel_check=lambda: None, retire=chirp.retire_after_workforce_commit)
        except VertexAuthError: pass
        else: raise AssertionError('Undiscovered launch was treated as settled.')
        assert store.snapshot_active().chirp_retirement_pending
        (root/'publish').touch(); wait_file(root/'published')
        assert chirp._is_pid_alive(pid) and store.snapshot_active().chirp_retirement_pending
        (root/'child-exit').touch()
        deadline = time.monotonic()+5
        while chirp._is_pid_alive(pid) and time.monotonic() < deadline: time.sleep(.01)
        assert not chirp._is_pid_alive(pid)
        backend.finish_workforce_retirement(store=store, expected_generation=context.generation,
            deadline=time.monotonic()+3, cancel_check=lambda: None, retire=chirp.retire_after_workforce_commit)
        assert not store.snapshot_active().chirp_retirement_pending
        assert not list((root/'chirp-launches').glob('*.json'))
    finally:
        (root/'child-exit').touch(); (root/'owner-exit').touch()
        try: owner.communicate(timeout=6)
        except subprocess.TimeoutExpired: owner.kill(); owner.communicate(timeout=3)

with tempfile.TemporaryDirectory(prefix='rook-chirp-orphan-smoke-') as directory:
    from rook.chirp_launch_tracking import LaunchRegistry
    from rook.chirp_process_job import job_is_active
    root = Path(directory)
    base = VertexStore(root/'vertex.json', mutex_name='Local\\Rook.OrphanSmoke.'+uuid.uuid4().hex)
    leaf = "import os,time; from pathlib import Path; root=Path(__file__).parent; (root/'leaf-pid').write_text(str(os.getpid()));\nwhile not (root/'leaf-exit').exists(): time.sleep(.01)\n"
    middle = "import os,subprocess,sys; from pathlib import Path; root=Path(__file__).parent; (root/'middle-pid').write_text(str(os.getpid())); subprocess.Popen([sys.executable,'-I',str(root/'leaf.py')],creationflags=subprocess.CREATE_NO_WINDOW); os._exit(0)"
    parent = "import os,subprocess,sys; from pathlib import Path; root=Path(__file__).parent; subprocess.Popen([sys.executable,'-I',str(root/'middle.py')],creationflags=subprocess.CREATE_NO_WINDOW); os._exit(0)"
    for name, code in [('leaf', leaf), ('middle', middle), ('parent', parent)]:
        (root/(name+'.py')).write_text(code)
    registry = LaunchRegistry(base)
    receipt = registry.begin()
    child = registry.launch(receipt).start([sys.executable, '-I', str(root/'parent.py')], creationflags=subprocess.CREATE_NO_WINDOW)
    job_name = registry._read(receipt)['job_name']
    try:
        child.wait(timeout=5)
        wait_file(root/'leaf-pid'); wait_file(root/'middle-pid')
        middle_pid = int((root/'middle-pid').read_text())
        deadline = time.monotonic()+3
        while chirp._is_pid_alive(middle_pid) and time.monotonic() < deadline: time.sleep(.01)
        assert not chirp._is_pid_alive(middle_pid)
        assert chirp._is_pid_alive(int((root/'leaf-pid').read_text()))
        assert job_is_active(job_name) is True and registry.pending()
    finally:
        (root/'leaf-exit').touch()
        if child.poll() is None: child.terminate(); child.wait(timeout=3)
        deadline = time.monotonic()+4
        while receipt.exists() and registry.pending() and time.monotonic() < deadline: time.sleep(.02)
        assert not receipt.exists()

print('Paired packaged smoke passed: installed CPython 3.11.9 Rook/Chirp source correspondence, fresh OAuth and ADC pending-import continuity, disconnect refusal, cross-process undiscovered launch and late discovery, orphan descendant after intermediate exit, blocked retirement and verified settlement; synthetic data only, no cloud traffic.')
