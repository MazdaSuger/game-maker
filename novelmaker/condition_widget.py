"""条件式ビルダーウィジェット.

``{"logic": "and"|"or", "terms": [...]}`` 形式の条件式を
ノーコードで編集する。選択肢の出現条件・条件分岐(if)で使う。
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLineEdit,
    QPushButton, QLabel, QFrame,
)

from .model import Project, new_term

NUM_OPS = [("==", "="), ("!=", "≠"), (">", ">"), (">=", "≥"),
           ("<", "<"), ("<=", "≤")]
ITEM_OPS = [("has", "所持している"), ("notHas", "所持していない")]
KINDS = [("var", "変数"), ("gauge", "ゲージ"), ("item", "アイテム"),
         ("ending", "エンディング到達回数")]


class _TermRow(QWidget):
    """条件1項を編集する行。"""

    def __init__(self, term: dict, project: Project, on_remove):
        super().__init__()
        self.term = term
        self.project = project
        self._on_remove = on_remove

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self.kind_cb = QComboBox()
        for key, label in KINDS:
            self.kind_cb.addItem(label, key)
        self._set_combo(self.kind_cb, term.get("kind", "var"))
        self.kind_cb.currentIndexChanged.connect(self._kind_changed)

        self.ref_cb = QComboBox()
        self.ref_cb.setMinimumWidth(120)
        self.ref_cb.currentIndexChanged.connect(self._sync)

        self.op_cb = QComboBox()
        self.op_cb.currentIndexChanged.connect(self._sync)

        self.value_edit = QLineEdit()
        self.value_edit.setMaximumWidth(90)
        self.value_edit.setPlaceholderText("値")
        self.value_edit.textChanged.connect(self._sync)

        rm = QPushButton("✕")
        rm.setFixedWidth(28)
        rm.clicked.connect(lambda: self._on_remove(self))

        for w in (self.kind_cb, self.ref_cb, self.op_cb, self.value_edit, rm):
            lay.addWidget(w)

        self._rebuild_for_kind()

    @staticmethod
    def _set_combo(cb: QComboBox, data):
        for i in range(cb.count()):
            if cb.itemData(i) == data:
                cb.setCurrentIndex(i)
                return
        cb.setCurrentIndex(0)

    def _kind_changed(self):
        k = self.kind_cb.currentData()
        self.term["kind"] = k
        # kind 変更時は ref/op/value を初期化
        self.term["ref"] = ""
        self.term["op"] = "has" if k == "item" else (">=" if k == "ending" else "==")
        self.term["value"] = "1" if k == "ending" else ""
        self._rebuild_for_kind()
        self._sync()

    def _rebuild_for_kind(self):
        kind = self.kind_cb.currentData()
        # ref 候補
        self.ref_cb.blockSignals(True)
        self.ref_cb.clear()
        if kind == "var":
            for v in self.project.variables:
                self.ref_cb.addItem(v["name"], v["name"])
            for v in self.project.system_vars:   # システム変数も参照可
                self.ref_cb.addItem(f'{v["name"]} [SYS]', v["name"])
        elif kind == "gauge":
            for g in self.project.gauges:
                self.ref_cb.addItem(g["name"], g["id"])
        elif kind == "item":
            for it in self.project.items:
                self.ref_cb.addItem(it["name"], it["id"])
        elif kind == "ending":
            for e in self.project.endings:
                lock = "🔒" if e.get("hidden") else ""
                self.ref_cb.addItem(f'{lock}{e["name"]}', e["id"])
        self._set_combo(self.ref_cb, self.term.get("ref", ""))
        self.ref_cb.blockSignals(False)

        # op 候補
        self.op_cb.blockSignals(True)
        self.op_cb.clear()
        ops = ITEM_OPS if kind == "item" else NUM_OPS
        for key, label in ops:
            self.op_cb.addItem(label, key)
        self._set_combo(self.op_cb, self.term.get("op", ops[0][0]))
        self.op_cb.blockSignals(False)

        # value はアイテム時は不要
        self.value_edit.setVisible(kind != "item")
        self.value_edit.setText(str(self.term.get("value", "")))

    def _sync(self):
        self.term["kind"] = self.kind_cb.currentData()
        self.term["ref"] = self.ref_cb.currentData() or ""
        self.term["op"] = self.op_cb.currentData() or "=="
        self.term["value"] = self.value_edit.text()


class ConditionWidget(QWidget):
    """条件式全体（AND/OR + 複数項）を編集する。"""

    def __init__(self, condition: dict, project: Project):
        super().__init__()
        self.condition = condition
        self.project = project

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        top.addWidget(QLabel("条件:"))
        self.logic_cb = QComboBox()
        self.logic_cb.addItem("すべて満たす (AND)", "and")
        self.logic_cb.addItem("いずれか満たす (OR)", "or")
        self._set_logic(condition.get("logic", "and"))
        self.logic_cb.currentIndexChanged.connect(self._logic_changed)
        top.addWidget(self.logic_cb)
        add_btn = QPushButton("+ 条件を追加")
        add_btn.clicked.connect(self._add_term)
        top.addWidget(add_btn)
        top.addStretch()
        outer.addLayout(top)

        self.rows_box = QVBoxLayout()
        outer.addLayout(self.rows_box)

        self.empty_label = QLabel("（条件なし＝常に成立）")
        self.empty_label.setStyleSheet("color:#888; font-style:italic;")
        outer.addWidget(self.empty_label)

        self._rows: list[_TermRow] = []
        for term in condition.get("terms", []):
            self._add_row_widget(term)
        self._update_empty()

    def _set_logic(self, val):
        for i in range(self.logic_cb.count()):
            if self.logic_cb.itemData(i) == val:
                self.logic_cb.setCurrentIndex(i)
                return

    def _logic_changed(self):
        self.condition["logic"] = self.logic_cb.currentData()

    def _add_term(self):
        term = new_term("var")
        self.condition.setdefault("terms", []).append(term)
        self._add_row_widget(term)
        self._update_empty()

    def _add_row_widget(self, term: dict):
        row = _TermRow(term, self.project, self._remove_row)
        self._rows.append(row)
        self.rows_box.addWidget(row)

    def _remove_row(self, row: _TermRow):
        if row.term in self.condition.get("terms", []):
            self.condition["terms"].remove(row.term)
        self._rows.remove(row)
        row.setParent(None)
        self._update_empty()

    def _update_empty(self):
        self.empty_label.setVisible(len(self._rows) == 0)
