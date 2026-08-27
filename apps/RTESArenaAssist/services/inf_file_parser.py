from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional
try:
    from .mif_loader import DEFAULT_INF_DIR
except ImportError:
    from runtime_paths import resolve_arena_data_dir
    DEFAULT_INF_DIR = resolve_arena_data_dir() / 'INF'

@dataclass
class INFData:
    menus: Dict[int, int] = field(default_factory=dict)
    menu_ranges: Dict[int, tuple] = field(default_factory=dict)
    flat_items: Dict[int, int] = field(default_factory=dict)
_ITEM_TREASURE_PILE_MIN = 2
_ITEM_TREASURE_PILE_MAX = 6

def is_treasure_pile_item(item_index: int) -> bool:
    return _ITEM_TREASURE_PILE_MIN <= int(item_index) <= _ITEM_TREASURE_PILE_MAX

def treasure_pile_flat_indices(inf: INFData) -> frozenset:
    return frozenset((fi for fi, item in inf.flat_items.items() if is_treasure_pile_item(item)))
_ITEM_LOCKED_CHEST = 7

def is_locked_chest_item(item_index: int) -> bool:
    return int(item_index) == _ITEM_LOCKED_CHEST
_DIRECTIVES_NO_TEXTURE = {'*BOXCAP', '*BOXSIDE', '*DOOR', '*TRANS', '*TRANSWALKTHRU', '*WALKTHRU', '*DRYCHASM', '*LAVACHASM', '*WETCHASM', '*LEVELDOWN', '*LEVELUP'}

def parse_inf(path: str) -> INFData:
    try:
        from .mif_loader import read_inf_bytes
        raw = read_inf_bytes(path)
    except ImportError:
        try:
            with open(path, 'rb') as f:
                raw = f.read()
        except OSError:
            raw = None
    if raw is None:
        return INFData()
    text = raw.decode('ascii', errors='replace')
    result = INFData()
    in_walls = False
    in_flats = False
    texture_id = 0
    pending_menu_id: Optional[int] = None
    flat_id = 0
    current_item_id: Optional[int] = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        upper = line.upper()
        if upper.startswith('@'):
            in_walls = upper == '@WALLS'
            in_flats = upper.startswith('@FLATS')
            continue
        if in_flats:
            if line.startswith('*'):
                tokens = line.split()
                if tokens[0].upper() == '*ITEM' and len(tokens) >= 2:
                    try:
                        current_item_id = int(tokens[1])
                    except ValueError:
                        current_item_id = None
                continue
            if current_item_id is not None:
                result.flat_items[flat_id] = current_item_id
            flat_id += 1
            current_item_id = None
            continue
        if not in_walls:
            continue
        if line.startswith('*'):
            tokens = line.split()
            directive = tokens[0].upper()
            if directive == '*MENU':
                if len(tokens) >= 2:
                    try:
                        pending_menu_id = int(tokens[1])
                    except ValueError:
                        pending_menu_id = None
            elif directive in _DIRECTIVES_NO_TEXTURE:
                pass
            else:
                pass
            continue
        hash_split = [s.strip() for s in line.split('#')]
        first = hash_split[0]
        if not first:
            continue
        set_size = 1
        if len(hash_split) >= 2 and first.lower().endswith('.set'):
            try:
                set_size = int(hash_split[1].split()[0])
            except (ValueError, IndexError):
                set_size = 1
        current_index = texture_id
        texture_id += set_size
        if pending_menu_id is not None:
            result.menus[pending_menu_id] = current_index
            result.menu_ranges[pending_menu_id] = (current_index, current_index + set_size)
            pending_menu_id = None
    return result
_ARENA_INF_DIR = os.fspath(DEFAULT_INF_DIR)

def get_city_inf_path(climate_letter: str='T', weather_letter: str='N') -> str:
    filename = f'{climate_letter}C{weather_letter}.INF'
    return os.path.normpath(os.path.join(_ARENA_INF_DIR, filename))
