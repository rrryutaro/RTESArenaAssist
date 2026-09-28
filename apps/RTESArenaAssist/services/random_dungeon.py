from __future__ import annotations
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from services.arena_random import ArenaRandom
_log = logging.getLogger('RTESArenaAssist')
DUNGEON_CHUNK_DIM = 32
RANDOM_DUNGEON_MIF_NAME = 'RANDOM1.MIF'
WIDTH_CHUNKS = 2
DEPTH_CHUNKS = 1
PERIMETER_VOXEL = 30720
GENERATED_LEVELS = 8
_RANDOM_DUNGEON_IDS = range(34, 48)
_SEED_MIF_RE = re.compile('^(\\d{8})\\.MIF$', re.IGNORECASE)

def _rol32(value: int, bits: int) -> int:
    value &= 4294967295
    return (value << bits | value >> 32 - bits) & 4294967295

def dungeon_seed(x: int, y: int, province_id: int) -> int:
    seed = (y << 16) + x + province_id & 4294967295
    return ~_rol32(seed, 5) & 4294967295

def mif_name_of_seed(seed: int) -> str:
    return f'{str(int(seed))[:8]}.MIF'

def _find_random_dungeon(mif_name: str, world=None) -> Optional[tuple[int, int, int]]:
    if not _SEED_MIF_RE.match((mif_name or '').strip()):
        return None
    if world is None:
        try:
            from services.city_data import load_world_map_data
            world = load_world_map_data()
        except (FileNotFoundError, OSError, ValueError, KeyError):
            return None
    want = mif_name.strip().upper()
    for province_id, province in enumerate(world.provinces):
        for location_id in _RANDOM_DUNGEON_IDS:
            loc = province.get_location(location_id)
            if loc is None:
                continue
            seed = dungeon_seed(loc.x, loc.y, province_id)
            if mif_name_of_seed(seed) == want:
                return (province_id, location_id, seed)
    return None

def find_random_dungeon_seed(mif_name: str, world=None) -> Optional[int]:
    found = _find_random_dungeon(mif_name, world)
    return found[2] if found else None

def find_random_dungeon_location(mif_name: str, world=None) -> Optional[tuple[int, int]]:
    found = _find_random_dungeon(mif_name, world)
    return (found[0], found[1]) if found else None

def _pack_level_change(x: int, y: int) -> int:
    return 10 * y + x

def _unpack_level_change(value: int) -> tuple[int, int]:
    return (value % 10, value // 10)

def _offset_level_change(coord: int) -> int:
    return 10 + coord * DUNGEON_CHUNK_DIM

def _level_change_voxel(texture_index: int) -> int:
    byte = texture_index + 1 & 255
    return byte << 8 | byte
_BLOCK_CELLS = DUNGEON_CHUNK_DIM * DUNGEON_CHUNK_DIM

def _is_block(block) -> bool:
    return getattr(block, 'width', 0) == DUNGEON_CHUNK_DIM and getattr(block, 'height', 0) == DUNGEON_CHUNK_DIM and (len(getattr(block, 'flor', None) or ()) == _BLOCK_CELLS) and (len(getattr(block, 'map1', None) or ()) == _BLOCK_CELLS)

@dataclass(frozen=True)
class GeneratedDungeon:
    seed: int
    width: int
    height: int
    levels: tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]
    start: tuple[int, int]
    info_name: str
    triggers: tuple[tuple, ...] = ()
    locks: tuple[tuple, ...] = ()
    drawn_level_count: int = 0

    @property
    def level_count(self) -> int:
        return len(self.levels)

