import ctypes
import ctypes.wintypes
import logging
from typing import Optional
try:
    from PIL import Image
    _PIL_OK = True
except ImportError:
    _PIL_OK = False
_log = logging.getLogger('screen_judge.capture')
_PW_CLIENTONLY = 1
_BI_RGB = 0
_SRCCOPY = 13369376

class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [('biSize', ctypes.c_uint32), ('biWidth', ctypes.c_int32), ('biHeight', ctypes.c_int32), ('biPlanes', ctypes.c_uint16), ('biBitCount', ctypes.c_uint16), ('biCompression', ctypes.c_uint32), ('biSizeImage', ctypes.c_uint32), ('biXPelsPerMeter', ctypes.c_int32), ('biYPelsPerMeter', ctypes.c_int32), ('biClrUsed', ctypes.c_uint32), ('biClrImportant', ctypes.c_uint32)]

def get_client_rect(hwnd: int) -> Optional[tuple[int, int, int, int]]:
    pt = ctypes.wintypes.POINT(0, 0)
    ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt))
    rc = ctypes.wintypes.RECT()
    if not ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rc)):
        return None
    w = rc.right - rc.left
    h = rc.bottom - rc.top
    if w <= 0 or h <= 0:
        return None
    return (pt.x, pt.y, pt.x + w, pt.y + h)

def get_client_size(hwnd: int) -> Optional[tuple[int, int]]:
    rc = ctypes.wintypes.RECT()
    if not ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rc)):
        return None
    w = rc.right - rc.left
    h = rc.bottom - rc.top
    if w <= 0 or h <= 0:
        return None
    return (w, h)

def _capture_via_printwindow(hwnd: int, w: int, h: int) -> Optional['Image.Image']:
    hdc_win = ctypes.windll.user32.GetDC(hwnd)
    if not hdc_win:
        return None
    hdc_mem = ctypes.windll.gdi32.CreateCompatibleDC(hdc_win)
    hbmp = ctypes.windll.gdi32.CreateCompatibleBitmap(hdc_win, w, h)
    ctypes.windll.gdi32.SelectObject(hdc_mem, hbmp)
    ok = ctypes.windll.user32.PrintWindow(hwnd, hdc_mem, _PW_CLIENTONLY)
    img = None
    if ok:
        img = _dibits_to_image(hdc_mem, hbmp, w, h)
    ctypes.windll.gdi32.DeleteObject(hbmp)
    ctypes.windll.gdi32.DeleteDC(hdc_mem)
    ctypes.windll.user32.ReleaseDC(hwnd, hdc_win)
    return img

def _capture_via_bitblt(hwnd: int, w: int, h: int) -> Optional['Image.Image']:
    hdc_src = ctypes.windll.user32.GetDC(hwnd)
    if not hdc_src:
        return None
    hdc_mem = ctypes.windll.gdi32.CreateCompatibleDC(hdc_src)
    hbmp = ctypes.windll.gdi32.CreateCompatibleBitmap(hdc_src, w, h)
    ctypes.windll.gdi32.SelectObject(hdc_mem, hbmp)
    ctypes.windll.gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_src, 0, 0, _SRCCOPY)
    img = _dibits_to_image(hdc_mem, hbmp, w, h)
    ctypes.windll.gdi32.DeleteObject(hbmp)
    ctypes.windll.gdi32.DeleteDC(hdc_mem)
    ctypes.windll.user32.ReleaseDC(hwnd, hdc_src)
    return img

def _dibits_to_image(hdc_mem, hbmp, w: int, h: int) -> Optional['Image.Image']:
    bmi = _BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
    bmi.biWidth = w
    bmi.biHeight = -h
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = _BI_RGB
    buf = (ctypes.c_char * (w * h * 4))()
    ret = ctypes.windll.gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0)
    if ret == 0:
        return None
    img = Image.frombuffer('RGBA', (w, h), bytes(buf), 'raw', 'BGRA', 0, 1)
    return img.convert('RGB')

def capture_client_area(hwnd: int) -> Optional['Image.Image']:
    if not _PIL_OK:
        _log.warning('Pillow not available')
        return None
    size = get_client_size(hwnd)
    if size is None:
        _log.debug('get_client_size failed for hwnd=%s', hwnd)
        return None
    w, h = size
    img = _capture_via_printwindow(hwnd, w, h)
    if img is not None:
        return img
    _log.debug('PrintWindow failed, falling back to BitBlt for hwnd=%s', hwnd)
    img = _capture_via_bitblt(hwnd, w, h)
    if img is None:
        _log.warning('Both PrintWindow and BitBlt failed for hwnd=%s', hwnd)
    return img
