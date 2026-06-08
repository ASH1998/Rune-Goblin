# Rune Goblin Map And Asset Plan

## Summary

Make the current RPG sandbox feel like a real dungeon crawler by expanding the
world into larger connected maps, giving each region a clear story purpose, and
using the existing asset library deliberately. The maps should reward curiosity:
players should see locked paths, suspicious objects, NPCs, shrines, hazards, and
boss gates before they can solve them.

The current game already has a working canvas renderer, portals, entities,
sprites, VFX, rune interactions, chests, shrines, and a boss. This plan keeps
that architecture and grows the content around it.

## Top Priority: Goblin Pack #1 As Player Heroes

Use `assets/Goblin Pack #1` as the main playable character pack. The title
screen should be a character select screen, and the final stage should transform
the chosen goblin into Goblin King.

### Assets

- Starting heroes:
  - `GoblinWarrior.gif` / `GoblinWarrior.aseprite`
  - `GoblinRogue.gif` / `GoblinRogue.aseprite`
  - `GoblinRoguePoison.gif` / `GoblinRoguePoison.aseprite`
  - `GoblinHunter.gif` / `GoblinHunter.aseprite`
  - `GoblinBarbarian.gif` / `GoblinBarbarian.aseprite`
- Final evolution:
  - `GoblinKing.gif`
  - `GoblinKingB.gif`
  - `GoblinKing.aseprite`
  - `GoblinkingParts.aseprite`
- Supporting source files:
  - `BarbarianParts.aseprite`
  - `GoblinWarriorParts.aseprite`
  - `GoblinHunterAnim.aseprite`

### Runtime Plan

- Promote exported runtime copies into `app/rpg_static/sprites/heroes/`.
- Prefer exported PNG sprite sheets from Aseprite for gameplay animation.
- Use GIFs on the title screen if they render cleanly and are cheap to load.
- Add hero metadata to `manifest.json`:
  - `id`
  - `label`
  - `sprite`
  - `preview_gif`
  - `hp`
  - `courage`
  - `speed`
  - `affinity_runes`
  - `passive`
  - `king_ability`
- Replace the current `player.png` runtime reference with the chosen hero
  sprite after character selection.
- During the final boss phase, swap the active player sprite to Goblin King and
  trigger a one-time evolution VFX.

### Character Select Screen

- First screen before `/rg/world` starts active play.
- Shows the five goblin choices in a row/grid with animated previews.
- Each card shows:
  - name,
  - HP,
  - courage,
  - rune affinity,
  - passive,
  - "evolves into Goblin King" note.
- Recommended starting balance:
  - Warrior: HP 13, courage 5, affinity `closed_circle`, `jagged_line`.
  - Rogue: HP 10, courage 7, affinity `key`, `coin`, `thread`.
  - Poison Rogue: HP 9, courage 7, affinity `leaf`, `tooth`, `broken_mark`.
  - Hunter: HP 11, courage 6, affinity `eye`, `thread`, `jagged_line`.
  - Barbarian: HP 15, courage 4, affinity `flame`, `bone`, `tooth`.

## Asset Inventory And Use

### Already Curated In `app/rpg_static`

Use these first because they are already copied, loaded by `manifest.json`, and
known to render in the browser.

- Core tiles:
  - `sprites/grass.png`
  - `sprites/water.png`
- Player and humanoids:
  - `sprites/player.png`
  - `sprites/npc_pawn.png`
  - `sprites/npc_monk.png`
  - `sprites/blue_archer.png`
  - `sprites/red_warrior.png`
- Goblin enemies:
  - `sprites/goblin_red.png`
  - `sprites/goblin_blue.png`
  - `sprites/goblin_yellow.png`
  - `sprites/goblin_purple.png`
