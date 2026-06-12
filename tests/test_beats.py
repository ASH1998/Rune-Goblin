"""Story-beat registry + endpoint payload sanity (game_plans/story_plan.md)."""

import pytest

from rune_goblin import beats, dialogue, story
from rune_goblin.world import AREAS


@pytest.fixture(autouse=True)
def _no_dialogue_api(monkeypatch):
    """Keep tests offline: every LLM path falls back deterministically."""
    monkeypatch.setenv("RG_USE_DIALOGUE_API", "0")


def test_beat_ids_unique():
    ids = [b.id for b in beats.BEATS]
    assert len(ids) == len(set(ids))


def test_beat_areas_exist():
    for b in beats.BEATS:
        assert b.area in AREAS, f"beat {b.id} points at unknown area {b.area}"


def test_first_meet_beats_reference_real_entities():
    for b in beats.BEATS:
        if b.trigger != "first_meet":
            continue
        ids = {e.id for e in AREAS[b.area].entities}
        assert b.npc in ids, f"beat {b.id}: no entity {b.npc} in {b.area}"
        assert b.bark, f"beat {b.id} needs a deterministic bark fallback"
        assert b.speaker, f"beat {b.id} needs a speaker name"


def test_area_enter_beats_have_fallback_text():
    for b in beats.BEATS:
        if b.trigger == "area_enter":
            assert b.toast, f"beat {b.id} needs a fallback toast"
            assert b.journal, f"beat {b.id} needs a fallback journal line"


def test_beat_conditions_use_allowlisted_flags():
    for b in beats.BEATS:
        for f in (*b.requires, *b.requires_any, *b.forbids):
            assert story.is_allowed_flag(f), f"beat {b.id}: unknown flag {f}"


def test_every_area_has_an_entry_beat():
    entry_areas = {b.area for b in beats.BEATS if b.trigger == "area_enter"}
    assert entry_areas == set(AREAS), "every map needs at least one entry beat"


def test_gate_routing():
    helpers = set(story.HELPER_FLAGS)
    devour = set(story.DEVOUR_FLAGS)
    allies = beats.get_beat("gate_allies")
    debts = beats.get_beat("gate_debts")
    mixed = beats.get_beat("gate_mixed")
    clean = beats.get_beat("gate_clean")
    # pure helper run -> allies only
    flags = ["tourist_helped"]
    assert beats.beat_eligible(allies, flags)
    assert not beats.beat_eligible(debts, flags)
    assert not beats.beat_eligible(mixed, flags)
    assert not beats.beat_eligible(clean, flags)
    # pure debt run -> debts only
    flags = ["debt_accepted"]
    assert not beats.beat_eligible(allies, flags)
    assert beats.beat_eligible(debts, flags)
    assert not beats.beat_eligible(mixed, flags)
    # both -> mixed only
    flags = ["tourist_helped", "debt_accepted"]
    assert not beats.beat_eligible(allies, flags)
    assert not beats.beat_eligible(debts, flags)
    assert beats.beat_eligible(mixed, flags)
    # neither -> clean only
    assert beats.beat_eligible(clean, [])
    assert helpers and devour  # guards against table renames emptying the sets


def test_client_manifest_shape():
    manifest = beats.client_manifest()
    assert len(manifest) == len(beats.BEATS)
    for entry in manifest:
        assert entry["trigger"] in {"area_enter", "first_meet"}
        if entry["trigger"] == "first_meet":
            assert entry["npc"] and entry["radius"] >= 1
        # text never ships in the manifest; the endpoint owns it
        assert "toast" not in entry and "bark" not in entry


def test_generate_beat_fallback(monkeypatch):
    monkeypatch.setenv("RG_USE_DIALOGUE_API", "0")
    out = dialogue.generate_beat(beat_id="opening_bell", area="Goblin Toll Road",
                                 player={"story_flags": []})
    assert out["source"] == "fallback"
    assert out["story_toast"].startswith("The Calendar Bell rings thirteen")
    assert out["journal_entry"]
    assert out["suggested_story_flag"] == ""


def test_generate_beat_rechecks_conditions(monkeypatch):
    monkeypatch.setenv("RG_USE_DIALOGUE_API", "0")
    # gate ally bark without the earning flag -> skipped, not narrated
    out = dialogue.generate_beat(beat_id="meet_gate_tourist",
                                 area="Calendar Gate Approach",
                                 player={"story_flags": []})
    assert out.get("skip") is True
    # unknown beat -> skipped
    out = dialogue.generate_beat(beat_id="nope", area="x", player={})
    assert out.get("skip") is True


