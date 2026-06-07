# Fine-Tuning the Rune Goblin Vision Model (MiniCPM-V 4.6)

How to fine-tune a vision-language model to read hand-drawn RuneLang glyphs from
a canvas image + game state and emit `visual_reading` + `spell` JSON.

> **TL;DR**
> 1. The GGUF you downloaded is **inference-only** — fine-tuning needs the full
>    safetensors model `openbmb/MiniCPM-V-4.6` (~2.6 GB).
> 2. Convert the dataset to absolute paths: `uv run python scripts/prepare_vision_dataset.py`
> 3. Train LoRA with **ms-swift** (one command) or **LLaMA-Factory** (ready config).
> 4. (Optional) merge LoRA → convert to GGUF to serve in the game via llama.cpp.

---

## 0. Critical: GGUF cannot be fine-tuned

| Artifact | What it's for |
|---|---|
| `models/MiniCPM-V-4.6-gguf/MiniCPM-V-4_6-Q8_0.gguf` + `mmproj-model-f16.gguf` | **Serving / inference** with llama.cpp / Ollama. Quantized — **not trainable.** |
| `openbmb/MiniCPM-V-4.6` (safetensors, 2.6 GB) | **The fine-tuning base.** This is what you train. |

So the flow is: **train on the safetensors model → (optionally) export back to GGUF
for fast game-time inference.**

Download the trainable base into `models/`:

```bash
cd /home/ashu/github/goblin
source .env   # HF_TOKEN
uv run python - <<'PY'
import os
from huggingface_hub import snapshot_download
snapshot_download("openbmb/MiniCPM-V-4.6",
                  local_dir="models/MiniCPM-V-4.6",
                  token=os.environ.get("HF_TOKEN"),
                  ignore_patterns=["*.pth","*.onnx"])
PY
```

### Model facts (drives VRAM planning)

`openbmb/MiniCPM-V-4.6` is the **lightweight / on-device** member of the family:

- Total ≈ **2.6 B params** (single `model.safetensors`, 2.6 GB bf16)
- Text backbone: `qwen3_5_text` — hidden 1024, 24 layers, vocab 248k
- Vision encoder: SigLIP-style — hidden 1152, 27 layers, max image 980px
- Arch class: `MiniCPMV4_6ForConditionalGeneration` (needs `trust_remote_code`)

**This easily fits LoRA in bf16 on your RTX 4070 Ti SUPER (16 GB)** — no 4-bit
required. Our canvases are only 256×256, so each image produces few vision
tokens, keeping memory low. (Full fine-tuning is also feasible with care.)

---

## 1. The dataset

Location: `data/rune_goblin_visual_dataset_5000/rune_goblin_visual_dataset/`

- **5,000 samples**, 256×256 RGB JPEG canvases of wobbly, hand-drawn ink runes
  on a parchment background (plus scattered dot-noise to mimic real canvas mess).
- Train/val already split **4,500 / 500**. Assistant JSON is **100 % valid**.
- Category mix: `basic_clean` 1000, `messy_handdrawn` 1200, `combo_rules` 1100,
  `cursed_broken_mark` 700, `enemy_specific` 700, `invalid_ambiguous` 300.

### Task

```
canvas image  +  game-state text  →  { visual_reading, spell }  (JSON only)
```

### Provided formats (pick one; image paths are **relative**)

| File | Shape |
|---|---|
| `*_full.jsonl` | everything: `id, category, image, runes_ground_truth, game_state, messages` |
| `train/validation_messages.jsonl` | `{image, messages}` with `<image>` token in the user turn |
| `train/validation_hf_vision_messages.jsonl` | HF/TRL content-parts: `{images:[...], messages:[{content:[{type:image},{type:text}]}]}` |
| `train/validation_llava_style.jsonl` | `{image, conversations:[{from,value}], system}` |

### Output JSON the model must learn

