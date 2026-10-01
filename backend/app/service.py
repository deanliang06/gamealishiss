"""Single-process game store. Every mutation is serialized per game."""
import asyncio
import copy
import json
import random
import secrets
import time
from dataclasses import dataclass, field
from .battle import Creature, resolve
from .generation import GenerationFailure

class GameError(Exception):
    def __init__(self, code, message, status=409, snapshot=None):
        self.code,self.message,self.status,self.snapshot=code,message,status,snapshot

@dataclass
class Game:
    id: str
    code: str
    players: list[str]
    progress_at: float
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    phase: str = 'lobby'
    turn: int = 0
    version: int = 1
    attempt_id: str = field(default_factory=lambda: secrets.token_hex(12))
    ready_version: int | None = None
    start: set = field(default_factory=set)
    ready: set = field(default_factory=set)
    descriptions: dict = field(default_factory=dict)
    generated: dict = field(default_factory=dict)
    teams: dict = field(default_factory=dict)
    active: dict = field(default_factory=dict)
    pending: dict = field(default_factory=dict)
    required: list = field(default_factory=list)
    deadline: float | None = None
    result: dict | None = None
    terminal_at: float | None = None
    terminal_version: int | None = None
    terminal_acks: set = field(default_factory=set)
    dedup: dict = field(default_factory=dict)
    last_ack: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    resolution_order: list = field(default_factory=list)
    tasks: set = field(default_factory=set)
    queues: dict = field(default_factory=dict)
    deleted: bool = False

