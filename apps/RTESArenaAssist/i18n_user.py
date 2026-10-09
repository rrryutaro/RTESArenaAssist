from __future__ import annotations
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from typing import Callable
SCHEMA = 'rtesaa.user_translation'
SCHEMA_VERSION = 1
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_TEXT_LEN = 20000
MAX_META_LEN = 200
TOKEN = re.compile('%%|%[A-Za-z0-9]+|\\{[^{}]*\\}')
_LANG_RE = re.compile('^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$')
_RESERVED_NAMES = frozenset(('con', 'prn', 'aux', 'nul'))
_CAT_RE = re.compile('^[A-Za-z0-9][A-Za-z0-9_]*$')
_CTRL_RE = re.compile('[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f\\x7f]')
CategoryLoader = Callable[[str, str], 'dict[str, str] | None']

@dataclass
class UserPacks:
    overlay: dict[str, dict[str, str]] = field(default_factory=dict)
    categories: dict[str, dict[str, str]] = field(default_factory=dict)
    langs: dict[str, dict] = field(default_factory=dict)
    files: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def entry_count(self) -> int:
        return sum((len(v) for v in self.overlay.values()))

def normalize_lang(code: object) -> str | None:
    if not isinstance(code, str):
        return None
    code = code.strip().replace('_', '-')
    if not code or code.startswith('-') or (not _LANG_RE.match(code)):
        return None
    if code.split('-')[0].lower() in _RESERVED_NAMES:
        return None
    parts = code.split('-')
    out = [parts[0].lower()]
    for p in parts[1:]:
        if len(p) == 4 and p.isalpha():
            out.append(p.title())
        elif len(p) == 2 and p.isalpha() or (len(p) == 3 and p.isdigit()):
            out.append(p.upper())
        else:
            out.append(p.lower())
    return '-'.join(out)
RTL_LANGUAGES = frozenset(('ar', 'arc', 'ckb', 'dv', 'fa', 'he', 'ks', 'nqo', 'ps', 'sd', 'syr', 'ug', 'ur', 'yi'))
PLURAL_FORMS = ('no_plural', 'en_like_2')

def default_direction(lang: str) -> str:
    return 'rtl' if lang.split('-')[0].lower() in RTL_LANGUAGES else 'ltr'

def _short(value: object, limit: int, default: str) -> str:
    return value if isinstance(value, str) and 0 < len(value) <= limit else default

def build_meta(lang: str, raw_meta: object, *, bundled: dict[str, str], warnings: list[str]) -> dict | None:
    m = raw_meta if isinstance(raw_meta, dict) else {}
    name = m.get('display_name')
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100 or _CTRL_RE.search(name) or ('\n' in name) or ('\r' in name) or ('<' in name) or ('>' in name):
        return None
    fb = m.get('fallback', 'en')
    fb_code = bundled.get(fb.lower()) if isinstance(fb, str) else None
    if fb_code is None:
        if 'fallback' in m:
            _warn(warnings, 'meta', 'fallback', '同梱言語でないため en にする')
        fb_code = bundled.get('en', 'en')
    direction = m.get('direction')
    if direction not in ('ltr', 'rtl'):
        direction = default_direction(lang)
    plural = m.get('plural_form')
    if plural not in PLURAL_FORMS:
        plural = 'en_like_2'
    locale = m.get('locale')
    locale = locale if isinstance(locale, str) and normalize_lang(locale) else lang
    if resolve_bundled(normalize_lang(locale) or lang, bundled) is not None:
        _warn(warnings, 'meta', 'locale', '同梱言語の locale と重なるため lang を使う')
        locale = lang
    chain = [lang]
    for c in (fb_code, 'en'):
        if c not in chain:
            chain.append(c)
    fonts = m.get('ui_font_families')
    fonts = [f for f in fonts if isinstance(f, str) and 0 < len(f) <= 100][:6] if isinstance(fonts, list) else []
    meta = {'lang_code': lang, 'display_name': name.strip(), 'locale': normalize_lang(locale) or lang, 'status': 'user', 'public_enabled': True, 'direction': direction, 'fallback_chain': chain, 'font_hint': _short(m.get('font_hint'), 200, 'Segoe UI, Arial, sans-serif'), 'plural_form': plural, 'decimal_separator': _short(m.get('decimal_separator'), 3, '.'), 'thousands_separator': _short(m.get('thousands_separator'), 3, ','), 'quote_open': _short(m.get('quote_open'), 3, '“'), 'quote_close': _short(m.get('quote_close'), 3, '”'), 'secondary_quote_open': _short(m.get('secondary_quote_open'), 3, '‘'), 'secondary_quote_close': _short(m.get('secondary_quote_close'), 3, '’'), 'user_defined': True}
    if fonts:
        meta['ui_font_families'] = fonts
    return meta

