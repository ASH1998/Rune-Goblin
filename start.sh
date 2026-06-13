#!/usr/bin/env bash
# Launch the Rune Goblin game.
#   ./start.sh          → run models on CPU
#   ./start.sh --gpu    → offload all GGUF layers to the GPU
# Set RG_USE_MODEL=0 in the environment to play purely on the rule engine.
set -euo pipefail

# CPU by default; --gpu flips to full offload (-1 = all layers on GPU).
GPU_LAYERS=0
if [[ "${1:-}" == "--gpu" ]]; then
  GPU_LAYERS=-1
  echo "[start] GPU mode: offloading all GGUF layers to the GPU"
else
  echo "[start] CPU mode (pass --gpu to use the GPU)"
fi

RG_USE_MODEL=1 \
RG_VISION_MODEL=models/goblinV1-gguf/gguf/rune-goblin-v46-Q4_K_M.gguf \
RG_VISION_MMPROJ=models/goblinV1-gguf/gguf/rune-goblin-v46-mmproj-f16.gguf \
RG_USE_DIALOGUE_MODEL=1 \
RG_DIALOGUE_MODEL=models/MiniCPM-V-4.6-gguf/MiniCPM-V-4_6-Q4_K_M.gguf \
RG_GGUF_GPU_LAYERS="${GPU_LAYERS}" \
uv run --extra gguf python app/rpg_app.py
# → http://localhost:7862   (set RG_USE_MODEL=0 to play purely on the rule engine)
