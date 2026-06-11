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

from . import beats as beats_mod
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
    "describing them. The world is strange, but every line you write must be "
    "instantly understandable to a casual player.\n"
    "Rules:\n"
    "- CLARITY FIRST. Use short, complete sentences and everyday words. A "
    "player who knows nothing about the lore must understand the line on the "
    "first read. At most one metaphor per reply; never stack strange images.\n"
    "- Always do these two jobs, in order: (1) react plainly to what the "
    "player just did, (2) when it fits the character, nudge them toward their "
    "current objective (it is given to you — use its plain wording).\n"
    "- npc_line is the character's SPOKEN WORDS ONLY, in first person — like "
    "a line of dialogue in a script. Never describe the character, never "
    "write \"X says\" or \"X is upset\", never narrate.\n"
    "- Stay in the named character's voice. Match the rhythm and humor of the "
    "example lines you are given; vary the wording, keep the personality.\n"
    "- Use only the provided state. Do not invent items, quests, exits, "
    "rewards, damage, NPC names, or facts not present in the persona.\n"
    "- Never tell the player to avoid or skip their current objective.\n"
    "- journal_entry records only what ACTUALLY happened in this moment, in "
    "past tense (a thing said, learned, or done). Never claim the player "
    "found, received, or completed something unless the state says so.\n"
    "- Never echo internal data: no flag names, no JSON keys, no stat numbers.\n"
    "- Joke second: the joke may decorate the information, never replace it.\n"
    "- You do NOT control the game. Leave suggested_story_flag empty (\"\"); the "
    "game engine decides all consequences.\n"
    "- Return valid JSON only with fields: story_toast, npc_line, "
    "journal_entry, suggested_story_flag, mood_shift.\n"
    "Example of a GOOD npc_line (clear action-react + objective + light joke): "
    '"That coin settles your toll. The road to the caverns is open — the '
    'Calendar Shard is down there, try not to break anything else."\n'
    "Example of a BAD npc_line (vague, lore-soup, no direction): "
    '"The spiral of moments unwinds its debt upon the threshold of maybe."'
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
        # Lower default temp: clarity beats variety for a small model.
        "temperature": float(os.environ.get("RG_DIALOGUE_TEMPERATURE", "0.45")),
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


def _story_brief(player: dict, area: str) -> str:
    """Plain-English game context for the model — no JSON, no internal keys.

    A small model writes coherent lines only when it understands where the
    player is in the story; raw state dumps made it parrot keys and produce
    word salad, so everything here is already translated into sentences.
    """
    cls = story.class_or_default(player.get("goblin_class"))
    weapon = story.weapon_or_default(player.get("weapon"))
    history = story.flag_story(player.get("story_flags"))
    history_str = " ".join(history) if history else "Nothing notable has happened yet."
    return (
        f"Where we are in the story: {story.story_chapter(player)}.\n"
        f"Current area: {area}.\n"
        f"The player is the {cls.label} (level {player.get('level', 1)}), "
        f"carrying the {weapon.label}.\n"
        f"What the player has done so far: {history_str}\n"
        f"The player's current objective: {story.main_objective(player)}"
    )


def _target_brief(target: dict) -> str:
    name = target.get("name") or "someone"
    ttype = target.get("type") or "npc"
    state = target.get("state")
    bits = [f"The player is talking to {name} (a {ttype}"]
    if state and state not in ("idle", "active"):
        bits.append(f", currently {state}")
    bits.append(").")
    return "".join(bits)


def _action_brief(action: dict, intent: str) -> str:
    runes = action.get("runes") or [] if isinstance(action, dict) else []
    if runes:
        names = ", ".join(r.replace("_", " ") for r in runes)
        return (f"The player just cast the runes [{names}] at them — this "
                f"reads as {_INTENT_GLOSS.get(intent, intent)}.")
    return "The player did not cast anything; they only came over to talk."


