from __future__ import annotations
import logging
from assist_log import recog as _recog
from hierarchy_state import facility_owners_for_session
from mages_signals import BUYSPELL_IMG, CONFIRM_IMG, DESC_LO_DETECT_REPLY, DESC_LO_MENU_TO_LIST, DETECT_COST_HINT, DETECT_KNOWN_HINT, DIALOG_NEGOTIATION, DIALOG_NORMAL, FAMILY_MENU_DETECT_CREATE, FRAME_EDIT_EFFECTS, FRAME_MAIN_MENU, FRAME_POPUP, FRAME_SUB_MENU, INVENTORY_LIST_IMG, LIST_IMGS, LIST_ON, MENU_IMG, NEGOTIATION_IMGS, SPELLMAKER_IMG, TYPE_POPUP
from mages_signals import CONFIRM_FAMILY as CONFIRM_FAMILY_VALUE
from normal_play.mages_owner_names import EFFECT_MENU_OWNER, LIST_OWNER, MENU_OWNER, MENU_OWNER_CONFIRM, MENU_OWNER_PROMPT, MENU_OWNER_SPELLDETAIL, NEGOTIATION_OWNER, REPLY_OWNER, SPELLMAKER_OWNER
from .facility_node import FacilityNode, FacilityView, register_facility_node
_log = logging.getLogger('RTESArenaAssist')

def _hex8(value) -> str:
    return f'{int(value):#04x}' if isinstance(value, int) else 'None'

def _hex16(value) -> str:
    return f'{int(value):#06x}' if isinstance(value, int) else 'None'
_PLACE_LIST_OWNERS = frozenset({'npc_dialog', 'npc_conversation', 'npc_message'})
_NONE = ('none', '', '')
VIEW_ATTR = '_mages_view_now'
VIEW_SEQ_ATTR = '_mages_view_seq'

def peek_mages_view(w):
    seq = getattr(w, '_poll_seq', None)
    if not isinstance(seq, int):
        return None
    if getattr(w, VIEW_SEQ_ATTR, None) != seq:
        return None
    return getattr(w, VIEW_ATTR, None)

def _is_menu_frame(s: dict) -> bool:
    return s['frame'] not in (FRAME_POPUP, FRAME_EDIT_EFFECTS, None)

def _popup_reply_frame(s: dict) -> bool:
    return s['frame'] == FRAME_POPUP and s['type'] in (None, TYPE_POPUP)

def _list_not_on(s: dict) -> bool:
    return s['list_flag'] not in (None, LIST_ON)

def _detect_common(s: dict) -> bool:
    if s['dialog'] != DIALOG_NORMAL:
        return False
    if s['family'] != FAMILY_MENU_DETECT_CREATE:
        return False
    if s['frame'] == FRAME_POPUP and s['list_flag'] == LIST_ON and (s['sub'] not in (None, 0)):
        return False
    return True

def _spellmaker_return(s: dict) -> bool:
    if s['img'] not in LIST_IMGS or not s['spellmaker_list_title']:
        return False
    if _list_not_on(s):
        return True
    return s['frame'] == FRAME_POPUP and s['list_flag'] is None and (s['dialog'] != DIALOG_NEGOTIATION)
