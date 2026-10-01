"""Measure five local games, including active turns during other generation."""
import asyncio
import json
import platform
import secrets
import time
from pathlib import Path
from backend.app.generation import Generator,DemoProvider
from backend.app.sprites import Renderer
from backend.app.service import Store
from backend.app.models import LobbyRequest,Mutation,Action

async def main():
    store=Store(Generator(DemoProvider(),Renderer()))
    async def mutation(g,p,kind,**fields):
        return await store.mutate(p,Mutation(request_id=secrets.token_hex(8),game_id=g.id,expected_phase=g.phase,turn=g.turn,attempt_id=g.attempt_id,kind=kind,**fields))
    async def create(i):
        a,b=f'a{i}',f'b{i}';gid=await store.lobby(a,LobbyRequest(request_id=secrets.token_hex(8)))
        g=store.get(gid,a);await store.lobby(b,LobbyRequest(request_id=secrets.token_hex(8),code=g.code))
        for p in g.players: await mutation(g,p,'start')
        for p in g.players:
            for j in range(2): await mutation(g,p,'describe',description=f'fire fox {j}')
        return g
    begin=time.perf_counter();games=await asyncio.gather(*(create(i) for i in range(5)))
    await asyncio.gather(*(t for g in games for t in list(g.tasks)))
    generation=time.perf_counter()-begin
    for g in games:
        for p in g.players: await mutation(g,p,'ready',ready_version=g.ready_version)
    async def turn(g):
        start=time.perf_counter()
        await asyncio.gather(*(mutation(g,p,'action',action=Action(kind='move',index=0)) for p in g.players))
        return (time.perf_counter()-start)*1000
    turns=await asyncio.gather(*(turn(g) for g in games))
    # Start another preparing game while an existing game's next turn commits.
    extra=await create(5);interleaved=await turn(games[0]);await asyncio.gather(*list(extra.tasks))
    report=dict(host=platform.platform(),python=platform.python_version(),provider='explicit offline demo',games=5,players=10,generation_concurrency=3,preparation_seconds=round(generation,3),turn_ms=[round(x,3) for x in turns],turn_during_other_generation_ms=round(interleaved,3),scope='Local service process only; excludes remote provider and network latency.')
    path=Path('docs/benchmark.json');path.write_text(json.dumps(report,indent=2)+'\n');await store.close();print(json.dumps(report,indent=2))

if __name__=='__main__': asyncio.run(main())
