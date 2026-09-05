from __future__ import annotations
import logging
import re
import i18n_helper as i18n
from normal_play.mages_render_common import _SPELLDETAIL_KEY, _NPC_DIALOG_OFFSET, _PROMPT_EXTRA_SCAN_OFFSETS, _read_cost_string, _casting_cost_from_spell_cost, _buy_price_for, _translate_ui
from normal_play.mages_spellmaker_render import _SPELL_KEY, _SPELLMAKER_LIST_TITLES, _SPELLMAKER_PROMPT_LITERALS, _SPELLMAKER_PROMPT_FRAGMENT_LITERALS, _SPELLMAKER_REFRESH_DETAIL_PROMPTS, _read_spellmaker_live_spell_cost, _resolve_spellmaker_spell_cost, _resolve_spellmaker_prompt
_log = logging.getLogger('RTESArenaAssist')
MENU_OWNER = 'mages_menu'
LIST_OWNER = 'mages_list'
SPELLMAKER_OWNER = 'mages_spellmaker'
EFFECT_MENU_OWNER = 'mages_effect_menu'
LIST_IMGS = ('POPUP7.IMG', 'POPUP.IMG', 'NEWPOP.IMG')
SPELLMAKER_IMG = 'SPELLMKR.IMG'
BUYSPELL_IMG = 'BUYSPELL.IMG'
MENU_OWNER_CONFIRM = 'mages_confirm'
MENU_OWNER_SPELLDETAIL = 'mages_spelldetail'
from normal_play.mages_negotiation_module import NEGOTIATION_OWNER
_CONFIRM_FAMILY = 75
_CONFIRM_DIALOG_OFFSET = 19280
_CONFIRM_TR = {'Are you sure ?': '本当によろしいですか？', 'Are you sure': '本当によろしいですか？', 'Yes': 'はい', 'No': 'いいえ'}
MENU_OWNER_PROMPT = 'mages_prompt'
STORY_OWNER = 'mages_story'
_PROMPT_KEY = '_mages_prompt_key_prev'
_MAGES_MENU_TEXT_OFFSET = 28508
_MAGES_MENU_PTR_START = 28416
_MAGES_MENU_PTR_END = 28736
_PROMPT_CACHE_ATTR = '_mages_prompt_resolve_cache'
_RESPONSE_END_RE = re.compile('[?!.]')
_DETECT_MAGIC_QUOTE_PREFIX = 'I can tell you if that is magical'
_DETECT_MAGIC_ALREADY_KNOWN = 'You already know what that is!'
_LIST_STABLE_ATTR = '_mages_list_stable_by_key'
_LIST_PENDING_ATTR = '_mages_list_pending_by_key'
_LIST_STABLE_CONFIRM = 3
_LIST_TITLE_ATTR = '_mages_list_title_en'
_MENU_KEY = '_mages_menu_key_prev'
_LIST_KEY = '_mages_list_key_prev'
_EFFECT_MENU_KEY = '_mages_effect_menu_key_prev'
_CONFIRM_KEY = '_mages_confirm_key_prev'

def poll_mages_render(w, *, view=None, shop_state=None, shop_img_name: str='', top_level_state: str='', **_ignored) -> tuple[bool, bool, bool, bool]:
    img = (shop_img_name or '').upper()
    menu_visible = False
    list_visible = False
    spell_visible = False
    effect_menu_visible = False
    prompt_visible = False
    negot_visible = False
    reply_visible = False
    confirm_visible = False
    detail_visible = False
    sig = getattr(view, 'signals_snapshot', None)
    if sig is None:
        sig = _read_signals(w)
    state = _classify(sig)
    is_form_img = img.startswith('FORM') and img.endswith('.IMG')
    view_kind = getattr(view, 'l4_kind', '') or ''
    if view_kind == 'confirm':
        confirm_visible = _render_confirm(w)
        spell_visible = confirm_visible
    elif view_kind == 'effect_menu':
        effect_menu_visible = _render_effect_menu(w)
    elif view_kind == 'menu':
        menu_visible = _render_menu(w, shop_state, img)
    elif view_kind == 'negotiation':
        negot_visible = _render_negotiation(w, img, top_level_state)
    elif view_kind == 'spelldetail':
        detail_visible = _render_buyspell_detail(w)
    elif view_kind == 'spellmaker' and is_form_img:
        spell_visible = _render_spellmaker(w, sig, form_img=img)
    elif view_kind == 'spellmaker':
        if _render_spellmaker_prompt_overlay(w, sig):
            prompt_visible = True
            spell_visible = True
        else:
            spell_visible = _render_spellmaker(w, sig)
    elif view_kind == 'prompt':
        prompt_visible = _render_buy_prompt(w, foreground_ptr=sig.get('foreground_ptr', _PROMPT_PTR_UNSET))
    elif view_kind == 'reply':
        reply_visible = _render_reply(w, img, sig=sig)
    elif view_kind == 'list':
        if _is_spellmaker_return_from_residual_list(w, sig, img, state):
            spell_visible = _render_spellmaker(w, sig)
        else:
            list_visible = _render_list(w, sig, img)
    if menu_visible or list_visible or spell_visible or confirm_visible or prompt_visible or detail_visible or negot_visible or effect_menu_visible or reply_visible:
        _cleanup(w, menu_visible, list_visible, spell_visible, confirm_visible, prompt_visible, detail_visible, negot_visible, effect_menu_visible, reply_visible)
    return (negot_visible, False, menu_visible, list_visible or spell_visible or confirm_visible or prompt_visible or detail_visible or effect_menu_visible or reply_visible)

