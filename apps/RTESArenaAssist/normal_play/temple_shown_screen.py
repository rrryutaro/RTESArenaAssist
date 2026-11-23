from __future__ import annotations
_ATTR = '_temple_last_shown'
SHOWN_NONE = ''
SHOWN_MENU = 'menu'
SHOWN_COST = 'cost'
SHOWN_CURE = 'cure'
SHOWN_REPLY = 'reply'

def note_shown(w, screen: str) -> None:
    setattr(w, _ATTR, screen)

def last_shown(w) -> str:
    return getattr(w, _ATTR, SHOWN_NONE)
__all__ = ['SHOWN_NONE', 'SHOWN_MENU', 'SHOWN_COST', 'SHOWN_CURE', 'SHOWN_REPLY', 'note_shown', 'last_shown']