DECISION_TABLE = ((lambda s: s['family'] == CONFIRM_FAMILY_VALUE, ('confirm', MENU_OWNER_CONFIRM, ''), 'mages_confirm'), (lambda s: s['frame'] == FRAME_EDIT_EFFECTS, ('effect_menu', EFFECT_MENU_OWNER, ''), 'mages_effect_menu'), (lambda s: _is_menu_frame(s) and s['ptr_menu'], ('menu', MENU_OWNER, ''), 'mages_menu'), (lambda s: s['frame'] in (FRAME_MAIN_MENU, FRAME_SUB_MENU), _NONE, 'mages_menu_state'), (lambda s: s['img'] == CONFIRM_IMG and s['dialog'] == DIALOG_NORMAL and _popup_reply_frame(s) and (s['ident_text'] is True) and (_list_not_on(s) or (s['list_flag'] == LIST_ON and s['ident_at_ptr'] is True)), ('reply', REPLY_OWNER, 'detect_result'), 'mages_detect_reply'), (lambda s: s['img'] == INVENTORY_LIST_IMG and _detect_common(s) and _popup_reply_frame(s) and _list_not_on(s) and (s['sub'] in (None, 0)) and (s['view_desc_lo'] == DESC_LO_DETECT_REPLY) and (s['result_hint'] == DETECT_KNOWN_HINT), ('reply', REPLY_OWNER, 'detect_known'), 'mages_detect_reply'), (lambda s: s['img'] == CONFIRM_IMG and _detect_common(s) and _popup_reply_frame(s) and _list_not_on(s) and (s['sub'] in (None, 0)) and (s['view_desc_lo'] == DESC_LO_DETECT_REPLY) and (s['result_hint'] == DETECT_COST_HINT), ('reply', REPLY_OWNER, 'detect_cost'), 'mages_detect_reply'), (lambda s: s['img'] == INVENTORY_LIST_IMG and _detect_common(s) and (s['frame'] == FRAME_POPUP) and _list_not_on(s) and (s['ptr_in_menu_range'] is True) and (s['known_text'] is True), ('reply', REPLY_OWNER, 'detect_known'), 'mages_detect_reply'), (lambda s: s['img'] == CONFIRM_IMG and _detect_common(s) and _popup_reply_frame(s) and (s['view_desc_lo'] in DESC_LO_MENU_TO_LIST), _NONE, 'mages_menu_to_list'), (lambda s: s['img'] == CONFIRM_IMG and _detect_common(s) and _popup_reply_frame(s) and (_list_not_on(s) or s['sub'] in (None, 0)) and (s['cost_text'] is True), ('reply', REPLY_OWNER, 'detect_cost'), 'mages_detect_reply'), (lambda s: s['img'] in NEGOTIATION_IMGS, ('negotiation', NEGOTIATION_OWNER, ''), 'mages_negotiation'), (lambda s: s['img'] == BUYSPELL_IMG, ('spelldetail', MENU_OWNER_SPELLDETAIL, ''), 'mages_spelldetail'), (lambda s: s['form'], ('spellmaker', SPELLMAKER_OWNER, ''), 'mages_form'), (lambda s: s['ptr_menu'] and s['img'] == MENU_IMG, ('menu', MENU_OWNER, ''), 'mages_menu'), (lambda s: s['img'] == SPELLMAKER_IMG, ('spellmaker', SPELLMAKER_OWNER, ''), 'mages_spellmaker'), (lambda s: _spellmaker_return(s), ('spellmaker', SPELLMAKER_OWNER, ''), 'mages_spellmaker_return'), (lambda s: s['img'] in LIST_IMGS and _list_not_on(s) and bool(s['prompt_text']), ('prompt', MENU_OWNER_PROMPT, ''), 'mages_prompt'), (lambda s: s['img'] in LIST_IMGS and s['frame'] == FRAME_POPUP and (s['list_flag'] == LIST_ON), ('list', LIST_OWNER, ''), 'mages_list'), (lambda s: True, _NONE, 'mages_guild:seam'))

