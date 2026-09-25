from __future__ import annotations
import logging
import re as _re
from dataclasses import dataclass
import arena_flc
from arena_bridge import SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN
from assist_log import recog as _recog
from img_decoder import decode_img_bytes
import npc_dialog_lookup as npcd
from screen_detector import SCREEN_ROW_BYTES, SCREEN_ROWS
from screen_display_copy import display_copies as _screen_display_copies
from top_level.top_level_dispatcher import current_state as _current_top_level
_log = logging.getLogger('RTESArenaAssist')
_CINEMATIC_TEXT_ADDR_OBSERVED = 276188176
_CINEMATIC_TEXT_ADDRS_OBSERVED = (_CINEMATIC_TEXT_ADDR_OBSERVED, 277679824)
_CINEMATIC_TEXT_ANCHOR_DELTAS_OBSERVED = (318080,)
_CINEMATIC_FULLREAD = 4096
_CINEMATIC_SCAN_START = 268435456
_CINEMATIC_SCAN_END = 301989888
_DEATH_GOOD_PREFIX = 'With you died our last hope for justice.'
_DEATH_BAD_PREFIX = 'You were a fool to confront me,'
_DREAM_TEMPLATE_KEYS = frozenset({*range(1294, 1303), *range(1392, 1400), 1500})
_INTRO_TEMPLATE_KEYS = frozenset({1400})
_IMPERIAL_TEMPLATE_KEYS = frozenset({1447, 1404, 1405, 1406, 1407})
_IMPERIAL_LAST_LINE_KEY = 1404
_EMPEROR_TEMPLATE_KEYS = (1405, 1406, 1407)
_FINAL_TEXT_GATE_KEYS = frozenset({_IMPERIAL_LAST_LINE_KEY, *_EMPEROR_TEMPLATE_KEYS})
_ENDING_TEMPLATE_KEYS = frozenset({1401})
_FINAL_SEQUENCE_TEMPLATE_KEYS = frozenset({*_FINAL_TEXT_GATE_KEYS, *_ENDING_TEMPLATE_KEYS})
_FINAL_UNIT_ORDER = ('imperial_last_line', 'emperor_all', 'ending')
_VISION_TEMPLATE_KEYS = frozenset(_DREAM_TEMPLATE_KEYS | _INTRO_TEMPLATE_KEYS | _IMPERIAL_TEMPLATE_KEYS | _ENDING_TEMPLATE_KEYS)
_DEATH_TEMPLATE_KEYS = frozenset({1402, 1403})
_CINEMATIC_TEMPLATE_KEYS = frozenset(_VISION_TEMPLATE_KEYS | _DEATH_TEMPLATE_KEYS)
_SCENE_PICTURES = ('JAGAR.FLC', 'VISION.FLC', 'HOUSE.IMG', 'KING.FLC', 'NUKING.FLC', 'AFLC2.FLC', 'END01.FLC', 'END02.FLC', 'JAGARDTH.FLC', 'NUJAGDTH.FLC', 'JAGRSHLD.FLC', 'MORPH.FLC', 'WARHAFT.FLC')
_PLAYER_HP_CURRENT_OFFSET = 509
_PLAYER_NAME_OFFSET = 429
_PLAYER_NAME_LEN = 26
_DEATH_GOOD_JA = 'お前とともに、正義への最後の希望も死んだ。サーンは今や望むままに振る舞うだろう。美しいタムリエルの地が内側から腐っていくのを見るのは悲しい。さようなら、[名前]。来世で安らぎを得られますように...'
_DEATH_BAD_JA = '愚かにも私に立ち向かい、ついに究極の代償を払ったな。今この時も、我が僕が貴様の朽ちた肉体を取りに向かっている。貴様は皇帝となった我が年月において、アンデッドとしてよく仕えることになる。もしかすると記憶の一部を残してやるかもしれん。そうすれば、失敗の代償が貴様にも意味を持つだろう....'

