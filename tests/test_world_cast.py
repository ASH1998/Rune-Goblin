"""Unit tests for world building + cast resolution (rune_goblin.world)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rune_goblin.world import build_world, resolve_world_cast, validate_world  # noqa: E402


def _types(res):
    return [a["type"] for a in res["world_actions"]]


def _player(**kw):
    base = {"hp": 12, "max_hp": 12, "courage": 5, "max_courage": 9,
            "goblin_class": "warrior", "weapon": "clerk_wand", "level": 1,
            "xp": 0, "story_flags": [], "rune_mastery": {}, "inventory": []}
    base.update(kw)
    return base


def test_world_validates_clean():
    assert validate_world() == []


def test_build_world_has_progression_and_content():
    w = build_world()
    assert len(w["areas"]) == 7
    assert {c["id"] for c in w["classes"]} == {"warrior", "rogue", "poison", "hunter", "barbarian"}
    assert {x["id"] for x in w["weapons"]}.issuperset({"clerk_wand", "bone_blade"})
    p = w["player"]
    for key in ("level", "xp", "goblin_class", "weapon", "story_flags", "gold", "journal"):
        assert key in p


def test_combat_damage_and_xp():
    tgt = {"id": "fungus_a", "type": "enemy", "name": "Mirror Fungus", "hp": 5,
           "max_hp": 5, "weakness": ["mirror", "eye"], "resistance": ["jagged_line"]}
    res = resolve_world_cast(["flame"], _player(), tgt, seed=1)  # flame not resisted here
    assert res["spell"]["enemy_hp_delta"] < 0
    assert "set_entity_hp" in _types(res)
    assert "set_progress" in _types(res)  # chip XP granted


def test_weapon_and_affinity_bonus():
    tgt = {"id": "e", "type": "enemy", "name": "Mirror Fungus", "hp": 9, "max_hp": 9,
           "weakness": [], "resistance": []}
    plain = resolve_world_cast(["bone"], _player(goblin_class="warrior", weapon="clerk_wand"), tgt, seed=2)
    geared = resolve_world_cast(["bone"], _player(goblin_class="barbarian", weapon="bone_blade"), tgt, seed=2)
    assert geared["spell"]["enemy_hp_delta"] < plain["spell"]["enemy_hp_delta"]


def test_enemy_defeat_grants_xp():
    tgt = {"id": "e", "type": "enemy", "name": "Mirror Fungus", "hp": 1, "max_hp": 5,
           "weakness": ["jagged_line"], "resistance": []}
    res = resolve_world_cast(["jagged_line"], _player(), tgt, seed=3)
    assert "defeat_entity" in _types(res)
    assert "set_progress" in _types(res)


def test_level_up_emitted_on_big_xp():
    # near level threshold, defeating an enemy should push a level_up
    tgt = {"id": "e", "type": "enemy", "name": "x", "hp": 1, "max_hp": 5,
           "weakness": ["flame"], "resistance": []}
    res = resolve_world_cast(["flame"], _player(level=1, xp=7), tgt, seed=4)
    assert "level_up" in _types(res)


def test_rune_mastery_adds_damage_and_emits_bump():
    tgt = {"id": "e", "type": "enemy", "name": "x", "hp": 9, "max_hp": 9,
           "weakness": [], "resistance": []}
    novice = resolve_world_cast(["spiral"], _player(goblin_class="warrior", weapon="clerk_wand"), tgt, seed=11)
    master = resolve_world_cast(["spiral"], _player(goblin_class="warrior", weapon="clerk_wand",
                                rune_mastery={"spiral": 5}), tgt, seed=11)
    assert master["spell"]["enemy_hp_delta"] < novice["spell"]["enemy_hp_delta"]
    assert "bump_mastery" in _types(novice)


def test_map_sizes_meet_plan_targets():
    w = build_world()
    a = w["areas"]
    assert a["overworld"]["width"] >= 48 and a["overworld"]["height"] >= 32
    assert a["caverns"]["width"] >= 44 and a["caverns"]["height"] >= 30
    assert a["library"]["width"] >= 44 and a["library"]["height"] >= 30
    assert a["bone_market"]["width"] >= 36 and a["bone_market"]["height"] >= 28
    assert a["clock_sewer"]["width"] >= 36 and a["clock_sewer"]["height"] >= 28
    assert a["arena"]["width"] >= 28 and a["arena"]["height"] >= 22


def test_chest_calendar_key_sets_flag():
    tgt = {"id": "ink_chest", "type": "chest", "state": "locked",
           "requires": ["key", "eye", "wave"], "loot": ["Calendar Key"]}
    res = resolve_world_cast(["key", "eye", "wave"], _player(), tgt, seed=5)
    flags = [a["flag"] for a in res["world_actions"] if a["type"] == "set_story_flag"]
    assert "calendar_key_found" in flags
    assert "add_inventory" in _types(res)


def test_merchant_sells_weapon_for_coin():
    tgt = {"id": "market_merchant", "type": "npc", "name": "Bone Market Merchant",
           "loot": ["bone_blade"], "dialogue": "buy"}
    res = resolve_world_cast(["coin"], _player(), tgt, seed=6)
    assert "add_weapon" in _types(res)
    flags = [a["flag"] for a in res["world_actions"] if a["type"] == "set_story_flag"]
    assert "weapon_bought" in flags


def test_npc_kindness_sets_trust_flag_and_journal():
    tgt = {"id": "tourist", "type": "npc", "name": "Lost Tourist", "dialogue": "help"}
    res = resolve_world_cast(["wave"], _player(), tgt, seed=7)
    flags = [a["flag"] for a in res["world_actions"] if a["type"] == "set_story_flag"]
    assert "tourist_helped" in flags
    assert "add_journal_entry" in _types(res)


def test_forced_door_creates_debt_pressure():
    tgt = {"id": "emotional_door", "type": "locked_door", "state": "locked",
           "requires": ["wave", "key"]}
    res = resolve_world_cast(["broken_mark", "key"], _player(), tgt, seed=8)
    flags = [a["flag"] for a in res["world_actions"] if a["type"] == "set_story_flag"]
    assert "debt_accepted" in flags and "calendar_devour_pressure" in flags


def test_boss_phase_banner_and_repaired_ending():
    # heavy hit that crosses a phase boundary (24 -> below 16)
    boss = {"id": "calendar_beast", "type": "boss", "name": "Calendar Beast",
            "hp": 17, "max_hp": 24, "weakness": ["spiral", "eye"], "resistance": []}
    res = resolve_world_cast(["spiral", "eye"], _player(), boss, seed=9)
    assert "start_boss_phase" in _types(res)

    # killing blow with repaired conditions
    boss2 = {"id": "calendar_beast", "type": "boss", "name": "Calendar Beast",
             "hp": 1, "max_hp": 24, "weakness": ["leaf"], "resistance": []}
    flags = ["calendar_truth_read", "tourist_helped", "fungus_colony_spared"]
    res2 = resolve_world_cast(["leaf", "spiral"], _player(story_flags=flags), boss2, seed=10)
    win = [a for a in res2["world_actions"] if a["type"] == "win_game"]
    assert win and win[0]["ending"] == "repaired"