def _read_signals(w) -> dict:
    try:
        from mages_signals import read_signals
        return read_signals(w._analyzer, w._anchor)
    except Exception:
        return {}

def _classify(sig: dict) -> str:
    try:
        from mages_signals import classify
        return classify(sig)
    except Exception:
        return 'unknown'

def _read_current_ptr(w):
    try:
        from popup11_response_reader import read_current_text_pointer
        return read_current_text_pointer(w._analyzer, w._anchor)
    except Exception:
        return None

def _render_menu(w, shop_state, img: str) -> bool:
    try:
        from shop_menu_reader import translate_shop_menu_items, translate_ui_text
        from normal_play.shop_render_common import build_menu_display
        items = shop_state.menu_items
        hotkeys = shop_state.menu_item_hotkeys
        key_now = (tuple(items), tuple(hotkeys))
        if key_now != getattr(w, _MENU_KEY, None):
            setattr(w, _MENU_KEY, key_now)
            menu_tr = translate_shop_menu_items(items, owner_kind='mages_guild')
            title_en = shop_state.menu_title_en or ''
            title_ja = translate_ui_text('mages_guild', title_en) or title_en if title_en else ''
            tab_en, tab_ja, panel_en, panel_ja = build_menu_display(menu_tr, hotkeys, title_en, title_ja)
            w._ui_router.update_translation(MENU_OWNER, tab_en, tab_ja, panel_en=panel_en, panel_ja=panel_ja)
            _log.info('mages_menu update (img=%r title=%r items=%r)', img, title_en, items)
    except Exception:
        _log.exception('mages_menu update failed')
    return True

def render_no_session_menu(w, *, shop_state, shop_img_name: str) -> bool:
    _is_own = shop_state is not None and getattr(shop_state, 'kind', '') == 'shop_menu' and (getattr(shop_state, 'owner_kind', '') == 'mages_guild')
    if not _is_own:
        if getattr(w, _MENU_KEY, None) is not None:
            setattr(w, _MENU_KEY, None)
            if w._panel_owner == MENU_OWNER:
                w._ui_router.clear_if_owner(MENU_OWNER)
        return False
    return _render_menu(w, shop_state, shop_img_name)

def _render_effect_menu(w) -> bool:
    title_en = 'Edit Effects'
    items = ['Add', 'Modify', 'Delete']
    en = title_en + ''.join((f'\n  {item}' for item in items))
    title_ja = _translate_ui(title_en)
    ja = title_ja + ''.join((f'\n  {_translate_ui(item)}' for item in items))
    try:
        key_now = ('effect_menu', en)
        changed = key_now != getattr(w, _EFFECT_MENU_KEY, None)
        if changed:
            setattr(w, _EFFECT_MENU_KEY, key_now)
            _log.info('mages_effect_menu update')
        if not _render_spellmaker_detail(w, panel_en=en, panel_ja=ja, reason='mages_effect_menu_overlay') and changed:
            w._ui_router.update_translation(EFFECT_MENU_OWNER, en, ja, panel_en=en, panel_ja=ja, update_tab=False, update_panel=True, keep_owner=True, mode=None, priority=95, reason='mages_effect_menu')
    except Exception:
        _log.exception('mages_effect_menu update failed')
    return True

def _select_list_source(w, sig: dict, img: str):
    from mages_list_reader import POTION_LIST_OFFSET, SPELL_LIST_OFFSET, INVENTORY_LIST_OFFSET, SPELLMAKER_TARGET_OFFSET, SPELLMAKER_EFFECT_OFFSET, SPELLMAKER_SUBLIST_OFFSET, EFFECT_PICK_OFFSET, read_name_list, read_magic_item_list, read_active_priced_list, looks_like_potion_list, read_active_list_offset, classify_spellmaker_name_items, enrich_unidentified_by_index
    family = sig.get('family')
    cur = sig.get('foreground_ptr') if 'foreground_ptr' in sig else _read_current_ptr(w)
    cur = cur if isinstance(cur, int) else 0

    def _classified(offset: int):
        items = read_name_list(w._analyzer, w._anchor, offset)
        return classify_spellmaker_name_items(items)
    if family == 89:
        tried: set[int] = set()
        ptr = read_active_list_offset(w._analyzer, w._anchor)
        for off in (ptr, EFFECT_PICK_OFFSET):
            if off is None or off in tried:
                continue
            tried.add(off)
            classified = _classified(off)
            if classified:
                return classified
        return ('Effects', '効果一覧', [])
    if family == 112:
        if img == 'POPUP7.IMG':
            return ('Magic Items', '魔法アイテム一覧', read_magic_item_list(w._analyzer, w._anchor))
        items = read_active_priced_list(w._analyzer, w._anchor)
        if items:
            if looks_like_potion_list(items):
                return ('Potions', 'ポーション一覧', items)
            return ('Spells', '呪文一覧', items)
        if SPELL_LIST_OFFSET <= cur < 39936:
            return ('Spells', '呪文一覧', [])
        if POTION_LIST_OFFSET <= cur < SPELL_LIST_OFFSET:
            return ('Potions', 'ポーション一覧', [])
        return ('', '', [])
    if family == 111:
        if img == 'NEWPOP.IMG':
            off = read_active_list_offset(w._analyzer, w._anchor)
            inv_items = read_name_list(w._analyzer, w._anchor, off if off else INVENTORY_LIST_OFFSET)
            inv_items = enrich_unidentified_by_index(w._analyzer, w._anchor, inv_items)
            return ('Inventory', '所持品一覧', inv_items)
        ptr = read_active_list_offset(w._analyzer, w._anchor)
        if ptr is not None:
            classified = _classified(ptr)
            if classified:
                return classified
        if 21857 <= cur < 22160:
            classified = _classified(SPELLMAKER_SUBLIST_OFFSET)
            if classified:
                return classified
            return ('Effect Options', '効果オプション', [])
        if 22160 <= cur < 22528:
            classified = _classified(SPELLMAKER_TARGET_OFFSET)
            if classified:
                return classified
            return ('Targets', '対象一覧', [])
        classified = _classified(SPELLMAKER_EFFECT_OFFSET)
        if classified:
            return classified
        return ('Effects', '効果一覧', [])
    return ('Items', '一覧', [])

