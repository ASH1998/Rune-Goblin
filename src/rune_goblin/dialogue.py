"""Interactive NPC dialogue, powered by the *base* MiniCPM-V-4.6 GGUF model.

The fine-tuned ``goblinV1`` model reads drawn runes (vision). For talking to
NPCs we want the **normal/base** ``openbmb/MiniCPM-V-4.6-gguf`` model doing
plain text generation, exactly as the goal requests.

Design (per ``game_plans/story_plan.md``):

* Input is *explicit state only* — area, scene, target, player state, the
  player's action, and the allowlisted story flags. No hidden memory.
* Output is short JSON: ``story_toast`` / ``npc_line`` / ``journal_entry`` /
  ``suggested_story_flag`` / ``mood_shift`` — all length-limited and the flag
  filtered against the allowlist before it can affect the world.
* If the model is missing or misbehaves, we fall back to the deterministic
  voice tables in :mod:`rune_goblin.story` so the game never stalls.

Enable the live model with ``RG_USE_DIALOGUE_MODEL=1`` and point
``RG_DIALOGUE_MODEL`` at a base MiniCPM-V-4.6 ``.gguf`` (a text-only Llama load,
no multimodal projector). Otherwise the fallback tables drive every line.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

from . import story

# Length limits (story_plan.md "Output Limits").
MAX_TOAST = 140
MAX_NPC = 240
MAX_JOURNAL = 420

DIALOGUE_SYSTEM = (
    "You are the story voice for Rune Goblin, a funny but sincere dungeon "
    "crawler. Write clear, short fantasy dialogue for normal players. The world "
    "is strange, but objectives must be understandable.\n"
    "Rules:\n"
    "- Use only the provided state.\n"
    "- Do not invent items, quests, exits, rewards, or damage.\n"
    "- React to the player's concrete action and known story flags.\n"
    "- Keep text short. Put useful information before jokes.\n"
    "- If a character speaks, preserve their personality.\n"
    "- Return valid JSON only with fields: story_toast, npc_line, "
    "journal_entry, suggested_story_flag, mood_shift."
)

# Default search paths for a base MiniCPM-V-4.6 text GGUF (normal, not goblinV1).
_DEFAULT_DIALOGUE_PATHS = (
    "models/MiniCPM-V-4.6-gguf/ggml-model-Q4_K_M.gguf",
    "models/MiniCPM-V-4_6-gguf/Model-7.6B-Q4_K_M.gguf",
    "models/MiniCPM-V-4.6-gguf/MiniCPM-V-4_6-Q4_K_M.gguf",
)

_LAST_ERROR = ""


def _dialogue_model_path() -> str | None:
    env = os.environ.get("RG_DIALOGUE_MODEL")
    if env:
        return env if Path(env).exists() else None
    for p in _DEFAULT_DIALOGUE_PATHS:
        if Path(p).exists():
            return p
    return None


def model_status() -> dict:
    """Diagnostics for the dialogue model (surfaced via /rg/ping)."""
    return {
        "enabled": os.environ.get("RG_USE_DIALOGUE_MODEL", "0") == "1",
        "model_path": _dialogue_model_path(),
        "last_error": _LAST_ERROR,
    }


@lru_cache(maxsize=1)
def _get_text_model():
    """Lazily build a text-only llama.cpp model from the base GGUF, or None."""
    global _LAST_ERROR
    if os.environ.get("RG_USE_DIALOGUE_MODEL", "0") != "1":
        _LAST_ERROR = "dialogue model disabled (set RG_USE_DIALOGUE_MODEL=1)"
        return None
    path = _dialogue_model_path()
    if not path:
        _LAST_ERROR = "no base MiniCPM-V-4.6 gguf found (set RG_DIALOGUE_MODEL)"
        return None
    try:
        from llama_cpp import Llama

        model = Llama(
            model_path=path,
            n_ctx=int(os.environ.get("RG_GGUF_CTX", "4096")),
            n_gpu_layers=int(os.environ.get("RG_GGUF_GPU_LAYERS", "-1")),
            chat_format=os.environ.get("RG_DIALOGUE_CHAT_FORMAT", "chatml"),
            verbose=os.environ.get("RG_GGUF_VERBOSE", "0") == "1",
        )
        _LAST_ERROR = ""
        return model
    except Exception as exc:  # noqa: BLE001 - never let dialogue crash the game
        _LAST_ERROR = f"{type(exc).__name__}: {exc}"
        print(f"[dialogue] base model unavailable, using fallback tables: {_LAST_ERROR}")
        return None


def _user_payload(area, scene, target, player, action, allowed_flags) -> str:
    return (
        f"Current area: {area}\n"
        f"Scene: {scene}\n"
        f"Target: {json.dumps(target)}\n"
        f"Player state: {json.dumps(player)}\n"
        f"Recent action: {json.dumps(action)}\n"
        f"Allowed story flags: {', '.join(allowed_flags)}\n"
        "Needed output fields: story_toast, npc_line, journal_entry, "
        "suggested_story_flag, mood_shift\n"
        "Return JSON only."
    )


def _extract_json(text: str) -> dict:
    """Best-effort JSON parse with brace-substring repair."""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except (ValueError, TypeError):
            return {}
    return {}


def _clip(s, n: int) -> str:
    s = "" if s is None else str(s)
    return s[:n].strip()


def sanitize(raw: dict, npc_id: str, runes) -> dict:
    """Validate + clamp model output; fall back per-field where missing."""
    fb = story.fallback_dialogue(npc_id, runes)
    flag = _clip(raw.get("suggested_story_flag"), 60)
    if not story.is_allowed_flag(flag):
        flag = ""
    return {
        "story_toast": _clip(raw.get("story_toast"), MAX_TOAST),
        "npc_line": _clip(raw.get("npc_line"), MAX_NPC) or fb["npc_line"],
        "journal_entry": _clip(raw.get("journal_entry"), MAX_JOURNAL) or fb["journal_entry"],
        "suggested_story_flag": flag,
        "mood_shift": _clip(raw.get("mood_shift"), 60),
        "source": "model",
    }


def generate_dialogue(
    *,
    area: str,
    scene: str,
    target: dict,
    player: dict,
    action: dict,
) -> dict:
    """Produce a validated dialogue payload for an NPC interaction.

    Tries the base MiniCPM model; always returns a usable, length-bounded dict
    (deterministic fallback if the model is absent or output is unusable).
    """
    npc_id = str(target.get("id", ""))
    runes = action.get("runes", []) if isinstance(action, dict) else []
    allowed = sorted(story.ALLOWED_FLAGS)

    model = _get_text_model()
    if model is not None:
        try:
            resp = model.create_chat_completion(
                messages=[
                    {"role": "system", "content": DIALOGUE_SYSTEM},
                    {"role": "user", "content": _user_payload(
                        area, scene, target, player, action, allowed)},
                ],
                response_format={"type": "json_object"},
                max_tokens=int(os.environ.get("RG_DIALOGUE_MAX_TOKENS", "256")),
                temperature=float(os.environ.get("RG_DIALOGUE_TEMPERATURE", "0.6")),
            )
            content = resp["choices"][0]["message"]["content"]
            parsed = _extract_json(content)
            if parsed:
                return sanitize(parsed, npc_id, runes)
        except Exception as exc:  # noqa: BLE001
            print(f"[dialogue] generation failed, using fallback: {exc}")

    out = story.fallback_dialogue(npc_id, runes)
    out["source"] = "fallback"
    return out
