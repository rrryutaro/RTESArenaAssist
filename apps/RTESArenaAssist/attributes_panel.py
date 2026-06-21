"""
attributes_panel.py — プレイヤーステータス総合表示パネル（オリジナル準拠）

Arena オリジナル ChooseAttributes 画面のレイアウトに対比して以下を表示する:

  RRR
  Breton
  Healer

  Str:38   Damage:-2     Max Kilos:76
  Int:64   Spell Pts:138/138
  Wil:50   Magic Def:+1
  Agi:48   to Hit:+1
  Spd:52
  End:47   Health:0
  Per:52   Charisma:+1
  Luc:53
            to Defend:+1
            Heal Mod:0

            BONUS PTS:0  (中央寄せ)

  Health: 30/30
  Fatigue: 75/75
  Gold:
  Experience: 0
  Level: 1

primary attributes はメモリから読み出し（cheat ON 時は書き換え可能）。
派生値は Arena Manual + OpenTESArena の公式で計算する。

派生値の公式: Arena Manual p22 + OpenTESArena ArenaPlayerUtils.cpp
"""

from __future__ import annotations

import re
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QSpinBox, QVBoxLayout, QWidget,
)

import i18n_helper as i18n
import assist_settings as settings


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# anchor 相対のメモリオフセット
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OFF_NAME            = 0x1AD     # 26B NUL 終端 ASCII
OFF_PRIMARY_1       = 0x1CD     # 8 u8 (current)
OFF_PRIMARY_2       = 0x1D5     # 8 u8 (duplicate / base)
PRIMARY_LEN         = 8

OFF_DAMAGE_I16      = 0x1DD     # i16 LE: STR に追従するダメージ補正（差分検証で確定）
OFF_BONUS_PTS_U8    = 0x129C    # u8: STR+1 で 6 に diff する byte（差分検証で確定）
OFF_HEALTH_CURR_U16 = 0x1FD
OFF_HEALTH_MAX_U16  = 0x1FF

# BONUS PTS は anchor + 0x129C (u8) に格納されている。
# memory 直読み書きするため pool/distributed の計算は不要になった。
# cheat ON で spinbox 編集 → +0x129C に直接書き込み、ゲーム側に反映される。

# 強候補（Healer INT=68 → SP 136 と一致）
OFF_SPELL_PTS_CURR  = 0x20A
OFF_SPELL_PTS_MAX   = 0x20C

# Race / Class
# 通常プレイ時オフセット（Breton=0 @ 0x1A8 を確認）。
#   chargen 観測の 0x214(race) / 0x217(class) は chargen バッファ値であり通常プレイでは異なる。
#   OFF_CLASS_INDEX=0x1A9 は観測ベースの暫定値（Healer=36）。
OFF_RACE_INDEX      = 0x1A8
OFF_CLASS_INDEX     = 0x1A9

OFF_LEVEL_U16       = 0x21D    # 旧候補（誤りと判明・廃止）
OFF_LEVEL_U8        = 0x1AA    # Level - 1 (実 Level = 値 + 1)

# Gold / Experience（差分検証で確認）:
#   Gold @ +0x5C2 (u16 LE), 実機 168=0xA8 を確認
#   Experience @ +0x5AD (u32 LE), 実機 700=0x2BC を確認
# 旧 +0x220 は別データ（無関係な値が入っていた）。
OFF_GOLD_U16        = 0x5C2
OFF_EXP_U32         = 0x5AD
OFF_FATIGUE_U16      = 0x201    # u16 LE 固定小数点。display = round(u16 * fat_max / ((STR_256+END_256)*64))。3点実測確認済み。
OFF_FATIGUE_MAX      = None    # 未格納（ゲーム側で STR+END から算出、メモリに独立保存なし）
OFF_BONUS_PTS       = None


