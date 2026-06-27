from __future__ import annotations
import json
import locale
import logging
import os
from typing import Any
logger = logging.getLogger(__name__)
_BASE_DIR: str = ''
_I18N_DIR: str = ''
_lang: str = 'en'
_meta_all: dict[str, dict[str, Any]] = {}
_default_fallback: str = 'en'
_lang_cache: dict[str, dict[str, str]] = {}
_lang_raw_cache: dict[str, dict[str, Any]] = {}
_rules_cache: dict[str, dict[str, Any]] = {}
_original_merged: dict[str, str] = {}
_originals_by_cat: dict[str, dict[str, Any]] = {}
_value_index: dict[str, dict[str, str]] = {}
try:
    from PySide6.QtCore import QObject, Signal

    class _I18nSignals(QObject):
        language_changed = Signal(str)
    signals = _I18nSignals()
except ImportError:
    signals = None
_V2_COMPAT = None
_V2_PUBLIC = None
_V2_SOURCE_ID_MAP = None
_V2_RUNTIME_ENABLED = False
_V2_CATEGORIES_ENABLED: set = set()
_V2_VALUE_INDEX: dict = {}
_V2_SURFACE_WARNINGS: dict = {}
_V2_SLOT_INDEX: dict = {}
_V2_SECTION_INDEX: dict = {}
_V2_DEGRADED_ACCEPTED: dict = {}
_V2_LOCALE_TAG = {'ja': 'ja-JP', 'en': 'en-US', 'es': 'es-ES'}
_PHASE5_VALUE_SAFE = frozenset({'calendar', 'chargen_race_descriptions', 'classes', 'equipment_suffixes', 'item_enchantments', 'location_types', 'protect_locations', 'races', 'spells', 'titles', 'template_dat_building_entry'})
_PHASE5_ITERATOR_SAFE = frozenset({'npc_dialog', 'npc_name_chunks'})
_PHASE5_DEGRADED_COMPLETE = frozenset({'pronouns', 'npc_traits', 'relations', 'descriptors', 'status_terms'})
_PHASE5_MIXED_COMPLETE = frozenset({'mages', 'item_materials'})
_PHASE5_LIVE_SURFACE_PENDING = frozenset({'ask_about_menu', 'dungeon_messages', 'eras', 'gods', 'placeholder_values', 'pregame_intro', 'status_buffer_text', 'ui'})
PHASE5_ENABLE_SET = _PHASE5_VALUE_SAFE | _PHASE5_ITERATOR_SAFE | _PHASE5_DEGRADED_COMPLETE | _PHASE5_MIXED_COMPLETE
_PHASE5_PARTIAL_OBS_ALLOWLIST = frozenset({'items', 'equipment', 'mages', 'character', 'dungeon', 'monsters', 'item_materials', 'pronouns', 'relations', 'ask_about_menu', 'status_buffer_text', 'descriptors', 'status_terms', 'npc_traits'})

def _v2_locale_tag(lang: str) -> str:
    return _V2_LOCALE_TAG.get((lang or '').lower(), lang)

def enable_v2(*, bundle_path: str, legacy_map_path: str, localpack_path: str | None=None, mods_dir: str | None=None) -> None:
    global _V2_COMPAT
    import i18n_compat
    _V2_COMPAT = i18n_compat.V2Compat.load(bundle_path=bundle_path, legacy_map_path=legacy_map_path, localpack_path=localpack_path, mods_dir=mods_dir)

def disable_v2() -> None:
    global _V2_COMPAT
    _V2_COMPAT = None

def v2_enabled() -> bool:
    return _V2_COMPAT is not None

