from __future__ import annotations
import io
import logging
import queue
import re
import threading
import time
import traceback
import wave
from collections import OrderedDict, deque
from dataclasses import dataclass
_SVSF_ASYNC = 1
_SVSF_PURGE_BEFORE_SPEAK = 2
_SAPI_WAIT_POLL_MS = 50
_URL_RE = re.compile('https?://\\S+')
_APOSTROPHES = ("'", '’', '‘', '`')
_TRAILING_SILENT_CHARS = frozenset('」』”’"\')）〕］】｝〉》〙〗〟〞>＞、，,・:：;；…‥ー―-!?！？')
_VOICEVOX_CACHE_MAX = 128
_VOICEVOX_READY_AUDIO_MAX_SECONDS = 30.0
_VOICEVOX_SCHEDULING_MARGIN_SECONDS = 0.5
_VOICEVOX_TIMEOUT_MIN_SECONDS = 15.0
_VOICEVOX_TIMEOUT_MAX_SECONDS = 120.0
_VOICEVOX_TIMEOUT_MULTIPLIER = 2.0
_VOICEVOX_TIMEOUT_PADDING_SECONDS = 3.0
_VOICEVOX_FALLBACK_SYNTH_SECONDS_PER_CHAR = 0.08
_VOICEVOX_FALLBACK_SYNTH_BASE_SECONDS = 0.5
_VOICEVOX_FALLBACK_AUDIO_SECONDS_PER_CHAR = 0.12
_VOICEVOX_TIMING_HISTORY_SIZE = 32
_VOICEVOX_RETRY_FAST_FAIL_SECONDS = 2.0
_VOICEVOX_PREFETCH_DONE = object()
_SPEECH_NAME_MIDDLE_DOT_RE = re.compile('(?<=[\\wぁ-んァ-ヶ一-龯々ー])\\s*[・･]\\s*(?=[\\wぁ-んァ-ヶ一-龯々ー])')
_SPEECH_MIDDLE_DOT_RE = re.compile('\\s*[・･]\\s*')
_SPEECH_COMMA_RE = re.compile('、{2,}')

def _log_tts(message: str) -> None:
    try:
        logging.getLogger('poll_controller').warning(message)
    except Exception:
        pass

@dataclass(frozen=True)
class _VVResult:
    index: int
    data: bytes | None
    error: str | None
    speaker: int
    chars: int
    duration_seconds: float = 0.0
    starts_segment: bool = True
    ends_segment: bool = True

class _VoicevoxBufferState:

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._ready_seconds = 0.0
        self._playing_started = 0.0
        self._playing_seconds = 0.0
        self._closed = False

    def available_seconds(self) -> float:
        with self._condition:
            return self._available_seconds_locked()

    def add_ready(self, duration_seconds: float) -> None:
        with self._condition:
            self._ready_seconds += max(0.0, float(duration_seconds))
            self._condition.notify_all()

    def start_playback(self, duration_seconds: float) -> None:
        duration = max(0.0, float(duration_seconds))
        with self._condition:
            self._ready_seconds = max(0.0, self._ready_seconds - duration)
            self._playing_started = time.perf_counter()
            self._playing_seconds = duration
            self._condition.notify_all()

    def finish_playback(self) -> None:
        with self._condition:
            self._playing_started = 0.0
            self._playing_seconds = 0.0
            self._condition.notify_all()

    def wait(self, timeout: float=0.05) -> bool:
        with self._condition:
            if self._closed:
                return False
            self._condition.wait(timeout=max(0.01, float(timeout)))
            return not self._closed

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def _available_seconds_locked(self) -> float:
        playback_remaining = 0.0
        if self._playing_started > 0.0 and self._playing_seconds > 0.0:
            elapsed = max(0.0, time.perf_counter() - self._playing_started)
            playback_remaining = max(0.0, self._playing_seconds - elapsed)
        return self._ready_seconds + playback_remaining

@dataclass(frozen=True)
class _TTSRequest:
    text: str
    force: bool
    generation: int

