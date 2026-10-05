import asyncio
import threading
from contextlib import contextmanager
from dataclasses import replace
from aiohttp.test_utils import TestClient, TestServer
import pytest
from rook.agent.chat.server import create_chat_app
from rook.agent.chat.vertex_configuration_http import VertexConfigurationHttp
from .test_vertex_backend import _store, _record, _auth, _authorized_user

class Manager:
    async def shutdown(self): pass

PATH='/internal/providers/vertex/configuration'
HEADERS={'X-Rook-Session':'nonce'}

@pytest.mark.asyncio
async def test_status_preserves_existing_text_region_and_never_refreshes(tmp_path):
    auth=_auth(); store=_store(tmp_path)
    store.replace(replace(_record(auth),region='europe-west4'))
    before=store.path.read_bytes()
    service=VertexConfigurationHttp(store=store,recycler=lambda _:None)
    async with TestClient(TestServer(create_chat_app(Manager(),expected_nonce='nonce',vertex_configuration=service))) as client:
        response=await client.post(PATH,headers=HEADERS,json={'operation':'status'})
        data=(await response.json())['data']
        assert data['video_location']=='europe-west4' and not data['video_available']
        assert data['image_location']=='global'
        assert store.path.read_bytes()==before

@pytest.mark.asyncio
@pytest.mark.parametrize('headers,body,status',[
    ({},{'operation':'status'},403),
    ({**HEADERS,'Origin':'https://app.rook.invalid'},{'operation':'status'},403),
    (HEADERS,{'operation':'status','extra':'secret'},400),
    (HEADERS,{'operation':'oauth.connect'},400),
])
async def test_closed_admission(tmp_path,headers,body,status):
    async with TestClient(TestServer(create_chat_app(Manager(),expected_nonce='nonce',vertex_configuration=VertexConfigurationHttp(store=_store(tmp_path))))) as client:
        response=await client.post(PATH,headers=headers,json=body)
        assert response.status==status and response.headers['Cache-Control']=='no-store'
        assert 'Access-Control-Allow-Origin' not in response.headers

@pytest.mark.asyncio
async def test_overlapping_connect_and_cancellation_preserve_prior_bytes(tmp_path):
    auth=_auth(); store=_store(tmp_path); store.replace(_record(auth)); before=store.path.read_bytes()
    started=threading.Event(); released=threading.Event()
    def authorize(_):
        started.set(); released.wait(3); return _authorized_user()
    config=tmp_path/'client.json'; config.write_text('{"installed":{"client_id":"client","client_secret":"secret"}}')
    service=VertexConfigurationHttp(store=store,recycler=lambda _:None,authorize=authorize)
    body={'operation':'connect','client_config_path':str(config),'project_id':'company-ai-project','video_location':'us-central1'}
    first=asyncio.create_task(service.execute(body,lambda:False))
    await asyncio.to_thread(started.wait,2)
    busy=await service.execute(body,lambda:False)
    assert busy.status==409
    first.cancel(); released.set()
    with pytest.raises(asyncio.CancelledError): await first
    assert store.path.read_bytes()==before
    if service.worker is not None: await service.worker
    await asyncio.sleep(0)
    assert service.worker is None

@pytest.mark.asyncio
async def test_explicit_save_preserves_mode_and_rotates_shared_setting(tmp_path):
    store=_store(tmp_path); auth=_auth(); store.replace(_record(auth)); before=store.read()
    recycled=[]; service=VertexConfigurationHttp(store=store,recycler=recycled.append)
    response=await service.execute({'operation':'save','project_id':'company-ai-project','video_location':'us-central1'},lambda:False)
    assert response.status==200
    assert store.read().generation!=before.generation and store.read().mode==before.mode
    assert len(recycled)==1

@pytest.mark.asyncio
@pytest.mark.parametrize('abort_kind',['disconnect','shutdown'])
async def test_browser_worker_cannot_commit_after_client_abort_or_shutdown(tmp_path,abort_kind):
    store=_store(tmp_path); store.replace(_record(_auth())); before=store.path.read_bytes()
    started=threading.Event(); released=threading.Event()
    def authorize(_): started.set(); released.wait(3); return _authorized_user()
    config=tmp_path/'client.json'; config.write_text('{"installed":{"client_id":"client","client_secret":"secret"}}')
    service=VertexConfigurationHttp(store=store,recycler=lambda _:None,authorize=authorize)
    disconnected=False
    pending=asyncio.create_task(service.execute({'operation':'connect','client_config_path':str(config),'project_id':'company-ai-project','video_location':'us-central1'},lambda:disconnected))
    await asyncio.to_thread(started.wait,2)
    if abort_kind=='disconnect':
        disconnected=True
        await asyncio.sleep(.06)
        released.set()
        with pytest.raises(asyncio.CancelledError): await pending
    else:
        shutdown=asyncio.create_task(service.shutdown(None))
        await asyncio.sleep(0)
        released.set(); await shutdown; await pending
    assert store.path.read_bytes()==before