def _list_signature(items: list[dict]) -> tuple:
    return tuple(((it.get('en', ''), it.get('price_display', ''), it.get('is_unidentified', False)) for it in items))

def _stabilize_list(w, list_key: str, items: list[dict]) -> list[dict]:
    if not list_key:
        return items
    stable_by_key = getattr(w, _LIST_STABLE_ATTR, None)
    if stable_by_key is None:
        stable_by_key = {}
    pending_by_key = getattr(w, _LIST_PENDING_ATTR, None)
    if pending_by_key is None:
        pending_by_key = {}
    stable = stable_by_key.get(list_key, [])
    if not stable:
        if items:
            stable_by_key[list_key] = [dict(it) for it in items]
            setattr(w, _LIST_STABLE_ATTR, stable_by_key)
        return items
    if not items:
        _log.info('mages_list transient empty suppressed (key=%r)', list_key)
        return [dict(it) for it in stable]
    stable_sig = _list_signature(stable)
    sig = _list_signature(items)
    if sig == stable_sig:
        pending_by_key.pop(list_key, None)
        setattr(w, _LIST_PENDING_ATTR, pending_by_key)
        return [dict(it) for it in stable]
    if len(items) < len(stable):
        prev_sig, count = pending_by_key.get(list_key, (None, 0))
        count = count + 1 if prev_sig == sig else 1
        pending_by_key[list_key] = (sig, count)
        setattr(w, _LIST_PENDING_ATTR, pending_by_key)
        if count < _LIST_STABLE_CONFIRM:
            _log.info('mages_list transient partial suppressed (key=%r stable=%d candidate=%d count=%d)', list_key, len(stable), len(items), count)
            return [dict(it) for it in stable]
    stable_by_key[list_key] = [dict(it) for it in items]
    pending_by_key.pop(list_key, None)
    setattr(w, _LIST_STABLE_ATTR, stable_by_key)
    setattr(w, _LIST_PENDING_ATTR, pending_by_key)
    return items

def _render_list(w, sig: dict, img: str) -> bool:
    try:
        title_en, title_ja, items = _select_list_source(w, sig, img)
    except Exception:
        _log.exception('mages_list source select failed')
        title_en, title_ja, items = ('Items', i18n.text('mages_list.title_items'), [])
    setattr(w, _LIST_TITLE_ATTR, title_en)
    items = _stabilize_list(w, title_en, items)
    try:
        if items:
            key_now = ('list', title_en, tuple(((it.get('en', ''), it.get('price_display', ''), it.get('is_unidentified', False)) for it in items)))
            if key_now != getattr(w, _LIST_KEY, None):
                setattr(w, _LIST_KEY, key_now)
                w._ui_router.update_facility_list(LIST_OWNER, items, title_en, title_ja, priority=90, reason=f'mages_list:{title_en}')
                _log.info('mages_list update (img=%r title=%r items=%d)', img, title_en, len(items))
        else:
            key_now = ('unparsed', img)
            if key_now != getattr(w, _LIST_KEY, None):
                setattr(w, _LIST_KEY, key_now)
                w._ui_router.update_translation(LIST_OWNER, f'{title_en} (list parsing...)', i18n.text('mages_list.parsing_format').replace('{title}', title_ja), priority=90, reason=f'mages_list_unparsed:{title_en}')
                _log.info('mages_list unparsed placeholder (img=%r)', img)
    except Exception:
        _log.exception('mages_list update failed')
    return True

def _render_spellmaker(w, sig: dict, form_img: str='') -> bool:
    if not form_img:
        return _render_spellmaker_detail(w)
    try:
        rows, panel_en, panel_ja, tab_title = _spellmaker_form_display(w, form_img)
    except Exception:
        _log.exception('mages_spellmaker form display failed')
        return _render_spellmaker_detail(w)
    try:
        key_now = ('spellmaker_form', panel_en, tuple(((r.get('en', ''), r.get('ja', '')) for r in rows)))
        if key_now != getattr(w, _SPELL_KEY, None):
            setattr(w, _SPELL_KEY, key_now)
            w._ui_router.update_facility_list(SPELLMAKER_OWNER, rows, panel_en, panel_ja, list_title_ja=tab_title, priority=90, reason='mages_form')
            _log.info('mages_spellmaker form update: %r', panel_en[:60])
    except Exception:
        _log.exception('mages_spellmaker update failed')
    return True

