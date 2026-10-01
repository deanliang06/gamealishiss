import random
import pytest
from backend.app.models import Stats, Move, MoveOutput, Action
from backend.app.battle import Creature
from backend.app.sprites import Renderer
from backend.app.generation import Generator, DemoProvider
from backend.app.service import Store, Game

class Clock:
    def __init__(self): self.now=1000.
    def __call__(self): return self.now
    def advance(self,n): self.now+=n

class Rolls:
    def __init__(self,*values): self.values=iter(values);self.calls=[]
    def randint(self,a,b):
        value=next(self.values);assert a<=value<=b;self.calls.append((a,b,value));return value

def move(**changes):
    data=dict(name='Strike',type='normal',category='physical',power=80,accuracy=100,sleep_chance=0,paralysis_chance=0,poison_chance=0,healing_percent=0)
    data.update(changes);return Move(**data)

def creature(name='mon',types=None,moves=None,**stats):
    base=dict(hp=80,attack=80,defense=80,special_attack=80,special_defense=80,speed=80);base.update(stats)
    return Creature(name,name,Stats(**base),MoveOutput(types=types or ['normal'],moves=moves or [move()]*4),'sprite')

@pytest.fixture
def clock(): return Clock()

@pytest.fixture
def store(clock): return Store(Generator(DemoProvider(),Renderer()),clock=clock,wall=lambda:1700000000.,rng=random.Random(4))

def battle_game(store):
    g=Game('game','ABC123',['a','b'],store.clock());g.phase='actions';g.turn=1;g.deadline=store.clock()+60;g.required=g.players[:]
    g.teams={p:[creature(p+'0'),creature(p+'1')] for p in g.players};g.active={p:0 for p in g.players};store.games[g.id]=g;store.codes[g.code]=g.id
    return g
