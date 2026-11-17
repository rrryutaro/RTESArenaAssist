from __future__ import annotations
from typing import NamedTuple
from interior_facility import facility_of_mif

def hint_facilities() -> frozenset[str]:
    from session import facility_nodes as _fn
    from session.facility_node import registered_facility_names
    return frozenset(registered_facility_names())

class L3Facility(NamedTuple):
    facility: str
    kept: str

def first_known_facility(*hints: str) -> str:
    known = hint_facilities()
    for h in hints:
        if (h or '') in known:
            return h
    return ''

def declared_facility_of(shop_state) -> str:
    if shop_state is None:
        return ''
    from shop_popup_detector import ptr_group_menu_items
    items = ptr_group_menu_items(shop_state, menu_back_on_yesno=yesno_menu_back_of(shop_state))
    if not items:
        return ''
    from session import facility_nodes as _fn
    from session.facility_node import build_menu_signature_table
    entry = build_menu_signature_table().get(frozenset(items))
    return entry[1] if entry else ''
_DECLARED_POPUP_POINTERS: list = []

def declared_popup_pointers() -> frozenset:
    if not _DECLARED_POPUP_POINTERS:
        from active_template_reader import COUNTER_OFFER_DECLARATIONS, declared_template_pointers
        from session import facility_nodes as _fn
        from session.facility_node import declared_template_groups
        _DECLARED_POPUP_POINTERS.append(declared_template_pointers(COUNTER_OFFER_DECLARATIONS, *declared_template_groups()))
    return _DECLARED_POPUP_POINTERS[0]

def yesno_menu_back_of(shop_state) -> bool:
    from shop_popup_detector import yesno_menu_back
    return yesno_menu_back(shop_state, declared_popup_pointers())

def facility_named_by_mif(interior_mif_name, in_interior: bool) -> str:
    if not in_interior:
        return ''
    if not (interior_mif_name or '').strip():
        return ''
    return facility_of_mif(interior_mif_name)

def resolve_l3_facility(interior_mif_name, in_interior: bool, *, area: str='', declared_facility: str='', kept: str='') -> L3Facility:
    if not in_interior:
        return L3Facility('', '')
    kept_next = first_known_facility(declared_facility) or (kept or '')
    if (interior_mif_name or '').strip():
        return L3Facility(facility_named_by_mif(interior_mif_name, in_interior), kept_next)
    if area == 'dungeon':
        return L3Facility('', kept_next)
    return L3Facility(first_known_facility(declared_facility, kept_next), kept_next)

def node_named_by_mif(interior_mif_name, in_interior: bool):
    from session import facility_nodes as _fn
    from session.facility_node import get_facility_node
    return get_facility_node(facility_named_by_mif(interior_mif_name, in_interior))

def decided_by_mif(interior_mif_name, in_interior: bool) -> bool:
    return bool(in_interior and (interior_mif_name or '').strip())

def set_l3(w, facility: str, *, interior_mif_name, in_interior: bool) -> None:
    import logging
    prev = getattr(w, '_l3_facility', '') or ''
    w._l3_facility = facility
    w._l3_by_mif = decided_by_mif(interior_mif_name, in_interior)
    if prev != facility:
        pending = tuple((n for n in getattr(w, '_l3_exit_pending', ()) if n.name != facility))
        if prev:
            from session import facility_nodes as _fn
            from session.facility_node import get_facility_node
            node = get_facility_node(prev)
            if node is not None:
                try:
                    node.on_l3_exit(w)
                except Exception:
                    logging.getLogger('poll_controller').exception('facility on_l3_exit failed (%s)', prev)
                if node not in pending:
                    pending += (node,)
        w._l3_exit_pending = pending

def finish_exits_in_render_stage(w, *, outside: bool) -> None:
    import logging
    pending = getattr(w, '_l3_exit_pending', ())
    if not pending:
        return
    left = []
    for node in pending:
        try:
            done = node.finish_exit_in_render_stage(w, outside=outside)
        except Exception:
            logging.getLogger('poll_controller').exception('facility finish_exit_in_render_stage failed (%s)', node.name)
            done = True
        if not done:
            left.append(node)
    w._l3_exit_pending = tuple(left)

def l3_decided_by_mif(w) -> bool:
    return bool(getattr(w, '_l3_by_mif', False))

def l3_node(w):
    from session import facility_nodes as _fn
    from session.facility_node import get_facility_node
    return get_facility_node(getattr(w, '_l3_facility', '') or '')
__all__ = ['L3Facility', 'facility_named_by_mif', 'l3_decided_by_mif', 'decided_by_mif', 'l3_node', 'node_named_by_mif', 'set_l3', 'declared_facility_of', 'first_known_facility', 'hint_facilities', 'resolve_l3_facility']