def _read_cinematic_block(w, address: int, *, template_keys: frozenset=_CINEMATIC_TEMPLATE_KEYS) -> str:
    from cinematic_text import read_block
    return read_block(w._analyzer, address, sizes=(_CINEMATIC_FULLREAD, 2048, 1024, 512, 256), template_keys=template_keys)

def _read_screen_img_name(w) -> str:
    try:
        raw = w._analyzer.read_bytes(w._anchor + SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN)
    except (OSError, AttributeError, TypeError):
        return ''
    try:
        return raw.split(b'\x00', 1)[0].decode('ascii', errors='replace').upper()
    except Exception:
        return ''

def _read_player_name(w) -> str:
    try:
        raw = w._analyzer.read_bytes(w._anchor + _PLAYER_NAME_OFFSET, _PLAYER_NAME_LEN)
    except (OSError, AttributeError, TypeError):
        return ''
    try:
        return raw.split(b'\x00', 1)[0].decode('ascii', errors='replace').strip()
    except Exception:
        return ''

def _death_cinematic_translation(text: str) -> str:
    if text.startswith(_DEATH_GOOD_PREFIX):
        name = '旅人'
        m = _re.search('Goodbye,\\s+(.+?)\\.', text)
        if m:
            name = m.group(1).strip()
        return _DEATH_GOOD_JA.replace('[名前]', name)
    if text.startswith(_DEATH_BAD_PREFIX):
        return _DEATH_BAD_JA
    return ''
_ANCHORLESS_KEYS_CACHE: dict[frozenset, frozenset] = {}

def _anchorless_keys(keys: frozenset=_VISION_TEMPLATE_KEYS) -> frozenset:
    cached = _ANCHORLESS_KEYS_CACHE.get(keys)
    if cached is None:
        cached = frozenset((key for key in keys if not npcd.body_head_anchors(frozenset({key}))))
        _ANCHORLESS_KEYS_CACHE[keys] = cached
    return cached

def _detect_cinematic_text(text: str) -> bool:
    if not text:
        return False
    if _death_cinematic_translation(text):
        return True
    body = ' '.join(text.split())
    anchors = npcd.body_head_anchors(_VISION_TEMPLATE_KEYS)
    if anchors and body.startswith(anchors):
        return True
    anchorless = _anchorless_keys(_VISION_TEMPLATE_KEYS)
    return bool(anchorless) and npcd.lookup_body_fixed_parts(text, keys=anchorless) is not None

def _lookup_vision_cinematic_payload(w, text: str) -> tuple[str, str, str] | None:
    if not text:
        return None
    death_ja = _death_cinematic_translation(text)
    if death_ja:
        return ('death_cinematic', text, death_ja)
    en = text
    resolved = npcd.lookup_body_head(text, keys=_VISION_TEMPLATE_KEYS)
    if resolved is not None:
        ja_template, placeholders = resolved
    else:
        fixed = npcd.lookup_body_fixed_parts(text, keys=_anchorless_keys(_VISION_TEMPLATE_KEYS))
        if fixed is None:
            return None
        ja_template, placeholders, en = fixed
        if not ja_template:
            return None
    player_name = placeholders.get('pcn') or placeholders.get('pcf') or _read_player_name(w)
    if player_name:
        for key in ('pcn', 'pcf'):
            if not placeholders.get(key):
                placeholders[key] = player_name
    ja = npcd.format_japanese(ja_template, placeholders)
    if not ja:
        return None
    return ('vision_cinematic', en, ja)

def _vision_template_key(text: str, keys: frozenset=_VISION_TEMPLATE_KEYS) -> int | None:
    found: list[int] = []
    for key in sorted(keys):
        one = frozenset({key})
        if npcd.lookup_body_head(text, keys=one) is not None:
            found.append(key)
            continue
        if npcd.lookup_body_fixed_parts(text, keys=one) is not None:
            found.append(key)
    return found[0] if len(found) == 1 else None

