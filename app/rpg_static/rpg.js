// Rune Goblin RPG — client-side canvas game.
// Movement, rendering and exploration run here; casting round-trips to the
// Python bridge (/rg/cast) so the engine + goblinV1 vision model stay the
// spell authority.
(function () {
  "use strict";

  // ---- state ----
  let W = null;                 // world payload from /rg/world
  let worldSeed = null;         // optional replay seed from /play?seed=...
  let bootFlags = [];           // optional smoke flags from /play?flags=a,b
  let bootArea = "";            // optional smoke area from /play?area=...
  let bootMasteryChoice = false; // optional smoke hook from /play?mastery=1
  let areas = {};               // mutable per-area state (entities/rows)
  let adminMode = false;        // client-side god-mode (Shift+L+A) — all maps unlocked
  let adminLockSnapshot = null; // saved lock states so the toggle is reversible
  let lastAdminToggle = 0;      // debounce for the Shift+L+A chord
  const keysDown = new Set();   // currently-held keys, for multi-key combos
  const ADMIN_ITEMS = ["Calendar Key", "Calendar Shard", "Debt Receipt", "Thawed Ember"];
  let runesMeta = [];           // [{key,symbol,label,meanings}]
  let P = null;                 // player {area,x,y,hp,max_hp,courage,...}
  let A = null;                 // current area
  let selected = [];            // selected rune keys (quick-cast)
  let facing = "down";
  let busy = false, over = false, drawing = false, paused = false;
  let toastMsg = "";
  let vfx = [];                 // active visual effects
  let turnNo = 0;
  let recentRunes = [];
  let enemyCooldown = {};
  let masteryChoiceOpen = false;
  let selecting = false;        // title-screen character select active
  let chosenClass = null;       // selected goblin class id
  let journalOpen = false;
  let invOpen = false;
  let objHit = null;            // canvas-space click box for the HUD objective icons
  let dialogueOpen = false;
  let lastEnding = null;        // {ending,title,text} from win_game action
  let lastCastMetadata = null;  // structured /rg/cast metadata for HUD/debug
  let CLASSES = [], WEAPONS = {}, ITEMS = {}, QUESTS_META = {};
  let STORY_BEATS = [];         // proactive beat triggers from /rg/world
  let barks = [];               // live speech bubbles: {eid, area, text, until}
  const CLASS_SPRITE = {        // in-game sprite per class (Goblin Pack #1 hero sheets)
    warrior: "hero_warrior", rogue: "hero_rogue", poison: "hero_poison",
    hunter: "hero_hunter", barbarian: "hero_barbarian",
  };
  const CLASS_SPRITE_FALLBACK = {  // generic goblins if a hero sheet fails to load
    warrior: "goblin_red", rogue: "goblin_yellow", poison: "goblin_purple",
    hunter: "goblin_blue", barbarian: "goblin_red",
  };
  const KING_SPRITE = "hero_king";  // evolved Goblin King in-game sprite

  let canvas, ctx, sketch, sctx;
  let TILE = 40, OX = 0, OY = 64, COLS = 20, ROWS = 13;
  const HUD_TOP = 64;

  const DIRV = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };
  const WALK = new Set([".", ","]);

  // Per-biome look: wall palette + ground tile sprite + optional tint wash.
  // ground: which baked tile to draw on walkable floor (grass | sand | snow | stone)
  // tint:   translucent wash over the ground so reused tiles still read as new places
  const BIOME = {
    toll_road: { floor: "#2e2415", alt: "#352a18", wall: "#6b5430", edge: "#46371d",
                 ground: "grass", tint: null },
    cavern:    { floor: "#13232a", alt: "#163038", wall: "#2c4e58", edge: "#1d3b42",
                 ground: "stone", tint: "rgba(18,76,96,0.30)" },
    library:   { floor: "#1a2230", alt: "#202a3c", wall: "#34465e", edge: "#222f44",
                 ground: "stone", tint: "rgba(36,52,84,0.34)" },
    arena:     { floor: "#2a1230", alt: "#331640", wall: "#5a2a66", edge: "#3d1c47",
                 ground: "sand", tint: "rgba(90,28,92,0.30)" },
    market:    { floor: "#2e1f12", alt: "#372615", wall: "#6b4a26", edge: "#46311a",
                 ground: "sand", tint: "rgba(116,64,18,0.16)" },
    sewer:     { floor: "#13241c", alt: "#162b21", wall: "#2c5842", edge: "#1d4230",
                 ground: "stone", tint: "rgba(24,88,52,0.30)" },
    gate:      { floor: "#241a2c", alt: "#2b2036", wall: "#544a6b", edge: "#372f47",
                 ground: "grass", tint: "rgba(58,34,84,0.28)" },
    ice:       { floor: "#1c2733", alt: "#22303f", wall: "#4a6a8a", edge: "#324a61",
                 ground: "snow", tint: null },
    forge:     { floor: "#2e1410", alt: "#371a12", wall: "#6b3a26", edge: "#46271a",
                 ground: "stone", tint: "rgba(150,52,10,0.26)" },
  };
  const DEFAULT_BIOME = { floor: "#1a1426", alt: "#211a30", wall: "#4a3a6b", edge: "#2a1f3d",
                          ground: "grass", tint: "rgba(20,20,30,0.25)" };
  const HAZARD = "#1f5e7a";

  // rune -> VFX school (colour + glyph), small client mirror of vfx.py
  const SCHOOL = {
    flame: ["#ff6a00", "🔥"], jagged_line: ["#9be7ff", "⚡"], spiral: ["#b07cff", "🌀"],
    tooth: ["#ff8fa3", "🦷"], bone: ["#ece4cf", "💀"], three_dots: ["#7bd66a", "🐝"],
    wave: ["#4fc3ff", "🌊"], leaf: ["#6df5a0", "🍃"], closed_circle: ["#ffce6b", "🛡"],
    mirror: ["#cfd8ff", "🪞"], bell: ["#ffd24a", "🔔"], thread: ["#d59bff", "🧵"],
    coin: ["#ffd700", "🪙"], eye: ["#9be7ff", "👁"], key: ["#ffce6b", "🗝"],
    broken_mark: ["#ff3d6e", "💢"],
  };

  // ---- sprites (Tiny Swords by Pixel Frog, CC0) ----
  const SPR_BASE = "/rg/static/sprites/";
  const SPRITES = {
    grass: { src: "grass.png", tile: true },
    sand: { src: "sand.png", tile: true },
    snow: { src: "snow.png", tile: true },
    stone: { src: "stone.png", tile: true },
    water: { src: "water.png", tile: true },
    player: { src: "player.png", fw: 192, fh: 192, frames: 8, anim: true, scale: 1.6 },
    npc_pawn: { src: "npc_pawn.png", fw: 192, fh: 192, frames: 8, anim: true, scale: 1.4 },
    npc_monk: { src: "npc_monk.png", fw: 192, fh: 192, frames: 6, anim: true, scale: 1.4 },
    goblin_red: { src: "goblin_red.png", fw: 192, fh: 192, frames: 7, anim: true, scale: 1.4 },
    goblin_blue: { src: "goblin_blue.png", fw: 192, fh: 192, frames: 7, anim: true, scale: 1.4 },
    goblin_purple: { src: "goblin_purple.png", fw: 192, fh: 192, frames: 7, anim: true, scale: 1.45 },
    goblin_yellow: { src: "goblin_yellow.png", fw: 192, fh: 192, frames: 7, anim: true, scale: 1.35 },
    chest_gold: { src: "chest_gold.png", fw: 128, fh: 128, frames: 1, scale: 1.0 },
    shrine_tower: { src: "shrine_tower.png", fw: 128, fh: 256, frames: 1, scale: 1.65 },
    goblin_house: { src: "goblin_house.png", fw: 128, fh: 192, frames: 1, scale: 1.65 },
    knight_tower_blue: { src: "knight_tower_blue.png", fw: 128, fh: 256, frames: 1, scale: 1.7 },
    goblin_tower_red: { src: "goblin_tower_red.png", fw: 128, fh: 192, frames: 8, anim: true, scale: 1.6 },
    bridge_all: { src: "bridge_all.png", fw: 192, fh: 256, frames: 1, scale: 1.15 },
    happy_sheep: { src: "happy_sheep.png", fw: 128, fh: 128, frames: 8, anim: true, scale: 0.9 },
    blue_archer: { src: "blue_archer.png", fw: 192, fh: 192, frames: 6, anim: true, scale: 1.25 },
    red_warrior: { src: "red_warrior.png", fw: 192, fh: 192, frames: 8, anim: true, scale: 1.35 },
  };
  const STATIC = "/rg/static/";
  const VFXM = {};            // name -> {img, fw, fh, frames}
  const SFXB = {};            // name -> url for Audio
  let CIRCLES = null;         // magic-circle atlas {img, fw, fh, frames, fps, entries}
  // creatures are tiny 16px sprites; keep them ~player-sized or smaller, not huge
  const CRE_SCALE = {
    magical_fairy: 0.9, fluttering_pixie: 0.85, glowing_wisp: 0.9,
    iron_golem: 1.3, earth_elemental: 1.2, ice_golem: 1.25, water_elemental: 1.05,
    corrupted_treant: 1.35, grizzled_treant: 1.35, adept_necromancer: 1.2,
    vile_witch: 1.05, fire_elemental: 1.1, deft_sorceress: 1.05,
    expert_druid: 1.1, novice_pyromancer: 1.05,
    // Goblin Pack hero frames include weapon swing padding. Keep their draw
    // boxes near one tile wide so they read as units beside houses and towers.
    hero_warrior: 1.65, hero_rogue: 1.45, hero_poison: 1.45,
    hero_hunter: 1.4, hero_barbarian: 1.7, hero_king: 1.75, water_foam: 1.0, water_rocks: 1.0,
    // new Tiny Swords additions
    flame: 1.0, tnt_goblin: 1.4, barrel_goblin: 1.35,
    wood_tower_blue: 1.6, wood_tower_purple: 1.6, wood_tower_yellow: 1.6,
  };
  const DECO_SCALE = {
    tree: 2.6, bush: 0.95, rock: 0.8, rock2: 0.8,
    goblin_house_destroyed: 1.65, knight_house_blue: 1.65,
    wood_tower_destroyed: 1.75, wood_tower_building: 1.75,
    castle_blue: 2.35, castle_red: 2.35, castle_destroyed: 2.35, black_castle: 2.35,
    knight_tower_yellow: 1.7, purple_tower: 1.7,
    red_barracks: 2.0, yellow_monastery: 1.85, gold_mine: 1.6,
    // new Tiny Swords additions
    tree_snow: 2.6, tree_dead: 2.6, skull: 0.85,
    house_red: 1.65, house_purple: 1.65, house_yellow: 1.65, house_destroyed: 1.65,
    castle_yellow: 2.35, castle_purple: 2.35, tower_red: 1.7, tower_destroyed: 1.7,
    goldmine_destroyed: 1.6, goldmine_inactive: 1.6,
    res_gold: 0.9, res_wood: 0.9, res_meat: 0.9,
  };
  function loadSprites() {
    Object.values(SPRITES).forEach((s) => { const img = new Image(); img.src = SPR_BASE + s.src; s.img = img; });
  }
  async function loadManifest() {
    let m;
    try { m = await fetch(STATIC + "manifest.json").then((r) => r.json()); }
    catch (e) { return; }
    for (const [k, v] of Object.entries(m.vfx || {})) {
      const img = new Image(); img.src = STATIC + v.file;
      VFXM[k] = { img, fw: v.fw, fh: v.fh, frames: v.frames };
    }
    for (const [k, v] of Object.entries(m.creatures || {})) {
      const img = new Image(); img.src = STATIC + v.file;
      SPRITES[k] = { img, fw: v.fw, fh: v.fh, frames: v.frames, anim: v.frames > 1, scale: CRE_SCALE[k] || 1.0 };
    }
    for (const [k, v] of Object.entries(m.deco || {})) {
      const img = new Image(); img.src = STATIC + v.file;
      const tall = v.fh > v.fw, big = v.fw >= 192;
      SPRITES[k] = { img, fw: v.fw, fh: v.fh, frames: 1, anim: false,
        scale: DECO_SCALE[k] || (big ? 1.45 : tall ? 1.25 : 0.95) };
    }
    for (const [k, v] of Object.entries(m.sfx || {})) SFXB[k] = STATIC + v;
    if (m.circles) {
      const img = new Image(); img.src = STATIC + m.circles.file;
      CIRCLES = { img, fw: m.circles.fw, fh: m.circles.fh, frames: m.circles.frames,
        fps: m.circles.fps || 12, entries: m.circles.entries || [] };
    }
  }
  // pick the magic-circle row whose runes best match the cast
  const RUNE_SHORT = { closed_circle: "circle", jagged_line: "jagged", broken_mark: "broken", three_dots: "dots" };
  function circleRow(runes) {
    if (!CIRCLES || !CIRCLES.entries.length) return -1;
    const short = runes.map((r) => RUNE_SHORT[r] || r);
    let best = CIRCLES.entries[0].row, bestScore = -1;
    for (const e of CIRCLES.entries) {
      const s = e.runes.filter((x) => short.includes(x)).length;
      if (s > bestScore) { bestScore = s; best = e.row; }
    }
    return best;
  }
  function spr(name) {
    const s = SPRITES[name];
    return (s && s.img && s.img.complete && s.img.naturalWidth) ? s : null;
  }
  function drawTileSprite(name, px, py) {
    const s = spr(name); if (!s) return false;
    ctx.drawImage(s.img, 0, 0, s.img.naturalWidth, s.img.naturalHeight, px, py, TILE + 1, TILE + 1);
    return true;
  }
  // bottom-centred unit/object sprite at screen (cx, baseY)
  function drawUnitSprite(name, cx, baseY, scale, frameIndex) {
    const s = spr(name); if (!s) return false;
    const fw = s.fw || s.img.naturalWidth, fh = s.fh || s.img.naturalHeight;
    const fcount = s.frames || 1;
    const col = (s.anim && fcount > 1) ? (frameIndex % fcount) : 0;
    const dw = TILE * (scale || s.scale || 1.4);
    const dh = dw * (fh / fw);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(s.img, col * fw, 0, fw, fh, cx - dw / 2, baseY - dh, dw, dh);
    return true;
  }
  const GOBLIN_BY_NAME = {
    "Queue Goblin": "goblin_red", "Mirror Fungus": "goblin_yellow",
    "PDF Wraith": "goblin_blue", "Tax Wraith": "goblin_blue",
    "Stapler Hydra": "goblin_red", "Mold Knight": "goblin_yellow",
    "Calendar Beast": "goblin_purple",
  };
  function entitySprite(e) {
    if (e.sprite_key && SPRITES[e.sprite_key]) return e.sprite_key;
    if (e.type === "boss") return "goblin_purple";
    if (e.type === "enemy") return GOBLIN_BY_NAME[e.name] || "goblin_red";
    if (e.type === "npc") return e.id === "librarian" ? "npc_monk" : "npc_pawn";
    if (e.type === "story_object") return e.sprite_key || "shrine_tower";
    if (e.type === "chest" || e.type === "powerup") return "chest_gold";
    if (e.type === "shrine" || e.type === "locked_door") return "shrine_tower";
    return null; // portals are drawn as a glow
  }

  // ---- spell element + complexity tier (drives the drawn magic) ----
  const ELEM_OF = {
    flame: "fire", tooth: "fire", jagged_line: "electric", wave: "water",
    leaf: "poison", three_dots: "poison", thread: "poison", bone: "dark",
    broken_mark: "dark", spiral: "wind", eye: "light", mirror: "light",
    closed_circle: "light", bell: "light", coin: "light", key: "light",
  };
  function elementOf(runes) {
    for (const r of runes) if (ELEM_OF[r]) return ELEM_OF[r];
    return "light";
  }
  const ELEM_VFX = {
    fire: { cast: "fire_cast", proj: "fire_ball", impact: "fire_burst", sound: "fire" },
    water: { cast: "ice_cast", proj: "ice_pick", impact: "ice_shatter", sound: "water" },
    electric: { cast: "light_cast", proj: "star", impact: "holy", sound: "electric" },
    poison: { cast: "poison_cast", proj: "poison_claw", impact: "poison_claw", sound: "earth" },
    wind: { cast: "tornado", proj: "tornado", impact: "tornado", sound: "wind" },
    light: { cast: "light_cast", proj: "star", impact: "holy", sound: "light" },
    dark: { cast: "poison_cast", proj: "poison_claw", impact: "explosion", sound: "dark" },
  };
  function spellTier(s, runes) {
    const chaos = s.chaos || 0, dmg = -(s.enemy_hp_delta || 0);
    let t = 1;
    if (chaos >= 4 || dmg >= 3 || runes.length >= 3) t = 2;
    if (chaos >= 6 || dmg >= 5 || runes.length >= 4) t = 3;
    if (chaos >= 8 || dmg >= 7 || runes.includes("broken_mark")) t = 4;
    return t;
  }
  function playSfx(name, tier) {
    if (!musicOn) return;
    const url = SFXB[name] || SFXB.light;
    if (url) { try { const a = new Audio(url); a.volume = 0.22; a.play().catch(() => {}); } catch (e) {} }
    if (tier >= 3 && SFXB.charge) { try { const c = new Audio(SFXB.charge); c.volume = 0.16; c.play().catch(() => {}); } catch (e) {} }
  }
  // Each region gets a distinct entry cue so areas feel sonically different.
  const REGION_SFX = {
    toll_road: "good", cavern: "water", library: "light", market: "dark",
    sewer: "water", gate: "charge", arena: "power",
  };
  function regionCue() {
    if (!musicOn || !A) return;
    const name = REGION_SFX[A.biome] || "sweep";
    const url = SFXB[name];
    if (url) { try { const a = new Audio(url); a.volume = 0.3; a.play().catch(() => {}); } catch (e) {} }
  }

  // ---- music (original procedural chiptune via Web Audio) ----
  let actx = null, masterGain = null, musicOn = true, musicTimer = null, step = 0;
  const PENTA = [0, 3, 5, 7, 10];           // minor pentatonic
  const ROOT_HZ = 196;                      // ~G3
  function noteHz(semi) { return ROOT_HZ * Math.pow(2, semi / 12); }
  function blip(freq, t, dur, type, gain) {
    const o = actx.createOscillator(), g = actx.createGain();
    o.type = type || "square"; o.frequency.value = freq;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(gain || 0.2, t + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g); g.connect(masterGain); o.start(t); o.stop(t + dur + 0.02);
  }
  function startMusic() {
    if (musicTimer || !actx) return;
    const beat = 60 / 96 / 2; // eighth notes @ 96bpm
    musicTimer = setInterval(() => {
      if (!actx || !musicOn) return;
      const t = actx.currentTime + 0.03;
      if (step % 4 === 0) blip(noteHz(PENTA[(step / 4 | 0) % PENTA.length] - 12), t, beat * 3.2, "triangle", 0.22);
      const mel = PENTA[(step * 2) % PENTA.length] + (step % 8 >= 4 ? 12 : 0);
      blip(noteHz(mel), t, beat * 0.85, "square", 0.10);
      step = (step + 1) % 32;
    }, beat * 1000);
  }
  function initAudio() {
    if (actx) { if (actx.state === "suspended") actx.resume(); return; }
    const AC = window.AudioContext || window.webkitAudioContext; if (!AC) return;
    actx = new AC(); masterGain = actx.createGain();
    masterGain.gain.value = musicOn ? 0.05 : 0; masterGain.connect(actx.destination);
    startMusic();
  }
  function toggleMute() {
    musicOn = !musicOn;
    if (masterGain) masterGain.gain.value = musicOn ? 0.05 : 0;
    const b = $("rg-mute"); if (b) b.textContent = musicOn ? "🔊" : "🔇";
  }

  // ---- helpers ----
  const $ = (id) => document.getElementById(id);
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const now = () => performance.now();

  function api(path, body) {
    const opt = body ? {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    } : undefined;
    return fetch(path, opt).then((r) => r.json());
  }
  function worldUrl() {
    const params = new URLSearchParams(window.location.search || "");
    const raw = params.get("seed");
    worldSeed = raw && /^-?\d+$/.test(raw) ? parseInt(raw, 10) : null;
    bootFlags = (params.get("flags") || "").split(",")
      .map((x) => x.trim()).filter(Boolean);
    bootArea = (params.get("area") || "").trim();
    bootMasteryChoice = params.get("mastery") === "1";
    return "/rg/world" + (worldSeed === null ? "" : ("?seed=" + encodeURIComponent(String(worldSeed))));
  }

  function toast(msg) { toastMsg = msg; const t = $("rg-toast"); if (t) t.innerHTML = msg; }

  function school(runes) {
    for (const k of Object.keys(SCHOOL)) {
      if (runes.includes(k) && !(k === "broken_mark" && runes.length > 1)) return SCHOOL[k];
    }
    return ["#b07cff", "✨"];
  }

  function ensurePlayerMeta() {
    P.inventory = P.inventory || [];
    P.statuses = P.statuses || [];
    P.quest_log = P.quest_log || [];
    P.discoveries = P.discoveries || [];
    P.trust = P.trust || {};
    P.level = P.level || 1;
    P.xp = P.xp || 0;
    P.xp_to_next = P.xp_to_next || 8;
    P.goblin_class = P.goblin_class || "warrior";
    P.weapon = P.weapon || "clerk_wand";
    P.weapon_inventory = P.weapon_inventory || [P.weapon];
    P.gold = P.gold || 0;
    P.story_flags = P.story_flags || [];
    P.journal = P.journal || [];
    P.recent_story_events = P.recent_story_events || [];
    P.evolved = P.evolved || false;
    P.four_rune_unlocked = P.four_rune_unlocked || false;
    P.items = P.items || {};      // counted bag: { item_id: qty }
    P.quests = P.quests || {};    // { quest_id: "active" | "done" }
    P.beats_seen = P.beats_seen || [];  // story beats already fired
  }
  function hasFlag(f) { return (P.story_flags || []).includes(f); }
  function rememberStoryEvent(kind, text) {
    if (!P || !text) return;
    P.recent_story_events = P.recent_story_events || [];
    const event = { kind, text: String(text).slice(0, 180) };
    P.recent_story_events = P.recent_story_events
      .filter((e) => !(e.kind === event.kind && e.text === event.text))
      .concat([event]).slice(-3);
  }
  function addFlag(f) {
    if (f && !hasFlag(f)) {
      P.story_flags.push(f);
      rememberStoryEvent("flag", f);
    }
  }
  function addInventory(item) { if (item && !P.inventory.includes(item)) P.inventory.push(item); }
  // ---- counted item bag (potions / trophies / materials) ----
  function itemCount(id) { return (P.items && P.items[id]) || 0; }
  function itemLabel(id) { return (ITEMS[id] && ITEMS[id].label) || id.replace(/_/g, " "); }
  function addItem(id, qty) {
    if (!id) return;
    P.items = P.items || {};
    P.items[id] = Math.max(0, (P.items[id] || 0) + (qty == null ? 1 : qty));
    if (P.items[id] <= 0) delete P.items[id];
  }
  function removeItem(id, qty) { addItem(id, -(qty == null ? 1 : qty)); }
  function useItem(id) {
    const meta = ITEMS[id];
    if (!meta || meta.kind !== "potion" || itemCount(id) <= 0) return;
    // Don't waste a potion that would do nothing (already topped up).
    const wouldHelp = (meta.heal && P.hp < P.max_hp) || (meta.courage && P.courage < P.max_courage);
    if (!wouldHelp) { toast("Already full — save the <b>" + meta.label + "</b> for later."); return; }
    let msg = "";
    if (meta.heal) { const before = P.hp; P.hp = clamp(P.hp + meta.heal, 0, P.max_hp); msg = "+" + (P.hp - before) + " HP"; }
    if (meta.courage) { const before = P.courage; P.courage = clamp(P.courage + meta.courage, 0, P.max_courage); msg += (msg ? ", " : "") + "+" + (P.courage - before) + " courage"; }
    removeItem(id, 1);
    toast("🧪 Used <b>" + meta.label + "</b> (" + (msg || "no effect") + ").");
    refreshPanels();
  }
  function weaponLabel(id) { return (WEAPONS[id] && WEAPONS[id].label) || id; }
  function addUnique(arr, text) { if (text && !arr.includes(text)) arr.push(text); }
  function questText() {
    const inv = new Set(P.inventory || []);
    const boss = (areas.arena || { entities: [] }).entities.find((e) => e.id === "calendar_beast");
    if (boss && boss.state === "defeated") return "The Calendar is decided";
    if (P.area === "arena") return "Defeat or repair the Calendar Beast";
    if (!inv.has("Calendar Shard")) return "Find the Calendar Shard in the Mirror Fungus Caverns";
    if (!inv.has("Calendar Key")) return "Find the Calendar Key in the Wet Library";
    const gate = (areas.library || { entities: [] }).entities.find((e) => e.id === "portal_arena");
    if (gate && gate.state === "locked") return "Open the Calendar Gate with the Calendar Key";
    return "Cross the Gate Approach to the Calendar Beast";
  }
  // Main-quest milestones as compact icons for the HUD (instead of a long line).
  function objectiveSteps() {
    const inv = new Set(P.inventory || []);
    const boss = (areas.arena || { entities: [] }).entities.find((e) => e.id === "calendar_beast");
    const gate = (areas.library || { entities: [] }).entities.find((e) => e.id === "portal_arena");
    const steps = [
      { icon: "💠", label: "SHARD", done: inv.has("Calendar Shard") },
      { icon: "🔑", label: "KEY", done: inv.has("Calendar Key") },
      { icon: "🚪", label: "GATE", done: !!(gate && gate.state !== "locked") },
      { icon: "👹", label: "BEAST", done: !!(boss && boss.state === "defeated") },
    ];
    const cur = steps.findIndex((s) => !s.done);
    steps.forEach((s, i) => { s.current = i === cur; });
    return steps;
  }
  function maxRunes() { return P.four_rune_unlocked ? 4 : 3; }

  // ---- layout ----
  let shakeAmt = 0;
  function layout() {
    COLS = A.width; ROWS = A.height;
    const viewH = canvas.height - HUD_TOP;
    // aim for ~11 tiles tall; clamp tile size so big maps scroll via the camera
    TILE = clamp(Math.floor(viewH / 11), 34, 88);
  }
  function camera() {
    const worldW = COLS * TILE, worldH = ROWS * TILE;
    const viewW = canvas.width, viewH = canvas.height - HUD_TOP;
    const pcx = P.x * TILE + TILE / 2, pcy = P.y * TILE + TILE / 2;
    let camX = pcx - viewW / 2, camY = pcy - viewH / 2;
    camX = (worldW <= viewW) ? -(viewW - worldW) / 2 : clamp(camX, 0, worldW - viewW);
    camY = (worldH <= viewH) ? -(viewH - worldH) / 2 : clamp(camY, 0, worldH - viewH);
    let jx = 0, jy = 0;
    if (shakeAmt > 0.01) { jx = (Math.random() * 2 - 1) * shakeAmt * TILE * 0.3; jy = (Math.random() * 2 - 1) * shakeAmt * TILE * 0.3; }
    OX = Math.round(-camX + jx);
    OY = Math.round(HUD_TOP - camY + jy);
    shakeAmt *= 0.88;
  }
  const sx = (tx) => OX + tx * TILE;
  const sy = (ty) => OY + ty * TILE;

  // ---- entity lookups ----
  function liveEntities() { return A.entities.filter((e) => e.state !== "defeated" && e.state !== "collected" && e.state !== "hidden"); }
  // Show/hide flag-gated entities (consequence enemies, returning allies).
  function applyConditionalSpawns(areaId) {
    const ar = areas[areaId]; if (!ar) return;
    const set = (id, show, flagWhenShown) => {
      const e = ar.entities.find((x) => x.id === id);
      if (!e || e.state === "defeated") return;
      e.state = show ? "idle" : "hidden";
      if (e.type === "npc") e.blocking = !!show;
      if (show && flagWhenShown) addFlag(flagWhenShown);
    };
    if (areaId === "gate_approach") {
      const debtUnpaid = (hasFlag("debt_accepted") || hasFlag("debt_deepened")) && !hasFlag("debt_repaid");
      set("debt_collector", debtUnpaid, "debt_collector_spawned");
      set("gate_tourist", hasFlag("tourist_helped"), "boss_ally_tourist");
      set("gate_librarian", hasFlag("librarian_trust"), "boss_ally_librarian");
      set("gate_water_spirit", hasFlag("clean_water_restored") || hasFlag("water_spirit_helped"), "boss_ally_water");
      set("gate_queue_goblin", hasFlag("queue_goblin_paid"), null);
    } else if (areaId === "bone_market") {
      const mastery = P.rune_mastery || {};
      const coinBellMastery = (mastery.coin || 0) >= 5 || (mastery.bell || 0) >= 5;
      const secretReady = hasFlag("secret_merchant_met") || hasFlag("tollmaster_route_open") ||
        coinBellMastery || ["coin_sling", "bell_staff"].includes(P.weapon);
      set("secret_merchant", secretReady, null);
    }
  }
  function entityAt(x, y) { return liveEntities().find((e) => e.x === x && e.y === y); }
  function byId(id) { return A.entities.find((e) => e.id === id); }
  function facedTile() { const v = DIRV[facing]; return [P.x + v[0], P.y + v[1]]; }
  function facedTarget() {
    const [fx, fy] = facedTile();
    const e = entityAt(fx, fy);
    return e && e.blocking && e.type !== "deco" ? e : null;
  }

  function distToPlayer(e) { return Math.abs(e.x - P.x) + Math.abs(e.y - P.y); }
  function canEnemyStep(e, x, y) {
    if (x < 0 || y < 0 || y >= A.rows.length || x >= A.rows[0].length) return false;
    if (!WALK.has(A.rows[y][x]) || (x === P.x && y === P.y)) return false;
    return !liveEntities().some((o) => o !== e && o.blocking && o.x === x && o.y === y);
  }
  function enemyAttack(e, verb) {
    if (now() - (enemyCooldown[e.id] || 0) < 850) return;
    enemyCooldown[e.id] = now();
    const dmg = e.type === "boss" ? 3 : 1;
    P.hp = clamp(P.hp - dmg, 0, P.max_hp);
    spawnHit();
    toast("<b>" + e.name + "</b> " + verb + " for " + dmg + ". Cast a weak rune.");
    if (P.hp <= 0 && !over) lose();
  }
  function enemyTurn() {
    if (!A || over || busy) return;
    turnNo += 1;
    for (const e of liveEntities()) {
      if (!(e.type === "enemy" || e.type === "boss") || e.hp <= 0) continue;
      const d0 = distToPlayer(e);
      if (d0 <= 1) { enemyAttack(e, "presses in"); continue; }
      if (e.type === "boss" || d0 > 6 || (d0 > 3 && (turnNo + e.id.length) % 3 !== 0)) continue;
      const step = ["up", "down", "left", "right"].map((dir) => {
        const v = DIRV[dir], nx = e.x + v[0], ny = e.y + v[1];
        return { nx, ny, d: Math.abs(nx - P.x) + Math.abs(ny - P.y) };
      }).sort((a, b) => a.d - b.d).find((p) => canEnemyStep(e, p.nx, p.ny));
      if (step) { e.x = step.nx; e.y = step.ny; }
      if (distToPlayer(e) <= 1) enemyAttack(e, "lunges");
    }
  }

  // ---- movement ----
  function tryMove(dir) {
    if (busy || over || drawing) return;
    facing = dir;
    const v = DIRV[dir];
    const nx = P.x + v[0], ny = P.y + v[1];
    if (nx < 0 || ny < 0 || ny >= A.rows.length || nx >= A.rows[0].length) { updateTarget(); return; }
    if (!WALK.has(A.rows[ny][nx])) { updateTarget(); return; }
    const e = entityAt(nx, ny);
    if (e && e.blocking) {
      if (e.type === "deco") { updateTarget(); return; } // scenery just blocks
      if (e.type === "npc") {
        if (SHOP_NPCS.has(e.id)) shopTalk(e); else openDialogue(e, []);
        updateTarget(); return;
      }
      toast("<b>" + e.name + "</b> — " + (e.hint || (e.dialogue || "")));
      updateTarget(); return;
    }
    P.x = nx; P.y = ny;
    if (e && !e.blocking) {
      if (e.type === "portal" && e.state !== "locked") travel(e);
      else if (e.type === "powerup") collect(e);
      else if (e.type === "hazard") triggerHazard(e);
    }
    enemyTurn();
    updateTarget();
    checkProximityBeats();
  }

  function travel(portal) {
    P.area = portal.target_area;
    A = areas[P.area];
    applyConditionalSpawns(P.area);
    layout();
    P.x = portal.target_x; P.y = portal.target_y;
    enemyCooldown = {};
    regionCue();
    if (P.area === "gate_approach") addFlag("arena_approach_reached");
    toast("You enter <b>" + A.name + "</b>. " + moodLine());
    checkAreaBeats();
    checkProximityBeats();
  }

  // ---- admin mode (client toggle: Shift+L+A) ----
  function applyAdminUnlock() {
    adminLockSnapshot = [];
    Object.values(areas).forEach((ar) => {
      (ar.entities || []).forEach((e) => {
        const gated = e.state === "locked" || (e.requires && e.requires.length);
        if (!gated) return;
        if (e.type === "portal" || e.type === "locked_door") {
          adminLockSnapshot.push({ e, state: e.state, blocking: e.blocking, requires: (e.requires || []).slice() });
          e.state = "open"; e.blocking = false; e.requires = [];
        } else if (e.type === "chest") {
          adminLockSnapshot.push({ e, state: e.state, blocking: e.blocking, requires: (e.requires || []).slice() });
          e.requires = [];
        }
      });
    });
    if (P) ADMIN_ITEMS.forEach((it) => addInventory(it));
  }
  function restoreAdminLocks() {
    if (!adminLockSnapshot) return;
    adminLockSnapshot.forEach((s) => { s.e.state = s.state; s.e.blocking = s.blocking; s.e.requires = s.requires; });
    adminLockSnapshot = null;
  }
  function buildAdminGoto() {
    const sel = $("rg-admin-goto"); if (!sel) return;
    const ids = areas ? Object.keys(areas) : [];
    sel.innerHTML = "<option value=''>⇪ Warp to map…</option>" +
      ids.map((id) => "<option value='" + id + "'>" + (areas[id].name || id) + "</option>").join("");
    sel.value = "";
  }
  function showAdminGoto(on) { const sel = $("rg-admin-goto"); if (sel) sel.style.display = on ? "" : "none"; }
  function warpToArea(id) {
    if (!P || !areas[id]) return;
    P.area = id; A = areas[id];
    applyConditionalSpawns(id);
    layout();
    const sp = A.spawn; P.x = sp[0]; P.y = sp[1];
    facing = "down"; selected = []; renderPalette();
    enemyCooldown = {}; updateTarget(); regionCue();
    toast("🔓 Warped to <b>" + A.name + "</b>. " + moodLine());
    checkAreaBeats();
    checkProximityBeats();
  }
  function setAdmin(on) {
    if (on === adminMode) return;
    adminMode = on;
    if (W) W.admin = on;            // drives the HUD badge
    if (on) { applyAdminUnlock(); buildAdminGoto(); }
    else { restoreAdminLocks(); }
    showAdminGoto(on);
    toast(on ? "🔓 <b>ADMIN MODE ON</b> — every map unlocked. Use the green dropdown to warp."
             : "Admin mode off — locks restored.");
  }

  function collect(e) {
    e.state = "collected";
    (e.loot || []).forEach((it) => addInventory(it));
    P.score += 25;
    addUnique(P.discoveries, "Found " + (e.loot.join(", ") || e.name) + ".");
    toast("Picked up <b>" + (e.loot.join(", ") || e.name) + "</b>.");
  }

  function triggerHazard(e) {
    if (now() - (enemyCooldown[e.id] || 0) < 900) return;
    enemyCooldown[e.id] = now();
    P.hp = clamp(P.hp - 1, 0, P.max_hp);
    spawnHit();
    toast("<b>" + e.name + "</b> bites one HP off your schedule.");
    if (P.hp <= 0 && !over) lose();
  }

  function moodLine() { return "<i>" + A.mood + "</i>"; }

  function updateTarget() {
    const t = facedTarget();
    const el = $("rg-target");
    if (!el) return;
    if (t) {
      let extra = "";
      if (t.type === "enemy" || t.type === "boss") {
        extra = " · " + t.hp + "/" + t.max_hp + " HP · weak " + (t.weakness || []).join("/");
        const fxi = Object.keys(t.fx || {}).map((k) => FX_ICON[k]).filter(Boolean).join("");
        if (fxi) extra += " " + fxi;
      }
      else if (t.requires && t.requires.length && t.state === "locked") extra = " · needs " + t.requires.join("+");
      else if (t.requires && t.requires.length) extra = " · reads with " + t.requires.join("+");
      el.innerHTML = "🎯 " + t.name + extra;
    } else {
      el.innerHTML = "🎯 (nothing — cast into the air)";
    }
  }

  // ---- casting ----
  function playerCtx() {
    return { hp: P.hp, max_hp: P.max_hp, courage: P.courage, max_courage: P.max_courage,
             inventory: P.inventory.slice(), statuses: P.statuses.slice(),
             level: P.level, xp: P.xp, goblin_class: P.goblin_class, weapon: P.weapon,
             weapon_inventory: (P.weapon_inventory || []).slice(),
             story_flags: (P.story_flags || []).slice(), rune_mastery: P.rune_mastery || {},
             gold: P.gold, recent_runes: recentRunes.slice(), evolved: P.evolved,
             items: Object.assign({}, P.items || {}), quests: Object.assign({}, P.quests || {}) };
  }
  function targetCtx(t) {
    if (!t) return null;
    return { id: t.id, type: t.type, name: t.name, hp: t.hp, max_hp: t.max_hp,
             weakness: t.weakness, resistance: t.resistance, state: t.state,
             requires: t.requires, tags: t.tags, mood: t.mood, loot: t.loot,
             dialogue: t.dialogue };
  }

  function metadataLine(meta) {
    const c = meta && meta.combat;
    if (!c || !c.total_bonus) return "";
    const bits = [];
    if (c.weapon && c.weapon.bonus_damage) bits.push(c.weapon.label + " +" + c.weapon.bonus_damage);
    if (c.goblin_class && c.goblin_class.bonus_damage) bits.push(c.goblin_class.label + " +" + c.goblin_class.bonus_damage);
    if (c.rune_mastery && c.rune_mastery.bonus_damage) bits.push("mastery +" + c.rune_mastery.bonus_damage);
    if (c.boss && c.boss.pylon_bonus) bits.push("pylon +" + c.boss.pylon_bonus);
    if (c.boss && c.boss.king_bonus) bits.push("king +" + c.boss.king_bonus);
    return bits.length ? " <span style='color:#ffd24a'>[" + bits.join(" · ") + "]</span>" : "";
  }

  async function castRunes() {
    if (busy || over || drawing) return;
    if (!selected.length) { toast("Pick at least one rune (click or press 1–9)."); return; }
    const target = facedTarget();
    busy = true; toast("Casting…");
    try {
      const res = await api("/rg/cast", {
        mode: "runes", runes: selected, player: playerCtx(),
        target: targetCtx(target), area_name: A.name,
      });
      applyCast(res, target);
    } catch (e) { toast("Cast failed: " + e); }
    selected = []; renderPalette(); busy = false;
  }

  async function castDrawing() {
    if (busy) return;
    const target = facedTarget();
    const image = sketch.toDataURL("image/png");
    busy = true; toast("🔮 The goblin squints at your drawing…");
    closeDraw();
    showReadingPending();
    try {
      const res = await api("/rg/cast", {
        mode: "drawing", image: image, player: playerCtx(),
        target: targetCtx(target), area_name: A.name,
      });
      let extra = "";
      if (res.visual_reading) {
        const d = (res.visual_reading.detected_runes || []).join(", ") || "unreadable";
        extra = " <span style='color:#6df5a0'>(read: " + d + ")</span>";
      }
      showReading(res);
      applyCast(res, target, extra);
    } catch (e) { hideReading(); toast("Drawing cast failed: " + e); }
    busy = false;
  }

  function applyCast(res, target, extra) {
    const s = res.spell || {};
    const runes = res.runes || selected;
    lastCastMetadata = res.metadata || null;
    // player HP change from the spell itself
    if (s.player_hp_delta) P.hp = clamp(P.hp + s.player_hp_delta, 0, P.max_hp);

    let defeated = false;
    (res.world_actions || []).forEach((a) => {
      const e = a.target_id ? byId(a.target_id) : null;
      switch (a.type) {
        case "set_entity_hp": if (e) e.hp = a.hp; break;
        case "defeat_entity": if (e) { e.state = "defeated"; e.blocking = false;
          P.score += (e.type === "boss" ? 200 : 50); defeated = true;
          toast("<b>" + e.name + "</b> is defeated!"); } break;
        case "set_entity_state": if (e) e.state = a.state; break;
        case "set_entity_blocking": if (e) e.blocking = a.blocking; break;
        case "add_inventory": addInventory(a.item); break;
        case "remove_inventory": { const i = P.inventory.indexOf(a.item); if (i >= 0) P.inventory.splice(i, 1); } break;
        case "add_item":
          addItem(a.item, a.qty == null ? 1 : a.qty);
          if (a.qty !== 0 && (a.qty == null || a.qty > 0)) toast("🎒 +" + (a.qty || 1) + " <b>" + itemLabel(a.item) + "</b>.");
          break;
        case "remove_item": removeItem(a.item, a.qty == null ? 1 : a.qty); break;
        case "set_quest":
          P.quests = P.quests || {};
          P.quests[a.quest] = a.state || "active";
          if (a.log) addUnique(P.quest_log, a.log);
          break;
        case "add_gold": P.gold = Math.max(0, (P.gold || 0) + (a.amount || 0)); break;
        case "add_xp": applyProgressGain(a.amount || 0); break;
        case "heal_player": P.hp = clamp(P.hp + a.amount, 0, P.max_hp); break;
        case "add_courage": P.courage = clamp(P.courage + a.amount, 0, P.max_courage); break;
        case "change_npc_trust":
          if (a.target_id) {
            P.trust[a.target_id] = clamp((P.trust[a.target_id] || 0) + (a.delta || 0), -3, 5);
            if (e) e.state = P.trust[a.target_id] > 0 ? "friendly" : (P.trust[a.target_id] < 0 ? "wary" : e.state);
          }
          break;
        case "add_discovery":
          addUnique(P.discoveries, a.text);
          rememberStoryEvent("discovery", a.text);
          break;
        case "add_quest": addUnique(P.quest_log, a.text); break;
        case "add_journal_entry":
          addUnique(P.journal, a.text); addUnique(P.discoveries, a.text);
          rememberStoryEvent("journal", a.text);
          break;
        case "set_story_flag":
          addFlag(a.flag);
          if (a.flag && (a.flag.startsWith("calendar_") || a.flag === "tollmaster_ending")) {
            P.ending_flags = P.ending_flags || [];
            addUnique(P.ending_flags, a.flag);
          }
          break;
        case "bump_mastery":
          (a.runes || []).forEach((r) => {
            const before = P.rune_mastery[r] || 0;
            P.rune_mastery[r] = before + 1;
            if (P.rune_mastery[r] === 5) toast("✦ You have <b>mastered</b> the " + r.replace(/_/g, " ") + " rune (+1 damage, steadier casts).");
          });
          break;
        case "set_progress":
          if (a.level > P.level) { /* level shown by level_up */ }
          P.level = a.level; P.xp = a.xp; P.xp_to_next = a.xp_to_next;
          break;
        case "level_up":
          if (a.max_hp) { P.max_hp += a.max_hp; P.hp = clamp(P.hp + a.max_hp, 0, P.max_hp); }
          if (a.max_courage) { P.max_courage += a.max_courage; P.courage = clamp(P.courage + a.max_courage, 0, P.max_courage); }
          if (a.unlock_four_runes) P.four_rune_unlocked = true;
          if (a.rune_mastery_choice) grantMasteryChoice();
          showBanner("⬆ LEVEL " + a.level + "<br><span style='font-size:11px'>" + (a.note || "") + "</span>");
          break;
        case "add_weapon":
          if (!P.weapon_inventory.includes(a.weapon)) P.weapon_inventory.push(a.weapon);
          P.weapon = a.weapon;  // auto-equip newest
          if (WEAPONS[a.weapon] && WEAPONS[a.weapon].story_flag) addFlag(WEAPONS[a.weapon].story_flag);
          toast("🗡️ You acquire the <b>" + weaponLabel(a.weapon) + "</b>. " + ((WEAPONS[a.weapon] || {}).identity || ""));
          break;
        case "equip_weapon": if (P.weapon_inventory.includes(a.weapon)) P.weapon = a.weapon; break;
        case "upgrade_weapon":
          if (a.weapon && !P.weapon_inventory.includes(a.weapon)) P.weapon_inventory.push(a.weapon);
          if (a.weapon) P.weapon = a.weapon;
          if (a.message) { addUnique(P.journal, a.message); rememberStoryEvent("journal", a.message); }
          break;
        case "spawn_entity":
          if (a.entity && !byId(a.entity.id)) A.entities.push(a.entity);
          break;
        case "unlock_shortcut":
          if (a.target_id && e) { e.state = "open"; e.blocking = false; }
          if (a.message) { addUnique(P.discoveries, a.message); rememberStoryEvent("shortcut", a.message); }
          break;
        case "reveal_weakness":
          if (e) {
            if (a.weakness) e.weakness = a.weakness;
            if (a.resistance) e.resistance = a.resistance;
            toast("🎯 <b>Weak point marked</b> — weak: " + (a.weakness || []).join("/") +
              ((a.resistance || []).length ? " · resists: " + a.resistance.join("/") : ""));
          }
          break;
        case "start_boss_phase":
          if (e) {
            if (a.weakness) e.weakness = a.weakness;
            if (a.resistance) e.resistance = a.resistance;
          }
          showBanner(a.banner || ("PHASE " + a.phase));
          setTimeout(() => {
            const reactions = (a.boss_reactions || []).map((line) => "<br><span style='color:#ffce6b'>" + line + "</span>").join("");
            toast("<b>Calendar Beast</b>: " + (a.line || "") + reactions);
          }, 700);
          if (a.phase >= 3) setTimeout(() => { if (!over && canEvolveNow()) maybeEvolve(); }, 1400);
          break;
        case "win_game": lastEnding = { ending: a.ending, title: a.title, text: a.text,
          choices: a.choices || [], boss_reactions: a.boss_reactions || [] }; win(); break;
        default: break;
      }
    });
    if (runes && runes.length) recentRunes = runes.slice();
    P.score += Math.max(0, -(s.enemy_hp_delta || 0)) * 10 + (s.chaos || 0);

    // a cast is a "turn": old statuses tick first, then this cast's land
    tickStatuses();
    applyStatusEffects(s, target);

    spawnSpellVfx(s, target, runes, res.mode === "drawing");

    if (!over) {
      let line = "<b>" + (s.spell_name || "Spell") + "</b> — " + (s.effect || "");
      if (s.side_effect) line += " <span style='color:#ffce6b'>⚠ " + s.side_effect + "</span>";
      line += metadataLine(lastCastMetadata);
      if (extra) line += extra;
      if (target) {
        const weak = runes.some((r) => (target.weakness || []).includes(r));
        const resist = runes.some((r) => (target.resistance || []).includes(r));
        if (weak) line += " <span style='color:#6df5a0'>weakness hit</span>";
        if (resist) line += " <span style='color:#ffce6b'>resisted</span>";
      }
      toast(line);
    }

    // enemy retaliation if it survived
    if (!over && target && (target.type === "enemy" || target.type === "boss") && !defeated) {
      retaliate(target, s.status_effects || []);
    }
    // casting at a friendly NPC also surfaces a model-driven reply
    if (!over && target && target.type === "npc") openDialogue(target, runes);
    updateTarget();
    if (P.hp <= 0 && !over) lose();
  }

  function applyProgressGain(amount) {
    if (!amount) return;
    P.xp += amount;
    while (P.xp_to_next > 0 && P.xp >= P.xp_to_next) {
      P.xp -= P.xp_to_next;
      P.level += 1;
      if (P.level === 2) { P.max_hp += 2; P.hp = clamp(P.hp + 2, 0, P.max_hp); }
      if (P.level === 3) P.four_rune_unlocked = true;
      if (P.level === 4) grantMasteryChoice();
      if (P.level >= 5) { P.max_courage += 2; P.courage = P.max_courage; P.xp_to_next = 0; break; }
      P.xp_to_next = P.level === 2 ? 16 : (P.level === 3 ? 28 : (P.level === 4 ? 44 : 0));
    }
  }

  function grantMasteryChoice() {
    const cls = CLASSES.find((c) => c.id === P.goblin_class) || {};
    const counts = Object.entries(P.rune_mastery || {}).sort((a, b) => b[1] - a[1]).map((x) => x[0]);
    const pool = counts.concat(selected || [], cls.affinity || [], ["closed_circle", "eye", "wave", "key", "spiral"]);
    const choices = [];
    pool.forEach((r) => { if (r && !choices.includes(r)) choices.push(r); });
    openMasteryChoice(choices.slice(0, 3));
  }

  function runeLabel(key) {
    const r = (runesMeta || []).find((x) => x.key === key);
    return (r && r.label) || key.replace(/_/g, " ");
  }

  function chooseMasteryRune(key) {
    if (!key) return;
    masteryChoiceOpen = false;
    P.rune_mastery[key] = Math.max(5, P.rune_mastery[key] || 0);
    const line = "Level 4 mastery: " + runeLabel(key) + " is now steady enough to hit harder.";
    addUnique(P.journal, line);
    addUnique(P.discoveries, line);
    rememberStoryEvent("journal", line);
    closeDialogue();
    showBanner("✦ RUNE MASTERY<br><span style='font-size:11px'>" + runeLabel(key) + "</span>");
    toast("✦ You chose <b>" + runeLabel(key) + "</b> mastery.");
  }

  function openMasteryChoice(choices) {
    choices = (choices && choices.length ? choices : ["closed_circle", "eye", "wave"]).slice(0, 3);
    masteryChoiceOpen = true;
    showDialogue({ id: "mastery_choice", name: "Rune Mastery" },
      "<div class='rg-mastery-title'>Choose one rune to steady permanently.</div>" +
      "<div class='rg-mastery-choices'>" + choices.map((r) =>
        "<button class='rg-mastery-choice' data-rune='" + r + "'>" +
        "<img src='" + ICON(r) + "' alt=''> <span>" + runeLabel(r) + "</span></button>").join("") +
      "</div>", false);
    document.querySelectorAll(".rg-mastery-choice").forEach((b) => {
      b.onclick = (ev) => { ev.stopPropagation(); chooseMasteryRune(b.dataset.rune); canvas.focus(); };
    });
  }

  // ---- persistent status effects (client-owned ticking; 1 cast = 1 turn) ----
  // Server statuses (from rune GLYPHS) map to durable effects with durations.
  const STATUS_FX = {
    enemy_burning: { key: "burn", turns: 2 },   // 1 dmg per turn
    enemy_swarmed: { key: "burn", turns: 1 },
    enemy_confused: { key: "stun", turns: 1 },  // skips retaliation
    enemy_bound: { key: "stun", turns: 1 },
    enemy_soothed: { key: "calm", turns: 1 },   // skips retaliation
    enemy_feared: { key: "fear", turns: 2 },    // weaker retaliation
    player_shielded: { key: "shield", turns: 2 },  // absorbs one hit
    player_blessed: { key: "regen", turns: 2 },    // +1 HP per turn
  };
  const FX_ICON = { burn: "🔥", stun: "💫", calm: "🌊", fear: "😨", shield: "🛡", regen: "✨" };

  function applyStatusEffects(s, target) {
    (s.status_effects || []).forEach((st) => {
      const m = STATUS_FX[st];
      if (!m) return;
      if (st.startsWith("enemy_") && target && (target.type === "enemy" || target.type === "boss") && target.hp > 0) {
        target.fx = target.fx || {};
        target.fx[m.key] = Math.max(target.fx[m.key] || 0, m.turns);
      } else if (st.startsWith("player_")) {
        P.fx = P.fx || {};
        P.fx[m.key] = Math.max(P.fx[m.key] || 0, m.turns);
      }
    });
  }

  function tickStatuses() {
    for (const e of liveEntities()) {
      if (!e.fx) continue;
      if ((e.type === "enemy" || e.type === "boss") && e.fx.burn > 0 && e.hp > 0) {
        // the boss's killing blow is server-owned (and must be hand-drawn)
        e.hp = Math.max(e.type === "boss" ? 1 : 0, e.hp - 1);
        addNum("-1", "#ff9d4a", e.x + 0.5, e.y - 0.2, 0);
        if (e.hp <= 0) {
          e.state = "defeated"; e.blocking = false; P.score += 50;
          toast("🔥 <b>" + e.name + "</b> succumbs to its wounds!");
        }
      }
      for (const k of Object.keys(e.fx)) { e.fx[k] -= 1; if (e.fx[k] <= 0) delete e.fx[k]; }
    }
    if (P.fx) {
      if (P.fx.regen > 0 && P.hp < P.max_hp) {
        P.hp = clamp(P.hp + 1, 0, P.max_hp);
        addNum("+1", "#6df5a0", P.x + 0.5, P.y - 0.2, 0);
      }
      for (const k of Object.keys(P.fx)) { P.fx[k] -= 1; if (P.fx[k] <= 0) delete P.fx[k]; }
    }
  }

  function retaliate(enemy, statuses) {
    const fx = enemy.fx || {};
    const skip = ["enemy_confused", "enemy_soothed", "enemy_bound"].some((x) => statuses.includes(x)) ||
      fx.stun > 0 || fx.calm > 0;
    if (skip) { setTimeout(() => toast(enemy.name + " fumbles its turn."), 650); return; }
    let dmg = enemy.type === "boss" ? 3 : (P.area === "arena" ? 2 : 1);
    if (fx.fear > 0) dmg = Math.max(1, dmg - 1);
    if (statuses.includes("player_shielded") || (P.fx && P.fx.shield > 0)) {
      if (P.fx && P.fx.shield > 0) { P.fx.shield -= 1; if (P.fx.shield <= 0) delete P.fx.shield; }
      setTimeout(() => toast("Your shield absorbs " + enemy.name + "'s blow."), 650); return;
    }
    setTimeout(() => {
      P.hp = clamp(P.hp - dmg, 0, P.max_hp);
      spawnHit();
      toast(enemy.name + " strikes back for " + dmg + (fx.fear > 0 ? " (cowed by fear)" : "") + "!");
      if (P.hp <= 0 && !over) lose();
    }, 650);
  }

  // ---- NPC dialogue (model-driven via /rg/dialogue, + deterministic fallback) ----
  function dialoguePortrait(npc) {
    const map = { tourist: "🧳", gate_tourist: "🧳", librarian: "📚", gate_librarian: "📚", lost_wisp: "✨",
      sewer_wisp: "✨", water_spirit: "💧", gate_water_spirit: "💧", market_merchant: "💀", cave_hermit: "🍄",
      watch_archer: "🏹", gate_archer: "🏹", road_druid: "🌿", toll_pixie: "🧚",
      red_guard: "🛡️", debt_collector: "📜", toll_goblin: "👺", gate_queue_goblin: "👺",
      mastery_choice: "✦" };
    return map[npc.id] || "🗣️";
  }
  function showDialogue(npc, text, thinking) {
    dialogueOpen = true;
    const box = $("rg-dialogue");
    box.className = "rg-dialogue open" + (thinking ? " thinking" : "");
    $("rg-dialogue-portrait").textContent = dialoguePortrait(npc);
    $("rg-dialogue-name").textContent = npc.name;
    $("rg-dialogue-text").innerHTML = text;
  }
  function closeDialogue() {
    if (masteryChoiceOpen) return;
    dialogueOpen = false; $("rg-dialogue").className = "rg-dialogue";
  }

  function applyDialoguePayload(npc, d) {
    if (!d) return;
    if (d.journal_entry) {
      addUnique(P.journal, d.journal_entry); addUnique(P.discoveries, d.journal_entry);
      rememberStoryEvent("journal", d.journal_entry);
    }
    // Dialogue is flavor-only: story flags are owned by the cast engine
    // (/rg/cast world actions), never by the chat model. See dialogue.sanitize.
    let text = d.npc_line || (npc.dialogue || "…");
    if (d.story_toast) text += "<br><span style='color:#9c8bc4'>" + d.story_toast + "</span>";
    // Attribute live model-written lines (yellow); blank for deterministic fallback.
    const src = d.source === "model"
      ? "<br><span style='color:#ffd24a;font-size:10px'>✶ generated by " + (d.model || "the story model") + "</span>"
      : "";
    showDialogue(npc, text + src, false);
  }

  async function openDialogue(npc, runes) {
    if (over || !npc) return;
    showDialogue(npc, "<i>…</i>", true);
    try {
      const d = await api("/rg/dialogue", {
        area: A.name, scene: "talk",
        target: { id: npc.id, name: npc.name, type: npc.type, state: npc.state },
        player: { goblin_class: P.goblin_class, level: P.level, hp: P.hp,
          courage: P.courage, weapon: P.weapon, inventory: P.inventory.slice(),
          story_flags: P.story_flags.slice(), npc_trust: P.trust[npc.id] || 0,
          recent_story_events: (P.recent_story_events || []).slice(-3) },
        action: { mode: runes && runes.length ? "cast" : "talk", runes: runes || [] },
      });
      applyDialoguePayload(npc, d);
    } catch (e) {
      showDialogue(npc, npc.dialogue || npc.hint || "They nod, distracted.", false);
    }
  }
  // Apply the limited action set a quest interaction can return (deterministic).
  function applyQuestActions(actions) {
    let leveled = false;
    (actions || []).forEach((a) => {
      switch (a.type) {
        case "set_quest":
          P.quests = P.quests || {}; P.quests[a.quest] = a.state || "active";
          if (a.log) addUnique(P.quest_log, a.log);
          break;
        case "add_item": addItem(a.item, a.qty == null ? 1 : a.qty); break;
        case "remove_item": removeItem(a.item, a.qty == null ? 1 : a.qty); break;
        case "add_weapon":
          if (!P.weapon_inventory.includes(a.weapon)) P.weapon_inventory.push(a.weapon);
          P.weapon = a.weapon;
          if (WEAPONS[a.weapon] && WEAPONS[a.weapon].story_flag) addFlag(WEAPONS[a.weapon].story_flag);
          break;
        case "upgrade_weapon":
          if (a.message) { addUnique(P.journal, a.message); rememberStoryEvent("journal", a.message); }
          break;
        case "add_inventory": addInventory(a.item); break;
        case "add_gold": P.gold = Math.max(0, (P.gold || 0) + (a.amount || 0)); break;
        case "add_xp": applyProgressGain(a.amount || 0); leveled = true; break;
        case "heal_player": P.hp = clamp(P.hp + (a.amount || 0), 0, P.max_hp); break;
        case "add_courage": P.courage = clamp(P.courage + (a.amount || 0), 0, P.max_courage); break;
        case "set_story_flag": addFlag(a.flag); break;
        case "add_journal_entry":
          addUnique(P.journal, a.text); addUnique(P.discoveries, a.text);
          rememberStoryEvent("journal", a.text);
          break;
        default: break;
      }
    });
    return leveled;
  }

  async function questTalk(npc) {
    if (over || !npc) return;
    showDialogue(npc, "<i>…</i>", true);
    try {
      const d = await api("/rg/quest", { npc_id: npc.id, player: playerCtx() });
      applyQuestActions(d.world_actions);
      // Reward turn-ins get a celebratory tag; offers/progress just show the line.
      let tag = "";
      if (d.quest_state === "turned_in" || d.quest_state === "exchange")
        tag = "<br><span style='color:#6df5a0;font-size:11px'>✓ " + (d.reward ? "received " + d.reward : "complete") + "</span>";
      else if (d.quest_state === "offered")
        tag = "<br><span style='color:#ffd24a;font-size:11px'>✦ quest accepted — check your Journal (J)</span>";
      showDialogue({ id: npc.id, name: npc.name || d.name }, (d.line || npc.dialogue || "…") + tag, false);
    } catch (e) {
      showDialogue(npc, npc.dialogue || npc.hint || "They nod, distracted.", false);
    }
  }

  // ---- Bone Market shop (deterministic, via /rg/shop) ----
  const SHOP_NPCS = new Set(["market_merchant", "secret_merchant"]);
  function shopHtml(d) {
    const rows = (d.offers || []).map((o) => {
      const buyable = !o.owned && (o.affordable || o.cursed);
      let tag = o.owned ? "owned" : (o.cursed ? "free*" : o.price + "g");
      return "<button class='rg-shop-buy" + (buyable ? "" : " off") + "' data-w='" + o.id + "'" +
        " data-p='" + (o.price || 0) + "'" + (buyable ? "" : " disabled") + ">" +
        "<span class='rg-shop-row'><b>" + o.label + "</b>" +
        "<span class='rg-shop-price" + (o.cursed ? " cursed" : "") + "'>" + tag + "</span></span>" +
        "<small>" + (o.pitch || o.identity || "") + "</small>" +
        (o.haggle ? "<small class='rg-shop-haggle'>“" + o.haggle + "”</small>" : "") +
        "</button>";
    }).join("");
    const cursedNote = (d.offers || []).some((o) => o.cursed && !o.owned)
      ? " · <i>free* = paid in curse, not coins</i>" : "";
    // Attribute live model-set prices (matches the dialogue panel's tag).
    const srcTag = d.pricing_source === "model"
      ? "<div class='rg-shop-model'>✶ prices haggled by " + (d.model || "the story model") + "</div>"
      : "";
    return "<div class='rg-shop-line'>" + (d.line || "") + "</div>" +
      "<div class='rg-shop-gold'>Your purse: <b>" + (P.gold || 0) + "g</b>" + cursedNote + "</div>" +
      "<div class='rg-shop'>" + rows + "</div>" + srcTag;
  }
  async function shopTalk(npc, weaponId, quotedPrice) {
    if (over || !npc) return;
    if (!weaponId) showDialogue(npc, "<i>…</i>", true);
    try {
      let d = await api("/rg/shop", { npc_id: npc.id, weapon_id: weaponId || "",
        quoted_price: weaponId ? (quotedPrice || 0) : null, player: playerCtx() });
      if (d.error) { openDialogue(npc, []); return; }
      const bought = (d.world_actions || []).length > 0;
      applyQuestActions(d.world_actions || []);
      if (bought) {
        refreshPanels();
        // re-list with post-purchase gold/ownership, keep the merchant's line
        const fresh = await api("/rg/shop", { npc_id: npc.id, weapon_id: "", player: playerCtx() });
        if (!fresh.error) { fresh.line = d.line; d = fresh; }
      }
      showDialogue(npc, shopHtml(d), false);
      document.querySelectorAll(".rg-shop-buy:not([disabled])").forEach((b) => {
        b.onclick = (ev) => {
          ev.stopPropagation();
          shopTalk(npc, b.dataset.w, parseInt(b.dataset.p || "0", 10));
          canvas.focus();
        };
      });
    } catch (e) { openDialogue(npc, []); }
  }

  function talk() {
    const t = facedTarget();
    if (!t || t.type !== "npc") { toast("Face an NPC, then press T to talk."); return; }
    if (SHOP_NPCS.has(t.id)) shopTalk(t);  // merchants -> shop panel
    else if (t.quest) questTalk(t);    // quest-giver -> deterministic quest flow
    else openDialogue(t, []);          // everyone else -> live story dialogue
  }

  // ---- proactive story beats (LLM-triggered via /rg/story_beat) ----
  // Triggers ship with the world payload; the client fires each beat at most
  // once (P.beats_seen) and the server owns the text (model + fallback).
  function beatEligible(b) {
    if ((P.beats_seen || []).includes(b.id)) return false;
    if ((b.requires || []).some((f) => !hasFlag(f))) return false;
    if ((b.requires_any || []).length && !b.requires_any.some(hasFlag)) return false;
    if ((b.requires_any_2 || []).length && !b.requires_any_2.some(hasFlag)) return false;
    if ((b.forbids || []).some(hasFlag)) return false;
    return true;
  }
  async function fireBeat(b, ent) {
    P.beats_seen.push(b.id);  // mark first so a slow request can't double-fire
    try {
      const d = await api("/rg/story_beat", {
        beat_id: b.id, area: A.name,
        player: { goblin_class: P.goblin_class, level: P.level, hp: P.hp,
          courage: P.courage, weapon: P.weapon,
          story_flags: (P.story_flags || []).slice(),
          recent_story_events: (P.recent_story_events || []).slice(-3) },
      });
      if (!d || d.skip) return;
      if (d.story_toast) { toast(d.story_toast); rememberStoryEvent("story", d.story_toast); }
      if (d.npc_line && ent) showBark(ent, d.npc_line);
      if (d.journal_entry) {
        addUnique(P.journal, d.journal_entry); addUnique(P.discoveries, d.journal_entry);
        rememberStoryEvent("journal", d.journal_entry);
      }
    } catch (e) { console.warn("[story_beat] " + b.id + " failed:", e); }
  }
  function checkAreaBeats() {
    if (!P || !A) return;
    const b = (STORY_BEATS || []).find((x) =>
      x.trigger === "area_enter" && x.area === P.area && beatEligible(x));
    if (b) fireBeat(b, null);
  }
  function checkProximityBeats() {
    if (!P || !A) return;
    for (const b of STORY_BEATS || []) {
      if (b.trigger !== "first_meet" || b.area !== P.area || !beatEligible(b)) continue;
      const e = (A.entities || []).find((x) => x.id === b.npc &&
        x.state !== "defeated" && x.state !== "hidden");
      if (e && distToPlayer(e) <= (b.radius || 3)) fireBeat(b, e);
    }
  }

  // ---- speech-bubble barks over entities ----
  function showBark(ent, text) {
    let clean = String(text).replace(/<[^>]*>/g, "");
    const prefix = (ent.name || "") + ":";
    if (clean.startsWith(prefix)) clean = clean.slice(prefix.length).trim();
    barks = barks.filter((b) => b.eid !== ent.id);
    barks.push({ eid: ent.id, area: P.area, text: clean.slice(0, 160), until: now() + 6200 });
  }
  function wrapBark(text, maxChars) {
    const words = text.split(/\s+/), lines = [];
    let line = "";
    for (const w of words) {
      if ((line + " " + w).trim().length > maxChars && line) { lines.push(line); line = w; }
      else line = (line + " " + w).trim();
      if (lines.length >= 3) break;
    }
    if (line && lines.length < 4) lines.push(line);
    return lines;
  }
  function drawBarks() {
    const t = now();
    barks = barks.filter((b) => b.until > t);
    for (const b of barks) {
      if (b.area !== P.area) continue;
      const e = (A.entities || []).find((x) => x.id === b.eid);
      if (!e || e.state === "defeated") continue;
      const lines = wrapBark(b.text, 28);
      if (!lines.length) continue;
      const fs = Math.max(10, Math.floor(TILE * 0.26));
      ctx.font = fs + "px monospace";
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      const w = Math.max(...lines.map((l) => ctx.measureText(l).width)) + 16;
      const lh = fs + 4, h = lines.length * lh + 10;
      const cx = sx(e.x) + TILE / 2;
      let bx = cx - w / 2, by = sy(e.y) - h - TILE * 0.45;
      bx = clamp(bx, 4, canvas.width - w - 4);
      by = Math.max(HUD_TOP + 4, by);
      const fade = Math.min(1, (b.until - t) / 500);
      ctx.save();
      ctx.globalAlpha = 0.92 * fade;
      ctx.fillStyle = "#13101d"; ctx.strokeStyle = "#b07cff"; ctx.lineWidth = 1.5;
      if (ctx.roundRect) {
        ctx.beginPath(); ctx.roundRect(bx, by, w, h, 7); ctx.fill(); ctx.stroke();
      } else { ctx.fillRect(bx, by, w, h); ctx.strokeRect(bx, by, w, h); }
      // tail
      ctx.beginPath();
      ctx.moveTo(cx - 5, by + h); ctx.lineTo(cx + 5, by + h); ctx.lineTo(cx, by + h + 7);
      ctx.closePath(); ctx.fill();
      ctx.fillStyle = "#e8e2f5";
      lines.forEach((l, i) => ctx.fillText(l, bx + w / 2, by + 8 + lh * i + lh / 2 - 2));
      ctx.restore();
    }
  }

  // Dev/debug peephole (read-only): lets tooling inspect beat + bark state.
  window.__rgDebug = {
    barks: () => barks.slice(),
    beatsSeen: () => (P && P.beats_seen ? P.beats_seen.slice() : []),
    pos: () => (P ? { area: P.area, x: P.x, y: P.y } : null),
  };

  // ---- banner (boss phase / evolution) ----
  let bannerTimer = null;
  function showBanner(text) {
    const el = $("rg-banner"); if (!el) return;
    el.innerHTML = text; el.className = "rg-banner show";
    if (bannerTimer) clearTimeout(bannerTimer);
    bannerTimer = setTimeout(() => { el.className = "rg-banner"; }, 2600);
  }

  // ---- Goblin King evolution ----
  const HELPER_FLAGS = ["tourist_helped", "fungus_colony_spared", "librarian_trust",
    "clean_water_restored", "queue_goblin_paid"];
  const DEVOUR_FLAGS = ["library_shelves_burned", "debt_deepened", "debt_accepted", "fungus_colony_burned"];
  function canEvolveNow() {
    if (P.evolved) return false;
    const identity = HELPER_FLAGS.concat(DEVOUR_FLAGS).some(hasFlag);
    return P.level >= 5 || identity;
  }
  function maybeEvolve() {
    if (P.evolved) return;
    const cls = CLASSES.find((c) => c.id === P.goblin_class) || {};
    addFlag("player_evolved");
    P.evolved = true;
    P.courage = P.max_courage;          // refill courage
    P.four_rune_unlocked = true;
    P.rune_mastery[(cls.affinity || ["closed_circle"])[0]] = Math.max(5, P.rune_mastery[(cls.affinity || ["closed_circle"])[0]] || 0);
    showBanner("👑 GOBLIN KING<br><span style='font-size:11px'>" + (cls.king_line || "") + "</span>");
    toast("<b>You evolve into the Goblin King!</b> " + (cls.king_ability || ""));
  }

  // ---- win / lose ----
  function endScreen(cls, title, sub) {
    over = true;
    const el = $("rg-end");
    el.className = "rg-end open " + cls;
    $("rg-end-title").textContent = title;
    $("rg-end-sub").innerHTML = sub;
  }
  function win() {
    const e = lastEnding || {};
    const title = e.title || "🏆 THE BEAST FALLS";
    const text = e.text || "You broke the Calendar.";
    const choices = (e.choices || []).length
      ? "<br><br><ul class='rg-ending-choices'>" + e.choices.map((line) => "<li>" + line + "</li>").join("") + "</ul>"
      : "";
    const bossLines = (e.boss_reactions || []).length
      ? "<br><br><div class='rg-ending-boss'>" + e.boss_reactions.map((line) => "<p>Calendar Beast: " + line + "</p>").join("") + "</div>"
      : "";
    endScreen("win", title, text + bossLines + choices + "<br><br>Hero: <b>" + ((CLASSES.find((c) => c.id === P.goblin_class) || {}).label || "Goblin")
      + (P.evolved ? " 👑" : "") + "</b> · Level " + P.level + " · Final score: " + P.score);
  }
  function lose() { endScreen("lose", "💀 YOU COLLAPSED", "The dungeon keeps your score: " + P.score); }

  // ---- VFX ----
  function tileCenter(e) { return [sx(e.x) + TILE / 2, sy(e.y) + TILE / 2]; }
  function playerCenter() { return [sx(P.x) + TILE / 2, sy(P.y) + TILE / 2]; }

  // world-anchored helpers (tile-space, resolved to screen at draw time)
  function tcOf(e) { return [e.x + 0.5, e.y + 0.5]; }
  function pcOf() { return [P.x + 0.5, P.y + 0.5]; }
  function addAnim(sheet, tx, ty, scale, delay) {
    if (VFXM[sheet]) vfx.push({ kind: "anim", sheet, tx, ty, scale, start: now() + (delay || 0) });
  }
  function addProj(sheet, from, to, travel, delay) {
    if (VFXM[sheet]) vfx.push({ kind: "proj", sheet, fx: from[0], fy: from[1], txx: to[0], tyy: to[1],
      travel, scale: 1.2, start: now() + (delay || 0) });
  }
  function addNum(text, color, tx, ty, delay) {
    vfx.push({ kind: "num", text, color, tx, ty, dur: 900, start: now() + (delay || 0) });
  }
  function addCircle(row, tx, ty, scale, dur) {
    if (CIRCLES && row >= 0) vfx.push({ kind: "circle", row, tx, ty, scale, dur, start: now() });
  }

  // The drawn magic: complexity (layers, size, shake, secondary bursts) scales
  // with the spell's tier — derived from rune count, chaos, damage and curse.
  // Hand-drawn casts (flashy) get a full tier bump plus their own fanfare.
  function spawnSpellVfx(s, target, runes, flashy) {
    runes = runes || [];
    const el = elementOf(runes), cfg = ELEM_VFX[el] || ELEM_VFX.light;
    const t = spellTier(s, runes) + (flashy ? 1 : 0);
    const dmg = -(s.enemy_hp_delta || 0), heal = Math.max(0, s.player_hp_delta || 0);
    const pc = pcOf(), tc = target ? tcOf(target) : pc;
    const travel = target ? 300 : 0;
    // magic circle under the caster, chosen by the drawn runes, bigger with tier
    const crow = circleRow(runes);
    addCircle(crow, pc[0], pc[1] + 0.1, 2.0 + 0.5 * t, 650 + 150 * t);
    if (target && t >= 2) addCircle(crow, tc[0], tc[1] + 0.1, 1.5 + 0.4 * t, 600 + 130 * t);
    addAnim(cfg.cast, pc[0], pc[1] - 0.3, 1.1 + 0.18 * t, 0);
    if (target) addProj(cfg.proj, pc, tc, travel, 110);
    addAnim(cfg.impact, tc[0], tc[1] - 0.2, 1.2 + 0.22 * t, 110 + travel);
    if (t >= 2) addAnim("explosion", tc[0], tc[1] - 0.2, 1.0, 150 + travel);
    if (t >= 3) { addAnim("star", tc[0], tc[1] - 0.4, 1.7, 170 + travel); shakeAmt = Math.max(shakeAmt, 0.35); }
    if (t >= 4) {
      addAnim("explosion_big", tc[0], tc[1] - 0.3, 1.6, 210 + travel);
      addAnim("tornado", tc[0], tc[1] - 0.3, 1.5, 90 + travel);
      shakeAmt = Math.max(shakeAmt, 0.7);
    }
    if (flashy) {
      addAnim("star", pc[0], pc[1] - 0.5, 1.4, 60);
      if (target) addAnim("star", tc[0], tc[1] - 0.5, 1.4, 200 + travel);
      addNum("✍ DRAWN", "#ffd24a", pc[0], pc[1] - 1.0, 40);
      shakeAmt = Math.max(shakeAmt, 0.45);
    }
    if (heal > 0) addAnim("holy", pc[0], pc[1] - 0.2, 1.1, 0);
    if ((s.status_effects || []).includes("player_shielded")) addAnim("barrier", pc[0], pc[1] - 0.2, 1.3, 0);
    if (dmg > 0) { addNum("-" + dmg, "#ff5d73", tc[0], tc[1] - 0.6, 110 + travel); shakeAmt = Math.max(shakeAmt, Math.min(0.55, 0.12 + dmg * 0.06)); }
    else if (heal > 0) addNum("+" + heal, "#6df5a0", pc[0], pc[1] - 0.6, 0);
    playSfx(cfg.sound, t);
  }
  function spawnHit() { vfx.push({ kind: "hit", start: now(), dur: 360 }); shakeAmt = Math.max(shakeAmt, 0.35); }

  // ---- rendering ----
  function waterColor() {
    if (A.biome === "cavern") return ["#255968", "#326f7e", "#78c7d8"];
    if (A.biome === "library") return ["#273d63", "#36527d", "#8db3dd"];
    if (A.biome === "arena") return ["#4e275f", "#653579", "#d49cff"];
    if (A.biome === "sewer") return ["#2a4a34", "#3a6347", "#8fd8a0"];   // murk
    if (A.biome === "ice") return ["#5b8fb8", "#7fb3d6", "#e8f6ff"];     // glacial melt
    if (A.biome === "forge") return ["#8a2406", "#c2540e", "#ffd24a"];   // lava
    if (A.biome === "market") return ["#3f7a68", "#5aa389", "#c9f0d8"];  // oasis
    return ["#3f8791", "#60aeb6", "#b4ecec"];
  }
  function drawWater(px, py, x, y) {
    const [deep, mid, glint] = waterColor();
    ctx.fillStyle = deep; ctx.fillRect(px, py, TILE, TILE);
    ctx.fillStyle = mid; ctx.fillRect(px, py, TILE, TILE);
    ctx.fillStyle = "rgba(255,255,255,0.16)";
    const wy = py + TILE * (0.34 + 0.18 * ((x + y) % 3));
    ctx.fillRect(px + TILE * 0.18, wy, TILE * 0.42, 2);
    ctx.fillStyle = glint; ctx.fillRect(px + TILE * 0.62, py + TILE * 0.68, TILE * 0.18, 2);
    ctx.strokeStyle = "rgba(10,22,30,0.5)";
    ctx.lineWidth = 2;
    const waterAt = (xx, yy) => yy >= 0 && yy < A.rows.length && xx >= 0 && xx < A.rows[0].length && A.rows[yy][xx] === "~";
    if (!waterAt(x, y - 1)) { ctx.beginPath(); ctx.moveTo(px, py + 1); ctx.lineTo(px + TILE, py + 1); ctx.stroke(); }
    if (!waterAt(x, y + 1)) { ctx.beginPath(); ctx.moveTo(px, py + TILE - 1); ctx.lineTo(px + TILE, py + TILE - 1); ctx.stroke(); }
    if (!waterAt(x - 1, y)) { ctx.beginPath(); ctx.moveTo(px + 1, py); ctx.lineTo(px + 1, py + TILE); ctx.stroke(); }
    if (!waterAt(x + 1, y)) { ctx.beginPath(); ctx.moveTo(px + TILE - 1, py); ctx.lineTo(px + TILE - 1, py + TILE); ctx.stroke(); }
  }
  function drawSolidTile(ch, px, py, x, y, b) {
    const col = ch === "#" ? b.wall : (ch === " " ? "#070510" : (((x + y) % 2 === 0) ? b.floor : b.alt));
    ctx.fillStyle = col; ctx.fillRect(px, py, TILE, TILE);
    if (ch === "#") { ctx.fillStyle = b.edge; ctx.fillRect(px, py + TILE - 5, TILE, 5); }
  }
  function drawTiles() {
    const b = BIOME[A.biome] || DEFAULT_BIOME;
    const groundName = spr(b.ground) ? b.ground : "grass";
    const haveGround = !!spr(groundName);
    const x0 = clamp(Math.floor((0 - OX) / TILE), 0, COLS - 1);
    const x1 = clamp(Math.ceil((canvas.width - OX) / TILE), 0, COLS - 1);
    const y0 = clamp(Math.floor((HUD_TOP - OY) / TILE), 0, ROWS - 1);
    const y1 = clamp(Math.ceil((canvas.height - OY) / TILE), 0, ROWS - 1);
    for (let y = y0; y <= y1; y++) {
      for (let x = x0; x <= x1; x++) {
        const ch = A.rows[y][x];
        const walk = WALK.has(ch);
        const px = sx(x), py = sy(y);
        if (ch === "~") {
          drawWater(px, py, x, y);
        } else if (haveGround && walk) {
          drawTileSprite(groundName, px, py);
          if (b.tint) { ctx.fillStyle = b.tint; ctx.fillRect(px, py, TILE, TILE); }
          if (walk && ((x * 7 + y * 11 + (now() / 900 | 0)) % 17 === 0)) {
            ctx.fillStyle = "rgba(255,255,255,0.08)";
            ctx.fillRect(px + TILE * 0.18, py + TILE * 0.72, TILE * 0.26, 2);
          }
        } else {
          drawSolidTile(ch, px, py, x, y, b);
        }
      }
    }
  }

  function drawPortal(cx, cy, e) {
    const t = now() / 600, locked = e.state === "locked";
    ctx.save();
    for (let i = 0; i < 3; i++) {
      ctx.globalAlpha = 0.5 - i * 0.13;
      ctx.strokeStyle = locked ? "#ff5d73" : "#b07cff";
      ctx.lineWidth = Math.max(2, TILE * 0.06);
      ctx.beginPath();
      ctx.arc(cx, cy, TILE * (0.2 + i * 0.13) + Math.sin(t + i) * 2, 0, Math.PI * 2);
      ctx.stroke();
    }
    // glowing core (no emoji)
    ctx.globalAlpha = 0.85;
    const grd = ctx.createRadialGradient(cx, cy, 1, cx, cy, TILE * 0.34);
    grd.addColorStop(0, locked ? "#ffd0d8" : "#e8d6ff");
    grd.addColorStop(1, locked ? "rgba(255,93,115,0)" : "rgba(176,124,255,0)");
    ctx.fillStyle = grd;
    ctx.beginPath(); ctx.arc(cx, cy, TILE * 0.34, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  }

  function drawEntity(e) {
    const cx = sx(e.x) + TILE / 2;
    const cy = sy(e.y) + TILE / 2, baseY = sy(e.y) + TILE * 0.98;

    if (e.type === "portal") {
      drawPortal(cx, cy, e);
    } else {
      ctx.save();
      ctx.globalAlpha = 0.26;
      ctx.fillStyle = "#050309";
      ctx.beginPath(); ctx.ellipse(cx, baseY - TILE * 0.1, TILE * 0.28, TILE * 0.08, 0, 0, Math.PI * 2); ctx.fill();
      ctx.restore();
      const name = entitySprite(e);
      const fi = (now() / 140) | 0;
      let drew = false;
      if (name && !(e.type === "chest" && e.state === "open")) {
        drew = drawUnitSprite(name, cx, baseY, null, fi);
      }
      if (!drew) {
        ctx.font = Math.floor(TILE * 0.7) + "px serif";
        ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.fillText(e.type === "chest" && e.state === "open" ? "📭" : e.sprite, cx, cy);
      }
    }
    // lock badge
    if (e.state === "locked") {
      ctx.font = Math.floor(TILE * 0.4) + "px serif";
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText("🔒", cx, sy(e.y) + TILE * 0.15);
    }
    // enemy HP bar
    if ((e.type === "enemy" || e.type === "boss") && e.hp > 0) {
      const w = TILE * 0.9, h = 5, bx = cx - w / 2, by = sy(e.y) - 4;
      ctx.fillStyle = "#000"; ctx.fillRect(bx - 1, by - 1, w + 2, h + 2);
      ctx.fillStyle = "#3a1020"; ctx.fillRect(bx, by, w, h);
      ctx.fillStyle = e.type === "boss" ? "#ffd24a" : "#ff5d73";
      ctx.fillRect(bx, by, w * clamp(e.hp / e.max_hp, 0, 1), h);
      if (distToPlayer(e) <= 4) {
        ctx.fillStyle = "#ffd24a";
        ctx.font = "bold " + Math.floor(TILE * 0.24) + 'px "Press Start 2P", monospace';
        ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.fillText("!", cx, sy(e.y) - 13);
      }
      const fxIcons = Object.keys(e.fx || {}).map((k) => FX_ICON[k]).filter(Boolean).join("");
      if (fxIcons) {
        ctx.font = Math.floor(TILE * 0.32) + "px serif";
        ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.fillText(fxIcons, cx, sy(e.y) - 22);
      }
    }
    if (e.type === "npc" && P.trust && P.trust[e.id]) {
      ctx.font = Math.floor(TILE * 0.28) + "px serif";
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(P.trust[e.id] > 0 ? "♥" : "?", cx + TILE * 0.32, sy(e.y) + TILE * 0.12);
    }
  }

  function playerSprite() {
    if (P.evolved && spr(KING_SPRITE)) return KING_SPRITE;
    const c = CLASS_SPRITE[P.goblin_class];
    if (c && spr(c)) return c;
    const fb = CLASS_SPRITE_FALLBACK[P.goblin_class];
    if (fb && spr(fb)) return fb;
    return spr("player") ? "player" : null;
  }
  function drawPlayer() {
    const cx = sx(P.x) + TILE / 2, cy = sy(P.y) + TILE / 2, baseY = sy(P.y) + TILE * 0.98;
    const fi = (now() / 140) | 0;
    const name = playerSprite();
    // evolved Goblin King aura
    if (P.evolved) {
      ctx.save();
      ctx.globalAlpha = 0.35 + 0.15 * Math.sin(now() / 220);
      const g = ctx.createRadialGradient(cx, cy, 2, cx, cy, TILE * 0.7);
      g.addColorStop(0, "rgba(255,210,74,0.8)"); g.addColorStop(1, "rgba(255,210,74,0)");
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, TILE * 0.7, 0, Math.PI * 2); ctx.fill();
      ctx.restore();
    }
    let drew = false;
    if (name) {
      ctx.save();
      if (facing === "left") { ctx.translate(cx * 2, 0); ctx.scale(-1, 1); }
      drew = drawUnitSprite(name, cx, baseY, null, fi);  // hero scale from CRE_SCALE
      ctx.restore();
    }
    if (P.evolved) {
      ctx.font = Math.floor(TILE * 0.4) + "px serif";
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText("👑", cx, sy(P.y) + TILE * 0.06);
    }
    if (!drew) {
      ctx.font = Math.floor(TILE * 0.7) + "px serif";
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText("🧙", cx, cy);
    }
    // facing pip
    const v = DIRV[facing];
    ctx.fillStyle = "#ffd24a";
    ctx.beginPath();
    ctx.arc(cx + v[0] * TILE * 0.36, cy + v[1] * TILE * 0.36, 3, 0, 7);
    ctx.fill();
  }

  // ground-level magic circles, drawn under entities
  function drawCircles() {
    if (!CIRCLES || !CIRCLES.img.complete || !CIRCLES.img.naturalWidth) return;
    ctx.imageSmoothingEnabled = false;
    for (const f of vfx) {
      if (f.kind !== "circle") continue;
      const t = now() - f.start; if (t < 0) continue;
      const p = t / f.dur; if (p >= 1) continue;
      const fi = Math.floor(t / (1000 / CIRCLES.fps)) % CIRCLES.frames;
      const dw = TILE * f.scale, dh = dw;
      ctx.globalAlpha = p < 0.15 ? p / 0.15 : (p > 0.8 ? (1 - p) / 0.2 : 1);
      ctx.drawImage(CIRCLES.img, fi * CIRCLES.fw, f.row * CIRCLES.fh, CIRCLES.fw, CIRCLES.fh,
        OX + f.tx * TILE - dw / 2, OY + f.ty * TILE - dh / 2, dw, dh);
      ctx.globalAlpha = 1;
    }
  }

  function drawVfx() {
    const FM = 24; // ms per frame
    const keep = [];
    ctx.imageSmoothingEnabled = false;
    for (const f of vfx) {
      const t = now() - f.start;
      if (t < 0) { keep.push(f); continue; }
      if (f.kind === "anim" || f.kind === "proj") {
        const m = VFXM[f.sheet];
        if (!m || !m.img.complete || !m.img.naturalWidth) { keep.push(f); continue; }
        const fi = Math.floor(t / FM);
        let cx, cy, fcol;
        if (f.kind === "proj") {
          const p = Math.min(1, t / f.travel);
          cx = OX + (f.fx + (f.txx - f.fx) * p) * TILE;
          cy = OY + (f.fy + (f.tyy - f.fy) * p) * TILE;
          fcol = fi % m.frames;
          if (p >= 1) continue;
          keep.push(f);
        } else {
          if (fi >= m.frames) continue;
          keep.push(f);
          cx = OX + f.tx * TILE; cy = OY + f.ty * TILE; fcol = fi;
        }
        const dw = TILE * f.scale, dh = dw * (m.fh / m.fw);
        ctx.drawImage(m.img, fcol * m.fw, 0, m.fw, m.fh, cx - dw / 2, cy - dh / 2, dw, dh);
      } else if (f.kind === "circle") {
        const p = t / f.dur; if (p >= 1) continue; keep.push(f); // drawn under entities by drawCircles()
      } else if (f.kind === "num") {
        const p = t / f.dur; if (p >= 1) continue; keep.push(f);
        ctx.fillStyle = f.color; ctx.globalAlpha = 1 - p;
        ctx.font = "bold " + Math.floor(TILE * 0.42) + 'px "Press Start 2P", monospace';
        ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.fillText(f.text, OX + f.tx * TILE, OY + f.ty * TILE - p * 30);
        ctx.globalAlpha = 1;
      } else if (f.kind === "hit") {
        const p = t / f.dur; if (p >= 1) continue; keep.push(f);
        ctx.fillStyle = "rgba(255,80,90," + (0.4 * (1 - p)) + ")";
        ctx.fillRect(0, HUD_TOP, canvas.width, canvas.height - HUD_TOP);
      }
    }
    vfx = keep;
  }

  function drawHud() {
    ctx.fillStyle = "rgba(16,10,26,0.92)";
    ctx.fillRect(0, 0, canvas.width, HUD_TOP);
    ctx.fillStyle = "#34254d"; ctx.fillRect(0, HUD_TOP - 2, canvas.width, 2);
    ctx.textBaseline = "middle"; ctx.textAlign = "left";
    ctx.font = '11px "Press Start 2P", monospace';
    let hx = 12;
    const cy = 18;
    ctx.fillStyle = "#ff5d73"; ctx.fillText("HP " + P.hp + "/" + P.max_hp, hx, cy); hx += 140;
    ctx.fillStyle = "#ffd24a"; ctx.fillText("CR " + P.courage + "/" + P.max_courage, hx, cy); hx += 120;
    ctx.fillStyle = (P.evolved ? "#ffd24a" : "#cdbfff");
    ctx.fillText("LV " + P.level + (P.evolved ? " 👑" : ""), hx, cy); hx += 95;
    // XP bar
    const xpw = 90, xb = hx, frac = P.xp_to_next > 0 ? clamp(P.xp / P.xp_to_next, 0, 1) : 1;
    ctx.fillStyle = "#241a36"; ctx.fillRect(xb, cy - 5, xpw, 10);
    ctx.fillStyle = "#6df5a0"; ctx.fillRect(xb, cy - 5, xpw * frac, 10);
    ctx.strokeStyle = "#34254d"; ctx.strokeRect(xb, cy - 5, xpw, 10);
    hx += xpw + 16;
    const bagCount = Object.values(P.items || {}).reduce((a, b) => a + b, 0);
    ctx.fillStyle = "#9c8bc4"; ctx.fillText("BAG " + bagCount, hx, cy); hx += 95;
    ctx.fillStyle = "#ffd24a"; ctx.fillText("G " + (P.gold || 0), hx, cy);
    ctx.textAlign = "right";
    const areaLabel = A.name.toUpperCase();
    ctx.fillStyle = "#b07cff";
    ctx.fillText(areaLabel, canvas.width - 14, cy);
    if (W && W.admin) {
      ctx.fillStyle = "#6df5a0";
      ctx.fillText("🔓 ADMIN", canvas.width - 14 - ctx.measureText(areaLabel).width - 18, cy);
    }
    // bottom row: weapon (left) + objective icon track (right)
    ctx.textAlign = "left"; ctx.font = '10px "Press Start 2P", monospace';
    ctx.fillStyle = "#ffce6b";
    ctx.fillText("🗡 " + weaponLabel(P.weapon).toUpperCase(), 12, HUD_TOP - 14);
    const pfx = Object.keys(P.fx || {}).map((k) => FX_ICON[k] + P.fx[k]).join(" ");
    if (pfx) {
      ctx.fillStyle = "#6df5a0";
      ctx.fillText(pfx, 12 + ctx.measureText("🗡 " + weaponLabel(P.weapon).toUpperCase()).width + 16, HUD_TOP - 14);
    }
    drawObjectiveIcons(HUD_TOP - 14);
    ctx.textAlign = "left";
  }

  // Compact objective track: faded = done, gold+underline = current, dim = future.
  // Click-zone (canvas coords) recorded in objHit so the canvas handler can open
  // the Journal when the painted icons are clicked.
  function drawObjectiveIcons(y) {
    const steps = objectiveSteps();
    const STEP = 30, R = canvas.width - 14;
    objHit = { x0: R - steps.length * STEP - 78, y0: y - 14, x1: R + 2, y1: y + 14 };
    const cur = steps.find((s) => s.current);
    // tiny current-step label so the icons stay understandable
    ctx.textAlign = "right"; ctx.font = '9px "Press Start 2P", monospace';
    ctx.fillStyle = "#ffd24a";
    const labelX = R - steps.length * STEP - 8;
    ctx.fillText(cur ? cur.label : "DONE", labelX, y);
    // icons, left-to-right ending at the right margin
    ctx.textAlign = "center"; ctx.font = '16px sans-serif';
    const startX = R - steps.length * STEP + STEP / 2;
    steps.forEach((s, i) => {
      const x = startX + i * STEP;
      ctx.globalAlpha = s.current ? 1 : (s.done ? 0.4 : 0.55);
      ctx.fillText(s.icon, x, y);
      if (s.current) {
        ctx.fillStyle = "#ffd24a"; ctx.fillRect(x - 9, y + 9, 18, 2);
      } else if (s.done) {
        ctx.fillStyle = "#6df5a0"; ctx.font = '8px "Press Start 2P", monospace';
        ctx.fillText("✓", x + 9, y - 8); ctx.font = '16px sans-serif';
      }
    });
    ctx.globalAlpha = 1;
  }

  // ---- circular minimap (translucent overlay, top-right; M toggles) ----
  let minimapOn = true;
  let miniCache = { areaId: null, canvas: null, scale: 1, r: 0 };
  function miniRadius() { return clamp(Math.round(Math.min(canvas.width, canvas.height) * 0.13), 52, 88); }
  function buildMiniTerrain(R) {
    const rowsN = A.rows.length, colsN = A.rows[0].length;
    const diag = Math.sqrt(colsN * colsN + rowsN * rowsN);
    const scale = (R * 2 - 12) / diag;
    const c = document.createElement("canvas");
    c.width = Math.ceil(colsN * scale); c.height = Math.ceil(rowsN * scale);
    const mc = c.getContext("2d");
    const b = BIOME[A.biome] || DEFAULT_BIOME;
    const waterMid = waterColor()[1];
    for (let y = 0; y < rowsN; y++) {
      for (let x = 0; x < colsN; x++) {
        const ch = A.rows[y][x];
        let col = null;
        if (ch === "~") col = waterMid;
        else if (WALK.has(ch)) col = b.alt;
        else if (ch === "#") col = b.wall;
        if (col) { mc.fillStyle = col; mc.fillRect(x * scale, y * scale, scale + 0.5, scale + 0.5); }
      }
    }
    miniCache = { areaId: P.area, canvas: c, scale, r: R };
  }
  function drawMinimap() {
    if (!minimapOn || !A) return;
    const R = miniRadius();
    if (miniCache.areaId !== P.area || miniCache.r !== R || !miniCache.canvas) buildMiniTerrain(R);
    const cx = canvas.width - R - 14, cy = HUD_TOP + R + 12;
    ctx.save();
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.clip();
    // translucent smoked-glass disc
    ctx.globalAlpha = 0.62;
    ctx.fillStyle = "#0c0816";
    ctx.fillRect(cx - R, cy - R, R * 2, R * 2);
    const mw = miniCache.canvas.width, mh = miniCache.canvas.height;
    const ox = cx - mw / 2, oy = cy - mh / 2;
    ctx.globalAlpha = 0.78;
    ctx.drawImage(miniCache.canvas, ox, oy);
    // live entity dots (skip clutter — only things worth walking toward)
    const s = miniCache.scale;
    const dot = (x, y, r, col) => { ctx.fillStyle = col; ctx.beginPath();
      ctx.arc(ox + (x + 0.5) * s, oy + (y + 0.5) * s, r, 0, Math.PI * 2); ctx.fill(); };
    ctx.globalAlpha = 0.95;
    for (const e of liveEntities()) {
      if (e.type === "boss") dot(e.x, e.y, 3.4, "#ff2d4d");
      else if (e.type === "enemy") dot(e.x, e.y, 2.2, "#ff5d73");
      else if (e.type === "npc") dot(e.x, e.y, 2.2, "#6df5a0");
      else if (e.type === "portal") dot(e.x, e.y, 2.8, e.state === "locked" ? "#ff9d4a" : "#b07cff");
      else if (e.type === "chest" && e.state !== "open") dot(e.x, e.y, 2.0, "#ffd24a");
      else if (e.type === "shrine") dot(e.x, e.y, 2.0, "#7fd6ff");
      else if (e.type === "powerup") dot(e.x, e.y, 2.0, "#ffffff");
    }
    // player: pulsing white dot
    dot(P.x, P.y, 3.0 + Math.sin(now() / 280) * 0.7, "#ffffff");
    ctx.restore();
    // ring border + inner glow line
    ctx.save();
    ctx.globalAlpha = 0.85; ctx.strokeStyle = "#b07cff"; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.stroke();
    ctx.globalAlpha = 0.30; ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.arc(cx, cy, R - 3, 0, Math.PI * 2); ctx.stroke();
    ctx.restore();
    ctx.globalAlpha = 1;
  }

  function render() {
    if (paused) return;
    fitCanvas();
    if (selecting || !A) {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = "#0b0810"; ctx.fillRect(0, 0, canvas.width, canvas.height);
      requestAnimationFrame(render);
      return;
    }
    camera();
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#0b0810"; ctx.fillRect(0, 0, canvas.width, canvas.height);
    drawTiles();
    drawCircles();
    // depth sort: lower y drawn first, player interleaved by row
    const ents = liveEntities().slice().sort((a, b) => a.y - b.y);
    let playerDrawn = false;
    for (const e of ents) {
      if (!playerDrawn && e.y > P.y) { drawPlayer(); playerDrawn = true; }
      drawEntity(e);
    }
    if (!playerDrawn) drawPlayer();
    drawVfx();
    drawBarks();
    drawHud();
    drawMinimap();
    requestAnimationFrame(render);
  }

  // ---- palette / DOM ----
  const ICON = (k) => "/rg/static/icons/" + k + ".png";
  function renderPalette() {
    const sel = $("rg-sel");
    if (sel) sel.innerHTML = selected.length
      ? selected.map((k) => "<img class='ricon' src='" + ICON(k) + "' alt=''>").join("<span class='plus'>+</span>")
      : "<span class='dim'>no runes</span>";
    document.querySelectorAll(".rg-rune").forEach((b) => {
      b.classList.toggle("on", selected.includes(b.dataset.rune));
    });
  }

  function toggleRune(k) {
    const i = selected.indexOf(k);
    if (i >= 0) selected.splice(i, 1);
    else if (selected.length < maxRunes()) selected.push(k);
    else { toast("You can weave " + maxRunes() + " runes (4-rune casts unlock at level 3)."); return; }
    renderPalette();
  }

  function buildPalette() {
    const pal = $("rg-palette");
    pal.innerHTML = "";
    runesMeta.forEach((r, i) => {
      const b = document.createElement("button");
      b.className = "rg-rune"; b.dataset.rune = r.key;
      b.title = r.label + " — " + (r.meanings || []).join(", ");
      b.innerHTML = (i < 9 ? "<span class='num'>" + (i + 1) + "</span>" : "")
        + "<img class='ricon' src='" + ICON(r.key) + "' alt='" + r.label + "'>";
      b.onclick = () => { toggleRune(r.key); canvas.focus(); };
      pal.appendChild(b);
    });
  }

  // ---- spell reading card: what the vision model read from your drawing ----
  let readingTimer = null;
  function escapeHtml(t) {
    return String(t || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function readingCard() {
    let card = $("rg-reading");
    if (!card) {
      card = document.createElement("div");
      card.id = "rg-reading"; card.className = "rg-reading";
      card.onclick = hideReading;
      document.getElementById("rg-stage").appendChild(card);
    }
    return card;
  }
  // Opens instantly when the drawing is sent, and stays up while the vision
  // model thinks — the result then replaces it in place.
  function showReadingPending() {
    const card = readingCard();
    card.innerHTML =
      "<div class='rg-read-head'>👁 The goblin squints at your drawing…</div>" +
      "<div class='rg-read-runes'><span class='rg-read-rune rg-read-wait'>" +
      "<i></i><i></i><i></i></span></div>" +
      "<div class='rg-read-note'>reading runes — first read can take a while</div>";
    card.classList.add("open");
    clearTimeout(readingTimer);
  }
  function showReading(res) {
    const vr = res.visual_reading || {};
    const s = res.spell || {};
    const card = readingCard();
    const det = vr.detected_runes || [];
    const amb = (vr.ambiguous_runes || []).filter((r) => !det.includes(r));
    const chip = (r, dim) => {
      const known = (runesMeta || []).some((x) => x.key === r);
      return "<span class='rg-read-rune" + (dim ? " dim" : "") + "'>" +
        (known ? "<img src='" + ICON(r) + "' alt=''> " : "") +
        escapeHtml(runeLabel(r)) + (dim ? " ?" : "") + "</span>";
    };
    const chips = det.map((r) => chip(r, false)).concat(amb.map((r) => chip(r, true))).join("");
    const conf = typeof vr.confidence === "number" && vr.confidence > 0
      ? "<div class='rg-read-conf' title='reading confidence'><i style='width:" +
        Math.round(Math.min(1, vr.confidence) * 100) + "%'></i></div>" : "";
    const note = (vr.notes && vr.notes[0]) || vr.drawing_style || "";
    const head = res.visual_reading
      ? "👁 The goblin read your drawing:"
      : "👁 The goblin couldn't read it — the rule engine took over:";
    card.innerHTML =
      "<div class='rg-read-head'>" + head + "</div>" +
      "<div class='rg-read-runes'>" + (chips ||
        "<span class='rg-read-rune dim'>unreadable scribble</span>") + "</div>" +
      "<div class='rg-read-spell'>“" + escapeHtml(s.spell_name || "Mystery Spell") + "”</div>" +
      (note ? "<div class='rg-read-note'>" + escapeHtml(note) + "</div>" : "") +
      conf;
    card.classList.add("open");
    clearTimeout(readingTimer);
    readingTimer = setTimeout(hideReading, 5200);
  }
  function hideReading() { const c = $("rg-reading"); if (c) c.classList.remove("open"); }

  // ---- drawing overlay ----
  function openDraw() {
    if (over) return;
    drawing = true; $("rg-draw").classList.add("open");
    clearSketch();
  }
  function closeDraw() { drawing = false; $("rg-draw").classList.remove("open"); }
  function clearSketch() { sctx.fillStyle = "#efe1bd"; sctx.fillRect(0, 0, sketch.width, sketch.height); }
  function setupSketch() {
    sketch = $("rg-sketch"); sctx = sketch.getContext("2d");
    clearSketch();
    let down = false, lx = 0, ly = 0;
    const pos = (ev) => { const r = sketch.getBoundingClientRect();
      const t = ev.touches ? ev.touches[0] : ev;
      return [(t.clientX - r.left) * sketch.width / r.width, (t.clientY - r.top) * sketch.height / r.height]; };
    const start = (ev) => { down = true; [lx, ly] = pos(ev); ev.preventDefault(); };
    const move = (ev) => { if (!down) return; const [x, y] = pos(ev);
      sctx.strokeStyle = "#17120b"; sctx.lineWidth = 7; sctx.lineCap = "round";
      sctx.beginPath(); sctx.moveTo(lx, ly); sctx.lineTo(x, y); sctx.stroke();
      lx = x; ly = y; ev.preventDefault(); };
    const end = () => { down = false; };
    sketch.addEventListener("mousedown", start); sketch.addEventListener("mousemove", move);
    window.addEventListener("mouseup", end);
    sketch.addEventListener("touchstart", start); sketch.addEventListener("touchmove", move);
    sketch.addEventListener("touchend", end);
  }

  // ---- input ----
  function onKey(ev) {
    const k = ev.key.toLowerCase();
    // Shift+L+A (held together) toggles admin mode from anywhere, even normal play.
    if (ev.shiftKey && keysDown.has("l") && keysDown.has("a") && !ev.repeat) {
      if (now() - lastAdminToggle > 350) { lastAdminToggle = now(); setAdmin(!adminMode); }
      ev.preventDefault(); return;
    }
    if (selecting) { return; }
    if (drawing) { if (k === "escape") closeDraw(); return; }
    if (dialogueOpen) { if (k === "escape" || k === " " || k === "enter") { closeDialogue(); ev.preventDefault(); } return; }
    if (k === "j") { toggleJournal(); ev.preventDefault(); return; }
    if (k === "i") { toggleInventory(); ev.preventDefault(); return; }
    if (k === "m") { minimapOn = !minimapOn; ev.preventDefault(); return; }
    if (journalOpen && k === "escape") { toggleJournal(); return; }
    if (invOpen && k === "escape") { toggleInventory(); return; }
    if (over) return;
    if (k === "t") { talk(); ev.preventDefault(); return; }
    if (["arrowup", "w"].includes(k)) { tryMove("up"); ev.preventDefault(); }
    else if (["arrowdown", "s"].includes(k)) { tryMove("down"); ev.preventDefault(); }
    else if (["arrowleft", "a"].includes(k)) { tryMove("left"); ev.preventDefault(); }
    else if (["arrowright", "d"].includes(k)) { tryMove("right"); ev.preventDefault(); }
    else if (k === " " || k === "enter") { castRunes(); ev.preventDefault(); }
    else if (k === "e") { openDraw(); ev.preventDefault(); }
    else if (k === "c") { selected = []; renderPalette(); }
    else if (k >= "1" && k <= "9") { const idx = parseInt(k, 10) - 1; if (runesMeta[idx]) toggleRune(runesMeta[idx].key); }
  }

  // ---- character select ----
  function buildSelect() {
    const wrap = $("rg-heroes"); if (!wrap) return;
    wrap.innerHTML = "";
    CLASSES.forEach((c) => {
      const card = document.createElement("div");
      card.className = "rg-hero"; card.dataset.cls = c.id;
      const aff = (c.affinity || []).join(", ");
      card.innerHTML =
        "<img src='/rg/static/sprites/" + c.preview_gif + "' alt='" + c.label + "'>" +
        "<div class='hname'>" + c.label + "</div>" +
        "<div class='hstat'>HP " + c.hp + " · CR " + c.courage + "</div>" +
        "<div class='hpass'>" + aff + "<br>" + c.passive + "</div>";
      card.onclick = () => {
        chosenClass = c.id;
        document.querySelectorAll(".rg-hero").forEach((h) => h.classList.toggle("sel", h.dataset.cls === c.id));
        let line = $("rg-select-line");
        if (!line) { line = document.createElement("div"); line.id = "rg-select-line"; line.className = "rg-select-line"; $("rg-heroes").after(line); }
        line.textContent = c.select_line;
        $("rg-select-start").disabled = false;
      };
      wrap.appendChild(card);
    });
  }
  function showSelect() {
    selecting = true; chosenClass = null;
    $("rg-select").className = "rg-select open";
    $("rg-select-start").disabled = true;
    buildSelect();
  }

  // ---- boot ----
  async function newGame() {
    if (!W) W = await api(worldUrl());
    runesMeta = W.runes;
    CLASSES = W.classes || [];
    WEAPONS = {}; (W.weapons || []).forEach((w) => { WEAPONS[w.id] = w; });
    ITEMS = {}; (W.items || []).forEach((i) => { ITEMS[i.id] = i; });
    QUESTS_META = {}; (W.quests || []).forEach((q) => { QUESTS_META[q.id] = q; });
    STORY_BEATS = W.story_beats || [];
    barks = [];
    areas = JSON.parse(JSON.stringify(W.areas));
    P = JSON.parse(JSON.stringify(W.player));
    ensurePlayerMeta();
    bootFlags.forEach(addFlag);
    over = false; lastEnding = null;
    $("rg-end").className = "rg-end";
    closeDialogue(); $("rg-journal").className = "rg-journal"; journalOpen = false;
    $("rg-inventory").className = "rg-journal rg-inventory"; invOpen = false;
    showSelect();
  }

  function startGame(classId) {
    const c = CLASSES.find((x) => x.id === classId) || CLASSES[0];
    if (c) {
      P.goblin_class = c.id; P.hp = c.hp; P.max_hp = c.hp;
      P.courage = c.courage; P.max_courage = Math.max(9, c.courage + 2);
    }
    selecting = false; $("rg-select").className = "rg-select";
    P.area = (bootArea && areas[bootArea]) ? bootArea : W.start_area;
    A = areas[P.area];
    applyConditionalSpawns(P.area);
    const sp = A.spawn; P.x = sp[0]; P.y = sp[1];
    facing = "down"; selected = []; vfx = []; busy = false; turnNo = 0; enemyCooldown = {};
    layout(); buildPalette(); renderPalette(); updateTarget(); regionCue();
    // Reconcile admin mode against the freshly-cloned (re-locked) world: honor the
    // backend RG_ADMIN flag, and keep client admin on across a New Game.
    const wantAdmin = adminMode || !!(W && W.admin);
    adminMode = false; adminLockSnapshot = null;
    if (wantAdmin) setAdmin(true); else showAdminGoto(false);
    const label = c ? c.label : "goblin";
    const seedLine = W.world_seed === null || W.world_seed === undefined ? "" :
      " Loop seed <b>" + W.world_seed + "</b>: " + ((W.variation || {}).label || "seeded loop") + ".";
    toast("You are the <b>" + label + "</b>. You broke the calendar. " + moodLine() + "." + seedLine + " — roam, talk (T), and cast.");
    // Opening beat lands shortly after the class toast so both get read.
    setTimeout(() => { if (!over && !selecting) { checkAreaBeats(); checkProximityBeats(); } }, 1800);
    if (bootMasteryChoice) setTimeout(() => grantMasteryChoice(), 250);
  }

  // ---- weapons ----
  const WEAPON_ICON = { clerk_wand: "wpn_magic", bell_staff: "wpn_shield",
    mirror_shield: "wpn_mirror", bone_blade: "wpn_sword", coin_sling: "wpn_fire",
    river_thread: "wpn_water" };
  function equipWeapon(id) {
    if (!(P.weapon_inventory || []).includes(id)) return;
    P.weapon = id;
    toast("🗡️ Equipped <b>" + weaponLabel(id) + "</b>. " + ((WEAPONS[id] || {}).identity || ""));
    refreshPanels();
  }
  function weaponStats(w) {
    const s = [];
    if (w.bonus_damage) s.push("+" + w.bonus_damage + " dmg on " + (w.school || []).join("/"));
    if (w.courage_relief) s.push("-" + w.courage_relief + " courage cost");
    if (w.shield_chance) s.push("shield chance");
    if (w.unlock_bonus) s.push("better unlocks");
    if (w.xp_bonus) s.push("+" + w.xp_bonus + " XP per win");
    return s.length ? "<br><span class='wstats'>" + s.join(" · ") + "</span>" : "";
  }
  function weaponsHtml() {
    const inv = P.weapon_inventory || [P.weapon];
    return inv.map((id) => {
      const w = WEAPONS[id] || { label: id, identity: "", school: [] };
      const on = id === P.weapon ? " equipped" : "";
      const ic = "/rg/static/icons/" + (WEAPON_ICON[id] || "wpn_magic") + ".png";
      const sch = (w.school || []).length ? " <span class='flag'>(" + w.school.join("/") + ")</span>" : "";
      return "<button class='rg-wpn" + on + "' data-w='" + id + "'>" +
        "<img src='" + ic + "' alt=''> <b>" + w.label + (on ? " ✓" : "") + "</b>" + sch +
        "<br><span class='wdesc'>" + w.identity + "</span>" + weaponStats(w) + "</button>";
    }).join("");
  }

  // ---- item bag + quests (inventory system) ----
  function bagHtml() {
    const ids = Object.keys(P.items || {}).filter((id) => itemCount(id) > 0);
    if (!ids.length) return "<ul><li class='flag'>— bag empty — defeat monsters for loot —</li></ul>";
    // potions first so the usable ones are easy to reach
    ids.sort((a, b) => ((ITEMS[b] && ITEMS[b].kind === "potion") - (ITEMS[a] && ITEMS[a].kind === "potion")));
    return "<div class='rg-bag'>" + ids.map((id) => {
      const m = ITEMS[id] || { icon: "📦", label: id, kind: "material", desc: "" };
      const usable = m.kind === "potion";
      return "<div class='rg-item" + (usable ? " usable" : "") + "'" + (usable ? " data-use='" + id + "'" : "") +
        " title='" + (m.desc || "") + "'>" +
        "<span class='rg-item-ic'>" + (m.icon || "📦") + "</span>" +
        "<span class='rg-item-lb'>" + m.label + "</span>" +
        "<span class='rg-item-qty'>×" + itemCount(id) + "</span>" +
        (usable ? "<span class='rg-item-use'>Use</span>" : "") + "</div>";
    }).join("") + "</div>";
  }
  function questsHtml() {
    const ids = Object.keys(P.quests || {});
    if (!ids.length) return "<ul><li class='flag'>— no quests yet — talk (T) to the Watch, Druid or Quartermaster —</li></ul>";
    return "<ul>" + ids.map((id) => {
      const q = QUESTS_META[id] || { title: id };
      const st = P.quests[id];
      if (st === "done") return "<li>✓ <b>" + q.title + "</b> <span class='flag'>complete</span></li>";
      const have = itemCount(q.objective_item), need = q.count || 0;
      return "<li>• <b>" + q.title + "</b> — " + have + "/" + need + " " + (q.objective_label || "") +
        (have >= need ? " <span style='color:#6df5a0'>(turn in!)</span>" : "") + "</li>";
    }).join("") + "</ul>";
  }

  // ---- journal panel ----
  function renderJournal() {
    const body = $("rg-journal-body"); if (!body) return;
    const cls = CLASSES.find((c) => c.id === P.goblin_class) || {};
    const li = (arr) => arr.length ? "<ul>" + arr.map((x) => "<li>" + x + "</li>").join("") + "</ul>" : "<ul><li class='flag'>— nothing yet —</li></ul>";
    const flags = (P.story_flags || []).map((f) => "<li class='flag'>" + f.replace(/_/g, " ") + "</li>");
    const mastered = Object.keys(P.rune_mastery || {}).filter((r) => P.rune_mastery[r] >= 5);
    const recentEvents = (P.recent_story_events || []).map((e) => e.text || e);
    body.innerHTML =
      "<div class='rg-jsec'><h4>Hero</h4><ul><li>" + (cls.label || "Goblin") + (P.evolved ? " 👑 (King)" : "") +
        " · Lv " + P.level + " · XP " + P.xp + "/" + P.xp_to_next + "</li></ul></div>" +
      "<div class='rg-jsec'><h4>Objective</h4><ul><li>" + questText() + "</li></ul></div>" +
      "<div class='rg-jsec'><h4>Quests (talk to turn in)</h4>" + questsHtml() + "</div>" +
      "<div class='rg-jsec'><h4>Recent events</h4>" + li(recentEvents) + "</div>" +
      "<div class='rg-jsec'><h4>Discoveries</h4>" + li((P.journal || []).concat((P.discoveries || []).filter((d) => !(P.journal || []).includes(d)))) + "</div>" +
      (mastered.length ? "<div class='rg-jsec'><h4>Rune mastery</h4><ul>" + mastered.map((r) => "<li class='flag'>" + r.replace(/_/g, " ") + " ✦</li>").join("") + "</ul></div>" : "") +
      "<div class='rg-jsec'><h4>Story memory</h4><ul>" + (flags.length ? flags.join("") : "<li class='flag'>— the world has not remembered anything yet —</li>") + "</ul></div>";
  }
  function toggleJournal() {
    journalOpen = !journalOpen;
    if (journalOpen) { renderJournal(); if (invOpen) toggleInventory(); }
    $("rg-journal").className = "rg-journal" + (journalOpen ? " open" : "");
  }

  // ---- inventory panel (separate from the journal) ----
  function renderInventory() {
    const body = $("rg-inventory-body"); if (!body) return;
    const li = (arr) => arr.length ? "<ul>" + arr.map((x) => "<li>" + x + "</li>").join("") + "</ul>" : "<ul><li class='flag'>— nothing yet —</li></ul>";
    body.innerHTML =
      "<div class='rg-jsec'><h4>Equipped weapon</h4><div class='rg-wpns'>" +
        "<button class='rg-wpn equipped'><img src='/rg/static/icons/" + (WEAPON_ICON[P.weapon] || "wpn_magic") +
        ".png' alt=''> <b>" + weaponLabel(P.weapon) + "</b></button></div></div>" +
      "<div class='rg-jsec'><h4>Weapons (click to equip)</h4><div class='rg-wpns'>" + weaponsHtml() + "</div></div>" +
      "<div class='rg-jsec'><h4>Bag (click a potion to use)</h4>" + bagHtml() + "</div>" +
      "<div class='rg-jsec'><h4>Key items</h4>" + li(P.inventory || []) + "</div>" +
      "<div class='rg-jsec'><h4>Coins</h4><ul><li>🪙 " + (P.gold || 0) + " coins</li></ul></div>";
    body.querySelectorAll(".rg-wpn[data-w]").forEach((b) => { b.onclick = () => equipWeapon(b.dataset.w); });
    body.querySelectorAll(".rg-item[data-use]").forEach((b) => { b.onclick = () => useItem(b.dataset.use); });
  }
  function toggleInventory() {
    invOpen = !invOpen;
    if (invOpen) { renderInventory(); if (journalOpen) toggleJournal(); }
    $("rg-inventory").className = "rg-journal rg-inventory" + (invOpen ? " open" : "");
  }
  function refreshPanels() { if (invOpen) renderInventory(); if (journalOpen) renderJournal(); }

  // Keep the canvas's internal resolution equal to its displayed CSS size.
  // Called every frame so it self-corrects even if Gradio lays out the iframe
  // late or the window resizes — otherwise the world renders at the wrong
  // scale and the player drifts off-screen.
  function fitCanvas() {
    const cw = canvas.clientWidth, ch = canvas.clientHeight;
    if (cw > 0 && ch > 0 && (canvas.width !== cw || canvas.height !== ch)) {
      canvas.width = cw; canvas.height = ch;
      if (A) layout();
    }
  }
  function resizeCanvas() { fitCanvas(); }

  function bootUI() {
    canvas = $("rg-canvas"); ctx = canvas.getContext("2d");
    setupSketch();
    resizeCanvas();
    window.addEventListener("resize", resizeCanvas);
    $("rg-boot").style.display = "none";
    const gesture = () => initAudio();
    $("rg-cast").onclick = () => { gesture(); castRunes(); canvas.focus(); };
    $("rg-draw-open").onclick = () => { gesture(); openDraw(); };
    $("rg-talk").onclick = () => { gesture(); talk(); canvas.focus(); };
    $("rg-journal-open").onclick = () => { gesture(); toggleJournal(); canvas.focus(); };
    const jc = $("rg-journal-close"); if (jc) jc.onclick = () => { toggleJournal(); canvas.focus(); };
    const io = $("rg-inventory-open"); if (io) io.onclick = () => { gesture(); toggleInventory(); canvas.focus(); };
    const ic = $("rg-inventory-close"); if (ic) ic.onclick = () => { toggleInventory(); canvas.focus(); };
    const ss = $("rg-select-start"); if (ss) ss.onclick = () => { gesture(); startGame(chosenClass); canvas.focus(); };
    const dlg = $("rg-dialogue"); if (dlg) dlg.onclick = () => { closeDialogue(); canvas.focus(); };
    $("rg-clear").onclick = () => { selected = []; renderPalette(); canvas.focus(); };
    $("rg-reset").onclick = () => { newGame(); canvas.focus(); };
    $("rg-draw-cast").onclick = castDrawing;
    $("rg-draw-clear").onclick = clearSketch;
    $("rg-draw-cancel").onclick = closeDraw;
    $("rg-end-restart").onclick = () => { newGame(); canvas.focus(); };
    $("rg-mute").onclick = () => { gesture(); toggleMute(); canvas.focus(); };
    $("rg-full").onclick = () => {
      const el = document.documentElement;
      if (document.fullscreenElement) document.exitFullscreen();
      else if (el.requestFullscreen) el.requestFullscreen().catch(() => {});
      canvas.focus();
    };
    window.addEventListener("keydown", (e) => { keysDown.add(e.key.toLowerCase()); gesture(); onKey(e); });
    window.addEventListener("keyup", (e) => { keysDown.delete(e.key.toLowerCase()); });
    window.addEventListener("blur", () => keysDown.clear());
    const goto = $("rg-admin-goto");
    if (goto) goto.onchange = () => { const id = goto.value; goto.value = ""; if (id) warpToArea(id); canvas.focus(); };
    canvas.addEventListener("click", (ev) => {
      gesture(); canvas.focus();
      // Clicking the HUD objective icons opens the Journal (full objective + quests).
      if (objHit) {
        const r = canvas.getBoundingClientRect();
        const cx = (ev.clientX - r.left) * canvas.width / r.width;
        const cy = (ev.clientY - r.top) * canvas.height / r.height;
        if (cx >= objHit.x0 && cx <= objHit.x1 && cy >= objHit.y0 && cy <= objHit.y1) {
          if (!journalOpen) toggleJournal();
        }
      }
    });
    canvas.addEventListener("mousemove", (ev) => {
      if (!objHit) return;
      const r = canvas.getBoundingClientRect();
      const cx = (ev.clientX - r.left) * canvas.width / r.width;
      const cy = (ev.clientY - r.top) * canvas.height / r.height;
      const over = cx >= objHit.x0 && cx <= objHit.x1 && cy >= objHit.y0 && cy <= objHit.y1;
      canvas.style.cursor = over ? "pointer" : "default";
    });
    canvas.setAttribute("tabindex", "0");
    canvas.focus();
    function debugEntity(id, areaId) {
      const ar = areas[areaId || (P && P.area)] || A;
      return ar ? ar.entities.find((e) => e.id === id) || null : null;
    }
    function debugArea(id, x, y) {
      if (!P || !areas[id]) return false;
      P.area = id;
      A = areas[id];
      applyConditionalSpawns(P.area);
      layout();
      P.x = Number.isFinite(x) ? x : A.spawn[0];
      P.y = Number.isFinite(y) ? y : A.spawn[1];
      updateTarget();
      return true;
    }
    function debugInventory(items) {
      (items || []).forEach(addInventory);
      updateTarget();
      return P.inventory.slice();
    }
    function debugFlags(flags) {
      (flags || []).forEach(addFlag);
      if (P && P.area) applyConditionalSpawns(P.area);
      updateTarget();
      return (P.story_flags || []).slice();
    }
    function debugOpen(id, areaId) {
      const e = debugEntity(id, areaId);
      if (!e) return false;
      e.state = "open";
      e.blocking = false;
      updateTarget();
      return true;
    }
    function debugFace(id) {
      const e = debugEntity(id);
      if (!e || !A) return false;
      const spots = [
        { x: e.x - 1, y: e.y, dir: "right" },
        { x: e.x + 1, y: e.y, dir: "left" },
        { x: e.x, y: e.y - 1, dir: "down" },
        { x: e.x, y: e.y + 1, dir: "up" },
      ];
      const spot = spots.find((p) => p.x >= 0 && p.y >= 0 && p.y < A.rows.length &&
        p.x < A.rows[0].length && WALK.has(A.rows[p.y][p.x]) &&
        !liveEntities().some((o) => o !== e && o.blocking && o.x === p.x && o.y === p.y));
      if (!spot) return false;
      P.x = spot.x; P.y = spot.y; facing = spot.dir;
      updateTarget();
      return true;
    }
    function debugSmoke() {
      const out = { current_area: P ? P.area : null, selecting, areas: {}, missing_sprites: [] };
      const startArea = W ? W.start_area : null;
      for (const [aid, ar] of Object.entries(areas || {})) {
        const ents = ar.entities || [];
        const portals = ents.filter((e) => e.type === "portal").map((e) => ({
          id: e.id, state: e.state, blocking: !!e.blocking, target_area: e.target_area,
          target_x: e.target_x, target_y: e.target_y, requires: (e.requires || []).slice(),
        }));
        out.areas[aid] = {
          size: [ar.width, ar.height],
          portals,
          locked: ents.filter((e) => e.state === "locked" || (e.requires || []).length)
            .map((e) => ({ id: e.id, type: e.type, state: e.state, requires: (e.requires || []).slice(), hint: e.hint || "" })),
          markers: ents.filter((e) => e.type === "map_marker")
            .map((e) => ({ id: e.id, name: e.name, x: e.x, y: e.y, hint: e.hint || "" })),
          npcs: ents.filter((e) => e.type === "npc")
            .map((e) => ({ id: e.id, name: e.name, state: e.state, blocking: !!e.blocking })),
          has_story: ents.some((e) => e.type === "story_object"),
          has_npc: ents.some((e) => e.type === "npc"),
          has_shrine: ents.some((e) => e.type === "shrine"),
          has_return: aid === startArea || portals.some((e) => e.target_area && e.target_area !== aid),
        };
      }
      ["hero_warrior", "hero_rogue", "hero_poison", "hero_hunter", "hero_barbarian",
        "hero_king", "water_rocks", "castle_blue", "black_castle", "goblin_house_destroyed"]
        .forEach((k) => { if (!spr(k)) out.missing_sprites.push(k); });
      return out;
    }
    function publishDebugState() {
      let el = $("rg-debug-state");
      if (!el) {
        el = document.createElement("script");
        el.id = "rg-debug-state";
        el.type = "application/json";
        document.body.appendChild(el);
      }
      const state = P && A ? {
        area: P.area, x: P.x, y: P.y, facing, hp: P.hp, courage: P.courage,
        world_seed: W ? W.world_seed : null, variation: W ? W.variation : null,
        selected: selected.slice(), target: (facedTarget() || {}).id || null,
        mastery_choice_open: masteryChoiceOpen,
        mastered: Object.keys(P.rune_mastery || {}).filter((r) => P.rune_mastery[r] >= 5),
        recent_story_events: (P.recent_story_events || []).slice(-3),
        last_cast_metadata: lastCastMetadata,
        selecting, over, toast: toastMsg, smoke: debugSmoke(),
      } : { selecting, ready: false, smoke: debugSmoke() };
      el.textContent = JSON.stringify(state);
    }
    // lightweight debug/test hook
    window.__rg = {
      state: () => ({ area: P.area, x: P.x, y: P.y, facing, hp: P.hp, courage: P.courage,
        score: P.score, inv: P.inventory.slice(), discoveries: P.discoveries.slice(),
        recent_story_events: (P.recent_story_events || []).slice(-3),
        last_cast_metadata: lastCastMetadata,
        trust: Object.assign({}, P.trust), over, toast: toastMsg,
        target: (facedTarget() || {}).id || null,
        cam: { OX, OY, TILE, cw: canvas.width, ch: canvas.height, cols: COLS, rows: ROWS,
               pscreenX: OX + P.x * TILE + TILE / 2, pscreenY: OY + P.y * TILE + TILE / 2 },
        entities: A.entities.map((e) => ({ id: e.id, type: e.type, x: e.x, y: e.y,
          hp: e.hp, state: e.state, blocking: e.blocking, requires: (e.requires || []).slice(),
          target_area: e.target_area || "" })) }),
      goto: (x, y, dir) => { P.x = x; P.y = y; if (dir) facing = dir; updateTarget(); },
      area: debugArea,
      entity: debugEntity,
      face: debugFace,
      open: debugOpen,
      travel: (id) => { const e = debugEntity(id); if (e && e.type === "portal" && e.state !== "locked") { travel(e); return true; } return false; },
      inventory: (...items) => debugInventory(items),
      give: (id, qty) => { addItem(id, qty == null ? 1 : qty); return Object.assign({}, P.items); },
      items: () => Object.assign({}, P.items || {}),
      quests: () => Object.assign({}, P.quests || {}),
      flags: (...flags) => debugFlags(flags),
      smoke: debugSmoke,
      start: (cls) => startGame(cls || "warrior"),
      selecting: () => selecting,
      prog: () => ({ level: P.level, xp: P.xp, xp_to_next: P.xp_to_next, weapon: P.weapon,
        gold: P.gold, evolved: P.evolved, flags: (P.story_flags || []).slice(),
        recent_story_events: (P.recent_story_events || []).slice(-3),
        class: P.goblin_class, four: P.four_rune_unlocked }),
      talk: (id) => { const e = byId(id); if (e) { e.quest ? questTalk(e) : openDialogue(e, []); } },
      journal: () => P.journal.slice(),
      pick: (...ks) => { selected = ks.slice(0, 4); renderPalette(); },
      pause: () => { paused = true; },
      resume: () => { if (paused) { paused = false; render(); } },
      sprites: () => Object.fromEntries(Object.entries(SPRITES).map(([k, s]) => [k, !!spr(k)])),
      vfxk: () => vfx.map((f) => f.kind),
      circles: () => CIRCLES ? { ready: !!(CIRCLES.img.complete && CIRCLES.img.naturalWidth), frames: CIRCLES.frames, n: CIRCLES.entries.length } : null,
    };
    window.__rgReady = true;
    setInterval(publishDebugState, 1000);
    publishDebugState();
  }

  function waitFor(sel, cb, n) {
    n = n || 0; const el = document.querySelector(sel);
    if (el) return cb();
    if (n > 100) return;
    setTimeout(() => waitFor(sel, cb, n + 1), 80);
  }

  waitFor("#rg-canvas", async () => {
    loadSprites();
    loadManifest();
    bootUI();
    await newGame();
    render();
  });
})();
