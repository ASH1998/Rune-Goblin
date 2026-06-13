"""Bake additional Tiny Swords assets into app/rpg_static/sprites.

The original bake copied a curated subset of the raw packs in ``assets/`` into
``app/rpg_static/sprites`` + ``manifest.json``. This script adds the previously
unused assets that give each biome its own identity:

* terrain tiles  — sand (cropped from Tilemap_Flat), snow + stone (recolors)
* deco recolors  — snowy / dead trees from the baked tree
* static deco    — colored houses, castles, towers, gold-mine states,
                   resource piles, a fallen knight
* animated       — flame effect, TNT / Barrel goblins, colored wood towers

Run from the repo root (needs Pillow + the raw packs in assets/)::

    .venv/bin/python scripts/bake_extra_sprites.py
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageEnhance

ROOT = Path(__file__).resolve().parent.parent
TS = ROOT / "assets/Tiny Swords/Tiny Swords (Update 010)"
OUT = ROOT / "app/rpg_static/sprites"
MANIFEST = ROOT / "app/rpg_static/manifest.json"


def tint(im: Image.Image, rgb: tuple[int, int, int], strength: float) -> Image.Image:
    """Blend ``im`` toward a flat color, preserving alpha."""
    im = im.convert("RGBA")
    overlay = Image.new("RGBA", im.size, rgb + (0,))
    overlay.putalpha(im.getchannel("A"))
    return Image.blend(im, overlay, strength)


def recolor(src: Path, dst: Path, *, saturation: float, brightness: float,
            tint_rgb: tuple[int, int, int] | None = None, tint_strength: float = 0.0) -> None:
    im = Image.open(src).convert("RGBA")
    alpha = im.getchannel("A")
    im = ImageEnhance.Color(im).enhance(saturation)
    im = ImageEnhance.Brightness(im).enhance(brightness)
    if tint_rgb is not None and tint_strength > 0:
        im = tint(im, tint_rgb, tint_strength)
    im.putalpha(alpha)
    im.save(dst)
    print(f"recolor {dst.name}")


def crop(src: Path, dst: Path, box: tuple[int, int, int, int]) -> None:
    Image.open(src).convert("RGBA").crop(box).save(dst)
    print(f"crop    {dst.name}  {box}")


def copy(src: Path, dst: Path) -> None:
    Image.open(src).convert("RGBA").save(dst)
    print(f"copy    {dst.name}")


def main() -> None:
    flat = TS / "Terrain/Ground/Tilemap_Flat.png"

    # ---- terrain tiles (64x64 centers) ------------------------------------
    # Tilemap_Flat: cols 0-3 grass block, cols 5-8 sand block; (6,1) is the
    # interior sand tile (the grass twin of the baked grass.png at (1,1)).
    crop(flat, OUT / "sand.png", (6 * 64, 64, 7 * 64, 128))
    # No snow/stone tiles ship with the pack — derive them from sand/grass so
    # they keep the same pixel texture as the rest of the terrain.
    recolor(OUT / "sand.png", OUT / "snow.png",
            saturation=0.10, brightness=1.14, tint_rgb=(208, 226, 248), tint_strength=0.42)
    recolor(OUT / "grass.png", OUT / "stone.png",
            saturation=0.16, brightness=0.78, tint_rgb=(96, 96, 118), tint_strength=0.30)

    # ---- deco recolors ------------------------------------------------------
    recolor(OUT / "deco_tree.png", OUT / "deco_tree_snow.png",
            saturation=0.25, brightness=1.25, tint_rgb=(210, 232, 255), tint_strength=0.30)
    recolor(OUT / "deco_tree.png", OUT / "deco_tree_dead.png",
            saturation=0.12, brightness=0.62, tint_rgb=(92, 70, 54), tint_strength=0.25)

    # ---- static deco copies -------------------------------------------------
    deco_src = {
        "house_red": "Factions/Knights/Buildings/House/House_Red.png",
        "house_purple": "Factions/Knights/Buildings/House/House_Purple.png",
        "house_yellow": "Factions/Knights/Buildings/House/House_Yellow.png",
        "house_destroyed": "Factions/Knights/Buildings/House/House_Destroyed.png",
        "castle_yellow": "Factions/Knights/Buildings/Castle/Castle_Yellow.png",
        "castle_purple": "Factions/Knights/Buildings/Castle/Castle_Purple.png",
        "tower_red": "Factions/Knights/Buildings/Tower/Tower_Red.png",
        "tower_destroyed": "Factions/Knights/Buildings/Tower/Tower_Destroyed.png",
        "goldmine_destroyed": "Resources/Gold Mine/GoldMine_Destroyed.png",
        "goldmine_inactive": "Resources/Gold Mine/GoldMine_Inactive.png",
        "res_gold": "Resources/Resources/G_Idle.png",
        "res_wood": "Resources/Resources/W_Idle.png",
        "res_meat": "Resources/Resources/M_Idle.png",
    }
    for key, rel in deco_src.items():
        copy(TS / rel, OUT / f"{key}.png")
    # Dead.png is a 7-frame 128x256 skull-bounce strip (big skull top, small
    # skull bottom). Frame 4's top half is the big skull at rest — a perfect
    # static prop for the Bone Market and battlefield areas.
    crop(TS / "Factions/Knights/Troops/Dead/Dead.png",
         OUT / "skull.png", (4 * 128, 0, 5 * 128, 128))

    # ---- animated sheets (full copies; client plays row 0) ------------------
    anim_src = {
        # key: (path, fw, fh, frames)
        "flame": ("Effects/Fire/Fire.png", 128, 128, 7),
        "tnt_goblin": ("Factions/Goblins/Troops/TNT/Red/TNT_Red.png", 192, 192, 7),
        "barrel_goblin": ("Factions/Goblins/Troops/Barrel/Red/Barrel_Red.png", 192, 192, 4),
        "wood_tower_blue": ("Factions/Goblins/Buildings/Wood_Tower/Wood_Tower_Blue.png", 128, 192, 8),
        "wood_tower_purple": ("Factions/Goblins/Buildings/Wood_Tower/Wood_Tower_Purple.png", 128, 192, 8),
        "wood_tower_yellow": ("Factions/Goblins/Buildings/Wood_Tower/Wood_Tower_Yellow.png", 128, 192, 8),
    }
    for key, (rel, *_rest) in anim_src.items():
        copy(TS / rel, OUT / f"{key}.png")

    # ---- manifest -----------------------------------------------------------
    manifest = json.loads(MANIFEST.read_text())
    for key in deco_src:
        im = Image.open(OUT / f"{key}.png")
        manifest["deco"][key] = {"file": f"sprites/{key}.png", "fw": im.width, "fh": im.height}
    manifest["deco"]["skull"] = {"file": "sprites/skull.png", "fw": 128, "fh": 128}
    # tree recolors keep the baked tree's frame geometry (6 frames of 256x256;
    # the client draws frame 0 for deco)
    for key in ("tree_snow", "tree_dead"):
        manifest["deco"][key] = {"file": f"sprites/deco_{key}.png", "fw": 256, "fh": 256,
                                 "frames": 6}
    manifest["deco"].pop("dead_knight", None)
    # fix the pre-existing bush entry: it's an 8-frame 128x128 strip that was
    # declared as one 1024-wide sprite (rendered squashed). Frame 0 is correct.
    manifest["deco"]["bush"] = {"file": "sprites/deco_bush.png", "fw": 128, "fh": 128,
                                "frames": 8}
    for key, (_rel, fw, fh, frames) in anim_src.items():
        manifest["creatures"][key] = {"file": f"sprites/{key}.png", "fw": fw, "fh": fh,
                                      "frames": frames}
    MANIFEST.write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"manifest updated: {len(manifest['deco'])} deco, {len(manifest['creatures'])} creatures")


if __name__ == "__main__":
    main()
