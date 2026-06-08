"""Rune Goblin — the full playable game (Gradio).

A tiny cursed dungeon crawler. Two ways to cast:

* **Draw** a RuneLang spell on the canvas and the fine-tuned ``goblinV1`` vision
  model reads your doodle, names the spell, and decides what it does.
* **Tap runes** from the board for an instant rule-engine cast (great when you
  want speed, or while the vision model warms up).

Survive five rooms. Draw bad spells. Suffer beautifully.

Run::

    RG_USE_MODEL=1 \
    RG_VISION_MODEL=models/goblinV1-gguf/gguf/rune-goblin-v46-Q4_K_M.gguf \
    RG_VISION_MMPROJ=models/goblinV1-gguf/gguf/rune-goblin-v46-mmproj-f16.gguf \
    uv run --extra gguf python app/vision_app.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import gradio as gr  # noqa: E402
from PIL import Image  # noqa: E402

from rune_goblin.game import Game  # noqa: E402
from rune_goblin.runelang import COMBOS, GLYPHS  # noqa: E402
from rune_goblin.schema import SpellResult, VisualReading  # noqa: E402
from rune_goblin.vfx import (  # noqa: E402
    enemy_sprite,
    plan_vfx,
    room_backdrop,
)
from rune_goblin.vision_inference import default_vision_model_id  # noqa: E402

USE_MODEL = os.environ.get("RG_USE_MODEL", "1") == "1"
VISION_MODEL = os.environ.get("RG_VISION_MODEL", default_vision_model_id())
CANVAS_BG = "#efe1bd"

HEAD = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap" rel="stylesheet">
"""

