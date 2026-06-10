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
    assert len(w["areas"]) == 9
    assert {"frost_pass", "ember_foundry"}.issubset(w["areas"])
    assert {c["id"] for c in w["classes"]} == {"warrior", "rogue", "poison", "hunter", "barbarian"}
    assert {x["id"] for x in w["weapons"]}.issuperset({"clerk_wand", "bone_blade"})
    p = w["player"]
    for key in ("level", "xp", "goblin_class", "weapon", "story_flags", "gold", "journal",
                "recent_story_events"):
        assert key in p
    assert p["recent_story_events"] == []


def test_admin_mode_unlocks_every_map():
    normal = build_world()
    admin = build_world(admin=True)

    # default build is never admin and keeps gates locked
    assert "admin" not in normal
    assert any(
        e.get("state") == "locked"
        for area in normal["areas"].values()
        for e in area["entities"]
        if e["type"] in {"portal", "locked_door"}
    )

    # admin build flags itself and leaves no locked portals/doors anywhere
    assert admin["admin"] is True
    for area in admin["areas"].values():
        for e in area["entities"]:
            if e["type"] in {"portal", "locked_door"}:
                assert e["state"] != "locked"
                assert e["blocking"] is False
                assert e["requires"] == []
    # key story items are granted so inventory-gated content also opens
    for item in ("Calendar Key", "Debt Receipt", "Thawed Ember"):
        assert item in admin["player"]["inventory"]


def test_seeded_world_variations_are_deterministic_and_noncritical():
    default = build_world()
    seeded_a = build_world(seed=123)
    seeded_b = build_world(seed=123)
    seeded_c = build_world(seed=456)

    assert default["world_seed"] is None
    assert seeded_a["world_seed"] == 123
    assert seeded_a["variation"] == seeded_b["variation"]
    assert seeded_a["player"]["journal"] == seeded_b["player"]["journal"]
    assert seeded_a["variation"]["id"] != seeded_c["variation"]["id"]

    markers = [
        e
        for area in seeded_a["areas"].values()
        for e in area["entities"]
        if e["type"] == "map_marker" and "seeded" in e["tags"]
    ]
    assert len(markers) == 1
    assert markers[0]["blocking"] is False


def test_gate_approach_has_hidden_consequence_allies():
    gate = build_world()["areas"]["gate_approach"]
    by_id = {e["id"]: e for e in gate["entities"]}

    for eid in ("gate_tourist", "gate_librarian", "gate_water_spirit",
                "gate_queue_goblin", "debt_collector"):
        assert by_id[eid]["state"] == "hidden"
        assert by_id[eid]["blocking"] is False

    assert by_id["gate_librarian"]["name"] == "Mold Librarian"
    assert by_id["gate_water_spirit"]["name"] == "Water Spirit"
    assert by_id["gate_queue_goblin"]["name"] == "Queue Goblin"


def test_world_quality_rules_have_evidence():
    w = build_world()
    for aid, area in w["areas"].items():
        entities = area["entities"]
        types = {e["type"] for e in entities}
        walkable = sum(ch in ".," for row in area["rows"] for ch in row)
        assert "story_object" in types
        assert "npc" in types
        assert "shrine" in types
        assert walkable > area["width"] * area["height"] * 0.45
        assert any(e["state"] == "locked" or e["requires"] for e in entities)
        assert any(
            (e["state"] == "locked" or e["requires"])
            and (e["loot"] or e["type"] in {"story_object", "locked_door", "portal", "chest"})
            for e in entities
        )
        assert any(e["dialogue"] and e["type"] in {"npc", "story_object"} for e in entities)
        assert any(
            e["type"] in {"chest", "locked_door"}
            or (e["type"] == "portal" and (e["state"] == "locked" or e["requires"]))
            or e["id"] in {
                "toll_board", "bell_shrine", "nursery", "cave_echo", "wet_catalog",
                "dry_shelves", "debt_altar", "clean_shrine", "sewer_valve",
                "gate_banner", "pylon_eye", "pylon_mirror", "pylon_leaf", "pylon_spiral",
            }
            for e in entities
        )
        if aid != w["start_area"]:
            assert any(e["type"] == "portal" and e["target_area"] != aid for e in entities)