def tokens_of(text: str) -> set[str]:
    return set(TOKEN.findall(text))

def _clip(value: object) -> str:
    return value.strip()[:MAX_META_LEN] if isinstance(value, str) else ''

def _entry_text(value: object) -> tuple[str | None, str | None]:
    if isinstance(value, str):
        return (value, None)
    if isinstance(value, dict):
        t = value.get('text', '')
        if t is None:
            t = ''
        if isinstance(t, str):
            return (t, None)
    return (None, '値が文字列でも {source,text} でもない')

def check_text(text: str, base: str | None) -> str | None:
    if len(text) > MAX_TEXT_LEN:
        return f'{MAX_TEXT_LEN} 文字を超えている'
    if _CTRL_RE.search(text):
        return '制御文字を含む'
    if '<' in text or '>' in text:
        return '< または > を含む（HTML は使えない）'
    if base:
        extra = tokens_of(text) - tokens_of(base)
        if extra:
            return '同梱の訳に無い置換項目がある: ' + ' '.join(sorted(extra))
    return None

def _warn(warnings: list[str], kind: str, where: str, detail: str) -> None:
    warnings.append(f'[{kind}] {where} {detail}'.rstrip())

def resolve_bundled(lang: str, bundled: dict[str, str]) -> str | None:
    low = (lang or '').lower()
    if low in bundled:
        return bundled[low]
    parts = low.split('-')
    if parts[0] == 'zh' and (not any((p in ('hans', 'hant') for p in parts[1:]))):
        region = next((p.upper() for p in parts[1:] if len(p) == 2), '')
        want = 'zh-hant' if region in ('TW', 'HK', 'MO') else 'zh-hans'
        if want in bundled:
            return bundled[want]
    for i in range(len(parts) - 1, 0, -1):
        cand = '-'.join(parts[:i])
        if cand in bundled:
            return bundled[cand]
    if len(parts) == 1:
        subs = [v for k, v in bundled.items() if k.startswith(parts[0] + '-')]
        if len(subs) == 1:
            return subs[0]
    return None

