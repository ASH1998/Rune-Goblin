# Rune Goblin: A Fine-Tuned Spell Language Dungeon Game

## 1. One-Line Pitch

**Rune Goblin is a tiny dungeon crawler where players draw spells in a new magical language, and a fine-tuned OpenBMB LLM interprets those spells to launch attacks, trigger curses, and change the game world.**

## 2. Core Idea

Most games have fixed controls: click attack, cast fireball, defend.

Rune Goblin replaces that with a new language.

The player draws spell symbols called **Runes**.  
The model has been fine-tuned to understand this invented symbolic language and convert it into game actions.

Example:

```text
Player draws:
spiral + broken triangle + three dots
```

The fine-tuned model interprets it as:

```json
{
  "spell_name": "Triplicate Panic Spiral",
  "effect": "Deals 2 damage and confuses the enemy.",
  "side_effect": "Player loses 1 courage.",
  "enemy_hp_delta": -2,
  "player_hp_delta": 0,
  "status_effects": ["enemy_confused"],
  "chaos": 8
}
```

The LLM is not just writing flavor text.  
It is the **spell engine**.

---

## 3. Hackathon Track Fit

This project targets:

### Chapter 2: An Adventure in Thousand Token Wood

The track rewards projects that are:

- delightful
- strange
- interactive
- powered by small models
- not just normal assistant apps
- built in Gradio
- fun enough to show a friend

Rune Goblin fits because the AI is the core game mechanic. The player invents spells visually, and the model decides what happens.

---

## 4. What We Fine-Tune

We fine-tune a small OpenBMB text model, preferably:

```text
MiniCPM5-1B-SFT
```

The fine-tuned model becomes:

```text
Rune Interpreter + Spell Physics Engine
```

It learns a new language made of symbolic spell glyphs.

We do **not** need to fine-tune the vision model initially.

The visual/drawing pipeline can be:

```text
Player drawing
→ glyph recognition
→ serialized rune sequence
→ fine-tuned MiniCPM model
→ spell outcome JSON
→ game state update
```

---

## 5. The New Language: RuneLang

RuneLang is a small magical language made of visual glyphs.

Each glyph has meaning.

### 5.1 Basic Glyph Vocabulary

| Rune | Meaning |
|---|---|
| Spiral | time, confusion, loops |
| Jagged Line | damage, lightning, cutting |
| Closed Circle | shield, trap, containment |
| Three Dots | swarm, insects, multiplication |
| Wave | water, emotion, softness |
| Eye | reveal, inspect, prophecy |
| Bone | fear, death, skeleton |
| Leaf | healing, growth, poison |
| Flame | burn, passion, danger |
| Key | unlock, escape, secrets |
| Mirror | reflect, copy, reverse |
| Bell | summon, alarm, attention |
| Tooth | bite, hunger, intimidation |
| Thread | bind, pull, stitch |
| Coin | greed, trade, sacrifice |
| Broken Mark | curse modifier |

---

### 5.2 Rune Grammar

RuneLang is not random. It has rules.

A spell contains 2–4 glyphs.

```text
[Core Rune] + [Modifier Rune] + [Target Rune] + [Risk Rune]
```

Example:

```text
flame + circle
```

Means:

```text
burning shield
```

Example:

```text
mirror + jagged line
```

Means:

```text
reflect enemy damage
```

Example:

```text
broken mark + coin + eye
```

Means:

```text
cursed greed prophecy
```

---

### 5.3 Combination Rules

| Combination | Meaning |
|---|---|
| Spiral + Eye | prophecy / see future move |
| Flame + Circle | burning shield |
| Dots + Bone | skeleton swarm |
| Mirror + Jagged | reflect damage |
| Key + Wave | unlock emotional door |
| Thread + Tooth | bind and bite |
| Coin + Bell | summon a merchant spirit |
| Broken + Any Rune | stronger effect, but cursed side effect |
| Leaf + Bone | healing with decay risk |
| Eye + Mirror | reveal enemy weakness |

---

## 6. Game Loop

### 6.1 Basic Turn

