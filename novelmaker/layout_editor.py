"""レイアウト編集タブ.

- ドラッグでコンポーネント（セリフ枠・立ち絵・選択肢・ゲージ・
  アイテムボタン・メニュー）の表示位置を変更できる。
- コンポーネントの取り込み画像（テーマ）を設定できる。

位置は 16:9 のプレビュー上で編集し、画面サイズに対する百分率で保持する。
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QFrame,
    QPushButton, QGroupBox, QScrollArea,
)
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QColor

from .model import (
    Project, merged_layout, merged_theme, LAYOUT_ELEMENTS, THEME_FIELDS,
    DEFAULT_LAYOUT, COMP_TARGETS,
)
from .editors import FilePicker

# プレビューキャンバスのサイズ（16:9）
PW, PH = 640, 360

# 各要素のプレビュー上の代表サイズ（プレビュー px）と色
_ELEM_STYLE = {
    "message": (PW * 0.92, PH * 0.26, "#3a6df0"),
    "spriteLeft":   (PW * 0.16, PH * 0.70, "#e060b0"),
    "spriteCenter": (PW * 0.16, PH * 0.70, "#d04ca0"),
    "spriteRight":  (PW * 0.16, PH * 0.70, "#b03c90"),
    "choices": (PW * 0.42, PH * 0.30, "#4cc2a0"),
    "gauges":  (PW * 0.20, PH * 0.10, "#ff6b9d"),
    "items":   (PW * 0.06, PH * 0.11, "#f0a030"),
    "menu":    (PW * 0.34, PH * 0.09, "#8a7bf0"),
    "titleName": (PW * 0.30, PH * 0.12, "#ffd56b"),
    "title":     (PW * 0.26, PH * 0.16, "#7ad0ff"),
}


class _Handle(QFrame):
    """ドラッグ可能な要素ハンドル。"""

    def __init__(self, elem_id: str, label: str, kind: str, color: str,
                 size, on_move, parent=None):
        super().__init__(parent)
        self.elem_id = elem_id
        self.kind = kind            # box / point / sprite
        self._on_move = on_move
        self.setFixedSize(int(size[0]), int(size[1]))
        self.setStyleSheet(
            f"background: {QColor(color).name()}33; "
            f"border: 2px solid {color}; border-radius: 6px; color:#fff;")
        lab = QLabel(label, self)
        lab.setAlignment(Qt.AlignCenter)
        lab.setStyleSheet("background: transparent; border: none; font-weight: bold;")
        lab.setGeometry(0, 0, self.width(), self.height())
        self._drag = None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.position().toPoint()

    def mouseMoveEvent(self, e):
        if self._drag is None:
            return
        parent = self.parentWidget()
        np = self.mapToParent(e.position().toPoint() - self._drag)
        x = max(0, min(parent.width() - self.width(), np.x()))
        y = max(0, min(parent.height() - self.height(), np.y()))
        self.move(x, y)
        self._on_move(self)

    def mouseReleaseEvent(self, e):
        self._drag = None


class _Canvas(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("layoutCanvas")
        self.setFixedSize(PW, PH)
        self.setStyleSheet(
            "#layoutCanvas { background: #11151f; border: 2px solid #3a4566; "
            "border-radius: 8px; }")


class LayoutEditor(QWidget):
    changed = Signal()

    def __init__(self, project: Project):
        super().__init__()
        self.project = project
        self.handles: dict[str, _Handle] = {}

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        # 左：プレビュー（ドラッグ編集）
        left = QVBoxLayout()
        left.addWidget(QLabel("<b>表示位置</b>　各コンポーネントをドラッグで移動できます"))
        wrap = QHBoxLayout()
        wrap.addStretch()
        self.canvas = _Canvas()
        wrap.addWidget(self.canvas)
        wrap.addStretch()
        left.addLayout(wrap)
        reset = QPushButton("位置を初期化")
        reset.clicked.connect(self._reset_layout)
        left.addWidget(reset, alignment=Qt.AlignLeft)
        left.addStretch()
        lw = QWidget(); lw.setLayout(left)
        root.addWidget(lw, 1)

        # 右：テーマ（取り込み画像）
        right = QVBoxLayout()
        box = QGroupBox("コンポーネント画像（取り込み）")
        bl = QFormLayout(box)
        theme = merged_theme(self.project)
        self.project.data.setdefault("theme", dict(theme))
        for key, label in THEME_FIELDS:
            picker = FilePicker(
                self.project.data["theme"].get(key, ""),
                lambda t, k=key: self._set_theme(k, t),
                "画像 (*.png *.jpg *.jpeg *.bmp *.webp)")
            bl.addRow(label + ":", picker)
        right.addWidget(box)
        hint = QLabel("※ 画像はセリフ枠・選択肢ボタン・タイトルボタン・アイテム\n"
                      "　ボタンの背景に引き伸ばして表示されます（プレイ画面に反映）。")
        hint.setStyleSheet("color:#888;")
        right.addWidget(hint)

        # 非表示にするコンポーネント
        hbox = QGroupBox("コンポーネントの非表示")
        hl = QVBoxLayout(hbox)
        hl.addWidget(QLabel("チェックを入れたコンポーネントはプレイ画面で消えます。"))
        self.project.data.setdefault("layout", {})
        from PySide6.QtWidgets import QCheckBox
        for elem_id, label in COMP_TARGETS:   # message/sprite/gauges/items/menu
            cb = QCheckBox(label)
            cur = self.project.data["layout"].get(elem_id, {})
            cb.setChecked(bool(cur.get("hidden", False)))
            cb.toggled.connect(lambda v, k=elem_id: self._set_hidden(k, v))
            hl.addWidget(cb)
        right.addWidget(hbox)

        # コンポーネントのサイズ
        szbox = QGroupBox("コンポーネントのサイズ")
        szf = QFormLayout(szbox)
        szf.addRow("セリフ枠 幅:", self._size_spin("message", "w", 10, 100, 92))
        szf.addRow("セリフ枠 高さ:", self._size_spin("message", "h", 5, 100, 26))
        for key, label in [("spriteLeft", "立ち絵(左) 大きさ"),
                           ("spriteCenter", "立ち絵(中) 大きさ"),
                           ("spriteRight", "立ち絵(右) 大きさ")]:
            szf.addRow(label + ":", self._size_spin(key, "scale", 10, 150, 80))
        for key, label in [("choices", "選択肢"), ("gauges", "ゲージ"),
                           ("items", "アイテムボタン"), ("menu", "メニュー"),
                           ("titleName", "タイトル文字"), ("title", "タイトルボタン")]:
            szf.addRow(label + " 大きさ:", self._size_spin(key, "scale", 30, 300, 100))
        right.addWidget(szbox)
        right.addStretch()
        rw = QWidget(); rw.setLayout(right)
        rw.setMaximumWidth(380)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(rw)
        scroll.setMaximumWidth(400)
        root.addWidget(scroll)

        self._build_handles()

    def _size_spin(self, key: str, field: str, lo: int, hi: int, default: int):
        from PySide6.QtWidgets import QSpinBox
        sp = QSpinBox()
        sp.setRange(lo, hi)
        sp.setSuffix(" %")
        cur = self.project.data.get("layout", {}).get(key, {}).get(field, default)
        try:
            sp.setValue(int(cur))
        except (TypeError, ValueError):
            sp.setValue(default)

        def on_change(v):
            self.project.data.setdefault("layout", {}).setdefault(key, {})[field] = v
            self.project.dirty = True
            self.changed.emit()
        sp.valueChanged.connect(on_change)
        return sp

    # ------------------------------------------------------------------
    def _build_handles(self):
        for h in self.handles.values():
            h.setParent(None)
        self.handles.clear()
        for elem_id, label, kind in LAYOUT_ELEMENTS:
            w, hgt, color = _ELEM_STYLE[elem_id]
            handle = _Handle(elem_id, label, kind, color, (w, hgt),
                             self._on_handle_move, self.canvas)
            self.handles[elem_id] = handle
            hide_key = "sprite" if elem_id.startswith("sprite") else elem_id
            hidden = self.project.data.get("layout", {}).get(hide_key, {}).get("hidden", False)
            handle.setVisible(not hidden)
        self._position_handles_from_layout()

    def _position_handles_from_layout(self):
        L = merged_layout(self.project)
        for elem_id, handle in self.handles.items():
            d = L.get(elem_id, DEFAULT_LAYOUT[elem_id])
            x = d.get("x", 50) / 100.0 * PW
            y = d.get("y", 50) / 100.0 * PH
            if handle.kind == "point":          # 中央アンカー or 左上
                if elem_id in ("choices", "titleName", "title"):
                    handle.move(int(x - handle.width() / 2),
                                int(y - handle.height() / 2))
                else:                           # gauges/items/menu は左上
                    handle.move(int(x), int(y))
            elif handle.kind == "sprite":       # 中央x・下端y
                handle.move(int(x - handle.width() / 2),
                            int(y - handle.height()))
            else:                               # box（セリフ枠）は左上
                handle.move(int(x), int(y))

    def _on_handle_move(self, handle: _Handle):
        self.project.data.setdefault("layout", {})
        d = self.project.data["layout"].setdefault(handle.elem_id, {})
        if handle.elem_id in ("choices", "titleName", "title"):
            d["x"] = round((handle.x() + handle.width() / 2) / PW * 100, 1)
            d["y"] = round((handle.y() + handle.height() / 2) / PH * 100, 1)
        elif handle.kind == "sprite":
            d["x"] = round((handle.x() + handle.width() / 2) / PW * 100, 1)
            d["y"] = round((handle.y() + handle.height()) / PH * 100, 1)
        else:
            d["x"] = round(handle.x() / PW * 100, 1)
            d["y"] = round(handle.y() / PH * 100, 1)
        self.project.dirty = True
        self.changed.emit()

    def _set_theme(self, key: str, path: str):
        self.project.data.setdefault("theme", {})[key] = path
        self.project.dirty = True
        self.changed.emit()

    def _set_hidden(self, elem_id: str, hidden: bool):
        d = self.project.data.setdefault("layout", {}).setdefault(elem_id, {})
        d["hidden"] = hidden
        # プレビュー上のハンドルを連動（立ち絵は3スロットまとめて）
        keys = (["spriteLeft", "spriteCenter", "spriteRight"]
                if elem_id == "sprite" else [elem_id])
        for k in keys:
            h = self.handles.get(k)
            if h is not None:
                h.setVisible(not hidden)
        self.project.dirty = True
        self.changed.emit()

    def _reset_layout(self):
        self.project.data["layout"] = {k: dict(v) for k, v in DEFAULT_LAYOUT.items()}
        self._position_handles_from_layout()
        self.project.dirty = True
        self.changed.emit()

    def reload(self):
        # プロジェクト差し替え時
        self._position_handles_from_layout()