CSS = """
.gradio-container {background: radial-gradient(circle at 50% -10%, #241836, #0e0b14) !important;
  color: #e7d9ff; max-width: 1100px !important; margin: 0 auto;}
.rg-pixel {font-family: "Press Start 2P", ui-monospace, monospace;}
#rg-title h1 {font-family:"Press Start 2P", monospace; font-size: 1.6rem; text-align:center;
  color:#b07cff; text-shadow: 0 0 12px #6d3bd1, 3px 3px 0 #160d24; margin:.4rem 0;}
#rg-title p {text-align:center; color:#9c8bc4; margin:.1rem 0 .6rem; letter-spacing:1px;}

/* battle stage */
.rg-stage {position:relative; height:330px; border-radius:14px; overflow:hidden;
  border:2px solid #4a3a6b; box-shadow: inset 0 0 60px rgba(0,0,0,.6);}
.rg-stage::after {content:""; position:absolute; inset:0; pointer-events:none;
  background:repeating-linear-gradient(0deg, rgba(0,0,0,.18) 0 2px, transparent 2px 4px);
  mix-blend-mode:multiply;}
.rg-enemy {position:absolute; top:46%; left:50%; transform:translate(-50%,-50%);
  display:flex; flex-direction:column; align-items:center;}
.rg-sprite {font-size:104px; line-height:1; filter:drop-shadow(0 8px 10px rgba(0,0,0,.55));
  animation: rg-bob 2.4s ease-in-out infinite;}
@keyframes rg-bob {0%,100%{transform:translateY(0)} 50%{transform:translateY(-10px)}}
.rg-reaction {font-size:40px; margin-top:-14px; height:42px;}
.rg-name {position:absolute; left:0; right:0; bottom:14px; text-align:center;
  font-family:"Press Start 2P", monospace; font-size:.62rem; color:#ffe9b0;
  text-shadow:1px 1px 0 #000; padding:0 10px;}
.rg-weak {color:#6df5a0;}
.rg-mood {color:#c9b6f0; font-style:italic; font-family:ui-monospace,monospace; font-size:.7rem;}

/* enemy HP bar */
.rg-hpwrap {position:absolute; top:14px; left:50%; transform:translateX(-50%);
  width:62%; }
.rg-hpbar {position:relative; height:18px; background:#2a1f3d; border:1px solid #000;
  border-radius:9px; overflow:hidden;}
.rg-hpfill {height:100%; background:linear-gradient(90deg,#ff5d73,#ff9b6b);
  transition:width .5s ease;}
.rg-hpbar span {position:absolute; inset:0; display:flex; align-items:center;
  justify-content:center; font-size:.62rem; color:#fff; font-family:"Press Start 2P",monospace;}

/* HUD */
.rg-hud {display:flex; gap:14px; flex-wrap:wrap; align-items:center;
  background:#1a1426; border:1px solid #34254d; border-radius:12px; padding:.7rem 1rem;
  margin-top:.6rem; font-family:ui-monospace,monospace;}
.rg-hud .blk {display:flex; flex-direction:column; gap:2px;}
.rg-hud .lab {font-size:.6rem; color:#9c8bc4; letter-spacing:1px;}
.rg-hud .big {font-family:"Press Start 2P",monospace; font-size:.8rem; color:#e7d9ff;}
.rg-hearts {color:#ff5d73; letter-spacing:2px; font-size:1.05rem;}
.rg-hearts .empty {color:#3a2a44;}
.rg-score {color:#ffd24a;}
.rg-inv {color:#9c8bc4; font-size:.72rem;}

/* rune board */
.rg-board {display:grid; grid-template-columns:repeat(8,1fr); gap:.4rem;}
#rg-selected {text-align:center; min-height:1.5rem; color:#b07cff;
  font-family:"Press Start 2P", monospace; font-size:.75rem; margin:.2rem 0 .4rem;}

/* result panel */
.rg-result {background:#1a1426; border:1px solid #34254d; border-radius:12px;
  padding:1rem; min-height:120px;}
.rg-result h3 {margin:0 0 .3rem; color:#b07cff; font-family:"Press Start 2P",monospace;
  font-size:.85rem; line-height:1.5;}
.rg-flavor {font-style:italic; color:#c9b6f0; margin:.2rem 0;}
.rg-side {color:#ffce6b;}
.rg-tags {color:#9c8bc4; font-size:.74rem; margin-top:.5rem; font-family:ui-monospace,monospace;}
.rg-detected {color:#6df5a0;}
.rg-banner {text-align:center; padding:1.2rem; border-radius:12px;
  font-family:"Press Start 2P",monospace; font-size:1rem; line-height:1.6;}
.rg-banner.win {background:#143a26; color:#6df5a0; box-shadow:0 0 30px #1e6b40;}
.rg-banner.lose {background:#3a1420; color:#ff5d73; box-shadow:0 0 30px #6b1e2e;}

/* guide */
.rg-guide {font-family:ui-monospace,monospace; font-size:.8rem; color:#cdbff0;}
.rg-guide table {width:100%; border-collapse:collapse;}
.rg-guide td {padding:3px 8px; border-bottom:1px solid #2a1f3d; vertical-align:top;}
.rg-guide .sym {font-size:1.2rem; width:34px;}
.rg-guide .nm {color:#e7d9ff; white-space:nowrap;}
.rg-guide .mn {color:#9c8bc4;}

#rg-log textarea {background:#100a1a !important; color:#b7f5c2 !important;
  font-family:ui-monospace,monospace !important; font-size:.78rem !important;}
button.rg-rune {font-size:1.3rem !important; min-width:0 !important; padding:.45rem 0 !important;
  background:#221836 !important; border:1px solid #34254d !important;}
button.rg-rune:hover {border-color:#b07cff !important; transform:translateY(-2px);}
"""


# ---------------------------------------------------------------------------
# Canvas helpers (Sketchpad can return PIL / ndarray / filepath / editor dict)
# ---------------------------------------------------------------------------
def _blank_canvas() -> Image.Image:
    return Image.new("RGB", (512, 512), CANVAS_BG)


def _normalize_canvas(value: Any) -> Image.Image:
    if value is None:
        return _blank_canvas()
    if isinstance(value, dict):
        value = value.get("composite") or value.get("background") or value.get("layers")
        if isinstance(value, list) and value:
            value = value[-1]
    if isinstance(value, Image.Image):
        image = value
    elif isinstance(value, (str, Path)):
        image = Image.open(value)
    else:
        image = Image.fromarray(value)
    if image.mode == "RGBA":
        bg = _blank_canvas().resize(image.size)
        bg.paste(image, mask=image.getchannel("A"))
        image = bg
    return image.convert("RGB")


def _canvas_is_blank(image: Image.Image) -> bool:
    """True if nothing was drawn (canvas still the parchment colour)."""
    extrema = image.convert("L").getextrema()
    return extrema[0] >= 0xDB  # darkest pixel still light => empty


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------
def _hp_bar(hp: int, max_hp: int) -> str:
    pct = max(0, round(100 * hp / max_hp)) if max_hp else 0
    return (
        f"<div class='rg-hpwrap'><div class='rg-hpbar'>"
        f"<div class='rg-hpfill' style='width:{pct}%'></div>"
        f"<span>HP {hp}/{max_hp}</span></div></div>"
    )


