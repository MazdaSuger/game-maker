/* ============================================================
 *  player.js — ブラウザ版プレイヤー UI（DOM）
 * ------------------------------------------------------------
 *  window.GAME_DATA（プロジェクト）と NovelEngine を用いて
 *  ノベルゲームを再生する。セーブは localStorage の10スロット。
 * ============================================================ */
(function () {
  "use strict";

  const DATA = window.GAME_DATA;
  if (!DATA) {
    // ゲームデータが無い（＝Pagesのトップ等）場合はエディタへ誘導
    try { window.location.replace("editor.html"); } catch (e) {}
    document.body.innerHTML =
      '<div style="color:#ccc;padding:24px;font-family:sans-serif">' +
      'ゲームデータが見つかりません。<a style="color:#9cf" href="editor.html">エディタを開く</a></div>';
    return;
  }
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

  // 自動再生ブロック対策：最初のユーザー操作で、止まっているBGMを再生し直す。
  // （テストプレイ＝iframe や、ブラウザの自動再生制限で無音になるのを防ぐ）
  let audioUnlocked = false;
  function unlockAudio() {
    if (audioUnlocked) return;
    audioUnlocked = true;
    if (audio && audio.paused) { const p = audio.play(); if (p && p.catch) p.catch(() => {}); }
  }
  ["pointerdown", "touchstart", "keydown", "click"].forEach((ev) =>
    document.addEventListener(ev, unlockAudio, { once: false, passive: true }));

  // ---------------- 提示 ----------------
  function present(ev) {
    current = ev;
    updateStage();
    (ev.sfx || []).forEach(playSe);   // 効果音
    elChoices.style.display = "none";
    if (ev.kind !== "endroll") {      // エンドロール解除・UI復帰
      stopEndroll();
      if (!titleMode) {
        $("items-btn").style.display = compHidden("items") ? "none" : "";
        $("menu").style.display = compHidden("menu") ? "none" : "flex";
      }
    }
    if (ev.kind === "endroll") { startEndroll(ev.text || "", ev.speed || 60, ev.noSkip); return; }
    hideOverlay("ov-name"); // 入力以外では閉じる前提

    const k = ev.kind;
    if (k === "say" || k === "narrate") {
      elMsgWin.style.display = compHidden("message") ? "none" : "";
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
        elMsgWin.style.display = compHidden("message") ? "none" : "";
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
      elMsgWin.style.display = compHidden("message") ? "none" : "";
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
      b.className = "choice-btn";
      b.appendChild(mkLabel(opt.text));
      b.onclick = (e) => { e.stopPropagation(); elChoices.style.display = "none"; present(rt.choose(opt.index)); };
      elChoices.appendChild(b);
    });
    if (!ev.options.length) {
      const b = document.createElement("button");
      b.className = "choice-btn";
      b.appendChild(mkLabel("続ける"));
      b.onclick = (e) => { e.stopPropagation(); present(rt.choose(-1)); };
      elChoices.appendChild(b);
    }
    elChoices.style.display = "flex";
    counterScale(elChoices, "choices");
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

    // 立ち絵（最大3人：左/中央/右、スロットごとに位置・スケール）
    elChar.innerHTML = "";
    if (!st.blackout && !compHidden("sprite") && st.sprites) {
      ["left", "center", "right"].forEach((pos) => {
        const entry = st.sprites[pos];
        if (!entry) return;
        const ch = chars[entry.charId];
        if (!ch || ch.showSprite === false) return;
        let ex = (ch.expressions || []).find((e) => e.id === entry.exprId);
        if (!ex && (ch.expressions || []).length) ex = ch.expressions[0];
        const sp = layoutOf(SPRITE_POS_KEY[pos]);
        const el = document.createElement("div");
        el.className = "sprite";
        el.style.left = sp.x + "%";
        el.style.bottom = (100 - sp.y) + "%";
        el.style.height = sp.scale + "%";
        if (ex && ex.image) {
          el.innerHTML = `<img src="${ex.image}" alt="">`;
        } else {
          el.classList.add("char-ph");
          el.style.background = hexA(ch.color || "#888", 0.28);
          el.style.border = "2px solid " + (ch.color || "#888");
          el.textContent = ch.name + (ex ? `\n（${ex.name}）` : "");
        }
        elChar.appendChild(el);
      });
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
  let endrollTimer = null, endrollY = 0, endrollSpeed = 60, endrollNoSkip = false;
  function startEndroll(text, speed, noSkip) {
    endrollNoSkip = !!noSkip;
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
    if (endrollNoSkip) return;
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
    elGauges.style.display = (shownAny && !compHidden("gauges")) ? "" : "none";
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
  elMsgWin.addEventListener("click", (e) => { e.stopPropagation(); onAdvance(); });
  // セリフ枠を非表示にした場合、ステージのクリックで進められる
  $("stage").addEventListener("click", () => {
    if (titleMode || !compHidden("message")) return;
    if (!$("endroll").classList.contains("hidden")) { skipEndroll(); return; }
    if (!anyOverlayOpen()) onAdvance();
  });
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
  function matchedTitleVariation() {
    const vars = DATA.meta.titleVariations || [];
    if (!vars.length) return null;
    const ctx = { variables: {}, gauges: {}, items: [], system: systemData,
                  _all_ending_ids: (DATA.endings || []).map((e) => e.id) };
    for (const v of vars) {
      if (window.NovelEngine.evaluateCondition(v.condition, ctx)) return v;
    }
    return null;
  }

  function showTitle() {
    titleMode = true;
    ["ov-name", "ov-items", "ov-save", "ov-ending"].forEach(hideOverlay);
    elChoices.style.display = "none";
    setGameChrome(false);
    // タイトル演出（条件を満たす最初の演出で上書き）
    const tvar = matchedTitleVariation();
    buildTitleExtraButtons(tvar);
    // タイトルロゴ画像があれば文字の代わりに表示
    const logo = (tvar && tvar.logo) || DATA.meta.titleLogoImage || "";
    if (logo) {
      $("title-logo").src = logo; $("title-logo").style.display = "block";
      $("title-name").style.display = "none";
    } else {
      $("title-logo").style.display = "none";
      $("title-name").style.display = "";
      $("title-name").textContent = DATA.meta.title || "ノベルゲーム";
    }
    // タイトル文字も縦横比に連動しないよう逆スケール
    wrapLabel($("title-name"));
    // タイトル文字の色（演出で上書き可）
    $("title-name").style.color =
      (tvar && tvar.color) || DATA.meta.titleColor || "#ffffff";
    const author = DATA.meta.author || "";
    $("title-author").textContent = author ? "作： " + author : "";
    // 配置（レイアウト）
    const tn = layoutOf("titleName"), tb = layoutOf("title");
    Object.assign($("title-namebox").style, { left: tn.x + "%", top: tn.y + "%",
      transform: `translate(-50%,-50%) scale(${compScaleXY("titleName")})` });
    counterScale($("title-namebox"), "titleName");
    // 「はじめから」「つづきから」を個別配置（タイトル直下の絶対配置）
    placeCoreTitleBtn($("btn-new"), "titleStart");
    placeCoreTitleBtn($("btn-continue"), "titleContinue");
    // 追加/終了ボタン群のボックス
    const tbtns = document.querySelector(".title-buttons");
    tbtns.style.left = tb.x + "%"; tbtns.style.top = tb.y + "%";
    tbtns.style.transform = `translate(-50%,-50%) scale(${compScaleXY("title")})`;
    counterScale(tbtns, "title");
    // つづきから：セーブがあれば有効
    const hasSave = readSlots().some((s) => s);
    $("btn-continue").disabled = !hasSave;
    // タイトル背景・BGM（演出があれば上書き）
    setTitleBg((tvar && tvar.bg) || DATA.meta.titleBg || "");
    curBgm = null; // 強制的に切り替え
    updateBgmById((tvar && tvar.bgm) || DATA.meta.titleBgm || "");
    showOverlay("ov-title");
  }

  let titleExtraButtons = [];
  function buildTitleExtraButtons(tvar) {
    titleExtraButtons.forEach((b) => b.remove());
    titleExtraButtons = [];
    if (!tvar) return;
    const cont = document.querySelector(".title-buttons");
    (tvar.buttons || []).forEach((spec) => {
      const btn = document.createElement("button");
      btn.className = "title-btn";
      btn.appendChild(mkLabel(spec.text || ""));
      btn.onclick = () => {
        if (spec.targetScene) {
          titleMode = false; hideOverlay("ov-title"); setGameChrome(true);
          present(rt.start(spec.targetScene));
        }
      };
      cont.appendChild(btn);   // つづきから の後ろに追加
      titleExtraButtons.push(btn);
    });
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
    elMsgWin.style.display = (visible && !compHidden("message")) ? "" : "none";
    $("items-btn").style.display = (visible && !compHidden("items")) ? "" : "none";
    $("menu").style.display = (visible && !compHidden("menu")) ? "flex" : "none";
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
    spriteLeft:   { x: 25, y: 99, scale: 80 },
    spriteCenter: { x: 50, y: 99, scale: 80 },
    spriteRight:  { x: 75, y: 99, scale: 80 },
    gauges:  { x: 1.2, y: 2 },
    items:   { x: 94, y: 2 },
    menu:    { x: 63, y: 9 },
    titleName: { x: 50, y: 24 },
    titleStart:    { x: 50, y: 50 },
    titleContinue: { x: 50, y: 58 },
    title:     { x: 50, y: 70 },
  };
  const SPRITE_POS_KEY = { left: "spriteLeft", center: "spriteCenter", right: "spriteRight" };

  function layoutOf(key) {
    const L = DATA.layout || {};
    return Object.assign({}, DEFAULT_LAYOUT[key], L[key] || {});
  }

  function compHidden(key) {
    const st = rt.state;
    if (st.blackout && st.blackout_hide_ui) return true;  // 暗転(UIも消す)
    const ov = st.comp_override ? st.comp_override[key] : undefined;
    if (ov !== undefined) return ov;                       // 表示/消去コマンド
    return !!layoutOf(key).hidden;
  }
  function compScale(key) {
    const s = layoutOf(key).scale;
    return (s === undefined ? 100 : s) / 100;
  }
  // 縦横比を変えられるよう、横(scaleX)・縦(scaleY)を個別に返す。
  // 未設定なら従来の uniform scale を使う。
  function scaleXYof(key) {
    const L = layoutOf(key);
    const base = L.scale === undefined ? 100 : L.scale;
    const sx = (L.scaleX === undefined ? base : L.scaleX) / 100;
    const sy = (L.scaleY === undefined ? base : L.scaleY) / 100;
    return { sx, sy };
  }
  function compScaleXY(key) {
    const { sx, sy } = scaleXYof(key);
    return sx + "," + sy;
  }
  // コンポーネントの縦横比を変えても文字が歪まないよう、文字は .nm-label で包み、
  // ボックスの拡縮を打ち消す逆スケールを当てる（文字サイズは textScale で別管理）。
  function compTextScale(key) {
    const t = layoutOf(key).textScale;
    return (t === undefined ? 100 : t) / 100;
  }
  function mkLabel(text) {
    const s = document.createElement("span");
    s.className = "nm-label"; s.textContent = text == null ? "" : text;
    return s;
  }
  function wrapLabel(el) {
    let lbl = el.querySelector(":scope > .nm-label");
    if (!lbl) {
      lbl = document.createElement("span");
      lbl.className = "nm-label";
      while (el.firstChild) lbl.appendChild(el.firstChild);
      el.appendChild(lbl);
    }
    return lbl;
  }
  function counterScale(scopeEl, key) {
    if (!scopeEl) return;
    const { sx, sy } = scaleXYof(key);
    const t = compTextScale(key);
    const L = layoutOf(key);
    const tx = L.textX === undefined ? 0 : L.textX;   // 文字の横位置オフセット(%)
    const ty = L.textY === undefined ? 0 : L.textY;   // 文字の縦位置オフセット(%)
    // translate を先に当てることで、移動量が箱の縦横比(sx,sy)に依存せず
    // 文字サイズ(t)と文字幅にのみ比例する一定の挙動になる。
    const tr = `translate(${tx}%, ${ty}%) scale(${sx ? t / sx : t}, ${sy ? t / sy : t})`;
    scopeEl.querySelectorAll(".nm-label").forEach((s) => { s.style.transform = tr; });
  }
  // 「はじめから」「つづきから」をタイトル直下へ移し、個別の座標に配置する。
  function placeCoreTitleBtn(btn, key) {
    if (!btn) return;
    if (btn.parentElement !== $("ov-title")) {
      $("ov-title").appendChild(btn);
      btn.classList.add("title-core-btn");
    }
    const d = layoutOf(key);
    btn.style.left = d.x + "%"; btn.style.top = d.y + "%";
    btn.style.transform = `translate(-50%,-50%) scale(${compScaleXY(key)})`;
    wrapLabel(btn); counterScale(btn, key);
  }

  function applyLayout() {
    const m = layoutOf("message");
    // 高さを大きくしても画面外へ出ないよう、下端が画面を超える場合は上へ寄せる
    let mTop = m.y, mH = m.h;
    if (mTop + mH > 100) mTop = Math.max(0, 100 - mH);
    Object.assign(elMsgWin.style,
      { left: m.x + "%", top: mTop + "%", width: m.w + "%",
        height: mH + "%", bottom: "auto" });
    // メッセージ枠内の文字位置（名前＋本文をまとめて、枠の大きさ基準で移動）
    const mtx = m.textX === undefined ? 0 : m.textX;
    const mty = m.textY === undefined ? 0 : m.textY;
    const mtr = (mtx || mty) ? `translate(${mtx}%, ${mty}%)` : "";
    const mc = $("msg-content");
    if (mc) mc.style.transform = mtr;
    else { elName.style.transform = mtr; elText.style.transform = mtr; }
    // セリフ本文の折り返し幅（＝文字の入る横範囲）。未指定/100は枠いっぱい。
    const tw = m.textWidth;
    elText.style.maxWidth = (tw != null && tw < 100) ? tw + "%" : "";
    const g = layoutOf("gauges");
    Object.assign(elGauges.style, { left: g.x + "%", top: g.y + "%", right: "auto",
      transform: `scale(${compScaleXY("gauges")})`, transformOrigin: "top left" });
    const it = layoutOf("items");
    Object.assign($("items-btn").style,
      { left: it.x + "%", top: it.y + "%", right: "auto",
        transform: `scale(${compScaleXY("items")})`, transformOrigin: "top left" });
    wrapLabel($("items-btn")); counterScale($("items-btn"), "items");
    const mn = layoutOf("menu");
    Object.assign($("menu").style, { left: mn.x + "%", top: mn.y + "%", right: "auto",
      transform: `scale(${compScaleXY("menu")})`, transformOrigin: "top left" });
    $("menu").querySelectorAll("button").forEach((bb) => wrapLabel(bb));
    counterScale($("menu"), "menu");
    const c = layoutOf("choices");
    Object.assign(elChoices.style,
      { left: c.x + "%", top: c.y + "%",
        transform: `translate(-50%,-50%) scale(${compScaleXY("choices")})` });
    // フォントサイズ（セリフ系）
    const fscale = (DATA.meta.fontScale || 100) / 100;
    const mscale = fscale * (DATA.meta.msgFontScale || 100) / 100;
    let fstyle = document.getElementById("nm-fontsize");
    if (!fstyle) { fstyle = document.createElement("style"); fstyle.id = "nm-fontsize"; document.head.appendChild(fstyle); }
    fstyle.textContent =
      `#msg-text{font-size:${19 * mscale}px;} #msg-name{font-size:${18 * fscale}px;}`;
    // 立ち絵(#char)はステージ全面のコンテナ。各立ち絵は updateStage で配置。
  }
  function spriteX(pos, centerX) {
    if (pos === "left") return Math.max(8, centerX - 25);
    if (pos === "right") return Math.min(92, centerX + 25);
    return centerX;
  }

  function applyTheme() {
    const t = DATA.theme || {};
    const rules = [];
    const bg = (sel, path) => {
      if (path) rules.push(
        `${sel}{background-image:url("${path}");background-size:100% 100%;` +
        `background-repeat:no-repeat;border-image:none;` +
        // 取り込み画像だけが見えるよう、元のデザイン（背景色/枠線/角丸/影）を消す
        `background-color:transparent;border:0;border-radius:0;box-shadow:none;}`);
    };
    bg("#msgwin", t.msgWindowImage);
    bg(".choice-btn", t.choiceButtonImage);
    bg(".title-btn", t.titleButtonImage);
    bg("#title-namebox", t.titleFrameImage);
    bg("#items-btn", t.itemsButtonImage);
    bg("#ov-name .box", t.nameBoxImage);
    bg("#name-field", t.nameFieldImage);
    // フォント
    const meta = DATA.meta || {};
    let fam = meta.font || "";
    if (meta.fontPath) {
      rules.push(`@font-face{font-family:"GameFont";src:url("${meta.fontPath}");}`);
      fam = "GameFont";
    }
    if (fam) {
      rules.push(`body, button, input, textarea, select, #stage, .box { font-family: "${fam}", sans-serif; }`);
    }
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
