from __future__ import annotations
from typing import Callable
_FACILITY_KEYS: dict[str, str] = {'tavern': 'recognition.facility_tavern', 'temple': 'recognition.facility_temple', 'equipment': 'recognition.facility_equipment', 'mages_guild': 'recognition.facility_mages', 'crypt': 'recognition.facility_crypt', 'tower': 'recognition.facility_tower', 'house': 'recognition.facility_house', 'palace': 'recognition.facility_palace'}

def resolve_stable_screen_name(stable_id: str, raw_id: str, raw_name: str, tr: Callable[[str], str]) -> str:
    if stable_id == 'npc_dialog':
        return tr('screen.game_screen')
    if stable_id == raw_id:
        return raw_name
    return tr(f'screen.{stable_id}')
OVERLAY_SCREEN_IDS: frozenset[str] = frozenset({'status_page', 'bonus_screen', 'equipment', 'spellbook', 'spell_detail', 'automap', 'logbook', 'system_menu', 'loadsave_in_play'})

def format_recognition_label(screen_name: str, indicator: str, facility_label: str, conv_label: str, screen_id_stable: str='') -> str:
    if facility_label:
        base = f'{indicator}{facility_label}{conv_label}' if indicator else f'{facility_label}{conv_label}'
        if (screen_id_stable or '') in OVERLAY_SCREEN_IDS and screen_name:
            return f'{base} {screen_name}'
        return base
    return f'{indicator} {screen_name}{conv_label}' if indicator else f'{screen_name}{conv_label}'

def facility_key_of(facility: str, in_interior: bool, *, area: str='') -> str:
    if not in_interior:
        return ''
    key = _FACILITY_KEYS.get(facility or '')
    if key:
        return key
    if area == 'dungeon':
        return ''
    return 'recognition.facility_other'
__all__ = ['OVERLAY_SCREEN_IDS', 'resolve_stable_screen_name', 'format_recognition_label', 'facility_key_of']
