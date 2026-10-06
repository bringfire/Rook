"""Independent review regressions; synthetic stores and local HTTP only."""
import asyncio
from dataclasses import replace
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
from types import SimpleNamespace

import pytest

from rook.agent.chat.vertex_configuration_http import VertexConfigurationHttp
from rook.providers import vertex_backend as backend
from rook.providers.vertex_auth import VertexAuthError, VertexMode
from .test_vertex_backend import _store, _record, _auth, _authorized_user
from .test_vertex_workforce_store import fixture as workforce_fixture


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['failure', 'cancel'])
async def test_committed_activation_failure_reports_new_active_status(workforce_fixture, monkeypatch, outcome):
    _, store, settings, _, candidate, exchange = workforce_fixture
    store.base.replace(_record(_auth()))
    ticket = store.import_pending(settings)
    monkeypatch.setattr(backend, 'exchange_assertion', lambda *args, **kwargs: exchange)
    def retire(*args):
        if outcome == 'cancel':
            raise VertexAuthError('vertex_authorization_declined', 'Cancelled.')
        raise RuntimeError('private-sentinel')
    entra = SimpleNamespace(begin=lambda *args, **kwargs: replace(candidate, operation_deadline=time.monotonic()+30))
    service = VertexConfigurationHttp(store=store.base, entra=entra, retire=retire)
    response = await service.execute({'operation':'connect_firm', 'pending_revision':ticket.pending_revision, 'authorization_epoch':ticket.authorization_epoch}, lambda:False)
    value = json.loads(response.body)
    assert response.status == 409 and not value['success']
    assert value['error']['code'] == 'vertex_restart_required'
    assert value['data']['active_generation'] == store.snapshot_active().generation
    assert value['data']['state'] == 'restart_required' and value['data']['retirement_pending']
    assert value['data']['pending'] is None and value['data']['legacy_mode'] is None
    assert 'private-sentinel' not in response.body.decode()


@pytest.mark.asyncio
async def test_other_service_empty_disconnect_revokes_first_legacy_browser(tmp_path):
    store = _store(tmp_path)
    entered, release = threading.Event(), threading.Event()
    def authorize(_):
        entered.set(); assert release.wait(3); return _authorized_user()
    path = tmp_path/'client.json'
    path.write_text('{"installed":{"client_id":"synthetic","client_secret":"synthetic"}}')
    first = VertexConfigurationHttp(store=store, authorize=authorize, recycler=lambda _:None)
    second = VertexConfigurationHttp(store=store, recycler=lambda _:None)
    task = asyncio.create_task(first.execute({'operation':'connect','client_config_path':str(path),'project_id':'synthetic-project','video_location':'us-central1'}, lambda:False))
    assert await asyncio.to_thread(entered.wait, 2)
    try:
        response = await second.execute({'operation':'disconnect'},lambda:False)
        assert response.status == 200
    finally:
        release.set()
    result = await task
    assert result.status == 409 and store.read() is None


@pytest.mark.asyncio
async def test_post_browser_worker_deadline_returns_promptly_and_denies_late_activation(workforce_fixture, monkeypatch):
    _, store, settings, _, candidate, exchange = workforce_fixture
    ticket = store.import_pending(settings)
    entered, release = threading.Event(), threading.Event()
    def begin(*args, **kwargs):
        deadline = time.monotonic()+.15
        kwargs['deadline_changed'](deadline)
        entered.set(); assert release.wait(3)
        return replace(candidate, operation_deadline=deadline)
    monkeypatch.setattr(backend, 'exchange_assertion',lambda *args,**kwargs:pytest.fail('No late exchange'))
    service = VertexConfigurationHttp(store=store.base, entra=SimpleNamespace(begin=begin), retire=lambda *args:None)
    task = asyncio.create_task(service.execute({'operation':'connect_firm','pending_revision':ticket.pending_revision,'authorization_epoch':ticket.authorization_epoch},lambda:False))
    assert await asyncio.to_thread(entered.wait, 2)
    try:
        result = await asyncio.wait_for(asyncio.shield(task), .8)
        assert result.status == 504 and service.worker is not None
        assert service.cancel.is_set()
    finally:
        release.set()
        await task
        if service.worker is not None: await service.worker
    assert store.snapshot_active() is None and store.read_pending()[1] == ticket


