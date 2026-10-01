import asyncio
import copy
import secrets
import pytest
from backend.app.models import Mutation,Action,LobbyRequest
from backend.app.service import GameError
from backend.app.generation import DemoProvider,GenerationFailure
from .conftest import battle_game,Rolls

def request(g,kind='action',**kwargs):
    return Mutation(request_id=kwargs.pop('request_id',secrets.token_hex(8)),game_id=g.id,expected_phase=g.phase,turn=g.turn,attempt_id=g.attempt_id,kind=kind,**kwargs)

async def test_concurrent_actions_once_and_private_snapshots(store):
    g=battle_game(store);store.rng=Rolls(0,1,100,1,100)
    q1=asyncio.Queue(maxsize=1);q2=asyncio.Queue(maxsize=1);g.queues={'a':{q1},'b':{q2}}
    a=request(g,action=Action(kind='move',index=0));b=request(g,action=Action(kind='move',index=1))
    ack=await store.mutate('a',a)
    sa,sb=await q1.get(),await q2.get()
    assert sa['own_pending']=={'kind':'move','index':0} and sb['own_pending'] is None
    assert sb['submission_ack'] is None
    duplicate,other=await asyncio.gather(store.mutate('a',a),store.mutate('b',b))
    assert duplicate==ack and g.turn==2 and len(store.rng.calls)==5
    assert await store.mutate('a',a)==ack and len(store.rng.calls)==5
    assert len([e for e in g.events if e=='Turn 1'])==1
    sa,sb=store.snapshot(g,'a'),store.snapshot(g,'b')
    for key in ['teams','active','events','turn','phase','resolution_order','state_version']: assert sa[key]==sb[key]

async def test_conflicting_duplicate_distinct_and_stale(store):
    g=battle_game(store);req=request(g,action=Action(kind='move',index=0));await store.mutate('a',req)
    for changed,code in [(req.model_copy(update={'action':Action(kind='move',index=1)}),'request_conflict'),(req.model_copy(update={'request_id':'other'}),'already_submitted'),(req.model_copy(update={'request_id':'stale','turn':0}),'stale_request')]:
        with pytest.raises(GameError) as exc: await store.mutate('a',changed)
        assert exc.value.code==code
        if exc.value.snapshot: assert exc.value.snapshot['own_pending']=={'kind':'move','index':0}

@pytest.mark.parametrize('offset',[59.999,60,60.001])
async def test_deadline_boundary(store,clock,offset):
    g=battle_game(store);req=request(g,action=Action(kind='move',index=0));clock.advance(offset)
    if offset<60:
        await store.mutate('a',req);assert g.phase=='actions'
    else:
        with pytest.raises(GameError) as exc: await store.mutate('a',req)
        assert exc.value.code=='stale_request' and g.result['winner'] is None and g.phase=='terminal'

async def test_one_missing_forfeits_and_deadline_not_reset_by_read(store,clock):
    g=battle_game(store);deadline=g.deadline
    await store.mutate('a',request(g,action=Action(kind='move',index=0)))
    clock.advance(20);snap=await store.read(g.id,'a');assert g.deadline==deadline and snap['own_pending']
    clock.advance(40);await store.tick();assert g.result['winner']=='a' and g.result['reason']=='timeout'

@pytest.mark.parametrize('both',[False,True])
async def test_private_replacement_reveal_together(store,both):
    g=battle_game(store);g.phase='replacement';g.required=['a','b'] if both else ['a']
    for p in g.required: g.teams[p][0].current_hp=0
    a=request(g,'replace',action=Action(kind='switch',index=1));b=request(g,'replace',action=Action(kind='switch',index=1))
    await store.mutate('a',a)
    if both:
        assert g.active['a']==0 and store.snapshot(g,'b')['own_pending'] is None
        await store.mutate('b',b)
    assert g.phase=='actions' and g.turn==2 and g.active['a']==1 and g.pending=={}

async def test_one_required_replacement_timeout(store,clock):
    g=battle_game(store);g.phase='replacement';g.required=['a'];g.teams['a'][0].current_hp=0
    clock.advance(60);await store.tick();assert g.result['winner']=='b'

async def test_terminal_retention_ack_cleanup_and_tombstone(store,clock):
    g=battle_game(store);store.finish(g,dict(reason='battle',winner='a'));version=g.terminal_version
    for p in g.players: await store.mutate(p,request(g,'terminal_ack',terminal_version=version))
    clock.advance(299.999);await store.tick();assert (await store.read(g.id,'a'))['result']['winner']=='a'
    clock.advance(.001);await store.tick();assert g.id not in store.games and not g.dedup and not g.teams
    with pytest.raises(GameError) as exc: await store.read(g.id,'a')
    assert exc.value.code=='game_expired'
    clock.advance(86400);await store.tick()
    with pytest.raises(GameError) as exc: store.get(g.id,'a')
    assert exc.value.code=='game_unavailable'

