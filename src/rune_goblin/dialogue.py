"""Interactive NPC dialogue for Rune Goblin.

The fine-tuned ``goblinV1`` model reads drawn runes (vision). For talking to
NPCs we generate plain text with a MiniCPM-V-4.6 chat model.

**Active backend: hosted OpenAI-compatible API.** We call a remote vLLM endpoint
(``MiniCPM-V-4.6-Thinking``) over HTTP. It is a *thinking* model: its reply
contains a chain-of-thought followed by a ``</think>`` marker and then the JSON
answer, so we strip everything up to and including ``</think>`` before parsing.
Toggle with ``RG_USE_DIALOGUE_API`` (default on) and configure via
``RG_DIALOGUE_API_URL`` / ``RG_DIALOGUE_API_KEY`` / ``RG_DIALOGUE_API_MODEL``.

The local GGUF path (``_get_text_model`` + the commented branch in
:func:`generate_dialogue`) is kept dormant so we can run fully offline again by
re-enabling it; it is not used while the API is on.

Design (per ``game_plans/story_plan.md``):

* Input is *explicit state only* — area, scene, target, player state, and the
  player's action. No hidden memory.
* Output is short JSON: ``story_toast`` / ``npc_line`` / ``journal_entry`` /
  ``suggested_story_flag`` / ``mood_shift`` — all length-limited. Dialogue is
  flavor-only: ``suggested_story_flag`` is always emptied (the engine owns flags).
* If the model is missing or misbehaves, we fall back to the deterministic
  voice tables in :mod:`rune_goblin.story` so the game never stalls.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

from . import story

# Load .env so RG_DIALOGUE_API_* (and friends) are available without the caller
# having to export them. Must run before the module-level config reads below.
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is a core dep, but never hard-fail
    pass

# Length limits (story_plan.md "Output Limits").
MAX_TOAST = 140
MAX_NPC = 240
MAX_JOURNAL = 420

DIALOGUE_SYSTEM = (
    "You are the story voice for Rune Goblin, a funny but sincere dungeon "
    "crawler. You speak AS one specific named character — never as a narrator "
    "describing them. The world is strange, but the player must always "
    "understand what to do next.\n"
    "Rules:\n"
    "- Stay in the named character's voice. Match the rhythm and humor of the "
    "example lines you are given; vary the wording, keep the personality.\n"
    "- Use only the provided state. Do not invent items, quests, exits, "
    "rewards, damage, NPC names, or facts not present in the persona.\n"
    "- React to the player's concrete action: the runes they cast (and whether "
    "it was kind, scary, or insightful), or that they only came to talk. Use "
    "the recent events for callbacks only when they are listed.\n"
    "- Put useful information before jokes. Keep every field short.\n"
    "- You do NOT control the game. Leave suggested_story_flag empty (\"\"); the "
    "game engine decides all consequences.\n"
    "- Return valid JSON only with fields: story_toast, npc_line, "
    "journal_entry, suggested_story_flag, mood_shift."
)

_LAST_ERROR = ""

# ---------------------------------------------------------------------------
# Remote dialogue backend — hosted vLLM, OpenAI-compatible (ACTIVE path).
# ---------------------------------------------------------------------------
# Operational config has safe defaults; the secret key comes ONLY from the
# environment / gitignored .env so it never lands in committed source.
DIALOGUE_API_URL = os.environ.get(
    "RG_DIALOGUE_API_URL", "http://35.203.155.71:8003/v1/chat/completions")
DIALOGUE_API_KEY = os.environ.get("RG_DIALOGUE_API_KEY", "")
DIALOGUE_API_MODEL = os.environ.get("RG_DIALOGUE_API_MODEL", "MiniCPM-V-4.6")


def _use_api() -> bool:
    return os.environ.get("RG_USE_DIALOGUE_API", "1") == "1"


def _strip_thinking(text: str) -> str:
    """Drop a MiniCPM 'Thinking' chain-of-thought, keeping the answer after it.

    The thinking model streams reasoning, a ``</think>`` marker, then the JSON.
    Some builds also wrap it as ``<think>...</think>``; we keep only what follows
    the final ``</think>``.
    """
    if not text:
        return ""
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    return text.strip()


def _remote_chat(messages: list[dict]) -> str | None:
    """POST to the hosted OpenAI-compatible endpoint; return raw content or None.

    Never raises: any network/parse failure records ``_LAST_ERROR`` and returns
    None so the caller falls back to the deterministic voice tables.
    """
    global _LAST_ERROR
    import urllib.request

    body = json.dumps({
        "model": DIALOGUE_API_MODEL,
        "messages": messages,
        "temperature": float(os.environ.get("RG_DIALOGUE_TEMPERATURE", "0.6")),
        # Non-thinking model answers JSON directly (~80-150 tok). Modest headroom;
        # the model stops on its own so a slightly higher ceiling costs no latency.
        "max_tokens": int(os.environ.get("RG_DIALOGUE_MAX_TOKENS", "512")),
    }).encode("utf-8")
    req = urllib.request.Request(
        DIALOGUE_API_URL, data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {DIALOGUE_API_KEY}"})
    try:
        timeout = float(os.environ.get("RG_DIALOGUE_API_TIMEOUT", "30"))
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        _LAST_ERROR = ""
        return data["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001 - never let dialogue crash the game
        _LAST_ERROR = f"{type(exc).__name__}: {exc}"
        print(f"[dialogue] remote API failed, using fallback: {_LAST_ERROR}")
        return None


def model_status() -> dict:
    """Diagnostics for the dialogue model (surfaced via /rg/ping)."""
    return {
        "enabled": _use_api(),
        "model_path": f"{DIALOGUE_API_MODEL} @ {DIALOGUE_API_URL}",
        "last_error": _LAST_ERROR,
    }


# ---------------------------------------------------------------------------
# Local GGUF backend (DORMANT). Kept for fully-offline use — re-enable by
# setting RG_USE_DIALOGUE_API=0 and uncommenting the local branch in
# generate_dialogue(). The helpers below are unused while the API is active.
# ---------------------------------------------------------------------------
_DEFAULT_DIALOGUE_PATHS = (
    "models/MiniCPM-V-4.6-gguf/ggml-model-Q4_K_M.gguf",
    "models/MiniCPM-V-4_6-gguf/Model-7.6B-Q4_K_M.gguf",
    "models/MiniCPM-V-4.6-gguf/MiniCPM-V-4_6-Q4_K_M.gguf",
)


def _dialogue_model_path() -> str | None:
    env = os.environ.get("RG_DIALOGUE_MODEL")
    if env:
        return env if Path(env).exists() else None
    for p in _DEFAULT_DIALOGUE_PATHS:
        if Path(p).exists():
            return p
    return None


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


# How a rune-intent reads in plain words, so the model reacts to the *meaning*
# of the cast rather than raw rune keys.
_INTENT_GLOSS = {
    "kind": "a gentle, healing or calming spell",
    "fear": "a scary, damaging or aggressive spell",
    "insight": "a revealing, reflective or truth-seeing spell",
    "coin": "an offer of payment (a coin)",
    "bell": "the ringing of a bell",
    "neutral": "a plain, unremarkable cast",
}


def _persona_block(npc_id: str, intent: str) -> str:
    """Describe the character the model must voice, using the canonical tables.

    Pulls the deterministic voice from :data:`story.NPC_VOICES` so generated
    lines match the character the player already knows. The intent-matched
    reaction is the strongest steer (it usually carries the real quest hint);
    one extra line shows tonal range.
    """
    voice = story.NPC_VOICES.get(npc_id)
    if voice is None:
        return ""
    lines = [
        f"You are speaking AS this character: {voice.name}.",
        f'{voice.name} usually opens with: "{voice.greeting}"',
    ]
    reaction = voice.reactions.get(intent)
    if reaction:
        lines.append(
            f'When the player responds with {_INTENT_GLOSS.get(intent, intent)}, '
            f'{voice.name} says something like: "{reaction}"'
        )
    others = [v for k, v in voice.reactions.items() if k != intent and v != reaction]
    if others:
        lines.append(f'{voice.name} might also say: "{others[0]}"')
    if voice.journal:
        lines.append(f"Fact {voice.name} can truthfully reveal: {voice.journal}")
    return "\n".join(lines)


def _user_payload(area, scene, target, player, action, persona, intent) -> str:
    recent = player.get("recent_story_events") or []
    recent_str = "; ".join(
        e.get("text", "") if isinstance(e, dict) else str(e) for e in recent[-3:]
    ) or "none yet"
    cast_a_spell = bool(action.get("runes")) if isinstance(action, dict) else False
    toast_rule = (
        "The story_toast narrates the spell's effect in one short line."
        if cast_a_spell
        else "The player only talked (no spell), so story_toast must be empty (\"\")."
    )
    return (
        f"{persona}\n\n"
        f"Current area: {area}\n"
        f"Scene: {scene}\n"
        f"Target: {json.dumps(target)}\n"
        f"Player state: {json.dumps(player)}\n"
        f"The player's action this moment: {json.dumps(action)} "
        f"(this reads as {_INTENT_GLOSS.get(intent, intent)}).\n"
        f"Recent story events (for callbacks only): {recent_str}\n"
        f"{toast_rule}\n"
        "Write the character's reply now. Needed output fields: story_toast, "
        "npc_line, journal_entry, suggested_story_flag (leave empty), "
        "mood_shift.\n"
        "Return JSON only."
    )


# Placeholder strings small models sometimes emit instead of leaving a field
# blank. Dropped so they never reach the player as flavor text.
_PLACEHOLDER_TEXT = frozenset({
    "no toast yet", "none", "n/a", "na", "null", "none yet", "no toast",
    "no journal entry", "no flag", "todo", "...", "…",
})


def _drop_placeholder(s: str) -> str:
    return "" if s.strip().lower().rstrip(".!") in _PLACEHOLDER_TEXT else s


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
    """Validate + clamp model output; fall back per-field where missing.

    Flavor-only: the model never sets durable game state. ``suggested_story_flag``
    is always emptied here — story flags are owned exclusively by the
    deterministic engine (:func:`rune_goblin.world.resolve_world_cast`), which
    sets them from the runes actually cast. This closes the path where a chatty
    model could fabricate a flag (e.g. ``queue_goblin_forced`` on a plain talk)
    and corrupt the ending logic.
    """
    fb = story.fallback_dialogue(npc_id, runes)
    return {
        "story_toast": _drop_placeholder(_clip(raw.get("story_toast"), MAX_TOAST)),
        "npc_line": _drop_placeholder(_clip(raw.get("npc_line"), MAX_NPC)) or fb["npc_line"],
        "journal_entry": _drop_placeholder(_clip(raw.get("journal_entry"), MAX_JOURNAL)) or fb["journal_entry"],
        "suggested_story_flag": "",  # flavor-only; engine owns flags
        "mood_shift": _drop_placeholder(_clip(raw.get("mood_shift"), 60)),
        "source": "model",
        "model": DIALOGUE_API_MODEL,
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
    intent = story.npc_intent(runes)
    persona = _persona_block(npc_id, intent)
    messages = [
        {"role": "system", "content": DIALOGUE_SYSTEM},
        {"role": "user", "content": _user_payload(
            area, scene, target, player, action, persona, intent)},
    ]

    # Active backend: hosted OpenAI-compatible API (thinking model -> strip CoT).
    if _use_api():
        content = _remote_chat(messages)
        if content:
            parsed = _extract_json(_strip_thinking(content))
            if parsed:
                return sanitize(parsed, npc_id, runes)

    # --- DORMANT: local GGUF dialogue model (uncomment to run fully offline) ---
    # model = _get_text_model()
    # if model is not None:
    #     try:
    #         resp = model.create_chat_completion(
    #             messages=messages,
    #             response_format={"type": "json_object"},
    #             max_tokens=int(os.environ.get("RG_DIALOGUE_MAX_TOKENS", "256")),
    #             temperature=float(os.environ.get("RG_DIALOGUE_TEMPERATURE", "0.6")),
    #         )
    #         content = resp["choices"][0]["message"]["content"]
    #         parsed = _extract_json(content)
    #         if parsed:
    #             return sanitize(parsed, npc_id, runes)
    #     except Exception as exc:  # noqa: BLE001
    #         print(f"[dialogue] local generation failed, using fallback: {exc}")

    out = story.fallback_dialogue(npc_id, runes)
    out["source"] = "fallback"
    return out