def test_required_item_paths_are_present():
    w = build_world()
    loot = {
        item
        for area in w["areas"].values()
        for e in area["entities"]
        for item in e.get("loot", [])
    }
    assert "Calendar Shard" in loot
    assert "Calendar Key" in loot
    # These are granted by story actions, not static chest loot.
    for item in ("Debt Receipt", "Mirror Cap", "Tollmaster Token"):
        assert item not in loot
    assert validate_world() == []


def test_boss_arena_has_movement_space_and_phase_anchors():
    arena = build_world()["areas"]["arena"]
    walkable = sum(ch in ".," for row in arena["rows"] for ch in row)
    assert walkable >= 80
    ids = {e["id"] for e in arena["entities"]}
    assert {"calendar_beast", "arena_echo", "arena_shrine", "pylon_eye", "pylon_mirror", "pylon_leaf", "pylon_spiral"} <= ids


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
    meta = geared["metadata"]["combat"]
    assert meta["weapon"]["id"] == "bone_blade"
    assert meta["weapon"]["bonus_damage"] == 2
    assert meta["goblin_class"]["id"] == "barbarian"
    assert meta["goblin_class"]["bonus_damage"] == 1
    assert meta["total_bonus"] == 3


def test_combat_metadata_tracks_mastery_pylon_and_king_bonus():
    boss = {"id": "calendar_beast", "type": "boss", "name": "Calendar Beast",
            "hp": 20, "max_hp": 24, "weakness": ["spiral"], "resistance": []}
    player = _player(
        goblin_class="hunter",
        weapon="river_thread",
        rune_mastery={"spiral": 5},
        story_flags=["pylon_spiral_charged"],
        evolved=True,
    )
    res = resolve_world_cast(["spiral", "thread"], player, boss, seed=25)
    meta = res["metadata"]["combat"]

    assert meta["weapon"]["bonus_damage"] == 0
    assert meta["goblin_class"]["bonus_damage"] == 1
    assert meta["rune_mastery"]["bonus_damage"] == 1
    assert meta["boss"]["pylon_bonus"] == 2
    assert meta["boss"]["king_bonus"] == 2
    assert "weakness_revealed" in meta["boss"]["king_statuses"]
    assert meta["total_bonus"] == 6


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
    # weapons cost gold now: a funded player buys, and gold is charged
    res = resolve_world_cast(["coin"], _player(gold=5), tgt, seed=6)
    assert "add_weapon" in _types(res)
    flags = [a["flag"] for a in res["world_actions"] if a["type"] == "set_story_flag"]
    assert "weapon_bought" in flags
    assert any(a["type"] == "add_gold" and a["amount"] < 0
               for a in res["world_actions"])


def test_bone_market_cursed_deal_grants_power_and_tracks_cost():
    tgt = {"id": "market_merchant", "type": "npc", "name": "Bone Market Merchant",
           "dialogue": "deal"}
    res = resolve_world_cast(["broken_mark"], _player(), tgt, seed=21)
    actions = res["world_actions"]
    flags = [a["flag"] for a in actions if a["type"] == "set_story_flag"]

    assert any(a["type"] == "add_weapon" and a["weapon"] == "bone_blade" for a in actions)
    assert any(a["type"] == "add_courage" and a["amount"] == 3 for a in actions)
    assert any(a["type"] == "add_gold" and a["amount"] == 2 for a in actions)
    assert "debt_deepened" in flags
    assert "calendar_devour_pressure" in flags
    assert "add_journal_entry" in _types(res)


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


def test_bone_market_portal_accepts_receipt_or_coin_bell_or_forced_debt():
    tgt = {"id": "portal_market", "type": "portal", "state": "locked",
           "requires": ["Debt Receipt"]}
    with_receipt = resolve_world_cast(["eye"], _player(inventory=["Debt Receipt"]), tgt, seed=16)
    with_coin_bell = resolve_world_cast(["coin", "bell"], _player(), tgt, seed=16)
    forced = resolve_world_cast(["broken_mark", "key"], _player(), tgt, seed=16)

    assert "set_entity_blocking" in _types(with_receipt)
    assert "set_entity_blocking" in _types(with_coin_bell)
    assert any(a.get("flag") == "bone_market_entered" for a in with_coin_bell["world_actions"])
    assert any(a.get("item") == "Debt Receipt" for a in forced["world_actions"])


