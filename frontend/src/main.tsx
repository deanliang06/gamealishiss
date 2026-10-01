import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { motion, MotionConfig } from 'framer-motion';
import { latest, countdown, effects } from './state';
import type { Snapshot, Mutation, Creature } from './types';
import './style.css';

type Failure = { error: { code: string; message: string }; snapshot?: Snapshot };
async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, { credentials: 'same-origin', ...(body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}) });
  const data = await response.json();
  if (!response.ok) throw data;
  return data;
}
// StrictMode replays mount effects. Share concurrent session requests so two
// cookie-less requests cannot create competing guest identities.
let sessionFlight: Promise<unknown> | null = null;
function ensureSession() {
  if (!sessionFlight) sessionFlight = request('/api/session').finally(() => { sessionFlight = null; });
  return sessionFlight;
}
function currentGame() { return location.pathname.startsWith('/game/') ? location.pathname.split('/')[2] : null; }

export function App() {
  const [game, setGame] = useState<string | null>(currentGame);
  const [state, setState] = useState<Snapshot | null>(null);
  const [sessionReady, setSessionReady] = useState(false);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState('');
  const [description, setDescription] = useState('');
  const [now, setNow] = useState(performance.now());
  const receivedAt = useRef(performance.now());
  const snapshotRef = useRef<Snapshot | null>(null);
  const gameRef = useRef(game);
  const terminalAck = useRef<string | null>(null);
  const navigation = (id: string | null) => { history.pushState({}, '', id ? `/game/${id}` : '/'); gameRef.current = id; setGame(id); setState(null); snapshotRef.current = null; terminalAck.current = null; setDescription(''); };
  const ingest = (incoming: Snapshot) => {
    if (incoming.game_id !== gameRef.current) return;
    const chosen = latest(snapshotRef.current, incoming);
    if (chosen === incoming) {
      // Clear only when the accepted slot advances, before rendering the next
      // prompt. A delayed HTTP acknowledgment must not erase its new draft.
      if (snapshotRef.current && chosen.description_count !== snapshotRef.current.description_count) setDescription('');
      receivedAt.current = performance.now(); snapshotRef.current = chosen; setState(chosen);
    }
  };
  const fail = (failure: Failure) => {
    setError(failure.error?.message || 'Connection failed. Please try again.');
    if (failure.snapshot) ingest(failure.snapshot);
    if (failure.error?.code === 'unauthenticated') {
      setSessionReady(false);
      ensureSession().then(() => setSessionReady(true)).catch(() => setError('Could not restore your session. Refresh to retry.'));
    }
    if (['game_expired', 'game_unavailable', 'not_member', 'unauthenticated'].includes(failure.error?.code)) navigation(null);
  };
  useEffect(() => {
    ensureSession().then(() => setSessionReady(true)).catch(fail);
    const timer = setInterval(() => setNow(performance.now()), 250);
    const pop = () => { gameRef.current = currentGame(); setGame(currentGame()); setState(null); snapshotRef.current = null; };
    window.addEventListener('popstate', pop);
    return () => { clearInterval(timer); window.removeEventListener('popstate', pop); };
  }, []);
  useEffect(() => {
    if (!game || !sessionReady) { setConnected(false); return; }
    let stopped = false; let socket: WebSocket; let retry: ReturnType<typeof setTimeout>; let heartbeat: ReturnType<typeof setInterval>;
    const connect = () => {
      request<Snapshot>(`/api/games/${game}`).then(s => { if (!stopped) ingest(s); }).catch(e => { if (!stopped) fail(e); });
      socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/games/${game}/ws`);
      socket.onopen = () => { if (!stopped) setConnected(true); heartbeat = setInterval(() => { if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ kind: 'heartbeat' })); }, 15000); };
      socket.onmessage = e => { if (stopped) return; const data = JSON.parse(e.data); if (data.error) fail(data); else ingest(data); };
      socket.onclose = () => { clearInterval(heartbeat); if (!stopped) { setConnected(false); retry = setTimeout(connect, 1000); } };
      socket.onerror = () => socket.close();
    };
    connect();
    return () => { stopped = true; clearTimeout(retry); clearInterval(heartbeat); socket?.close(); };
  }, [game, sessionReady]);
  const mutate = async (kind: Mutation['kind'], extra: Partial<Mutation> = {}) => {
    const s = snapshotRef.current; if (!s || busy) return;
    setBusy(true); setError('');
    const payload: Mutation = { request_id: crypto.randomUUID(), game_id: s.game_id, expected_phase: s.phase, turn: s.turn, attempt_id: s.attempt_id, kind, ...extra };
    try {
      // A transport retry uses exactly the same request ID and payload.
      try { await request(`/api/games/${s.game_id}/mutations`, payload); }
      catch (e) { if (e instanceof TypeError) await request(`/api/games/${s.game_id}/mutations`, payload); else throw e; }
      ingest(await request<Snapshot>(`/api/games/${s.game_id}`));
    } catch (e) { if (gameRef.current === s.game_id) fail(e as Failure); } finally { setBusy(false); }
  };
  useEffect(() => {
    if (state?.phase === 'terminal' && !state.terminal_acks.includes(state.player_id) && terminalAck.current !== state.game_id && !busy) {
      terminalAck.current = state.game_id;
      void mutate('terminal_ack', { terminal_version: state.terminal_version! });
    }
  }, [state, busy]);
  const lobby = async (join = false) => {
    setBusy(true); setError('');
    try { const result = await request<{ game_id: string }>('/api/lobbies', { request_id: crypto.randomUUID(), ...(join ? { code: code.trim().toUpperCase() } : {}) }); navigation(result.game_id); }
    catch (e) { fail(e as Failure); } finally { setBusy(false); }
  };
  const opponent = state?.players.find(p => p !== state.player_id);
  const own = state?.teams[state.player_id] || [];
  const other = state && opponent ? state.teams[opponent] || [] : [];
  const canAct = state && connected && !busy && !state.own_pending && state.required.includes(state.player_id);
  const seconds = state ? countdown(state, receivedAt.current, now) : null;

  return <MotionConfig reducedMotion="user"><div className="app-shell">
    <header><a href="/" onClick={e => { e.preventDefault(); navigation(null); }} className="wordmark"><span className="orb"/>gamealishiss<span className="brand-tag">CREATURE ARENA</span></a><span className="connection">{game ? connected ? '● Connected' : '○ Reconnecting…' : 'Two players. Infinite creatures.'}</span></header>
    <main>
      {error && <div role="alert" className="error">{error}<button aria-label="Dismiss error" onClick={() => setError('')}>×</button></div>}
      {!sessionReady && <p role="status">Connecting to the arena…</p>}
      {!game && <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="landing">
        <div><p className="eyebrow">YOUR IMAGINATION. YOUR TEAM.</p><h1>Dream it.<br/><em>Battle it.</em></h1><p className="intro">Describe two creatures. Give them life. Challenge a friend in a turn-based clash of original monsters.</p><div className="steps"><span>01 · Describe</span><span>02 · Discover</span><span>03 · Duel</span></div></div>
        <div className="panel lobby-panel"><span className="eyebrow">ENTER THE ARENA</span><h2>A new rivalry starts here.</h2><button className="primary" disabled={busy || !sessionReady} onClick={() => lobby()}>Create a lobby <span>↗</span></button><div className="divider">or join your friend</div><form onSubmit={e => { e.preventDefault(); if (code.length === 6) void lobby(true); }}><label htmlFor="code">Lobby code</label><input id="code" placeholder="ABC123" maxLength={6} value={code} onChange={e => setCode(e.target.value.toUpperCase())}/><button className="secondary" disabled={busy || !sessionReady || code.trim().length !== 6}>Join lobby</button></form><p className="hint">Share the code. Play from different computers.</p></div>
      </motion.section>}
      {game && !state && <section className="panel"><p role="status">Recovering your game…</p></section>}
      {state && <>
        <div className="game-meta"><span className="eyebrow">LOBBY <strong>{state.code}</strong></span><span>{state.phase === 'actions' || state.phase === 'replacement' ? `Turn ${state.turn}` : state.phase.toUpperCase()}{seconds !== null && <strong className={seconds < 10 ? 'urgent' : ''}> · {seconds}s</strong>}</span></div>
        {state.phase === 'lobby' && <section className="panel centered"><p className="eyebrow">INVITE YOUR OPPONENT</p><h1 className="code-display">{state.code}</h1><p>{state.players.length === 2 ? 'Your opponent has joined. Both players must start.' : 'Share this code with a friend to fill the second spot.'}</p><div className="player-slots"><span>You · {state.start_ready.includes(state.player_id) ? 'Ready' : 'Joined'}</span><span>{opponent ? `Opponent · ${state.start_ready.includes(opponent) ? 'Ready' : 'Joined'}` : 'Waiting for opponent…'}</span></div><button className="primary" disabled={busy || !connected || state.players.length < 2 || state.start_ready.includes(state.player_id)} onClick={() => mutate('start')}>{state.start_ready.includes(state.player_id) ? 'Waiting for opponent…' : 'Start creating'}</button></section>}
        {state.phase === 'preparation' && <section className="panel preparation"><p className="eyebrow">BUILD YOUR TEAM · {Math.min(state.description_count + 1, 2)} / 2</p>{state.description_count < 2 ? <form onSubmit={e => { e.preventDefault(); void mutate('describe', { description }); }}><h2>Describe your {state.description_count === 0 ? 'first' : 'second'} pokemon</h2><p>Tell us its shape, temperament, and elemental powers. Make something entirely your own.</p><label htmlFor="description">Creature description</label><textarea id="description" maxLength={1000} rows={5} placeholder="A fierce little fox with sapphire fur and a thundercloud tail…" value={description} onChange={e => setDescription(e.target.value)}/><span className="hint">{description.length}/1000 characters</span><button className="primary" disabled={busy || !connected || description.trim().length < 3}>Create creature ↗</button></form> : <><h2>Bringing your team to life…</h2><p role="status">The arena opens when all four creatures are ready.</p></>}<div className="generation-grid">{state.players.map(p => <div key={p}><h3>{p === state.player_id ? 'Your team' : 'Opponent team'}</h3>{[0, 1].map(i => <p key={i}>Creature {i + 1} · {Object.keys(state.generation[p]?.[i] || {}).length}/3 steps complete</p>)}</div>)}</div></section>}
        {state.phase === 'ready' && <section className="panel centered"><p className="eyebrow">TEAMS COMPLETE</p><h2>Meet your creatures.</h2><div className="team-preview">{own.map(c => c && <CreatureCard key={c.id} creature={c}/>)}</div><button className="primary" disabled={busy || !connected || state.ready.includes(state.player_id)} onClick={() => mutate('ready', { ready_version: state.ready_version! })}>{state.ready.includes(state.player_id) ? 'Waiting for opponent…' : 'Ready to battle'}</button></section>}
        {['actions', 'replacement', 'terminal'].includes(state.phase) && own.filter(Boolean).length === 2 && other.filter(Boolean).length === 2 && <>
          <section className="arena"><div className="arena-side"><span className="eyebrow">YOUR ACTIVE CREATURE</span><CreatureCard creature={own[state.active[state.player_id]]!}/><Reserves team={own} active={state.active[state.player_id]}/></div><span className="versus">VS</span><div className="arena-side"><span className="eyebrow">OPPONENT</span><CreatureCard creature={other[state.active[opponent!]]!}/><Reserves team={other} active={state.active[opponent!]}/></div></section>
          {state.phase !== 'terminal' && <section className="panel controls"><div className="control-title"><h2>{state.phase === 'replacement' ? 'Choose your replacement' : 'Your next move'}</h2><span role="status">{state.own_pending ? 'Choice locked. Waiting for opponent…' : !state.required.includes(state.player_id) ? 'Waiting for opponent to replace…' : 'Select secretly. Resolve together.'}</span></div>{state.phase === 'actions' && <div className="move-grid">{own[state.active[state.player_id]]!.moves.map((m, i) => <button key={i} disabled={!canAct} onClick={() => mutate('action', { action: { kind: 'move', index: i } })} className="move-button"><span className="eyebrow">{m.type} · {m.category}</span><strong>{m.name}</strong><span>Power {m.power} · Accuracy {m.accuracy}%</span>{effects(m) && <small>{effects(m)}</small>}</button>)}</div>}<div className="switch-row">{own.map((c, i) => c && <button key={c.id} className="secondary" disabled={!canAct || i === state.active[state.player_id] || c.current_hp === 0} onClick={() => mutate(state.phase === 'replacement' ? 'replace' : 'action', { action: { kind: 'switch', index: i } })}>Switch to {c.name} · {c.current_hp === 0 ? 'Fainted' : `${c.current_hp}/${c.max_hp} HP`}</button>)}</div></section>}
        </>}
        {state.phase === 'terminal' && <section className="panel centered terminal"><p className="eyebrow">{state.result?.reason.replaceAll('_', ' ')}</p><h2>{state.result?.winner ? state.result.winner === state.player_id ? 'Victory is yours.' : 'You lost this battle.' : state.result?.reason === 'battle' || state.result?.reason === 'timeout' ? 'A draw.' : 'Match ended.'}</h2><p>{state.result?.message || 'Your battle is complete. A new team awaits.'}</p><div className="terminal-buttons"><button className="primary" disabled={busy} onClick={() => lobby()}>Play again</button><button className="secondary" onClick={() => navigation(null)}>Exit to lobby</button></div></section>}
        {state.events.length > 0 && <section className="panel battle-log"><h3>Battle journal</h3><ol aria-label="Battle events">{state.events.slice(-20).map((event, i) => <li key={i}>{event.replaceAll(state.player_id, 'You').replaceAll(opponent || '___', 'Opponent')}</li>)}</ol></section>}
        {state.phase !== 'terminal' && <button className="leave" disabled={busy || !connected} onClick={() => mutate('leave')}>Leave match</button>}
      </>}
    </main><footer>Original creatures. Shared imagination. <span>Level 50 · Two creatures per team</span></footer>
  </div></MotionConfig>;
}

function CreatureCard({ creature: c }: { creature: Creature }) {
  return <div className="creature-card"><div className="sprite-stage"><img src={c.sprite} alt={c.name} width={256} height={256}/></div><h3>{c.name}</h3><div className="types">{c.types.map(t => <span key={t}>{t}</span>)}</div><div className="hp-track" role="progressbar" aria-label={`${c.name} HP`} aria-valuemin={0} aria-valuemax={c.max_hp} aria-valuenow={c.current_hp}><div style={{ width: `${100 * c.current_hp / c.max_hp}%` }}/></div><p className="hp-label">{c.current_hp} / {c.max_hp} HP · {c.current_hp === 0 ? 'Fainted' : c.status ? `${c.status}${c.status === 'sleep' ? ` (${c.sleep_actions} actions)` : ''}` : 'Healthy'}</p></div>;
}
function Reserves({ team, active }: { team: (Creature | null)[]; active: number }) {
  return <div className="reserve">{team.map((c, i) => c && i !== active && <span key={c.id}>Reserve: {c.name} · {c.current_hp === 0 ? 'Fainted' : `${c.current_hp}/${c.max_hp} HP${c.status ? ` · ${c.status}` : ''}`}</span>)}</div>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
