"""
tab_translate.py — 翻訳タブ

panel_mode で表示内容を切り替える:
  - "translate"          : 既定（ゲーム状態 + 翻訳ペア）
  - "class_list"         : クラス一覧パネル（chargen クラス選択画面用）
  - "race_list"          : 種族一覧パネル（chargen 種族選択画面用、b57）
  - "choose_attributes"  : ステータス決定パネル（chargen ChooseAttributes 画面用）
  - "load_screen"        : セーブスロット一覧（LOADSAVE.IMG 表示中）
  - "item_pickup"        : NEWPOP アイテム取得一覧
  - "place_list"         : 場所一覧 / 詳細場所一覧（ASK ABOUT? Where is... 系）
  - "shop_buy"           : 店アイテム一覧（Buy Drinks 等選択後）
"""

import logging

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QWidget,
)

import assist_settings as settings
import i18n_helper as i18n

_log = logging.getLogger("RTESArenaAssist")
from attributes_panel import AttributesPanel
from appearance_faces_panel import AppearanceFacesPanel
from tabs.tab_map import TabMap
from tabs.translate_panels.item_row import ItemRow
from tabs.translate_panels.shop_item_row import ShopItemRow
from tabs.translate_panels.equipment_list import render_equipment_list
from tabs.translate_panels.load_screen import render_load_screen_slots


_MODE_TRANSLATE         = "translate"
_MODE_CLASS_LIST        = "class_list"
_MODE_RACE_LIST         = "race_list"
_MODE_CHOOSE_ATTRIBUTES = "choose_attributes"
_MODE_LOAD_SCREEN       = "load_screen"
_MODE_ITEM_PICKUP       = "item_pickup"
_MODE_EQUIPMENT         = "equipment"
_MODE_SPELL_DETAIL      = "spell_detail"
_MODE_PLACE_LIST        = "place_list"
_MODE_SHOP_BUY          = "shop_buy"
# 施設専用 L4 一覧モード。宿屋 shop_buy とは別 identity だが、純粋なリスト行
# ウィジェット (3 列、ShopItemRow) は副作用なしの描画部品として共有する。
_MODE_FACILITY_LIST     = "facility_list"
_MODE_APPEARANCE_FACES  = "appearance_faces"
_MODE_FALLBACK_STATUS   = "fallback_status"
_MODE_FALLBACK_MAP      = "fallback_map"