def _render_spellmaker_detail(w, *, panel_en: str='', panel_ja: str='', reason: str='mages_spellmaker_detail') -> bool:
    try:
        from spell_reader import read_spell_detail
        from mages_list_reader import translate_name
        data = read_spell_detail(w._analyzer, w._anchor)
    except Exception:
        _log.exception('mages_spellmaker detail read failed')
        return False
    name = (data.get('name') or '').strip()
    translated_name = translate_name(name) if name else ''
    data['name_ja'] = translated_name if translated_name != name else ''
    casting_cost = _read_cost_string(w)
    spell_cost = _resolve_spellmaker_spell_cost(w, data, casting_cost=casting_cost)
    data['spell_cost'] = spell_cost
    if casting_cost is not None:
        data['casting_cost'] = casting_cost
    else:
        data['casting_cost'] = _casting_cost_from_spell_cost(spell_cost, data.get('player_level')) if spell_cost else 0
    if all((x == 255 for x in data.get('effects', []))):
        data['effect_en'] = ''
        data['effect_ja'] = ''
        data['text_en'] = ''
        data['text_ja'] = ''
    if not panel_en and (not panel_ja):
        panel_en = 'Spellmaker'
        panel_ja = '呪文作成'
    try:
        key_now = ('spellmaker_detail', data.get('name'), data.get('target_id'), data.get('element_id'), tuple(data.get('effects', [])), data.get('cost'), data.get('spell_cost'), data.get('casting_cost'), data.get('text_en'), tuple(((d.get('effect_en', ''), d.get('text_en', ''), d.get('text_ja', '')) for d in data.get('effect_details') or [] if isinstance(d, dict))), panel_en, panel_ja)
        if key_now != getattr(w, _SPELL_KEY, None):
            setattr(w, _SPELL_KEY, key_now)
            w._ui_router.propose_spell_detail(SPELLMAKER_OWNER, data, panel_en=panel_en, panel_ja=panel_ja, priority=90, reason=reason)
            _log.info('mages_spellmaker detail update: %r', name)
    except Exception:
        _log.exception('mages_spellmaker detail update failed')
    return True

def _spellmaker_form_display(w, form_img: str) -> tuple[list[dict], str, str, str]:
    from mages_spellmaker import FORM_CHOICES, read_form_values, format_form_assist, resolve_edit_slot, resolve_effect_title_from_record
    form = form_img[:-4] if form_img.endswith('.IMG') else form_img
    title = _read_effect_title(w)
    if not title:
        title = resolve_effect_title_from_record(w._analyzer, w._anchor, form)
    title_en = title or ''
    title_ja = ''
    if title:
        try:
            from mages_list_reader import translate_name
            title_ja = translate_name(title)
        except Exception:
            title_ja = _translate_ui(title)
    slot = resolve_edit_slot(w._analyzer, w._anchor, title)
    vals = read_form_values(w._analyzer, w._anchor, form, slot=slot)
    cost = _read_cost_string(w)
    choice = _resolve_form_choice(w, FORM_CHOICES.get(form))
    return format_form_assist(form, vals, cost=cost, title_en=title_en, title_ja=title_ja, choice=choice)

def _resolve_form_choice(w, spec: dict | None) -> dict | None:
    if not spec:
        return None
    from spell_reader import read_spell_choice_index
    options = [(o.get('en', ''), _term(o)) for o in spec.get('options', [])]
    if not options:
        return None
    label = spec.get('label', {})
    return {'label_en': label.get('en', ''), 'label_ja': _term(label), 'options': options, 'selected': read_spell_choice_index(w._analyzer, w._anchor)}

def _term(entry: dict) -> str:
    en = entry.get('en', '') if entry else ''
    key = entry.get('id', '') if entry else ''
    if not key:
        return en
    try:
        return i18n.text_opt(key) or en
    except Exception:
        return en

def _render_spellmaker_prompt_overlay(w, sig: dict) -> bool:
    info = _resolve_spellmaker_prompt(w, sig)
    if not info:
        return False
    en, ja = info
    if en in _SPELLMAKER_REFRESH_DETAIL_PROMPTS:
        if _render_spellmaker_detail(w, panel_en=en, panel_ja=ja, reason='mages_prompt_overlay'):
            return True
    try:
        key_now = ('prompt_overlay', en)
        if key_now != getattr(w, _PROMPT_KEY, None):
            setattr(w, _PROMPT_KEY, key_now)
            _log.info('mages_prompt overlay update: %r', en[:50])
            w._ui_router.update_translation(MENU_OWNER_PROMPT, en, ja, panel_en=en, panel_ja=ja, update_tab=False, update_panel=True, keep_owner=True, mode=None, priority=95, reason='mages_prompt_overlay')
    except Exception:
        _log.exception('mages_prompt overlay update failed')
    return True

def _read_effect_title(w) -> str:
    try:
        from popup11_response_reader import read_response_candidates_all
        from mages_spellmaker import EFFECT_TO_FORM
        cands = read_response_candidates_all(w._analyzer, w._anchor)
    except Exception:
        return ''
    for cand in cands:
        text = (getattr(cand, 'text', '') or '').strip()
        for effect in EFFECT_TO_FORM:
            if text == effect or text.startswith(effect):
                return text
    return ''

def _is_negotiation_img(img: str) -> bool:
    try:
        from negotiation_reader import get_negotiation_profile
    except ImportError:
        return False
    return get_negotiation_profile(img) is not None

def _render_negotiation(w, img: str, top_level_state: str) -> bool:
    try:
        from normal_play.mages_negotiation_module import poll_mages_negotiation, cleanup_mages_negotiation_if_owner
        handled = poll_mages_negotiation(w, img_name=img, top_level_state=top_level_state)
        if not handled:
            cleanup_mages_negotiation_if_owner(w)
        return handled
    except Exception:
        _log.exception('mages_negotiation update failed')
        return False

