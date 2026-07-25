from __future__ import annotations
import re
import i18n_helper as i18n
_ITEM_NAME_DICT: dict[str, str] | None = None
_MATERIALS: list[tuple[str, str]] | None = None
_ENCHANT_RE = re.compile('^(.+?) (of .+)$')

def invalidate_caches() -> None:
    global _ITEM_NAME_DICT, _MATERIALS
    _ITEM_NAME_DICT = None
    _MATERIALS = None

def _item_name_dict() -> dict[str, str]:
    global _ITEM_NAME_DICT
    if _ITEM_NAME_DICT is None:
        out: dict[str, str] = {}
        for _id, e in i18n.originals('items').items():
            if not isinstance(e, dict):
                continue
            en = e.get('original', '')
            if not en:
                continue
            ja = i18n.text(_id)
            if ja and ja != _id:
                out[en] = ja
        for ent in i18n.v2_category_entries('items'):
            en, ja = (ent.get('original'), ent.get('text'))
            if en and ja:
                out.setdefault(en, ja)
        _ITEM_NAME_DICT = out
    return _ITEM_NAME_DICT

def _section_pairs(section_name: str) -> list[tuple[str, str]]:
    out: dict[str, str] = {}
    for ent in i18n.v2_category_entries('items'):
        if (ent.get('context') or {}).get('section') != section_name:
            continue
        en, ja = (ent.get('original'), ent.get('text'))
        if en and ja:
            out.setdefault(en, ja)
    for _id, e in i18n.originals('items').items():
        parts = _id.split('.')
        if len(parts) < 2 or parts[1] != section_name or (not isinstance(e, dict)):
            continue
        en = e.get('original', '')
        ja = i18n.text(_id)
        if en and ja and (ja != _id):
            out.setdefault(en, ja)
    return sorted(out.items(), key=lambda p: len(p[0]), reverse=True)

def _materials() -> list[tuple[str, str]]:
    global _MATERIALS
    if _MATERIALS is None:
        pairs = _section_pairs('magical_materials')
        seen = {en for en, _ in pairs}
        extra: dict[str, str] = {}
        for ent in i18n.v2_category_entries('item_materials'):
            en, ja = (ent.get('original'), ent.get('text'))
            if en and ja and (en not in seen):
                extra.setdefault(en, ja)
        for _id, e in i18n.originals('item_materials').items():
            if not isinstance(e, dict):
                continue
            en = e.get('original', '')
            if not en or en in seen:
                continue
            ja = i18n.text(_id)
            if ja and ja != _id:
                extra.setdefault(en, ja)
        pairs.extend(extra.items())
        pairs.sort(key=lambda p: len(p[0]), reverse=True)
        _MATERIALS = pairs
    return _MATERIALS

def _plain_name_ja(en: str) -> str | None:
    name_dict = _item_name_dict()
    if en in name_dict:
        return name_dict[en]
    stripped: list[str] = []
    base_en = en
    changed = True
    while changed:
        changed = False
        for mat_en, mat_ja in _materials():
            pfx = f'{mat_en} '
            if base_en.startswith(pfx):
                stripped.append(mat_ja)
                base_en = base_en[len(pfx):]
                changed = True
                break
    if not stripped:
        return None
    base_ja = name_dict.get(base_en)
    if not base_ja:
        return None
    fmt = i18n.text('item.name.material_format')
    out = base_ja
    for mat_ja in reversed(stripped):
        out = fmt.replace('{material}', mat_ja, 1).replace('{base}', out, 1)
    return out

def translate_item_name_opt(en: str) -> str | None:
    key = (en or '').strip()
    if not key:
        return None
    name_dict = _item_name_dict()
    if key in name_dict:
        return name_dict[key]
    m = _ENCHANT_RE.match(key)
    if m:
        ench_tr = i18n.value('item_enchantments', m.group(2))
        if ench_tr:
            base_ja = _plain_name_ja(m.group(1).strip())
            if base_ja:
                return i18n.text('item.name.enchant_format').replace('{enchant}', ench_tr, 1).replace('{base}', base_ja, 1)
    return _plain_name_ja(key)
__all__ = ['translate_item_name_opt', 'invalidate_caches']
