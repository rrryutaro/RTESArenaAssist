from __future__ import annotations
import logging
import os
import queue
import re
import tempfile
import threading
import time
import traceback
from collections import OrderedDict
from dataclasses import dataclass
_SVSF_ASYNC = 1
_SVSF_PURGE_BEFORE_SPEAK = 2
_URL_RE = re.compile('https?://\\S+')
_APOSTROPHES = ("'", '’', '‘', '`')
_TRAILING_SILENT_CHARS = frozenset('」』”’"\')）〕］】｝〉》〙〗〟〞>＞、，,・:：;；…‥ー―-!?！？')
_VOICEVOX_CACHE_MAX = 128
_VOICEVOX_PREFETCH_QUEUE_SIZE = 4

def _log_tts(message: str) -> None:
    try:
        logging.getLogger('poll_controller').debug(message)
    except Exception:
        pass

@dataclass(frozen=True)
class _VVResult:
    index: int
    data: bytes | None
    error: str | None
    speaker: int
    chars: int

@dataclass(frozen=True)
class _TTSRequest:
    text: str
    force: bool
    generation: int

class TTSService:

    def __init__(self, *, start_worker: bool=True) -> None:
        self._enabled = False
        self._interrupt = False
        self._volume = 100
        self._rate = 0
        self._voice_desc = ''
        self._engine = 'sapi5'
        self._vv_speaker = 0
        self._lock = threading.RLock()
        self._pause_cond = threading.Condition(self._lock)
        self._paused = False
        self._generation = 0
        self._stopping = False
        self._segment_observer = None
        self._voicevox_cache: OrderedDict[tuple[str, int, int, int], bytes] = OrderedDict()
        self._queue: queue.Queue = queue.Queue()
        self._worker = None
        self._prewarm_queue: queue.Queue = queue.Queue()
        self._prewarm_seen: set[tuple[str, int, int, int]] = set()
        self._prewarm_worker = None
        if start_worker:
            self._worker = threading.Thread(target=self._run, daemon=True)
            self._worker.start()
            self._prewarm_worker = threading.Thread(target=self._run_prewarm, daemon=True)
            self._prewarm_worker.start()

    def set_enabled(self, value: bool) -> None:
        with self._lock:
            self._enabled = bool(value)

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def set_interrupt(self, value: bool) -> None:
        with self._lock:
            self._interrupt = bool(value)

    def set_volume(self, value: int) -> None:
        with self._lock:
            self._volume = max(0, min(100, int(value)))

    def set_rate(self, value: int) -> None:
        with self._lock:
            self._rate = max(-10, min(10, int(value)))

    def set_voice(self, desc: str) -> None:
        with self._lock:
            self._voice_desc = desc or ''

    def set_engine(self, value: str) -> None:
        with self._lock:
            self._engine = 'voicevox' if str(value) == 'voicevox' else 'sapi5'

    def set_vv_speaker(self, value: int) -> None:
        try:
            speaker = int(value)
        except (TypeError, ValueError):
            speaker = 0
        with self._lock:
            self._vv_speaker = speaker

    def set_segment_observer(self, callback) -> None:
        self._segment_observer = callback

    def _notify_segment(self, full_text, segment_text, prefetched=None) -> None:
        cb = self._segment_observer
        if cb is None:
            return
        try:
            cb(full_text, segment_text, list(prefetched or []))
        except Exception:
            pass

    def _emit_reading(self, ctx: dict) -> None:
        if self._segment_observer is None:
            return
        if not self._is_generation_current(ctx['generation']):
            return
        segs = ctx['segments']
        cur = ctx.get('playing')
        with ctx['lock']:
            ahead = sorted((i for i in ctx['requested'] if cur is None or i > cur))
        prefetched = [segs[i] for i in ahead if 0 <= i < len(segs)]
        current_seg = segs[cur] if cur is not None and 0 <= cur < len(segs) else None
        self._notify_segment(ctx['full'], current_seg, prefetched)

    def speak(self, text: str) -> None:
        if self._enabled:
            self._enqueue(text, force=False)

    def speak_now(self, text: str) -> None:
        self._enqueue(text, force=True)

    def pause_speaking(self) -> None:
        with self._pause_cond:
            self._paused = True
            self._pause_cond.notify_all()

    def resume_speaking(self) -> None:
        with self._pause_cond:
            self._paused = False
            self._pause_cond.notify_all()

    def stop_speaking(self) -> None:
        with self._pause_cond:
            self._generation += 1
            generation = self._generation
            self._paused = False
            self._pause_cond.notify_all()
        self._drain()
        self._stop_playback()
        self._notify_segment(None, None)
        self._queue.put(_TTSRequest('', True, generation))

    def prewarm(self, texts) -> None:
        if not texts:
            return
        with self._lock:
            if self._engine != 'voicevox':
                return
            speaker = self._vv_speaker
            rate = self._rate
            volume = self._volume
        for text in texts:
            value = self._sanitize(text)
            if not value:
                continue
            for segment in self._split_sentences(value):
                if not segment:
                    continue
                key = (segment, speaker, rate, volume)
                with self._lock:
                    if key in self._prewarm_seen or key in self._voicevox_cache:
                        continue
                    self._prewarm_seen.add(key)
                self._prewarm_queue.put(segment)

    def shutdown(self) -> None:
        with self._pause_cond:
            self._stopping = True
            self._paused = False
            self._pause_cond.notify_all()
        self._drain()
        self._stop_playback()
        self._queue.put(None)
        self._prewarm_queue.put(None)

    def _enqueue(self, text: str, *, force: bool) -> None:
        value = self._sanitize(text)
        if not value:
            return
        with self._pause_cond:
            if self._stopping:
                return
            interrupt = self._interrupt
            engine = self._engine
            if interrupt:
                self._generation += 1
                self._paused = False
                self._pause_cond.notify_all()
            generation = self._generation
        if interrupt:
            self._drain()
            if engine == 'voicevox':
                self._stop_playback()
        self._queue.put(_TTSRequest(value, force, generation))

    def _drain(self) -> None:
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass

    def _stop_playback(self) -> None:
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass

    @classmethod
    def _sanitize(cls, text: str) -> str:
        if not text:
            return ''
        value = _URL_RE.sub('', str(text))
        for ap in _APOSTROPHES:
            value = value.replace(ap, '')
        return value.strip()

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        value = str(text or '').replace('\r\n', '\n').replace('\r', '\n')
        segments: list[str] = []
        for line in value.split('\n'):
            if not line.strip():
                if segments and segments[-1] != '':
                    segments.append('')
                continue
            segments.extend(TTSService._split_line_sentences(line))
        while segments and segments[-1] == '':
            segments.pop()
        return segments

    @staticmethod
    def _split_line_sentences(line: str) -> list[str]:
        value = line.strip()
        if not value:
            return []
        sentences: list[str] = []
        start = 0
        index = 0
        while index < len(value):
            if value[index] != '。':
                index += 1
                continue
            end = index + 1
            while end < len(value) and (value[end].isspace() or value[end] in _TRAILING_SILENT_CHARS):
                end += 1
            sentence = value[start:end].strip()
            if sentence:
                sentences.append(sentence)
            start = end
            index = end
        tail = value[start:].strip()
        if tail:
            sentences.append(tail)
        return sentences

    def _is_generation_current(self, generation: int) -> bool:
        with self._lock:
            return not self._stopping and generation == self._generation

    def _wait_if_paused(self, generation: int) -> bool:
        with self._pause_cond:
            while self._paused and (not self._stopping) and (generation == self._generation):
                self._pause_cond.wait(timeout=0.05)
            return not self._stopping and generation == self._generation

    def _is_paused(self) -> bool:
        with self._lock:
            return self._paused

    def _run(self) -> None:
        speaker = None
        had_sapi = False
        while True:
            entry = self._queue.get()
            if entry is None:
                break
            request = entry
            try:
                with self._lock:
                    enabled = self._enabled
                    engine = self._engine
                if not request.force and (not enabled):
                    continue
                segments = self._split_sentences(request.text)
                if not any(segments):
                    continue
                try:
                    if engine == 'voicevox':
                        self._speak_voicevox(request.text, segments, request.generation)
                    else:
                        if speaker is None:
                            speaker = self._init_sapi5()
                            had_sapi = speaker is not None
                            if had_sapi:
                                logging.getLogger('poll_controller').warning('TTS backend: SAPI5 (win32com, in-process・外部プロセス無し)')
                            else:
                                logging.getLogger('poll_controller').warning('TTS unavailable: SAPI5(win32com) を初期化できないため読み上げを行いません（外部プロセスは起動しません）。pywin32 を確認してください')
                        if speaker is not None:
                            self._speak_sapi5_segments(speaker, request.text, segments, request.generation)
                finally:
                    self._notify_segment(None, None)
            except Exception:
                _log_tts('TTS worker error:\n' + traceback.format_exc())
                continue
        speaker = None
        if had_sapi:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass

    def _speak_sapi5_segments(self, speaker, full_text: str, segments: list[str], generation: int) -> None:
        for segment in segments:
            if not self._is_generation_current(generation):
                return
            if not self._wait_if_paused(generation):
                return
            if not segment:
                continue
            self._notify_segment(full_text, segment)
            self._speak_sapi5_blocking(speaker, segment)

    def _speak_sapi5_blocking(self, speaker, text: str) -> None:
        try:
            with self._lock:
                volume = self._volume
                rate = self._rate
            speaker.Volume = volume
            speaker.Rate = rate
            self._apply_voice(speaker)
            speaker.Speak(text)
        except Exception:
            _log_tts('SAPI5 speak error:\n' + traceback.format_exc())

    def _apply_voice(self, speaker) -> None:
        with self._lock:
            voice_desc = self._voice_desc
        if not voice_desc:
            return
        try:
            voices = speaker.GetVoices()
            for i in range(voices.Count):
                tok = voices.Item(i)
                if tok.GetDescription() == voice_desc:
                    speaker.Voice = tok
                    return
        except Exception:
            _log_tts('SAPI5 apply voice error:\n' + traceback.format_exc())

    def _init_sapi5(self):
        try:
            import pythoncom
            pythoncom.CoInitialize()
            import win32com.client.dynamic
            return win32com.client.dynamic.Dispatch('SAPI.SpVoice')
        except Exception as exc:
            try:
                logging.getLogger('poll_controller').warning('TTS SAPI5 init failed: %s: %s', type(exc).__name__, exc)
            except Exception:
                pass
            return None

    def _speak_voicevox(self, full_text: str, segments: list[str], generation: int) -> None:
        index = self._next_segment_index(segments, 0)
        if index < 0:
            return
        ctx = {'full': full_text, 'segments': segments, 'playing': None, 'requested': set(), 'lock': threading.Lock(), 'generation': generation}
        result_queue = self._start_voicevox_prefetch(segments, index, generation, ctx)
        prefetched: dict[int, _VVResult] = {}
        while index >= 0:
            if not self._is_generation_current(generation):
                return
            if not self._wait_if_paused(generation):
                return
            result = self._get_voicevox_prefetch_result(result_queue, prefetched, index, generation, consume=True)
            if result is None:
                return
            if result.error:
                _log_tts(f'VOICEVOX synthesize error: speaker={result.speaker} chars={result.chars}\n{result.error}')
                return
            if not result.data:
                _log_tts(f'VOICEVOX synthesize returned no audio: speaker={result.speaker} chars={result.chars}')
                return
            if not self._wait_if_paused(generation):
                return
            next_index = self._next_segment_index(segments, index + 1)
            try:
                ctx['playing'] = index
                self._emit_reading(ctx)
                self._play_wav(result.data, generation)
            except Exception:
                _log_tts('VOICEVOX playback error:\n' + traceback.format_exc())
                return
            if not self._is_generation_current(generation):
                return
            gap_end = next_index if next_index >= 0 else len(segments)
            for gap in segments[index + 1:gap_end]:
                if not self._is_generation_current(generation):
                    return
                if not self._wait_if_paused(generation):
                    return
                if not gap:
                    time.sleep(0.25)
            index = next_index

    def _start_voicevox_prefetch(self, segments: list[str], start_index: int, generation: int, ctx: dict | None=None) -> 'queue.Queue':
        result_queue: queue.Queue = queue.Queue(maxsize=_VOICEVOX_PREFETCH_QUEUE_SIZE)
        segment_list = list(segments)

        def worker() -> None:
            index = start_index
            while index >= 0 and self._is_generation_current(generation):
                segment = segment_list[index]
                speaker = -1
                chars = len(segment)
                if ctx is not None:
                    with ctx['lock']:
                        ctx['requested'].add(index)
                    self._emit_reading(ctx)
                try:
                    data, speaker = self._synthesize_voicevox_segment(segment)
                    result = _VVResult(index, data, None, speaker, chars)
                except Exception:
                    result = _VVResult(index, None, traceback.format_exc(), speaker, chars)
                if not self._put_voicevox_prefetch_result(result_queue, result, generation):
                    return
                if result.error or not result.data:
                    return
                index = self._next_segment_index(segment_list, index + 1)
        threading.Thread(target=worker, daemon=True, name='RTESAssistVoicevoxPrefetch').start()
        return result_queue

    def _put_voicevox_prefetch_result(self, result_queue: 'queue.Queue', result: '_VVResult', generation: int) -> bool:
        while self._is_generation_current(generation):
            try:
                result_queue.put(result, timeout=0.05)
                return True
            except queue.Full:
                continue
        return False

    def _get_voicevox_prefetch_result(self, result_queue: 'queue.Queue', prefetched: dict, index: int, generation: int, *, consume: bool):
        result = prefetched.get(index)
        if result is not None:
            if consume:
                prefetched.pop(index, None)
            return result
        while self._is_generation_current(generation):
            try:
                result = result_queue.get(timeout=0.05)
            except queue.Empty:
                continue
            prefetched[result.index] = result
            if result.index == index:
                if consume:
                    prefetched.pop(index, None)
                return result
        return None

    def _synthesize_voicevox_segment(self, segment: str):
        import voicevox_client as vv
        with self._lock:
            rate = self._rate
            volume_value = self._volume
            speaker = self._vv_speaker
            cache_key = (segment, speaker, rate, volume_value)
            cached = self._voicevox_cache.get(cache_key)
            if cached is not None:
                self._voicevox_cache.move_to_end(cache_key)
                return (cached, speaker)
        speed = max(0.5, min(2.0, 1.0 + rate / 20.0))
        volume = max(0.0, min(2.0, volume_value / 100.0))
        data = vv.synthesize(segment, speaker, speed=speed, volume=volume)
        if data:
            with self._lock:
                self._voicevox_cache[cache_key] = data
                self._voicevox_cache.move_to_end(cache_key)
                while len(self._voicevox_cache) > _VOICEVOX_CACHE_MAX:
                    self._voicevox_cache.popitem(last=False)
        return (data, speaker)

    @staticmethod
    def _next_segment_index(segments: list[str], start: int) -> int:
        for index in range(start, len(segments)):
            if segments[index]:
                return index
        return -1

    def _play_wav(self, data: bytes, generation: int) -> None:
        if os.name != 'nt':
            _log_tts('VOICEVOX playback unsupported on this OS (winsound 無し)')
            return
        import winsound
        path = ''
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as fp:
                fp.write(data)
                path = fp.name
            duration = self._wav_duration_seconds(data)
            while True:
                if not self._wait_if_paused(generation):
                    return
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                deadline = time.perf_counter() + max(0.1, duration + 0.1)
                restart = False
                while time.perf_counter() < deadline:
                    if not self._is_generation_current(generation):
                        winsound.PlaySound(None, winsound.SND_PURGE)
                        return
                    if self._is_paused():
                        winsound.PlaySound(None, winsound.SND_PURGE)
                        restart = True
                        break
                    time.sleep(0.03)
                if not restart:
                    break
        finally:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass

    @staticmethod
    def _wav_duration_seconds(data: bytes) -> float:
        try:
            import io
            import wave
            with wave.open(io.BytesIO(data), 'rb') as wav:
                frames = wav.getnframes()
                rate = wav.getframerate()
                if rate > 0:
                    return frames / float(rate)
        except Exception:
            pass
        return max(0.3, min(30.0, len(data) / 88200.0))

    def _run_prewarm(self) -> None:
        while True:
            segment = self._prewarm_queue.get()
            if segment is None:
                break
            try:
                with self._lock:
                    if self._stopping or self._engine != 'voicevox':
                        continue
                self._synthesize_voicevox_segment(segment)
            except Exception:
                _log_tts('TTS prewarm error:\n' + traceback.format_exc())
                continue

    @staticmethod
    def list_voices() -> list[str]:
        try:
            import pythoncom
            pythoncom.CoInitialize()
            import win32com.client
            sp = win32com.client.Dispatch('SAPI.SpVoice')
            voices = sp.GetVoices()
            out = []
            for i in range(voices.Count):
                try:
                    out.append(voices.Item(i).GetDescription())
                except Exception:
                    pass
            return out
        except Exception:
            return []
__all__ = ['TTSService']
