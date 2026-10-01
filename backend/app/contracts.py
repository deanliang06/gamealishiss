"""Public snapshot schemas also exported in OpenAPI for frontend consumers."""
from typing import Annotated, Any, Literal
from pydantic import Field
from .models import StrictModel,Stats,Move,Action

class Acknowledgment(StrictModel):
    request_id: str
    accepted: Literal[True]
    state_version: int

class CreatureState(StrictModel):
    id: str
    name: str
    base_stats: Stats
    battle_stats: dict[str,int]
    types: list[str]
    moves: Annotated[list[Move], Field(min_length=4,max_length=4)]
    sprite: str
    current_hp: int
    max_hp: int
    status: Literal['sleep','paralysis','poison'] | None
    sleep_actions: int
    level: int
    renderer_version: str
    catalog_version: str

class Result(StrictModel):
    reason: Literal['battle','timeout','forfeit','abandonment','generation_failure']
    winner: str | None
    message: str | None = None
    step: str | None = None

class Snapshot(StrictModel):
    game_id: str
    code: str
    player_id: str
    players: list[str]
    phase: Literal['lobby','preparation','ready','actions','resolving','replacement','terminal']
    turn: int
    state_version: int
    attempt_id: str
    ready_version: int | None
    start_ready: list[str]
    ready: list[str]
    description_count: int
    generation: dict[str,list[dict[str,Any]]]
    teams: dict[str,list[CreatureState | None]]
    active: dict[str,int]
    required: list[str]
    own_pending: Action | None
    submission_ack: Acknowledgment | None
    deadline: float | None
    server_time: float
    result: Result | None
    terminal_version: int | None
    terminal_acks: list[str]
    events: list[str]
    resolution_order: list[str]