- Magic creatures:
  - `sprites/fire_elemental.png`
  - `sprites/water_elemental.png`
  - `sprites/earth_elemental.png`
  - `sprites/ice_golem.png`
  - `sprites/iron_golem.png`
  - `sprites/vile_witch.png`
  - `sprites/adept_necromancer.png`
  - `sprites/deft_sorceress.png`
  - `sprites/novice_pyromancer.png`
  - `sprites/expert_druid.png`
  - `sprites/corrupted_treant.png`
  - `sprites/grizzled_treant.png`
  - `sprites/glowing_wisp.png`
  - `sprites/magical_fairy.png`
  - `sprites/fluttering_pixie.png`
- Buildings and map objects:
  - `sprites/chest_gold.png`
  - `sprites/shrine_tower.png`
  - `sprites/goblin_house.png`
  - `sprites/goblin_tower_red.png`
  - `sprites/knight_tower_blue.png`
  - `sprites/bridge_all.png`
  - `sprites/happy_sheep.png`
- Decoration:
  - `sprites/deco_tree.png`
  - `sprites/deco_bush.png`
  - `sprites/deco_rock.png`
  - `sprites/deco_rock2.png`
  - `sprites/deco_d01.png` through `sprites/deco_d18.png`
- Rune icons:
  - `icons/*.png` for all 16 RuneLang runes.
- VFX:
  - Fire, ice, poison, light, holy, tornado, barrier, explosion, star, and
    magic-circle atlas assets under `vfx/`.
- Audio:
  - Elemental spell SFX, charge, sweep, good/bad status, and power SFX under
    `sfx/`.

### Raw Assets To Promote From `assets`

Only copy/promote raw assets into `app/rpg_static` when a map needs them. Keep
raw pack paths ignored and do not load directly from `assets` at runtime.

- `assets/Tiny Swords/Tiny Swords (Update 010)`:
  - Deco: `Deco/01.png` through `Deco/18.png`.
  - Effects: `Effects/Explosion/Explosions.png`, `Effects/Fire/Fire.png`.
  - Goblin buildings: `Goblin_House.png`, `Goblin_House_Destroyed.png`,
    `Wood_Tower_Blue.png`, `Wood_Tower_Red.png`, `Wood_Tower_Yellow.png`,
    `Wood_Tower_Purple.png`, `Wood_Tower_Destroyed.png`,
    `Wood_Tower_InConstruction.png`.
  - Goblin troops: Torch, Barrel, TNT, and Dynamite variants in blue, red,
    yellow, and purple.
  - Knight buildings: Castle, House, and Tower variants in blue, red, yellow,
    purple, construction, and destroyed states.
  - Knight troops: Archer, Pawn, Warrior, Dead, Arrow, and Archer+Bows variants.
  - Resources: active/inactive/destroyed gold mine, gold/wood/meat spawn/idle
    resources, sheep animations, tree.
  - Terrain: bridge, shadows, flat/elevation tilemaps, water, water foam, and
    water rocks.
  - UI: banners, carved panels, buttons, icons, pointers, and ribbons.
- `assets/Tiny Swords (Free Pack)/Tiny Swords (Free Pack)`:
  - Buildings in black, blue, purple, red, and yellow: Archery, Barracks,
    Castle, House1, House2, House3, Monastery, Tower.
  - Full animated units in black, blue, purple, red, and yellow:
    Archer idle/run/shoot, Lancer attack/defence/run, Monk idle/run/heal,
    Pawn idle/run/interact with axe/gold/hammer/knife/meat/pickaxe/wood, and
    Warrior idle/run/attack/guard.
  - Particle FX: dust, explosion, fire, water splash.
  - Terrain decorations: bushes, clouds, rocks, water rocks, rubber duck.
  - Resources: gold stones/highlights, meat, sheep, tools, tree stumps, trees,
    wood resource, tilemaps, water background, water foam, shadows.
  - UI: banners, bars, buttons, cursors, human avatars, icons, papers, ribbons,
    swords, wood table, and slot panels.
- `assets/GameFXexport/GameFXexport`:
  - Additional spell animation sheets: fireballs, explosions, ice, light,
    poison, stars, tornadoes, barriers.
  - Use for higher-tier boss attacks and special room hazards.