def _render_reply(w, img: str, *, sig: dict | None=None) -> bool:
    setattr(w, '_mages_reply_polled_in_render', True)
    try:
        from normal_play.mages_reply_module import poll_mages_reply
        snapshot_kwargs = {'signals_snapshot': sig}
        if sig is not None and 'foreground_ptr' in sig:
            snapshot_kwargs['foreground_ptr'] = sig['foreground_ptr']
        handled = poll_mages_reply(w, mages_active=True, mages_just_started=False, img_name=img, shop_menu_visible=False, **snapshot_kwargs)
    except Exception:
        _log.exception('mages_reply render failed')
        handled = False
    setattr(w, '_mages_reply_handled_in_render', bool(handled))
    return bool(handled)

def _render_buyspell_detail(w) -> bool:
    try:
        from spell_reader import read_spell_detail
        from mages_list_reader import translate_name
        data = read_spell_detail(w._analyzer, w._anchor)
    except Exception:
        return False
    name = (data.get('name') or '').strip()
    if not name:
        return False
    cc = _read_cost_string(w)
    if cc is not None:
        data['casting_cost'] = cc
    price = _buy_price_for(w, name)
    if price is not None:
        data['spell_cost'] = price
        if cc is None:
            data['casting_cost'] = price // 4
    data['name_ja'] = translate_name(name)
    try:
        key_now = ('spelldetail', name, data.get('cost'), data.get('spell_cost'), data.get('casting_cost'), data.get('text_en'))
        if key_now != getattr(w, _SPELLDETAIL_KEY, None):
            setattr(w, _SPELLDETAIL_KEY, key_now)
            w._ui_router.propose_spell_detail(MENU_OWNER_SPELLDETAIL, data, priority=90, reason='mages_buyspell_detail')
            _log.info('mages_spelldetail update: %r', name)
    except Exception:
        _log.exception('mages_spelldetail update failed')
    return True

def _read_confirm_dialog(w):
    try:
        raw = w._analyzer.read_bytes(w._anchor + _CONFIRM_DIALOG_OFFSET, 64)
    except (OSError, AttributeError):
        return None
    segs = []
    for s in raw.split(b'\x00'):
        t = s.decode('ascii', errors='replace').replace('\r', '').strip()
        if t:
            segs.append(t)
    title = next((s for s in segs if '?' in s or 'Are you sure' in s), '')
    buttons = [s for s in segs if s in ('Yes', 'No')]
    if not title:
        return None
    return (title, buttons or ['Yes', 'No'])

def _render_confirm(w) -> bool:
    info = _read_confirm_dialog(w)
    if not info:
        return False
    title, buttons = info
    try:
        en = title + ''.join((f'\n  {b}' for b in buttons))
        ja_title = _CONFIRM_TR.get(title) or _CONFIRM_TR.get(title.rstrip(' ?').strip(), title)
        ja = ja_title + ''.join((f'\n  {_CONFIRM_TR.get(b, b)}' for b in buttons))
        key_now = ('confirm', en)
        changed = key_now != getattr(w, _CONFIRM_KEY, None)
        if changed:
            setattr(w, _CONFIRM_KEY, key_now)
            _log.info('mages_confirm update: %r', en[:40])
        if not _render_spellmaker_detail(w, panel_en=en, panel_ja=ja, reason='mages_confirm_overlay') and changed:
            w._ui_router.update_translation(MENU_OWNER_CONFIRM, en, ja, panel_en=en, panel_ja=ja, update_tab=False, update_panel=True, keep_owner=True, mode=None, priority=95, reason='mages_confirm')
    except Exception:
        _log.exception('mages_confirm update failed')
    return True
_PROMPT_PTR_UNSET = object()

def _resolve_response_prompt(w, *, foreground_ptr=_PROMPT_PTR_UNSET):
    try:
        raw = w._analyzer.read_bytes(w._anchor + _NPC_DIALOG_OFFSET, 512)
    except (OSError, AttributeError):
        raw = b''
    extra_chunks: list[bytes] = []
    for off in _PROMPT_EXTRA_SCAN_OFFSETS:
        try:
            extra_chunks.append(w._analyzer.read_bytes(w._anchor + off, 160))
        except (OSError, AttributeError):
            extra_chunks.append(b'')
    current_ptr = foreground_ptr
    if current_ptr is _PROMPT_PTR_UNSET:
        try:
            from popup11_response_reader import read_current_text_pointer
            current_ptr = read_current_text_pointer(w._analyzer, w._anchor)
        except Exception:
            current_ptr = None
    cache_key = (raw, tuple(extra_chunks), current_ptr)
    cache = getattr(w, _PROMPT_CACHE_ATTR, None)
    if cache is not None and cache[0] == cache_key:
        return cache[1]
    text = ''.join((c if 32 <= ord(c) <= 126 else ' ' for c in raw.decode('ascii', errors='replace')))
    literal_text = text + ' ' + ' '.join((''.join((c if 32 <= ord(c) <= 126 else ' ' for c in chunk.decode('ascii', errors='replace'))) for chunk in extra_chunks))
    try:
        from npc_dialog_lookup import lookup as _nd_lookup
        from npc_dialog_lookup import format_japanese as _nd_format
    except Exception:
        return None
    normalized_text = ' '.join(literal_text.split())
    result = None
    if _DETECT_MAGIC_QUOTE_PREFIX in normalized_text:
        if isinstance(current_ptr, int) and _MAGES_MENU_PTR_START <= current_ptr < _MAGES_MENU_PTR_END:
            try:
                raw_known = w._analyzer.read_bytes(w._anchor + _MAGES_MENU_TEXT_OFFSET, 80)
            except (OSError, AttributeError):
                raw_known = b''
            known = raw_known.split(b'\x00', 1)[0].decode('ascii', errors='replace').strip()
            if known == _DETECT_MAGIC_ALREADY_KNOWN:
                res = _nd_lookup(_DETECT_MAGIC_ALREADY_KNOWN)
                if res:
                    try:
                        result = (_DETECT_MAGIC_ALREADY_KNOWN, _nd_format(res[0], res[1]))
                    except Exception:
                        result = (_DETECT_MAGIC_ALREADY_KNOWN, _DETECT_MAGIC_ALREADY_KNOWN)
    for literal in _SPELLMAKER_PROMPT_LITERALS:
        if literal not in normalized_text:
            continue
        res = _nd_lookup(literal)
        if res:
            try:
                result = (literal, _nd_format(res[0], res[1]))
            except Exception:
                result = (literal, literal)
            break
    if result is None:
        lowered_text = normalized_text.lower()
        for needles, literal in _SPELLMAKER_PROMPT_FRAGMENT_LITERALS:
            if not all((needle in lowered_text for needle in needles)):
                continue
            res = _nd_lookup(literal)
            if res:
                try:
                    result = (literal, _nd_format(res[0], res[1]))
                except Exception:
                    result = (literal, literal)
                break
    seen: set[str] = set()
    for i, ch in enumerate(text):
        if result is not None or not ch.isupper():
            continue
        seg = text[i:i + 160]
        end = _RESPONSE_END_RE.search(seg)
        if not end:
            continue
        cand = ' '.join(seg[:end.end()].split())
        if len(cand) < 10 or cand in seen:
            continue
        seen.add(cand)
        res = _nd_lookup(cand)
        if res:
            try:
                result = (cand, _nd_format(res[0], res[1]))
            except Exception:
                result = (cand, cand)
            break
    setattr(w, _PROMPT_CACHE_ATTR, (cache_key, result))
    return result

