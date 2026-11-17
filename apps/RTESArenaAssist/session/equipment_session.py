from __future__ import annotations
from normal_play.equipment_l4_state import EQUIPMENT_OWNERS, EquipmentL4State, get_equipment_l4_state
from .session_base import SessionBase, SessionContext
_EQUIPMENT_PANEL_OWNERS = EQUIPMENT_OWNERS
_EQUIPMENT_NONE_HYSTERESIS_POLLS = 3

class EquipmentSession(SessionBase):
    name = 'equipment'
    bar_label_key = 'recognition.conv_shop_owner'
    is_facility_session = True

    def facility_l4_owners(self) -> frozenset:
        from session.equipment_node import EQUIPMENT_NODE
        return frozenset(EQUIPMENT_NODE.panel_owners)

    def on_facility_stopped(self, w) -> None:
        from session.equipment_node import EQUIPMENT_NODE
        EQUIPMENT_NODE.on_exit(w)

    def __init__(self) -> None:
        super().__init__()
        self._none_shop_polls = 0
        self._last_img: str = ''

    @staticmethod
    def _is_equipment_context(ctx: SessionContext) -> bool:
        return (ctx.facility_kind or '').upper() == 'EQUIPMENT'

    @staticmethod
    def _known_non_equipment_context(ctx: SessionContext) -> bool:
        return (ctx.facility_kind or '').upper() != 'EQUIPMENT'

    def _shop_state_of(self, ctx: SessionContext) -> tuple[str, str]:
        extras_kind = ctx.extras.get('shop_kind') if ctx.extras else None
        extras_owner = ctx.extras.get('owner_kind') if ctx.extras else None
        if extras_kind is not None or extras_owner is not None:
            kind = extras_kind if extras_kind is not None else 'none'
            owner = extras_owner if extras_owner is not None else ''
            return (kind or 'none', owner or '')
        if ctx.top_level_state != 'normal-play':
            return ('none', '')
        if not ctx.in_interior:
            return ('none', '')
        from equipment_signals import own_menu_of
        if own_menu_of(ctx.shop_state)[0]:
            return ('shop_menu', 'equipment')
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
        return self._is_equipment_context(ctx)

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
        if self._known_non_equipment_context(ctx):
            return False
        if not self._is_confirmed_equipment_facility(ctx):
            return False
        if self._resolve_l4_state(ctx) is EquipmentL4State.NONE:
            return False
        self._none_shop_polls = 0
        self._last_img = ctx.img_name or ''
        self._set_active(True)
        return True

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
