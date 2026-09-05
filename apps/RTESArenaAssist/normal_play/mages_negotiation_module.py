from __future__ import annotations
import logging
_log = logging.getLogger('RTESArenaAssist')
NEGOTIATION_OWNER = 'mages_negotiation'
_EMPTY_POLLS_THRESHOLD = 2
_KEY_PREV = '_mages_negot_key_prev'
_DIAG_KEY_PREV = '_mages_negot_diag_key_prev'
_PROMPTS_CTX_PREV = '_mages_negot_prompts_ctx_prev'
_EMPTY_POLLS = '_mages_negot_empty_polls'
_COUNTER_ACTIVE = '_mages_negot_counter_active'
_SPEECH_PREV = '_mages_negot_speech_prev'

def compute_speech_diff(body_lines: list[str], prev_lines) -> list[str]:
    prev = prev_lines or []
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
    if not hasattr(w, _KEY_PREV):
        setattr(w, _KEY_PREV, None)
    if not hasattr(w, _DIAG_KEY_PREV):
        setattr(w, _DIAG_KEY_PREV, None)
    if not hasattr(w, _PROMPTS_CTX_PREV):
        setattr(w, _PROMPTS_CTX_PREV, None)
    if not hasattr(w, _EMPTY_POLLS):
        setattr(w, _EMPTY_POLLS, 0)
    if not hasattr(w, _COUNTER_ACTIVE):
        setattr(w, _COUNTER_ACTIVE, False)
    if not hasattr(w, _SPEECH_PREV):
        setattr(w, _SPEECH_PREV, [])

def reset_mages_negotiation_state(w) -> None:
    setattr(w, _KEY_PREV, None)
    setattr(w, _DIAG_KEY_PREV, None)
    setattr(w, _PROMPTS_CTX_PREV, None)
    setattr(w, _EMPTY_POLLS, 0)
    setattr(w, _COUNTER_ACTIVE, False)
    setattr(w, _SPEECH_PREV, [])

def poll_mages_negotiation(w, *, img_name: str, top_level_state: str) -> bool:
    _ensure_state(w)
    setattr(w, _COUNTER_ACTIVE, False)
    if top_level_state != 'normal-play':
        return False
    profile = _get_profile(img_name)
    if profile is None:
        return False
    try:
        from negotiation_reader import read_negotiation_diagnostic
        _raw, _canon, _rendered, _text = read_negotiation_diagnostic(w._analyzer, w._anchor)
    except Exception:
        _log.exception('mages negotiation_reader failed')
        _raw = _canon = _rendered = _text = None
    _diag_key = (_raw, _rendered, _text)
    if getattr(w, _DIAG_KEY_PREV) != _diag_key:
        setattr(w, _DIAG_KEY_PREV, _diag_key)
        _suffix = ''
        if _text and _rendered:
            _suffix = _rendered[len(_text):][:32]
        elif _rendered:
            _suffix = _rendered[:32]
        _log.info('mages negotiation template raw=%r canonical=%r rendered=%r matched=%r suffix=%r', (_raw or '')[:80], (_canon or '')[:80], (_rendered or '')[:80], (_text or '')[:80], _suffix)
    try:
        import npc_dialog_lookup as _ndl
    except ImportError:
        _ndl = None
    _r = None
    if _text and _ndl is not None:
        try:
            _r = _ndl.lookup(_text)
        except Exception:
            _log.exception('mages negotiation lookup failed')
            _r = None
    _active_prompts_pairs: list[tuple[str, str]] = []
    _counter_rendered = False
    if _ndl is not None:
        try:
            from active_template_reader import read_active_template_candidates, template_surface_kind
            _ap_ctx_key = (img_name, top_level_state, 'mages_negot')
            _allow_slot = _ap_ctx_key != getattr(w, _PROMPTS_CTX_PREV)
            setattr(w, _PROMPTS_CTX_PREV, _ap_ctx_key)
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
            _log.exception('mages negotiation prompts read failed')
    setattr(w, _COUNTER_ACTIVE, _counter_rendered)
    _has_body = _r is not None
    _has_prompts = bool(_active_prompts_pairs)
    if _has_body or _has_prompts:
        setattr(w, _EMPTY_POLLS, 0)
    else:
        setattr(w, _EMPTY_POLLS, getattr(w, _EMPTY_POLLS) + 1)
    if getattr(w, _EMPTY_POLLS) >= _EMPTY_POLLS_THRESHOLD:
        _log.info('mages negotiation exit: empty body+prompts for %d polls (img=%r)', getattr(w, _EMPTY_POLLS), img_name)
        return False
    if not (_has_body or _has_prompts):
        return w._ui_router.current_owner() == NEGOTIATION_OWNER
    _btn_en = '  '.join(profile['buttons_en'])
    _btn_ja = '  '.join(profile['buttons_ja'])
    _en_lines = [_btn_en]
    _ja_lines = [_btn_ja]
    if _r is not None:
        _ja_tmpl, _ph = _r
        _ja_body = _ndl.format_japanese(_ja_tmpl, _ph)
        _en_lines.append(_text or '')
        _ja_lines.append(_ja_body)
    else:
        _ja_body = ''
    for _ap_en, _ap_ja in _active_prompts_pairs:
        _en_lines.append(_ap_en)
        _ja_lines.append(_ap_ja)
    _en_text = '\n'.join(_en_lines)
    _ja_text = '\n'.join(_ja_lines)
    _key = (_text or '', _ja_body, tuple(_active_prompts_pairs))
    if _key != getattr(w, _KEY_PREV):
        setattr(w, _KEY_PREV, _key)
        _body_lines = [ln.strip() for ln in _ja_lines[1:] if ln.strip()]
        _new_lines = compute_speech_diff(_body_lines, getattr(w, _SPEECH_PREV))
        setattr(w, _SPEECH_PREV, _body_lines)
        _speech_text = '\n'.join(_new_lines).strip()
        w._ui_router.update_translation(NEGOTIATION_OWNER, _en_text, _ja_text, speech_role='conversation', speech_text=_speech_text)
        _log.info('mages negotiation translated: body=%r prompts=%d', (_text or '')[:80], len(_active_prompts_pairs))
    return True

def cleanup_mages_negotiation_if_owner(w) -> None:
    _ensure_state(w)
    try:
        if w._ui_router.is_owner(NEGOTIATION_OWNER):
            w._ui_router.clear_if_owner(NEGOTIATION_OWNER)
            _log.info('mages negotiation exit (cleanup)')
    except AttributeError:
        pass
    reset_mages_negotiation_state(w)
__all__ = ['NEGOTIATION_OWNER', 'poll_mages_negotiation', 'cleanup_mages_negotiation_if_owner', 'reset_mages_negotiation_state', 'compute_speech_diff']
