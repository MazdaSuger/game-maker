"""アプリケーションエントリポイント."""

from __future__ import annotations

import sys
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox

from . import APP_NAME
from .model import Project
from .mainwindow import MainWindow

# アプリ全体のダークテーマ
APP_QSS = """
QWidget { font-size: 13px; color: #e6e9f2; background: #1e2233; }
QMainWindow, QDialog { background: #1a1e2c; }
QTabWidget::pane { border: 1px solid #313a55; }
QTabBar::tab {
    background: #232838; padding: 8px 14px; border: 1px solid #313a55;
    border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px;
}
QTabBar::tab:selected { background: #313a5e; }
QListWidget, QPlainTextEdit, QLineEdit, QComboBox, QSpinBox {
    background: #141826; border: 1px solid #313a55; border-radius: 6px;
    padding: 4px; selection-background-color: #3a6df0;
}
QListWidget::item { padding: 5px; }
QListWidget::item:selected { background: #3a6df0; }
QListWidget::item:alternate { background: #181c2c; }
QPushButton {
    background: #2a3050; border: 1px solid #44507a; border-radius: 6px;
    padding: 6px 12px;
}
QPushButton:hover { background: #3a4470; }
QPushButton:pressed { background: #283058; }
QPushButton[primary="true"] { background:#3a6df0; border-color:#5a8dff; font-weight:bold; }
QToolButton { background:#2a3050; border:1px solid #44507a; border-radius:6px; padding:6px 12px; }
QToolButton:hover { background:#3a4470; }
QGroupBox {
    border: 1px solid #3a4566; border-radius: 8px; margin-top: 10px; padding-top: 8px;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color:#aab4d8; }
QToolBar { background: #161a28; border-bottom: 1px solid #313a55; spacing: 4px; padding: 4px; }
QMenuBar { background: #161a28; }
QMenuBar::item:selected { background: #313a5e; }
QMenu { background: #232838; border: 1px solid #3a4566; }
QMenu::item:selected { background: #3a6df0; }
QScrollBar:vertical { background: #141826; width: 12px; }
QScrollBar::handle:vertical { background: #3a4566; border-radius: 6px; min-height: 24px; }
QLabel { background: transparent; }
"""


def _install_excepthook():
    """スロット内の未処理例外でアプリが落ちないようにする。

    例外をダイアログで表示し、操作を継続できるようにする。
    """
    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        sys.stderr.write(text)
        try:
            box = QMessageBox(QMessageBox.Critical, "エラー",
                              "予期しないエラーが発生しました。\n"
                              "操作は継続できますが、念のため保存をおすすめします。")
            box.setDetailedText(text)
            box.exec()
        except Exception:
            pass
    sys.excepthook = hook


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(APP_QSS)
    _install_excepthook()

    from .model import default_project
    window = MainWindow(Project(default_project()))
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