@pytest.mark.asyncio
async def test_bad_client_file_and_failed_settings_write_preserve_previous_bytes(tmp_path,monkeypatch):
    store=_store(tmp_path); store.replace(_record(_auth())); before=store.path.read_bytes()
    service=VertexConfigurationHttp(store=store,recycler=lambda _:None)
    path=tmp_path/'client.json'; path.write_text('{"web":{"client_id":"bad"}}')
    response=await service.execute({'operation':'connect','client_config_path':str(path),'project_id':'company-ai-project','video_location':'us-central1'},lambda:False)
    assert response.status==400 and store.path.read_bytes()==before
    def fail(*args): raise OSError('secret-sentinel')
    monkeypatch.setattr(store,'replace',fail)
    response=await service.execute({'operation':'save','project_id':'company-ai-project','video_location':'us-central1'},lambda:False)
    assert response.status==409 and store.path.read_bytes()==before

@pytest.mark.asyncio
async def test_cancelled_disconnect_waiting_for_mutex_preserves_authorization(tmp_path,monkeypatch):
    from rook.providers import vertex_backend
    store=_store(tmp_path); store.replace(_record(_auth())); before=store.path.read_bytes()
    entered=threading.Event(); released=threading.Event(); revoked=[]
    @contextmanager
    def lock(_):
        entered.set(); released.wait(3); yield
    monkeypatch.setattr(vertex_backend,'_mutation_lock',lock)
    monkeypatch.setattr(vertex_backend,'_revoke_token',lambda token: revoked.append(token) or True)
    service=VertexConfigurationHttp(store=store,recycler=lambda _:None)
    pending=asyncio.create_task(service.execute({'operation':'disconnect'},lambda:False))
    assert await asyncio.to_thread(entered.wait,2)
    pending.cancel(); await asyncio.sleep(0); released.set()
    with pytest.raises(asyncio.CancelledError): await pending
    if service.worker is not None: await service.worker
    await asyncio.sleep(0)
    assert store.path.read_bytes()==before and not revoked and service.worker is None

@pytest.mark.asyncio
async def test_cancel_during_dispatched_revocation_preserves_local_record(tmp_path,monkeypatch):
    from rook.providers import vertex_backend
    auth=_auth(); store=_store(tmp_path)
    store.replace(_record(auth,mode=auth.VertexMode.OAUTH,ciphertext=store.protect_authorized_user(_authorized_user())))
    before=store.path.read_bytes()
    entered=threading.Event(); released=threading.Event(); revoked=[]
    def revoke(token):
        revoked.append(token); entered.set(); released.wait(3); return True
    monkeypatch.setattr(vertex_backend,'_revoke_token',revoke)
    service=VertexConfigurationHttp(store=store,recycler=lambda _:None)
    pending=asyncio.create_task(service.execute({'operation':'disconnect'},lambda:False))
    assert await asyncio.to_thread(entered.wait,2)
    pending.cancel(); await asyncio.sleep(0); released.set()
    with pytest.raises(asyncio.CancelledError): await pending
    assert store.path.read_bytes()==before and len(revoked)==1

from .test_vertex_workforce_store import fixture as workforce_fixture, activate as activate_workforce

@pytest.mark.asyncio
async def test_pending_import_is_not_connected_and_never_refreshes(workforce_fixture, tmp_path):
    import json
    from dataclasses import asdict
    _,store,settings,*_=workforce_fixture
    prior=store.base.replace(_record(_auth()))
    path=tmp_path/'synthetic-firm.json';path.write_text(json.dumps(asdict(settings)))
    service=VertexConfigurationHttp(store=store.base,recycler=lambda _:pytest.fail('No retirement on import'),entra=object())
    response=await service.execute({'operation':'import_firm','settings_path':str(path)},lambda:False)
    data=json.loads(response.body)['data']
    assert response.status==200 and data['active'] is None and data['pending']['label']==settings.label
    assert data['state']=='sign_in_required' and data['legacy_mode']==prior.mode.value
    assert store.snapshot_active()==prior
    body=store.base.path.read_bytes()
    await service.execute({'operation':'firm_status'},lambda:False)
    assert store.base.path.read_bytes()==body

