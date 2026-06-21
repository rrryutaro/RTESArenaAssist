"""screen_detector_play_dungeon.py — ダンジョン探索中の画面検出

ダンジョン（および当面はフィールドも含む）固有の Priority 3〜4。
共通判定（Priority 1〜2）が None を返した後に呼ばれる。

判定対象:
  - system_menu      : OP.IMG + MENU_ACTIVE=0 連続 2 ポーリング
  - loadsave_in_play : LOADSAVE.IMG + MENU_ACTIVE=0 連続 2 ポーリング
                       （ロードデータ選択中。SCREEN_IMG 残留中も
                        menu_active 変化で離脱を検出するため screen_id 経由で判定）
  - game_screen      : 既定（探索中）

街固有の NPC 会話判定（CITY_NPC_ACTIVE_OFFSET 等）はこのファイルに
**絶対に持ち込まない**。街向け修正がダンジョン判定に影響しない構造を保つ。
"""
from __future__ import annotations
from typing import Tuple

from screen_detector import (
    _tr,
    MENU_ACTIVE_OFFSET,
    _read_u16_le,
)


def detect_dungeon_play_screen(
    analyzer,
    anchor: int,
    img_name: str,
    menu_active_was_zero: bool = False,
) -> Tuple[str, str]:
    """ダンジョン/フィールドでの Priority 3〜4 を判定する。"""
    img_upper = (img_name or "").upper()
    menu_active = _read_u16_le(analyzer, anchor + MENU_ACTIVE_OFFSET)

    # ── Priority 3: システムメニュー ──
    # OP.IMG + menu_active=0 は探索画面 idle pulse でも一時的に成立するため、
    # 連続 2 ポーリング同値（menu_active_was_zero=True）を要求する。
    if (img_upper == "OP.IMG"
            and menu_active == 0
            and menu_active_was_zero):
        return ("system_menu", _tr("system_menu"))

    # ── Priority 3.5: ロードデータ選択中 ──
    # LOADSAVE.IMG 表示中 + menu_active 連続 2 poll 0 安定でロードデータ選択中。
    # システムメニュー (OP.IMG) と同じパターンで判定し、SCREEN_IMG 残留中も
    # menu_active 変化で離脱を検出できるようにする。
    if (img_upper == "LOADSAVE.IMG"
            and menu_active == 0
            and menu_active_was_zero):
        return ("loadsave_in_play", _tr("loadsave_in_play"))

    # ── Priority 4: 既定（探索中） ──
    return ("game_screen", _tr("game_screen"))
