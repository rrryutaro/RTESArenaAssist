from __future__ import annotations
import json
import os
import re
import i18n_source_address as addr
_I18N_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'i18n')
_AEXE_DIR = os.path.join(_I18N_DIR, '_aexe_template')
_LOCATION_CITYDATA_MAP = os.path.join(_I18N_DIR, 'location_citydata_map.json')
_PH_OC_SOURCE_MAP = os.path.join(_I18N_DIR, 'placeholder_values_oc_source.json')
_BE_PREFIX = 'template_dat_building_entry.'
_NNC_PREFIX = 'npc_name_chunks.chunks.'

def building_entry_source_id(legacy_id: str) -> str | None:
    if not legacy_id.startswith(_BE_PREFIX):
        return None
    rest = legacy_id[len(_BE_PREFIX):]
    if '.copy' not in rest:
        return None
    block, tail = rest.rsplit('.copy', 1)
    parts = tail.split('.')
    if len(parts) != 2:
        return None
    try:
        copy_i, idx_i = (int(parts[0]), int(parts[1]))
    except ValueError:
        return None
    return addr.template_id(block, idx_i, copy=copy_i)

def npc_name_chunks_source_id(legacy_id: str) -> str | None:
    if not legacy_id.startswith(_NNC_PREFIX):
        return None
    parts = legacy_id[len(_NNC_PREFIX):].split('.')
    if len(parts) != 2:
        return None
    try:
        chunk_i, idx_i = (int(parts[0]), int(parts[1]))
    except ValueError:
        return None
    return addr.namechnk_id(chunk_i, idx_i)
_INF_PREFIX = 'inf_text.'
_RIDDLE_SUBS = ('question', 'correct', 'wrong')

def inf_text_source_id(legacy_id: str) -> str | None:
    if not legacy_id.startswith(_INF_PREFIX):
        return None
    rest = legacy_id[len(_INF_PREFIX):]
    m = re.match('^_CHARGEN_Q_(\\d+)__0\\.(0|display)$', rest)
    if m:
        base = addr.question_id(int(m.group(1)))
        return base if m.group(2) == '0' else base + ':display'
    if rest.startswith('_CHARGEN_'):
        import arena_regen
        sid = arena_regen.chargen_ui_source_id(rest)
        if sid is not None:
            return sid
        m = re.match('^(_CHARGEN_\\w*?)_(\\d+)\\.(0|display)$', rest)
        if m:
            base = addr.inf_id(m.group(1), int(m.group(2)))
            return base if m.group(3) == '0' else base + ':display'
        return None
    if rest.startswith('TEMPLATE_DAT'):
        return None
    if '.INF_' not in rest:
        return None
    name, tail = rest.split('.INF_', 1)
    parts = tail.split('.')
    if len(parts) != 2:
        return None
    idx_s, sub = parts
    try:
        idx_i = int(idx_s)
    except ValueError:
        return None
    base = addr.inf_id(name + '.INF', idx_i)
    if sub == '0':
        return base
    if sub in _RIDDLE_SUBS:
        return base + ':' + sub
    return None
_NPCD_PREFIX = 'npc_dialog.'
_AKEY_RE = re.compile('^A\\d')

def npc_dialog_source_id(legacy_id: str) -> str | None:
    if not legacy_id.startswith(_NPCD_PREFIX):
        return None
    rest = legacy_id[len(_NPCD_PREFIX):]
    if _AKEY_RE.match(rest):
        return _akey_source_id(rest)
    if '.' not in rest:
        return None
    block, var = rest.rsplit('.', 1)
    try:
        var_i = int(var)
    except ValueError:
        return None
    return addr.template_id(block, var_i)

def _akey_source_id(akey: str) -> str | None:
    import arena_regen
    return arena_regen.akey_structural_source_id(akey, set(_aexe_template('akey')))