def enable_v2_public(*, bundle_path: str, source_id_map_path: str, localpack_path: str | None=None, mods_dir: str | None=None, categories=None) -> None:
    global _V2_PUBLIC, _V2_SOURCE_ID_MAP, _V2_RUNTIME_ENABLED, _V2_CATEGORIES_ENABLED
    global _V2_VALUE_INDEX, _V2_SURFACE_WARNINGS, _V2_SLOT_INDEX, _V2_SECTION_INDEX
    global _V2_DEGRADED_ACCEPTED
    import json
    import i18n_v2
    _V2_PUBLIC = i18n_v2.I18nV2.load(bundle_path=bundle_path, localpack_path=localpack_path, mods_dir=mods_dir)
    with open(source_id_map_path, encoding='utf-8') as fh:
        _V2_SOURCE_ID_MAP = json.load(fh).get('map', {})
    _V2_DEGRADED_ACCEPTED = _load_degraded_accepted(bundle_path)
    _V2_RUNTIME_ENABLED = True
    _V2_CATEGORIES_ENABLED = set(categories) if categories is not None else None
    _V2_VALUE_INDEX = {}
    _V2_SURFACE_WARNINGS = {}
    _V2_SLOT_INDEX = {}
    _V2_SECTION_INDEX = {}

def disable_v2_public() -> None:
    global _V2_PUBLIC, _V2_SOURCE_ID_MAP, _V2_RUNTIME_ENABLED, _V2_CATEGORIES_ENABLED
    global _V2_VALUE_INDEX, _V2_SURFACE_WARNINGS, _V2_SLOT_INDEX, _V2_SECTION_INDEX
    global _V2_DEGRADED_ACCEPTED
    _V2_PUBLIC = None
    _V2_SOURCE_ID_MAP = None
    _V2_RUNTIME_ENABLED = False
    _V2_CATEGORIES_ENABLED = set()
    _V2_VALUE_INDEX = {}
    _V2_SURFACE_WARNINGS = {}
    _V2_SLOT_INDEX = {}
    _V2_SECTION_INDEX = {}
    _V2_DEGRADED_ACCEPTED = {}

def _load_degraded_accepted(bundle_path: str) -> dict:
    import json
    path = os.path.join(os.path.dirname(bundle_path), 'degraded_accepted.json')
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
        out: dict = {}
        for cat, spec in (data.get('accepted') or {}).items():
            ids = (spec or {}).get('ids') or []
            out[cat] = {int(i) for i in ids}
        return out
    except Exception:
        logger.warning('i18n: degraded_accepted.json 読込失敗（除外なしで継続）', exc_info=True)
        return {}

def enable_v2_public_if_available(*, bundle_path: str, source_id_map_path: str, localpack_path: str | None, enabled: bool, categories=None, user_dir: str | None=None) -> bool:
    if not enabled or not localpack_path or (not os.path.exists(localpack_path)):
        return False
    try:
        enable_v2_public(bundle_path=bundle_path, source_id_map_path=source_id_map_path, localpack_path=localpack_path, categories=categories)
        if user_dir:
            merge_user_observations(user_dir)
        return True
    except Exception:
        logger.warning('i18n: 公開 v2 runtime 有効化失敗（v1 継続）', exc_info=True)
        return False

def v2_public_enabled(category: str | None=None) -> bool:
    if not _V2_RUNTIME_ENABLED or _V2_PUBLIC is None:
        return False
    if category is None or _V2_CATEGORIES_ENABLED is None:
        return True
    return category in _V2_CATEGORIES_ENABLED

def v2_generated_asset(name: str) -> bytes | None:
    if _V2_PUBLIC is None or getattr(_V2_PUBLIC, 'localpack', None) is None:
        return None
    return _V2_PUBLIC.localpack.generated_asset(name)

def _v2_ids_for_source_id(source_id: str) -> list:
    v = (_V2_SOURCE_ID_MAP or {}).get(source_id)
    if v is None:
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]

def _v2_pick_id(source_id: str, category: str | None):
    ids = _v2_ids_for_source_id(source_id)
    if not ids:
        return None
    if len(ids) > 1 and category is not None and (_V2_PUBLIC is not None):
        for i in ids:
            c = _V2_PUBLIC.category_of(int(i))
            if c and c.get('category') == category:
                return int(i)
    return int(ids[0])

