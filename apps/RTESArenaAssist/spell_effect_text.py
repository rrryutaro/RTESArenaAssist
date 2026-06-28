from __future__ import annotations
import re

def _template_ja(idx: int) -> str | None:
    import i18n_helper as i18n
    return i18n.text_opt(f'spell_effect_text.template.{idx}')
_PLACEHOLDER_RE = re.compile('%(\\d|a|b|c|f)')

def _parse_spellmkr(data: str) -> dict[int, str]:
    out: dict[int, str] = {}
    for m in re.finditer('#(\\d+)\\r?\\n(.*?)(?=#\\d+\\r?\\n|$)', data, re.S):
        out[int(m.group(1))] = ' '.join(m.group(2).split())
    return out

def _en_templates() -> dict[int, str]:
    try:
        from runtime_paths import install_vfs
        vfs = install_vfs()
        if vfs is not None:
            data = vfs.read('SPELLMKR.TXT')
            if data is not None:
                return _parse_spellmkr(data.decode('latin-1', errors='replace'))
    except Exception:
        pass
    return {}
_COMPILED: list[tuple[re.Pattern, list[str], int]] | None = None

def _build() -> list[tuple[re.Pattern, list[str], int]]:
    out: list[tuple[re.Pattern, list[str], int]] = []
    for idx, en in _en_templates().items():
        if _template_ja(idx) is None:
            continue
        order: list[str] = []
        seen: dict[str, str] = {}
        parts: list[str] = []
        last = 0
        for m in re.finditer('%%|%(\\d|a|b|c|f)', en):
            parts.append(re.escape(en[last:m.start()]))
            tok = m.group(0)
            if tok == '%%':
                parts.append('%')
            else:
                name = tok[1:]
                gid = f'p_{name}'
                if name in seen:
                    parts.append(f'(?P={gid})')
                else:
                    seen[name] = gid
                    order.append(name)
                    if name in ('b',):
                        parts.append(f'(?P<{gid}>\\w*)')
                    elif name in ('c',):
                        parts.append(f'(?P<{gid}>[A-Za-z]+)')
                    elif name in ('f',):
                        parts.append(f'(?P<{gid}>[^.]+?)')
                    else:
                        parts.append(f'(?P<{gid}>\\d+)')
            last = m.end()
        parts.append(re.escape(en[last:]))
        pattern = '^' + ''.join(parts) + '\\.?\\s*$'
        try:
            out.append((re.compile(pattern), order, idx))
        except re.error:
            continue
    return out

def _candidate_prefixes(text_en: str) -> list[str]:
    s = ' '.join((text_en or '').split()).strip()
    if not s:
        return []
    out: list[str] = [s]
    for m in re.finditer('\\.', s):
        cand = s[:m.end()].strip()
        if cand and cand not in out:
            out.append(cand)
    return sorted(out, key=len, reverse=True)

def _translate_value(name: str, value: str) -> str:
    import i18n_helper as i18n
    if name == 'c':
        return i18n.value('spell_effect_text', value) or value
    if name in ('b', 'f'):
        v = value.strip()
        if name == 'b' and v == '':
            return i18n.text_opt('spell_effect_text.slot_b_absent') or ''
        return i18n.value('spell_effect_text', v) or v
    return value

def match_template(text_en: str) -> tuple[int, str, str] | None:
    global _COMPILED
    if not text_en:
        return None
    if _COMPILED is None:
        _COMPILED = _build()
    for s in _candidate_prefixes(text_en):
        for pattern, order, idx in _COMPILED:
            m = pattern.match(s)
            if not m:
                continue
            ja = _template_ja(idx) or ''
            for name in order:
                val = _translate_value(name, m.group(f'p_{name}'))
                ja = ja.replace(f'%{name}', val)
            ja = ja.replace('%%', '%')
            return (idx, s, ja)
    return None

def normalize(text_en: str) -> str:
    matched = match_template(text_en)
    return matched[1] if matched else ' '.join((text_en or '').split()).strip()

def translate(text_en: str) -> str:
    matched = match_template(text_en)
    return matched[2] if matched else ''
__all__ = ['match_template', 'normalize', 'translate']