# 種族 index → (英名, 日本語)
RACE_INDEX_TO_DISPLAY: dict[int, tuple[str, str]] = {
    0: ("Breton",   "ブレトン"),
    1: ("Redguard", "レッドガード"),
    2: ("Nord",     "ノルド"),
    3: ("Dark Elf", "ダークエルフ"),
    4: ("High Elf", "ハイエルフ"),
    5: ("Wood Elf", "ウッドエルフ"),
    6: ("Khajiit",  "カジート"),
    7: ("Argonian", "アルゴニアン"),
}


ATTR_KEYS = ("STR", "INT", "WIL", "AGI", "SPD", "END", "PER", "LUC")
# game-style 表記: 1 文字目大文字
ATTR_DISPLAY_EN = ("Str", "Int", "Wil", "Agi", "Spd", "End", "Per", "Luc")
# 日本語別名（参考用、英名と併記）
ATTR_DISPLAY_JA = ("筋力", "知性", "意志力", "敏捷", "速度", "持久力", "個性", "幸運")

# Arena オリジナル CHARSTAT.PNG / 実機画面の配置:
#   Str  : Damage    Max Kilos
#   Int  : Spell Pts
#   Wil  : Magic Def
#   Agi  : to Hit    to Defend     ← AGI 由来は同じ行に集約
#   Spd  :
#   End  : Health    Heal Mod      ← END 由来は同じ行に集約
#   Per  : Charisma
#   Luc  :
DERIVED_COL2_BY_ATTR: dict[int, str] = {
    0: "damage",       # Str
    1: "spell_pts",    # Int
    2: "magic_def",    # Wil
    3: "to_hit",       # Agi
    # 4: Spd (empty col 2)
    5: "health",       # End
    6: "charisma",     # Per
    # 7: Luc (empty col 2)
}

DERIVED_COL3_BY_ATTR: dict[int, str] = {
    0: "max_kilos",    # Str row col 3
    3: "to_defend",    # Agi row col 3 (AGI 由来)
    5: "heal_mod",     # End row col 3 (END 由来)
}

# 派生値の表示ラベル（英名 / 日本語）
DERIVED_LABELS: dict[str, tuple[str, str]] = {
    "damage":     ("Damage",    "ダメージ"),
    "spell_pts":  ("Spell Pts", "呪文ポイント"),
    "magic_def":  ("Magic Def", "魔法防御"),
    "to_hit":     ("to Hit",    "命中"),
    "to_defend":  ("to Defend", "防御"),
    "health":     ("Health",    "体力"),
    "charisma":   ("Charisma",  "魅力"),
    "heal_mod":   ("Heal Mod",  "回復補正"),
    "max_kilos":  ("Max Kilos", "最大重量"),
    "bonus_pts":  ("BONUS PTS", "ボーナスPTS"),
}

STAT_LABELS: dict[str, tuple[str, str]] = {
    "hp":         ("Health",     "体力"),
    "fatigue":    ("Fatigue",    "疲労"),
    "gold":       ("Gold",       "ゴールド"),
    "experience": ("Experience", "経験値"),
    "level":      ("Level",      "レベル"),
}


def resolve_class_en_from_label(label: Optional[str]) -> Optional[str]:
    """表示ラベルから Arena の canonical class 英名を復元する。"""
    text = (label or "").strip()
    if not text:
        return None

    def _canonical_from_en(value: str) -> Optional[str]:
        value_norm = value.strip().lower()
        try:
            from class_list_panel import CLASS_LIST_ORDER
            for canonical, _kana, _kanji in CLASS_LIST_ORDER:
                if value_norm == canonical.lower():
                    return canonical
        except ImportError:
            pass
        return None

    direct = _canonical_from_en(text)
    if direct:
        return direct

    m = re.search(r"[（(]\s*([A-Za-z ]+)\s*[)）]", text)
    if m:
        from_paren = _canonical_from_en(m.group(1))
        if from_paren:
            return from_paren

    try:
        from class_list_panel import CLASS_LIST_ORDER
        for canonical, kana, kanji in CLASS_LIST_ORDER:
            if text == kana or (kanji and text == kanji):
                return canonical
            if kanji and text == f"{kana}（{kanji}）":
                return canonical
    except ImportError:
        pass

    try:
        from controllers.chargen_helpers import _CHARGEN_CLASS_JA
        for en_name, ja_name in _CHARGEN_CLASS_JA.items():
            if text == ja_name:
                return en_name
    except ImportError:
        pass

    return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 派生値計算式（Arena Manual p22 ベースの段階式）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 派生値の純粋計算式は attribute_formulas.py へ分離（副作用なし・単体テスト対象）。