def _render_buy_prompt(w, *, foreground_ptr=_PROMPT_PTR_UNSET) -> bool:
    info = _resolve_response_prompt(w, foreground_ptr=foreground_ptr)
    if not info:
        return False
    en, ja = info
    try:
        key_now = ('prompt', en)
        if key_now != getattr(w, _PROMPT_KEY, None):
            setattr(w, _PROMPT_KEY, key_now)
            w._ui_router.update_translation(MENU_OWNER_PROMPT, en, ja)
            _log.info('mages_prompt update: %r', en[:50])
    except Exception:
        _log.exception('mages_prompt update failed')
    return True

def _last_spellmaker_list_title(w) -> str:
    title = (getattr(w, _LIST_TITLE_ATTR, '') or '').strip()
    return title if title in _SPELLMAKER_LIST_TITLES else ''

def _is_spellmaker_return_from_residual_list(w, sig: dict, img: str, state: str) -> bool:
    return img in LIST_IMGS and bool(_last_spellmaker_list_title(w)) and (state == 'reply') and (sig.get('list') != 0)
_STORY_BUF_OFFSET = 38434
_STORY_BUF_READ = 4096
_STORY_KEY_ATTR = '_mages_story_key_prev'
_STORY_UNIT_ATTR = '_mages_story_accepted_unit'
_STORY_RESOLVE_CACHE_ATTR = '_mages_story_resolve_cache'
_POINTER_UNSET = object()
_STORY_CHOICE_OVERLAY_PTR = 33384

def _story_body_source(ptr: int | None) -> tuple[int, int, bool] | None:
    if ptr is None:
        return None
    try:
        from active_template_reader import message_buffer_remaining
    except ImportError:
        return None
    remaining = message_buffer_remaining(ptr)
    if remaining is not None:
        return (ptr, remaining, False)
    if ptr == _STORY_BUF_OFFSET:
        return (_STORY_BUF_OFFSET, _STORY_BUF_READ, False)
    if ptr == _STORY_CHOICE_OVERLAY_PTR:
        return (_STORY_BUF_OFFSET, _STORY_BUF_READ, True)
    return None

def _story_hold_pointer(ptr: int | None) -> bool:
    if ptr is None:
        return False
    if _story_body_source(ptr) is not None:
        return False
    return _STORY_BUF_OFFSET <= ptr < _STORY_BUF_OFFSET + _STORY_BUF_READ

def _story_foreground(w) -> bool:
    try:
        from active_template_reader import read_current_text_pointer
        ptr = read_current_text_pointer(w._analyzer, w._anchor)
    except Exception:
        return False
    return _story_body_source(ptr) is not None
_TEXT_BYTES = frozenset(bytes(range(32, 127)) + b'\n\r\t')

def _is_text_bytes(seg: bytes) -> bool:
    return bool(seg) and all((b in _TEXT_BYTES for b in seg))

def _read_story_chunks(w, off: int=_STORY_BUF_OFFSET, size: int=_STORY_BUF_READ) -> list[str]:
    try:
        raw = w._analyzer.read_bytes(w._anchor + off, size)
        if len(raw) != size:
            return []
    except (OSError, AttributeError, TypeError):
        return []
    parts: list[str] = []
    segments = raw.split(b'\x00')
    final_is_terminated = raw.endswith(b'\x00')
    for index, seg in enumerate(segments):
        if index == len(segments) - 1 and (not final_is_terminated):
            if parts:
                break
            return []
        if not seg:
            if parts:
                break
            return []
        if not _is_text_bytes(seg):
            if parts:
                break
            return []
        frag = seg.decode('ascii', errors='replace').strip()
        if frag:
            parts.append(' '.join(frag.split()))
        elif parts:
            break
        else:
            return []
    return parts