```text
1. A monster appears.
2. Player draws 2–4 runes.
3. RuneLang input is sent to the fine-tuned LLM.
4. LLM returns a valid spell result.
5. Game engine updates HP, statuses, inventory, and room state.
6. Next enemy or event appears.
```

---

### 6.2 Example Turn

Enemy:

```text
Mirror Fungus
HP: 5
Weakness: confusion
Resistance: direct damage
```

Player draws:

```text
spiral + eye + broken mark
```

Fine-tuned model returns:

```json
{
  "spell_name": "Cursed Foresight Loop",
  "spell_type": "prophecy_curse",
  "flavor": "The fungus sees three possible futures and panics in all of them.",
  "effect": "Enemy is confused for 1 turn and takes 1 psychic damage.",
  "side_effect": "Player loses 1 courage from seeing their own future haircut.",
  "enemy_hp_delta": -1,
  "player_hp_delta": 0,
  "status_effects": ["enemy_confused"],
  "chaos": 7
}
```

The game applies the result.

---

## 7. Why Fine-Tuning Matters

This is not a generic fantasy generator.

The fine-tuned model learns:

1. The custom RuneLang vocabulary
2. The relationship between glyph combinations and spell effects
3. Game balance rules
4. Valid JSON output
5. Enemy-specific weaknesses and resistances
6. The weird tone of the world
7. How to update game state safely

Without fine-tuning, a base model may generate nice text, but it will not consistently obey the invented spell language.

The fine-tuned model becomes the game’s unique magic system.

---

## 8. Dataset Design

The dataset teaches the model:

```text
game state + rune sequence → spell outcome
```

Each training example contains:

- player HP
- enemy name
- enemy HP
- enemy weakness
- enemy resistance
- room mood
- inventory
- drawn runes
- expected spell JSON

---

### 8.1 Training Example Format

```json
{
  "messages": [
    {
      "role": "system",
      "content": "You are Rune Goblin, a tiny dungeon spell engine. Interpret RuneLang and output valid JSON only."
    },
    {
      "role": "user",
      "content": "STATE: player_hp=7 enemy=Mirror Fungus enemy_hp=5 weakness=confusion resistance=direct_damage room_mood=paranoid inventory=[wet candle, button]\nRUNES: spiral, broken_mark, three_dots\nReturn spell result."
    },
    {
      "role": "assistant",
      "content": "{\"spell_name\":\"Triplicate Panic Spiral\",\"spell_type\":\"curse_swarm\",\"flavor\":\"Three tiny copies of your fear run around the fungus yelling contradictory prophecies.\",\"effect\":\"Deals 2 damage and confuses the enemy for 1 turn.\",\"side_effect\":\"Player loses 1 courage because one fear-copy refuses to leave.\",\"enemy_hp_delta\":-2,\"player_hp_delta\":0,\"status_effects\":[\"enemy_confused\"],\"chaos\":8}"
    }
  ]
}
```

---

## 9. Dataset Generation Plan

We generate a synthetic dataset using a mix of rule-based logic and LLM-assisted flavor generation.

### 9.1 Dataset Size

Target:

```text
5,000 examples
```

Split:

| Dataset Type | Count | Purpose |
|---|---:|---|
| Basic spells | 2,000 | Teach individual rune meanings |
| Combo spells | 1,200 | Teach rune interactions |
| Cursed spells | 700 | Teach broken-mark side effects |
| Enemy-specific spells | 700 | Teach weaknesses/resistances |
| Invalid/edge cases | 400 | Teach safe fallback and valid JSON |

---

### 9.2 Generation Pipeline

```text
1. Define RuneLang rules manually.
2. Write Python rule engine.
3. Generate random game states.
4. Sample rune combinations.
5. Calculate legal damage/status effects.
6. Use a larger model or template system to create funny spell names and flavor text.
7. Validate JSON.
8. Save as JSONL.
9. Fine-tune MiniCPM5-1B-SFT with LoRA.
```

---

## 10. Game World

### 10.1 Dungeon Rooms

The game can have a short 5-room run:

```text
Room 1: Goblin Toll Booth
Room 2: Mirror Fungus Cave
Room 3: The Wet Library
Room 4: Department of Forbidden Doors
Room 5: Calendar Beast Arena
```

---

### 10.2 Enemies