def test_boss_phase_banner_and_repaired_ending():
    # heavy hit that crosses a phase boundary (24 -> below 16)
    boss = {"id": "calendar_beast", "type": "boss", "name": "Calendar Beast",
            "hp": 17, "max_hp": 24, "weakness": ["spiral", "eye"], "resistance": []}
    phase_flags = ["tourist_helped", "fungus_colony_spared", "librarian_trust", "clean_water_restored"]
    res = resolve_world_cast(["spiral", "eye"], _player(story_flags=phase_flags), boss, seed=9)
    phase = [a for a in res["world_actions"] if a["type"] == "start_boss_phase"]
    assert phase
    assert len(phase[0]["boss_reactions"]) >= 2

    # killing blow with repaired conditions (must be hand-drawn to land)
    boss2 = {"id": "calendar_beast", "type": "boss", "name": "Calendar Beast",
             "hp": 1, "max_hp": 24, "weakness": ["leaf"], "resistance": []}
    flags = ["calendar_truth_read", "tourist_helped", "fungus_colony_spared"]
    res2 = resolve_world_cast(["leaf", "spiral"], _player(story_flags=flags), boss2,
                              seed=10, drawn=True)
    win = [a for a in res2["world_actions"] if a["type"] == "win_game"]
    assert win and win[0]["ending"] == "repaired"
    assert "choices" in win[0]
    assert win[0]["boss_reactions"]
    assert any("Lost Tourist" in line for line in win[0]["choices"])
    assert any("calendar truth" in line for line in win[0]["choices"])


def test_pylons_charge_flags_and_alter_boss_combat():
    pylon = {"id": "pylon_spiral", "type": "story_object", "name": "Spiral Pylon",
             "requires": ["spiral"], "dialogue": "charged"}
    charged = resolve_world_cast(["spiral"], _player(), pylon, seed=22)
    assert any(a.get("flag") == "pylon_spiral_charged" for a in charged["world_actions"])

    boss = {"id": "calendar_beast", "type": "boss", "name": "Calendar Beast",
            "hp": 20, "max_hp": 24, "weakness": ["spiral", "eye"], "resistance": []}
    plain = resolve_world_cast(["spiral"], _player(), boss, seed=23)
    with_pylon = resolve_world_cast(
        ["spiral"], _player(story_flags=["pylon_spiral_charged"]), boss, seed=23)

    assert with_pylon["spell"]["enemy_hp_delta"] < plain["spell"]["enemy_hp_delta"]
    assert "pylon_spiral_unwound" in with_pylon["spell"]["status_effects"]


def test_eye_pylon_reveals_boss_weakness():
    boss = {"id": "calendar_beast", "type": "boss", "name": "Calendar Beast",
            "hp": 12, "max_hp": 24, "weakness": ["mirror", "wave"], "resistance": []}
    plain = resolve_world_cast(["eye"], _player(), boss, seed=24)
    revealed = resolve_world_cast(
        ["eye"], _player(story_flags=["pylon_eye_charged"]), boss, seed=24)

    assert revealed["spell"]["enemy_hp_delta"] < plain["spell"]["enemy_hp_delta"]
    assert "pylon_eye_revealed" in revealed["spell"]["status_effects"]


def test_boss_repeated_runes_adapt_and_spawn_phase_adds():
    boss = {"id": "calendar_beast", "type": "boss", "name": "Calendar Beast",
            "hp": 17, "max_hp": 24, "weakness": ["spiral", "eye"], "resistance": []}
    fresh = resolve_world_cast(["spiral", "eye"], _player(), boss, seed=12)
    repeated = resolve_world_cast(
        ["spiral", "eye"], _player(recent_runes=["spiral", "eye"]), boss, seed=12)

    assert "boss_adapted" in repeated["spell"]["status_effects"]
    assert repeated["spell"]["enemy_hp_delta"] > fresh["spell"]["enemy_hp_delta"]

    spawns = [a for a in fresh["world_actions"] if a["type"] == "spawn_entity"]
    assert spawns and spawns[0]["entity"]["id"] == "phase2_debt_echo"


