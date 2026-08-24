from __future__ import annotations
import logging
import i18n_helper as i18n
from assist_log import recog as _recog
from normal_play import lock_difficulty
_log = logging.getLogger('RTESArenaAssist')
OWNER = 'lock_message'
_MESSAGE_ID_PREFIX = 'lock_messages.difficulty.'
_LOCK_SEARCH_RANGE = 3
_ARM_RANGE = 5
_ARM_RANGE_D2_OUT = 8
_FIELD_JUDGE_RANGE = 1
_DISARM_POLLS = 30
_ABSENT_POLLS_TO_END = 10
_PENDING_POLLS = 15

def _panel_owner(w) -> str:
    try:
        return w._ui_router.current_owner() or ''
    except (AttributeError, RuntimeError):
        return getattr(w, '_panel_owner', '') or ''

def resolve_current_mif(w):
    cur = getattr(w, '_current_map_level', None)
    if not cur:
        return (None, None)
    try:
        mif, index = cur
    except (TypeError, ValueError):
        return (None, None)
    if not mif or index is None:
        return (None, None)
    return (mif, index)

def _locks_for(w, mif_name: str, level_index: int):
    key = (mif_name.upper(), int(level_index))
    if getattr(w, '_lock_msg_level_key', None) == key:
        return getattr(w, '_lock_msg_locks', ())
    locks: tuple = ()
    try:
        import assist_settings as settings
        from runtime_paths import resolve_arena_install_dir
        from services.mif_loader import DEFAULT_MIF_DIR, load_mif
        dirs = [d for d in (settings.get('mif_dir', '') or None, DEFAULT_MIF_DIR, resolve_arena_install_dir()) if d]
        mif = load_mif(mif_name, dirs, level_index_override=int(level_index))
        if mif is not None:
            locks = tuple(((int(e.x), int(e.y), int(e.level)) for e in mif.locks or []))
    except Exception:
        _log.exception('lock message: MIF の LOCK 読取に失敗: %s', mif_name)
        locks = ()
    w._lock_msg_level_key = key
    w._lock_msg_locks = locks
    return locks

class _LockNearby:
    __slots__ = ('lock', 'where', 'reason', 'near', 'known')

    def __init__(self, lock=None, where='', reason='', near=False, known=True):
        self.lock = lock
        self.where = where
        self.reason = reason
        self.near = near
        self.known = known

def resolve_nearby_lock(w, rt_x, rt_z) -> _LockNearby:
    if rt_x is None or rt_z is None:
        return _LockNearby(reason=f'位置が不明 rt=({rt_x},{rt_z})', known=False)
    cur_mif, level_index = resolve_current_mif(w)
    if cur_mif is not None and level_index is not None:
        locks = _locks_for(w, cur_mif, level_index)
        where = '%s#%s' % (cur_mif, level_index)
        if not locks:
            return _LockNearby(where=where, reason=f'錠が無い mif={cur_mif} level={level_index}')
        found = lock_difficulty.find_nearest_lock(int(rt_x), int(rt_z), locks, max_range=_ARM_RANGE)
        if found is None:
            return _LockNearby(where=where, reason='近くに錠が無い 位置=(%s,%s) 錠=%s' % (rt_x, rt_z, list(locks)[:6]))
        dist = abs(found[0] - int(rt_x)) + abs(found[1] - int(rt_z))
        if dist > _LOCK_SEARCH_RANGE:
            return _LockNearby(where=where, near=True, reason='近くに錠が無い 位置=(%s,%s) 最寄り=%s 距離=%d' % (rt_x, rt_z, found, dist))
        return _LockNearby(lock=found, where=where, near=True)
    field = _nearest_field_door(w)
    if field is not None:
        return field
    door, d2 = _nearest_outdoor_door(w, rt_x, rt_z)
    place = getattr(w, '_current_outdoor_location', '') or '?'
    where = '屋外 %s' % place
    if door is None:
        return _LockNearby(where=where, reason='近くに扉が無い 位置=(%s,%s) 場所=%r' % (rt_x, rt_z, place))
    try:
        from services.arena_level_utils import get_door_voxel_lock_level
        level = get_door_voxel_lock_level(door.original_x, door.original_y)
    except ImportError:
        return _LockNearby(where=where, near=True, reason='扉の施錠レベルを引けない')
    if d2 > 2:
        return _LockNearby(where=where, near=True, reason='近くに扉が無い 位置=(%s,%s) 最寄り=(%d,%d) d2=%d' % (rt_x, rt_z, door.original_x, door.original_y, d2))
    return _LockNearby(lock=(int(rt_x), int(rt_z), level), where=where, near=True)

