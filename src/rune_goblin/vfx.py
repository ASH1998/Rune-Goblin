"""Deterministic VFX / asset planner.

The plan (section 11.2 / 21.6) describes a vision model that turns a validated
spell outcome into *render metadata* — colours, projectile shape, particles,
screen shake — which the game then animates from existing assets. No images are
generated at runtime.

For the playable MVP we implement that asset planner as a small rule-based
function instead of a second model: it is instant, deterministic, and never
fails. The signature and the metadata shape are kept close to the schema in the
plan so a real ``MiniCPM-V-4.6`` planner can be dropped in later without
touching the renderer.
"""

from __future__ import annotations

from .runelang import ENEMIES
from .schema import SpellResult

# ---------------------------------------------------------------------------
# Per-rune "school" of magic: palette + glyphs the renderer draws.
# Order in this dict is the priority used to pick a spell's dominant school.
# ---------------------------------------------------------------------------
_SCHOOLS: dict[str, dict] = {
    "flame": {"palette": ["#ff6a00", "#ffd23f", "#fff4d6"], "glyph": "🔥", "particle": "🔥"},
    "jagged_line": {"palette": ["#9be7ff", "#ffffff", "#6ad0ff"], "glyph": "⚡", "particle": "✦"},
    "spiral": {"palette": ["#b07cff", "#6df5ff", "#ffffff"], "glyph": "🌀", "particle": "🌀"},
    "tooth": {"palette": ["#ff8fa3", "#ffd6dd", "#fff"], "glyph": "🦷", "particle": "✦"},
    "bone": {"palette": ["#ece4cf", "#b9b09a", "#fff"], "glyph": "💀", "particle": "🦴"},
    "three_dots": {"palette": ["#7bd66a", "#caffb0", "#fff"], "glyph": "🐝", "particle": "•"},
    "wave": {"palette": ["#4fc3ff", "#bdecff", "#fff"], "glyph": "🌊", "particle": "💧"},
    "leaf": {"palette": ["#6df5a0", "#d6ffe0", "#fff"], "glyph": "🍃", "particle": "🍃"},
    "closed_circle": {"palette": ["#ffce6b", "#fff3c4", "#fff"], "glyph": "🛡", "particle": "✦"},
    "mirror": {"palette": ["#cfd8ff", "#ffffff", "#aeb9ff"], "glyph": "🪞", "particle": "✦"},
    "bell": {"palette": ["#ffd24a", "#fff6c9", "#fff"], "glyph": "🔔", "particle": "♪"},
    "thread": {"palette": ["#d59bff", "#f0d6ff", "#fff"], "glyph": "🧵", "particle": "·"},
    "coin": {"palette": ["#ffd700", "#fff2a8", "#fff"], "glyph": "🪙", "particle": "🪙"},
    "eye": {"palette": ["#9be7ff", "#e7d9ff", "#fff"], "glyph": "👁", "particle": "✦"},
    "key": {"palette": ["#ffce6b", "#e7d9ff", "#fff"], "glyph": "🗝", "particle": "✦"},
    "broken_mark": {"palette": ["#ff3d6e", "#b07cff", "#1a0010"], "glyph": "💢", "particle": "✶"},
}

_GENERIC = {"palette": ["#b07cff", "#e7d9ff", "#fff"], "glyph": "✨", "particle": "✦"}

# Enemy reaction faces shown briefly on impact.
_REACTION = {
    "hurt": "😣",
    "confused": "😵",
    "burning": "🥵",
    "soothed": "😌",
    "feared": "😱",
    "shielded": "🛡",
    "none": "",
}


def _dominant_school(spell: SpellResult, runes: list[str]) -> dict:
    """Pick the palette/glyph from the most visually striking rune in play."""
    for key in _SCHOOLS:  # dict order == priority
        if key in runes:
            # broken_mark recolours but rarely "leads" unless it's the only rune
            if key == "broken_mark" and len(runes) > 1:
                continue
            return _SCHOOLS[key]
    return _GENERIC


