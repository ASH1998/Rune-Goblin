"""FastAPI routes that bridge the canvas game to the Python spell engine.

Stateless per request: the client owns the world (maps, entities, player) and
sends only the context needed to resolve a cast. Python computes the spell
outcome + world actions and clamps anything that touches gameplay numbers.

Endpoints
---------
GET  /rg/world  -> the full serializable world (areas, entities, player, runes)
POST /rg/cast   -> resolve a rune or drawing cast against the faced target
"""

from __future__ import annotations

import base64
import binascii
import os
from io import BytesIO

from fastapi import FastAPI
from pydantic import BaseModel, Field

# `app/` is on sys.path via rpg_app; `src/` too. Import the game packages.
from rune_goblin.engine import GameState  # noqa: E402
from rune_goblin.world import build_world, resolve_world_cast, validate_world  # noqa: E402

USE_MODEL = os.environ.get("RG_USE_MODEL", "1") == "1"


class CastRequest(BaseModel):
    mode: str = Field(default="runes")  # "runes" | "drawing"
    runes: list[str] = Field(default_factory=list)
    image: str | None = None  # data URL for drawing mode
    player: dict = Field(default_factory=dict)
    target: dict | None = None
    area_name: str | None = None
    seed: int | None = None


class DialogueRequest(BaseModel):
    area: str = ""
    scene: str = "talk"
    target: dict = Field(default_factory=dict)
    player: dict = Field(default_factory=dict)
    action: dict = Field(default_factory=dict)


class QuestRequest(BaseModel):
    npc_id: str = ""
    player: dict = Field(default_factory=dict)


def _decode_image(data_url: str):
    from PIL import Image

    raw = data_url.split(",", 1)[1] if "," in data_url else data_url
    return Image.open(BytesIO(base64.b64decode(raw))).convert("RGB")


def register_routes(app: FastAPI) -> None:
    @app.get("/rg/ping")
    def ping() -> dict:
        from rune_goblin.dialogue import model_status

        problems = validate_world()
        return {"ok": not problems, "msg": "rune goblin online",
                "world_problems": problems, "dialogue_model": model_status()}

    @app.post("/rg/dialogue")
    def dialogue(req: DialogueRequest) -> dict:
        """Interactive NPC dialogue via the base MiniCPM model (+ fallback)."""
        from rune_goblin.dialogue import generate_dialogue

        return generate_dialogue(
            area=req.area, scene=req.scene, target=req.target,
            player=req.player, action=req.action,
        )

    @app.post("/rg/quest")
    def quest(req: QuestRequest) -> dict:
        """Deterministic quest interaction (offer / progress / turn-in / exchange)."""
        from rune_goblin.quests import resolve_quest_talk

        return resolve_quest_talk(req.player, req.npc_id)

    @app.get("/rg/world")
    def world(seed: int | None = None) -> dict:
        return build_world(seed=seed)

    @app.post("/rg/cast")
    def cast(req: CastRequest) -> dict:
        runes = [r for r in (req.runes or []) if r][:4]
        visual = None
        model_spell = None

        if req.mode == "drawing" and req.image:
            try:
                image = _decode_image(req.image)
                from rune_goblin.vision_inference import cast_vision_spell

                t = req.target or {}
                state = GameState(
                    player_hp=req.player.get("hp", 10),
                    player_max_hp=req.player.get("max_hp", 10),
                    enemy_name=t.get("name", "Mirror Fungus"),
                    enemy_hp=t.get("hp", 5), enemy_max_hp=t.get("max_hp", 5),
                    room_mood=t.get("mood", ""),
                    inventory=tuple(req.player.get("inventory", [])),
                    courage=req.player.get("courage", 5),
                )
                result = cast_vision_spell(
                    state, image, room_name=req.area_name, use_model=USE_MODEL
                )
                visual = result.visual_reading
                model_spell = result.spell
                if visual.detected_runes:
                    runes = [r for r in visual.detected_runes if r][:4]
            except (binascii.Error, ValueError, OSError) as exc:
                visual = None
                model_spell = None
                print(f"[rpg_bridge] drawing decode/read failed: {exc}")

        out = resolve_world_cast(runes, req.player, req.target, seed=req.seed)

        # For drawings, borrow the model's personality (name + flavor) over the
        # deterministic outcome, and surface what it read.
        if model_spell is not None:
            if model_spell.spell_name:
                out["spell"]["spell_name"] = model_spell.spell_name
            if model_spell.flavor:
                out["spell"]["flavor"] = model_spell.flavor
        if visual is not None:
            out["visual_reading"] = visual.model_dump()
        out["mode"] = req.mode
        return out
