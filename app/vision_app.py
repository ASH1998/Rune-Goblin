"""Rune Goblin vision Gradio app.

Draw a spell on the canvas and let the fine-tuned MiniCPM-V model
(``ASHu2/goblinV1`` by default) decide what the spell does.

Run:

    RG_USE_MODEL=1 uv run python app/vision_app.py
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
from rune_goblin.vision_inference import default_vision_model_id  # noqa: E402

USE_MODEL = os.environ.get("RG_USE_MODEL", "1") == "1"
VISION_MODEL = os.environ.get("RG_VISION_MODEL", default_vision_model_id())

CSS = """
.gradio-container {background: #11100d; color: #efe7d0;}
#title {text-align:center; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;}
#canvas-wrap {border: 1px solid #594b34;}
#log textarea {background:#17140f; color:#cce8b0; font-family:monospace;}
.stat-panel {border-left: 3px solid #8e6e37; padding-left: 12px;}
"""


def _blank_canvas() -> Image.Image:
    return Image.new("RGB", (512, 512), "#efe1bd")


def _normalize_canvas(value: Any) -> Image.Image:
    """Gradio Sketchpad can return PIL, ndarray, filepath, or editor dicts."""
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


def _enemy_md(snap: dict) -> str:
    e = snap["enemy"]
    bar = "#" * e["hp"] + "-" * (e["max_hp"] - e["hp"])
    return (
        f"### {e['name']}\n"
        f"HP: `{bar}` {e['hp']}/{e['max_hp']}\n\n"
        f"Weakness: **{', '.join(e['weakness'])}**\n\n"
        f"Resists: {', '.join(e['resistance'])}\n\n"
        f"Mood: *{e['mood']}*"
    )


def _player_md(snap: dict) -> str:
    p = snap["player"]
    hp = "#" * p["hp"] + "-" * (p["max_hp"] - p["hp"])
    inv = ", ".join(p["inventory"]) or "empty"
    room = snap["room"]
    return (
        f"### Room {room['index'] + 1}/{room['total']}: {room['name']}\n"
        f"Player HP: `{hp}` {p['hp']}/{p['max_hp']}\n\n"
        f"Score: **{snap['score']}**\n\n"
        f"Inventory: {inv}"
    )


def _result_md(result) -> str:
    spell = result.spell
    visual = result.visual_reading
    detected = ", ".join(visual.detected_runes) or "none"
    ambiguous = ", ".join(visual.ambiguous_runes) or "none"
    notes = ", ".join(visual.notes) or "none"
    return (
        f"### {spell.spell_name}\n"
        f"*{spell.flavor}*\n\n"
        f"**Effect:** {spell.effect}\n\n"
        + (f"**Side effect:** {spell.side_effect}\n\n" if spell.side_effect else "")
        + f"Detected: `{detected}`  \n"
        + f"Ambiguous: `{ambiguous}`  \n"
        + f"Confidence: `{visual.confidence:.0%}`  \n"
        + f"Notes: `{notes}`  \n"
        + f"Enemy `{spell.enemy_hp_delta:+d}` | Player `{spell.player_hp_delta:+d}` | "
        + f"Chaos `{spell.chaos}/10`"
    )


def new_game():
    game = Game.new(use_model=USE_MODEL)
    snap = game.snapshot()
    return (
        game,
        _blank_canvas(),
        _enemy_md(snap),
        _player_md(snap),
        "\n".join(snap["log"]),
        "*Draw 2-4 runes, then cast.*",
        {},
    )


def clear_canvas():
    return _blank_canvas()


def cast_drawing(game: Game, canvas):
    if game is None:
        game = Game.new(use_model=USE_MODEL)
    image = _normalize_canvas(canvas)
    result = game.cast_drawing(image)
    snap = game.snapshot()
    return (
        game,
        _enemy_md(snap),
        _player_md(snap),
        "\n".join(snap["log"]),
        _result_md(result),
        result.model_dump(),
    )


def build() -> gr.Blocks:
    model_label = VISION_MODEL if USE_MODEL else "fallback only"
    with gr.Blocks(title="Rune Goblin Vision") as demo:
        game_state = gr.State()

        gr.Markdown(
            f"# Rune Goblin Vision\nDraw a spell. Model: `{model_label}`",
            elem_id="title",
        )

        with gr.Row():
            with gr.Column(scale=7):
                canvas = gr.Sketchpad(
                    value=_blank_canvas(),
                    label="Spell canvas",
                    type="pil",
                    image_mode="RGBA",
                    canvas_size=(512, 512),
                    height=540,
                    brush=gr.Brush(default_size=9, colors=["#17120b"], default_color="#17120b"),
                    eraser=gr.Eraser(default_size=24),
                    elem_id="canvas-wrap",
                )
                with gr.Row():
                    cast_btn = gr.Button("Cast Drawing", variant="primary")
                    clear_btn = gr.Button("Clear Canvas")
                    new_btn = gr.Button("New Run")
            with gr.Column(scale=5, elem_classes="stat-panel"):
                enemy_md = gr.Markdown()
                player_md = gr.Markdown()
                result_md = gr.Markdown()

        log_box = gr.Textbox(label="Dungeon Log", lines=10, interactive=False, elem_id="log")
        raw_json = gr.JSON(label="Parsed model JSON")

        cast_btn.click(
            cast_drawing,
            inputs=[game_state, canvas],
            outputs=[game_state, enemy_md, player_md, log_box, result_md, raw_json],
        )
        clear_btn.click(clear_canvas, outputs=canvas)
        new_btn.click(
            new_game,
            outputs=[game_state, canvas, enemy_md, player_md, log_box, result_md, raw_json],
        )
        demo.load(
            new_game,
            outputs=[game_state, canvas, enemy_md, player_md, log_box, result_md, raw_json],
        )
    return demo


if __name__ == "__main__":
    build().launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("GRADIO_SERVER_PORT", "7861")),
        theme=gr.themes.Base(),
        css=CSS,
    )