def _user_payload(area, scene, target, player, action, persona, intent) -> str:
    recent = player.get("recent_story_events") or []
    recent_str = "; ".join(
        e.get("text", "") if isinstance(e, dict) else str(e) for e in recent[-3:]
    ) or "none yet"
    cast_a_spell = bool(action.get("runes")) if isinstance(action, dict) else False
    toast_rule = (
        "The story_toast narrates the spell's visible effect in one short "
        "line, in narrator voice, addressing the player as \"you\" (e.g. "
        "\"Your flames send the Tourist scrambling.\")."
        if cast_a_spell
        else "The player only talked (no spell), so story_toast must be empty (\"\")."
    )
    # The canonical intent-matched reaction goes LAST: small models weight the
    # end of the prompt hardest, and this line carries the real meaning the
    # reply must keep (e.g. a coin PLEASES the Queue Goblin).
    voice = story.NPC_VOICES.get(str(target.get("id", "")))
    steer = ""
    if voice is not None:
        canonical = voice.reactions.get(intent) or voice.greeting
        steer = (
            f'A correct reaction for {voice.name} in this moment is: '
            f'"{canonical}"\n'
            f"Your npc_line must KEEP THAT MEANING and attitude — do not "
            f"soften, invert, or contradict it. Write a fresh variation of it "
            f"in {voice.name}'s spoken words, first person, 1-2 short clear "
            f"sentences.\n"
        )
    return (
        f"{persona}\n\n"
        f"{_story_brief(player, area)}\n\n"
        f"{_target_brief(target)}\n"
        f"{_action_brief(action, intent)}\n"
        f"Recent story events (for callbacks only): {recent_str}\n"
        f"{toast_rule}\n"
        f"{steer}"
        "Needed output fields: story_toast, npc_line, journal_entry, "
        "suggested_story_flag (leave empty), mood_shift.\n"
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


# ---------------------------------------------------------------------------
# Proactive story beats (game-triggered, no Talk button) — see beats.py
# ---------------------------------------------------------------------------
NARRATOR_SYSTEM = (
    "You are the narrator voice for Rune Goblin, a funny but sincere dungeon "
    "crawler about a junior spell clerk who broke the dungeon calendar. The "
    "world is strange, but the player must always understand what is "
    "happening and what to do next.\n"
    "Rules:\n"
    "- CLARITY FIRST. Short, complete sentences, everyday words. A casual "
    "player must understand the narration on the first read. At most one "
    "metaphor; never stack strange images.\n"
    "- Speak to the player as \"you\". Never write \"the player\".\n"
    "- Every narration does two jobs, in order: (1) say plainly what this "
    "place or moment is, (2) point at the player's current objective using "
    "its plain wording.\n"
    "- The objective names WHERE it happens. Never move it: if the objective "
    "is in another area, do not claim it can be found, bought, or done here.\n"
    "- Use only the provided state and scene direction. Do not invent items, "
    "quests, exits, rewards, NPC names, or facts.\n"
    "- Mention the player's past choices only when they are listed, and "
    "describe them in plain words.\n"
    "- Never echo internal data: no flag names, no JSON keys, no stat numbers.\n"
    "- Joke second: the joke decorates the information, never replaces it.\n"
    "- You do NOT control the game. Leave suggested_story_flag empty (\"\").\n"
    "- Return valid JSON only with fields: story_toast, npc_line, "
    "journal_entry, suggested_story_flag, mood_shift.\n"
    "Example of a GOOD story_toast: \"The Wet Library drips around you. The "
    "Calendar Key is hidden here — it opens for readers, not thieves.\"\n"
    "Example of a BAD story_toast: \"Damp chronicles weep their yesterdays "
    "into the spine of forever.\""
)

MAX_BARK = 160


def _beat_payload(beat, area: str, player: dict) -> str:
    recent = player.get("recent_story_events") or []
    recent_str = "; ".join(
        e.get("text", "") if isinstance(e, dict) else str(e) for e in recent[-3:]
    ) or "none yet"
    if beat.trigger == "first_meet":
        field_rule = (
            "Write ONE short greeting line (under 160 characters) the character "
            "calls out as the player first comes near — it appears as a speech "
            "bubble over their head. It must be a plain, complete sentence a "
            "casual player understands instantly. Put it in npc_line WITHOUT a "
            "name prefix. Leave story_toast empty (\"\")."
        )
    else:
        field_rule = (
            "Write the narration in story_toast (one line, under 140 "
            "characters) that says plainly what this place or moment is and, "
            "where natural, what the player should do here. Also write a "
            "slightly fuller journal_entry the player can reread later. Leave "
            "npc_line empty (\"\")."
        )
    return (
        f"Scene direction: {beat.prompt}\n\n"
        f"{_story_brief(player, area)}\n"
        f"Recent story events (for callbacks only): {recent_str}\n"
        f"{field_rule}\n"
        "Return JSON only."
    )


def sanitize_beat(raw: dict, beat) -> dict:
    """Validate + clamp model output for a beat; fall back per-field."""
    fb = beats_mod.fallback_payload(beat)
    if beat.trigger == "first_meet":
        toast = ""
        bark = _drop_placeholder(_clip(raw.get("npc_line"), MAX_BARK)) or fb["npc_line"]
    else:
        toast = _drop_placeholder(_clip(raw.get("story_toast"), MAX_TOAST)) or fb["story_toast"]
        bark = ""
    return {
        "beat_id": beat.id,
        "kind": beat.trigger,
        "speaker": beat.speaker,
        "story_toast": toast,
        "npc_line": bark,
        "journal_entry": _drop_placeholder(_clip(raw.get("journal_entry"), MAX_JOURNAL)) or fb["journal_entry"],
        "suggested_story_flag": "",  # flavor-only; engine owns flags
        "mood_shift": _drop_placeholder(_clip(raw.get("mood_shift"), 60)),
        "source": "model",
        "model": DIALOGUE_API_MODEL,
    }


def generate_beat(*, beat_id: str, area: str, player: dict) -> dict:
    """Produce a validated story-beat payload, LLM-enriched when possible.

    Returns ``{"skip": True}`` for unknown beats or failed flag conditions so
    a stale/forged client request can never surface wrong-route narration.
    """
    beat = beats_mod.get_beat(beat_id)
    if beat is None or not beats_mod.beat_eligible(beat, player.get("story_flags")):
        return {"skip": True, "beat_id": beat_id}

    # gate_tourist has no voice table entry of its own; the road tourist's fits.
    persona_id = beat.npc if beat.npc in story.NPC_VOICES else (
        "tourist" if beat.npc == "gate_tourist" else "")
    if beat.trigger == "first_meet" and persona_id:
        system = DIALOGUE_SYSTEM
        persona = _persona_block(persona_id, "neutral")
        user = f"{persona}\n\n{_beat_payload(beat, area, player)}"
    else:
        system = NARRATOR_SYSTEM
        user = _beat_payload(beat, area, player)

    if _use_api():
        content = _remote_chat([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        if content:
            parsed = _extract_json(_strip_thinking(content))
            if parsed:
                return sanitize_beat(parsed, beat)

    return beats_mod.fallback_payload(beat)


# ---------------------------------------------------------------------------
# Bone Market pricing — the model haggles INSIDE deterministic bands
# ---------------------------------------------------------------------------
SHOP_PRICER_SYSTEM = (
    "You are the Bone Market Merchant of Rune Goblin setting today's prices. "
    "You are charming, predatory, and fair-ish: you respect customers who "
    "repaid debts and gouge customers carrying curses, and prices creep up "
    "as the world gets closer to ending.\n"
    "Rules:\n"
    "- For each item you are given an allowed price range (min..max). Your "
    "price MUST be an integer inside that range. Never invent items.\n"
    "- For each item write one short haggle line (under 80 characters) in "
    "plain words that explains today's price, referencing the player's deeds "
    "or the state of the world when relevant.\n"
    "- Clarity first: a casual player must understand every line.\n"
    "- Return valid JSON only, shaped: {\"prices\": [{\"id\": \"...\", "
    "\"price\": 4, \"reason\": \"...\"}]}."
)


def _pricer_payload(player: dict, area: str, offers: list[dict]) -> str:
    items = "\n".join(
        f'- id "{o["id"]}" ({o["label"]}): allowed {o["band"][0]}..{o["band"][1]} gold'
        for o in offers
    )
    return (
        f"{_story_brief(player, area)}\n\n"
        f"Today's stock and allowed price ranges:\n{items}\n"
        "Set a price and a haggle line for each item. Return JSON only."
    )


def generate_shop_prices(*, player: dict, area: str, offers: list[dict]) -> dict:
    """LLM-priced stock within engine bands. Returns {wid: {price, reason}}.

    ``offers`` entries need ``id``, ``label`` and ``band`` (lo, hi, anchor).
    Fallback (model off/invalid) is each band's anchor with no haggle line.
    Every model price is clamped back into its band, so the model can flavor
    the economy but never break it.
    """
    fallback = {o["id"]: {"price": o["band"][2], "reason": "", "source": "fallback"}
                for o in offers}
    priced = [o for o in offers if o["band"][1] > 0]
    if not priced or not _use_api():
        return fallback
    content = _remote_chat([
        {"role": "system", "content": SHOP_PRICER_SYSTEM},
        {"role": "user", "content": _pricer_payload(player, area, priced)},
    ])
    if not content:
        return fallback
    parsed = _extract_json(_strip_thinking(content))
    rows = parsed.get("prices") if isinstance(parsed, dict) else None
    if not isinstance(rows, list):
        return fallback
    by_id = {o["id"]: o for o in priced}
    out = dict(fallback)
    for row in rows:
        if not isinstance(row, dict):
            continue
        wid = str(row.get("id", ""))
        o = by_id.get(wid)
        if o is None:
            continue
        lo, hi, anchor = o["band"]
        try:
            price = int(row.get("price", anchor))
        except (TypeError, ValueError):
            price = anchor
        out[wid] = {
            "price": max(lo, min(hi, price)),
            "reason": _drop_placeholder(_clip(row.get("reason"), 90)),
            "source": "model",
        }
    return out


# ---------------------------------------------------------------------------
# Loot christening — the model NAMES a Python-rolled trinket (no stats from it)
# ---------------------------------------------------------------------------
LOOT_NAMER_SYSTEM = (
    "You are the loot-namer for Rune Goblin, a funny but sincere goblin RPG. "
    "Given a trinket's rarity, the area it dropped in, and its mechanical "
    "effects, invent a short evocative name and a one-line flavor description. "
    "Rules:\n"
    "- Name: under 32 characters, no quotes, title-case, a little weird.\n"
    "- Flavor: under 140 characters, one sentence, clear before clever.\n"
    "- Do NOT mention exact numbers or invent new powers.\n"
    "- Return valid JSON only: {\"name\": \"...\", \"flavor\": \"...\"}."
)


def generate_loot_name(*, item_spec: dict, area: str = "") -> dict:
    """Christen a rolled trinket. Returns {name, flavor, source}.

    The stats are decided by Python (``item_spec``); the model only writes
    display text. Any failure falls back to the deterministic rolled name."""
    fb = {"name": item_spec.get("name", "Odd Trinket"),
          "flavor": "", "source": "fallback"}
    if not _use_api():
        return fb
    stats = item_spec.get("stats") or {}
    effects = ", ".join(f"+{v} {k.replace('_', ' ')}" for k, v in stats.items()) or "a faint hum"
    payload = (
        f"Rarity: {item_spec.get('rarity', 'rare')}.\n"
        f"Dropped in: {area or 'the dungeon'}.\n"
        f"Mechanical effects: {effects}.\n"
        "Name this trinket and write one flavor line. JSON only."
    )
    content = _remote_chat([
        {"role": "system", "content": LOOT_NAMER_SYSTEM},
        {"role": "user", "content": payload},
    ])
    if not content:
        return fb
    parsed = _extract_json(_strip_thinking(content))
    name = _drop_placeholder(_clip(parsed.get("name"), 32))
    if not name:
        return fb
    return {"name": name,
            "flavor": _drop_placeholder(_clip(parsed.get("flavor"), 140)),
            "source": "model"}


# ---------------------------------------------------------------------------
# Combat taunts — elites/bosses speak; the model flavors, fallback never blocks
# ---------------------------------------------------------------------------
TAUNT_SYSTEM = (
    "You voice a single enemy in Rune Goblin during a fight. Write ONE short "
    "taunt (under 90 characters) in this enemy's voice for the given moment. "
    "Be funny, menacing, and clear. Reference the player's deeds only when "
    "they fit. No stage directions, no quotes. Return JSON: {\"line\": \"...\"}."
)
_TAUNT_EVENT_HINT = {
    "spotted": "the enemy just noticed the player",
    "windup": "the enemy is winding up a big attack",
    "enrage": "the enemy just dropped below a third of its health and enrages",
    "player_low": "the player is nearly defeated",
    "defeated": "the enemy has just been beaten",
}


def generate_taunt(*, enemy_name: str, archetype: str, event: str,
                   area: str = "", flag_story: list[str] | None = None) -> dict:
    """One in-character combat line for an elite/boss. Returns {line, source}."""
    fb = {"line": story.taunt_fallback(archetype, event), "source": "fallback"}
    if not _use_api():
        return fb
    deeds = " ".join(flag_story or []) or "Nothing notable yet."
    payload = (
        f"Enemy: {enemy_name} (a {archetype}-type).\n"
        f"Area: {area or 'the dungeon'}.\n"
        f"Moment: {_TAUNT_EVENT_HINT.get(event, event)}.\n"
        f"What the player has done so far: {deeds}\n"
        "Write this enemy's one-line taunt. JSON only."
    )
    content = _remote_chat([
        {"role": "system", "content": TAUNT_SYSTEM},
        {"role": "user", "content": payload},
    ])
    if not content:
        return fb
    parsed = _extract_json(_strip_thinking(content))
    line = _drop_placeholder(_clip(parsed.get("line"), 90))
    return {"line": line or fb["line"], "source": "model" if line else "fallback"}
