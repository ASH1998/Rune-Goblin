// Rune Goblin RPG — client-side canvas game.
// Movement, rendering and exploration run here; casting round-trips to the
// Python bridge (/rg/cast) so the engine + goblinV1 vision model stay the
// spell authority.
(function () {
  "use strict";

  // ---- state ----
  let W = null;                 // world payload from /rg/world
  let areas = {};               // mutable per-area state (entities/rows)
  let runesMeta = [];           // [{key,symbol,label,meanings}]
  let P = null;                 // player {area,x,y,hp,max_hp,courage,...}
  let A = null;                 // current area
  let selected = [];            // selected rune keys (quick-cast)
  let facing = "down";
  let busy = false, over = false, drawing = false, paused = false;
  let toastMsg = "";
  let vfx = [];                 // active visual effects

  let canvas, ctx, sketch, sctx;
  let TILE = 40, OX = 0, OY = 40, COLS = 20, ROWS = 13;
  const HUD_TOP = 42;

  const DIRV = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };
  const WALK = new Set([".", ","]);

  const BIOME = {
    toll_road: { floor: "#2e2415", alt: "#352a18", wall: "#6b5430", edge: "#46371d" },
    cavern:    { floor: "#13232a", alt: "#163038", wall: "#2c4e58", edge: "#1d3b42" },
    library:   { floor: "#1a2230", alt: "#202a3c", wall: "#34465e", edge: "#222f44" },
    arena:     { floor: "#2a1230", alt: "#331640", wall: "#5a2a66", edge: "#3d1c47" },
  };
  const DEFAULT_BIOME = { floor: "#1a1426", alt: "#211a30", wall: "#4a3a6b", edge: "#2a1f3d" };
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
    water: { src: "water.png", tile: true },
    player: { src: "player.png", fw: 192, fh: 192, frames: 8, anim: true, scale: 1.6 },
    npc_pawn: { src: "npc_pawn.png", fw: 192, fh: 192, frames: 8, anim: true, scale: 1.4 },
    npc_monk: { src: "npc_monk.png", fw: 192, fh: 192, frames: 6, anim: true, scale: 1.4 },
    goblin_red: { src: "goblin_red.png", fw: 192, fh: 192, frames: 7, anim: true, scale: 1.4 },
    goblin_blue: { src: "goblin_blue.png", fw: 192, fh: 192, frames: 7, anim: true, scale: 1.4 },
    goblin_purple: { src: "goblin_purple.png", fw: 192, fh: 192, frames: 7, anim: true, scale: 1.8 },
    goblin_yellow: { src: "goblin_yellow.png", fw: 192, fh: 192, frames: 7, anim: true, scale: 1.35 },
    chest_gold: { src: "chest_gold.png", fw: 128, fh: 128, frames: 1, scale: 1.0 },
    shrine_tower: { src: "shrine_tower.png", fw: 128, fh: 256, frames: 1, scale: 1.4 },
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
        scale: k === "tree" ? 1.5 : big ? 1.5 : tall ? 1.25 : 0.95 };
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

  function toast(msg) { toastMsg = msg; const t = $("rg-toast"); if (t) t.innerHTML = msg; }

  function school(runes) {
    for (const k of Object.keys(SCHOOL)) {
      if (runes.includes(k) && !(k === "broken_mark" && runes.length > 1)) return SCHOOL[k];
    }
    return ["#b07cff", "✨"];
  }

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
  function liveEntities() { return A.entities.filter((e) => e.state !== "defeated" && e.state !== "collected"); }
  function entityAt(x, y) { return liveEntities().find((e) => e.x === x && e.y === y); }
  function byId(id) { return A.entities.find((e) => e.id === id); }
  function facedTile() { const v = DIRV[facing]; return [P.x + v[0], P.y + v[1]]; }
  function facedTarget() {
    const [fx, fy] = facedTile();
    const e = entityAt(fx, fy);
    return e && e.blocking && e.type !== "deco" ? e : null;
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
      toast("<b>" + e.name + "</b> — " + (e.hint || (e.dialogue || "")));
      updateTarget(); return;
    }
    P.x = nx; P.y = ny;
    if (e && !e.blocking) {
      if (e.type === "portal" && e.state !== "locked") travel(e);
      else if (e.type === "powerup") collect(e);
    }
    updateTarget();
  }

  function travel(portal) {
    P.area = portal.target_area;
    A = areas[P.area];
    layout();
    P.x = portal.target_x; P.y = portal.target_y;
    toast("You enter <b>" + A.name + "</b>. " + moodLine());
  }

  function collect(e) {
    e.state = "collected";
    (e.loot || []).forEach((it) => P.inventory.push(it));
    P.score += 25;
    toast("Picked up <b>" + (e.loot.join(", ") || e.name) + "</b>.");
  }

  function moodLine() { return "<i>" + A.mood + "</i>"; }

  function updateTarget() {
    const t = facedTarget();
    const el = $("rg-target");
    if (!el) return;
    if (t) {
      let extra = "";
      if (t.type === "enemy" || t.type === "boss") extra = " · " + t.hp + "/" + t.max_hp + " HP · weak " + (t.weakness || []).join("/");
      else if (t.requires && t.requires.length && t.state === "locked") extra = " · needs " + t.requires.join("+");
      el.innerHTML = "🎯 " + t.name + extra;
    } else {
      el.innerHTML = "🎯 (nothing — cast into the air)";
    }
  }

  // ---- casting ----
  function playerCtx() {
    return { hp: P.hp, max_hp: P.max_hp, courage: P.courage, max_courage: P.max_courage,
             inventory: P.inventory.slice(), statuses: P.statuses.slice() };
  }
  function targetCtx(t) {
    if (!t) return null;
    return { id: t.id, type: t.type, name: t.name, hp: t.hp, max_hp: t.max_hp,
             weakness: t.weakness, resistance: t.resistance, state: t.state,
             requires: t.requires, tags: t.tags, mood: t.mood, loot: t.loot };
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
      applyCast(res, target, extra);
    } catch (e) { toast("Drawing cast failed: " + e); }
    busy = false;
  }

  function applyCast(res, target, extra) {
    const s = res.spell || {};
    const runes = res.runes || selected;
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
        case "add_inventory": P.inventory.push(a.item); break;
        case "remove_inventory": { const i = P.inventory.indexOf(a.item); if (i >= 0) P.inventory.splice(i, 1); } break;
        case "heal_player": P.hp = clamp(P.hp + a.amount, 0, P.max_hp); break;
        case "add_courage": P.courage = clamp(P.courage + a.amount, 0, P.max_courage); break;
        case "change_npc_trust": break;
        case "win_game": win(); break;
        default: break;
      }
    });
    P.score += Math.max(0, -(s.enemy_hp_delta || 0)) * 10 + (s.chaos || 0);

    spawnSpellVfx(s, target, runes);

    if (!over) {
      let line = "<b>" + (s.spell_name || "Spell") + "</b> — " + (s.effect || "");
      if (s.side_effect) line += " <span style='color:#ffce6b'>⚠ " + s.side_effect + "</span>";
      if (extra) line += extra;
      toast(line);
    }

    // enemy retaliation if it survived
    if (!over && target && (target.type === "enemy" || target.type === "boss") && !defeated) {
      retaliate(target, s.status_effects || []);
    }
    updateTarget();
    if (P.hp <= 0 && !over) lose();
  }

  function retaliate(enemy, statuses) {
    const skip = ["enemy_confused", "enemy_soothed", "enemy_bound"].some((x) => statuses.includes(x));
    if (skip) { setTimeout(() => toast(enemy.name + " fumbles its turn."), 650); return; }
    let dmg = enemy.type === "boss" ? 3 : (P.area === "arena" ? 2 : 1);
    if (statuses.includes("player_shielded")) {
      setTimeout(() => toast("Your shield absorbs " + enemy.name + "'s blow."), 650); return;
    }
    setTimeout(() => {
      P.hp = clamp(P.hp - dmg, 0, P.max_hp);
      spawnHit();
      toast(enemy.name + " strikes back for " + dmg + "!");
      if (P.hp <= 0 && !over) lose();
    }, 650);
  }

  // ---- win / lose ----
  function endScreen(cls, title, sub) {
    over = true;
    const el = $("rg-end");
    el.className = "rg-end open " + cls;
    $("rg-end-title").textContent = title;
    $("rg-end-sub").innerHTML = sub;
  }
  function win() { endScreen("win", "🏆 THE BEAST FALLS", "You broke the Calendar.<br>Final score: " + P.score); }
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
  function spawnSpellVfx(s, target, runes) {
    runes = runes || [];
    const el = elementOf(runes), cfg = ELEM_VFX[el] || ELEM_VFX.light;
    const t = spellTier(s, runes);
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
    if (heal > 0) addAnim("holy", pc[0], pc[1] - 0.2, 1.1, 0);
    if ((s.status_effects || []).includes("player_shielded")) addAnim("barrier", pc[0], pc[1] - 0.2, 1.3, 0);
    if (dmg > 0) { addNum("-" + dmg, "#ff5d73", tc[0], tc[1] - 0.6, 110 + travel); shakeAmt = Math.max(shakeAmt, Math.min(0.55, 0.12 + dmg * 0.06)); }
    else if (heal > 0) addNum("+" + heal, "#6df5a0", pc[0], pc[1] - 0.6, 0);
    playSfx(cfg.sound, t);
  }
  function spawnHit() { vfx.push({ kind: "hit", start: now(), dur: 360 }); shakeAmt = Math.max(shakeAmt, 0.35); }

  // ---- rendering ----
  function drawTiles() {
    const b = BIOME[A.biome] || DEFAULT_BIOME;
    const haveTiles = spr("grass") && spr("water");
    const x0 = clamp(Math.floor((0 - OX) / TILE), 0, COLS - 1);
    const x1 = clamp(Math.ceil((canvas.width - OX) / TILE), 0, COLS - 1);
    const y0 = clamp(Math.floor((HUD_TOP - OY) / TILE), 0, ROWS - 1);
    const y1 = clamp(Math.ceil((canvas.height - OY) / TILE), 0, ROWS - 1);
    for (let y = y0; y <= y1; y++) {
      for (let x = x0; x <= x1; x++) {
        const ch = A.rows[y][x];
        const walk = WALK.has(ch);
        const px = sx(x), py = sy(y);
        if (haveTiles) {
          drawTileSprite(walk ? "grass" : "water", px, py);
          if (ch === "~") { ctx.fillStyle = "rgba(120,40,60,0.25)"; ctx.fillRect(px, py, TILE, TILE); }
        } else {
          let col;
          if (ch === "#") col = b.wall;
          else if (ch === "~") col = HAZARD;
          else if (ch === " ") col = "#070510";
          else col = ((x + y) % 2 === 0) ? b.floor : b.alt;
          ctx.fillStyle = col; ctx.fillRect(px, py, TILE, TILE);
          if (ch === "#") { ctx.fillStyle = b.edge; ctx.fillRect(px, py + TILE - 4, TILE, 4); }
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
    }
  }

  function drawPlayer() {
    const cx = sx(P.x) + TILE / 2, cy = sy(P.y) + TILE / 2, baseY = sy(P.y) + TILE * 0.98;
    const fi = (now() / 140) | 0;
    let drew = false;
    if (spr("player")) {
      ctx.save();
      if (facing === "left") { ctx.translate(cx * 2, 0); ctx.scale(-1, 1); }
      drew = drawUnitSprite("player", cx, baseY, null, fi);
      ctx.restore();
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
    const cy = HUD_TOP / 2;
    ctx.fillStyle = "#ff5d73"; ctx.fillText("HP " + P.hp + "/" + P.max_hp, hx, cy); hx += 150;
    ctx.fillStyle = "#ffd24a"; ctx.fillText("CR " + P.courage, hx, cy); hx += 90;
    ctx.fillStyle = "#6df5a0"; ctx.fillText("SCORE " + P.score, hx, cy); hx += 150;
    ctx.fillStyle = "#9c8bc4"; ctx.fillText("BAG " + P.inventory.length, hx, cy);
    ctx.textAlign = "right"; ctx.fillStyle = "#b07cff";
    ctx.fillText(A.name.toUpperCase(), canvas.width - 14, cy);
  }

  function render() {
    if (paused) return;
    fitCanvas();
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
    drawHud();
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
    else if (selected.length < 4) selected.push(k);
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
    if (drawing) { if (k === "escape") closeDraw(); return; }
    if (over) return;
    if (["arrowup", "w"].includes(k)) { tryMove("up"); ev.preventDefault(); }
    else if (["arrowdown", "s"].includes(k)) { tryMove("down"); ev.preventDefault(); }
    else if (["arrowleft", "a"].includes(k)) { tryMove("left"); ev.preventDefault(); }
    else if (["arrowright", "d"].includes(k)) { tryMove("right"); ev.preventDefault(); }
    else if (k === " " || k === "enter") { castRunes(); ev.preventDefault(); }
    else if (k === "e") { openDraw(); ev.preventDefault(); }
    else if (k === "c") { selected = []; renderPalette(); }
    else if (k >= "1" && k <= "9") { const idx = parseInt(k, 10) - 1; if (runesMeta[idx]) toggleRune(runesMeta[idx].key); }
  }

  // ---- boot ----
  async function newGame() {
    if (!W) W = await api("/rg/world");
    runesMeta = W.runes;
    areas = JSON.parse(JSON.stringify(W.areas));
    P = JSON.parse(JSON.stringify(W.player));
    P.area = W.start_area;
    A = areas[P.area];
    const sp = A.spawn; P.x = sp[0]; P.y = sp[1];
    facing = "down"; selected = []; vfx = []; over = false; busy = false;
    $("rg-end").className = "rg-end";
    layout(); buildPalette(); renderPalette(); updateTarget();
    toast("You wake on the <b>Goblin Toll Road</b>. " + moodLine() + " — roam and cast.");
  }

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
    window.addEventListener("keydown", (e) => { gesture(); onKey(e); });
    canvas.addEventListener("click", () => { gesture(); canvas.focus(); });
    canvas.setAttribute("tabindex", "0");
    canvas.focus();
    // lightweight debug/test hook
    window.__rg = {
      state: () => ({ area: P.area, x: P.x, y: P.y, facing, hp: P.hp, courage: P.courage,
        score: P.score, inv: P.inventory.slice(), over,
        target: (facedTarget() || {}).id || null,
        cam: { OX, OY, TILE, cw: canvas.width, ch: canvas.height, cols: COLS, rows: ROWS,
               pscreenX: OX + P.x * TILE + TILE / 2, pscreenY: OY + P.y * TILE + TILE / 2 },
        entities: A.entities.map((e) => ({ id: e.id, x: e.x, y: e.y, hp: e.hp, state: e.state })) }),
      goto: (x, y, dir) => { P.x = x; P.y = y; if (dir) facing = dir; updateTarget(); },
      pick: (...ks) => { selected = ks.slice(0, 4); renderPalette(); },
      pause: () => { paused = true; },
      resume: () => { if (paused) { paused = false; render(); } },
      sprites: () => Object.fromEntries(Object.entries(SPRITES).map(([k, s]) => [k, !!spr(k)])),
      vfxk: () => vfx.map((f) => f.kind),
      circles: () => CIRCLES ? { ready: !!(CIRCLES.img.complete && CIRCLES.img.naturalWidth), frames: CIRCLES.frames, n: CIRCLES.entries.length } : null,
    };
    window.__rgReady = true;
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
