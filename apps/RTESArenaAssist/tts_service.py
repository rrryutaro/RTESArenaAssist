from __future__ import annotations

import queue
import re
import threading

_SVSF_ASYNC = 1
_SVSF_PURGE_BEFORE_SPEAK = 2

_URL_RE = re.compile(r"https?://\S+")


class TTSService:

    def __init__(self, *, start_worker: bool = True) -> None:
        self._enabled = False
        self._interrupt = False
        self._volume = 100
        self._rate = 0
        self._voice_desc = ""
        self._engine = "sapi5"
        self._vv_speaker = 0

        self._queue: queue.Queue = queue.Queue()
        self._worker = None
        if start_worker:
            self._worker = threading.Thread(target=self._run, daemon=True)
            self._worker.start()

    def set_enabled(self, value: bool) -> None:
        self._enabled = bool(value)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_interrupt(self, value: bool) -> None:
        self._interrupt = bool(value)

    def set_volume(self, value: int) -> None:
        self._volume = max(0, min(100, int(value)))

    def set_rate(self, value: int) -> None:
        self._rate = max(-10, min(10, int(value)))

    def set_voice(self, desc: str) -> None:
        self._voice_desc = desc or ""

    def set_engine(self, value: str) -> None:
        self._engine = "voicevox" if str(value) == "voicevox" else "sapi5"

    def set_vv_speaker(self, value: int) -> None:
        try:
            self._vv_speaker = int(value)
        except (TypeError, ValueError):
            self._vv_speaker = 0

    def speak(self, text: str) -> None:
        if not self._enabled:
            return
        self._enqueue(text)

    def speak_now(self, text: str) -> None:
        self._enqueue(text)

    def stop_speaking(self) -> None:
        self._drain()
        self._stop_playback()
        self._queue.put(("", True))

    def _stop_playback(self) -> None:
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:  # noqa: BLE001
            pass

    def shutdown(self) -> None:
        self._drain()
        self._queue.put(None)

    def _enqueue(self, text: str) -> None:
        t = self._sanitize(text)
        if not t:
            return
        if self._interrupt:
            self._drain()
            if self._engine == "voicevox":
                self._stop_playback()
        self._queue.put((t, False))

    def _drain(self) -> None:
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass

    _APOSTROPHES = ("'", "’", "‘", "`")

    @classmethod
    def _sanitize(cls, text: str) -> str:
        if not text:
            return ""
        t = _URL_RE.sub("", str(text))
        for _ap in cls._APOSTROPHES:
            t = t.replace(_ap, "")
        return t.strip()

    def _run(self) -> None:
        speaker = self._init_sapi5()
        had_sapi = speaker is not None
        import logging as _logging
        _tlog = _logging.getLogger("poll_controller")
        if had_sapi:
            _tlog.warning("TTS backend: SAPI5 (win32com, in-process・外部プロセス無し)")
        else:
            _tlog.warning(
                "TTS unavailable: SAPI5(win32com) を初期化できないため読み上げを"
                "行いません（外部プロセスは起動しません）。pywin32 を確認して"
                "ください（上の SAPI5 init エラーを参照）")
        while True:
            entry = self._queue.get()
            if entry is None:
                break
            text, _force = entry
            if self._engine == "voicevox":
                if self._speak_voicevox(text):
                    continue
            if speaker is not None:
                self._speak_sapi5(speaker, text)
        speaker = None
        if had_sapi:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:  # noqa: BLE001
                pass

    def _speak_sapi5(self, speaker, text: str) -> None:
        try:
            speaker.Volume = self._volume
            speaker.Rate = self._rate
            self._apply_voice(speaker)
            if self._interrupt:
                speaker.Speak(text, _SVSF_ASYNC | _SVSF_PURGE_BEFORE_SPEAK)
            else:
                speaker.Speak(text)
        except Exception:  # noqa: BLE001
            pass

    def _speak_voicevox(self, text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return True
        try:
            import voicevox_client as vv
            speed = max(0.5, min(2.0, 1.0 + self._rate / 20.0))
            volume = max(0.0, min(2.0, self._volume / 100.0))
            data = vv.synthesize(t, self._vv_speaker,
                                 speed=speed, volume=volume)
        except Exception:  # noqa: BLE001
            return False
        if not data:
            return False
        self._play_wav(data)
        return True

    def _play_wav(self, data: bytes) -> None:
        try:
            import winsound
        except Exception:  # noqa: BLE001
            return
        try:
            winsound.PlaySound(data, winsound.SND_MEMORY)
        except Exception:  # noqa: BLE001
            pass

    def _apply_voice(self, speaker) -> None:
        if not self._voice_desc:
            return
        try:
            voices = speaker.GetVoices()
            for i in range(voices.Count):
                tok = voices.Item(i)
                if tok.GetDescription() == self._voice_desc:
                    speaker.Voice = tok
                    return
        except Exception:  # noqa: BLE001
            pass

    def _init_sapi5(self):
        try:
            import pythoncom
            pythoncom.CoInitialize()
            import win32com.client.dynamic
            return win32com.client.dynamic.Dispatch("SAPI.SpVoice")
        except Exception as exc:  # noqa: BLE001
            try:
                import logging as _logging
                _logging.getLogger("poll_controller").warning(
                    "TTS SAPI5 init failed: %s: %s",
                    type(exc).__name__, exc)
            except Exception:  # noqa: BLE001
                pass
            return None

    @staticmethod
    def list_voices() -> list[str]:
        try:
            import pythoncom
            pythoncom.CoInitialize()
            import win32com.client
            sp = win32com.client.Dispatch("SAPI.SpVoice")
            voices = sp.GetVoices()
            out = []
            for i in range(voices.Count):
                try:
                    out.append(voices.Item(i).GetDescription())
                except Exception:  # noqa: BLE001
                    pass
            return out
        except Exception:  # noqa: BLE001
            return []


__all__ = ["TTSService"]