def plan_vfx(
    spell: SpellResult,
    *,
    enemy_name: str,
    runes: list[str] | None = None,
    cast_id: int = 0,
) -> dict:
    """Turn a validated :class:`SpellResult` into renderer metadata.

    Returns a flat dict the Gradio battle-stage HTML knows how to animate.
    ``cast_id`` makes the CSS animation names unique so they replay every turn.
    """
    runes = runes or []
    school = _dominant_school(spell, runes)

    dmg = -spell.enemy_hp_delta  # positive number = damage dealt
    heal = max(0, spell.player_hp_delta)
    cursed = "broken_mark" in runes or "curse" in spell.spell_type
    statuses = set(spell.status_effects)

    # Shake scales with damage + chaos, clamped so VFX stay readable (§21.6).
    shake = min(1.0, 0.12 + 0.14 * max(0, dmg) + 0.03 * spell.chaos)
    if cursed:
        shake = min(1.0, shake + 0.15)

    # What the spell is mostly "doing", for projectile direction + reaction.
    if heal > 0 and dmg <= 0:
        mode = "heal"
    elif "player_shielded" in statuses and dmg <= 0:
        mode = "shield"
    elif dmg > 0:
        mode = "attack"
    else:
        mode = "hex"

    if "enemy_burning" in statuses:
        reaction = _REACTION["burning"]
    elif "enemy_confused" in statuses:
        reaction = _REACTION["confused"]
    elif "enemy_feared" in statuses:
        reaction = _REACTION["feared"]
    elif "enemy_soothed" in statuses:
        reaction = _REACTION["soothed"]
    elif dmg > 0:
        reaction = _REACTION["hurt"]
    else:
        reaction = _REACTION["none"]

    palette = list(school["palette"])
    if cursed:
        palette = ["#ff3d6e", *palette[:2]]

    return {
        "cast_id": cast_id,
        "mode": mode,
        "palette": palette,
        "glyph": school["glyph"],
        "particle": school["particle"],
        "particle_count": 6 + spell.chaos + (4 if cursed else 0),
        "shake": round(shake, 3),
        "flash": palette[0],
        "duration_ms": 700 + 40 * spell.chaos,
        "damage": dmg,
        "heal": heal,
        "cursed": cursed,
        "reaction": reaction,
        "enemy_name": enemy_name,
    }


# Sprite + biome lookups used by the battle stage. Kept here so the renderer has
# a single source of truth for "what an enemy looks like".
ENEMY_SPRITES: dict[str, str] = {
    "Queue Goblin": "👺",
    "Mirror Fungus": "🍄",
    "Tax Wraith": "👻",
    "Stapler Hydra": "🐉",
    "Emotional Door": "🚪",
    "Calendar Beast": "📆",
    "PDF Wraith": "📄",
    "Mold Knight": "🦠",
}

# Backdrop gradient per room index in the 5-room run.
ROOM_BACKDROPS: list[list[str]] = [
    ["#2a1f10", "#0e0b06"],  # Goblin Toll Booth — torchlit booth
    ["#10242a", "#06100e"],  # Mirror Fungus Cave — damp cave
    ["#16202e", "#070b12"],  # The Wet Library — soggy stacks
    ["#241019", "#0c060a"],  # Department of Forbidden Doors
    ["#2a1230", "#0c0612"],  # Calendar Beast Arena — overbooked void
]


def enemy_sprite(name: str) -> str:
    return ENEMY_SPRITES.get(name, "👾")


def room_backdrop(room_index: int) -> list[str]:
    if 0 <= room_index < len(ROOM_BACKDROPS):
        return ROOM_BACKDROPS[room_index]
    return ["#1a1426", "#0e0b14"]


def enemy_weak_to(enemy_name: str) -> tuple[str, ...]:
    e = ENEMIES.get(enemy_name)
    return e.weakness if e else ()
