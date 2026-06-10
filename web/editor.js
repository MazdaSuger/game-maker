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
      case "ending": return P.endings.map((b) => [b.id, (b.hidden ? "🔒" : "") + b.name]);
      case "strvar": return P.variables.filter((v) => v.type === "string").map((v) => [v.name, v.name]);
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

  function assetField(obj, fd) {
    const kind = fd.t.split(":")[1] || "image";
    const accept = { image: "image/*", audio: "audio/*", font: ".ttf,.otf,.woff,.woff2" }[kind] || "*/*";
    const box = el("div", { class: "assetrow" });
    const name = el("span", { class: "name" });
    const update = () => {
      const v = obj[fd.k] || "";
      name.textContent = v ? (v.startsWith("data:") ? "（取り込み済み）" : v) : "（なし）";
      box.querySelectorAll("img.thumb").forEach((i) => i.remove());
      if (kind === "image" && v) box.insertBefore(el("img", { class: "thumb", src: v }), name);
    };
    const file = el("input", { type: "file", accept, style: "display:none", onchange: (e) => {
      const f = e.target.files[0]; if (!f) return;
      const r = new FileReader();
      r.onload = () => { obj[fd.k] = r.result; update(); };
      r.readAsDataURL(f);
    } });
    const pick = el("button", { onclick: () => file.click() }, ["選択"]);
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
    ["scenes", "🎬 シーン"], ["characters", "🧑 キャラ"], ["items", "🎒 アイテム"],
    ["variables", "🔢 変数"], ["systemVars", "🌐 システム変数"], ["gauges", "📊 ゲージ"],
    ["backgrounds", "🖼 背景"], ["cg", "🌅 CG"], ["bgm", "🎵 BGM"], ["se", "🔊 SE"],
    ["endings", "🏁 エンディング"], ["settings", "⚙ 設定"],
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
    return renderResource(c, state.section);
  }

  // ---- シーン編集 ----
  function renderScenes(c) {
    const P = state.project;
    c.appendChild(el("h2", { text: "シーン" }));
    const row = el("div", { class: "row" });
    // 左：シーン一覧
    const left = el("div", { class: "col" });
    left.appendChild(el("h3", { text: "シーン一覧" }));
    const slist = el("div", { class: "list" });
    P.scenes.forEach((s, i) => {
      const mark = P.meta.startScene === s.id ? "⭐ " : "";
      const it = el("div", { class: "item" + (i === state.sceneIdx ? " sel" : ""), onclick: () => { state.sceneIdx = i; renderScenes(c); } }, [mark + s.name]);
      slist.appendChild(it);
    });
    left.appendChild(slist);
    const sbar = el("div", { class: "toolbar" });
    sbar.appendChild(el("button", { onclick: () => { const n = prompt("シーン名"); if (n) { P.scenes.push({ id: uid("scene"), name: n, commands: [] }); if (P.scenes.length === 1) P.meta.startScene = P.scenes[0].id; state.sceneIdx = P.scenes.length - 1; renderScenes(c); } } }, ["＋追加"]));
    sbar.appendChild(el("button", { onclick: () => { const s = P.scenes[state.sceneIdx]; if (!s) return; const n = prompt("シーン名", s.name); if (n) { s.name = n; renderScenes(c); } } }, ["改名"]));
    sbar.appendChild(el("button", { onclick: () => moveItem(P.scenes, state.sceneIdx, -1, (i) => { state.sceneIdx = i; renderScenes(c); }) }, ["▲"]));
    sbar.appendChild(el("button", { onclick: () => moveItem(P.scenes, state.sceneIdx, 1, (i) => { state.sceneIdx = i; renderScenes(c); }) }, ["▼"]));
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
        const it = el("div", { class: "item", onclick: () => editCommand(scene, i, c) }, [
          el("span", { text: (CMD_ICON[cmd.type] || "•") + "  " }),
          el("span", { class: "col", text: describe(cmd, P) }),
          el("button", { onclick: (e) => { e.stopPropagation(); moveItem(scene.commands, i, -1, () => renderScenes(c)); } }, ["▲"]),
          el("button", { onclick: (e) => { e.stopPropagation(); moveItem(scene.commands, i, 1, () => renderScenes(c)); } }, ["▼"]),
          el("button", { class: "danger", onclick: (e) => { e.stopPropagation(); scene.commands.splice(i, 1); renderScenes(c); } }, ["✕"]),
        ]);
        clist.appendChild(it);
      });
      right.appendChild(clist);
      // 追加メニュー
      const addbar = el("div", { class: "toolbar" });
      const sel = el("select");
      COMMAND_TYPES.forEach(([t, l, ic]) => sel.appendChild(el("option", { value: t }, [ic + " " + l])));
      addbar.appendChild(sel);
      addbar.appendChild(el("button", { class: "primary", onclick: () => {
        const cmd = newCommand(sel.value);
        openCommandModal(cmd, (res) => { scene.commands.push(res); renderScenes(c); });
      } }, ["＋ コンポーネント追加"]));
      right.appendChild(addbar);
    }
    row.appendChild(right);
    c.appendChild(row);
  }

  function editCommand(scene, i, c) {
    openCommandModal(scene.commands[i], (res) => { scene.commands[i] = res; renderScenes(c); });
  }

  function moveItem(arr, i, dir, after) {
    const j = i + dir;
    if (j < 0 || j >= arr.length) return;
    const t = arr[i]; arr[i] = arr[j]; arr[j] = t;
    after && after(j);
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
      { k: "desc", label: "説明文", t: "text" }],
      neww: () => ({ id: uid("end"), name: "エンディング", hidden: false, desc: "" }),
      labelf: (e) => (e.hidden ? "🔒 " : "") + e.name },
  };

  function renderResource(c, key) {
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
    c.appendChild(field(m, { k: "font", label: "フォント名(任意)", t: "str" }, m));
    c.appendChild(field(m, { k: "fontPath", label: "取り込みフォント(任意)", t: "asset:font" }, m));
    c.appendChild(el("p", { class: "hint", text: "※ 画像/音声/フォントはこの端末から取り込むと、書き出したHTMLに埋め込まれます。" }));
  }

  // ============================================================
  //  読み込み / 保存 / 書き出し / テスト
  // ============================================================
  function migrate(p) {
    p.meta = p.meta || {}; const m = p.meta;
    ["variables", "systemVars", "gauges", "characters", "items", "backgrounds", "cg", "bgm", "se", "endings", "scenes"].forEach((k) => { if (!Array.isArray(p[k])) p[k] = []; });
    p.layout = p.layout || {}; p.theme = p.theme || {};
    if (m.fontScale == null) m.fontScale = 100;
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
    state.sceneIdx = 0; state.resIdx = {}; state.section = "scenes";
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
    const [eng, ply, css, idx] = await Promise.all(
      ["engine.js", "player.js", "style.css", "index.html"].map((f) => fetch(f).then((r) => r.text())));
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

  async function testPlay(startScene) {
    const proj = JSON.parse(JSON.stringify(state.project));
    if (startScene) proj.meta = Object.assign({}, proj.meta, { startScene });
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
  $("btn-play").onclick = () => testPlay().catch((e) => alert("テスト失敗: " + e));
  $("playclose").onclick = closePlay;
  $("modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });

  setProject(makeProjectDefault(), "");
  window.NovelEditor = { get project() { return state.project; } };
})();
