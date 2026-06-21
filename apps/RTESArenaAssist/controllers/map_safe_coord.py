"""controllers/map_safe_coord.py — マップ表示用 safe 座標判定。

ダイアログ表示中 / 施設会話中 / 通常 NPC 会話中などに raw 座標が破損
(= X:3 Y:3 等) する場面で、マップ描画へ渡す座標を raw / held (= 直前安定値) /
none に切替えるための pure helper。

window / analyzer / poll_controller の時系列状態には触らず、引数だけで
判定する。これにより:
  - 単体テストで unsafe ケースを網羅できる
  - poll_controller 内の変数寿命に依存しない (= UnboundLocalError 再発防止)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# unsafe 判定の対象画像 (= ダイアログ / 交渉 / 取得一覧 / NPC 立絵)
DIALOG_IMGS_FOR_MAP: frozenset = frozenset({
    "YESNO.IMG",
    "NEGOTBUT.IMG",
    "NEWPOP.IMG",
    "POPUP11.IMG",
    "FACES00.CIF",
})

# unsafe 判定の対象 panel_owner (= 施設会話 / 交渉 / 店メニュー系)
OWNER_FACILITY_OR_NEGOT: frozenset = frozenset({
    "tavern_yesno",
    "tavern_rumor_type",
    "tavern_negotiation",  # 宿屋から開始した交渉
    "negotiation",
    "shop_menu",
    "shop_rumor_type",
    "shop_buy",
    "shop_rooms",
})

# held 座標として使ってはいけない Arena 初期/過渡値。
# - (3,3): DLGFLG 系ダイアログ表示中に出る既知の破損座標
# - (0,0): pregame/chargen/遷移直後に残りやすい初期値。reveal stencil の
#          端 wrap により右上へ未到達領域を描いてしまう。
INVALID_HELD_COORDS: frozenset = frozenset({
    (0, 0),
    (3, 3),
})


@dataclass
class MapSafeCoord:
    """compute_map_safe_coord の戻り値。

    source: "raw" / "held" / "none" のいずれか。
      - "raw":  ダイアログ抑止対象でないため raw 座標をそのまま使う
      - "held": 抑止対象なので直前安定値を使う
      - "none": 抑止対象だが直前値もないため座標なし

    player_x / player_y / angle_deg: マップ描画に渡す座標と角度。
      source="none" の場合は全て None。

    unsafe_reasons: unsafe 判定の理由リスト (= 診断ログ用)。
      source="raw" の場合は空リスト。
    """
    source: str  # "raw" / "held" / "none"
    player_x: Optional[int]
    player_y: Optional[int]
    angle_deg: Optional[float]
    unsafe_reasons: list = field(default_factory=list)


# NPC_PHASE_IDLE 値 (= arena_bridge 依存を避けるため定数で持つ)
_NPC_PHASE_IDLE = 0x00


def compute_map_safe_coord(
    *,
    img_name: str,
    npc_phase: Optional[int],
    is_building_entry_msg: bool,
    facility_active: bool,
    owner: str,
    raw_x: Optional[int],
    raw_y: Optional[int],
    raw_angle: Optional[float],
    last_x: Optional[int],
    last_y: Optional[int],
    last_angle: Optional[float],
    npc_phase_idle_value: int = _NPC_PHASE_IDLE,
) -> MapSafeCoord:
    """マップ描画用の safe 座標を判定する pure helper。

    unsafe 条件 (= いずれか 1 つで unsafe):
      1. 入店メッセージ表示中 (is_building_entry_msg)
      2. NPC 会話 phase が IDLE 以外
      3. ダイアログ画像 (= DIALOG_IMGS_FOR_MAP に含まれる)
      4. 施設会話 active (= facility_active=True、宿屋/寺院 session active)
      5. 翻訳所有者が施設/交渉/店メニュー系
         (= OWNER_FACILITY_OR_NEGOT に含まれる)

    unsafe のとき:
      - last_x/last_y がある → source="held" で last を返す
      - last_x/last_y がない → source="none" で全 None

    safe のとき:
      - source="raw" で raw を返す (= raw_x/raw_y が None なら raw None)

    Args:
      img_name: 現在の画像名 (= 大文字、正規化済み想定)
      npc_phase: NPC phase バイト値 (None なら判定に使わない)
      is_building_entry_msg: 入店メッセージ表示中か
      facility_active: 施設会話 session active か
      owner: 現在の panel_owner 文字列
      raw_x / raw_y / raw_angle: メモリから読み取った raw 座標
      last_x / last_y / last_angle: 直前 poll の安定座標
      npc_phase_idle_value: IDLE 判定値 (= 既定 0x00)

    Returns:
      MapSafeCoord (source / player_x / player_y / angle_deg / unsafe_reasons)
    """
    img_upper = (img_name or "").upper()

    unsafe_reasons: list = []
    if is_building_entry_msg:
        unsafe_reasons.append("building_entry")
    if npc_phase is not None and npc_phase != npc_phase_idle_value:
        unsafe_reasons.append("npc_phase_non_idle")
    if img_upper in DIALOG_IMGS_FOR_MAP:
        unsafe_reasons.append(f"dialog_img={img_upper}")
    if facility_active:
        unsafe_reasons.append("facility_active")
    if owner in OWNER_FACILITY_OR_NEGOT:
        unsafe_reasons.append(f"owner={owner}")

    if unsafe_reasons:
        last_pair = (
            (last_x, last_y)
            if last_x is not None and last_y is not None
            else None
        )
        if last_pair is not None and last_pair not in INVALID_HELD_COORDS:
            return MapSafeCoord(
                source="held",
                player_x=last_x,
                player_y=last_y,
                angle_deg=last_angle,
                unsafe_reasons=unsafe_reasons,
            )
        return MapSafeCoord(
            source="none",
            player_x=None,
            player_y=None,
            angle_deg=None,
            unsafe_reasons=unsafe_reasons,
        )
    # safe
    return MapSafeCoord(
        source="raw",
        player_x=raw_x,
        player_y=raw_y,
        angle_deg=raw_angle,
        unsafe_reasons=[],
    )


__all__ = [
    "MapSafeCoord",
    "compute_map_safe_coord",
    "DIALOG_IMGS_FOR_MAP",
    "INVALID_HELD_COORDS",
    "OWNER_FACILITY_OR_NEGOT",
]