_AEXE_CATEGORIES = frozenset({'calendar', 'chargen_provinces', 'classes', 'location_types', 'protect_locations', 'races', 'titles', 'spells', 'equipment_suffixes', 'item_enchantments', 'item_materials', 'monsters', 'equipment', 'character', 'mages', 'dungeon', 'items', 'settlement_types', 'chargen_race_descriptions', 'pronouns', 'relations', 'ask_about_menu', 'status_buffer_text', 'descriptors', 'status_terms', 'npc_traits'})
_aexe_cache: dict[str, dict] = {}

def _owned_i18n_json(disk_path: str, seed_rel: str) -> dict:
    try:
        with open(disk_path, encoding='utf-8') as fh:
            return json.load(fh)
    except OSError:
        pass
    try:
        import app_resources
        txt = app_resources.read_text(seed_rel)
        if txt is not None:
            return json.loads(txt)
    except Exception:
        pass
    return {}

def _aexe_template(category: str) -> dict:
    if category not in _aexe_cache:
        _aexe_cache[category] = _owned_i18n_json(os.path.join(_AEXE_DIR, category + '.json'), f'i18n/_aexe_template/{category}.json')
    return _aexe_cache[category]
_PUBLIC_BUILTIN_SURFACES = {'generic.yes': 'Yes', 'generic.no': 'No'}
_PUBLIC_BUILTIN_LEGACY = {'mages.Yes': 'generic.yes', 'mages.No': 'generic.no'}

def public_builtin_source_id(legacy_id: str) -> str | None:
    key = _PUBLIC_BUILTIN_LEGACY.get(legacy_id)
    return addr.public_builtin_id(key) if key else None

def public_builtin_surfaces() -> dict:
    return {addr.public_builtin_id(k): v for k, v in _PUBLIC_BUILTIN_SURFACES.items()}
_MAGES_MAGIC_ITEM = {'mages.Mark of Light': (0, 'misc', 0), 'mages.Mark of Stamina': (0, 'defensive', 0), "mages.Crystal of Wizard's Fire": (1, 'attack', 0)}
_MAGIC_ITEM_TABLE = {'attack': 'equipment.attack_spell_names', 'defensive': 'equipment.defensive_spell_names', 'misc': 'equipment.misc_spell_names'}

def mages_magic_item_source_id(legacy_id: str) -> str | None:
    rec = _MAGES_MAGIC_ITEM.get(legacy_id)
    return addr.magic_item_id(*rec) if rec else None
_MAGES_MATERIAL_ITEM = {'mages.Mithril Belt': (5, 1)}

def mages_material_item_source_id(legacy_id: str) -> str | None:
    rec = _MAGES_MATERIAL_ITEM.get(legacy_id)
    return addr.material_item_id(*rec) if rec else None

def compose_material_item(material_idx: int, acc_idx: int, tables: dict) -> str | None:
    mats = tables.get('equipment.material_names')
    accs = tables.get('equipment.enhancement_item_names')
    if not mats or not accs:
        return None
    if 0 <= material_idx < len(mats) and 0 <= acc_idx < len(accs):
        m, a = (mats[material_idx], accs[acc_idx])
        if isinstance(m, str) and isinstance(a, str) and m and a:
            return f'{m} {a}'
    return None

def material_item_surfaces(tables: dict) -> dict:
    out = {}
    for rec in set(_MAGES_MATERIAL_ITEM.values()):
        surf = compose_material_item(rec[0], rec[1], tables)
        if surf:
            out[addr.material_item_id(*rec)] = surf
    return out

def compose_magic_item(item_idx: int, spell_kind: str, spell_idx: int, tables: dict) -> str | None:
    items = tables.get('equipment.spellcasting_item_names')
    spells = tables.get(_MAGIC_ITEM_TABLE.get(spell_kind, ''))
    if not items or not spells:
        return None
    if 0 <= item_idx < len(items) and 0 <= spell_idx < len(spells):
        item, spell = (items[item_idx], spells[spell_idx])
        if isinstance(item, str) and isinstance(spell, str) and item and spell:
            return f'{item} {spell}'
    return None

