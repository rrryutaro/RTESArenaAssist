from __future__ import annotations
import logging
_log = logging.getLogger('RTESArenaAssist')
CAMP_MENU_OWNER = 'camp_menu'
CAMP_PROMPT_OWNER = 'camp_prompt'
_CAMP_UI_IDS = {'CAMP OPTIONS': 'ui.camp_options_title.0', 'Camp for a while...': 'ui.camp_for_a_while.0', 'Until fully  healed': 'ui.camp_until_healed.0'}
_HOURS_PROMPT_ID = 'npc_dialog.A110.0'
_CONFIRM_HOURS_ID = 'npc_dialog.A136.0'
_CONFIRM_ASK_ID = 'npc_dialog.A137.0'

def _translate_camp_ui(en: str) -> str:
    import i18n_helper as i18n
    _id = _CAMP_UI_IDS.get(en)
    if _id:
        t = i18n.text_opt(_id)
        if t:
            return t
    return en

def _render_camp_menu(w, view) -> None:
    try:
        title_en = view.title
        title_ja = _translate_camp_ui(title_en)
        tab_en_lines = [title_en, '']
        tab_ja_lines = [title_ja, '']
        panel_en_lines = [title_en, '']
        panel_ja_lines = [title_ja, '']
        for it in view.items:
            ja = _translate_camp_ui(it.text)
            prefix = f'[{it.hotkey}] ' if it.hotkey else ''
            tab_en_lines.append(f'  {prefix}{it.text}')
            tab_ja_lines.append(f'  {prefix}{ja}')
            panel_en_lines.append(it.text)
            panel_ja_lines.append(ja)
        _key = (title_en, tuple(tab_ja_lines))
        _prev_key = getattr(w, '_camp_menu_key_prev', None)
        if _key != _prev_key:
            w._camp_menu_key_prev = _key
            w._ui_router.update_translation(CAMP_MENU_OWNER, '\n'.join(tab_en_lines), '\n'.join(tab_ja_lines), panel_en='\n'.join(panel_en_lines), panel_ja='\n'.join(panel_ja_lines))
            _log.info('camp_menu update (title=%r items=%r)', title_en, [it.text for it in view.items])
    except Exception:
        _log.exception('camp_menu update failed')

def _render_camp_prompt(w, view) -> None:
    try:
        en = view.prompt_text
        ja = ''
        try:
            import npc_dialog_lookup as ndl
            r = ndl.lookup(en)
            if r is not None:
                ja = ndl.format_japanese(r[0], r[1])
        except Exception:
            ja = ''
        if not ja:
            import i18n_helper as i18n
            ja = i18n.text_opt(_HOURS_PROMPT_ID) or en
        _key = (en, ja)
        _prev_key = getattr(w, '_camp_prompt_key_prev', None)
        if _key != _prev_key:
            w._camp_prompt_key_prev = _key
            w._ui_router.update_translation(CAMP_PROMPT_OWNER, en, ja, speech_role='situation')
            _log.info('camp_prompt update (en=%r ja=%r)', en[:60], ja[:60])
    except Exception:
        _log.exception('camp_prompt update failed')

def _render_camp_confirm(w, view) -> None:
    try:
        import re
        import i18n_helper as i18n
        en = view.prompt_text
        m = re.search('(\\d+)\\s+remaining hours', en)
        num = m.group(1) if m else ''
        hours_ja = (i18n.text_opt(_CONFIRM_HOURS_ID) or '').replace('%a', num)
        ask_ja = i18n.text_opt(_CONFIRM_ASK_ID) or ''
        body_ja = ''.join((p for p in (hours_ja, ask_ja) if p)) or en
        en_display = f'{en}\nYes\nNo'
        ja_display = f'{body_ja}\nはい\nいいえ'
        _key = (en_display, ja_display)
        _prev_key = getattr(w, '_camp_prompt_key_prev', None)
        if _key != _prev_key:
            w._camp_prompt_key_prev = _key
            w._ui_router.update_translation(CAMP_PROMPT_OWNER, en_display, ja_display, speech_role='situation')
            _log.info('camp_confirm update (en=%r ja=%r)', en_display[:60], ja_display[:60])
    except Exception:
        _log.exception('camp_confirm update failed')

def _cleanup_camp(w) -> None:
    _had = bool(getattr(w, '_camp_menu_key_prev', None) is not None or getattr(w, '_camp_prompt_key_prev', None) is not None or w._panel_owner in (CAMP_MENU_OWNER, CAMP_PROMPT_OWNER))
    if not _had:
        return
    w._camp_menu_key_prev = None
    w._camp_prompt_key_prev = None
    for _owner in (CAMP_MENU_OWNER, CAMP_PROMPT_OWNER):
        if w._panel_owner == _owner:
            w._ui_router.clear_if_owner(_owner)
            _log.info('%s exit', _owner)

def poll_camp_rest(w) -> bool:
    try:
        from camp_rest_reader import classify_camp_view
        _streak_prev = int(getattr(w, '_camp_menu_release_streak', 0) or 0)
        view = classify_camp_view(w._analyzer, w._anchor, menu_release_streak=_streak_prev)
        w._camp_menu_release_streak = int(getattr(view, 'menu_release_streak', 0) or 0)
    except Exception:
        _log.exception('classify_camp_view failed')
        view = None
        w._camp_menu_release_streak = 0
    kind = getattr(view, 'kind', 'none') if view is not None else 'none'
    _prev_kind = getattr(w, '_camp_view_kind_prev', 'none')
    if kind != _prev_kind:
        w._camp_view_kind_prev = kind
        _log.info('camp view: %s -> %s (%s)', _prev_kind, kind, getattr(view, 'reason', '') if view is not None else 'no view')
    if kind == 'menu':
        _render_camp_menu(w, view)
        return True
    if kind == 'hours_prompt':
        _render_camp_prompt(w, view)
        return True
    if kind == 'rest_confirm':
        _render_camp_confirm(w, view)
        return True
    _cleanup_camp(w)
    return False
__all__ = ['CAMP_MENU_OWNER', 'CAMP_PROMPT_OWNER', 'poll_camp_rest']
