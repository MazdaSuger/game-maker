"""メインウィンドウ — エディタ各タブとプレイヤーを統合する."""

from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QTabWidget, QStackedWidget, QVBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QLabel, QFileDialog, QMessageBox, QToolBar, QHBoxLayout,
    QPushButton,
)
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtCore import Qt, QStandardPaths

from . import APP_NAME, __version__
from .model import Project
from .scene_editor import SceneEditor
from .editors import (
    CharacterEditor, ItemEditor, VariableEditor, GaugeEditor,
    BackgroundEditor, BgmEditor, EndingEditor, SeEditor, CgEditor,
)
from .layout_editor import LayoutEditor
from .flowchart import FlowchartTab
from .player import PlayerWidget
from .save import SaveManager, default_save_dir
from .exporter import export_to_html, export_to_zip

PROJECT_FILTER = "ノベルメーカー プロジェクト (*.nvproj);;JSON (*.json);;すべて (*.*)"


def save_path_for(project: Project) -> str:
    if project.path:
        base = os.path.splitext(project.path)[0]
        return base + ".saves.json"
    return os.path.join(default_save_dir(), "untitled.saves.json")


def default_documents_dir() -> str:
    """保存ダイアログの初期ディレクトリ（書き込み可能な場所）を返す。

    macOS の .app はカレントディレクトリが "/"（読み取り専用）になるため、
    相対パスのままだと保存に失敗する。書類フォルダ→ホームの順に解決する。
    """
    for loc in (QStandardPaths.DocumentsLocation,
                QStandardPaths.HomeLocation,
                QStandardPaths.DesktopLocation):
        d = QStandardPaths.writableLocation(loc)
        if d and os.path.isdir(d):
            return d
    return os.path.expanduser("~")


class SettingsEditor(QWidget):
    """ゲーム全体の設定（タイトル/作者/開始シーン）。"""

    def __init__(self, project: Project):
        super().__init__()
        self.project = project
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.addWidget(QLabel("<h2>ゲーム設定</h2>"))
        f = QFormLayout()

        self.title_edit = QLineEdit(project.meta.get("title", ""))
        self.title_edit.textChanged.connect(
            lambda t: project.meta.__setitem__("title", t))
        self.author_edit = QLineEdit(project.meta.get("author", ""))
        self.author_edit.textChanged.connect(
            lambda t: project.meta.__setitem__("author", t))
        self.start_cb = QComboBox()
        self.start_cb.currentIndexChanged.connect(self._set_start)
        self.titlebg_cb = QComboBox()
        self.titlebg_cb.currentIndexChanged.connect(self._set_titlebg)
        self.titlebgm_cb = QComboBox()
        self.titlebgm_cb.currentIndexChanged.connect(self._set_titlebgm)

        f.addRow("タイトル:", self.title_edit)
        f.addRow("作者:", self.author_edit)
        f.addRow("開始シーン:", self.start_cb)
        f.addRow("タイトル画面の背景:", self.titlebg_cb)
        f.addRow("タイトル画面のBGM:", self.titlebgm_cb)
        lay.addLayout(f)

        info = QLabel(
            f"<p style='color:#888'>{APP_NAME} v{__version__}<br>"
            "ノベルゲーム特化のノーコード制作ソフト。<br>"
            "変数・分岐・名前入力・BGM・キャラ表情差分・アイテム・<br>"
            "セリフ・エンディング(裏含む)・10スロットセーブ・暗転/背景・ゲージに対応。</p>")
        lay.addWidget(info)
        lay.addStretch()
        self.reload()

    def reload(self):
        self.title_edit.setText(self.project.meta.get("title", ""))
        self.author_edit.setText(self.project.meta.get("author", ""))
        self.start_cb.blockSignals(True)
        self.start_cb.clear()
        for s in self.project.scenes:
            self.start_cb.addItem(s["name"], s["id"])
        start = self.project.meta.get("startScene", "")
        for i in range(self.start_cb.count()):
            if self.start_cb.itemData(i) == start:
                self.start_cb.setCurrentIndex(i)
                break
        self.start_cb.blockSignals(False)

        # タイトル背景・BGM
        self._fill_combo(self.titlebg_cb,
                         [(b["id"], b["name"]) for b in self.project.backgrounds],
                         self.project.meta.get("titleBg", ""), "（なし）")
        self._fill_combo(self.titlebgm_cb,
                         [(t["id"], t["name"]) for t in self.project.bgm],
                         self.project.meta.get("titleBgm", ""), "（なし）")

    @staticmethod
    def _fill_combo(cb, items, current, none_label):
        cb.blockSignals(True)
        cb.clear()
        cb.addItem(none_label, "")
        for value, label in items:
            cb.addItem(label, value)
        for i in range(cb.count()):
            if cb.itemData(i) == current:
                cb.setCurrentIndex(i)
                break
        cb.blockSignals(False)

    def _set_start(self, _):
        sid = self.start_cb.currentData()
        if sid:
            self.project.meta["startScene"] = sid
            self.project.dirty = True

    def _set_titlebg(self, _):
        self.project.meta["titleBg"] = self.titlebg_cb.currentData() or ""
        self.project.dirty = True

    def _set_titlebgm(self, _):
        self.project.meta["titleBgm"] = self.titlebgm_cb.currentData() or ""
        self.project.dirty = True


