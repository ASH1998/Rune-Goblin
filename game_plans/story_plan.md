# Rune Goblin Story Plan

## Story Goal

Rune Goblin should feel like a real adventure, not a tech demo. A normal player
should understand the problem within the first minute:

> You broke the calendar. Tomorrow is being eaten. Draw weird runes, explore the
> dungeon road, make friends or debts, and decide whether the future gets fixed,
> sold, or destroyed.

The LLM should make the world feel alive through short, reactive dialogue and
story consequences. It should not bury players in lore. Every important story
beat must connect to a visible map object, NPC, enemy, item, or rune gate.

## Top Priority: Chosen Goblin Hero And Goblin King Evolution

The story starts on a title-screen character select. The player is not a generic
hero: they choose one goblin from `assets/Goblin Pack #1`, and that choice
changes stats, dialogue, spell flavor, NPC reactions, and the final evolution.

### Starting Goblin Choices

Each goblin should be understandable at a glance. The LLM can add flavor, but
the core stats and identity are deterministic.

| Goblin | Player fantasy | Stats | Rune affinity | Story identity |
|---|---|---|---|---|
| Goblin Warrior | Safe, balanced, direct | High HP, medium courage | `closed_circle`, `jagged_line` | An ex-road guard trying to fix the mess honorably |
| Goblin Rogue | Clever, fast, greedy | Low HP, high courage | `key`, `coin`, `thread` | A toll cheat who knows every lock has feelings |
| Goblin Rogue Poison | Risky, sneaky, status-heavy | Low HP, high courage, higher chaos | `leaf`, `tooth`, `broken_mark` | A back-alley potion goblin with questionable medicine |
| Goblin Hunter | Smart, tactical, ranged | Medium HP, medium-high courage | `eye`, `thread`, `jagged_line` | A road scout who sees weak points before trouble starts |
| Goblin Barbarian | Strong, loud, simple | Highest HP, low courage | `flame`, `bone`, `tooth` | A gate-crasher learning that not every door deserves violence |

### Character Select Dialogue

Title text:

- "Choose the goblin who broke tomorrow."

Warrior:

- "You were hired for security. Unfortunately, the calendar was not secure."

Rogue:

- "You have stolen coins, keys, and once, a suspiciously portable staircase."

Poison Rogue:

- "Your medicine works. The side effects are mostly rumors with legs."

Hunter:

- "You can spot a weak point, a fake bridge, and a lying invoice at thirty
  paces."

Barbarian:

- "You solve problems by entering the room before the door agrees."

Confirm button copy:

- "Start shift"

### Class-Specific Story Reactions

The LLM should receive `goblin_class` and use it for small callbacks.

- Warrior NPC reactions:
  - "A guard caused this? That is almost organized."
  - Blue Watch Archer respects the player earlier.
- Rogue NPC reactions:
  - Locks and merchants recognize the player as "professionally suspicious."
  - Bone Market gives sharper, funnier trade lines.
- Poison Rogue NPC reactions:
  - Healers distrust the player at first.
  - Fungus and swamp/sewer entities react with curiosity.
- Hunter NPC reactions:
  - Weakness hints are framed as the player noticing details.
  - Boss tells become slightly clearer in dialogue.
- Barbarian NPC reactions:
  - NPCs are nervous if the player uses fear/damage runes often.
  - Physical shortcut and break-wall story beats feel class-appropriate.

### Goblin King Evolution

At the final Calendar Beast phase, the chosen goblin evolves into Goblin King if
the player has reached the required story/progression threshold.

Baseline trigger:

- Player reaches Calendar Beast phase 3.
- Player is at least level 5 or has completed two major story routes.
- Player has at least one strong identity flag:
  - helped allies,
  - mastered a rune path,
  - repaid/deepened debt,
  - spared/burned fungus,
  - restored/ignored clean water.

Evolution scene:

- The Calendar Beast tries to eat the player's last tomorrow.
- The player's chosen goblin refuses to remain a clerk, thief, scout, chemist,
  or brawler.
- The Goblin King form appears.
- The LLM writes a short class-specific transformation line.

Class transformation lines:

- Warrior King: "The shield becomes a crown. The crown remembers every hit you
  took and gives one back."
- Rogue King: "Every stolen key turns in the air. The lock on tomorrow clicks."
- Poison King: "The venom becomes medicine for the future and poison for the
  Beast."
