# Acceptance report

Implementation and automated verification were performed on Windows 11 with Python 3.12.14 and Node 22.16.0. Backend and browser acceptance use an explicitly selected offline provider; provider adapter tests exercise the real OpenAI SDK against controlled HTTP responses. No production API key was available during implementation.

## Milestone evidence

| Milestone | Delivered implementation and evidence | Verification scope |
| --- | --- | --- |
| 1: foundation/contracts | React/Tailwind/Framer Motion app, single-worker FastAPI, pinned Python requirements, npm lockfile, `.env.example`, `docs/protocol.md`, OpenAPI snapshot/acknowledgment contracts | TypeScript/build checks; missing-key startup test; strict request/response schema tests |
| 2: identities/lobby/descriptions | Signed HttpOnly guest sessions, membership checks on HTTP/WebSockets/sprites, unique codes, two start acknowledgments, immutable sequential descriptions | API tests and actual two-profile browser creation/join/start/description flow; full/invalid/unauthorized lobby tests |
| 3: generation/sprites | Strict stats/moves/spec schemas, bounded recursive correction, real Responses API adapter, safe failure states, explicit offline provider, authored mask catalog/renderer/cache | Initial success and each retry/exhaustion for all steps; SDK transport/refusal/incomplete/JSON tests; all 216 legal sprite/expression assemblies; contact sheets reviewed |
| 4: battle mechanics | Pure battle engine with injected RNG, modern 18-type chart, simultaneous actions, switching, speed/status/healing/poison, replacement, win/loss/draw, event journal | Formula/status/order/knockout fixtures; all 324 matchup cells checked against the official chart; complete browser match with switching and replacement |
| 5: synchronization/lifecycle | Per-game locks, accepted-request deduplication, monotonic versions/deadlines, private snapshots, bounded socket queues, terminal acknowledgments/retention, progress abandonment, cleanup and tombstones | Concurrency/replay/conflict/stale tests; exact deadline boundaries; single/double missing players; readiness token stability; refresh/reconnect; late generation and cleanup races; restart response |
| 6: user experience/delivery | Lobby/preparation/readiness/battle/result screens, move effect labels, accessible HP/control labels, reduced motion, keyboard layouts, play again/exit, README, browser evidence, CI workflow, live acceptance harness | Automated browser and build checks; local five-game service benchmark. Live-provider, physical two-computer, and deployed-host checks remain unverified |

## Automated checks

Run the commands in README. Final local results are recorded in `docs/check-results.txt`. These cover backend unit/integration tests, frontend unit tests, TypeScript checking, production build, catalog verification, and headless Chrome browser tests. The CI workflow is provided for future pushes; it has not been run remotely in this session.

Browser tests include 18 scenarios: one-session bootstrap under React StrictMode; a full match in two isolated cookie profiles with a delayed description acknowledgment that preserves the next draft; invalid-code and unauthorized URL handling; three landing widths; three battle widths; preparation failure, timeout loss/draw, normal win/draw, abandonment; forced replacement controls; expired URL; and WebSocket reconnect with rejection of an older snapshot. Terminal/deadline edge-case UI tests use controlled snapshots; the corresponding backend outcomes are independently tested with controlled clocks/RNG. The integrated match uses real HTTP/WebSocket handlers and the actual mask-rendered PNGs with explicit demo generation.

Contact sheets in `docs/sprites/` cover all 72 legal silhouettes at native and 4x scale, plus all nine head/expression combinations. Automated verification additionally covers each silhouette's three expressions (216 assemblies), binary mask partitioning, region constraints, visibility, attachment connectivity, baseline, bounds, transparency, and deterministic pixels. Visual review found no detached/cropped parts or erased selected features. Browser screenshots show 360px, 768px, and 1280px layouts, plus an integrated demo battle.

The type-chart ground truth is transcribed in `backend/tests/test_chart.py` from the [official Pokémon chart](https://sg.portal-pokemon.com/game/type-chart/), checked on October 1, 2026. All 324 attacker/defender cells are compared independently of the engine's row representation.

`docs/benchmark.json` records a local five-game/ten-player measurement, generation concurrency of three, and a turn committed while another game generated creatures. These measurements use fixtures and an in-process service; they exclude real-provider latency, network conditions, and deployment overhead. They establish local correctness under the initial concurrency target, not production capacity.

## Outstanding acceptance steps

1. Configure `OPENAI_API_KEY` in `.env`, start the real-provider server, and run `python -m backend.scripts.accept_match`. This creates `docs/live-acceptance.json` only after four real generations, usable sprites, switching, forced replacement, and a terminal result pass. No live API calls or paid usage have been claimed as verified.
2. Follow README's LAN setup on two physical computers. Verify membership, refresh and connection-loss recovery, shared countdowns, and the final result across that network. The automated profiles establish logical separation but do not substitute for a physical-network check.
3. On the selected deployment host, repeat the five-game workload with the real provider and record latency, configuration, and provider-concurrency behavior. Review production-origin/HTTPS configuration and the in-memory restart behavior there.

The implementation is present and locally tested. The plan's full acceptance criteria remain open until these external checks are recorded; no required acceptance step has been relabeled as an optional feature.