class MainWindow(QMainWindow):
    def __init__(self, project: Project = None):
        super().__init__()
        self.project = project or Project()
        self.player = None
        self.setWindowTitle(APP_NAME)
        self.resize(1100, 720)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        # --- エディタページ ---
        self.editor_page = QWidget()
        epl = QVBoxLayout(self.editor_page)
        epl.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self._build_tabs()
        epl.addWidget(self.tabs)
        self.stack.addWidget(self.editor_page)

        self._build_toolbar()
        self._build_menu()
        self._update_title()

    # ------------------------------------------------------------------
    def _build_tabs(self):
        self.scene_editor = SceneEditor(self.project)
        self.character_editor = CharacterEditor(self.project)
        self.item_editor = ItemEditor(self.project)
        self.variable_editor = VariableEditor(self.project)
        self.gauge_editor = GaugeEditor(self.project)
        self.background_editor = BackgroundEditor(self.project)
        self.cg_editor = CgEditor(self.project)
        self.bgm_editor = BgmEditor(self.project)
        self.se_editor = SeEditor(self.project)
        self.ending_editor = EndingEditor(self.project)
        self.layout_editor = LayoutEditor(self.project)
        self.flowchart_tab = FlowchartTab(self.project)
        self.settings_editor = SettingsEditor(self.project)

        self._editors = [
            ("🎬 シーン", self.scene_editor),
            ("🗺 フローチャート", self.flowchart_tab),
            ("🧑 キャラ・表情", self.character_editor),
            ("🎒 アイテム", self.item_editor),
            ("🔢 変数", self.variable_editor),
            ("📊 ゲージ", self.gauge_editor),
            ("🖼 背景", self.background_editor),
            ("🌅 CG", self.cg_editor),
            ("🎵 BGM", self.bgm_editor),
            ("🔊 SE", self.se_editor),
            ("🏁 エンディング", self.ending_editor),
            ("🎨 レイアウト", self.layout_editor),
            ("⚙ 設定", self.settings_editor),
        ]
        for label, w in self._editors:
            self.tabs.addTab(w, label)

        # シーン変更時に設定タブの開始シーン候補を更新
        self.scene_editor.changed.connect(self._on_project_changed)
        self.scene_editor.testFromScene.connect(self.play_from)
        self.layout_editor.changed.connect(self._on_project_changed)
        self.flowchart_tab.sceneOpenRequested.connect(self._open_scene_from_flowchart)
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _open_scene_from_flowchart(self, scene_id: str):
        self.tabs.setCurrentWidget(self.scene_editor)
        self.scene_editor.select_scene(scene_id)

    def _on_tab_changed(self, _):
        cur = self.tabs.currentWidget()
        # 設定タブ表示時に開始シーン一覧をリフレッシュ
        if cur is self.settings_editor:
            self.settings_editor.reload()
        # フローチャートは最新のシーン構成で再描画
        elif cur is self.flowchart_tab:
            self.flowchart_tab.rebuild()

    def _on_project_changed(self):
        self.project.dirty = True
        self._update_title()

    def _build_toolbar(self):
        tb = QToolBar("メイン")
        tb.setMovable(False)
        self.addToolBar(tb)

        play_act = QAction("▶ テストプレイ", self)
        play_act.setShortcut("F5")
        play_act.triggered.connect(self.play)
        tb.addAction(play_act)
        tb.addSeparator()

        new_act = QAction("新規", self)
        new_act.triggered.connect(self.new_project)
        open_act = QAction("開く", self)
        open_act.triggered.connect(self.open_project)
        save_act = QAction("保存", self)
        save_act.triggered.connect(self.save_project)
        for a in (new_act, open_act, save_act):
            tb.addAction(a)

    def _build_menu(self):
        m = self.menuBar().addMenu("ファイル")
        for text, slot, sc in [
            ("新規プロジェクト", self.new_project, QKeySequence.New),
            ("開く…", self.open_project, QKeySequence.Open),
            ("保存", self.save_project, QKeySequence.Save),
            ("名前を付けて保存…", self.save_project_as, QKeySequence.SaveAs),
        ]:
            a = QAction(text, self)
            if sc:
                a.setShortcut(sc)
            a.triggered.connect(slot)
            m.addAction(a)
        m.addSeparator()
        export_a = QAction("🌐 ブラウザ(HTML)に書き出し…", self)
        export_a.triggered.connect(self.export_html)
        m.addAction(export_a)
        zip_a = QAction("☁ Cloudflare用ZIPに書き出し…", self)
        zip_a.triggered.connect(self.export_zip)
        m.addAction(zip_a)
        m.addSeparator()
        quit_a = QAction("終了", self)
        quit_a.triggered.connect(self.close)
        m.addAction(quit_a)

        play_m = self.menuBar().addMenu("実行")
        pa = QAction("テストプレイ", self)
        pa.setShortcut("F5")
        pa.triggered.connect(self.play)
        play_m.addAction(pa)

    # ------------------------------------------------------------------
    # テストプレイ
    # ------------------------------------------------------------------
    def play(self):
        self._launch_player(None)

    def play_from(self, scene_id: str):
        """選択したシーンからテストプレイを開始する（タイトルを飛ばす）。"""
        self._launch_player(scene_id)

    def _launch_player(self, start_scene):
        if not self.project.scenes:
            QMessageBox.information(self, "シーンがありません",
                                    "先にシーンを1つ以上作成してください。")
            return
        saves = SaveManager(save_path_for(self.project))
        self.player = PlayerWidget(self.project, saves)
        self.player.exited.connect(self._exit_player)
        self.stack.addWidget(self.player)
        self.stack.setCurrentWidget(self.player)
        if start_scene:
            self.player.start_at(start_scene)
        else:
            self.player.start()

    def export_html(self):
        """現在のプロジェクトをブラウザで遊べるWebゲームに書き出す。"""
        if not self.project.scenes:
            QMessageBox.information(self, "シーンがありません",
                                    "先にシーンを1つ以上作成してください。")
            return
        out_dir = QFileDialog.getExistingDirectory(
            self, "書き出し先フォルダを選択（中身が上書きされます）",
            default_documents_dir())
        if not out_dir:
            return
        # 空でないフォルダへの書き出しは確認
        try:
            if os.listdir(out_dir):
                if QMessageBox.question(
                        self, "確認",
                        "選択したフォルダにはすでにファイルがあります。\n"
                        "同名ファイルは上書きされます。続行しますか？") != QMessageBox.Yes:
                    return
        except OSError:
            pass
        try:
            result = export_to_html(self.project.data, out_dir)
        except Exception as e:
            QMessageBox.critical(self, "書き出し失敗", f"書き出せませんでした:\n{e}")
            return
        msg = (f"ブラウザ用ゲームを書き出しました。\n\n"
               f"場所: {out_dir}\n"
               f"アセット: {result['assets']} 個をコピー\n\n"
               f"「index.html」をブラウザで開くと遊べます。")
        if result["missing"]:
            msg += f"\n\n⚠ 見つからなかったファイル {len(result['missing'])} 件は除外しました。"
        box = QMessageBox(QMessageBox.Information, "書き出し完了", msg, parent=self)
        open_btn = box.addButton("フォルダを開く", QMessageBox.ActionRole)
        box.addButton("閉じる", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            self._open_folder(out_dir)
        self.statusBar().showMessage(f"ブラウザ書き出し完了: {out_dir}", 5000)

    def export_zip(self):
        """Cloudflare Pages 等へそのままデプロイできる ZIP を書き出す。"""
        if not self.project.scenes:
            QMessageBox.information(self, "シーンがありません",
                                    "先にシーンを1つ以上作成してください。")
            return
        default = os.path.join(default_documents_dir(),
                               (self.project.title or "novelgame") + "-web.zip")
        zip_path, _ = QFileDialog.getSaveFileName(
            self, "Cloudflare用ZIPを書き出し", default, "ZIP (*.zip)")
        if not zip_path:
            return
        if not zip_path.lower().endswith(".zip"):
            zip_path += ".zip"
        try:
            result = export_to_zip(self.project.data, zip_path)
        except Exception as e:
            QMessageBox.critical(self, "書き出し失敗", f"書き出せませんでした:\n{e}")
            return
        msg = (f"Cloudflare Pages 用の ZIP を書き出しました。\n\n"
               f"ファイル: {zip_path}\n"
               f"アセット: {result['assets']} 個\n\n"
               "▼ デプロイ手順（Cloudflare Pages）\n"
               "1. Cloudflare ダッシュボード → Workers & Pages → Create → Pages\n"
               "2. 「Upload assets（直接アップロード）」を選択\n"
               "3. この ZIP（または展開した中身）をドラッグ＆ドロップ\n"
               "4. Deploy を押すと公開URLが発行されます\n\n"
               "※ ZIP のルートに index.html があるため、そのまま公開できます。")
        if result["missing"]:
            msg += f"\n\n⚠ 見つからないファイル {len(result['missing'])} 件は除外しました。"
        box = QMessageBox(QMessageBox.Information, "書き出し完了", msg, parent=self)
        open_btn = box.addButton("保存先を開く", QMessageBox.ActionRole)
        box.addButton("閉じる", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            self._open_folder(os.path.dirname(os.path.abspath(zip_path)))
        self.statusBar().showMessage(f"Cloudflare用ZIP書き出し完了: {zip_path}", 5000)

    def _open_folder(self, path: str):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _exit_player(self):
        self.stack.setCurrentWidget(self.editor_page)
        if self.player:
            self.stack.removeWidget(self.player)
            self.player.deleteLater()
            self.player = None
        # プレイ中に状態が変わることは無いが、念のためUIを最新化
        self.scene_editor.reload()
        self.settings_editor.reload()

    # ------------------------------------------------------------------
    # プロジェクト操作
    # ------------------------------------------------------------------
    def _reload_all_editors(self):
        # 既存タブを作り直す（プロジェクト差し替え時）
        self.tabs.clear()
        self._build_tabs()

    def new_project(self):
        if not self._confirm_discard():
            return
        from .model import default_project
        self.project = Project(default_project())
        self._reload_all_editors()
        self._update_title()

    def open_project(self):
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "プロジェクトを開く", "", PROJECT_FILTER)
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                proj = Project.from_json(f.read())
            proj.path = path
            self.project = proj
            self._reload_all_editors()
            self._update_title()
        except Exception as e:
            QMessageBox.critical(self, "読み込み失敗", f"ファイルを開けませんでした:\n{e}")

    def save_project(self) -> bool:
        if not self.project.path:
            return self.save_project_as()
        return self._write(self.project.path)

    def save_project_as(self) -> bool:
        fname = (self.project.title or "novelgame") + ".nvproj"
        default = os.path.join(default_documents_dir(), fname)
        path, _ = QFileDialog.getSaveFileName(self, "名前を付けて保存", default, PROJECT_FILTER)
        if not path:
            return False
        if not os.path.splitext(path)[1]:
            path += ".nvproj"
        self.project.path = path
        return self._write(path)

    def _write(self, path: str) -> bool:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.project.to_json())
            self.project.dirty = False
            self._update_title()
            self.statusBar().showMessage(f"保存しました: {path}", 4000)
            return True
        except Exception as e:
            QMessageBox.critical(self, "保存失敗", f"保存できませんでした:\n{e}")
            return False

    def _confirm_discard(self) -> bool:
        if not self.project.dirty:
            return True
        r = QMessageBox.question(
            self, "未保存の変更",
            "保存していない変更があります。保存しますか？",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Cancel:
            return False
        if r == QMessageBox.Save:
            return self.save_project()
        return True

    def _update_title(self):
        name = os.path.basename(self.project.path) if self.project.path else "（未保存）"
        star = "*" if self.project.dirty else ""
        self.setWindowTitle(f"{APP_NAME} — {self.project.title} [{name}]{star}")

    def closeEvent(self, event):
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()
