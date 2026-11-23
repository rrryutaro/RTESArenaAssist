from __future__ import annotations
from typing import Optional
import logging
from assist_log import recog as _recog
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
    has_conversation_session = True
    panel_owners = frozenset({'shop_menu', 'shop_rumor_type', 'shop_buy', 'shop_rooms', 'tavern_yesno', 'tavern_rumor_type', 'tavern_negotiation', 'negotiation', 'active_template', 'npc_dialog'})
    outside_conversation_owners = frozenset({'artifact_offer'})

    def bar_sub_label_key(self, w, *, active_session_name: str, screen_suppresses_conversation_label: bool, img_name: str) -> str:
        return getattr(getattr(w, '_tavern_view', None), 'bar_key', '') or ''
    template_declarations = ((29598, 'stay_days', 'tavern_stay_days', ('popup',), ('popup',)), (29537, '', 'tavern_sneak_result', (), ('confirm', 'popup')), (29561, 'sneak_yesno', 'tavern_sneak_confirm', ('confirm',), ('confirm',)), (29638, '', 'tavern_sneak_result', (), ('confirm', 'popup')), (29674, '', 'tavern_room_contract', (), ('popup',)), (29728, '', 'tavern_cost_show', (), ('popup',)), (29748, '', 'tavern_cost_confirm', (), ('confirm',)))
    menu_signatures = ((frozenset({'Buy Drinks', 'Get a Room', 'Sneak into a Room', 'Rumors', 'Exit'}), 'shop_menu', 'MENU OPTIONS'), (frozenset({'Buy Drinks', 'Rumors', 'Exit'}), 'shop_menu', 'MENU OPTIONS'), (frozenset({'General', 'Work'}), 'shop_rumor_type', 'Rumor Type'))
    DRINKS_PRICE_CACHE_SIG = b'200\x00'
    LIST_WINDOW_DEFS = frozenset({20486, 20571, 20656})

    @classmethod
    def list_window_running(cls, analyzer, anchor) -> Optional[bool]:
        from active_template_reader import ACTIVE_TEMPLATE_PTR_OFFSETS
        first = ACTIVE_TEMPLATE_PTR_OFFSETS[0]
        size = ACTIVE_TEMPLATE_PTR_OFFSETS[-1] + 2 - first
        try:
            raw = analyzer.read_bytes(anchor + first, size)
        except Exception:
            return None
        return cls.list_window_in(raw)

    @classmethod
    def list_window_in(cls, raw) -> Optional[bool]:
        from active_template_reader import ACTIVE_TEMPLATE_PTR_OFFSETS
        first = ACTIVE_TEMPLATE_PTR_OFFSETS[0]
        size = ACTIVE_TEMPLATE_PTR_OFFSETS[-1] + 2 - first
        if not isinstance(raw, (bytes, bytearray)) or len(raw) < size:
            return None
        return any((int.from_bytes(raw[off - first:off - first + 2], 'little') in cls.LIST_WINDOW_DEFS for off in ACTIVE_TEMPLATE_PTR_OFFSETS))

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
    SURFACE_L4_KINDS = frozenset({'menu', 'rooms', 'drinks', 'rumor_type'})

    def _publish_surface_claim(self, w, view, facility_tavern, shop_state) -> None:
        if shop_state is None or not facility_tavern:
            return
        if (getattr(view, 'l4_kind', '') or '') in self.SURFACE_L4_KINDS:
            from store_surface import publish_l4_surface_claim
            publish_l4_surface_claim(w)

    def classify_view(self, w, *, shop_kind: str='none', shop_facility: str='', img: str='', in_interior: bool=False, facility_tavern: bool=False, npc_phase: Optional[int]=None, ask_about_obs=None, shop_state=None, signals_override: Optional[dict]=None):
        cached = peek_tavern_view(w)
        if cached is not None:
            self._log_dbg_with_observation(w, cached, shop_state, img)
            self._publish_surface_claim(w, cached, facility_tavern, shop_state)
            return cached
        from session.tavern_signals import gather_tavern_signals, kind_facility_of_surface, tavern_surface_of
        from session.tavern_view import classify_tavern_signals
        if shop_state is not None:
            shop_kind, shop_facility = kind_facility_of_surface(tavern_surface_of(w, shop_state))
        sig = gather_tavern_signals(w._analyzer, w._anchor, shop_kind=shop_kind, shop_facility=shop_facility, img=img, in_interior=in_interior, facility_tavern=facility_tavern, npc_phase=npc_phase, ask_about_obs=ask_about_obs)
        if signals_override:
            from dataclasses import replace
            sig = replace(sig, **signals_override)
        view = classify_tavern_signals(sig)
        setattr(w, VIEW_ATTR, view)
        setattr(w, VIEW_SEQ_ATTR, getattr(w, '_poll_seq', None))
        self._log_dbg_with_observation(w, view, shop_state, img)
        self._publish_surface_claim(w, view, facility_tavern, shop_state)
        self._log_view_diag(w, sig=sig, view=view)
        return view

    @staticmethod
    def _log_dbg_with_observation(w, view, shop_state, img) -> None:
        if shop_state is None:
            return
        try:
            from session.tavern_view_diagnostics import log_tavern_view_diagnostics
            log_tavern_view_diagnostics(w, view=view, shop_state=shop_state, img=img)
        except Exception:
            pass

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
            closed = w._ui_router.clear_if_owner_in(frozenset(self.panel_owners), mode='translate', place_list_owners=_PLACE_LIST_OWNERS)
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

    def observe(self, w, *, shop_state, shop_img_name: str, in_interior: bool) -> None:
        try:
            view = self.classify_view(w, shop_state=shop_state, img=shop_img_name, in_interior=in_interior, facility_tavern=self.latch(w)[0], npc_phase=getattr(w, '_npc_phase', None))
        except Exception:
            _log.exception('tavern view classify failed')
            from session.tavern_view import TavernView
            view = TavernView(l4_kind='none', render_owner='', bar_key='', l4_visible=False, l4_start=False, reason='error')
        setattr(w, VIEW_ATTR, view)

    def on_l3_exit(self, w) -> None:
        self.reset_view(w)
        super().on_l3_exit(w)

    def finish_exit_in_render_stage(self, w, *, outside: bool) -> bool:
        from normal_play.tavern_render_module import close_units_outside_conversation, leave_units_outside_conversation
        if not outside:
            close_units_outside_conversation(w)
            return False
        leave_units_outside_conversation(w)
        return True

    def session_view(self, w, *, shop_state, shop_img_name: str, foreground_ptr):
        if not self.latch(w)[0]:
            return None
        return getattr(w, '_tavern_view', None)

    def poll_units_outside_conversation(self, w, *, outside: bool, shop_img_name: str, shop_menu_visible: bool, shop_buy_active: bool, area: str, top_level_state: str):
        from normal_play.tavern_render_module import close_units_outside_conversation, poll_units_outside_conversation
        if not outside:
            close_units_outside_conversation(w)
            return (False, False)
        return poll_units_outside_conversation(w, shop_img_name=shop_img_name, shop_menu_visible=shop_menu_visible, shop_buy_active=shop_buy_active, area=area, top_level_state=top_level_state)

    def render_no_session_shop(self, w, *, shop_state, shop_img_name: str, shop_buy_active: bool, shop_menu_visible: bool):
        from normal_play.tavern_render_module import render_no_session_shop
        return render_no_session_shop(w, shop_state=shop_state, shop_img_name=shop_img_name, shop_buy_active=shop_buy_active, shop_menu_visible=shop_menu_visible)
TAVERN_NODE = TavernNode()
register_facility_node(TAVERN_NODE)
__all__ = ['TavernNode', 'TAVERN_NODE', 'peek_tavern_view']
