"""Smoke-test the deployed Modal **GGUF / llama.cpp** vision endpoint.

Same contract as ``test_modal_vision.py`` (the vLLM deploy) — system prompt +
canvas image as an ``image_url`` data-URI + ``response_format=json_object`` —
but points at the ``goblin-vision-gguf`` app (``llama-server`` serving
``rune-goblin-v46-Q8_0.gguf`` + mmproj on an A10G with GPU snapshotting).

Liveness is probed via ``GET /v1/models`` (the llama-cpp-python server has no
``/health`` route); its duration on a cold container ~= the cold-boot time.

Reads the endpoint URL + key from .env / environment, in this order:
  * MODAL_GGUF_APP_URL          (base URL, no trailing path)
  * RG_VISION_API_URL           (full .../v1/chat/completions — base is derived)
  * the deployed default below
plus RG_VISION_API_KEY.

Usage:
  uv run python tests/test_modal_vision_gguf.py
  # or against an ad-hoc image:
  uv run python tests/test_modal_vision_gguf.py path/to/spell.png
"""

from __future__ import annotations

import base64
import json
import math
import sys
import time
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402
import os  # noqa: E402

from rune_goblin.engine import GameState  # noqa: E402
from rune_goblin.vision_inference import (  # noqa: E402
    VISION_SYSTEM_PROMPT,
    format_vision_user_message,
)
from rune_goblin.schema import try_parse_vision_spell  # noqa: E402

load_dotenv(ROOT / ".env")

# Deployed goblin-vision-gguf URL (override via env above).
DEFAULT_BASE = "https://ashutosh-36597--goblin-vision-gguf-goblinvisiongguf-serve.modal.run"


def _resolve_base() -> str:
    base = os.environ.get("MODAL_GGUF_APP_URL", "").strip()
    if base:
        return base.rstrip("/")
    full = os.environ.get("RG_VISION_API_URL", "").strip()
    if full:
        # Derive the base from the game's full chat-completions URL.
        return full.rstrip("/").removesuffix("/v1/chat/completions").rstrip("/")
    return DEFAULT_BASE


BASE = _resolve_base()
API_KEY = os.environ.get("RG_VISION_API_KEY", "")
MODEL = os.environ.get("RG_VISION_API_MODEL", "ASHu2/goblinV1")
# Recipe: stop runaway generations on MiniCPM-V-4.6. llama-server ignores
# unknown fields, so this is a harmless no-op here (the GGUF's EOS tokens stop
# generation), kept for parity with what the game actually sends.
STOP_TOKEN_IDS = [248044, 248046]


def _fail(msg: str) -> None:
    print(f"\033[31mFAIL\033[0m {msg}")
    sys.exit(1)


def doodle() -> "object":
    """Crude spiral on parchment, same as the local repro."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (320, 320), "#efe1bd")
    d = ImageDraw.Draw(img)
    pts = [
        (160 + math.cos(a / 4) * (5 + a * 1.4), 160 + math.sin(a / 4) * (5 + a * 1.4))
        for a in range(80)
    ]
    d.line(pts, fill="#17120b", width=6)
    return img


def image_data_uri(arg: str | None) -> str:
    from PIL import Image

    img = Image.open(arg) if arg else doodle()
    buf = BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _request(path: str, payload: dict | None = None) -> tuple[int, dict]:
    url = f"{BASE}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method="POST" if data else "GET",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, {"raw": raw}
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        return e.code, {"error": body}
    except urllib.error.URLError as e:
        _fail(f"could not reach {url}: {e.reason}")
        raise  # unreachable


def main() -> None:
    if not BASE:
        _fail("no endpoint URL (set MODAL_GGUF_APP_URL or RG_VISION_API_URL in .env)")
    if not API_KEY:
        _fail("RG_VISION_API_KEY not set (.env)")

    print(f"endpoint : {BASE}")
    print(f"model    : {MODEL}\n")

    # 1) liveness + cold-boot timing — GET /v1/models (the llama-cpp-python
    #    server has no /health route). The first hit may cold-boot / restore the
    #    snapshot; allow time for it. The duration here ~= your cold-boot time.
    print("[1/2] GET /v1/models (may cold-boot / restore the snapshot) ...")
    t0 = time.monotonic()
    status, body = _request("/v1/models")
    if status != 200:
        _fail(f"/v1/models -> HTTP {status}: {body.get('error', body)}")
    ids = [m.get("id") for m in body.get("data", [])]
    print(f"      ok ({status}) in {time.monotonic() - t0:.1f}s -> {ids}\n")

    # 2) a real cast — system + image data-URI + json_object, like the game.
    state = GameState(
        player_hp=12,
        player_max_hp=12,
        enemy_name="Mirror Fungus",
        enemy_hp=5,
        enemy_max_hp=5,
        room_mood="damp",
        inventory=("wet candle",),
        courage=5,
    )
    user_text = format_vision_user_message(state, room_name="Goblin Toll Road")
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": VISION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_data_uri(
                        sys.argv[1] if len(sys.argv) > 1 else None)}},
                    {"type": "text", "text": user_text},
                ],
            },
        ],
        "response_format": {"type": "json_object"},
        "stop_token_ids": STOP_TOKEN_IDS,
        "max_tokens": 512,
        "temperature": 0.2,
    }

    print("[2/2] POST /v1/chat/completions (casting on a doodle) ...")
    t0 = time.monotonic()
    status, body = _request("/v1/chat/completions", payload)
    dt = time.monotonic() - t0
    if status != 200:
        _fail(f"/v1/chat/completions -> HTTP {status}: {body.get('error', body)}")

    raw = body["choices"][0]["message"]["content"]
    usage = body.get("usage", {})
    print(f"      ok ({status}) in {dt:.1f}s  "
          f"[prompt={usage.get('prompt_tokens')} completion={usage.get('completion_tokens')}]\n")
    print("--- raw model output ---")
    print(raw)
    print("------------------------\n")

    result = try_parse_vision_spell(raw)
    if result is None:
        _fail("model output did not parse into a VisionSpellResult")
    print("\033[32mPASS\033[0m parsed VisionSpellResult:")
    print("  detected_runes :", result.visual_reading.detected_runes)
    print("  notes          :", result.visual_reading.notes)
    print("  spell          :", result.spell.spell_name, "|", result.spell.effect)


if __name__ == "__main__":
    main()
