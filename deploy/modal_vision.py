"""Serve the Rune Goblin vision model (``ASHu2/goblinV1``) on Modal.

One-time deploy of a serverless **T4** GPU that runs the merged MiniCPM-V-4.6
fine-tune behind an **OpenAI-compatible** endpoint (vLLM). The game talks to it
exactly like the dialogue model: ``POST /v1/chat/completions`` with a system
prompt, an ``image_url`` data-URI, and ``response_format=json_object``.

Behavior (per docs/MODAL_DEPLOYMENT.md):
  * GPU: T4                              ($0.000164/sec while warm)
  * scaledown_window = 5 min            -> scales to zero after 5 min idle
  * @modal.concurrent(max_inputs=10)    -> <=10 in-flight requests per replica
  * HF_TOKEN via the existing Modal secret ``huggingface-secret`` (fast pulls)
  * Endpoint auth via ``RG_VISION_API_KEY`` (Modal secret ``rg-vision``)

----------------------------------------------------------------------------
ONE-TIME SETUP (run once, locally):

  # 1. Authenticate the Modal CLI (token id/secret are in .env)
  modal token set --token-id "$MODAL_TOKEN_ID" --token-secret "$MODAL_SECRET"

  # 2. The HF token secret already exists as `huggingface-secret`.
  #    Create the endpoint API key (any long random string the game will send):
  modal secret create rg-vision RG_VISION_API_KEY="$(openssl rand -hex 32)"
  #    -> copy that value into the game's RG_VISION_API_KEY (.env / Space secret)

  # 3. Deploy:
  modal deploy deploy/modal_vision.py

Modal prints a URL like:
  https://<workspace>--goblin-vision-serve.modal.run
The game's RG_VISION_API_URL is that URL + "/v1/chat/completions".

Smoke test:
  curl -s https://<workspace>--goblin-vision-serve.modal.run/v1/models \
    -H "Authorization: Bearer $RG_VISION_API_KEY"
----------------------------------------------------------------------------

CLIENT NOTE (Phase 2): the vLLM recipe recommends sending
``"stop_token_ids": [248044, 248046]`` on each request to prevent runaway
generations. Add that to RemoteVisionSpellModel's request body alongside
``response_format={"type": "json_object"}``.

Requires vLLM >= 0.22.0 (first release with MiniCPMV4_6 support) and
transformers >= 5.7.0 — see VLLM_VERSION below.
Ref: https://recipes.vllm.ai/openbmb/MiniCPM-V-4.6
"""

from __future__ import annotations

import os
import subprocess

import modal

# --- Model -----------------------------------------------------------------
MODEL_ID = "ASHu2/goblinV1"   # public; HF_TOKEN used only for fast downloads
# Pin a commit SHA before going to production so deploys are reproducible.
MODEL_REVISION = os.environ.get("RG_VISION_MODEL_REVISION", "main")

# --- Serving knobs ---------------------------------------------------------
VLLM_PORT = 8000
MINUTES = 60  # seconds
N_GPU = 1
GPU_TYPE = "L4" 
# Recipe suggests starting at 8192 (model supports up to 256K). Plenty for a
# single canvas image + state; the 1.3B model leaves the T4 with room to spare.
MAX_MODEL_LEN = 8192

# The MiniCPMV4_6ForConditionalGeneration arch landed in vLLM 0.22.0 (PR #43213)
# and needs transformers >= 5.7.0. Earlier vLLM (e.g. 0.11) raises
# "Model architectures ['MiniCPMV4_6ForConditionalGeneration'] are not supported".
# PIN EXACTLY 0.22.0: vLLM 0.23.0 regressed the MiniCPM-V-4.6 image processor
# ("'MiniCPMV4_6ImageProcessor' object has no attribute 'version'"); 0.22.0 is
# the version the recipe was validated against.
# Ref: https://recipes.vllm.ai/openbmb/MiniCPM-V-4.6
VLLM_VERSION = "vllm==0.22.0"
TRANSFORMERS_VERSION = "transformers>=5.7.0"
# TRANSFORMERS_VERSION = "transformers==5.5.0"

