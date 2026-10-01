"""Exercise a configured server through two genuine cookie sessions.

Run after starting the backend with a real API key to record live-provider
acceptance without ever exposing that key. No special test endpoints are used.
"""
import argparse
import json
import secrets
import time
from pathlib import Path
import httpx

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://localhost:8000');parser.add_argument('--output',default='docs/live-acceptance.json');args=parser.parse_args()
    with httpx.Client(base_url=args.url,timeout=15) as a,httpx.Client(base_url=args.url,timeout=15) as b:
        provider=a.get('/api/health').raise_for_status().json()['provider']
        if provider!='openai': raise SystemExit('Live acceptance requires GAME_PROVIDER=openai and OPENAI_API_KEY, not demo.')
        players=[c.get('/api/session').raise_for_status().json()['player_id'] for c in [a,b]]
        gid=a.post('/api/lobbies',json={'request_id':secrets.token_hex(8)}).raise_for_status().json()['game_id']
        def read(c): return c.get(f'/api/games/{gid}').raise_for_status().json()
        def mutate(c,kind,**extra):
            s=read(c);payload=dict(request_id=secrets.token_hex(8),game_id=gid,expected_phase=s['phase'],turn=s['turn'],attempt_id=s['attempt_id'],kind=kind,**extra)
            return c.post(f'/api/games/{gid}/mutations',json=payload).raise_for_status().json()
        code=read(a)['code'];b.post('/api/lobbies',json={'request_id':secrets.token_hex(8),'code':code}).raise_for_status()
        for c in [a,b]: mutate(c,'start')
        for c,descriptions in [(a,['A fierce sapphire fox with water powers','A gentle leaf guardian with a round cat head']),(b,['A fiery horned lizard with tiny bat wings','A stone cat with a curved tail'])]:
            for description in descriptions: mutate(c,'describe',description=description)
        started=time.monotonic()
        while read(a)['phase']=='preparation':
            if time.monotonic()-started>300: raise SystemExit('Preparation exceeded its bounded acceptance window.')
            time.sleep(.25)
        s=read(a)
        if s['phase']!='ready': raise SystemExit(s.get('result',{}).get('message','Generation failed'))
        generation_seconds=time.monotonic()-started
        for team in s['teams'].values():
            for creature in team: assert a.get(creature['sprite']).raise_for_status().headers['content-type']=='image/png'
        battle_started=time.monotonic()
        for c in [a,b]: mutate(c,'ready',ready_version=s['ready_version'])
        for c in [a,b]: mutate(c,'action',action={'kind':'switch','index':1})
        replacement=False
        for _ in range(500):
            s=read(a)
            if s['phase']=='terminal': break
            if s['phase']=='replacement':
                replacement=True
                for c,p in zip([a,b],players):
                    if p in s['required']:
                        index=next(i for i,mon in enumerate(s['teams'][p]) if mon['current_hp'] and i!=s['active'][p])
                        mutate(c,'replace',action={'kind':'switch','index':index})
            else:
                for c,p in zip([a,b],players):
                    mon=s['teams'][p][s['active'][p]]
                    index=next(i for i,m in enumerate(mon['moves']) if m['power'])
                    mutate(c,'action',action={'kind':'move','index':index})
        else: raise SystemExit('Match did not terminate after 500 turns; inspect generated move balance.')
        assert replacement,'Live match finished without forced replacement; repeat to cover that acceptance requirement.'
        for c in [a,b]: mutate(c,'terminal_ack',terminal_version=s['terminal_version'])
        report=dict(provider=provider,creatures=4,turns=s['turn'],forced_replacement=replacement,result=s['result'],generation_seconds=round(generation_seconds,3),battle_seconds=round(time.monotonic()-battle_started,3),checked_at=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
        output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n')
        print(f'PASS: live provider, four sprites, switching, forced replacement, terminal result. Evidence: {output}')

if __name__=='__main__': main()
