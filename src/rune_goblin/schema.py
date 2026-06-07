"""Pydantic schema for the spell result JSON the model must emit.

The model *proposes* a spell outcome; the game engine clamps the numeric
deltas to safe ranges (see ``engine.clamp_spell``). Validation here is what
turns "the model wrote some text" into "a legal game action".
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field, field_validator


class SpellResult(BaseModel):
    """The canonical spell-outcome object (section 8.1 / 2)."""

    spell_name: str = Field(..., min_length=1, max_length=80)
    spell_type: str = Field(default="generic", max_length=40)
    flavor: str = Field(default="", max_length=400)
    effect: str = Field(..., max_length=400)
    side_effect: str = Field(default="", max_length=400)
    enemy_hp_delta: int = Field(default=0)
    player_hp_delta: int = Field(default=0)
    status_effects: list[str] = Field(default_factory=list)
    chaos: int = Field(default=0, ge=0, le=10)

    @field_validator("enemy_hp_delta", "player_hp_delta")
    @classmethod
    def _clamp_delta(cls, v: int) -> int:
        # Hard bound proposals so a single spell can never one-shot anything.
        return max(-10, min(10, int(v)))

    @field_validator("status_effects", mode="before")
    @classmethod
    def _coerce_statuses(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return list(v)

    def to_compact_json(self) -> str:
        """Serialize exactly the way training targets are serialized."""
        return json.dumps(self.model_dump(), ensure_ascii=False, separators=(",", ":"))


class VisualReading(BaseModel):
    """What the vision model saw on the drawn spell canvas."""

    detected_runes: list[str] = Field(default_factory=list)
    ambiguous_runes: list[str] = Field(default_factory=list)
    drawing_style: str = Field(default="", max_length=200)
    layout: str = Field(default="", max_length=200)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)

    @field_validator("detected_runes", "ambiguous_runes", "notes", mode="before")
    @classmethod
    def _coerce_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return list(v)


class VisionSpellResult(BaseModel):
    """Nested JSON emitted by the MiniCPM-V Rune Goblin fine-tune."""

    visual_reading: VisualReading = Field(default_factory=VisualReading)
    spell: SpellResult

    def to_compact_json(self) -> str:
        return json.dumps(self.model_dump(), ensure_ascii=False, separators=(",", ":"))


def try_parse_spell(text: str) -> SpellResult | None:
    """Best-effort parse of model output into a :class:`SpellResult`.

    Returns ``None`` if no valid spell can be recovered even after JSON repair.
    """
    candidate = _extract_json(text)
    if candidate is None:
        return None
    try:
        return SpellResult.model_validate(candidate)
    except Exception:
        return None


def try_parse_vision_spell(text: str) -> VisionSpellResult | None:
    """Best-effort parse of vision-model output into the nested schema."""
    candidate = _extract_json(text)
    if candidate is None:
        return None
    try:
        if "spell" not in candidate:
            candidate = {"visual_reading": {}, "spell": candidate}
        return VisionSpellResult.model_validate(candidate)
    except Exception:
        return None


def _extract_json(text: str) -> dict | None:
    """Pull the first balanced ``{...}`` object out of arbitrary model text."""
    text = text.strip()
    # Fast path: the whole thing is JSON.
    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                blob = text[start : i + 1]
                try:
                    return json.loads(blob)
                except Exception:
                    return None
    return None


# A safe, always-valid fallback spell for when the model produces garbage.
FALLBACK_SPELL = SpellResult(
    spell_name="Fizzle of Mild Disappointment",
    spell_type="fallback",
    flavor="The runes shrug at each other and decline to cooperate.",
    effect="Nothing much happens. The dungeon judges you quietly.",
    side_effect="You lose a little dignity.",
    enemy_hp_delta=0,
    player_hp_delta=0,
    status_effects=[],
    chaos=1,
)

FALLBACK_VISION_SPELL = VisionSpellResult(
    visual_reading=VisualReading(
        detected_runes=[],
        ambiguous_runes=[],
        drawing_style="unreadable canvas",
        layout="unknown",
        confidence=0.0,
        notes=["vision_model_unavailable_or_invalid_json"],
    ),
    spell=FALLBACK_SPELL.model_copy(),
)
