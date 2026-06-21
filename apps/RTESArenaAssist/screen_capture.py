"""
screen_capture.py  —  RTESArenaAssist スクリーンキャプチャユーティリティ
==========================================================================
Win32 PrintWindow + GetDIBits でキャプチャする。
ImageGrab.grab() と異なりハードウェアアクセラレーション
(DOSBox, DirectX 等) でも正しく取得できる。

依存: Pillow  (pip install pillow)

使い方:
    from screen_capture import save_screenshots, is_available

    game_path, viewer_path = save_screenshots(
        out_dir    = r"C:\\path\\to\\output",
        cap_no     = 1,
        widget     = main_window,   # QMainWindow インスタンス
        game_pid   = pid,
    )
"""

import os
import ctypes
import ctypes.wintypes

try:
    from PIL import Image
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

# ── Win32 定数 ──────────────────────────────────────────────
_GA_ROOT              = 2   # GetAncestor: ルートウィンドウ
_PW_RENDERFULLCONTENT = 2   # PrintWindow: DWM コンテンツ込みでレンダリング
_BI_RGB               = 0   # BITMAPINFOHEADER.biCompression


# ── BITMAPINFOHEADER 構造体 ────────────────────────────────
class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize",          ctypes.c_uint32),
        ("biWidth",         ctypes.c_int32),
        ("biHeight",        ctypes.c_int32),
        ("biPlanes",        ctypes.c_uint16),
        ("biBitCount",      ctypes.c_uint16),
        ("biCompression",   ctypes.c_uint32),
        ("biSizeImage",     ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32),
        ("biClrUsed",       ctypes.c_uint32),
        ("biClrImportant",  ctypes.c_uint32),
    ]


# ── ウィンドウ列挙 ────────────────────────────────────────
def _find_hwnds_by_prefix(prefix: str) -> list:
    """タイトルが prefix で始まる可視ウィンドウの HWND リストを返す。"""
    result = []
    _EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def _cb(hwnd, _):
        if not ctypes.windll.user32.IsWindowVisible(hwnd):
            return True
        n = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, n + 1)
        if buf.value.startswith(prefix):
            result.append(hwnd)
        return True

    ctypes.windll.user32.EnumWindows(_EnumWindowsProc(_cb), None)
    return result


def _find_hwnds_by_pid(pid: int) -> list:
    """指定 PID の可視ウィンドウの HWND リストを返す（面積降順）。"""
    result = []
    _EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def _cb(hwnd, _):
        if not ctypes.windll.user32.IsWindowVisible(hwnd):
            return True
        win_pid = ctypes.c_ulong(0)
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(win_pid))
        if win_pid.value == pid:
            result.append(hwnd)
        return True

    ctypes.windll.user32.EnumWindows(_EnumWindowsProc(_cb), None)

    def _area(hwnd):
        rect = ctypes.wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return (rect.right - rect.left) * (rect.bottom - rect.top)

    result.sort(key=_area, reverse=True)
    return result


# ── キャプチャ本体 ────────────────────────────────────────
def _capture_hwnd(hwnd: int):
    """
    PrintWindow + GetDIBits でウィンドウをキャプチャする。
    ハードウェアアクセラレーション (DOSBox, DWM 等) に対応。

    Returns:
        PIL.Image.Image または None
    """
    if not _PIL_OK:
        return None

    rect = ctypes.wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right  - rect.left
    h = rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return None

    hdc_win = ctypes.windll.user32.GetWindowDC(hwnd)
    hdc_mem = ctypes.windll.gdi32.CreateCompatibleDC(hdc_win)
    hbmp    = ctypes.windll.gdi32.CreateCompatibleBitmap(hdc_win, w, h)
    ctypes.windll.gdi32.SelectObject(hdc_mem, hbmp)

    ctypes.windll.user32.PrintWindow(hwnd, hdc_mem, _PW_RENDERFULLCONTENT)

    bmi = _BITMAPINFOHEADER()
    bmi.biSize        = ctypes.sizeof(_BITMAPINFOHEADER)
    bmi.biWidth       = w
    bmi.biHeight      = -h   # 負値 = トップダウン
    bmi.biPlanes      = 1
    bmi.biBitCount    = 32
    bmi.biCompression = _BI_RGB

    buf = (ctypes.c_char * (w * h * 4))()
    ctypes.windll.gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0)

    ctypes.windll.gdi32.DeleteObject(hbmp)
    ctypes.windll.gdi32.DeleteDC(hdc_mem)
    ctypes.windll.user32.ReleaseDC(hwnd, hdc_win)

    img = Image.frombuffer("RGBA", (w, h), bytes(buf), "raw", "BGRA", 0, 1)
    return img.convert("RGB")