- Hunter King: "You see the weak point at last: not the Beast's heart, but its
  hunger."
- Barbarian King: "You stop breaking doors. You become the door that breaks
  back."

Goblin King gameplay beat:

- Refill courage.
- Upgrade the chosen class passive for the rest of the fight.
- Unlock one king ability based on starting class.
- Change final boss dialogue to recognize the player's path.

## Tone

- Strange, funny, and sincere.
- Easy to understand, even when the world is weird.
- Dialogue should sound like characters in a fantasy game who know their lives
  are ridiculous.
- Avoid long lore dumps. Use short lines, repeated motifs, and callbacks.
- The best feeling: "I did something weird, and the game remembered."

Reference tone:

- A toll goblin arguing about paperwork.
- A fungus that is afraid of mirrors.
- A librarian trying to keep books dry in a cursed wet library.
- A market that sells useful weapons but charges emotional interest.
- A final boss that is not evil because it hates you, but because it is hungry
  for every tomorrow people keep wasting.

## Premise

The player is a junior spell clerk on the Goblin Toll Road. Their job was simple:
stamp travel receipts, collect small debts, and never touch the ancient Calendar
Bell.

During a boring shift, the player doodles a RuneLang spell on a receipt. The
spell misfires. The Calendar Bell rings thirteen times. The dungeon calendar
cracks. Days begin looping, invoices become monsters, and the Calendar Beast
wakes under the road.

Now the world is stuck between yesterday and tomorrow. The player must collect
calendar pieces, learn what the runes really do, and choose what kind of future
to leave behind.

## Player Fantasy

The player is not a chosen hero. They are a messy spellcaster learning a magical
language by using it badly.

The fantasy is:

- "My drawings matter."
- "NPCs remember how I treated them."
- "Exploration reveals better options than brute force."
- "Weapons change how my spells feel."
- "The story reacts without becoming confusing."

## Core Story Loop

Every story moment should follow this pattern:

1. The player sees a clear situation.
2. The player chooses runes, a route, a weapon, or an interaction.
3. The game gives an immediate reaction.
4. A durable flag records what happened.
5. A later character, room, enemy, or ending pays it off.

Example:

- Situation: Lost Tourist is panicking near the Toll Road.
- Choice: player casts `wave` or `leaf`.
- Immediate reaction: Tourist calms down and gives courage.
- Flag: `tourist_helped`.
- Later payoff: Tourist appears before the final boss with a healing lunch.

## Main Cast

### The Player: Failed Spell Clerk

- Role: player avatar.
- Want: fix the mistake, survive, maybe become important.
- Secret: their "bad" spell drawings are actually good at bending rules.
- Dialogue style: mostly silent, but journal entries can frame their thoughts.

Sample journal lines:

- "I broke a calendar today. That feels hard to explain on a form."
- "The runes do not care if I understand them. They work anyway."
- "People keep asking if I am licensed. I have decided to walk faster."

### Queue Goblin

- Sprite role: goblin torch/red goblin.
- Map: Goblin Toll Road.
- Role: first hostile blocker and recurring comic rival.
- Want: collect tolls, keep the road official, not be blamed for time breaking.
- Character function: teaches basic combat, coin/bell hints, and goblin faction
  logic.

First meeting:

- "Road's closed. Calendar's screaming. Toll is one coin, one apology, or one
  legally confusing spell."
- "If you broke time, stand in the left line. If you only damaged it, right
  line."

If player uses `coin`:

- "Payment accepted. I hate how responsible that was."

If player uses `bell`:

- "Do not ring that. I am emotionally hourly."

If defeated:

- "Fine. Pass. But if tomorrow asks, I never saw you."

Later callback:

- If spared or paid: "The clerk! Still alive, still undertrained. Respect."
- If forced/burned: "Oh great. The walking incident report."

### Lost Tourist

- Sprite role: magical fairy, pawn, or sheep-side NPC.
- Map: Toll Road.
- Role: first emotional NPC and trust tutorial.
- Want: get home before the same afternoon happens again.
- Character function: shows that non-damage runes matter.

First meeting:

- "Excuse me. Is this the road to Tuesday? My map keeps biting me."
- "Please do not attack the map. It has already won twice."

If helped with `wave`:

- "Oh. That made the panic quieter. Are you allowed to do kind magic?"

If helped with `leaf`:

