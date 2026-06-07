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
| Task-level eval over validation set | Pending |
| Full game polish loop | Pending |

---

## What is in the project now

### Core game/runtime

- `src/rune_goblin/runelang.py` - 16 runes, combos, enemies, rooms.
- `src/rune_goblin/engine.py` - deterministic spell physics and HP clamping.
- `src/rune_goblin/schema.py` - spell JSON schema plus nested vision schema:
  `visual_reading` + `spell`.
- `src/rune_goblin/game.py` - 5-room dungeon state machine; now supports both
  rune-button casts and drawing-based casts.
- `src/rune_goblin/inference.py` - text-model spell inference path.
- `src/rune_goblin/vision_inference.py` - MiniCPM-V vision path with two backends:
  Transformers/safetensors and local GGUF via `llama-cpp-python`.

### Apps

- `app/app.py` - existing Gradio rune-button game.
- `app/vision_app.py` - new Gradio drawing app. It uses a sketch canvas, sends
  the canvas image plus current game state to the vision model, parses the
  nested JSON, and applies the validated/clamped spell result to the same game
  state machine.
- `api/server.py` and `frontend/` - existing FastAPI + Vite/React path.

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

Run the drawing app:

```bash
RG_USE_MODEL=1 \
RG_VISION_MODEL=models/goblinV1-gguf/gguf/rune-goblin-v46-Q4_K_M.gguf \
RG_VISION_MMPROJ=models/goblinV1-gguf/gguf/rune-goblin-v46-mmproj-f16.gguf \
uv run --extra gguf python app/vision_app.py
```

Default URL:

```text
http://localhost:7861
```

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
- End-to-end `Game.cast_drawing(...)` smoke test - produced valid nested
  `visual_reading` + `spell` JSON and applied the turn.

---

## Pending work

1. Run generation eval over the validation set:
   - valid JSON rate
   - rune recall / exact rune-set match
   - damage and chaos range validity
   - weakness usage
2. If rune recall is weak, consider another run with `--freeze_vit false`.
3. Add a small eval script for `ASHu2/goblinV1` GGUF using validation images.
4. Improve the drawing UX:
   - rune guide/reference panel
   - better canvas reset
   - spell history with detected runes
   - room win/loss polish
5. Decide deployment target:
   - Hugging Face Space with Transformers model, or
   - local/hosted llama.cpp GGUF runtime.

---

## Standing constraints

- Commit only after explicit user approval.
- Do not commit large model artifacts under `models/`; keep them ignored or use
  a proper external model store.
- Use the global git identity and existing signing behavior.
