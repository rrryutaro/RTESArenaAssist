import os
import re
import shutil
from datetime import datetime
DEFAULT_CONF_PATH = 'C:\\Program Files (x86)\\Steam\\steamapps\\common\\The Elder Scrolls Arena\\DOSBox-0.74\\arena.conf'

def read_conf(path: str) -> tuple:
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    index: dict = {}
    values: dict = {}
    current_section: str | None = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            current_section = stripped[1:-1].lower()
            continue
        if not stripped or stripped.startswith('#'):
            continue
        if '=' in stripped and current_section:
            key, _, value = stripped.partition('=')
            key = key.strip().lower()
            value = value.strip()
            index[current_section, key] = i
            values[current_section, key] = value
    return (lines, index, values)

def write_conf(path: str, lines: list, index: dict, new_values: dict) -> None:
    for (section, key), new_val in new_values.items():
        if (section, key) not in index:
            continue
        line_idx = index[section, key]
        old_line = lines[line_idx]
        new_line = re.sub('^(\\s*' + re.escape(key) + '\\s*=\\s*).*', lambda m, v=new_val: m.group(1) + v, old_line.rstrip()) + '\n'
        lines[line_idx] = new_line
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(lines)

def backup_conf(path: str) -> str:
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = path + f'.bak_{ts}'
    shutil.copy2(path, backup_path)
    return backup_path

def get_output_mode(path: str) -> str | None:
    try:
        _, _, values = read_conf(path)
        return values.get(('sdl', 'output'), None)
    except Exception:
        return None

def get_aspect(path: str) -> str | None:
    try:
        _, _, values = read_conf(path)
        return values.get(('render', 'aspect'), None)
    except Exception:
        return None

def get_window_size(path: str) -> tuple[int, int] | None:
    try:
        _, _, values = read_conf(path)
        res = values.get(('sdl', 'windowresolution'), '')
        if 'x' in res:
            w, h = res.split('x', 1)
            return (int(w.strip()), int(h.strip()))
    except Exception:
        pass
    return None