# ── 公開 HWND 検索関数 ────────────────────────────────────
def find_hwnds_by_prefix(prefix: str) -> list:
    """タイトルが prefix で始まる可視ウィンドウの HWND リストを返す（公開版）。"""
    return _find_hwnds_by_prefix(prefix)


def find_hwnds_by_pid(pid: int) -> list:
    """指定 PID の可視ウィンドウ HWND リストを返す（公開版）。"""
    return _find_hwnds_by_pid(pid)


# ── 公開キャプチャ関数 ────────────────────────────────────
def capture_window_by_prefix(prefix: str):
    """タイトルが prefix で始まる最初の可視ウィンドウをキャプチャする。"""
    if not _PIL_OK:
        return None
    hwnds = _find_hwnds_by_prefix(prefix)
    if not hwnds:
        return None
    return _capture_hwnd(hwnds[0])


def capture_window_by_pid(pid: int):
    """指定 PID のメインウィンドウをキャプチャする（面積最大の可視ウィンドウ）。"""
    if not _PIL_OK:
        return None
    hwnds = _find_hwnds_by_pid(pid)
    if not hwnds:
        return None
    return _capture_hwnd(hwnds[0])


def capture_pyside6_window(window):
    """
    PySide6 の QWidget / QMainWindow をタイトルバーごとキャプチャする。

    Args:
        window: QWidget インスタンス（QMainWindow 等）

    Returns:
        PIL.Image または None
    """
    if not _PIL_OK:
        return None
    hwnd = ctypes.windll.user32.GetAncestor(int(window.winId()), _GA_ROOT)
    if not hwnd:
        hwnd = int(window.winId())
    return _capture_hwnd(hwnd)


# ── 連番管理 ──────────────────────────────────────────────
def next_cap_no(out_dir: str) -> int:
    """out_dir 内の cap_XXX_*.png を走査し、次の連番を返す。"""
    nums = []
    try:
        for name in os.listdir(out_dir):
            if name.startswith("cap_") and name.endswith(".png"):
                part = name[4:].split("_")[0]
                try:
                    nums.append(int(part))
                except ValueError:
                    pass
    except OSError:
        pass
    return max(nums) + 1 if nums else 1


