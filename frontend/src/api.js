// Thin client for the Rune Goblin FastAPI backend.
const BASE = import.meta.env.VITE_API_BASE ?? "";

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

export const newGame = () => post("/api/new");
export const castSpell = (sessionId, runes) =>
  post("/api/cast", { session_id: sessionId, runes });