def _vfx_layer(vfx: dict) -> str:
    """Per-cast inline-styled animation layer (unique names => replays)."""
    cid = vfx["cast_id"]
    dur = vfx["duration_ms"]
    pal = vfx["palette"]
    glyph = vfx["glyph"]
    flash = vfx["flash"]
    mode = vfx["mode"]
    shake = vfx["shake"]
    amp = int(4 + 18 * shake)

    # particles bursting outward from centre
    parts = []
    n = max(4, min(22, vfx["particle_count"]))
    for i in range(n):
        ang = int(360 * i / n)
        parts.append(
            f"<span class='rg-pt-{cid}' style='--a:{ang}deg;'>{vfx['particle']}</span>"
        )
    particles = "".join(parts)

    # floating number
    if vfx["damage"] > 0:
        num = f"<div class='rg-num-{cid}' style='color:#ff5d73'>-{vfx['damage']}</div>"
    elif vfx["heal"] > 0:
        num = f"<div class='rg-num-{cid}' style='color:#6df5a0'>+{vfx['heal']}</div>"
    elif mode == "shield":
        num = f"<div class='rg-num-{cid}' style='color:#ffd24a'>BLOCK</div>"
    else:
        num = f"<div class='rg-num-{cid}' style='color:#c9b6f0'>…</div>"

    # projectile travels up toward the enemy for attacks; rises on the player
    # side for heals/shields.
    if mode in {"attack", "hex"}:
        proj_from, proj_to = "170px", "-6px"
    else:
        proj_from, proj_to = "120px", "70px"

    shake_anim = (
        f"animation:rg-shake-{cid} {min(500, dur)}ms steps(6) 1;"
        if mode in {"attack", "hex"} and vfx["damage"] > 0
        else ""
    )

    style = f"""
    <style>
    @keyframes rg-shake-{cid} {{
      0%,100%{{transform:translate(-50%,-50%)}}
      25%{{transform:translate(calc(-50% - {amp}px),-50%)}}
      75%{{transform:translate(calc(-50% + {amp}px),-50%)}}
    }}
    @keyframes rg-proj-{cid} {{
      0%{{transform:translate(-50%,{proj_from}) scale(.5); opacity:0}}
      30%{{opacity:1}}
      70%{{transform:translate(-50%,{proj_to}) scale(1.3); opacity:1}}
      100%{{transform:translate(-50%,{proj_to}) scale(2); opacity:0}}
    }}
    @keyframes rg-flash-{cid} {{0%{{opacity:0}} 60%{{opacity:.45}} 100%{{opacity:0}}}}
    @keyframes rg-burst-{cid} {{
      0%{{transform:rotate(var(--a)) translateY(0) scale(.4); opacity:0}}
      35%{{opacity:1}}
      100%{{transform:rotate(var(--a)) translateY(-96px) scale(1); opacity:0}}
    }}
    @keyframes rg-num-{cid} {{
      0%{{transform:translate(-50%,10px) scale(.6); opacity:0}}
      30%{{transform:translate(-50%,-14px) scale(1.2); opacity:1}}
      100%{{transform:translate(-50%,-58px) scale(1); opacity:0}}
    }}
    .rg-flash-{cid}{{position:absolute; inset:0; background:{flash};
      animation:rg-flash-{cid} {dur}ms ease-out 1; pointer-events:none;}}
    .rg-proj-{cid}{{position:absolute; left:50%; bottom:0; font-size:46px;
      filter:drop-shadow(0 0 10px {pal[0]});
      animation:rg-proj-{cid} {int(dur*0.7)}ms ease-out 1; pointer-events:none;}}
    .rg-pt-{cid}{{position:absolute; top:46%; left:50%; font-size:20px; color:{pal[1]};
      animation:rg-burst-{cid} {dur}ms ease-out 1 .12s both; pointer-events:none;}}
    .rg-num-{cid}{{position:absolute; top:30%; left:50%; font-family:"Press Start 2P",monospace;
      font-size:1.3rem; text-shadow:2px 2px 0 #000;
      animation:rg-num-{cid} {dur}ms ease-out 1 .1s both; pointer-events:none;}}
    .rg-burstwrap-{cid}{{position:absolute; top:0; left:0; right:0; bottom:0; pointer-events:none;}}
    </style>
    """
    enemy_anim = f"style='{shake_anim}'" if shake_anim else ""
    return (
        style
        + f"<div class='rg-flash-{cid}'></div>"
        + f"<div class='rg-proj-{cid}'>{glyph}</div>"
        + f"<div class='rg-burstwrap-{cid}'>{particles}</div>"
        + num,
        enemy_anim,
    )


