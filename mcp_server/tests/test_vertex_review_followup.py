"""User review regressions: synthetic stores and actual loopback sockets only."""
import asyncio
import json
import socket
import threading
import time
from dataclasses import replace
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from rook.providers.vertex_auth import VertexAuthError
from rook.providers import vertex_entra as entra, vertex_workforce_exchange as exchange
from .test_vertex_workforce_store import fixture as workforce_fixture


@pytest.mark.parametrize('cancelled', [False, True])
def test_native_dns_cancel_closes_request_without_resolver_thread(monkeypatch, cancelled):
    from rook.providers import vertex_dns as dns
    from rook.providers.vertex_bounded_io import SocketDeadline
    instances = []
    class Lookup:
        def __init__(self, *args): self.ready = False; self.cancelled = False; self.closed = False; instances.append(self)
        def poll(self, seconds): time.sleep(seconds); return self.ready
        def cancel(self): self.cancelled = True; self.ready = True
        def close(self): self.closed = True
        def addresses(self): raise AssertionError('Late resolution must not publish')
    monkeypatch.setattr(dns, '_WindowsResolution', Lookup)
    cancel = threading.Event()
    def check():
        if cancel.is_set(): raise VertexAuthError('vertex_authorization_declined', 'Cancelled.')
    timer = threading.Timer(.05, cancel.set) if cancelled else None
    if timer: timer.start()
    started = time.monotonic()
    try:
        with SocketDeadline(started+(2 if cancelled else .05), check, time.monotonic) as guard:
            with pytest.raises(VertexAuthError): dns.resolve_addresses('synthetic.invalid', 443, guard)
        assert time.monotonic()-started < .4
        assert len(instances) == 1 and instances[0].cancelled and instances[0].closed
        assert dns._retained is None
    finally:
        if timer: timer.cancel(); timer.join()


def test_failed_native_cancel_retains_one_request_until_completion(monkeypatch):
    from rook.providers import vertex_dns as dns
    from rook.providers.vertex_bounded_io import SocketDeadline
    instances = []
    class Lookup:
        def __init__(self, *args): self.ready = bool(instances); self.closed = False; instances.append(self)
        def poll(self, seconds): time.sleep(seconds); return self.ready
        def cancel(self): pass  # Broken provider does not confirm cancellation.
        def close(self): self.closed = True
        def addresses(self):
            assert self is not instances[0], 'Abandoned lookup cannot return late results'
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, ('127.0.0.1', 443))]
    monkeypatch.setattr(dns, '_WindowsResolution', Lookup)
    monkeypatch.setattr(dns, '_retained', None)
    with SocketDeadline(time.monotonic()+.05, lambda: None, time.monotonic) as guard:
        with pytest.raises(VertexAuthError): dns.resolve_addresses('synthetic.invalid', 443, guard)
    assert dns._retained is instances[0] and not instances[0].closed
    with SocketDeadline(time.monotonic()+1, lambda: None, time.monotonic) as guard:
        with pytest.raises(VertexAuthError): dns.resolve_addresses('synthetic.invalid', 443, guard)
        assert len(instances) == 1
        instances[0].ready = True
        assert dns.resolve_addresses('synthetic.invalid', 443, guard)[0][-1] == ('127.0.0.1', 443)
    assert all(instance.closed for instance in instances) and dns._retained is None


def test_native_localhost_resolution_preserves_addresses_without_blocking_getaddrinfo(monkeypatch):
    from rook.providers.vertex_dns import resolve_addresses
    from rook.providers.vertex_bounded_io import SocketDeadline
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *args: pytest.fail('Blocking resolver must not be called'))
    with SocketDeadline(time.monotonic()+2, lambda: None, time.monotonic) as guard:
        values = resolve_addresses('localhost', 45678, guard)
    assert values and all(value[-1][1] == 45678 for value in values)
    assert all(value[-1][0] in ('127.0.0.1', '::1') for value in values)


