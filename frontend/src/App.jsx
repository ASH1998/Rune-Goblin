import React, { useEffect, useState } from "react";
import { newGame, castSpell } from "./api.js";

export default function App() {
  const [snap, setSnap] = useState(null);
  const [selected, setSelected] = useState([]);
  const [spell, setSpell] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const start = async () => {
    setError(null);
    setSpell(null);
    setSelected([]);
    try {
      setSnap(await newGame());
    } catch (e) {
      setError(`Backend unreachable. Start it with: uv run uvicorn api.server:app --port 8000`);
    }
  };

  useEffect(() => {
    start();
  }, []);

  const toggleRune = (key) => {
    setSelected((cur) => {
      if (cur.includes(key)) return cur.filter((k) => k !== key);
      if (cur.length >= 4) return cur;
      return [...cur, key];
    });
  };

  const cast = async () => {
    if (!snap || selected.length === 0 || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await castSpell(snap.session_id, selected);
      setSpell(res.spell);
      setSnap(res);
      setSelected([]);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!snap) {
    return (
      <div className="wrap">
        <h1>🪄 Rune Goblin</h1>
        <p className="muted">{error ?? "Summoning the dungeon…"}</p>
      </div>
    );
  }

  const { enemy, player, room, runes, log } = snap;

  return (
    <div className="wrap">
      <header>
        <h1>🪄 Rune Goblin</h1>
        <p className="tag">Draw forbidden spells. Regret efficiently.</p>
      </header>

      <div className="cards">
        <section className="card enemy">
          <h2>👹 {enemy.name}</h2>
          <Bar value={enemy.hp} max={enemy.max_hp} kind="hp" />
          <p className="muted">
            weak: <b>{enemy.weakness.join(", ")}</b> · resists: {enemy.resistance.join(", ")}
          </p>
          <p className="mood">mood: {enemy.mood}</p>
        </section>

        <section className="card player">
          <h2>
            🧙 You — Room {room.index + 1}/{room.total}
          </h2>
          <p className="room">{room.name}</p>
          <Bar value={player.hp} max={player.max_hp} kind="health" />
          <p className="muted">score: {snap.score} · 🎒 {player.inventory.join(", ") || "empty"}</p>
        </section>
      </div>

      <div className="board">
        {runes.map((r) => (
          <button
            key={r.key}
            className={`rune ${selected.includes(r.key) ? "on" : ""}`}
            onClick={() => toggleRune(r.key)}
            title={r.label}
          >
            <span className="sym">{r.symbol}</span>
            <span className="lbl">{r.label}</span>
          </button>
        ))}
      </div>

      <div className="selected">{selected.join(" + ") || "pick 2–4 runes"}</div>

      <div className="actions">
        <button className="cast" disabled={busy || snap.over} onClick={cast}>
          {busy ? "casting…" : "🔮 CAST SPELL"}
        </button>
        <button onClick={() => setSelected([])}>clear</button>
        <button onClick={start}>new run</button>
      </div>

      {spell && (
        <div className="result">
          <h3>✨ {spell.spell_name}</h3>
          <p className="flavor">{spell.flavor}</p>
          <p>{spell.effect}</p>
          {spell.side_effect && <p className="side">⚠ {spell.side_effect}</p>}
          <p className="muted">
            enemy {spell.enemy_hp_delta} · player {spell.player_hp_delta} · chaos {spell.chaos}/10
          </p>
        </div>
      )}

      {snap.over && (
        <div className={`banner ${snap.won ? "win" : "lose"}`}>
          {snap.won ? "🏆 You survived the dungeon!" : "💀 You collapsed."} Score: {snap.score}
        </div>
      )}

      <pre className="log">{log.join("\n")}</pre>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

function Bar({ value, max, kind }) {
  const pct = Math.max(0, Math.round((value / max) * 100));
  return (
    <div className="bar">
      <div className={`fill ${kind}`} style={{ width: `${pct}%` }} />
      <span>
        {value}/{max}
      </span>
    </div>
  );
}