# 後方互換のため本モジュール名前空間へ再エクスポートする（クラス内は bare 名で参照）。
from attribute_formulas import (  # noqa: E402
    _scale_100_to_256,
    _scale_256_to_100,
)
import attribute_formulas as _attribute_formulas  # noqa: E402

# 後方互換 re-export (実体は attribute_formulas が単一所有。
# test_attribute_formulas が同一実体であることを固定)。
calc_damage_bonus = _attribute_formulas.calc_damage_bonus
calc_max_kilos = _attribute_formulas.calc_max_kilos
calc_magic_defense = _attribute_formulas.calc_magic_defense
calc_bonus_to_hit = _attribute_formulas.calc_bonus_to_hit
calc_bonus_to_health = _attribute_formulas.calc_bonus_to_health
calc_max_stamina = _attribute_formulas.calc_max_stamina


def _signed(value: int) -> str:
    """符号付き表示。0 の場合も "+0" でゲーム画面と一致させる。"""
    return f"+{value}" if value >= 0 else str(value)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Widget
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

POLL_INTERVAL_MS = 100
UNKNOWN          = "—"

# QGridLayout 列構成:
#   0: primary label  (Str:)
#   1: primary value  (spinbox)
#   2: derived label  (Damage:)
#   3: derived value
#   4: max kilos label
#   5: max kilos value
COL_PRIMARY_LABEL  = 0
COL_PRIMARY_VALUE  = 1
COL_DERIVED_LABEL  = 2
COL_DERIVED_VALUE  = 3
COL_KILOS_LABEL    = 4
COL_KILOS_VALUE    = 5

# 行配置
ROW_NAME           = 0
ROW_RACE           = 1
ROW_CLASS          = 2
ROW_HEADER_GAP     = 3
ROW_PRIMARY_FIRST  = 4   # Str
ROW_PRIMARY_LAST   = 11  # Luc
ROW_PRE_BONUS_GAP  = 12
ROW_BONUS_PTS      = 13
ROW_POST_BONUS_GAP = 14
ROW_HP             = 15
ROW_FATIGUE        = 16
ROW_GOLD           = 17
ROW_GOLD_EXP_GAP   = 18
ROW_EXP            = 19
ROW_LEVEL          = 20


def _bilingual(en: str, ja: str) -> str:
    return f"{en} ({ja})"


