from __future__ import annotations
from services.arena_level_utils import MENU_MIF_PREFIXES
_FACILITY_OF_PREFIX = {'PALACE': 'palace', 'BS': 'house', 'NOBLE': 'noble', 'TAVERN': 'tavern', 'TEMPLE': 'temple', 'EQUIP': 'equipment', 'MAGE': 'mages_guild', 'WCRYPT': 'crypt', 'TOWNPAL': 'palace', 'VILPAL': 'palace', 'TOWER': 'tower'}
assert set(_FACILITY_OF_PREFIX) == set(MENU_MIF_PREFIXES), '生成規則の接頭辞と表がずれている'
_FACILITY_OF_PREFIX['IMPPAL'] = 'palace'
_PREFIXES_LONGEST_FIRST = tuple(sorted(_FACILITY_OF_PREFIX, key=len, reverse=True))

def mif_prefix_of(interior_mif_name) -> str:
    u = (interior_mif_name or '').strip().upper()
    if not u:
        return ''
    for p in _PREFIXES_LONGEST_FIRST:
        if u.startswith(p):
            return p
    return ''

def facility_of_mif(interior_mif_name) -> str:
    return _FACILITY_OF_PREFIX.get(mif_prefix_of(interior_mif_name), '')
