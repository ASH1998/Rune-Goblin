"""Serve the Rune Goblin vision model on Modal via **llama.cpp** (GGUF + mmproj).

A faster-cold-boot alternative to ``modal_vision.py`` (vLLM). The vLLM path
loads ~2.6B safetensors with torch on every cold start and takes **~4 minutes**
to become ready — unacceptable for an interactive game. This script instead
serves the already-quantized GGUF with **llama-cpp-python's built-in OpenAI
server** (CUDA build) and uses Modal's **GPU memory snapshot** so a
scaled-from-zero container restores in seconds.

We use llama-cpp-python (the ``Llama`` + ``MTMDChatHandler`` path), NOT the
standalone ``llama-server`` C++ binary: the binary mis-reads MiniCPM-V-4.6's
Qwen3.5 layer count when combined with ``--mmproj`` ("missing tensor
'blk.24.attn_norm.weight'"), whereas llama-cpp-python's MTMD path is the exact
code that loads this GGUF correctly in the local game backend.

Why this is fast:
  * No torch — the tiny GGUF (Q8_0 811 MB) + mmproj (f16 1.1 GB) are pulled
    from the Hub (``ASHu2/goblinV1/gguf/``) once into a Modal Volume cache, so
    only the first ever boot pays the download; later boots read from disk.
  * The server (CUDA build) load + warmup happens **once**, inside
    ``@modal.enter(snap=True)``, and is captured in the snapshot.
  * On every subsequent cold start Modal restores the snapshot (model already
    in VRAM) instead of re-loading — target boot ~seconds, not minutes.
  Ref: https://modal.com/docs/guide/memory-snapshots  (GPU snapshot is alpha)

Endpoint contract is IDENTICAL to the vLLM deploy, so the game needs no code
change — only a new ``RG_VISION_API_URL``. The server speaks the same OpenAI
dialect ``RemoteVisionSpellModel`` already sends: ``POST /v1/chat/completions``
with a system prompt, an ``image_url`` data-URI, and ``response_format={"type":
"json_object"}`` (turned into a JSON grammar). The ``stop_token_ids`` the client
also sends are harmless extras — the GGUF's own EOS tokens stop generation.

Behavior:
  * GPU: A10G (24 GB; the 2.6B model + mmproj use <4 GB, lots of headroom)
  * scaledown_window = 5 min            -> scales to zero after 5 min idle
  * @modal.concurrent(max_inputs=10)    -> <=10 in-flight requests per replica
                                           (the server serializes generations)
  * Endpoint auth via ``RG_VISION_API_KEY`` (Modal secret ``rg-vision``)

----------------------------------------------------------------------------
ONE-TIME SETUP (run once, locally):

  # 1. Authenticate the Modal CLI (token id/secret are in .env)
  modal token set --token-id "$MODAL_TOKEN_ID" --token-secret "$MODAL_SECRET"

  # 2. The endpoint API-key secret already exists from the vLLM deploy
  #    (`rg-vision`). If not, create one (REQUIRED — the server refuses to
  #    start without it):
  #    modal secret create rg-vision RG_VISION_API_KEY="$(openssl rand -hex 32)"
  #    The HF token secret `huggingface-secret` (HF_TOKEN) is also already
  #    deployed and used for fast Hub pulls.

  # 3. Deploy (first deploy compiles llama.cpp w/ CUDA — a few minutes, cached
  #    in the image afterwards; the GGUF + mmproj are pulled from the Hub on the
  #    first container boot into the `goblin-gguf-cache` Volume):
  modal deploy deploy/modal_vision_gguf.py

Modal prints a URL like:
  https://<workspace>--goblin-vision-gguf-goblinvisiongguf-serve.modal.run
The game's RG_VISION_API_URL is that URL + "/v1/chat/completions".

Smoke test (health + model list):
  curl -s https://<workspace>--...modal.run/health
  curl -s https://<workspace>--...modal.run/v1/models \
    -H "Authorization: Bearer $RG_VISION_API_KEY"
----------------------------------------------------------------------------
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request

import modal

# --- Config ----------------------------------------------------------------
APP_NAME = "goblin-vision-gguf"
GPU_TYPE = "A10G"               # Modal's A10 (24 GB, Ampere SM86). Start here.
N_GPU = 1
PORT = 8080
MINUTES = 60                    # seconds

# Weights live on the Hugging Face Hub under ASHu2/goblinV1/gguf/. We download
# them on first boot into a Modal Volume (cached, so later boots skip it) and
# point the server at the local copies.
HF_REPO_ID = "ASHu2/goblinV1"
MODEL_FILE = "gguf/rune-goblin-v46-Q8_0.gguf"          # requested Q8_0 build
MMPROJ_FILE = "gguf/rune-goblin-v46-mmproj-f16.gguf"    # multimodal projector (vision)

# Local download dir, backed by the Volume below. hf_hub_download(local_dir=...)
# writes to "<dir>/<filename>", preserving the gguf/ subpath.
MODEL_DIR = "/models"
MODEL_PATH = f"{MODEL_DIR}/{MODEL_FILE}"
MMPROJ_PATH = f"{MODEL_DIR}/{MMPROJ_FILE}"

# Model name reported by the server; the game sends RG_VISION_API_MODEL
# (default "ASHu2/goblinV1"). Matching the alias keeps /v1/models tidy.
SERVED_MODEL_NAME = "ASHu2/goblinV1"

# Context window — mirror the known-good local GGUF backend (n_ctx 4096).
CTX_SIZE = 4096

# Serve with the SAME library that loads this GGUF locally: llama-cpp-python's
# built-in OpenAI server (Llama + MTMDChatHandler), pinned to the installed
# version. The standalone llama-server C++ binary mis-reads MiniCPM-V-4.6's
# Qwen3.5 layer count when combined with --mmproj ("missing tensor
# 'blk.24.attn_norm.weight'"); llama-cpp-python's MTMD path loads it correctly.
LLAMA_CPP_PYTHON_VERSION = "0.3.27"

# --- Image -----------------------------------------------------------------
# CUDA *devel* image (full toolkit) so pip can compile llama-cpp-python with
# GPU support. A10G is Ampere -> CUDA arch 86.
cuda_version = "12.4.0"
flavor = "devel"
operating_sys = "ubuntu22.04"
cuda_tag = f"{cuda_version}-{flavor}-{operating_sys}"

llama_image = (
    modal.Image.from_registry(f"nvidia/cuda:{cuda_tag}", add_python="3.12")
    .apt_install("git", "build-essential", "cmake")
    # The CUDA *driver* lib (libcuda.so.1) isn't in the build image — only the
    # host provides it at runtime. The toolkit ships a stub (libcuda.so); expose
    # it as libcuda.so.1 so the CUDA build links (cuMem*/cuDevice*). The real
    # driver is used at runtime on the GPU.
    .run_commands(
        "ln -sf /usr/local/cuda/lib64/stubs/libcuda.so /usr/local/cuda/lib64/stubs/libcuda.so.1"
    )
    # Build llama-cpp-python from source with CUDA (PyPI ships CPU-only wheels,
    # so --no-binary forces the source build). [server] pulls fastapi/uvicorn/
    # sse-starlette etc. Point the linker at the driver stub during the build.
    .run_commands(
        # The base image sets CC=clang (not installed); force gcc/g++ from
        # build-essential as the host compiler for the CUDA build.
        "CC=gcc CXX=g++ "
        "CMAKE_ARGS='-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=86' "
        "LIBRARY_PATH=/usr/local/cuda/lib64/stubs "
        "LD_LIBRARY_PATH=/usr/local/cuda/lib64/stubs "
        "pip install --no-binary llama-cpp-python "
        f"'llama-cpp-python[server]=={LLAMA_CPP_PYTHON_VERSION}'"
    )
    # huggingface_hub pulls weights at boot; pillow builds the warmup image.
    .pip_install("huggingface_hub[hf_transfer]", "pillow")
    .env(
        {
            "HF_HUB_ENABLE_HF_TRANSFER": "1",   # fast HF downloads
            "HF_XET_HIGH_PERFORMANCE": "1",     # faster Xet-backed transfers
        }
    )
    .entrypoint([])
)

# Persistent cache for the downloaded weights so only the first ever boot pays
# the HF download cost; later cold starts read straight from the Volume.
models_volume = modal.Volume.from_name("goblin-gguf-cache", create_if_missing=True)

app = modal.App(APP_NAME)

def _warmup_image_data_uri() -> str:
    """A real 448x448 white RGB PNG (Pillow) as a data-URI — same encoding the
    game sends. A degenerate 1x1 PNG fails llama.cpp's image decoder, so build a
    proper one to warm the multimodal (mtmd) + CUDA path into the snapshot."""
    import base64
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (448, 448), "white").save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _wait_until_up(api_key: str, timeout_s: int) -> None:
    """Block until the server answers GET /v1/models (HTTP listening), or raise.

    The llama-cpp-python server has no /health route, and /v1/models lists the
    model without forcing a load — so this only confirms the HTTP server is up.
    Actual weight loading into VRAM is forced by the warmup cast below."""
    deadline = time.monotonic() + timeout_s
    last_err: Exception | None = None
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:  # noqa: BLE001 — server not up yet; keep polling
            last_err = exc
        time.sleep(1)
    raise RuntimeError(f"server did not come up in {timeout_s}s: {last_err}")


def _warmup(api_key: str) -> None:
    """Send one tiny multimodal cast to force the GGUF + mmproj to load into
    VRAM (and warm the CUDA/mtmd path) so the loaded state is captured in the
    snapshot. Raises on failure — a snapshot without the model loaded would
    defeat the purpose."""
    body = json.dumps(
        {
            "model": SERVED_MODEL_NAME,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": _warmup_image_data_uri()}},
                        {"type": "text", "text": "Reply with the single word: ready"},
                    ],
                }
            ],
            "max_tokens": 8,
            "temperature": 0.0,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/v1/chat/completions",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        resp.read()
    print("[modal_vision_gguf] warmup cast OK — model loaded")


def _require_api_key() -> str:
    """Return RG_VISION_API_KEY, or raise if missing/empty.

    Checked BEFORE anything else so we never launch the server (and never
    expose an unauthenticated public endpoint that could burn Modal credits)
    when the key isn't configured."""
    api_key = os.environ.get("RG_VISION_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "RG_VISION_API_KEY is unset/empty — refusing to start the server. "
            "Create it: modal secret create rg-vision RG_VISION_API_KEY=\"$(openssl rand -hex 32)\""
        )
    return api_key


