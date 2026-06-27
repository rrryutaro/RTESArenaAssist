from __future__ import annotations
from typing import Tuple

def settle_char_page(detected: str, settling: bool, budget: int) -> Tuple[str, bool, int]:
    if not settling:
        return (detected, False, budget)
    if detected == 'status_page':
        return ('status_page', False, 0)
    if budget <= 0:
        return (detected, False, 0)
    return ('status_page', True, budget - 1)
__all__ = ['settle_char_page']
