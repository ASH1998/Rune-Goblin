"""RuneLang: the invented symbolic spell language for Rune Goblin.

This module is the single source of truth for the game's vocabulary, grammar,
enemies, rooms and combination rules. Both the dataset generator and the game
engine import from here so the model is trained on exactly the rules the game
enforces.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Glyph:
    """A single rune in RuneLang."""

    key: str  # snake_case identifier used in serialized rune sequences
    symbol: str  # short display glyph / emoji for the UI
    label: str  # human-readable name
    meanings: tuple[str, ...]  # flavour meanings from the rulebook
    tags: tuple[str, ...]  # categories used for weakness/resistance matching
    base_damage: int = 0  # raw damage this rune contributes to a spell
    status: str | None = None  # status effect this rune tends to apply
    heal: int = 0  # player HP this rune tends to restore


# ---------------------------------------------------------------------------
# 16-rune vocabulary (section 5.1 of the plan)
# ---------------------------------------------------------------------------
GLYPHS: dict[str, Glyph] = {
    "spiral": Glyph(
        "spiral", "🌀", "Spiral", ("time", "confusion", "loops"),
        ("time", "confusion", "loop"), base_damage=1, status="enemy_confused",
    ),
    "jagged_line": Glyph(
        "jagged_line", "⚡", "Jagged Line", ("damage", "lightning", "cutting"),
        ("damage", "lightning", "cutting", "direct_damage", "jagged"),
        base_damage=2,
    ),
    "closed_circle": Glyph(
        "closed_circle", "⭕", "Closed Circle", ("shield", "trap", "containment"),
        ("shield", "trap", "containment", "circle"), status="player_shielded",
    ),
    "three_dots": Glyph(
        "three_dots", "⠿", "Three Dots", ("swarm", "insects", "multiplication"),
        ("swarm", "insect", "multiplication", "dots"), base_damage=1,
        status="enemy_swarmed",
    ),
    "wave": Glyph(
        "wave", "🌊", "Wave", ("water", "emotion", "softness"),
        ("water", "emotion", "softness"), status="enemy_soothed",
    ),
    "eye": Glyph(
        "eye", "👁", "Eye", ("reveal", "inspect", "prophecy"),
        ("reveal", "inspect", "prophecy"), status="enemy_revealed",
    ),
    "bone": Glyph(
        "bone", "🦴", "Bone", ("fear", "death", "skeleton"),
        ("fear", "death", "skeleton"), base_damage=1, status="enemy_feared",
    ),
    "leaf": Glyph(
        "leaf", "🍃", "Leaf", ("healing", "growth", "poison"),
        ("healing", "growth", "poison"), heal=2,
    ),
    "flame": Glyph(
        "flame", "🔥", "Flame", ("burn", "passion", "danger"),
        ("burn", "passion", "danger", "direct_damage", "fire"),
        base_damage=2, status="enemy_burning",
    ),
    "key": Glyph(
        "key", "🗝", "Key", ("unlock", "escape", "secrets"),
        ("unlock", "escape", "secrets"), status="door_unlocked",
    ),
    "mirror": Glyph(
        "mirror", "🪞", "Mirror", ("reflect", "copy", "reverse"),
        ("reflect", "copy", "reverse"), status="damage_reflected",
    ),
    "bell": Glyph(
        "bell", "🔔", "Bell", ("summon", "alarm", "attention"),
        ("summon", "alarm", "attention"), base_damage=1, status="enemy_alarmed",
    ),
    "tooth": Glyph(
        "tooth", "🦷", "Tooth", ("bite", "hunger", "intimidation"),
        ("bite", "hunger", "intimidation", "direct_damage"), base_damage=2,
    ),
    "thread": Glyph(
        "thread", "🧵", "Thread", ("bind", "pull", "stitch"),
        ("bind", "pull", "stitch"), base_damage=1, status="enemy_bound",
    ),
    "coin": Glyph(
        "coin", "🪙", "Coin", ("greed", "trade", "sacrifice"),
        ("greed", "trade", "sacrifice"), base_damage=1,
    ),
    "broken_mark": Glyph(
        "broken_mark", "💢", "Broken Mark", ("curse modifier",),
        ("curse",),
    ),
}

ALL_RUNES: list[str] = list(GLYPHS.keys())
CORE_RUNES: list[str] = [k for k in ALL_RUNES if k != "broken_mark"]


# ---------------------------------------------------------------------------
# Combination rules (section 5.3)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Combo:
    runes: frozenset[str]
    meaning: str
    spell_type: str


COMBOS: list[Combo] = [
    Combo(frozenset({"spiral", "eye"}), "prophecy / see future move", "prophecy"),
    Combo(frozenset({"flame", "closed_circle"}), "burning shield", "shield_burn"),
    Combo(frozenset({"three_dots", "bone"}), "skeleton swarm", "swarm_curse"),
    Combo(frozenset({"mirror", "jagged_line"}), "reflect damage", "reflect"),
    Combo(frozenset({"key", "wave"}), "unlock emotional door", "unlock_emotion"),
    Combo(frozenset({"thread", "tooth"}), "bind and bite", "bind_bite"),
    Combo(frozenset({"coin", "bell"}), "summon a merchant spirit", "summon_merchant"),
    Combo(frozenset({"leaf", "bone"}), "healing with decay risk", "heal_decay"),
    Combo(frozenset({"eye", "mirror"}), "reveal enemy weakness", "reveal_weakness"),
]


def find_combo(runes: list[str]) -> Combo | None:
    """Return the first combination rule fully contained in ``runes``."""
    rune_set = set(runes)
    for combo in COMBOS:
        if combo.runes.issubset(rune_set):
            return combo
    return None


# ---------------------------------------------------------------------------
# Enemies (section 10.2) — weakness/resistance use glyph keys or tags
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Enemy:
    name: str
    max_hp: int
    weakness: tuple[str, ...]
    resistance: tuple[str, ...]
    mood: str


ENEMIES: dict[str, Enemy] = {
    "Queue Goblin": Enemy("Queue Goblin", 5, ("bell", "coin"), ("flame",), "impatient"),
    "Mirror Fungus": Enemy("Mirror Fungus", 5, ("confusion", "mirror"), ("direct_damage",), "suspiciously moist"),
    "Tax Wraith": Enemy("Tax Wraith", 6, ("coin", "key"), ("bone",), "audit-hungry"),
    "Stapler Hydra": Enemy("Stapler Hydra", 7, ("jagged", "flame"), ("thread",), "clicky and furious"),
    "Emotional Door": Enemy("Emotional Door", 6, ("wave", "key"), ("jagged",), "deeply conflicted"),
    "Calendar Beast": Enemy("Calendar Beast", 8, ("spiral", "eye"), ("flame",), "overbooked"),
    "PDF Wraith": Enemy("PDF Wraith", 6, ("mirror", "bell"), ("tooth",), "compressed and bitter"),
    "Mold Knight": Enemy("Mold Knight", 7, ("leaf", "flame"), ("wave",), "damply chivalrous"),
}

ALL_ENEMIES: list[str] = list(ENEMIES.keys())


# ---------------------------------------------------------------------------
# Rooms (section 10.1) — each room pairs with a thematic enemy for a 5-room run
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Room:
    name: str
    enemy: str
    intro: str


ROOMS: list[Room] = [
    Room("Goblin Toll Booth", "Queue Goblin", "A goblin demands payment in a currency you do not have."),
    Room("Mirror Fungus Cave", "Mirror Fungus", "The walls reflect a damper version of you."),
    Room("The Wet Library", "PDF Wraith", "Every book is slightly soggy and overdue."),
    Room("Department of Forbidden Doors", "Emotional Door", "A door refuses to open until you validate its feelings."),
    Room("Calendar Beast Arena", "Calendar Beast", "Time itself has scheduling conflicts."),
]


# ---------------------------------------------------------------------------
# Misc flavour pools used by the dataset generator and game
# ---------------------------------------------------------------------------
ROOM_MOODS: tuple[str, ...] = (
    "paranoid", "soggy", "overcaffeinated", "bureaucratic", "haunted",
    "suspiciously moist", "passive-aggressive", "echoing", "expired",
)

INVENTORY_ITEMS: tuple[str, ...] = (
    "wet candle", "button", "expired coupon", "single sock", "rubber duck",
    "broken compass", "jar of teeth", "laminated regret", "spare courage",
    "lukewarm soup", "tax form", "cursed stapler",
)

STATUS_EFFECTS: tuple[str, ...] = (
    "enemy_confused", "enemy_swarmed", "enemy_soothed", "enemy_revealed",
    "enemy_feared", "enemy_burning", "enemy_alarmed", "enemy_bound",
    "player_shielded", "player_healed", "damage_reflected", "door_unlocked",
    "weakness_revealed",
)


def rune_matches(rune: str, categories: tuple[str, ...]) -> bool:
    """True if ``rune`` (by key or tag) is in the given weakness/resistance set."""
    glyph = GLYPHS.get(rune)
    if glyph is None:
        return False
    if rune in categories:
        return True
    return any(tag in categories for tag in glyph.tags)
