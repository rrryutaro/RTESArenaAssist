from __future__ import annotations
NONE = 255
_EFFECT_PREFIX = {0: 'Cause', 1: 'Continuous Damage', 2: 'Create', 3: 'Cure', 4: 'Damage', 6: 'Destroy', 9: 'Drain Attribute', 10: 'Elemental Resistance', 11: 'Fortify Attribute', 12: 'Heal', 13: 'Transfer Attribute'}
_DAMAGE_TARGET = {0: 'Health', 1: 'Fatigue', 2: 'Spell Points'}
_HEAL_TARGET = {0: 'Fatigue', 1: 'Health', 2: 'Spell Points'}
_ELEMENT_SUB = {0: 'Fire', 1: 'Cold', 2: 'Shock', 3: 'Magic', 4: 'Poison'}
_ATTRIBUTE = {0: 'Strength', 1: 'Intelligence', 2: 'Willpower', 3: 'Agility', 4: 'Speed', 5: 'Endurance', 6: 'Personality', 7: 'Luck'}
_CAUSE_SUB = {0: 'Disease', 1: 'Poison', 2: 'Paralyzation', 3: 'Curse'}
_CURE_SUB = {0: 'Disease', 1: 'Poison', 2: 'Paralyzation', 3: 'Curse'}
_CREATE_SUB = {0: 'Shield', 1: 'Wall', 2: 'Floor'}
_DESTROY_SUB = {0: 'Wall', 1: 'Floor'}
_SIMPLE_EFFECT = {5: 'Designate as Non-Target', 15: 'Invisibility', 16: 'Levitate', 17: 'Light', 18: 'Lock', 19: 'Open', 20: 'Regenerate', 21: 'Silence', 22: 'Spell Absorption', 23: 'Spell Reflection', 24: 'Spell Resistance'}
_VERIFIED_COMPOSITE = {(0, 0): 'Cause Disease', (0, 1): 'Cause Poison', (0, 2): 'Cause Paralyzation', (0, 3): 'Cause Curse', (1, 0): 'Continuous Damage Health', (1, 1): 'Continuous Damage Fatigue', (1, 2): 'Continuous Damage Spell Points', (2, 0): 'Create Shield', (2, 1): 'Create Wall', (2, 2): 'Create Floor', (3, 0): 'Cure Disease', (3, 1): 'Cure Poison', (3, 2): 'Cure Paralyzation', (3, 3): 'Cure Curse', (4, 0): 'Damage Health', (4, 1): 'Damage Fatigue', (4, 2): 'Damage Spell Points', (6, 0): 'Destroy Wall', (6, 1): 'Destroy Floor', (12, 0): 'Heal Fatigue', (12, 1): 'Heal Health', (12, 2): 'Heal Spell Points'}
_VERIFIED_STRUCTURE_EFFECTS = {9, 10, 11}

def surface_for(effect_id: int, sub_effect_id: int=0, affected_attr_id: int=0) -> tuple[str, str] | None:
    if effect_id == NONE:
        return None
    if effect_id in _SIMPLE_EFFECT:
        return (_SIMPLE_EFFECT[effect_id], 'verified')
    confirmed = _VERIFIED_COMPOSITE.get((effect_id, sub_effect_id))
    if confirmed is not None:
        return (confirmed, 'verified')
    prefix = _EFFECT_PREFIX.get(effect_id)
    if prefix is None:
        return None
    if effect_id == 9:
        attr = _ATTRIBUTE.get(sub_effect_id) or _ATTRIBUTE.get(affected_attr_id)
        return (f'{prefix} {attr}', 'verified_structure') if attr else (prefix, 'verified_surface')
    if effect_id == 11:
        attr = _ATTRIBUTE.get(sub_effect_id) or _ATTRIBUTE.get(affected_attr_id)
        return (f'{prefix} {attr}', 'verified_structure') if attr else (prefix, 'verified_surface')
    if effect_id == 10:
        elem = _ELEMENT_SUB.get(sub_effect_id)
        return (f'{prefix} {elem}', 'verified_structure') if elem else (prefix, 'verified_surface')
    if effect_id == 13:
        return (prefix, 'verified')
    return (prefix, 'unverified_composite')

def build_originals(entries: list[dict]) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for entry in entries:
        src = entry.get('source') or {}
        result = surface_for(int(src.get('effect_id', NONE)), int(src.get('sub_effect_id', 0)), int(src.get('affected_attr_id', 0)))
        if result is None:
            continue
        text, status = result
        out[int(entry['id'])] = {'text': text, 'status': status}
    return out
__all__ = ['surface_for', 'build_originals', 'NONE']