class Store:
    def __init__(self,generator,clock=time.monotonic,wall=time.time,rng=None):
        self.generator,self.clock,self.wall=generator,clock,wall
        self.rng=rng or random.SystemRandom()
        self.games={};self.codes={};self.expired={};self.lobby_dedup={};self.images={}
        self.registry_lock=asyncio.Lock()
        self.boot=secrets.token_hex(4)

    def get(self,gid,player):
        game=self.games.get(gid)
        if not game or game.deleted:
            expired=gid in self.expired
            raise GameError('game_expired' if expired else 'game_unavailable','This game expired.' if expired else 'This game is unavailable. Return to the lobby.',410)
        if player not in game.players:
            raise GameError('not_member','You are not a member of this game.',403)
        return game

    def snapshot(self,g,player,clock_now=None,wall_now=None):
        clock_now=self.clock() if clock_now is None else clock_now
        wall_now=self.wall() if wall_now is None else wall_now
        remaining=max(0,g.deadline-clock_now) if g.deadline is not None else None
        return dict(game_id=g.id,code=g.code,player_id=player,players=g.players[:],phase=g.phase,turn=g.turn,state_version=g.version,
                    attempt_id=g.attempt_id,ready_version=g.ready_version,start_ready=list(g.start),ready=list(g.ready),
                    description_count=len(g.descriptions.get(player,[])),generation=copy.deepcopy(g.generated),
                    teams={p:[c.public() if c else None for c in team] for p,team in g.teams.items()},active=g.active.copy(),
                    required=g.required[:],own_pending=g.pending[player].model_dump() if player in g.pending else None,
                    submission_ack=copy.deepcopy(g.last_ack.get(player)),deadline=wall_now+remaining if remaining is not None else None,
                    server_time=wall_now,result=copy.deepcopy(g.result),terminal_version=g.terminal_version,
                    terminal_acks=list(g.terminal_acks),events=g.events[:],resolution_order=g.resolution_order[:])

    def publish(self,g):
        # Bounded queues coalesce snapshots; no socket I/O while holding a lock.
        clock_now,wall_now=self.clock(),self.wall()
        for player,queues in g.queues.items():
            for queue in queues:
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(self.snapshot(g,player,clock_now,wall_now))

    def changed(self,g,progress=False):
        g.version+=1
        if progress: g.progress_at=self.clock()

    def finish(self,g,result):
        if g.phase=='terminal': return
        g.phase='terminal';g.result=result;g.deadline=None;g.required=[];g.pending={}
        self.changed(g);g.terminal_at=self.clock();g.terminal_version=g.version

    def begin_actions(self,g):
        g.phase='actions';g.turn+=1;g.pending={};g.required=g.players[:];g.deadline=self.clock()+60

    def expire(self,g):
        if g.phase in ('actions','replacement') and self.clock()>=g.deadline:
            missing=[p for p in g.required if p not in g.pending]
            if missing:
                winner=next((p for p in g.players if p not in missing),None) if len(missing)==1 else None
                self.finish(g,dict(reason='timeout',winner=winner,message='Action deadline expired.'))
        elif g.phase in ('lobby','preparation','ready') and self.clock()-g.progress_at>=300:
            self.finish(g,dict(reason='abandonment',winner=None,message='Preparation was inactive for five minutes.'))

    async def lobby(self,player,request):
        async with self.registry_lock:
            key=(player,request.request_id);payload=request.model_dump_json()
            if key in self.lobby_dedup:
                old,out,_=self.lobby_dedup[key]
                if old!=payload: raise GameError('request_conflict','Request ID was reused with another payload.')
                self.get(out,player)
                return out
            if request.code:
                gid=self.codes.get(request.code.upper())
                if not gid: raise GameError('invalid_code','Lobby code is invalid or expired.',404)
                g=self.games[gid]
                async with g.lock:
                    self.expire(g)
                    if g.phase!='lobby':
                        self.publish(g)
                        raise GameError('lobby_closed','This lobby has already started or expired.')
                    if player not in g.players:
                        if len(g.players)==2: raise GameError('lobby_full','This lobby already has two players.')
                        g.players.append(player);self.changed(g,True)
                    self.publish(g)
            else:
                code=''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(6))
                while code in self.codes:
                    code=''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(6))
                gid=f'{self.boot}-{secrets.token_hex(12)}'
                self.games[gid]=Game(gid,code,[player],self.clock());self.codes[code]=gid
            self.lobby_dedup[key]=(payload,gid,self.clock())
            return gid

    async def read(self,gid,player):
        g=self.get(gid,player)
        async with g.lock:
            if g.deleted: raise GameError('game_expired','This game expired.',410)
            self.expire(g);self.publish(g)
            return self.snapshot(g,player)

    async def mutate(self,player,req):
        g=self.get(req.game_id,player)
        async with g.lock:
            if g.deleted: raise GameError('game_expired','This game expired.',410)
            payload=req.model_dump_json();key=(player,req.request_id)
            if key in g.dedup:
                old,ack=g.dedup[key]
                if old!=payload: raise GameError('request_conflict','Request ID was reused with another payload.',snapshot=self.snapshot(g,player))
                return copy.deepcopy(ack)
            self.expire(g)
            if (req.expected_phase,req.turn,req.attempt_id)!=(g.phase,g.turn,g.attempt_id):
                self.publish(g)
                raise GameError('stale_request','State changed. Please retry with the latest state.',snapshot=self.snapshot(g,player))
            if req.kind=='start' and g.phase=='lobby':
                if len(g.players)!=2: raise GameError('need_opponent','Wait for an opponent.')
                if player in g.start: raise GameError('already_submitted','You already requested start.')
                g.start.add(player)
                if len(g.start)==2:
                    g.phase='preparation'
                    g.descriptions={p:[] for p in g.players};g.generated={p:[{},{}] for p in g.players}
                self.changed(g,True)
            elif req.kind=='describe' and g.phase=='preparation':
                text=(req.description or '').strip()
                if not 3<=len(text)<=1000: raise GameError('invalid_description','Use between 3 and 1000 characters.')
                if len(g.descriptions[player])>=2: raise GameError('already_submitted','Both descriptions are locked.')
                index=len(g.descriptions[player]);g.descriptions[player].append(text)
                self.changed(g,True)
                task=asyncio.create_task(self.generate(g,player,index,text,g.attempt_id))
                g.tasks.add(task);task.add_done_callback(g.tasks.discard)
            elif req.kind=='ready' and g.phase=='ready':
                if req.ready_version!=g.ready_version: raise GameError('stale_ready','Readiness token is stale.',snapshot=self.snapshot(g,player))
                if player in g.ready: raise GameError('already_submitted','You are already ready.')
                g.ready.add(player);self.changed(g,True)
                if len(g.ready)==2: self.begin_actions(g)
            elif req.kind in ('action','replace') and g.phase in ('actions','replacement'):
                if req.kind!=('action' if g.phase=='actions' else 'replace'): raise GameError('invalid_action','Incorrect action for this phase.')
                action=req.action
                if player not in g.required or not action: raise GameError('invalid_action','No action is required from you.')
                if player in g.pending: raise GameError('already_submitted','Your choice is already locked.')
                team=g.teams[player]
                if action.kind=='switch':
                    if action.index>=len(team) or action.index==g.active[player] or not team[action.index].current_hp:
                        raise GameError('invalid_switch','Choose your conscious reserve.')
                elif g.phase=='replacement' or team[g.active[player]].current_hp==0:
                    raise GameError('invalid_action','Choose a replacement.')
                g.pending[player]=action;self.changed(g)
                if all(p in g.pending for p in g.required):
                    if g.phase=='replacement':
                        for p,a in g.pending.items(): g.active[p]=a.index
                        self.begin_actions(g)
                    else:
                        g.phase='resolving'
                        events,order,required,result=resolve(g.teams,g.active,g.pending,self.rng)
                        g.events=(g.events+[f'Turn {g.turn}',*events])[-200:];g.resolution_order=order
                        g.pending={}
                        if result: self.finish(g,result)
                        elif required:
                            g.phase='replacement';g.required=required;g.deadline=self.clock()+60
                        else: self.begin_actions(g)
            elif req.kind=='terminal_ack' and g.phase=='terminal':
                if req.terminal_version!=g.terminal_version: raise GameError('stale_terminal','Terminal version is stale.')
                g.terminal_acks.add(player);self.changed(g)
            elif req.kind=='leave' and g.phase!='terminal':
                winner=next((p for p in g.players if p!=player),None) if g.phase in ('actions','replacement') else None
                self.finish(g,dict(reason='forfeit' if winner else 'abandonment',winner=winner,message='A player left the game.'))
            else:
                raise GameError('invalid_phase','This operation is not allowed in this phase.',snapshot=self.snapshot(g,player))
            ack=dict(request_id=req.request_id,accepted=True,state_version=g.version)
            g.last_ack[player]=ack;g.dedup[key]=(payload,ack)
            self.publish(g)
            return copy.deepcopy(ack)

    async def generate(self,g,player,index,text,attempt):
        def current(): return not g.deleted and self.games.get(g.id) is g and g.phase=='preparation' and g.attempt_id==attempt
        async def progress(step,value):
            async with g.lock:
                self.expire(g)
                if not current():
                    self.publish(g)
                    raise asyncio.CancelledError
                g.generated[player][index][step]=value;self.changed(g,True);self.publish(g)
        try:
            stats,moves,spec,key,png=await asyncio.wait_for(self.generator.creature(text,progress),280)
            async with g.lock:
                self.expire(g)
                if not current():
                    self.publish(g)
                    return
                self.images[key]=png
                team=g.teams.setdefault(player,[None,None])
                team[index]=Creature(f'{player}-{index}',text[:40],stats,moves,f'/api/sprites/{key}.png',spec.model_dump())
                g.active[player]=0
                self.changed(g,True)
                if all(p in g.teams and all(g.teams[p]) for p in g.players):
                    g.phase='ready';g.ready_version=g.version
                self.publish(g)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            async with g.lock:
                if not current(): return
                message=str(exc) if isinstance(exc,GenerationFailure) else 'Creature generation could not finish. Please start a new lobby.'
                self.finish(g,dict(reason='generation_failure',winner=None,message=message,step=exc.step if isinstance(exc,GenerationFailure) else 'generation'))
                self.publish(g)

    async def tick(self):
        for g in list(self.games.values()):
            async with g.lock:
                version=g.version;self.expire(g)
                if g.version!=version: self.publish(g)
                if g.terminal_at is not None and self.clock()-g.terminal_at>=300:
                    g.deleted=True;self.games.pop(g.id,None);self.codes.pop(g.code,None);self.expired[g.id]=self.clock()
                    for task in list(g.tasks): task.cancel()
                    for queues in g.queues.values():
                        for queue in queues:
                            if queue.full(): queue.get_nowait()
                            queue.put_nowait({'error':{'code':'game_expired','message':'This game expired.'}})
                    g.teams.clear();g.generated.clear();g.descriptions.clear();g.dedup.clear();g.last_ack.clear()
        # Tombstones survive for 24 hours; unknown IDs then return unavailable.
        self.expired={k:v for k,v in self.expired.items() if self.clock()-v<86400}
        self.lobby_dedup={k:v for k,v in self.lobby_dedup.items() if v[1] in self.games}
        # PNGs survive only while referenced by a retained game.
        used={c.sprite.rsplit('/',1)[-1][:-4] for g in self.games.values() for team in g.teams.values() for c in team if c}
        self.images={k:v for k,v in self.images.items() if k in used}

    async def close(self):
        tasks=[t for g in self.games.values() for t in g.tasks]
        for t in tasks: t.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        await self.generator.provider.close()
