"""データモデル — プロジェクト構造・コマンド定義・シリアライズ.

プロジェクトは JSON 互換のプレーンな dict / list で保持する。
これにより保存・読み込み・複製が容易になる。
:class:`Project` はその dict をラップして検索ヘルパーを提供する。
"""

from __future__ import annotations

import copy
import itertools
import json
import time
from typing import Any, Optional

# ---------------------------------------------------------------------------
# ユニークID生成
# ---------------------------------------------------------------------------
_counter = itertools.count(int(time.time() * 1000))


def uid(prefix: str = "id") -> str:
    """衝突しないユニークなIDを返す。"""
    return f"{prefix}_{next(_counter):x}"


# ---------------------------------------------------------------------------
# コマンド（コンポーネント）の種類
# ---------------------------------------------------------------------------
# (type, 表示名, アイコン)  ※エディタの「追加」メニューと表示に使う
COMMAND_TYPES = [
    ("say",       "セリフ",       "💬"),
    ("narrate",   "地の文",       "📝"),
    ("charExit",  "キャラ退場",   "🚪"),
    ("bg",        "背景変更",     "🖼"),
    ("cg",        "CG表示",       "🌅"),
    ("blackout",  "暗転",         "🌑"),
    ("compVis",   "コンポーネント表示・消去", "👁"),
    ("bgm",       "BGM",          "🎵"),
    ("se",        "効果音(SE)",   "🔊"),
    ("nameInput", "名前入力",     "🔤"),
    ("setVar",    "変数操作",     "🔢"),
    ("gauge",     "ゲージ操作",   "📊"),
    ("item",      "アイテム",     "🎒"),
    ("choice",    "選択肢分岐",   "🔀"),
    ("if",        "条件分岐",     "❓"),
    ("jump",      "シーン移動",   "➡"),
    ("endroll",   "エンドロール", "🎞"),
    ("ending",    "エンディング", "🏁"),
]

COMMAND_LABELS = {t: label for t, label, _ in COMMAND_TYPES}
COMMAND_ICONS = {t: icon for t, _, icon in COMMAND_TYPES}

# セリフの「立ち絵表示なし」を表す表情ID（差分セレクトの既定候補）
NO_SPRITE = "__none__"

# 立ち絵の配置位置（1画面に最大3人）
SAY_POSITIONS = [("left", "左"), ("center", "中央"), ("right", "右")]
SPRITE_SLOTS = ["left", "center", "right"]

# 表示/消去できるコンポーネント（compVis コマンド・レイアウトの非表示で共通）
COMP_TARGETS = [
    ("message", "セリフ枠"),
    ("sprite", "立ち絵"),
    ("gauges", "ゲージ"),
    ("items", "アイテムボタン"),
    ("menu", "メニュー"),
]

# 変数操作の演算子
VAR_OPS = [("set", "代入 ="), ("add", "加算 +="), ("sub", "減算 -="),
           ("mul", "乗算 *="), ("toggle", "反転(真偽)")]
# ゲージ操作の演算子
GAUGE_OPS = [("set", "代入 ="), ("add", "加算 +="), ("sub", "減算 -=")]


# ---------------------------------------------------------------------------
# レイアウト（コンポーネント表示位置）とテーマ（コンポーネント画像）
# ---------------------------------------------------------------------------
# 位置は画面サイズに対する百分率。x,y は要素の左上（spriteのみ中央下）。
DEFAULT_LAYOUT = {
    "message": {"x": 4.0, "y": 72.0, "w": 92.0, "h": 26.0},
    "choices": {"x": 50.0, "y": 42.0},   # 中央アンカー
    # 立ち絵は左/中/右の3スロットを個別に配置（中央下アンカー）
    "spriteLeft":   {"x": 25.0, "y": 99.0, "scale": 80.0},
    "spriteCenter": {"x": 50.0, "y": 99.0, "scale": 80.0},
    "spriteRight":  {"x": 75.0, "y": 99.0, "scale": 80.0},
    "sprite":  {},                       # 立ち絵の非表示フラグ用
    "gauges":  {"x": 1.2, "y": 2.0},     # 左上
    "items":   {"x": 94.0, "y": 2.0},    # 左上座標（右上付近）
    "menu":    {"x": 63.0, "y": 9.0},
    "title":   {"x": 50.0, "y": 38.0},   # タイトルのボタン群中央
}

