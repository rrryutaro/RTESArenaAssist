from __future__ import annotations
import re
from typing import Iterable, Optional
_WINDOW_START = 3014656
_WINDOW_SIZE = 131072
_FILL = {'%ef': "[A-Z][A-Za-z'\\-]{1,24}", '%n': "[A-Z][A-Za-z'\\- ]{1,32}", '%ct': '[A-Za-z][A-Za-z ]{1,24}'}

def _name_pattern(prefixes: Iterable[str], suffix: str) -> Optional[re.Pattern]:
    alts = []
    for pre in prefixes:
        body = re.escape(pre)
        for token, fill in _FILL.items():
            body = body.replace(re.escape(token), fill)
        alts.append(body)
    if not alts:
        return None
    return re.compile('(?<![A-Za-z])(?:' + '|'.join(alts) + ') ' + re.escape(suffix))

def read_displayed_name(analyzer, anchor: Optional[int], expected_suffix: str, prefixes: Iterable[str]=()) -> Optional[str]:
    if analyzer is None or anchor is None or (not expected_suffix):
        return None
    pattern = _name_pattern(prefixes, expected_suffix)
    if pattern is None:
        return None
    try:
        raw = analyzer.read_bytes(anchor + _WINDOW_START, _WINDOW_SIZE)
    except (OSError, AttributeError, ValueError):
        return None
    if not raw:
        return None
    m = pattern.search(raw.decode('latin-1'))
    return m.group() if m is not None else None
__all__ = ['read_displayed_name']