- `assets/Retro_Magic_FX`:
  - Large SFX library for spell elements, charge loops, status good/bad,
    movement sweeps, power cues, and UI quips.
  - Use to give each region a distinct sound identity.
- `assets/Mythril Age Icons`:
  - Icons for weapons, aura, sword, shield, arrow, magic swirl, tornado,
    hearts, mountain, lightning, claw, and defense.
  - Use for weapon inventory, status effects, map markers, and quest badges.
- `assets/Basic Asset Pack`:
  - Basic magical sprites and animations.
  - Use only as fallback or for simple collectible/map-marker effects if the
    GameFX assets are too visually heavy.
- `assets/rune_goblin_magic_circles_pack`:
  - Magic-circle atlas, metadata, preview, and loader references.
  - Already represented in `app/rpg_static/vfx/magic_circles.png`; keep using it
    for rune identity and spell tiers.

## Unused Tiny Swords Promotion Matrix

These assets are currently underused or unused. Promote them by gameplay need,
not as a bulk dump. Each promoted asset should get a stable lowercase runtime
name in `app/rpg_static/manifest.json`.

| Raw asset group | Promote as | Story/game role | Maps |
|---|---|---|---|
| Free Pack black buildings: Archery, Barracks, Castle, House1-3, Monastery, Tower | `black_archery`, `black_barracks`, `black_castle`, `black_house_*`, `black_monastery`, `black_tower` | Bone Market stalls, cursed faction architecture, debt offices | Bone Market, Calendar Gate Approach |
| Free Pack blue buildings | `blue_archery`, `blue_barracks`, `blue_castle`, `blue_house_*`, `blue_monastery`, `blue_tower` | Friendly road/knight settlement, training posts, safe landmarks | Toll Road Hub, Gate Approach |
| Free Pack purple buildings | `purple_castle`, `purple_tower`, `purple_monastery`, etc. | Calendar corruption, boss cult structures, secret archive | Wet Library, Calendar Arena |
| Free Pack red buildings | `red_barracks`, `red_tower`, `red_house_*` | Hostile guards, aggressive toll faction, arena damage states | Toll Road Hub, Gate Approach |
| Free Pack yellow buildings | `yellow_house_*`, `yellow_tower`, `yellow_castle` | Merchant/toll economy, coin route, secret Tollmaster path | Toll Road Hub, Bone Market |
| Update 010 goblin destroyed/in-construction buildings | `goblin_house_destroyed`, `wood_tower_destroyed`, `wood_tower_building` | Show consequences from fire, debt, repairs, and faction state | Toll Road Hub, Gate Approach |
| Update 010 colored goblin towers | `goblin_tower_blue/yellow/purple/red` | Colored faction markers and gated districts | Toll Road Hub, Bone Market |
| Goblin Torch variants | `goblin_torch_blue/red/yellow/purple` | Basic enemy families with color-coded rune schools | Toll Road, Caverns, Gate |
| Goblin Barrel variants | `goblin_barrel_*` | Defensive enemies and explosive map blockers | Bone Market, Clock Sewer |
| Goblin TNT and Dynamite | `goblin_tnt_*`, `dynamite` | Hazard enemies, breakable walls, forced shortcut risk | Clock Sewer, Bone Market |
| Update 010 knight archer/pawn/warrior variants | `knight_archer_*`, `knight_pawn_*`, `knight_warrior_*` | Allies, guards, training NPCs, ending reinforcements | Toll Road, Library, Gate, Arena |
| Free Pack full animated units | `unit_archer_*`, `unit_lancer_*`, `unit_monk_*`, `unit_worker_*`, `unit_warrior_*` | Higher-polish NPC/enemy upgrades once animation states are supported | All major maps |
| Free Pack pawns carrying axe/gold/hammer/knife/meat/pickaxe/wood | `worker_axe`, `worker_gold`, `worker_hammer`, `worker_knife`, `worker_pickaxe`, `worker_wood` | Shopkeepers, resource NPCs, weapon pickup characters, quest givers | Toll Road, Bone Market, Clock Sewer |
| Free Pack monks and heal effect | `monk_*`, `monk_heal_effect` | Shrines, healing NPCs, good-ending ally | Library, Gate, Arena |
| Free Pack lancers | `lancer_*` | Elite guards, bridge blockers, late-game enemies | Gate Approach, Arena |
| Terrain tilemaps and shadows | `tilemap_flat`, `tilemap_elevation`, `shadow` | Larger, more legible maps with elevation/edges instead of flat fields | All outdoor maps |
| Water foam, water rocks, water background | `water_foam`, `water_rock_*`, `water_bg` | Readable rivers, sewer channels, cave pools | Caverns, Clock Sewer, Toll Road |
| Bridge asset | `bridge_all` variants if sliced | Proper bridge crossings and repairable shortcuts | Toll Road, Caverns, Clock Sewer |
| Bushes, rocks, trees, stumps, clouds, rubber duck | `bush_*`, `rock_*`, `tree_*`, `stump_*`, `cloud_*`, `duck` | Map density, secrets, jokes, environmental landmarks | All maps |
| Gold mine, gold stones, gold resource/highlight | `gold_mine_*`, `gold_stone_*`, `gold_resource` | Economy route, coin puzzles, mine side room | Toll Road, Bone Market |
| Meat/sheep assets | `sheep_*`, `meat_resource` | Food rewards, tourist lunch, healing side quest | Toll Road, Gate |
| Tool assets | `tool_axe`, `tool_hammer`, `tool_pickaxe`, `tool_knife` | Weapon pickups, shop icons, repair puzzles | Bone Market, Clock Sewer |
| Wood resource | `wood_resource` | Bridge repair, shrine repair, shortcut construction | Toll Road, Clock Sewer |
| UI bars | `ui_bigbar_*`, `ui_smallbar_*` | HP, XP, courage, boss phase bars | HUD |
| UI papers and wood table | `ui_paper_regular`, `ui_paper_special`, `ui_wood_table` | Journal, map, shop, dialogue panels | HUD/overlays |
| UI banners/ribbons/buttons/pointers | `ui_banner_*`, `ui_ribbon_*`, `ui_button_*`, `ui_pointer_*` | Area title cards, quest updates, boss warnings, map markers | HUD/overlays |
| UI human avatars | `avatar_01` through `avatar_25` | Dialogue portraits if we add NPC panels | NPC dialogue/journal |
| UI swords and icons | `ui_swords`, `ui_icon_*` | Weapon inventory, equipment cards, status badges | Inventory/HUD |
| Particle FX dust/explosion/fire/water splash | `fx_dust_*`, `fx_explosion_*`, `fx_fire_*`, `fx_water_splash` | Footsteps, breakable walls, fire hazards, water puzzles | All maps |