| Enemy | Weakness | Resistance |
|---|---|---|
| Queue Goblin | bell, coin | flame |
| Mirror Fungus | confusion, mirror | direct damage |
| Tax Wraith | coin, key | bone |
| Stapler Hydra | jagged, flame | thread |
| Emotional Door | wave, key | jagged |
| Calendar Beast | spiral, eye | flame |
| PDF Wraith | mirror, bell | tooth |
| Mold Knight | leaf, flame | wave |

---

## 11. Model Architecture

### 11.1 MVP Architecture

```text
Gradio UI
  |
  |-- Canvas / Rune buttons
  |
Rune Serializer
  |
Fine-tuned MiniCPM5-1B-SFT LoRA
  |
JSON Spell Result
  |
Game State Engine
  |
Updated UI
```

---

### 11.2 Optional Vision Architecture

Later, we can add freehand drawing recognition:

```text
Player freehand drawing
  |
MiniCPM-V / image classifier
  |
Detected glyphs
  |
Fine-tuned RuneLang model
  |
Spell result
```

For hackathon safety, start with clickable/drawable rune stamps first.

Freehand drawing is cool, but it can waste time if recognition becomes unstable.

---

## 12. Gradio App Design

### 12.1 UI Layout

The Gradio app should feel like a tiny game, not a chatbot.

Suggested layout:

```text
------------------------------------------------
| Rune Goblin                                  |
| Draw forbidden spells. Regret efficiently.   |
------------------------------------------------

[Enemy Card]
Name: Mirror Fungus
HP: 5/5
Weakness: Confusion
Mood: Suspiciously moist

[Player Stats]
HP: 7/10
Inventory: wet candle, button

[Rune Board]
spiral | flame | eye | mirror | broken | dots

[Selected Spell]
spiral + broken + dots

[CAST SPELL]

[Result Panel]
Spell: Triplicate Panic Spiral
Effect: Deals 2 damage and confuses enemy.
Side Effect: You lose 1 courage.

[Dungeon Log]
Turn 1: You entered the Wet Library.
Turn 2: Mirror Fungus appears.
```

---

### 12.2 Core Interactions

MVP interactions:

- select 2–4 runes
- cast spell
- see spell animation text
- update enemy HP
- move to next enemy
- survive 5 rooms
- get final score

Optional interactions:

- draw glyphs on canvas
- unlock new runes
- cursed rune mutations
- inventory items modify spells
- enemies learn from repeated rune usage

---

## 13. Fine-Tuning Plan with Modal

### 13.1 Why Modal

Modal credits can be used for:

- generating synthetic data
- running LoRA fine-tuning
- evaluating the model
- serving the fine-tuned model behind the Gradio app

---

### 13.2 Training Flow

```text
Local / Modal:
1. Generate rune_spell_dataset.jsonl
2. Upload dataset to Hugging Face
3. Fine-tune MiniCPM5-1B-SFT using LoRA/QLoRA
4. Save LoRA adapter
5. Push adapter to Hugging Face
6. Load adapter in Gradio or Modal endpoint
```

---

### 13.3 Suggested Training Setup

```text
Base model: OpenBMB MiniCPM5-1B-SFT
Method: LoRA / QLoRA
Dataset size: 5k examples
Epochs: 2–4
Max sequence length: 1024 or 2048
Batch size: based on GPU
Output: rune-goblin-minicpm5-1b-lora
```

---

## 14. Evaluation

We should evaluate the model like a game engine, not just a text model.

### 14.1 Metrics

| Metric | Goal |
|---|---|
| Valid JSON rate | > 95% |
| Rune rule accuracy | > 85% |
| Enemy weakness usage | > 80% |
| Damage range validity | > 95% |
| Spell diversity | high |
| Generic spell rate | low |
| Average latency | playable |

---

### 14.2 Eval Examples

Test cases:

```text
flame + circle should usually produce shield/burn effect
mirror + jagged should reflect damage
broken + anything should add side effect
eye + spiral should reveal future/confuse
dots + bone should create swarm/skeleton effect
```

Bad outputs:

```text
"casts fireball"
```

Why bad?

Because it ignores RuneLang.

Good output:

