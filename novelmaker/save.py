"""セーブ/ロード管理 — マニュアル10スロット.

プレイヤーの実行状態(:class:`GameState`)をスロットへ保存/復元する。
セーブデータは JSON ファイル1つにまとめて永続化する。
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional

from .runtime import GameState

NUM_SLOTS = 10


def default_save_dir() -> str:
    """セーブデータ既定ディレクトリ (~/.novelmaker)。"""
    d = os.path.join(os.path.expanduser("~"), ".novelmaker")
    os.makedirs(d, exist_ok=True)
    return d


class Slot:
    """1スロット分のセーブデータ。"""

    def __init__(self, state: GameState, label: str, saved_at: str):
        self.state = state
        self.label = label        # 一覧表示用のプレビュー文
        self.saved_at = saved_at

    def to_dict(self) -> dict:
        return {"state": self.state.to_dict(),
                "label": self.label, "saved_at": self.saved_at}

    @classmethod
    def from_dict(cls, d: dict) -> "Slot":
        return cls(GameState.from_dict(d.get("state", {})),
                   d.get("label", ""), d.get("saved_at", ""))


class SaveManager:
    """10スロットを管理し、JSONファイルへ永続化する。"""

    def __init__(self, save_path: str):
        self.save_path = save_path
        self.slots: list[Optional[Slot]] = [None] * NUM_SLOTS
        self.load_file()

    # --- 永続化 -------------------------------------------------------
    def load_file(self):
        self.slots = [None] * NUM_SLOTS
        if not os.path.exists(self.save_path):
            return
        try:
            with open(self.save_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for i, sd in enumerate(data.get("slots", [])):
                if i >= NUM_SLOTS:
                    break
                self.slots[i] = Slot.from_dict(sd) if sd else None
        except (OSError, ValueError):
            # 壊れている場合は空として扱う
            self.slots = [None] * NUM_SLOTS

    def flush(self):
        os.makedirs(os.path.dirname(self.save_path) or ".", exist_ok=True)
        data = {"slots": [s.to_dict() if s else None for s in self.slots]}
        with open(self.save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # --- スロット操作 -------------------------------------------------
    def save(self, index: int, state: GameState, label: str):
        if not (0 <= index < NUM_SLOTS):
            return
        # GameState のコピーを保存（以後の進行で書き換わらないように）
        snap = GameState.from_dict(state.to_dict())
        self.slots[index] = Slot(snap, label,
                                 time.strftime("%Y-%m-%d %H:%M:%S"))
        self.flush()

    def load(self, index: int) -> Optional[GameState]:
        if not (0 <= index < NUM_SLOTS):
            return None
        slot = self.slots[index]
        if slot is None:
            return None
        # コピーを返す
        return GameState.from_dict(slot.state.to_dict())

    def clear(self, index: int):
        if 0 <= index < NUM_SLOTS:
            self.slots[index] = None
            self.flush()


class SystemStore:
    """ゲーム全体で共有・永続化されるシステムデータ。

    ``data = {"vars": {名前: 値}, "endings": {endingId: 回数}}``
    プレイをまたいで保持される（10スロットのセーブとは独立）。
    """

    def __init__(self, path: str):
        self.path = path
        self.data = {"vars": {}, "endings": {}}
        self.load()

    def load(self):
        if not os.path.exists(self.path):
            self.data = {"vars": {}, "endings": {}}
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.data = {"vars": dict(d.get("vars", {})),
                         "endings": dict(d.get("endings", {}))}
        except (OSError, ValueError):
            self.data = {"vars": {}, "endings": {}}

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def reset(self):
        self.data = {"vars": {}, "endings": {}}
        self.save()
