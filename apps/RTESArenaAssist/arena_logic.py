import os
import sys
import struct
import ctypes
import zlib
_ROOT = os.path.dirname(os.path.abspath(__file__))
import i18n_helper as i18n
import location_lookup
from memory_core import ArenaMemoryAnalyzer, MEMORY_BASIC_INFORMATION, MEM_COMMIT, PAGE_NOACCESS, PAGE_GUARD
from viewer_constants import GAMESTATE_OFFSET, GS_DEFS, TRIGGER_BLOCK_OFFSET, TRIGGER_BLOCK_READ, TRIGGER_FLAG_OFFSET, TRIGGER_INDEX_OFFSET, FLAGS4_BITS, INF_PREFIXES, LIVE_MIF_OFFSET, LIVE_MIF_MAXLEN, MAP_NAME_OFFSET, MAP_NAME_MAXLEN, CHARGEN_STATE_OFFSET, RT_ANGLE_OFFSET, RT_ANGLE_BYTE_SIZE, RT_ANGLE_MASK, RT_ANGLE_RANGE, RT_ANGLE_NORTH_RAW
_LOG_BASE = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, 'frozen', False) else _ROOT
LOG_DIR = os.path.join(_LOG_BASE, 'output')
os.makedirs(LOG_DIR, exist_ok=True)
ANCHOR_PATTERN = b'BethesdaSoftworkRun-TimeLibrary'
STARTUP_TEXT_QUERIES = ['The Elder Scrolls', 'Chapter One', 'The Arena', 'The best techniques', 'Gaiden Shinji', 'For centuries', 'different factions', 'Start new game', 'Load game', 'Drop to Dos', 'Load Saved Game', 'Start New Game', 'Exit']

def find_anchor(analyzer: ArenaMemoryAnalyzer) -> int | None:
    k = analyzer._kernel32
    CHUNK = 4 * 1024 * 1024
    addr = 0
    mbi = MEMORY_BASIC_INFORMATION()
    candidates = []
    while addr < 2147483647:
        ret = k.VirtualQueryEx(analyzer.handle, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi))
        if not ret:
            break
        base = mbi.BaseAddress or 0
        sz = mbi.RegionSize
        prot = mbi.Protect
        if mbi.State == MEM_COMMIT and prot & PAGE_NOACCESS == 0 and (prot & PAGE_GUARD == 0):
            offset = 0
            while offset < sz:
                chunk = min(CHUNK, sz - offset)
                try:
                    data = analyzer.read_bytes(base + offset, chunk)
                except OSError:
                    offset += chunk
                    continue
                idx = data.find(ANCHOR_PATTERN)
                if idx != -1:
                    candidates.append(base + offset + idx)
                offset += chunk
        addr = base + sz
    return max(candidates) if candidates else None

def _read_gs_val(analyzer, gs_base: int, off: int, typ: str):
    addr = gs_base + off
    try:
        if typ == 'u8':
            return analyzer.read_bytes(addr, 1)[0]
        elif typ == 'u16':
            return struct.unpack_from('<H', analyzer.read_bytes(addr, 2))[0]
        elif typ.startswith('str'):
            n = int(typ[3:])
            raw = analyzer.read_bytes(addr, n)
            end = raw.find(b'\x00')
            return (raw[:end] if end >= 0 else raw).decode('ascii', errors='replace').strip()
    except OSError:
        return None

def read_game_state(analyzer, anchor: int) -> dict:
    gs_base = anchor + GAMESTATE_OFFSET
    result = {'_gs_base': gs_base}
    for name, off, typ, _ in GS_DEFS:
        result[name] = _read_gs_val(analyzer, gs_base, off, typ)
    live_raw = read_live_buffer(analyzer, anchor + LIVE_MIF_OFFSET, LIVE_MIF_MAXLEN)
    result['LiveMifName'] = normalize_mif_name(live_raw)
    result['MapName'] = read_live_buffer(analyzer, anchor + MAP_NAME_OFFSET, MAP_NAME_MAXLEN)
    try:
        result['ChargenState'] = analyzer.read_bytes(anchor + CHARGEN_STATE_OFFSET, 1)[0]
    except OSError:
        result['ChargenState'] = None
    try:
        angle_bytes = analyzer.read_bytes(anchor + RT_ANGLE_OFFSET, RT_ANGLE_BYTE_SIZE)
        angle_u16 = int.from_bytes(angle_bytes, 'little')
        result['PlayerAngle'] = ((angle_u16 & RT_ANGLE_MASK) - RT_ANGLE_NORTH_RAW) % RT_ANGLE_RANGE
    except OSError:
        result['PlayerAngle'] = None
    return result

