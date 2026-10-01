"""Strict wire and generation contracts. All gameplay integers reject coercion."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

TYPES = ('normal','fire','water','electric','grass','ice','fighting','poison','ground','flying','psychic','bug','rock','ghost','dragon','dark','steel','fairy')
PokemonType = Literal['normal','fire','water','electric','grass','ice','fighting','poison','ground','flying','psychic','bug','rock','ghost','dragon','dark','steel','fairy']
Percent = Annotated[int, Field(ge=0, le=100)]

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class Stats(StrictModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    hp: Annotated[int, Field(ge=1, le=255)]
    attack: Annotated[int, Field(ge=1, le=190)]
    defense: Annotated[int, Field(ge=1, le=230)]
    special_attack: Annotated[int, Field(ge=1, le=194)]
    special_defense: Annotated[int, Field(ge=1, le=230)]
    speed: Annotated[int, Field(ge=1, le=200)]

    @model_validator(mode='after')
    def total(self):
        if sum(self.model_dump().values()) > 600:
            raise ValueError('Base stat total must be at most 600')
        return self

class Move(StrictModel):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    type: PokemonType
    category: Literal['physical', 'special', 'status']
    power: Annotated[int, Field(ge=0, le=150)]
    accuracy: Annotated[int, Field(ge=1, le=100)]
    sleep_chance: Percent
    paralysis_chance: Percent
    poison_chance: Percent
    healing_percent: Annotated[int, Field(ge=0, le=50)]

    @model_validator(mode='after')
    def mechanics(self):
        chances = [self.sleep_chance, self.paralysis_chance, self.poison_chance]
        if not self.name.strip():
            raise ValueError('Move name cannot be blank')
        if (self.category == 'status') != (self.power == 0):
            raise ValueError('Status moves require zero power; damage moves require positive power')
        if sum(c > 0 for c in chances) > 1:
            raise ValueError('At most one status chance is allowed')
        if self.healing_percent and (self.power or any(chances) or self.category != 'status'):
            raise ValueError('Healing is a self-only status move with no other effects')
        if not (self.power or any(chances) or self.healing_percent):
            raise ValueError('No-op moves are forbidden')
        return self

class MoveOutput(StrictModel):
    types: Annotated[list[PokemonType], Field(min_length=1, max_length=2)]
    moves: Annotated[list[Move], Field(min_length=4, max_length=4)]

    @model_validator(mode='after')
    def choices(self):
        if len(set(self.types)) != len(self.types):
            raise ValueError('Duplicate types')
        if not any(m.power for m in self.moves):
            raise ValueError('At least one damaging move is required')
        return self

class Silhouette(StrictModel):
    body_family: Literal['biped']
    head: Literal['fox_large_round', 'cat_round', 'lizard_round']
    body: Literal['compact_torso']
    ears: Literal['none', 'paired_tall_triangles', 'paired_round_ears', 'paired_short_fins']
    tail: Literal['none', 'single_fluffy_zigzag', 'single_cat_curve', 'single_lizard_taper']
    limbs: Literal['short_paws', 'short_claws']
    eyes: Literal['alert', 'gentle', 'fierce']
    wings: Literal['none', 'paired_small_bat', 'paired_small_feather']
    horns: Literal['none', 'single_forehead_horn', 'paired_small_horns']

Hex = Annotated[str, Field(pattern=r'^#[0-9A-Fa-f]{6}$')]
Role = Literal['base', 'highlight', 'accent', 'shadow', 'outline']

class Palette(StrictModel):
    max_colors: Literal[5]
    base: Hex
    highlight: Hex
    accent: Hex
    shadow: Hex
    outline: Hex

class Region(StrictModel):
    part: Literal['head','muzzle','belly','ear_tips','tail_tip','paws','wing_membrane','wing_feathers','horns']
    color: Role

class SpriteSpec(StrictModel):
    schema_version: Literal['1']
    canvas: Annotated[list[Literal[64]], Field(min_length=2, max_length=2)]
    silhouette: Silhouette
    pose: Literal['front_three_quarter']
    palette_rules: Palette
    regions: Annotated[list[Region], Field(max_length=9)]

class Action(StrictModel):
    kind: Literal['move','switch']
    index: Annotated[int, Field(ge=0, le=3)]

class Mutation(StrictModel):
    request_id: Annotated[str, Field(min_length=1, max_length=100)]
    game_id: str
    expected_phase: Literal['lobby','preparation','ready','actions','replacement','terminal']
    turn: Annotated[int, Field(ge=0)]
    attempt_id: str
    kind: Literal['start','describe','ready','action','replace','terminal_ack','leave']
    description: Annotated[str, Field(max_length=1000)] | None = None
    action: Action | None = None
    ready_version: int | None = None
    terminal_version: int | None = None

class LobbyRequest(StrictModel):
    request_id: Annotated[str, Field(min_length=1, max_length=100)]
    code: Annotated[str, Field(max_length=6)] | None = None
