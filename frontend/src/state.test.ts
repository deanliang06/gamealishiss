import { describe, expect, it } from 'vitest';
import { latest, countdown, effects } from './state';
import type { Snapshot } from './types';
const state = (version: number, id = 'g') => ({ game_id: id, state_version: version, deadline: 1060, server_time: 1000 } as Snapshot);
describe('authoritative snapshot handling', () => {
  it('discards delayed snapshots and accepts a new game', () => {
    const current = state(8);
    expect(latest(current, state(7))).toBe(current);
    expect(latest(current, state(9)).state_version).toBe(9);
    expect(latest(current, state(1, 'new')).game_id).toBe('new');
  });
  it('uses elapsed local monotonic time instead of client wall clock', () => {
    expect(countdown(state(1), 250, 10250)).toBe(50);
    expect(countdown(state(1), 250, 60250)).toBe(0);
    expect(countdown({ ...state(1), deadline: null }, 0, 0)).toBeNull();
  });
  it('displays the move effects clients need to choose an action', () => {
    expect(effects({ sleep_chance: 25, paralysis_chance: 0, poison_chance: 0, healing_percent: 0 })).toBe('25% sleep');
    expect(effects({ sleep_chance: 0, paralysis_chance: 0, poison_chance: 0, healing_percent: 35 })).toBe('Heal 35%');
  });
});