# 立ち絵スロット → レイアウトキー
SPRITE_POS_KEY = {"left": "spriteLeft", "center": "spriteCenter", "right": "spriteRight"}

# レイアウト編集対象（id, ラベル, 種別）
LAYOUT_ELEMENTS = [
    ("message", "セリフ枠", "box"),
    ("spriteLeft",   "立ち絵(左)", "sprite"),
    ("spriteCenter", "立ち絵(中)", "sprite"),
    ("spriteRight",  "立ち絵(右)", "sprite"),
    ("choices", "選択肢",   "point"),
    ("gauges",  "ゲージ",   "point"),
    ("items",   "アイテム", "point"),
    ("menu",    "メニュー", "point"),
]

# テーマ（コンポーネントの取り込み画像）
DEFAULT_THEME = {
    "msgWindowImage": "",     # セリフ枠の背景画像
    "choiceButtonImage": "",  # 選択肢ボタンの背景画像
    "titleButtonImage": "",   # タイトルボタンの背景画像
    "itemsButtonImage": "",   # アイテムボタンの画像
    "nameBoxImage": "",       # 名前入力の枠（コンポーネント枠）背景
    "nameFieldImage": "",     # 名前入力の入力欄背景
}

THEME_FIELDS = [
    ("msgWindowImage", "セリフ枠の背景"),
    ("choiceButtonImage", "選択肢ボタンの背景"),
    ("titleButtonImage", "タイトルボタンの背景"),
    ("itemsButtonImage", "アイテムボタンの画像"),
    ("nameBoxImage", "名前入力の枠"),
    ("nameFieldImage", "名前入力の入力欄"),
]


def merged_layout(project: "Project") -> dict:
    """プロジェクトのレイアウトを既定値とマージして返す（旧データ互換）。"""
    out = {k: dict(v) for k, v in DEFAULT_LAYOUT.items()}
    for key, val in (project.data.get("layout") or {}).items():
        if key in out and isinstance(val, dict):
            out[key].update(val)
        else:
            out[key] = val
    return out


def merged_theme(project: "Project") -> dict:
    out = dict(DEFAULT_THEME)
    out.update(project.data.get("theme") or {})
    return out


def empty_condition() -> dict:
    """空の条件式を返す。terms が空なら常に真として扱う。"""
    return {"logic": "and", "terms": []}


def new_term(kind: str = "var") -> dict:
    """新しい条件の項を返す。"""
    if kind == "item":
        return {"kind": "item", "ref": "", "op": "has", "value": ""}
    if kind == "ending":
        return {"kind": "ending", "ref": "", "op": ">=", "value": "1"}
    return {"kind": kind, "ref": "", "op": "==", "value": "0"}


