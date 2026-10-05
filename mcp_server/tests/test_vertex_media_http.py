from dataclasses import asdict
from types import SimpleNamespace
import pytest
from aiohttp.test_utils import TestClient, TestServer
from rook.agent.chat.server import create_chat_app
from .test_vertex_token_lease import _record, _Store, _Clock, _Refresher, _service, MODEL, GENERATION_B

class Manager:
    async def shutdown(self): pass

@pytest.mark.asyncio
@pytest.mark.parametrize('method,headers,body,status', [
    ('POST',{}, {},403), ('POST',{'X-Rook-Session':'wrong'}, {},403),
    ('POST',{'X-Rook-Session':'nonce','Origin':'https://app.rook.invalid'}, {},403),
    ('OPTIONS',{'X-Rook-Session':'nonce'}, {},405), ('GET',{'X-Rook-Session':'nonce'}, {},405),
    ('POST',{'X-Rook-Session':'nonce'}, {'operation':'acquire','model':MODEL,'location':'global','expected_binding':None,'extra':1},400),
    ('POST',{'X-Rook-Session':'nonce'}, {'operation':'validate','model':MODEL,'location':'global','expected_binding':None},400),
])
async def test_internal_token_admission(method,headers,body,status):
    clock=_Clock(); store=_Store(_record()); refresher=_Refresher(clock)
    client=TestClient(TestServer(create_chat_app(Manager(),expected_nonce='nonce',vertex_token_service=_service(store,clock,refresher))))
    async with client:
        response=await client.request(method,'/internal/providers/vertex/access-token',headers=headers,json=body)
        assert response.status==status
        assert response.headers['Cache-Control']=='no-store'
        assert 'Access-Control-Allow-Origin' not in response.headers
        assert refresher.calls==[]

@pytest.mark.asyncio
async def test_token_route_oversized_body_and_rotated_followup_are_bounded():
    clock=_Clock(); store=_Store(_record()); refresher=_Refresher(clock)
    service=_service(store,clock,refresher)
    client=TestClient(TestServer(create_chat_app(Manager(),expected_nonce='nonce',vertex_token_service=service)))
    headers={'X-Rook-Session':'nonce'}
    async with client:
        response=await client.post('/internal/providers/vertex/access-token',headers=headers,data='x'*8193)
        assert response.status==400 and response.headers['Cache-Control']=='no-store'
        body={'operation':'acquire','model':MODEL,'location':'global','expected_binding':None}
        response=await client.post('/internal/providers/vertex/access-token',headers=headers,json=body)
        data=(await response.json())['data']
        assert data['binding']['model_id']==MODEL
        body['operation']='validate'; body['expected_binding']=data['binding']
        response=await client.post('/internal/providers/vertex/access-token',headers=headers,json=body)
        assert (await response.json())['data']=={'validated':True}
        assert len(refresher.calls)==1
        store.record=_record(generation=GENERATION_B)
        body['operation']='acquire'
        response=await client.post('/internal/providers/vertex/access-token',headers=headers,json=body)
        assert response.status==409
        assert len(refresher.calls)==1
        assert 'short-lived-token' not in await response.text()