- "My paper cuts are gone. The map is still rude, but now I can fight it."

If scared with `flame`, `bone`, or `tooth`:

- "I understand less than before, but much faster."

Final payoff if helped:

- "I found the arena! Bad news: it is awful. Good news: I packed sandwiches."

### Blue Watch Archer

- Sprite role: blue archer.
- Map: Toll Road, later Gate Approach.
- Role: tutorial mentor.
- Want: train the player without admitting the situation is hopeless.
- Character function: explains weaknesses, facing targets, weapons, and tells.

Dialogue:

- "Face the thing you mean to bother. Runes are powerful, not polite."
- "Weakness matters. A small correct spell beats a dramatic wrong one."
- "When a boss changes stance, stop repeating yourself. The calendar learns."

If player keeps losing:

- "You are not bad at magic. You are just giving the dungeon very clear
  evidence."

### Road Druid

- Sprite role: expert druid or grizzled treant.
- Map: Toll Road, Clock Sewer.
- Role: gentle systems guide for leaf/wave/repair routes.
- Want: restore growth around the broken road.
- Character function: points to optional noncombat routes and good ending.

Dialogue:

- "Calendars are just gardens with numbers. Yours has weeds."
- "Leaf repairs. Wave forgives. Use both when a place has forgotten how to be
  alive."
- "The sewer water remembers the clean version of itself. Help it remember
  louder."

### Mirror Hermit

- Sprite role: grizzled treant or glowing wisp.
- Map: Mirror Fungus Caverns.
- Role: cryptic but useful cave guide.
- Want: keep the fungus colony from being burned by scared travelers.
- Character function: introduces mirror/eye and nonviolent enemy resolution.

Dialogue:

- "Do not swing at mirrors unless you want a very accurate enemy."
- "The fungus is not hiding a shard. It is remembering one."
- "Eye shows. Mirror admits. Together they make cowards of secrets."

If player burned fungus:

- "Fire is an answer. It is just rarely the last one."

If player spared fungus:

- "Good. The colony will tell the Beast where its own fear lives."

### Mirror Mycologist

- Sprite role: glowing wisp, yellow goblin, or promoted fungus proxy.
- Map: Mirror Fungus Caverns.
- Role: Act 1 miniboss.
- Want: protect the Calendar Shard by reflecting hostile intent.
- Mechanic: copies the player's last rune school and resists repetition.
- Character function: teaches that RuneLang is expressive, not just damage.

Intro:

- "You arrive wearing one face. I arrive wearing every spell you regret."
- "Strike me once, I learn. Strike me twice, I become paperwork."

If player uses repeated damage:

- "Again? How generous. I was running out of you."

If player uses `mirror + eye`:

- "Ah. You came to see, not take. That is terribly inconvenient."

Defeat/spare outcome:

- Defeated: "Take the shard. May it itch in your pocket."
- Spared: "Take the memory of the shard. It weighs less and opens more doors."

### Mold Librarian

- Sprite role: monk, expert druid, or promoted blue/purple unit.
- Map: Wet Library.
- Role: Act 2 story anchor.
- Want: preserve the archive and stop the Calendar Key from being stolen again.
- Character function: makes investigation understandable; reacts strongly to
  reading, burning, and shortcuts.

First meeting:

- "Quiet. The books are damp, frightened, and legally witnesses."
- "The Calendar Key is ink-locked. It opens for readers, not burglars."

If player reads clues:

- "Good. A person who reads before exploding things. I had hoped the species was
  not finished."

If player burns shelves:

- "That was a century of notes and three perfectly dry jokes."

If trust is high:

- "When the Beast asks what you are, say: a clerk who learned to listen."

### Index Wisp

- Sprite role: glowing wisp.
- Map: Wet Library and Clock Sewer.
- Role: clue delivery without feeling like a tutorial popup.
- Want: be indexed correctly.
- Character function: repeats important hints in simple language.

Dialogue:

- "Key plus Eye plus Wave. The chest likes calm witnesses."
- "If lost: follow the wet floor. It is going somewhere against policy."
- "The sewer has a clean memory. Leaf and Wave can wake it."

### Bone Market Merchant

- Sprite role: vile witch, adept necromancer, worker with gold, black building
  stall.
- Map: Bone Market.
- Role: optional risk/reward vendor.
- Want: sell power, collect debts, remain charming.
- Character function: weapon system, curse trades, alternate endings.

