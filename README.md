# Gamealishiss

A two-player creature battle game: share a lobby code, describe two original Pokemon-like creatures each, discover their generated moves and pixel sprites, and secretly choose actions each turn. React, Tailwind, and Framer Motion frontend; authoritative single-worker FastAPI backend; OpenAI Structured Outputs; deterministic Pillow mask renderer.

## Setup

Requires Python 3.12+ and Node.js 22+ with npm. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `OPENAI_API_KEY` in `.env`. Set `SESSION_SECRET` to a long random value (for example, generate one with `python -c "import secrets; print(secrets.token_hex(32))"`). Do not commit `.env`. The backend fails startup clearly when no provider key is configured. `OPENAI_MODEL` is configurable; the default is `gpt-4.1-mini`. See `.env.example` for concurrency, cookie, and origin settings.

Install and build the frontend:

```powershell
cd frontend
npm ci
npm run build
cd ..
```

Run the built game with **exactly one worker**:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Open `http://localhost:8000`. For two computers, add the host's LAN origin (for example `http://192.168.1.10:8000`) to `ALLOWED_ORIGINS` in `.env`, restart the backend, permit inbound TCP 8000 through the host firewall, and open that same host URL on both computers. Create a lobby on one and enter its code on the other. An internet deployment should use HTTPS through a WebSocket-capable reverse proxy, `COOKIE_SECURE=true`, a persistent session secret, and the actual public origin. Do not run multiple workers or replicas with this in-memory store.

For frontend development, run `npm run dev` inside `frontend` while the backend runs on port 8000. Vite proxies `/api` and WebSockets to the backend; open port 5173. Add the actual Vite browser origin to `ALLOWED_ORIGINS` when developing over LAN.

Linux/macOS use `.venv/bin/python` in place of `.venv\Scripts\python.exe` and `cp .env.example .env` when setting up.

## Explicit offline development

Set `GAME_PROVIDER=demo` to use deterministic offline fixtures, without a key. This is an explicit development mode; production failures never fall back to fixtures. Restart after changing configuration. Remove that setting or set `GAME_PROVIDER=openai` for real generation.

After building the frontend, a local offline preview can be started directly:

```powershell
$env:GAME_PROVIDER = 'demo'
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Open `http://localhost:8000`. Set `$env:GAME_PROVIDER = 'openai'` when switching that PowerShell session back to real generation.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m backend.scripts.verify_catalog
.\.venv\Scripts\python.exe -m backend.scripts.benchmark
cd frontend
npm test
npm run build
npm run test:e2e
```

Browser tests start/stop their own backend and Vite servers on ports 8000/5173 and use explicit demo generation. Stop any existing servers using those ports first. On Windows the tests use installed Google Chrome. On Linux/macOS first run `npx playwright install chromium`. `TEST_PYTHON` can override the test backend's Python executable. Browser checks include a full match in two isolated browser profiles, accepted-action refresh recovery, private choices, forced replacements, invalid codes/membership, terminal states, expiration, reconnects, and keyboard/responsive layouts. Some edge-case UI scenarios use controlled snapshots; backend deadline/cleanup tests use an injected monotonic clock.

Rebuild the authored mask library only when changing sprite geometry:

```powershell
.\.venv\Scripts\python.exe backend/scripts/build_assets.py
.\.venv\Scripts\python.exe -m backend.scripts.verify_catalog
```

Review contact sheets in `docs/sprites/`. Runtime rendering uses the committed PNG masks, not procedural shapes. The verification command checks all 72 legal silhouettes with all three expressions (216 assemblies), including palette, bounds, baseline, connectivity, part visibility, and repeatable pixels.

With a real-key server running, run the live acceptance harness:

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.accept_match --url http://localhost:8000
```

It uses two authenticated cookie sessions, four real generations, sprite downloads, readiness, voluntary switching, battles, forced replacements, and terminal acknowledgments, and writes `docs/live-acceptance.json`. It refuses demo mode. It may incur API usage costs. A live match that does not exercise forced replacement must be repeated for that acceptance criterion.

## Design and evidence

- [Implementation plan](plan.md)
- [Protocol, phases, stat limits, errors, and provider policy](docs/protocol.md)
- [Acceptance report](docs/acceptance.md)
- [Sprite contact sheets](docs/sprites/)
- [Browser screenshots](docs/screenshots/)
- [Local concurrency measurements](docs/benchmark.json)

Guest identities last 30 days and refreshes recover state. Disconnecting never pauses battle clocks. Results remain recoverable for five minutes; expired game URLs return to the lobby. Restarting the backend ends all in-memory matches. The initial concurrency target is five two-player games; recorded local fixture measurements do not establish live-provider or deployment capacity.