@pytest.mark.asyncio
async def test_disconnect_clears_pending_and_rejects_late_firm_callback(workforce_fixture, monkeypatch):
    import time
    from dataclasses import replace
    from types import SimpleNamespace
    from rook.providers import vertex_backend as backend
    _,store,settings,_,candidate,exchange=workforce_fixture
    ticket=store.import_pending(settings)
    entered,released=threading.Event(),threading.Event()
    def begin(*args,**kwargs):
        entered.set();assert released.wait(3)
        return replace(candidate,operation_deadline=time.monotonic()+30)
    monkeypatch.setattr(backend,'exchange_assertion',lambda *args,**kwargs:pytest.fail('No exchange after disconnect'))
    service=VertexConfigurationHttp(store=store.base,entra=SimpleNamespace(begin=begin),retire=lambda *args:pytest.fail('No late retirement'))
    pending=asyncio.create_task(service.execute({'operation':'connect_firm','pending_revision':ticket.pending_revision,'authorization_epoch':ticket.authorization_epoch},lambda:False))
    assert await asyncio.to_thread(entered.wait,2)
    disconnected=await asyncio.wait_for(service.execute({'operation':'disconnect'},lambda:False),1)
    assert disconnected.status==200 and store.snapshot_active() is None and store.read_pending() is None
    assert service.worker is not None
    released.set();response=await pending
    assert response.status!=200
    assert store.snapshot_active() is None

@pytest.mark.asyncio
async def test_timed_out_check_keeps_worker_slot_until_settled(workforce_fixture, monkeypatch):
    import json
    import time
    from rook.providers.vertex_workforce_contract import FirmSignInCheckResult
    from rook.agent.chat import vertex_configuration_http as route
    _,store,*_=workforce_fixture
    context=activate_workforce(workforce_fixture)
    entered,released=threading.Event(),threading.Event()
    checks=[]
    def held(expected_generation,**kwargs):
        checks.append(kwargs['cancel_check']);entered.set();assert released.wait(3)
        return FirmSignInCheckResult('signed_in',None,expected_generation)
    monkeypatch.setattr(route,'check_firm_sign_in',held)
    service=VertexConfigurationHttp(store=store.base,check_timeout=.1)
    pending=asyncio.create_task(service.execute({'operation':'check_firm_sign_in','authorization_generation':context.generation},lambda:False))
    assert await asyncio.to_thread(entered.wait,2)
    response=await asyncio.wait_for(pending,1)
    data=json.loads(response.body)['data']
    assert data['state']=='service_unavailable' and data['code']=='vertex_token_issuance_timeout'
    assert service.worker is not None
    with pytest.raises(_auth().VertexAuthError):checks[0]()
    busy=await service.execute({'operation':'discard_firm'},lambda:False)
    assert busy.status==409
    disconnected=await service.execute({'operation':'disconnect'},lambda:False)
    assert disconnected.status==200 and store.snapshot_active() is None
    old=service.worker;released.set();await old;await asyncio.sleep(0)
    assert service.worker is None

@pytest.mark.asyncio
async def test_idle_disconnect_clears_pending_firm_settings(workforce_fixture):
    _,store,settings,*_=workforce_fixture
    store.import_pending(settings)
    service=VertexConfigurationHttp(store=store.base,recycler=lambda _:None)
    response=await service.execute({'operation':'disconnect'},lambda:False)
    assert response.status==200 and store.read_pending() is None

@pytest.mark.asyncio
async def test_prepare_reconnect_copies_active_to_pending_without_rotating(workforce_fixture):
    import json
    _,store,*_=workforce_fixture
    context=activate_workforce(workforce_fixture)
    service=VertexConfigurationHttp(store=store.base,recycler=lambda _:pytest.fail('No retirement while preparing reconnect'))
    response=await service.execute({'operation':'prepare_firm_reconnect','authorization_generation':context.generation},lambda:False)
    data=json.loads(response.body)['data']
    assert response.status==200 and data['active_generation']==context.generation and data['pending']==data['active']
    assert store.snapshot_active().generation==context.generation

@pytest.mark.asyncio
async def test_disconnect_during_legacy_browser_does_not_wait_for_provider(tmp_path):
    store=_store(tmp_path);store.replace(_record(_auth()))
    entered,released=threading.Event(),threading.Event()
    def authorize(_):entered.set();assert released.wait(3);return _authorized_user()
    config=tmp_path/'client.json';config.write_text('{"installed":{"client_id":"client","client_secret":"secret"}}')
    service=VertexConfigurationHttp(store=store,recycler=lambda _:None,authorize=authorize)
    pending=asyncio.create_task(service.execute({'operation':'connect','client_config_path':str(config),'project_id':'company-ai-project','video_location':'us-central1'},lambda:False))
    assert await asyncio.to_thread(entered.wait,2)
    try:
        response=await asyncio.wait_for(service.execute({'operation':'disconnect'},lambda:False),.5)
        assert response.status==200 and service.store.read() is None
    finally:released.set()
    response=await pending
    assert response.status!=200 and service.store.read() is None
