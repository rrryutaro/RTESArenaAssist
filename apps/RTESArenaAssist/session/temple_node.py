from __future__ import annotations
import logging
from .facility_node import FacilityNode, register_facility_node
_log = logging.getLogger('RTESArenaAssist')
_PLACE_LIST_OWNERS = frozenset({'npc_dialog', 'npc_conversation', 'npc_message'})

class TempleNode(FacilityNode):
    name = 'temple'
    has_conversation_session = True
    panel_owners = frozenset({'temple_menu', 'temple_active_template', 'temple_priest_reply', 'temple_cost', 'temple_prompt', 'temple_cure'})
    story_kind = 'temple'
    story_owner = 'temple_story'
    outside_conversation_owners = frozenset({story_owner})
    template_declarations = ((30199, 'donate_amount', 'temple_donate_amount', ('popup',), ('popup',)), (29728, '', 'tavern_cost_show', (), ('popup',)), (29748, '', 'tavern_cost_confirm', (), ('confirm',)))
    menu_signatures = ((frozenset({'Bless', 'Cure', 'Heal', 'Exit'}), 'shop_menu', 'MENU OPTIONS'),)

    def classify_view(self, w, *, shop_state=None, shop_img_name: str='', **_signals):
        from temple_signals import own_menu_of
        if own_menu_of(shop_state, window=w)[0]:
            from store_surface import publish_menu_front
            publish_menu_front(w)
        from normal_play.temple_render_module import classify_temple_view
        view = classify_temple_view(w, shop_state=shop_state, shop_img_name=shop_img_name)
        w._temple_view_l4_visible = bool(view.l4_visible)
        w._temple_view_l4_kind = view.l4_kind
        return view

    def render(self, w, *, view=None, shop_state=None, shop_img_name: str='', top_level_state: str='', **_ctx):
        from normal_play.temple_render_module import classify_temple_view, render_temple_view
        if view is None:
            view = classify_temple_view(w, shop_state=shop_state, shop_img_name=shop_img_name)
        return render_temple_view(w, view=view, shop_state=shop_state, shop_img_name=shop_img_name)
    owns_shop_replies = True

    def after_l3(self, w, *, img_name: str) -> None:
        from temple_signals import resolve_yesno_menu_back
        resolve_yesno_menu_back(w, img_name=img_name, temple_active=self.latch(w)[0])

    def bar_sub_label_key(self, w, *, active_session_name: str, screen_suppresses_conversation_label: bool, img_name: str) -> str:
        from session.temple_bar_label import temple_bar_sub_label_key
        return temple_bar_sub_label_key(w, active_session_name=active_session_name, screen_suppresses_conversation_label=screen_suppresses_conversation_label, img_name=img_name)

    def own_shop_state(self, w, *, area, in_interior: bool, interior_mif_name: str, top_level_state: str, img_name: str, screen_id, yesno_candidate_pointers: tuple):
        from normal_play.field_temple_module import detect_field_temple_shop_state
        if area != 'wilderness':
            return None
        return detect_field_temple_shop_state(w._analyzer, w._anchor, top_level_state=top_level_state, img_name=img_name, in_interior=in_interior, screen_id=screen_id, yesno_candidate_pointers=yesno_candidate_pointers, interior_mif_name=interior_mif_name)

    def poll_own_session(self, w, ctx) -> None:
        from normal_play.field_temple_module import poll_field_temple_session
        poll_field_temple_session(w, ctx)
        if getattr(w, '_field_temple_just_stopped', False):
            self.on_exit(w)

    def after_latch(self, w, *, img_name: str) -> None:
        from normal_play.temple_render_module import reset_keys_on_img_transition
        reset_keys_on_img_transition(w, img_name=img_name, temple_active_now=self.latch(w)[0])

    def latch(self, w) -> tuple[bool, bool]:
        active, started = super().latch(w)
        if getattr(w, '_field_temple_active_now', False):
            active = True
            started = started or bool(getattr(w, '_field_temple_just_started', False))
        return (active, started)

    def poll_reply_unit(self, w, *, shop_state, entry_handled: bool, img_name: str, shop_menu_visible: bool, area: str='') -> tuple[bool, bool]:
        from normal_play.temple_dialog_module import poll_temple_reply_unit
        active, started = self.latch(w)
        return poll_temple_reply_unit(w, shop_state=shop_state, temple_active_now=active, temple_just_started=started, entry_handled=entry_handled, img_name=img_name, shop_menu_visible=shop_menu_visible, area=area)

    def story_of(self, w, *, ptr, view) -> str:
        if getattr(w, '_field_temple_active_now', False):
            return ''
        from l3_facility import l3_decided_by_mif
        from normal_play.temple_story_module import is_strong_story_pointer, _dialog_body_source, _dialog_hold_pointer
        view_visible = bool(view is not None and getattr(view, 'l4_visible', False))
        if l3_decided_by_mif(w) and (_dialog_body_source(ptr) or _dialog_hold_pointer(ptr)) and (is_strong_story_pointer(ptr) or not view_visible):
            return 'temple'
        return ''

    def poll_story(self, w, *, active: bool, foreground_ptr=None) -> bool:
        from normal_play.temple_story_module import poll_temple_story
        if not active:
            return bool(poll_temple_story(w, temple_active=False))
        return bool(poll_temple_story(w, temple_active=True, foreground_ptr=foreground_ptr))

    def prepare_render(self, w) -> None:
        if self.latch(w)[0]:
            try:
                from temple_dialog_reader import temple_gate_foreground
                w._temple_menu_fg, w._temple_popup_fg, _gate_now = temple_gate_foreground(w, w._analyzer, w._anchor)
            except Exception:
                w._temple_menu_fg = False
                w._temple_popup_fg = False
        else:
            _reset_temple_gate(w)

    def on_l3_exit(self, w) -> None:
        from normal_play.temple_dialog_module import reset_temple_reply_on_stop
        if getattr(w, '_temple_dialog_context_prev', False):
            reset_temple_reply_on_stop(w)
        w._temple_dialog_context_prev = False
        _reset_temple_gate(w)
        from temple_signals import YESNO_MENU_BACK_ATTR
        setattr(w, YESNO_MENU_BACK_ATTR, False)
        w._temple_last_img_prev = ''
        from normal_play.field_temple_module import stop_field_temple_session
        if stop_field_temple_session(w):
            self.on_exit(w)
        super().on_l3_exit(w)

    def on_exit(self, w) -> None:
        from normal_play.temple_render_module import MENU_KEY
        current = getattr(w, '_panel_owner', '') or ''
        if current in frozenset(self.panel_owners):
            _log.info('facility session stopped -> clearing L4 display (session=%s owner=%r)', self.name, current)
            try:
                w._ui_router.clear_if_owner(current, mode='translate', clear_place_list=current in _PLACE_LIST_OWNERS)
            except (AttributeError, RuntimeError) as exc:
                _log.debug('facility stop display clear skipped: %s', exc)
        try:
            setattr(w, MENU_KEY, None)
        except AttributeError:
            pass
        try:
            from normal_play.temple_cost_module import reset_temple_cost_on_stop
            reset_temple_cost_on_stop(w)
        except Exception:
            pass

    def suspend_for_story(self, w) -> None:
        current = getattr(w, '_panel_owner', '') or ''
        if current in frozenset(self.panel_owners):
            try:
                w._ui_router.notify_display_unit_replaced(current)
            except AttributeError:
                pass
        self.on_exit(w)

    def render_no_session_shop(self, w, *, shop_state, shop_img_name: str, shop_buy_active: bool, shop_menu_visible: bool):
        from normal_play.temple_render_module import render_no_session_menu
        if render_no_session_menu(w, shop_state=shop_state, shop_img_name=shop_img_name):
            shop_menu_visible = True
        return (shop_buy_active, shop_menu_visible)

def _reset_temple_gate(w) -> None:
    w._temple_menu_fg = False
    w._temple_popup_fg = False
    w._temple_gate_stable_value = None
    w._temple_gate_stable_count = 0
TEMPLE_NODE = TempleNode()
register_facility_node(TEMPLE_NODE)
__all__ = ['TempleNode', 'TEMPLE_NODE']
