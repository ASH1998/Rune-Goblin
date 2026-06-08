# Rune Goblin - Progress

> Rune Goblin is moving from training work into the playable prototype: players
> draw RuneLang spells, the fine-tuned vision model reads the drawing, and the
> game engine applies the returned spell JSON.

---

## Status at a glance

| Area | State |
|---|---|
| Repo scaffolding: text engine, game state, API, React frontend | Done and committed |
| Dataset exploration notebook | Done and committed: `1412fb8` |
| Vision dataset on Hugging Face | Done: `ASHu2/rune_goblin_visual_dataset` |
| Modal vision fine-tune docs/notebooks | Done and committed: `08627a2`, `7370187` |
| Legacy vision scripts cleanup | Done and committed: `1ec4add` |
| Vision fine-tune on Modal A100 | Done: 3 epochs / 846 steps |
| Merged model + LoRA pushed | Done: `ASHu2/goblinV1` root + `lora/` |
| Fine-tuned GGUF files downloaded locally | Done: `models/goblinV1-gguf/gguf/` |
| Gradio drawing app using local GGUF | Done and pushed: `3960dc8` |
| Full playable game (draw + rune board, VFX, guide) | Done: `app/vision_app.py` |
| Deterministic VFX/asset planner | Done: `src/rune_goblin/vfx.py` |
| Free-roaming RPG sandbox (canvas world) | Done: `app/rpg_app.py` + `world.py` |
| Task-level eval over validation set | Pending |

---

## What is in the project now

### Core game/runtime

- `src/rune_goblin/runelang.py` - 16 runes, combos, enemies, rooms.
- `src/rune_goblin/engine.py` - deterministic spell physics and HP clamping.
- `src/rune_goblin/schema.py` - spell JSON schema plus nested vision schema:
  `visual_reading` + `spell`.
- `src/rune_goblin/game.py` - 5-room dungeon state machine. Two cast paths:
  `use_vision_model` drives drawing casts (goblinV1), `use_text_model` drives
  rune-button casts (defaults to the deterministic rule engine).
- `src/rune_goblin/vfx.py` - deterministic asset/VFX planner. Maps a validated
  `SpellResult` to renderer metadata (palette, projectile glyph, particles,
  screen shake, floating damage number) plus enemy-sprite and biome lookups.
  Rule-based stand-in for the MiniCPM-V-4.6 asset planner.
- `src/rune_goblin/inference.py` - text-model spell inference path.
- `src/rune_goblin/vision_inference.py` - MiniCPM-V vision path with two backends:
  Transformers/safetensors and local GGUF via `llama-cpp-python`.

### Apps

- `app/vision_app.py` - **the full playable game**. Retro cursed-dungeon Gradio
  UI: animated battle stage (enemy sprite, HP bar, room backdrop, per-cast VFX),
  heart/score/courage HUD, a sketch canvas (drawings read by goblinV1) AND a
  16-rune board for instant rule-engine casts, a RuneLang grimoire/combo guide,
  spell result panel with detected runes + confidence, dungeon log, win/loss
  banners, and a parsed-JSON trace panel. A blank-canvas guard and a "reading…"
  beat smooth out the model latency.
- `app/app.py` - minimal legacy Gradio rune-button game.
- `api/server.py` and `frontend/` - existing FastAPI + Vite/React path.

### RPG sandbox (free-roaming)

- `src/rune_goblin/world.py` - the RPG world: four tile-map areas (overworld hub
  + Mirror Fungus Caverns, Wet Library, Calendar Beast Arena), entity types
  (enemy/boss/npc/chest/locked_door/shrine/portal/powerup), `build_world()`
  serialization, `validate_world()` (placement + reachability), and
  `resolve_world_cast()` mapping runes+target → spell outcome + world actions.
- `app/rpg_app.py` - Gradio shell that mounts FastAPI (`gr.mount_gradio_app`) and
  serves the canvas game at `/play`, embedded via an iframe. Run on port 7862.