def _final_unit_key(template_key: int | None) -> str:
    if template_key == _IMPERIAL_LAST_LINE_KEY:
        return 'imperial_last_line'
    if template_key in _EMPEROR_TEMPLATE_KEYS:
        return 'emperor_all'
    if template_key in _ENDING_TEMPLATE_KEYS:
        return 'ending'
    return ''

def _grouped_vision_payload(w, text: str, template_key: int | None) -> tuple[str, str, str] | None:
    if template_key not in _EMPEROR_TEMPLATE_KEYS:
        return _lookup_vision_cinematic_payload(w, text)
    return _render_final_unit_payload(w, 'emperor_all')

def _render_final_unit_payload(w, unit: str) -> tuple[str, str, str] | None:
    keys = {'imperial_last_line': (_IMPERIAL_LAST_LINE_KEY,), 'emperor_all': _EMPEROR_TEMPLATE_KEYS, 'ending': tuple(_ENDING_TEMPLATE_KEYS)}.get(unit)
    if not keys:
        return None
    player_name = _read_player_name(w)
    rendered = npcd.render_body_group(keys, {'pcn': player_name, 'pcf': player_name})
    if rendered is None:
        return None
    en, ja = rendered
    return ('vision_cinematic', en, ja)

def _show_vision_payload(w, payload: tuple[str, str, str], *, speech_action: str='replace') -> None:
    owner, en, ja = payload
    try:
        w._ui_router.propose_translation(owner, en, ja, priority=46, reason='vision_cinematic', speech_role='situation', speech_action=speech_action)
    except AttributeError:
        w._ui_router.update_translation(owner, en, ja, speech_role='situation', speech_action=speech_action)

def reset_final_sequence(w) -> None:
    w._final_sequence_seen_units = frozenset()
    w._final_sequence_started = False
    w._final_presentation_queue = ()
    w._final_presentation_active = None
    w._final_presentation_action = 'replace'

def _close_final_presentation(w) -> None:
    if not getattr(w, '_final_sequence_started', False):
        return
    try:
        w._ui_router.notify_display_context_ended('vision_cinematic')
    except AttributeError:
        pass
    try:
        w._ui_router.clear_if_owner('vision_cinematic', notify_close=False)
    except AttributeError:
        pass
    w._final_sequence_started = False
    w._final_presentation_queue = ()
    w._final_presentation_active = None
    w._final_presentation_action = 'replace'
    try:
        from controllers.poll_controller import reset_coord_transition_on_world_jump
        reset_coord_transition_on_world_jump(w)
    except (AttributeError, ImportError):
        pass
    _recog(_log, 'final sequence context closed on gameplay return')

def _final_speech_pending(w) -> bool:
    try:
        return bool(w._tts.is_speaking())
    except AttributeError:
        return False

def _poll_final_presentation(w) -> None:
    queue = list(getattr(w, '_final_presentation_queue', ()))
    if _final_speech_pending(w):
        active = getattr(w, '_final_presentation_active', None)
        if active is not None:
            _show_vision_payload(w, active, speech_action=getattr(w, '_final_presentation_action', 'replace'))
        return
    if not queue:
        return
    unit, payload = queue.pop(0)
    w._final_presentation_queue = tuple(queue)
    _recog(_log, 'final sequence presentation display unit=%s remaining=%d', unit, len(queue))
    _show_final_sequence_payload(w, payload)

def _enqueue_final_presentation(w, unit: str, payload: tuple[str, str, str]) -> None:
    if not getattr(w, '_final_sequence_started', False) or not _final_speech_pending(w):
        _show_final_sequence_payload(w, payload)
        return
    queue = list(getattr(w, '_final_presentation_queue', ()))
    queue.append((unit, payload))
    w._final_presentation_queue = tuple(queue)
    _recog(_log, 'final sequence presentation queued unit=%s pending=%d', unit, len(queue))

