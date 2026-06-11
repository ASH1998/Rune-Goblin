"""Tests for the Phase-2 RPG-depth systems (rpg_plan.md):
leveling 1-20, monster tiers, loot/reforge economy, crits."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rune_goblin import story, world  # noqa: E402


def _cum_xp(target_level: int) -> int:
    total, lvl = 0, 1
    while lvl < target_level:
        total += story.xp_to_next(lvl)
        lvl += 1
    return total


def test_xp_curve_landmarks():
    assert story.MAX_LEVEL == 20
    assert _cum_xp(5) == 64
    assert _cum_xp(8) == 154
    assert _cum_xp(10) == 236   # tier-2 evolution lands here
    assert _cum_xp(16) == 638   # king-eligible
    assert _cum_xp(20) == 1088


def test_level_rewards_cover_every_level():
    # Every level 2..20 grants at least +1 max HP plus its milestone.
    for lvl in range(2, 21):
        assert lvl in story.LEVEL_REWARDS
        assert story.LEVEL_REWARDS[lvl].get("max_hp", 0) >= 1
    assert story.LEVEL_REWARDS[10]["evolve_tier"] == 2
    assert story.LEVEL_REWARDS[8]["crit"] == 10


def test_apply_xp_reaches_level_10():
    level, xp, rewards = story.apply_xp(1, 0, 236)
    assert level == 10
    assert xp == 0
    assert len(rewards) == 9  # levels 2..10


def test_tier_kill_xp_and_respawn_halving():
    assert story.xp_for_kill("minion", 1) == 4
    assert story.xp_for_kill("standard", 2) == 10
    assert story.xp_for_kill("elite", 5) == 34
    assert story.xp_for_kill("standard", 2, respawned=True) == 5  # halved


def test_tier_stat_formulas():
    assert world._tier_hp("minion", 1) == 5
    assert world._tier_hp("standard", 2) == 12
    assert world._tier_hp("elite", 5) == 37
    assert world._tier_dmg("minion", 6) == 1
    assert world._tier_dmg("standard", 4) == 3
    assert world._tier_dmg("elite", 6) == 5


def test_monster_tiers_applied_in_world():
    cav = world.AREAS["caverns"]
    enemies = [e for e in cav.entities if e.type == "enemy"]
    assert any(e.tier == "elite" for e in enemies)
    assert any(e.tier == "minion" and e.unique is False for e in enemies)
    # every combat entity is tier-stamped with a melee value and display level
    for e in enemies:
        assert e.tier in ("minion", "standard", "elite")
        assert e.dmg >= 1
        assert e.level >= 1


def test_tier_levels_track_dr_and_tier():
    # higher DR and tougher tiers read as higher display levels
    assert world._tier_level("minion", 1) == 1   # floored at 1
    assert world._tier_level("standard", 2) == 4
    assert world._tier_level("elite", 5) == 12
    assert world._tier_level("boss", 6) == 15
    # the arena boss carries the level the client renders above its head
    boss = next(e for e in world.AREAS["arena"].entities if e.type == "boss")
    assert boss.level == 15


def test_reforge_clamps_and_gates():
    base = {"weapon_inventory": ["bell_staff"], "weapon_tiers": {},
            "items": {"rune_grit": 99, "warped_cog": 99}, "gold": 999, "level": 16}
    cur = 0
    for expected in (1, 2, 3):
        res = world.resolve_shop(base, "market_merchant", "reforge:bell_staff")
        act = [a for a in res["world_actions"] if a["type"] == "reforge_weapon"]
        assert act and act[0]["tier"] == expected
        cur = expected
        base["weapon_tiers"]["bell_staff"] = cur
    # maxed out
    res = world.resolve_shop(base, "market_merchant", "reforge:bell_staff")
    assert res.get("denied") and not res["world_actions"]


def test_reforge_level_gate():
    low = {"weapon_inventory": ["bell_staff"], "weapon_tiers": {"bell_staff": 2},
           "items": {"warped_cog": 9}, "gold": 99, "level": 5}
    res = world.resolve_shop(low, "market_merchant", "reforge:bell_staff")
    assert res.get("denied")  # +3 needs level 12


def test_crit_chance_gating_and_cap():
    assert world._crit_chance({"level": 1, "crit": 10}, []) == 0  # locked < L8
    assert world._crit_chance({"level": 8, "crit": 10}, []) == 10
    assert world._crit_chance({"level": 20, "crit": 100}, []) == 40  # capped
    masterful = {"level": 8, "crit": 10, "rune_mastery": {"bell": 5}}
    assert world._crit_chance(masterful, ["bell"]) == 20  # +10 mastered rune


def test_trinket_roll_shape():
    rare = story.roll_trinket("rare", "Clock Sewer", 1234)
    assert rare["id"] == "trinket_1234"
    assert len(rare["stats"]) == 1
    epic = story.roll_trinket("epic", "Bone Market", 5678)
    assert len(epic["stats"]) == 2
    assert all(k in story.TRINKET_STATS for k in epic["stats"])


def test_taunt_fallback_table():
    assert story.taunt_fallback("boss", "enrage")
    assert story.taunt_fallback("charge", "windup")
    # unknown archetype falls back to the brute line for that event
    assert story.taunt_fallback("nonsense", "spotted") == story.TAUNT_FALLBACK[("brute", "spotted")]


def test_drop_table_respawn_no_rares():
    import random
    acts = world._roll_drops({"tier": "elite", "id": "x", "name": "Foe", "respawned": True},
                             random.Random(1), area="Clock Sewer")
    kinds = {a["type"] for a in acts}
    assert "add_trinket" not in kinds  # respawn farming never yields rares
    assert "add_gold" in kinds
