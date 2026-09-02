from __future__ import annotations
from typing import Optional, Tuple
import threading
import time
import i18n_helper as _i18n
FLAG_STATUS_POPUP_OFFSET = 4794
FLAG_EQUIPMENT_OPEN_OFFSET = 4762
FLAG_SPELL_DETAIL_OFFSET = 6890
SPELL_INDEX_OFFSET = 4758
SPELL_DETAIL_ACTIVE_OFFSET = 37790
SCREEN_BUFFER_OFFSET = 84288
SCREEN_ROW_BYTES = 320
SCREEN_ROWS = 200
PALETTE_OFFSET = 3089872
PALETTE_BYTES = 256 * 3
PALETTE_IS_VGA_6BIT = True
ACTION_TEXT_ROW = 24
ACTION_TEXT_COL_FIRST = 148
ACTION_TEXT_COL_LAST = 171
ACTION_TEXT_ROW_FIRST = 20
ACTION_TEXT_ROW_LAST = 28
ACTION_TEXT_RGB = (195, 0, 0)
SPELL_VIEW_OFFSET = 36718
MENU_ACTIVE_OFFSET = 4732
POPUP_OPEN_OFFSET = 31012
CITY_NPC_ACTIVE_OFFSET = 43077
ACTION_ACTIVE_OFFSET = 31145
SCREEN_IDS: frozenset = frozenset({'quote', 'scroll01', 'scroll02', 'menu', 'loadsave', 'newgame_intro', 'race_select', 'race_confirm', 'race_description', 'status_proclamation', 'class_select', 'class_list', 'class_accept', 'ten_questions', 'province_confirm', 'class_advice', 'goyenow', 'distribute', 'choose_attrs', 'name_input', 'sex_select', 'appearance', 'chargen_complete', 'opening_cinematic', 'game_screen', 'status_page', 'bonus_screen', 'equipment', 'spellbook', 'spell_detail', 'system_menu', 'loadsave_in_play', 'automap', 'logbook', 'npc_dialog', 'combat', 'shop', 'travel_map', 'message_box', 'loading', 'unknown'})

def _tr(sid: str, **kwargs) -> str:
    return _i18n.tr(f'screen.{sid}', **kwargs)

def _read_u8(analyzer, addr: int) -> int:
    try:
        return analyzer.read_bytes(addr, 1)[0]
    except (OSError, AttributeError):
        return 0

def read_screen_row(analyzer, anchor: int, row: int=0) -> bytes | None:
    try:
        return analyzer.read_bytes(anchor + SCREEN_BUFFER_OFFSET + row * SCREEN_ROW_BYTES, SCREEN_ROW_BYTES)
    except (OSError, AttributeError):
        return None

def is_spell_detail_drawn(analyzer, anchor: int) -> bool | None:
    row = read_screen_row(analyzer, anchor, 0)
    if row is None or len(row) < SCREEN_ROW_BYTES:
        return None
    return 0 in row

def read_palette(analyzer, anchor: int) -> bytes | None:
    try:
        raw = analyzer.read_bytes(anchor + PALETTE_OFFSET, PALETTE_BYTES)
    except (OSError, AttributeError, RuntimeError):
        return None
    if len(raw) < PALETTE_BYTES:
        return None
    if not PALETTE_IS_VGA_6BIT:
        return bytes(raw)
    return bytes(((v << 2 | v >> 4) & 255 for v in raw))

def resolve_action_text_color_index(analyzer, anchor: int) -> int | None:
    pal = read_palette(analyzer, anchor)
    if pal is None:
        return None
    want = bytes(ACTION_TEXT_RGB)
    for index in range(256):
        if pal[index * 3:index * 3 + 3] == want:
            return index
    return None

def action_text_probe_addr(anchor: int) -> tuple[int, int]:
    return (anchor + SCREEN_BUFFER_OFFSET + ACTION_TEXT_ROW * SCREEN_ROW_BYTES + ACTION_TEXT_COL_FIRST, ACTION_TEXT_COL_LAST - ACTION_TEXT_COL_FIRST + 1)

def is_action_text_drawn(analyzer, anchor: int) -> bool | None:
    color = resolve_action_text_color_index(analyzer, anchor)
    if color is None:
        return None
    addr, size = action_text_probe_addr(anchor)
    try:
        line = analyzer.read_bytes(addr, size)
    except (OSError, AttributeError):
        return None
    if len(line) < size:
        return None
    return color in line

