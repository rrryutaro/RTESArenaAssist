from __future__ import annotations
import struct
import i18n_helper as i18n
ITEM_SIZE = 19
INV_SLOTS = 40
INV_OFFSET = 530
WEAPON_NAMES_OFFSET = 8708
PLATE_NAMES_OFFSET = 9870
CHAIN_NAMES_OFFSET = 10032
LEATHER_NAMES_OFFSET = 10194
JEWELRY_NAMES_OFFSET = 8232
SPELLCASTING_NAMES_OFFSET = 7633
MATERIAL_NAMES_OFFSET = 9791
BASE_ARMOR_NAMES_OFFSET = 9252
ARMOR_ENCHANT_NAMES_OFFSET = 9549
WEAPON_ENCHANT_NAMES_OFFSET = 8991
POTION_NAMES_OFFSET = 10445
POTION_NAMES_SIZE = 772
POTION_COUNT = 15
UNIDENT_POTION_NAME_OFFSET = 24112
SPELL_ATTACK_NAMES_OFFSET = 7683
SPELL_DEFENSE_NAMES_OFFSET = 7946
SPELL_MISC_NAMES_OFFSET = 8095
SPELL_ATTACK_COUNT = 15
SPELL_DEFENSE_COUNT = 9
SPELL_MISC_COUNT = 8
FLAG_MAGIC = 1
FLAG_UNIDENTIFIED = 2
ENCHANT_COUNT = 14
ACCESSORY_MATERIAL_BASE = 3
SHIELD_SLOT_MIN = 7
SHIELD_SLOT_MAX = 11
ARMOR_PIECE_SLOT_MAX = 6
_CONDITION_THRESHOLDS = [1, 5, 15, 40, 60, 75, 91]
_ITEMS_LABEL_SOURCE_IDS = {'items.spellcasting_items.1.0': 'aexe:equipment:spellcasting_item_names:1', 'items.spellcasting_items.3.0': 'aexe:equipment:spellcasting_item_names:3', **{f'items.conditions.{i}.0': f'aexe:equipment:item_condition_names:{i}' for i in range(8)}}

def _label_text(label_id: str) -> str:
    s = i18n.text_opt(label_id)
    if s is None:
        sid = _ITEMS_LABEL_SOURCE_IDS.get(label_id)
        if sid:
            s = i18n.text_by_source_id(sid, category='items')
    return s if s is not None else i18n.text(label_id)

def _weight_str(weight_raw: int) -> str:
    if weight_raw == 0:
        return '—'
    kg = weight_raw / 256
    return f'{kg:.1f}kg' if kg != int(kg) else f'{int(kg)}.0kg'

def _shield_name_original(sid: int) -> str:
    try:
        rec = i18n.originals('items').get(f'items.shields.{sid}.0')
        if isinstance(rec, dict):
            return rec.get('original') or ''
    except Exception:
        return ''
    return ''

def is_broken_item(health: int, max_hp: int, hands: int=0) -> bool:
    if hands > 2 or max_hp <= 1:
        return False
    return health * 100 // max_hp < _CONDITION_THRESHOLDS[0]

def _condition_str(item: dict) -> str:
    if item['hands'] > 2:
        return i18n.text('item.condition.charges_left').replace('{count}', str(item['hands']))
    hp, max_hp = (item['health'], item['max_hp'])
    if max_hp <= 1:
        return ''
    pct = hp * 100 // max_hp
    idx = 0
    for i, threshold in enumerate(_CONDITION_THRESHOLDS, start=1):
        if pct >= threshold:
            idx = i
    return _label_text(f'items.conditions.{idx}.0')

def _effect_str(item: dict) -> str:
    if item['hands'] in (1, 2):
        return i18n.text('item.effect.damage').replace('{min}', str(item['param1'])).replace('{max}', str(item['param2']))
    ar = item['param1'] // 5
    if ar <= 0:
        return ''
    return i18n.text('item.effect.defense').replace('{ar}', str(ar))

