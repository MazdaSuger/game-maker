# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — ノベルメーカーのデスクトップ実行ファイルを生成する.

Windows: dist/NovelMaker/NovelMaker.exe （ワンフォルダ）
macOS:   dist/NovelMaker.app （universal2 = Intel + Apple Silicon 両対応）
Linux:   dist/NovelMaker/NovelMaker

使い方:
    pyinstaller packaging/novelmaker.spec

web/（ブラウザ書き出し用ランタイム）を同梱するため、書き出し機能は
パッケージ後も動作する（exporter.py が sys._MEIPASS を参照）。
"""

import os
import sys

block_cipher = None

# spec ファイルからプロジェクトルートを解決
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(SPEC)), ".."))

# 同梱データ: Webランタイム一式
datas = [
    (os.path.join(ROOT, "web"), "web"),
]

# macOS は universal2（Intel/Apple Silicon 両対応）でビルド
target_arch = "universal2" if sys.platform == "darwin" else None

# アイコン（存在すれば使用）
def _icon():
    if sys.platform == "darwin":
        p = os.path.join(ROOT, "packaging", "icon.icns")
    elif sys.platform.startswith("win"):
        p = os.path.join(ROOT, "packaging", "icon.ico")
    else:
        p = None
    return p if (p and os.path.exists(p)) else None


a = Analysis(
    [os.path.join(ROOT, "run.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "PySide6.QtMultimedia",  # BGM 再生に使用（動的import対策）
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "tkinter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NovelMaker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUI アプリ（コンソール非表示）
    disable_windowed_traceback=False,
    target_arch=target_arch,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon(),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="NovelMaker",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="NovelMaker.app",
        icon=_icon(),
        bundle_identifier="com.novelmaker.app",
        info_plist={
            "CFBundleName": "NovelMaker",
            "CFBundleDisplayName": "ノベルメーカー",
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.developer-tools",
        },
    )
