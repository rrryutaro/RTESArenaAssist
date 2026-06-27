from __future__ import annotations
import sys
_MUTEX_NAME = 'Local\\RTESArenaAssist_SingleInstance_v1'
_WINDOW_TITLE = 'RTESArenaAssist'
_ERROR_ALREADY_EXISTS = 183
_mutex_handle = None

def already_running() -> bool:
    global _mutex_handle
    if not sys.platform.startswith('win'):
        return False
    try:
        import ctypes
        _mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, True, _MUTEX_NAME)
        return ctypes.windll.kernel32.GetLastError() == _ERROR_ALREADY_EXISTS
    except Exception:
        return False

def release() -> None:
    global _mutex_handle
    if _mutex_handle is None or not sys.platform.startswith('win'):
        return
    try:
        import ctypes
        ctypes.windll.kernel32.ReleaseMutex(_mutex_handle)
        ctypes.windll.kernel32.CloseHandle(_mutex_handle)
    except Exception:
        pass
    _mutex_handle = None

def activate_existing_window() -> bool:
    if not sys.platform.startswith('win'):
        return False
    try:
        import ctypes
        found = [0]
        cb_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_long)

        def _on_window(hwnd, _lparam):
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
            if buf.value == _WINDOW_TITLE and ctypes.windll.user32.IsWindowVisible(hwnd):
                found[0] = hwnd
                return False
            return True
        ctypes.windll.user32.EnumWindows(cb_type(_on_window), 0)
        if found[0]:
            SW_RESTORE = 9
            ctypes.windll.user32.ShowWindow(found[0], SW_RESTORE)
            ctypes.windll.user32.SetForegroundWindow(found[0])
            return True
        return False
    except Exception:
        return False
__all__ = ['already_running', 'activate_existing_window', 'release']