def text_by_source_id(source_id: str, *, category: str | None=None, lang: str | None=None) -> str | None:
    if _V2_PUBLIC is None:
        return None
    nid = _v2_pick_id(source_id, category)
    if nid is None:
        return None
    return _V2_PUBLIC.resolve_text(nid, _v2_locale_tag(lang or _lang))

def original_by_source_id(source_id: str, *, category: str | None=None) -> str | None:
    if _V2_PUBLIC is None:
        return None
    nid = _v2_pick_id(source_id, category)
    if nid is None:
        return None
    return _V2_PUBLIC.resolve_original_surface(nid)

def v2_category_entries(category: str, *, lang: str | None=None) -> list:
    if _V2_PUBLIC is None:
        return []
    meta = _V2_PUBLIC.bundle.categories.get(category)
    if not meta:
        return []
    loc = _v2_locale_tag(lang or _lang)
    out = []
    for e in meta.get('entries', []):
        if e.get('retired'):
            continue
        eid = int(e['id'])
        out.append({'id': eid, 'source_id': (e.get('source') or {}).get('source_id'), 'kind': e.get('kind'), 'original': _V2_PUBLIC.resolve_original_surface(eid), 'text': _V2_PUBLIC.resolve_text(eid, loc), 'rich': _V2_PUBLIC.rich_meta(eid), 'context': e.get('context') or {}})
    return out

def v2_bundle_categories() -> list:
    if _V2_PUBLIC is None:
        return []
    try:
        return sorted(_V2_PUBLIC.bundle.categories.keys())
    except Exception:
        return []

def _v2_value_index(category: str) -> dict:
    idx = _V2_VALUE_INDEX.get(category)
    if idx is None:
        idx = {}
        dup_warn: list[str] = []
        if _V2_PUBLIC is not None:
            meta = _V2_PUBLIC.bundle.categories.get(category)
            if meta:
                loc = _v2_locale_tag(_lang)
                for e in meta.get('entries', []):
                    if e.get('retired'):
                        continue
                    eid = int(e['id'])
                    o = _V2_PUBLIC.resolve_original_surface(eid)
                    if not isinstance(o, str):
                        o = _V2_PUBLIC.resolve_live_surface(eid)
                    if not isinstance(o, str):
                        continue
                    prev = idx.get(o)
                    if prev is None:
                        idx[o] = eid
                    elif prev != eid:
                        t_prev = _V2_PUBLIC.resolve_text(prev, loc)
                        t_cur = _V2_PUBLIC.resolve_text(eid, loc)
                        if t_prev != t_cur and o not in dup_warn:
                            dup_warn.append(o)
        _V2_VALUE_INDEX[category] = idx
        _V2_SURFACE_WARNINGS[category] = dup_warn
        if dup_warn:
            logger.warning('i18n v2: category %r has %d surface(s) with conflicting translations (value_by_surface first-win unsafe): %s', category, len(dup_warn), dup_warn[:5])
    return idx

def v2_surface_conflicts(category: str) -> list:
    _v2_value_index(category)
    return list(_V2_SURFACE_WARNINGS.get(category, []))

def _v2_section_index(category: str) -> dict:
    idx = _V2_SECTION_INDEX.get(category)
    if idx is None:
        idx = {}
        if _V2_PUBLIC is not None:
            meta = _V2_PUBLIC.bundle.categories.get(category)
            if meta:
                for e in meta.get('entries', []):
                    if e.get('retired'):
                        continue
                    section = (e.get('context') or {}).get('section')
                    if section is None:
                        continue
                    eid = int(e['id'])
                    o = _V2_PUBLIC.resolve_original_surface(eid)
                    if not isinstance(o, str):
                        o = _V2_PUBLIC.resolve_live_surface(eid)
                    if isinstance(o, str):
                        idx.setdefault((section, o), eid)
        _V2_SECTION_INDEX[category] = idx
    return idx

