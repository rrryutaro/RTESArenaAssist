from __future__ import annotations
SPELLDATA_OFFSET = 22502
GRP_OFFS = [22502, 22508, 22514, 22520, 22526, 22532]

def _u16(analyzer, anchor: int, off: int):
    try:
        raw = analyzer.read_bytes(anchor + off, 2)
    except (OSError, AttributeError):
        return None
    if len(raw) < 2:
        return None
    return raw[0] | raw[1] << 8

def read_record_values(analyzer, anchor: int, slot: int=0) -> dict[int, int]:
    col = 0 if slot <= 0 else min(slot, 2) * 2
    out: dict[int, int] = {}
    for grp, base in enumerate(GRP_OFFS):
        v = _u16(analyzer, anchor, base + col)
        if v is not None:
            out[grp] = v
    if out and all((v == 0 for v in out.values())):
        return {}
    return out
__all__ = ['SPELLDATA_OFFSET', 'GRP_OFFS', 'read_record_values']