def test_ipv6_socket_creation_failure_falls_back_to_real_ipv4_listener(monkeypatch):
    from rook.providers import vertex_bounded_io as bounded
    from rook.providers.vertex_dns import resolve_addresses
    allocate = socket.socket
    attempted = []
    with allocate(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', 0)); listener.listen(2); listener.settimeout(2)
        port = listener.getsockname()[1]
        with bounded.SocketDeadline(time.monotonic()+2, lambda: None, time.monotonic) as guard:
            resolved = resolve_addresses('localhost', port, guard)
        assert resolved[0][0] == socket.AF_INET6
        assert any(value[0] == socket.AF_INET for value in resolved)
        def ipv6_unavailable(family=socket.AF_INET, *args, **kwargs):
            attempted.append(family)
            if family == socket.AF_INET6:
                raise OSError(10047, 'Synthetic unsupported address family')
            return allocate(family, *args, **kwargs)
        monkeypatch.setattr(socket, 'socket', ipv6_unavailable)
        # Control: stdlib handles the same injected allocation failure.
        with socket.create_connection(('localhost', port), timeout=2) as control:
            control.sendall(b'control')
            with listener.accept()[0] as accepted:
                assert accepted.recv(7) == b'control'
        assert attempted[0] == socket.AF_INET6 and attempted[-1] == socket.AF_INET
        attempted.clear()
        with bounded.SocketDeadline(time.monotonic()+2, lambda: None, time.monotonic) as guard:
            connection = bounded._DeadlineHTTPConnection('localhost', port, timeout=1, guard=guard)
            try:
                connection.connect()
                connection.sock.sendall(b'fallback')
                with listener.accept()[0] as accepted:
                    assert accepted.recv(8) == b'fallback'
                assert attempted[0] == socket.AF_INET6 and attempted[-1] == socket.AF_INET
            finally:
                connection.close()


def test_per_address_timeout_allows_next_address_before_absolute_cutoff(monkeypatch):
    import errno
    from rook.providers import vertex_bounded_io as bounded
    peers = []
    class Peer:
        def __init__(self, *args): self.closed = False; peers.append(self)
        def setblocking(self, value): pass
        def settimeout(self, value): pass
        def setsockopt(self, *args): pass
        def connect_ex(self, address): return errno.EINPROGRESS if len(peers) == 1 else 0
        def shutdown(self, how): pass
        def close(self): self.closed = True
    monkeypatch.setattr(socket, 'socket', Peer)
    monkeypatch.setattr(bounded, 'resolve_addresses', lambda *args: [(socket.AF_INET6, socket.SOCK_STREAM, 6, ('::1', 9, 0, 0)), (socket.AF_INET, socket.SOCK_STREAM, 6, ('127.0.0.1', 9))])
    def pending(*args): time.sleep(args[-1]); return [], [], []
    monkeypatch.setattr(bounded.select, 'select', pending)
    with bounded.SocketDeadline(time.monotonic()+.5, lambda: None, time.monotonic) as guard:
        connection = bounded._DeadlineHTTPConnection('localhost', 9, timeout=.1, guard=guard)
        connection.connect()
        assert connection.sock is peers[1] and peers[0].closed
        connection.close()


@pytest.mark.asyncio
async def test_held_native_dns_releases_configuration_slot_on_deadline(workforce_fixture, tmp_path, monkeypatch):
    from rook.agent.chat.vertex_configuration_http import VertexConfigurationHttp
    from rook.providers import vertex_dns as dns
    instances = []
    class Lookup:
        def __init__(self, *args): self.ready = False; self.closed = False; instances.append(self)
        def poll(self, seconds): time.sleep(seconds); return self.ready
        def cancel(self): self.ready = True
        def close(self): self.closed = True
        def addresses(self): raise AssertionError('Must not dispatch')
    monkeypatch.setattr(dns, '_WindowsResolution', Lookup)
    monkeypatch.setattr(entra, '_allowed_url', lambda *args, **kwargs: None)
    _, store, settings, *_ = workforce_fixture
    ticket = store.import_pending(settings)
    def begin(settings, ticket, *, cancel_check, deadline_changed):
        deadline = time.monotonic()+.1; deadline_changed(deadline)
        return entra.BoundedEntraHttpClient(settings, deadline, cancel_check).get('http://synthetic.invalid/')
    service = VertexConfigurationHttp(store=store.base, entra=SimpleNamespace(begin=begin))
    started = time.monotonic()
    response = await service.execute({'operation':'connect_firm', 'pending_revision':ticket.pending_revision, 'authorization_epoch':ticket.authorization_epoch}, lambda: False)
    assert response.status != 200
    if service.worker is not None: await asyncio.wait_for(asyncio.shield(service.worker), .3)
    await asyncio.sleep(0)
    assert service.worker is None and time.monotonic()-started < .6
    assert len(instances) == 1 and instances[0].closed
    path = tmp_path/'synthetic-firm.json'; path.write_text(json.dumps(asdict(settings)))
    imported = await service.execute({'operation':'import_firm', 'settings_path':str(path)}, lambda: False)
    assert imported.status == 200


@pytest.mark.parametrize('phase', ['dns', 'connect'])
@pytest.mark.parametrize('cancelled', [False, True])
def test_resolution_and_connect_release_auth_worker_at_cutoff(monkeypatch, phase, cancelled):
    import errno
    from rook.providers import vertex_bounded_io as bounded
    cancel = threading.Event()
    peers = []
    def check():
        if cancel.is_set(): raise VertexAuthError('vertex_authorization_declined', 'Cancelled.')
    def held_dns(*args, **kwargs):
        time.sleep(.8)
        raise socket.gaierror('synthetic held DNS')
    def held_resolution(host, port, guard):
        while True:
            guard.check(); time.sleep(.01)
    class Peer:
        def __init__(self, *args): self.closed = False; peers.append(self)
        def settimeout(self, value): pass
        def setblocking(self, value): pass
        def connect(self, address): time.sleep(.8)
        def connect_ex(self, address): return errno.EINPROGRESS
        def shutdown(self, how): pass
        def close(self): self.closed = True
    if phase == 'dns':
        monkeypatch.setattr(socket, 'getaddrinfo', held_dns)
        monkeypatch.setattr(bounded, 'resolve_addresses', held_resolution, raising=False)
    else:
        monkeypatch.setattr(socket, 'getaddrinfo', lambda *args: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 9))])
        monkeypatch.setattr(socket, 'socket', Peer)
        # A pending nonblocking connection never becomes writable.
        import select
        def pending(*args): time.sleep(args[-1]); return [], [], []
        monkeypatch.setattr(select, 'select', pending)
    timer = threading.Timer(.15, cancel.set) if cancelled else None
    if timer: timer.start()
    started = time.monotonic()
    try:
        with bounded.SocketDeadline(started+(2 if cancelled else .15), check, time.monotonic) as guard:
            connection = bounded._DeadlineHTTPConnection('synthetic.invalid' if phase == 'dns' else '127.0.0.1', 9, timeout=2, guard=guard)
            with pytest.raises(VertexAuthError): connection.connect()
        assert time.monotonic()-started < .5
        assert all(peer.closed for peer in peers)
    finally:
        if timer: timer.cancel(); timer.join()


