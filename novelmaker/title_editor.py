"""タイトル演出エディタ.

条件（全エンディング解放・到達回数・システム変数など）を満たしたとき、
タイトル画面の背景/BGM/ロゴを差し替え、ボタンを追加する「演出」を編集する。
"""

from __future__ import annotations

import copy

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QLineEdit, QComboBox, QGroupBox, QScrollArea, QFrame,
)
from PySide6.QtCore import Qt, Signal

from .model import Project, new_title_variation, empty_condition
from .condition_widget import ConditionWidget
from .editors import FilePicker


def _combo(items, current, none_label):
    cb = QComboBox()
    cb.addItem(none_label, "")
    for value, label in items:
        cb.addItem(label, value)
    for i in range(cb.count()):
        if cb.itemData(i) == current:
            cb.setCurrentIndex(i)
            break
    return cb


class TitleVariationEditor(QWidget):
    changed = Signal()

    def __init__(self, project: Project):
        super().__init__()
        self.project = project
        self.current = None

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)

        left = QVBoxLayout()
        left.addWidget(QLabel("<b>タイトル演出一覧</b>"))
        info = QLabel("条件を満たした最初の演出が適用されます\n（上から順に評価）。")
        info.setStyleSheet("color:#888;")
        left.addWidget(info)
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
        lw = QWidget(); lw.setLayout(left); lw.setMaximumWidth(280)
        root.addWidget(lw)

        sep = QFrame(); sep.setFrameShape(QFrame.VLine)
        root.addWidget(sep)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.form_host = QWidget()
        self.form_layout = QVBoxLayout(self.form_host)
        self.scroll.setWidget(self.form_host)
        root.addWidget(self.scroll, 1)

        self.reload()

    # ------------------------------------------------------------------
    def entries(self):
        return self.project.meta.setdefault("titleVariations", [])

    def reload(self):
        self.list.blockSignals(True)
        self.list.clear()
        for v in self.entries():
            self.list.addItem(v.get("name", "(無題)"))
        self.list.blockSignals(False)
        if self.entries():
            self.list.setCurrentRow(0)
        else:
            self.current = None
            self._clear_form()

    def _on_select(self, row):
        e = self.entries()
        self.current = e[row] if 0 <= row < len(e) else None
        self._rebuild_form()

    def _clear_form(self):
        while self.form_layout.count():
            it = self.form_layout.takeAt(0)
            if it.widget():
                it.widget().setParent(None)

    def _touch(self):
        row = self.list.currentRow()
        if self.current is not None and 0 <= row < self.list.count():
            self.list.item(row).setText(self.current.get("name", "(無題)"))
        self.project.dirty = True
        self.changed.emit()

    # ------------------------------------------------------------------
    def _rebuild_form(self):
        self._clear_form()
        if self.current is None:
            return
        v = self.current
        f = QFormLayout()
        name = QLineEdit(v.get("name", ""))
        name.textChanged.connect(lambda t: (v.__setitem__("name", t), self._touch()))
        f.addRow("演出名:", name)
        bg = _combo([(b["id"], b["name"]) for b in self.project.backgrounds],
                    v.get("bg", ""), "（既定の背景のまま）")
        bg.currentIndexChanged.connect(
            lambda _i: (v.__setitem__("bg", bg.currentData() or ""), self._touch()))
        f.addRow("タイトル背景:", bg)
        bgm = _combo([(t["id"], t["name"]) for t in self.project.bgm],
                     v.get("bgm", ""), "（既定のBGMのまま）")
        bgm.currentIndexChanged.connect(
            lambda _i: (v.__setitem__("bgm", bgm.currentData() or ""), self._touch()))
        f.addRow("タイトルBGM:", bgm)
        logo = FilePicker(v.get("logo", ""),
                          lambda t: (v.__setitem__("logo", t), self._touch()),
                          "画像 (*.png *.jpg *.jpeg *.bmp *.webp)")
        f.addRow("ロゴ画像:", logo)
        from .editors import ColorButton
        color = ColorButton(v.get("color") or "#ffffff",
                            lambda cc: (v.__setitem__("color", cc), self._touch()))
        f.addRow("タイトル文字の色:", color)
        host = QWidget(); host.setLayout(f)
        self.form_layout.addWidget(host)

        # 条件
        v.setdefault("condition", empty_condition())
        cbox = QGroupBox("適用条件（例：全エンディング解放）")
        cl = QVBoxLayout(cbox)
        cl.addWidget(ConditionWidget(v["condition"], self.project))
        self.form_layout.addWidget(cbox)

        # 追加ボタン
        bbox = QGroupBox("タイトルに追加するボタン")
        self.btns_layout = QVBoxLayout(bbox)
        v.setdefault("buttons", [])
        for spec in v["buttons"]:
            self._add_button_row(spec)
        addb = QPushButton("＋ ボタンを追加")
        addb.clicked.connect(self._add_button)
        self.btns_layout.addWidget(addb)
        self.form_layout.addWidget(bbox)
        self.form_layout.addStretch()

    def _add_button(self):
        spec = {"text": "おまけ", "targetScene": ""}
        self.current["buttons"].append(spec)
        self._add_button_row(spec)
        self._touch()

    def _add_button_row(self, spec):
        row = QFrame()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        text = QLineEdit(spec.get("text", ""))
        text.setPlaceholderText("ボタン文字")
        text.textChanged.connect(lambda t: (spec.__setitem__("text", t), self._touch()))
        scene = _combo([(s["id"], s["name"]) for s in self.project.scenes],
                       spec.get("targetScene", ""), "（移動先シーン）")
        scene.currentIndexChanged.connect(
            lambda _i: (spec.__setitem__("targetScene", scene.currentData() or ""),
                        self._touch()))
        rm = QPushButton("✕"); rm.setFixedWidth(30)

        def remove():
            if spec in self.current["buttons"]:
                self.current["buttons"].remove(spec)
            row.setParent(None)
            self._touch()
        rm.clicked.connect(remove)
        rl.addWidget(text, 2); rl.addWidget(scene, 2); rl.addWidget(rm)
        # 「＋ボタンを追加」の前に挿入
        self.btns_layout.insertWidget(self.btns_layout.count() - 1, row)

    # ------------------------------------------------------------------
    def _add(self):
        self.entries().append(new_title_variation())
        self.reload()
        self.list.setCurrentRow(self.list.count() - 1)
        self._touch()

    def _dup(self):
        if self.current is None:
            return
        from .model import uid
        clone = copy.deepcopy(self.current)
        clone["id"] = uid("tv")
        clone["name"] = self.current.get("name", "") + " のコピー"
        self.entries().append(clone)
        self.reload()
        self.list.setCurrentRow(self.list.count() - 1)
        self._touch()

    def _del(self):
        row = self.list.currentRow()
        if self.current is None:
            return
        self.entries().remove(self.current)
        self.reload()
        self.list.setCurrentRow(min(row, self.list.count() - 1))
        self._touch()

    def _up(self):
        row = self.list.currentRow()
        e = self.entries()
        if row > 0:
            e[row - 1], e[row] = e[row], e[row - 1]
            self.reload(); self.list.setCurrentRow(row - 1); self._touch()

    def _down(self):
        row = self.list.currentRow()
        e = self.entries()
        if 0 <= row < len(e) - 1:
            e[row + 1], e[row] = e[row], e[row + 1]
            self.reload(); self.list.setCurrentRow(row + 1); self._touch()