def generate(seed: int, blocks: list, level_up_index: int, level_down_index: int, *, width_chunks: int=WIDTH_CHUNKS, depth_chunks: int=DEPTH_CHUNKS) -> GeneratedDungeon:
    random = ArenaRandom(seed)
    drawn_level_count = 1 + random.next() % 2
    seed2 = random.get_seed()

    def next_transition() -> int:
        ty = random.next() % depth_chunks
        tx = random.next() % width_chunks
        return _pack_level_change(tx, ty)
    transitions = [next_transition()]
    for _ in range(1, GENERATED_LEVELS):
        value = next_transition()
        while value == transitions[-1]:
            value = next_transition()
        transitions.append(value)
    from services.mif_loader import LockRecord, TriggerRecord
    width = DUNGEON_CHUNK_DIM * width_chunks
    height = DUNGEON_CHUNK_DIM * depth_chunks
    levels = []
    level_triggers = []
    level_locks = []
    for i in range(GENERATED_LEVELS):
        random.srand(seed2 + i)
        flor = [0] * (width * height)
        map1 = [0] * (width * height)
        triggers: list = []
        locks: list = []
        tile_set = random.next() % 4
        for row in range(depth_chunks):
            for column in range(width_chunks):
                block_index = tile_set * 8 + random.next() % 8
                block = blocks[block_index]
                if not _is_block(block):
                    raise ValueError(f'random dungeon block {block_index} is not a {DUNGEON_CHUNK_DIM}x{DUNGEON_CHUNK_DIM} level')
                for z in range(DUNGEON_CHUNK_DIM):
                    src = z * block.width
                    dst = (row * DUNGEON_CHUNK_DIM + z) * width + column * DUNGEON_CHUNK_DIM
                    flor[dst:dst + DUNGEON_CHUNK_DIM] = block.flor[src:src + DUNGEON_CHUNK_DIM]
                    map1[dst:dst + DUNGEON_CHUNK_DIM] = block.map1[src:src + DUNGEON_CHUNK_DIM]
                x_offset = column * DUNGEON_CHUNK_DIM
                z_offset = row * DUNGEON_CHUNK_DIM
                for lock in getattr(block, 'locks', None) or ():
                    locks.append(LockRecord(x_offset + lock.x, z_offset + lock.y, lock.level, len(locks)))
                for trig in getattr(block, 'trigs', None) or ():
                    triggers.append(TriggerRecord(x_offset + trig.x, z_offset + trig.y, trig.text_index, trig.sound_index, len(triggers)))
        for x in range(width):
            map1[x] = PERIMETER_VOXEL
            map1[(height - 1) * width + x] = PERIMETER_VOXEL
        for z in range(1, height - 1):
            map1[z * width] = PERIMETER_VOXEL
            map1[z * width + width - 1] = PERIMETER_VOXEL
        ux, uy = _unpack_level_change(transitions[i])
        map1[_offset_level_change(uy) * width + _offset_level_change(ux)] = _level_change_voxel(level_up_index)
        if i < drawn_level_count - 1:
            dx, dy = _unpack_level_change(transitions[i + 1])
            map1[_offset_level_change(dy) * width + _offset_level_change(dx)] = _level_change_voxel(level_down_index)
        levels.append((tuple(flor), tuple(map1)))
        level_triggers.append(tuple(triggers))
        level_locks.append(tuple(locks))
    sx, sy = _unpack_level_change(transitions[0])
    info_name = str(getattr(blocks[0], 'info_name', '') or '')
    return GeneratedDungeon(seed=seed, width=width, height=height, levels=tuple(levels), start=(_offset_level_change(sx), _offset_level_change(sy)), info_name=info_name, triggers=tuple(level_triggers), locks=tuple(level_locks), drawn_level_count=drawn_level_count)
_BLOCKS_CACHE: dict[tuple, list] = {}
_GENERATED_CACHE: dict[tuple, GeneratedDungeon] = {}
_BEYOND_LOGGED: set[tuple[int, int]] = set()
_NOT_BUILT_LOGGED: set[tuple] = set()

def reset_caches() -> None:
    _BLOCKS_CACHE.clear()
    _GENERATED_CACHE.clear()
    _BEYOND_LOGGED.clear()
    _NOT_BUILT_LOGGED.clear()

