from __future__ import annotations
from dataclasses import dataclass
_HOLD_OVERRIDE_PAGES = ('equipment', 'spellbook', 'spell_detail', 'status_page')

@dataclass
class BonusScreenResolve:
    screen_id_stable: str
    hold_active: bool
    log_start: bool
    log_end: bool
    log_override: bool
    clear_spell_markers: bool

def resolve_bonus_screen(screen_id_stable: str, in_levelup: bool, flag_status: int, hold_active: bool) -> BonusScreenResolve:
    log_start = False
    log_end = False
    log_override = False
    clear_spell_markers = False
    if in_levelup and flag_status == 1:
        if not hold_active:
            log_start = True
        hold_active = True
        clear_spell_markers = True
    elif screen_id_stable == 'bonus_screen' and (not in_levelup):
        screen_id_stable = 'status_page'
    if hold_active and (flag_status == 0 or not in_levelup):
        log_end = True
        hold_active = False
    if hold_active and screen_id_stable in _HOLD_OVERRIDE_PAGES:
        log_override = True
        screen_id_stable = 'bonus_screen'
    return BonusScreenResolve(screen_id_stable=screen_id_stable, hold_active=hold_active, log_start=log_start, log_end=log_end, log_override=log_override, clear_spell_markers=clear_spell_markers)
__all__ = ['resolve_bonus_screen', 'BonusScreenResolve', '_HOLD_OVERRIDE_PAGES']
