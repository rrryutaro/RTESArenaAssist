"""normal_play/base_location/base_location_view.py — L2 基本居場所の単一判定。

C 配下 L2（C1 ダンジョン / C2 街 / C3 フィールド）を **1 つの classifier** に集約する
1軸 seam。area 判定は既存の純関数 ``detect_play_area``（``classify_play_area`` ＋
``+0x4BD0`` wilderness 補助）を単一ソースとして再利用し、L2 階層コード（C1/C2/C3）へ
写像する。これにより L2 の「真実」を 1 か所に名前付きで集約する。

屋内（店内 / L3）は呼び出し側（``MapDispatcher`` が ``InteriorMapSession`` を先に
評価）が判定するため、本関数は**非屋内前提**で C1/C2/C3 を返す（該当なしは ""）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from play_area_classifier import detect_play_area


@dataclass(frozen=True)
class FieldEntranceContext:
    """フィールド(C3)入口へ進入した直後の入口コンテキスト。

    クリプト/塔/神殿へ入ると `LiveMifName` が stale な VILLAGE*.MIF になり、
    クリプトでは `interior_flag(0xBC8E)=0x00` のまま city 誤認する既知問題への
    補正に使う。フィールド上で player が進入可能 MENU セル（クリプト/神殿/塔/
    ダンジョン）に乗った/隣接した直前情報を latch し、入場後の場所解決へ渡す。

    interior_mif_name は扉座標から解決した実 MIF（WCRYPT*/TEMPLE*/TOWER*）。
    施設（クリプト/神殿/塔）は MIF あり、ダンジョン（固定 MIF なし）は None。
    menu_label は種別の説明文字列（"crypt"/"temple"/"tower"/"dungeon"）。
    name_en/name_ja は wild chunk seed から生成した固有名（神殿のみ。OTA は荒地で
    神殿/酒場のみ命名し、クリプト/塔は固有名を持たない＝None）。
    """
    interior_mif_name: Optional[str] = None  # 扉座標から解決した実 MIF（WCRYPT*等）
    menu_label: str = ""                     # 種別（"crypt" 等）
    name_en: str = ""                        # 固有名 en（神殿のみ・seed 生成）
    name_ja: Optional[str] = None            # 固有名 ja（神殿のみ・seed 生成）


# フィールド施設「中」判定の補助フラグ値（+0x4BD0、play_area_classifier と同 offset）。
#   0x01 = フィールド（地表）、0x04 = 地下室（クリプト）の中。
#   0x04 は観測 1 回の仮説。実機で 1 回確認してから確定すること
#   （「+0x4BD0 直マッピング regression」を避けるため、必ず入口 hint で
#    gate して単独マッピングにしない）。
_WILD_FIELD_FLAG = 0x01
_WILD_CRYPT_FLAG = 0x04


def resolve_field_facility_entry(
    hint: Optional[FieldEntranceContext],
    *,
    interior_flag_nonzero: bool,
    wild_flag: int,
) -> Tuple[bool, Optional[str], str]:
    """フィールド施設（地下室/神殿/塔）の「中」を 1 つの純判定で確定する。

    入口 hint（フィールド上で latch・入場で凍結）を gate にして、施設内信号と
    組み合わせて判定する（単独の +0x4BD0 マッピングにしない）:
      - 神殿/塔: `interior_flag(0xBC8E)` 非0（立つ）かつ +0x4BD0 がフィールド
        (0x01) でない。
      - 地下室: +0x4BD0 == 0x04（仮説・要実機確認）。
      - +0x4BD0 == 0x01（フィールド地表）は施設ではない＝退出。夜のフィールドで
        interior_flag=0x06 になる既知の汚染（[[project_field_location_signal_gaps]]
        ①）も、この明示フィールド判定で誤検出を抑える。

    Returns:
        (active, interior_mif_name, menu_label)
        active=False のとき mif=None / label=""（呼び側は施設状態を解除）。
    """
    if hint is None or not hint.interior_mif_name:
        return (False, None, "")
    if wild_flag == _WILD_CRYPT_FLAG:
        active = True
    elif interior_flag_nonzero and wild_flag != _WILD_FIELD_FLAG:
        active = True
    else:
        active = False
    if not active:
        return (False, None, "")
    return (True, hint.interior_mif_name, hint.menu_label or "")


# area 名（dungeon/city/wilderness） ⇔ L2 コード（C1/C2/C3）
_AREA_TO_L2 = {"dungeon": "C1", "city": "C2", "wilderness": "C3"}
_L2_TO_AREA = {v: k for k, v in _AREA_TO_L2.items()}

# 屋内施設 MIF 名の先頭パターン（dungeon 判定の補完対象）
_INTERIOR_MIF_PREFIXES: Tuple[str, ...] = (
    "TAVERN", "TEMPLE", "EQUIP", "ARMORS", "MAGES", "MAGE",
    "PALACE", "NOBLE", "HOUSE",
)


def _looks_like_interior_mif(mif_name: Optional[str]) -> bool:
    u = (mif_name or "").upper()
    return any(u.startswith(p) for p in _INTERIOR_MIF_PREFIXES)


def classify_base_location(
    analyzer, anchor: Optional[int], mif_name: Optional[str]) -> str:
    """非屋内前提で L2 コード（C1/C2/C3）を 1 つ返す。該当なしは ""。

    判定は ``detect_play_area``（= MIF 名 ＋ +0x4BD0 補助）に委譲する単一ソース。
    """
    return _AREA_TO_L2.get(detect_play_area(analyzer, anchor, mif_name), "")


def area_name(l2_code: str) -> str:
    """L2 コード（C1/C2/C3）→ area 名（dungeon/city/wilderness）。未知は ""。"""
    return _L2_TO_AREA.get(l2_code or "", "")


def classify_map_axis(
    analyzer,
    anchor: Optional[int],
    *,
    mif_name: Optional[str],
    interior_mif_name: Optional[str],
    in_interior: Optional[bool] = None,
    area: Optional[str] = None,
) -> Optional[str]:
    """マップ表示の L2/L3 軸を 1 つだけ確定する単一分類器 (1軸・S6)。

    旧 try_start 並列評価 (interior→dungeon→city→wilderness の毎 poll
    再評価＋優先順選定) の真理値表を 1 つの決定木へ verbatim 集約したもの。
    detect_play_area / interior flag の読取は本関数で各1回 (単一実行)。

    Returns:
        "interior" / "dungeon" / "city" / "wilderness" / None (= 軸なし)

    決定木 (旧 try_start 連鎖と同一):
      - 屋内 + 施設 MIF あり → interior (施設は detect が dungeon でも
        計算で確定する施設マップ)
      - 屋内 + 施設 MIF なし + detect==dungeon → dungeon (ダンジョン中の
        +0xBC8E は menuType 等の別軸値で非0を取りうるため C1 へ譲る)
      - 屋内 + 施設 MIF なし + detect!=dungeon → interior
      - 非屋内 → detect の dungeon/city/wilderness をそのまま軸に
        (unknown は None=軸なし)

    in_interior は poll 確定値の注入を想定 (単一の真実)。None の場合のみ
    互換 fallback として interior flag を自前 read する。
    """
    if in_interior is None:
        from arena_bridge import read_interior_flag
        from play_area_classifier import (
            resolve_in_interior, _WILDERNESS_FLAG_OFFSET,
        )
        try:
            _place = analyzer.read_bytes(
                anchor + _WILDERNESS_FLAG_OFFSET, 1)[0]
        except (OSError, IndexError, AttributeError):
            _place = None
        in_interior = resolve_in_interior(
            read_interior_flag(analyzer, anchor), _place, mif_name)
    if in_interior and interior_mif_name:
        return "interior"
    # 単一ソース: poll 確定の保持 area を優先消費する (全消費者が同じ値を見る
    # 1軸化)。area が注入されない (None) ときだけ互換 fallback で自前判定する。
    if area is None:
        area = detect_play_area(analyzer, anchor, mif_name)
    if in_interior:
        return "dungeon" if area == "dungeon" else "interior"
    if area in _AREA_TO_L2:
        return area
    return None


def resolve_area_with_indoor_fallback(
    analyzer,
    anchor: Optional[int],
    mif_name: Optional[str],
    in_interior: bool,
    last_non_interior_area: str,
) -> Tuple[str, str]:
    """屋内補完ロジックを含む area 確定関数（S4 単一軸、stateless）。

    poll_controller の ``_resolve_outdoor_area`` と等価だが副作用なし。
    呼び出し元が返値の second 要素を ``w._last_non_interior_area`` に保存する。

    Returns:
        (area_str, new_last_non_interior_area)
        area_str: "city" / "wilderness" / "dungeon" / "unknown"
        new_last_non_interior_area: 呼び出し元が保存する値
    """
    if in_interior:
        if last_non_interior_area:
            return last_non_interior_area, last_non_interior_area
        area = detect_play_area(analyzer, anchor, mif_name)
        if area == "unknown" or (
                area == "dungeon" and _looks_like_interior_mif(mif_name)):
            return "city", last_non_interior_area
        return area, last_non_interior_area
    area = detect_play_area(analyzer, anchor, mif_name)
    if area in ("city", "wilderness", "dungeon"):
        return area, area
    return area, last_non_interior_area


__all__ = [
    "FieldEntranceContext",
    "resolve_field_facility_entry",
    "classify_base_location",
    "area_name",
    "classify_map_axis",
    "resolve_area_with_indoor_fallback",
]
