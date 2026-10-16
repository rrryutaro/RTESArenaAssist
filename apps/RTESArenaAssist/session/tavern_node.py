from __future__ import annotations
from typing import Optional
import logging
from assist_log import recog as _recog
from hierarchy_state import facility_owners_for_session
from .facility_node import FacilityNode, register_facility_node
_log = logging.getLogger('RTESArenaAssist')
VIEW_ATTR = '_tavern_view'
VIEW_SEQ_ATTR = '_tavern_view_seq'

def peek_tavern_view(w):
    seq = getattr(w, '_poll_seq', None)
    if not isinstance(seq, int):
        return None
    if getattr(w, VIEW_SEQ_ATTR, None) != seq:
        return None
    return getattr(w, VIEW_ATTR, None)
_PLACE_LIST_OWNERS = frozenset({'npc_dialog', 'npc_conversation', 'npc_message'})

class TavernNode(FacilityNode):
    name = 'tavern'
    menu_signatures = ((frozenset({'Buy Drinks', 'Get a Room', 'Sneak into a Room', 'Rumors', 'Exit'}), 'shop_menu', 'MENU OPTIONS'), (frozenset({'Buy Drinks', 'Rumors', 'Exit'}), 'shop_menu', 'MENU OPTIONS'), (frozenset({'General', 'Work'}), 'shop_rumor_type', 'Rumor Type'))
    DRINKS_PRICE_CACHE_SIG = b'200\x00'

    @staticmethod
    def read_shop_buy_span(analyzer, anchor):
        from shop_item_list_reader import SHOP_ITEM_LIST_OFFSET, SHOP_ITEM_LIST_MAXLEN, parse_shop_item_list
        try:
            raw = analyzer.read_bytes(anchor + SHOP_ITEM_LIST_OFFSET, SHOP_ITEM_LIST_MAXLEN)
        except (OSError, AttributeError):
            return ([], None)
        items = parse_shop_item_list(raw)
        if not items:
            return ([], None)
        span = (SHOP_ITEM_LIST_OFFSET, SHOP_ITEM_LIST_OFFSET + SHOP_ITEM_LIST_MAXLEN)
        return (items, span)

    @staticmethod
    def read_room_items(analyzer, anchor):
        from room_list_reader import read_room_list
        return read_room_list(analyzer, anchor)

    @staticmethod
    def is_room_list_context(*, interior_mif_name: str, active_facility_name: str) -> bool:
        _mif_u = (interior_mif_name or '').upper()
        _active_facility = (active_facility_name or '').lower()
        _non_tavern_active = _active_facility in ('temple', 'equipment', 'mages_guild', 'magesguild')
        return not _non_tavern_active and (_active_facility == 'tavern' or _mif_u.startswith('TAVERN'))

    def classify_view(self, w, *, shop_kind: str='none', shop_facility: str='', img: str='', in_interior: bool=False, facility_tavern: bool=False, npc_phase: Optional[int]=None, ask_about_obs=None):
        cached = peek_tavern_view(w)
        if cached is not None:
            return cached
        from session.tavern_signals import gather_tavern_signals
        from session.tavern_view import classify_tavern_signals
        sig = gather_tavern_signals(w._analyzer, w._anchor, shop_kind=shop_kind, shop_facility=shop_facility, img=img, in_interior=in_interior, facility_tavern=facility_tavern, npc_phase=npc_phase, ask_about_obs=ask_about_obs)
        view = classify_tavern_signals(sig)
        setattr(w, VIEW_ATTR, view)
        setattr(w, VIEW_SEQ_ATTR, getattr(w, '_poll_seq', None))
        self._log_view_diag(w, sig=sig, view=view)
        return view

    @staticmethod
    def _log_view_diag(w, *, sig, view) -> None:
        if not sig.facility_tavern and view.l4_kind == 'none':
            return
        drawn_by = view.render_owner or '-'
        shop_by = sig.shop_facility or '-'
        key = (view.l4_kind, drawn_by, view.reason, sig.img, sig.shop_kind, shop_by, tuple(sorted(sig.active_surfaces)), sig.cur_ptr_surface, sig.negotiation_body, sig.counter_active, sig.npc_response_hit, sig.rumor_marker, sig.in_interior, sig.facility_tavern)
        if key == getattr(w, '_tavern_view_diag_key', None):
            return
        w._tavern_view_diag_key = key
        _recog(_log, 'tavern L4 view: img=%r kind=%s owner=%s reason=%s shop=%s/%s surfaces=%s cur=%s negot=%s counter=%s resp=%s rumor=%s interior=%s fac=%s', sig.img, view.l4_kind, drawn_by, view.reason, sig.shop_kind, shop_by, ','.join(sorted(sig.active_surfaces)) or '-', sig.cur_ptr_surface or '-', sig.negotiation_body, sig.counter_active, sig.npc_response_hit, sig.rumor_marker, sig.in_interior, sig.facility_tavern)

    @staticmethod
    def reset_view(w) -> None:
        setattr(w, VIEW_ATTR, None)
        setattr(w, VIEW_SEQ_ATTR, None)
        w._tavern_view_diag_key = None

    def render(self, w, *, view, shop_state=None, shop_img_name: str='', top_level_state: str=''):
        from normal_play.tavern_render_module import poll_tavern_render
        return poll_tavern_render(w, tview=view, shop_state=shop_state, shop_img_name=shop_img_name, top_level_state=top_level_state)

    def on_exit(self, w) -> None:
        try:
            closed = w._ui_router.clear_if_owner_in(facility_owners_for_session(self.name), mode='translate', place_list_owners=_PLACE_LIST_OWNERS)
        except (AttributeError, RuntimeError) as exc:
            closed = ''
            _log.debug('facility stop display clear skipped: %s', exc)
        if closed:
            _log.info('facility session stopped -> clearing L4 display (session=%s owner=%r)', self.name, closed)
        try:
            from normal_play.tavern_render_module import reset_tavern_render_state
            reset_tavern_render_state(w)
        except Exception:
            pass
        try:
            self.reset_view(w)
        except Exception:
            pass
        try:
            from normal_play.negotiation_module import cleanup_if_owner as _cleanup_negotiation
            _cleanup_negotiation(w)
        except Exception:
            pass
        try:
            from normal_play.active_template_module import cleanup_if_owner as _cleanup_active_template
            _cleanup_active_template(w)
        except Exception:
            pass

    def render_no_session_shop(self, w, *, shop_state, shop_img_name: str, shop_buy_active: bool, shop_menu_visible: bool):
        from normal_play.tavern_render_module import render_no_session_shop
        return render_no_session_shop(w, shop_state=shop_state, shop_img_name=shop_img_name, shop_buy_active=shop_buy_active, shop_menu_visible=shop_menu_visible)
TAVERN_NODE = TavernNode()
register_facility_node(TAVERN_NODE)
__all__ = ['TavernNode', 'TAVERN_NODE', 'peek_tavern_view']
