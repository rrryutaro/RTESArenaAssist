from __future__ import annotations
GAMESTATE_BASE_OFFSET = 47878
GS_LEVEL_NAME_OFFSET = 1934
GS_INF_NAME_OFFSET = 1967
GS_MIF_NAME_OFFSET = 2169
_NAME_MAXLEN = 33

def _read_str(analyzer, addr: int, maxlen: int=_NAME_MAXLEN) -> str:
    try:
        raw = analyzer.read_bytes(addr, maxlen)
    except (OSError, AttributeError):
        return ''
    return raw.split(b'\x00')[0].decode('ascii', errors='replace').strip()

def read_level_identity(analyzer, anchor: int) -> dict | None:
    base = anchor + GAMESTATE_BASE_OFFSET
    level = _read_str(analyzer, base + GS_LEVEL_NAME_OFFSET)
    inf = _read_str(analyzer, base + GS_INF_NAME_OFFSET)
    mif = _read_str(analyzer, base + GS_MIF_NAME_OFFSET)
    if not is_consistent(level, inf, mif):
        return None
    return {'level': level, 'inf': inf, 'mif': mif}

def is_consistent(level: str, inf: str, mif: str) -> bool:
    return bool(level) and inf.lower().endswith('.inf') and mif.lower().endswith('.mif')

def match_level_index(identity: dict | None, level_names: list[str], level_infs: list[str] | None=None) -> int | None:
    if not identity:
        return None

    def _unique(cands: list[str], want: str) -> int | None:
        want = (want or '').strip().lower()
        if not want:
            return None
        hits = [i for i, n in enumerate(cands) if (n or '').strip().lower() == want]
        return hits[0] if len(hits) == 1 else None
    idx = _unique(level_names or [], identity.get('level', ''))
    if idx is None and level_infs:
        idx = _unique(level_infs, identity.get('inf', ''))
    return idx
