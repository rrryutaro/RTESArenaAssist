from __future__ import annotations
from typing import Tuple
from top_level.top_level_dispatcher import current_state as _current_state
_TITLE_IMGS = ('MENU.IMG', 'PERCNTRO.XMI')

def classify_top_level(current_state: str, img: str) -> Tuple[str, str]:
    iu = (img or '').upper()
    cur = current_state or 'pregame'
    if cur != 'pregame' and iu in _TITLE_IMGS:
        return ('pregame', iu)
    if cur == 'pregame' and iu == 'EVLINTRO.XMI':
        return ('chargen', 'EVLINTRO.XMI')
    return (cur, '')

class TopLevelNode:
    name = 'top_level'

    def owner_namespace(self) -> str:
        return self.name

    def current(self, w) -> str:
        return _current_state(w)

    def classify_transition(self, w, img: str) -> Tuple[str, str]:
        return classify_top_level(_current_state(w), img)
TOP_LEVEL_NODE = TopLevelNode()
__all__ = ['classify_top_level', 'TopLevelNode', 'TOP_LEVEL_NODE']
