"""Isolated packaged SDK/DPAPI/TLS smoke; synthetic identities, no external traffic."""
import base64
import gc
import hashlib
import importlib
from importlib.metadata import version
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
from urllib.parse import parse_qs,urlsplit
import uuid

from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
from rook.providers.vertex_auth import VertexStore,VertexAuthError
from rook.providers.vertex_entra import EntraSessionAdapter
from rook.providers.vertex_workforce_contract import FirmSettings
from rook.providers.vertex_workforce_store import VertexWorkforceStore
from rook.providers.vertex_workforce_exchange import exchange_assertion
from rook.providers import vertex_backend as backend

expected={'msal':'1.39.0','google-auth':'2.56.3','PyJWT':'2.15.0','litellm':'1.89.7','requests':'2.34.2','cryptography':'50.0.1','multidict':'6.9.1'}
assert sys.version_info[:3]==(3,11,9) and all(version(key)==value for key,value in expected.items())

# Guard the admitted C-extension correction for GHSA-54p9-h82j-f925.
# Tiny operands verify actual reference ownership without a memory stress test.
from multidict import CIMultiDict, MultiDict
assert CIMultiDict.__module__ == 'multidict._multidict'
for dictionary in (CIMultiDict, MultiDict):
    for operation in ('reflected_union', 'subtraction', 'intersection_control'):
        items=dictionary(seed='x').items()
        sentinel=object()
        operand=[(f'synthetic-{index}',sentinel) for index in range(32)]
        gc.collect(); before=sys.getrefcount(sentinel)
        if operation=='reflected_union': result=operand | items
        elif operation=='subtraction': result=items - operand
        else: result=items & operand
        del result
        gc.collect()
        assert sys.getrefcount(sentinel)==before, f'{dictionary.__name__} {operation} leaks references'
repo=Path(__file__).resolve().parents[3]
for name in ('vertex_backend','vertex_entra','vertex_workforce_exchange','vertex_workforce_store','vertex_token_lease','vertex_bounded_io','vertex_dns'):
    module=importlib.import_module('rook.providers.'+name)
    installed=Path(module.__file__).resolve()
    assert installed.is_relative_to(Path(sys.prefix).resolve())
    source=repo/'mcp_server/src/rook/providers'/f'{name}.py'
    # Wheel build may normalize line endings; compare exact source text.
    assert installed.read_text(encoding='utf-8')==source.read_text(encoding='utf-8')

settings=FirmSettings(2,'Packaged synthetic firm','11111111-1111-1111-1111-111111111111','22222222-2222-2222-2222-222222222222','123456789','synthetic-pool','synthetic-provider','synthetic-firm-project','synthetic-firm-project',None,'us-central1')
oid='33333333-3333-3333-3333-333333333333'
key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
wire={'nonce':None,'state':None,'missing_oid':False,'sts':0,'entra':0}
class Response:
    status_code=200
    headers={}
    def __init__(self,data): self.data=data; self.text=json.dumps(data)
    def json(self): return self.data
class Transport:
    def get(self,url,**kwargs):
        if url.endswith('/.well-known/openid-configuration'):
            return Response({'issuer':settings.authority+'/v2.0','authorization_endpoint':settings.authority+'/oauth2/v2.0/authorize','token_endpoint':settings.authority+'/oauth2/v2.0/token','jwks_uri':settings.authority+'/discovery/v2.0/keys'})
        assert url==settings.authority+'/discovery/v2.0/keys'
        jwk=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())); jwk.update(kid='synthetic-key',alg='RS256',use='sig')
        return Response({'keys':[jwk]})
    def post(self,url,data,**kwargs):
        assert url==settings.authority+'/oauth2/v2.0/token'
        wire['entra']+=1
        now=int(time.time())
        claims={'iss':settings.authority+'/v2.0','aud':settings.entra_client_id,'tid':settings.entra_tenant_id,'oid':oid,'sub':'synthetic-subject','iat':now,'nbf':now-10,'exp':now+3600,'nonce':wire['nonce']}
        if wire['missing_oid']: claims.pop('oid')
        info=base64.urlsafe_b64encode(json.dumps({'uid':oid,'utid':settings.entra_tenant_id}).encode()).decode().rstrip('=')
        return Response({'access_token':'synthetic-entra-access','id_token':jwt.encode(claims,key,algorithm='RS256',headers={'kid':'synthetic-key'}),'token_type':'Bearer','expires_in':3600,'refresh_token':'synthetic-entra-refresh','client_info':info,'scope':'openid profile offline_access'})
class Listener:
    redirect_uri='http://localhost:45678'
    def wait_for_callback(self,*args): return {'code':'synthetic-code','state':wire['state']}
    def close(self): pass
def browser(url):
    query=parse_qs(urlsplit(url).query)
    assert set(query['scope'][0].split())=={'openid','profile','offline_access'}
    assert query['code_challenge_method']==['S256']
    wire.update(nonce=query['nonce'][0],state=query['state'][0]); return True