def magic_item_surfaces(tables: dict) -> dict:
    out = {}
    for rec in set(_MAGES_MAGIC_ITEM.values()):
        surf = compose_magic_item(rec[0], rec[1], rec[2], tables)
        if surf:
            out[addr.magic_item_id(*rec)] = surf
    return out

def _mages_spell_effect_struct() -> dict:
    if not hasattr(_mages_spell_effect_struct, '_cache'):
        import spell_effect_structure as ses
        m = {f'mages.{name}': struct for struct, name in ses._VERIFIED_COMPOSITE.items()}
        m['mages.Transfer Attribute'] = (13, 0)
        _mages_spell_effect_struct._cache = m
    return _mages_spell_effect_struct._cache

def mages_spell_effect_source_id(legacy_id: str) -> str | None:
    struct = _mages_spell_effect_struct().get(legacy_id)
    if struct is None:
        return None
    import spell_effect_structure as ses
    surf = ses.surface_for(struct[0], struct[1])
    if not surf or not surf[1].startswith('verified'):
        return None
    return addr.spell_effect_id(struct[0], struct[1])

def spell_effect_surfaces() -> dict:
    import spell_effect_structure as ses
    out = {}
    for struct in set(_mages_spell_effect_struct().values()):
        surf = ses.surface_for(struct[0], struct[1])
        if surf and surf[1].startswith('verified'):
            out[addr.spell_effect_id(struct[0], struct[1])] = surf[0]
    return out
_MAGES_SPELLSG65_INDEX = {'Stamina': 0, 'Sanctuary': 1, 'Wanderlight': 3, 'Wizard Lock': 4, 'Orc Strength': 5, "Wizard's Fire": 6, 'Strength Leech': 11, 'Ice Bolt': 12, 'Resist Fire': 14, 'Resist Cold': 15, 'Fireball': 16, 'Earth Wall': 17, "Witch's Curse": 19, 'Cure Poison': 21, 'Resist Shock': 23, 'Ice Storm': 26, 'Heal True': 33, 'Fire Storm': 35, 'Spell Shield': 36, 'Free Action': 37, "Troll's Blood": 41, 'Cause Disease': 59, 'Cure Disease': 60}

def mages_spellsg65_source_id(legacy_id: str) -> str | None:
    if not legacy_id.startswith('mages.'):
        return None
    name = legacy_id[len('mages.'):]
    idx = _MAGES_SPELLSG65_INDEX.get(name)
    if idx is None:
        return None
    return addr.spellsg65_id(idx)
_ITEM_MATERIALS_ARMOR_PREFIX = {'item_materials.0.0': 'leather', 'item_materials.1.0': 'chain', 'item_materials.2.0': 'plate'}

def item_materials_armor_prefix_source_id(legacy_id: str) -> str | None:
    material = _ITEM_MATERIALS_ARMOR_PREFIX.get(legacy_id)
    return addr.armor_prefix_id(material) if material else None

def derive_armor_prefix(material: str, comp_table: list, base_table: list) -> str | None:
    if not comp_table or not base_table:
        return None
    full, part = (comp_table[0], base_table[0])
    if isinstance(full, str) and isinstance(part, str) and full.endswith(part):
        prefix = full[:len(full) - len(part)].strip()
        return prefix or None
    return None

def aexe_source_id(category: str, legacy_id: str) -> str | None:
    rec = _aexe_template(category).get(legacy_id)
    if not isinstance(rec, dict):
        return None
    src_table = rec.get('src_table')
    src_index = rec.get('src_index')
    if not src_table or src_index is None:
        return None
    if '.' in src_table:
        group, table = src_table.split('.', 1)
    else:
        group, table = (category, src_table)
    return addr.aexe_table_id(group, table, src_index)