def _read_story_body(w, off: int=_STORY_BUF_OFFSET, size: int=_STORY_BUF_READ) -> str:
    return ' '.join(_read_story_chunks(w, off, size))

def _is_building_entry_body(body: str) -> bool:
    try:
        import template_dat_building_lookup as _tbl
        return _tbl.is_building_entry_message(body)
    except (ImportError, AttributeError):
        return False

def _is_building_entry_chunks(chunks: list[str]) -> bool:
    return any((_is_building_entry_body(' '.join(chunks[:end])) for end in range(1, len(chunks) + 1)))

def _explains_body(span: str, first_chunk: str) -> bool:
    if not span or not first_chunk:
        return False
    return span == first_chunk or span.startswith(first_chunk + ' ')

def resolve_story_text(w) -> tuple[str, str] | None:
    source = _story_body_source(_read_story_pointer(w))
    if source is None:
        return None
    return _resolve_story_from_source(w, source)

def _read_story_pointer(w) -> int | None:
    try:
        from active_template_reader import read_current_text_pointer
        return read_current_text_pointer(w._analyzer, w._anchor)
    except Exception:
        return None
_story_resolve_state: dict[str, bool] = {}

def _note_story_unresolved(resolved: bool, chunks: list[str]) -> None:
    if _story_resolve_state.get('ok') is resolved:
        return
    _story_resolve_state['ok'] = resolved
    if resolved:
        return
    detail = ''
    try:
        import npc_dialog_lookup as _ndl
        detail = ' / ' + _ndl.describe_unmatched_body(' '.join(chunks))
    except (ImportError, AttributeError):
        pass
    _log.warning('ギルドのストーリー本文の範囲を同定できなかった: チャンク数=%d 長さ=%s%s', len(chunks), [len(c) for c in chunks], detail)

def _resolve_story_from_source(w, source: tuple[int, int]) -> tuple[str, str] | None:
    chunks = _read_story_chunks(w, source[0], source[1])
    if not chunks:
        return None
    cache_key = (source, tuple(chunks))
    cached = getattr(w, _STORY_RESOLVE_CACHE_ATTR, None)
    if cached is not None and cached[0] == cache_key:
        return cached[1]
    if _is_building_entry_chunks(chunks):
        setattr(w, _STORY_RESOLVE_CACHE_ATTR, (cache_key, None))
        return None
    en, ja = (chunks[0], '')
    try:
        import npc_dialog_lookup as _ndl
        found = _ndl.lookup_span_at_chunk_boundaries(chunks)
        boundaries = {' '.join(chunks[:i]) for i in range(1, len(chunks) + 1)}
        if found and found[2] in boundaries and _explains_body(found[2], chunks[0]):
            ja_text = _ndl.format_japanese(found[0], found[1])
            if ja_text and '%' not in ja_text:
                en, ja = (found[2], ja_text)
    except (ImportError, AttributeError):
        pass
    _note_story_unresolved(bool(ja), chunks)
    resolved = (en, ja) if en else None
    setattr(w, _STORY_RESOLVE_CACHE_ATTR, (cache_key, resolved))
    return resolved

def is_mages_interior_mif(interior_mif_name: str | None) -> bool:
    return (interior_mif_name or '').upper().startswith('MAGE')

def poll_mages_story(w, *, guild_active: bool, foreground_ptr=_POINTER_UNSET) -> bool:
    if not guild_active:
        _close_story_unit(w)
        return False
    return _render_story(w, foreground_ptr=foreground_ptr)

def _close_story_unit(w) -> None:
    shown = getattr(w, _STORY_KEY_ATTR, None) is not None
    if shown:
        try:
            w._ui_router.notify_display_unit_closed(STORY_OWNER)
        except AttributeError:
            pass
    if w._ui_router.is_owner(STORY_OWNER):
        w._ui_router.clear_if_owner(STORY_OWNER, notify_close=False)
    setattr(w, _STORY_KEY_ATTR, None)
    setattr(w, _STORY_UNIT_ATTR, None)

def _read_story_occurrence(w) -> int | None:
    try:
        from active_template_reader import read_display_occurrence
        return read_display_occurrence(w._analyzer, w._anchor)
    except Exception:
        return None

def _story_display_unit(w, occurrence: int, source: tuple[int, int, bool], resolved: tuple[str, str]) -> str:
    unit = getattr(w, _STORY_UNIT_ATTR, None)
    if unit is None:
        return 'new'
    body_changed = unit[3] != resolved[0]
    if unit[0] != occurrence:
        if body_changed:
            return 'new'
        return 'page' if (unit[1], unit[2]) != (source[0], source[2]) else 'same'
    if body_changed:
        return 'hold'
    if (unit[1], unit[2]) != (source[0], source[2]):
        return 'page'
    return 'same'

def _story_display_text(ja: str) -> str:
    if not ja:
        return ja
    return f'{ja}\n\n  はい\n  いいえ'

