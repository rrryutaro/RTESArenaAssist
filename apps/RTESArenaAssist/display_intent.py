from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional
from hierarchy_state import SeparationHierarchy

@dataclass(frozen=True)
class PollFrame:
    top_level: str = 'pregame'
    screen_id: Optional[str] = None
    img_name: str = ''
    panel_owner: str = ''
    hierarchy: SeparationHierarchy = field(default_factory=SeparationHierarchy)

    @classmethod
    def from_window(cls, window, *, hierarchy: Optional[SeparationHierarchy]=None) -> 'PollFrame':
        return cls(top_level=getattr(window, '_top_level_state', 'pregame'), screen_id=getattr(window, '_screen_id_prev', None), img_name=getattr(window, '_img_name_prev', '') or '', panel_owner=getattr(window, '_panel_owner', '') or '', hierarchy=hierarchy if hierarchy is not None else SeparationHierarchy.from_window(window))

@dataclass(frozen=True)
class DisplayIntent:
    kind: str
    panel_owner: str = ''
    mode: Optional[str] = None
    en: str = ''
    ja: str = ''
    panel_en: Optional[str] = None
    panel_ja: Optional[str] = None
    items: Any = None
    remaining: Optional[int] = None
    title: str = ''
    update_panel: bool = True
    update_tab: bool = True
    keep_owner: bool = False
    clear_place_list: bool = False
    clear_travel_table: bool = False
    priority: int = 0
    reason: str = ''
    allowed_current_owners: Optional[tuple[str, ...]] = None
    speech_role: Optional[str] = None
    speech_text: Optional[str] = None

    @classmethod
    def translation(cls, panel_owner: str, en: str, ja: str, *, mode: Optional[str]='translate', panel_en: Optional[str]=None, panel_ja: Optional[str]=None, update_panel: bool=True, update_tab: bool=True, keep_owner: bool=False, clear_place_list: bool=False, priority: int=0, reason: str='', allowed_current_owners: Optional[tuple[str, ...]]=None, speech_role: Optional[str]=None, speech_text: Optional[str]=None) -> 'DisplayIntent':
        return cls(kind='translation', panel_owner=panel_owner, mode=mode, en=en, ja=ja, panel_en=panel_en, panel_ja=panel_ja, update_panel=update_panel, update_tab=update_tab, keep_owner=keep_owner, clear_place_list=clear_place_list, priority=priority, reason=reason, allowed_current_owners=allowed_current_owners, speech_role=speech_role, speech_text=speech_text)

    @classmethod
    def panel_translation(cls, panel_en: str, panel_ja: str, *, priority: int=0, reason: str='', speech_role: Optional[str]=None, speech_text: Optional[str]=None) -> 'DisplayIntent':
        return cls(kind='translation', panel_owner='', mode=None, en='', ja='', panel_en=panel_en, panel_ja=panel_ja, update_tab=False, update_panel=True, keep_owner=True, priority=priority, reason=reason, speech_role=speech_role, speech_text=speech_text)

    @classmethod
    def clear(cls, panel_owner: str='', *, mode: Optional[str]='translate', clear_place_list: bool=False, clear_travel_table: bool=False, priority: int=0, reason: str='', allowed_current_owners: Optional[tuple[str, ...]]=None) -> 'DisplayIntent':
        return cls(kind='clear', panel_owner=panel_owner, mode=mode, clear_place_list=clear_place_list, clear_travel_table=clear_travel_table, priority=priority, reason=reason, allowed_current_owners=allowed_current_owners)

    @classmethod
    def clear_if_owner(cls, panel_owner: str, *, mode: Optional[str]=None, clear_place_list: bool=False, clear_travel_table: bool=False, priority: int=0, reason: str='') -> 'DisplayIntent':
        return cls(kind='clear_if_owner', panel_owner=panel_owner, mode=mode, clear_place_list=clear_place_list, clear_travel_table=clear_travel_table, priority=priority, reason=reason)

    @classmethod
    def release_if_owner(cls, panel_owner: str, *, priority: int=0, reason: str='') -> 'DisplayIntent':
        return cls(kind='release_if_owner', panel_owner=panel_owner, priority=priority, reason=reason)

    @classmethod
    def claim_owner(cls, panel_owner: str, *, mode: Optional[str]=None, priority: int=0, reason: str='') -> 'DisplayIntent':
        return cls(kind='claim_owner', panel_owner=panel_owner, mode=mode, priority=priority, reason=reason)

    @classmethod
    def panel_mode(cls, mode: str, *, priority: int=0, reason: str='') -> 'DisplayIntent':
        return cls(kind='panel_mode', mode=mode, priority=priority, reason=reason)

    @classmethod
    def shop_buy_list(cls, panel_owner: str, items: list, panel_en: str, panel_ja: str, *, priority: int=0, reason: str='') -> 'DisplayIntent':
        return cls(kind='shop_buy_list', panel_owner=panel_owner, mode='shop_buy', items=items, panel_en=panel_en, panel_ja=panel_ja, priority=priority, reason=reason)

    @classmethod
    def facility_list(cls, panel_owner: str, items: list, panel_en: str, panel_ja: str, *, priority: int=0, reason: str='') -> 'DisplayIntent':
        return cls(kind='facility_list', panel_owner=panel_owner, mode='facility_list', items=items, panel_en=panel_en, panel_ja=panel_ja, priority=priority, reason=reason)

    @classmethod
    def item_pickup_list(cls, panel_owner: str, items: list, remaining: int, *, priority: int=0, reason: str='') -> 'DisplayIntent':
        return cls(kind='item_pickup_list', panel_owner=panel_owner, mode='item_pickup', items=items, remaining=remaining, priority=priority, reason=reason)

    @classmethod
    def load_screen_slots(cls, panel_owner: str, slot_data: list, *, priority: int=0, reason: str='') -> 'DisplayIntent':
        return cls(kind='load_screen_slots', panel_owner=panel_owner, mode='load_screen', items=slot_data, priority=priority, reason=reason)

    @classmethod
    def equipment_list(cls, panel_owner: str, title: str, items: list, *, priority: int=0, reason: str='') -> 'DisplayIntent':
        return cls(kind='equipment_list', panel_owner=panel_owner, mode='equipment', title=title, items=items, priority=priority, reason=reason)

    @classmethod
    def spell_detail(cls, panel_owner: str, data: dict, *, panel_en: str='', panel_ja: str='', priority: int=0, reason: str='') -> 'DisplayIntent':
        return cls(kind='spell_detail', panel_owner=panel_owner, mode='spell_detail', items=data, panel_en=panel_en, panel_ja=panel_ja, priority=priority, reason=reason)

    @classmethod
    def travel_table(cls, panel_owner: str, rows: list, *, title: str='', panel_en: str='', panel_ja: str='', speech_role: Optional[str]=None, speech_text: Optional[str]=None, priority: int=0, reason: str='') -> 'DisplayIntent':
        return cls(kind='travel_table', panel_owner=panel_owner, mode='travel_table', items=rows, title=title, panel_en=panel_en, panel_ja=panel_ja, speech_role=speech_role, speech_text=speech_text, priority=priority, reason=reason)

    @classmethod
    def place_list(cls, panel_owner: str, items: list, *, title: str='', panel_en: str='', panel_ja: str='', priority: int=0, reason: str='') -> 'DisplayIntent':
        return cls(kind='place_list', panel_owner=panel_owner, mode='place_list', title=title, items=items, panel_en=panel_en, panel_ja=panel_ja, priority=priority, reason=reason)
__all__ = ['DisplayIntent', 'PollFrame']