# ── 一括保存 ──────────────────────────────────────────────
def save_screenshots(out_dir: str, cap_no: int,
                     widget=None,
                     game_pid: int = 0,
                     game_prefix: str = "DOSBox",
                     composite_hwnd: int = 0):
    """
    ゲーム画面と Assist 画面を PNG として保存する。

    Args:
        out_dir:     保存先ディレクトリ
        cap_no:      連番（ファイル名 cap_XXX_*.png の XXX 部分）
        widget:      Assist の QMainWindow インスタンス（None なら撮影しない）
        game_pid:    アタッチ済みプロセスの PID（0 の場合は game_prefix で検索）
        game_prefix: game_pid が 0 のときに使うウィンドウタイトルプレフィックス

    Returns:
        (game_path, viewer_path) — 保存できなかった項目は None

    Raises:
        RuntimeError: Pillow が見つからない場合
    """
    if not _PIL_OK:
        raise RuntimeError(
            "Pillow が見つかりません。\n"
            "  pip install pillow  を実行してください。"
        )

    os.makedirs(out_dir, exist_ok=True)

    game_path   = None
    viewer_path = None

    if game_pid:
        img_game = capture_window_by_pid(game_pid)
    else:
        img_game = capture_window_by_prefix(game_prefix)

    img_viewer = None
    if widget is not None:
        img_viewer = capture_pyside6_window(widget)

    # ── コンポジットモード（レイアウトモード用） ──────────────────────
    import logging as _logging
    _cap_log = _logging.getLogger("screen_capture")

    composite_done = False
    if composite_hwnd and img_game and img_viewer:
        try:
            # GA_ROOT で取得したHWNDを使う（capture_pyside6_window と同じ）
            _raw_hwnd = int(widget.winId())
            viewer_hwnd = ctypes.windll.user32.GetAncestor(_raw_hwnd, _GA_ROOT) or _raw_hwnd
            vr = ctypes.wintypes.RECT()
            dr = ctypes.wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(viewer_hwnd, ctypes.byref(vr))
            ctypes.windll.user32.GetWindowRect(composite_hwnd, ctypes.byref(dr))
            rel_x = dr.left - vr.left
            rel_y = dr.top  - vr.top
            _cap_log.debug("composite: viewer(%d,%d) dosbox(%d,%d) rel=(%d,%d) "
                           "viewer_img=%s dosbox_img=%s",
                           vr.left, vr.top, dr.left, dr.top, rel_x, rel_y,
                           img_viewer.size, img_game.size)
            composite = img_viewer.copy()
            composite.paste(img_game, (rel_x, rel_y))
            game_path = os.path.join(out_dir, f"cap_{cap_no:03d}_layout.png")
            composite.save(game_path)
            composite_done = True
        except Exception as _e:
            _cap_log.warning("composite failed: %s", _e, exc_info=True)
            composite_done = False

    if not composite_done:
        if img_game:
            game_path = os.path.join(out_dir, f"cap_{cap_no:03d}_game.png")
            img_game.save(game_path)
        if img_viewer:
            viewer_path = os.path.join(out_dir, f"cap_{cap_no:03d}_viewer.png")
            img_viewer.save(viewer_path)

    return game_path, viewer_path


def capture_screen_region(x: int, y: int, w: int, h: int):
    """
    スクリーン全体から指定の物理ピクセル領域を BitBlt でキャプチャする。
    レイアウトモード用: DOSBox と Assist ウィンドウが自然に合成される。

    Args:
        x, y: スクリーン上の物理座標（左上）
        w, h: キャプチャ幅・高さ（物理ピクセル）

    Returns:
        PIL.Image.Image または None
    """
    if not _PIL_OK or w <= 0 or h <= 0:
        return None

    _SRCCOPY = 0x00CC0020
    hdc_screen = ctypes.windll.user32.GetDC(0)
    hdc_mem    = ctypes.windll.gdi32.CreateCompatibleDC(hdc_screen)
    hbmp       = ctypes.windll.gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
    ctypes.windll.gdi32.SelectObject(hdc_mem, hbmp)
    ctypes.windll.gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, x, y, _SRCCOPY)

    bmi = _BITMAPINFOHEADER()
    bmi.biSize        = ctypes.sizeof(_BITMAPINFOHEADER)
    bmi.biWidth       = w
    bmi.biHeight      = -h
    bmi.biPlanes      = 1
    bmi.biBitCount    = 32
    bmi.biCompression = _BI_RGB

    buf = (ctypes.c_char * (w * h * 4))()
    ctypes.windll.gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0)

    ctypes.windll.gdi32.DeleteObject(hbmp)
    ctypes.windll.gdi32.DeleteDC(hdc_mem)
    ctypes.windll.user32.ReleaseDC(0, hdc_screen)

    img = Image.frombuffer("RGBA", (w, h), bytes(buf), "raw", "BGRA", 0, 1)
    return img.convert("RGB")


def is_available() -> bool:
    """Pillow が利用可能かどうかを返す。"""
    return _PIL_OK
