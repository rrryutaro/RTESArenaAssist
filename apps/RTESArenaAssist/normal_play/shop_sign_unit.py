from __future__ import annotations
import logging
from typing import Optional
from assist_log import recog as _recog
_log = logging.getLogger('RTESArenaAssist')

def _reset(w, door_pos) -> None:
    w._shop_sign_door = door_pos
    w._shop_sign_name = None
    w._shop_sign_en = ''
    w._shop_sign_entry_text = ''

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
    from normal_play.building_entry_module import current_entry_text
    text = current_entry_text(w)
    if not text:
        return None
    if text == getattr(w, '_shop_sign_entry_text', ''):
        return None
    w._shop_sign_entry_text = text
    from city_viewer_bridge import extract_shop_sign, translate_shop_sign
    observed = extract_shop_sign(text, facility_info)
    list_en = getattr(facility_info, 'name_en', '') or ''
    if not observed or observed == list_en:
        w._shop_sign_en = observed or ''
        return None
    ja = translate_shop_sign(observed, facility_info)
    if not ja:
        w._shop_sign_en = observed
        return None
    w._shop_sign_name = ja
    w._shop_sign_en = observed
    _recog(_log, '店内の表示名: %r（街の一覧の名前は %r）', ja, getattr(facility_info, 'name_ja', None) or list_en or None)
    return ja
__all__ = ['poll_shop_sign', 'release_shop_sign']
