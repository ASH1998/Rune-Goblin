# Rune Goblin Game Plan: From MVP To Hackathon-Ready LLM Dungeon Crawler

## Summary

Upgrade Rune Goblin from a working sandbox into a replayable dungeon crawler where
the core hook is still RuneLang: players draw or select runes, the model
interprets intent, and the world reacts. The game should feel like a strange,
story-rich exploration RPG with meaningful combat, progression, weapons, bosses,
secrets, and player-driven narrative changes.

The existing split stays intact: browser handles exploration/rendering, Python
handles spell/world resolution, and LLM output adds interpretation, flavor,
story branches, and spell personality while validated deterministic rules
protect balance.

## Top Priority: Goblin Hero Selection And King Evolution

The player character should come from `assets/Goblin Pack #1`, not the current
generic knight/player sprite. This becomes the first screen and the core player
identity.

- Add a title screen before the game starts:
  - Show animated goblin choices using the pack GIFs or exported sprite sheets.
  - Let the player choose one starting goblin.
  - Show simple stats and a one-line playstyle summary for each choice.
  - Start the world only after selection.
- Use `assets/Goblin Pack #1` as the primary character asset source:
  - `GoblinWarrior.gif` / `GoblinWarrior.aseprite`
  - `GoblinRogue.gif` / `GoblinRogue.aseprite`
  - `GoblinRoguePoison.gif` / `GoblinRoguePoison.aseprite`
  - `GoblinHunter.gif` / `GoblinHunter.aseprite`
  - `GoblinBarbarian.gif` / `GoblinBarbarian.aseprite`
  - `GoblinKing.gif`, `GoblinKingB.gif`, `GoblinKing.aseprite`,
    `GoblinkingParts.aseprite`
- Starting class stats:
  - Goblin Warrior: balanced HP, shield/circle affinity, reliable melee spell
    bonuses.
  - Goblin Rogue: lower HP, higher courage, key/coin affinity, better chests and
    shortcuts.
  - Goblin Rogue Poison: lower HP, poison/leaf/tooth affinity, stronger status
    effects but more chaos risk.
  - Goblin Hunter: ranged style, eye/thread/jagged affinity, better weakness
    reveals and first-strike bonuses.
  - Goblin Barbarian: high HP, flame/bone/tooth affinity, higher damage and
    worse NPC trust if used recklessly.
- Add `goblin_class` to player state and include it in `/rg/cast` context so
  spell resolution, LLM dialogue, NPC reactions, and ending text can reference
  the chosen hero.
- Final-stage evolution:
  - During the final Calendar Beast phase, the selected goblin can evolve into
    Goblin King.
  - Use `GoblinKing.gif` or an exported `GoblinKing` sheet for the evolved
    player sprite.
  - Evolution should be story-earned, not just cosmetic: it triggers when the
    player reaches the final phase with enough level/story progress.
  - The evolved form grants a short final power spike: max courage refill,
    stronger rune mastery, and one class-specific king ability.
- Goblin King ability examples:
  - Warrior King: shield allies and punish boss retaliation.
  - Rogue King: open one final lock/phase weakness without a key.
  - Poison King: apply a boss debuff that weakens repeated resistance.
  - Hunter King: reveal and mark the true Calendar Beast weak point.
  - Barbarian King: break a boss pylon at the cost of courage.

## Key Changes

- Add a real campaign arc with 3 dungeon acts, recurring NPCs, faction choices,
  branching discoveries, and multiple endings based on player actions.
- Replace the generic player sprite with title-screen goblin class selection and
  final-stage Goblin King evolution.
- Expand the world from 4 areas into connected dungeon floors with optional
  rooms, locked secrets, shortcuts, minibosses, and environmental puzzles.
- Add progression: XP, level, max HP/courage growth, rune mastery, weapon
  upgrades, and permanent discoveries.
- Add a weapon system where weapons modify spells, not replace them: wand,
  knife, bell-staff, bone blade, mirror shield, coin sling, etc.
- Add monster families with distinct behavior: goblins, fungi, wraiths, mimics,
  constructs, beasts, spirits, and corrupted librarians.
- Add bosses with phases, tells, resistances, special mechanics, and story
  consequences.
- Add LLM-driven interactive moments: dynamic NPC dialogue, story reactions,
  room descriptions, curse text, boss taunts, and post-fight consequences.
- Keep gameplay numbers deterministic and schema-validated; never let raw model
  output directly mutate HP, inventory, XP, or quest state without validation.

## Implementation Changes

- Add player progression fields to the world payload: `level`, `xp`,
  `xp_to_next`, `goblin_class`, `evolved_form`, `weapon`,
  `weapon_inventory`, `rune_mastery`, `gold`, `story_flags`, and
  `ending_flags`.
- Extend `resolve_world_cast()` to return new action types: `add_xp`,
  `level_up`, `add_weapon`, `equip_weapon`, `upgrade_weapon`, `set_story_flag`,
  `start_boss_phase`, `spawn_entity`, `unlock_shortcut`, and
  `add_journal_entry`.
