import asyncio
import json
import httpx
import pytest
from openai import AsyncOpenAI
from backend.app.generation import OpenAIProvider,Generator,GenerationFailure
from backend.app.models import Stats
from backend.app.sprites import Renderer

VALID=dict(hp=80,attack=80,defense=80,special_attack=80,special_defense=80,speed=80)
def result(content=None,status='completed'):
    return dict(id='resp_test',object='response',created_at=1700000000,status=status,model='gpt-4.1-mini',output=[dict(type='message',id='msg_test',role='assistant',status='completed',content=content or [dict(type='output_text',text=json.dumps(VALID),annotations=[])])])

def provider(monkeypatch,handler):
    monkeypatch.setenv('OPENAI_API_KEY','test-not-a-real-key')
    p=OpenAIProvider()
    p.client=AsyncOpenAI(api_key='test-not-a-real-key',max_retries=0,http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    return p

async def test_real_sdk_structured_request_contract(monkeypatch):
    requests=[]
    def handler(request):
        requests.append(json.loads(request.content));return httpx.Response(200,json=result())
    p=provider(monkeypatch,handler)
    output=await Generator(p,Renderer()).step('stats',Stats,{'description':'A fire fox'})
    assert output.hp==80 and len(requests)==1
    fmt=requests[0]['text']['format'];assert fmt['type']=='json_schema' and fmt['strict'] is True
    assert fmt['schema']['additionalProperties'] is False and len(fmt['schema']['required'])==6
    assert 'A fire fox' in requests[0]['input'][1]['content']
    await p.close()

@pytest.mark.parametrize('kind',['refusal','incomplete','rate_limit','transport','server_error'])
async def test_provider_failures_are_bounded_and_safe(monkeypatch,kind):
    calls=[]
    def handler(request):
        calls.append(request)
        if kind=='rate_limit': return httpx.Response(429,json={'error':{'message':'secret provider error','type':'rate_limit_error'}})
        if kind=='transport': raise httpx.ConnectError('secret transport detail',request=request)
        if kind=='server_error': return httpx.Response(500,json={'error':{'message':'secret internal error'}})
        if kind=='incomplete': return httpx.Response(200,json=result(status='incomplete'))
        return httpx.Response(200,json=result([dict(type='refusal',refusal='secret refusal detail')]))
    p=provider(monkeypatch,handler)
    with pytest.raises(GenerationFailure) as exc: await p.generate('stats',Stats,{'description':'fox'},None,None)
    assert len(calls)==(2 if kind in ('rate_limit','transport') else 1)
    assert 'secret' not in str(exc.value)
    await p.close()

async def test_provider_timeout_clears_step():
    class Hanging:
        async def generate(self,*args): await asyncio.Event().wait()
    with pytest.raises(GenerationFailure,match='timeout'):
        await Generator(Hanging(),Renderer(),call_timeout=.001).step('stats',Stats,{'description':'fox'})

async def test_malformed_json_has_four_correction_attempts(monkeypatch):
    calls=[]
    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200,json=result([dict(type='output_text',text='not json',annotations=[])]))
    p=provider(monkeypatch,handler)
    with pytest.raises(GenerationFailure): await Generator(p,Renderer()).step('stats',Stats,{'description':'fox'})
    assert len(calls)==4
    prompt=json.loads(calls[1]['input'][1]['content']);assert prompt['previous_output']=='not json' and prompt['validation_errors']
    await p.close()
