from game_surface import game_surface

def _sound_only(text_index: int) -> bool:
    return text_index == 255
_RIDDLE_MARKER = '^'
_RIDDLE_ANSWER = ':'
_RIDDLE_RESPONSE = '`'

def extract_riddle_question(chunk_text: str) -> str:
    out: list[str] = []
    for line in chunk_text.replace('\r', '\n').split('\n'):
        stripped = line.strip()
        if stripped.startswith(_RIDDLE_RESPONSE):
            break
        if stripped.startswith(_RIDDLE_MARKER) or stripped.startswith(_RIDDLE_ANSWER):
            continue
        out.append(line)
    return '\n'.join(out).strip()

def extract_riddle_response(chunk_text: str) -> str:
    out: list[str] = []
    for line in chunk_text.replace('\r', '\n').split('\n'):
        if line.strip().startswith(_RIDDLE_RESPONSE):
            continue
        out.append(line)
    return '\n'.join(out).strip()

def riddle_part_ranges(raw_block: bytes) -> list[dict]:
    out: list[dict] = []
    group = -1
    pos = 0
    for part in raw_block.split(b'\x00'):
        if part:
            head = part.decode('ascii', errors='replace').lstrip('~')
            if head.startswith(_RIDDLE_MARKER):
                group += 1
                out.append({'kind': 'question', 'start': pos, 'len': len(part), 'group': group})
            elif head.startswith(_RIDDLE_RESPONSE) and group >= 0:
                upper = head[1:].upper()
                kind = 'correct' if upper.startswith('CORRECT') else 'wrong' if upper.startswith('WRONG') else None
                if kind:
                    out.append({'kind': kind, 'start': pos, 'len': len(part), 'group': group})
        pos += len(part) + 1
    return out

def _norm_riddle_text(s: str) -> str:
    return game_surface(s or '')

def find_riddle_group(raw_block: bytes, question_text: str) -> list[dict]:
    target = _norm_riddle_text(question_text)
    if not target:
        return []
    ranges = riddle_part_ranges(raw_block)
    for r in ranges:
        if r['kind'] != 'question':
            continue
        chunk = raw_block[r['start']:r['start'] + r['len']]
        text = chunk.decode('ascii', errors='replace').lstrip('~')
        if _norm_riddle_text(extract_riddle_question(text)) == target:
            g = r['group']
            return [x for x in ranges if x['group'] == g]
    return []

def riddle_answers(raw_block: bytes, question_text: str) -> list[str]:
    ranges = find_riddle_group(raw_block, question_text)
    q = next((r for r in ranges if r['kind'] == 'question'), None)
    if q is None:
        return []
    chunk = raw_block[q['start']:q['start'] + q['len']].decode('ascii', errors='replace')
    out: list[str] = []
    for line in chunk.replace('\r', '\n').split('\n'):
        s = line.strip()
        if s.startswith(_RIDDLE_ANSWER):
            v = s[1:].strip()
            if v:
                out.append(v)
    return out

def classify_riddle_part(ptr: int, base: int, ranges: list[dict]) -> dict | None:
    off = ptr - base
    for r in ranges:
        if r['start'] <= off < r['start'] + r['len']:
            return r
    return None

def _chunk_to_trigger_text(chunk: bytes) -> str | None:
    text = chunk.decode('ascii', errors='replace').strip().lstrip('~')
    if not text:
        return None
    ratio = sum((32 <= ord(c) <= 126 for c in text)) / max(len(text), 1)
    if ratio < 0.7:
        return None
    if text.startswith(_RIDDLE_MARKER):
        text = extract_riddle_question(text)
    elif text.startswith(_RIDDLE_RESPONSE):
        text = extract_riddle_response(text)
    return text.replace('\r', ' ').replace('\n', ' ')

def extract_trigger_texts(raw_block: bytes) -> list[str]:
    texts = []
    for chunk in raw_block.split(b'\x00'):
        text = _chunk_to_trigger_text(chunk)
        if text:
            texts.append(text)
    return texts

def get_trigger_text_by_index(raw_block: bytes, text_index: int) -> str:
    number = -1
    for chunk in raw_block.split(b'\x00'):
        if not chunk:
            continue
        head = chunk.decode('ascii', errors='replace').lstrip('~')
        if not head.strip():
            continue
        is_response = head.startswith(_RIDDLE_RESPONSE)
        if not is_response:
            number += 1
            if number == text_index:
                return _chunk_to_trigger_text(chunk) or ''
        if number > text_index:
            break
    return ''

