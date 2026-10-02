from __future__ import annotations
import logging
import assist_log
import assist_settings as settings
from spell_effect_overlay import SpellEffectOverlay, STYLES
from spell_effects import SpellEffectTracker, read_sample
_log = logging.getLogger('RTESArenaAssist')

class SpellEffectController:

    def __init__(self, window) -> None:
        self._window = window
        self._tracker = SpellEffectTracker()
        self._overlay = SpellEffectOverlay(window)
        self._last_key = None

    def reset(self) -> None:
        self._tracker.reset()
        self._overlay.clear()
        self._last_key = None

    def poll(self, *, gameplay: bool) -> None:
        window = self._window
        if not gameplay or getattr(window, '_loading_state_active', False) or (not settings.get('spell_effect_arena_enabled', False)):
            self._tracker.pause()
            self._overlay.clear()
            return
        sample = read_sample(window._analyzer, window._anchor)
        if sample is None:
            self._tracker.pause()
            self._overlay.clear()
            return
        unit = settings.get('spell_effect_time_unit', 'rounds')
        rows = self._tracker.update(sample, time_unit=unit if unit in ('rounds', 'seconds') else 'rounds')
        key = tuple(((row.key, row.value, row.ratio) for row in rows))
        if key != self._last_key:
            self._last_key = key
            assist_log.recog(_log, 'spell_effect display: %s', key)
        if not rows:
            self._overlay.clear()
            return
        layout = getattr(window, '_layout_mgr', None)
        if layout is None or not layout.is_dosbox_foreground():
            self._tracker.pause()
            self._overlay.clear()
            return
        rect = layout.get_visible_dosbox_client_qt_rect()
        if not isinstance(rect, (tuple, list)) or len(rect) != 4:
            self._tracker.pause()
            self._overlay.clear()
            return
        style = str(settings.get('spell_effect_arena_style', 'E')).upper()
        combat = getattr(window, '_combat_info_controller', None)
        combat_top = bool(combat is not None and combat.arena_header_visible())
        self._overlay.render(rows, style=style if style in STYLES else 'E', rect=rect, top_offset=70 if combat_top else 10)

def poll_spell_effects(window, *, gameplay: bool) -> None:
    controller = getattr(window, '_spell_effect_controller', None)
    if controller is None:
        controller = SpellEffectController(window)
        window._spell_effect_controller = controller
    try:
        controller.poll(gameplay=gameplay)
    except Exception:
        _log.exception('spell effect poll failed')
        controller._overlay.clear()

def reset_spell_effects(window) -> None:
    controller = getattr(window, '_spell_effect_controller', None)
    if controller is not None:
        controller.reset()
__all__ = ['SpellEffectController', 'poll_spell_effects', 'reset_spell_effects']
