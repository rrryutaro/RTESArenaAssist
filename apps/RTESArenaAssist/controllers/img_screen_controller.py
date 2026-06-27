import logging
import assist_settings as settings
from top_level.top_level_dispatcher import current_state as _current_top_level
from top_level import pregame_render as _pregame_render
from normal_play.npc_conversation_module import NPC_CONVERSATION_OWNER
_log = logging.getLogger('img_screen_controller')
TRAVEL_SEARCH_OWNER = 'travel_search'

class ImgScreenController:

    def __init__(self, window):
        self._w = window

    def _set_panel_mode(self, mode: str) -> None:
        self._w._ui_router.set_panel_mode(mode)

    def on_img_name_changed(self, img_name: str) -> None:
        _log.info('img_name changed: %r', img_name)
        img_upper = (img_name or '').upper()
        top = _current_top_level(self._w)
        prev_screen = getattr(self._w, '_screen_id_prev', None)
        from top_level.top_level_node import classify_top_level
        _l1_next, _ = classify_top_level(top, img_upper)
        if _l1_next == 'pregame' and top != 'pregame':
            try:
                via = 'system_menu' if prev_screen == 'system_menu' else top
                self._w._transition_top_level('pregame', f'{via} → {img_upper}')
                self._w._pregame_loadsave_seen = False
            except AttributeError:
                pass
        elif _l1_next == 'chargen' and top == 'pregame':
            try:
                self._w._transition_top_level('chargen', 'EVLINTRO.XMI')
                self._w._pregame_loadsave_seen = False
            except AttributeError:
                pass
        if img_upper == 'LOADSAVE.IMG' and _current_top_level(self._w) == 'pregame':
            try:
                self._w._pregame_loadsave_seen = True
            except AttributeError:
                pass
        if img_upper.endswith('.XMI'):
            if _current_top_level(self._w) == 'chargen':
                self._w._chargen_opening_text_prev = ''
            try:
                self._w._ui_router.clear_display('')
            except AttributeError:
                pass
            return
        if img_name == 'MENU.IMG':
            self._show_menu_screen()
        elif img_name == 'LOADSAVE.IMG':
            self._show_load_screen()
        elif img_name.startswith('INTRO') and img_name.endswith('.IMG'):
            self._show_newgame_slide(img_name)
        elif img_name == 'PARCH.CIF':
            self._w._set_chargen_ui_state(True)
        elif img_name in ('QUOTE.IMG', 'SCROLL01.IMG', 'SCROLL02.IMG'):
            self._show_startup_intro(img_name)
        elif img_name == 'MRSHIRT.IMG':
            return
        elif img_name in ('EQUIP.IMG', 'MPANTS.IMG'):
            return
        elif img_name == 'POPUP11.IMG':
            return
        elif img_name.startswith('CHARBK') and img_name.endswith('.IMG'):
            return
        else:
            self._w._newgame_layout_pushed = False
            self._w._startup_layout_pushed = False
            try:
                if self._w._tab_translate.panel_mode() == 'load_screen':
                    self._set_panel_mode('translate')
            except AttributeError:
                pass
            self._w._set_chargen_ui_state(False)
    _NPC_DIALOG_RELATED_SCREENS = frozenset({'npc_dialog'})

    def on_screen_id_changed(self, screen_id: str) -> None:
        _log.info('screen_id changed: %r', screen_id)
        if _current_top_level(self._w) == 'normal-play' and screen_id not in self._NPC_DIALOG_RELATED_SCREENS:
            self._reset_npc_dialog_display(clear_display=False)
        if screen_id == 'equipment':
            self._show_equipment_screen()
        elif screen_id == 'spellbook':
            self._show_spellbook_screen()
        elif screen_id == 'spell_detail':
            self._show_spell_detail_screen()

    def _reset_npc_dialog_display(self, *, clear_display: bool=True) -> None:
        try:
            if clear_display:
                clear_mode = self._npc_clear_panel_mode()
                if self._w._tab_translate is not None:
                    self._w._ui_router.clear_display('', mode=clear_mode, clear_place_list=True, allowed_current_owners=('', 'npc_dialog', NPC_CONVERSATION_OWNER, 'npc_message'))
            self._w._ask_about_menu_active_prev = False
            self._w._ask_about_current_ptr_prev = -1
            self._w._popup11_list_state_prev = ''
            self._w._popup11_exit_pending_ask_about = False
            self._w._popup11_place_response_lock = None
            self._w._npc_dialog_text_prev = ''
        except (AttributeError, RuntimeError) as exc:
            _log.debug('_reset_npc_dialog_display skipped: %s', exc)

    def _npc_clear_panel_mode(self) -> str | None:
        try:
            mode = self._w._tab_translate.panel_mode()
            img_name_now = (getattr(self._w, '_img_name_prev', '') or '').upper()
            if mode == 'load_screen' and img_name_now == 'LOADSAVE.IMG':
                return None
            screen_id_now = getattr(self._w, '_screen_id_prev', '') or ''
            if mode == 'choose_attributes' and screen_id_now in ('status_page', 'bonus_screen'):
                return 'choose_attributes'
            if _current_top_level(self._w) == 'normal-play':
                fallback = settings.get('translate_fallback_screen', 'map')
                if fallback == 'map':
                    return 'fallback_map'
                if fallback == 'status':
                    return 'fallback_status'
            return 'translate'
        except AttributeError:
            return 'translate'

    def _show_startup_intro(self, img_name: str) -> None:
        _pregame_render.show_startup_intro(self._w, img_name)

    def _show_menu_screen(self) -> None:
        _pregame_render.show_menu_screen(self._w)

    def _show_load_screen(self) -> None:
        _pregame_render.show_load_screen(self._w)

    def _show_equipment_screen(self) -> None:
        item_data: list = []
        title = '装備品一覧'
        try:
            import arena_data
            import assist_settings as settings
            from inventory_reader import read_equipment_items
            import dungeon_msg_lookup as dml
            json_class_id: int | None = None
            is_hypothesis = True
            try:
                play_cls_id = self._w._analyzer.read_bytes(self._w._anchor + 425, 1)[0]
                play_cls_map = settings.get('arena_play_class_id_map', {}) or {}
                class_en = play_cls_map.get(str(play_cls_id))
                if class_en:
                    cls_data = arena_data.get_class_by_name(class_en)
                    if cls_data:
                        json_class_id = cls_data['id']
                        is_hypothesis = bool(cls_data.get('_hypothesis_note'))
            except Exception:
                pass

            def _can_equip(it: dict) -> bool | None:
                if json_class_id is None:
                    return None
                t = it['item_type']
                if t == 'weapon':
                    return arena_data.can_class_use_weapon(json_class_id, it['slot_id'])
                if t == 'armor':
                    return arena_data.can_class_use_armor(json_class_id, it['armor_material_id'])
                if t == 'shield':
                    return arena_data.can_class_use_shield(json_class_id, it['slot_id'])
                return True
            items_raw = read_equipment_items(self._w._analyzer, self._w._anchor)
            item_data = [{'en': it['en'], 'ja': dml.lookup_item(it['en']), 'equipped': it['equipped'], 'is_unidentified': it['is_unidentified'], 'can_equip': _can_equip(it), 'slot_label': it['slot_label'], 'weight': it['weight'], 'condition': it['condition'], 'effect': it['effect']} for it in items_raw]
            title = '装備品一覧'
        except Exception:
            _log.exception('equipment read failed')
        self._w._ui_router.propose_equipment_list('equipment', title, item_data, priority=30, reason='screen:equipment')

    def _show_spell_detail_screen(self) -> None:
        try:
            from spell_reader import read_spell_detail
            import dungeon_msg_lookup as dml
            data = read_spell_detail(self._w._analyzer, self._w._anchor)
            data['name_ja'] = dml.lookup_spell(data.get('name', '')) or ''
        except Exception:
            _log.exception('spell_detail read failed')
            data = {}
        text_en = (data.get('text_en') or '').strip()
        spell_name = (data.get('name') or '').strip()
        last_name = getattr(self._w, '_spell_detail_last_accepted_name', '')
        last_text = getattr(self._w, '_spell_detail_last_accepted_text', '')
        text_is_stale_prev = bool(text_en) and spell_name and (spell_name != last_name) and (text_en == last_text)
        text_is_name_residue = bool(text_en) and text_en == spell_name
        text_is_invalid = not text_en or text_is_name_residue or text_is_stale_prev
        if text_is_invalid:
            data['text_en'] = ''
            data['text_ja'] = ''
            self._w._spell_detail_text_ready = False
        else:
            self._w._spell_detail_text_ready = True
            self._w._spell_detail_last_accepted_name = spell_name
            self._w._spell_detail_last_accepted_text = text_en
        self._w._ui_router.propose_spell_detail('spell_detail', data, priority=30, reason='screen:spell_detail')

    def _show_spellbook_screen(self) -> None:
        try:
            from spell_reader import read_spellbook_items
            import dungeon_msg_lookup as dml
            items_raw = read_spellbook_items(self._w._analyzer, self._w._anchor)
            item_data = [{'en': it['en'], 'ja': dml.lookup_spell(it['en'])} for it in items_raw]
        except Exception:
            _log.exception('spellbook read failed')
            item_data = []
        self._w._ui_router.propose_equipment_list('spellbook', '習得呪文一覧', item_data, priority=30, reason='screen:spellbook')

    def _show_newgame_slide(self, img_name: str) -> None:
        _pregame_render.show_newgame_slide(self._w, img_name)

    def _restore_translate_mode(self) -> None:
        try:
            mode = self._w._tab_translate.panel_mode()
            if mode == 'translate':
                return
            img_name_now = (getattr(self._w, '_img_name_prev', '') or '').upper()
            if mode == 'load_screen' and img_name_now == 'LOADSAVE.IMG':
                return
            screen_id_now = getattr(self._w, '_screen_id_prev', '') or ''
            if mode == 'choose_attributes' and screen_id_now in ('status_page', 'bonus_screen'):
                return
            self._set_panel_mode('translate')
        except AttributeError:
            pass

    def _show_npc_dialog(self, text_override: str | None=None) -> None:
        try:
            _tav = getattr(self._w, '_tavern_session', None)
            _tem = getattr(self._w, '_temple_session', None)
            if _tav is not None and _tav.is_active() or (_tem is not None and _tem.is_active()):
                return
        except Exception:
            pass
        try:
            import npc_dialog_lookup as ndl
            self._restore_translate_mode()
            text = (text_override or '').strip()
            if not text:
                from popup11_response_reader import read_response_candidate
                cand = read_response_candidate(self._w._analyzer, self._w._anchor)
                text = cand.text if cand else ''
            if not text:
                self._w._ui_router.clear_if_owner(NPC_CONVERSATION_OWNER, mode=self._npc_clear_panel_mode(), clear_place_list=True)
                return
            result = ndl.lookup(text)
            if result:
                ja_template, placeholders = result
                ja_text = ndl.format_japanese(ja_template, placeholders)
            else:
                ja_text = ''
            self._w._ui_router.update_translation(NPC_CONVERSATION_OWNER, text, ja_text, clear_place_list=True, speech_role='conversation')
        except Exception:
            _log.exception('_show_npc_dialog failed')

    def _show_ask_about_menu(self) -> None:
        try:
            _tav = getattr(self._w, '_tavern_session', None)
            _tem = getattr(self._w, '_temple_session', None)
            if _tav is not None and _tav.is_active() or (_tem is not None and _tem.is_active()):
                return
        except Exception:
            pass
        try:
            from arena_bridge import read_ask_about_menu
            from ask_about_menu_parser import build_display, build_display_sub, build_panel_display, build_panel_display_sub, parse_menu
            self._restore_translate_mode()
            raw = read_ask_about_menu(self._w._analyzer, self._w._anchor)
            parsed = parse_menu(raw)
            active_sub_title = self._detect_active_sub_menu_title(parsed)
            _log.info('_show_ask_about_menu: active_sub_title=%r', active_sub_title)
            if active_sub_title:
                en_tab, ja_tab = build_display_sub(parsed, sub_title=active_sub_title)
            else:
                en_tab, ja_tab = build_display(parsed, include_sub=False)
            en_panel = ja_panel = ''
            if self._w._layout_translate_panel is not None:
                if active_sub_title:
                    en_panel, ja_panel = build_panel_display_sub(parsed, sub_title=active_sub_title)
                else:
                    en_panel, ja_panel = build_panel_display(parsed)
            self._w._ui_router.update_translation(NPC_CONVERSATION_OWNER, en_tab, ja_tab, panel_en=en_panel, panel_ja=ja_panel)
        except Exception:
            _log.exception('_show_ask_about_menu failed')

    def _detect_active_sub_menu_title(self, parsed: dict) -> str:
        try:
            from popup11_list_detector import read_active_menu_marker
            from ask_about_menu_parser import detect_active_sub_menu_title
            marker = read_active_menu_marker(self._w._analyzer, self._w._anchor)
            title = detect_active_sub_menu_title(parsed, marker)
            _log.info('_detect_active_sub_menu_title: marker=%r title=%r', marker, title)
            return title
        except Exception:
            _log.exception('_detect_active_sub_menu_title failed')
            return ''

    def _show_where_is_list(self) -> None:
        try:
            _tav = getattr(self._w, '_tavern_session', None)
            _tem = getattr(self._w, '_temple_session', None)
            if _tav is not None and _tav.is_active() or (_tem is not None and _tem.is_active()):
                return
        except Exception:
            pass
        try:
            from popup11_list_detector import POPUP11_ITEM_COUNT_OFFSET, _read_u8
            from popup11_list_parser import parse_where_is_list
            from ask_about_menu_parser import translate
            item_count = _read_u8(self._w._analyzer, self._w._anchor + POPUP11_ITEM_COUNT_OFFSET) or 0
            items_en = parse_where_is_list(self._w._analyzer, self._w._anchor, item_count)
            if not items_en:
                return
            item_data = [{'en': opt_en, 'ja': self._translate_where_is_item(opt_en, translate)} for opt_en in items_en]
            title_en = 'Where is...'
            title_ja = translate(title_en)
            self._w._ui_router.update_place_list(NPC_CONVERSATION_OWNER, item_data, title='', panel_en=title_en, panel_ja=title_ja)
        except Exception:
            _log.exception('_show_where_is_list failed')

    @staticmethod
    def _translate_where_is_item(opt_en: str, translate) -> str:
        ja = translate(opt_en)
        if ja and ja != opt_en:
            return ja
        try:
            from location_lookup import lookup as _loc_lookup
            loc = _loc_lookup(opt_en)
            if loc:
                return loc
        except Exception:
            pass
        return ja

    def _show_travel_city_list(self) -> None:
        try:
            from travel_search_list_reader import read_travel_city_list
            from location_lookup import lookup as _loc_lookup
            items_en = read_travel_city_list(self._w._analyzer, self._w._anchor)
            if not items_en:
                return
            item_data = [{'en': en, 'ja': _loc_lookup(en) or ''} for en in items_en]
            self._w._ui_router.update_place_list(TRAVEL_SEARCH_OWNER, item_data, title='', panel_en='', panel_ja='')
        except Exception:
            _log.exception('_show_travel_city_list failed')
    _SEARCH_PROMPT_EN = 'Enter the name of the city or press Enter key for a list.'
    _SEARCH_PROMPT_JA = '都市名を入力するか、Enter キーで一覧を表示します。'

    def _read_travel_search_prompt(self) -> tuple[str, str]:
        clean_en, ja = (self._SEARCH_PROMPT_EN, self._SEARCH_PROMPT_JA)
        try:
            from arena_logic import read_live_buffer
            from viewer_constants import NPC_DIALOG_OFFSET, NPC_DIALOG_MAXLEN
            import npc_dialog_lookup as _ndl
            raw = read_live_buffer(self._w._analyzer, self._w._anchor + NPC_DIALOG_OFFSET, NPC_DIALOG_MAXLEN)
            res = _ndl.lookup_prompt_prefix_tolerant(raw)
            if res:
                lk_en, lk_ja = res
                return (lk_en or clean_en, lk_ja or ja)
        except Exception:
            pass
        return (clean_en, ja)

    def _show_travel_search_prompt(self) -> None:
        try:
            panel_en, panel_ja = self._read_travel_search_prompt()
            self._w._ui_router.update_place_list(TRAVEL_SEARCH_OWNER, [], title='', panel_en=panel_en, panel_ja=panel_ja)
        except Exception:
            _log.exception('_show_travel_search_prompt failed')

    def _clear_travel_city_list(self) -> None:
        try:
            self._w._ui_router.clear_if_owner(TRAVEL_SEARCH_OWNER, mode='translate', clear_place_list=True)
        except Exception:
            pass

    def _show_dynamic_place_list(self) -> None:
        try:
            _tav = getattr(self._w, '_tavern_session', None)
            _tem = getattr(self._w, '_temple_session', None)
            if _tav is not None and _tav.is_active() or (_tem is not None and _tem.is_active()):
                return
        except Exception:
            pass
        try:
            from popup11_list_detector import POPUP11_ITEM_COUNT_OFFSET, _read_u8
            from popup11_list_parser import parse_dynamic_place_list
            from ask_about_menu_parser import translate
            item_count = _read_u8(self._w._analyzer, self._w._anchor + POPUP11_ITEM_COUNT_OFFSET) or 0
            items_en = parse_dynamic_place_list(self._w._analyzer, self._w._anchor, item_count)
            if not items_en:
                return
            import dynamic_place_lookup as dpl
            category = dpl.detect_category(items_en[0]) if items_en else None
            item_data = [{'en': opt_en, 'ja': dpl.lookup(opt_en, category)} for opt_en in items_en]
            title_en = 'Where is...'
            title_ja = translate(title_en)
            self._w._ui_router.update_place_list(NPC_CONVERSATION_OWNER, item_data, title='', panel_en=title_en, panel_ja=title_ja)
        except Exception:
            _log.exception('_show_dynamic_place_list failed')
