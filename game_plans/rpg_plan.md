# Rune Goblin RPG Plan: Phase 2 — From Complete Campaign To Proper RPG

## Summary

Phase 1 delivered the campaign: seven authored maps, character select, story
flags, beats, four endings, and the LLM dialogue layer. But the RPG systems
underneath are shallow. The level cap is 5 and a full run earns less than 100
XP. Monsters are 5-8 HP melee sacks that drop a trophy and a coin or two.
Weapons are flat +1/+2 bonuses with no upgrade path. Gold piles up with nothing
to buy. Combat resolves instantly with no enemy variety, telegraphs, or
tension. Evolution is a single automatic jump to Goblin King. A page refresh
loses the entire run.

Phase 2 turns this into a proper RPG: a 20-level curve with rewards every
level, a tiered monster system with abilities and telegraphs, real loot with
rarity and LLM-christened drops, weapon reforging and a trinket slot, crits and
knockback and potion quick-use, a three-tier evolution chain (base goblin →
class champion form → Goblin King via relic), and localStorage persistence.

Locked decisions:

- Level cap 20. Tier-2 evolution at level 10. Goblin King requires the Cracked
  Crown item plus level 16+ (no longer automatic at boss phase 3).
- Combat deepens the existing real-time hybrid. Not turn-based.
- Persistence via localStorage autosave with Continue/New Game on the title
  screen.
- LLM expansion limited to loot/item flavor and combat narration/taunts.

The sacred constraint from Phase 1 stays: Python is the deterministic
authority, the LLM writes prose inside Python-rolled bands (the `price_band`
shop-haggle pattern), and the client only executes validated `world_actions`.
Every new system below extends the existing action vocabulary; nothing is
rewritten.

## 1. Leveling 1-20

### XP Curve

Replace `MAX_LEVEL` and `XP_TO_NEXT` in `src/rune_goblin/story.py` (currently
line ~181). Same data shape, so `apply_xp()` and the client `level_up` handler
keep working.

```python
MAX_LEVEL = 20
XP_TO_NEXT = {1: 10, 2: 14, 3: 18, 4: 22, 5: 26, 6: 30, 7: 34, 8: 38, 9: 44,
              10: 50, 11: 56, 12: 62, 13: 70, 14: 78, 15: 86, 16: 96,
              17: 106, 18: 118, 19: 130, 20: 0}
```

| Reach level | Cumulative XP | Demo expectation |
|---|---|---|
| 5 | 64 | end of caverns/library |
| 8 | 154 | after sewer + market |
| 10 | 236 | gate approach — tier-2 evolution |
| 12 | 342 | arena entry on a thorough run |
| 16 | 638 | requires frost_pass / ember_foundry optional content |
| 20 | 1088 | completionist / post-demo |

### XP Source Rebalance

Kills must matter. Replace the flat constants in story.py with tier-driven
values computed in `world.py` when emitting `add_xp` (DR = area difficulty
rating, see section 2):

| Source | XP |
|---|---|
| Minion kill | 4 |
| Standard kill | 6 + 2×DR (8-16) |
| Elite kill | 14 + 4×DR (22-38) |
| Boss phase | 30 (up from 10) |
| Respawned-enemy kill | 50% of the above, floored |
| Read story object | 4 |
| Help NPC | 6 |
| Unlock / shortcut | 3 |
| Quest turn-ins | 12 / 15 / 20 (the three existing quests, by order) |

Demo budget: ~6 minions + ~20 standards + ~4 elites + 3 boss phases + quests
and story reads ≈ 330-380 XP, landing a demo player at level 11-12 by the boss
naturally. Level 16 needs ~300 more XP — exactly the two optional bonus areas.

### Per-Level Rewards

Baseline: +1 max HP every level (folded into the `LEVEL_REWARDS` table).
Milestones on top:

