from __future__ import annotations
from .facility_node import SeamFacilityNode, register_facility_node

class PalaceNode(SeamFacilityNode):
    name = 'palace'
    story_kind = 'palace'
    story_owner = 'palace_dialog'
    outside_conversation_owners = frozenset({story_owner})

    def story_of(self, w, *, ptr, view) -> str:
        from l3_facility import l3_decided_by_mif
        from normal_play.palace_dialog_module import _dialog_body_source, _dialog_hold_pointer
        if l3_decided_by_mif(w) and (_dialog_body_source(ptr) or _dialog_hold_pointer(ptr)):
            return 'palace'
        return ''

    def poll_story(self, w, *, active: bool, foreground_ptr=None) -> bool:
        from normal_play.palace_dialog_module import poll_palace_dialog
        if not active:
            return bool(poll_palace_dialog(w, palace_active=False))
        return bool(poll_palace_dialog(w, palace_active=True, foreground_ptr=foreground_ptr))
PALACE_NODE = PalaceNode()
register_facility_node(PALACE_NODE)
__all__ = ['PalaceNode', 'PALACE_NODE']
