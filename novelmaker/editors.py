"""リソース編集タブ群.

キャラ・表情 / アイテム / 変数 / ゲージ / 背景 / BGM / エンディング。
共通の :class:`ListEditor` を継承し、左に一覧・右に詳細フォームを表示。
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QListWidget,
    QListWidgetItem, QPushButton, QLabel, QLineEdit, QComboBox, QCheckBox,
    QSpinBox, QPlainTextEdit, QColorDialog, QFileDialog, QFrame, QGroupBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from .model import Project, uid


# ===========================================================================
# 共通ベース
# ===========================================================================
class ListEditor(QWidget):
    """左：一覧／右：詳細フォーム の汎用エディタ。"""

    changed = Signal()
    title = "項目"

    def __init__(self, project: Project):
        super().__init__()
        self.project = project
        self.current = None

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        left = QVBoxLayout()
        left.addWidget(QLabel(f"<b>{self.title}一覧</b>"))
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._on_select)
        left.addWidget(self.list, 1)
        brow = QHBoxLayout()
        for text, slot in [("＋追加", self._add), ("複製", self._dup),
                           ("▲", self._up), ("▼", self._down), ("削除", self._del)]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            brow.addWidget(b)
        left.addLayout(brow)
        lw = QWidget()
        lw.setLayout(left)
        lw.setMaximumWidth(280)
        root.addWidget(lw)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        root.addWidget(sep)

        self.form_host = QVBoxLayout()
        fw = QWidget()
        fw.setLayout(self.form_host)
        root.addWidget(fw, 1)

        self.reload()

    # --- サブクラスが実装 ---------------------------------------------
    def entries(self) -> list:
        raise NotImplementedError

    def default_entry(self) -> dict:
        raise NotImplementedError

    def label_for(self, entry: dict) -> str:
        raise NotImplementedError

    def build_form(self, entry: dict):
        raise NotImplementedError

    # --- 共通処理 -----------------------------------------------------
    def reload(self):
        self.list.blockSignals(True)
        self.list.clear()
        for e in self.entries():
            self.list.addItem(self.label_for(e))
        self.list.blockSignals(False)
        if self.entries():
            self.list.setCurrentRow(0)
        else:
            self.current = None
            self._clear_form()

    def _on_select(self, row: int):
        entries = self.entries()
        if 0 <= row < len(entries):
            self.current = entries[row]
            self._rebuild_form()
        else:
            self.current = None
            self._clear_form()

    def _clear_form(self):
        while self.form_host.count():
            item = self.form_host.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)

    def _rebuild_form(self):
        self._clear_form()
        if self.current is not None:
            self.build_form(self.current)
            self.form_host.addStretch()

    def touch(self):
        """現在項目のラベル更新＋変更通知。"""
        row = self.list.currentRow()
        if self.current is not None and 0 <= row < self.list.count():
            self.list.item(row).setText(self.label_for(self.current))
        self.project.dirty = True
        self.changed.emit()

    def _add(self):
        entry = self.default_entry()
        self.entries().append(entry)
        self.list.addItem(self.label_for(entry))
        self.list.setCurrentRow(self.list.count() - 1)
        self.touch()

    def _dup(self):
        if self.current is None:
            return
        import copy
        clone = copy.deepcopy(self.current)
        clone["id"] = uid(clone["id"].split("_")[0] if "_" in clone.get("id", "") else "id")
        if "name" in clone:
            clone["name"] = clone["name"] + " のコピー"
        self.entries().append(clone)
        self.reload()
        self.list.setCurrentRow(self.list.count() - 1)
        self.touch()

    def _del(self):
        row = self.list.currentRow()
        if self.current is None or row < 0:
            return
        self.entries().remove(self.current)
        self.reload()
        self.list.setCurrentRow(min(row, self.list.count() - 1))
        self.touch()

    def _up(self):
        row = self.list.currentRow()
        if row <= 0:
            return
        e = self.entries()
        e[row - 1], e[row] = e[row], e[row - 1]
        self.reload()
        self.list.setCurrentRow(row - 1)
        self.touch()

    def _down(self):
        row = self.list.currentRow()
        e = self.entries()
        if row < 0 or row >= len(e) - 1:
            return
        e[row + 1], e[row] = e[row], e[row + 1]
        self.reload()
        self.list.setCurrentRow(row + 1)
        self.touch()


# --- 小物ウィジェット -------------------------------------------------------
class ColorButton(QPushButton):
    """色選択ボタン。"""

    def __init__(self, color: str, on_change):
        super().__init__()
        self.color = color or "#888888"
        self._on_change = on_change
        self.setFixedWidth(80)
        self._refresh()
        self.clicked.connect(self._pick)

    def _refresh(self):
        self.setText(self.color)
        self.setStyleSheet(
            f"background:{self.color}; color:{_contrast(self.color)};")

    def _pick(self):
        c = QColorDialog.getColor(QColor(self.color), self, "色を選択")
        if c.isValid():
            self.color = c.name()
            self._refresh()
            self._on_change(self.color)


class FilePicker(QWidget):
    """ファイルパス入力＋参照ボタン。"""

    def __init__(self, path: str, on_change, filter_str="すべて (*.*)"):
        super().__init__()
        self._on_change = on_change
        self.filter_str = filter_str
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit(path or "")
        self.edit.textChanged.connect(self._on_change)
        btn = QPushButton("参照…")
        btn.clicked.connect(self._browse)
        clr = QPushButton("クリア")
        clr.setFixedWidth(56)
        clr.clicked.connect(lambda: self.edit.setText(""))
        lay.addWidget(self.edit, 1)
        lay.addWidget(btn)
        lay.addWidget(clr)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "ファイルを選択", "", self.filter_str)
        if path:
            self.edit.setText(path)


def _contrast(hexcolor: str) -> str:
    try:
        c = QColor(hexcolor)
        lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
        return "#000000" if lum > 150 else "#ffffff"
    except Exception:
        return "#ffffff"


# ===========================================================================
# 変数エディタ
# ===========================================================================
class VariableEditor(ListEditor):
    title = "変数"

    def entries(self):
        return self.project.variables

    def default_entry(self):
        return {"id": uid("var"), "name": f"var{len(self.entries())+1}",
                "type": "number", "initial": 0}

    def label_for(self, e):
        return f'{e["name"]}  [{e["type"]}] = {e.get("initial")}'

    def build_form(self, e):
        f = QFormLayout()
        name = QLineEdit(e["name"])
        name.textChanged.connect(lambda t: (e.__setitem__("name", t), self.touch()))
        type_cb = QComboBox()
        for val, lbl in [("number", "数値"), ("string", "文字列"), ("boolean", "真偽")]:
            type_cb.addItem(lbl, val)
        for i in range(type_cb.count()):
            if type_cb.itemData(i) == e["type"]:
                type_cb.setCurrentIndex(i)
        init = QLineEdit(str(e.get("initial", "")))

        def set_type(_):
            e["type"] = type_cb.currentData()
            self.touch()
        type_cb.currentIndexChanged.connect(set_type)

        def set_init(t):
            if e["type"] == "number":
                try:
                    e["initial"] = float(t) if "." in t else int(t)
                except ValueError:
                    e["initial"] = 0
            elif e["type"] == "boolean":
                e["initial"] = t.strip().lower() in ("true", "1", "はい", "yes", "on")
            else:
                e["initial"] = t
            self.touch()
        init.textChanged.connect(set_init)

        f.addRow("変数名:", name)
        f.addRow("型:", type_cb)
        f.addRow("初期値:", init)
        hint = QLabel("真偽型の初期値は true / false で入力。")
        hint.setStyleSheet("color:#888;")
        f.addRow("", hint)
        host = QWidget(); host.setLayout(f)
        self.form_host.addWidget(host)


# ===========================================================================
# ゲージエディタ
# ===========================================================================
class GaugeEditor(ListEditor):
    title = "ゲージ"

    def entries(self):
        return self.project.gauges

    def default_entry(self):
        return {"id": uid("gauge"), "name": f"ゲージ{len(self.entries())+1}",
                "min": 0, "max": 100, "initial": 0, "color": "#4cc2ff", "show": True}

    def label_for(self, e):
        return f'{e["name"]}  ({e.get("min")}〜{e.get("max")})'

    def build_form(self, e):
        f = QFormLayout()
        name = QLineEdit(e["name"])
        name.textChanged.connect(lambda t: (e.__setitem__("name", t), self.touch()))
        f.addRow("名前:", name)

        for key, label in [("min", "最小値"), ("max", "最大値"), ("initial", "初期値")]:
            sp = QSpinBox()
            sp.setRange(-1000000, 1000000)
            sp.setValue(int(e.get(key, 0)))
            sp.valueChanged.connect(lambda v, k=key: (e.__setitem__(k, v), self.touch()))
            f.addRow(label + ":", sp)

        color = ColorButton(e.get("color", "#4cc2ff"),
                            lambda c: (e.__setitem__("color", c), self.touch()))
        f.addRow("色:", color)

        show = QCheckBox("ゲーム画面に表示する")
        show.setChecked(bool(e.get("show", True)))
        show.toggled.connect(lambda v: (e.__setitem__("show", v), self.touch()))
        f.addRow("", show)

        host = QWidget(); host.setLayout(f)
        self.form_host.addWidget(host)


# ===========================================================================
# アイテムエディタ
# ===========================================================================
class ItemEditor(ListEditor):
    title = "アイテム"

    def entries(self):
        return self.project.items

    def default_entry(self):
        return {"id": uid("item"), "name": f"アイテム{len(self.entries())+1}",
                "desc": "", "icon": "📦"}

    def label_for(self, e):
        return f'{e.get("icon","")} {e["name"]}'

    def build_form(self, e):
        f = QFormLayout()
        name = QLineEdit(e["name"])
        name.textChanged.connect(lambda t: (e.__setitem__("name", t), self.touch()))
        icon = QLineEdit(e.get("icon", ""))
        icon.setMaxLength(4)
        icon.textChanged.connect(lambda t: (e.__setitem__("icon", t), self.touch()))
        desc = QPlainTextEdit(e.get("desc", ""))
        desc.setMinimumHeight(80)
        desc.textChanged.connect(
            lambda: (e.__setitem__("desc", desc.toPlainText()), self.touch()))
        f.addRow("名前:", name)
        f.addRow("アイコン(絵文字):", icon)
        f.addRow("説明:", desc)
        host = QWidget(); host.setLayout(f)
        self.form_host.addWidget(host)


# ===========================================================================
# 背景エディタ
# ===========================================================================
class BackgroundEditor(ListEditor):
    title = "背景"

    def entries(self):
        return self.project.backgrounds

    def default_entry(self):
        return {"id": uid("bg"), "name": f"背景{len(self.entries())+1}",
                "image": "", "color": "#222244"}

    def label_for(self, e):
        return e["name"]

    def build_form(self, e):
        f = QFormLayout()
        name = QLineEdit(e["name"])
        name.textChanged.connect(lambda t: (e.__setitem__("name", t), self.touch()))
        img = FilePicker(e.get("image", ""),
                         lambda t: (e.__setitem__("image", t), self.touch()),
                         "画像 (*.png *.jpg *.jpeg *.bmp *.webp)")
        color = ColorButton(e.get("color", "#222244"),
                            lambda c: (e.__setitem__("color", c), self.touch()))
        f.addRow("名前:", name)
        f.addRow("画像:", img)
        f.addRow("背景色(画像が無い時):", color)
        host = QWidget(); host.setLayout(f)
        self.form_host.addWidget(host)


# ===========================================================================
# BGMエディタ
# ===========================================================================
class BgmEditor(ListEditor):
    title = "BGM"

    def entries(self):
        return self.project.bgm

    def default_entry(self):
        return {"id": uid("bgm"), "name": f"曲{len(self.entries())+1}",
                "path": "", "loop": True}

    def label_for(self, e):
        loop = " 🔁" if e.get("loop") else ""
        return f'{e["name"]}{loop}'

    def build_form(self, e):
        f = QFormLayout()
        name = QLineEdit(e["name"])
        name.textChanged.connect(lambda t: (e.__setitem__("name", t), self.touch()))
        path = FilePicker(e.get("path", ""),
                          lambda t: (e.__setitem__("path", t), self.touch()),
                          "音声 (*.mp3 *.wav *.ogg *.m4a *.flac)")
        loop = QCheckBox("ループ再生する")
        loop.setChecked(bool(e.get("loop", True)))
        loop.toggled.connect(lambda v: (e.__setitem__("loop", v), self.touch()))
        f.addRow("曲名:", name)
        f.addRow("音声ファイル:", path)
        f.addRow("", loop)
        host = QWidget(); host.setLayout(f)
        self.form_host.addWidget(host)


# ===========================================================================
# SE（効果音）エディタ
# ===========================================================================
class SeEditor(ListEditor):
    title = "SE"

    def entries(self):
        return self.project.se

    def default_entry(self):
        return {"id": uid("se"), "name": f"SE{len(self.entries())+1}", "path": ""}

    def label_for(self, e):
        return f'🔊 {e["name"]}'

    def build_form(self, e):
        f = QFormLayout()
        name = QLineEdit(e["name"])
        name.textChanged.connect(lambda t: (e.__setitem__("name", t), self.touch()))
        path = FilePicker(e.get("path", ""),
                          lambda t: (e.__setitem__("path", t), self.touch()),
                          "音声 (*.mp3 *.wav *.ogg *.m4a *.flac)")
        f.addRow("効果音名:", name)
        f.addRow("音声ファイル:", path)
        hint = QLabel("※ SE は一度だけ再生されます（BGMと別系統・ループしません）。")
        hint.setStyleSheet("color:#888;")
        f.addRow("", hint)
        host = QWidget(); host.setLayout(f)
        self.form_host.addWidget(host)


# ===========================================================================
# CG（イベント絵）エディタ
# ===========================================================================
class CgEditor(ListEditor):
    title = "CG"

    def entries(self):
        return self.project.cg

    def default_entry(self):
        return {"id": uid("cg"), "name": f"CG{len(self.entries())+1}",
                "image": "", "color": "#1a1a2a"}

    def label_for(self, e):
        return f'🌅 {e["name"]}'

    def build_form(self, e):
        f = QFormLayout()
        name = QLineEdit(e["name"])
        name.textChanged.connect(lambda t: (e.__setitem__("name", t), self.touch()))
        img = FilePicker(e.get("image", ""),
                         lambda t: (e.__setitem__("image", t), self.touch()),
                         "画像 (*.png *.jpg *.jpeg *.bmp *.webp)")
        color = ColorButton(e.get("color", "#1a1a2a"),
                            lambda c: (e.__setitem__("color", c), self.touch()))
        f.addRow("CG名:", name)
        f.addRow("画像:", img)
        f.addRow("背景色(画像が無い時):", color)
        hint = QLabel("※ CGは画面全体に表示されます（背景・立ち絵の上）。\n"
                      "　CGコマンドの「消す」で非表示にできます。")
        hint.setStyleSheet("color:#888;")
        f.addRow("", hint)
        host = QWidget(); host.setLayout(f)
        self.form_host.addWidget(host)


# ===========================================================================
# エンディングエディタ
# ===========================================================================
class EndingEditor(ListEditor):
    title = "エンディング"

    def entries(self):
        return self.project.endings

    def default_entry(self):
        return {"id": uid("end"), "name": f"エンディング{len(self.entries())+1}",
                "hidden": False, "desc": ""}

    def label_for(self, e):
        lock = "🔒 " if e.get("hidden") else ""
        return f'{lock}{e["name"]}'

    def build_form(self, e):
        f = QFormLayout()
        name = QLineEdit(e["name"])
        name.textChanged.connect(lambda t: (e.__setitem__("name", t), self.touch()))
        hidden = QCheckBox("裏エンディング（隠し要素）にする")
        hidden.setChecked(bool(e.get("hidden", False)))
        hidden.toggled.connect(lambda v: (e.__setitem__("hidden", v), self.touch()))
        desc = QPlainTextEdit(e.get("desc", ""))
        desc.setMinimumHeight(80)
        desc.textChanged.connect(
            lambda: (e.__setitem__("desc", desc.toPlainText()), self.touch()))
        f.addRow("名前:", name)
        f.addRow("", hidden)
        f.addRow("説明文:", desc)
        host = QWidget(); host.setLayout(f)
        self.form_host.addWidget(host)


# ===========================================================================
# キャラクター・表情差分エディタ
# ===========================================================================
class CharacterEditor(ListEditor):
    title = "キャラ"

    def entries(self):
        return self.project.characters

    def default_entry(self):
        return {"id": uid("char"), "name": f"キャラ{len(self.entries())+1}",
                "color": "#ffffff", "isProtagonist": False, "showSprite": True,
                "expressions": [{"id": uid("expr"), "name": "通常", "image": ""}]}

    def label_for(self, e):
        n = len(e.get("expressions", []))
        mark = "👤 " if e.get("isProtagonist") else ""
        return f'{mark}{e["name"]}  （表情{n}種）'

    def build_form(self, e):
        f = QFormLayout()
        name = QLineEdit(e["name"])
        name.textChanged.connect(lambda t: (e.__setitem__("name", t), self.touch()))
        color = ColorButton(e.get("color", "#ffffff"),
                            lambda c: (e.__setitem__("color", c), self.touch()))
        f.addRow("名前:", name)
        f.addRow("名前色:", color)

        protag = QCheckBox("主人公（プレイヤー操作キャラ）にする")
        protag.setChecked(bool(e.get("isProtagonist", False)))
        show = QCheckBox("立ち絵を表示する")
        show.setChecked(bool(e.get("showSprite", True)))

        def on_protag(v):
            e["isProtagonist"] = v
            if v:
                # 主人公は既定で立ち絵非表示
                e["showSprite"] = False
                show.setChecked(False)
            self.touch()
        protag.toggled.connect(on_protag)
        show.toggled.connect(lambda v: (e.__setitem__("showSprite", v), self.touch()))
        f.addRow("", protag)
        f.addRow("", show)
        hint = QLabel("※ 主人公は通常、立ち絵を表示しません（名前だけ表示）。\n"
                      "　立ち絵を出したい場合は「立ち絵を表示する」をオンに。")
        hint.setStyleSheet("color:#888;")
        f.addRow("", hint)
        host = QWidget(); host.setLayout(f)
        self.form_host.addWidget(host)

        # --- 表情差分のサブエディタ ---
        box = QGroupBox("表情差分")
        v = QVBoxLayout(box)
        self.expr_list = QListWidget()
        self.expr_list.setMaximumHeight(140)
        v.addWidget(self.expr_list)

        erow = QHBoxLayout()
        add = QPushButton("＋表情追加")
        add.clicked.connect(lambda: self._add_expr(e))
        rm = QPushButton("削除")
        rm.clicked.connect(lambda: self._del_expr(e))
        erow.addWidget(add)
        erow.addWidget(rm)
        erow.addStretch()
        v.addLayout(erow)

        self.expr_form_host = QVBoxLayout()
        efw = QWidget(); efw.setLayout(self.expr_form_host)
        v.addWidget(efw)

        self.form_host.addWidget(box)

        self.expr_list.currentRowChanged.connect(lambda r: self._on_expr_select(e, r))
        self._reload_expr_list(e)

    def _reload_expr_list(self, e):
        self.expr_list.blockSignals(True)
        self.expr_list.clear()
        for ex in e.get("expressions", []):
            mark = "🖼 " if ex.get("image") else "▫ "
            self.expr_list.addItem(f'{mark}{ex["name"]}')
        self.expr_list.blockSignals(False)
        if e.get("expressions"):
            self.expr_list.setCurrentRow(0)
        else:
            self._clear_expr_form()

    def _clear_expr_form(self):
        while self.expr_form_host.count():
            it = self.expr_form_host.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)

    def _on_expr_select(self, e, row):
        self._clear_expr_form()
        exprs = e.get("expressions", [])
        if not (0 <= row < len(exprs)):
            return
        ex = exprs[row]
        f = QFormLayout()
        name = QLineEdit(ex["name"])

        def set_name(t):
            ex["name"] = t
            self.expr_list.item(row).setText(("🖼 " if ex.get("image") else "▫ ") + t)
            self.touch()
        name.textChanged.connect(set_name)

        def set_img(t):
            ex["image"] = t
            self.expr_list.item(row).setText(("🖼 " if t else "▫ ") + ex["name"])
            self.touch()
        img = FilePicker(ex.get("image", ""), set_img,
                         "画像 (*.png *.jpg *.jpeg *.bmp *.webp)")
        f.addRow("表情名:", name)
        f.addRow("立ち絵画像:", img)
        host = QWidget(); host.setLayout(f)
        self.expr_form_host.addWidget(host)

    def _add_expr(self, e):
        e.setdefault("expressions", []).append(
            {"id": uid("expr"), "name": "新しい表情", "image": ""})
        self._reload_expr_list(e)
        self.expr_list.setCurrentRow(self.expr_list.count() - 1)
        self.touch()

    def _del_expr(self, e):
        row = self.expr_list.currentRow()
        exprs = e.get("expressions", [])
        if 0 <= row < len(exprs):
            del exprs[row]
            self._reload_expr_list(e)
            self.touch()