```json
{
  "visual_reading": {
    "detected_runes": ["spiral","eye","broken_mark"],
    "ambiguous_runes": [],
    "drawing_style": "wobbly ink marks",
    "layout": "left-to-right chain",
    "confidence": 0.91,
    "notes": ["broken_mark_adds_cursed_side_effect"]
  },
  "spell": {
    "spell_name": "Cursed Foresight Loop",
    "spell_type": "prophecy_loop_curse",
    "flavor": "...",
    "effect": "Deals 2 damage to Mirror Fungus; confuses for 1 turn.",
    "side_effect": "player loses a little courage.",
    "enemy_hp_delta": -2,    // range -4..0
    "player_hp_delta": -1,   // range -3..2
    "status_effects": ["enemy_confused","spell_cursed"],
    "chaos": 8               // range 1..10
  }
}
```

Game-design signal baked into the data: **clearer drawings → higher `confidence`,
lower `chaos`; messy/ambiguous drawings still cast but raise chaos and can turn
cursed.** Bad player art is part of the game loop.

### Step 1 — convert to absolute paths + framework formats

Frameworks need absolute image paths. Run:

```bash
uv run python scripts/prepare_vision_dataset.py
# writes data/vision_prepared/:
#   vision_swift_{train,val}.jsonl       (ms-swift)
#   vision_sharegpt_{train,val}.jsonl    (LLaMA-Factory ShareGPT)
```

---

## 2. Option A — ms-swift (recommended, simplest)

MiniCPM-V 4.6 has **native** ms-swift support. One CLI, handles the vision
plumbing and LoRA target modules for you.

```bash
uv pip install "ms-swift>=3.0" transformers accelerate peft   # into the project venv
# (or: pip install ms-swift in a dedicated env)
```

Train LoRA:

```bash
source .env
swift sft \
  --model models/MiniCPM-V-4.6 \
  --model_type minicpm-v-4_6 \
  --dataset data/vision_prepared/vision_swift_train.jsonl \
  --val_dataset data/vision_prepared/vision_swift_val.jsonl \
  --train_type lora \
  --lora_rank 16 --lora_alpha 32 \
  --torch_dtype bfloat16 \
  --num_train_epochs 3 \
  --per_device_train_batch_size 2 \
  --gradient_accumulation_steps 8 \
  --learning_rate 1e-4 \
  --freeze_vit true \
  --max_length 2048 \
  --gradient_checkpointing true \
  --eval_steps 200 --save_steps 200 \
  --output_dir models/rune-goblin-vision-lora
```

Notes:
- `--freeze_vit true` trains only the LLM + resampler adapters (faster, lighter,
  and enough since the glyph vocabulary is small). Set `false` to also adapt the
  vision encoder if recognition of messy drawings underperforms.
- Effective batch = 2 × 8 = 16. Drop `per_device_train_batch_size` to 1 (and
  raise grad-accum) if you hit OOM.
- Inference after training:
  ```bash
  swift infer --adapters models/rune-goblin-vision-lora \
              --load_data_args true --val_dataset data/vision_prepared/vision_swift_val.jsonl
  ```
- Merge LoRA into the base:
  ```bash
  swift export --adapters models/rune-goblin-vision-lora --merge_lora true
  ```

---

## 2. Option B — LLaMA-Factory (ready-made config)

OpenBMB ships a MiniCPM-V 4.6 LoRA recipe for LLaMA-Factory.

```bash
git clone https://github.com/hiyouga/LLaMA-Factory && cd LLaMA-Factory
pip install -e ".[torch,metrics]"
```

1. Register the dataset — add to `data/dataset_info.json`:

   ```json
   "rune_goblin_vision": {
     "file_name": "/home/ashu/github/goblin/data/vision_prepared/vision_sharegpt_train.jsonl",
     "formatting": "sharegpt",
     "columns": { "messages": "conversations", "images": "images", "system": "system" },
     "tags": { "role_tag": "from", "content_tag": "value",
               "user_tag": "human", "assistant_tag": "gpt" }
   }
   ```

