"""Unit tests for the story/progression tables (rune_goblin.story)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rune_goblin import story  # noqa: E402


def test_classes_and_weapons_present():
    assert set(story.GOBLIN_CLASSES) == {"warrior", "rogue", "poison", "hunter", "barbarian"}
    assert story.STARTING_WEAPON in story.WEAPONS
    for c in story.GOBLIN_CLASSES.values():
        assert c.hp > 0 and c.courage > 0 and c.affinity


def test_apply_xp_levels_up_with_rewards():
    level, xp, rewards = story.apply_xp(1, 0, story.xp_to_next(1))
    assert level == 2
    assert xp == 0
    assert rewards and rewards[0]["level"] == 2 and rewards[0].get("max_hp") == 2


def test_apply_xp_multi_level():
    # enough XP to vault several levels at once
    total = sum(story.xp_to_next(i) for i in range(1, 4))
    level, xp, rewards = story.apply_xp(1, 0, total)
    assert level == 4
    assert [r["level"] for r in rewards] == [2, 3, 4]


def test_apply_xp_caps_at_max_level():
    level, xp, rewards = story.apply_xp(story.MAX_LEVEL, 0, 9999)
    assert level == story.MAX_LEVEL


def test_filter_flags_allowlist():
    out = story.filter_flags(["tourist_helped", "not_a_real_flag", "tourist_helped"])
    assert out == ["tourist_helped"]


def test_ending_repaired():
    e = story.compute_ending(
        ["calendar_truth_read", "tourist_helped", "fungus_colony_spared"],
        final_runes=["leaf"])
    assert e.key == "repaired"


def test_ending_devoured():
    e = story.compute_ending(
        ["library_shelves_burned", "debt_deepened"], final_runes=["flame"])
    assert e.key == "devoured"


def test_ending_default_broken():
    e = story.compute_ending([], final_runes=["jagged_line"])
    assert e.key == "broken"


def test_ending_tollmaster_secret():
    flags = ["tollmaster_route_open", "queue_goblin_paid", "secret_merchant_met"]
    e = story.compute_ending(flags, final_runes=["coin"], weapon="coin_sling")
    assert e.key == "tollmaster"


def test_boss_phase_thresholds():
    assert story.boss_phase_for(24, 24)["phase"] == 1
    assert story.boss_phase_for(12, 24)["phase"] == 2
    assert story.boss_phase_for(4, 24)["phase"] == 3


def test_can_evolve():
    assert story.can_evolve(5, [], 3) is True
    assert story.can_evolve(1, ["tourist_helped"], 3) is True
    assert story.can_evolve(1, [], 3) is False  # no level, no identity
    assert story.can_evolve(5, [], 2) is False  # not final phase


def test_npc_intent_buckets():
    assert story.npc_intent(["coin"]) == "coin"
    assert story.npc_intent(["wave"]) == "kind"
    assert story.npc_intent(["eye"]) == "insight"
    assert story.npc_intent(["flame"]) == "fear"
    assert story.npc_intent([]) == "neutral"


def test_fallback_dialogue_shape():
    d = story.fallback_dialogue("toll_goblin", ["coin"])
    assert set(d) >= {"story_toast", "npc_line", "journal_entry",
                      "suggested_story_flag", "mood_shift"}
    assert "Queue Goblin" in d["npc_line"]
