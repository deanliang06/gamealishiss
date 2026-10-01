from backend.app.contracts import Snapshot
from .conftest import battle_game
from .test_service import prepare

async def test_websocket_and_http_snapshots_conform_to_shared_schema(store):
    g=battle_game(store)
    for p in g.players:
        raw=store.snapshot(g,p);parsed=Snapshot.model_validate(raw)
        assert parsed.model_dump(exclude_unset=True)==raw
    store.finish(g,{'reason':'battle','winner':'a'})
    raw=store.snapshot(g,'a');assert Snapshot.model_validate(raw).model_dump(exclude_unset=True)==raw
    g=await prepare(store)
    raw=store.snapshot(g,'a');assert Snapshot.model_validate(raw).model_dump(exclude_unset=True)==raw