def test_sanitize_beat_clamps_and_routes_fields():
    bark_beat = beats.get_beat("meet_tourist")
    raw = {"story_toast": "should be dropped for barks",
           "npc_line": "Lost Tourist: " + "y" * 400,
           "journal_entry": "j" * 999, "suggested_story_flag": "tourist_helped"}
    out = dialogue.sanitize_beat(raw, bark_beat)
    assert out["story_toast"] == ""
    assert len(out["npc_line"]) <= dialogue.MAX_BARK
    assert len(out["journal_entry"]) <= dialogue.MAX_JOURNAL
    assert out["suggested_story_flag"] == ""

    area_beat = beats.get_beat("library_enter")
    out = dialogue.sanitize_beat({"npc_line": "drop me", "story_toast": "t" * 400}, area_beat)
    assert out["npc_line"] == ""
    assert len(out["story_toast"]) <= dialogue.MAX_TOAST


def test_world_payload_ships_beats():
    from rune_goblin.world import build_world

    w = build_world(seed=1, admin=False)
    assert w["story_beats"] == beats.client_manifest()
    assert w["player"]["beats_seen"] == []


def test_story_brief_is_plain_english():
    from rune_goblin.dialogue import _story_brief

    player = {"goblin_class": "rogue", "level": 2, "weapon": "coin_sling",
              "inventory": ["Calendar Shard"],
              "story_flags": ["tourist_helped", "queue_goblin_paid",
                              "calendar_shard_1_taken"]}
    brief = _story_brief(player, "The Wet Library")
    assert "Goblin Rogue" in brief and "Coin Sling" in brief
    assert "Calendar Key" in brief  # current objective named plainly
    assert "calmed the Lost Tourist" in brief
    # no raw internal keys leak to the model
    assert "tourist_helped" not in brief and "{" not in brief


def test_main_objective_progression():
    assert "Calendar Shard" in story.main_objective({})
    assert "Calendar Key" in story.main_objective(
        {"inventory": ["Calendar Shard"]})
    assert "Calendar Gate" in story.main_objective(
        {"inventory": ["Calendar Shard", "Calendar Key"]})
    assert "arena" in story.main_objective(
        {"inventory": ["Calendar Shard", "Calendar Key"],
         "story_flags": ["arena_approach_reached"]})
    assert "Defeat or repair" in story.main_objective(
        {"story_flags": ["calendar_beast_phase_2"]})
    assert "ending" in story.main_objective(
        {"story_flags": ["calendar_repaired"]})


def test_flag_gloss_covers_story_critical_flags():
    for f in (*story.HELPER_FLAGS, *story.DEVOUR_FLAGS):
        assert f in story.FLAG_GLOSS, f"missing gloss for {f}"
    for f, text in story.FLAG_GLOSS.items():
        assert story.is_allowed_flag(f)
        assert text.endswith(".") and "_" not in text


def test_shop_list_and_buy():
    from rune_goblin.world import resolve_shop

    player = {"gold": 5, "weapon_inventory": ["clerk_wand"], "story_flags": []}
    listing = resolve_shop(player, "market_merchant")
    ids = [o["id"] for o in listing["offers"]]
    assert ids == ["mirror_shield", "bell_staff", "river_thread", "bone_blade"]
    assert listing["world_actions"] == [] and listing["line"]

    buy = resolve_shop(player, "market_merchant", "mirror_shield")
    kinds = [a["type"] for a in buy["world_actions"]]
    assert {"add_gold", "add_weapon", "add_inventory"} <= set(kinds)
    gold_delta = next(a["amount"] for a in buy["world_actions"] if a["type"] == "add_gold")
    assert gold_delta == -4
    flags = {a["flag"] for a in buy["world_actions"] if a["type"] == "set_story_flag"}
    assert "weapon_bought" in flags and "calendar_repair_possible" in flags


def test_shop_denies_when_broke():
    from rune_goblin.world import resolve_shop

    player = {"gold": 1, "weapon_inventory": ["clerk_wand"], "story_flags": []}
    buy = resolve_shop(player, "market_merchant", "bell_staff")
    assert buy.get("denied") is True and buy["world_actions"] == []
    # cursed blade needs no gold but takes the debt instead
    cursed = resolve_shop(player, "market_merchant", "bone_blade")
    flags = {a["flag"] for a in cursed["world_actions"] if a["type"] == "set_story_flag"}
    assert "debt_accepted" in flags and "calendar_devour_pressure" in flags
    assert not any(a["type"] == "add_gold" for a in cursed["world_actions"])


