"""Rune Goblin — Gradio game UI (plan section 12).

Feels like a tiny cursed dungeon, not a chatbot. Runs on the deterministic
rule engine until a fine-tuned adapter is present, then automatically uses
the model (see ``rune_goblin.inference``).

Run::

    uv run python app/app.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# allow running the file directly without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import gradio as gr  # noqa: E402

from rune_goblin.game import Game  # noqa: E402
from rune_goblin.runelang import GLYPHS  # noqa: E402

USE_MODEL = os.environ.get("RG_USE_MODEL", "0") == "1"

CSS = """
.gradio-container {background: #0e0b14; color: #e7d9ff;}
#title {text-align:center; font-family: monospace;}
.rune-btn button {font-size: 1.4rem !important; min-width: 64px;}
#log textarea {background:#1a1426; color:#b7f5c2; font-family:monospace;}
"""


def _enemy_md(snap: dict) -> str:
    e = snap["enemy"]
    bar = "█" * e["hp"] + "░" * (e["max_hp"] - e["hp"])
    return (
        f"### 👹 {e['name']}\n"
        f"HP: `{bar}` {e['hp']}/{e['max_hp']}\n\n"
        f"Weakness: **{', '.join(e['weakness'])}**  ·  Resists: {', '.join(e['resistance'])}\n\n"
        f"Mood: *{e['mood']}*"
    )


def _player_md(snap: dict) -> str:
    p = snap["player"]
    bar = "❤" * p["hp"] + "·" * (p["max_hp"] - p["hp"])
    inv = ", ".join(p["inventory"]) or "empty"
    r = snap["room"]
    return (
        f"### 🧙 You — Room {r['index'] + 1}/{r['total']}: {r['name']}\n"
        f"HP: {bar} {p['hp']}/{p['max_hp']}  ·  Score: **{snap['score']}**\n\n"
        f"Inventory: {inv}"
    )


def new_game():
    game = Game.new(use_text_model=USE_MODEL)
    snap = game.snapshot()
    return (game, _enemy_md(snap), _player_md(snap), "\n".join(snap["log"]),
            "", "*No spell cast yet.*")


def add_rune(selected: str, key: str):
    parts = [p for p in selected.split(" + ") if p]
    if len(parts) >= 4:
        return selected  # max 4 runes
    parts.append(key)
    return " + ".join(parts)


def clear_runes():
    return ""


def cast(game: Game, selected: str):
    runes = [p for p in selected.split(" + ") if p]
    if not game or game.over or not runes:
        snap = game.snapshot() if game else {}
        return (game, gr.update(), gr.update(), gr.update(), "",
                "*Pick 2–4 runes first (or start a new run).*")
    spell = game.cast(runes)
    snap = game.snapshot()
    result_md = (
        f"### ✨ {spell.spell_name}  \n"
        f"*{spell.flavor}*\n\n"
        f"**Effect:** {spell.effect}\n\n"
        + (f"**Side effect:** {spell.side_effect}\n\n" if spell.side_effect else "")
        + f"`enemy {spell.enemy_hp_delta:+d}` · `player {spell.player_hp_delta:+d}` · "
        f"chaos {spell.chaos}/10 · {', '.join(spell.status_effects) or 'no statuses'}"
    )
    return (game, _enemy_md(snap), _player_md(snap), "\n".join(snap["log"]),
            "", result_md)


def build() -> gr.Blocks:
    with gr.Blocks(css=CSS, title="Rune Goblin", theme=gr.themes.Base()) as demo:
        game_state = gr.State()

        gr.Markdown("# 🪄 Rune Goblin\nDraw forbidden spells. Regret efficiently.", elem_id="title")

        with gr.Row():
            enemy_md = gr.Markdown()
            player_md = gr.Markdown()

        selected = gr.Textbox(label="Selected spell", interactive=False)

        gr.Markdown("#### Rune Board — tap 2–4 runes")
        with gr.Row():
            for key, g in GLYPHS.items():
                btn = gr.Button(f"{g.symbol} {g.label}", elem_classes="rune-btn")
                btn.click(add_rune, inputs=[selected, gr.State(key)], outputs=selected)

        with gr.Row():
            cast_btn = gr.Button("🔮 CAST SPELL", variant="primary")
            clear_btn = gr.Button("Clear")
            new_btn = gr.Button("New Run")

        result_md = gr.Markdown()
        log_box = gr.Textbox(label="Dungeon Log", lines=12, interactive=False, elem_id="log")

        clear_btn.click(clear_runes, outputs=selected)
        cast_btn.click(cast, inputs=[game_state, selected],
                       outputs=[game_state, enemy_md, player_md, log_box, selected, result_md])
        new_btn.click(new_game,
                      outputs=[game_state, enemy_md, player_md, log_box, selected, result_md])
        demo.load(new_game,
                  outputs=[game_state, enemy_md, player_md, log_box, selected, result_md])
    return demo


if __name__ == "__main__":
    build().launch(server_name="0.0.0.0", server_port=7860)
