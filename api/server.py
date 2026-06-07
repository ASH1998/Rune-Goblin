"""FastAPI backend powering the React/Vite frontend.

Holds in-memory game sessions and exposes the same game logic the Gradio app
uses. Sessions are ephemeral (fine for a hackathon demo / single player).

Run::

    uv run uvicorn api.server:app --reload --port 8000
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from rune_goblin.game import Game  # noqa: E402

USE_MODEL = os.environ.get("RG_USE_MODEL", "0") == "1"

app = FastAPI(title="Rune Goblin API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_SESSIONS: dict[str, Game] = {}


class CastRequest(BaseModel):
    session_id: str
    runes: list[str]


@app.post("/api/new")
def new_game() -> dict:
    sid = uuid.uuid4().hex
    game = Game.new(use_model=USE_MODEL)
    _SESSIONS[sid] = game
    return {"session_id": sid, **game.snapshot()}


@app.get("/api/state/{session_id}")
def get_state(session_id: str) -> dict:
    game = _SESSIONS.get(session_id)
    if game is None:
        raise HTTPException(404, "unknown session")
    return {"session_id": session_id, **game.snapshot()}


@app.post("/api/cast")
def cast(req: CastRequest) -> dict:
    game = _SESSIONS.get(req.session_id)
    if game is None:
        raise HTTPException(404, "unknown session")
    runes = [r for r in req.runes if r][:4]
    if not runes:
        raise HTTPException(400, "pick at least one rune")
    spell = game.cast(runes)
    return {"session_id": req.session_id, "spell": spell.model_dump(), **game.snapshot()}


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "use_model": USE_MODEL, "sessions": len(_SESSIONS)}