def _render_story(w, *, foreground_ptr=_POINTER_UNSET) -> bool:
    ptr = _read_story_pointer(w) if foreground_ptr is _POINTER_UNSET else foreground_ptr
    source = _story_body_source(ptr)
    if source is None:
        if _story_hold_pointer(ptr) and getattr(w, _STORY_UNIT_ATTR, None) is not None:
            return True
        _close_story_unit(w)
        return False
    resolved = _resolve_story_from_source(w, source)
    occurrence = _read_story_occurrence(w)
    if resolved is None or occurrence is None:
        return True
    kind = _story_display_unit(w, occurrence, source, resolved)
    if kind == 'hold':
        return True
    if kind == 'same':
        return True
    en, ja = resolved
    if kind == 'new' and getattr(w, _STORY_KEY_ATTR, None) is not None:
        try:
            w._ui_router.notify_display_unit_replaced(STORY_OWNER)
        except AttributeError:
            pass
    display_ja = _story_display_text(ja) if source[2] else ja
    keep = (en, display_ja, source[2])
    if getattr(w, _STORY_KEY_ATTR, None) != keep:
        setattr(w, _STORY_KEY_ATTR, keep)
        w._ui_router.update_translation(STORY_OWNER, en, display_ja, speech_role='conversation' if ja else None, speech_text=ja if ja else None)
        _log.info('mages story displayed (len=%d translated=%s choices=%s)', len(en), bool(ja), source[2])
    unit = getattr(w, _STORY_UNIT_ATTR, None)
    accepted = occurrence if kind == 'new' or unit is None else unit[0]
    setattr(w, _STORY_UNIT_ATTR, (accepted, source[0], source[2], en))
    return True

def reset_mages_render_keys(w) -> None:
    setattr(w, _MENU_KEY, None)
    setattr(w, _LIST_KEY, None)
    setattr(w, _SPELL_KEY, None)
    setattr(w, _EFFECT_MENU_KEY, None)
    setattr(w, _CONFIRM_KEY, None)
    setattr(w, _PROMPT_KEY, None)
    setattr(w, _SPELLDETAIL_KEY, None)
    setattr(w, _LIST_TITLE_ATTR, '')
    setattr(w, _LIST_STABLE_ATTR, {})
    setattr(w, _LIST_PENDING_ATTR, {})
    try:
        if w._tab_translate.panel_mode() == 'facility_list':
            w._ui_router.set_panel_mode('translate')
    except AttributeError:
        pass

def _cleanup(w, menu_visible: bool, list_visible: bool, spell_visible: bool, confirm_visible: bool=False, prompt_visible: bool=False, detail_visible: bool=False, negot_visible: bool=False, effect_menu_visible: bool=False, reply_visible: bool=False) -> None:
    if not reply_visible:
        try:
            from normal_play.mages_reply_module import REPLY_OWNER, reset_mages_reply_state
            reset_mages_reply_state(w)
            if w._panel_owner == REPLY_OWNER:
                w._ui_router.clear_if_owner(REPLY_OWNER)
        except Exception:
            pass
    if not negot_visible and w._panel_owner == NEGOTIATION_OWNER:
        try:
            from normal_play.mages_negotiation_module import cleanup_mages_negotiation_if_owner
            cleanup_mages_negotiation_if_owner(w)
        except Exception:
            pass
    if not detail_visible and getattr(w, _SPELLDETAIL_KEY, None) is not None:
        setattr(w, _SPELLDETAIL_KEY, None)
        if w._panel_owner == MENU_OWNER_SPELLDETAIL:
            w._ui_router.clear_if_owner(MENU_OWNER_SPELLDETAIL)
    if not prompt_visible and getattr(w, _PROMPT_KEY, None) is not None:
        setattr(w, _PROMPT_KEY, None)
        if w._panel_owner == MENU_OWNER_PROMPT:
            w._ui_router.clear_if_owner(MENU_OWNER_PROMPT)
    if not confirm_visible and getattr(w, _CONFIRM_KEY, None) is not None:
        setattr(w, _CONFIRM_KEY, None)
        if w._panel_owner == MENU_OWNER_CONFIRM:
            w._ui_router.clear_if_owner(MENU_OWNER_CONFIRM)
    if not effect_menu_visible and getattr(w, _EFFECT_MENU_KEY, None) is not None:
        setattr(w, _EFFECT_MENU_KEY, None)
        if w._panel_owner == EFFECT_MENU_OWNER:
            w._ui_router.clear_if_owner(EFFECT_MENU_OWNER)
    if not menu_visible and getattr(w, _MENU_KEY, None) is not None:
        setattr(w, _MENU_KEY, None)
        if w._panel_owner == MENU_OWNER:
            w._ui_router.clear_if_owner(MENU_OWNER)
    if not list_visible and getattr(w, _LIST_KEY, None) is not None:
        setattr(w, _LIST_KEY, None)
        setattr(w, _LIST_TITLE_ATTR, '')
        setattr(w, _LIST_STABLE_ATTR, {})
        setattr(w, _LIST_PENDING_ATTR, {})
        try:
            if w._tab_translate.panel_mode() == 'facility_list':
                w._ui_router.set_panel_mode('translate')
        except AttributeError:
            pass
        if w._panel_owner == LIST_OWNER:
            w._ui_router.clear_if_owner(LIST_OWNER, mode='translate')
    if not spell_visible and getattr(w, _SPELL_KEY, None) is not None:
        setattr(w, _SPELL_KEY, None)
        if w._panel_owner == SPELLMAKER_OWNER:
            w._ui_router.clear_if_owner(SPELLMAKER_OWNER)
__all__ = ['poll_mages_render', 'reset_mages_render_keys', 'MENU_OWNER', 'LIST_OWNER', 'SPELLMAKER_OWNER', 'EFFECT_MENU_OWNER', 'LIST_IMGS', 'SPELLMAKER_IMG', '_read_cost_string', '_casting_cost_from_spell_cost', '_buy_price_for', '_read_spellmaker_live_spell_cost', '_resolve_spellmaker_spell_cost', '_read_effect_title']