First meeting:

- "Welcome to the Bone Market. Prices are low because some are metaphorical."
- "I sell weapons, refunds, and mistakes with handles."

Weapon offer lines:

- Wand: "For tidy spellwork and untidy consequences."
- Bone Blade: "For customers who think healing lacks teeth."
- Mirror Shield: "For people who want enemies to participate in their own
  defeat."
- Coin Sling: "Turns money into arguments at excellent range."
- Bell Staff: "Rings once for help, twice for trouble, three times for lawyers."

If player accepts cursed deal:

- "Excellent. Your future has approved the loan by screaming."

If player repays debt:

- "Responsible customers are terrible for business and wonderful for endings."

### Debt Collector

- Sprite role: goblin barrel/TNT, black lancer, or red warrior.
- Map: Gate Approach if debts are unpaid.
- Role: consequence miniboss.
- Want: collect shortcuts the player forced earlier.
- Character function: makes `broken_mark + key` feel powerful but costly.

Intro:

- "You opened three doors with one apology. I am here for the other two."
- "Debt is just a monster that learned accounting."

If defeated:

- "Fine. Consider the account emotionally closed."

### Water Spirit

- Sprite role: water elemental or glowing wisp.
- Map: Clock Sewer.
- Role: optional good-ending ally.
- Want: restore clean flow through the road.
- Character function: rewards utility runes and noncombat exploration.

Dialogue:

- "I used to be a river. Now I am a hallway with regrets."
- "Wave moves water. Leaf reminds it why."
- "Clean me, and I will carry one kindness to the final room."

If helped:

- "The water remembers the sky. So will I."

### Calendar Beast

- Sprite role: adept necromancer, purple goblin, or future custom boss.
- Map: Calendar Beast Arena.
- Role: final boss and thematic resolution.
- Want: eat tomorrow because people keep wasting today.
- Character function: tests combat, story flags, allies, rune variety, and
  ending choices.

Intro:

- "Little clerk. You rang the bell. I answered."
- "I do not hate the future. I am simply hungry, and yours was left unattended."

Phase 1:

- "Show me the language you broke me with."

Phase 2:

- "I know that spell now. Draw a new mistake."

If allies appear:

- Tourist: "I brought sandwiches and very limited courage!"
- Librarian: "For the record, I object to being eaten by an overdue date."
- Water Spirit: "The clean river enters the room."
- Queue Goblin: "I am only helping because the Beast owes toll."

Phase 3, good-route prompt:

- "Break me and the loop ends. Repair me and the future returns. Feed me and no
  one has to be disappointed by tomorrow again."

Defeat default:

- "Then take your morning. It was always too bright for me."

Repair ending:

- "You learned the rarest rune: enough."

Devoured ending:

- "Thank you, clerk. I will spend your tomorrows carefully."

## Campaign Structure

### Opening: The Bell Rings Thirteen Times

Map: Goblin Toll Road Hub.

Player goal:

- Learn movement, targeting, rune casting, NPC interaction, and the first quest:
  find the Calendar Shard in the caverns.

Story beats:

- Queue Goblin blocks the road.
- Lost Tourist introduces kind magic.
- Blue Watch Archer teaches weakness targeting.
- Road Druid hints that the calendar is a living system.
- The Calendar Gate is visible but locked, so the player understands the final
  destination early.

Required player understanding:

- "I need to explore the caverns to get the first calendar piece."
- "Runes can fight, unlock, heal, reveal, and change NPC reactions."

### Act 1: Reflections Under The Road

Map: Mirror Fungus Caverns.

Player goal:

- Get Calendar Shard 1 or its memory.

Story beats:

- Mirror Hermit explains `mirror + eye`.
- Fungus enemies copy or resist repeated direct damage.
- Fungus nursery gives a clear choice: burn, ignore, or spare.
- Mirror Mycologist miniboss tests spell variety.

Required player understanding:

- "Repeated brute force can backfire."
- "Some enemies can be solved better through the right rune idea."
- "The game remembers whether I spared or burned things."

### Act 2: The Library That Leaks Yesterday

Map: Wet Library.

Player goal:

- Find the Calendar Key and learn the truth: the calendar is broken because the
  road was using tomorrow as debt collateral.

Story beats:

- Mold Librarian asks player to read before stealing.
- Index Wisp gives simple puzzle reminders.
- Restricted stacks open after Calendar Shard 1.
- Ink-Locked Chest requires `key + eye + wave`.
- Burning shelves creates a shortcut but worsens ending pressure.

Required player understanding:

- "The Calendar Key can open the final gate, but the ending depends on what I
  learned and how I acted."
- "Clues are optional but powerful."

### Optional Act: The Bone Market

Map: Bone Market.

Player goal:

- Get a weapon, repay or deepen debt, unlock optional ending routes.

Story beats:

- Merchant offers weapons with clear gameplay identity.
- Cursed deals are tempting and funny, but tracked.
- Secret merchant appears for coin/bell mastery.
- Debt choices determine whether the Debt Collector appears later.

Required player understanding:

- "Weapons make my rune choices more interesting."
- "Shortcuts and cursed power have story cost."

### Optional Act: Clock Sewer

Map: Clock Sewer.

Player goal:

- Restore clean water, unlock shortcut, earn final-boss support.

Story beats:

- Water Spirit frames the sewer as a repairable place, not just a dungeon.
- Valve rooms teach utility rune gates.
- Clean-water shrine requires `wave + leaf`.
- Restoring water creates a visible route back to the Toll Road and a final ally.

Required player understanding:

- "Noncombat exploration can make the final fight easier and change the ending."

### Act 3: Calendar Gate Approach

Map: Calendar Gate Approach.

Player goal:

- See consequences, prepare, and enter the final arena.

Story beats:

- Helped NPCs appear in alcoves.
- Destroyed buildings or debt enemies appear if player acted harshly.
- Debt Collector appears if debt is unpaid.
- Blue Watch Archer or Mold Librarian gives one final simple hint.

Required player understanding:

- "My earlier actions are now visible."
- "I am going into the final boss with the allies and problems I created."

### Finale: Calendar Beast Arena

Map: Calendar Beast Arena.

Player goal:

- Defeat, repair, feed, or politically replace the Calendar Beast.

Story beats:

- Boss changes phase at 66% and 33% HP.
- Boss resists repeated rune schools.
- Allies deliver short support lines and small deterministic benefits.
- Final phase exposes ending choices if flags qualify.

Required player understanding:

- "I can win by damage, but better endings need story knowledge and deliberate
  rune choices."

## Dialogue System

### Dialogue Types

- `bark`: one short line triggered by proximity, combat, or map state.
- `npc_response`: 1-2 sentences after casting at or talking to an NPC.
- `story_toast`: immediate event narration after an action.
- `journal_entry`: durable summary of a discovery or consequence.
- `boss_line`: phase intro, reaction, or low-HP line.
- `ending_line`: final outcome summary.

### LLM Input

Send only explicit state. Do not rely on hidden memory.

```json
{
  "area": "Wet Library",
  "scene": "ink_locked_chest",
  "target": {
    "id": "ink_chest",
    "name": "Ink-Locked Chest",
    "type": "chest",
    "state": "locked"
  },
  "player": {
    "level": 3,
    "hp": 9,
    "courage": 6,
    "weapon": "Mirror Shield",
    "inventory": ["Calendar Shard 1", "wet candle"],
    "story_flags": ["mirror_truth_seen", "tourist_helped"],
    "npc_trust": {"librarian": 2}
  },
  "action": {
    "mode": "drawing",
    "runes": ["key", "eye", "wave"],
    "validated_spell_name": "Patient Witness Key",
    "deterministic_result": "chest_unlocked"
  },
  "tone": "clear, weird, warm, short"
}
```

### LLM Output

The model returns text only. It may suggest a story flag, but Python decides if
the flag is allowed.

```json
{
  "story_toast": "The lock stops pretending to be a lock and becomes a very wet keyhole.",
  "npc_line": "Mold Librarian: Good. You asked the chest a question instead of starting a fire.",
  "journal_entry": "The Ink-Locked Chest opened to key, eye, and wave. The library trusts careful magic.",
  "suggested_story_flag": "ink_chest_opened_patiently",
  "mood_shift": "library_less_hostile"
}
```

### Output Limits

- `story_toast`: max 140 characters.
- `npc_line`: max 240 characters.
- `journal_entry`: max 420 characters.
- `suggested_story_flag`: must match allowlisted flags.
- If output is invalid, use deterministic fallback text.

## Dialogue Rules For The LLM