def test_entra_real_drip_response_is_cut_off_at_aggregate_deadline(workforce_fixture):
    from rook.providers.vertex_entra import BoundedEntraHttpClient
    _, _, settings, *_ = workforce_fixture
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_GET(self):
            self.send_response(200); self.send_header('Content-Length','40'); self.end_headers()
            try:
                for _ in range(40):
                    self.wfile.write(b'x'); self.wfile.flush(); time.sleep(.025)
            except OSError: pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=.15)
    class Opener:
        def open(self,request,timeout):
            connection.request('GET','/'); return connection.getresponse()
    started=time.monotonic()
    try:
        client=BoundedEntraHttpClient(settings,started+.15,lambda:None,opener=Opener())
        with pytest.raises(VertexAuthError): client.get(settings.authority+'/discovery/v2.0/keys')
        assert time.monotonic()-started < .4
    finally:
        connection.close(); server.shutdown(); server.server_close(); thread.join(2)


def test_sts_real_drip_response_yields_for_aggregate_deadline(monkeypatch):
    from rook.providers import vertex_workforce_exchange as exchange
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            self.send_response(200); self.send_header('Content-Length','40'); self.end_headers()
            try:
                for _ in range(40):
                    self.wfile.write(b'x'); self.wfile.flush(); time.sleep(.025)
            except OSError: pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    monkeypatch.setattr(exchange,'STS_URL',f'http://127.0.0.1:{server.server_port}/')
    started=time.monotonic()
    try:
        with pytest.raises(VertexAuthError):
            exchange._StsRequest(started+.25,lambda:None)(url=exchange.STS_URL,method='POST',headers={},body=b'synthetic')
        assert time.monotonic()-started < .65
    finally:
        server.shutdown(); server.server_close(); thread.join(2)


@pytest.mark.parametrize('operation', ['save', 'disconnect'])
def test_legacy_mutation_releases_credential_lock_before_chirp_recycle(tmp_path, monkeypatch, operation):
    from rook import chirp_manager as chirp
    from rook.providers.vertex_auth import VertexStore, _WindowsNamedMutex
    from contextlib import contextmanager
    store=_store(tmp_path); store._mutex_timeout_ms=350
    store.replace(_record(_auth()))
    mutate_entered, launch_entered=threading.Event(),threading.Event()
    original_lock=backend._mutation_lock
    @contextmanager
    def mutation_lock(selected):
        with original_lock(selected):
            mutate_entered.set(); assert launch_entered.wait(2); yield
    def launch_lock(*args):
        launch_entered.set(); return _WindowsNamedMutex(*args)
    monkeypatch.setattr(backend,'_mutation_lock',mutation_lock)
    monkeypatch.setattr(VertexStore,'production',classmethod(lambda cls:store))
    monkeypatch.setattr(chirp,'_WindowsNamedMutex',launch_lock)
    monkeypatch.setattr(chirp,'_chirp_process',None)
    child=object()
    monkeypatch.setattr(chirp,'_start_chirp_unlocked',lambda *args,**kwargs:child)
    results, errors=[],[]
    def recycle(_):
        with chirp._replacement_lock: pass
    def mutate():
        results.append(backend.save_vertex_configuration(VertexMode.ADC,'synthetic-project','us-central1',store=store,recycler=recycle) if operation=='save' else backend.disconnect_vertex(store=store,recycler=recycle))
    def launch():
        try: results.append(chirp._launch_registered_chirp(tmp_path,None,False))
        except Exception as error: errors.append(error)
    mutation=threading.Thread(target=mutate); launcher=threading.Thread(target=launch)
    mutation.start(); assert mutate_entered.wait(2); launcher.start()
    mutation.join(3); launcher.join(3)
    assert not mutation.is_alive() and not launcher.is_alive()
    assert not errors and child in results and any(getattr(value,'success',False) for value in results)