class MagesGuildNode(FacilityNode):
    name = 'mages_guild'
    menu_signatures = ((frozenset({'Buy', 'Detect Magic', 'Spellmaker', 'Steal', 'Exit'}), 'shop_menu', 'MENU OPTIONS'), (frozenset({'Buy', 'Detect Magic', 'Steal', 'Exit'}), 'shop_menu', 'MENU OPTIONS'), (frozenset({'Potions', 'Magic items', 'Spells'}), 'shop_menu', 'PICK ITEM'), (frozenset({'Potions', 'Spells'}), 'shop_menu', 'PICK ITEM'), (frozenset({'Potion', 'Magic item'}), 'shop_menu', 'PICK ITEM'))

    def classify_view(self, w, *, shop_state=None, shop_img_name: str='', **_signals) -> FacilityView:
        cached = peek_mages_view(w)
        if cached is not None:
            return cached
        from mages_signals import read_signals
        img = (shop_img_name or '').upper()
        has_foreground_snapshot = 'foreground_ptr' in _signals
        foreground_ptr = _signals.get('foreground_ptr')
        if not has_foreground_snapshot:
            try:
                from active_template_reader import read_current_text_pointer
                foreground_ptr = read_current_text_pointer(w._analyzer, w._anchor)
            except Exception:
                foreground_ptr = None
        try:
            sig = read_signals(w._analyzer, w._anchor, foreground_ptr=foreground_ptr, img=img, shop_state=shop_state, cache_on=w)
        except Exception:
            sig = {}
        view = self._classify_view_from_signals(sig)
        setattr(w, VIEW_ATTR, view)
        setattr(w, VIEW_SEQ_ATTR, getattr(w, '_poll_seq', None))
        self._log_view_diag(w, sig=sig, view=view)
        return view

    def view_for_poll(self, w, *, shop_state=None, shop_img_name: str=''):
        view = peek_mages_view(w)
        if view is not None:
            return view
        return self.classify_view(w, shop_state=shop_state, shop_img_name=shop_img_name)

    @staticmethod
    def _classify_view_from_signals(sig: dict) -> FacilityView:
        s = _Columns(sig)
        for cond, (kind, owner, reply_kind), reason in DECISION_TABLE:
            try:
                hit = bool(cond(s))
            except (KeyError, TypeError):
                hit = False
            if hit:
                return FacilityView(l4_kind=kind, render_owner=owner, l4_visible=bool(owner), reply_kind=reply_kind, signals_snapshot=sig, reason=reason)
        return FacilityView(signals_snapshot=sig, reason='mages_guild:seam')

    @staticmethod
    def _log_view_diag(w, *, sig: dict, view: FacilityView) -> None:
        g = sig.get
        desc_lo = g('view_desc_lo')
        prompt = g('prompt_text')
        prompt_en = prompt[0] if isinstance(prompt, tuple) and prompt else None
        key = (g('img'), view.l4_kind, view.reply_kind, view.reason, g('frame'), g('type'), g('list_flag'), g('dialog'), g('family'), g('sub'), desc_lo, g('ptr'), g('ptr_menu'), g('ptr_area'), g('cost_text'), g('ident_text'), g('known_text'), prompt_en)
        if key == getattr(w, '_mages_l4_diag_prev', None):
            return
        w._mages_l4_diag_prev = key
        _recog(_log, 'mages L4 view: img=%r kind=%s reply=%s reason=%s frame=%s type=%s list=%s dialog=%s family=%s sub=%s desc_lo=%s ptr=%s ptr_menu=%s ptr_area=%s cost_txt=%s ident_txt=%s known_txt=%s prompt_txt=%r', g('img'), view.l4_kind, view.reply_kind or '-', view.reason, _hex8(g('frame')), _hex8(g('type')), _hex8(g('list_flag')), _hex8(g('dialog')), _hex8(g('family')), _hex8(g('sub')), _hex8(desc_lo), _hex16(g('ptr')), g('ptr_menu'), g('ptr_area'), g('cost_text'), g('ident_text'), g('known_text'), prompt_en)

    def render(self, w, *, view=None, shop_state=None, shop_img_name: str='', top_level_state: str='', **_ctx):
        from normal_play.mages_guild_render_module import poll_mages_render
        if view is None:
            view = self.classify_view(w, shop_state=shop_state, shop_img_name=shop_img_name)
        return poll_mages_render(w, view=view, shop_state=shop_state, shop_img_name=shop_img_name, top_level_state=top_level_state)

    def on_exit(self, w) -> None:
        from normal_play.mages_guild_render_module import reset_mages_render_keys
        try:
            closed = w._ui_router.clear_if_owner_in(facility_owners_for_session(self.name), mode='translate', place_list_owners=_PLACE_LIST_OWNERS)
        except (AttributeError, RuntimeError) as exc:
            closed = ''
            _log.debug('facility stop display clear skipped: %s', exc)
        if closed:
            _log.info('facility session stopped -> clearing L4 display (session=%s owner=%r)', self.name, closed)
        if getattr(w, '_mages_reply_baselined', False):
            from normal_play.mages_reply_module import reset_mages_reply_state
            try:
                reset_mages_reply_state(w)
            except Exception:
                pass
        try:
            reset_mages_render_keys(w)
        except Exception:
            pass

    def suspend_for_story(self, w) -> None:
        from normal_play.mages_guild_render_module import _cleanup
        normal_owners = (MENU_OWNER, LIST_OWNER, SPELLMAKER_OWNER, EFFECT_MENU_OWNER, MENU_OWNER_CONFIRM, MENU_OWNER_SPELLDETAIL, MENU_OWNER_PROMPT, NEGOTIATION_OWNER, REPLY_OWNER)
        try:
            w._ui_router.notify_display_unit_replaced_in(normal_owners)
        except AttributeError:
            pass
        _cleanup(w, False, False, False)
        self.on_exit(w)

    def render_no_session_shop(self, w, *, shop_state, shop_img_name: str, shop_buy_active: bool, shop_menu_visible: bool):
        from normal_play.mages_guild_render_module import render_no_session_menu
        if render_no_session_menu(w, shop_state=shop_state, shop_img_name=shop_img_name):
            shop_menu_visible = True
        return (shop_buy_active, shop_menu_visible)

class _Columns:
    __slots__ = ('_sig',)

    def __init__(self, sig: dict) -> None:
        self._sig = sig if isinstance(sig, dict) else {}

    def __getitem__(self, name: str):
        return self._sig.get(name)
MAGES_GUILD_NODE = MagesGuildNode()
register_facility_node(MAGES_GUILD_NODE)
__all__ = ['MagesGuildNode', 'MAGES_GUILD_NODE', 'DECISION_TABLE', 'peek_mages_view', 'VIEW_ATTR', 'VIEW_SEQ_ATTR']