def _note_not_built(reason: str, mif_name: str, mif_dirs, detail: str='') -> None:
    key = (reason, tuple((str(d) for d in mif_dirs)))
    if key in _NOT_BUILT_LOGGED:
        return
    _NOT_BUILT_LOGGED.add(key)
    from assist_log import recog
    recog(_log, 'random dungeon not built: reason=%s mif=%s dirs=%s%s', reason, mif_name, list(key[1]), detail)

def _blocks(mif_dirs) -> list:
    key = tuple((str(d) for d in mif_dirs))
    cached = _BLOCKS_CACHE.get(key)
    if cached is None:
        from services.mif_loader import load_mif_levels
        cached = load_mif_levels(RANDOM_DUNGEON_MIF_NAME, mif_dirs)
        if len(cached) < 32 or not all((_is_block(b) for b in cached[:32])):
            return []
        _BLOCKS_CACHE[key] = cached
    return cached

def _level_change_indices(info_name: str) -> tuple[Optional[int], Optional[int]]:
    from services.mif_loader import DEFAULT_INF_DIR, parse_inf_level_transitions, resolve_inf_for_mif
    inf_path = resolve_inf_for_mif(RANDOM_DUNGEON_MIF_NAME, info_name, DEFAULT_INF_DIR)
    if inf_path is None:
        return (None, None)
    try:
        return parse_inf_level_transitions(inf_path)
    except Exception:
        return (None, None)

def generated_dungeon(mif_name: str, mif_dirs) -> Optional[GeneratedDungeon]:
    seed = find_random_dungeon_seed(mif_name)
    if seed is None:
        return None
    blocks = _blocks(mif_dirs)
    if not blocks:
        _note_not_built('blocks', mif_name, mif_dirs)
        return None
    level_up, level_down = _level_change_indices(blocks[0].info_name)
    if level_up is None or level_down is None:
        _note_not_built('inf', mif_name, mif_dirs, f' inf={blocks[0].info_name}')
        return None
    key = (seed, level_up, level_down, tuple((str(d) for d in mif_dirs)))
    dungeon = _GENERATED_CACHE.get(key)
    if dungeon is None:
        dungeon = generate(seed, blocks, level_up, level_down)
        _GENERATED_CACHE[key] = dungeon
        from assist_log import recog
        recog(_log, 'random dungeon generated: mif=%s seed=%d drawn_levels=%d start=%s', mif_name, seed, dungeon.drawn_level_count, dungeon.start)
    return dungeon

def load_generated_level(mif_name: str, mif_dirs, *, level_index_override: Optional[int]=None):
    dungeon = generated_dungeon(mif_name, mif_dirs)
    if dungeon is None:
        return None
    index = 0 if level_index_override is None else int(level_index_override)
    if not 0 <= index < dungeon.level_count:
        mark = (dungeon.seed, index)
        if mark not in _BEYOND_LOGGED:
            _BEYOND_LOGGED.add(mark)
            from assist_log import recog
            recog(_log, 'random dungeon level beyond the generated levels: mif=%s level=%d levels=%d', mif_name, index, dungeon.level_count)
        return None
    from services.mif_loader import MifMap, _extract_entities
    flor, map1 = dungeon.levels[index]
    return MifMap(path=Path(mif_name), flor=list(flor), map1=list(map1), trigs=list(dungeon.triggers[index]) if dungeon.triggers else [], locks=list(dungeon.locks[index]) if dungeon.locks else [], entities=_extract_entities(list(map1), list(flor), dungeon.width, dungeon.height), width=dungeon.width, height=dungeon.height, level_index=index, level_count=dungeon.level_count, starting_level_index=0, info_name=dungeon.info_name, generated=True)
__all__ = ['DUNGEON_CHUNK_DIM', 'RANDOM_DUNGEON_MIF_NAME', 'WIDTH_CHUNKS', 'DEPTH_CHUNKS', 'GENERATED_LEVELS', 'GeneratedDungeon', 'dungeon_seed', 'mif_name_of_seed', 'find_random_dungeon_seed', 'find_random_dungeon_location', 'generate', 'generated_dungeon', 'load_generated_level', 'reset_caches']
