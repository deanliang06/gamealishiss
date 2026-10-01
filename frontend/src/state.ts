import type { Snapshot } from './types';
export function latest(current: Snapshot | null, incoming: Snapshot): Snapshot {
  return current && current.game_id === incoming.game_id && current.state_version > incoming.state_version ? current : incoming;
}
export function countdown(snapshot: Snapshot, receivedAt: number, now: number): number | null {
  return snapshot.deadline === null ? null : Math.max(0, Math.ceil(snapshot.deadline - snapshot.server_time - Math.max(0, now - receivedAt) / 1000));
}
export function effects(move: { sleep_chance: number; paralysis_chance: number; poison_chance: number; healing_percent: number }): string {
  return [move.sleep_chance ? `${move.sleep_chance}% sleep` : '', move.paralysis_chance ? `${move.paralysis_chance}% paralysis` : '', move.poison_chance ? `${move.poison_chance}% poison` : '', move.healing_percent ? `Heal ${move.healing_percent}%` : ''].filter(Boolean).join(' · ');
}