def test_shop_secret_merchant_and_guards():
    from rune_goblin.world import resolve_shop

    player = {"gold": 9, "weapon_inventory": ["clerk_wand"], "story_flags": []}
    buy = resolve_shop(player, "secret_merchant", "coin_sling")
    flags = {a["flag"] for a in buy["world_actions"] if a["type"] == "set_story_flag"}
    assert {"secret_merchant_met", "tollmaster_route_open"} <= flags
    assert resolve_shop(player, "toll_goblin").get("error") == "not_a_merchant"
    owned = resolve_shop({"gold": 9, "weapon_inventory": ["coin_sling"]},
                         "secret_merchant", "coin_sling")
    assert owned["world_actions"][0]["type"] == "upgrade_weapon"


def test_rune_cast_purchase_charges_gold():
    from rune_goblin.world import resolve_world_cast

    target = {"id": "market_merchant", "type": "npc", "name": "Bone Market Merchant"}
    rich = {"gold": 5, "weapon_inventory": ["clerk_wand"], "inventory": [],
            "hp": 10, "max_hp": 10, "courage": 5, "max_courage": 9, "level": 2}
    out = resolve_world_cast(["coin"], rich, target, seed=7)
    kinds = [a["type"] for a in out["world_actions"]]
    assert "add_weapon" in kinds
    assert any(a["type"] == "add_gold" and a["amount"] == -4 for a in out["world_actions"])

    broke = dict(rich, gold=0)
    out = resolve_world_cast(["coin"], broke, target, seed=7)
    kinds = [a["type"] for a in out["world_actions"]]
    assert "add_weapon" not in kinds  # denied, no free weapon


def test_price_band_scales_with_stage_and_reputation():
    early = {"story_flags": [], "inventory": []}
    late = {"story_flags": ["arena_approach_reached", "calendar_shard_1_taken",
                            "calendar_key_found"],
            "inventory": ["Calendar Shard", "Calendar Key"]}
    lo_e, hi_e, anchor_e = story.price_band("mirror_shield", early)
    lo_l, hi_l, anchor_l = story.price_band("mirror_shield", late)
    assert anchor_l > anchor_e  # endgame markets gouge
    assert lo_e <= anchor_e <= hi_e and lo_l <= anchor_l <= hi_l
    # repaying debt earns a kinder price; carrying curses costs extra
    kind = story.price_band("mirror_shield", {"story_flags": ["debt_repaid"]})
    cursed = story.price_band("mirror_shield", {"story_flags": ["debt_accepted"]})
    assert kind[2] < cursed[2]
    # the Bone Blade is never priced in gold
    assert story.price_band("bone_blade", early) == (0, 0, 0)


def test_shop_prices_clamped_to_band(monkeypatch):
    from rune_goblin import dialogue as dlg

    offers = [{"id": "mirror_shield", "label": "Mirror Shield", "band": (3, 5, 4)}]
    monkeypatch.setenv("RG_USE_DIALOGUE_API", "1")
    monkeypatch.setattr(dlg, "_remote_chat", lambda messages: (
        '{"prices": [{"id": "mirror_shield", "price": 99, "reason": "Endgame tax."}]}'))
    out = dlg.generate_shop_prices(player={"story_flags": []},
                                   area="The Bone Market", offers=offers)
    assert out["mirror_shield"]["price"] == 5  # clamped to band hi
    assert out["mirror_shield"]["source"] == "model"
    # model off -> anchor fallback
    monkeypatch.setenv("RG_USE_DIALOGUE_API", "0")
    out = dlg.generate_shop_prices(player={}, area="x", offers=offers)
    assert out["mirror_shield"] == {"price": 4, "reason": "", "source": "fallback"}


def test_shop_buy_honors_quote_only_inside_band(monkeypatch):
    from rune_goblin.world import resolve_shop

    monkeypatch.setenv("RG_USE_DIALOGUE_API", "0")
    player = {"gold": 9, "weapon_inventory": ["clerk_wand"], "story_flags": []}
    lo, hi, anchor = story.price_band("mirror_shield", player)
    # in-band quote honored
    buy = resolve_shop(player, "market_merchant", "mirror_shield", quoted_price=hi)
    paid = next(a["amount"] for a in buy["world_actions"] if a["type"] == "add_gold")
    assert paid == -hi
    # forged out-of-band quote falls back to the anchor
    buy = resolve_shop(player, "market_merchant", "mirror_shield", quoted_price=1)
    paid = next(a["amount"] for a in buy["world_actions"] if a["type"] == "add_gold")
    assert paid == -anchor


def test_client_manifest_marks_major_beats():
    entries = {e["id"]: e for e in beats.client_manifest()}
    assert entries["opening_bell"]["major"] is True
    assert entries["arena_enter"]["major"] is True
    assert entries["gate_allies"]["major"] is True
    assert entries["meet_collector"]["major"] is True
    # ambient mood beats stay in the toast channel
    assert entries["caverns_enter"]["major"] is False
    assert entries["meet_tourist"]["major"] is False
