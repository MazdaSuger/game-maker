/* ============================================================
 *  editor.js — ブラウザ版エディタ（iPad等で .nvproj を編集・書き出し）
 * ============================================================ */
(function () {
  "use strict";
  const M = window.NovelModel;
  const { uid, COMMAND_TYPES, CMD_LABEL, CMD_ICON, COMMAND_FIELDS, newCommand,
          describe, emptyCondition, SAY_POSITIONS, VAR_OPS, GAUGE_OPS,
          COMP_TARGETS, makeProjectDefault } = M;

  const state = { project: null, fileName: "", section: "scenes",
                  sceneIdx: 0, resIdx: {} };

  // ---- DOM ヘルパ ----
  function el(tag, attrs, kids) {
    const e = document.createElement(tag);
    if (attrs) for (const k in attrs) {
      if (k === "class") e.className = attrs[k];
      else if (k === "html") e.innerHTML = attrs[k];
      else if (k === "text") e.textContent = attrs[k];
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), attrs[k]);
      else if (attrs[k] != null) e.setAttribute(k, attrs[k]);
    }
    (kids || []).forEach((c) => c != null && e.appendChild(typeof c === "string" ? document.createTextNode(c) : c));
    return e;
  }
  const $ = (id) => document.getElementById(id);
  // プロジェクト全体のフラグ地点(label)名を集める
  function allLabels(P) {
    const names = [];
    (P.scenes || []).forEach((s) => (s.commands || []).forEach((cm) => {
      if (cm.type === "label" && cm.name && names.indexOf(cm.name) < 0) names.push(cm.name);
    }));
    return names;
  }
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  function markDirty() { /* 必要なら拡張 */ }

  // ---- 選択肢ソース ----
  function getOpts(src, ctx) {
    const P = state.project;
    switch (src) {
      case "char": return P.characters.map((c) => [c.id, c.name]);
      case "expr": { const ch = P.characters.find((c) => c.id === (ctx && ctx.charId)); return ch ? (ch.expressions || []).map((e) => [e.id, e.name]) : []; }
      case "bg": return P.backgrounds.map((b) => [b.id, b.name]);
      case "bgm": return (P.bgm || []).map((b) => [b.id, b.name]);
      case "se": return (P.se || []).map((b) => [b.id, b.name]);
      case "cg": return (P.cg || []).map((b) => [b.id, b.name]);
      case "item": return P.items.map((b) => [b.id, b.name]);
      case "gauge": return P.gauges.map((b) => [b.id, b.name]);
      case "scene": return P.scenes.map((b) => [b.id, b.name]);
      case "jumpTarget": return P.scenes.map((s) => [s.id, "🎬 " + s.name])
        .concat(allLabels(P).map((n) => ["flag:" + n, "🚩 " + n]));
      case "ending": return P.endings.map((b) => [b.id, (b.hidden ? "🔒" : "") + b.name]);
      case "strvar": return P.variables.filter((v) => v.type === "string").map((v) => [v.name, v.name])
        .concat((P.systemVars || []).filter((v) => v.type === "string").map((v) => [v.name, v.name + " [SYS]"]));
      case "anyvar": return P.variables.map((v) => [v.name, v.name + " (" + v.type + ")"]).concat((P.systemVars || []).map((v) => [v.name, v.name + " [SYS]"]));
      case "pos": return SAY_POSITIONS;
      case "varOp": return VAR_OPS;
      case "gaugeOp": return GAUGE_OPS;
      case "cgAction": return [["show", "表示する"], ["hide", "消す"]];
      case "blackoutMode": return [["on", "暗転する"], ["off", "暗転を解除"]];
      case "bgmAction": return [["play", "再生"], ["stop", "停止"]];
      case "itemAction": return [["add", "入手する"], ["use", "使用する(消費)"], ["remove", "失う/破棄する"]];
      case "compTarget": return COMP_TARGETS;
      case "compAction": return [["hide", "消去する"], ["show", "表示する"]];
      case "vartype": return [["number", "数値"], ["string", "文字列"], ["boolean", "真偽"]];
      case "inputType": return [["text", "通常"], ["password", "パスワード(伏字)"]];
    }
    return [];
  }

  // ---- 汎用フィールド描画 ----
  function field(obj, fd, ctx, onSelectChange) {
    const wrap = el("div", { class: "field" });
    if (fd.t !== "bool") wrap.appendChild(el("label", { text: fd.label }));
    const cur = obj[fd.k];
    if (fd.t === "str") {
      wrap.appendChild(el("input", { type: "text", value: cur || "", oninput: (e) => obj[fd.k] = e.target.value }));
    } else if (fd.t === "text") {
      wrap.appendChild(el("textarea", { oninput: (e) => obj[fd.k] = e.target.value }, [cur || ""]));
    } else if (fd.t === "num") {
      wrap.appendChild(el("input", { type: "number", value: cur == null ? 0 : cur, oninput: (e) => obj[fd.k] = parseFloat(e.target.value) || 0 }));
    } else if (fd.t === "bool") {
      const lab = el("label", { class: "field inline" });
      const cb = el("input", { type: "checkbox", onchange: (e) => obj[fd.k] = e.target.checked });
      cb.checked = !!cur;
      lab.appendChild(cb); lab.appendChild(el("span", { text: fd.label }));
      return lab;
    } else if (fd.t === "color") {
      wrap.appendChild(el("input", { type: "color", value: cur || "#888888", oninput: (e) => obj[fd.k] = e.target.value }));
    } else if (fd.t === "select") {
      const sel = el("select", { onchange: (e) => { obj[fd.k] = e.target.value; if (onSelectChange) onSelectChange(fd.k); } });
      if (fd.none != null) sel.appendChild(el("option", { value: "" }, [fd.none]));
      getOpts(fd.src, obj).forEach(([v, l]) => {
        const o = el("option", { value: v }, [l]); if (v === cur) o.selected = true; sel.appendChild(o);
      });
      // 既定で先頭/現在を選択
      if (cur == null || ![...sel.options].some((o) => o.value === String(cur))) {
        if (fd.none == null && sel.options.length) { sel.selectedIndex = 0; obj[fd.k] = sel.value; }
      }
      wrap.appendChild(sel);
    } else if (fd.t && fd.t.startsWith("asset")) {
      wrap.appendChild(assetField(obj, fd));
    } else if (fd.t === "cond") {
      if (!obj[fd.k]) obj[fd.k] = emptyCondition();
      wrap.appendChild(conditionBuilder(obj[fd.k]));
    } else if (fd.t === "choices") {
      wrap.appendChild(choicesEditor(obj));
    }
    return wrap;
  }

  let _assetSeq = 0;
  function assetField(obj, fd) {
    const kind = fd.t.split(":")[1] || "image";
    const box = el("div", { class: "assetrow" });
    const name = el("span", { class: "name" });
    const update = () => {
      const v = obj[fd.k] || "";
      name.textContent = v ? (v.startsWith("data:") ? "（取り込み済み）" : v) : "（なし）";
      box.querySelectorAll("img.thumb").forEach((i) => i.remove());
      if (kind === "image" && v) box.insertBefore(el("img", { class: "thumb", src: v }), name);
    };
    const inputId = "asset-" + (_assetSeq++);
    // iOS対策: display:none にせず視覚的非表示(.vhide)、label[for] でネイティブに
    // ピッカーを開く。accept は画像のみ image/* で絞り込み、音声/フォントは
    // 端末によってファイルがグレーアウトするため指定しない。
    const attrs = { type: "file", id: inputId, class: "vhide", onchange: (e) => {
      const f = e.target.files[0]; if (!f) { return; }
      const r = new FileReader();
      r.onload = () => { obj[fd.k] = r.result; update(); };
      r.onerror = () => alert("ファイルを読み込めませんでした。");
      r.readAsDataURL(f);
      e.target.value = "";
    } };
    if (kind === "image") attrs.accept = "image/*";
    const file = el("input", attrs);
    const pick = el("label", { class: "fakebtn", for: inputId, role: "button", tabindex: "0" }, ["選択"]);
    const clr = el("button", { onclick: () => { obj[fd.k] = ""; update(); } }, ["クリア"]);
    box.appendChild(name); box.appendChild(pick); box.appendChild(clr); box.appendChild(file);
    update();
    return box;
  }

  // ---- 条件ビルダー ----
  const COND_KINDS = [["var", "変数"], ["gauge", "ゲージ"], ["item", "アイテム"],
                      ["ending", "エンディング到達回数"], ["allEndings", "全エンディング解放"]];
  const NUM_OPS = [["==", "="], ["!=", "≠"], [">", ">"], [">=", "≥"], ["<", "<"], ["<=", "≤"]];
  const ITEM_OPS = [["has", "所持している"], ["notHas", "所持していない"]];
  function conditionBuilder(cond) {
    cond.terms = cond.terms || [];
    const box = el("div", { class: "cond" });
    const top = el("div", { class: "term" });
    const logic = el("select", { onchange: (e) => cond.logic = e.target.value }, []);
    [["and", "すべて満たす(AND)"], ["or", "いずれか(OR)"]].forEach(([v, l]) => { const o = el("option", { value: v }, [l]); if (v === (cond.logic || "and")) o.selected = true; logic.appendChild(o); });
    top.appendChild(el("span", { text: "条件:" })); top.appendChild(logic);
    const add = el("button", { onclick: () => { cond.terms.push({ kind: "var", ref: "", op: "==", value: "0" }); render(); } }, ["＋条件"]);
    top.appendChild(add);
    box.appendChild(top);
    const rows = el("div");
    box.appendChild(rows);
    function render() {
      rows.innerHTML = "";
      if (!cond.terms.length) rows.appendChild(el("div", { class: "hint", text: "（条件なし＝常に成立）" }));
      cond.terms.forEach((term) => {
        const r = el("div", { class: "term" });
        const kc = el("select", { onchange: (e) => { term.kind = e.target.value; term.ref = ""; term.op = term.kind === "item" ? "has" : (term.kind === "ending" ? ">=" : "=="); term.value = term.kind === "ending" ? "1" : ""; render(); } });
        COND_KINDS.forEach(([v, l]) => { const o = el("option", { value: v }, [l]); if (v === term.kind) o.selected = true; kc.appendChild(o); });
        r.appendChild(kc);
        if (term.kind !== "allEndings") {
          const refSrc = { var: "anyvar", gauge: "gauge", item: "item", ending: "ending" }[term.kind];
          const rc = el("select", { onchange: (e) => term.ref = e.target.value });
          getOpts(refSrc, {}).forEach(([v, l]) => { const o = el("option", { value: v }, [l]); if (v === term.ref) o.selected = true; rc.appendChild(o); });
          if (!term.ref && rc.options.length) { rc.selectedIndex = 0; term.ref = rc.value; }
          r.appendChild(rc);
          const ops = term.kind === "item" ? ITEM_OPS : NUM_OPS;
          const oc = el("select", { onchange: (e) => term.op = e.target.value });
          ops.forEach(([v, l]) => { const o = el("option", { value: v }, [l]); if (v === term.op) o.selected = true; oc.appendChild(o); });
          r.appendChild(oc);
          if (term.kind !== "item") {
            const vi = el("input", { type: "text", value: term.value || "", style: "width:70px", oninput: (e) => term.value = e.target.value });
            r.appendChild(vi);
          }
        }
        const rm = el("button", { onclick: () => { cond.terms.splice(cond.terms.indexOf(term), 1); render(); } }, ["✕"]);
        r.appendChild(rm);
        rows.appendChild(r);
      });
    }
    render();
    return box;
  }

  // ---- 選択肢エディタ ----
  function choicesEditor(cmd) {
    cmd.options = cmd.options || [];
    const box = el("div", { class: "opts" });
    const list = el("div");
    box.appendChild(list);
    box.appendChild(el("button", { onclick: () => { cmd.options.push({ id: uid("opt"), text: "新しい選択肢", targetScene: "", condition: emptyCondition() }); render(); } }, ["＋ 選択肢を追加"]));
    function render() {
      list.innerHTML = "";
      cmd.options.forEach((opt, i) => {
        const o = el("div", { class: "opt" });
        o.appendChild(el("div", { class: "hint", text: "選択肢 " + (i + 1) }));
        o.appendChild(el("input", { type: "text", value: opt.text || "", oninput: (e) => opt.text = e.target.value }));
        const sel = el("select", { onchange: (e) => opt.targetScene = e.target.value });
        sel.appendChild(el("option", { value: "" }, ["（次のコマンドへ）"]));
        getOpts("scene", {}).forEach(([v, l]) => { const x = el("option", { value: v }, [l]); if (v === opt.targetScene) x.selected = true; sel.appendChild(x); });
        o.appendChild(sel);
        o.appendChild(el("div", { class: "hint", text: "出現条件:" }));
        if (!opt.condition) opt.condition = emptyCondition();
        o.appendChild(conditionBuilder(opt.condition));
        o.appendChild(el("button", { class: "danger", onclick: () => { cmd.options.splice(i, 1); render(); } }, ["この選択肢を削除"]));
        list.appendChild(o);
      });
    }
    render();
    return box;
  }

  // ---- モーダル ----
  function openModal(node) { $("modal-box").innerHTML = ""; $("modal-box").appendChild(node); $("modal").classList.remove("hidden"); }
  function closeModal() { $("modal").classList.add("hidden"); }

  function openCommandModal(cmd, onsave) {
    const work = JSON.parse(JSON.stringify(cmd));
    const box = el("div");
    box.appendChild(el("h3", { text: (CMD_ICON[work.type] || "") + " " + (CMD_LABEL[work.type] || work.type) + " の編集" }));
    const form = el("div");
    function rebuild() {
      form.innerHTML = "";
      (COMMAND_FIELDS[work.type] || []).forEach((fd) => {
        form.appendChild(field(work, fd, work, (key) => { if (key === "charId") rebuild(); }));
      });
    }
    rebuild();
    box.appendChild(form);
    const act = el("div", { class: "actions" });
    act.appendChild(el("button", { onclick: closeModal }, ["キャンセル"]));
    act.appendChild(el("button", { class: "primary", onclick: () => { onsave(work); closeModal(); } }, ["OK"]));
    box.appendChild(act);
    openModal(box);
  }

  // ============================================================
  //  ナビ & セクション
  // ============================================================
  const SECTIONS = [
    ["scenes", "🎬 シーン"], ["flow", "🗺 フローチャート"], ["characters", "🧑 キャラ"],
    ["items", "🎒 アイテム"], ["variables", "🔢 変数"], ["systemVars", "🌐 システム変数"],
    ["gauges", "📊 ゲージ"], ["backgrounds", "🖼 背景"], ["cg", "🌅 CG"],
    ["bgm", "🎵 BGM"], ["se", "🔊 SE"], ["endings", "🏁 エンディング"],
    ["layout", "📐 配置(位置/サイズ)"], ["theme", "🎨 テーマ画像"],
    ["titleVars", "✨ タイトル演出"], ["settings", "⚙ 設定"],
  ];

  function renderNav() {
    const nav = $("nav"); nav.innerHTML = "";
    SECTIONS.forEach(([k, label]) => {
      nav.appendChild(el("button", { class: state.section === k ? "active" : "", onclick: () => { state.section = k; renderNav(); renderContent(); } }, [label]));
    });
  }

  function renderContent() {
    const c = $("content"); c.innerHTML = "";
    if (state.section === "scenes") return renderScenes(c);
    if (state.section === "settings") return renderSettings(c);
    if (state.section === "characters") return renderCharacters(c);
    if (state.section === "flow") return renderFlow(c);
    if (state.section === "layout") return renderLayout(c);
    if (state.section === "theme") return renderTheme(c);
    if (state.section === "titleVars") return renderTitleVars(c);
    return renderResource(c, state.section);
  }

  // ---- シーンのフォルダ（「ファイル」）管理 ----
  function folderOrder(P) {
    const o = [];
    (P.scenes || []).forEach((s) => { const f = s.folder || ""; if (o.indexOf(f) < 0) o.push(f); });
    return o;
  }
  function regroupByOrder(P, order) {
    const by = {};
    P.scenes.forEach((s) => { const f = s.folder || ""; (by[f] = by[f] || []).push(s); });
    const out = [];
    order.forEach((f) => (by[f] || []).forEach((s) => out.push(s)));
    P.scenes.length = 0; out.forEach((s) => P.scenes.push(s));
  }
  function moveFolder(P, folder, dir) {
    const o = folderOrder(P); const i = o.indexOf(folder); const j = i + dir;
    if (j < 0 || j >= o.length) return;
    [o[i], o[j]] = [o[j], o[i]]; regroupByOrder(P, o);
  }
  function dupFolder(P, folder) {
    const newName = (folder || "フォルダ") + " のコピー";
    const copies = P.scenes.filter((s) => (s.folder || "") === folder).map((s) => {
      const cl = JSON.parse(JSON.stringify(s));
      cl.id = uid("scene"); cl.name = s.name || "";
      cl.folder = newName; (cl.commands || []).forEach(freshenCommand);
      return cl;
    });
    copies.forEach((s) => P.scenes.push(s));
    regroupByOrder(P, folderOrder(P));
  }

  // ---- シーン編集 ----
  function renderScenes(c) {
    c.innerHTML = "";
    const P = state.project;
    c.appendChild(el("h2", { text: "シーン" }));
    const row = el("div", { class: "row" });
    // 左：シーン一覧
    const left = el("div", { class: "col" });
    left.appendChild(el("h3", { text: "シーン一覧（📁＝フォルダ）" }));
    // フォルダが連続する並びになるよう整列してから描画（選択シーンは維持）
    const _selScene = P.scenes[state.sceneIdx];
    regroupByOrder(P, folderOrder(P));
    if (_selScene) state.sceneIdx = Math.max(0, P.scenes.indexOf(_selScene));
    const fixSel = (id) => { state.sceneIdx = Math.max(0, P.scenes.findIndex((s) => s.id === id)); };
    const order = folderOrder(P);
    const groupArrs = {};
    order.forEach((f) => { groupArrs[f] = P.scenes.filter((s) => (s.folder || "") === f); });
    const commitGroups = () => {
      const selId = (P.scenes[state.sceneIdx] || {}).id;
      const out = []; order.forEach((f) => groupArrs[f].forEach((s) => out.push(s)));
      P.scenes.length = 0; out.forEach((s) => P.scenes.push(s));
      fixSel(selId); renderScenes(c);
    };
    order.forEach((folder) => {
      if (folder !== "") {
        const hdr = el("div", { class: "folder-hdr" }, [
          el("span", { class: "col", title: "クリックで名前変更", onclick: () => {
            const nn = prompt("フォルダ名を変更", folder);
            if (nn != null) { P.scenes.forEach((s) => { if ((s.folder || "") === folder) s.folder = nn.trim(); }); renderScenes(c); }
          } }, ["📁 " + folder]),
          el("button", { title: "フォルダごと上へ", onclick: () => { const id = (P.scenes[state.sceneIdx] || {}).id; moveFolder(P, folder, -1); fixSel(id); renderScenes(c); } }, ["▲"]),
          el("button", { title: "フォルダごと下へ", onclick: () => { const id = (P.scenes[state.sceneIdx] || {}).id; moveFolder(P, folder, 1); fixSel(id); renderScenes(c); } }, ["▼"]),
          el("button", { title: "フォルダごと複製", onclick: () => { dupFolder(P, folder); renderScenes(c); } }, ["⎘"]),
        ]);
        left.appendChild(hdr);
      }
      const flist = el("div", { class: "list" });
      groupArrs[folder].forEach((s) => {
        const mark = P.meta.startScene === s.id ? "⭐ " : "";
        const sel = P.scenes[state.sceneIdx] === s;
        const it = el("div", { class: "item" + (sel ? " sel" : ""), onclick: () => { state.sceneIdx = P.scenes.indexOf(s); state.cmdSelIdx = -1; renderScenes(c); } },
          [el("span", { class: "grip", title: "ドラッグで並び替え" }, ["⠿"]), el("span", { class: "col", text: mark + s.name })]);
        flist.appendChild(it);
      });
      enableDragReorder(flist, groupArrs[folder], () => commitGroups());
      left.appendChild(flist);
    });
    const sbar = el("div", { class: "toolbar" });
    sbar.appendChild(el("button", { onclick: () => { const n = prompt("シーン名"); if (n) { P.scenes.push({ id: uid("scene"), name: n, commands: [] }); if (P.scenes.length === 1) P.meta.startScene = P.scenes[0].id; state.sceneIdx = P.scenes.length - 1; renderScenes(c); } } }, ["＋追加"]));
    sbar.appendChild(el("button", { onclick: () => { const s = P.scenes[state.sceneIdx]; if (!s) return; const n = prompt("シーン名", s.name); if (n) { s.name = n; renderScenes(c); } } }, ["改名"]));
    sbar.appendChild(el("button", { onclick: () => {
      const s = P.scenes[state.sceneIdx]; if (!s) return;
      const folders = folderOrder(P).filter((x) => x);
      const hint = folders.length ? "\n既存フォルダ: " + folders.join(", ") : "";
      const n = prompt("このシーンを入れるフォルダ名（空欄でフォルダから出す）" + hint, s.folder || "");
      if (n == null) return;
      s.folder = n.trim();
      regroupByOrder(P, folderOrder(P));
      state.sceneIdx = P.scenes.findIndex((x) => x.id === s.id);
      renderScenes(c);
    } }, ["📁 フォルダ"]));
    sbar.appendChild(el("button", { onclick: () => moveItem(P.scenes, state.sceneIdx, -1, (i) => { state.sceneIdx = i; renderScenes(c); }) }, ["▲"]));
    sbar.appendChild(el("button", { onclick: () => moveItem(P.scenes, state.sceneIdx, 1, (i) => { state.sceneIdx = i; renderScenes(c); }) }, ["▼"]));
    sbar.appendChild(el("button", { onclick: () => {
      const s = P.scenes[state.sceneIdx]; if (!s) return;
      const clone = JSON.parse(JSON.stringify(s));
      clone.id = uid("scene"); clone.name = (s.name || "") + " のコピー";
      (clone.commands || []).forEach(freshenCommand);
      P.scenes.splice(state.sceneIdx + 1, 0, clone);
      state.sceneIdx += 1; renderScenes(c);
    } }, ["複製"]));
    sbar.appendChild(el("button", { class: "danger", onclick: () => { const s = P.scenes[state.sceneIdx]; if (s && confirm("シーン「" + s.name + "」を削除？")) { P.scenes.splice(state.sceneIdx, 1); state.sceneIdx = Math.max(0, state.sceneIdx - 1); renderScenes(c); } } }, ["削除"]));
    left.appendChild(sbar);
    const scene = P.scenes[state.sceneIdx];
    if (scene) left.appendChild(el("button", { style: "margin-top:8px", onclick: () => { P.meta.startScene = scene.id; renderScenes(c); } }, ["⭐ 開始シーンに設定"]));
    if (scene) left.appendChild(el("button", { class: "primary", style: "margin-top:8px;width:100%", onclick: () => testPlay(scene.id) }, ["▶ このシーンからテスト"]));
    row.appendChild(left);

    // 右：コマンド列
    const right = el("div", { class: "col" });
    right.appendChild(el("h3", { text: scene ? "コンポーネント列 — " + scene.name : "コンポーネント列" }));
    if (scene) {
      const clist = el("div", { class: "list" });
      scene.commands = scene.commands || [];
      scene.commands.forEach((cmd, i) => {
        const it = el("div", { class: "item" + (i === state.cmdSelIdx ? " sel" : ""),
          onclick: () => { state.cmdSelIdx = i; renderScenes(c); editCommand(scene, i, c); } }, [
          el("span", { class: "grip", title: "ドラッグで並び替え" }, ["⠿"]),
          el("span", { text: (CMD_ICON[cmd.type] || "•") + "  " }),
          el("span", { class: "col", text: describe(cmd, P) }),
          el("button", { onclick: (e) => { e.stopPropagation(); moveItem(scene.commands, i, -1, () => renderScenes(c)); } }, ["▲"]),
          el("button", { onclick: (e) => { e.stopPropagation(); moveItem(scene.commands, i, 1, () => renderScenes(c)); } }, ["▼"]),
          el("button", { title: "複製", onclick: (e) => { e.stopPropagation();
            const clone = freshenCommand(JSON.parse(JSON.stringify(scene.commands[i])));
            scene.commands.splice(i + 1, 0, clone); state.cmdSelIdx = i + 1; renderScenes(c);
          } }, ["⎘"]),
          el("button", { class: "danger", onclick: (e) => { e.stopPropagation(); scene.commands.splice(i, 1); if (state.cmdSelIdx >= i) state.cmdSelIdx--; renderScenes(c); } }, ["✕"]),
        ]);
        clist.appendChild(it);
      });
      enableDragReorder(clist, scene.commands, () => renderScenes(c));
      right.appendChild(clist);
      // 追加メニュー（クリック中のコンポーネントの直下に挿入）
      const addbar = el("div", { class: "toolbar" });
      const sel = el("select");
      COMMAND_TYPES.forEach(([t, l, ic]) => sel.appendChild(el("option", { value: t }, [ic + " " + l])));
      addbar.appendChild(sel);
      addbar.appendChild(el("button", { class: "primary", onclick: () => {
        const cmd = newCommand(sel.value);
        openCommandModal(cmd, (res) => {
          const sidx = state.cmdSelIdx;
          const at = (sidx != null && sidx >= 0 && sidx < scene.commands.length) ? sidx + 1 : scene.commands.length;
          scene.commands.splice(at, 0, res);
          state.cmdSelIdx = at;   // 連続追加は直前に作った物の下へ積む
          renderScenes(c);
        });
      } }, ["＋ コンポーネント追加"]));
      right.appendChild(addbar);
    }
    row.appendChild(right);
    c.appendChild(row);
  }

  function editCommand(scene, i, c) {
    openCommandModal(scene.commands[i], (res) => { scene.commands[i] = res; renderScenes(c); });
  }

  // 複製時に重複IDを避けるため、ID系を振り直す
  function freshenCommand(cmd) {
    cmd.id = uid("cmd");
    if (Array.isArray(cmd.options)) cmd.options.forEach((o) => { if (o && typeof o === "object") o.id = uid("opt"); });
    return cmd;
  }

  function moveItem(arr, i, dir, after) {
    const j = i + dir;
    if (j < 0 || j >= arr.length) return;
    const t = arr[i]; arr[i] = arr[j]; arr[j] = t;
    after && after(j);
  }

  // ---- ドラッグ&ドロップ並び替え（ポインタイベント＝iPad等のタッチ対応）----
  // listEl 内の各 .item に .grip があり、それを掴んで上下にドラッグすると
  // arr の順序を入れ替える。完了時に onReorder() を呼ぶ（通常は再描画）。
  function enableDragReorder(listEl, arr, onReorder) {
    Array.from(listEl.children).forEach((item, idx) => {
      const grip = item.querySelector(".grip");
      if (!grip) return;
      grip.style.touchAction = "none";
      // グリップのタップで item の onclick（編集など）が発火しないように
      grip.addEventListener("click", (e) => { e.stopPropagation(); e.preventDefault(); });
      grip.addEventListener("pointerdown", (e) => {
        e.preventDefault(); e.stopPropagation();
        const fromIdx = idx;
        item.classList.add("dragging");
        // タッチ中もドラッグを掴み続けるためキャプチャ（スクロール抑止）。
        try { grip.setPointerCapture(e.pointerId); } catch (_) {}
        const onMove = (ev) => {
          const sibs = Array.from(listEl.children).filter((s) => s !== item);
          let target = null;
          for (const s of sibs) {
            const r = s.getBoundingClientRect();
            if (ev.clientY < r.top + r.height / 2) { target = s; break; }
          }
          if (target) listEl.insertBefore(item, target);
          else listEl.appendChild(item);
        };
        const onUp = () => {
          window.removeEventListener("pointermove", onMove);
          window.removeEventListener("pointerup", onUp);
          window.removeEventListener("pointercancel", onUp);
          item.classList.remove("dragging");
          const toIdx = Array.from(listEl.children).indexOf(item);
          if (toIdx >= 0 && toIdx !== fromIdx) {
            const [moved] = arr.splice(fromIdx, 1);
            arr.splice(toIdx, 0, moved);
            onReorder(fromIdx, toIdx);
          }
        };
        // window で受けると、ポインタキャプチャの有無に関わらず確実に拾える。
        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onUp);
        window.addEventListener("pointercancel", onUp);
      });
    });
  }

  // ---- リソース定義 ----
  const RES = {
    items: { icon: "🎒", fields: [
      { k: "name", label: "名前", t: "str" }, { k: "icon", label: "アイコン(絵文字)", t: "str" },
      { k: "image", label: "アイコン画像", t: "asset:image" }, { k: "desc", label: "説明", t: "text" },
      { k: "consumable", label: "使用したら消費する", t: "bool" }],
      neww: () => ({ id: uid("item"), name: "アイテム", icon: "📦", image: "", desc: "", consumable: true }),
      labelf: (e) => (e.image ? "🖼" : e.icon || "") + " " + e.name },
    variables: { icon: "🔢", fields: [
      { k: "name", label: "変数名", t: "str" }, { k: "type", label: "型", t: "select", src: "vartype" },
      { k: "initial", label: "初期値", t: "str" }],
      neww: () => ({ id: uid("var"), name: "var", type: "number", initial: 0 }),
      labelf: (e) => `${e.name} [${e.type}] = ${e.initial}` },
    systemVars: { icon: "🌐", listProp: "systemVars", fields: [
      { k: "name", label: "変数名", t: "str" }, { k: "type", label: "型", t: "select", src: "vartype" },
      { k: "initial", label: "初期値", t: "str" }],
      neww: () => ({ id: uid("svar"), name: "sys", type: "number", initial: 0 }),
      labelf: (e) => `${e.name} [${e.type}] = ${e.initial}` },
    gauges: { icon: "📊", fields: [
      { k: "name", label: "名前", t: "str" }, { k: "min", label: "最小", t: "num" },
      { k: "max", label: "最大", t: "num" }, { k: "initial", label: "初期値", t: "num" },
      { k: "color", label: "色", t: "color" }, { k: "show", label: "画面に表示する", t: "bool" }],
      neww: () => ({ id: uid("gauge"), name: "ゲージ", min: 0, max: 100, initial: 0, color: "#4cc2ff", show: true }),
      labelf: (e) => `${e.name} (${e.min}〜${e.max})` },
    backgrounds: { icon: "🖼", fields: [
      { k: "name", label: "名前", t: "str" }, { k: "image", label: "画像", t: "asset:image" },
      { k: "color", label: "背景色(画像なし時)", t: "color" }],
      neww: () => ({ id: uid("bg"), name: "背景", image: "", color: "#222244" }),
      labelf: (e) => e.name },
    cg: { icon: "🌅", listProp: "cg", fields: [
      { k: "name", label: "名前", t: "str" }, { k: "image", label: "画像", t: "asset:image" },
      { k: "color", label: "背景色(画像なし時)", t: "color" }],
      neww: () => ({ id: uid("cg"), name: "CG", image: "", color: "#1a1a2a" }),
      labelf: (e) => "🌅 " + e.name },
    bgm: { icon: "🎵", fields: [
      { k: "name", label: "曲名", t: "str" }, { k: "path", label: "音声ファイル", t: "asset:audio" },
      { k: "loop", label: "ループ再生する", t: "bool" }],
      neww: () => ({ id: uid("bgm"), name: "曲", path: "", loop: true }),
      labelf: (e) => "🎵 " + e.name },
    se: { icon: "🔊", listProp: "se", fields: [
      { k: "name", label: "効果音名", t: "str" }, { k: "path", label: "音声ファイル", t: "asset:audio" }],
      neww: () => ({ id: uid("se"), name: "SE", path: "" }),
      labelf: (e) => "🔊 " + e.name },
    endings: { icon: "🏁", fields: [
      { k: "name", label: "名前", t: "str" }, { k: "hidden", label: "裏エンディングにする", t: "bool" },
      { k: "cgId", label: "エンディングCG(任意)", t: "select", src: "cg", none: "（なし）" },
      { k: "desc", label: "説明文", t: "text" }],
      neww: () => ({ id: uid("end"), name: "エンディング", hidden: false, cgId: "", desc: "" }),
      labelf: (e) => (e.hidden ? "🔒 " : "") + e.name },
  };

  function renderResource(c, key) {
    c.innerHTML = "";
    const def = RES[key];
    const P = state.project;
    const listProp = def.listProp || key;
    P[listProp] = P[listProp] || [];
    const list = P[listProp];
    c.appendChild(el("h2", { text: (SECTIONS.find((s) => s[0] === key) || [, key])[1] }));
    const row = el("div", { class: "row" });
    const left = el("div", { class: "col" });
    const ul = el("div", { class: "list" });
    if (state.resIdx[key] == null) state.resIdx[key] = 0;
    list.forEach((e, i) => {
      ul.appendChild(el("div", { class: "item" + (i === state.resIdx[key] ? " sel" : ""), onclick: () => { state.resIdx[key] = i; renderResource(c, key); } }, [def.labelf(e)]));
    });
    left.appendChild(ul);
    const bar = el("div", { class: "toolbar" });
    bar.appendChild(el("button", { onclick: () => { list.push(def.neww()); state.resIdx[key] = list.length - 1; renderResource(c, key); } }, ["＋追加"]));
    bar.appendChild(el("button", { onclick: () => moveItem(list, state.resIdx[key], -1, (i) => { state.resIdx[key] = i; renderResource(c, key); }) }, ["▲"]));
    bar.appendChild(el("button", { onclick: () => moveItem(list, state.resIdx[key], 1, (i) => { state.resIdx[key] = i; renderResource(c, key); }) }, ["▼"]));
    bar.appendChild(el("button", { class: "danger", onclick: () => { if (list.length) { list.splice(state.resIdx[key], 1); state.resIdx[key] = Math.max(0, state.resIdx[key] - 1); renderResource(c, key); } } }, ["削除"]));
    left.appendChild(bar);
    row.appendChild(left);

    const right = el("div", { class: "col" });
    const e = list[state.resIdx[key]];
    if (e) def.fields.forEach((fd) => right.appendChild(field(e, fd, e)));
    row.appendChild(right);
    c.appendChild(row);
  }

  // ---- キャラ（表情差分つき） ----
  function renderCharacters(c) {
    c.innerHTML = "";
    const P = state.project; const key = "characters";
    c.appendChild(el("h2", { text: "キャラ・表情" }));
    const row = el("div", { class: "row" });
    const left = el("div", { class: "col" });
    const ul = el("div", { class: "list" });
    if (state.resIdx[key] == null) state.resIdx[key] = 0;
    P.characters.forEach((e, i) => {
      ul.appendChild(el("div", { class: "item" + (i === state.resIdx[key] ? " sel" : ""), onclick: () => { state.resIdx[key] = i; renderCharacters(c); } }, [(e.isProtagonist ? "👤 " : "") + e.name + `（表情${(e.expressions || []).length}）`]));
    });
    left.appendChild(ul);
    const bar = el("div", { class: "toolbar" });
    bar.appendChild(el("button", { onclick: () => { P.characters.push({ id: uid("char"), name: "キャラ", color: "#ffffff", isProtagonist: false, showSprite: true, expressions: [{ id: uid("expr"), name: "通常", image: "" }] }); state.resIdx[key] = P.characters.length - 1; renderCharacters(c); } }, ["＋追加"]));
    bar.appendChild(el("button", { class: "danger", onclick: () => { if (P.characters.length) { P.characters.splice(state.resIdx[key], 1); state.resIdx[key] = Math.max(0, state.resIdx[key] - 1); renderCharacters(c); } } }, ["削除"]));
    left.appendChild(bar);
    row.appendChild(left);

    const right = el("div", { class: "col" });
    const e = P.characters[state.resIdx[key]];
    if (e) {
      right.appendChild(field(e, { k: "name", label: "名前", t: "str" }, e));
      right.appendChild(field(e, { k: "color", label: "名前色", t: "color" }, e));
      right.appendChild(field(e, { k: "isProtagonist", label: "主人公（プレイヤー操作キャラ）にする", t: "bool" }, e));
      right.appendChild(field(e, { k: "showSprite", label: "立ち絵を表示する", t: "bool" }, e));
      right.appendChild(el("h3", { text: "表情差分" }));
      const exl = el("div", { class: "list" });
      e.expressions = e.expressions || [];
      e.expressions.forEach((ex, i) => {
        const r = el("div", { class: "item" }, [
          el("input", { type: "text", value: ex.name || "", style: "flex:1", oninput: (ev) => ex.name = ev.target.value }),
          assetField(ex, { k: "image", label: "", t: "asset:image" }),
          el("button", { class: "danger", onclick: () => { e.expressions.splice(i, 1); renderCharacters(c); } }, ["✕"]),
        ]);
        exl.appendChild(r);
      });
      right.appendChild(exl);
      right.appendChild(el("button", { style: "margin-top:8px", onclick: () => { e.expressions.push({ id: uid("expr"), name: "新しい表情", image: "" }); renderCharacters(c); } }, ["＋ 表情を追加"]));
    }
    row.appendChild(right);
    c.appendChild(row);
  }

  // ---- 設定 ----
  function renderSettings(c) {
    c.innerHTML = "";
    const P = state.project; const m = P.meta;
    c.appendChild(el("h2", { text: "ゲーム設定" }));
    c.appendChild(field(m, { k: "title", label: "タイトル", t: "str" }, m));
    c.appendChild(field(m, { k: "author", label: "作者", t: "str" }, m));
    c.appendChild(field(m, { k: "startScene", label: "開始シーン", t: "select", src: "scene" }, m));
    c.appendChild(field(m, { k: "titleBg", label: "タイトル画面の背景", t: "select", src: "bg", none: "（なし）" }, m));
    c.appendChild(field(m, { k: "titleBgm", label: "タイトル画面のBGM", t: "select", src: "bgm", none: "（なし）" }, m));
    c.appendChild(field(m, { k: "titleColor", label: "タイトル文字の色", t: "color" }, m));
    c.appendChild(field(m, { k: "titleLogoImage", label: "タイトルロゴ画像(任意)", t: "asset:image" }, m));
    c.appendChild(field(m, { k: "fontScale", label: "文字サイズ(%)", t: "num" }, m));
    c.appendChild(field(m, { k: "msgFontScale", label: "セリフのフォントサイズ(%)", t: "num" }, m));
    c.appendChild(field(m, { k: "font", label: "フォント名(任意)", t: "str" }, m));
    c.appendChild(field(m, { k: "fontPath", label: "取り込みフォント(任意)", t: "asset:font" }, m));
    c.appendChild(el("p", { class: "hint", text: "※ 画像/音声/フォントはこの端末から取り込むと、書き出したHTMLに埋め込まれます。" }));
  }

  // ============================================================
  //  フローチャート（読み取り専用の関係図）
  // ============================================================
  function sceneEdges(scene) {
    // 戻り値: [{to: sceneId, label}] と末尾フォールスルー情報
    const edges = [];
    (scene.commands || []).forEach((c) => {
      if (c.type === "jump" && c.targetScene) edges.push({ to: c.targetScene, label: "移動" });
      else if (c.type === "choice") (c.options || []).forEach((o) => {
        if (o.targetScene) edges.push({ to: o.targetScene, label: "選: " + (o.text || "") });
      });
      else if (c.type === "if") {
        if (c.targetTrue) edges.push({ to: c.targetTrue, label: "条件成立" });
        if (c.targetFalse) edges.push({ to: c.targetFalse, label: "不成立" });
      }
    });
    return edges;
  }

  function renderFlow(c) {
    c.innerHTML = "";
    const P = state.project;
    c.appendChild(el("h2", { text: "🗺 フローチャート" }));
    c.appendChild(el("p", { class: "hint",
      text: "各シーンの「シーン移動・選択肢・条件分岐」によるつながりを表示します（読み取り専用）。シーン名をタップで編集へ。" }));
    if (!P.scenes.length) { c.appendChild(el("p", { class: "hint", text: "シーンがありません。" })); return; }
    const nameOf = (id) => { const s = P.scenes.find((x) => x.id === id); return s ? s.name : "??"; };
    const wrap = el("div", { class: "flow" });
    P.scenes.forEach((s, i) => {
      const node = el("div", { class: "flow-node" });
      const head = el("div", { class: "flow-name", onclick: () => { state.section = "scenes"; state.sceneIdx = i; renderNav(); renderContent(); } },
        ["🎬 " + (s.name || "(無題)")]);
      node.appendChild(head);
      const edges = sceneEdges(s);
      if (edges.length) {
        edges.forEach((e) => node.appendChild(el("div", { class: "flow-edge" }, ["└▶ " + e.label + " → " + nameOf(e.to)])));
      } else {
        // 明示的な遷移が無ければ次のシーンへ流れる（最後はエンドの可能性）
        const nx = P.scenes[i + 1];
        node.appendChild(el("div", { class: "flow-edge dim" }, [nx ? "└▶ （次のシーンへ）→ " + nx.name : "└▶ （シーン終了）"]));
      }
      wrap.appendChild(node);
    });
    c.appendChild(wrap);
  }

  // ============================================================
  //  配置（コンポーネント位置・サイズ・表示/非表示）
  // ============================================================
  const LAYOUT_DEFAULT = {
    message: { x: 4, y: 72, w: 92, h: 26 },
    choices: { x: 50, y: 42, scale: 100 },
    spriteLeft: { x: 25, y: 99, scale: 80 }, spriteCenter: { x: 50, y: 99, scale: 80 },
    spriteRight: { x: 75, y: 99, scale: 80 },
    gauges: { x: 1.2, y: 2, scale: 100 }, items: { x: 94, y: 2, scale: 100 },
    menu: { x: 63, y: 9, scale: 100 }, nameBox: { x: 50, y: 50, scale: 100 },
    endingBox: { x: 50, y: 50, scale: 100 },
    titleName: { x: 50, y: 24, scale: 100 },
    titleStart: { x: 50, y: 50, scale: 100 }, titleContinue: { x: 50, y: 58, scale: 100 },
    title: { x: 50, y: 70, scale: 100 },
  };
  // (key, ラベル, 種別, 非表示フラグ用キー)
  const LAYOUT_ELEMENTS = [
    ["message", "セリフ枠", "box", "message"],
    ["spriteLeft", "立ち絵(左)", "sprite", "sprite"],
    ["spriteCenter", "立ち絵(中)", "sprite", "sprite"],
    ["spriteRight", "立ち絵(右)", "sprite", "sprite"],
    ["choices", "選択肢", "point", "choices"],
    ["gauges", "ゲージ", "point", "gauges"],
    ["items", "アイテム", "point", "items"],
    ["menu", "メニュー", "point", "menu"],
    ["nameBox", "名前入力の枠", "point", "nameBox"],
    ["endingBox", "エンディング枠", "point", "endingBox"],
    ["titleName", "タイトル文字", "point", "titleName"],
    ["titleStart", "「はじめから」", "point", "titleStart"],
    ["titleContinue", "「つづきから」", "point", "titleContinue"],
    ["title", "タイトル追加/終了ボタン", "point", "title"],
  ];

  function layCfg(key) {
    const L = state.project.layout || (state.project.layout = {});
    if (!L[key]) L[key] = {};
    return L[key];
  }
  function layVal(key, prop) {
    const cfg = layCfg(key);
    // 縦横比(scaleX/scaleY)が未設定なら、従来の uniform scale にフォールバック
    if ((prop === "scaleX" || prop === "scaleY") && cfg[prop] == null) {
      const s = cfg.scale;
      const d = (LAYOUT_DEFAULT[key] || {}).scale;
      return s == null ? (d == null ? 100 : d) : s;
    }
    if (prop === "textScale" && cfg[prop] == null) return 100;  // 文字サイズの既定
    if ((prop === "textX" || prop === "textY") && cfg[prop] == null) return 0;  // 文字位置の既定
    if (prop === "textWidth" && cfg[prop] == null) return 100;  // 折り返し幅の既定
    const v = cfg[prop];
    return v == null ? (LAYOUT_DEFAULT[key] || {})[prop] : v;
  }

  function renderLayout(c) {
    c.innerHTML = "";
    state.layoutSel = state.layoutSel || "message";
    c.appendChild(el("h2", { text: "📐 配置（位置・サイズ・表示）" }));
    c.appendChild(el("p", { class: "hint",
      text: "ステージ上の四角をドラッグして位置を調整。下のスライダーでサイズ、チェックで非表示にできます。" }));

    const stage = el("div", { class: "lay-stage" });
    function place(chip, key, type) {
      let top = layVal(key, "y");
      if (type === "box") {
        const h = layVal(key, "h");
        if (top + h > 100) top = Math.max(0, 100 - h);  // プレイヤーと同じく画面内に収める
        chip.style.width = layVal(key, "w") + "%"; chip.style.height = h + "%";
      }
      chip.style.left = layVal(key, "x") + "%";
      chip.style.top = top + "%";
      chip.style.transform = type === "box" ? "translate(0,0)"
        : type === "sprite" ? "translate(-50%,-100%)" : "translate(-50%,-50%)";
    }
    LAYOUT_ELEMENTS.forEach(([key, label, type, hideKey]) => {
      if (layCfg(hideKey).hidden) return;  // 非表示要素はステージに出さない
      const chip = el("div", { class: "lay-chip" + (key === state.layoutSel ? " sel" : "") +
        (type === "box" ? " box" : ""), "data-k": key }, [label]);
      place(chip, key, type);
      // ドラッグ（ポインタ＝タッチ対応）
      chip.addEventListener("pointerdown", (ev) => {
        ev.preventDefault();
        state.layoutSel = key; renderLayout(c);
        const rect = stage.getBoundingClientRect();
        const move = (e) => {
          let nx = ((e.clientX - rect.left) / rect.width) * 100;
          let ny = ((e.clientY - rect.top) / rect.height) * 100;
          if (type === "box") { nx -= 0; ny -= 0; }  // 箱は左上アンカー
          const cfg = layCfg(key);
          cfg.x = Math.max(0, Math.min(100, Math.round(nx * 10) / 10));
          cfg.y = Math.max(0, Math.min(100, Math.round(ny * 10) / 10));
          const live = stage.querySelector('[data-k="' + key + '"]');
          if (live) { live.style.left = cfg.x + "%"; live.style.top = cfg.y + "%"; }
          syncSliders();
        };
        const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
        window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
      });
      stage.appendChild(chip);
    });
    c.appendChild(stage);

    // ---- 選択中要素のコントロール ----
    const panel = el("div", { class: "lay-panel" });
    let sliderRefs = [];
    function syncSliders() { sliderRefs.forEach((f) => f()); }
    function buildPanel() {
      panel.innerHTML = ""; sliderRefs = [];
      const ent = LAYOUT_ELEMENTS.find((e) => e[0] === state.layoutSel);
      if (!ent) return;
      const [key, label, type, hideKey] = ent;
      panel.appendChild(el("h3", { text: "選択中: " + label }));
      const sliderRow = (lab, prop, min, max, step) => {
        const row = el("div", { class: "lay-srow" });
        row.appendChild(el("span", { class: "lay-slab", text: lab }));
        const num = el("span", { class: "lay-snum" });
        const rng = el("input", { type: "range", min, max, step, value: layVal(key, prop),
          oninput: (e) => {
            layCfg(key)[prop] = parseFloat(e.target.value);
            num.textContent = e.target.value;
            const live = stage.querySelector('[data-k="' + key + '"]');
            if (live) {
              live.style.left = layVal(key, "x") + "%";
              let top = layVal(key, "y");
              if (type === "box") {
                const h = layVal(key, "h");
                if (top + h > 100) top = Math.max(0, 100 - h);
                live.style.width = layVal(key, "w") + "%"; live.style.height = h + "%";
              }
              live.style.top = top + "%";
            }
          } });
        const sync = () => { rng.value = layVal(key, prop); num.textContent = layVal(key, prop); };
        sliderRefs.push(sync); sync();
        row.appendChild(rng); row.appendChild(num); return row;
      };
      panel.appendChild(sliderRow("X位置 (%)", "x", 0, 100, 0.5));
      panel.appendChild(sliderRow("Y位置 (%)", "y", 0, 100, 0.5));
      if (type === "box") {
        panel.appendChild(sliderRow("幅 (%)", "w", 10, 100, 1));
        panel.appendChild(sliderRow("高さ (%)", "h", 5, 100, 1));
        panel.appendChild(sliderRow("文字の折り返し幅 (%)", "textWidth", 20, 100, 1));
        panel.appendChild(sliderRow("文字の横位置 (%)", "textX", -150, 150, 1));
        panel.appendChild(sliderRow("文字の縦位置 (%)", "textY", -150, 150, 1));
      } else if (type === "sprite") {
        panel.appendChild(sliderRow("サイズ(高さ %)", "scale", 20, 200, 1));
      } else {
        // point 系は横・縦を個別に＝縦横比を変えられる。文字サイズ・位置は別管理（連動しない）。
        panel.appendChild(sliderRow("横幅 (%)", "scaleX", 20, 300, 1));
        panel.appendChild(sliderRow("縦高さ (%)", "scaleY", 20, 300, 1));
        panel.appendChild(sliderRow("文字サイズ (%)", "textScale", 30, 300, 1));
        panel.appendChild(sliderRow("文字の横位置 (%)", "textX", -150, 150, 1));
        panel.appendChild(sliderRow("文字の縦位置 (%)", "textY", -150, 150, 1));
      }
      // 非表示チェック
      const hl = el("label", { class: "field inline" });
      const cb = el("input", { type: "checkbox", onchange: (e) => { layCfg(hideKey).hidden = e.target.checked; renderLayout(c); } });
      cb.checked = !!layCfg(hideKey).hidden;
      hl.appendChild(cb);
      hl.appendChild(el("span", { text: type === "sprite" ? "立ち絵をまとめて非表示" : "このコンポーネントを非表示" }));
      panel.appendChild(hl);
      // リセット
      panel.appendChild(el("button", { onclick: () => {
        const d = LAYOUT_DEFAULT[key] || {}; const cfg = layCfg(key);
        ["x", "y", "w", "h", "scale"].forEach((p) => { if (d[p] != null) cfg[p] = d[p]; });
        // 縦横比・文字サイズ・文字位置・折り返し幅も解除
        ["scaleX", "scaleY", "textScale", "textX", "textY", "textWidth"].forEach((p) => delete cfg[p]);
        renderLayout(c);
      } }, ["既定値に戻す"]));
    }
    buildPanel();
    c.appendChild(panel);

    // 要素切り替えボタン
    const picker = el("div", { class: "lay-picker" });
    LAYOUT_ELEMENTS.forEach(([key, label, , hideKey]) => {
      const b = el("button", { class: key === state.layoutSel ? "active" : "",
        onclick: () => { state.layoutSel = key; renderLayout(c); } },
        [(layCfg(hideKey).hidden ? "🚫 " : "") + label]);
      picker.appendChild(b);
    });
    c.appendChild(el("h3", { text: "要素を選択" }));
    c.appendChild(picker);
  }

  // ============================================================
  //  タイトル演出（条件で背景/BGM/ロゴ/色を差し替え＋ボタン追加）
  // ============================================================
  function newTitleVariation() {
    return { id: uid("tv"), name: "新しい演出", bg: "", bgm: "", logo: "", color: "#ffffff",
             condition: emptyCondition(), buttons: [] };
  }

  function renderTitleVars(c) {
    c.innerHTML = "";
    const P = state.project;
    const list = P.meta.titleVariations || (P.meta.titleVariations = []);
    c.appendChild(el("h2", { text: "✨ タイトル演出" }));
    c.appendChild(el("p", { class: "hint",
      text: "条件（全エンディング解放・到達回数・システム変数など）を満たすと、タイトル画面の背景/BGM/ロゴ/文字色を差し替え、ボタンを追加します。上から順に評価され、最初に条件を満たした演出が適用されます。" }));

    const listBox = el("div", { class: "list" });
    list.forEach((v, i) => {
      const it = el("div", { class: "item" + (i === (state.tvIdx || 0) ? " sel" : "") },
        [el("span", { text: v.name || "(無題)" })]);
      it.addEventListener("click", () => { state.tvIdx = i; renderTitleVars(c); });
      listBox.appendChild(it);
    });
    c.appendChild(listBox);

    const tb = el("div", { class: "toolbar" });
    tb.appendChild(el("button", { class: "primary", onclick: () => { list.push(newTitleVariation()); state.tvIdx = list.length - 1; renderTitleVars(c); } }, ["＋追加"]));
    if (list.length) {
      tb.appendChild(el("button", { onclick: () => {
        const i = state.tvIdx || 0; if (i > 0) { [list[i - 1], list[i]] = [list[i], list[i - 1]]; state.tvIdx = i - 1; renderTitleVars(c); } } }, ["▲"]));
      tb.appendChild(el("button", { onclick: () => {
        const i = state.tvIdx || 0; if (i < list.length - 1) { [list[i + 1], list[i]] = [list[i], list[i + 1]]; state.tvIdx = i + 1; renderTitleVars(c); } } }, ["▼"]));
      tb.appendChild(el("button", { class: "danger", onclick: () => {
        const i = state.tvIdx || 0; list.splice(i, 1); state.tvIdx = Math.max(0, i - 1); renderTitleVars(c); } }, ["削除"]));
    }
    c.appendChild(tb);

    const v = list[state.tvIdx || 0];
    if (!v) return;
    if (!v.condition) v.condition = emptyCondition();
    const form = el("div");
    form.appendChild(field(v, { k: "name", label: "演出名", t: "str" }, v));
    form.appendChild(field(v, { k: "bg", label: "タイトル背景", t: "select", src: "bg", none: "（既定の背景のまま）" }, v));
    form.appendChild(field(v, { k: "bgm", label: "タイトルBGM", t: "select", src: "bgm", none: "（既定のBGMのまま）" }, v));
    form.appendChild(field(v, { k: "logo", label: "ロゴ画像(任意)", t: "asset:image" }, v));
    form.appendChild(field(v, { k: "color", label: "タイトル文字の色", t: "color" }, v));
    form.appendChild(el("h3", { text: "適用条件（例：全エンディング解放）" }));
    form.appendChild(conditionBuilder(v.condition));

    // 追加ボタン群
    form.appendChild(el("h3", { text: "タイトルに追加するボタン" }));
    v.buttons = v.buttons || [];
    const btnBox = el("div", { class: "opts" });
    function renderBtns() {
      btnBox.innerHTML = "";
      v.buttons.forEach((spec, bi) => {
        const row = el("div", { class: "term" });
        row.appendChild(el("input", { type: "text", value: spec.text || "", placeholder: "ボタン文字",
          oninput: (e) => spec.text = e.target.value, style: "flex:2" }));
        const sel = el("select", { style: "flex:2", onchange: (e) => spec.targetScene = e.target.value });
        sel.appendChild(el("option", { value: "" }, ["（移動先シーン）"]));
        P.scenes.forEach((s) => { const o = el("option", { value: s.id }, [s.name]); if (s.id === spec.targetScene) o.selected = true; sel.appendChild(o); });
        row.appendChild(sel);
        row.appendChild(el("button", { class: "danger", onclick: () => { v.buttons.splice(bi, 1); renderBtns(); } }, ["✕"]));
        btnBox.appendChild(row);
      });
    }
    renderBtns();
    form.appendChild(btnBox);
    form.appendChild(el("button", { onclick: () => { v.buttons.push({ text: "おまけ", targetScene: "" }); renderBtns(); } }, ["＋ ボタンを追加"]));
    c.appendChild(form);
  }

  // ============================================================
  //  テーマ画像（枠・ボタン・名前入力などの取り込み画像）
  // ============================================================
  const THEME_FIELDS = [
    ["msgWindowImage", "セリフ枠の背景"],
    ["titleFrameImage", "タイトルの背景枠"],
    ["choiceButtonImage", "選択肢ボタンの背景"],
    ["titleButtonImage", "タイトルボタンの背景"],
    ["itemsButtonImage", "アイテムボタンの画像"],
    ["menuButtonImage", "メニューボタンの背景"],
    ["nameBoxImage", "名前入力の枠"],
    ["nameFieldImage", "名前入力の入力欄"],
  ];

  function renderTheme(c) {
    c.innerHTML = "";
    const t = state.project.theme || (state.project.theme = {});
    c.appendChild(el("h2", { text: "🎨 テーマ画像" }));
    c.appendChild(el("p", { class: "hint",
      text: "各コンポーネントの枠・ボタンの背景画像をこの端末から取り込めます（書き出すHTMLに埋め込まれます）。未設定なら既定のデザインのままです。" }));
    THEME_FIELDS.forEach(([k, label]) => {
      c.appendChild(field(t, { k, label, t: "asset:image" }, t));
    });
  }

  // ============================================================
  //  読み込み / 保存 / 書き出し / テスト
  // ============================================================
  function migrate(p) {
    p.meta = p.meta || {}; const m = p.meta;
    ["variables", "systemVars", "gauges", "characters", "items", "backgrounds", "cg", "bgm", "se", "endings", "scenes"].forEach((k) => { if (!Array.isArray(p[k])) p[k] = []; });
    p.layout = p.layout || {}; p.theme = p.theme || {};
    if (m.fontScale == null) m.fontScale = 100;
    if (m.msgFontScale == null) m.msgFontScale = 100;
    if (p.theme.titleFrameImage == null) p.theme.titleFrameImage = "";
    if (p.theme.menuButtonImage == null) p.theme.menuButtonImage = "";
    if (!Array.isArray(m.titleVariations)) m.titleVariations = [];
    (p.scenes || []).forEach((s) => (s.commands || []).forEach((c) => {
      if (c.type === "say") { if (c.exprId === "__none__") c.exprId = ""; if (c.hideSprite == null) c.hideSprite = false; if (!c.pos) c.pos = "center"; }
    }));
    const L = p.layout;
    if (L.sprite && (L.sprite.x != null || L.sprite.scale != null) && !L.spriteCenter) {
      const sp = L.sprite, cx = +sp.x || 50, y = +sp.y || 99, sc = +sp.scale || 80;
      L.spriteCenter = { x: cx, y, scale: sc }; L.spriteLeft = { x: Math.max(8, cx - 25), y, scale: sc };
      L.spriteRight = { x: Math.min(92, cx + 25), y, scale: sc }; L.sprite = { hidden: sp.hidden };
    }
    return p;
  }

  function setProject(p, fname) {
    state.project = migrate(p); state.fileName = fname || "";
    state.sceneIdx = 0; state.resIdx = {}; state.section = "scenes"; state.cmdSelIdx = -1;
    $("pname").textContent = state.fileName || "（未保存）";
    renderNav(); renderContent();
  }

  function download(name, text, mime) {
    const blob = new Blob([text], { type: mime || "application/octet-stream" });
    const url = URL.createObjectURL(blob);
    const a = el("a", { href: url, download: name });
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  function saveProject() {
    const P = state.project;
    const name = (P.meta.title || "novelgame").replace(/[\\/:*?"<>|]/g, "_") + ".nvproj";
    download(name, JSON.stringify(P, null, 2), "application/json");
  }

  async function buildHtml(project) {
    // キャッシュ回避: 常に最新のランタイムを取り込む（iPad Safari等の強いキャッシュ対策）
    const bust = "?v=" + Date.now();
    const [eng, ply, css, idx] = await Promise.all(
      ["engine.js", "player.js", "style.css", "index.html"].map(
        (f) => fetch(f + bust, { cache: "no-store" }).then((r) => r.text())));
    const m = idx.match(/<body>([\s\S]*?)<\/body>/i);
    let inner = (m ? m[1] : "");
    inner = inner.replace(/<script src="[^"]*"><\/script>/g, "");
    return `<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,user-scalable=no">
<title>${esc(project.meta.title || "ノベルゲーム")}</title>
<style>${css}</style></head>
<body>${inner}
<script>window.GAME_DATA=${JSON.stringify(project)};</script>
<script>${eng}</script>
<script>${ply}</script>
</body></html>`;
  }

  async function exportHtml() {
    const html = await buildHtml(state.project);
    const name = (state.project.meta.title || "novelgame").replace(/[\\/:*?"<>|]/g, "_") + ".html";
    download(name, html, "text/html");
  }

  // ============================================================
  //  Cloudflare Pages 用 ZIP 書き出し
  //  ルート直下に index.html / engine.js / player.js / style.css /
  //  game.js / _headers と assets/ を入れる（デスクトップ版と同構成）。
  // ============================================================
  function* iterAssetFields(data) {
    for (const bg of data.backgrounds || []) yield [bg, "image"];
    for (const ch of data.characters || []) for (const ex of ch.expressions || []) yield [ex, "image"];
    for (const tr of data.bgm || []) yield [tr, "path"];
    for (const tr of data.se || []) yield [tr, "path"];
    for (const cg of data.cg || []) yield [cg, "image"];
    for (const it of data.items || []) yield [it, "image"];
    const meta = data.meta;
    if (meta) {
      for (const key of ["fontPath", "titleLogoImage"]) if (key in meta) yield [meta, key];
      for (const tv of meta.titleVariations || []) if ("logo" in tv) yield [tv, "logo"];
    }
    const theme = data.theme;
    if (theme) for (const key of ["msgWindowImage", "choiceButtonImage", "titleButtonImage",
      "titleFrameImage", "itemsButtonImage", "nameBoxImage", "nameFieldImage"])
      if (key in theme) yield [theme, key];
  }

  const _crcTable = (() => {
    const t = new Uint32Array(256);
    for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1); t[n] = c >>> 0; }
    return t;
  })();
  function crc32(bytes) {
    let c = 0xFFFFFFFF;
    for (let i = 0; i < bytes.length; i++) c = _crcTable[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8);
    return (c ^ 0xFFFFFFFF) >>> 0;
  }
  const _enc = (s) => new TextEncoder().encode(s);

  function dataUrlToBytes(durl) {
    const i = durl.indexOf(",");
    if (i < 0) return null;
    const head = durl.slice(5, i);                 // "<mime>;base64" 等（先頭 data: を除く）
    const body = durl.slice(i + 1);
    const mime = (head.split(";")[0]) || "application/octet-stream";
    if (/;base64/i.test(head)) {
      const bin = atob(body);
      const bytes = new Uint8Array(bin.length);
      for (let j = 0; j < bin.length; j++) bytes[j] = bin.charCodeAt(j);
      return { mime, bytes };
    }
    return { mime, bytes: _enc(decodeURIComponent(body)) };
  }
  function extForMime(mime) {
    const map = { "image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg", "image/webp": "webp",
      "image/gif": "gif", "image/bmp": "bmp", "image/svg+xml": "svg",
      "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/wav": "wav", "audio/x-wav": "wav",
      "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/aac": "aac",
      "font/ttf": "ttf", "font/otf": "otf", "font/woff": "woff", "font/woff2": "woff2",
      "application/font-woff": "woff", "application/x-font-ttf": "ttf" };
    return map[mime] || (mime.split("/")[1] || "bin").replace(/[^a-z0-9]/gi, "") || "bin";
  }

  function makeZip(files) {
    const body = [], central = [];
    let offset = 0;
    for (const f of files) {
      const nameB = _enc(f.name), data = f.data, crc = crc32(data);
      const lh = new DataView(new ArrayBuffer(30));
      lh.setUint32(0, 0x04034b50, true); lh.setUint16(4, 20, true); lh.setUint16(6, 0x0800, true);
      lh.setUint16(8, 0, true); lh.setUint16(10, 0, true); lh.setUint16(12, 0x21, true);
      lh.setUint32(14, crc, true); lh.setUint32(18, data.length, true); lh.setUint32(22, data.length, true);
      lh.setUint16(26, nameB.length, true); lh.setUint16(28, 0, true);
      body.push(new Uint8Array(lh.buffer), nameB, data);
      const ch = new DataView(new ArrayBuffer(46));
      ch.setUint32(0, 0x02014b50, true); ch.setUint16(4, 20, true); ch.setUint16(6, 20, true);
      ch.setUint16(8, 0x0800, true); ch.setUint16(10, 0, true); ch.setUint16(12, 0, true); ch.setUint16(14, 0x21, true);
      ch.setUint32(16, crc, true); ch.setUint32(20, data.length, true); ch.setUint32(24, data.length, true);
      ch.setUint16(28, nameB.length, true); ch.setUint32(42, offset, true);
      central.push(new Uint8Array(ch.buffer), nameB);
      offset += 30 + nameB.length + data.length;
    }
    let centralSize = 0; central.forEach((c) => centralSize += c.length);
    const eo = new DataView(new ArrayBuffer(22));
    eo.setUint32(0, 0x06054b50, true); eo.setUint16(8, files.length, true); eo.setUint16(10, files.length, true);
    eo.setUint32(12, centralSize, true); eo.setUint32(16, offset, true);
    const parts = body.concat(central, [new Uint8Array(eo.buffer)]);
    let total = 0; parts.forEach((p) => total += p.length);
    const out = new Uint8Array(total);
    let p = 0; for (const part of parts) { out.set(part, p); p += part.length; }
    return out;
  }

  async function exportZip() {
    const bust = "?v=" + Date.now();
    const [eng, ply, css, idx] = await Promise.all(
      ["engine.js", "player.js", "style.css", "index.html"].map(
        (f) => fetch(f + bust, { cache: "no-store" }).then((r) => r.text())));
    const data = JSON.parse(JSON.stringify(state.project));
    const files = [];
    let n = 0;
    for (const [holder, key] of iterAssetFields(data)) {
      const v = holder[key];
      if (!v || typeof v !== "string" || !v.startsWith("data:")) continue;
      const dec = dataUrlToBytes(v);
      if (!dec) continue;
      const name = "assets/a" + (++n) + "." + extForMime(dec.mime);
      files.push({ name, data: dec.bytes });
      holder[key] = name;
    }
    const gameJs = "window.GAME_DATA = " + JSON.stringify(data, null, 2) + ";\n";
    files.push({ name: "index.html", data: _enc(idx) });
    files.push({ name: "engine.js", data: _enc(eng) });
    files.push({ name: "player.js", data: _enc(ply) });
    files.push({ name: "style.css", data: _enc(css) });
    files.push({ name: "game.js", data: _enc(gameJs) });
    files.push({ name: "_headers", data: _enc("/assets/*\n  Cache-Control: public, max-age=31536000, immutable\n") });
    const zip = makeZip(files);
    const name = (data.meta.title || "novelgame").replace(/[\\/:*?"<>|]/g, "_") + "_cloudflare.zip";
    download(name, zip, "application/zip");
  }

  async function testPlay(startScene) {
    const proj = JSON.parse(JSON.stringify(state.project));
    if (startScene) {
      // 指定シーンから直接開始（タイトルを飛ばす）ためのマーカー
      proj.meta = Object.assign({}, proj.meta, { startScene, __testStartScene: startScene });
    }
    const html = await buildHtml(proj);
    const fr = $("playframe");
    fr.srcdoc = html; fr.classList.remove("hidden"); $("playclose").classList.remove("hidden");
  }
  function closePlay() { $("playframe").classList.add("hidden"); $("playframe").srcdoc = ""; $("playclose").classList.add("hidden"); }

  // ---- 起動 ----
  $("btn-new").onclick = () => { if (confirm("新規プロジェクトを作成しますか？（未保存の変更は失われます）")) setProject(makeProjectDefault(), ""); };
  // 開くは <label for="file-open"> がネイティブにピッカーを開く（iOS対策）。
  // キーボード操作用の保険のみ JS で対応。
  $("btn-open").addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") $("file-open").click(); });
  $("file-open").onchange = (e) => {
    const f = e.target.files[0]; if (!f) return;
    const r = new FileReader();
    r.onload = () => {
      try {
        const data = JSON.parse(String(r.result).replace(/^﻿/, ""));
        setProject(data, f.name);
      } catch (err) { alert("読み込みに失敗しました。\n" + err); }
    };
    r.onerror = () => alert("ファイルを読み込めませんでした。");
    r.readAsText(f); e.target.value = "";
  };
  $("btn-save").onclick = saveProject;
  $("btn-export").onclick = () => exportHtml().catch((e) => alert("書き出し失敗: " + e));
  $("btn-zip").onclick = () => exportZip().catch((e) => alert("ZIP書き出し失敗: " + e));
  $("btn-play").onclick = () => testPlay().catch((e) => alert("テスト失敗: " + e));
  $("playclose").onclick = closePlay;
  $("modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });

  setProject(makeProjectDefault(), "");
  window.NovelEditor = { get project() { return state.project; } };
})();