def new_command(ctype: str) -> dict:
    """指定タイプのコマンド初期値を返す。"""
    base = {"id": uid("cmd"), "type": ctype}
    if ctype == "say":
        # 既定はキャラの最初の表情で立ち絵表示。hideSprite で個別に非表示も可。
        base.update(charId="", exprId="", text="", hideSprite=False, pos="center")
    elif ctype == "narrate":
        base.update(text="")
    elif ctype == "charExit":
        base.update(charId="")  # 空=全員退場
    elif ctype == "bg":
        base.update(bgId="")
    elif ctype == "blackout":
        base.update(mode="on", hideUi=False)  # on=暗転 / off=解除, hideUi=UIも消す
    elif ctype == "compVis":
        base.update(target="message", action="hide")  # show / hide
    elif ctype == "bgm":
        base.update(action="play", bgmId="", loop=True, fadeMs=0)
    elif ctype == "endroll":
        base.update(text="", speed=60, noSkip=False)  # noSkip=スキップ不可
    elif ctype == "se":
        base.update(seId="")
    elif ctype == "cg":
        base.update(cgId="", action="show")  # show / hide
    elif ctype == "nameInput":
        base.update(varName="", prompt="名前を入力してください")
    elif ctype == "setVar":
        base.update(varName="", op="set", value="0")
    elif ctype == "gauge":
        base.update(gaugeId="", op="add", value="1")
    elif ctype == "item":
        base.update(itemId="", action="add", notify=True)  # add / remove / use
    elif ctype == "choice":
        base.update(prompt="", options=[
            {"id": uid("opt"), "text": "選択肢1", "targetScene": "",
             "condition": empty_condition()},
            {"id": uid("opt"), "text": "選択肢2", "targetScene": "",
             "condition": empty_condition()},
        ])
    elif ctype == "if":
        base.update(condition=empty_condition(), targetTrue="", targetFalse="")
    elif ctype == "jump":
        base.update(targetScene="")
    elif ctype == "ending":
        base.update(endingId="")
    return base


def migrate_project(data: dict) -> dict:
    """旧バージョンのデータを現行仕様に補正する。

    - セリフの「立ち絵表示なし」を表情ID(``__none__``)に埋め込んでいた旧仕様を、
      表情=空（最初の表情で表示）＋ ``hideSprite`` 方式へ移行する。
      これにより「立ち絵を表示する」にしたのに出ない不具合を解消する。
    """
    for scene in data.get("scenes", []):
        for cmd in scene.get("commands", []):
            if cmd.get("type") == "say":
                if cmd.get("exprId") == NO_SPRITE:
                    cmd["exprId"] = ""          # 立ち絵を表示する側に倒す
                cmd.setdefault("hideSprite", False)
    # 旧：単一 "sprite" レイアウト → 左/中/右の3スロットへ
    lay = data.get("layout")
    if isinstance(lay, dict):
        s = lay.get("sprite")
        if isinstance(s, dict) and ("x" in s or "scale" in s) and "spriteCenter" not in lay:
            cx = float(s.get("x", 50)); y = float(s.get("y", 99)); sc = float(s.get("scale", 80))
            lay.setdefault("spriteCenter", {"x": cx, "y": y, "scale": sc})
            lay.setdefault("spriteLeft", {"x": max(8.0, cx - 25), "y": y, "scale": sc})
            lay.setdefault("spriteRight", {"x": min(92.0, cx + 25), "y": y, "scale": sc})
            # "sprite" は非表示フラグだけ残す
            lay["sprite"] = {k: v for k, v in s.items() if k == "hidden"}
    return data


