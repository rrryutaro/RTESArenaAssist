import logging
import inf_text_lookup as itl
from controllers.chargen_helpers import _CHARGEN_OPENING_HINT_ADDR, _CHARGEN_OPENING_MAXLEN, _CHARGEN_OPENING_FULLREAD, _CHARGEN_OPENING_SCAN_START, _CHARGEN_OPENING_SCAN_END, _CHARGEN_OPENING_PREFIXES, _is_garbage_npc_buffer, _looks_like_cinematic, _CHARGEN_NAME_RE, _CHARGEN_CLASS_JA, _CHARGEN_DYNAMIC_PATTERNS
_log = logging.getLogger('chargen_controller')

class ChargenController:

    def __init__(self, window):
        self._w = window

    def _reset_chargen_state_for_restart(self, reason: str='unknown') -> None:
        w = self._w
        w._chargen_state_streak = 0
        w._chargen_state_prev = 0
        try:
            from arena_bridge import CHARGEN_Q_SEQ_OFFSET as _OFF
            w._chargen_q_seq_prev = w._analyzer.read_bytes(w._anchor + _OFF, 1)[0]
        except (OSError, AttributeError, ImportError):
            w._chargen_q_seq_prev = 0
        w._in_chargen_name = False
        w._chargen_in_advice = False
        w._chargen_advice_state = None
        w._chargen_advice_a845 = None
        w._chargen_goyenow_displayed = False
        w._chargen_goyenow_state = None
        w._chargen_10q_displayed = False
        w._chargen_method_state = None
        w._chargen_method_a845 = None
        w._chargen_distribute_displayed = False
        w._chargen_choose_attrs_displayed = False
        w._chargen_choose_attrs_state_val = None
        w._chargen_appearance_displayed = False
        w._chargen_opening_displayed = False
        w._chargen_method_window = False
        w._chargen_race_select_displayed = False
        w._chargen_class_accept_displayed = False
        w._chargen_race_desc_displayed = False
        w._chargen_sex_select_displayed = False
        w._chargen_complete_displayed = False
        w._chargen_class_list_active = False
        w._chargen_race_ja = None
        w._chargen_class_ja = None
        w._chargen_class_en = None
        w._goyenow_scan_budget = 0
        w._advice_capture_age = -1
        w._chargen_status_display_armed = False
        w._chargen_attrs_state_anchor = None
        w._chargen_attrs_phase_seen = False
        w._chargen_attrs_modal_active = False
        w._chargen_attrs_modal_kind = None
        w._chargen_attrs_phase_log_prev = None
        w._chargen_explanation_active = None
        w._chargen_explanation_distribute_npc_snapshot = None
        w._chargen_explanation_distribute_dlg_seen_open = False
        w._chargen_goyenow_npc_snapshot = None
        w._chargen_goyenow_b7c4_prev = None
        w._dungeon_entry_cleared = False
        w._chargen_subscreen_last = None
        w._last_class_list_activation = None
        w._set_class_list_panel_mode(False)
        _log.info('chargen: state reset for restart (%s)', reason)

    def _read_chargen_done_live(self) -> int:
        w = self._w
        try:
            from arena_bridge import CHARGEN_DONE_OFFSET as _CDO
            return w._analyzer.read_bytes(w._anchor + _CDO, 1)[0]
        except (OSError, ImportError, AttributeError):
            return w._chargen_done_prev

    def _read_text_at(self, address: int) -> str:
        w = self._w
        for size in (_CHARGEN_OPENING_MAXLEN, 512, 256, 128, 64, 32):
            try:
                data = w._analyzer.read_bytes(address, size)
            except OSError:
                continue
            if not data:
                continue
            end = data.find(b'\x00')
            if end >= 0:
                data = data[:end]
            try:
                return data.decode('ascii', errors='replace').strip()
            except Exception:
                return ''
        return ''

    def _read_cinematic_block(self, address: int) -> str:
        w = self._w
        data = b''
        for size in (_CHARGEN_OPENING_FULLREAD, 2048, 1024, 512, 256):
            try:
                data = w._analyzer.read_bytes(address, size)
                if data:
                    break
            except OSError:
                continue
        if not data:
            return ''
        parts = data.split(b'\x00')
        text_parts: list[str] = []
        empty_run = 0
        for raw in parts:
            if not raw:
                empty_run += 1
                if empty_run >= 4 and text_parts:
                    break
                continue
            empty_run = 0
            try:
                s = raw.decode('ascii', errors='replace').strip()
            except Exception:
                if text_parts:
                    break
                continue
            if not s:
                if text_parts:
                    break
                continue
            printable = sum((1 for c in s if 32 <= ord(c) < 127))
            ratio = printable / max(len(s), 1)
            if ratio < 0.7:
                if text_parts:
                    break
                continue
            if len(s) < 3 and text_parts:
                continue
            text_parts.append(s)
        return ' '.join(text_parts).strip()

    def _read_player_name(self) -> str:
        w = self._w
        if w._analyzer is None or not w._anchor:
            return ''
        try:
            raw = w._analyzer.read_bytes(w._anchor + 429, 26)
        except OSError:
            return ''
        return raw.split(b'\x00', 1)[0].decode('ascii', errors='ignore').strip()

    def _read_chargen_state_byte(self) -> int | None:
        w = self._w
        try:
            from arena_bridge import CHARGEN_STATE_OFFSET as _OFF
            return w._analyzer.read_bytes(w._anchor + _OFF, 1)[0]
        except (OSError, ImportError, AttributeError):
            return None

    def _fire_post_chargen_opening(self) -> bool:
        w = self._w
        text = ''
        addr_used = 0
        block = self._read_cinematic_block(_CHARGEN_OPENING_HINT_ADDR)
        if block and _looks_like_cinematic(block):
            text = block
            addr_used = _CHARGEN_OPENING_HINT_ADDR
        if not text:
            for prefix in _CHARGEN_OPENING_PREFIXES:
                try:
                    results = w._analyzer.scan_string(prefix, _CHARGEN_OPENING_SCAN_START, _CHARGEN_OPENING_SCAN_END)
                except (OSError, RuntimeError, AttributeError) as exc:
                    _log.debug('chargen: opening scan_string error: %s', exc)
                    continue
                if not results:
                    continue
                addr_used = results[0].address
                block = self._read_cinematic_block(addr_used)
                if block and _looks_like_cinematic(block):
                    text = block
                    break
        if not text:
            _log.debug('chargen: post-chargen opening not yet written')
            return False
        if text == w._chargen_opening_text_prev:
            return True
        w._chargen_opening_text_prev = text
        entry = itl.lookup_by_text('', text)
        if entry is None:
            entry = itl.lookup('_CHARGEN_OPENING_', 0)
        original = text
        translated = ''
        if entry is not None:
            player_name = self._read_player_name() or ''
            disp = entry.get('text_display') or entry.get('text', '') or ''
            tr = itl.get_translation(entry)
            tr_str = tr if isinstance(tr, str) else ''
            if player_name:
                disp = disp.replace('[name]', player_name)
                tr_str = tr_str.replace('[名前]', player_name)
            original = text
            translated = tr_str
        w._set_chargen_ui_state(True)
        w._push_translation(original, translated, speech_role='situation')
        _log.info('chargen: post-chargen cinematic displayed (addr=0x%X, text_len=%d, mapped=%s)', addr_used, len(text), entry is not None)
        return True

    def _update_chargen_name_display(self, cls_en: str) -> None:
        w = self._w
        cls_ja = _CHARGEN_CLASS_JA.get(cls_en, cls_en)
        if cls_en:
            w._chargen_class_en = cls_en
        if cls_ja and w._chargen_class_ja != cls_ja:
            w._chargen_class_ja = cls_ja
            w._sync_attributes_race_class()
        entry = itl.lookup('_CHARGEN_NAME_', 0)
        if entry is None:
            return
        tab_orig = itl.get_text_display(entry).replace('[class]', cls_en)
        panel_orig = itl.get_text_panel(entry).replace('[class]', cls_en)
        tab_disp = itl.get_translation_display(entry) or ''
        tab_trans = tab_disp.replace('[クラス]', cls_ja)
        panel_basic = itl.get_translation(entry) or ''
        panel_trans = panel_basic.replace('[クラス]', cls_ja)
        w._push_translation(tab_orig, tab_trans, panel_original=panel_orig, panel_translated=panel_trans)

    def _handle_chargen_npc_dialog(self, npc_dialog: str) -> None:
        w = self._w
        if not npc_dialog:
            return
        if _is_garbage_npc_buffer(npc_dialog):
            _log.debug('npc_dialog: ignored garbage buffer (%r)', npc_dialog[:24])
            return
        from class_list_panel import resolve_npc_class_name
        cls_canonical = resolve_npc_class_name(npc_dialog)
        if cls_canonical is not None:
            _last_cls = getattr(w, '_last_class_list_activation', None)
            if _last_cls != cls_canonical:
                w._last_class_list_activation = cls_canonical
                self._activate_class_list_for_class(cls_canonical)
            return
        m = _CHARGEN_NAME_RE.search(npc_dialog)
        if m:
            if not w._in_chargen_name:
                w._in_chargen_name = True
                w._chargen_class_accept_displayed = False
                w._chargen_10q_displayed = False
                w._chargen_method_window = False
                if w._chargen_class_list_active:
                    w._set_class_list_panel_mode(False)
                entry = itl.lookup('_CHARGEN_NAME_', 0)
                if entry is not None:
                    w._update_translate_tab(entry)
            self._update_chargen_name_display(m.group(1))
            return
        if w._in_chargen_name:
            w._in_chargen_name = False
        if self._try_dynamic_chargen_npc(npc_dialog):
            return
        entry = itl.lookup_by_text('', npc_dialog)
        if entry is not None:
            _entry_key = (entry.get('inf') or '', (entry.get('text') or '')[:40])
            _prev_key = getattr(w, '_last_chargen_entry_key', None)
            if _prev_key == _entry_key:
                return
            inf_key = (entry.get('inf') or '').upper()
            if w._chargen_class_list_active and inf_key == '_CHARGEN_':
                return
            w._last_chargen_entry_key = _entry_key
            w._update_translate_tab(entry)
            w._track_chargen_race_class(inf_key)
            if inf_key.startswith('_CHARGEN_CLASS_ADVICE_'):
                w._chargen_in_advice = True
                w._chargen_advice_state = None
                w._chargen_advice_a845 = None
                w._chargen_goyenow_displayed = False
                w._chargen_goyenow_state = None
                w._chargen_choose_attrs_displayed = False
                w._chargen_choose_attrs_state_val = None
                w._goyenow_scan_budget = 60
                _log.info('chargen: class_advice mode entered (%s)', inf_key)
            elif inf_key == '_CHARGEN_CHOOSE_ATTRIBUTES_':
                w._chargen_choose_attrs_state_val = w._chargen_state_prev
                w._chargen_appearance_displayed = False
                if not w._chargen_attrs_phase_seen:
                    _old_anchor = w._chargen_attrs_state_anchor
                    w._chargen_attrs_state_anchor = w._chargen_state_prev
                    w._chargen_attrs_phase_seen = True
                    _log.info('chargen_latch: attrs_anchor=%s->0x%02X source=CHOOSE_ATTRIBUTES_initial', '0x%02X' % _old_anchor if _old_anchor is not None else 'None', w._chargen_attrs_state_anchor)
                if not w._chargen_status_display_armed:
                    w._chargen_status_display_armed = True
                    _log.info('chargen_latch: status_armed=0->1 source=CHOOSE_ATTRIBUTES')
                w._chargen_attrs_modal_active = False
                normal_chargen_flow = w._chargen_advice_state is not None or w._chargen_goyenow_displayed or w._chargen_distribute_displayed
                if normal_chargen_flow:
                    w._chargen_choose_attrs_displayed = True
                    _log.info('chargen: choose_attributes detected, state_val=0x%02X', w._chargen_state_prev)
                else:
                    try:
                        from arena_bridge import SCREEN_IMG_OFFSET as _SCR_OFF, SCREEN_IMG_MAXLEN as _SCR_MAX
                        _img_raw = w._analyzer.read_bytes(w._anchor + _SCR_OFF, _SCR_MAX)
                        _img_now = _img_raw.split(b'\x00', 1)[0].decode('ascii', errors='replace').upper()
                    except (OSError, AttributeError, ImportError):
                        _img_now = ''
                    if _img_now in ('MRSHIRT.IMG', 'FRSHIRT.IMG'):
                        w._chargen_choose_attrs_displayed = True
                        w._chargen_attrs_modal_active = False
                        w._chargen_attrs_modal_kind = None
                        _log.info('chargen: reconnect Appearance fire suppressed (img=%s) — choose_attrs phase activated', _img_now)
                    elif _img_now.startswith('FACES') and _img_now.endswith('.CIF'):
                        app_entry = itl.lookup('_CHARGEN_APPEARANCE_', 0)
                        if app_entry is not None:
                            w._update_translate_tab(app_entry)
                        w._chargen_appearance_displayed = True
                        _log.info('chargen: Appearance fired immediately (reconnect, FACES IMG detected, img=%s)', _img_now)
                    else:
                        w._chargen_choose_attrs_displayed = True
                        w._chargen_attrs_modal_active = False
                        w._chargen_attrs_modal_kind = None
                        _log.info('chargen: reconnect Appearance fire suppressed (img=%s unrecognized) — choose_attrs phase activated as default', _img_now)
            else:
                w._chargen_choose_attrs_displayed = False
                w._chargen_choose_attrs_state_val = None
        else:
            return

    def _activate_class_list_for_class(self, en_name: str) -> None:
        w = self._w
        first_activation = not w._chargen_class_list_active
        if en_name:
            w._chargen_class_en = en_name
            cls_ja = _CHARGEN_CLASS_JA.get(en_name, en_name)
            if cls_ja and w._chargen_class_ja != cls_ja:
                w._chargen_class_ja = cls_ja
                w._sync_attributes_race_class()
        if first_activation and (w._chargen_appearance_displayed or w._chargen_opening_displayed):
            self._reset_chargen_state_for_restart(reason='class_list reactivated after appearance/opening')
            first_activation = True
        if first_activation:
            w._chargen_method_window = False
            w._set_class_list_panel_mode(True)
            w._set_chargen_ui_state(True)
            _log.info('chargen: class list panel activated (npc=%s)', en_name)
        try:
            w._tab_translate.select_class_in_list(en_name)
        except AttributeError:
            pass

    def _try_dynamic_chargen_npc(self, npc_dialog: str) -> bool:
        w = self._w
        normalized = ' '.join(npc_dialog.split())
        for item in _CHARGEN_DYNAMIC_PATTERNS:
            pattern, inf_key = (item[0], item[1])
            extract_re = item[2] if len(item) > 2 else None
            subst_fn = item[3] if len(item) > 3 else None
            orig_suffix = item[4] if len(item) > 4 else None
            if not pattern.search(normalized):
                continue
            w._chargen_method_window = False
            if inf_key == '_CHARGEN_PROVINCE_':
                w._chargen_race_select_displayed = True
                w._in_chargen_name = False
                w._chargen_sex_select_displayed = False
                w._chargen_10q_displayed = False
                w._chargen_class_accept_displayed = False
                w._chargen_class_list_active = False
                w._chargen_appearance_displayed = False
                w._chargen_complete_displayed = False
            elif inf_key == '_CHARGEN_PROVINCE_CONFIRM_':
                w._chargen_complete_displayed = False
            elif inf_key == '_CHARGEN_COMPLETE_':
                _log.info("chargen_complete fired (NPC match: 'Then thou wilt be known as the'); flags before fire: appearance=%s chargen_done_prev=%s", w._chargen_appearance_displayed, w._chargen_done_prev)
                w._chargen_complete_displayed = True
                w._chargen_race_select_displayed = False
                w._chargen_race_desc_displayed = False
                w._chargen_class_accept_displayed = False
                w._chargen_in_advice = False
                w._chargen_goyenow_displayed = False
                w._chargen_distribute_displayed = False
                w._chargen_choose_attrs_displayed = False
                w._chargen_appearance_displayed = False
                w._chargen_sex_select_displayed = False
                w._in_chargen_name = False
                w._chargen_10q_displayed = False
                w._chargen_method_window = False
                w._chargen_class_list_active = False
            w._set_chargen_ui_state(True)
            entry = itl.lookup(inf_key, 0)
            tab_orig = normalized + (orig_suffix or '')
            panel_orig = normalized + (orig_suffix or '')
            tab_disp = itl.get_translation_display(entry) if entry else None
            tab_trans = tab_disp if isinstance(tab_disp, str) else ''
            panel_basic = itl.get_translation(entry) if entry else None
            panel_trans = panel_basic if isinstance(panel_basic, str) else ''
            if extract_re and subst_fn:
                m = extract_re.search(normalized)
                if m:
                    subs = subst_fn(m)
                    for placeholder, value in subs.items():
                        if tab_trans:
                            tab_trans = tab_trans.replace(placeholder, value)
                        if panel_trans:
                            panel_trans = panel_trans.replace(placeholder, value)
                    new_race = subs.get('[種族]')
                    new_cls = subs.get('[クラス]')
                    if new_race and w._chargen_race_ja != new_race:
                        w._chargen_race_ja = new_race
                    if new_cls and w._chargen_class_ja != new_cls:
                        w._chargen_class_ja = new_cls
                    if new_race or new_cls:
                        w._sync_attributes_race_class()
            w._push_translation(tab_orig, tab_trans, panel_original=panel_orig, panel_translated=panel_trans, speech_role='situation')
            return True
        return False
