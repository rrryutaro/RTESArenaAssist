from __future__ import annotations
import re
import i18n_helper as i18n
_NON_ALNUM = re.compile('[^a-z0-9]+')

def _slug(en: str) -> str:
    s = en.strip().lower().replace("'", '')
    return _NON_ALNUM.sub('_', s).strip('_')
_ARTICLE_TOKENS = frozenset({'the'})

def lookup(en: str) -> str | None:
    if not en:
        return None
    slug = _slug(en.strip())
    hit = i18n.text_opt(f'location.{slug}.0')
    if hit is not None:
        return hit
    tokens = slug.split('_')
    stripped = [t for t in tokens if t not in _ARTICLE_TOKENS]
    if stripped and len(stripped) != len(tokens):
        return i18n.text_opt(f"location.{'_'.join(stripped)}.0")
    return None