# ---------------------------------------------------------------------------
# Project ラッパー
# ---------------------------------------------------------------------------
class Project:
    """プロジェクトデータ(dict)のラッパー。検索/操作ヘルパーを提供。"""

    def __init__(self, data: Optional[dict] = None):
        self.data: dict = data if data is not None else default_project()
        migrate_project(self.data)       # 旧データの補正
        self.path: Optional[str] = None  # 保存先ファイルパス
        self.dirty: bool = False         # 未保存の変更があるか

    # --- メタ ---------------------------------------------------------
    @property
    def meta(self) -> dict:
        return self.data["meta"]

    @property
    def title(self) -> str:
        return self.meta.get("title", "無題")

    # --- 各リストへのアクセス ----------------------------------------
    @property
    def variables(self) -> list:
        return self.data["variables"]

    @property
    def system_vars(self) -> list:
        return self.data.setdefault("systemVars", [])

    @property
    def gauges(self) -> list:
        return self.data["gauges"]

    @property
    def characters(self) -> list:
        return self.data["characters"]

    @property
    def items(self) -> list:
        return self.data["items"]

    @property
    def backgrounds(self) -> list:
        return self.data["backgrounds"]

    @property
    def bgm(self) -> list:
        return self.data["bgm"]

    @property
    def se(self) -> list:
        return self.data.setdefault("se", [])

    @property
    def cg(self) -> list:
        return self.data.setdefault("cg", [])

    @property
    def endings(self) -> list:
        return self.data["endings"]

    @property
    def scenes(self) -> list:
        return self.data["scenes"]

    # --- ID 検索 ------------------------------------------------------
    @staticmethod
    def _find(lst: list, _id: str) -> Optional[dict]:
        for e in lst:
            if e.get("id") == _id:
                return e
        return None

    def character(self, cid: str) -> Optional[dict]:
        return self._find(self.characters, cid)

    def expression(self, cid: str, eid: str) -> Optional[dict]:
        ch = self.character(cid)
        if not ch:
            return None
        return self._find(ch.get("expressions", []), eid)

    def item(self, iid: str) -> Optional[dict]:
        return self._find(self.items, iid)

    def background(self, bid: str) -> Optional[dict]:
        return self._find(self.backgrounds, bid)

    def gauge(self, gid: str) -> Optional[dict]:
        return self._find(self.gauges, gid)

    def bgm_track(self, bid: str) -> Optional[dict]:
        return self._find(self.bgm, bid)

    def se_track(self, sid: str) -> Optional[dict]:
        return self._find(self.se, sid)

    def cg_item(self, cid: str) -> Optional[dict]:
        return self._find(self.cg, cid)

    def ending(self, eid: str) -> Optional[dict]:
        return self._find(self.endings, eid)

    def scene(self, sid: str) -> Optional[dict]:
        return self._find(self.scenes, sid)

    def variable(self, name: str) -> Optional[dict]:
        for v in self.variables:
            if v.get("name") == name:
                return v
        return None

    # --- 名前ヘルパー（UI 表示用） ------------------------------------
    def scene_name(self, sid: str) -> str:
        s = self.scene(sid)
        return s["name"] if s else "（未設定）"

    def character_name(self, cid: str) -> str:
        c = self.character(cid)
        return c["name"] if c else ""

    # --- シリアライズ -------------------------------------------------
    def to_json(self) -> str:
        return json.dumps(self.data, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "Project":
        return cls(json.loads(text))

    def clone_data(self) -> dict:
        return copy.deepcopy(self.data)


# ---------------------------------------------------------------------------
# デフォルト（サンプル）プロジェクト
# ---------------------------------------------------------------------------
def default_project() -> dict:
    hero = uid("char")
    player = uid("char")
    friend = uid("char")
    f_normal = uid("expr")
    p_normal = uid("expr")
    e_normal, e_smile, e_sad = uid("expr"), uid("expr"), uid("expr")
    bg_room, bg_night = uid("bg"), uid("bg")
    bgm_main = uid("bgm")
    g_aff = uid("gauge")
    it_key = uid("item")
    se_select = uid("se")
    cg_event = uid("cg")
    end_true, end_normal, end_secret = uid("end"), uid("end"), uid("end")
    s_start, s_a, s_b, s_end = uid("scene"), uid("scene"), uid("scene"), uid("scene")
    s_true, s_normal, s_secret = uid("scene"), uid("scene"), uid("scene")

    return {
        "meta": {
            "title": "はじめてのノベルゲーム",
            "author": "",
            "startScene": s_start,
            "titleBg": bg_room,     # タイトル画面の背景
            "titleBgm": bgm_main,   # タイトル画面のBGM
            "font": "",             # ゲーム内フォント（フォント名）
            "fontPath": "",         # 取り込みフォントファイル（任意）
        },
        "variables": [
            {"id": uid("var"), "name": "playerName", "type": "string", "initial": "主人公"},
            {"id": uid("var"), "name": "flag_secret", "type": "boolean", "initial": False},
        ],
        "systemVars": [
            # ゲーム全体で共有・永続するシステム変数（プレイをまたいで保持）
            {"id": uid("svar"), "name": "clearCount", "type": "number", "initial": 0},
        ],
        "gauges": [
            {"id": g_aff, "name": "好感度", "min": 0, "max": 100,
             "initial": 50, "color": "#ff6b9d", "show": True},
        ],
        "characters": [
            {"id": hero, "name": "ヒロイン", "color": "#ffb6c1",
             "isProtagonist": False, "showSprite": True, "expressions": [
                {"id": e_normal, "name": "通常", "image": ""},
                {"id": e_smile, "name": "笑顔", "image": ""},
                {"id": e_sad, "name": "悲しい", "image": ""},
            ]},
            {"id": player, "name": "主人公", "color": "#9fd3ff",
             "isProtagonist": True, "showSprite": False, "expressions": [
                {"id": p_normal, "name": "通常", "image": ""},
            ]},
            {"id": friend, "name": "友人", "color": "#a0e6a0",
             "isProtagonist": False, "showSprite": True, "expressions": [
                {"id": f_normal, "name": "通常", "image": ""},
            ]},
        ],
        "items": [
            {"id": it_key, "name": "古い鍵",
             "desc": "何かを開けられそうだ。\nどこかの扉を開けるのに使えるかもしれない。",
             "icon": "🔑", "image": "", "consumable": False},
        ],
        "backgrounds": [
            {"id": bg_room, "name": "部屋", "image": "", "color": "#3a4a6b"},
            {"id": bg_night, "name": "夜の街", "image": "", "color": "#1a1a3a"},
        ],
        "bgm": [
            {"id": bgm_main, "name": "メインテーマ", "path": "", "loop": True},
        ],
        "se": [
            {"id": se_select, "name": "決定音", "path": ""},
        ],
        "cg": [
            {"id": cg_event, "name": "回想シーン", "image": "", "color": "#2a1a3a"},
        ],
        "endings": [
            {"id": end_true, "name": "トゥルーエンド", "hidden": False,
             "desc": "二人は末永く幸せに暮らした。"},
            {"id": end_normal, "name": "ノーマルエンド", "hidden": False,
             "desc": "物語は静かに幕を閉じた。"},
            {"id": end_secret, "name": "裏エンド：真実", "hidden": True,
             "desc": "隠されていた真実が、いま明らかになる――。"},
        ],
        "scenes": [
            {"id": s_start, "name": "オープニング", "commands": [
                {"id": uid("cmd"), "type": "bg", "bgId": bg_room},
                {"id": uid("cmd"), "type": "bgm", "action": "play",
                 "bgmId": bgm_main, "loop": True, "fadeMs": 1500},
                {"id": uid("cmd"), "type": "narrate", "text": "ある晴れた日のことだった。"},
                {"id": uid("cmd"), "type": "nameInput", "varName": "playerName",
                 "prompt": "あなたの名前は？"},
                {"id": uid("cmd"), "type": "say", "charId": player, "exprId": p_normal,
                 "text": "（さて、どこへ行こうか……）"},
                {"id": uid("cmd"), "type": "say", "charId": hero, "exprId": e_smile,
                 "text": "はじめまして、{playerName}さん！"},
                {"id": uid("cmd"), "type": "choice", "prompt": "どう答える？", "options": [
                    {"id": uid("opt"), "text": "笑顔で挨拶する",
                     "targetScene": s_a, "condition": empty_condition()},
                    {"id": uid("opt"), "text": "そっけなく返す",
                     "targetScene": s_b, "condition": empty_condition()},
                ]},
            ]},
            {"id": s_a, "name": "好感ルート", "commands": [
                {"id": uid("cmd"), "type": "say", "charId": hero, "exprId": e_smile,
                 "pos": "left", "text": "えへへ、嬉しいな。"},
                # 立ち絵を1画面に複数（左：ヒロイン／右：友人）
                {"id": uid("cmd"), "type": "say", "charId": friend, "exprId": f_normal,
                 "pos": "right", "text": "おっ、二人とも仲良いね！"},
                {"id": uid("cmd"), "type": "say", "charId": hero, "exprId": e_smile,
                 "pos": "left", "text": "もう、からかわないでよ。"},
                {"id": uid("cmd"), "type": "charExit", "charId": friend},
                {"id": uid("cmd"), "type": "gauge", "gaugeId": g_aff, "op": "add", "value": "20"},
                {"id": uid("cmd"), "type": "item", "itemId": it_key, "action": "add"},
                {"id": uid("cmd"), "type": "jump", "targetScene": s_end},
            ]},
            {"id": s_b, "name": "冷淡ルート", "commands": [
                {"id": uid("cmd"), "type": "say", "charId": hero, "exprId": e_sad,
                 "text": "……そっか。"},
                {"id": uid("cmd"), "type": "gauge", "gaugeId": g_aff, "op": "sub", "value": "20"},
                {"id": uid("cmd"), "type": "jump", "targetScene": s_end},
            ]},
            {"id": s_end, "name": "エンディング分岐", "commands": [
                {"id": uid("cmd"), "type": "blackout", "mode": "on"},
                {"id": uid("cmd"), "type": "bg", "bgId": bg_night},
                {"id": uid("cmd"), "type": "blackout", "mode": "off"},
                {"id": uid("cmd"), "type": "narrate", "text": "こうして物語は終わりを迎える。"},
                # 好感度70以上 かつ 鍵所持 → 裏エンドへジャンプ
                {"id": uid("cmd"), "type": "if", "condition": {
                    "logic": "and", "terms": [
                        {"kind": "gauge", "ref": g_aff, "op": ">=", "value": "70"},
                        {"kind": "item", "ref": it_key, "op": "has", "value": ""},
                    ]},
                 "targetTrue": s_secret, "targetFalse": ""},
                # 好感度60以上 → トゥルー / それ未満 → ノーマル
                {"id": uid("cmd"), "type": "if", "condition": {
                    "logic": "and", "terms": [
                        {"kind": "gauge", "ref": g_aff, "op": ">=", "value": "60"},
                    ]},
                 "targetTrue": s_true, "targetFalse": s_normal},
            ]},
            {"id": s_true, "name": "[END] トゥルー", "commands": [
                {"id": uid("cmd"), "type": "setVar", "varName": "clearCount",
                 "op": "add", "value": "1"},  # システム変数（永続）
                {"id": uid("cmd"), "type": "bgm", "action": "stop", "fadeMs": 2000},
                {"id": uid("cmd"), "type": "endroll",
                 "text": "― 完 ―\n\n\n企画・シナリオ\n{playerName}\n\n\n"
                         "イラスト\nあなた\n\n\n音楽\nあなた\n\n\n"
                         "Special Thanks\nプレイしてくれたあなた\n\n\n\n"
                         "ノベルメーカーで制作", "speed": 70},
                {"id": uid("cmd"), "type": "ending", "endingId": end_true},
            ]},
            {"id": s_normal, "name": "[END] ノーマル", "commands": [
                {"id": uid("cmd"), "type": "setVar", "varName": "clearCount",
                 "op": "add", "value": "1"},
                {"id": uid("cmd"), "type": "ending", "endingId": end_normal},
            ]},
            {"id": s_secret, "name": "[END] 裏エンド", "commands": [
                {"id": uid("cmd"), "type": "se", "seId": se_select},
                {"id": uid("cmd"), "type": "cg", "cgId": cg_event, "action": "show"},
                {"id": uid("cmd"), "type": "say", "charId": hero, "exprId": e_normal,
                 "text": "……実はね、ずっと言えなかったことがあるの。"},
                {"id": uid("cmd"), "type": "cg", "cgId": cg_event, "action": "hide"},
                {"id": uid("cmd"), "type": "setVar", "varName": "flag_secret",
                 "op": "set", "value": "true"},
                {"id": uid("cmd"), "type": "setVar", "varName": "clearCount",
                 "op": "add", "value": "1"},
                {"id": uid("cmd"), "type": "ending", "endingId": end_secret},
            ]},
        ],
        "layout": {k: dict(v) for k, v in DEFAULT_LAYOUT.items()},
        "theme": dict(DEFAULT_THEME),
    }


def _short(text: str, n: int = 40) -> str:
    text = (text or "").replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "…"


def describe_command(cmd: dict, project: "Project") -> str:
    """コマンドを一覧表示用の1行テキストに要約する。"""
    t = cmd.get("type")
    if t == "say":
        ch = project.character(cmd.get("charId", ""))
        name = ch["name"] if ch else "（地の文）"
        pos = {"left": "[左]", "right": "[右]"}.get(cmd.get("pos", "center"), "")
        return f"{pos}{name}「{_short(cmd.get('text',''))}」"
    if t == "narrate":
        return f"{_short(cmd.get('text',''))}"
    if t == "charExit":
        ch = project.character(cmd.get("charId", ""))
        return f"キャラ退場 → {ch['name'] if ch else '（全員）'}"
    if t == "bg":
        bg = project.background(cmd.get("bgId", ""))
        return f"背景 → {bg['name'] if bg else '（未設定）'}"
    if t == "blackout":
        if cmd.get("mode") == "on":
            return "暗転する（UIも消す）" if cmd.get("hideUi") else "暗転する"
        return "暗転を解除"
    if t == "compVis":
        tname = dict(COMP_TARGETS).get(cmd.get("target", ""), "（未設定）")
        act = "表示" if cmd.get("action") == "show" else "消去"
        return f"{tname} を {act}"
    if t == "bgm":
        fade = cmd.get("fadeMs", 0)
        fade_s = f"（フェード{fade}ms）" if fade else ""
        if cmd.get("action") == "stop":
            return f"BGM停止{fade_s}"
        bgm = project.bgm_track(cmd.get("bgmId", ""))
        loop = "（ループ）" if cmd.get("loop", True) else ""
        return f"BGM再生 → {bgm['name'] if bgm else '（未設定）'}{loop}{fade_s}"
    if t == "endroll":
        skip = "・スキップ不可" if cmd.get("noSkip") else ""
        return f"エンドロール（{_short(cmd.get('text',''), 20)}{skip}）"
    if t == "se":
        se = project.se_track(cmd.get("seId", ""))
        return f"効果音 → {se['name'] if se else '（未設定）'}"
    if t == "cg":
        cg = project.cg_item(cmd.get("cgId", ""))
        if cmd.get("action") == "hide":
            return "CGを消す"
        return f"CG表示 → {cg['name'] if cg else '（未設定）'}"
    if t == "nameInput":
        return f"名前入力 → 変数「{cmd.get('varName','?')}」"
    if t == "setVar":
        op_map = dict(VAR_OPS)
        return f"変数 {cmd.get('varName','?')} {op_map.get(cmd.get('op'),'')} {cmd.get('value','')}"
    if t == "gauge":
        g = project.gauge(cmd.get("gaugeId", ""))
        op_map = dict(GAUGE_OPS)
        return f"ゲージ「{g['name'] if g else '?'}」 {op_map.get(cmd.get('op'),'')} {cmd.get('value','')}"
    if t == "item":
        it = project.item(cmd.get("itemId", ""))
        act = {"add": "入手", "remove": "破棄", "use": "使用"}.get(cmd.get("action"), "?")
        return f"アイテム {act} → {it['name'] if it else '（未設定）'}"
    if t == "choice":
        opts = cmd.get("options", [])
        return f"選択肢分岐（{len(opts)}択）" + (f"：{_short(cmd.get('prompt',''),20)}" if cmd.get("prompt") else "")
    if t == "if":
        n = len(cmd.get("condition", {}).get("terms", []))
        return f"条件分岐（{n}件の条件）"
    if t == "jump":
        return f"シーン移動 → {project.scene_name(cmd.get('targetScene',''))}"
    if t == "ending":
        e = project.ending(cmd.get("endingId", ""))
        lock = "🔒" if (e and e.get("hidden")) else ""
        return f"エンディング → {lock}{e['name'] if e else '（未設定）'}"
    return t or "?"


def make_save_meta(project: Project) -> dict:
    """新規保存用の最小メタ情報。"""
    return {"savedAt": time.strftime("%Y-%m-%d %H:%M:%S")}
