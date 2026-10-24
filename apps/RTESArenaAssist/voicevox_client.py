from __future__ import annotations
import errno
import http.client
import json
import logging
import threading
import urllib.error
import urllib.parse
DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 50021
STATUS_OK = 'ok'
STATUS_UNREACHABLE = 'unreachable'
STATUS_PORT_EXHAUSTED = 'port_exhausted'
STATUS_SPEAKER_MISSING = 'speaker_missing'
STATUS_ERROR = 'error'
_WSAENOBUFS = 10055
_WSAECONNREFUSED = 10061
_status_lock = threading.Lock()
_status: dict = {'code': None, 'detail': '', 'seq': 0}

def _base() -> str:
    return f'http://{DEFAULT_HOST}:{DEFAULT_PORT}'

class VoicevoxHTTPError(Exception):

    def __init__(self, code: int) -> None:
        super().__init__(f'HTTP {code}')
        self.code = code

def _request(method: str, path: str, *, body: bytes | None=None, headers: dict | None=None, timeout: float) -> bytes:
    conn = http.client.HTTPConnection(DEFAULT_HOST, DEFAULT_PORT, timeout=timeout)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        data = resp.read()
    finally:
        conn.close()
    if resp.status >= 400:
        raise VoicevoxHTTPError(resp.status)
    return data

def classify_error(exc: BaseException) -> tuple[str, str]:
    reason = exc.reason if isinstance(exc, urllib.error.URLError) and (not isinstance(exc, urllib.error.HTTPError)) else exc
    detail = f'{type(reason).__name__}: {reason}'
    if isinstance(exc, (urllib.error.HTTPError, VoicevoxHTTPError)):
        return (STATUS_ERROR, f'HTTP {exc.code}')
    if isinstance(reason, OSError):
        winerror = getattr(reason, 'winerror', None)
        if winerror == _WSAENOBUFS or reason.errno == errno.ENOBUFS:
            return (STATUS_PORT_EXHAUSTED, detail)
        if winerror == _WSAECONNREFUSED or isinstance(reason, ConnectionRefusedError) or isinstance(reason, TimeoutError):
            return (STATUS_UNREACHABLE, detail)
    return (STATUS_ERROR, detail)

def _record(code: str, detail: str='') -> None:
    with _status_lock:
        before = _status['code']
        if before == code and (code == STATUS_OK or _status['detail'] == detail):
            return
        _status['code'] = code
        _status['detail'] = detail
        _status['seq'] += 1
    logging.getLogger('poll_controller').warning('VOICEVOX status: %s -> %s%s', before, code, f' ({detail})' if detail else '')

def last_status() -> tuple[str | None, str, int]:
    with _status_lock:
        return (_status['code'], _status['detail'], _status['seq'])

def check(speaker_id: int | None=None, timeout: float=3.0) -> tuple[str, str]:
    try:
        _request('GET', '/version', timeout=timeout)
        if speaker_id is not None:
            raw = json.loads(_request('GET', '/speakers', timeout=timeout).decode('utf-8'))
            ids = {int(st.get('id')) for sp in raw for st in sp.get('styles', []) if st.get('id') is not None}
            if int(speaker_id) not in ids:
                result = (STATUS_SPEAKER_MISSING, f'speaker={int(speaker_id)}')
                _record(*result)
                return result
    except Exception as exc:
        result = classify_error(exc)
        _record(*result)
        return result
    _record(STATUS_OK)
    return (STATUS_OK, '')

def is_available(timeout: float=0.3) -> bool:
    try:
        _request('GET', '/version', timeout=timeout)
        return True
    except Exception:
        return False

def list_speakers(timeout: float=3.0) -> list[dict]:
    try:
        raw = json.loads(_request('GET', '/speakers', timeout=timeout).decode('utf-8'))
    except Exception:
        return []
    out: list[dict] = []
    for sp in raw:
        try:
            styles = [{'name': st.get('name', ''), 'id': int(st.get('id'))} for st in sp.get('styles', []) if st.get('id') is not None]
            if styles:
                out.append({'name': sp.get('name', ''), 'styles': styles})
        except Exception:
            continue
    return out

def synthesize(text: str, speaker_id: int, *, speed: float=1.0, volume: float=1.0, timeout: float=15.0) -> bytes | None:
    t = (text or '').strip()
    if not t:
        return None
    try:
        q = urllib.parse.urlencode({'text': t, 'speaker': int(speaker_id)})
        query = json.loads(_request('POST', '/audio_query?' + q, body=b'', timeout=timeout).decode('utf-8'))
        query['speedScale'] = float(speed)
        query['volumeScale'] = float(volume)
        q2 = urllib.parse.urlencode({'speaker': int(speaker_id)})
        body = json.dumps(query).encode('utf-8')
        data = _request('POST', '/synthesis?' + q2, body=body, headers={'Content-Type': 'application/json'}, timeout=timeout)
    except VoicevoxHTTPError as exc:
        if exc.code in (404, 422):
            _record(STATUS_SPEAKER_MISSING, f'speaker={int(speaker_id)} HTTP {exc.code}')
        else:
            _record(*classify_error(exc))
        return None
    except Exception as exc:
        _record(*classify_error(exc))
        return None
    _record(STATUS_OK)
    return data
__all__ = ['is_available', 'list_speakers', 'synthesize', 'check', 'last_status', 'classify_error', 'DEFAULT_HOST', 'DEFAULT_PORT', 'STATUS_OK', 'STATUS_UNREACHABLE', 'STATUS_PORT_EXHAUSTED', 'STATUS_SPEAKER_MISSING', 'STATUS_ERROR']
