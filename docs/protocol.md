# Game protocol and implementation choices

The backend is one authoritative process. Run exactly one Uvicorn worker. React renders snapshots; it does not compute damage, reveal private choices, or advance phases. The implementation is in `backend/app/`, with frontend wire types in `frontend/src/types.ts`. FastAPI exposes the mutation/generation schemas at `/docs` and `/openapi.json`.

## Identity and lobbies

`GET /api/session` creates or restores an anonymous authenticated guest identity. An HttpOnly, SameSite=Lax cookie contains a random 128-bit player ID, timestamp, and HMAC-SHA256 signature. Sessions expire after 30 days. Set a persistent `SESSION_SECRET` to retain session validity across server restarts; if omitted, a random process secret is used. Possession of a lobby code permits joining a free slot, not impersonating an existing player. HTTP and WebSocket handlers verify game membership. Cookie `Secure` is configurable for HTTPS deployments. State-changing requests and WebSockets reject browser origins outside `ALLOWED_ORIGINS`.

`POST /api/lobbies` takes `{ "request_id": "unique-id" }` to create a game, or the same shape plus `code` to join one. Returns `{ "game_id": "..." }`. Codes have six characters from `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`. A full lobby rejects new identities; existing membership does not duplicate slots. Both members request start once. An unstarted/inactive lobby expires after five minutes without meaningful progress. Codes stop accepting joins when preparation begins. Create/join requests cannot carry an expected game phase because a creator has no game yet; their deduplication is scoped to the authenticated identity and retained game's lifetime.

Descriptions contain 3–1000 characters after trimming. Each player submits slot 0 then slot 1; accepted text is immutable for the preparation attempt. Creature display names use the first 40 characters of that description, escaped by React; IDs remain distinct. Pokemon generation starts per slot immediately after acceptance, with at most three provider calls concurrently across all games by default. Sprite selection has no gameplay effect.

## State machine

| Phase | Accepted operations | Exit |
| --- | --- | --- |
| `lobby` | start, leave | both start -> preparation; leave/inactivity -> terminal |
| `preparation` | describe, leave | four fully validated creatures -> ready; failure/inactivity -> terminal |
| `ready` | ready, leave | both stable-token acknowledgments -> turn 1 actions; inactivity -> terminal |
| `actions` | action, leave | both choices -> resolving; deadline/leave -> terminal |
| `resolving` | no external mutations | committed turn -> replacement, next actions, or terminal |
| `replacement` | replace for required players, leave | all choices -> next actions; deadline/leave -> terminal |
| `terminal` | terminal_ack | retained for five minutes, then deleted |

Resolving is internal and synchronous under the game lock. No partial damage state is published. A phase change and the preceding accepted mutation may share one committed state version. State versions increase on every accepted mutation, generation progress, and terminal transition; exact increment sizes are not a client contract. `ready_version` is an immutable token assigned when all four creatures are usable; it remains unchanged as each acknowledgment advances the snapshot version. `terminal_version` likewise identifies the terminal result even after delivery acknowledgments.

## Mutations

`POST /api/games/{game_id}/mutations` requires authenticated membership. The URL and body game IDs must match. Every request includes:

```json
{
  "request_id": "new-random-id",
  "game_id": "game-url-id",
  "expected_phase": "actions",
  "turn": 1,
  "attempt_id": "attempt-from-snapshot",
  "kind": "action",
  "action": { "kind": "move", "index": 0 }
}
```

Use `kind=start`; `kind=describe` plus `description`; `kind=ready` plus `ready_version`; `kind=action` plus `action`; `kind=replace` plus a switch action; `kind=terminal_ack` plus `terminal_version`; or `kind=leave`. Move indexes are 0–3, team indexes 0–1. Replace cannot choose a move. Voluntary/forced switches cannot select the active or a fainted creature. Request IDs are scoped to identity and game. Identical replay returns the original `{request_id, accepted: true, state_version}` acknowledgment, even if the phase has advanced; changed payloads fail. Only accepted requests are recorded. Network retries must reuse the original payload and ID.