- `app/rpg_bridge.py` - `/rg/world` and `/rg/cast` routes; `/rg/cast` runs the
  goblinV1 vision model for drawings, then resolves world effects deterministically.
- `app/rpg_static/rpg.js` + `rpg.css` - HTML5 canvas client: tile/sprite
  rendering, WASD/arrow roaming + facing, collision, entity targeting, rune
  quick-cast + drawing overlay, VFX, multi-area portals, win/loss screens.

The Gradio `head=`/`js=` hooks are dropped under `mount_gradio_app` and `gr.HTML`
won't run inline scripts, so the canvas game is served as a standalone page and
embedded via a same-origin iframe — robust, and still one Gradio app.

### Fine-tune and docs

- `notebooks/MODAL-run-p1Jun2026.ipynb` - Modal notebook with completed
  fine-tune workflow and outputs.
- `notebooks/deprecated-rune_goblin_vision_finetune_modal.ipynb` - older
  notebook retained as deprecated reference.
- `docs/FINETUNE_VISION.md` - Modal/ms-swift vision fine-tuning reference.
- `README.md` - updated with Modal fine-tuning and local GGUF drawing-app usage.

### Local model artifacts

Downloaded from `ASHu2/goblinV1/tree/main/gguf` into ignored `models/` paths:

| File | Size |
|---|---:|
| `models/goblinV1-gguf/gguf/rune-goblin-v46-Q4_K_M.gguf` | 529 MB |
| `models/goblinV1-gguf/gguf/rune-goblin-v46-Q8_0.gguf` | 812 MB |
| `models/goblinV1-gguf/gguf/rune-goblin-v46-mmproj-f16.gguf` | 1.1 GB |

These are intentionally not tracked by git because `models/` is ignored.

---

## Current run command

Install the GGUF runtime:

```bash
uv sync --extra gguf
```

Run the **RPG sandbox** (free-roaming, the main game):

```bash
RG_USE_MODEL=1 \
RG_VISION_MODEL=models/goblinV1-gguf/gguf/rune-goblin-v46-Q4_K_M.gguf \
RG_VISION_MMPROJ=models/goblinV1-gguf/gguf/rune-goblin-v46-mmproj-f16.gguf \
uv run --extra gguf python app/rpg_app.py        # → http://localhost:7862
```

Controls: WASD/arrows move · 1–9 pick runes · Space cast · E draw · step into
portals to travel. `RG_USE_MODEL=0` plays purely on the rule engine.

Run the **linear combat game**:

```bash
RG_USE_MODEL=1 \
RG_VISION_MODEL=models/goblinV1-gguf/gguf/rune-goblin-v46-Q4_K_M.gguf \
RG_VISION_MMPROJ=models/goblinV1-gguf/gguf/rune-goblin-v46-mmproj-f16.gguf \
uv run --extra gguf python app/vision_app.py     # → http://localhost:7861
```

Play with `RG_USE_MODEL=0` to skip the model entirely (drawings then fall back
to the rule engine; rune-button casts are unaffected). Rune-button casts are
always instant; the first drawing cast loads the vision model (~30s on CPU).
`.claude/launch.json` has a `rune-goblin` preview config (model off) for quick
UI checks.

---

## Training run notes

Vision fine-tune was a healthy Modal A100 run:

- 3 epochs / 846 steps, effective batch 16.
- `train/loss` dropped from ~4.7 to ~0.11.
- `eval/loss` ended around ~0.115 and was still gently improving.
- `train/token_acc` reached ~0.96.
- `eval/token_acc` reached ~0.957.
- Generalization gap was small; no obvious overfitting from loss curves.

Caveat: token accuracy is teacher-forced JSON-token accuracy. The real game
metric is generation-time validity and rune recognition.

---

## Resolved issues

