import asyncio
import pytest
from backend.app.generation import Generator,DemoProvider,GenerationFailure
from backend.app.models import Stats,MoveOutput,SpriteSpec
from backend.app.sprites import Renderer

@pytest.mark.parametrize('step,schema',[('stats',Stats),('moves',MoveOutput),('sprite',SpriteSpec)])
@pytest.mark.parametrize('failures',[0,1,2,3,4])
async def test_retry_scope_and_context(step,schema,failures):
    calls=[]
    class Provider(DemoProvider):
        async def generate(self,s,sc,context,previous,errors):
            calls.append((context.copy(),previous,errors))
            if len(calls)<=failures: return {'invalid':len(calls)}
            return await super().generate(s,sc,context,previous,errors)
    gen=Generator(Provider(),Renderer());context={'description':'A fire fox'}
    if failures==4:
        with pytest.raises(GenerationFailure) as exc: await gen.step(step,schema,context)
        assert exc.value.step==step
    else: assert isinstance(await gen.step(step,schema,context),schema)
    assert len(calls)==min(failures+1,4)
    for i,(ctx,previous,errors) in enumerate(calls):
        assert ctx==context
        if i: assert previous=={'invalid':i} and errors
        else: assert previous is None and errors is None

async def test_backend_sprite_rejection_retried():
    class Provider(DemoProvider):
        def __init__(self): self.calls=0
        async def generate(self,*args):
            self.calls+=1
            value=await super().generate(*args)
            if self.calls==1: value['silhouette']['wings']='paired_small_bat'
            return value
    p=Provider();await Generator(p,Renderer()).step('sprite',SpriteSpec,{'description':'fox'})
    assert p.calls==2

async def test_partial_outputs_and_dependent_context():
    seen=[];progress=[]
    class Provider(DemoProvider):
        async def generate(self,step,schema,context,*args):
            seen.append((step,context.copy()))
            if step=='sprite': raise GenerationFailure(step,'refusal')
            return await super().generate(step,schema,context,*args)
    async def record(step,data): progress.append(step)
    with pytest.raises(GenerationFailure): await Generator(Provider(),Renderer()).creature('fox',record)
    assert progress==['stats','moves'] and 'stats' in seen[1][1] and 'types' in seen[2][1]

async def test_provider_concurrency_limit():
    class Provider(DemoProvider):
        def __init__(self): self.current=0;self.maximum=0
        async def generate(self,*args):
            self.current+=1;self.maximum=max(self.maximum,self.current)
            try: return await super().generate(*args)
            finally: self.current-=1
    p=Provider();gen=Generator(p,Renderer(),2)
    await asyncio.gather(*(gen.step('stats',Stats,{'description':'fox'}) for _ in range(10)))
    assert p.maximum==2
