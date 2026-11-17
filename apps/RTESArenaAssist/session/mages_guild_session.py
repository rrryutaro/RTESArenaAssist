from __future__ import annotations
from .session_base import SessionBase, SessionContext
_MAGES_FACILITY_KINDS = frozenset({'shop_menu'})
_MAGES_NPC_PHASES = frozenset({111, 112})
_MAGES_NONE_HYSTERESIS_POLLS = 3

class MagesGuildSession(SessionBase):
    name = 'mages_guild'
    bar_label_key = 'recognition.conv_shop_owner'
    is_facility_session = True

    def facility_l4_owners(self) -> frozenset:
        from session.mages_guild_node import MAGES_GUILD_NODE
        return frozenset(MAGES_GUILD_NODE.panel_owners)

    def on_facility_stopped(self, w) -> None:
        from session.mages_guild_node import MAGES_GUILD_NODE
        MAGES_GUILD_NODE.on_exit(w)

    def __init__(self) -> None:
        super().__init__()
        self._none_shop_polls = 0
        self._last_img: str = ''

    @staticmethod
    def _is_mages_context(ctx: SessionContext) -> bool:
        return (ctx.facility_kind or '').upper() == 'MAGES_GUILD'

    @staticmethod
    def _known_non_mages_context(ctx: SessionContext) -> bool:
        return (ctx.facility_kind or '').upper() != 'MAGES_GUILD'

    def _shop_state_of(self, ctx: SessionContext) -> tuple[str, str]:
        extras_kind = ctx.extras.get('shop_kind') if ctx.extras else None
        extras_facility = ctx.extras.get('owner_kind') if ctx.extras else None
        if extras_kind is not None or extras_facility is not None:
            kind = extras_kind if extras_kind is not None else 'none'
            facility = extras_facility if extras_facility is not None else ''
            return (kind or 'none', facility or '')
        if ctx.top_level_state != 'normal-play':
            return ('none', '')
        if not ctx.in_interior:
            return ('none', '')
        from mages_signals import own_menu_of
        if own_menu_of(ctx.shop_state)[0]:
            return ('shop_menu', 'mages_guild')
        return ('none', '')

    @staticmethod
    def _is_guild_modal_img(ctx: SessionContext) -> bool:
        from mages_signals import is_guild_modal_img
        return is_guild_modal_img(ctx.img_name or '')

    @staticmethod
    def _is_negotiation_active(ctx: SessionContext) -> bool:
        from mages_signals import NEGOTIATION_IMGS
        img = (ctx.img_name or '').upper()
        return bool(img) and img in NEGOTIATION_IMGS

    @staticmethod
    def _is_mages_conversation_phase(ctx: SessionContext) -> bool:
        return ctx.npc_phase in _MAGES_NPC_PHASES

    @property
    def last_img(self) -> str:
        return self._last_img

    def _stop(self) -> bool:
        self._none_shop_polls = 0
        self._last_img = ''
        self._set_active(False)
        return True

    def try_start(self, ctx: SessionContext) -> bool:
        if self._active:
            return False
        if ctx.top_level_state != 'normal-play' or not ctx.in_interior:
            return False
        if not self._is_mages_context(ctx):
            return False
        kind, facility = self._shop_state_of(ctx)
        if facility == 'mages_guild' and kind in _MAGES_FACILITY_KINDS:
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ''
            self._set_active(True)
            return True
        return False

    def try_stop(self, ctx: SessionContext) -> bool:
        if not self._active:
            return False
        if ctx.top_level_state != 'normal-play' or not ctx.in_interior:
            return self._stop()
        if self._known_non_mages_context(ctx):
            return self._stop()
        kind, facility = self._shop_state_of(ctx)
        if facility == 'mages_guild' and kind in _MAGES_FACILITY_KINDS:
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ''
            return False
        if self._is_guild_modal_img(ctx):
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ''
            return False
        if self._is_negotiation_active(ctx):
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ''
            return False
        if self._is_mages_conversation_phase(ctx):
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ''
            return False
        self._none_shop_polls += 1
        if self._none_shop_polls >= _MAGES_NONE_HYSTERESIS_POLLS:
            return self._stop()
        self._last_img = ctx.img_name or ''
        return False

    def poll(self, ctx: SessionContext) -> None:
        return None
__all__ = ['MagesGuildSession']
