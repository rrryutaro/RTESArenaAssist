"""session/hierarchy_attach.py — 中途接続の階層解決。

Assist 起動時（ユーザーが既に任意状態でプレイ中）に、現在のメモリ信号から
L1→L2→L3 のパスを解決する seam。L1 判定（current_state）、L2 単一
classifier（classify_base_location）、施設ノード registry（node_for_facility_kind）を
**合成**して、中途接続時の階層を現在状態から push する形を 1 か所に表す。

屋外不明時の fallback（街扱い等）は SeparationHierarchy 側の方針に従う（本
helper は現在信号からの素直な解決を担う）。
"""
from __future__ import annotations

from typing import Any, Dict

from top_level.top_level_dispatcher import current_state
from normal_play.base_location.base_location_view import classify_base_location
from session.facility_nodes import node_for_facility_kind


def resolve_attach_path(
    w,
    *,
    mif_name: str = "",
    in_interior: bool = False,
    facility_kind: str = "",
) -> Dict[str, Any]:
    """中途接続時の階層パスを現在信号から解決する（pure 合成）。

    Returns:
      {
        "l1":       "pregame"/"chargen"/"normal-play",
        "l2":       "C1"/"C2"/"C3"/""（L1!=normal-play なら ""。屋内中でも親 L2 を保持）,
        "l3":       "interior"（屋内中）または ""（屋外）,
        "facility": FacilityNode | None（屋内かつ facility_kind 判明時のみ）,
      }

    注: mif_name は在室中も「街マップ MIF」（SessionContext.mif_name）。
    interior_mif_name とは別。よって屋内中でも mif_name から親 L2（C2/C3）を
    解決でき、L1→L2→L3 push / 退出時の親復帰（③④）が成立する。
    """
    l1 = current_state(w)
    if l1 != "normal-play":
        return {"l1": l1, "l2": "", "l3": "", "facility": None}

    # 屋外/屋内いずれも親 L2 は街マップ MIF (= mif_name) から解決する。
    l2 = classify_base_location(
        getattr(w, "_analyzer", None), getattr(w, "_anchor", None), mif_name)

    if in_interior:
        # 屋内(L3)。親 L2(C2/C3)を結果に保持し、施設が判れば node を返す。
        # (singleton への set_parent 副作用は避け、親は結果の l2 で渡す。実際の
        #  親接続は SessionManager 統合時に行う＝③の形)
        facility = node_for_facility_kind(facility_kind)
        return {"l1": l1, "l2": l2, "l3": "interior", "facility": facility}

    return {"l1": l1, "l2": l2, "l3": "", "facility": None}


__all__ = ["resolve_attach_path"]
