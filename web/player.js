/* ============================================================
 *  player.js — ブラウザ版プレイヤー UI（DOM）
 * ------------------------------------------------------------
 *  window.GAME_DATA（プロジェクト）と NovelEngine を用いて
 *  ノベルゲームを再生する。セーブは localStorage の10スロット。
 * ============================================================ */
(function () {
  "use strict";

  const DATA = window.GAME_DATA;
  if (!DATA) { document.body.innerHTML = "ゲームデータが見つかりません。"; return; }
  document.title = (DATA.meta && DATA.meta.title) || "ノベルゲーム";

  // システムデータ（全体共有・永続）: localStorage に保存
  const SYS_KEY = "novelmaker_system_" + (DATA.meta.title || "game");
  let systemData;
  try {
    systemData = JSON.parse(localStorage.getItem(SYS_KEY)) || { vars: {}, endings: {} };
  } catch (e) { systemData = { vars: {}, endings: {} }; }
  systemData.vars = systemData.vars || {};
  systemData.endings = systemData.endings || {};
  function persistSystem() {
    try { localStorage.setItem(SYS_KEY, JSON.stringify(systemData)); } catch (e) {}
  }
  const rt = new window.NovelEngine.Runtime(DATA, systemData, persistSystem);

  // 索引
  const byId = (list) => Object.fromEntries((list || []).map((e) => [e.id, e]));
  const chars = byId(DATA.characters), bgs = byId(DATA.backgrounds),
        items = byId(DATA.items), bgms = byId(DATA.bgm),
        ses = byId(DATA.se || []), cgs = byId(DATA.cg || []);

  // DOM
  const $ = (id) => document.getElementById(id);
  const elBg = $("bg"), elChar = $("char"), elCg = $("cg"), elBlackout = $("blackout"),
        elGauges = $("gauges"), elMsgWin = $("msgwin"), elName = $("msg-name"),
        elText = $("msg-text"), elNext = $("msg-next"), elChoices = $("choices");

  let current = null, fullText = "", shown = 0, typing = false, typeTimer = null;
  let titleMode = false;
  const SAVE_KEY = "novelmaker_save_" + (DATA.meta.title || "game");

  // BGM
  let audio = null, curBgm = null;

  // ---------------- 提示 ----------------
  function present(ev) {
    current = ev;
    updateStage();
    (ev.sfx || []).forEach(playSe);   // 効果音
    elChoices.style.display = "none";
    if (ev.kind !== "endroll") {      // エンドロール解除・UI復帰
      stopEndroll();
      if (!titleMode) { $("items-btn").style.display = ""; $("menu").style.display = "flex"; }
    }
    if (ev.kind === "endroll") { startEndroll(ev.text || "", ev.speed || 60); return; }
    hideOverlay("ov-name"); // 入力以外では閉じる前提

    const k = ev.kind;
    if (k === "say" || k === "narrate") {
      elMsgWin.style.display = "";
      if (k === "say") {
        elName.textContent = ev.name || "";
        elName.style.color = ev.color || "#fff";
        elName.style.visibility = ev.name ? "visible" : "hidden";
      } else {
        elName.style.visibility = "hidden";
        elName.textContent = "";
      }
      typewrite(ev.text || "");
    } else if (k === "choice") {
      if (ev.prompt) {
        elMsgWin.style.display = "";
        elName.style.visibility = "hidden";
        typewrite(ev.prompt);
      } else {
        elMsgWin.style.display = "none";
      }
      showChoices(ev);
    } else if (k === "nameInput") {
      $("name-prompt").textContent = ev.prompt || "名前を入力";
      $("name-field").value = "";
      showOverlay("ov-name");
      $("name-field").focus();
    } else if (k === "itemGet") {
      showItemGet(ev);
    } else if (k === "ending") {
      showEnding(ev);
    } else if (k === "end") {
      elMsgWin.style.display = "";
      elName.style.visibility = "hidden";
      typewrite("― おわり ―");
    }
  }

  // ---------------- タイプライタ ----------------
  function typewrite(text) {
    fullText = text; shown = 0; typing = true; elText.textContent = "";
    elNext.style.display = "none";
    clearInterval(typeTimer);
    typeTimer = setInterval(() => {
      shown++;
      if (shown >= fullText.length) { finishType(); }
      else { elText.textContent = fullText.slice(0, shown); }
    }, 22);
  }
  function finishType() {
    clearInterval(typeTimer); typing = false;
    elText.textContent = fullText; elNext.style.display = "";
  }

  function onAdvance() {
    if (!current) return;
    const k = current.kind;
    if (k !== "say" && k !== "narrate" && k !== "end") return;
    if (typing) { finishType(); return; }
    if (k === "end") return;
    present(rt.advance());
  }

  // ---------------- 選択肢 ----------------
  function showChoices(ev) {
    elChoices.innerHTML = "";
    (ev.options || []).forEach((opt) => {
      const b = document.createElement("button");
      b.className = "choice-btn"; b.textContent = opt.text;
      b.onclick = () => { elChoices.style.display = "none"; present(rt.choose(opt.index)); };
      elChoices.appendChild(b);
    });
    if (!ev.options.length) {
      const b = document.createElement("button");
      b.className = "choice-btn"; b.textContent = "続ける";
      b.onclick = () => present(rt.choose(-1));
      elChoices.appendChild(b);
    }
    elChoices.style.display = "flex";
  }

  // ---------------- 名前入力 ----------------
  function submitName() {
    const v = ($("name-field").value || "").trim() || "名無し";
    hideOverlay("ov-name");
    present(rt.advance(v));
  }

  // ---------------- アイテム入手/使用 ----------------
  function showItemGet(ev) {
    $("itemget-verb").textContent =
      ev.verb === "use" ? `「${ev.name}」を使った` : `「${ev.name}」を手に入れた`;
    const ic = $("itemget-icon");
    if (ev.image) ic.innerHTML = `<img src="${ev.image}" alt="">`;
    else ic.textContent = ev.icon || "📦";
    $("itemget-name").textContent = ev.name || "";
    $("itemget-desc").textContent = ev.desc || "";
    showOverlay("ov-itemget");
  }
  function closeItemGet() {
    hideOverlay("ov-itemget");
    present(rt.advance());
  }

  // ---------------- エンディング ----------------
  function showEnding(ev) {
    elMsgWin.style.display = "none";
    const badge = $("ending-badge");
    if (ev.hidden) { badge.textContent = "🔒 裏エンディング 🔒"; badge.style.color = "#ffd56b"; }
    else { badge.textContent = "★ ENDING ★"; badge.style.color = "#9fe3ff"; }
    $("ending-name").textContent =
      (ev.name || "") + (ev.count > 1 ? `　（${ev.count}回目）` : "");
    $("ending-desc").textContent = ev.desc || "";
    showOverlay("ov-ending");
  }

  // ---------------- ステージ描画 ----------------
  function updateStage() {
    const st = rt.state;
    // 背景
    const bg = bgs[st.bg_id];
    if (bg && bg.image) {
      elBg.style.backgroundImage = `url("${bg.image}")`;
      elBg.style.backgroundColor = bg.color || "#101018";
    } else if (bg) {
      elBg.style.backgroundImage = "none";
      elBg.style.backgroundColor = bg.color || "#222244";
    } else {
      elBg.style.backgroundImage = "none";
      elBg.style.backgroundColor = "#101018";
    }

    // 立ち絵
    elChar.innerHTML = "";
    if (!st.blackout && st.char_id) {
      const ch = chars[st.char_id];
      let ex = ch && (ch.expressions || []).find((e) => e.id === st.expr_id);
      if (ch && !ex && (ch.expressions || []).length) ex = ch.expressions[0];
      if (ex && ex.image) {
        const img = document.createElement("img");
        img.src = ex.image; elChar.appendChild(img);
      } else if (ch) {
        const ph = document.createElement("div");
        ph.className = "char-ph";
        ph.style.background = hexA(ch.color || "#888", 0.28);
        ph.style.border = "2px solid " + (ch.color || "#888");
        ph.textContent = ch.name + (ex ? `\n（${ex.name}）` : "");
        elChar.appendChild(ph);
      }
    }

    // CG（背景・立ち絵の上、全画面）
    const cg = cgs[st.cg_id];
    if (st.cg_id && cg) {
      if (cg.image) {
        elCg.style.backgroundImage = `url("${cg.image}")`;
        elCg.textContent = "";
      } else {
        elCg.style.backgroundImage = "none";
        elCg.style.backgroundColor = cg.color || "#000";
        elCg.textContent = "［CG］" + (cg.name || "");
      }
      elCg.style.display = "flex";
    } else {
      elCg.style.display = "none";
    }

    // 暗転
    elBlackout.classList.toggle("on", !!st.blackout);

    updateGauges();
    updateBgm();
  }

  // ---------------- エンドロール ----------------
  let endrollTimer = null, endrollY = 0, endrollSpeed = 60;
  function startEndroll(text, speed) {
    setGameChrome(false);
    elGauges.style.display = "none";
    const wrap = $("endroll"), t = $("endroll-text");
    t.textContent = text;
    wrap.classList.remove("hidden");
    endrollSpeed = Math.max(10, speed || 60);
    endrollY = wrap.clientHeight;        // 画面下端から開始
    t.style.top = endrollY + "px";
    let last = performance.now();
    clearInterval(endrollTimer);
    endrollTimer = setInterval(() => {
      const now = performance.now(), dt = (now - last) / 1000; last = now;
      endrollY -= endrollSpeed * dt;
      t.style.top = endrollY + "px";
      if (endrollY + t.offsetHeight < 0) finishEndroll();
    }, 16);
  }
  function stopEndroll() {
    clearInterval(endrollTimer); endrollTimer = null;
    $("endroll").classList.add("hidden");
  }
  function finishEndroll() { stopEndroll(); present(rt.advance()); }
  function skipEndroll() {
    if (!$("endroll").classList.contains("hidden")) finishEndroll();
  }

  // ---------------- SE（効果音） ----------------
  function playSe(seId) {
    const track = ses[seId];
    if (!track || !track.path) return;
    try {
      const a = new Audio(track.path);
      a.volume = 0.9;
      const p = a.play(); if (p && p.catch) p.catch(() => {});
    } catch (e) {}
  }

  function updateGauges() {
    elGauges.innerHTML = "";
    let shownAny = false;
    (DATA.gauges || []).forEach((g) => {
      if (g.show === false) return;
      shownAny = true;
      const val = rt.state.gauges[g.id] !== undefined ? rt.state.gauges[g.id] : (g.initial || 0);
      const lo = +g.min || 0, hi = +g.max || 100;
      const ratio = hi <= lo ? 0 : Math.max(0, Math.min(1, (val - lo) / (hi - lo)));
      const wrap = document.createElement("div");
      wrap.className = "gauge";
      const disp = (val === Math.round(val)) ? val : Math.round(val * 10) / 10;
      wrap.innerHTML =
        `<div class="gauge-label">${esc(g.name)}: ${disp}</div>` +
        `<div class="gauge-track"><div class="gauge-fill" style="width:${ratio * 100}%;background:${g.color || "#4cc2ff"}"></div></div>`;
      elGauges.appendChild(wrap);
    });
    elGauges.style.display = shownAny ? "" : "none";
  }

  // ---------------- BGM（フェード対応） ----------------
  const BGM_VOL = 0.7;
  function rampVolume(el, from, to, ms, onDone) {
    if (!el) { if (onDone) onDone(); return; }
    const steps = Math.max(1, Math.round(ms / 40));
    let i = 0;
    el.volume = Math.max(0, Math.min(1, from));
    const iv = setInterval(() => {
      i++;
      const v = from + (to - from) * (i / steps);
      try { el.volume = Math.max(0, Math.min(1, v)); } catch (e) {}
      if (i >= steps) { clearInterval(iv); if (onDone) onDone(); }
    }, 40);
  }
  function setBgm(bgmId, fadeMs) {
    if (bgmId === curBgm) return;
    curBgm = bgmId;
    const fade = fadeMs || 0;
    const old = audio;
    if (!bgmId) {
      if (old) {
        if (fade > 0) rampVolume(old, old.volume, 0, fade, () => old.pause());
        else old.pause();
      }
      audio = null;
      return;
    }
    const track = bgms[bgmId];
    if (!track || !track.path) { if (old) old.pause(); audio = null; return; }
    try {
      const a = new Audio(track.path);
      a.loop = track.loop !== false;
      if (fade > 0) {
        a.volume = 0;
        const p = a.play(); if (p && p.catch) p.catch(() => {});
        rampVolume(a, 0, BGM_VOL, fade);
        if (old) rampVolume(old, old.volume, 0, fade, () => old.pause());
      } else {
        a.volume = BGM_VOL;
        const p = a.play(); if (p && p.catch) p.catch(() => {});
        if (old) old.pause();
      }
      audio = a;
    } catch (e) { /* noop */ }
  }
  function updateBgm() { setBgm(rt.state.bgm_id, rt.state.bgm_fade || 0); }

  // ---------------- アイテム ----------------
  function showItems() {
    const list = $("items-list"); list.innerHTML = "";
    const owned = rt.state.items;
    if (!owned.length) { list.innerHTML = "<p style='color:#aab'>（所持アイテムはありません）</p>"; }
    owned.forEach((iid) => {
      const it = items[iid]; if (!it) return;
      const row = document.createElement("div");
      row.className = "item-row";
      const icoHtml = it.image
        ? `<img src="${it.image}" alt="">` : esc(it.icon || "📦");
      row.innerHTML = `<div class="ico">${icoHtml}</div>` +
        `<div class="info"><b>${esc(it.name)}</b><div class="sub">${esc(it.desc || "")}</div></div>`;
      list.appendChild(row);
    });
    showOverlay("ov-items");
  }

  // ---------------- セーブ / ロード ----------------
  function readSlots() {
    try { return JSON.parse(localStorage.getItem(SAVE_KEY)) || []; }
    catch (e) { return []; }
  }
  function writeSlots(slots) { localStorage.setItem(SAVE_KEY, JSON.stringify(slots)); }

  let saveMode = true;
  function openSave(saving) {
    saveMode = saving;
    $("save-title").textContent = saving ? "セーブ（スロットを選択）" : "ロード（スロットを選択）";
    const slots = readSlots();
    const host = $("slots"); host.innerHTML = "";
    for (let i = 0; i < 10; i++) {
      const slot = slots[i];
      const row = document.createElement("div");
      row.className = "slot";
      const sceneName = slot ? slot.label : "";
      row.innerHTML = slot
        ? `<div class="info"><b>スロット ${i + 1}</b> ${esc(slot.savedAt)}<div class="sub">${esc(sceneName)}</div></div>`
        : `<div class="info"><b>スロット ${i + 1}</b> <span class="sub">（空き）</span></div>`;
      const actions = document.createElement("div");
      actions.className = "row-actions";
      if (saving) {
        actions.appendChild(mkBtn("ここに保存", () => doSave(i)));
      } else {
        const b = mkBtn("ロード", () => doLoad(i)); b.disabled = !slot;
        if (!slot) b.style.opacity = .4;
        actions.appendChild(b);
      }
      if (slot) actions.appendChild(mkBtn("削除", () => doClear(i)));
      row.appendChild(actions);
      host.appendChild(row);
    }
    showOverlay("ov-save");
  }
  function slotLabel() {
    const sc = (DATA.scenes || []).find((s) => s.id === rt.state.scene_id);
    return (DATA.meta.title || "") + "／" + (sc ? sc.name : "");
  }
  function doSave(i) {
    const slots = readSlots();
    slots[i] = { state: rt.state, label: slotLabel(),
                 savedAt: new Date().toLocaleString() };
    writeSlots(slots); openSave(true);
  }
  function doLoad(i) {
    const slots = readSlots();
    if (!slots[i]) return;
    hideOverlay("ov-save");
    hideOverlay("ov-title");
    titleMode = false;
    setGameChrome(true);
    present(rt.loadState(slots[i].state));
  }
  function doClear(i) {
    const slots = readSlots(); slots[i] = null; writeSlots(slots); openSave(saveMode);
  }

  // ---------------- 共通 ----------------
  function mkBtn(label, fn) {
    const b = document.createElement("button"); b.textContent = label; b.onclick = fn; return b;
  }
  function showOverlay(id) { $(id).classList.remove("hidden"); }
  function hideOverlay(id) { $(id).classList.add("hidden"); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }
  function hexA(hex, a) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex || "");
    if (!m) return `rgba(136,136,136,${a})`;
    const n = parseInt(m[1], 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  }
  function anyOverlayOpen() {
    return ["ov-name", "ov-items", "ov-save", "ov-ending", "ov-title", "ov-itemget"]
      .some((id) => !$(id).classList.contains("hidden"));
  }

  // ---------------- イベント結線 ----------------
  elMsgWin.addEventListener("click", onAdvance);
  $("endroll").addEventListener("click", skipEndroll);
  document.addEventListener("keydown", (e) => {
    if (e.key === " " || e.key === "Enter") {
      if (!$("endroll").classList.contains("hidden")) { e.preventDefault(); skipEndroll(); }
      else if (!$("ov-itemget").classList.contains("hidden")) { e.preventDefault(); closeItemGet(); }
      else if (!titleMode && !anyOverlayOpen()) { e.preventDefault(); onAdvance(); }
    }
  });
  $("items-btn").onclick = showItems;
  document.querySelectorAll("#menu button").forEach((b) => {
    b.onclick = () => {
      const act = b.dataset.act;
      if (act === "save") openSave(true);
      else if (act === "load") openSave(false);
      else if (act === "title") toTitle();
    };
  });
  document.querySelectorAll("[data-close]").forEach((b) => {
    b.onclick = () => hideOverlay(b.dataset.close);
  });
  $("itemget-ok").onclick = closeItemGet;
  $("name-ok").onclick = submitName;
  $("name-field").addEventListener("keydown", (e) => { if (e.key === "Enter") submitName(); });
  $("ending-restart").onclick = toTitle;
  $("ending-restart").textContent = "タイトルへ戻る";
  $("btn-new").onclick = beginNew;
  $("btn-continue").onclick = beginContinue;

  // ---------------- タイトル画面 ----------------
  function showTitle() {
    titleMode = true;
    ["ov-name", "ov-items", "ov-save", "ov-ending"].forEach(hideOverlay);
    elChoices.style.display = "none";
    setGameChrome(false);
    $("title-name").textContent = DATA.meta.title || "ノベルゲーム";
    const author = DATA.meta.author || "";
    $("title-author").textContent = author ? "作： " + author : "";
    // つづきから：セーブがあれば有効
    const hasSave = readSlots().some((s) => s);
    $("btn-continue").disabled = !hasSave;
    // タイトル背景・BGM
    setTitleBg(DATA.meta.titleBg || "");
    curBgm = null; // 強制的に切り替え
    updateBgmById(DATA.meta.titleBgm || "");
    showOverlay("ov-title");
  }

  function setTitleBg(bgId) {
    const bg = bgs[bgId];
    if (bg && bg.image) {
      elBg.style.backgroundImage = `url("${bg.image}")`;
      elBg.style.backgroundColor = bg.color || "#101018";
    } else if (bg) {
      elBg.style.backgroundImage = "none";
      elBg.style.backgroundColor = bg.color || "#101018";
    } else {
      elBg.style.backgroundImage = "none";
      elBg.style.backgroundColor = "#101018";
    }
    elChar.innerHTML = "";
    elBlackout.classList.remove("on");
    elGauges.style.display = "none";
  }

  function setGameChrome(visible) {
    const disp = visible ? "" : "none";
    elMsgWin.style.display = disp;
    $("items-btn").style.display = disp;
    $("menu").style.display = visible ? "flex" : "none";
    if (!visible) { elChoices.style.display = "none"; elGauges.style.display = "none"; }
  }

  function updateBgmById(bgmId) { setBgm(bgmId, 0); }

  function beginNew() {
    titleMode = false;
    hideOverlay("ov-title");
    setGameChrome(true);
    present(rt.start());
  }

  function beginContinue() { openSave(false); }

  function toTitle() { showTitle(); }

  // ---------------- レイアウト / テーマ ----------------
  const DEFAULT_LAYOUT = {
    message: { x: 4, y: 72, w: 92, h: 26 },
    choices: { x: 50, y: 42 },
    sprite:  { x: 50, y: 99, scale: 80 },
    gauges:  { x: 1.2, y: 2 },
    items:   { x: 94, y: 2 },
    menu:    { x: 63, y: 9 },
  };

  function layoutOf(key) {
    const L = DATA.layout || {};
    return Object.assign({}, DEFAULT_LAYOUT[key], L[key] || {});
  }

  function applyLayout() {
    const m = layoutOf("message");
    Object.assign(elMsgWin.style,
      { left: m.x + "%", top: m.y + "%", width: m.w + "%",
        height: m.h + "%", bottom: "auto" });
    const g = layoutOf("gauges");
    Object.assign(elGauges.style, { left: g.x + "%", top: g.y + "%", right: "auto" });
    const it = layoutOf("items");
    Object.assign($("items-btn").style,
      { left: it.x + "%", top: it.y + "%", right: "auto" });
    const mn = layoutOf("menu");
    Object.assign($("menu").style, { left: mn.x + "%", top: mn.y + "%", right: "auto" });
    const c = layoutOf("choices");
    Object.assign(elChoices.style,
      { left: c.x + "%", top: c.y + "%", transform: "translate(-50%,-50%)" });
    const sp = layoutOf("sprite");
    Object.assign(elChar.style,
      { left: sp.x + "%", bottom: (100 - sp.y) + "%", height: sp.scale + "%",
        transform: "translateX(-50%)" });
  }

  function applyTheme() {
    const t = DATA.theme || {};
    const rules = [];
    const bg = (sel, path) => {
      if (path) rules.push(
        `${sel}{background-image:url("${path}");background-size:100% 100%;` +
        `background-repeat:no-repeat;border-image:none;}`);
    };
    bg("#msgwin", t.msgWindowImage);
    bg(".choice-btn", t.choiceButtonImage);
    bg(".title-btn", t.titleButtonImage);
    bg("#items-btn", t.itemsButtonImage);
    if (rules.length) {
      const st = document.createElement("style");
      st.textContent = rules.join("\n");
      document.head.appendChild(st);
    }
  }

  // 開始
  applyTheme();
  applyLayout();
  showTitle();
})();