def read_live_buffer(analyzer, addr: int, maxlen: int) -> str:
    try:
        raw = analyzer.read_bytes(addr, maxlen)
        end = raw.find(b'\x00')
        if end >= 0:
            raw = raw[:end]
        start = 0
        while start < len(raw) and (not 32 <= raw[start] <= 126):
            start += 1
        text = raw[start:].decode('ascii', errors='replace').strip()
        if not text:
            return ''
        ratio = sum((32 <= ord(c) <= 126 for c in text)) / len(text)
        return text if ratio >= 0.7 else ''
    except OSError:
        return ''

def normalize_mif_name(value: str | None) -> str:
    if not value:
        return ''
    name = value.strip()
    if not name:
        return ''
    if '.' not in name:
        name = f'{name}.MIF'
    name = name.upper()
    if not name.endswith('.MIF'):
        return ''
    if len(name) > 13:
        return ''
    allowed = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.')
    if any((ch not in allowed for ch in name)):
        return ''
    return name

def collect_startup_memory_diagnostics(analyzer: ArenaMemoryAnalyzer, anchor: int | None=None, start: int=0, end: int=2147483647, max_hits_per_query: int=8) -> dict:
    queries = [(q, q.encode('ascii', errors='ignore')) for q in STARTUP_TEXT_QUERIES]
    hits: dict[str, list[dict]] = {q: [] for q, _ in queries}
    regions = []
    total_size = 0
    combined_crc = 0
    for base, size in analyzer._enum_readable_regions(start, end):
        try:
            data = analyzer.read_bytes(base, size)
        except OSError:
            continue
        region_crc = zlib.crc32(data) & 4294967295
        total_size += len(data)
        combined_crc = zlib.crc32(region_crc.to_bytes(4, 'little'), combined_crc)
        combined_crc = zlib.crc32(len(data).to_bytes(8, 'little'), combined_crc)
        regions.append({'base': f'0x{base:08X}', 'size': len(data), 'crc32': f'{region_crc:08X}', **({'offset_from_anchor': base - anchor, 'offset_from_anchor_hex': f'0x{base - anchor:X}'} if anchor is not None else {})})
        for query, needle in queries:
            if not needle or len(hits[query]) >= max_hits_per_query:
                continue
            offset = 0
            while len(hits[query]) < max_hits_per_query:
                idx = data.find(needle, offset)
                if idx < 0:
                    break
                ctx_start = max(0, idx - 24)
                ctx_end = min(len(data), idx + len(needle) + 56)
                ctx = data[ctx_start:ctx_end]
                item = {'address': f'0x{base + idx:08X}', 'offset_from_region': idx, 'context_ascii': ''.join((chr(b) if 32 <= b <= 126 else '.' for b in ctx))}
                if anchor is not None:
                    item['offset_from_anchor'] = base + idx - anchor
                    item['offset_from_anchor_hex'] = f'0x{base + idx - anchor:X}'
                hits[query].append(item)
                offset = idx + 1
    return {'scan_range': {'start': f'0x{start:08X}', 'end': f'0x{end:08X}'}, 'region_count': len(regions), 'total_readable_bytes': total_size, 'combined_crc32': f'{combined_crc & 4294967295:08X}', 'regions': regions, 'startup_text_hits': {query: {'hit_count_limited': len(items), 'hits': items} for query, items in hits.items()}}

def check_trigger_flag(analyzer, anchor: int, prev_flag: int, trigger_indices: list, cached_trig_idx: int=0) -> tuple:
    try:
        curr_flag = analyzer.read_bytes(anchor + TRIGGER_FLAG_OFFSET, 1)[0]
    except OSError:
        return ('', prev_flag, 0, 0, 0)
    if curr_flag == 0:
        return ('', curr_flag, 0, 0, 0)
    trig_idx = cached_trig_idx
    try:
        raw = analyzer.read_bytes(anchor + TRIGGER_BLOCK_OFFSET, TRIGGER_BLOCK_READ)
    except OSError:
        raw = b''
    texts = []
    for chunk in raw.split(b'\x00'):
        text = chunk.decode('ascii', errors='replace').strip().lstrip('~')
        ratio = sum((32 <= ord(c) <= 126 for c in text)) / max(len(text), 1)
        if text and ratio >= 0.7:
            texts.append(text.replace('\r', ' ').replace('\n', ' '))
    if not texts:
        return (f'[0x{curr_flag:02X}]', curr_flag, trig_idx, 0, 0)
    if trig_idx and trig_idx not in trigger_indices:
        trigger_indices.append(trig_idx)
    n = len(texts)
    if not trig_idx:
        slot = 0
        body = texts[0]
    else:
        slot = trig_idx // 32 - 1
        if 0 <= slot < n:
            body = texts[slot]
        else:
            slot = 0
            body = texts[0]
    return (body, curr_flag, trig_idx, n, slot)