class AttributesPanel(QWidget):
    """ChooseAttributes 画面のオリジナル配置に準拠した総合パネル。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._analyzer = None
        self._anchor: int = 0
        # cheat 親スイッチ + 「ステータス変更」サブ設定の AND で能力値書き換えを有効化
        self._cheat_enabled: bool = (
            bool(settings.get("cheat_enabled", False))
            and bool(settings.get("cheat_status_change", False))
        )
        # cheat 親スイッチ単独の状態 (= 任意値書込み / 常時 MAX の有効条件)。
        # ステータス変更 ON は不要。
        self._cheat_parent: bool = bool(settings.get("cheat_enabled", False))
        # 常時 MAX 系は cheat 親スイッチのみで有効 (= ステータス変更 ON は不要)。
        self._health_max_enabled: bool = self._compute_always_max("cheat_health_max")
        self._fatigue_max_enabled: bool = self._compute_always_max("cheat_fatigue_max")
        self._spell_max_enabled: bool = self._compute_always_max("cheat_spell_max")
        # chargen 中は primary attrs が 0-100 ダイレクト値（normal-play は 256 スケール）
        self._chargen_mode: bool = False
        # ボーナス画面（CHARSTAT.IMG）中は primary attrs が 100 scale に切替わる
        # （差分検証で確定）。BONUS PTS も bonus_screen 中のみ意味あり。
        self._is_bonus_screen: bool = False
        # chargen Appearance 画面では memory 内容がゴミ値となる
        # ため、_poll() を一時凍結して最後の有効表示 (ChooseAttributes 時の値) を
        # 維持する。chargen_state.poll() からセットされる。
        self._freeze_updates: bool = False

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll)

        self._race_label: Optional[str] = None
        self._class_label: Optional[str] = None

        # widget refs
        self._spinboxes: list[QSpinBox] = []
        self._derived: dict[str, QLabel] = {}
        self._stats:   dict[str, QLabel] = {}
        self._name_lbl  = QLabel(UNKNOWN)
        self._race_lbl  = QLabel(UNKNOWN)
        self._class_lbl = QLabel(UNKNOWN)

        self._build_ui()
        self._apply_cheat_state(self._cheat_enabled)

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        # チート / 常時 MAX 系の UI は設定ダイアログのチートタブへ移動。
        # 状態自体は self._cheat_enabled / self._{health,fatigue,spell}_max_enabled
        # で保持し、設定変更時は apply_cheat_settings() を呼び出して反映する。
        # 旧 _cheat_note_lbl はステータス書き込み権限エラー時のフィードバック
        # 表示にも使われていたため、表示用ラベルとしてのみ残置 (UI から見えない
        # よう非表示にする)。
        self._cheat_note_lbl = QLabel("")
        self._cheat_note_lbl.setObjectName("dimLabel")
        self._cheat_note_lbl.setVisible(False)
        root.addWidget(self._cheat_note_lbl)

        # メイングリッド
        root.addWidget(self._build_main_grid())

        # チート: 任意値書込みグループ (cheat 親 ON 時のみ表示)
        self._cheat_values_group = self._build_cheat_values_group()
        self._cheat_values_group.setVisible(self._cheat_parent)
        root.addWidget(self._cheat_values_group)

        root.addSpacing(12)
        root.addSpacing(12)
        note = QLabel(i18n.tr("status.note_redraw"))
        note.setObjectName("dimLabel")
        note.setWordWrap(True)
        root.addWidget(note)

        root.addStretch(1)

    def _build_main_grid(self) -> QWidget:
        from attributes_panel_ui import build_main_grid
        return build_main_grid(self)

    # ------------------------------------------------------------------
    # 接続管理
    # ------------------------------------------------------------------

    def set_memory_target(self, analyzer, anchor: int) -> None:
        self._analyzer = analyzer
        self._anchor = anchor
        self._poll()
        self._poll_timer.start()
        self._apply_write_permission_state()

    def clear_memory_target(self) -> None:
        self._analyzer = None
        self._anchor = 0
        self._poll_timer.stop()

    def set_chargen_mode(self, mode: bool) -> None:
        """chargen 中 / 通常プレイ中の切替。

        chargen 中: primary attrs は 0-100 ダイレクト値なので変換不要。
                    race/level は メモリ値が不正確なため chargen 検出値を優先。
        normal-play: primary attrs は 256 スケール → (b*100)>>8 で変換。
        """
        self._chargen_mode = mode
        # BONUS PTS は chargen 中または bonus_screen 中のみ表示
        self._bp_widget.setVisible(mode or self._is_bonus_screen)

    def set_is_bonus_screen(self, mode: bool) -> None:
        """ボーナス画面（CHARSTAT.IMG）中フラグ。

        ボーナス画面中:
        - primary attrs は 0-100 ダイレクト値（chargen と同じ、変換不要）
        - BONUS PTS は意味のある値（+0x129C を表示）
        通常プレイ中・status_page 中は False。
        """
        if self._is_bonus_screen == mode:
            return
        self._is_bonus_screen = mode
        # BONUS PTS の表示切替
        self._bp_widget.setVisible(self._chargen_mode or mode)

    def set_race_class(self, race: Optional[str], cls: Optional[str]) -> None:
        """assist_window 側で chargen から得た race / class 表示名（日本語）を反映。

        chargen モード中は memory 読み出しより優先される。
        """
        self._race_label = race
        self._class_label = cls

    # ------------------------------------------------------------------
    # チート: 任意値書込み (実行ボタンでメモリへ一回書込み)
    # ------------------------------------------------------------------

    # (key, ラベル i18n, spinbox 最大値)
    _CHEAT_VALUE_SPECS = (
        ("health",  "status.cheat_field_hp",      65535),
        ("fatigue", "status.cheat_field_fatigue", 200),
        ("spell",   "status.cheat_field_spell",   65535),
        ("gold",    "status.cheat_field_gold",    65535),
        ("exp",     "status.cheat_field_exp",     9999999),
    )

    def _build_cheat_values_group(self) -> QGroupBox:
        from attributes_panel_ui import build_cheat_values_group
        return build_cheat_values_group(self)

    def _write_cheat_value(self, key: str) -> None:
        """実行ボタン: 入力値を該当メモリへ一回書き込む (cheat 親 ON 時のみ)。"""
        if not self._cheat_parent:
            return
        if self._analyzer is None or self._anchor == 0:
            return
        if not getattr(self._analyzer, "can_write", False):
            self._cheat_note_lbl.setText(i18n.tr("status.no_write_permission"))
            self._cheat_note_lbl.setVisible(True)
            return
        sb = getattr(self, "_cheat_value_spins", {}).get(key)
        if sb is None:
            return
        value = int(sb.value())

        def _u16(off: int, v: int) -> None:
            v &= 0xFFFF
            self._analyzer.write_bytes(
                self._anchor + off, bytes([v & 0xFF, (v >> 8) & 0xFF]))

        try:
            if key == "health":
                _u16(OFF_HEALTH_CURR_U16, value)
            elif key == "spell":
                _u16(OFF_SPELL_PTS_CURR, value)
            elif key == "gold":
                _u16(OFF_GOLD_U16, value)
            elif key == "exp":
                v = value & 0xFFFFFFFF
                self._analyzer.write_bytes(
                    self._anchor + OFF_EXP_U32,
                    bytes([v & 0xFF, (v >> 8) & 0xFF,
                           (v >> 16) & 0xFF, (v >> 24) & 0xFF]))
            elif key == "fatigue":
                # 表示値 → 内部固定小数点 u16 = round(v*256/100) << 6
                raw256 = max(0, min(1023, round(value * 256 / 100)))
                _u16(OFF_FATIGUE_U16, raw256 << 6)
        except (OSError, AttributeError):
            pass

    # ------------------------------------------------------------------
    # チート切替
    # ------------------------------------------------------------------

    def _on_cheat_toggled(self, on: bool) -> None:
        self._cheat_enabled = on
        settings.set_val("cheat_enabled", on)
        self._apply_cheat_state(on)
        self._apply_write_permission_state()

    def _compute_always_max(self, key: str) -> bool:
        """常時 MAX 系チートの有効状態を算出する。

        cheat_enabled (親スイッチ) のみで有効化し、「ステータス変更」には依存しない。
        """
        if not bool(settings.get("cheat_enabled", False)):
            return False
        return bool(settings.get(key, False))

    def apply_cheat_settings(self) -> None:
        """設定ダイアログでチート設定が変更されたときの反映用。

        cheat_enabled / 常時 MAX 系の最新値を settings から読み直し、現在値と
        異なる場合は内部状態とスピン編集可否を更新する。
        """
        new_cheat = (
            bool(settings.get("cheat_enabled", False))
            and bool(settings.get("cheat_status_change", False))
        )
        if new_cheat != self._cheat_enabled:
            self._cheat_enabled = new_cheat
            self._apply_cheat_state(new_cheat)
            self._apply_write_permission_state()
        # 常時 MAX 系は親スイッチのみで有効 (= ステータス変更非依存)。
        self._health_max_enabled = self._compute_always_max("cheat_health_max")
        self._fatigue_max_enabled = self._compute_always_max("cheat_fatigue_max")
        self._spell_max_enabled = self._compute_always_max("cheat_spell_max")
        # 任意値書込み UI は cheat 親スイッチ ON 時のみ表示。
        self._cheat_parent = bool(settings.get("cheat_enabled", False))
        if hasattr(self, "_cheat_values_group"):
            self._cheat_values_group.setVisible(self._cheat_parent)

    def _apply_cheat_state(self, on: bool) -> None:
        all_spins = list(self._spinboxes)
        if hasattr(self, "_bp_spin"):
            all_spins.append(self._bp_spin)
        for sb in all_spins:
            sb.setReadOnly(not on)
            sb.setButtonSymbols(
                QSpinBox.ButtonSymbols.UpDownArrows if on
                else QSpinBox.ButtonSymbols.NoButtons
            )
            # widget 幅自体を ON/OFF で切替える。updateGeometry()
            #       だけでは Qt が widget サイズを再計算してくれないため、
            #       setMinimum/MaximumWidth を直接切替えて反映を確実にする。
            #       ON  = 枠 + 上下ボタンが収まる幅
            #       OFF = 値だけが収まるコンパクト幅（ラベル風）
            #       OFF 時は QSpinBox デフォルト枠を残したまま widget 幅を
            #       コンパクトにして下線が目立つ表示にする。
            sb.setStyleSheet("")
            if on:
                sb.setMinimumWidth(72)
                sb.setMaximumWidth(96)
            else:
                sb.setMinimumWidth(0)
                sb.setMaximumWidth(72)
            sb.updateGeometry()
        if hasattr(self, "_main_grid") and self._main_grid is not None:
            self._main_grid.invalidate()
        if on:
            self._cheat_note_lbl.setText(i18n.tr("status.cheat_enabled"))
        else:
            self._cheat_note_lbl.setText(i18n.tr("status.cheat_disabled_note"))

    def _on_bonus_changed(self, value: int) -> None:
        """BONUS PTS spinbox の編集 → memory +0x129C (u8) に直接書き込む。

        cheat OFF 時 (read-only) はこのコールバックは来ない想定。
        """
        if not self._cheat_enabled:
            return
        if self._analyzer is None or self._anchor == 0:
            return
        if not getattr(self._analyzer, "can_write", False):
            return
        try:
            payload = bytes([max(0, min(255, int(value)))])
            self._analyzer.write_bytes(self._anchor + OFF_BONUS_PTS_U8, payload)
        except OSError:
            pass

    def _apply_write_permission_state(self) -> None:
        if (self._cheat_enabled and self._analyzer is not None
                and not getattr(self._analyzer, "can_write", True)):
            self._cheat_note_lbl.setText(i18n.tr("status.no_write_permission"))

    # ------------------------------------------------------------------
    # ポーリング & 書き込み
    # ------------------------------------------------------------------

    def set_freeze_updates(self, freeze: bool) -> None:
        """ステータス表示の更新を一時凍結する。

        True にすると _poll() がメモリ読み出し・表示更新を skip し、
        最後の有効表示を維持する。chargen 外見画面など、関連
        memory location にゴミ値が書き込まれる場面で異常値表示を防ぐ。
        """
        self._freeze_updates = freeze

    def set_display_active(self, active: bool) -> None:
        """ステータス表示の有効/無効を切替える。

        無効 (active=False) のとき:
          - polling を停止し、メモリ読み出しと表示更新を行わない
          - 表示値を全て UNKNOWN/初期状態にクリアする (前回プレイの残置防止)
        有効 (active=True) のとき:
          - polling を再開し、次回 poll で実メモリ値を表示
        タイトル中 / 能力値配分前 chargen で False、能力値配分以降で True。
        """
        if active:
            self._freeze_updates = False
        else:
            self._freeze_updates = True
            self._clear_display()

    def _clear_display(self) -> None:
        """全表示フィールドを初期状態 (UNKNOWN/0) にリセットする。"""
        self._name_lbl.setText(UNKNOWN)
        self._race_lbl.setText(UNKNOWN)
        self._class_lbl.setText(UNKNOWN)
        for sb in self._spinboxes:
            sb.blockSignals(True)
            sb.setValue(0)
            sb.blockSignals(False)
        for w in self._derived.values():
            w.setText(UNKNOWN)
        for w in self._stats.values():
            w.setText(UNKNOWN)
        self._bp_spin.blockSignals(True)
        self._bp_spin.setValue(0)
        self._bp_spin.blockSignals(False)

    def _poll(self) -> None:
        from attributes_panel_poll import poll_attributes
        poll_attributes(self)

    def _read_u16(self, addr: int) -> int:
        b = self._analyzer.read_bytes(addr, 2)
        return b[0] | (b[1] << 8)

    def _next_exp_threshold(self, current_level: Optional[int]) -> Optional[int]:
        """現在のクラス・レベルから次レベル必要経験値を返す。chargen 中や
        クラス ID 未取得時は None。
        """
        if current_level is None or self._chargen_mode:
            return None
        try:
            cls_byte = self._analyzer.read_bytes(self._anchor + OFF_CLASS_INDEX, 1)[0]
            mapping = settings.get("arena_play_class_id_map", {}) or {}
            class_en = mapping.get(str(cls_byte))
            if not class_en:
                class_en = resolve_class_en_from_label(self._class_label)
            if not class_en:
                class_en = resolve_class_en_from_label(self._class_lbl.text())
            if not class_en:
                return None
            import arena_data
            cls_data = arena_data.get_class_by_name(class_en)
            if not cls_data:
                return None
            from experience_calc import exp_threshold_for_next_level
            return exp_threshold_for_next_level(cls_data["id"], current_level)
        except (OSError, AttributeError, ImportError):
            return None

    def _lookup_class_display(self, cls_idx: int) -> Optional[str]:
        """通常プレイ時クラス内部 ID (+0x1A9) から「日本語 (English)」表記を返す。"""
        mapping = settings.get("arena_play_class_id_map", {}) or {}
        en = mapping.get(str(cls_idx))
        if not en:
            return None
        try:
            from class_list_panel import CLASS_LIST_ORDER
            for canonical, kana, kanji in CLASS_LIST_ORDER:
                if canonical == en:
                    return f"{kana} ({en})"
        except ImportError:
            pass
        return en

    def _on_attr_changed(self, value: int) -> None:
        if not self._cheat_enabled:
            return
        sb = self.sender()
        if not isinstance(sb, QSpinBox):
            return
        idx = sb.property("attr_idx")
        if not isinstance(idx, int):
            return
        if self._analyzer is None or self._anchor == 0:
            return
        if not getattr(self._analyzer, "can_write", False):
            return
        # 書き込み時のスケール変換
        # 表示は常に 0-100 だが、メモリ表現はモードで異なる:
        #   - chargen / bonus_screen: メモリ +0x1CD は 0-100 ダイレクト
        #   - normal-play:            メモリ +0x1CD は 256 スケール raw
        # 旧実装は変換せずに raw を書いていたため、normal-play で 90 入力 →
        # memory 90 → 次 poll で round(90*100/256)=35 に戻る現象が発生した。
        if self._chargen_mode or self._is_bonus_screen:
            raw_val = max(0, min(255, int(value)))
        else:
            raw_val = max(0, min(255, round(value * 256 / 100)))
        try:
            payload = bytes([raw_val])
            self._analyzer.write_bytes(self._anchor + OFF_PRIMARY_1 + idx, payload)
            self._analyzer.write_bytes(self._anchor + OFF_PRIMARY_2 + idx, payload)
        except OSError:
            pass
