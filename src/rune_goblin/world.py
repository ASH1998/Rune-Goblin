"""The Rune Goblin RPG world: tile-map areas, entities, and cast resolution.

This is the authoritative game-world model for the free-roaming sandbox
(`app/rpg_app.py`). It defines several connected areas (an overworld hub plus
dungeons), the entities that live in them, and — crucially —
:func:`resolve_world_cast`, which turns a set of drawn/selected runes plus the
target the player is facing into a validated spell outcome *and* a list of
world actions (unlock a chest, open a door, heal an NPC, defeat an enemy…).

Movement and rendering happen client-side in JS; only cast resolution comes
here, so Python stays the spell engine and the balance authority.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field

from .engine import GameState, resolve_spell
from .runelang import ENEMIES, GLYPHS, find_combo, rune_matches
from .schema import SpellResult
from .vfx import enemy_sprite

# ---------------------------------------------------------------------------
# Tiles
# ---------------------------------------------------------------------------
# Terrain characters used in the ASCII maps below.
#   '#' wall   '.' floor   ',' floor (alt/decor)   '~' water/hazard
#   ' ' void (non-walkable, rendered dark)
WALKABLE = set(".,")
TILE_LEGEND = {"#": "wall", ".": "floor", ",": "floor_alt", "~": "hazard", " ": "void"}


@dataclass
class Entity:
    id: str
    type: str  # enemy|boss|npc|chest|locked_door|shrine|merchant|portal|powerup|story_object
    name: str
    x: int
    y: int
    sprite: str = "👾"
    state: str = "idle"
    blocking: bool = True
    hp: int = 0
    max_hp: int = 0
    weakness: list[str] = field(default_factory=list)
    resistance: list[str] = field(default_factory=list)
    mood: str = ""
    tags: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)  # runes/tags needed to interact
    loot: list[str] = field(default_factory=list)
    dialogue: str = ""
    target_area: str = ""  # for portals
    target_x: int = 0
    target_y: int = 0
    hint: str = ""  # short interaction hint shown to the player
    sprite_key: str = ""  # explicit client sprite (creature/deco), else type-mapped


@dataclass
class Area:
    id: str
    name: str
    biome: str
    mood: str
    rows: list[str]
    entities: list[Entity]
    spawn: tuple[int, int]


def _mob(eid, name, x, y, *, hp, weakness, resistance, sprite_key,
         mood="", boss=False) -> Entity:
    return Entity(
        id=eid, type="boss" if boss else "enemy", name=name, x=x, y=y,
        sprite=enemy_sprite(name), sprite_key=sprite_key, hp=hp, max_hp=hp,
        weakness=list(weakness), resistance=list(resistance), mood=mood,
        tags=["hostile"] + (["boss"] if boss else []),
        hint=("the floor's master — cast to fight" if boss else "cast a spell to fight"),
    )


def _enemy(eid: str, name: str, x: int, y: int, mood: str = "") -> Entity:
    e = ENEMIES[name]
    return Entity(
        id=eid, type="enemy", name=name, x=x, y=y, sprite=enemy_sprite(name),
        hp=e.max_hp, max_hp=e.max_hp, weakness=list(e.weakness),
        resistance=list(e.resistance), mood=mood or e.mood,
        tags=["hostile"], hint="cast a spell to fight",
    )


def _npc(eid, name, x, y, *, sprite_key, dialogue, hint) -> Entity:
    return Entity(id=eid, type="npc", name=name, x=x, y=y, sprite_key=sprite_key,
                  blocking=True, tags=["friendly"], dialogue=dialogue, hint=hint)


def _deco(eid, x, y, sprite_key, blocking=False) -> Entity:
    # decorations never block movement (avoids sealed paths / "stuck" feel)
    return Entity(id=eid, type="deco", name=sprite_key.replace("_", " "), x=x, y=y,
                  sprite_key=sprite_key, blocking=blocking, tags=["deco"])


# Ground clutter pool (small 64px deco + bushes/rocks) for filling the world.
_DECO_POOL = ["bush", "rock", "rock2", "d01", "d02", "d03", "d04", "d05", "d06",
              "d07", "d08", "d09", "d10", "d11", "d12", "d13", "d14", "d15"]


def _scatter_deco(area: Area, n: int, seed: int) -> None:
    """Sprinkle non-blocking decorations on free floor tiles to fill the map."""
    rng = random.Random(seed)
    rows = area.rows
    h, w = len(rows), len(rows[0])
    occupied = {(e.x, e.y) for e in area.entities}
    sx0, sy0 = area.spawn
    placed = idx = tries = 0
    while placed < n and tries < n * 40:
        tries += 1
        x, y = rng.randint(1, w - 2), rng.randint(1, h - 2)
        if rows[y][x] not in WALKABLE or (x, y) in occupied:
            continue
        if abs(x - sx0) <= 1 and abs(y - sy0) <= 1:
            continue
        occupied.add((x, y))
        area.entities.append(_deco(f"{area.id}_sc{idx}", x, y, rng.choice(_DECO_POOL)))
        idx += 1
        placed += 1


def _field(w: int, h: int, feats=()) -> list[str]:
    """A bordered open field. ``feats`` stamps (x, y, w, h, char) rectangles
    (e.g. ``~`` ponds) into the interior — never the border."""
    grid = [["#" if (y == 0 or y == h - 1 or x == 0 or x == w - 1) else "."
             for x in range(w)] for y in range(h)]
    for (fx, fy, fw, fh, ch) in feats:
        for yy in range(fy, fy + fh):
            for xx in range(fx, fx + fw):
                if 0 < yy < h - 1 and 0 < xx < w - 1:
                    grid[yy][xx] = ch
    return ["".join(r) for r in grid]


# ---------------------------------------------------------------------------
# Areas — big open fields dotted with ponds, creatures, NPCs and decorations.
# ---------------------------------------------------------------------------
def _build_areas() -> dict[str, Area]:
    overworld = Area(
        id="overworld", name="Goblin Toll Road", biome="toll_road", mood="impatient",
        rows=_field(30, 20, [(9, 5, 4, 3, "~"), (21, 13, 5, 3, "~")]),
        spawn=(3, 3),
        entities=[
            _enemy("toll_goblin", "Queue Goblin", 15, 9, "blocking the toll gate"),
            _mob("ember_sprite", "Ember Sprite", 25, 4, hp=6, weakness=["wave", "closed_circle"],
                 resistance=["flame"], sprite_key="fire_elemental", mood="crackling"),
            _mob("toll_wisp", "Toll Wisp", 5, 15, hp=5, weakness=["bone", "broken_mark"],
                 resistance=["jagged_line"], sprite_key="glowing_wisp", mood="flickering"),
            _npc("tourist", "Lost Tourist", 5, 6, sprite_key="magical_fairy",
                 dialogue="I lost my map. Soothe me (wave) and I'll bless your courage.",
                 hint="cast wave/leaf to comfort"),
            _npc("toll_pixie", "Toll Pixie", 16, 3, sprite_key="fluttering_pixie",
                 dialogue="The goblin hates bells and coins. Just saying.",
                 hint="a helpful hint about the gate goblin"),
            _npc("road_druid", "Road Druid", 24, 17, sprite_key="expert_druid",
                 dialogue="Two doors west and east. The Library hides a Calendar Key.",
                 hint="cast leaf and I may share growth"),
            Entity("road_chest", "chest", "Roadside Chest", 27, 16, sprite="🧰",
                   state="locked", tags=["wood"], requires=["key"],
                   loot=["spare courage"], hint="locked — needs a key rune"),
            Entity("coin_chest", "chest", "Toll Coffer", 3, 17, sprite="🧰",
                   state="locked", tags=["coin"], requires=["coin"],
                   loot=["lucky coin"], hint="locked — pay with a coin rune"),
            Entity("toll_shrine", "shrine", "Mile-Marker Shrine", 14, 3, sprite="⛩️",
                   blocking=True, tags=["holy"], state="dormant",
                   hint="cast leaf/closed_circle to bless yourself"),
            Entity("portal_caverns", "portal", "Cavern Mouth", 2, 10, sprite="🕳️",
                   blocking=False, target_area="caverns", target_x=3, target_y=2,
                   hint="step in → Mirror Fungus Caverns"),
            Entity("portal_library", "portal", "Soggy Archway", 28, 9, sprite="🌀",
                   blocking=False, target_area="library", target_x=3, target_y=2,
                   hint="step in → The Wet Library"),
            _deco("o_tree1", 8, 11, "tree"), _deco("o_tree2", 20, 4, "tree"),
            _deco("o_tree3", 12, 16, "tree"), _deco("o_rock1", 18, 16, "rock"),
            _deco("o_rock2", 7, 3, "rock2"),
            _deco("o_bush1", 6, 13, "bush", blocking=False),
            _deco("o_bush2", 22, 8, "bush", blocking=False),
            _deco("o_bush3", 11, 3, "bush", blocking=False),
            _deco("o_bush4", 25, 11, "bush", blocking=False),
        ],
    )

    caverns = Area(
        id="caverns", name="Mirror Fungus Caverns", biome="cavern", mood="suspiciously moist",
        rows=_field(28, 18, [(6, 3, 3, 3, "~"), (18, 10, 4, 3, "~"), (12, 7, 3, 2, "~")]),
        spawn=(3, 2),
        entities=[
            _mob("fungus_a", "Mirror Fungus", 9, 8, hp=5, weakness=["mirror", "eye"],
                 resistance=["jagged_line"], sprite_key="glowing_wisp", mood="reflective"),
            _mob("fungus_b", "Mirror Fungus", 15, 5, hp=5, weakness=["mirror", "eye"],
                 resistance=["jagged_line"], sprite_key="glowing_wisp", mood="reflective"),
            _mob("fungus_c", "Mirror Fungus", 24, 11, hp=5, weakness=["mirror", "eye"],
                 resistance=["jagged_line"], sprite_key="glowing_wisp", mood="reflective"),
            _mob("drip_horror", "Drip Horror", 23, 3, hp=7, weakness=["jagged_line", "bone"],
                 resistance=["flame"], sprite_key="water_elemental", mood="sloshing"),
            _mob("cave_golem", "Mossy Golem", 6, 13, hp=8, weakness=["flame", "jagged_line"],
                 resistance=["wave", "thread"], sprite_key="earth_elemental", mood="grinding"),
            _npc("cave_hermit", "Cave Hermit", 4, 15, sprite_key="grizzled_treant",
                 dialogue="The mirrors fear themselves. Reflect them (mirror) to win.",
                 hint="a mossy hint about the fungus"),
            Entity("cavern_chest", "chest", "Spore Coffer", 24, 14, sprite="🧰",
                   state="locked", tags=["fungal"], requires=["flame", "key"],
                   loot=["jar of teeth", "minor powerup"], hint="locked — flame or key"),
            Entity("cavern_shrine", "shrine", "Dripping Shrine", 13, 9, sprite="⛩️",
                   blocking=True, tags=["holy"], state="dormant",
                   hint="cast leaf to heal at the shrine"),
            Entity("portal_home_c", "portal", "Cave Exit", 2, 16, sprite="🚪",
                   blocking=False, target_area="overworld", target_x=2, target_y=10,
                   hint="step out → Toll Road"),
            _deco("c_rock1", 10, 3, "rock"), _deco("c_rock2", 16, 13, "rock2"),
            _deco("c_bush1", 5, 6, "bush", blocking=False),
            _deco("c_bush2", 20, 7, "bush", blocking=False),
        ],
    )

    library = Area(
        id="library", name="The Wet Library", biome="library", mood="overdue and damp",
        rows=_field(28, 18, [(13, 0, 2, 8, "#"), (8, 7, 3, 2, "~")]),
        spawn=(3, 2),
        entities=[
            _mob("pdf_a", "PDF Wraith", 17, 4, hp=6, weakness=["mirror", "bell"],
                 resistance=["tooth"], sprite_key="vile_witch", mood="compressed"),
            _mob("tax_wraith", "Tax Wraith", 22, 13, hp=7, weakness=["coin", "key"],
                 resistance=["bone"], sprite_key="adept_necromancer", mood="audit-hungry"),
            _mob("mold_knight", "Mold Knight", 6, 12, hp=7, weakness=["leaf", "flame"],
                 resistance=["wave"], sprite_key="corrupted_treant", mood="damply chivalrous"),
            _npc("librarian", "Mold Librarian", 3, 4, sprite_key="expert_druid",
                 dialogue="The Ink-Locked Chest hides the Calendar Key. Reveal it with eye+mirror.",
                 hint="cast eye/mirror to learn the chest's secret"),
            _npc("lost_wisp", "Index Wisp", 24, 3, sprite_key="glowing_wisp",
                 dialogue="The east gate is sealed. Only the Calendar Key opens it.",
                 hint="a glowing hint about the gate"),
            Entity("emotional_door", "locked_door", "Emotional Door", 14, 8, sprite="🚪",
                   state="locked", blocking=True, tags=["door", "feelings"],
                   requires=["wave", "key"], hint="locked — calm it with wave+key"),
            Entity("ink_chest", "chest", "Ink-Locked Chest", 20, 9, sprite="🗃️",
                   state="locked", blocking=True, tags=["ink", "locked"],
                   requires=["key", "eye", "wave"], loot=["Calendar Key"],
                   hint="needs key + eye + wave"),
            Entity("lib_powerup", "powerup", "Bottled Focus", 24, 6, sprite="✨",
                   blocking=False, tags=["powerup"], loot=["Bottled Focus"],
                   state="idle", hint="walk over it to grab"),
            Entity("portal_home_l", "portal", "Library Exit", 2, 15, sprite="🚪",
                   blocking=False, target_area="overworld", target_x=28, target_y=9,
                   hint="step out → Toll Road"),
            Entity("portal_arena", "portal", "Calendar Gate", 25, 9, sprite="🌀",
                   blocking=True, state="locked", target_area="arena",
                   target_x=11, target_y=13, requires=["Calendar Key"],
                   hint="sealed — needs the Calendar Key"),
            _deco("l_tree1", 9, 12, "tree"), _deco("l_tree2", 18, 14, "tree"),
            _deco("l_bush1", 6, 8, "bush", blocking=False),
            _deco("l_bush2", 21, 5, "bush", blocking=False),
        ],
    )

    arena = Area(
        id="arena", name="Calendar Beast Arena", biome="arena", mood="overbooked",
        rows=_field(24, 16),
        spawn=(11, 13),
        entities=[
            _mob("calendar_beast", "Calendar Beast", 11, 3, hp=24, boss=True,
                 weakness=["spiral", "eye"], resistance=["flame"],
                 sprite_key="adept_necromancer", mood="overbooked and furious"),
            Entity("portal_home_a", "portal", "Arena Exit", 1, 14, sprite="🚪",
                   blocking=False, target_area="library", target_x=25, target_y=9,
                   hint="flee → The Wet Library"),
            _deco("a_rock1", 3, 3, "rock"), _deco("a_rock2", 20, 3, "rock2"),
            _deco("a_rock3", 3, 12, "rock2"), _deco("a_rock4", 20, 12, "rock"),
        ],
    )

    _scatter_deco(overworld, 26, 11)
    _scatter_deco(caverns, 18, 22)
    _scatter_deco(library, 16, 33)
    _scatter_deco(arena, 10, 44)
    return {a.id: a for a in (overworld, caverns, library, arena)}


AREAS: dict[str, Area] = _build_areas()
START_AREA = "overworld"


def _normalize_rows(rows: list[str]) -> list[str]:
    """Authoring maps embed entity-marker letters; turn anything that isn't
    real terrain into plain floor (entities are positioned by explicit coords)."""
    terrain = "#.,~ "
    return ["".join(ch if ch in terrain else "." for ch in row) for row in rows]


def _area_to_dict(area: Area) -> dict:
    rows = _normalize_rows(area.rows)
    return {
        "id": area.id,
        "name": area.name,
        "biome": area.biome,
        "mood": area.mood,
        "rows": rows,
        "width": len(rows[0]),
        "height": len(rows),
        "spawn": list(area.spawn),
        "entities": [asdict(e) for e in area.entities],
    }


def _reachable(norm: list[str], spawn: tuple[int, int], blocked: set[tuple[int, int]]) -> set:
    """BFS over walkable tiles from spawn, treating blocked tiles as obstacles."""
    h, wdt = len(norm), len(norm[0])
    sx, sy = spawn
    seen = {(sx, sy)}
    stack = [(sx, sy)]
    while stack:
        x, y = stack.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < wdt and 0 <= ny < h and (nx, ny) not in seen \
                    and norm[ny][nx] in WALKABLE and (nx, ny) not in blocked:
                seen.add((nx, ny))
                stack.append((nx, ny))
    return seen


def validate_world() -> list[str]:
    """Return a list of placement/reachability problems (empty == all good)."""
    problems: list[str] = []
    for a in AREAS.values():
        norm = _normalize_rows(a.rows)
        h, wdt = len(norm), len(norm[0])
        sx, sy = a.spawn
        if any(len(r) != wdt for r in norm):
            problems.append(f"{a.id}: ragged map")
        if not (0 <= sy < h and 0 <= sx < wdt and norm[sy][sx] in WALKABLE):
            problems.append(f"{a.id}: spawn {a.spawn} not walkable")
            continue
        for e in a.entities:
            if not (0 <= e.y < h and 0 <= e.x < wdt):
                problems.append(f"{a.id}/{e.id}: ({e.x},{e.y}) out of bounds")
            elif norm[e.y][e.x] not in WALKABLE:
                problems.append(f"{a.id}/{e.id}: on '{norm[e.y][e.x]}' at ({e.x},{e.y})")
        # reachability: blocking entities are obstacles
        blocked = {(e.x, e.y) for e in a.entities if e.blocking}
        reach = _reachable(norm, a.spawn, blocked)
        for e in a.entities:
            if (e.x, e.y) in problems:
                continue
            if not e.blocking:  # stepped onto (portal/powerup): tile itself must be reachable
                if (e.x, e.y) not in reach:
                    problems.append(f"{a.id}/{e.id}: unreachable tile ({e.x},{e.y})")
            else:  # interacted with from an adjacent tile
                adj = [(e.x + dx, e.y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
                if not any(p in reach for p in adj):
                    problems.append(f"{a.id}/{e.id}: no reachable neighbour ({e.x},{e.y})")
    return problems


def build_world() -> dict:
    """Full serializable world for the client."""
    return {
        "start_area": START_AREA,
        "areas": {aid: _area_to_dict(a) for aid, a in AREAS.items()},
        "player": {
            "hp": 12, "max_hp": 12, "courage": 5, "max_courage": 9,
            "inventory": ["wet candle"], "score": 0, "statuses": [],
        },
        "runes": [{"key": k, "symbol": g.symbol, "label": g.label,
                   "meanings": list(g.meanings)} for k, g in GLYPHS.items()],
        "walkable": "".join(sorted(WALKABLE)),
    }


# ---------------------------------------------------------------------------
# Cast resolution: runes + target -> spell outcome + world actions
# ---------------------------------------------------------------------------
def _matches_requirement(runes: list[str], requires: list[str], inventory: list[str]) -> bool:
    """True if the runes (or a held item) satisfy a requires list."""
    if not requires:
        return True
    have = set(runes)
    inv = {i for i in inventory}
    for req in requires:
        if req in inv:  # an item key like "Calendar Key"
            continue
        if req in have or any(rune_matches(r, (req,)) for r in runes):
            continue
        return False
    return True


_NPC_GIFTS = {
    "wave": ("blessed", "The NPC calms and blesses your courage.", "courage", 2),
    "leaf": ("healed", "Green light knits a small wound. +HP.", "hp", 3),
}


def _flavor_world(runes: list[str], target: dict | None, combo) -> str:
    glyphs = ", ".join(GLYPHS[r].label.lower() for r in runes if r in GLYPHS) or "static"
    if target:
        return f"Your {glyphs} spell coils toward the {target.get('name', 'air').lower()}."
    return f"A spell of {glyphs} fizzes harmlessly into the {('damp ' if combo else '')}air."


def resolve_world_cast(
    runes: list[str],
    player: dict,
    target: dict | None,
    seed: int | None = None,
) -> dict:
    """Resolve a cast against a target entity (or empty air).

    Returns ``{spell, world_actions, target_id, runes}`` where ``spell`` is a
    validated :class:`SpellResult` dict and ``world_actions`` is a list of
    ``{type, ...}`` dicts the client applies to its world copy.
    """
    rng = random.Random(seed)
    runes = [r for r in runes if r in GLYPHS]
    inventory = list(player.get("inventory", []))
    actions: list[dict] = []
    combo = find_combo(runes)

    if not runes:
        spell = SpellResult(
            spell_name="Damp Misfire", spell_type="fallback",
            flavor="The runes refuse to cooperate.", effect="Nothing happens.",
            chaos=1,
        )
        return {"spell": spell.model_dump(), "world_actions": [], "target_id": None, "runes": []}

    ttype = (target or {}).get("type")
    tid = (target or {}).get("id")

    # --- combat: enemy / boss ---------------------------------------------
    if ttype in {"enemy", "boss"}:
        state = GameState(
            player_hp=player.get("hp", 10), player_max_hp=player.get("max_hp", 10),
            enemy_name=target.get("name", "Mirror Fungus"),
            enemy_hp=target.get("hp", 5), enemy_max_hp=target.get("max_hp", 5),
            room_mood=target.get("mood", ""), inventory=tuple(inventory),
            courage=player.get("courage", 5),
            weakness_override=tuple(target.get("weakness") or ()),
            resistance_override=tuple(target.get("resistance") or ()),
        )
        spell = resolve_spell(state, runes, seed=seed)
        new_hp = max(0, target.get("hp", 5) + spell.enemy_hp_delta)
        actions.append({"type": "set_entity_hp", "target_id": tid, "hp": new_hp})
        if new_hp <= 0:
            actions.append({"type": "defeat_entity", "target_id": tid})
            if ttype == "boss":
                actions.append({"type": "win_game"})
        return {"spell": spell.model_dump(), "world_actions": actions,
                "target_id": tid, "runes": runes}

    # --- chest -------------------------------------------------------------
    if ttype == "chest":
        requires = target.get("requires", [])
        if target.get("state") == "open":
            effect = "The chest is already open and slightly smug about it."
            spell = SpellResult(spell_name="Redundant Knock", effect=effect, chaos=1)
            return {"spell": spell.model_dump(), "world_actions": [], "target_id": tid, "runes": runes}
        if _matches_requirement(runes, requires, inventory):
            loot = target.get("loot", [])
            actions.append({"type": "set_entity_state", "target_id": tid, "state": "open"})
            actions.append({"type": "set_entity_blocking", "target_id": tid, "blocking": False})
            for item in loot:
                actions.append({"type": "add_inventory", "item": item})
            effect = f"The lock surrenders. You find: {', '.join(loot) or 'dust'}."
            name = "Cursed Refund Bell" if "bell" in runes else "Tumbler's Lament"
            spell = SpellResult(
                spell_name=name, spell_type="unlock",
                flavor=_flavor_world(runes, target, combo), effect=effect,
                status_effects=["chest_unlocked"], chaos=4,
            )
        else:
            need = " + ".join(requires)
            spell = SpellResult(
                spell_name="Stubborn Tumbler", spell_type="unlock",
                flavor=_flavor_world(runes, target, combo),
                effect=f"The lock holds. It wants: {need}.", chaos=2,
            )
        return {"spell": spell.model_dump(), "world_actions": actions, "target_id": tid, "runes": runes}

    # --- locked door / portal seal ----------------------------------------
    if ttype in {"locked_door", "portal"} and target.get("state") == "locked":
        requires = target.get("requires", [])
        forced = "broken_mark" in runes and "key" in runes
        if _matches_requirement(runes, requires, inventory) or forced:
            actions.append({"type": "set_entity_state", "target_id": tid, "state": "open"})
            actions.append({"type": "set_entity_blocking", "target_id": tid, "blocking": False})
            side = "A small debt appears in your satchel." if forced else ""
            if forced:
                actions.append({"type": "add_inventory", "item": "small debt"})
            spell = SpellResult(
                spell_name="Emotional Unlocking" if not forced else "Forced Apology",
                spell_type="unlock_emotion", flavor=_flavor_world(runes, target, combo),
                effect="The way opens.", side_effect=side,
                status_effects=["door_unlocked"], chaos=5 if forced else 4,
            )
        else:
            spell = SpellResult(
                spell_name="Polite Refusal", spell_type="unlock_emotion",
                flavor=_flavor_world(runes, target, combo),
                effect=f"It stays shut. It needs: {' + '.join(requires)}.", chaos=2,
            )
        return {"spell": spell.model_dump(), "world_actions": actions, "target_id": tid, "runes": runes}

    # --- shrine ------------------------------------------------------------
    if ttype == "shrine":
        heal = 4 if any(r in {"leaf", "closed_circle"} for r in runes) else 2
        actions.append({"type": "heal_player", "amount": heal})
        actions.append({"type": "add_courage", "amount": 1})
        actions.append({"type": "set_entity_state", "target_id": tid, "state": "spent"})
        spell = SpellResult(
            spell_name="Mile-Marker Blessing", spell_type="shrine",
            flavor=_flavor_world(runes, target, combo),
            effect=f"Warmth restores {heal} HP and steadies your nerve.",
            player_hp_delta=heal, status_effects=["player_blessed"], chaos=3,
        )
        return {"spell": spell.model_dump(), "world_actions": actions, "target_id": tid, "runes": runes}

    # --- npc ---------------------------------------------------------------
    if ttype == "npc":
        gift = next((_NPC_GIFTS[r] for r in runes if r in _NPC_GIFTS), None)
        if gift:
            _, msg, kind, amt = gift
            if kind == "courage":
                actions.append({"type": "add_courage", "amount": amt})
            else:
                actions.append({"type": "heal_player", "amount": amt})
            actions.append({"type": "change_npc_trust", "target_id": tid, "delta": 1})
            spell = SpellResult(
                spell_name="Kindly Hex", spell_type="npc",
                flavor=_flavor_world(runes, target, combo), effect=msg,
                player_hp_delta=amt if kind == "hp" else 0,
                status_effects=["npc_charmed"], chaos=2,
            )
        else:
            fear = any(r in {"flame", "jagged_line", "bone", "tooth"} for r in runes)
            actions.append({"type": "change_npc_trust", "target_id": tid, "delta": -1 if fear else 0})
            effect = (target.get("dialogue") or "They blink at you.") if not fear \
                else "They recoil! Maybe lead with kindness next time."
            spell = SpellResult(
                spell_name="Awkward Overture" if fear else "Friendly Spark",
                spell_type="npc", flavor=_flavor_world(runes, target, combo),
                effect=effect, status_effects=["npc_scared"] if fear else [], chaos=1,
            )
        return {"spell": spell.model_dump(), "world_actions": actions, "target_id": tid, "runes": runes}

    # --- empty air / self-cast --------------------------------------------
    heal = sum(GLYPHS[r].heal for r in runes)
    statuses = [GLYPHS[r].status for r in runes if GLYPHS[r].status and GLYPHS[r].status.startswith("player")]
    if heal:
        actions.append({"type": "heal_player", "amount": heal})
    spell = SpellResult(
        spell_name=_air_name(rng, runes), spell_type="self" if heal or statuses else "whiff",
        flavor=_flavor_world(runes, None, combo),
        effect=(f"You patch yourself for {heal} HP." if heal else
                "The spell dissipates with a disappointed pop."),
        player_hp_delta=heal, status_effects=statuses, chaos=2 + len(runes),
    )
    return {"spell": spell.model_dump(), "world_actions": actions, "target_id": None, "runes": runes}


_AIR_ADJ = ["Wandering", "Pointless", "Ambient", "Speculative", "Premature"]
_AIR_NOUN = ["Sparkle", "Whiff", "Gesture", "Incantation", "Doodle"]


def _air_name(rng: random.Random, runes: list[str]) -> str:
    return f"{rng.choice(_AIR_ADJ)} {rng.choice(_AIR_NOUN)}"