| Level | Reward |
|---|---|
| 2 | +2 max HP (kept from Phase 1) |
| 3 | Four-rune casts (kept) |
| 4 | Rune mastery choice #1 (kept) |
| 5 | +2 max courage (kept, minus the old `boss_ready` gate) |
| 6 | +1 spell power (new flat stat added to every cast's damage) |
| 7 | Potion belt slot 2 (quick-use, section 5) |
| 8 | Crit unlocked: base 10% |
| 9 | +2 max HP |
| 10 | Evolution: tier-2 class form — +3 max HP, +1 spell power, class perk upgrade |
| 11 | +1 max courage |
| 12 | Rune mastery choice #2 |
| 13 | +5% crit |
| 14 | +2 max HP |
| 15 | Crits knock the target back 1 tile |
| 16 | Goblin King eligible (still needs the Cracked Crown) |
| 17 | +1 spell power |
| 18 | +5% crit |
| 19 | +2 max HP |
| 20 | Capstone "Calendar Sovereign": +1 spell power, +5% crit, +2 max HP |

Max HP grows from 10 to roughly 23 at level 10 and ~37 at level 20.
`spell_power` is a new int on the player dict; `resolve_world_cast()` adds it
to raw damage exactly like the existing weapon `bonus_damage` term.

### Level Gates

- `frost_pass` portal: locked below level 6 ("The pass wind pushes back
  novices").
- `ember_foundry` portal: locked below level 8.
- Arena door: soft gate — Queue Goblin warns below level 10 but never blocks
  (the demo must always be finishable).
- Reforge tier +3 at the smith: requires level 12.

## 2. Monster System

### Tiers And Area Difficulty Rating

Scale by authored area DR, not player level — deterministic, debuggable, and
hand-placed story encounters keep their identity. The `_enemy()` helper in
`world.py` gains `tier="standard"`, and HP/damage become derived.

| Area | DR |
|---|---|
| overworld | 1 |
| caverns, library, bone_market | 2 |
| clock_sewer | 3 |
| gate_approach, frost_pass | 4 |
| ember_foundry | 5 |
| arena | 6 |

Stat formulas (server-authored, shipped in the `/rg/world` payload — the
client never invents numbers):

| Tier | HP | Melee dmg | Move cadence | XP | Visual |
|---|---|---|---|---|---|
| minion | 3 + 2×DR | 1 | every 2 turns | 4 | small sprite, HP bar only once hit |
| standard | 6 + 3×DR | 1 + ⌊DR/2⌋ | existing 1-in-3 | 6 + 2×DR | as today |
| elite | 12 + 5×DR | 2 + ⌊DR/2⌋ | every turn within 6 | 14 + 4×DR | gold outline + affix prefix |
| boss | hand-authored phases | 3-5 | scripted | 30/phase | as today |

Re-tag the existing ~15 hand-placed enemies (most become `standard`; the
Mirror Mycologist, Debt Collector, and 2-3 new placements become `elite`). Add
2-4 minion packs per area so the kill-XP economy works.

### Enemy Abilities — Four Archetypes With Telegraphs

All run inside the existing `enemyTurn()` loop and status pipeline
(`tickStatuses`, status icons). A telegraph is a status on the enemy rendered
as an icon above its HP bar (Mythril Age icons) plus a pulsing overlay on
threatened tiles. Behavior scripts live in the client, but every number
(damage, range, cooldown) is authored on the entity definition in `world.py` —
the same authority split as movement today.

1. **Charge** (1-turn windup). Turn A: if the player is in a straight line
   within 4 tiles, set `windup_charge` and highlight the line. Turn B: dash up
   to 3 tiles along the line; on contact, 2× melee damage and knock the player
   back 1 tile. Dodged by stepping off the line. Users: sewer pike-rats,
   foundry brutes.
2. **Spit** (ranged). If the player is 2-4 tiles away, set `windup_spit` and
   mark the player's current tile. Next turn the projectile hits that tile
   (not the player) for 1× melee plus `burn 2` (fungi) or `slow 1` (frost).
   Dodged by moving. Users: fungi, frost lurkers.
3. **Summon** (elite/boss only). Every 4 turns, if fewer than 3 of its minions
   are alive: spawn 1-2 minions on adjacent walkable tiles via the existing
   `spawn_entity` action. Telegraph: `windup_summon` for 1 turn.
4. **Enrage** (one-shot, below 33% HP). +1 melee damage, moves every turn, red
   tint, permanent `enraged` status, fires the LLM taunt event "enrage"
   (section 8). Users: all elites and boss phases.

New enemy statuses: `windup_charge`, `windup_spit`, `windup_summon` (1 turn
each), `enraged` (permanent), `slow` (skip next move, 1-2 turns). Stun and
calm already cancel windups for free — a bell interrupting a charge is
emergent counterplay that needs zero extra code.

### Respawn Policy

- Every entity gets `unique: true|false`. All current story encounters,
  elites, bosses, and quest targets are `unique` — permanent defeat, exactly
  as today.
- Non-unique minions/standards respawn at their spawn point when the player
  re-enters the area after at least 2 intervening area transitions (tracked in
  a client-side defeats ledger `{entity_id: transition_counter}` persisted by
  the save system).
- Respawned kills award 50% XP and gold, never quest items, never rare drops.
  Grinding is possible, but optional content is always better.

### Elite Affixes

One affix per elite, authored deterministically and shown as a name prefix:

| Affix | Effect | Counterplay |
|---|---|---|
| Shielded | starts with `shield 2`, reapplies on enrage | `broken_mark` pierces shields |
| Vampiric | heals 1 per successful melee | kill its summons first |
| Splitting | spawns 2 minions on death | calm before the kill suppresses it |
| Hexed | melee also drains 1 courage | mirror_shield reflects the hex |
| Stonehide | one extra resistance school | reveal_weakness combo bypasses |

## 3. Loot And Drops

### Drop Tables Per Tier

Rolled in Python inside `resolve_world_cast()` when emitting defeat actions,
delivered through the existing `add_gold` / `add_item` actions. New materials:
`rune_grit` and `warped_cog` (added to the `quests.py` ITEMS bag).

| Tier | Gold | Materials | Consumables | Gear |
|---|---|---|---|---|
| minion | 1-2 | 20% rune_grit | 8% health_potion | — |
| standard | 2-4 | 35% rune_grit | 12% potion/draught | 5% rare trinket |
| elite | 6-10 | 2× rune_grit + 60% warped_cog | 25% potion | 30% rare trinket + guaranteed monster_trophy |
| boss phase | 10-15 | 1× warped_cog | — | guaranteed epic (phase 2 = Cracked Crown) |
| chest | 3-6 | 50% rune_grit | 30% | bonus areas: 1 guaranteed rare each |

Expected demo income: ~90-130 gold against ~100-140 gold of sinks (section 4)
— gold finally matters.

### Rarity Tiers

- **Common**: materials and potions. Static names.
- **Rare**: trinkets with one stat roll. LLM-christened.
- **Epic**: trinkets with two stat rolls, or unique relics (Cracked Crown).
  LLM-christened; relics keep their authored names.

### LLM Christening (mirror of `price_band`)

Python rolls everything:
`{"slot": "trinket", "rarity": "rare", "stats": {"crit": 5}, "school": "ember",
"area": "ember_foundry", "seed": N}`. Stat pool: `bonus_damage +1`, `crit +5`,
`max_hp +2`, `courage_relief +1`, `gold_find +1`, `xp_bonus +1` (epic = two
distinct rolls). The LLM receives the spec and returns only
`{name, flavor}` — name clipped to 32 chars, flavor to 140, placeholders
stripped, deterministic fallback table on failure
(`"{School} Charm of the {Area}"` plus canned flavor). The item id is
deterministic (`trinket_<seed>`); the LLM name is cosmetic display text stored
alongside. Stats never touch the LLM.

## 4. Weapons And Gear

### Weapon Reforge Tiers

The six story weapons keep their identities. The Hooded Merchant at the Bone
Market gains a Reforge tab (extends the existing shop UI and `/rg/shop`
endpoint). Reuses the existing `upgrade_weapon` world_action.

| Tier | Cost | Effect |
|---|---|---|
| +1 | 6 gold + 2 rune_grit | +1 bonus_damage |
| +2 | 12 gold + 4 rune_grit + 1 warped_cog | +1 bonus_damage, +5% crit |
| +3 (level 12+) | 20 gold + 2 warped_cog | +1 bonus_damage, perk amplified |

Tier +3 perk amplification per weapon: mirror_shield shield_chance doubled;
bell_staff and river_thread xp_bonus +1; coin_sling gold_find +1; bone_blade
curse cost waived; clerk_wand becomes "Senior Clerk Wand" (+1 courage_relief —
the joke weapon, viable).

Stored as `P.weapon_tiers = {weapon_id: 0..3}`. `resolve_world_cast()` reads
the tier from the player payload it already receives and clamps to 0-3 —
Python stays authoritative.

### Gear Scope: One Trinket Slot, No Armor

Hackathon-sane: exactly one trinket slot (`P.trinket`). Trinkets come only
from drops. Swapping is free in the inventory panel. No armor — defense is
covered by mirror_shield, shield statuses, and the new ward_salve.

### Gold Sinks

| Sink | Price |
|---|---|
| Weapon reforge chain | 38 gold total per weapon |
| health_potion | 3 |
| courage_draught | 4 |
| ward_salve (new: grants `shield 2`) | 5 |
| Trinket reroll (rerolls stat, new LLM name) | 8 |
| Existing tolls/bribes | unchanged |

## 5. Combat Feel

All randomness is rolled in Python (seeded, inside `resolve_world_cast()`) and
shipped as action fields; the client only animates.

### Crits

- Crit chance: 0 before level 8, then 10% base, +5% at levels 13/18/20,
  +weapon tier +2 bonus, +trinket bonus, and +10% when the cast contains the
  player's mastered rune (mastery felt in every fight). Cap 40%.
- Crit = ×1.5 final damage, rounded up.
- The cast response gains `"crit": true`; the existing `set_entity_hp` carries
  the final number. Client: bigger gold damage float, heavy screen shake,
  `star` VFX burst.

### Damage Variance

After all bonuses: `dmg += rng.choice([-1, 0, 0, 1])`, floored at 1 if
pre-variance damage was positive. Small, but kills the "every cast is
identical" feel.

### Knockback

- New world_action `{"type": "knockback_entity", "target_id": id, "dx": ±1,
  "dy": ±1}` — the client moves the entity 1 tile away from the player if the
  tile is walkable and unoccupied (client validates geometry; Python decides
  that knockback happens).
- Emitted on crits (from the level-15 reward) and on any single cast dealing
  6+ damage.
- Player knockback from Charge hits is purely client behavior, like enemy
  melee today.

### Potion Quick-Use

Keys `1` and `2` form the potion belt (slot 2 unlocks at level 7). The belt
auto-fills from the bag (health_potion in 1, courage_draught/ward_salve in 2,
configurable in the inventory panel). Drinking costs the move that turn — the
enemy still acts — which is the real-time-hybrid tension. Pure client change
reusing the existing item-consume path.

### Telegraph Rendering

Windup statuses render as a 16px icon above the HP bar (Mythril Age icons:
crossed swords for charge, droplet for spit, magic swirl for summon) plus a
pulsing red overlay on threatened tiles. One new `drawTelegraphs()` call in
the render loop; the data comes entirely from the status map.

### New World Actions

| Action | New? | Purpose |
|---|---|---|
| `apply_status {target_id, status, turns}` | new | lets Python apply any status outside the cast path |
| `knockback_entity {target_id, dx, dy}` | new | crit/heavy-hit knockback |
| `evolve_player {tier, form, note}` | new | sprite swap + stat grants + VFX, replaces the ad-hoc king logic |
| everything else | existing | `set_entity_hp`, `defeat_entity`, `spawn_entity`, `add_item`, `add_gold`, `add_xp`, `upgrade_weapon`, ... reused |

## 6. Evolution Chain

### Tiers

| Tier | Levels | Sprite source | Name |
|---|---|---|---|
| 1 — Goblin | 1-9 | existing Goblin Pack #1 heroes | as today |
| 2 — class form | 10+ (automatic on level-up) | Tiny Swords units | below |
| 3 — Goblin King | 16+ and consumes the Cracked Crown | existing `hero_king` | Goblin King |

### Tier-2 Class Mapping (Tiny Swords, 192×192 frames)

| Class | Tiny Swords unit + color | Tier-2 name | Perk upgrade at evolution |
|---|---|---|---|
| warrior | Warrior, red | Goblin Champion | retaliation damage taken -1 (min 0) |
| rogue | Lancer, purple | Goblin Reaver | +5% crit |
| poison | Monk, green | Goblin Plaguewarden | burn/poison statuses last +1 turn |
| hunter | Archer, blue | Goblin Sharpeye | reveal_weakness bonus +1 |
| barbarian | Torch Goblin (Update 010), red | Goblin Ravager | knockback threshold 5 dmg instead of 6 |

All tier-2 forms also grant +3 max HP and +1 spell power (the level-10 reward
row).

### Goblin King Via The Cracked Crown

- Primary source: guaranteed drop when boss phase 2 ends (emitted inside the
  existing `start_boss_phase` phase-3 action batch) — a level-16 player can
  crown themselves mid-boss-fight, which is the best demo beat in the game.
- Optional early source: a new mini-gauntlet in ember_foundry ("Foundry
  Coronation": defeat 3 elites guarding the Mold Crucible) ends in a chest
  with the Cracked Crown — the path for players who did optional content and
  hit 16 before the arena.
- Using the Crown below level 16: deterministic refusal toast ("The crown
  weighs your résumé and finds it thin"). At 16+: consume it, emit
  `evolve_player {tier: 3, form: "hero_king"}`, set the existing
  `player_evolved` flag, grant +5 max HP, +2 spell power, +10% crit, +2 max
  courage.
- `can_evolve()` in story.py is rewritten to this rule; the boss-phase-3
  auto-evolution path is removed.

### Transformation VFX And Asset Pipeline

VFX: tier-2 = `holy` sheet (already in manifest) + screen flash + 1.2 s input
lock; King = `explosion_big` + `star` shower.

Pipeline (mirrors how the Phase-1 heroes were promoted):

1. Copy idle sheets from
   `assets/Tiny Swords (Free Pack)/Tiny Swords (Free Pack)/Units/...` (idle is
   enough for MVP; run/attack sheets are stretch).
2. Place at `app/rpg_static/sprites/heroes/champion_<class>.png` — the sheets
   are already horizontal strips (e.g. Warrior 1536×192 = 8 frames); confirm
   with `sips -g pixelWidth` and crop only if a sheet bundles rows.
3. Add manifest entries:
   `{"file": "sprites/heroes/champion_warrior.png", "fw": 192, "fh": 192,
   "frames": 8}`.
4. In rpg.js the hero sprite key becomes a function of
   `(goblin_class, evolution_tier)`; the king already proves big-source
   sprites scale fine.

## 7. Save System

### Schema

localStorage key `rg_save`, single slot, versioned:

```json
{
  "version": 1,
  "ts": 1760000000,
  "seed": 12345,
  "player": {
    "hp": 18, "max_hp": 21, "courage": 6, "max_courage": 7,
    "level": 9, "xp": 31, "spell_power": 1, "crit": 10, "gold": 42,
    "class": "warrior", "evolution_tier": 1,
    "weapon": "bell_staff", "weapon_inventory": [], "weapon_tiers": {"bell_staff": 2},
    "trinket": {"id": "trinket_8812", "name": "...", "flavor": "...",
                "stats": {"crit": 5}, "rarity": "rare"},
    "inventory": [], "items": {}, "masteries": [], "story_flags": [],
    "quests": {}, "journal": [], "discoveries": [], "npc_trust": {},
    "potion_belt": ["health_potion", "courage_draught"]
  },
  "area_id": "clock_sewer", "pos": {"x": 12, "y": 7},
  "turnNo": 143, "transitions": 9,
  "areas": {
    "<area_id>": {"defeated": {"eid": 7}, "opened": ["chest_2"],
                   "states": {"eid": "calmed"}, "spawned": [], "shortcuts": []}
  },
  "boss": {"phase": 0}
}
```

`defeated` stores the transition counter at death (drives respawn). World
geometry is not saved — it is rebuilt from `/rg/world?seed=` and the diffs are
replayed (small, robust, survives map tweaks).

### Triggers And Flow

- Autosave on: area travel, level up, boss phase change, quest turn-in,
  evolution, and every 25 turns. One serialized write, debounced 250 ms.
- Title screen: a valid save shows "Continue" (default) and "New Game"
  (confirm overwrite). `?seed=` / `?bootFlags=` query params skip loading
  (testing flows preserved) but autosave under a separate `rg_save_dev` key.
- Versioning: `SAVE_VERSION` const with a `migrations[v](save)` chain.
  Unknown/corrupt saves (try/catch + required-key check) toast "Old save
  retired honorably" and fall through to New Game. Never crash the title
  screen.

## 8. LLM Features

Both endpoints follow the existing `dialogue.py` patterns (`_use_api` check →
compact payload → `_extract_json` → sanitize/clip → deterministic fallback)
and register in `app/rpg_bridge.py` beside `/rg/shop`. Flavor-only — no stats,
no actions, no flags in either schema.

### `/rg/loot` — Loot Christening

`POST {item_spec, area, player_brief}` → `dialogue.generate_loot_name()`,
modeled on `generate_shop_prices`. Schema: `{"name": str≤32, "flavor":
str≤140}`. Fallback table keyed by `(rarity, primary_stat, area)` — e.g.
"Foundry Charm of Sharp Opinions". Called fire-and-forget by the client when a
rare/epic drops; the item is fully usable with the fallback name immediately
and the LLM name patches in when the response lands.

### `/rg/taunt` — Elite/Boss Combat Narration

`POST {enemy_id, enemy_name, archetype, event, area, flag_story}` where
`event ∈ {spotted, windup, enrage, player_low, defeated}` and `flag_story` is
the existing flag gloss (≤4 lines). Response: `{"line": str≤90}`. Fallback: a
per-archetype × per-event table in story.py (25 canned lines). Client rules:
elites and bosses only, max one taunt per (enemy, event), async, rendered as a
3 s speech bubble; a slow or failed request silently keeps the fallback line
already shown. The boss referencing the player's choices mid-fight is the
demo's best LLM showcase.

## 9. Implementation Order

Verification ritual after every milestone: `uv run --extra gguf ruff check app
src/rune_goblin`, `uv run --extra gguf python -m compileall app
src/rune_goblin`, `validate_world()`, and a browser smoke at `/play` (using
`?seed=` / `?bootFlags=` for targeted states).

1. **M1 — Leveling + spell power (½ day).** story.py: new `XP_TO_NEXT`,
   `MAX_LEVEL`, `LEVEL_REWARDS`, XP constants. world.py: emit tiered XP, read
   `spell_power`/`crit` from the player payload into the damage calc. rpg.js:
   apply new reward fields in the `level_up` handler. Smoke: bootFlags to L9,
   kill one enemy, confirm the L10 reward text.
2. **M2 — Save system (½ day).** rpg.js only: serialize/load/migrate, title
   screen Continue. Done early so every later milestone is reload-testable.
   Smoke: save → F5 → continue → identical state.
3. **M3 — Monster tiers, abilities, respawn (1 day).** world.py: `tier`, DR,
   `unique`, affixes, ability specs, stat formulas. rpg.js: enemyTurn
   archetype scripts, windup statuses, telegraph rendering, respawn ledger,
   elite outline. Smoke each archetype in clock_sewer/frost_pass.
4. **M4 — Loot, gear, gold sinks (1 day).** world.py: drop tables, trinket
   rolling, reforge resolution. story.py: reforge costs/effects. rpg.js:
   trinket slot UI row, Reforge tab, materials in the bag. Smoke: kill an
   elite → trinket with fallback name; reforge bell_staff to +2.
5. **M5 — Combat feel (½ day).** world.py: crit roll, variance, knockback
   emission. rpg.js: `knockback_entity` and `apply_status` cases, potion belt
   keys, crit VFX. Smoke: L15 character, crit knocks the enemy back.
6. **M6 — Evolution chain (1 day).** Asset copy + 5 manifest entries.
   story.py: rewrite `can_evolve`, crown rules. world.py: Cracked Crown drop
   in boss phase 2 + foundry gauntlet chest, `evolve_player` emission. rpg.js:
   sprite-key function, `evolve_player` case, transformation VFX. Smoke:
   bootFlags L10 ding mid-area; L16 + crown → King.
7. **M7 — LLM endpoints (½ day).** dialogue.py: `generate_loot_name`,
   `generate_taunt`; fallback tables in story.py. rpg_bridge.py: two routes.
   rpg.js: async patch-in + speech bubbles. Fully functional offline via
   fallbacks, so safely last.
8. **M8 — Tuning pass (½ day).** One full 30-minute playthrough; adjust DR
   stats and the XP table only — all knobs live in two dicts by design.

Dependencies: M3 needs M1 (XP tiers); M4 needs M3 (tiers drive drops); M6
needs M1 (level gates); M7 needs M4 (item specs). M2 is independent and can be
parallelized.

## 10. Tests And Verification

- Unit tests: XP curve monotonicity and milestone sums (L10 = 236, L16 = 638
  cumulative); tier stat formulas per DR; drop-table bounds; reforge cost and
  clamp logic; `can_evolve` matrix (level × crown × tier); crit chance cap;
  loot/taunt JSON repair and fallback with malformed, too-long, and
  unknown-field outputs.
- `validate_world()` extensions: every level-gated portal has a visible hint;
  the Cracked Crown has both acquisition paths; minion packs do not block
  required routes.
- Browser smoke: new game → save → refresh → continue; level to 10 and
  confirm the tier-2 sprite + perk; dodge a telegraphed charge; quick-use a
  potion mid-fight; reforge a weapon; receive an LLM-named trinket (and the
  fallback name when the model is off); reach boss phase 2, collect the
  Crown, evolve to King at 16+; finish a run on each soft path.
- Balance pass target: a 20-40 minute demo run reaches level 11-12 by the
  boss with ~90-130 gold earned and at least one reforge + several potions
  purchased.
