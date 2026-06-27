from __future__ import annotations
import logging
from assist_log import recog as _recog
_log = logging.getLogger('RTESArenaAssist')
_ALLOWED_IMGS = frozenset({'', 'MENU_RT.IMG', 'YESNO.IMG', 'NEWPOP.IMG', 'FACES00.CIF'})
_RESPONSE_HOLD_POLLS = 18
_BLESSING_TEMPLATE_PTR = 30115
_BLESSING_TEMPLATE_TEXT = 'Receive our blessings...'
_BLESSING_TEMPLATE_IMGS = frozenset({'MENU_RT.IMG', 'YESNO.IMG', 'NEWPOP.IMG'})
_RESULT_SURFACE_PTR_OFFSET = 43268
_RESULT_INTENT_HINT_OFFSET = 44470
_RESULT_INTENT_HEAL_VALUE = 133
_RESULT_INTENT_CURE_VALUE = 243

def _result_episode_signature(edge_sig, p8f6e):
    if edge_sig is None and p8f6e is None:
        return None
    return (edge_sig, p8f6e)

def _read_result_surface_ptr(w) -> int | None:
    try:
        raw = w._analyzer.read_bytes(w._anchor + _RESULT_SURFACE_PTR_OFFSET, 2)
    except (OSError, AttributeError):
        return None
    if not raw or len(raw) < 2:
        return None
    ptr = raw[0] | raw[1] << 8
    if ptr < 4096:
        return None
    return ptr

def _read_result_intent_hint(w) -> int | None:
    try:
        raw = w._analyzer.read_bytes(w._anchor + _RESULT_INTENT_HINT_OFFSET, 1)
    except (OSError, AttributeError):
        return None
    if not raw:
        return None
    return raw[0]

def _result_intent_name(value: int | None) -> str:
    if value == _RESULT_INTENT_HEAL_VALUE:
        return 'heal'
    if value == _RESULT_INTENT_CURE_VALUE:
        return 'cure'
    return ''

def _extend_current_template_candidate(w, candidates: list, *, phase: str='', armed: bool=False, img_name: str='') -> list:
    try:
        from active_template_reader import read_active_template_candidates
        from temple_dialog_reader import TempleResponseCandidate, is_temple_priest_text, lookup_temple_priest_text
    except ImportError:
        return candidates
    try:
        tmpl_candidates = read_active_template_candidates(w._analyzer, w._anchor)
    except Exception:
        return candidates
    out = list(candidates)
    seen = {(c.source_offset, c.text) for c in out}
    for c in tmpl_candidates:
        source = getattr(c, 'source', '') or ''
        ptr = getattr(c, 'ptr', 0) or 0
        text = (getattr(c, 'text', '') or '').rstrip()
        if source == 'current_ptr':
            pass
        elif source == 'active_slot':
            holding_same_blessing = getattr(w, '_temple_dialog_current_text', None) == _BLESSING_TEMPLATE_TEXT
            if not (ptr == _BLESSING_TEMPLATE_PTR and text == _BLESSING_TEMPLATE_TEXT and (phase in ('select_input', 'result')) and (armed or holding_same_blessing) and ((img_name or '').upper() in _BLESSING_TEMPLATE_IMGS)):
                continue
        else:
            continue
        if '%' in text:
            continue
        if not is_temple_priest_text(text):
            continue
        if lookup_temple_priest_text(text) is None:
            continue
        key = (ptr, text)
        if key in seen:
            continue
        seen.add(key)
        out.append(TempleResponseCandidate(text=text, lookup_hit=True, source_offset=ptr, raw_text=text))
    return out

def _classify_kind(text: str) -> str:
    s = ' '.join((text or '').split())
    if s.startswith('This service will cost'):
        return 'cost'
    if s.startswith('How much do you wish to donate?'):
        return 'prompt'
    return 'result'

def _owner_for_kind(kind: str) -> str:
    if kind == 'cost':
        return 'temple_cost'
    if kind == 'prompt':
        return 'temple_prompt'
    return 'temple_priest_reply'