Errors use `{ "error": { "code": "stale_request", "message": "..." }, "snapshot": {...} }`. Stale requests carry a current recipient-filtered snapshot. Important codes: `unauthenticated` (401), `not_member`/`invalid_origin` (403), `invalid_code` (404), `game_unavailable`/`game_expired` (410), `request_conflict`, `already_submitted`, `stale_request`, `stale_ready`, `stale_terminal`, `invalid_phase`, `invalid_action`, `invalid_switch`, `need_opponent`, `lobby_full`, `lobby_closed`, and `invalid_description` (409). Schema errors use FastAPI's standard 422 validation response. Unknown game IDs, including IDs from a previous process, return unavailable; expired IDs have bounded 24-hour tombstones and then become unavailable.

## Snapshots and sockets

`GET /api/games/{id}` resynchronizes. `WS /api/games/{id}/ws` authenticates the same cookie and sends an initial snapshot, then updates. Send `{ "kind": "resync" }` for another complete snapshot or `{ "kind": "heartbeat" }` for keepalive. Mutations use HTTP. A one-entry per-socket queue coalesces superseded snapshots; sends time out after five seconds. Clients reconnect automatically after one second and resynchronize. Socket delivery never counts as a terminal acknowledgment.

Snapshot fields: `game_id`, `code`, recipient `player_id`, `players`, `phase`, `turn`, `state_version`, `attempt_id`, `ready_version`, `start_ready`, `ready`, recipient `description_count`, validated generation progress, `teams`, `active`, `required`, recipient `own_pending` and `submission_ack`, `deadline`, `server_time`, `result`, `terminal_version`, `terminal_acks`, `events`, and `resolution_order`. During preparation a team slot may be null. Generation progress contains validated stats/moves/specifications, never descriptions or pending battle choices. Creature state includes IDs/names/types, immutable base stats, calculated battle stats, moves, sprite URL, level, HP, status, and remaining sleep actions. Public fields match for both clients. The opponent's private action/replacement never appears.

Discard older versions within the same game. Countdown display uses the difference between deadline and server time plus elapsed client monotonic time. Backend deadlines use monotonic time and expire at `now >= deadline`. Missing one required submission forfeits; missing two draws. Maintenance checks every 200ms, and submissions check expiration under the lock independently of maintenance. Reading, heartbeats, and reconnects do not reset deadlines/progress. A replacement phase does not start a new action clock until all required replacements commit.

## Generation and battle settings

Version-1 base-stat bounds are HP 1–255, Attack 1–190, Defense 1–230, Special Attack 1–194, Special Defense 1–230, Speed 1–200, with a **game balance total cap of 600**. They are fixed game limits, not a live database of species. Every creature uses level 50, zero IV/EV, and neutral nature. All other mechanics follow `plan.md`; see `backend/app/battle.py` for the full 18-type chart. Reference: [official Pokémon type chart](https://sg.portal-pokemon.com/game/type-chart/).

The provider uses the Responses API with strict JSON Schema, followed by strict Pydantic and backend validation. [Official Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs). The configured default model is `gpt-4.1-mini`; override `OPENAI_MODEL` with a Structured Outputs-compatible model available to your API account. Each schema correction step allows one initial attempt plus three recursive retries, preserving original context and previous rejected output/errors. No validated upstream steps are rerun. Transport/rate-limit failures allow two total transport attempts with a 0.5s delay; refusals, incomplete responses, and other API errors fail immediately. SDK transport timeout is 30s, each provider-step call is bounded at 70s, and a creature pipeline at 280s including semaphore waiting. A failed match becomes terminal and cannot later start.

PNG cache entries are in memory, keyed by validated specification plus renderer/catalog versions, and served only to members of games referencing them. Maintenance evicts unreferenced entries; a retained terminal game keeps its sprites for its full retention period. Stats/moves/specifications remain in failed terminal snapshots for inspection. Cleanup removes all game objects, deduplication records, and generation tasks after five minutes. Restart discards games, sprites, and deduplication; this version has no persistence or distributed workers.
