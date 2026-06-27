from __future__ import annotations
from typing import Optional
from .facility_node import FacilityNode, get_facility_node
from .tavern_node import TAVERN_NODE
from .temple_node import TEMPLE_NODE
from .equipment_node import EQUIPMENT_NODE
from .mages_guild_node import MAGES_GUILD_NODE
from .palace_node import PALACE_NODE
_NORM_TO_NAME = {'TAVERN': 'tavern', 'TEMPLE': 'temple', 'EQUIPMENT': 'equipment', 'MAGESGUILD': 'mages_guild', 'PALACE': 'palace'}

def _normalize_facility_kind(facility_kind: str) -> str:
    return (facility_kind or '').upper().replace('_', '').replace(' ', '')

def node_for_facility_kind(facility_kind: str) -> Optional[FacilityNode]:
    name = _NORM_TO_NAME.get(_normalize_facility_kind(facility_kind))
    return get_facility_node(name) if name else None
__all__ = ['TAVERN_NODE', 'TEMPLE_NODE', 'EQUIPMENT_NODE', 'MAGES_GUILD_NODE', 'PALACE_NODE', 'node_for_facility_kind']