def _is_blessing_result(c) -> bool:
    s = ' '.join((getattr(c, 'text', '') or '').split())
    return getattr(c, 'source_offset', 0) == _BLESSING_TEMPLATE_PTR and s.startswith('Receive our blessings')

def _is_donation_blessing_state(w, *, view, img: str) -> bool:
    return getattr(view, 'kind', '') == 'donation_blessing' and (img or '').upper() in _BLESSING_TEMPLATE_IMGS

def _is_cannot_cure_result(c) -> bool:
    s = ' '.join((getattr(c, 'text', '') or '').split())
    return s.startswith('We humbly beg your forgivness')

def _is_perfect_condition_result(c) -> bool:
    s = ' '.join((getattr(c, 'text', '') or '').split())
    return 'is in perfect condition' in s

def _is_heal_result(c) -> bool:
    s = ' '.join((getattr(c, 'text', '') or '').split())
    return 'thou art healed' in s or 'is in perfect condition' in s

def _snapshot_episode_baseline(w, candidates) -> None:
    w._temple_reply_episode_baseline = {c.source_offset: c.text for c in candidates}

def _snapshot_edge_baseline(w, edge) -> None:
    w._temple_reply_edge_baseline = edge
    w._temple_reply_edge_consumed = edge

def _reset_state(w) -> None:
    w._temple_dialog_text_by_offset = {}
    w._temple_dialog_current_key = None
    w._temple_dialog_current_text = None
    w._temple_dialog_current_owner = None
    w._temple_dialog_baselined = False
    w._temple_dialog_hold_polls = 0
    w._temple_reply_armed = False
    w._temple_reply_episode_id = 0
    w._temple_reply_episode_baseline = {}
    w._temple_reply_edge_baseline = None
    w._temple_reply_edge_consumed = None
    w._temple_dialog_last_diag_key = None

def reset_temple_dialog_state(w) -> None:
    _reset_state(w)

def reset_temple_reply_on_stop(w) -> None:
    if getattr(w, '_temple_dialog_baselined', False):
        _release_reply(w)
        _reset_state(w)

def _ensure_state(w) -> None:
    for attr, default in (('_temple_dialog_text_by_offset', {}), ('_temple_dialog_current_key', None), ('_temple_dialog_current_text', None), ('_temple_dialog_current_owner', None), ('_temple_dialog_baselined', False), ('_temple_dialog_hold_polls', 0), ('_temple_reply_armed', False), ('_temple_reply_episode_id', 0), ('_temple_reply_episode_baseline', {}), ('_temple_reply_edge_baseline', None), ('_temple_reply_edge_consumed', None), ('_temple_dialog_last_diag_key', None)):
        if not hasattr(w, attr):
            setattr(w, attr, default)

def _with_yesno_buttons(img_name: str, kind: str, en: str, ja: str) -> tuple[str, str]:
    if kind != 'cost' or (img_name or '').upper() != 'YESNO.IMG':
        return (en, ja)
    try:
        from negotiation_reader import get_negotiation_profile
        profile = get_negotiation_profile('YESNO.IMG')
    except ImportError:
        profile = None
    if not profile:
        return (en, ja)
    en_buttons = '  '.join(profile['buttons_en'])
    ja_buttons = '  '.join(profile['buttons_ja'])
    return (f'{en_buttons}\n{en}', f'{ja_buttons}\n{ja}')

def _release_reply(w) -> None:
    owner = getattr(w, '_temple_dialog_current_owner', None)
    w._temple_dialog_current_key = None
    w._temple_dialog_current_text = None
    w._temple_dialog_current_owner = None
    w._temple_dialog_hold_polls = 0
    if not owner:
        return
    try:
        if w._ui_router.current_owner() == owner:
            w._ui_router.clear_if_owner(owner)
    except Exception:
        pass

