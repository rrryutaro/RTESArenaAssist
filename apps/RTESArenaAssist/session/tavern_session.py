from __future__ import annotations
from .session_base import SessionBase, SessionContext
from .npc_chat_session import NPC_PHASE_ASKING
_TAVERN_OWNER_KINDS = frozenset({'shop_menu', 'shop_buy', 'shop_rooms', 'shop_rumor_type'})
_TAVERN_NONE_HYSTERESIS_POLLS = 3

class TavernSession(SessionBase):
    name = 'tavern'

    def __init__(self) -> None:
        super().__init__()
        self._none_shop_polls = 0

    @staticmethod
    def _is_tavern_context(ctx: SessionContext) -> bool:
        mif = (ctx.interior_mif_name or '').upper()
        if mif.startswith('TAVERN'):
            return True
        if ctx.facility_kind == 'TAVERN':
            return True
        return False

    @staticmethod
    def _facility_info_unknown(ctx: SessionContext) -> bool:
        return not ctx.interior_mif_name and (not ctx.facility_kind)

    @staticmethod
    def _known_non_tavern_context(ctx: SessionContext) -> bool:
        mif = (ctx.interior_mif_name or '').upper()
        if mif and (not mif.startswith('TAVERN')):
            return True
        if ctx.facility_kind and ctx.facility_kind != 'TAVERN':
            return True
        return False

    def _detect_shop_state(self, ctx: SessionContext) -> tuple[str, str]:
        extras_kind = ctx.extras.get('shop_kind') if ctx.extras else None
        extras_owner = ctx.extras.get('owner_kind') if ctx.extras else None
        if extras_kind is not None or extras_owner is not None:
            kind = extras_kind if extras_kind is not None else 'none'
            owner = extras_owner if extras_owner is not None else 'tavern' if kind in _TAVERN_OWNER_KINDS else ''
            return (kind or 'none', owner or '')
        try:
            from shop_popup_detector import detect_shop_popup_state
        except ImportError:
            return ('none', '')
        if ctx.top_level_state != 'normal-play':
            return ('none', '')
        if not ctx.in_interior:
            return ('none', '')
        w = ctx.extras.get('window') if ctx.extras else None
        _allow_recovery = bool(getattr(w, '_yesno_menu_recovery_last', False)) if w else False
        try:
            state = detect_shop_popup_state(ctx.analyzer, ctx.anchor, top_level_state=ctx.top_level_state, img_name=ctx.img_name, in_interior=ctx.in_interior, screen_id=ctx.screen_id, allow_yesno_menu_recovery=_allow_recovery, interior_mif_name=ctx.interior_mif_name or '', active_facility_name='tavern' if self._active or self._is_tavern_context(ctx) else '')
            kind = state.kind or 'none'
            owner = state.owner_kind or ''
            if _allow_recovery and (not owner) and (kind in _TAVERN_OWNER_KINDS):
                owner = 'tavern'
            return (kind, owner)
        except Exception:
            return ('none', '')

    @staticmethod
    def _is_negotiation_active(ctx: SessionContext) -> bool:
        img = (ctx.img_name or '').upper()
        if not img:
            return False
        if img == 'YESNO.IMG':
            return False
        try:
            from negotiation_reader import get_negotiation_profile
        except ImportError:
            return False
        return get_negotiation_profile(img) is not None
    _TAVERN_PANEL_OWNERS = frozenset({'tavern_rumor_type', 'negotiation', 'active_template', 'npc_dialog'})

    def _is_tavern_panel_owned(self, ctx: SessionContext) -> bool:
        extras_owner = ctx.extras.get('tavern_panel_owner') if ctx.extras else None
        if extras_owner is not None:
            return extras_owner in self._TAVERN_PANEL_OWNERS
        w = ctx.extras.get('window') if ctx.extras else None
        if w is None:
            return False
        owner = getattr(w, '_panel_owner', '') or ''
        return owner in self._TAVERN_PANEL_OWNERS

    def _is_tavern_template_surface_active(self, ctx: SessionContext) -> bool:
        extras_flag = ctx.extras.get('tavern_template_surface_active') if ctx.extras else None
        if extras_flag is not None:
            return bool(extras_flag)
        try:
            from active_template_reader import read_active_template_candidates, template_surface_kind
        except ImportError:
            return False
        try:
            candidates = read_active_template_candidates(ctx.analyzer, ctx.anchor)
        except Exception:
            return False
        _tavern_surface_kinds = ('tavern_stay_days', 'tavern_sneak_confirm', 'tavern_sneak_result')
        for c in candidates:
            try:
                kind = template_surface_kind(c)
            except Exception:
                continue
            if kind in _tavern_surface_kinds:
                return True
        return False

    def _is_tavern_rumor_type_continuation(self, ctx: SessionContext) -> bool:
        extras_flag = ctx.extras.get('tavern_rumor_type_active') if ctx.extras else None
        if extras_flag is not None:
            return bool(extras_flag)
        if ctx.npc_phase != NPC_PHASE_ASKING:
            return False
        try:
            from arena_bridge import read_ask_about_menu
            from ask_about_menu_parser import parse_menu, detect_active_sub_menu_title
            from popup11_list_detector import read_active_menu_marker
        except ImportError:
            return False
        try:
            marker = read_active_menu_marker(ctx.analyzer, ctx.anchor)
            if not marker:
                return False
            raw = read_ask_about_menu(ctx.analyzer, ctx.anchor)
            parsed = parse_menu(raw)
            title = detect_active_sub_menu_title(parsed, marker)
            return title == 'Rumor Type'
        except Exception:
            return False

    def _stop(self, ctx: SessionContext | None=None) -> bool:
        self._none_shop_polls = 0
        self._set_active(False)
        if ctx is not None:
            w = ctx.extras.get('window') if ctx.extras else None
            if w is not None:
                try:
                    w._tavern_rumor_key_prev = None
                    w._ui_router.clear_if_owner('tavern_rumor_type')
                except AttributeError:
                    pass
                w._tavern_rumor_flow_active = False
        return True

    def try_start(self, ctx: SessionContext) -> bool:
        if self._active:
            return False
        if ctx.top_level_state != 'normal-play' or not ctx.in_interior:
            return False
        if not (self._is_tavern_context(ctx) or self._facility_info_unknown(ctx)):
            return False
        kind, owner = self._detect_shop_state(ctx)
        if owner == 'tavern' and kind in _TAVERN_OWNER_KINDS:
            self._none_shop_polls = 0
            self._set_active(True)
            return True
        return False

    def try_stop(self, ctx: SessionContext) -> bool:
        if not self._active:
            return False
        if ctx.top_level_state != 'normal-play' or not ctx.in_interior:
            return self._stop(ctx)
        if self._known_non_tavern_context(ctx):
            return self._stop(ctx)
        kind, owner = self._detect_shop_state(ctx)
        if owner == 'tavern' and kind == 'shop_menu':
            w = ctx.extras.get('window') if ctx.extras else None
            if w is not None and getattr(w, '_tavern_rumor_flow_active', False):
                w._tavern_rumor_flow_active = False
        _w_view = ctx.extras.get('window') if ctx.extras else None
        if _w_view is not None and getattr(_w_view, '_tavern_view_l4_visible', False):
            self._none_shop_polls = 0
            return False
        if owner == 'tavern' and kind in _TAVERN_OWNER_KINDS:
            self._none_shop_polls = 0
            return False
        if self._is_negotiation_active(ctx):
            self._none_shop_polls = 0
            return False
        if self._is_tavern_rumor_type_continuation(ctx):
            self._none_shop_polls = 0
            return False
        if self._is_tavern_template_surface_active(ctx):
            self._none_shop_polls = 0
            return False
        if self._is_tavern_panel_owned(ctx):
            self._none_shop_polls = 0
            return False
        self._none_shop_polls += 1
        if self._none_shop_polls >= _TAVERN_NONE_HYSTERESIS_POLLS:
            return self._stop(ctx)
        return False

    def poll(self, ctx: SessionContext) -> None:
        w = ctx.extras.get('window') if ctx.extras else None
        if w is None:
            return
        try:
            from arena_bridge import read_ask_about_menu
            from ask_about_menu_parser import parse_menu, build_display_sub, build_panel_display_sub, detect_active_sub_menu_title
            from popup11_list_detector import read_active_menu_marker
        except ImportError:
            return
        try:
            _aa_marker = read_active_menu_marker(w._analyzer, w._anchor)
            _aa_raw = read_ask_about_menu(w._analyzer, w._anchor)
            _aa_parsed = parse_menu(_aa_raw)
            _aa_active_sub = detect_active_sub_menu_title(_aa_parsed, _aa_marker)
        except Exception:
            _aa_active_sub = None
        _rumor_type_visible = _aa_active_sub == 'Rumor Type'
        if not _rumor_type_visible:
            if w._ui_router.is_owner('tavern_rumor_type'):
                w._tavern_rumor_key_prev = None
                w._ui_router.clear_if_owner('tavern_rumor_type')
        if ctx.npc_phase != NPC_PHASE_ASKING:
            return
        kind, _ = self._detect_shop_state(ctx)
        if kind in ('shop_menu', 'shop_buy', 'shop_rumor_type'):
            return
        try:
            if not _rumor_type_visible:
                return
            w._tavern_rumor_flow_active = True
            _rt_key = ('tavern_rumor_type', tuple((s.get('title', '') for s in _aa_parsed.get('sub_menus', []))))
            _rt_owner_taken = w._ui_router.current_owner() != 'tavern_rumor_type'
            _rt_prev_key = getattr(w, '_tavern_rumor_key_prev', None)
            if _rt_key == _rt_prev_key and (not _rt_owner_taken):
                return
            w._tavern_rumor_key_prev = _rt_key
            _rt_tab_en, _rt_tab_ja = build_display_sub(_aa_parsed, sub_title='Rumor Type')
            _rt_panel_en, _rt_panel_ja = build_panel_display_sub(_aa_parsed, sub_title='Rumor Type')
            w._ui_router.update_translation('tavern_rumor_type', _rt_tab_en, _rt_tab_ja, panel_en=_rt_panel_en, panel_ja=_rt_panel_ja)
        except Exception:
            import logging
            logging.getLogger('RTESArenaAssist').exception('tavern rumor type display failed')

    def on_other_session_started(self, ctx: SessionContext) -> None:
        w = ctx.extras.get('window') if ctx.extras else None
        if w is not None:
            try:
                w._tavern_rumor_key_prev = None
                w._ui_router.clear_if_owner('tavern_rumor_type')
            except AttributeError:
                pass
        super().on_other_session_started(ctx)
__all__ = ['TavernSession']
