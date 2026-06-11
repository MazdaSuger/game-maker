"""ゲーム実行エンジン（純粋ロジック・Qt非依存）.

:class:`Runtime` はプロジェクトを解釈してノベルゲームを進行させる
ステートマシン。UI（player.py）は ``advance()`` を呼び出して
次に表示すべき「イベント」を受け取り、画面を描画する。

UI への依存が無いため、単体テストやヘッドレス検証が可能。
"""

from __future__ import annotations

import re
from typing import Any, Optional

from .model import Project, NO_SPRITE

# テキスト内の {変数名} を置換するためのパターン
_VAR_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


# ---------------------------------------------------------------------------
# 条件評価（純粋関数）
# ---------------------------------------------------------------------------
def _to_number(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _compare(left: float, op: str, right: float) -> bool:
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    return False


def evaluate_condition(cond: Optional[dict], state: "GameState") -> bool:
    """条件式 ``cond`` を現在の状態で評価する。

    terms が空、または cond が None の場合は常に True。
    """
    if not cond:
        return True
    terms = cond.get("terms", [])
    if not terms:
        return True
    logic = cond.get("logic", "and")
    results = [_eval_term(t, state) for t in terms]
    return all(results) if logic == "and" else any(results)


def _read_var(state: "GameState", name: str):
    """変数を読む。ローカル変数→システム変数の順に解決する。"""
    if name in state.variables:
        return state.variables[name]
    sysd = getattr(state, "system", None)
    if sysd and name in sysd.get("vars", {}):
        return sysd["vars"][name]
    return None


def _eval_term(term: dict, state: "GameState") -> bool:
    kind = term.get("kind")
    ref = term.get("ref", "")
    op = term.get("op", "==")
    raw = term.get("value", "")

    if kind == "var":
        val = _read_var(state, ref)
        # 真偽値の比較（"true"/"false" や 1/0 を許容）
        if isinstance(val, bool):
            want = str(raw).strip().lower() in ("true", "1", "はい", "yes", "on")
            if op == "==":
                return val == want
            if op == "!=":
                return val != want
            return False
        # 文字列同士の比較を試みる
        if isinstance(val, str) and not _looks_numeric(val):
            if op == "==":
                return val == str(raw)
            if op == "!=":
                return val != str(raw)
            # 文字列に大小比較はとりあえず辞書順
            return _compare_str(val, op, str(raw))
        return _compare(_to_number(val), op, _to_number(raw))

    if kind == "gauge":
        val = state.gauges.get(ref, 0)
        return _compare(_to_number(val), op, _to_number(raw))

    if kind == "ending":
        # エンディング到達回数（システムデータ）
        sysd = getattr(state, "system", None) or {}
        cnt = (sysd.get("endings", {}) or {}).get(ref, 0)
        return _compare(_to_number(cnt), op, _to_number(raw))

    if kind == "allEndings":
        # 全エンディングを1回以上解放したか
        ids = getattr(state, "_all_ending_ids", []) or []
        if not ids:
            return False
        sysd = getattr(state, "system", None) or {}
        ec = sysd.get("endings", {}) or {}
        return all(_to_number(ec.get(i, 0)) >= 1 for i in ids)

    if kind == "item":
        has = ref in state.items
        if op == "has":
            return has
        if op == "notHas":
            return not has
        return False

    return False


def _looks_numeric(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def _compare_str(a: str, op: str, b: str) -> bool:
    if op == ">":
        return a > b
    if op == ">=":
        return a >= b
    if op == "<":
        return a < b
    if op == "<=":
        return a <= b
    return False


# ---------------------------------------------------------------------------
# ゲーム状態
# ---------------------------------------------------------------------------
class GameState:
    """セーブ/ロード対象となる実行時状態。"""

    def __init__(self):
        self.variables: dict[str, Any] = {}
        self.gauges: dict[str, float] = {}
        self.items: list[str] = []            # 所持アイテムID
        self.scene_id: str = ""
        self.cmd_index: int = 0
        # 表示状態
        self.bg_id: str = ""
        self.blackout: bool = False
        self.blackout_hide_ui: bool = False   # 暗転時にUIも消すか
        # コンポーネント表示上書き（key→True=消去/False=表示）。空はレイアウト設定に従う
        self.comp_override: dict[str, bool] = {}
        self.cg_id: str = ""                  # 表示中のCG（""=なし）
        # 立ち絵：最大3人（{"left":{"charId","exprId"}, ...}）
        self.sprites: dict[str, dict] = {}
        self.bgm_id: str = ""                 # 再生中BGM
        self.bgm_fade: int = 0                # 直近のBGM切替フェード(ms)
        self.discovered_endings: list[str] = []  # 到達済みエンディング

    # --- シリアライズ ---
    def to_dict(self) -> dict:
        return {
            "variables": self.variables,
            "gauges": self.gauges,
            "items": self.items,
            "scene_id": self.scene_id,
            "cmd_index": self.cmd_index,
            "bg_id": self.bg_id,
            "blackout": self.blackout,
            "blackout_hide_ui": self.blackout_hide_ui,
            "comp_override": self.comp_override,
            "cg_id": self.cg_id,
            "sprites": self.sprites,
            "bgm_id": self.bgm_id,
            "bgm_fade": self.bgm_fade,
            "discovered_endings": self.discovered_endings,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GameState":
        s = cls()
        s.variables = dict(d.get("variables", {}))
        s.gauges = dict(d.get("gauges", {}))
        s.items = list(d.get("items", []))
        s.scene_id = d.get("scene_id", "")
        s.cmd_index = d.get("cmd_index", 0)
        s.bg_id = d.get("bg_id", "")
        s.blackout = d.get("blackout", False)
        s.blackout_hide_ui = d.get("blackout_hide_ui", False)
        s.comp_override = dict(d.get("comp_override", {}))
        s.cg_id = d.get("cg_id", "")
        # 立ち絵：新形式 sprites、無ければ旧 char_id/expr_id から移行
        if "sprites" in d and isinstance(d["sprites"], dict):
            s.sprites = {k: dict(v) for k, v in d["sprites"].items()}
        elif d.get("char_id"):
            s.sprites = {"center": {"charId": d.get("char_id", ""),
                                    "exprId": d.get("expr_id", "")}}
        s.bgm_id = d.get("bgm_id", "")
        s.bgm_fade = d.get("bgm_fade", 0)
        s.discovered_endings = list(d.get("discovered_endings", []))
        return s


# ---------------------------------------------------------------------------
# Runtime（インタプリタ）
# ---------------------------------------------------------------------------
class _MemStore:
    """永続化しないインメモリのシステムストア（既定）。"""

    def __init__(self):
        self.data = {"vars": {}, "endings": {}}

    def save(self):
        pass


class Runtime:
    """ノベルゲームを進行させるインタプリタ。

    返すイベント（dict）の ``kind``:
      - ``say``      : セリフ表示。name/color/text/charId/exprId
      - ``narrate``  : 地の文。text
      - ``choice``   : 選択肢。prompt/options[{text, index}]
      - ``nameInput``: 名前入力。prompt/varName
      - ``ending``   : エンディング。name/desc/hidden
      - ``end``      : シーン終端に到達（次が無い）
    いずれのイベントにも ``state`` への変更が反映済み。UI は
    ``runtime.state`` を読んでステージ(背景/キャラ/ゲージ等)を再描画する。
    """

    def __init__(self, project: Project, system_store=None):
        self.project = project
        # システムデータ（ゲーム全体で共有・永続）。store.data = {"vars":{}, "endings":{}}
        self.system = system_store or _MemStore()
        self.system.data.setdefault("vars", {})
        self.system.data.setdefault("endings", {})
        self._sysnames = {v.get("name") for v in project.data.get("systemVars", [])}
        self.state = GameState()
        self._pending: Optional[dict] = None  # 入力待ちイベント
        self._sfx: list[str] = []             # この区間で再生するSE

    def _init_system_vars(self):
        """システム変数を（未登録なら）初期値で用意する。値は永続。"""
        changed = False
        for v in self.project.data.get("systemVars", []):
            name = v.get("name")
            if name and name not in self.system.data["vars"]:
                self.system.data["vars"][name] = _initial_var_value(v)
                changed = True
        if changed:
            self.system.save()

    # --- 開始 / ロード ------------------------------------------------
    def start(self, start_scene: Optional[str] = None) -> dict:
        """初期状態を構築してゲームを開始する。

        ``start_scene`` を指定すると、そのシーンから開始する
        （選択シーンからのテストプレイに使用）。
        """
        st = GameState()
        for v in self.project.variables:
            st.variables[v["name"]] = _initial_var_value(v)
        for g in self.project.gauges:
            st.gauges[g["id"]] = _to_number(g.get("initial", 0))
        st.scene_id = start_scene or self.project.meta.get("startScene", "")
        if not st.scene_id and self.project.scenes:
            st.scene_id = self.project.scenes[0]["id"]
        st.cmd_index = 0
        self._init_system_vars()
        st.system = self.system.data          # システムデータへの参照
        st._all_ending_ids = [e["id"] for e in self.project.endings]
        self.state = st
        self._pending = None
        return self.advance()

    def load_state(self, state: GameState) -> dict:
        """セーブ状態から再開する。"""
        self._init_system_vars()
        state.system = self.system.data
        state._all_ending_ids = [e["id"] for e in self.project.endings]
        self.state = state
        return self.advance()

    # --- 進行 ---------------------------------------------------------
    def advance(self, text_input: Optional[str] = None) -> dict:
        """ブロッキングコマンドに当たるまでコマンドを処理し、
        表示すべきイベントを返す。

        直前が名前入力イベントの場合、``text_input`` に入力文字列を渡す。
        """
        # 直前のブロッキングイベントを解決して次のコマンドへ進める
        if self._pending:
            kind = self._pending.get("kind")
            if kind == "nameInput":
                var = self._pending.get("varName", "")
                if var:
                    self.state.variables[var] = text_input or ""
                self.state.cmd_index += 1
            elif kind in ("say", "narrate", "endroll", "itemGet"):
                self.state.cmd_index += 1
            # choice は choose() で解決。ending/end は終端
            self._pending = None

        return self._run()

    def choose(self, option_index: int) -> dict:
        """選択肢を選んだときに呼ぶ。対象シーンへジャンプする。"""
        if not self._pending or self._pending.get("kind") != "choice":
            return self._run()
        opts = self._pending.get("_options_raw", [])
        if 0 <= option_index < len(opts):
            target = opts[option_index].get("targetScene", "")
            self._pending = None
            if target:
                self._goto_scene(target)
            else:
                self.state.cmd_index += 1
        return self._run()

    # --- 内部実行ループ ----------------------------------------------
    def _run(self) -> dict:
        guard = 0  # 無限ループ保護
        self._sfx = []  # この区間で鳴らすSEを集める
        while True:
            guard += 1
            if guard > 100000:
                return self._with_sfx({"kind": "end", "reason": "loop-guard"})

            scene = self.project.scene(self.state.scene_id)
            if scene is None:
                return self._with_sfx({"kind": "end", "reason": "no-scene"})
            cmds = scene.get("commands", [])
            if self.state.cmd_index >= len(cmds):
                return self._with_sfx({"kind": "end", "reason": "scene-finished"})

            cmd = cmds[self.state.cmd_index]
            event = self._exec(cmd)
            if event is not None:
                # ブロッキングイベント：返して停止
                self._pending = event
                return self._with_sfx(event)
            # 非ブロッキング：ジャンプ系で cmd_index を動かさなかった場合のみ進める
            # _exec が False を返した（=ジャンプ済み）場合は進めない
            if cmd.get("_jumped"):
                cmd.pop("_jumped", None)
            else:
                self.state.cmd_index += 1

    def _exec(self, cmd: dict) -> Optional[dict]:
        """1コマンドを実行。ブロッキングならイベントdictを返し、
        非ブロッキングなら None を返す。"""
        t = cmd.get("type")

        if t == "say":
            cid = cmd.get("charId", "")
            ch = self.project.character(cid)
            expr_id = cmd.get("exprId", "")
            pos = cmd.get("pos", "center")
            if pos not in ("left", "center", "right"):
                pos = "center"
            # 立ち絵を配置する条件：showSprite かつ hideSprite でない
            show = bool(ch.get("showSprite", True)) if ch else False
            if cmd.get("hideSprite", False):
                show = False
            if show and cid:
                # 同一キャラは1スロットだけに（他スロットから取り除く）
                for p in list(self.state.sprites.keys()):
                    if self.state.sprites[p].get("charId") == cid and p != pos:
                        del self.state.sprites[p]
                self.state.sprites[pos] = {"charId": cid, "exprId": expr_id}
            return {
                "kind": "say",
                "name": ch["name"] if ch else "",
                "color": ch.get("color", "#ffffff") if ch else "#ffffff",
                "text": self._interp(cmd.get("text", "")),
                "speaker": cid,
            }

        if t == "narrate":
            return {"kind": "narrate", "text": self._interp(cmd.get("text", ""))}

        if t == "charExit":
            target = cmd.get("charId", "")
            if not target:
                self.state.sprites = {}        # 全員退場
            else:
                for p in list(self.state.sprites.keys()):
                    if self.state.sprites[p].get("charId") == target:
                        del self.state.sprites[p]
            return None

        if t == "bg":
            self.state.bg_id = cmd.get("bgId", "")
            return None

        if t == "blackout":
            on = (cmd.get("mode", "on") == "on")
            self.state.blackout = on
            self.state.blackout_hide_ui = on and bool(cmd.get("hideUi", False))
            return None

        if t == "compVis":
            target = cmd.get("target", "")
            if target:
                self.state.comp_override[target] = (cmd.get("action") == "hide")
            return None

        if t == "bgm":
            self.state.bgm_fade = int(cmd.get("fadeMs", 0) or 0)
            if cmd.get("action") == "stop":
                self.state.bgm_id = ""
            else:
                self.state.bgm_id = cmd.get("bgmId", "")
            return None

        if t == "endroll":
            return {"kind": "endroll",
                    "text": self._interp(cmd.get("text", "")),
                    "speed": _to_number(cmd.get("speed", 60)) or 60,
                    "noSkip": bool(cmd.get("noSkip", False))}

        if t == "se":
            sid = cmd.get("seId", "")
            if sid:
                self._sfx.append(sid)
            return None

        if t == "cg":
            if cmd.get("action") == "hide":
                self.state.cg_id = ""
            else:
                self.state.cg_id = cmd.get("cgId", "")
            return None

        if t == "nameInput":
            return {"kind": "nameInput",
                    "prompt": cmd.get("prompt", "名前を入力"),
                    "varName": cmd.get("varName", ""),
                    "inputType": cmd.get("inputType", "text")}

        if t == "setVar":
            self._apply_setvar(cmd)
            return None

        if t == "gauge":
            self._apply_gauge(cmd)
            return None

        if t == "item":
            iid = cmd.get("itemId", "")
            if not iid:
                return None
            action = cmd.get("action", "add")
            notify = cmd.get("notify", True)
            item = self.project.item(iid)
            if action == "remove":
                if iid in self.state.items:
                    self.state.items.remove(iid)
                return None
            if action == "use":
                # 使用＝所持していれば（消費するアイテムなら）取り除く
                if iid in self.state.items:
                    if item is None or item.get("consumable", True):
                        self.state.items.remove(iid)
                    if notify and item:
                        return self._item_event(item, "use")
                return None
            # add（入手）
            if iid not in self.state.items:
                self.state.items.append(iid)
            if notify and item:
                return self._item_event(item, "get")
            return None

        if t == "choice":
            return self._build_choice(cmd)

        if t == "if":
            ok = evaluate_condition(cmd.get("condition"), self.state)
            target = cmd.get("targetTrue") if ok else cmd.get("targetFalse")
            if target:
                self._goto_scene(target)
                cmd["_jumped"] = True
            # target 未設定なら通常どおり次のコマンドへ
            return None

        if t == "jump":
            target = cmd.get("targetScene", "")
            if target:
                self._goto_scene(target)
                cmd["_jumped"] = True
            return None

        if t == "label":
            return None  # 位置マーカー（何もしない）

        if t == "labelJump":
            if evaluate_condition(cmd.get("condition"), self.state):
                loc = self._find_label(cmd.get("target", ""))
                if loc is not None:
                    self.state.scene_id, self.state.cmd_index = loc
                    cmd["_jumped"] = True
            return None

        if t == "ending":
            end = self.project.ending(cmd.get("endingId", ""))
            if end:
                if end["id"] not in self.state.discovered_endings:
                    self.state.discovered_endings.append(end["id"])
                # システムデータ：エンディング到達回数を加算して永続化
                eid = end["id"]
                ec = self.system.data.setdefault("endings", {})
                ec[eid] = int(ec.get(eid, 0)) + 1
                self.system.save()
            return {
                "kind": "ending",
                "name": end["name"] if end else "エンディング",
                "desc": end.get("desc", "") if end else "",
                "hidden": end.get("hidden", False) if end else False,
                "cgId": end.get("cgId", "") if end else "",
                "count": self.system.data["endings"].get(end["id"], 0) if end else 0,
            }

        # 未知のコマンドは無視
        return None

    def _item_event(self, item: dict, verb: str) -> dict:
        """アイテム入手/使用の演出イベントを作る。"""
        return {
            "kind": "itemGet",
            "itemId": item.get("id", ""),
            "name": item.get("name", ""),
            "desc": item.get("desc", ""),
            "icon": item.get("icon", ""),
            "image": item.get("image", ""),
            "verb": verb,  # get / use
        }

    def _with_sfx(self, event: dict) -> dict:
        """イベントに、この区間で再生するSE一覧を添える。"""
        if self._sfx:
            event["sfx"] = list(self._sfx)
            self._sfx = []
        return event

    # --- ヘルパー -----------------------------------------------------
    def _goto_scene(self, sid: str):
        self.state.scene_id = sid
        self.state.cmd_index = 0

    def _find_label(self, name: str):
        """フラグ地点(label)を探す。まず現在シーン、無ければ全シーン。"""
        if not name:
            return None
        cur = self.project.scene(self.state.scene_id)
        scenes = ([cur] if cur else []) + [s for s in self.project.scenes if s is not cur]
        for s in scenes:
            for i, c in enumerate(s.get("commands", [])):
                if c.get("type") == "label" and c.get("name") == name:
                    return (s["id"], i)
        return None

    def _interp(self, text: str) -> str:
        """テキスト内の {変数名} を現在値で置換する（ローカル→システム）。"""
        def repl(m):
            name = m.group(1)
            val = _read_var(self.state, name)
            return str(val) if val is not None else m.group(0)
        return _VAR_PATTERN.sub(repl, text)

    def _var_container(self, name: str):
        """変数名の格納先を返す。(dict, 永続フラグ)。

        システム変数として定義された名前ならシステムストアへ、
        それ以外はローカル変数へ書き込む。"""
        if name in self._sysnames:
            return self.system.data["vars"], True
        return self.state.variables, False

    def _apply_setvar(self, cmd: dict):
        name = cmd.get("varName", "")
        if not name:
            return
        op = cmd.get("op", "set")
        raw = cmd.get("value", "")
        store, persist = self._var_container(name)
        cur = store.get(name)

        if op == "toggle":
            store[name] = not bool(cur)
        elif op == "set":
            # 真偽値変数なら真偽に、数値なら数値に、それ以外は文字列に
            if isinstance(cur, bool):
                store[name] = str(raw).strip().lower() in (
                    "true", "1", "はい", "yes", "on")
            elif isinstance(cur, (int, float)) and _looks_numeric(str(raw)):
                store[name] = _to_number(raw)
            elif _looks_numeric(str(raw)) and (cur is None or _looks_numeric(str(cur))):
                store[name] = _to_number(raw)
            else:
                store[name] = str(raw)
        else:
            # 算術系
            base = _to_number(cur)
            delta = _to_number(raw)
            if op == "add":
                base += delta
            elif op == "sub":
                base -= delta
            elif op == "mul":
                base *= delta
            store[name] = int(base) if base == int(base) else base
        if persist:
            self.system.save()

    def _apply_gauge(self, cmd: dict):
        gid = cmd.get("gaugeId", "")
        g = self.project.gauge(gid)
        if not g:
            return
        op = cmd.get("op", "add")
        delta = _to_number(cmd.get("value", "0"))
        cur = _to_number(self.state.gauges.get(gid, g.get("initial", 0)))
        if op == "set":
            cur = delta
        elif op == "add":
            cur += delta
        elif op == "sub":
            cur -= delta
        # min/max でクランプ
        lo = _to_number(g.get("min", 0))
        hi = _to_number(g.get("max", 100))
        cur = max(lo, min(hi, cur))
        self.state.gauges[gid] = cur

    def _build_choice(self, cmd: dict) -> dict:
        visible = []
        raw = []
        for opt in cmd.get("options", []):
            if evaluate_condition(opt.get("condition"), self.state):
                visible.append({"text": self._interp(opt.get("text", "")),
                                "index": len(raw)})
                raw.append(opt)
        return {
            "kind": "choice",
            "prompt": self._interp(cmd.get("prompt", "")),
            "options": visible,
            "_options_raw": raw,
        }


def _initial_var_value(v: dict) -> Any:
    t = v.get("type", "string")
    init = v.get("initial")
    if t == "number":
        return _to_number(init)
    if t == "boolean":
        if isinstance(init, bool):
            return init
        return str(init).strip().lower() in ("true", "1", "はい", "yes", "on")
    return "" if init is None else str(init)