def test_story_branches_for_spores_shelves_and_tollmaster_token():
    nursery = {"id": "nursery", "type": "story_object", "name": "Fungus Nursery",
               "requires": ["mirror"], "dialogue": "spared"}
    spared = resolve_world_cast(["mirror"], _player(), nursery, seed=13)
    burned = resolve_world_cast(["flame"], _player(), nursery, seed=13)
    assert any(a.get("item") == "Mirror Cap" for a in spared["world_actions"])
    assert any(a.get("weapon") == "mirror_shield" for a in spared["world_actions"])
    assert any(a.get("flag") == "fungus_colony_burned" for a in burned["world_actions"])

    shelves = {"id": "dry_shelves", "type": "story_object", "name": "Dry Archive Shelves",
               "requires": ["flame"], "dialogue": "shortcut"}
    shelf_res = resolve_world_cast(["flame"], _player(), shelves, seed=14)
    assert "unlock_shortcut" in _types(shelf_res)
    assert any(a.get("flag") == "library_shelves_burned" for a in shelf_res["world_actions"])

    shrine = {"id": "bell_shrine", "type": "story_object", "name": "Hidden Bell Shrine",
              "requires": ["bell", "coin"], "dialogue": "token"}
    token_res = resolve_world_cast(["bell", "coin"], _player(), shrine, seed=15)
    assert any(a.get("item") == "Tollmaster Token" for a in token_res["world_actions"])
    assert any(a.get("weapon") == "bell_staff" for a in token_res["world_actions"])


def test_secret_merchant_hidden_and_duplicate_trade_upgrades_weapon():
    world = build_world()
    secret = next(e for e in world["areas"]["bone_market"]["entities"] if e["id"] == "secret_merchant")
    assert secret["state"] == "hidden" and secret["blocking"] is False

    merchant = {"id": "market_merchant", "type": "npc", "name": "Bone Market Merchant",
                "dialogue": "buy"}
    res = resolve_world_cast(
        ["coin"], _player(weapon_inventory=["clerk_wand", "mirror_shield"]), merchant, seed=17)
    assert "upgrade_weapon" in _types(res)


def test_clean_water_sets_sewer_shortcut_flag():
    shrine = {"id": "clean_shrine", "type": "story_object", "name": "Clean-Water Shrine",
              "requires": ["wave", "leaf"], "dialogue": "clean"}
    res = resolve_world_cast(["wave", "leaf"], _player(), shrine, seed=18)
    flags = [a["flag"] for a in res["world_actions"] if a["type"] == "set_story_flag"]
    assert "clean_water_restored" in flags and "sewer_shortcut_open" in flags
    assert any(a.get("weapon") == "river_thread" for a in res["world_actions"])

    valve = {"id": "sewer_valve", "type": "story_object", "name": "Rusted Valve",
             "requires": ["thread", "key"], "dialogue": "aligned"}
    valve_res = resolve_world_cast(["thread", "key"], _player(), valve, seed=19)
    valve_flags = [a["flag"] for a in valve_res["world_actions"] if a["type"] == "set_story_flag"]
    assert "sewer_valves_aligned" in valve_flags and "sewer_shortcut_open" in valve_flags


def test_gate_approach_final_gate_requires_calendar_key():
    world = build_world()
    final_gate = next(e for e in world["areas"]["gate_approach"]["entities"] if e["id"] == "final_gate")
    assert final_gate["state"] == "locked"
    assert final_gate["blocking"] is True
    assert final_gate["requires"] == ["Calendar Key"]

    denied = resolve_world_cast(["key"], _player(), final_gate, seed=20)
    assert "set_entity_blocking" not in _types(denied)

    opened = resolve_world_cast(["key"], _player(inventory=["Calendar Key"]), final_gate, seed=20)
    assert "set_entity_blocking" in _types(opened)


def _flags(res):
    return [a["flag"] for a in res["world_actions"] if a["type"] == "set_story_flag"]


def _gold_delta(res):
    return sum(a["amount"] for a in res["world_actions"] if a["type"] == "add_gold")


