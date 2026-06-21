"""screen_detector_play_city.py — 街（IMPERIAL/CITY/TOWN/VILLAGE）の画面検出

街固有の Priority 3〜4。共通判定（Priority 1〜2）が None を返した後に呼ばれる。

街固有の挙動:
  - NPC 会話と system_menu がいずれも OP.IMG + MENU_ACTIVE=0 で観測される。
  - CITY_NPC_ACTIVE_OFFSET (0xA845) が NPC 会話中に非ゼロ、
    システムメニュー / 屋外で 0 を観測（観測ベースの仮説）。

判定対象:
  - system_menu      : OP.IMG + MENU_ACTIVE=0 連続 2 ポーリング + city_npc_active=0
  - npc_dialog       : OP.IMG + MENU_ACTIVE=0 連続 2 ポーリング + city_npc_active!=0
  - loadsave_in_play : LOADSAVE.IMG + MENU_ACTIVE=0 連続 2 ポーリング
                       （ロードデータ選択中。SCREEN_IMG 残留中も
                        menu_active 変化で離脱を検出するため screen_id 経由で判定）
  - game_screen      : 既定（屋外探索中）
"""
from __future__ import annotations
from typing import Tuple

from screen_detector import (
    _tr,
    MENU_ACTIVE_OFFSET,
    CITY_NPC_ACTIVE_OFFSET,
    _read_u16_le,
)


def detect_city_play_screen(
    analyzer,
    anchor: int,
    img_name: str,
    menu_active_was_zero: bool = False,
) -> Tuple[str, str]:
    """街での Priority 3〜4 を判定する。"""
    img_upper = (img_name or "").upper()
    menu_active = _read_u16_le(analyzer, anchor + MENU_ACTIVE_OFFSET)

    # ── Priority 3: システムメニュー / NPC 会話の弁別 ──
    if (img_upper == "OP.IMG"
            and menu_active == 0
            and menu_active_was_zero):
        city_npc_active = _read_u16_le(analyzer, anchor + CITY_NPC_ACTIVE_OFFSET)
        if city_npc_active != 0:
            return ("npc_dialog", _tr("npc_dialog"))
        return ("system_menu", _tr("system_menu"))

    # ── Priority 3.5: ロードデータ選択中 ──
    # LOADSAVE.IMG 表示中 + menu_active 連続 2 poll 0 安定でロードデータ選択中。
    # システムメニュー (OP.IMG) と同じパターンで判定し、SCREEN_IMG 残留中も
    # menu_active 変化で離脱を検出できるようにする。
    if (img_upper == "LOADSAVE.IMG"
            and menu_active == 0
            and menu_active_was_zero):
        return ("loadsave_in_play", _tr("loadsave_in_play"))

    # ── Priority 4: 既定（屋外探索中） ──
    return ("game_screen", _tr("game_screen"))