2. Train (start from the official example and point `dataset` at `rune_goblin_vision`):

   ```bash
   llamafactory-cli train \
     --stage sft --do_train true \
     --model_name_or_path /home/ashu/github/goblin/models/MiniCPM-V-4.6 \
     --trust_remote_code true \
     --dataset rune_goblin_vision \
     --template minicpm_v \
     --finetuning_type lora --lora_rank 16 --lora_target all \
     --freeze_vision_tower true \
     --cutoff_len 2048 \
     --per_device_train_batch_size 2 --gradient_accumulation_steps 8 \
     --learning_rate 1e-4 --num_train_epochs 3 \
     --bf16 true --gradient_checkpointing true \
     --output_dir models/rune-goblin-vision-lora-lf
   ```

   Reference config: <https://github.com/OpenSQZ/MiniCPM-V-CookBook/blob/main/finetune/llamafactory_minicpmv46.md>

---

## 3. VRAM guidance (16 GB)

| Setup | Fits 16 GB? | Notes |
|---|---|---|
| LoRA bf16, ViT frozen, bs=2, len=2048 | ✅ comfortable | recommended starting point |
| LoRA bf16, ViT trainable | ✅ likely | a bit more memory; helps messy-drawing recall |
| QLoRA 4-bit | ✅ easy | only needed if you also raise batch/seq a lot |
| Full fine-tune | ⚠️ tight | possible for a ~2.6B model with bs=1 + grad-ckpt |

If you OOM: `per_device_train_batch_size=1`, raise `gradient_accumulation_steps`,
keep `gradient_checkpointing true`, keep `freeze_vit true`.

---

## 4. Evaluate like a game engine

Beyond loss, the metrics that matter (mirrors `rune_goblin.evaluate`):

- **Valid JSON rate** (must parse to the `visual_reading`+`spell` schema) — target > 95 %
- **Rune-recognition accuracy** — compare `visual_reading.detected_runes` to
  `runes_ground_truth` in `*_full.jsonl`
- **Delta-range validity** — `enemy_hp_delta ∈ [-4,0]`, `player_hp_delta ∈ [-3,2]`,
  `chaos ∈ [1,10]`
- **Weakness usage** — weakness-hitting runes should produce meaningful effects

Quick recognition check after training (sketch):

```python
import json
from rune_goblin.schema import _extract_json   # reuse the JSON repair
# load *_full.jsonl for ground-truth runes, run model.infer(image, state),
# parse visual_reading.detected_runes, compare to runes_ground_truth.
```

---

## 5. Serve the fine-tune in the game

Two paths:

1. **transformers (simplest):** load `models/MiniCPM-V-4.6` + the LoRA adapter
   (or the merged model) with `trust_remote_code=True` and call its chat method
   with the canvas image + state prompt. Wire this into a vision variant of
   `rune_goblin.inference`.
2. **llama.cpp / Ollama (fast, matches your GGUF download):** after
   `swift export --merge_lora true`, convert the merged HF model to GGUF with
   `llama.cpp/convert_hf_to_gguf.py`, regenerate the `mmproj` projector, then
   serve. This produces a fine-tuned analogue of the Q8_0 + mmproj pair you
   already have in `models/MiniCPM-V-4.6-gguf/`.

The game prompt must match training exactly (see the system + user strings in
the dataset): system = "You are Rune Goblin, a tiny vision spell engine…",
user = `<image>\nSTATE: player_hp=… enemy=… …\nLook at the drawn RuneLang spell…`.

---

## 6. Pitfalls

- **Don't** point training at the GGUF — use `openbmb/MiniCPM-V-4.6` safetensors.
- **Relative image paths** in the raw dataset will fail mid-training; always run
  `prepare_vision_dataset.py` first (it makes them absolute and verifies they exist).
- **Prompt drift:** keep the exact system/user template from the dataset at game
  time or accuracy drops.
- The dataset is **synthetic** — after launch, log real Gradio-canvas drawings
  and append them as a second-stage dataset (the README suggests this).
- `trust_remote_code=True` is required (custom `MiniCPMV4_6` architecture).
```