### Promotion Priorities

1. Terrain readability: water foam, water rocks, shadows, elevation/flat
   tilemaps, extra bushes/rocks/trees.
2. Buildings for map identity: blue/yellow hub buildings, black/purple market
   buildings, purple/destroyed final-gate buildings.
3. Unit variety: goblin Torch/Barrel/TNT variants, knight archer/warrior/pawn
   variants, monks/workers.
4. Resource and tool props: gold mine/stones, wood, tools, sheep/meat.
5. UI polish: bars, paper, wood table, banners, pointers, icons.
6. Full animated Free Pack units after the renderer supports animation states
   beyond idle/run/simple frame cycling.

## Map Progression Structure

The world should become a hub-and-dungeon layout with visible locks and clear
progression. The player should often see a path before they can open it.

### Area Size Targets

- Current maps are roughly 24-30 tiles wide and 16-20 tiles tall.
- New target sizes:
  - Hub maps: 48x32 minimum.
  - Main dungeon floors: 44x30 minimum.
  - Optional dungeons: 36x28 minimum.
  - Boss arenas: 28x22 minimum, with phase-specific hazard zones.
- Keep the camera-follow model. Do not try to fit the full map on screen.
- Add more internal walls, ponds, bridges, buildings, and loops so exploration
  is not just walking across open fields.

