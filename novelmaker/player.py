"""プレイヤーウィジェット — 作成したノベルゲームを実行/テストプレイする.

背景・立ち絵・暗転・メッセージ・選択肢・名前入力・ゲージ表示・
アイテム表示・エンディング・BGM・10スロットセーブを扱う。
:class:`Runtime` を駆動し、返るイベントに応じて画面を更新する。
"""

from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QLineEdit,
    QFrame, QGridLayout, QScrollArea, QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer, QRect, Signal
from PySide6.QtGui import QPainter, QColor, QPixmap, QFont, QFontMetrics

from .model import Project, merged_layout, merged_theme, SPRITE_POS_KEY
from .runtime import Runtime, GameState, evaluate_condition
from .save import SaveManager


BGM_VOLUME = 0.7  # BGM の基準音量


def _qss_url(path: str) -> str:
    """QSS 用にパスを正規化（バックスラッシュ→スラッシュ）。"""
    return path.replace("\\", "/")

# BGM（任意・環境に無ければ無音で続行）
try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PySide6.QtCore import QUrl
    _HAS_AUDIO = True
except Exception:  # pragma: no cover
    _HAS_AUDIO = False


class PlayerWidget(QWidget):
    exited = Signal()

    def __init__(self, project: Project, save_manager: SaveManager,
                 system_store=None, parent=None):
        super().__init__(parent)
        self.project = project
        self.saves = save_manager
        self.runtime = Runtime(project, system_store)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(800, 500)

        self._pix_cache: dict[str, QPixmap] = {}
        self._current_event = None
        self._full_text = ""
        self._shown_chars = 0
        self._typing = False
        self._title_mode = False
        self._title_bg_id = ""

        # タイプライタ用タイマー
        self._type_timer = QTimer(self)
        self._type_timer.setInterval(22)
        self._type_timer.timeout.connect(self._tick_type)

        # BGM
        self._audio = None
        self._player = None
        self._cur_bgm = None
        # BGM フェード用
        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(40)
        self._fade_timer.timeout.connect(self._fade_step)
        self._fade_target = BGM_VOLUME
        self._fade_step_amt = 0.0
        self._fade_stop_after = False
        # SE（効果音）: 同時発音できるよう小さなプールを用意
        self._se_pool = []
        self._se_idx = 0
        if _HAS_AUDIO:
            try:
                self._audio = QAudioOutput()
                self._player = QMediaPlayer()
                self._player.setAudioOutput(self._audio)
            except Exception:
                self._player = None
            try:
                for _ in range(3):
                    out = QAudioOutput()
                    pl = QMediaPlayer()
                    pl.setAudioOutput(out)
                    self._se_pool.append((pl, out))
            except Exception:
                self._se_pool = []

        self._build_ui()

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------
    def _build_ui(self):
        # ゲージ表示
        self.gauge_panel = QFrame(self)
        self.gauge_panel.setObjectName("gaugePanel")
        self.gauge_panel.setFixedWidth(206)
        self.gauge_layout = QVBoxLayout(self.gauge_panel)
        self.gauge_layout.setContentsMargins(10, 8, 10, 8)
        self.gauge_layout.setSpacing(4)

        # アイテムボタン
        self.items_btn = QPushButton("🎒", self)
        self.items_btn.setObjectName("itemsBtn")
        self.items_btn.setFixedSize(44, 44)
        self.items_btn.setToolTip("所持アイテム")
        self.items_btn.clicked.connect(self._show_items)

        # メニューボタン群
        self.menu_frame = QFrame(self)
        ml = QHBoxLayout(self.menu_frame)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(6)
        for text, slot in [("セーブ", lambda: self._open_save(True)),
                           ("ロード", lambda: self._open_save(False)),
                           ("タイトル", self._to_title),
                           ("終了", self._exit)]:
            b = QPushButton(text)
            b.setObjectName("menuBtn")
            b.clicked.connect(slot)
            ml.addWidget(b)

        # メッセージウィンドウ
        self.msg_frame = QFrame(self)
        self.msg_frame.setObjectName("msgWin")
        mv = QVBoxLayout(self.msg_frame)
        mv.setContentsMargins(24, 14, 24, 16)
        self.name_label = QLabel("", self.msg_frame)
        self.name_label.setObjectName("nameLabel")
        self.text_label = QLabel("", self.msg_frame)
        self.text_label.setObjectName("msgText")
        self.text_label.setWordWrap(True)
        self.text_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        mv.addWidget(self.name_label)
        mv.addWidget(self.text_label, 1)
        self.msg_frame.mousePressEvent = lambda ev: self._on_advance_click()

        # 選択肢コンテナ
        self.choice_frame = QFrame(self)
        self.choice_layout = QVBoxLayout(self.choice_frame)
        self.choice_layout.setAlignment(Qt.AlignCenter)
        self.choice_frame.hide()

        # 名前入力オーバーレイ
        self.name_overlay = self._make_overlay()
        self.name_overlay.box.setObjectName("nameBox")   # 枠（画像カスタム対象）
        nl = self.name_overlay.box_layout
        self.name_prompt = QLabel("", self.name_overlay)
        self.name_prompt.setObjectName("overlayTitle")
        self.name_field = QLineEdit(self.name_overlay)
        self.name_field.setObjectName("nameField")       # 入力欄（画像カスタム対象）
        self.name_field.setMaxLength(16)
        self.name_field.returnPressed.connect(self._submit_name)
        name_ok = QPushButton("決定", self.name_overlay)
        name_ok.setObjectName("primary")
        name_ok.clicked.connect(self._submit_name)
        nl.addWidget(self.name_prompt)
        nl.addWidget(self.name_field)
        nl.addWidget(name_ok)
        self.name_overlay.hide()

        # アイテムオーバーレイ
        self.items_overlay = self._make_overlay(wide=True)
        il = self.items_overlay.box_layout
        title = QLabel("所持アイテム", self.items_overlay)
        title.setObjectName("overlayTitle")
        il.addWidget(title)
        self.items_scroll = QScrollArea(self.items_overlay)
        self.items_scroll.setWidgetResizable(True)
        self.items_scroll.setFrameShape(QFrame.NoFrame)
        self.items_inner = QWidget()
        self.items_inner_layout = QVBoxLayout(self.items_inner)
        self.items_scroll.setWidget(self.items_inner)
        il.addWidget(self.items_scroll, 1)
        close_items = QPushButton("閉じる", self.items_overlay)
        close_items.clicked.connect(self.items_overlay.hide)
        il.addWidget(close_items)
        self.items_overlay.hide()

        # セーブ/ロードオーバーレイ
        self.save_overlay = self._make_overlay(wide=True)
        sl = self.save_overlay.box_layout
        self.save_title = QLabel("セーブ", self.save_overlay)
        self.save_title.setObjectName("overlayTitle")
        sl.addWidget(self.save_title)
        self.slots_scroll = QScrollArea(self.save_overlay)
        self.slots_scroll.setWidgetResizable(True)
        self.slots_scroll.setFrameShape(QFrame.NoFrame)
        self.slots_inner = QWidget()
        self.slots_layout = QVBoxLayout(self.slots_inner)
        self.slots_scroll.setWidget(self.slots_inner)
        sl.addWidget(self.slots_scroll, 1)
        close_save = QPushButton("閉じる", self.save_overlay)
        close_save.clicked.connect(self.save_overlay.hide)
        sl.addWidget(close_save)
        self.save_overlay.hide()

        # エンディングオーバーレイ
        self.ending_overlay = self._make_overlay()
        el = self.ending_overlay.box_layout
        self.ending_badge = QLabel("", self.ending_overlay)
        self.ending_badge.setObjectName("endingBadge")
        self.ending_badge.setAlignment(Qt.AlignCenter)
        self.ending_name = QLabel("", self.ending_overlay)
        self.ending_name.setObjectName("endingName")
        self.ending_name.setAlignment(Qt.AlignCenter)
        self.ending_name.setWordWrap(True)
        self.ending_desc = QLabel("", self.ending_overlay)
        self.ending_desc.setAlignment(Qt.AlignCenter)
        self.ending_desc.setWordWrap(True)
        end_btn = QPushButton("タイトルへ戻る", self.ending_overlay)
        end_btn.setObjectName("primary")
        end_btn.clicked.connect(self._to_title)
        el.addWidget(self.ending_badge)
        el.addWidget(self.ending_name)
        el.addWidget(self.ending_desc)
        el.addWidget(end_btn)
        self.ending_overlay.hide()

        # アイテム入手/使用オーバーレイ
        self.itemget_overlay = self._make_overlay()
        gl = self.itemget_overlay.box_layout
        self.itemget_verb = QLabel("", self.itemget_overlay)
        self.itemget_verb.setObjectName("overlayTitle")
        self.itemget_verb.setAlignment(Qt.AlignCenter)
        self.itemget_icon = QLabel("", self.itemget_overlay)
        self.itemget_icon.setAlignment(Qt.AlignCenter)
        self.itemget_icon.setMinimumHeight(96)
        self.itemget_name = QLabel("", self.itemget_overlay)
        self.itemget_name.setObjectName("itemGetName")
        self.itemget_name.setAlignment(Qt.AlignCenter)
        self.itemget_name.setWordWrap(True)
        self.itemget_desc = QLabel("", self.itemget_overlay)
        self.itemget_desc.setAlignment(Qt.AlignCenter)
        self.itemget_desc.setWordWrap(True)
        ig_btn = QPushButton("OK", self.itemget_overlay)
        ig_btn.setObjectName("primary")
        ig_btn.clicked.connect(self._close_itemget)
        gl.addWidget(self.itemget_verb)
        gl.addWidget(self.itemget_icon)
        gl.addWidget(self.itemget_name)
        gl.addWidget(self.itemget_desc)
        gl.addWidget(ig_btn)
        self.itemget_overlay.hide()

        # タイトル画面オーバーレイ（はじめから / つづきから）
        self.title_overlay = QFrame(self)
        self.title_overlay.setObjectName("titleOverlay")
        # タイトル文字/ロゴ・作者（個別配置できるよう絶対配置のコンテナ）
        self.title_name_box = QWidget(self.title_overlay)
        self.title_name_box.setStyleSheet("background: transparent;")
        nbl = QVBoxLayout(self.title_name_box)
        nbl.setContentsMargins(0, 0, 0, 0)
        nbl.setAlignment(Qt.AlignCenter)
        self.title_logo = QLabel(self.title_name_box)   # ロゴ画像
        self.title_logo.setAlignment(Qt.AlignCenter)
        self.title_logo.hide()
        self.title_name = QLabel("", self.title_name_box)
        self.title_name.setObjectName("titleName")
        self.title_name.setAlignment(Qt.AlignCenter)
        self.title_name.setWordWrap(False)   # 途中で改行しない（1行表示）
        self.title_author = QLabel("", self.title_name_box)
        self.title_author.setObjectName("titleAuthor")
        self.title_author.setAlignment(Qt.AlignCenter)
        nbl.addWidget(self.title_logo)
        nbl.addWidget(self.title_name)
        nbl.addWidget(self.title_author)

        # ボタン群（絶対配置のコンテナ）
        self.title_btn_box = QWidget(self.title_overlay)
        self.title_btn_box.setStyleSheet("background: transparent;")
        bbl = QVBoxLayout(self.title_btn_box)
        bbl.setContentsMargins(0, 0, 0, 0)
        bbl.setAlignment(Qt.AlignCenter)
        self.btn_new = QPushButton("▶ はじめから", self.title_btn_box)
        self.btn_new.setObjectName("titleBtn")
        self.btn_new.clicked.connect(self._begin_new)
        self.btn_continue = QPushButton("⏵ つづきから", self.title_btn_box)
        self.btn_continue.setObjectName("titleBtn")
        self.btn_continue.clicked.connect(self._begin_continue)
        self.btn_title_exit = QPushButton("✕ 終了（エディタへ）", self.title_btn_box)
        self.btn_title_exit.setObjectName("titleBtn")
        self.btn_title_exit.clicked.connect(self._exit)
        for b in (self.btn_new, self.btn_continue, self.btn_title_exit):
            b.setFixedWidth(280)
            bbl.addWidget(b)
        self.title_overlay.hide()

        # エンドロール（縦スクロール）
        self.endroll_overlay = QFrame(self)
        self.endroll_overlay.setObjectName("endrollOverlay")
        self.endroll_label = QLabel("", self.endroll_overlay)
        self.endroll_label.setObjectName("endrollText")
        self.endroll_label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.endroll_label.setWordWrap(True)
        self.endroll_overlay.mousePressEvent = lambda ev: self._skip_endroll()
        self.endroll_overlay.hide()
        self._endroll_speed = 60
        self._endroll_y = 0.0
        self._endroll_timer = QTimer(self)
        self._endroll_timer.setInterval(16)
        self._endroll_timer.timeout.connect(self._endroll_step)

        self._apply_styles()

    def _make_overlay(self, wide=False):
        ov = QFrame(self)
        ov.setObjectName("overlay")
        lay = QVBoxLayout(ov)
        lay.setAlignment(Qt.AlignCenter)
        box = QFrame(ov)
        box.setObjectName("overlayBox")
        box.setMaximumWidth(640 if wide else 460)
        box.setMinimumWidth(420 if wide else 360)
        bl = QVBoxLayout(box)
        bl.setContentsMargins(24, 24, 24, 24)
        bl.setSpacing(12)
        lay.addWidget(box)
        ov.box_layout = bl  # 後から中身を追加するため公開
        ov.box = box
        return ov

    def _apply_styles(self):
        self.setStyleSheet(self._font_qss() + PLAYER_QSS
                           + self._theme_qss() + self._size_qss())

    @staticmethod
    def _num(v, default=100):
        try:
            return float(v)
        except (TypeError, ValueError):
            return float(default)

    def _comp_scale(self, elem: str) -> float:
        L = merged_layout(self.project)
        return self._num(L.get(elem, {}).get("scale", 100), 100) / 100.0

    def _size_qss(self) -> str:
        """文字サイズ（セリフ系）と各コンポーネントのサイズ(%)を反映する。"""
        fs = self._num(self.project.meta.get("fontScale", 100), 100) / 100.0
        ch = self._comp_scale("choices")
        mn = self._comp_scale("menu")
        its = self._comp_scale("items")
        tn = self._comp_scale("titleName")
        tb = self._comp_scale("title")
        r = [
            f'#msgText {{ font-size: {19 * fs:.0f}px; }}',
            f'#nameLabel {{ font-size: {18 * fs:.0f}px; }}',
            f'#choiceBtn {{ font-size: {17 * ch:.0f}px; '
            f'padding: {14 * ch:.0f}px {20 * ch:.0f}px; }}',
            f'#menuBtn {{ font-size: {13 * mn:.0f}px; }}',
            f'#titleName {{ font-size: {44 * tn:.0f}px; }}',
            f'#titleBtn {{ font-size: {18 * tb:.0f}px; '
            f'padding: {14 * tb:.0f}px {24 * tb:.0f}px; }}',
            f'#itemsBtn {{ font-size: {20 * its:.0f}px; '
            f'border-radius: {22 * its:.0f}px; }}',
        ]
        return "\n".join(r)

    def _font_qss(self) -> str:
        """ゲーム内フォント（取り込みフォント or フォント名）を適用する。"""
        fam = self._resolve_font_family()
        if not fam:
            return ""
        return f'* {{ font-family: "{fam}"; }}\n'

    def _resolve_font_family(self) -> str:
        meta = self.project.meta
        path = meta.get("fontPath", "")
        if path and os.path.exists(path):
            try:
                from PySide6.QtGui import QFontDatabase
                fid = QFontDatabase.addApplicationFont(path)
                fams = QFontDatabase.applicationFontFamilies(fid)
                if fams:
                    return fams[0]
            except Exception:
                pass
        return meta.get("font", "") or ""

    def _theme_qss(self) -> str:
        """テーマ（取り込み画像）に応じた追加スタイルを生成する。"""
        t = merged_theme(self.project)
        rules = []

        def img_rule(selector, path, extra=""):
            if path and os.path.exists(path):
                rules.append(
                    f'{selector} {{ border-image: url("{_qss_url(path)}") '
                    f'0 0 0 0 stretch stretch; background: transparent; '
                    f'border: none; {extra} }}')

        img_rule("#msgWin", t.get("msgWindowImage", ""))
        img_rule("#choiceBtn", t.get("choiceButtonImage", ""))
        img_rule("#titleBtn", t.get("titleButtonImage", ""))
        img_rule("#itemsBtn", t.get("itemsButtonImage", ""))
        img_rule("#nameBox", t.get("nameBoxImage", ""))
        img_rule("#nameField", t.get("nameFieldImage", ""), extra="color:#fff;")
        return "\n".join(rules)

    # ------------------------------------------------------------------
    # 開始 / 終了
    # ------------------------------------------------------------------
    def start(self):
        """プレイ開始時はまずタイトル画面を表示する。"""
        self._show_title()
        self.setFocus()

    def _show_title(self):
        self._title_mode = True
        self._hide_all_overlays()
        self.choice_frame.hide()
        # ゲーム用UIを隠す
        self._set_game_chrome(False)
        # タイトル演出（条件を満たす最初の演出で背景/BGM/ロゴ/ボタンを上書き）
        var = self._matched_title_variation()
        logo = (var.get("logo") if var else "") or self.project.meta.get("titleLogoImage", "")
        self._title_bg_override = (var.get("bg") if var else "") or self.project.meta.get("titleBg", "")
        self._title_bgm_override = (var.get("bgm") if var else "") or self.project.meta.get("titleBgm", "")
        self._build_title_extra_buttons(var)
        # タイトル情報（ロゴ画像があれば文字の代わりに表示）
        pix = self._pixmap(logo) if logo else None
        if pix is not None:
            scaled = pix.scaledToWidth(min(pix.width(), int(self.width() * 0.6)),
                                       Qt.SmoothTransformation)
            self.title_logo.setPixmap(scaled)
            self.title_logo.show()
            self.title_name.hide()
        else:
            self.title_logo.hide()
            self.title_name.show()
            self.title_name.setText(self.project.title)
        author = self.project.meta.get("author", "")
        self.title_author.setText(f"作： {author}" if author else "")
        # つづきから：セーブが1つでもあれば有効
        self.saves.load_file()
        has_save = any(s is not None for s in self.saves.slots)
        self.btn_continue.setEnabled(has_save)
        self.btn_continue.setToolTip("" if has_save else "セーブデータがありません")
        # タイトル背景・BGM（演出があれば上書き）
        self._title_bg_id = self._title_bg_override
        self._play_bgm_id(self._title_bgm_override)
        self.title_overlay.show()
        self.title_overlay.raise_()
        self._layout_title()
        self.update()

    def _matched_title_variation(self):
        """条件を満たす最初のタイトル演出を返す（無ければ None）。"""
        variations = self.project.meta.get("titleVariations", []) or []
        if not variations:
            return None
        ctx = GameState()
        ctx.system = self.runtime.system.data
        ctx._all_ending_ids = [e["id"] for e in self.project.endings]
        for v in variations:
            if evaluate_condition(v.get("condition"), ctx):
                return v
        return None

    def _build_title_extra_buttons(self, var):
        """演出で追加するボタンを作り直す。"""
        if not hasattr(self, "_title_extra_buttons"):
            self._title_extra_buttons = []
        for b in self._title_extra_buttons:
            b.setParent(None)
        self._title_extra_buttons = []
        if not var:
            return
        bbl = self.title_btn_box.layout()
        # 「つづきから」の直後（終了ボタンの前）に挿入
        insert_at = bbl.indexOf(self.btn_title_exit)
        for spec in var.get("buttons", []):
            text = spec.get("text", "")
            target = spec.get("targetScene", "")
            btn = QPushButton(text, self.title_btn_box)
            btn.setObjectName("titleBtn")
            btn.setFixedWidth(self.btn_new.width() or 280)
            btn.clicked.connect(lambda checked=False, t=target: self.start_at(t) if t else None)
            bbl.insertWidget(insert_at, btn)
            insert_at += 1
            self._title_extra_buttons.append(btn)

    def _layout_title(self):
        """タイトル文字/ロゴとボタン群を、レイアウト設定に従い配置する。"""
        w, h = self.width(), self.height()
        L = merged_layout(self.project)
        # ボタン幅をサイズ(%)に合わせる
        tw = int(280 * self._comp_scale("title"))
        for b in (self.btn_new, self.btn_continue, self.btn_title_exit):
            b.setFixedWidth(tw)
        for box, key in ((self.title_name_box, "titleName"),
                         (self.title_btn_box, "title")):
            box.adjustSize()
            d = L.get(key, {})
            cx = int(d.get("x", 50) / 100.0 * w)
            cy = int(d.get("y", 50) / 100.0 * h)
            box.move(cx - box.width() // 2, cy - box.height() // 2)

    def start_at(self, scene_id: str):
        """タイトルを飛ばして指定シーンから開始（選択シーンのテスト用）。"""
        self._title_mode = False
        self._hide_all_overlays()
        self.choice_frame.hide()
        self._set_game_chrome(True)
        self._present(self.runtime.start(start_scene=scene_id))
        self.setFocus()

    def _begin_new(self):
        self._title_mode = False
        self.title_overlay.hide()
        self._set_game_chrome(True)
        self._present(self.runtime.start())

    def _begin_continue(self):
        # ロード画面を開く。ロード成功時にタイトルを抜ける。
        self._open_save(False)

    def _to_title(self):
        """エンディング等からタイトル画面へ戻る。"""
        self._hide_all_overlays()
        self._show_title()

    def _set_game_chrome(self, visible: bool):
        """ゲーム中のUI（メッセージ/ゲージ/メニュー等）の表示切替。"""
        for wdg in (self.msg_frame, self.items_btn, self.menu_frame):
            wdg.setVisible(visible)
        if not visible:
            self.gauge_panel.setVisible(False)
            self.choice_frame.hide()

    def _restart(self):
        self._hide_all_overlays()
        self.start()

    def _exit(self):
        self._stop_bgm()
        self.exited.emit()

    def _hide_all_overlays(self):
        for ov in (self.name_overlay, self.items_overlay, self.save_overlay,
                   self.ending_overlay, self.title_overlay, self.itemget_overlay):
            ov.hide()

    # ------------------------------------------------------------------
    # イベント提示
    # ------------------------------------------------------------------
    def _comp_hidden(self, key: str) -> bool:
        """コンポーネントを隠すか。

        優先度: 暗転(UIも消す) > シナリオの表示/消去コマンド > レイアウトの非表示。
        """
        st = self.runtime.state
        if st.blackout and st.blackout_hide_ui:
            return True
        ov = st.comp_override.get(key)
        if ov is not None:
            return ov
        return bool(merged_layout(self.project).get(key, {}).get("hidden", False))

    def _present(self, ev: dict):
        self._current_event = ev
        self._update_stage()
        for se_id in ev.get("sfx", []):   # 効果音を再生
            self._play_se(se_id)
        kind = ev.get("kind")

        self.choice_frame.hide()
        # エンドロール以外ではエンドロールを止める／メニュー類を復帰
        if kind != "endroll":
            self._endroll_timer.stop()
            self.endroll_overlay.hide()
            if not self._title_mode:
                self.items_btn.setVisible(not self._comp_hidden("items"))
                self.menu_frame.setVisible(not self._comp_hidden("menu"))

        if kind == "endroll":
            self._start_endroll(ev.get("text", ""), ev.get("speed", 60),
                                ev.get("noSkip", False))

        elif kind in ("say", "narrate"):
            self.msg_frame.setVisible(not self._comp_hidden("message"))
            if kind == "say":
                self.name_label.setText(ev.get("name", ""))
                self.name_label.setStyleSheet(
                    f'color:{ev.get("color", "#fff")};')
                self.name_label.setVisible(bool(ev.get("name")))
            else:
                self.name_label.setVisible(False)
            self._start_typewriter(ev.get("text", ""))

        elif kind == "choice":
            self.msg_frame.setVisible(bool(ev.get("prompt")) and not self._comp_hidden("message"))
            if ev.get("prompt"):
                self.name_label.setVisible(False)
                self._start_typewriter(ev.get("prompt", ""))
            self._show_choices(ev)

        elif kind == "nameInput":
            self.name_prompt.setText(ev.get("prompt", "名前を入力"))
            self.name_field.setText("")
            self.name_overlay.show()
            self._raise_overlays()
            self.name_field.setFocus()

        elif kind == "itemGet":
            self._show_itemget(ev)

        elif kind == "ending":
            self._show_ending(ev)

        elif kind == "end":
            self.msg_frame.setVisible(not self._comp_hidden("message"))
            self.name_label.setVisible(False)
            self._start_typewriter("― おわり ―")

        self._layout_children()

    # --- タイプライタ ---
    def _start_typewriter(self, text: str):
        self._full_text = text
        self._shown_chars = 0
        self._typing = True
        self.text_label.setText("")
        self._type_timer.start()

    def _tick_type(self):
        self._shown_chars += 1
        if self._shown_chars >= len(self._full_text):
            self.text_label.setText(self._full_text)
            self._typing = False
            self._type_timer.stop()
        else:
            self.text_label.setText(self._full_text[: self._shown_chars])

    def _finish_typewriter(self):
        self._type_timer.stop()
        self._typing = False
        self.text_label.setText(self._full_text)

    # --- エンドロール ---
    def _start_endroll(self, text: str, speed, no_skip: bool = False):
        # ゲーム中UIを隠す
        self.msg_frame.hide()
        self.gauge_panel.hide()
        self.items_btn.hide()
        self.menu_frame.hide()
        self.choice_frame.hide()
        self._endroll_no_skip = bool(no_skip)
        self._endroll_speed = max(10, float(speed or 60))
        w, h = self.width(), self.height()
        self.endroll_overlay.setGeometry(0, 0, w, h)
        self.endroll_label.setText(text or "")
        self.endroll_label.setFixedWidth(int(w * 0.8))
        self.endroll_label.adjustSize()
        # 画面下端から開始
        self._endroll_y = float(h)
        self.endroll_label.move(int(w * 0.1), int(self._endroll_y))
        self.endroll_overlay.show()
        self.endroll_overlay.raise_()
        self._endroll_timer.start()

    def _endroll_step(self):
        dt = self._endroll_timer.interval() / 1000.0
        self._endroll_y -= self._endroll_speed * dt
        self.endroll_label.move(self.endroll_label.x(), int(self._endroll_y))
        # ラベル全体が画面上端より上に抜けたら終了
        if self._endroll_y + self.endroll_label.height() < 0:
            self._finish_endroll()

    def _finish_endroll(self):
        self._endroll_timer.stop()
        self.endroll_overlay.hide()
        self._present(self.runtime.advance())

    def _skip_endroll(self):
        if self.endroll_overlay.isVisible() and not getattr(self, "_endroll_no_skip", False):
            self._finish_endroll()

    # --- クリックで進める ---
    def _on_advance_click(self):
        ev = self._current_event or {}
        kind = ev.get("kind")
        if kind not in ("say", "narrate", "end"):
            return
        if self._typing:
            self._finish_typewriter()
            return
        if kind == "end":
            return  # 終端では進めない
        self._present(self.runtime.advance())

    # --- 選択肢 ---
    def _show_choices(self, ev: dict):
        # 既存のボタンを掃除
        while self.choice_layout.count():
            it = self.choice_layout.takeAt(0)
            if it.widget():
                it.widget().setParent(None)
        for opt in ev.get("options", []):
            b = QPushButton(opt["text"], self.choice_frame)
            b.setObjectName("choiceBtn")
            idx = opt["index"]
            b.clicked.connect(lambda checked=False, i=idx: self._choose(i))
            self.choice_layout.addWidget(b)
        if not ev.get("options"):
            lbl = QLabel("（選択できる項目がありません）", self.choice_frame)
            self.choice_layout.addWidget(lbl)
            skip = QPushButton("続ける", self.choice_frame)
            skip.clicked.connect(lambda: self._present(self.runtime.choose(-1)))
            self.choice_layout.addWidget(skip)
        self.choice_frame.show()
        self.choice_frame.raise_()

    def _choose(self, index: int):
        self.choice_frame.hide()
        self._present(self.runtime.choose(index))

    # --- 名前入力 ---
    def _submit_name(self):
        text = self.name_field.text().strip() or "名無し"
        self.name_overlay.hide()
        self._present(self.runtime.advance(text))

    # --- アイテム入手/使用 ---
    def _show_itemget(self, ev: dict):
        verb = ev.get("verb", "get")
        name = ev.get("name", "")
        self.itemget_verb.setText(
            f'「{name}」を使った' if verb == "use" else f'「{name}」を手に入れた')
        # アイコン（画像優先、なければ絵文字）
        img = ev.get("image", "")
        pix = self._pixmap(img) if img else None
        if pix is not None:
            self.itemget_icon.setPixmap(
                pix.scaled(112, 112, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.itemget_icon.setPixmap(QPixmap())
            self.itemget_icon.setText(ev.get("icon", "📦"))
            self.itemget_icon.setStyleSheet("font-size: 64px;")
        self.itemget_name.setText(name)
        self.itemget_desc.setText(ev.get("desc", ""))
        self.itemget_overlay.show()
        self._raise_overlays()

    def _close_itemget(self):
        self.itemget_overlay.hide()
        self._present(self.runtime.advance())

    # --- エンディング ---
    def _show_ending(self, ev: dict):
        self.msg_frame.hide()
        hidden = ev.get("hidden", False)
        self.ending_badge.setText("🔒 裏エンディング 🔒" if hidden else "★ ENDING ★")
        self.ending_badge.setStyleSheet(
            "color:#ffd56b;" if hidden else "color:#9fe3ff;")
        self.ending_name.setText(ev.get("name", ""))
        self.ending_desc.setText(ev.get("desc", ""))
        self.ending_overlay.show()
        self._raise_overlays()

    # ------------------------------------------------------------------
    # ステージ描画
    # ------------------------------------------------------------------
    def _update_stage(self):
        self._update_gauges()
        self._update_bgm()
        self.update()  # paintEvent

    def _update_gauges(self):
        # クリア
        while self.gauge_layout.count():
            it = self.gauge_layout.takeAt(0)
            if it.widget():
                it.widget().setParent(None)
        st = self.runtime.state
        gs = self._comp_scale("gauges")
        self.gauge_panel.setFixedWidth(int(206 * gs))
        shown = False
        for g in self.project.gauges:
            if not g.get("show", True):
                continue
            shown = True
            val = st.gauges.get(g["id"], g.get("initial", 0))
            row = _GaugeBar(g, val, gs, self.gauge_panel)
            self.gauge_layout.addWidget(row)
        self.gauge_panel.setVisible(shown and not self._comp_hidden("gauges")
                                    and not self._title_mode)

    def _pixmap(self, path: str):
        if not path:
            return None
        if path in self._pix_cache:
            return self._pix_cache[path]
        pix = QPixmap(path) if os.path.exists(path) else None
        if pix is not None and pix.isNull():
            pix = None
        self._pix_cache[path] = pix
        return pix

    def _paint_background(self, p: QPainter, rect: QRect, bg_id: str):
        """指定背景（画像 or 色）を rect 全体に描画する。"""
        bg = self.project.background(bg_id) if bg_id else None
        if bg:
            pix = self._pixmap(bg.get("image", ""))
            if pix is not None:
                scaled = pix.scaled(rect.size(), Qt.KeepAspectRatioByExpanding,
                                    Qt.SmoothTransformation)
                x = (scaled.width() - rect.width()) // 2
                y = (scaled.height() - rect.height()) // 2
                p.drawPixmap(rect, scaled, QRect(x, y, rect.width(), rect.height()))
                return
            p.fillRect(rect, QColor(bg.get("color", "#222244")))
            return
        p.fillRect(rect, QColor("#101018"))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = self.rect()
        st = self.runtime.state

        # タイトル画面：タイトル背景のみ描画
        if self._title_mode:
            self._paint_background(p, rect, self._title_bg_id)
            p.end()
            return

        # 背景
        bg = self.project.background(st.bg_id) if st.bg_id else None
        drew_bg = False
        if bg:
            pix = self._pixmap(bg.get("image", ""))
            if pix is not None:
                scaled = pix.scaled(rect.size(), Qt.KeepAspectRatioByExpanding,
                                    Qt.SmoothTransformation)
                x = (scaled.width() - rect.width()) // 2
                y = (scaled.height() - rect.height()) // 2
                p.drawPixmap(rect, scaled, QRect(x, y, rect.width(), rect.height()))
                drew_bg = True
            if not drew_bg:
                p.fillRect(rect, QColor(bg.get("color", "#222244")))
                drew_bg = True
        if not drew_bg:
            p.fillRect(rect, QColor("#101018"))

        # 立ち絵（暗転中・CG表示中・非表示指定中は描かない／最大3人）
        if (not st.blackout and not st.cg_id and st.sprites
                and not self._comp_hidden("sprite")):
            self._paint_sprites(p, rect, st)

        # CG（画面全体・背景と立ち絵の上）
        if st.cg_id and not st.blackout:
            self._paint_cg(p, rect, st.cg_id)

        # 暗転
        if st.blackout:
            p.fillRect(rect, QColor(0, 0, 0))

        p.end()

    def _paint_cg(self, p: QPainter, rect: QRect, cg_id: str):
        cg = self.project.cg_item(cg_id)
        if not cg:
            return
        # 下地（画像が無い/レターボックス部分）
        p.fillRect(rect, QColor(cg.get("color", "#000000")))
        pix = self._pixmap(cg.get("image", ""))
        if pix is not None:
            # 全体が見えるように contain（アスペクト維持）で中央配置
            scaled = pix.scaled(rect.size(), Qt.KeepAspectRatio,
                                Qt.SmoothTransformation)
            x = (rect.width() - scaled.width()) // 2
            y = (rect.height() - scaled.height()) // 2
            p.drawPixmap(x, y, scaled)
        else:
            # 画像未設定：CG名をプレースホルダ表示
            p.setPen(QColor("#ffffff"))
            font = QFont(); font.setPointSize(20); font.setBold(True)
            p.setFont(font)
            p.drawText(rect, Qt.AlignCenter, f'［CG］{cg.get("name", "")}')

    def _paint_sprites(self, p: QPainter, rect: QRect, st: GameState):
        L = merged_layout(self.project)
        # 左→中央→右 の順で、スロットごとの位置・スケールで描画
        for pos in ("left", "center", "right"):
            entry = st.sprites.get(pos)
            if not entry:
                continue
            slot = L.get(SPRITE_POS_KEY[pos], {})
            avail_h = int(rect.height() * (slot.get("scale", 80) / 100.0))
            cx = int(slot.get("x", 50) / 100.0 * rect.width())
            by = int(slot.get("y", 99) / 100.0 * rect.height())
            self._paint_one_sprite(p, rect, entry, cx, by, avail_h)

    def _paint_one_sprite(self, p: QPainter, rect: QRect, entry: dict,
                          cx: int, by: int, avail_h: int):
        ch = self.project.character(entry.get("charId", ""))
        if not ch or not ch.get("showSprite", True):
            return
        ex = self.project.expression(entry.get("charId", ""), entry.get("exprId", ""))
        if ex is None:
            exprs = ch.get("expressions", [])
            ex = exprs[0] if exprs else None
        pix = self._pixmap(ex.get("image", "")) if ex else None
        if pix is not None:
            scaled = pix.scaledToHeight(avail_h, Qt.SmoothTransformation)
            p.drawPixmap(cx - scaled.width() // 2, by - scaled.height(), scaled)
        else:
            w = int(rect.width() * 0.18)
            x = cx - w // 2
            y = by - avail_h
            color = QColor(ch.get("color", "#888888"))
            color.setAlpha(70)
            p.setBrush(color)
            p.setPen(QColor(ch.get("color", "#888888")))
            p.drawRoundedRect(x, y, w, avail_h, 16, 16)
            p.setPen(QColor("#ffffff"))
            font = QFont(); font.setPointSize(14); font.setBold(True)
            p.setFont(font)
            label = ch.get("name", "")
            if ex:
                label += f'\n（{ex.get("name","")}）'
            p.drawText(QRect(x, y, w, avail_h), Qt.AlignCenter | Qt.TextWordWrap, label)

    def _msg_height(self) -> int:
        return max(150, int(self.height() * 0.26))

    # ------------------------------------------------------------------
    # BGM
    # ------------------------------------------------------------------
    def _update_bgm(self):
        self._play_track(self.runtime.state.bgm_id)

    def _play_bgm_id(self, bgm_id: str):
        self._play_track(bgm_id)

    def _play_track(self, bgm_id: str):
        if not self._player:
            return
        if bgm_id == self._cur_bgm:
            return
        self._cur_bgm = bgm_id
        fade = max(0, int(getattr(self.runtime.state, "bgm_fade", 0) or 0))
        if not bgm_id:
            # 停止（フェードアウト）
            if fade > 0:
                self._start_fade(0.0, fade, stop_after=True)
            else:
                self._fade_timer.stop()
                self._player.stop()
            return
        track = self.project.bgm_track(bgm_id)
        if not track or not track.get("path") or not os.path.exists(track["path"]):
            self._player.stop()
            return
        try:
            self._fade_timer.stop()
            self._player.setSource(QUrl.fromLocalFile(track["path"]))
            self._player.setLoops(QMediaPlayer.Infinite if track.get("loop", True) else 1)
            if fade > 0:
                self._audio.setVolume(0.0)
                self._player.play()
                self._start_fade(BGM_VOLUME, fade)
            else:
                self._audio.setVolume(BGM_VOLUME)
                self._player.play()
        except Exception:
            pass

    def _start_fade(self, target: float, ms: int, stop_after: bool = False):
        steps = max(1, ms // self._fade_timer.interval())
        cur = self._audio.volume()
        self._fade_target = target
        self._fade_stop_after = stop_after
        self._fade_step_amt = (target - cur) / steps
        self._fade_timer.start()

    def _fade_step(self):
        if not self._audio:
            self._fade_timer.stop()
            return
        cur = self._audio.volume() + self._fade_step_amt
        done = (self._fade_step_amt >= 0 and cur >= self._fade_target) or \
               (self._fade_step_amt < 0 and cur <= self._fade_target)
        if done:
            cur = self._fade_target
        self._audio.setVolume(max(0.0, min(1.0, cur)))
        if done:
            self._fade_timer.stop()
            if self._fade_stop_after and self._player:
                self._player.stop()

    def _stop_bgm(self):
        if self._player:
            try:
                self._player.stop()
            except Exception:
                pass
        self._cur_bgm = None

    def _play_se(self, se_id: str):
        """効果音を一度だけ再生する（プールを巡回）。"""
        if not self._se_pool:
            return
        track = self.project.se_track(se_id)
        if not track or not track.get("path") or not os.path.exists(track["path"]):
            return
        pl, out = self._se_pool[self._se_idx]
        self._se_idx = (self._se_idx + 1) % len(self._se_pool)
        try:
            pl.setSource(QUrl.fromLocalFile(track["path"]))
            pl.setLoops(1)
            out.setVolume(0.9)
            pl.play()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # アイテム表示
    # ------------------------------------------------------------------
    def _show_items(self):
        while self.items_inner_layout.count():
            it = self.items_inner_layout.takeAt(0)
            if it.widget():
                it.widget().setParent(None)
        st = self.runtime.state
        if not st.items:
            self.items_inner_layout.addWidget(QLabel("（所持アイテムはありません）"))
        for iid in st.items:
            item = self.project.item(iid)
            if not item:
                continue
            row = QFrame()
            row.setObjectName("itemRow")
            rl = QHBoxLayout(row)
            icon = QLabel()
            pix = self._pixmap(item.get("image", "")) if item.get("image") else None
            if pix is not None:
                icon.setPixmap(pix.scaled(48, 48, Qt.KeepAspectRatio,
                                          Qt.SmoothTransformation))
            else:
                icon.setText(item.get("icon", "📦"))
                icon.setStyleSheet("font-size:28px;")
            icon.setFixedWidth(52)
            icon.setAlignment(Qt.AlignCenter)
            desc_html = (item.get("desc", "") or "").replace("\n", "<br>")
            name = QLabel(f'<b>{item["name"]}</b><br><span style="color:#bbb">'
                          f'{desc_html}</span>')
            name.setWordWrap(True)
            rl.addWidget(icon)
            rl.addWidget(name, 1)
            self.items_inner_layout.addWidget(row)
        self.items_inner_layout.addStretch()
        self.items_overlay.show()
        self._raise_overlays()

    # ------------------------------------------------------------------
    # セーブ / ロード
    # ------------------------------------------------------------------
    def _open_save(self, saving: bool):
        self._save_mode = saving
        self.save_title.setText("セーブ（スロットを選択）" if saving else "ロード（スロットを選択）")
        self.saves.load_file()
        while self.slots_layout.count():
            it = self.slots_layout.takeAt(0)
            if it.widget():
                it.widget().setParent(None)
        for i in range(len(self.saves.slots)):
            self.slots_layout.addWidget(self._make_slot_row(i, saving))
        self.slots_layout.addStretch()
        self.save_overlay.show()
        self._raise_overlays()

    def _make_slot_row(self, i: int, saving: bool) -> QFrame:
        slot = self.saves.slots[i]
        row = QFrame()
        row.setObjectName("slotRow")
        rl = QHBoxLayout(row)
        if slot:
            info = QLabel(f'<b>スロット {i+1}</b>　{slot.saved_at}<br>'
                         f'<span style="color:#bbb">{slot.label}</span>')
        else:
            info = QLabel(f'<b>スロット {i+1}</b>　<span style="color:#888">（空き）</span>')
        info.setWordWrap(True)
        rl.addWidget(info, 1)

        if saving:
            b = QPushButton("ここに保存")
            b.clicked.connect(lambda checked=False, idx=i: self._do_save(idx))
            rl.addWidget(b)
        else:
            b = QPushButton("ロード")
            b.setEnabled(slot is not None)
            b.clicked.connect(lambda checked=False, idx=i: self._do_load(idx))
            rl.addWidget(b)
        if slot:
            d = QPushButton("削除")
            d.clicked.connect(lambda checked=False, idx=i: self._do_clear(idx))
            rl.addWidget(d)
        return row

    def _slot_label(self) -> str:
        scene = self.project.scene(self.runtime.state.scene_id)
        sname = scene["name"] if scene else ""
        return f'{self.project.title}／{sname}'

    def _do_save(self, idx: int):
        self.saves.save(idx, self.runtime.state, self._slot_label())
        self._open_save(True)  # リフレッシュ

    def _do_load(self, idx: int):
        state = self.saves.load(idx)
        if state is None:
            return
        self.save_overlay.hide()
        self._hide_all_overlays()
        # タイトル画面からの「つづきから」もここを通る
        self._title_mode = False
        self._set_game_chrome(True)
        ev = self.runtime.load_state(state)
        self._present(ev)

    def _do_clear(self, idx: int):
        self.saves.clear(idx)
        self._open_save(self._save_mode)

    # ------------------------------------------------------------------
    # レイアウト
    # ------------------------------------------------------------------
    def resizeEvent(self, event):
        self._layout_children()
        super().resizeEvent(event)

    def _layout_children(self):
        w, h = self.width(), self.height()
        L = merged_layout(self.project)

        def px(v, total):
            return int(v / 100.0 * total)

        # メッセージウィンドウ（左上座標＋サイズ）
        m = L["message"]
        self.msg_frame.setGeometry(px(m["x"], w), px(m["y"], h),
                                   px(m["w"], w), px(m["h"], h))
        # ゲージパネル（左上座標）
        g = L["gauges"]
        self.gauge_panel.adjustSize()
        self.gauge_panel.move(px(g["x"], w), px(g["y"], h))
        # アイテムボタン（左上座標・サイズ）
        it = L["items"]
        isz = int(44 * self._comp_scale("items"))
        self.items_btn.setFixedSize(isz, isz)
        self.items_btn.move(px(it["x"], w), px(it["y"], h))
        # メニュー（左上座標）
        mn = L["menu"]
        self.menu_frame.adjustSize()
        self.menu_frame.move(px(mn["x"], w), px(mn["y"], h))
        # 選択肢（中央アンカー）
        c = L["choices"]
        cw, chh = int(w * 0.6), int(h * 0.5)
        self.choice_frame.setGeometry(px(c["x"], w) - cw // 2,
                                      px(c["y"], h) - chh // 2, cw, chh)
        # オーバーレイ：全面
        for ov in (self.name_overlay, self.items_overlay, self.save_overlay,
                   self.ending_overlay, self.title_overlay, self.endroll_overlay,
                   self.itemget_overlay):
            ov.setGeometry(0, 0, w, h)
        self._layout_title()

    def _raise_overlays(self):
        # タイトルを先に上げ、モーダル（ロード等）を最後に上げて最前面にする
        for ov in (self.title_overlay, self.name_overlay, self.items_overlay,
                   self.save_overlay, self.ending_overlay, self.itemget_overlay):
            if ov.isVisible():
                ov.raise_()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            if self.endroll_overlay.isVisible():
                self._skip_endroll()
            elif self.itemget_overlay.isVisible():
                self._close_itemget()
            elif not self._title_mode and not any(ov.isVisible() for ov in
                       (self.name_overlay, self.items_overlay, self.save_overlay,
                        self.ending_overlay, self.title_overlay, self.itemget_overlay)):
                self._on_advance_click()
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        # ステージ（メッセージ枠以外）クリックでも進められる。
        # セリフ枠を非表示にした場合の進行手段にもなる。
        if self.endroll_overlay.isVisible():
            self._skip_endroll()
        elif not self._title_mode and not any(ov.isVisible() for ov in
                (self.name_overlay, self.items_overlay, self.save_overlay,
                 self.ending_overlay, self.title_overlay, self.itemget_overlay)):
            self._on_advance_click()
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# ゲージバー
# ---------------------------------------------------------------------------
class _GaugeBar(QWidget):
    def __init__(self, gauge: dict, value, scale=1.0, parent=None):
        super().__init__(parent)
        self.gauge = gauge
        self.value = float(value)
        self.scale = scale
        self.setFixedSize(int(180 * scale), int(30 * scale))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        g = self.gauge
        s = self.scale
        lo = float(g.get("min", 0))
        hi = float(g.get("max", 100))
        ratio = 0 if hi <= lo else max(0.0, min(1.0, (self.value - lo) / (hi - lo)))

        bar_y = int(16 * s)
        bar_h = int(12 * s)
        bar_rect = QRect(0, bar_y, self.width(), bar_h)
        p.setBrush(QColor(0, 0, 0, 120))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(bar_rect, int(6 * s), int(6 * s))
        fill = QRect(0, bar_y, int(self.width() * ratio), bar_h)
        p.setBrush(QColor(g.get("color", "#4cc2ff")))
        p.drawRoundedRect(fill, int(6 * s), int(6 * s))

        p.setPen(QColor("#ffffff"))
        font = QFont()
        font.setPointSize(max(7, int(9 * s)))
        font.setBold(True)
        p.setFont(font)
        val = int(self.value) if self.value == int(self.value) else round(self.value, 1)
        p.drawText(QRect(0, 0, self.width(), int(14 * s)), Qt.AlignLeft,
                   f'{g.get("name","")}: {val}')
        p.end()


# ---------------------------------------------------------------------------
# スタイル
# ---------------------------------------------------------------------------
PLAYER_QSS = """
PlayerWidget { background:#000; }
#msgWin {
    background: rgba(15, 18, 30, 0.86);
    border: 2px solid rgba(120,150,220,0.5);
    border-radius: 14px;
}
#nameLabel { font-size: 18px; font-weight: bold; }
#msgText { font-size: 19px; color: #f2f4ff; line-height: 150%; }
#gaugePanel {
    background: rgba(10,12,20,0.62);
    border-radius: 10px;
}
#itemsBtn {
    font-size: 20px;
    background: rgba(20,24,40,0.8);
    border: 1px solid rgba(150,170,230,0.5);
    border-radius: 22px;
}
#itemsBtn:hover { background: rgba(40,48,80,0.9); }
#menuBtn {
    background: rgba(20,24,40,0.8);
    border: 1px solid rgba(150,170,230,0.4);
    border-radius: 8px;
    padding: 6px 10px;
}
#menuBtn:hover { background: rgba(50,60,100,0.9); }
#choiceBtn {
    background: rgba(30,36,60,0.92);
    border: 2px solid rgba(150,170,230,0.6);
    border-radius: 10px;
    padding: 14px 20px;
    font-size: 17px;
    margin: 6px 0;
    color: #eef;
}
#choiceBtn:hover { background: rgba(70,90,160,0.95); border-color:#9fe3ff; }
#overlay { background: rgba(0,0,0,0.72); }
#endrollOverlay { background: #05060a; }
#endrollText { color: #f2f4ff; font-size: 22px; }
#titleOverlay { background: rgba(0,0,0,0.55); }
#titleName {
    font-size: 44px; font-weight: bold; color: #ffffff;
    padding: 8px 28px;
}
#titleAuthor { font-size: 16px; color: #cdd6f4; }
#titleBtn {
    background: transparent; border: none;
    padding: 8px 24px; font-size: 18px; font-weight: bold; color: #eef;
    margin: 4px 0;
}
#titleBtn:hover { color: #9fe3ff; }
#titleBtn:disabled { color: #888; }
#titleName { background: transparent; }
#overlayBox {
    background: #1a1e2e;
    border: 2px solid rgba(150,170,230,0.5);
    border-radius: 16px;
}
#overlayTitle { font-size: 20px; font-weight: bold; color:#dfe6ff; }
#endingBadge { font-size: 22px; font-weight: bold; letter-spacing: 3px; }
#endingName { font-size: 28px; font-weight: bold; color:#fff; }
#itemGetName { font-size: 22px; font-weight: bold; color:#ffe9a8; }
#slotRow, #itemRow {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(150,170,230,0.25);
    border-radius: 10px;
    margin: 3px 0;
}
QPushButton {
    background:#2a3050; color:#e8ecff; border:1px solid #44507a;
    border-radius:7px; padding:7px 12px;
}
QPushButton:hover { background:#3a4470; }
QPushButton#primary { background:#3a6df0; border-color:#5a8dff; font-weight:bold; }
QPushButton#primary:hover { background:#4a7dff; }
QLineEdit {
    background:#0e1120; border:1px solid #44507a; border-radius:6px;
    padding:8px; color:#fff; font-size:16px;
}
"""
