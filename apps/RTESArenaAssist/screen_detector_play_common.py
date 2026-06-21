"""screen_detector_play_common.py — normal-play 共通検出（area 非依存）

area に依存しない判定を共通化:
  - Priority 1: キャラクターポップアップ family
                （status / equipment / spellbook / spell_detail / bonus_screen）
  - Priority 2: 汎用 popup（automap / logbook）

area 固有判定（system_menu / npc_dialog / game_screen の最終分岐）は
screen_detector_play_dungeon / _city へ振り分ける。
"""
from __future__ import annotations
from typing import Optional, Tuple

from screen_detector import (
    _tr,
    FLAG_STATUS_POPUP_OFFSET,
    FLAG_EQUIPMENT_OPEN_OFFSET,
    POPUP_OPEN_OFFSET,
    _read_u8,
)


def detect_common_play_screen(
    analyzer,
    anchor: int,
    img_name: str,
) -> Optional[Tuple[str, str]]:
    """area 非依存の Priority 1〜2 を判定する。

    判定できれば (screen_id, display_name) を返し、できなければ None を返す。
    None の場合、呼び出し側 dispatcher が area 固有の Priority 3〜4 を実行する。
    """
    img_upper = (img_name or "").upper()

    flag_status       = _read_u8(analyzer, anchor + FLAG_STATUS_POPUP_OFFSET)
    flag_equipment    = _read_u8(analyzer, anchor + FLAG_EQUIPMENT_OPEN_OFFSET)
    popup_open        = _read_u8(analyzer, anchor + POPUP_OPEN_OFFSET)

    # ── Priority 1: キャラクターポップアップ family ──
    # flag_status=1 はキャラクターポップアップ（status/equipment/spellbook/
    # spell_detail/bonus_screen）専用。system_menu / automap / logbook では 0。
    # 前提: normal-play 状態でのみ呼ばれる（dispatcher が保証）。
    # chargen 中も flag_status が変動することが観測されているが、dispatcher 構造で
    # chargen 中は本関数が呼ばれないため誤検出は発生しない。
    if flag_status == 1:
        if img_upper == "PAGE2.IMG":
            return ("status_page", _tr("status_page"))
        if img_upper == "CHARSTAT.IMG":
            return ("bonus_screen", _tr("bonus_screen"))
        if flag_equipment == 1:
            return ("equipment", _tr("equipment"))
        # flag_equipment=0 配下は魔法画面 family（一覧/詳細/名称変更）。
        # SPELL_VIEW (+0x8F6E) の絶対値はロード毎に変わり、一覧/詳細はその差
        # （観測: 一覧-詳細=0x54）で区別される。base（突入時=一覧値）が必要なため、
        # ここでは spellbook を返し、poll_controller が突入時の値を捕捉して
        # 詳細/名称変更を判別する。
        return ("spellbook", _tr("spellbook"))

    # ── Priority 2: 汎用 popup（automap / logbook） ──
    # popup_open=1 はキャラクターポップアップ + automap + logbook で立つ。
    # ここまで来ていれば flag_status=0 なのでキャラポップアップではない。
    if popup_open == 1:
        if img_upper == "LOGBOOK.IMG":
            return ("logbook", _tr("logbook"))
        if img_upper in ("AUTOMAP.IMG", "POINTER.IMG"):
            return ("automap", _tr("automap"))
        # 不明 IMG での popup_open=1 → area 固有判定にフォールスルー

    return None