TOLL_GOBLIN = {"id": "toll_goblin", "type": "enemy", "name": "Queue Goblin",
               "hp": 5, "max_hp": 5}


def test_toll_paid_with_coin_spends_gold_and_opens_gate():
    res = resolve_world_cast(["coin"], _player(gold=3), dict(TOLL_GOBLIN), seed=1)
    assert _gold_delta(res) == -1  # one coin spent
    assert "queue_goblin_paid" in _flags(res)
    assert "defeat_entity" in _types(res)  # gate opens
    assert res["spell"]["player_hp_delta"] == 0  # no blood toll when you can pay


def test_toll_without_coin_costs_hp_but_still_passes():
    res = resolve_world_cast(["coin"], _player(gold=0), dict(TOLL_GOBLIN), seed=1)
    assert _gold_delta(res) == 0  # nothing to spend
    assert res["spell"]["player_hp_delta"] == -2  # paid in blood
    assert "queue_goblin_forced" in _flags(res)
    assert "defeat_entity" in _types(res)  # never soft-locks: still passes


def test_toll_bell_passes_free_and_opens_tollmaster_route():
    res = resolve_world_cast(["bell"], _player(gold=0), dict(TOLL_GOBLIN), seed=1)
    assert _gold_delta(res) == 0
    assert res["spell"]["player_hp_delta"] == 0  # ringing is free
    flags = _flags(res)
    assert "queue_goblin_paid" in flags and "tollmaster_route_open" in flags


def test_player_starts_with_spendable_coins():
    assert build_world()["player"]["gold"] >= 1


def test_enemy_defeat_drops_gold():
    tgt = {"id": "toll_wisp", "type": "enemy", "name": "Toll Wisp", "hp": 1, "max_hp": 5,
           "weakness": ["bone"], "resistance": []}
    res = resolve_world_cast(["bone"], _player(), tgt, seed=3)
    assert "defeat_entity" in _types(res)
    assert _gold_delta(res) >= 1  # coins drop on defeat


def test_world_exposes_items_and_quests_metadata():
    w = build_world()
    item_ids = {i["id"] for i in w["items"]}
    assert {"health_potion", "courage_draught", "monster_trophy", "fungus_spore"} <= item_ids
    quest_ids = {q["id"] for q in w["quests"]}
    assert {"road_patrol", "spore_sample", "quartermaster_kit"} <= quest_ids
    assert w["player"]["items"] == {} and w["player"]["quests"] == {}


def test_quest_giver_npcs_are_tagged():
    road = build_world()["areas"]["overworld"]["entities"]
    givers = {e["id"]: e["quest"] for e in road if e["type"] == "npc" and e.get("quest")}
    assert givers.get("watch_archer") == "road_patrol"
    assert givers.get("road_druid") == "spore_sample"
    assert givers.get("quartermaster") == "quartermaster_kit"


def test_enemy_defeat_drops_quest_items():
    tgt = {"id": "toll_wisp", "type": "enemy", "name": "Toll Wisp", "hp": 1, "max_hp": 5,
           "weakness": ["bone"], "resistance": []}
    res = resolve_world_cast(["bone"], _player(), tgt, seed=3)
    drops = [a["item"] for a in res["world_actions"] if a["type"] == "add_item"]
    assert "monster_trophy" in drops


def test_rune_mastery_steadies_chaos():
    tgt = {"id": "toll_wisp", "type": "enemy", "name": "Toll Wisp", "hp": 5, "max_hp": 5,
           "weakness": ["flame"], "resistance": []}
    raw = resolve_world_cast(["flame", "bone"], _player(), tgt, seed=4)
    steady = resolve_world_cast(
        ["flame", "bone"], _player(rune_mastery={"flame": 5, "bone": 5}), tgt, seed=4)

    assert steady["metadata"]["combat"]["rune_mastery"]["chaos_relief"] == 2
    assert steady["spell"]["chaos"] < raw["spell"]["chaos"]
    assert steady["spell"]["chaos"] >= 1