def _read_null_strings(data: bytes, max_count: int) -> list[str]:
    result: list[str] = []
    pos = 0
    for _ in range(max_count):
        end = data.find(b'\x00', pos)
        if end == -1:
            end = len(data)
        s = data[pos:end].decode('ascii', errors='replace').strip()
        result.append(s)
        pos = end + 1
        if pos >= len(data):
            break
    return result

def _parse_item(data: bytes, off: int) -> dict | None:
    if off + ITEM_SIZE > len(data):
        return None
    d = data[off:off + ITEM_SIZE]
    return dict(slot_id=d[0], weight=struct.unpack_from('<H', d, 1)[0], hands=d[3], param1=d[4], param2=d[5], health=struct.unpack_from('<H', d, 6)[0], max_hp=struct.unpack_from('<H', d, 8)[0], price=struct.unpack_from('<I', d, 10)[0], flags=d[14], x=d[15], material=d[16], y=d[17], attr=d[18])
_ACCESSORY_SLOT_LABEL_IDS = {0: 'item.slot.bracelet', 1: 'item.slot.belt', 2: 'item.slot.torc', 3: 'item.slot.amulet'}
_SPELLCASTING_SLOT_LABEL_IDS = {0: 'item.slot.mark', 1: 'items.spellcasting_items.1.0', 2: 'item.slot.bracers', 3: 'items.spellcasting_items.3.0'}
_ARMOR_SLOT_LABEL_IDS = {0: 'item.slot.torso', 1: 'item.slot.hands', 2: 'item.slot.legs', 3: 'item.slot.shoulder_left', 4: 'item.slot.shoulder_right', 5: 'item.slot.head', 6: 'item.slot.feet'}

def _slot_label(item: dict, classification: tuple[str, int] | None=None) -> str:
    hands = item['hands']
    sid = item['slot_id']
    kind, _armor_material_id = classification if classification is not None else _classify_item(item)
    if kind == 'potion':
        return _label_text('item.slot.potion')
    if kind == 'weapon':
        return _label_text('item.slot.one_handed' if hands == 1 else 'item.slot.two_handed')
    if kind == 'spellcasting':
        return _label_text(_SPELLCASTING_SLOT_LABEL_IDS.get(sid, 'item.slot.spellcasting'))
    if kind == 'accessory':
        return _label_text(_ACCESSORY_SLOT_LABEL_IDS.get(sid, 'item.slot.accessory'))
    if kind == 'armor':
        return _label_text(_ARMOR_SLOT_LABEL_IDS.get(sid, 'item.slot.armor'))
    if kind == 'shield':
        return _label_text('item.slot.shield')
    return ''

def _is_potion(item: dict) -> bool:
    return item['hands'] == 0 and item['attr'] == 255 and (item['x'] == 0) and (0 <= item['slot_id'] < POTION_COUNT)

def _potion_count(item: dict) -> int:
    return item['weight'] + 1

def _classify_item(item: dict) -> tuple[str, int]:
    if _is_potion(item):
        return ('potion', -1)
    sid = item['slot_id']
    hands = item['hands']
    p1 = item['param1']
    if hands in (1, 2):
        return ('weapon', -1)
    if hands > 2:
        return ('spellcasting', -1)
    if item['x'] == 255 and 0 <= sid <= 3:
        return ('accessory', -1)
    if SHIELD_SLOT_MIN <= sid <= SHIELD_SLOT_MAX:
        return ('shield', -1)
    if item['x'] == 255 and 0 <= item['material'] <= 7 and (4 <= sid <= 6):
        return ('armor', 2)
    if 40 <= p1 <= 50:
        return ('armor', 2)
    if 29 <= p1 <= 39:
        return ('armor', 1)
    if 18 <= p1 <= 28:
        return ('armor', 0)
    return ('accessory', -1)

def _is_empty(item: dict) -> bool:
    return item['price'] == 0 and item['health'] == 0 and (item['max_hp'] == 0) and (item['param1'] == 0) and (item['slot_id'] == 0)

def _display_unidentified(item: dict) -> bool:
    flags = item['flags']
    return bool(flags & FLAG_MAGIC) and bool(flags & FLAG_UNIDENTIFIED)

