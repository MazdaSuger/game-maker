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

  const rt = new window.NovelEngine.Runtime(DATA);

  // 索引
  const byId = (list) => Object.fromEntries((list || []).map((e) => [e.id, e]));
  const chars = byId(DATA.characters), bgs = byId(DATA.backgrounds),
        items = byId(DATA.items), bgms = byId(DATA.bgm);

  // DOM
  const $ = (id) => document.getElementById(id);
  const elBg = $("bg"), elChar = $("char"), elBlackout = $("blackout"),
        elGauges = $("gauges"), elMsgWin = $("msgwin"), elName = $("msg-name"),
        elText = $("msg-text"), elNext = $("msg-next"), elChoices = $("choices");

  let current = null, fullText = "", shown = 0, typing = false, typeTimer = null;
  const SAVE_KEY = "novelmaker_save_" + (DATA.meta.title || "game");

  // BGM
  let audio = null, curBgm = null;

  // ---------------- 提示 ----------------
  function present(ev) {
    current = ev;
    updateStage();
    elChoices.style.display = "none";
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

  // ---------------- エンディング ----------------
  function showEnding(ev) {
    elMsgWin.style.display = "none";
    const badge = $("ending-badge");
    if (ev.hidden) { badge.textContent = "🔒 裏エンディング 🔒"; badge.style.color = "#ffd56b"; }
    else { badge.textContent = "★ ENDING ★"; badge.style.color = "#9fe3ff"; }
    $("ending-name").textContent = ev.name || "";
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
      const ex = ch && (ch.expressions || []).find((e) => e.id === st.expr_id);
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

    // 暗転
    elBlackout.classList.toggle("on", !!st.blackout);

    updateGauges();
    updateBgm();
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

  // ---------------- BGM ----------------
  function updateBgm() {
    const st = rt.state;
    if (st.bgm_id === curBgm) return;
    curBgm = st.bgm_id;
    if (audio) { audio.pause(); audio = null; }
    const track = bgms[st.bgm_id];
    if (!track || !track.path) return;
    try {
      audio = new Audio(track.path);
      audio.loop = track.loop !== false;
      audio.volume = 0.7;
      const p = audio.play();
      if (p && p.catch) p.catch(() => {}); // 自動再生制限は無視
    } catch (e) { /* noop */ }
  }

  // ---------------- アイテム ----------------
  function showItems() {
    const list = $("items-list"); list.innerHTML = "";
    const owned = rt.state.items;
    if (!owned.length) { list.innerHTML = "<p style='color:#aab'>（所持アイテムはありません）</p>"; }
    owned.forEach((iid) => {
      const it = items[iid]; if (!it) return;
      const row = document.createElement("div");
      row.className = "item-row";
      row.innerHTML = `<div style="font-size:22px">${esc(it.icon || "📦")}</div>` +
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
    return ["ov-name", "ov-items", "ov-save", "ov-ending"]
      .some((id) => !$(id).classList.contains("hidden"));
  }

  // ---------------- イベント結線 ----------------
  elMsgWin.addEventListener("click", onAdvance);
  document.addEventListener("keydown", (e) => {
    if ((e.key === " " || e.key === "Enter") && !anyOverlayOpen()) { e.preventDefault(); onAdvance(); }
  });
  $("items-btn").onclick = showItems;
  document.querySelectorAll("#menu button").forEach((b) => {
    b.onclick = () => {
      const act = b.dataset.act;
      if (act === "save") openSave(true);
      else if (act === "load") openSave(false);
      else if (act === "restart") restart();
    };
  });
  document.querySelectorAll("[data-close]").forEach((b) => {
    b.onclick = () => hideOverlay(b.dataset.close);
  });
  $("name-ok").onclick = submitName;
  $("name-field").addEventListener("keydown", (e) => { if (e.key === "Enter") submitName(); });
  $("ending-restart").onclick = restart;

  function restart() {
    ["ov-name", "ov-items", "ov-save", "ov-ending"].forEach(hideOverlay);
    present(rt.start());
  }

  // 開始
  restart();
})();
