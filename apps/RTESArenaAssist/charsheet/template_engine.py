from __future__ import annotations
import html
import re
from typing import Mapping, Optional, Union
from charsheet.values import IMAGE_KEYS, LABEL_KEYS, UNKNOWN, VALUE_KEYS
_KEY = '[A-Za-z][A-Za-z0-9_]*(?:\\.[A-Za-z][A-Za-z0-9_]*)?'
_TAG_RE = re.compile('\\{\\{\\s*(?:#if\\s+(?P<if>' + _KEY + ')|(?P<else>else)|(?P<end>/if)|(?P<key>' + _KEY + '))\\s*\\}\\}')
_TITLE_RE = re.compile('<title[^>]*>(.*?)</title>', re.IGNORECASE | re.DOTALL)
_COMMENT_RE = re.compile('<!--.*?-->', re.DOTALL)
_KNOWN: dict[str, frozenset[str]] = {'': frozenset(VALUE_KEYS), 'label': frozenset(LABEL_KEYS), 'img': frozenset(IMAGE_KEYS)}

class _Key:
    __slots__ = ('key',)

    def __init__(self, key: str) -> None:
        self.key = key

class _Mark:
    __slots__ = ('tag',)

    def __init__(self, tag: str) -> None:
        self.tag = tag

class _If:
    __slots__ = ('key', 'then', 'otherwise')

    def __init__(self, key: str) -> None:
        self.key = key
        self.then: list = []
        self.otherwise: Optional[list] = None
_Node = Union[str, _Key, _Mark, _If]

def _outside_comments(template_html: str) -> list[tuple[bool, str]]:
    parts: list[tuple[bool, str]] = []
    position = 0
    for match in _COMMENT_RE.finditer(template_html):
        parts.append((False, template_html[position:match.start()]))
        parts.append((True, match.group(0)))
        position = match.end()
    parts.append((False, template_html[position:]))
    return parts

def _parse(template_html: str) -> list[_Node]:
    root: list[_Node] = []
    current = root
    stack: list[tuple[list[_Node], _If]] = []
    for is_comment, text in _outside_comments(template_html or ''):
        if is_comment:
            current.append(text)
            continue
        position = 0
        for match in _TAG_RE.finditer(text):
            if match.start() > position:
                current.append(text[position:match.start()])
            position = match.end()
            if match.group('if'):
                node = _If(match.group('if'))
                current.append(node)
                stack.append((current, node))
                current = node.then
            elif match.group('else'):
                if not stack or stack[-1][1].otherwise is not None:
                    current.append(_Mark('else'))
                else:
                    stack[-1][1].otherwise = []
                    current = stack[-1][1].otherwise
            elif match.group('end'):
                if not stack:
                    current.append(_Mark('/if'))
                else:
                    current = stack.pop()[0]
            else:
                current.append(_Key(match.group('key')))
        if position < len(text):
            current.append(text[position:])
    while stack:
        current = stack.pop()[0]
        current.append(_Mark('/if'))
    return root

def _split(key: str) -> tuple[str, str]:
    if '.' in key:
        kind, name = key.split('.', 1)
        return (kind, name)
    return ('', key)

def is_known(key: str) -> bool:
    kind, name = _split(key)
    return name in _KNOWN.get(kind, frozenset())

def _keys(nodes: list[_Node], seen: dict[str, None]) -> None:
    for node in nodes:
        if isinstance(node, _Key):
            seen.setdefault(node.key, None)
        elif isinstance(node, _If):
            seen.setdefault(node.key, None)
            _keys(node.then, seen)
            _keys(node.otherwise or [], seen)

def placeholders(template_html: str) -> list[str]:
    seen: dict[str, None] = {}
    _keys(_parse(template_html), seen)
    return list(seen)

def unknown_placeholders(template_html: str) -> list[str]:
    return [key for key in placeholders(template_html) if not is_known(key)]

def render(template_html: str, values: Mapping[str, str], labels: Mapping[str, str], images: Mapping[str, str]) -> str:

    def text_of(key: str) -> str:
        kind, name = _split(key)
        if kind == 'label':
            return labels.get(name) or ''
        if kind == 'img':
            return images.get(name) or ''
        return values.get(name) or ''

    def emit(nodes: list[_Node], out: list[str]) -> None:
        for node in nodes:
            if isinstance(node, str):
                out.append(node)
            elif isinstance(node, _Key):
                if not is_known(node.key):
                    out.append(html.escape(f'[{node.key}?]'))
                elif _split(node.key)[0]:
                    out.append(html.escape(text_of(node.key), quote=True))
                else:
                    out.append(html.escape(text_of(node.key) or UNKNOWN, quote=True))
            elif isinstance(node, _Mark):
                out.append(html.escape(f'[{node.tag}?]'))
            elif not is_known(node.key):
                out.append(html.escape(f'[{node.key}?]'))
                emit(node.otherwise or [], out)
            elif text_of(node.key):
                emit(node.then, out)
            else:
                emit(node.otherwise or [], out)
    out: list[str] = []
    emit(_parse(template_html), out)
    return ''.join(out)

def title_of(template_html: str) -> Optional[str]:
    match = _TITLE_RE.search(template_html or '')
    if not match:
        return None
    text = html.unescape(re.sub('\\s+', ' ', match.group(1))).strip()
    return text or None
__all__ = ['is_known', 'placeholders', 'unknown_placeholders', 'render', 'title_of']