def render_stage(snap: dict, vfx: dict | None = None) -> str:
    e = snap["enemy"]
    top, bot = room_backdrop(snap["room"]["index"])
    sprite = enemy_sprite(e["name"])
    weak = ", ".join(e["weakness"]) or "?"

    overlay = ""
    enemy_anim = ""
    if vfx is not None:
        overlay, enemy_anim = _vfx_layer(vfx)
        reaction = vfx.get("reaction", "")
    else:
        reaction = ""

    return (
        f"<div class='rg-stage' style='background:linear-gradient(180deg,{top},{bot})'>"
        f"{_hp_bar(e['hp'], e['max_hp'])}"
        f"<div class='rg-enemy' {enemy_anim}>"
        f"<div class='rg-sprite'>{sprite}</div>"
        f"<div class='rg-reaction'>{reaction}</div>"
        f"</div>"
        f"{overlay}"
        f"<div class='rg-name'>{e['name']} &nbsp;·&nbsp; "
        f"<span class='rg-weak'>weak: {weak}</span><br>"
        f"<span class='rg-mood'>{e['mood']}</span></div>"
        f"</div>"
    )


def render_hud(snap: dict) -> str:
    p = snap["player"]
    r = snap["room"]
    hearts = "♥" * p["hp"] + f"<span class='empty'>{'♡' * (p['max_hp'] - p['hp'])}</span>"
    inv = ", ".join(p["inventory"]) or "empty"
    return (
        "<div class='rg-hud'>"
        f"<div class='blk'><span class='lab'>HEALTH</span>"
        f"<span class='rg-hearts'>{hearts}</span></div>"
        f"<div class='blk'><span class='lab'>ROOM</span>"
        f"<span class='big'>{r['index'] + 1}/{r['total']}</span></div>"
        f"<div class='blk'><span class='lab'>SCORE</span>"
        f"<span class='big rg-score'>{snap['score']}</span></div>"
        f"<div class='blk'><span class='lab'>COURAGE</span>"
        f"<span class='big'>{p['courage']}</span></div>"
        f"<div class='blk' style='flex:1'><span class='lab'>SATCHEL</span>"
        f"<span class='rg-inv'>{inv}</span></div>"
        "</div>"
    )


def render_result(
    spell: SpellResult | None,
    visual: VisualReading | None = None,
    *,
    snap: dict | None = None,
    intro: str | None = None,
) -> str:
    if snap is not None and snap.get("over"):
        won = snap["won"]
        cls = "win" if won else "lose"
        head = "🏆 YOU SURVIVED THE DUNGEON" if won else "💀 YOU COLLAPSED"
        return (
            f"<div class='rg-banner {cls}'>{head}<br>Final score: {snap['score']}<br>"
            "<span style='font-size:.7rem'>press New Run to descend again</span></div>"
        )
    if intro is not None:
        return f"<div class='rg-result rg-flavor'>{intro}</div>"
    if spell is None:
        return "<div class='rg-result rg-flavor'>Draw a spell, or tap runes, then cast.</div>"

    parts = [f"<div class='rg-result'><h3>✨ {spell.spell_name}</h3>"]
    if spell.flavor:
        parts.append(f"<p class='rg-flavor'>{spell.flavor}</p>")
    parts.append(f"<p>{spell.effect}</p>")
    if spell.side_effect:
        parts.append(f"<p class='rg-side'>⚠ {spell.side_effect}</p>")
    if visual is not None:
        detected = ", ".join(visual.detected_runes) or "unreadable"
        amb = f" · ambiguous: {', '.join(visual.ambiguous_runes)}" if visual.ambiguous_runes else ""
        parts.append(
            f"<p class='rg-tags'>👁 read: <span class='rg-detected'>{detected}</span>"
            f"{amb} · {visual.confidence:.0%} sure</p>"
        )
    statuses = ", ".join(spell.status_effects) or "none"
    parts.append(
        f"<p class='rg-tags'>enemy {spell.enemy_hp_delta:+d} · "
        f"you {spell.player_hp_delta:+d} · chaos {spell.chaos}/10 · {statuses}</p></div>"
    )
    return "".join(parts)


