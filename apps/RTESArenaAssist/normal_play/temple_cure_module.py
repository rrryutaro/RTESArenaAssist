from __future__ import annotations
import logging
_log = logging.getLogger('RTESArenaAssist')
CURE_OWNER = 'temple_cure'
CURE_KEY = '_temple_cure_key_prev'
_CURE_KEY_BY_EN = {'Diseased': 'ui.diseased.0', 'Poisoned': 'ui.poisoned.0', 'Cursed': 'ui.cursed.0'}
_CURE_ALL_KEY = 'ui.cure_all.0'
_LIST_TITLE_KEY = 'ui.cure.0'

def _tr_name(en: str) -> str:
    import i18n_helper as i18n
    key = _CURE_KEY_BY_EN.get(en) or (_CURE_ALL_KEY if en == 'Cure all' else None)
    if key:
        ja = i18n.text_opt(key)
        if ja:
            return ja
    return en

def _title_ja(char_name: str) -> str:
    import i18n_helper as i18n
    tmpl = i18n.text_opt('npc_dialog.A156.0')
    if not tmpl:
        return ''
    return tmpl.replace('%nc2', char_name)

def cure_foreground_view(w, *, img: str='', shop_state=None):
    if (img or '').upper() != 'NEWPOP.IMG':
        return None
    if shop_state is None:
        return None
    if getattr(shop_state, 'b7c4', None) != 0:
        return None
    if (getattr(shop_state, 'ff2', 0) or 0) != 0:
        return None
    try:
        from temple_cure_reader import read_cure_view, read_active_slot_values
        analyzer = getattr(w, '_analyzer', None)
        anchor = getattr(w, '_anchor', 0)
        cure = read_cure_view(analyzer, anchor)
        if cure is None or not cure.rows:
            return None
        slots = read_active_slot_values(analyzer, anchor)
    except Exception:
        return None
    if not any((off in slots for off in cure.row_offsets)):
        return None
    return cure

def poll_temple_cure(w, *, cure) -> bool:
    if cure is None:
        return False
    try:
        rows = [{'en': r.en, 'ja': _tr_name(r.en), 'price_raw': str(r.price), 'price_display': f'{r.price} gp'} for r in cure.rows]
        key_now = (cure.title_en, tuple(((r['en'], r['price_raw']) for r in rows)))
        if key_now != getattr(w, CURE_KEY, None):
            setattr(w, CURE_KEY, key_now)
            import i18n_helper as i18n
            w._ui_router.update_facility_list(CURE_OWNER, rows, cure.title_en, _title_ja(cure.char_name), list_title_ja=i18n.text_opt(_LIST_TITLE_KEY) or '')
            _log.info('temple_cure update (name=%r rows=%r)', cure.char_name, [r['en'] for r in rows])
        return True
    except Exception:
        _log.exception('temple_cure update failed')
        return False
__all__ = ['poll_temple_cure', 'cure_foreground_view', 'CURE_OWNER', 'CURE_KEY']
