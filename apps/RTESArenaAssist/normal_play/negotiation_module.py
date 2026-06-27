from __future__ import annotations
import logging
_log = logging.getLogger('RTESArenaAssist')
_EMPTY_POLLS_THRESHOLD = 2

def compute_speech_diff(body_lines: list[str], prev_lines, *, owner_taken: bool) -> list[str]:
    prev = [] if owner_taken else prev_lines or []
    if prev and body_lines[:len(prev)] == prev:
        return body_lines[len(prev):]
    return body_lines

def _get_profile(img_name: str):
    try:
        from negotiation_reader import get_negotiation_profile
    except ImportError:
        return None
    return get_negotiation_profile((img_name or '').upper())

def _ensure_state(w) -> None:
    if not hasattr(w, '_negot_key_prev'):
        w._negot_key_prev = None
    if not hasattr(w, '_negot_diag_key_prev'):
        w._negot_diag_key_prev = None
    if not hasattr(w, '_negot_prompts_ctx_prev'):
        w._negot_prompts_ctx_prev = None
    if not hasattr(w, '_negot_empty_polls'):
        w._negot_empty_polls = 0
    if not hasattr(w, '_negot_counter_active'):
        w._negot_counter_active = False
    if not hasattr(w, '_negot_speech_prev'):
        w._negot_speech_prev = []

def _reset_state(w) -> None:
    w._negot_key_prev = None
    w._negot_diag_key_prev = None
    w._negot_prompts_ctx_prev = None
    w._negot_empty_polls = 0
    w._negot_counter_active = False
    w._negot_speech_prev = []

def poll_negotiation(w, *, img_name: str, top_level_state: str, owner: str='negotiation') -> bool:
    _ensure_state(w)
    w._negot_counter_active = False
    if top_level_state != 'normal-play':
        return False
    profile = _get_profile(img_name)
    if profile is None:
        return False
    if getattr(w, '_tavern_rumor_flow_active', False):
        return False
    try:
        from active_template_reader import read_active_template_candidates, template_surface_kind
        for _c in read_active_template_candidates(w._analyzer, w._anchor):
            _k = template_surface_kind(_c)
            if _k and _k.startswith('tavern_'):
                return False
    except Exception:
        pass
    try:
        from negotiation_reader import read_negotiation_diagnostic
        _raw, _canon, _rendered, _text = read_negotiation_diagnostic(w._analyzer, w._anchor)
    except Exception:
        _log.exception('negotiation_reader failed')
        _raw = _canon = _rendered = _text = None
    _diag_key = (_raw, _rendered, _text)
    if w._negot_diag_key_prev != _diag_key:
        w._negot_diag_key_prev = _diag_key
        _suffix = ''
        if _text and _rendered:
            _suffix = _rendered[len(_text):][:32]
        elif _rendered:
            _suffix = _rendered[:32]
        _log.info('negotiation template raw=%r canonical=%r rendered=%r matched=%r suffix=%r', (_raw or '')[:80], (_canon or '')[:80], (_rendered or '')[:80], (_text or '')[:80], _suffix)
    try:
        import npc_dialog_lookup as _ndl
    except ImportError:
        _ndl = None
    _r = None
    if _text and _ndl is not None:
        try:
            _r = _ndl.lookup(_text)
        except Exception:
            _log.exception('negotiation lookup failed')
            _r = None
    _fallback_body = ''
    if _text and _r is None and (owner == 'equipment_negotiation'):
        _fallback_body = ' '.join(_text.split())
    _active_prompts_pairs: list[tuple[str, str]] = []
    _counter_rendered = False
    if _ndl is not None:
        try:
            from active_template_reader import read_active_template_candidates, template_surface_kind
            _ap_ctx_key = (img_name, top_level_state, 'negot')
            _allow_slot = _ap_ctx_key != w._negot_prompts_ctx_prev
            w._negot_prompts_ctx_prev = _ap_ctx_key
            for c in read_active_template_candidates(w._analyzer, w._anchor):
                try:
                    _is_counter = template_surface_kind(c) == 'negotiation_counter'
                except Exception:
                    _is_counter = False
                if c.source == 'active_slot' and (not _allow_slot) and (not _is_counter):
                    continue
                _ap_clean = c.text.rstrip()
                if not _ap_clean:
                    continue
                _apr = _ndl.lookup(_ap_clean)
                if _apr is None:
                    continue
                _apja_tmpl, _apph = _apr
                _apja = _ndl.format_japanese(_apja_tmpl, _apph)
                _active_prompts_pairs.append((_ap_clean, _apja))
                if _is_counter:
                    _counter_rendered = True
        except Exception:
            _log.exception('negotiation prompts read failed')
    w._negot_counter_active = _counter_rendered
    _has_body = _r is not None or bool(_fallback_body)
    _has_prompts = bool(_active_prompts_pairs)
    if _has_body or _has_prompts:
        w._negot_empty_polls = 0
    else:
        w._negot_empty_polls += 1
    if w._negot_empty_polls >= _EMPTY_POLLS_THRESHOLD:
        _log.info('negotiation exit: empty body+prompts for %d polls (img=%r)', w._negot_empty_polls, img_name)
        return False
    if not (_has_body or _has_prompts):
        return w._ui_router.current_owner() == owner
    _btn_en = '  '.join(profile['buttons_en'])
    _btn_ja = '  '.join(profile['buttons_ja'])
    _en_lines = [_btn_en]
    _ja_lines = [_btn_ja]
    if _r is not None:
        _ja_tmpl, _ph = _r
        _ja_body = _ndl.format_japanese(_ja_tmpl, _ph)
        _en_lines.append(_text or '')
        _ja_lines.append(_ja_body)
    elif _fallback_body:
        _ja_body = '（未登録テンプレート）'
        _en_lines.append(_fallback_body)
        _ja_lines.append(_ja_body)
    else:
        _ja_body = ''
    for _ap_en, _ap_ja in _active_prompts_pairs:
        _en_lines.append(_ap_en)
        _ja_lines.append(_ap_ja)
    _en_text = '\n'.join(_en_lines)
    _ja_text = '\n'.join(_ja_lines)
    _key = (_text or '', _ja_body, tuple(_active_prompts_pairs))
    _owner_taken = w._ui_router.current_owner() != owner
    if _key != w._negot_key_prev or _owner_taken:
        w._negot_key_prev = _key
        _body_lines = [ln.strip() for ln in _ja_lines[1:] if ln.strip()]
        _new_lines = compute_speech_diff(_body_lines, w._negot_speech_prev, owner_taken=_owner_taken)
        w._negot_speech_prev = _body_lines
        _speech_text = '\n'.join(_new_lines).strip()
        w._ui_router.update_translation(owner, _en_text, _ja_text, speech_role='conversation', speech_text=_speech_text)
        _log.info('negotiation translated: owner=%s body=%r prompts=%d', owner, (_text or '')[:80], len(_active_prompts_pairs))
    return True

def cleanup_if_owner(w, *, owner: str='negotiation') -> None:
    _ensure_state(w)
    try:
        if w._ui_router.is_owner(owner):
            w._ui_router.clear_if_owner(owner)
            _log.info('negotiation exit (cleanup owner=%s)', owner)
    except AttributeError:
        pass
    _reset_state(w)
__all__ = ['poll_negotiation', 'cleanup_if_owner', 'compute_speech_diff']