def render_selected(selected: list[str]) -> str:
    if not selected:
        inner = "tap 2–4 runes ↓"
    else:
        inner = " + ".join(GLYPHS[k].symbol + GLYPHS[k].label for k in selected)
    return f"<div id='rg-selected'>{inner}</div>"


def _guide_html() -> str:
    rows = "".join(
        f"<tr><td class='sym'>{g.symbol}</td><td class='nm'>{g.label}</td>"
        f"<td class='mn'>{', '.join(g.meanings)}</td></tr>"
        for g in GLYPHS.values()
    )
    combos = "".join(
        f"<tr><td class='nm'>{' + '.join(GLYPHS[r].symbol for r in c.runes)}</td>"
        f"<td class='mn'>{c.meaning}</td></tr>"
        for c in COMBOS
    )
    return (
        "<div class='rg-guide'><b>Runes</b><table>"
        + rows
        + "</table><br><b>Known combinations</b><table>"
        + combos
        + "</table><p class='mn'>Add the 💢 Broken Mark to any spell for a stronger "
        "but cursed effect. Hit an enemy's weakness for bonus damage.</p></div>"
    )


# ---------------------------------------------------------------------------
# Game callbacks
# ---------------------------------------------------------------------------
def new_game():
    game = Game.new(use_vision_model=USE_MODEL, use_text_model=False)
    snap = game.snapshot()
    return (
        game,
        0,  # cast_id
        [],  # selected runes
        render_stage(snap),
        render_hud(snap),
        render_result(None, snap=snap, intro=game.current_room.intro),
        "\n".join(snap["log"]),
        render_selected([]),
        {},
        _blank_canvas(),
    )


def _post_cast(game: Game, cast_id: int, spell, visual, runes, raw):
    snap = game.snapshot()
    vfx = plan_vfx(spell, enemy_name=snap["enemy"]["name"], runes=runes, cast_id=cast_id)
    return (
        game,
        cast_id,
        render_stage(snap, vfx),
        render_hud(snap),
        render_result(spell, visual, snap=snap),
        "\n".join(snap["log"]),
        raw,
    )


def cast_drawing(game: Game, cast_id: int, canvas):
    """Generator: show a 'reading' beat, then the resolved spell."""
    if game is None:
        game = Game.new(use_vision_model=USE_MODEL, use_text_model=False)
    snap = game.snapshot()
    if snap["over"]:
        yield (game, cast_id, render_stage(snap), render_hud(snap),
               render_result(None, snap=snap), "\n".join(snap["log"]), gr.update())
        return

    image = _normalize_canvas(canvas)
    if _canvas_is_blank(image):
        yield (game, cast_id, gr.update(), gr.update(),
               render_result(None, intro="The canvas is blank. Draw a rune or two first."),
               "\n".join(snap["log"]), gr.update())
        return

    reading = "🔮 The goblin squints at your drawing" + ("…" if USE_MODEL else " (rule mode)…")
    yield (game, cast_id, gr.update(), gr.update(),
           render_result(None, intro=reading), "\n".join(snap["log"]), gr.update())

    cast_id += 1
    result = game.cast_drawing(image)
    yield _post_cast(game, cast_id, result.spell, result.visual_reading,
                     result.visual_reading.detected_runes, result.model_dump())


def add_rune(selected: list[str], key: str):
    selected = list(selected or [])
    if key in selected:
        selected.remove(key)
    elif len(selected) < 4:
        selected.append(key)
    return selected, render_selected(selected)


def clear_runes():
    return [], render_selected([])


def cast_runes(game: Game, cast_id: int, selected: list[str]):
    if game is None:
        game = Game.new(use_vision_model=USE_MODEL, use_text_model=False)
    snap = game.snapshot()
    if snap["over"] or not selected:
        intro = None if snap["over"] else "Pick at least one rune from the board first."
        return (game, cast_id, selected, render_stage(snap), render_hud(snap),
                render_result(None, snap=snap, intro=intro), "\n".join(snap["log"]),
                render_selected(selected), gr.update())
    cast_id += 1
    spell = game.cast(list(selected))
    g, cid, stage, hud, res, log, raw = _post_cast(
        game, cast_id, spell, None, list(selected), spell.model_dump()
    )
    return g, cid, [], stage, hud, res, log, render_selected([]), raw


