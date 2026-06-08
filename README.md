# 🪄 Rune Goblin

> Draw bad spells, suffer beautifully.

A tiny dungeon crawler where players draw spells in an invented symbolic
language (**RuneLang**) and a fine-tuned [`openbmb/MiniCPM5-1B-SFT`](https://huggingface.co/openbmb/MiniCPM5-1B-SFT)
acts as the **spell engine** — reading glyph combinations and emitting JSON
that drives attacks, curses and game-state changes. Runtime visuals are not
image-generated; spell metadata recolors, resizes, retargets and animates
existing/procedural game assets.

See [`rune_goblin_plan.md`](./rune_goblin_plan.md) for the full design doc.

## Architecture

```
Rune buttons (Gradio / React)
   → serialized rune sequence + game state
   → fine-tuned MiniCPM5-1B + LoRA   (rune_goblin.inference)
   → spell outcome JSON              (validated by rune_goblin.schema)
   → game state engine               (rune_goblin.game, clamps HP)
   → updated UI

Drawn canvas (Gradio vision app)
   → canvas image + game state
   → goblinV1-gguf Q4_K_M sketch reader
   → visual_reading / rune metadata  (rune_goblin.vision_inference)
   → fine-tuned RuneLang spell JSON  (validated by rune_goblin.schema)
   → asset / VFX planner             (rune_goblin.vfx — rule-based today, MiniCPM-V-4.6 later)
   → attack / VFX metadata           (palette, projectile, particles, screen shake)
   → CSS/canvas renderer + game state engine
```

For the playable MVP the asset planner is a small deterministic function
(`rune_goblin.vfx`) instead of a second model: it is instant and never fails,
and its metadata shape mirrors the plan so a real `MiniCPM-V-4.6` planner can be
swapped in later without touching the renderer.

The deterministic rule engine (`rune_goblin.engine`) is both the **dataset
oracle** (it generates training targets) and the **runtime fallback** (used
until a fine-tuned adapter exists, so the UIs run before training finishes).

The **RPG sandbox** (`app/rpg_app.py` + `src/rune_goblin/world.py`) realizes the
map-exploration direction: tile-map areas with enemies, NPCs, chests, shrines,
powerups, locked doors and a boss. The canvas client owns movement/rendering;
`resolve_world_cast` turns drawn/selected runes + the faced target into a
validated spell **and** a list of world actions (unlock, loot, defeat, heal,
travel-gate…). Python stays the spell engine and balance authority.

## Layout

| Path | What |
|---|---|
| `src/rune_goblin/runelang.py` | 16 runes, grammar, combos, enemies, rooms |
| `src/rune_goblin/engine.py` | spell-physics rule engine + HP clamping |
| `src/rune_goblin/schema.py` | Pydantic spell schema + JSON repair |
| `src/rune_goblin/generate_dataset.py` | synthetic dataset → `data/*.jsonl` |
| `src/rune_goblin/finetune.py` | LoRA/QLoRA training (TRL + PEFT) |
| `src/rune_goblin/inference.py` | load base + adapter, cast spells |
| `src/rune_goblin/vision_inference.py` | load `ASHu2/goblinV1`, read canvas drawings |
| `src/rune_goblin/evaluate.py` | game-engine eval metrics |
| `src/rune_goblin/vfx.py` | deterministic asset/VFX planner (palette, projectile, particles, shake) |
| `src/rune_goblin/game.py` | 5-room dungeon state machine (vision + text/rule cast paths) |
| `src/rune_goblin/world.py` | **RPG world**: tile-map areas, entities, and cast→world-action resolution |
| `app/rpg_app.py` | **Gradio + canvas RPG** — free-roaming sandbox (the main game) |
| `app/rpg_bridge.py` | FastAPI `/rg/world` + `/rg/cast` bridge for the canvas client |
| `app/rpg_static/` | `rpg.js` + `rpg.css` — the HTML5 canvas game client |
| `app/rpg_static/sprites/` | curated Tiny Swords sprites (CC0) baked for the renderer |
| `assets/` | raw Tiny Swords packs (git-ignored; drop the itch download here) |
| `app/vision_app.py` | **Gradio** — linear 5-room combat game (draw + tap, VFX, rune guide) |
| `app/app.py` | minimal Gradio rune-button game (legacy) |
| `api/server.py` | FastAPI backend for the React frontend |
| `frontend/` | Vite + React custom cursed-dungeon UI |
| `notebooks/` | dataset exploration and Modal.com vision fine-tuning notebooks |
| `data/` | drop your `.jsonl` training data here |
| `models/` | downloaded base model + trained adapters |

## Setup

Prerequisites: [`uv`](https://docs.astral.sh/uv/), Node 20+, an `HF_TOKEN` in `.env`.

```bash
# 1. Python env (UI + game only)
uv sync

# 2. Add the heavy ML stack for training / local model inference
uv sync --extra train

# 2b. Add GGUF runtime support for the local vision model
uv sync --extra gguf

# 3. Download the fine-tuning base model into models/
uv run rune-goblin-download            # add --gguf for the .env serving model

# 4. Frontend deps
cd frontend && npm install && cd ..
```

## Workflow

```bash
# Generate a synthetic dataset (writes data/rune_spells.jsonl + _val.jsonl)
uv run rune-goblin-data --n 5000

# (You can also just drop your own data/*.jsonl — same chat format.)

# Fine-tune LoRA on your GPU (QLoRA 4-bit by default; 16GB is plenty)
uv run rune-goblin-train --data data/rune_spells.jsonl

# Evaluate (rule engine, or the model once trained)
uv run rune-goblin-eval --n 200            # add --rules-only to skip the model
```

## Vision fine-tuning on Modal.com

For the hand-drawn canvas model, use the Modal.com notebook workflow:

1. Open [`notebooks/MODAL-run-p1Jun2026.ipynb`](./notebooks/MODAL-run-p1Jun2026.ipynb)
   in Modal Notebooks.
2. Attach a GPU, add your Hugging Face and W&B secrets, and run the notebook
   top-to-bottom.
3. The notebook prepares the vision JSONL data, fine-tunes `openbmb/MiniCPM-V-4.6`
   with ms-swift LoRA, evaluates samples, and exports the adapter artifacts.

See [`docs/FINETUNE_VISION.md`](./docs/FINETUNE_VISION.md) for the full
fine-tuning reference and model-serving notes.

## Run the game

### 🗺️ RPG sandbox (the main game)

A free-roaming tile world: explore an overworld hub and three dungeons, fight
enemies, unlock chests and doors, bless yourself at shrines, find the Calendar
Key, and beat the Calendar Beast. Movement and rendering run in an HTML5 canvas;
casting round-trips to the Python engine + `goblinV1` vision model. The game is
served at `/play` and embedded in a Gradio app.

```bash
RG_USE_MODEL=1 \
RG_VISION_MODEL=models/goblinV1-gguf/gguf/rune-goblin-v46-Q4_K_M.gguf \
RG_VISION_MMPROJ=models/goblinV1-gguf/gguf/rune-goblin-v46-mmproj-f16.gguf \
uv run --extra gguf python app/rpg_app.py
# → http://localhost:7862   (set RG_USE_MODEL=0 to play purely on the rule engine)
```

**Controls:** `WASD` / arrows move · `1–9` pick runes (or click the rune deck) ·
`Space` cast at whatever you face · `E` draw a spell (read by goblinV1) · `C`
clear runes · `🔊` music · `⛶` fullscreen · step into portals to travel. Face an
enemy and cast; hit its weakness for bonus damage. Locked chests/doors show what
runes they need.

The world renders with real **[Tiny Swords](https://pixelfrog-assets.itch.io/tiny-swords)**
pixel art by **Pixel Frog** (CC0): grassy islands, knight player, torch goblins,
towers and chests. Background music is an original procedural chiptune (Web
Audio) that starts on your first click/keypress — toggle it with `🔊`. If a
sprite is missing the game falls back to emoji, so it always runs.

> Deployment note: `rpg_app.py` mounts FastAPI routes alongside Gradio
> (`gr.mount_gradio_app`) and runs under `uvicorn`. For a Hugging Face Space, use
> a Docker space (or expose `app` to uvicorn) rather than the plain Gradio SDK
> auto-launch.

### ⚔️ Linear combat game

`app/vision_app.py` is the simpler 5-room combat game. There are two ways to cast every turn:

- **Draw** a RuneLang spell on the canvas → the fine-tuned `goblinV1` vision
  model reads your doodle and decides the spell.
- **Tap 2–4 runes** from the board → instant deterministic rule-engine cast
  (great for speed, and while the vision model warms up).

```bash
# The full game with the downloaded goblinV1 GGUF reading your drawings
RG_USE_MODEL=1 \
RG_VISION_MODEL=models/goblinV1-gguf/gguf/rune-goblin-v46-Q4_K_M.gguf \
RG_VISION_MMPROJ=models/goblinV1-gguf/gguf/rune-goblin-v46-mmproj-f16.gguf \
uv run --extra gguf python app/vision_app.py
# → http://localhost:7861
# The first drawing cast loads the model (~30s on CPU, faster on GPU). Rune-button
# casts are instant. Set RG_USE_MODEL=0 to play purely on the rule engine.

# Minimal legacy rune-button game
uv run python app/app.py                   # → http://localhost:7860

# OR: React frontend + FastAPI backend (rune buttons)
uv run uvicorn api.server:app --port 8000  # terminal 1
cd frontend && npm run dev                 # terminal 2 → http://localhost:5173
```

Set `RG_USE_MODEL=1` (and optionally `RG_BASE_MODEL` / `RG_ADAPTER`) to switch
the UIs from the rule engine to the fine-tuned model.

For the drawing app, set `RG_VISION_MODEL` to either a local merged MiniCPM-V
Transformers directory or a local `.gguf` file. For GGUF, also set
`RG_VISION_MMPROJ` to the downloaded projector. The model returns nested
`visual_reading` + `spell` JSON; the game applies only the validated and clamped
`spell` object.

In the full RPG pipeline, the smaller sketch model should only read the player's
drawing and produce metadata such as detected runes, ambiguity, stroke energy
and target hints. The stronger asset planner receives validated spell JSON plus
player condition, weapon, statuses, power level, enemy state and room/map
context, then returns attack/VFX metadata for the renderer.

## Notes on the model

- **Fine-tuning base**: `openbmb/MiniCPM5-1B-SFT` — safetensors, llama-arch,
  LoRA-trainable. This is what `rune-goblin-download` and `finetune.py` use.
- **Vision fine-tune**: `ASHu2/goblinV1` — merged MiniCPM-V model for canvas
  drawings. The local GGUF files live in `models/goblinV1-gguf/gguf/`; use
  `app/vision_app.py` for the first playable drawing prototype.
- **Sketch metadata model**: `models/goblinV1-gguf/gguf/rune-goblin-v46-Q4_K_M.gguf`
  — fast reader for user sketches and rune metadata.
- **Asset planner model**: `models/MiniCPM-V-4.6-gguf/MiniCPM-V-4_6-Q8_0.gguf`
  — planned higher-quality model for attack type, palette, size, area, path,
  impact reaction, particle tags and animation timing from validated spell JSON.
- The `MODEL` in `.env` (`openbmb/MiniCPM-o-4_5-gguf`) is a **quantized GGUF
  multimodal** model — it's the llama.cpp/serving + optional vision path and
  **cannot** be LoRA-fine-tuned. Download it with `--gguf` only if you need it.

Renderer rule: do not generate new images during combat or exploration. Use
model metadata to drive existing sprites, particles, overlays, CSS/canvas
effects, weapon trails, colors, sizes and enemy reactions.

## Credits

All art/audio packs are free / CC0. The raw packs live in the git-ignored
`assets/`; a curated subset is baked into `app/rpg_static/{sprites,vfx,icons,sfx}/`
with a generated `manifest.json` (regenerate by re-running the bake step).

- **Terrain & buildings**: [Tiny Swords](https://pixelfrog-assets.itch.io/tiny-swords) by **Pixel Frog** (CC0).
- **Creatures (enemies/NPCs)**: Basic magical animations pack — elementals,
  golems, witch, treant, fairy, pixie, necromancer, sorceress, druid, wisp.
- **Spell VFX**: GameFX spritesheets — fireball/cast/burst, ice cast/shatter,
  poison, tornado, holy explosion, magic barrier, explosions, stars. Cast magic
  is layered so it grows more elaborate with the spell's tier (rune count, chaos,
  damage, curse).
- **Spell sounds**: Retro Magic FX — element spell SFX (fire/ice/electric/
  light/dark/earth/water/wind) plus charging/sweeps, played per element on cast.
- **Magic circles**: Rune Goblin Magic Circles pack — a 100-spell atlas (8-frame
  96px rings). On cast, the circle whose runes best match the drawn spell animates
  under the caster (and the target at higher tiers), growing with the spell tier.
- **Rune icons**: Mythril Age Icons — one icon per RuneLang glyph (no emoji).
- **Music**: original procedural chiptune synthesized in-browser via the Web
  Audio API (no external audio files). `🔊` toggles all music + SFX.