def value_by_surface(category: str, original_text: str, *, section: str | None=None, lang: str | None=None) -> str | None:
    if _V2_PUBLIC is None or not original_text:
        return None
    if section is not None:
        nid = _v2_section_index(category).get((section, original_text))
        if nid is None:
            return None
        return _V2_PUBLIC.resolve_text(nid, _v2_locale_tag(lang or _lang))
    nid = _v2_value_index(category).get(original_text)
    if nid is None:
        return None
    if original_text in _V2_SURFACE_WARNINGS.get(category, ()):
        return None
    return _V2_PUBLIC.resolve_text(nid, _v2_locale_tag(lang or _lang))

def value_section(category: str, original_text: str, section: str) -> str | None:
    if not original_text:
        return None
    if v2_public_enabled(category):
        return value_by_surface(category, original_text, section=section)
    return value(category, original_text)

def _v2_slot_index(category: str) -> dict:
    idx = _V2_SLOT_INDEX.get(category)
    if idx is None:
        idx = {}
        if _V2_PUBLIC is not None:
            meta = _V2_PUBLIC.bundle.categories.get(category)
            if meta:
                for e in meta.get('entries', []):
                    if e.get('retired'):
                        continue
                    slot = (e.get('context') or {}).get('slot')
                    if slot is not None and slot not in idx:
                        idx[int(slot)] = int(e['id'])
        _V2_SLOT_INDEX[category] = idx
    return idx

def value_by_slot(category: str, slot: int, *, lang: str | None=None) -> str | None:
    if _V2_PUBLIC is None or slot is None:
        return None
    nid = _v2_slot_index(category).get(int(slot))
    if nid is None:
        return None
    return _V2_PUBLIC.resolve_text(nid, _v2_locale_tag(lang or _lang))

def v2_category_mixed_complete(category: str) -> bool:
    if _V2_PUBLIC is None:
        return False
    meta = _V2_PUBLIC.bundle.categories.get(category)
    if not meta:
        return False
    accepted = _V2_DEGRADED_ACCEPTED.get(category, ())
    for e in meta.get('entries', []):
        if e.get('retired'):
            continue
        eid = int(e['id'])
        if eid in accepted:
            continue
        if _V2_PUBLIC.bundle.redirect_of(eid) is not None:
            continue
        if isinstance(_V2_PUBLIC.resolve_original_surface(eid), str):
            continue
        if isinstance(_V2_PUBLIC.resolve_live_surface(eid), str):
            continue
        return False
    return True

def _v2_clear_surface_caches() -> None:
    global _V2_VALUE_INDEX, _V2_SECTION_INDEX, _V2_SURFACE_WARNINGS
    _V2_VALUE_INDEX = {}
    _V2_SECTION_INDEX = {}
    _V2_SURFACE_WARNINGS = {}

def register_observation(category: str, id: int, surface: str, *, user_dir: str) -> bool:
    if _V2_PUBLIC is None or not surface or category not in _PHASE5_PARTIAL_OBS_ALLOWLIST:
        return False
    meta = _V2_PUBLIC.bundle.categories.get(category)
    if not meta:
        return False
    ent = None
    for e in meta.get('entries', []):
        if int(e['id']) == int(id):
            ent = e
            break
    if ent is None or ent.get('retired'):
        return False
    if (ent.get('source') or {}).get('source_id'):
        return False
    import arena_local_data as _ald
    if not _ald.append_user_observation(user_dir, int(id), surface):
        return False
    if _V2_PUBLIC.localpack is not None:
        _V2_PUBLIC.localpack.live_surface_obs[int(id)] = surface
        _v2_clear_surface_caches()
    return True

def merge_user_observations(user_dir: str) -> int:
    if _V2_PUBLIC is None or _V2_PUBLIC.localpack is None:
        return 0
    import arena_local_data as _ald
    obs = _ald.load_user_observations(user_dir)
    if obs:
        _V2_PUBLIC.localpack.live_surface_obs.update(obs)
        _v2_clear_surface_caches()
    return len(obs)