def _download_weights() -> None:
    """Pull the GGUF + mmproj from the Hub into the Volume-backed cache (skips
    files already present), then persist them so later cold starts reuse them."""
    from huggingface_hub import hf_hub_download

    for fname in (MODEL_FILE, MMPROJ_FILE):
        print(f"[modal_vision_gguf] ensuring {HF_REPO_ID}/{fname}")
        hf_hub_download(repo_id=HF_REPO_ID, filename=fname, local_dir=MODEL_DIR)
    models_volume.commit()
    print("[modal_vision_gguf] weights ready")


@app.cls(
    image=llama_image,
    gpu=f"{GPU_TYPE}:{N_GPU}",
    scaledown_window=5 * MINUTES,    # scale to zero after 5 min idle  (requirement)
    timeout=15 * MINUTES,            # allow a slow first (pre-snapshot) boot
    volumes={MODEL_DIR: models_volume},
    secrets=[
        # RG_VISION_API_KEY — endpoint auth (shared with the vLLM deploy).
        modal.Secret.from_name("rg-vision"),
        # HF_TOKEN — fast/authenticated Hub pulls (repo is public; token helps).
        modal.Secret.from_name("huggingface-secret"),
    ],
    enable_memory_snapshot=True,                       # CPU snapshot
    experimental_options={"enable_gpu_snapshot": True},  # + GPU VRAM snapshot
    min_containers=0,
)
@modal.concurrent(max_inputs=10)    # <=10 concurrent requests per replica  (requirement)
class GoblinVisionGGUF:
    """llama-cpp-python OpenAI server (Llama + MTMDChatHandler) serving the GGUF
    vision model, snapshotted after warmup for fast cold starts."""

    def _launch(self, api_key: str) -> "subprocess.Popen":
        # api_key is always required (validated by the callers); pass it so the
        # endpoint is never exposed unauthenticated. `--chat_format mtmd` +
        # `--clip_model_path` selects MTMDChatHandler — the exact path that loads
        # this MiniCPM-V-4.6 GGUF locally.
        cmd = [
            "python", "-m", "llama_cpp.server",
            "--model", MODEL_PATH,
            "--clip_model_path", MMPROJ_PATH,   # mmproj — enables image input
            "--chat_format", "mtmd",
            "--model_alias", SERVED_MODEL_NAME,
            "--n_gpu_layers", "-1",             # offload all layers to the GPU
            "--n_ctx", str(CTX_SIZE),
            # The HF GGUF was converted with block_count=25 / nextn_predict_layers=1,
            # i.e. it bundles an extra NextN (multi-token-prediction) layer used only
            # for speculative decoding. This llama.cpp can't load that layer and fails
            # with "missing tensor 'blk.24.attn_norm.weight'". Override the metadata
            # to the real 24-layer model (matching the known-good local GGUF); the
            # unused NextN tensors are simply ignored.
            "--kv_overrides",
            "qwen35.block_count=int:24",
            "qwen35.nextn_predict_layers=int:0",
            "--host", "0.0.0.0",
            "--port", str(PORT),
            "--api_key", api_key,
        ]
        print("[modal_vision_gguf] launching:", " ".join(cmd[:-2]), "--api_key ***")
        return subprocess.Popen(cmd)

    @modal.enter(snap=True)
    def start_server(self):
        """Pre-snapshot: validate the API key FIRST, then download weights, start
        the server, and force the model into VRAM via a warmup cast. This whole
        loaded state (incl. VRAM) is captured in the GPU snapshot, so later cold
        starts restore it instead of re-loading. If the key is missing we raise
        here and never launch."""
        api_key = _require_api_key()     # checked first — no key, no server
        _download_weights()
        self.process = self._launch(api_key)
        _wait_until_up(api_key, timeout_s=5 * MINUTES)
        _warmup(api_key)
        print("[modal_vision_gguf] server ready — snapshotting")

    @modal.web_server(port=PORT, startup_timeout=15 * MINUTES)
    def serve(self):
        """Expose the server's port. The process is already running — started in
        ``start_server`` and captured by the snapshot, so on a restored cold
        start it comes back with the model already in VRAM. Confirm it's up and
        only relaunch in the rare case the snapshot didn't preserve it."""
        api_key = _require_api_key()
        try:
            _wait_until_up(api_key, timeout_s=30)
            print("[modal_vision_gguf] server up — routing requests")
        except RuntimeError as exc:
            print(f"[modal_vision_gguf] server not up ({exc}); launching")
            self.process = self._launch(api_key)
            _wait_until_up(api_key, timeout_s=5 * MINUTES)
            _warmup(api_key)
