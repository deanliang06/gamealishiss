import secrets
import time
import pytest
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.generation import DemoProvider

def mutation(state,kind,**kwargs):
    return dict(request_id=secrets.token_hex(4),game_id=state['game_id'],expected_phase=state['phase'],turn=state['turn'],attempt_id=state['attempt_id'],kind=kind,**kwargs)

def test_auth_origin_http_websocket_and_lobby():
    with TestClient(create_app(DemoProvider())) as client:
        assert client.post('/api/lobbies',json={'request_id':'create'}).status_code==401
        a=client.get('/api/session').json()['player_id'];cookie_a=client.cookies.get('session')
        assert client.get('/api/session').json()['player_id']==a
        assert client.post('/api/lobbies',json={'request_id':'create'},headers={'origin':'https://evil.example'}).status_code==403
        gid=client.post('/api/lobbies',json={'request_id':'create'}).json()['game_id']
        state=client.get(f'/api/games/{gid}').json()
        with client.websocket_connect(f'/api/games/{gid}/ws') as ws:
            assert ws.receive_json()['game_id']==gid
            ws.send_json({'kind':'resync'});assert ws.receive_json()['players']==[a]
        client.cookies.clear();b=client.get('/api/session').json()['player_id'];cookie_b=client.cookies.get('session')
        assert client.get(f'/api/games/{gid}').status_code==403
        with client.websocket_connect(f'/api/games/{gid}/ws') as ws:
            assert ws.receive_json()['error']['code']=='not_member'
        assert client.post('/api/lobbies',json={'request_id':'join','code':state['code']}).status_code==200
        client.cookies.set('session',cookie_a)
        state=client.get(f'/api/games/{gid}').json()
        assert client.post(f'/api/games/{gid}/mutations',json=mutation(state,'start')).status_code==200
        client.cookies.set('session',cookie_b);state=client.get(f'/api/games/{gid}').json()
        assert client.post(f'/api/games/{gid}/mutations',json=mutation(state,'start')).status_code==200
        for cookie in [cookie_a,cookie_b]:
            client.cookies.set('session',cookie)
            for i in range(2):
                state=client.get(f'/api/games/{gid}').json()
                assert client.post(f'/api/games/{gid}/mutations',json=mutation(state,'describe',description='A fire fox')).status_code==200
        for _ in range(100):
            state=client.get(f'/api/games/{gid}').json()
            if state['phase']=='ready': break
            time.sleep(.02)
        assert state['phase']=='ready'
        sprite=state['teams'][a][0]['sprite']
        assert client.get(sprite).headers['content-type']=='image/png'
        token=state['ready_version']
        for cookie in [cookie_a,cookie_b]:
            client.cookies.set('session',cookie);state=client.get(f'/api/games/{gid}').json()
            assert client.post(f'/api/games/{gid}/mutations',json=mutation(state,'ready',ready_version=token)).status_code==200
        state=client.get(f'/api/games/{gid}').json();assert state['phase']=='actions'
        client.cookies.set('session',cookie_a)
        action=mutation(state,'action',action={'kind':'move','index':0})
        ack=client.post(f'/api/games/{gid}/mutations',json=action).json()
        assert client.post(f'/api/games/{gid}/mutations',json=action).json()==ack
        client.cookies.set('session',cookie_b)
        with client.websocket_connect(f'/api/games/{gid}/ws') as ws:
            snapshot=ws.receive_json();assert snapshot['own_pending'] is None and snapshot['submission_ack']['request_id']!=ack['request_id']
        client.cookies.clear();client.get('/api/session')
        assert client.get(sprite).status_code==403

def test_restart_unavailable_and_strict_wire_validation():
    with TestClient(create_app(DemoProvider())) as c:
        c.get('/api/session');old_cookie=c.cookies.get('session');gid=c.post('/api/lobbies',json={'request_id':'r'}).json()['game_id']
        assert c.post('/api/lobbies',json={'request_id':'r','player_id':'forged'}).status_code==422
    with TestClient(create_app(DemoProvider())) as c:
        c.cookies.set('session',old_cookie)
        assert c.get(f'/api/games/{gid}').json()['error']['code']=='game_unavailable'
        with c.websocket_connect(f'/api/games/{gid}/ws') as ws:
            assert ws.receive_json()['error']['code']=='game_unavailable'

def test_missing_key_fails_startup(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False);monkeypatch.delenv('GAME_PROVIDER',raising=False)
    with pytest.raises(RuntimeError,match='OPENAI_API_KEY'):
        with TestClient(create_app()): pass
