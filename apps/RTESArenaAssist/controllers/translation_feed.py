from __future__ import annotations
from collections import OrderedDict
import re
import assist_settings as settings
import i18n_helper as i18n
_ROLE_SETTING = {'situation': 'tts_target_situation', 'conversation': 'tts_target_conversation'}
_LOG_MEANINGFUL_RE = re.compile('[0-9A-Za-z\\u3040-\\u30ff\\u3400-\\u9fff]')

def _is_loggable_text(text: str) -> bool:
    s = (text or '').strip()
    return bool(s and _LOG_MEANINGFUL_RE.search(s))

class TranslationFeed:

    def __init__(self, tts, window=None, log_store=None) -> None:
        self._tts = tts
        self._window = window
        self._log_store = log_store
        self._last_spoken: str | None = None
        self._last_top_level: str | None = None
        self._spoken_keys: 'OrderedDict[tuple[str | None, str], None]' = OrderedDict()
        self._speaking_owner: str | None = None

    def on_translation(self, panel_owner: str, original: str, text: str, speech_role: str | None=None, speech_text: str | None=None, log_enabled: bool=True) -> None:
        self._reset_guard_on_context_change()
        if speech_role is None:
            return
        read_text = speech_text if speech_text is not None else text
        if not read_text:
            return
        if log_enabled and self._log_store is not None:
            self._append_log(speech_role, read_text, original)
        if not settings.get('tts_enabled', False):
            return
        key = _ROLE_SETTING.get(speech_role)
        if not (key and bool(settings.get(key, True))):
            return
        if read_text == self._last_spoken:
            return
        repeat_key = (speech_role, read_text)
        if settings.get('tts_suppress_repeat', False) and repeat_key in self._spoken_keys:
            return
        self._last_spoken = read_text
        self._remember_spoken(repeat_key)
        self._speaking_owner = panel_owner
        self._tts.speak(self._apply_name_reading(read_text))

    def _remember_spoken(self, key) -> None:
        self._spoken_keys[key] = None
        self._spoken_keys.move_to_end(key)
        while len(self._spoken_keys) > 256:
            self._spoken_keys.popitem(last=False)

    def on_display_cleared(self, owner: str) -> None:
        if not settings.get('tts_cancel_on_close', False):
            return
        if owner and owner == self._speaking_owner:
            try:
                self._tts.stop_speaking()
            except Exception:
                pass
            self._speaking_owner = None
            self._last_spoken = None

    def _reset_guard_on_context_change(self) -> None:
        w = self._window
        if w is None:
            return
        try:
            from top_level.top_level_dispatcher import current_state
            tl = current_state(w)
        except Exception:
            return
        if tl != self._last_top_level:
            prev = self._last_top_level
            self._last_top_level = tl
            self._last_spoken = None
            self._spoken_keys.clear()
            self._speaking_owner = None
            if prev is not None and tl in ('pregame', 'chargen') and (self._log_store is not None):
                try:
                    self._log_store.reset_active()
                except Exception:
                    pass

    def reset_spoken(self) -> None:
        self._last_spoken = None
        self._last_top_level = None
        self._spoken_keys.clear()
        self._speaking_owner = None

    def _apply_name_reading(self, text: str) -> str:
        reading = settings.get('tts_name_reading', '') or ''
        if not reading:
            return text
        name = self._player_name()
        if name and name in text:
            return text.replace(name, reading)
        return text

    def _player_name(self) -> str:
        w = self._window
        if w is None:
            return ''
        try:
            from spell_reader import PLAYER_NAME_OFFSET
            raw = w._analyzer.read_bytes(w._anchor + PLAYER_NAME_OFFSET, 26)
            return raw.split(b'\x00', 1)[0].decode('ascii', errors='replace').strip()
        except Exception:
            return ''

    def _resolve_location(self) -> str:
        w = self._window
        if w is None:
            return ''
        try:
            from top_level.top_level_dispatcher import current_state
            tl = current_state(w)
        except Exception:
            tl = ''
        if tl == 'chargen':
            return i18n.tr('log.location.chargen', default='キャラクター作成')
        if tl == 'pregame':
            return i18n.tr('log.location.title', default='タイトル画面')
        return getattr(w, '_log_location_hint', '') or ''

    def _append_log(self, category: str, text: str, original: str) -> None:
        if not _is_loggable_text(text):
            return
        try:
            from datetime import datetime
            ts = datetime.now().timestamp()
        except Exception:
            ts = 0.0
        location = self._resolve_location()
        try:
            self._log_store.append(ts=ts, category=category, text=text, original=original, location=location)
        except Exception:
            pass
__all__ = ['TranslationFeed']