def _show_final_sequence_payload(w, payload: tuple[str, str, str]) -> None:
    action = 'queue' if getattr(w, '_final_sequence_started', False) else 'replace'
    w._final_sequence_started = True
    w._final_presentation_active = payload
    w._final_presentation_action = action
    _show_vision_payload(w, payload, speech_action=action)

def _render_final_units_payload(w, units: list[str]) -> tuple[str, str, str] | None:
    keys: list[int] = []
    for unit in units:
        keys.extend({'imperial_last_line': (_IMPERIAL_LAST_LINE_KEY,), 'emperor_all': _EMPEROR_TEMPLATE_KEYS, 'ending': tuple(_ENDING_TEMPLATE_KEYS)}.get(unit, ()))
    if not keys:
        return None
    player_name = _read_player_name(w)
    rendered = npcd.render_body_group(tuple(keys), {'pcn': player_name, 'pcf': player_name})
    if rendered is None:
        return None
    en, ja = rendered
    return ('vision_cinematic', en, ja)

def _accept_final_sequence_payload(w, unit: str, payload: tuple[str, str, str]) -> bool:
    seen = set(getattr(w, '_final_sequence_seen_units', frozenset()))
    if unit in seen:
        return False
    if unit != 'ending':
        seen.add(unit)
        w._final_sequence_seen_units = frozenset(seen)
        _enqueue_final_presentation(w, unit, payload)
        return True
    missing = [key for key in _FINAL_UNIT_ORDER[:-1] if key not in seen]
    if not missing:
        seen.add(unit)
        w._final_sequence_seen_units = frozenset(seen)
        _enqueue_final_presentation(w, unit, payload)
        return True
    combined_units = [*missing, unit]
    combined = _render_final_units_payload(w, combined_units)
    if combined is None:
        return False
    seen.update(combined_units)
    w._final_sequence_seen_units = frozenset(seen)
    w._final_presentation_queue = ()
    _recog(_log, 'final sequence combined at ending missing=%s units=%d', missing, len(combined_units))
    _show_final_sequence_payload(w, combined)
    return True

def _candidate_text_addrs(w) -> tuple[int, ...]:
    out: list[int] = []
    latched = int(getattr(w, '_cinematic_text_addr', 0) or 0)
    if latched:
        out.append(latched)
    anchor = int(getattr(w, '_anchor', 0) or 0)
    if anchor:
        out.extend((anchor + delta for delta in _CINEMATIC_TEXT_ANCHOR_DELTAS_OBSERVED))
    out.extend(_CINEMATIC_TEXT_ADDRS_OBSERVED)
    return tuple(dict.fromkeys(out))

def _iter_candidate_blocks(w, *, template_keys: frozenset=_CINEMATIC_TEMPLATE_KEYS):
    for addr in _candidate_text_addrs(w):
        block = _read_cinematic_block(w, addr, template_keys=template_keys)
        if block:
            yield (addr, block)

def _probe_cinematic_text(w, resolver, *, template_keys: frozenset=_CINEMATIC_TEMPLATE_KEYS, blocks=None) -> tuple[str, int]:
    source = blocks if blocks is not None else _iter_candidate_blocks(w, template_keys=template_keys)
    for addr, block in source:
        if resolver(block):
            w._cinematic_text_addr = addr
            return (block, addr)
    return ('', 0)

def _cinematic_scan_prefixes(template_keys: frozenset=_CINEMATIC_TEMPLATE_KEYS) -> tuple[str, ...]:
    return npcd.body_head_anchors(template_keys)

def _scan_vision_cinematic_text(w, resolver, *, template_keys: frozenset=_CINEMATIC_TEMPLATE_KEYS, error_attr: str='_cinematic_scan_error_logged') -> tuple[str, int]:
    for prefix in _cinematic_scan_prefixes(template_keys):
        try:
            results = w._analyzer.scan_string(prefix, _CINEMATIC_SCAN_START, _CINEMATIC_SCAN_END)
        except (OSError, RuntimeError, AttributeError) as exc:
            if not getattr(w, error_attr, False):
                setattr(w, error_attr, True)
                _log.info('cinematic scan_string error: %s', exc)
            continue
        if not results:
            continue
        for result in results:
            addr = getattr(result, 'address', 0)
            if not addr:
                continue
            block = _read_cinematic_block(w, addr, template_keys=template_keys)
            if block and resolver(block):
                w._cinematic_text_addr = addr
                return (block, addr)
    return ('', 0)

