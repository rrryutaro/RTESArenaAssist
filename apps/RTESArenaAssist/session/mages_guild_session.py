from __future__ import annotations
from .session_base import SessionBase, SessionContext

def _norm_facility_kind(fk: str) -> str:
    return (fk or '').upper().replace('_', '').replace(' ', '')
_MAGES_MIF_PREFIXES = ('MAGE',)
_OTHER_FACILITY_MIF_PREFIXES = ('TAVERN', 'TEMPLE', 'EQUIP', 'ARMOR', 'PALACE')
_MAGES_OWNER_KINDS = frozenset({'shop_menu'})
_MAGES_UI_IMGS = frozenset({'MENU_RT.IMG', 'SPELLMKR.IMG', 'BUYSPELL.IMG', 'YESNO.IMG', 'NEGOTBUT.IMG', 'POPUP.IMG', 'POPUP7.IMG', 'NEWPOP.IMG'})
_MAGES_NPC_PHASES = frozenset({111, 112})
_MAGES_PANEL_OWNERS = frozenset({'mages_menu', 'mages_list', 'mages_spellmaker', 'mages_effect_menu', 'mages_spelldetail', 'mages_prompt', 'mages_confirm', 'mages_negotiation', 'mages_reply'})
_MAGES_NONE_HYSTERESIS_POLLS = 3

class MagesGuildSession(SessionBase):
    name = 'mages_guild'

    def __init__(self) -> None:
        super().__init__()
        self._none_shop_polls = 0
        self._last_img: str = ''

    @staticmethod
    def _is_mages_context(ctx: SessionContext) -> bool:
        mif = (ctx.interior_mif_name or '').upper()
        if mif.startswith(_MAGES_MIF_PREFIXES):
            return True
        if _norm_facility_kind(ctx.facility_kind) == 'MAGESGUILD':
            return True
        return False

    @staticmethod
    def _known_non_mages_context(ctx: SessionContext) -> bool:
        mif = (ctx.interior_mif_name or '').upper()
        if mif and mif.startswith(_OTHER_FACILITY_MIF_PREFIXES):
            return True
        fk = _norm_facility_kind(ctx.facility_kind)
        if fk and fk != 'MAGESGUILD':
            return True
        return False

    def _detect_shop_state(self, ctx: SessionContext) -> tuple[str, str]:
        extras_kind = ctx.extras.get('shop_kind') if ctx.extras else None
        extras_owner = ctx.extras.get('owner_kind') if ctx.extras else None
        if extras_kind is not None or extras_owner is not None:
            kind = extras_kind if extras_kind is not None else 'none'
            owner = extras_owner if extras_owner is not None else ''
            return (kind or 'none', owner or '')
        try:
            from shop_popup_detector import detect_shop_popup_state
        except ImportError:
            return ('none', '')
        if ctx.top_level_state != 'normal-play':
            return ('none', '')
        if not ctx.in_interior:
            return ('none', '')
        try:
            state = detect_shop_popup_state(ctx.analyzer, ctx.anchor, top_level_state=ctx.top_level_state, img_name=ctx.img_name, in_interior=ctx.in_interior, screen_id=ctx.screen_id, interior_mif_name=ctx.interior_mif_name or '', active_facility_name='mages_guild' if self._active or self._is_mages_context(ctx) else '')
            return (state.kind or 'none', state.owner_kind or '')
        except Exception:
            return ('none', '')

    @staticmethod
    def _is_guild_modal_img(ctx: SessionContext) -> bool:
        img = (ctx.img_name or '').upper()
        return img in _MAGES_UI_IMGS or (img.startswith('FORM') and img.endswith('.IMG'))

    @staticmethod
    def _is_negotiation_active(ctx: SessionContext) -> bool:
        img = (ctx.img_name or '').upper()
        if not img:
            return False
        try:
            from negotiation_reader import get_negotiation_profile
        except ImportError:
            return False
        return get_negotiation_profile(img) is not None

    def _is_mages_panel_owned(self, ctx: SessionContext) -> bool:
        extras_owner = ctx.extras.get('mages_panel_owner') if ctx.extras else None
        if extras_owner is not None:
            return extras_owner in _MAGES_PANEL_OWNERS
        w = ctx.extras.get('window') if ctx.extras else None
        if w is None:
            return False
        owner = getattr(w, '_panel_owner', '') or ''
        return owner in _MAGES_PANEL_OWNERS

    def _is_mages_panel_surface_active(self, ctx: SessionContext) -> bool:
        if not self._is_mages_panel_owned(ctx):
            return False
        if self._is_guild_modal_img(ctx):
            return True
        if self._is_negotiation_active(ctx):
            return True
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
        kind, owner = self._detect_shop_state(ctx)
        if owner == 'mages_guild' and kind in _MAGES_OWNER_KINDS:
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
        kind, owner = self._detect_shop_state(ctx)
        if owner == 'mages_guild' and kind in _MAGES_OWNER_KINDS:
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
        if self._is_mages_panel_surface_active(ctx):
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