def _nearest_field_door(w):
    door = getattr(w, '_current_field_door', None)
    if not door:
        return None
    abs_x, abs_y, dist = door
    where = 'フィールド %s' % (getattr(w, '_current_outdoor_location', '') or '?')
    if dist is not None and dist > _FIELD_JUDGE_RANGE:
        return _LockNearby(where=where, near=True, reason='扉に接していない 扉=(%d,%d) 距離=%s' % (abs_x, abs_y, dist))
    try:
        from services.arena_level_utils import get_door_voxel_lock_level
        level = get_door_voxel_lock_level(abs_x, abs_y)
    except ImportError:
        return _LockNearby(where=where, near=True, reason='扉の施錠レベルを引けない')
    return _LockNearby(lock=(abs_x, abs_y, level), where=where, near=True)

def _nearest_outdoor_door(w, rt_x, rt_z):
    place = getattr(w, '_current_outdoor_location', '') or ''
    if not place:
        return (None, 0)
    if getattr(w, '_lock_msg_doors_key', None) != place:
        doors = ()
        try:
            from services.city_lookup import get_city_doors_by_location_name
            doors = tuple(get_city_doors_by_location_name(place) or ())
        except Exception:
            _log.exception('lock message: 街の扉一覧の取得に失敗: %s', place)
        w._lock_msg_doors_key = place
        w._lock_msg_doors = doors
    doors = getattr(w, '_lock_msg_doors', ())
    if not doors:
        return (None, 0)
    try:
        from services.city_door_detector import door_at
    except ImportError:
        return (None, 0)
    door = door_at(doors, int(rt_x), int(rt_z), max_d2=_ARM_RANGE_D2_OUT)
    if door is None:
        return (None, 0)
    dx = door.original_x - int(rt_x)
    dy = door.original_y - int(rt_z)
    return (door, dx * dx + dy * dy)

def _exe_tables(w):
    anchor = getattr(w, '_anchor', None)
    if getattr(w, '_lock_msg_tables_tried', None) == anchor:
        return getattr(w, '_lock_msg_tables', None)
    w._lock_msg_tables_tried = anchor
    tables = None
    try:
        import arena_aexe
        tables = arena_aexe.read_lock_message_data(w._analyzer, anchor)
    except Exception:
        _log.exception('lock message: 施錠メッセージの表の読取に失敗')
        tables = None
    w._lock_msg_tables = tables
    return tables

def _thieving_divisor(w, tables) -> int | None:
    try:
        import assist_settings as settings
        from attributes_panel import OFF_CLASS_INDEX
        cls_id = w._analyzer.read_bytes(w._anchor + OFF_CLASS_INDEX, 1)[0]
    except (OSError, AttributeError, IndexError, ImportError):
        return None
    class_en = (settings.get('arena_play_class_id_map', {}) or {}).get(str(cls_id))
    if not class_en:
        return None
    idx = lock_difficulty.class_index_from_name(class_en, tables['class_names'])
    if idx is None:
        return None
    divisors = tables['thieving_divisors']
    if not 0 <= idx < len(divisors):
        return None
    divisor = divisors[idx]
    return divisor if divisor > 0 else None

def _player_stats(w):
    try:
        from attributes_panel import OFF_LEVEL_U8, OFF_PRIMARY_1, PRIMARY_LEN
        level_raw = w._analyzer.read_bytes(w._anchor + OFF_LEVEL_U8, 1)[0]
        primary = w._analyzer.read_bytes(w._anchor + OFF_PRIMARY_1, PRIMARY_LEN)
    except (OSError, AttributeError, IndexError, ImportError):
        return None
    if len(primary) < PRIMARY_LEN:
        return None
    intelligence = lock_difficulty.attribute_display_from_memory(primary[1])
    agility = lock_difficulty.attribute_display_from_memory(primary[3])
    return (int(level_raw), intelligence, agility)