### Progression Gates

- Rune gates:
  - `key`: normal locks, chests, doors.
  - `eye`: readable lore, hidden weakness, secret map markers.
  - `mirror`: reflection puzzles, fungus diplomacy, boss weak-point reveal.
  - `wave`: emotional doors, water paths, NPC comfort.
  - `leaf`: healing shrines, growth bridges, corrupted forest cleanup.
  - `coin`: tolls, shops, debt gates, goblin faction choices.
  - `bell`: summons, alarms, secret merchant, boss interruption.
  - `broken_mark`: force locks, cursed shortcuts, bad ending pressure.
- Item gates:
  - Calendar Shard 1: opens Wet Library restricted stacks.
  - Calendar Key: opens Calendar Gate.
  - Debt Receipt: lets the player enter Bone Market safely.
  - Mirror Cap: unlocks nonviolent fungus route.
  - Tollmaster Token: unlocks secret ending route.
- Progression gates should support at least one fallback clue nearby so players
  know what they are missing.

## Planned Maps

### 1. Goblin Toll Road Hub

- Target size: 52x34.
- Story purpose: starting hub, tutorial space, visible locked branches.
- Assets:
  - Grass/water tiles, bridge, goblin house, goblin tower, trees, bushes, rocks.
  - Happy sheep and resource props to make it feel lived-in.
  - Goblin Torch units for toll enemies.
  - Knight house/tower assets from raw Tiny Swords for distant landmarks.
- Layout:
  - Central toll road running west-east.
  - North: training shrine and Blue Watch Archer.
  - East: locked Calendar Gate visible but inaccessible.
  - South: river crossing that needs bridge repair or `wave + key`.
  - West: cave mouth to Mirror Fungus Caverns.
  - Hidden corner: Bell/Coin shrine for the secret Tollmaster route.
- Progression:
  - Starts with basic combat and simple chests.
  - Player learns NPC trust through Lost Tourist.
  - Player sees at least 3 locked things: coin toll, key chest, calendar gate.
- Story flags:
  - `tourist_helped`
  - `tourist_scared`
  - `toll_paid`
  - `toll_forced`
  - `secret_bell_shrine_seen`

### 2. Mirror Fungus Caverns

- Target size: 46x32.
- Story purpose: Act 1 dungeon, teaches weaknesses, reflection, and repeated
  spell consequences.
- Assets:
  - Water/rock terrain, bushes as fungus clusters, glowing wisp sprites, yellow
    goblins as fungus proxies until specific fungus art exists.
  - Magic circles and light/poison VFX for mirror spores.
  - Promote water rocks and foam from raw Tiny Swords to make pools readable.
- Layout:
  - Three looping chambers connected by narrow bridges.
  - Shallow hazard pools that block straight paths.
  - Mirror Stone lore room behind `mirror + eye`.
  - Fungus nursery optional room where the player can spare or burn spores.
  - Miniboss chamber at the far end.
- Progression:
  - First half: enemies with clear weaknesses.
  - Midpoint: locked mirror door requiring `mirror` or a clue from the hermit.
  - End: Mirror Mycologist miniboss copies the player's previous rune school.
- Story flags:
  - `mirror_truth_seen`
  - `fungus_colony_spared`
  - `fungus_colony_burned`
  - `mycologist_defeated`
  - `calendar_shard_1_taken`

### 3. Wet Library

- Target size: 50x34.
- Story purpose: Act 2 investigation map, more puzzle/exploration than combat.
- Assets:
  - Blue/purple building assets as library towers and archive blocks.
  - Monk/druid NPCs, vile witch, necromancer, wisps.
  - UI paper assets from raw Tiny Swords for journal/readable panels.
  - Water foam and tile overlays for damp floors.
