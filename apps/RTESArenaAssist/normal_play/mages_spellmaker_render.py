from __future__ import annotations
from normal_play.mages_render_common import _NPC_DIALOG_OFFSET, _PROMPT_EXTRA_SCAN_OFFSETS
_SPELLMAKER_LIVE_COST_HALF_OFFSETS = (22697, 22699, 22701)
_SPELLMAKER_COST_CACHE_ATTR = '_mages_spellmaker_cost_cache'
_SPELLMAKER_RECORD_OFFSET = 22502
_SPELLMAKER_RECORD_COST_KEY_LEN = 52
_SPELL_KEY = '_mages_spellmaker_key_prev'
_PROMPT_KEY = '_mages_prompt_key_prev'
_SPELLMAKER_PROMPT_LIST_FLAG = 1
_SPELLMAKER_PROMPT_HOLD_FLAG = 3
_SPELLMAKER_TEMPLATE_PTR_START = 23040
_SPELLMAKER_TEMPLATE_PTR_END = 23296
_ACTIVE_TEMPLATE_PTR_OFFSETS = tuple(range(64184, 64216, 2))
_SPELLMAKER_PROMPT_LITERALS = ('You must name this spell!', 'You do not have enough money to purchase this spell', 'The spell has been inscribed in your spellbook', 'Not enough room to store spell.', 'You must choose an effect first!')
_SPELLMAKER_PROMPT_FRAGMENT_LITERALS = ((('money', 'to purchase this spell'), 'You do not have enough money to purchase this spell'), (('inscribed', 'spellbook'), 'The spell has been inscribed in your spellbook'), (('not enough room', 'store spell'), 'Not enough room to store spell.'), (('choose', 'effect', 'first'), 'You must choose an effect first!'))
_SPELLMAKER_REFRESH_DETAIL_PROMPTS = frozenset({'The spell has been inscribed in your spellbook'})
_SPELLMAKER_LIST_TITLES = frozenset({'Targets', 'Effects', 'Effect Options'})

def _read_spellmaker_live_spell_cost(w, effects) -> int | None:
    total = 0
    for slot, effect in enumerate(effects or ()):
        if effect == 255:
            continue
        if slot >= len(_SPELLMAKER_LIVE_COST_HALF_OFFSETS):
            return None
        try:
            raw = w._analyzer.read_bytes(w._anchor + _SPELLMAKER_LIVE_COST_HALF_OFFSETS[slot], 2)
        except (OSError, AttributeError):
            return None
        if len(raw) < 2:
            return None
        total += raw[0] | raw[1] << 8
    if total <= 0:
        return None
    return total * 2

def _spellmaker_cost_cache_key(w, data: dict) -> tuple:
    try:
        raw_record = w._analyzer.read_bytes(w._anchor + _SPELLMAKER_RECORD_OFFSET, _SPELLMAKER_RECORD_COST_KEY_LEN)
    except (OSError, AttributeError):
        raw_record = b''
    return (raw_record, data.get('target_id'), data.get('element_id'), tuple(data.get('effects', [])), tuple(data.get('sub_effects', [])), tuple(data.get('affected_attrs', [])), data.get('player_level'))

def _resolve_spellmaker_spell_cost(w, data: dict) -> int:
    try:
        record_cost = int(data.get('cost') or 0)
    except (TypeError, ValueError):
        record_cost = 0
    if all((x == 255 for x in data.get('effects', []))):
        setattr(w, _SPELLMAKER_COST_CACHE_ATTR, None)
        return 0
    key = _spellmaker_cost_cache_key(w, data)
    if record_cost > 0:
        spell_cost = record_cost * 2
        setattr(w, _SPELLMAKER_COST_CACHE_ATTR, (key, spell_cost))
        return spell_cost
    live_spell_cost = _read_spellmaker_live_spell_cost(w, data.get('effects'))
    if live_spell_cost:
        setattr(w, _SPELLMAKER_COST_CACHE_ATTR, (key, live_spell_cost))
        return live_spell_cost
    cached = getattr(w, _SPELLMAKER_COST_CACHE_ATTR, None)
    if isinstance(cached, tuple) and len(cached) == 2:
        cached_key, cached_cost = cached
        if cached_key == key:
            try:
                return int(cached_cost)
            except (TypeError, ValueError):
                return 0
    return 0

def _has_spellmaker_prompt_slot(w) -> bool:
    for off in _ACTIVE_TEMPLATE_PTR_OFFSETS:
        try:
            raw = w._analyzer.read_bytes(w._anchor + off, 2)
        except (OSError, AttributeError):
            continue
        if len(raw) < 2:
            continue
        ptr = raw[0] | raw[1] << 8
        if _SPELLMAKER_TEMPLATE_PTR_START <= ptr < _SPELLMAKER_TEMPLATE_PTR_END:
            return True
    return False

def _is_spellmaker_prompt_foreground(w, sig: dict) -> bool:
    if not (sig.get('view') == 0 and sig.get('type') == 199 and (sig.get('dialog') == 61)):
        return False
    list_flag = sig.get('list')
    if list_flag == _SPELLMAKER_PROMPT_LIST_FLAG:
        return True
    if list_flag == _SPELLMAKER_PROMPT_HOLD_FLAG:
        return _has_spellmaker_prompt_slot(w)
    return False

def _resolve_spellmaker_prompt(w, sig: dict):
    if not _is_spellmaker_prompt_foreground(w, sig):
        return None
    try:
        raw = w._analyzer.read_bytes(w._anchor + _NPC_DIALOG_OFFSET, 512)
    except (OSError, AttributeError):
        raw = b''
    extra_chunks: list[bytes] = []
    for off in _PROMPT_EXTRA_SCAN_OFFSETS:
        try:
            extra_chunks.append(w._analyzer.read_bytes(w._anchor + off, 160))
        except (OSError, AttributeError):
            extra_chunks.append(b'')
    text = ''.join((c if 32 <= ord(c) <= 126 else ' ' for c in raw.decode('ascii', errors='replace')))
    literal_text = text + ' ' + ' '.join((''.join((c if 32 <= ord(c) <= 126 else ' ' for c in chunk.decode('ascii', errors='replace'))) for chunk in extra_chunks))
    normalized_text = ' '.join(literal_text.split())
    try:
        from npc_dialog_lookup import lookup as _nd_lookup
        from npc_dialog_lookup import format_japanese as _nd_format
    except Exception:
        return None
    for literal in _SPELLMAKER_PROMPT_LITERALS:
        if literal not in normalized_text:
            continue
        res = _nd_lookup(literal)
        if res:
            try:
                return (literal, _nd_format(res[0], res[1]))
            except Exception:
                return (literal, literal)
    lowered_text = normalized_text.lower()
    for needles, literal in _SPELLMAKER_PROMPT_FRAGMENT_LITERALS:
        if not all((needle in lowered_text for needle in needles)):
            continue
        res = _nd_lookup(literal)
        if res:
            try:
                return (literal, _nd_format(res[0], res[1]))
            except Exception:
                return (literal, literal)
    return None
