from __future__ import annotations
import logging
import re
import assist_settings as settings
import i18n_helper as i18n
from panel_mode_resolver import SCREEN_PANEL_PRIORITY, closing_panel_mode, screen_panel_mode
from top_level.top_level_dispatcher import current_state as _current_top_level
_log = logging.getLogger('char_screen_module')
SCREEN_PANEL_OWNERS: dict[str, str] = {'equipment': 'equipment', 'spellbook': 'spellbook', 'spell_detail': 'spell_detail'}
SCREEN_PANEL_OWNER_SET = frozenset(SCREEN_PANEL_OWNERS.values())
_STAFF_PIECES_RE = re.compile('^\\s*Staff\\s+Pieces\\s*\\((\\d+)\\)', re.I)

def read_staff_pieces_row(w) -> dict | None:
    try:
        from arena_bridge import NPC_DIALOG_OFFSET
        raw = w._analyzer.read_bytes(w._anchor + NPC_DIALOG_OFFSET, 64)
    except (OSError, AttributeError, ImportError):
        return None
    text = raw.split(b'\x00', 1)[0].decode('ascii', errors='replace').strip()
    m = _STAFF_PIECES_RE.match(text)
    if not m:
        return None
    count = int(m.group(1))
    ja = ''
    try:
        import npc_dialog_lookup as ndl
        hit = ndl.lookup(text)
        if hit is not None:
            ja = ndl.format_japanese(hit[0], hit[1]) or ''
    except Exception:
        ja = ''
    return {'en': text, 'ja': ja, 'equipped': False, 'is_unidentified': False, 'can_equip': False, 'slot_label': '', 'weight': None, 'condition': None, 'uses': None, 'item_type': None, 'effect': f'{count} 個'}

def show_equipment_page(w) -> None:
    item_data: list = []
    title = '装備品一覧'
    try:
        from class_equip_reader import can_equip_item, read_class_equip_rules
        from inventory_reader import INV_SLOTS, read_equipment_items_with_status
        import dungeon_msg_lookup as dml
        rules = read_class_equip_rules(w._analyzer, w._anchor)
        inventory_ok, items_raw = read_equipment_items_with_status(w._analyzer, w._anchor)
        if inventory_ok:
            title = '%s  %d / %d' % (title, len(items_raw), INV_SLOTS)
        item_data = [{'en': it['en'], 'ja': dml.lookup_item(it['en']), 'equipped': it['equipped'], 'is_unidentified': it['is_unidentified'], 'can_equip': can_equip_item(it, rules), 'slot_label': it['slot_label'], 'weight': it['weight'], 'condition': it['condition'], 'uses': it.get('uses'), 'item_type': it.get('item_type'), 'effect': f"{it['count']} 個" if it.get('count') is not None else it['effect']} for it in items_raw]
        _staff = read_staff_pieces_row(w)
        if _staff is not None:
            item_data.append(_staff)
    except Exception:
        _log.exception('equipment read failed')
    w._ui_router.propose_equipment_list('equipment', title, item_data, priority=SCREEN_PANEL_PRIORITY, reason='screen:equipment')

def show_spell_detail_page(w) -> None:
    try:
        from spell_reader import read_spell_detail
        import dungeon_msg_lookup as dml
        data = read_spell_detail(w._analyzer, w._anchor)
        data['name_ja'] = dml.lookup_spell(data.get('name', '')) or ''
    except Exception:
        _log.exception('spell_detail read failed')
        data = {}
    text_en = (data.get('text_en') or '').strip()
    spell_name = (data.get('name') or '').strip()
    last_name = getattr(w, '_spell_detail_last_accepted_name', '')
    last_text = getattr(w, '_spell_detail_last_accepted_text', '')
    text_is_stale_prev = bool(text_en) and spell_name and (spell_name != last_name) and (text_en == last_text)
    text_is_name_residue = bool(text_en) and text_en == spell_name
    text_is_invalid = not text_en or text_is_name_residue or text_is_stale_prev
    if text_is_invalid:
        data['text_en'] = ''
        data['text_ja'] = ''
        w._spell_detail_text_ready = False
    else:
        w._spell_detail_text_ready = True
        w._spell_detail_last_accepted_name = spell_name
        w._spell_detail_last_accepted_text = text_en
    w._ui_router.propose_spell_detail('spell_detail', data, priority=SCREEN_PANEL_PRIORITY, reason='screen:spell_detail')

