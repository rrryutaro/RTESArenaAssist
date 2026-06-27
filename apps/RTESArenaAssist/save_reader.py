import os
import re
from datetime import datetime
_NAMES_SLOT_SIZE = 48

def read_slot_info(game_dir: str, slot: int) -> dict:
    result: dict = {'slot': slot, 'save_name': None, 'modified': None, 'file_count': 0}
    if not os.path.isdir(game_dir):
        return result
    ext_re = re.compile(f'\\.0{slot}$', re.IGNORECASE)
    try:
        slot_files = [f for f in os.listdir(game_dir) if ext_re.search(f)]
    except OSError:
        return result
    result['file_count'] = len(slot_files)
    mtime_path = _find_file(game_dir, 'SAVEENGN', slot) or _find_file(game_dir, 'SAVEGAME', slot) or (os.path.join(game_dir, slot_files[0]) if slot_files else None)
    if mtime_path:
        try:
            mtime = os.path.getmtime(mtime_path)
            result['modified'] = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
        except OSError:
            pass
    result['save_name'] = read_save_name(game_dir, slot)
    return result

def _find_file(game_dir: str, prefix: str, slot: int) -> str | None:
    target = f'{prefix}.0{slot}'.upper()
    try:
        for fname in os.listdir(game_dir):
            if fname.upper() == target:
                return os.path.join(game_dir, fname)
    except OSError:
        pass
    return None

def read_save_name(game_dir: str, slot: int) -> str | None:
    names_path = None
    try:
        for fname in os.listdir(game_dir):
            if fname.upper() == 'NAMES.DAT':
                names_path = os.path.join(game_dir, fname)
                break
    except OSError:
        return None
    if not names_path:
        return None
    try:
        with open(names_path, 'rb') as f:
            data = f.read()
    except OSError:
        return None
    offset = slot * _NAMES_SLOT_SIZE
    if offset + _NAMES_SLOT_SIZE > len(data):
        return None
    chunk = data[offset:offset + _NAMES_SLOT_SIZE]
    null_idx = chunk.find(b'\x00')
    if null_idx <= 0:
        return None
    raw = chunk[:null_idx]
    if len(raw) < 2:
        return None
    if not all((32 <= b <= 126 for b in raw)):
        return None
    try:
        return raw.decode('ascii')
    except UnicodeDecodeError:
        return None

def write_save_name(game_dir: str, slot: int, name: str) -> bool:
    names_path = None
    try:
        for fname in os.listdir(game_dir):
            if fname.upper() == 'NAMES.DAT':
                names_path = os.path.join(game_dir, fname)
                break
    except OSError:
        return False
    if not names_path:
        return False
    try:
        with open(names_path, 'rb') as f:
            data = bytearray(f.read())
    except OSError:
        return False
    offset = slot * _NAMES_SLOT_SIZE
    if offset + _NAMES_SLOT_SIZE > len(data):
        return False
    encoded = bytearray()
    for ch in name:
        b = ord(ch)
        if 32 <= b <= 126:
            encoded.append(b)
        if len(encoded) >= _NAMES_SLOT_SIZE - 1:
            break
    chunk = bytearray(_NAMES_SLOT_SIZE)
    chunk[:len(encoded)] = encoded
    data[offset:offset + _NAMES_SLOT_SIZE] = chunk
    try:
        with open(names_path, 'wb') as f:
            f.write(bytes(data))
    except OSError:
        return False
    return True
