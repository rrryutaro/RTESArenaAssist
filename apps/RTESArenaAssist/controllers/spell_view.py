from __future__ import annotations
from typing import Optional
SPELL_VIEW_DELTA_DETAIL = 84
SPELL_VIEW_DELTA_RENAME = 159

def classify_spell_view(spell_view: int, base: Optional[int]) -> str:
    if base is None:
        return 'spellbook'
    delta = base - spell_view & 255
    if delta in (SPELL_VIEW_DELTA_DETAIL, SPELL_VIEW_DELTA_RENAME):
        return 'spell_detail'
    return 'spellbook'

def classify_spell_screen(screen_id: str, img_name: str, spell_view: int, base: Optional[int], *, previous_screen_id: str | None=None, flag_spell_detail: int | None=None, spell_name: str='') -> str:
    _ = (img_name, previous_screen_id, spell_name)
    if screen_id != 'spellbook':
        return screen_id
    if base is None:
        if flag_spell_detail == 0:
            return 'spell_detail'
        return 'spellbook'
    delta = base - spell_view & 255
    if delta == 0:
        return 'spellbook'
    if delta in (SPELL_VIEW_DELTA_DETAIL, SPELL_VIEW_DELTA_RENAME):
        return 'spell_detail'
    if flag_spell_detail == 255:
        return 'spellbook'
    if flag_spell_detail == 0:
        return 'spell_detail'
    return 'spellbook'
__all__ = ['classify_spell_view', 'classify_spell_screen', 'SPELL_VIEW_DELTA_DETAIL', 'SPELL_VIEW_DELTA_RENAME']