@pytest.mark.asyncio
@pytest.mark.parametrize('caller', ['normal', 'cancelled', 'timeout'])
async def test_disconnect_owns_deletion_before_await_and_after_caller_cancellation(workforce_fixture, tmp_path, monkeypatch, caller):
    from rook.agent.chat.vertex_configuration_http import VertexConfigurationHttp
    _, store, settings, *_ = workforce_fixture
    service = VertexConfigurationHttp(store=store.base, recycler=lambda _: None, check_timeout=.1)
    old_release = asyncio.Event()
    service.worker = asyncio.create_task(old_release.wait())
    service.cancel = threading.Event()
    service.worker.add_done_callback(service._settled)
    deletion_entered, deletion_release, deletion_finished = threading.Event(), threading.Event(), threading.Event()
    calls = []
    delete = service.firm_store.disconnect_all
    def held_delete():
        calls.append(1); deletion_entered.set()
        try:
            assert deletion_release.wait(3)
            delete()
        finally: deletion_finished.set()
    monkeypatch.setattr(service.firm_store, 'disconnect_all', held_delete)
    path = tmp_path/'synthetic-firm.json'; path.write_text(json.dumps(asdict(settings)))
    disconnect = asyncio.create_task(service.execute({'operation':'disconnect'}, lambda: False))
    assert await asyncio.to_thread(deletion_entered.wait, 1)
    retained = None
    try:
        old = service.worker; old_release.set(); await old; await asyncio.sleep(0)
        if caller == 'cancelled':
            disconnect.cancel()
            with pytest.raises(asyncio.CancelledError): await disconnect
        elif caller == 'timeout':
            result = await asyncio.wait_for(asyncio.shield(disconnect), .4)
            assert result.status == 504 and 'data' not in json.loads(result.body)
            owned = service.retirement_worker
            retry = await service.execute({'operation':'disconnect'}, lambda: False)
            assert retry.status == 504 and service.retirement_worker is owned
        busy = await service.execute({'operation':'import_firm', 'settings_path':str(path)}, lambda: False)
        assert busy.status == 409 and json.loads(busy.body)['error']['code'] == 'vertex_configuration_busy'
        retained = service.retirement_worker
        assert retained is not None and not retained.done()
        deletion_release.set(); await retained; await asyncio.sleep(0)
        if caller == 'normal': await disconnect
        imported = await service.execute({'operation':'import_firm', 'settings_path':str(path)}, lambda: False)
        assert imported.status == 200 and store.read_pending()[0] == settings
        assert calls == [1]
    finally:
        old_release.set(); deletion_release.set()
        if not disconnect.done(): await disconnect
        assert await asyncio.to_thread(deletion_finished.wait, 1)
        if service.retirement_worker is not None: await service.retirement_worker


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
