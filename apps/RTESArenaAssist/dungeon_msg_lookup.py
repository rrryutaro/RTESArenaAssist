from __future__ import annotations
import re
import logging
import i18n_helper as i18n
_log = logging.getLogger(__name__)
_table_state: dict[str, bool] = {}
_entries: list[dict] = []
_loaded = False
_MONSTER_NAMES: dict[str, str] | None = None
_MONSTER_PHRASES: dict[str, str] | None = None
_ITEM_NAMES: dict[str, str] | None = None

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

def _enemy_name(name_en: str) -> str:
    name_en = name_en.strip()
    names = _monster_names()
    monster = names.get(name_en)
    if monster:
        return monster
    folded = [tr for en, tr in names.items() if en.casefold() == name_en.casefold()]
    if len(set(folded)) == 1:
        return folded[0]
    return name_en

def lookup_enemy_name(name_en: str) -> str | None:
    if not name_en or not name_en.strip():
        return None
    translated = _enemy_name(name_en)
    return translated if translated != name_en.strip() else None

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

def lookup_spell(name: str) -> str:
    if not name:
        return ''
    surface = name.strip()
    from item_name_lookup import translate_artifact_name_opt
    return i18n.value('mages', surface) or translate_artifact_name_opt(surface) or ''

def _rebuild_category(category: str) -> list[dict]:
    originals = i18n.originals(category)
    if i18n.v2_public_enabled(category) or (not originals and i18n.v2_public_enabled(None)):
        rebuilt: list[dict] = []
        for e in i18n.v2_category_entries(category):
            en = e.get('original') or ''
            if not en:
                continue
            tr = e.get('text') or ''
            rebuilt.append({'key': {'en': en}, 'translations': {'ja': tr if tr != en else ''}})
        return rebuilt
    rebuilt = []
    for _id, e in originals.items():
        en = e.get('original', '') if isinstance(e, dict) else ''
        if not en:
            continue
        ja = i18n.value(category, en)
        ja_clean = ja if ja and ja != en else ''
        rebuilt.append({'key': {'en': en}, 'translations': {'ja': ja_clean}})
    return rebuilt

def _note_table_size(name: str, n: int) -> None:
    ok = n > 0
    if _table_state.get(name) == ok:
        return
    _table_state[name] = ok
    if ok:
        _log.warning('ダンジョンのメッセージ表 %s: %d 件で作られた', name, n)
    else:
        _log.warning('ダンジョンのメッセージ表 %s: **空のまま作られた**。このカテゴリの原文が読めていないため、該当メッセージは翻訳されない', name)

def _ensure_loaded() -> None:
    global _entries, _loaded
    if _loaded:
        return
    _dungeon = [dict(e, exact_only=True) for e in _rebuild_category('dungeon_messages')]
    _lock = _rebuild_category('lock_messages')
    _note_table_size('lock_messages', len(_lock))
    _entries = _dungeon + _lock
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
    from item_name_lookup import translate_artifact_name_opt
    artifact = translate_artifact_name_opt(name)
    if artifact:
        return artifact
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
            return _compose_material_name(prefix, base_ja)
    folded_names = _item_names_casefold()
    folded = folded_names.get(name.casefold())
    if folded:
        return folded
    folded_name = name.casefold()
    best = None
    for base_key, base_ja in folded_names.items():
        if folded_name.endswith(' ' + base_key) and (best is None or len(base_key) > len(best[0])):
            best = (base_key, base_ja)
    if best is not None:
        prefix = name[:len(name) - len(best[0])].strip()
        return _compose_material_name(prefix, best[1])
    return ''

def _compose_material_name(prefix: str, base_tr: str) -> str:
    if not prefix:
        return base_tr
    fmt = i18n.text('item.name.material_format')
    out = base_tr
    for p in reversed(prefix.split()):
        mat_tr = i18n.value('item_materials', p) or p
        out = fmt.replace('{material}', mat_tr).replace('{base}', out)
    return out
_ITEM_NAMES_CASEFOLD: tuple | None = None

def _item_names_casefold() -> dict[str, str]:
    global _ITEM_NAMES_CASEFOLD
    names = _item_names()
    if _ITEM_NAMES_CASEFOLD is None or _ITEM_NAMES_CASEFOLD[0] is not names:
        folded: dict[str, str] = {}
        ambiguous: set[str] = set()
        for en, tr in names.items():
            key = en.casefold()
            if key in folded and folded[key] != tr:
                ambiguous.add(key)
            folded.setdefault(key, tr)
        for key in ambiguous:
            folded.pop(key, None)
        _ITEM_NAMES_CASEFOLD = (names, folded)
    return _ITEM_NAMES_CASEFOLD[1]

def lookup(text: str) -> str:
    if not text:
        return ''
    if text in _monster_phrases():
        return _monster_phrases()[text]
    m = re.match('^You see (an?) (.+?)\\.', text)
    if m:
        name_en = m.group(2).strip()
        name_ja = _enemy_name(name_en)
        return i18n.text('dungeon_msg.you_see_format').replace('{article}', m.group(1)).replace('{name}', name_ja)
    if text.startswith('The ') and text.endswith(' has no gold or usable items.'):
        name_en = text[4:-len(' has no gold or usable items.')]
        name_ja = _enemy_name(name_en)
        return i18n.text('dungeon_msg.no_gold_no_items_format').replace('{name}', name_ja)
    if text.startswith('The ') and text.endswith(' has nothing usable.'):
        name_en = text[4:-len(' has nothing usable.')]
        name_ja = _enemy_name(name_en)
        return i18n.text('dungeon_msg.nothing_usable_format').replace('{name}', name_ja)
    if text.startswith('The ') and ' has ' in text and (' in their possession' in text):
        after_the = text[4:]
        has_pos = after_the.find(' has ')
        name_en = after_the[:has_pos]
        name_ja = _enemy_name(name_en)
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
        if e.get('exact_only'):
            continue
        eng = e.get('key', {}).get('en', '')
        if eng and text.startswith(eng) and (len(eng) > best_len):
            best_len = len(eng)
            best_jpn = e.get('translations', {}).get('ja', '')
    return best_jpn