def _find_vision_cinematic_text(w, *, allow_scan: bool=True) -> tuple[str, int]:
    text, addr = _probe_cinematic_text(w, _detect_cinematic_text)
    if text:
        return (text, addr)
    if not allow_scan:
        return ('', 0)
    return _scan_vision_cinematic_text(w, _detect_cinematic_text)

def _accept_vision_text(w, text: str, addr: int) -> None:
    template_key = _vision_template_key(text, _FINAL_SEQUENCE_TEMPLATE_KEYS)
    payload = _grouped_vision_payload(w, text, template_key)
    if payload is None:
        if text != getattr(w, '_cinematic_unresolved_prev', ''):
            w._cinematic_unresolved_prev = text
            _recog(_log, 'cinematic detected but unresolved addr=0x%08X len=%d', addr, len(text))
        return
    owner, en, ja = payload
    final_unit = _final_unit_key(template_key)
    if final_unit:
        if not _accept_final_sequence_payload(w, final_unit, payload):
            return
        w._vision_cinematic_text_prev = text
        w._cinematic_last_accepted_text = text
        _recog(_log, 'vision cinematic accepted owner=%s addr=0x%08X len=%d picture=%s', owner, addr, len(text), _picture_now(w))
        return
    prev_attr = '_death_cinematic_text_prev' if owner == 'death_cinematic' else '_vision_cinematic_text_prev'
    if text == getattr(w, prev_attr, ''):
        return
    setattr(w, prev_attr, text)
    w._cinematic_last_accepted_text = text
    _recog(_log, 'vision cinematic accepted owner=%s addr=0x%08X len=%d picture=%s', owner, addr, len(text), _picture_now(w))
    _show_vision_payload(w, payload)

def _poll_vision_state(w, *, allow_scan: bool=True) -> None:
    text, addr = _find_vision_cinematic_text(w, allow_scan=allow_scan)
    if text:
        _accept_vision_text(w, text, addr)
_FRAME_LEN = SCREEN_ROWS * SCREEN_ROW_BYTES
_MAIN_QUEST_STATE_OFFSET = 3958
_MAIN_QUEST_STATE_LEN = 10

@dataclass(frozen=True)
class PictureSignature:
    name: str
    x: int
    columns: frozenset

    def describe(self) -> str:
        return '%s@%d:%d' % (self.name, self.x, len(self.columns))

def column_of(frame, x: int, width: int=SCREEN_ROW_BYTES, height: int=SCREEN_ROWS) -> bytes:
    return bytes(frame[x::width][:height])

def is_uniform(column) -> bool:
    return len(set(column)) < 2

def derive_column_signature(name: str, width: int, height: int, frames) -> PictureSignature | None:
    if (width, height) != (SCREEN_ROW_BYTES, SCREEN_ROWS):
        return None
    for x in (0, width - 1):
        columns = frozenset((column for column in (column_of(frame, x, width, height) for frame in frames) if len(column) == height and (not is_uniform(column))))
        if columns:
            return PictureSignature(name, x, columns)
    return None

def _picture_frames(vfs, name: str):
    upper = name.upper()
    if upper.endswith('.FLC'):
        anim = arena_flc.load(vfs, name)
        if anim is None:
            return None
        return (anim.width, anim.height, anim.frames)
    if upper.endswith('.IMG'):
        try:
            raw = vfs.read(name)
            if not raw:
                return None
            width, height, pixels, _palette = decode_img_bytes(raw, name)
        except Exception:
            return None
        if len(pixels) < width * height:
            return None
        return (width, height, (bytes(pixels[:width * height]),))
    return None

