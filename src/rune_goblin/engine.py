"""The Rune Goblin spell-physics engine.

Two responsibilities:

1. ``resolve_spell`` — given a game state + drawn runes, compute a *correct*
   :class:`SpellResult`. This is the rule-based oracle used to generate training
   targets, so the fine-tuned model learns to imitate these rules.
2. ``clamp_spell`` — given any (possibly model-produced) :class:`SpellResult`
   and the current state, bound the numeric deltas so HP can never go out of
   range (Risk 3 in the plan: "Let Python enforce final HP limits").
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .runelang import (
    ENEMIES,
    GLYPHS,
    find_combo,
    rune_matches,
)
from .schema import SpellResult


@dataclass
class GameState:
    player_hp: int = 10
    player_max_hp: int = 10
    enemy_name: str = "Mirror Fungus"
    enemy_hp: int = 5
    enemy_max_hp: int = 5
    room_mood: str = "paranoid"
    inventory: tuple[str, ...] = ()
    courage: int = 5
    # RPG entities carry their own weakness/resistance (not in the ENEMIES table);
    # set these to override the lookup.
    weakness_override: tuple[str, ...] | None = None
    resistance_override: tuple[str, ...] | None = None

    @property
    def weakness(self) -> tuple[str, ...]:
        if self.weakness_override is not None:
            return self.weakness_override
        e = ENEMIES.get(self.enemy_name)
        return e.weakness if e else ()

    @property
    def resistance(self) -> tuple[str, ...]:
        if self.resistance_override is not None:
            return self.resistance_override
        e = ENEMIES.get(self.enemy_name)
        return e.resistance if e else ()


# ---------------------------------------------------------------------------
# Funny-name generation (Risk 4: avoid generic "Fireball" outputs)
# ---------------------------------------------------------------------------
_ADJECTIVES = [
    "Cursed", "Triplicate", "Moist", "Bureaucratic", "Looping", "Forbidden",
    "Mildly", "Overdue", "Spiteful", "Recursive", "Laminated", "Haunted",
    "Passive-Aggressive", "Expired", "Reluctant", "Tax-Deductible",
]
_NOUNS = [
    "Panic Spiral", "Ember Cage", "Regret", "Refund Bell", "Bone Swarm",
    "Foresight Loop", "Paperwork Storm", "Moth Tax", "Echo", "Hex",
    "Reflection", "Whisper", "Gambit", "Tantrum", "Prophecy", "Audit",
]


def _make_spell_name(rng: random.Random, runes: list[str], spell_type: str) -> str:
    adj = rng.choice(_ADJECTIVES)
    noun = rng.choice(_NOUNS)
    if "broken_mark" in runes and rng.random() < 0.6:
        adj = "Cursed"
    return f"{adj} {noun}"


def _flavor(rng: random.Random, state: GameState, runes: list[str], combo) -> str:
    glyph_labels = [GLYPHS[r].label.lower() for r in runes if r in GLYPHS]
    bits = ", ".join(glyph_labels)
    if combo is not None:
        return (
            f"The {state.enemy_name.lower()} reacts to a {combo.meaning} woven from "
            f"{bits}."
        )
    return f"A spell of {bits} unfurls in the {state.room_mood} air."


def _side_effect(rng: random.Random, state: GameState, cursed: bool) -> str:
    if not cursed:
        return ""
    pool = [
        "Player loses 1 courage from a sudden vision of their own future haircut.",
        "A copy of your fear refuses to leave and follows you to the next room.",
        "Room temperature rises; your next water spell is weaker.",
        "You sign a contract you do not remember agreeing to.",
        "A small debt appears in your inventory.",
    ]
    return rng.choice(pool)


# ---------------------------------------------------------------------------
# Core resolution
# ---------------------------------------------------------------------------
def resolve_spell(state: GameState, runes: list[str], seed: int | None = None) -> SpellResult:
    """Deterministically (given ``seed``) compute the correct spell outcome."""
    rng = random.Random(seed)
    runes = [r for r in runes if r in GLYPHS]
    if not runes:
        from .schema import FALLBACK_SPELL

        return FALLBACK_SPELL.model_copy()

    cursed = "broken_mark" in runes
    combo = find_combo(runes)

    # --- base damage from glyphs ---
    raw_damage = sum(GLYPHS[r].base_damage for r in runes)
    heal = sum(GLYPHS[r].heal for r in runes)

    statuses: list[str] = []
    for r in runes:
        st = GLYPHS[r].status
        if st and st not in statuses:
            statuses.append(st)

    # --- weakness / resistance interaction ---
    hits_weakness = any(rune_matches(r, state.weakness) for r in runes)
    hits_resistance = any(rune_matches(r, state.resistance) for r in runes)

    if hits_weakness:
        raw_damage += 2
        statuses.append("weakness_revealed")
    if hits_resistance:
        raw_damage = max(0, raw_damage - 2)

    # --- combo adjustments ---
    spell_type = combo.spell_type if combo else "generic"
    if combo is not None:
        if combo.spell_type in {"reflect", "shield_burn"}:
            statuses.append("damage_reflected")
        if combo.spell_type == "reveal_weakness":
            statuses.append("weakness_revealed")
            raw_damage += 1
        if combo.spell_type == "heal_decay":
            heal += 1
            cursed = True  # decay risk

    # --- curse modifier ---
    if cursed:
        raw_damage = int(round(raw_damage * 1.5))

    # --- player cost ---
    player_delta = heal
    if cursed:
        player_delta -= 1  # courage/HP cost of using the broken mark

    chaos = min(10, 2 + len(runes) + (3 if cursed else 0) + (2 if combo else 0))

    # de-duplicate statuses, keep order
    seen: set[str] = set()
    statuses = [s for s in statuses if not (s in seen or seen.add(s))]

    effect_bits = []
    if raw_damage > 0:
        effect_bits.append(f"Deals {raw_damage} damage")
    if "enemy_confused" in statuses:
        effect_bits.append("confuses the enemy for 1 turn")
    if "enemy_burning" in statuses:
        effect_bits.append("sets the enemy on fire")
    if "player_shielded" in statuses:
        effect_bits.append("shields the player")
    if heal > 0:
        effect_bits.append(f"heals the player {heal}")
    if not effect_bits:
        effect_bits.append("disturbs the enemy mildly")
    effect = ", ".join(effect_bits).capitalize() + "."

    spell = SpellResult(
        spell_name=_make_spell_name(rng, runes, spell_type),
        spell_type=spell_type,
        flavor=_flavor(rng, state, runes, combo),
        effect=effect,
        side_effect=_side_effect(rng, state, cursed),
        enemy_hp_delta=-raw_damage,
        player_hp_delta=player_delta,
        status_effects=statuses,
        chaos=chaos,
    )
    return clamp_spell(spell, state)


def clamp_spell(spell: SpellResult, state: GameState) -> SpellResult:
    """Bound HP deltas so they can never push HP outside [0, max]."""
    # Enemy can lose at most its current HP, gain at most up to max.
    enemy_delta = max(-state.enemy_hp, min(state.enemy_max_hp - state.enemy_hp, spell.enemy_hp_delta))
    player_delta = max(-state.player_hp, min(state.player_max_hp - state.player_hp, spell.player_hp_delta))
    spell.enemy_hp_delta = enemy_delta
    spell.player_hp_delta = player_delta
    return spell
