from __future__ import annotations
import logging
_log = logging.getLogger('pregame_render')

def show_startup_intro(w, img_name: str) -> None:
    from intro_texts import STARTUP_PAGE_IDS, STARTUP_PAGE_ORDER, source_text, display_text
    page_id = STARTUP_PAGE_IDS.get(img_name)
    slide_en = source_text(page_id)
    slide_ja = display_text(page_id)
    all_en = '\n'.join((source_text(i) for i in STARTUP_PAGE_ORDER))
    all_ja = '\n'.join((display_text(i) for i in STARTUP_PAGE_ORDER))
    if not getattr(w, '_startup_intro_prewarmed', False):
        from tts_prewarm import prewarm_fixed_sequence
        prewarm_fixed_sequence(w, [all_ja], '_startup_intro_prewarmed')
    w._set_chargen_ui_state(True)
    update_panel = not w._startup_layout_pushed and w._layout_translate_panel is not None
    if update_panel:
        w._ui_router.update_translation('top_level_startup_intro', slide_en, slide_ja, panel_en=all_en, panel_ja=all_ja, speech_role='situation', speech_text=all_ja)
        w._startup_layout_pushed = True
    else:
        w._ui_router.update_translation('top_level_startup_intro', slide_en, slide_ja, update_panel=False, speech_role='situation', speech_text=all_ja)

def show_menu_screen(w) -> None:
    from intro_texts import MENU_ITEM_IDS, source_text, display_text
    try:
        w._chargen._reset_chargen_state_for_restart(reason='title screen entered (MENU.IMG)')
    except (AttributeError, RuntimeError) as exc:
        _log.debug('chargen reset on MENU.IMG skipped: %s', exc)
    main_en_parts = [f'{source_text(nid)}  — {source_text(did)}' for nid, did in MENU_ITEM_IDS]
    main_ja_parts = [f'{display_text(nid)}  — {display_text(did)}' for nid, did in MENU_ITEM_IDS]
    main_en = '\n'.join(main_en_parts)
    main_ja = '\n'.join(main_ja_parts)
    layout_en = '\n'.join((source_text(nid) for nid, _did in MENU_ITEM_IDS))
    layout_ja = '\n'.join((display_text(nid) for nid, _did in MENU_ITEM_IDS))
    w._set_chargen_ui_state(True)
    w._ui_router.update_translation('top_level_menu', main_en, main_ja, panel_en=layout_en, panel_ja=layout_ja)

def show_load_screen(w) -> None:
    import save_manager as sm
    import save_reader as sr
    import assist_settings as settings
    game_dir = settings.get('save_dir', '')
    slot_data: list[dict] = []
    if game_dir:
        backup_dir = settings.get('backup_dir', '') or sm.default_backup_dir()
        try:
            notes = sm.load_slot_notes(backup_dir)
        except Exception:
            notes = {}
        for slot in sm.list_slots(game_dir):
            try:
                info = sr.read_slot_info(game_dir, slot)
            except Exception:
                info = {'slot': slot, 'save_name': None, 'modified': None}
            slot_data.append({'slot': info.get('slot', slot), 'save_name': info.get('save_name') or '', 'note_label': notes.get(str(slot), {}).get('name', ''), 'modified': info.get('modified') or ''})
    w._set_chargen_ui_state(True)
    try:
        w._ui_router.update_load_screen_slots('load_screen', slot_data)
    except AttributeError:
        pass

def show_newgame_slide(w, img_name: str) -> None:
    from intro_texts import NEWGAME_SLIDE_IDS, NEWGAME_SLIDE_ORDER, source_text, display_text
    key = img_name.replace('.IMG', '')
    slide_id = NEWGAME_SLIDE_IDS.get(key)
    slide_en = source_text(slide_id)
    slide_ja = display_text(slide_id)
    all_en = '\n'.join((s for i in NEWGAME_SLIDE_ORDER if (s := source_text(i))))
    all_ja = '\n'.join((s for i in NEWGAME_SLIDE_ORDER if (s := display_text(i))))
    if not getattr(w, '_newgame_intro_prewarmed', False):
        from tts_prewarm import prewarm_fixed_sequence
        prewarm_fixed_sequence(w, [all_ja], '_newgame_intro_prewarmed')
    w._set_chargen_ui_state(True)
    update_panel = not w._newgame_layout_pushed and w._layout_translate_panel is not None
    if update_panel:
        w._ui_router.update_translation('top_level_newgame_slide', slide_en, slide_ja, panel_en=all_en, panel_ja=all_ja, speech_role='situation', speech_text=all_ja)
        w._newgame_layout_pushed = True
    else:
        w._ui_router.update_translation('top_level_newgame_slide', slide_en, slide_ja, update_panel=False, speech_role='situation', speech_text=all_ja)
__all__ = ['show_startup_intro', 'show_menu_screen', 'show_load_screen', 'show_newgame_slide']
