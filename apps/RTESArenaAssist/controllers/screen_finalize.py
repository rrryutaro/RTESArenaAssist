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
BONUS_PTS_MIN = 0
BONUS_PTS_MAX = 30
ARTIFACT_BONUS_PTS_MAX = 50

def bonus_pts_is_plausible(bonus_pts: int | None, maximum: int=BONUS_PTS_MAX) -> bool:
    if bonus_pts is None:
        return False
    return BONUS_PTS_MIN <= int(bonus_pts) <= int(maximum)

@dataclass(frozen=True)
class BonusScreenSignals:
    flag_status: int
    bonus_pts: int | None
BONUS_SCREEN_FLAG_OFFSET = 4794
BONUS_PTS_OFFSET = 4764
PRIMARY_ATTRS_OFFSET = 461

def read_bonus_screen_signals(analyzer, anchor: int) -> BonusScreenSignals:

    def _read(offset: int) -> int | None:
        try:
            return analyzer.read_bytes(anchor + offset, 1)[0]
        except (OSError, AttributeError, IndexError, TypeError):
            return None
    flag = _read(BONUS_SCREEN_FLAG_OFFSET)
    return BonusScreenSignals(flag_status=0 if flag is None else int(flag), bonus_pts=_read(BONUS_PTS_OFFSET))

def infer_bonus_window_from_memory(*, flag_status: int, bonus_pts: int | None, primary_raw: bytes | None, hold_active: bool) -> bool:
    if int(flag_status) != 1:
        return False
    if hold_active:
        return True
    if not bonus_pts_is_plausible(bonus_pts) or int(bonus_pts) < 1:
        return False
    if primary_raw is None or len(primary_raw) != 8:
        return False
    return all((1 <= int(b) <= 100 for b in primary_raw))

def resolve_bonus_screen(screen_id_stable: str, in_levelup: bool, flag_status: int, hold_active: bool, bonus_pts: int | None=None, bonus_max: int=BONUS_PTS_MAX) -> BonusScreenResolve:
    log_start = False
    log_end = False
    log_override = False
    clear_spell_markers = False
    if in_levelup and flag_status == 1 and (hold_active or bonus_pts_is_plausible(bonus_pts, bonus_max)):
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
