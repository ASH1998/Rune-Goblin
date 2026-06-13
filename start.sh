#!/usr/bin/env bash
# Launch the Rune Goblin game.
#   ./start.sh          → run the vision model locally on CPU
#   ./start.sh --gpu    → run the vision model locally, all GGUF layers on GPU
#   ./start.sh --modal  → use the vision model served from Modal (no local weights)
# Set RG_USE_MODEL=0 in the environment to play purely on the rule engine.
set -euo pipefail

MODE="${1:-}"

if [[ "${MODE}" == "--modal" ]]; then
  # Vision via the serverless T4 endpoint (deploy/modal_vision.py). No local
  # GGUF/torch — the canvas cast is a remote HTTPS call. Dialogue is unchanged.
  if [[ -f .env ]]; then
    set -a; source .env; set +a
  fi
  : "${MODAL_APP_URL:?set MODAL_APP_URL in .env (e.g. https://<workspace>--goblin-vision-serve.modal.run)}"
  : "${RG_VISION_API_KEY:?set RG_VISION_API_KEY in .env (the Modal --api-key)}"
  echo "[start] Modal mode: vision via ${MODAL_APP_URL}"

  RG_USE_MODEL=1 \
  RG_USE_VISION_API=1 \
  RG_VISION_API_URL="${MODAL_APP_URL%/}/v1/chat/completions" \
  RG_VISION_API_MODEL="${RG_VISION_API_MODEL:-ASHu2/goblinV1}" \
  uv run python app/rpg_app.py
  exit 0
fi

# Local GGUF modes. CPU by default; --gpu flips to full offload (-1 = all layers).
GPU_LAYERS=0
if [[ "${MODE}" == "--gpu" ]]; then
  GPU_LAYERS=-1
  echo "[start] GPU mode: offloading all GGUF layers to the GPU"
else
  echo "[start] CPU mode (pass --gpu for GPU, --modal for the Modal API)"
fi

RG_USE_MODEL=1 \
RG_VISION_MODEL=models/goblinV1-gguf/gguf/rune-goblin-v46-Q4_K_M.gguf \
RG_VISION_MMPROJ=models/goblinV1-gguf/gguf/rune-goblin-v46-mmproj-f16.gguf \
RG_USE_DIALOGUE_MODEL=1 \
RG_DIALOGUE_MODEL=models/MiniCPM-V-4.6-gguf/MiniCPM-V-4_6-Q4_K_M.gguf \
RG_GGUF_GPU_LAYERS="${GPU_LAYERS}" \
uv run --extra gguf python app/rpg_app.py
# → http://localhost:7862   (set RG_USE_MODEL=0 to play purely on the rule engine)