- Add a structured LLM story layer after deterministic spell resolution:
  - Input: area, target, player state, selected/detected runes, validated spell,
    recent actions, story flags.
  - Output: short JSON with `narration`, `npc_line`, `journal_entry`,
    `mood_shift`, and optional suggested `story_flag`.
  - Validate and clamp all text length; ignore unknown action requests.
- Add weapon modifiers in Python balance logic:
  - Weapons add small deterministic bonuses such as +1 damage on matching rune
    school, reduced courage cost, shield chance, better unlocks, or bonus XP.
  - Weapon effects must be visible in the toast/HUD and included in cast
    response metadata.
- Add level-up rewards:
  - Level 2: +2 max HP.
  - Level 3: unlock 4-rune casts by default.
  - Level 4: choose a rune mastery.
  - Level 5: boss-ready power spike and ending branch unlock.
- Add rune mastery:
  - Track successful use of each rune.
  - At thresholds, improve that rune's reliability, reduce chaos, or add a
    minor passive.
- Add dungeon content:
  - Overworld hub becomes the quest hub.
  - Caverns become Act 1 with Mirror Fungus miniboss.
  - Wet Library becomes Act 2 with puzzle locks and story NPCs.
  - New Bone Market/Clock Sewer optional dungeon for weapons and secrets.
  - Calendar Beast Arena becomes final Act 3 with multi-phase boss.
- Add boss mechanics:
  - Bosses gain phase thresholds at 66% and 33% HP.
  - Each phase changes weakness/resistance and spawns hazards or adds.
  - Bosses react to repeated rune spam with temporary resistance.
- Add UI/HUD support in `rpg.js`:
  - Show level, XP bar, equipped weapon, gold, objective, and current area.
  - Add inventory/weapon panel toggle.
  - Add journal panel for discoveries, NPC clues, and story consequences.
  - Add boss phase banner and clearer enemy intent tells.
- Add replay hooks:
  - Seeded world variations.
  - Optional secret ending flags.
  - At least 3 ending summaries: Calendar Broken, Calendar Repaired, Calendar
    Devoured.

## Story And Natural Progression

The story should not feel like a popup layered over the game. It should come
from what the player does: which runes they rely on, who they help, which doors
they force open, which monsters they spare or defeat, and what secrets they
choose to read.

### Campaign Spine

- Opening hook: the player is a failed toll-road spell clerk who accidentally
  breaks the dungeon calendar. Days start looping, debts become monsters, and
  the Calendar Beast begins eating future mornings.
- Act 1, Goblin Toll Road and Mirror Fungus Caverns:
  - Goal: learn that runes affect people, locks, monsters, and the world.
  - Main beat: the player needs the first calendar shard from the Mirror Fungus
    colony.
  - Natural story moment: NPCs react differently if the player comforts the
    Lost Tourist, scares them, ignores them, or uses Eye/Mirror to learn the
    truth.
  - Miniboss: Mirror Mycologist, a fungus that copies the player's last spell
    and teaches that repeated rune spam is risky.
- Act 2, Wet Library and Bone Market/Clock Sewer:
  - Goal: turn exploration into investigation.
  - Main beat: find the Calendar Key, but learn it can repair, break, or sell
    the calendar depending on player choices.
  - Natural story moment: the Mold Librarian tracks whether the player reads
    clues, burns shelves, pays debts, or helps trapped spirits.
  - Optional dungeon: Bone Market/Clock Sewer offers weapons and cursed deals.
    This gives players a reason to explore beyond the critical path.
- Act 3, Calendar Beast Arena:
  - Goal: resolve the calendar crisis based on accumulated choices.
  - Main beat: the final boss changes dialogue, phase mechanics, and ending
    options based on story flags.
  - Natural story moment: allies can appear in the arena if the player earned
    trust; enemies can appear if the player abused curses or forced doors.

### Natural Progression Rules

- Every area should introduce one new idea through play:
  - Hub: rune targeting, NPCs, simple locks.
  - Caverns: weaknesses, reflection, copied spells.
  - Library: puzzle locks, reading, story flags.
  - Bone Market/Clock Sewer: weapons, trades, curses, optional risk.
  - Arena: boss phases, allies, endings.
- Each main objective should have 2-3 supporting clues from different sources:
  NPC dialogue, readable story objects, enemy drops, and environmental hints.
  Players should not get stuck because they missed one line.
- Quest text should stay short and concrete, while the journal carries richer
  context. Example HUD objective: "Find the Calendar Key." Example journal:
  "The Mold Librarian says the key is ink-locked and afraid of direct fire."
- Story changes should be tracked as durable flags, not inferred from prose.
  Examples: `tourist_helped`, `tourist_scared`, `library_shelves_burned`,
  `calendar_key_stolen`, `fungus_colony_spared`, `debt_accepted`,
  `mirror_truth_seen`, `boss_ally_librarian`.
- Reactions should happen near the action that caused them. If the player scares
  an NPC, show the immediate reaction, update trust, and later make one small
  consequence visible in the same region before using it in the ending.
- Optional content should make the main path easier or stranger, not mandatory.
  Weapons, allies, shortcuts, lore, and alternate endings are the rewards for
  curiosity.