def _ench_index(item: dict) -> int | None:
    flags = item['flags']
    if not flags & FLAG_MAGIC:
        return None
    if flags & FLAG_UNIDENTIFIED:
        return None
    x = item['x']
    if x == 255 or not 0 <= x < ENCHANT_COUNT:
        return None
    return x

def _get_item_name(item: dict, weapon_names: list[str], plate_names: list[str], chain_names: list[str], leather_names: list[str], jewelry_names: list[str], spellcasting_names: list[str], material_names: list[str], base_armor_names: list[str], armor_enchant_names: list[str], weapon_enchant_names: list[str], spell_attack_names: list[str], spell_defense_names: list[str], spell_misc_names: list[str], potion_names: list[str] | None=None, unidentified_potion_name: list[str] | None=None, classification: tuple[str, int] | None=None) -> str:
    sid = item['slot_id']
    hands = item['hands']
    p1 = item['param1']
    mat_id = item['material']
    is_magic = bool(item['flags'] & FLAG_MAGIC)
    is_identified = not item['flags'] & FLAG_UNIDENTIFIED
    kind, _armor_material_id = classification if classification is not None else _classify_item(item)
    if kind == 'potion':
        if not is_identified:
            _un = unidentified_potion_name or []
            if _un and _un[0]:
                return _un[0]
            return 'Potion#?'
        _pn = potion_names or []
        return _pn[sid] if 0 <= sid < len(_pn) else f'Potion#{sid}'
    if kind == 'weapon':
        if 0 <= sid < len(weapon_names):
            base = weapon_names[sid]
        else:
            return f'Weapon#{sid}'
        if item['x'] == 255 and 0 <= mat_id < len(material_names):
            return f'{material_names[mat_id]} {base}'
        ei = _ench_index(item)
        if ei is not None and ei < len(weapon_enchant_names):
            return f'{base} {weapon_enchant_names[ei]}'
        return base
    if kind == 'spellcasting':
        base = spellcasting_names[sid] if 0 <= sid < len(spellcasting_names) else f'Spellcasting#{sid}'
        if is_magic and is_identified:
            table = {0: spell_attack_names, 1: spell_defense_names, 2: spell_misc_names}.get(mat_id)
            x = item['x']
            if table is not None and 0 <= x < len(table):
                return f'{base} {table[x]}'
        return base
    ei = _ench_index(item)
    if ei is not None and kind == 'accessory' and (0 <= sid < len(jewelry_names)):
        base = jewelry_names[sid]
        if ei < len(armor_enchant_names):
            return f'{base} {armor_enchant_names[ei]}'
        return base
    if ei is not None and kind in ('armor', 'shield') and (0 <= sid < len(base_armor_names)):
        base = base_armor_names[sid]
        if 0 <= mat_id < len(material_names):
            base = f'{material_names[mat_id]} {base}'
        if ei < len(armor_enchant_names):
            return f'{base} {armor_enchant_names[ei]}'
    if kind == 'accessory' and item['x'] == 255:
        base = jewelry_names[sid] if 0 <= sid < len(jewelry_names) else f'Jewelry#{sid}'
        if is_magic and is_identified:
            mi = mat_id + ACCESSORY_MATERIAL_BASE
            if 0 <= mi < len(material_names):
                return f'{material_names[mi]} {base}'
        return base
    if kind == 'armor' and item['x'] == 255 and (0 <= mat_id < len(material_names)) and (4 <= sid <= ARMOR_PIECE_SLOT_MAX):
        base = base_armor_names[sid] if sid < len(base_armor_names) else f'Slot#{sid}'
        return f'{material_names[mat_id]} {base}'
    if kind == 'armor':
        if 40 <= p1 <= 50:
            if 0 <= sid < len(plate_names):
                return plate_names[sid]
        elif 29 <= p1 <= 39:
            if 0 <= sid < len(chain_names):
                return chain_names[sid]
        elif 18 <= p1 <= 28:
            if 0 <= sid < len(leather_names):
                return leather_names[sid]
    elif kind == 'shield':
        if 0 <= sid < len(plate_names):
            return plate_names[sid]
        dict_name = _shield_name_original(sid)
        if dict_name:
            return dict_name
        return f'Shield#{sid}'
    elif kind == 'accessory' and 0 <= sid < len(jewelry_names):
        return jewelry_names[sid]
    elif kind == 'accessory':
        return f'Jewelry#{sid}'
    return f'Armor#{p1}'

