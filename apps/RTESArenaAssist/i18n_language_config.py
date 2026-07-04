from __future__ import annotations
import json
import os
from collections.abc import Iterable
from typing import Any
PUBLIC_STATUS = 'public_enabled'
DRAFT_STATUS = 'draft'
DEFAULT_LOCALE_TAGS = {'en': 'en-US', 'ja': 'ja-JP', 'es': 'es-ES', 'de': 'de-DE', 'fr': 'fr-FR', 'it': 'it-IT'}

def load_meta(i18n_dir: str | os.PathLike) -> dict[str, Any]:
    path = os.path.join(os.fspath(i18n_dir), '_meta.json')
    with open(path, 'r', encoding='utf-8') as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}

def language_items(i18n_dir: str | os.PathLike) -> list[tuple[str, dict[str, Any]]]:
    langs = load_meta(i18n_dir).get('languages', {})
    if not isinstance(langs, dict):
        return []
    out: list[tuple[str, dict[str, Any]]] = []
    for code, meta in langs.items():
        if isinstance(code, str) and isinstance(meta, dict):
            out.append((code, meta))
    return out

def locale_tag_for(code: str, meta: dict[str, Any] | None=None) -> str:
    if meta:
        tag = meta.get('locale')
        if isinstance(tag, str) and tag:
            return tag
    norm = (code or '').lower()
    return DEFAULT_LOCALE_TAGS.get(norm, code)

def is_public_enabled(meta: dict[str, Any], *, default: bool=False) -> bool:
    if 'public_enabled' in meta:
        return bool(meta.get('public_enabled'))
    status = meta.get('status')
    if isinstance(status, str):
        return status == PUBLIC_STATUS
    return default

def public_language_items(i18n_dir: str | os.PathLike, *, require_dir: bool=False, exclude: Iterable[str]=()) -> list[tuple[str, dict[str, Any]]]:
    base = os.fspath(i18n_dir)
    excluded = set(exclude)
    out: list[tuple[str, dict[str, Any]]] = []
    for code, meta in language_items(base):
        if code in excluded or not is_public_enabled(meta):
            continue
        if require_dir and (not os.path.isdir(os.path.join(base, code))):
            raise FileNotFoundError(f'public language has no i18n folder: {code}')
        out.append((code, meta))
    return out

def public_language_codes(i18n_dir: str | os.PathLike, *, require_dir: bool=False, exclude: Iterable[str]=()) -> list[str]:
    return [code for code, _meta in public_language_items(i18n_dir, require_dir=require_dir, exclude=exclude)]

def public_locale_tags(i18n_dir: str | os.PathLike, *, require_dir: bool=False, exclude: Iterable[str]=()) -> list[str]:
    return [locale_tag_for(code, meta) for code, meta in public_language_items(i18n_dir, require_dir=require_dir, exclude=exclude)]
