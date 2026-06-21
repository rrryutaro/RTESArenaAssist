"""screen_detector_play.py — normal-play 画面検出 dispatcher

階層構造（「normal-play」直下）:
  1. 共通判定（screen_detector_play_common）
       Priority 1: キャラクターポップアップ family
       Priority 2: 汎用 popup（automap / logbook）
       → 該当すれば即返す（area 非依存）
  2. area 固有判定（MIF 名から detect_play_area で振り分け）
       - city      → screen_detector_play_city
       - dungeon   → screen_detector_play_dungeon
       - wilderness→ screen_detector_play_dungeon（ダンジョンと同判定）
       - unknown   → screen_detector_play_dungeon（安全側 / 既定の探索中扱い）

街向け修正（NPC 会話等）はすべて screen_detector_play_city に閉じ込め、
ダンジョン判定への副作用が構造的に発生しないことを保証する。

dispatcher により本判定が呼ばれる前提条件:
- top_level_state == "normal-play"
- chargen_hint が None
- boot IMG（QUOTE / SCROLL / MENU / LOADSAVE / INTRO\\*.IMG）に該当しない
"""
from __future__ import annotations
from typing import Tuple

from play_area_classifier import detect_play_area
from screen_detector_play_common import detect_common_play_screen
from screen_detector_play_city import detect_city_play_screen
from screen_detector_play_dungeon import detect_dungeon_play_screen


def detect_play_screen(
    analyzer,
    anchor: int,
    img_name: str,
    mif_name: str = "",
    menu_active_was_zero: bool = False,
    area: str | None = None,
) -> Tuple[str, str]:
    """通常プレイ画面を検出する dispatcher。

    Args:
        analyzer:             アタッチ済み ArenaMemoryAnalyzer
        anchor:               アンカーアドレス
        img_name:             現在の screen_img 値
        mif_name:             現在の LiveMifName / MifName（area 判定用）
        menu_active_was_zero: 直前 poll の menu_active も 0 だったか

    Returns:
        (screen_id, display_name) のタプル
    """
    # ── 1. area 非依存の共通判定（Priority 1〜2）──
    common = detect_common_play_screen(analyzer, anchor, img_name)
    if common is not None:
        return common

    # ── 2. area 固有判定（Priority 3〜4）──
    # 単一ソース: poll 確定の保持 area を優先消費する (全消費者が同じ値を見る
    # 1軸化)。area が注入されない (None) ときだけ互換 fallback で自前判定する。
    if area is None:
        area = detect_play_area(analyzer, anchor, mif_name)
    if area == "city":
        return detect_city_play_screen(
            analyzer, anchor, img_name,
            menu_active_was_zero=menu_active_was_zero,
        )
    # dungeon / wilderness / unknown は当面 dungeon と同判定
    return detect_dungeon_play_screen(
        analyzer, anchor, img_name,
        menu_active_was_zero=menu_active_was_zero,
    )
