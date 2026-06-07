"""Synthetic dataset generator for RuneLang (sections 8 & 9 of the plan).

Produces chat-format JSONL where each line is::

    {"messages": [ {system}, {user}, {assistant} ]}

The assistant content is the compact JSON spell result produced by the
rule engine, so the model learns: game_state + runes -> spell outcome.

Usage::

    uv run python -m rune_goblin.generate_dataset --n 5000 --out data/rune_spells.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from .engine import GameState, resolve_spell
from .prompts import build_chat_messages
from .runelang import (
    ALL_ENEMIES,
    ALL_RUNES,
    COMBOS,
    CORE_RUNES,
    ENEMIES,
    INVENTORY_ITEMS,
    ROOM_MOODS,
)
from .schema import FALLBACK_SPELL

# Plan section 9.1 split.
DEFAULT_MIX = {
    "basic": 2000,
    "combo": 1200,
    "cursed": 700,
    "enemy": 700,
    "invalid": 400,
}


def _random_state(rng: random.Random, enemy_name: str | None = None) -> GameState:
    enemy_name = enemy_name or rng.choice(ALL_ENEMIES)
    enemy = ENEMIES[enemy_name]
    enemy_hp = rng.randint(1, enemy.max_hp)
    inv = tuple(rng.sample(INVENTORY_ITEMS, k=rng.randint(0, 3)))
    return GameState(
        player_hp=rng.randint(1, 10),
        player_max_hp=10,
        enemy_name=enemy_name,
        enemy_hp=enemy_hp,
        enemy_max_hp=enemy.max_hp,
        room_mood=rng.choice(ROOM_MOODS),
        inventory=inv,
        courage=rng.randint(0, 5),
    )


def _sample_runes(rng: random.Random, kind: str) -> list[str]:
    if kind == "combo":
        combo = rng.choice(COMBOS)
        runes = list(combo.runes)
        # optionally pad with an extra core rune up to 4
        if rng.random() < 0.4:
            extra = rng.choice([r for r in CORE_RUNES if r not in runes])
            runes.append(extra)
        rng.shuffle(runes)
        return runes
    if kind == "cursed":
        n = rng.randint(1, 3)
        runes = rng.sample(CORE_RUNES, k=n) + ["broken_mark"]
        rng.shuffle(runes)
        return runes
    # basic / enemy
    n = rng.randint(2, 4)
    return rng.sample(ALL_RUNES, k=n)


def _make_example(rng: random.Random, kind: str) -> dict:
    if kind == "invalid":
        return _make_invalid_example(rng)

    enemy = None
    if kind == "enemy":
        enemy = rng.choice(ALL_ENEMIES)

    state = _random_state(rng, enemy)
    runes = _sample_runes(rng, kind)

    if kind == "enemy":
        # bias toward including a rune that hits this enemy's weakness
        e = ENEMIES[state.enemy_name]
        if e.weakness and rng.random() < 0.7:
            from .runelang import GLYPHS

            for r in ALL_RUNES:
                g = GLYPHS[r]
                if r in e.weakness or any(t in e.weakness for t in g.tags):
                    if r not in runes:
                        runes[rng.randrange(len(runes))] = r
                    break

    spell = resolve_spell(state, runes, seed=rng.randint(0, 2**31 - 1))
    messages = build_chat_messages(state, runes, spell.to_compact_json())
    return {"messages": messages, "meta": {"kind": kind}}


def _make_invalid_example(rng: random.Random) -> dict:
    """Edge case: empty / nonsense runes -> safe fallback JSON (Risk 2)."""
    state = _random_state(rng)
    bad_runes_pool = [[], ["???"], ["squiggle"], ["broken_mark"], ["aaaa", "bbbb"]]
    runes = rng.choice(bad_runes_pool)
    # The model should still emit the safe fallback spell.
    spell = FALLBACK_SPELL.model_copy()
    display_runes = runes if runes else ["(none)"]
    messages = build_chat_messages(state, display_runes, spell.to_compact_json())
    return {"messages": messages, "meta": {"kind": "invalid"}}


def generate(n: int, mix: dict[str, int] | None, seed: int) -> list[dict]:
    rng = random.Random(seed)
    mix = mix or DEFAULT_MIX
    total = sum(mix.values())
    # scale the mix to the requested n
    scaled = {k: max(1, round(v * n / total)) for k, v in mix.items()}
    examples: list[dict] = []
    for kind, count in scaled.items():
        for _ in range(count):
            examples.append(_make_example(rng, kind))
    rng.shuffle(examples)
    return examples[:n] if n <= len(examples) else examples


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate the RuneLang spell dataset.")
    ap.add_argument("--n", type=int, default=5000, help="total examples")
    ap.add_argument("--out", type=Path, default=Path("data/rune_spells.jsonl"))
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--val-split", type=float, default=0.05, help="fraction held out for eval")
    args = ap.parse_args()

    examples = generate(args.n, DEFAULT_MIX, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    n_val = int(len(examples) * args.val_split)
    val, train = examples[:n_val], examples[n_val:]

    def _dump(path: Path, rows: list[dict]) -> None:
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    _dump(args.out, train)
    if n_val:
        val_path = args.out.with_name(args.out.stem + "_val.jsonl")
        _dump(val_path, val)
        print(f"Wrote {len(train)} train -> {args.out}")
        print(f"Wrote {len(val)} val   -> {val_path}")
    else:
        print(f"Wrote {len(train)} examples -> {args.out}")


if __name__ == "__main__":
    main()
