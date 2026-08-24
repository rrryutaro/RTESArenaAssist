from __future__ import annotations
import re
import i18n_helper as i18n
_entries: list[dict] = []
_loaded = False
_MONSTER_NAMES: dict[str, str] | None = None
_MONSTER_PHRASES: dict[str, str] | None = None
_ITEM_NAMES: dict[str, str] | None = None
_ARTIFACT_NAMES: dict[str, str] | None = None

def _iter_monsters():
    originals = i18n.originals('monsters')
    if i18n.v2_public_enabled('monsters') or (not originals and i18n.v2_public_enabled(None)):
        for e in i18n.v2_category_entries('monsters'):
            eng = e.get('original') or ''
            ja = e.get('text')
            if eng and ja:
                yield (eng, ja)
        return
    for _id, e in originals.items():
        eng = e.get('original', '') if isinstance(e, dict) else ''
        ja = i18n.text(_id)
        if eng and ja and (ja != _id):
            yield (eng, ja)

def _monster_names() -> dict[str, str]:
    global _MONSTER_NAMES
    if _MONSTER_NAMES is None:
        result: dict[str, str] = {}
        for eng, ja in _iter_monsters():
            if eng[0].isupper() and (not eng.startswith('You ')):
                result[eng] = ja
        _MONSTER_NAMES = result
    return _MONSTER_NAMES

def lookup_monster_name(name_en: str) -> str | None:
    if not name_en:
        return None
    return _monster_names().get(name_en.strip())

def _monster_phrases() -> dict[str, str]:
    global _MONSTER_PHRASES
    if _MONSTER_PHRASES is None:
        result: dict[str, str] = {}
        for eng, ja in _iter_monsters():
            if eng.startswith('You '):
                result[eng] = ja
        _MONSTER_PHRASES = result
    return _MONSTER_PHRASES

def _item_names() -> dict[str, str]:
    global _ITEM_NAMES
    if _ITEM_NAMES is None:
        by_sec: dict[str, list[tuple[str, dict]]] = {}
        for _id, e in i18n.originals('items').items():
            parts = _id.split('.')
            if len(parts) >= 2 and isinstance(e, dict):
                by_sec.setdefault(parts[1], []).append((_id, e))
        result: dict[str, str] = {}
        _SECS = ('weapons', 'armor_slots', 'shields', 'accessories', 'potions', 'unidentified_potion', 'quest_items', 'lookup_aliases', 'spellcasting_items')
        for sec in _SECS:
            for _id, e in by_sec.get(sec, []):
                en = e.get('original', '')
                if not en:
                    continue
                ja = i18n.text(_id)
                if ja and ja != _id:
                    result[en] = ja
        for ent in i18n.v2_category_entries('items'):
            if (ent.get('context') or {}).get('section') not in _SECS:
                continue
            en, ja = (ent.get('original'), ent.get('text'))
            if en and ja:
                result.setdefault(en, ja)
        _ITEM_NAMES = result
    return _ITEM_NAMES

def _artifact_names() -> dict[str, str]:
    global _ARTIFACT_NAMES
    if _ARTIFACT_NAMES is None:
        result: dict[str, str] = {}
        originals = i18n.originals('glossary')
        if originals:
            for _id, e in originals.items():
                if not _id.startswith('glossary.artifact_'):
                    continue
                eng = e.get('original', '') if isinstance(e, dict) else ''
                tr = i18n.text_opt(_id)
                if eng and tr:
                    result[eng] = tr
        else:
            cur = {e['id']: e.get('text') for e in i18n.v2_category_entries('glossary')}
            for e in i18n.v2_category_entries('glossary', lang='en'):
                dn = e.get('debug_name') or ''
                if not dn.startswith('glossary.artifact_'):
                    continue
                eng = e.get('text')
                tr = cur.get(e['id'])
                if eng and tr:
                    result[eng] = tr
        _ARTIFACT_NAMES = result
    return _ARTIFACT_NAMES

def lookup_spell(name: str) -> str:
    if not name:
        return ''
    surface = name.strip()
    return i18n.value('mages', surface) or _artifact_names().get(surface) or ''

