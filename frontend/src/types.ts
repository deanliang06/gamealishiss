export type Phase = 'lobby' | 'preparation' | 'ready' | 'actions' | 'resolving' | 'replacement' | 'terminal';
export type Action = { kind: 'move' | 'switch'; index: number };
export type Move = { name: string; type: string; category: string; power: number; accuracy: number; sleep_chance: number; paralysis_chance: number; poison_chance: number; healing_percent: number };
export type Creature = { id: string; name: string; types: string[]; moves: Move[]; sprite: string; renderer_version: string; catalog_version: string; current_hp: number; max_hp: number; status: string | null; sleep_actions: number; level: number; base_stats: Record<string, number>; battle_stats: Record<string, number> };
export type Snapshot = {
  game_id: string; code: string; player_id: string; players: string[]; phase: Phase; turn: number; state_version: number;
  attempt_id: string; ready_version: number | null; start_ready: string[]; ready: string[]; description_count: number;
  generation: Record<string, Record<string, unknown>[]>; teams: Record<string, (Creature | null)[]>; active: Record<string, number>;
  required: string[]; own_pending: Action | null; submission_ack: { request_id: string; accepted: boolean; state_version: number } | null;
  deadline: number | null; server_time: number; terminal_version: number | null; terminal_acks: string[];
  result: { reason: string; winner: string | null; message?: string; step?: string } | null; events: string[]; resolution_order: string[];
};
export type Mutation = { request_id: string; game_id: string; expected_phase: Phase; turn: number; attempt_id: string; kind: 'start'|'describe'|'ready'|'action'|'replace'|'terminal_ack'|'leave'; description?: string; action?: Action; ready_version?: number; terminal_version?: number };