def init(base_dir: str, lang: str | None=None) -> None:
    global _BASE_DIR, _I18N_DIR, _lang_cache, _lang_raw_cache, _rules_cache
    global _originals_by_cat, _value_index
    _BASE_DIR = base_dir
    _I18N_DIR = os.path.join(base_dir, 'i18n')
    _lang_cache = {}
    _lang_raw_cache = {}
    _rules_cache = {}
    _originals_by_cat = {}
    _value_index = {}
    _load_meta()
    _load_originals()
    resolved = _resolve_initial_lang(lang)
    _set_active(resolved)

def _i18n_read_text(*parts: str) -> 'str | None':
    try:
        with open(os.path.join(_I18N_DIR, *parts), encoding='utf-8') as f:
            return f.read()
    except OSError:
        pass
    try:
        import app_resources
        return app_resources.read_text('/'.join(('i18n',) + parts))
    except Exception:
        return None

def _i18n_listdir(*parts: str) -> list[str]:
    d = os.path.join(_I18N_DIR, *parts) if parts else _I18N_DIR
    if os.path.isdir(d):
        return sorted(os.listdir(d))
    try:
        import app_resources
        return app_resources.listdir('/'.join(('i18n',) + parts))
    except Exception:
        return []

def _i18n_isdir(*parts: str) -> bool:
    if os.path.isdir(os.path.join(_I18N_DIR, *parts) if parts else _I18N_DIR):
        return True
    try:
        import app_resources
        return app_resources.is_dir('/'.join(('i18n',) + parts))
    except Exception:
        return False

def _load_meta() -> None:
    global _meta_all, _default_fallback
    _meta_all = {}
    _default_fallback = 'en'
    txt = _i18n_read_text('_meta.json')
    if txt is None:
        logger.warning('i18n: failed to load _meta.json')
        return
    try:
        data = json.loads(txt)
        _meta_all = data.get('languages', {}) or {}
        _default_fallback = data.get('_default_fallback', 'en') or 'en'
    except json.JSONDecodeError as e:
        logger.warning('i18n: failed to parse _meta.json: %s', e)

def _ingest_original_category(category: str, cat: object) -> None:
    if not isinstance(cat, dict):
        return
    _originals_by_cat[category] = cat
    for k, v in cat.items():
        if isinstance(v, dict):
            o = v.get('original')
            if isinstance(o, str):
                _original_merged[k] = o

def _load_originals() -> None:
    global _original_merged, _originals_by_cat
    _original_merged = {}
    _originals_by_cat = {}
    _load_originals_from_disk()

def _load_originals_from_disk() -> None:
    odir = os.path.join(_I18N_DIR, '_original')
    if not os.path.isdir(odir):
        return
    for fname in sorted(os.listdir(odir)):
        if not fname.endswith('.json') or fname.startswith('_'):
            continue
        category = fname[:-5]
        try:
            with open(os.path.join(odir, fname), encoding='utf-8') as f:
                cat = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        _ingest_original_category(category, cat)

def available_languages() -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for name in _i18n_listdir():
        if name.startswith('_') or not _i18n_isdir(name):
            continue
        meta = _meta_all.get(name, {})
        results.append({'code': name, 'display_name': meta.get('display_name', name), 'direction': meta.get('direction', 'ltr')})
    return results

def _available_codes() -> set[str]:
    return {entry['code'] for entry in available_languages()}

def _resolve_initial_lang(lang: str | None) -> str:
    avail = _available_codes()
    if not avail:
        return _default_fallback
    if lang:
        match = _match_tag(lang, avail)
        if match:
            return match
    else:
        try:
            sys_lang = locale.getdefaultlocale()[0]
        except (ValueError, TypeError):
            sys_lang = None
        if sys_lang:
            match = _match_tag(sys_lang, avail)
            if match:
                return match
    if _default_fallback in avail:
        return _default_fallback
    if 'en' in avail:
        return 'en'
    for code in _meta_all:
        if code in avail:
            return code
    return sorted(avail)[0]