class TabTranslate(QWidget):
    # パネルモード変化を通知する (assist_window が共有 AttributesPanel の
    # マウント先タブを判断するために購読する)。
    panel_mode_changed = Signal(str)

    def __init__(self, attributes_panel=None, parent=None):
        super().__init__(parent)
        self._panel_mode = _MODE_TRANSLATE
        # AttributesPanel はステータスタブと 1 インスタンスを共有する。
        # 外部 (assist_window) から受け取り、未指定時のみ自前生成する。
        self._attributes_panel = (
            attributes_panel if attributes_panel is not None
            else AttributesPanel())
        self._build_ui()
        self.set_connected(False)

    def _build_ui(self):
        from tabs.tab_translate_ui import build_ui
        build_ui(self)

    # ------------------------------------------------------------------

    def set_connected(self, connected: bool) -> None:
        self._no_conn.setVisible(not connected)
        self._conn_widget.setVisible(connected)

    def update_game_state(self, state: dict) -> None:
        """旧ゲーム状態行はマップタブ上部の場所表示に移行したため空実装。

        既存の poll_controller からの呼び出しを壊さないために残置している。
        場所表示は poll_controller から tab_map.update_map_state() へ
        place_text として渡される。
        """
        return

    def update_translation(self, original: str, translated: str,
                           *, suppress_fallback: bool = False) -> None:
        # 観測ログ: 翻訳タブに渡される (原文, 翻訳) ペアの変化を追跡。
        # 「(辞書未登録)」と表示される原文の流入経路を特定するため。
        _prev_orig = getattr(self, "_b267_prev_orig", None)
        _prev_trans = getattr(self, "_b267_prev_trans", None)
        if (original, translated) != (_prev_orig, _prev_trans):
            self._b267_prev_orig = original
            self._b267_prev_trans = translated
            _log.debug(
                "b267 tab_translate.update_translation "
                "(panel_mode=%r orig=%r trans=%r)",
                self._panel_mode, original[:160], translated[:160])
        nd     = i18n.tr("translate.no_data")
        not_in = i18n.tr("translate.not_in_dict")
        self._orig_val.setText(original or nd)
        self._trans_val.setText(translated if translated else not_in)
        # fallback 床判定は flush 末尾の単一権威 (UiRouter.
        # _apply_flush_panel_mode → resolve_flush_mode) へ完全集約済み。
        # update_translation は本文描画専念。suppress_fallback は呼出側互換の
        # ため受けるが未使用 (常に床判定なし＝per-push bypass 廃止)。

    def fallback_map_tab(self) -> TabMap:
        """翻訳タブに埋め込んだ TabMap インスタンス。

        assist_window の apply_settings 等で共通 apply を呼びたい場合に使う。
        """
        return self._fallback_map_tab

    def update_fallback_map_state(self, *args, **kwargs) -> None:
        """埋め込み TabMap の update_map_state を proxy する。"""
        self._fallback_map_tab.update_map_state(*args, **kwargs)

    def poll_fallback_automap_file(self) -> bool:
        """埋め込み TabMap の poll_automap_file を proxy する。"""
        return self._fallback_map_tab.poll_automap_file()

    def apply_map_settings(self) -> None:
        """assist_window から呼ばれてマップ設定変更を埋め込み TabMap に反映。"""
        self._fallback_map_tab.apply_settings()

    # fallback 床判定 (旧 _maybe_apply_fallback) と top_level 同期
    # (旧 set_top_level_state) は撤去した。fallback は flush 末尾の単一権威
    # (UiRouter._apply_flush_panel_mode → panel_mode_resolver.resolve_flush_mode)
    # のみが決定する (pregame/chargen 抑止・所有者不在の床落ちを含む)。
    # 通常プレイ突入時の床落ちは UiRouter 経由の提案 (poll の load 完了解放 /
    # _transition_top_level) で funnel に乗せ、resolver が確定する。

    # ------------------------------------------------------------------
    # モード切替
    # ------------------------------------------------------------------

    def set_panel_mode(self, mode: str) -> None:
        if mode == self._panel_mode:
            return
        if mode == _MODE_CLASS_LIST:
            self._stack.setCurrentIndex(1)
            self._class_list_panel.reset_selection()
        elif mode == _MODE_CHOOSE_ATTRIBUTES:
            self._stack.setCurrentIndex(2)
        elif mode == _MODE_LOAD_SCREEN:
            self._stack.setCurrentIndex(3)
        elif mode == _MODE_ITEM_PICKUP:
            self._stack.setCurrentIndex(4)
        elif mode == _MODE_EQUIPMENT:
            self._stack.setCurrentIndex(5)
        elif mode == _MODE_SPELL_DETAIL:
            self._stack.setCurrentIndex(6)
        elif mode == _MODE_RACE_LIST:
            # 種族選択拡張
            self._stack.setCurrentIndex(7)
            self._race_list_panel.reset_selection()
        elif mode == _MODE_PLACE_LIST:
            self._stack.setCurrentIndex(8)
        elif mode == _MODE_SHOP_BUY:
            self._stack.setCurrentIndex(9)
        elif mode == _MODE_FACILITY_LIST:
            # 施設専用一覧 (宿屋 shop_buy とは別ページ index 12)。
            self._stack.setCurrentIndex(12)
        elif mode == _MODE_APPEARANCE_FACES:
            self._stack.setCurrentIndex(10)
        elif mode == _MODE_FALLBACK_STATUS:
            self._stack.setCurrentIndex(2)   # AttributesPanel と共有
        elif mode == _MODE_FALLBACK_MAP:
            self._stack.setCurrentIndex(11)
        else:
            mode = _MODE_TRANSLATE
            self._stack.setCurrentIndex(0)
        self._panel_mode = mode
        self.panel_mode_changed.emit(mode)

    def update_item_pickup_list(self, items: list, remaining: int) -> None:
        """NEWPOP アイテム取得一覧を更新する。

        items: [{"en": str, "ja": str, "taken": bool}, ...]
        remaining: 残り取得可能アイテム数
        """
        layout = self._pickup_rows_layout
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for item_data in items:
            en = item_data.get("en", "")
            ja = item_data.get("ja", "") or "—"
            row = ItemRow(en, ja)
            if item_data.get("taken"):
                row.set_taken(True)
            layout.addWidget(row)

        layout.addStretch(1)
        self._pickup_remaining.setText(f"残り {remaining} 個" if remaining > 0 else "")

    def update_equipment_list(self, items: list) -> None:
        """装備画面インベントリ一覧を更新する。"""
        render_equipment_list(self._equip_table, items)

    def update_place_list(self, items: list) -> None:
        """場所一覧 / 詳細場所一覧 を更新する。

        items: [{"en": str, "ja": str}, ...]

        場所一覧は「取得済み」概念のない画面なので
        状態マーカー (`•` / `✓`) は出さない。
        """
        layout = self._place_rows_layout
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for item_data in items:
            en = item_data.get("en", "")
            ja = item_data.get("ja", "") or "—"
            layout.addWidget(ItemRow(en, ja, show_mark=False))

        layout.addStretch(1)

    def set_place_list_title(self, title: str) -> None:
        """場所一覧パネルのグループボックスタイトルを更新する。空文字でタイトル枠を隠す。"""
        self._place_list_group.setTitle(title)

    @staticmethod
    def _render_price_rows(layout, items: list, *,
                           show_price: bool = True) -> None:
        """価格付きリスト行 (ShopItemRow) を layout へ描画する純粋 helper。

        shop_buy / facility_list が共有する副作用なしの描画部品。owner や mode、
        どの施設かには一切依存せず、items を ShopItemRow 行として並べるだけ。
        items: [{"en": str, "ja": str | None, "price_display": str, ...}, ...]
        """
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        for item_data in items:
            en = item_data.get("en", "")
            ja = item_data.get("ja", "") or ""
            price_display = item_data.get("price_display", "")
            extras = []
            hands = item_data.get("hands", "")
            protects = item_data.get("protects_ja", "") or item_data.get(
                "protects", "")
            weight = item_data.get("weight", "")
            if protects:
                extras.append(str(protects))
            elif hands:
                extras.append(str(hands))
            if weight:
                extras.append(str(weight))
            layout.addWidget(ShopItemRow(
                en, ja, price_display, extras=extras,
                show_price=show_price,
                unidentified=bool(item_data.get("is_unidentified", False))))
        layout.addStretch(1)

    def update_shop_buy_list(self, items: list) -> None:
        """店アイテム一覧 (shop_buy モード、宿屋) を更新する。

        items: [{"en": str, "ja": str | None, "price_display": str,
                 "price_raw": str}, ...]
        """
        self._render_price_rows(self._shop_buy_rows_layout, items)

    def update_facility_list(self, items: list) -> None:
        """施設専用 L4 一覧 (facility_list モード) を更新する。

        宿屋 shop_buy とは別ページ (_facility_list_rows_layout) に描画する。
        共有するのは純粋な行描画 helper (_render_price_rows) のみ。
        """
        has_hands = any(item.get("hands", "") for item in items)
        has_protects = any(
            item.get("protects", "") or item.get("protects_ja", "")
            for item in items)
        has_weight = any(item.get("weight", "") for item in items)
        has_price = any(item.get("price_display", "") for item in items)
        self._facility_header_hands.setText(
            "保護部位" if has_protects else "持ち手")
        self._facility_header_hands.setVisible(has_hands or has_protects)
        self._facility_header_weight.setVisible(has_weight)
        self._facility_header_price.setVisible(has_price)
        self._render_price_rows(
            self._facility_list_rows_layout, items,
            show_price=has_price)

    def set_facility_list_title(self, title: str) -> None:
        """施設専用 L4 一覧パネルのタイトルを更新する。"""
        self._facility_list_group.setTitle(title)

    def set_shop_buy_title(self, title: str) -> None:
        """店アイテム一覧パネルのグループボックスタイトルを更新する。"""
        self._shop_buy_group.setTitle(title)

    def _on_equip_toggle(self, key: str, col_idx: int, checked: bool) -> None:
        self._equip_table.setColumnHidden(col_idx, not checked)
        cols = dict(settings.get("equipment_columns", {}))
        cols[key] = checked
        settings.set_val("equipment_columns", cols)

    def set_equipment_panel_title(self, title: str) -> None:
        """装備/呪文パネルのグループボックスタイトルを更新する（b38）。"""
        self._equip_group.setTitle(title)

    @staticmethod
    def _spell_effect_details_for_display(data: dict) -> list[dict]:
        details = [
            d for d in (data.get("effect_details") or [])
            if isinstance(d, dict) and d.get("effect_en")
        ]
        if details:
            return details
        effect_en = data.get("effect_en", "")
        if effect_en and effect_en != "(none)":
            return [{
                "effect_en": effect_en,
                "effect_ja": data.get("effect_ja", ""),
                "text_en": data.get("text_en", ""),
                "text_ja": data.get("text_ja", ""),
            }]
        return []

    @staticmethod
    def _spell_effect_ja_text(text_en: str, text_ja: str) -> str:
        if text_ja:
            return text_ja
        return "(テンプレート未登録)" if text_en else "—"

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            child = layout.takeAt(0)
            widget = child.widget()
            if widget:
                widget.deleteLater()

    def _add_spell_effect_card(self, detail: dict) -> None:
        card = QFrame()
        card.setObjectName("spellEffectCard")
        card.setStyleSheet(
            "QFrame#spellEffectCard {"
            "  background: #17293a;"
            "  border: 1px solid #2a4258;"
            "  border-radius: 4px;"
            "}"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(8, 7, 8, 8)
        lay.setSpacing(4)

        effect_en = detail.get("effect_en", "") or "—"
        effect_ja = detail.get("effect_ja", "") or "—"
        title_text = (
            f"{effect_en}  {effect_ja}"
            if effect_en != effect_ja else effect_en
        )
        title = QLabel(title_text)
        title.setWordWrap(True)
        title.setStyleSheet(
            "QLabel { color: #c9d1e0; font-size: 12px; font-weight: bold; }")
        lay.addWidget(title)
        lay.addSpacing(4)

        text_en = detail.get("text_en", "") or ""
        text_ja = detail.get("text_ja", "") or ""
        en_label = QLabel(text_en or "—")
        en_label.setWordWrap(True)
        en_label.setStyleSheet(
            "QLabel { color: #c9d1e0; font-size: 12px; }")
        lay.addWidget(en_label)

        ja_label = QLabel(self._spell_effect_ja_text(text_en, text_ja))
        ja_label.setWordWrap(True)
        ja_label.setStyleSheet(
            "QLabel { color: #a0c4d8; font-size: 11px; }")
        lay.addWidget(ja_label)
        self._sd_effect_cards_layout.addWidget(card)

    def _render_spell_effect_cards(self, details: list[dict]) -> None:
        layout = self._sd_effect_cards_layout
        self._clear_layout(layout)
        if not details:
            none = QLabel("—")
            none.setStyleSheet("QLabel { color: #c9d1e0; font-size: 12px; }")
            layout.addWidget(none)
            layout.addStretch(1)
            return
        for detail in details:
            self._add_spell_effect_card(detail)
        layout.addStretch(1)

    def update_spell_detail(self, data: dict) -> None:
        """呪文詳細パネルを更新する（b49）。

        data はゲーム内 SPELLBOOK 詳細画面の全項目を含む辞書:
          name(_en/_ja), cost, target_en/_ja, element_en/_ja,
          effect_en/_ja, text_en, player_name, player_level, player_gold
        """
        # プレイヤー情報
        self._sd_player_name.setText(data.get("player_name", "") or "—")
        gold = data.get("player_gold", 0)
        self._sd_player_balance.setText(str(gold) if gold else "—")
        level = data.get("player_level", 0)
        self._sd_player_level.setText(str(level) if level else "—")
        # Spell Cost は学習/購入コスト、Casting Cost は詠唱コスト。
        # SpellData +0x32 の raw cost は Spell Cost の半分として扱われるため、
        # 呼び出し側から明示された spell_cost / casting_cost を優先する。
        raw_cost = data.get("cost", 0)
        cast_cost = data.get("casting_cost", raw_cost)
        spell_cost = data.get("spell_cost")
        if spell_cost:
            self._sd_spell_cost.setText(str(spell_cost))
        else:
            self._sd_spell_cost.setText(
                str(raw_cost * 2) if raw_cost else "—")

        # 呪文名
        self._sd_name_en.setText(data.get("name", "") or "—")
        self._sd_name_ja.setText(data.get("name_ja", "") or "—")

        # Save Vs. = element
        elem_en = data.get("element_en", "")
        elem_ja = data.get("element_ja", "")
        if elem_en:
            self._sd_save_vs.setText(f"{elem_en} ({elem_ja})")
        else:
            self._sd_save_vs.setText("—")

        # Target
        tgt_en = data.get("target_en", "")
        tgt_ja = data.get("target_ja", "")
        if tgt_en:
            self._sd_target.setText(f"{tgt_en} ({tgt_ja})")
        else:
            self._sd_target.setText("—")

        # Casting Cost
        self._sd_cost_lbl.setText(str(cast_cost) if cast_cost else "—")

        self._render_spell_effect_cards(
            self._spell_effect_details_for_display(data))

    def update_load_screen_slots(self, slots: list) -> None:
        """ロード画面テーブルをセーブスロット情報で更新する。"""
        render_load_screen_slots(self._load_table, slots)

    def panel_mode(self) -> str:
        return self._panel_mode

    def select_class_in_list(self, en_name: str) -> None:
        self._class_list_panel.select_class(en_name)

    def set_chargen_active(self, active: bool) -> None:
        """キャラ作成中はゲーム状態行を隠す（位置・座標等に意味が無いため）。"""
        self._gs_group.setVisible(not active)

    def appearance_faces_panel(self) -> AppearanceFacesPanel:
        """外見選択時の顔候補パネルへの参照を返す。"""
        return self._appearance_faces_panel

    def attributes_panel(self) -> AttributesPanel:
        """choose_attributes モードで使う AttributesPanel への参照を返す。
        assist_window 側で memory target を渡したり race/class を反映したりする。
        ステータスタブと 1 インスタンスを共有する。
        """
        return self._attributes_panel

    def mount_attributes_panel(self) -> None:
        """共有 AttributesPanel を本タブの slot へ取り込む (reparent)。

        翻訳タブが choose_attributes / fallback_status を表示するとき、
        assist_window から呼ばれて実体を index 2 の slot に移す。
        """
        if self._attributes_panel.parent() is not self._attr_slot:
            self._attr_slot.layout().addWidget(self._attributes_panel)
