from __future__ import annotations
import re
import i18n_helper as i18n
_NON_ALNUM = re.compile('[^a-z0-9]+')

def _slug(en: str) -> str:
    s = en.strip().lower().replace("'", '')
    return _NON_ALNUM.sub('_', s).strip('_')

def lookup(en: str) -> str | None:
    if not en:
        return None
    return i18n.text_opt(f'location.{_slug(en.strip())}.0')