class ActionTextWatcher:
    INTERVAL_SEC = 0.004
    IDLE_INTERVAL_SEC = 0.2
    PALETTE_REFRESH_SEC = 0.5

    def __init__(self) -> None:
        self._thread = None
        self._stop = None
        self._lock = threading.Lock()
        self._seen = False
        self._readable = False
        self._key = None
        self._samples = 0
        self._hits = 0
        self._first_sample_at = None
        self._last_sample_at = None
        self._active = True
        self._fine = False
        self._color = None

    def ensure(self, analyzer, anchor: int) -> None:
        key = (id(analyzer), anchor)
        if self._thread is not None and self._thread.is_alive() and (self._key == key):
            return
        self.stop()
        self._key = key
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(analyzer, anchor, self._stop), name='action-text-watch', daemon=True)
        self._thread.start()

    def set_active(self, active: bool) -> None:
        with self._lock:
            self._active = bool(active)

    def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()
        self._thread = None
        self._stop = None
        with self._lock:
            self._seen = False
            self._readable = False

    def consume(self) -> bool | None:
        with self._lock:
            if not self._readable:
                return None
            seen = self._seen
            self._seen = False
            return seen

    def color_index(self):
        with self._lock:
            return self._color

    def stats(self) -> tuple[int, int, int]:
        with self._lock:
            span = 0.0
            if self._first_sample_at is not None and self._last_sample_at is not None and (self._samples > 1):
                span = self._last_sample_at - self._first_sample_at
            ms = int(round(span * 1000.0 / (self._samples - 1))) if self._samples > 1 and span > 0 else 0
            return (self._samples, self._hits, ms)

    @staticmethod
    def _timer_resolution(enter: bool) -> None:
        try:
            import ctypes
            fn = ctypes.windll.winmm.timeBeginPeriod if enter else ctypes.windll.winmm.timeEndPeriod
            fn(1)
        except Exception:
            pass

    def _run(self, analyzer, anchor: int, stop) -> None:
        try:
            self._loop(analyzer, anchor, stop)
        finally:
            if self._fine:
                self._timer_resolution(False)
                self._fine = False

    def _loop(self, analyzer, anchor: int, stop) -> None:
        addr, size = action_text_probe_addr(anchor)
        color = None
        next_palette = 0.0
        while not stop.is_set():
            with self._lock:
                active = self._active
            if active != self._fine:
                self._timer_resolution(active)
                self._fine = active
            if not active:
                with self._lock:
                    self._readable = False
                stop.wait(self.IDLE_INTERVAL_SEC)
                continue
            now = time.monotonic()
            if now >= next_palette:
                next_palette = now + self.PALETTE_REFRESH_SEC
                color = resolve_action_text_color_index(analyzer, anchor)
                with self._lock:
                    self._color = color
            ok = False
            band = None
            if color is not None:
                try:
                    band = analyzer.read_bytes(addr, size)
                    ok = len(band) >= size
                except (OSError, AttributeError, RuntimeError):
                    ok = False
                    band = None
            with self._lock:
                self._readable = ok
                if ok:
                    self._samples += 1
                    if self._first_sample_at is None:
                        self._first_sample_at = now
                    self._last_sample_at = now
                    if color in band:
                        self._seen = True
                        self._hits += 1
            stop.wait(self.INTERVAL_SEC)

def _read_u16_le(analyzer, addr: int) -> int:
    try:
        b = analyzer.read_bytes(addr, 2)
        return b[0] | b[1] << 8
    except (OSError, AttributeError):
        return 65535
_CITY_NPC_PHASE_ASKING = 133
_CITY_NPC_PHASE_RESPONDING = 16

def is_city_npc_dialog_active(raw_value: int) -> bool:
    return int(raw_value) & 255 in (_CITY_NPC_PHASE_ASKING, _CITY_NPC_PHASE_RESPONDING)

def _detect_pregame_screen(img_name: str) -> Optional[Tuple[str, str]]:
    img_upper = (img_name or '').upper()
    if img_upper.endswith('.XMI'):
        return ('loading', _tr('loading'))
    if img_upper == 'QUOTE.IMG':
        return ('quote', _tr('quote'))
    if img_upper == 'SCROLL01.IMG':
        return ('scroll01', _tr('scroll01'))
    if img_upper == 'SCROLL02.IMG':
        return ('scroll02', _tr('scroll02'))
    if img_upper == 'MENU.IMG':
        return ('menu', _tr('menu'))
    if img_upper == 'LOADSAVE.IMG':
        return ('loadsave', _tr('loadsave'))
    return None

def detect_screen(analyzer, anchor: Optional[int], img_name: str, chargen_hint: Optional[str]=None, menu_active_was_zero: bool=False, top_level_state: str='pregame', last_chargen_subscreen: Optional[str]=None, mif_name: str='', area: Optional[str]=None, foreground_ptr: Optional[int]=None, trigger_display_active: bool=False) -> Tuple[str, str]:
    from screen_detector_chargen import detect_chargen_screen
    from screen_detector_play import detect_play_screen
    if analyzer is None or anchor is None:
        return ('loading', _tr('loading'))
    if top_level_state == 'pregame':
        result = _detect_pregame_screen(img_name)
        return result if result is not None else ('loading', _tr('loading'))
    elif top_level_state == 'chargen':
        result = detect_chargen_screen(chargen_hint, img_name, last_subscreen=last_chargen_subscreen)
        if result is not None:
            return result
        fallback = last_chargen_subscreen or 'loading'
        return (fallback, _tr(fallback))
    else:
        return detect_play_screen(analyzer, anchor, img_name, mif_name=mif_name, menu_active_was_zero=menu_active_was_zero, area=area, foreground_ptr=foreground_ptr, trigger_display_active=trigger_display_active)

def get_chargen_subscreen(window) -> Optional[str]:
    if getattr(window, '_chargen_opening_displayed', False):
        return 'opening_cinematic'
    if getattr(window, '_chargen_sex_select_displayed', False):
        return 'sex_select'
    if getattr(window, '_in_chargen_name', False):
        return 'name_input'
    if getattr(window, '_chargen_appearance_displayed', False):
        return 'appearance'
    if getattr(window, '_chargen_choose_attrs_displayed', False):
        return 'choose_attrs'
    if getattr(window, '_chargen_distribute_displayed', False):
        return 'distribute'
    if getattr(window, '_chargen_goyenow_displayed', False):
        return 'goyenow'
    if getattr(window, '_chargen_in_advice', False):
        return 'class_advice'
    if getattr(window, '_chargen_race_desc_displayed', False):
        return 'race_description'
    if getattr(window, '_chargen_complete_displayed', False):
        return 'status_proclamation'
    if getattr(window, '_chargen_race_select_displayed', False):
        return 'race_select'
    if getattr(window, '_chargen_class_accept_displayed', False):
        return 'class_accept'
    if getattr(window, '_chargen_10q_displayed', False):
        return 'ten_questions'
    if getattr(window, '_chargen_class_list_active', False):
        return 'class_list'
    if getattr(window, '_chargen_method_window', False):
        return 'class_select'
    return None
