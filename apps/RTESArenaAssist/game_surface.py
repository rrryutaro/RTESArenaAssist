from __future__ import annotations
_YN_PROMPT_SUFFIX = '(y/n)'
_YN_PROMPT_SURFACE = 'yn'

def game_surface(text: str) -> str:
    s = ' '.join((text or '').split())
    if s.endswith(_YN_PROMPT_SUFFIX):
        return s[:-len(_YN_PROMPT_SUFFIX)] + _YN_PROMPT_SURFACE
    return s
