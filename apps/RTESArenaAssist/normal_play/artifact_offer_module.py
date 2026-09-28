from __future__ import annotations
import logging
import sys
_log = logging.getLogger('RTESArenaAssist')
ARTIFACT_OFFER_OWNER = 'artifact_offer'
_NEGOTIATION_IMG = 'NEGOTBUT.IMG'
_TEXT_OFFSET = 37534
_TEXT_MAXLEN = 39034 - 37534
_COUNTER_SURFACE = 'negotiation_counter'
_BUTTONS = (('ACCEPT', 'negotiation.accept'), ('COUNTER', 'negotiation.counter'), ('REJECT', 'negotiation.reject'))
_BUTTON_SEP = '  '

def _ensure_state(w) -> None:
    if not hasattr(w, '_artifact_offer_key_prev'):
        _reset_state(w)

def _log_failure_once(w, where: str) -> None:
    logged = getattr(w, '_artifact_offer_failures_logged', None)
    if logged is None:
        logged = w._artifact_offer_failures_logged = set()
    exc = sys.exc_info()[1]
    key = (where, type(exc).__name__, str(exc))
    if key in logged:
        return
    logged.add(key)
    _log.exception('artifact offer: %s failed', where)

def _reset_state(w) -> None:
    w._artifact_offer_key_prev = None
    w._artifact_offer_prompt_stale = None

def _read_text(w) -> str | None:
    try:
        raw = w._analyzer.read_bytes(w._anchor + _TEXT_OFFSET, _TEXT_MAXLEN)
    except (OSError, AttributeError):
        return None
    nul = raw.find(b'\x00')
    if nul <= 0:
        return None
    return raw[:nul].decode('latin-1')

def _read_counter_prompts(w) -> dict | None:
    out: dict = {}
    try:
        from active_template_reader import candidate_signature, read_active_template_candidates, template_surface_kind
        for c in read_active_template_candidates(w._analyzer, w._anchor):
            if template_surface_kind(c) == _COUNTER_SURFACE:
                text = c.text.rstrip()
                if text:
                    out[candidate_signature(c)] = text
    except Exception:
        _log_failure_once(w, 'counter prompt read')
        return None
    return out

def _current_counter_prompt(w) -> str | None:
    found = _read_counter_prompts(w)
    if found is None:
        return None
    now = frozenset(found)
    if w._artifact_offer_prompt_stale is None:
        w._artifact_offer_prompt_stale = now
    else:
        w._artifact_offer_prompt_stale &= now
    for sig, text in found.items():
        if sig not in w._artifact_offer_prompt_stale:
            return text
    return None

def _button_rows() -> tuple[str, str]:
    import i18n_helper as i18n
    return (_BUTTON_SEP.join((en for en, _key in _BUTTONS)), _BUTTON_SEP.join((i18n.tr(key) for _en, key in _BUTTONS)))

def poll_artifact_offer(w, *, img_name: str, top_level_state: str) -> bool:
    _ensure_state(w)
    if top_level_state != 'normal-play':
        return False
    if (img_name or '').upper() != _NEGOTIATION_IMG:
        return False
    text = _read_text(w)
    if not text:
        return False
    try:
        import npc_dialog_lookup as ndl
        hit = ndl.match_artifact_dialog(text)
    except Exception:
        _log_failure_once(w, 'lookup')
        return False
    if hit is None:
        return False
    body_en = ' '.join(text.split())
    body_tr = ndl.format_japanese(hit.ja_template, hit.placeholders)
    line_en, line_tr, speech = (body_en, body_tr, body_tr)
    counter_input = False
    prompt_en = _current_counter_prompt(w)
    if prompt_en:
        prompt_hit = ndl.lookup(prompt_en)
        line_en = prompt_en
        if prompt_hit is not None:
            line_tr = speech = ndl.format_japanese(*prompt_hit)
        else:
            line_tr, speech = (prompt_en, '')
        counter_input = True
    btn_en, btn_tr = _button_rows()
    en_text = f'{btn_en}\n{line_en}'
    tr_text = f'{btn_tr}\n{line_tr}'
    key = (en_text, tr_text)
    if key != w._artifact_offer_key_prev:
        w._artifact_offer_key_prev = key
        w._ui_router.update_translation(ARTIFACT_OFFER_OWNER, en_text, tr_text, speech_role='conversation', speech_text=speech)
        _log.info('artifact offer translated: ref=%s counter_input=%s len=%d', hit.ref, counter_input, len(line_en))
    return True

def release_artifact_offer(w) -> None:
    _ensure_state(w)
    try:
        if w._ui_router.is_owner(ARTIFACT_OFFER_OWNER):
            w._ui_router.clear_if_owner(ARTIFACT_OFFER_OWNER)
            _log.info('artifact offer exit')
    except AttributeError:
        pass
    _reset_state(w)
__all__ = ['ARTIFACT_OFFER_OWNER', 'poll_artifact_offer', 'release_artifact_offer']