def _match_tag(tag: str, avail: set[str]) -> str | None:
    if not tag:
        return None
    tag = tag.replace('_', '-')
    lower_map = {c.lower(): c for c in avail}
    parts = tag.split('-')
    for i in range(len(parts), 0, -1):
        cand = '-'.join(parts[:i]).lower()
        if cand in lower_map:
            return lower_map[cand]
    base = parts[0].lower()
    if base in lower_map:
        return lower_map[base]
    for c in avail:
        if c.lower().split('-')[0] == base:
            return c
    return None

def _fallback_chain(lang: str) -> list[str]:
    meta = _meta_all.get(lang, {})
    chain = list(meta.get('fallback_chain', []) or [])
    if lang not in chain:
        chain.insert(0, lang)
    if _default_fallback and _default_fallback not in chain:
        chain.append(_default_fallback)
    return chain

def _load_lang_merged(lang: str) -> dict[str, str]:
    if lang in _lang_cache:
        return _lang_cache[lang]
    merged: dict[str, str] = {}
    for fname in _i18n_listdir(lang):
        if not fname.endswith('.json') or fname.startswith('_'):
            continue
        txt = _i18n_read_text(lang, fname)
        if txt is None:
            continue
        try:
            cat = json.loads(txt)
        except json.JSONDecodeError:
            continue
        if not isinstance(cat, dict):
            continue
        for k, v in cat.items():
            if isinstance(v, str):
                s = v
            elif isinstance(v, dict):
                s = v.get('value', '')
            else:
                continue
            if s != '':
                merged[k] = s
    _lang_cache[lang] = merged
    return merged

def text_opt(id: str) -> str | None:
    if _V2_COMPAT is not None:
        v = _V2_COMPAT.text_opt(id, _lang)
        if v is not None:
            return v
    for lang in _fallback_chain(_lang):
        m = _load_lang_merged(lang)
        v = m.get(id)
        if v:
            return v
    o = _original_merged.get(id)
    if o:
        return o
    return None

def text(id: str) -> str:
    v = text_opt(id)
    if v is not None:
        return v
    logger.debug("i18n: missing id '%s' (lang=%s)", id, _lang)
    return id

def lang_only(id: str) -> str | None:
    return _load_lang_merged(_lang).get(id)

def _load_lang_raw(lang: str) -> dict[str, Any]:
    if lang in _lang_raw_cache:
        return _lang_raw_cache[lang]
    raw: dict[str, Any] = {}
    for fname in _i18n_listdir(lang):
        if not fname.endswith('.json') or fname.startswith('_'):
            continue
        txt = _i18n_read_text(lang, fname)
        if txt is None:
            continue
        try:
            cat = json.loads(txt)
        except json.JSONDecodeError:
            continue
        if isinstance(cat, dict):
            raw.update(cat)
    _lang_raw_cache[lang] = raw
    return raw

def lang_value_in(id: str, lang: str, form: str='value') -> str | None:
    rawval = _load_lang_raw(lang).get(id)
    if isinstance(rawval, dict):
        v = rawval.get(form)
        return v if v else None
    if isinstance(rawval, str):
        return rawval if form == 'value' and rawval else None
    return None

def rules(lang: str | None=None) -> dict[str, Any]:
    target = lang or _lang
    if target in _rules_cache:
        return _rules_cache[target]
    data: dict[str, Any] = {}
    txt = _i18n_read_text(target, '_rules.json')
    if txt is not None:
        try:
            loaded = json.loads(txt)
            if isinstance(loaded, dict):
                data = loaded
        except json.JSONDecodeError:
            data = {}
    _rules_cache[target] = data
    return data

def original(id: str) -> str | None:
    if _V2_COMPAT is not None:
        v = _V2_COMPAT.original(id)
        if v is not None:
            return v
    return _original_merged.get(id)

