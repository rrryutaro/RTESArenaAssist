from __future__ import annotations

from .facility_node import SeamFacilityNode, register_facility_node


class PalaceNode(SeamFacilityNode):
    name = "palace"


PALACE_NODE = PalaceNode()
register_facility_node(PALACE_NODE)

__all__ = ["PalaceNode", "PALACE_NODE"]
