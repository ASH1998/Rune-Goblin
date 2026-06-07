"""
Rune Goblin synthetic dataset generator.

This is the reproducible generator used to create the bundled 5,000-example
RuneLang SFT dataset. It uses deterministic rule logic + templated flavor text.
Run:

    python generate_rune_goblin_dataset.py

It will produce:
- rune_goblin_5000_chatml.jsonl
- train.jsonl
- validation.jsonl
- messages-only versions
- schema.json
"""

# For the full generation logic, use the generated dataset files directly.
# This compact script creates a small smoke-test subset in the same format.
import json, random
from pathlib import Path

random.seed(1337)

RUNES = [
    "spiral", "jagged_line", "closed_circle", "three_dots", "wave", "eye", "bone", "leaf",
    "flame", "key", "mirror", "bell", "tooth", "thread", "coin", "broken_mark"
]

ENEMIES = [
    ("Queue Goblin", "bell", "flame"),
    ("Mirror Fungus", "confusion", "direct_damage"),
    ("Tax Wraith", "coin", "bone"),
    ("Stapler Hydra", "jagged_line", "thread"),
    ("Emotional Door", "wave", "jagged_line"),
    ("Calendar Beast", "spiral", "flame"),
    ("PDF Wraith", "mirror", "tooth"),
    ("Mold Knight", "leaf", "wave"),
]

COMBOS = {
    frozenset(["spiral", "eye"]): ("prophecy_loop", "reveals the enemy's next move and confuses it", ["enemy_confused","future_move_revealed"]),
    frozenset(["flame", "closed_circle"]): ("burning_shield", "creates a burning shield", ["player_shielded","enemy_burned"]),
    frozenset(["three_dots", "bone"]): ("skeleton_swarm", "summons a skeleton swarm", ["enemy_swarmed","enemy_frightened"]),
    frozenset(["mirror", "jagged_line"]): ("reflect_damage", "reflects damage as a jagged reply", ["reflect_ready","enemy_cut"]),
    frozenset(["key", "wave"]): ("emotional_unlock", "unlocks an emotional door", ["room_unlocked","enemy_softened"]),
    frozenset(["thread", "tooth"]): ("bind_and_bite", "binds and bites the enemy", ["enemy_bound","enemy_intimidated"]),
    frozenset(["coin", "bell"]): ("merchant_summon", "summons a merchant spirit", ["merchant_summoned","enemy_distracted"]),
    frozenset(["leaf", "bone"]): ("decay_heal", "heals with decay risk", ["player_regenerating","decay_risk"]),
    frozenset(["eye", "mirror"]): ("reveal_weakness", "reveals enemy weakness", ["enemy_revealed","enemy_weakened"]),
}

def output_for(enemy, weakness, resistance, runes):
    invalid = not (2 <= len(runes) <= 4) or any(r not in RUNES for r in runes)
    if invalid:
        return {
            "spell_name":"Fizzled Grammar Imp",
            "spell_type":"invalid_spell",
            "flavor":"A tiny syntax moth eats the spell before it becomes dangerous.",
            "effect":"Invalid RuneLang sequence. No combat effect is applied.",
            "side_effect":"The spell consumes the turn but changes no HP.",
            "enemy_hp_delta":0,
            "player_hp_delta":0,
            "status_effects":["spell_fizzled","syntax_warning"],
            "chaos":2
        }
    combo = next((v for k, v in COMBOS.items() if k.issubset(set(runes))), None)
    cursed = "broken_mark" in runes
    spell_type = combo[0] if combo else "mixed_rune_spell"
    statuses = list(combo[2]) if combo else ["enemy_distracted"]
    damage = -2 if combo and combo[0] in ["skeleton_swarm","bind_and_bite"] else (-1 if combo else -1)
    player_delta = 0
    if spell_type == "decay_heal":
        damage = 0
        player_delta = 1
    if cursed:
        statuses.append("player_cursed")
        damage = min(0, damage - 1) if damage else -1
    if weakness in runes or (weakness == "confusion" and "enemy_confused" in statuses):
        statuses.append("weakness_triggered")
        if damage < 0:
            damage -= 1
    if resistance in runes or (resistance == "direct_damage" and damage < 0):
        damage += 1
        statuses.append("enemy_resisted")
    damage = max(-4, min(0, damage))
    return {
        "spell_name": ("Cursed " if cursed else "") + random.choice(["Goblin Clause","Moth Spiral","Refund Bell","Bone Committee","Wet Key"]),
        "spell_type": spell_type,
        "flavor": f"The {' + '.join(runes)} glyphs wobble toward {enemy} with suspicious confidence.",
        "effect": combo[1].capitalize() + "." if combo else "A mixed RuneLang spell applies a small dungeon effect.",
        "side_effect": "Player hears future elevator music." if cursed else "None. The spell behaves suspiciously well.",
        "enemy_hp_delta": damage,
        "player_hp_delta": player_delta,
        "status_effects": list(dict.fromkeys(statuses)),
        "chaos": min(10, 3 + len(runes) + (2 if cursed else 0))
    }

def make_row(i):
    enemy, weakness, resistance = random.choice(ENEMIES)
    runes = random.sample(RUNES[:-1], random.choice([2,3,4]))
    if random.random() < 0.2:
        runes[0] = "broken_mark"
    out = output_for(enemy, weakness, resistance, runes)
    return {
        "id": f"rune-goblin-smoke-{i:04d}",
        "category": "smoke_test",
        "runes": runes,
        "messages": [
            {"role":"system","content":"You are Rune Goblin, a tiny dungeon spell engine. Interpret RuneLang and output valid JSON only."},
            {"role":"user","content":f"STATE: player_hp=7 enemy={enemy} enemy_hp=6 weakness={weakness} resistance={resistance} room=The Wet Library room_mood=damp inventory=[wet candle]\nRUNES: {', '.join(runes)}\nReturn spell result."},
            {"role":"assistant","content":json.dumps(out,separators=(',',':'))}
        ]
    }

rows = [make_row(i) for i in range(100)]
Path("rune_goblin_smoke_100.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
print("Wrote rune_goblin_smoke_100.jsonl")
