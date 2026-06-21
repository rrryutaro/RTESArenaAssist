"""spell_view.py — 魔法一覧 / 魔法詳細 / 名称変更 の判別 pure helper。

SPELL_VIEW (+0x8F6E) の絶対値はロード毎に変わるが、ロード内では
一覧 / 詳細 / 名称変更 が固定の差でセットになる (観測, 数回再現):

  一覧 - 詳細     = 0x54
  一覧 - 名称変更 = 0x9F   (= 詳細 - 名称変更 = 0x4B)

魔法画面に突入した瞬間は一覧なので、その値を base (一覧値) として捕捉し、
base からの差 (mod 256) で詳細 / 名称変更 を判別する。

window / analyzer の時系列状態に触れない pure helper にして単体テストできる
ようにする (map_safe_coord / char_screen_page と同方針)。値の関係は観測ベースの
仮説であり、ロードに依らず成立するかは実機で継続確認する。
"""
from __future__ import annotations

from typing import Optional

SPELL_VIEW_DELTA_DETAIL = 0x54   # 一覧 - 詳細
SPELL_VIEW_DELTA_RENAME = 0x9F   # 一覧 - 名称変更


def classify_spell_view(spell_view: int, base: Optional[int]) -> str:
    """SPELL_VIEW 値から魔法画面のサブ状態を返す。

    Args:
      spell_view: 現在の +0x8F6E の値。
      base:       魔法画面突入時に捕捉した一覧値 (None=未捕捉)。

    Returns:
      "spell_detail" (詳細 / 名称変更) または "spellbook" (一覧 / 過渡)。
    """
    if base is None:
        return "spellbook"
    delta = (base - spell_view) & 0xFF
    if delta in (SPELL_VIEW_DELTA_DETAIL, SPELL_VIEW_DELTA_RENAME):
        return "spell_detail"
    return "spellbook"


def classify_spell_screen(screen_id: str, img_name: str,
                          spell_view: int,
                          base: Optional[int],
                          *,
                          previous_screen_id: str | None = None,
                          flag_spell_detail: int | None = None,
                          spell_name: str = "") -> str:
    """screen_id と spell family の補助信号から最終 ID を返す。"""
    _ = (img_name, previous_screen_id, spell_name)
    if screen_id != "spellbook":
        return screen_id

    if base is None:
        if flag_spell_detail == 0x00:
            return "spell_detail"
        return "spellbook"

    delta = (base - spell_view) & 0xFF
    if delta == 0:
        # 一覧復帰後も CHARBK / spell_name / effect text は残留する。
        # SPELL_VIEW が base と同じなら一覧を優先し、残留値では詳細へ戻さない。
        return "spellbook"

    if delta in (SPELL_VIEW_DELTA_DETAIL, SPELL_VIEW_DELTA_RENAME):
        return "spell_detail"

    if flag_spell_detail == 0xFF:
        return "spellbook"

    if flag_spell_detail == 0x00:
        # 0x54/0x9F 以外の delta でも、flag が詳細側なら詳細として扱う。
        # ただし delta==0 は上で一覧に固定済み。
        return "spell_detail"

    return "spellbook"


__all__ = [
    "classify_spell_view",
    "classify_spell_screen",
    "SPELL_VIEW_DELTA_DETAIL",
    "SPELL_VIEW_DELTA_RENAME",
]