- Always be clear about what happened.
- Put the useful information first, joke second.
- Never require the player to understand deep lore to know the next objective.
- Mention concrete player actions: the rune used, the NPC helped, the debt
  accepted, the weapon equipped, or the boss phase changed.
- Use callbacks only when the matching flag is present.
- Do not invent items, map exits, bosses, or quest requirements.
- Do not promise a reward unless the deterministic action already granted it.
- Keep fantasy words simple. Prefer "Calendar Key" over "chrono-ordinal
  reliquary".
- Characters can be funny, but they should still want understandable things.

## Story Flags

### Trust And NPC Flags

- `tourist_helped`: Lost Tourist can appear before the final boss.
- `tourist_scared`: Tourist avoids player; fear route gets Bone Market discount.
- `librarian_trust`: increases when player reads clues or avoids burning books.
- `librarian_angry`: set if player burns shelves or forces the archive.
- `water_spirit_helped`: Water Spirit assists in final fight.
- `queue_goblin_paid`: goblin respects player and may help with Tollmaster route.
- `queue_goblin_forced`: goblin calls player an incident report later.

### Dungeon Choice Flags

- `mirror_truth_seen`: reveals Calendar Beast weak point.
- `fungus_colony_spared`: unlocks repair-ending support.
- `fungus_colony_burned`: unlocks shortcut but worsens final mood.
- `wet_catalog_read`: adds clear journal hint for Calendar Key.
- `library_shelves_burned`: creates shortcut, blocks some good-ending dialogue.
- `clean_water_restored`: opens sewer shortcut and good-ending ally.

### Debt And Weapon Flags

- `debt_accepted`: player forced a shortcut or cursed deal.
- `debt_repaid`: prevents Debt Collector spawn.
- `debt_deepened`: worsens Calendar Devoured ending pressure.
- `weapon_bought`: merchant recognizes player later.
- `secret_merchant_met`: unlocks rare weapon or Tollmaster route.

### Ending Flags

- `calendar_truth_read`: required for repaired ending.
- `calendar_key_found`: required for final gate.
- `calendar_repair_possible`: set if truth read plus enough allies/helpful acts.
- `calendar_devour_pressure`: increases with curses, burned shelves, unpaid debt.
- `tollmaster_route_open`: set by coin/bell mastery, paid tolls, spared goblins.

## Weapons As Story

Weapons are not just stats. Each weapon gives the player a story identity and
changes how NPCs react.

### Clerk Wand

- Starting weapon.
- Identity: official but weak.
- NPC reaction: "You still have the training wand? Brave or underfunded."
- Gameplay: reliable baseline, no strong bonus.

### Bell Staff

- Route: Toll Road secret shrine or Bone Market.
- Identity: summons help, annoys goblins, interrupts bosses.
- Story flags: supports Tollmaster route.
- NPC reaction: "Please stop ringing public infrastructure."

### Mirror Shield

- Route: Mirror Fungus Caverns nonviolent path.
- Identity: defensive, reflective, patient.
- Story flags: supports repaired ending.
- NPC reaction: "That shield shows people the version they were avoiding."

### Bone Blade

- Route: Bone Market cursed deal.
- Identity: strong, scary, debt-heavy.
- Story flags: raises devour pressure if overused.
- NPC reaction: "That knife has more opinions than most citizens."

### Coin Sling

- Route: Bone Market or Toll Road coin route.
- Identity: economy magic, tolls, bribery, secret merchant.
- Story flags: supports Tollmaster route.
- NPC reaction: "You weaponized payment. The goblins are moved."

### River Thread

- Route: Clock Sewer clean-water shrine.
- Identity: utility, binding, repair, ally support.
- Story flags: supports repaired ending and water spirit ally.
- NPC reaction: "That thread smells like rain that forgave someone."

## Sample Player-Facing Story Beats

### First Minute

System toast:

- "The Calendar Bell rings thirteen times. Somewhere under the road, tomorrow
  wakes up hungry."

Queue Goblin:

- "Road's closed. Calendar's screaming. Toll is one coin, one apology, or one
  legally confusing spell."

Blue Watch Archer:

- "Face a target before casting. Magic is powerful, but it will absolutely hit
  the wrong paperwork."

HUD objective:

- "Find the Calendar Shard in the caverns."

Journal:

- "I broke the dungeon calendar. The road guards are treating this as both a
  disaster and a staffing issue."

### First Kind Choice

