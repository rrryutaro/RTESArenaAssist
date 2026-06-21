"""
tab_translate_ui.py — TabTranslate UI ビルダー

tab_translate.py の _build_ui 相当をモジュールレベル関数として保持する。
ロジック・スロット・スタック・シグナルハンドラはすべて tab_translate.py 本体に残す。

循環 import 禁止: このモジュールは tab_translate.py を import しない。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tabs.tab_translate import TabTranslate

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QGroupBox, QHeaderView, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSizePolicy, QStackedWidget, QTableWidget, QVBoxLayout, QWidget,
)

import assist_settings as settings
import i18n_helper as i18n

from class_list_panel import ClassListPanel
from race_list_panel import RaceListPanel
from appearance_faces_panel import AppearanceFacesPanel
from tabs.tab_map import TabMap


def build_ui(tab: "TabTranslate") -> None:
    """
    TabTranslate の UI を構築し、ウィジェット参照を tab に設定する。
    tab_translate.py の _build_ui から cut-paste（self → tab リネーム・インデント調整のみ）。
    """
    root = QVBoxLayout(tab)
    root.setContentsMargins(10, 10, 10, 10)
    root.setSpacing(8)

    # 未接続オーバーレイ
    tab._no_conn = QLabel(i18n.tr("translate.no_connection"))
    tab._no_conn.setAlignment(Qt.AlignmentFlag.AlignCenter)
    tab._no_conn.setWordWrap(True)
    tab._no_conn.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
    )
    root.addWidget(tab._no_conn)

    # 接続時コンテンツ（コンテナ）
    tab._conn_widget = QWidget()
    cl = QVBoxLayout(tab._conn_widget)
    cl.setContentsMargins(0, 0, 0, 0)
    cl.setSpacing(8)

    # モード切替用 QStackedWidget
    # 旧 ゲーム状態行 (場所/階数/方角/天気/座標) は廃止。マップタブ上部に集約。
    tab._stack = QStackedWidget()

    # ── 翻訳モード ─────────────────────────────────────────────
    translate_page = QWidget()
    tp_lay = QVBoxLayout(translate_page)
    tp_lay.setContentsMargins(0, 0, 0, 0)
    tp_lay.setSpacing(8)

    trans_group = QGroupBox(i18n.tr("translate.translation"))
    trans_lay = QVBoxLayout(trans_group)

    # 翻訳結果（長文 cinematic 等で溢れる場合はスクロール）
    tab._trans_val = QLabel(i18n.tr("translate.no_data"))
    tab._trans_val.setWordWrap(True)
    tab._trans_val.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
    tab._trans_val.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding
    )
    tab._trans_val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    from tts_read_aloud import attach_read_aloud as _attach_ra
    _attach_ra(tab._trans_val, tab._trans_val.text)
    tab._trans_scroll = QScrollArea()
    tab._trans_scroll.setWidget(tab._trans_val)
    tab._trans_scroll.setWidgetResizable(True)
    tab._trans_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    tab._trans_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    trans_lay.addWidget(tab._trans_scroll, 1)

    orig_lbl = QLabel(i18n.tr("translate.original") + ":")
    orig_lbl.setObjectName("subLabel")
    # 原文も同様にスクロール対応
    tab._orig_val = QLabel(i18n.tr("translate.no_data"))
    tab._orig_val.setWordWrap(True)
    tab._orig_val.setObjectName("dimLabel")
    tab._orig_val.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
    tab._orig_val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    _attach_ra(tab._orig_val, tab._orig_val.text)
    tab._orig_scroll = QScrollArea()
    tab._orig_scroll.setWidget(tab._orig_val)
    tab._orig_scroll.setWidgetResizable(True)
    tab._orig_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    tab._orig_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    tab._orig_scroll.setMinimumHeight(60)
    tab._orig_scroll.setMaximumHeight(180)
    trans_lay.addWidget(orig_lbl)
    trans_lay.addWidget(tab._orig_scroll)

    tp_lay.addWidget(trans_group, 1)

    # ── クラス一覧モード ───────────────────────────────────────
    tab._class_list_panel = ClassListPanel()

    # ── 種族一覧モード ────────────────────────
    tab._race_list_panel = RaceListPanel()

    # ── ChooseAttributes / fallback status モード ───────────────
    # AttributesPanel 実体は __init__ で受け取った共有インスタンス。
    # ここでは reparent 先となる slot だけを用意する (実体のマウントは
    # assist_window が mount_attributes_panel() 経由で行う)。
    tab._attr_slot = QWidget()
    _attr_slot_lay = QVBoxLayout(tab._attr_slot)
    _attr_slot_lay.setContentsMargins(0, 0, 0, 0)

    # ── Appearance Faces モード: chargen 外見選択時の顔候補表示
    tab._appearance_faces_panel = AppearanceFacesPanel()

    # ── ロード画面モード ───────────────────────────────────────
    load_page = QWidget()
    lp_lay = QVBoxLayout(load_page)
    lp_lay.setContentsMargins(0, 0, 0, 0)
    lp_lay.setSpacing(4)

    load_group = QGroupBox(i18n.tr("save.col_slots"))
    lg_lay = QVBoxLayout(load_group)
    lg_lay.setContentsMargins(4, 4, 4, 4)

    tab._load_table = QTableWidget(0, 4)
    tab._load_table.setHorizontalHeaderLabels([
        i18n.tr("save.col_slot"),
        i18n.tr("save.col_name"),
        i18n.tr("save.col_label"),
        i18n.tr("save.col_date"),
    ])
    tab._load_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    tab._load_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    tab._load_table.verticalHeader().setVisible(False)
    tab._load_table.horizontalHeader().setStretchLastSection(True)
    tab._load_table.horizontalHeader().setSectionResizeMode(
        0, QHeaderView.ResizeMode.ResizeToContents)
    tab._load_table.horizontalHeader().setSectionResizeMode(
        1, QHeaderView.ResizeMode.Stretch)
    tab._load_table.horizontalHeader().setSectionResizeMode(
        2, QHeaderView.ResizeMode.Stretch)
    lg_lay.addWidget(tab._load_table)
    lp_lay.addWidget(load_group, 1)

    # ── アイテム取得モード（b32）─────────────────────────────
    pickup_page = QWidget()
    pp_lay = QVBoxLayout(pickup_page)
    pp_lay.setContentsMargins(0, 0, 0, 0)
    pp_lay.setSpacing(4)

    pickup_group = QGroupBox("アイテム取得")
    pg_lay = QVBoxLayout(pickup_group)
    pg_lay.setContentsMargins(4, 4, 4, 4)
    pg_lay.setSpacing(2)

    # アイテム行を動的に追加するコンテナ
    tab._pickup_rows_widget = QWidget()
    tab._pickup_rows_layout = QVBoxLayout(tab._pickup_rows_widget)
    tab._pickup_rows_layout.setContentsMargins(0, 0, 0, 0)
    tab._pickup_rows_layout.setSpacing(2)
    tab._pickup_rows_layout.addStretch(1)

    pickup_scroll = QScrollArea()
    pickup_scroll.setWidget(tab._pickup_rows_widget)
    pickup_scroll.setWidgetResizable(True)
    pickup_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    pickup_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    pg_lay.addWidget(pickup_scroll, 1)

    tab._pickup_remaining = QLabel("")
    tab._pickup_remaining.setObjectName("dimLabel")
    pg_lay.addWidget(tab._pickup_remaining)

    pp_lay.addWidget(pickup_group, 1)

    # ── 装備画面モード ────────────────────────────
    equip_page = QWidget()
    ep_lay = QVBoxLayout(equip_page)
    ep_lay.setContentsMargins(0, 0, 0, 0)
    ep_lay.setSpacing(4)

    tab._equip_group = QGroupBox("装備品一覧")
    eg_lay = QVBoxLayout(tab._equip_group)
    eg_lay.setContentsMargins(4, 4, 4, 4)
    eg_lay.setSpacing(2)

    # 列表示切替ボタン行（col0 "装" を含む全8列をトグル）
    _TOGGLE_DEFS = [
        ("equipped_mark", "装",    0),
        ("identified",    "鑑",    1),
        ("slot",          "部位",  2),
        ("en",            "原文名", 3),
        ("ja",            "翻訳名", 4),
        ("weight",        "重量",  5),
        ("condition",     "状態",  6),
        ("effect",        "性能",  7),
    ]
    tab._equip_col_btns: dict = {}
    equip_cols = settings.get("equipment_columns", {})

    toggle_row = QHBoxLayout()
    toggle_row.setSpacing(2)
    toggle_row.setContentsMargins(0, 0, 0, 0)
    for key, label, col_idx in _TOGGLE_DEFS:
        btn = QPushButton(label)
        btn.setCheckable(True)
        btn.setChecked(bool(equip_cols.get(key, True)))
        btn.setFixedHeight(20)
        btn.setStyleSheet(
            "QPushButton { font-size: 10px; padding: 1px 4px;"
            " background: #1a2635; color: #7ab8d4;"
            " border: 1px solid #2a4258; border-radius: 2px; }"
            "QPushButton:checked { background: #1f3d5a; color: #c9d1e0; }"
            "QPushButton:!checked { background: #0e161e; color: #4a5a6a; }"
        )
        btn.toggled.connect(
            lambda checked, k=key, c=col_idx: tab._on_equip_toggle(k, c, checked))
        toggle_row.addWidget(btn)
        tab._equip_col_btns[key] = (col_idx, btn)
    toggle_row.addStretch(1)
    eg_lay.addLayout(toggle_row)

    # 8列テーブル（装/鑑/部位/原文名/翻訳名/重量/状態/性能）
    tab._equip_table = QTableWidget(0, 8)
    tab._equip_table.setHorizontalHeaderLabels(
        ["装", "鑑", "部位", "原文名", "翻訳名", "重量", "状態", "性能"])
    tab._equip_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    tab._equip_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    tab._equip_table.setAlternatingRowColors(True)
    tab._equip_table.verticalHeader().setVisible(False)
    hdr = tab._equip_table.horizontalHeader()
    hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
    hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
    hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
    hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
    hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
    hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
    hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
    hdr.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
    tab._equip_table.setColumnWidth(0, 22)
    tab._equip_table.setColumnWidth(1, 22)
    tab._equip_table.setStyleSheet(
        "QTableWidget {"
        "  background: #131c24;"
        "  alternate-background-color: #1a2635;"
        "  gridline-color: #2a4258;"
        "  color: #c9d1e0;"
        "  border: none;"
        "}"
        "QTableWidget::item:selected { background: #1f3d5a; }"
        "QHeaderView::section {"
        "  background: #0e161e;"
        "  color: #7ab8d4;"
        "  border: 1px solid #2a4258;"
        "  padding: 3px 6px;"
        "  font-size: 10px;"
        "}"
    )
    for key, (col_idx, btn) in tab._equip_col_btns.items():
        if not btn.isChecked():
            tab._equip_table.setColumnHidden(col_idx, True)
    eg_lay.addWidget(tab._equip_table, 1)

    ep_lay.addWidget(tab._equip_group, 1)

    # ── 呪文詳細モード ─ ゲーム内 SPELLBOOK パーチメントの構成を再現
    spell_detail_page = QWidget()
    sd_lay = QVBoxLayout(spell_detail_page)
    sd_lay.setContentsMargins(0, 0, 0, 0)
    sd_lay.setSpacing(4)

    tab._spell_detail_group = QGroupBox("呪文詳細 (SPELLBOOK)")
    sdg_lay = QVBoxLayout(tab._spell_detail_group)
    sdg_lay.setContentsMargins(8, 8, 8, 8)
    sdg_lay.setSpacing(4)

    # 共通スタイル
    _LBL_HEAD = "QLabel { color: #7ab8d4; font-size: 11px; font-weight: bold; }"
    _LBL_VAL  = "QLabel { color: #c9d1e0; font-size: 12px; }"
    _LBL_VAL_JA = "QLabel { color: #a0c4d8; font-size: 12px; }"

    def _make_row():
        row = QHBoxLayout()
        row.setSpacing(8)
        return row

    def _add_field(row, head_text, val_widget):
        head = QLabel(head_text)
        head.setStyleSheet(_LBL_HEAD)
        head.setMinimumWidth(130)
        head.setMaximumWidth(220)
        row.addWidget(head)
        row.addWidget(val_widget, 1)

    # ── プレイヤー情報行（Name / Balance / Level / Spell Cost）──
    # ゲーム画面は左上に Name/Level、右上に Balance/Spell Cost を表示
    row1 = _make_row()
    tab._sd_player_name = QLabel("")
    tab._sd_player_name.setStyleSheet(_LBL_VAL)
    _add_field(row1, "Name / 名前:", tab._sd_player_name)
    tab._sd_player_balance = QLabel("")
    tab._sd_player_balance.setStyleSheet(_LBL_VAL)
    _add_field(row1, "Balance / 残高:", tab._sd_player_balance)
    sdg_lay.addLayout(row1)

    row2 = _make_row()
    tab._sd_player_level = QLabel("")
    tab._sd_player_level.setStyleSheet(_LBL_VAL)
    _add_field(row2, "Level / レベル:", tab._sd_player_level)
    tab._sd_spell_cost = QLabel("")
    tab._sd_spell_cost.setStyleSheet(_LBL_VAL)
    _add_field(row2, "Spell Cost / 呪文コスト:", tab._sd_spell_cost)
    sdg_lay.addLayout(row2)

    # 区切り
    sep1 = QFrame()
    sep1.setFrameShape(QFrame.Shape.HLine)
    sep1.setStyleSheet("QFrame { color: #2a4258; }")
    sdg_lay.addWidget(sep1)

    # ── 呪文名 / Save Vs.（JA は EN の右に横並び表示 b50）──
    row3 = _make_row()
    tab._sd_name_en = QLabel("")
    tab._sd_name_en.setStyleSheet(
        "QLabel { color: #c9d1e0; font-size: 14px; font-weight: bold; }")
    tab._sd_name_ja = QLabel("")
    tab._sd_name_ja.setStyleSheet(
        "QLabel { color: #a0c4d8; font-size: 13px; }")
    name_box = QHBoxLayout()
    name_box.setSpacing(8)
    name_box.addWidget(tab._sd_name_en)
    name_box.addWidget(tab._sd_name_ja, 1)
    name_wrapper = QWidget()
    name_wrapper.setLayout(name_box)
    _add_field(row3, "Spell Name / 呪文名:", name_wrapper)
    tab._sd_save_vs = QLabel("")
    tab._sd_save_vs.setStyleSheet(_LBL_VAL)
    _add_field(row3, "Save Vs. / セーブ:", tab._sd_save_vs)
    sdg_lay.addLayout(row3)

    # ── Target / Casting Cost ──
    row4 = _make_row()
    tab._sd_target = QLabel("")
    tab._sd_target.setStyleSheet(_LBL_VAL)
    _add_field(row4, "Target / 対象:", tab._sd_target)
    tab._sd_cost_lbl = QLabel("")
    tab._sd_cost_lbl.setStyleSheet(_LBL_VAL)
    _add_field(row4, "Casting Cost / 詠唱コスト:", tab._sd_cost_lbl)
    sdg_lay.addLayout(row4)

    # 区切り
    sep2 = QFrame()
    sep2.setFrameShape(QFrame.Shape.HLine)
    sep2.setStyleSheet("QFrame { color: #2a4258; }")
    sdg_lay.addWidget(sep2)

    # ── Effects ──
    eff_caption = QLabel("Effects / 効果:")
    eff_caption.setStyleSheet(_LBL_HEAD)
    sdg_lay.addWidget(eff_caption)

    tab._sd_effect_cards_widget = QWidget()
    tab._sd_effect_cards_layout = QVBoxLayout(tab._sd_effect_cards_widget)
    tab._sd_effect_cards_layout.setContentsMargins(0, 0, 0, 0)
    tab._sd_effect_cards_layout.setSpacing(6)
    sdg_lay.addWidget(tab._sd_effect_cards_widget)

    sdg_lay.addStretch(1)
    sd_lay.addWidget(tab._spell_detail_group, 1)

    # ── 場所一覧 / 詳細場所一覧モード ────────────────────────────
    place_page = QWidget()
    plp_lay = QVBoxLayout(place_page)
    plp_lay.setContentsMargins(0, 0, 0, 0)
    plp_lay.setSpacing(4)

    tab._place_list_group = QGroupBox("")
    plg_lay = QVBoxLayout(tab._place_list_group)
    plg_lay.setContentsMargins(4, 4, 4, 4)
    plg_lay.setSpacing(2)

    tab._place_rows_widget = QWidget()
    tab._place_rows_layout = QVBoxLayout(tab._place_rows_widget)
    tab._place_rows_layout.setContentsMargins(0, 0, 0, 0)
    tab._place_rows_layout.setSpacing(2)
    tab._place_rows_layout.addStretch(1)

    place_scroll = QScrollArea()
    place_scroll.setWidget(tab._place_rows_widget)
    place_scroll.setWidgetResizable(True)
    place_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    place_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    plg_lay.addWidget(place_scroll, 1)

    plp_lay.addWidget(tab._place_list_group, 1)

    # ── 店アイテム一覧モード (shop_buy) ─────────────────
    # 店主メニュー「Buy Drinks」等の選択後に表示されるアイテム一覧。
    # 独自タイトル「店アイテム一覧」と
    # 列ヘッダー「原文 / 翻訳 / 金額」は出さない。bullet も出さない。
    # データ行 (原文 / 翻訳 / 金額) のみを並べる。
    shop_buy_page = QWidget()
    sb_lay = QVBoxLayout(shop_buy_page)
    sb_lay.setContentsMargins(0, 0, 0, 0)
    sb_lay.setSpacing(4)

    # タイトル空 (GroupBox の枠だけ残す、見出し非表示)
    tab._shop_buy_group = QGroupBox("")
    sbg_lay = QVBoxLayout(tab._shop_buy_group)
    sbg_lay.setContentsMargins(4, 4, 4, 4)
    sbg_lay.setSpacing(2)

    # 列ヘッダー (原文 / 翻訳 / 金額) は表示しない。
    # ゲーム画面に表示されていない見出しは出さない。

    tab._shop_buy_rows_widget = QWidget()
    tab._shop_buy_rows_layout = QVBoxLayout(tab._shop_buy_rows_widget)
    tab._shop_buy_rows_layout.setContentsMargins(0, 0, 0, 0)
    tab._shop_buy_rows_layout.setSpacing(2)
    tab._shop_buy_rows_layout.addStretch(1)

    shop_buy_scroll = QScrollArea()
    shop_buy_scroll.setWidget(tab._shop_buy_rows_widget)
    shop_buy_scroll.setWidgetResizable(True)
    shop_buy_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    shop_buy_scroll.setHorizontalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    sbg_lay.addWidget(shop_buy_scroll, 1)

    sb_lay.addWidget(tab._shop_buy_group, 1)

    # ── 施設専用 L4 一覧モード (facility_list) ─────────────
    # 武具店/魔術師ギルド等の一覧。宿屋 shop_buy とは別ページ・別 layout に
    # 描画し (= 完全分離)、共有するのは純粋な行描画 helper のみ。
    facility_list_page = QWidget()
    fl_lay = QVBoxLayout(facility_list_page)
    fl_lay.setContentsMargins(0, 0, 0, 0)
    fl_lay.setSpacing(4)
    tab._facility_list_group = QGroupBox("")
    flg_lay = QVBoxLayout(tab._facility_list_group)
    flg_lay.setContentsMargins(4, 4, 4, 4)
    flg_lay.setSpacing(2)

    tab._facility_list_header = QFrame()
    tab._facility_list_header.setObjectName("shopItemHeader")
    flh_lay = QHBoxLayout(tab._facility_list_header)
    flh_lay.setContentsMargins(8, 2, 8, 2)
    flh_lay.setSpacing(8)
    # 鑑定マーカー列（ShopItemRow の "?" 列と同じ固定幅・stretch0 でヘッダーを揃える）
    tab._facility_header_mark = QLabel("")
    tab._facility_header_mark.setFixedWidth(16)
    tab._facility_header_en = QLabel("原文名")
    tab._facility_header_ja = QLabel("翻訳名")
    tab._facility_header_hands = QLabel("持ち手")
    tab._facility_header_weight = QLabel("重量")
    tab._facility_header_price = QLabel("価格")
    for lbl, stretch, align in (
            (tab._facility_header_mark, 0,
             Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter),
            (tab._facility_header_en, 2,
             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            (tab._facility_header_ja, 2,
             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            (tab._facility_header_hands, 1,
             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            (tab._facility_header_weight, 1,
             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            (tab._facility_header_price, 1,
             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
    ):
        lbl.setAlignment(align)
        lbl.setObjectName("shopItemHeaderLabel")
        flh_lay.addWidget(lbl, stretch)
    tab._facility_list_header.setStyleSheet(
        "QFrame#shopItemHeader {"
        "  background: #0e161e;"
        "  border: 1px solid #2a4258;"
        "  border-radius: 3px;"
        "}"
        "QFrame#shopItemHeader QLabel#shopItemHeaderLabel {"
        "  color: #7ab8d4;"
        "  background: transparent;"
        "  border: none;"
        "  font-size: 10px;"
        "  font-weight: bold;"
        "}"
    )
    flg_lay.addWidget(tab._facility_list_header)

    tab._facility_list_rows_widget = QWidget()
    tab._facility_list_rows_layout = QVBoxLayout(
        tab._facility_list_rows_widget)
    tab._facility_list_rows_layout.setContentsMargins(0, 0, 0, 0)
    tab._facility_list_rows_layout.setSpacing(2)
    tab._facility_list_rows_layout.addStretch(1)
    facility_list_scroll = QScrollArea()
    facility_list_scroll.setWidget(tab._facility_list_rows_widget)
    facility_list_scroll.setWidgetResizable(True)
    facility_list_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    facility_list_scroll.setHorizontalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    flg_lay.addWidget(facility_list_scroll, 1)
    fl_lay.addWidget(tab._facility_list_group, 1)

    # 翻訳タブ全域に表示するフォールバック用マップ画面 (= ステータスタブ/マップタブと
    # 同じ内容を翻訳タブで表示)。ステータス画面側は _attributes_panel を共有する。
    tab._fallback_map_tab = TabMap(name="fallback_map")

    tab._stack.addWidget(translate_page)               # index 0: translate
    tab._stack.addWidget(tab._class_list_panel)       # index 1: class list
    tab._stack.addWidget(tab._attr_slot)              # index 2: choose attrs / fallback status (共有パネルの slot)
    tab._stack.addWidget(load_page)                    # index 3: load screen
    tab._stack.addWidget(pickup_page)                  # index 4: item pickup
    tab._stack.addWidget(equip_page)                   # index 5: equipment
    tab._stack.addWidget(spell_detail_page)            # index 6: spell detail
    tab._stack.addWidget(tab._race_list_panel)        # index 7: race list
    tab._stack.addWidget(place_page)                   # index 8: place list
    tab._stack.addWidget(shop_buy_page)                # index 9: shop buy
    tab._stack.addWidget(tab._appearance_faces_panel) # index 10: appearance faces
    tab._stack.addWidget(tab._fallback_map_tab)       # index 11: fallback map
    tab._stack.addWidget(facility_list_page)           # index 12: facility list

    cl.addWidget(tab._stack, 1)
    root.addWidget(tab._conn_widget)
