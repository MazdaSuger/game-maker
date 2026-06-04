"""フローチャートタブ — シーンと分岐の流れを可視化する.

ノード＝シーン（＋エンディング）、エッジ＝遷移
（選択肢・条件分岐(if)・シーン移動(jump)・エンディング）。
開始シーンからの深さで自動レイアウトする。ノードをダブルクリックすると
そのシーンをシーンエディタで開く。
"""

from __future__ import annotations

import math

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QGraphicsView,
    QGraphicsScene, QGraphicsItem, QGraphicsRectItem, QGraphicsSimpleTextItem,
    QGraphicsPathItem, QLabel,
)
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QColor, QPen, QBrush, QPainterPath, QPolygonF, QFont, QPainter

from .model import Project

NODE_W, NODE_H = 170, 56
COL_GAP, ROW_GAP = 240, 96


class _Node(QGraphicsRectItem):
    def __init__(self, node_id, label, kind, on_open):
        super().__init__(0, 0, NODE_W, NODE_H)
        self.node_id = node_id
        self.kind = kind            # scene / ending / start
        self._on_open = on_open
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)
        self.edges = []             # 接続エッジ（再描画用）

        if kind == "start":
            fill, border = "#2f5fd0", "#7aa0ff"
        elif kind == "ending":
            fill, border = "#5a3a10", "#f0a030"
        else:
            fill, border = "#283050", "#5a6aa0"
        self.setBrush(QBrush(QColor(fill)))
        self.setPen(QPen(QColor(border), 2))

        txt = QGraphicsSimpleTextItem(label, self)
        f = QFont(); f.setPointSize(10); f.setBold(True)
        txt.setFont(f)
        txt.setBrush(QBrush(QColor("#ffffff")))
        # 中央寄せ
        br = txt.boundingRect()
        txt.setPos((NODE_W - br.width()) / 2, (NODE_H - br.height()) / 2)

    def center(self) -> QPointF:
        return self.pos() + QPointF(NODE_W / 2, NODE_H / 2)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            for e in self.edges:
                e.update_path()
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event):
        if self.kind in ("scene", "start") and self._on_open:
            self._on_open(self.node_id)
        super().mouseDoubleClickEvent(event)


class _Edge(QGraphicsPathItem):
    def __init__(self, src: _Node, dst: _Node, label: str, color: str):
        super().__init__()
        self.src = src
        self.dst = dst
        self.label_text = label
        self.setPen(QPen(QColor(color), 2))
        self.setZValue(-1)
        self._color = color
        self._label_item = None
        if label:
            self._label_item = QGraphicsSimpleTextItem(label)
            self._label_item.setBrush(QBrush(QColor("#cdd6f4")))
            f = QFont(); f.setPointSize(8); self._label_item.setFont(f)
        src.edges.append(self)
        dst.edges.append(self)
        self.update_path()

    def update_path(self):
        p1 = self.src.center()
        p2 = self.dst.center()
        path = QPainterPath(p1)
        # ゆるいベジェ曲線
        dx = (p2.x() - p1.x()) * 0.5
        path.cubicTo(p1.x() + dx, p1.y(), p2.x() - dx, p2.y(), p2.x(), p2.y())
        self.setPath(path)
        if self._label_item is not None:
            mid = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2 - 8)
            self._label_item.setPos(mid)

    def attach_label(self, scene: QGraphicsScene):
        if self._label_item is not None:
            scene.addItem(self._label_item)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        # 矢印の先端
        p1 = self.src.center()
        p2 = self.dst.center()
        ang = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())
        # ノード境界手前で矢印を描く（dst の中心から手前へオフセット）
        tip = QPointF(p2.x() - math.cos(ang) * (NODE_W / 2),
                      p2.y() - math.sin(ang) * (NODE_H / 2))
        size = 9
        a = QPointF(tip.x() - math.cos(ang - 0.5) * size,
                    tip.y() - math.sin(ang - 0.5) * size)
        b = QPointF(tip.x() - math.cos(ang + 0.5) * size,
                    tip.y() - math.sin(ang + 0.5) * size)
        painter.setBrush(QBrush(QColor(self._color)))
        painter.setPen(QPen(QColor(self._color)))
        painter.drawPolygon(QPolygonF([tip, a, b]))


