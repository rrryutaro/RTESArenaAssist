from __future__ import annotations
import json
import urllib.parse
import urllib.request
DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 50021

def _base() -> str:
    return f'http://{DEFAULT_HOST}:{DEFAULT_PORT}'

def is_available(timeout: float=0.3) -> bool:
    try:
        req = urllib.request.Request(_base() + '/version', method='GET')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return getattr(resp, 'status', 200) == 200
    except Exception:
        return False

def list_speakers(timeout: float=3.0) -> list[dict]:
    try:
        req = urllib.request.Request(_base() + '/speakers', method='GET')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode('utf-8'))
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
        req = urllib.request.Request(_base() + '/audio_query?' + q, data=b'', method='POST')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            query = json.loads(resp.read().decode('utf-8'))
        query['speedScale'] = float(speed)
        query['volumeScale'] = float(volume)
        q2 = urllib.parse.urlencode({'speaker': int(speaker_id)})
        body = json.dumps(query).encode('utf-8')
        req2 = urllib.request.Request(_base() + '/synthesis?' + q2, data=body, method='POST', headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req2, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        return None
__all__ = ['is_available', 'list_speakers', 'synthesize', 'DEFAULT_HOST', 'DEFAULT_PORT']
