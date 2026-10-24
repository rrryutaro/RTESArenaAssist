from __future__ import annotations
import i18n_helper as i18n
_REASON_KEYS = {'unreachable': 'tts.vv_problem.unreachable', 'port_exhausted': 'tts.vv_problem.port_exhausted', 'speaker_missing': 'tts.vv_problem.speaker_missing'}

def title() -> str:
    return i18n.tr('tts.vv_problem.title')

def problem_text(code: str, detail: str, *, speaker: int, fallback_sapi: bool) -> str:
    key = _REASON_KEYS.get(code, 'tts.vv_problem.error')
    reason = i18n.tr(key, speaker=speaker, detail=detail)
    tail = i18n.tr('tts.vv_problem.fallback_on' if fallback_sapi else 'tts.vv_problem.fallback_off')
    return f'{reason}\n{tail}'

def recovered_text() -> str:
    return i18n.tr('tts.vv_recovered')