Lost Tourist:

- "Is this the way to Tuesday? My map keeps changing its teeth."

If helped:

- "The Tourist stops shaking. The map still hates you, but now it does so from
  a respectful distance."

If scared:

- "The Tourist flees into a bush that was not previously accepting visitors."

### First Big Discovery

Mirror Hermit:

- "The Beast is not behind the calendar. It is inside the habit of wasting it."

Journal:

- "The Mirror Stone showed a truth: the Calendar Beast feeds on ignored
  tomorrows, unpaid debts, and spells cast without care."

### Pre-Boss Consequence Moment

If many allies:

- "The gate is crowded. Somehow, people you helped got here before you."

If many debts:

- "The gate is crowded. Unfortunately, most of the crowd has invoices."

If mixed:

- "The gate remembers both your kindness and your shortcuts."

## Endings

### Calendar Broken

Requirement:

- Defeat the Calendar Beast without repair conditions.

Ending text:

- "The Beast falls. Tomorrow returns, slightly dented. The Toll Road reopens
  with a new sign: DO NOT RING THE BELL UNLESS SUPERVISED."

Tone:

- Valid default ending. Funny, complete, not a failure.

### Calendar Repaired

Requirement:

- `calendar_truth_read`
- At least two helper flags: `tourist_helped`, `fungus_colony_spared`,
  `librarian_trust`, `clean_water_restored`, `queue_goblin_paid`
- Use at least one repair-oriented rune in final phase: `eye`, `mirror`,
  `spiral`, `wave`, or `leaf`

Ending text:

- "You do not kill tomorrow. You teach it where to stand. The calendar closes
  its teeth, opens its pages, and gives everyone one honest morning."

Tone:

- Best standard ending. Warm and earned.

### Calendar Devoured

Requirement:

- Defeat the boss while `calendar_devour_pressure` is high from curse deals,
  burned shelves, unpaid debt, or repeated forced locks.

Ending text:

- "The Beast falls forward, smiling. It does not eat you. It eats every morning
  you were not careful enough to protect."

Tone:

- Darkly funny bad ending. Player still technically wins.

### Secret Tollmaster

Requirement:

- `tollmaster_route_open`
- Coin/bell mastery.
- Queue Goblin paid or spared.
- Secret merchant met.

Ending text:

- "The Beast offers you the road. You accept, because someone has to organize
  the chaos. The first new law is simple: all tolls may be paid in coins,
  sandwiches, or sincere spellcraft."

Tone:

- Weird prestige ending for curious players.

## LLM Prompt Template

Use this as the system/developer instruction for story generation:

```text
You are the story voice for Rune Goblin, a funny but sincere dungeon crawler.
Write clear, short fantasy dialogue for normal players. The world is strange,
but objectives must be understandable.

Rules:
- Use only the provided state.
- Do not invent items, quests, exits, rewards, or damage.
- React to the player's concrete action and known story flags.
- Keep text short.
- Put useful information before jokes.
- Return valid JSON only.
- If a character speaks, preserve their personality.
```

Use this as the user payload:

```text
Current area: {area}
Scene: {scene}
Target: {target_json}
Player state: {player_json}
Recent action: {action_json}
Allowed story flags: {allowed_flags}
Needed output fields: story_toast, npc_line, journal_entry, suggested_story_flag, mood_shift
```

## Implementation Notes

- Add deterministic fallback dialogue tables for every NPC, map, boss phase, and
  major flag. LLM failure should never block play.
- Store `journal_entry` text only after validation and de-duplication.
- Use short `story_toast` text for action feedback and longer `journal_entry`
  text for optional reading.
- Let the LLM vary flavor, but keep quest-critical clues deterministic and
  repeated in at least two places.
- Use area-specific dialogue pools so characters do not sound interchangeable.
- Add a "recent story events" list with only the last 3 validated events. This
  helps the LLM make callbacks without pretending to remember the whole run.
- If a player repeats the same interaction, generate shorter repeat text or use
  deterministic repeat lines.

## Story Acceptance Criteria

- A first-time player can state the main goal after 60 seconds.
- Every major map has at least one memorable NPC line, one story object, one
  visible consequence, and one journal discovery.
- At least three player choices visibly pay off before the final boss.
- Final boss dialogue changes based on at least four flags.
- Every ending names specific choices the player made.
- LLM text is entertaining but never required to understand the next objective.
