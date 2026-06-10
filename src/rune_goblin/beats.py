"""LLM-triggered story beats for Rune Goblin.

A *story beat* is a proactive narrative moment the game fires WITHOUT the
player pressing Talk: entering an area for the first time, walking near an
NPC they have never met, or arriving at the gate with consequences in tow.

Design (per ``game_plans/story_plan.md`` "Core Story Loop"):

* Triggers are **deterministic and client-evaluated** — the world payload
  ships a manifest of beats (id + trigger + conditions) and the browser fires
  each at most once, tracked in ``player.beats_seen``.
* Text is **LLM-enriched, fallback-guaranteed** — ``/rg/story_beat`` asks the
  dialogue model to write the moment in-voice; if the model is absent or
  misbehaves the deterministic ``toast``/``bark``/``journal`` lines below are
  used. A beat never blocks play and never sets story flags.
* Conditions read only allowlisted story flags (:data:`story.ALLOWED_FLAGS`)
  so a beat can pay off earlier choices (gate allies vs. gate debts).

Trigger kinds:

* ``area_enter`` — fires once when the player enters the area and the flag
  conditions hold. Narrator voice: text lands in ``story_toast`` + journal.
* ``first_meet`` — fires once when the player first comes within ``radius``
  tiles of entity ``npc`` in ``area``. Character voice: text lands in
  ``npc_line`` and is drawn as a speech bubble over the entity.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import story


@dataclass(frozen=True)
class StoryBeat:
    id: str
    trigger: str                  # "area_enter" | "first_meet"
    area: str                     # world area id this beat belongs to
    npc: str = ""                 # entity id (first_meet only)
    radius: int = 3               # proximity in tiles (first_meet only)
    requires: tuple[str, ...] = ()      # every flag must be present
    requires_any: tuple[str, ...] = ()  # at least one must be present
    forbids: tuple[str, ...] = ()       # none may be present
    prompt: str = ""              # narrative direction handed to the LLM
    toast: str = ""               # deterministic fallback story_toast
    bark: str = ""                # deterministic fallback npc_line / bark
    journal: str = ""             # deterministic fallback journal entry
    speaker: str = ""             # display name; "" = narrator


_HELPERS = tuple(story.HELPER_FLAGS)
_DEVOUR = tuple(story.DEVOUR_FLAGS)


BEATS: tuple[StoryBeat, ...] = (
    # ------------------------------------------------------------------
    # Area-enter narration (one per map, story_plan.md campaign structure)
    # ------------------------------------------------------------------
    StoryBeat(
        id="opening_bell", trigger="area_enter", area="overworld",
        prompt=(
            "The very first moment of the game. The player, a junior spell "
            "clerk, just doodled a rune on a receipt and broke the dungeon "
            "calendar: the Calendar Bell rang thirteen times and the Calendar "
            "Beast woke under the Toll Road. Narrate the disaster in one "
            "vivid, funny line and point them toward the caverns for the "
            "first Calendar Shard."
        ),
        toast="The Calendar Bell rings thirteen times. Somewhere under the road, tomorrow wakes up hungry.",
        journal=("I broke the dungeon calendar. The road guards are treating "
                 "this as both a disaster and a staffing issue."),
    ),
    StoryBeat(
        id="caverns_enter", trigger="area_enter", area="caverns",
        prompt=(
            "The player descends into the Mirror Fungus Caverns hunting the "
            "first Calendar Shard. The fungus here copies hostile spells back "
            "at casters; mirrors remember. Set the mood and hint that brute "
            "force backfires down here."
        ),
        toast="The caverns glisten. Every surface is politely rehearsing your reflection.",
        journal=("The Mirror Fungus Caverns hold the first Calendar Shard. "
                 "The fungus copies repeated violence back at its sender."),
    ),
    StoryBeat(
        id="library_enter", trigger="area_enter", area="library",
        prompt=(
            "The player enters the Wet Library, where the Calendar Key is "
            "ink-locked and the books are damp, frightened, and legally "
            "witnesses. Hint that reading before stealing pays off."
        ),
        toast="The Wet Library drips in alphabetical order. The books watch you like witnesses.",
        journal=("The Wet Library hides the Calendar Key. It is ink-locked: "
                 "it opens for readers, not burglars."),
    ),
    StoryBeat(
        id="market_enter", trigger="area_enter", area="bone_market",
        prompt=(
            "The player walks into the Bone Market, an optional vendor den "
            "where prices are low because some are metaphorical. Weapons, "
            "refunds, and mistakes with handles are for sale; cursed deals "
            "are tracked by the story."
        ),
        toast="The Bone Market smells of bargains. Some of the price tags are watching you back.",
        journal=("The Bone Market sells weapons and cursed deals. Debts here "
                 "are remembered — and collected."),
    ),
    StoryBeat(
        id="sewer_enter", trigger="area_enter", area="clock_sewer",
        prompt=(
            "The player wades into the Clock Sewer. The water down here used "
            "to be a river and remembers its clean version. Hint that wave "
            "and leaf can restore the flow and earn a final ally."
        ),
        toast="The Clock Sewer ticks instead of dripping. The water remembers being a river.",
        journal=("The Clock Sewer can be repaired, not just survived: wave "
                 "and leaf can wake the clean water."),
    ),
    StoryBeat(
        id="frost_enter", trigger="area_enter", area="frost_pass",
        prompt=(
            "The player crosses Frostbite Pass, a bitter optional detour "
            "where even time moves slower out of stubbornness. One cold, "
            "funny line of mood."
        ),
        toast="Frostbite Pass greets you the way winter greets paperwork: slowly, and out of spite.",
        journal="Frostbite Pass is bitterly patient. Dress your spells warmly.",
    ),
    StoryBeat(
        id="foundry_enter", trigger="area_enter", area="ember_foundry",
        prompt=(
            "The player enters the Ember Foundry, overheated and proud, where "
            "old calendar pages are smelted into sparks. One hot, funny line "
            "of mood."
        ),
        toast="The Ember Foundry roars. Somewhere in the heat, last week is being melted down for parts.",
        journal="The Ember Foundry burns proudly. Flame is cheap here; care is not.",
    ),
    StoryBeat(
        id="arena_enter", trigger="area_enter", area="arena",
        prompt=(
            "The player steps into the Calendar Beast Arena for the final "
            "fight. The Beast is not evil — it is hungry for every tomorrow "
            "people keep wasting. Narrate the arrival with weight and one dry "
            "joke; the Beast's own intro line comes separately."
        ),
        toast="The arena is quiet the way an unpaid invoice is quiet. Under the floor, tomorrow holds its breath.",
        journal=("The Calendar Beast waits in the arena. It eats ignored "
                 "tomorrows. It learns repeated spells."),
    ),
    # ------------------------------------------------------------------
    # Gate Approach consequence narration (story_plan.md pre-boss moment)
    # ------------------------------------------------------------------
    StoryBeat(
        id="gate_allies", trigger="area_enter", area="gate_approach",
        requires_any=_HELPERS, forbids=_DEVOUR,
        prompt=(
            "The player reaches the Calendar Gate Approach having helped "
            "people: the listed story flags name who. Narrate that the "
            "people they helped got here first to stand with them."
        ),
        toast="The gate is crowded. Somehow, people you helped got here before you.",
        journal="Allies wait at the Calendar Gate. Kindness travelled faster than you did.",
    ),
    StoryBeat(
        id="gate_debts", trigger="area_enter", area="gate_approach",
        requires_any=_DEVOUR, forbids=_HELPERS,
        prompt=(
            "The player reaches the Calendar Gate Approach trailing debts, "
            "burned shelves or cursed deals (see flags). Narrate that the "
            "crowd at the gate is mostly consequences holding invoices."
        ),
        toast="The gate is crowded. Unfortunately, most of the crowd has invoices.",
        journal="Your shortcuts reached the Calendar Gate before you did, and they brought paperwork.",
    ),
    StoryBeat(
        id="gate_mixed", trigger="area_enter", area="gate_approach",
        requires_any=_HELPERS,  # plus at least one devour flag, checked below
        requires=(), forbids=(),
        prompt=(
            "The player reaches the Calendar Gate Approach with both kind "
            "deeds and debts behind them (see flags). Narrate that the gate "
            "remembers both their kindness and their shortcuts."
        ),
        toast="The gate remembers both your kindness and your shortcuts.",
        journal="The Calendar Gate keeps two ledgers on you. Both are full.",
    ),
    StoryBeat(
        id="gate_clean", trigger="area_enter", area="gate_approach",
        forbids=_HELPERS + _DEVOUR,
        prompt=(
            "The player reaches the Calendar Gate Approach having kept to "
            "themselves: no allies earned, no debts owed. Narrate the empty, "
            "echoing approach — the loop only knows them by their mistake."
        ),
        toast="The gate approach is empty. The loop knows you only by the bell you rang.",
        journal="No one waited at the gate. The calendar has only your signature to go on.",
    ),
    # ------------------------------------------------------------------
    # First-meet barks (proximity speech bubbles, character voice)
    # ------------------------------------------------------------------
    StoryBeat(
        id="meet_toll_goblin", trigger="first_meet", area="overworld",
        npc="toll_goblin", speaker="Queue Goblin", radius=4,
        prompt=("The player approaches the toll gate for the first time. The "
                "Queue Goblin blocks the road and demands the toll."),
        bark="Road's closed. Calendar's screaming. Toll is one coin, one apology, or one legally confusing spell.",
    ),
    StoryBeat(
        id="meet_tourist", trigger="first_meet", area="overworld",
        npc="tourist", speaker="Lost Tourist",
        prompt=("The player walks near the panicking Lost Tourist for the "
                "first time. Their map keeps biting them."),
        bark="Excuse me! Is this the road to Tuesday? My map keeps biting me.",
    ),
    StoryBeat(
        id="meet_archer", trigger="first_meet", area="overworld",
        npc="watch_archer", speaker="Blue Watch Archer",
        prompt=("The player passes the Blue Watch Archer, the tutorial "
                "mentor, for the first time. One brisk piece of advice."),
        bark="Face the thing you mean to bother. Runes are powerful, not polite.",
    ),
    StoryBeat(
        id="meet_druid", trigger="first_meet", area="overworld",
        npc="road_druid", speaker="Road Druid",
        prompt=("The player wanders near the Road Druid for the first time. "
                "Calm gardener energy about the broken calendar."),
        bark="Calendars are just gardens with numbers. Yours has weeds.",
    ),
    StoryBeat(
        id="meet_hermit", trigger="first_meet", area="caverns",
        npc="cave_hermit", speaker="Mirror Hermit",
        prompt=("The player meets the Mirror Hermit deep in the caverns. "
                "Cryptic but useful warning about the mirrors."),
        bark="Do not swing at mirrors unless you want a very accurate enemy.",
    ),
    StoryBeat(
        id="meet_librarian", trigger="first_meet", area="library",
        npc="librarian", speaker="Mold Librarian",
        prompt=("The player squelches into the Mold Librarian's archive for "
                "the first time. Stern, damp, protective of the books."),
        bark="Quiet. The books are damp, frightened, and legally witnesses.",
    ),
    StoryBeat(
        id="meet_merchant", trigger="first_meet", area="bone_market",
        npc="market_merchant", speaker="Bone Market Merchant", radius=4,
        prompt=("The player enters earshot of the Bone Market Merchant for "
                "the first time. Charming, predatory salesmanship."),
        bark="Welcome to the Bone Market. Prices are low because some are metaphorical.",
    ),
    StoryBeat(
        id="meet_water_spirit", trigger="first_meet", area="clock_sewer",
        npc="water_spirit", speaker="Water Spirit",
        prompt=("The player finds the Water Spirit in the sewer for the "
                "first time. Wistful ex-river energy."),
        bark="I used to be a river. Now I am a hallway with regrets.",
    ),
    StoryBeat(
        id="meet_collector", trigger="first_meet", area="gate_approach",
        npc="debt_collector", speaker="Debt Collector", radius=5,
        requires_any=("debt_accepted", "debt_deepened"), forbids=("debt_repaid",),
        prompt=("The Debt Collector has tracked the player to the gate over "
                "their unpaid shortcuts and cursed deals. Menacing accountancy."),
        bark="You opened three doors with one apology. I am here for the other two.",
    ),
    StoryBeat(
        id="meet_gate_tourist", trigger="first_meet", area="gate_approach",
        npc="gate_tourist", speaker="Lost Tourist",
        requires=("tourist_helped",),
        prompt=("The Lost Tourist the player once calmed has made it to the "
                "gate to support them before the final fight. Sandwiches."),
        bark="I found the arena! Bad news: it is awful. Good news: I packed sandwiches.",
    ),
    StoryBeat(
        id="meet_gate_librarian", trigger="first_meet", area="gate_approach",
        npc="gate_librarian", speaker="Mold Librarian",
        requires=("librarian_trust",),
        prompt=("The Mold Librarian came to the gate because the player "
                "listened and read. Dry, formal solidarity."),
        bark="For the record, I object to being eaten by an overdue date.",
    ),
    StoryBeat(
        id="meet_gate_water", trigger="first_meet", area="gate_approach",
        npc="gate_water_spirit", speaker="Water Spirit",
        requires_any=("clean_water_restored", "water_spirit_helped"),
        prompt=("The restored Water Spirit has flowed up to the gate to carry "
                "one kindness into the final room."),
        bark="The clean river enters the room.",
    ),
    StoryBeat(
        id="meet_gate_goblin", trigger="first_meet", area="gate_approach",
        npc="gate_queue_goblin", speaker="Queue Goblin",
        requires=("queue_goblin_paid",),
        prompt=("The Queue Goblin the player paid properly now stands at the "
                "gate, grudgingly on their side."),
        bark="I am only helping because the Beast owes toll.",
    ),
)

_BY_ID: dict[str, StoryBeat] = {b.id: b for b in BEATS}


def get_beat(beat_id: str) -> StoryBeat | None:
    return _BY_ID.get(beat_id or "")


def beat_eligible(beat: StoryBeat, flags) -> bool:
    """Server-side recheck of a beat's flag conditions (defense in depth)."""
    flagset = set(flags or ())
    if beat.requires and not all(f in flagset for f in beat.requires):
        return False
    if beat.requires_any and not (flagset & set(beat.requires_any)):
        return False
    if beat.forbids and (flagset & set(beat.forbids)):
        return False
    if beat.id == "gate_mixed" and not (flagset & set(_DEVOUR)):
        return False  # mixed needs a debt too; helpers alone is gate_allies
    return True


def client_manifest() -> list[dict]:
    """Trigger metadata for the world payload; text stays server-side."""
    out: list[dict] = []
    for b in BEATS:
        entry = {
            "id": b.id, "trigger": b.trigger, "area": b.area,
            "requires": list(b.requires), "requires_any": list(b.requires_any),
            "forbids": list(b.forbids),
        }
        if b.trigger == "first_meet":
            entry["npc"] = b.npc
            entry["radius"] = b.radius
        if b.id == "gate_mixed":
            # client mirrors the "needs a debt too" rule in beat_eligible
            entry["requires_any_2"] = list(_DEVOUR)
        out.append(entry)
    return out


def fallback_payload(beat: StoryBeat) -> dict:
    """Deterministic beat text in the dialogue payload shape (never stalls)."""
    return {
        "beat_id": beat.id,
        "kind": beat.trigger,
        "speaker": beat.speaker,
        "story_toast": beat.toast,
        "npc_line": beat.bark,
        "journal_entry": beat.journal,
        "suggested_story_flag": "",
        "mood_shift": "",
        "source": "fallback",
    }
