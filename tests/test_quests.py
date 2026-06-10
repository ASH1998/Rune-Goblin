"""Unit tests for the quest + item system (rune_goblin.quests)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rune_goblin import quests  # noqa: E402


def _types(res):
    return [a["type"] for a in res["world_actions"]]


def _player(**kw):
    base = {"level": 1, "xp": 0, "items": {}, "quests": {}, "weapon": "clerk_wand"}
    base.update(kw)
    return base


def test_monster_drops_always_include_a_trophy():
    assert "monster_trophy" in quests.monster_drops("toll_wisp", "Toll Wisp")


def test_fungus_drops_a_spore_by_id_and_name():
    by_id = quests.monster_drops("fungus_a", "Mirror Fungus")
    assert "fungus_spore" in by_id and "monster_trophy" in by_id


def test_quest_giver_lookup():
    assert quests.is_quest_giver("watch_archer")
    assert not quests.is_quest_giver("tourist")


def test_first_talk_offers_and_accepts_quest():
    res = quests.resolve_quest_talk(_player(), "watch_archer")
    assert res["quest_state"] == "offered"
    assert "set_quest" in _types(res)
    setq = next(a for a in res["world_actions"] if a["type"] == "set_quest")
    assert setq["quest"] == "road_patrol" and setq["state"] == "active"


def test_active_quest_without_items_shows_progress():
    p = _player(quests={"road_patrol": "active"}, items={"monster_trophy": 1})
    res = quests.resolve_quest_talk(p, "watch_archer")
    assert res["quest_state"] == "progress"
    assert res["world_actions"] == []
    assert "1/2" in res["line"]


def test_turn_in_consumes_items_and_grants_reward():
    p = _player(quests={"road_patrol": "active"}, items={"monster_trophy": 2})
    res = quests.resolve_quest_talk(p, "watch_archer")
    assert res["quest_state"] == "turned_in"
    rm = next(a for a in res["world_actions"] if a["type"] == "remove_item")
    assert rm["item"] == "monster_trophy" and rm["qty"] == 2
    # two health potions + gold + xp + quest marked done
    adds = [a for a in res["world_actions"] if a["type"] == "add_item"]
    assert sum(a["qty"] for a in adds if a["item"] == "health_potion") == 2
    assert any(a["type"] == "add_gold" for a in res["world_actions"])
    assert any(a["type"] == "add_xp" for a in res["world_actions"])
    setq = next(a for a in res["world_actions"] if a["type"] == "set_quest")
    assert setq["state"] == "done"


def test_weapon_reward_quest_grants_equipment():
    p = _player(quests={"spore_sample": "active"}, items={"fungus_spore": 1})
    res = quests.resolve_quest_talk(p, "road_druid")
    assert res["quest_state"] == "turned_in"
    assert any(a["type"] == "add_weapon" and a["weapon"] == "river_thread"
               for a in res["world_actions"])


def test_completed_quartermaster_offers_repeatable_exchange():
    # done quest + enough trophies -> trade trophies for a potion
    p = _player(quests={"quartermaster_kit": "done"}, items={"monster_trophy": 2})
    res = quests.resolve_quest_talk(p, "quartermaster")
    assert res["quest_state"] == "exchange"
    assert any(a["type"] == "remove_item" for a in res["world_actions"])
    assert any(a["type"] == "add_item" and a["item"] == "health_potion"
               for a in res["world_actions"])


def test_completed_quest_without_trophies_just_thanks():
    p = _player(quests={"quartermaster_kit": "done"}, items={})
    res = quests.resolve_quest_talk(p, "quartermaster")
    assert res["quest_state"] == "done"
    assert res["world_actions"] == []


def test_non_giver_returns_none_state():
    res = quests.resolve_quest_talk(_player(), "tourist")
    assert res["quest_state"] == "none"
    assert res["world_actions"] == []
