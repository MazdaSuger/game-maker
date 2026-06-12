"""シーンエディタ — シーン一覧とコマンド(コンポーネント)列を編集する.

左：シーン一覧。右：選択シーンのコマンド列。
コマンドはノーコードで追加・編集・並べ替え・複製・削除できる。
"""

from __future__ import annotations

import copy

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QMenu, QInputDialog, QMessageBox, QToolButton,
    QFrame, QDialog, QAbstractItemView,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QBrush

from .model import (
    Project, COMMAND_TYPES, COMMAND_ICONS, new_command, describe_command, uid,
)
from .command_dialog import CommandDialog


class SceneEditor(QWidget):
    changed = Signal()           # プロジェクトが変更された
    testFromScene = Signal(str)  # このシーンからテストプレイ（scene_id）

    def __init__(self, project: Project):
        super().__init__()
        self.project = project
        self.current_scene = None

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        # ---- 左：シーン一覧 ----
        left = QVBoxLayout()
        left.addWidget(QLabel("<b>シーン一覧</b>"))
        self.scene_list = QListWidget()
        self.scene_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.scene_list.currentRowChanged.connect(self._on_scene_selected)
        self.scene_list.itemDoubleClicked.connect(lambda _: self._rename_scene())
        self.scene_list.model().rowsMoved.connect(self._scenes_reordered)
        left.addWidget(self.scene_list, 1)

        srow = QHBoxLayout()
        for text, slot in [("＋追加", self._add_scene), ("複製", self._dup_scene),
                           ("改名", self._rename_scene), ("削除", self._del_scene)]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            srow.addWidget(b)
        left.addLayout(srow)

        # フォルダ（ファイル）操作はメニューにまとめる（横幅が狭くても読める）
        self.folder_btn = QToolButton()
        self.folder_btn.setText("📁 フォルダ操作")
        self.folder_btn.setPopupMode(QToolButton.InstantPopup)
        fmenu = QMenu(self)
        fmenu.addAction("このシーンをフォルダへ入れる／出す", self._set_folder)
        fmenu.addSeparator()
        fmenu.addAction("▲ フォルダごと上へ移動", lambda: self._move_folder(-1))
        fmenu.addAction("▼ フォルダごと下へ移動", lambda: self._move_folder(1))
        fmenu.addAction("⎘ フォルダごと複製", self._dup_folder)
        self.folder_btn.setMenu(fmenu)
        frow = QHBoxLayout()
        frow.addWidget(self.folder_btn)
        frow.addStretch()
        left.addLayout(frow)

        self.start_btn = QPushButton("⭐ 開始シーンに設定")
        self.start_btn.clicked.connect(self._set_start)
        left.addWidget(self.start_btn)

        self.test_btn = QPushButton("▶ このシーンからテスト")
        self.test_btn.setProperty("primary", True)
        self.test_btn.clicked.connect(self._test_from_here)
        left.addWidget(self.test_btn)

        lw = QWidget()
        lw.setLayout(left)
        lw.setMaximumWidth(260)
        root.addWidget(lw)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        root.addWidget(sep)

        # ---- 右：コマンド列 ----
        right = QVBoxLayout()
        self.scene_title = QLabel("<b>コマンド列</b>")
        right.addWidget(self.scene_title)

        self.cmd_list = QListWidget()
        self.cmd_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.cmd_list.itemDoubleClicked.connect(lambda _: self._edit_command())
        self.cmd_list.setAlternatingRowColors(True)
        self.cmd_list.model().rowsMoved.connect(self._commands_reordered)
        right.addWidget(self.cmd_list, 1)

        crow = QHBoxLayout()
        self.add_btn = QToolButton()
        self.add_btn.setText("＋ コンポーネント追加")
        self.add_btn.setPopupMode(QToolButton.InstantPopup)
        self._build_add_menu()
        crow.addWidget(self.add_btn)
        for text, slot in [("編集", self._edit_command), ("複製", self._dup_command),
                           ("▲", self._move_up), ("▼", self._move_down),
                           ("削除", self._del_command)]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            crow.addWidget(b)
        crow.addStretch()
        right.addLayout(crow)

        rw = QWidget()
        rw.setLayout(right)
        root.addWidget(rw, 1)

        self.reload()

    # ------------------------------------------------------------------
    def _build_add_menu(self):
        menu = QMenu(self)
        for ctype, label, icon in COMMAND_TYPES:
            act = menu.addAction(f"{icon}  {label}")
            act.triggered.connect(lambda checked=False, t=ctype: self._add_command(t))
        self.add_btn.setMenu(menu)

    # ------------------------------------------------------------------
    # フォルダ（ファイル）管理
    # ------------------------------------------------------------------
    def _folder_order(self):
        order = []
        for s in self.project.scenes:
            f = s.get("folder", "") or ""
            if f not in order:
                order.append(f)
        return order

    def _regroup(self, order=None):
        """同じフォルダのシーンが連続する並びへ整列する。"""
        if order is None:
            order = self._folder_order()
        by = {}
        for s in self.project.scenes:
            by.setdefault(s.get("folder", "") or "", []).append(s)
        out = []
        for f in order:
            out.extend(by.get(f, []))
        self.project.scenes[:] = out

    def _first_scene_row(self):
        for i in range(self.scene_list.count()):
            if self.scene_list.item(i).data(Qt.UserRole):
                return i
        return -1

    def reload(self):
        """プロジェクト全体を読み直す（読込/インポート後に呼ぶ）。"""
        self.scene_list.blockSignals(True)
        self.scene_list.clear()
        self._regroup()
        start = self.project.meta.get("startScene", "")
        last_folder = None
        for s in self.project.scenes:
            f = s.get("folder", "") or ""
            if f and f != last_folder:
                hdr = QListWidgetItem(f"📁 {f}")
                hdr.setData(Qt.UserRole, None)
                hdr.setFlags(Qt.ItemIsEnabled)   # 選択・ドラッグ不可
                ft = hdr.font(); ft.setBold(True); hdr.setFont(ft)
                hdr.setForeground(QBrush(QColor("#cfe0ff")))
                hdr.setBackground(QBrush(QColor("#20284a")))
                self.scene_list.addItem(hdr)
            last_folder = f
            mark = "⭐ " if s["id"] == start else ""
            indent = "   " if f else ""
            item = QListWidgetItem(f'{indent}{mark}{s["name"]}')
            item.setData(Qt.UserRole, s["id"])
            self.scene_list.addItem(item)
        self.scene_list.blockSignals(False)
        row = self._first_scene_row()
        if row >= 0:
            self.scene_list.setCurrentRow(row)
        else:
            self.current_scene = None
            self._reload_commands()

    def select_scene(self, scene_id: str):
        """指定IDのシーンを一覧で選択する（見出し行があるため行を検索）。"""
        for i in range(self.scene_list.count()):
            if self.scene_list.item(i).data(Qt.UserRole) == scene_id:
                self.scene_list.setCurrentRow(i)
                return

    def _refresh_scene_labels(self):
        start = self.project.meta.get("startScene", "")
        by_id = {s["id"]: s for s in self.project.scenes}
        for i in range(self.scene_list.count()):
            it = self.scene_list.item(i)
            sid = it.data(Qt.UserRole)
            if not sid or sid not in by_id:
                continue
            s = by_id[sid]
            mark = "⭐ " if sid == start else ""
            indent = "   " if (s.get("folder", "") or "") else ""
            it.setText(f'{indent}{mark}{s["name"]}')

    # ------------------------------------------------------------------
    # シーン操作
    # ------------------------------------------------------------------
    def _scenes_reordered(self, *args):
        """シーンをドラッグで並べ替えたら project.scenes も並べ替える。
        フォルダ見出し行は除外し、フォルダが連続するよう整列し直す。"""
        ids = [self.scene_list.item(i).data(Qt.UserRole)
               for i in range(self.scene_list.count())]
        ids = [i for i in ids if i]
        by_id = {s["id"]: s for s in self.project.scenes}
        self.project.scenes[:] = [by_id[i] for i in ids if i in by_id]
        self._regroup()
        sid = self.current_scene["id"] if self.current_scene else None
        # ドラッグ中の再入を避けて遅延リロード（見出しを再描画）
        QTimer.singleShot(0, lambda: self._reload_keep(sid))
        self._emit_changed()

    def _reload_keep(self, scene_id):
        self.reload()
        if scene_id:
            self.select_scene(scene_id)

    # ------------------------------------------------------------------
    def _set_folder(self):
        if not self.current_scene:
            return
        folders = [f for f in self._folder_order() if f]
        hint = ("\n既存フォルダ: " + ", ".join(folders)) if folders else ""
        cur = self.current_scene.get("folder", "") or ""
        name, ok = QInputDialog.getText(
            self, "フォルダ", "フォルダ名（空欄でフォルダから出す）:" + hint, text=cur)
        if not ok:
            return
        self.current_scene["folder"] = name.strip()
        sid = self.current_scene["id"]
        self._reload_keep(sid)
        self._emit_changed()

    def _move_folder(self, direction):
        if not self.current_scene:
            return
        f = self.current_scene.get("folder", "") or ""
        order = self._folder_order()
        i = order.index(f)
        j = i + direction
        if j < 0 or j >= len(order):
            return
        order[i], order[j] = order[j], order[i]
        self._regroup(order)
        sid = self.current_scene["id"]
        self._reload_keep(sid)
        self._emit_changed()

    def _dup_folder(self):
        if not self.current_scene:
            return
        f = self.current_scene.get("folder", "") or ""
        if not f:
            QMessageBox.information(self, "フォルダ複製",
                                   "このシーンはフォルダに入っていません。")
            return
        new_name = f + " のコピー"
        copies = []
        for s in [x for x in self.project.scenes if (x.get("folder", "") or "") == f]:
            cl = copy.deepcopy(s)
            cl["id"] = uid("scene")
            cl["folder"] = new_name
            for c in cl.get("commands", []):
                c["id"] = uid("cmd")
            copies.append(cl)
        self.project.scenes.extend(copies)
        self._regroup()
        self.reload()
        self._emit_changed()

    def _commands_reordered(self, *args):
        """コンポーネントをドラッグで並べ替えたら commands も並べ替える。"""
        if not self.current_scene:
            return
        ids = [self.cmd_list.item(i).data(Qt.UserRole)
               for i in range(self.cmd_list.count())]
        by_id = {c["id"]: c for c in self.current_scene["commands"]}
        self.current_scene["commands"][:] = [by_id[i] for i in ids if i in by_id]
        self._emit_changed()

    def _on_scene_selected(self, row: int):
        item = self.scene_list.item(row)
        if item is not None:
            sid = item.data(Qt.UserRole)
            if sid is None:
                return   # フォルダ見出し行は無視（選択を変えない）
            self.current_scene = self.project.scene(sid)
        elif 0 <= row < len(self.project.scenes):
            self.current_scene = self.project.scenes[row]
        else:
            self.current_scene = None
        self._reload_commands()

    def _add_scene(self):
        name, ok = QInputDialog.getText(self, "シーン追加", "シーン名:")
        if not ok or not name.strip():
            return
        scene = {"id": uid("scene"), "name": name.strip(), "commands": []}
        self.project.scenes.append(scene)
        if len(self.project.scenes) == 1:
            self.project.meta["startScene"] = scene["id"]
        self.reload()
        self.scene_list.setCurrentRow(len(self.project.scenes) - 1)
        self._emit_changed()

    def _dup_scene(self):
        if not self.current_scene:
            return
        clone = copy.deepcopy(self.current_scene)
        clone["id"] = uid("scene")
        clone["name"] = self.current_scene["name"] + " のコピー"
        # コマンドIDを振り直し
        for c in clone.get("commands", []):
            c["id"] = uid("cmd")
        self.project.scenes.append(clone)
        self.reload()
        self.scene_list.setCurrentRow(len(self.project.scenes) - 1)
        self._emit_changed()

    def _rename_scene(self):
        if not self.current_scene:
            return
        name, ok = QInputDialog.getText(self, "シーン名の変更", "シーン名:",
                                        text=self.current_scene["name"])
        if ok and name.strip():
            self.current_scene["name"] = name.strip()
            self._refresh_scene_labels()
            self.scene_title.setText(f'<b>コマンド列</b> — {name.strip()}')
            self._emit_changed()

    def _del_scene(self):
        if not self.current_scene:
            return
        if QMessageBox.question(self, "シーン削除",
                                f'シーン「{self.current_scene["name"]}」を削除しますか？') \
                != QMessageBox.Yes:
            return
        self.project.scenes.remove(self.current_scene)
        if self.project.meta.get("startScene") == self.current_scene["id"]:
            self.project.meta["startScene"] = \
                self.project.scenes[0]["id"] if self.project.scenes else ""
        self.reload()
        self._emit_changed()

    def _set_start(self):
        if not self.current_scene:
            return
        self.project.meta["startScene"] = self.current_scene["id"]
        self._refresh_scene_labels()
        self._emit_changed()

    def _test_from_here(self):
        if self.current_scene:
            self.testFromScene.emit(self.current_scene["id"])

    # ------------------------------------------------------------------
    # コマンド操作
    # ------------------------------------------------------------------
    def _reload_commands(self):
        self.cmd_list.clear()
        if not self.current_scene:
            self.scene_title.setText("<b>コマンド列</b>")
            return
        self.scene_title.setText(f'<b>コマンド列</b> — {self.current_scene["name"]}')
        self.cmd_list.blockSignals(True)
        for cmd in self.current_scene.get("commands", []):
            icon = COMMAND_ICONS.get(cmd["type"], "•")
            item = QListWidgetItem(f'{icon}  {describe_command(cmd, self.project)}')
            item.setData(Qt.UserRole, cmd["id"])
            self.cmd_list.addItem(item)
        self.cmd_list.blockSignals(False)

    def _current_cmd_index(self) -> int:
        return self.cmd_list.currentRow()

    def _add_command(self, ctype: str):
        if not self.current_scene:
            QMessageBox.information(self, "シーン未選択", "先にシーンを選択/作成してください。")
            return
        cmd = new_command(ctype)
        dlg = CommandDialog(cmd, self.project, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_cmd:
            idx = self._current_cmd_index()
            cmds = self.current_scene["commands"]
            if idx < 0:
                cmds.append(dlg.result_cmd)
                new_idx = len(cmds) - 1
            else:
                cmds.insert(idx + 1, dlg.result_cmd)
                new_idx = idx + 1
            self._reload_commands()
            self.cmd_list.setCurrentRow(new_idx)
            self._emit_changed()

    def _edit_command(self):
        idx = self._current_cmd_index()
        if not self.current_scene or idx < 0:
            return
        cmd = self.current_scene["commands"][idx]
        dlg = CommandDialog(cmd, self.project, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_cmd:
            self.current_scene["commands"][idx] = dlg.result_cmd
            self._reload_commands()
            self.cmd_list.setCurrentRow(idx)
            self._emit_changed()

    def _dup_command(self):
        idx = self._current_cmd_index()
        if not self.current_scene or idx < 0:
            return
        clone = copy.deepcopy(self.current_scene["commands"][idx])
        clone["id"] = uid("cmd")
        self.current_scene["commands"].insert(idx + 1, clone)
        self._reload_commands()
        self.cmd_list.setCurrentRow(idx + 1)
        self._emit_changed()

    def _move_up(self):
        idx = self._current_cmd_index()
        if not self.current_scene or idx <= 0:
            return
        cmds = self.current_scene["commands"]
        cmds[idx - 1], cmds[idx] = cmds[idx], cmds[idx - 1]
        self._reload_commands()
        self.cmd_list.setCurrentRow(idx - 1)
        self._emit_changed()

    def _move_down(self):
        idx = self._current_cmd_index()
        if not self.current_scene or idx < 0 or idx >= len(self.current_scene["commands"]) - 1:
            return
        cmds = self.current_scene["commands"]
        cmds[idx + 1], cmds[idx] = cmds[idx], cmds[idx + 1]
        self._reload_commands()
        self.cmd_list.setCurrentRow(idx + 1)
        self._emit_changed()

    def _del_command(self):
        idx = self._current_cmd_index()
        if not self.current_scene or idx < 0:
            return
        del self.current_scene["commands"][idx]
        self._reload_commands()
        self.cmd_list.setCurrentRow(min(idx, self.cmd_list.count() - 1))
        self._emit_changed()

    def _emit_changed(self):
        self.project.dirty = True
        self.changed.emit()
