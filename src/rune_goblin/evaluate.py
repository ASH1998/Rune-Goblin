"""Evaluate the fine-tuned model like a game engine (section 14).

Metrics: valid-JSON rate, rune-rule accuracy (does a weakness-hitting spell
deal extra damage?), enemy-weakness usage, damage-range validity, and a
crude spell-name diversity score.

Usage::

    uv run python -m rune_goblin.evaluate --n 200
"""

from __future__ import annotations

import argparse
import random

from .engine import GameState, resolve_spell
from .inference import get_model
from .runelang import ALL_ENEMIES, ALL_RUNES, ENEMIES, rune_matches


def _random_case(rng: random.Random) -> tuple[GameState, list[str]]:
    enemy = rng.choice(ALL_ENEMIES)
    e = ENEMIES[enemy]
    state = GameState(
        player_hp=rng.randint(3, 10), enemy_name=enemy,
        enemy_hp=e.max_hp, enemy_max_hp=e.max_hp, room_mood=e.mood,
    )
    runes = rng.sample(ALL_RUNES, k=rng.randint(2, 4))
    return state, runes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=123)
    ap.add_argument("--rules-only", action="store_true", help="evaluate the rule engine, not the model")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    model = None if args.rules_only else get_model()
    using = "rule-engine" if model is None else "fine-tuned model"
    print(f"Evaluating {using} on {args.n} cases\n")

    valid = 0
    weakness_used = 0
    weakness_cases = 0
    damage_ok = 0
    names: set[str] = set()

    for _ in range(args.n):
        state, runes = _random_case(rng)
        if model is not None:
            spell = model.cast(state, runes)
            raw_valid = spell is not None
        else:
            spell = resolve_spell(state, runes, seed=rng.randint(0, 2**31 - 1))
            raw_valid = True

        if not raw_valid or spell is None:
            continue
        valid += 1
        names.add(spell.spell_name)

        # damage range: enemy_hp_delta must be within [-enemy_hp, 0..]
        if -state.enemy_hp <= spell.enemy_hp_delta <= state.enemy_max_hp:
            damage_ok += 1

        hits_weak = any(rune_matches(r, state.weakness) for r in runes)
        if hits_weak:
            weakness_cases += 1
            # heuristic: hitting a weakness should produce meaningful damage
            if spell.enemy_hp_delta <= -2 or "weakness_revealed" in spell.status_effects:
                weakness_used += 1

    n = args.n
    print(f"Valid JSON rate     : {valid / n:.1%}  (goal >95%)")
    print(f"Damage range valid  : {damage_ok / max(1, valid):.1%}  (goal >95%)")
    if weakness_cases:
        print(f"Weakness usage      : {weakness_used / weakness_cases:.1%}  (goal >80%)")
    print(f"Spell name diversity: {len(names)}/{valid} unique")


if __name__ == "__main__":
    main()
