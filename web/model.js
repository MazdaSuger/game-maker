/* ============================================================
 *  model.js — ブラウザ版エディタ用のデータモデル
 * ------------------------------------------------------------
 *  novelmaker/model.py の編集に必要な部分を JavaScript へ移植。
 *  コマンド種別・各フィールド定義・新規値・1行要約・既定プロジェクト。
 *  window.NovelModel として公開する。
 * ============================================================ */
(function (root) {
  "use strict";

  let _seq = Date.now();
  function uid(p) { _seq += 1; return (p || "id") + "_" + _seq.toString(36); }

  // (type, 表示名, アイコン)
  const COMMAND_TYPES = [
    ["say", "セリフ", "💬"],
    ["narrate", "地の文", "📝"],
    ["charExit", "キャラ退場", "🚪"],
    ["bg", "背景変更", "🖼"],
    ["cg", "CG表示", "🌅"],
    ["blackout", "暗転", "🌑"],
    ["compVis", "コンポーネント表示・消去", "👁"],
    ["bgm", "BGM", "🎵"],
    ["se", "効果音(SE)", "🔊"],
    ["nameInput", "文字入力(名前/パスワード等)", "🔤"],
    ["setVar", "変数操作", "🔢"],
    ["gauge", "ゲージ操作", "📊"],
    ["item", "アイテム", "🎒"],
    ["choice", "選択肢分岐", "🔀"],
    ["if", "条件分岐", "❓"],
    ["jump", "シーン移動", "➡"],
    ["label", "フラグ地点", "🚩"],
    ["labelJump", "フラグへジャンプ", "🎯"],
    ["endroll", "エンドロール", "🎞"],
    ["ending", "エンディング", "🏁"],
  ];
  const CMD_LABEL = {}, CMD_ICON = {};
  COMMAND_TYPES.forEach(([t, l, i]) => { CMD_LABEL[t] = l; CMD_ICON[t] = i; });

  const NO_SPRITE = "__none__";
  const SAY_POSITIONS = [["left", "左"], ["center", "中央"], ["right", "右"]];
  const VAR_OPS = [["set", "代入 ="], ["add", "加算 +="], ["sub", "減算 -="],
                   ["mul", "乗算 *="], ["toggle", "反転(真偽)"]];
  const GAUGE_OPS = [["set", "代入 ="], ["add", "加算 +="], ["sub", "減算 -="]];
  const COMP_TARGETS = [["message", "セリフ枠"], ["sprite", "立ち絵"],
                        ["gauges", "ゲージ"], ["items", "アイテムボタン"], ["menu", "メニュー"]];

  // 各コマンドのフィールド定義（汎用フォーム描画に使用）
  // t: str/text/num/bool/select/cond/choices ; src: 選択肢の元
  const COMMAND_FIELDS = {
    say: [
      { k: "charId", label: "キャラ", t: "select", src: "char", none: "（地の文）" },
      { k: "exprId", label: "表情", t: "select", src: "expr" },
      { k: "pos", label: "立ち絵の位置", t: "select", src: "pos" },
      { k: "text", label: "セリフ", t: "text" },
      { k: "hideSprite", label: "このセリフでは立ち絵を表示しない", t: "bool" },
    ],
    narrate: [{ k: "text", label: "本文", t: "text" }],
    charExit: [{ k: "charId", label: "退場するキャラ", t: "select", src: "char", none: "（全員）" }],
    bg: [{ k: "bgId", label: "背景", t: "select", src: "bg", none: "（変更なし）" }],
    cg: [
      { k: "action", label: "動作", t: "select", src: "cgAction" },
      { k: "cgId", label: "CG", t: "select", src: "cg", none: "（CGを選択）" },
    ],
    blackout: [
      { k: "mode", label: "動作", t: "select", src: "blackoutMode" },
      { k: "hideUi", label: "画面上のコンポーネントも消す", t: "bool" },
    ],
    compVis: [
      { k: "target", label: "コンポーネント", t: "select", src: "compTarget" },
      { k: "action", label: "動作", t: "select", src: "compAction" },
    ],
    bgm: [
      { k: "action", label: "動作", t: "select", src: "bgmAction" },
      { k: "bgmId", label: "曲", t: "select", src: "bgm", none: "（なし）" },
      { k: "loop", label: "ループ再生する", t: "bool" },
      { k: "fadeMs", label: "フェード(ms)", t: "num" },
    ],
    se: [{ k: "seId", label: "効果音", t: "select", src: "se", none: "（効果音を選択）" }],
    nameInput: [
      { k: "varName", label: "格納先(文字列変数)", t: "select", src: "strvar", none: "（変数を選択）" },
      { k: "prompt", label: "メッセージ", t: "str" },
      { k: "inputType", label: "入力方式", t: "select", src: "inputType" },
    ],
    setVar: [
      { k: "varName", label: "変数", t: "select", src: "anyvar", none: "（変数を選択）" },
      { k: "op", label: "操作", t: "select", src: "varOp" },
      { k: "value", label: "値", t: "str" },
    ],
    gauge: [
      { k: "gaugeId", label: "ゲージ", t: "select", src: "gauge", none: "（ゲージを選択）" },
      { k: "op", label: "操作", t: "select", src: "gaugeOp" },
      { k: "value", label: "値", t: "str" },
    ],
    item: [
      { k: "itemId", label: "アイテム", t: "select", src: "item", none: "（アイテムを選択）" },
      { k: "action", label: "動作", t: "select", src: "itemAction" },
      { k: "notify", label: "入手/使用メッセージを表示する", t: "bool" },
    ],
    choice: [
      { k: "prompt", label: "問いかけ", t: "str" },
      { k: "options", label: "選択肢", t: "choices" },
    ],
    if: [
      { k: "condition", label: "条件", t: "cond" },
      { k: "targetTrue", label: "条件成立時", t: "select", src: "scene", none: "（次のコマンドへ）" },
      { k: "targetFalse", label: "不成立時", t: "select", src: "scene", none: "（次のコマンドへ）" },
    ],
    jump: [{ k: "targetScene", label: "移動先シーン", t: "select", src: "scene", none: "（シーンを選択）" }],
    label: [{ k: "name", label: "フラグ地点名", t: "str" }],
    labelJump: [
      { k: "target", label: "ジャンプ先フラグ", t: "str" },
      { k: "condition", label: "ジャンプ条件（空＝常に）", t: "cond" },
    ],
    endroll: [
      { k: "text", label: "本文", t: "text" },
      { k: "speed", label: "スクロール速度(px/秒)", t: "num" },
      { k: "noSkip", label: "スキップ不可にする", t: "bool" },
    ],
    ending: [{ k: "endingId", label: "エンディング", t: "select", src: "ending", none: "（エンディングを選択）" }],
  };

  function emptyCondition() { return { logic: "and", terms: [] }; }

  function newCommand(type) {
    const base = { id: uid("cmd"), type: type };
    const d = {
      say: { charId: "", exprId: "", text: "", hideSprite: false, pos: "center" },
      narrate: { text: "" },
      charExit: { charId: "" },
      bg: { bgId: "" },
      cg: { cgId: "", action: "show" },
      blackout: { mode: "on", hideUi: false },
      compVis: { target: "message", action: "hide" },
      bgm: { action: "play", bgmId: "", loop: true, fadeMs: 0 },
      se: { seId: "" },
      nameInput: { varName: "", prompt: "名前を入力してください", inputType: "text" },
      setVar: { varName: "", op: "set", value: "0" },
      gauge: { gaugeId: "", op: "add", value: "1" },
      item: { itemId: "", action: "add", notify: true },
      choice: { prompt: "", options: [
        { id: uid("opt"), text: "選択肢1", targetScene: "", condition: emptyCondition() },
        { id: uid("opt"), text: "選択肢2", targetScene: "", condition: emptyCondition() },
      ] },
      if: { condition: emptyCondition(), targetTrue: "", targetFalse: "" },
      jump: { targetScene: "" },
      label: { name: "" },
      labelJump: { target: "", condition: emptyCondition() },
      endroll: { text: "", speed: 60, noSkip: false },
      ending: { endingId: "" },
    }[type] || {};
    return Object.assign(base, d);
  }

  // 資源参照ヘルパ
  function byId(list, id) { return (list || []).find((e) => e.id === id); }
  function short(s, n) { s = (s || "").replace(/\n/g, " "); n = n || 40; return s.length <= n ? s : s.slice(0, n - 1) + "…"; }

  function describe(cmd, p) {
    const t = cmd.type;
    const sc = (id) => { const s = byId(p.scenes, id); return s ? s.name : "（未設定）"; };
    if (t === "say") {
      const ch = byId(p.characters, cmd.charId);
      const pos = { left: "[左]", right: "[右]" }[cmd.pos] || "";
      return `${pos}${ch ? ch.name : "（地の文）"}「${short(cmd.text)}」`;
    }
    if (t === "narrate") return short(cmd.text);
    if (t === "charExit") { const c = byId(p.characters, cmd.charId); return "キャラ退場 → " + (c ? c.name : "（全員）"); }
    if (t === "bg") { const b = byId(p.backgrounds, cmd.bgId); return "背景 → " + (b ? b.name : "（未設定）"); }
    if (t === "cg") { if (cmd.action === "hide") return "CGを消す"; const c = byId(p.cg, cmd.cgId); return "CG表示 → " + (c ? c.name : "（未設定）"); }
    if (t === "blackout") return cmd.mode === "on" ? (cmd.hideUi ? "暗転する（UIも消す）" : "暗転する") : "暗転を解除";
    if (t === "compVis") { const n = (COMP_TARGETS.find((x) => x[0] === cmd.target) || [, "?"])[1]; return `${n} を ${cmd.action === "show" ? "表示" : "消去"}`; }
    if (t === "bgm") { const f = cmd.fadeMs ? `（フェード${cmd.fadeMs}ms）` : ""; if (cmd.action === "stop") return "BGM停止" + f; const b = byId(p.bgm, cmd.bgmId); return `BGM再生 → ${b ? b.name : "（未設定）"}${cmd.loop ? "（ループ）" : ""}${f}`; }
    if (t === "se") { const s = byId(p.se, cmd.seId); return "効果音 → " + (s ? s.name : "（未設定）"); }
    if (t === "nameInput") return `文字入力${cmd.inputType === "password" ? "(伏字)" : ""} → 変数「${cmd.varName || "?"}」`;
    if (t === "setVar") { const o = (VAR_OPS.find((x) => x[0] === cmd.op) || [, ""])[1]; return `変数 ${cmd.varName || "?"} ${o} ${cmd.value}`; }
    if (t === "gauge") { const g = byId(p.gauges, cmd.gaugeId); const o = (GAUGE_OPS.find((x) => x[0] === cmd.op) || [, ""])[1]; return `ゲージ「${g ? g.name : "?"}」 ${o} ${cmd.value}`; }
    if (t === "item") { const it = byId(p.items, cmd.itemId); const a = { add: "入手", remove: "破棄", use: "使用" }[cmd.action] || "?"; return `アイテム ${a} → ${it ? it.name : "（未設定）"}`; }
    if (t === "choice") return `選択肢分岐（${(cmd.options || []).length}択）` + (cmd.prompt ? "：" + short(cmd.prompt, 20) : "");
    if (t === "if") return `条件分岐（${(cmd.condition && cmd.condition.terms || []).length}件）`;
    if (t === "jump") return "シーン移動 → " + sc(cmd.targetScene);
    if (t === "label") return "🚩 フラグ地点: " + (cmd.name || "（未設定）");
    if (t === "labelJump") return "フラグへジャンプ → " + (cmd.target || "（未設定）");
    if (t === "endroll") return `エンドロール（${short(cmd.text, 20)}${cmd.noSkip ? "・スキップ不可" : ""}）`;
    if (t === "ending") { const e = byId(p.endings, cmd.endingId); return "エンディング → " + (e ? (e.hidden ? "🔒" : "") + e.name : "（未設定）"); }
    return t;
  }

  // ------- リソース定義（フィールドと新規値） -------
  function makeProjectDefault() {
    const hero = uid("char"), e1 = uid("expr");
    const s = uid("scene"), end = uid("end");
    return {
      meta: { title: "新しいノベルゲーム", author: "", startScene: s,
              titleBg: "", titleBgm: "", font: "", fontPath: "", fontScale: 100,
              msgFontScale: 100, titleLogoImage: "", titleColor: "#ffffff", titleVariations: [] },
      variables: [{ id: uid("var"), name: "playerName", type: "string", initial: "主人公" }],
      systemVars: [],
      gauges: [], characters: [{ id: hero, name: "キャラ1", color: "#ffb6c1",
        isProtagonist: false, showSprite: true, expressions: [{ id: e1, name: "通常", image: "" }] }],
      items: [], backgrounds: [{ id: uid("bg"), name: "背景1", image: "", color: "#33405e" }],
      cg: [], bgm: [], se: [],
      endings: [{ id: end, name: "エンド", hidden: false, desc: "おわり" }],
      scenes: [{ id: s, name: "シーン1", commands: [
        { id: uid("cmd"), type: "say", charId: hero, exprId: e1, pos: "center", text: "はじめまして！", hideSprite: false },
        { id: uid("cmd"), type: "ending", endingId: end },
      ] }],
      layout: {}, theme: {},
    };
  }

  root.NovelModel = {
    uid, COMMAND_TYPES, CMD_LABEL, CMD_ICON, COMMAND_FIELDS, newCommand, describe,
    emptyCondition, byId, NO_SPRITE, SAY_POSITIONS, VAR_OPS, GAUGE_OPS, COMP_TARGETS,
    makeProjectDefault,
  };
})(typeof window !== "undefined" ? window : globalThis);
