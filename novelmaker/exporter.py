"""ブラウザ書き出し — プロジェクトを単体HTML/JSのWebゲームに変換する.

出力フォルダに、Webランタイム(engine.js/player.js/style.css/index.html)と
プロジェクトデータ(game.js)、参照アセット(assets/)をまとめる。
``index.html`` をブラウザで開けばそのまま遊べる。
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import sys


def web_dir() -> str:
    """Webランタイム(web/)の場所を解決する。

    PyInstaller でパッケージ化された場合は _MEIPASS を参照する。
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        cand = os.path.join(base, "web")
        if os.path.isdir(cand):
            return cand
    # 開発時：このファイルの1つ上 / web
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), "web")


# プロジェクト内で「ファイルパス」を保持しているフィールド
def _iter_asset_fields(data: dict):
    """(holder_dict, key) を列挙する。値はファイルパス（書き換え対象）。"""
    for bg in data.get("backgrounds", []):
        yield bg, "image"
    for ch in data.get("characters", []):
        for ex in ch.get("expressions", []):
            yield ex, "image"
    for tr in data.get("bgm", []):
        yield tr, "path"


def collect_assets(data: dict):
    """書き換え対象フィールドのうち、実在するファイルのみ集める。"""
    result = []
    for holder, key in _iter_asset_fields(data):
        path = holder.get(key, "")
        if path and os.path.isfile(path):
            result.append((holder, key, path))
    return result


def export_to_html(project_data: dict, out_dir: str) -> dict:
    """project_data を out_dir にWebゲームとして書き出す。

    返り値: {"files": [...], "assets": n, "missing": [...]}
    """
    src = web_dir()
    runtime_files = ["engine.js", "player.js", "style.css", "index.html"]
    for f in runtime_files:
        if not os.path.isfile(os.path.join(src, f)):
            raise FileNotFoundError(f"Webランタイムが見つかりません: {os.path.join(src, f)}")

    os.makedirs(out_dir, exist_ok=True)
    assets_dir = os.path.join(out_dir, "assets")

    # データはコピーを書き換える（元プロジェクトは変更しない）
    data = copy.deepcopy(project_data)

    # アセットをコピーし、パスを相対(assets/...)へ書き換え
    copied = 0
    missing = []
    used_names = {}
    # 実在チェックしつつ全フィールド走査（欠落も記録）
    for holder, key in _iter_asset_fields(data):
        path = holder.get(key, "")
        if not path:
            continue
        if not os.path.isfile(path):
            missing.append(path)
            holder[key] = ""  # 壊れた参照は空に
            continue
        os.makedirs(assets_dir, exist_ok=True)
        rel = _unique_asset_name(path, used_names)
        shutil.copy2(path, os.path.join(assets_dir, os.path.basename(rel)))
        holder[key] = rel
        copied += 1

    # game.js（データ）を書き出し
    game_js = "window.GAME_DATA = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n"
    with open(os.path.join(out_dir, "game.js"), "w", encoding="utf-8") as f:
        f.write(game_js)

    # ランタイムをコピー
    for f in runtime_files:
        shutil.copy2(os.path.join(src, f), os.path.join(out_dir, f))

    return {
        "files": runtime_files + ["game.js"],
        "assets": copied,
        "missing": missing,
        "out_dir": out_dir,
    }


def _unique_asset_name(path: str, used: dict) -> str:
    """assets/ 内で名前が衝突しないよう一意なファイル名を返す。"""
    base = os.path.basename(path)
    name, ext = os.path.splitext(base)
    candidate = base
    i = 1
    while candidate in used and used[candidate] != path:
        candidate = f"{name}_{i}{ext}"
        i += 1
    used[candidate] = path
    return "assets/" + candidate