def poll_temple_dialog(w, *, temple_active: bool, temple_just_started: bool, img_name: str, shop_menu_visible: bool, menu_foreground: bool=False, popup_foreground: bool=False) -> bool:
    _ensure_state(w)
    if not temple_active:
        return False
    img = (img_name or '').upper()
    if img not in _ALLOWED_IMGS:
        return False
    if temple_just_started:
        _reset_state(w)
    try:
        from temple_dialog_reader import TempleResponseCandidate, classify_temple_view, format_temple_priest_text, is_transient_priest_text, read_popup_gate, read_temple_result_edge_signature, read_temple_response_candidates
        read = read_temple_response_candidates(w._analyzer, w._anchor)
        gate = read_popup_gate(w._analyzer, w._anchor)
        edge_sig = read_temple_result_edge_signature(w._analyzer, w._anchor)
        view = classify_temple_view(w._analyzer, w._anchor)
        phase, _phase_vals = (view.phase, view.values)
    except Exception:
        _log.exception('temple_dialog response read failed')
        return False
    try:
        _b6e = w._analyzer.read_bytes(w._anchor + 36718, 2)
        _p8f6e = _b6e[0] | _b6e[1] << 8 if len(_b6e) >= 2 else None
    except (OSError, AttributeError):
        _p8f6e = None
    _surface_ptr = _read_result_surface_ptr(w)
    _intent_hint_value = _read_result_intent_hint(w)
    _result_intent = _result_intent_name(_intent_hint_value)
    result_sig = _result_episode_signature(edge_sig, _p8f6e)
    hold = int(getattr(w, '_temple_dialog_hold_polls', 0) or 0)
    armed = bool(getattr(w, '_temple_reply_armed', False))
    candidates = _extend_current_template_candidate(w, list(read.candidates), phase=phase, armed=armed, img_name=img)
    episode = int(getattr(w, '_temple_reply_episode_id', 0) or 0)
    ep_base = dict(getattr(w, '_temple_reply_episode_baseline', {}))
    edge_base = getattr(w, '_temple_reply_edge_baseline', None)
    edge_consumed = getattr(w, '_temple_reply_edge_consumed', None)
    if temple_just_started:
        _snapshot_episode_baseline(w, candidates)
        _snapshot_edge_baseline(w, result_sig)
        return False

    def _diag(outcome: str) -> None:
        try:
            cset = ' | '.join((f"0x{c.source_offset:X}:{c.text[:22]}{('(raw:' + c.raw_text[:12] + ')' if c.raw_text and c.raw_text != c.text else '')}" for c in candidates))
            dkey = (gate, _p8f6e, result_sig, _intent_hint_value, getattr(view, 'kind', ''), cset, outcome, bool(menu_foreground), bool(popup_foreground), episode, armed, _surface_ptr)
            if dkey == getattr(w, '_temple_dialog_last_diag_key', None):
                return
            w._temple_dialog_last_diag_key = dkey
            g = f'0x{gate:02X}' if isinstance(gate, int) else '?'
            p = f'0x{_p8f6e:04X}' if isinstance(_p8f6e, int) else '?'
            sp = f'0x{_surface_ptr:04X}' if isinstance(_surface_ptr, int) else '?'
            ih = f'0x{_intent_hint_value:02X}/{_result_intent}' if isinstance(_intent_hint_value, int) else '?'
            _recog(_log, 'temple_dialog: gate=%s 8F6E=%s surf=%s intent=%s edge=%s view=%s phase=%s menu_fg=%s popup_fg=%s ep=%d armed=%s img=%r outcome=%s cands=[%s]', g, p, sp, ih, edge_sig, getattr(view, 'kind', ''), phase, bool(menu_foreground), bool(popup_foreground), episode, armed, img, outcome, cset)
        except Exception:
            pass
    transients = [c for c in candidates if is_transient_priest_text(c.text)]
    nontrans = [c for c in candidates if not is_transient_priest_text(c.text)]
    results = [c for c in nontrans if _classify_kind(c.text) == 'result']
    costs = [c for c in nontrans if _classify_kind(c.text) == 'cost']
    prompts = [c for c in nontrans if _classify_kind(c.text) == 'prompt']

    def _is_new(c):
        return ep_base.get(c.source_offset) != c.text
    current_text = getattr(w, '_temple_dialog_current_text', None)
    current_cp_visible = bool(current_text and any((c.text == current_text for c in costs + prompts)))
    yesno_cost_prompt_present = phase != 'menu' and img == 'YESNO.IMG' and bool(costs or prompts)
    cost_prompt_foreground = yesno_cost_prompt_present and (current_cp_visible or getattr(w, '_temple_dialog_current_owner', None) in ('temple_cost', 'temple_prompt') or any((_is_new(c) for c in costs + prompts)))
    if menu_foreground and (not cost_prompt_foreground):
        w._temple_reply_armed = True
        _snapshot_episode_baseline(w, candidates)
        _snapshot_edge_baseline(w, result_sig)
        _release_reply(w)
        _diag('release_menu')
        return False
    if menu_foreground and cost_prompt_foreground:
        _diag('ignore_menu_fg_cost_prompt')
    if phase == 'out':
        _release_reply(w)
        w._temple_reply_armed = False
        w._temple_dialog_hold_polls = 0
        _diag('release_phase_out')
        return False

    def _rank(pool, *, prefer_cannot_cure: bool=False, result_intent: str=''):
        pool = list(pool)

        def _base_key(c):
            return (0 if _is_blessing_result(c) else 1, c.source_offset)
        if result_intent == 'heal':
            preferred = [c for c in pool if _is_blessing_result(c) or _is_heal_result(c)]
            if preferred:
                rest = [c for c in pool if c not in preferred]
                return sorted(preferred, key=_base_key) + sorted(rest, key=_base_key)
        elif result_intent == 'cure':
            preferred = [c for c in pool if _is_cannot_cure_result(c)]
            if preferred:
                rest = [c for c in pool if c not in preferred]
                return sorted(preferred, key=_base_key) + sorted(rest, key=_base_key)
        has_perfect = any((_is_perfect_condition_result(c) for c in pool))

        def _key(c):
            cannot_rank = 0 if prefer_cannot_cure and (not has_perfect) and _is_cannot_cure_result(c) else 1
            return (0 if _is_blessing_result(c) else 1, cannot_rank, c.source_offset)
        return sorted(pool, key=_key)
    new_results = [c for c in results if _is_new(c)]
    new_costs = [c for c in costs if _is_new(c)]
    new_prompts = [c for c in prompts if _is_new(c)]
    new_transients = [c for c in transients if _is_new(c)]
    result_edge = armed and phase == 'result' and (result_sig is not None) and (edge_base is not None) and (result_sig != edge_base) and (result_sig != edge_consumed)
    donation_blessing_state = _is_donation_blessing_state(w, view=view, img=img)

    def _append_synth_blessing() -> object:
        synth = TempleResponseCandidate(text=_BLESSING_TEMPLATE_TEXT, lookup_hit=True, source_offset=_BLESSING_TEMPLATE_PTR, raw_text=_BLESSING_TEMPLATE_TEXT)
        if not any((_is_blessing_result(c) for c in candidates)):
            candidates.append(synth)
            results.append(synth)
        return synth
    chosen = None
    reason = ''
    new_episode = False
    if phase == 'select_input':
        blessing_results = [c for c in results if _is_blessing_result(c)]
        new_blessing_results = [c for c in new_results if _is_blessing_result(c)]
        if current_text and any((c.text == current_text for c in blessing_results)):
            for c in blessing_results:
                if c.text == current_text:
                    chosen, reason = (c, 'hold')
                    break
        elif donation_blessing_state:
            chosen, reason = (_append_synth_blessing(), 'donation_blessing')
        elif getattr(w, '_temple_dialog_current_owner', None) == 'temple_priest_reply':
            _release_reply(w)
        if chosen is not None:
            pass
        elif new_blessing_results:
            chosen, reason, new_episode = (_rank(new_blessing_results)[0], 'blessing_new', True)
        elif armed and donation_blessing_state and (not new_costs) and (not new_prompts):
            chosen, reason, new_episode = (_append_synth_blessing(), 'blessing_donate_edge', True)
        elif new_costs:
            chosen, reason = (_rank(new_costs)[0], 'cost_new')
        elif new_prompts:
            chosen, reason = (_rank(new_prompts)[0], 'prompt_new')
        else:
            w._temple_dialog_hold_polls = 0
            _diag(f'select_input_no_reply(results={len(results)},costs={len(costs)},prompts={len(prompts)})')
            return False
    elif new_costs:
        chosen, reason = (_rank(new_costs)[0], 'cost_new')
    elif new_prompts:
        chosen, reason = (_rank(new_prompts)[0], 'prompt_new')
    elif new_results:
        chosen, reason, new_episode = (_rank(new_results, result_intent=_result_intent)[0], 'result_new', True)
    elif hold > 0 and current_text and any((c.text == current_text for c in candidates)):
        for c in candidates:
            if c.text == current_text:
                chosen, reason = (c, 'hold')
                break
    elif yesno_cost_prompt_present and (costs or prompts) and result_edge and (not _result_intent):
        chosen, reason = (_rank(costs or prompts)[0], 'yesno_cost_prompt_present')
    elif new_transients:
        chosen, reason = (_rank(new_transients)[0], 'transient_new')
    elif result_edge and results and (_result_intent or not yesno_cost_prompt_present):
        suffix = f'_{_result_intent}' if _result_intent else ''
        chosen, reason, new_episode = (_rank(results, prefer_cannot_cure=True, result_intent=_result_intent)[0], f'result_edge{suffix}', True)
    elif popup_foreground and (costs or prompts):
        chosen, reason = (_rank(costs or prompts)[0], 'popup_present_cp')
    elif popup_foreground and transients:
        chosen, reason, new_episode = (_rank(transients)[0], 'popup_transient', True)
    now_by_offset = dict(getattr(w, '_temple_dialog_text_by_offset', {}))
    for c in candidates:
        now_by_offset[c.source_offset] = c.text
    w._temple_dialog_text_by_offset = now_by_offset
    w._temple_dialog_baselined = True
    if chosen is None:
        w._temple_dialog_hold_polls = max(hold - 1, 0)
        _diag(f'none(results={len(results)},new_res={len(new_results)},costs={len(costs)},prompts={len(prompts)})')
        return False
    kind = 'transient' if is_transient_priest_text(chosen.text) else _classify_kind(chosen.text)
    is_reply = kind in ('result', 'transient')
    if is_reply:
        if new_episode:
            episode += 1
            w._temple_reply_episode_id = episode
            if result_sig is not None:
                w._temple_reply_edge_consumed = result_sig
            ep_base = dict(getattr(w, '_temple_reply_episode_baseline', {}))
            ep_base[chosen.source_offset] = chosen.text
            w._temple_reply_episode_baseline = ep_base
        w._temple_reply_armed = False
    else:
        w._temple_reply_armed = True
        _snapshot_episode_baseline(w, candidates)
        _snapshot_edge_baseline(w, result_sig)
    ja = format_temple_priest_text(chosen.text)
    if ja is None:
        w._temple_dialog_hold_polls = max(hold - 1, 0)
        _diag(f'lookup_miss:{chosen.text[:22]}')
        return False
    en_text, ja_text = _with_yesno_buttons(img, kind, chosen.text, ja)
    owner = _owner_for_kind(kind)
    key = (owner, img, chosen.source_offset, chosen.text, ja_text, episode)
    owner_taken = w._ui_router.current_owner() != owner
    if reason == 'hold':
        w._temple_dialog_hold_polls = max(hold, 1)
    else:
        w._temple_dialog_hold_polls = _RESPONSE_HOLD_POLLS
    should_update = key != w._temple_dialog_current_key or owner_taken
    if should_update:
        w._temple_dialog_current_key = key
        w._temple_dialog_current_text = chosen.text
        w._temple_dialog_current_owner = owner
        _speech_role = 'conversation' if owner == 'temple_priest_reply' else None
        w._ui_router.update_translation(owner, en_text, ja_text, speech_role=_speech_role, speech_text=ja)
        _log.info('temple_dialog translated: owner=%s src=0x%X reason=%s ep=%d img=%r text=%r', owner, chosen.source_offset, reason, episode, img, chosen.text[:80])
    _diag(f'render:{reason}:{owner}:{chosen.text[:22]}')
    return True
__all__ = ['poll_temple_dialog', 'reset_temple_dialog_state']
