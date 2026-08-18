from __future__ import annotations
from viewer_constants import LOOT_RECORD_SIZE, LOOT_RECORD_MAX
GOLD_NONE = 65535

def _u16(raw: bytes, i: int) -> int:
    return raw[i] | raw[i + 1] << 8

def parse_records(raw: bytes) -> list[dict]:
    out: list[dict] = []
    for k in range(LOOT_RECORD_MAX):
        off = k * LOOT_RECORD_SIZE
        rec = raw[off:off + LOOT_RECORD_SIZE]
        if len(rec) < LOOT_RECORD_SIZE or not any(rec):
            continue
        gold = _u16(rec, 5)
        out.append({'index': k, 'container': _u16(rec, 2), 'floor': rec[4], 'gold': gold, 'is_gold': gold != GOLD_NONE})
    return out

def items_in_container(records: list[dict], container: int, floor: int | None=None) -> list[dict]:
    return [r for r in records if r['container'] == container and (floor is None or r['floor'] == floor)]

def container_item_count(records: list[dict], container: int, floor: int | None=None) -> int:
    return len(items_in_container(records, container, floor))