def _resolve_message(tables, index: int) -> tuple[str, str]:
    messages = tables['messages']
    original = messages[index] if 0 <= index < len(messages) else ''
    translated = i18n.text_opt(f'{_MESSAGE_ID_PREFIX}{index}') or ''
    if translated == original:
        translated = ''
    return (original, translated)

def _watcher(w):
    from screen_detector import ActionTextWatcher
    watcher = getattr(w, '_lock_msg_watcher', None)
    if watcher is None:
        watcher = ActionTextWatcher()
        w._lock_msg_watcher = watcher
    return watcher

def update_watch(w, near) -> bool:
    armed = bool(getattr(w, '_lock_msg_armed', False))
    if near.known:
        if near.near:
            w._lock_msg_disarm_count = 0
            armed = True
        else:
            count = int(getattr(w, '_lock_msg_disarm_count', 0)) + 1
            w._lock_msg_disarm_count = count
            hold = bool(getattr(w, '_lock_msg_live', False)) or int(getattr(w, '_lock_msg_pending', 0)) > 0 or count < _DISARM_POLLS
            armed = hold and armed
    if armed != bool(getattr(w, '_lock_msg_armed', False)):
        _recog(_log, '赤文字の見張り: %s（%s）', '開始' if armed else '休止', near.where or near.reason)
    w._lock_msg_armed = armed
    if armed or getattr(w, '_lock_msg_watcher', None) is not None:
        try:
            watcher = _watcher(w)
            watcher.ensure(w._analyzer, w._anchor)
            watcher.set_active(armed)
        except (OSError, AttributeError, ImportError, RuntimeError):
            return False
    return armed

def read_drawn(w) -> bool | None:
    try:
        return _watcher(w).consume()
    except (OSError, AttributeError, ImportError, RuntimeError):
        return None

def update_live(w, drawn: bool | None) -> bool:
    if drawn is None:
        return bool(getattr(w, '_lock_msg_live', False))
    if drawn:
        w._lock_msg_absent = 0
        w._lock_msg_live = True
        return True
    absent = int(getattr(w, '_lock_msg_absent', 0)) + 1
    w._lock_msg_absent = absent
    if absent >= _ABSENT_POLLS_TO_END:
        w._lock_msg_live = False
    return bool(getattr(w, '_lock_msg_live', False))

def detect_rising_edge(w, drawn: bool | None) -> bool:
    prev = bool(getattr(w, '_lock_msg_live', False))
    live = update_live(w, drawn)
    return live and (not prev)

def _decide(w, b30, near, c1_fg):
    owner_now = _panel_owner(w)
    if owner_now not in ('', OWNER):
        return (None, None, f'他の表示が持ち主 owner={owner_now!r}', True)
    if c1_fg == 'red_text' and b30.get('red_str'):
        return (None, None, f"バッファに本文あり={b30['red_str'][:30]!r}", True)
    if c1_fg not in ('', 'red_text'):
        return (None, None, f'別の面が前景 c1_fg={c1_fg!r}', True)
    if not b30.get('in_gameplay'):
        return (None, None, 'in_gameplay=False', True)
    if getattr(w, '_npc_conversation_active', False):
        return (None, None, 'NPC 会話中', True)
    if not near.known:
        return (None, None, near.reason, True)
    if near.lock is None:
        return (None, None, near.reason, False)
    lock = near.lock
    tables = _exe_tables(w)
    if tables is None:
        return (None, None, '施錠メッセージの表が読めない', False)
    divisor = _thieving_divisor(w, tables)
    if divisor is None:
        return (None, None, 'クラスが決まらない', False)
    stats = _player_stats(w)
    if stats is None:
        return (None, None, '能力値が読めない', False)
    player_level, intelligence, agility = stats
    try:
        index = lock_difficulty.lock_difficulty_index(lock[2], divisor, player_level, intelligence, agility)
    except ValueError as exc:
        return (None, None, f'番号を計算できない: {exc}', False)
    original, translated = _resolve_message(tables, index)
    if not original and (not translated):
        return (None, None, f'番号 {index} の文が引けない', False)
    return (original, translated, '番号=%d 錠=(%d,%d,lv%d) 場所=%s' % (index, lock[0], lock[1], lock[2], near.where), False)