def derive_picture_signatures(vfs, names=_SCENE_PICTURES):
    signed: list[PictureSignature] = []
    unsignable: list[str] = []
    missing: list[str] = []
    for name in names:
        frames = _picture_frames(vfs, name) if vfs is not None else None
        if frames is None:
            missing.append(name)
            continue
        signature = derive_column_signature(name, *frames)
        if signature is None:
            unsignable.append(name)
            continue
        signed.append(signature)
    return (tuple(signed), tuple(unsignable), tuple(missing))

def _picture_vfs():
    from runtime_paths import install_vfs
    return install_vfs()
_SIGNATURES_UNDERIVED = object()

def _scene_signatures(w) -> tuple:
    vfs = _picture_vfs()
    key = getattr(vfs, 'arena_dir', None) if vfs is not None else None
    if getattr(w, '_cinematic_pictures_key', _SIGNATURES_UNDERIVED) == key:
        return getattr(w, '_cinematic_pictures', ())
    signed, unsignable, missing = derive_picture_signatures(vfs)
    w._cinematic_pictures_key = key
    w._cinematic_pictures = signed
    _recog(_log, 'cinematic pictures: dir=%r signed=[%s] unsignable=%s missing=%s', key, ', '.join((s.describe() for s in signed)), list(unsignable), list(missing))
    return signed

@dataclass(frozen=True)
class ScenePicture:
    name: str = ''
    copy: int = 0
    copies: tuple = ()
    columns: tuple = ()
    signed: bool = True
    indeterminate: bool = False

    @property
    def lit(self) -> bool:
        return bool(self.name)

    def describe(self, signatures=()) -> str:
        if self.lit:
            return '%s@0x%X' % (self.name, self.copy)
        if not self.signed:
            return 'unread(no signatures)'
        if not self.copies:
            return 'unread(no display copy)'
        if self.indeterminate:
            return 'unknown(uniform copies=%d)' % len(self.copies)
        nearest = _nearest_picture(self.columns, signatures)
        return 'none(copies=%d nearest=%s)' % (len(self.copies), nearest or '-')

def _nearest_picture(columns, signatures) -> str:
    best = ('', -1)
    for _base, cols in columns:
        for signature in signatures:
            column = cols.get(signature.x)
            if not column:
                continue
            for candidate in signature.columns:
                rows = sum((1 for a, b in zip(column, candidate) if a == b))
                if rows > best[1]:
                    best = (signature.name, rows)
    if not best[0]:
        return ''
    return '%s:%d/%d' % (best[0], best[1], SCREEN_ROWS)

def _read_frame(analyzer, base: int) -> bytes | None:
    try:
        raw = analyzer.read_bytes(base, _FRAME_LEN)
    except (OSError, RuntimeError, AttributeError, TypeError):
        return None
    if not isinstance(raw, (bytes, bytearray)) or len(raw) < _FRAME_LEN:
        return None
    return bytes(raw)

def _display_copies(w) -> tuple:
    return _screen_display_copies(w).bases

def _observe_scene_picture(w, signatures) -> ScenePicture:
    if not signatures:
        return ScenePicture(signed=False)
    analyzer = getattr(w, '_analyzer', None)
    bases = _display_copies(w)
    if analyzer is None or not bases:
        return ScenePicture()
    xs = sorted({signature.x for signature in signatures})
    copies: list[int] = []
    columns: list[tuple] = []
    for base in bases:
        frame = _read_frame(analyzer, base)
        if frame is None:
            continue
        cols = {x: column_of(frame, x) for x in xs}
        copies.append(base)
        columns.append((base, cols))
        for signature in signatures:
            if cols[signature.x] in signature.columns:
                return ScenePicture(name=signature.name, copy=base, copies=tuple(copies), columns=tuple(columns))
    indeterminate = bool(columns) and all((is_uniform(column) for _base, cols in columns for column in cols.values()))
    return ScenePicture(copies=tuple(copies), columns=tuple(columns), indeterminate=indeterminate)

