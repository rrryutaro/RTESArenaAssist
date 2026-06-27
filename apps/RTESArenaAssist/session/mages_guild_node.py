from __future__ import annotations
from .facility_node import FacilityNode, FacilityView, register_facility_node

class MagesGuildNode(FacilityNode):
    name = 'mages_guild'
    menu_signatures = ((frozenset({'Buy', 'Detect Magic', 'Spellmaker', 'Steal', 'Exit'}), 'shop_menu', 'MENU OPTIONS'), (frozenset({'Potions', 'Magic items', 'Spells'}), 'shop_menu', 'PICK ITEM'), (frozenset({'Potion', 'Magic item'}), 'shop_menu', 'PICK ITEM'))

    def classify_view(self, w, *, shop_state=None, shop_img_name: str='', **_signals) -> FacilityView:
        from normal_play.mages_guild_render_module import MENU_OWNER, LIST_OWNER, SPELLMAKER_OWNER, EFFECT_MENU_OWNER, MENU_OWNER_CONFIRM, MENU_OWNER_SPELLDETAIL, MENU_OWNER_PROMPT, NEGOTIATION_OWNER, LIST_IMGS, SPELLMAKER_IMG, BUYSPELL_IMG, _CONFIRM_FAMILY, _is_negotiation_img, _last_spellmaker_list_title, _is_spellmaker_return_from_residual_list, _resolve_response_prompt
        from normal_play.mages_reply_module import REPLY_OWNER
        from mages_signals import classify, detect_magic_reply_kind_from_memory, read_signals, LIST_ON
        img = (shop_img_name or '').upper()
        try:
            sig = read_signals(w._analyzer, w._anchor)
        except Exception:
            sig = {}
        state = classify(sig)
        is_menu_state = state in ('main_menu', 'buy_submenu', 'steal_menu')
        has_menu_state = shop_state is not None and shop_state.kind == 'shop_menu' and (getattr(shop_state, 'owner_kind', '') == 'mages_guild')
        if sig.get('family') == _CONFIRM_FAMILY:
            return FacilityView(l4_kind='confirm', render_owner=MENU_OWNER_CONFIRM, l4_visible=True, reason='mages_confirm')
        if state == 'edit_effects_menu':
            return FacilityView(l4_kind='effect_menu', render_owner=EFFECT_MENU_OWNER, l4_visible=True, reason='mages_effect_menu')
        if is_menu_state and has_menu_state:
            return FacilityView(l4_kind='menu', render_owner=MENU_OWNER, l4_visible=True, reason='mages_menu')
        if is_menu_state:
            return FacilityView(reason='mages_menu_state')
        if detect_magic_reply_kind_from_memory(w._analyzer, w._anchor, img, sig):
            return FacilityView(l4_kind='reply', render_owner=REPLY_OWNER, l4_visible=True, reason='mages_detect_reply')
        if _is_negotiation_img(img):
            return FacilityView(l4_kind='negotiation', render_owner=NEGOTIATION_OWNER, l4_visible=True, reason='mages_negotiation')
        if img == BUYSPELL_IMG:
            return FacilityView(l4_kind='spelldetail', render_owner=MENU_OWNER_SPELLDETAIL, l4_visible=True, reason='mages_spelldetail')
        if img.startswith('FORM') and img.endswith('.IMG'):
            return FacilityView(l4_kind='spellmaker', render_owner=SPELLMAKER_OWNER, l4_visible=True, reason='mages_form')
        if has_menu_state and img == 'MENU_RT.IMG':
            return FacilityView(l4_kind='menu', render_owner=MENU_OWNER, l4_visible=True, reason='mages_menu')
        if img == SPELLMAKER_IMG:
            return FacilityView(l4_kind='spellmaker', render_owner=SPELLMAKER_OWNER, l4_visible=True, reason='mages_spellmaker')
        if img in LIST_IMGS:
            if _is_spellmaker_return_from_residual_list(w, sig, img, state):
                return FacilityView(l4_kind='spellmaker', render_owner=SPELLMAKER_OWNER, l4_visible=True, reason='mages_spellmaker_return')
            if sig.get('list') not in (None, LIST_ON):
                if _last_spellmaker_list_title(w):
                    return FacilityView(l4_kind='spellmaker', render_owner=SPELLMAKER_OWNER, l4_visible=True, reason='mages_spellmaker_return')
                if _resolve_response_prompt(w):
                    return FacilityView(l4_kind='prompt', render_owner=MENU_OWNER_PROMPT, l4_visible=True, reason='mages_prompt')
            if state == 'list':
                return FacilityView(l4_kind='list', render_owner=LIST_OWNER, l4_visible=True, reason='mages_list')
        return FacilityView(reason='mages_guild:seam')

    def render(self, w, *, view=None, shop_state=None, shop_img_name: str='', top_level_state: str='', **_ctx):
        from normal_play.mages_guild_render_module import poll_mages_render
        if view is None:
            view = self.classify_view(w, shop_state=shop_state, shop_img_name=shop_img_name)
        return poll_mages_render(w, view=view, shop_state=shop_state, shop_img_name=shop_img_name, top_level_state=top_level_state)

    def on_exit(self, w) -> None:
        from normal_play.mages_guild_render_module import MENU_OWNER, LIST_OWNER, SPELLMAKER_OWNER, EFFECT_MENU_OWNER, MENU_OWNER_CONFIRM, MENU_OWNER_SPELLDETAIL, MENU_OWNER_PROMPT, NEGOTIATION_OWNER
        from normal_play.mages_reply_module import REPLY_OWNER
        for owner in (MENU_OWNER, LIST_OWNER, SPELLMAKER_OWNER, EFFECT_MENU_OWNER, MENU_OWNER_CONFIRM, MENU_OWNER_SPELLDETAIL, MENU_OWNER_PROMPT, NEGOTIATION_OWNER, REPLY_OWNER):
            try:
                if w._panel_owner == owner:
                    w._ui_router.clear_if_owner(owner)
            except AttributeError:
                pass
MAGES_GUILD_NODE = MagesGuildNode()
register_facility_node(MAGES_GUILD_NODE)
__all__ = ['MagesGuildNode', 'MAGES_GUILD_NODE']
