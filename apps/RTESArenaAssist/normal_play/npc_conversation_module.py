from __future__ import annotations
import logging
import assist_settings as settings
from panel_mode_resolver import closing_panel_mode, screen_panel_mode
from top_level.top_level_dispatcher import current_state as _current_top_level
_log = logging.getLogger('RTESArenaAssist')
NPC_CONVERSATION_OWNER = 'npc_conversation'

def poll_npc_conversation(w, ctx, *, npc_dialog: str, npc_dialog_changed: bool, dialog_just_opened: bool, in_interior: bool, facility_active_now: bool, npc_translated: bool, c_area: str='', screen_img: str='') -> None:
    _response_surface_active = bool(getattr(ctx, 'response_text_on_screen', False) or getattr(ctx, 'panel_only_interior_message', False))
    _route4_eligible = not npc_translated and bool(npc_dialog) and (c_area != 'dungeon') and (npc_dialog_changed or dialog_just_opened) and (w._npc_conversation_active or in_interior) and (not facility_active_now) and _response_surface_active
    if _route4_eligible:
        try:
            import npc_dialog_lookup as _ndl
            _ndl_result = _ndl.lookup(npc_dialog)
            if _ndl_result:
                _ndl_ja_tmpl, _ndl_ph = _ndl_result
                _ndl_ja = _ndl.format_japanese(_ndl_ja_tmpl, _ndl_ph)
                if ctx.panel_only_interior_message:
                    w._ui_router.update_panel_translation(npc_dialog, _ndl_ja, speech_role='conversation')
                else:
                    w._ui_router.update_translation(NPC_CONVERSATION_OWNER, npc_dialog, _ndl_ja, clear_place_list=True, speech_role='conversation')
                    from normal_play.normal_play_render import latch_popup11_place_response_from_conversation
                    latch_popup11_place_response_from_conversation(w, npc_dialog, screen_img=screen_img)
                _log.info('npc_dialog message displayed (route=ask_about panel_only=%s text=%r)', ctx.panel_only_interior_message, npc_dialog)
            else:
                _log.info('route4 lookup miss (npc_conv=%s in_interior=%s changed=%s just_opened=%s text=%r)', w._npc_conversation_active, in_interior, npc_dialog_changed, dialog_just_opened, npc_dialog[:120])
        except (ImportError, AttributeError):
            pass
    elif npc_dialog and _current_top_level(w) == 'normal-play' and w._npc_conversation_active:
        _r4_reasons = []
        if npc_translated:
            _r4_reasons.append('translated_by_route2')
        if not (npc_dialog_changed or dialog_just_opened):
            _r4_reasons.append('no_change_no_edge')
        if not (w._npc_conversation_active or in_interior):
            _r4_reasons.append('no_conv_no_interior')
        if facility_active_now:
            _r4_reasons.append('facility_active')
        if not _response_surface_active:
            _r4_reasons.append('response_not_on_screen')
        if _r4_reasons:
            _route4_skip_key = (tuple(_r4_reasons), npc_dialog[:80])
            _prev_skip_key = getattr(w, '_b263_route4_skip_prev', None)
            if _route4_skip_key != _prev_skip_key:
                w._b263_route4_skip_prev = _route4_skip_key
                _log.info('route4 skipped (reasons=%s text=%r)', '|'.join(_r4_reasons), npc_dialog[:80])

def npc_clear_panel_mode(w) -> str | None:
    try:
        return closing_panel_mode(current_mode=w._tab_translate.panel_mode(), img_name=getattr(w, '_img_name_prev', '') or '', screen_id=getattr(w, '_screen_id_prev', '') or '', top_level=_current_top_level(w), fallback_setting=settings.get('translate_fallback_screen', 'map'))
    except AttributeError:
        return 'translate'

def restore_translate_mode(w) -> None:
    try:
        mode = w._tab_translate.panel_mode()
        if mode == 'translate':
            return
        img_name_now = (getattr(w, '_img_name_prev', '') or '').upper()
        if mode == 'load_screen' and img_name_now == 'LOADSAVE.IMG':
            return
        screen_id_now = getattr(w, '_screen_id_prev', '') or ''
        if mode == 'choose_attributes' and screen_panel_mode(screen_id_now) == 'choose_attributes':
            return
        w._ui_router.set_panel_mode('translate')
    except AttributeError:
        pass

def show_npc_dialog(w, text_override: str | None=None) -> None:
    try:
        import npc_dialog_lookup as ndl
        restore_translate_mode(w)
        text = (text_override or '').strip()
        if not text:
            from popup11_response_reader import read_response_candidate
            cand = read_response_candidate(w._analyzer, w._anchor)
            text = cand.text if cand else ''
        if not text:
            return
        result = ndl.lookup(text)
        if result:
            ja_template, placeholders = result
            ja_text = ndl.format_japanese(ja_template, placeholders)
        else:
            ja_text = ''
        w._ui_router.update_translation(NPC_CONVERSATION_OWNER, text, ja_text, clear_place_list=True, speech_role='conversation')
    except Exception:
        _log.exception('show_npc_dialog failed')