def test_gate_tourist_shares_healing_lunch_once():
    tourist = {"id": "gate_tourist", "type": "npc", "name": "Lost Tourist",
               "dialogue": "sandwiches"}
    helped = _player(hp=4, story_flags=["tourist_helped"])
    res = resolve_world_cast(["wave"], helped, tourist, seed=20)

    assert res["spell"]["spell_name"] == "Healing Lunch"
    heals = [a for a in res["world_actions"] if a["type"] == "heal_player"]
    assert heals and heals[0]["amount"] == helped["max_hp"]
    flags = [a["flag"] for a in res["world_actions"] if a["type"] == "set_story_flag"]
    assert "tourist_lunch_shared" in flags and "boss_ally_tourist" in flags

    # second visit: the lunch is a memory, not a refill
    again = resolve_world_cast(
        ["wave"], _player(story_flags=["tourist_helped", "tourist_lunch_shared"]),
        tourist, seed=20)
    assert again["spell"]["spell_name"] != "Healing Lunch"

    # never helped the tourist -> no lunch
    cold = resolve_world_cast(["wave"], _player(), tourist, seed=20)
    assert cold["spell"]["spell_name"] != "Healing Lunch"


def test_hunter_king_marks_boss_weak_point():
    boss = {"id": "calendar_beast", "type": "boss", "name": "Calendar Beast",
            "hp": 20, "max_hp": 24, "weakness": ["spiral", "eye"], "resistance": []}
    hunter = _player(goblin_class="hunter", evolved=True)
    res = resolve_world_cast(["eye"], hunter, boss, seed=21)

    reveals = [a for a in res["world_actions"] if a["type"] == "reveal_weakness"]
    assert reveals and reveals[0]["target_id"] == "calendar_beast"
    assert reveals[0]["weakness"]
    assert "weakness_revealed" in res["spell"]["status_effects"]

    # un-evolved hunter gets no reveal
    plain = resolve_world_cast(["eye"], _player(goblin_class="hunter"), boss, seed=21)
    assert not [a for a in plain["world_actions"] if a["type"] == "reveal_weakness"]


def test_boss_phase_action_carries_new_weakness():
    boss = {"id": "calendar_beast", "type": "boss", "name": "Calendar Beast",
            "hp": 17, "max_hp": 24, "weakness": ["spiral", "eye"], "resistance": []}
    res = resolve_world_cast(["spiral", "eye"], _player(), boss, seed=9)
    phase = [a for a in res["world_actions"] if a["type"] == "start_boss_phase"]
    assert phase
    assert phase[0]["target_id"] == "calendar_beast"
    assert phase[0]["weakness"] and phase[0]["resistance"] is not None


def test_drawn_cast_gets_damage_flourish():
    tgt = {"id": "toll_wisp", "type": "enemy", "name": "Toll Wisp", "hp": 9, "max_hp": 9,
           "weakness": ["flame"], "resistance": []}
    plain = resolve_world_cast(["flame"], _player(), tgt, seed=30)
    inked = resolve_world_cast(["flame"], _player(), tgt, seed=30, drawn=True)

    assert inked["metadata"]["combat"]["drawn"]["bonus_damage"] == 2
    assert inked["spell"]["enemy_hp_delta"] == plain["spell"]["enemy_hp_delta"] - 2
    assert "drawn_flourish" in inked["spell"]["status_effects"]
    assert "drawn" not in plain["metadata"]["combat"]


def test_boss_killing_blow_requires_drawn_spell():
    boss = {"id": "calendar_beast", "type": "boss", "name": "Calendar Beast",
            "hp": 1, "max_hp": 24, "weakness": ["leaf"], "resistance": []}
    undrawn = resolve_world_cast(["leaf", "spiral"], _player(), boss, seed=31)
    hp_actions = [a for a in undrawn["world_actions"] if a["type"] == "set_entity_hp"]
    assert hp_actions and hp_actions[0]["hp"] == 1  # clings on at 1 HP
    assert "boss_warded_undrawn" in undrawn["spell"]["status_effects"]
    assert not [a for a in undrawn["world_actions"] if a["type"] == "win_game"]
    assert any("hand-drawn" in a.get("text", "")
               for a in undrawn["world_actions"] if a["type"] == "add_journal_entry")

    inked = resolve_world_cast(["leaf", "spiral"], _player(), boss, seed=31, drawn=True)
    assert [a for a in inked["world_actions"] if a["type"] == "win_game"]