### Story Response Pattern

Use a consistent "cause -> local reaction -> durable memory -> later payoff"
loop:

1. Player action: cast runes, open a chest, defeat/spare a creature, read a
   story object, equip a weapon, accept a cursed deal.
2. Local reaction: toast, animation, NPC line, changed entity state, or spawned
   hazard.
3. Durable memory: set a story flag, journal entry, NPC trust value, rune
   mastery count, or ending flag.
4. Later payoff: altered room text, changed shop prices, ally/enemy spawn,
   shortcut, boss phase modifier, or ending option.

Examples:

- The player uses `wave` or `leaf` on the Lost Tourist:
  - Local reaction: tourist calms down and gives courage.
  - Durable memory: `tourist_helped`.
  - Later payoff: tourist appears before the arena and gives a healing lunch.
- The player uses `flame` or `bone` on friendly NPCs:
  - Local reaction: NPC becomes wary.
  - Durable memory: `npc_intimidator` and lower trust.
  - Later payoff: fewer allies, but Bone Market gives better fear-based deals.
- The player opens a sealed door with `broken_mark + key`:
  - Local reaction: door opens, but adds "small debt".
  - Durable memory: `debt_accepted`.
  - Later payoff: Debt Collector miniboss appears unless the debt is repaid.
- The player defeats the Mirror Mycologist with `mirror + eye` instead of raw
  damage:
  - Local reaction: fungus reveals a truth instead of dying angry.
  - Durable memory: `fungus_colony_spared`.
  - Later payoff: Calendar Beast phase 2 has a visible weak point.

### Ending Logic

- Calendar Broken ending:
  - Default win if the player defeats the Calendar Beast without repairing the
    deeper story.
  - Tone: funny victory with lingering consequences.
- Calendar Repaired ending:
  - Requires reading the calendar truth, helping at least two NPCs/factions, and
    using Eye/Mirror/Spiral during the final phase.
  - Tone: satisfying good ending with allies acknowledged.
- Calendar Devoured ending:
  - Triggered by heavy curse use, unpaid debts, or accepting too many Bone
    Market deals.
  - Tone: darkly funny bad ending where the player wins the fight but loses the
    future.
- Secret Tollmaster ending:
  - Optional hackathon wow moment.
  - Requires coin/bell mastery, paying debts, and sparing at least one goblin.
  - Tone: the player becomes the new weird ruler of the Toll Road.

## LLM Interactive Design

- LLM should enhance curiosity, not control core balance.
- Use it for:
  - Interpreting messy drawings into runes.
  - Naming spells.
  - Generating short flavorful consequences.
  - NPC responses based on trust and prior actions.
  - Boss taunts and phase transitions.
  - Story journal entries.
- Do not use it for:
  - Arbitrary damage.
  - Free-form inventory mutation.
  - Unvalidated quest progression.
  - Runtime image generation.
- All model responses must be JSON, schema-validated, length-limited, and have
  deterministic fallbacks.
- Story LLM output should be grounded in explicit state only: current area,
  target, recent action, story flags, NPC trust, inventory, equipped weapon,
  and validated spell. Do not ask it to remember prior events outside that
  payload.
- Keep generated text short enough for a game loop:
  - Toast narration: 1 sentence, max 140 characters.
  - NPC line: 1-2 sentences, max 240 characters.
  - Journal entry: 1-3 sentences, max 420 characters.
- Prefer callbacks over monologues. The LLM should mention a prior flag in a
  concrete way, such as "The Tourist recognizes the wet candle you kept," not
  generic "your choices matter" text.
- If the LLM fails, use deterministic fallback lines from the entity, area, or
  story flag tables so the game never stalls.

## Test Plan

- Validate world reachability after every new map/entity addition.
- Unit test `resolve_world_cast()` for combat, XP, level-up, weapons, NPC trust,
  story flags, boss phases, and ending flags.
- Unit test story progression for cause -> flag -> later payoff chains:
  `tourist_helped`, `debt_accepted`, `fungus_colony_spared`, and
  `library_shelves_burned`.
- Unit test LLM story JSON repair/fallback with malformed, too-long, and
  unknown-field outputs.
- Browser smoke test:
  - Start new game.
  - Fight one enemy.
  - Gain XP.
  - Equip a weapon.
  - Unlock a chest.
  - Trigger NPC story response.
  - Enter boss phase 2.
  - Win and see ending screen.
- Run:
  - `uv run --extra gguf ruff check app src/rune_goblin`
  - `uv run --extra gguf python -m compileall app src/rune_goblin`
  - Local browser check at `http://localhost:7862/play`.

## Assumptions

- Keep the current Gradio + FastAPI + canvas architecture.
- Keep Python as the balance authority and browser as the mutable
  renderer/client.
- Prioritize hackathon impact over long-term engine purity.
- No runtime image generation; use existing sprites, procedural VFX, text,
  animation, and sound.
- The first implementation should be content-rich but scoped: one complete
  upgraded campaign path plus optional secrets, not an infinite roguelike.