```json
{
  "spell_name": "Looping Ember Cage",
  "effect": "Creates a burning shield that blocks 2 damage and burns attacker for 1 damage.",
  "side_effect": "Room temperature rises; next water spell is weaker.",
  "enemy_hp_delta": -1,
  "player_hp_delta": 0,
  "status_effects": ["player_shielded"],
  "chaos": 5
}
```

---

## 15. Hackathon Deliverables

### 15.1 Required

- Gradio app on Hugging Face Space
- Demo video
- Social post
- Fine-tuned model uploaded to Hugging Face
- Dataset uploaded to Hugging Face
- README explaining RuneLang

---

### 15.2 Bonus Badge Targets

| Badge | How We Earn It |
|---|---|
| Well-Tuned | Fine-tuned MiniCPM5-1B-SFT on RuneLang |
| Off-Brand | Custom Gradio UI that looks like a tiny cursed dungeon |
| Field Notes | Blog post explaining RuneLang and training process |
| Open Trace | Publish sample game traces / spell logs |
| Llama Champion | Only if final runtime supports llama.cpp-compatible model |

---

## 16. MVP Scope

### Must Have

- RuneLang rulebook
- Synthetic dataset generation
- Fine-tuned OpenBMB model
- Gradio game UI
- 5 enemies
- 16 runes
- turn-based combat
- valid JSON spell outputs
- short demo video

---

### Should Have

- dungeon log
- funny spell names
- enemy weaknesses
- side effects
- final score
- Hugging Face dataset card
- model card

---

### Nice to Have

- freehand rune drawing
- MiniCPM-V glyph recognition
- spell animations
- voice narration
- procedural rooms
- unlockable cursed runes

---

## 17. Timeline

### Day 1: Language + Game Design

- finalize RuneLang glyphs
- define grammar
- define enemies
- define spell output schema
- create initial Python rule engine

---

### Day 2: Dataset Generation

- generate 5k synthetic examples
- validate JSON
- inspect 100 examples manually
- create train/test split
- upload dataset to Hugging Face

---

### Day 3: Fine-Tuning

- run LoRA fine-tuning on Modal
- test model locally or via endpoint
- measure JSON validity and rule accuracy
- iterate dataset if needed

---

### Day 4: Gradio MVP

- build game UI
- implement rune selection
- connect model inference
- implement HP/status update
- create 5-room dungeon loop

---

### Day 5: Polish

- add custom UI styling
- add dungeon log
- add enemy cards
- add better spell result panel
- add evaluation page

---

### Day 6: Demo + Submission

- record 60–90 sec demo
- write model card
- write dataset card
- write README
- create social post
- submit

---

## 18. Risks and Fixes

### Risk 1: Freehand drawing recognition is hard

Fix:

Start with rune buttons/stamps. Add freehand only after MVP works.

---

### Risk 2: Model outputs invalid JSON

Fix:

- fine-tune heavily on JSON-only outputs
- add JSON repair fallback
- validate with Pydantic
- retry once on invalid output

---

### Risk 3: Spell results are unbalanced

Fix:

Let Python enforce final HP limits.

The model proposes:

```json
{
  "enemy_hp_delta": -3
}
```

The game engine clamps values safely.

---

### Risk 4: Model becomes generic

Fix:

Add negative examples and strong dataset rules.

Bad:

```text
Fireball
Ice blast
Lightning strike
```

Good:

```text
Moth Tax Spiral
Cursed Refund Bell
Bone Swarm of Minor Regret
```

---

## 19. Final Submission Story

The story we tell judges:

```text
We created RuneLang, a tiny symbolic magic language.
Players draw spells using RuneLang glyphs.
We generated a synthetic spell-physics dataset and fine-tuned a small OpenBMB model to interpret this language.
The fine-tuned model acts as the dungeon engine: it reads the spell, understands glyph combinations, launches attacks, applies side effects, and updates the game world.
```

This makes the fine-tune central to the project.

The model is not just a narrator.

The model is the magic system.

---

## 20. Final Tagline

```text
Rune Goblin: draw bad spells, suffer beautifully.
```

Alternative tagline:

```text
A tiny dungeon crawler powered by a fine-tuned language of cursed doodles.
```
