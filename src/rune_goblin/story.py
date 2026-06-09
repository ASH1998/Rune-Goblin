"""Rune Goblin story, progression and content tables.

This module is the single source of truth for everything the three game plans
(`game_plans/game_plan.md`, `map_plan.md`, `story_plan.md`) call "durable":

* **Goblin classes** — the title-screen hero choices and their stats/affinities.
* **Weapons** — deterministic spell modifiers with a story identity.
* **Progression** — XP/level curve, level rewards, rune-mastery thresholds.
* **Story flags** — the allowlist of durable memory the world may set, plus the
  endings logic that reads them.
* **Dialogue tables** — deterministic NPC/boss/ending lines used as the LLM
  fallback (the plans require the game never stalls if the model is absent).

The Python side stays the balance authority: the browser renders and proposes,
but only values that pass through here (or :mod:`rune_goblin.world`) touch HP,
XP, inventory, flags or endings.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Goblin hero classes (title-screen character select)
# ---------------------------------------------------------------------------
# Stats follow map_plan.md "Recommended starting balance". `sprite` is the
# in-game runtime sprite is the exported hero sheet; `preview_gif` is the
# animated title-screen art from the pack.


@dataclass(frozen=True)
class GoblinClass:
    id: str
    label: str
    sprite: str  # runtime sprite_key drawn on the canvas
    preview_gif: str  # title-screen animated preview (under /rg/static/heroes)
    hp: int
    courage: int
    speed: int
    affinity: tuple[str, ...]  # rune keys this class is good at
    passive: str  # one-line passive summary
    king_ability: str  # final-evolution ability summary
    fantasy: str  # one-line playstyle summary
    select_line: str  # character-select flavor line
    king_line: str  # Goblin King transformation line


GOBLIN_CLASSES: dict[str, GoblinClass] = {
    "warrior": GoblinClass(
        id="warrior", label="Goblin Warrior", sprite="hero_warrior",
        preview_gif="heroes/GoblinWarrior.gif", hp=13, courage=5, speed=3,
        affinity=("closed_circle", "jagged_line"),
        passive="Shield affinity: +1 shield on circle spells.",
        king_ability="Warrior King: shield yourself and punish boss retaliation.",
        fantasy="Safe, balanced, direct.",
        select_line="You were hired for security. Unfortunately, the calendar was not secure.",
        king_line="The shield becomes a crown. The crown remembers every hit you took and gives one back.",
    ),
    "rogue": GoblinClass(
        id="rogue", label="Goblin Rogue", sprite="hero_rogue",
        preview_gif="heroes/GoblinRogue.gif", hp=10, courage=7, speed=4,
        affinity=("key", "coin", "thread"),
        passive="Key/coin affinity: better chests and shortcuts.",
        king_ability="Rogue King: open one final lock or phase weakness without a key.",
        fantasy="Clever, fast, greedy.",
        select_line="You have stolen coins, keys, and once, a suspiciously portable staircase.",
        king_line="Every stolen key turns in the air. The lock on tomorrow clicks.",
    ),
    "poison": GoblinClass(
        id="poison", label="Goblin Rogue Poison", sprite="hero_poison",
        preview_gif="heroes/GoblinRoguePoison.gif", hp=9, courage=7, speed=4,
        affinity=("leaf", "tooth", "broken_mark"),
        passive="Poison affinity: stronger status effects, more chaos risk.",
        king_ability="Poison King: apply a boss debuff that weakens repeated resistance.",
        fantasy="Risky, sneaky, status-heavy.",
        select_line="Your medicine works. The side effects are mostly rumors with legs.",
        king_line="The venom becomes medicine for the future and poison for the Beast.",
    ),
    "hunter": GoblinClass(
        id="hunter", label="Goblin Hunter", sprite="hero_hunter",
        preview_gif="heroes/GoblinHunter.gif", hp=11, courage=6, speed=4,
        affinity=("eye", "thread", "jagged_line"),
        passive="Eye affinity: better weakness reveals and first-strike bonuses.",
        king_ability="Hunter King: reveal and mark the true Calendar Beast weak point.",
        fantasy="Smart, tactical, ranged.",
        select_line="You can spot a weak point, a fake bridge, and a lying invoice at thirty paces.",
        king_line="You see the weak point at last: not the Beast's heart, but its hunger.",
    ),
    "barbarian": GoblinClass(
        id="barbarian", label="Goblin Barbarian", sprite="hero_barbarian",
        preview_gif="heroes/GoblinBarbarian.gif", hp=15, courage=4, speed=2,
        affinity=("flame", "bone", "tooth"),
        passive="Flame/bone affinity: higher damage, worse NPC trust if reckless.",
        king_ability="Barbarian King: break a boss pylon at the cost of courage.",
        fantasy="Strong, loud, simple.",
        select_line="You solve problems by entering the room before the door agrees.",
        king_line="You stop breaking doors. You become the door that breaks back.",
    ),
}

DEFAULT_CLASS = "warrior"


def class_or_default(class_id: str | None) -> GoblinClass:
    return GOBLIN_CLASSES.get(class_id or "", GOBLIN_CLASSES[DEFAULT_CLASS])


# ---------------------------------------------------------------------------
# Weapons — modify spells, never replace them (game_plan.md weapon system)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Weapon:
    id: str
    label: str
    identity: str
    school: tuple[str, ...]  # rune keys it boosts
    bonus_damage: int = 0  # extra damage when a school rune is used vs enemy
    courage_relief: int = 0  # reduces self curse/courage cost
    shield_chance: bool = False
    unlock_bonus: bool = False  # eases locks
    xp_bonus: int = 0
    npc_reaction: str = ""
    story_flag: str = ""  # flag set when first acquired/used


WEAPONS: dict[str, Weapon] = {
    "clerk_wand": Weapon(
        "clerk_wand", "Clerk Wand", "Official but weak.", (), bonus_damage=0,
        npc_reaction="You still have the training wand? Brave or underfunded.",
    ),
    "bell_staff": Weapon(
        "bell_staff", "Bell Staff", "Summons help, annoys goblins, interrupts bosses.",
        ("bell", "coin"), bonus_damage=1, xp_bonus=1,
        npc_reaction="Please stop ringing public infrastructure.",
        story_flag="tollmaster_route_open",
    ),
    "mirror_shield": Weapon(
        "mirror_shield", "Mirror Shield", "Defensive, reflective, patient.",
        ("mirror", "eye", "closed_circle"), shield_chance=True, courage_relief=1,
        npc_reaction="That shield shows people the version they were avoiding.",
        story_flag="calendar_repair_possible",
    ),
    "bone_blade": Weapon(
        "bone_blade", "Bone Blade", "Strong, scary, debt-heavy.",
        ("bone", "tooth", "broken_mark"), bonus_damage=2,
        npc_reaction="That knife has more opinions than most citizens.",
        story_flag="debt_deepened",
    ),
    "coin_sling": Weapon(
        "coin_sling", "Coin Sling", "Economy magic: tolls, bribery, secret merchant.",
        ("coin", "bell"), bonus_damage=1, unlock_bonus=True,
        npc_reaction="You weaponized payment. The goblins are moved.",
        story_flag="tollmaster_route_open",
    ),
    "river_thread": Weapon(
        "river_thread", "River Thread", "Utility, binding, repair, ally support.",
        ("wave", "leaf", "thread"), courage_relief=1, xp_bonus=1,
        npc_reaction="That thread smells like rain that forgave someone.",
        story_flag="calendar_repair_possible",
    ),
}

STARTING_WEAPON = "clerk_wand"


def weapon_or_default(weapon_id: str | None) -> Weapon:
    return WEAPONS.get(weapon_id or "", WEAPONS[STARTING_WEAPON])


# ---------------------------------------------------------------------------
# XP / leveling (game_plan.md level rewards)
# ---------------------------------------------------------------------------
# xp_to_next[level] = XP needed to advance FROM that level.
XP_TO_NEXT: dict[int, int] = {1: 8, 2: 16, 3: 28, 4: 44, 5: 0}
MAX_LEVEL = 5

# Reward applied on reaching each level (cumulative, applied once).
LEVEL_REWARDS: dict[int, dict] = {
    2: {"max_hp": 2, "note": "Level 2 — toughened up: +2 max HP."},
    3: {"unlock_four_runes": True, "note": "Level 3 — you can weave 4-rune casts."},
    4: {"rune_mastery_choice": True, "note": "Level 4 — choose a rune mastery."},
    5: {"max_courage": 2, "boss_ready": True,
        "note": "Level 5 — boss-ready power spike; ending branches unlocked."},
}

XP_DEFEAT_ENEMY = 6
XP_DEFEAT_BOSS_PHASE = 10
XP_READ_STORY = 3
XP_HELP_NPC = 4
XP_UNLOCK = 2


def xp_to_next(level: int) -> int:
    return XP_TO_NEXT.get(level, 0)


def apply_xp(level: int, xp: int, gained: int) -> tuple[int, int, list[dict]]:
    """Add ``gained`` XP; return (new_level, new_xp, list_of_level_reward_dicts)."""
    rewards: list[dict] = []
    xp += max(0, gained)
    while level < MAX_LEVEL:
        need = xp_to_next(level)
        if need <= 0 or xp < need:
            break
        xp -= need
        level += 1
        reward = dict(LEVEL_REWARDS.get(level, {}))
        reward["level"] = level
        rewards.append(reward)
    return level, xp, rewards


# Rune-mastery: count successful uses; at threshold a rune gets steadier.
RUNE_MASTERY_THRESHOLD = 5


# ---------------------------------------------------------------------------
# Story flags — the allowlist of durable memory (story_plan.md "Story Flags")
# ---------------------------------------------------------------------------
ALLOWED_FLAGS: frozenset[str] = frozenset({
    # trust / NPC
    "tourist_helped", "tourist_scared", "librarian_trust", "librarian_angry",
    "water_spirit_helped", "queue_goblin_paid", "queue_goblin_forced",
    # dungeon choices
    "mirror_truth_seen", "fungus_colony_spared", "fungus_colony_burned",
    "wet_catalog_read", "library_shelves_burned", "clean_water_restored",
    "sewer_valves_aligned", "sewer_shortcut_open",
    # debt / weapon
    "debt_accepted", "debt_repaid", "debt_deepened", "debt_receipt",
    "weapon_bought", "secret_merchant_met", "bone_market_entered",
    "secret_bell_shrine_seen",
    # toll road
    "toll_paid", "toll_forced",
    # mirror caverns
    "mycologist_defeated", "calendar_shard_1_taken",
    # ending
    "calendar_truth_read", "calendar_key_found", "calendar_repair_possible",
    "calendar_devour_pressure", "tollmaster_route_open",
    "calendar_beast_phase_2", "calendar_beast_phase_3",
    "pylon_eye_charged", "pylon_mirror_charged", "pylon_leaf_charged",
    "pylon_spiral_charged",
    "calendar_broken", "calendar_repaired", "calendar_devoured",
    "tollmaster_ending",
    "boss_ally_tourist", "boss_ally_librarian", "boss_ally_water",
    "arena_approach_reached", "debt_collector_spawned", "player_evolved",
})

# Flags that, when present, increase the "devour" pressure (bad-ending weight).
DEVOUR_FLAGS = ("library_shelves_burned", "debt_deepened", "debt_accepted",
                "fungus_colony_burned")
# Helpful flags that count toward the repaired ending.
HELPER_FLAGS = ("tourist_helped", "fungus_colony_spared", "librarian_trust",
                "clean_water_restored", "queue_goblin_paid")

# Final boss callbacks keyed to durable choices. These satisfy the story-plan
# requirement that the Beast's dialogue changes based on at least four flags.
BOSS_FLAG_REACTIONS: dict[str, str] = {
    "tourist_helped": "You brought a witness with sandwiches. Even hunger finds that irritating.",
    "tourist_scared": "The frightened one still runs in circles. I can eat circles.",
    "fungus_colony_spared": "The fungus showed you my fear. Rude, reflective little colony.",
    "fungus_colony_burned": "Smoke is a kind of future too: short, hot, and gone.",
    "librarian_trust": "The wet librarian filed an objection. I intend to eat the folder.",
    "library_shelves_burned": "Burned shelves make excellent kindling for devoured mornings.",
    "clean_water_restored": "Clean water enters my room and remembers a sky I never swallowed.",
    "queue_goblin_paid": "You paid the toll. That makes this officially inconvenient.",
    "queue_goblin_forced": "You forced the road open. Now the road has teeth.",
    "debt_repaid": "You closed a debt before I could hatch it. Uncharitable clerk.",
    "debt_deepened": "Borrowed power tastes best when the bill arrives late.",
    "calendar_truth_read": "You read the truth. Most meals do not read the menu back.",
}


def is_allowed_flag(flag: str) -> bool:
    return flag in ALLOWED_FLAGS


def filter_flags(flags) -> list[str]:
    """Keep only allowlisted flags, de-duplicated and ordered."""
    seen: set[str] = set()
    out: list[str] = []
    for f in flags or ():
        if f in ALLOWED_FLAGS and f not in seen:
            seen.add(f)
            out.append(f)
    return out


def boss_flag_reactions(flags, *, limit: int = 2) -> list[str]:
    """Return short Beast lines for known flags, preserving flag order."""
    out: list[str] = []
    for flag in filter_flags(flags):
        line = BOSS_FLAG_REACTIONS.get(flag)
        if line and line not in out:
            out.append(line)
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# Endings (story_plan.md "Endings" + game_plan.md ending logic)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Ending:
    key: str
    title: str
    text: str


ENDINGS: dict[str, Ending] = {
    "repaired": Ending(
        "repaired", "🌅 Calendar Repaired",
        "You do not kill tomorrow. You teach it where to stand. The calendar "
        "closes its teeth, opens its pages, and gives everyone one honest morning.",
    ),
    "tollmaster": Ending(
        "tollmaster", "🪙 The Secret Tollmaster",
        "The Beast offers you the road. You accept, because someone has to "
        "organize the chaos. New law: all tolls may be paid in coins, sandwiches, "
        "or sincere spellcraft.",
    ),
    "devoured": Ending(
        "devoured", "🌑 Calendar Devoured",
        "The Beast falls forward, smiling. It does not eat you. It eats every "
        "morning you were not careful enough to protect.",
    ),
    "broken": Ending(
        "broken", "🏆 Calendar Broken",
        "The Beast falls. Tomorrow returns, slightly dented. The Toll Road "
        "reopens with a new sign: DO NOT RING THE BELL UNLESS SUPERVISED.",
    ),
}


def compute_ending(flags, final_runes=(), weapon: str | None = None,
                   mastery=None) -> Ending:
    """Pick the ending from durable flags + the runes used in the final blow.

    Priority: Tollmaster (secret) > Repaired (good) > Devoured (bad) > Broken
    (default). This matches the requirement gating in story_plan.md.
    """
    flagset = set(flags or ())
    final = set(final_runes or ())
    mastery = mastery or {}

    # Secret Tollmaster: coin/bell mastery + paid/spared goblin + secret merchant.
    coin_bell_mastery = (mastery.get("coin", 0) >= RUNE_MASTERY_THRESHOLD or
                         mastery.get("bell", 0) >= RUNE_MASTERY_THRESHOLD or
                         (weapon in {"coin_sling", "bell_staff"}))
    if ("tollmaster_route_open" in flagset and "queue_goblin_paid" in flagset
            and "secret_merchant_met" in flagset and coin_bell_mastery):
        return ENDINGS["tollmaster"]

    # Calendar Repaired: read truth + >=2 helper flags + repair rune in final blow.
    repair_runes = {"eye", "mirror", "spiral", "wave", "leaf"}
    helpers = len(flagset & set(HELPER_FLAGS))
    if ("calendar_truth_read" in flagset and helpers >= 2
            and (final & repair_runes)):
        return ENDINGS["repaired"]

    # Calendar Devoured: high devour pressure.
    pressure = len(flagset & set(DEVOUR_FLAGS))
    if "calendar_devour_pressure" in flagset or pressure >= 2:
        return ENDINGS["devoured"]

    return ENDINGS["broken"]


def ending_choice_lines(flags, final_runes=(), weapon: str | None = None,
                        goblin_class: str | None = None, mastery=None,
                        evolved: bool = False) -> list[str]:
    """Short deterministic ending receipts naming concrete player choices.

    story_plan.md requires every ending to acknowledge specific choices the
    player made. These lines are deliberately factual and sourced only from
    durable state the deterministic rules own.
    """
    flagset = set(flags or ())
    final = set(final_runes or ())
    mastery = mastery or {}
    lines: list[str] = []

    cls = class_or_default(goblin_class)
    hero = f"You ended the loop as the {cls.label}"
    if evolved or "player_evolved" in flagset:
        hero += ", crowned into Goblin King"
    lines.append(hero + ".")

    if "calendar_truth_read" in flagset:
        lines.append("You read the wet calendar truth before the final choice.")
    if "tourist_helped" in flagset:
        lines.append("The Lost Tourist remembered your kindness at the gate.")
    elif "tourist_scared" in flagset:
        lines.append("The Lost Tourist remembered being frightened by your magic.")
    if "fungus_colony_spared" in flagset:
        lines.append("The fungus colony survived to point at the Beast's fear.")
    elif "fungus_colony_burned" in flagset:
        lines.append("The burned fungus made the future smell like smoke.")
    if "librarian_trust" in flagset:
        lines.append("The Mold Librarian trusted you because you listened.")
    elif "librarian_angry" in flagset or "library_shelves_burned" in flagset:
        lines.append("The library kept the scorch marks in its testimony.")
    if "clean_water_restored" in flagset or "water_spirit_helped" in flagset:
        lines.append("Clean water reached the arena as an ally.")
    if "queue_goblin_paid" in flagset:
        lines.append("The Queue Goblin respected that you paid or rang the toll properly.")
    elif "queue_goblin_forced" in flagset:
        lines.append("The Queue Goblin filed you under walking incident report.")
    if "debt_repaid" in flagset:
        lines.append("You repaid a debt before it could become another monster.")
    elif "debt_deepened" in flagset or "debt_accepted" in flagset:
        lines.append("You carried borrowed power into the ending, interest included.")
    if weapon and weapon in WEAPONS and weapon != STARTING_WEAPON:
        lines.append(f"Your {WEAPONS[weapon].label} shaped the final spell.")

    mastered = [r for r, count in mastery.items() if count >= RUNE_MASTERY_THRESHOLD]
    if mastered:
        label = mastered[0].replace("_", " ")
        lines.append(f"Your mastered {label} rune held steady when tomorrow buckled.")
    elif final:
        label = ", ".join(sorted(r.replace("_", " ") for r in final))
        lines.append(f"Your final rune weave was {label}.")

    # Keep the end screen readable; the full journal still carries deeper detail.
    out: list[str] = []
    for line in lines:
        if line not in out:
            out.append(line)
        if len(out) >= 5:
            break
    return out


# ---------------------------------------------------------------------------
# Boss phases (game_plan.md / map_plan.md Calendar Beast Arena)
# ---------------------------------------------------------------------------
# Calendar Beast has 24 max HP. Phase thresholds at 66% (16) and 33% (8).
BOSS_PHASES: list[dict] = [
    {"phase": 1, "min_ratio": 0.66, "weakness": ["spiral", "eye"],
     "resistance": ["flame"], "line": "Show me the language you broke me with.",
     "banner": "PHASE 1 — The Beast watches your runes."},
    {"phase": 2, "min_ratio": 0.33, "weakness": ["mirror", "wave"],
     "resistance": ["flame", "jagged_line"],
     "line": "I know that spell now. Draw a new mistake.",
     "banner": "PHASE 2 — It resists what you repeat."},
    {"phase": 3, "min_ratio": 0.0, "weakness": ["leaf", "spiral", "eye"],
     "resistance": ["flame"],
     "line": "Break me and the loop ends. Repair me and the future returns.",
     "banner": "PHASE 3 — Choose what tomorrow becomes."},
]


def boss_phase_for(hp: int, max_hp: int) -> dict:
    ratio = hp / max_hp if max_hp else 0
    for ph in BOSS_PHASES:
        if ratio > ph["min_ratio"]:
            return ph
    return BOSS_PHASES[-1]


# Goblin King evolution trigger (story_plan.md baseline trigger).
def can_evolve(level: int, flags, boss_phase: int) -> bool:
    flagset = set(flags or ())
    identity = bool(flagset & set(HELPER_FLAGS)) or bool(flagset & set(DEVOUR_FLAGS))
    return boss_phase >= 3 and (level >= 5 or identity) and "player_evolved" not in flagset


# ---------------------------------------------------------------------------
# Deterministic dialogue fallback tables (story_plan.md "Main Cast")
# ---------------------------------------------------------------------------
# Keyed by NPC entity id. Each entry: greeting + reactions keyed by an intent
# bucket the world derives from runes ("kind", "fear", "insight", "coin",
# "bell", "neutral"). The LLM, when present, overrides flavor; these guarantee
# the game never stalls and quest-critical clues are always available.
@dataclass
class NpcVoice:
    name: str
    greeting: str
    reactions: dict[str, str] = field(default_factory=dict)
    journal: str = ""  # durable discovery line written on first meaningful talk


NPC_VOICES: dict[str, NpcVoice] = {
    "toll_goblin": NpcVoice(
        name="Queue Goblin",
        greeting="Road's closed. Calendar's screaming. Toll is one coin, one apology, "
                 "or one legally confusing spell.",
        reactions={
            "coin": "Payment accepted. I hate how responsible that was.",
            "bell": "Do not ring that. I am emotionally hourly.",
            "fear": "Oh great. The walking incident report.",
            "neutral": "If you broke time, stand in the left line. If you only "
                       "damaged it, right line.",
        },
        journal="Queue Goblin guards the Toll Road. It hates bells and respects coins.",
    ),
    "tourist": NpcVoice(
        name="Lost Tourist",
        greeting="Excuse me. Is this the road to Tuesday? My map keeps biting me.",
        reactions={
            "kind": "Oh. That made the panic quieter. Are you allowed to do kind magic?",
            "fear": "I understand less than before, but much faster.",
            "neutral": "Please do not attack the map. It has already won twice.",
        },
        journal="The Lost Tourist calms to wave/leaf and may bring a healing lunch later.",
    ),
    "watch_archer": NpcVoice(
        name="Blue Watch Archer",
        greeting="Face the thing you mean to bother. Runes are powerful, not polite.",
        reactions={
            "insight": "Weakness matters. A small correct spell beats a dramatic wrong one.",
            "neutral": "When a boss changes stance, stop repeating yourself. The "
                       "calendar learns.",
        },
        journal="Blue Watch Archer: face a target, read its weakness, then exploit it.",
    ),
    "road_druid": NpcVoice(
        name="Road Druid",
        greeting="Calendars are just gardens with numbers. Yours has weeds.",
        reactions={
            "kind": "Leaf repairs. Wave forgives. Use both where a place forgot how "
                    "to be alive.",
            "neutral": "The sewer water remembers the clean version of itself. Help "
                       "it remember louder.",
        },
        journal="Road Druid points to leaf/wave repair routes and the Clock Sewer.",
    ),
    "toll_pixie": NpcVoice(
        name="Toll Pixie",
        greeting="The goblin hates bells and coins. Just saying.",
        reactions={"neutral": "Bell to annoy, coin to pay. Either gets you past the gate."},
        journal="Toll Pixie hint: the gate goblin yields to bell or coin.",
    ),
    "cave_hermit": NpcVoice(
        name="Mirror Hermit",
        greeting="Do not swing at mirrors unless you want a very accurate enemy.",
        reactions={
            "insight": "Eye shows. Mirror admits. Together they make cowards of secrets.",
            "fear": "Fire is an answer. It is just rarely the last one.",
            "kind": "Good. The colony will tell the Beast where its own fear lives.",
            "neutral": "The fungus is not hiding a shard. It is remembering one.",
        },
        journal="Mirror Hermit: solve the fungus with mirror+eye, not fire.",
    ),
    "librarian": NpcVoice(
        name="Mold Librarian",
        greeting="Quiet. The books are damp, frightened, and legally witnesses.",
        reactions={
            "insight": "Good. A person who reads before exploding things. I had hoped "
                       "the species was not finished.",
            "fear": "That was a century of notes and three perfectly dry jokes.",
            "neutral": "The Calendar Key is ink-locked. It opens for readers, not burglars.",
        },
        journal="Mold Librarian: the Calendar Key is ink-locked — key + eye + wave.",
    ),
    "lost_wisp": NpcVoice(
        name="Index Wisp",
        greeting="Key plus Eye plus Wave. The chest likes calm witnesses.",
        reactions={"neutral": "If lost: follow the wet floor. It is going somewhere "
                              "against policy."},
        journal="Index Wisp: the Ink-Locked Chest opens to key + eye + wave.",
    ),
    "red_guard": NpcVoice(
        name="Red Guard",
        greeting="The boss resists flame. Spiral and eye fold time around it.",
        reactions={"insight": "Spiral and eye. The Beast is overbooked; confuse its schedule."},
        journal="Red Guard: the Calendar Beast resists flame; spiral + eye work.",
    ),
    "market_merchant": NpcVoice(
        name="Bone Market Merchant",
        greeting="Welcome to the Bone Market. Prices are low because some are metaphorical.",
        reactions={
            "coin": "Responsible customers are terrible for business and wonderful for endings.",
            "bell": "A bell-ringer! Sit. The secret stock is for people who make noise.",
            "fear": "Excellent. Your future has approved the loan by screaming.",
            "neutral": "I sell weapons, refunds, and mistakes with handles.",
        },
        journal="Bone Market Merchant sells weapons; coins repay debt, curses deepen it.",
    ),
    "water_spirit": NpcVoice(
        name="Water Spirit",
        greeting="I used to be a river. Now I am a hallway with regrets.",
        reactions={
            "kind": "The water remembers the sky. So will I.",
            "neutral": "Wave moves water. Leaf reminds it why. Clean me and I carry "
                       "one kindness to the final room.",
        },
        journal="Water Spirit: restore clean flow with wave + leaf for a final ally.",
    ),
    "secret_merchant": NpcVoice(
        name="Hooded Merchant",
        greeting="Psst. Coin and bell mastery? The Tollmaster's road is hiring.",
        reactions={
            "coin": "A paying customer with taste. The secret route opens for you.",
            "bell": "You ring like someone who pays their tolls. Welcome to the inner market.",
            "neutral": "Tolls, sandwiches, or sincere spellcraft — all accepted here.",
        },
        journal="Hooded Merchant hints at the secret Tollmaster ending (coin/bell mastery).",
    ),
    "debt_collector": NpcVoice(
        name="Debt Collector",
        greeting="You opened three doors with one apology. I am here for the other two.",
        reactions={
            "coin": "Fine. Consider the account emotionally closed.",
            "neutral": "Debt is just a monster that learned accounting.",
        },
        journal="Debt Collector appears when forced shortcuts go unpaid.",
    ),
    "gate_librarian": NpcVoice(
        name="Mold Librarian",
        greeting="For the record, I object to being eaten by an overdue date.",
        reactions={
            "insight": "When the Beast asks what you are, say: a clerk who learned to listen.",
            "neutral": "The Calendar Key opened a gate. Your choices decide what comes through it.",
        },
        journal="The Mold Librarian reached the gate because the library trusted careful magic.",
    ),
    "gate_water_spirit": NpcVoice(
        name="Water Spirit",
        greeting="The clean river enters the room.",
        reactions={
            "kind": "The water remembers the sky. So will the final room.",
            "neutral": "Clean water carries one kindness into the Beast's arena.",
        },
        journal="The restored water reached the Calendar Gate as a final ally.",
    ),
    "gate_queue_goblin": NpcVoice(
        name="Queue Goblin",
        greeting="I am only helping because the Beast owes toll.",
        reactions={
            "coin": "Payment accepted again. This is becoming suspiciously civic.",
            "bell": "Do not ring that near the Beast unless you mean it.",
            "neutral": "The clerk! Still alive, still undertrained. Respect.",
        },
        journal="The Queue Goblin respects paid tolls and may help the Tollmaster route.",
    ),
}


BOSS_VOICE: dict[str, str] = {
    "intro": "Little clerk. You rang the bell. I answered. I am simply hungry, "
             "and your tomorrow was left unattended.",
    "phase1": "Show me the language you broke me with.",
    "phase2": "I know that spell now. Draw a new mistake.",
    "phase3": "Break me, repair me, or feed me. Choose what tomorrow becomes.",
    "defeat": "Then take your morning. It was always too bright for me.",
}


def npc_intent(runes) -> str:
    """Bucket a rune list into the dialogue intent the fallback tables key on."""
    rset = set(runes or ())
    if "coin" in rset:
        return "coin"
    if "bell" in rset:
        return "bell"
    if rset & {"wave", "leaf"}:
        return "kind"
    if rset & {"eye", "mirror", "spiral"}:
        return "insight"
    if rset & {"flame", "bone", "tooth", "jagged_line", "broken_mark"}:
        return "fear"
    return "neutral"


def fallback_dialogue(npc_id: str, runes=()) -> dict:
    """Deterministic dialogue payload for an NPC + rune intent.

    Returns the same shape the LLM endpoint produces so callers are uniform.
    """
    voice = NPC_VOICES.get(npc_id)
    if voice is None:
        return {
            "story_toast": "", "npc_line": "They blink at you, professionally.",
            "journal_entry": "", "suggested_story_flag": "", "mood_shift": "",
        }
    intent = npc_intent(runes)
    line = voice.reactions.get(intent) or voice.greeting
    return {
        "story_toast": "",
        "npc_line": f"{voice.name}: {line}",
        "journal_entry": voice.journal,
        "suggested_story_flag": "",
        "mood_shift": "",
    }
