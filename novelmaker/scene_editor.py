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
from PySide6.QtCore import Qt, Signal

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

    def reload(self):
        """プロジェクト全体を読み直す（読込/インポート後に呼ぶ）。"""
        self.scene_list.blockSignals(True)
        self.scene_list.clear()
        start = self.project.meta.get("startScene", "")
        for s in self.project.scenes:
            mark = "⭐ " if s["id"] == start else ""
            item = QListWidgetItem(f'{mark}{s["name"]}')
            item.setData(Qt.UserRole, s["id"])
            self.scene_list.addItem(item)
        self.scene_list.blockSignals(False)
        if self.project.scenes:
            self.scene_list.setCurrentRow(0)
        else:
            self.current_scene = None
            self._reload_commands()

    def select_scene(self, scene_id: str):
        """指定IDのシーンを一覧で選択する（フローチャックから呼ばれる）。"""
        for i, s in enumerate(self.project.scenes):
            if s["id"] == scene_id:
                self.scene_list.setCurrentRow(i)
                return

    def _refresh_scene_labels(self):
        start = self.project.meta.get("startScene", "")
        for i, s in enumerate(self.project.scenes):
            mark = "⭐ " if s["id"] == start else ""
            self.scene_list.item(i).setText(f'{mark}{s["name"]}')

    # ------------------------------------------------------------------
    # シーン操作
    # ------------------------------------------------------------------
    def _scenes_reordered(self, *args):
        """シーンをドラッグで並べ替えたら project.scenes も並べ替える。"""
        ids = [self.scene_list.item(i).data(Qt.UserRole)
               for i in range(self.scene_list.count())]
        by_id = {s["id"]: s for s in self.project.scenes}
        self.project.scenes[:] = [by_id[i] for i in ids if i in by_id]
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
            self.current_scene = self.project.scene(item.data(Qt.UserRole))
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