# --- Image -----------------------------------------------------------------
vllm_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        VLLM_VERSION,
        TRANSFORMERS_VERSION,
        "huggingface_hub[hf_transfer]",
    )
    .env(
        {
            "HF_HUB_ENABLE_HF_TRANSFER": "1",  # fast HF downloads
            # FlashInfer JIT-compiles CUDA kernels at startup and needs `nvcc`,
            # which this slim image does NOT ship — and the T4 (Turing/SM75) is
            # below FlashInfer/FlashAttention-2's SM80+ target anyway. Disable the
            # FlashInfer sampler and use the Turing-safe xFormers attention backend
            # so the engine starts without a CUDA toolkit.
            "VLLM_USE_FLASHINFER_SAMPLER": "0",
            "VLLM_ATTENTION_BACKEND": "XFORMERS",

            "HF_XET_HIGH_PERFORMANCE": "1",  # faster model transfers
            "VLLM_LOG_STATS_INTERVAL": "1",  # more frequent metrics logging
        }
    )
)

# Persist weights + vLLM compile cache across cold starts so only the first
# ever boot pays the download cost.
hf_cache = modal.Volume.from_name("goblin-hf-cache", create_if_missing=True)
vllm_cache = modal.Volume.from_name("goblin-vllm-cache", create_if_missing=True)

app = modal.App("goblin-vision-gpu")
snapshot_key = "v1"  # change this to invalidate the snapshot cache


@app.function(
    image=vllm_image,
    gpu=f"{GPU_TYPE}:{N_GPU}",
    scaledown_window=5 * MINUTES,   # scale to zero after 5 min idle  (requirement)
    timeout=10 * MINUTES,           # allow a slow first container start
    volumes={
        "/root/.cache/huggingface": hf_cache,
        "/root/.cache/vllm": vllm_cache,
    },
    secrets=[
        # HF_TOKEN — already deployed on Modal (public repo, faster pulls).
        modal.Secret.from_name("huggingface-secret"),
        # RG_VISION_API_KEY — endpoint auth. Create with:
        #   modal secret create rg-vision RG_VISION_API_KEY=...
        modal.Secret.from_name("rg-vision"),
    ],
    experimental_options={"enable_gpu_snapshot": True}
)

@modal.concurrent(max_inputs=10)    # <=10 concurrent requests per replica  (requirement)
@modal.web_server(port=VLLM_PORT, startup_timeout=10 * MINUTES)
def serve():
    print(f"snapshotting {snapshot_key}")
    """Launch vLLM's OpenAI-compatible server inside the container."""
    cmd = [
        "vllm",
        "serve",
        MODEL_ID,
        "--revision",
        MODEL_REVISION,
        "--served-model-name",
        MODEL_ID,
        "--trust-remote-code",         # MiniCPM-V requires custom modeling code
        "--dtype",
        "float16",                     # T4 has no fast bf16 path
        "--max-model-len",
        str(MAX_MODEL_LEN),
        "--gpu-memory-utilization",
        "0.90",
        "--limit-mm-per-prompt",
        '{"image": 1}',                # one canvas image per cast (JSON in vLLM 0.11)
        "--enforce-eager",             # safer/leaner startup for a small MM model on T4
        "--host",
        "0.0.0.0",
        "--port",
        str(VLLM_PORT),
    ]

    # Require Bearer auth on the public endpoint so randoms can't burn credits.
    api_key = os.environ.get("RG_VISION_API_KEY")
    if api_key:
        cmd += ["--api-key", api_key]
    else:
        print("[modal_vision] WARNING: RG_VISION_API_KEY unset — endpoint is OPEN")

    print("[modal_vision] launching:", " ".join(cmd))
    subprocess.Popen(cmd)
