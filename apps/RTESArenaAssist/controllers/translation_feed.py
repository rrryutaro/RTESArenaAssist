from __future__ import annotations

import assist_settings as settings
import i18n_helper as i18n

_ROLE_SETTING = {
    "situation":    "tts_target_situation",
    "conversation": "tts_target_conversation",
}


class TranslationFeed:

    def __init__(self, tts, window=None, log_store=None) -> None:
        self._tts = tts
        self._window = window
        self._log_store = log_store
        self._last_spoken: str | None = None
        self._last_top_level: str | None = None

    def on_translation(self, panel_owner: str, original: str, text: str,
                       speech_role: str | None = None,
                       speech_text: str | None = None) -> None:
        self._reset_guard_on_context_change()
        if speech_role is None:
            return
        read_text = speech_text if speech_text is not None else text
        if not read_text:
            return
        if self._log_store is not None:
            self._append_log(speech_role, read_text, original)
        if not settings.get("tts_enabled", False):
            return
        key = _ROLE_SETTING.get(speech_role)
        if not (key and bool(settings.get(key, True))):
            return
        if read_text == self._last_spoken:
            return
        self._last_spoken = read_text
        self._tts.speak(self._apply_name_reading(read_text))

    def _reset_guard_on_context_change(self) -> None:
        w = self._window
        if w is None:
            return
        try:
            from top_level.top_level_dispatcher import current_state
            tl = current_state(w)
        except Exception:  # noqa: BLE001
            return
        if tl != self._last_top_level:
            prev = self._last_top_level
            self._last_top_level = tl
            self._last_spoken = None
            if prev is not None and tl in ("pregame", "chargen") \
                    and self._log_store is not None:
                try:
                    self._log_store.reset_active()
                except Exception:  # noqa: BLE001
                    pass

    def reset_spoken(self) -> None:
        self._last_spoken = None
        self._last_top_level = None

    def _apply_name_reading(self, text: str) -> str:
        reading = settings.get("tts_name_reading", "") or ""
        if not reading:
            return text
        name = self._player_name()
        if name and name in text:
            return text.replace(name, reading)
        return text

    def _player_name(self) -> str:
        w = self._window
        if w is None:
            return ""
        try:
            from spell_reader import PLAYER_NAME_OFFSET
            raw = w._analyzer.read_bytes(w._anchor + PLAYER_NAME_OFFSET, 26)
            return raw.split(b"\x00", 1)[0].decode(
                "ascii", errors="replace").strip()
        except Exception:  # noqa: BLE001
            return ""

    def _resolve_location(self) -> str:
        w = self._window
        if w is None:
            return ""
        try:
            from top_level.top_level_dispatcher import current_state
            tl = current_state(w)
        except Exception:  # noqa: BLE001
            tl = ""
        if tl == "chargen":
            return i18n.tr("log.location.chargen", default="キャラクター作成")
        if tl == "pregame":
            return i18n.tr("log.location.title", default="タイトル画面")
        return getattr(w, "_log_location_hint", "") or ""

    def _append_log(self, category: str, text: str, original: str) -> None:
        try:
            from datetime import datetime
            ts = datetime.now().timestamp()
        except Exception:  # noqa: BLE001
            ts = 0.0
        location = self._resolve_location()
        try:
            self._log_store.append(
                ts=ts, category=category, text=text,
                original=original, location=location)
        except Exception:  # noqa: BLE001
            pass


__all__ = ["TranslationFeed"]
