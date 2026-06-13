# Deploying the Vision Model on Modal + Hosting the Game on Hugging Face

**Status:** plan / not yet implemented
**Owner:** ashutosh
**Goal:** stop paying for the always-on private GPU instance. Serve the `goblinV1`
vision model from a serverless Modal GPU (T4), point the game at that endpoint,
and host the game itself on a free CPU-only Hugging Face Space.

---

## 1. Where we are today

Two models power the game:

| Model | What it does | How it runs today | Cost |
|-------|--------------|-------------------|------|
| **Vision** `goblinV1` (fine-tune of `openbmb/MiniCPM-V-4.6`, ~2.6B) | reads the hand-drawn RuneLang canvas → `visual_reading` + `spell` JSON | local **GGUF via llama.cpp** in [`start.sh`](../start.sh) (needs the dev's GPU/CPU) | the dev's own machine |
| **Dialogue** `MiniCPM-V-4.6` | NPC lines, beats, shop prices, taunts | remote **vLLM** at `http://35.203.155.71:8003` (private instance) | **paid, always-on** |

Relevant code:

- Vision entry point: [`src/rune_goblin/vision_inference.py`](../src/rune_goblin/vision_inference.py)
  — `cast_vision_spell()` is the single call site used by
  [`game.py`](../src/rune_goblin/game.py) and [`rpg_bridge.py`](../app/rpg_bridge.py).
  It already has two backends: `VisionSpellModel` (HF transformers) and
  `GGUFVisionSpellModel` (llama.cpp). The GGUF backend builds an
  OpenAI-style `image_url` data-URI message and asks for `response_format=json_object`.
- Dialogue already proves the **remote-API pattern** we want to copy:
  [`dialogue.py`](../src/rune_goblin/dialogue.py) `_remote_chat()` +
  `RG_USE_DIALOGUE_API` / `RG_DIALOGUE_API_URL` / `RG_DIALOGUE_API_KEY` /
  `RG_DIALOGUE_API_MODEL`.

**End state we want:** game runs on a free HF Space (CPU only). Both models are
remote HTTP endpoints. Vision → Modal (we have credits). Dialogue → Modal too
(phase 4), so the private paid instance can be shut down.

---

## 2. Target architecture

```
┌────────────────────────────┐        HTTPS (OpenAI-compatible /v1/chat/completions)
│  HF Space (CPU, free)      │ ─────────────────────────────────────────────┐
│  - FastAPI api/server.py   │                                               │
│    or Gradio app           │   image+state  ┌──────────────────────────┐   │
│  - rune_goblin engine      │ ──────────────▶│ Modal: goblin-vision      │   │
│  - NO local model weights  │                │  T4 GPU, vLLM, scale→0    │   │
│                            │                │  scaledown 5 min, conc 10 │   │
│                            │   dialogue      └──────────────────────────┘   │
│                            │ ──────────────▶┌──────────────────────────┐    │
└────────────────────────────┘                │ Modal: goblin-dialogue   │◀──┘
                                               │  (phase 4 — replaces the  │
                                               │   private 35.x instance)  │
                                               └──────────────────────────┘
```

Both Modal apps are **serverless**: they scale to zero after 5 minutes of no
requests and only bill while a container is warm.

---

## 3. Key decision: vLLM vs llama.cpp on Modal

This is the one real fork in the road. Decide before writing the deploy script.

### Option A — vLLM serving the HF safetensors `ASHu2/goblinV1` (CONFIRMED working path)
- **Pros:** matches the linked Modal example, OpenAI-compatible out of the box,
  supports [memory snapshots](https://modal.com/docs/guide/memory-snapshots) for
  fast cold starts, robust guided-JSON (`guided_json`/`response_format`), serves
  the original bf16 weights (no quant quality loss on an already-small model).
- **Version requirement (resolved):** the `MiniCPMV4_6ForConditionalGeneration`
  arch landed in **vLLM ≥ 0.22.0** (PR #43213) and needs **transformers ≥ 5.7.0**.
  vLLM 0.11 fails with *"Model architectures [...] are not supported"*. Pin
  accordingly in [`deploy/modal_vision.py`](../deploy/modal_vision.py).
  Ref: https://recipes.vllm.ai/openbmb/MiniCPM-V-4.6
- **Cons:** needs `--trust-remote-code`; slightly heavier image / longer first build.
- **Recipe flags:** `--trust-remote-code`, `--max-model-len 8192` (model supports
  up to 256K), and **clients should send `"stop_token_ids": [248044, 248046]`** to
  avoid runaway generations. Tool-calling flags are optional and we don't need them
  (we use `response_format=json_object`, not tools).

### Option B — llama.cpp `llama-server` serving the GGUF + mmproj (de-risk fallback)
- **Pros:** the **exact model + format already proven working** locally
  ([`GGUFVisionSpellModel`](../src/rune_goblin/vision_inference.py)). Tiny
  (Q4 529 MB + mmproj 1.1 GB ≈ 1.6 GB), very fast cold start, and `llama-server`
  speaks the same `/v1/chat/completions` + `image_url` dialect the client already
  sends. Lowest risk of "model won't load".
- **Cons:** lower throughput/batching than vLLM (irrelevant at single-player
  concurrency ≤10), no Modal memory-snapshot story, Q4 quant.

**Recommendation:** attempt **Option A (vLLM)** first because it's the documented
Modal path and the client already speaks OpenAI. **If vLLM chokes on the
`MiniCPMV4_6` multimodal arch, fall back to Option B** — the GGUF is known-good
and the client code is identical either way. Both expose the same endpoint
contract, so the game-side changes in §5 are unchanged regardless.

> **Model access (confirmed):** `ASHu2/goblinV1` is **public**, but we still pass
> `HF_TOKEN` to Modal for fast/authenticated downloads. The token is already
> deployed as a Modal secret named **`huggingface-secret`** — use
> `secrets=[modal.Secret.from_name("huggingface-secret")]`.

---

## 4. Modal deploy script — config

New file: **`deploy/modal_vision.py`** (new `deploy/` dir).

Hard requirements from the brief:
- **GPU:** `T4` (`gpu="T4"`, $0.000164/sec ≈ $0.59/hr while warm).
- **Scale to zero after 5 min idle:** `scaledown_window=5 * 60`.
- **Concurrency cap 10:** `@modal.concurrent(max_inputs=10)`.

Sketch (vLLM / Option A):

```python
import modal

MODEL_ID = "ASHu2/goblinV1"          # merged safetensors fine-tune
MODEL_REVISION = "main"               # pin a commit SHA before going live
VLLM_PORT = 8000
MINUTES = 60

vllm_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("vllm==<pin>", "huggingface_hub[hf_transfer]")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1", "VLLM_USE_V1": "1"})
)

hf_cache = modal.Volume.from_name("hf-cache", create_if_missing=True)
vllm_cache = modal.Volume.from_name("vllm-cache", create_if_missing=True)

app = modal.App("goblin-vision")

@app.function(
    image=vllm_image,
    gpu="T4",
    scaledown_window=5 * MINUTES,     # shut down after 5 min idle  ← requirement
    timeout=10 * MINUTES,             # allow slow first container start
    volumes={
        "/root/.cache/huggingface": hf_cache,
        "/root/.cache/vllm": vllm_cache,
    },
    secrets=[modal.Secret.from_name("huggingface-secret")],   # HF_TOKEN — already deployed on Modal
)
@modal.concurrent(max_inputs=10)      # ≤10 concurrent requests per replica  ← requirement
@modal.web_server(port=VLLM_PORT, startup_timeout=10 * MINUTES)
def serve():
    import subprocess
    subprocess.Popen(
        [
            "vllm", "serve", MODEL_ID,
            "--revision", MODEL_REVISION,
            "--trust-remote-code",
            "--dtype", "float16",          # T4 has no bf16 fast path
            "--max-model-len", "4096",
            "--port", str(VLLM_PORT),
            "--api-key", "$RG_VISION_API_KEY",   # via Secret; see §6
        ]
    )
```

Notes:
- **Memory snapshots** (optional, big cold-start win): follow
  https://modal.com/docs/guide/memory-snapshots — enable on the function and
  snapshot after weights load so a cold start restores in seconds instead of
  re-downloading/reloading. Add once the basic deploy works; don't block on it.
- For **Option B**, swap the image to one with `llama.cpp` built (or the
  `llama-cpp-python` server), download the GGUF + mmproj into a Volume, and run
  `llama-server --model rune-goblin-v46-Q4_K_M.gguf --mmproj
  rune-goblin-v46-mmproj-f16.gguf --host 0.0.0.0 --port 8000 --api-key ...`.
  Same `web_server(port=8000)` wrapper, same endpoint contract.
- Deploy with `modal deploy deploy/modal_vision.py`; Modal returns a URL like
  `https://<workspace>--goblin-vision-serve.modal.run`. The chat endpoint is
  that URL + `/v1/chat/completions`.

---

## 5. Game-side change: add a remote vision backend

Mirror the dialogue API pattern exactly so the codebase stays consistent.

### 5.1 New env vars (add to `.env` / `.env.example`)
```
RG_USE_VISION_API=1
RG_VISION_API_URL=https://<workspace>--goblin-vision-serve.modal.run/v1/chat/completions
RG_VISION_API_KEY=<the same key set on the Modal --api-key>
RG_VISION_API_MODEL=ASHu2/goblinV1        # or "goblinV1" — must match what vLLM reports
RG_VISION_API_TIMEOUT=60
```

### 5.2 New backend class in [`vision_inference.py`](../src/rune_goblin/vision_inference.py)
Add `RemoteVisionSpellModel` alongside the existing two. It should:
1. Reuse the **same message construction** as `GGUFVisionSpellModel`
   (system prompt `VISION_SYSTEM_PROMPT` + `image_url` data URI via
   `_image_data_uri` + user text from `format_vision_user_message`).
2. POST to `RG_VISION_API_URL` with `Authorization: Bearer <key>`,
   `response_format={"type":"json_object"}`, modest `max_tokens`/`temperature`
   — copy `_remote_chat()` from [`dialogue.py`](../src/rune_goblin/dialogue.py).
3. Parse with the existing `try_parse_vision_spell`, then
   `clamp_spell(result.spell, state)` — identical to the local backends.
4. Never raise: on any network/parse failure, return `FALLBACK_VISION_SPELL`
   (same as the local backends do today) so the game never stalls.

`_image_data_uri` currently lives on `GGUFVisionSpellModel`; lift it to a
module-level helper so both GGUF and remote backends share it.

### 5.3 Wire selection into `get_vision_model()` — local GGUF *or* Modal API (configurable)
The backend must be **switchable by a flag**, exactly like dialogue:

- **No `RG_USE_VISION_API`** (or `=0`) → unchanged behavior. The existing
  precedence in `get_vision_model()` still applies: `RG_VISION_MODEL` ending in
  `.gguf` → `GGUFVisionSpellModel`, else HF transformers. **[`start.sh`](../start.sh)
  keeps working as-is** (it sets `RG_VISION_MODEL`/`RG_VISION_MMPROJ` to local
  GGUF and never sets the API flag).
- **`RG_USE_VISION_API=1`** → build/return `RemoteVisionSpellModel` and skip all
  local-weight loading. This is the path the HF Space and a new `start-modal.sh`
  use. The Space then needs **no GGUF download and no torch/llama-cpp** — big
  image savings.

Implementation: add an early check at the top of `get_vision_model()` —
`if os.environ.get("RG_USE_VISION_API") == "1": return RemoteVisionSpellModel()`.
This flag wins over `RG_VISION_MODEL`, so the same checkout runs local or remote
purely from env, mirroring `RG_USE_DIALOGUE_API`.

Add a convenience launcher `start-modal.sh` (sibling of `start.sh`) that sets
`RG_USE_MODEL=1 RG_USE_VISION_API=1 RG_VISION_API_URL=... RG_VISION_API_KEY=...`
and runs the app with no GGUF paths — the "use the Modal API" counterpart to
`start.sh`'s "use the local model".

### 5.4 Don't forget `/rg/ping` diagnostics
Add a `model_status()`-style report for the vision backend (URL + last error),
matching what dialogue exposes, so the Space can be debugged without logs.

---

## 6. Secrets & config

- **Modal side** (`modal secret create`):
  - `huggingface-secret` → `HF_TOKEN` — **already deployed.** Repo is public, but
    the token gives fast/authenticated downloads.
  - `rg-vision` → `RG_VISION_API_KEY` (a long random string we generate; used as vLLM `--api-key`).
- **Modal CLI auth:** `MODAL_TOKEN_ID` / `MODAL_SECRET` are already in `.env`.
  Either `modal token set --token-id ... --token-secret ...` once, or export them
  in the deploy shell.
- **HF Space side** (Space → Settings → Secrets): set `RG_USE_MODEL=1`,
  `RG_USE_VISION_API=1`, `RG_VISION_API_URL`, `RG_VISION_API_KEY`,
  `RG_VISION_API_MODEL`, plus the existing `RG_USE_DIALOGUE_API` /
  `RG_DIALOGUE_API_*`. **No `HF_TOKEN` needed on the Space** once both models are
  remote (the Space pulls no weights).

The API key is what stops the public Space's endpoint from letting anyone burn
our Modal credits. Keep it out of committed source (env only), same as the
dialogue key today.

---

## 7. Hugging Face Space (existing — `ASHu2/test-goblin-space`)

We already have a **working CPU Docker Space**. Shipping is automated:

- **Image:** the root [`Dockerfile`](../Dockerfile) — `python:3.12-slim`, installs
  only [`requirements.txt`](../requirements.txt) (gradio/fastapi/uvicorn/pydantic/
  dotenv/pillow — **no torch, no llama-cpp**), copies `src` + `app`, and runs
  `uvicorn app.rpg_app:app --port 7860`. Already CPU-only and slim because both
  models are meant to be remote.
- **CI:** [`.github/workflows/deploy-hf-space.yml`](../.github/workflows/deploy-hf-space.yml)
  (manual `workflow_dispatch`). It syncs Space variables/secrets from GitHub
  repo vars/secrets via `huggingface_hub`, then force-pushes the branch to the
  Space's `main`, where HF rebuilds the Dockerfile.

**Changes needed to turn vision on via Modal:**

1. **Dockerfile** — flip the defaults (and update the header comment, which
   currently says vision is OFF):
   - `RG_USE_MODEL=1` (was `0`)
   - add `RG_USE_VISION_API=1`
   - keep `RG_USE_DIALOGUE_API=1`
   - `requirements.txt` needs **no change** — the remote vision backend uses only
     stdlib `urllib` + `pillow` (already present).
2. **CI workflow** — add the vision env passthroughs alongside the dialogue ones,
   same pattern (variables vs secret):
   - variables: `RG_USE_VISION_API`, `RG_VISION_API_URL`, `RG_VISION_API_MODEL`,
     `RG_VISION_API_TIMEOUT`
   - secret: `RG_VISION_API_KEY`
   - flip the `RG_USE_MODEL` default in the sync script from `"0"` to `"1"`.
3. **GitHub repo settings** — add the matching Actions *variables*
   (`RG_VISION_API_URL`, …) and the *secret* `RG_VISION_API_KEY`.

First canvas cast warms the Modal container (a few seconds cold-start);
subsequent casts are fast until the 5-min scaledown.

---

## 8. Phased rollout

1. **Phase 1 — Deploy vision on Modal.** Write `deploy/modal_vision.py` (Option A),
   `modal deploy`, and smoke-test the raw endpoint with `curl` (send a base64
   image + state, confirm valid spell JSON comes back). Fall back to Option B if
   vLLM can't load the arch.
2. **Phase 2 — Point the game at it locally.** Add `RemoteVisionSpellModel` +
   env vars (§5). Run the game locally with `RG_USE_VISION_API=1` and verify
   casts go to Modal and parse/clamp correctly. Confirm fallback still works when
   the endpoint is down.
3. **Phase 3 — Host on HF Space.** Slim build, set secrets, deploy, play through
   a spell + an NPC chat end to end.
4. **Phase 4 (optional, kills the paid instance) — Move dialogue to Modal.**
   Same recipe, second Modal app `goblin-dialogue` serving `MiniCPM-V-4.6`, then
   repoint `RG_DIALOGUE_API_URL` at it and shut down `35.203.155.71`. Dialogue
   already speaks the remote-API contract, so only the URL/key change.

---

## 9. Cost sanity check

- T4 warm: ~$0.59/hr. With `scaledown_window=5min` and bursty single-player
  traffic, the container is idle→stopped most of the time. A play session that
  fires a cast every minute keeps one container warm for the session + 5 min,
  i.e. roughly the session length × $0.59/hr. A 20-minute session ≈ **$0.20**.
- No traffic = **$0** (scaled to zero). Modal credits absorb this easily.
- The expensive thing today (always-on private instance) goes away entirely
  after phase 4.

---

## 10. Resolved / open questions

**Resolved:**
1. `ASHu2/goblinV1` is **public**; still pass `HF_TOKEN` (Modal secret
   `huggingface-secret`, already deployed) for fast downloads.
2. **Shipping is solved** — existing CPU Docker Space `ASHu2/test-goblin-space`,
   `app/rpg_app.py` on 7860, deployed by `deploy-hf-space.yml` (§7).
3. **Backend must be configurable** — `RG_USE_VISION_API=1` → Modal API;
   unset → local GGUF (`start.sh` unchanged). See §5.3.

4. **vLLM supports the arch** — confirmed: vLLM ≥ 0.22.0 + transformers ≥ 5.7.0
   load `MiniCPMV4_6` (Option A). The deploy script is pinned to `vllm>=0.22.0`.

**Still open:**
- Phase 4 (move dialogue to Modal, retire the private instance) in scope now, or
  later?
