"""Quick repro: load the goblinV1 GGUF vision model and cast on a doodle.

Usage: uv run --extra gguf python scripts/test_vision_cast.py
Env knobs: RG_GGUF_CTX, RG_GGUF_GPU_LAYERS, RG_GGUF_N_BATCH
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("RG_USE_MODEL", "1")
os.environ.setdefault(
    "RG_VISION_MODEL", str(ROOT / "models/goblinV1-gguf/gguf/rune-goblin-v46-Q4_K_M.gguf"))
os.environ.setdefault(
    "RG_VISION_MMPROJ", str(ROOT / "models/goblinV1-gguf/gguf/rune-goblin-v46-mmproj-f16.gguf"))

from PIL import Image, ImageDraw  # noqa: E402

from rune_goblin.engine import GameState  # noqa: E402
from rune_goblin.vision_inference import cast_vision_spell  # noqa: E402


def doodle() -> Image.Image:
    img = Image.new("RGB", (320, 320), "#efe1bd")
    d = ImageDraw.Draw(img)
    # crude spiral
    import math
    pts = [(160 + math.cos(a / 4) * (5 + a * 1.4), 160 + math.sin(a / 4) * (5 + a * 1.4))
           for a in range(80)]
    d.line(pts, fill="#17120b", width=6)
    return img


state = GameState(player_hp=12, player_max_hp=12, enemy_name="Mirror Fungus",
                  enemy_hp=5, enemy_max_hp=5, room_mood="damp", inventory=("wet candle",),
                  courage=5)
res = cast_vision_spell(state, doodle(), room_name="Goblin Toll Road", use_model=True)
print("DETECTED:", res.visual_reading.detected_runes)
print("NOTES:", res.visual_reading.notes)
print("SPELL:", res.spell.spell_name, "|", res.spell.effect)
