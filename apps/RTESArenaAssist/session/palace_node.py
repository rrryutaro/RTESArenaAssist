"""session/palace_node.py — 宮殿 施設ノード（seam）。

宮殿のサブ画面フローは未解明のため、宿屋(TavernNode)と同じ形の seam として
配置する。実機フロー観測後に宿屋と同じ手順で classify_view / render を充足する。
"""
from __future__ import annotations

from .facility_node import SeamFacilityNode, register_facility_node


class PalaceNode(SeamFacilityNode):
    """宮殿の施設分離ノード（seam）。"""
    name = "palace"


PALACE_NODE = PalaceNode()
register_facility_node(PALACE_NODE)

__all__ = ["PalaceNode", "PALACE_NODE"]