- Layout:
  - Main hall with visible locked stacks.
  - West wing: Mold Librarian and clue chain.
  - East wing: Ink-Locked Chest route.
  - Basement stairs to Clock Sewer.
  - Restricted stacks locked by Calendar Shard 1.
  - Secret archive opened by `eye + mirror`.
- Progression:
  - Player gathers multiple clues for the Calendar Key.
  - Combat is avoidable or easier if the player reads objects.
  - Burning shelves creates a shortcut but sets a bad story flag.
- Story flags:
  - `librarian_trust`
  - `wet_catalog_read`
  - `library_shelves_burned`
  - `calendar_key_found`
  - `calendar_truth_read`

### 4. Bone Market

- Target size: 38x28.
- Story purpose: optional risk/reward shop dungeon with weapons and cursed deals.
- Assets:
  - Black/purple buildings from raw Tiny Swords for market stalls.
  - Necromancer, vile witch, corrupted treant, goblin barrel/TNT units.
  - Mythril icons for weapon cards and trade choices.
  - Retro Magic FX bad/status/power SFX.
- Layout:
  - Compact bazaar with 4 stalls, a debt altar, and a back-room boss door.
  - Entry requires Debt Receipt, `coin + bell`, or a forced cursed entrance.
  - Secret merchant appears if the player has high coin/bell mastery.
- Progression:
  - Player can buy one weapon upgrade, repay debt, or accept a curse for power.
  - Every deal has a clear short-term benefit and tracked ending consequence.
- Story flags:
  - `bone_market_entered`
  - `debt_repaid`
  - `debt_deepened`
  - `weapon_bought`
  - `secret_merchant_met`

### 5. Clock Sewer

- Target size: 42x30.
- Story purpose: optional traversal dungeon that links Library and Arena while
  giving players a noncombat route to a better ending.
- Assets:
  - Water tiles, foam, bridges, water rocks, barrels, TNT, resource props.
  - Water elemental, ice golem, glowing wisp.
  - Wind/water/light VFX and sweep SFX.
- Layout:
  - Water channels with bridge shortcuts.
  - Valve rooms represented by locked doors and story objects.
  - Hidden clean-water shrine requiring `wave + leaf`.
  - Shortcut back to the Toll Road after solving the valve puzzle.
- Progression:
  - Rewards players who use utility runes instead of only damage.
  - Solving the clean-water shrine grants ally support in the final boss.
- Story flags:
  - `sewer_valves_aligned`
  - `clean_water_restored`
  - `sewer_shortcut_open`
  - `water_spirit_helped`

### 6. Calendar Gate Approach

- Target size: 34x26.
- Story purpose: pre-boss checkpoint where consequences become visible.
- Assets:
  - Knight towers/castle pieces, banners/ribbons, destroyed buildings if the
    player has high curse/debt flags.
  - NPC allies or debt enemies based on flags.
  - UI banners for boss warning.
- Layout:
  - Short but dense approach map.
  - Three side alcoves where helped NPCs appear.
  - Cursed debt path spawns Debt Collector.
  - Final gate requires Calendar Key.
- Progression:
  - Gives the player one last heal/shop/journal beat before the boss.
  - Shows visible consequences from earlier choices.
- Story flags:
  - `arena_approach_reached`
  - `boss_ally_tourist`
  - `boss_ally_librarian`
  - `debt_collector_spawned`

### 7. Calendar Beast Arena

- Target size: 30x24.
- Story purpose: final boss with phase changes and ending resolution.
- Assets:
  - Purple goblin or adept necromancer as current boss sprite.
  - Promote larger castle/tower/destroyed pieces for arena edges.
  - Use GameFXexport big explosions, tornado, star, barrier, and magic circles.
  - Use Retro Magic FX charge loops and power sounds for phase transitions.
- Layout:
  - Open center with four calendar pylons.
  - Each pylon can be activated by a rune school to alter a phase.
  - Hazard tiles appear during phase 2.
  - Ally positions around the edge if story flags qualify.
- Progression:
  - Phase 1: teaches boss weakness.
  - Phase 2: boss resists repeated rune schools and spawns debt/fungus adds.
  - Phase 3: ending choice opens if the player has the right flags.
