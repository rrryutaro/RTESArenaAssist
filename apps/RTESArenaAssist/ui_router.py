from __future__ import annotations
from dataclasses import replace
import logging
from typing import Optional
import assist_settings as settings
import i18n_helper as i18n
from assist_log import recog as _recog
from display_intent import DisplayIntent, PollFrame
from hierarchy_state import active_facility_session_name, facility_owners_for_session, CONVERSATION_PANEL_OWNERS
from panel_mode_resolver import closing_panel_mode as _closing_panel_mode, panel_is_effective, required_owner_for_mode, resolve_flush_mode, restore_translate_target
_log = logging.getLogger('RTESArenaAssist')
SCREEN_CHANGE_CLEAR_PRIORITY = -1
_CONVERSATION_TAB_OWNERS = CONVERSATION_PANEL_OWNERS

class UiRouter:

    def __init__(self, window) -> None:
        self._window = window
        self._poll_frame: Optional[PollFrame] = None
        self._pending_display: Optional[DisplayIntent] = None
        self._pending_order = 0
        self._pending_display_order = 0
        self._translation_observer = None
        self._obs_last_key = None
        self._unit_end_observer = None
        self._displayed_translation: Optional[tuple[str, str, str]] = None

    def set_translation_observer(self, callback) -> None:
        self._translation_observer = callback

    def set_unit_end_observer(self, callback) -> None:
        self._unit_end_observer = callback

    def notify_display_unit_closed(self, panel_owner: str) -> None:
        self._notify_clear(panel_owner)

    def notify_display_context_ended(self, panel_owner: str) -> None:
        self._emit_unit_end(panel_owner, 'context_ended', forget_key=True)

    def notify_display_unit_replaced(self, panel_owner: str) -> None:
        self._emit_unit_end(panel_owner, 'replaced', forget_key=True)

    def notify_display_page_ended(self, panel_owner: str) -> None:
        self._emit_unit_end(panel_owner, 'page_ended', forget_key=False)

    def _notify_clear(self, owner: str) -> None:
        self._emit_unit_end(owner, 'cleared', forget_key=True)

    def _emit_unit_end(self, owner: str, reason: str, *, forget_key: bool) -> None:
        if not owner:
            return
        if forget_key and self._obs_last_key is not None and (self._obs_last_key[0] == owner):
            self._obs_last_key = None
        if self._unit_end_observer is None:
            return
        try:
            self._unit_end_observer(owner, reason)
        except Exception:
            _log.exception('unit_end_observer failed')

    def begin_poll_frame(self, frame: PollFrame) -> None:
        self._poll_frame = frame
        self._pending_display = None
        self._pending_order = 0
        self._pending_display_order = 0

    def _owner_gate_passes(self, intent: DisplayIntent) -> bool:
        current = self.current_owner()
        if intent.allowed_current_owners is not None and current not in intent.allowed_current_owners:
            return False
        if intent.kind in ('clear_if_owner', 'release_if_owner') and current != intent.panel_owner:
            return False
        return True

    def propose_display(self, intent: DisplayIntent) -> bool:
        resolved = self._resolve_proposed_intent(intent)
        if self._poll_frame is None:
            if resolved is not None:
                self.apply_display(resolved)
            self._apply_flush_panel_mode(intent)
            return resolved is not None
        if resolved is None:
            return False
        self._pending_order += 1
        current = self._pending_display
        merged = self._merge_compatible_intents(current, resolved)
        if merged is not None:
            self._pending_display = merged
            self._pending_display_order = self._pending_order
            self._apply_logical_display(merged)
            return True
        if current is None or (resolved.priority, self._pending_order) >= (current.priority, self._pending_display_order):
            self._pending_display = resolved
            self._pending_display_order = self._pending_order
            self._apply_logical_display(resolved)
        return True

    def _merge_compatible_intents(self, current: Optional[DisplayIntent], resolved: DisplayIntent) -> Optional[DisplayIntent]:
        if current is None or current.priority != resolved.priority:
            return None
        if current.kind == 'panel_mode' and resolved.kind == 'translation':
            if current.mode is not None and (resolved.mode is None or resolved.mode == current.mode):
                return replace(resolved, mode=current.mode)
        if current.kind == 'translation' and resolved.kind == 'panel_mode':
            if resolved.mode is not None and (current.mode is None or current.mode == resolved.mode):
                return replace(current, mode=resolved.mode)
        if current.kind == 'translation' and resolved.kind == 'translation':
            if current.mode is not None and (resolved.mode is None or resolved.mode == current.mode):
                return replace(resolved, mode=current.mode)
        return None

    def pending_display(self) -> Optional[DisplayIntent]:
        return self._pending_display

    def flush_poll_display(self) -> None:
        intent = self._pending_display
        frame = self._poll_frame
        self._poll_frame = None
        self._pending_display = None
        self._pending_order = 0
        self._pending_display_order = 0
        if intent is not None:
            self.apply_display(intent)
        self._apply_flush_panel_mode(intent)
        self._log_flush_winner(intent, frame)
        self._log_facility_display_invariant(frame)

    def _winner_has_content(self, intent: Optional[DisplayIntent]) -> bool:
        if intent is None:
            return False
        if intent.kind == 'translation':
            en = (intent.en or '').strip()
        else:
            return False
        try:
            nd = i18n.tr('translate.no_data')
        except Exception:
            nd = ''
        return bool(en) and en not in ('—', nd)

    @staticmethod
    def _flush_mode_settings() -> tuple[bool, str]:
        try:
            emulate = bool(settings.get('translate_tab_emulate_panel_hidden', False))
            fb = settings.get('translate_fallback_screen', 'map')
        except Exception:
            emulate, fb = (False, 'map')
        return (emulate, fb)

    def _panel_active(self, emulate: bool) -> bool:
        return panel_is_effective(panel_present=getattr(self._window, '_layout_translate_panel', None) is not None, emulate_panel_hidden=emulate)

    def _apply_flush_panel_mode(self, intent: Optional[DisplayIntent]) -> None:
        tab = getattr(self._window, '_tab_translate', None)
        if tab is None:
            return
        try:
            cur = tab.panel_mode()
        except AttributeError:
            return
        owner_now = self.current_owner()
        target = self._resolve_flush_target(intent, cur, owner_now)
        if target is None or target == cur:
            return
        if required_owner_for_mode(cur) is not None:
            _recog(_log, 'owner-bound panel mode released: mode=%r owner=%r → %r', cur, owner_now, target)
        tab.set_panel_mode(target)

    def _resolve_flush_target(self, intent: Optional[DisplayIntent], cur: str, owner_now: str) -> Optional[str]:
        emulate, fb = self._flush_mode_settings()
        panel_active = self._panel_active(emulate)
        top_level = getattr(self._window, '_top_level_state', 'pregame')
        if intent is None or intent.kind == 'release_if_owner':
            if required_owner_for_mode(cur) is None:
                return None
            return resolve_flush_mode(winner_mode=cur, top_level=top_level, emulate=emulate, winner_has_content=False, winner_is_tab_owner=False, fallback_setting=fb, current_owner=owner_now, panel_active=panel_active)
        return resolve_flush_mode(winner_mode=intent.mode if intent.mode is not None else cur, top_level=top_level, emulate=emulate, winner_has_content=self._winner_has_content(intent), winner_is_tab_owner=bool(intent.kind == 'translation' and (intent.panel_owner or '') in _CONVERSATION_TAB_OWNERS), fallback_setting=fb, current_owner=owner_now, panel_active=panel_active)

    def _log_flush_winner(self, intent: Optional[DisplayIntent], frame: Optional[PollFrame]) -> None:
        if intent is None:
            key = ('<none>', '', '', 0, '')
        else:
            key = (intent.kind, intent.panel_owner or '', intent.mode or '', intent.priority, intent.closed_owner or '')
        prev = getattr(self, '_winner_key', None)
        if key == prev:
            return
        self._winner_key = key

        def _idle(k) -> bool:
            return k is not None and k[0] in ('<none>', 'clear') and (not k[1]) and (not k[4])
        if _idle(key) and _idle(prev):
            return
        try:
            tab_mode = self._window._tab_translate.panel_mode()
        except (AttributeError, RuntimeError):
            tab_mode = '?'
        _recog(_log, 'flush winner: kind=%s owner=%r mode=%r prio=%d closed=%r tab_mode=%r owner_now=%r reason=%r', key[0], key[1], key[2], key[3], key[4], tab_mode, self.current_owner(), intent.reason if intent is not None else '')

    def _resolve_proposed_intent(self, intent: DisplayIntent) -> Optional[DisplayIntent]:
        current = self.current_owner()
        applied_owner = self._poll_frame.panel_owner if self._poll_frame is not None else current
        if not self._owner_gate_passes(intent):
            if intent.kind == 'translation':
                _recog(_log, 'display proposal gated: owner=%s current=%s reason=%s', intent.panel_owner or '-', current or '-', intent.reason or '-')
            elif intent.allowed_current_owners is not None:
                _log.debug('ui_router.propose_display skipped (kind=%s owner=%r current=%r allowed=%r)', intent.kind, intent.panel_owner, current, intent.allowed_current_owners)
            return None
        if intent.allowed_current_owners is not None:
            intent = replace(intent, allowed_current_owners=None)
        if intent.kind == 'clear':
            return intent if intent.closed_owner else replace(intent, closed_owner=applied_owner)
        if intent.kind == 'clear_if_owner':
            return DisplayIntent.clear('', mode=intent.mode, clear_place_list=intent.clear_place_list, clear_travel_table=intent.clear_travel_table, priority=intent.priority, reason=intent.reason, closed_owner=applied_owner, notify_close=intent.notify_close)
        if intent.kind == 'release_if_owner':
            return DisplayIntent.claim_owner('', mode=intent.mode, priority=intent.priority, reason=intent.reason, closed_owner=applied_owner)
        return intent

    def _apply_logical_display(self, intent: DisplayIntent) -> None:
        self._write_owner(intent)
    _OWNER_WRITING_KINDS = frozenset({'clear', 'claim_owner', 'combat_info', 'shop_buy_list', 'facility_list', 'spellbook', 'item_pickup_list', 'load_screen_slots', 'equipment_list', 'spell_detail', 'place_list', 'travel_table', 'journal_entries'})

    def _write_owner(self, intent: DisplayIntent) -> None:
        if intent.kind == 'translation':
            if not intent.keep_owner:
                self._window._panel_owner = intent.panel_owner
            return
        if intent.kind in self._OWNER_WRITING_KINDS:
            self._window._panel_owner = intent.panel_owner

    def update_translation(self, panel_owner: str, en: str, ja: str, *, mode: Optional[str]='translate', panel_en: Optional[str]=None, panel_ja: Optional[str]=None, update_panel: bool=True, update_tab: bool=True, keep_owner: bool=False, clear_place_list: bool=False, priority: int=0, reason: str='', speech_role: Optional[str]=None, speech_text: Optional[str]=None, speech_action: str='replace', allowed_current_owners: Optional[tuple[str, ...]]=None, skip_if_displaying: bool=False) -> bool:
        if skip_if_displaying and self.is_displaying(panel_owner, en, ja):
            return False
        return self.propose_display(DisplayIntent.translation(panel_owner, en, ja, mode=mode, panel_en=panel_en, panel_ja=panel_ja, update_panel=update_panel, update_tab=update_tab, keep_owner=keep_owner, clear_place_list=clear_place_list, priority=priority, reason=reason, allowed_current_owners=allowed_current_owners, speech_role=speech_role, speech_text=speech_text, speech_action=speech_action))

    def propose_translation(self, panel_owner: str, en: str, ja: str, *, mode: Optional[str]='translate', panel_en: Optional[str]=None, panel_ja: Optional[str]=None, update_panel: bool=True, update_tab: bool=True, keep_owner: bool=False, clear_place_list: bool=False, priority: int=0, reason: str='', speech_role: Optional[str]=None, speech_text: Optional[str]=None, speech_action: str='replace') -> None:
        self.propose_display(DisplayIntent.translation(panel_owner, en, ja, mode=mode, panel_en=panel_en, panel_ja=panel_ja, update_panel=update_panel, update_tab=update_tab, keep_owner=keep_owner, clear_place_list=clear_place_list, priority=priority, reason=reason, speech_role=speech_role, speech_text=speech_text, speech_action=speech_action))
    _RENDERERS = {'translation': '_render_translation', 'combat_info': '_render_combat_info', 'clear': '_render_clear', 'claim_owner': '_render_claim_owner', 'panel_mode': '_render_panel_mode', 'shop_buy_list': '_render_shop_buy_list', 'facility_list': '_render_facility_list', 'spellbook': '_render_spellbook', 'item_pickup_list': '_render_item_pickup_list', 'load_screen_slots': '_render_load_screen_slots', 'equipment_list': '_render_equipment_list', 'spell_detail': '_render_spell_detail', 'place_list': '_render_place_list', 'travel_table': '_render_travel_table', 'journal_entries': '_render_journal_entries'}

    def apply_display(self, intent: DisplayIntent) -> None:
        render = self._RENDERERS.get(intent.kind)
        if render is None:
            raise ValueError(f'unknown or unresolved display intent kind: {intent.kind!r}')
        after = getattr(self, render)(intent)
        self._write_owner(intent)
        if after is not None:
            after()

    def _notify_translation(self, intent: DisplayIntent, owner: str, en: str, ja: str) -> None:
        if self._translation_observer is None:
            return
        key = (owner, en, ja, intent.speech_role, intent.speech_text, intent.speech_action, intent.log_enabled, intent.speech_event_id, intent.speech_cues, intent.kind)
        if self._obs_last_key == key:
            return
        self._obs_last_key = key
        args = (owner, en, ja, intent.speech_role, intent.speech_text, intent.log_enabled, intent.speech_action)
        if intent.kind == 'combat_info':
            args += (intent.speech_cues,)
        try:
            self._translation_observer(*args)
        except Exception:
            _log.exception('translation_observer failed')

    def _update_layout_panel(self, en: str, ja: str) -> None:
        panel = self._window._layout_translate_panel
        if panel is not None:
            panel.update_translation(en, ja)

    def _clear_list_payloads(self, intent: DisplayIntent) -> None:
        w = self._window
        if intent.clear_place_list:
            try:
                w._tab_translate.update_place_list([])
            except AttributeError:
                pass
        if intent.clear_travel_table:
            try:
                w._tab_translate.update_travel_table([])
            except AttributeError:
                pass

    def _render_translation(self, intent: DisplayIntent):
        w = self._window
        _prev_key = getattr(self, '_applied_prev_key', None)
        _mode = intent.mode
        _mode_key = _mode if _mode is not None else '<keep>'
        _panel_en = intent.panel_en or ''
        _panel_ja = intent.panel_ja or ''
        _now_key = (intent.panel_owner, _mode_key, intent.en[:160], intent.ja[:160], _panel_en[:160], _panel_ja[:160])
        if _prev_key != _now_key:
            self._applied_prev_key = _now_key
            if _panel_en or _panel_ja:
                _recog(_log, 'panel applied: owner=%r mode=%r en=%r ja=%r panel_en=%r panel_ja=%r', intent.panel_owner, _mode_key, intent.en[:120], intent.ja[:120], _panel_en[:120], _panel_ja[:120])
            else:
                _recog(_log, 'panel applied: owner=%r mode=%r en=%r ja=%r', intent.panel_owner, _mode_key, intent.en[:120], intent.ja[:120])
        if intent.update_tab:
            w._tab_translate.update_translation(intent.en, intent.ja, suppress_fallback=True)
        if intent.clear_place_list:
            try:
                w._tab_translate.update_place_list([])
            except AttributeError:
                pass
        if intent.update_panel:
            _pen = intent.panel_en if intent.panel_en is not None else intent.en
            _pja = intent.panel_ja if intent.panel_ja is not None else intent.ja
            self._update_layout_panel(_pen, _pja)

        def _after() -> None:
            self._displayed_translation = (self.current_owner(), intent.en, intent.ja)
            self._notify_translation(intent, intent.panel_owner or self.current_owner(), intent.en or (intent.panel_en or ''), intent.ja or (intent.panel_ja or ''))
        return _after

    def _render_combat_info(self, intent: DisplayIntent):
        w = self._window
        data = intent.items or {}
        w._tab_translate.update_combat_view(data)
        if data.get('panel_enabled'):
            _en = intent.panel_en or ''
            _ja = intent.panel_ja or ''
            self._update_layout_panel(_en, _ja)
            self._displayed_translation = (intent.panel_owner, _en, _ja)
        elif self._displayed_translation is not None and self._displayed_translation[0] == 'combat_info':
            self._update_layout_panel('', '')
            self._displayed_translation = None
        if not intent.speech_role:
            return None
        return lambda: self._notify_translation(intent, intent.panel_owner, intent.panel_en or '', intent.panel_ja or '')

    def _render_clear(self, intent: DisplayIntent):
        w = self._window
        closed_owner = intent.closed_owner or self.current_owner()
        w._tab_translate.update_translation('', '', suppress_fallback=True)
        self._clear_list_payloads(intent)
        self._update_layout_panel('', '')
        self._displayed_translation = None
        if not intent.notify_close:
            return None
        return lambda: self._notify_clear(closed_owner)

    def _render_claim_owner(self, intent: DisplayIntent):
        return lambda: self._notify_clear(intent.closed_owner)

    def _render_panel_mode(self, intent: DisplayIntent):
        return None

    def _render_shop_buy_list(self, intent: DisplayIntent):
        self._window._tab_translate.update_shop_buy_list(intent.items)
        self._update_layout_panel(intent.panel_en or '', intent.panel_ja or '')
        return None

    def _render_facility_list(self, intent: DisplayIntent):
        tab = self._window._tab_translate
        try:
            tab.set_facility_list_title(intent.list_title_ja or intent.panel_ja or intent.panel_en or '')
        except AttributeError:
            pass
        tab.update_facility_list(intent.items)
        self._update_layout_panel(intent.panel_en or '', intent.panel_ja or '')
        return None

    def _render_spellbook(self, intent: DisplayIntent):
        tab = self._window._tab_translate
        try:
            tab.set_spellbook_title(intent.list_title_ja or intent.panel_ja or intent.panel_en or '')
        except AttributeError:
            pass
        tab.update_spellbook_list(intent.items)
        self._update_layout_panel(intent.panel_en or '', intent.panel_ja or '')
        return None

    def _render_item_pickup_list(self, intent: DisplayIntent):
        self._window._tab_translate.update_item_pickup_list(intent.items, intent.remaining or 0)
        return None

    def _render_load_screen_slots(self, intent: DisplayIntent):
        self._window._tab_translate.update_load_screen_slots(intent.items)
        self._update_layout_panel('', '')
        return None

    def _render_equipment_list(self, intent: DisplayIntent):
        tab = self._window._tab_translate
        tab.set_equipment_panel_title(intent.title)
        tab.update_equipment_list(intent.items)
        return None

    def _render_spell_detail(self, intent: DisplayIntent):
        self._window._tab_translate.update_spell_detail(intent.items)
        if intent.panel_en or intent.panel_ja:
            self._update_layout_panel(intent.panel_en or '', intent.panel_ja or '')
        return None

    def _render_place_list(self, intent: DisplayIntent):
        tab = self._window._tab_translate
        tab.set_place_list_title(intent.title)
        tab.update_place_list(intent.items)
        self._update_layout_panel(intent.panel_en or '', intent.panel_ja or '')
        return None

    def _render_travel_table(self, intent: DisplayIntent):
        tab = self._window._tab_translate
        tab.set_travel_table_title(intent.title)
        tab.update_travel_table(intent.items)
        self._update_layout_panel(intent.panel_en or '', intent.panel_ja or '')
        if not intent.speech_role:
            return None
        return lambda: self._notify_translation(intent, intent.panel_owner or self.current_owner(), intent.panel_en or '', intent.panel_ja or '')

    def _render_journal_entries(self, intent: DisplayIntent):
        try:
            self._window._tab_translate.update_journal_entries(intent.items or [])
        except AttributeError:
            pass
        self._update_layout_panel(intent.panel_en or '', intent.panel_ja or '')
        if not intent.speech_role:
            return None
        return lambda: self._notify_translation(intent, intent.panel_owner or self.current_owner(), intent.panel_en or '', intent.panel_ja or '')

    def _log_facility_display_invariant(self, frame: Optional[PollFrame]) -> None:
        w = self._window
        session_name = active_facility_session_name(w)
        if not session_name:
            return
        owner = self.current_owner()
        if owner and owner in facility_owners_for_session(session_name):
            return
        story_owner = {'mages': 'mages_story', 'palace': 'palace_dialog', 'temple': 'temple_story'}.get(getattr(w, '_facility_story_kind_now', ''), '')
        if owner and owner == story_owner:
            return
        key = (session_name, owner, getattr(w, '_screen_id_prev', None), getattr(w, '_img_name_prev', '') or '', frame.top_level if frame is not None else '')
        if key == getattr(self, '_facility_empty_owner_key', None):
            return
        self._facility_empty_owner_key = key
        _log.warning('facility display invariant warning: active L4 facility session display owner is %s (session=%s screen=%r img=%r frame_top=%r)', 'empty' if not owner else f'non-facility {owner!r}', session_name, getattr(w, '_screen_id_prev', None), getattr(w, '_img_name_prev', '') or '', frame.top_level if frame is not None else '')

    def current_owner(self) -> str:
        return getattr(self._window, '_panel_owner', '') or ''

    def applied_owner(self) -> str:
        frame = self._poll_frame
        if frame is not None:
            return frame.panel_owner or ''
        return self.current_owner()

    def is_owner(self, panel_owner: str) -> bool:
        return self.current_owner() == panel_owner

    def is_displaying(self, panel_owner: str, en: str, ja: str) -> bool:
        if self.current_owner() != panel_owner:
            return False
        return self._displayed_translation == (panel_owner, en, ja)

    def clear_if_owner(self, panel_owner: str, *, mode: Optional[str]=None, clear_place_list: bool=False, clear_travel_table: bool=False, notify_close: bool=True) -> bool:
        return self.propose_display(DisplayIntent.clear_if_owner(panel_owner, mode=mode, clear_place_list=clear_place_list, clear_travel_table=clear_travel_table, notify_close=notify_close))

    def clear_if_owner_in(self, owners, *, mode: Optional[str]=None, place_list_owners=frozenset(), notify_close: bool=True) -> str:
        current = self.current_owner()
        if not current or current not in owners:
            return ''
        ok = self.clear_if_owner(current, mode=mode, clear_place_list=current in place_list_owners, notify_close=notify_close)
        return current if ok else ''

    def notify_display_unit_replaced_in(self, owners) -> str:
        current = self.current_owner()
        if not current or current not in owners:
            return ''
        self.notify_display_unit_replaced(current)
        return current

    def clear_display(self, panel_owner: str='', *, mode: Optional[str]='translate', clear_place_list: bool=False, clear_travel_table: bool=False, allowed_current_owners: Optional[tuple]=None, priority: int=0, notify_close: bool=True) -> bool:
        return self.propose_display(DisplayIntent.clear(panel_owner, mode=mode, clear_place_list=clear_place_list, clear_travel_table=clear_travel_table, priority=priority, allowed_current_owners=allowed_current_owners, notify_close=notify_close))

    def update_panel_translation(self, panel_en: str, panel_ja: str, *, speech_role: Optional[str]=None, speech_text: Optional[str]=None, speech_action: str='replace', log_enabled: bool=True, priority: int=0) -> None:
        self.propose_display(DisplayIntent.panel_translation(panel_en, panel_ja, priority=priority, speech_role=speech_role, speech_text=speech_text, speech_action=speech_action, log_enabled=log_enabled))

    def release_if_owner(self, panel_owner: str, *, mode: Optional[str]=None, priority: int=0, reason: str='') -> bool:
        return self.propose_display(DisplayIntent.release_if_owner(panel_owner, mode=mode, priority=priority, reason=reason))

    def claim_owner(self, panel_owner: str, *, mode: Optional[str]=None, priority: int=0, reason: str='') -> None:
        self.propose_display(DisplayIntent.claim_owner(panel_owner, mode=mode, priority=priority, reason=reason))

    def set_panel_mode(self, mode: str, *, priority: int=0, reason: str='') -> None:
        self.propose_display(DisplayIntent.panel_mode(mode, priority=priority, reason=reason))

    def _tab_panel_mode(self) -> Optional[str]:
        tab = getattr(self._window, '_tab_translate', None)
        if tab is None:
            return None
        try:
            return tab.panel_mode()
        except (AttributeError, RuntimeError):
            return None

    def ensure_panel_mode(self, mode: str, *, priority: int=0, reason: str='', propose: bool=True) -> str:
        cur = self._tab_panel_mode()
        if cur is None or cur == mode:
            return ''
        if propose:
            self.set_panel_mode(mode, priority=priority, reason=reason)
        return cur

    def reset_panel_mode_if(self, modes, *, to: str='translate', priority: int=0, reason: str='') -> str:
        cur = self._tab_panel_mode()
        if not cur or cur not in modes:
            return ''
        self.set_panel_mode(to, priority=priority, reason=reason)
        return cur

    def closing_panel_mode(self, *, img_name: str, screen_id: str, top_level: str, fallback_setting: str) -> Optional[str]:
        cur = self._tab_panel_mode()
        if cur is None:
            return 'translate'
        return _closing_panel_mode(current_mode=cur, img_name=img_name, screen_id=screen_id, top_level=top_level, fallback_setting=fallback_setting)

    def restore_translate_mode(self, *, img_name: str, screen_id: str) -> bool:
        cur = self._tab_panel_mode()
        if cur is None:
            return False
        target = restore_translate_target(current_mode=cur, img_name=img_name, screen_id=screen_id)
        if target is None:
            return False
        self.set_panel_mode(target)
        return True

    def update_shop_buy_list(self, panel_owner: str, items: list, panel_en: str, panel_ja: str) -> None:
        self.propose_display(DisplayIntent.shop_buy_list(panel_owner, items, panel_en, panel_ja))

    def update_facility_list(self, panel_owner: str, items: list, panel_en: str, panel_ja: str, *, list_title_ja: str=None, priority: int=0, reason: str='') -> None:
        self.propose_display(DisplayIntent.facility_list(panel_owner, items, panel_en, panel_ja, list_title_ja=list_title_ja, priority=priority, reason=reason))

    def update_item_pickup_list(self, panel_owner: str, items: list, remaining: int) -> None:
        self.propose_display(DisplayIntent.item_pickup_list(panel_owner, items, remaining))

    def update_load_screen_slots(self, panel_owner: str, slot_data: list) -> None:
        self.propose_display(DisplayIntent.load_screen_slots(panel_owner, slot_data))

    def propose_load_screen_slots(self, panel_owner: str, slot_data: list, *, priority: int=0, reason: str='') -> None:
        self.propose_display(DisplayIntent.load_screen_slots(panel_owner, slot_data, priority=priority, reason=reason))

    def update_equipment_list(self, panel_owner: str, title: str, items: list) -> None:
        self.propose_display(DisplayIntent.equipment_list(panel_owner, title, items))

    def propose_spellbook_list(self, panel_owner: str, items: list, panel_en: str, panel_ja: str, *, list_title_ja: str=None, priority: int=0, reason: str='') -> None:
        self.propose_display(DisplayIntent.spellbook_list(panel_owner, items, panel_en, panel_ja, list_title_ja=list_title_ja, priority=priority, reason=reason))

    def propose_equipment_list(self, panel_owner: str, title: str, items: list, *, priority: int=0, reason: str='') -> None:
        self.propose_display(DisplayIntent.equipment_list(panel_owner, title, items, priority=priority, reason=reason))

    def update_spell_detail(self, panel_owner: str, data: dict, *, panel_en: str='', panel_ja: str='') -> None:
        self.propose_display(DisplayIntent.spell_detail(panel_owner, data, panel_en=panel_en, panel_ja=panel_ja))

    def propose_spell_detail(self, panel_owner: str, data: dict, *, panel_en: str='', panel_ja: str='', priority: int=0, reason: str='') -> None:
        self.propose_display(DisplayIntent.spell_detail(panel_owner, data, panel_en=panel_en, panel_ja=panel_ja, priority=priority, reason=reason))

    def update_place_list(self, panel_owner: str, items: list, *, title: str='', panel_en: str='', panel_ja: str='') -> None:
        self.propose_display(DisplayIntent.place_list(panel_owner, items, title=title, panel_en=panel_en, panel_ja=panel_ja))

    def update_travel_table(self, panel_owner: str, rows: list, *, title: str='', panel_en: str='', panel_ja: str='', speech_role: Optional[str]=None, speech_text: Optional[str]=None, speech_action: str='replace', log_enabled: bool=True, priority: int=0, reason: str='') -> None:
        self.propose_display(DisplayIntent.travel_table(panel_owner, rows, title=title, panel_en=panel_en, panel_ja=panel_ja, speech_role=speech_role, speech_text=speech_text, speech_action=speech_action, log_enabled=log_enabled, priority=priority, reason=reason))

    def propose_journal_entries(self, panel_owner: str, entries: list, *, panel_en: str='', panel_ja: str='', speech_role: Optional[str]=None, speech_text: Optional[str]=None, speech_action: str='replace', log_enabled: bool=True, priority: int=0, reason: str='') -> None:
        self.propose_display(DisplayIntent.journal_entries(panel_owner, entries, panel_en=panel_en, panel_ja=panel_ja, speech_role=speech_role, speech_text=speech_text, speech_action=speech_action, log_enabled=log_enabled, priority=priority, reason=reason))
__all__ = ['UiRouter']
