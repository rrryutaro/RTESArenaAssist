from __future__ import annotations
import os
from spell_effect_compose import _lookup_pair, _active_effect_slot, _resolve_effect_name, _effect_details_from_arrays, _decode_spell_effect_segments, _normalize_spell_effect_text, _attach_effect_texts, _fill_missing_spellmaker_effect_texts, translate_effect_text
__all__ = ['load_spellsg', 'read_spell_detail', 'read_spellbook_items', 'translate_effect_text']
NPCDATA_BASE = 420
SPELL_COUNT_OFFSET = NPCDATA_BASE + 870
SPELL_IDS_OFFSET = NPCDATA_BASE + 871
SPELL_DATA_SIZE = 85
SPELL_NAME_OFFSET = 52
SPELL_NAME_LEN = 33
MAX_KNOWN_SPELLS = 160

def load_spellsg(game_dir: str) -> dict[int, str]:
    if not game_dir:
        return {}
    for nn in ('00', '01', '02', '03', '04', '05', '06', '07', '08', '09'):
        path = os.path.join(game_dir, f'SPELLSG.{nn}')
        if not os.path.exists(path):
            continue
        try:
            with open(path, 'rb') as f:
                data = f.read()
            result: dict[int, str] = {}
            max_records = min(MAX_KNOWN_SPELLS, len(data) // SPELL_DATA_SIZE)
            for i in range(max_records):
                base = i * SPELL_DATA_SIZE
                if base + SPELL_DATA_SIZE > len(data):
                    break
                name_bytes = data[base + SPELL_NAME_OFFSET:base + SPELL_NAME_OFFSET + SPELL_NAME_LEN]
                name = name_bytes.split(b'\x00')[0].decode('ascii', errors='replace').strip()
                if name:
                    result[i] = name
            return result
        except OSError:
            continue
    return {}
SPELL_DETAIL_DATA_OFFSET = 22502
SPELL_DETAIL_NAME_OFFSET = SPELL_DETAIL_DATA_OFFSET + SPELL_NAME_OFFSET
SPELL_DETAIL_COST_OFFSET = SPELL_DETAIL_DATA_OFFSET + 50
SPELL_DETAIL_TARGET_OFFSET = SPELL_DETAIL_DATA_OFFSET + 36
SPELL_DETAIL_ELEMENT_OFFSET = SPELL_DETAIL_DATA_OFFSET + 38
SPELL_DETAIL_FLAGS_OFFSET = SPELL_DETAIL_DATA_OFFSET + 39
SPELL_DETAIL_EFFECTS_OFFSET = SPELL_DETAIL_DATA_OFFSET + 41
SPELL_DETAIL_SUB_EFFECTS_OFFSET = SPELL_DETAIL_DATA_OFFSET + 44
SPELL_DETAIL_AFFECTED_ATTRS_OFFSET = SPELL_DETAIL_DATA_OFFSET + 47
SPELL_DETAIL_TEXT_OFFSET = 4164
SPELL_DETAIL_TEXT_LEN = 512
PLAYER_NAME_OFFSET = 429
PLAYER_LEVEL_OFFSET = 426
PLAYER_GOLD_OFFSET = 1474
TARGET_TYPE_NAMES = {0: ('Caster only', '自分のみ'), 1: ('1 Target, Touch', '対象1体・接触'), 2: ('1 Target at Range', '対象1体・遠隔'), 3: ('Area - Centered on Caster', '範囲・術者中心'), 4: ('Area - at Range, Explosion', '範囲・遠隔爆発')}
ELEMENT_NAMES = {0: ('Fire', '火'), 1: ('Cold', '冷気'), 2: ('Poison', '毒'), 3: ('Shock', '電撃'), 4: ('Magic', '魔法'), 5: ('None', 'なし'), 6: ('Energy', 'エネルギー')}

def read_spell_detail(analyzer, anchor: int) -> dict:

    def _u8(off: int) -> int:
        try:
            return analyzer.read_bytes(anchor + off, 1)[0]
        except (OSError, AttributeError):
            return 0

    def _u8_opt(off: int) -> int | None:
        try:
            return analyzer.read_bytes(anchor + off, 1)[0]
        except (OSError, AttributeError, IndexError):
            return None

    def _u16(off: int) -> int:
        try:
            b = analyzer.read_bytes(anchor + off, 2)
            return b[0] | b[1] << 8
        except (OSError, AttributeError):
            return 0

    def _u8_array(off: int, length: int, default: int=0) -> list[int]:
        try:
            raw = analyzer.read_bytes(anchor + off, length)
            return [raw[i] if i < len(raw) else default for i in range(length)]
        except (OSError, AttributeError):
            return [default] * length

    def _str(off: int, length: int) -> str:
        try:
            raw = analyzer.read_bytes(anchor + off, length)
            return raw.split(b'\x00', 1)[0].decode('ascii', errors='replace').strip()
        except (OSError, AttributeError):
            return ''
    name = _str(SPELL_DETAIL_NAME_OFFSET, SPELL_NAME_LEN)
    cost = _u16(SPELL_DETAIL_COST_OFFSET)
    spell_cost = cost * 2 if cost else 0
    casting_cost = spell_cost // 4 if spell_cost else 0
    target_id = _u8(SPELL_DETAIL_TARGET_OFFSET)
    element_id = _u8(SPELL_DETAIL_ELEMENT_OFFSET)
    effects = _u8_array(SPELL_DETAIL_EFFECTS_OFFSET, 3, 255)
    sub_effects = _u8_array(SPELL_DETAIL_SUB_EFFECTS_OFFSET, 3, 0)
    affected_attrs = _u8_array(SPELL_DETAIL_AFFECTED_ATTRS_OFFSET, 3, 0)
    effect_details = _effect_details_from_arrays(effects, sub_effects, affected_attrs)
    effect_slot = _active_effect_slot(effects)
    effect_id = effects[effect_slot]
    sub_effect_id = sub_effects[effect_slot]
    affected_attr_id = affected_attrs[effect_slot]
    target_en, target_ja = _lookup_pair(TARGET_TYPE_NAMES, target_id)
    element_en, element_ja = _lookup_pair(ELEMENT_NAMES, element_id)
    effect_en, effect_ja = _resolve_effect_name(effect_id, sub_effect_id, affected_attr_id)
    text_en = ''
    text_segments: list[str] = []
    try:
        raw = analyzer.read_bytes(anchor + SPELL_DETAIL_TEXT_OFFSET, SPELL_DETAIL_TEXT_LEN)
        text_segments = _decode_spell_effect_segments(raw)
        text_en = ' '.join(text_segments).strip()
    except (OSError, AttributeError):
        pass
    player_name = _str(PLAYER_NAME_OFFSET, 26)
    level_raw = _u8_opt(PLAYER_LEVEL_OFFSET)
    player_level = level_raw + 1 if level_raw is not None else 0
    player_gold = _u16(PLAYER_GOLD_OFFSET)
    effect_details = _attach_effect_texts(text_en, effect_details, text_segments)
    effect_details = _fill_missing_spellmaker_effect_texts(effect_details, analyzer, anchor)
    if effect_details:
        first_detail = effect_details[0]
        effect_en = first_detail.get('effect_en', effect_en)
        effect_ja = first_detail.get('effect_ja', effect_ja)
        text_en = first_detail.get('text_en', '') or ''
        text_ja = first_detail.get('text_ja', '') or ''
    else:
        text_en, text_ja = _normalize_spell_effect_text(text_en, effect_en)
    return {'name': name, 'cost': cost, 'spell_cost': spell_cost, 'casting_cost': casting_cost, 'target_id': target_id, 'target_en': target_en, 'target_ja': target_ja, 'element_id': element_id, 'element_en': element_en, 'element_ja': element_ja, 'effect_slot': effect_slot, 'effect_id': effect_id, 'sub_effect_id': sub_effect_id, 'affected_attr_id': affected_attr_id, 'effects': effects, 'sub_effects': sub_effects, 'affected_attrs': affected_attrs, 'effect_details': effect_details, 'effect_en': effect_en, 'effect_ja': effect_ja, 'text_en': text_en, 'text_ja': text_ja, 'player_name': player_name, 'player_level': player_level, 'player_gold': player_gold}

def read_spellbook_items(analyzer, anchor: int) -> list[dict]:
    import assist_settings as settings
    game_dir = settings.get('save_dir', '')
    spell_table = load_spellsg(game_dir)
    try:
        count = analyzer.read_bytes(anchor + SPELL_COUNT_OFFSET, 1)[0]
    except OSError:
        return []
    if count == 0 or count > 160:
        return []
    try:
        ids_raw = analyzer.read_bytes(anchor + SPELL_IDS_OFFSET, count)
    except OSError:
        return []
    items: list[dict] = []
    for spell_id in ids_raw[:count]:
        name = spell_table.get(spell_id, f'Spell#{spell_id}')
        items.append({'en': name})
    return items
