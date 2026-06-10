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

import os
import random
from dataclasses import asdict, dataclass, field

from . import quests, story
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
    quest: str = ""  # quest id this NPC gives (tags quest-giver NPCs for the client)


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


def _npc(eid, name, x, y, *, sprite_key, dialogue, hint, quest="") -> Entity:
    tags = ["friendly"] + (["quest_giver"] if quest else [])
    return Entity(id=eid, type="npc", name=name, x=x, y=y, sprite_key=sprite_key,
                  blocking=True, tags=tags, dialogue=dialogue, hint=hint, quest=quest)


def _deco(eid, x, y, sprite_key, blocking=False) -> Entity:
    # decorations never block movement (avoids sealed paths / "stuck" feel)
    return Entity(id=eid, type="deco", name=sprite_key.replace("_", " "), x=x, y=y,
                  sprite_key=sprite_key, blocking=blocking, tags=["deco"])


def _story(eid, name, x, y, *, sprite_key, requires, dialogue, hint) -> Entity:
    return Entity(id=eid, type="story_object", name=name, x=x, y=y, sprite="✨",
                  sprite_key=sprite_key, blocking=True, tags=["story"],
                  requires=list(requires), dialogue=dialogue, hint=hint)


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


def _free_tiles(area: Area, *, margin_from_spawn: int = 2):
    """Yield (x, y) interior floor tiles not occupied by an entity."""
    rows = area.rows
    h, w = len(rows), len(rows[0])
    occupied = {(e.x, e.y) for e in area.entities}
    sx0, sy0 = area.spawn
    free = []
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            if rows[y][x] not in WALKABLE or (x, y) in occupied:
                continue
            if abs(x - sx0) <= margin_from_spawn and abs(y - sy0) <= margin_from_spawn:
                continue
            free.append((x, y))
    return free


def _scatter_buildings(area: Area, keys, n: int, seed: int, *, blocking=True,
                       spacing: int = 4) -> None:
    """Place ``n`` landmark building/prop sprites across free floor, spaced out."""
    rng = random.Random(seed)
    free = _free_tiles(area)
    rng.shuffle(free)
    placed_pts: list[tuple[int, int]] = [(e.x, e.y) for e in area.entities if e.blocking]
    idx = 0
    for (x, y) in free:
        if idx >= n:
            break
        if any(abs(x - px) + abs(y - py) < spacing for px, py in placed_pts):
            continue
        key = keys[idx % len(keys)]
        area.entities.append(_deco(f"{area.id}_bld{idx}", x, y, key, blocking=blocking))
        placed_pts.append((x, y))
        idx += 1


