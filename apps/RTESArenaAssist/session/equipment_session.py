from __future__ import annotations
from .session_base import SessionBase, SessionContext

def _norm_facility_kind(fk: str) -> str:
    return (fk or '').upper().replace('_', '').replace(' ', '')
_EQUIPMENT_MIF_PREFIXES = ('EQUIP', 'ARMOR')
_OTHER_FACILITY_MIF_PREFIXES = ('TAVERN', 'TEMPLE', 'MAGE', 'PALACE')
_EQUIPMENT_OWNER_KINDS = frozenset({'shop_menu', 'equipment_list'})
_EQUIPMENT_PANEL_OWNERS = frozenset({'equipment_menu', 'equipment_list', 'equipment_negotiation', 'equipment_reply'})
_EQUIPMENT_REPLY_START_IMGS = frozenset({'YESNO.IMG', 'NEWPOP.IMG', 'FACES00.CIF'})
_EQUIPMENT_REPLY_PREFIXES = ('Your ', 'Fixing that ', 'Sure I could fix that ', 'Fine. I can get it done in ', "Fine, I'll charge you ", "Then I'll get started", "Good, I'll get to it", 'I understand. You might consider', 'Well, if you change your mind', "Can't you afford it?", "Can't you wait that long?", "Maybe you're not interested?", 'I can cut down the time', 'I can cut the cost')
_EQUIPMENT_NONE_HYSTERESIS_POLLS = 3

class EquipmentSession(SessionBase):
    name = 'equipment'

    def __init__(self) -> None:
        super().__init__()
        self._none_shop_polls = 0
        self._last_img: str = ''

    @staticmethod
    def _is_equipment_context(ctx: SessionContext) -> bool:
        mif = (ctx.interior_mif_name or '').upper()
        if mif.startswith(_EQUIPMENT_MIF_PREFIXES):
            return True
        if _norm_facility_kind(ctx.facility_kind) == 'EQUIPMENT':
            return True
        return False

    @staticmethod
    def _known_non_equipment_context(ctx: SessionContext) -> bool:
        mif = (ctx.interior_mif_name or '').upper()
        if mif and mif.startswith(_OTHER_FACILITY_MIF_PREFIXES):
            return True
        fk = _norm_facility_kind(ctx.facility_kind)
        if fk and fk != 'EQUIPMENT':
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
            state = detect_shop_popup_state(ctx.analyzer, ctx.anchor, top_level_state=ctx.top_level_state, img_name=ctx.img_name, in_interior=ctx.in_interior, screen_id=ctx.screen_id, interior_mif_name=ctx.interior_mif_name or '', active_facility_name='equipment' if self._active or self._is_equipment_context(ctx) else '')
            return (state.kind or 'none', state.owner_kind or '')
        except Exception:
            return ('none', '')

    @staticmethod
    def _is_yesno_active(ctx: SessionContext) -> bool:
        return (ctx.img_name or '').upper() == 'YESNO.IMG'

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

    def _is_equipment_panel_owned(self, ctx: SessionContext) -> bool:
        extras_owner = ctx.extras.get('equipment_panel_owner') if ctx.extras else None
        if extras_owner is not None:
            return extras_owner in _EQUIPMENT_PANEL_OWNERS
        w = ctx.extras.get('window') if ctx.extras else None
        if w is None:
            return False
        owner = getattr(w, '_panel_owner', '') or ''
        return owner in _EQUIPMENT_PANEL_OWNERS

    @staticmethod
    def _has_equipment_reply_signal(ctx: SessionContext) -> bool:
        if (ctx.img_name or '').upper() not in _EQUIPMENT_REPLY_START_IMGS:
            return False
        if ctx.analyzer is None:
            return False
        try:
            from popup11_response_reader import read_response_candidates_all
            cands = read_response_candidates_all(ctx.analyzer, ctx.anchor)
        except Exception:
            return False
        for cand in cands:
            if not cand.lookup_hit:
                continue
            text = cand.text or ''
            if text.startswith('Your ') and 'repair' not in text:
                continue
            if text.startswith(_EQUIPMENT_REPLY_PREFIXES):
                return True
        return False

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
        if owner == 'equipment' and kind in _EQUIPMENT_OWNER_KINDS:
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ''
            self._set_active(True)
            return True
        if not self._known_non_equipment_context(ctx) and self._has_equipment_reply_signal(ctx):
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
        if self._known_non_equipment_context(ctx):
            return self._stop()
        kind, owner = self._detect_shop_state(ctx)
        if owner == 'equipment' and kind in _EQUIPMENT_OWNER_KINDS:
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ''
            return False
        if self._is_yesno_active(ctx):
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ''
            return False
        if self._is_negotiation_active(ctx):
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ''
            return False
        if self._is_equipment_panel_owned(ctx):
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ''
            return False
        self._none_shop_polls += 1
        if self._none_shop_polls >= _EQUIPMENT_NONE_HYSTERESIS_POLLS:
            return self._stop()
        self._last_img = ctx.img_name or ''
        return False

    def poll(self, ctx: SessionContext) -> None:
        return None
__all__ = ['EquipmentSession']
