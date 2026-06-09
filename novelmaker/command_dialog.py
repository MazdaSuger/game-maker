"""コマンド編集ダイアログ — 1つのコマンド(コンポーネント)を編集する.

コマンドのタイプに応じてフォームを動的に組み立てる。
編集はコピーに対して行い、OK 時に結果 dict を返す。
"""

from __future__ import annotations

import copy

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox, QLineEdit,
    QPlainTextEdit, QCheckBox, QPushButton, QLabel, QGroupBox, QWidget,
    QScrollArea, QFrame, QSpinBox,
)
from PySide6.QtCore import Qt

from .model import (
    Project, COMMAND_LABELS, COMMAND_ICONS, VAR_OPS, GAUGE_OPS,
    empty_condition, uid, NO_SPRITE, SAY_POSITIONS, COMP_TARGETS, all_labels,
)
from .condition_widget import ConditionWidget


def _combo(items, current, none_label=None):
    """(value,label) のリストからコンボボックスを作る。"""
    cb = QComboBox()
    if none_label is not None:
        cb.addItem(none_label, "")
    for value, label in items:
        cb.addItem(label, value)
    set_combo_value(cb, current)
    return cb


def set_combo_value(cb: QComboBox, value):
    for i in range(cb.count()):
        if cb.itemData(i) == value:
            cb.setCurrentIndex(i)
            return
    cb.setCurrentIndex(0)


