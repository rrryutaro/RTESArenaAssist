from __future__ import annotations
import re
from typing import Iterable, Optional
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

def extract_displayed_name(text: str, expected_suffix: str, prefixes: Iterable[str]=()) -> Optional[str]:
    if not text or not expected_suffix:
        return None
    pattern = _name_pattern(prefixes, expected_suffix)
    if pattern is None:
        return None
    m = pattern.search(text)
    return m.group() if m is not None else None

def extract_tavern_displayed_name(text: str, prefixes: Iterable[str], suffixes: Iterable[str]) -> Optional[str]:
    if not text:
        return None
    prefix_values = tuple((value for value in prefixes if value))
    suffix_values = tuple((value for value in suffixes if value))
    if not prefix_values or not suffix_values:
        return None
    pattern = re.compile('(?<![A-Za-z])(?:' + '|'.join((re.escape(value) for value in prefix_values)) + ') (?:' + '|'.join((re.escape(value) for value in suffix_values)) + ')(?![A-Za-z])')
    match = pattern.search(text)
    return match.group() if match is not None else None
__all__ = ['extract_displayed_name', 'extract_tavern_displayed_name']