def _color_index(w):
    watcher = getattr(w, '_lock_msg_watcher', None)
    try:
        return watcher.color_index() if watcher is not None else None
    except AttributeError:
        return None

def _watch_stats(w):
    watcher = getattr(w, '_lock_msg_watcher', None)
    try:
        return watcher.stats() if watcher is not None else None
    except AttributeError:
        return None

def poll_lock_message(w, *, b30: dict, rt_x=None, rt_z=None, c1_fg: str='') -> None:
    near = resolve_nearby_lock(w, rt_x, rt_z)
    armed = update_watch(w, near)
    drawn = read_drawn(w) if armed else None
    _obs = (drawn, bool(b30.get('red_str')), bool(b30.get('in_gameplay')), armed, near.where, near.lock is not None)
    if _obs != getattr(w, '_lock_msg_obs_prev', None):
        w._lock_msg_obs_prev = _obs
        _recog(_log, '赤文字の描画: drawn=%s バッファ本文=%s in_gameplay=%s 見張り=%s 場所=%s 近くの錠=%s 色番号=%s (読/当/間隔ms)=%s', drawn, _obs[1], _obs[2], '動作' if armed else '休止', near.where or '-', near.lock or near.reason, _color_index(w), _watch_stats(w))
    if detect_rising_edge(w, drawn):
        w._lock_msg_pending = _PENDING_POLLS
    pending = int(getattr(w, '_lock_msg_pending', 0))
    if pending <= 0:
        return
    w._lock_msg_pending = pending - 1
    original, translated, why, transient = _decide(w, b30, near, c1_fg)
    if original is None and translated is None:
        if not transient:
            w._lock_msg_pending = 0
            _recog(_log, '錠前メッセージ: 出さない（%s）', why)
        elif w._lock_msg_pending <= 0:
            _recog(_log, '錠前メッセージ: 出せないまま持ち越しが切れた（%s）', why)
        return
    w._lock_msg_pending = 0
    w._lock_msg_spoken_seen = False
    w._ui_router.update_translation(OWNER, original, translated, speech_role='situation', speech_action='reannounce')
    _recog(_log, '錠前メッセージ: 出す %s → %r', why, translated or original)

def poll_lock_message_lifetime(w, *, b30: dict) -> None:
    if _panel_owner(w) != OWNER:
        w._lock_msg_spoken_seen = False
        return
    feed = getattr(w, '_translation_feed', None)
    try:
        speaking_owner = feed.speaking_owner() if feed is not None else None
    except AttributeError:
        speaking_owner = None
    try:
        speaking = bool(w._tts.is_speaking())
    except AttributeError:
        speaking = False
    if speaking_owner == OWNER and speaking:
        w._lock_msg_spoken_seen = True
        return
    if getattr(w, '_lock_msg_spoken_seen', False):
        _recog(_log, '錠前メッセージ: 表示終了（読み上げ終了）')
        w._lock_msg_spoken_seen = False
        w._ui_router.clear_if_owner(OWNER)
        return
    if not bool(getattr(w, '_lock_msg_live', False)):
        _recog(_log, '錠前メッセージ: 表示終了（ゲーム側の表示が消えた・読み上げなし）')
        w._ui_router.clear_if_owner(OWNER)

def release_lock_message(w) -> None:
    w._lock_msg_armed = False
    w._lock_msg_disarm_count = 0
    watcher = getattr(w, '_lock_msg_watcher', None)
    if watcher is not None:
        try:
            watcher.set_active(False)
        except AttributeError:
            pass
    w._lock_msg_live = False
    w._lock_msg_absent = 0
    w._lock_msg_pending = 0
    w._lock_msg_spoken_seen = False
    w._lock_msg_level_key = None
    w._lock_msg_locks = ()
    if _panel_owner(w) == OWNER:
        w._ui_router.clear_if_owner(OWNER)
__all__ = ['OWNER', 'read_drawn', 'update_live', 'detect_rising_edge', 'resolve_current_mif', 'poll_lock_message', 'poll_lock_message_lifetime', 'release_lock_message']
