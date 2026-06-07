# Rune Goblin 5k RuneLang SFT Dataset

Synthetic fine-tuning dataset for **Rune Goblin**, a tiny dungeon crawler where an OpenBMB text model acts as the spell interpreter / spell physics engine.

## What the model learns

The model is trained on:

```text
game state + drawn RuneLang glyphs -> valid JSON spell result
```

The dataset follows the project plan: RuneLang has 16 glyphs, spells use 2–4 glyphs, and the assistant must return JSON only.

## Files

| File | Rows | Purpose |
|---|---:|---|
| `rune_goblin_5000_chatml.jsonl` | 5,000 | Full dataset with metadata + `messages` |
| `rune_goblin_5000_messages_only.jsonl` | 5,000 | Direct SFT format: only `messages` |
| `train.jsonl` | 4,500 | 90% train split with metadata |
| `validation.jsonl` | 500 | 10% validation split with metadata |
| `train_messages_only.jsonl` | 4,500 | Direct SFT train |
| `validation_messages_only.jsonl` | 500 | Direct SFT validation |
| `sample_100_preview.csv` | 100 | Human inspection preview |
| `schema.json` | - | Output schema and RuneLang rules |
| `generate_rune_goblin_dataset.py` | - | Compact reproducible smoke-test generator |

## Category Mix

| Category | Count | Purpose |
|---|---:|---|
| Basic spells | 2,000 | Teach individual rune meanings |
| Combo spells | 1,200 | Teach rune interactions |
| Cursed spells | 700 | Teach broken-mark side effects |
| Enemy-specific spells | 700 | Teach weaknesses/resistances |
| Invalid/edge cases | 400 | Teach safe fallback and valid JSON |

## Assistant JSON schema

```json
{
  "spell_name": "string",
  "spell_type": "string",
  "flavor": "string",
  "effect": "string",
  "side_effect": "string",
  "enemy_hp_delta": -2,
  "player_hp_delta": 0,
  "status_effects": ["enemy_confused"],
  "chaos": 7
}
```

Damage is intentionally clamped for game balance:

- `enemy_hp_delta`: `-4` to `0`
- `player_hp_delta`: `-2` to `3`
- `chaos`: `1` to `10`

## Example row

```json
{
  "id": "rune-goblin-02314",
  "category": "combo_spells",
  "rune_count": 3,
  "runes": [
    "mirror",
    "eye",
    "jagged_line"
  ],
  "enemy": "Button Oracle",
  "weakness": "coin",
  "resistance": "thread",
  "messages": [
    {
      "role": "system",
      "content": "You are the Rune Goblin spell physics engine. Convert RuneLang glyphs into balanced game-result JSON only."
    },
    {
      "role": "user",
      "content": "STATE: player_hp=10 enemy=Button Oracle enemy_hp=4 weakness=coin resistance=thread room=The Wet Library room_mood=bookish inventory=[snail invoice, bone bead]\nRUNES: mirror, eye, jagged_line\nReturn spell result."
    },
    {
      "role": "assistant",
      "content": "{\"spell_name\":\"Mirror Says No\",\"spell_type\":\"reflect_damage\",\"flavor\":\"RuneLang clicks like bad teeth, and Button Oracle suddenly understands why this was a mistake.\",\"effect\":\"Turns incoming harm around and returns it as a jagged reflection. Enemy takes 1 damage; applies reflect-ready, cut.\",\"side_effect\":\"Player sees their brave face and decides it needs work.\",\"enemy_hp_delta\":-1,\"player_hp_delta\":0,\"status_effects\":[\"reflect_ready\",\"enemy_cut\"],\"chaos\":7}"
    }
  ]
}
```

## Suggested SFT target

Use `train_messages_only.jsonl` and `validation_messages_only.jsonl` for most chat-style SFT pipelines.

Suggested setup:

```text
base_model: OpenBMB/MiniCPM5-1B-SFT
method: LoRA or QLoRA
max_seq_len: 1024 or 2048
epochs: 2-4
```

## Notes

This is synthetic data generated from a deterministic rule engine plus templated creative flavor. It is designed for hackathon prototyping, not production balance. The game engine should still validate JSON and clamp HP changes at runtime.