_LOC_DISPLAY_MEMO: dict[tuple[str, str, str], str] = {}

def _location_display_name(name_key: str) -> str:
    lang = i18n.current_lang()
    if lang == 'en':
        return name_key
    memo_key = (getattr(i18n, '_I18N_DIR', ''), lang, name_key)
    cached = _LOC_DISPLAY_MEMO.get(memo_key)
    if cached is None:
        cached = location_lookup.lookup(name_key) or name_key
        _LOC_DISPLAY_MEMO[memo_key] = cached
    return cached

def interpret_location(gs: dict) -> dict:
    mif = gs.get('LiveMifName') or gs.get('MifName') or ''
    inf = gs.get('InfName') or ''
    f4 = gs.get('Flags4') or 0
    level_name = (gs.get('LevelName') or '').strip()
    map_name = (gs.get('MapName') or '').strip()
    name_key = level_name or map_name
    if name_key:
        loc = _location_display_name(name_key)
    else:
        mu = mif.upper()
        if mu == 'IMPERIAL.MIF':
            loc = i18n.text('place.kind.imperial_city').replace('{mif}', mif)
        elif mu.startswith('CITY') or mu.startswith('TOWN'):
            type_en, type_id = ('City', 'settlement_types.2.0') if mu.startswith('CITY') else ('Town', 'settlement_types.1.0')
            type_tr = i18n.value('settlement_types', type_en) or i18n.lang_value_in(type_id, i18n.current_lang()) or type_en
            loc = i18n.text('place.kind.settlement_format').replace('{type}', type_tr).replace('{mif}', mif)
        elif 'WILD' in mu:
            loc = i18n.text('place.kind.field_format').replace('{mif}', mif)
        elif mif:
            loc = i18n.text('place.kind.dungeon_format').replace('{mif}', mif)
        else:
            loc = i18n.text('place.kind.unknown')
    interior = INF_PREFIXES.get(inf[:2].upper(), '')
    if not interior:
        if 'palace' in inf.lower() or 'imppal' in inf.lower():
            interior = '宮殿'
    angle = gs.get('PlayerAngle')
    dirs = ['北', '北東', '東', '南東', '南', '南西', '西', '北西']
    direction = dirs[round(angle / 64) % 8] if angle is not None else '不明'
    wf = gs.get('WeatherFlags') or 0
    if wf & 128:
        weather_key = 'weather.rain' if wf & 1 else 'weather.snow' if wf & 2 else 'weather.precipitation'
    else:
        weather_key = 'weather.clear'
    weather = i18n.text(weather_key)
    flags = [desc for bit, desc in FLAGS4_BITS.items() if f4 & bit]
    return {'location': loc, 'interior': interior, 'mif_name': mif, 'inf_name': inf, 'level': gs.get('LevelName') or '', 'floor': gs.get('PlayerFloor') or 0, 'x': gs.get('PlayerX'), 'z': gs.get('PlayerZ'), 'y': gs.get('PlayerY'), 'angle': angle, 'direction': direction, 'weather': weather, 'flags': flags}

def next_log_no() -> int:
    files = [f for f in os.listdir(LOG_DIR) if f.startswith('gs_log_') and f.endswith('.json')]
    nums = []
    for f in files:
        try:
            nums.append(int(f.replace('gs_log_', '').replace('.json', '')))
        except ValueError:
            pass
    return max(nums) + 1 if nums else 1

def next_bin_no() -> int:
    files = [f for f in os.listdir(LOG_DIR) if f.startswith('mem_dump_') and f.endswith('.bin')]
    nums = []
    for f in files:
        try:
            nums.append(int(f.replace('mem_dump_', '').replace('.bin', '')))
        except ValueError:
            pass
    return max(nums) + 1 if nums else 1
