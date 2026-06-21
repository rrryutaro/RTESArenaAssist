"""play_area_classifier.py — 探索エリア種別判定（normal-play 階層）

normal-play 中のエリア種別を MIF 名から純粋関数で判定する。
画面検出 dispatcher（screen_detector_play）と _screen_name 装飾の双方で使用。
"""
from __future__ import annotations
from typing import Literal, Optional

import i18n_helper as _i18n


# 現在 active な location の wilderness 補助フラグを保持するメモリ位置
# (= anchor 相対 offset)。+0x4BD0 が 0x01 のとき wilderness とみなす
# (= 仮説扱い、観測複数回)。MIF 名先確定後の補助判定に使う。
_WILDERNESS_FLAG_OFFSET = 0x4BD0

PlayArea = Literal["city", "dungeon", "wilderness", "unknown"]


def classify_play_area(mif_name: str | None) -> PlayArea:
    """MIF 名から探索エリア種別を返す。

    判定基準:
      - city      : IMPERIAL.MIF / CITY* / TOWN* / VILLAG*
      - wilderness: 名前に "WILD" を含む
      - dungeon   : それ以外で MIF 名がある（START.MIF・個別ダンジョン名等）
      - unknown   : MIF 名が空（連続ロード初期や測定失敗）

    街外観 MIF には CITY1-5/CITYW1-3・TOWN1-5/TOWNW1-2/
    TOWNPAL1-3・VILLAGE1-5/VILLAGW1-2 が存在する（"W" 付き＝フィールド隣接版）。
    "CITY"/"TOWN" は接頭辞が短く W 版も拾えるが、村だけは "VILLAGE"(7文字) が
    VILLAGW*(VILLAG"W") を弾くため、村の接頭辞は "VILLAG"(6文字) とする。
    """
    mu = (mif_name or "").upper()
    if not mu:
        return "unknown"
    if mu == "IMPERIAL.MIF" or mu.startswith(("CITY", "TOWN", "VILLAG")):
        return "city"
    if "WILD" in mu:
        return "wilderness"
    return "dungeon"


def detect_play_area(
    analyzer,
    anchor: Optional[int],
    mif_name: Optional[str],
) -> PlayArea:
    """MIF 名先確定 + `+0x4BD0` 補助で play area を判定する純粋関数。

    判定順:
      1. classify_play_area(mif_name) で base 判定
      2. base in (city, unknown) かつ `+0x4BD0 == 0x01` → wilderness
      3. それ以外は base 判定そのまま

    dungeon MIF (= START.MIF / 8 桁手続き名) では `+0x4BD0` で override
    しない (= 旧仕様で dungeon も wilderness 扱いになる regression を回避)。
    """
    base = classify_play_area(mif_name)
    if base in ("city", "unknown"):
        if analyzer is not None and anchor is not None:
            try:
                raw = analyzer.read_bytes(anchor + _WILDERNESS_FLAG_OFFSET, 1)
                if raw and raw[0] == 0x01:
                    return "wilderness"
            except (OSError, AttributeError):
                pass
    return base


def resolve_in_interior(
    interior_flag: Optional[int],
    place_byte: Optional[int],
    mif_name: Optional[str],
) -> bool:
    """屋内在室を場所種別byte(+0x4BD0)を権威にして確定する純関数。

    `interior_flag`(+0xBC8E)は屋内専用ではなく menuType 由来で、夜の街路/
    フィールドでも非0(例 0x4C / 0x06)に汚染され、誤って屋内(L3)と認識される
    既知問題がある。一方 `place_byte`(+0x4BD0)は屋内=0x04・街路=0x00・
    フィールド=0x01 で昼夜とも安定（実測: 街路昼夜=0x00 / 宿屋=0x04 / 地下室=0x04）。

    判定:
      - interior_flag が 0/None → 屋外（屋内でない）。
      - interior_flag 非0 でも、場所種別byteが屋外(街路0x00/フィールド0x01)を
        示す間は屋内扱いしない（夜間汚染の抑止）。ただしダンジョン(C1)は別軸で
        扱い place_byte=0x00 でも 0xBC8E を屋内信号に使う現状を維持（除外）。
      - それ以外（place_byte=0x04 等）は interior_flag に従う。

    place_byte が None（読み取り不可）のときは従来どおり interior_flag のみで判定。
    """
    raw = interior_flag is not None and interior_flag != 0
    if not raw:
        return False
    if place_byte in (0x00, 0x01) and classify_play_area(mif_name) != "dungeon":
        return False
    return True


def area_suffix_ja(area: PlayArea, player_floor: int = 0) -> str:
    """探索エリア種別の表示サフィックス。screen_name 装飾用。

    ダンジョンの場合は PlayerFloor（1 始まり）を付加する。
    player_floor が 0 または不明の場合は階数を省略する。
    """
    if area == "dungeon":
        if player_floor > 0:
            return _i18n.tr("screen.area_suffix.dungeon", n=player_floor)
        return _i18n.tr("screen.area_suffix.dungeon_no_floor")
    return _i18n.tr(f"screen.area_suffix.{area}")