def originals(category: str) -> dict[str, Any]:
    return _originals_by_cat.get(category, {})

def original_categories() -> list[str]:
    return sorted(_originals_by_cat.keys())

def lang_ids(category: str) -> list[str]:
    prefix = f'{category}.'
    out: set[str] = set()
    for lang in _fallback_chain(_lang):
        for k in _load_lang_merged(lang):
            if k.startswith(prefix):
                out.add(k)
    return sorted(out)

def value(category: str, original_text: str) -> str | None:
    if not original_text:
        return None
    if v2_public_enabled(category):
        return value_by_surface(category, original_text)
    idx = _value_index.get(category)
    if idx is None:
        idx = {}
        for k, e in _originals_by_cat.get(category, {}).items():
            if isinstance(e, dict):
                o = e.get('original')
                if isinstance(o, str) and o not in idx:
                    idx[o] = k
        _value_index[category] = idx
    id_ = idx.get(original_text)
    if id_ is None:
        return None
    return text_opt(id_)

def value_in(category: str, original_text: str, lang: str) -> str | None:
    if not original_text:
        return None
    if v2_public_enabled(category):
        return value_by_surface(category, original_text, lang=lang)
    idx = _value_index.get(category)
    if idx is None:
        idx = {}
        for k, e in _originals_by_cat.get(category, {}).items():
            if isinstance(e, dict):
                o = e.get('original')
                if isinstance(o, str) and o not in idx:
                    idx[o] = k
        _value_index[category] = idx
    id_ = idx.get(original_text)
    if id_ is None:
        return None
    return lang_value_in(id_, lang)

def glossary(term_id: str) -> str | None:
    return text_opt(term_id)

def tr(key: str, **kwargs: Any) -> str:
    s = text(key)
    if kwargs:
        try:
            s = s.format(**kwargs)
        except (KeyError, ValueError, IndexError):
            pass
    return s

def tr_n(key: str, n: int, **kwargs: Any) -> str:
    plural_form = current_meta().get('plural_form', 'no_plural')
    s: str | None = None
    if _needs_plural(plural_form, n):
        s = text_opt(f'{key}_plural')
    if s is None:
        s = text(key)
    try:
        s = s.format(n=n, **kwargs)
    except (KeyError, ValueError, IndexError):
        pass
    return s

def _set_active(lang: str) -> None:
    global _lang, _V2_SURFACE_WARNINGS
    _lang = lang
    _load_lang_merged(lang)
    _V2_SURFACE_WARNINGS = {}
    _apply_qt_settings()

def set_language(lang: str) -> bool:
    match = _match_tag(lang, _available_codes())
    if not match:
        return False
    _set_active(match)
    if signals is not None:
        signals.language_changed.emit(_lang)
    return True

def current_lang() -> str:
    return _lang

def current_meta() -> dict[str, Any]:
    return dict(_meta_all.get(_lang, {}))

def direction() -> str:
    return current_meta().get('direction', 'ltr')

def font_hint() -> str | None:
    return current_meta().get('font_hint') or None

def _needs_plural(plural_form: str, n: int) -> bool:
    if plural_form == 'no_plural':
        return False
    if plural_form == 'en_like_2':
        return n != 1
    if plural_form not in ('no_plural', 'en_like_2'):
        logger.warning("i18n: plural_form '%s' not fully implemented, using en_like_2", plural_form)
        return n != 1
    return False

def _apply_qt_settings() -> None:
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QFont
        app = QApplication.instance()
        if app is None:
            return
        if direction() == 'rtl':
            app.setLayoutDirection(Qt.RightToLeft)
        else:
            app.setLayoutDirection(Qt.LeftToRight)
        hint = font_hint()
        if hint:
            families = [f.strip() for f in hint.split(',')]
            if families:
                font = QFont(app.font())
                font.setFamilies(families)
                app.setFont(font)
    except Exception:
        pass