def _scatter_water_rocks(area: Area, n: int, seed: int) -> None:
    """Dot non-blocking animated water rocks beside the ponds for readability."""
    rng = random.Random(seed)
    rows = area.rows
    h, w = len(rows), len(rows[0])
    occupied = {(e.x, e.y) for e in area.entities}
    placed = idx = tries = 0
    while placed < n and tries < n * 40:
        tries += 1
        x, y = rng.randint(1, w - 2), rng.randint(1, h - 2)
        if rows[y][x] not in WALKABLE or (x, y) in occupied:
            continue
        # only next to water
        if not any(0 <= y + dy < h and 0 <= x + dx < w and rows[y + dy][x + dx] == "~"
                   for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
            continue
        occupied.add((x, y))
        area.entities.append(_deco(f"{area.id}_wr{idx}", x, y, "water_rocks"))
        idx += 1
        placed += 1


def _relocate_invalid(area: Area) -> None:
    """Move any entity that landed on a wall/pond/out-of-bounds to a free tile.

    Lets us safely enlarge maps and stamp new ponds without hand-checking every
    existing entity coordinate.
    """
    rows = area.rows
    h, w = len(rows), len(rows[0])
    occupied = {(e.x, e.y) for e in area.entities}

    def ok(x, y):
        return 0 < x < w - 1 and 0 < y < h - 1 and rows[y][x] in WALKABLE

    for e in area.entities:
        if ok(e.x, e.y) and sum(1 for o in area.entities if o.x == e.x and o.y == e.y) == 1:
            continue
        # spiral outward for the nearest free, unoccupied floor tile
        for r in range(1, max(h, w)):
            found = None
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    nx, ny = e.x + dx, e.y + dy
                    if ok(nx, ny) and (nx, ny) not in occupied:
                        found = (nx, ny)
                        break
                if found:
                    break
            if found:
                occupied.discard((e.x, e.y))
                e.x, e.y = found
                occupied.add(found)
                break


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
        rows=_field(48, 32, [(14, 9, 5, 3, "~"), (33, 21, 6, 4, "~"),
                             (9, 24, 4, 3, "~"), (24, 4, 3, 6, "#")]),
        spawn=(3, 3),
        entities=[
            _enemy("toll_goblin", "Queue Goblin", 20, 16, "blocking the toll gate"),
            _mob("ember_sprite", "Ember Sprite", 41, 5, hp=6, weakness=["wave", "closed_circle"],
                 resistance=["flame"], sprite_key="fire_elemental", mood="crackling"),
            _mob("toll_wisp", "Toll Wisp", 5, 18, hp=5, weakness=["bone", "broken_mark"],
                 resistance=["jagged_line"], sprite_key="glowing_wisp", mood="flickering"),
            _mob("road_brute", "Road Enforcer", 30, 27, hp=7, weakness=["bell", "coin"],
                 resistance=["flame"], sprite_key="red_warrior", mood="enforcing the toll"),
            _npc("tourist", "Lost Tourist", 5, 6, sprite_key="magical_fairy",
                 dialogue="I lost my map. Soothe me (wave) and I'll bless your courage.",
                 hint="cast wave/leaf to comfort"),
            _npc("toll_pixie", "Toll Pixie", 16, 3, sprite_key="fluttering_pixie",
                 dialogue="The goblin hates bells and coins. Just saying.",
                 hint="a helpful hint about the gate goblin"),
            _npc("road_druid", "Road Druid", 41, 27, sprite_key="expert_druid",
                 dialogue="Two doors west and east. The Library hides a Calendar Key. "
                          "Bring me a live fungus spore and I'll thread you something that mends.",
                 hint="talk (T) for a quest — a living sample", quest="spore_sample"),
            _npc("watch_archer", "Blue Watch Archer", 11, 24, sprite_key="blue_archer",
                 dialogue="Weaknesses matter. Face a creature, read its weak runes, then exploit them. "
                          "Clear some road vermin for me and I'll spare you potions.",
                 hint="talk (T) for a patrol quest", quest="road_patrol"),
            _npc("quartermaster", "Quartermaster Bramble", 35, 24, sprite_key="npc_pawn",
                 dialogue="Bring me monster trophies and I'll trade you proper equipment "
                          "and potions. A clerk needs more than a training wand.",
                 hint="talk (T) to turn trophies into gear", quest="quartermaster_kit"),
            _story("toll_board", "Toll Notice Board", 13, 6, sprite_key="goblin_house",
                   requires=["eye"], dialogue="The toll road ledger names three debts: fungus mirrors, wet books, and the Calendar Beast.",
                   hint="cast eye to read the road story"),
            Entity("road_chest", "chest", "Roadside Chest", 45, 27, sprite="🧰",
                   state="locked", tags=["wood"], requires=["key"],
                   loot=["spare courage"], hint="locked — needs a key rune"),
            Entity("coin_chest", "chest", "Toll Coffer", 3, 28, sprite="🧰",
                   state="locked", tags=["coin"], requires=["coin"],
                   loot=["lucky coin"], hint="locked — pay with a coin rune"),
            Entity("toll_shrine", "shrine", "Mile-Marker Shrine", 24, 3, sprite="⛩️",
                   blocking=True, tags=["holy"], state="dormant",
                   hint="cast leaf/closed_circle to bless yourself"),
            Entity("portal_caverns", "portal", "Cavern Mouth", 2, 14, sprite="🕳️",
                   blocking=False, target_area="caverns", target_x=3, target_y=2,
                   hint="step in → Mirror Fungus Caverns"),
            Entity("portal_library", "portal", "Soggy Archway", 45, 16, sprite="🌀",
                   blocking=False, target_area="library", target_x=3, target_y=2,
                   hint="step in → The Wet Library"),
            Entity("portal_market", "portal", "Bone Market Tunnel", 24, 30, sprite="🕳️",
                   state="locked", blocking=True, target_area="bone_market", target_x=2, target_y=2,
                   requires=["Debt Receipt"], tags=["shop", "shortcut"],
                   hint="sealed — needs Debt Receipt, coin+bell, or a forced cursed entrance"),
            Entity("portal_frost", "portal", "Frostbite Trail", 5, 27, sprite="🌀",
                   blocking=False, target_area="frost_pass", target_x=3, target_y=3,
                   hint="step in → Frostbite Pass"),
            Entity("portal_foundry_o", "portal", "Foundry Road", 43, 27, sprite="🕳️",
                   blocking=False, target_area="ember_foundry", target_x=3, target_y=3,
                   hint="step in → The Ember Foundry"),
            _story("bell_shrine", "Hidden Bell Shrine", 2, 2, sprite_key="shrine_tower",
                   requires=["bell", "coin"], dialogue="A buried shrine hums. The Tollmaster's route remembers those who pay and ring.",
                   hint="cast bell+coin to wake the secret shrine"),
            _deco("o_tree1", 8, 11, "tree"), _deco("o_tree2", 20, 4, "tree"),
            _deco("o_tree3", 12, 16, "tree"), _deco("o_rock1", 18, 16, "rock"),
            _deco("o_rock2", 7, 3, "rock2"),
            _deco("o_bridge1", 10, 8, "bridge_all"),
            _deco("o_sheep1", 6, 16, "happy_sheep"),
            _deco("o_house1", 4, 5, "goblin_house", blocking=True),
            _deco("o_tower1", 26, 7, "goblin_tower_red", blocking=True),
            _deco("o_bush1", 6, 13, "bush", blocking=False),
            _deco("o_bush2", 22, 8, "bush", blocking=False),
            _deco("o_bush3", 11, 3, "bush", blocking=False),
            _deco("o_bush4", 25, 11, "bush", blocking=False),
        ],
    )

    caverns = Area(
        id="caverns", name="Mirror Fungus Caverns", biome="cavern", mood="suspiciously moist",
        rows=_field(46, 32, [(8, 5, 4, 3, "~"), (24, 14, 5, 4, "~"),
                             (16, 10, 4, 2, "~"), (34, 6, 4, 4, "~"), (20, 22, 6, 3, "~")]),
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
            _mob("mycologist", "Mirror Mycologist", 40, 27, hp=9,
                 weakness=["mirror", "eye"], resistance=["jagged_line", "flame"],
                 sprite_key="deft_sorceress", mood="reflecting your regrets", boss=False),
            _npc("cave_hermit", "Mirror Hermit", 4, 15, sprite_key="grizzled_treant",
                 dialogue="The mirrors fear themselves. Reflect them (mirror) to win.",
                 hint="a mossy hint about the fungus"),
            _story("nursery", "Fungus Nursery", 10, 15, sprite_key="goblin_house",
                   requires=["mirror"], dialogue="The spores quiet under a mirror. Spared, the colony will whisper the Beast's fear.",
                   hint="cast mirror to spare the nursery (or flame to burn it)"),
            Entity("shard_chest", "chest", "Calendar Shard Vault", 43, 4, sprite="🗃️",
                   state="locked", blocking=True, tags=["fungal"],
                   requires=["mirror", "eye"], loot=["Calendar Shard"],
                   hint="locked — reveal with mirror + eye"),
            _story("cave_echo", "Echoing Mirror Stone", 12, 12, sprite_key="knight_tower_blue",
                   requires=["mirror", "eye"], dialogue="The stone repeats your last spell and reveals hidden weakness patterns.",
                   hint="cast mirror+eye to study the cave"),
            Entity("cavern_chest", "chest", "Spore Coffer", 24, 14, sprite="🧰",
                   state="locked", tags=["fungal"], requires=["flame", "key"],
                   loot=["jar of teeth", "minor powerup"], hint="locked — flame or key"),
            Entity("cavern_shrine", "shrine", "Dripping Shrine", 13, 9, sprite="⛩️",
                   blocking=True, tags=["holy"], state="dormant",
                   hint="cast leaf to heal at the shrine"),
            Entity("portal_home_c", "portal", "Cave Exit", 2, 29, sprite="🚪",
                   blocking=False, target_area="overworld", target_x=3, target_y=14,
                   hint="step out → Toll Road"),
            _deco("c_rock1", 10, 3, "rock"), _deco("c_rock2", 16, 13, "rock2"),
            _deco("c_bush1", 5, 6, "bush", blocking=False),
            _deco("c_bush2", 20, 7, "bush", blocking=False),
        ],
    )

    library = Area(
        id="library", name="The Wet Library", biome="library", mood="overdue and damp",
        rows=_field(50, 34, [(13, 0, 2, 13, "#"), (32, 21, 2, 13, "#"),
                             (8, 9, 4, 3, "~"), (30, 18, 6, 4, "~"), (40, 6, 4, 4, "~")]),
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
            _npc("red_guard", "Red Guard", 11, 5, sprite_key="red_warrior",
                 dialogue="The boss resists flame. Spiral and eye fold time around it.",
                 hint="cast spiral or eye for boss advice"),
            _story("wet_catalog", "Wet Card Catalog", 38, 8, sprite_key="goblin_house",
                   requires=["eye", "mirror"], dialogue="A smeared card points to the Ink-Locked Chest: key + eye + wave.",
                   hint="cast eye+mirror to decode the catalog"),
            _story("dry_shelves", "Dry Archive Shelves", 29, 5, sprite_key="wood_tower_building",
                   requires=["flame"], dialogue="The shelves burn into a shortcut. The librarian will remember this.",
                   hint="cast flame to burn a risky shortcut"),
            Entity("emotional_door", "locked_door", "Emotional Door", 16, 20, sprite="🚪",
                   state="locked", blocking=True, tags=["door", "feelings"],
                   requires=["wave", "key"], hint="locked — calm it with wave+key"),
            Entity("ink_chest", "chest", "Ink-Locked Chest", 45, 9, sprite="🗃️",
                   state="locked", blocking=True, tags=["ink", "locked"],
                   requires=["key", "eye", "wave"], loot=["Calendar Key"],
                   hint="needs key + eye + wave"),
            Entity("lib_powerup", "powerup", "Bottled Focus", 44, 5, sprite="✨",
                   blocking=False, tags=["powerup"], loot=["Bottled Focus"],
                   state="idle", hint="walk over it to grab"),
            Entity("library_shrine", "shrine", "Dry Joke Shrine", 20, 28, sprite="⛩️",
                   blocking=True, tags=["holy"], state="dormant",
                   hint="cast leaf/closed_circle to dry one good joke and heal"),
            Entity("portal_home_l", "portal", "Library Exit", 2, 31, sprite="🚪",
                   blocking=False, target_area="overworld", target_x=44, target_y=16,
                   hint="step out → Toll Road"),
            Entity("portal_arena", "portal", "Calendar Gate", 47, 16, sprite="🌀",
                   blocking=True, state="locked", target_area="gate_approach",
                   target_x=2, target_y=8, requires=["Calendar Key"],
                   hint="sealed — needs the Calendar Key"),
            Entity("portal_sewer", "portal", "Basement Stairs", 2, 20, sprite="🕳️",
                   blocking=False, target_area="clock_sewer", target_x=2, target_y=2,
                   hint="step down → The Clock Sewer"),
            _deco("l_tree1", 9, 12, "tree"), _deco("l_tree2", 18, 14, "tree"),
            _deco("l_bush1", 6, 8, "bush", blocking=False),
            _deco("l_bush2", 21, 5, "bush", blocking=False),
        ],
    )

    arena = Area(
        id="arena", name="Calendar Beast Arena", biome="arena", mood="overbooked",
        rows=_field(28, 22),
        spawn=(14, 18),
        entities=[
            _mob("calendar_beast", "Calendar Beast", 14, 4, hp=24, boss=True,
                 weakness=["spiral", "eye"], resistance=["flame"],
                 sprite_key="adept_necromancer", mood="overbooked and furious"),
            Entity("portal_home_a", "portal", "Arena Exit", 2, 20, sprite="🚪",
                   blocking=False, target_area="gate_approach", target_x=2, target_y=12,
                   hint="flee → Calendar Gate Approach"),
            _story("pylon_eye", "Eye Pylon", 5, 8, sprite_key="knight_tower_blue",
                   requires=["eye"], dialogue="The eye pylon lights; the Beast's weak point flickers into view.",
                   hint="cast eye to charge this pylon"),
            _story("pylon_mirror", "Mirror Pylon", 23, 8, sprite_key="knight_tower_blue",
                   requires=["mirror"], dialogue="The mirror pylon answers; the Beast must face itself.",
                   hint="cast mirror to charge this pylon"),
            _story("pylon_leaf", "Leaf Pylon", 5, 15, sprite_key="shrine_tower",
                   requires=["leaf"], dialogue="The leaf pylon greens; the calendar remembers how to grow.",
                   hint="cast leaf to charge this pylon"),
            _story("pylon_spiral", "Spiral Pylon", 23, 15, sprite_key="shrine_tower",
                   requires=["spiral"], dialogue="The spiral pylon turns; the Beast's schedule unravels.",
                   hint="cast spiral to charge this pylon"),
            _npc("arena_echo", "Arena Echo", 14, 20, sprite_key="glowing_wisp",
                 dialogue="The Beast changes when wounded. Vary your runes and watch the pylons.",
                 hint="last whisper before tomorrow chooses"),
            Entity("arena_shrine", "shrine", "Last Tomorrow Shrine", 14, 17, sprite="⛩️",
                   blocking=True, tags=["holy"], state="dormant",
                   hint="cast leaf/closed_circle for one final blessing"),
            _deco("a_castle1", 2, 2, "castle_destroyed", blocking=True),
            _deco("a_castle2", 23, 2, "black_castle", blocking=True),
            _deco("a_rock3", 3, 12, "rock2"), _deco("a_rock4", 24, 18, "rock"),
        ],
    )

    bone_market = Area(
        id="bone_market", name="The Bone Market", biome="market",
        mood="charmingly indebted",
        rows=_field(38, 28, [(16, 12, 5, 3, "~"), (28, 20, 4, 3, "#")]),
        spawn=(2, 2),
        entities=[
            _npc("market_merchant", "Bone Market Merchant", 19, 6,
                 sprite_key="vile_witch",
                 dialogue="I sell weapons, refunds, and mistakes with handles. Pay with coin to settle debts.",
                 hint="cast coin to trade / repay debt, or bell for the secret stock"),
            Entity("bone_chest", "chest", "Knife Rack", 6, 6, sprite="🗃️",
                   state="locked", blocking=True, tags=["market"], requires=["coin"],
                   loot=["bone_blade"], hint="locked — pay coin for the Bone Blade"),
            Entity("sling_chest", "chest", "Coin Stall", 33, 6, sprite="🗃️",
                   state="locked", blocking=True, tags=["market"], requires=["bell"],
                   loot=["coin_sling"], hint="locked — ring bell for the Coin Sling"),
            _story("debt_altar", "Debt Altar", 19, 16, sprite_key="goblin_tower_red",
                   requires=["coin"],
                   dialogue="The altar tallies what you forced open. Coin closes the account.",
                   hint="cast coin to repay your debts"),
            Entity("market_shrine", "shrine", "Refund Shrine", 12, 23, sprite="⛩️",
                   blocking=True, tags=["holy"], state="dormant",
                   hint="cast coin or closed_circle for a risky blessing"),
            _mob("market_brute", "Market Enforcer", 33, 24, hp=7,
                 weakness=["coin", "key"], resistance=["bone"],
                 sprite_key="adept_necromancer", mood="enforcing the spread"),
            _npc("secret_merchant", "Hooded Merchant", 4, 25, sprite_key="deft_sorceress",
                 dialogue="Psst. Coin and bell mastery? The Tollmaster's road is hiring.",
                 hint="cast coin+bell to meet the secret merchant"),
            Entity("portal_home_b", "portal", "Market Exit", 2, 25, sprite="🚪",
                   blocking=False, target_area="overworld", target_x=24, target_y=29,
                   hint="step out → Toll Road"),
            _deco("b_castle", 4, 4, "black_castle", blocking=True),
            _deco("b_barracks", 30, 3, "red_barracks", blocking=True),
            _deco("b_tower1", 10, 20, "purple_tower", blocking=True),
            _deco("b_ruin1", 26, 12, "goblin_house_destroyed", blocking=True),
            _deco("b_bush1", 8, 11, "bush"), _deco("b_rock1", 14, 22, "rock"),
        ],
    )

    clock_sewer = Area(
        id="clock_sewer", name="The Clock Sewer", biome="sewer",
        mood="dripping and punctual",
        rows=_field(42, 30, [(8, 5, 6, 4, "~"), (22, 11, 7, 4, "~"),
                             (14, 20, 8, 4, "~"), (32, 6, 4, 5, "~")]),
        spawn=(2, 2),
        entities=[
            _npc("water_spirit", "Water Spirit", 20, 9, sprite_key="water_elemental",
                 dialogue="Wave moves water. Leaf reminds it why. Clean me and I carry one kindness to the final room.",
                 hint="cast wave+leaf to restore the flow"),
            _story("clean_shrine", "Clean-Water Shrine", 36, 26, sprite_key="shrine_tower",
                   requires=["wave", "leaf"],
                   dialogue="The water remembers the sky. A shortcut and a final ally open.",
                   hint="cast wave+leaf to restore clean water"),
            Entity("sewer_shrine", "shrine", "Sluice Shrine", 18, 25, sprite="⛩️",
                   blocking=True, tags=["holy"], state="dormant",
                   hint="cast leaf/closed_circle to rinse off damage"),
            _mob("sewer_golem", "Sluice Golem", 37, 5, hp=7,
                 weakness=["flame", "jagged_line"], resistance=["wave", "thread"],
                 sprite_key="ice_golem", mood="clanking on schedule"),
            _npc("sewer_wisp", "Index Wisp", 4, 26, sprite_key="glowing_wisp",
                 dialogue="The sewer has a clean memory. Leaf and Wave can wake it.",
                 hint="a glowing hint about the valves"),
            _story("sewer_valve", "Rusted Valve", 30, 16, sprite_key="knight_tower_blue",
                   requires=["thread", "key"],
                   dialogue="The valve groans open; the sewer current realigns.",
                   hint="cast thread+key to align the valve"),
            Entity("portal_sewer_lib", "portal", "Sewer Stairs", 2, 27, sprite="🚪",
                   blocking=False, target_area="library", target_x=3, target_y=20,
                   hint="step up → The Wet Library"),
            _deco("s_ruin1", 10, 4, "wood_tower_destroyed", blocking=True),
            _deco("s_rock1", 6, 14, "rock2"), _deco("s_bush1", 26, 22, "bush"),
        ],
    )

    gate_approach = Area(
        id="gate_approach", name="Calendar Gate Approach", biome="gate",
        mood="crowded with consequences",
        rows=_field(34, 26, [(15, 4, 3, 8, "#"), (15, 16, 3, 6, "#")]),
        spawn=(2, 12),
        entities=[
            _npc("gate_archer", "Blue Watch Archer", 6, 5, sprite_key="blue_archer",
                 dialogue="When a boss changes stance, stop repeating yourself. The calendar learns.",
                 hint="one last word of advice"),
            _npc("gate_tourist", "Lost Tourist", 6, 20, sprite_key="magical_fairy",
                 dialogue="I found the arena! Bad news: it is awful. Good news: I packed sandwiches.",
                 hint="the tourist you helped, if you did"),
            _npc("gate_librarian", "Mold Librarian", 11, 6, sprite_key="expert_druid",
                 dialogue="For the record, I object to being eaten by an overdue date.",
                 hint="a trusted librarian ally, if you earned one"),
            _npc("gate_water_spirit", "Water Spirit", 11, 19, sprite_key="water_elemental",
                 dialogue="The clean river enters the room. I carried one kindness here.",
                 hint="a clean-water ally, if you restored the flow"),
            _npc("gate_queue_goblin", "Queue Goblin", 22, 5, sprite_key="goblin_red",
                 dialogue="I am only helping because the Beast owes toll.",
                 hint="a paid toll-road ally, if you kept the books clean"),
            _mob("debt_collector", "Debt Collector", 24, 12, hp=8,
                 weakness=["coin", "bell"], resistance=["broken_mark"],
                 sprite_key="red_warrior", mood="collecting forced shortcuts"),
            _story("gate_banner", "Consequence Banner", 10, 5,
                   sprite_key="knight_tower_blue", requires=["eye"],
                   dialogue="The gate remembers both your kindness and your shortcuts.",
                   hint="cast eye to read who waits in the arena"),
            Entity("gate_shrine", "shrine", "Before-Tomorrow Shrine", 12, 20, sprite="⛩️",
                   blocking=True, tags=["holy"], state="dormant",
                   hint="cast leaf/closed_circle before entering the final gate"),
            Entity("final_gate", "portal", "Calendar Gate", 31, 12, sprite="🌀",
                   state="locked", blocking=True, target_area="arena", target_x=14, target_y=18,
                   requires=["Calendar Key"], hint="sealed — prove you carry the Calendar Key"),
            Entity("portal_gate_lib", "portal", "Back to Library", 2, 4, sprite="🚪",
                   blocking=False, target_area="library", target_x=46, target_y=16,
                   hint="step out → The Wet Library"),
            _deco("g_castle", 30, 3, "castle_red", blocking=True),
            _deco("g_ruin1", 10, 22, "castle_destroyed", blocking=True),
            _deco("g_tower1", 28, 20, "knight_tower_yellow", blocking=True),
        ],
    )

    frost_pass = Area(
        id="frost_pass", name="Frostbite Pass", biome="ice", mood="bitterly patient",
        rows=_field(40, 28, [(10, 6, 5, 3, "~"), (24, 14, 6, 4, "~"),
                             (16, 20, 4, 3, "~")]),
        spawn=(3, 3),
        entities=[
            _mob("frost_wisp", "Frost Wisp", 12, 5, hp=6, weakness=["flame", "bell"],
                 resistance=["wave"], sprite_key="glowing_wisp", mood="shivering the air"),
            _mob("glacier_golem", "Glacier Golem", 28, 9, hp=9,
                 weakness=["flame", "jagged_line"], resistance=["wave", "thread"],
                 sprite_key="ice_golem", mood="grinding slow and cold"),
            _mob("hailmonger", "Hailmonger", 33, 22, hp=10, weakness=["flame", "eye"],
                 resistance=["wave"], sprite_key="deft_sorceress", mood="counting snowflakes"),
            _npc("frost_hermit", "Frozen Hermit", 4, 14, sprite_key="grizzled_treant",
                 dialogue="Flame thaws what cold has locked. The deep cache hides a Thawed "
                          "Ember the Foundry's vault craves.",
                 hint="a cold hint about flame"),
            _npc("snow_pixie", "Snow Pixie", 18, 3, sprite_key="fluttering_pixie",
                 dialogue="The golem hates fire. So do I, but only for fashion reasons.",
                 hint="a chilly hint about the golem"),
            _story("ice_ledger", "Frozen Ledger", 8, 9, sprite_key="goblin_house",
                   requires=["eye"], dialogue="The frost ledger lists a debt owed in warmth — "
                   "collectable only at the Ember Foundry.",
                   hint="cast eye to read the frozen ledger"),
            Entity("frost_chest", "chest", "Rime-Locked Cache", 35, 5, sprite="🗃️",
                   state="locked", blocking=True, tags=["ice"],
                   requires=["flame", "key"], loot=["Thawed Ember", "minor powerup"],
                   hint="locked — thaw it with flame + key"),
            Entity("frost_shrine", "shrine", "Hearthless Shrine", 14, 23, sprite="⛩️",
                   blocking=True, tags=["holy"], state="dormant",
                   hint="cast flame/closed_circle to warm yourself and heal"),
            Entity("portal_home_f", "portal", "Pass Exit", 2, 25, sprite="🚪",
                   blocking=False, target_area="overworld", target_x=8, target_y=27,
                   hint="step out → Toll Road"),
            Entity("portal_foundry_f", "portal", "Steam Vent", 37, 25, sprite="🌀",
                   blocking=False, target_area="ember_foundry", target_x=3, target_y=3,
                   hint="step in → The Ember Foundry"),
            _deco("f_rock1", 10, 4, "rock"), _deco("f_rock2", 22, 12, "rock2"),
            _deco("f_bush1", 6, 7, "bush", blocking=False),
            _deco("f_bush2", 26, 6, "bush", blocking=False),
        ],
    )

    ember_foundry = Area(
        id="ember_foundry", name="The Ember Foundry", biome="forge",
        mood="overheated and proud",
        rows=_field(38, 28, [(14, 10, 5, 3, "~"), (26, 18, 4, 3, "~")]),
        spawn=(3, 3),
        entities=[
            _mob("forge_imp", "Forge Imp", 12, 6, hp=6, weakness=["wave", "closed_circle"],
                 resistance=["flame"], sprite_key="fire_elemental", mood="spitting sparks"),
            _mob("slag_golem", "Slag Golem", 9, 18, hp=9, weakness=["wave", "jagged_line"],
                 resistance=["flame", "thread"], sprite_key="earth_elemental",
                 mood="molten and slow"),
            _mob("cinder_smith", "Cinder Smith", 30, 22, hp=11, weakness=["wave", "eye"],
                 resistance=["flame"], sprite_key="adept_necromancer",
                 mood="hammering debts flat"),
            _npc("forge_master", "Foundry Master", 4, 13, sprite_key="npc_pawn",
                 dialogue="Bring warmth from the Frost Pass and I forge real steel. Wave cools "
                          "my temper if you must talk.",
                 hint="forge lore — wave to calm the heat"),
            _npc("anvil_wisp", "Anvil Wisp", 20, 3, sprite_key="glowing_wisp",
                 dialogue="The vault door wants a Thawed Ember. The smith resists fire — soak "
                          "him with water.",
                 hint="a glowing hint about the vault door"),
            _story("forge_ledger", "Slag Ledger", 8, 9, sprite_key="goblin_house",
                   requires=["eye"], dialogue="The foundry ledger: every blade here was a debt "
                   "reforged into an edge.",
                   hint="cast eye to read the slag ledger"),
            Entity("ember_door", "locked_door", "Ember Vault Door", 24, 12, sprite="🚪",
                   state="locked", blocking=True, tags=["door", "forge"],
                   requires=["Thawed Ember"],
                   hint="locked — open it with a Thawed Ember from the Frost Pass"),
            Entity("ember_chest", "chest", "Brand Rack", 33, 6, sprite="🗃️",
                   state="locked", blocking=True, tags=["forge"], requires=["flame"],
                   loot=["forge-hot trophy", "minor powerup"],
                   hint="locked — light it with flame"),
            Entity("foundry_shrine", "shrine", "Quenching Shrine", 16, 22, sprite="⛩️",
                   blocking=True, tags=["holy"], state="dormant",
                   hint="cast wave/closed_circle to quench and heal"),
            Entity("portal_home_e", "portal", "Foundry Exit", 2, 25, sprite="🚪",
                   blocking=False, target_area="overworld", target_x=40, target_y=27,
                   hint="step out → Toll Road"),
            Entity("portal_frost_e", "portal", "Cooling Vent", 35, 3, sprite="🕳️",
                   blocking=False, target_area="frost_pass", target_x=37, target_y=24,
                   hint="step in → Frostbite Pass"),
            _deco("e_castle", 4, 4, "black_castle", blocking=True),
            _deco("e_rock1", 10, 16, "rock"), _deco("e_rock2", 28, 8, "rock2"),
            _deco("e_bush1", 18, 6, "bush", blocking=False),
        ],
    )

    all_areas = (overworld, caverns, library, bone_market, clock_sewer,
                 gate_approach, arena, frost_pass, ember_foundry)
    for e in bone_market.entities:
        if e.id == "secret_merchant":
            e.state = "hidden"
            e.blocking = False
    for e in gate_approach.entities:
        if e.id in {"gate_tourist", "gate_librarian", "gate_water_spirit",
                    "gate_queue_goblin", "debt_collector"}:
            e.state = "hidden"
            e.blocking = False
    # 1) fix anything an enlarged map / new pond displaced
    for a in all_areas:
        _relocate_invalid(a)
    # 2) landmark buildings to give each region identity and break up open fields
    _scatter_buildings(overworld, ["castle_blue", "knight_house_blue", "goblin_house",
                                   "wood_tower_building", "gold_mine"], 6, 101)
    _scatter_buildings(caverns, ["wood_tower_destroyed", "knight_tower_blue"], 4, 102)
    _scatter_buildings(library, ["castle_blue", "purple_tower", "knight_tower_yellow",
                                 "yellow_monastery"], 6, 103)
    _scatter_buildings(bone_market, ["black_castle", "red_barracks", "goblin_house_destroyed"], 3, 104)
    _scatter_buildings(clock_sewer, ["wood_tower_destroyed", "knight_tower_blue"], 3, 105)
    _scatter_buildings(gate_approach, ["castle_red", "knight_tower_yellow"], 2, 106)
    _scatter_buildings(frost_pass, ["knight_tower_blue", "wood_tower_destroyed"], 3, 107)
    _scatter_buildings(ember_foundry, ["red_barracks", "goblin_tower_red"], 3, 108)
    # 3) animated water rocks beside ponds, then ground clutter to fill
    for a, n, s in ((overworld, 6, 201), (caverns, 8, 202), (library, 5, 203),
                    (clock_sewer, 10, 204), (frost_pass, 7, 205), (ember_foundry, 4, 206)):
        _scatter_water_rocks(a, n, s)
    _scatter_deco(overworld, 70, 11)
    _scatter_deco(caverns, 60, 22)
    _scatter_deco(library, 60, 33)
    _scatter_deco(bone_market, 34, 55)
    _scatter_deco(clock_sewer, 46, 66)
    _scatter_deco(gate_approach, 26, 77)
    _scatter_deco(arena, 14, 44)
    _scatter_deco(frost_pass, 50, 88)
    _scatter_deco(ember_foundry, 44, 99)
    return {a.id: a for a in all_areas}


