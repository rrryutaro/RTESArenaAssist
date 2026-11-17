from __future__ import annotations
from typing import Any, Dict
from top_level.top_level_dispatcher import current_state
from normal_play.base_location.base_location_view import classify_base_location

def resolve_attach_path(w, *, mif_name: str='', in_interior: bool=False) -> Dict[str, Any]:
    l1 = current_state(w)
    if l1 != 'normal-play':
        return {'l1': l1, 'l2': '', 'l3': ''}
    l2 = classify_base_location(getattr(w, '_analyzer', None), getattr(w, '_anchor', None), mif_name)
    return {'l1': l1, 'l2': l2, 'l3': 'interior' if in_interior else ''}
__all__ = ['resolve_attach_path']
