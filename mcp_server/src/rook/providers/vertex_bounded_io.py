"""Interrupt owned sockets at an absolute deadline, including HTTP headers."""
import http.client
import math
import socket
import threading
from urllib.request import HTTPHandler, HTTPSHandler, HTTPRedirectHandler, build_opener

from .vertex_workforce_contract import auth_error


class SocketDeadline:
    def __init__(self, deadline, cancel_check, monotonic):
        self.deadline, self.cancel_check, self.monotonic = deadline, cancel_check, monotonic
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._sockets = []
        self._thread = None

    def check(self):
        self.cancel_check()
        if not math.isfinite(self.deadline) or self.monotonic() >= self.deadline:
            raise auth_error('vertex_token_issuance_timeout')

    @staticmethod
    def _abort(peer):
        try: peer.shutdown(socket.SHUT_RDWR)
        except OSError: pass
        try: peer.close()
        except OSError: pass

    def register(self, peer):
        with self._lock:
            try: self.check()
            except Exception:
                self._abort(peer)
                raise
            self._sockets.append(peer)

    def _watch(self):
        while not self._stop.wait(.025):
            try: self.check()
            except Exception:
                with self._lock:
                    for peer in self._sockets: self._abort(peer)
                return

    def __enter__(self):
        self.check()
        self._thread = threading.Thread(target=self._watch, name='Rook auth socket deadline', daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *args):
        self._stop.set()
        self._thread.join()


def _track_connection(connection, guard):
    connection.guard = guard
    create = connection._create_connection
    def connect(*args, **kwargs):
        guard.check()
        peer = create(*args, **kwargs)
        guard.register(peer)  # Before proxy headers or TLS handshake.
        return peer
    connection._create_connection = connect


class _DeadlineHTTPConnection(http.client.HTTPConnection):
    def __init__(self, *args, guard, **kwargs):
        super().__init__(*args, **kwargs)
        _track_connection(self, guard)


class _DeadlineHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, guard, **kwargs):
        super().__init__(*args, **kwargs)
        _track_connection(self, guard)

    def connect(self):
        # Match stdlib HTTPSConnection, retaining its verified SSL context and
        # hostname, but register the SSL socket before its blocking handshake.
        http.client.HTTPConnection.connect(self)
        self.guard.check()
        self.sock = self._context.wrap_socket(self.sock,
            server_hostname=self._tunnel_host or self.host, do_handshake_on_connect=False)
        self.guard.register(self.sock)
        self.sock.do_handshake()
        self.guard.check()


class _HttpHandler(HTTPHandler):
    def __init__(self, guard): super().__init__(); self.guard = guard
    def http_open(self, request):
        return self.do_open(lambda *args, **kwargs: _DeadlineHTTPConnection(*args, guard=self.guard, **kwargs), request)


class _HttpsHandler(HTTPSHandler):
    def __init__(self, guard): super().__init__(); self.guard = guard
    def https_open(self, request):
        tls = {'context': self._context}
        if hasattr(self, '_check_hostname'):  # CPython 3.11; removed in 3.12.
            tls['check_hostname'] = self._check_hostname
        return self.do_open(lambda *args, **kwargs: _DeadlineHTTPSConnection(*args, guard=self.guard, **kwargs), request,
            **tls)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None


def bounded_opener(guard):
    return build_opener(_HttpHandler(guard), _HttpsHandler(guard), _NoRedirect())