def detect_active_sub_menu_title(w, parsed: dict) -> str:
    try:
        from popup11_list_detector import read_active_menu_marker
        from ask_about_menu_parser import detect_active_sub_menu_title as _detect
        marker = read_active_menu_marker(w._analyzer, w._anchor)
        title = _detect(parsed, marker)
        _log.info('detect_active_sub_menu_title: marker=%r title=%r', marker, title)
        return title
    except Exception:
        _log.exception('detect_active_sub_menu_title failed')
        return ''

def show_ask_about_menu(w) -> None:
    try:
        from arena_bridge import read_ask_about_menu
        from ask_about_menu_parser import build_display, build_display_sub, build_panel_display, build_panel_display_sub, parse_menu
        restore_translate_mode(w)
        raw = read_ask_about_menu(w._analyzer, w._anchor)
        parsed = parse_menu(raw)
        active_sub_title = detect_active_sub_menu_title(w, parsed)
        _log.info('show_ask_about_menu: active_sub_title=%r', active_sub_title)
        if active_sub_title:
            en_tab, ja_tab = build_display_sub(parsed, sub_title=active_sub_title)
        else:
            en_tab, ja_tab = build_display(parsed, include_sub=False)
        en_panel = ja_panel = ''
        if w._layout_translate_panel is not None:
            if active_sub_title:
                en_panel, ja_panel = build_panel_display_sub(parsed, sub_title=active_sub_title)
            else:
                en_panel, ja_panel = build_panel_display(parsed)
        w._ui_router.update_translation(NPC_CONVERSATION_OWNER, en_tab, ja_tab, panel_en=en_panel, panel_ja=ja_panel)
    except Exception:
        _log.exception('show_ask_about_menu failed')

def translate_where_is_item(opt_en: str, translate) -> str:
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

def show_where_is_list(w) -> None:
    try:
        from popup11_list_detector import POPUP11_ITEM_COUNT_OFFSET, _read_u8
        from popup11_list_parser import parse_where_is_list
        from ask_about_menu_parser import translate
        item_count = _read_u8(w._analyzer, w._anchor + POPUP11_ITEM_COUNT_OFFSET) or 0
        items_en = parse_where_is_list(w._analyzer, w._anchor, item_count)
        if not items_en:
            return
        item_data = [{'en': opt_en, 'ja': translate_where_is_item(opt_en, translate)} for opt_en in items_en]
        title_en = 'Where is...'
        title_ja = translate(title_en)
        w._ui_router.update_place_list(NPC_CONVERSATION_OWNER, item_data, title='', panel_en=title_en, panel_ja=title_ja)
    except Exception:
        _log.exception('show_where_is_list failed')

def show_dynamic_place_list(w) -> None:
    try:
        from popup11_list_detector import POPUP11_ITEM_COUNT_OFFSET, _read_u8
        from popup11_list_parser import parse_dynamic_place_list
        from ask_about_menu_parser import translate
        item_count = _read_u8(w._analyzer, w._anchor + POPUP11_ITEM_COUNT_OFFSET) or 0
        items_en = parse_dynamic_place_list(w._analyzer, w._anchor, item_count)
        if not items_en:
            return
        import dynamic_place_lookup as dpl
        category = dpl.detect_category(items_en[0]) if items_en else None
        item_data = [{'en': opt_en, 'ja': dpl.lookup(opt_en, category)} for opt_en in items_en]
        title_en = 'Where is...'
        title_ja = translate(title_en)
        w._ui_router.update_place_list(NPC_CONVERSATION_OWNER, item_data, title='', panel_en=title_en, panel_ja=title_ja)
    except Exception:
        _log.exception('show_dynamic_place_list failed')

def _reset_internal_state(w) -> None:
    w._ask_about_menu_active_prev = False
    w._ask_about_current_ptr_prev = -1
    w._popup11_list_state_prev = ''
    w._popup11_exit_pending_ask_about = False
    w._popup11_place_response_lock = None
    w._npc_dialog_text_prev = ''

def reset_npc_dialog_display(w, *, clear_display: bool=True) -> None:
    try:
        if clear_display:
            clear_mode = npc_clear_panel_mode(w)
            if w._tab_translate is not None:
                w._ui_router.clear_display('', mode=clear_mode, clear_place_list=True, allowed_current_owners=('', 'npc_dialog', NPC_CONVERSATION_OWNER, 'npc_message'))
        _reset_internal_state(w)
    except (AttributeError, RuntimeError) as exc:
        _log.debug('reset_npc_dialog_display skipped: %s', exc)

def close_on_modal_overlay(w) -> None:
    try:
        w._ui_router.clear_if_owner(NPC_CONVERSATION_OWNER, mode='translate', clear_place_list=True)
    except (AttributeError, RuntimeError):
        pass
    _reset_internal_state(w)
__all__ = ['poll_npc_conversation', 'NPC_CONVERSATION_OWNER', 'npc_clear_panel_mode', 'restore_translate_mode', 'show_npc_dialog', 'show_ask_about_menu', 'detect_active_sub_menu_title', 'translate_where_is_item', 'show_where_is_list', 'show_dynamic_place_list', 'reset_npc_dialog_display', 'close_on_modal_overlay']
