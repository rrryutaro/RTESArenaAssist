from __future__ import annotations
import logging
_log = logging.getLogger('RTESArenaAssist')

def poll_journal(w, *, modal_kind: str) -> None:
    tab_journal = getattr(w, '_tab_journal', None)
    if tab_journal is None:
        return
    if modal_kind != 'journal':
        return
    try:
        from journal_reader import read_journal_raw, split_journal_lines, translate_journal
        _raw = read_journal_raw(w._analyzer, w._anchor)
        if _raw is None:
            return
        _date_en, _body_en = split_journal_lines(_raw)
        _key = (_date_en, _body_en)
        _prev = getattr(w, '_journal_key_prev', None)
        if _key == _prev:
            return
        w._journal_key_prev = _key
        _date_ja, _body_ja = translate_journal(_date_en, _body_en)
        tab_journal.update_journal_entries([{'date_ja': _date_ja or _date_en or '', 'body_ja': _body_ja or _body_en or ''}])
        _combined_en = '\n'.join((x for x in (_date_en, _body_en) if x))
        _combined_ja = '\n'.join((x for x in (_date_ja or _date_en, _body_ja or '') if x))
        if _combined_en:
            w._ui_router.propose_translation('journal', _combined_en, _combined_ja, priority=40, reason='screen:logbook', speech_role='situation')
            _log.info('panel_owner -> journal (date=%r body=%r)', (_date_en or '')[:60], (_body_en or '')[:60])
    except Exception:
        _log.exception('journal read failed')
__all__ = ['poll_journal']