def clear_canvas():
    return _blank_canvas()


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
def build() -> gr.Blocks:
    model_label = (VISION_MODEL.split("/")[-1] if USE_MODEL else "rule engine (model off)")
    with gr.Blocks(title="Rune Goblin", css=CSS, head=HEAD, theme=gr.themes.Base()) as demo:
        game_state = gr.State()
        cast_id_state = gr.State(0)
        selected_state = gr.State([])

        gr.HTML(
            "<div id='rg-title' class='rg-pixel'><h1>🪄 RUNE GOBLIN</h1>"
            "<p>draw bad spells · suffer beautifully</p></div>"
        )

        with gr.Row():
            with gr.Column(scale=6):
                stage_html = gr.HTML()
                hud_html = gr.HTML()
            with gr.Column(scale=5):
                result_html = gr.HTML()

        with gr.Row():
            with gr.Column(scale=6):
                gr.Markdown("#### ✍️ Draw your spell")
                canvas = gr.Sketchpad(
                    value=_blank_canvas(),
                    type="pil",
                    image_mode="RGBA",
                    canvas_size=(512, 512),
                    height=360,
                    label=None,
                    show_label=False,
                    brush=gr.Brush(default_size=9, colors=["#17120b"], default_color="#17120b"),
                    eraser=gr.Eraser(default_size=24),
                )
                with gr.Row():
                    cast_draw_btn = gr.Button("🔮 Cast Drawing", variant="primary")
                    clear_canvas_btn = gr.Button("Clear Canvas")
            with gr.Column(scale=5):
                gr.Markdown("#### 🪧 …or tap runes (instant)")
                rune_selected = gr.HTML(render_selected([]))
                rune_buttons = []
                keys = list(GLYPHS.keys())
                for r0 in range(0, len(keys), 8):
                    with gr.Row():
                        for key in keys[r0 : r0 + 8]:
                            b = gr.Button(GLYPHS[key].symbol, elem_classes="rg-rune")
                            rune_buttons.append((b, key))
                with gr.Row():
                    cast_runes_btn = gr.Button("⚡ Cast Runes", variant="primary")
                    clear_runes_btn = gr.Button("Clear")
                new_btn = gr.Button("🗡️ New Run")

        log_box = gr.Textbox(label="Dungeon Log", lines=8, interactive=False, elem_id="rg-log")

        with gr.Accordion("📖 RuneLang grimoire (rune meanings & combos)", open=False):
            gr.HTML(_guide_html())
        with gr.Accordion(f"⚙️ Model: {model_label}", open=False):
            gr.Markdown(
                "Drawings are read by the fine-tuned **goblinV1** vision model; rune-button "
                "casts use the deterministic rule engine. If the vision model can't load, "
                "drawings fall back to the rule engine so the game stays playable."
            )
            raw_json = gr.JSON(label="Last parsed model JSON")

        # wiring -----------------------------------------------------------
        draw_outputs = [game_state, cast_id_state, stage_html, hud_html, result_html,
                        log_box, raw_json]
        cast_draw_btn.click(
            cast_drawing, inputs=[game_state, cast_id_state, canvas], outputs=draw_outputs
        )
        clear_canvas_btn.click(clear_canvas, outputs=canvas)

        for b, key in rune_buttons:
            b.click(add_rune, inputs=[selected_state, gr.State(key)],
                    outputs=[selected_state, rune_selected])
        cast_runes_btn.click(
            cast_runes,
            inputs=[game_state, cast_id_state, selected_state],
            outputs=[game_state, cast_id_state, selected_state, stage_html, hud_html,
                     result_html, log_box, rune_selected, raw_json],
        )
        clear_runes_btn.click(clear_runes, outputs=[selected_state, rune_selected])

        new_outputs = [game_state, cast_id_state, selected_state, stage_html, hud_html,
                       result_html, log_box, rune_selected, raw_json, canvas]
        new_btn.click(new_game, outputs=new_outputs)
        demo.load(new_game, outputs=new_outputs)
    return demo


if __name__ == "__main__":
    build().launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("GRADIO_SERVER_PORT", "7861")),
    )