def parse_file(path: str, *, bundled: dict[str, str], category_loader: CategoryLoader) -> dict:
    name = os.path.basename(path)
    res: dict = {'filename': name, 'status': 'skipped', 'reason': '', 'code': '', 'lang': '', 'entries': 0, 'skipped': 0, 'warnings': [], 'author': '', 'license': '', 'comment': '', 'texts': {}, 'cats': {}}
    warnings: list[str] = res['warnings']
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        res['code'] = 'unreadable'
        res['reason'] = f'読めない: {exc}'
        return res
    if size > MAX_FILE_BYTES:
        res['code'] = 'too_large'
        res['reason'] = f'{MAX_FILE_BYTES // (1024 * 1024)} MiB を超えている'
        return res
    try:
        with open(path, 'r', encoding='utf-8-sig') as fh:
            raw = json.load(fh)
    except (OSError, ValueError, RecursionError) as exc:
        res['code'] = 'json'
        res['reason'] = f'JSON として読めない: {exc}'
        return res
    if not isinstance(raw, dict):
        res['code'] = 'json'
        res['reason'] = '最上位が JSON オブジェクトでない'
        return res
    if raw.get('schema') != SCHEMA:
        res['code'] = 'schema'
        res['reason'] = 'schema が違う（rtesaa.user_translation ではない）'
        return res
    version = raw.get('schema_version')
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        res['code'] = 'schema'
        res['reason'] = 'schema_version が整数でない'
        return res
    if version > SCHEMA_VERSION:
        res['code'] = 'version'
        res['reason'] = f'schema_version {version} はこの版より新しい（対応は {SCHEMA_VERSION}）'
        return res
    lang = normalize_lang(raw.get('lang'))
    if lang is None:
        res['code'] = 'lang'
        res['reason'] = 'lang が言語コード（BCP 47）として不正'
        return res
    res['lang'] = lang
    code = resolve_bundled(lang, bundled)
    is_new = code is None
    res['is_new'] = is_new
    meta = None
    if is_new:
        meta = build_meta(lang, raw.get('meta'), bundled=bundled, warnings=warnings)
        if meta is None:
            res['code'] = 'display_name'
            res['reason'] = 'meta.display_name が無い・不正（言語一覧に出す名前が要る）'
            return res
        code = lang
        res['meta'] = meta
        struct_lang = bundled.get('ja') or bundled.get('en') or next(iter(bundled.values()), '')
        token_lang = bundled.get(meta['fallback_chain'][1].lower(), struct_lang)
    else:
        res['lang'] = code
        struct_lang = token_lang = code
    texts_root = raw.get('texts')
    if not isinstance(texts_root, dict):
        res['code'] = 'texts'
        res['reason'] = 'texts がオブジェクトでない'
        return res
    res['author'] = _clip(raw.get('author'))
    res['license'] = _clip(raw.get('license'))
    res['comment'] = _clip(raw.get('comment'))
    if 'meta' in raw and (not is_new):
        _warn(warnings, 'meta', '', '同梱言語の meta は無視する（_meta.json が正）')
    if not is_new and code.lower() == 'en':
        _warn(warnings, 'en', '', 'en は UI の文言だけ上書きできる')
    skipped = 0
    for cat, body in texts_root.items():
        if not isinstance(cat, str) or not _CAT_RE.match(cat):
            skipped += _count(body)
            _warn(warnings, 'category', str(cat), 'カテゴリ名が不正')
            continue
        base = category_loader(struct_lang, cat)
        if base is None:
            skipped += _count(body)
            _warn(warnings, 'category', cat, '同梱にこのカテゴリが無い')
            continue
        if not isinstance(body, dict):
            _warn(warnings, 'category', cat, '値がオブジェクトでない')
            continue
        for key, value in body.items():
            where = f'{cat}::{key}'
            if not isinstance(key, str) or key.startswith('_'):
                continue
            if key not in base:
                skipped += 1
                _warn(warnings, 'key', where, '同梱にこのキーが無い')
                continue
            text, bad = _entry_text(value)
            if bad:
                skipped += 1
                _warn(warnings, 'value', where, bad)
                continue
            if not text or not text.strip():
                continue
            base_text = base.get(key)
            if is_new and token_lang != struct_lang:
                other = category_loader(token_lang, cat)
                if other and other.get(key):
                    base_text = other[key]
            problem = check_text(text, base_text)
            if problem:
                skipped += 1
                _warn(warnings, 'text', where, problem)
                continue
            res['texts'][key] = text
            res['cats'][key] = cat
    res['entries'] = len(res['texts'])
    res['skipped'] = skipped
    res['status'] = 'ok'
    return res

def _count(body: object) -> int:
    return len(body) if isinstance(body, dict) else 1

def load_dir(translations_dir: str | None, *, bundled: dict[str, str], category_loader: CategoryLoader) -> UserPacks:
    packs = UserPacks()
    if not translations_dir or not os.path.isdir(translations_dir):
        return packs
    try:
        names = sorted((n for n in os.listdir(translations_dir) if n.lower().endswith('.json') and (not n.startswith('_'))))
    except OSError:
        return packs
    names.sort(key=lambda n: n.lower())
    seen_lang: dict[str, str] = {}
    for name in names:
        try:
            info = parse_file(os.path.join(translations_dir, name), bundled=bundled, category_loader=category_loader)
        except Exception as exc:
            packs.warnings.append(f'[skip] {name}: 読み込み中に例外 {type(exc).__name__}')
            packs.files.append({'filename': name, 'status': 'skipped', 'code': 'json', 'reason': f'{type(exc).__name__}', 'lang': '', 'entries': 0, 'skipped': 0, 'warnings': []})
            continue
        packs.files.append({k: v for k, v in info.items() if k not in ('texts', 'cats', 'meta')})
        if info['status'] != 'ok':
            packs.warnings.append(f"[skip] {name}: {info['reason']}")
            continue
        lang = info['lang']
        if lang in seen_lang:
            packs.warnings.append(f'[dup] {name}: 同じ言語 {lang} のファイルが複数ある（{seen_lang[lang]} の後に読む・後が勝つ）')
        seen_lang[lang] = name
        if info.get('is_new'):
            packs.langs[lang] = info['meta']
        packs.overlay.setdefault(lang, {}).update(info['texts'])
        packs.categories.setdefault(lang, {}).update(info['cats'])
        for w in info['warnings']:
            packs.warnings.append(f'{name}: {w}')
    return packs