AREAS: dict[str, Area] = _build_areas()
START_AREA = "overworld"

# Admin mode is a *backend-only* switch: set the RG_ADMIN env var on the server
# and every gated portal / door / chest in the served world is pre-unlocked, so
# all maps are reachable from the start. There is no client-side toggle and no
# query parameter — the only way to enable it is on the machine running the app.
ADMIN_MODE = os.environ.get("RG_ADMIN", "0").strip().lower() in {"1", "true", "yes", "on"}

# Key story items granted to the player in admin mode so inventory-gated content
# (vault doors, sealed portals) also opens without questing for them.
_ADMIN_GRANT_ITEMS = ("Calendar Key", "Calendar Shard", "Debt Receipt", "Thawed Ember")


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
    item_sources: dict[str, list[str]] = {}
    required_items: dict[str, list[str]] = {}
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
        quality = {
            "story": False, "npc": False, "shrine": False, "locked": False,
            "return": a.id == START_AREA, "journal": False, "consequence": False,
            "optional_loop": len(reach) > wdt * h * 0.45,
            "locked_reward": False,
        }
        for e in a.entities:
            if (e.x, e.y) in problems:
                continue
            if e.loot:
                for item in e.loot:
                    item_sources.setdefault(item, []).append(f"{a.id}/{e.id}")
            for req in e.requires:
                if req and req not in GLYPHS and req not in {"Debt Receipt"}:
                    required_items.setdefault(req, []).append(f"{a.id}/{e.id}")
            if e.type == "story_object":
                quality["story"] = True
            if e.type == "npc":
                quality["npc"] = True
            if e.type == "shrine":
                quality["shrine"] = True
            if e.dialogue and e.type in {"npc", "story_object"}:
                quality["journal"] = True
            if (e.id in globals().get("_STORY_FLAG", {})
                    or any(k[0] == e.id for k in globals().get("_NPC_FLAG", {}))
                    or e.type in {"chest", "locked_door"}
                    or (e.type == "portal" and (e.state == "locked" or e.requires))):
                quality["consequence"] = True
            if e.state == "locked" or e.requires:
                quality["locked"] = True
                if e.loot or e.type in {"story_object", "locked_door", "portal", "chest"}:
                    quality["locked_reward"] = True
            if not e.blocking:  # stepped onto (portal/powerup): tile itself must be reachable
                if (e.x, e.y) not in reach:
                    problems.append(f"{a.id}/{e.id}: unreachable tile ({e.x},{e.y})")
            else:  # interacted with from an adjacent tile
                adj = [(e.x + dx, e.y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
                if not any(p in reach for p in adj):
                    problems.append(f"{a.id}/{e.id}: no reachable neighbour ({e.x},{e.y})")
            # portals must point at a real area and a walkable landing tile
            if e.type == "portal" and e.target_area:
                dest = AREAS.get(e.target_area)
                if dest is None:
                    problems.append(f"{a.id}/{e.id}: portal target '{e.target_area}' missing")
                else:
                    dn = _normalize_rows(dest.rows)
                    if not (0 <= e.target_y < len(dn) and 0 <= e.target_x < len(dn[0])
                            and dn[e.target_y][e.target_x] in WALKABLE):
                        problems.append(
                            f"{a.id}/{e.id}: portal lands on non-walkable "
                            f"({e.target_x},{e.target_y}) in {e.target_area}")
                    if e.target_area != a.id:
                        quality["return"] = True
        if a.id == "arena" and len(reach) < 80:
            problems.append(f"{a.id}: boss arena has only {len(reach)} reachable tiles")
        for key, ok in quality.items():
            if not ok:
                problems.append(f"{a.id}: missing required map quality '{key}'")
    # Manual story/item sources that come from world actions rather than static loot.
    item_sources.setdefault("Debt Receipt", []).append("forced broken_mark+key entry")
    item_sources.setdefault("Mirror Cap", []).append("caverns/nursery spare")
    item_sources.setdefault("Tollmaster Token", []).append("overworld/bell_shrine")
    for item, uses in required_items.items():
        if item not in item_sources:
            problems.append(f"item '{item}' required by {', '.join(uses)} has no acquisition path")
    return problems


def _class_to_dict(c: story.GoblinClass) -> dict:
    return {
        "id": c.id, "label": c.label, "sprite": c.sprite,
        "preview_gif": c.preview_gif, "hp": c.hp, "courage": c.courage,
        "speed": c.speed,
        "affinity": list(c.affinity), "passive": c.passive,
        "king_ability": c.king_ability, "fantasy": c.fantasy,
        "select_line": c.select_line, "king_line": c.king_line,
    }


def _weapon_to_dict(w: story.Weapon) -> dict:
    return {
        "id": w.id, "label": w.label, "identity": w.identity,
        "school": list(w.school), "bonus_damage": w.bonus_damage,
        "courage_relief": w.courage_relief, "shield_chance": w.shield_chance,
        "unlock_bonus": w.unlock_bonus, "xp_bonus": w.xp_bonus,
        "npc_reaction": w.npc_reaction, "story_flag": w.story_flag,
    }


_WORLD_VARIATIONS = (
    {
        "id": "sandwich_weather",
        "label": "Sandwich Weather",
        "marker_area": "overworld",
        "marker_xy": (7, 7),
        "marker": "Tourist Lunch Cache",
        "hint": "A lunch bundle marks a kinder route toward the arena.",
        "journal": "This loop smells faintly of packed lunches. Helping frightened travelers may matter.",
    },
    {
        "id": "mirror_bloom",
        "label": "Mirror Bloom",
        "marker_area": "caverns",
        "marker_xy": (7, 4),
        "marker": "Bright Mirror Spore",
        "hint": "A harmless spore catches the light like a clue.",
        "journal": "This loop's fungus glints early. Mirror and eye routes may reveal more than damage.",
    },
    {
        "id": "coin_draft",
        "label": "Coin Draft",
        "marker_area": "bone_market",
        "marker_xy": (8, 8),
        "marker": "Warm Coin Draft",
        "hint": "The air jingles toward a secret toll route.",
        "journal": "This loop carries market noise on the road. Coin and bell mastery may open stranger endings.",
    },
)


def _apply_world_variation(payload: dict, seed: int | None) -> None:
    """Attach deterministic, noncritical replay variation to a world payload.

    Main progression stays authored and validated. The seed only changes
    visible hints/markers and metadata so repeated runs feel distinct without
    invalidating tests, locks, or balance.
    """
    if seed is None:
        payload["world_seed"] = None
        payload["variation"] = {"id": "default", "label": "Default Loop"}
        return

    rng = random.Random(seed)
    var = dict(_WORLD_VARIATIONS[rng.randrange(len(_WORLD_VARIATIONS))])
    area = payload["areas"].get(var["marker_area"])
    if area:
        x, y = var["marker_xy"]
        area["entities"].append({
            "id": f"seed_marker_{var['id']}",
            "type": "map_marker",
            "name": var["marker"],
            "x": x,
            "y": y,
            "sprite": "!",
            "state": "idle",
            "blocking": False,
            "hp": 0,
            "max_hp": 0,
            "weakness": [],
            "resistance": [],
            "mood": "seeded loop clue",
            "tags": ["seeded", "hint"],
            "requires": [],
            "loot": [],
            "dialogue": var["journal"],
            "target_area": "",
            "target_x": 0,
            "target_y": 0,
            "hint": var["hint"],
            "sprite_key": "glowing_wisp",
        })
    payload["world_seed"] = seed
    payload["variation"] = {
        "id": var["id"],
        "label": var["label"],
        "journal": var["journal"],
    }
    payload["player"]["world_seed"] = seed
    payload["player"]["world_variation"] = var["id"]
    payload["player"]["journal"].append(var["journal"])


def _admin_unlock(payload: dict) -> None:
    """Unlock every gated portal / door / chest in a world payload.

    Backend-only god-mode (see :data:`ADMIN_MODE`): area-to-area portals and
    locked doors become walkable, chests open with any cast, and the player
    starts holding the key story items so nothing soft-locks exploration.
    """
    for area in payload["areas"].values():
        for e in area["entities"]:
            gated = e.get("state") == "locked" or e.get("requires")
            if not gated:
                continue
            etype = e.get("type")
            if etype in {"portal", "locked_door"}:
                # state != "locked" lets the client travel / pass freely
                e["state"] = "open"
                e["blocking"] = False
                e["requires"] = []
                e["hint"] = "🔓 admin — unlocked"
            elif etype == "chest":
                # clearing requires lets any cast pop it; still a reward to grab
                e["requires"] = []
                e["hint"] = "🔓 admin — open with any cast"
    inv = payload["player"].setdefault("inventory", [])
    for item in _ADMIN_GRANT_ITEMS:
        if item not in inv:
            inv.append(item)
    payload["admin"] = True


def build_world(seed: int | None = None, admin: bool | None = None) -> dict:
    """Full serializable world for the client.

    ``admin`` defaults to the server-side :data:`ADMIN_MODE` env switch; pass it
    explicitly only in tests. When on, every map is pre-unlocked.
    """
    start = story.GOBLIN_CLASSES[story.DEFAULT_CLASS]
    payload = {
        "start_area": START_AREA,
        "areas": {aid: _area_to_dict(a) for aid, a in AREAS.items()},
        "player": {
            "hp": start.hp, "max_hp": start.hp, "courage": start.courage,
            "max_courage": max(9, start.courage + 2),
            "level": 1, "xp": 0, "xp_to_next": story.xp_to_next(1),
            "goblin_class": start.id, "evolved": False, "evolved_form": "",
            "weapon": story.STARTING_WEAPON, "weapon_inventory": [story.STARTING_WEAPON],
            "gold": 3, "rune_mastery": {}, "story_flags": [], "ending_flags": [], "journal": [],
            "four_rune_unlocked": False,
            "inventory": ["wet candle"], "score": 0, "statuses": [],
            "items": {}, "quests": {},
            "quest_log": ["Find the Calendar Shard in the Mirror Fungus Caverns."],
            "discoveries": [], "recent_story_events": [], "trust": {},
        },
        "classes": [_class_to_dict(c) for c in story.GOBLIN_CLASSES.values()],
        "weapons": [_weapon_to_dict(w) for w in story.WEAPONS.values()],
        "items": quests.items_payload(),
        "quests": quests.quests_payload(),
        "runes": [{"key": k, "symbol": g.symbol, "label": g.label,
                   "meanings": list(g.meanings)} for k, g in GLYPHS.items()],
        "walkable": "".join(sorted(WALKABLE)),
    }
    _apply_world_variation(payload, seed)
    if admin is None:
        admin = ADMIN_MODE
    if admin:
        _admin_unlock(payload)
    return payload


# ---------------------------------------------------------------------------
# Progression / story helpers used by resolve_world_cast
# ---------------------------------------------------------------------------
def _combat_bonus(runes: list[str], player: dict) -> int:
    """Deterministic extra damage from equipped weapon + class affinity + rune mastery."""
    return _combat_metadata(runes, player)["total_bonus"]


def _combat_metadata(runes: list[str], player: dict) -> dict:
    """Structured breakdown for plan-required cast response metadata."""
    weapon = story.weapon_or_default(player.get("weapon"))
    gclass = story.class_or_default(player.get("goblin_class"))
    mastery = player.get("rune_mastery") or {}
    weapon_bonus = 0
    if weapon.school and any(r in weapon.school for r in runes):
        weapon_bonus = weapon.bonus_damage
    class_bonus = 1 if gclass.affinity and any(r in gclass.affinity for r in runes) else 0
    mastered = [r for r in runes if mastery.get(r, 0) >= story.RUNE_MASTERY_THRESHOLD]
    mastery_bonus = 1 if mastered else 0
    total = weapon_bonus + class_bonus + mastery_bonus
    return {
        "weapon": {
            "id": weapon.id,
            "label": weapon.label,
            "matched": bool(weapon_bonus),
            "bonus_damage": weapon_bonus,
            "identity": weapon.identity,
        },
        "goblin_class": {
            "id": gclass.id,
            "label": gclass.label,
            "matched": bool(class_bonus),
            "bonus_damage": class_bonus,
        },
        "rune_mastery": {
            "matched": mastered,
            "bonus_damage": mastery_bonus,
        },
        "boss": {
            "pylon_bonus": 0,
            "king_bonus": 0,
            "king_statuses": [],
        },
        "total_bonus": total,
    }


def _class_king_bonus(runes: list[str], player: dict, target: dict) -> tuple[int, list[str]]:
    """Final-form class abilities from the plan, exposed as deterministic combat bonuses."""
    if not player.get("evolved"):
        return 0, []
    cls = player.get("goblin_class")
    flags: list[str] = []
    bonus = 0
    if cls == "warrior" and "closed_circle" in runes:
        bonus += 1
        flags.append("player_shielded")
    elif cls == "rogue" and any(r in runes for r in ("key", "coin")):
        bonus += 2
    elif cls == "poison" and any(r in runes for r in ("leaf", "tooth", "broken_mark")):
        bonus += 1
        flags.append("enemy_bound")
    elif cls == "hunter" and any(r in runes for r in ("eye", "thread")):
        bonus += 2
        flags.append("weakness_revealed")
    elif cls == "barbarian" and any(r in runes for r in ("flame", "bone", "tooth")):
        bonus += 3 if target.get("type") == "boss" else 2
    return bonus, flags


def _xp_actions(player: dict, gained: int) -> list[dict]:
    """Grant XP and surface any level-up rewards as world actions."""
    level = int(player.get("level", 1))
    xp = int(player.get("xp", 0))
    weapon = story.weapon_or_default(player.get("weapon"))
    if gained > 0 and weapon.xp_bonus:
        gained += weapon.xp_bonus
    new_level, new_xp, rewards = story.apply_xp(level, xp, gained)
    acts: list[dict] = [{
        "type": "set_progress", "level": new_level, "xp": new_xp,
        "xp_to_next": story.xp_to_next(new_level), "gained": gained,
    }]
    for reward in rewards:
        acts.append({"type": "level_up", **reward})
    return acts


def _flag_actions(flags) -> list[dict]:
    """Emit set_story_flag actions for any allowlisted flags."""
    return [{"type": "set_story_flag", "flag": f} for f in story.filter_flags(flags)]


# NPC id + rune-intent -> durable story flag (story_plan.md trust flags).
_NPC_FLAG: dict[tuple[str, str], str] = {
    ("tourist", "kind"): "tourist_helped",
    ("tourist", "fear"): "tourist_scared",
    ("librarian", "insight"): "librarian_trust",
    ("librarian", "fear"): "librarian_angry",
    ("water_spirit", "kind"): "water_spirit_helped",
    ("toll_goblin", "coin"): "queue_goblin_paid",
    ("toll_goblin", "bell"): "queue_goblin_paid",
    ("toll_goblin", "fear"): "queue_goblin_forced",
    ("cave_hermit", "kind"): "fungus_colony_spared",
    ("cave_hermit", "fear"): "fungus_colony_burned",
    ("market_merchant", "coin"): "debt_repaid",
    ("market_merchant", "fear"): "debt_deepened",
    ("debt_collector", "coin"): "debt_repaid",
    ("secret_merchant", "coin"): "secret_merchant_met",
    ("secret_merchant", "bell"): "secret_merchant_met",
}

# Story-object id -> flags set when it is successfully read.
_STORY_FLAG: dict[str, tuple[str, ...]] = {
    "cave_echo": ("mirror_truth_seen",),
    "wet_catalog": ("wet_catalog_read", "calendar_truth_read"),
    "dry_shelves": ("library_shelves_burned", "calendar_devour_pressure"),
    "toll_board": (),
    "bell_shrine": ("secret_bell_shrine_seen", "tollmaster_route_open"),
    "debt_altar": ("debt_repaid",),
    "clean_shrine": ("clean_water_restored", "sewer_shortcut_open"),
    "sewer_valve": ("sewer_valves_aligned", "sewer_shortcut_open"),
    "nursery": ("fungus_colony_spared",),
    "pylon_eye": ("mirror_truth_seen", "pylon_eye_charged"),
    "pylon_mirror": ("calendar_repair_possible", "pylon_mirror_charged"),
    "pylon_leaf": ("calendar_repair_possible", "pylon_leaf_charged"),
    "pylon_spiral": ("calendar_repair_possible", "pylon_spiral_charged"),
}

_MERCHANT_STOCK = {
    "market_merchant": {
        "coin": "mirror_shield",
        "bell": "bell_staff",
        "bone": "bone_blade",
        "tooth": "bone_blade",
        "broken_mark": "bone_blade",
        "wave": "river_thread",
        "leaf": "river_thread",
    },
    "secret_merchant": {
        "coin": "coin_sling",
        "bell": "coin_sling",
    },
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


def _spawn_entity(eid: str, etype: str, name: str, x: int, y: int, *,
                  sprite_key: str, hp: int = 0, weakness=(), resistance=(),
                  mood: str = "", blocking: bool = True) -> dict:
    """Action payload for temporary enemies/hazards spawned by boss phases."""
    return {
        "id": eid, "type": etype, "name": name, "x": x, "y": y,
        "sprite": enemy_sprite(name) if etype in {"enemy", "boss"} else "⚠",
        "state": "idle", "blocking": blocking, "hp": hp, "max_hp": hp,
        "weakness": list(weakness), "resistance": list(resistance),
        "mood": mood, "tags": ["hostile"] if etype == "enemy" else ["hazard"],
        "requires": [], "loot": [], "dialogue": "", "target_area": "",
        "target_x": 0, "target_y": 0,
        "hint": "phase consequence — cast to clear" if etype == "enemy" else "phase hazard",
        "sprite_key": sprite_key,
    }


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

    # --- toll gate: the Queue Goblin takes a coin, a bell, or your blood ----
    # Paying is a deterministic transaction, not combat: a coin (if you have
    # one) buys peaceful passage; a bell annoys him aside for free; with no
    # coin the toll comes out of your hide and you shove past anyway.
    if ttype == "enemy" and tid == "toll_goblin" and (
            "coin" in runes or "bell" in runes):
        gold = int(player.get("gold", 0) or 0)
        journal = story.NPC_VOICES["toll_goblin"].journal
        actions.append({"type": "bump_mastery", "runes": runes})
        # Clear the gate in every branch so the player is never soft-locked.
        # Use defeat_entity (not set_entity_state) so the client marks the goblin
        # done and does NOT retaliate — paying the toll is a transaction, not a
        # fight. The spell's effect text carries the peaceful "gate opens" line.
        actions.append({"type": "defeat_entity", "target_id": tid})

        if "bell" in runes:
            actions += _flag_actions(["queue_goblin_paid", "tollmaster_route_open"])
            actions.append({"type": "add_journal_entry", "text": journal})
            actions += _xp_actions(player, story.XP_UNLOCK)
            spell = SpellResult(
                spell_name="Bell of Passage", spell_type="utility",
                flavor=_flavor_world(runes, target, combo),
                effect="You ring the bell. The Queue Goblin winces and waves you through.",
                status_effects=["toll_rung"], chaos=2)
        elif gold >= 1:
            actions.append({"type": "add_gold", "amount": -1})
            actions += _flag_actions(["queue_goblin_paid", "toll_paid"])
            actions.append({"type": "add_journal_entry", "text": journal})
            actions += _xp_actions(player, story.XP_UNLOCK)
            spell = SpellResult(
                spell_name="Toll Paid", spell_type="utility",
                flavor=_flavor_world(runes, target, combo),
                effect="You drop a coin in his cup. The gate opens. (-1 coin)",
                status_effects=["toll_paid"], chaos=1)
        else:
            actions += _flag_actions(["queue_goblin_forced", "toll_forced"])
            actions.append({"type": "add_journal_entry",
                            "text": "No coin for the toll — the Queue Goblin took it out of your hide."})
            spell = SpellResult(
                spell_name="Toll of Blood", spell_type="utility",
                flavor=_flavor_world(runes, target, combo),
                effect="You have no coin. The goblin takes the toll out of your hide "
                       "(-2 HP) and you shove past.",
                player_hp_delta=-2, status_effects=["toll_forced"], chaos=2)
        return {"spell": spell.model_dump(), "world_actions": actions,
                "target_id": tid, "runes": runes,
                "metadata": {"combat": _combat_metadata(runes, player)}}

    # --- combat: enemy / boss ---------------------------------------------
    if ttype in {"enemy", "boss"}:
        cur_hp = target.get("hp", 5)
        max_hp = target.get("max_hp", 5)
        weakness = tuple(target.get("weakness") or ())
        resistance = tuple(target.get("resistance") or ())
        flags = list(player.get("story_flags", []))

        # Bosses shift weakness/resistance by phase (game_plan.md boss mechanics).
        phase_info = None
        if ttype == "boss":
            phase_info = story.boss_phase_for(cur_hp, max_hp)
            weakness = tuple(phase_info["weakness"])
            resistance = tuple(phase_info["resistance"])
            if "pylon_eye_charged" in flags:
                weakness = tuple(dict.fromkeys(weakness + ("eye", "mirror")))
            if "pylon_mirror_charged" in flags and phase_info["phase"] >= 2:
                resistance = tuple(r for r in resistance if r not in {"jagged_line", "flame"})
            if "pylon_leaf_charged" in flags and phase_info["phase"] >= 3:
                resistance = tuple(r for r in resistance if r != "flame")
            recent = tuple(player.get("recent_runes") or ())
            if recent and any(r in recent for r in runes):
                repeated = tuple(dict.fromkeys(recent + tuple(runes)))
                resistance = tuple(dict.fromkeys(resistance + repeated))

        state = GameState(
            player_hp=player.get("hp", 10), player_max_hp=player.get("max_hp", 10),
            enemy_name=target.get("name", "Mirror Fungus"),
            enemy_hp=cur_hp, enemy_max_hp=max_hp,
            room_mood=target.get("mood", ""), inventory=tuple(inventory),
            courage=player.get("courage", 5),
            weakness_override=weakness, resistance_override=resistance,
        )
        spell = resolve_spell(state, runes, seed=seed)
        if ttype == "boss" and player.get("recent_runes") and any(r in player.get("recent_runes", []) for r in runes):
            # The Calendar Beast learns repeated rune spam. Clamp after normal
            # spell resolution so the deterministic engine still owns base math.
            if spell.enemy_hp_delta < 0:
                spell.enemy_hp_delta = min(0, spell.enemy_hp_delta + 2)
            spell.effect = f"{spell.effect} The Beast remembers that pattern and resists it."
            if "boss_adapted" not in spell.status_effects:
                spell.status_effects.append("boss_adapted")

        # Weapon + class affinity bonus damage (visible in HUD metadata).
        metadata = {"combat": _combat_metadata(runes, player)}
        bonus = metadata["combat"]["total_bonus"]
        if ttype == "boss" and "pylon_spiral_charged" in flags and "spiral" in runes:
            bonus += 2
            metadata["combat"]["boss"]["pylon_bonus"] += 2
        king_bonus, king_statuses = _class_king_bonus(runes, player, target)
        bonus += king_bonus
        metadata["combat"]["boss"]["king_bonus"] = king_bonus
        metadata["combat"]["boss"]["king_statuses"] = king_statuses
        metadata["combat"]["total_bonus"] = bonus
        delta = spell.enemy_hp_delta
        if bonus and delta < 0:
            delta = max(-cur_hp, delta - bonus)
            spell.enemy_hp_delta = delta
            if bonus:
                spell.effect = f"{spell.effect} (+{bonus} from gear/affinity)"
        for st in king_statuses:
            if st not in spell.status_effects:
                spell.status_effects.append(st)
        if ttype == "boss":
            pylon_status = {
                "pylon_eye_charged": "pylon_eye_revealed",
                "pylon_mirror_charged": "pylon_mirror_softened",
                "pylon_leaf_charged": "pylon_leaf_greened",
                "pylon_spiral_charged": "pylon_spiral_unwound",
            }
            for flag, status in pylon_status.items():
                if flag in flags and status not in spell.status_effects:
                    spell.status_effects.append(status)
        new_hp = max(0, cur_hp + delta)
        actions.append({"type": "set_entity_hp", "target_id": tid, "hp": new_hp})
        # rune mastery grows with offensive use of each rune
        actions.append({"type": "bump_mastery", "runes": runes})

        # Boss phase transition banner.
        if ttype == "boss" and new_hp > 0:
            new_phase = story.boss_phase_for(new_hp, max_hp)
            if phase_info and new_phase["phase"] != phase_info["phase"]:
                boss_reactions = story.boss_flag_reactions(flags)
                actions.append({"type": "start_boss_phase", "phase": new_phase["phase"],
                                "banner": new_phase["banner"], "line": new_phase["line"],
                                "boss_reactions": boss_reactions})
                if new_phase["phase"] >= 2:
                    actions += _flag_actions(["calendar_beast_phase_2"])
                    actions.append({"type": "spawn_entity", "entity": _spawn_entity(
                        "phase2_debt_echo", "enemy", "Debt Echo", 11, 11,
                        hp=5, weakness=["coin", "bell"], resistance=["broken_mark"],
                        sprite_key="red_warrior", mood="collecting repeated mistakes")})
                if new_phase["phase"] >= 3:
                    actions += _flag_actions(["calendar_beast_phase_3"])
                    actions.append({"type": "spawn_entity", "entity": _spawn_entity(
                        "phase3_fungus_echo", "enemy", "Fungus Echo", 17, 10,
                        hp=5, weakness=["mirror", "eye"], resistance=["flame"],
                        sprite_key="glowing_wisp", mood="copying old spellwork")})
                    actions.append({"type": "spawn_entity", "entity": _spawn_entity(
                        "phase3_time_hazard", "hazard", "Calendar Hazard", 14, 12,
                        sprite_key="water_foam", mood="phase hazard", blocking=False)})
                    if "tourist_helped" in flags:
                        actions.append({"type": "heal_player", "amount": 2})
                        actions.append({"type": "add_journal_entry",
                                        "text": "The Lost Tourist reaches the arena with sandwiches and limited courage."})
                        actions += _flag_actions(["boss_ally_tourist"])
                    if "librarian_trust" in flags:
                        actions.append({"type": "add_courage", "amount": 2})
                        actions.append({"type": "add_journal_entry",
                                        "text": "The Mold Librarian objects to being eaten by an overdue date."})
                        actions += _flag_actions(["boss_ally_librarian"])
                    if "clean_water_restored" in flags:
                        actions.append({"type": "heal_player", "amount": 2})
                        actions.append({"type": "add_journal_entry",
                                        "text": "The clean river enters the final room as promised."})
                        actions += _flag_actions(["boss_ally_water"])

        if new_hp <= 0:
            actions.append({"type": "defeat_entity", "target_id": tid})
            actions += _xp_actions(player, story.XP_DEFEAT_BOSS_PHASE if ttype == "boss"
                                   else story.XP_DEFEAT_ENEMY)
            # Enemies drop a coin or two so the player can afford tolls, plus
            # trophies/materials that feed the quest economy.
            if ttype == "enemy":
                actions.append({"type": "add_gold", "amount": rng.randint(1, 2)})
                for drop in quests.monster_drops(tid, target.get("name", "")):
                    actions.append({"type": "add_item", "item": drop, "qty": 1})
            if tid == "mycologist" or "mycologist" in str(tid):
                actions += _flag_actions(["mycologist_defeated"])
            if ttype == "boss":
                ending = story.compute_ending(
                    flags, final_runes=runes, weapon=player.get("weapon"),
                    mastery=player.get("rune_mastery"))
                choices = story.ending_choice_lines(
                    flags, final_runes=runes, weapon=player.get("weapon"),
                    goblin_class=player.get("goblin_class"),
                    mastery=player.get("rune_mastery"),
                    evolved=bool(player.get("evolved")),
                )
                _ending_flag = {"repaired": "calendar_repaired",
                                "devoured": "calendar_devoured",
                                "tollmaster": "tollmaster_ending"}.get(
                    ending.key, "calendar_broken")
                actions += _flag_actions([_ending_flag])
                actions.append({"type": "win_game", "ending": ending.key,
                                "title": ending.title, "text": ending.text,
                                "choices": choices,
                                "boss_reactions": story.boss_flag_reactions(flags, limit=3)})
        else:
            actions += _xp_actions(player, 1)  # chip damage XP
        return {"spell": spell.model_dump(), "world_actions": actions,
                "target_id": tid, "runes": runes, "metadata": metadata}

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
                if item in story.WEAPONS:
                    actions.append({"type": "add_weapon", "weapon": item})
                    actions += _flag_actions(["weapon_bought"])
            if any("Calendar Key" in str(i) for i in loot):
                actions += _flag_actions(["calendar_key_found"])
            if any("Shard" in str(i) for i in loot):
                actions += _flag_actions(["calendar_shard_1_taken"])
            # Chests also spill a few coins for tolls and trades.
            actions.append({"type": "add_gold", "amount": rng.randint(2, 3)})
            actions += _xp_actions(player, story.XP_UNLOCK)
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
        weapon = story.weapon_or_default(player.get("weapon"))
        forced = "broken_mark" in runes and "key" in runes
        weapon_unlock = weapon.unlock_bonus and "key" in requires and any(r in {"coin", "bell", "key"} for r in runes)
        market_pass = tid == "portal_market" and (
            ("Debt Receipt" in inventory) or {"coin", "bell"}.issubset(set(runes)) or forced
        )
        if _matches_requirement(runes, requires, inventory) or forced or weapon_unlock or market_pass:
            actions.append({"type": "set_entity_state", "target_id": tid, "state": "open"})
            actions.append({"type": "set_entity_blocking", "target_id": tid, "blocking": False})
            side = "A small debt appears in your satchel." if forced else ""
            if forced:
                actions.append({"type": "add_inventory", "item": "Debt Receipt"})
                actions += _flag_actions(["debt_accepted", "debt_receipt", "calendar_devour_pressure"])
            if tid == "portal_market":
                actions += _flag_actions(["bone_market_entered"])
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
        intent = story.npc_intent(runes)
        gift = next((_NPC_GIFTS[r] for r in runes if r in _NPC_GIFTS), None)
        insight = any(r in {"eye", "spiral", "mirror"} for r in runes)

        # Durable story flag + journal from the NPC voice tables.
        flag = _NPC_FLAG.get((tid, intent))
        if flag:
            actions += _flag_actions([flag])
        voice = story.NPC_VOICES.get(tid)
        if voice and voice.journal:
            actions.append({"type": "add_journal_entry", "text": voice.journal})

        # Bone Market merchants sell deterministic weapons by rune intent.
        stock = _MERCHANT_STOCK.get(tid, {})
        wid = next((stock[r] for r in runes if r in stock), "")
        if wid:
            if wid in (player.get("weapon_inventory") or []):
                actions.append({"type": "upgrade_weapon", "weapon": wid,
                                "message": f"{story.WEAPONS[wid].label} is honed by the market's bad advice."})
            else:
                actions.append({"type": "add_weapon", "weapon": wid})
                actions.append({"type": "add_inventory", "item": story.WEAPONS[wid].label})
            actions += _flag_actions(["weapon_bought", "bone_market_entered"])
            if tid == "secret_merchant":
                actions += _flag_actions(["secret_merchant_met", "tollmaster_route_open"])
            if story.WEAPONS[wid].story_flag:
                actions += _flag_actions([story.WEAPONS[wid].story_flag])
            if tid == "market_merchant" and intent == "fear":
                deal = ("The Bone Market approves the cursed deal: power now, "
                        "interest later.")
                actions.append({"type": "add_courage", "amount": 3})
                actions.append({"type": "add_gold", "amount": 2})
                actions.append({"type": "add_journal_entry", "text": deal})
                actions.append({"type": "add_discovery", "text": deal})
                actions += _flag_actions(["calendar_devour_pressure"])

        if gift:
            _, msg, kind, amt = gift
            if kind == "courage":
                actions.append({"type": "add_courage", "amount": amt})
            else:
                actions.append({"type": "heal_player", "amount": amt})
            actions.append({"type": "change_npc_trust", "target_id": tid, "delta": 1})
            actions += _xp_actions(player, story.XP_HELP_NPC)
            actions.append({"type": "add_discovery", "text": f"{target.get('name')} trusts you."})
            spell = SpellResult(
                spell_name="Kindly Hex", spell_type="npc",
                flavor=_flavor_world(runes, target, combo), effect=msg,
                player_hp_delta=amt if kind == "hp" else 0,
                status_effects=["npc_charmed"], chaos=2,
            )
        elif insight:
            actions.append({"type": "change_npc_trust", "target_id": tid, "delta": 1})
            actions.append({"type": "add_discovery", "text": target.get("dialogue") or "A clue settles in your journal."})
            spell = SpellResult(
                spell_name="Listening Sigil", spell_type="npc",
                flavor=_flavor_world(runes, target, combo),
                effect=target.get("dialogue") or "They share a useful clue.",
                status_effects=["npc_charmed"], chaos=2,
            )
        else:
            fear = intent == "fear"
            actions.append({"type": "change_npc_trust", "target_id": tid, "delta": -1 if fear else 0})
            effect = (target.get("dialogue") or "They blink at you.") if not fear \
                else "They recoil! Maybe lead with kindness next time."
            spell = SpellResult(
                spell_name="Awkward Overture" if fear else "Friendly Spark",
                spell_type="npc", flavor=_flavor_world(runes, target, combo),
                effect=effect, status_effects=["npc_scared"] if fear else [], chaos=1,
            )
        return {"spell": spell.model_dump(), "world_actions": actions, "target_id": tid, "runes": runes}

    # --- story object ------------------------------------------------------
    if ttype == "story_object":
        requires = target.get("requires", [])
        if tid == "nursery" and any(r in {"flame", "bone", "tooth"} for r in runes):
            text = "The nursery blackens. The shortcut smells useful and unforgiven."
            actions.append({"type": "set_entity_state", "target_id": tid, "state": "burned"})
            actions.append({"type": "add_discovery", "text": text})
            actions.append({"type": "add_journal_entry", "text": text})
            actions += _flag_actions(["fungus_colony_burned", "calendar_devour_pressure"])
            spell = SpellResult(
                spell_name="Spore Fire Receipt", spell_type="lore",
                flavor=_flavor_world(runes, target, combo), effect=text,
                status_effects=["enemy_burning"], chaos=6,
            )
            return {"spell": spell.model_dump(), "world_actions": actions, "target_id": tid, "runes": runes}
        if _matches_requirement(runes, requires, inventory):
            text = target.get("dialogue") or "The world gives up a small secret."
            actions.append({"type": "set_entity_state", "target_id": tid, "state": "read"})
            actions.append({"type": "add_discovery", "text": text})
            actions.append({"type": "add_journal_entry", "text": text})
            actions += _flag_actions(_STORY_FLAG.get(tid, ()))
            def grant_story_weapon(wid: str) -> None:
                if wid not in (player.get("weapon_inventory") or []):
                    actions.append({"type": "add_weapon", "weapon": wid})
                    actions.append({"type": "add_inventory", "item": story.WEAPONS[wid].label})
                if story.WEAPONS[wid].story_flag:
                    actions.extend(_flag_actions([story.WEAPONS[wid].story_flag]))

            if tid == "nursery":
                actions.append({"type": "add_inventory", "item": "Mirror Cap"})
                grant_story_weapon("mirror_shield")
            if tid == "bell_shrine":
                actions.append({"type": "add_inventory", "item": "Tollmaster Token"})
                grant_story_weapon("bell_staff")
            if tid == "clean_shrine":
                grant_story_weapon("river_thread")
            if tid == "dry_shelves":
                actions.append({"type": "unlock_shortcut", "target_id": "emotional_door",
                                "message": "Burned shelves opened a library shortcut, but worsened the ending pressure."})
            actions += _xp_actions(player, story.XP_READ_STORY)
            spell = SpellResult(
                spell_name="World-Reading Glyph", spell_type="lore",
                flavor=_flavor_world(runes, target, combo), effect=text,
                status_effects=["weakness_revealed"], chaos=3,
            )
        else:
            spell = SpellResult(
                spell_name="Unreadable Scratch", spell_type="lore",
                flavor=_flavor_world(runes, target, combo),
                effect=f"It needs: {' + '.join(requires)}.", chaos=1,
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
