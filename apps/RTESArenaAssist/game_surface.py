from __future__ import annotations
import re
_REF_MARKER_ARTICLE_RE = re.compile('^#\\d{4} t(he\\b.*)$')
_YN_PROMPT_SUFFIX = '(y/n)'
_YN_PROMPT_SURFACE = 'yn'

def game_surface(text: str) -> str:
    s = ' '.join((text or '').split())
    m = _REF_MARKER_ARTICLE_RE.match(s)
    if m:
        s = m.group(1)
    if s.endswith(_YN_PROMPT_SUFFIX):
        return s[:-len(_YN_PROMPT_SUFFIX)] + _YN_PROMPT_SURFACE
    return s