def build_template(lang: str, *, categories: list[str], category_loader: CategoryLoader, source_loader: CategoryLoader | None=None, app_version: str='') -> dict:
    texts: dict[str, dict] = {}
    for cat in categories:
        base = category_loader(lang, cat)
        if not base:
            continue
        src = source_loader(cat, base) if source_loader else None
        body: dict = {}
        for key, text in base.items():
            if src is not None and src.get(key):
                body[key] = {'source': src[key], 'text': text}
            else:
                body[key] = text
        texts[cat] = body
    return {'schema': SCHEMA, 'schema_version': SCHEMA_VERSION, 'lang': lang, 'author': '', 'license': '', 'comment': '', 'exported_from': {'app_version': app_version, 'lang': lang, 'with_source': source_loader is not None}, 'texts': texts}

def build_new_language_template(*, categories: list[str], category_loader: CategoryLoader, reference_lang: str, source_loader: Callable[[str, dict], 'dict[str, str] | None'] | None=None, app_version: str='') -> dict:
    texts: dict[str, dict] = {}
    for cat in categories:
        base = category_loader(reference_lang, cat)
        if not base:
            continue
        src = source_loader(cat, base) if source_loader else None
        body: dict = {}
        for key, ref in base.items():
            entry: dict = {}
            if src and src.get(key):
                entry['source'] = src[key]
            if ref:
                entry['ref'] = ref
            entry['text'] = ''
            body[key] = entry
        texts[cat] = body
    return {'schema': SCHEMA, 'schema_version': SCHEMA_VERSION, 'lang': '', 'meta': {'display_name': '', 'locale': '', 'direction': 'ltr', 'fallback': 'en', 'font_hint': 'Segoe UI, Arial, sans-serif', 'ui_font_families': [], 'plural_form': 'en_like_2'}, 'author': '', 'license': '', 'comment': 'lang は言語コード（例: tr）、meta.display_name は言語一覧に出す名前。source は英語の原文、ref は参照言語の訳。text に訳を書く（空の項目は fallback の言語で表示）。', 'exported_from': {'app_version': app_version, 'lang': '', 'with_source': source_loader is not None, 'reference_lang': reference_lang}, 'texts': texts}

def write_template(path: str, data: dict) -> None:
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write('\n')

@dataclass
class InstallResult:
    status: str
    code: str = ''
    lang: str = ''
    dest: str = ''
    entries: int = 0
    skipped: int = 0
    reason: str = ''
    warnings: list[str] = field(default_factory=list)

def install(src_path: str, translations_dir: str, *, bundled: dict[str, str], category_loader: CategoryLoader, overwrite: bool=False) -> InstallResult:
    info = parse_file(src_path, bundled=bundled, category_loader=category_loader)
    if info['status'] != 'ok':
        return InstallResult('invalid', code=info['code'], lang=info['lang'], reason=info['reason'])
    dest = os.path.join(translations_dir, info['lang'] + '.json')
    other = _same_language_file(translations_dir, info['lang'], bundled, category_loader)
    if other:
        dest = other
    result = InstallResult('ok', lang=info['lang'], dest=dest, entries=info['entries'], skipped=info['skipped'], warnings=list(info['warnings']))
    same = os.path.abspath(src_path) == os.path.abspath(dest)
    if os.path.exists(dest) and (not same) and (not overwrite):
        result.status = 'exists'
        return result
    if not same:
        try:
            os.makedirs(translations_dir, exist_ok=True)
            shutil.copyfile(src_path, dest)
        except OSError as exc:
            return InstallResult('invalid', code='unreadable', lang=info['lang'], reason=f'書き込めない: {exc}')
    return result

def _same_language_file(translations_dir: str, lang: str, bundled: dict[str, str], category_loader: CategoryLoader) -> str:
    try:
        names = sorted((n for n in os.listdir(translations_dir) if n.lower().endswith('.json') and (not n.startswith('_'))), key=lambda n: n.lower())
    except OSError:
        return ''
    found = ''
    for name in names:
        path = os.path.join(translations_dir, name)
        try:
            info = parse_file(path, bundled=bundled, category_loader=category_loader)
        except Exception:
            continue
        if info['status'] == 'ok' and info['lang'] == lang:
            found = path
    return found

def remove_file(translations_dir: str, filename: str) -> bool:
    if not filename or filename != os.path.basename(filename):
        return False
    path = os.path.join(translations_dir, filename)
    if not os.path.isfile(path):
        return False
    try:
        os.remove(path)
    except OSError:
        return False
    return True
