"""User review regressions: synthetic stores and actual loopback sockets only."""
import asyncio
import json
import socket
import threading
import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from rook.providers.vertex_auth import VertexAuthError
from rook.providers import vertex_entra as entra, vertex_workforce_exchange as exchange
from .test_vertex_workforce_store import fixture as workforce_fixture


@pytest.mark.parametrize('phase', ['headers', 'body'])
@pytest.mark.parametrize('cancelled', [False, True])
def test_callback_slow_input_worker_settles_at_absolute_deadline(phase, cancelled):
    listener = entra.EntraLoopbackListener()
    stop, cancel = threading.Event(), threading.Event()
    errors = []
    def check():
        if cancel.is_set(): raise VertexAuthError('vertex_authorization_declined', 'Cancelled.')
    def send():
        try:
            with socket.create_connection(('127.0.0.1', urlsplit(listener.redirect_uri).port), timeout=1) as peer:
                port = urlsplit(listener.redirect_uri).port
                peer.sendall(b'POST / HTTP/1.1\r\n')
                if phase == 'body': peer.sendall(f'Host: localhost:{port}\r\nContent-Type: application/x-www-form-urlencoded\r\nContent-Length: 100\r\n\r\n'.encode())
                for _ in range(48):
                    if stop.wait(.025): break
                    peer.sendall(b'x')
        except OSError: pass
    thread = threading.Thread(target=send); thread.start()
    timer = threading.Timer(.15, cancel.set) if cancelled else None
    if timer: timer.start()
    started = time.monotonic()
    try:
        with pytest.raises(VertexAuthError): listener.wait_for_callback(started + (2 if cancelled else .15), check, time.monotonic)
        assert time.monotonic() - started < .5
    finally:
        stop.set(); thread.join(2); listener.close()
        if timer: timer.cancel(); timer.join()


@pytest.mark.parametrize('provider', ['entra', 'sts'])
@pytest.mark.parametrize('cancelled', [False, True])
def test_dripping_response_headers_release_auth_worker(workforce_fixture, monkeypatch, provider, cancelled):
    _, _, settings, *_ = workforce_fixture
    stop, cancel = threading.Event(), threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            try:
                self.connection.sendall(b'HTTP/1.1 200 OK\r\nX-Slow: ')
                for _ in range(48):
                    if stop.wait(.025): break
                    self.connection.sendall(b'x')
                self.connection.sendall(b'\r\nContent-Length: 2\r\n\r\n{}')
            except OSError: pass
        do_POST = do_GET
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever); thread.start()
    url = f'http://127.0.0.1:{server.server_port}/'
    monkeypatch.setattr(entra, '_allowed_url', lambda *args, **kwargs: None)
    monkeypatch.setattr(exchange, 'STS_URL', url)
    def check():
        if cancel.is_set(): raise VertexAuthError('vertex_authorization_declined', 'Cancelled.')
    started = time.monotonic(); deadline = started + (2 if cancelled else .2)
    timer = threading.Timer(.15, cancel.set) if cancelled else None
    if timer: timer.start()
    try:
        with pytest.raises(VertexAuthError):
            if provider == 'entra': entra.BoundedEntraHttpClient(settings, deadline, check).get(url)
            else: exchange._StsRequest(deadline, check)(url=url, method='POST', headers={}, body=b'synthetic')
        assert time.monotonic() - started < .65
    finally:
        stop.set(); server.shutdown(); server.server_close(); thread.join(2)
        if timer: timer.cancel(); timer.join()


def test_cancel_during_sts_transport_setup_prevents_dispatch(monkeypatch):
    cancelled = [False]
    calls = []
    def setup(guard):
        cancelled[0] = True
        return SimpleNamespace(open=lambda *args, **kwargs: calls.append(args))
    def check():
        if cancelled[0]: raise VertexAuthError('vertex_authorization_declined', 'Cancelled.')
    monkeypatch.setattr(exchange, 'bounded_opener', setup)
    with pytest.raises(VertexAuthError):
        exchange._StsRequest(time.monotonic()+2, check)(url=exchange.STS_URL, method='POST', headers={}, body=b'synthetic')
    assert calls == []


@pytest.mark.parametrize('trusted', [False, True])
def test_bounded_https_keeps_certificate_verification(tmp_path, trusted):
    import ssl
    from datetime import datetime, timedelta, timezone
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from urllib.request import Request, build_opener
    from rook.providers.vertex_bounded_io import SocketDeadline, _HttpsHandler
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, 'localhost')])
    now = datetime.now(timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(1).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(minutes=5))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]), critical=False)
        .sign(key, hashes.SHA256()))
    cert = tmp_path/'synthetic-cert.pem'; private = tmp_path/'synthetic-key.pem'
    cert.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            calls.append(1); self.send_response(200); self.send_header('Content-Length', '2'); self.end_headers(); self.wfile.write(b'{}')
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(cert, private)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever); thread.start()
    try:
        with SocketDeadline(time.monotonic()+2, lambda: None, time.monotonic) as guard:
            handler = _HttpsHandler(guard)
            if trusted: handler._context = ssl.create_default_context(cafile=str(cert))
            opener = build_opener(handler)
            request = Request(f'https://localhost:{server.server_port}/')
            if trusted:
                with opener.open(request, timeout=1) as response: assert response.read() == b'{}'
            else:
                with pytest.raises(Exception): opener.open(request, timeout=1)
        assert calls == ([1] if trusted else [])
    finally:
        server.shutdown(); server.server_close(); thread.join(2)


@pytest.mark.asyncio
async def test_busy_disconnect_returns_committed_state_while_recycler_is_held(workforce_fixture):
    from rook.agent.chat.vertex_configuration_http import VertexConfigurationHttp
    _, store, settings, _, candidate, _ = workforce_fixture
    ticket = store.import_pending(settings)
    browser_entered, browser_release = threading.Event(), threading.Event()
    recycler_entered, recycler_release = threading.Event(), threading.Event()
    def begin(*args, **kwargs):
        browser_entered.set(); assert browser_release.wait(3)
        return replace(candidate, operation_deadline=time.monotonic()+30)
    def recycle(_):
        recycler_entered.set(); assert recycler_release.wait(3)
    service = VertexConfigurationHttp(store=store.base, entra=SimpleNamespace(begin=begin), recycler=recycle, check_timeout=.1)
    first = asyncio.create_task(service.execute({'operation':'connect_firm', 'pending_revision':ticket.pending_revision, 'authorization_epoch':ticket.authorization_epoch}, lambda:False))
    assert await asyncio.to_thread(browser_entered.wait, 1)
    task = asyncio.create_task(service.execute({'operation':'disconnect'}, lambda:False))
    assert await asyncio.to_thread(recycler_entered.wait, 1)
    try:
        result = await asyncio.wait_for(asyncio.shield(task), .4)
        value = json.loads(result.body)
        assert result.status == 409 and value['error']['code'] == 'vertex_restart_required'
        assert value['data']['active'] is None and value['data']['pending'] is None
        assert store.snapshot_active() is None and store.read_pending() is None
        browser_release.set(); await first
        busy = await service.execute({'operation':'import_firm', 'settings_path':'C:/synthetic-unused.json'}, lambda:False)
        assert busy.status == 409 and json.loads(busy.body)['error']['code'] == 'vertex_configuration_busy'
    finally:
        browser_release.set(); recycler_release.set()
        await first; await task
        retirement = getattr(service, 'retirement_worker', None)
        if retirement is not None: await retirement
