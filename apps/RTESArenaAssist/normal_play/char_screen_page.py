"""char_screen_page.py — キャラクター画面 (ステータス画面) の page 過渡吸収。

ステータス画面は 1 つの分離であり、内部に ステータス / アイテム一覧 /
魔法一覧 / 魔法詳細 のページを持つ。ゲームは画面を開く瞬間に紙人形 img
(0EQUIP.CIF) を先に出すため、page 検出が一瞬 equipment に倒れてチラつく。

開いた直後 (settling=True) は、実際のステータスページ (status_page) が
現れるまで status_page を表示し、開く途中の equipment / spellbook 等の
過渡を抑える。想定外に status_page が現れない場合の保険として budget を
持ち、尽きたら抑制を解除する。

window / analyzer の時系列状態に触れない pure helper にして単体テストできる
ようにする (map_safe_coord と同方針)。
"""
from __future__ import annotations

from typing import Tuple


def settle_char_page(detected: str, settling: bool,
                     budget: int) -> Tuple[str, bool, int]:
    """キャラクター画面の page 過渡を吸収する pure helper。

    Args:
      detected: 今 poll に検出した page
                (status_page / equipment / spellbook / spell_detail)。
      settling: 開いた直後の抑制中フラグ。
      budget:   抑制を続ける残りポール数 (保険)。

    Returns:
      (表示する page, 新しい settling, 新しい budget)
    """
    if not settling:
        return (detected, False, budget)
    if detected == "status_page":
        # 実際のステータスページが現れた → 抑制解除
        return ("status_page", False, 0)
    if budget <= 0:
        # 保険: 想定外に status_page が来ない (直接 equipment 等で開く等)
        # → 抑制解除して検出値をそのまま表示
        return (detected, False, 0)
    # 抑制中: 開く途中の過渡 (equipment / spellbook 等) を status_page に置換
    return ("status_page", True, budget - 1)


__all__ = ["settle_char_page"]