def _rebuild_category(category: str) -> list[dict]:
    rebuilt: list[dict] = []
    for _id, e in i18n.originals(category).items():
        en = e.get('original', '') if isinstance(e, dict) else ''
        if not en:
            continue
        ja = i18n.value(category, en)
        ja_clean = ja if ja and ja != en else ''
        rebuilt.append({'key': {'en': en}, 'translations': {'ja': ja_clean}})
    return rebuilt

def _ensure_loaded() -> None:
    global _entries, _loaded
    if _loaded:
        return
    _entries = _rebuild_category('dungeon_messages') + _rebuild_category('lock_messages')
    _loaded = True

def lookup_item(name: str) -> str:
    if not name:
        return ''
    m = re.match('Bag of (\\d+) gold pieces?', name, re.IGNORECASE)
    if m:
        return i18n.text('item.name.gold_bag').replace('{count}', m.group(1))
    m_lr = re.match('^(.*?)\\s*\\(([LR])\\)$', name)
    if m_lr:
        base_result = lookup_item(m_lr.group(1).strip())
        if base_result:
            side_key = 'item.name.side_left' if m_lr.group(2) == 'L' else 'item.name.side_right'
            return base_result + i18n.text(side_key)
    item_names = _item_names()
    if name in item_names:
        return item_names[name]
    m_ench = re.match('^(.+?) (of .+)$', name)
    if m_ench:
        ench_ja = i18n.value('item_enchantments', m_ench.group(2))
        if ench_ja:
            base_ja = lookup_item(m_ench.group(1).strip())
            if base_ja:
                return i18n.text('item.name.enchant_format').replace('{enchant}', ench_ja).replace('{base}', base_ja)
    for base_en, base_ja in item_names.items():
        if name.endswith(base_en):
            prefix = name[:len(name) - len(base_en)].strip()
            if not prefix:
                return base_ja
            fmt = i18n.text('item.name.material_format')
            out = base_ja
            for p in reversed(prefix.split()):
                mat_tr = i18n.value('item_materials', p) or p
                out = fmt.replace('{material}', mat_tr).replace('{base}', out)
            return out
    return ''

def lookup(text: str) -> str:
    if not text:
        return ''
    if text in _monster_phrases():
        return _monster_phrases()[text]
    m = re.match('^You see (an?) (.+?)\\.', text)
    if m:
        name_en = m.group(2).strip()
        name_ja = _monster_names().get(name_en, name_en)
        return i18n.text('dungeon_msg.you_see_format').replace('{article}', m.group(1)).replace('{name}', name_ja)
    if text.startswith('The ') and text.endswith(' has no gold or usable items.'):
        name_en = text[4:-len(' has no gold or usable items.')]
        name_ja = _monster_names().get(name_en, name_en)
        return i18n.text('dungeon_msg.no_gold_no_items_format').replace('{name}', name_ja)
    if text.startswith('The ') and text.endswith(' has nothing usable.'):
        name_en = text[4:-len(' has nothing usable.')]
        name_ja = _monster_names().get(name_en, name_en)
        return i18n.text('dungeon_msg.nothing_usable_format').replace('{name}', name_ja)
    if text.startswith('The ') and ' has ' in text and (' in their possession' in text):
        after_the = text[4:]
        has_pos = after_the.find(' has ')
        name_en = after_the[:has_pos]
        name_ja = _monster_names().get(name_en, name_en)
        item_part = after_the[has_pos + 5:].rstrip('.')
        item_part = item_part.replace(' in their possession', '').strip()
        return i18n.text('dungeon_msg.possession_format').replace('{name}', name_ja).replace('{item}', item_part)
    m = re.match('^You have found (\\d+) gold pieces?!!', text)
    if m:
        return i18n.text('dungeon_msg.gold_found_format').replace('{count}', m.group(1))
    _ensure_loaded()
    for e in _entries:
        if e.get('key', {}).get('en', '') == text:
            return e.get('translations', {}).get('ja', '')
    best_len = 0
    best_jpn = ''
    for e in _entries:
        eng = e.get('key', {}).get('en', '')
        if eng and text.startswith(eng) and (len(eng) > best_len):
            best_len = len(eng)
            best_jpn = e.get('translations', {}).get('ja', '')
    return best_jpn
