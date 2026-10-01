"""Local low-traffic concurrency acceptance; fake provider avoids paid API calls."""
import asyncio
import time
from .test_service import prepare,request
from backend.app.models import Action

async def test_five_matches_prepare_without_blocking_active_battle(store):
    # Use independent identities so every game can prepare concurrently.
    from backend.app.models import LobbyRequest
    async def create_pair(i):
        a,b=f'a{i}',f'b{i}'
        gid=await store.lobby(a,LobbyRequest(request_id=f'create{i}'));g=store.get(gid,a)
        await store.lobby(b,LobbyRequest(request_id=f'join{i}',code=g.code))
        for p in [a,b]: await store.mutate(p,request(g,'start'))
        for p in [a,b]:
            for j in range(2): await store.mutate(p,request(g,'describe',description=f'fire fox {j}'))
        return g
    games=await asyncio.gather(*(create_pair(i) for i in range(5)))
    await asyncio.gather(*(t for g in games for t in list(g.tasks)))
    assert all(g.phase=='ready' for g in games)
    for g in games:
        token=g.ready_version
        for p in g.players: await store.mutate(p,request(g,'ready',ready_version=token))
    started=time.perf_counter()
    await asyncio.gather(*(store.mutate(p,request(g,action=Action(kind='move',index=0))) for g in games for p in g.players))
    latency=time.perf_counter()-started
    assert all(g.turn==2 and g.phase=='actions' for g in games)
    assert latency<1, f'Five local turns took {latency:.3f}s'