def show_spellbook_page(w) -> None:
    try:
        from spell_reader import read_spellbook_items
        import dungeon_msg_lookup as dml
        items_raw = read_spellbook_items(w._analyzer, w._anchor)
        item_data = [{'en': it['en'], 'ja': dml.lookup_spell(it['en'])} for it in items_raw]
    except Exception:
        _log.exception('spellbook read failed')
        item_data = []
    w._ui_router.propose_spellbook_list('spellbook', item_data, 'Spell Book', i18n.tr('screen.spellbook'), list_title_ja=i18n.tr('spellbook.list_title'), priority=SCREEN_PANEL_PRIORITY, reason='screen:spellbook')

def _closing_panel_mode(w) -> str | None:
    try:
        return closing_panel_mode(current_mode=w._tab_translate.panel_mode(), img_name=getattr(w, '_img_name_prev', '') or '', screen_id=getattr(w, '_screen_id_prev', '') or '', top_level=_current_top_level(w), fallback_setting=settings.get('translate_fallback_screen', 'map'))
    except AttributeError:
        return 'translate'

def release_screen_panel_owner(w, screen_id: str) -> None:
    next_owner = SCREEN_PANEL_OWNERS.get(screen_id, '')
    try:
        current = w._ui_router.current_owner()
    except AttributeError:
        return
    if current not in SCREEN_PANEL_OWNER_SET or current == next_owner:
        return
    mode = screen_panel_mode(screen_id)
    if mode is None:
        mode = _closing_panel_mode(w)
    w._ui_router.release_if_owner(current, mode=mode, priority=SCREEN_PANEL_PRIORITY, reason='screen:%s_exit' % current)

def on_screen_id_changed(w, screen_id: str) -> None:
    release_screen_panel_owner(w, screen_id)
    if screen_id == 'equipment':
        show_equipment_page(w)
    elif screen_id == 'spellbook':
        show_spellbook_page(w)
    elif screen_id == 'spell_detail':
        show_spell_detail_page(w)

def reset_spell_detail_markers(w) -> None:
    w._spell_detail_marker = None
    w._spell_detail_text_marker = None
    w._spell_detail_text_ready = True
_CHAR_SCREENS = frozenset({'spell_detail', 'equipment', 'spellbook', 'race_select'})

def poll_char_screen_pages(w, screen_id_stable) -> None:
    try:
        panel = w._tab_translate.panel_mode()
        if screen_id_stable == 'spell_detail':
            try:
                marker = w._analyzer.read_bytes(w._anchor + 22554, 16)
            except (OSError, AttributeError):
                marker = b''
            try:
                text_marker = w._analyzer.read_bytes(w._anchor + 4164, 96)
            except (OSError, AttributeError):
                text_marker = b''
            marker_prev = getattr(w, '_spell_detail_marker', None)
            text_marker_prev = getattr(w, '_spell_detail_text_marker', None)
            text_ready = getattr(w, '_spell_detail_text_ready', True)
            if panel != 'spell_detail' or marker != marker_prev or text_marker != text_marker_prev or (not text_ready):
                w._spell_detail_marker = marker
                w._spell_detail_text_marker = text_marker
                show_spell_detail_page(w)
        elif screen_id_stable == 'equipment':
            try:
                _inv_marker = w._analyzer.read_bytes(w._anchor + 530, 19 * 40)
            except (OSError, AttributeError):
                _inv_marker = None
            try:
                _staff_marker = w._analyzer.read_bytes(w._anchor + 4164, 64)
            except (OSError, AttributeError):
                _staff_marker = None
            if panel != 'equipment' or _inv_marker != w._equipment_marker or _staff_marker != getattr(w, '_equipment_staff_marker', None):
                w._equipment_marker = _inv_marker
                w._equipment_staff_marker = _staff_marker
                show_equipment_page(w)
            reset_spell_detail_markers(w)
        elif screen_id_stable == 'spellbook':
            if panel != 'equipment':
                show_spellbook_page(w)
            reset_spell_detail_markers(w)
        elif screen_id_stable == 'race_select':
            reset_spell_detail_markers(w)
        else:
            if getattr(w, '_char_screen_stable_prev', None) in _CHAR_SCREENS and panel in ('race_list', 'equipment', 'spell_detail'):
                w._ui_router.set_panel_mode('translate', reason='screen:exit')
            reset_spell_detail_markers(w)
        w._char_screen_stable_prev = screen_id_stable
    except (AttributeError, RuntimeError):
        pass
__all__ = ['SCREEN_PANEL_OWNERS', 'SCREEN_PANEL_OWNER_SET', 'read_staff_pieces_row', 'show_equipment_page', 'show_spell_detail_page', 'show_spellbook_page', 'release_screen_panel_owner', 'on_screen_id_changed', 'reset_spell_detail_markers', 'poll_char_screen_pages']
