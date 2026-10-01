import asyncio
import hashlib
import hmac
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response, FileResponse
from dotenv import load_dotenv
from .models import LobbyRequest, Mutation
from .generation import Generator, OpenAIProvider, DemoProvider
from .sprites import Renderer, legal_specs
from .service import Store, GameError
from .contracts import Snapshot, Acknowledgment

load_dotenv()

def create_app(provider=None,clock=time.monotonic,wall=time.time):
    secret=os.getenv('SESSION_SECRET') or secrets.token_hex(32)
    allowed={origin.strip() for origin in os.getenv('ALLOWED_ORIGINS','http://localhost:5173,http://localhost:8000').split(',') if origin.strip()}
    cookie_secure=os.getenv('COOKIE_SECURE','false').lower()=='true'

    def identity(token):
        try:
            player,stamp,signature=token.split('.')
            payload=f'{player}.{stamp}'
            expected=hmac.new(secret.encode(),payload.encode(),hashlib.sha256).hexdigest()
            if len(player)!=32 or not hmac.compare_digest(signature,expected) or not 0<=time.time()-int(stamp)<30*86400:
                return None
            return player
        except (AttributeError,ValueError): return None

    def auth(request):
        player=identity(request.cookies.get('session'))
        if not player: raise GameError('unauthenticated','Open the lobby to create a session.',401)
        return player

    @asynccontextmanager
    async def lifespan(app):
        selected=provider or (DemoProvider() if os.getenv('GAME_PROVIDER')=='demo' else OpenAIProvider())
        renderer=Renderer()
        for spec in legal_specs(include_expressions=True): renderer.render(spec)
        concurrency=int(os.getenv('GENERATION_CONCURRENCY','3'))
        if not 1<=concurrency<=10: raise RuntimeError('GENERATION_CONCURRENCY must be between 1 and 10')
        app.state.store=Store(Generator(selected,renderer,concurrency),clock,wall)
        async def maintenance():
            while True:
                await asyncio.sleep(.2)
                await app.state.store.tick()
        timer=asyncio.create_task(maintenance())
        yield
        timer.cancel();await asyncio.gather(timer,return_exceptions=True)
        await app.state.store.close()

    app=FastAPI(title='Gamealishiss',lifespan=lifespan)

    @app.exception_handler(GameError)
    async def handle_error(request,exc):
        return JSONResponse({'error':dict(code=exc.code,message=exc.message),'snapshot':exc.snapshot},status_code=exc.status)

    @app.middleware('http')
    async def origin_guard(request,call_next):
        if request.method not in ('GET','HEAD','OPTIONS') and request.headers.get('origin') and request.headers['origin'] not in allowed:
            return JSONResponse({'error':{'code':'invalid_origin','message':'Origin is not allowed.'}},status_code=403)
        return await call_next(request)

    @app.get('/api/session')
    async def session(request:Request):
        player=identity(request.cookies.get('session'))
        response=JSONResponse({'player_id':player})
        if not player:
            player=secrets.token_hex(16);payload=f'{player}.{int(time.time())}'
            token=payload+'.'+hmac.new(secret.encode(),payload.encode(),hashlib.sha256).hexdigest()
            response=JSONResponse({'player_id':player})
            response.set_cookie('session',token,httponly=True,secure=cookie_secure,samesite='lax',max_age=30*86400)
        response.headers['Cache-Control']='no-store'
        return response

    @app.get('/api/health')
    async def health(): return {'ok':True,'provider':'demo' if isinstance(app.state.store.generator.provider,DemoProvider) else 'openai'}

    @app.post('/api/lobbies')
    async def lobby(req:LobbyRequest,request:Request):
        return {'game_id':await app.state.store.lobby(auth(request),req)}

    @app.get('/api/games/{gid}',response_model=Snapshot,response_model_exclude_unset=True)
    async def game(gid:str,request:Request):
        if gid not in app.state.store.games: app.state.store.get(gid,'')
        return await app.state.store.read(gid,auth(request))

    @app.post('/api/games/{gid}/mutations',response_model=Acknowledgment)
    async def mutate(gid:str,req:Mutation,request:Request):
        if req.game_id!=gid: raise GameError('game_mismatch','Payload game ID must match URL.',422)
        return await app.state.store.mutate(auth(request),req)

    @app.get('/api/sprites/{key}.png')
    async def sprite(key:str,request:Request):
        player=auth(request);store=app.state.store
        # Cache contents are readable only through membership in a retained game.
        if not any(player in g.players and any(c and c.sprite==f'/api/sprites/{key}.png' for team in g.teams.values() for c in team) for g in store.games.values()):
            raise GameError('not_member','Sprite is not available to this session.',403)
        data=store.images.get(key)
        if data is None: raise GameError('sprite_unavailable','Sprite is unavailable.',404)
        return Response(data,media_type='image/png',headers={'Cache-Control':'private, max-age=300'})

    @app.websocket('/api/games/{gid}/ws')
    async def websocket(ws:WebSocket,gid:str):
        if ws.headers.get('origin') and ws.headers['origin'] not in allowed:
            await ws.close(code=1008);return
        await ws.accept()
        queue=asyncio.Queue(maxsize=1);g=None;sender=None
        try:
            store=app.state.store
            if gid not in store.games: store.get(gid,'')
            player=auth(ws);g=store.get(gid,player)
            async with g.lock:
                if g.deleted: raise GameError('game_expired','This game expired.',410)
                store.expire(g)
                g.queues.setdefault(player,set()).add(queue)
                store.publish(g)
            async def send():
                while True:
                    state=await queue.get()
                    await asyncio.wait_for(ws.send_json(state),5)
                    if 'error' in state:
                        await ws.close(code=1000);return
            async def receive():
                while True:
                    message=await ws.receive_json()
                    if message=={'kind':'resync'}:
                        async with g.lock:
                            if g.deleted: return
                            store.expire(g);store.publish(g)
                    elif message!={'kind':'heartbeat'}:
                        await ws.close(code=1008);return
            sender=asyncio.create_task(send());receiver=asyncio.create_task(receive())
            done,pending=await asyncio.wait([sender,receiver],return_when=asyncio.FIRST_COMPLETED)
            for task in pending: task.cancel()
            await asyncio.gather(*done,*pending,return_exceptions=True)
        except GameError as exc:
            await ws.send_json({'error':dict(code=exc.code,message=exc.message)})
            await ws.close(code=1008)
        except (WebSocketDisconnect,TimeoutError,ValueError): pass
        finally:
            if sender: sender.cancel()
            if g:
                async with g.lock:
                    for queues in g.queues.values(): queues.discard(queue)

    dist=Path(__file__).resolve().parents[2]/'frontend/dist'
    if dist.is_dir():
        from fastapi.staticfiles import StaticFiles
        app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')
        @app.get('/{path:path}')
        async def index(path:str):
            if path.startswith('api/'): return JSONResponse({'error':{'code':'not_found','message':'Unknown route.'}},404)
            return FileResponse(dist/'index.html')
    return app

app=create_app()
