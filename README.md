# 🪄 Rune Goblin

> Draw bad spells, suffer beautifully.

A tiny dungeon crawler where players draw spells in an invented symbolic
language (**RuneLang**) and a fine-tuned [`openbmb/MiniCPM5-1B-SFT`](https://huggingface.co/openbmb/MiniCPM5-1B-SFT)
acts as the **spell engine** — reading glyph combinations and emitting JSON
that drives attacks, curses and game-state changes.

See [`rune_goblin_plan.md`](./rune_goblin_plan.md) for the full design doc.

## Architecture

```
Rune buttons (Gradio / React)
   → serialized rune sequence + game state
   → fine-tuned MiniCPM5-1B + LoRA   (rune_goblin.inference)
   → spell outcome JSON              (validated by rune_goblin.schema)
   → game state engine               (rune_goblin.game, clamps HP)
   → updated UI
```

The deterministic rule engine (`rune_goblin.engine`) is both the **dataset
oracle** (it generates training targets) and the **runtime fallback** (used
until a fine-tuned adapter exists, so the UIs run before training finishes).

## Layout

| Path | What |
|---|---|
| `src/rune_goblin/runelang.py` | 16 runes, grammar, combos, enemies, rooms |
| `src/rune_goblin/engine.py` | spell-physics rule engine + HP clamping |
| `src/rune_goblin/schema.py` | Pydantic spell schema + JSON repair |
| `src/rune_goblin/generate_dataset.py` | synthetic dataset → `data/*.jsonl` |
| `src/rune_goblin/finetune.py` | LoRA/QLoRA training (TRL + PEFT) |
| `src/rune_goblin/inference.py` | load base + adapter, cast spells |
| `src/rune_goblin/evaluate.py` | game-engine eval metrics |
| `src/rune_goblin/game.py` | 5-room dungeon state machine |
| `app/app.py` | **Gradio** game UI (HF Space deliverable) |
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

```bash
# Gradio (rule engine by default; set RG_USE_MODEL=1 to use the fine-tune)
uv run python app/app.py                   # → http://localhost:7860

# OR: React frontend + FastAPI backend
uv run uvicorn api.server:app --port 8000  # terminal 1
cd frontend && npm run dev                 # terminal 2 → http://localhost:5173
```

Set `RG_USE_MODEL=1` (and optionally `RG_BASE_MODEL` / `RG_ADAPTER`) to switch
the UIs from the rule engine to the fine-tuned model.

## Notes on the model

- **Fine-tuning base**: `openbmb/MiniCPM5-1B-SFT` — safetensors, llama-arch,
  LoRA-trainable. This is what `rune-goblin-download` and `finetune.py` use.
- The `MODEL` in `.env` (`openbmb/MiniCPM-o-4_5-gguf`) is a **quantized GGUF
  multimodal** model — it's the llama.cpp/serving + optional vision path and
  **cannot** be LoRA-fine-tuned. Download it with `--gguf` only if you need it.
