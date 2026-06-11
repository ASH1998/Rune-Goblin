"""Quests, collectible items and the turn-in economy for Rune Goblin.

This is the deterministic backbone of the new adventure loop:

* **Items** — stackable potions, monster trophies and quest materials, each with
  an icon and (for potions) a use effect. The player carries them in a counted
  bag (``player["items"]`` = ``{item_id: qty}``), distinct from the legacy
  narrative ``inventory`` list (Calendar Key, wet candle, …) which existing
  puzzle gates still rely on.
* **Monster drops** — every felled monster yields trophies/materials, so killing
  things feeds the quest economy.
* **Quests** — quest-giver NPCs hand out monster-hunt tasks; you bring back the
  drops and turn them in for equipment, potions, gold and XP.
* **Turn-in logic** — :func:`resolve_quest_talk` is a pure state machine over the
  player's quests + items; it returns the giver's line plus the same
  ``world_actions`` vocabulary the client already applies. Python stays the
  authority: the browser proposes a talk, this decides the consequence.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import story

# ---------------------------------------------------------------------------
# Items (potions / materials / trophies)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Item:
    id: str
    label: str
    kind: str  # "potion" | "material" | "trophy"
    icon: str  # emoji rendered in the bag UI
    desc: str
    heal: int = 0  # potion: HP restored on use
    courage: int = 0  # potion: courage restored on use
    shield: int = 0  # potion: shield turns granted on use


ITEMS: dict[str, Item] = {
    "health_potion": Item(
        "health_potion", "Health Potion", "potion", "🧪",
        "Restores 5 HP. Tastes of rust and optimism.", heal=5),
    "courage_draught": Item(
        "courage_draught", "Courage Draught", "potion", "⚗️",
        "Restores 4 courage. Mostly adrenaline and bad ideas.", courage=4),
    "monster_trophy": Item(
        "monster_trophy", "Monster Trophy", "trophy", "🦷",
        "Proof you bothered a monster into stopping. Quest-givers love these."),
    "fungus_spore": Item(
        "fungus_spore", "Fungus Spore", "material", "🍄",
        "A live spore from a Mirror Fungus. The Road Druid wants one."),
    "ward_salve": Item(
        "ward_salve", "Ward Salve", "potion", "🩹",
        "Grants a shield that absorbs the next 2 blows.", shield=2),
    "rune_grit": Item(
        "rune_grit", "Rune Grit", "material", "⛏️",
        "Abrasive rune-dust. The smith uses it to reforge weapons."),
    "warped_cog": Item(
        "warped_cog", "Warped Cog", "material", "⚙️",
        "A cog that remembers a better hour. Needed for high-tier reforging."),
}


def item_or_none(item_id: str) -> Item | None:
    return ITEMS.get(item_id or "")


def is_potion(item_id: str) -> bool:
    it = ITEMS.get(item_id or "")
    return bool(it and it.kind == "potion")


# ---------------------------------------------------------------------------
# Monster drops — what each felled enemy yields into the bag.
# Keyed first by entity id, then by display name (so spawned/duplicated mobs
# that share a name still drop). Every standard kill also yields a trophy.
# ---------------------------------------------------------------------------
_DROP_BY_ID: dict[str, tuple[str, ...]] = {
    "fungus_a": ("fungus_spore",),
    "fungus_b": ("fungus_spore",),
    "fungus_c": ("fungus_spore",),
}
_DROP_BY_NAME: dict[str, tuple[str, ...]] = {
    "Mirror Fungus": ("fungus_spore",),
}


def monster_drops(enemy_id: str, enemy_name: str = "") -> list[str]:
    """Item ids a defeated standard enemy drops (boss/toll gate excluded by caller)."""
    drops = ["monster_trophy"]
    drops += list(_DROP_BY_ID.get(enemy_id or "", ()))
    for extra in _DROP_BY_NAME.get(enemy_name or "", ()):
        if extra not in drops:
            drops.append(extra)
    return drops


# ---------------------------------------------------------------------------
# Quests
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Quest:
    id: str
    giver: str  # npc entity id
    title: str
    objective_item: str  # item id to collect
    count: int  # how many to bring
    pitch: str  # story line offered when the quest is accepted
    progress_line: str  # reminder while incomplete
    turnin_line: str  # story line on completion
    done_line: str  # post-completion thanks
    reward_items: tuple[str, ...] = ()  # potion/material ids granted
    reward_weapon: str = ""  # weapon id granted + auto-equipped
    reward_gold: int = 0
    reward_xp: int = 0


QUESTS: dict[str, Quest] = {
    "road_patrol": Quest(
        id="road_patrol", giver="watch_archer", title="Road Patrol",
        objective_item="monster_trophy", count=2,
        pitch="The road's crawling with broken-calendar vermin. Bring me 2 monster "
              "trophies and I'll requisition you some healing.",
        progress_line="Still {have}/{need} trophies. Hit something, bring proof.",
        turnin_line="Two trophies, properly bothered. Here — field potions, on the Watch.",
        done_line="The road's a little quieter thanks to you. Keep your potions handy.",
        reward_items=("health_potion", "health_potion"), reward_gold=6, reward_xp=8,
    ),
    "spore_sample": Quest(
        id="spore_sample", giver="road_druid", title="A Living Sample",
        objective_item="fungus_spore", count=1,
        pitch="The Mirror Fungus in the caverns remembers the old calendar. Bring me "
              "one live spore and I'll thread you something that mends.",
        progress_line="No spore yet. The fungus is in the Mirror Caverns — try mirror or eye.",
        turnin_line="A breathing spore. Take the River Thread — it binds wounds and water alike.",
        done_line="The spore is singing to the weeds. Your thread will hold.",
        reward_items=("courage_draught",), reward_weapon="river_thread", reward_xp=8,
    ),
    "quartermaster_kit": Quest(
        id="quartermaster_kit", giver="quartermaster", title="Proper Equipment",
        objective_item="monster_trophy", count=2,
        pitch="A clerk with a training wand? No. Bring me 2 monster trophies and I'll "
              "kit you out like someone who plans to survive.",
        progress_line="{have}/{need} trophies on the counter. Go thin the herd.",
        turnin_line="Quartermaster's seal of approval. Take the Bell Staff and a potion "
                    "for the road.",
        done_line="Need more gear? Bring me 2 trophies any time and I'll trade you a potion.",
        reward_items=("health_potion",), reward_weapon="bell_staff", reward_xp=10,
    ),
}

# After a giver's quest is done, some keep a repeatable trophy -> potion exchange.
REPEAT_EXCHANGE: dict[str, dict] = {
    "quartermaster": {"item": "monster_trophy", "count": 2,
                      "reward": "health_potion",
                      "line": "Two trophies for a potion. Pleasure doing business."},
}

# npc id -> quest id, for tagging entities + quick lookup.
QUEST_BY_GIVER: dict[str, str] = {q.giver: qid for qid, q in QUESTS.items()}


def is_quest_giver(npc_id: str) -> bool:
    return npc_id in QUEST_BY_GIVER


def quest_for_giver(npc_id: str) -> Quest | None:
    qid = QUEST_BY_GIVER.get(npc_id or "")
    return QUESTS.get(qid) if qid else None


def _have(player: dict, item_id: str) -> int:
    items = player.get("items") or {}
    try:
        return int(items.get(item_id, 0))
    except (TypeError, ValueError):
        return 0


def _reward_actions(quest: Quest) -> list[dict]:
    acts: list[dict] = []
    for item_id in quest.reward_items:
        acts.append({"type": "add_item", "item": item_id, "qty": 1})
    if quest.reward_weapon and quest.reward_weapon in story.WEAPONS:
        acts.append({"type": "add_weapon", "weapon": quest.reward_weapon})
        acts.append({"type": "add_inventory", "item": story.WEAPONS[quest.reward_weapon].label})
    if quest.reward_gold:
        acts.append({"type": "add_gold", "amount": quest.reward_gold})
    if quest.reward_xp:
        acts.append({"type": "add_xp", "amount": quest.reward_xp})
    return acts


def _reward_summary(quest: Quest) -> str:
    bits: list[str] = []
    for item_id in quest.reward_items:
        it = ITEMS.get(item_id)
        if it:
            bits.append(it.label)
    if quest.reward_weapon and quest.reward_weapon in story.WEAPONS:
        bits.append(story.WEAPONS[quest.reward_weapon].label)
    if quest.reward_gold:
        bits.append(f"{quest.reward_gold} coins")
    if quest.reward_xp:
        bits.append(f"{quest.reward_xp} XP")
    return ", ".join(bits)


def resolve_quest_talk(player: dict, npc_id: str) -> dict:
    """Pure state machine for talking to a quest-giver.

    Returns ``{name, line, world_actions, quest_id, quest_state, reward}``.
    ``quest_state`` is one of: ``offered`` (just accepted), ``progress``,
    ``turned_in`` (completed now), ``done`` (already completed), ``exchange``
    (repeatable turn-in), or ``none`` (npc is not a quest-giver).
    """
    quest = quest_for_giver(npc_id)
    voice = story.NPC_VOICES.get(npc_id)
    name = (voice.name if voice else npc_id) or "Quest Giver"
    if quest is None:
        return {"name": name, "line": "", "world_actions": [],
                "quest_id": "", "quest_state": "none", "reward": ""}

    quests_state = player.get("quests") or {}
    state = quests_state.get(quest.id)
    have = _have(player, quest.objective_item)
    obj_label = (ITEMS.get(quest.objective_item).label
                 if ITEMS.get(quest.objective_item) else quest.objective_item)

    # Not started yet -> offer and auto-accept.
    if state is None:
        return {
            "name": name, "line": quest.pitch,
            "world_actions": [
                {"type": "set_quest", "quest": quest.id, "state": "active",
                 "title": quest.title,
                 "log": f"{quest.title}: bring {quest.count} {obj_label} to {name}."},
                {"type": "add_journal_entry",
                 "text": f"{name} gave you a quest — {quest.title}: collect "
                         f"{quest.count} {obj_label}."},
            ],
            "quest_id": quest.id, "quest_state": "offered", "reward": "",
        }

    # Active -> turn in if the objective is met, else nudge.
    if state == "active":
        if have >= quest.count:
            actions: list[dict] = [
                {"type": "remove_item", "item": quest.objective_item, "qty": quest.count},
                {"type": "set_quest", "quest": quest.id, "state": "done",
                 "title": quest.title,
                 "log": f"{quest.title}: completed."},
            ]
            actions += _reward_actions(quest)
            actions.append({"type": "add_journal_entry",
                            "text": f"You completed {quest.title} for {name}. "
                                    f"Reward: {_reward_summary(quest)}."})
            return {
                "name": name,
                "line": f"{quest.turnin_line} ({_reward_summary(quest)})",
                "world_actions": actions, "quest_id": quest.id,
                "quest_state": "turned_in", "reward": _reward_summary(quest),
            }
        line = quest.progress_line.format(have=have, need=quest.count)
        return {"name": name, "line": line, "world_actions": [],
                "quest_id": quest.id, "quest_state": "progress", "reward": ""}

    # Completed -> optional repeatable exchange, else a thank-you.
    exch = REPEAT_EXCHANGE.get(npc_id)
    if exch and _have(player, exch["item"]) >= exch["count"]:
        reward_item = ITEMS.get(exch["reward"])
        actions = [
            {"type": "remove_item", "item": exch["item"], "qty": exch["count"]},
            {"type": "add_item", "item": exch["reward"], "qty": 1},
            {"type": "add_journal_entry",
             "text": f"You traded {exch['count']} {ITEMS[exch['item']].label} to {name} "
                     f"for a {reward_item.label if reward_item else exch['reward']}."},
        ]
        return {"name": name, "line": exch["line"], "world_actions": actions,
                "quest_id": quest.id, "quest_state": "exchange",
                "reward": reward_item.label if reward_item else exch["reward"]}
    return {"name": name, "line": quest.done_line, "world_actions": [],
            "quest_id": quest.id, "quest_state": "done", "reward": ""}


# ---------------------------------------------------------------------------
# Serialization for the client (mirrors world._weapon_to_dict).
# ---------------------------------------------------------------------------


def item_to_dict(it: Item) -> dict:
    return {
        "id": it.id, "label": it.label, "kind": it.kind, "icon": it.icon,
        "desc": it.desc, "heal": it.heal, "courage": it.courage,
    }


def items_payload() -> list[dict]:
    return [item_to_dict(it) for it in ITEMS.values()]


def quests_payload() -> list[dict]:
    """Lightweight quest metadata for the client (titles + givers + objectives)."""
    out = []
    for q in QUESTS.values():
        obj = ITEMS.get(q.objective_item)
        out.append({
            "id": q.id, "giver": q.giver, "title": q.title,
            "objective_item": q.objective_item,
            "objective_label": obj.label if obj else q.objective_item,
            "count": q.count,
        })
    return out
