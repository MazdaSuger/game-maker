/* ============================================================
 *  engine.js — ブラウザ版ゲーム実行エンジン
 * ------------------------------------------------------------
 *  novelmaker/runtime.py を JavaScript へ移植したもの。
 *  DOM には依存しない純粋ロジック（Node でもテスト可能）。
 *  ブラウザでは window.NovelEngine として公開する。
 * ============================================================ */
(function (root) {
  "use strict";

  const VAR_PATTERN = /\{([A-Za-z_][A-Za-z0-9_]*)\}/g;
  const NO_SPRITE = "__none__";

  function toNumber(v) {
    const n = parseFloat(v);
    return isNaN(n) ? 0 : n;
  }

  function looksNumeric(s) {
    if (s === "" || s === null || s === undefined) return false;
    return !isNaN(parseFloat(s)) && isFinite(s);
  }

  function compare(left, op, right) {
    switch (op) {
      case "==": return left === right;
      case "!=": return left !== right;
      case ">":  return left > right;
      case ">=": return left >= right;
      case "<":  return left < right;
      case "<=": return left <= right;
      default:   return false;
    }
  }

  function compareStr(a, op, b) {
    switch (op) {
      case ">":  return a > b;
      case ">=": return a >= b;
      case "<":  return a < b;
      case "<=": return a <= b;
      default:   return false;
    }
  }

  // -------------------------------------------------------------------
  // 条件評価
  // -------------------------------------------------------------------
  function evaluateCondition(cond, state) {
    if (!cond) return true;
    const terms = cond.terms || [];
    if (terms.length === 0) return true;
    const logic = cond.logic || "and";
    const results = terms.map((t) => evalTerm(t, state));
    return logic === "and" ? results.every(Boolean) : results.some(Boolean);
  }

  function readVar(state, name) {
    if (Object.prototype.hasOwnProperty.call(state.variables, name))
      return state.variables[name];
    const sys = state.system;
    if (sys && sys.vars && Object.prototype.hasOwnProperty.call(sys.vars, name))
      return sys.vars[name];
    return undefined;
  }

  function evalTerm(term, state) {
    const kind = term.kind;
    const ref = term.ref || "";
    const op = term.op || "==";
    const raw = term.value !== undefined ? term.value : "";

    if (kind === "ending") {
      const sys = state.system || {};
      const cnt = (sys.endings || {})[ref] || 0;
      return compare(toNumber(cnt), op, toNumber(raw));
    }
    if (kind === "allEndings") {
      const ids = state._all_ending_ids || [];
      if (!ids.length) return false;
      const ec = (state.system || {}).endings || {};
      return ids.every((i) => toNumber(ec[i] || 0) >= 1);
    }
    if (kind === "var") {
      const val = readVar(state, ref);
      if (typeof val === "boolean") {
        const want = ["true", "1", "はい", "yes", "on"].includes(
          String(raw).trim().toLowerCase());
        if (op === "==") return val === want;
        if (op === "!=") return val !== want;
        return false;
      }
      if (typeof val === "string" && !looksNumeric(val)) {
        if (op === "==") return val === String(raw);
        if (op === "!=") return val !== String(raw);
        return compareStr(val, op, String(raw));
      }
      return compare(toNumber(val), op, toNumber(raw));
    }
    if (kind === "gauge") {
      const val = state.gauges[ref] !== undefined ? state.gauges[ref] : 0;
      return compare(toNumber(val), op, toNumber(raw));
    }
    if (kind === "item") {
      const has = state.items.includes(ref);
      if (op === "has") return has;
      if (op === "notHas") return !has;
      return false;
    }
    return false;
  }

  // -------------------------------------------------------------------
  // プロジェクト索引
  // -------------------------------------------------------------------
  function indexById(list) {
    const m = {};
    (list || []).forEach((e) => { m[e.id] = e; });
    return m;
  }

  // -------------------------------------------------------------------
  // Runtime
  // -------------------------------------------------------------------
  function Runtime(project, system, persist) {
    this.project = project;
    // システムデータ（永続・全体共有）
    this.system = system || { vars: {}, endings: {} };
    this.system.vars = this.system.vars || {};
    this.system.endings = this.system.endings || {};
    this._persist = typeof persist === "function" ? persist : function () {};
    this._sysnames = new Set((project.systemVars || []).map((v) => v.name));
    this._scenes = indexById(project.scenes);
    this._chars = indexById(project.characters);
    this._bgs = indexById(project.backgrounds);
    this._gauges = indexById(project.gauges);
    this._bgm = indexById(project.bgm);
    this._items = indexById(project.items);
    this._endings = indexById(project.endings);
    this.state = newState();
    this._pending = null;
  }

  function newState() {
    return {
      variables: {}, gauges: {}, items: [],
      scene_id: "", cmd_index: 0,
      bg_id: "", blackout: false, blackout_hide_ui: false, comp_override: {},
      cg_id: "", sprites: {}, bgm_id: "", bgm_fade: 0, discovered_endings: [],
    };
  }

  Runtime.prototype.character = function (id) { return this._chars[id] || null; };
  Runtime.prototype.expression = function (cid, eid) {
    const ch = this._chars[cid];
    if (!ch) return null;
    return (ch.expressions || []).find((e) => e.id === eid) || null;
  };
  Runtime.prototype.background = function (id) { return this._bgs[id] || null; };
  Runtime.prototype.gauge = function (id) { return this._gauges[id] || null; };
  Runtime.prototype.bgmTrack = function (id) { return this._bgm[id] || null; };
  Runtime.prototype.item = function (id) { return this._items[id] || null; };
  Runtime.prototype.ending = function (id) { return this._endings[id] || null; };
  Runtime.prototype.scene = function (id) { return this._scenes[id] || null; };

  Runtime.prototype._initSystemVars = function () {
    let changed = false;
    (this.project.systemVars || []).forEach((v) => {
      if (!Object.prototype.hasOwnProperty.call(this.system.vars, v.name)) {
        this.system.vars[v.name] = initialVarValue(v);
        changed = true;
      }
    });
    if (changed) this._persist();
  };

  Runtime.prototype.start = function (startScene) {
    const st = newState();
    (this.project.variables || []).forEach((v) => {
      st.variables[v.name] = initialVarValue(v);
    });
    (this.project.gauges || []).forEach((g) => {
      st.gauges[g.id] = toNumber(g.initial || 0);
    });
    st.scene_id = startScene || (this.project.meta && this.project.meta.startScene) || "";
    if (!st.scene_id && this.project.scenes.length) {
      st.scene_id = this.project.scenes[0].id;
    }
    st.cmd_index = 0;
    this._initSystemVars();
    st.system = this.system;
    st._all_ending_ids = (this.project.endings || []).map((e) => e.id);
    this.state = st;
    this._pending = null;
    return this.advance();
  };

  Runtime.prototype.loadState = function (state) {
    this._initSystemVars();
    state.system = this.system;
    state._all_ending_ids = (this.project.endings || []).map((e) => e.id);
    this.state = state;
    this._pending = null;
    return this.advance();
  };

  Runtime.prototype.advance = function (textInput) {
    if (this._pending) {
      const kind = this._pending.kind;
      if (kind === "nameInput") {
        const v = this._pending.varName;
        if (v) this.state.variables[v] = textInput || "";
        this.state.cmd_index += 1;
      } else if (kind === "say" || kind === "narrate" ||
                 kind === "endroll" || kind === "itemGet") {
        this.state.cmd_index += 1;
      }
      this._pending = null;
    }
    return this._run();
  };

  Runtime.prototype.choose = function (optionIndex) {
    if (!this._pending || this._pending.kind !== "choice") return this._run();
    const opts = this._pending._options_raw || [];
    if (optionIndex >= 0 && optionIndex < opts.length) {
      const target = opts[optionIndex].targetScene || "";
      this._pending = null;
      if (target) this._goto(target);
      else this.state.cmd_index += 1;
    } else {
      this._pending = null;
    }
    return this._run();
  };

  Runtime.prototype._goto = function (sid) {
    this.state.scene_id = sid;
    this.state.cmd_index = 0;
  };

  Runtime.prototype._findLabel = function (name) {
    if (!name) return null;
    const cur = this.scene(this.state.scene_id);
    const scenes = (cur ? [cur] : []).concat(
      (this.project.scenes || []).filter((s) => s !== cur));
    for (const s of scenes) {
      const cmds = s.commands || [];
      for (let i = 0; i < cmds.length; i++) {
        if (cmds[i].type === "label" && cmds[i].name === name) return [s.id, i];
      }
    }
    return null;
  };

  Runtime.prototype._run = function () {
    let guard = 0;
    this._sfx = [];
    while (true) {
      if (++guard > 100000) return this._withSfx({ kind: "end", reason: "loop-guard" });
      const scene = this.scene(this.state.scene_id);
      if (!scene) return this._withSfx({ kind: "end", reason: "no-scene" });
      const cmds = scene.commands || [];
      if (this.state.cmd_index >= cmds.length)
        return this._withSfx({ kind: "end", reason: "scene-finished" });
      const cmd = cmds[this.state.cmd_index];
      this._jumped = false;
      const event = this._exec(cmd);
      if (event !== null) {
        this._pending = event;
        return this._withSfx(event);
      }
      if (!this._jumped) this.state.cmd_index += 1;
    }
  };

  Runtime.prototype._withSfx = function (event) {
    if (this._sfx && this._sfx.length) {
      event.sfx = this._sfx.slice();
      this._sfx = [];
    }
    return event;
  };

  Runtime.prototype._interp = function (text) {
    const st = this.state;
    return String(text || "").replace(VAR_PATTERN, (m, name) => {
      const v = readVar(st, name);
      return v !== undefined ? String(v) : m;
    });
  };

  Runtime.prototype._exec = function (cmd) {
    const t = cmd.type;
    const st = this.state;

    if (t === "say") {
      const cid = cmd.charId || "";
      const ch = this.character(cid);
      const exprId = cmd.exprId || "";
      let pos = cmd.pos || "center";
      if (!["left", "center", "right"].includes(pos)) pos = "center";
      let show = ch ? (ch.showSprite !== false) : false;
      if (cmd.hideSprite) show = false;
      if (show && cid) {
        Object.keys(st.sprites).forEach((p) => {
          if (st.sprites[p].charId === cid && p !== pos) delete st.sprites[p];
        });
        st.sprites[pos] = { charId: cid, exprId: exprId };
      }
      return {
        kind: "say",
        name: ch ? ch.name : "",
        color: ch ? (ch.color || "#ffffff") : "#ffffff",
        text: this._interp(cmd.text),
        speaker: cid,
      };
    }
    if (t === "narrate") return { kind: "narrate", text: this._interp(cmd.text) };
    if (t === "charExit") {
      const target = cmd.charId || "";
      if (!target) { st.sprites = {}; }
      else {
        Object.keys(st.sprites).forEach((p) => {
          if (st.sprites[p].charId === target) delete st.sprites[p];
        });
      }
      return null;
    }
    if (t === "bg") { st.bg_id = cmd.bgId || ""; return null; }
    if (t === "blackout") {
      const on = (cmd.mode || "on") === "on";
      st.blackout = on;
      st.blackout_hide_ui = on && !!cmd.hideUi;
      return null;
    }
    if (t === "compVis") {
      if (cmd.target) st.comp_override[cmd.target] = (cmd.action === "hide");
      return null;
    }
    if (t === "bgm") {
      st.bgm_fade = parseInt(cmd.fadeMs || 0, 10) || 0;
      st.bgm_id = (cmd.action === "stop") ? "" : (cmd.bgmId || "");
      return null;
    }
    if (t === "endroll") {
      return { kind: "endroll", text: this._interp(cmd.text),
               speed: toNumber(cmd.speed) || 60, noSkip: !!cmd.noSkip };
    }
    if (t === "se") {
      if (cmd.seId) { this._sfx = this._sfx || []; this._sfx.push(cmd.seId); }
      return null;
    }
    if (t === "cg") {
      st.cg_id = (cmd.action === "hide") ? "" : (cmd.cgId || "");
      return null;
    }
    if (t === "nameInput") {
      return { kind: "nameInput", prompt: cmd.prompt || "名前を入力",
               varName: cmd.varName || "" };
    }
    if (t === "setVar") { this._applySetVar(cmd); return null; }
    if (t === "gauge") { this._applyGauge(cmd); return null; }
    if (t === "item") {
      const iid = cmd.itemId || "";
      if (!iid) return null;
      const action = cmd.action || "add";
      const notify = cmd.notify !== false;
      const item = this.item(iid);
      if (action === "remove") {
        st.items = st.items.filter((x) => x !== iid);
        return null;
      }
      if (action === "use") {
        if (st.items.includes(iid)) {
          const consumable = item ? (item.consumable !== false) : true;
          if (consumable) st.items = st.items.filter((x) => x !== iid);
          if (notify && item) return itemEvent(item, "use");
        }
        return null;
      }
      if (!st.items.includes(iid)) st.items.push(iid);
      if (notify && item) return itemEvent(item, "get");
      return null;
    }
    if (t === "choice") return this._buildChoice(cmd);
    if (t === "if") {
      const ok = evaluateCondition(cmd.condition, st);
      const target = ok ? cmd.targetTrue : cmd.targetFalse;
      if (target) { this._goto(target); this._jumped = true; }
      return null;
    }
    if (t === "jump") {
      if (cmd.targetScene) { this._goto(cmd.targetScene); this._jumped = true; }
      return null;
    }
    if (t === "label") return null;   // 位置マーカー
    if (t === "labelJump") {
      if (evaluateCondition(cmd.condition, st)) {
        const loc = this._findLabel(cmd.target || "");
        if (loc) { st.scene_id = loc[0]; st.cmd_index = loc[1]; this._jumped = true; }
      }
      return null;
    }
    if (t === "ending") {
      const end = this.ending(cmd.endingId);
      let count = 0;
      if (end) {
        if (!st.discovered_endings.includes(end.id))
          st.discovered_endings.push(end.id);
        this.system.endings[end.id] = (this.system.endings[end.id] || 0) + 1;
        count = this.system.endings[end.id];
        this._persist();
      }
      return {
        kind: "ending",
        name: end ? end.name : "エンディング",
        desc: end ? (end.desc || "") : "",
        hidden: end ? !!end.hidden : false,
        count: count,
      };
    }
    return null;
  };

  Runtime.prototype._applySetVar = function (cmd) {
    const name = cmd.varName;
    if (!name) return;
    const op = cmd.op || "set";
    const raw = cmd.value !== undefined ? cmd.value : "";
    const persist = this._sysnames.has(name);
    const store = persist ? this.system.vars : this.state.variables;
    const cur = store[name];

    if (op === "toggle") { store[name] = !cur; }
    else if (op === "set") {
      if (typeof cur === "boolean") {
        store[name] = ["true", "1", "はい", "yes", "on"]
          .includes(String(raw).trim().toLowerCase());
      } else if (typeof cur === "number" && looksNumeric(String(raw))) {
        store[name] = toNumber(raw);
      } else if (looksNumeric(String(raw)) &&
                 (cur === undefined || cur === null || looksNumeric(String(cur)))) {
        store[name] = toNumber(raw);
      } else {
        store[name] = String(raw);
      }
    } else {
      let base = toNumber(cur), delta = toNumber(raw);
      if (op === "add") base += delta;
      else if (op === "sub") base -= delta;
      else if (op === "mul") base *= delta;
      store[name] = base;
    }
    if (persist) this._persist();
  };

  Runtime.prototype._applyGauge = function (cmd) {
    const g = this.gauge(cmd.gaugeId);
    if (!g) return;
    const op = cmd.op || "add";
    const delta = toNumber(cmd.value);
    const st = this.state;
    let cur = toNumber(st.gauges[cmd.gaugeId] !== undefined
      ? st.gauges[cmd.gaugeId] : g.initial || 0);
    if (op === "set") cur = delta;
    else if (op === "add") cur += delta;
    else if (op === "sub") cur -= delta;
    const lo = toNumber(g.min || 0), hi = toNumber(g.max || 100);
    cur = Math.max(lo, Math.min(hi, cur));
    st.gauges[cmd.gaugeId] = cur;
  };

  Runtime.prototype._buildChoice = function (cmd) {
    const visible = [], raw = [];
    (cmd.options || []).forEach((opt) => {
      if (evaluateCondition(opt.condition, this.state)) {
        visible.push({ text: this._interp(opt.text), index: raw.length });
        raw.push(opt);
      }
    });
    return {
      kind: "choice",
      prompt: this._interp(cmd.prompt),
      options: visible,
      _options_raw: raw,
    };
  };

  function itemEvent(item, verb) {
    return {
      kind: "itemGet",
      itemId: item.id || "",
      name: item.name || "",
      desc: item.desc || "",
      icon: item.icon || "",
      image: item.image || "",
      verb: verb,
    };
  }

  function initialVarValue(v) {
    const t = v.type || "string";
    const init = v.initial;
    if (t === "number") return toNumber(init);
    if (t === "boolean") {
      if (typeof init === "boolean") return init;
      return ["true", "1", "はい", "yes", "on"].includes(
        String(init).trim().toLowerCase());
    }
    return init === undefined || init === null ? "" : String(init);
  }

  const api = { Runtime, evaluateCondition, newState };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;       // Node (テスト用)
  }
  root.NovelEngine = api;        // ブラウザ
})(typeof window !== "undefined" ? window : globalThis);
