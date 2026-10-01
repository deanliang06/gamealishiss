"""Pure authoritative battle mechanics; randomness is explicitly injected."""
import math
from dataclasses import dataclass, field
from .models import Stats, MoveOutput, Move

# Standard modern 18-type chart. Unlisted matchups are neutral.
# Each row is (super-effective, resisted, immune).
CHART = {
 'normal': ('', 'rock steel', 'ghost'),
 'fire': ('grass ice bug steel', 'fire water rock dragon', ''),
 'water': ('fire ground rock', 'water grass dragon', ''),
 'electric': ('water flying', 'electric grass dragon', 'ground'),
 'grass': ('water ground rock', 'fire grass poison flying bug dragon steel', ''),
 'ice': ('grass ground flying dragon', 'fire water ice steel', ''),
 'fighting': ('normal ice rock dark steel', 'poison flying psychic bug fairy', 'ghost'),
 'poison': ('grass fairy', 'poison ground rock ghost', 'steel'),
 'ground': ('fire electric poison rock steel', 'grass bug', 'flying'),
 'flying': ('grass fighting bug', 'electric rock steel', ''),
 'psychic': ('fighting poison', 'psychic steel', 'dark'),
 'bug': ('grass psychic dark', 'fire fighting poison flying ghost steel fairy', ''),
 'rock': ('fire ice flying bug', 'fighting ground steel', ''),
 'ghost': ('psychic ghost', 'dark', 'normal'),
 'dragon': ('dragon', 'steel', 'fairy'),
 'dark': ('psychic ghost', 'fighting dark fairy', ''),
 'steel': ('ice rock fairy', 'fire water electric steel', ''),
 'fairy': ('fighting dragon dark', 'fire poison steel', ''),
}

def effectiveness(move_type, defender_types):
    strong, weak, immune = [s.split() for s in CHART[move_type]]
    return math.prod(0 if t in immune else 2 if t in strong else .5 if t in weak else 1 for t in defender_types)

@dataclass
class Creature:
    id: str
    name: str
    base_stats: Stats
    kit: MoveOutput
    sprite: str
    sprite_spec: dict = field(default_factory=dict)
    renderer_version: str = '1'
    catalog_version: str = '1'
    level: int = 50
    status: str | None = None
    sleep_actions: int = 0
    current_hp: int = field(init=False)

    def __post_init__(self):
        self.current_hp = self.max_hp

    @property
    def max_hp(self):
        return 2 * self.base_stats.hp * self.level // 100 + self.level + 10

    def stat(self, name):
        value = 2 * getattr(self.base_stats, name) * self.level // 100 + 5
        return max(1, value // 2) if name == 'speed' and self.status == 'paralysis' else value

    def public(self):
        return dict(id=self.id, name=self.name, base_stats=self.base_stats.model_dump(),
                    battle_stats={k:self.stat(k) for k in Stats.model_fields if k != 'hp'},
                    types=self.kit.types, moves=[m.model_dump() for m in self.kit.moves],
                    sprite=self.sprite, current_hp=self.current_hp, max_hp=self.max_hp,
                    status=self.status, sleep_actions=self.sleep_actions, level=self.level,
                    renderer_version=self.renderer_version,catalog_version=self.catalog_version)

def damage(user: Creature, target: Creature, move: Move, random_percent: int):
    eff = effectiveness(move.type, target.kit.types)
    if not move.power or not eff:
        return 0
    a, d = ('attack','defense') if move.category == 'physical' else ('special_attack','special_defense')
    raw = ((2 * user.level / 5 + 2) * move.power * (max(1,user.stat(a))/max(1,target.stat(d))) / 50 + 2)
    modifier = (1.5 if move.type in user.kit.types else 1) * eff * random_percent / 100
    return max(1, math.floor(raw * modifier))

def execute(user, target, move, rng, events):
    if user.current_hp == 0:
        events.append(f'{user.name} fainted before acting.')
        return
    if user.status == 'sleep':
        user.sleep_actions -= 1
        events.append(f'{user.name} is asleep and cannot move.')
        if user.sleep_actions == 0:
            user.status = None
            events.append(f'{user.name} woke up.')
        return
    if user.status == 'paralysis' and rng.randint(1,100) <= 25:
        events.append(f'{user.name} is paralyzed and cannot move.')
        return
    if rng.randint(1,100) > move.accuracy:
        events.append(f'{user.name} used {move.name}, but missed.')
        return
    events.append(f'{user.name} used {move.name}.')
    if move.healing_percent:
        restored = min(user.max_hp - user.current_hp, user.max_hp * move.healing_percent // 100)
        user.current_hp += restored
        events.append(f'{user.name} recovered {restored} HP.')
        return
    if move.power:
        if not effectiveness(move.type, target.kit.types):
            events.append(f'{target.name} is immune.')
            return
        dealt = min(target.current_hp, damage(user,target,move,rng.randint(85,100)))
        target.current_hp -= dealt
        events.append(f'{target.name} lost {dealt} HP.')
    if target.current_hp:
        for status, chance in [('sleep',move.sleep_chance),('paralysis',move.paralysis_chance),('poison',move.poison_chance)]:
            if chance and rng.randint(1,100) <= chance and target.status is None:
                target.status = status
                target.sleep_actions = 2 if status == 'sleep' else 0
                events.append(f'{target.name} gained {status}.')

def resolve(teams, active, actions, rng):
    players = list(teams)
    events = []
    users = {p:teams[p][active[p]] for p in players}
    for p in players:
        if actions[p].kind == 'switch':
            active[p] = actions[p].index
            events.append(f'{p} switched to {teams[p][active[p]].name}.')
    movers = [p for p in players if actions[p].kind == 'move']
    if len(movers) == 2:
        s0, s1 = (users[p].stat('speed') for p in movers)
        if s0 < s1 or (s0 == s1 and rng.randint(0,1)):
            movers.reverse()
    order = movers[:]
    for p in movers:
        opponent = next(q for q in players if q != p)
        execute(users[p], teams[opponent][active[opponent]], users[p].kit.moves[actions[p].index], rng, events)
    for p in players:
        mon = teams[p][active[p]]
        if mon.current_hp and mon.status == 'poison':
            tick = min(mon.current_hp, max(1,mon.max_hp//8))
            mon.current_hp -= tick
            events.append(f'{mon.name} lost {tick} HP to poison.')
    for p in players:
        if teams[p][active[p]].current_hp == 0:
            events.append(f'{teams[p][active[p]].name} fainted.')
    exhausted = [p for p in players if not any(c.current_hp for c in teams[p])]
    result = None
    if exhausted:
        result = dict(reason='battle', winner=None if len(exhausted)==2 else next(p for p in players if p not in exhausted))
    required = [p for p in players if teams[p][active[p]].current_hp==0] if not result else []
    return events, order, required, result
