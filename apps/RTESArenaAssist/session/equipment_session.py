from __future__ import annotations
from normal_play.equipment_l4_state import EQUIPMENT_OWNERS, EquipmentL4State, REPLY_STATES, get_equipment_l4_state
from .session_base import SessionBase, SessionContext

def _norm_facility_kind(fk: str) -> str:
    return (fk or '').upper().replace('_', '').replace(' ', '')
_EQUIPMENT_MIF_PREFIXES = ('EQUIP', 'ARMOR')
_OTHER_FACILITY_MIF_PREFIXES = ('TAVERN', 'TEMPLE', 'MAGE', 'PALACE')
_EQUIPMENT_OWNER_KINDS = frozenset({'shop_menu', 'equipment_list'})
_EQUIPMENT_PANEL_OWNERS = EQUIPMENT_OWNERS
_EQUIPMENT_MIDFLOW_START_STATES = frozenset(REPLY_STATES) | frozenset({EquipmentL4State.REPAIR_JOBS})
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
            state = detect_shop_popup_state(ctx.analyzer, ctx.anchor, top_level_state=ctx.top_level_state, img_name=ctx.img_name, in_interior=ctx.in_interior, screen_id=ctx.screen_id, interior_mif_name=ctx.interior_mif_name or '', area=ctx.area, active_facility_name='equipment' if self._active or self._is_equipment_context(ctx) else '')
            return (state.kind or 'none', state.owner_kind or '')
        except Exception:
            return ('none', '')

    @staticmethod
    def _resolve_l4_state(ctx: SessionContext):
        extras_state = ctx.extras.get('equipment_l4_state') if ctx.extras else None
        if extras_state is not None:
            try:
                return EquipmentL4State(extras_state)
            except ValueError:
                return EquipmentL4State.NONE
        w = ctx.extras.get('window') if ctx.extras else None
        if w is None or getattr(w, '_analyzer', None) is None:
            return EquipmentL4State.NONE
        try:
            snap = get_equipment_l4_state(w, img=(ctx.img_name or '').upper())
            return snap.state
        except Exception:
            return EquipmentL4State.NONE

    def _is_confirmed_equipment_facility(self, ctx: SessionContext) -> bool:
        if self._is_equipment_context(ctx):
            return True
        w = ctx.extras.get('window') if ctx.extras else None
        if w is None:
            return False
        return (getattr(w, '_interior_facility_kind', '') or '') == 'equipment'

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
        if not self._known_non_equipment_context(ctx) and self._is_confirmed_equipment_facility(ctx) and (self._resolve_l4_state(ctx) in _EQUIPMENT_MIDFLOW_START_STATES):
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
        state = self._resolve_l4_state(ctx)
        if state is not EquipmentL4State.NONE:
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
