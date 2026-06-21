"""session/facility_nodes.py — 施設分離ノードの集約。

全施設ノード（宿屋＝確定実装 / 神殿・装備品店・魔術師ギルド・宮殿＝seam）を
import して registry へ登録し、``facility_kind``（SessionContext / CityViewer 由来の
大文字キー）→ ノードの対応表を提供する。poll_controller / 上位 dispatcher は本
モジュール経由で施設ノードを取得する。
"""
from __future__ import annotations

from typing import Optional

from .facility_node import FacilityNode, get_facility_node
from .tavern_node import TAVERN_NODE
from .temple_node import TEMPLE_NODE
from .equipment_node import EQUIPMENT_NODE
from .mages_guild_node import MAGES_GUILD_NODE
from .palace_node import PALACE_NODE


# 正規化 facility_kind → ノード名（小文字 = owner名前空間）。
# facility_kind は呼出元により表記ゆれがある:
#   - ArenaMenuType の enum 値 (CamelCase): "Tavern" / "MagesGuild" / "Equipment"
#   - enum 名 (UPPER_SNAKE):                "TAVERN" / "MAGES_GUILD"
#   - 小文字:                                "tavern" / "mages_guild"
# いずれも「大文字化＋区切り除去」で正規化して受ける。
_NORM_TO_NAME = {
    "TAVERN": "tavern",
    "TEMPLE": "temple",
    "EQUIPMENT": "equipment",
    "MAGESGUILD": "mages_guild",
    "PALACE": "palace",
}


def _normalize_facility_kind(facility_kind: str) -> str:
    """facility_kind を表記ゆれ非依存のキーへ正規化（大文字化＋区切り除去）。"""
    return (facility_kind or "").upper().replace("_", "").replace(" ", "")


def node_for_facility_kind(facility_kind: str) -> Optional[FacilityNode]:
    """facility_kind（'TAVERN' / 'MagesGuild' / 'mages_guild' 等）に対応する
    施設ノードを返す。表記ゆれを正規化して解決。該当なしは None。"""
    name = _NORM_TO_NAME.get(_normalize_facility_kind(facility_kind))
    return get_facility_node(name) if name else None


__all__ = [
    "TAVERN_NODE",
    "TEMPLE_NODE",
    "EQUIPMENT_NODE",
    "MAGES_GUILD_NODE",
    "PALACE_NODE",
    "node_for_facility_kind",
]
