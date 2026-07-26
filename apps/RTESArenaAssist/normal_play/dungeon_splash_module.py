from __future__ import annotations
import hashlib
import logging
from normal_play.npc_message_module import NPC_MESSAGE_OWNER
_log = logging.getLogger('RTESArenaAssist')
SPLASH_IMG_TO_SLUG = {'FANGLAIR.IMG': 'fang_lair', 'LABRINTH.IMG': 'labyrinthian', 'GROVE.IMG': 'elden_grove', 'COLOSSUS.IMG': 'halls_of_colossus', 'TOWER.IMG': 'crystal_tower', 'CRYPT.IMG': 'crypt_of_hearts', 'MIRKWOOD.IMG': 'murkwood', 'DAGOTHUR.IMG': 'dagoth_ur'}
_SLUG_BODY_HASH = {'halls_of_colossus': 'bc7dccd6', 'crypt_of_hearts': 'e0711598', 'crystal_tower': '628fdaa3', 'dagoth_ur': '7b7763e0', 'elden_grove': '227a3839', 'fang_lair': '9ec0606f', 'labyrinthian': '16d80867', 'murkwood': 'ff46bcfb'}
_SLUG_ENTRY_INDEX = {'halls_of_colossus': 0, 'crypt_of_hearts': 1, 'crystal_tower': 2, 'dagoth_ur': 3, 'elden_grove': 4, 'fang_lair': 5, 'labyrinthian': 6, 'murkwood': 7}
_BLOCK_OFFSET = 37534
_BLOCK_READ_LEN = 6144
_WIDE_OFFSET = 32768
_WIDE_READ_LEN = 16384
_ENTRY_MAX = 8

def classify_dungeon_splash(screen_img: str | None) -> str | None:
    if not screen_img:
        return None
    return SPLASH_IMG_TO_SLUG.get(screen_img.strip().upper())

def _norm(s: str) -> str:
    return ' '.join(s.split())

def _body_hash(body: str) -> str:
    return hashlib.sha1(body.encode('utf-8')).hexdigest()[:8]

def _read_block_text(analyzer, anchor: int, offset: int, length: int) -> str:
    try:
        raw = analyzer.read_bytes(anchor + offset, length)
    except (OSError, AttributeError):
        return ''
    if not isinstance(raw, (bytes, bytearray)):
        return ''
    return ''.join((chr(b) if 32 <= b <= 126 else '\n' for b in raw))

def _parse_entries(text: str) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    title: str | None = None
    body: list[str] = []
    for line in text.split('\n'):
        line = line.rstrip()
        if line.startswith('#'):
            if title and body:
                entries.append((title, _norm(' '.join(body))))
            title, body = (None, [])
            if len(entries) >= _ENTRY_MAX:
                break
        elif not line.strip():
            continue
        elif title is None:
            title = line.strip()
        else:
            body.append(line)
    if title and body and (len(entries) < _ENTRY_MAX):
        entries.append((title, _norm(' '.join(body))))
    return entries

def _read_splash_entry(analyzer, anchor: int, slug: str) -> tuple[str, str]:
    want = _SLUG_BODY_HASH.get(slug, '')
    entries = _parse_entries(_read_block_text(analyzer, anchor, _BLOCK_OFFSET, _BLOCK_READ_LEN))
    for title, body in entries:
        if _body_hash(body) == want:
            return (title, body)
    index = _SLUG_ENTRY_INDEX.get(slug)
    if index is not None and len(entries) == _ENTRY_MAX:
        return entries[index]
    for title, body in _parse_entries(_read_block_text(analyzer, anchor, _WIDE_OFFSET, _WIDE_READ_LEN)):
        if _body_hash(body) == want:
            return (title, body)
    return ('', '')

def _read_splash_body(analyzer, anchor: int, slug: str) -> str:
    return _read_splash_entry(analyzer, anchor, slug)[1]

def _lookup_translation(slug: str) -> str:
    try:
        import i18n_helper as i18n
        return i18n.text_opt(f'dungeon_splash.{slug}.0') or ''
    except Exception:
        return ''

def _lookup_name(slug: str) -> str:
    try:
        import i18n_helper as i18n
        return i18n.text_opt(f'glossary.{slug}.0') or ''
    except Exception:
        return ''

def classify_dungeon_splash_view(w, *, screen_img: str | None, facility_active_now: bool):
    if facility_active_now:
        return None
    slug = classify_dungeon_splash(screen_img)
    if slug is None:
        return None
    body_tr = _lookup_translation(slug)
    if not body_tr:
        return None
    title_en, body_en = _read_splash_entry(w._analyzer, w._anchor, slug)
    if not body_en:
        return None
    name_tr = _lookup_name(slug)
    if title_en and name_tr:
        return (slug, f'{title_en}\n{body_en}', f'{name_tr}\n{body_tr}')
    return (slug, body_en, body_tr)

def _render_dungeon_splash_view(w, view) -> None:
    slug, en, tr = view
    keep = (en, tr)
    if getattr(w, '_dungeon_splash_keep_key', None) == keep:
        return
    w._dungeon_splash_keep_key = keep
    w._ui_router.update_translation(NPC_MESSAGE_OWNER, en, tr, speech_role='situation')
    _log.info('npc_message displayed (route=dungeon_splash slug=%s)', slug)

def _clear_dungeon_splash_residue(w) -> None:
    keep = getattr(w, '_dungeon_splash_keep_key', None)
    if not keep:
        return
    w._dungeon_splash_keep_key = None
    en, tr = keep
    try:
        if not w._ui_router.is_displaying(NPC_MESSAGE_OWNER, en, tr):
            return
        w._ui_router.clear_if_owner(NPC_MESSAGE_OWNER, mode='translate')
    except (AttributeError, RuntimeError):
        pass

def poll_dungeon_splash_lifecycle(w, *, screen_img: str | None, facility_active_now: bool) -> bool:
    view = classify_dungeon_splash_view(w, screen_img=screen_img, facility_active_now=facility_active_now)
    if view is None:
        _clear_dungeon_splash_residue(w)
        return False
    _render_dungeon_splash_view(w, view)
    return True
__all__ = ['SPLASH_IMG_TO_SLUG', 'classify_dungeon_splash', 'classify_dungeon_splash_view', 'poll_dungeon_splash_lifecycle']
