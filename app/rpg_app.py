"""Rune Goblin RPG — a free-roaming canvas dungeon, hosted by Gradio.

The world is an HTML5 canvas game (``app/rpg_static/rpg.js``): movement,
rendering and exploration run client-side for smooth roaming. Spell casting is
the only thing that round-trips to Python — rune casts hit the deterministic
engine, drawings are read by the fine-tuned ``goblinV1`` vision model — via the
FastAPI routes mounted alongside the Gradio app.

The game page is served standalone at ``/play`` and embedded in the Gradio
Blocks via an iframe. (Gradio drops ``head=`` under ``mount_gradio_app`` and
``gr.HTML`` won't execute inline scripts, so the iframe is the robust way to run
a real canvas game while still shipping as one Gradio app / HF Space.)

Run::

    uv run --extra gguf python app/rpg_app.py      # → http://localhost:7862
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import gradio as gr  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from app.rpg_bridge import register_routes  # noqa: E402

STATIC_DIR = APP_DIR / "rpg_static"
PORT = int(os.environ.get("GRADIO_SERVER_PORT", "7862"))

PLAY_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Rune Goblin RPG</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/rg/static/rpg.css?v=42">
</head>
<body>
  <div id="rg-root">
    <div id="rg-stage">
      <div id="rg-boot" class="rg-boot">Summoning the dungeon…</div>
      <canvas id="rg-canvas" tabindex="0"></canvas>

      <div class="rg-select" id="rg-select">
        <h1>RUNE GOBLIN</h1>
        <p class="rg-select-sub">The Calendar Bell rang thirteen times. Tomorrow is being eaten.<br>Choose the goblin who broke tomorrow.</p>
        <div class="rg-heroes" id="rg-heroes"></div>
        <button class="rg-btn primary" id="rg-select-start" disabled>Start shift</button>
      </div>

      <div class="rg-dialogue" id="rg-dialogue">
        <div class="rg-dialogue-portrait" id="rg-dialogue-portrait">🗣️</div>
        <div class="rg-dialogue-body">
          <div class="rg-dialogue-name" id="rg-dialogue-name">NPC</div>
          <div class="rg-dialogue-text" id="rg-dialogue-text">…</div>
          <div class="rg-dialogue-tip">Space/Esc to close · cast a rune at them to react</div>
        </div>
      </div>

      <div class="rg-journal" id="rg-journal">
        <h3>📓 Journal <span class="rg-journal-close" id="rg-journal-close">✕ (J)</span></h3>
        <div id="rg-journal-body"></div>
      </div>

      <div class="rg-journal rg-inventory" id="rg-inventory">
        <h3>🎒 Inventory <span class="rg-journal-close" id="rg-inventory-close">✕ (I)</span></h3>
        <div id="rg-inventory-body"></div>
      </div>

      <div class="rg-banner" id="rg-banner"></div>

      <div class="rg-draw" id="rg-draw">
        <h3>Draw your spell</h3>
        <canvas id="rg-sketch" width="340" height="340"></canvas>
        <div class="row">
          <button class="rg-btn primary" id="rg-draw-cast">🔮 Cast Drawing</button>
          <button class="rg-btn" id="rg-draw-clear">Clear</button>
          <button class="rg-btn ghost" id="rg-draw-cancel">Cancel (Esc)</button>
        </div>
        <div class="tip">Sketch 1–4 RuneLang glyphs. The fine-tuned goblinV1 model reads your doodle (~slow on CPU).</div>
      </div>

      <div class="rg-end" id="rg-end">
        <h2 id="rg-end-title"></h2>
        <div id="rg-end-sub"></div>
        <button class="rg-btn primary" id="rg-end-restart">Descend again</button>
      </div>
    </div>

    <div id="rg-ui">
      <div class="rg-palette" id="rg-palette"></div>
      <div class="rg-actions">
        <span class="rg-sel" id="rg-sel">no runes</span>
        <button class="rg-btn primary" id="rg-cast">⚡ Cast (Space)</button>
        <button class="rg-btn" id="rg-draw-open">✍ Draw (E)</button>
        <button class="rg-btn" id="rg-talk">💬 Talk (T)</button>
        <button class="rg-btn" id="rg-inventory-open">🎒 Bag (I)</button>
        <button class="rg-btn" id="rg-journal-open">📓 Journal (J)</button>
        <button class="rg-btn ghost" id="rg-clear">Clear (C)</button>
        <button class="rg-btn ghost" id="rg-reset">New Game</button>
        <button class="rg-btn ghost" id="rg-mute" title="music">🔊</button>
        <button class="rg-btn ghost" id="rg-full" title="fullscreen">⛶</button>
        <select class="rg-btn rg-admin-goto" id="rg-admin-goto" title="admin: warp to map" style="display:none"></select>
        <span class="rg-target" id="rg-target"></span>
      </div>
      <div class="rg-toast" id="rg-toast">Use WASD / arrows to roam. Face something and cast a spell.</div>
      <div class="rg-hint">WASD / Arrows move · 1–9 pick runes · Space cast · E draw · C clear · M minimap · step into portals to travel</div>
    </div>
  </div>
  <script src="/rg/static/rpg.js?v=42"></script>
</body>
</html>
"""

# The Gradio shell frames the standalone game page full-bleed.
SHELL_HTML = """
<style>
  html, body { margin: 0; padding: 0; overflow: hidden !important; height: 100%; }
  .gradio-container { max-width: none !important; padding: 0 !important; margin: 0 !important; overflow: hidden !important; }
  .gradio-container > .main, .gradio-container .wrap, .gradio-container .contain {
    padding: 0 !important;
    margin: 0 !important;
    overflow: hidden !important;
    min-height: 100vh !important;
  }
  footer { display: none !important; }
  #rg-shell { position: fixed; inset: 0; overflow: hidden; background: #000; }
  #rg-frame { position: absolute; inset: 0; width: 100vw; height: 100dvh; border: 0; display: block; }
</style>
<div id="rg-shell">
  <iframe id="rg-frame" src="/play" title="Rune Goblin RPG" allow="fullscreen"></iframe>
</div>
"""

fastapi_app = FastAPI(title="Rune Goblin RPG")
register_routes(fastapi_app)
fastapi_app.mount("/rg/static", StaticFiles(directory=str(STATIC_DIR)), name="rg-static")


@fastapi_app.get("/play", response_class=HTMLResponse)
def play_page() -> str:
    return PLAY_PAGE


def build() -> gr.Blocks:
    with gr.Blocks(title="Rune Goblin RPG") as demo:
        gr.HTML(SHELL_HTML)
    return demo


demo = build()
app = gr.mount_gradio_app(fastapi_app, demo, path="/")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