class CommandDialog(QDialog):
    def __init__(self, command: dict, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.cmd = copy.deepcopy(command)
        self.result_cmd = None

        ctype = self.cmd["type"]
        self.setWindowTitle(
            f"{COMMAND_ICONS.get(ctype,'')} {COMMAND_LABELS.get(ctype, ctype)} の編集")
        self.setMinimumWidth(480)

        outer = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        self.form_host = QVBoxLayout(body)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        self._build_form(ctype)

        # ボタン
        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("キャンセル")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("OK")
        ok.setDefault(True)
        ok.setProperty("primary", True)
        ok.clicked.connect(self._accept)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        outer.addLayout(btns)

    # ------------------------------------------------------------------
    # フォーム構築
    # ------------------------------------------------------------------
    def _build_form(self, ctype: str):
        method = getattr(self, f"_form_{ctype}", None)
        if method:
            method()
        else:
            self.form_host.addWidget(QLabel("（このコマンドに編集項目はありません）"))

    def _add_form(self, layout: QFormLayout):
        w = QWidget()
        w.setLayout(layout)
        self.form_host.addWidget(w)

    # --- 各タイプ -----------------------------------------------------
    def _form_say(self):
        f = QFormLayout()
        self.char_cb = _combo([(c["id"], c["name"]) for c in self.project.characters],
                              self.cmd.get("charId", ""), none_label="（地の文）")
        self.char_cb.currentIndexChanged.connect(self._reload_expr)
        self.expr_cb = QComboBox()
        self._reload_expr()
        self.text_edit = QPlainTextEdit(self.cmd.get("text", ""))
        self.text_edit.setPlaceholderText("セリフ本文。{変数名} で変数を埋め込めます。")
        self.text_edit.setMinimumHeight(100)
        self.pos_cb = _combo(list(SAY_POSITIONS), self.cmd.get("pos", "center"))
        self.hide_sprite_cb = QCheckBox("このセリフでは立ち絵を表示しない（名前だけ）")
        self.hide_sprite_cb.setChecked(bool(self.cmd.get("hideSprite", False)))
        f.addRow("キャラ:", self.char_cb)
        f.addRow("表情:", self.expr_cb)
        f.addRow("立ち絵の位置:", self.pos_cb)
        f.addRow("セリフ:", self.text_edit)
        f.addRow("", self.hide_sprite_cb)
        hint = QLabel("※ 立ち絵は1画面に最大3人（左/中央/右）まで配置できます。\n"
                      "　出ない場合はキャラ側「立ち絵を表示する」がONか確認してください。")
        hint.setStyleSheet("color:#888;")
        f.addRow("", hint)
        self._add_form(f)

    def _reload_expr(self):
        if not hasattr(self, "expr_cb"):
            return
        cid = self.char_cb.currentData()
        ch = self.project.character(cid)
        self.expr_cb.clear()
        exprs = ch.get("expressions", []) if ch else []
        for e in exprs:
            self.expr_cb.addItem(e["name"], e["id"])
        want = self.cmd.get("exprId", "")
        ids = [e["id"] for e in exprs]
        if not exprs:
            return
        if want in ids:
            set_combo_value(self.expr_cb, want)
        else:
            self.expr_cb.setCurrentIndex(0)  # 最初の表情

    def _form_charExit(self):
        f = QFormLayout()
        self.char_cb = _combo([(c["id"], c["name"]) for c in self.project.characters],
                              self.cmd.get("charId", ""),
                              none_label="（表示中のキャラを退場）")
        f.addRow("退場するキャラ:", self.char_cb)
        hint = QLabel("※ 指定したキャラが表示中なら立ち絵を消します。\n"
                      "　未指定の場合は、今表示している立ち絵を消します。")
        hint.setStyleSheet("color:#888;")
        f.addRow("", hint)
        self._add_form(f)

    def _form_narrate(self):
        f = QFormLayout()
        self.text_edit = QPlainTextEdit(self.cmd.get("text", ""))
        self.text_edit.setPlaceholderText("地の文（ナレーション）。{変数名} で変数を埋め込めます。")
        self.text_edit.setMinimumHeight(120)
        f.addRow("本文:", self.text_edit)
        self._add_form(f)

    def _form_bg(self):
        f = QFormLayout()
        self.bg_cb = _combo([(b["id"], b["name"]) for b in self.project.backgrounds],
                            self.cmd.get("bgId", ""), none_label="（変更なし）")
        f.addRow("背景:", self.bg_cb)
        self._add_form(f)

    def _form_compVis(self):
        f = QFormLayout()
        self.target_cb = _combo(list(COMP_TARGETS), self.cmd.get("target", "message"))
        self.action_cb = _combo([("hide", "消去する（隠す）"), ("show", "表示する")],
                                self.cmd.get("action", "hide"))
        f.addRow("コンポーネント:", self.target_cb)
        f.addRow("動作:", self.action_cb)
        hint = QLabel("※ シナリオ途中で各コンポーネントを出し入れします。\n"
                      "　レイアウトの「非表示」より、こちらの指定が優先されます。")
        hint.setStyleSheet("color:#888;")
        f.addRow("", hint)
        self._add_form(f)

    def _form_blackout(self):
        f = QFormLayout()
        self.mode_cb = _combo([("on", "暗転する（画面を暗くする）"),
                               ("off", "暗転を解除する")],
                              self.cmd.get("mode", "on"))
        self.hideui_cb = QCheckBox("画面上のコンポーネントも消す（セリフ枠・ゲージ等）")
        self.hideui_cb.setChecked(bool(self.cmd.get("hideUi", False)))
        f.addRow("動作:", self.mode_cb)
        f.addRow("", self.hideui_cb)
        hint = QLabel("※「コンポーネントも消す」をONにすると、暗転中は\n"
                      "　セリフ枠・ゲージ・ボタン・立ち絵もすべて消えます。")
        hint.setStyleSheet("color:#888;")
        f.addRow("", hint)
        self._add_form(f)

    def _form_bgm(self):
        f = QFormLayout()
        self.action_cb = _combo([("play", "再生"), ("stop", "停止")],
                                self.cmd.get("action", "play"))
        self.bgm_cb = _combo([(b["id"], b["name"]) for b in self.project.bgm],
                             self.cmd.get("bgmId", ""), none_label="（なし）")
        self.loop_cb = QCheckBox("ループ再生する")
        self.loop_cb.setChecked(bool(self.cmd.get("loop", True)))
        self.fade_spin = QSpinBox()
        self.fade_spin.setRange(0, 60000)
        self.fade_spin.setSingleStep(250)
        self.fade_spin.setSuffix(" ms")
        self.fade_spin.setValue(int(self.cmd.get("fadeMs", 0) or 0))
        f.addRow("動作:", self.action_cb)
        f.addRow("曲:", self.bgm_cb)
        f.addRow("", self.loop_cb)
        f.addRow("フェード時間:", self.fade_spin)
        hint = QLabel("※ 再生=フェードイン / 停止=フェードアウト。0でフェードなし。")
        hint.setStyleSheet("color:#888;")
        f.addRow("", hint)
        self._add_form(f)

    def _form_endroll(self):
        f = QFormLayout()
        self.text_edit = QPlainTextEdit(self.cmd.get("text", ""))
        self.text_edit.setPlaceholderText(
            "エンドロール本文（改行で複数行）。下から上へスクロールします。\n"
            "{変数名} で変数を埋め込めます。")
        self.text_edit.setMinimumHeight(160)
        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(10, 400)
        self.speed_spin.setSuffix(" px/秒")
        self.speed_spin.setValue(int(self.cmd.get("speed", 60) or 60))
        self.noskip_cb = QCheckBox("スキップ不可にする（最後まで再生）")
        self.noskip_cb.setChecked(bool(self.cmd.get("noSkip", False)))
        f.addRow("本文:", self.text_edit)
        f.addRow("スクロール速度:", self.speed_spin)
        f.addRow("", self.noskip_cb)
        hint = QLabel("※ 再生中はセリフ枠が消えます。スキップ不可にすると\n"
                      "　クリックやスペースでスキップできなくなります。")
        hint.setStyleSheet("color:#888;")
        f.addRow("", hint)
        self._add_form(f)

    def _form_se(self):
        f = QFormLayout()
        self.se_cb = _combo([(s["id"], s["name"]) for s in self.project.se],
                            self.cmd.get("seId", ""), none_label="（効果音を選択）")
        f.addRow("効果音:", self.se_cb)
        self._add_form(f)

    def _form_cg(self):
        f = QFormLayout()
        self.action_cb = _combo([("show", "表示する"), ("hide", "消す")],
                                self.cmd.get("action", "show"))
        self.cg_cb = _combo([(c["id"], c["name"]) for c in self.project.cg],
                            self.cmd.get("cgId", ""), none_label="（CGを選択）")
        f.addRow("動作:", self.action_cb)
        f.addRow("CG:", self.cg_cb)
        self._add_form(f)

    def _form_nameInput(self):
        f = QFormLayout()
        str_vars = [(v["name"], v["name"]) for v in self.project.variables
                    if v.get("type") == "string"]
        self.var_cb = _combo(str_vars, self.cmd.get("varName", ""),
                             none_label="（変数を選択）")
        self.prompt_edit = QLineEdit(self.cmd.get("prompt", ""))
        f.addRow("格納先(文字列変数):", self.var_cb)
        f.addRow("メッセージ:", self.prompt_edit)
        hint = QLabel("※ 文字列型の変数が候補に出ます。")
        hint.setStyleSheet("color:#888;")
        f.addRow("", hint)
        self._add_form(f)

    def _form_setVar(self):
        f = QFormLayout()
        items = [(v["name"], f'{v["name"]} ({v["type"]})')
                 for v in self.project.variables]
        items += [(v["name"], f'{v["name"]} ({v["type"]}) [システム]')
                  for v in self.project.system_vars]
        self.var_cb = _combo(items, self.cmd.get("varName", ""),
                             none_label="（変数を選択）")
        self.op_cb = _combo(VAR_OPS, self.cmd.get("op", "set"))
        self.value_edit = QLineEdit(str(self.cmd.get("value", "")))
        f.addRow("変数:", self.var_cb)
        f.addRow("操作:", self.op_cb)
        f.addRow("値:", self.value_edit)
        self._add_form(f)

    def _form_gauge(self):
        f = QFormLayout()
        self.gauge_cb = _combo([(g["id"], g["name"]) for g in self.project.gauges],
                               self.cmd.get("gaugeId", ""), none_label="（ゲージを選択）")
        self.op_cb = _combo(GAUGE_OPS, self.cmd.get("op", "add"))
        self.value_edit = QLineEdit(str(self.cmd.get("value", "")))
        f.addRow("ゲージ:", self.gauge_cb)
        f.addRow("操作:", self.op_cb)
        f.addRow("値:", self.value_edit)
        self._add_form(f)

    def _form_item(self):
        f = QFormLayout()
        self.item_cb = _combo([(it["id"], f'{it.get("icon","")} {it["name"]}')
                               for it in self.project.items],
                              self.cmd.get("itemId", ""), none_label="（アイテムを選択）")
        self.action_cb = _combo([("add", "入手する"),
                                 ("use", "使用する（消費）"),
                                 ("remove", "失う/破棄する")],
                                self.cmd.get("action", "add"))
        self.notify_cb = QCheckBox("入手/使用メッセージを表示する（アイコン＋説明）")
        self.notify_cb.setChecked(bool(self.cmd.get("notify", True)))
        f.addRow("アイテム:", self.item_cb)
        f.addRow("動作:", self.action_cb)
        f.addRow("", self.notify_cb)
        hint = QLabel("※「使用」で消費するかは、アイテム側の設定（使用したら消費する）に従います。\n"
                      "　メッセージはアイテムのアイコン（絵文字/画像）と説明を表示します。")
        hint.setStyleSheet("color:#888;")
        f.addRow("", hint)
        self._add_form(f)

    def _form_jump(self):
        f = QFormLayout()
        self.scene_cb = _combo([(s["id"], s["name"]) for s in self.project.scenes],
                               self.cmd.get("targetScene", ""), none_label="（シーンを選択）")
        f.addRow("移動先シーン:", self.scene_cb)
        self._add_form(f)

    def _form_label(self):
        f = QFormLayout()
        self.name_edit = QLineEdit(self.cmd.get("name", ""))
        self.name_edit.setPlaceholderText("例: 分岐A、ループ開始 など")
        f.addRow("フラグ地点名:", self.name_edit)
        hint = QLabel("※ シナリオ内に目印（位置）を作ります。\n"
                      "　「フラグへジャンプ」でここに飛べます。")
        hint.setStyleSheet("color:#888;")
        f.addRow("", hint)
        self._add_form(f)

    def _form_labelJump(self):
        f = QFormLayout()
        self.target_combo = QComboBox()
        self.target_combo.setEditable(True)
        for name in all_labels(self.project):
            self.target_combo.addItem(name)
        self.target_combo.setCurrentText(self.cmd.get("target", ""))
        f.addRow("ジャンプ先フラグ:", self.target_combo)
        hint = QLabel("※ 同名の「フラグ地点」へジャンプします。\n"
                      "　現在のシーンを優先し、無ければ全シーンから探します。")
        hint.setStyleSheet("color:#888;")
        f.addRow("", hint)
        self._add_form(f)
        # 任意の条件（満たすときだけジャンプ＝条件付きループ/分岐が可能）
        self.cmd.setdefault("condition", empty_condition())
        box = QGroupBox("ジャンプ条件（空＝常にジャンプ）")
        bl = QVBoxLayout(box)
        bl.addWidget(ConditionWidget(self.cmd["condition"], self.project))
        self.form_host.addWidget(box)

    def _form_ending(self):
        f = QFormLayout()
        self.end_cb = _combo([(e["id"], ("🔒 " if e.get("hidden") else "") + e["name"])
                              for e in self.project.endings],
                             self.cmd.get("endingId", ""), none_label="（エンディングを選択）")
        f.addRow("エンディング:", self.end_cb)
        self._add_form(f)

    def _form_if(self):
        self.cmd.setdefault("condition", empty_condition())
        self.cond_widget = ConditionWidget(self.cmd["condition"], self.project)
        box = QGroupBox("条件")
        bl = QVBoxLayout(box)
        bl.addWidget(self.cond_widget)
        self.form_host.addWidget(box)

        f = QFormLayout()
        scenes = [(s["id"], s["name"]) for s in self.project.scenes]
        self.true_cb = _combo(scenes, self.cmd.get("targetTrue", ""),
                              none_label="（次のコマンドへ）")
        self.false_cb = _combo(scenes, self.cmd.get("targetFalse", ""),
                               none_label="（次のコマンドへ）")
        f.addRow("条件成立時:", self.true_cb)
        f.addRow("不成立時:", self.false_cb)
        self._add_form(f)

    def _form_choice(self):
        f = QFormLayout()
        self.prompt_edit = QLineEdit(self.cmd.get("prompt", ""))
        self.prompt_edit.setPlaceholderText("（任意）選択前に表示する問いかけ")
        f.addRow("問いかけ:", self.prompt_edit)
        self._add_form(f)

        self.options_box = QVBoxLayout()
        host = QWidget()
        host.setLayout(self.options_box)
        self.form_host.addWidget(host)

        self._option_rows = []
        self.cmd.setdefault("options", [])
        for opt in self.cmd["options"]:
            self._add_option_row(opt)

        add_btn = QPushButton("+ 選択肢を追加")
        add_btn.clicked.connect(self._add_option)
        self.form_host.addWidget(add_btn)

    def _add_option(self):
        opt = {"id": uid("opt"), "text": "新しい選択肢",
               "targetScene": "", "condition": empty_condition()}
        self.cmd["options"].append(opt)
        self._add_option_row(opt)

    def _add_option_row(self, opt: dict):
        box = QGroupBox(f"選択肢 {len(self._option_rows) + 1}")
        v = QVBoxLayout(box)

        f = QFormLayout()
        text_edit = QLineEdit(opt.get("text", ""))
        scene_cb = _combo([(s["id"], s["name"]) for s in self.project.scenes],
                          opt.get("targetScene", ""), none_label="（次のコマンドへ）")
        f.addRow("表示文:", text_edit)
        f.addRow("移動先:", scene_cb)
        v.addLayout(f)

        opt.setdefault("condition", empty_condition())
        cond = ConditionWidget(opt["condition"], self.project)
        v.addWidget(QLabel("出現条件:"))
        v.addWidget(cond)

        rm = QPushButton("この選択肢を削除")
        rm.clicked.connect(lambda: self._remove_option(opt, box, row_ref))
        v.addWidget(rm)

        row_ref = {"opt": opt, "box": box, "text": text_edit, "scene": scene_cb}
        self._option_rows.append(row_ref)
        self.options_box.addWidget(box)

    def _remove_option(self, opt, box, row_ref):
        if opt in self.cmd["options"]:
            self.cmd["options"].remove(opt)
        if row_ref in self._option_rows:
            self._option_rows.remove(row_ref)
        box.setParent(None)

    # ------------------------------------------------------------------
    # 収集
    # ------------------------------------------------------------------
    def _accept(self):
        t = self.cmd["type"]
        if t == "say":
            self.cmd["charId"] = self.char_cb.currentData() or ""
            self.cmd["exprId"] = self.expr_cb.currentData() or ""
            self.cmd["text"] = self.text_edit.toPlainText()
            self.cmd["hideSprite"] = self.hide_sprite_cb.isChecked()
            self.cmd["pos"] = self.pos_cb.currentData() or "center"
        elif t == "narrate":
            self.cmd["text"] = self.text_edit.toPlainText()
        elif t == "charExit":
            self.cmd["charId"] = self.char_cb.currentData() or ""
        elif t == "bg":
            self.cmd["bgId"] = self.bg_cb.currentData() or ""
        elif t == "blackout":
            self.cmd["mode"] = self.mode_cb.currentData()
            self.cmd["hideUi"] = self.hideui_cb.isChecked()
        elif t == "compVis":
            self.cmd["target"] = self.target_cb.currentData() or "message"
            self.cmd["action"] = self.action_cb.currentData()
        elif t == "bgm":
            self.cmd["action"] = self.action_cb.currentData()
            self.cmd["bgmId"] = self.bgm_cb.currentData() or ""
            self.cmd["loop"] = self.loop_cb.isChecked()
            self.cmd["fadeMs"] = self.fade_spin.value()
        elif t == "endroll":
            self.cmd["text"] = self.text_edit.toPlainText()
            self.cmd["speed"] = self.speed_spin.value()
            self.cmd["noSkip"] = self.noskip_cb.isChecked()
        elif t == "se":
            self.cmd["seId"] = self.se_cb.currentData() or ""
        elif t == "cg":
            self.cmd["action"] = self.action_cb.currentData()
            self.cmd["cgId"] = self.cg_cb.currentData() or ""
        elif t == "nameInput":
            self.cmd["varName"] = self.var_cb.currentData() or ""
            self.cmd["prompt"] = self.prompt_edit.text()
        elif t == "setVar":
            self.cmd["varName"] = self.var_cb.currentData() or ""
            self.cmd["op"] = self.op_cb.currentData()
            self.cmd["value"] = self.value_edit.text()
        elif t == "gauge":
            self.cmd["gaugeId"] = self.gauge_cb.currentData() or ""
            self.cmd["op"] = self.op_cb.currentData()
            self.cmd["value"] = self.value_edit.text()
        elif t == "item":
            self.cmd["itemId"] = self.item_cb.currentData() or ""
            self.cmd["action"] = self.action_cb.currentData()
            self.cmd["notify"] = self.notify_cb.isChecked()
        elif t == "jump":
            self.cmd["targetScene"] = self.scene_cb.currentData() or ""
        elif t == "label":
            self.cmd["name"] = self.name_edit.text().strip()
        elif t == "labelJump":
            self.cmd["target"] = self.target_combo.currentText().strip()
        elif t == "ending":
            self.cmd["endingId"] = self.end_cb.currentData() or ""
        elif t == "if":
            self.cmd["targetTrue"] = self.true_cb.currentData() or ""
            self.cmd["targetFalse"] = self.false_cb.currentData() or ""
            # condition は ConditionWidget が直接 self.cmd["condition"] を更新済み
        elif t == "choice":
            self.cmd["prompt"] = self.prompt_edit.text()
            for row in self._option_rows:
                row["opt"]["text"] = row["text"].text()
                row["opt"]["targetScene"] = row["scene"].currentData() or ""
        self.result_cmd = self.cmd
        self.accept()