_RESOLVERS = {'template_dat_building_entry': building_entry_source_id, 'npc_name_chunks': npc_name_chunks_source_id, 'inf_text': inf_text_source_id, 'npc_dialog': npc_dialog_source_id}
_loc_cd_cache: dict | None = None

def _location_citydata_map() -> dict:
    global _loc_cd_cache
    if _loc_cd_cache is None:
        try:
            with open(_LOCATION_CITYDATA_MAP, encoding='utf-8') as fh:
                _loc_cd_cache = json.load(fh).get('map', {})
        except OSError:
            _loc_cd_cache = {}
    return _loc_cd_cache

def location_citydata_source_id(legacy_id: str) -> str | None:
    return _location_citydata_map().get(legacy_id)
_ph_oc_cache: dict | None = None

def _ph_oc_source_map() -> dict:
    global _ph_oc_cache
    if _ph_oc_cache is None:
        try:
            with open(_PH_OC_SOURCE_MAP, encoding='utf-8') as fh:
                _ph_oc_cache = {k: v for k, v in json.load(fh).items() if not k.startswith('_')}
        except OSError:
            _ph_oc_cache = {}
    return _ph_oc_cache

def placeholder_values_source_id(legacy_id: str) -> str | None:
    rec = _ph_oc_source_map().get(legacy_id)
    if not isinstance(rec, dict):
        return None
    block = rec.get('block')
    index = rec.get('index')
    if block is None or index is None:
        return None
    return addr.template_id(block, int(index))

def placeholder_values_oc_keys() -> set[str]:
    return set(_ph_oc_source_map().keys())
_PH_DERIVED_MAP = os.path.join(_I18N_DIR, 'placeholder_values_derived_map.json')
_ph_derived_cache: dict | None = None

def _ph_derived_map() -> dict:
    global _ph_derived_cache
    if _ph_derived_cache is None:
        try:
            with open(_PH_DERIVED_MAP, encoding='utf-8') as fh:
                _ph_derived_cache = {k: v for k, v in json.load(fh).items() if not k.startswith('_')}
        except OSError:
            _ph_derived_cache = {}
    return _ph_derived_cache

def placeholder_redirect_target(legacy_id: str):
    rec = _ph_derived_map().get(legacy_id)
    if isinstance(rec, dict):
        tid = rec.get('target_id')
        return int(tid) if tid is not None else None
    return None

def placeholder_derived_keys() -> set[str]:
    return set(_ph_derived_map().keys())

def location_citydata_keys() -> set[str]:
    return set(_location_citydata_map().keys())

def source_id_for(category: str, legacy_id: str) -> str | None:
    if category == 'mages':
        sid = public_builtin_source_id(legacy_id)
        if sid:
            return sid
        sid = mages_spellsg65_source_id(legacy_id)
        if sid:
            return sid
        sid = mages_spell_effect_source_id(legacy_id)
        if sid:
            return sid
        sid = mages_magic_item_source_id(legacy_id)
        if sid:
            return sid
        sid = mages_material_item_source_id(legacy_id)
        if sid:
            return sid
        return aexe_source_id(category, legacy_id)
    if category == 'item_materials':
        sid = item_materials_armor_prefix_source_id(legacy_id)
        if sid:
            return sid
        return aexe_source_id(category, legacy_id)
    if category in _AEXE_CATEGORIES:
        return aexe_source_id(category, legacy_id)
    if category == 'location_citydata':
        return location_citydata_source_id(legacy_id)
    if category == 'placeholder_values':
        return placeholder_values_source_id(legacy_id)
    fn = _RESOLVERS.get(category)
    return fn(legacy_id) if fn else None

def supported_categories() -> set[str]:
    return set(_RESOLVERS.keys()) | set(_AEXE_CATEGORIES) | {'location_citydata'}
__all__ = ['source_id_for', 'building_entry_source_id', 'supported_categories']