class FlowchartTab(QWidget):
    sceneOpenRequested = Signal(str)   # scene_id

    def __init__(self, project: Project):
        super().__init__()
        self.project = project

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("<b>分岐フローチャート</b>　"
                             "（ノードをドラッグで移動 / ダブルクリックでシーンを開く）"))
        bar.addStretch()
        refresh = QPushButton("🔄 更新")
        refresh.clicked.connect(self.rebuild)
        zin = QPushButton("＋")
        zin.setFixedWidth(36)
        zin.clicked.connect(lambda: self.view.scale(1.2, 1.2))
        zout = QPushButton("－")
        zout.setFixedWidth(36)
        zout.clicked.connect(lambda: self.view.scale(1 / 1.2, 1 / 1.2))
        fit = QPushButton("全体表示")
        fit.clicked.connect(self._fit)
        for b in (refresh, zin, zout, fit):
            bar.addWidget(b)
        root.addLayout(bar)

        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setBackgroundBrush(QBrush(QColor("#0e1118")))
        root.addWidget(self.view, 1)

        self.rebuild()

    # ------------------------------------------------------------------
    def _fit(self):
        if self.scene.itemsBoundingRect().isValid():
            self.view.fitInView(self.scene.itemsBoundingRect().adjusted(-40, -40, 40, 40),
                                Qt.KeepAspectRatio)

    def rebuild(self):
        self.scene.clear()
        p = self.project
        scenes = p.scenes
        if not scenes:
            self.scene.addText("シーンがありません")
            return

        # --- エッジ情報を収集 ---
        # edges: list of (src_scene_id, dst_node_id, label, color)
        edges = []
        ending_nodes = {}  # ending_id -> node_id
        for s in scenes:
            sid = s["id"]
            for cmd in s.get("commands", []):
                t = cmd.get("type")
                if t == "choice":
                    for opt in cmd.get("options", []):
                        if opt.get("targetScene"):
                            edges.append((sid, opt["targetScene"],
                                          _short(opt.get("text", "")), "#4cc2a0"))
                elif t == "jump":
                    if cmd.get("targetScene"):
                        edges.append((sid, cmd["targetScene"], "移動", "#7a86c8"))
                elif t == "if":
                    if cmd.get("targetTrue"):
                        edges.append((sid, cmd["targetTrue"], "条件:真", "#6bd06b"))
                    if cmd.get("targetFalse"):
                        edges.append((sid, cmd["targetFalse"], "条件:偽", "#d06b6b"))
                elif t == "ending":
                    eid = cmd.get("endingId", "")
                    end = p.ending(eid)
                    if end:
                        nid = "end:" + eid
                        ending_nodes[nid] = end
                        edges.append((sid, nid, "", "#f0a030"))

        # --- 自動レイアウト（開始シーンからの深さ） ---
        start = p.meta.get("startScene", scenes[0]["id"])
        adj = {}
        for src, dst, _l, _c in edges:
            adj.setdefault(src, []).append(dst)

        depth = {}
        order = []
        from collections import deque
        dq = deque()
        if p.scene(start):
            dq.append((start, 0))
            depth[start] = 0
        for s in scenes:  # 念のため全シーンを起点候補に
            if s["id"] not in depth:
                pass
        while dq:
            nid, d = dq.popleft()
            order.append(nid)
            for nxt in adj.get(nid, []):
                if nxt not in depth:
                    depth[nxt] = d + 1
                    dq.append((nxt, d + 1))
        # 未到達シーンを末尾の列に
        max_d = max(depth.values()) if depth else 0
        for s in scenes:
            if s["id"] not in depth:
                max_d += 0
                depth[s["id"]] = max(depth.values(), default=0) + 1
        # エンディングノードの深さ＝接続元+1
        for src, dst, _l, _c in edges:
            if dst.startswith("end:"):
                depth[dst] = max(depth.get(dst, 0), depth.get(src, 0) + 1)

        # 列ごとに行を割り当て
        col_rows = {}
        node_pos = {}
        # 安定した順序で配置：シーン→エンディング
        all_nodes = [s["id"] for s in scenes] + list(ending_nodes.keys())
        for nid in all_nodes:
            d = depth.get(nid, 0)
            row = col_rows.get(d, 0)
            col_rows[d] = row + 1
            node_pos[nid] = (d, row)

        # --- ノード生成 ---
        items = {}
        for s in scenes:
            nid = s["id"]
            kind = "start" if nid == start else "scene"
            node = _Node(nid, _short(s["name"], 16), kind, self._open_scene)
            d, row = node_pos[nid]
            node.setPos(d * COL_GAP, row * ROW_GAP)
            self.scene.addItem(node)
            items[nid] = node
        for nid, end in ending_nodes.items():
            lock = "🔒" if end.get("hidden") else "🏁"
            node = _Node(nid, f'{lock} {_short(end["name"], 14)}', "ending", None)
            d, row = node_pos[nid]
            node.setPos(d * COL_GAP, row * ROW_GAP)
            self.scene.addItem(node)
            items[nid] = node

        # --- エッジ生成 ---
        for src, dst, label, color in edges:
            if src in items and dst in items:
                e = _Edge(items[src], items[dst], label, color)
                self.scene.addItem(e)
                e.attach_label(self.scene)

        self._fit()

    def _open_scene(self, scene_id: str):
        self.sceneOpenRequested.emit(scene_id)

    def reload(self):
        self.rebuild()


def _short(text: str, n: int = 16) -> str:
    text = (text or "").replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "…"