def sts(**kwargs):
    assert kwargs['url']=='https://sts.googleapis.com/v1/token' and kwargs['method']=='POST'
    assert not any(key.lower()=='authorization' for key in kwargs['headers'])
    body=parse_qs(kwargs['body'].decode())
    assert body['subject_token_type']==['urn:ietf:params:oauth:token-type:id_token']
    wire['sts']+=1
    return SimpleNamespace(status=200,data=json.dumps({'access_token':'synthetic-google-access','expires_in':3600,'token_type':'Bearer','issued_token_type':'urn:ietf:params:oauth:token-type:access_token'}).encode())
backend.exchange_assertion=lambda *args,**kwargs:exchange_assertion(*args,**kwargs,request=sts)
adapter=EntraSessionAdapter(http_client_factory=lambda *args:Transport(),listener_factory=Listener,browser_open=browser)
with tempfile.TemporaryDirectory(prefix='rook-packaged-auth-smoke-') as directory:
    base=VertexStore(Path(directory)/'vertex.json',mutex_name='Local\\Rook.PackagedSmoke.'+uuid.uuid4().hex)
    store=VertexWorkforceStore(base)
    ticket=store.import_pending(settings)
    result=backend.connect_vertex_workforce(ticket,store=store,entra=adapter,cancel_check=lambda:None,retire=lambda *args:None)
    assert result.success and not store.snapshot_active().chirp_retirement_pending
    context=backend.refresh_vertex_workforce(store=store,entra=adapter,expected_generation=result.generation,deadline=time.monotonic()+30,cancel_check=lambda:None)
    assert context.generation==result.generation and store.snapshot_active().cache_revision==1
    assert wire['entra']==2 and wire['sts']==2
    before=base.path.read_bytes(); wire['missing_oid']=True
    try:
        backend.refresh_vertex_workforce(store=store,entra=adapter,expected_generation=result.generation,deadline=time.monotonic()+30,cancel_check=lambda:None)
        raise AssertionError('Missing oid accepted')
    except VertexAuthError: pass
    assert base.path.read_bytes()==before and wire['sts']==2
    store.disconnect_all()
    assert store.snapshot_active() is None and store.authorization_epoch()!=ticket.authorization_epoch

# Exercise the packaged CPython HTTPS handler, including the version-specific
# constructor signature, with a local synthetic certificate and no cloud calls.
import ssl
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, build_opener
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from rook.providers.vertex_bounded_io import SocketDeadline, _HttpsHandler
with tempfile.TemporaryDirectory(prefix='rook-packaged-tls-smoke-') as directory:
    tls_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME,'localhost')])
    now=datetime.now(timezone.utc)
    certificate=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(tls_key.public_key())
        .serial_number(1).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(minutes=5))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]),critical=False).sign(tls_key,hashes.SHA256()))
    cert=Path(directory)/'synthetic-cert.pem'; private=Path(directory)/'synthetic-key.pem'
    cert.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    private.write_bytes(tls_key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_GET(self):
            calls.append(1); self.send_response(200); self.send_header('Content-Length','2'); self.end_headers(); self.wfile.write(b'{}')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(cert,private)
    server.socket=context.wrap_socket(server.socket,server_side=True)
    thread=threading.Thread(target=server.serve_forever); thread.start()
    try:
        for trusted in (False,True):
            with SocketDeadline(time.monotonic()+3,lambda:None,time.monotonic) as guard:
                handler=_HttpsHandler(guard)
                if trusted: handler._context=ssl.create_default_context(cafile=str(cert))
                opener=build_opener(handler); request=Request(f'https://localhost:{server.server_port}/')
                if trusted:
                    with opener.open(request,timeout=2) as response: assert response.read()==b'{}'
                else:
                    try: opener.open(request,timeout=2)
                    except Exception: pass
                    else: raise AssertionError('Untrusted certificate accepted')
                    assert calls==[]
        assert calls==[1]
    finally:
        server.shutdown(); server.server_close(); thread.join(2)
# Socket allocation can fail before connect; retain IPv4 fallback in the actual
# packaged interpreter with Windows localhost resolution and a real listener.
import socket
from unittest.mock import patch
from rook.providers.vertex_bounded_io import _DeadlineHTTPConnection
allocate=socket.socket
attempted=[]
def ipv6_unavailable(family=socket.AF_INET,*args,**kwargs):
    attempted.append(family)
    if family==socket.AF_INET6: raise OSError(10047,'Synthetic unsupported address family')
    return allocate(family,*args,**kwargs)
with allocate(socket.AF_INET,socket.SOCK_STREAM) as listener:
    listener.bind(('127.0.0.1',0)); listener.listen(1); listener.settimeout(2)
    with SocketDeadline(time.monotonic()+3,lambda:None,time.monotonic) as guard:
        connection=_DeadlineHTTPConnection('localhost',listener.getsockname()[1],timeout=2,guard=guard)
        try:
            with patch('socket.socket',ipv6_unavailable): connection.connect()
            assert attempted[0]==socket.AF_INET6 and attempted[-1]==socket.AF_INET
            connection.sock.sendall(b'fallback')
            with listener.accept()[0] as accepted: assert accepted.recv(8)==b'fallback'
        finally: connection.close()
print('Packaged auth smoke passed: CPython 3.11.9, exact pinned SDKs, real MSAL/signed ID tokens, SDK STS wire, forced refresh, missing-oid cache preservation, Windows DPAPI/tombstone lifecycle, actual local TLS certificate verification and IPv6-allocation/IPv4 fallback; no external traffic or real identities.')
