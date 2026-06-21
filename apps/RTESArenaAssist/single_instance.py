"""single_instance.py — 多重起動の検出と既存ウィンドウの前面化。

ランチャーは起動ごとに新プロセスを足すため、誤って二重起動すると紛らわしい。
ただし「起動中のインスタンスを終了させる」のは、未保存データ（拡張データ含む）を
失わせる最悪の対処のため行わない。代わりに、既に起動中なら**警告を表示し、起動中の
ウィンドウを前面化して**新しいプロセスは起動を中止する（ルーレットアプリ等と同方式）。

仕組み: Win32 名前付きミューテックス。プロセス終了時に OS が自動解放するため、
クラッシュ後の stale 問題が無い。Python 実行と EXE で同一ミューテックス名を使うため、
どちらの組み合わせでも多重起動を検出する。外部依存（psutil 等）は不要。

Windows 以外・ctypes 不可の環境では常に「単一」とみなし、従来どおり起動する
（多重起動制御なし）。
"""
from __future__ import annotations

import sys

# Python 実行と EXE で同一の名前を使い、どちらの組み合わせでも検出する。
_MUTEX_NAME = "Local\\RTESArenaAssist_SingleInstance_v1"
# AssistWindow のウィンドウタイトル（i18n "app.title" は全言語で固定）。
_WINDOW_TITLE = "RTESArenaAssist"
_ERROR_ALREADY_EXISTS = 183

# プロセス存続中ミューテックスを保持する（解放されると検出が無効になるため）。
_mutex_handle = None


def already_running() -> bool:
    """既存インスタンスがあれば True。無ければミューテックスを確保して False を返す。

    Windows 以外・ctypes 不可時は常に False（多重起動制御を行わない）。
    """
    global _mutex_handle
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        _mutex_handle = ctypes.windll.kernel32.CreateMutexW(
            None, True, _MUTEX_NAME)
        return ctypes.windll.kernel32.GetLastError() == _ERROR_ALREADY_EXISTS
    except Exception:  # noqa: BLE001
        return False


def release() -> None:
    """確保中のミューテックスを明示的に解放する（即時プロセス終了の補助）。

    生成中キャンセルでプロセスを強制終了する際、OS による解放を待たず先に解放して
    新インスタンスが即座に起動できるようにする（裏処理の居座りで再起動できない不具合の
    保険）。確保していなければ何もしない。
    """
    global _mutex_handle
    if _mutex_handle is None or not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        ctypes.windll.kernel32.ReleaseMutex(_mutex_handle)
        ctypes.windll.kernel32.CloseHandle(_mutex_handle)
    except Exception:  # noqa: BLE001
        pass
    _mutex_handle = None


def activate_existing_window() -> bool:
    """起動中アプリのウィンドウを探して前面化する。見つかれば True。

    タイトルが ``_WINDOW_TITLE`` に一致する可視ウィンドウを最前面へ復元する。
    """
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        found = [0]
        cb_type = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.c_void_p, ctypes.c_long)

        def _on_window(hwnd, _lparam):
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
            if (buf.value == _WINDOW_TITLE
                    and ctypes.windll.user32.IsWindowVisible(hwnd)):
                found[0] = hwnd
                return False  # 見つかったら列挙停止
            return True

        ctypes.windll.user32.EnumWindows(cb_type(_on_window), 0)
        if found[0]:
            SW_RESTORE = 9
            ctypes.windll.user32.ShowWindow(found[0], SW_RESTORE)
            ctypes.windll.user32.SetForegroundWindow(found[0])
            return True
        return False
    except Exception:  # noqa: BLE001
        return False


__all__ = ["already_running", "activate_existing_window", "release"]
