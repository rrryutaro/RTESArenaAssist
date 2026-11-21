from __future__ import annotations
from .session_base import SessionBase, SessionContext
from .npc_chat_session import NPC_PHASE_ASKING
from .tavern_signals import observe_ask_about as _observe_ask_about_once
_TAVERN_NONE_HYSTERESIS_POLLS = 3

class TavernSession(SessionBase):
    name = 'tavern'
    bar_label_key = 'recognition.conv_shop_owner'
    is_facility_session = True

    def facility_l4_owners(self) -> frozenset:
        from session.tavern_node import TAVERN_NODE
        return frozenset(TAVERN_NODE.panel_owners)

    def on_facility_stopped(self, w) -> None:
        from session.tavern_node import TAVERN_NODE
        TAVERN_NODE.on_exit(w)

    def __init__(self) -> None:
        super().__init__()
        self._none_shop_polls = 0

    @staticmethod
    def _is_tavern_context(ctx: SessionContext) -> bool:
        return (ctx.facility_kind or '').upper() == 'TAVERN'

    @staticmethod
    def _known_non_tavern_context(ctx: SessionContext) -> bool:
        return (ctx.facility_kind or '').upper() != 'TAVERN'

    def _shop_state_of(self, ctx: SessionContext) -> tuple[str, str]:
        extras_kind = ctx.extras.get('shop_kind') if ctx.extras else None
        extras_facility = ctx.extras.get('owner_kind') if ctx.extras else None
        if extras_kind is not None or extras_facility is not None:
            kind = extras_kind if extras_kind is not None else 'none'
            from session.tavern_view import l4_of_shop_kind
            facility = extras_facility if extras_facility is not None else 'tavern' if l4_of_shop_kind(kind) else ''
            return (kind or 'none', facility or '')
        if ctx.top_level_state != 'normal-play':
            return ('none', '')
        if not ctx.in_interior:
            return ('none', '')
        w = ctx.extras.get('window') if ctx.extras else None
        if w is not None and getattr(w, '_analyzer', None) is not None:
            from session.tavern_signals import kind_facility_of_surface, tavern_surface_of
            return kind_facility_of_surface(tavern_surface_of(w, ctx.shop_state))
        from session.tavern_signals import shop_kind_facility_of
        from l3_facility import decided_by_mif
        return shop_kind_facility_of(ctx.shop_state, ctx.analyzer, ctx.anchor, l3_by_mif=decided_by_mif(ctx.interior_mif_name, ctx.in_interior))

    @staticmethod
    def _observe_ask_about(ctx: SessionContext):
        key = '_tavern_ask_about_obs'
        if ctx.extras is not None and key in ctx.extras:
            return ctx.extras[key]
        obs = _observe_ask_about_once(ctx.analyzer, ctx.anchor)
        if ctx.extras is not None:
            ctx.extras[key] = obs
        return obs

    def _view_of(self, ctx: SessionContext, kind: str, facility: str):
        obs = self._observe_ask_about(ctx) if ctx.npc_phase == NPC_PHASE_ASKING else None
        w = ctx.extras.get('window') if ctx.extras else None
        if w is None:
            import types
            w = types.SimpleNamespace(_analyzer=ctx.analyzer, _anchor=ctx.anchor, _poll_seq=None)
        elif getattr(w, '_analyzer', None) is None:
            return None
        override = ctx.extras.get('tavern_signals_override') if ctx.extras else None
        try:
            from session.tavern_node import TAVERN_NODE
            return TAVERN_NODE.classify_view(w, shop_kind=kind, shop_facility=facility, img=(ctx.img_name or '').upper(), in_interior=True, facility_tavern=True, npc_phase=ctx.npc_phase, ask_about_obs=obs, signals_override=override)
        except Exception:
            return None

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
        if not self._is_tavern_context(ctx):
            return False
        kind, facility = self._shop_state_of(ctx)
        from session.tavern_view import conversation_starts
        if conversation_starts(kind, facility):
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
        kind, facility = self._shop_state_of(ctx)
        view = self._view_of(ctx, kind, facility)
        if view is not None and view.l4_kind == 'menu':
            w = ctx.extras.get('window') if ctx.extras else None
            if w is not None and getattr(w, '_tavern_rumor_flow_active', False):
                w._tavern_rumor_flow_active = False
        if view is not None and view.continues:
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
            from ask_about_menu_parser import build_display_sub, build_panel_display_sub
        except ImportError:
            return
        kind, facility = self._shop_state_of(ctx)
        view = self._view_of(ctx, kind, facility)
        if view is None or not view.session_draws_rumor_type:
            if w._ui_router.clear_if_owner('tavern_rumor_type'):
                w._tavern_rumor_key_prev = None
            return
        _aa_marker, _aa_parsed, _aa_active_sub = self._observe_ask_about(ctx)
        if _aa_parsed is None:
            _aa_parsed = {}
        try:
            w._tavern_rumor_flow_active = True
            _rt_key = ('tavern_rumor_type', tuple((s.get('title', '') for s in _aa_parsed.get('sub_menus', []))))
            _rt_prev_key = getattr(w, '_tavern_rumor_key_prev', None)
            if _rt_key == _rt_prev_key:
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
