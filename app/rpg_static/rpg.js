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
  let busy = false, over = false, drawing = false;
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
  function layout() {
    COLS = A.width; ROWS = A.height;
    const availW = canvas.width - 8, availH = canvas.height - HUD_TOP - 8;
    TILE = Math.floor(Math.min(availW / COLS, availH / ROWS));
    OX = Math.floor((canvas.width - TILE * COLS) / 2);
    OY = HUD_TOP + Math.floor((canvas.height - HUD_TOP - TILE * ROWS) / 2);
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
    return e && e.blocking ? e : null;
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
      // bump: face it, surface hint
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

    spawnVfx(s, target, runes);

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

  function spawnVfx(s, target, runes) {
    const [color, glyph] = school(runes || []);
    const dmg = -(s.enemy_hp_delta || 0), heal = Math.max(0, s.player_hp_delta || 0);
    const tgtPos = target ? tileCenter(target) : playerCenter();
    vfx.push({
      t0: now(), dur: 760 + 40 * (s.chaos || 0), color, glyph,
      from: playerCenter(), to: tgtPos, dmg, heal,
      shieldy: (s.status_effects || []).includes("player_shielded"),
      particles: 8 + (s.chaos || 0),
      shakeTarget: target && dmg > 0 ? target.id : null,
    });
  }
  function spawnHit() { vfx.push({ t0: now(), dur: 420, color: "#ff5d73", glyph: "", from: playerCenter(), to: playerCenter(), dmg: 0, heal: 0, hit: true, particles: 0 }); }

  // ---- rendering ----
  function drawTiles() {
    const b = BIOME[A.biome] || DEFAULT_BIOME;
    for (let y = 0; y < ROWS; y++) {
      for (let x = 0; x < COLS; x++) {
        const ch = A.rows[y][x];
        let col;
        if (ch === "#") col = b.wall;
        else if (ch === "~") col = HAZARD;
        else if (ch === " ") col = "#070510";
        else col = ((x + y) % 2 === 0) ? b.floor : b.alt;
        ctx.fillStyle = col;
        ctx.fillRect(sx(x), sy(y), TILE, TILE);
        if (ch === "#") {
          ctx.fillStyle = b.edge;
          ctx.fillRect(sx(x), sy(y) + TILE - 4, TILE, 4);
        }
      }
    }
  }

  function drawEntity(e) {
    let [cx, cy] = tileCenter(e);
    // shake if currently being hit
    const sh = vfx.find((f) => f.shakeTarget === e.id && now() - f.t0 < 360);
    if (sh) { const p = (now() - sh.t0) / 360; cx += Math.sin(p * 40) * (6 * (1 - p)); }
    ctx.font = Math.floor(TILE * 0.7) + "px serif";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    let glyph = e.sprite;
    if (e.type === "chest" && e.state === "open") glyph = "📭";
    if ((e.type === "locked_door" || (e.type === "portal" && e.state === "locked"))) {
      // draw door/portal then a lock badge
    }
    ctx.fillText(glyph, cx, cy);
    // lock badge
    if (e.state === "locked") {
      ctx.font = Math.floor(TILE * 0.32) + "px serif";
      ctx.fillText("🔒", cx + TILE * 0.26, cy - TILE * 0.24);
    }
    // enemy HP bar
    if ((e.type === "enemy" || e.type === "boss") && e.hp > 0) {
      const w = TILE * 0.8, h = 5, bx = cx - w / 2, by = sy(e.y) + 2;
      ctx.fillStyle = "#000"; ctx.fillRect(bx - 1, by - 1, w + 2, h + 2);
      ctx.fillStyle = "#3a1020"; ctx.fillRect(bx, by, w, h);
      ctx.fillStyle = e.type === "boss" ? "#ffd24a" : "#ff5d73";
      ctx.fillRect(bx, by, w * clamp(e.hp / e.max_hp, 0, 1), h);
    }
  }

  function drawPlayer() {
    const [cx, cy] = playerCenter();
    ctx.font = Math.floor(TILE * 0.7) + "px serif";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText("🧙", cx, cy);
    // facing pip
    const v = DIRV[facing];
    ctx.fillStyle = "#ffd24a";
    ctx.beginPath();
    ctx.arc(cx + v[0] * TILE * 0.34, cy + v[1] * TILE * 0.34, 3, 0, 7);
    ctx.fill();
  }

  function drawVfx() {
    const keep = [];
    for (const f of vfx) {
      const t = now() - f.t0, p = t / f.dur;
      if (p >= 1) continue;
      keep.push(f);
      if (f.hit) {
        ctx.fillStyle = "rgba(255,80,90," + (0.4 * (1 - p)) + ")";
        ctx.fillRect(0, HUD_TOP, canvas.width, canvas.height - HUD_TOP);
        continue;
      }
      // flash
      ctx.save();
      ctx.globalAlpha = 0.35 * (1 - p);
      ctx.fillStyle = f.color;
      ctx.fillRect(0, HUD_TOP, canvas.width, canvas.height - HUD_TOP);
      ctx.restore();
      // projectile
      const px = f.from[0] + (f.to[0] - f.from[0]) * Math.min(1, p * 1.4);
      const py = f.from[1] + (f.to[1] - f.from[1]) * Math.min(1, p * 1.4);
      ctx.font = Math.floor(TILE * 0.6) + "px serif";
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.globalAlpha = 1;
      ctx.fillText(f.glyph, px, py);
      // particles at target
      if (p > 0.35) {
        const n = f.particles;
        for (let i = 0; i < n; i++) {
          const a = (i / n) * Math.PI * 2;
          const r = TILE * 0.9 * (p - 0.35) / 0.65;
          ctx.fillStyle = f.color;
          ctx.globalAlpha = 1 - p;
          ctx.beginPath();
          ctx.arc(f.to[0] + Math.cos(a) * r, f.to[1] + Math.sin(a) * r, 3, 0, 7);
          ctx.fill();
        }
        ctx.globalAlpha = 1;
      }
      // floating number
      if (f.dmg > 0 || f.heal > 0) {
        const txt = f.dmg > 0 ? "-" + f.dmg : "+" + f.heal;
        ctx.fillStyle = f.dmg > 0 ? "#ff5d73" : "#6df5a0";
        ctx.font = 'bold ' + Math.floor(TILE * 0.5) + 'px "Press Start 2P", monospace';
        ctx.globalAlpha = 1 - p;
        ctx.fillText(txt, f.to[0], f.to[1] - TILE * 0.6 - p * 24);
        ctx.globalAlpha = 1;
      }
    }
    vfx = keep;
  }

  function drawHud() {
    ctx.fillStyle = "rgba(16,10,26,0.9)";
    ctx.fillRect(0, 0, canvas.width, HUD_TOP);
    ctx.fillStyle = "#34254d"; ctx.fillRect(0, HUD_TOP - 2, canvas.width, 2);
    ctx.textBaseline = "middle"; ctx.textAlign = "left";
    // hearts
    ctx.font = '16px serif';
    let hx = 12;
    ctx.fillStyle = "#ff5d73";
    ctx.fillText("❤", hx, HUD_TOP / 2); hx += 20;
    ctx.font = '12px "Press Start 2P", monospace';
    ctx.fillStyle = "#e7d9ff";
    ctx.fillText(P.hp + "/" + P.max_hp, hx, HUD_TOP / 2); hx += 70;
    ctx.fillStyle = "#ffd24a"; ctx.fillText("⚡" + P.courage, hx, HUD_TOP / 2); hx += 60;
    ctx.fillStyle = "#6df5a0"; ctx.fillText("★" + P.score, hx, HUD_TOP / 2); hx += 90;
    ctx.fillStyle = "#9c8bc4";
    ctx.fillText("🎒" + P.inventory.length, hx, HUD_TOP / 2);
    // area name centred
    ctx.textAlign = "center"; ctx.fillStyle = "#b07cff";
    ctx.fillText(A.name.toUpperCase(), canvas.width / 2, HUD_TOP / 2);
  }

  function render() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#0b0810"; ctx.fillRect(0, 0, canvas.width, canvas.height);
    drawTiles();
    liveEntities().forEach(drawEntity);
    drawPlayer();
    drawVfx();
    drawHud();
    requestAnimationFrame(render);
  }

  // ---- palette / DOM ----
  function renderPalette() {
    const sel = $("rg-sel");
    if (sel) sel.innerHTML = selected.length
      ? selected.map((k) => runeSym(k)).join(" + ")
      : "no runes";
    document.querySelectorAll(".rg-rune").forEach((b) => {
      b.classList.toggle("on", selected.includes(b.dataset.rune));
    });
  }
  function runeSym(k) { const r = runesMeta.find((x) => x.key === k); return r ? r.symbol + r.label : k; }

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
      b.innerHTML = (i < 9 ? "<span class='num'>" + (i + 1) + "</span>" : "") + r.symbol;
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

  function bootUI() {
    canvas = $("rg-canvas"); ctx = canvas.getContext("2d");
    setupSketch();
    $("rg-boot").style.display = "none";
    $("rg-cast").onclick = () => { castRunes(); canvas.focus(); };
    $("rg-draw-open").onclick = () => { openDraw(); };
    $("rg-clear").onclick = () => { selected = []; renderPalette(); canvas.focus(); };
    $("rg-reset").onclick = () => { newGame(); canvas.focus(); };
    $("rg-draw-cast").onclick = castDrawing;
    $("rg-draw-clear").onclick = clearSketch;
    $("rg-draw-cancel").onclick = closeDraw;
    $("rg-end-restart").onclick = () => { newGame(); canvas.focus(); };
    window.addEventListener("keydown", onKey);
    canvas.addEventListener("click", () => canvas.focus());
    canvas.setAttribute("tabindex", "0");
    canvas.focus();
    // lightweight debug/test hook
    window.__rg = {
      state: () => ({ area: P.area, x: P.x, y: P.y, facing, hp: P.hp, courage: P.courage,
        score: P.score, inv: P.inventory.slice(), over,
        target: (facedTarget() || {}).id || null,
        entities: A.entities.map((e) => ({ id: e.id, x: e.x, y: e.y, hp: e.hp, state: e.state })) }),
      goto: (x, y, dir) => { P.x = x; P.y = y; if (dir) facing = dir; updateTarget(); },
      pick: (...ks) => { selected = ks.slice(0, 4); renderPalette(); },
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
    bootUI();
    await newGame();
    render();
  });
})();
