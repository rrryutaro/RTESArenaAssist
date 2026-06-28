from __future__ import annotations
import logging
_log = logging.getLogger('RTESArenaAssist')
_JOURNAL_PRIORITY = 50

def _clear_journal_display(w) -> None:
    try:
        w._ui_router.clear_display('', mode='translate', allowed_current_owners=('journal',))
    except AttributeError:
        pass

def _panel_text(entry: dict, en: bool) -> str:
    date_key = 'date_en' if en else 'date_ja'
    body_key = 'body_en' if en else 'body_ja'
    return '\n'.join((x for x in (entry.get(date_key, ''), entry.get(body_key, '')) if x))

def poll_journal(w, *, modal_kind: str) -> None:
    tab_journal = getattr(w, '_tab_journal', None)
    if tab_journal is None:
        return
    if modal_kind != 'journal':
        if getattr(w, '_journal_active_prev', False):
            _log.info('panel_owner -> clear journal (screen:logbook closed)')
        w._journal_active_prev = False
        w._journal_key_prev = None
        _clear_journal_display(w)
        return
    w._journal_active_prev = True
    try:
        from journal_reader import parse_journal_entries, read_journal_raw, translate_journal
        _raw = read_journal_raw(w._analyzer, w._anchor)
        if _raw is None:
            return
        _entries_en = parse_journal_entries(_raw)
        if not _entries_en:
            return
        _key = tuple(_entries_en)
        _prev = getattr(w, '_journal_key_prev', None)
        if _key != _prev:
            w._journal_key_prev = _key
            _entries: list[dict] = []
            for _date_en, _body_en in _entries_en:
                _date_ja, _body_ja = translate_journal(_date_en, _body_en)
                _entries.append({'date_en': _date_en or '', 'body_en': _body_en or '', 'date_ja': _date_ja or _date_en or '', 'body_ja': _body_ja or ''})
            w._journal_entries_cached = _entries
            tab_journal.update_journal_entries(_entries)
        else:
            _entries = list(getattr(w, '_journal_entries_cached', []) or [])
            if not _entries:
                return
        _latest = _entries[-1]
        _panel_en = _panel_text(_latest, True)
        _panel_ja = _panel_text(_latest, False)
        if _panel_en:
            w._ui_router.propose_journal_entries('journal', _entries, panel_en=_panel_en, panel_ja=_panel_ja, priority=_JOURNAL_PRIORITY, reason='screen:logbook', speech_role='situation', log_enabled=False)
            _log.info('panel_owner -> journal (entries=%d latest_date=%r body=%r)', len(_entries), _latest.get('date_en', '')[:60], _latest.get('body_en', '')[:60])
    except Exception:
        _log.exception('journal read failed')
__all__ = ['poll_journal']
