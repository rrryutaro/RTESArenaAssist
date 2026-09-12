from __future__ import annotations
from typing import Optional
from .arena_types import ArenaMenuType
_CATEGORY = {ArenaMenuType.EQUIPMENT: 'equipment_store', ArenaMenuType.TAVERN: 'tavern', ArenaMenuType.TEMPLE: 'temple'}

def category_of(menu_type: Optional[ArenaMenuType]) -> str:
    return _CATEGORY.get(menu_type, '')
__all__ = ['category_of']
