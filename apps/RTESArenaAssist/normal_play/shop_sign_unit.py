from __future__ import annotations
import logging
from typing import Optional
from assist_log import recog as _recog
_log = logging.getLogger('RTESArenaAssist')
RETRY_POLLS = 10

def _reset(w, door_pos) -> None:
    w._shop_sign_door = door_pos
    w._shop_sign_seeded = False
    w._shop_sign_seed = None
    w._shop_sign_name = None
    w._shop_sign_en = ''
    w._shop_sign_tries = 0

def release_shop_sign(w) -> None:
    _reset(w, None)

def poll_shop_sign(w, *, door_pos, facility_info) -> Optional[str]:
    if door_pos is None or facility_info is None:
        return None
    if getattr(w, '_shop_sign_door', None) != door_pos:
        _reset(w, door_pos)
    name = getattr(w, '_shop_sign_name', None)
    if name is not None:
        return name or None
    w._shop_sign_tries = int(getattr(w, '_shop_sign_tries', 0)) + 1
    if w._shop_sign_tries % RETRY_POLLS != 1:
        return None
    from city_viewer_bridge import read_shop_sign, translate_shop_sign
    observed = read_shop_sign(getattr(w, '_analyzer', None), getattr(w, '_anchor', None), facility_info)
    if not getattr(w, '_shop_sign_seeded', False):
        w._shop_sign_seeded = True
        w._shop_sign_seed = observed
        return None
    if not observed or observed == w._shop_sign_seed:
        return None
    list_en = getattr(facility_info, 'name_en', '') or ''
    if observed == list_en:
        w._shop_sign_name = ''
        w._shop_sign_en = observed
        return None
    ja = translate_shop_sign(observed, facility_info)
    if not ja:
        return None
    w._shop_sign_name = ja
    w._shop_sign_en = observed
    _recog(_log, '店内の表示名: %r（街の一覧の名前は %r）', ja, getattr(facility_info, 'name_ja', None) or list_en or None)
    return ja
__all__ = ['poll_shop_sign', 'release_shop_sign', 'RETRY_POLLS']