- Story flags:
  - `calendar_beast_phase_2`
  - `calendar_beast_phase_3`
  - `calendar_broken`
  - `calendar_repaired`
  - `calendar_devoured`
  - `tollmaster_ending`

## Asset-To-Story Mapping

- Goblin houses/towers:
  - Toll Road settlement, Bone Market stalls, Calendar Gate damage states.
- Knight castles/towers/houses:
  - Old calendar authority, Library architecture, final arena border.
- Goblin Torch/Barrel/TNT units:
  - Toll guards, debt collectors, market enforcers, explosive hazards.
- Knight archers/warriors/pawns/monks:
  - Watch Archer, Red Guard, monk healers, faction allies near the boss.
- Magic creatures:
  - Elementals become rune-school enemies and environmental guardians.
  - Wisps are hints, secrets, and noncombat guides.
  - Necromancer/witch sprites support Bone Market and Calendar Beast story.
  - Treants/druids support leaf/growth/shrine content.
- Resources and decorations:
  - Trees, rocks, bushes, gold, sheep, tools, bridges, and water rocks make
    each map readable and less empty.
- UI assets:
  - Bars for HP/XP/courage.
  - Papers for journal/readable lore.
  - Ribbons/banners for area names, boss phase warnings, and quest updates.
  - Mythril icons for weapons, statuses, and map markers.
- VFX and SFX:
  - Each rune school gets a consistent effect/sound.
  - Boss phases use larger and layered effects.
  - Puzzle solves use good/status/power sounds, not combat explosions.

## Implementation Order

1. Promote missing raw assets into `app/rpg_static/sprites`, `ui`, and `sfx`
   with stable lowercase names.
2. Extend `manifest.json` to include promoted buildings, unit variants,
   resources, UI panels, and any new SFX.
3. Add map authoring helpers in `world.py`:
   - rectangle rooms,
   - corridors,
   - water pools,
   - bridge placement,
   - deterministic decoration scatter by biome,
   - validation for locks and required adjacent reachable tiles.
4. Replace current open-field maps with larger authored maps one at a time:
   Toll Road, Caverns, Library, Bone Market, Clock Sewer, Gate Approach, Arena.
5. Add new entity types only where needed:
   - `map_marker`
   - `weapon_pickup`
   - `shop`
   - `hazard`
   - `pylon`
   - `shortcut`
6. Add progression flags and item gates after the bigger maps are navigable.
7. Add boss phase map changes last, once the arena and story flags exist.

## Map Quality Rules

- Every map needs at least:
  - one main path,
  - one optional loop,
  - one visible locked reward,
  - one story object,
  - one NPC or noncombat interaction,
  - one shrine/checkpoint,
  - one shortcut or return portal.
- Do not make large empty fields. Fill with buildings, water, bridges, rocks,
  trees, resource props, narrow paths, and readable landmarks.
- The player should always know the next likely objective from HUD text, but
  curiosity should be rewarded by side rooms and visible secrets.
- Locked content must telegraph its requirement through nearby hint text, sprite
  language, or an NPC clue.
- Optional maps should improve survivability, story options, or endings, but
  the main route must remain completable without them.
- Larger maps must pass `validate_world()` and a browser roam test before adding
  enemies or story gates.

## Tests And Verification

- Extend `validate_world()` to check:
  - every portal target exists,
  - every locked gate has a reachable adjacent tile,
  - every required story item has at least one acquisition path,
  - every boss arena has enough reachable movement space,
  - every map has a return route or intentional one-way story gate.
- Add unit tests for:
  - map reachability,
  - item-gated progression,
  - rune-gated progression,
  - optional map completion,
  - final gate access,
  - boss phase area state.
- Browser smoke tests:
  - roam through each map,
  - verify promoted sprites render,
  - verify portals and shortcuts work,
  - verify locked paths show requirements,
  - verify boss arena phase VFX do not obscure the player.
