"""Static runtime manifest checks for RPG assets."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_manifest_carries_playable_hero_metadata():
    manifest = json.loads((ROOT / "app/rpg_static/manifest.json").read_text())
    heroes = manifest.get("heroes", [])

    assert {h["id"] for h in heroes} == {"warrior", "rogue", "poison", "hunter", "barbarian"}
    for hero in heroes:
        assert hero["sprite"] in manifest["creatures"]
        assert hero["hp"] > 0
        assert hero["courage"] > 0
        assert hero["speed"] > 0
        assert hero["affinity_runes"]
        assert hero["passive"]
        assert hero["king_ability"]
        assert (ROOT / "app/rpg_static" / hero["preview_gif"]).exists()

