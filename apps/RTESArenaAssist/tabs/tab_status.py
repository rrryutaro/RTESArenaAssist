"""
tab_status.py — プレイヤーステータスタブ

AttributesPanel を埋め込んで、プレイヤーの primary attributes と派生値を
リアルタイム表示する。チート機能 ON 時は書き換え可能。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

import i18n_helper as i18n
from attributes_panel import AttributesPanel


class TabStatus(QWidget):
    def __init__(self, panel=None, parent=None):
        super().__init__(parent)
        self._connected: bool = False
        self._display_active: bool = True
        # AttributesPanel は翻訳タブと 1 インスタンスを共有する。外部
        # (assist_window) から受け取り、未指定時のみ自前生成する。
        self._panel = panel if panel is not None else AttributesPanel()
        self._build_ui()
        self._refresh_visibility()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self._no_conn_lbl = QLabel(i18n.tr("status.no_connection"))
        self._no_conn_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_conn_lbl.setWordWrap(True)
        self._no_conn_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        root.addWidget(self._no_conn_lbl)

        # 共有 AttributesPanel をマウントする slot。アクティブタブ切替時に
        # assist_window が mount_attributes_panel() 経由で reparent する。
        self._attr_slot = QWidget()
        _slot_lay = QVBoxLayout(self._attr_slot)
        _slot_lay.setContentsMargins(0, 0, 0, 0)
        _slot_lay.addWidget(self._panel, 1)
        root.addWidget(self._attr_slot, 1)

    # ------------------------------------------------------------------

    def _refresh_visibility(self) -> None:
        """接続状態 + display_active から no_conn ラベル / パネルの表示制御。

        - 切断中: no_conn 表示、パネル非表示
        - 接続中 + display 無効 (タイトル中 / chargen 前半): 何も表示しない
        - 接続中 + display 有効: パネル表示
        """
        if not self._connected:
            self._no_conn_lbl.setVisible(True)
            self._panel.setVisible(False)
        elif not self._display_active:
            self._no_conn_lbl.setVisible(False)
            self._panel.setVisible(False)
        else:
            self._no_conn_lbl.setVisible(False)
            self._panel.setVisible(True)

    def mount_attributes_panel(self) -> None:
        """共有 AttributesPanel を本タブの slot へ取り込む (reparent)。

        翻訳タブから戻すとき等に assist_window から呼ばれて実体を
        ステータスタブ側の slot に移す。
        """
        if self._panel.parent() is not self._attr_slot:
            self._attr_slot.layout().addWidget(self._panel, 1)
        self._refresh_visibility()

    def set_connected(self, connected: bool) -> None:
        self._connected = connected
        if not connected:
            self._panel.clear_memory_target()
        self._refresh_visibility()

    def set_memory_target(self, analyzer, anchor: int) -> None:
        self._connected = True
        self._panel.set_memory_target(analyzer, anchor)
        self._refresh_visibility()

    def clear_memory_target(self) -> None:
        self._panel.clear_memory_target()
        self.set_connected(False)

    def set_chargen_mode(self, mode: bool) -> None:
        self._panel.set_chargen_mode(mode)

    def set_is_bonus_screen(self, mode: bool) -> None:
        """ボーナス画面（レベルアップ / キャラクター作成時）中フラグを内部パネルへ伝える。

        ボーナス状態では primary attrs が 0-100 ダイレクト値となり、通常プレイの
        256 スケール変換とは計算方法が異なる。翻訳タブ側 AttributesPanel とは
        独立インスタンスのため、ステータスタブ側にも伝えないと通常計算のままの
        誤った値が表示される。
        """
        self._panel.set_is_bonus_screen(mode)

    def set_race_class(self, race: str | None, cls: str | None) -> None:
        self._panel.set_race_class(race, cls)

    def set_freeze_updates(self, freeze: bool) -> None:
        """ステータス表示の更新を一時凍結する。

        chargen 外見画面など memory にゴミ値が書かれる場面で
        異常表示を防ぐ。chargen_state.poll() から呼ばれる。
        """
        self._panel.set_freeze_updates(freeze)

    def set_display_active(self, active: bool) -> None:
        """ステータス表示の有効/無効を切替える (マップタブと同じ挙動)。

        無効時はパネル全体を非表示にし、何も表示しない状態にする。
        個別フィールドのクリアでは描画の都度フィールド更新が発生して
        チラツキが見えるため、widget の visibility を直接制御する。
        無効化中はパネル内 polling も停止する (再有効化で自動再開)。
        タイトル中 / chargen 前半 (能力値配分前) で False、それ以降で True。
        """
        if self._display_active == active:
            return
        self._display_active = active
        self._panel.set_display_active(active)
        self._refresh_visibility()

    def apply_cheat_settings(self) -> None:
        """設定ダイアログでチート設定が変更されたときの反映。

        ステータスタブが持つ AttributesPanel に最新の cheat_enabled /
        常時 MAX 系設定を反映する。翻訳タブ側 AttributesPanel とは
        独立インスタンスのため、双方への反映が必要。
        """
        self._panel.apply_cheat_settings()