async def test_abandonment_heartbeats_and_progress(store,clock):
    gid=await store.lobby('a',LobbyRequest(request_id='create'));g=store.get(gid,'a')
    clock.advance(299);await store.read(gid,'a');assert g.phase=='lobby'
    await store.lobby('b',LobbyRequest(request_id='join',code=g.code));clock.advance(299);await store.tick();assert g.phase=='lobby'
    clock.advance(1);await store.tick();assert g.result['reason']=='abandonment'

async def test_lobby_dedup_capacity_and_membership(store):
    req=LobbyRequest(request_id='create');gid=await store.lobby('a',req);g=store.get(gid,'a')
    assert await store.lobby('a',req)==gid
    await store.lobby('b',LobbyRequest(request_id='join',code=g.code))
    await store.lobby('b',LobbyRequest(request_id='join2',code=g.code));assert len(g.players)==2
    with pytest.raises(GameError) as exc: await store.lobby('c',LobbyRequest(request_id='join',code=g.code))
    assert exc.value.code=='lobby_full'
    with pytest.raises(GameError) as exc: store.get(gid,'c')
    assert exc.value.code=='not_member'

async def prepare(store):
    gid=await store.lobby('a',LobbyRequest(request_id='create'));g=store.get(gid,'a')
    await store.lobby('b',LobbyRequest(request_id='join',code=g.code))
    a=request(g,'start');b=request(g,'start');await asyncio.gather(store.mutate('a',a),store.mutate('b',b))
    for p in g.players:
        for i in range(2): await store.mutate(p,request(g,'describe',request_id=f'd{i}',description=f'A fire fox {i}'))
    await asyncio.gather(*list(g.tasks))
    return g

async def test_generation_and_concurrent_ready_stable_token(store):
    g=await prepare(store);assert g.phase=='ready' and len(store.images)==1 and g.deadline is None
    token=g.ready_version
    a=request(g,'ready',ready_version=token);b=request(g,'ready',ready_version=token)
    await store.mutate('a',a);assert g.version>token and g.ready_version==token
    await asyncio.gather(store.mutate('a',a),store.mutate('b',b))
    assert g.phase=='actions' and g.turn==1

async def test_generation_failure_clears_loading_preserves_validated_outputs(store):
    class Failed(DemoProvider):
        async def generate(self,step,*args):
            if step=='sprite': raise GenerationFailure(step)
            return await super().generate(step,*args)
    store.generator.provider=Failed();g=await prepare(store)
    assert g.phase=='terminal' and g.result['step']=='sprite' and g.deadline is None
    assert any('stats' in entry and 'moves' in entry for entries in g.generated.values() for entry in entries)

async def test_late_generation_does_not_recreate_deleted_game(store,clock):
    started=asyncio.Event();release=asyncio.Event()
    class Slow(DemoProvider):
        async def generate(self,*args):
            started.set();await release.wait();return await super().generate(*args)
    store.generator.provider=Slow()
    gid=await store.lobby('a',LobbyRequest(request_id='create'));g=store.get(gid,'a')
    await store.lobby('b',LobbyRequest(request_id='join',code=g.code))
    await store.mutate('a',request(g,'start'));await store.mutate('b',request(g,'start'))
    await store.mutate('a',request(g,'describe',request_id='d',description='fire fox'))
    await started.wait();tasks=list(g.tasks)
    clock.advance(300);await store.tick();assert g.phase=='terminal'
    clock.advance(300);await store.tick();release.set();await asyncio.gather(*tasks)
    assert gid not in store.games and not store.images

async def test_slow_queue_coalesces_and_does_not_block(store):
    g=battle_game(store);q=asyncio.Queue(maxsize=1);g.queues={'b':{q}}
    for _ in range(100): store.changed(g);store.publish(g)
    assert q.qsize()==1 and (await q.get())['state_version']==g.version

async def test_public_push_timestamps_are_shared_even_if_wall_clock_changes(store):
    g=battle_game(store);a=asyncio.Queue(maxsize=1);b=asyncio.Queue(maxsize=1)
    g.queues={'a':{a},'b':{b}};wall=iter([1000.,1001.,1002.,1003.]);store.wall=lambda:next(wall)
    store.publish(g);sa,sb=await a.get(),await b.get()
    assert sa['server_time']==sb['server_time']==1000.
    assert sa['deadline']==sb['deadline']==1060.

async def test_read_waiting_on_cleanup_cannot_recover_deleted_snapshot(store,clock):
    g=battle_game(store);store.finish(g,dict(reason='battle',winner='a'));clock.advance(300)
    async with g.lock:
        cleanup=asyncio.create_task(store.tick());await asyncio.sleep(0)
        read=asyncio.create_task(store.read(g.id,'a'));await asyncio.sleep(0)
    await cleanup
    with pytest.raises(GameError) as exc: await read
    assert exc.value.code=='game_expired'

@pytest.mark.parametrize('kind,index',[('switch',0),('switch',2),('switch',1)])
async def test_illegal_switch_does_not_mutate(store,kind,index):
    g=battle_game(store);g.teams['a'][1].current_hp=0;version=g.version
    with pytest.raises(GameError): await store.mutate('a',request(g,action=Action(kind=kind,index=index)))
    assert g.version==version and not g.pending