def _resolve_scene_picture(w, observed: ScenePicture) -> ScenePicture:
    if not observed.indeterminate:
        w._scene_picture_confirmed = observed
        return observed
    previous = getattr(w, '_scene_picture_confirmed', None)
    if previous is None or not previous.lit:
        return observed
    return ScenePicture(name=previous.name, copy=previous.copy, copies=observed.copies, columns=observed.columns, signed=observed.signed, indeterminate=True)

def forget_scene(w) -> None:
    if getattr(w, '_cinematic_gate_prev', ''):
        _note_gate(w, ScenePicture(), None)
    w._scene_picture_confirmed = ScenePicture()
    w._scene_picture_now = None
    w._cinematic_gate_prev = ''
    w._cinematic_gate_polls = 0
    w._vision_cinematic_text_prev = ''
    reset_final_sequence(w)
    w._cinematic_unresolved_prev = ''
    w._cinematic_scan_error_logged = False

def _picture_now(w) -> str:
    picture = getattr(w, '_scene_picture_now', None)
    if picture is None:
        return '?'
    return picture.describe(getattr(w, '_cinematic_pictures', ()))

def _read_main_quest_state_hex(w) -> str:
    try:
        raw = w._analyzer.read_bytes(w._anchor + _MAIN_QUEST_STATE_OFFSET, _MAIN_QUEST_STATE_LEN)
    except (OSError, RuntimeError, AttributeError, TypeError):
        return '?'
    if not isinstance(raw, (bytes, bytearray)) or len(raw) < _MAIN_QUEST_STATE_LEN:
        return '?'
    return bytes(raw[:_MAIN_QUEST_STATE_LEN]).hex()

def _note_gate(w, picture: ScenePicture, img_name) -> None:
    prev = getattr(w, '_cinematic_gate_prev', '')
    name = picture.name
    if name == prev:
        if name:
            w._cinematic_gate_polls = int(getattr(w, '_cinematic_gate_polls', 0)) + 1
        return
    polls = int(getattr(w, '_cinematic_gate_polls', 0))
    if not prev:
        _recog(_log, 'cinematic gate: open picture=%s img=%r quest=%s', picture.describe(), img_name or '', _read_main_quest_state_hex(w))
    elif not name:
        _recog(_log, 'cinematic gate: closed polls=%d img=%r', polls, img_name or '')
    else:
        _recog(_log, 'cinematic gate: picture %r -> %s polls=%d img=%r', prev, picture.describe(), polls, img_name or '')
    w._cinematic_gate_prev = name
    w._cinematic_gate_polls = 1 if name else 0
_CLOSED_GATE_SIGHT_IMG_LOG_MAX = 6

def _note_vision_text_while_closed(w, text: str, addr: int, img_name: str | None) -> None:
    prev = getattr(w, '_cinematic_closed_sight_text', '')
    if not text:
        if prev:
            w._cinematic_closed_sight_text = ''
        return
    img = img_name or ''
    if text != prev:
        w._cinematic_closed_sight_text = text
        w._cinematic_closed_sight_img = img
        w._cinematic_closed_sight_img_logs = 0
        anchor = int(getattr(w, '_anchor', 0) or 0)
        _recog(_log, 'cinematic text seen while gate closed: img=%r addr=0x%08X rel=0x%X len=%d shown_before=%s picture=%s', img, addr, addr - anchor, len(text), text == getattr(w, '_cinematic_last_accepted_text', ''), _picture_now(w))
        return
    if img == getattr(w, '_cinematic_closed_sight_img', ''):
        return
    w._cinematic_closed_sight_img = img
    count = int(getattr(w, '_cinematic_closed_sight_img_logs', 0)) + 1
    w._cinematic_closed_sight_img_logs = count
    if count <= _CLOSED_GATE_SIGHT_IMG_LOG_MAX:
        _recog(_log, 'cinematic text still seen while gate closed: img=%r (%d/%d)', img, count, _CLOSED_GATE_SIGHT_IMG_LOG_MAX)

