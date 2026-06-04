"""ゲーム実行エンジン（純粋ロジック・Qt非依存）.

:class:`Runtime` はプロジェクトを解釈してノベルゲームを進行させる
ステートマシン。UI（player.py）は ``advance()`` を呼び出して
次に表示すべき「イベント」を受け取り、画面を描画する。

UI への依存が無いため、単体テストやヘッドレス検証が可能。
"""

from __future__ import annotations

import re
from typing import Any, Optional

from .model import Project

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


def _eval_term(term: dict, state: "GameState") -> bool:
    kind = term.get("kind")
    ref = term.get("ref", "")
    op = term.get("op", "==")
    raw = term.get("value", "")

    if kind == "var":
        val = state.variables.get(ref)
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
        self.char_id: str = ""                # 現在表示中のキャラ
        self.expr_id: str = ""
        self.bgm_id: str = ""                 # 再生中BGM
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
            "char_id": self.char_id,
            "expr_id": self.expr_id,
            "bgm_id": self.bgm_id,
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
        s.char_id = d.get("char_id", "")
        s.expr_id = d.get("expr_id", "")
        s.bgm_id = d.get("bgm_id", "")
        s.discovered_endings = list(d.get("discovered_endings", []))
        return s


# ---------------------------------------------------------------------------
# Runtime（インタプリタ）
# ---------------------------------------------------------------------------
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

    def __init__(self, project: Project):
        self.project = project
        self.state = GameState()
        self._pending: Optional[dict] = None  # 入力待ちイベント

    # --- 開始 / ロード ------------------------------------------------
    def start(self) -> dict:
        """初期状態を構築してゲームを開始する。"""
        st = GameState()
        for v in self.project.variables:
            st.variables[v["name"]] = _initial_var_value(v)
        for g in self.project.gauges:
            st.gauges[g["id"]] = _to_number(g.get("initial", 0))
        st.scene_id = self.project.meta.get("startScene", "")
        if not st.scene_id and self.project.scenes:
            st.scene_id = self.project.scenes[0]["id"]
        st.cmd_index = 0
        self.state = st
        return self.advance()

    def load_state(self, state: GameState) -> dict:
        """セーブ状態から再開する。"""
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
            elif kind in ("say", "narrate"):
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
        while True:
            guard += 1
            if guard > 100000:
                return {"kind": "end", "reason": "loop-guard"}

            scene = self.project.scene(self.state.scene_id)
            if scene is None:
                return {"kind": "end", "reason": "no-scene"}
            cmds = scene.get("commands", [])
            if self.state.cmd_index >= len(cmds):
                return {"kind": "end", "reason": "scene-finished"}

            cmd = cmds[self.state.cmd_index]
            event = self._exec(cmd)
            if event is not None:
                # ブロッキングイベント：返して停止
                self._pending = event
                return event
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
            ch = self.project.character(cmd.get("charId", ""))
            # 立ち絵を表示するキャラのみ、表示中の立ち絵を切り替える。
            # 主人公など showSprite=False のキャラは直前の立ち絵を維持する。
            show = bool(ch.get("showSprite", True)) if ch else False
            if show:
                self.state.char_id = cmd.get("charId", "")
                self.state.expr_id = cmd.get("exprId", "")
            return {
                "kind": "say",
                "name": ch["name"] if ch else "",
                "color": ch.get("color", "#ffffff") if ch else "#ffffff",
                "text": self._interp(cmd.get("text", "")),
                "charId": self.state.char_id,
                "exprId": self.state.expr_id,
            }

        if t == "narrate":
            return {"kind": "narrate", "text": self._interp(cmd.get("text", ""))}

        if t == "bg":
            self.state.bg_id = cmd.get("bgId", "")
            return None

        if t == "blackout":
            self.state.blackout = (cmd.get("mode", "on") == "on")
            return None

        if t == "bgm":
            if cmd.get("action") == "stop":
                self.state.bgm_id = ""
            else:
                self.state.bgm_id = cmd.get("bgmId", "")
            return None

        if t == "nameInput":
            return {"kind": "nameInput",
                    "prompt": cmd.get("prompt", "名前を入力"),
                    "varName": cmd.get("varName", "")}

        if t == "setVar":
            self._apply_setvar(cmd)
            return None

        if t == "gauge":
            self._apply_gauge(cmd)
            return None

        if t == "item":
            iid = cmd.get("itemId", "")
            if iid:
                if cmd.get("action") == "remove":
                    if iid in self.state.items:
                        self.state.items.remove(iid)
                else:
                    if iid not in self.state.items:
                        self.state.items.append(iid)
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

        if t == "ending":
            end = self.project.ending(cmd.get("endingId", ""))
            if end and end["id"] not in self.state.discovered_endings:
                self.state.discovered_endings.append(end["id"])
            return {
                "kind": "ending",
                "name": end["name"] if end else "エンディング",
                "desc": end.get("desc", "") if end else "",
                "hidden": end.get("hidden", False) if end else False,
            }

        # 未知のコマンドは無視
        return None

    # --- ヘルパー -----------------------------------------------------
    def _goto_scene(self, sid: str):
        self.state.scene_id = sid
        self.state.cmd_index = 0

    def _interp(self, text: str) -> str:
        """テキスト内の {変数名} を現在値で置換する。"""
        def repl(m):
            name = m.group(1)
            if name in self.state.variables:
                return str(self.state.variables[name])
            return m.group(0)
        return _VAR_PATTERN.sub(repl, text)

    def _apply_setvar(self, cmd: dict):
        name = cmd.get("varName", "")
        if not name:
            return
        op = cmd.get("op", "set")
        raw = cmd.get("value", "")
        cur = self.state.variables.get(name)

        if op == "toggle":
            self.state.variables[name] = not bool(cur)
            return
        if op == "set":
            # 真偽値変数なら真偽に、数値なら数値に、それ以外は文字列に
            if isinstance(cur, bool):
                self.state.variables[name] = str(raw).strip().lower() in (
                    "true", "1", "はい", "yes", "on")
            elif isinstance(cur, (int, float)) and _looks_numeric(str(raw)):
                self.state.variables[name] = _to_number(raw)
            elif _looks_numeric(str(raw)) and (cur is None or _looks_numeric(str(cur))):
                self.state.variables[name] = _to_number(raw)
            else:
                self.state.variables[name] = str(raw)
            return
        # 算術系
        base = _to_number(cur)
        delta = _to_number(raw)
        if op == "add":
            base += delta
        elif op == "sub":
            base -= delta
        elif op == "mul":
            base *= delta
        # 整数なら整数で保持
        self.state.variables[name] = int(base) if base == int(base) else base

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
