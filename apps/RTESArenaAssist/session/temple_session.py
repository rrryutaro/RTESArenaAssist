from __future__ import annotations
from .session_base import SessionBase, SessionContext
_TEMPLE_OWNER_KINDS = frozenset({'shop_menu'})
_TEMPLE_PANEL_OWNERS = frozenset({'temple_menu', 'temple_priest_reply', 'temple_cost', 'temple_prompt'})
_TEMPLE_NONE_HYSTERESIS_POLLS = 3

class TempleSession(SessionBase):
    name = 'temple'

    def __init__(self) -> None:
        super().__init__()
        self._none_shop_polls = 0
        self._last_img: str = ''

    @staticmethod
    def _is_temple_context(ctx: SessionContext) -> bool:
        mif = (ctx.interior_mif_name or '').upper()
        if mif.startswith('TEMPLE'):
            return True
        if ctx.facility_kind == 'TEMPLE':
            return True
        return False

    @staticmethod
    def _facility_info_unknown(ctx: SessionContext) -> bool:
        return not ctx.interior_mif_name and (not ctx.facility_kind)

    @staticmethod
    def _known_non_temple_context(ctx: SessionContext) -> bool:
        mif = (ctx.interior_mif_name or '').upper()
        if mif and (not mif.startswith('TEMPLE')):
            return True
        if ctx.facility_kind and ctx.facility_kind != 'TEMPLE':
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
            state = detect_shop_popup_state(ctx.analyzer, ctx.anchor, top_level_state=ctx.top_level_state, img_name=ctx.img_name, in_interior=ctx.in_interior, screen_id=ctx.screen_id, interior_mif_name=ctx.interior_mif_name or '', active_facility_name='temple' if self._active or self._is_temple_context(ctx) else '')
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

    @staticmethod
    def _detect_temple_phase(ctx: SessionContext) -> str:
        extras_phase = ctx.extras.get('temple_phase') if ctx.extras else None
        if extras_phase is not None:
            return str(extras_phase or '')
        if ctx.analyzer is None:
            return ''
        try:
            from temple_dialog_reader import classify_temple_phase
        except ImportError:
            return ''
        try:
            phase, _values = classify_temple_phase(ctx.analyzer, ctx.anchor)
            return phase or ''
        except Exception:
            return ''

    @staticmethod
    def _is_temple_template_active(ctx: SessionContext) -> bool:
        extras_flag = ctx.extras.get('temple_template_active') if ctx.extras else None
        if extras_flag is not None:
            return bool(extras_flag)
        if ctx.analyzer is None:
            return False
        try:
            from active_template_reader import read_active_template_candidates, input_prompt_facility
            import npc_dialog_lookup as _ndl
        except ImportError:
            return False
        try:
            cands = read_active_template_candidates(ctx.analyzer, ctx.anchor)
        except Exception:
            return False
        for c in cands:
            if c.source == 'current_ptr':
                try:
                    if _ndl.lookup(c.text) is not None:
                        return True
                except Exception:
                    continue
            elif c.source == 'active_slot':
                if input_prompt_facility(c) != 'temple':
                    continue
                try:
                    if _ndl.lookup(c.text) is not None:
                        return True
                except Exception:
                    continue
        return False

    @staticmethod
    def _is_temple_response_active(ctx: SessionContext) -> bool:
        extras_flag = ctx.extras.get('temple_response_active') if ctx.extras else None
        if extras_flag is not None:
            return bool(extras_flag)
        w = ctx.extras.get('window') if ctx.extras else None
        if w is not None:
            try:
                if int(getattr(w, '_temple_dialog_hold_polls', 0) or 0) > 0:
                    return True
            except (TypeError, ValueError):
                pass
        if ctx.analyzer is None:
            return False
        try:
            from temple_dialog_reader import read_temple_response_candidates
        except ImportError:
            return False
        try:
            read = read_temple_response_candidates(ctx.analyzer, ctx.anchor)
        except Exception:
            return False
        if w is not None:
            prev_by_offset = dict(getattr(w, '_temple_dialog_text_by_offset', {}))
            baselined = bool(getattr(w, '_temple_dialog_baselined', False))
            if baselined:
                return any((prev_by_offset.get(c.source_offset) != c.text for c in read.candidates))
        return False

    def _is_temple_panel_owned(self, ctx: SessionContext) -> bool:
        extras_owner = ctx.extras.get('temple_panel_owner') if ctx.extras else None
        if extras_owner is not None:
            return extras_owner in _TEMPLE_PANEL_OWNERS
        w = ctx.extras.get('window') if ctx.extras else None
        if w is None:
            return False
        owner = getattr(w, '_panel_owner', '') or ''
        return owner in _TEMPLE_PANEL_OWNERS

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
        if not (self._is_temple_context(ctx) or self._facility_info_unknown(ctx)):
            return False
        kind, owner = self._detect_shop_state(ctx)
        if owner == 'temple' and kind in _TEMPLE_OWNER_KINDS:
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
        if self._known_non_temple_context(ctx):
            return self._stop()
        kind, owner = self._detect_shop_state(ctx)
        if owner == 'temple' and kind in _TEMPLE_OWNER_KINDS:
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ''
            return False
        if self._detect_temple_phase(ctx) == 'out':
            return self._stop()
        if self._is_yesno_active(ctx):
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ''
            return False
        if self._is_negotiation_active(ctx):
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ''
            return False
        if self._is_temple_template_active(ctx):
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ''
            return False
        if self._is_temple_response_active(ctx):
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ''
            return False
        if self._is_temple_panel_owned(ctx):
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ''
            return False
        self._none_shop_polls += 1
        if self._none_shop_polls >= _TEMPLE_NONE_HYSTERESIS_POLLS:
            return self._stop()
        self._last_img = ctx.img_name or ''
        return False

    def poll(self, ctx: SessionContext) -> None:
        return None
__all__ = ['TempleSession']