| Symptom | Fix |
|---|---|
| `model_type 'minicpm-v-4_6' not in [...]` | Use `minicpmv4_6`. |
| W&B CLI args rejected by ms-swift | Use `WANDB_PROJECT` / `WANDB_NAME` env vars with `--report_to wandb`. |
| `--train_type` rejected in ms-swift 4.2.3 | Drop it; LoRA is default and configured by rank/alpha. |
| Slow ModelScope download | Set `USE_HF=1`. |
| GPU underutilized | Increase dataloader workers. |
| OOM at batch 32 | Use batch 16 and `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`. |
| Swift LoRA could not attach via `PeftModel` | Merge with `swift export --merge_lora true`. |
| MiniCPM-V has no `.chat()` method in this path | Use `AutoModelForImageTextToText` + `AutoProcessor` + `generate`. |
| App returned fallback JSON | Added visible diagnostics and local GGUF backend. |
| `llama_cpp` missing | Added optional `gguf` extra with `llama-cpp-python`. |
| GGUF failed to load: missing `blk.24.*` | Local GGUF metadata patched from `qwen35.block_count=25` to `24`. |
| GGUF failed to load: missing `nextn` tensor | Local GGUF metadata patched from `qwen35.nextn_predict_layers=1` to `0`. |

Important: the GGUF metadata patch is local because the GGUF binaries are
ignored. If the files are re-downloaded and upstream has not fixed them, the
metadata patch may need to be repeated or the GGUF re-exported correctly.

---

## Verified locally

- `uv run --extra gguf ruff check app src/rune_goblin` - passing.
- `uv run --extra gguf python -m compileall app src/rune_goblin` - passing.
- Local Q4 GGUF + mmproj load through `llama-cpp-python` - passing after metadata patch.
- End-to-end `Game.cast_drawing(...)` smoke test with the live goblinV1 GGUF -
  detected `['three_dots','wave']` @0.92, valid nested JSON, ~32s on CPU.
- `uvx ruff check app/vision_app.py src/rune_goblin/{vfx,game}.py` - passing.
- Headless app-callback test: new game, rune selection, rune-button cast
  (bell+coin → -4 on Queue Goblin), drawing-cast generator frames, blank-canvas
  guard, and a full 5-room playthrough that wins (score 596 in 8 turns).
- Browser smoke test (Gradio on :7861): retro UI renders, a live bell+coin cast
  resolved to "Mildly Regret" (-4, weakness_revealed) with the gold VFX flash.
- RPG world (`world.py`): `validate_world()` reports zero placement/reachability
  problems; cast resolution unit-checked for combat, chest gating+loot, doors,
  item-gated gate, shrine, NPC, air-cast, and boss-kill (`win_game`).
- RPG bridge (:7862): `/rg/world` serves 4 areas + 16 runes; `/rg/cast` resolves
  rune and drawing modes (drawing falls back gracefully with the model off).
- RPG browser playthrough (canvas): roam + face + cast (bell+coin → -4 on the
  Queue Goblin + retaliation), chest unlock with loot, shrine heal/courage,
  portal travel overworld→library, then the full quest chain — ink chest →
  Calendar Key → open sealed gate → arena → Calendar Beast 18→0 → 🏆 win screen.

---

## Pending work

1. Run generation eval over the validation set:
   - valid JSON rate
   - rune recall / exact rune-set match
   - damage and chaos range validity
   - weakness usage
2. If rune recall is weak, consider another run with `--freeze_vit false`.
3. Add a small eval script for `ASHu2/goblinV1` GGUF using validation images.
4. Drawing UX — **done** in `app/vision_app.py`: rune guide/combo panel, canvas
   reset, detected-rune readout with confidence, animated VFX, win/loss banners.
   Remaining polish ideas: GPU offload for faster drawing casts, optional sound.
5. Decide deployment target:
   - Hugging Face Space with Transformers model, or
   - local/hosted llama.cpp GGUF runtime.

---

## Standing constraints

- Commit only after explicit user approval.
- Do not commit large model artifacts under `models/`; keep them ignored or use
  a proper external model store.
- Use the global git identity and existing signing behavior.
