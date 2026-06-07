"""Prompt formatting shared by dataset generation, training and inference.

Keeping this in one place guarantees the model is *trained* on exactly the
string format it is *queried* with at game time.
"""

from __future__ import annotations

from .engine import GameState

SYSTEM_PROMPT = (
    "You are Rune Goblin, a tiny dungeon spell engine. Interpret RuneLang glyph "
    "sequences and the current game state, then output a single valid JSON object "
    "describing the spell outcome. Output JSON only — no prose, no markdown."
)


def format_state_user_message(state: GameState, runes: list[str]) -> str:
    """Build the user turn (matches section 8.1 of the plan)."""
    inv = ", ".join(state.inventory) if state.inventory else "empty"
    return (
        f"STATE: player_hp={state.player_hp} enemy={state.enemy_name} "
        f"enemy_hp={state.enemy_hp} weakness={'/'.join(state.weakness)} "
        f"resistance={'/'.join(state.resistance)} room_mood={state.room_mood} "
        f"inventory=[{inv}]\n"
        f"RUNES: {', '.join(runes)}\n"
        f"Return spell result."
    )


def build_chat_messages(state: GameState, runes: list[str], assistant: str | None = None) -> list[dict]:
    """Assemble the chat-format messages list used for SFT and inference."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": format_state_user_message(state, runes)},
    ]
    if assistant is not None:
        messages.append({"role": "assistant", "content": assistant})
    return messages