class TTSService:

    def __init__(self, *, start_worker: bool=True) -> None:
        self._pending_lock = threading.Lock()
        self._pending = 0
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
        self._voicevox_timing_history: dict[tuple[int, int], 'deque[tuple[int, float, float]]'] = {}
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

    def is_speaking(self) -> bool:
        with self._pending_lock:
            return self._pending > 0

    def _pending_add(self) -> None:
        with self._pending_lock:
            self._pending += 1

    def _pending_done(self) -> None:
        with self._pending_lock:
            if self._pending > 0:
                self._pending -= 1

    def _pending_clear(self) -> None:
        with self._pending_lock:
            self._pending = 0

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
        self._pending_clear()
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
                key = (self._normalize_speech_text(segment), speaker, rate, volume)
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
            self._pending_clear()
            if engine == 'voicevox':
                self._stop_playback()
        self._pending_add()
        self._queue.put(_TTSRequest(value, force, generation))

    def _drain(self) -> None:
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass

    def _stop_playback(self) -> None:
        try:
            from services import audio_player
            audio_player.get_client().stop_tts()
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
    def _normalize_speech_text(text: str) -> str:
        value = str(text or '')
        value = _SPEECH_NAME_MIDDLE_DOT_RE.sub('', value)
        value = _SPEECH_MIDDLE_DOT_RE.sub('、', value)
        return _SPEECH_COMMA_RE.sub('、', value)

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
            finally:
                self._pending_done()
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
            if not self._speak_sapi5_async(speaker, segment, generation):
                return

    def _speak_sapi5_async(self, speaker, text: str, generation: int) -> bool:
        try:
            speech_text = self._normalize_speech_text(text)
            with self._lock:
                volume = self._volume
                rate = self._rate
            speaker.Volume = volume
            speaker.Rate = rate
            self._apply_voice(speaker)
            speaker.Speak(speech_text, _SVSF_ASYNC)
            while True:
                if not self._is_generation_current(generation):
                    speaker.Speak('', _SVSF_ASYNC | _SVSF_PURGE_BEFORE_SPEAK)
                    return False
                if speaker.WaitUntilDone(_SAPI_WAIT_POLL_MS):
                    return self._is_generation_current(generation)
        except Exception:
            error_trace = traceback.format_exc()
            try:
                speaker.Speak('', _SVSF_ASYNC | _SVSF_PURGE_BEFORE_SPEAK)
            except Exception:
                pass
            _log_tts('SAPI5 speak error:\n' + error_trace)
            return False

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
        result_queue, buffer_state = self._start_voicevox_prefetch(segments, index, generation, ctx)
        try:
            while self._is_generation_current(generation):
                if not self._wait_if_paused(generation):
                    return
                try:
                    item = result_queue.get(timeout=0.05)
                except queue.Empty:
                    continue
                if item is _VOICEVOX_PREFETCH_DONE:
                    return
                result = item
                if result.error:
                    _log_tts(f'VOICEVOX synthesize error: speaker={result.speaker} chars={result.chars}\n{result.error}')
                    return
                if not result.data:
                    _log_tts(f'VOICEVOX synthesize returned no audio: speaker={result.speaker} chars={result.chars}')
                    return
                if not self._wait_if_paused(generation):
                    return
                try:
                    if result.starts_segment:
                        ctx['playing'] = result.index
                        self._emit_reading(ctx)
                    buffer_state.start_playback(result.duration_seconds)
                    try:
                        self._play_wav(result.data, generation)
                    finally:
                        buffer_state.finish_playback()
                except Exception:
                    _log_tts('VOICEVOX playback error:\n' + traceback.format_exc())
                    return
                if not self._is_generation_current(generation):
                    return
                if not result.ends_segment:
                    continue
                next_index = self._next_segment_index(segments, result.index + 1)
                gap_end = next_index if next_index >= 0 else len(segments)
                for gap in segments[result.index + 1:gap_end]:
                    if not self._is_generation_current(generation):
                        return
                    if not self._wait_if_paused(generation):
                        return
                    if not gap:
                        time.sleep(0.25)
        finally:
            buffer_state.close()

    def _start_voicevox_prefetch(self, segments: list[str], start_index: int, generation: int, ctx: dict | None=None) -> tuple['queue.Queue', '_VoicevoxBufferState']:
        result_queue: queue.Queue = queue.Queue()
        buffer_state = _VoicevoxBufferState()
        segment_list = list(segments)

        def produce() -> None:
            index = start_index
            sequence = 0
            while index >= 0 and self._is_generation_current(generation):
                source_segment = str(segment_list[index] or '').strip()
                offset = 0
                while offset < len(source_segment) and self._is_generation_current(generation):
                    with self._lock:
                        speaker = self._vv_speaker
                        rate = self._rate
                    remaining = source_segment[offset:]
                    predicted_full = self._estimate_voicevox_synthesis_seconds(remaining, speaker, rate)
                    while sequence > 0 and self._is_generation_current(generation):
                        if not self._wait_if_paused(generation):
                            buffer_state.close()
                            return
                        available = buffer_state.available_seconds()
                        if available < _VOICEVOX_READY_AUDIO_MAX_SECONDS and available < predicted_full + _VOICEVOX_SCHEDULING_MARGIN_SECONDS:
                            break
                        if not buffer_state.wait():
                            return
                    available = buffer_state.available_seconds()
                    if offset == 0 and self._voicevox_cache_contains(remaining):
                        chunk, end = (remaining, len(source_segment))
                    else:
                        chunk, end = self._select_voicevox_chunk(source_segment, offset, available, speaker, rate, startup=sequence == 0)
                    if not chunk or end <= offset:
                        chunk, end = (remaining, len(source_segment))
                    chars = len(chunk)
                    if ctx is not None and offset == 0:
                        with ctx['lock']:
                            ctx['requested'].add(index)
                        self._emit_reading(ctx)
                    started = time.perf_counter()
                    error = None
                    cache_hit = False
                    try:
                        data, speaker, cache_hit = self._synthesize_voicevox_segment(chunk)
                    except Exception:
                        data = None
                        error = traceback.format_exc()
                    elapsed = time.perf_counter() - started
                    if data is None and error is None and (elapsed < _VOICEVOX_RETRY_FAST_FAIL_SECONDS) and self._is_generation_current(generation):
                        _log_tts(f'VOICEVOX synthesize fast-fail retry: speaker={speaker} chars={chars}')
                        time.sleep(0.25)
                        try:
                            data, speaker, cache_hit = self._synthesize_voicevox_segment(chunk)
                        except Exception:
                            data = None
                            error = traceback.format_exc()
                        elapsed = time.perf_counter() - started
                    duration = self._wav_duration_seconds(data) if data else 0.0
                    if data and (not cache_hit):
                        self._record_voicevox_timing(speaker, rate, chars, elapsed, duration)
                    result = _VVResult(index, data, error, speaker, chars, duration_seconds=duration, starts_segment=offset == 0, ends_segment=end >= len(source_segment))
                    if not self._is_generation_current(generation):
                        buffer_state.close()
                        return
                    if data:
                        buffer_state.add_ready(duration)
                    result_queue.put(result)
                    if error or not data:
                        buffer_state.close()
                        return
                    sequence += 1
                    offset = end
                index = self._next_segment_index(segment_list, index + 1)
            if self._is_generation_current(generation):
                result_queue.put(_VOICEVOX_PREFETCH_DONE)

        def worker() -> None:
            try:
                produce()
            except Exception:
                _log_tts('VOICEVOX prefetch worker error:\n' + traceback.format_exc())
                buffer_state.close()
                result_queue.put(_VVResult(start_index, None, 'prefetch worker error', -1, 0))
        threading.Thread(target=worker, daemon=True, name='RTESAssistVoicevoxPrefetch').start()
        return (result_queue, buffer_state)

    def _select_voicevox_chunk(self, text: str, start: int, available_seconds: float, speaker: int, rate: int, *, startup: bool) -> tuple[str, int]:
        endpoints = self._voicevox_chunk_endpoints(text, start)
        if not endpoints:
            return (text[start:].strip(), len(text))
        full_end = endpoints[-1]
        full = text[start:full_end].strip()
        comma_endpoints = endpoints[:-1]
        if not comma_endpoints:
            return (full, full_end)
        if startup:
            first_end = comma_endpoints[0]
            return (text[start:first_end].strip(), first_end)
        available_for_synthesis = max(0.0, float(available_seconds) - _VOICEVOX_SCHEDULING_MARGIN_SECONDS)
        remaining_audio_capacity = max(0.0, _VOICEVOX_READY_AUDIO_MAX_SECONDS - max(0.0, float(available_seconds)))
        if self._estimate_voicevox_synthesis_seconds(full, speaker, rate) <= available_for_synthesis and self._estimate_voicevox_audio_seconds(full, speaker, rate) <= remaining_audio_capacity:
            return (full, full_end)
        selected_end = -1
        for end in comma_endpoints:
            chunk = text[start:end].strip()
            if not chunk:
                continue
            if self._estimate_voicevox_synthesis_seconds(chunk, speaker, rate) <= available_for_synthesis and self._estimate_voicevox_audio_seconds(chunk, speaker, rate) <= remaining_audio_capacity:
                selected_end = end
                continue
            break
        if selected_end >= 0:
            return (text[start:selected_end].strip(), selected_end)
        first_end = comma_endpoints[0]
        return (text[start:first_end].strip(), first_end)

    @staticmethod
    def _voicevox_chunk_endpoints(text: str, start: int) -> list[int]:
        endpoints = [m.end() for m in re.finditer('、+', text[start:])]
        absolute = [start + end for end in endpoints]
        if not absolute or absolute[-1] != len(text):
            absolute.append(len(text))
        return absolute

    def _estimate_voicevox_synthesis_seconds(self, text: str, speaker: int, rate: int) -> float:
        chars = max(1, len(self._normalize_speech_text(text).strip()))
        with self._lock:
            samples = list(self._voicevox_timing_history.get((int(speaker), int(rate)), ()))
        if not samples:
            return _VOICEVOX_FALLBACK_SYNTH_BASE_SECONDS + chars * _VOICEVOX_FALLBACK_SYNTH_SECONDS_PER_CHAR
        ratios = sorted((seconds / max(1, sample_chars) for sample_chars, seconds, _audio in samples))
        percentile_index = min(len(ratios) - 1, max(0, int(len(ratios) * 0.9)))
        return max(0.2, ratios[percentile_index] * chars + 0.2)

    def _estimate_voicevox_audio_seconds(self, text: str, speaker: int, rate: int) -> float:
        chars = max(1, len(self._normalize_speech_text(text).strip()))
        with self._lock:
            samples = list(self._voicevox_timing_history.get((int(speaker), int(rate)), ()))
        audio_samples = [audio / max(1, sample_chars) for sample_chars, _seconds, audio in samples if audio > 0.0]
        if audio_samples:
            audio_samples.sort()
            return max(0.2, audio_samples[len(audio_samples) // 2] * chars)
        speed = max(0.5, min(2.0, 1.0 + int(rate) / 20.0))
        return max(0.2, chars * _VOICEVOX_FALLBACK_AUDIO_SECONDS_PER_CHAR / speed)

    def _record_voicevox_timing(self, speaker: int, rate: int, chars: int, synthesis_seconds: float, audio_seconds: float) -> None:
        if chars <= 0 or synthesis_seconds <= 0.0:
            return
        key = (int(speaker), int(rate))
        with self._lock:
            history = self._voicevox_timing_history.get(key)
            if history is None:
                history = deque(maxlen=_VOICEVOX_TIMING_HISTORY_SIZE)
                self._voicevox_timing_history[key] = history
            history.append((int(chars), float(synthesis_seconds), max(0.0, float(audio_seconds))))

    def _voicevox_timeout_seconds(self, text: str, speaker: int, rate: int) -> float:
        predicted = self._estimate_voicevox_synthesis_seconds(text, speaker, rate)
        return max(_VOICEVOX_TIMEOUT_MIN_SECONDS, min(_VOICEVOX_TIMEOUT_MAX_SECONDS, predicted * _VOICEVOX_TIMEOUT_MULTIPLIER + _VOICEVOX_TIMEOUT_PADDING_SECONDS))

    @staticmethod
    def _wav_duration_seconds(data: bytes) -> float:
        try:
            with wave.open(io.BytesIO(data), 'rb') as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate()
                if rate > 0:
                    return frames / float(rate)
        except Exception:
            pass
        return max(0.3, min(30.0, len(data) / 88200.0))

    def _voicevox_cache_contains(self, segment: str) -> bool:
        speech_segment = self._normalize_speech_text(segment)
        with self._lock:
            key = (speech_segment, self._vv_speaker, self._rate, self._volume)
            return key in self._voicevox_cache

    def _synthesize_voicevox_segment(self, segment: str):
        import voicevox_client as vv
        speech_segment = self._normalize_speech_text(segment)
        with self._lock:
            rate = self._rate
            volume_value = self._volume
            speaker = self._vv_speaker
            cache_key = (speech_segment, speaker, rate, volume_value)
            cached = self._voicevox_cache.get(cache_key)
            if cached is not None:
                self._voicevox_cache.move_to_end(cache_key)
                return (cached, speaker, True)
        speed = max(0.5, min(2.0, 1.0 + rate / 20.0))
        volume = max(0.0, min(2.0, volume_value / 100.0))
        timeout = self._voicevox_timeout_seconds(speech_segment, speaker, rate)
        data = vv.synthesize(speech_segment, speaker, speed=speed, volume=volume, timeout=timeout)
        if data:
            with self._lock:
                self._voicevox_cache[cache_key] = data
                self._voicevox_cache.move_to_end(cache_key)
                while len(self._voicevox_cache) > _VOICEVOX_CACHE_MAX:
                    self._voicevox_cache.popitem(last=False)
        return (data, speaker, False)

    @staticmethod
    def _next_segment_index(segments: list[str], start: int) -> int:
        for index in range(start, len(segments)):
            if segments[index]:
                return index
        return -1

    def _play_wav(self, data: bytes, generation: int) -> None:
        try:
            from services import audio_player
            audio_player.get_client().play_tts_and_wait(data, should_continue=lambda: self._is_generation_current(generation), is_paused=self._is_paused)
        except Exception:
            _log_tts('VOICEVOX playback error:\n' + traceback.format_exc())

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