def _poll_closed_gate(w, img_name: str | None) -> None:
    blocks = tuple(_iter_candidate_blocks(w))
    text, addr = _probe_cinematic_text(w, lambda block: bool(_death_cinematic_translation(block)), blocks=blocks)
    if not text:
        w._death_cinematic_text_prev = ''
        seen, seen_addr = _probe_cinematic_text(w, _detect_cinematic_text, blocks=blocks)
        key = _vision_template_key(seen, _FINAL_TEXT_GATE_KEYS) if seen else None
        if key in _FINAL_TEXT_GATE_KEYS:
            _note_vision_text_while_closed(w, '', 0, img_name)
            _accept_vision_text(w, seen, seen_addr)
            return
        _note_vision_text_while_closed(w, seen, seen_addr, img_name)
        return
    _note_vision_text_while_closed(w, '', 0, img_name)
    ja = _death_cinematic_translation(text)
    if not ja:
        return
    if text == getattr(w, '_death_cinematic_text_prev', ''):
        return
    w._death_cinematic_text_prev = text
    _log.info('death cinematic accepted addr=0x%08X: %r', addr, text[:96])
    try:
        w._ui_router.propose_translation('death_cinematic', text, ja, priority=45, reason='death_cinematic', speech_role='situation')
    except AttributeError:
        w._ui_router.update_translation('death_cinematic', text, ja, speech_role='situation')

def _log_death_gate_once(w) -> None:
    hp_zero = _current_hp_is_zero(w)
    if not hp_zero:
        w._death_gate_logged = False
        return
    if getattr(w, '_death_gate_logged', False):
        return
    w._death_gate_logged = True
    try:
        img = _read_screen_img_name(w)
        probe_addr = _candidate_text_addrs(w)[0]
        head = _read_cinematic_block(w, probe_addr)
        head_ok = bool(head and _death_cinematic_translation(head))
        _log.info('death gate: top=%r img=%r hp0=True probe_addr=0x%08X probe=%s head=%r', _current_top_level(w), img, probe_addr, head_ok, (head or '')[:60])
    except Exception:
        pass

def poll_cinematic(w, *, b30: dict | None=None) -> None:
    if _current_top_level(w) != 'normal-play':
        return
    _log_death_gate_once(w)
    img_name = b30.get('img_name') if isinstance(b30, dict) else None
    if img_name is None:
        img_name = _read_screen_img_name(w)
    observed = _observe_scene_picture(w, _scene_signatures(w))
    picture = _resolve_scene_picture(w, observed)
    w._scene_picture_now = picture
    final_seen = 'ending' in getattr(w, '_final_sequence_seen_units', frozenset())
    gameplay_returned = bool(isinstance(b30, dict) and b30.get('in_gameplay'))
    if final_seen and (not picture.lit) and gameplay_returned:
        _close_final_presentation(w)
    else:
        _poll_final_presentation(w)
    _note_gate(w, picture, img_name)
    if not picture.lit:
        w._vision_cinematic_text_prev = ''
        w._cinematic_unresolved_prev = ''
        w._cinematic_scan_error_logged = False
        _poll_closed_gate(w, img_name)
        return
    _poll_vision_state(w, allow_scan=not picture.indeterminate)

def _current_hp_is_zero(w) -> bool:
    try:
        raw = w._analyzer.read_bytes(w._anchor + _PLAYER_HP_CURRENT_OFFSET, 2)
    except (OSError, AttributeError, TypeError):
        return False
    if not raw or len(raw) < 2:
        return False
    return int.from_bytes(raw[:2], 'little') == 0
__all__ = ['poll_cinematic', 'reset_final_sequence', 'PictureSignature', 'ScenePicture', 'column_of', 'is_uniform', 'derive_column_signature', 'derive_picture_signatures', 'forget_scene', '_current_hp_is_zero']