class MifTriggerMatcher:

    def __init__(self, mif_dir: str=''):
        self._mif_dir = mif_dir
        self._loaded_mif: str = ''
        self._trigs_by_level: list[list[tuple[int, int, int, int]]] = []
        self._info_by_level: list[str] = []
        self._active_level: int | None = None
        self._matched_level: int | None = None
        self._last_status: str = 'unknown'
        self._last_mif_entry: tuple[int, int, int, int] | None = None
        self._source: str = 'none'

    def update_map(self, mif_name: str, level_index: int | None=None) -> bool:
        if mif_name and mif_name != self._loaded_mif:
            self._load_levels(mif_name)
        self._active_level = level_index
        return any(self._trigs_by_level)

    def _load_levels(self, mif_name: str) -> None:
        levels: list[list[tuple[int, int, int, int]]] = []
        infos: list[str] = []
        try:
            from runtime_paths import resolve_arena_install_dir
            from services.mif_loader import DEFAULT_MIF_DIR, load_mif
            dirs = [d for d in (self._mif_dir or None, DEFAULT_MIF_DIR, resolve_arena_install_dir()) if d]
            head = load_mif(mif_name, dirs)
            if head is not None:
                want = max(int(head.level_count or 1), 1)
                for i in range(want):
                    lv = head if i == head.level_index else load_mif(mif_name, dirs, level_index_override=i)
                    trigs = [(t.x, t.y, t.text_index, t.sound_index) for t in (lv.trigs if lv is not None else []) or []]
                    levels.append(trigs)
                    infos.append(getattr(lv, 'info_name', '') or '')
        except Exception:
            levels = []
            infos = []
        self._trigs_by_level = levels
        self._info_by_level = infos
        self._matched_level = None
        self._loaded_mif = mif_name
        self._source = 'mif_levels' if any(levels) else 'none'
        self._last_status = 'unknown' if any(levels) else 'mif_trig_not_found'

    def _match_in(self, trigs: list[tuple[int, int, int, int]], rt_x: int, rt_y: int) -> list[tuple[int, int, int, int]]:
        return [e for e in trigs if e[0] == rt_x and e[1] == rt_y and (not _sound_only(e[2]))]

    def find_text_index(self, rt_x: int, rt_y: int) -> int | None:
        self._last_mif_entry = None
        self._matched_level = None
        if not any(self._trigs_by_level):
            self._last_status = 'mif_not_loaded' if not self._loaded_mif else 'mif_trig_not_found'
            return None
        lvl = self._active_level
        if lvl is not None and 0 <= lvl < len(self._trigs_by_level):
            hits = self._match_in(self._trigs_by_level[lvl], rt_x, rt_y)
            hit_levels = [lvl] if hits else []
        else:
            hits = []
            hit_levels = []
            for li, trigs in enumerate(self._trigs_by_level):
                lv_hits = self._match_in(trigs, rt_x, rt_y)
                if lv_hits:
                    hits.extend(lv_hits)
                    hit_levels.append(li)
            if len({e[2] for e in hits}) > 1:
                self._last_status = 'mif_coord_ambiguous'
                return None
        if hits:
            self._last_mif_entry = hits[0]
            if len(hit_levels) == 1:
                self._matched_level = hit_levels[0]
            self._last_status = 'matched'
            return hits[0][2]
        self._last_status = 'mif_coord_not_found'
        return None

    def declared_inf_name(self) -> str:
        infos = self._info_by_level
        if not infos:
            return ''
        for lvl in (self._matched_level, self._active_level):
            if lvl is not None and 0 <= lvl < len(infos) and infos[lvl]:
                return infos[lvl]
        uniq = {n for n in infos if n}
        if len(uniq) == 1:
            return next(iter(uniq))
        return ''

    @property
    def trig_count(self) -> int:
        return sum((len(t) for t in self._trigs_by_level))

    @property
    def loaded_mif(self) -> str:
        return self._loaded_mif

    @property
    def last_status(self) -> str:
        return self._last_status

    @property
    def last_mif_entry(self) -> tuple[int, int, int, int] | None:
        return self._last_mif_entry

    @property
    def source(self) -> str:
        return self._source