def read_item_name_tables(analyzer, anchor: int) -> dict:

    def _s(offset: int, size: int, count: int) -> list[str]:
        try:
            return _read_null_strings(analyzer.read_bytes(anchor + offset, size), count)
        except (OSError, AttributeError, TypeError):
            return []
    return {'weapon_names': _s(WEAPON_NAMES_OFFSET, 400, 18), 'plate_names': _s(PLATE_NAMES_OFFSET, 300, 11), 'chain_names': _s(CHAIN_NAMES_OFFSET, 300, 11), 'leather_names': _s(LEATHER_NAMES_OFFSET, 300, 11), 'jewelry_names': _s(JEWELRY_NAMES_OFFSET, 100, 4), 'spellcasting_names': _s(SPELLCASTING_NAMES_OFFSET, 64, 4), 'material_names': _s(MATERIAL_NAMES_OFFSET, 100, 8), 'base_armor_names': _s(BASE_ARMOR_NAMES_OFFSET, 200, 11), 'armor_enchant_names': _s(ARMOR_ENCHANT_NAMES_OFFSET, 300, ENCHANT_COUNT), 'weapon_enchant_names': _s(WEAPON_ENCHANT_NAMES_OFFSET, 300, ENCHANT_COUNT), 'spell_attack_names': _s(SPELL_ATTACK_NAMES_OFFSET, 400, SPELL_ATTACK_COUNT), 'spell_defense_names': _s(SPELL_DEFENSE_NAMES_OFFSET, 300, SPELL_DEFENSE_COUNT), 'spell_misc_names': _s(SPELL_MISC_NAMES_OFFSET, 300, SPELL_MISC_COUNT), 'potion_names': _s(POTION_NAMES_OFFSET, POTION_NAMES_SIZE, POTION_COUNT), 'unidentified_potion_name': _s(UNIDENT_POTION_NAME_OFFSET, 16, 1)}

def name_from_item_bytes(item_bytes: bytes, tables: dict) -> str:
    item = _parse_item(item_bytes, 0)
    if item is None:
        return ''
    classification = _classify_item(item)
    return _get_item_name(item, classification=classification, **tables)

def read_equipment_items_with_status(analyzer, anchor: int) -> tuple[bool, list[dict]]:
    try:
        inv_raw = analyzer.read_bytes(anchor + INV_OFFSET, ITEM_SIZE * INV_SLOTS)
        if len(inv_raw) != ITEM_SIZE * INV_SLOTS:
            return (False, [])
    except (OSError, AttributeError, TypeError):
        return (False, [])
    tables = read_item_name_tables(analyzer, anchor)
    items: list[dict] = []
    for i in range(INV_SLOTS):
        item = _parse_item(inv_raw, i * ITEM_SIZE)
        if item is None or _is_empty(item):
            continue
        classification = _classify_item(item)
        item_type, armor_material_id = classification
        en = _get_item_name(item, classification=classification, **tables)
        items.append({'en': en, 'slot_id': item['slot_id'], 'hands': item['hands'], 'health': item['health'], 'max_hp': item['max_hp'], 'price': item['price'], 'equipped': bool(item['flags'] & 128), 'is_unidentified': _display_unidentified(item), 'item_type': item_type, 'armor_material_id': armor_material_id, 'slot_label': _slot_label(item, classification=classification), 'weight': '' if item_type == 'potion' else _weight_str(item['weight']), 'condition': '' if item_type == 'potion' else _condition_str(item), 'effect': '' if item_type == 'potion' else _effect_str(item), 'count': _potion_count(item) if item_type == 'potion' else None})
    return (True, items)

def read_equipment_items(analyzer, anchor: int) -> list[dict]:
    return read_equipment_items_with_status(analyzer, anchor)[1]
