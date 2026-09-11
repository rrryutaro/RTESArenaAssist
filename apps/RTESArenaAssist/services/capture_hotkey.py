from __future__ import annotations
import ctypes
import logging
import sys
from typing import Callable, Optional
_log = logging.getLogger('RTESArenaAssist')
KEY_CHOICES: tuple[tuple[str, int], ...] = (('F5', 116), ('F6', 117), ('F7', 118), ('F8', 119), ('F9', 120), ('F10', 121), ('F11', 122), ('F12', 123), ('PrintScreen', 44), ('Pause', 19), ('ScrollLock', 145), ('Insert', 45), ('Home', 36), ('End', 35), ('PageUp', 33), ('PageDown', 34))
_VK_BY_NAME = {name: vk for name, vk in KEY_CHOICES}
_NAME_BY_LOWER = {name.lower(): name for name, _vk in KEY_CHOICES}
MODIFIER_ORDER: tuple[str, ...] = ('Ctrl', 'Alt', 'Shift')
_MOD_VK = {'Ctrl': 17, 'Alt': 18, 'Shift': 16}
DEFAULT_HOTKEY = 'F12'
_BLOCKED: frozenset[tuple[frozenset[str], str]] = frozenset([(frozenset({'Ctrl'}), f'F{n}') for n in range(5, 13)] + [(frozenset({'Ctrl', 'Alt'}), f'F{n}') for n in range(5, 13)] + [(frozenset({'Alt'}), 'F12'), (frozenset({'Alt'}), 'Pause')])
WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = (256, 257, 260, 261)

def parse_hotkey(spec: str) -> tuple[frozenset[str], str]:
    parts = [p.strip() for p in (spec or '').split('+') if p.strip()]
    if not parts:
        raise ValueError('empty hotkey')
    key = _NAME_BY_LOWER.get(parts[-1].lower())
    if key is None:
        raise ValueError(f'unsupported key: {parts[-1]!r}')
    mods: set[str] = set()
    for p in parts[:-1]:
        m = {'ctrl': 'Ctrl', 'control': 'Ctrl', 'alt': 'Alt', 'shift': 'Shift'}.get(p.lower())
        if m is None:
            raise ValueError(f'unsupported modifier: {p!r}')
        mods.add(m)
    if (frozenset(mods), key) in _BLOCKED:
        raise ValueError(f'reserved by DOSBox: {format_hotkey(mods, key)}')
    return (frozenset(mods), key)

def format_hotkey(mods, key: str) -> str:
    ordered = [m for m in MODIFIER_ORDER if m in mods]
    return '+'.join(ordered + [key])

def is_blocked(mods, key: str) -> bool:
    return (frozenset(mods), key) in _BLOCKED

def vk_of(key: str) -> int:
    return _VK_BY_NAME[key]
if sys.platform.startswith('win'):
    import ctypes.wintypes as _wt

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [('vkCode', _wt.DWORD), ('scanCode', _wt.DWORD), ('flags', _wt.DWORD), ('time', _wt.DWORD), ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong))]
    HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, _wt.WPARAM, _wt.LPARAM)
    _user32 = ctypes.windll.user32
    _user32.SetWindowsHookExW.restype = _wt.HHOOK
    _user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, _wt.HINSTANCE, _wt.DWORD)
    _user32.CallNextHookEx.restype = ctypes.c_ssize_t
    _user32.CallNextHookEx.argtypes = (_wt.HHOOK, ctypes.c_int, _wt.WPARAM, _wt.LPARAM)
    _user32.UnhookWindowsHookEx.argtypes = (_wt.HHOOK,)
    _user32.GetAsyncKeyState.restype = ctypes.c_short
    _kernel32 = ctypes.windll.kernel32
    _kernel32.GetModuleHandleW.restype = _wt.HMODULE
    _kernel32.GetModuleHandleW.argtypes = (_wt.LPCWSTR,)
else:
    KBDLLHOOKSTRUCT = None
    HOOKPROC = None
    _user32 = None
    _kernel32 = None

def _default_install(proc) -> Optional[int]:
    if _user32 is None:
        return None
    hmod = _kernel32.GetModuleHandleW(None)
    h = _user32.SetWindowsHookExW(WH_KEYBOARD_LL, proc, hmod, 0)
    if not h:
        _log.warning('SetWindowsHookExW failed: GetLastError=%s', ctypes.GetLastError())
        return None
    return int(h)

def _default_uninstall(hook: int) -> None:
    if _user32 is not None:
        _user32.UnhookWindowsHookEx(hook)

def _default_modifier_state() -> frozenset[str]:
    if _user32 is None:
        return frozenset()
    return frozenset((m for m, vk in _MOD_VK.items() if _user32.GetAsyncKeyState(vk) & 32768))

def _qt_dispatch(fn: Callable[[], None]) -> None:
    from PySide6.QtCore import QTimer
    QTimer.singleShot(0, fn)

class CaptureHotkey:

    def __init__(self, on_trigger: Callable[[], None], *, install_fn=None, uninstall_fn=None, dispatch=None, modifier_state=None):
        self._on_trigger = on_trigger
        self._install = install_fn or _default_install
        self._uninstall = uninstall_fn or _default_uninstall
        self._dispatch = dispatch or _qt_dispatch
        self._modifier_state = modifier_state or _default_modifier_state
        self._hook: Optional[int] = None
        self._proc = None
        self._target: Optional[tuple[frozenset[str], int]] = None
        self._down = False
        self.spec: str = ''

    @property
    def registered(self) -> bool:
        return self._hook is not None

    def apply(self, enabled: bool, spec: str) -> tuple[bool, str]:
        self.unregister()
        self.spec = spec or ''
        if not enabled:
            return (True, self.spec)
        try:
            mods, key = parse_hotkey(self.spec)
        except ValueError as e:
            _log.warning('capture hotkey rejected: %s', e)
            return (False, self.spec)
        self._target = (mods, vk_of(key))
        self._down = False
        if HOOKPROC is not None:
            self._proc = HOOKPROC(self._hook_proc)
        hook = self._install(self._proc)
        if not hook:
            _log.warning('capture hotkey hook failed: %s', self.spec)
            self._target = None
            self._proc = None
            return (False, self.spec)
        self._hook = hook
        _log.info('capture hotkey registered: %s', self.spec)
        return (True, self.spec)

    def unregister(self) -> None:
        if self._hook is not None:
            try:
                self._uninstall(self._hook)
            except Exception:
                pass
            self._hook = None
        self._proc = None
        self._target = None
        self._down = False

    def handle(self, vk: int, wparam: int) -> bool:
        if self._target is None:
            return False
        mods, tvk = self._target
        if int(vk) != tvk:
            return False
        if wparam in (WM_KEYUP, WM_SYSKEYUP):
            was = self._down
            self._down = False
            return was
        if wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
            if self._modifier_state() != mods:
                return False
            if not self._down:
                self._down = True
                self._dispatch(self._on_trigger)
            return True
        return False

    def _hook_proc(self, n_code: int, wparam: int, lparam: int) -> int:
        if n_code >= 0 and KBDLLHOOKSTRUCT is not None:
            try:
                kb = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if self.handle(int(kb.vkCode), int(wparam)):
                    return 1
            except Exception:
                pass
        if _user32 is None:
            return 0
        return _user32.CallNextHookEx(None, n_code, wparam, lparam)
